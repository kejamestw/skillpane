"""Attack-oriented regressions. Synthetic filesystem only; unlink is mocked."""
from copy import deepcopy
from hashlib import sha256
import http.client
import json
import os
from pathlib import Path
import threading
import unittest
from unittest.mock import patch

from skillpane.catalog import Catalog
from skillpane.library import Library
from skillpane.server import AppServer
from skillpane.storage import Annotations
from skillpane.transfers import Transfers
from test_catalog import fixture_root, skill


def link_directory(target, alias):
    if os.name == 'nt':
        import _winapi
        _winapi.CreateJunction(str(target), str(alias))
    else:
        alias.symlink_to(target, target_is_directory=True)


class AdversarialStorageTests(unittest.TestCase):
    def setUp(self):
        self.base = fixture_root()
        self.home = self.base / 'home'
        self.source = skill(self.home, '.agents/skills/first', 'first', 'Synthetic API', 'Source sentinel')
        self.other = skill(self.home, '.agents/skills/second', 'second', 'Synthetic helper', 'Second sentinel')
        self.catalog = Catalog(self.home)
        self.store = Annotations(self.base / 'state')
        self.library = Library(self.catalog, self.store)
        self.transfers = Transfers(self.library)
        self.ids = {item['name']: item['id'] for item in self.library.snapshot()['skills']}
        self.source_bytes = self.source.read_bytes()

    def import_payload(self, preview):
        return {'token':preview['token'],'choices':{row['id']:row['target'] for row in preview['rows']},'mode':'replace','restore_settings':False}

    def prepare_cleanup(self):
        for index in range(3):
            self.store.update(self.ids['first'], {'note':f'Synthetic {index}'})
        self.transfers.settings({'keep_last':1})
        return self.transfers.preview_cleanup()

    def test_external_data_change_invalidates_cleanup_without_any_unlink(self):
        preview = self.prepare_cleanup()
        self.store.path.write_text('Externally changed synthetic state', encoding='utf-8')
        with patch.object(Path, 'unlink', autospec=True) as unlink:
            with self.assertRaises(ValueError):
                self.transfers.apply_cleanup({'token':preview['token'],'confirm':True})
            unlink.assert_not_called()

    def test_preview_expires_and_wrong_kind_cannot_mutate_state(self):
        preview = self.transfers.preview_import(self.transfers.export())
        before = self.store.path.read_bytes()
        with self.assertRaises(ValueError):
            self.transfers.apply_cleanup({'token':preview['token'],'confirm':True})
        self.transfers.previews[preview['token']]['expires'] = 0
        with self.assertRaises(ValueError):
            self.transfers.apply_import(self.import_payload(preview))
        self.assertEqual(self.store.path.read_bytes(), before)

    def test_import_preview_owns_its_payload_and_apply_is_single_use(self):
        backup = self.transfers.export()
        backup['records'][0]['annotation'] = {'note':'Previewed value'}
        record_id = backup['records'][0]['id']
        preview = self.transfers.preview_import(backup)
        backup['records'][0]['annotation']['note'] = 'Changed after preview'
        self.transfers.apply_import(self.import_payload(preview))
        self.assertEqual(self.store.state['annotations'][record_id]['note'], 'Previewed value')
        before = self.store.path.read_bytes()
        with self.assertRaises(ValueError):
            self.transfers.apply_import(self.import_payload(preview))
        self.assertEqual(self.store.path.read_bytes(), before)

    def test_invalid_last_import_choice_cannot_partially_apply(self):
        backup = self.transfers.export()
        for record in backup['records']:
            record['annotation'] = {'note':'Must not be partially written'}
        preview = self.transfers.preview_import(backup)
        payload = self.import_payload(preview)
        payload['choices'][backup['records'][-1]['id']] = 'unknown-destination'
        before = self.store.path.read_bytes()
        with self.assertRaises(ValueError):
            self.transfers.apply_import(payload)
        self.assertEqual(self.store.path.read_bytes(), before)
        self.assertEqual(self.source.read_bytes(), self.source_bytes)

    def test_changed_backup_invalidates_whole_cleanup_before_unlink(self):
        preview = self.prepare_cleanup()
        changed = self.transfers.backup_path(preview['files'][-1]['id'])
        changed.write_text('Changed synthetic backup', encoding='utf-8')
        with patch.object(Path, 'unlink', autospec=True) as unlink:
            with self.assertRaises(ValueError):
                self.transfers.apply_cleanup({'token':preview['token'],'confirm':True})
            unlink.assert_not_called()

    def test_backup_directory_rebound_outside_state_is_not_read(self):
        preview = self.prepare_cleanup()
        directory = self.store.directory / 'backups'
        directory.rename(self.store.directory / 'kept-backups')
        outside = self.base / 'outside'
        outside.mkdir()
        sentinel = outside / preview['files'][0]['id']
        sentinel.write_text('Outside sentinel', encoding='utf-8')
        link_directory(outside, directory)
        with self.assertRaises(ValueError):
            self.transfers.preview_restore({'backup_id':sentinel.name})
        with patch.object(Path, 'unlink', autospec=True) as unlink:
            with self.assertRaises(ValueError):
                self.transfers.apply_cleanup({'token':preview['token'],'confirm':True})
            unlink.assert_not_called()
        self.assertEqual(sentinel.read_text(), 'Outside sentinel')

    def rebind_source(self):
        folder = self.source.parent
        folder.rename(folder.with_name('kept-first'))
        outside = self.base / 'outside-skill'
        outside.mkdir()
        (outside / 'SKILL.md').write_text('Outside source sentinel', encoding='utf-8')
        link_directory(outside, folder)

    def test_source_rebound_is_not_read_or_compared(self):
        self.rebind_source()
        for action in [lambda:self.library.content(self.ids['first']),lambda:self.library.comparison(self.ids['first'],self.ids['second'])]:
            with self.assertRaises((OSError,ValueError)):
                action()

    def test_source_rebound_cannot_launch_git_outside_scan_scope(self):
        entry = self.library.skill(self.ids['first'])
        self.library.git_cache[entry['path'], entry['sha256']] = {'state':'not-tracked'}
        self.rebind_source()
        with patch('skillpane.library.subprocess.run') as run:
            with self.assertRaises((OSError,ValueError)):
                self.library.provenance(self.ids['first'])
            run.assert_not_called()

    def test_alias_cannot_reintroduce_an_excluded_trash_directory(self):
        trashed = skill(self.home, '.agents/skills/.trash/retired', 'retired', 'Synthetic excluded skill')
        link_directory(trashed.parent, self.home / '.agents/skills/reintroduced')
        self.catalog.refresh()
        self.assertNotIn('retired', [item['name'] for item in self.catalog.snapshot()['skills']])

    def test_overlong_skill_metadata_does_not_prevent_service_startup(self):
        skill(self.home, '.agents/skills/oversized-name', 'x'*201, 'Synthetic malformed name')
        server = AppServer(port=0, home=self.home, state_dir=self.base / 'fresh-state')
        try:
            snapshot = server.library.snapshot()
            self.assertEqual(snapshot['stats']['total'], 2)
            self.assertGreaterEqual(snapshot['stats']['skipped'], 1)
        finally:
            server.server_close()

    def test_cleanup_token_is_single_use_even_with_mocked_deletion(self):
        preview = self.prepare_cleanup()
        with patch.object(Path, 'unlink', autospec=True) as unlink:
            self.transfers.apply_cleanup({'token':preview['token'],'confirm':True})
            calls = unlink.call_count
            with self.assertRaises(ValueError):
                self.transfers.apply_cleanup({'token':preview['token'],'confirm':True})
            self.assertEqual(unlink.call_count,calls)


class AdversarialHTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base = fixture_root()
        cls.source = skill(cls.base / 'home', '.agents/skills/fixture', 'fixture', 'Synthetic HTTP target')
        cls.server = AppServer(port=0, home=cls.base / 'home', state_dir=cls.base / 'state')
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.skill_id = cls.server.library.snapshot()['skills'][0]['id']

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def request(self, method, path, payload=None, extra=None):
        headers={'Origin':self.server.origin,'Content-Type':'application/json','X-Skillpane-Client':'1'}
        if extra is not None:
            headers.update(extra)
        connection=http.client.HTTPConnection(*self.server.server_address,timeout=5)
        connection.request(method,path,json.dumps(payload) if payload is not None else None,headers)
        response=connection.getresponse()
        status,body=response.status,response.read()
        connection.close()
        return status,body

    def test_cross_origin_and_missing_client_block_every_write_route(self):
        before=self.server.annotations.path.read_bytes()
        routes=['/api/rescan','/api/import/preview','/api/import/apply','/api/restore/preview','/api/relink/preview','/api/relink/apply','/api/backup/settings','/api/backups/cleanup/preview','/api/backups/cleanup/apply','/api/comparison']
        for route in routes:
            for origin in ['https://attacker.invalid','null','http://127.0.0.1:1']:
                with self.subTest(route=route,origin=origin):
                    self.assertEqual(self.request('POST',route,{}, {'Origin':origin})[0],403)
            self.assertEqual(self.request('POST',route,{}, {'X-Skillpane-Client':''})[0],403)
        self.assertEqual(self.server.annotations.path.read_bytes(),before)

    def test_mutated_import_and_annotation_corpus_is_rejected_without_writes(self):
        before=self.server.annotations.path.read_bytes()
        status,raw=self.request('GET','/api/backup')
        self.assertEqual(status,200)
        valid=json.loads(raw)
        corpus=[]
        mutations=[('format',None),('version',True),('exported_at','not-a-date'),('records',{}),('comparisons',{}),('settings',{'keep_last':True})]
        for field,value in mutations:
            item=deepcopy(valid);item[field]=value;corpus.append(item)
        for value in [None,True,17,[],{},'string']:
            for field in ['id','identity','annotation']:
                if field == 'id' and value == 'string' or field == 'annotation' and value == {}:
                    continue  # A valid alternate ID and an empty annotation are supported.
                item=deepcopy(valid);item['records'][0][field]=value;corpus.append(item)
        item=deepcopy(valid);item['records'].append(deepcopy(item['records'][0]));corpus.append(item)
        for payload in corpus:
            with self.subTest(case=len(json.dumps(payload))):
                self.assertEqual(self.request('POST','/api/import/preview',payload)[0],400)
        for payload in [{'tags':[{}]},{'note':[]},{'favorite':1},{'status':{}},{'unknown':'field'},{'alias':'x'*101},{'source_url':'file:///synthetic'},{'summary':'\x00'}]:
            self.assertEqual(self.request('PATCH','/api/annotation?id='+self.skill_id,payload)[0],400)
        self.assertEqual(self.server.annotations.path.read_bytes(),before)

    def test_encoded_and_platform_specific_path_attacks_cannot_read_files(self):
        paths=['/%2e%2e/.git/config','/..%2f.data%2fannotations.json','/..%5c.data%5cannotations.json','/C:/Windows/win.ini','/file:///etc/passwd','/.data/annotations.json%00','/api/skill?id=../../outside','/api/skill?id=%2e%2e%2foutside','/api/skill?id=C%3A%5CWindows%5Cwin.ini']
        for path in paths:
            with self.subTest(path=path):
                self.assertEqual(self.request('GET',path)[0],404)
        self.assertEqual(self.request('GET','/api/health')[0],200)


if __name__ == '__main__':
    unittest.main()

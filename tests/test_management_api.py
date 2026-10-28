import http.client
import json
import threading
import unittest

from skillpane.server import AppServer
from test_catalog import fixture_root, skill


class ManagementAPITests(unittest.TestCase):
    def setUp(self):
        base = fixture_root()
        self.path = skill(base / 'home', '.agents/skills/first', 'first', body='Synthetic first content')
        skill(base / 'home', '.agents/skills/second', 'second', body='Synthetic second content')
        self.original = self.path.read_bytes()
        self.server = AppServer(port=0, home=base / 'home', state_dir=base / 'state')
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.ids = [s['id'] for s in self.server.library.snapshot()['skills']]

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.assertEqual(self.path.read_bytes(),self.original)

    def request(self, method, path, payload=None, trusted=True):
        headers = {'Content-Type':'application/json', 'X-Skillpane-Client':'1', 'Origin':self.server.origin} if trusted else {}
        connection = http.client.HTTPConnection(*self.server.server_address, timeout=10)
        connection.request(method,path,json.dumps(payload) if payload is not None else None,headers)
        response = connection.getresponse()
        result = response.status,json.loads(response.read())
        connection.close()
        return result

    def test_portable_backup_import_and_replay_protection(self):
        skill_id = self.ids[0]
        self.request('PATCH','/api/annotation?id='+skill_id,{'note':'Synthetic backup note','alias':'Synthetic name'})
        code,backup = self.request('GET','/api/backup')
        self.assertEqual(code,200)
        self.assertEqual(backup['format'],'skillpane-backup')
        self.assertNotIn('path_hint',json.dumps(backup))
        self.assertNotIn('Synthetic first content',json.dumps(backup))
        code,preview = self.request('POST','/api/import/preview',backup)
        self.assertEqual(code,200)
        payload = {'token':preview['token'],'choices':{row['id']:row['target'] for row in preview['rows']},'mode':'replace','restore_settings':False}
        self.assertEqual(self.request('POST','/api/import/apply',payload)[0],200)
        self.assertEqual(self.request('POST','/api/import/apply',payload)[0],400)

    def test_comparison_and_custom_metadata_endpoints(self):
        left,right = self.ids
        self.assertEqual(self.request('PATCH','/api/annotation?id='+left,{'tags':['Synthetic'],'category':'My custom category','scope_note':'Read only','modifies_files':'no'})[0],200)
        self.assertEqual(self.request('POST','/api/comparison',{'left_id':left,'right_id':right,'decision':'keep-both','reason':'Different scope'})[0],200)
        code,comparison = self.request('GET',f'/api/compare?left={left}&right={right}')
        self.assertEqual(code,200)
        self.assertEqual(comparison['record']['reason'],'Different scope')
        self.assertFalse(comparison['record']['needs_review'])
        self.assertEqual(self.request('GET',f'/api/compare?left={left}&right={left}')[0],400)
        self.assertEqual(self.request('GET','/api/source?id=missing')[0],404)

    def test_all_management_writes_require_trusted_origin_and_validate_payload(self):
        for route in ['/api/import/preview','/api/import/apply','/api/restore/preview','/api/relink/preview','/api/relink/apply','/api/backup/settings','/api/backups/cleanup/preview','/api/backups/cleanup/apply','/api/comparison']:
            with self.subTest(route=route):
                self.assertEqual(self.request('POST',route,{},trusted=False)[0],403)
        before = self.server.annotations.path.read_bytes()
        for payload in [{'format':'wrong'}, {'format':'skillpane-backup','version':999}, []]:
            self.assertEqual(self.request('POST','/api/import/preview',payload)[0],400)
        self.assertEqual(before,self.server.annotations.path.read_bytes())
        self.assertEqual(self.request('POST','/api/restore/preview',{'backup_id':'../../annotations.json'})[0],400)


if __name__ == '__main__':
    unittest.main()

"""Scan-history regressions use synthetic directories and observations only."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import http.client
import json
from pathlib import Path
import threading
import unittest
from unittest.mock import patch

from skillpane.catalog import Catalog
from skillpane.changes import MAX_EVENTS, MAX_SKILLS, ScanHistory, validate_history
from skillpane.library import Library
from skillpane.server import AppServer
from skillpane.storage import Annotations
from skillpane.transfers import Transfers
from test_catalog import fixture_root, skill


class ChangeTests(unittest.TestCase):
    def setUp(self):
        self.base = fixture_root()
        self.home = self.base / 'home'
        self.path = skill(self.home, '.agents/skills/first', 'first', body='Synthetic history body')
        self.store = Annotations(self.base / 'state')
        self.library = Library(Catalog(self.home), self.store)
        self.history = self.library.history

    def test_baseline_is_not_added_and_reads_and_unchanged_scans_do_not_write(self):
        original = self.history.path.read_bytes()
        stamp = self.history.path.stat().st_mtime_ns
        self.assertEqual(self.library.snapshot()['changes']['events'], [])
        self.library.snapshot()
        self.library.rescan()
        self.assertEqual(self.history.path.read_bytes(), original)
        self.assertEqual(self.history.path.stat().st_mtime_ns, stamp)
        self.assertEqual(list(self.store.directory.glob('scan-history-*.tmp')), [])

    def test_added_changed_missing_and_repeat_scans_are_deduplicated(self):
        self.path.write_text(self.path.read_text() + '\nSynthetic revision', encoding='utf-8')
        added = skill(self.home, '.agents/skills/added', 'added')
        result = self.library.rescan()['changes']
        self.assertCountEqual([e['kind'] for e in result['events']], ['added', 'changed'])
        # Move only our fixture into an excluded directory; no file deletion.
        target = self.home / '.agents/skills/.trash/added'
        target.parent.mkdir()
        added.parent.rename(target)
        result = self.library.rescan()['changes']
        self.assertEqual(result['events'][0]['kind'], 'missing')
        self.assertEqual(result['events'][0]['before']['name'], 'added')
        frozen = self.history.path.read_bytes()
        self.library.rescan()
        self.assertEqual(self.history.path.read_bytes(), frozen)

    def test_restart_observes_changes_and_retains_baseline(self):
        baseline = self.history.snapshot()['baseline_at']
        self.path.write_text(self.path.read_text() + '\nChanged while stopped', encoding='utf-8')
        other = Library(Catalog(self.home), Annotations(self.store.directory))
        self.assertEqual(other.history.snapshot()['baseline_at'], baseline)
        self.assertEqual([e['kind'] for e in other.history.snapshot()['events']], ['changed'])
        again = Library(Catalog(self.home), Annotations(self.store.directory))
        self.assertEqual(len(again.history.snapshot()['events']), 1)

    def test_unique_move_preserves_identity_without_a_false_addition(self):
        self.path.parent.rename(self.path.parent.with_name('moved'))
        self.assertEqual(self.library.rescan()['changes']['events'], [])

    def test_plugin_version_and_old_cache_changes_are_observed(self):
        older = skill(self.home, '.codex/plugins/cache/market/plugin/1/skills/example', 'example', body='Cache one')
        self.library.rescan()
        skill(self.home, '.codex/plugins/cache/market/plugin/2/skills/example', 'example', body='Cache two')
        event = self.library.rescan()['changes']['events'][0]
        self.assertEqual(event['kind'], 'changed')
        self.assertEqual((event['before']['version'], event['after']['version']), ('1', '2'))
        older.write_text(older.read_text() + '\nOld cache changed', encoding='utf-8')
        event = self.library.rescan()['changes']['events'][0]
        self.assertEqual(event['before']['sha256'], event['after']['sha256'])
        self.assertNotEqual(event['before']['cache'], event['after']['cache'])

    def test_partial_scan_preserves_unseen_observations_until_a_complete_scan(self):
        current = self.library.snapshot()['skills']
        self.history.observe([], skipped=1)
        self.assertEqual(self.history.snapshot()['events'], [])
        self.assertEqual(len(self.history.state['observations']), 1)
        self.history.observe(current, skipped=0)
        self.assertEqual(self.history.snapshot()['events'], [])
        self.history.observe([], skipped=0)
        self.assertEqual(self.history.snapshot()['events'][0]['kind'], 'missing')

    def test_retention_keeps_latest_300_events_and_latest_fingerprint(self):
        current = self.library.snapshot()['skills']
        for index in range(MAX_EVENTS + 3):
            current[0]['sha256'] = f'{index:064x}'
            self.history.observe(current)
        data = self.history.snapshot()
        self.assertEqual(len(data['events']), MAX_EVENTS)
        self.assertEqual(data['events'][0]['after']['sha256'], f'{MAX_EVENTS + 2:064x}')
        self.assertEqual(len(self.history.state['observations']), 1)
        validate_history(self.history.state)

    def test_history_does_not_store_bodies_paths_notes_or_enter_portable_backups(self):
        skill_id = self.library.snapshot()['skills'][0]['id']
        self.store.update(skill_id, {'note': 'Synthetic private note'})
        self.path.write_text(self.path.read_text() + '\nSynthetic second body', encoding='utf-8')
        self.library.rescan()
        raw = self.history.path.read_text()
        for forbidden in ('Synthetic history body', 'Synthetic second body', 'Synthetic private note', str(self.home), 'path_hint'):
            self.assertNotIn(forbidden, raw)
        backup = Transfers(self.library).export()
        self.assertNotIn('changes', backup)
        self.assertNotIn('scan-history', json.dumps(backup))

    def test_corrupt_duplicate_future_and_oversized_records_are_preserved(self):
        value = deepcopy(self.history.state)
        future = {**value, 'version': 999}
        for raw in ('{broken', '{"format":"x","format":"y"}', json.dumps(future), 'x' * (8 * 1024 * 1024 + 1)):
            with self.subTest(length=len(raw)):
                self.history.path.write_text(raw, encoding='utf-8')
                other = ScanHistory(self.store)
                other.observe([])
                self.assertTrue(other.snapshot()['error'])
                self.assertEqual(self.history.path.read_text(), raw)

    def test_external_change_and_atomic_failure_preserve_both_data_and_memory(self):
        original = self.history.path.read_bytes()
        current = self.library.snapshot()['skills']
        current[0]['sha256'] = 'a' * 64
        with patch.object(Path, 'replace', side_effect=OSError('Synthetic write failure')):
            self.history.observe(current)
        self.assertTrue(self.history.error)
        self.assertEqual(self.history.path.read_bytes(), original)
        self.assertEqual(self.history.snapshot()['events'], [])
        other = ScanHistory(self.store)
        external = original + b'\n'
        self.history.path.write_bytes(external)
        other.observe(current)
        self.assertTrue(other.error)
        self.assertEqual(self.history.path.read_bytes(), external)

    def test_linked_history_is_rejected_without_writing_target(self):
        target = self.base / 'outside-history.json'
        target.write_text('Synthetic outside target')
        isolated = Annotations(self.base / 'link-state')
        isolated.directory.mkdir()
        link = isolated.directory / 'scan-history.json'
        try:
            link.symlink_to(target)
        except OSError:
            # Windows file symlinks can require a privilege unavailable to CI;
            # exercise a real directory junction instead, without deleting it.
            import _winapi
            isolated.directory.rename(isolated.directory.with_name('original-link-state'))
            outside = self.base / 'outside-directory'
            outside.mkdir()
            target = outside / 'scan-history.json'
            target.write_text('Synthetic outside target')
            _winapi.CreateJunction(str(outside), str(isolated.directory))
        other = ScanHistory(isolated)
        other.observe([])
        self.assertTrue(other.error)
        self.assertEqual(target.read_text(), 'Synthetic outside target')

    def test_capacity_and_invalid_transition_fail_closed(self):
        value = deepcopy(self.history.state)
        item = next(iter(value['observations'].values()))
        value['observations'] = {f'{index:x}': item for index in range(MAX_SKILLS + 1)}
        with self.assertRaises(ValueError):
            validate_history(value)
        value = deepcopy(self.history.state)
        value['events'] = [{'id': 'abc', 'skill_id': 'def', 'kind': 'missing',
                            'observed_at': value['baseline_at'], 'before': item, 'after': item}]
        with self.assertRaises(ValueError):
            validate_history(value)

    def test_concurrent_rescans_record_a_single_change(self):
        self.path.write_text(self.path.read_text() + '\nConcurrent revision', encoding='utf-8')
        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(lambda _: self.library.rescan(), range(4)))
        self.assertEqual(len(self.history.snapshot()['events']), 1)


class ChangeAPITests(unittest.TestCase):
    def test_rescan_requires_origin_and_history_is_not_a_static_resource(self):
        base = fixture_root()
        path = skill(base / 'home', '.agents/skills/first', 'first')
        original = path.read_bytes()
        server = AppServer(port=0, home=base / 'home', state_dir=base / 'state')
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        def request(method, route, trusted=False):
            connection = http.client.HTTPConnection(*server.server_address, timeout=10)
            headers = {'Origin': server.origin, 'Content-Type': 'application/json', 'X-Skillpane-Client': '1'} if trusted else {}
            connection.request(method, route, '{}' if method == 'POST' else None, headers)
            response = connection.getresponse()
            status, body = response.status, response.read()
            connection.close()
            return status, body
        try:
            before = server.library.history.path.read_bytes()
            self.assertEqual(request('POST', '/api/rescan')[0], 403)
            self.assertEqual(server.library.history.path.read_bytes(), before)
            self.assertEqual(request('GET', '/.data/scan-history.json')[0], 404)
            self.assertEqual(request('GET', '/changes.js')[0], 200)
            self.assertEqual(request('POST', '/api/rescan', True)[0], 200)
            self.assertNotIn('changes', json.loads(request('GET', '/api/export')[1]))
            self.assertEqual(path.read_bytes(), original)
        finally:
            server.shutdown()
            server.server_close()
            thread.join()

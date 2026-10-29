"""Exercise copied source bundles and real CLI processes with synthetic homes.

This tests supported data formats, not historical binaries or Python installers.
Fixtures remain under .runtime/test-runs; no real home or running app is used.
"""
from contextlib import contextmanager
from hashlib import sha256
import http.client
import json
import os
from pathlib import Path
import queue
import re
import shutil
import subprocess
import sys
import threading
import unittest

from skillpane import __version__
from skillpane.catalog import Catalog
from test_catalog import fixture_root, skill

ROOT = Path(__file__).resolve().parents[1]


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.base = fixture_root() / 'source bundle with spaces'
        self.bundle = self.base / 'app'
        self.home = self.base / 'synthetic-home'
        self.bundle.mkdir(parents=True)
        for name in ('skillpane', 'web'):
            shutil.copytree(ROOT / name, self.bundle / name,
                            ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
        self.skills = [skill(self.home, f'.agents/skills/lifecycle-{n}',
                             f'lifecycle-{n}', 'Synthetic lifecycle API', f'Synthetic content {n}')
                       for n in range(2)]
        self.fingerprints = [sha256(p.read_bytes()).hexdigest() for p in self.skills]
        # Do not pass credentials, real home, Python import paths or app settings.
        allowed = {'PATH', 'SYSTEMROOT', 'WINDIR', 'TEMP', 'TMP', 'COMSPEC',
                   'SYSTEMDRIVE', 'LANG', 'LC_ALL', 'LD_LIBRARY_PATH'}
        self.env = {k: v for k, v in os.environ.items() if k.upper() in allowed}
        self.env.update(HOME=str(self.home), USERPROFILE=str(self.home),
                        PYTHONUTF8='1', PYTHONDONTWRITEBYTECODE='1')
        self.data = self.bundle / '.data' / 'annotations.json'

    def tearDown(self):
        self.assertEqual([sha256(p.read_bytes()).hexdigest() for p in self.skills], self.fingerprints)
        self.assertFalse((self.bundle / '.git').exists())
        self.assertFalse((self.bundle / 'node_modules').exists())

    @contextmanager
    def running(self):
        process = subprocess.Popen([sys.executable, '-B', '-u', '-m', 'skillpane', '--port', '0'],
                                   cwd=self.bundle, env=self.env, stdin=subprocess.DEVNULL,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   text=True, encoding='utf-8')
        lines = queue.Queue()
        threading.Thread(target=lambda: lines.put(process.stdout.readline()), daemon=True).start()
        try:
            line = lines.get(timeout=30).strip()
            match = re.fullmatch(r'Skillpane [\w.]+ is ready at http://127\.0\.0\.1:(\d+)', line)
            self.assertIsNotNone(match, 'Copied CLI bundle did not become ready.')
            self.port = int(match[1])
            self.assertEqual(self.request('GET', '/api/health')[1],
                             {'app': 'skillpane', 'version': __version__, 'skill_files_readonly': True})
            yield
        finally:
            if process.poll() is None:
                process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=10)
            process.stdout.close()
            process.stderr.close()

    def request(self, method, route, payload=None):
        connection = http.client.HTTPConnection('127.0.0.1', self.port, timeout=10)
        headers = {'Origin': f'http://127.0.0.1:{self.port}',
                   'Content-Type': 'application/json', 'X-Skillpane-Client': '1'}
        try:
            connection.request(method, route, json.dumps(payload) if payload is not None else None, headers)
            response = connection.getresponse()
            content = response.read()
            return response.status, json.loads(content)
        finally:
            connection.close()

    def snapshot(self):
        status, snapshot = self.request('GET', '/api/state')
        self.assertEqual(status, 200)
        self.assertEqual({s['name'] for s in snapshot['skills']}, {'lifecycle-0', 'lifecycle-1'})
        return snapshot

    def apply(self, preview):
        return self.request('POST', '/api/import/apply', {
            'token': preview['token'], 'mode': 'replace', 'restore_settings': True,
            'choices': {row['id']: row['target'] for row in preview['rows']}})

    def test_clean_bundle_start_assets_stop_and_restart(self):
        result = subprocess.run([sys.executable, '-B', '-m', 'skillpane', '--help'],
                                cwd=self.bundle, env=self.env, capture_output=True, timeout=20)
        self.assertEqual(result.returncode, 0)
        self.assertFalse(self.data.exists())
        with self.running():
            before = self.snapshot()
            entry = before['skills'][0]
            annotation = {'favorite': True, 'note': 'Synthetic persistent note',
                          'prompts': [{'id': 'lifecycle-prompt', 'title': '測試', 'body': 'Synthetic\n多行內容'}]}
            self.assertEqual(self.request('PATCH', '/api/annotation?id=' + entry['id'],
                                          {**annotation, 'prompts_base': []})[0], 200)
            connection = http.client.HTTPConnection('127.0.0.1', self.port, timeout=5)
            try:
                for route in ('/', '/app.js', '/management.js', '/prompts.js', '/styles.css', '/favicon.svg'):
                    connection.request('GET', route)
                    response = connection.getresponse()
                    self.assertEqual(response.status, 200)
                    self.assertIn("script-src 'self'", response.getheader('Content-Security-Policy'))
                    self.assertGreater(len(response.read()), 0)
            finally:
                connection.close()
        with self.assertRaises(OSError):
            self.request('GET', '/api/health')
        with self.running():
            after = self.snapshot()
            self.assertEqual([(s['id'], s['first_seen_at']) for s in after['skills']],
                             [(s['id'], s['first_seen_at']) for s in before['skills']])
            self.assertEqual(after['annotations'][entry['id']], annotation)

    def test_legacy_upgrade_backup_restore_and_restart(self):
        raw = Catalog(self.home).snapshot()['skills'][0]
        old = {raw['id']: {'favorite': True, 'note': 'Synthetic legacy note', 'status': 'review'}}
        self.data.parent.mkdir()
        self.data.write_text(json.dumps(old), encoding='utf-8')
        original = self.data.read_bytes()
        with self.running():
            snapshot = self.snapshot()
            entry = next(s for s in snapshot['skills'] if s['name'] == raw['name'])
            self.assertEqual(snapshot['annotations'][entry['id']], old[raw['id']])
            backup_path = next(p for p in (self.data.parent / 'backups').glob('*.json')
                               if p.read_bytes() == original)
            self.assertEqual(json.loads(self.data.read_text(encoding='utf-8'))['version'], 2)
            self.assertEqual(self.request('PATCH', '/api/annotation?id=' + entry['id'],
                                          {'note': 'Synthetic edited note'})[0], 200)
            before_preview = self.data.read_bytes()
            status, preview = self.request('POST', '/api/restore/preview', {'backup_id': backup_path.name})
            self.assertEqual(status, 200)
            self.assertEqual(self.data.read_bytes(), before_preview)
            self.assertEqual(self.apply(preview)[0], 200)
            self.assertEqual(self.snapshot()['annotations'][entry['id']], old[raw['id']])
            self.assertEqual(self.apply(preview)[0], 400)
            self.assertEqual(backup_path.read_bytes(), original)
        with self.running():
            after = self.snapshot()
            self.assertEqual(after['annotations'][entry['id']], old[raw['id']])
            self.assertEqual(next(s for s in after['skills'] if s['id'] == entry['id'])['first_seen_at'],
                             entry['first_seen_at'])

    def test_v2_without_prompts_upgrade_and_portable_restore(self):
        with self.running():
            first, second = self.snapshot()['skills']
            annotation = {'favorite': True, 'alias': 'Synthetic v2 alias', 'note': 'Synthetic v2 note'}
            self.assertEqual(self.request('PATCH', '/api/annotation?id=' + first['id'], annotation)[0], 200)
            self.assertEqual(self.request('POST', '/api/comparison', {
                'left_id': first['id'], 'right_id': second['id'], 'decision': 'keep-both',
                'reason': 'Synthetic pre-prompt comparison'})[0], 200)
            self.assertEqual(self.request('POST', '/api/backup/settings', {'keep_last': 10})[0], 200)
        state = json.loads(self.data.read_text(encoding='utf-8'))
        self.assertEqual(state['version'], 2)
        self.assertNotIn('prompts', state['annotations'][first['id']])
        with self.running():
            before = self.snapshot()
            self.assertEqual(before['annotations'][first['id']], annotation)
            prompts = [{'id': 'upgraded-prompt', 'title': '升級測試', 'body': 'Synthetic prompt after upgrade'}]
            self.assertEqual(self.request('PATCH', '/api/annotation?id=' + first['id'],
                                          {'prompts': prompts, 'prompts_base': []})[0], 200)
            status, backup = self.request('GET', '/api/backup')
            self.assertEqual(status, 200)
            record = next(r for r in backup['records'] if r['id'] == first['id'])
            self.assertEqual(record['annotation'], {**annotation, 'prompts': prompts})
            self.assertEqual(backup['settings'], {'keep_last': 10})
            self.assertEqual(len(backup['comparisons']), 1)
            self.assertNotIn('path_hint', json.dumps(backup))
            self.assertEqual(self.request('PATCH', '/api/annotation?id=' + first['id'],
                                          {'note': 'Synthetic change before restore'})[0], 200)
            before_preview = self.data.read_bytes()
            status, preview = self.request('POST', '/api/import/preview', backup)
            self.assertEqual(status, 200)
            self.assertEqual(self.data.read_bytes(), before_preview)
            self.assertEqual(self.apply(preview)[0], 200)
        with self.running():
            after = self.snapshot()
            self.assertEqual(after['annotations'][first['id']], {**annotation, 'prompts': prompts})
            self.assertEqual(after['comparisons'], before['comparisons'])
            self.assertEqual(json.loads(self.data.read_text(encoding='utf-8'))['settings'], {'keep_last': 10})

    def test_damaged_and_future_data_remain_read_only(self):
        self.data.parent.mkdir()
        for content in ('{invalid synthetic JSON', '{"format":"skillpane-state","version":999}'):
            with self.subTest(content=content):
                self.data.write_text(content, encoding='utf-8')
                original = self.data.read_bytes()
                with self.running():
                    entry = self.snapshot()['skills'][0]
                    self.assertEqual(self.request('PATCH', '/api/annotation?id=' + entry['id'],
                                                  {'note': 'Must not overwrite damaged data'})[0], 400)
                    self.assertEqual(self.data.read_bytes(), original)
                self.assertEqual(self.data.read_bytes(), original)


if __name__ == '__main__':
    unittest.main()

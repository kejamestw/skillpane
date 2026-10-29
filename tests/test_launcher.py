"""Real Windows launcher operations on isolated bundles, ports and synthetic homes."""
from contextlib import contextmanager
from hashlib import sha256
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import threading
import unittest

from test_catalog import fixture_root, skill

ROOT = Path(__file__).resolve().parents[1]
POWERSHELL = shutil.which('powershell.exe')
PWSH = shutil.which('pwsh')


def unused_port():
    while True:
        with socket.socket() as listener:
            listener.bind(('127.0.0.1', 0))
            port = listener.getsockname()[1]
        if port != 8766:
            return port


@unittest.skipUnless(os.name == 'nt' and POWERSHELL, 'Windows PowerShell launcher tests')
class LauncherTests(unittest.TestCase):
    def setUp(self):
        self.base = fixture_root()
        self.home = self.base / 'synthetic-home'
        self.source = skill(self.home, '.agents/skills/launcher-only', 'launcher-only')
        self.fingerprint = sha256(self.source.read_bytes()).hexdigest()
        self.bundle = self.copy_bundle('launcher bundle with spaces 測試')
        self.port = unused_port()
        allowed = {'PATH', 'SYSTEMROOT', 'WINDIR', 'TEMP', 'TMP', 'COMSPEC', 'SYSTEMDRIVE', 'LANG', 'LC_ALL'}
        self.env = {key: value for key, value in os.environ.items() if key.upper() in allowed}
        self.env.update(HOME=str(self.home), USERPROFILE=str(self.home),
                        SKILLPANE_PYTHON=sys.executable, PYTHONUTF8='1', PYTHONDONTWRITEBYTECODE='1')
        self.owned = []
        self.commands = 0

    def copy_bundle(self, name):
        bundle = self.base / name
        bundle.mkdir()
        for directory in ('skillpane', 'web'):
            shutil.copytree(ROOT / directory, bundle / directory,
                            ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
        (bundle / 'scripts').mkdir()
        for filename in ('Start.ps1', 'Stop.ps1'):
            shutil.copyfile(ROOT / filename, bundle / filename)
        for filename in ('Launcher.ps1', 'launcher_entry.py'):
            shutil.copyfile(ROOT / 'scripts' / filename, bundle / 'scripts' / filename)
        return bundle

    def invoke(self, action, *, bundle=None, port=None, shell=None, check=True, extra=()):
        bundle = bundle or self.bundle
        command = [shell or POWERSHELL, '-NoProfile', '-ExecutionPolicy', 'Bypass',
                   '-File', str(bundle / (action + '.ps1')), '-Port', str(self.port if port is None else port)]
        if action == 'Start':
            command.append('-NoBrowser')
        # Background Start-Process descendants can inherit pipe handles even
        # when their own output is redirected. Files avoid waiting for EOF from
        # a service that is intentionally still running after its launcher exits.
        self.commands += 1
        out = self.base / f'command-{self.commands}.stdout.txt'
        err = self.base / f'command-{self.commands}.stderr.txt'
        with out.open('wb') as stdout, err.open('wb') as stderr:
            completed = subprocess.run(command + list(extra), cwd=bundle, env=self.env,
                                       stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr,
                                       creationflags=subprocess.CREATE_NO_WINDOW, timeout=60)
        result = subprocess.CompletedProcess(completed.args, completed.returncode,
                    out.read_text(encoding='utf-8', errors='replace'),
                    err.read_text(encoding='utf-8', errors='replace'))
        if check:
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result

    @staticmethod
    def record_file(bundle):
        return bundle / '.runtime/server.json'

    def start(self, *, bundle=None, port=None, shell=None):
        bundle, port = bundle or self.bundle, self.port if port is None else port
        self.invoke('Start', bundle=bundle, port=port, shell=shell)
        original = self.record_file(bundle).read_bytes()
        record = json.loads(original.decode('utf-8-sig'))
        self.owned.append((bundle, port, original))
        return record

    def request(self, route='/api/health', *, port=None):
        connection = http.client.HTTPConnection('127.0.0.1', self.port if port is None else port, timeout=5)
        try:
            connection.request('GET', route)
            response = connection.getresponse()
            self.assertEqual(response.status, 200)
            return json.loads(response.read())
        finally:
            connection.close()

    def tearDown(self):
        # Only restore records saved immediately after our own successful starts.
        # Never stop a PID obtained from a deliberately corrupted test record.
        for bundle, port, original in reversed(self.owned):
            self.record_file(bundle).write_bytes(original)
            self.invoke('Stop', bundle=bundle, port=port)
        self.assertEqual(sha256(self.source.read_bytes()).hexdigest(), self.fingerprint)
        self.assertFalse((self.bundle / '.git').exists())

    def test_start_duplicate_stop_and_restart_preserves_data(self):
        first = self.start()
        self.assertEqual(self.request()['app'], 'skillpane')
        snapshot = self.request('/api/state')
        self.assertEqual([s['name'] for s in snapshot['skills']], ['launcher-only'])
        record_before = self.record_file(self.bundle).read_bytes()
        state_before = (self.bundle / '.data/annotations.json').read_bytes()
        self.invoke('Start')
        self.assertEqual(self.record_file(self.bundle).read_bytes(), record_before)
        self.assertEqual((self.bundle / '.data/annotations.json').read_bytes(), state_before)
        self.invoke('Stop')
        self.invoke('Stop')
        with self.assertRaises((OSError, http.client.HTTPException)):
            self.request()
        # The old process is gone; do not put its record back during cleanup.
        self.owned.clear()
        second = self.start()
        self.assertNotEqual((first['Pid'], first['StartedUtc']), (second['Pid'], second['StartedUtc']))
        self.assertEqual(self.request('/api/state')['skills'][0]['id'], snapshot['skills'][0]['id'])

    def test_other_port_and_corrupted_identity_are_rejected_without_stopping(self):
        self.start()
        original = self.record_file(self.bundle).read_bytes()
        record = json.loads(original.decode('utf-8-sig'))
        self.assertNotEqual(self.invoke('Start', port=unused_port(), check=False).returncode, 0)
        self.assertNotEqual(self.invoke('Stop', port=unused_port(), check=False).returncode, 0)
        variants = [dict(record, StartedUtc='2000-01-01T00:00:00+00:00'),
                    dict(record, Root=str(self.base)), dict(record, Port=unused_port()),
                    dict(record, PythonPath=str(self.base / 'python.exe')),
                    dict(record, Pid=True), dict(record, RecordVersion=999)]
        for variant in variants:
            with self.subTest(fields=[key for key in variant if variant[key] != record.get(key)]):
                self.record_file(self.bundle).write_text(json.dumps(variant), encoding='utf-8')
                changed = self.record_file(self.bundle).read_bytes()
                self.assertNotEqual(self.invoke('Stop', check=False).returncode, 0)
                self.assertNotEqual(self.invoke('Start', check=False).returncode, 0)
                self.assertEqual(self.record_file(self.bundle).read_bytes(), changed)
                self.assertEqual(self.request()['app'], 'skillpane')
        self.record_file(self.bundle).write_bytes(original)

    def test_other_checkout_process_cannot_be_adopted(self):
        other = self.copy_bundle('other checkout with spaces')
        self.start(bundle=other)
        record = json.loads(self.record_file(other).read_text(encoding='utf-8-sig'))
        record['Root'] = str(self.bundle)
        self.record_file(self.bundle).parent.mkdir()
        self.record_file(self.bundle).write_text(json.dumps(record), encoding='utf-8')
        self.assertNotEqual(self.invoke('Stop', check=False).returncode, 0)
        self.assertNotEqual(self.invoke('Start', check=False).returncode, 0)
        self.assertEqual(self.request()['app'], 'skillpane')
        self.assertFalse((self.bundle / '.data').exists())

    @contextmanager
    def occupied(self, app):
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                body = json.dumps({'app': app, 'skill_files_readonly': True}).encode()
                self.send_response(200)
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            def log_message(self, *args):
                pass
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield server.server_address[1]
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

    def test_occupied_port_is_rejected_even_with_forged_health(self):
        for app in ('unrelated', 'skillpane'):
            with self.subTest(app=app), self.occupied(app) as port:
                self.assertNotEqual(self.invoke('Start', port=port, check=False).returncode, 0)
                self.assertEqual(self.request(port=port)['app'], app)
                self.assertFalse(self.record_file(self.bundle).exists())
                self.assertFalse((self.bundle / '.data').exists())

    def test_missing_corrupt_legacy_records_and_invalid_ports(self):
        self.invoke('Stop')
        for port in (0, -1, 65536):
            for action in ('Start', 'Stop'):
                self.assertNotEqual(self.invoke(action, port=port, check=False).returncode, 0)
        self.assertFalse((self.bundle / '.runtime').exists())
        self.record_file(self.bundle).parent.mkdir()
        self.record_file(self.bundle).write_text('{broken', encoding='utf-8')
        for action in ('Start', 'Stop'):
            self.assertNotEqual(self.invoke(action, check=False).returncode, 0)
        self.assertEqual(self.record_file(self.bundle).read_text(), '{broken')
        # A legacy record pointing to a live process must never be used to kill it.
        self.record_file(self.bundle).write_text(json.dumps({'Pid': os.getpid(), 'Root': str(self.bundle),
            'StartedUtc': '2000-01-01T00:00:00+00:00'}), encoding='utf-8')
        for action in ('Start', 'Stop'):
            self.assertNotEqual(self.invoke(action, check=False).returncode, 0)

    def test_start_failure_is_not_reported_as_ready(self):
        (self.bundle / 'scripts/launcher_entry.py').write_text('raise RuntimeError("Synthetic startup failure")\n')
        result = self.invoke('Start', check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn('Skillpane is ready:', result.stdout)
        with self.assertRaises((OSError, http.client.HTTPException)):
            self.request()
        self.invoke('Stop')

    def test_lock_blocks_concurrent_launcher_operations(self):
        self.start()
        original = self.record_file(self.bundle).read_bytes()
        # Open with FileShare.None inside a process we own. The actual launchers
        # must fail rather than replace the record or stop its running service.
        # Keep the lock until this test explicitly closes stdin. A fixed sleep
        # can expire while hosted Windows runners are still starting PowerShell.
        code = "$lock=[IO.File]::Open($args[0],'Open','ReadWrite','None');try{[Console]::WriteLine('locked');[Console]::In.ReadLine() | Out-Null}finally{$lock.Dispose()}"
        script = self.base / 'hold-lock.ps1'
        script.write_text(code, encoding='utf-8')
        process = subprocess.Popen([POWERSHELL, '-NoProfile', '-File', str(script),
                                    str(self.bundle / '.runtime/launcher.lock')], env=self.env,
                                   stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                   stderr=subprocess.DEVNULL, text=True,
                                   creationflags=subprocess.CREATE_NO_WINDOW)
        try:
            self.assertEqual(process.stdout.readline().strip(), 'locked')
            for action in ('Start', 'Stop'):
                self.assertIsNone(process.poll(), 'Lock holder exited before the competing operation.')
                self.assertNotEqual(self.invoke(action, check=False).returncode, 0)
            self.assertIsNone(process.poll(), 'Lock holder must outlive both competing operations.')
            self.assertEqual(self.record_file(self.bundle).read_bytes(), original)
            self.assertEqual(self.request()['app'], 'skillpane')
        finally:
            process.stdin.close()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.terminate()
                process.wait(timeout=10)
            process.stdout.close()

    @unittest.skipUnless(PWSH, 'PowerShell 7 is not installed')
    def test_powershell_7_uses_the_same_record_and_process_identity(self):
        self.start(shell=PWSH)
        self.invoke('Start', shell=POWERSHELL)
        self.invoke('Stop', shell=PWSH)
        self.owned.clear()
        with self.assertRaises((OSError, http.client.HTTPException)):
            self.request()


if __name__ == '__main__':
    unittest.main()

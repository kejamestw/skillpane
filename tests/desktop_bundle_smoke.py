"""Opt-in relocated EXE smoke; synthetic profile, no Python on PATH, no GUI automation."""
import ctypes
from ctypes import wintypes
from hashlib import sha256
import http.client
import json
import os
from pathlib import Path
import shutil
import socket
import struct
import subprocess
import sys
import time
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]


def listener_ports(pid):
    class Row(ctypes.Structure):
        _fields_ = [(field, wintypes.DWORD) for field in ('state', 'local_address', 'local_port',
                                                        'remote_address', 'remote_port', 'pid')]
    api = ctypes.WinDLL('iphlpapi').GetExtendedTcpTable
    api.argtypes = [wintypes.LPVOID, ctypes.POINTER(wintypes.DWORD), wintypes.BOOL,
                    wintypes.ULONG, ctypes.c_int, wintypes.ULONG]
    api.restype = wintypes.DWORD
    size = wintypes.DWORD()
    status = api(None, ctypes.byref(size), False, socket.AF_INET, 3, 0)
    if status not in (0, 122):
        raise RuntimeError('Cannot inspect owned TCP listener.')
    for _ in range(3):
        buffer = ctypes.create_string_buffer(size.value)
        status = api(buffer, ctypes.byref(size), False, socket.AF_INET, 3, 0)
        if status == 122:
            continue
        if status:
            raise RuntimeError('Cannot inspect owned TCP listener.')
        count = wintypes.DWORD.from_buffer(buffer).value
        rows = (Row * count).from_buffer(buffer, ctypes.sizeof(wintypes.DWORD))
        return [socket.ntohs(row.local_port & 0xffff) for row in rows
                if row.pid == pid and socket.inet_ntoa(struct.pack('<I', row.local_address)) == '127.0.0.1']
    raise RuntimeError('TCP table changed repeatedly.')


def main():
    executable = Path(sys.argv[1]).resolve()
    if os.name != 'nt' or executable.name != 'Skillpane.exe' or not executable.is_file():
        raise SystemExit('Pass the built Windows Skillpane.exe.')
    base = ROOT / '.runtime' / ('desktop-bundle-smoke-' + uuid4().hex)
    app = base / 'relocated app with spaces'
    shutil.copytree(executable.parent, app)
    home = base / 'synthetic-home'
    local = base / 'synthetic-local-app-data'
    target = home / '.agents/skills/bundled-demo/SKILL.md'
    target.parent.mkdir(parents=True)
    target.write_text('---\nname: bundled-demo\ndescription: 合成桌面包驗證。\n---\n# Synthetic only\n', encoding='utf-8')
    fingerprint = sha256(target.read_bytes()).hexdigest()
    allowed = {'SYSTEMROOT', 'WINDIR', 'TEMP', 'TMP', 'COMSPEC', 'SYSTEMDRIVE',
               'PROGRAMFILES', 'PROGRAMFILES(X86)', 'PROGRAMW6432'}
    env = {key: value for key, value in os.environ.items() if key.upper() in allowed}
    env.update(USERPROFILE=str(home), HOME=str(home), LOCALAPPDATA=str(local),
               APPDATA=str(base / 'synthetic-roaming-app-data'),
               PATH=str(Path(os.environ['SYSTEMROOT']) / 'System32'))
    process = subprocess.Popen([str(app / 'Skillpane.exe')], cwd=home, env=env,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                               creationflags=subprocess.CREATE_NO_WINDOW)
    checks = []
    def request(route, payload=None, method='GET'):
        connection = http.client.HTTPConnection('127.0.0.1', port, timeout=5)
        try:
            headers = {'Origin': f'http://127.0.0.1:{port}', 'X-Skillpane-Client': '1', 'Content-Type': 'application/json'}
            connection.request(method, route, json.dumps(payload) if payload is not None else None, headers)
            response = connection.getresponse()
            content = response.read()
            assert response.status == 200, 'Bundled HTTP request failed.'
            return content, dict(response.getheaders())
        finally:
            connection.close()
    try:
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            assert process.poll() is None, 'Bundled desktop exited during startup.'
            ports = listener_ports(process.pid)
            if len(ports) == 1:
                port = ports[0]
                try:
                    health = json.loads(request('/api/health')[0])
                    if health.get('app') == 'skillpane':
                        break
                except (OSError, ValueError):
                    pass
            time.sleep(0.2)
        else:
            raise AssertionError('Bundled desktop did not become ready.')
        checks.append('relocated-exe-starts-without-python-on-path')
        state = json.loads(request('/api/state')[0])
        assert [s['name'] for s in state['skills']] == ['bundled-demo']
        checks.append('only-generated-home-scanned')
        script, headers = request('/app.js')
        assert sha256(script).digest() == sha256((ROOT / 'web/app.js').read_bytes()).digest()
        assert 'unsafe-eval' not in headers['Content-Security-Policy']
        checks.append('current-frontend-bundled-with-original-csp')
        assert request('/favicon.svg')[0] == (ROOT / 'web/favicon.svg').read_bytes()
        assert (app / '_internal/desktop-assets/skillpane.ico').read_bytes() == (ROOT / 'assets/brand/skillpane.ico').read_bytes()
        checks.append('approved-icon-in-web-and-desktop-bundle')
        request('/api/annotation?id=' + state['skills'][0]['id'], {'note': 'Synthetic bundled note'}, 'PATCH')
        assert (local / 'Skillpane/data/annotations.json').is_file()
        assert 'Synthetic bundled note' in request('/api/backup')[0].decode('utf-8')
        checks.append('organization-saved-under-generated-local-app-data')
        second = subprocess.run([str(app / 'Skillpane.exe')], cwd=home, env=env,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                timeout=30, creationflags=subprocess.CREATE_NO_WINDOW)
        assert second.returncode == 0 and process.poll() is None
        assert listener_ports(process.pid) == [port]
        checks.append('second-exe-launch-reuses-owned-instance')
        assert sha256(target.read_bytes()).hexdigest() == fingerprint
        checks.append('synthetic-skill-remains-unchanged')
    finally:
        # This is explicit fixture teardown, not a claim of native close-button coverage.
        if process.poll() is None:
            process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=10)
    assert not listener_ports(process.pid)
    checks.append('owned-listener-released-after-fixture-termination')
    result = {'checks': checks, 'count': len(checks), 'fixture_teardown': 'forced-owned-process-only',
              'clean_windows_without_python': 'not-tested', 'native_close_button': 'covered-by-source-integration-only'}
    (base / 'result.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result), flush=True)


if __name__ == '__main__':
    main()

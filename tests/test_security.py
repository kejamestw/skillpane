"""Security regressions use synthetic data and never delete real backups."""
import http.client
import json
import os
from pathlib import Path
import stat
import threading
import unittest
from unittest.mock import Mock
from types import SimpleNamespace

from skillpane.server import AppServer, Handler
from skillpane.storage import Annotations, strict_json_loads
from test_catalog import fixture_root, skill


class SecurityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base = fixture_root()
        cls.source = skill(cls.base / 'home', '.agents/skills/synthetic', body='<img src=x onerror=alert(1)>')
        cls.server = AppServer(port=0, home=cls.base / 'home', state_dir=cls.base / 'state')
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.skill_id = cls.server.library.snapshot()['skills'][0]['id']

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def request(self, method, path, body=b'', extra=()):
        connection = http.client.HTTPConnection(*self.server.server_address, timeout=5)
        connection.putrequest(method, path, skip_host=True)
        connection.putheader('Host', self.server.origin.removeprefix('http://'))
        for key, value in extra:
            connection.putheader(key, value)
        connection.endheaders(body)
        response = connection.getresponse()
        result = response.status, dict(response.getheaders()), response.read()
        connection.close()
        return result

    def write_headers(self, body):
        return [('Origin', self.server.origin), ('X-Skillpane-Client', '1'),
                ('Content-Type', 'application/json'), ('Content-Length', str(len(body)))]

    def test_duplicate_security_headers_are_rejected(self):
        for header in ('Host', 'Origin', 'Sec-Fetch-Site', 'Content-Type', 'X-Skillpane-Client'):
            body = b'{}'
            headers = self.write_headers(body)
            value = dict(headers).get(header, 'same-origin')
            if header == 'Host':
                value = self.server.origin.removeprefix('http://')
            if header == 'Sec-Fetch-Site':
                headers.append((header, value))
            with self.subTest(header=header):
                self.assertEqual(self.request('POST', '/api/rescan', body, headers + [(header, value)])[0], 403)

    def test_ambiguous_json_and_deep_bodies_do_not_change_data(self):
        original = self.server.annotations.path.read_bytes()
        bodies = [b'{"note":"first","note":"second"}', b'{"note":NaN}',
                  b'{"note":Infinity}', b'{"note":' + b'[' * 1500 + b'0' + b']' * 1500 + b'}', b'{broken']
        for body in bodies:
            with self.subTest(size=len(body)):
                code, _, _ = self.request('PATCH', '/api/annotation?id=' + self.skill_id, body, self.write_headers(body))
                self.assertEqual(code, 400)
                self.assertEqual(self.server.annotations.path.read_bytes(), original)
        self.assertEqual(self.request('GET', '/api/health')[0], 200)

    def test_malformed_request_targets_are_rejected(self):
        for path in ('http://[', 'http://example.invalid/api/state', '/api/state#fragment'):
            with self.subTest(path=path):
                self.assertEqual(self.request('GET', path)[0], 400)

    def test_transfer_encoding_and_oversized_requests_are_rejected(self):
        body = b'{}'
        original = self.server.annotations.path.read_bytes()
        # Send headers only: these requests must be rejected before reading any
        # body. Sending unread bytes races Windows' TCP reset on early close.
        chunked = self.write_headers(body) + [('Transfer-Encoding', 'chunked')]
        self.assertEqual(self.request('POST', '/api/rescan', b'', chunked)[0], 400)
        headers = [(key, str(5 * 1024 * 1024) if key == 'Content-Length' else value) for key, value in self.write_headers(body)]
        self.assertEqual(self.request('POST', '/api/import/preview', b'', headers)[0], 400)
        for values in (chunked, headers):
            handler = object.__new__(Handler)
            handler.headers = http.client.HTTPMessage()
            for key, value in values:
                handler.headers.add_header(key, value)
            handler.rfile = Mock()
            with self.assertRaises(ValueError):
                handler.body(4 * 1024 * 1024 + 65536)
            handler.rfile.read.assert_not_called()
        self.assertEqual(self.server.annotations.path.read_bytes(), original)
        self.assertEqual(self.request('GET', '/api/health')[0], 200)

    def test_duplicate_lengths_are_rejected_at_the_parsed_header_boundary(self):
        # Some local network middleware normalizes Content-Length before Python.
        handler = object.__new__(Handler)
        handler.server = SimpleNamespace(origin=self.server.origin)
        handler.headers = http.client.HTTPMessage()
        for key, value in [('Host', self.server.origin.removeprefix('http://')), *self.write_headers(b'{}'), ('Content-Length', '3')]:
            handler.headers.add_header(key, value)
        handler.json = Mock()
        self.assertFalse(handler.trusted(write=True))
        self.assertEqual(handler.json.call_args.args[1], 403)

    def test_private_paths_and_encoded_traversal_are_not_served(self):
        for path in ('/.git/config', '/.data/backups/example.json', '/%2e%2e/.data/annotations.json', '/management.js/../../skillpane/server.py', '/.runtime/server.json'):
            with self.subTest(path=path):
                self.assertEqual(self.request('GET', path)[0], 404)

    def test_security_headers_cover_management_assets_and_errors(self):
        for path in ('/management.js', '/prompts.js', '/api/health', '/not-found'):
            _, headers, _ = self.request('GET', path)
            self.assertEqual(headers['X-Content-Type-Options'], 'nosniff')
            self.assertEqual(headers['X-Frame-Options'], 'DENY')
            self.assertEqual(headers['Referrer-Policy'], 'no-referrer')
            self.assertNotIn('Access-Control-Allow-Origin', headers)
            self.assertIn("script-src 'self'", headers['Content-Security-Policy'])
            self.assertNotIn("'unsafe-inline'", headers['Content-Security-Policy'])

    def test_raw_skill_is_json_text_and_source_is_unchanged(self):
        original = self.source.read_bytes()
        code, headers, body = self.request('GET', '/api/skill?id=' + self.skill_id)
        self.assertEqual(code, 200)
        self.assertTrue(headers['Content-Type'].startswith('application/json'))
        self.assertIn('<img src=x onerror=alert(1)>', json.loads(body)['content'])
        self.assertEqual(self.source.read_bytes(), original)

    def test_dangerous_source_urls_are_rejected_without_writes(self):
        original = self.server.annotations.path.read_bytes()
        for url in ('javascript:alert(1)', 'data:text/html,test', 'https://user:synthetic@example.invalid', 'https://example.invalid/?token=synthetic'):
            body = json.dumps({'source_url': url}).encode()
            self.assertEqual(self.request('PATCH', '/api/annotation?id=' + self.skill_id, body, self.write_headers(body))[0], 400)
        self.assertEqual(self.server.annotations.path.read_bytes(), original)

    @unittest.skipUnless(os.name == 'posix', 'POSIX file modes; Windows uses inherited NTFS ACLs')
    def test_local_data_and_backups_are_private_on_posix(self):
        store = Annotations(fixture_root() / 'private-state')
        store.update('synthetic', {'note': 'First synthetic note'})
        store.update('synthetic', {'note': 'Second synthetic note'})
        for directory in (store.directory, store.directory / 'backups'):
            self.assertEqual(stat.S_IMODE(directory.stat().st_mode), 0o700)
        for path in [store.path, *(store.directory / 'backups').glob('*.json')]:
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)

    def test_strict_json_reader_rejects_duplicates_and_nonfinite_numbers(self):
        for body in ('{"a":1,"a":2}', '{"a":NaN}', '{"a":-Infinity}'):
            with self.assertRaises(ValueError):
                strict_json_loads(body)
        self.assertEqual(strict_json_loads('{"a":false}'), {'a': False})


if __name__ == '__main__':
    unittest.main()

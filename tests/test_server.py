import http.client
import io
import json
from pathlib import Path
import threading
import unittest
from unittest.mock import patch

from skillpane.server import AppServer
from test_catalog import fixture_root, skill


class ServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        base = fixture_root()
        cls.skill_path = skill(base / 'home', '.agents/skills/fixture', body='Original synthetic skill')
        cls.original = cls.skill_path.read_bytes()
        cls.server = AppServer(port=0, home=base / 'home', state_dir=base / 'state')
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.skill_id = cls.server.library.snapshot()['skills'][0]['id']

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def request(self, method, path, headers=None, payload=None):
        connection = http.client.HTTPConnection(*self.server.server_address, timeout=10)
        connection.request(method, path, json.dumps(payload) if payload is not None else None, headers or {})
        response = connection.getresponse()
        result = response.status, dict(response.getheaders()), response.read()
        connection.close()
        return result

    def write_headers(self):
        return {'Origin':self.server.origin, 'X-Skillpane-Client':'1', 'Content-Type':'application/json'}

    def test_state_and_skill_content(self):
        code, _, body = self.request('GET', '/api/state')
        self.assertEqual(code, 200)
        self.assertEqual(json.loads(body)['stats']['personal'], 1)
        code, _, body = self.request('GET', '/api/skill?id=' + self.skill_id)
        self.assertIn('Original synthetic skill', json.loads(body)['content'])

    def test_readonly_skill_methods(self):
        for method, path in [('PUT','/api/skill'),('DELETE','/api/skill'),('POST','/api/skill/archive'),('POST','/api/skills')]:
            with self.subTest(method=method,path=path):
                self.assertEqual(self.request(method,path,self.write_headers(),{})[0], 405)
        self.assertEqual(self.skill_path.read_bytes(), self.original)

    def test_cross_origin_host_and_fetch_site_rejected(self):
        for headers in [{'Origin':'https://attacker.invalid'}, {'Host':'attacker.invalid'}, {'Sec-Fetch-Site':'cross-site'}, {'Sec-Fetch-Site':'same-site'}]:
            with self.subTest(headers=headers):
                self.assertEqual(self.request('GET','/api/state',headers)[0],403)

    def test_metadata_write_requires_same_origin_json_and_client_header(self):
        url = '/api/annotation?id=' + self.skill_id
        for headers in [{}, {'Origin':self.server.origin}, {'Origin':self.server.origin,'Content-Type':'text/plain','X-Skillpane-Client':'1'}]:
            self.assertEqual(self.request('PATCH',url,headers,{'favorite':True})[0],403)
        code,_,body = self.request('PATCH',url,self.write_headers(),{'favorite':True})
        self.assertEqual(code,200)
        self.assertTrue(json.loads(body)['favorite'])
        self.assertEqual(self.skill_path.read_bytes(),self.original)

    def test_unknown_annotation_id_and_content_id_rejected(self):
        self.assertEqual(self.request('PATCH','/api/annotation?id=unknown',self.write_headers(),{'favorite':True})[0],404)
        self.assertEqual(self.request('GET','/api/skill?id=unknown')[0],404)

    def test_static_allowlist_and_security_headers(self):
        for path in ['/../skillpane/server.py','/.data/annotations.json','/.env','/LICENSE']:
            self.assertEqual(self.request('GET',path)[0],404)
        for path in ['/','/app.js','/styles.css','/favicon.svg']:
            code,headers,_ = self.request('GET',path)
            self.assertEqual(code,200)
            self.assertIn("frame-ancestors 'none'",headers['Content-Security-Policy'])
            self.assertEqual(headers['Cache-Control'],'no-store')

    def test_static_assets_are_served_from_memory(self):
        expected = (Path(__file__).resolve().parents[1] / 'web/app.js').read_bytes()
        with patch.object(Path, 'read_bytes', side_effect=AssertionError('static asset read from disk')):
            code, headers, body = self.request('GET', '/app.js')
        self.assertEqual((code, body), (200, expected))
        self.assertEqual(headers['Content-Type'], 'text/javascript; charset=utf-8')

    def test_export_omits_paths_and_body(self):
        code,_,body = self.request('GET','/api/export')
        entry = json.loads(body)['skills'][0]
        self.assertEqual(code,200)
        self.assertNotIn('path',entry)
        self.assertNotIn('aliases',entry)
        self.assertNotIn('source',entry['invocation']['codex'])
        self.assertNotIn('roots',json.loads(body)['scan_scope'])
        self.assertIn('source',self.server.catalog.snapshot()['skills'][0]['invocation']['codex'])
        self.assertNotIn(b'Original synthetic skill',body)

    def test_rescan_requires_trusted_request(self):
        self.assertEqual(self.request('POST','/api/rescan',{},{} )[0],403)
        self.assertEqual(self.request('POST','/api/rescan',self.write_headers(),{})[0],200)

    def test_unexpected_failures_return_generic_json_and_server_keeps_serving(self):
        cases = [('GET', '/api/state', None, self.server.library, 'snapshot'),
                 ('GET', '/api/export', None, self.server.catalog, 'snapshot'),
                 ('POST', '/api/rescan', {}, self.server.library, 'rescan'),
                 ('PATCH', '/api/annotation?id=' + self.skill_id, {'favorite': True}, self.server.annotations, 'update')]
        for method, path, payload, owner, name in cases:
            with self.subTest(method=method, path=path):
                headers = self.write_headers() if method != 'GET' else None
                with patch.object(owner, name, side_effect=AttributeError('C:/synthetic/private/path')), \
                        patch('sys.stderr', new_callable=io.StringIO) as stderr:
                    code, response_headers, body = self.request(method, path, headers, payload)
                self.assertEqual(code, 500)
                self.assertTrue(response_headers['Content-Type'].startswith('application/json'))
                self.assertIn("default-src 'none'", response_headers['Content-Security-Policy'])
                self.assertIn('error', json.loads(body))
                self.assertNotIn(b'synthetic/private', body)
                self.assertEqual(stderr.getvalue(), 'Skillpane request failed: AttributeError\n')
        self.assertEqual(self.request('GET', '/api/state')[0], 200)

    def test_refuses_lan_and_state_inside_skill_root(self):
        with self.assertRaises(ValueError):
            AppServer(host='0.0.0.0')
        with self.assertRaises(ValueError):
            AppServer(home=self.server.catalog.home,state_dir=self.server.catalog.home / '.agents/skills/state')


class PythonVersionTests(unittest.TestCase):
    def test_unsupported_python_stops_with_a_readable_message(self):
        import importlib
        import sys
        import skillpane
        try:
            with patch.object(sys, 'version_info', (3, 10, 14, 'final', 0)):
                with self.assertRaisesRegex(SystemExit, 'Python 3.11 or newer'):
                    importlib.reload(skillpane)
        finally:
            importlib.reload(skillpane)
        self.assertTrue(skillpane.__version__)


if __name__ == '__main__':
    unittest.main()

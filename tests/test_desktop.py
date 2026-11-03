"""Desktop lifecycle, storage and trust boundaries without requiring a GUI."""
from hashlib import sha256
import http.client
import json
import os
from pathlib import Path
import threading
import unittest
from unittest.mock import Mock, patch
from uuid import uuid4

from skillpane.desktop import (CloseGuard, DesktopServer, DesktopService, PreferenceStore,
                               checked_directory, default_directory, instance_name, preferences)
from skillpane.desktop_windows import download_allowed, navigation_allowed
from test_catalog import fixture_root, skill


class DesktopTests(unittest.TestCase):
    def setUp(self):
        self.root = fixture_root() / 'desktop with spaces'
        self.root.mkdir()

    def test_default_location_does_not_depend_on_checkout(self):
        with patch.dict(os.environ, {'LOCALAPPDATA': str(self.root)}):
            self.assertEqual(default_directory(), self.root / 'Skillpane')
        with patch.dict(os.environ, {'LOCALAPPDATA': 'relative'}):
            self.assertRaises(ValueError, default_directory)

    def test_preferences_are_bounded_and_survive_restart(self):
        store = PreferenceStore(self.root)
        value = {'skillpane-theme': 'dark', 'skillpane-text-size': 'large', 'skillpane-sidebar-hidden': '1'}
        store.save(value)
        self.assertEqual(PreferenceStore(self.root).value, value)
        original = store.path.read_bytes()
        for bad in ({'url': 'file:///outside'}, {'skillpane-theme': ['dark']},
                    {'skillpane-sidebar-hidden': True}, {'skillpane-theme': '</script>'}):
            self.assertRaises(ValueError, store.save, bad)
            self.assertEqual(store.path.read_bytes(), original)
        self.assertEqual(list(self.root.glob('*.tmp')), [])

    def test_external_preference_change_is_preserved(self):
        store = PreferenceStore(self.root)
        store.path.write_text('{"skillpane-theme":"light"}', encoding='utf-8')
        self.assertRaises(ValueError, store.save, {'skillpane-theme': 'dark'})
        self.assertEqual(PreferenceStore(self.root).value, {'skillpane-theme': 'light'})

    def test_corrupt_and_oversized_preferences_are_not_replaced(self):
        path = self.root / 'desktop-preferences.json'
        for content in ('{"skillpane-theme":"light","skillpane-theme":"dark"}', 'x' * 4097):
            path.write_text(content, encoding='utf-8')
            self.assertRaises(ValueError, PreferenceStore, self.root)
            self.assertEqual(path.read_text(encoding='utf-8'), content)

    def test_rebound_directory_is_rejected(self):
        real = self.root / 'real'
        real.mkdir()
        alias = self.root / 'alias'
        if os.name == 'nt':
            import _winapi
            _winapi.CreateJunction(str(real), str(alias))
        else:
            alias.symlink_to(real, target_is_directory=True)
        self.assertRaises(ValueError, checked_directory, alias)

    def test_navigation_and_download_allow_only_owned_content(self):
        origin = 'http://127.0.0.1:54321'
        self.assertTrue(navigation_allowed(origin + '/#skills', origin))
        for uri in ('file:///etc/passwd', 'https://example.com/', origin + '.evil/',
                    origin + '/api/state', origin + '/?url=https://example.com',
                    'javascript:alert(1)', 'http://user@127.0.0.1:54321/'):
            self.assertFalse(navigation_allowed(uri, origin), uri)
        self.assertTrue(download_allowed('blob:' + origin + '/id', origin, 'application/json'))
        for uri, mime in [('https://example.com/file', 'application/json'),
                          ('blob:' + origin + '.evil/id', 'application/json'),
                          ('blob:' + origin + '/id', 'application/x-msdownload')]:
            self.assertFalse(download_allowed(uri, origin, mime))

    def test_owned_service_uses_free_port_keeps_csp_and_stops(self):
        home = self.root / 'home'
        target = skill(home, '.agents/skills/desktop-demo', 'desktop-demo', body='Synthetic desktop only')
        fingerprint = sha256(target.read_bytes()).hexdigest()
        server = DesktopServer(home=home, directory=self.root / 'data', display={'skillpane-theme': 'dark'})
        service = DesktopService(server)
        service.start()
        port = server.server_address[1]
        def request(route, headers=None):
            connection = http.client.HTTPConnection('127.0.0.1', port, timeout=5)
            try:
                connection.request('GET', route, headers=headers or {})
                response = connection.getresponse()
                return response.status, dict(response.getheaders()), response.read()
            finally:
                connection.close()
        try:
            status, headers, html = request('/')
            self.assertEqual(status, 200)
            self.assertIn(b'/desktop-preferences.js', html)
            self.assertNotIn('unsafe-eval', headers['Content-Security-Policy'])
            self.assertNotIn('unsafe-inline', headers['Content-Security-Policy'])
            self.assertIn(b'dark', request('/desktop-preferences.js')[2])
            state = json.loads(request('/api/state')[2])
            self.assertEqual([s['name'] for s in state['skills']], ['desktop-demo'])
            self.assertEqual(request('/api/state', {'Origin': 'https://example.com'})[0], 403)
            self.assertEqual(request('/api/state', {'Host': 'example.com'})[0], 403)
            self.assertEqual(request('/api/desktop/shutdown')[0], 404)
            self.assertEqual(sha256(target.read_bytes()).hexdigest(), fingerprint)
        finally:
            service.stop()
        self.assertFalse(service.thread.is_alive())
        with self.assertRaises(OSError):
            connection = http.client.HTTPConnection('127.0.0.1', port, timeout=1)
            try:
                connection.request('GET', '/api/health')
            finally:
                connection.close()

    def test_close_cancels_with_draft_and_never_saves_draft_text(self):
        window = Mock()
        window.run_js.return_value = json.dumps({'ready': True, 'dirty': True, 'busy': False,
                                                 'preferences': {'skillpane-theme': 'dark'}})
        window.create_confirmation_dialog.return_value = False
        store = PreferenceStore(self.root)
        guard = CloseGuard(window, store)
        guard.lock.acquire()
        guard.check()
        self.assertFalse(guard.allowed)
        window.destroy.assert_not_called()
        self.assertFalse(store.path.exists())
        window.create_confirmation_dialog.return_value = True
        guard.lock.acquire()
        guard.check()
        self.assertTrue(guard.allowed)
        window.destroy.assert_called_once()
        self.assertEqual(store.path.read_text(), '{"skillpane-theme": "dark"}')

    def test_busy_close_and_unreadable_state_do_not_silently_exit(self):
        window = Mock()
        store = PreferenceStore(self.root)
        guard = CloseGuard(window, store)
        for raw in ('null', 'not json', '{"dirty":false}', json.dumps({
                'ready': True, 'dirty': False, 'busy': True, 'preferences': {}})):
            window.run_js.return_value = raw
            window.create_confirmation_dialog.return_value = False
            guard.lock.acquire()
            guard.check()
            self.assertFalse(guard.allowed)
            window.destroy.assert_not_called()

    @unittest.skipUnless(os.name == 'nt', 'Windows kernel integration')
    def test_windows_single_instance_activates_without_another_service(self):
        from skillpane.desktop_windows import SingleInstance
        name = instance_name(self.root / uuid4().hex)
        window = Mock()
        raised = threading.Event()
        window.show.side_effect = raised.set
        with SingleInstance(name) as first:
            self.assertTrue(first.primary)
            first.watch(window)
            with SingleInstance(name) as second:
                self.assertFalse(second.primary)
                second.activate()
                self.assertTrue(raised.wait(3))
        with SingleInstance(name) as third:
            self.assertTrue(third.primary)


if __name__ == '__main__':
    unittest.main()

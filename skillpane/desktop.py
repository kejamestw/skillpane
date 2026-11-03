"""Optional Windows desktop host; the browser/stdlib entry point stays independent."""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
import os
import queue
from pathlib import Path
import sys
import threading

from .server import AppServer
from .storage import file_digest, strict_json_loads, write_replace

PREFERENCE_VALUES = {
    'skillpane-theme': {'system', 'light', 'dark'},
    'skillpane-text-size': {'standard', 'large', 'extra-large'},
    'skillpane-sidebar-hidden': {'0', '1'},
}
SNAPSHOT_SCRIPT = "JSON.stringify(window.skillpaneDesktopSnapshot ? window.skillpaneDesktopSnapshot() : null)"


def preferences(value):
    if (not isinstance(value, dict) or set(value) - PREFERENCE_VALUES.keys()
            or any(not isinstance(item, str) or item not in PREFERENCE_VALUES[key]
                   for key, item in value.items())):
        raise ValueError('桌面顯示偏好格式錯誤。')
    return dict(value)


def checked_directory(path):
    path = Path(os.path.abspath(path))
    if path.resolve() != path:
        raise ValueError('桌面資料目錄不可經由連結轉向。')
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.resolve() != path or not path.is_dir():
        raise ValueError('桌面資料目錄已變更。')
    return path


def default_directory():
    local = os.environ.get('LOCALAPPDATA')
    if not local or not Path(local).is_absolute():
        raise ValueError('找不到 Windows 使用者資料目錄。')
    return Path(local) / 'Skillpane'


class PreferenceStore:
    """Only three display choices; no skill text, arbitrary JS or browser profile import."""
    def __init__(self, directory):
        self.directory = checked_directory(directory)
        self.path = self.directory / 'desktop-preferences.json'
        self.digest = self._digest()
        self.value = {}
        if self.digest is not None:
            self.value = preferences(strict_json_loads(self.path.read_text(encoding='utf-8')))

    def _digest(self):
        if (self.directory.resolve() != self.directory or self.path.is_symlink()
                or self.path.resolve() != self.path):
            raise ValueError('桌面偏好路徑已變更。')
        if not self.path.exists():
            return None
        if not self.path.is_file() or self.path.stat().st_size > 4096:
            raise ValueError('桌面偏好檔案大小或格式異常；原檔已保留。')
        return file_digest(self.path)

    def check(self):
        if self._digest() != self.digest:
            raise ValueError('桌面偏好被其他程式修改；原檔已保留。')

    def save(self, value):
        value = preferences(value)
        self.check()
        if value == self.value:
            return
        content = json.dumps(value, ensure_ascii=True, sort_keys=True).encode('utf-8')
        self.digest = write_replace(self.directory, 'desktop-preferences', content, self.path, check=self.check)
        self.value = value


class DesktopServer(AppServer):
    # Wait for in-flight requests during normal exit, including atomic saves.
    daemon_threads = False

    def __init__(self, *, home, directory, display):
        super().__init__(port=0, home=home, state_dir=directory)
        # An external, same-origin script runs before the existing module. CSP stays intact.
        script = ('for (const [key, value] of Object.entries('
                  + json.dumps(preferences(display), ensure_ascii=True)
                  + ')) localStorage.setItem(key, value);').encode('utf-8')
        html, mime = self.assets['/']
        marker = b'<script type="module" src="/app.js"></script>'
        if html.count(marker) != 1:
            self.server_close()
            raise ValueError('桌面啟動頁面不符合預期。')
        html = html.replace('本機 .data 目錄'.encode(), '本機桌面資料目錄'.encode()).replace('這個瀏覽器會記住設定。'.encode(), '正常關閉桌面視窗時會記住設定。'.encode())
        self.assets['/'] = (html.replace(marker, b'<script src="/desktop-preferences.js"></script>\n' + marker), mime)
        self.assets['/desktop-preferences.js'] = (script, 'text/javascript; charset=utf-8')


class DesktopService:
    def __init__(self, server):
        self.server = server
        self.thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': 0.1}, daemon=True)

    def start(self):
        self.thread.start()

    def stop(self):
        if self.thread.is_alive():
            self.server.shutdown()
            self.thread.join(timeout=5)
        self.server.server_close()


class CloseGuard:
    """Cancel the native close first: never wait for JS on the GUI thread."""
    def __init__(self, window, store):
        self.window, self.store = window, store
        self.allowed = False
        self.lock = threading.Lock()

    def closing(self):
        if self.allowed or getattr(self.window, '_skillpane_guard_failed', False) is True:
            return True
        if self.lock.acquire(blocking=False):
            threading.Thread(target=self.check, daemon=True).start()
        return False

    def check(self):
        try:
            snapshot = None
            result = queue.Queue(maxsize=1)
            def read_snapshot():
                try:
                    result.put(self.window.run_js(SNAPSHOT_SCRIPT))
                except Exception:
                    result.put(None)
            threading.Thread(target=read_snapshot, daemon=True).start()
            try:
                snapshot = strict_json_loads(result.get(timeout=3))
                if (not isinstance(snapshot, dict) or set(snapshot) != {'ready', 'dirty', 'busy', 'preferences'}
                        or any(type(snapshot[key]) is not bool for key in ('ready', 'dirty', 'busy'))):
                    snapshot = None
            except (ValueError, TypeError, RuntimeError, queue.Empty):
                pass
            if snapshot and snapshot['busy']:
                self.window.create_confirmation_dialog('請稍後再關閉', '操作仍在進行中。請等候儲存或匯入完成，再關閉 Skillpane。')
                return
            if not snapshot or not snapshot['ready'] or snapshot['dirty']:
                if not self.window.create_confirmation_dialog('關閉 Skillpane？', '可能有尚未儲存的內容。關閉後不會保留草稿，確定要離開嗎？'):
                    return
            if snapshot:
                try:
                    self.store.save(snapshot['preferences'])
                except (ValueError, OSError):
                    if not self.window.create_confirmation_dialog('無法儲存顯示偏好', '這次的字級、主題或側欄偏好無法儲存。仍要離開嗎？'):
                        return
            self.allowed = True
            self.window.destroy()
        finally:
            self.lock.release()


def instance_name(directory):
    return 'Skillpane.Desktop.' + sha256(os.path.normcase(str(Path(directory).resolve())).encode('utf-8')).hexdigest()[:32]


def run(*, directory=None, home=None):
    if sys.platform != 'win32':
        raise RuntimeError('桌面原型目前僅支援 Windows；其他系統請使用瀏覽器版。')
    from .desktop_windows import SingleInstance, attach_native_guards
    root = checked_directory(default_directory() if directory is None else directory)
    with SingleInstance(instance_name(root)) as instance:
        if not instance.primary:
            instance.activate()
            return
        import webview
        store = PreferenceStore(root)
        state = checked_directory(root / 'data')
        profile = checked_directory(root / 'webview')
        server = DesktopServer(home=Path.home() if home is None else home, directory=state, display=store.value)
        service = DesktopService(server)
        try:
            webview.settings.update(ALLOW_DOWNLOADS=True, ALLOW_FILE_URLS=False,
                                    OPEN_EXTERNAL_LINKS_IN_BROWSER=False, IGNORE_SSL_ERRORS=False,
                                    OPEN_DEVTOOLS_IN_DEBUG=False, REMOTE_DEBUGGING_PORT=None)
            window = webview.create_window('Skillpane', server.origin + '/', width=1280, height=820,
                                           min_size=(720, 480), text_select=True, zoomable=True,
                                           background_color='#f5f6f8')
            window.events.initialized += lambda renderer: renderer == 'edgechromium'
            def install_guards():
                try:
                    attach_native_guards(window, server.origin)
                except Exception:
                    window._skillpane_guard_failed = True
                    window.native.Close()
            window.events.before_show += install_guards
            guard = CloseGuard(window, store)
            window.events.closing += guard.closing
            service.start()
            webview.start(func=lambda: instance.watch(window), gui='edgechromium', debug=False,
                          private_mode=False, storage_path=str(profile), http_server=False,
                          icon=str(Path(__file__).resolve().parent.parent / ('desktop-assets/skillpane.ico' if getattr(sys, 'frozen', False) else 'assets/brand/skillpane.ico')),
                          localization={'global.quitConfirmation': '確定要關閉 Skillpane？',
                                        'windows.fileFilter.allFiles': '所有檔案'})
            if getattr(window, '_skillpane_guard_failed', False):
                raise RuntimeError('Desktop native guards failed.')
        finally:
            service.stop()


def main():
    parser = argparse.ArgumentParser(description='Skillpane Windows 桌面原型')
    parser.parse_args()
    try:
        run()
        return 0
    except Exception as error:
        # No paths, skill text, credentials or arbitrary exception messages in dialogs/logs.
        message = ('Skillpane 無法啟動。請確認已安裝 Microsoft WebView2 Runtime 與 .NET Framework 4.6.2 以上版本，'
                   '且使用者資料目錄可讀寫。瀏覽器版仍可使用 Open-Skillpane.cmd 啟動。')
        if sys.stderr is not None:
            print(f'Skillpane desktop failed: {type(error).__name__}', file=sys.stderr)
        if sys.platform == 'win32':
            import ctypes
            ctypes.windll.user32.MessageBoxW(None, message, 'Skillpane', 0x10)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())

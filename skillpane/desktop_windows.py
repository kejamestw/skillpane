"""Windows-only native integration. Imports no UI or third-party modules at import."""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import threading
import time
from urllib.parse import urlsplit


class SingleInstance:
    """Session-local named mutex/event; activation carries no commands or data."""
    def __init__(self, name):
        self.kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        for name_, args, result in (
            ('CreateMutexW', [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR], wintypes.HANDLE),
            ('CreateEventW', [wintypes.LPVOID, wintypes.BOOL, wintypes.BOOL, wintypes.LPCWSTR], wintypes.HANDLE),
            ('OpenEventW', [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR], wintypes.HANDLE),
            ('SetEvent', [wintypes.HANDLE], wintypes.BOOL),
            ('WaitForSingleObject', [wintypes.HANDLE, wintypes.DWORD], wintypes.DWORD),
            ('ReleaseMutex', [wintypes.HANDLE], wintypes.BOOL),
            ('CloseHandle', [wintypes.HANDLE], wintypes.BOOL),
        ):
            function = getattr(self.kernel, name_)
            function.argtypes, function.restype = args, result
        self.mutex = self.kernel.CreateMutexW(None, True, 'Local\\' + name)
        self.primary = ctypes.get_last_error() != 183
        self.event = None
        self.name = 'Local\\' + name + '.Activate'
        self.stop = threading.Event()
        self.worker = None
        if not self.mutex:
            raise OSError('Cannot acquire desktop mutex.')

    def __enter__(self):
        if self.primary:
            self.event = self.kernel.CreateEventW(None, False, False, self.name)
            if not self.event:
                self.__exit__(None, None, None)
                raise OSError('Cannot create desktop activation event.')
        return self

    def activate(self):
        for _ in range(30):
            handle = self.kernel.OpenEventW(0x0002, False, self.name)
            if handle:
                try:
                    if not self.kernel.SetEvent(handle):
                        raise OSError('Cannot activate desktop window.')
                    return
                finally:
                    self.kernel.CloseHandle(handle)
            time.sleep(0.1)
        raise RuntimeError('Desktop is starting or stopping; retry shortly.')

    def watch(self, window):
        def watch():
            while not self.stop.is_set():
                result = self.kernel.WaitForSingleObject(self.event, 200)
                if result == 0 and not self.stop.is_set():
                    window.restore()
                    window.show()
                elif result not in (0, 258):
                    return
        self.worker = threading.Thread(target=watch, daemon=True)
        self.worker.start()

    def __exit__(self, *_):
        self.stop.set()
        if self.worker:
            self.worker.join(timeout=2)
        if self.event:
            self.kernel.CloseHandle(self.event)
            self.event = None
        if self.mutex:
            if self.primary:
                self.kernel.ReleaseMutex(self.mutex)
            self.kernel.CloseHandle(self.mutex)
            self.mutex = None


def navigation_allowed(uri, origin):
    # Main-frame navigation stays on the app entry point (hash changes are fine).
    try:
        url = urlsplit(uri)
        return (url.scheme + '://' + url.netloc == origin and url.path in ('', '/')
                and not url.query and not url.username and not url.password)
    except ValueError:
        return False


def download_allowed(uri, origin, mime):
    return (mime == 'application/json' and isinstance(uri, str)
            and uri.startswith('blob:' + origin + '/') and '\x00' not in uri)


def attach_native_guards(window, origin):
    """Hook the actual WebView2 control before its first local navigation."""
    from Microsoft.Web.WebView2.Core import CoreWebView2PermissionState
    browser = window.native.browser
    view = browser.webview

    def navigating(sender, args):
        if not navigation_allowed(str(args.Uri), origin):
            args.Cancel = True

    def deny_popup(sender, args):
        args.Handled = True

    def deny_permission(sender, args):
        args.State = CoreWebView2PermissionState.Deny

    def downloading(sender, args):
        operation = args.DownloadOperation
        if not download_allowed(str(operation.Uri), origin, str(operation.MimeType)):
            args.Cancel = True
            return
        browser.on_download_starting(sender, args)

    def configure_ready(sender, args):
        if not args.IsSuccess:
            return
        core = view.CoreWebView2
        # No Python API is exposed and WebMessage/native host objects are disabled.
        core.Settings.AreHostObjectsAllowed = False
        core.Settings.IsWebMessageEnabled = False
        core.Settings.IsGeneralAutofillEnabled = False
        core.Settings.IsPasswordAutosaveEnabled = False
        core.NewWindowRequested -= browser.on_new_window_request
        core.NewWindowRequested += deny_popup
        core.PermissionRequested += deny_permission
        core.DownloadStarting -= browser.on_download_starting
        core.DownloadStarting += downloading
        window._skillpane_guards_ready = True

    def ready(sender, args):
        try:
            configure_ready(sender, args)
        except Exception:
            window._skillpane_guard_failed = True
            window.native.Close()

    view.NavigationStarting += navigating
    view.CoreWebView2InitializationCompleted += ready
    if view.CoreWebView2 is not None:
        from types import SimpleNamespace
        ready(view, SimpleNamespace(IsSuccess=True))
    # Keep Python delegates alive for the native control's lifetime.
    window._skillpane_handlers = (navigating, deny_popup, deny_permission, downloading, ready)

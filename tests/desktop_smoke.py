"""Opt-in real WebView2 integration, using only generated home/data (not UI input)."""
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import webview
from skillpane.desktop import run


def main():
    base = ROOT / '.runtime' / ('desktop-integration-' + uuid4().hex)
    home = base / 'synthetic-home'
    profile = base / 'desktop-profile'
    files = []
    for n in range(24):
        target = home / '.agents/skills' / f'desktop-demo-{n:02}' / 'SKILL.md'
        target.parent.mkdir(parents=True)
        target.write_text(f'---\nname: desktop-demo-{n:02}\ndescription: 桌面原型合成技能 {n}。\n---\n# 合成資料\n', encoding='utf-8')
        files.append(target)
    fingerprints = [sha256(path.read_bytes()).hexdigest() for path in files]
    result = {'checks': [], 'errors': []}
    original_start = webview.start

    def start(**kwargs):
        activate = kwargs.pop('func')
        window = webview.windows[0]

        def read(expression):
            return json.loads(window.run_js('JSON.stringify(' + expression + ')'))

        def wait(expression, predicate=lambda value: bool(value), timeout=15):
            end = time.monotonic() + timeout
            while time.monotonic() < end:
                value = read(expression)
                if predicate(value):
                    return value
                time.sleep(0.1)
            raise AssertionError('WebView2 integration condition timed out.')

        def check(name, condition):
            if not condition:
                raise AssertionError(name)
            result['checks'].append(name)
            print(json.dumps({'check': name, 'passed': True}), flush=True)

        def tests():
            activate()
            saved_dialog = window.create_confirmation_dialog
            try:
                check('native-document-loaded', window.events.loaded.wait(30))
                snapshot = wait('window.skillpaneDesktopSnapshot ? window.skillpaneDesktopSnapshot() : null',
                                lambda v: bool(v and v['ready'] and not v['busy']))
                check('real-webview2-native-guards-installed', bool(getattr(window, '_skillpane_guards_ready', False)))
                check('only-synthetic-skills', read("Array.from(document.querySelectorAll('.skill-row')).every(row=>row.textContent.includes('desktop-demo-'))")
                      and read("document.querySelectorAll('.skill-row').length") == 24)
                check('no-native-python-api', read("!window.pywebview || !window.pywebview.api || Object.keys(window.pywebview.api).length===0"))
                check('brand-image-loaded-with-original-csp', wait("document.querySelector('.brand img').complete && document.querySelector('.brand img').naturalWidth > 0"))
                # Use the same DOM handlers as the page; these are programmatic, not physical input.
                window.run_js("document.querySelector('#searchInput').value='desktop-demo-12';document.querySelector('#searchInput').dispatchEvent(new Event('input',{bubbles:true}));")
                check('search-one-synthetic-skill', wait("document.querySelectorAll('.skill-row').length", lambda v: v == 1) == 1)
                window.run_js("document.querySelector('#searchInput').value='';document.querySelector('#searchInput').dispatchEvent(new Event('input',{bubbles:true}));")
                wait("document.querySelectorAll('.skill-row').length", lambda v: v == 24)
                window.run_js("document.querySelector('#themeSelect').value='dark';document.querySelector('#themeSelect').dispatchEvent(new Event('change',{bubbles:true}));document.querySelector('#textSizeSelect').value='large';document.querySelector('#textSizeSelect').dispatchEvent(new Event('change',{bubbles:true}));")
                check('theme-and-text-size', read("document.documentElement.dataset.theme==='dark' && document.documentElement.dataset.textSize==='large'"))
                check('note-field-present', read("Boolean(document.querySelector('#noteInput'))"))
                window.run_js("document.querySelector('#noteInput').value='桌面整合測試筆記';document.querySelector('#noteInput').dispatchEvent(new Event('input',{bubbles:true}));")
                check('unsaved-draft-detected', read('window.skillpaneDesktopSnapshot().dirty'))
                asked = threading.Event()
                def cancel(*_):
                    asked.set()
                    return False
                window.create_confirmation_dialog = cancel
                window.destroy()
                check('actual-close-cancelled-for-draft', asked.wait(10))
                check('draft-survives-cancelled-close', read("document.querySelector('#noteInput').value==='桌面整合測試筆記'"))
                window.run_js("document.querySelector('#saveNoteButton').click();")
                wait('window.skillpaneDesktopSnapshot()', lambda v: v['ready'] and not v['dirty'] and not v['busy'])
                check('note-saved-through-same-origin-api', True)
                # A second process must return without creating a second GUI/backend.
                code = "from skillpane.desktop import run;run(directory=" + repr(str(profile)) + ",home=" + repr(str(home)) + ")"
                second = subprocess.run([sys.executable, '-B', '-c', code], cwd=ROOT,
                                        capture_output=True, timeout=20)
                check('second-process-activates-existing-window', second.returncode == 0)
                # A direct native navigation attempt must be cancelled before an external page loads.
                from System import Action
                origin = read('location.origin')
                view = window.native.browser.webview
                view.BeginInvoke(Action(lambda: view.CoreWebView2.Navigate('https://skillpane-test.invalid/')))
                time.sleep(0.3)
                check('external-native-navigation-blocked', read('location.origin') == origin)
                # Capture native switches on the UI thread, without exposing a JS/Python bridge.
                native = {}
                def settings():
                    core = view.CoreWebView2
                    native.update(web_messages=core.Settings.IsWebMessageEnabled,
                                  host_objects=core.Settings.AreHostObjectsAllowed,
                                  devtools=core.Settings.AreDevToolsEnabled)
                view.Invoke(Action(settings))
                check('native-capabilities-disabled', native == {'web_messages': False, 'host_objects': False, 'devtools': False})
                # Real Blob download path, choosing a fixture file instead of a system save dialog.
                downloaded = base / 'synthetic-backup.json'
                browser = window.native.browser
                original_download = browser.on_download_starting
                def download(sender, args):
                    args.ResultFilePath = str(downloaded)
                    args.Handled = True
                browser.on_download_starting = download
                window.run_js("document.querySelector('#openDataSettings').click();")
                wait("Boolean(document.querySelector('#downloadBackup') && !document.querySelector('#downloadBackup').disabled)")
                window.run_js("document.querySelector('#downloadBackup').click();")
                deadline = time.monotonic() + 15
                while time.monotonic() < deadline:
                    try:
                        backup = json.loads(downloaded.read_text(encoding='utf-8'))
                        break
                    except (OSError, ValueError):
                        time.sleep(0.1)
                else:
                    raise AssertionError('Native JSON Blob download did not finish.')
                check('real-native-json-download', downloaded.is_file() and '桌面整合測試筆記' in json.dumps(backup, ensure_ascii=False))
                browser.on_download_starting = original_download
            except Exception as error:
                result['errors'].append(type(error).__name__ + ': ' + str(error))
                print(json.dumps({'integration_failed': result['errors'][-1]}), flush=True)
            finally:
                # All data is owned synthetic content. Allow cleanup even after an assertion fails.
                window.create_confirmation_dialog = lambda *_: True
                try:
                    window.run_js("if(document.querySelector('#noteInput')){document.querySelector('#noteInput').value='';document.querySelector('#noteInput').dispatchEvent(new Event('input',{bubbles:true}));}")
                except Exception:
                    pass
                window.destroy()

        kwargs['func'] = tests
        return original_start(**kwargs)

    webview.start = start
    run(directory=profile, home=home)
    assert fingerprints == [sha256(path.read_bytes()).hexdigest() for path in files]
    result['checks'].append('normal-window-exit-and-skills-unchanged')
    prefs = json.loads((profile / 'desktop-preferences.json').read_text(encoding='utf-8'))
    assert prefs['skillpane-theme'] == 'dark' and prefs['skillpane-text-size'] == 'large'
    result['checks'].append('display-preferences-persisted')
    (base / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'checks': len(result['checks']), 'failures': len(result['errors']), 'fixture': str(base)}), flush=True)
    return bool(result['errors'])


if __name__ == '__main__':
    raise SystemExit(main())

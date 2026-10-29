"""Loopback-only application. The only disk writes are local annotations."""
from __future__ import annotations
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from . import __version__
from .catalog import Catalog
from .storage import Annotations, PromptConflict, strict_json_loads
from .library import Library
from .transfers import Transfers

PROJECT = Path(__file__).resolve().parent.parent
# Both old and new lists can contain 20 prompts. Allow escaped Unicode at the
# existing field limits without removing a bounded request size.
ANNOTATION_REQUEST_LIMIT = 2 * 1024 * 1024
ASSETS = {'/': ('index.html', 'text/html; charset=utf-8'),
          '/app.js': ('app.js', 'text/javascript; charset=utf-8'),
          '/management.js': ('management.js', 'text/javascript; charset=utf-8'),
          '/prompts.js': ('prompts.js', 'text/javascript; charset=utf-8'),
          '/styles.css': ('styles.css', 'text/css; charset=utf-8'),
          '/favicon.svg': ('favicon.svg', 'image/svg+xml')}


class AppServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, port=8766, home=None, state_dir=None, host='127.0.0.1'):
        if host != '127.0.0.1':
            raise ValueError('Skillpane 僅允許 127.0.0.1 本機連線。')
        home = Path.home() if home is None else Path(home)
        directory = PROJECT / '.data' if state_dir is None else Path(state_dir)
        # Refuse annotation storage anywhere inside a skill root.
        from .catalog import roots, within
        if within(directory.resolve(), [p.resolve() for p in roots(home)]):
            raise ValueError('整理資料不可放在技能目錄內。')
        self.catalog = Catalog(home)
        self.annotations = Annotations(directory, recover=True)
        self.library = Library(self.catalog, self.annotations)
        self.transfers = Transfers(self.library)
        super().__init__((host, port), Handler)
        self.origin = f'http://127.0.0.1:{self.server_address[1]}'


class Handler(BaseHTTPRequestHandler):
    server_version = f'Skillpane/{__version__}'

    def setup(self):
        super().setup()
        self.connection.settimeout(20)

    def end_headers(self):
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('X-Frame-Options', 'DENY')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Cross-Origin-Resource-Policy', 'same-origin')
        self.send_header('Content-Security-Policy',
                         "default-src 'none'; script-src 'self'; style-src 'self'; "
                         "connect-src 'self'; img-src 'self' data:; font-src 'self'; "
                         "frame-ancestors 'none'; base-uri 'none'; form-action 'none'; object-src 'none'")
        super().end_headers()

    def trusted(self, write=False):
        hosts = self.headers.get_all('Host', [])
        if hosts != [self.server.origin.removeprefix('http://')]:
            self.json({'error': '拒絕不受信任的 Host。'}, 403)
            return False
        if any(len(self.headers.get_all(header, [])) > 1 for header in ('Origin', 'Sec-Fetch-Site', 'Content-Length', 'Content-Type', 'X-Skillpane-Client')):
            self.json({'error': '拒絕重複的請求標頭。'}, 403)
            return False
        origin = self.headers.get('Origin')
        if origin is not None and origin != self.server.origin:
            self.json({'error': '拒絕跨來源請求。'}, 403)
            return False
        site = self.headers.get('Sec-Fetch-Site')
        if site is not None and site not in {'same-origin', 'none'}:
            self.json({'error': '拒絕跨站請求。'}, 403)
            return False
        if write and (origin != self.server.origin or self.headers.get('X-Skillpane-Client') != '1'
                      or self.headers.get_content_type() != 'application/json'):
            self.json({'error': '整理操作必須由本機面板送出。'}, 403)
            return False
        return True

    def target(self):
        try:
            if not self.path.startswith('/') or self.path.startswith('//'):
                raise ValueError()
            url = urlsplit(self.path)
            if url.scheme or url.netloc or url.fragment:
                raise ValueError()
            return url
        except ValueError:
            self.json({'error': '請求網址格式錯誤。'}, 400)
            return None

    def json(self, value, status=200):
        self.respond(json.dumps(value, ensure_ascii=False).encode('utf-8'), 'application/json; charset=utf-8', status)

    def respond(self, body, content_type, status=200):
        # Drain a bounded request body before closing HTTP/1.0 connections.
        # Windows can otherwise reset the socket before the client sees a 405.
        if not getattr(self, '_body_consumed', False) and not self.headers.get('Transfer-Encoding'):
            try:
                length = int(self.headers.get('Content-Length', '0'))
            except ValueError:
                length = 0
            if 0 < length <= 24000:
                self.rfile.read(length)
            self._body_consumed = True
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if not self.trusted():
            return
        url = self.target()
        if url is None:
            return
        if url.path == '/api/health':
            self.json({'app': 'skillpane', 'version': __version__, 'skill_files_readonly': True})
        elif url.path == '/api/state':
            self.json(self.server.library.snapshot())
        elif url.path in {'/api/backup', '/api/backups', '/api/source', '/api/compare'}:
            try:
                query = parse_qs(url.query)
                if url.path == '/api/backup':
                    result = self.server.transfers.export()
                elif url.path == '/api/backups':
                    result = {'files': self.server.transfers.backups(), 'settings': self.server.annotations.state['settings']}
                elif url.path == '/api/source':
                    result = self.server.library.provenance(query.get('id', [''])[0])
                else:
                    result = self.server.library.comparison(query.get('left', [''])[0], query.get('right', [''])[0])
                self.json(result)
            except KeyError:
                self.json({'error': '找不到指定技能。'}, 404)
            except ValueError as error:
                self.json({'error': str(error)}, 400)
            except (OSError, RuntimeError):
                self.json({'error': '無法讀取這份資料；請檢查本機資料或重新選擇。'}, 400)
        elif url.path == '/api/skill':
            try:
                skill_id = parse_qs(url.query).get('id', [''])[0]
                self.json({'content': self.server.library.content(skill_id)})
            except (KeyError, OSError, ValueError, RuntimeError):
                self.json({'error': '無法讀取技能內容，請重新掃描。'}, 404)
        elif url.path == '/api/export':
            snapshot = self.server.catalog.snapshot()
            # Export metadata only, never skill bodies or absolute source paths.
            for entry in snapshot['skills']:
                entry.pop('path', None)
                entry.pop('aliases', None)
                entry.pop('versions', None)
                entry['invocation'] = {key: {field: value for field, value in setting.items() if field != 'source'}
                                       if isinstance(setting, dict) else setting
                                       for key, setting in entry['invocation'].items()}
            snapshot['scan_scope'].pop('roots', None)
            self.json(snapshot)
        elif url.path in ASSETS:
            name, mime = ASSETS[url.path]
            self.respond((PROJECT / 'web' / name).read_bytes(), mime)
        else:
            self.json({'error': '找不到這個資源。'}, 404)

    def body(self, maximum=24000):
        if self.headers.get('Transfer-Encoding'):
            raise ValueError('不支援分塊請求。')
        lengths = self.headers.get_all('Content-Length', [])
        if len(lengths) != 1 or not lengths[0].isascii() or not lengths[0].isdecimal():
            raise ValueError('請求長度格式錯誤。')
        length = int(lengths[0])
        if not 0 < length <= maximum:
            raise ValueError('請求大小不正確。')
        raw = self.rfile.read(length)
        self._body_consumed = True
        if len(raw) != length:
            raise ValueError('請求內容不完整。')
        payload = strict_json_loads(raw.decode('utf-8'))
        if not isinstance(payload, dict):
            raise ValueError('請求必須是 JSON 物件。')
        return payload

    def do_POST(self):
        if not self.trusted(write=True):
            return
        url = self.target()
        if url is None:
            return
        route = url.path
        actions = {
            '/api/import/preview': self.server.transfers.preview_import,
            '/api/import/apply': self.server.transfers.apply_import,
            '/api/restore/preview': self.server.transfers.preview_restore,
            '/api/relink/preview': self.server.transfers.preview_relink,
            '/api/relink/apply': self.server.transfers.apply_relink,
            '/api/backup/settings': self.server.transfers.settings,
            '/api/backups/cleanup/preview': lambda _: self.server.transfers.preview_cleanup(),
            '/api/backups/cleanup/apply': self.server.transfers.apply_cleanup,
            '/api/comparison': self.server.library.save_comparison,
        }
        if route not in actions and route != '/api/rescan':
            self.json({'error': '技能本體維持唯讀。'}, 405)
            return
        try:
            payload = self.body(4 * 1024 * 1024 + 65536 if route == '/api/import/preview' else 1024 * 1024 if route == '/api/import/apply' else 24000)
            if route == '/api/rescan':
                self.server.catalog.refresh()
                self.server.library.git_cache.clear()
                result = self.server.library.snapshot()
            else:
                result = actions[route](payload)
            self.json(result)
        except KeyError:
            self.json({'error': '找不到指定技能，請重新掃描。'}, 404)
        except ValueError as error:
            self.json({'error': str(error) if not isinstance(error, (json.JSONDecodeError, UnicodeError)) else 'JSON 或文字格式錯誤，未套用資料。'}, 400)
        except (OSError, RuntimeError, TypeError):
            self.json({'error': '操作未完成，請保留現有資料並重新預覽。'}, 400)

    def do_PATCH(self):
        if not self.trusted(write=True):
            return
        url = self.target()
        if url is None:
            return
        if url.path != '/api/annotation':
            self.json({'error': '技能本體維持唯讀。'}, 405)
            return
        skill_id = parse_qs(url.query).get('id', [''])[0]
        if skill_id not in self.server.library.live:
            self.json({'error': '找不到要整理的技能。'}, 404)
            return
        try:
            payload = self.body(ANNOTATION_REQUEST_LIMIT)
            expected = None
            if isinstance(payload, dict) and 'prompts' in payload:
                expected = payload.pop('prompts_base')
                if not isinstance(expected, list):
                    raise ValueError('提示詞版本格式錯誤。')
            self.json(self.server.annotations.update(skill_id, payload, expected_prompts=expected))
        except PromptConflict as error:
            self.json({'error': str(error)}, 409)
        except KeyError:
            self.json({'error': '儲存提示詞時需一併提供目前版本。'}, 400)
        except (ValueError, OSError, UnicodeError, TypeError):
            self.json({'error': '無法儲存整理資料，請檢查欄位與本機資料目錄。'}, 400)

    def deny(self):
        if self.trusted():
            self.json({'error': '技能本體維持唯讀。'}, 405)
        self.close_connection = True

    do_PUT = deny
    do_DELETE = deny
    do_OPTIONS = deny

    def log_message(self, *_):
        pass


def main():
    parser = argparse.ArgumentParser(description='Skillpane 本機技能庫')
    parser.add_argument('--port', type=int, default=8766)
    args = parser.parse_args()
    server = AppServer(port=args.port)
    print(f'Skillpane {__version__} is ready at {server.origin}', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()

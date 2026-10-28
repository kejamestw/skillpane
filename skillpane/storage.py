"""Versioned local organization data. Never writes inside skill folders."""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import shutil
import threading
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

MAX_BYTES = 4 * 1024 * 1024
STATUSES = {'keep', 'review', 'merge', 'archive'}
DECISIONS = {'keep-both', 'consider-merge', 'checked'}
TEXT_LIMITS = {'note': 4000, 'alias': 100, 'summary': 600, 'category': 40,
               'origin_reason': 1000, 'source_url': 2048, 'scope_note': 600}
SOURCES = {'personal', 'managed', 'system', 'plugin', 'unknown'}


def strict_json_loads(text):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('JSON 不可包含重複欄位。')
            result[key] = value
        return result

    def constant(_):
        raise ValueError('JSON 不可包含非有限數值。')

    try:
        return json.loads(text, object_pairs_hook=unique, parse_constant=constant)
    except RecursionError:
        raise ValueError('JSON 巢狀層級過深。') from None


def now():
    return datetime.now(timezone.utc).isoformat()


def clone(value):
    return json.loads(json.dumps(value, ensure_ascii=False))


def file_digest(path):
    digest = sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(65536), b''):
            digest.update(block)
    return digest.hexdigest()


def valid_id(value):
    return isinstance(value, str) and re.fullmatch(r'[a-zA-Z0-9_-]{1,80}', value) is not None


def valid_time(value):
    if not isinstance(value, str) or len(value) > 40:
        return False
    try:
        return datetime.fromisoformat(value.replace('Z', '+00:00')).utcoffset() is not None
    except ValueError:
        return False


def validate_annotation(payload):
    if not isinstance(payload, dict) or set(payload) - (set(TEXT_LIMITS) | {'favorite', 'status', 'tags', 'display_mode', 'modifies_files'}):
        raise ValueError('整理資料包含不支援的欄位。')
    if 'favorite' in payload and type(payload['favorite']) is not bool:
        raise ValueError('收藏狀態格式錯誤。')
    if 'status' in payload and (not isinstance(payload['status'], str) or payload['status'] not in STATUSES):
        raise ValueError('不支援的整理狀態。')
    for field, limit in TEXT_LIMITS.items():
        if field in payload and (not isinstance(payload[field], str) or len(payload[field]) > limit or '\x00' in payload[field]):
            raise ValueError(f'{field} 格式錯誤或超過 {limit} 字。')
    if 'display_mode' in payload and payload['display_mode'] not in ('default', 'original'):
        raise ValueError('不支援的顯示方式。')
    if 'modifies_files' in payload and payload['modifies_files'] not in ('unknown', 'yes', 'no'):
        raise ValueError('是否改檔的選項錯誤。')
    if 'tags' in payload:
        tags = payload['tags']
        if not isinstance(tags, list) or len(tags) > 12 or any(not isinstance(t, str) or not t.strip() or len(t) > 30 or '\x00' in t for t in tags):
            raise ValueError('標籤最多 12 個，每個 1–30 字。')
        if len(set(tags)) != len(tags):
            raise ValueError('標籤不可重複。')
    if payload.get('source_url'):
        try:
            url = urlsplit(payload['source_url'])
            if url.scheme not in {'http', 'https'} or not url.hostname or url.username or url.password:
                raise ValueError()
            if any(re.search(r'token|secret|password|api.?key|authorization', key, re.I) for key in parse_qs(url.query)):
                raise ValueError()
            if any(c.isspace() for c in payload['source_url']):
                raise ValueError()
        except ValueError:
            raise ValueError('來源網址請使用不含帳密或憑證參數的 http／https 網址。') from None
    return clone(payload)


def empty_state():
    return {'format': 'skillpane-state', 'version': 2, 'revision': uuid4().hex,
            'annotations': {}, 'identities': {}, 'comparisons': {}, 'settings': {'keep_last': None}}


def validate_identity(identity, *, portable=False):
    required = {'name', 'source', 'plugin', 'sha256', 'first_seen_at'}
    optional = {'retired', 'catalog_key', 'path_hint', 'legacy_ids'} if not portable else {'retired'}
    if not isinstance(identity, dict) or not required <= identity.keys() or set(identity) - (required | optional):
        raise ValueError('技能識別資料格式錯誤。')
    if any(not isinstance(identity[k], str) or len(identity[k]) > limit for k, limit in [('name', 200), ('plugin', 200), ('sha256', 64)]):
        raise ValueError('技能識別欄位超過限制。')
    if not isinstance(identity['source'], str) or identity['source'] not in SOURCES or not valid_time(identity['first_seen_at']):
        raise ValueError('技能來源或首次發現時間錯誤。')
    if identity['sha256'] and not re.fullmatch('[0-9a-f]{64}', identity['sha256']):
        raise ValueError('技能內容指紋格式錯誤。')
    if 'retired' in identity and type(identity['retired']) is not bool:
        raise ValueError('技能關聯狀態錯誤。')
    if not portable:
        if 'catalog_key' in identity and not valid_id(identity['catalog_key']):
            raise ValueError('技能對應資料錯誤。')
        if 'path_hint' in identity and (not isinstance(identity['path_hint'], str) or len(identity['path_hint']) > 4096):
            raise ValueError('技能路徑提示錯誤。')
        if 'legacy_ids' in identity and (not isinstance(identity['legacy_ids'], list) or len(identity['legacy_ids']) > 200 or not all(valid_id(v) for v in identity['legacy_ids'])):
            raise ValueError('技能舊識別資料錯誤。')


def validate_comparison(record):
    fields = {'left_id', 'right_id', 'fingerprints', 'decision', 'reason', 'checked_at'}
    if not isinstance(record, dict) or set(record) != fields:
        raise ValueError('比較結論格式錯誤。')
    if not valid_id(record['left_id']) or not valid_id(record['right_id']) or record['left_id'] == record['right_id']:
        raise ValueError('比較技能識別錯誤。')
    if not isinstance(record['decision'], str) or record['decision'] not in DECISIONS or not isinstance(record['reason'], str) or len(record['reason']) > 2000 or not valid_time(record['checked_at']):
        raise ValueError('比較結論內容錯誤。')
    if not isinstance(record['fingerprints'], dict) or set(record['fingerprints']) != {record['left_id'], record['right_id']} or any(not isinstance(v, str) or not re.fullmatch('[0-9a-f]{64}', v) for v in record['fingerprints'].values()):
        raise ValueError('比較內容指紋錯誤。')


def validate_state(state):
    if not isinstance(state, dict) or set(state) != set(empty_state()) or state['format'] != 'skillpane-state' or type(state['version']) is not int or state['version'] != 2 or not valid_id(state['revision']):
        raise ValueError('本機整理資料版本或格式錯誤。')
    for field in ['annotations', 'identities', 'comparisons']:
        if not isinstance(state[field], dict) or len(state[field]) > 10000:
            raise ValueError('本機整理資料筆數異常。')
    for key, value in state['annotations'].items():
        if not valid_id(key):
            raise ValueError('技能識別格式錯誤。')
        validate_annotation(value)
    for key, value in state['identities'].items():
        if not valid_id(key):
            raise ValueError('技能識別格式錯誤。')
        validate_identity(value)
    for key, value in state['comparisons'].items():
        validate_comparison(value)
        if key != pair_key(value['left_id'], value['right_id']):
            raise ValueError('比較結論識別錯誤。')
    if not isinstance(state['settings'], dict) or set(state['settings']) != {'keep_last'}:
        raise ValueError('備份設定格式錯誤。')
    validate_keep(state['settings']['keep_last'])


def validate_keep(value):
    if value is not None and (type(value) is not int or not 1 <= value <= 1000):
        raise ValueError('備份保留數量須為 1–1000，或保留全部。')


def pair_key(left, right):
    return ':'.join(sorted([left, right]))


class Annotations:
    def __init__(self, directory, *, recover=False):
        self.directory = Path(directory).resolve()
        self.path = self.directory / 'annotations.json'
        self.lock = threading.RLock()
        self.state = empty_state()
        self.error = None
        self.legacy = False
        self.disk_digest = None
        if self.path.exists() or self.path.is_symlink():
            try:
                if self.path.is_symlink():
                    raise ValueError('本機整理資料的路徑或大小異常。')
                self.disk_digest = file_digest(self.path)
                if self.path.stat().st_size > MAX_BYTES:
                    raise ValueError('本機整理資料超過大小上限。')
                value = strict_json_loads(self.path.read_text(encoding='utf-8'))
                if isinstance(value, dict) and value.get('format') == 'skillpane-state':
                    validate_state(value)
                    self.state = value
                elif isinstance(value, dict):
                    for key, item in value.items():
                        if not valid_id(key):
                            raise ValueError('舊版技能識別格式錯誤。')
                        validate_annotation(item)
                    self.state['annotations'] = value
                    self.legacy = True
                else:
                    raise ValueError('本機整理資料格式錯誤。')
            except (ValueError, UnicodeError, OSError, TypeError, RecursionError):
                if not recover:
                    raise ValueError('本機整理資料損壞；原檔已保留。') from None
                self.error = '本機整理資料無法讀取；原檔已保留。可查閱技能，請從「資料與備份」預覽還原或匯入備份。'

    def snapshot(self):
        with self.lock:
            return clone(self.state['annotations'])

    def safe_directory(self, child=None):
        directory = self.directory if child is None else self.directory / child
        if directory.resolve() != directory:
            raise ValueError('本機資料目錄已變更，停止操作。')
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        if directory.resolve() != directory:
            raise ValueError('本機資料目錄已變更，停止操作。')
        if os.name == 'posix':
            directory.chmod(0o700)
        return directory

    def commit(self, next_state, *, recovery=False):
        with self.lock:
            if self.error and not recovery:
                raise ValueError(self.error)
            next_state = clone(next_state)
            next_state['revision'] = uuid4().hex
            validate_state(next_state)
            content = json.dumps(next_state, ensure_ascii=False, indent=2)
            if len(content.encode('utf-8')) > MAX_BYTES:
                raise ValueError('整理資料超過 4 MiB 上限，原資料維持不變。')
            self.safe_directory()
            self.ensure_unchanged()
            if self.path.exists():
                directory = self.safe_directory('backups')
                backup = directory / f'{datetime.now(timezone.utc):%Y%m%dT%H%M%S}-{uuid4().hex}.json'
                shutil.copy2(self.path, backup)
                if os.name == 'posix':
                    backup.chmod(0o600)
            temporary = self.directory / f'annotations-{uuid4().hex}.tmp'
            descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_BINARY', 0), 0o600)
            with os.fdopen(descriptor, 'w', encoding='utf-8', newline='\n') as stream:
                stream.write(content)
                stream.flush()
            temporary.replace(self.path)
            self.state = next_state
            self.disk_digest = sha256(content.encode('utf-8')).hexdigest()
            self.error, self.legacy = None, False

    def ensure_unchanged(self):
        """Also guard destructive operations that do not commit annotations."""
        with self.lock:
            if self.directory.resolve() != self.directory or self.path.is_symlink():
                raise ValueError('本機整理資料路徑已變更，停止操作。')
            current_digest = file_digest(self.path) if self.path.exists() else None
            if current_digest != self.disk_digest:
                raise ValueError('整理資料已由其他程序變更，請重新啟動面板後再操作。')

    def update(self, skill_id, payload):
        validate_annotation(payload)
        if not valid_id(skill_id):
            raise ValueError('技能識別格式錯誤。')
        with self.lock:
            next_state = clone(self.state)
            next_state['annotations'][skill_id] = {**next_state['annotations'].get(skill_id, {}), **payload}
            self.commit(next_state)
            return clone(next_state['annotations'][skill_id])

"""Bounded local scan observations, without skill bodies or source paths."""
from hashlib import sha256
import json
import os
import re
import threading
from uuid import uuid4

from .storage import clone, now, strict_json_loads, valid_id, valid_time

MAX_EVENTS = 300
MAX_SKILLS = 5000
MAX_BYTES = 8 * 1024 * 1024
FIELDS = {'name', 'source', 'plugin', 'version', 'sha256', 'cache'}
KINDS = {'added', 'changed', 'missing'}
ERROR = '變更紀錄無法更新，原檔已保留；技能仍可瀏覽。請檢查本機資料目錄並重新啟動。'


def observation(skill):
    versions = sorted((v['version'], v['sha256']) for v in skill['versions'])
    return {**{key: skill[key] for key in ('name', 'source', 'plugin', 'sha256')},
            'version': skill['version'][:80],
            'cache': sha256(json.dumps(versions, ensure_ascii=False).encode()).hexdigest()
                     if skill['source'] == 'plugin' else ''}


def validate_observation(value):
    if not isinstance(value, dict) or set(value) != FIELDS:
        raise ValueError('Invalid observation.')
    for field, limit in [('name', 200), ('plugin', 200), ('version', 80)]:
        if not isinstance(value[field], str) or len(value[field]) > limit or '\x00' in value[field]:
            raise ValueError('Invalid observation text.')
    if value['source'] not in ('personal', 'managed', 'system', 'plugin'):
        raise ValueError('Invalid source.')
    if not isinstance(value['sha256'], str) or not re.fullmatch('[0-9a-f]{64}', value['sha256']):
        raise ValueError('Invalid fingerprint.')
    if not isinstance(value['cache'], str) or (value['cache'] != '' and not re.fullmatch('[0-9a-f]{64}', value['cache'])):
        raise ValueError('Invalid cache fingerprint.')


def validate_history(value):
    if (not isinstance(value, dict) or set(value) != {'format', 'version', 'baseline_at', 'observations', 'events'}
            or value['format'] != 'skillpane-scan-history' or type(value['version']) is not int
            or value['version'] != 1 or not valid_time(value['baseline_at'])):
        raise ValueError('Invalid scan history.')
    observations, events = value['observations'], value['events']
    if not isinstance(observations, dict) or len(observations) > MAX_SKILLS:
        raise ValueError('Too many observations.')
    for key, item in observations.items():
        if not valid_id(key):
            raise ValueError('Invalid skill id.')
        validate_observation(item)
    if not isinstance(events, list) or len(events) > MAX_EVENTS:
        raise ValueError('Too many scan events.')
    ids = set()
    for event in events:
        if (not isinstance(event, dict) or set(event) != {'id', 'kind', 'skill_id', 'observed_at', 'before', 'after'}
                or not valid_id(event['id']) or event['id'] in ids or not valid_id(event['skill_id'])
                or event['kind'] not in KINDS or not valid_time(event['observed_at'])):
            raise ValueError('Invalid scan event.')
        ids.add(event['id'])
        before, after = event['before'], event['after']
        for item in (before, after):
            if item is not None:
                validate_observation(item)
        if ((event['kind'] == 'added' and (before is not None or after is None))
                or (event['kind'] == 'missing' and (before is None or after is not None))
                or (event['kind'] == 'changed' and (before is None or after is None or before == after))):
            raise ValueError('Invalid scan transition.')


class ScanHistory:
    def __init__(self, store):
        self.store = store
        self.path = store.directory / 'scan-history.json'
        self.lock = threading.RLock()
        self.state, self.disk_digest, self.error = None, None, None
        self.checked_at, self.skipped = None, 0
        try:
            raw = self.read_disk()
            if raw is not None:
                value = strict_json_loads(raw.decode('utf-8'))
                validate_history(value)
                self.state = value
                self.disk_digest = sha256(raw).hexdigest()
        except (ValueError, OSError, UnicodeError, RuntimeError, TypeError, RecursionError):
            self.error = ERROR

    def read_disk(self):
        if self.store.directory.resolve() != self.store.directory or self.path.is_symlink():
            raise ValueError('Scan history path changed.')
        if not self.path.exists():
            return None
        if not self.path.is_file() or self.path.stat().st_size > MAX_BYTES:
            raise ValueError('Scan history is too large.')
        with self.path.open('rb') as stream:
            raw = stream.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            raise ValueError('Scan history is too large.')
        return raw

    def ensure_unchanged(self):
        raw = self.read_disk()
        if (sha256(raw).hexdigest() if raw is not None else None) != self.disk_digest:
            raise ValueError('Scan history was externally modified.')

    def commit(self, value):
        validate_history(value)
        raw = json.dumps(value, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
        if len(raw) > MAX_BYTES:
            raise ValueError('Scan history is too large.')
        self.store.safe_directory()
        self.ensure_unchanged()
        temporary = self.store.directory / ('scan-history-' + uuid4().hex + '.tmp')
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_BINARY', 0), 0o600)
        with os.fdopen(descriptor, 'wb') as stream:
            stream.write(raw)
            stream.flush()
        self.ensure_unchanged()
        temporary.replace(self.path)
        self.state, self.disk_digest = value, sha256(raw).hexdigest()

    def observe(self, skills, *, skipped=0):
        with self.lock:
            self.checked_at, self.skipped = now(), skipped
            if self.error:
                return
            try:
                self.ensure_unchanged()
                current = {skill['id']: observation(skill) for skill in skills}
                if len(current) > MAX_SKILLS:
                    raise ValueError('Too many observations.')
                if self.state is None:
                    self.commit({'format': 'skillpane-scan-history', 'version': 1,
                                 'baseline_at': self.checked_at, 'observations': current, 'events': []})
                    return
                previous = self.state['observations']
                events = []
                for key, after in current.items():
                    before = previous.get(key)
                    if before != after:
                        events.append({'id': uuid4().hex, 'kind': 'added' if before is None else 'changed',
                                       'skill_id': key, 'observed_at': self.checked_at, 'before': before, 'after': after})
                if skipped:
                    # A failed read is not evidence of absence. Keep unseen
                    # observations until a scan with no skipped entries.
                    current = {**previous, **current}
                else:
                    for key in sorted(previous.keys() - current.keys()):
                        events.append({'id': uuid4().hex, 'kind': 'missing', 'skill_id': key,
                                       'observed_at': self.checked_at, 'before': previous[key], 'after': None})
                if current != previous:
                    self.commit({**self.state, 'observations': current,
                                 'events': [*self.state['events'], *events][-MAX_EVENTS:]})
            except (ValueError, OSError, UnicodeError, RuntimeError, TypeError):
                self.error = ERROR

    def snapshot(self):
        with self.lock:
            return {'baseline_at': self.state['baseline_at'] if self.state else None,
                    'checked_at': self.checked_at, 'limit': MAX_EVENTS, 'max_skills': MAX_SKILLS,
                    'events': clone(list(reversed(self.state['events']))) if self.state else [],
                    'skipped': self.skipped, 'error': self.error}

"""Previewed, revision-checked organization transfers. No skill file writes."""
from datetime import datetime, timezone
from hashlib import sha256
import json
import re
import time
from uuid import uuid4

from .library import signature
from .storage import (MAX_BYTES, clone, now, pair_key, validate_annotation,
                      validate_comparison, validate_identity, validate_keep,
                      validate_state, valid_id, valid_time)


def portable_identity(identity):
    return {key: value for key, value in identity.items() if key in {'name', 'source', 'plugin', 'sha256', 'first_seen_at', 'retired'}}


def validate_backup(value):
    if not isinstance(value, dict) or set(value) != {'format', 'version', 'exported_at', 'records', 'comparisons', 'settings'} or value['format'] != 'skillpane-backup' or type(value['version']) is not int or value['version'] != 2 or not valid_time(value['exported_at']):
        raise ValueError('請選擇 Skillpane 第 2 版整理資料備份；技能清單 JSON 不能當作整理資料還原。')
    if not isinstance(value['records'], list) or len(value['records']) > 10000 or not isinstance(value['comparisons'], list) or len(value['comparisons']) > 10000:
        raise ValueError('備份筆數或格式錯誤。')
    ids = set()
    for record in value['records']:
        if not isinstance(record, dict) or set(record) != {'id', 'identity', 'annotation'} or not valid_id(record['id']) or record['id'] in ids:
            raise ValueError('備份包含重複或錯誤的技能識別。')
        ids.add(record['id'])
        validate_identity(record['identity'], portable=True)
        validate_annotation(record['annotation'])
    pairs = set()
    for record in value['comparisons']:
        validate_comparison(record)
        key = pair_key(record['left_id'], record['right_id'])
        if key in pairs or not {record['left_id'], record['right_id']} <= ids:
            raise ValueError('備份比較結論缺少技能或重複。')
        pairs.add(key)
    if not isinstance(value['settings'], dict) or set(value['settings']) != {'keep_last'}:
        raise ValueError('備份保留設定格式錯誤。')
    validate_keep(value['settings']['keep_last'])
    if len(json.dumps(value, ensure_ascii=False).encode()) > MAX_BYTES:
        raise ValueError('備份超過 4 MiB。')
    return clone(value)


class Transfers:
    def __init__(self, library):
        self.library, self.store = library, library.store
        self.previews = {}

    def _token(self, kind, payload):
        self.previews = {k: v for k, v in self.previews.items() if v['expires'] > time.monotonic()}
        while len(self.previews) >= 8:
            self.previews.pop(next(iter(self.previews)))
        token = uuid4().hex
        self.previews[token] = {'kind': kind, 'payload': payload, 'revision': self.store.state['revision'], 'expires': time.monotonic() + 600}
        return token

    def _take(self, token, kind):
        preview = self.previews.get(token) if isinstance(token, str) else None
        if not preview or preview['kind'] != kind or preview['expires'] < time.monotonic():
            raise ValueError('預覽已失效，請重新預覽。')
        if preview['revision'] != self.store.state['revision']:
            raise ValueError('資料已變更，請重新預覽後再套用。')
        return preview['payload']

    def export(self, state=None):
        with self.store.lock:
            if state is None and self.store.error:
                raise ValueError(self.store.error)
            state = self.store.state if state is None else state
            records = []
            for key in sorted(set(state['identities']) | set(state['annotations'])):
                identity = state['identities'].get(key, {'name': '未識別技能 ' + key[:8], 'source': 'unknown', 'plugin': '', 'sha256': '', 'first_seen_at': now()})
                records.append({'id': key, 'identity': portable_identity(identity), 'annotation': clone(state['annotations'].get(key, {}))})
            value = {'format': 'skillpane-backup', 'version': 2, 'exported_at': now(), 'records': records,
                     'comparisons': list(clone(state['comparisons']).values()), 'settings': clone(state['settings'])}
            return validate_backup(value)

    def preview_import(self, value):
        value = validate_backup(value)
        with self.store.lock:
            identities = self.store.state['identities']
            counts = {}
            for record in value['records']:
                if record['identity'].get('retired'):
                    continue
                sig = signature(record['identity'])
                counts[sig] = counts.get(sig, 0) + 1
            rows, used = [], set()
            for record in value['records']:
                key, incoming = record['id'], record['identity']
                target, basis = None, '未找到唯一對應，可保留為未關聯資料'
                candidates = [k for k, item in identities.items() if not item.get('retired') and item['source'] == incoming['source'] and item['plugin'] == incoming['plugin'] and
                              (bool(incoming['sha256']) and item['sha256'] == incoming['sha256'] or item['name'] == incoming['name'])]
                if incoming.get('retired') and key not in identities:
                    candidates = []
                    basis = '保留歷史關聯紀錄，不自動接到目前技能'
                elif key in identities and all(identities[key][field] == incoming[field] for field in ('source', 'plugin')):
                    target, basis = key, '穩定識別相同'
                else:
                    legacy = [k for k, item in identities.items() if key in item.get('legacy_ids', []) and not item.get('retired')]
                    exact = [k for k in self.library.live if signature(identities[k]) == signature(incoming) and incoming['sha256']]
                    if len(legacy) == 1:
                        target, basis = legacy[0], '舊版識別相同'
                    elif len(exact) == 1 and counts[signature(incoming)] == 1:
                        target, basis = exact[0], '來源與內容唯一對應'
                if target in used:
                    target, basis = None, '多筆備份可能對應同一技能，請手動選擇'
                if target:
                    used.add(target)
                current = self.store.state['annotations'].get(target, {})
                conflicts = [field for field, val in record['annotation'].items() if field in current and current[field] != val]
                rows.append({'id': key, 'name': incoming['name'], 'source': incoming['source'], 'basis': basis,
                             'target': target or ('' if candidates else 'orphan'), 'candidates': candidates,
                             'incoming': record['annotation'], 'current': clone(current), 'conflicts': conflicts})
            token = self._token('import', value)
            targets = [{'id': k, 'name': item['name'] + ('（歷史關聯）' if item.get('retired') else ''), 'source': item['source'], 'live': k in self.library.live}
                       for k, item in identities.items()]
            return {'token': token, 'rows': rows, 'targets': targets, 'comparisons': len(value['comparisons']), 'settings': value['settings']}

    def apply_import(self, payload):
        if not isinstance(payload, dict) or set(payload) != {'token', 'choices', 'mode', 'restore_settings'} or payload['mode'] not in ('keep', 'replace') or type(payload['restore_settings']) is not bool or not isinstance(payload['choices'], dict):
            raise ValueError('匯入選項格式錯誤。')
        with self.store.lock:
            value = self._take(payload['token'], 'import')
            if set(payload['choices']) != {record['id'] for record in value['records']}:
                raise ValueError('每筆備份都需要指定處理方式。')
            next_state, mapping, used = clone(self.store.state), {}, set()
            for record in value['records']:
                choice = payload['choices'][record['id']]
                if choice == 'skip':
                    continue
                if choice == 'orphan':
                    target = record['id'] if record['id'] not in next_state['identities'] else uuid4().hex
                    next_state['identities'][target] = clone(record['identity'])
                elif isinstance(choice, str) and choice in next_state['identities'] and (not next_state['identities'][choice].get('retired') or choice == record['id'] and record['identity'].get('retired')):
                    target = choice
                    existing = next_state['identities'][target]
                    incoming_time = record['identity']['first_seen_at']
                    existing['first_seen_at'] = min([existing['first_seen_at'], incoming_time], key=lambda t: datetime.fromisoformat(t.replace('Z', '+00:00')))
                else:
                    raise ValueError('請為有歧義的技能指定對應、保留未關聯，或略過。')
                if target in used:
                    raise ValueError('多筆備份不可同時覆蓋同一個技能。')
                used.add(target)
                mapping[record['id']] = target
                current = next_state['annotations'].get(target, {})
                next_state['annotations'][target] = clone(record['annotation']) if payload['mode'] == 'replace' else {**record['annotation'], **current}
            for record in value['comparisons']:
                if not {record['left_id'], record['right_id']} <= mapping.keys():
                    continue
                incoming = clone(record)
                incoming['left_id'], incoming['right_id'] = mapping[record['left_id']], mapping[record['right_id']]
                incoming['fingerprints'] = {mapping[k]: v for k, v in record['fingerprints'].items()}
                key = pair_key(incoming['left_id'], incoming['right_id'])
                if key not in next_state['comparisons'] or payload['mode'] == 'replace':
                    next_state['comparisons'][key] = incoming
            if payload['restore_settings']:
                next_state['settings'] = clone(value['settings'])
            self.store.commit(next_state, recovery=True)
            self.previews.pop(payload['token'], None)
            return {'imported': len(mapping)}

    def preview_relink(self, payload):
        if not isinstance(payload, dict) or set(payload) != {'from_id', 'to_id'} or not all(isinstance(v, str) for v in payload.values()):
            raise ValueError('重新關聯選項格式錯誤。')
        with self.store.lock:
            source, target = payload['from_id'], payload['to_id']
            identity = self.store.state['identities'].get(source)
            if not identity or identity.get('retired') or source in self.library.live or target not in self.library.live:
                raise ValueError('請選擇一筆未關聯資料與一個目前存在的技能。')
            old = self.store.state['annotations'].get(source, {})
            current = self.store.state['annotations'].get(target, {})
            related = [clone(record) for record in self.store.state['comparisons'].values() if source in record['fingerprints'] or target in record['fingerprints']]
            comparison_conflicts = sum(pair_key(source if record['left_id'] == target else record['left_id'], source if record['right_id'] == target else record['right_id']) in self.store.state['comparisons']
                                       for record in related if target in record['fingerprints'] and source not in record['fingerprints'])
            return {'token': self._token('relink', payload), 'incoming': clone(old), 'current': clone(current),
                    'conflicts': [k for k, v in old.items() if k in current and current[k] != v],
                    'comparison_conflicts': comparison_conflicts, 'comparisons': related,
                    'from_name': identity['name'], 'to_name': self.library.skill(target)['name']}

    def apply_relink(self, payload):
        if not isinstance(payload, dict) or set(payload) != {'token', 'mode'} or payload['mode'] not in ('keep', 'replace'):
            raise ValueError('重新關聯選項錯誤。')
        with self.store.lock:
            value = self._take(payload['token'], 'relink')
            source, target = value['from_id'], value['to_id']
            self.library.skill(target)
            next_state = clone(self.store.state)
            old_identity, new_identity = next_state['identities'][source], next_state['identities'][target]
            first_seen = old_identity['first_seen_at']
            legacy_ids = list(dict.fromkeys([*old_identity.get('legacy_ids', []), *new_identity.get('legacy_ids', [])]))[-200:]
            old_identity.update(clone(new_identity), first_seen_at=first_seen)
            old_identity['legacy_ids'] = legacy_ids
            new_identity['retired'] = True
            old, current = next_state['annotations'].get(source, {}), next_state['annotations'].get(target, {})
            next_state['annotations'][source] = {**current, **old} if payload['mode'] == 'replace' else {**old, **current}
            for record in list(next_state['comparisons'].values()):
                if target not in record['fingerprints'] or source in record['fingerprints']:
                    continue
                rebound = clone(record)
                rebound['left_id'] = source if record['left_id'] == target else record['left_id']
                rebound['right_id'] = source if record['right_id'] == target else record['right_id']
                rebound['fingerprints'] = {source if key == target else key: value for key, value in record['fingerprints'].items()}
                key = pair_key(rebound['left_id'], rebound['right_id'])
                if key not in next_state['comparisons'] or payload['mode'] == 'keep':
                    next_state['comparisons'][key] = rebound
            self.store.commit(next_state)
            self.previews.pop(payload['token'], None)
            self.library.reconcile()
            return {'id': source}

    def backups(self):
        directory = self.store.directory / 'backups'
        if not directory.exists():
            return []
        if directory.resolve() != directory:
            raise ValueError('備份目錄已變更，停止操作。')
        items = []
        for path in directory.iterdir():
            if re.fullmatch(r'\d{8}T\d{6}-[0-9a-f]{32}\.json', path.name) and not path.is_symlink() and path.is_file():
                stat = path.stat()
                items.append({'id': path.name, 'size': stat.st_size,
                              'modified_at': datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat()})
        return sorted(items, key=lambda item: (item['modified_at'], item['id']), reverse=True)

    def backup_path(self, name):
        if not isinstance(name, str) or not re.fullmatch(r'\d{8}T\d{6}-[0-9a-f]{32}\.json', name):
            raise ValueError('找不到指定備份。')
        directory = self.store.directory / 'backups'
        path = directory / name
        if directory.resolve() != directory or path.resolve() != path or not path.is_file():
            raise ValueError('找不到指定備份。')
        return path

    def preview_restore(self, payload):
        if not isinstance(payload, dict) or set(payload) != {'backup_id'}:
            raise ValueError('備份選項錯誤。')
        with self.store.lock:
            path = self.backup_path(payload['backup_id'])
            if path.stat().st_size > MAX_BYTES:
                raise ValueError('備份超過大小上限。')
            try:
                value = json.loads(path.read_text(encoding='utf-8'))
            except (ValueError, UnicodeError):
                raise ValueError('這份備份已損壞，未修改現有資料。') from None
            if isinstance(value, dict) and value.get('format') == 'skillpane-state':
                validate_state(value)
                portable = self.export(value)
            elif isinstance(value, dict) and value.get('format') == 'skillpane-backup':
                portable = value
            elif isinstance(value, dict):
                records = []
                for key, annotation in value.items():
                    validate_annotation(annotation)
                    identity = next((v for k, v in self.store.state['identities'].items() if k == key or key in v.get('legacy_ids', [])),
                                    {'name': '未識別技能 ' + str(key)[:8], 'source': 'unknown', 'plugin': '', 'sha256': '', 'first_seen_at': now()})
                    records.append({'id': key, 'identity': portable_identity(identity), 'annotation': annotation})
                portable = {'format': 'skillpane-backup', 'version': 2, 'exported_at': now(), 'records': records, 'comparisons': [], 'settings': {'keep_last': None}}
            else:
                raise ValueError('備份格式錯誤，未修改現有資料。')
            return self.preview_import(portable)

    def settings(self, payload):
        if not isinstance(payload, dict) or set(payload) != {'keep_last'}:
            raise ValueError('備份保留設定錯誤。')
        validate_keep(payload['keep_last'])
        with self.store.lock:
            next_state = clone(self.store.state)
            next_state['settings'] = clone(payload)
            self.store.commit(next_state)
            return clone(payload)

    def preview_cleanup(self):
        with self.store.lock:
            keep = self.store.state['settings']['keep_last']
            candidates = self.backups()[keep:] if keep is not None else []
            fingerprints = {item['id']: sha256(self.backup_path(item['id']).read_bytes()).hexdigest() for item in candidates}
            return {'token': self._token('cleanup', fingerprints), 'files': candidates, 'keep_last': keep}

    def apply_cleanup(self, payload):
        if not isinstance(payload, dict) or set(payload) != {'token', 'confirm'} or payload['confirm'] is not True:
            raise ValueError('請先預覽並明確確認刪除這些舊備份。')
        with self.store.lock:
            fingerprints = self._take(payload['token'], 'cleanup')
            paths = [self.backup_path(name) for name in fingerprints]
            if any(sha256(path.read_bytes()).hexdigest() != fingerprints[path.name] for path in paths):
                raise ValueError('備份內容已變更，請重新預覽。')
            for path in paths:
                path.unlink()
            self.previews.pop(payload['token'], None)
            return {'removed': len(paths)}

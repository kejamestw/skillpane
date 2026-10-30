"""Stable local identities, read-only comparisons and source evidence."""
from collections import Counter
from datetime import datetime
import difflib
import os
from pathlib import Path
import re
import shutil
import subprocess
from uuid import uuid4

from .catalog import roots
from .storage import clone, file_digest, now, pair_key, validate_comparison
from .changes import ScanHistory


def identity_for(skill):
    return {key: skill[key] for key in ('name', 'source', 'plugin', 'sha256')}


def signature(identity):
    return identity['source'], identity['plugin'], identity['sha256']


class Library:
    def __init__(self, catalog, store):
        self.catalog, self.store = catalog, store
        self.live = {}
        self.raw = {}
        self.git_cache = {}
        self.reconciled, self.catalog_view = None, None
        self.reconcile()
        self.history = ScanHistory(store)
        self.observe_changes()

    def observe_changes(self):
        if self.store.error:
            self.history.error = '整理資料無法讀取，暫停記錄技能變更；原始檔已保留。'
            return
        skills = [{**self.raw[key], 'id': stable_id} for stable_id, key in self.live.items()]
        self.history.observe(skills, skipped=self.catalog.stats['skipped'])

    def rescan(self):
        with self.store.lock:
            self.catalog.refresh()
            self.git_cache.clear()
            self.reconcile()
            self.observe_changes()
            return self.snapshot()

    def reconcile(self):
        """Path continuity first; content moves only when both sides are unique."""
        with self.store.lock:
            # Read before the snapshot: a concurrent refresh only makes the key stale.
            generation = self.catalog.generation
            catalog = self.catalog.snapshot()
            next_state = clone(self.store.state)
            identities, annotations = next_state['identities'], next_state['annotations']
            raw = {s['id']: s for s in catalog['skills']}
            live = {}
            existing = {v.get('catalog_key'): key for key, v in identities.items() if not v.get('retired')}
            for key in raw:
                if key in existing:
                    live[existing[key]] = key
            missing = {key: item for key, item in identities.items()
                       if key not in live and not item.get('retired') and item['sha256']}
            unmatched = [s for s in raw.values() if s['id'] not in live.values()]
            old_counts = Counter(signature(v) for v in missing.values())
            new_counts = Counter(signature(v) for v in unmatched)
            for skill in unmatched:
                sig = signature(skill)
                if old_counts[sig] == new_counts[sig] == 1:
                    stable_id = next(k for k, v in missing.items() if signature(v) == sig)
                else:
                    stable_id = uuid4().hex
                    identities[stable_id] = {**identity_for(skill), 'first_seen_at': now(), 'legacy_ids': []}
                live[stable_id] = skill['id']
            for stable_id, key in live.items():
                skill = raw[key]
                identity = identities[stable_id]
                identity.update(identity_for(skill), catalog_key=key, path_hint=skill['path'])
                identity['legacy_ids'] = list(dict.fromkeys([*identity.get('legacy_ids', []), key]))[-200:]
                if key in annotations and key != stable_id:
                    annotations[stable_id] = {**annotations.pop(key), **annotations.get(stable_id, {})}
            for key in annotations:
                if key not in identities:
                    identities[key] = {'name': '未識別技能 ' + key[:8], 'source': 'unknown', 'plugin': '',
                                       'sha256': '', 'first_seen_at': now(), 'legacy_ids': [key]}
            if next_state != self.store.state or self.store.legacy:
                if self.store.error:
                    next_state['revision'] = uuid4().hex
                    self.store.state = next_state
                else:
                    self.store.commit(next_state)
            self.live, self.raw = live, raw
            self.reconciled, self.catalog_view = (generation, self.store.state['revision']), catalog
            return catalog

    def current(self):
        """Reconcile only after a rescan or a stored-data change; otherwise reuse the result."""
        with self.store.lock:
            if self.reconciled != (self.catalog.generation, self.store.state['revision']):
                return self.reconcile()
            return self.catalog_view

    def snapshot(self):
        with self.store.lock:
            catalog = clone(self.current())
            reverse = {raw: stable for stable, raw in self.live.items()}
            for skill in catalog['skills']:
                skill['id'] = reverse[skill['id']]
                skill['first_seen_at'] = self.store.state['identities'][skill['id']]['first_seen_at']
            for field in ('overlaps', 'related_groups'):
                catalog[field] = [{**group, 'ids': [reverse[key] for key in group['ids']]} for group in catalog[field]]
            organized = [{**skill, 'category': self.store.state['annotations'].get(skill['id'], {}).get('category', '').strip() or skill['category']} for skill in catalog['skills']]
            catalog['related_groups'] = self.catalog.find_related(organized)
            catalog['stats']['related_groups'] = len(catalog['related_groups'])
            comparisons = clone(self.store.state['comparisons'])
            current_hashes = {s['id']: s['sha256'] for s in catalog['skills']}
            for record in comparisons.values():
                record['needs_review'] = any(current_hashes.get(key) != value for key, value in record['fingerprints'].items())
            return {**catalog, 'annotations': self.store.snapshot(), 'comparisons': comparisons,
                    'orphans': [{'id': key, 'identity': clone(value), 'annotation': clone(self.store.state['annotations'].get(key, {}))}
                                for key, value in self.store.state['identities'].items() if key not in self.live and not value.get('retired')],
                    'storage_error': self.store.error, 'data_version': 2,
                    'backup_settings': clone(self.store.state['settings']), 'changes': self.history.snapshot()}

    def skill(self, stable_id):
        if stable_id not in self.live:
            raise KeyError(stable_id)
        return self.raw[self.live[stable_id]]

    def content(self, stable_id):
        with self.store.lock:
            return self.catalog.content(self.skill(stable_id)['id'])

    def comparison(self, left_id, right_id):
        with self.store.lock:
            if left_id == right_id:
                raise ValueError('請選擇兩個不同技能。')
            self.skill(left_id)
            self.skill(right_id)
            self.verify_content(left_id)
            self.verify_content(right_id)
            originals = [self.content(key) for key in (left_id, right_id)]
            lines = [text[:128000].splitlines(keepends=True)[:1500] for text in originals]
            trimmed = any(len(text) > 128000 or len(text.splitlines()) > 1500 for text in originals)
            diff_parts, size = [], 0
            for line in difflib.unified_diff(*lines, fromfile=self.skill(left_id)['name'] + ' (A)', tofile=self.skill(right_id)['name'] + ' (B)', n=3):
                size += len(line)
                if size > 64000:
                    trimmed = True
                    break
                diff_parts.append(line)
            record = clone(self.store.state['comparisons'].get(pair_key(left_id, right_id)))
            if record:
                record['needs_review'] = any(self.skill(key)['sha256'] != value for key, value in record['fingerprints'].items())
            return {'diff': ''.join(diff_parts), 'truncated': trimmed, 'record': record,
                    'identical': self.skill(left_id)['sha256'] == self.skill(right_id)['sha256']}

    def verify_content(self, stable_id):
        skill = self.skill(stable_id)
        self.content(stable_id)
        with self.catalog.lock:
            path = self.catalog.by_id[skill['id']]['_path']
        if file_digest(path) != skill['sha256']:
            raise ValueError('技能內容已變更，請重新掃描後再比較或儲存結論。')

    def save_comparison(self, payload):
        if not isinstance(payload, dict) or set(payload) != {'left_id', 'right_id', 'decision', 'reason'}:
            raise ValueError('比較結論欄位錯誤。')
        with self.store.lock:
            left, right = payload['left_id'], payload['right_id']
            if not isinstance(left, str) or not isinstance(right, str):
                raise ValueError('技能識別錯誤。')
            self.verify_content(left)
            self.verify_content(right)
            record = {**payload, 'fingerprints': {key: self.skill(key)['sha256'] for key in (left, right)}, 'checked_at': now()}
            validate_comparison(record)
            next_state = clone(self.store.state)
            next_state['comparisons'][pair_key(left, right)] = record
            self.store.commit(next_state)
            return clone(record)

    def provenance(self, stable_id):
        with self.store.lock:
            skill = self.skill(stable_id)
            path = self.catalog.source_path(skill['id'])
            key = skill['path'], skill['sha256']
            if key in self.git_cache:
                return clone(self.git_cache[key])
        result = {'state': 'unknown', 'first_added_at': None, 'commit': None}
        executable = shutil.which('git')
        # Search no higher than the scan root, e.g. a home-directory dotfiles repo.
        boundaries = [root.resolve() for root in roots(self.catalog.home)]
        boundary = max((root for root in boundaries if path.is_relative_to(root)), key=lambda root: len(root.parts))
        if executable:
            environment = {k: v for k, v in os.environ.items() if not k.startswith('GIT_')}
            environment.update(GIT_NO_LAZY_FETCH='1', GIT_TERMINAL_PROMPT='0',
                               GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL=os.devnull,
                               GIT_CEILING_DIRECTORIES=str(boundary.parent))
            try:
                # A skill folder laid out as a bare repository must not supply config.
                process = subprocess.run([executable, '--no-pager', '-c', 'core.fsmonitor=false', '-c', 'log.showSignature=false',
                                          '-c', 'safe.bareRepository=explicit',
                                          '-C', str(path.parent), 'log', '--no-ext-diff', '--no-textconv', '--follow',
                                          '--diff-filter=A', '--format=%aI%x09%H', '--', 'SKILL.md'],
                                         capture_output=True, timeout=3, env=environment, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
                evidence = process.stdout.decode('utf-8', errors='replace').strip().splitlines()
                if process.returncode == 0:
                    result['state'] = 'not-tracked'
                    if evidence:
                        date, commit = evidence[-1].split('\t')
                        if re.fullmatch('[0-9a-f]{40,64}', commit) and datetime.fromisoformat(date).utcoffset() is not None:
                            result.update(state='known', first_added_at=date, commit=commit)
            except (OSError, subprocess.SubprocessError, ValueError):
                pass
        self.git_cache[key] = result
        return clone(result)

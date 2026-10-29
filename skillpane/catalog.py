"""Read-only discovery, originally derived from oh-my-skills (MIT).

See THIRD_PARTY_NOTICES.md. No workflow or script in a skill is executed.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from hashlib import sha256
import os
from pathlib import Path
import re
import threading

from .metadata import Document, frontmatter, parse_mapping, invocation_setting

LIMIT = 2 * 1024 * 1024
EXCLUDED = {'.git', '.trash', '.disabled', '__pycache__', 'node_modules'}
SOURCE_LABELS = {'personal': '個人技能', 'managed': 'Claude 同步',
                 'system': '系統內建', 'plugin': '外掛快取'}
GUIDES = {
    'animate': ('實作介面動畫', '設計與動畫', '為元件新增合適的動畫，直接完成實作。', '用 animate 幫這個對話框加入開啟與關閉動畫。'),
    'animation-vocabulary': ('查詢動畫名稱', '設計與動畫', '把你描述的動態效果，轉換成精確的動畫術語。', '用 animation-vocabulary 告訴我，元素依序出現的動畫叫什麼。'),
    'apple-design': ('Apple 介面設計', '設計與動畫', '規劃清楚的介面層次、自然的互動與細緻的動態。', '用 apple-design 改善這個設定面板的介面與互動。'),
    'emil-design-eng': ('打磨介面細節', '設計與動畫', '檢視元件、排版與互動細節，提升整體使用感受。', '用 emil-design-eng 檢查這個元件還能打磨哪些細節。'),
    'find-animation-opportunities': ('尋找動畫機會', '設計與動畫', '尋找值得加入動畫的地方，提出建議，維持原始碼唯讀。', '用 find-animation-opportunities 找出這個頁面值得加入動畫的地方。'),
    'improve-animations': ('盤點動畫改善', '設計與動畫', '盤點整個專案的動畫，整理問題與可執行的改善計畫。', '用 improve-animations 盤點整個專案的動畫問題，先提供計畫。'),
    'review-animations': ('審查動畫品質', '設計與動畫', '針對既有動畫或差異提出品質審查，與整體專案盤點分工。', '用 review-animations 審查這次修改的動畫。'),
    'mobile-native': ('改善手機體驗', '設計與動畫', '改善觸控、捲動、視窗高度與安全區域等手機網頁細節。', '用 mobile-native 檢查這個網頁在手機上的使用體驗。'),
    'prototype': ('探索介面方案', '設計與動畫', '建立幾個有明確差異的可操作原型，再選擇適合的方向。', '用 prototype 為這個技能列表做三種不同的介面方案。'),
}


def parse_frontmatter(text: str) -> dict:
    """Compatibility helper; records use the document with diagnostic details."""
    document = frontmatter(text)
    return {p[0]: value for p, value in document.values.items()
            if len(p) == 1 and document.error_for(p) is None}


def roots(home: Path):
    return [home / '.agents/skills', home / '.codex/skills',
            home / '.claude/skills', home / '.codex/plugins/cache']


def short_path(path: Path, home: Path) -> str:
    try:
        return '~/' + path.relative_to(home).as_posix()
    except ValueError:
        return str(path)


def within(path: Path, boundaries) -> bool:
    return any(path.is_relative_to(root) for root in boundaries)


def iter_skill_files(root, boundaries, on_skip):
    """Stop at skill boundaries; validate links before entering a directory.

    Each branch tracks canonical ancestors so allowed aliases remain visible
    across roots without following directory cycles. A SKILL.md boundary is
    honored even if that file is later rejected: nested copies must not become
    standalone skills merely because the outer metadata is unreadable.
    """
    pending = [(root, frozenset())]
    while pending:
        directory, ancestors = pending.pop()
        try:
            if EXCLUDED.intersection(directory.relative_to(root).parts):
                continue
            canonical = directory.resolve(strict=True)
            if (not within(canonical, boundaries) or canonical in ancestors
                    or any(EXCLUDED.intersection(canonical.relative_to(boundary).parts)
                           for boundary in boundaries if canonical.is_relative_to(boundary))):
                on_skip()
                continue
            with os.scandir(directory) as stream:
                entries = sorted(stream, key=lambda entry: entry.name.casefold())
            markers = [entry for entry in entries
                       if os.path.normcase(entry.name) == os.path.normcase('SKILL.md')
                       and not entry.is_dir()]
            if markers:
                yield directory / markers[0].name
                continue
            lineage = ancestors | {canonical}
            pending.extend((directory / entry.name, lineage) for entry in reversed(entries)
                           if entry.name not in EXCLUDED and entry.is_dir())
        except (OSError, ValueError, RuntimeError):
            on_skip()


def identify(path: Path, home: Path):
    plugin_root = home / '.codex/plugins/cache'
    if path.is_relative_to(plugin_root):
        parts = path.relative_to(plugin_root).parts
        if len(parts) >= 5:
            market, plugin, version = parts[:3]
            return 'plugin', '|'.join((market, plugin, *parts[3:])), version, plugin
        return 'plugin', str(path), '', ''
    if path.is_relative_to(home / '.codex/skills/.system'):
        return 'system', str(path), '', ''
    if path.is_relative_to(home / '.claude/skills/synced'):
        return 'managed', str(path), '', ''
    return 'personal', str(path), '', ''


def version_key(version):
    return tuple((0, int(p)) if p.isdigit() else (1, p.lower())
                 for p in re.findall(r'\d+|[^\d]+', version))


def category_for(name, description):
    text = (name + ' ' + description).lower()
    if any(s in text for s in ('animation', 'motion', 'design', 'animate', '動畫', '介面')):
        return '設計與動畫'
    if any(s in text for s in ('grafana', 'kibana', 'database', 'log query', '資料庫', '告警', '查 log')):
        return '維運與資料'
    if any(s in text for s in ('pdf', 'document', 'sheet', 'slides', 'presentation', '文件', '試算表')):
        return '文件與簡報'
    if any(s in text for s in ('commit', 'github', 'postman', 'api', 'skill-', '提交')):
        return '開發工具'
    return '其他'


# Bind curated descriptions to known personal skills, not just matching names.
GUIDE_SIGNATURES = {
    'apple-design': '07b280d5b529ba5eecec04f84d1cdde07160c028be90b8fc592d8679c50c4d2d',
    'animate': '7b49481b304d8fa724bc0cc49c92551020c4d1bf1fab6125540a0d28d858e1c2',
    'review-animations': '33eba2c2266237b894c1e096dd1e4e01da52012f0ce68a6108d196ca362f2461',
    'find-animation-opportunities': '9c2fc2f8aa09ae9b64f84fdb6e4c0497187edb76a5b5e082fa8d29fbd911bc07',
    'emil-design-eng': 'd19c67aadc5618c4b0e04edd5e6be9158c956a21bf685d6ac5b3aacebbf5d158',
    'prototype': '6e478c0cdf8f552afef1a48e00fd4ba8bb389a91ab9f794e7a219fc78654a6bb',
    'mobile-native': 'd25e0f21d1de6e717e02fb7bf70169cf14a8b3ac3cb62d53e09e50f83232a838',
    'animation-vocabulary': '0fa198004148d2af9c8a447c7ab3bbf8123f183f30583a70767577a9175af233',
    'improve-animations': '634983953a35bba1762780259240b9979dbd0d46ee4829bb1e06693915fcee88',
}


def read_record(path, aliases, home):
    raw = path.read_bytes()
    stat = path.stat()
    document = frontmatter(raw.decode('utf-8-sig', errors='replace'))
    warnings, advisories = [], []

    def string_field(key, fallback):
        error, value = document.error_for((key,)), document.values.get((key,))
        if error or (value is not None and not isinstance(value, str)):
            warnings.append(f'{key} 無法判讀：{error or "欄位必須是字串"}')
            return fallback
        return value.strip() if isinstance(value, str) and value.strip() else fallback

    name = string_field('name', path.parent.name)
    description = string_field('description', '')
    source, key, version, plugin = identify(path, home)
    if len(name) > 200 or len(plugin) > 200:
        raise ValueError('技能名稱或外掛識別超過支援長度。')
    signature = sha256(' '.join(description.split()).encode()).hexdigest()
    curated = (source == 'personal' and path == home / '.agents/skills' / name / 'SKILL.md'
               and GUIDE_SIGNATURES.get(name) == signature)
    display, category, summary, example = GUIDES[name] if curated else (
        name, category_for(name, description), description or '這個技能尚未提供用途描述。',
        f'請使用 {name} 協助我完成相關工作，先說明你會採取的步驟。')
    claude = invocation_setting(document, ('disable-model-invocation',),
                                short_path(path, home), invert=True)
    policy_file = path.parent / 'agents/openai.yaml'
    policy_document = Document()
    if policy_file.exists() or policy_file.is_symlink():
        try:
            resolved = policy_file.resolve(strict=True)
            if not resolved.is_relative_to(path.parent) or resolved.stat().st_size > 65536:
                raise ValueError('設定檔路徑或大小不符合讀取範圍')
            policy_document = parse_mapping(resolved.read_text(encoding='utf-8-sig'))
        except (OSError, ValueError, UnicodeError, RuntimeError):
            policy_document = Document(fatal=['無法安全讀取設定檔'])
    codex = invocation_setting(policy_document, ('policy', 'allow_implicit_invocation'),
                               short_path(policy_file, home))
    for host, setting in [('Codex', codex), ('Claude Code', claude)]:
        if setting['state'] == 'unknown':
            warnings.append(f'{host} 自動選用設定無法判讀：{setting["reason"]}')
    if codex['allowed'] is not None and claude['allowed'] is not None and codex['allowed'] != claude['allowed']:
        advisories.append('兩個工具的自動選用宣告不同。這是設定差異，並不一定是錯誤。')
    if not description:
        warnings.append('缺少 description，可能影響自動選用。')
    associated = set()
    for alias in aliases:
        if alias.is_relative_to(home / '.claude/skills'):
            associated.add('Claude')
        if alias.is_relative_to(home / '.agents/skills') or alias.is_relative_to(home / '.codex'):
            associated.add('Codex')
    valid = bool(re.fullmatch(r'[a-zA-Z0-9_-]+', name)) and source != 'plugin'
    commands = {'codex': '$' + name if valid and 'Codex' in associated else '',
                'claude': '/' + name if valid and 'Claude' in associated else ''}
    return {'id': sha256(key.encode('utf-8')).hexdigest()[:24], 'name': name,
            'display_name': display, 'description': description, 'summary': summary,
            'provenance': {'display_name': 'skillpane' if curated else 'skill' if document.values.get(('name',)) == name else 'folder',
                           'summary': 'skillpane' if curated else 'skill' if description else 'fallback',
                           'example': 'skillpane'},
            'category': category, 'source': source, 'source_label': SOURCE_LABELS[source],
            'path': short_path(path, home), 'aliases': [short_path(a, home) for a in sorted(aliases)],
            'associated_tools': sorted(associated), 'plugin': plugin, 'version': version,
            'versions': [], 'sha256': sha256(raw).hexdigest(), 'example': example,
            'commands': commands,
            'command_note': ('外掛命名空間尚未確認，請在對應工具的技能選擇器確認呼叫方式。'
                             if source == 'plugin' else 'CLI 參考格式；是否可用仍取決於工具載入與專案設定。'),
            'invocation': {'codex': codex, 'claude': claude,
                           'codex_implicit': codex['allowed'], 'claude_implicit': claude['allowed']},
            'warnings': list(dict.fromkeys(warnings)), 'advisories': advisories, 'usage': None,
            'created_at': datetime.fromtimestamp(stat.st_birthtime, timezone.utc).isoformat() if hasattr(stat, 'st_birthtime') else None,
            'modified_at': datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
            '_path': path}


class Catalog:
    def __init__(self, home):
        self.home = Path(home).resolve()
        self.lock = threading.RLock()
        self.entries, self.by_id, self.stats, self.overlaps = [], {}, {}, []
        self.generated_at = ''
        self.related_groups = []
        self.refresh()

    def refresh(self):
        root_paths = roots(self.home)
        boundaries = [r.resolve() for r in root_paths]
        aliases, skipped = defaultdict(set), 0
        def count_skip():
            nonlocal skipped
            skipped += 1
        for root in root_paths:
            if not root.is_dir():
                continue
            try:
                candidates = iter_skill_files(root, boundaries, count_skip)
                for candidate in candidates:
                    if EXCLUDED.intersection(candidate.relative_to(root).parts):
                        continue
                    try:
                        canonical = candidate.resolve(strict=True)
                        if not within(canonical, boundaries) or not canonical.is_file() or canonical.stat().st_size > LIMIT:
                            skipped += 1
                            continue
                        if any(EXCLUDED.intersection(canonical.relative_to(boundary).parts)
                               for boundary in boundaries if canonical.is_relative_to(boundary)):
                            skipped += 1
                            continue
                        aliases[canonical].add(candidate)
                    except (OSError, ValueError, RuntimeError):
                        skipped += 1
            except (OSError, ValueError, RuntimeError):
                skipped += 1
        grouped = defaultdict(list)
        for path, links in aliases.items():
            try:
                item = read_record(path, links, self.home)
                grouped[item['id']].append(item)
            except (OSError, ValueError, RuntimeError):
                skipped += 1
        entries = []
        for versions in grouped.values():
            versions.sort(key=lambda v: version_key(v['version']), reverse=True)
            current = versions[0]
            current['versions'] = [{'version': v['version'], 'path': v['path'],
                                    'sha256': v['sha256']} for v in versions]
            entries.append(current)
        entries.sort(key=lambda v: (v['source'] != 'personal', v['display_name'].casefold(), v['name']))
        overlaps = self.find_overlaps(entries)
        related_groups = self.find_related(entries)
        stats = {key: sum(item['source'] == key for item in entries) for key in SOURCE_LABELS}
        stats.update(total=len(entries), files=len(aliases),
                     extra_versions=sum(len(group) - 1 for group in grouped.values()),
                     shared=sum(len(paths) > 1 for paths in aliases.values()), skipped=skipped,
                     warnings=sum(bool(i['warnings']) for i in entries), overlap_groups=len(overlaps), related_groups=len(related_groups),
                     advisories=sum(bool(i['advisories']) for i in entries))
        with self.lock:
            self.entries = entries
            self.by_id = {v['id']: v for v in entries}
            self.stats, self.overlaps = stats, overlaps
            self.related_groups = related_groups
            self.generated_at = datetime.now(timezone.utc).isoformat()

    @staticmethod
    def find_overlaps(entries):
        groups = []
        for field, kind, title in [('name', 'same-name', '名稱相同'), ('sha256', 'identical', '內容完全相同')]:
            found = defaultdict(list)
            for entry in entries:
                found[entry[field]].append(entry)
            for key, members in found.items():
                if len(members) > 1:
                    groups.append({'kind': kind, 'title': title, 'label': members[0]['name'],
                                   'ids': [m['id'] for m in members],
                                   'reason': '請比較來源與用途，再決定是否需要整理。'})
        return groups

    @staticmethod
    def find_related(entries):
        categories = defaultdict(list)
        for entry in entries:
            if entry['source'] == 'personal':
                categories[entry['category']].append(entry)
        return [{'kind': 'related', 'title': '同分類工具', 'label': category,
                 'ids': [entry['id'] for entry in members],
                 'reason': '僅依分類整理，方便比較各自分工；不是重複或淘汰判定。'}
                for category, members in sorted(categories.items()) if len(members) > 1]

    def snapshot(self):
        with self.lock:
            public = [{k: v for k, v in item.items() if not k.startswith('_')} for item in self.entries]
            return {'skills': public, 'stats': dict(self.stats), 'overlaps': list(self.overlaps),
                    'generated_at': self.generated_at, 'related_groups': list(self.related_groups),
                    'scan_scope': {'roots': [short_path(p, self.home) for p in roots(self.home)],
                                   'skill_boundary': 'first-skill-file',
                                   'nested_skills_scanned': False,
                                   'project_skills_scanned': False, 'activation_verified': False}}

    def content(self, skill_id):
        return self.source_path(skill_id).read_text(encoding='utf-8-sig', errors='replace')

    def source_path(self, skill_id):
        with self.lock:
            item = self.by_id.get(skill_id)
        if item is None:
            raise KeyError('這個技能不在目前的清單中。')
        path = item['_path']
        canonical = path.resolve(strict=True)
        if canonical != path or not within(canonical, [r.resolve() for r in roots(self.home)]) or canonical.stat().st_size > LIMIT:
            raise ValueError('來源路徑已變更，請重新掃描。')
        return canonical

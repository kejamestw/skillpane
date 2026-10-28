"""Read-only discovery. Frontmatter parsing adapted from oh-my-skills (MIT).

See THIRD_PARTY_NOTICES.md. No workflow or script in a skill is executed.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import re
import threading

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


def parse_frontmatter(text: str) -> dict[str, str]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != '---':
        return {}
    end = next((i for i in range(1, len(lines)) if lines[i].strip() == '---'), None)
    if end is None:
        return {}
    metadata, index = {}, 1
    while index < end:
        line = lines[index]
        if not line.strip() or line.startswith((' ', '\t')) or ':' not in line:
            index += 1
            continue
        key, value = (part.strip() for part in line.split(':', 1))
        if value in {'>', '|', '>-', '|-'}:
            block, index = [], index + 1
            while index < end and (not lines[index] or lines[index].startswith((' ', '\t'))):
                block.append(lines[index].strip())
                index += 1
            metadata[key] = ('\n' if value.startswith('|') else ' ').join(block).strip()
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            if value[0] == '"':
                try:
                    value = json.loads(value)
                except (ValueError, TypeError):
                    value = value[1:-1]
            else:
                value = value[1:-1].replace("''", "'")
        metadata[key] = value
        index += 1
    return metadata


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


def read_record(path, aliases, home):
    raw = path.read_bytes()
    text = raw.decode('utf-8-sig', errors='replace')
    meta = parse_frontmatter(text)
    name = meta.get('name', path.parent.name).strip() or path.parent.name
    description = meta.get('description', '').strip()
    source, key, version, plugin = identify(path, home)
    display, category, summary, example = GUIDES.get(name, (
        name, category_for(name, description), description or '這個技能尚未提供用途描述。',
        f'請使用 {name} 協助我完成相關工作，先說明你會採取的步驟。'))
    manual_claude = meta.get('disable-model-invocation', '').lower() == 'true'
    implicit_codex = True
    policy_file = path.parent / 'agents/openai.yaml'
    if policy_file.is_file():
        resolved = policy_file.resolve()
        if resolved.is_relative_to(path.parent) and resolved.stat().st_size < 65536:
            policy = resolved.read_text(encoding='utf-8-sig', errors='replace')
            policy_match = re.search(r'^\s+allow_implicit_invocation:\s*(true|false)\b', policy, re.M)
            if policy_match:
                implicit_codex = policy_match.group(1) == 'true'
    associated = set()
    for alias in aliases:
        if alias.is_relative_to(home / '.claude/skills'):
            associated.add('Claude')
        if alias.is_relative_to(home / '.agents/skills') or alias.is_relative_to(home / '.codex'):
            associated.add('Codex')
    warnings = []
    if manual_claude and implicit_codex:
        warnings.append('Claude 設為僅手動呼叫；Codex 未設定相同的自動呼叫限制。')
    if not description:
        warnings.append('缺少 description，可能影響自動選用。')
    valid_command = bool(re.fullmatch(r'[a-zA-Z0-9_-]+', name))
    return {'id': sha256(key.encode('utf-8')).hexdigest()[:24], 'name': name,
            'display_name': display, 'description': description, 'summary': summary,
            'category': category, 'source': source, 'source_label': SOURCE_LABELS[source],
            'path': short_path(path, home), 'aliases': [short_path(a, home) for a in sorted(aliases)],
            'associated_tools': sorted(associated), 'plugin': plugin, 'version': version,
            'versions': [], 'sha256': sha256(raw).hexdigest(), 'example': example,
            'commands': {'codex': '$' + name if valid_command else '',
                         'claude': '/' + name if valid_command else ''},
            'invocation': {'codex_implicit': implicit_codex, 'claude_implicit': not manual_claude},
            'warnings': warnings, 'usage': None,
            'modified_at': datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat(),
            '_path': path}


class Catalog:
    def __init__(self, home):
        self.home = Path(home).resolve()
        self.lock = threading.RLock()
        self.entries, self.by_id, self.stats, self.overlaps = [], {}, {}, []
        self.generated_at = ''
        self.refresh()

    def refresh(self):
        root_paths = roots(self.home)
        boundaries = [r.resolve() for r in root_paths]
        aliases, skipped = defaultdict(set), 0
        for root in root_paths:
            if not root.is_dir():
                continue
            try:
                candidates = root.rglob('SKILL.md')
                for candidate in candidates:
                    if EXCLUDED.intersection(candidate.relative_to(root).parts):
                        continue
                    try:
                        canonical = candidate.resolve(strict=True)
                        if not within(canonical, boundaries) or not canonical.is_file() or canonical.stat().st_size > LIMIT:
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
        stats = {key: sum(item['source'] == key for item in entries) for key in SOURCE_LABELS}
        stats.update(total=len(entries), files=len(aliases),
                     extra_versions=sum(len(group) - 1 for group in grouped.values()),
                     shared=sum(len(paths) > 1 for paths in aliases.values()), skipped=skipped,
                     warnings=sum(bool(i['warnings']) for i in entries), overlap_groups=len(overlaps))
        with self.lock:
            self.entries = entries
            self.by_id = {v['id']: v for v in entries}
            self.stats, self.overlaps = stats, overlaps
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
        motion = [v for v in entries if v['source'] == 'personal' and v['category'] == '設計與動畫']
        if len(motion) > 1:
            groups.append({'kind': 'related', 'title': '用途相近，分工待確認', 'label': '設計與動畫',
                           'ids': [v['id'] for v in motion],
                           'reason': '依分類整理的檢查候選，包含實作、審查、盤點等不同工作；不代表可以刪除。'})
        return groups

    def snapshot(self):
        with self.lock:
            public = [{k: v for k, v in item.items() if not k.startswith('_')} for item in self.entries]
            return {'skills': public, 'stats': dict(self.stats), 'overlaps': list(self.overlaps),
                    'generated_at': self.generated_at}

    def content(self, skill_id):
        with self.lock:
            item = self.by_id.get(skill_id)
        if item is None:
            raise KeyError('這個技能不在目前的清單中。')
        path = item['_path']
        canonical = path.resolve(strict=True)
        if canonical != path or not within(canonical, [r.resolve() for r in roots(self.home)]) or canonical.stat().st_size > LIMIT:
            raise ValueError('來源路徑已變更，請重新掃描。')
        return canonical.read_text(encoding='utf-8-sig', errors='replace')

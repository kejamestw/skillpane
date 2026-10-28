"""Conservative, non-executing YAML field reader; unsupported fields stay unknown.

Reads block mappings and common scalar forms needed for skill metadata. It is
not a general YAML validator. Sequences, flow collections and YAML tags are
never interpreted as invocation settings.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import json
import re


def without_comment(line: str) -> str:
    quote, escaped, index = None, False, 0
    while index < len(line):
        char = line[index]
        if quote == '"':
            if escaped:
                escaped = False
            elif char == '\\':
                escaped = True
            elif char == quote:
                quote = None
        elif quote == "'":
            if char == "'":
                if index + 1 < len(line) and line[index + 1] == "'":
                    index += 1
                else:
                    quote = None
        elif char in {'"', "'"} and not line[:index].strip():
            quote = char
        elif char == '#' and (index == 0 or line[index - 1].isspace()):
            return line[:index].rstrip()
        index += 1
    if quote is not None:
        raise ValueError('引號未關閉')
    return line.rstrip()


def scalar(value):
    if value == '':
        return None
    if value.startswith('"'):
        parsed = json.loads(value)
        if not isinstance(parsed, str):
            raise ValueError('不是字串')
        return parsed
    if value.startswith("'"):
        if len(value) < 2 or not value.endswith("'"):
            raise ValueError('引號格式錯誤')
        inner = value[1:-1]
        if "'" in inner.replace("''", ''):
            raise ValueError('單引號字串格式錯誤')
        return inner.replace("''", "'")
    if value.lower() in {'true', 'false'}:
        return value.lower() == 'true'
    if value.lower() in {'null', '~'}:
        return None
    if re.fullmatch(r'[-+]?\d+', value):
        return int(value)
    if value == '{}':
        return {}
    if value == '[]':
        return []
    if value[0] in '[{&*!>|@`' or ': ' in value:
        raise ValueError('這個 YAML 寫法目前無法判讀')
    return value


@dataclass
class Document:
    values: dict = field(default_factory=dict)
    lines: dict = field(default_factory=dict)
    problems: dict = field(default_factory=dict)
    fatal: list = field(default_factory=list)

    def error_for(self, path):
        if self.fatal:
            return self.fatal[0]
        for problem_path, message in self.problems.items():
            if path[:len(problem_path)] == problem_path:
                return message
        for size in range(1, len(path)):
            parent = path[:size]
            if parent in self.values and not isinstance(self.values[parent], dict):
                return '父層欄位不是可判讀的對應表'
        return None


def parse_mapping(text: str, *, line_offset=0) -> Document:
    document = Document()
    lines, stack, child_indents = text.splitlines(), [(-1, ())], {}
    index = 0
    while index < len(lines):
        raw, number = lines[index], index + 1 + line_offset
        index += 1
        if not raw.strip() or raw.lstrip().startswith('#'):
            continue
        if '\t' in raw[:len(raw) - len(raw.lstrip())]:
            document.fatal.append(f'第 {number} 行的縮排包含 Tab')
            continue
        indent = len(raw) - len(raw.lstrip(' '))
        while len(stack) > 1 and indent <= stack[-1][0]:
            stack.pop()
        parent = stack[-1][1]
        if not parent and indent:
            document.fatal.append(f'第 {number} 行的頂層縮排不正確')
        if parent in child_indents and child_indents[parent] != indent:
            document.problems[parent] = f'第 {number} 行的縮排不一致'
        else:
            child_indents[parent] = indent
        if parent and document.values.get(parent) is None:
            document.values[parent] = {}
        match = re.match(r"(?:([A-Za-z_][\w-]*)|\"([A-Za-z_][\w-]*)\"|'([A-Za-z_][\w-]*)'):\s*(.*)$", raw.strip())
        if not match:
            message = f'第 {number} 行包含無法判讀的 YAML 結構'
            if parent:
                document.problems[parent] = message
            else:
                document.fatal.append(message)
            continue
        key = next(v for v in match.groups()[:3] if v is not None)
        path = (*parent, key)
        if path in document.values:
            document.problems[path] = f'第 {number} 行重複定義欄位'
        document.lines[path] = number
        try:
            value = without_comment(match.group(4)).strip()
            if value in {'|', '|-', '|+', '>', '>-', '>+'}:
                block = []
                while index < len(lines):
                    candidate = lines[index]
                    if candidate.strip() and len(candidate) - len(candidate.lstrip(' ')) <= indent:
                        break
                    block.append(candidate)
                    index += 1
                nonempty = [len(v) - len(v.lstrip(' ')) for v in block if v.strip()]
                width = min(nonempty) if nonempty else indent + 1
                block = [v[width:] if v.strip() else '' for v in block]
                if value.startswith('|'):
                    parsed = '\n'.join(block).rstrip('\n')
                else:
                    parsed = re.sub(r'(?<=\S)\n(?=\S)', ' ', '\n'.join(block)).strip()
                document.values[path] = parsed
            else:
                document.values[path] = scalar(value)
                if not value:
                    stack.append((indent, path))
        except (ValueError, TypeError) as error:
            document.values[path] = None
            document.problems[path] = f'第 {number} 行：{error}'
    return document


def frontmatter(text):
    lines = text.lstrip('\ufeff').splitlines()
    if not lines or lines[0].strip() != '---':
        return Document(fatal=['缺少 YAML frontmatter'])
    end = next((i for i in range(1, len(lines)) if lines[i].strip() == '---'), None)
    if end is None:
        return Document(fatal=['YAML frontmatter 未結束'])
    return parse_mapping('\n'.join(lines[1:end]), line_offset=1)


def invocation_setting(document, path, source, *, invert=False):
    error = document.error_for(path)
    value = document.values.get(path)
    if not error and path in document.values and type(value) is not bool:
        error = '這個設定必須是 YAML 布林值 true 或 false'
    if error:
        state, allowed = 'unknown', None
    elif path in document.values:
        state, allowed = 'explicit', not value if invert else value
    else:
        state, allowed = 'default', True
    return {'state': state, 'allowed': allowed, 'source': source,
            'field': '.'.join(path), 'line': document.lines.get(path),
            'reason': error or ('依明確設定判讀' if state == 'explicit' else '未設定此欄位，採工具預設值')}

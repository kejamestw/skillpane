"""Check repository Markdown file/image links locally, without network requests."""
import html
from pathlib import Path
import re
import shutil
import subprocess
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]


def broken_links(text, document, root):
    targets = re.findall(r'!?\[[^\]\n]*\]\(([^)\n]+)\)', text)
    targets += re.findall(r'<img\b[^>]*\bsrc=[\"\x27]([^\"\x27]+)', text, re.I)
    broken = 0
    for target in targets:
        target = html.unescape(target.strip().split(' "', 1)[0].strip('<>'))
        try:
            url = urlsplit(target)
            if url.scheme in ('http', 'https', 'mailto'):
                continue
            if url.scheme or url.netloc:
                raise ValueError('Unsupported link.')
            if not url.path:
                continue  # Fragment anchors and remote content are not verified.
            path = (document.parent / unquote(url.path)).resolve()
            path.relative_to(root.resolve())
            if not path.is_file():
                raise ValueError('Missing link.')
        except (OSError, ValueError):
            broken += 1
    return broken


def main():
    git = shutil.which('git')
    if not git:
        raise RuntimeError('Git is required for documentation checks.')
    raw = subprocess.check_output([git, '-c', 'core.fsmonitor=false', 'ls-files', '-z',
                                   '--cached', '--others', '--exclude-standard'], cwd=ROOT, timeout=30)
    names = sorted(set(raw.decode('utf-8').split('\0')) - {''})
    files = [ROOT / name for name in names if name.endswith('.md')]
    errors = 0
    for path in files:
        if path.is_symlink() or not path.resolve().is_relative_to(ROOT.resolve()):
            print(f'Unsafe Markdown source: {path.relative_to(ROOT).as_posix()!r}')
            errors += 1
            continue
        count = broken_links(path.read_text(encoding='utf-8-sig'), path, ROOT)
        if count:
            print(f'Broken relative links: {path.relative_to(ROOT).as_posix()!r} ({count})')
            errors += count
    print(f'Checked {len(files)} Markdown files; broken relative file/image links: {errors}.')
    raise SystemExit(bool(errors))


if __name__ == '__main__':
    main()

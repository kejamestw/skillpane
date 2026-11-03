"""Build a local Windows x64 one-folder prototype from explicit public assets only."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from hashlib import sha256
import importlib.metadata
import json
from pathlib import Path
import platform
import shutil
import sys
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from skillpane.server import ASSETS


def copy_licenses(destination):
    destination.mkdir()
    for source in (ROOT / 'LICENSE', ROOT / 'THIRD_PARTY_NOTICES.md', ROOT / 'third_party/oh-my-skills.LICENSE'):
        shutil.copyfile(source, destination / source.name)
    python_license = Path(sys.base_prefix) / 'LICENSE.txt'
    if not python_license.is_file():
        raise RuntimeError('Python license is required for a desktop bundle.')
    shutil.copyfile(python_license, destination / 'Python-LICENSE.txt')
    distributions = {}
    for line in (ROOT / 'requirements-desktop.lock').read_text(encoding='utf-8').splitlines():
        if not line.strip() or line.startswith('#'):
            continue
        name, rest = line.split('==', 1)
        version = rest.split()[0]
        distribution = importlib.metadata.distribution(name)
        if distribution.version != version:
            raise RuntimeError('Installed desktop dependency does not match its lock.')
        folder = destination / name
        folder.mkdir()
        # Include the package's public metadata and any shipped license/notice files.
        (folder / 'METADATA.txt').write_text(distribution.read_text('METADATA') or '', encoding='utf-8')
        license_files = []
        for entry in distribution.files or ():
            if any(part.lower().startswith(('license', 'copying', 'notice')) for part in entry.parts):
                source = distribution.locate_file(entry)
                if source.is_file():
                    target = folder / ('-'.join(entry.parts))
                    shutil.copyfile(source, target)
                    license_files.append(target.name)
        distributions[name] = {'version': version, 'licenses': license_files}
    (destination / 'desktop-dependencies.json').write_text(json.dumps(distributions, indent=2), encoding='utf-8')


def main():
    argparse.ArgumentParser(description=__doc__).parse_args()
    if sys.platform != 'win32' or platform.machine().lower() not in ('amd64', 'x86_64') or sys.version_info[:2] != (3, 12):
        raise SystemExit('This prototype build lock requires Windows x64 and CPython 3.12.')
    import PyInstaller.__main__
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid4().hex[:8]
    build = ROOT / '.runtime' / 'desktop-build' / stamp
    resources = build / 'resources'
    web = resources / 'web'
    web.mkdir(parents=True)
    for filename in sorted({name for name, _ in ASSETS.values()}):
        source = ROOT / 'web' / filename
        if not source.is_file() or source.is_symlink():
            raise RuntimeError('Unexpected frontend asset.')
        shutil.copyfile(source, web / filename)
    icon = resources / 'skillpane.ico'
    icon_source = ROOT / 'assets/brand/skillpane.ico'
    if not icon_source.is_file() or icon_source.is_symlink():
        raise RuntimeError('The approved desktop icon is required.')
    shutil.copyfile(icon_source, icon)
    copy_licenses(resources / 'licenses')
    # No repo-wide --add-data, no personal home/data/runtime and no onefile extraction.
    PyInstaller.__main__.run([
        str(ROOT / 'scripts/desktop_entry.py'), '--name', 'Skillpane', '--windowed', '--onedir', '--noupx',
        '--distpath', str(build / 'dist'), '--workpath', str(build / 'work'), '--specpath', str(build / 'spec'),
        '--paths', str(ROOT), '--icon', str(icon),
        '--add-data', str(web) + ';web', '--add-data', str(resources / 'licenses') + ';licenses',
        '--add-data', str(icon) + ';desktop-assets',
        '--hidden-import', 'webview.platforms.edgechromium', '--hidden-import', 'webview.platforms.winforms',
    ])
    app = build / 'dist' / 'Skillpane'
    guide = (ROOT / 'docs/DESKTOP.md').read_text(encoding='utf-8')
    guide = guide.replace('(../assets/brand/README.md)', '(https://github.com/kejamestw/skillpane/blob/main/assets/brand/README.md)')
    (app / 'DESKTOP.md').write_text(guide, encoding='utf-8')
    files = sorted(p for p in app.rglob('*') if p.is_file())
    # Reject known personal-data filenames even if a future collection hook changes.
    forbidden = {'annotations.json', 'scan-history.json', 'server.json', 'desktop-preferences.json'}
    if any(p.name in forbidden or {'.data', '.runtime', '.agents', '.codex', '.claude'} & set(p.relative_to(app).parts)
           for p in files):
        raise RuntimeError('Private path found in generated desktop bundle; do not distribute.')
    result = {'executable': str(app / 'Skillpane.exe'), 'files': len(files),
              'bytes': sum(p.stat().st_size for p in files),
              'executable_sha256': sha256((app / 'Skillpane.exe').read_bytes()).hexdigest(),
              'icon_sha256': sha256(icon.read_bytes()).hexdigest(),
              'signed': False, 'published': False}
    (build / 'build-result.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result), flush=True)


if __name__ == '__main__':
    main()

"""Conservative CI selection. Unknown events, paths or Git state run everything."""
import argparse
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
ROOT_DOCS = {'README.md', 'README.en.md', 'CHANGELOG.md', 'SECURITY.md',
             'SUPPORT.md', 'CONTRIBUTING.md', 'THIRD_PARTY_NOTICES.md', 'LICENSE'}


def docs_only(paths):
    if not paths:
        return False
    for name in paths:
        path = PurePosixPath(name)
        if (not name or '\\' in name or path.is_absolute() or '..' in path.parts
                or any(ord(character) < 32 for character in name)):
            return False
        if name in ROOT_DOCS:
            continue
        if len(path.parts) > 1 and path.parts[0] == 'docs' and path.suffix == '.md':
            continue
        if len(path.parts) == 3 and path.parts[:2] == ('docs', 'images') and path.suffix == '.png':
            continue
        return False
    return True


def git(root, *args):
    executable = shutil.which('git')
    if not executable:
        raise ValueError('Git unavailable.')
    result = subprocess.run([executable, '-c', 'core.fsmonitor=false', *args], cwd=root,
                            capture_output=True, timeout=30, check=True)
    return result.stdout


def commit(value):
    if not isinstance(value, str) or not re.fullmatch(r'[0-9a-f]{40}|[0-9a-f]{64}', value) or set(value) == {'0'}:
        raise ValueError('Invalid commit.')
    return value


def detect(event, payload, root=ROOT):
    if event not in ('push', 'pull_request'):
        return True, 'manual-or-unknown-event'
    try:
        if event == 'push':
            base, head = commit(payload['before']), commit(payload['after'])
            if git(root, 'rev-parse', 'HEAD').decode('ascii').strip() != head:
                raise ValueError('Checkout mismatch.')
        else:
            base = commit(payload['pull_request']['base']['sha'])
            head = commit(payload['pull_request']['head']['sha'])
            git(root, 'merge-base', '--is-ancestor', head, 'HEAD')
            base = commit(git(root, 'merge-base', base, head).decode('ascii').strip())
        for value in (base, head):
            git(root, 'cat-file', '-e', value + '^{commit}')
        raw = git(root, 'diff', '--name-only', '--no-renames', '--no-ext-diff', '--no-textconv', '-z', base, head, '--')
        if len(raw) > 1024 * 1024 or (raw and not raw.endswith(b'\0')):
            raise ValueError('Invalid changed paths.')
        paths = raw.decode('utf-8').split('\0')[:-1] if raw else []
        return (False, 'documentation-only') if docs_only(paths) else (True, 'code-or-unknown-path')
    except (KeyError, TypeError, ValueError, UnicodeError, OSError, subprocess.SubprocessError):
        return True, 'uncertain-git-or-event'


def validate_jobs(full, changes, tests, browser, secrets):
    if changes != 'success' or secrets != 'success' or full not in ('true', 'false'):
        raise ValueError('Classification and secret checks must succeed.')
    expected = 'success' if full == 'true' else 'skipped'
    if tests != expected or browser != expected:
        raise ValueError('Required test jobs did not reach their expected result.')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['detect', 'validate'])
    args = parser.parse_args()
    if args.action == 'validate':
        validate_jobs(*(os.environ.get(name, '') for name in
                        ('CI_FULL', 'CI_CHANGES', 'CI_TESTS', 'CI_BROWSER', 'CI_SECRETS')))
        print('CI validation passed; required jobs reached the expected results.')
        return
    try:
        with Path(os.environ['GITHUB_EVENT_PATH']).open('rb') as stream:
            raw = stream.read(2 * 1024 * 1024 + 1)
        if len(raw) > 2 * 1024 * 1024:
            raise ValueError('Oversized event.')
        full, reason = detect(os.environ.get('GITHUB_EVENT_NAME', ''), json.loads(raw))
    except (KeyError, ValueError, OSError, RecursionError):
        full, reason = True, 'unreadable-event'
    # Only fixed boolean/static reason values enter Actions outputs and logs.
    value = 'true' if full else 'false'
    with Path(os.environ['GITHUB_OUTPUT']).open('a', encoding='utf-8') as output:
        output.write(f'full={value}\n')
    print(f'CI full={value}; reason={reason}')


if __name__ == '__main__':
    main()

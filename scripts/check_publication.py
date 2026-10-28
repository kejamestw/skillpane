"""Check publication file boundaries; use Gitleaks separately for secrets.

Only filenames and counts are printed. Never reads personal skill directories.
"""
import argparse
from pathlib import Path, PurePosixPath
import shutil
import subprocess


def git(*args):
    executable = shutil.which('git')
    if executable is None:
        raise RuntimeError('Git is required for publication checks.')
    return subprocess.check_output([executable, *args], cwd=ROOT).decode('utf-8', errors='surrogateescape')


def forbidden(name):
    path = PurePosixPath(name.lower())
    private = {'.data', '.runtime', '.agents', '.claude', '.codex', '.venv', '__pycache__'}
    return (bool(private.intersection(path.parts)) or path.name in {'annotations.json', 'server.json', 'credentials.json', 'id_rsa', 'id_ed25519'}
            or path.name == '.env' or path.name.startswith('.env.') and path.name != '.env.example'
            or path.suffix in {'.pem', '.key', '.p12', '.pfx', '.pyc'}
            or path.name.startswith('skillpane-backup-') and path.suffix == '.json')


ROOT = Path(__file__).resolve().parents[1]
if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Check Git file boundaries without printing file contents.')
    parser.add_argument('--history', action='store_true', help='Include filenames from all locally reachable history.')
    parser.add_argument('--include-untracked', action='store_true', help='Include non-ignored files proposed for commit.')
    args = parser.parse_args()
    options = ['ls-files', '-z', '--cached']
    if args.include_untracked:
        options += ['--others', '--exclude-standard']
    paths = set(git(*options).split('\0')) - {''}
    if args.history:
        paths.update(set(git('log', '--all', '--name-only', '--format=', '-z').split('\0')) - {''})
    problems = sorted(name for name in paths if forbidden(name.strip('\n')))
    for name in problems:
        print('Forbidden publication path:', repr(name))
    print(f'Checked {len(paths)} Git paths; forbidden paths: {len(problems)}.')
    raise SystemExit(bool(problems))

"""Synthetic Git histories and negative cases for conservative CI selection."""
import itertools
import os
from pathlib import Path
import shutil
import subprocess
import sys
import unittest
from unittest.mock import patch

from scripts.ci_scope import detect, docs_only, validate_jobs
from test_catalog import fixture_root


class ScopeTests(unittest.TestCase):
    def test_documentation_allowlist(self):
        self.assertTrue(docs_only(['README.md', 'docs/USER_GUIDE.md', 'docs/images/changes.png', 'LICENSE']))

    def test_unknown_runtime_workflow_and_ambiguous_paths_run_full(self):
        for name in ('AGENTS.md', 'unknown.md', 'web/index.html', 'skillpane/server.py',
                     'tests/test_ci_scope.py', 'scripts/ci_scope.py', 'Start.ps1',
                     '.github/workflows/ci.yml', 'package-lock.json', 'docs/demo.py',
                     'docs/images/example.svg', '../README.md', '/docs/x.md',
                     'docs\\x.md', 'docs/fake\nfull=false.md'):
            with self.subTest(name=name):
                self.assertFalse(docs_only([name]))
                self.assertFalse(docs_only(['README.md', name]))
        self.assertFalse(docs_only([]))

    def test_dispatch_unknown_and_malformed_events_run_full(self):
        for event, payload in [('workflow_dispatch', {}), ('merge_group', {}), ('push', {}),
                               ('push', None), ('pull_request', {'pull_request': {}}),
                               ('push', {'before': '0' * 40, 'after': 'a' * 40}),
                               ('push', {'before': '--help', 'after': 'a' * 40})]:
            self.assertTrue(detect(event, payload)[0])

    def test_git_errors_and_checkout_mismatch_run_full(self):
        payload = {'before': 'a' * 40, 'after': 'b' * 40}
        with patch('scripts.ci_scope.git', side_effect=OSError('Synthetic Git failure')):
            self.assertTrue(detect('push', payload)[0])
        with patch('scripts.ci_scope.git', return_value=b'c' * 40):
            self.assertTrue(detect('push', payload)[0])

    def test_invalid_paths_bytes_or_empty_diff_run_full(self):
        payload = {'before': 'a' * 40, 'after': 'b' * 40}
        for changed in (b'README.md', b'\xff\0', b'', b'x' * (1024 * 1024 + 1)):
            with self.subTest(changed_size=len(changed)), patch('scripts.ci_scope.git',
                    side_effect=[b'b' * 40 + b'\n', b'', b'', changed]):
                self.assertTrue(detect('push', payload)[0])

    def test_aggregate_never_accepts_missing_failed_or_cancelled_jobs(self):
        statuses = ('success', 'failure', 'cancelled', 'skipped', '')
        for full in ('true', 'false', ''):
            for values in itertools.product(statuses, repeat=4):
                changes, tests, browser, secrets = values
                valid = values == ('success', 'success', 'success', 'success') if full == 'true' else (
                    full == 'false' and values == ('success', 'skipped', 'skipped', 'success'))
                if valid:
                    validate_jobs(full, *values)
                else:
                    with self.assertRaises(ValueError):
                        validate_jobs(full, changes, tests, browser, secrets)


@unittest.skipUnless(shutil.which('git'), 'Git is required for synthetic history cases')
class GitScopeTests(unittest.TestCase):
    def setUp(self):
        self.root = fixture_root() / 'synthetic-git-scope'
        self.root.mkdir()
        self.env = {key: value for key, value in os.environ.items() if key.upper() in
                    {'PATH', 'SYSTEMROOT', 'WINDIR', 'TEMP', 'TMP', 'COMSPEC', 'SYSTEMDRIVE'}}
        self.env.update(GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM='1',
                        GIT_TERMINAL_PROMPT='0', GIT_AUTHOR_NAME='Synthetic fixture',
                        GIT_AUTHOR_EMAIL='fixture@example.invalid', GIT_COMMITTER_NAME='Synthetic fixture',
                        GIT_COMMITTER_EMAIL='fixture@example.invalid')
        self.git('init', '--quiet')
        (self.root / 'README.md').write_text('Synthetic initial docs\n', encoding='utf-8')
        (self.root / 'program.py').write_text('# Synthetic initial code\n', encoding='utf-8')
        self.base = self.save()

    def git(self, *args):
        return subprocess.check_output([shutil.which('git'), '-c', 'commit.gpgsign=false',
                '-c', 'core.hooksPath=' + str(self.root / 'no-hooks'), *args], cwd=self.root,
                env=self.env, stderr=subprocess.DEVNULL).decode('utf-8').strip()

    def save(self):
        self.git('add', '--', 'README.md', 'program.py')
        self.git('commit', '--quiet', '-m', 'Synthetic CI scope fixture')
        return self.git('rev-parse', 'HEAD')

    def test_real_push_docs_then_mixed_changes(self):
        (self.root / 'README.md').write_text('Synthetic updated docs\n', encoding='utf-8')
        head = self.save()
        self.assertFalse(detect('push', {'before': self.base, 'after': head}, self.root)[0])
        (self.root / 'program.py').write_text('# Synthetic code revision\n', encoding='utf-8')
        changed = self.save()
        self.assertTrue(detect('push', {'before': self.base, 'after': changed}, self.root)[0])

    def test_real_pr_merge_base_excludes_target_only_changes(self):
        # Build two histories without switching or modifying any real project branch.
        (self.root / 'README.md').write_text('Synthetic PR docs\n', encoding='utf-8')
        head = self.save()
        self.git('read-tree', self.base)
        (self.root / 'program.py').write_text('# Synthetic target-only change\n', encoding='utf-8')
        self.git('add', '--', 'program.py')
        tree = self.git('write-tree')
        target = self.git('commit-tree', tree, '-p', self.base, '-m', 'Synthetic target')
        self.assertIn('program.py', self.git('diff', '--name-only', target, head))
        payload = {'pull_request': {'base': {'sha': target}, 'head': {'sha': head}}}
        self.assertFalse(detect('pull_request', payload, self.root)[0])

    def test_missing_push_base_runs_full(self):
        self.assertTrue(detect('push', {'before': 'f' * 40, 'after': self.base}, self.root)[0])

    def test_cli_corrupt_event_emits_only_full_true(self):
        event, output = self.root / 'event.json', self.root / 'outputs.txt'
        event.write_text('{broken synthetic event', encoding='utf-8')
        env = {**self.env, 'GITHUB_EVENT_NAME': 'push', 'GITHUB_EVENT_PATH': str(event),
               'GITHUB_OUTPUT': str(output)}
        script = Path(__file__).resolve().parents[1] / 'scripts/ci_scope.py'
        result = subprocess.run([sys.executable, '-B', str(script), 'detect'], cwd=self.root,
                                env=env, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(output.read_text(encoding='utf-8'), 'full=true\n')
        self.assertNotIn('broken synthetic event', result.stdout)

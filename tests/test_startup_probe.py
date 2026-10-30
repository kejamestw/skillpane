"""Privacy and no-service boundaries of the optional developer startup probes."""
from pathlib import Path
import unittest

from launcher_diagnostics import LIMIT
from startup_probe import CASES, ENTRY_PREFIX, STEPS, command, make_sources, read_steps, synthetic_env
from test_catalog import fixture_root


class StartupProbeTests(unittest.TestCase):
    def setUp(self):
        self.base = fixture_root()
        self.err = self.base/'probe.stderr.txt'

    @staticmethod
    def lines(values=None):
        return ''.join(f'SKILLPANE_BOOT step={step} ms={value}\n'
                       for step, value in zip(STEPS, range(len(STEPS)) if values is None else values))

    def test_steps_ignore_unknown_raw_and_non_ascii_payloads(self):
        self.err.write_text('private-payload\nSKILLPANE_BOOT step=private-payload ms=3\n'
            'SKILLPANE_BOOT step=entry ms=０\nSKILLPANE_BOOT step=entry ms=0 extra\n' + self.lines(), encoding='utf-8')
        result = read_steps(self.err)
        self.assertEqual(result, dict(zip(STEPS, range(len(STEPS)))))
        self.assertNotIn('private-payload', str(result))

    def test_steps_reject_missing_duplicate_backward_and_huge_values(self):
        for text in (self.lines().replace('SKILLPANE_BOOT step=exit ms=6\n', ''),
                     self.lines() + 'SKILLPANE_BOOT step=exit ms=7\n',
                     self.lines([0, 1, 2, 1, 4, 5, 6]),
                     self.lines().replace('ms=6', 'ms=123456789')):
            with self.subTest(text_length=len(text)):
                self.err.write_text(text, encoding='utf-8')
                with self.assertRaisesRegex(ValueError, '^Incomplete or invalid startup steps.$'):
                    read_steps(self.err)

    def test_reader_is_bounded_and_missing_file_does_not_return_fake_timings(self):
        with self.assertRaises(OSError):
            read_steps(self.err)
        self.err.write_bytes(b'private-prefix' * LIMIT + b'\n' + self.lines().encode())
        self.assertEqual(read_steps(self.err)['exit'], 6)
        self.err.write_bytes(self.lines().encode() + b'x' * (LIMIT * 2))
        with self.assertRaises(ValueError):
            read_steps(self.err)

    def test_entry_layout_drift_fails_before_generating_executable_sources(self):
        for entry in ('', ENTRY_PREFIX + 'changed', ENTRY_PREFIX + "Write-SkillpaneStage 'start-enter'\nother",
                      ENTRY_PREFIX + "Write-SkillpaneStage 'start-enter'" * 2):
            with self.assertRaisesRegex(ValueError, '^Unexpected launcher entry layout.$'):
                make_sources(entry)

    def test_windows_crlf_checkout_preserves_the_same_generated_cases(self):
        entry = Path(__file__).resolve().parents[1].joinpath('Start.ps1').read_text(encoding='utf-8-sig')
        self.assertEqual(make_sources(entry), make_sources(entry.replace('\n', '\r\n')))

    def test_sources_return_before_retained_application_body(self):
        entry = Path(__file__).resolve().parents[1].joinpath('Start.ps1').read_text(encoding='utf-8-sig')
        sources = make_sources(entry)
        self.assertEqual(tuple(sources), CASES)
        for case, source in sources.items():
            with self.subTest(case=case):
                self.assertEqual(source.count('\nreturn\n'), 1)
                self.assertNotIn('Start-Process', source.split('\nreturn\n', 1)[0])
                self.assertLess(source.index('stage=start-enter elapsed_ms=0'), source.index("Write-BootStep 'module-ready'"))
                if case == 'entry-body-parse':
                    self.assertLess(source.index('\nreturn\n'), source.index('$launcherLock ='))
                else:
                    self.assertNotIn('$launcherLock =', source)
        self.assertIn('Import-Module Microsoft.PowerShell.Management', sources['header-import'])
        self.assertNotIn('Join-Path', sources['header-dotnet'])

    def test_environment_is_synthetic_allowlist_without_mutating_parent(self):
        original = {'PATH': 'synthetic-tools', 'SystemRoot': 'synthetic-system', 'GH_TOKEN': 'private-payload',
                    'USERPROFILE': 'private-home', 'PSModulePath': 'private-modules', 'PSExecutionPolicyPreference': 'AllSigned'}
        env = synthetic_env(self.base/'home', original)
        self.assertEqual(env['PATH'], 'synthetic-tools')
        self.assertEqual(env['SystemRoot'], 'synthetic-system')
        self.assertEqual(env['USERPROFILE'], str(self.base/'home'))
        self.assertNotIn('private', str(env))
        self.assertNotIn('PSExecutionPolicyPreference', env)
        self.assertEqual(original['USERPROFILE'], 'private-home')

    def test_policy_factor_is_process_argument_and_other_arguments_match(self):
        default = command('synthetic-shell', 'minimal-default', self.base/'case.ps1')
        bypass = command('synthetic-shell', 'minimal-bypass', self.base/'case.ps1')
        self.assertNotIn('-ExecutionPolicy', default)
        self.assertEqual(bypass[2:4], ['-ExecutionPolicy', 'Bypass'])
        self.assertEqual(default, bypass[:2] + bypass[4:])
        with self.assertRaises(ValueError):
            command('synthetic-shell', 'private-payload', self.base/'case.ps1')

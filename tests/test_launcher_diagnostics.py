"""Diagnostic safety and timeout regressions independent of the host OS."""
from contextlib import redirect_stdout
import io
import subprocess
import unittest
from unittest.mock import patch

from launcher_diagnostics import LIMIT, describe, invoke, read_events
from test_catalog import fixture_root


class LauncherDiagnosticTests(unittest.TestCase):
    def setUp(self):
        self.base = fixture_root()
        self.err = self.base / 'stderr.txt'
        self.out = self.base / 'stdout.txt'

    def test_parser_ignores_raw_output_unknown_labels_and_backward_clock(self):
        self.err.write_text('private-payload\n'
            'SKILLPANE_LAUNCHER stage=python-start-begin elapsed_ms=100\n'
            'SKILLPANE_LAUNCHER stage=private-payload elapsed_ms=101\n'
            'SKILLPANE_LAUNCHER stage=python-start-end elapsed_ms=99\n'
            'SKILLPANE_LAUNCHER stage=python-start-end elapsed_ms=120\n'
            'SKILLPANE_LAUNCHER stage=launcher-exit elapsed_ms=１２１\n'
            'SKILLPANE_LAUNCHER stage=launcher-exit elapsed_ms=121 trailing-payload\n', encoding='utf-8')
        self.assertEqual(read_events(self.err), [('python-start-begin', 100), ('python-start-end', 120)])

    def test_reader_bounds_tail_and_handles_missing_file(self):
        self.assertEqual(read_events(self.err), [])
        self.err.write_bytes(b'SKILLPANE_LAUNCHER stage=start-enter elapsed_ms=0\n' +
            b'x' * (LIMIT * 2) + b'\nSKILLPANE_LAUNCHER stage=listener-query-begin elapsed_ms=10\n')
        self.assertEqual(read_events(self.err), [('listener-query-begin', 10)])

    def test_summary_reports_pending_nested_query_after_cleanup(self):
        events = [('readiness-begin', 10), ('listener-query-begin', 15), ('launcher-exit', 60)]
        text = describe('Start', 'WindowsPowerShell', 100, 'timeout', events)
        self.assertIn('pending=listener-query', text)
        self.assertIn('last=launcher-exit', text)
        self.assertIn('total_ms=100', text)

    def test_summary_spans_and_missing_marker(self):
        text = describe('Start', 'WindowsPowerShell', 200, 'exit-0',
            [('listener-query-begin', 10), ('listener-query-end', 110)])
        self.assertIn('spans_ms=listener-query:100', text)
        text = describe('Stop', 'PowerShell7', 60000, 'timeout', [])
        self.assertIn('last=no-marker', text)
        self.assertIn('pending=none', text)

    def test_summary_rejects_untrusted_labels(self):
        for action, shell, outcome in [('payload', 'PowerShell7', 'exit-0'),
            ('Start', 'payload', 'exit-0'), ('Start', 'PowerShell7', 'payload')]:
            with self.assertRaises(ValueError):
                describe(action, shell, 1, outcome, [])

    def test_timeout_keeps_partial_events_without_echoing_command_or_raw_output(self):
        def expire(command, **kwargs):
            self.assertEqual(kwargs['timeout'], 60)
            kwargs['stderr'].write(b'private-payload\nSKILLPANE_LAUNCHER stage=python-start-begin elapsed_ms=500\n')
            kwargs['stderr'].flush()
            raise subprocess.TimeoutExpired(['private-command'], 60, output=b'private-output')
        console = io.StringIO()
        with patch('launcher_diagnostics.subprocess.run', side_effect=expire), redirect_stdout(console):
            with self.assertRaises(AssertionError) as error:
                invoke(['private-command'], cwd=self.base, env={}, out=self.out, err=self.err,
                       action='Start', shell='WindowsPowerShell', creationflags=0)
        combined = console.getvalue() + str(error.exception)
        self.assertIn('outcome=timeout', combined)
        self.assertIn('pending=python-start', combined)
        for value in ('private-command', 'private-output', 'private-payload'):
            self.assertNotIn(value, combined)
        self.assertIn(b'private-payload', self.err.read_bytes())

    def test_nonzero_exit_is_returned_with_safe_summary(self):
        def failed(command, **kwargs):
            kwargs['stdout'].write(b'private-output')
            return subprocess.CompletedProcess(command, 1)
        console = io.StringIO()
        with patch('launcher_diagnostics.subprocess.run', side_effect=failed), redirect_stdout(console):
            result = invoke(['private-command'], cwd=self.base, env={}, out=self.out, err=self.err,
                            action='Stop', shell='PowerShell7', creationflags=0)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, 'private-output')
        self.assertIn('outcome=exit-1', result.diagnostics)
        self.assertNotIn('private-', console.getvalue())

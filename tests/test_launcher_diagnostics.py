"""Diagnostic safety and timeout regressions independent of the host OS."""
from contextlib import redirect_stdout
import io
import subprocess
import sys
import unittest
from unittest.mock import patch

from launcher_diagnostics import LIMIT, describe, invoke, read_events
from test_catalog import fixture_root


class FakeProcess:
    def __init__(self, command, stdout, stderr, clock, *, code=0, finish=1,
                 stages=(), hang=False, kill_error=False):
        self.command, self.stdout, self.stderr, self.clock = command, stdout, stderr, clock
        self.code, self.finish, self.stages = code, finish, list(stages)
        self.hang, self.kill_error = hang, kill_error
        self.returncode = None
        self.killed = False

    def poll(self):
        while self.stages and self.clock[0] >= self.stages[0][0]:
            _, line = self.stages.pop(0)
            self.stderr.write(line)
            self.stderr.flush()
        if self.returncode is None and not self.hang and self.clock[0] >= self.finish:
            self.returncode = self.code
        return self.returncode

    def wait(self, timeout):
        if self.returncode is not None:
            return self.returncode
        self.clock[0] += min(timeout, 0.1)
        if self.poll() is None:
            raise subprocess.TimeoutExpired(['private-command'], timeout, output=b'private-output')
        return self.returncode

    def kill(self):
        self.killed = True
        if self.kill_error:
            raise OSError('private-cleanup-payload')
        self.returncode = -9


class LauncherDiagnosticTests(unittest.TestCase):
    def setUp(self):
        self.base = fixture_root()
        self.err = self.base / 'stderr.txt'
        self.out = self.base / 'stdout.txt'

    def run_fake(self, *, code=0, finish=1, stages=(), hang=False,
                 creation=0.2, kill_error=False, stdout=b''):
        clock = [0.0]
        processes = []
        def create(command, **kwargs):
            clock[0] += creation
            kwargs['stdout'].write(stdout)
            process = FakeProcess(command, kwargs['stdout'], kwargs['stderr'], clock,
                code=code, finish=finish, stages=stages, hang=hang, kill_error=kill_error)
            processes.append(process)
            return process
        console = io.StringIO()
        error = None
        result = None
        with patch('launcher_diagnostics.time.monotonic', side_effect=lambda: clock[0]), \
                patch('launcher_diagnostics.subprocess.Popen', side_effect=create), redirect_stdout(console):
            try:
                result = invoke(['private-command'], cwd=self.base, env={}, out=self.out, err=self.err,
                                action='Start', shell='WindowsPowerShell', creationflags=0)
            except AssertionError as caught:
                error = caught
        return result, error, console.getvalue(), processes, clock[0]

    @staticmethod
    def fields(text):
        return dict(field.split('=', 1) for field in text.split() if '=' in field)

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
        _, error, console, processes, elapsed = self.run_fake(hang=True,
            stages=[(1, b'private-payload\nSKILLPANE_LAUNCHER stage=python-start-begin elapsed_ms=500\n')])
        self.assertIsInstance(error, AssertionError)
        self.assertIsNone(error.__cause__)
        self.assertTrue(error.__suppress_context__)
        combined = console + str(error)
        self.assertIn('outcome=timeout', combined)
        self.assertIn('pending=python-start', combined)
        for value in ('private-command', 'private-output', 'private-payload'):
            self.assertNotIn(value, combined)
        self.assertIn(b'private-payload', self.err.read_bytes())
        self.assertTrue(processes[0].killed)
        self.assertAlmostEqual(elapsed, 60)

    def test_nonzero_exit_is_returned_with_safe_summary(self):
        result, error, console, processes, _ = self.run_fake(code=1, stdout=b'private-output')
        self.assertIsNone(error)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, 'private-output')
        self.assertIn('outcome=exit-1', result.diagnostics)
        self.assertNotIn('private-', console)
        self.assertIn('first_stage_seen_ms=-1', console)
        self.assertIn('exit_stage_seen_ms=-1', console)
        self.assertFalse(processes[0].killed)

    def test_observer_separates_creation_script_markers_and_process_end(self):
        result, error, console, processes, _ = self.run_fake(creation=2, finish=5, stages=[
            (3, b'SKILLPANE_LAUNCHER stage=start-enter elapsed_ms=0\n'),
            (3.5, b'SKILLPANE_LAUNCHER stage=launcher-exit elapsed_ms=500\n')])
        self.assertIsNone(error)
        self.assertEqual(result.returncode, 0)
        fields = self.fields(console)
        self.assertEqual(int(fields['spawn_ms']), 2000)
        self.assertTrue(2999 <= int(fields['first_stage_seen_ms']) <= 3100)
        self.assertTrue(3499 <= int(fields['exit_stage_seen_ms']) <= 3600)
        self.assertTrue(4999 <= int(fields['process_end_ms']) <= 5100)
        self.assertEqual(int(fields['script_elapsed_ms']), 500)
        self.assertFalse(processes[0].killed)

    def test_slow_creation_does_not_receive_another_sixty_seconds(self):
        for hang in (True, False):
            with self.subTest(still_running=hang):
                _, error, console, processes, elapsed = self.run_fake(creation=65, hang=hang)
                self.assertIsInstance(error, AssertionError)
                self.assertEqual(elapsed, 65)
                self.assertEqual(processes[0].killed, hang)
                self.assertIn('outcome=timeout', console)
                self.assertIn('spawn_ms=65000', console)

    def test_spawn_error_is_reported_without_raw_error(self):
        console = io.StringIO()
        with patch('launcher_diagnostics.subprocess.Popen', side_effect=OSError('private-spawn-payload')), redirect_stdout(console):
            with self.assertRaises(AssertionError) as error:
                invoke(['private-command'], cwd=self.base, env={}, out=self.out, err=self.err,
                       action='Stop', shell='PowerShell7', creationflags=0)
        self.assertIn('outcome=spawn-error', console.getvalue())
        self.assertNotIn('private-', console.getvalue() + str(error.exception))
        self.assertTrue(error.exception.__suppress_context__)

    def test_cleanup_error_is_a_failure_without_raw_error(self):
        _, error, console, processes, _ = self.run_fake(creation=60, hang=True, kill_error=True)
        self.assertIsInstance(error, AssertionError)
        self.assertTrue(processes[0].killed)
        self.assertIn('outcome=cleanup-error', console)
        self.assertNotIn('private-', console + str(error))

    def test_real_child_markers_are_observed_without_echoing_its_output(self):
        code = ("import sys,time;sys.stderr.write('private-payload\\nSKILLPANE_LAUNCHER stage=start-enter elapsed_ms=0\\n');"
                "sys.stderr.flush();time.sleep(0.25);sys.stderr.write('SKILLPANE_LAUNCHER stage=launcher-exit elapsed_ms=250\\n');sys.stderr.flush()")
        console = io.StringIO()
        with redirect_stdout(console):
            result = invoke([sys.executable, '-B', '-c', code], cwd=self.base, env={},
                out=self.out, err=self.err, action='Start', shell='WindowsPowerShell',
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        self.assertEqual(result.returncode, 0)
        fields = self.fields(console.getvalue())
        self.assertGreaterEqual(int(fields['spawn_ms']), 0)
        self.assertGreaterEqual(int(fields['first_stage_seen_ms']), int(fields['spawn_ms']))
        self.assertGreaterEqual(int(fields['exit_stage_seen_ms']), int(fields['first_stage_seen_ms']))
        self.assertGreaterEqual(int(fields['process_end_ms']), int(fields['exit_stage_seen_ms']))
        self.assertEqual(int(fields['script_elapsed_ms']), 250)
        self.assertNotIn('private-', console.getvalue())

    def test_untrusted_timing_fields_are_rejected(self):
        good = dict(spawn_ms=0, first_stage_seen_ms=-1, exit_stage_seen_ms=-1, process_end_ms=1)
        for timings in (dict(good, payload=1), dict(good, spawn_ms='private-payload'),
                        dict(good, spawn_ms=-2), dict(good, spawn_ms=True)):
            with self.assertRaises(ValueError):
                describe('Start', 'PowerShell7', 1, 'exit-0', [], timings)

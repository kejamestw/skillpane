"""Bounded, allowlisted launcher summaries for synthetic tests only."""
from pathlib import Path
import re
import subprocess
import time

PHASES = {'lock-open', 'record-read', 'process-check', 'process-metadata',
          'listener-query', 'python-start', 'record-write', 'health-wait',
          'readiness', 'stop-process'}
STAGES = {'start-enter', 'stop-enter', 'launcher-exit'} | {
    phase + suffix for phase in PHASES for suffix in ('-begin', '-end')}
LINE = re.compile(r'SKILLPANE_LAUNCHER stage=([a-z-]+) elapsed_ms=([0-9]{1,8})', re.ASCII)
LIMIT = 16 * 1024
POLL_SECONDS = 0.1
TIMEOUT_SECONDS = 60
TIMING_FIELDS = ('spawn_ms', 'first_stage_seen_ms', 'exit_stage_seen_ms', 'process_end_ms')


def read_events(path):
    try:
        with Path(path).open('rb') as stream:
            stream.seek(0, 2)
            stream.seek(max(0, stream.tell() - LIMIT))
            text = stream.read(LIMIT).decode('utf-8', errors='replace')
    except OSError:
        return []
    events = []
    previous = -1
    for line in text.splitlines():
        match = LINE.fullmatch(line)
        if not match or match[1] not in STAGES:
            continue
        milliseconds = int(match[2])
        if milliseconds < previous:
            continue
        previous = milliseconds
        events.append((match[1], milliseconds))
    return events[-128:]


def describe(action, shell, milliseconds, outcome, events, timings=None):
    if action not in ('Start', 'Stop', 'Probe') or shell not in ('WindowsPowerShell', 'PowerShell7'):
        raise ValueError('Unknown diagnostic label.')
    if not re.fullmatch(r'timeout|exit--?[0-9]+|spawn-error|cleanup-error', outcome, flags=re.ASCII):
        raise ValueError('Unknown diagnostic outcome.')
    pending, spans = {}, []
    for stage, elapsed in events:
        if stage.endswith('-begin'):
            pending[stage[:-6]] = elapsed
        elif stage.endswith('-end') and stage[:-4] in pending:
            phase = stage[:-4]
            spans.append((phase, elapsed - pending.pop(phase)))
    active = next(reversed(pending), 'none')
    last = events[-1][0] if events else 'no-marker'
    span_text = ','.join(f'{phase}:{elapsed}' for phase, elapsed in spans) or 'none'
    timings = dict.fromkeys(TIMING_FIELDS, -1) if timings is None else timings
    if (set(timings) != set(TIMING_FIELDS)
            or any(type(value) is not int or value < -1 for value in timings.values())):
        raise ValueError('Invalid diagnostic timing.')
    timing_text = ' '.join(f'{name}={timings[name]}' for name in TIMING_FIELDS)
    script_ms = events[-1][1] if events else -1
    return (f'launcher_diag action={action} shell={shell} outcome={outcome} '
            f'total_ms={max(0, int(milliseconds))} last={last} pending={active} '
            f'spans_ms={span_text} {timing_text} script_elapsed_ms={script_ms}')


def invoke(command, *, cwd, env, out, err, action, shell, creationflags):
    start = time.monotonic()
    deadline = start + TIMEOUT_SECONDS
    timings = dict.fromkeys(TIMING_FIELDS, -1)
    process = None
    outcome = 'spawn-error'

    def observe():
        events = read_events(err)
        elapsed = max(0, int((time.monotonic() - start) * 1000))
        if events and timings['first_stage_seen_ms'] == -1:
            timings['first_stage_seen_ms'] = elapsed
        if any(stage == 'launcher-exit' for stage, _ in events) and timings['exit_stage_seen_ms'] == -1:
            timings['exit_stage_seen_ms'] = elapsed

    try:
        with out.open('wb') as stdout, err.open('wb') as stderr:
            # Files still avoid inherited pipe handles from background services.
            # Measure CreateProcess separately; never relax the overall budget.
            process = subprocess.Popen(command, cwd=cwd, env=env,
                stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr,
                creationflags=creationflags)
            timings['spawn_ms'] = max(0, int((time.monotonic() - start) * 1000))
            while True:
                observe()
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    outcome = 'timeout'
                    break
                returncode = process.poll()
                if returncode is not None:
                    timings['process_end_ms'] = max(0, int((time.monotonic() - start) * 1000))
                    outcome = f'exit-{returncode}'
                    break
                try:
                    process.wait(timeout=min(POLL_SECONDS, remaining))
                except subprocess.TimeoutExpired:
                    pass
    except OSError:
        outcome = 'spawn-error'
    finally:
        # Only terminate the launcher Popen handle owned by this invocation.
        # Never find or kill a PID from a server record or from captured output.
        if process is not None and process.poll() is None:
            try:
                process.kill()
                process.wait(timeout=10)
            except (OSError, subprocess.TimeoutExpired):
                outcome = 'cleanup-error'
        summary = describe(action, shell, (time.monotonic() - start) * 1000,
                           outcome, read_events(err), timings)
        print(summary, flush=True)
    if outcome == 'timeout':
        # Do not repeat TimeoutExpired's full command, paths or captured output.
        raise AssertionError('Launcher exceeded the 60-second limit; ' + summary) from None
    if outcome in ('spawn-error', 'cleanup-error'):
        raise AssertionError('Launcher process could not be run or cleaned up; ' + summary) from None
    result = subprocess.CompletedProcess(command, process.returncode,
        out.read_text(encoding='utf-8', errors='replace'),
        err.read_text(encoding='utf-8', errors='replace'))
    result.diagnostics = summary
    return result

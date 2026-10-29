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


def describe(action, shell, milliseconds, outcome, events):
    if action not in ('Start', 'Stop') or shell not in ('WindowsPowerShell', 'PowerShell7'):
        raise ValueError('Unknown diagnostic label.')
    if not re.fullmatch(r'timeout|exit--?[0-9]+|spawn-error', outcome, flags=re.ASCII):
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
    return (f'launcher_diag action={action} shell={shell} outcome={outcome} '
            f'total_ms={max(0, int(milliseconds))} last={last} pending={active} '
            f'spans_ms={span_text}')


def invoke(command, *, cwd, env, out, err, action, shell, creationflags):
    start = time.monotonic()
    timed_out = False
    outcome = 'spawn-error'
    try:
        with out.open('wb') as stdout, err.open('wb') as stderr:
            try:
                completed = subprocess.run(command, cwd=cwd, env=env,
                    stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr,
                    creationflags=creationflags, timeout=60)
                outcome = f'exit-{completed.returncode}'
            except subprocess.TimeoutExpired:
                timed_out = True
                outcome = 'timeout'
    finally:
        summary = describe(action, shell, (time.monotonic() - start) * 1000,
                           outcome, read_events(err))
        print(summary, flush=True)
    if timed_out:
        # Do not repeat TimeoutExpired's full command, paths or captured output.
        raise AssertionError('Launcher exceeded the 60-second limit; ' + summary) from None
    result = subprocess.CompletedProcess(completed.args, completed.returncode,
        out.read_text(encoding='utf-8', errors='replace'),
        err.read_text(encoding='utf-8', errors='replace'))
    result.diagnostics = summary
    return result

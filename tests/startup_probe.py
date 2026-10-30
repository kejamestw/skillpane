"""Developer-only startup probes; generated scripts return before any app operation."""
import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
from uuid import uuid4

from launcher_diagnostics import LIMIT, invoke

ROOT = Path(__file__).resolve().parents[1]
CASES = ('minimal-default', 'minimal-bypass', 'header-join', 'header-dotnet',
         'header-qualified', 'header-import', 'entry-body-parse')
STEPS = ('entry', 'preferences-ready', 'module-ready', 'runtime-path-ready',
         'shared-path-ready', 'shared-ready', 'exit')
BOOT_LINE = re.compile(r'SKILLPANE_BOOT step=([a-z-]+) ms=([0-9]{1,8})', re.ASCII)
ENV_KEYS = {'PATH', 'SYSTEMROOT', 'WINDIR', 'TEMP', 'TMP', 'COMSPEC', 'SYSTEMDRIVE', 'LANG', 'LC_ALL'}
HEADER = '''param([switch]$NoBrowser, [ValidateRange(1,65535)][int]$Port=50001)
$bootClock=[Diagnostics.Stopwatch]::StartNew()
function Write-BootStep([string]$Step) {
    [Console]::Error.WriteLine(('SKILLPANE_BOOT step={0} ms={1}' -f $Step,$bootClock.ElapsedMilliseconds))
}
Write-BootStep 'entry'
[Console]::Error.WriteLine('SKILLPANE_LAUNCHER stage=start-enter elapsed_ms=0')
$ErrorActionPreference='Stop'
$appUrl="http://127.0.0.1:$Port"
Write-BootStep 'preferences-ready'
__MODULE__
Write-BootStep 'module-ready'
__RUNTIME__
Write-BootStep 'runtime-path-ready'
__SHARED__
Write-BootStep 'shared-path-ready'
. $sharedPath
Write-BootStep 'shared-ready'
Write-SkillpaneStage 'start-enter'
Write-SkillpaneStage 'launcher-exit'
Write-BootStep 'exit'
return
'''
ENTRY_PREFIX = '''param([switch]$NoBrowser, [ValidateRange(1,65535)][int]$Port = 8766)
$ErrorActionPreference = 'Stop'
$appUrl = "http://127.0.0.1:$Port"
$runtimePath = Microsoft.PowerShell.Management\\Join-Path $PSScriptRoot '.runtime'
. (Join-Path $PSScriptRoot 'scripts\\Launcher.ps1')
'''


def make_sources(entry):
    entry = entry.replace('\r\n', '\n')
    marker = "Write-SkillpaneStage 'start-enter'"
    if entry.count(marker) != 1:
        raise ValueError('Unexpected launcher entry layout.')
    prefix, rest = entry.split(marker, 1)
    if prefix != ENTRY_PREFIX or not rest.lstrip().startswith('$launcherLock ='):
        raise ValueError('Unexpected launcher entry layout.')
    sources = {}
    for case in CASES:
        module = ''
        runtime = "$runtimePath=Join-Path $PSScriptRoot '.runtime'"
        shared = "$sharedPath=Join-Path $PSScriptRoot 'scripts\\Launcher.ps1'"
        if case.startswith('minimal') or case == 'header-dotnet':
            runtime = '' if case.startswith('minimal') else "$runtimePath=[IO.Path]::Combine($PSScriptRoot,'.runtime')"
            shared = "$sharedPath=[IO.Path]::Combine($PSScriptRoot,'scripts','Launcher.ps1')"
        if case in ('header-qualified', 'entry-body-parse'):
            runtime = runtime.replace('Join-Path', 'Microsoft.PowerShell.Management\\Join-Path')
        if case == 'header-qualified':
            shared = shared.replace('Join-Path', 'Microsoft.PowerShell.Management\\Join-Path')
        if case == 'header-import':
            module = 'Import-Module Microsoft.PowerShell.Management -ErrorAction Stop'
        source = HEADER.replace('__MODULE__', module).replace('__RUNTIME__', runtime).replace('__SHARED__', shared)
        if case == 'entry-body-parse':
            # Retain the original remainder for parsing only, after top-level return.
            source += rest
        sources[case] = source
    return sources


def read_steps(path):
    with Path(path).open('rb') as stream:
        stream.seek(0, 2)
        stream.seek(max(0, stream.tell() - LIMIT))
        text = stream.read(LIMIT).decode('utf-8', errors='replace')
    events = []
    for line in text.splitlines():
        match = BOOT_LINE.fullmatch(line)
        if match and match[1] in STEPS:
            events.append((match[1], int(match[2])))
    if tuple(stage for stage, _ in events) != STEPS or any(b[1] < a[1] for a, b in zip(events, events[1:])):
        raise ValueError('Incomplete or invalid startup steps.')
    return dict(events)


def synthetic_env(home, original):
    env = {key: value for key, value in original.items() if key.upper() in ENV_KEYS}
    env.update(HOME=str(home), USERPROFILE=str(home), PYTHONUTF8='1', PYTHONDONTWRITEBYTECODE='1',
               SKILLPANE_LAUNCHER_DIAGNOSTICS='1')
    return env


def command(shell, case, path):
    if case not in CASES:
        raise ValueError('Unknown startup case.')
    args = [shell, '-NoProfile']
    if case != 'minimal-default':
        args += ['-ExecutionPolicy', 'Bypass']
    return args + ['-File', str(path), '-Port', '50001', '-NoBrowser']


def run(selected):
    shells = {'windows-powershell': ('WindowsPowerShell', shutil.which('powershell.exe')),
              'powershell7': ('PowerShell7', shutil.which('pwsh'))}
    chosen = tuple(shells) if selected == 'both' else (selected,)
    if os.name != 'nt' or any(not shells[key][1] for key in chosen):
        raise ValueError('Requested Windows shell is unavailable.')
    entry_path, shared_path = ROOT/'Start.ps1', ROOT/'scripts/Launcher.ps1'
    entry_bytes, shared_bytes = entry_path.read_bytes(), shared_path.read_bytes()
    sources = make_sources(entry_bytes.decode('utf-8-sig'))
    base = ROOT/'.runtime/startup-probes'/uuid4().hex
    bundle, home = base/'isolated bundle 測試', base/'synthetic-home'
    (bundle/'scripts').mkdir(parents=True)
    home.mkdir()
    (bundle/'scripts/Launcher.ps1').write_bytes(shared_bytes)
    for case, source in sources.items():
        (bundle/(case+'.ps1')).write_text(source, encoding='utf-8')
    env = synthetic_env(home, os.environ)
    count = 0
    try:
        for key in chosen:
            label, shell = shells[key]
            for case in CASES:
                err = base/f'{count}.stderr.txt'
                result = invoke(command(shell, case, bundle/(case+'.ps1')), cwd=bundle, env=env,
                    out=base/f'{count}.stdout.txt', err=err, action='Probe', shell=label,
                    creationflags=subprocess.CREATE_NO_WINDOW)
                if result.returncode or result.stdout:
                    raise ValueError('Startup case failed.')
                steps = read_steps(err)
                timing = dict(field.split('=', 1) for field in result.diagnostics.split() if '=' in field)
                safe = {'case': case, 'shell': label, 'steps_ms': steps}
                safe.update({name: int(timing[name]) for name in ('total_ms', 'spawn_ms', 'first_stage_seen_ms',
                    'exit_stage_seen_ms', 'process_end_ms', 'script_elapsed_ms')})
                print('startup_probe ' + json.dumps(safe, separators=(',', ':')), flush=True)
                count += 1
    finally:
        if (sha256(entry_path.read_bytes()).digest() != sha256(entry_bytes).digest()
                or sha256(shared_path.read_bytes()).digest() != sha256(shared_bytes).digest()):
            raise ValueError('Source fingerprint changed.') from None
        if (bundle/'.runtime').exists() or (bundle/'.data').exists():
            raise ValueError('Unexpected app state in startup probe.') from None
    print(f'startup_probe_complete records={count} service_started=false', flush=True)


def main():
    parser = argparse.ArgumentParser(description='Synthetic developer startup diagnosis; no application is started.')
    parser.add_argument('--shell', choices=('both', 'windows-powershell', 'powershell7'), default='both')
    args = parser.parse_args()
    try:
        run(args.shell)
    except (AssertionError, OSError, ValueError):
        raise SystemExit('Startup diagnosis failed; raw output is retained only in the ignored synthetic fixture.') from None


if __name__ == '__main__':
    main()

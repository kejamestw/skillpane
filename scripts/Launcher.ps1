# Shared by Start.ps1 and Stop.ps1; Windows PowerShell 5.1 and PowerShell 7.
# Load only bundled modules; do not rediscover every installed module when the
# first JSON, HTTP or CIM command is encountered. Missing modules must fail closed.
Import-Module ([IO.Path]::Combine($PSHOME, 'Modules', 'Microsoft.PowerShell.Utility', 'Microsoft.PowerShell.Utility.psd1')) -ErrorAction Stop
Import-Module ([IO.Path]::Combine($PSHOME, 'Modules', 'CimCmdlets', 'CimCmdlets.psd1')) -ErrorAction Stop

$script:SkillpaneLauncherClock = $null
if ($env:SKILLPANE_LAUNCHER_DIAGNOSTICS -eq '1') {
    $script:SkillpaneLauncherClock = [Diagnostics.Stopwatch]::StartNew()
}

function Write-SkillpaneStage([string]$Stage) {
    if (-not $script:SkillpaneLauncherClock) { return }
    # Fixed labels only: never log paths, PIDs, arguments, environment or errors.
    $allowed = @('start-enter', 'stop-enter', 'launcher-exit')
    foreach ($phase in @('lock-open', 'record-read', 'process-check', 'process-metadata',
                         'listener-query', 'python-start', 'record-write', 'health-wait',
                         'readiness', 'stop-process')) {
        $allowed += "$phase-begin", "$phase-end"
    }
    if ($Stage -notin $allowed) { return }
    try {
        [Console]::Error.WriteLine(('SKILLPANE_LAUNCHER stage={0} elapsed_ms={1}' -f $Stage, $script:SkillpaneLauncherClock.ElapsedMilliseconds))
    } catch { } # Diagnostic output must not affect launcher decisions.
}

function Get-SkillpaneStartTime($Value) {
    # PowerShell 7 converts ISO JSON strings to DateTime; 5.1 keeps strings.
    if ($Value -is [datetime] -and $Value.Kind -ne [DateTimeKind]::Unspecified) { return $Value.ToUniversalTime() }
    if ($Value -is [string] -and $Value -match '(?:Z|[+-]\d{2}:\d{2})$') {
        try { return [DateTimeOffset]::Parse($Value).UtcDateTime } catch {}
    }
    throw 'Invalid process creation time.'
}

function Open-SkillpaneLock($RuntimePath) {
    Write-SkillpaneStage 'lock-open-begin'
    New-Item -ItemType Directory -Path $RuntimePath -Force | Out-Null
    try {
        $handle = [IO.File]::Open((Join-Path $RuntimePath 'launcher.lock'), 'OpenOrCreate', 'ReadWrite', 'None')
        Write-SkillpaneStage 'lock-open-end'
        return $handle
    } catch { throw 'Another launcher operation is running, or the runtime directory is unavailable.' }
}

function Read-SkillpaneRecord($StatePath, $Root) {
    if (-not (Test-Path -LiteralPath $StatePath)) { return $null }
    try { $record = Get-Content -LiteralPath $StatePath -Raw -Encoding UTF8 | ConvertFrom-Json } catch {
        throw 'Invalid launcher record; refusing to replace it or stop an unverified process.'
    }
    if ($record.Root -isnot [string] -or [IO.Path]::GetFullPath($record.Root) -ne $Root -or
        ($record.Pid -isnot [int] -and $record.Pid -isnot [long]) -or $record.Pid -le 0) {
        throw 'Launcher record identity is invalid or belongs to another checkout.'
    }
    [void](Get-SkillpaneStartTime $record.StartedUtc)
    if ($record.RecordVersion -ne 1) {
        # Old launchers did not put the checkout in the process command line.
        if (Get-Process -Id $record.Pid -ErrorAction SilentlyContinue) {
            throw 'Legacy or unsupported launcher record. Stop with the previous launcher before upgrading.'
        }
        return $null
    }
    if (($record.Port -isnot [int] -and $record.Port -isnot [long]) -or $record.Port -lt 1 -or $record.Port -gt 65535 -or
        $record.PythonPath -isnot [string]) { throw 'Invalid launcher port or interpreter record.' }
    return $record
}

function Get-SkillpaneProcess($Record, $Root) {
    if (-not $Record) { return $null }
    $managed = Get-Process -Id $Record.Pid -ErrorAction SilentlyContinue
    if (-not $managed) { return $null }
    try {
        # Pin a process handle before checking identity; never kill by a bare PID.
        [void]$managed.Handle
        $recordedTime = Get-SkillpaneStartTime $Record.StartedUtc
        if ($managed.StartTime.ToUniversalTime().Ticks -ne $recordedTime.Ticks) {
            throw 'PID was reused or the recorded creation time changed; refusing this process.'
        }
        Write-SkillpaneStage 'process-metadata-begin'
        $metadata = Get-CimInstance Win32_Process -Filter "ProcessId = $($Record.Pid)" -ErrorAction Stop
        Write-SkillpaneStage 'process-metadata-end'
        $entryPath = Join-Path $Root 'scripts\launcher_entry.py'
        $pythonPath = [IO.Path]::GetFullPath($Record.PythonPath)
        $pattern = '^\s*(?:"' + [regex]::Escape($pythonPath) + '"|' + [regex]::Escape($pythonPath) +
            ')\s+-B\s+-u\s+"' + [regex]::Escape($entryPath) + '"\s+--port\s+' + $Record.Port + '\s*$'
        if (-not $metadata -or $metadata.ExecutablePath -ne $pythonPath -or
            $metadata.ExecutablePath -notmatch 'python(?:w)?\.exe$' -or
            $metadata.CommandLine -notmatch $pattern -or $managed.HasExited) {
            throw 'Process executable or checkout command line does not match the launcher record.'
        }
        return $managed
    } catch { $managed.Dispose(); throw }
}

function Get-SkillpaneListeners([ValidateRange(1,65535)][int]$Port) {
    # Query failures must stop the operation; they are not proof that a port is free.
    Write-SkillpaneStage 'listener-query-begin'
    # Same Windows TCP provider; filter at the provider instead of enumerating
    # every listener through NetTCPIP. State 2 is Listen. A successful query
    # with no matches is empty; provider errors still propagate and stop startup.
    $listeners = @(Get-CimInstance -Namespace root/StandardCimv2 -ClassName MSFT_NetTCPConnection -Filter "LocalPort = $Port AND State = 2" -ErrorAction Stop)
    Write-SkillpaneStage 'listener-query-end'
    return $listeners
}

function Assert-SkillpaneReady($Managed, $Port) {
    Write-SkillpaneStage 'readiness-begin'
    $listeners = @(Get-SkillpaneListeners $Port | Where-Object { $_.LocalAddress -eq '127.0.0.1' })
    if ($listeners.Count -ne 1 -or $listeners[0].OwningProcess -ne $Managed.Id) {
        throw 'The listening socket does not belong to the recorded Skillpane process.'
    }
    $health = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/health" -TimeoutSec 2 -UseBasicParsing
    if ($health.app -ne 'skillpane' -or $health.skill_files_readonly -ne $true) {
        throw 'The recorded process did not return the expected health response.'
    }
    Write-SkillpaneStage 'readiness-end'
}

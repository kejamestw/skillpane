param([switch]$NoBrowser, [ValidateRange(1,65535)][int]$Port = 8766)
$ErrorActionPreference = 'Stop'
$appUrl = "http://127.0.0.1:$Port"
$runtimePath = Join-Path $PSScriptRoot '.runtime'
. (Join-Path $PSScriptRoot 'scripts\Launcher.ps1')
$launcherLock = Open-SkillpaneLock $runtimePath
$managed = $null
try {
    $statePath = Join-Path $runtimePath 'server.json'
    $record = Read-SkillpaneRecord $statePath $PSScriptRoot
    $managed = Get-SkillpaneProcess $record $PSScriptRoot
    if ($managed) {
        if ($record.Port -ne $Port) { throw 'This checkout is already running on another port. Stop it before changing ports.' }
        Assert-SkillpaneReady $managed $Port
    } else {
        if (@(Get-SkillpaneListeners $Port).Count) { throw 'Requested port is occupied; no existing service was changed.' }
        $pythonPath = $null
        if ($env:SKILLPANE_PYTHON) {
            if (-not (Test-Path -LiteralPath $env:SKILLPANE_PYTHON -PathType Leaf)) { throw 'SKILLPANE_PYTHON is not an executable file.' }
            $pythonPath = $env:SKILLPANE_PYTHON
        } else {
            $bundledPython = Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
            if (Test-Path -LiteralPath $bundledPython -PathType Leaf) { $pythonPath = $bundledPython }
            else {
                $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
                if ($pythonCommand -and $pythonCommand.Source -notlike '*WindowsApps*') { $pythonPath = $pythonCommand.Source }
            }
        }
        if (-not $pythonPath) { throw 'Python 3.10+ is required. Install Python or set SKILLPANE_PYTHON.' }
        $pythonPath = [IO.Path]::GetFullPath($pythonPath)
        if ($pythonPath -notmatch 'python(?:w)?\.exe$') { throw 'The launcher requires a Python executable.' }
        $entryPath = Join-Path $PSScriptRoot 'scripts\launcher_entry.py'
        $arguments = '-B -u "' + $entryPath + '" --port ' + $Port
        $managed = Start-Process -FilePath $pythonPath -ArgumentList $arguments -WorkingDirectory $PSScriptRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $runtimePath 'stdout.log') -RedirectStandardError (Join-Path $runtimePath 'stderr.log') -PassThru
        try {
            [void]$managed.Handle
            @{RecordVersion=1;Pid=$managed.Id;Root=$PSScriptRoot;Port=$Port;PythonPath=$pythonPath;StartedUtc=$managed.StartTime.ToUniversalTime().ToString('o')} | ConvertTo-Json | Set-Content -LiteralPath $statePath -Encoding UTF8
            $ready = $false
            for ($attempt=0; $attempt -lt 40; $attempt++) {
                $managed.Refresh()
                if ($managed.HasExited) { throw 'Skillpane exited. See .runtime/stderr.log.' }
                try {
                    $health = Invoke-RestMethod -Uri "$appUrl/api/health" -TimeoutSec 2 -UseBasicParsing
                    if ($health.app -eq 'skillpane' -and $health.skill_files_readonly -eq $true) { $ready = $true; break }
                } catch { $ready = $false }
                Start-Sleep -Milliseconds 300
            }
            if (-not $ready) { throw 'Skillpane did not become ready.' }
            Assert-SkillpaneReady $managed $Port
        } catch {
            if (-not $managed.HasExited) { $managed.Kill(); [void]$managed.WaitForExit(5000) }
            throw
        }
    }
    Write-Output "Skillpane is ready: $appUrl"
    if (-not $NoBrowser) { Start-Process $appUrl -WindowStyle Hidden }
} finally {
    if ($managed) { $managed.Dispose() }
    $launcherLock.Dispose()
}

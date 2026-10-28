param([switch]$NoBrowser)
$ErrorActionPreference = 'Stop'
$appUrl = 'http://127.0.0.1:8766'
$runtimePath = Join-Path $PSScriptRoot '.runtime'
$pythonCandidates = @($env:SKILLPANE_PYTHON, (Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'))
$pythonPath = $pythonCandidates | Where-Object { $_ -and (Test-Path -LiteralPath $_) } | Select-Object -First 1
if (-not $pythonPath) {
    $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
    if ($pythonCommand -and $pythonCommand.Source -notlike '*WindowsApps*') { $pythonPath = $pythonCommand.Source }
}
if (-not $pythonPath) { throw 'Python 3.10+ is required. Install Python or set SKILLPANE_PYTHON to its executable path.' }
$health = $null
try { $health = Invoke-RestMethod -Uri "$appUrl/api/health" -TimeoutSec 2 } catch {}
if ($health -and $health.app -ne 'skillpane') { throw 'Port 8766 belongs to another application.' }
if (-not $health) {
    New-Item -ItemType Directory -Path $runtimePath -Force | Out-Null
    $process = Start-Process -FilePath $pythonPath -ArgumentList '-B -u -m skillpane --port 8766' -WorkingDirectory $PSScriptRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $runtimePath 'stdout.log') -RedirectStandardError (Join-Path $runtimePath 'stderr.log') -PassThru
    @{Pid=$process.Id;Root=$PSScriptRoot;StartedUtc=$process.StartTime.ToUniversalTime().ToString('o')} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $runtimePath 'server.json') -Encoding UTF8
    for ($attempt=0; $attempt -lt 40; $attempt++) {
        Start-Sleep -Milliseconds 300
        try { $health = Invoke-RestMethod -Uri "$appUrl/api/health" -TimeoutSec 2; break } catch {}
        if ($process.HasExited) { throw 'Skillpane exited. See .runtime/stderr.log.' }
    }
    if (-not $health -or $health.app -ne 'skillpane') { throw 'Skillpane did not become ready.' }
}
Write-Output "Skillpane is ready: $appUrl"
if (-not $NoBrowser) { Start-Process $appUrl -WindowStyle Hidden }

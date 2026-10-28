$ErrorActionPreference = 'Stop'
$statePath = Join-Path $PSScriptRoot '.runtime\server.json'
if (-not (Test-Path -LiteralPath $statePath)) { Write-Output 'No recorded Skillpane process.'; exit 0 }
$state = Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json
$serverProcess = Get-CimInstance Win32_Process -Filter "ProcessId = $([int]$state.Pid)"
if (-not $serverProcess) { Write-Output 'Skillpane is already stopped.'; exit 0 }
if ($serverProcess.CommandLine -notlike '*-m skillpane --port 8766*') { throw 'PID belongs to another process; refusing to stop it.' }
if ($serverProcess.ExecutablePath -notmatch 'python(?:w)?\.exe$') { throw 'The recorded process is not Python.' }
$recordedStart = ([datetime]$state.StartedUtc).ToUniversalTime()
if ([math]::Abs(($serverProcess.CreationDate.ToUniversalTime() - $recordedStart).TotalSeconds) -gt 1) { throw 'PID was reused; refusing to stop another process.' }
Stop-Process -Id ([int]$state.Pid)
Write-Output 'Skillpane stopped.'

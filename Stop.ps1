param([ValidateRange(1,65535)][int]$Port = 8766)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'scripts\Launcher.ps1')
$statePath = Join-Path $PSScriptRoot '.runtime\server.json'
if (-not (Test-Path -LiteralPath $statePath)) { Write-Output 'No recorded Skillpane process.'; exit 0 }
$launcherLock = Open-SkillpaneLock (Split-Path -Parent $statePath)
$managed = $null
try {
    $record = Read-SkillpaneRecord $statePath $PSScriptRoot
    if ($record -and $record.Port -ne $Port) { throw 'Requested port does not match the launcher record; refusing to stop it.' }
    $managed = Get-SkillpaneProcess $record $PSScriptRoot
    if (-not $managed) { Write-Output 'Skillpane is already stopped.'; exit 0 }
    $managed.Kill()
    if (-not $managed.WaitForExit(5000)) { throw 'Skillpane has not stopped yet.' }
    Write-Output 'Skillpane stopped.'
} finally {
    if ($managed) { $managed.Dispose() }
    $launcherLock.Dispose()
}

param([ValidateRange(1,65535)][int]$Port = 8766)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'scripts\Launcher.ps1')
Write-SkillpaneStage 'stop-enter'
$statePath = Join-Path $PSScriptRoot '.runtime\server.json'
if (-not (Test-Path -LiteralPath $statePath)) { Write-Output 'No recorded Skillpane process.'; exit 0 }
$launcherLock = Open-SkillpaneLock (Split-Path -Parent $statePath)
$managed = $null
try {
    Write-SkillpaneStage 'record-read-begin'
    $record = Read-SkillpaneRecord $statePath $PSScriptRoot
    Write-SkillpaneStage 'record-read-end'
    if ($record -and $record.Port -ne $Port) { throw 'Requested port does not match the launcher record; refusing to stop it.' }
    Write-SkillpaneStage 'process-check-begin'
    $managed = Get-SkillpaneProcess $record $PSScriptRoot
    Write-SkillpaneStage 'process-check-end'
    if (-not $managed) { Write-Output 'Skillpane is already stopped.'; exit 0 }
    Write-SkillpaneStage 'stop-process-begin'
    $managed.Kill()
    if (-not $managed.WaitForExit(5000)) { throw 'Skillpane has not stopped yet.' }
    Write-SkillpaneStage 'stop-process-end'
    Write-Output 'Skillpane stopped.'
} finally {
    if ($managed) { $managed.Dispose() }
    $launcherLock.Dispose()
    Write-SkillpaneStage 'launcher-exit'
}

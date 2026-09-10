# Install (or refresh) the night-shift schedule on Windows.
#
#   powershell -ExecutionPolicy Bypass -File brain\tools\setup_night.ps1
#   powershell -ExecutionPolicy Bypass -File brain\tools\setup_night.ps1 -Off
#
# Safe to re-run. The hour comes from config.json (night.at), so there is one
# place to change it. Windows Task Scheduler wakes the machine for this by
# default (WakeToRun), which is what makes a desktop the ideal host.

param([switch]$Off)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$TaskName = "LifeBrain Night Shift"

if ($Off) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
    Write-Host "Night shift unscheduled. brain\config.json still holds your settings."
    exit 0
}

$PyExe = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $PyExe) { $PyExe = (Get-Command python3 -ErrorAction SilentlyContinue).Source }
if (-not $PyExe) { Write-Error "Python is not on your PATH."; exit 1 }

Push-Location $Root
$Cfg = & $PyExe (Join-Path $Root "brain\tools\night_config.py") --powershell
Pop-Location
$Cfg | ForEach-Object { Invoke-Expression $_ }

$Action = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument ("-NoProfile -ExecutionPolicy Bypass -File `"" +
               (Join-Path $Root "brain\tools\night.ps1") + "`"") `
    -WorkingDirectory $Root
$Trigger = New-ScheduledTaskTrigger -Daily -At $NightAt
# WakeToRun is the whole point on a desktop: the machine gets itself up, does
# the work, and is finished long before anyone is.
$Settings = New-ScheduledTaskSettingsSet -WakeToRun -StartWhenAvailable `
    -AllowStartIfOnBatteries:$false -DontStopIfGoingOnBatteries:$false `
    -ExecutionTimeLimit (New-TimeSpan -Hours 2)

Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger `
    -Settings $Settings -Force | Out-Null

Write-Host "Night shift scheduled for $NightAt - jobs: $NightJobs on $NightModel."
if ($NightEnabled -ne "1") {
    Write-Host ""
    Write-Host "It is still switched OFF in brain\config.json. Set night.enabled"
    Write-Host "to true there (or use the Night shift control on the page)."
}

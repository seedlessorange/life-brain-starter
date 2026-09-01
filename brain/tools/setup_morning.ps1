# Register (or remove) the 7am morning run in Windows Task Scheduler.
#
#   powershell -ExecutionPolicy Bypass -File brain\tools\setup_morning.ps1
#   powershell -ExecutionPolicy Bypass -File brain\tools\setup_morning.ps1 -Remove
#
# Or double-click "Set Up Mornings (Windows).bat" in the brain's folder.
# The task runs brain\tools\morning.ps1 daily at 07:00, and if the PC was
# asleep at 07:00 it runs as soon as it wakes instead of skipping the day.

param([switch]$Remove)

$TaskName = "Life brain morning"

if ($Remove) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
    Write-Host "The '$TaskName' task is gone. Mornings are manual again."
    exit 0
}

$Script = Join-Path $PSScriptRoot "morning.ps1"
if (-not (Test-Path $Script)) {
    Write-Host "Can't find morning.ps1 next to this script — run this from the brain's own folder."
    exit 1
}

$Action = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$Script`""
$Trigger = New-ScheduledTaskTrigger -Daily -At 7:00am
# StartWhenAvailable: a PC asleep at 07:00 runs the task on wake instead of
# skipping the day — the same behaviour launchd gives the Mac version.
$Settings = New-ScheduledTaskSettingsSet -StartWhenAvailable `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries

Register-ScheduledTask -TaskName $TaskName -Action $Action `
    -Trigger $Trigger -Settings $Settings -Force | Out-Null

Write-Host ""
Write-Host "Done. Every morning at 7:00 (or when the PC next wakes), the brain"
Write-Host "syncs Beeper, writes today's plan, and only notifies you if"
Write-Host "something is overdue or needs a chase."
Write-Host ""
Write-Host "To undo: run this script again with -Remove."

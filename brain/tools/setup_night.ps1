# Install (or refresh) the night-shift schedule on Windows.
#
#   powershell -ExecutionPolicy Bypass -File brain\tools\setup_night.ps1
#   powershell -ExecutionPolicy Bypass -File brain\tools\setup_night.ps1 -Off
#
# Safe to re-run. The hour (night.at) and the battery rule (night.on_battery)
# come from config.json, so there is one place to change them; run this
# again after changing either. Windows Task Scheduler wakes the machine for
# this (WakeToRun), which is what makes a desktop the ideal host.

param([switch]$Off)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$TaskName = "LifeBrain Night Shift"
# Python runs in UTF-8 mode, and its output is read back as UTF-8: the
# brain's files are UTF-8.
$env:PYTHONUTF8 = "1"
try { [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding $false } catch { }

if ($Off) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
    Write-Host "Night shift unscheduled. brain\config.json still holds your settings."
    exit 0
}

function Find-Python {
    # The launcher first, then plain python - the same order as Open
    # Brain.bat. Each candidate is run once, because the "python" Windows
    # puts on the PATH is a Microsoft Store shortcut that exits with an
    # error instead of running anything.
    $ErrorActionPreference = "Continue"
    foreach ($c in @("py", "python", "python3")) {
        $pre = @()
        if ($c -eq "py") { $pre = @("-3") }
        foreach ($cmd in @(Get-Command $c -CommandType Application -All -ErrorAction SilentlyContinue)) {
            $exe = $cmd.Path
            try {
                & $exe @pre -c "import sys" 2>&1 | Out-Null
                if ($LASTEXITCODE -eq 0) { return @{ Exe = $exe; Pre = $pre } }
            } catch { }
        }
    }
    return $null
}

$Py = Find-Python
if (-not $Py) {
    Write-Host ""
    Write-Host "Python is not installed, or this window cannot find it, so the"
    Write-Host "night shift cannot be scheduled yet."
    Write-Host ""
    Write-Host "Install it (Step 2 in START HERE (Windows).md), then run this again."
    Write-Host "A 'python' that only opens the Microsoft Store is a Windows shortcut,"
    Write-Host "not a real install."
    exit 1
}
$PyExe = $Py.Exe
$PyPre = $Py.Pre

# The settings, read by Python (night_config.py) so the Mac and Windows
# setups cannot drift. Every value arrives as a quoted literal.
Push-Location $Root
$Cfg = @(& $PyExe @PyPre (Join-Path $Root "brain\tools\night_config.py") --powershell)
Pop-Location
if (-not $Cfg) {
    Write-Host "Could not read the night-shift settings from brain\config.json."
    Write-Host "Run  claude  in the brain's folder and describe this; it can fix it."
    exit 1
}
foreach ($CfgLine in $Cfg) { Invoke-Expression $CfgLine }
# sets $NightEnabled, $NightJobs, $NightModel, $NightBattery, $NightBatteryMin, $NightAt

# -WindowStyle Hidden: no window pops up at 1am.
$Action = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument ("-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"" +
               (Join-Path $Root "brain\tools\night.ps1") + "`"") `
    -WorkingDirectory $Root
$Trigger = New-ScheduledTaskTrigger -Daily -At $NightAt
# WakeToRun is the whole point on a desktop: the machine gets itself up, does
# the work, and is finished long before anyone is.
$Settings = New-ScheduledTaskSettingsSet -WakeToRun -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Hours 2)
# Battery follows night.on_battery. false (a floor of 101 here): never start
# unplugged, and stop if the charger comes out. true (0) or a charge floor:
# the task may start, and night.ps1 checks the floor itself.
$BattMin = 101
if ("$NightBatteryMin" -match '^\d+$') { $BattMin = [int]$NightBatteryMin }
$NeverOnBattery = ($BattMin -ge 101)
$Settings.DisallowStartIfOnBatteries = $NeverOnBattery
$Settings.StopIfGoingOnBatteries = $NeverOnBattery

Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger `
    -Settings $Settings -Force | Out-Null

Write-Host "Night shift scheduled for $NightAt - jobs: $NightJobs on $NightModel."
if ($BattMin -ge 101) { Write-Host "It runs only while the PC is plugged in." }
elseif ($BattMin -le 0) { Write-Host "It runs on battery too." }
else { Write-Host "Unplugged, it runs only above $BattMin% charge." }
if ($NightEnabled -ne "1") {
    Write-Host ""
    Write-Host "It is still switched OFF in brain\config.json. Set night.enabled"
    Write-Host "to true there (or use the Night shift control on the page)."
}

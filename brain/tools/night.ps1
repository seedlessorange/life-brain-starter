# The night shift, Windows port of night.sh. See that file for why it runs at
# 01:00 rather than 03:00 — the five-hour usage window must close before the
# 07:00 morning plan opens a fresh one.
#
# Scheduled by setup_night.ps1. Sends nothing, submits nothing, buys nothing;
# git is the undo.

$ErrorActionPreference = "Continue"
$Root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
Set-Location $Root

$Log = Join-Path $Root "brain\.night.log"
$Report = Join-Path $Root "brain\.night-report.md"
$Today = Get-Date -Format "yyyy-MM-dd"
Add-Content $Log ("--- {0} night shift ---" -f (Get-Date -Format "yyyy-MM-dd HH:mm"))

$PyExe = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $PyExe) { $PyExe = (Get-Command python3 -ErrorAction SilentlyContinue).Source }
if (-not $PyExe) { Add-Content $Log "python not found; nothing to do"; exit 0 }

& $PyExe (Join-Path $Root "brain\tools\night_config.py") --powershell |
    ForEach-Object { Invoke-Expression $_ }

if ($NightEnabled -ne "1") {
    Add-Content $Log "night shift is off (config.json: night.enabled)"
    exit 0
}

# A machine asleep at 01:00 makes the task fire on the next wake. The night
# shift is only allowed to run at night.
$Hour = [int](Get-Date -Format "HH")
if ($Hour -ge 6 -and $Hour -lt 23) {
    Add-Content $Log "woke at ${Hour}h - outside the night window, skipping (normal)"
    exit 0
}

# "Tonight" is the last 20 hours, not the calendar date — the 23:00–06:00
# window straddles midnight, so a date comparison would happily run twice.
if ((Test-Path $Report) -and
    (((Get-Date) - (Get-Item $Report).LastWriteTime).TotalHours -lt 20)) {
    Add-Content $Log "already ran tonight, skipping"
    exit 0
}

# On battery this would drain a laptop flat by morning. A desktop reports no
# battery at all, so Win32_Battery is empty and it always passes.
if ($NightBattery -ne "1") {
    $Batt = Get-CimInstance -ClassName Win32_Battery -ErrorAction SilentlyContinue
    if ($Batt -and $Batt.BatteryStatus -eq 1) {
        Add-Content $Log "on battery - skipping (set night.on_battery true to override)"
        exit 0
    }
}

& $PyExe (Join-Path $Root "brain\tools\beeper.py") sync --write 2>&1 | Add-Content $Log

git add -A 2>&1 | Add-Content $Log
git commit -m "pre-night snapshot" 2>&1 | Add-Content $Log
# Take what the other machine pushed before working on top of it.
& $PyExe (Join-Path $Root "brain\tools\gitsync.py") --pull 2>&1 | Add-Content $Log

# Find claude BEFORE writing the report: the report's timestamp is the
# once-a-night marker, and a night with no claude must not burn the slot.
$Claude = Get-Command claude -ErrorAction SilentlyContinue
if (-not $Claude) {
    Add-Content $Log "claude not found on PATH; nothing to run"
    exit 0
}
Remove-Item Env:ANTHROPIC_API_KEY -ErrorAction SilentlyContinue
Remove-Item Env:ANTHROPIC_AUTH_TOKEN -ErrorAction SilentlyContinue
# Makes email_send.py and beeper.py refuse to send: nobody is watching.
$env:LIFEBRAIN_UNATTENDED = "1"
# The unattended marker arms private_gate.py, the hook keeping config's
# `private` files (the journal) out of unattended runs. It reads this
# FILE, not the env var — Claude Code hands hooks a scrubbed environment.
# Removed at the end of the loop; the gate ignores a file older than six
# hours, so a crash cannot leave tomorrow's attended sessions filtered.
# --lock is the layer that actually holds: an icacls deny-read on the
# private paths, the Windows twin of the Mac's chmod 0. --unlock after
# the loop removes it; a crash self-heals in her next attended session.
$Unattended = Join-Path $Root "brain\.unattended"
New-Item -ItemType File -Path $Unattended -Force | Out-Null
& $PyExe (Join-Path $Root "brain\tools\private_gate.py") --lock 2>&1 | Add-Content $Log

Set-Content $Report "# Last night"
Add-Content $Report ""
Add-Content $Report ("_{0}_" -f (Get-Date -Format "dddd d MMMM, HH:mm"))

$Result = Join-Path $Root "brain\.night-result.json"
foreach ($Job in ($NightJobs -split " ")) {
    if (-not $Job) { continue }
    Add-Content $Log "--- running /$Job ---"
    $null | & $Claude.Source -p "/$Job" --permission-mode bypassPermissions `
        --model $NightModel --output-format json | Set-Content $Result
    $Code = $LASTEXITCODE
    Add-Content $Report ""
    Add-Content $Report "## /$Job"
    Add-Content $Report ""
    if ($Code -eq 0) {
        & $PyExe (Join-Path $Root "brain\tools\usage.py") --record $Result `
            --kind night --label "night /$Job" --model $NightModel |
            Add-Content $Report
    } else {
        Add-Content $Report "That run failed (exit $Code). Nothing was lost."
    }
    Add-Content $Log "/$Job exit $Code"
    Remove-Item $Result -ErrorAction SilentlyContinue
}
Remove-Item $Unattended -ErrorAction SilentlyContinue
& $PyExe (Join-Path $Root "brain\tools\private_gate.py") --unlock 2>&1 | Add-Content $Log

& $PyExe (Join-Path $Root "brain\tools\build.py") 2>&1 | Add-Content $Log
& $PyExe (Join-Path $Root "brain\tools\map.py") 2>&1 | Add-Content $Log
& $PyExe (Join-Path $Root "brain\tools\rooms.py") 2>&1 | Add-Content $Log
& $PyExe (Join-Path $Root "brain\tools\proto.py") 2>&1 | Add-Content $Log

git add -A 2>&1 | Add-Content $Log
git commit -m ("night shift " + $Today) 2>&1 | Add-Content $Log
# Off-machine copy: push when a remote exists. Never fatal.
git remote get-url origin 2>$null | Out-Null
if ($LASTEXITCODE -eq 0) { git push -q origin HEAD 2>&1 | Add-Content $Log }

Add-Content $Report ""
Add-Content $Report "---"
Add-Content $Report ""
& $PyExe (Join-Path $Root "brain\tools\usage.py") --days 1 |
    Select-Object -First 6 | Add-Content $Report

Get-Content $Log -Tail 500 | Set-Content "$Log.tmp"
Move-Item "$Log.tmp" $Log -Force
Add-Content $Log "night shift finished"

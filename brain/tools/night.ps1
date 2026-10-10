# The night shift, Windows port of night.sh: keep the two in the same order,
# and put anything both need to decide in Python for both to read. See
# night.sh for why it runs at 01:00 rather than 03:00 - the five-hour usage
# window must close before the 07:00 morning plan opens a fresh one.
#
# Scheduled by setup_night.ps1. Sends nothing, submits nothing, buys nothing;
# git is the undo. Left out as Mac-only: caffeinate (no Windows twin in the
# repo yet); pmset's battery reading is Windows' own power status here.

$ErrorActionPreference = "Continue"
$Root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
Set-Location $Root
$Tools = Join-Path $Root "brain\tools"

$Log = Join-Path $Root "brain\.night.log"
$Report = Join-Path $Root "brain\.night-report.md"
$Today = Get-Date -Format "yyyy-MM-dd"
$Invariant = [System.Globalization.CultureInfo]::InvariantCulture

# Text in and out is UTF-8, as on the Mac. Python runs in UTF-8 mode, and
# PowerShell decodes what it captures from Python and Claude as UTF-8
# instead of the console's old code page. The files are written through
# .NET, because PowerShell 5.1's Add-Content and Set-Content write the ANSI
# code page: that mangles every non-ASCII character, and night_config.py
# reads this log back as UTF-8 to tell the page which nights were skipped.
$env:PYTHONUTF8 = "1"
$Utf8 = New-Object System.Text.UTF8Encoding $false
try { [Console]::OutputEncoding = $Utf8 } catch { }
$OutputEncoding = $Utf8

function Add-Utf8 {
    # Append lines to a file as UTF-8 without a BOM (Add-Content's twin).
    param([string]$Path, [Parameter(ValueFromPipeline = $true)] $Line)
    process {
        try { [System.IO.File]::AppendAllText($Path, "$Line`r`n", $Utf8) } catch { }
    }
}

function Write-Log {
    param([Parameter(ValueFromPipeline = $true)] $Line)
    process { Add-Utf8 $Log $Line }
}

function Split-Stderr {
    # A native command run with 2>&1 hands back its stdout lines as strings
    # and its stderr lines as error records: the records go to the log, the
    # strings pass on.
    param([Parameter(ValueFromPipeline = $true)] $Item)
    process {
        if ($Item -is [System.Management.Automation.ErrorRecord]) { Write-Log "$Item" }
        else { "$Item" }
    }
}

function Save-Utf8([string]$Path, $Lines) {
    [System.IO.File]::WriteAllText($Path, ((@($Lines) | ForEach-Object { "$_" }) -join "`n"), $Utf8)
}

Write-Log ("--- {0} night shift ---" -f (Get-Date -Format "yyyy-MM-dd HH:mm"))

# Python: the launcher first, then plain python - the same order as Open
# Brain.bat. Each candidate is run once, because the "python" Windows puts on
# the PATH is a Microsoft Store shortcut that exits with an error instead of
# running anything.
$PyExe = $null; $PyPre = @()
foreach ($c in @("py", "python", "python3")) {
    $pre = @()
    if ($c -eq "py") { $pre = @("-3") }
    foreach ($cmd in @(Get-Command $c -CommandType Application -All -ErrorAction SilentlyContinue)) {
        $exe = $cmd.Path
        & $exe @pre -c "import sys" 2>&1 | Out-Null
        if ($LASTEXITCODE -eq 0) { $PyExe = $exe; $PyPre = $pre; break }
    }
    if ($PyExe) { break }
}
if (-not $PyExe) { Write-Log "python not found on PATH; nothing to do"; exit 0 }

# The settings, read by Python (night_config.py) so this script and night.sh
# cannot drift. Every value arrives as a quoted literal.
$Cfg = @(& $PyExe @PyPre (Join-Path $Tools "night_config.py") --powershell 2>$null)
if (-not $Cfg) {
    Write-Log "no night config, or config.json unreadable - nothing to do"
    exit 0
}
foreach ($CfgLine in $Cfg) { Invoke-Expression $CfgLine }
# sets $NightEnabled, $NightJobs, $NightModel, $NightBattery, $NightBatteryMin

if ($NightEnabled -ne "1") {
    Write-Log "night shift is off (config.json: night.enabled)"
    exit 0
}

# A machine asleep at 01:00 makes the task fire on the next wake - which
# could be 09:15, mid-coffee. The night shift is only allowed to run at night.
$Hour = [int](Get-Date -Format "HH")
if ($Hour -ge 6 -and $Hour -lt 23) {
    Write-Log "woke at ${Hour}h - outside the night window, skipping (this is normal)"
    exit 0
}

# Once per night. "Tonight" is the last 20 hours, not the calendar date - the
# 23:00-06:00 window straddles midnight, so a date comparison would happily
# run twice.
if ((Test-Path $Report) -and
    (((Get-Date) - (Get-Item $Report).LastWriteTime).TotalHours -lt 20)) {
    Write-Log "already ran tonight, skipping"
    exit 0
}

# On battery this could drain the machine flat by morning, so unplugged it
# runs only above the charge config sets (night.on_battery: false never, true
# always, a number is the floor). A desktop reports no battery and always
# passes. The scheduled task itself also refuses to start on battery when
# on_battery is false (setup_night.ps1).
$BattMin = 101
if ("$NightBatteryMin" -match '^\d+$') { $BattMin = [int]$NightBatteryMin }
if ($BattMin -gt 0) {
    $Power = $null
    try {
        Add-Type -AssemblyName System.Windows.Forms
        $Power = [System.Windows.Forms.SystemInformation]::PowerStatus
    } catch { }
    if ($Power -and "$($Power.PowerLineStatus)" -eq "Offline") {
        $Pct = [int]($Power.BatteryLifePercent * 100)
        if ($Pct -lt $BattMin) {
            Write-Log "on battery at $Pct% - skipping (runs unplugged only above $BattMin%, config night.on_battery)"
            exit 0
        }
        Write-Log "on battery at $Pct% - above the $BattMin% floor, running"
    }
}

# The agent the brain is set to run (agents.py): Claude Code, Codex or
# Gemini CLI. For Claude only a real claude.exe counts (run_policy.py
# refuses an npm claude.cmd: cmd.exe cuts a prompt at its first line break).
$null | & $PyExe @PyPre (Join-Path $Tools "agents.py") check 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) {
    $null | & $PyExe @PyPre (Join-Path $Tools "agents.py") check 2>&1 | Write-Log
    Write-Log "Nothing to run tonight."
    exit 0
}

# The smoke test, so a broken parser is on record before an unattended
# agent works on top of it. Logged, never fatal.
$null | & $PyExe @PyPre (Join-Path $Tools "selftest.py") 2>&1 | Write-Log
if ($LASTEXITCODE -ne 0) { Write-Log "SELFTEST FAILED - see above" }

# Beeper is usually still open overnight; free either way.
$null | & $PyExe @PyPre (Join-Path $Tools "beeper.py") sync --write 2>&1 | Write-Log
if ($LASTEXITCODE -eq 0) { Write-Log "beeper sync ok" } else { Write-Log "beeper sync skipped" }

# Restore point before an unattended agent touches anything.
git add -A 2>&1 | Write-Log
git commit -m "pre-night snapshot" 2>&1 | Write-Log
# Take what the other machine pushed before working on top of it.
$null | & $PyExe @PyPre (Join-Path $Tools "gitsync.py") --pull 2>&1 | Write-Log

[System.IO.File]::WriteAllText($Report, "# Last night`r`n`r`n", $Utf8)
Add-Utf8 $Report ("_{0}_" -f (Get-Date).ToString("dddd d MMMM, HH:mm", $Invariant))
Add-Utf8 $Report ""

Remove-Item Env:ANTHROPIC_API_KEY -ErrorAction SilentlyContinue
Remove-Item Env:ANTHROPIC_AUTH_TOKEN -ErrorAction SilentlyContinue
# Makes email_send.py and beeper.py refuse to send: nobody is watching.
$env:LIFEBRAIN_UNATTENDED = "1"

# Private files (config `private`, the journal by default) stay out of the
# unattended runs, two layers deep. --lock is an icacls deny-read on them,
# the Windows twin of the Mac's chmod 0 and the layer that actually holds.
# The .unattended marker file arms the hook layer as well (a FILE, not the
# env var: Claude Code hands hooks a scrubbed environment). The finally block
# undoes both however the loop ends; a killed process self-heals anyway - the
# gate ignores a stale marker and her next attended session lifts the lock.
$Unattended = Join-Path $Root "brain\.unattended"
$Result = Join-Path $Root "brain\.night-result.json"
$Policy = Join-Path $Tools "run_policy.py"
$EventsFile = Join-Path $Root "brain\events.md"
try {
    New-Item -ItemType File -Path $Unattended -Force | Out-Null
    $null | & $PyExe @PyPre (Join-Path $Tools "private_gate.py") --lock 2>&1 | Write-Log
    foreach ($Job in ("$NightJobs" -split " ")) {
        if (-not $Job) { continue }
        # /scout is weekly by design: when events.md is under 6 days old,
        # skip before starting a claude run at all. The command self-gates
        # on the same date too - this check just makes the usual outcome free.
        if ($Job -eq "scout" -and (Test-Path $EventsFile) -and
            (((Get-Date) - (Get-Item $EventsFile).LastWriteTime).TotalSeconds -lt 518400)) {
            Write-Log "scout: events.md under 6 days old - weekly job, skipping"
            continue
        }
        Write-Log "--- running /$Job ---"
        $Start = Get-Date
        # Never bypass: run_policy.py sets the fences (on Windows, a command
        # allowlist, since Claude Code has no sandbox there). The scout is the
        # one job that reads the open web, so it runs in a temp folder of its
        # own with only the taste file in reach.
        if ($Job -eq "scout") {
            $Out = @($null | & $PyExe @PyPre $Policy scout $NightModel 2>&1 | Split-Stderr)
        } else {
            $Out = @($null | & $PyExe @PyPre $Policy run scheduled '--' -p "/$Job" `
                --model $NightModel --output-format json 2>&1 | Split-Stderr)
        }
        $Code = $LASTEXITCODE
        Save-Utf8 $Result $Out
        Add-Utf8 $Report ""
        Add-Utf8 $Report "## /$Job"
        Add-Utf8 $Report ""
        if ($Code -eq 0) {
            $null | & $PyExe @PyPre (Join-Path $Tools "usage.py") --record $Result `
                --kind night --label "night /$Job" --model $NightModel 2>&1 |
                Split-Stderr | Add-Utf8 $Report
        } else {
            Add-Utf8 $Report "That run failed (exit $Code). Nothing was lost."
            Write-Log "/$Job failed with $Code"
        }
        $Secs = [int]((Get-Date) - $Start).TotalSeconds
        Write-Log "/$Job done in ${Secs}s (exit $Code)"
        Remove-Item $Result -Force -ErrorAction SilentlyContinue
    }
} finally {
    Remove-Item $Unattended -Force -ErrorAction SilentlyContinue
    $null | & $PyExe @PyPre (Join-Path $Tools "private_gate.py") --unlock 2>&1 | Write-Log
}

$null | & $PyExe @PyPre (Join-Path $Tools "rebuild.py") 2>&1 | Write-Log

git add -A 2>&1 | Write-Log
git commit -m ("night shift " + $Today) 2>&1 | Write-Log
# Off-machine copy, through gitsync.py, which pushes only when config turns
# it on. Never fatal.
$null | & $PyExe @PyPre (Join-Path $Tools "gitsync.py") --push 2>&1 | Write-Log

# What it cost, appended to the report so the morning can see it in one place.
Add-Utf8 $Report ""
Add-Utf8 $Report "---"
Add-Utf8 $Report ""
$Usage = @($null | & $PyExe @PyPre (Join-Path $Tools "usage.py") --days 1 2>$null)
$Usage | Select-Object -First 6 | Add-Utf8 $Report

# Keep the log from growing forever. Read as UTF-8 so older lines written
# in the ANSI code page come through as replacement marks, not errors.
try {
    [string[]]$Lines = [System.IO.File]::ReadAllLines($Log, $Utf8)
    if ($Lines.Count -gt 500) {
        [string[]]$Keep = $Lines | Select-Object -Last 500
        [System.IO.File]::WriteAllLines($Log, $Keep, $Utf8)
    }
} catch { }
Write-Log "night shift finished"
exit 0

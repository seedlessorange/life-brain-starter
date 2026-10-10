# The 7am run, Windows edition: write today's plan before the owner is up,
# and only make a sound if something genuinely needs them ("no news, no
# message"). This is a line-for-line port of morning.sh: keep the two in the
# same order, and put anything both need to decide in Python for both to read.
#
# Scheduled by Task Scheduler - run brain\tools\setup_morning.ps1 once (or
# double-click "Set Up Mornings (Windows).bat") to register it. The task is
# registered with StartWhenAvailable, so if the PC is asleep at 07:00 it runs
# on the next wake - which means "when you open the lid".
#
# Left out as Mac-only: caffeinate (no Windows twin in the repo yet). The
# notification is a Windows toast instead of osascript.
#
# Cost: one small headless Claude run a day on the owner's subscription.

$ErrorActionPreference = "Continue"
$Root = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
Set-Location $Root
$Tools = Join-Path $Root "brain\tools"
$Log = Join-Path $Root "brain\.morning.log"

# Text in and out is UTF-8, as on the Mac. Python runs in UTF-8 mode, and
# PowerShell decodes what it captures from Python and Claude as UTF-8
# instead of the console's old code page. The files are written through
# .NET, because PowerShell 5.1's Add-Content and Set-Content write the ANSI
# code page, which mangles every non-ASCII character and which Python then
# refuses to read back.
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

function Show-Toast([string]$Msg) {
    # A native Windows toast, no modules needed (Windows 10/11).
    try {
        [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
        [Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] | Out-Null
        $Escaped = [System.Security.SecurityElement]::Escape($Msg)
        $Xml = New-Object Windows.Data.Xml.Dom.XmlDocument
        $Xml.LoadXml("<toast><visual><binding template='ToastGeneric'><text>Your brain</text><text>$Escaped</text></binding></visual></toast>")
        $AppId = '{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe'
        $Toast = New-Object Windows.UI.Notifications.ToastNotification $Xml
        [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($AppId).Show($Toast)
        Write-Log ("notified: " + $Msg)
    } catch {
        Write-Log ("toast failed: " + $_)
    }
}

function Invoke-Step([string]$Tool, [string[]]$ToolArgs, [string]$Ok, [string]$Skip) {
    # One free, never-fatal step: output to the log, then one line saying
    # whether it worked (morning.sh's `cmd && echo ok || echo skipped`).
    $null | & $PyExe @PyPre (Join-Path $Tools $Tool) @ToolArgs 2>&1 | Write-Log
    if ($LASTEXITCODE -eq 0) { Write-Log $Ok } else { Write-Log $Skip }
}

Write-Log ("--- {0} morning run ---" -f (Get-Date -Format "yyyy-MM-dd HH:mm"))

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
if (-not $PyExe) {
    Write-Log "python not found on PATH; giving up"
    exit 1
}
# -P wherever Python reads its script from stdin here: without it the current
# folder (the repo root, which a run may write) comes first on the import
# path, and a planted json.py would run. -P needs Python 3.11 or later.
$SafePath = @()
& $PyExe @PyPre -P -c "import sys" 2>&1 | Out-Null
if ($LASTEXITCODE -eq 0) { $SafePath = @("-P") }
else { Write-Log "python is older than 3.11: running its inline checks without -P" }

# The smoke test: a quarter of a second, no network, no model. A failure
# does not block the morning - it gets a notification, because a silently
# broken parser is exactly the failure this system exists to prevent.
$null | & $PyExe @PyPre (Join-Path $Tools "selftest.py") 2>&1 | Write-Log
if ($LASTEXITCODE -ne 0) {
    Show-Toast "Something in the brain is broken - see brain\.morning.log"
}

# Once per day: if today's plan is already dated today, a second wake
# (or a manual test) must not burn a second run.
$Today = Get-Date -Format "yyyy-MM-dd"
$TodayFile = Join-Path $Root "brain\today.md"
if ((Test-Path $TodayFile) -and
    (Select-String -Path $TodayFile -Pattern ("updated: " + $Today) -SimpleMatch -Quiet)) {
    Write-Log "already ran today, skipping"
    exit 0
}

# Pull who the owner has actually spoken to, from Beeper's local API. Free,
# no model, no network beyond localhost - and it only works while Beeper is
# open, so a silent failure here is expected and must not stop the run.
Invoke-Step "beeper.py" @("sync", "--write") "beeper sync ok" "beeper sync skipped (app closed or not connected)"

# Bank feed: balances + transactions into brain\finance\, read-only, no
# model. A lapsed consent (some banks' last a day) is expected and must not
# stop the morning - the page shows each bank's freshness instead.
Invoke-Step "finance.py" @("fetch") "bank fetch ok" "bank fetch skipped (no key or consent lapsed)"

# The day's news briefing: RSS from the outlets in config plus one small
# no-tool Haiku call for the finance breakdown (--explain, cached for the
# day). Dead wifi must not stop the morning.
Invoke-Step "news.py" @("fetch", "--explain") "news fetch ok" "news fetch skipped (offline?)"
Invoke-Step "jobs.py" @("scan", "--if-on") "jobs scan ok" "jobs scan skipped (offline?)"

# Class material downloaded yesterday, still sitting in Downloads: copied in
# and filed by course from what is printed on it. Copies only. Then new
# slide decks in the class folder, read for the dates they hide; nothing
# files itself. A class folder that isn't on this machine must not stop the
# morning.
Invoke-Step "school.py" @("--catch") "downloads catch ok" "downloads catch skipped"
Invoke-Step "school.py" @("--scan") "school scan ok" "school scan skipped (class folder not on this machine?)"

# Fold any new sessions into each course's running guide. Self-gating: a
# model call happens only once a course has enough new material to be
# worth one.
Invoke-Step "guide.py" @("--all") "guides ok" "guides skipped"

# Class notes from Notion, if connected. Read-only; exits quietly when there
# is no token, which is the normal case until it is connected.
Invoke-Step "notion.py" @("--pull") "notion pull ok" "notion pull skipped (not connected)"

# Restore point before an unattended agent touches anything.
git add -A 2>&1 | Write-Log
git commit -m "pre-morning snapshot" 2>&1 | Write-Log
# Take what the other machine pushed before planning on top of it. Never
# fatal - an offline morning runs on what this machine already has.
$null | & $PyExe @PyPre (Join-Path $Tools "gitsync.py") --pull 2>&1 | Write-Log

# The scheduled Claude run follows the mode - Full runs it, Careful (a Pro
# plan's shared 5-hour window) skips it - unless the Usage page set the
# morning switch explicitly (config `ai_features.morning`). Skipped, the free
# parts above still happened and /today stays a manual, cheap choice.
$ModeCode = @'
import json
try:
    cfg = json.load(open("brain/config.json", encoding="utf-8"))
except Exception:
    cfg = {}
mode = "careful" if cfg.get("ai") in ("low", "careful", "pro") else "full"
ov = (cfg.get("ai_features") or {}).get("morning")
run = (mode == "full") if not isinstance(ov, bool) else ov
print("run" if run else "skip")
'@
$MorningRun = "$(@($ModeCode | & $PyExe @PyPre @SafePath - 2>&1 | Split-Stderr))".Trim()
if (-not $MorningRun) { $MorningRun = "run" }

# The agent the brain is set to run (agents.py): Claude Code, Codex or
# Gemini CLI. For Claude only a real claude.exe counts (run_policy.py
# refuses an npm claude.cmd: cmd.exe cuts a prompt at its first line break).
$null | & $PyExe @PyPre (Join-Path $Tools "agents.py") check 2>&1 | Out-Null
$Claude = ($LASTEXITCODE -eq 0)
if ($MorningRun -eq "skip") {
    Write-Log "morning Claude run switched off (mode or Usage page): skipping"
    $null | & $PyExe @PyPre (Join-Path $Tools "rebuild.py") 2>&1 | Write-Log
} elseif (-not $Claude) {
    Write-Log "the brain's agent is not installed; rebuilding only"
    $null | & $PyExe @PyPre (Join-Path $Tools "agents.py") check 2>&1 | Write-Log
    $MorningRun = "skip"
    $null | & $PyExe @PyPre (Join-Path $Tools "rebuild.py") 2>&1 | Write-Log
} else {
    # stdin closed (claude -p hangs forever otherwise). /today needs to run
    # the rebuild, which run_policy.py allows by command; git above is the
    # undo. The API-key variables are stripped so the run always bills the
    # subscription login, never a key.
    Remove-Item Env:ANTHROPIC_API_KEY -ErrorAction SilentlyContinue
    Remove-Item Env:ANTHROPIC_AUTH_TOKEN -ErrorAction SilentlyContinue
    # Makes email_send.py and beeper.py refuse to send: nobody is watching.
    $env:LIFEBRAIN_UNATTENDED = "1"
    # --output-format json so the run lands in the usage ledger. usage.py
    # prints the plan text back out, so this log stays readable prose.
    $Result = Join-Path $Root "brain\.morning-result.json"
    $Policy = Join-Path $Tools "run_policy.py"
    $Unattended = Join-Path $Root "brain\.unattended"
    $Status = 1
    # Private files (config `private`, the journal by default) stay out of
    # this unattended run, two layers deep: --lock is an icacls deny-read on
    # them (the Windows twin of the Mac's chmod 0, and the layer that
    # actually holds), and the .unattended marker arms the hook layer (a
    # FILE, not the env var - hooks get a scrubbed environment). The finally
    # block undoes both however the run ends; a killed process self-heals in
    # her next attended session.
    try {
        New-Item -ItemType File -Path $Unattended -Force | Out-Null
        $null | & $PyExe @PyPre (Join-Path $Tools "private_gate.py") --lock 2>&1 | Write-Log
        # The calendar is read here, outside the run, so the run's own
        # calendar_read calls land on the ten-minute cache. On Windows it
        # reads feeds only, which are quick, so the two spans run in turn.
        $null | & $PyExe @PyPre (Join-Path $Tools "calendar_read.py") --days 1 2>&1 | Out-Null
        $null | & $PyExe @PyPre (Join-Path $Tools "calendar_read.py") --days 7 2>&1 | Out-Null
        # Never bypass: run_policy.py sets the fences (on Windows, a command
        # allowlist, since Claude Code has no sandbox there).
        $Invariant = [System.Globalization.CultureInfo]::InvariantCulture
        $Prompt = "/today Today is " + (Get-Date).ToString("dddd d MMMM yyyy", $Invariant) + "."
        $Out = @($null | & $PyExe @PyPre $Policy run scheduled '--' -p $Prompt `
            --output-format json 2>&1 | Split-Stderr)
        $Status = $LASTEXITCODE
        Save-Utf8 $Result $Out
    } finally {
        Remove-Item $Unattended -Force -ErrorAction SilentlyContinue
        $null | & $PyExe @PyPre (Join-Path $Tools "private_gate.py") --unlock 2>&1 | Write-Log
    }
    $null | & $PyExe @PyPre (Join-Path $Tools "usage.py") --record $Result `
        --kind morning --label "morning /today" 2>&1 | Write-Log
    # What the plan looked at, read from the run's own transcript, for "How
    # this plan was made" under the plan (plan_sources.py). Names only.
    if ($Status -eq 0) {
        $null | & $PyExe @PyPre (Join-Path $Tools "plan_sources.py") trace `
            --result $Result --by morning 2>&1 | Write-Log
        $null | & $PyExe @PyPre (Join-Path $Tools "rebuild.py") 2>&1 | Write-Log
    }
    Remove-Item $Result -Force -ErrorAction SilentlyContinue
    Write-Log ("claude exit: {0}" -f $Status)
    # The scout is a night job, and a laptop left unplugged skips every
    # night. When the night has missed its week, the morning catches it up -
    # same isolated run, at most once, since a fresh events.md stops it.
    $ScoutDue = "$(& $PyExe @PyPre (Join-Path $Tools "night_config.py") --scout-due 2>$null)".Trim()
    if ($ScoutDue -eq "due") {
        Write-Log "scout: the night missed it this week - catching up"
        $Out = @($null | & $PyExe @PyPre $Policy scout 2>&1 | Split-Stderr)
        $ScoutCode = $LASTEXITCODE
        Save-Utf8 $Result $Out
        if ($ScoutCode -eq 0) {
            $null | & $PyExe @PyPre (Join-Path $Tools "usage.py") --record $Result `
                --kind morning --label "morning /scout" 2>&1 | Write-Log
        }
        Remove-Item $Result -Force -ErrorAction SilentlyContinue
        $null | & $PyExe @PyPre (Join-Path $Tools "build.py") 2>&1 | Write-Log
    }
}

git add -A 2>&1 | Write-Log
git commit -m ("morning run " + $Today) 2>&1 | Write-Log
# Off-machine copy, through gitsync.py, which pushes only when config turns
# it on. Never fatal - dead hotel wifi must not break the morning.
$null | & $PyExe @PyPre (Join-Path $Tools "gitsync.py") --push 2>&1 | Write-Log

# Threshold-gated notification: silent unless something is actually on fire.
$MsgCode = @'
import os
import sys
# The script already moved to the brain, wherever it lives.
sys.path.insert(0, os.path.join(os.getcwd(), "brain", "tools"))
import model
b = model.briefing(model.load())
bits = []
if b["overdue"]:
    bits.append(f"{len(b['overdue'])} overdue")
if b["chase"]:
    bits.append(f"{len(b['chase'])} to chase")
print(" and ".join(bits))
'@
$Msg = "$(@($MsgCode | & $PyExe @PyPre @SafePath - 2>&1 | Split-Stderr))".Trim()
if ($Msg) {
    if ($MorningRun -eq "run") { $Msg = $Msg + " - plan is ready" }
    Show-Toast $Msg
} else {
    Write-Log "all quiet, no notification"
}

# The plan to the phone, from HERE: the scheduler runs this at 7:00 or at
# the first wake after, while the in-server bridge only pushes if serve.py
# happens to be up in the window.
$null | & $PyExe @PyPre (Join-Path $Tools "telegram_bridge.py") --push-plan 2>&1 | Write-Log
$null | & $PyExe @PyPre (Join-Path $Tools "telegram_bridge.py") --push-news 2>&1 | Write-Log

# Keep the log from growing forever. Read as UTF-8 so older lines written
# in the ANSI code page come through as replacement marks, not errors.
try {
    [string[]]$Lines = [System.IO.File]::ReadAllLines($Log, $Utf8)
    if ($Lines.Count -gt 400) {
        [string[]]$Keep = $Lines | Select-Object -Last 400
        [System.IO.File]::WriteAllLines($Log, $Keep, $Utf8)
    }
} catch { }
exit 0

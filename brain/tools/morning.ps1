# The 7am run, Windows edition: write today's plan before the owner is up,
# and only make a sound if something genuinely needs them ("no news, no
# message"). This is a line-for-line port of morning.sh.
#
# Scheduled by Task Scheduler — run brain\tools\setup_morning.ps1 once (or
# double-click "Set Up Mornings (Windows).bat") to register it. The task is
# registered with StartWhenAvailable, so if the PC is asleep at 07:00 it runs
# on the next wake — which means "when you open the lid".
#
# Cost: one small headless Claude run a day on the owner's subscription.

$ErrorActionPreference = "Continue"
$Root = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
Set-Location $Root
$Log = Join-Path $Root "brain\.morning.log"
Add-Content $Log ("--- {0} morning run ---" -f (Get-Date -Format "yyyy-MM-dd HH:mm"))

# Python: the launcher first, then plain python — same order as the launcher.
$PyExe = $null; $PyPre = @()
foreach ($c in @("py", "python", "python3")) {
    $cmd = Get-Command $c -ErrorAction SilentlyContinue
    if ($cmd) {
        $PyExe = $cmd.Source
        if ($c -eq "py") { $PyPre = @("-3") }
        break
    }
}
if (-not $PyExe) {
    Add-Content $Log "python not found on PATH; giving up"
    exit 1
}

# Once per day: if today's plan is already dated today, a second wake
# (or a manual test) must not burn a second run.
$Today = Get-Date -Format "yyyy-MM-dd"
$TodayFile = Join-Path $Root "brain\today.md"
if ((Test-Path $TodayFile) -and
    (Select-String -Path $TodayFile -Pattern ("updated: " + $Today) -SimpleMatch -Quiet)) {
    Add-Content $Log "already ran today, skipping"
    exit 0
}

# Pull who the owner has actually spoken to, from Beeper's local API. Free,
# no model, no network beyond localhost — and it only works while Beeper is
# open, so a silent failure here is expected and must not stop the run.
& $PyExe @PyPre (Join-Path $Root "brain\tools\beeper.py") sync --write 2>&1 | Add-Content $Log
if ($LASTEXITCODE -eq 0) { Add-Content $Log "beeper sync ok" }
else { Add-Content $Log "beeper sync skipped (app closed or not connected)" }

# The day's news briefing: RSS from the outlets in config plus one small
# no-tool Haiku call for the finance breakdown (--explain, cached for the
# day). Dead wifi must not stop the morning.
& $PyExe @PyPre (Join-Path $Root "brain\tools\news.py") fetch --explain 2>&1 | Add-Content $Log
if ($LASTEXITCODE -eq 0) { Add-Content $Log "news fetch ok" }
else { Add-Content $Log "news fetch skipped (offline?)" }

# Restore point before an unattended agent touches anything.
git add -A 2>&1 | Add-Content $Log
git commit -m "pre-morning snapshot" 2>&1 | Add-Content $Log
# Take what the other machine pushed before planning on top of it. Never
# fatal - an offline morning runs on what this machine already has.
& $PyExe @PyPre (Join-Path $Root "brain\tools\gitsync.py") --pull 2>&1 | Add-Content $Log

# The scheduled Claude run follows the mode - Full runs it, Careful (a Pro
# plan's shared 5-hour window) skips it - unless the Usage page set the
# morning switch explicitly (config `ai_features.morning`). Skipped, the free
# parts above still happened and /today stays a manual, cheap choice.
$ModeCode = @'
import json
try:
    cfg = json.load(open("brain/config.json"))
except Exception:
    cfg = {}
mode = "careful" if cfg.get("ai") in ("low", "careful", "pro") else "full"
ov = (cfg.get("ai_features") or {}).get("morning")
run = (mode == "full") if not isinstance(ov, bool) else ov
print("run" if run else "skip")
'@
$MorningRun = $ModeCode | & $PyExe @PyPre - 2>$null
if (-not $MorningRun) { $MorningRun = "run" }
$MorningRun = "$MorningRun".Trim()

$Claude = Get-Command claude -ErrorAction SilentlyContinue
if ($MorningRun -eq "skip" -or -not $Claude) {
    if (-not $Claude) { Add-Content $Log "claude not found on PATH; rebuilding only" }
    else { Add-Content $Log "morning Claude run switched off (mode or Usage page): skipping" }
    & $PyExe @PyPre (Join-Path $Root "brain\tools\build.py") 2>&1 | Add-Content $Log
    & $PyExe @PyPre (Join-Path $Root "brain\tools\map.py") 2>&1 | Add-Content $Log
    & $PyExe @PyPre (Join-Path $Root "brain\tools\rooms.py") 2>&1 | Add-Content $Log
    & $PyExe @PyPre (Join-Path $Root "brain\tools\proto.py") 2>&1 | Add-Content $Log
} else {
    # stdin closed (claude -p hangs forever otherwise); bypassPermissions
    # because /today needs to run the rebuild. The HARD RULES in CLAUDE.md
    # are the guardrails; git above is the undo. The API-key variables are
    # stripped so the run always bills the subscription login, never a key.
    Remove-Item Env:ANTHROPIC_API_KEY -ErrorAction SilentlyContinue
    Remove-Item Env:ANTHROPIC_AUTH_TOKEN -ErrorAction SilentlyContinue
    # Makes email_send.py and beeper.py refuse to send: nobody is watching.
    $env:LIFEBRAIN_UNATTENDED = "1"
    # The unattended marker arms private_gate.py, the hook keeping
    # config's `private` files (the journal) out of unattended runs. A
    # FILE, not the env var — Claude Code hands hooks a scrubbed
    # environment. Removed right after the run; the gate ignores a file
    # older than six hours. --lock is the layer that actually holds: an
    # icacls deny-read on the private paths, the Windows twin of the
    # Mac's chmod 0. --unlock after the run removes it.
    $Unattended = Join-Path $Root "brain\.unattended"
    New-Item -ItemType File -Path $Unattended -Force | Out-Null
    & $PyExe @PyPre (Join-Path $Root "brain\tools\private_gate.py") --lock 2>&1 | Add-Content $Log
    # --output-format json so the run lands in the usage ledger. usage.py
    # prints the plan text back out, so this log stays readable prose.
    $Result = Join-Path $Root "brain\.morning-result.json"
    $null | & $Claude.Source -p "/today" --permission-mode bypassPermissions `
        --output-format json | Set-Content $Result
    Add-Content $Log ("claude exit: {0}" -f $LASTEXITCODE)
    Remove-Item $Unattended -ErrorAction SilentlyContinue
    & $PyExe @PyPre (Join-Path $Root "brain\tools\private_gate.py") --unlock 2>&1 | Add-Content $Log
    & $PyExe @PyPre (Join-Path $Root "brain\tools\usage.py") --record $Result `
        --kind morning --label "morning /today" 2>&1 | Add-Content $Log
    Remove-Item $Result -ErrorAction SilentlyContinue
}

git add -A 2>&1 | Add-Content $Log
git commit -m ("morning run " + $Today) 2>&1 | Add-Content $Log
# Off-machine copy: push when a remote exists. Never fatal.
git remote get-url origin 2>$null | Out-Null
if ($LASTEXITCODE -eq 0) { git push -q origin HEAD 2>&1 | Add-Content $Log }

# Threshold-gated notification: silent unless something is actually on fire.
$MsgCode = @'
import os
import sys
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
$Msg = $MsgCode | & $PyExe @PyPre - 2>$null
$Msg = "$Msg".Trim()
if ($Msg) {
    if ($MorningRun -eq "run") { $Msg = $Msg + " - plan is ready" }
    try {
        # A native Windows toast, no modules needed (Windows 10/11).
        [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
        [Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] | Out-Null
        $Escaped = [System.Security.SecurityElement]::Escape($Msg)
        $Xml = New-Object Windows.Data.Xml.Dom.XmlDocument
        $Xml.LoadXml("<toast><visual><binding template='ToastGeneric'><text>Your brain</text><text>$Escaped</text></binding></visual></toast>")
        $AppId = '{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe'
        [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($AppId).Show(
            [Windows.UI.Notifications.ToastNotification]::new($Xml))
        Add-Content $Log ("notified: " + $Msg)
    } catch {
        Add-Content $Log ("toast failed: " + $_)
    }
} else {
    Add-Content $Log "all quiet, no notification"
}

# The plan to the phone, from HERE: the scheduler runs this at 7:00 or at
# the first wake after, while the in-server bridge only pushes if serve.py
# happens to be up in the window.
& $PyExe @PyPre (Join-Path $Root "brain\tools\telegram_bridge.py") --push-plan 2>&1 | Add-Content $Log
& $PyExe @PyPre (Join-Path $Root "brain\tools\telegram_bridge.py") --push-news 2>&1 | Add-Content $Log

# Keep the log from growing forever.
$Tail = Get-Content $Log -Tail 400
Set-Content $Log $Tail
exit 0

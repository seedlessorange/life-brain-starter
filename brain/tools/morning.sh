#!/usr/bin/env bash
# The 7am run: write today's plan before the owner is up, and only make a
# sound if something genuinely needs them ("no news, no message").
#
# On a Mac this is scheduled by a launchd agent in ~/Library/LaunchAgents
# (e.g. com.lifebrain.today.plist), which runs it under zsh at 07:00 local
# time; if the Mac is asleep then, it runs on the next wake — which usually
# means "when the lid opens". Local time also means it follows the owner
# across cities. On Linux (a server, a Docker cron) the same file runs under
# bash or sh — it is written to the POSIX subset all three shells share, and
# the Mac-only helpers (osascript, caffeinate) step aside when absent.
#
# Cost: one small headless Claude run a day on her subscription. The brain's
# context is a few thousand tokens, so this is cents, not dollars.

[ -n "${ZSH_VERSION:-}" ] && emulate sh   # zsh: POSIX word-splitting etc.
set -u
export PATH="/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin"
# Where the brain is, derived from this script's own location rather than
# assumed to be ~/life-brain — the folder is often kept in Documents, and a
# hardcoded path fails silently at 1am with nobody watching.
SELF="$0"
while [ -L "$SELF" ]; do
  LINKDIR="$(cd "$(dirname "$SELF")" && pwd -P)"
  SELF="$(readlink "$SELF")"
  case "$SELF" in /*) ;; *) SELF="$LINKDIR/$SELF" ;; esac
done
BRAIN_DIR="$(cd "$(dirname "$SELF")/../.." && pwd -P)"
cd "$BRAIN_DIR" || exit 1

# Mac-only comforts, gated so a Linux run is quieter but never broken.
notify() {  # $1 message, $2 sound name (Mac only)
  if command -v osascript > /dev/null 2>&1; then
    osascript -e "display notification \"$1\" with title \"Your brain\" sound name \"$2\"" 2>/dev/null
  elif command -v notify-send > /dev/null 2>&1; then
    notify-send "Your brain" "$1" 2>/dev/null
  fi
}
CAFF=""
command -v caffeinate > /dev/null 2>&1 && CAFF="caffeinate -is"

LOG="$BRAIN_DIR/brain/.morning.log"
echo "--- $(date '+%Y-%m-%d %H:%M') morning run ---" >> "$LOG"

# The smoke test: a quarter of a second, no network, no model. A failure
# does not block the morning — it gets a notification, because a silently
# broken parser is exactly the failure this system exists to prevent.
if ! python3 brain/tools/selftest.py >> "$LOG" 2>&1; then
  notify "Something in the brain is broken — see brain/.morning.log" "Basso"
fi

# Once per day: if today's plan is already dated today, a second wake
# (or a manual test) must not burn a second run.
if grep -q "updated: $(date +%Y-%m-%d)" brain/today.md 2>/dev/null; then
  echo "already ran today, skipping" >> "$LOG"
  exit 0
fi

# Pull who she has actually spoken to, from Beeper's local API. Free, no
# model, no network beyond localhost — and it only works while Beeper is
# open, so a silent failure here is expected and must not stop the run.
python3 brain/tools/beeper.py sync --write >> "$LOG" 2>&1 \
  && echo "beeper sync ok" >> "$LOG" \
  || echo "beeper sync skipped (app closed or not connected)" >> "$LOG"

# Bank feed: balances + transactions into brain/finance/, read-only, no
# model. A lapsed consent (some banks' last a day) is expected and must
# not stop the morning — the page shows each bank's freshness instead.
python3 brain/tools/finance.py fetch >> "$LOG" 2>&1 \
  && echo "bank fetch ok" >> "$LOG" \
  || echo "bank fetch skipped (no key or consent lapsed)" >> "$LOG"

# The day's news briefing: RSS from the outlets in config plus one small
# no-tool Haiku call for the finance breakdown (--explain, cached for the
# day). Dead hotel wifi must not stop the morning.
python3 brain/tools/news.py fetch --explain >> "$LOG" 2>&1 \
  && echo "news fetch ok" >> "$LOG" \
  || echo "news fetch skipped (offline?)" >> "$LOG"

# The job hunt: the public job boards of the companies she follows, read
# for new roles that match (jobs.py; no model call). Off unless config
# `jobs.on` says a search is live.
python3 brain/tools/jobs.py scan --if-on >> "$LOG" 2>&1 \
  && echo "jobs scan ok" >> "$LOG" \
  || echo "jobs scan skipped (offline?)" >> "$LOG"
# Who emailed her (her ask, 8 Oct): the header check, when the morning
# plan's mail switch is on (plan_sources.py). The server runs it: it holds
# the Full Disk Access the Mail app's index needs, and this job does not.
# Mail app only, so never the password and never a Touch ID prompt at 7am;
# names and dates only, never a subject or a body. Before the plan run, so
# the run reads the result and never the mail.
python3 brain/tools/plan_sources.py mail-check >> "$LOG" 2>&1 \
  && echo "mail check ok" >> "$LOG" \
  || echo "mail check skipped (server down, or Mail app reading off)" >> "$LOG"

# The correction rate on the usage page: how often she had to correct
# Claude, counted from her own transcripts (corrections.py; no model call).
python3 brain/tools/corrections.py --json >> "$LOG" 2>&1 \
  && echo "corrections ok" >> "$LOG" \
  || echo "corrections skipped" >> "$LOG"

# The profile she pastes into claude.ai and ChatGPT, rebuilt from the card so
# the page can say when her pasted copy is out of date (context.py; no model).
python3 brain/tools/context.py jarvis --write >> "$LOG" 2>&1 \
  && echo "profile ok" >> "$LOG" \
  || echo "profile skipped" >> "$LOG"

# The weekly lesson tray: one no-tools call turns her week of corrections,
# draft edits and reasons into at most five lessons she keeps or bins on
# For you (lessons.py). Self-gated: a week since the last proposal and three
# new signals, else one line and done. env -u: her subscription, never a key.
env -u ANTHROPIC_API_KEY -u ANTHROPIC_AUTH_TOKEN \
  python3 brain/tools/lessons.py propose --if-due >> "$LOG" 2>&1 \
  && echo "lessons ok" >> "$LOG" \
  || echo "lessons skipped" >> "$LOG"

# Facts whose date has passed ("away until end of September") become
# questions for her, before the plan reads them (stale_facts.py; no model).
python3 brain/tools/stale_facts.py >> "$LOG" 2>&1 \
  && echo "stale facts ok" >> "$LOG" \
  || echo "stale facts skipped" >> "$LOG"

# Task lines she is about to meet that won't read cold ("M4 —…", "Gate:…"):
# one small no-tools call per new or reworded title, at most ten, and its
# wording is only ever offered on For you (tasklint.py). Her subscription.
env -u ANTHROPIC_API_KEY -u ANTHROPIC_AUTH_TOKEN \
  python3 brain/tools/tasklint.py --suggest --max 10 >> "$LOG" 2>&1 \
  && echo "tasklint ok" >> "$LOG" \
  || echo "tasklint skipped" >> "$LOG"

# New slide decks in the class folder, read for the dates they hide. Free
# unless something new turned up, and then one small Haiku call per date
# found. Nothing files itself — it fills a tray she accepts from. A Desktop
# folder that isn't there (another machine) must not stop the morning.
# Class material she downloaded yesterday, still sitting in ~/Downloads.
# Copied in and filed by course from what is printed on it, so she never has
# to sort a folder. Copies only — her Downloads folder is hers.
python3 brain/tools/school.py --catch >> "$LOG" 2>&1 \
  && echo "downloads catch ok" >> "$LOG" \
  || echo "downloads catch skipped" >> "$LOG"

python3 brain/tools/school.py --scan >> "$LOG" 2>&1 \
  && echo "school scan ok" >> "$LOG" \
  || echo "school scan skipped (class folder not on this machine?)" >> "$LOG"

# Fold any new sessions into each course's running guide. Self-gating: the
# text comes out locally for nothing, and a model call happens only once a
# course has accumulated enough new material to be worth one. A week of
# discussion-led classes with thin decks costs nothing until it adds up.
python3 brain/tools/guide.py --all >> "$LOG" 2>&1 \
  && echo "guides ok" >> "$LOG" \
  || echo "guides skipped" >> "$LOG"

# Her Notion class notes, if she has connected Notion. Read-only, and it
# exits quietly when there is no token — which is the normal case until she
# connects it.
python3 brain/tools/notion.py --pull >> "$LOG" 2>&1 \
  && echo "notion pull ok" >> "$LOG" \
  || echo "notion pull skipped (not connected)" >> "$LOG"

# Restore point before an unattended agent touches anything.
git add -A >> "$LOG" 2>&1
git commit -m "pre-morning snapshot" >> "$LOG" 2>&1 || true
# Take what the other machine pushed before planning on top of it. Never
# fatal — an offline morning runs on what this machine already has.
python3 brain/tools/gitsync.py --pull >> "$LOG" 2>&1 || true

# The scheduled Claude run follows the mode — Full runs it, Careful (a Pro
# plan's shared 5-hour window) skips it — unless the Usage page set the
# morning switch explicitly (config `ai_features.morning`). Skipped, the free
# parts above still happened and /today stays a manual, cheap choice.
export MORNING_RUN
# -P everywhere python reads its script from -c or stdin here: without it the
# current folder (the repo root, which a run may write) comes first on the
# import path, and a planted json.py would run outside the sandbox.
MORNING_RUN=$(python3 -P -c "
import json
try:
    cfg = json.load(open('brain/config.json'))
except Exception:
    cfg = {}
mode = 'careful' if cfg.get('ai') in ('low', 'careful', 'pro') else 'full'
ov = (cfg.get('ai_features') or {}).get('morning')
run = (mode == 'full') if not isinstance(ov, bool) else ov
print('run' if run else 'skip')")
if [ "$MORNING_RUN" = "skip" ]; then
  echo "morning Claude run switched off (mode or Usage page): skipping" >> "$LOG"
  python3 brain/tools/rebuild.py >> "$LOG" 2>&1
  STATUS=0
else
  # stdin closed (claude -p hangs forever otherwise). /today needs Bash for
  # the rebuild, which it gets inside the sandbox run_policy.py sets up;
  # git above is still the undo. env -u strips any API key
  # so the run always bills the subscription login, never a key.
  #
  # --output-format json so the run lands in the usage ledger. usage.py
  # prints the plan text back out, so this log stays readable prose.
  # LIFEBRAIN_UNATTENDED makes email_send.py and beeper.py refuse outright:
  # nobody is watching, so the send boundary is code here, not just prose.
  # Private files (config `private`, the journal by default) stay out of
  # this unattended run, two layers deep: --lock chmods them unreadable
  # (the layer that actually holds), and the .unattended marker arms the
  # hook layer (a FILE, not the env var — hooks get a scrubbed
  # environment). The trap undoes both on any exit; a crash self-heals —
  # her next attended session restores the chmod.
  touch "$BRAIN_DIR/brain/.unattended"
  python3 brain/tools/private_gate.py --lock >> "$LOG" 2>&1
  trap 'rm -f "$BRAIN_DIR/brain/.unattended"; python3 "$BRAIN_DIR/brain/tools/private_gate.py" --unlock' EXIT
  RESULT="$BRAIN_DIR/brain/.morning-result.json"
  # caffeinate ($CAFF, Macs only): the 7am wake is brief. Without a sleep
  # assertion the Mac dozes mid-run and this two-minute job stretches to an
  # hour-plus of wake crumbs (the ledger showed 84-minute averages). -i
  # holds off idle sleep, -s holds the system awake while on AC; both end
  # with the run. On Linux there is no lid to close and $CAFF is empty.
  # The calendar is read here, outside the run: inside the sandbox the run
  # cannot drive the Calendar app, and the ten-minute cache means its own
  # calendar_read calls land on these answers. Both spans at once — each
  # read takes most of two minutes.
  python3 brain/tools/calendar_read.py --days 1 > /dev/null 2>&1 &
  python3 brain/tools/calendar_read.py --days 7 > /dev/null 2>&1 &
  wait
  # The bell's line for the plan (activity.py): started now, ended below.
  ACT_ID=$(python3 brain/tools/activity.py start "Plan today" --by morning --kind run 2>>"$LOG")
  # Sandboxed, never bypass: run_policy.py holds the fences and the why.
  env -u ANTHROPIC_API_KEY -u ANTHROPIC_AUTH_TOKEN LIFEBRAIN_UNATTENDED=1 \
    $CAFF python3 brain/tools/run_policy.py run scheduled -- \
    -p "/today Today is $(date '+%A %-d %B %Y')." \
    --output-format json < /dev/null > "$RESULT" 2>>"$LOG"
  STATUS=$?
  if [ -n "$ACT_ID" ]; then
    if [ $STATUS -eq 0 ]; then
      python3 brain/tools/activity.py finish "$ACT_ID" --result-json "$RESULT" \
        --result "Today's plan is written" --href "index.html#/today" \
        --label "Open Today" >> "$LOG" 2>&1
    else
      python3 brain/tools/activity.py finish "$ACT_ID" --failed \
        --result "The plan run failed (exit $STATUS). Its log is in .morning.log" >> "$LOG" 2>&1
    fi
  fi
  rm -f "$BRAIN_DIR/brain/.unattended"
  python3 brain/tools/private_gate.py --unlock >> "$LOG" 2>&1
  python3 brain/tools/usage.py --record "$RESULT" --kind morning \
    --label "morning /today" >> "$LOG" 2>&1
  # What the plan looked at, read from the run's own transcript, for "How
  # this plan was made" under the plan (plan_sources.py). Source names only.
  if [ $STATUS -eq 0 ]; then
    python3 brain/tools/plan_sources.py trace --result "$RESULT" --by morning \
      >> "$LOG" 2>&1 && python3 brain/tools/rebuild.py >> "$LOG" 2>&1
  fi
  rm -f "$RESULT"
  echo "claude exit: $STATUS" >> "$LOG"
  # The scout is a night job, and a laptop left unplugged skips every night
  # (a whole week of that, Sep 22-28, left a stale events list). When the
  # night has missed its week, the morning catches it up — same isolated
  # run, a few minutes, at most once, since a fresh events.md stops it.
  if [ "$(python3 brain/tools/night_config.py --scout-due 2>/dev/null)" = "due" ]; then
    echo "scout: the night missed it this week — catching up" >> "$LOG"
    env -u ANTHROPIC_API_KEY -u ANTHROPIC_AUTH_TOKEN LIFEBRAIN_UNATTENDED=1 \
      $CAFF python3 brain/tools/run_policy.py scout \
      < /dev/null > "$RESULT" 2>>"$LOG" \
      && python3 brain/tools/usage.py --record "$RESULT" --kind morning \
        --label "morning /scout" >> "$LOG" 2>&1
    rm -f "$RESULT"
    python3 brain/tools/build.py >> "$LOG" 2>&1
  fi
fi

git add -A >> "$LOG" 2>&1
git commit -m "morning run $(date +%Y-%m-%d)" >> "$LOG" 2>&1 || true
# Off-machine copy, when config's git_push says this brain pushes (a fork
# of a public starter must not publish a life). Never fatal — dead hotel
# wifi must not break the morning.
python3 brain/tools/gitsync.py --push >> "$LOG" 2>&1 || true

# Threshold-gated notification: silent unless something is actually on fire.
python3 -P - <<'PY' >> "$LOG" 2>&1
import subprocess, sys, os, shutil
# The script already cd'd to the brain, wherever it lives — never assume
# ~/life-brain here or the notification dies silently on other installs.
sys.path.insert(0, os.path.join(os.getcwd(), "brain", "tools"))
import model
b = model.briefing(model.load())
hot = len(b["overdue"]) + len(b["chase"])
import privacy
if privacy.presenting():
    # Presenting mode: her screen may be shared, so the brain stays quiet.
    hot = 0
    print("presenting: no notification")
if hot:
    bits = []
    if b["overdue"]:
        bits.append(f"{len(b['overdue'])} overdue")
    if b["chase"]:
        bits.append(f"{len(b['chase'])} to chase")
    tail = " — plan is ready" if os.environ.get("MORNING_RUN") == "run" else ""
    msg = " and ".join(bits) + tail
    if shutil.which("osascript"):
        subprocess.run(["osascript", "-e",
                        f'display notification "{msg}" with title "Your brain" '
                        f'sound name "Glass"'], timeout=10)
        print(f"notified: {msg}")
    elif shutil.which("notify-send"):
        subprocess.run(["notify-send", "Your brain", msg], timeout=10)
        print(f"notified: {msg}")
    else:
        print(f"hot, but no notifier on this OS: {msg}")
else:
    print("all quiet, no notification")
PY

# The plan to the phone, from HERE: launchd runs this script at 7:00 or at
# the first wake after, while the in-server bridge only pushes if serve.py
# happens to be up in the window — which is exactly what kept failing.
python3 brain/tools/telegram_bridge.py --push-plan >> "$LOG" 2>&1
python3 brain/tools/telegram_bridge.py --push-news >> "$LOG" 2>&1

# Keep the log from growing forever.
tail -n 400 "$LOG" > "$LOG.tmp" && mv "$LOG.tmp" "$LOG"
exit 0

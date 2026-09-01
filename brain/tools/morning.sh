#!/bin/zsh
# The 7am run: write today's plan before the owner is up, and only make a
# sound if something genuinely needs them ("no news, no message").
#
# Scheduled by a launchd agent in ~/Library/LaunchAgents (e.g.
# com.lifebrain.today.plist). launchd runs it at 07:00 local time; if the
# Mac is asleep then, it runs on the next wake — which usually means "when
# the lid opens". Local time also means it follows the owner across cities.
#
# Cost: one small headless Claude run a day on her subscription. The brain's
# context is a few thousand tokens, so this is cents, not dollars.

set -u
export PATH="/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin"
# Where the brain is, derived from this script's own location rather than
# assumed to be ~/life-brain — the folder is often kept in Documents, and a
# hardcoded path fails silently at 1am with nobody watching.
BRAIN_DIR="${0:A:h:h:h}"
cd "$BRAIN_DIR" || exit 1

LOG="$BRAIN_DIR/brain/.morning.log"
echo "--- $(date '+%Y-%m-%d %H:%M') morning run ---" >> "$LOG"

# The smoke test: a quarter of a second, no network, no model. A failure
# does not block the morning — it gets a notification, because a silently
# broken parser is exactly the failure this system exists to prevent.
if ! python3 brain/tools/selftest.py >> "$LOG" 2>&1; then
  osascript -e 'display notification "Something in the brain is broken — see brain/.morning.log" with title "Your brain" sound name "Basso"' 2>/dev/null
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
# model. A lapsed consent (Santander's lasts a day) is expected and must
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
MORNING_RUN=$(python3 -c "
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
  python3 brain/tools/build.py >> "$LOG" 2>&1
  python3 brain/tools/map.py >> "$LOG" 2>&1
  python3 brain/tools/rooms.py >> "$LOG" 2>&1
  python3 brain/tools/proto.py >> "$LOG" 2>&1
  STATUS=0
else
  # stdin closed (claude -p hangs forever otherwise); bypassPermissions
  # because /today needs Bash for the rebuild. The HARD RULES in CLAUDE.md
  # are the guardrails; git above is the undo. env -u strips any API key
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
  # caffeinate: the 7am wake is brief. Without a sleep assertion the Mac
  # dozes mid-run and this two-minute job stretches to an hour-plus of
  # wake crumbs (the ledger showed 84-minute averages). -i holds off idle
  # sleep, -s holds the system awake while on AC; both end with the run.
  env -u ANTHROPIC_API_KEY -u ANTHROPIC_AUTH_TOKEN LIFEBRAIN_UNATTENDED=1 \
    caffeinate -is claude -p "/today" --permission-mode bypassPermissions \
    --output-format json < /dev/null > "$RESULT" 2>>"$LOG"
  STATUS=$?
  rm -f "$BRAIN_DIR/brain/.unattended"
  python3 brain/tools/private_gate.py --unlock >> "$LOG" 2>&1
  python3 brain/tools/usage.py --record "$RESULT" --kind morning \
    --label "morning /today" >> "$LOG" 2>&1
  rm -f "$RESULT"
  echo "claude exit: $STATUS" >> "$LOG"
fi

git add -A >> "$LOG" 2>&1
git commit -m "morning run $(date +%Y-%m-%d)" >> "$LOG" 2>&1 || true
# Off-machine copy: push when a remote exists. Never fatal — dead hotel
# wifi must not break the morning.
if git remote get-url origin > /dev/null 2>&1; then
  git push -q origin HEAD >> "$LOG" 2>&1 || echo "push failed (offline?)" >> "$LOG"
fi

# Threshold-gated notification: silent unless something is actually on fire.
python3 - <<'PY' >> "$LOG" 2>&1
import subprocess, sys, os
# The script already cd'd to the brain, wherever it lives — never assume
# ~/life-brain here or the notification dies silently on other installs.
sys.path.insert(0, os.path.join(os.getcwd(), "brain", "tools"))
import model
b = model.briefing(model.load())
hot = len(b["overdue"]) + len(b["chase"])
if hot:
    bits = []
    if b["overdue"]:
        bits.append(f"{len(b['overdue'])} overdue")
    if b["chase"]:
        bits.append(f"{len(b['chase'])} to chase")
    tail = " — plan is ready" if os.environ.get("MORNING_RUN") == "run" else ""
    msg = " and ".join(bits) + tail
    subprocess.run(["osascript", "-e",
                    f'display notification "{msg}" with title "Your brain" '
                    f'sound name "Glass"'], timeout=10)
    print(f"notified: {msg}")
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

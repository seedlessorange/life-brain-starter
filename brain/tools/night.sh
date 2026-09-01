#!/bin/zsh
# The night shift: do the heavy, slow work while nobody is waiting for it.
#
# WHY 01:00 AND NOT 03:00. Claude subscriptions meter usage in rolling
# five-hour windows. A window opens on the first call and closes five hours
# later. Starting at 01:00 means the night window is 01:00–06:00 and has
# closed before the 07:00 morning plan opens a fresh one — so the night's work
# and the morning's plan never compete for the same allowance. Move this to
# 03:00 and the two share a window, which is exactly what this exists to
# avoid. If you change the hour, keep it at least five hours before the
# morning run.
#
# WHAT IT DOES NOT DO. It has the same hands as any other run and the same
# boundary: it drafts, files and tidies. It sends nothing, submits nothing and
# buys nothing — the HARD RULES in CLAUDE.md apply to an unattended run more
# than to any other, and git is the undo.
#
# Scheduled by ~/Library/LaunchAgents/com.lifebrain.night.plist
# (run `brain/tools/setup_night.sh` once to install it).

set -u
# launchd hands over a nearly empty PATH, so this rebuilds it. The extra
# entries cover the usual npm/nvm/pipx install spots: an unattended run that
# cannot find `claude` fails at 01:00 with nobody watching, so it is worth
# looking in more places than the morning run bothers with.
export PATH="/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:$HOME/.local/bin:$HOME/.npm-global/bin:$HOME/bin"
if [ -d "$HOME/.nvm/versions/node" ]; then
  for d in "$HOME"/.nvm/versions/node/*/bin(N); do PATH="$PATH:$d"; done
fi
# Where the brain is, derived from this script's own location rather than
# assumed to be ~/life-brain — the folder is often kept in Documents, and a
# hardcoded path fails silently at 1am with nobody watching.
BRAIN_DIR="${0:A:h:h:h}"
cd "$BRAIN_DIR" || exit 1

LOG="$BRAIN_DIR/brain/.night.log"
REPORT="$BRAIN_DIR/brain/.night-report.md"
echo "--- $(date '+%Y-%m-%d %H:%M') night shift ---" >> "$LOG"

CFG=$(python3 brain/tools/night_config.py 2>/dev/null)
if [ -z "$CFG" ]; then
  echo "no night config, or config.json unreadable — nothing to do" >> "$LOG"
  exit 0
fi
eval "$CFG"        # sets NIGHT_ENABLED, NIGHT_JOBS, NIGHT_MODEL, NIGHT_BATTERY

if [ "$NIGHT_ENABLED" != "1" ]; then
  echo "night shift is off (config.json: night.enabled)" >> "$LOG"
  exit 0
fi

# A laptop asleep at 01:00 makes launchd fire this the moment the lid opens —
# which could be 09:15, mid-coffee, with the machine suddenly busy for twenty
# minutes. The night shift is only allowed to run at night.
HOUR=$(date +%-H)
if [ "$HOUR" -ge 6 ] && [ "$HOUR" -lt 23 ]; then
  echo "woke at ${HOUR}h — outside the night window, skipping (this is normal)" >> "$LOG"
  exit 0
fi

# Once per night. A second wake must not run the whole shift again. "Tonight"
# is the last 20 hours, not the calendar date — the 23:00–06:00 window
# straddles midnight, so a 23:40 run and the 01:00 run land on different
# dates and a date comparison would happily run both.
if [ -f "$REPORT" ] && [ $(( $(date +%s) - $(date -r "$REPORT" +%s) )) -lt 72000 ]; then
  echo "already ran tonight, skipping" >> "$LOG"
  exit 0
fi

# On battery this would drain the machine flat by morning. Desktops report no
# battery at all, which pmset prints as "AC Power" — so they always pass.
if [ "$NIGHT_BATTERY" != "1" ]; then
  if ! pmset -g batt 2>/dev/null | grep -q "AC Power"; then
    echo "on battery — skipping (set night.on_battery true to override)" >> "$LOG"
    exit 0
  fi
fi

if ! command -v claude > /dev/null 2>&1; then
  echo "claude is not on PATH — nothing to run. Add its folder to the PATH" >> "$LOG"
  echo "line at the top of this script, or reinstall Claude Code." >> "$LOG"
  exit 0
fi

# The smoke test, so a broken parser is on record before an unattended
# agent works on top of it. Logged, never fatal.
python3 brain/tools/selftest.py >> "$LOG" 2>&1 \
  || echo "SELFTEST FAILED — see above" >> "$LOG"

# Beeper is usually still open overnight; free either way.
python3 brain/tools/beeper.py sync --write >> "$LOG" 2>&1 \
  && echo "beeper sync ok" >> "$LOG" \
  || echo "beeper sync skipped" >> "$LOG"

# Restore point before an unattended agent touches anything.
git add -A >> "$LOG" 2>&1
git commit -m "pre-night snapshot" >> "$LOG" 2>&1 || true
# Take what the other machine pushed before working on top of it.
python3 brain/tools/gitsync.py --pull >> "$LOG" 2>&1 || true

echo "# Last night" > "$REPORT"
echo "" >> "$REPORT"
echo "_$(date '+%A %-d %B, %H:%M')_" >> "$REPORT"
echo "" >> "$REPORT"

# Private files (config `private`, the journal by default) stay out of the
# unattended runs, two layers deep. --lock chmods them unreadable — the layer
# that actually holds, since the OS refuses the open no matter what a run
# decides to do. The .unattended marker file arms the hook layer as well
# (a FILE, not the env var: Claude Code hands hooks a scrubbed environment).
# The trap undoes both however this script exits; a crash self-heals anyway —
# the gate ignores a stale marker and her next attended session restores
# the chmod.
touch "$BRAIN_DIR/brain/.unattended"
python3 brain/tools/private_gate.py --lock >> "$LOG" 2>&1
trap 'rm -f "$BRAIN_DIR/brain/.unattended"; python3 "$BRAIN_DIR/brain/tools/private_gate.py" --unlock' EXIT

RESULT="$BRAIN_DIR/brain/.night-result.json"
for JOB in ${(s: :)NIGHT_JOBS}; do
  # /scout is weekly by design: when events.md is under 6 days old, skip
  # before starting a claude run at all. The command self-gates on the same
  # date too — this check just makes the usual outcome free.
  if [ "$JOB" = "scout" ] && [ -f brain/events.md ] \
     && [ $(( $(date +%s) - $(date -r brain/events.md +%s) )) -lt 518400 ]; then
    echo "scout: events.md under 6 days old — weekly job, skipping" >> "$LOG"
    continue
  fi
  echo "--- running /$JOB ---" >> "$LOG"
  START=$(date +%s)
  # caffeinate: hold the Mac awake for the run's real few minutes rather
  # than letting it doze mid-job and crawl (same fix as morning.sh).
  env -u ANTHROPIC_API_KEY -u ANTHROPIC_AUTH_TOKEN LIFEBRAIN_UNATTENDED=1 \
    caffeinate -is claude -p "/$JOB" --permission-mode bypassPermissions \
    --model "$NIGHT_MODEL" --output-format json \
    < /dev/null > "$RESULT" 2>>"$LOG"
  CODE=$?
  echo "" >> "$REPORT"
  echo "## /$JOB" >> "$REPORT"
  echo "" >> "$REPORT"
  if [ $CODE -eq 0 ]; then
    python3 brain/tools/usage.py --record "$RESULT" --kind night \
      --label "night /$JOB" --model "$NIGHT_MODEL" >> "$REPORT" 2>>"$LOG"
  else
    echo "That run failed (exit $CODE). Nothing was lost." >> "$REPORT"
    echo "/$JOB failed with $CODE" >> "$LOG"
  fi
  echo "/$JOB done in $(( $(date +%s) - START ))s (exit $CODE)" >> "$LOG"
  rm -f "$RESULT"
done
rm -f "$BRAIN_DIR/brain/.unattended"
python3 brain/tools/private_gate.py --unlock >> "$LOG" 2>&1

python3 brain/tools/build.py >> "$LOG" 2>&1
python3 brain/tools/map.py >> "$LOG" 2>&1
python3 brain/tools/rooms.py >> "$LOG" 2>&1
python3 brain/tools/proto.py >> "$LOG" 2>&1

git add -A >> "$LOG" 2>&1
git commit -m "night shift $(date +%Y-%m-%d)" >> "$LOG" 2>&1 || true
# Off-machine copy: push when a remote exists. Never fatal.
if git remote get-url origin > /dev/null 2>&1; then
  git push -q origin HEAD >> "$LOG" 2>&1 || echo "push failed (offline?)" >> "$LOG"
fi

# What it cost, appended to the report so the morning can see it in one place.
{
  echo ""
  echo "---"
  echo ""
  python3 brain/tools/usage.py --days 1 2>/dev/null | head -6
} >> "$REPORT"

tail -n 500 "$LOG" > "$LOG.tmp" && mv "$LOG.tmp" "$LOG"
echo "night shift finished" >> "$LOG"
exit 0

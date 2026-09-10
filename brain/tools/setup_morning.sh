#!/bin/zsh
# Install (or remove) the 7am morning run on a Mac.
#
#   zsh brain/tools/setup_morning.sh          # schedule it
#   zsh brain/tools/setup_morning.sh --off    # unschedule it
#
# The Windows side has had a one-command installer since the beginning
# (setup_morning.ps1); this is its Mac counterpart, so neither platform
# needs a human to hand-write a launchd agent.
#
# Safe to re-run: it rewrites the agent and reloads it.

set -u
# Where the brain is, derived from this script's own location rather than
# assumed to be ~/life-brain — the folder is often kept in Documents, and a
# hardcoded path fails silently at 1am with nobody watching.
BRAIN_DIR="${0:A:h:h:h}"
cd "$BRAIN_DIR" || exit 1
LABEL="com.lifebrain.morning"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
# Earlier installs used per-person labels ending in lifebrain-today. Retire
# any of them whenever this script runs, or --off leaves the real 7am agent
# running and a re-install schedules the morning twice.
for OLD_PLIST in "$HOME/Library/LaunchAgents"/com.*.lifebrain-today.plist; do
  [ -f "$OLD_PLIST" ] || continue
  launchctl unload "$OLD_PLIST" 2>/dev/null
  rm -f "$OLD_PLIST"
  echo "(retired the old $(basename "$OLD_PLIST" .plist) agent)"
done

if [ "${1:-}" = "--off" ]; then
  launchctl unload "$PLIST" 2>/dev/null
  rm -f "$PLIST"
  echo "Mornings are manual again. Nothing else changed."
  exit 0
fi

# launchd runs this at 07:00 local time. If the Mac is asleep then, it runs
# on the next wake — which usually means when the lid opens. Local time also
# means it follows you across cities.
mkdir -p "$HOME/Library/LaunchAgents"
cat > "$PLIST" <<PLISTEOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>$LABEL</string>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/zsh</string>
        <string>$BRAIN_DIR/brain/tools/morning.sh</string>
    </array>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>7</integer>
        <key>Minute</key>
        <integer>0</integer>
    </dict>
    <key>StandardOutPath</key>
    <string>$BRAIN_DIR/brain/.morning-launchd.log</string>
    <key>StandardErrorPath</key>
    <string>$BRAIN_DIR/brain/.morning-launchd.log</string>
</dict>
</plist>
PLISTEOF

launchctl unload "$PLIST" 2>/dev/null
launchctl load "$PLIST" 2>/dev/null

echo "Mornings are on. At 7:00 the brain syncs your folders, rebuilds the"
echo "page, and notifies you only if something is genuinely overdue."
echo ""
if python3 -c "
import json,sys
try: sys.exit(0 if json.load(open('brain/config.json')).get('ai') in ('low','careful','pro') else 1)
except Exception: sys.exit(1)" 2>/dev/null; then
  echo "You are in careful mode, so the 7am run does only the free parts"
  echo "(sync, rebuild, notify) and spends nothing."
else
  echo "You are in full mode, so the 7am run also writes your daily plan."
fi

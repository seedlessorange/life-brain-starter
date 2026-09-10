#!/bin/zsh
# Install (or refresh) the night-shift schedule on a Mac.
#
#   zsh brain/tools/setup_night.sh          # install at the configured hour
#   zsh brain/tools/setup_night.sh --off    # unschedule it
#
# Safe to re-run: it rewrites the agent and reloads it. The schedule comes
# from config.json (night.at) so there is one place to change the hour.

set -u
# Where the brain is, derived from this script's own location rather than
# assumed to be ~/life-brain — the folder is often kept in Documents, and a
# hardcoded path fails silently at 1am with nobody watching.
BRAIN_DIR="${0:A:h:h:h}"
cd "$BRAIN_DIR" || exit 1
LABEL="com.lifebrain.night"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"

if [ "${1:-}" = "--off" ]; then
  launchctl unload "$PLIST" 2>/dev/null
  rm -f "$PLIST"
  echo "Night shift unscheduled. brain/config.json still holds your settings."
  exit 0
fi

eval "$(python3 brain/tools/night_config.py)"
HOUR="${NIGHT_AT%%:*}"
MIN="${NIGHT_AT##*:}"
HOUR=$((10#$HOUR)); MIN=$((10#$MIN))

# A desktop that is awake at 01:00 runs it then. A Mac asleep at 01:00 runs it
# on the next wake — which night.sh refuses if that wake is in daylight, so a
# closed laptop simply skips the night rather than surprising you at 09:15.
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
        <string>$BRAIN_DIR/brain/tools/night.sh</string>
    </array>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>$HOUR</integer>
        <key>Minute</key>
        <integer>$MIN</integer>
    </dict>
    <key>StandardOutPath</key>
    <string>$BRAIN_DIR/brain/.night-launchd.log</string>
    <key>StandardErrorPath</key>
    <string>$BRAIN_DIR/brain/.night-launchd.log</string>
</dict>
</plist>
PLISTEOF

launchctl unload "$PLIST" 2>/dev/null
launchctl load "$PLIST" 2>/dev/null

echo "Night shift scheduled for ${NIGHT_AT} — jobs: ${NIGHT_JOBS} on ${NIGHT_MODEL}."
if [ "$NIGHT_ENABLED" != "1" ]; then
  echo ""
  echo "It is still switched OFF in brain/config.json. Set night.enabled to"
  echo "true there (or use the Night shift control on the page) to start it."
fi

# A Mac that is fully asleep runs nothing. This asks it to wake for the job.
# It needs your password, so it is offered rather than done.
echo ""
echo "A sleeping Mac will not run this until you next open it. To have it wake"
echo "itself instead:"
echo "  sudo pmset repeat wakeorpoweron MTWRFSU ${NIGHT_AT}:00"

#!/bin/zsh
# What Brain Server.app runs: start, stop, open, busy, ensure.
#
# Kept outside the app on purpose. macOS ties Full Disk Access to the app's
# exact build, so the app is a fixed few lines that call this file, and
# everything that may change lives here, where editing it never costs her
# the permission. The server started from here inherits the app's access
# (Voice Memos, Mail's index); Terminal needs none.
cd "${0:A:h}/../.." || exit 1

PORT="${BRAIN_PORT:-7718}"
URL="http://127.0.0.1:$PORT/"
PIDF=brain/.serve.pid
LOG=brain/.serve.log

listening() { lsof -nP -iTCP:$PORT -sTCP:LISTEN >/dev/null 2>&1 }
ours() { local p; p=$(cat "$PIDF" 2>/dev/null); [ -n "$p" ] && kill -0 "$p" 2>/dev/null }

start() {
  print "$(date '+%F %T')  starting (Brain Server)" >> "$LOG"
  BRAIN_BIND=tailnet nohup python3 brain/tools/serve.py >> "$LOG" 2>&1 < /dev/null &
  print $! > "$PIDF"
}

case "$1" in
  start)
    # Already up (this app's server, or one started by hand): show the page.
    if listening; then open "$URL"; else start; fi
    ;;
  open)
    open "$URL"
    ;;
  busy)
    # A Claude run in progress: stopping now would cut it off mid-edit.
    if curl -s -m 3 "${URL}api/agent" | grep -q '"running": true'; then
      print yes
    else
      print no
    fi
    ;;
  ensure)
    # The app's heartbeat. If its server died, bring it back — at most once
    # every five minutes, so a server that cannot start does not loop.
    if ! listening && ! ours; then
      if [ ! -f "$PIDF" ] || [ -n "$(find "$PIDF" -mmin +5 2>/dev/null)" ]; then
        print "$(date '+%F %T')  the server had stopped; restarting" >> "$LOG"
        start
      fi
    fi
    ;;
  stop)
    p=$(cat "$PIDF" 2>/dev/null)
    if [ -n "$p" ] && kill -0 "$p" 2>/dev/null; then
      kill "$p"
      for i in {1..20}; do kill -0 "$p" 2>/dev/null || break; sleep 0.5; done
      kill -0 "$p" 2>/dev/null && kill -9 "$p"
      print "$(date '+%F %T')  stopped (Brain Server quit)" >> "$LOG"
    fi
    rm -f "$PIDF"
    ;;
  *)
    print "usage: brain_app.sh start|stop|open|busy|ensure" >&2
    exit 2
    ;;
esac

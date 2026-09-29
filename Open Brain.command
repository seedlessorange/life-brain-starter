#!/bin/zsh
# Double-click me to start the brain.
cd "${0:A:h}" || exit 1

# Closes this window when the brain stops, so dead windows don't pile up.
[ -f brain/tools/window.sh ] && source brain/tools/window.sh
type brain_window_remember >/dev/null 2>&1 && brain_window_remember

PORT="${BRAIN_PORT:-7718}"
URL="http://127.0.0.1:$PORT/"

# Where Brain Server.app has been built (brain/tools/make_brain_app.sh), it is how
# the brain starts on this Mac: it holds Full Disk Access for Voice Memos and
# Mail's index, so Terminal doesn't have to.
if [ -d "Brain Server.app" ] && [ -z "$BRAIN_IN_TERMINAL" ]; then
  open "Brain Server.app"
  sleep 1
  type brain_window_close >/dev/null 2>&1 && brain_window_close
  exit 0
fi

# Already running? Don't start a second one that can't have the port — show
# the page that is already up and get this window out of the way.
if lsof -nP -iTCP:$PORT -sTCP:LISTEN >/dev/null 2>&1; then
  print ""
  print "  Your brain is already running at  $URL"
  print "  Opening it now."
  print ""
  open "$URL" 2>/dev/null
  sleep 2
  type brain_window_close >/dev/null 2>&1 && brain_window_close
  exit 0
fi

BRAIN_BIND=tailnet python3 brain/tools/serve.py
rc=$?

# Ctrl-C is a clean stop (0, or 130 if the shell sees the signal first) and
# the window goes. Anything else went wrong, so the window stays and the
# error above stays readable.
if [ $rc -eq 0 ] || [ $rc -eq 130 ]; then
  type brain_window_close >/dev/null 2>&1 && brain_window_close
else
  print ""
  print "  The brain stopped with an error (code $rc)."
  print "  What went wrong is printed above. Press Return to close this window."
  read -r _
  type brain_window_close >/dev/null 2>&1 && brain_window_close
fi

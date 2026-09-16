#!/bin/zsh
# Double-click me to start the brain.
cd "${0:A:h}" || exit 1

# Closes this window when the brain stops, so dead windows don't pile up.
[ -f brain/tools/window.sh ] && source brain/tools/window.sh
type brain_window_remember >/dev/null 2>&1 && brain_window_remember

PORT="${BRAIN_PORT:-7718}"
URL="http://127.0.0.1:$PORT/"

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
status=$?

# Ctrl-C is a clean stop (0, or 130 if the shell sees the signal first) and
# the window goes. Anything else went wrong, so the window stays and the
# error above stays readable.
if [ $status -eq 0 ] || [ $status -eq 130 ]; then
  type brain_window_close >/dev/null 2>&1 && brain_window_close
else
  print ""
  print "  The brain stopped with an error (code $status)."
  print "  What went wrong is printed above. Press Return to close this window."
  read -r _
  type brain_window_close >/dev/null 2>&1 && brain_window_close
fi

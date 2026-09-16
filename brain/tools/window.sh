# Close the Terminal window a double-clicked .command ran in.
#
# macOS leaves the window open after the script ends, showing "[Process
# completed]", and Terminal's session restore brings those corpses back the
# next morning. Ten of them had piled up before anyone noticed (16 Sep 2026).
# Sourced by the .command launchers; silent on anything that isn't Apple
# Terminal, so Linux and iTerm users lose nothing.

BRAIN_WINDOW_ID=""

# Call at the top of the script, while the window still has a live tab.
brain_window_remember() {
  [ "$TERM_PROGRAM" = "Apple_Terminal" ] || return 0
  command -v osascript >/dev/null 2>&1 || return 0
  local mytty
  mytty="$(tty 2>/dev/null)" || return 0
  # Match on the tty AND on the tab being busy. Terminal recycles tty names,
  # so a long-dead window can carry the same one; only ours is running this.
  BRAIN_WINDOW_ID="$(osascript 2>/dev/null <<APPLESCRIPT
tell application "Terminal"
  repeat with w in windows
    try
      repeat with tb in tabs of w
        try
          if (busy of tb is true) and (tty of tb is "$mytty") then return id of w
        end try
      end repeat
    end try
  end repeat
  return ""
end tell
APPLESCRIPT
)"
}

# Call on the way out. The close is fired from a detached process after a
# short delay: the window is still busy with this very script right now, and
# Terminal would ask before closing a busy window.
brain_window_close() {
  [ -n "$BRAIN_WINDOW_ID" ] || return 0
  nohup osascript \
    -e "delay 0.6" \
    -e "tell application \"Terminal\" to close (every window whose id is $BRAIN_WINDOW_ID) saving no" \
    >/dev/null 2>&1 &
  disown >/dev/null 2>&1
  return 0
}

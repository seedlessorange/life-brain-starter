#!/bin/zsh
# Double-click me to find out what's missing. Reads nothing, changes
# nothing, installs nothing — it just looks and tells you.
#
# Written for someone who has never opened Terminal, so every failure
# states the fix in full rather than naming the problem and stopping.

cd "${0:A:h}" || exit 1

PY=0; CLAUDE=0; GIT=0; FILES=0; RUNNING=0

command -v python3 >/dev/null 2>&1 && PY=1
command -v claude  >/dev/null 2>&1 && CLAUDE=1
command -v git     >/dev/null 2>&1 && GIT=1
[ -f "brain/tools/serve.py" ] && FILES=1
# lsof is the reliable check on macOS; nc as a fallback if it's restricted.
if lsof -nP -iTCP:7718 -sTCP:LISTEN >/dev/null 2>&1; then RUNNING=1; fi

print ""
print "  ============================================"
print "    Life brain — setup check"
print "  ============================================"
print ""

if [ $PY -eq 1 ]; then
  print "  [ OK ]  Python is installed."
else
  print "  [MISSING]  Python"
  print ""
  print "      The page cannot run without it."
  print ""
  print "      Easiest fix: in this window, type the line below and"
  print "      press Return. macOS offers to install its developer"
  print "      tools, which include Python. Click Install and wait."
  print ""
  print "          xcode-select --install"
  print ""
  print "      Or download it from https://www.python.org/downloads/"
  print ""
fi

if [ $CLAUDE -eq 1 ]; then
  print "  [ OK ]  Claude Code is installed."
else
  print "  [MISSING]  Claude Code"
  print ""
  print "      The page still works without it, but the brain will"
  print "      not maintain itself."
  print ""
  print "      Install it from  https://claude.com/claude-code"
  print "      and follow the Mac instructions on that page."
  print ""
  print "      Already installed it? Close this window, open a NEW"
  print "      one, and run this check again. A window opened before"
  print "      the install cannot see it."
  print ""
fi

if [ $GIT -eq 1 ]; then
  print "  [ OK ]  Git is installed (this is your undo button)."
else
  print "  [MISSING]  Git"
  print ""
  print "      Everything still works without it, but you lose the"
  print "      safety net: the brain snapshots your files before and"
  print "      after every job, and that is what makes a bad edit"
  print "      undoable."
  print ""
  print "      Fix: type  xcode-select --install  and click Install."
  print "      That gets you Git and Python together."
  print ""
fi

if [ $FILES -eq 1 ]; then
  print "  [ OK ]  The brain's files are all here."
  # The brain ships its own smoke test — 44-odd checks over the parser, the
  # send boundary and the data files, in about a second with no network and
  # no model. Worth running here: everything above only proves the machine
  # is ready, this proves the brain itself is.
  if [ $PY -eq 1 ]; then
    if python3 brain/tools/selftest.py >/tmp/lb-selftest.$$ 2>&1; then
      print "  [ OK ]  $(tail -1 /tmp/lb-selftest.$$)"
    else
      print "  [PROBLEM]  The brain's own checks did not all pass:"
      sed 's/^/            /' /tmp/lb-selftest.$$ | tail -12
      print ""
      print "      Run \`claude\` in this folder and paste the lines above."
      print ""
    fi
    rm -f /tmp/lb-selftest.$$
  fi
else
  print "  [PROBLEM]  This folder is incomplete."
  print ""
  print "      Some files are missing. The usual cause is running"
  print "      this from inside the zip instead of unzipping first."
  print "      Double-click the zip to expand it, then run this from"
  print "      the folder it creates."
  print ""
fi

if [ $RUNNING -eq 1 ]; then
  print "  [ OK ]  The page is running right now."
  print "            Open  http://127.0.0.1:7718  in your browser."
else
  print "  [ -- ]  The page is not running."
  print "            That is fine — double-click \"Open Brain.command\""
  print "            to start it whenever you want to use it."
fi

print ""
print "  --------------------------------------------"
if [ $PY -eq 1 ] && [ $CLAUDE -eq 1 ] && [ $FILES -eq 1 ]; then
  print "    You are fully set up."
  print ""
  print "    Next: double-click \"Open Brain.command\", then follow"
  print "    Step 5 onward in \"START HERE (Mac).md\"."
else
  print "    Fix the items marked MISSING or PROBLEM above, then"
  print "    run this again."
  print ""
  print "    The full walkthrough is in \"START HERE (Mac).md\"."
fi
print "  --------------------------------------------"
print ""
print "  Press Return to close this window."
read -r _

#!/usr/bin/env python3
"""Write time blocks into ONE calendar she chooses — and nowhere else.

The leash, stated once and enforced in code: this module only ever ADDS
events, only to the single target calendar, and never reads, moves,
edits or deletes anything anywhere. Delete that calendar (or its events)
in the Calendar app and every trace of this feature is gone.

The target is `calendar_target` in config.json. Unset, it creates and
uses a local calendar named "Brain" — private to the Mac, invisible to
her phone. Pointing it at a calendar that belongs to an ACCOUNT (her
HEC/Exchange one, iCloud) is what makes blocks show up in Outlook on
her phone, because the account syncs them.

Blocks are proposals made real: the page asks, she picks the slot, this
writes it. Nothing here runs on a schedule.
"""
import json
import os
import subprocess
import sys
from datetime import datetime

CAL = "Brain"
HERE = os.path.dirname(os.path.abspath(__file__))
BRAIN = os.path.dirname(HERE)


def target():
    """The calendar blocks go to. "" means the local Brain calendar."""
    try:
        with open(os.path.join(BRAIN, "config.json"), encoding="utf-8") as f:
            return (json.load(f).get("calendar_target") or "").strip()
    except Exception:
        return ""


_LIST = '''
tell application "Calendar"
  set out to ""
  repeat with c in calendars
    try
      if writable of c then set out to out & (name of c) & linefeed
    end try
  end repeat
end tell
return out
'''


def calendars():
    """Writable calendar names — the ones a block could legally land in."""
    if sys.platform != "darwin":
        return []
    try:
        r = subprocess.run(["osascript", "-e", _LIST],
                           capture_output=True, text=True, timeout=45)
    except Exception:
        return []
    if r.returncode != 0:
        return []
    seen, out = set(), []
    for ln in (r.stdout or "").splitlines():
        n = ln.strip()
        # Birthday/holiday feeds report writable but are nobody's workspace.
        if not n or n.lower() in seen:
            continue
        if any(k in n.lower() for k in ("birthday", "holiday", "fête", "fete",
                                        "siri", "reminder")):
            continue
        seen.add(n.lower())
        out.append(n)
    return out

_SCRIPT = '''
tell application "Calendar"
  if not (exists calendar "{cal}") then
    make new calendar with properties {{name:"{cal}"}}
    delay 1
  end if
  set d1 to current date
  set year of d1 to {y}
  set month of d1 to {mo}
  set day of d1 to {d}
  set hours of d1 to {h}
  set minutes of d1 to {mi}
  set seconds of d1 to 0
  set d2 to d1 + ({mins} * minutes)
  tell calendar "{cal}"
    make new event with properties {{summary:"{title}", start date:d1, end date:d2}}
  end tell
end tell
'''


def block(title, when, minutes, cal=None):
    """Create one block. `when` is a datetime, `minutes` its length.
    `cal` overrides the configured target. Raises with a plain sentence
    when the Mac says no."""
    if sys.platform != "darwin":
        raise RuntimeError("calendar blocks only work on the Mac")
    minutes = max(15, min(8 * 60, int(minutes)))
    safe = str(title).replace("\\", "").replace('"', "'").strip()[:120]
    if not safe:
        raise ValueError("the block needs a title")
    dest = (cal or target() or CAL).replace('"', "")
    if dest != CAL and dest not in calendars():
        raise ValueError(f"no writable calendar called {dest!r} — pick "
                         "another one in Connections")
    script = _SCRIPT.format(cal=dest, title=safe, y=when.year, mo=when.month,
                            d=when.day, h=when.hour, mi=when.minute,
                            mins=minutes)
    r = subprocess.run(["osascript", "-e", script],
                       capture_output=True, text=True, timeout=45)
    if r.returncode != 0:
        err = (r.stderr or "").strip().splitlines()
        raise RuntimeError("the Calendar app refused: "
                           + (err[-1] if err else "unknown error"))
    return {"title": safe, "start": when.isoformat(timespec="minutes"),
            "minutes": minutes, "calendar": dest}


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("title")
    ap.add_argument("--at", required=True, help="YYYY-MM-DDTHH:MM")
    ap.add_argument("--minutes", type=int, default=60)
    a = ap.parse_args()
    print(block(a.title, datetime.fromisoformat(a.at), a.minutes))

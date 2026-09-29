#!/usr/bin/env python3
"""Read the night-shift settings out of config.json as shell variables.

    eval "$(python3 brain/tools/night_config.py)"

The shell scripts must not parse JSON themselves — zsh and PowerShell would
each need their own parser and they would drift. This prints one form both
can eval, and is the single place the defaults live.

Config shape, under `"night"` in brain/config.json:

    "night": {
      "enabled": false,          the whole thing, off by default
      "at": "01:00",             read by setup_night.sh when scheduling
      "jobs": ["queue", "wrap"], run in order, one at a time
      "model": "",               "" follows the default model (the Usage page's
                                 pick if set, else careful -> haiku)
      "on_battery": false        laptops: false skips unless plugged in,
                                 true runs unplugged, a number (50) runs
                                 unplugged only above that charge
    }
"""

import json
import os
import re
import shlex
import sys
import time
from datetime import date, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
BRAIN = os.path.dirname(HERE)

DEFAULTS = {"enabled": False, "at": "01:00", "jobs": ["queue"],
            "model": "", "on_battery": False}
# The jobs an unattended run may do. /today is deliberately absent: the morning
# plan must be written in the morning, against the day it is planning. Every
# name here must exist in .claude/commands/ — the night runs `claude -p /job`.
ALLOWED = {"queue", "wrap", "sync", "brief", "discover", "scout"}


def load():
    try:
        with open(os.path.join(BRAIN, "config.json"), encoding="utf-8") as f:
            cfg = json.load(f)
    except Exception:
        cfg = {}
    night = dict(DEFAULTS, **(cfg.get("night") or {}))
    jobs = [j for j in (night.get("jobs") or []) if j in ALLOWED]
    night["jobs"] = jobs or ["queue"]
    if not night.get("model"):
        # Same resolution as every other run: the Usage page's explicit
        # default model if set, else the mode's.
        ov = (cfg.get("ai_features") or {}).get("model")
        if ov in ("haiku", "sonnet", "opus", "fable"):
            night["model"] = ov
        else:
            careful = cfg.get("ai") in ("low", "careful", "pro")
            night["model"] = "haiku" if careful else "sonnet"
    # setup_night.sh does arithmetic on the hour and minute, and a shell
    # evaluates what it finds inside arithmetic: only a real time passes.
    if not re.fullmatch(r"\d{1,2}:\d{2}", str(night.get("at") or "")):
        night["at"] = DEFAULTS["at"]
    return night


# A skip is one line under the night's header. These are the ones worth
# telling her about, in the words the page shows; "already ran" and "woke
# outside the window" are the shift working as designed.
SKIPS = {"on battery": "the Mac was unplugged",
         "claude is not on PATH": "Claude Code wasn't found",
         "night shift is off": "it was switched off"}


def recent(days=14):
    """The last nights, newest first: (date, None) for a night that ran,
    (date, reason) for one that skipped. Read from the night log, because
    its timestamp alone says "last ran" on nights that did nothing."""
    try:
        with open(os.path.join(BRAIN, ".night.log"), encoding="utf-8") as f:
            lines = f.read().splitlines()
    except OSError:
        return []
    nights, cur = {}, None
    for ln in lines:
        m = re.match(r"--- (\d{4}-\d{2}-\d{2}) (\d{2}):\d{2} night shift ---", ln)
        if m:
            cur = m.group(1)
            # A 23:xx run belongs to the night after it.
            if int(m.group(2)) >= 23:
                cur = (date.fromisoformat(cur) + timedelta(days=1)).isoformat()
            continue
        if cur is None:
            continue
        if ln.startswith("--- running /") or ln == "night shift finished":
            nights[cur] = None
        else:
            for key, why in SKIPS.items():
                if ln.startswith(key) and nights.get(cur, "x") is not None:
                    nights[cur] = why
    return sorted(nights.items(), reverse=True)[:days]


def skipped_streak():
    """(nights, reason) for the unbroken run of skipped nights up to now,
    or (0, "") when the last night that mattered ran."""
    n, why = 0, ""
    for _d, reason in recent():
        if reason is None:
            break
        n, why = n + 1, why or reason
    return n, why


def scout_due(max_days=8):
    """True when the weekly scout is one of the night's jobs and the night
    has missed it: events.md older than a week and a day. The morning run
    catches it up then, so an unplugged week still gets its list."""
    n = load()
    if not n.get("enabled") or "scout" not in n["jobs"]:
        return False
    try:
        age = os.path.getmtime(os.path.join(BRAIN, "events.md"))
    except OSError:
        return True
    return time.time() - age > max_days * 86400


def battery_min(n):
    """The lowest charge the shift may run on unplugged: 101 for never
    (false), 0 for always (true), else the percentage she set."""
    v = n.get("on_battery")
    if v is True:
        return 0
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return max(0, min(100, int(v)))
    return 101


def _ps(value):
    """A PowerShell single-quoted literal: nothing inside it expands. Curly
    single quotes also close a PowerShell string, so they are doubled too."""
    s = str(value)
    for q in ("'", "\u2018", "\u2019", "\u201a", "\u201b"):
        s = s.replace(q, q + q)
    return "'" + s + "'"


def main():
    if "--scout-due" in sys.argv:
        print("due" if scout_due() else "")
        return 0
    n = load()
    if "--json" in sys.argv:
        print(json.dumps(n, indent=2))
        return 0
    # The shells pass this straight to `claude --model`, which wants Fable by
    # its full name — the short alias comes back 404.
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import usage
    n = dict(n, model=usage.cli_model(n["model"]))
    # Both shells eval these lines, so every value is quoted as a literal:
    # a config value like $(...) must arrive as text, never run.
    if "--powershell" in sys.argv:
        print(f'$NightEnabled = {_ps(1 if n["enabled"] else 0)}')
        print(f'$NightJobs = {_ps(" ".join(n["jobs"]))}')
        print(f'$NightModel = {_ps(n["model"])}')
        print(f'$NightBattery = {_ps(1 if n["on_battery"] is True else 0)}')
        print(f'$NightBatteryMin = {_ps(battery_min(n))}')
        print(f'$NightAt = {_ps(n["at"])}')
        return 0
    q = shlex.quote
    print(f'NIGHT_ENABLED={q(str(1 if n["enabled"] else 0))}')
    print(f'NIGHT_JOBS={q(" ".join(n["jobs"]))}')
    print(f'NIGHT_MODEL={q(n["model"])}')
    print(f'NIGHT_BATTERY={q(str(1 if n["on_battery"] is True else 0))}')
    print(f'NIGHT_BATTERY_MIN={q(str(battery_min(n)))}')
    print(f'NIGHT_AT={q(n["at"])}')
    return 0


if __name__ == "__main__":
    sys.exit(main())

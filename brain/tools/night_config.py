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
      "on_battery": false        laptops: skip unless plugged in
    }
"""

import json
import os
import sys

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
        if ov in ("haiku", "sonnet", "opus"):
            night["model"] = ov
        else:
            careful = cfg.get("ai") in ("low", "careful", "pro")
            night["model"] = "haiku" if careful else "sonnet"
    return night


def main():
    n = load()
    if "--json" in sys.argv:
        print(json.dumps(n, indent=2))
        return 0
    if "--powershell" in sys.argv:
        print(f'$NightEnabled = "{1 if n["enabled"] else 0}"')
        print(f'$NightJobs = "{" ".join(n["jobs"])}"')
        print(f'$NightModel = "{n["model"]}"')
        print(f'$NightBattery = "{1 if n["on_battery"] else 0}"')
        print(f'$NightAt = "{n["at"]}"')
        return 0
    print(f'NIGHT_ENABLED={1 if n["enabled"] else 0}')
    print(f'NIGHT_JOBS="{" ".join(n["jobs"])}"')
    print(f'NIGHT_MODEL="{n["model"]}"')
    print(f'NIGHT_BATTERY={1 if n["on_battery"] else 0}')
    print(f'NIGHT_AT="{n["at"]}"')
    return 0


if __name__ == "__main__":
    sys.exit(main())

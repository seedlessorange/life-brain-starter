#!/usr/bin/env python3
"""Commands she keeps starting by hand, and whether one has earned a schedule.

    python3 brain/tools/promote.py          # plain lines, for /wrap
    python3 brain/tools/promote.py --json

The rule, adopted 28 Sep from the "agentic OS" video (repeat tasks become
skills, reliable skills become automations): a command she has started by
hand at least five times in the last 30 days, whose last five runs all
finished cleanly, is proposed for a schedule. Proposed, never scheduled:
/wrap turns each proposal into one question in questions.md, and only her
answer moves anything. A command she has said no to stays in config
`promote.declined` and is never raised again.

What counts, read by command name and time only, never content:
- the usage ledger (brain/.usage.jsonl): kind "run" is a page button she
  pressed; kind "morning" / "night" is the schedule itself;
- Claude Code's own session logs for this folder, for commands she typed
  into an interactive session. Headless runs are already in the ledger.

Where a proposal can land today: the night shift (config night.jobs, which
allows queue, wrap, sync, brief, discover and scout) and the morning job
(only /today). A habit at a daytime hour with no slot to go to says so
plainly rather than pretending a slot exists.
"""
import glob
import json
import os
import re
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
BRAIN = os.path.dirname(HERE)
ROOT = os.path.dirname(BRAIN)
LEDGER = os.path.join(BRAIN, ".usage.jsonl")
DAYS = 30
TIMES = 5
NIGHT_OK = {"queue", "wrap", "sync", "brief", "discover", "scout"}
# Conversations and one-off tools: started by hand because they need her.
MANUAL = {"write", "journal", "dump", "teach", "critic", "consult", "analyst",
          "finish", "onboard", "import-history", "checkin", "transcribe",
          "usageaudit", "usage-audit", "audit"}
DAYNAMES = ["Mondays", "Tuesdays", "Wednesdays", "Thursdays", "Fridays",
            "Saturdays", "Sundays"]


def _config():
    try:
        with open(os.path.join(BRAIN, "config.json"), encoding="utf-8") as f:
            return json.load(f) or {}
    except Exception:
        return {}


def _commands():
    """The brain's own commands, by name: only these can be scheduled."""
    names = {os.path.splitext(os.path.basename(p))[0]
             for p in glob.glob(os.path.join(ROOT, ".claude", "commands", "*.md"))}
    return names | NIGHT_OK | {"today"}


def _local(ts):
    """ISO time from either source to a naive local datetime."""
    try:
        d = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except ValueError:
        return None
    if d.tzinfo is not None:
        d = d.astimezone().replace(tzinfo=None)
    return d


def by_hand(now=None):
    """{command: [(when, ok)]} started by hand in the window."""
    now = now or datetime.now()
    since = now - timedelta(days=DAYS)
    known = _commands()
    out = {}
    try:
        with open(LEDGER, encoding="utf-8") as f:
            for line in f:
                try:
                    r = json.loads(line)
                except ValueError:
                    continue
                if r.get("kind") != "run":
                    continue
                job = str(r.get("label") or "").strip().lstrip("/")
                if job not in known:
                    continue
                d = _local(r.get("at"))
                if d and d >= since:
                    out.setdefault(job, []).append((d, r.get("ok") is not False))
    except OSError:
        pass
    # Commands she typed herself, in an interactive session.
    logs = os.path.expanduser("~/.claude/projects/"
                              + re.sub(r"[^A-Za-z0-9]", "-", ROOT))
    for path in glob.glob(os.path.join(logs, "*.jsonl")):
        try:
            if datetime.fromtimestamp(os.path.getmtime(path)) < since:
                continue
            with open(path, encoding="utf-8", errors="replace") as f:
                for line in f:
                    if "<command-name>/" not in line or '"entrypoint"' not in line:
                        continue
                    try:
                        j = json.loads(line)
                    except ValueError:
                        continue
                    if j.get("entrypoint") in (None, "sdk-cli", "sdk-py", "sdk-ts"):
                        continue          # headless: the ledger has it
                    m = re.search(r"<command-name>/([a-z-]+)</command-name>",
                                  json.dumps(j.get("message") or {}))
                    d = _local(j.get("timestamp"))
                    if m and m.group(1) in known and d and d >= since:
                        out.setdefault(m.group(1), []).append((d, True))
        except OSError:
            continue
    for v in out.values():
        v.sort()
    return out


def scheduled(cfg):
    """{command: 'when'} for what already runs by itself."""
    out = {}
    night = cfg.get("night") or {}
    if night.get("enabled"):
        for j in night.get("jobs") or []:
            out[j] = "nightly at " + (night.get("at") or "01:00")
    feats = cfg.get("ai_features") or {}
    if feats.get("morning", cfg.get("ai") == "full"):
        out["today"] = "every morning at 07:00"
    return out


def _habit(times):
    """(text, hour or None) describing when she tends to start it."""
    hours = Counter(t.hour for t, _ in times)
    best, share = None, 0.0
    for h in range(24):
        c = hours[h] + hours[(h + 1) % 24]
        if c / len(times) > share:
            best, share = h, c / len(times)
    days = Counter(t.weekday() for t, _ in times)
    wd, wn = days.most_common(1)[0]
    bits = []
    if share >= .6:
        bits.append(f"mostly between {best:02d}:00 and {(best + 2) % 24:02d}:00")
    else:
        best = None
        bits.append("at no steady hour")
    if wn / len(times) >= .6 and len(times) >= TIMES:
        bits.append("on " + DAYNAMES[wd])
    return " ".join(bits), best


def considered(now=None):
    """One line per command started by hand, for the record in /wrap."""
    cfg = _config()
    sched = scheduled(cfg)
    lines = []
    for job, times in sorted(by_hand(now).items(), key=lambda kv: -len(kv[1])):
        habit, _h = _habit(times) if len(times) >= 2 else ("", None)
        note = (f"already {sched[job]}" if job in sched else
                "kept manual on purpose" if job in MANUAL else
                f"fewer than {TIMES} times" if len(times) < TIMES else "a candidate")
        lines.append(f"/{job}: {len(times)} by hand ({note}{'; ' + habit if habit else ''})")
    return lines


def proposals(now=None):
    cfg = _config()
    declined = set((cfg.get("promote") or {}).get("declined") or [])
    sched = scheduled(cfg)
    out = []
    for job, times in sorted(by_hand(now).items(), key=lambda kv: -len(kv[1])):
        if job in MANUAL or job in declined or len(times) < TIMES:
            continue
        last = times[-TIMES:]
        if not all(ok for _, ok in last):
            continue                      # not reliable yet: five clean runs first
        habit, hour = _habit(times)
        n = len(times)
        if job in sched:
            if hour is not None and not (hour >= 22 or hour < 6):
                out.append({
                    "job": job, "count": n, "habit": habit, "kind": "second-slot",
                    "text": (f"/{job} already runs {sched[job]}, and you still started "
                             f"it by hand {n} times in {DAYS} days, {habit}. A daytime "
                             f"run at {hour:02d}:30 would need a slot the brain does not "
                             "have yet: build one?")})
            continue
        if job in NIGHT_OK:
            out.append({
                "job": job, "count": n, "habit": habit, "kind": "night",
                "text": (f"You started /{job} by hand {n} times in {DAYS} days, "
                         f"{habit}, and the last {TIMES} runs all finished cleanly. "
                         "Add it to the night shift (01:00)?")})
        else:
            out.append({
                "job": job, "count": n, "habit": habit, "kind": "no-slot",
                "text": (f"You started /{job} by hand {n} times in {DAYS} days, "
                         f"{habit}. Nothing can run it on a schedule yet: worth "
                         "building a slot for it?")})
    return out


if __name__ == "__main__":
    ps = proposals()
    if "--json" in sys.argv:
        print(json.dumps(ps, indent=2))
    elif not ps:
        seen = considered()
        print("Nothing to promote." + (" Looked at: " + "; ".join(seen) + "." if seen
                                       else " No command was started by hand this month."))
    else:
        for p in ps:
            print("- " + p["text"])

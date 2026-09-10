#!/usr/bin/env python3
"""The plan's track record, mined from git.

Every morning /today overwrites brain/today.md, and every version is in git —
so the history of that one file is a complete record of what was planned vs
what got ticked. This script digs it out and prints a short digest /today
reads before sizing the day: completion by task size, by weekday, planned
load vs capacity, and the tasks that keep carrying without getting done.

Two completion facts, kept separate on purpose:
- same-day ticks (did the plan's own boxes get ticked), and
- eventual outcomes per distinct task, where a tick in workstreams.md or
  next.md's Done trail also counts — finishing through a different door
  is still finishing.

Usage: python3 brain/tools/calibrate.py [--days 60]   (--days = most recent
N plans to read). Prints plain text, a dozen lines. No files written.
"""

import json
import re
import subprocess
import sys
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

EST_RE = re.compile(r"~(?:(\d+)h(\d+)?m?|(\d+)m)\b")
BOX_RE = re.compile(r"^\s*- \[( |x|X)\]\s*(.*)$")
DATE_RE = re.compile(r"^updated:\s*(\d{4}-\d{2}-\d{2})")
MARKER_RE = re.compile(r"\((?:carrying|dropped)\s+\d{4}-\d{2}-\d{2}\)")
SUFFIX_RE = re.compile(r"\((?:due|by|waiting until)[^)]*\)")


def git(*args):
    return subprocess.run(
        ["git", "-C", str(ROOT)] + list(args),
        capture_output=True, text=True, check=False,
    ).stdout


def est_minutes(text):
    m = EST_RE.search(text)
    if not m:
        return None
    if m.group(3):
        return int(m.group(3))
    return int(m.group(1)) * 60 + int(m.group(2) or 0)


def normalize(text):
    """A task's identity across days and files: text minus estimate,
    markers, urgency and date suffixes."""
    t = EST_RE.sub("", text)
    t = MARKER_RE.sub("", t)
    t = SUFFIX_RE.sub("", t)
    t = t.replace("(urgent)", "")
    return " ".join(t.lower().split())


def parse_plan(content):
    """One version of today.md -> (plan_date, [task dicts])."""
    plan_date, section, tasks = None, None, []
    for line in content.splitlines():
        if plan_date is None:
            m = DATE_RE.match(line)
            if m:
                plan_date = m.group(1)
        if line.startswith("## "):
            h = line[3:].lower()
            section = ("three" if h.startswith("do these")
                       else "chases" if h.startswith("two-minute")
                       else None)
            continue
        if section is None:
            continue
        m = BOX_RE.match(line)
        if m:
            tasks.append({
                "section": section,
                "ticked": m.group(1) in "xX",
                "dropped": "(dropped" in m.group(2),
                "minutes": est_minutes(m.group(2)),
                "key": normalize(m.group(2)),
            })
    return plan_date, tasks


def collect(max_days):
    """Newest git version per plan date = that day's final tick state."""
    shas = git("log", "--format=%H", "--", "brain/today.md").split()
    plans = {}
    for sha in shas:
        content = git("show", f"{sha}:brain/today.md")
        d, tasks = parse_plan(content)
        if d and d not in plans and tasks:
            plans[d] = tasks
        if len(plans) >= max_days:
            break
    today = date.today().isoformat()
    return {d: t for d, t in plans.items() if d < today}


def done_elsewhere():
    """Keys of tasks ticked in workstreams.md or listed in next.md's Done
    trail — completions that never came back to tick the plan."""
    keys = set()
    for name in ("workstreams.md", "next.md"):
        try:
            content = (ROOT / "brain" / name).read_text()
        except OSError:
            continue
        in_done = name != "next.md"
        for line in content.splitlines():
            if name == "next.md":
                if line.startswith("## "):
                    in_done = line[3:].strip().lower() == "done"
                if in_done and line.startswith("- "):
                    keys.add(normalize(re.sub(r"^- (\[.\] )?", "", line)))
                continue
            m = BOX_RE.match(line)
            if m and m.group(1) in "xX":
                keys.add(normalize(m.group(2)))
    keys.discard("")
    return keys


def pct(done, total):
    return f"{round(100 * done / total)}%" if total else "–"


def bucket(minutes):
    if minutes is None:
        return "unsized"
    if minutes <= 20:
        return "<=20m"
    if minutes <= 60:
        return "21-60m"
    return ">1h"


def main():
    max_days = 60
    if "--days" in sys.argv:
        max_days = int(sys.argv[sys.argv.index("--days") + 1])

    plans = collect(max_days)
    if not plans:
        print("CALIBRATION: no plan history in git yet.")
        return

    dates = sorted(plans)
    span = (datetime.strptime(dates[-1], "%Y-%m-%d")
            - datetime.strptime(dates[0], "%Y-%m-%d")).days
    lines = [f"CALIBRATION — {len(dates)} past plans, {dates[0]} to {dates[-1]}"]
    if len(dates) < 7:
        lines.append("(thin history — treat everything below as a hint, not a law)")

    # Eventual outcome per distinct "three" task.
    elsewhere = done_elsewhere()
    uniq = {}  # key -> {"appearances", "ticked", "dropped"} in date order
    for d in dates:
        for t in plans[d]:
            if t["section"] != "three" or not t["key"]:
                continue
            u = uniq.setdefault(t["key"], {"n": 0, "ticked": False, "dropped": False})
            u["n"] += 1
            u["ticked"] = u["ticked"] or t["ticked"]
            u["dropped"] = t["dropped"] and not t["ticked"]  # final state wins
    done_keys = {k for k, u in uniq.items() if u["ticked"] or k in elsewhere}
    dropped_keys = {k for k, u in uniq.items()
                    if u["dropped"] and k not in done_keys}
    open_keys = set(uniq) - done_keys - dropped_keys
    via_elsewhere = sum(1 for k in done_keys if not uniq[k]["ticked"])
    lines.append(
        f"Distinct tasks planned: {len(uniq)} — {len(done_keys)} done in the end"
        + (f" ({via_elsewhere} finished outside the plan's own tickbox)" if via_elsewhere else "")
        + f", {len(dropped_keys)} dropped on purpose, {len(open_keys)} with no trace of completion.")

    three = [t for ts in plans.values() for t in ts if t["section"] == "three" and not t["dropped"]]
    chases = [t for ts in plans.values() for t in ts if t["section"] == "chases" and not t["dropped"]]
    lines.append(f"Same-day ticks: the three {pct(sum(t['ticked'] for t in three), len(three))} "
                 f"of {len(three)}, chases {pct(sum(t['ticked'] for t in chases), len(chases))} "
                 f"of {len(chases)}. A gap between this and the line above means work "
                 f"finishes but the plan's boxes don't hear about it.")

    by_size = defaultdict(lambda: [0, 0])
    for t in three:
        done = t["ticked"] or t["key"] in elsewhere
        b = bucket(t["minutes"])
        by_size[b][1] += 1
        by_size[b][0] += done
    order = ["<=20m", "21-60m", ">1h", "unsized"]
    parts = [f"{b} {pct(*by_size[b])} (n={by_size[b][1]})"
             for b in order if by_size[b][1]]
    lines.append("Done by size: " + ", ".join(parts))

    # Weekdays are noise until a few weeks exist.
    if span >= 21:
        by_wd = defaultdict(lambda: [0, 0])
        for d, ts in plans.items():
            wd = datetime.strptime(d, "%Y-%m-%d").strftime("%a")
            for t in ts:
                if t["section"] == "three" and not t["dropped"]:
                    by_wd[wd][1] += 1
                    by_wd[wd][0] += (t["ticked"] or t["key"] in elsewhere)
        rated = {w: v[0] / v[1] for w, v in by_wd.items() if v[1] >= 6}
        if len(rated) >= 2:
            best = max(rated, key=rated.get)
            worst = min(rated, key=rated.get)
            if best != worst:
                lines.append(f"By weekday: best {best} ({pct(*by_wd[best])}), "
                             f"worst {worst} ({pct(*by_wd[worst])}).")

    cap = None
    try:
        cfg = json.loads((ROOT / "brain" / "config.json").read_text())
        cap = cfg.get("capacity", {}).get("daily_minutes")
    except Exception:
        pass
    sized_days = [sum(t["minutes"] for t in ts if t["minutes"] and not t["dropped"])
                  for ts in plans.values()]
    sized_days = [s for s in sized_days if s]
    if sized_days and cap:
        avg = round(sum(sized_days) / len(sized_days))
        lines.append(f"Planned load: avg {avg}m/day against a {cap}m capacity"
                     + (" — the plans themselves are oversized." if avg > cap else "."))

    chronic = sorted(
        ((k, uniq[k]["n"]) for k in open_keys if uniq[k]["n"] >= 3),
        key=lambda kv: -kv[1])
    for k, n in chronic[:3]:
        lines.append(f"Chronic carry: \"{k[:70]}\" planned {n} days, no trace of completion.")

    print("\n".join(lines))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Find the project folders you have actually been working in.

    python3 brain/tools/discover.py            # what is live, and what the brain already knows
    python3 brain/tools/discover.py --months 6 # look further back

Walks your home folder for real project directories (a git repo, or a
recognisable project marker), works out when each was last genuinely touched,
and prints them ranked by recency — marking which ones the brain already
follows and which it does not.

Reads only. It never edits config.json; `/discover` in Claude Code does that,
after showing you the list. The point is that a folder you have not opened in
four months is a decision waiting to be made, not a folder to sync silently.
"""

import argparse
import json
import os
import subprocess
import sys
from datetime import date, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
BRAIN = os.path.dirname(HERE)
ROOT = os.path.dirname(BRAIN)
HOME = os.path.expanduser("~")

MARKERS = ("package.json", "pyproject.toml", "Cargo.toml", "go.mod", "build.gradle",
           "build.gradle.kts", "requirements.txt", "Gemfile", "composer.json",
           "CLAUDE.md", "TODO.md", "TODOS.md")

# Folders that are never a project of hers, however recently they changed.
SKIP = {"Library", "Applications", "Movies", "Music", "Pictures", "Public",
        "Downloads", "Desktop", "node_modules", "miniconda3", "OrbStack",
        "go", "Parallels", "Creative Cloud Files", ".Trash"}
SKIP_INNER = {".git", "node_modules", ".venv", "venv", "__pycache__", "build",
              "dist", ".next", "target", ".gradle", "Pods", ".idea", "vendor"}


def is_project(path):
    if os.path.isdir(os.path.join(path, ".git")):
        return True
    return any(os.path.exists(os.path.join(path, m)) for m in MARKERS)


def last_commit(path):
    try:
        r = subprocess.run(["git", "-C", path, "log", "-1", "--format=%cI"],
                           capture_output=True, text=True, timeout=8)
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.strip()[:10]
    except Exception:
        pass
    return None


def newest_file(path, depth=2):
    """Most recent edit, ignoring build output — which changes without anyone
    doing any work and would make a dead project look alive."""
    newest, base = 0.0, path.rstrip(os.sep).count(os.sep)
    for root, dirs, files in os.walk(path):
        dirs[:] = [d for d in dirs if d not in SKIP_INNER and not d.startswith(".")]
        if root.count(os.sep) - base >= depth:
            dirs[:] = []
        for fn in files:
            if fn.startswith("."):
                continue
            try:
                newest = max(newest, os.path.getmtime(os.path.join(root, fn)))
            except OSError:
                pass
    return newest or None


def tracked_paths():
    """What the brain already follows, as absolute paths."""
    try:
        with open(os.path.join(BRAIN, "config.json"), encoding="utf-8") as f:
            cfg = json.load(f)
    except Exception:
        return set()
    out = set()
    for s in cfg.get("sources", []):
        p = s.get("path", "")
        if p:
            out.add(os.path.realpath(os.path.expanduser(p)))
    return out


def scan(months):
    today = date.today()
    known = tracked_paths()
    found = []
    for entry in sorted(os.listdir(HOME)):
        if entry in SKIP or entry.startswith("."):
            continue
        path = os.path.join(HOME, entry)
        # The brain itself is not one of her projects.
        if not os.path.isdir(path) or os.path.realpath(path) == os.path.realpath(ROOT):
            continue
        if not is_project(path):
            continue
        commit = last_commit(path)
        mt = newest_file(path)
        mtime = datetime.fromtimestamp(mt).date().isoformat() if mt else None
        # The later of the two: a repo can have old commits and fresh edits.
        best = max([d for d in (commit, mtime) if d], default=None)
        days = (today - date.fromisoformat(best)).days if best else None
        found.append({
            "name": entry, "path": path, "days": days, "last": best,
            "commit": commit, "mtime": mtime,
            "tracked": os.path.realpath(path) in known,
            "git": os.path.isdir(os.path.join(path, ".git")),
        })
    found.sort(key=lambda f: (f["days"] is None, f["days"]))
    cutoff = months * 30
    return found, cutoff


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--months", type=int, default=4,
                    help="how far back still counts as active (default 4)")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    found, cutoff = scan(args.months)
    if args.json:
        print(json.dumps(found, indent=2))
        return

    live = [f for f in found if f["days"] is not None and f["days"] <= cutoff]
    cold = [f for f in found if f not in live]

    def row(f):
        age = "unknown" if f["days"] is None else (
            "today" if f["days"] == 0 else f"{f['days']}d ago")
        mark = "tracked" if f["tracked"] else "NOT TRACKED"
        return f"  {f['name']:<34} {age:>10}   {mark}"

    print(f"\nActive in the last {args.months} months ({len(live)}):")
    for f in live:
        print(row(f))
    if cold:
        print(f"\nQuiet for longer ({len(cold)}):")
        for f in cold:
            print(row(f))

    missing = [f for f in live if not f["tracked"]]
    if missing:
        print(f"\n{len(missing)} active project(s) the brain does not follow:")
        for f in missing:
            print(f'    {{"name": "{f["name"]}", "path": "~/{os.path.relpath(f["path"], HOME)}"}},')
    else:
        print("\nEverything active is already tracked.")

    stale = [f for f in found if f["tracked"] and f not in live]
    if stale:
        print(f"\nTracked but quiet — worth parking or dropping: "
              + ", ".join(f["name"] for f in stale))


if __name__ == "__main__":
    main()

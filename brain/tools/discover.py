#!/usr/bin/env python3
"""Find the project folders you have actually been working in.

    python3 brain/tools/discover.py            # what is live, and what the brain already knows
    python3 brain/tools/discover.py --months 6 # look further back

Walks your home folder for real project directories (a git repo, or a
recognisable project marker), works out when each was last genuinely touched,
and prints them ranked by recency — marking which ones the brain already
follows and which it does not.

Reads only. It never edits config.json; `/discover` in Claude Code does that,
after showing you the list, and so do the Follow and Not a project buttons
that `proposals()` puts in For you for anything active this fortnight. The point is that a folder you have not opened in
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


# ── adding a folder by hand (9 Oct, her ask: paste names, or let it look) ──
# The scan above finds code projects one level under home and skips the
# Desktop, so a folder of documents there (a renovation, a class) never
# turns up. These let her name the folder instead, by path or by name.

# Never followed, whatever she types: the Mac's own folders and anywhere
# credentials live. Checked on the resolved path.
NEVER_TOP = {"Library", "Applications", ".Trash", ".ssh", ".aws", ".gnupg",
             ".config", ".claude", "AppData"}   # AppData: Windows' own


def check_folder(path):
    """(real path, "") when this folder may be followed, else ("", why)."""
    p = os.path.realpath(os.path.expanduser((path or "").strip()))
    home = os.path.realpath(HOME)
    if not os.path.isdir(p):
        return "", "no folder there"
    if p == home or not p.startswith(home + os.sep):
        return "", "only folders inside your home folder"
    top = p[len(home) + 1:].split(os.sep, 1)[0]
    if top in NEVER_TOP or top.startswith("."):
        return "", "that is one of the Mac's own folders"
    root = os.path.realpath(ROOT)
    if p == root or p.startswith(root + os.sep):
        return "", "that is the brain itself"
    return p, ""


def _tilde(p):
    home = os.path.realpath(HOME)
    return "~" + p[len(home):] if p.startswith(home + os.sep) else p


def folder_info(path, known=None):
    known = tracked_paths() if known is None else known
    commit, mt = last_commit(path), newest_file(path)
    mtime = datetime.fromtimestamp(mt).date().isoformat() if mt else None
    best = max([d for d in (commit, mtime) if d], default=None)
    real = os.path.realpath(path)
    return {"name": os.path.basename(path), "path": _tilde(path),
            "days": (date.today() - date.fromisoformat(best)).days if best else None,
            "tracked": real in known,
            # Inside a folder already followed: following it again would
            # list the same tasks twice.
            "inside": next((_tilde(k) for k in known
                            if real.startswith(k + os.sep)), ""),
            "project": is_project(path)}


def find_folders(text, depth=4, limit=6, budget=40000):
    """Each pasted line as [{query, matches, error}]. A path is checked as
    given; a bare name is looked for under home, exact names first, then
    names that contain it. Reads only, and only folder names."""
    known = tracked_paths()
    lines = [ln.strip().strip('"\'').rstrip("/") for ln in (text or "").splitlines()]
    lines = [ln for ln in lines if ln][:20]
    out = []
    names = [ln for ln in lines if not ln.startswith(("~", "/"))]
    hits = {n.casefold(): ([], []) for n in names}
    if names:
        home, seen = os.path.realpath(HOME), 0
        base = home.count(os.sep)
        for root, dirs, _files in os.walk(home):
            dirs[:] = sorted(d for d in dirs if not d.startswith(".")
                             and d not in SKIP_INNER
                             and not (root == home and d in NEVER_TOP | {"Library"}))
            if root.count(os.sep) - base >= depth:
                dirs[:] = []
            for d in dirs:
                seen += 1
                low = d.casefold()
                for q, (exact, part) in hits.items():
                    if low == q:
                        exact.append(os.path.join(root, d))
                    elif q in low and len(part) < limit:
                        part.append(os.path.join(root, d))
            if seen > budget:
                break
    for ln in lines:
        if ln.startswith(("~", "/")):
            p, why = check_folder(ln)
            out.append({"query": ln, "matches": [folder_info(p, known)] if p else [],
                        "error": why})
            continue
        exact, part = hits[ln.casefold()]
        ok = []
        for c in (exact or part):
            p, _why = check_folder(c)
            if p and p not in [m["_real"] for m in ok]:
                ok.append(dict(folder_info(p, known), _real=p))
        for m in ok:
            m.pop("_real", None)
        out.append({"query": ln, "matches": ok[:limit],
                    "error": "" if ok else "no folder with that name"})
    return out


def source_for(path, name=""):
    """The config.json `sources` entry for a folder she chose to follow."""
    p, why = check_folder(path)
    if not p:
        raise ValueError(why)
    src = {"name": (name or "").strip()[:60] or os.path.basename(p),
           "path": _tilde(p)}
    if os.path.isfile(os.path.join(p, "brain", "handoff.md")):
        src["files"] = ["brain/handoff.md"]
    return src


def active_untracked(cfg=None, months=4):
    """The scan's active projects the brain does not follow and she has not
    turned down: what "Look for them" lists."""
    if cfg is None:
        try:
            with open(os.path.join(BRAIN, "config.json"), encoding="utf-8") as f:
                cfg = json.load(f)
        except Exception:
            cfg = {}
    no = set((cfg.get("discover") or {}).get("ignored") or [])
    found, cutoff = scan(months)
    return [dict(f, path=_tilde(f["path"])) for f in found
            if not f["tracked"] and f["days"] is not None and f["days"] <= cutoff
            and f["name"] not in no]


def proposals(cfg=None, days=14):
    """New projects worth a line in For you: worked in within `days`, not
    followed, not one she already said no to. Two weeks, not the scan's four
    months: a folder she is in this fortnight is a question worth asking her,
    and anything older is what `/discover` is for. Still reads only — the
    page's Follow and Not a project buttons are what write config.json."""
    if cfg is None:
        try:
            with open(os.path.join(BRAIN, "config.json"), encoding="utf-8") as f:
                cfg = json.load(f)
        except Exception:
            cfg = {}
    no = set((cfg.get("discover") or {}).get("ignored") or [])
    out = []
    for f in scan(1)[0]:
        if f["tracked"] or f["days"] is None or f["days"] > days:
            continue
        if f["name"] in no:
            continue
        f["handoff"] = os.path.isfile(os.path.join(f["path"], "brain", "handoff.md"))
        f["handoff_tool"] = os.path.isfile(
            os.path.join(f["path"], "brain", "tools", "handoff.py"))
        out.append(f)
    return out


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

#!/usr/bin/env python3
"""Update a brain's code from a newer share package, keeping every data file.

    # from inside your brain, pointing at the new zip (or unzipped folder):
    python3 brain/tools/update.py ~/Downloads/life-brain-2026-08-19.zip
    python3 brain/tools/update.py ~/Downloads/life-brain-2026-08-19.zip --yes

    # or from inside the NEW unzipped package, pointing at your brain
    # (this is the route when your current version predates this script):
    python3 brain/tools/update.py --into ~/Documents/life-brain --yes

Code and data live in the same folder but are different things. This
replaces CODE — the tools, the commands, the pages, the launchers, the
reference docs — and never touches DATA: your workstreams, people, habits,
config values, queue, rooms, daily digests, drafts, files, transcripts, or
your git history. New config settings the update introduces are added with
their defaults; every value you already have keeps yours.

Safety, in order: without --yes it only prints what would change; your git
gets a snapshot commit before anything moves (when git is available); and
every file it replaces is copied first to brain/archive/update-<stamp>/,
so even without git nothing is ever lost.

After it runs, restart the brain (close the black window, double-click the
launcher again) so the server picks up its own new code.
"""

import argparse
import filecmp
import json
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from datetime import datetime

# What is DATA (kept, always). Everything else in the package is code and
# gets copied over. Paths are package-relative, / separated.
DATA_FILES = {
    "brain/workstreams.md", "brain/people.md", "brain/habits.md",
    "brain/goals.md", "brain/inbox.md", "brain/next.md", "brain/waiting.md",
    "brain/questions.md", "brain/decisions.md", "brain/today.md",
    "brain/about-me.md", "brain/writing-rules.md", "brain/interests.md",
    "brain/routine.md", "brain/synced.md", "brain/config.json",
    "brain/people-ignored.json", "brain/sessions.json", "brain/season.md",
    "brain/countdowns.md", "brain/week-plan.md", "brain/journal-trace.md",
    "brain/reference/history.md",
}
DATA_DIRS = ("brain/queue/", "brain/rooms/", "brain/daily/", "brain/drafts/",
             "brain/files/", "brain/transcripts/", "brain/sessions/",
             "brain/archive/", "brain/avatars/", "brain/journal/",
             "brain/finance/")
SKIP = {".share-package"}          # package bookkeeping, not code or data


def is_data(rel):
    rel = rel.replace(os.sep, "/")
    if rel in DATA_FILES or rel in SKIP:
        return True
    if rel.startswith(".git/") or "/.git/" in rel or rel == ".git":
        return True
    if os.path.basename(rel).startswith(".") and rel.startswith("brain/") \
            and "/" not in rel[len("brain/"):]:
        return True                # brain/.tokens, caches, logs — theirs
    return any(rel.startswith(d) for d in DATA_DIRS)


def looks_like_brain(path):
    return (os.path.isdir(os.path.join(path, "brain", "tools"))
            and os.path.exists(os.path.join(path, "brain", "config.json")))


def package_root(path):
    """The folder inside `path` that holds the package (zips wrap one dir)."""
    if looks_like_brain(path):
        return path
    kids = [os.path.join(path, k) for k in os.listdir(path)
            if not k.startswith("__MACOSX")]
    dirs = [k for k in kids if os.path.isdir(k)]
    if len(dirs) == 1 and looks_like_brain(dirs[0]):
        return dirs[0]
    return None


def code_files(src):
    """Package-relative paths of every CODE file in the source package."""
    out = []
    for dirpath, dirnames, filenames in os.walk(src):
        dirnames[:] = [d for d in dirnames
                       if d not in ("__pycache__", ".git")]
        for fn in filenames:
            rel = os.path.relpath(os.path.join(dirpath, fn), src)
            rel = rel.replace(os.sep, "/")
            if fn.endswith(".pyc") or is_data(rel):
                continue
            out.append(rel)
    return sorted(out)


def merge_config(target, src):
    """New settings arrive with their defaults; existing values are never
    changed. Returns the list of added key paths."""
    tpath = os.path.join(target, "brain", "config.json")
    spath = os.path.join(src, "brain", "config.json")
    try:
        with open(tpath, encoding="utf-8") as f:
            mine = json.load(f)
        with open(spath, encoding="utf-8") as f:
            new = json.load(f)
    except Exception as exc:
        return [f"(config merge skipped: {exc})"]
    added = []

    def walk(mine_d, new_d, prefix):
        for k, v in new_d.items():
            if k not in mine_d:
                mine_d[k] = v
                added.append(prefix + k)
            elif isinstance(v, dict) and isinstance(mine_d[k], dict):
                walk(mine_d[k], v, prefix + k + ".")

    walk(mine, new, "")
    if added:
        tmp = tpath + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(mine, f, indent=2, ensure_ascii=False)
            f.write("\n")
        os.replace(tmp, tpath)
    return added


def snapshot(target, msg):
    try:
        subprocess.run(["git", "-C", target, "add", "-A"],
                       capture_output=True, timeout=30)
        subprocess.run(["git", "-C", target, "commit", "-m", msg],
                       capture_output=True, timeout=30)
        return True
    except Exception:
        return False


def main():
    ap = argparse.ArgumentParser(
        description="Update a brain's code from a newer share package; "
                    "every data file stays untouched.")
    ap.add_argument("source", nargs="?",
                    help="the new package: a .zip or an unzipped folder "
                         "(omit when running from inside the new package)")
    ap.add_argument("--into", metavar="BRAIN",
                    help="the brain to update (default: the one this "
                         "script runs inside)")
    ap.add_argument("--yes", action="store_true",
                    help="apply the update (otherwise: preview only)")
    args = ap.parse_args()

    here_brain = os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))))
    target = os.path.realpath(os.path.expanduser(args.into or here_brain))
    if not looks_like_brain(target):
        sys.exit(f"{target} doesn't look like a brain "
                 "(no brain/tools or brain/config.json)")

    tmpdir = None
    if args.source:
        srcpath = os.path.realpath(os.path.expanduser(args.source))
        if srcpath.lower().endswith(".zip"):
            tmpdir = tempfile.mkdtemp(prefix="brain-update-")
            with zipfile.ZipFile(srcpath) as z:
                z.extractall(tmpdir)
            src = package_root(tmpdir)
        else:
            src = package_root(srcpath)
    else:
        src = here_brain if here_brain != target else None
    if not src or not looks_like_brain(src):
        sys.exit("Couldn't find the new package. Point at the zip or the "
                 "unzipped life-brain folder.")
    if os.path.realpath(src) == target:
        sys.exit("Source and target are the same folder — run this from the "
                 "NEW package with --into, or pass the new zip as the source.")

    files = code_files(src)
    changed, new = [], []
    for rel in files:
        dst = os.path.join(target, rel.replace("/", os.sep))
        s = os.path.join(src, rel.replace("/", os.sep))
        if not os.path.exists(dst):
            new.append(rel)
        elif not filecmp.cmp(s, dst, shallow=False):
            changed.append(rel)

    print(f"Updating {target}")
    print(f"  {len(changed)} code file(s) change, {len(new)} arrive new, "
          f"{len(files) - len(changed) - len(new)} identical.")
    print("  Your data — workstreams, people, config values, queue, "
          "transcripts, history — is not touched.")
    for rel in (changed + new)[:25]:
        print(f"    {'update' if rel in changed else 'new   '}  {rel}")
    if len(changed) + len(new) > 25:
        print(f"    … and {len(changed) + len(new) - 25} more")
    if not args.yes:
        print("\nPreview only — re-run with --yes to apply.")
        if tmpdir:
            shutil.rmtree(tmpdir, ignore_errors=True)
        return
    if not changed and not new:
        print("Already up to date.")
        if tmpdir:
            shutil.rmtree(tmpdir, ignore_errors=True)
        return

    stamp = datetime.now().strftime("update-%Y%m%d-%H%M%S")
    if snapshot(target, f"before {stamp}"):
        print("  git snapshot taken — that is the full undo.")
    arch = os.path.join(target, "brain", "archive", stamp)
    for rel in changed:                       # belt and braces beyond git
        keep = os.path.join(arch, rel.replace("/", os.sep))
        os.makedirs(os.path.dirname(keep), exist_ok=True)
        shutil.copy2(os.path.join(target, rel.replace("/", os.sep)), keep)
    for rel in changed + new:
        s = os.path.join(src, rel.replace("/", os.sep))
        d = os.path.join(target, rel.replace("/", os.sep))
        os.makedirs(os.path.dirname(d), exist_ok=True)
        shutil.copy2(s, d)
    if changed:
        print(f"  the replaced versions are in brain/archive/{stamp}/")

    added = merge_config(target, src)
    if added:
        print("  new settings added with defaults (yours kept): "
              + ", ".join(added))

    print("  rebuilding the pages…")
    for job in ("build.py", "map.py", "rooms.py", "proto.py"):
        try:
            subprocess.run([sys.executable,
                            os.path.join(target, "brain", "tools", job)],
                           cwd=target, capture_output=True, timeout=120)
        except Exception:
            pass
    snapshot(target, f"after {stamp}: code updated, data untouched")
    if tmpdir:
        shutil.rmtree(tmpdir, ignore_errors=True)
    print("\nDone. Restart the brain (close the black window, double-click "
          "the launcher) so the server runs its new code.")


if __name__ == "__main__":
    main()

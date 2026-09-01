#!/usr/bin/env python3
"""Keep two machines' brains agreeing, through the git remote.

    python3 brain/tools/gitsync.py --pull    # take what the other machine pushed
    python3 brain/tools/gitsync.py --push    # hand ours back
    python3 brain/tools/gitsync.py --sync    # commit, pull, push — the full cycle

One implementation for every caller: morning.sh/.ps1 and night.sh/.ps1 pull
before their run (their existing push stays), and serve.py's auto-sync loop
runs the full cycle so page ticks and drafts reach the other machine within
twenty minutes instead of waiting for 7am.

The rules that make this safe to run unattended:

* Never fatal. No remote, no network, a hotel wifi that eats the connection —
  every failure prints one line and exits 0, because a sync problem must not
  stop a morning run or the server loop.
* Never lose work. Anything dirty is committed before the pull, and a rebase
  that hits a real conflict is aborted outright — this machine keeps exactly
  what it had, and the divergence waits for an attended session to resolve.
* Detached HEAD or mid-rebase state: do nothing at all.
"""

import os
import subprocess
import sys
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))


def _git(*args, timeout=120):
    return subprocess.run(["git", "-C", ROOT, *args],
                          capture_output=True, text=True, timeout=timeout)


def _has_remote():
    try:
        return _git("remote", "get-url", "origin", timeout=10).returncode == 0
    except Exception:
        return False


def _branch():
    """Current branch name, or '' when detached / mid-rebase — the states
    where an automatic pull could only make things worse."""
    try:
        r = _git("rev-parse", "--abbrev-ref", "HEAD", timeout=10)
        name = r.stdout.strip()
        if r.returncode != 0 or name == "HEAD":
            return ""
        if os.path.isdir(os.path.join(ROOT, ".git", "rebase-merge")) or \
           os.path.isdir(os.path.join(ROOT, ".git", "rebase-apply")):
            return ""
        return name
    except Exception:
        return ""


def _head():
    try:
        r = _git("rev-parse", "HEAD", timeout=10)
        return r.stdout.strip() if r.returncode == 0 else ""
    except Exception:
        return ""


def commit_if_dirty(message):
    try:
        r = _git("status", "--porcelain", timeout=30)
        if r.returncode != 0 or not r.stdout.strip():
            return False
        _git("add", "-A")
        return _git("commit", "-m", message).returncode == 0
    except Exception:
        return False


def pull():
    """git pull --rebase, defensively. Returns True when it brought new
    commits (the caller may want to rebuild the pages)."""
    if not _has_remote():
        return False
    branch = _branch()
    if not branch:
        print("gitsync: detached or mid-rebase, leaving git alone")
        return False
    commit_if_dirty(f"auto snapshot before pull {date.today().isoformat()}")
    before = _head()
    try:
        r = _git("pull", "--rebase", "origin", branch)
    except Exception as exc:
        print(f"gitsync: pull skipped ({exc})")
        return False
    if r.returncode != 0:
        try:
            _git("rebase", "--abort", timeout=30)
        except Exception:
            pass
        print("gitsync: pull hit a conflict — kept this machine's version; "
              "resolve in a session (git pull --rebase by hand)")
        return False
    moved = _head() != before
    print("gitsync: pulled new work" if moved else "gitsync: already current")
    return moved


def push():
    if not _has_remote():
        return False
    try:
        r = _git("push", "-q", "origin", "HEAD")
    except Exception as exc:
        print(f"gitsync: push skipped ({exc})")
        return False
    if r.returncode != 0:
        print("gitsync: push failed (offline, or the other machine pushed "
              "first — the next pull sorts it out)")
        return False
    return True


def cycle(label="page updates"):
    """Commit what this machine changed, take the other machine's work, hand
    ours back. Returns True when the pull brought new content."""
    commit_if_dirty(f"{label} {date.today().isoformat()}")
    moved = pull()
    push()
    return moved


if __name__ == "__main__":
    try:
        if "--pull" in sys.argv:
            pull()
        elif "--push" in sys.argv:
            push()
        else:
            cycle()
    except Exception as exc:                    # belt and braces: exit 0, always
        print(f"gitsync: skipped ({exc})")
    sys.exit(0)

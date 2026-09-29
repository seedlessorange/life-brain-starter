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
* Pushing is switched on, never assumed. A remote is not proof the place is
  private: someone who forks the public starter and clones their fork has an
  `origin` anyone can read, and this would publish their journal every
  twenty minutes. config.json `"git_push": true` says this brain's remote is
  its own private copy; without it, nothing leaves the machine by git.
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
        r = _git("commit", "-m", message)
        if r.returncode != 0 and "ident" in (r.stderr or "").lower():
            # A machine where git was never told a name refuses to commit,
            # and the undo silently stops. Her configured name always wins;
            # this stands in only where there is none.
            r = _git("-c", "user.name=life-brain", "-c", "user.email=brain@localhost",
                     "commit", "-m", message)
        return r.returncode == 0
    except Exception:
        return False


CODE_PATHS = ("brain/tools/", ".claude/", ".github/", "CLAUDE.md",
              "CLAUDE.local.md", "brain/reference/")
CODE_EXT = (".py", ".sh", ".command", ".ps1", ".bat", ".js", ".pth")


def _incoming_code(branch):
    """Files the remote would bring in that something here executes or obeys.
    Empty when the fetch fails: the pull then fails the same way."""
    try:
        if _git("fetch", "origin", branch).returncode != 0:
            return []
        r = _git("diff", "--name-only", "HEAD...FETCH_HEAD")
    except Exception:
        return []
    return [f for f in (r.stdout or "").splitlines()
            if f.startswith(CODE_PATHS) or f.endswith(CODE_EXT)]


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
    held = _incoming_code(branch)
    if held:
        # The scripts run whatever lands here, outside any sandbox, within
        # minutes. Code from elsewhere waits for her to pull it by hand, so
        # a stolen GitHub login is not a way onto this Mac.
        print("gitsync: new code on GitHub (%s) — not pulled automatically; "
              "run `git pull --rebase` in a session after a look"
              % ", ".join(held[:5]))
        return False
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


def push_on():
    """config.json `git_push` — true only where she set it."""
    import json
    try:
        with open(os.path.join(ROOT, "brain", "config.json"), encoding="utf-8") as f:
            return json.load(f).get("git_push") is True
    except (OSError, ValueError, AttributeError):
        return False


def push():
    if not _has_remote():
        return False
    if not push_on():
        print("gitsync: push is off (config git_push)")
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

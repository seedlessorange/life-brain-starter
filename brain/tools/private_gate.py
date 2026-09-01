#!/usr/bin/env python3
"""Keep private files out of unattended runs — a Claude Code PreToolUse hook.

The brain already shrinks what the scheduled runs may touch: email is
headers-only, chats are dates-only, sending needs a human click. This is
the same idea for files. `"private"` in brain/config.json lists paths the
night shift and the morning run must never load, so the most intimate text
(the journal, by default) simply does not travel into a model call nobody
is watching.

Wired in .claude/settings.json as a PreToolUse hook on the file tools and
Bash. It reads the pending tool call on stdin and answers with a deny when:

  * the run is unattended — only the scheduled scripts mark it so — and
  * any string in the tool's input mentions a private path.

How a run is known to be unattended: the scheduled scripts (night.sh,
morning.sh and their .ps1 twins) write `brain/.unattended` just before
their claude run and delete it after. A file, not an env var, because
Claude Code runs hooks with a scrubbed environment — LIFEBRAIN_UNATTENDED
reaches the run's own child processes (email_send.py's refusal relies on
it) but never reaches a hook; this was measured, not assumed. The file
only counts while fresh (six hours), so a crashed night shift cannot
leave tomorrow's attended sessions filtered. An attended session, where
she is present and asking, is never filtered.

THE HOOK IS THE SECOND LAYER, NOT THE FIRST. Measured on Claude Code
2.0.76: settings hooks fire in interactive sessions but NOT in headless
`claude -p` runs — which are exactly the runs this must police. So the
load-bearing layer is the OS: the scheduled scripts run `--lock` before
their claude run, which chmods every private path to unreadable (mode 0),
and `--unlock` after, which restores the recorded modes. A run cannot
read a file the OS refuses to open, whatever its prompts say. Crash
safety: the attended-session hook auto-heals — the first tool call of any
attended session restores a stale lock — and `--unlock` is idempotent.
On Windows chmod cannot deny reads, so the lock is an icacls deny ACE
instead: the current user is denied read on each private path, inherited
down the folder, which a headless run cannot open any more than a
chmod-0 file. The owner keeps the implicit right to edit the ACL, which
is what lets `--unlock` (and the attended-session healing) undo it.

Config: `"private": ["brain/journal/"]`. The key absent means the default
(the journal); an explicit `[]` switches the gate off. Paths are relative
to the brain folder, or absolute, or ~-style.

The deny is advice Claude can act on — the run is told the file is private
and to work without it, which is exactly what /today's journal step says
to do. Substring matching is deliberate: it catches Read, Grep, Glob and a
`cat` in Bash alike, and a scheduled run has no honest reason to mention a
private path at all.
"""

import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
BRAIN = os.path.dirname(HERE)
ROOT = os.path.dirname(BRAIN)

DEFAULT_PRIVATE = ["brain/journal/"]
UNATTENDED_FLAG = os.path.join(BRAIN, ".unattended")
LOCK_STATE = os.path.join(BRAIN, ".private-locked")
FLAG_FRESH_SECS = 6 * 3600


def unattended():
    if os.environ.get("LIFEBRAIN_UNATTENDED"):
        return True                       # direct invocation, and tests
    try:
        return (time.time() - os.stat(UNATTENDED_FLAG).st_mtime) < FLAG_FRESH_SECS
    except OSError:
        return False


def private_paths():
    try:
        with open(os.path.join(BRAIN, "config.json"), encoding="utf-8") as f:
            cfg = json.load(f) or {}
    except Exception:
        cfg = {}
    priv = cfg.get("private")
    if priv is None:
        priv = DEFAULT_PRIVATE
    return [str(p) for p in priv if str(p).strip()]


def _fragments():
    """For each private path, the strings that would betray a touch: the
    brain-relative form and the absolute form, /-normalised, lowercase."""
    frags = set()
    root = ROOT.replace(os.sep, "/").rstrip("/")
    for p in private_paths():
        p = os.path.expanduser(p.strip()).replace("\\", "/").rstrip("/")
        if not p:
            continue
        if os.path.isabs(p):
            frags.add(p.lower())
        else:
            frags.add(p.lower())
            frags.add((root + "/" + p).lower())
    return frags


def _strings(value, out):
    if isinstance(value, str):
        out.append(value)
    elif isinstance(value, dict):
        for v in value.values():
            _strings(v, out)
    elif isinstance(value, list):
        for v in value:
            _strings(v, out)


def _targets():
    """The private paths that actually exist, absolute, inside the brain's
    root only — a config typo must never chmod something else on the disk."""
    out = []
    for p in private_paths():
        p = os.path.expanduser(p.strip().rstrip("/\\"))
        ap = os.path.normpath(p if os.path.isabs(p) else os.path.join(ROOT, p))
        if ap.startswith(ROOT + os.sep) and os.path.exists(ap):
            out.append(ap)
    return out


def _icacls(args):
    import subprocess
    try:
        return subprocess.run(["icacls"] + args, capture_output=True,
                              text=True, timeout=30).returncode == 0
    except Exception:
        return False


def lock():
    """Make the private paths unreadable for the duration of a scheduled
    run. On Mac/Linux, chmod 0 on the top entry is enough — an unreadable
    directory refuses everything inside it. On Windows, an icacls deny-read
    ACE on the current user does the same job; (OI)(CI) inherits it to
    everything inside a folder, so a direct path to a child file is refused
    too. A non-NTFS disk where icacls fails leaves only the hook layer —
    rare, and better than refusing to run."""
    if os.name == "nt":
        user = os.environ.get("USERNAME", "").strip()
        if not user:
            return 0
        locked = []
        for ap in _targets():
            spec = (f"{user}:(OI)(CI)(R)" if os.path.isdir(ap)
                    else f"{user}:(R)")
            if _icacls([ap, "/deny", spec]):
                locked.append(ap)
        with open(LOCK_STATE, "w", encoding="utf-8") as f:
            json.dump({"nt_user": user, "paths": locked}, f)
        return 0
    state = {}
    for ap in _targets():
        state[ap] = os.stat(ap).st_mode & 0o777
        os.chmod(ap, 0)
    with open(LOCK_STATE, "w", encoding="utf-8") as f:
        json.dump(state, f)
    return 0


def unlock():
    """Restore what lock() took away. Idempotent, and healing: even with
    the state file gone it restores sane modes (or clears the deny ACE)
    on anything still locked."""
    if os.name == "nt":
        user = os.environ.get("USERNAME", "").strip()
        try:
            with open(LOCK_STATE, encoding="utf-8") as f:
                state = json.load(f)
        except Exception:
            state = {}
        paths = state.get("paths", []) if isinstance(state, dict) else []
        user = (state.get("nt_user") if isinstance(state, dict) else "") or user
        if user:
            for ap in set(paths) | set(_targets()):
                _icacls([ap, "/remove:d", user])
        try:
            os.remove(LOCK_STATE)
        except OSError:
            pass
        return 0
    try:
        with open(LOCK_STATE, encoding="utf-8") as f:
            state = json.load(f)
    except Exception:
        state = {}
    for ap, mode in state.items():
        try:
            os.chmod(ap, mode or 0o700)
        except OSError:
            pass
    for ap in _targets():
        try:
            if not (os.stat(ap).st_mode & 0o400):
                os.chmod(ap, 0o700 if os.path.isdir(ap) else 0o600)
        except OSError:
            pass
    try:
        os.remove(LOCK_STATE)
    except OSError:
        pass
    return 0


def main():
    if not unattended():
        # Her session. The one job here: if a crashed scheduled run left
        # the OS lock in place, put it right before her tool call runs.
        if os.path.exists(LOCK_STATE):
            unlock()
        return 0
    frags = _fragments()
    if not frags:
        return 0
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0
    parts = []
    _strings(payload.get("tool_input") or {}, parts)
    haystack = "\n".join(parts).replace("\\", "/").lower()
    hit = next((f for f in frags if f in haystack), None)
    if not hit:
        return 0
    shown = hit[len(ROOT.lower()):].lstrip("/") if hit.startswith(
        ROOT.replace(os.sep, "/").lower()) else hit
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": (
                f"{shown} is private: unattended runs never load it. "
                "This is by design, not an error — do the work without "
                "it and move on."),
        }
    }))
    return 0


if __name__ == "__main__":
    if "--lock" in sys.argv:
        sys.exit(lock())
    if "--unlock" in sys.argv:
        sys.exit(unlock())
    sys.exit(main())

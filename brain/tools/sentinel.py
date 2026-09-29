#!/usr/bin/env python3
"""The security alarm: tells her when the brain's safety code changes.

    python3 brain/tools/sentinel.py            # what changed since she last approved
    python3 brain/tools/sentinel.py --init     # first run only: record today's state

Some of the brain's protection is macOS's (Touch ID, the sandbox, Full Disk
Access tied to one app). The rest is code: the sandbox rules, the send
gates, the Keychain handling. Code can be rewritten by any Claude session
she runs, and a session can be talked into it by text it reads. This does
not stop that. It makes sure no such change goes unseen: the page shows a
card naming what changed and in which commit, until she confirms with Touch
ID that it was her (serve.py /api/security/seen, through brainconfirm).

The approved state lives in brain/tools/.run-policy/, which the brain's
background runs cannot write. A session with full control could still
rewrite it by hand; that is the limit of an alarm, and it is stated here
rather than hidden.
"""
import ast
import glob
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
BRAIN = os.path.dirname(HERE)
ROOT = os.path.dirname(BRAIN)
SEEN = os.path.join(HERE, ".run-policy", "security-seen.json")

# Whole files: what fences the runs, what gates sending and secrets, and
# what runs outside the sandbox on its own (launchers, schedules).
FILES = {
    "brain/tools/run_policy.py": "the sandbox rules for Claude runs",
    "brain/tools/private_gate.py": "the journal's privacy lock",
    "brain/tools/approve_gate.py": "the approval hook",
    "brain/tools/email_send.py": "sending email",
    "brain/tools/email_read.py": "reading mail headers",
    "brain/tools/mail_local.py": "reading the Mail app",
    "brain/tools/mail_tasks.py": "reading task mail",
    "brain/tools/keychain.py": "the Keychain helper",
    "brain/tools/brainmail.swift": "the Touch ID mail lock",
    "brain/tools/brainconfirm.swift": "the Touch ID confirmation",
    "brain/tools/make_brainmail.sh": "building the Touch ID helpers",
    "brain/tools/brain_app.sh": "Brain Server's start and stop",
    "brain/tools/brain_app.applescript": "the Brain Server app",
    "brain/tools/make_brain_app.sh": "building the Brain Server app",
    "brain/tools/sentinel.py": "this alarm",
    "brain/tools/morning.sh": "the morning job",
    "brain/tools/night.sh": "the night shift",
    ".claude/settings.json": "the hooks every session runs",
    "Open Brain.command": "the brain's launcher",
}
# Built things: a swapped binary or a rewritten app is a change too.
BUILT = {
    "brain/tools/.bin/brainmail": "the Touch ID mail lock (built)",
    "brain/tools/.bin/brainconfirm": "the Touch ID confirmation (built)",
    "Brain Server.app": "the Brain Server app (built)",
}
# Parts of big files that change daily for other reasons: only these.
# (Telegram's owner check sits inside its main loop, too busy to watch.)
REGIONS = {
    "brain/tools/serve.py": {
        "request_is_own": "who may call the page",
        "_guard": "who may call the page",
        "ALLOWED_HOSTS": "who may call the page",
        "ALLOWED_ORIGINS": "who may call the page",
        "GUARD_ENFORCED": "who may call the page",
        "start_agent": "how Claude runs are started",
        "post_draft": "the Approve & send button",
        "email_send_ready": "sending email",
        "post_email_check": "the mail check button",
    },
}
SECTIONS = {
    "CLAUDE.md": {
        "## HARD RULES": "the hard rules",
        "## Executing tasks — the boundary": "the sending boundary",
        "## Confidential material": "the confidential-files rule",
    },
}


def _sha(data):
    return hashlib.sha256(data).hexdigest()[:16]


def _read(rel):
    try:
        with open(os.path.join(ROOT, rel), "rb") as f:
            return f.read()
    except OSError:
        return None


def _built(rel):
    p = os.path.join(ROOT, rel)
    if os.path.isdir(p):
        h = hashlib.sha256()
        for f in sorted(glob.glob(os.path.join(p, "**"), recursive=True)):
            if os.path.isfile(f):
                h.update(os.path.relpath(f, p).encode())
                with open(f, "rb") as fh:
                    h.update(fh.read())
        return h.hexdigest()[:16]
    data = _read(rel)
    return _sha(data) if data is not None else "missing"


def _regions(rel, names):
    src = (_read(rel) or b"").decode("utf-8", "replace")
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return {n: "unparseable" for n in names}
    found = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in names:
            found[node.name] = ast.get_source_segment(src, node) or ""
        elif isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id in names:
                    found[t.id] = ast.get_source_segment(src, node) or ""
    return {n: _sha(found[n].encode()) if n in found else "missing" for n in names}


def _sections(rel, heads):
    lines = (_read(rel) or b"").decode("utf-8", "replace").split("\n")
    out = {}
    for head in heads:
        start = next((i for i, l in enumerate(lines) if l.startswith(head)), None)
        if start is None:
            out[head] = "missing"
            continue
        end = next((j for j in range(start + 1, len(lines))
                    if lines[j].startswith("## ")), len(lines))
        out[head] = _sha("\n".join(lines[start:end]).encode())
    return out


def _states():
    """Settings whose value is the protection itself."""
    try:
        with open(os.path.join(BRAIN, "config.json"), encoding="utf-8") as f:
            cfg = json.load(f)
    except (OSError, ValueError):
        cfg = {}
    return {"state:touch_id": "on" if (cfg.get("email") or {}).get("touch_id") else "OFF"}


def fingerprints():
    """key -> (hash, what it protects)."""
    out = {}
    for rel, what in FILES.items():
        data = _read(rel)
        out[rel] = (_sha(data) if data is not None else "missing", what)
    for rel, what in BUILT.items():
        out[rel] = (_built(rel), what)
    for rel, names in REGIONS.items():
        for n, h in _regions(rel, names).items():
            out[f"{rel} · {n}"] = (h, names[n])
    for rel, heads in SECTIONS.items():
        for head, h in _sections(rel, heads).items():
            out[f"{rel} · {head[3:]}"] = (h, heads[head])
    out["state:touch_id"] = (_states()["state:touch_id"], "Touch ID on the mail password")
    return out


def _seen():
    try:
        with open(SEEN, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _last_commit(rel):
    rel = rel.split(" · ")[0]
    if rel.startswith("state:") or not os.path.exists(os.path.join(ROOT, rel)):
        return ""
    try:
        dirty = subprocess.run(["git", "-C", ROOT, "status", "--porcelain", "--", rel],
                               capture_output=True, text=True, timeout=10).stdout.strip()
        if dirty:
            return "not committed yet"
        r = subprocess.run(["git", "-C", ROOT, "log", "-1", "--format=%h %ad %s",
                            "--date=format:%d %b %H:%M", "--", rel],
                           capture_output=True, text=True, timeout=10)
        return r.stdout.strip()
    except Exception:
        return ""


def changes():
    """What differs from the state she last approved: [{key, what, commit}].
    Empty when nothing has, or when nothing was ever recorded (--init)."""
    seen = _seen()
    if not seen:
        return []
    now = fingerprints()
    out = []
    for key, (h, what) in now.items():
        was = (seen.get("hashes") or {}).get(key)
        if was != h:
            label = "Touch ID for mail is off" if key == "state:touch_id" and h == "OFF" else key
            out.append({"key": key, "label": label, "what": what,
                        "commit": _last_commit(key)})
    return out


def accept(via):
    """Record the current state as approved. `via` says how she confirmed."""
    os.makedirs(os.path.dirname(SEEN), exist_ok=True)
    data = {"at": datetime.now().isoformat(timespec="seconds"), "via": via,
            "hashes": {k: h for k, (h, _) in fingerprints().items()}}
    tmp = SEEN + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1)
    os.replace(tmp, SEEN)
    return data["at"]


def main():
    if "--init" in sys.argv:
        if _seen():
            sys.exit("already recorded; approve changes from the page (Touch ID)")
        print("recorded at", accept("first run"))
        return
    ch = changes()
    if not ch:
        print("no security changes since she last approved"
              if _seen() else "nothing recorded yet: run with --init")
        return
    for c in ch:
        print(f"  {c['label']}: {c['what']}" + (f"  [{c['commit']}]" if c["commit"] else ""))


if __name__ == "__main__":
    main()

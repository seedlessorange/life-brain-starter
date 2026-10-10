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
import difflib
import glob
import hashlib
import json
import os
import re
import subprocess
import sys
import threading
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
BRAIN = os.path.dirname(HERE)
ROOT = os.path.dirname(BRAIN)
SEEN = os.path.join(HERE, ".run-policy", "security-seen.json")

# Whole files: what fences the runs, what gates sending and secrets, and
# what runs outside the sandbox on its own (launchers, schedules).
FILES = {
    "brain/tools/run_policy.py": "the sandbox rules for Claude runs",
    "brain/tools/agents.py": "which agent runs (Claude, Codex, Gemini) and its fences",
    "brain/tools/private_gate.py": "the journal's privacy lock",
    "brain/tools/privacy.py": "the privacy and safety settings",
    "brain/tools/privacy_log.py": "the record of what runs opened",
    "brain/tools/approve_gate.py": "the approval hook",
    "brain/tools/new_file_gate.py": "the new-files-only hook for a waiting conversation",
    "brain/tools/email_send.py": "sending email",
    "brain/tools/email_read.py": "reading mail headers",
    "brain/tools/mail_local.py": "reading the Mail app",
    "brain/tools/mail_tasks.py": "reading task mail",
    "brain/tools/keychain.py": "the Keychain helper",
    "brain/tools/browser_core.py": "the job hunt's browser helpers: who may start them",
    "brain/tools/browser_apply.py": "filling application forms in Chrome",
    "brain/tools/browser_linkedin.py": "reading LinkedIn in Chrome",
    "brain/tools/browser_scan.py": "searching job sites in a browser",
    "brain/tools/brainmail.swift": "the Touch ID mail lock",
    "brain/tools/brainconfirm.swift": "the Touch ID confirmation",
    "brain/tools/make_brainmail.sh": "building the Touch ID helpers",
    "brain/tools/pen.swift": "Brain Pen, which reads and types into other apps",
    "brain/tools/make_pen_app.sh": "building Brain Pen",
    "brain/tools/brain_app.sh": "Brain Server's start and stop",
    "brain/tools/brain_app.applescript": "the Brain Server app",
    "brain/tools/make_brain_app.sh": "building the Brain Server app",
    "brain/tools/sentinel.py": "this alarm",
    # What the watched scripts trust (9 Oct audit): night.sh evals what
    # night_config prints, every model call goes through llm.py, and
    # gitsync is what pushes the brain to GitHub.
    "brain/tools/night_config.py": "the night shift's settings, which its script runs",
    "brain/tools/llm.py": "how small model calls are made",
    "brain/tools/gitsync.py": "what the brain commits and pushes to GitHub",
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
    "Brain Pen.app": "Brain Pen, which reads and types into other apps (built)",
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
        "privacy_change": "who may loosen the privacy settings",
    },
    "brain/tools/beeper.py": {
        "send_message": "sending chat messages",
    },
    "brain/tools/sessions.py": {
        "claude_env": "how Sessions conversations start Claude",
        "new_convo": "how Sessions conversations start Claude",
    },
    "brain/tools/telegram_bridge.py": {
        "_capture_only": "Telegram's capture-only mode",
        "_capture_text": "Telegram's capture-only mode",
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
            # From the first decorator: a wrapper added above a watched
            # function changes what it does, and get_source_segment starts
            # at `def`, so the hash never moved (9 Oct audit).
            first = min([d.lineno for d in node.decorator_list] + [node.lineno])
            found[node.name] = "\n".join(
                src.split("\n")[first - 1:node.end_lineno])
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
    try:
        sys.path.insert(0, HERE)
        import privacy
        priv = privacy.fingerprint()
    except Exception as exc:
        priv = "unreadable: " + type(exc).__name__
    try:
        import privacy_log
        trips = privacy_log.trips_fingerprint()
    except Exception as exc:
        trips = "unreadable: " + type(exc).__name__
    # Her consent to mail reading lives in config.json, which runs can write
    # (9 Oct audit): reading on, the Mac's Mail index, the 7am mail check and
    # the task-mail senders. The page re-approves its own changes to these.
    # Claude Code adds allow rules to settings.local.json whenever she
    # approves a prompt, so the file itself churns; its hooks are what run
    # outside the sandbox, and every brain run loads it (9 Oct audit).
    try:
        with open(os.path.join(ROOT, ".claude", "settings.local.json"),
                  encoding="utf-8") as f:
            local = json.load(f)
        hooks = json.dumps({k: local.get(k) for k in ("hooks", "env",
                            "apiKeyHelper", "statusLine") if k in local},
                           sort_keys=True)
    except FileNotFoundError:
        hooks = "{}"
    except (OSError, ValueError) as exc:
        hooks = "unreadable: " + type(exc).__name__
    em = cfg.get("email") or {}
    rd = em.get("read") or {}
    mail = json.dumps({"on": bool(rd.get("on")), "mac": bool(rd.get("mac_mail")),
                       "morning": (cfg.get("plan_sources") or {}).get("mail"),
                       "senders": sorted((em.get("tasks") or {}).get("senders")
                                         or [])}, sort_keys=True)
    return {"state:touch_id": "on" if (cfg.get("email") or {}).get("touch_id") else "OFF",
            "state:privacy": priv, "state:trips": trips, "state:mail": mail,
            "state:local_hooks": hooks}


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
    st = _states()
    out["state:touch_id"] = (st["state:touch_id"], "Touch ID on the mail password")
    # Hashed like a file: the alarm compares, and the card shows no settings.
    out["state:privacy"] = (_sha(st["state:privacy"].encode()),
                            "the privacy settings (changed outside the page?)")
    out["state:local_hooks"] = (_sha(st["state:local_hooks"].encode()),
                                "hooks in this folder's local Claude settings")
    out["state:mail"] = (_sha(st["state:mail"].encode()),
                         "what mail the brain may read (switched outside "
                         "the page?)")
    out["state:trips"] = (_sha(st["state:trips"].encode()),
                          "a run on a timer opened something your privacy "
                          "level locks (Privacy page, Where your words went)")
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
        if os.path.exists(SEEN):
            # There but unreadable: an alarm that cannot compare must say so,
            # not report all clear (9 Oct audit).
            raise RuntimeError("the record of what you last approved can't "
                               "be read")
        return []
    now = fingerprints()
    out = []
    for key, (h, what) in now.items():
        was = (seen.get("hashes") or {}).get(key)
        if was != h:
            # Words, never the key: the card printed "state:mail" glued to
            # its sentence (9 Oct). A new entry has nothing to compare with.
            if key == "state:touch_id" and h == "OFF":
                label = "Touch ID for mail is off"
            elif was is None:
                label = "newly watched: approving records how it is now"
            elif key == "state:trips":
                label = "a new one since you last approved"
            elif key.startswith("state:"):
                label = "changed since you last approved"
            else:
                label = key
            out.append({"key": key, "label": label, "what": what,
                        "commit": _last_commit(key)})
    return out


# The brain's own saves: their message says when, never what (7 Oct: most of
# a day's security changes went in under "page updates").
AUTO_SAVE = re.compile(r"^(page updates \d{4}-\d{2}-\d{2}|page session snapshot"
                       r"|auto snapshot)", re.I)


def _git(*args):
    try:
        return subprocess.run(["git", "-C", ROOT] + list(args), capture_output=True,
                              text=True, timeout=15).stdout
    except Exception:
        return ""


def _segment(text, key):
    """The watched part of a file's text: the same function or section the
    fingerprint covers, so the lines shown are the lines that tripped it."""
    rel, _, part = key.partition(" · ")
    if not part:
        return text
    if rel in REGIONS:
        try:
            tree = ast.parse(text)
        except SyntaxError:
            return text
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == part:
                return ast.get_source_segment(text, node) or ""
            if isinstance(node, ast.Assign) and any(
                    isinstance(t, ast.Name) and t.id == part for t in node.targets):
                return ast.get_source_segment(text, node) or ""
        return ""
    head = next((h for h in SECTIONS.get(rel, {}) if h[3:] == part), None)
    if head:
        lines = text.split("\n")
        start = next((i for i, l in enumerate(lines) if l.startswith(head)), None)
        if start is None:
            return ""
        end = next((j for j in range(start + 1, len(lines))
                    if lines[j].startswith("## ")), len(lines))
        return "\n".join(lines[start:end])
    return text


def _defs(text):
    """(first line, last line, name) for every function and class."""
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []
    return [(n.lineno, getattr(n, "end_lineno", n.lineno), n.name)
            for n in ast.walk(tree)
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))]


def _where(defs, lines):
    """The innermost function holding each changed line, by name."""
    out = []
    for ln in lines:
        inside = [d for d in defs if d[0] <= ln <= d[1]]
        if inside:
            name = min(inside, key=lambda d: d[1] - d[0])[2]
            if name not in out:
                out.append(name)
    return out


def _state_evidence(key):
    """What a watched setting says now, in plain lines, so approving it is
    approving something she can read (9 Oct: these showed a bare key)."""
    try:
        with open(os.path.join(BRAIN, "config.json"), encoding="utf-8") as f:
            cfg = json.load(f)
    except (OSError, ValueError):
        cfg = {}
    em = cfg.get("email") or {}
    rd = em.get("read") or {}

    def onoff(v):
        return "on" if v else "off"
    if key == "state:mail":
        snd = (em.get("tasks") or {}).get("senders") or []
        return [f"Reading who emailed you: {onoff(rd.get('on'))}",
                f"Also the Mac's Mail app: {onoff(rd.get('mac_mail'))}",
                "The 7am mail check: " + onoff((cfg.get("plan_sources") or {})
                                               .get("mail")),
                "Senders whose mail is read for tasks: "
                + (", ".join(snd) if snd else "none")]
    if key == "state:touch_id":
        return [f"Touch ID on the mail password: {onoff(em.get('touch_id'))}"]
    if key == "state:trips":
        try:
            sys.path.insert(0, HERE)
            import privacy_log
            trips = [e for e in privacy_log.read(30) if e.get("trip")][-3:]
        except Exception:                                # noqa: BLE001
            trips = []
        names = {"journal": "the journal", "people": "people.md",
                 "money": "the money files", "transcripts": "the transcripts"}
        from datetime import datetime as _dt
        return [f"{_dt.fromisoformat(e['t']):%-d %b} at {e['t'][11:16]}: a "
                + ("night" if e["t"][11:13] < "05" else "morning")
                + " run opened " + " and ".join(names.get(k, k)
                                                 for k in e["trip"])
                for e in trips] or ["No trips in the last 30 days"]
    if key == "state:local_hooks":
        try:
            with open(os.path.join(ROOT, ".claude", "settings.local.json"),
                      encoding="utf-8") as f:
                local = json.load(f)
        except (OSError, ValueError):
            local = {}
        hooks = local.get("hooks") or {}
        return ([f"{ev}: " + ", ".join(h.get("command", "?")[:60]
                                       for m in hooks[ev] for h in m.get("hooks", []))
                 for ev in hooks] or ["No hooks in the local settings"])
    if key == "state:privacy":
        return ["The Privacy page shows the settings as they are now"]
    return []


def details():
    """Everything the security card shows, so she can approve knowing what
    she approves: per change, the commits since her last approval (and which
    were only the brain's automatic saves), how many lines, in which
    functions, and the lines themselves. Approving clears the alarm and
    changes no code, so the card has to carry the evidence."""
    seen = _seen() or {}
    at = seen.get("at") or ""
    base = _git("rev-list", "-1", "--before=" + at, "HEAD").strip() if at else ""
    items = []
    for c in changes():
        key, rel = c["key"], c["key"].split(" · ")[0]
        item = dict(c, file=rel, part=c["key"].partition(" · ")[2], kind="code",
                    commits=[], uncommitted=False, added=0, removed=0,
                    funcs=[], diff=[])
        if key.startswith("state:"):
            item["kind"] = "state"
            item["evidence"] = _state_evidence(key)
            items.append(item)
            continue
        if rel in BUILT:
            item["kind"] = "built"
        for ln in _git("log", "--since=" + at, "--format=%h%x09%ad%x09%s",
                       "--date=format:%d %b %H:%M", "--", rel).splitlines()[:8]:
            h, _, rest = ln.partition("\t")
            when, _, subject = rest.partition("\t")
            item["commits"].append({"hash": h, "when": when, "subject": subject,
                                    "auto": bool(AUTO_SAVE.match(subject))})
        item["uncommitted"] = bool(_git("status", "--porcelain", "--", rel).strip())
        if item["part"]:
            # A watched function or section: only the commits that changed
            # it, not every commit to the big file around it.
            item["commits"] = [
                m for m in item["commits"]
                if _segment(_git("show", f"{m['hash']}^:{rel}"), key)
                != _segment(_git("show", f"{m['hash']}:{rel}"), key)]
            if item["uncommitted"]:
                item["uncommitted"] = (_segment(_git("show", f"HEAD:{rel}"), key)
                                       != _segment((_read(rel) or b"").decode(
                                           "utf-8", "replace"), key))
        if item["kind"] == "built":
            items.append(item)
            continue
        old = _segment(_git("show", f"{base}:{rel}") if base else "", key)
        new = _segment((_read(rel) or b"").decode("utf-8", "replace"), key)
        a, b = old.splitlines(), new.splitlines()
        changed_new, changed_old = [], []
        for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
            if tag == "equal":
                continue
            item["removed"] += i2 - i1
            item["added"] += j2 - j1
            changed_old += range(i1 + 1, i2 + 1)
            changed_new += range(j1 + 1, j2 + 1)
        if rel.endswith(".py") and not item["part"]:
            item["funcs"] = (_where(_defs(new), changed_new)
                             + [f for f in _where(_defs(old), changed_old)
                                if f not in _where(_defs(new), changed_new)])[:6]
        diff = [l for l in difflib.unified_diff(a, b, n=2, lineterm="")
                if not l.startswith(("---", "+++"))]
        item["diff"] = diff[:160] + ([f"… {len(diff) - 160} more lines"]
                                     if len(diff) > 160 else [])
        items.append(item)
    return {"since": at, "items": items}


def _fresh():
    """Today's fingerprints, worked out by the sentinel.py now on disk.

    The server imports this module once, when it starts. On 8 Oct a session
    added two watched items while it ran; her Touch ID approval came from the
    server's older copy, which had never heard of them, so they stayed on the
    card however often she approved. The card is drawn by a fresh build, so
    the approval is computed fresh too: both see the same list."""
    r = subprocess.run([sys.executable, os.path.abspath(__file__), "--hashes"],
                       capture_output=True, text=True, timeout=120, cwd=ROOT)
    if r.returncode:
        raise RuntimeError("could not read the safety code's state: "
                           + (r.stderr or "").strip()[-300:])
    return json.loads(r.stdout)


# accept and accept_one are read-modify-write on one file, from the page's
# threads: one lock and a temp name per writer, so neither undoes the other.
_LOCK = threading.Lock()


def _save_seen(data):
    tmp = "%s.%d.%d.tmp" % (SEEN, os.getpid(), threading.get_ident())
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1)
    os.replace(tmp, SEEN)


def accept(via):
    """Record the current state as approved. `via` says how she confirmed."""
    os.makedirs(os.path.dirname(SEEN), exist_ok=True)
    with _LOCK:
        data = {"at": datetime.now().isoformat(timespec="seconds"), "via": via,
                "hashes": _fresh()}
        _save_seen(data)
    return data["at"]


def accept_one(key, via):
    """Approve a single entry: a privacy setting she just changed on the page
    (one tap to tighten, Touch ID to loosen). Every other change keeps
    waiting for her fingerprint on the card. Before the first approval there
    is nothing to update."""
    with _LOCK:
        seen = _seen()
        h = _fresh().get(key)
        if not seen or h is None:
            return None
        seen["hashes"][key] = h
        _save_seen(seen)
    return via


def approved(key):
    """True when this entry is as she last approved it (or nothing was ever
    recorded). The page re-approves its own switch only from an approved
    state, so her tap never launders a change something else made first."""
    seen = _seen()
    if not seen:
        return True
    return (seen.get("hashes") or {}).get(key) == _fresh().get(key)


def main():
    if "--hashes" in sys.argv:
        # Read-only: what accept() records, from this file as it is now.
        print(json.dumps({k: h for k, (h, _) in fingerprints().items()}))
        return
    if "--init" in sys.argv:
        if _seen():
            sys.exit("already recorded; approve changes from the page (Touch ID)")
        print("recorded at", accept("first run"))
        return
    if "--diff" in sys.argv:
        d = details()
        print("last approved:", d["since"] or "never")
        for it in d["items"]:
            print(f"\n== {it['what']}  [{it['key']}]")
            for c in it["commits"]:
                print(f"   {c['when']}  {c['hash']}  "
                      + ("(automatic save: says nothing about what)" if c["auto"]
                         else c["subject"]))
            if it["uncommitted"]:
                print("   not committed yet")
            if it["kind"] == "code":
                print(f"   +{it['added']} -{it['removed']} lines"
                      + (" in " + ", ".join(it["funcs"]) if it["funcs"] else ""))
                print("\n".join("   " + l for l in it["diff"]))
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

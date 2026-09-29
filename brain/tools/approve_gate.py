#!/usr/bin/env python3
"""Ask before it runs: a PreToolUse hook that waits for her answer.

A headless run cannot stop and ask the way the terminal does, so a
conversation was either free to act or read-only, with nothing in between.
This sits in front of the tools that change things: it writes what the
conversation wants to do into brain/.approvals.json, the Sessions page shows
it with Allow and Don't, and the tool call waits here until she answers.

No answer inside the window is a no, with a reason the conversation can read,
because a silent yes while she is away is the one outcome worth ruling out.

Wired by sessions.py when a conversation is in "asks first" mode:
    --settings '{"hooks":{"PreToolUse":[{"matcher":"Bash|Write|Edit|…",
                 "hooks":[{"type":"command","command":"… approve_gate.py --convo <id>"}]}]}}'
"""
import argparse
import json
import os
import sys
import time
import uuid
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
BRAIN = os.path.dirname(HERE)
STORE = os.path.join(BRAIN, ".approvals.json")
WAIT_SECONDS = 600
POLL = 0.7


def _load():
    try:
        with open(STORE, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {"pending": [], "answered": {}}


def _save(data):
    tmp = STORE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1, ensure_ascii=False)
    os.replace(tmp, STORE)


def summarise(tool, inp, cwd=""):
    """One line she can decide on without reading JSON. The whole path, not
    just the name: "write pre-commit" could be .git/hooks/pre-commit."""
    inp = inp or {}
    path = str(inp.get("file_path") or "")
    if path and cwd and os.path.realpath(path).startswith(os.path.realpath(cwd) + os.sep):
        path = os.path.relpath(os.path.realpath(path), os.path.realpath(cwd))
    if tool == "Bash":
        return "run: " + str(inp.get("command") or "")[:300]
    if tool == "Write":
        return "write " + (path or "a file")
    if tool in ("Edit", "MultiEdit", "NotebookEdit"):
        return "edit " + (path or "a file")
    return tool


def detail(tool, inp):
    inp = inp or {}
    if tool == "Bash":
        return str(inp.get("command") or "")[:2000]
    if tool == "Write":
        return str(inp.get("content") or "")[:1500]
    if tool in ("Edit", "MultiEdit"):
        edits = inp.get("edits") or [inp]
        out = []
        for e in edits[:4]:
            out.append("- " + str(e.get("old_string") or "")[:300]
                       + "\n+ " + str(e.get("new_string") or "")[:300])
        return "\n\n".join(out)
    return json.dumps(inp)[:1200]


def decide(decision, reason):
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": decision,
        "permissionDecisionReason": reason}}))
    return 0


def convo_for(session_id):
    """Which conversation this run belongs to, and whether she asked to be
    consulted in it. The hook fires for every Claude session in the folder,
    including the terminal, so anything it cannot place is left alone."""
    try:
        with open(os.path.join(BRAIN, "sessions.json"), encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None
    for c in data.get("convos") or []:
        if c.get("sid") and c["sid"] == session_id:
            return c
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--convo", default="")
    ap.add_argument("--wait", type=int, default=WAIT_SECONDS)
    a = ap.parse_args()
    # Not ours to judge: say nothing, and the run's own permission rules
    # decide. An explicit "allow" here would skip those rules entirely —
    # which is how, until 26 Sep, this hook quietly waved every Write and
    # Edit past the sandboxed runs' deny list (see reference/security.md).
    try:
        ev = json.load(sys.stdin)
    except ValueError:
        return 0

    convo = convo_for(ev.get("session_id") or "")
    if not convo or not convo.get("careful"):
        return 0
    a.convo = convo["id"]

    tool = ev.get("tool_name") or "?"
    inp = ev.get("tool_input") or {}
    aid = uuid.uuid4().hex[:12]
    data = _load()
    data["pending"] = [p for p in data.get("pending", [])
                       if time.time() - p.get("ts", 0) < 3600]
    data["pending"].append({
        "id": aid, "convo": a.convo, "tool": tool,
        "summary": summarise(tool, inp, ev.get("cwd") or ""),
        "detail": detail(tool, inp),
        "cwd": ev.get("cwd") or "", "ts": time.time(),
        "at": datetime.now().strftime("%H:%M:%S")})
    _save(data)

    end = time.time() + a.wait
    while time.time() < end:
        time.sleep(POLL)
        answer = (_load().get("answered") or {}).get(aid)
        if not answer:
            continue
        data = _load()
        data["pending"] = [p for p in data.get("pending", []) if p["id"] != aid]
        data["answered"].pop(aid, None)
        _save(data)
        if answer.get("allow"):
            # Her yes lifts this gate only: say nothing, and the run's own
            # rules (the deny list, the sandbox) still decide. An "allow"
            # here would override them, and a run that wrote the approvals
            # file could have answered for her (it no longer can).
            return 0
        return decide("deny", answer.get("reason")
                      or "she said no on the page. Ask her what to do instead "
                         "rather than trying another way around it.")

    data = _load()
    data["pending"] = [p for p in data.get("pending", []) if p["id"] != aid]
    _save(data)
    return decide("deny", "nobody answered within %d minutes, so this was not "
                          "done. Say what you were about to do and leave it to "
                          "her." % (a.wait // 60))


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""The hook in front of a waiting conversation's Write tool: new files only.

run_policy.py's `waiting` profile lets a brain conversation that is waiting
on another one save NEW files under drafts/ and files/, so a CV she asked for
does not sit unsaved until the other conversation finishes. The folder fence
is a permission rule; "never overwrite" was only an instruction until a test
on 7 Oct: asked to, the model read her CV and wrote it back with her name
changed. A rule the model can be talked out of is not a wall, so this is the
wall: Claude Code runs it before every Write, Edit or MultiEdit in that
profile, and exit code 2 refuses the call with the reason shown to the model.

Fails closed: input it cannot read is a refusal. It lives in brain/tools/,
which no run may write.
"""
import json
import os
import sys


def main():
    try:
        ev = json.load(sys.stdin)
        inp = ev.get("tool_input") or {}
        tool = ev.get("tool_name") or ""
        path = str(inp.get("file_path") or inp.get("notebook_path") or "")
    except (ValueError, AttributeError):
        print("refused: could not read the tool call", file=sys.stderr)
        return 2
    if tool != "Write":
        print("refused: while another conversation is changing this folder, "
              "this one can only create new files", file=sys.stderr)
        return 2
    if not path:
        print("refused: no file named", file=sys.stderr)
        return 2
    if ".." in path.replace("\\", "/").split("/"):
        # drafts/nope/../cv.md passed: lexists() fails on the missing folder
        # while the write would land on the existing drafts/cv.md (9 Oct).
        print("refused: name the file directly, without ..", file=sys.stderr)
        return 2
    if not os.path.isabs(path):
        path = os.path.join(ev.get("cwd") or os.getcwd(), path)
    if os.path.lexists(path) or os.path.lexists(os.path.realpath(path)):
        print("refused: %s already exists, and while another conversation is "
              "changing this folder this one may only create new files. Say "
              "you will change it once that one finishes." % path,
              file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())

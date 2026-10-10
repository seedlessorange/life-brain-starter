#!/usr/bin/env python3
"""Her writing style, ready to paste into another tool (her ask, 2 Oct).

    python3 brain/tools/style.py            # the full version
    python3 brain/tools/style.py --short    # the short one
    python3 brain/tools/style.py --stamp    # mark the short one current

writing-rules.md is written for the brain's own Claude: it opens with how to
load and update it, and its corrections log carries dates and bookkeeping.
Pasted into another tool that is noise, so `full()` takes it off. It is
derived from the file on every call, never stored, so there is still one
voice guide.

The short version, writing-style-short.md, is for boxes with a small limit
(ChatGPT's custom instructions take 1,500 characters). It is a condensation
and can fall behind, so it records a hash of the rules it was written from
and `stale()` says when they have changed since. A session that changes the
rules checks the short version still holds, then runs --stamp.
"""
import hashlib
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BRAIN = os.path.dirname(HERE)
if HERE not in sys.path:
    sys.path.insert(0, HERE)

RULES = os.path.join(BRAIN, "writing-rules.md")
SHORT = os.path.join(BRAIN, "writing-style-short.md")
SHORT_LIMIT = 1500


def _read(path):
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except OSError:
        return ""


def _body(raw):
    import md as MD
    return MD.split_frontmatter(raw)[1].strip()


def _hash(text):
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]


def full():
    """The voice guide minus the brain's machinery, in the first person."""
    body = _body(_read(RULES))
    if not body:
        return ""
    out = []
    in_log = False
    for block in re.split(r"\n\s*\n", body):
        b = block.strip()
        # How the brain loads and grows the file: meaningless elsewhere.
        if b.startswith(("*This file learns", "Append-only.")):
            continue
        if b.startswith("*Claude:"):
            b = re.sub(r"\s+", " ", b)
            b = re.sub(r"^\*Claude:[^.]*\.\s*", "", b).strip("* ")
            for a, z in (("Her languages", "My languages"),
                         ("or Spanish — match", "or Spanish, so match"),
                         ("her chats with you", "my chats with you"),
                         ("she is feminine", "I am feminine")):
                b = b.replace(a, z)
        if b.startswith("## "):
            in_log = "learned from corrections" in b.lower()
            if in_log:
                b = "## Lessons from past corrections"
        if in_log and b.startswith("- **"):
            if "folded in" in b.split("**")[1].lower():
                continue           # a pointer to rules already above
            # "**2026-09-30, later (Venture website).**" -> "**Venture website.**"
            b = re.sub(r"^- \*\*\d{4}-\d{2}(?:-\d{2})?(?:, later)?\s*\((.+?)\)\.\*\*",
                       lambda m: "- **" + m.group(1)[:1].upper()
                       + m.group(1)[1:] + ".**", b)
        out.append(b)
    text = "\n\n".join(out)
    # The guide bans em dashes; a pasted copy full of them teaches the
    # opposite. A colon reads right in every place the file uses one. The
    # file itself is hers to change.
    text = re.sub(r"\s*—\s*", ": ", text)
    return text.strip() + "\n"


def short():
    return _body(_read(SHORT)) + "\n" if _read(SHORT) else ""


def stale():
    """True when the rules changed after the short version was written."""
    import md as MD
    meta, _ = MD.split_frontmatter(_read(SHORT))
    rules = _body(_read(RULES))
    return bool(rules) and (meta or {}).get("rules") != _hash(rules)


def stamp():
    raw = _read(SHORT)
    if not raw:
        raise SystemExit("no short version to stamp")
    h = _hash(_body(_read(RULES)))
    raw = re.sub(r"^rules:.*$", f"rules: {h}", raw, count=1, flags=re.M)
    with open(SHORT, "w", encoding="utf-8") as f:
        f.write(raw)
    return h


if __name__ == "__main__":
    if "--stamp" in sys.argv:
        print("stamped", stamp())
    elif "--short" in sys.argv:
        s = short()
        sys.stdout.write(s)
        print(f"\n[{len(s.strip())} characters, limit {SHORT_LIMIT}"
              + ("; OLDER THAN THE RULES" if stale() else "") + "]",
              file=sys.stderr)
    else:
        sys.stdout.write(full())

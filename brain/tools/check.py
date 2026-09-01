#!/usr/bin/env python3
"""The brain's linter: mechanical integrity checks, no AI, no tokens.

    python3 brain/tools/check.py          # print problems, exit 1 if any

Runs automatically at the end of every build. The point (borrowed from
Silica's write-verification idea): a long run can quietly break a file in
ways the parsers absorb silently — an invented status word makes a
workstream invisible in the counts, twin checkbox lines make the page's
tickboxes refuse, a Ball change without Since disables the chase reminders.
Detection at write time beats archaeology at failure time.

Every check here is mechanical on purpose. A check that needs judgement
belongs in the audit, not in a script that runs forty times a day.
"""

import os
import re
import sys

TOOLS = os.path.dirname(os.path.abspath(__file__))
BRAIN = os.path.dirname(TOOLS)
sys.path.insert(0, TOOLS)

import model as M  # noqa: E402

# The fixed status vocabulary — CLAUDE.md's list, lowercase.
STATUSES = {"moving", "stalled", "blocked", "waiting", "not started",
            "done", "dropped", "parked"}

# Files whose `- [ ]` lines get page tickboxes that find their line by a
# hash of its text — twins make the tick refuse rather than guess.
TICKBOX_FILES = ("workstreams.md", "goals.md", "season.md", "questions.md",
                 "today.md")

# The generated pages, and the source trees they are built from. A source
# newer than a page means someone edited brain/ and skipped the rebuild —
# the owner is reading stale content.
PAGES = ("index.html", "map.html", "rooms.html")


def _read(name):
    try:
        with open(os.path.join(BRAIN, name), encoding="utf-8") as f:
            return f.read()
    except OSError:
        return ""


def check(today=None):
    """Return a list of problem strings, empty when the brain is sound."""
    problems = []

    # -- workstreams.md ------------------------------------------------------
    text = _read("workstreams.md")
    items = M.parse(text)
    seen_names = set()
    for w in items:
        nm = w["name"]
        if nm.lower() in seen_names:
            problems.append(f'workstreams.md: two workstreams named "{nm}" — '
                            "the second shadows the first")
        seen_names.add(nm.lower())
        status = (w["fields"].get("status") or "").strip().lower()
        if not status:
            problems.append(f'workstreams.md: "{nm}" has no Status — '
                            "invisible in every count")
        elif status not in STATUSES:
            problems.append(f'workstreams.md: "{nm}" has Status "{status}" — '
                            "not a word the parser knows "
                            "(Moving, Stalled, Blocked, Waiting, Not started, "
                            "Done, Dropped, Parked)")
        ball = (w["fields"].get("ball") or "").strip().lower()
        if (ball and ball not in ("", "nobody", "me")
                and not w["fields"].get("since")
                and not w["fields"].get("touched")):
            problems.append(f'workstreams.md: "{nm}" has Ball: '
                            f'{w["fields"].get("ball")} but no Since — '
                            "the chase reminder is silently off")

    # -- twin checkbox lines -------------------------------------------------
    for fname in TICKBOX_FILES:
        seen = {}
        for i, line in enumerate(_read(fname).split("\n"), 1):
            m = re.match(r"^\s*-\s*\[\s\]\s*(.+)$", line)
            if not m:
                continue
            key = m.group(1).strip().lower()
            if key in seen:
                problems.append(f"{fname}: lines {seen[key]} and {i} are the "
                                f'same open checkbox ("{key[:50]}") — '
                                "the page tick will refuse both")
            else:
                seen[key] = i

    # -- people.md: circle typos make a person invisible ---------------------
    cfg = M.load_config()
    known = {c["name"].lower() for c in M.circles(cfg).values()}
    known.add("everyone else")
    for p in M.load_people(today=today):
        c = (p.get("circle") or "").strip()
        if c and c.lower() not in known:
            problems.append(f'people.md: "{p["name"]}" has circle "{c}" — '
                            "not in config.json, so no rhythm applies")

    # -- habits.md: duplicate headings would merge two logs ------------------
    seen = set()
    for line in _read("habits.md").split("\n"):
        m = re.match(r"^##\s+(.*)$", line.strip())
        if m:
            nm = m.group(1).strip().lower()
            if nm in seen:
                problems.append(f'habits.md: two habits named "{m.group(1)}"')
            seen.add(nm)

    # -- stale generated pages ----------------------------------------------
    newest_src, newest_name = 0, ""
    for root, dirs, files in os.walk(BRAIN):
        dirs[:] = [d for d in dirs if d not in
                   ("journal", "archive", "files", "fonts", "art", "avatars")]
        for f in files:
            if f.endswith(".md") or f == "config.json":
                p = os.path.join(root, f)
                try:
                    mt = os.path.getmtime(p)
                except OSError:
                    continue
                if mt > newest_src:
                    newest_src, newest_name = mt, os.path.relpath(p, BRAIN)
    for page in PAGES:
        try:
            if os.path.getmtime(os.path.join(BRAIN, page)) < newest_src - 2:
                problems.append(f"{page} is older than {newest_name} — "
                                "the owner is reading stale pages; rebuild")
        except OSError:
            pass

    return problems


if __name__ == "__main__":
    probs = check()
    for p in probs:
        print(f"  ⚠ {p}")
    if not probs:
        print("check.py: the brain is sound")
    sys.exit(1 if probs else 0)

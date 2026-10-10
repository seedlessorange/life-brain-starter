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


TASK_WORDS = 25

# Text that leaves the brain for someone else: drafts she sends as they are,
# and the markdown in To share. Notes are hers to read, so they are not here.
SENT_KINDS = ("email", "message", "form")
TO_SHARE = os.path.join(os.path.dirname(BRAIN), "To share")


def _read(name):
    try:
        with open(os.path.join(BRAIN, name), encoding="utf-8") as f:
            return f.read()
    except OSError:
        return ""


def _texts_for_others(textcheck):
    """(label, text) for every unsent email, message or form draft and every
    .md under To share. An email's subject is read too, so it is checked."""
    import glob
    for path in sorted(glob.glob(os.path.join(BRAIN, "drafts", "*.md"))):
        try:
            with open(path, encoding="utf-8") as f:
                meta, body = textcheck.split_frontmatter(f.read())
        except OSError:
            continue
        if (meta.get("kind", "note").lower() not in SENT_KINDS
                or meta.get("status", "draft").lower() in ("sent", "discarded")):
            continue
        subject = meta.get("subject", "")
        yield ("drafts/" + os.path.basename(path),
               (subject + "\n\n" + body) if subject else body)
    for root, dirs, files in os.walk(TO_SHARE):
        for f in sorted(files):
            if f.endswith(".md") and not f.startswith(("~$", ".")):
                p = os.path.join(root, f)
                try:
                    with open(p, encoding="utf-8") as fh:
                        yield os.path.relpath(p, os.path.dirname(BRAIN)), fh.read()
                except OSError:
                    continue


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
        # A task line is what she does, readable cold. Past ~25 words it has
        # swallowed its own backstory, and on a card the action is lost in it
        # (M2's 50 words, 27 Sep). The backstory belongs on an indented line
        # under the task, where it travels as the task's own note.
        for t in w["tasks"]:
            n = len(t["text"].split())
            if not t["done"] and not t.get("dropped") and n > TASK_WORDS:
                problems.append(f'workstreams.md: "{t["text"][:50]}…" is {n} '
                                "words — cut it to the action and move the "
                                "rest to an indented note under it")

    # -- twin checkbox lines -------------------------------------------------
    # Keyed exactly as serve.task_action finds a line: the bare words' hash,
    # over open AND ticked lines. Comparing raw open lines missed a re-added
    # task beside its ticked twin, or two with different dates (9 Oct audit),
    # and the server refuses every action on both.
    import md as MD
    for fname in TICKBOX_FILES:
        seen = {}
        for i, line in enumerate(_read(fname).split("\n"), 1):
            m = re.match(r"^(\s*[-*]\s+)\[([ xX])\]\s+(.*)$", line)
            if not m:
                continue
            key = MD.taskkey(MD.bare(m.group(3)))
            is_open = m.group(2) == " "
            if key in seen:
                j, was_open = seen[key]
                if is_open or was_open:
                    problems.append(
                        f"{fname}: lines {j} and {i} have the same words "
                        f'("{MD.bare(m.group(3))[:50]}") — the page tick will '
                        "refuse both; make one of them different")
                seen[key] = (i, was_open or is_open)
            else:
                seen[key] = (i, is_open)

    # -- deadlines in words ---------------------------------------------------
    # CLAUDE.md: dates or ranges, never "this week". A word deadline is
    # re-read against today every morning, so it never goes late (9 Oct:
    # "due this month" had slid from September into October).
    for fname in TICKBOX_FILES:
        for i, line in enumerate(_read(fname).split("\n"), 1):
            if not re.match(r"^\s*[-*]\s+\[ \]", line):
                continue
            for mm in re.finditer(r"\((due|by) ([^)]+)\)", line):
                val = mm.group(2).strip()
                if not re.match(r"\d{4}-\d{2}-\d{2}", val) \
                        and M.parse_due(val):
                    problems.append(
                        f'{fname}:{i}: "({mm.group(1)} {val})" is a deadline in '
                        "words — write the date or range it means")

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

    # -- text for other people: em dashes and the AI tells -------------------
    # Her one absolute rule is no em dashes, and four of the six failed draft
    # tests on 27 Sep were em dashes. textcheck.py is the same check the
    # model calls run on their output; this catches what was written or
    # edited some other way.
    try:
        import textcheck
        for label, text in _texts_for_others(textcheck):
            for prob in textcheck.problems(text):
                problems.append(f"{label}: {prob}")
    except Exception as exc:                          # noqa: BLE001
        problems.append(f"textcheck.py could not run ({exc})")

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

    # -- the security alarm (sentinel.py) -----------------------------------
    # Every session that builds the page sees it, not only her.
    try:
        import sentinel
        for c in sentinel.changes():
            problems.append(f"SECURITY: {c['label']} changed ({c['what']})"
                            + (f" [{c['commit']}]" if c["commit"] else "")
                            + " — she has not confirmed it was hers")
    except Exception as exc:                          # noqa: BLE001
        problems.append(f"SECURITY: the alarm could not run ({exc})")

    return problems


if __name__ == "__main__":
    probs = check()
    for p in probs:
        print(f"  ⚠ {p}")
    if not probs:
        print("check.py: the brain is sound")
    sys.exit(1 if probs else 0)

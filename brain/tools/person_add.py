#!/usr/bin/env python3
"""Add someone you just met, with the follow-ups already set.

    python3 brain/tools/person_add.py "Aymeric Penven" \
        --role "Site Director" --company "Creative Destruction Lab" \
        --how "met at the CDL Paris evening" --where Paris --ladder

    python3 brain/tools/person_add.py "Aymeric Penven" --update --linkedin ...

The gap this closes is timing. A new contact is warm for about three days, and
that is exactly when you are walking out of a room rather than sitting at a
keyboard. So the writing is a script — a voice note becomes a real entry with
the follow-ups already dated, and nothing depends on remembering later.

`--ladder` is the whole point: three parked promises at +3 days, +3 weeks and
+3 months. They sit silent until their date and then surface in the daily
chases like anything else, which is the rhythm a new professional contact
needs and a friendship does not.

Writing is deterministic on purpose, the same reason `people_update.py` is: a
script cannot drift from the file format, so the only judgement involved is
what was actually said.
"""

import argparse
import os
import re
import sys
from datetime import date, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from import_chats import PEOPLE                          # noqa: E402
from people_update import normalise                      # noqa: E402
from linkedin_import import person_block, tidy_url       # noqa: E402

# Field order matches how an entry reads on the page: who they are to you
# first, then the professional block, then the machinery.
FIELDS = ("Circle", "Every", "Ball", "Last", "Role", "Company", "LinkedIn",
          "How", "Met", "Where", "Pronouns", "Reach", "Tags", "Why")

LADDER = (("Follow up on meeting {who}", 3),
          ("Check back in with {who}", 21),
          ("Keep {who} warm — something useful, not a ping", 90))


def aliases(path=None):
    """{canonical name: [every name they appear under]}, from any people file.

    `import_chats.people_aliases` only ever reads the real one, and a writer
    that checks a different file from the one it writes would happily add a
    second Maman.
    """
    path = path or PEOPLE
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read()
    except FileNotFoundError:
        return {}
    out, cur = {}, None
    for line in text.split("\n"):
        h = re.match(r"^##\s+(.*)$", line.strip())
        if h:
            cur = re.sub(r"[*`]", "", h.group(1)).strip()
            out[cur] = [cur]
            continue
        if cur is None:
            continue
        m = re.match(r"^\s*-\s+\*\*Also:\*\*\s*(.*)$", line, re.I)
        if m:
            out[cur] += [a.strip() for a in m.group(1).split(",") if a.strip()]
    return out


def existing(name, path=None):
    """The canonical name this already matches, through aliases, or ""."""
    n = normalise(name)
    for canonical, names in aliases(path).items():
        for alias in names:
            if normalise(alias) == n:
                return canonical
    return ""


def ladder_lines(who, when=None):
    """The three parked promises. Each is silent until its date."""
    when = when or date.today()
    out = []
    for text, days in LADDER:
        due = when + timedelta(days=days)
        out.append(f"- [ ] {text.format(who=who)} (waiting until {due.isoformat()})")
    return out


def add(name, values, ladder=False, met_on=None, path=None):
    """Append a new person. Returns the lines written."""
    path = path or PEOPLE
    with open(path, encoding="utf-8") as f:
        text = f.read()

    block = [f"## {name}", ""]
    for field in FIELDS:
        v = (values.get(field.lower()) or "").strip()
        if v:
            block.append(f"- **{field}:** {v}")
    if ladder:
        block.append("")
        block += ladder_lines(name, met_on)
    block.append("")

    body = text.rstrip("\n") + "\n\n" + "\n".join(block)
    with open(path, "w", encoding="utf-8") as f:
        f.write(body.rstrip("\n") + "\n")
    return block


def update(name, values, ladder=False, met_on=None, path=None):
    """Fill blank fields on someone already there, and optionally add the
    ladder. Never overwrites a value — same rule as the LinkedIn import."""
    path = path or PEOPLE
    with open(path, encoding="utf-8") as f:
        lines = f.read().split("\n")
    span = person_block(lines, name)
    if not span:
        return []
    start, end = span

    have, last_field = set(), start
    for j in range(start + 1, end):
        m = re.match(r"^\s*-\s+\*\*([A-Za-z ]+):\*\*\s*(.*)$", lines[j])
        if m:
            last_field = j
            if m.group(2).strip():
                have.add(m.group(1).strip().lower())

    written, insert = [], last_field + 1
    for field in FIELDS:
        v = (values.get(field.lower()) or "").strip()
        if not v or field.lower() in have:
            continue
        lines.insert(insert, f"- **{field}:** {v}")
        insert += 1
        written.append(f"- **{field}:** {v}")

    if ladder:
        # Only if they have no open ladder already, so a re-run does not stack
        # three more promises on someone who is already being followed up.
        block = "\n".join(lines[start:end + len(written)])
        if "Follow up on meeting" not in block:
            for ln in reversed(ladder_lines(name, met_on)):
                lines.insert(insert, ln)
                written.append(ln)

    if written:
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
    return written


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("name")
    for f in ("role", "company", "linkedin", "how", "met", "where",
              "pronouns", "reach", "tags", "why", "every"):
        ap.add_argument("--" + f, default="")
    ap.add_argument("--circle", default="Network",
                    help="which group they belong to (default Network — say so "
                         "in the Outcome so she can change it in one tap)")
    ap.add_argument("--ladder", action="store_true",
                    help="add follow-ups at +3 days, +3 weeks, +3 months")
    ap.add_argument("--on", default="", help="the day you met (YYYY-MM-DD, default today)")
    ap.add_argument("--update", action="store_true",
                    help="fill blanks on someone already on the list")
    ap.add_argument("--people", default=None, help="a different people.md (for testing)")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    met_on = None
    if a.on:
        m = re.match(r"(\d{4})-(\d{2})-(\d{2})$", a.on.strip())
        if not m:
            sys.exit(f"--on wants YYYY-MM-DD, got {a.on!r}")
        met_on = date(*map(int, m.groups()))

    values = {
        "circle": a.circle, "every": a.every, "role": a.role,
        "company": a.company, "linkedin": tidy_url(a.linkedin) or a.linkedin,
        "how": a.how, "met": a.met, "where": a.where, "pronouns": a.pronouns,
        "reach": a.reach, "tags": a.tags, "why": a.why,
        "ball": "Nobody",
        "last": (met_on or date.today()).isoformat(),
    }

    already = existing(a.name, a.people)
    if already and not a.update:
        sys.exit(f"{already} is already on your people list. "
                 f"Re-run with --update to fill in what's missing, "
                 f"or use a different name.")
    if not already and a.update:
        sys.exit(f"{a.name} is not on your people list yet — drop --update to add them.")

    if a.dry_run:
        who = already or a.name
        print(f"would {'update' if already else 'add'} {who}:")
        for field in FIELDS:
            v = (values.get(field.lower()) or "").strip()
            if v:
                print(f"  - **{field}:** {v}")
        if a.ladder:
            for ln in ladder_lines(who, met_on):
                print("  " + ln)
        return

    if already:
        written = update(already, values, a.ladder, met_on, a.people)
        if not written:
            print(f"{already} already had everything — nothing changed.")
            return
        print(f"Updated {already}:")
    else:
        written = add(a.name, values, a.ladder, met_on, a.people)
        print(f"Added {a.name}:")
    for ln in written:
        if ln.strip():
            print("  " + ln)
    print("\nRebuild with: python3 brain/tools/build.py")


if __name__ == "__main__":
    main()

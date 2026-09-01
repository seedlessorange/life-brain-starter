#!/usr/bin/env python3
"""Backfill "last spoke" dates from WhatsApp chat exports.

    python3 brain/tools/import_chats.py ~/Downloads        # show what it found
    python3 brain/tools/import_chats.py ~/Downloads --write # update people.md

WhatsApp has no API that can read your personal chats. The only legitimate
route is its own per-chat export, and this reads those.

It reads DATES ONLY. It never stores, prints or passes on a single word of
what anyone said — it scans each line for a leading timestamp, keeps the
latest one, and throws the rest away. That is deliberate: this runs as a plain
script rather than through Claude precisely so your conversations never enter
a model's context.

To make an export: open a chat in WhatsApp, tap the contact name, scroll to
Export chat, choose Without media, and save it somewhere this can see.
"""

import argparse
import os
import re
import sys
from datetime import date, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
BRAIN = os.path.dirname(HERE)
PEOPLE = os.path.join(BRAIN, "people.md")

# The two shapes WhatsApp writes, depending on phone and locale:
#   Android: "11/08/2026, 14:32 - Name: ..."
#   iPhone:  "[11/08/2026, 14:32:07] Name: ..."
STAMP = re.compile(r"^\[?\s*(\d{1,2})[/.](\d{1,2})[/.](\d{2,4})")

# "WhatsApp Chat with Ellis.txt" / "WhatsApp Chat - Ellis.txt" / "_chat.txt"
NAME_FROM_FILE = re.compile(r"whatsapp chat (?:with|-)\s*(.+)", re.I)


def parse_stamp(line, dayfirst=True):
    m = STAMP.match(line)
    if not m:
        return None
    a, b, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
    if y < 100:
        y += 2000
    day, month = (a, b) if dayfirst else (b, a)
    # A file written in US order will fail day-first once past the 12th; the
    # caller retries the other way round rather than guessing per line.
    try:
        return date(y, month, day)
    except ValueError:
        return None


def last_date(path):
    """The most recent message date in an export. Content is never kept."""
    for dayfirst in (True, False):
        latest, seen = None, 0
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                for line in f:
                    d = parse_stamp(line, dayfirst)
                    if d:
                        seen += 1
                        if latest is None or d > latest:
                            latest = d
        except OSError:
            return None, 0
        # A date in the future means the day/month order was wrong.
        if latest and latest <= date.today():
            return latest, seen
    return None, 0


def person_from(path):
    stem = os.path.splitext(os.path.basename(path))[0]
    m = NAME_FROM_FILE.search(stem)
    if m:
        return m.group(1).strip()
    if stem == "_chat":                     # iPhone exports name the folder
        return os.path.basename(os.path.dirname(path)).replace("WhatsApp Chat with ", "").strip()
    return None


def find_exports(root):
    out = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if not d.startswith(".")][:200]
        for fn in filenames:
            if not fn.lower().endswith(".txt"):
                continue
            path = os.path.join(dirpath, fn)
            if person_from(path):
                out.append(path)
    return sorted(out)


def known_people():
    try:
        with open(PEOPLE, encoding="utf-8") as f:
            text = f.read()
    except FileNotFoundError:
        return []
    return [re.sub(r"[*`]", "", m).strip()
            for m in re.findall(r"^##\s+(.*)$", text, re.M)]


def people_aliases():
    """{canonical name: [every name they might appear under]}.

    Chat apps show whatever she saved the contact as — "Mom" against a
    people.md entry called "Mum", "Lennox" with an emoji stuck on the end.
    An `Also:` line closes that gap, and without it the automatic sync
    silently fails to match the person who matters most.
    """
    try:
        with open(PEOPLE, encoding="utf-8") as f:
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


def set_last(name, when):
    """Write `- **Last:** date` for one person, only if it moves it forward."""
    with open(PEOPLE, encoding="utf-8") as f:
        lines = f.read().split("\n")
    start = None
    for i, line in enumerate(lines):
        m = re.match(r"^##\s+(.*)$", line.strip())
        if m and re.sub(r"[*`]", "", m.group(1)).strip().lower() == name.lower():
            start = i
            break
    if start is None:
        return False
    end = len(lines)
    for j in range(start + 1, len(lines)):
        if re.match(r"^##\s+", lines[j].strip()):
            end = j
            break
    for j in range(start + 1, end):
        m = re.match(r"^\s*-\s+\*\*Last:\*\*\s*(.*)$", lines[j], re.I)
        if m:
            cur = re.search(r"\d{4}-\d{2}-\d{2}", m.group(1))
            if cur and cur.group() >= when:
                return False        # never move a contact date backwards
            lines[j] = f"- **Last:** {when}"
            break
    else:
        insert = start + 1
        for j in range(start + 1, end):
            if re.match(r"^\s*-\s+\*\*[A-Za-z ]+:\*\*", lines[j]):
                insert = j + 1
        lines.insert(insert, f"- **Last:** {when}")
    with open(PEOPLE, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return True


def set_ball_me(name):
    """Flip one person's Ball to Me. The Beeper sync calls this when THEIR
    message is the newest in a personal-circle chat and has sat unanswered
    past the reply fuse — her explicit ask (19 Aug 2026): a reply owed to a
    close friend should surface in days, not at the circle's rhythm."""
    with open(PEOPLE, encoding="utf-8") as f:
        lines = f.read().split("\n")
    start = None
    for i, line in enumerate(lines):
        m = re.match(r"^##\s+(.*)$", line.strip())
        if m and re.sub(r"[*`]", "", m.group(1)).strip().lower() == name.lower():
            start = i
            break
    if start is None:
        return False
    end = len(lines)
    for j in range(start + 1, len(lines)):
        if re.match(r"^##\s+", lines[j].strip()):
            end = j
            break
    for j in range(start + 1, end):
        if re.match(r"^\s*-\s+\*\*Ball:\*\*", lines[j], re.I):
            if re.search(r"\bme\b", lines[j], re.I):
                return False               # already hers to answer
            lines[j] = "- **Ball:** Me"
            break
    else:
        insert = start + 1
        for j in range(start + 1, end):
            if re.match(r"^\s*-\s+\*\*[A-Za-z ]+:\*\*", lines[j]):
                insert = j + 1
        lines.insert(insert, "- **Ball:** Me")
    with open(PEOPLE, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return True


def set_ball_nobody(name):
    """Flip one person's `- **Ball:** Me` to Nobody. The Beeper sync calls this
    when your own message is the newest in their chat — a reply you already
    sent is not a reply you owe. It only ever clears; it never sets."""
    with open(PEOPLE, encoding="utf-8") as f:
        lines = f.read().split("\n")
    start = None
    for i, line in enumerate(lines):
        m = re.match(r"^##\s+(.*)$", line.strip())
        if m and re.sub(r"[*`]", "", m.group(1)).strip().lower() == name.lower():
            start = i
            break
    if start is None:
        return False
    for j in range(start + 1, len(lines)):
        if re.match(r"^##\s+", lines[j].strip()):
            return False
        if re.match(r"^\s*-\s+\*\*Ball:\*\*", lines[j], re.I):
            lines[j] = "- **Ball:** Nobody"
            with open(PEOPLE, "w", encoding="utf-8") as f:
                f.write("\n".join(lines))
            return True
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("folder", nargs="?", default=os.path.expanduser("~/Downloads"))
    ap.add_argument("--write", action="store_true",
                    help="actually update people.md (otherwise just report)")
    args = ap.parse_args()

    root = os.path.expanduser(args.folder)
    if not os.path.isdir(root):
        sys.exit(f"No such folder: {root}")

    exports = find_exports(root)
    if not exports:
        print(f"No WhatsApp exports found under {root}.\n"
              "In WhatsApp: open a chat, tap the name, Export chat, Without media.")
        return

    known = {k.lower(): k for k in known_people()}
    updated, unknown = 0, []
    print(f"Found {len(exports)} export(s) under {root}:\n")
    for path in exports:
        who = person_from(path)
        when, seen = last_date(path)
        if not when:
            print(f"  {who:<22} could not read any dates")
            continue
        age = (date.today() - when).days
        mark = ""
        if who.lower() in known:
            if args.write and set_last(known[who.lower()], when.isoformat()):
                updated += 1
                mark = "  -> updated"
            elif not args.write:
                mark = "  -> would update"
        else:
            unknown.append(who)
            mark = "  (not on your people list)"
        print(f"  {who:<22} last message {when} ({age} days ago, "
              f"{seen} messages){mark}")

    if unknown:
        print("\nNot on your list yet: " + ", ".join(sorted(set(unknown))))
        print("Add them on the page (+ button, Add, Person) and run this again.")
    if args.write:
        print(f"\nUpdated {updated} person(s). Rebuild with: python3 brain/tools/build.py")
    else:
        print("\nNothing was changed. Re-run with --write to apply.")


if __name__ == "__main__":
    main()

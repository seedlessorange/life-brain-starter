#!/usr/bin/env python3
"""Set "last spoke" dates for several people at once.

    python3 brain/tools/people_update.py "Mum=2026-08-11" "Ellis=today"

Written for the screenshot flow: Claude reads an inbox screenshot, works out
who appeared and how recently, and calls this to do the writing. The writing
is deterministic on purpose — a script that cannot drift from the file format,
so the only judgement involved is reading the picture.

Never moves a date backwards, so re-running on an older screenshot is safe.
Names are matched case-insensitively, and loosely enough that "Mum ❤️" in a
phone's contact list still finds "Mum".
"""

import argparse
import os
import re
import sys
from datetime import date, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from import_chats import PEOPLE, known_people, set_last  # noqa: E402


def parse_when(s):
    s = (s or "").strip().lower()
    if s in ("today", "now"):
        return date.today()
    if s == "yesterday":
        return date.today() - timedelta(days=1)
    m = re.match(r"(\d+)\s*d(?:ays?)?\s*ago$", s)
    if m:
        return date.today() - timedelta(days=int(m.group(1)))
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return None
    return None


def normalise(s):
    """Strip emoji, punctuation and spacing so a contact-list name matches the
    plain one in people.md."""
    return re.sub(r"[^a-z0-9]+", "", (s or "").lower())


def match(name, known):
    """`known` is a list of names, or a {canonical: [aliases]} map."""
    n = normalise(name)
    if not n:
        return None
    by_norm = {}
    if isinstance(known, dict):
        for canonical, names in known.items():
            for alias in names:
                by_norm[normalise(alias)] = canonical
    else:
        by_norm = {normalise(k): k for k in known}
    if n in by_norm:
        return by_norm[n]
    # A contact saved as "Dad Mobile" or "Daddy" should still find "Dad".
    # The floor is 3, not 4: it has to clear two-letter noise without losing
    # Mum and Dad, which are the two names that matter most here.
    for k_norm, k in by_norm.items():
        if min(len(k_norm), len(n)) >= 3 and (n.startswith(k_norm) or k_norm.startswith(n)):
            return k
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pairs", nargs="+", metavar="NAME=WHEN",
                    help='e.g. "Mum=today" "Ellis=2026-08-09" "Ana=3 days ago"')
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    known = known_people()
    if not known:
        sys.exit(f"No people found in {PEOPLE}")

    changed, skipped, unknown = [], [], []
    for pair in args.pairs:
        if "=" not in pair:
            unknown.append(f"{pair} (expected NAME=WHEN)")
            continue
        raw_name, raw_when = pair.split("=", 1)
        who = match(raw_name, known)
        when = parse_when(raw_when)
        if not who:
            unknown.append(raw_name.strip())
            continue
        if not when:
            unknown.append(f"{raw_name.strip()} (could not read the date '{raw_when}')")
            continue
        if when > date.today():
            skipped.append(f"{who}: {when} is in the future")
            continue
        if args.dry_run:
            changed.append(f"{who} -> {when} (dry run)")
        elif set_last(who, when.isoformat()):
            changed.append(f"{who} -> {when}")
        else:
            skipped.append(f"{who}: already had that date or a newer one")

    for line in changed:
        print("updated  " + line)
    for line in skipped:
        print("skipped  " + line)
    if unknown:
        print("\nNot on your people list: " + ", ".join(unknown))
        print("Add them on the page (+ button, Add, Person), then run this again.")
    print(f"\n{len(changed)} updated, {len(skipped)} unchanged, {len(unknown)} unmatched.")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Find the networking you already did and then dropped.

    python3 brain/tools/linkedin_invites.py ~/Downloads

An invitation is the expensive half of networking — you found the person,
decided they were worth knowing, and reached out. What usually goes missing is
the cheap half: the message three days later. This reads the invitations out of
LinkedIn's own export (the same zip `linkedin_import.py` uses) and reports the
three places a connection dies:

  - people who accepted and were never spoken to — the warm ones going cold,
  - invitations sitting in your inbox unanswered,
  - invitations you sent that nobody accepted.

It reports and never writes. Turning a name here into a tracked person or a
follow-up task is a decision, and decisions belong to you — the same rule the
Beeper sync follows for unmatched chats.

Whether someone has actually been spoken to is read from people.md, and from
Beeper's chat list when Beeper Desktop happens to be open. As everywhere else,
that means chat titles and dates; the export's messages.csv is never opened.
"""

import argparse
import csv
import io
import os
import re
import sys
import zipfile
from datetime import date, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from import_chats import PEOPLE                          # noqa: E402
from people_update import normalise                      # noqa: E402
from linkedin_import import find_exports, read_rows, build_index  # noqa: E402

# "8/18/26, 1:07 PM" — the export writes US order regardless of your locale.
SENT_AT = re.compile(r"(\d{1,2})/(\d{1,2})/(\d{2,4})")


def read_invitations(text):
    rows = []
    for r in csv.DictReader(io.StringIO(text)):
        rows.append({
            "from": (r.get("From") or "").strip(),
            "to": (r.get("To") or "").strip(),
            "sent": parse_sent(r.get("Sent At")),
            # Kept because SHE wrote it (or it was written to her as an
            # introduction, which is context she never got to act on). It is
            # printed so a follow-up can pick up where the note left off.
            "message": " ".join((r.get("Message") or "").split()),
            "direction": (r.get("Direction") or "").strip().upper(),
        })
    return rows


def parse_sent(s):
    m = SENT_AT.search(s or "")
    if not m:
        return None
    month, day, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
    if year < 100:
        year += 2000
    try:
        return date(year, month, day)
    except ValueError:
        return None


def find_invitations(root):
    """Every Invitations.csv under `root`, loose or inside an export zip."""
    out = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if not d.startswith(".")][:200]
        for fn in sorted(filenames):
            path = os.path.join(dirpath, fn)
            low = fn.lower()
            if low.endswith(".csv") and "invitation" in low:
                try:
                    with open(path, encoding="utf-8-sig", errors="replace") as f:
                        out.append(f.read())
                except OSError:
                    pass
            elif low.endswith(".zip"):
                try:
                    with zipfile.ZipFile(path) as z:
                        for member in z.namelist():
                            if "invitation" in member.lower() and member.lower().endswith(".csv"):
                                out.append(z.read(member).decode("utf-8-sig", errors="replace"))
                except (zipfile.BadZipFile, OSError, KeyError):
                    pass
    return out


def spoken_to():
    """Everyone there is evidence of an actual conversation with.

    people.md is the record you keep; Beeper's chat list is the one that keeps
    itself. Beeper is optional on purpose — it only answers while the desktop
    app is open, and a networking report should not fail because it is shut.
    """
    names = set(build_index().keys())
    try:
        from beeper import keychain_get, fetch_chats, chat_name
        token = keychain_get()
        if token:
            for c in fetch_chats(token) or []:
                n = normalise(chat_name(c) or "")
                if n:
                    names.add(n)
    except Exception:
        pass                    # Beeper shut, not logged in, not installed.
    return names


def ago(d, today=None):
    n = ((today or date.today()) - d).days
    if n <= 0:
        return "today"
    if n == 1:
        return "yesterday"
    if n < 60:
        return f"{n} days ago"
    return f"{n // 30} months ago"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("folder", nargs="?", default=os.path.expanduser("~/Downloads"))
    ap.add_argument("--top", type=int, default=20, help="how many to print in each list")
    args = ap.parse_args()

    root = os.path.expanduser(args.folder)
    if not os.path.isdir(root):
        sys.exit(f"No such folder: {root}")

    texts = find_invitations(root)
    if not texts:
        sys.exit(
            f"No LinkedIn invitations export found under {root}.\n"
            "It comes in the same zip as your connections: Settings > Data\n"
            "privacy > Get a copy of your data. Save it to Downloads and re-run.")

    invites = []
    for t in texts:
        invites += read_invitations(t)

    connections, seen = set(), set()
    for label, text in find_exports(root):
        for r in read_rows(text):
            connections.add(normalise(r["name"]))
            seen.add(label)
    known = spoken_to()
    today = date.today()

    outgoing = [i for i in invites if i["direction"] == "OUTGOING"]
    incoming = [i for i in invites if i["direction"] == "INCOMING"]

    # Accepted means they are in your connections now. Without the connections
    # file there is nothing to check against, so say so rather than guess.
    if not connections:
        print("No Connections.csv alongside the invitations — "
              "acceptance cannot be worked out, so only the counts below are real.\n")

    accepted = [i for i in outgoing if normalise(i["to"]) in connections]
    pending_out = [i for i in outgoing if normalise(i["to"]) not in connections]
    cold = [i for i in accepted if normalise(i["to"]) not in known]
    awaiting = [i for i in incoming if normalise(i["from"]) not in connections]

    span = [i["sent"] for i in invites if i["sent"]]
    when = (f" between {min(span):%b %Y} and {max(span):%b %Y}" if span else "")
    print(f"{len(invites)} invitations{when}: "
          f"{len(outgoing)} you sent, {len(incoming)} you received.\n")

    print(f"ACCEPTED AND NEVER SPOKEN TO — {len(cold)} people")
    print("  They said yes and nothing followed. This is the whole leak.")
    for i in sorted(cold, key=lambda x: x["sent"] or date.min, reverse=True)[:args.top]:
        stamp = ago(i["sent"], today) if i["sent"] else "date unknown"
        print(f"  {i['to'][:32]:<34}accepted {stamp}")
        if i["message"]:
            print(f"      you wrote: {i['message'][:70]}")
    if len(cold) > args.top:
        print(f"  ... and {len(cold) - args.top} more")

    print(f"\nWAITING ON YOU — {len(awaiting)} invitations you have not answered")
    for i in sorted(awaiting, key=lambda x: x["sent"] or date.min, reverse=True)[:args.top]:
        stamp = ago(i["sent"], today) if i["sent"] else "date unknown"
        print(f"  {i['from'][:32]:<34}sent {stamp}")
        if i["message"]:
            print(f"      they wrote: {i['message'][:70]}")
    if len(awaiting) > args.top:
        print(f"  ... and {len(awaiting) - args.top} more")

    print(f"\nSENT, NOT ACCEPTED — {len(pending_out)}")
    for i in sorted(pending_out, key=lambda x: x["sent"] or date.min, reverse=True)[:args.top]:
        stamp = ago(i["sent"], today) if i["sent"] else "date unknown"
        print(f"  {i['to'][:32]:<34}sent {stamp}")

    if outgoing:
        rate = round(100 * len(accepted) / len(outgoing))
        talked = len(accepted) - len(cold)
        print(f"\n{len(accepted)} of {len(outgoing)} invitations were accepted ({rate}%), "
              f"and {talked} became a conversation.")
    print("Nothing was written. Ask Claude to turn any of these into "
          "tracked people or follow-up tasks.")


if __name__ == "__main__":
    main()

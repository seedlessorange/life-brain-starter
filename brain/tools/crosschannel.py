#!/usr/bin/env python3
"""Who you actually talk to, against who LinkedIn thinks you know.

    python3 brain/tools/crosschannel.py ~/Downloads

LinkedIn holds one channel and treats all 1,400 connections as equally
connected. Beeper holds six and knows which of them you have said a word to
this year. Neither is the truth on its own, and putting them together answers
the question that decides every piece of outreach: is this a stranger with a
job title, or someone I already know well enough to just ask?

Four groups come out of the overlap:

  WARM ALREADY   a connection you message often — never cold-pitch them, ask.
  THE REAL QUEUE a connection with a useful role and no conversation anywhere.
  UNTRACKED      someone you message often who is on no list at all.
  QUIET FRIENDS  someone on your people list who has gone silent everywhere.

Beeper must be open for the chat half; without it this falls back to people.md
alone and says so, because a report that quietly halves its evidence is worse
than one that refuses.

Titles and dates only, on both sides. No message content is read here or
anywhere else in this brain.
"""

import argparse
import csv
import io
import os
import re
import sys
import zipfile
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import model as M                                        # noqa: E402
from people_update import normalise                      # noqa: E402
from linkedin_import import find_exports, read_rows, build_index, resolve  # noqa: E402

# Roles worth a deliberate approach — the people who can hire, fund, refer or
# partner. Deliberately blunt: it ranks the queue, it does not judge anyone.
SENIOR = re.compile(
    r"\b(founder|co-?founder|ceo|cto|coo|cfo|chief|president|partner|"
    r"managing director|director|head of|vp|vice president|principal|"
    r"investor|recruit\w*|talent|hiring)\b", re.I)

CHATTY_DAYS = 90          # said something within this = a live conversation
QUIET_DAYS = 365          # nothing anywhere for this long = gone cold


def own_names(root):
    """Every name she appears under herself, so her own accounts stay out.

    `config.json`'s owner is a possessive label for the page ("the owner's"),
    not a name to match on, and her own Instagram handle is otherwise a chat
    she talks to constantly. The export's Profile.csv carries the real one.
    """
    out = set()
    cfg = normalise((M.load_config() or {}).get("owner") or "")
    if cfg:
        out.add(cfg)
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if not d.startswith(".")][:200]
        for fn in filenames:
            if not fn.lower().endswith(".zip"):
                continue
            try:
                with zipfile.ZipFile(os.path.join(dirpath, fn)) as z:
                    for member in z.namelist():
                        if not member.lower().endswith("profile.csv"):
                            continue
                        raw = z.read(member).decode("utf-8-sig", errors="replace")
                        for row in csv.DictReader(io.StringIO(raw)):
                            first = (row.get("First Name") or "").strip()
                            last = (row.get("Last Name") or "").strip()
                            for nm in (f"{first} {last}", first):
                                if normalise(nm):
                                    out.add(normalise(nm))
            except (zipfile.BadZipFile, OSError, KeyError):
                pass
    return {x for x in out if x}


def beeper_chats(mine=()):
    """{normalised chat title: days since it last had activity}, or None when
    Beeper cannot answer. None and {} mean different things, so they stay
    different values: one is "not asked", the other is "asked, nothing there".

    Direct chats only. A message in a group of twelve is not a conversation
    with each of them, and a report about who you actually talk to is exactly
    where counting it as one would do the most damage.
    """
    try:
        from beeper import keychain_get, fetch_chats, chat_name, chat_when, load_ignored
    except Exception:
        return None
    try:
        token = keychain_get()
        if not token:
            return None
        chats = fetch_chats(token, include_groups=False)
    except Exception:
        return None
    if not chats:
        return None
    # Chats she has already dismissed on the People page stay dismissed —
    # being asked twice about the same plumber is how a tool gets ignored.
    ignored = {normalise(x) for x in load_ignored()} | set(mine)
    today, out = date.today(), {}
    for c in chats:
        n = normalise(chat_name(c) or "")
        if not n or n in ignored:
            continue
        when = chat_when(c)
        if not when:
            continue
        days = (today - when).days
        out[n] = min(days, out.get(n, days))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("folder", nargs="?", default=os.path.expanduser("~/Downloads"))
    ap.add_argument("--top", type=int, default=15)
    a = ap.parse_args()

    root = os.path.expanduser(a.folder)
    conns = []
    if os.path.isdir(root):
        for label, text in find_exports(root):
            conns += read_rows(text)
    by_conn = {}
    for r in conns:
        by_conn.setdefault(normalise(r["name"]), r)

    people = M.load_people()
    by_name = {p["name"].lower(): p for p in people}

    # Which connection is which person, through the same matcher the import
    # uses — so a full legal name reaches the entry filed under a family
    # nickname instead of being reported as a stranger messaged daily.
    matched, _amb, _unk = resolve(list(by_conn.values()), build_index())
    by_person = {}
    for canonical, r in matched:
        p = by_name.get(canonical.lower())
        if p:
            by_person[normalise(r["name"])] = p
    # Everyone on the list, under every name they go by, for the chat half.
    for p in people:
        also = p.get("also") or ""
        if not isinstance(also, str):
            also = ", ".join(also)
        for nm in [p["name"]] + [x.strip() for x in also.split(",") if x.strip()]:
            by_person.setdefault(normalise(nm), p)

    chats = beeper_chats(own_names(root))
    if chats is None:
        print("Beeper did not answer — open Beeper Desktop for the chat half of "
              "this. Falling back to the dates in people.md alone.\n")
        chats = {}

    def days_since(key, person):
        """The freshest evidence of a conversation, from either side."""
        best = chats.get(key)
        if person is not None and person.get("days_since") is not None:
            d = person["days_since"]
            best = d if best is None else min(best, d)
        return best

    warm, queue, untracked, quiet = [], [], [], []

    for key, r in by_conn.items():
        person = by_person.get(key)
        d = days_since(key, person)
        if d is not None and d <= CHATTY_DAYS:
            warm.append((d, r, person))
        elif d is None or d > QUIET_DAYS:
            if SENIOR.search(r.get("role") or ""):
                queue.append((d, r, person))

    for key, d in chats.items():
        if d <= CHATTY_DAYS and key not in by_person and key not in by_conn:
            untracked.append((d, key))

    for p in people:
        d = p.get("days_since")
        if d is not None and d > QUIET_DAYS and not p.get("oneoff"):
            quiet.append((d, p))

    if not by_conn:
        print(f"No LinkedIn connections export under {root} — "
              "the two professional groups below need one.\n")

    print(f"WARM ALREADY — {len(warm)}")
    print("  LinkedIn connections you have actually spoken to in the last "
          f"{CHATTY_DAYS} days. Ask them; do not pitch them.")
    for d, r, person in sorted(warm, key=lambda x: x[0])[:a.top]:
        rc = " at ".join(x for x in (r.get("role"), r.get("company")) if x)
        circle = f"  [{person['circle']}]" if person else "  [not on your list]"
        print(f"  {r['name'][:26]:<28}{rc[:40]:<42}{d}d{circle}")
    if len(warm) > a.top:
        print(f"  ... and {len(warm) - a.top} more")

    print(f"\nTHE REAL QUEUE — {len(queue)}")
    print("  Useful role, no conversation anywhere. This is where outreach "
          "belongs.")
    for d, r, person in sorted(queue, key=lambda x: (x[0] is not None, x[0] or 0))[:a.top]:
        rc = " at ".join(x for x in (r.get("role"), r.get("company")) if x)
        when = "never" if d is None else f"{d // 30}mo"
        print(f"  {r['name'][:26]:<28}{rc[:40]:<42}{when}")
    if len(queue) > a.top:
        print(f"  ... and {len(queue) - a.top} more")

    print(f"\nUNTRACKED BUT CLOSE — {len(untracked)}")
    print("  You message them; no list has them. Worth a circle.")
    for d, key in sorted(untracked, key=lambda x: x[0])[:a.top]:
        print(f"  {key[:36]:<38}{d}d ago")
    if len(untracked) > a.top:
        print(f"  ... and {len(untracked) - a.top} more")

    print(f"\nQUIET FOR OVER A YEAR — {len(quiet)}")
    for d, p in sorted(quiet, key=lambda x: -x[0])[:a.top]:
        print(f"  {p['name'][:26]:<28}{p.get('circle',''):<18}{d // 30} months")
    if len(quiet) > a.top:
        print(f"  ... and {len(quiet) - a.top} more")

    print("\nNothing was written.")


if __name__ == "__main__":
    main()

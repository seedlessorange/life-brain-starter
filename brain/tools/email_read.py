#!/usr/bin/env python3
"""Read email headers — never bodies — so the people file stays honest.

    python3 brain/tools/email_read.py on       # consent: turn reading on
    python3 brain/tools/email_read.py check    # look now, report, write nothing
    python3 brain/tools/email_read.py check --write   # also move Last dates on
    python3 brain/tools/email_read.py off

It fetches four header fields (From, To, Cc, Date) over IMAP with BODY.PEEK,
so nothing gets marked read. It never fetches a message body and it never
asks for a subject line. What it learns is who wrote, who was written to, and
when — the three facts the brain actually plans around.

Why headers only. The moment the brain reads bodies, anyone who can email her
can put text in front of Claude. Headers answer the question this brain asks
("who is waiting on me") with almost nothing an attacker can steer.

Reading is off until she turns it on: no `email.read.on` in config.json, no
read path. It uses the app password already in the Keychain from setting up
sending, so turning it on adds no new secret. Nothing here can send.
"""

import argparse
import email.utils
import imaplib
import json
import os
import re
import sys
from datetime import date, datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
BRAIN = os.path.dirname(HERE)
STATE = os.path.join(BRAIN, ".email-read.json")

import email_send as ES          # noqa: E402  (accounts + the Keychain lookup)
from import_chats import people_aliases, set_last  # noqa: E402
from people_update import match  # noqa: E402

# host, port. All implicit-SSL on 993; there is no plaintext path here.
IMAP_HOSTS = {
    "gmail": ("imap.gmail.com", 993),
    "yahoo": ("imap.mail.yahoo.com", 993),
    "icloud": ("imap.mail.me.com", 993),
    "outlook": ("outlook.office365.com", 993),
}

# Fallbacks for the Sent folder, tried in order when the server does not
# advertise \Sent. Providers each name it differently and none of them is wrong.
SENT_GUESSES = ['"[Gmail]/Sent Mail"', '"Sent Items"', '"Sent Messages"', "Sent",
                '"INBOX.Sent"']

HEADERS = "(BODY.PEEK[HEADER.FIELDS (FROM TO CC DATE)])"


# --------------------------------------------------------------------------
# consent — the whole feature hangs off this one flag

def reading_on(cfg=None):
    cfg = cfg if cfg is not None else ES.load_cfg()
    return bool(((cfg.get("email") or {}).get("read") or {}).get("on"))


def set_reading(on, days=14):
    cfg = ES.load_cfg()
    em = cfg.setdefault("email", {"accounts": []})
    if on:
        em["read"] = {"on": True, "days": int(days)}
    else:
        em.pop("read", None)
        # Turning it off should leave the file as it found it, not a husk of
        # a mail block that makes the page think something is configured.
        if not em.get("accounts") and not em.get("default"):
            cfg.pop("email", None)
    ES.save_cfg(cfg)
    return on


def read_days(cfg=None):
    cfg = cfg if cfg is not None else ES.load_cfg()
    return int((((cfg.get("email") or {}).get("read") or {}).get("days")) or 14)


# --------------------------------------------------------------------------
# the read itself

def _imap_for(entry):
    if entry.get("imap_host"):
        return entry["imap_host"], int(entry.get("imap_port", 993))
    prov = entry.get("provider", "")
    if prov not in IMAP_HOSTS:
        raise ValueError(f"no IMAP host known for {prov!r}")
    return IMAP_HOSTS[prov]


def _connect(address=None):
    address = address or ES.default_account()
    entry = next((a for a in ES.accounts() if a["address"] == address), None)
    if not entry:
        raise ValueError("that account isn't set up — connect it for sending first")
    pw = ES.kc_get(address)
    if not pw:
        raise ValueError("no app password in the Keychain for " + address)
    host, port = _imap_for(entry)
    try:
        conn = imaplib.IMAP4_SSL(host, port)
    except OSError as exc:
        raise ValueError(f"couldn't reach {host} — {exc}") from None
    try:
        conn.login(address, pw)
    except imaplib.IMAP4.error as exc:
        detail = str(exc)
        if "AUTHENTICATIONFAILED" in detail or "Invalid credentials" in detail:
            raise ValueError(
                "the mail server refused the login. The app password is wrong "
                "or expired, or IMAP is switched off for this account — in "
                "Gmail that's Settings, Forwarding and POP/IMAP, Enable IMAP."
            ) from None
        raise ValueError("the mail server said: " + detail) from None
    return conn, address


def _selectable(conn, folder):
    try:
        return bool(folder) and conn.select(folder, readonly=True)[0] == "OK"
    except Exception:                                    # noqa: BLE001
        return False


def _sent_folder(conn):
    """The Sent folder, asked for rather than guessed where possible.

    Every candidate is confirmed by selecting it, including the one the
    server names itself — a \\Sent line parsed wrong is worse than no answer,
    because it silently makes everyone look like they are waiting on a reply.
    """
    candidates = []
    try:
        ok, boxes = conn.list()
        if ok == "OK":
            for raw in boxes:
                line = raw.decode("utf-8", "replace") if isinstance(raw, bytes) else str(raw)
                if "\\Sent" not in line:
                    continue
                # ... (\HasNoChildren \Sent) "/" "[Gmail]/Sent Mail"
                m = re.search(r'"((?:[^"\\]|\\.)*)"\s*$', line.strip())
                candidates.append(f'"{m.group(1)}"' if m
                                  else line.strip().rsplit(" ", 1)[-1])
    except Exception:                                    # noqa: BLE001
        pass
    for folder in candidates + SENT_GUESSES:
        if _selectable(conn, folder):
            return folder
    return ""


def _addresses(value):
    """Every address in a header value, lowercased, with its display name."""
    out = []
    for name, addr in email.utils.getaddresses([value or ""]):
        addr = (addr or "").strip().lower()
        if "@" in addr:
            out.append(((name or "").strip(), addr))
    return out


def _when(value):
    try:
        d = email.utils.parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    if d is None:
        return None
    return d.date()


def _scan(conn, folder, since, want):
    """Header-only sweep of one folder.

    `want` picks which side of the message we care about: "from" for the
    inbox (who wrote to her), "to" for Sent (who she wrote to). Yields
    (display_name, address, date) and nothing else — no subject is requested
    from the server, so there is no message content in this process at all.
    """
    if conn.select(folder, readonly=True)[0] != "OK":
        return
    ok, data = conn.search(None, f'(SINCE {since.strftime("%d-%b-%Y")})')
    if ok != "OK" or not data or not data[0]:
        return
    ids = data[0].split()
    # Newest first, and capped: a busy inbox should not turn a button press
    # into a two-minute stall.
    ids = ids[-800:]
    for i in range(0, len(ids), 100):
        chunk = b",".join(ids[i:i + 100])
        ok, parts = conn.fetch(chunk, HEADERS)
        if ok != "OK":
            continue
        for part in parts:
            if not isinstance(part, tuple) or len(part) < 2:
                continue
            raw = part[1].decode("utf-8", "replace")
            head = {}
            for m in re.finditer(r"^(From|To|Cc|Date):(.*(?:\n[ \t].*)*)", raw,
                                 re.M | re.I):
                head[m.group(1).lower()] = m.group(2).replace("\n", " ").strip()
            when = _when(head.get("date"))
            if not when:
                continue
            fields = ["from"] if want == "from" else ["to", "cc"]
            for f in fields:
                for name, addr in _addresses(head.get(f)):
                    yield name, addr, when


def check(address=None, days=None, write=False):
    """Look at the last N days and work out who is waiting on a reply.

    Returns a report of names and dates. Deliberately no subjects, no
    addresses of untracked senders, no counts that could identify anyone she
    has not chosen to track.
    """
    cfg = ES.load_cfg()
    if not reading_on(cfg):
        raise ValueError("email reading is off — turn it on first")
    days = int(days or read_days(cfg))
    since = date.today() - timedelta(days=days)

    aliases = people_aliases()
    if not aliases:
        raise ValueError("no people to match against yet")

    conn, address = _connect(address)
    incoming, outgoing, seen_in, unmatched = {}, {}, 0, set()
    try:
        for name, addr, when in _scan(conn, "INBOX", since, "from"):
            if addr == address.lower():
                continue                     # her own mail, bounced back to her
            seen_in += 1
            who = match(name, aliases) or match(addr.split("@", 1)[0], aliases)
            if not who:
                unmatched.add(addr)
                continue
            if when > incoming.get(who, date.min):
                incoming[who] = when
        sent = _sent_folder(conn)
        if sent:
            for name, addr, when in _scan(conn, sent, since, "to"):
                if addr == address.lower():
                    continue
                who = match(name, aliases) or match(addr.split("@", 1)[0], aliases)
                if who and when > outgoing.get(who, date.min):
                    outgoing[who] = when
    finally:
        try:
            conn.logout()
        except Exception:                                # noqa: BLE001
            pass

    people = []
    for who in sorted(set(incoming) | set(outgoing)):
        last_in, last_out = incoming.get(who), outgoing.get(who)
        people.append({
            "name": who,
            "last_in": last_in.isoformat() if last_in else "",
            "last_out": last_out.isoformat() if last_out else "",
            # She owes a reply when their last message is newer than hers.
            "owed": bool(last_in and (not last_out or last_in > last_out)),
        })

    written = []
    if write:
        for p in people:
            newest = max(d for d in (p["last_in"], p["last_out"]) if d)
            if set_last(p["name"], newest):
                written.append(f'{p["name"]} → {newest}')

    report = {
        "checked": datetime.now().isoformat(timespec="seconds"),
        "account": address,
        "days": days,
        "scanned": seen_in,
        "sent_folder": bool(sent),
        "people": people,
        "owed": [p["name"] for p in people if p["owed"]],
        # A count, never the addresses themselves — an untracked sender is
        # noise, and noise the brain keeps is a list of who mails her.
        "unmatched": len(unmatched),
        "written": written,
    }
    # State on disk is names and dates. No subjects, no addresses, nothing a
    # sender wrote.
    tmp = STATE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({k: report[k] for k in
                   ("checked", "days", "scanned", "owed", "unmatched")}, f, indent=2)
        f.write("\n")
    os.replace(tmp, STATE)
    return report


def last_check():
    try:
        with open(STATE, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


# --------------------------------------------------------------------------
# cli

def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status")
    o = sub.add_parser("on")
    o.add_argument("--days", type=int, default=14)
    sub.add_parser("off")
    c = sub.add_parser("check")
    c.add_argument("--days", type=int)
    c.add_argument("--write", action="store_true",
                   help="move Last dates forward in people.md")
    args = ap.parse_args()

    if args.cmd == "status":
        print("  reading: " + ("ON" if reading_on() else "off")
              + f"  (last {read_days()} days)")
        st = last_check()
        if st:
            print(f'  last checked {st.get("checked", "?")} — '
                  f'{st.get("scanned", 0)} messages, '
                  f'{len(st.get("owed", []))} waiting on you')
        return

    if args.cmd == "on":
        set_reading(True, args.days)
        print(f"  Reading is on: headers only, last {args.days} days.")
        print("  Check now:  python3 brain/tools/email_read.py check")
        return

    if args.cmd == "off":
        set_reading(False)
        print("  Reading is off. Nothing will look at your mail.")
        return

    if args.cmd == "check":
        try:
            r = check(days=args.days, write=args.write)
        except (ValueError, imaplib.IMAP4.error) as exc:
            sys.exit("  " + str(exc))
        print(f'  {r["scanned"]} messages in the last {r["days"]} days, '
              f'{r["unmatched"]} from people you do not track.')
        if not r["sent_folder"]:
            print("  (couldn't find your Sent folder — 'waiting on you' will "
                  "over-report until that works)")
        for p in r["people"]:
            flag = "  ← waiting on you" if p["owed"] else ""
            print(f'  {p["name"]:<20} they: {p["last_in"] or "—":<12} '
                  f'you: {p["last_out"] or "—":<12}{flag}')
        for line in r["written"]:
            print("  updated  " + line)
        if not args.write and r["people"]:
            print("\n  Nothing was written. Add --write to move Last dates on.")


if __name__ == "__main__":
    main()

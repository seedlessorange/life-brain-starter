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
}

# Microsoft is missing on purpose. Its IMAP server answers LOGINDISABLED and
# offers only OAuth, so an app password cannot log in — on a personal Outlook
# account or a school/work one alike. That is Microsoft's decision, not a
# setting anyone can switch, so the honest move is to say so rather than let
# someone spend an hour hunting for an app-password screen that no longer
# applies. Sending still works; only reading is closed.
NO_IMAP = {
    "outlook": ("Microsoft switched off password logins for reading mail, so "
                "no app password can work here — on a personal Outlook "
                "account or a school one. Reading needs Gmail, Yahoo or "
                "iCloud. To get school mail in, forward the senders that "
                "matter to one of those and read it there."),
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
        # Kept, not rebuilt: a fresh dict here switched Mac Mail back off
        # every time she toggled reading.
        em["read"] = dict(em.get("read") or {}, on=True, days=int(days))
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
    prov = entry.get("provider", "")
    # A run can write config.json, so an `imap_host` there is honoured only
    # when it matches a pin in brain/tools/.run-policy/email-hosts.json (key
    # "imap:<address>"), which no run can write. Otherwise the login — and
    # her app password — could be pointed at someone else's server.
    if entry.get("imap_host") and prov not in IMAP_HOSTS:
        want = [entry["imap_host"], int(entry.get("imap_port", 993))]
        pin = ES._host_pins().get("imap:" + (entry.get("address") or "").lower())
        if pin != want:
            raise ValueError(f"the mail server for {entry.get('address')} changed "
                             "since you set it up — run the email setup again")
        return tuple(want)
    if prov in NO_IMAP:
        raise ValueError(NO_IMAP[prov])
    if prov not in IMAP_HOSTS:
        raise ValueError(f"no IMAP host known for {prov!r}")
    return IMAP_HOSTS[prov]


def _connect(address=None, reason="check who has written to you"):
    address = address or ES.default_account()
    entry = next((a for a in ES.accounts() if a["address"] == address), None)
    if not entry:
        raise ValueError("that account isn't set up — connect it for sending first")
    try:
        pw = ES.kc_get(address, reason=reason)
    except RuntimeError as exc:
        raise ValueError(str(exc)) from None
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


def _privacy_guard():
    """The privacy level can switch the mail check off (Locked). It only
    subtracts: with it on, reading still needs reading switched on."""
    import privacy
    if not privacy.value("mail_check"):
        raise ValueError("the mail check is off at your privacy level")


def check(address=None, days=None, write=False, mac_only=False):
    """Look at the last N days and work out who is waiting on a reply.

    Returns a report of names and dates. Deliberately no subjects, no
    addresses of untracked senders, no counts that could identify anyone she
    has not chosen to track.

    mac_only: the Mail app's index and nothing else, never the password.
    That is the 7am check (her ask, 8 Oct: the plan should know who emailed
    without her pressing Check now), so no Touch ID prompt waits for nobody.
    """
    # Never inside a Claude run: the morning job asks before its run starts
    # (through the server, plan_sources.mail_check), and a run that calls
    # this is refused here even so. The night shift never reads mail.
    from private_gate import unattended
    if unattended():
        raise ValueError("email isn't read in unattended runs — her click only")
    _privacy_guard()
    cfg = ES.load_cfg()
    if not reading_on(cfg):
        raise ValueError("email reading is off — turn it on first")
    days = int(days or read_days(cfg))
    since = date.today() - timedelta(days=days)

    aliases = people_aliases()
    if not aliases:
        raise ValueError("no people to match against yet")

    import mail_local as ML
    use_imap = bool(ES.accounts()) and not mac_only
    use_mac = ML.on(cfg)
    if mac_only and not use_mac:
        raise ValueError("the morning check reads only the Mail app, and "
                         "the Mail app is off for reading")
    incoming, outgoing, seen_in, unmatched = {}, {}, 0, set()
    sources, problems, sent = [], [], ""

    def take_in(name, addr, when):
        nonlocal seen_in
        seen_in += 1
        who = match(name, aliases) or match(addr.split("@", 1)[0], aliases)
        if not who:
            unmatched.add(addr)
        elif when > incoming.get(who, date.min):
            incoming[who] = when

    def take_out(name, addr, when):
        who = match(name, aliases) or match(addr.split("@", 1)[0], aliases)
        if who and when > outgoing.get(who, date.min):
            outgoing[who] = when

    # Gmail (or any IMAP account) over the network. With Mac Mail on too, a
    # failed login here is one source down, not the whole check.
    if use_imap:
        try:
            conn, address = _connect(address)
        except ValueError as exc:
            if not use_mac:
                raise
            problems.append(str(exc))
        else:
            try:
                for name, addr, when in _scan(conn, "INBOX", since, "from"):
                    if addr != address.lower():   # her own mail, bounced back
                        take_in(name, addr, when)
                sent = _sent_folder(conn)
                if sent:
                    for name, addr, when in _scan(conn, sent, since, "to"):
                        if addr != address.lower():
                            take_out(name, addr, when)
            finally:
                try:
                    conn.logout()
                except Exception:                        # noqa: BLE001
                    pass
            sources.append(address)
    # Every account the Mail app holds — Outlook included, which IMAP
    # cannot reach — read from Mail's own index on this Mac.
    if use_mac:
        try:
            inc, out, _mine = ML.scan(days, cfg)
        except ValueError as exc:
            if not sources:
                raise
            problems.append("Mac Mail: " + str(exc))
        else:
            for row in inc:
                take_in(*row)
            for row in out:
                take_out(*row)
            sources.append("Mac Mail")
            sent = sent or bool(out)
    if not sources:
        raise ValueError("no mail source is set up — connect an account or "
                         "turn on Mac Mail")
    address = " + ".join(sources)

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
        "problems": problems,
    }
    # State on disk is names and dates. No subjects, no addresses, nothing a
    # sender wrote.
    tmp = STATE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({k: report[k] for k in
                   ("checked", "account", "days", "scanned", "owed", "unmatched",
                    "problems")}, f, indent=2)
        f.write("\n")
    os.replace(tmp, STATE)
    return report


def last_check():
    try:
        with open(STATE, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def recent_senders(days=14, limit=25):
    """Who emailed her in the last N days, most frequent first, so she can
    pick task-mail senders by tapping instead of hunting for an address
    (her ask, 9 Oct). Her click only, like the check: the From lines and a
    count, handed to the page once and never written anywhere, and nothing
    of what anyone wrote. The Mail app's copy when it is on (no password),
    else the inbox over IMAP (her Touch ID)."""
    from private_gate import unattended
    if unattended():
        raise ValueError("email isn't read in unattended runs — her click only")
    _privacy_guard()
    cfg = ES.load_cfg()
    if not reading_on(cfg):
        raise ValueError("turn on Mail in first: picking senders reads the "
                         "same From lines")
    import mail_local as ML
    import mail_tasks
    rows = []
    if ML.on(cfg):
        rows, _out, mine = ML.scan(days, cfg)
    else:
        conn, address = _connect(reason="list who has written to you")
        mine = {address.lower()}
        try:
            rows = list(_scan(conn, "INBOX", date.today() - timedelta(days=days),
                              "from"))
        finally:
            try:
                conn.logout()
            except Exception:                            # noqa: BLE001
                pass
    mine |= {(a.get("address") or "").lower() for a in ES.accounts()}
    allowed = {x.lower() for x in mail_tasks.senders(cfg)}
    seen = {}
    for name, addr, when in rows:
        addr = (addr or "").lower()
        if not addr or addr in mine:
            continue
        got = seen.setdefault(addr, {"address": addr, "name": "", "count": 0,
                                     "last": ""})
        got["count"] += 1
        w = when.isoformat() if hasattr(when, "isoformat") else str(when or "")
        if w >= got["last"]:
            got["last"], got["name"] = w, (name or got["name"]).strip()
    out = sorted(seen.values(), key=lambda r: (-r["count"], r["address"]))[:limit]
    for r in out:
        dom = "@" + r["address"].split("@", 1)[1]
        r["allowed"] = r["address"] in allowed or dom in allowed
    return out


# Domains anyone can hold an address at. Asking for "everyone she wrote to at
# gmail.com" would be asking for her address book, so they are refused.
PUBLIC_DOMAINS = {"gmail.com", "googlemail.com", "yahoo.com", "yahoo.fr", "hotmail.com",
                  "hotmail.fr", "outlook.com", "outlook.fr", "live.com", "live.fr",
                  "icloud.com", "me.com", "mac.com", "proton.me", "protonmail.com",
                  "gmx.com", "gmx.fr", "orange.fr", "free.fr", "wanadoo.fr", "sfr.fr",
                  "laposte.net", "aol.com", "msn.com"}


def lookup(addresses, domains=(), days=None, address=None):
    """For a project brain: when did she write to, or hear from, these exact
    addresses? Written for Venture's outreach log (venture-brain
    scripts/mail-check.ts), which sends the addresses of its leads.

    The same headers-only sweep as `check`, under the same rules: her own
    run only, never unattended, and only with reading switched on. What comes
    back is narrower than `check`: dates for the addresses asked about, and,
    for the domains asked about, the addresses she herself wrote to there, so
    a colleague she emailed can be suggested as a lead. Incoming mail from
    anyone not asked about is dropped, and nothing is written to disk.
    """
    from private_gate import unattended
    if unattended():
        raise ValueError("email isn't read in unattended runs — her click only")
    _privacy_guard()
    cfg = ES.load_cfg()
    if not reading_on(cfg):
        raise ValueError("email reading is off — turn it on first")
    want = {a.strip().lower() for a in addresses if a and "@" in a}
    doms = {d.strip().lower().lstrip("@") for d in domains if d}
    doms -= PUBLIC_DOMAINS
    if len(doms) > 200:
        raise ValueError("too many domains asked for")
    if not want and not doms:
        raise ValueError("nothing to look up")
    days = int(days or read_days(cfg))
    since = date.today() - timedelta(days=days)

    def at_domain(addr):
        dom = addr.split("@", 1)[-1]
        return any(dom == d or dom.endswith("." + d) for d in doms)

    found, new_out = {}, {}
    mine = set()

    def seen(kind, addr, when):
        if addr in mine:
            return
        if addr in want:
            entry = found.setdefault(addr, {"sent": set(), "received": set()})
            entry[kind].add(when.isoformat())
        elif kind == "sent" and at_domain(addr):
            new_out.setdefault(addr, set()).add(when.isoformat())

    import mail_local as ML
    sources, problems = [], []
    use_mac = ML.on(cfg)
    if ES.accounts():
        try:
            conn, acct = _connect(address, reason="log your Venture outreach")
        except ValueError as exc:
            if not use_mac:
                raise
            problems.append(str(exc))
        else:
            mine.add(acct.lower())
            try:
                for _name, addr, when in _scan(conn, "INBOX", since, "from"):
                    seen("received", addr, when)
                sent = _sent_folder(conn)
                if sent:
                    for _name, addr, when in _scan(conn, sent, since, "to"):
                        seen("sent", addr, when)
                else:
                    problems.append(f"{acct}: Sent folder not found")
            finally:
                try:
                    conn.logout()
                except Exception:                        # noqa: BLE001
                    pass
            sources.append(acct)
    if use_mac:
        try:
            inc, out, own = ML.scan(days, cfg)
        except ValueError as exc:
            problems.append("Mac Mail: " + str(exc))
        else:
            mine |= own
            for _name, addr, when in out:
                seen("sent", addr, when)
            for _name, addr, when in inc:
                seen("received", addr, when)
            sources.append("Mac Mail")
    if not sources:
        raise ValueError("no mail source could be read" +
                         (": " + "; ".join(problems) if problems else ""))
    return {
        "checked": datetime.now().isoformat(timespec="seconds"),
        "days": days,
        "sources": sources,
        "problems": problems,
        "found": {a: {k: sorted(v) for k, v in e.items()} for a, e in found.items()},
        "new_at_domains": {a: sorted(v) for a, v in new_out.items() if a not in mine},
    }


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
    lk = sub.add_parser("lookup", help="for a project brain: dates for the addresses "
                        "given as JSON on stdin ({\"addresses\": [...], \"domains\": [...]})")
    lk.add_argument("--days", type=int)
    args = ap.parse_args()

    if args.cmd == "lookup":
        try:
            ask = json.loads(sys.stdin.read() or "{}")
            r = lookup(ask.get("addresses") or [], ask.get("domains") or [], days=args.days)
        except (ValueError, imaplib.IMAP4.error) as exc:
            print(json.dumps({"error": str(exc)}))
            sys.exit(1)
        print(json.dumps(r))
        return

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

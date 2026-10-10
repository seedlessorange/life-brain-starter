#!/usr/bin/env python3
"""Who she wrote to, and who wrote to her — from the Mac's Mail app, locally.

    python3 brain/tools/mail_local.py status     # can it read? which boxes?
    python3 brain/tools/mail_local.py check      # report, write nothing

Why this exists. Her Outlook (school) account cannot be read over IMAP:
Microsoft refuses app passwords for reading, and the only door left is
OAuth. But Mail.app already holds that account, and every other one she
added, and keeps an index of their headers on disk. Reading that index
covers Outlook with no password, no login and no network at all.

What it reads — the same three facts email_read.py reads over IMAP: an
address, its display name, and a date. The SQL below names the addresses,
recipients, mailboxes and messages tables and nothing else; the subjects
table and the message files on disk are never opened, so there is no text
anyone wrote to her in this process. Nothing is written back to Mail.

Consent. Off until `email.read.mac_mail` is true in config.json, and it
runs only from her "Check now" button through email_read.check() — the
morning job and the night shift never call it (the same rule as all mail
reading, CLAUDE.md). macOS adds its own gate: Mail's folder is private
until she gives the app that runs the brain (Terminal) Full Disk Access.
"""
import glob
import os
import re
import shutil
import sqlite3
import sys
import tempfile
import unicodedata
from datetime import date, datetime, timedelta
from urllib.parse import unquote

MAIL = os.path.expanduser("~/Library/Mail")

# A mailbox is "sent" when one whole folder name in its path says so, in the
# languages her Macs and accounts use: Gmail's "[Gmail]/Sent Mail", Outlook's
# "Sent Items", iCloud's "Sent Messages", the French "Éléments envoyés" /
# "Messages envoyés". Whole names, not substrings: "Presentations" holds
# "sent" and is not her sent mail.
SENT_NAMES = {"sent", "sent mail", "sent messages", "sent items", "sent-mail",
              "éléments envoyés", "messages envoyés", "envoyés",
              "gesendet", "gesendete elemente", "enviados",
              "elementos enviados"}
# Mail that isn't correspondence: a spammer "writing to her" must not look
# like someone waiting on a reply.
SKIP_WORDS = ("junk", "spam", "trash", "deleted", "corbeille", "ind%c3%a9sirable",
              "indésirable", "draft", "brouillon", "outbox")

NO_ACCESS = ("macOS keeps Mail's folder private. Give Full Disk Access to "
             "the app that runs the brain (System Settings → Privacy & "
             "Security → Full Disk Access → turn on Terminal), then quit "
             "and reopen the brain.")


def on(cfg):
    return bool((((cfg or {}).get("email") or {}).get("read") or {}).get("mac_mail"))


def _guard(cfg=None, need_on=True):
    """Her click only, and only with Mac Mail switched on. The same rule as
    every other mail read: the morning job and the night shift never read."""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from private_gate import unattended
    if unattended():
        raise ValueError("Mac Mail isn't read in unattended runs — her click only")
    import privacy
    if not privacy.value("mail_check"):
        raise ValueError("the mail check is off at your privacy level")
    if need_on:
        if cfg is None:
            import email_send as ES
            cfg = ES.load_cfg()
        if not on(cfg):
            raise ValueError("Mac Mail reading is off — turn it on first")


def index_path():
    """The newest Envelope Index. Mail bumps the V-number on big macOS
    upgrades (V9, V10…) and leaves the old folder behind."""
    found = glob.glob(os.path.join(MAIL, "V*", "MailData", "Envelope Index"))

    def ver(p):
        try:
            return int(p.split(os.sep + "V")[-1].split(os.sep)[0])
        except ValueError:
            return 0
    return max(found, key=ver) if found else ""


def _open():
    """A read-only connection. Mail keeps the index in WAL mode while it
    runs, so opening in place read-only can fail on the shared-memory file;
    a private copy of the three files is the fallback, deleted afterwards."""
    try:
        os.listdir(MAIL)
    except PermissionError:
        raise ValueError(NO_ACCESS) from None
    except FileNotFoundError:
        raise ValueError("Mail has never been set up on this Mac") from None
    path = index_path()
    if not path:
        raise ValueError("Mail's index wasn't found — open Mail once and let it finish syncing")
    try:
        con = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=5)
        con.execute("select count(*) from mailboxes").fetchone()
        return con, None
    except PermissionError:
        raise ValueError(NO_ACCESS) from None
    except sqlite3.Error:
        pass
    tmp = tempfile.mkdtemp(prefix="brain-mail-")
    try:
        for suffix in ("", "-wal", "-shm"):
            if os.path.exists(path + suffix):
                shutil.copy2(path + suffix, os.path.join(tmp, "idx" + suffix))
    except PermissionError:
        shutil.rmtree(tmp, ignore_errors=True)
        raise ValueError(NO_ACCESS) from None
    try:
        con = sqlite3.connect(os.path.join(tmp, "idx"), timeout=5)
    except Exception:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
    return con, tmp


def _cols(con, table):
    return {r[1] for r in con.execute(f"pragma table_info({table})")}


def _check_shape(con):
    need = {"messages": {"sender", "mailbox", "date_sent", "date_received"},
            "addresses": {"address", "comment"},
            "recipients": {"message", "address"},
            "mailboxes": {"url"}}
    for table, cols in need.items():
        missing = cols - _cols(con, table)
        if missing:
            raise ValueError(f"Mail's index has changed shape ({table} lacks "
                             f"{', '.join(sorted(missing))}) — this reader needs updating")


def _is_sent(url):
    # "/" between folders, and "." on servers that nest as INBOX.Sent.
    # NFC first: macOS can hand back "é" as e plus an accent, two characters.
    path = unicodedata.normalize("NFC", unquote(url or ""))
    parts = [p.strip().lower() for p in re.split(r"[/.]", path)]
    return any(p in SENT_NAMES for p in parts if p)


def mailboxes():
    """(url, is_sent) for every mailbox — the status command's sanity check."""
    _guard(need_on=False)
    con, tmp = _open()
    try:
        return [(u, _is_sent(u)) for (u,) in con.execute("select url from mailboxes")]
    finally:
        con.close()
        if tmp:
            shutil.rmtree(tmp, ignore_errors=True)


def scan(days=14, cfg=None):
    """(incoming, outgoing, mine): incoming and outgoing are lists of
    (display_name, address, date). `mine` is the set of addresses she sends
    from, learned from her own sent boxes, so her own copies are skipped."""
    _guard(cfg)
    since = datetime.combine(date.today() - timedelta(days=days),
                             datetime.min.time()).timestamp()
    con, tmp = _open()
    try:
        _check_shape(con)
        # Unix seconds in the Mail versions seen so far; Apple's own epoch
        # (2001) in some older ones. The newest date tells which: in Unix
        # seconds anything this decade is past 1.3 billion.
        top = con.execute("select max(date_received) from messages").fetchone()[0] or 0
        shift = 0 if top > 1_300_000_000 else 978_307_200
        since -= shift

        def day(ts):
            return date.fromtimestamp((ts or 0) + shift)
        urls = dict(con.execute("select ROWID, url from mailboxes"))
        boxes = {rid: _is_sent(url) for rid, url in urls.items()}
        sent_ids = [rid for rid, s in boxes.items() if s]
        mine = set()
        outgoing, incoming = [], []
        if sent_ids:
            q = ",".join("?" * len(sent_ids))
            for (addr,) in con.execute(
                    f"select distinct a.address from messages m join addresses a "
                    f"on a.ROWID = m.sender where m.mailbox in ({q}) "
                    f"and m.date_sent >= ?", (*sent_ids, since)):
                if addr:
                    mine.add(addr.strip().lower())
            for name, addr, ts in con.execute(
                    f"select a.comment, a.address, m.date_sent from messages m "
                    f"join recipients r on r.message = m.ROWID "
                    f"join addresses a on a.ROWID = r.address "
                    f"where m.mailbox in ({q}) and m.date_sent >= ?",
                    (*sent_ids, since)):
                if addr and "@" in addr:
                    outgoing.append(((name or "").strip(), addr.strip().lower(),
                                     day(ts)))
        others = [rid for rid, s in boxes.items() if not s
                  and not any(w in unquote(urls[rid]).lower() for w in SKIP_WORDS)]
        if others:
            q = ",".join("?" * len(others))
            for name, addr, ts in con.execute(
                    f"select a.comment, a.address, m.date_received from messages m "
                    f"join addresses a on a.ROWID = m.sender "
                    f"where m.mailbox in ({q}) and m.date_received >= ?",
                    (*others, since)):
                if addr and "@" in addr and addr.strip().lower() not in mine:
                    incoming.append(((name or "").strip(), addr.strip().lower(),
                                     day(ts)))
        return incoming, outgoing, mine
    finally:
        con.close()
        if tmp:
            shutil.rmtree(tmp, ignore_errors=True)


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    try:
        if cmd == "status":
            boxes = mailboxes()
            sent = [unquote(u).rsplit("/", 2)[-2:] for u, s in boxes if s]
            print(f"  Mail's index: {index_path()}")
            print(f"  {len(boxes)} mailboxes, {len(sent)} counted as sent:")
            for parts in sent:
                print("    " + "/".join(parts))
        elif cmd == "check":
            inc, out, mine = scan(int(sys.argv[2]) if len(sys.argv) > 2 else 14)
            print(f"  sent from {len(mine)} of your addresses; "
                  f"{len(out)} recipients, {len(inc)} incoming in the window")
        else:
            sys.exit("usage: mail_local.py status | check [days]")
    except ValueError as exc:
        sys.exit("  " + str(exc))


if __name__ == "__main__":
    main()

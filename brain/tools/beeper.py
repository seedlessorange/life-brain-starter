#!/usr/bin/env python3
"""Pull "last spoke" dates from Beeper, automatically.

    python3 brain/tools/beeper.py login     # once — approve it in Beeper
    python3 brain/tools/beeper.py sync      # see what it would change
    python3 brain/tools/beeper.py sync --write

Beeper Desktop ships an official local API covering every network she has
bridged (WhatsApp, Instagram, Messenger, Signal, iMessage...). That matters
because it is the only fully automatic route that is also legitimate: it is
Beeper's own supported developer feature, it runs on 127.0.0.1 and only while
the app is open, and nothing is reverse-engineered — so there is no ToS
violation and no risk to her WhatsApp number.

WHAT IT READS: the chat list — who each direct chat is with, and when it last
had activity. It does NOT read message text. `chats/search` returns titles and
timestamps, which is all this needs, and nothing else is requested.

Runs on macOS, Windows and Linux (Beeper Desktop ships for all three).
The token goes to the OS credential store where there is one — the macOS
Keychain, or Windows Credential Manager via `pip install keyring` — and
otherwise to an owner-only file, which it tells you about rather than
doing quietly.
"""

import argparse
import base64
import hashlib
import json
import os
import re
import secrets
import subprocess
import sys
import threading
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from datetime import date, datetime
from http.server import BaseHTTPRequestHandler, HTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from import_chats import PEOPLE as PEOPLE_MD, people_aliases, set_last, set_ball_nobody, set_ball_me  # noqa: E402
from people_update import match                          # noqa: E402

API = os.environ.get("BEEPER_API", "http://127.0.0.1:23373")
CALLBACK_PORT = int(os.environ.get("BEEPER_CALLBACK_PORT", "7719"))
REDIRECT = f"http://127.0.0.1:{CALLBACK_PORT}/callback"
KEYCHAIN_SERVICE = "life-brain-beeper"
KEYCHAIN_ACCOUNT = "beeper-api-token"
CLIENT_FILE = os.path.join(os.path.dirname(HERE), ".beeper-client.json")


# --------------------------------------------------------------------------
# secrets: the OS keystore where there is one, a locked-down file otherwise

TOKEN_FILE = os.path.join(os.path.dirname(HERE), ".beeper-token")


def keychain_set(value):
    if sys.platform == "darwin":
        subprocess.run(["security", "add-generic-password", "-U",
                        "-s", KEYCHAIN_SERVICE, "-a", KEYCHAIN_ACCOUNT, "-w", value],
                       check=True, capture_output=True)
        return "macOS Keychain"
    try:
        # Windows Credential Manager / Linux Secret Service, if keyring is here.
        import keyring
        keyring.set_password(KEYCHAIN_SERVICE, KEYCHAIN_ACCOUNT, value)
        return "your system credential store"
    except Exception:
        pass
    # Last resort: a file only this user can read. Said out loud rather than
    # done quietly, because it is genuinely weaker than the alternatives.
    with open(TOKEN_FILE, "w", encoding="utf-8") as f:
        f.write(value)
    os.chmod(TOKEN_FILE, 0o600)
    return f"{TOKEN_FILE} (owner-only). For something stronger: pip install keyring"


def keychain_get():
    if sys.platform == "darwin":
        r = subprocess.run(["security", "find-generic-password",
                            "-s", KEYCHAIN_SERVICE, "-a", KEYCHAIN_ACCOUNT, "-w"],
                           capture_output=True, text=True)
        if r.returncode == 0:
            return r.stdout.strip()
    else:
        try:
            import keyring
            tok = keyring.get_password(KEYCHAIN_SERVICE, KEYCHAIN_ACCOUNT)
            if tok:
                return tok
        except Exception:
            pass
    try:
        with open(TOKEN_FILE, encoding="utf-8") as f:
            return f.read().strip() or None
    except OSError:
        return None


# --------------------------------------------------------------------------
# http

def call(path, token=None, params=None, method="GET", body=None):
    url = API + path
    if params:
        url += "?" + urllib.parse.urlencode(params, doseq=True)
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Accept", "application/json")
    if data:
        req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            return json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode()[:200]
        raise SystemExit(f"Beeper API {exc.code} on {path}: {detail}")
    except urllib.error.URLError as exc:
        raise SystemExit(
            "Could not reach Beeper Desktop. Is the app running, and is the API "
            f"enabled (Settings > Developers)?\n  {exc}")


# --------------------------------------------------------------------------
# login

class _Catch(BaseHTTPRequestHandler):
    code = None

    def do_GET(self):
        q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        _Catch.code = (q.get("code") or [None])[0]
        ok = bool(_Catch.code)
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(
            ("<body style='font:16px -apple-system;padding:60px;background:#F7F2E9;color:#26231D'>"
             + ("<h2>Connected.</h2><p>You can close this tab and go back to the terminal.</p>"
                if ok else "<h2>No code came back.</h2><p>Try again.</p>")
             + "</body>").encode())

    def log_message(self, *a):
        pass


def login():
    client = {}
    if os.path.exists(CLIENT_FILE):
        try:
            client = json.load(open(CLIENT_FILE))
        except Exception:
            client = {}
    if not client.get("client_id"):
        client = call("/oauth/register", method="POST", body={
            "client_name": "life-brain",
            "redirect_uris": [REDIRECT],
            "grant_types": ["authorization_code", "refresh_token"],
            "response_types": ["code"],
            "token_endpoint_auth_method": "none",
        })
        with open(CLIENT_FILE, "w") as f:
            json.dump({"client_id": client["client_id"]}, f)
        print(f"Registered with Beeper as '{client.get('client_name', 'life-brain')}'.")

    verifier = base64.urlsafe_b64encode(secrets.token_bytes(48)).decode().rstrip("=")
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    state = secrets.token_urlsafe(16)

    srv = HTTPServer(("127.0.0.1", CALLBACK_PORT), _Catch)
    threading.Thread(target=srv.handle_request, daemon=True).start()

    scope = "read write" if ("--write" in sys.argv) else "read"
    url = API + "/oauth/authorize?" + urllib.parse.urlencode({
        "client_id": client["client_id"], "redirect_uri": REDIRECT,
        "response_type": "code", "scope": scope, "state": state,
        "code_challenge": challenge, "code_challenge_method": "S256",
    })
    print("\n  Opening Beeper to ask for your approval.")
    print("  Approve the request, and this will finish on its own.\n")
    webbrowser.open(url)

    for _ in range(120):
        if _Catch.code:
            break
        threading.Event().wait(1)
    if not _Catch.code:
        raise SystemExit("No approval came back within two minutes. Run login again.")

    tok = call("/oauth/token", method="POST", body={
        "grant_type": "authorization_code", "code": _Catch.code,
        "redirect_uri": REDIRECT, "client_id": client["client_id"],
        "code_verifier": verifier,
    })
    access = tok.get("access_token")
    if not access:
        raise SystemExit(f"No token in the reply: {json.dumps(tok)[:200]}")
    where = keychain_set(access)
    print(f"  Connected. Token stored in {where}.")
    print("  Now run:  python3 brain/tools/beeper.py sync\n")


# --------------------------------------------------------------------------
# sync

def iso_date(v):
    """Beeper timestamps arrive as ISO strings or epoch ms."""
    if not v:
        return None
    if isinstance(v, (int, float)):
        return datetime.fromtimestamp(v / 1000 if v > 1e11 else v).date()
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", str(v))
    if m:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    return None


IGNORE_FILE = os.path.join(os.path.dirname(HERE), "people-ignored.json")


def load_ignored():
    try:
        with open(IGNORE_FILE, encoding="utf-8") as f:
            return set(json.load(f))
    except Exception:
        return set()


def save_ignored(names):
    with open(IGNORE_FILE, "w", encoding="utf-8") as f:
        json.dump(sorted(names), f, indent=2)
        f.write("\n")


def ignore_chat(name):
    ig = load_ignored()
    ig.add(name.strip())
    save_ignored(ig)


def link_alias(chat_name, person):
    """Record that a chat name is someone already on the list.

    Instagram handles rarely match the name in your head, and re-answering
    "is @sol.fjn Sol?" every sync would be worse than not asking. Written as
    an `Also:` line, so the match is permanent and readable.
    """
    chat_name, person = chat_name.strip(), person.strip()
    with open(PEOPLE_MD, encoding="utf-8") as f:
        lines = f.read().split("\n")
    start = None
    for i, line in enumerate(lines):
        h = re.match(r"^##\s+(.*)$", line.strip())
        if h and re.sub(r"[*`]", "", h.group(1)).strip().lower() == person.lower():
            start = i
            break
    if start is None:
        raise ValueError(f"nobody called {person!r}")
    end = len(lines)
    for j in range(start + 1, len(lines)):
        if re.match(r"^##\s+", lines[j].strip()):
            end = j
            break
    for j in range(start + 1, end):
        m = re.match(r"^(\s*-\s+\*\*Also:\*\*)\s*(.*)$", lines[j], re.I)
        if m:
            have = [a.strip() for a in m.group(2).split(",") if a.strip()]
            if chat_name.lower() in [h.lower() for h in have]:
                return False
            lines[j] = f"{m.group(1)} {', '.join(have + [chat_name])}"
            break
    else:
        insert = start + 1
        for j in range(start + 1, end):
            if re.match(r"^\s*-\s+\*\*[A-Za-z ]+:\*\*", lines[j]):
                insert = j + 1
        lines.insert(insert, f"- **Also:** {chat_name}")
    with open(PEOPLE_MD, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return True


def fetch_chats(token, limit=1000, include_groups=True):
    """Chats with their last activity. Titles and timestamps only.

    Groups are fetched but only ever matched by their own title, never spread
    across their members: a message in a group of twelve is not a conversation
    with each of them, and counting it as one would make everybody look
    recently-contacted — which is precisely the lie this file exists to avoid.
    So a group only counts if she has deliberately added it as something to
    keep warm (a family thread, a close group of four).
    """
    out = []
    for kind in (["single", "group"] if include_groups else ["single"]):
        cursor, got = None, 0
        while got < limit:
            params = {"type": kind, "limit": min(100, limit - got)}
            if cursor:
                # Walk backwards in time from the newest page: the API's
                # cursors are oldestCursor/newestCursor, and "before" +
                # oldestCursor is how you reach everything older. The old
                # nextCursor guess matched nothing, so only the freshest 100
                # chats ever loaded — everyone quiet for a month was missing.
                params.update({"cursor": cursor, "direction": "before"})
            page = call("/v1/chats/search", token=token, params=params)
            items = page.get("items") or page.get("chats") or page.get("data") or []
            if not items:
                break
            for it in items:
                if isinstance(it, dict):
                    it["_group"] = (kind == "group")
            out += items
            got += len(items)
            cursor = (page.get("oldestCursor") or page.get("nextCursor")
                      or page.get("cursor")
                      or (page.get("pagination") or {}).get("nextCursor"))
            if not cursor or not page.get("hasMore", bool(cursor)):
                break
    return out


def chat_name(c):
    for k in ("title", "name", "displayName", "chatName"):
        if c.get(k):
            return str(c[k])
    ps = c.get("participants")
    if isinstance(ps, dict):
        ps = ps.get("items") or []
    if isinstance(ps, list) and ps:
        for p in ps:
            if isinstance(p, dict) and not p.get("isSelf"):
                return str(p.get("fullName") or p.get("displayName") or p.get("username") or "")
    return ""


# Digits, the glyphs Beeper masks digits with, and the punctuation a phone
# number is written with. Letters are deliberately absent — one letter and it
# is a name, however odd.
_NUMERISH = set("0123456789+()[]-./ •∙·‧⋅*#~ ")


def is_bare_number(name):
    """A chat whose whole name is a phone number, masked or not.

    "+34631179463" says nothing about who it is, so it can never be sorted
    into a circle — it is a row you skip every time you open the sorter, and
    there are ten times more of them than there are namable people left.

    They are FILTERED, never deleted or hidden: the chat is untouched in
    WhatsApp, the count is reported on the page so nothing vanishes quietly,
    and the day one of them acquires a name it rejoins the queue by itself.
    """
    s = (name or "").strip()
    if not s or not all(ch in _NUMERISH for ch in s):
        return False
    # Long enough to actually be a number. Guards a contact genuinely called
    # "22" or "+" from being swept up with them.
    return sum(1 for ch in s if ch not in "+()[]-./  ") >= 7


def chat_members(c, limit=10):
    """Non-self participant names of a chat — how a group tells you who is
    inside it, so its members can become contacts."""
    ps = c.get("participants")
    if isinstance(ps, dict):
        ps = ps.get("items") or []
    out = []
    for p in (ps or []):
        if isinstance(p, dict) and not p.get("isSelf"):
            nm = str(p.get("fullName") or p.get("displayName")
                     or p.get("username") or "").strip()
            if nm and nm not in out:
                out.append(nm)
    return out[:limit]


def chat_when(c):
    for k in ("lastActivity", "timestamp", "lastMessageTime", "updatedAt", "sortKey"):
        d = iso_date(c.get(k))
        if d:
            return d
    msg = c.get("lastMessage") or {}
    return iso_date(msg.get("timestamp")) if isinstance(msg, dict) else None


AVATARS = os.path.join(os.path.dirname(HERE), "avatars")
_IMG_EXT = ((b"\xff\xd8", ".jpg"), (b"\x89P", ".png"),
            (b"RIFF", ".webp"), (b"GIF8", ".gif"))


def avatar_slug(name):
    """One safe, stable filename per person — build.py must derive the
    identical slug to find the face again."""
    import unicodedata
    s = unicodedata.normalize("NFKD", name or "").encode("ascii", "ignore").decode()
    s = re.sub(r"[^A-Za-z0-9]+", "-", s).strip("-").lower()
    return s or "x"


def chat_avatar(c):
    """A DM's face: the non-self participant's imgURL, which is a file:// URL
    into Beeper's local media cache. Groups have icons, not faces — skipped."""
    if c.get("_group"):
        return ""
    ps = c.get("participants")
    if isinstance(ps, dict):
        ps = ps.get("items") or []
    for p in (ps or []):
        if isinstance(p, dict) and not p.get("isSelf") and p.get("imgURL"):
            return str(p["imgURL"])
    return ""


def save_avatar(who, img_path):
    """Copy a chat's avatar from Beeper's own media cache into brain/avatars/
    — a local file copied to a local file, nothing fetched, nothing uploaded.
    First face wins; returns True only when a new one lands."""
    try:
        if img_path.startswith("file://"):
            from urllib.parse import unquote
            img_path = unquote(img_path[7:])
        if not img_path or not os.path.isfile(img_path):
            return False
        slug = avatar_slug(who)
        if any(os.path.exists(os.path.join(AVATARS, slug + x))
               for _, x in _IMG_EXT):
            return False
        with open(img_path, "rb") as f:
            head = f.read(8)
        ext = next((x for magic, x in _IMG_EXT if head.startswith(magic)), None)
        if not ext:
            return False                     # not an image we recognise
        os.makedirs(AVATARS, exist_ok=True)
        import shutil
        shutil.copyfile(img_path, os.path.join(AVATARS, slug + ext))
        return True
    except OSError:
        return False


def _owed_names():
    """People whose Ball is with you — the only rows worth asking Beeper who
    spoke last, because that answer can retire the debt."""
    try:
        with open(PEOPLE_MD, encoding="utf-8") as f:
            text = f.read()
    except OSError:
        return set()
    out, cur = set(), None
    for line in text.split("\n"):
        h = re.match(r"^##\s+(.*)$", line.strip())
        if h:
            cur = re.sub(r"[*`]", "", h.group(1)).strip()
            continue
        m = re.match(r"^\s*-\s+\*\*Ball:\*\*\s*(.*)$", line, re.I)
        if m and cur and m.group(1).strip().lower().startswith(("me", "mine", "you")):
            out.add(cur.lower())
    return out


def focus_chat(person):
    """Bring Beeper Desktop to the front, opened on this person's newest
    direct chat (the API's /v1/focus). A window focus and nothing else —
    no message is sent, drafted, or read."""
    token = keychain_get()
    if not token:
        raise RuntimeError("Not connected to Beeper — run the login once.")
    known = people_aliases()
    want = (person or "").strip().lower()
    if not want:
        raise RuntimeError("who?")
    for c in fetch_chats(token, include_groups=False):
        if not isinstance(c, dict) or c.get("_group"):
            continue
        cid = c.get("id") or c.get("chatID") or c.get("chatId")
        if not cid:
            continue
        who = match(chat_name(c), known)
        if who and who.lower() == want:
            call("/v1/focus", token=token, method="POST", body={"chatID": cid})
            return {"chat": chat_name(c)}
    raise RuntimeError(f"no direct Beeper chat found for {person}")


def collect(write=False):
    """The whole sync, as data. Returns (updated, unmatched, total).

    Split out from the printing so the page can call it too — the terminal
    and the browser must never be able to disagree about what synced.
    """
    token = keychain_get()
    if not token:
        raise RuntimeError("Not connected to Beeper yet — run the login once.")

    chats = fetch_chats(token)
    if not chats:
        raise RuntimeError("Beeper returned no chats. Is it finished syncing?")

    known = people_aliases()
    ignored = {n.lower() for n in load_ignored()}
    today = date.today()
    updated, unmatched = [], []
    n_numeric = 0                 # chats whose only name is a phone number

    # Newest first, so a person with several chats keeps their latest contact.
    rows = []
    for c in chats:
        name, when = chat_name(c).strip(), chat_when(c)
        if name and when and when <= today:
            rows.append((name, when, (c.get("network") or c.get("accountID") or ""),
                         bool(c.get("_group")),
                         chat_members(c) if c.get("_group") else [],
                         c.get("id") or "",
                         chat_avatar(c)))
    rows.sort(key=lambda r: r[1], reverse=True)
    # /v1/accounts answers with a bare list on some versions and a wrapper on
    # others, so accept either rather than crash the whole sync.
    me = call("/v1/accounts", token=token)
    accounts = me if isinstance(me, list) else (
        (me or {}).get("items") or (me or {}).get("accounts") or (me or {}).get("data") or [])
    self_names = set()
    for a in accounts:
        if not isinstance(a, dict):
            continue
        u = a.get("user") or {}
        for k in ("fullName", "displayName", "username"):
            if u.get(k):
                self_names.add(str(u[k]).strip().lower())
    rows = [r for r in rows if r[0].strip().lower() not in self_names]

    seen = set()
    owed = _owed_names() if write else set()
    # Personal-circle names and the reply fuse, for RAISING the ball below.
    personal, fuse = set(), 2
    if write:
        try:
            import model as _M
            fuse = int((_M.load_config().get("people") or {})
                       .get("reply_after_days", 2))
            # Short-rhythm personal people only — the close friends of her
            # ask. Personal-circle alone flagged 90+ acquaintances whose
            # chats merely ENDED with their message; a person whose rhythm
            # she set to a fortnight or less is one she actively keeps warm,
            # and those are the replies worth raising automatically.
            personal = {p["name"].lower() for p in _M.load_people()
                        if p.get("personal")
                        and (p.get("every_days") or 999) <= 16}
        except Exception:
            personal = set()    # raising is a bonus; never fail the sync over it
    for name, when, network, is_group, members, cid, img in rows:
        who = match(name, known)
        if not who:
            if name not in seen and name.lower() not in ignored:
                seen.add(name)
                # A bare phone number cannot be sorted into a circle by
                # anybody, so it never joins the queue — only the count does.
                if is_bare_number(name):
                    n_numeric += 1
                    continue
                unmatched.append({"name": name, "date": when.isoformat(),
                                  "days": (today - when).days,
                                  "network": network, "group": is_group,
                                  "members": members})
            continue
        if who in seen:
            continue
        seen.add(who)
        days = (today - when).days
        # A face for every sorted person: the newest DM chat's avatar, copied
        # once from Beeper's local cache. Groups keep no faces.
        if write and not is_group and img:
            save_avatar(who, img)
        # An owed reply whose chat now ends with YOUR message is a debt already
        # paid — one look at the last message's direction, and the flag drops.
        # (This used to be asymmetric — clear only. She asked for the other
        # direction on 19 Aug 2026, the Ember case: see the raise block below.)
        cleared = False
        if write and not is_group and cid and who.lower() in owed:
            try:
                pg = call(f"/v1/chats/{cid}/messages", token=token,
                          params={"limit": 1, "direction": "before"})
                msgs = pg.get("items") if isinstance(pg, dict) else (pg or [])
                if msgs and isinstance(msgs[0], dict) and msgs[0].get("isSender"):
                    cleared = set_ball_nobody(who)
            except Exception:
                pass            # direction is a bonus; never fail the sync over it
        # The raise: a personal-circle DM whose newest message is THEIRS,
        # unanswered past the fuse (config people.reply_after_days, default
        # 2), flips the ball to Me — a reply owed to a close friend surfaces
        # in days, not at the circle's fortnightly rhythm. Network circles
        # stay a human call.
        # The window matters as much as the fuse: a chat that happens to END
        # with their message from months back is a conversation that finished,
        # not a reply owed — without the 14-day ceiling this flagged 90+
        # people on its first run. Recent AND unanswered, or nothing.
        raised = False
        if (write and not is_group and cid and not cleared
                and who.lower() in personal and who.lower() not in owed
                and fuse <= days <= 14):
            try:
                pg = call(f"/v1/chats/{cid}/messages", token=token,
                          params={"limit": 1, "direction": "before"})
                msgs = pg.get("items") if isinstance(pg, dict) else (pg or [])
                if msgs and isinstance(msgs[0], dict) and not msgs[0].get("isSender"):
                    raised = set_ball_me(who)
            except Exception:
                pass            # direction is a bonus; never fail the sync over it
        entry = {"name": who, "date": when.isoformat(), "days": days,
                 "network": network, "group": is_group}
        if cleared:
            entry["ball_cleared"] = True
        if raised:
            entry["ball_raised"] = True
        if not write or set_last(who, when.isoformat()) or cleared or raised:
            updated.append(entry)

    # Cache the unmatched list so the page can embed the triage without a
    # 20-second live read. Refreshed by every sync (morning + background).
    try:
        with open(os.path.join(os.path.dirname(HERE), ".beeper-review.json"),
                  "w", encoding="utf-8") as f:
            json.dump({"when": datetime.now().isoformat(timespec="seconds"),
                       "numeric_hidden": n_numeric,
                       "unmatched": unmatched}, f, indent=1)
    except OSError:
        pass
    return updated, unmatched, len(rows)


def send_message(person, text):
    """Send ONE message to ONE person's direct chat, on her explicit click.

    Every refusal here is the boundary working, not an error to route around:
    - the person must be on the people list and outside every personal circle
      (re-derived from people.md right now, never trusted from a draft file);
    - only a direct chat matched unambiguously by name or `Also:` alias will
      do — a group, no match, or two candidate chats all refuse;
    - unattended runs (night shift, morning job) are refused outright.

    Returns (ok, detail). Never raises for a foreseeable failure — the page
    shows `detail` to the owner as the reason nothing was sent.
    """
    person = (person or "").strip()
    text = (text or "").strip()
    if os.environ.get("LIFEBRAIN_UNATTENDED"):
        return False, "sending is disabled in unattended runs"
    if not person or not text:
        return False, "need both a person and a message"

    import model as M
    people = {p["name"].lower(): p for p in M.load_people()}
    p = people.get(person.lower())
    if p is None:
        return False, f"{person} is not on your people list — sending needs a tracked person"
    if p.get("personal", True):
        return False, (f"{person} is in a personal circle — Claude can't send "
                       "to them, only draft")

    token = keychain_get()
    if not token:
        return False, "no Beeper token — connect Beeper on the People page first"

    # The names this person may appear under in a chat list.
    wanted = {person.lower()}
    for canon, names in people_aliases().items():
        if canon.lower() == person.lower():
            wanted.update(n.lower() for n in names)

    try:
        chats = fetch_chats(token, include_groups=False)
    except SystemExit as exc:
        return False, str(exc)
    hits = []
    for c in chats:
        name = chat_name(c).strip()
        if name and name.lower() in wanted:
            cid = c.get("id") or c.get("chatID") or c.get("chatId")
            if cid:
                hits.append((name, str(cid)))
    if not hits:
        return False, (f"no direct chat found for {person} — link their chat "
                       "name on People > Review chats first")
    if len({cid for _, cid in hits}) > 1:
        return False, (f"{len(hits)} chats match {person} — say which one by "
                       "linking the right chat name first")

    _, cid = hits[0]
    try:
        call(f"/v1/chats/{urllib.parse.quote(cid, safe='')}/messages",
             token=token, method="POST", body={"text": text})
    except SystemExit as exc:
        return False, str(exc)
    try:
        set_last(person, date.today().isoformat())
    except Exception:
        pass    # the send happened; a missed Last date must not report failure
    return True, "sent"


def sync(write=False):
    """The terminal view of collect()."""
    try:
        updated, unmatched, total = collect(write=write)
    except RuntimeError as exc:
        raise SystemExit(str(exc))

    print(f"\nRead {total} chats from Beeper. Message text was not requested.\n")
    if updated:
        print("On your people list:")
        for u in updated:
            ago = "today" if u["days"] == 0 else f"{u['days']}d ago"
            tag = " (group)" if u["group"] else ""
            print(f"  {u['name']:<20} {u['date']}  ({ago})  {u['network']}{tag}")
    if unmatched:
        print(f"\nNot on your people list ({len(unmatched)} total, newest 15):")
        for u in unmatched[:15]:
            tag = " (group)" if u["group"] else ""
            print(f"  {u['name']:<28} {u['date']}  {u['network']}{tag}")
        print("\nMatch them up on the page: People > Review chats.")
    if write:
        print(f"\nUpdated {len(updated)} people. Rebuild: python3 brain/tools/build.py")
    else:
        print("\nNothing was changed. Re-run with --write to apply.")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("login", help="connect to Beeper (one time)")
    s = sub.add_parser("sync", help="update last-spoke dates")
    s.add_argument("--write", action="store_true")
    a = sub.add_parser("add", help="add people to the list by name")
    a.add_argument("names", nargs="+")
    a.add_argument("--every", default="monthly", help="rhythm, e.g. weekly")
    a.add_argument("--circle", default="Friends")
    sub.add_parser("status", help="is it connected?")
    args = ap.parse_args()

    if args.cmd == "add":
        add_people(args.names, args.every, args.circle)
    elif args.cmd == "login":
        login()
    elif args.cmd == "status":
        info = call("/v1/info")
        print(f"Beeper {info['app']['version']} on {info['server']['base_url']}, "
              f"MCP {'on' if info['server'].get('mcp_enabled') else 'off'}")
        print("Token in Keychain: " + ("yes" if keychain_get() else "no — run login"))
    else:
        sync(write=args.write)


if __name__ == "__main__":
    main()

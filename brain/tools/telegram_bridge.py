"""The brain as a contact: a Telegram bot, long-polled from this Mac.

"brain: buy socks before Montenegro" from a pharmacy queue lands in the
inbox by the time you're home; "plan" answers with today's page; the
morning plan arrives as a message once the 7am refresh has run. Capture and read-back only:
starting a job or spending anything stays a button pressed on the page.

Technically it needs no server of its own: this Mac polls Telegram
(getUpdates, 50 s long-poll), so it works from any network and stops
mattering the moment serve.py isn't running. The bot appears inside
Beeper like any other Telegram chat.

Setup, once, two minutes:
  1. In Telegram, message @BotFather: /newbot — any name and username.
  2. Put the token in via the page's Connections card (or by hand into
     brain/.telegram.json — the file is gitignored, the token never
     enters history).
  3. The bridge mints a six-digit PAIRING CODE (shown on the Connections
     card). Message that code to your bot — only the chat that sends the
     exact code is ever adopted; every other sender gets silence,
     forever. Bot usernames are public, so the code is what makes "first
     message wins" safe. If you ever need to re-pair, delete the
     "chat_id" line from brain/.telegram.json.

A paired chat can do three things: file text into the inbox, ask for the
plan, and send a voice note — which is downloaded, transcribed on this
Mac's own GPU, filed as a transcript, and queued for Claude to turn into
tasks, after which the audio is deleted. Anything else it is told, it
ignores.
"""
import hashlib
import json
import os
import re
import secrets
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
BRAIN = os.path.dirname(HERE)
# The routine nudge reads habits.md through the parser rather than re-reading
# the file here, so the phone and the page can never disagree about the steps.
if HERE not in sys.path:
    sys.path.insert(0, HERE)
CONF = os.path.join(BRAIN, ".telegram.json")


def _load():
    try:
        with open(CONF, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save(conf):
    tmp = CONF + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(conf, f, indent=2)
    os.replace(tmp, CONF)


def _api(token, method, **params):
    url = f"https://api.telegram.org/bot{token}/{method}"
    data = urllib.parse.urlencode(params).encode()
    with urllib.request.urlopen(url, data, timeout=70) as r:
        return json.load(r)


def _send(token, chat_id, text, buttons=None):
    """Telegram caps messages at 4096 chars; the plan can run long. `buttons`
    is [(label, callback_data)], attached to the last chunk so the taps sit
    under the whole message."""
    chunks = [text[i:i + 3900] for i in range(0, max(len(text), 1), 3900)]
    for n, chunk in enumerate(chunks):
        extra = {}
        if buttons and n == len(chunks) - 1:
            extra["reply_markup"] = json.dumps({"inline_keyboard": [[
                {"text": lbl, "callback_data": cb} for lbl, cb in buttons]]})
        _api(token, "sendMessage", chat_id=chat_id, text=chunk, **extra)


def _send_document(token, chat_id, path, caption=""):
    """Upload a file to her own chat. Hand-rolled multipart because the
    bridge has no requests dependency and urlencode cannot carry bytes.
    Telegram accepts 50MB for a bot upload; anything larger is told, not
    truncated."""
    size = os.path.getsize(path)
    if size > 49 * 1024 * 1024:
        _send(token, chat_id,
              f"{os.path.basename(path)} is {size / 1e6:.0f}MB and a bot can "
              "only upload 50MB. It is on the Mac if you need it.")
        return False
    with open(path, "rb") as f:
        blob = f.read()
    boundary = "----brain" + hashlib.md5(blob[:2048]).hexdigest()[:16]
    name = os.path.basename(path)
    parts = []
    for key, val in (("chat_id", str(chat_id)), ("caption", caption[:1000])):
        if val:
            parts.append(
                f'--{boundary}\r\nContent-Disposition: form-data; '
                f'name="{key}"\r\n\r\n{val}\r\n'.encode())
    parts.append(
        f'--{boundary}\r\nContent-Disposition: form-data; name="document"; '
        f'filename="{name}"\r\n'
        f'Content-Type: application/octet-stream\r\n\r\n'.encode())
    body = b"".join(parts) + blob + f"\r\n--{boundary}--\r\n".encode()
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendDocument", data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.load(r).get("ok", False)


def _send_html(token, chat_id, text):
    """HTML mode for the briefing, so headlines are tappable links. Splits
    on paragraph boundaries — a mid-tag split makes Telegram reject the
    whole message — and mutes link previews, or every story grows a card."""
    chunk = ""
    for para in text.split("\n\n"):
        if chunk and len(chunk) + len(para) + 2 > 3500:
            _api(token, "sendMessage", chat_id=chat_id, text=chunk,
                 parse_mode="HTML", disable_web_page_preview="true")
            chunk = ""
        chunk = (chunk + "\n\n" + para).strip()
    if chunk:
        _api(token, "sendMessage", chat_id=chat_id, text=chunk,
             parse_mode="HTML", disable_web_page_preview="true")


def _plan_text():
    """today.md as a phone-sized message, with the markdown furniture off.

    today.md is hard-wrapped for the page at ~78 characters. A phone wraps
    again at its own width, so sending it verbatim produces ragged half-lines.
    Prose paragraphs are joined back into one line each and let the phone wrap
    them; bullets and headings stay as they are."""
    try:
        with open(os.path.join(BRAIN, "today.md"), encoding="utf-8") as f:
            body = f.read()
    except OSError:
        return "No plan written yet."
    out, in_front, para = [], False, []

    def flush():
        if para:
            out.append(" ".join(para))
            para.clear()

    for ln in body.split("\n"):
        s = ln.strip()
        if s == "---":
            in_front = not in_front
            continue
        if in_front:
            continue
        if not s:
            flush()
            out.append("")
            continue
        if s.startswith("#") or s.startswith(("- ", "* ", "|")):
            flush()
            s = s.replace("### ", "").replace("## ", "").replace("# ", "")
            s = s.replace("- [x] ", "done  ").replace("- [ ] ", "• ")
            out.append(s)
            continue
        para.append(s)
    flush()
    return "\n".join(out).strip() or "No plan written yet."


def _plan_counts():
    """(done, still open) for the three that were planned. The two-minute
    chases are counted apart: the daily list is three items by design, and
    folding the bonus in makes a clean day read as a missed one."""
    three_done, three_open, chases_open = 0, [], 0
    section = ""
    try:
        with open(os.path.join(BRAIN, "today.md"), encoding="utf-8") as f:
            body = f.read()
    except OSError:
        return 0, [], 0
    for ln in body.split("\n"):
        s = ln.strip()
        if s.startswith("#"):
            section = s.lower()
            continue
        m = re.match(r"^[-*]\s+\[([ xX])\]\s+(.*)$", s)
        if not m or "(dropped" in m.group(2) or "(carrying" in m.group(2):
            continue
        if "chase" in section:
            if m.group(1).lower() != "x":
                chases_open += 1
            continue
        if "three" not in section and "do these" not in section:
            continue
        if m.group(1).lower() == "x":
            three_done += 1
        else:
            three_open.append(re.sub(
                r"\s*\((?:due|waiting until|urgent)[^)]*\)", "",
                m.group(2)).strip())
    return three_done, three_open, chases_open


def _morning_push(conf, cutoff=11):
    """The plan walks over to the phone once a day, after the 7am refresh.

    Nothing after the cutoff: a morning plan arriving at four in the
    afternoon is an interruption reporting a day that has already happened.
    The live bridge uses 11; the morning job passes 14, because launchd runs
    it at the first wake after a slept-through 7:00 and a plan surfacing at
    13:00 still plans the afternoon."""
    token, chat = (conf.get("token") or "").strip(), conf.get("chat_id")
    if not (token and chat):
        return
    now = datetime.now()
    today = now.date().isoformat()
    if not (7 <= now.hour < cutoff) or conf.get("plan_sent") == today:
        return
    conf["plan_sent"] = today
    _save(conf)                    # marked before sending: a crash mid-send
    # Weather first: it is the one thing that can change the order of the day
    # before she has read it, and it is one line.
    head = "Morning — today's plan:\n\n"
    try:
        import weather as WX
        w = WX.words()
        if w:
            head = "Morning — " + w + "\n\nToday's plan:\n\n"
    except Exception:
        pass
    _send(token, chat, head + _plan_text())


def _news_text():
    """brain/.news.json as a phone message: linked headlines per section,
    and the finance breakdown in full — that paragraph is the point."""
    import html as H
    try:
        with open(os.path.join(BRAIN, ".news.json"), encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return ""
    if (data.get("updated") or "")[:10] != datetime.now().date().isoformat():
        return ""                  # yesterday's paper is not worth a ping

    def sec(title, items, tail=""):
        if not items:
            return ""
        rows = [f"<b>{H.escape(title)}</b>"]
        for i in items:
            rows.append('• <a href="' + H.escape(i["link"], quote=True)
                        + f'">{H.escape(i["title"])}</a>'
                        + f' — {H.escape(i["outlet"])}')
        if tail:
            rows.append(f"<i>{H.escape(tail)}</i>")
        return "\n".join(rows)

    parts = [sec("The front page", data.get("front") or [])]
    for t in data.get("topics") or []:
        parts.append(sec(t["topic"], t["items"], t.get("explainer") or ""))
    body = "\n\n".join(p for p in parts if p)
    return "Your briefing:\n\n" + body if body else ""


def _news_push(conf, cutoff=11):
    """The morning paper to the phone, once a day, in the same window as
    the plan. Skips silently when the briefing isn't today's."""
    token, chat = (conf.get("token") or "").strip(), conf.get("chat_id")
    if not (token and chat):
        return
    now = datetime.now()
    today = now.date().isoformat()
    if not (7 <= now.hour < cutoff) or conf.get("news_sent") == today:
        return
    text = _news_text()
    if not text:
        return
    conf["news_sent"] = today
    _save(conf)                    # marked before sending, like the plan
    _send_html(token, chat, text)


def _evening_push(conf):
    """The other half of the accountability loop: the morning says what
    matters, the evening asks what happened. Once a day, after 17:30."""
    token, chat = (conf.get("token") or "").strip(), conf.get("chat_id")
    if not (token and chat):
        return
    now = datetime.now()
    today = now.date().isoformat()
    if now.hour < 17 or (now.hour == 17 and now.minute < 30) or now.hour >= 23:
        return
    if conf.get("evening_sent") == today:
        return
    conf["evening_sent"] = today
    _save(conf)
    done, open_, chases = _plan_counts()
    if not (done or open_):
        return
    # What the day actually contained, before any verdict on it. The three
    # planned tasks are one slice of a day, and a day spent entirely on
    # TapGate used to report "none of the three moved" — true about the list
    # and false about the day.
    made = ""
    try:
        import day as DAY
        d = DAY.gather()
        if d["projects"] or d["ticked"] or d["touched"] or d["drafts"]:
            made = DAY.as_text(d, phone=True)
    except Exception:
        pass
    if not open_:
        msg = f"Evening check — all {done} landed today. Clean close."
    elif done == 0:
        # A day where none of the three moved usually went somewhere else,
        # not nowhere. Ask what it turned into rather than reading the list
        # back: the fix for missing all three is a shorter list, not a
        # sterner message.
        msg = ("Evening check — none of the three moved, but the day was not "
               "empty. What did it turn into? Tell me and I'll file it, and "
               "tomorrow's list can be shorter."
               if made else
               "Evening check — none of the three moved today. What did the "
               "day turn into? Tell me and I'll file it, and tomorrow's list "
               "can be shorter.")
    else:
        msg = (f"Evening check — {done} of {done + len(open_)} done. Still open:\n"
               + "\n".join("• " + t for t in open_[:6])
               + "\n\nCarry or drop them on the page — or just tell me what "
                 "changed and I'll file it.")
    if made:
        msg += "\n\nWhat the day held:\n" + made
    if chases:
        msg += f"\n\n({chases} two-minute chase{'s' if chases > 1 else ''} still there.)"
    # Sunday evening: the coming week's sketch, if this morning wrote one —
    # read from the file, no model call.
    if now.weekday() == 6:
        try:
            with open(os.path.join(BRAIN, "week-plan.md"), encoding="utf-8") as f:
                wk = f.read()
            n = 0
            for ms in re.finditer(r"^## [^\n]*?(\d{4}-\d{2}-\d{2})[^\n]*$\n(.*?)(?=\n## |\Z)",
                                  wk, re.M | re.S):
                if ms.group(1) >= today:
                    n += len(re.findall(r"^\s*[-*]\s+\[ \]", ms.group(2), re.M))
            if n:
                msg += (f"\n\nThe coming week is sketched — {n} placed. If the "
                        "shape is wrong, drag things around on the page.")
        except Exception:
            pass
    # The evening check is the journal's front door: she is already telling
    # the day, so one line makes keeping it a reply instead of a habit.
    msg += ("\n\nWant to keep the day? Reply starting with “journal:” — or a "
            "voice note captioned “journal” — and it becomes tonight's entry, "
            "in your words.")
    # Ticking used to be the one thing that needed the laptop, which is why
    # the day so often closed unrecorded. One button per open item, straight
    # into today.md.
    _send(token, chat, msg, buttons=_tick_buttons(open_))


def _tick_buttons(open_tasks, limit=3):
    """[(label, callback)] for the still-open three. The callback carries the
    task's own hash, the same key the page uses, so a tick from the sofa and
    a tick from the page land on exactly the same line."""
    out = []
    for t in open_tasks[:limit]:
        try:
            import md as MD
            # MD.bare, not the raw text: _plan_counts has already dropped the
            # (due …) and (urgent) suffixes but keeps the ~45m estimate, and
            # serve.py hashes the fully bared line. Skip this and every tick
            # comes back "that item has changed".
            key = MD.taskkey(MD.bare(t))
        except Exception:
            continue
        _pending["tick:" + key] = t
        label = t if len(t) <= 26 else t[:24].rstrip() + "…"
        out.append(("✓ " + label, f"t:{key}"))
    return out or None


def _routine_push(conf):
    """A routine's steps, on the phone, at the hour it belongs to.

    A morning routine is a cue problem, not a memory problem: she knows what
    the steps are, she is just not standing in the bathroom thinking about
    them. So this arrives AT the hour, says the steps, and stops — no target,
    no streak, nothing to feel bad about at 07:30.

    Two rules keep it from becoming noise, which is the only way a nudge like
    this dies. It never fires for a routine already ticked today, and after
    two missed days it sends the FLOOR instead of the full list — the short
    version she can do in a hotel at 1am. A nudge for the full routine on the
    morning she is least able to do it is how the whole thing gets muted.
    """
    token, chat = (conf.get("token") or "").strip(), conf.get("chat_id")
    if not (token and chat):
        return
    try:
        import model as M
    except Exception:
        return
    now = datetime.now()
    today = now.date().isoformat()
    sent = conf.get("routine_sent") or {}
    for hb in M.load_habits():
        steps = hb.get("steps") or []
        when = hb.get("when") or ""
        if not (steps and when) or hb.get("done_today"):
            continue
        hh, mm = int(when[:2]), int(when[3:5])
        due = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
        # A 90-minute window: late enough to catch a slow start, short enough
        # that it never lands hours after the moment has passed.
        if not (due <= now < due + timedelta(minutes=90)):
            continue
        if sent.get(hb["name"]) == today:
            continue
        sent[hb["name"]] = today
        conf["routine_sent"] = sent
        _save(conf)                # marked before sending, like the others
        l14 = hb.get("last14") or []
        # Never done once is new, not slipping — see the page's note.
        slipping = (hb.get("dates_list") and len(l14) >= 3
                    and not l14[-2] and not l14[-3])
        floor = hb.get("floor") or []
        if slipping and floor:
            _send(token, chat, hb["name"] + " — short version tonight, "
                  "just these:\n\n" + "\n".join("• " + s for s in floor))
        else:
            _send(token, chat, hb["name"] + ":\n\n"
                  + "\n".join("• " + s for s in steps))


VOICE_DIR = os.path.join(BRAIN, ".voice")
MAX_VOICE_MB = 20          # the Bot API's own download ceiling
# "dump:" or "dump —" or dump on its own first line. The punctuation is what
# keeps "dump the bins" a task about bins.
DUMP_PREFIX = r"(?i)^dump\s*(?:[:,\-—]\s*|\n)"
# "journal:" the same way — the rest of the message becomes the day's journal
# entry, kept in her words. Same punctuation rule, so "journal ideas for the
# blog" stays an ordinary inbox line.
JOURNAL_PREFIX = r"(?i)^journal\s*(?:[:,\-—]\s*|\n)"
# Getting something back OUT. The colon is optional: "send me the week plan"
# is what a person types, and a fetch is read-only, so a wrong guess costs
# nothing. Anything not found is still filed, so nothing is ever lost.
FETCH_PREFIX = (r"(?i)^(?:send|share|doc|document|file|get|find)"
                r"\s*(?:[:,\-—]\s*|\s+(?:me\s+)?|\n)")
# Same for asking. It spends usage, but "ask what did I decide" is
# unambiguous enough that demanding punctuation only teaches her the bot is
# fussy.
ASK_PREFIX = r"(?i)^(?:ask|claude)\s*(?:[:,\-—]\s*|\s+|\n)"
DRAFT_PREFIX = r"(?i)^drafts?\s*(?:[:,\-—]\s*|\s+|\n|$)"
HELP_WORDS = ("help", "?", "commands", "what can you do", "how does this work")

HELP = (
    "Most of this is free — it reads your files, no model involved.\n\n"
    "FREE\n"
    "plan / done — today's three, with a tick button on each.\n"
    "tomorrow · this week · what's late · who do I owe · next\n"
    "where am I — the house, its weather, who's near, the day's size.\n"
    "habits · dinners · shopping · countdowns\n"
    "drafts — list them; “draft 2” reads one and offers Reword.\n"
    "send me the week plan — finds a file and uploads it.\n"
    "cook: chicken, tomatoes — what you can make from those.\n\n"
    "COSTS A LITTLE\n"
    "ask … — only when no lookup fits. Rewording a draft is cents.\n\n"
    "ANYTHING ELSE is filed to the inbox, and if it reads like a request "
    "you get buttons to ask or fetch instead. dump: … sorts a headful, "
    "journal: … keeps the day in your words.\n\n"
    "A voice note is transcribed on the Mac. A photo of a receipt stocks "
    "the pantry and teaches the meal planner what you buy.")

# Bare messages that read like a request rather than a note to self. These do
# not trigger anything: they add two buttons to the "Filed" reply, so the
# answer to "do I have to phrase it right?" is no, just tap.
REQUEST_RX = re.compile(
    r"(?i)^(?:can you|could you|please|what|who|when|where|why|how|which|"
    r"give|show|write|draft|make|remind|tell me|do i|did i|is there|"
    r"are there|summar)|\?\s*$")

# callback_data is capped at 64 bytes, so the message itself cannot ride in
# it. Short-lived ids, kept only for as long as the bridge is up.
_pending = {}
# The last few turns, so "can you give it to me?" has an antecedent. Without
# this the bot answered "give you what exactly?" to a question whose subject
# was one message above it. Text only, in memory, never written to disk.
_recent = []


def _remember(who, text):
    _recent.append(f"{who}: {text.strip()[:400]}")
    del _recent[:-6]


def _history():
    return "\n".join(_recent[:-1]) if len(_recent) > 1 else ""


def _voice_part(msg):
    """The audio in a message, whatever shape Telegram sent it in: a held-
    button voice note, a forwarded audio file, a round video note, or an
    audio file dragged in as a document."""
    for key in ("voice", "audio", "video_note"):
        if msg.get(key):
            return msg[key], key
    doc = msg.get("document") or {}
    if str(doc.get("mime_type") or "").startswith(("audio/", "video/")):
        return doc, "document"
    return None, ""


PHOTO_DIR = os.path.join(BRAIN, "files", "telegram")   # gitignored


def _photo_part(msg):
    """The image in a message: a compressed photo (largest size) or an
    image file sent as a document."""
    sizes = msg.get("photo") or []
    if sizes:
        return sizes[-1]
    doc = msg.get("document") or {}
    if str(doc.get("mime_type") or "").startswith("image/"):
        return doc
    return None


def _download_photo(token, part):
    """Telegram photo → brain/files/telegram/ (kept out of git). The queued
    ask carries this path so the next Claude session can Read the image."""
    info = _api(token, "getFile", file_id=part["file_id"])
    path = ((info.get("result") or {}).get("file_path") or "")
    if not path:
        raise RuntimeError("Telegram would not hand over the file")
    os.makedirs(PHOTO_DIR, exist_ok=True)
    ext = os.path.splitext(path)[1] or ".jpg"
    dest = os.path.join(
        PHOTO_DIR, f"photo-{datetime.now().strftime('%Y-%m-%d-%H%M%S')}{ext}")
    url = f"https://api.telegram.org/file/bot{token}/{path}"
    with urllib.request.urlopen(url, timeout=120) as r, open(dest, "wb") as f:
        while True:
            chunk = r.read(65536)
            if not chunk:
                break
            f.write(chunk)
    return dest


RECEIPT_WORDS = ("receipt", "ticket", "caisse", "courses", "groceries")


def _photo_ask(caption, path):
    """The queue item a photo becomes. A receipt gets the kitchen workflow;
    anything else is filed by its caption."""
    cap = (caption or "").lower()
    if not caption or any(w in cap for w in RECEIPT_WORDS):
        return ("Grocery receipt photo from Telegram"
                + (f' (caption: "{caption}")' if caption else "")
                + ". Read the image, then: add what she bought to the Fresh "
                  "list in brain/cooking/pantry.md (short generic names — "
                  "'chicken thighs', not brands); tick any matching items on "
                  "brain/cooking/shopping.md; rebuild with "
                  "brain/tools/cook.py. In the Outcome, list what she bought "
                  "and 2–3 dinners it unlocks (dorm-friendly ones if the "
                  "kitchen is set to dorm). Never log food as eaten — "
                  "Satio tracks eating; this only stocks the kitchen.")
    return (f'Photo from Telegram, captioned "{caption}". The caption is '
            "her instruction — file or act on it, and say what you did "
            "in the Outcome.")


"""Fetching a file back out of the brain.

The bridge could only ever put things IN: every message that was not a
command got filed and answered "Filed ✓". Asking for a document she wrote
last week was indistinguishable from dumping a thought. These two functions
are the other direction, and they are deliberately mechanical — a search over
names and contents, no Claude call, no cost."""

# Folders worth searching, in the order a person would look. The journal is
# absent on purpose: it is private, and a message asking for "the doc about
# X" must never post an entry of hers into a chat.
FETCH_DIRS = ["drafts", "files", "daily", "rooms", "cooking", "reference",
              "queue", ""]
FETCH_SKIP = {"journal", "recipes-library", "transcripts", "sessions",
              "archive", "fonts", "art", "avatars"}
FETCH_EXT = {".md", ".txt", ".pdf", ".csv", ".json", ".html", ".png", ".jpg",
             ".jpeg", ".docx", ".xlsx", ".ics"}
# Dependency and build trees in the project folders — never where a document
# she named by hand lives, and walking them would make every fetch crawl.
FETCH_SKIP_HEAVY = {"node_modules", "dist", "build", "out", "coverage",
                    "venv", ".venv", "__pycache__", "Pods", "DerivedData",
                    ".next", "target", "vendor"}


def _source_dirs():
    """The synced project folders from config.json. She names her project
    docs herself (a renovation folder's numbered files, say) and asks for
    the fetch must see them. Read-only, best effort: a broken config must
    not break fetching the brain's own files."""
    try:
        with open(os.path.join(BRAIN, "config.json"), encoding="utf-8") as f:
            cfg = json.load(f)
    except Exception:
        return []
    repo = os.path.dirname(BRAIN)
    out = []
    for src in cfg.get("sources", []):
        p = os.path.abspath(os.path.expanduser(src.get("path", "") or ""))
        # the brain lists itself as a source; it is already searched above
        if p and p != repo and os.path.isdir(p):
            out.append(p)
    return out


def _source_dirs():
    """The project folders config.json points at. Her renovation plans, the
    school folder, the app repos: the document she asks for by name is far
    more often in one of these than in brain/ itself, and leaving them out
    was why "the Isa and Tatum split" came back empty while Claude found
    it in seconds. Read-only, like every other use of sources."""
    out = []
    try:
        with open(os.path.join(BRAIN, "config.json"), encoding="utf-8") as f:
            cfg = json.load(f)
    except Exception:
        return out
    for s in cfg.get("sources") or []:
        p = os.path.expanduser((s or {}).get("path") or "")
        if p and os.path.isdir(p):
            out.append(p)
    return out


# Heavy folders a document search must never walk into.
SRC_SKIP = {".git", "node_modules", "venv", ".venv", "__pycache__", "build",
            "dist", "target", ".next", "Pods", ".gradle", "DerivedData",
            "site-packages", ".cache", "coverage"}


def _fetch_candidates():
    out = []
    for base in _source_dirs():
        for root, dirs, files in os.walk(base):
            dirs[:] = [d for d in dirs
                       if d not in SRC_SKIP and not d.startswith(".")]
            if root[len(base):].count(os.sep) > 3:
                dirs[:] = []                   # deep trees are code, not docs
            for fn in files:
                if fn.startswith(".") or os.path.splitext(fn)[1].lower() \
                        not in FETCH_EXT:
                    continue
                out.append(os.path.join(root, fn))
            if len(out) > 4000:
                break
    for sub in FETCH_DIRS:
        base = os.path.join(BRAIN, sub) if sub else BRAIN
        if not os.path.isdir(base):
            continue
        for root, dirs, files in os.walk(base):
            dirs[:] = [d for d in dirs
                       if d not in FETCH_SKIP and not d.startswith(".")]
            rel_root = os.path.relpath(root, BRAIN)
            if any(p in FETCH_SKIP for p in rel_root.split(os.sep)):
                continue
            for fn in files:
                if fn.startswith(".") or os.path.splitext(fn)[1].lower() \
                        not in FETCH_EXT:
                    continue
                out.append(os.path.join(root, fn))
            if not sub:
                break                      # the brain root itself, not all of it
    for base in _source_dirs():
        for root, dirs, files in os.walk(base):
            dirs[:] = [d for d in dirs
                       if d not in FETCH_SKIP_HEAVY and not d.startswith(".")]
            for fn in files:
                if fn.startswith(".") or os.path.splitext(fn)[1].lower() \
                        not in FETCH_EXT:
                    continue
                out.append(os.path.join(root, fn))
    return out


def _find_files(query, limit=5):
    """Score every candidate on the query's words. A hit in the filename is
    worth far more than one in the body, because she names things for herself
    and then asks for them by that name."""
    words = [w for w in re.split(r"[^a-z0-9à-ÿ]+", query.lower()) if len(w) > 2]
    stop = {"the", "and", "doc", "document", "file", "about", "for", "with",
            "send", "share", "give", "get", "wrote", "made", "created", "that",
            "one", "you", "please", "can", "from", "our", "les", "des", "sur"}
    words = [w for w in words if w not in stop]
    if not words:
        return []
    scored, seen_paths = [], set()
    for path in _fetch_candidates():
        # life-brain is itself one of the configured sources, so brain files
        # arrive twice — once from the source walk, once from FETCH_DIRS.
        real = os.path.realpath(path)
        if real in seen_paths:
            continue
        seen_paths.add(real)
        name = os.path.basename(path).lower()
        # the caption she sees: brain files relative to brain/, project
        # files as ~/… — never a ../../ crumb trail
        if path.startswith(BRAIN + os.sep):
            rel = os.path.relpath(path, BRAIN)
        else:
            home = os.path.expanduser("~")
            rel = "~" + path[len(home):] if path.startswith(home) else path
        score = 0
        for w in words:
            if w in name:
                score += 10
        if score or len(words) > 1:
            body = ""
            try:
                if os.path.getsize(path) < 400_000 and \
                        os.path.splitext(path)[1].lower() in {
                            ".md", ".txt", ".csv"}:
                    with open(path, encoding="utf-8", errors="ignore") as f:
                        body = f.read(120_000).lower()
            except OSError:
                body = ""
            if body:
                for w in words:
                    c = body.count(w)
                    if c:
                        score += min(4, 1 + c // 8)
        if all(w in name for w in words):
            score += 8                     # every word in the name beats a stray
        # A body mention or two is not a match: without a floor, "the doc
        # about X" happily returns inbox.md because the word appears once.
        if score >= 8:
            scored.append((score, os.path.getmtime(path), rel, path))
    scored.sort(key=lambda x: (-x[0], -x[1]))
    return scored[:limit]


def _open_drafts():
    """[(filename, to, task, body)] for drafts still waiting to be sent."""
    out = []
    ddir = os.path.join(BRAIN, "drafts")
    if not os.path.isdir(ddir):
        return out
    for fn in sorted(os.listdir(ddir)):
        if not fn.endswith(".md"):
            continue
        try:
            with open(os.path.join(ddir, fn), encoding="utf-8") as f:
                raw = f.read()
        except OSError:
            continue
        m = re.match(r"^---\n(.*?)\n---\n(.*)$", raw, re.S)
        if not m:
            continue
        front, body = m.group(1), m.group(2).strip()
        meta = dict(re.findall(r"^([a-z_]+):\s*(.*)$", front, re.M))
        if (meta.get("status") or "draft").lower() not in ("draft", "ready"):
            continue
        out.append((fn, meta.get("person") or meta.get("to") or "",
                    meta.get("task") or "", body))
    return out


def _draft_card(i, d):
    fn, who, task, body = d
    head = f"{i}. {who or fn[:-3]}"
    if task:
        head += f"\n   for: {task}"
    return head + "\n\n" + (body if len(body) < 2500 else body[:2500] + "…")


MENU = [
    ("plan", "Today's three, with tick buttons"),
    ("done", "What's left today, tap to tick"),
    ("tomorrow", "What's on tomorrow"),
    ("week", "The week's sketch"),
    ("late", "What's past its date"),
    ("people", "Who you owe a reply, who's gone quiet"),
    ("next", "Worth your next free hour"),
    ("where", "Which house, its weather, the day's size"),
    ("drafts", "Drafts waiting, and reword one"),
    ("dinners", "This week's dinners"),
    ("shopping", "What's still on the list"),
    ("habits", "This week's counts"),
    ("help", "Everything you can say"),
]


def _publish_menu(token, conf):
    """Register the commands so Telegram shows its own Menu button. This is
    the honest answer to "how am I supposed to talk to it": she taps a list
    instead of remembering keywords. Once per token."""
    if conf.get("menu_v") == 2:
        return
    try:
        _api(token, "setMyCommands", commands=json.dumps(
            [{"command": c, "description": d} for c, d in MENU]))
        conf["menu_v"] = 2
        _save(conf)
    except Exception:
        pass


def _mechanical(query, strict=False):
    """The free lookup, tried before anything is filed or asked. Import is
    local so a broken answers.py can never take the bridge down with it."""
    try:
        import answers
        return answers.answer(query, strict=strict)
    except Exception:
        return None


def _cook_reply(query):
    """'cook: chicken, tomatoes' → top matches from her own cookbooks,
    straight from the index. Mechanical, instant, costs nothing."""
    try:
        import cook as C
        have = [w.strip().lower() for w in re.split(r"[,;+]| and ",
                                                    query) if w.strip()]
        if not have:
            return "Tell me what's in the kitchen: cook: chicken, tomatoes"
        pantry = C.load_pantry()
        words = have + [w.strip().lower()
                        for w in pantry["staples"] + pantry["fresh"]]
        dorm = pantry.get("kitchen") == "dorm"
        scored = []
        for r in C.index():
            if r["cat"] in C.NOT_A_MEAL or len(r["n"]) < 3:
                continue
            if dorm and not r["dorm"]:
                continue
            miss = [n for n in r["n"] if not C._pantry_has(n, words)]
            used = sum(1 for n in r["n"] if C._pantry_has(n, have))
            if len(miss) <= 1 and used:
                t = r.get("tot") or r.get("m")
                scored.append((len(miss), -used, t or 999, r, miss))
        scored.sort(key=lambda x: x[:3])
        if not scored:
            return ("Nothing close with just that — add an ingredient or "
                    "two, or browse the Cook page.")
        out = []
        for len_miss, _, _, r, miss in scored[:5]:
            t = r.get("tot") or r.get("m")
            line = f"• {r['t']} — {r['b']}"
            if t:
                line += f", {t} min" if t < 90 else f", {round(t / 60, 1)} h"
            if miss:
                line += f" (need: {miss[0]})"
            out.append(line)
        return ("From your cookbooks tonight:\n" + "\n".join(out)
                + "\n\nFull recipes on the Cook page.")
    except Exception:
        return "The recipe index isn't available right now — try the Cook page."


def _download(token, part, kind):
    """Telegram file → a local path under brain/.voice. Returns the path."""
    info = _api(token, "getFile", file_id=part["file_id"])
    path = ((info.get("result") or {}).get("file_path") or "")
    if not path:
        raise RuntimeError("Telegram would not hand over the file")
    os.makedirs(VOICE_DIR, exist_ok=True)
    ext = os.path.splitext(path)[1] or (".ogg" if kind == "voice" else ".m4a")
    # The transcript takes its name from this one and already carries the
    # date, so the file itself only needs the time.
    dest = os.path.join(VOICE_DIR,
                        f"{kind}-{datetime.now().strftime('%H%M%S')}{ext}")
    url = f"https://api.telegram.org/file/bot{token}/{path}"
    with urllib.request.urlopen(url, timeout=120) as r, open(dest, "wb") as f:
        while True:
            chunk = r.read(65536)
            if not chunk:
                break
            f.write(chunk)
    return dest


def run(capture_fn, rebuild_fn, voice_fn=None, dump_fn=None, ask_fn=None,
        tick_fn=None, draft_fn=None):
    """The loop serve.py runs as a daemon thread. Idles on five-minute checks
    until a token appears in brain/.telegram.json, so it costs nothing to
    always start.

    `voice_fn(path, meta, reply)` is handed a downloaded recording and takes
    it from there (transcribe, file, delete the audio); it is optional so the
    bridge still runs on a machine with no transcriber. `dump_fn(text, mode)`
    queues a message to be worked rather than left as an inbox line — mode
    "dump" to be sorted into the brain, "journal" to be kept as the day's
    entry."""
    offset = 0
    while True:
        conf = _load()
        token = (conf.get("token") or "").strip()
        if not token:
            time.sleep(300)
            continue
        if not conf.get("chat_id") and not conf.get("pair_code"):
            # Mint the pairing code the moment there's a token to pair
            # against, and rebuild so the Connections card shows it.
            conf["pair_code"] = f"{secrets.randbelow(900000) + 100000}"
            _save(conf)
            try:
                rebuild_fn()
            except Exception:
                pass
        _publish_menu(token, conf)
        try:
            resp = _api(token, "getUpdates", offset=offset, timeout=50)
        except Exception:
            # Offline, bad token, a second poller (409): the poll can fail
            # for days, and the daily pushes must not die with it — this
            # `continue` used to skip them, which is how a running server
            # still delivered no morning plan.
            try:
                _morning_push(conf)
                _news_push(conf)
                _evening_push(conf)
                _routine_push(conf)
            except Exception:
                pass
            time.sleep(30)
            continue
        for up in resp.get("result", []):
            offset = max(offset, up.get("update_id", 0) + 1)
            # A tap on "Ask Claude" or "Find a file" under a filed message.
            cb = up.get("callback_query")
            if cb:
                try:
                    _api(token, "answerCallbackQuery",
                         callback_query_id=cb.get("id"))
                    cchat = ((cb.get("message") or {}).get("chat")
                             or {}).get("id")
                    if cchat != conf.get("chat_id"):
                        continue
                    kind_, _, key = (cb.get("data") or "").partition(":")
                    original = _pending.get(key)
                    if not original:
                        _send(token, cchat, "That one has aged out — send it "
                                            "again with “ask” or “send” in "
                                            "front.")
                    elif kind_ == "f":
                        hits = _find_files(original)
                        if hits:
                            _send_document(token, cchat, hits[0][3],
                                           caption=hits[0][2])
                        else:
                            _send(token, cchat,
                                  "No file here matches that. Tap Ask Claude "
                                  "instead and it can write you one.")
                    elif kind_ == "r":
                        fn = _pending.get("draft:" + key)
                        if not fn:
                            _send(token, cchat, "That draft has aged out — "
                                                "send “drafts” again.")
                        else:
                            _pending["reword"] = fn
                            _send(token, cchat,
                                  "What should change? Your next message is "
                                  "the instruction — “warmer”, “cut the last "
                                  "paragraph”, “say Thursday not Friday”.")
                    elif kind_ == "t":
                        if not tick_fn:
                            _send(token, cchat, "No writer on this machine.")
                            continue
                        label = _pending.get("tick:" + key, "that")
                        try:
                            tick_fn(key)
                            rebuild_fn()
                            done_n, still, _ = _plan_counts()
                            tail = (f"{done_n} done, {len(still)} to go."
                                    if still else
                                    f"All {done_n} landed. Clean close.")
                            _send(token, cchat, f"✓ {label}\n{tail}",
                                  buttons=_tick_buttons(still))
                        except Exception as exc:        # noqa: BLE001
                            _send(token, cchat,
                                  f"Couldn't tick that: {exc}")
                    elif kind_ == "a" and ask_fn:
                        _send(token, cchat, "Thinking — this costs a little "
                                            "usage. I'll answer here.")
                        ask_fn(original, lambda m, f=None, c=cchat: (
                            _send(token, c, m) if not f
                            else _send_document(token, c, f, caption=m[:900])),
                               _history())
                except Exception:
                    pass
                continue
            msg = up.get("message") or {}
            chat = (msg.get("chat") or {}).get("id")
            text = (msg.get("text") or msg.get("caption") or "").strip()
            # Telegram's Menu button sends "/plan", "/where", "/late". They
            # are the same words the router already understands, so the
            # slash is simply dropped rather than given its own dispatch.
            if re.match(r"^/[a-z_]+(@\w+)?\b", text, re.I):
                text = re.sub(r"^/([a-z_]+)(@\w+)?", r"\1", text, flags=re.I).strip()
                if text.lower() in ("start", "menu"):
                    text = "help"
            part, kind = _voice_part(msg)
            photo = _photo_part(msg)
            if chat is None or not (text or part or photo):
                continue
            try:
                if not conf.get("chat_id"):
                    # Bot usernames are public: adoption needs the code from
                    # the Connections card, and wrong guesses get silence —
                    # a stranger can't even learn the bot is live.
                    if text.strip() != (conf.get("pair_code") or ""):
                        continue
                    conf["chat_id"] = chat
                    conf.pop("pair_code", None)
                    # A pairing at ten at night should not be answered with
                    # this morning's plan and an evening scorecard: today's
                    # two pushes are counted as spent, and tomorrow starts
                    # the rhythm properly.
                    stamp = datetime.now().date().isoformat()
                    conf["plan_sent"] = stamp
                    conf["evening_sent"] = stamp
                    _save(conf)
                    _send(token, chat,
                          "Paired ✓ — this chat now feeds your brain. Type "
                          "anything and it lands in the inbox; send a voice "
                          "note and it gets transcribed on the Mac and turned "
                          "into tasks; caption one “met …” after meeting "
                          "someone and they become a tracked contact with "
                          "follow-ups already dated; send “plan” for today's "
                          "plan. To get something back: “send: the Isa "
                          "note” finds the file and uploads it, and “ask: …” "
                          "puts the question to Claude and answers here.")
                    continue
                if chat != conf["chat_id"]:
                    continue       # not the owner: silence, always
                if text:
                    _remember("her", text)
                if part:
                    if not voice_fn:
                        _send(token, chat, "No transcriber on this machine — "
                                           "send it as text and I'll file it.")
                        continue
                    mb = (part.get("file_size") or 0) / 1e6
                    if mb > MAX_VOICE_MB:
                        _send(token, chat,
                              f"That's {mb:.0f}MB and Telegram only hands over "
                              f"{MAX_VOICE_MB}MB — drop it in Downloads and "
                              "transcribe it from the page instead.")
                        continue
                    _send(token, chat, "Got it — transcribing on the Mac. "
                                       "I'll message when it's filed.")
                    path = _download(token, part, kind)
                    voice_fn(path, {"seconds": part.get("duration") or 0,
                                    "caption": text, "kind": kind},
                             lambda m: _send(token, chat, m))
                elif photo:
                    mb = (photo.get("file_size") or 0) / 1e6
                    if mb > 19:
                        _send(token, chat,
                              f"That's {mb:.0f}MB and Telegram only hands "
                              "over 20MB — send it as a compressed photo.")
                        continue
                    if not dump_fn:
                        _send(token, chat, "No queue on this machine — "
                                           "photos can't be filed here.")
                        continue
                    ppath = _download_photo(token, photo)
                    dump_fn(_photo_ask(text, ppath), "just-do-it",
                            files=[ppath])
                    cap = (text or "").lower()
                    is_receipt = (not text
                                  or any(w in cap for w in RECEIPT_WORDS))
                    _send(token, chat,
                          ("Receipt saved ✓ — queued: the next Claude run "
                           "stocks the pantry from it and ticks the "
                           "shopping list.") if is_receipt else
                          "Photo saved ✓ — queued with your caption as "
                          "the instruction.")
                elif text.lower().startswith(("cook:", "cook ")) \
                        and len(text) > 5:
                    _send(token, chat, _cook_reply(text[5:]))
                elif text.lower() in ("plan", "today"):
                    done_n, still, _ = _plan_counts()
                    _send(token, chat, _plan_text(),
                          buttons=_tick_buttons(still))
                elif text.strip().lower() in ("done", "tick", "ticked",
                                              "what's left", "whats left",
                                              "left"):
                    done_n, still, chases = _plan_counts()
                    if not still:
                        _send(token, chat,
                              f"All {done_n} are ticked."
                              + (f" {chases} chase(s) still open."
                                 if chases else ""))
                    else:
                        _send(token, chat,
                              f"{done_n} done, {len(still)} left. Tap to tick.",
                              buttons=_tick_buttons(still))
                elif re.match(DRAFT_PREFIX, text):
                    rest = re.sub(DRAFT_PREFIX, "", text).strip()
                    drafts = _open_drafts()
                    if not drafts:
                        _send(token, chat, "No drafts waiting.")
                    elif not rest:
                        _send(token, chat,
                              "Drafts waiting:\n\n" + "\n".join(
                                  f"{i}. {d[1] or d[0][:-3]}"
                                  + (f" — {d[2]}" if d[2] else "")
                                  for i, d in enumerate(drafts, 1)) +
                              "\n\nSend “draft 2” to read one.")
                    else:
                        m = re.match(r"^(\d+)\s*(.*)$", rest, re.S)
                        idx = int(m.group(1)) - 1 if m else -1
                        if not (0 <= idx < len(drafts)):
                            _send(token, chat, f"There are {len(drafts)}.")
                        else:
                            d = drafts[idx]
                            key = secrets.token_hex(4)
                            _pending["draft:" + key] = d[0]
                            _send(token, chat, _draft_card(idx + 1, d),
                                  buttons=[("Reword it", f"r:{key}")])
                elif _pending.get("reword") and draft_fn:
                    # Her previous message tapped Reword; this one is the
                    # instruction. Consumed either way, so a second stray
                    # message cannot silently rewrite a draft.
                    fn = _pending.pop("reword")
                    _send(token, chat, "Rewording — a small model, cents.")
                    try:
                        new = draft_fn(fn, text)
                        _send(token, chat, "Rewritten ✓\n\n" + new)
                    except Exception as exc:            # noqa: BLE001
                        _send(token, chat, f"That rewrite failed: {exc}")
                elif re.match(FETCH_PREFIX, text):
                    q = re.sub(FETCH_PREFIX, "", text).strip()
                    hits = _find_files(q)
                    if not hits:
                        # The colon is optional now, so "send Marie the
                        # invoice" reaches here as a fetch. Filing it anyway
                        # is what stops a real note being swallowed by a
                        # search that found nothing.
                        capture_fn(text)
                        rebuild_fn()
                        key = secrets.token_hex(4)
                        _pending[key] = q
                        _send(token, chat,
                              "No file here matches that, so I filed it "
                              "instead.",
                              buttons=[("Ask Claude", f"a:{key}")])
                    else:
                        top = hits[0]
                        _send_document(token, chat, top[3], caption=top[2])
                        if len(hits) > 1:
                            _send(token, chat, "Also close: " +
                                  ", ".join(h[2] for h in hits[1:4]) +
                                  " — say the name to get one of those.")
                elif re.match(ASK_PREFIX, text):
                    # Even an explicit "ask" gets the free lookup first: most
                    # of what she types is a question the files already
                    # answer, and paying a model to re-read today.md is
                    # paying for a grep.
                    q = re.sub(ASK_PREFIX, "", text).strip()
                    free = _mechanical(q)
                    if free:
                        _send(token, chat, free)
                    elif not q:
                        _send(token, chat, "Ask me what?")
                    elif ask_fn:
                        _send(token, chat, "Nothing canned fits that, so I'm "
                                           "asking Claude. Costs a little.")
                        ask_fn(q, lambda m, f=None: (
                            _send(token, chat, m) if not f
                            else _send_document(token, chat, f, caption=m[:900])),
                               _history())
                    else:
                        _send(token, chat, "No Claude on this machine.")
                elif re.match(JOURNAL_PREFIX, text) and dump_fn:
                    dump_fn(re.sub(JOURNAL_PREFIX, "", text).strip(), "journal")
                    rebuild_fn()
                    _send(token, chat, "Journaled ✓ — kept as the day's "
                                       "entry, in your words. The next "
                                       "session folds it into the brain.")
                elif re.match(DUMP_PREFIX, text) and dump_fn:
                    # Everything after the marker: an inbox line waits for the
                    # next triage as one line, a dump gets taken apart. The
                    # punctuation is required so "dump the bins" stays a task.
                    dump_fn(re.sub(DUMP_PREFIX, "", text).strip())
                    rebuild_fn()
                    _send(token, chat, "Dumped ✓ — queued to be sorted into "
                                       "the brain, questions and all.")
                elif text.strip().lower().rstrip("?") in HELP_WORDS \
                        or text.strip().lower() in HELP_WORDS:
                    _send(token, chat, HELP)
                else:
                    # A free lookup beats both filing and asking. Strict
                    # unless it already reads as a question, so "call the
                    # plumber tomorrow" stays a task about the plumber.
                    looks_asked = bool(REQUEST_RX.search(text.strip()))
                    free = _mechanical(text, strict=not looks_asked)
                    if free:
                        _send(token, chat, free)
                        continue
                    # Then try the file search, unprefixed. "give me the
                    # isa and tatum file" is the commonest thing she
                    # types and it needed a keyword she had to remember;
                    # searching is free, so there is no reason to make her.
                    if looks_asked:
                        hits = _find_files(text)
                        if hits and hits[0][0] >= 18:
                            _send_document(token, chat, hits[0][3],
                                           caption=hits[0][2])
                            continue
                    capture_fn(text)
                    rebuild_fn()
                    # Filing is right for a note to self and wrong for a
                    # request, and the bot cannot tell which without spending
                    # money to find out. So it files either way and offers the
                    # two other readings as taps.
                    if looks_asked and len(text) < 700:
                        key = secrets.token_hex(4)
                        _pending[key] = text.strip()
                        for old in list(_pending)[:-40]:
                            _pending.pop(old, None)
                        _send(token, chat,
                              "Filed ✓ — that reads like a request, though.",
                              buttons=[("Ask Claude", f"a:{key}"),
                                       ("Find a file", f"f:{key}")])
                    else:
                        _send(token, chat, "Filed ✓")
            except Exception:
                pass               # one bad message never kills the bridge
        try:
            _morning_push(conf)
        except Exception:
            pass
        try:
            _news_push(conf)
        except Exception:
            pass
        try:
            _evening_push(conf)
            _routine_push(conf)
        except Exception:
            pass


if __name__ == "__main__":
    # `--push-plan`: the morning job's own delivery path. The in-server
    # bridge only pushes while serve.py happens to be running in the 7-11
    # window; launchd runs the morning job at 7:00 OR at the first wake
    # after, so this is the arm that actually reaches the phone on a
    # slept-through morning. The shared plan_sent stamp stops double sends.
    import sys
    if "--push-plan" in sys.argv:
        _c = _load()
        _before = _c.get("plan_sent")
        try:
            _morning_push(_c, cutoff=14)
        except Exception as _ex:                        # noqa: BLE001
            print("plan push failed:", _ex)
        else:
            print("plan push:", "sent" if _load().get("plan_sent") != _before
                  else "already sent, unpaired, or out of window")
    if "--push-news" in sys.argv:
        _c = _load()
        _before = _c.get("news_sent")
        try:
            _news_push(_c, cutoff=14)
        except Exception as _ex:                        # noqa: BLE001
            print("news push failed:", _ex)
        else:
            print("news push:", "sent" if _load().get("news_sent") != _before
                  else "already sent, unpaired, stale, or out of window")

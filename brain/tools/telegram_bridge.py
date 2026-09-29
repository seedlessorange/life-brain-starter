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
     card; a fresh one every half hour, or after five wrong tries).
     Message that code to your bot from a one-to-one chat — only the chat
     that sends the exact code is ever adopted; every other sender gets silence,
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
    # The file holds the bot token: owner-only from the first byte, and
    # chmod again after the swap in case an older file was wider.
    tmp = CONF + ".tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(conf, f, indent=2)
    os.replace(tmp, CONF)
    os.chmod(CONF, 0o600)


# Six digits is a million guesses, which is only safe if the guessing
# window is short: a code lives half an hour, and five wrong tries retire
# it early.
PAIR_TTL = 30 * 60
PAIR_TRIES = 5


def _mint_pair(conf):
    conf["pair_code"] = f"{secrets.randbelow(900000) + 100000}"
    conf["pair_at"] = int(time.time())
    conf["pair_misses"] = 0


def _pair_expired(conf):
    try:
        return time.time() - float(conf.get("pair_at") or 0) > PAIR_TTL
    except (TypeError, ValueError):
        return True


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
            # A flat list is one row; a list of lists is several rows.
            rows = buttons if isinstance(buttons[0], list) else [buttons]
            extra["reply_markup"] = json.dumps({"inline_keyboard": [
                [{"text": lbl, "callback_data": cb} for lbl, cb in row]
                for row in rows]})
        # No link previews, ever: Telegram's servers fetch any URL in the
        # text to build one, with no tap from her — and the morning plan is
        # written by a run that reads strangers' calendar invites. A link a
        # run planted would otherwise carry whatever it put in the address.
        _api(token, "sendMessage", chat_id=chat_id, text=chunk,
             disable_web_page_preview="true", **extra)


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


def _send_voice(token, chat_id, path):
    """A voice note back to her own chat: the brain answering out loud.
    `path` is an OGG/Opus file (voice.synth makes one); Telegram plays
    anything else as a plain audio file instead of a voice bubble."""
    with open(path, "rb") as f:
        blob = f.read()
    if len(blob) > 49 * 1024 * 1024:
        return False
    boundary = "----brain" + hashlib.md5(blob[:2048]).hexdigest()[:16]
    body = (f'--{boundary}\r\nContent-Disposition: form-data; '
            f'name="chat_id"\r\n\r\n{chat_id}\r\n'
            f'--{boundary}\r\nContent-Disposition: form-data; name="voice"; '
            f'filename="reply.ogg"\r\nContent-Type: audio/ogg\r\n\r\n'
            ).encode() + blob + f"\r\n--{boundary}--\r\n".encode()
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendVoice", data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.load(r).get("ok", False)


def _replier(token, chat_id):
    """What a voice note's handler answers through: words, a file, or a
    voice note — any of the three, in that order."""
    def reply(m="", f=None, audio=None):
        if f:
            _send_document(token, chat_id, f, caption=(m or "")[:900])
        elif m:
            _send(token, chat_id, m)
        if audio:
            _send_voice(token, chat_id, audio)
    return reply


def _send_html(token, chat_id, text):
    """HTML mode for the briefing, so headlines are tappable links. Splits
    on paragraph boundaries — a mid-tag split makes Telegram reject the
    whole message — and mutes link previews, or every story grows a card.
    Telegram's 4096 limit counts the text she sees, not the link addresses
    behind it, so that is what gets measured."""
    import html as H

    def seen(s):
        return len(H.unescape(re.sub(r"<[^>]+>", "", s)))
    chunk = ""
    for para in text.split("\n\n"):
        if chunk and seen(chunk) + seen(para) + 2 > 3900:
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

    import md as MD
    for ln in body.split("\n"):
        s = MD.SHORT.sub("", ln)
        # The moment rides on her phone in words, not brackets: the 07:00
        # message is where an if-then plan meets its day.
        s = MD.AT.sub(lambda a: " — " + a.group(1)
                      + (", " + a.group(2).strip() if a.group(2) else ""),
                      s).strip()
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
    import md as MD
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
                r"\s*\((?:due|waiting until|urgent|short:)[^)]*\)", "",
                MD.AT.sub("", m.group(2))).strip())
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
    body = head + _plan_text()
    try:
        import school_brief as SB
        blk = SB.morning()
        if blk:
            body += "\n\n" + blk
    except Exception:
        pass
    # The briefing rides in the same message when it is ready: batched
    # deliveries beat a stream of pings for attention and mood (Fitz et al.
    # 2019), and 07:00 used to be two arrivals. When it isn't ready yet it
    # follows on its own, as before.
    news = ""
    if conf.get("news_sent") != today:
        try:
            news = _news_text()
        except Exception:
            news = ""
    if news:
        import html as H
        conf["news_sent"] = today
        _save(conf)
        _send_html(token, chat, H.escape(body) + "\n\n" + news)
    else:
        _send(token, chat, body)


def _news_url():
    """The News tab at the address her phone can open (Tailscale's name for
    this Mac), or None when the page isn't reachable from the phone."""
    try:
        import serve
        name = serve.tailnet_dns_name()
    except Exception:
        return None
    return f"https://{name}/#/news" if name else None


def _news_text():
    """brain/.news.json as one phone message: the front page, the lead story
    of each topic, and each learning topic's breakdown folded shut with its
    term left showing — the paragraph is the point, but thirty links and two
    open paragraphs were two screens of scrolling. On Sunday the week's recap
    takes the daily paragraphs' place. Everything else is on the News tab,
    linked at the end."""
    import html as H
    try:
        with open(os.path.join(BRAIN, ".news.json"), encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return ""
    now = datetime.now()
    today = now.date().isoformat()
    if (data.get("updated") or "")[:10] != today:
        return ""                  # yesterday's paper is not worth a ping

    def story(i):
        return ('• <a href="' + H.escape(i["link"], quote=True)
                + f'">{H.escape(i["title"])}</a> — {H.escape(i["outlet"])}')

    def folded(text):
        # An expandable quote shows its first lines and opens on a tap.
        body = "\n".join(p.strip() for p in text.splitlines() if p.strip())
        return f"<blockquote expandable>{H.escape(body)}</blockquote>"

    recaps = [r for r in data.get("recaps") or []
              if r.get("on") == today and r.get("text")]
    parts = []
    front = data.get("front") or []
    if front:
        parts.append("<b>The front page</b>\n" + "\n".join(map(story, front)))
    for t in data.get("topics") or []:
        if not t["items"]:
            continue
        rows = [f"<b>{H.escape(t['topic'])}</b>", story(t["items"][0])]
        exp = t.get("explainer") or ""
        if exp and not recaps:
            m = re.search(r"^\s*(Term worth knowing:.*)$", exp, flags=re.M)
            rows.append(folded(exp[:m.start()] if m else exp))
            if m:
                rows.append(f"<i>{H.escape(m.group(1).strip())}</i>")
        parts.append("\n".join(rows))
    for r in recaps:
        parts.append(f"<b>The week in {H.escape(r['topic'])}</b>\n"
                     + folded(r["text"]))
    if not parts:
        return ""
    url = _news_url()
    if url:
        parts.append(f'<a href="{H.escape(url, quote=True)}">'
                     "The rest of today’s briefing</a>")
    day = now.strftime("%A %d %B").replace(" 0", " ")
    return f"<b>Your briefing — {day}</b>\n\n" + "\n\n".join(parts)


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


def _update_times():
    """When the evening asks for the daily update, and when it asks once
    more. config.json `daily_update`: {"at": "20:30", "remind": "22:30"} —
    late enough that the day is over on a class night."""
    try:
        with open(os.path.join(BRAIN, "config.json"), encoding="utf-8") as f:
            du = json.load(f).get("daily_update") or {}
    except Exception:
        du = {}
    def mins(s, dflt):
        m = re.match(r"(\d{1,2})[:h.](\d{2})", str(s or ""))
        return int(m.group(1)) * 60 + int(m.group(2)) if m else dflt
    return mins(du.get("at"), 20 * 60 + 30), mins(du.get("remind"), 22 * 60 + 30)


def _updated_today():
    try:
        import model as M
        return datetime.now().date() in M.update_days(since_days=1)
    except Exception:
        return False


def _evening_push(conf):
    """The other half of the accountability loop: the morning says what
    matters, the evening asks what happened.

    It leads with the ask for the daily update (her call, 24 Sep): the brain
    sees the laptop and nothing else, so a voice note about the day is the
    only way calls, conversations and things done in person ever reach it.
    The scorecard follows. Once a day, at `daily_update.at`."""
    token, chat = (conf.get("token") or "").strip(), conf.get("chat_id")
    if not (token and chat):
        return
    now = datetime.now()
    today = now.date().isoformat()
    at, _remind = _update_times()
    if now.hour * 60 + now.minute < at or now.hour >= 23:
        return
    if conf.get("evening_sent") == today:
        return
    conf["evening_sent"] = today
    _save(conf)
    done, open_, chases = _plan_counts()
    shorts = _shorts()

    def _still(ts):
        import md as MD
        out = []
        for t in ts[:6]:
            out.append("• " + t)
            sv = shorts.get(MD.taskkey(MD.bare(t)))
            if sv:
                out.append("   ↘ short version: " + sv)
        return "\n".join(out)
    asked = not _updated_today()
    ask = (UPDATE_HEAD + " — send me a voice note: what happened today and "
           "what's next. Most of all, what happened away from the laptop, "
           "because the brain can't see that on its own. I'll tick what's "
           "done and fold the rest in overnight. (Reply to this message, or "
           "caption it “journal” to keep it as your journal instead.)")
    habits = _habit_buttons(now)
    habit_line = ("Habits you haven't ticked today — tap the ones you did."
                  if habits else "")
    if not (done or open_):
        text = "\n\n".join(t for t in (ask if asked else "", habit_line) if t)
        if text:
            _send(token, chat, text, buttons=_button_rows(None, habits))
        return
    # What the day actually contained, before any verdict on it. The three
    # planned tasks are one slice of a day, and a day spent entirely on
    # A day on one app used to report "none of the three moved" — true about the list
    # and false about the day.
    made = ""
    try:
        import day as DAY
        d = DAY.gather()
        if d["projects"] or d["ticked"] or d["touched"] or d["drafts"]:
            made = DAY.as_text(d, phone=True)
    except Exception:
        pass
    if asked:
        msg = ask + "\n\n" + (
            "Today's plan: nothing left open." if not open_ else
            f"Today's three: {done} of {done + len(open_)} done. Still open:\n"
            + _still(open_))
    elif not open_:
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
               + _still(open_)
               + "\n\nSay when each one happens instead — or just tell "
                 "me what changed and I'll file it.")
    if made:
        msg += ("\n\nWhat the brain already saw today:\n" if asked
                else "\n\nWhat the day held:\n") + made
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
    # the day, so one line makes keeping it a reply instead of a habit. When
    # the update ask leads, its own last line already says this.
    if not asked:
        msg += ("\n\nWant to keep the day? Reply starting with “journal:” — "
                "or a voice note captioned “journal” — and it becomes "
                "tonight's entry, in your words.")
    # Ticking used to be the one thing that needed the laptop, which is why
    # the day so often closed unrecorded. One button per open item, straight
    # into today.md, and one per habit not ticked yet.
    if habit_line:
        msg += "\n\n" + habit_line
    _send(token, chat, msg,
          buttons=(_task_rows(open_) + (_button_rows(None, habits) or []))
          or None)


def _update_reminder(conf):
    """One more ask, at `daily_update.remind`, only if the evening message
    went out and no update came back. Once, then silence: a second nudge is
    a reminder, a third is how a bot gets muted."""
    token, chat = (conf.get("token") or "").strip(), conf.get("chat_id")
    if not (token and chat):
        return
    now = datetime.now()
    today = now.date().isoformat()
    _at, remind = _update_times()
    if now.hour * 60 + now.minute < remind:
        return
    if conf.get("evening_sent") != today or conf.get("update_nudged") == today:
        return
    conf["update_nudged"] = today
    _save(conf)
    if _updated_today():
        return
    ask = (UPDATE_HEAD + " — still open for today. One voice note, a minute "
           "is plenty, and tomorrow's plan starts from what actually "
           "happened. Reply to this message.")
    # The evening routine's reminder falls in the same minute (both 22:30),
    # and two arrivals at once is one too many (Fitz et al. 2019). The ask
    # leads: a reply counts as the update because the message it answers
    # starts "Daily update".
    due = _routines_due(conf, now)
    if not due:
        _send(token, chat, ask)
        return
    sent = conf.get("routine_sent") or {}
    for hb in due:
        sent[hb["name"]] = today
    conf["routine_sent"] = sent
    _save(conf)
    parts, buttons = [ask], []
    for hb in due:
        text, btn = _routine_message(hb, now)
        parts.append(text)
        buttons += btn
    _send(token, chat, "\n\n".join(parts), buttons=buttons)


def _school_push(conf):
    """Tomorrow at school, the evening before: classes, readings, guest
    speakers, what is due, and whether today's slides made it in. Once a day
    from 18:30, before a volleyball night leaves the house; silent on an
    evening with nothing school-shaped ahead (Sunday always sends, as the
    week's opener)."""
    token, chat = (conf.get("token") or "").strip(), conf.get("chat_id")
    if not (token and chat):
        return
    now = datetime.now()
    today = now.date().isoformat()
    if not ((now.hour == 18 and now.minute >= 30) or 19 <= now.hour < 23):
        return
    if conf.get("school_sent") == today:
        return
    conf["school_sent"] = today
    _save(conf)                    # marked before sending, like the others
    try:
        import school_brief as SB
        msg = SB.evening(now.date())
    except Exception:
        return
    if msg:
        _send(token, chat, msg)


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


def _habit_key(name):
    """A habit's short id for a button. callback_data is capped at 64 bytes;
    a hash of the name, matched against habits.md at tap time, also survives
    a server restart, which a _pending entry would not."""
    return hashlib.sha1(name.encode("utf-8")).hexdigest()[:10]


def _habit_buttons(now):
    """[(label, callback)] for the habits not ticked today, for the evening
    message. Until 28 Sep only the routines had a phone path (their own
    reminder's Done), so most habits needed the laptop, and she does about
    half of them without logging. Left out: habits that count themselves
    (journal, updates), and a routine whose own reminder is still to come
    tonight, since that one brings its own Done."""
    try:
        import model as M
        habits = M.load_habits()
    except Exception:
        return []
    hm, ymd = f"{now:%H:%M}", f"{now:%Y%m%d}"
    out = []
    for hb in habits:
        if hb.get("done_today") or hb.get("auto") or not hb.get("target"):
            continue
        if hb.get("steps") and (hb.get("when") or "") > hm:
            continue
        name = hb["name"]
        label = name if len(name) <= 22 else name[:20].rstrip() + "…"
        out.append(("✓ " + label, f"h:{_habit_key(name)}:{ymd}"))
    return out


def _button_rows(tasks, habits):
    """Keyboard rows: a task to a row, where its label has room; habits two
    to a row, since their names are short."""
    rows = [[b] for b in (tasks or [])]
    hs = habits or []
    rows += [hs[i:i + 2] for i in range(0, len(hs), 2)]
    return rows or None


def _shorts():
    """{task key: its short version} for today's open plan tasks — the
    `(short: …)` the morning plan puts on each of the three."""
    import md as MD
    try:
        with open(os.path.join(BRAIN, "today.md"), encoding="utf-8") as f:
            body = f.read()
    except OSError:
        return {}
    out = {}
    for ln in body.split("\n"):
        m = re.match(r"^\s*[-*]\s+\[ \]\s+(.*)$", ln)
        ms = MD.SHORT.search(m.group(1)) if m else None
        if ms and ms.group(1).strip():
            out[MD.taskkey(MD.bare(m.group(1)))] = ms.group(1).strip()
    return out


def _batch_day():
    """The weekly hour's day from config `now.batch` ("Friday"), or ""."""
    try:
        with open(os.path.join(BRAIN, "config.json"), encoding="utf-8") as f:
            now_ = json.load(f).get("now") or {}
        return str((now_.get("batch") or {}).get("day") or "").strip().title()
    except Exception:
        return ""


def _task_rows(open_tasks, limit=3):
    """Each open task of the three: its tick on one row, and under it when
    it happens instead — Tomorrow (the page's Carry), the weekly hour, or
    Let it go (off today's plan; the task itself stays in its project).
    Deciding when an unfinished task will happen quiets it nearly as well as
    finishing it (Masicampo & Baumeister 2011), and the page's Carry and
    Drop needed the laptop."""
    day = _batch_day()
    rows = []
    for lbl, cb in _tick_buttons(open_tasks, limit) or []:
        key = cb[2:]
        rows.append([(lbl, cb)])
        rows.append([("Tomorrow", f"p:{key}:t")]
                    + ([(f"{day} hour", f"p:{key}:b")] if day else [])
                    + [("Let it go", f"p:{key}:x")])
    return rows


def _replan_tap(token, chat, key, replan_fn, rebuild_fn):
    """A tap on Tomorrow / the weekly hour / Let it go. `replan_fn` is
    serve.py's, so the page and the phone move a task the same way."""
    if not replan_fn:
        _send(token, chat, "No writer on this machine.")
        return
    tk, _, op = key.rpartition(":")
    label = _pending.get("tick:" + tk, "")
    try:
        said = replan_fn(tk, op)
        rebuild_fn()
    except Exception as exc:                            # noqa: BLE001
        _send(token, chat, f"Couldn't move that: {exc}")
        return
    _send(token, chat, said + (f"\n{label}" if label else ""))


def _habit_tap(token, chat, kind_, key, habit_fn, rebuild_fn):
    """Done ("h") logs a habit for the day its reminder was about; Undo
    ("u") takes it back. Both set rather than toggle, so a Done tapped after
    a tick on the page never quietly unticks it."""
    if not habit_fn:
        _send(token, chat, "No writer on this machine.")
        return
    hk, _, ymd = key.partition(":")
    try:
        import model as M
        hb = next((h for h in M.load_habits()
                   if _habit_key(h["name"]) == hk), None)
        day = datetime.strptime(ymd, "%Y%m%d").date()
    except Exception:
        hb = day = None
    if not (hb and day):
        _send(token, chat, "That habit has changed since. Tick it on the "
                           "page instead.")
        return
    on = kind_ == "h"
    try:
        habit_fn(hb["name"], day, on)
        rebuild_fn()
    except Exception as exc:                            # noqa: BLE001
        _send(token, chat, f"Couldn't log that: {exc}")
        return
    when = ("" if day == datetime.now().date()
            else " for {0:%a} {0.day} {0:%b}".format(day))
    if on:
        _send(token, chat, f"✓ {hb['name']} logged{when}.",
              buttons=[("Undo", f"u:{key}")])
    else:
        _send(token, chat, f"{hb['name']} unticked{when}.")


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
    now = datetime.now()
    today = now.date().isoformat()
    sent = conf.get("routine_sent") or {}
    for hb in _routines_due(conf, now):
        sent[hb["name"]] = today
        conf["routine_sent"] = sent
        _save(conf)                # marked before sending, like the others
        text, buttons = _routine_message(hb, now)
        _send(token, chat, text, buttons=buttons)


def _routines_due(conf, now):
    """Routines whose hour is now, not ticked today, not yet reminded."""
    try:
        import model as M
        habits = M.load_habits()
    except Exception:
        return []
    today = now.date().isoformat()
    sent = conf.get("routine_sent") or {}
    out = []
    for hb in habits:
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
        out.append(hb)
    return out


def _routine_message(hb, now):
    """(text, buttons) for one routine's reminder."""
    # Slipping, or the first days in a new house: model.py decides.
    steps = hb.get("steps") or []
    floor = hb.get("floor") or []
    show = floor if hb.get("floor_day") else steps
    head = (" — short version today, just these:" if show is floor
            else ":")
    # Done logs it from where she already is: half her habits were
    # happening and going unlogged (28 Sep) because a tick meant the
    # laptop. The button carries the day, so a tap the morning after
    # still logs the evening it was about.
    return (hb["name"] + (", " + hb["cue"] if hb.get("cue") else "") + head
            + "\n\n" + "\n".join("• " + s for s in show),
            [("✓ Done", f"h:{_habit_key(hb['name'])}:{now:%Y%m%d}")])

VOICE_DIR = os.path.join(BRAIN, ".voice")
MAX_VOICE_MB = 20          # the Bot API's own download ceiling
# "dump:" or "dump —" or dump on its own first line. The punctuation is what
# keeps "dump the bins" a task about bins.
DUMP_PREFIX = r"(?i)^dump\s*(?:[:,\-—]\s*|\n)"
UPDATE_PREFIX = r"(?i)^update\s*(?:[:,\-—]\s*|\n)"
UPDATE_HEAD = "Daily update"


def _replies_to_update(msg):
    """A reply to the evening message is the update, whatever it says."""
    return ((msg.get("reply_to_message") or {}).get("text") or "") \
        .startswith(UPDATE_HEAD)
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
    "school — classes, readings, guest speakers, what's due.\n"
    "where am I — the house, its weather, who's near, the day's size.\n"
    "habits · dinners · shopping · countdowns\n"
    "drafts — list them; “draft 2” reads one and offers Reword.\n"
    "send me the week plan — finds a file and uploads it.\n"
    "cook: chicken, tomatoes — what you can make from those.\n\n"
    "COSTS A LITTLE\n"
    "ask … — only when no lookup fits. Rewording a draft is cents.\n\n"
    "ANYTHING ELSE is filed to the inbox, and if it reads like a request "
    "you get buttons to ask or fetch instead. dump: … sorts a headful, "
    "update: … is the daily update (so is any reply to the evening "
    "message), journal: … keeps the day in your words.\n\n"
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
                  "her food-tracking app does that; this only stocks the kitchen.")
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
    was why "the Perry and Arden split" came back empty while Claude found
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
        tick_fn=None, draft_fn=None, habit_fn=None, replan_fn=None):
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
        if (not conf.get("chat_id") and conf.get("pair_code")
                and not conf.get("pair_at")):
            # The server mints a code when the token is saved, without a
            # time on it: the half hour starts when the bridge first sees it.
            conf["pair_at"] = int(time.time())
            _save(conf)
        elif not conf.get("chat_id") and (not conf.get("pair_code")
                                          or _pair_expired(conf)):
            # Mint the pairing code the moment there's a token to pair
            # against (or the old one ran out), and rebuild so the
            # Connections card shows it.
            _mint_pair(conf)
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
                _update_reminder(conf)
                _school_push(conf)
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
                    # Only Find and Ask keep the message itself in _pending.
                    # Tick and Reword file theirs under a prefix and Done
                    # carries its habit in the button; gating those on
                    # `original` answered every tap "aged out" (31 Aug-28 Sep).
                    if kind_ in ("f", "a") and not original:
                        _send(token, cchat, "That one has aged out — send it "
                                            "again with “ask” or “send” in "
                                            "front.")
                    elif kind_ in ("h", "u"):
                        _habit_tap(token, cchat, kind_, key, habit_fn,
                                   rebuild_fn)
                    elif kind_ == "p":
                        _replan_tap(token, cchat, key, replan_fn, rebuild_fn)
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
                    # a stranger can't even learn the bot is live. Only a
                    # one-to-one chat can be adopted: a group's chat id would
                    # hand the brain to everyone in the group.
                    if ((msg.get("chat") or {}).get("type") != "private"
                            or (msg.get("from") or {}).get("id") != chat):
                        continue
                    guess = text.strip()
                    if (not guess or guess != (conf.get("pair_code") or "")
                            or _pair_expired(conf)):
                        if guess.isdigit():
                            conf["pair_misses"] = int(conf.get("pair_misses") or 0) + 1
                            if conf["pair_misses"] >= PAIR_TRIES:
                                _mint_pair(conf)
                                _save(conf)
                                try:
                                    rebuild_fn()
                                except Exception:
                                    pass
                            else:
                                _save(conf)
                        continue
                    conf["chat_id"] = chat
                    for k in ("pair_code", "pair_at", "pair_misses"):
                        conf.pop(k, None)
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
                          "plan. To get something back: “send: the Perry "
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
                    # Someone else's voice, forwarded in: filed like any
                    # forward, never answered as if she had asked it.
                    fwd = bool(msg.get("forward_origin") or msg.get("forward_from")
                               or msg.get("forward_sender_name")
                               or msg.get("forward_date"))
                    upd = _replies_to_update(msg)
                    short_ask = ((part.get("duration") or 0) <= 60 and not fwd
                                 and not upd and (not text or re.match(
                                     r"(?i)^(?:ask|claude|question)\b", text)))
                    _send(token, chat, "Got it — listening." if short_ask else
                          "Got it — transcribing on the Mac. "
                          "I'll message when it's filed.")
                    path = _download(token, part, kind)
                    voice_fn(path, {"seconds": part.get("duration") or 0,
                                    "caption": text, "kind": kind,
                                    "update": upd, "forwarded": fwd},
                             _replier(token, chat))
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
                elif (re.match(UPDATE_PREFIX, text)
                      or _replies_to_update(msg)) and dump_fn:
                    import model as M
                    dump_fn(M.DAILY_UPDATE_PRE + "\n\nWhat she wrote: "
                            + re.sub(UPDATE_PREFIX, "", text).strip(), "dump")
                    rebuild_fn()
                    _send(token, chat, "Update filed ✓ — the 01:00 run folds "
                                       "it in before the morning plan, or tap "
                                       "Run now on the page.")
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
                    # perry and arden file" is the commonest thing she
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
            _update_reminder(conf)
            _school_push(conf)
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

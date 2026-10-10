"""The Under the Hood tab: build()'s UNDER THE HOOD section, in its own file.

build() calls render() where the section used to sit, passing what the
sections above it worked out; render() returns what the ones below read.
The page helpers come from build.py, so run the page with build.py.
"""

from datetime import datetime
from datetime import timedelta
import agents as AG
import json
import md as MD
import model as M
import os
import re
import usage as USAGE

from build import (BRAIN, _calblock_row, _mailread_row, _mailtasks_row, _tid,
    ask_label, clip, conn_allow, draft_label, draftcard, e, iso_prose, linkify_html,
    palette_chips, style_chips, tray_item, writingcard)


def _dm(iso):
    """A visible date, day first: "2026-09-27" -> "27 Sep"."""
    d = M.parse_date((iso or "")[:10])
    return f"{d.day} {d:%b}" if d else (iso or "")


# What each night job does, in the words its own button uses — the Settings
# row and the Usage page said "/queue, /wrap, /scout" (28 Sep review).
NIGHT_WORDS = {"queue": "works your queue", "wrap": "tidies the brain",
               "scout": "looks for things to do", "brief": "catches you up",
               "discover": "scans your project folders",
               "sync": "reads your project folders"}


def night_plain(jobs):
    """"works your queue, tidies the brain and looks for things to do"."""
    words = [NIGHT_WORDS.get(j, j) for j in (jobs or ["queue"])]
    return (", ".join(words[:-1]) + " and " + words[-1]
            if len(words) > 1 else words[0])


def _draft_chip(d):
    """What a draft is, in two words, for its row in For you."""
    kind, ch = (d.get("kind") or "").lower(), (d.get("channel") or "").lower()
    if kind == "email" or ch == "email":
        return "Email draft"
    if ch == "linkedin":
        return "LinkedIn draft"
    if kind == "message":
        said = " ".join([d.get("task") or "", d.get("subject") or "",
                         (d.get("body") or "")[:300]]).lower()
        return "WhatsApp draft" if "whatsapp" in said else "Message draft"
    if kind == "form":
        return "Form answers"
    return "Note"


def render(V, cfg, hood_inbox, hood_ref, parked_qhtml, pending, q, today,
           tray_confirm, tray_read, tray_send):
    # The Claude tab dissolved on 28 Sep ("The brain, redrawn", decisions.md).
    # Talking to Claude is the box, on every page. What Claude hands back is
    # For you, on Today: drafts to send, finished work to read. What is left —
    # the jobs and their runs, the connections, the look, the brain's own
    # memory — is machinery, and it lives here, behind the gear.
    ai = "careful" if cfg.get("ai") in ("low", "careful", "pro") else "full"
    import build as _B
    # Presenting (privacy.py): no drafts on the page at all, since a card
    # carries the subject, the recipient and the words.
    drafts = [] if _B.PRESENTING else M.load_drafts(today=today)
    email_default = (cfg.get("email") or {}).get("default", "")
    email_ready = bool(email_default)
    # Each fresh draft is its own Send line in For you, its card one click
    # down with every control it had (Copy, Open in email, the per-message
    # approval for work contacts; personal circles stay copy-only, in code).
    # Newest first (9 Oct, her ask): the draft she just asked for sat fourth,
    # under three older ones, because the files sort by name. Its created
    # date first, then when the file last changed.
    def _newest(d):
        try:
            mt = os.path.getmtime(os.path.join(BRAIN, "drafts", d["file"]))
        except OSError:
            mt = 0
        return (d.get("created") or "", mt)
    for d in sorted(drafts, key=_newest, reverse=True):
        if d.get("stale"):
            continue
        who = d.get("person") or d.get("to") or ""
        # A note is read, not sent: three plan notes filled For you's five
        # Send lines and folded every question the page asks (10 Oct).
        kind = "read" if d.get("kind") == "note" else "send"
        (tray_read if kind == "read" else tray_send).append(tray_item(
            _tid("d", d["file"]), kind,
            (d.get("task") or d.get("subject") or d.get("title")
             or draft_label(d["file"])),
            draftcard(d, email_ready, email_default),
            sub=("to " + who) if who else "", chip=_draft_chip(d)))
    # The ones the page folded away — their date passed, their task closed,
    # or two weeks unsent — are the brain's memory now, not a decision.
    oldies = [d for d in drafts if d.get("stale")]
    hood_olddrafts = ""
    if oldies:
        hood_olddrafts = (
            '<details class="refblock"><summary>Older drafts'
            f'<span class="reffresh">{len(oldies)}</span></summary>'
            + "".join(draftcard(d, email_ready, email_default) for d in oldies)
            + "</details>")

    # The voice guide: part of the brain's memory of her.
    hood_memory = [writingcard()]

    V["hood"].append(
        '<section class="hoodhead"><p class="eyebrow">Under the hood</p>'
        '<h2>How the brain runs</h2></section>')
    V["hood"].append('<section id="queue" class="hoodsec">'
                     '<h3 class="area">Jobs and runs</h3>')
    # The four verbs ARE the page: a blank box asking you to invent a request
    # is harder to face than buttons that already know what you want.
    # And each button answers the question every button row invites — "am I
    # supposed to press this every day?" — with when it last ran and whether
    # it ran itself. From the ledger, not the run history: the history only
    # keeps the last 20 page runs, and the 7am/night runs never land there.
    def _job_runs():
        last = {}
        try:
            for r in USAGE.load(days=365):
                if not r.get("ok") or r.get("kind") not in ("run", "morning",
                                                           "night"):
                    continue
                lbl = (r.get("label") or "").strip()
                auto = r.get("kind") in ("morning", "night")
                base = lbl.rsplit("/", 1)[-1].strip() if auto else lbl
                last[base] = (r.get("at") or "", auto)
        except Exception:
            pass
        return last

    _runs_by_job = _job_runs()

    def _ranline(job):
        at, auto = _runs_by_job.get(job, ("", False))
        if not at:
            return "not run yet"
        d, tm = at[:10], at[11:16]
        if d == today.isoformat():
            when = "today at " + tm
        elif d == (today - timedelta(days=1)).isoformat():
            when = "yesterday"
        else:
            when = _dm(d)
        return ("ran itself " if auto else "you ran it ") + when

    n_pending = len(pending)
    qcount_label = (f"{n_pending} waiting" if n_pending else "nothing waiting")

    def _job(job, name, tip):
        # Name plus one faint line — when it last ran, which answers "am I
        # meant to press this?". The description lives in the tooltip.
        return (f'<button class="jobbtn" data-job="{job}" title="{tip}">{name}'
                f'<span class="jobwhen">{_ranline(job)}</span></button>')
    # Asking moved into the box; these are the jobs themselves.
    V["hood"].append(f"""
<div class="asker needs-server">
  <div class="jobrow jobrow3">
    <button id="askrun" class="jobbtn jobqueue{' hot' if n_pending else ''}" title="Start {AG.label()} here and work through everything waiting">Work the queue<span id="qcount" class="jobwhen">{qcount_label}</span></button>
    {_job("brief", "Catch me up", "The whole brain, in plain language. Good after a few days away.")}
    {_job("today", "Refresh today&rsquo;s plan", "Rewrites the three from the brain as it stands. Runs itself every morning at 7.")}
  </div>
  <details class="morejobs"><summary>More jobs</summary>
  <div class="jobrow jobrow3">
    {_job("wrap", "Tidy the brain", "Files strays, catches stale or contradictory entries. The night shift runs this too.")}
    {_job("discover", "Scan my project folders", "Finds new work on this Mac. It only reads, so run it any time.")}
    {_job("scout", "Find things to do", "Searches the web for concerts and nights out that match your taste. It runs weekly on its own and never books anything.")}
    {_job("audit", "Ask me what&rsquo;s missing", AG.say("Claude hunts the missing facts that make the ranking wrong; they become questions on Today."))}
  </div></details>
  <div id="agentfeed" class="feed" hidden></div>
  <div id="runhistory" class="runs"></div>
</div>""")

    _qlabel = ask_label

    def _qcard(item):
        # Done cards lead with the payload: the Outcome in full size, the
        # original ask folded away, and no status chip — "done" on every
        # card carries no information. Anything not-done keeps its chip.
        label = _qlabel(item)
        chip = ("" if item["status"] == "done" else
                f'<span class="v v-{"wait" if item["status"] == "pending" else "mine" if item["status"] == "working" else "unk"}">{e(item["status"])}</span> ')
        out = [f'<div class="qitem q-{e(item["status"])}"'
               f' data-qfile="{e(item["file"])}">'
               f'<div class="qhead">{chip}<b>{e(label)}</b>'
               f'<span class="qdate">{e(_dm(item["created"]))}</span></div>']
        if item["outcome"]:
            out.append('<div class="qout qoutfirst">'
                       + linkify_html(MD.render(item["outcome"])) + "</div>")
        if item["body"]:
            out.append('<details class="qask"><summary>what you asked</summary>'
                       f'<div class="qbody">{MD.render(item["body"])}</div></details>')
        if item["status"] == "done" and item["outcome"].strip():
            # An Outcome is the end of a thread that often has more in it.
            # This opens a conversation already holding the ask and the answer.
            out.append('<button class="qcont" data-qcont='
                       f'"{e(item["file"])}">Carry on in a conversation '
                       "&#8594;</button>")
        out.append("</div>")
        return iso_prose("".join(out))       # her ask and its title, day-first too

    if pending:
        # The queue the buttons talk about, visible — not a black box.
        V["hood"].append(
            f'<h3 class="area hoodsub">In the queue <span class="csub">{n_pending}</span></h3>'
            '<div class="qlist">' + "".join(_qcard(item) for item in pending)
            + "</div>")
    finished = [x for x in q if x["status"] in ("done", "dropped")]
    finished.sort(key=lambda x: (x["created"] or "", x["file"]), reverse=True)

    def _isq(item):
        # Her own answers being filed — receipts of something she already
        # did, never reading. The page's answer boxes word them like this.
        t = (item["title"] or "").lower()
        return (item["status"] == "done"
                and (t.startswith("answer")
                     or t.startswith("a question in brain/questions.md now carries")
                     or t.startswith("a task now carries her answer")))
    # What Claude finished lately is a Read line in For you, until she says
    # she has it. Filed answers to her own questions are receipts, not
    # reading, and stay out.
    _seen = set(cfg.get("tray_seen") or [])
    _cut3 = (today - timedelta(days=3)).isoformat()
    for item in finished:
        if len(tray_read) >= 6:
            break
        if (item["status"] != "done" or not (item["outcome"] or "").strip()
                or _isq(item) or (item["created"] or "")[:10] < _cut3):
            continue
        tid = _tid("r", item["file"])
        if tid in _seen:
            continue
        _title = _qlabel(item, 90)
        if _title.lower().startswith("i rambled these notes"):
            # The wrapper the ramble button writes says nothing; the day
            # she rambled does.
            _d = M.parse_date((item["created"] or "")[:10])
            if _d:
                _title = f"Your notes from {_d.day} {_d:%b}, filed"
        tray_read.append(tray_item(
            tid, "read", _title,
            '<div class="qout">' + linkify_html(MD.render(item["outcome"]))
            + '</div><div class="tracts needs-server">'
            f'<button class="mini" data-trayseen="{e(tid)}">Got it</button>'
            f'<button class="mini qcont" data-qcont="{e(item["file"])}">Carry on'
            " in a conversation &rarr;</button></div>"))
    # Documents the brain made lately — a transcript, a study guide, a Word
    # file — are reading too. Open shows it in the box's Files, where it can
    # be edited or opened in its own app. Message drafts are already Send
    # lines, and her project folders' own files are hers, not news.
    try:
        import docs as DOCS
        _cutd = (datetime.now() - timedelta(days=3)).timestamp()
        _new = [d for d in DOCS.index()
                if d["mtime"] >= _cutd and d["kind"] != "Project file"
                and not (d["kind"] == "Draft" and d["ext"] == ".md")]
        # Three or more of one kind inside two minutes is a re-render of the
        # lot (every guide restyled at once), not something new to read.
        _batch = {}
        for d in _new:
            k = (d["kind"], int(d["mtime"] // 120))
            _batch[k] = _batch.get(k, 0) + 1
        _nd = 0
        for d in _new:
            if _nd >= 4:
                break
            if _batch[(d["kind"], int(d["mtime"] // 120))] >= 3:
                continue
            tid = "f:" + d["id"]
            if tid in _seen:
                continue
            _nd += 1
            tray_read.append(tray_item(
                tid, "read", f'{d["kind"]}: {d["name"]}',
                '<div class="tracts needs-server">'
                f'<button class="mini go" data-openfile="{e(d["id"])}">Open</button>'
                f'<button class="mini" data-trayseen="{e(tid)}">Got it</button></div>',
                sub=d["where"]))
    except Exception:                                   # noqa: BLE001
        pass
    if finished:
        # The whole archive, folded: newest first, runs of filed answers as
        # one line each.
        cards = []
        i3 = 0
        while i3 < len(finished):
            item = finished[i3]
            if _isq(item):
                j3 = i3
                while (j3 < len(finished) and _isq(finished[j3])
                       and finished[j3]["created"][:10] == item["created"][:10]):
                    j3 += 1
                grp = finished[i3:j3]
                if len(grp) >= 3:
                    cards.append(
                        f'<details class="ghost qgroup"><summary>{len(grp)} questions '
                        f'answered <span class="qdate">{e(_dm(item["created"]))}</span>'
                        "</summary>" + "".join(_qcard(x) for x in grp) + "</details>")
                    i3 = j3
                    continue
            cards.append(_qcard(item))
            i3 += 1
        V["hood"].append(
            '<details class="ghost qgroup hoodfold" id="finished"><summary>What '
            f'{AG.short()} finished <span class="csub">{len(finished)}</span></summary>'
            '<div class="qlist">' + "".join(cards) + "</div></details>")
    V["hood"].append("</section>")
    # Fix and improve (8 Oct): check the brain, change it, undo a change,
    # pack an improvement. The doors a terminal used to be the only way to.
    import tab_fix
    V["hood"].append(tab_fix.section())

    # ---- Connections: every channel the brain has, with its live state and
    # the way in. These existed but hid behind conditions (mail setup only
    # appeared when a draft was stuck); a channel you can't find is a channel
    # that doesn't exist.
    tg = {}
    try:
        with open(os.path.join(BRAIN, ".telegram.json"), encoding="utf-8") as f:
            tg = json.load(f)
    except Exception:
        pass
    try:
        import email_send as _es
        mail_accts = _es.accounts()
    except Exception:
        mail_accts = []
    cal_on = bool(cfg.get("calendar"))
    conn = []
    # Every row ends in conn_allow(): what it can and can't do, the risk,
    # and the way out, checked against the code on 8 Oct. Three rows had
    # promised less than the code does (the app password "can only send",
    # Telegram "can never start a job", the calendar "never leaves this
    # Mac" while its titles go into the morning plan's Claude run).
    # Beeper: Connect and Disconnect live on the row (8 Oct). The People
    # page's sync shows only once it is connected, so this is the way in.
    try:
        import beeper as _beep
        _bee_on = _beep.connected()
    except Exception:
        _bee_on = False
    _bee_allow = conn_allow(
        ("Set up", "" if _bee_on else "Keep Beeper Desktop open on this "
         "Mac, press Connect and approve the brain in the page that opens. "
         "It asks for reading only."),
        ("It can", "See the name of every chat and when it last moved. For "
         "people on your list it also looks at the last ten messages to tell "
         "who wrote last; code checks the words and throws them away, and no "
         "model sees them."),
        ("It can&rsquo;t", "Send by itself. A message goes only when you "
         "press send on a draft, and drafts to family and friends get Copy "
         "only."),
        ("Risk", "The key opens every chat in Beeper while Beeper is open. "
         "It sits in your Mac&rsquo;s Keychain, where a program running as "
         "you could use it to read them."),
        ("To stop", "Disconnect: Beeper cancels the key and this Mac deletes "
         "its copy. Quitting Beeper pauses it."))
    _bs = ""
    try:
        _bm = os.path.getmtime(os.path.join(BRAIN, ".beeper-review.json"))
        _bd2 = datetime.now() - datetime.fromtimestamp(_bm)
        _bs = ("just now" if _bd2.total_seconds() < 3600 else
               f"{int(_bd2.total_seconds() // 3600)}h ago" if _bd2.days == 0 else
               f"{_bd2.days}d ago")
    except Exception:
        pass
    conn.append(
        '<div class="connrow needs-server"><i class="cdot'
        + (" on" if _bee_on else "") + '"></i><b>Beeper</b><span>'
        + ((f"Synced {_bs}. Runs itself each morning. " if _bs else
            "Connected. It syncs each morning. ")
           + '<button class="mini" id="bee-off">Disconnect</button>'
           if _bee_on else
           "Off. &ldquo;Last spoke&rdquo; dates stay manual. "
           '<button class="mini" id="bee-on">Connect</button>')
        + '<span class="mshelp" id="bee-help"></span>'
        + _bee_allow + '</span></div>')
    # Telegram — three states: paired, token-awaiting-first-message, nothing.
    _tg_allow = conn_allow(
        ("Set up", "" if tg.get("chat_id") else "In Telegram, message <b>@BotFather</b>, send "
         "<code>/newbot</code>, pick any name and paste the token it gives "
         "you here. Then send your bot the six-digit code that appears on "
         "this row."),
        ("It can", "File whatever you send into your inbox, send you the "
         "plan and the evening check, answer questions from your files and "
         "upload a file you ask for. Questions and long messages start a "
         f"{AG.short()} run, which spends your plan."),
        ("It can&rsquo;t", "Hear anyone but the private chat that paired. A "
         "run it starts is fenced like every other: it can&rsquo;t send "
         "anything or change the brain&rsquo;s code."),
        ("Risk", "Bot chats aren&rsquo;t end-to-end encrypted, so what the "
         "brain sends you, plans and files included, is stored on "
         "Telegram&rsquo;s servers. Whoever gets into your Telegram account "
         "can ask the brain about your life."),
        ("To stop", "Disconnect, and the brain forgets the bot within a "
         "minute. The token itself works until you message @BotFather, send "
         "<code>/revoke</code> and pick your bot."))
    _tg_off = ('<button class="mini" id="tg-off">Disconnect</button>'
               '<span class="mshelp" id="tg-help"></span>')
    if tg.get("chat_id"):
        conn.append('<div class="connrow needs-server"><i class="cdot on"></i>'
                    '<b>Telegram</b><span>Paired with your own chat. The plan '
                    'arrives mornings, the check evenings. ' + _tg_off
                    + _tg_allow + '</span></div>')
    elif tg.get("token"):
        _pc = tg.get("pair_code") or ""
        conn.append('<div class="connrow needs-server"><i class="cdot wait"></i>'
                    '<b>Telegram</b><span>Token saved. To pair, send '
                    + (f'the code <b class="paircode">{e(_pc)}</b>' if _pc
                       else 'the pairing code (it appears here within a '
                            'minute, then refresh)')
                    + ' to your bot in Telegram. Only the chat that sends it '
                    'is ever listened to. ' + _tg_off + _tg_allow
                    + '</span></div>')
    else:
        conn.append(
            '<div class="connrow needs-server"><i class="cdot"></i><b>Telegram</b>'
            '<span>Off. Message the brain from your phone once this is set up.'
            '<span class="connform"><input id="tg-token" autocomplete="off"'
            ' placeholder="123456789:AAF...">'
            '<button class="mini" id="tg-connect">Connect</button>'
            '<span class="mshelp" id="tg-help"></span></span>'
            + _tg_allow + '</span></div>')
    # Mail — accounts listed; the add form always reachable, not draft-gated.
    # The flow is written as numbered steps with the provider's own settings
    # page one click away, because "app password" is jargon until the page
    # that mints one is in front of you.
    # Each address is a chip with its own Disconnect, like Task mail's.
    mrows = " ".join(
        f'<span class="mtchip">{e(a["address"])}<button class="mtx" '
        f'data-mailrm="{e(a["address"])}" title="Disconnect this account">'
        '&times;</button></span>' for a in mail_accts)
    # The app password is full mailbox access (IMAP and SMTP); Mail in
    # reads with the same one. Touch ID is what keeps it behind her.
    _tid_mail = bool((cfg.get("email") or {}).get("touch_id"))
    conn.append(
        '<div class="connrow needs-server"><i class="cdot'
        + (" on" if mail_accts else "") + '"></i><b>Mail</b><span>'
        + (f"Connected: {mrows} Drafts you approve can send from it. "
           if mail_accts else
           "Not connected. Email drafts stay copy and paste until it is. ")
        + '<button class="mini" id="ms2-open">'
        + ("Add another account" if mail_accts else "Set up sending")
        + '</button>'
        '<span id="ms2wrap" hidden>'
        '<span class="msteps"><b>This needs an app password, never your '
        'real one.</b> Your provider makes it just for this and you can '
        'delete it any time. It can&rsquo;t change your password or '
        'settings, but it does open the whole mailbox, reading as well as '
        'sending.<br>'
        '<b>Step 1.</b> Create one, about two minutes: '
        '<a href="https://myaccount.google.com/apppasswords" target="_blank" '
        'rel="noopener">Gmail: create an app password &#8599;</a> &nbsp;&middot;&nbsp; '
        '<a href="https://login.yahoo.com/myaccount/security" target="_blank" '
        'rel="noopener">Yahoo: Account Security &#8599;</a> (look for '
        '&ldquo;Generate app password&rdquo;). If the page asks you to turn '
        'on 2-Step Verification first, do that and come back.<br>'
        '<b>Step 2.</b> Back here, pick the provider, type your address and '
        'paste the code.</span>'
        '<form id="ms2" class="mailsetup">'
        '<select id="ms2-prov"><option value="gmail">Gmail</option>'
        '<option value="yahoo">Yahoo</option><option value="icloud">iCloud</option>'
        '<option value="outlook">Outlook (sending only)</option></select>'
        '<input id="ms2-addr" placeholder="you@gmail.com" autocomplete="off">'
        '<input id="ms2-pw" type="password" placeholder="paste the app password" autocomplete="off">'
        '<button type="submit" class="primary">Connect</button>'
        '<span class="mshelp" id="ms2-help">The code lands in your '
        'Mac&rsquo;s Keychain, never in a file.</span></form></span>'
        + conn_allow(
            ("It can", "Send a draft when you press Approve &amp; send, one "
             "message per press, with the exact from, to, subject and text "
             "in front of you."
             + (" Each send asks for your fingerprint." if _tid_mail else "")),
            ("It can&rsquo;t", "Send on its own: the morning plan and the "
             "night shift have no way to. Drafts to anyone in a personal "
             "circle, family and friends, get Copy only."),
            ("Risk", "The app password opens the whole mailbox. "
             + ("It sits in your Mac&rsquo;s Keychain and only comes out "
                "with your fingerprint." if _tid_mail else
                "It sits in your Mac&rsquo;s Keychain, where a program "
                "running as you could read it.")),
            ("To stop", "Press &times; on the address and this Mac forgets "
             "the app password. It still works at your provider until you "
             'delete it there (Gmail: <a href="https://myaccount.google.com/'
             'apppasswords" target="_blank" rel="noopener">App passwords '
             "&#8599;</a>)."))
        + '</span></div>')
    # Mail, the other direction. Off until she turns it on, headers only, and
    # only ever on a button — see email_read.py for why bodies stay out. Shown
    # even with no account connected: a capability nobody can see is one she
    # can't decide about.
    conn.append(_mailread_row(cfg, bool(mail_accts)))
    # Task suggestions from whitelisted mail — the amended boundary of
    # 2026-09-08 (decisions.md): bodies for HER list only, read by a no-tools
    # model, nothing lands without her Accept.
    conn.append(_mailtasks_row(cfg, bool(mail_accts)))
    # Calendar — local read of the Mac's Calendar app; Google and Outlook
    # ride in through Internet Accounts, no OAuth anywhere.
    conn.append(
        '<div class="connrow needs-server"><i class="cdot'
        + (" on" if cal_on else "") + '"></i><b>Calendar</b><span>'
        + ("On. The morning plan reads titles and times from the Mac&rsquo;s "
           "Calendar app. "
           '<button class="mini" id="cal-test">Test read</button> '
           '<button class="mini" id="cal-off">Turn off</button>'
           if cal_on else
           "Off. The plan can&rsquo;t see your real day. "
           '<button class="mini" id="cal-on">Turn on</button>')
        + '<span class="mshelp" id="cal-help"></span>'
        + (_calblock_row(cfg) if cal_on else "")
        # The time-block help moved into the fold (28 Sep review): the row
        # keeps the one sentence that matters, the how-to folds.
        + conn_allow(
            ("Set up", "In System Settings, Internet Accounts, add "
             "<b>Google</b> and <b>Microsoft Exchange</b> and tick Calendars "
             "on each; the Mac&rsquo;s Calendar app then carries both. The "
             "first read asks for one macOS permission; allow it once."
             + ('<br>For blocks on your phone, pick a calendar that belongs '
                'to an account (school, Outlook or iCloud); the local Brain '
                'calendar stays on this Mac. To keep them apart, in the '
                'Calendar app choose File &rarr; New Calendar, pick the '
                'account, name it &ldquo;Brain&rdquo; and choose it here.'
                if cal_on else "")),
            ("It can", "Read event titles and times, and add the time blocks "
             "you ask for to "
             + ("the calendar picked above." if cal_on
                else "a calendar you pick.")),
            ("It can&rsquo;t", "See notes, guests or locations, or change or "
             "delete any event, its own blocks included."),
            ("Risk", f"The titles go to {AG.short()} with each morning plan, so the "
             "model sees what a private appointment is called. Blocks on an "
             "account calendar sync to that account and your phone."))
        + '</span></div>')
    # The way back into the walkthrough. The ? in the corner always starts
    # this page's tour; this re-arms the whole thing — for a new tester on
    # this brain, or for her own second look. It is not a connection, so it
    # carries no on/off dot and stays out of the count (28 Sep review, H3).
    tour_row = (
        '<div class="connrow conntour needs-server"><i class="cdot none"></i>'
        '<b>Show me around</b><span>'
        'The ? in the corner walks through whichever page you are on. '
        '<button class="mini" id="tour-again">Start the full tour</button> '
        + ('<button class="mini" data-tipoff="1">Stop the daily tips</button>'
           if (cfg.get("tips") or {}).get("on") else
           '<button class="mini" data-tipon="1" title="For you shows one feature a '
           'day, with Show me">Show me one new thing a day</button>')
        + '<span class="mshelp" id="tour-help"></span></span></div>')
    # The night shift's switch moved here from the top of the tab.
    _n = cfg.get("night") or {}
    _non = bool(_n.get("enabled"))
    # What the night really runs: night_config drops the scout while the
    # Season is switched off (parts.py).
    try:
        import night_config as _NC
        _njobs = _NC.load()["jobs"]
    except Exception:
        _njobs = _n.get("jobs")
    _nb = _n.get("on_battery")
    _nbat = ("plugged in or not" if _nb is True
             else f"on battery only above {_nb}%"
             if isinstance(_nb, (int, float)) and not isinstance(_nb, bool)
             else "only when plugged in")
    conn.append('<div class="connrow needs-server"><i class="cdot'
                + (' on' if _non else '') + '"></i><b>Night shift</b><span>'
                + (f'At {e(_n.get("at") or "01:00")} it '
                   f'{night_plain(_njobs)}; {_nbat}. ' if _non
                   else 'Off. ')
                + '<button class="mini" id="nighttoggle" data-on="'
                + ('1' if _non else '0') + '">'
                + ('Turn off' if _non else 'Turn on') + '</button>'
                + conn_allow(
                    ("It can", f"Start {AG.short()} while you sleep to do those "
                     f"jobs, using your {AG.short()} plan, then save the brain"
                     + (" and push it to your backup copy online."
                        if cfg.get("git_push") else ".")),
                    ("It can&rsquo;t", "Send a message or an email, or "
                     "change the brain&rsquo;s own code. Each run is fenced "
                     "to the brain folder."),
                    ("Risk", "Queue items can hold text other people wrote, "
                     "such as a pasted email, and that text could try to "
                     "steer the run; the fence keeps it inside the brain. "
                     f"Each night spends from your weekly {AG.short()} allowance."))
                + '</span></div>')
    # Folded to one line: seven rows of settings are something she visits,
    # not something the tab should make her scroll past every time. The
    # line says whether any of them needs her.
    # The line names what is off or waiting: "7 of 8 on" left her to find
    # the eighth by squinting at dots (28 Sep review, H3).
    def _cname(row):
        m = re.search(r'</i><b>([^<]+)</b>', row)
        return m.group(1) if m else ""
    rows = [r for r in conn if r]
    waits = [_cname(r) for r in rows if 'cdot wait"' in r]
    offs = [_cname(r) for r in rows
            if 'cdot on"' not in r and 'cdot wait"' not in r]
    n_on = len(rows) - len(waits) - len(offs)
    body = "".join(rows) + tour_row

    def _names(ns):
        return ", ".join(ns) if len(ns) <= 2 else f"{len(ns)}"
    state = (f"{_names(waits)} need{'s' if len(waits) == 1 else ''} you"
             if waits else
             f"{n_on} on &middot; {_names(offs)} off" if offs
             else f"all {n_on} on")
    V["hoodrail"].append(
        '<section id="connections" class="hoodsec">'
        f'<h3 class="area">Connections <span class="csub">{state}</span></h3>'
        f'<div class="connlist">{body}</div></section>')
    # What Claude costs, and the dial for it: the page of its own.
    V["hoodrail"].append(
        '<section id="spend" class="hoodsec"><h3 class="area">AI and spend</h3>'
        # The plan itself, the way /usage shows it in Claude Code: filled
        # in live by orb.py's meter (plan_usage.py behind it).
        '<div class="planmeter" data-planmeter hidden></div>'
        '<p class="lcfaint">'
        + ("Careful mode: Haiku by default, no 7am plan"
           if ai == "careful" else
           "Full mode: the morning plan runs itself, Sonnet by default")
        + f'</p><a class="mini" href="usage.html">What {AG.short()} spends &rarr;</a>'
        ' <a class="mini" href="privacy.html">What it may read and send &rarr;</a>'
        "</section>")

    # ---- New files in her folders. A session in a project repo can write a
    # 75-item task menu and a walkthrough log, and none of it reaches the
    # brain: sync mirrors CHECKBOXES, and those files have none. This lists
    # what changed and hands it to Claude to file.
    try:
        import serve as _srv
        import docs as _docs
        newf = _srv.recent_source_files()
        # The brain's own files and the handoffs every sync rewrites are not
        # news: they were 30 of the 40 (28 Sep review). Same rule as the
        # Files list, so each row here is also a door into it.
        newf = [f for f in newf
                if f.get("source") != "The brain"
                and not _docs._in_brain(f.get("path", ""))
                and os.path.basename(f.get("path", "")).lower() != "handoff.md"]
    except Exception:
        newf = []
    if newf:
        rows = []
        for fdesc in newf[:12]:
            rows.append('<div class="recrow"><span class="recname">'
                        f'{e(fdesc["name"])}</span>'
                        f'<span class="recmeta">{e(fdesc["source"])} &middot; '
                        f'{e(fdesc["when"].lstrip("0"))}</span>'
                        f'<button class="mini" data-openfile="{_docs._id(fdesc["path"])}"'
                        ' title="Opens it in Files">Open</button></div>')
        # A decision for her — file these or not — so it is a line in For you.
        n_nf = len(newf)
        tray_confirm.append(tray_item(
            "newfiles", "confirm", "New notes in your project folders",
            '<div class="recwrap needs-server">'
            + "".join(rows)
            + (f'<p class="meta">and {n_nf - 12} more in Files</p>'
               if n_nf > 12 else "")
            + '<div class="recopts">'
            f'<button class="mini" id="filenew">Have {AG.short()} read and file these</button>'
            "</div></div>", n_nf))

    # ---- Projects she is working in that the brain does not follow yet.
    # Found by a free scan on every build; following one is her click.
    try:
        import discover as _disc
        newp = _disc.proposals(cfg)
    except Exception:
        newp = []
    if newp:
        rows = []
        for p in newp[:6]:
            when = "today" if p["days"] == 0 else f'{p["days"]}d ago'
            tip = ("Has a handoff file: its tasks come through on the next sync"
                   if p["handoff"] else
                   "No handoff file yet: following it also puts a note in your "
                   "inbox to give it one")
            rows.append('<div class="recrow"><span class="recname">'
                        f'{e(p["name"])}</span>'
                        f'<span class="recmeta" title="{e(tip)}">{when}'
                        + (" &middot; handoff" if p["handoff"] else "")
                        + '</span>'
                        f'<button class="mini" data-proj="{e(p["name"])}" '
                        'data-projdo="follow">Follow</button>'
                        f'<button class="mini" data-proj="{e(p["name"])}" '
                        'data-projdo="ignore">Not a project</button></div>')
        tray_confirm.append(tray_item(
            "newprojects", "confirm", "New projects on this Mac",
            '<div class="recwrap needs-server">' + "".join(rows) + "</div>",
            len(newp)))

    # ---- Recordings: the loop from "I recorded the kitchen conversation" to
    # "the project's task lists moved" without a shell script in between.
    try:
        import transcribe as TR
        recs = TR.recordings()[:6]
        haves = TR.existing_transcripts()
    except Exception:
        recs, haves = [], []
    if _B.PRESENTING:
        recs, haves = [], []        # their names and folders can be private
    if recs or haves:
        rooms_opts = ['<option value="">which project?</option>']
        for room in M.all_rooms(cfg):
            nm = room.get("name", "")
            sl = room.get("slug") or M.room_slug(nm)
            rooms_opts.append(f'<option value="{e(sl)}">{e(nm)}</option>')
        rows = []
        for r in recs:
            mins = f'{r["minutes"]:g} min' if r["minutes"] else ""
            state = ('<span class="recdone">transcribed &#10003;</span>'
                     if r["done"] else
                     f'<button class="mini needs-server" data-rec="{e(r["path"])}">'
                     "Transcribe &amp; file</button>")
            rows.append('<div class="recrow"><span class="recname">'
                        f'{e(r["name"])}</span>'
                        f'<span class="recmeta">{e(mins)} &middot; {e(_dm(r["when"]) + r["when"][10:])}</span>'
                        f"{state}</div>")
        # Transcripts she already produced herself — the cheap path: file it
        # and go straight to the tasks, no second twenty-minute run.
        hrows = []
        for t in haves:
            hrows.append(
                '<div class="recrow"><span class="recname">'
                f'{e(t.get("label") or t["name"])}</span>'
                f'<span class="recmeta">{t["kb"]}KB &middot; {e(_dm(t["when"]) + t["when"][10:])}</span>'
                f'<button class="mini needs-server" data-adopt="{e(t["path"])}">'
                "Use this transcript</button></div>")
        if hrows:
            rows.append('<details class="recold"><summary>Already transcribed '
                        f"({len(hrows)}): file one straight into a project"
                        "</summary>" + "".join(hrows) + "</details>")
        n_todo = sum(1 for r in recs if not r["done"])
        if n_todo:
            tray_confirm.append(tray_item(
                "recordings", "confirm", "Recordings not transcribed yet",
                '<a class="mini" href="#/hood" data-hoodgo="recordings">'
                "Transcribe and file them &rarr;</a>", n_todo))
        # The heading stays a heading; the fold is a row that looks like it
        # opens. "Recordings 3 to transcribe" read as one line of plain text.
        V["hood"].append(
            '<section id="recordings" class="hoodsec">'
            '<h3 class="area">Recordings</h3><details class="hoodfold"><summary>'
            + (f"{n_todo} recording{'' if n_todo == 1 else 's'} to transcribe"
               if n_todo else "All transcribed")
            + '</summary><div class="recwrap needs-server">'
            '<div class="recopts"><select id="rec-room">'
            + "".join(rooms_opts) + '</select>'
            '<select id="rec-lang"><option value="fr">French</option>'
            '<option value="en">English</option></select>'
            '<input id="rec-prompt" placeholder="names and jargon to expect '
            '(Bexley, moquette, évacuation…)" autocomplete="off"></div>'
            + "".join(rows)
            + '<p class="recnote" id="recnote" hidden></p>'
            '<p class="lcfaint">Each transcript shows up in the box&rsquo;s '
            'Files. A recording of an hour takes roughly twenty minutes to '
            'do, and the page can be closed while it runs.</p></div></details>'
            '</section>')

    # The voice — who speaks each language, and how fast (voice.py). Kokoro
    # when it's installed; "This Mac" hands that language to `say`.
    try:
        import voice as _VO
        _kk = (cfg.get("voice") or {}).get("kokoro") or {}
        _ready = _VO.kokoro_ready()

        def _pick(lang):
            cur = _kk.get(lang, _VO.KOKORO_DEFAULT[lang]) if _ready else ""
            opts = []
            if _ready:
                for grp, names in _VO.KOKORO_VOICES[lang]:
                    opts.append(f'<optgroup label="{e(grp)}">' + "".join(
                        f'<option value="{e(n)}"{" selected" if n == cur else ""}>'
                        f'{e(_VO.voice_label(n))}</option>' for n in names)
                        + "</optgroup>")
            mac = _VO.pick_voice(lang) or "system voice"
            opts.append('<optgroup label="This Mac">'
                        f'<option value=""{" selected" if not cur else ""}>'
                        f'{e(mac)}</option></optgroup>')
            name = "English" if lang == "en" else "French"
            return (f'<div class="vpick"><label class="aplabel" for="vp-{lang}">{name}</label>'
                    f'<select id="vp-{lang}" data-voiceset="{lang}">{"".join(opts)}</select>'
                    f'<button class="mini" data-voicehear="{lang}">&#9656; Hear it</button></div>')
        _sp = float(_kk.get("speed") or 1.0)
        _paces = [(.9, "Calmer"), (1.0, "Natural"), (1.1, "Brisker"), (1.2, "Quick")]
        V["hood"].append(
            '<section id="voice" class="hoodsec"><h3 class="area">Voice</h3>'
            + _pick("en") + _pick("fr")
            + '<div class="vpick"><label class="aplabel" for="vp-speed">Pace</label>'
            '<select id="vp-speed" data-voiceset="speed">' + "".join(
                f'<option value="{v}"{" selected" if abs(v - _sp) < .01 else ""}>{lab}</option>'
                for v, lab in _paces) + '</select></div>'
            '<p class="lcfaint" data-voicenote>'
            + ("Kokoro, on this Mac" if _ready else
               "The Mac&rsquo;s own voices. Kokoro isn&rsquo;t installed")
            + '</p></section>')
    except Exception:
        pass

    # The parts of the brain, each with its switch (parts.py, 8 Oct, her
    # ask: less of the brain for someone who wants less). Off hides the part
    # and stops its own work; its files stay, so on brings it all back.
    import parts as PARTS
    _off = PARTS.off(cfg)
    _prow = []
    for pid, pname, pline in PARTS.PARTS:
        pon = pid not in _off
        _prow.append(
            f'<div class="connrow partrow"><i class="cdot{" on" if pon else ""}">'
            f'</i><b>{e(pname)}</b><span>{e(AG.say(pline))}</span>'
            f'<button class="mini needs-server" data-part="{pid}"'
            f' data-on="{0 if pon else 1}">{"Turn off" if pon else "Turn on"}'
            '</button></div>')
    _offn = [PARTS.NAMES[p] for p in _off]
    V["hood"].append(
        '<section id="parts" class="hoodsec"><h3 class="area">Parts of the'
        ' brain</h3><details class="hoodfold"><summary>'
        + ("Every part on" if not _offn else
           " and ".join(_offn) + " off" if len(_offn) <= 2 else
           f"{len(_offn)} parts off")
        + '</summary><div class="connlist">' + "".join(_prow) + '</div>'
        '<p class="lcfaint">Off hides a part and stops its work. Its files'
        ' stay, so turning it back on brings it all back.</p></details>'
        '</section>')

    # What the morning plan checks (plan_sources.py, 8 Oct, her ask: let
    # each person choose). The core four have no switch; a source a part
    # owns follows that part above. The same list, filled from the run's
    # own record, is "How this plan was made" under the plan on Today.
    import plan_sources as PS
    _srows, _son = [], 0
    for sid, sname, sline, _dflt, spart, sswitch in PS.SOURCES:
        son = PS.on(sid, cfg)
        _son += son
        if not sswitch:
            tail = (f'<span class="lcfaint pstail">'
                    + ("Always" if not spart else
                       f"{e(PARTS.NAMES.get(spart, spart))} part")
                    + '</span>')
        else:
            ok, why = (PS.mail_ready(cfg) if sid == "mail" else
                       (not PS.unset(sid, cfg), PS.unset(sid, cfg)))
            if not son and not ok:
                tail = f'<span class="lcfaint pstail">{e(why)}</span>'
            else:
                tail = (f'<button class="mini needs-server" data-part="plan:{sid}"'
                        f' data-on="{0 if son else 1}">'
                        + ("Turn off" if son else "Turn on") + '</button>')
        _srows.append(
            f'<div class="connrow partrow"><i class="cdot{" on" if son else ""}">'
            f'</i><b>{e(sname)}</b><span>{e(sline)}</span>{tail}</div>')
    V["hood"].append(
        '<section id="plansources" class="hoodsec"><h3 class="area">What the'
        ' morning plan checks</h3><details class="hoodfold"><summary>'
        f'{_son} of {len(PS.SOURCES)} on</summary><div class="connlist">'
        + "".join(_srows) + '</div><p class="lcfaint">One marked with a part'
        ' turns off with that part, in Parts of the brain above. Under each'
        ' day&rsquo;s plan, How this plan was made shows what it looked at.'
        '</p></details>'
        '</section>')

    # Project folders (9 Oct, her ask): which folders the brain reads for
    # open tasks, and two ways to add one: paste names or paths, or let it
    # look. config.json held the list with no way to see it on the page.
    _root = os.path.realpath(os.path.dirname(BRAIN))
    _frows = []
    for _src in cfg.get("sources") or []:
        _sp = _src.get("path", "")
        if not _sp or os.path.realpath(os.path.expanduser(_sp)) == _root:
            continue                      # the brain itself is not a project
        _here = os.path.isdir(os.path.expanduser(_sp))
        _frows.append(
            f'<div class="connrow partrow"><i class="cdot{" on" if _here else ""}">'
            f'</i><b>{e(_src.get("name") or os.path.basename(_sp))}</b>'
            f'<span>{e(_sp)}{"" if _here else " (not found)"}</span>'
            f'<button class="mini needs-server" data-srcdrop="{e(_sp)}"'
            f' data-srcname="{e(_src.get("name") or _sp)}">Stop following</button></div>')
    V["hood"].append(
        '<section id="folders" class="hoodsec"><h3 class="area">Project folders'
        '</h3><details class="hoodfold"><summary>'
        f'{len(_frows)} followed</summary><div class="connlist">'
        + ("".join(_frows) or '<p class="lcfaint">None yet.</p>') + '</div>'
        '<div class="srcadd"><label for="srcpaste"><b>Add by name or path</b>'
        '</label><textarea id="srcpaste" rows="3" spellcheck="false"'
        ' placeholder="the country house&#10;~/Desktop/School"></textarea>'
        '<div class="srcbtns"><button class="mini needs-server" id="srcfind">'
        'Find these</button><button class="mini needs-server" id="srcscan">'
        'Look for them on this computer</button></div><div id="srcres"'
        ' class="connlist" aria-live="polite"></div></div>'
        '<p class="lcfaint">The brain reads a followed folder for open tasks.'
        ' It never changes what is already in it.</p></details></section>')

    # The look — style, palette, theme, accent, paper, type. It lived in the
    # header's ⋯; a setting visited monthly belongs with the machinery.
    _ap = cfg.get("appearance", {}) or {}
    V["hood"].append(
        '<section id="look" class="hoodsec"><h3 class="area">The look</h3>'
        f'<div class="apwrap hoodlook" data-accent="{e(_ap.get("accent", "olive"))}"'
        f' data-base="{e(_ap.get("base", "warm"))}"'
        f' data-font="{e(_ap.get("font", "editorial"))}">'
        '<p class="aplabel">Style</p>'
        f'<div class="aprow styles" id="ap-style">{style_chips(cfg)}</div>'
        # Theme works under every style, so it comes first; the four after
        # it do not (see .apown).
        '<p class="aplabel">Theme</p>'
        '<div class="aprow" id="ap-theme">'
        '<button data-theme-set="light">Light</button>'
        '<button data-theme-set="dark">Dark</button>'
        '<button data-theme-set="auto">Auto</button></div>'
        # Every style but Workroom brings its own colours and type, so the
        # four rows below change nothing under one; they dim and say why,
        # and stay clickable for the day she goes back (8 Oct review).
        '<div class="apown"><p class="apownote">This style brings its own '
        'colours and type. These four apply when the style is Workroom.</p>'
        '<p class="aplabel">Palette</p>'
        f'<div class="aprow palettes" id="ap-palette">{palette_chips(cfg)}</div>'
        '<p class="aplabel">Accent</p>'
        '<div class="aprow swatches" id="ap-accent">'
        '<button data-accent="olive" style="--sw:oklch(48% .11 135)" title="Olive"></button>'
        '<button data-accent="forest" style="--sw:oklch(48% .11 150)" title="Forest"></button>'
        '<button data-accent="teal" style="--sw:oklch(52% .11 185)" title="Teal"></button>'
        '<button data-accent="ocean" style="--sw:oklch(52% .12 245)" title="Ocean"></button>'
        '<button data-accent="indigo" style="--sw:oklch(50% .13 280)" title="Indigo"></button>'
        '<button data-accent="plum" style="--sw:oklch(50% .13 325)" title="Plum"></button>'
        '<button data-accent="rose" style="--sw:oklch(55% .14 12)" title="Rose"></button>'
        '<button data-accent="amber" style="--sw:oklch(60% .12 70)" title="Amber"></button>'
        "</div>"
        '<p class="aplabel">Paper</p>'
        '<div class="aprow" id="ap-base">'
        '<button data-base="warm">Warm</button><button data-base="cool">Cool</button>'
        '<button data-base="rose">Blush</button><button data-base="mono">Neutral</button>'
        "</div>"
        '<p class="aplabel">Type</p>'
        '<div class="aprow" id="ap-font">'
        '<button data-font="editorial">Editorial</button>'
        '<button data-font="clean">Clean</button>'
        '<button data-font="playful">Playful</button></div>'
        "</div></div></section>")
    # The brain's memory: what it knows about her and why things are the way
    # they are. Read here; changed by telling the box.
    V["hoodrail"].append(
        '<section id="memory" class="hoodsec"><h3 class="area">The brain&rsquo;s'
        ' memory</h3>' + "".join(hood_memory) + hood_ref
        # The working drawings of how it all fits (blueprints.py), when made.
        + ('<p><a class="mini" href="blueprints/life-brain-blueprints.html">'
           'Open the blueprints &rarr;</a></p>'
           if os.path.exists(os.path.join(BRAIN, "blueprints",
                                          "life-brain-blueprints.html")) else "")
        + (('<details class="refblock"><summary>Questions you parked</summary>'
            + parked_qhtml + "</details>") if parked_qhtml else "")
        + hood_olddrafts + hood_inbox + "</section>")
    return drafts

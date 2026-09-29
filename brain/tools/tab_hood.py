"""The Under the Hood tab: build()'s UNDER THE HOOD section, in its own file.

build() calls render() where the section used to sit, passing what the
sections above it worked out; render() returns what the ones below read.
The page helpers come from build.py, so run the page with build.py.
"""

from datetime import datetime
from datetime import timedelta
import json
import md as MD
import model as M
import os
import re
import usage as USAGE

from build import (BRAIN, _calblock_row, _mailread_row, _mailtasks_row, _tid,
    ask_label, clip, draft_label, draftcard, e, iso_prose, linkify_html,
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


def render(V, cfg, hood_inbox, hood_ref, parked_qhtml, pending, q, today,
           tray_confirm, tray_read, tray_send):
    # The Claude tab dissolved on 28 Sep ("The brain, redrawn", decisions.md).
    # Talking to Claude is the box, on every page. What Claude hands back is
    # For you, on Today: drafts to send, finished work to read. What is left —
    # the jobs and their runs, the connections, the look, the brain's own
    # memory — is machinery, and it lives here, behind the gear.
    ai = "careful" if cfg.get("ai") in ("low", "careful", "pro") else "full"
    drafts = M.load_drafts(today=today)
    email_default = (cfg.get("email") or {}).get("default", "")
    email_ready = bool(email_default)
    # Each fresh draft is its own Send line in For you, its card one click
    # down with every control it had (Copy, Open in email, the per-message
    # approval for work contacts; personal circles stay copy-only, in code).
    for d in drafts:
        if d.get("stale"):
            continue
        who = d.get("person") or d.get("to") or ""
        tray_send.append(tray_item(
            _tid("d", d["file"]), "send",
            clip(d.get("task") or d.get("subject") or d.get("title")
                 or draft_label(d["file"]), 90),
            draftcard(d, email_ready, email_default),
            sub=("to " + who) if who else ""))
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
    <button id="askrun" class="jobbtn jobqueue{' hot' if n_pending else ''}" title="Start Claude Code here and work through everything waiting">Work the queue<span id="qcount" class="jobwhen">{qcount_label}</span></button>
    {_job("brief", "Catch me up", "The whole brain, in plain language. Good after a few days away.")}
    {_job("today", "Refresh today&rsquo;s plan", "Rewrites the three from the brain as it stands. Runs itself every morning at 7.")}
  </div>
  <details class="morejobs"><summary>More jobs</summary>
  <div class="jobrow jobrow3">
    {_job("wrap", "Tidy the brain", "Files strays, catches stale or contradictory entries. The night shift runs this too.")}
    {_job("discover", "Scan my project folders", "Finds new work on this Mac. Read-only; safe anytime.")}
    {_job("scout", "Find things to do", "Searches the web for concerts, shows and nights out that match your taste. Runs weekly on its own; nothing is ever booked.")}
    {_job("audit", "Ask me what&rsquo;s missing", "Claude hunts the missing facts that make the ranking wrong; they become questions on Today.")}
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
            '<details class="ghost qgroup hoodfold" id="finished"><summary>What Claude '
            f'finished <span class="csub">{len(finished)}</span></summary>'
            '<div class="qlist">' + "".join(cards) + "</div></details>")
    V["hood"].append("</section>")

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
    # Beeper — runs itself; state is just the stamp.
    try:
        _bm = os.path.getmtime(os.path.join(BRAIN, ".beeper-review.json"))
        _bd2 = datetime.now() - datetime.fromtimestamp(_bm)
        _bs = ("just now" if _bd2.total_seconds() < 3600 else
               f"{int(_bd2.total_seconds() // 3600)}h ago" if _bd2.days == 0 else
               f"{_bd2.days}d ago")
        conn.append('<div class="connrow"><i class="cdot on"></i><b>Beeper</b>'
                    f'<span>Synced {_bs} &mdash; chat names and dates only, '
                    'runs itself every morning.</span></div>')
    except Exception:
        conn.append('<div class="connrow"><i class="cdot"></i><b>Beeper</b>'
                    '<span>Never synced &mdash; tap <b>Sync from Beeper</b> on '
                    'the People page.</span></div>')
    # Telegram — three states: paired, token-awaiting-first-message, nothing.
    if tg.get("chat_id"):
        conn.append('<div class="connrow"><i class="cdot on"></i><b>Telegram</b>'
                    '<span>Paired &mdash; anything you message the bot gets '
                    'filed; the plan arrives mornings, the check evenings.</span></div>')
    elif tg.get("token"):
        _pc = tg.get("pair_code") or ""
        conn.append('<div class="connrow"><i class="cdot wait"></i><b>Telegram</b>'
                    '<span>Token saved. To pair, message '
                    + (f'the code <b class="paircode">{e(_pc)}</b>' if _pc
                       else 'the pairing code (appears here within a minute '
                            '&mdash; refresh)')
                    + ' to your bot in Telegram. Only the chat that sends the '
                    'exact code is ever listened to &mdash; anyone else who '
                    'finds the bot gets silence, forever. Once paired, the '
                    'whole surface is two things: file a note, and read the plan '
                    'back. A message can never start a job or spend '
                    'anything.</span></div>')
    else:
        conn.append(
            '<div class="connrow needs-server"><i class="cdot"></i><b>Telegram</b>'
            '<span>Message the brain from your phone &mdash; captures file '
            'themselves, the plan arrives as a message. Two minutes: in '
            'Telegram message <b>@BotFather</b>, send <code>/newbot</code>, '
            'pick any name, paste the token here.'
            '<span class="connform"><input id="tg-token" autocomplete="off"'
            ' placeholder="123456789:AAF...">'
            '<button class="mini" id="tg-connect">Connect</button>'
            '<span class="mshelp" id="tg-help"></span></span></span></div>')
    # Mail — accounts listed; the add form always reachable, not draft-gated.
    # The flow is written as numbered steps with the provider's own settings
    # page one click away, because "app password" is jargon until the page
    # that mints one is in front of you.
    mrows = " ".join(f'<code>{e(a["address"])}</code>' for a in mail_accts)
    conn.append(
        '<div class="connrow needs-server"><i class="cdot'
        + (" on" if mail_accts else "") + '"></i><b>Mail</b><span>'
        + (f"Connected: {mrows} &mdash; drafts can send for real. "
           if mail_accts else
           "Not connected &mdash; email drafts stay copy-paste until this is "
           "set up. ")
        + '<button class="mini" id="ms2-open">'
        + ("Add another account" if mail_accts else "Set up sending")
        + '</button>'
        '<span id="ms2wrap" hidden>'
        '<span class="msteps"><b>What this needs is an app password &mdash; '
        'never your real one.</b> It&rsquo;s a separate throwaway code your '
        'provider mints just for this: it can only send mail, it can&rsquo;t '
        'open your account, and you can revoke it any time.<br>'
        '<b>Step 1</b> &mdash; create one (takes two minutes): '
        '<a href="https://myaccount.google.com/apppasswords" target="_blank" '
        'rel="noopener">Gmail: create an app password &#8599;</a> &nbsp;&middot;&nbsp; '
        '<a href="https://login.yahoo.com/myaccount/security" target="_blank" '
        'rel="noopener">Yahoo: Account Security &#8599;</a> (look for '
        '&ldquo;Generate app password&rdquo;). If the page asks you to turn '
        'on 2-Step Verification first, do that and come back.<br>'
        '<b>Step 2</b> &mdash; back here: pick the provider, your address, '
        'paste the code it gave you.</span>'
        '<form id="ms2" class="mailsetup">'
        '<select id="ms2-prov"><option value="gmail">Gmail</option>'
        '<option value="yahoo">Yahoo</option><option value="icloud">iCloud</option>'
        '<option value="outlook">Outlook (sending only)</option></select>'
        '<input id="ms2-addr" placeholder="you@gmail.com" autocomplete="off">'
        '<input id="ms2-pw" type="password" placeholder="paste the app password" autocomplete="off">'
        '<button type="submit" class="primary">Connect</button>'
        '<span class="mshelp" id="ms2-help">The code lands in your '
        'Mac&rsquo;s Keychain, never in a file.</span></form></span>'
        '</span></div>')
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
        + ("On &mdash; the morning plan reads the Mac&rsquo;s Calendar app, "
           "titles and times only. "
           '<button class="mini" id="cal-test">Test read</button> '
           '<button class="mini" id="cal-off">Turn off</button>'
           if cal_on else
           "Off &mdash; the plan can&rsquo;t see your real day. "
           '<button class="mini" id="cal-on">Turn on</button>')
        + '<span class="mshelp" id="cal-help"></span>'
        + (_calblock_row(cfg) if cal_on else "")
        + '<details class="connhow"><summary>How Google, Outlook and your '
        'phone fit in</summary>System Settings &rarr; Internet Accounts &rarr; add '
        '<b>Google</b> and <b>Microsoft Exchange</b>, tick Calendars on each. '
        'The Mac&rsquo;s Calendar app then carries both, and the brain reads '
        'it locally, so nothing about your calendar leaves this Mac. '
        'The first read pops one macOS permission dialog; allow it once.'
        # The time-block help moved here from the row itself (28 Sep review):
        # the row keeps the one sentence that matters, the how-to folds.
        + ('<br><br>Time blocks: pick a calendar that belongs to an account '
           '(your school or Outlook one, or iCloud) and the blocks appear on '
           'your phone; the local Brain calendar stays on this Mac. For a '
           'separate calendar that still syncs, in the Calendar app choose '
           'File &rarr; New Calendar, pick the account, name it '
           '&ldquo;Brain&rdquo;, then choose it here.' if cal_on else '')
        + '</details></span></div>')
    # The way back into the walkthrough. The ? in the corner always starts
    # this page's tour; this re-arms the whole thing — for a new tester on
    # this brain, or for her own second look. It is not a connection, so it
    # carries no on/off dot and stays out of the count (28 Sep review, H3).
    tour_row = (
        '<div class="connrow conntour needs-server"><i class="cdot none"></i>'
        '<b>Show me around</b><span>'
        'The ? in the corner walks through whichever page you are on. '
        '<button class="mini" id="tour-again">Start the full tour</button>'
        '<span class="mshelp" id="tour-help"></span></span></div>')
    # The night shift's switch moved here from the top of the tab.
    _n = cfg.get("night") or {}
    _non = bool(_n.get("enabled"))
    _nb = _n.get("on_battery")
    _nbat = ("plugged in or not" if _nb is True
             else f"on battery only above {_nb}%"
             if isinstance(_nb, (int, float)) and not isinstance(_nb, bool)
             else "only when plugged in")
    conn.append('<div class="connrow needs-server"><i class="cdot'
                + (' on' if _non else '') + '"></i><b>Night shift</b><span>'
                + (f'At {e(_n.get("at") or "01:00")} it '
                   f'{night_plain(_n.get("jobs"))}; {_nbat}. ' if _non
                   else 'Off. ')
                + '<button class="mini" id="nighttoggle" data-on="'
                + ('1' if _non else '0') + '">'
                + ('Turn off' if _non else 'Turn on') + '</button></span></div>')
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
        + ("Careful mode: Haiku by default, nothing scheduled spends"
           if ai == "careful" else
           "Full mode: the morning plan runs itself, Sonnet by default")
        + '</p><a class="mini" href="usage.html">What Claude spends &rarr;</a>'
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
            '<button class="mini" id="filenew">Have Claude read and file these</button>'
            "</div></div>", n_nf))

    # ---- Recordings: the loop from "I recorded the kitchen conversation" to
    # "the project's task lists moved" without a shell script in between.
    try:
        import transcribe as TR
        recs = TR.recordings()[:6]
        haves = TR.existing_transcripts()
    except Exception:
        recs, haves = [], []
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
                        f"({len(hrows)}) &mdash; file one straight into a project"
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
            '(Perry, moquette, évacuation…)" autocomplete="off"></div>'
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
        '<p class="aplabel">Palette</p>'
        f'<div class="aprow palettes" id="ap-palette">{palette_chips(cfg)}</div>'
        '<p class="aplabel">Theme</p>'
        '<div class="aprow" id="ap-theme">'
        '<button data-theme-set="light">Light</button>'
        '<button data-theme-set="dark">Dark</button>'
        '<button data-theme-set="auto">Auto</button></div>'
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
        "</div></section>")
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

"""The Today tab: build()'s TODAY section, in its own file.

build() calls render() where the section used to sit, passing what the
sections above it worked out; render() returns what the ones below read.
The page helpers come from build.py, so run the page with build.py.
"""

from datetime import date
from datetime import datetime
from datetime import timedelta
import agents as AG
import lines as LN
import md as MD
import model as M
import os
import re

from build import (BRAIN, _greeting, _mailtasks_tray, _offer_verb, _plan_time,
    _probablydone_tray, _same_thing, _school_tray, _sig_tokens, _tid, ago,
    area_groups, artvid, calendar_starts, cardhead, clip, countdown_card,
    dayshape, e, forecastcard, friday_block, fronts_block, glance_row,
    heroline, ico, linkify_html, moneycard, next_line, now_minutes,
    plan_estimates, plan_reading, plan_tokens, plan_ws_lookup, read,
    rhythm_lines,
    room_labels, routine_card, school_view, security_card, sevclass, span,
    taskrow, tray_item, week_strip, why_line)


def _dump_in_flight():
    """Is a brain dump waiting in the queue or being worked right now?"""
    import glob
    for path in glob.glob(os.path.join(BRAIN, "queue", "*.md")):
        try:
            with open(path, encoding="utf-8") as f:
                head = f.read(600)
        except OSError:
            continue
        if "\nmode: dump" in head and re.search(r"\nstatus: (pending|working)", head):
            return True
    return False


def _free_weekend(cfg, today):
    """For you: "This weekend is free", with two ideas from the season list
    and a button per free day that slots one there. Only when the calendar
    was read (an unread one looks free), the weekend's days have nothing in
    the calendar or the season grid, and the season is on and running. Ideas
    whose window closes soonest come first, then this month's."""
    import parts
    if not parts.on("season", cfg) or not cfg.get("calendar"):
        return None
    s = M.load_season(today=today)
    if not s or (s["end"] and s["end"] < today):
        return None
    wd = today.weekday()
    sat = today + timedelta(days=(5 - wd) % 7) if wd < 6 else today - timedelta(days=1)
    days = [d for d in (sat, sat + timedelta(days=1))
            if d >= today and not (s["end"] and d > s["end"])]
    if not days:
        return None
    import calendar_read
    taken = {str(w)[:10] for w, _t in calendar_read.events(7)}
    for i in s["items"]:
        p = i.get("planned")
        if p and not i["done"]:
            d = p["start"]
            while d <= p["end"]:
                taken.add(d.isoformat())
                d += timedelta(days=1)
    if any(d.isoformat() in taken for d in days):
        return None
    ideas = [i for i in s["items"] if not i["done"] and not i["dropped"]
             and not i["planned"] and not (i.get("ends") and i["ends"] < today)]
    if not ideas:
        return None
    mon = today.strftime("%B").lower()
    ideas.sort(key=lambda i: ((i["ends"] - today).days if i.get("ends") else 999,
                              0 if (i["when_label"] or "").lower().startswith(mon) else 1))
    rows = []
    for i in ideas[:2]:
        key = MD.taskkey(MD.bare(i["text"]))
        hint = ""
        if i.get("ends"):
            hint = "ends " + i["ends"].strftime("%-d %b")
        elif i["fits"]:
            hint = i["fits"]
        rows.append('<div class="mtrow"><span class="mttask">' + e(clip(i["text"], 90))
                    + (f"<i>{e(hint)}</i>" if hint else "") + "</span>"
                    + "".join(f'<button class="mini needs-server" data-szput="{key}"'
                              f' data-day="{d.isoformat()}">{d.strftime("%A")}</button>'
                              for d in days) + "</div>")
    title = ("This weekend is free" if len(days) == 2 else
             days[0].strftime("%A") + " is free")
    body = ("".join(rows) + '<p class="meta">Nothing in your calendar yet. '
            '<a href="#/season">More ideas on Season</a></p>'
            '<span class="mshelp" id="szput-help"></span>')
    return tray_item(_tid("weekend", days[0].isoformat()), "answer", title,
                     body, len(rows))


def render(V, b, cfg, pending, people, today, tray_answer, tray_confirm,
           urgent, warm, ws, WS_OUTCOMES):
    today_md = read("today.md")
    # The starter ships a placeholder plan ("updated: never"): it is not a
    # plan, and counting it as one hid the empty state (7 Oct audit).
    if "updated: never" in today_md[:160]:
        today_md = ""
    import build as _B
    if _B.PRESENTING:
        # Presenting (privacy.py): headings and the tasks outside the hidden
        # areas only; no free text, no two-minute chases.
        today_md = _B.present_md(today_md)
    # Today's plan, tokenised once. Every block below that could restate a
    # task the plan already carries checks itself against this. The hero is
    # the one exception: it is allowed to be the plan's task, because being
    # the most pressed thing is its entire job — so it publishes what it took
    # and the others avoid THAT too.
    PLAN_TOKS = plan_tokens(today_md)
    # A plan written on an earlier day is that day's plan, not today's. She
    # works to midnight, so from 00:00 until the morning run (and all day if
    # it fails) the page put Thursday's three in Friday's free hours, deck
    # and week strip (9 Oct audit). It still shows, named for its day, with
    # its evening check open; nothing places it in today's time.
    _pm = re.search(r"^updated:\s*(\d{4}-\d{2}-\d{2})", today_md[:300], re.M)
    plan_day = M.parse_date(_pm.group(1)) if _pm else None
    stale_plan = bool(today_md.strip() and plan_day and plan_day < today)
    day_md = "" if stale_plan else today_md

    # ONE OWNER PER FACT. Every block below that can name a task registers what
    # it printed, and checks the register before printing. Filtering each block
    # against the plan alone was not enough: two blocks that both avoided the
    # plan could still land on each other, which is how the same recording
    # upload reached the horizons, the quick wins and the digest at once.
    #
    # Order of claim is the order of the page, so the block a reader meets
    # first keeps the sentence and the ones below it move on to something else.
    SHOWN = list(PLAN_TOKS)

    def shown_already(text):
        return bool(text) and any(_same_thing(text, s) for s in SHOWN)

    def claim(text):
        toks = _sig_tokens(text)
        if toks:
            SHOWN.append(toks)
        return text

    # Where the "Today, so far" card landed in the rail, if it rendered —
    # the fronts radar splices itself into that card instead of standing
    # beside it as a near-twin (her ask, 31 Aug: "can these be combined?").
    daycard_ix = None

    # The hero is gone (2026-09-10, her call): one giant "next hour" block
    # read as a monument and demotivated. The plan leads the page now, and
    # fronts_block below it shows every area of her life with its own short
    # ranked list. hero() stays defined above in case a skin wants it back.
    # Orbit's deck, the first screen of Today in that skin (skin furniture
    # too): the orb to talk to, the three, the plan meter, the skills.
    import orb as ORB
    from build import countdown_rows
    V.setdefault("todaytop", []).append(
        ORB.deck_html(day_md, [] if _B.PRESENTING else countdown_rows(today),
                      (cfg.get("now") or {}).get("place") or "",
                      greeting=_greeting(today_md),
                      # presenting: Claude's ranking and her countdowns stay off
                      next_md="" if _B.PRESENTING else read("next.md")))
    # The greeting headline (skin furniture, hidden unless a skin shows it):
    # the day and what's left of the plan, said like a person would.
    V["today"].append('<h2 class="skinx skinx-greet">'
                      + e(_greeting(today_md)) + "</h2>")
    # A change to the brain's safety code she hasn't confirmed: first.
    V["today"].append(security_card())
    if not b["live"]:
        # A fresh brain teaches the first thing to do rather than showing a
        # blank hero. This is what a friend sees on their own new install.
        cues = [
            ("Start with you", "where you live, and what you're studying or building"),
            ("What fills your days", "the projects, work or study that take up your time"),
            ("The people", "family and close friends, including the ones far away you don't want to drift from"),
            ("What's weighing on you", "a deadline you're dreading, or a decision you keep putting off"),
            ("Loose threads", "what you owe people and what they owe you, like a reply you keep meaning to send"),
            ("What you're building in yourself", "habits or routines, and how often you do them"),
            ("Anything else", "small nagging things, or something that matters but doesn't fit anywhere"),
        ]
        cuelist = "".join(f'<li><b>{c}:</b> {d}</li>' for c, d in cues)
        # A first dump already queued or running: say so instead of offering
        # Start talking again, which made a second submission easy after a
        # reload lost the progress screen (7 Oct audit).
        _building = _dump_in_flight()
        V["today"].append(
            '<section class="hero sev-none">'
            + heroline('<p class="eyebrow">Welcome</p>',
                       '<video class="artvid cardart" autoplay muted loop playsinline poster="art/waving.png?v=2" width="72" height="72" aria-hidden="true"><source src="art/waving.mp4?v=2" type="video/mp4"></video>')
            + "<h1>Let's fill your brain</h1>"
            '<p class="hero-why hero-calmnote">Say who you are and what\'s '
            "going on, in whatever order it comes. The prompts below are only "
            f"there in case you get stuck. {AG.short()} sorts it all and "
            "checks with you before writing anything down.</p>"
            f'<ol class="onboard-cues">{cuelist}</ol>'
            + (f'<p class="hero-why"><b>Your brain is being built.</b> {AG.short()} is '
               'reading what you said; it takes a few minutes and you can close '
               'this page. The bell at the top shows its progress, and this '
               'card changes once it is done.</p>' if _building else
               '<button class="dumpstart needs-server" id="startdump">'
               "Start talking</button>")
            # /onboard is a Claude Code command; Codex and Gemini don't read
            # .claude/commands, so the terminal route is offered under Claude only.
            + ('<p class="meta" style="margin-top:12px">Prefer the terminal? Open Claude Code '
               "here and run <code>/onboard</code>.</p>"
               if AG.provider() == "claude" else "")
            + "</section>")

    # ORDER OF THE PAGE (her ask: clear, uncluttered, action-first):
    # hero → the plan (act) → questions (answer) → offers → forecast → digest.
    # Status never sits above action.

    # The assistant offers before being asked: upcoming dated tasks Claude can
    # get ahead of, one tap each. This is the difference between a brain that
    # presents and one that assists — the offer is visible, the boundary is
    # unchanged (research and drafts yes; booking, paying, sending never).
    # Built lazily, because it renders BELOW the plan and the horizons and so
    # must claim its tasks after them. Constructing it here but printing it
    # there would let it grab a sentence the blocks above were about to use.
    def build_offers():
        sec_offers = []
        if not b["live"]:
            return sec_offers
        soon_tasks = []
        for w2 in b["live"]:
            for t2 in w2["tasks"]:
                if (not t2["done"] and not t2.get("parked") and not t2.get("dropped")
                        and t2.get("due_days") is not None
                        and 0 <= t2["due_days"] <= 35):
                    verb = _offer_verb(t2["text"])
                    if verb:
                        soon_tasks.append((t2["due_days"], t2["text"],
                                           w2["name"], verb))

        def _prepped(txt, wn):
            return any(len(_sig_tokens(txt) & _sig_tokens(i2["title"] or "")) >= 2
                       for i2 in WS_OUTCOMES.get(wn.lower(), []))

        # Filter BEFORE the slice, never after. The three soonest-due tasks
        # are by construction the ones the plan already chose, so taking the
        # top three and then dropping the duplicates leaves an empty card on
        # exactly the days there was something to offer. Filtering first lets
        # this surface the NEXT three — which is the card's actual job.
        dupes = [s2 for s2 in soon_tasks if shown_already(s2[1])]
        soon_tasks = [s2 for s2 in soon_tasks if s2 not in dupes]
        soon_tasks.sort(key=lambda x: x[0])
        # A task already on today's list keeps its ✦ button on its own row, so
        # nothing is lost by dropping it from here — except the one thing the
        # row cannot say, which is that Claude ALREADY did the legwork. That
        # gets a line naming no task, so it restores the pointer without
        # reprinting the errand.
        if soon_tasks:
            rows3 = []
            for dd, txt, wn, verb in soon_tasks[:3]:
                when = "today" if dd == 0 else f"in {dd}d"
                seen_prep = _prepped(txt, wn)     # work already landed?
                claim(txt)
                rows3.append(
                    f'<div class="offer"><span class="offerwhen">{when}</span>'
                    f'<span class="offertext">{e(txt)}'
                    + (f'<a class="offersee" href="#/today">&#10022; {AG.short()} found '
                       "options. Open the card to see them</a>"
                       if seen_prep else f'<span class="offerwould">{verb}</span>')
                    + "</span>"
                    f'<button class="mini offerbtn needs-server" data-claudestart="{e(txt)}"'
                    f' data-claudews="{e(wn)}">'
                    + ("Run it again" if seen_prep else "Start it for me")
                    + "</button></div>")
            # A proposal waiting on her yes, so it is a For you line (7 Oct,
            # the page's own rule: one tray for what the brain proposes).
            tray_confirm.append(tray_item(
                "offers", "confirm", f"{AG.short()} can get ahead of these",
                '<div class="offercard intray">' + "".join(rows3)
                # A faint line, not the skin's .meta pill, which looked like
                # a button (28 Sep review).
                + '<p class="offerfoot">It never sends anything.</p></div>',
                len(rows3)))
        return sec_offers

    # Open questions from the brain — the second half of any dump's interview.
    # Claude writes them to questions.md when there's nobody to ask; answering
    # one hands it back to Claude, who files the answer and ticks the box.
    qtext = "" if _B.PRESENTING else read("questions.md")
    open_qs, parked_qs = [], []
    for line in qtext.split("\n"):
        mq = re.match(r"^\s*-\s+\[ \]\s+(.*)$", line)
        if not (mq and mq.group(1).strip()):
            continue
        raw = mq.group(1).strip()
        # A question you cannot answer yet is not a question you are
        # failing to answer. Parked ones wait for their date.
        mu = MD.UNTIL.search(raw)
        if mu and mu.group(1) > today.isoformat():
            parked_qs.append((raw, mu.group(1)))
        else:
            open_qs.append(raw)
    actqs = ""
    sec_questions = []

    def _qkey(raw):
        """Same stripping the server does, or the key will not match."""
        return MD.taskkey(re.sub(r"\s*\(urgent\)", "",
                                 MD.UNTIL.sub("", MD.DROPPED.sub(
                                     "", MD.CARRYING.sub("", raw))), flags=re.I))

    parked_qhtml = ""
    if open_qs or parked_qs:
        rows = []
        for raw in open_qs:
            # A question that knows its likely answers carries them,
            # "(options: Yes, add it | No)", and each becomes one tap that
            # files exactly what typing it would (8 Oct: a decision left as
            # prose in a run's summary never reached anyone's page).
            mo = re.search(r"\s*\(options?:\s*([^)]*)\)", raw, re.I)
            opts = [o.strip() for o in (mo.group(1).split("|") if mo else [])
                    if o.strip()][:4]
            qtxt = MD.plain(MD.UNTIL.sub("", raw.replace(mo.group(0), "")
                                         if mo else raw))
            key = _qkey(raw)
            _qstart = len(rows)
            optbtns = "".join(
                f'<button class="mini qopt" data-opt="{e(o)}">{e(o)}</button>'
                for o in opts)
            rows.append(
                '<li class="qrow">'
                f'<span class="qq"><span class="ttext">{e(qtxt)}</span>'
                f'<span class="qinline needs-server">{optbtns}'
                f'<input class="qin" data-q="{e(qtxt)}" autocomplete="off"'
                ' placeholder="Type the answer&hellip;">'
                f'<button class="mini qgo" data-qkey="{key}">file it</button>'
                f'<button class="mini qlater" data-qlater="{key}"'
                ' title="Park this until you can answer it">not yet&hellip;</button>'
                # Was a checkbox in front of every question (24 Sep: "too
                # many different check boxes"). Typing the answer is the
                # action; this is the rarer "already settled elsewhere".
                '<button class="mini tick qdone" aria-pressed="false"'
                f' data-src="questions.md" data-key="{key}"'
                ' title="Tick it off if you answered it somewhere else">already '
                'answered</button></span>'
                '<span class="qwhen needs-server" hidden>'
                f'<button class="mini" data-qdefer="{key}" data-days="7">next week</button>'
                f'<button class="mini" data-qdefer="{key}" data-days="30">in a month</button>'
                f'<button class="mini" data-qdefer="{key}" data-days="90">in three months</button>'
                f'<input type="date" class="qdate" data-qdate="{key}">'
                "</span></span></li>")
            # Each question is its own line in For you, answerable in place.
            tray_answer.append(tray_item(
                _tid("q", key), "answer", qtxt,
                '<ul class="tasks qslist">' + rows[_qstart] + "</ul>"))
        # Parked questions are never deleted — they wait in a fold with the
        # date they come back, and can be pulled forward again.
        prows = "".join(
            f'<li class="qparked"><span>{e(MD.plain(MD.UNTIL.sub("", praw)))}</span>'
            f'<b>{e(when)}</b>'
            f'<button class="mini needs-server" data-qwake="{_qkey(praw)}">'
            "bring it back</button></li>"
            for praw, when in sorted(parked_qs, key=lambda x: x[1]))
        parked_html = (
            f'<details class="ghost qparkfold"><summary>{len(parked_qs)} parked '
            "until you can answer them</summary>"
            f'<ul class="qparklist">{prows}</ul></details>' if parked_qs else "")
        parked_qhtml = parked_html
        if open_qs:
            sec_questions.append(
                '<section class="qcard"><p class="eyebrow">The brain needs '
                f'{len(open_qs)} answer{"s" if len(open_qs) != 1 else ""}</p>'
                '<p class="qlead">Each answer sharpens a task or a date. Park anything '
                "you cannot answer yet.</p>"
                f'<ul class="tasks qslist">{"".join(rows)}</ul>'
                + parked_html + "</section>")
        elif parked_qs:
            sec_questions.append(
                '<section class="qcard"><p class="eyebrow">Nothing to answer'
                "</p><p class=\"qlead\">Every open question is parked until you "
                "can answer it.</p>" + parked_html + "</section>")
        # The same questions ride in the activity drawer, answerable from any
        # tab — a follow-up should never require going to find it.
        if open_qs:
            actqs = ('<div class="actqs"><p class="eyebrow">The brain needs '
                     f'{len(open_qs)} answer{"s" if len(open_qs) != 1 else ""}</p>'
                     f'<ul class="tasks qslist">{"".join(rows)}</ul></div>')

    # The runbar pill says "1 waiting for Claude"; the drawer must SHOW the
    # one. A count whose item cannot be seen reads as a mystery, not a
    # status — so each pending ask gets a row: its name, a line of the ask
    # itself, and when it arrived.
    actpend = ""
    if pending:
        _mode_words = {"dump": "a dump to sort", "chat": "a shared chat",
                       "journal": "a journal entry",
                       "just-do-it": "a ramble from the page"}
        _one_day = __import__("datetime").timedelta(days=1)

        def _asked(created):
            d = (created or "")[:10]
            if d == today.isoformat():
                return "asked today"
            if d == (today - _one_day).isoformat():
                return "asked yesterday"
            return "asked " + d if d else "asked a while ago"

        def _wordcut(s, n):
            if len(s) <= n:
                return s
            cut = s[:n]
            return (cut[:cut.rfind(" ")] if " " in cut else cut) + "…"

        prows = []
        for it in pending:
            title = (it["title"] or "").strip() or "Untitled ask"
            raw = (it["body"] or "").strip()
            paras = [p.strip() for p in re.split(r"\n\s*\n", raw) if p.strip()]
            # The ramble button prefixes every ask with the same instruction
            # paragraph, so leading with it says nothing — her own words
            # start after it. The instructions stay out of the expanded
            # view too: she wrote the notes, not the wrapper.
            if len(paras) > 1 and paras[0].lower().startswith(
                    "i rambled these notes"):
                paras = paras[1:]
            full = "\n\n".join(MD.plain(p) for p in paras).strip()
            head = _wordcut(re.sub(r"\s+", " ", full).strip() or title, 110)
            more = full
            if len(more) > 1500:
                more = _wordcut(more, 1500) + "\n\n(the rest is in Jobs, under the hood)"
            bits = [_asked(it["created"])]
            bits.append(_mode_words.get(it["mode"], "asked from the page"))
            if it["status"] == "working":
                bits.append("left mid-work by the last run")
            prows.append(
                '<li><details class="actqd"><summary>'
                f'<b>{e(head)}</b>'
                f'<span class="meta">{e(" · ".join(bits))}'
                ' <span class="actmore"></span></span></summary>'
                f'<div class="actqfull">{e(more)}</div>'
                '<p class="meta actqgo"><a href="#/hood">In the queue, '
                'under the hood &rarr;</a></p></details></li>')
        actpend = ('<div class="actpend"><p class="eyebrow">Waiting to run</p>'
                   f'<ul class="actplist">{"".join(prows)}</ul></div>')

    # ---- Today's shape: the fixed skeleton of the day, so the plan is read
    # against real hours. Calendar events (local read, titles and times only)
    # plus the weekday's standing blocks from config "week". Silent when
    # there is nothing fixed — an empty strip would be furniture.
    V["todayrail"].append(routine_card(today))
    V["todayrail"].append(dayshape(cfg, today, day_md,
                                   ws_lookup=plan_ws_lookup(ws, cfg)))
    V["todayrail"].append(countdown_card(today))
    # A reply you owe a friend is the loudest small thing there is — her ask
    # (19 Aug 2026): don't make her find it under People. Personal circles
    # only, high on the rail; the digest at the bottom skips whoever is
    # already named here.
    # Freshest first: the card exists to catch a reply BEFORE it ages, so a
    # message from 4 days ago outranks a debt from a month back (which the
    # People tab and the digest still carry).
    _owed_close = sorted((pp for pp in people
                          if pp.get("owed") and pp.get("personal")
                          and not pp.get("held")),
                         key=lambda pp: pp.get("days_since")
                         if pp.get("days_since") is not None else 999)
    _owed_shown = {pp["name"] for pp in _owed_close[:7]}
    if _owed_close:
        _orows = []
        for pp in _owed_close[:7]:
            d = pp.get("days_since")
            # The row says the action, and the wait in words: "Reply to Indigo
            # · 5 days". A name, an arrow icon and "5d" left the verb for
            # her to supply (28 Sep review).
            when = ("today" if d == 0 else "yesterday" if d == 1
                    else f"{d} days" if d is not None and d < 14
                    else ago(d).replace(" ago", "") if d is not None else "")
            # The arrow opens Beeper on their chat rather than walking her to
            # the People tab to find the same person again. Her Reach says
            # which app that is, so the tooltip promises the right one; a
            # person she phones or emails has no chat to open, and the row
            # keeps the old jump instead of failing at her.
            reach = (pp.get("reach") or "").strip()
            chatty = reach.lower() not in ("email", "call", "phone", "in person")
            if chatty:
                where = f" on {e(reach)}" if reach else ""
                arrow = ('<span class="darrow opench" role="button" tabindex="0"'
                         f' data-openchat="{e(pp["name"])}"'
                         f' title="Opens your chat with them in Beeper{where},'
                         ' without sending anything"'
                         ' aria-label="Open the chat">&rarr;</span>')
            else:
                arrow = ('<span class="darrow" aria-hidden="true"'
                         f' title="You reach {e(pp["name"])} by {e(reach)}">'
                         "&rarr;</span>")
            _orows.append(f'<a class="drow owed" href="#/people">'
                          f'<span class="dname">Reply to {e(pp["name"])}</span>'
                          + (f'<span class="dwhy" title="They wrote last; you owe'
                             f' them a reply">&middot; {when}</span>' if when else
                             '<span class="dwhy"></span>')
                          + f"{arrow}</a>")
        extra = len(_owed_close) - 7
        if extra > 0:
            _orows.append(f'<a class="drow" href="#/people">'
                          f'<span class="dname">{extra} more to reply to</span>'
                          f'<span class="dwhy">&middot; on People</span>'
                          '<span class="darrow" aria-hidden="true">&rarr;</span></a>')
    # The owed replies ride in the two-minute sweep with the quick wins,
    # printed once both are known (below the plan).
    sweep_reply = "".join(_orows) if _owed_close else ""
    sweep_quick = ""
    plan_chases = ""      # the plan's own chase rows, moved into Quick replies
    late_fold = ""        # the late tasks, folded behind their one figure

    import parts as PARTS
    habits = M.load_habits(today=today) if PARTS.on("habits", cfg) else []
    if not today_md.strip() and not habits and b["live"]:
        # An empty state that teaches: what this space becomes, and the one
        # action that fills it. Blank is the state that loses trust fastest.
        V["today"].append(
            '<section class="firstrun"><p class="eyebrow">Nothing here yet</p>'
            '<span class="wav"></span>'
            '<p class="coach">This is where the three things worth your day '
            'land each morning. It fills itself once the brain knows what '
            'you have on.</p>'
            '<div class="frdo"><button class="btnp needs-server" id="frdump">'
            'Empty your head into it</button>'
            '<button class="mini needs-server" data-job="today">'
            'or write today&rsquo;s plan from what it already knows</button>'
            "</div></section>")
    if today_md.strip() or habits:
        # A fresh plan edit leaves its snapshot behind; while it is recent,
        # the undo sits right where the change happened.
        _undo = ""
        _upath = os.path.join(BRAIN, ".plan-undo.json")
        try:
            if (os.path.exists(_upath)
                    and datetime.now().timestamp() - os.path.getmtime(_upath) < 7200):
                _undo = ('<button class="mini planundo needs-server" id="planundo"'
                         ' title="Reverse the last plan edit">&#8617; Undo</button>')
        except Exception:
            pass
        # Two kicks or more and the day has visibly drifted from the plan \u2014
        # offer the re-rank, never run it unasked.
        _resug = ""
        if len(re.findall(r"^\s*-\s+\d\d:\d\d kicked ", today_md or "", re.M)) >= 2:
            _resug = ('<button class="mini planresug needs-server" data-job="today"'
                      ' title="The day has drifted from this morning&rsquo;s plan. '
                      f'Have {AG.short()} re-rank what is left">'
                      "Resuggest the rest of today</button>")
        # The weather, above the plan, with the place named in it. She moves
        # between four houses across the year, and a forecast for the one she
        # left on Tuesday looks exactly like a forecast for the one she is in
        # — naming the place is the only thing that stops this quietly lying.
        _wparts, _wfull = [], ""
        try:
            import weather as WX
            _wparts = WX.glance()
            _wfull = (WX.place() or {}).get("place", "")
        except Exception:
            _wparts = []
        if _wparts:
            # Icons and numbers, the words on hover (her ask, 28 Sep: the
            # sentence took reading). The place stays the first chip.
            _wparts[0]["title"] = (_wfull + ". This is where the brain "
                                   "thinks you are, so tell "
                                   f"{AG.short()} when you move")
            # The declared season of work rides on the same line as the
            # place: both are the brain's beliefs about "right now", and a
            # stale one must be visible to be corrected.
            _nowc = cfg.get("now") or {}
            if _nowc.get("phase"):
                _nu = M.parse_date(_nowc.get("until"))
                _wk = (max(1, -(-(_nu - today).days // 7))
                       if _nu and _nu >= today else None)
                _wparts.append({
                    "icon": "cap" if "School" in (_nowc.get("areas") or [])
                    else "calendar", "kind": "phase",
                    "text": _nowc["phase"] + (f" · {_wk} wk" if _wk else ""),
                    "title": _nowc["phase"] + (" until " + _nu.strftime("%a %d %b")
                                               if _nu else "")})
            V["today"].append(glance_row(_wparts))
        # Tasks proposed from her whitelisted mail, waiting on a yes/no. This
        # belongs on Today, not in the settings panel where the whitelist
        # lives: it is a thing asking for her attention, not a setting.
        _mt_html = _mailtasks_tray(cfg, bare=True)
        if _mt_html:
            tray_confirm.append(tray_item(
                "mail", "confirm", "Found in your mail", _mt_html,
                _mt_html.count('class="mtrow"')))
        _sc_html = _school_tray(cfg, part="rows")
        if _sc_html:
            tray_confirm.append(tray_item(
                "slides", "confirm", "Found in your class folder", _sc_html,
                _sc_html.count('class="mtrow"')))
        # School has its own tab; on Today its due work sits in "Also due"
        # with every other front's, and today's classes are in When (7 Oct).
        V["school"].append(school_view(cfg))
        # Tasks whose moment has passed, asking to be closed — never closed
        # by the machine on its own.
        _pd_html = _probablydone_tray(b["live"], bare=True)
        if _pd_html:
            tray_confirm.insert(0, tray_item(
                "done", "confirm", "Probably done?", _pd_html,
                _pd_html.count('class="pdrow"')))
        # The page's own questions (8 Oct audit): did it happen, why does it
        # keep slipping, is this front finished. At most three, one tap each,
        # ahead of the questions.md ones because each carries its evidence.
        import tab_asks as ASKS
        tray_answer[:0] = ASKS.ask_items(b["live"], cfg)
        # A free weekend, offered with two season ideas that fit (9 Oct, her
        # ask: the season list was never suggested unless a plan had room).
        try:
            _fw = _free_weekend(cfg, today)
            if _fw:
                tray_answer.append(_fw)
        except Exception:                                # noqa: BLE001
            pass
        # What changed in the calendar (8 Oct, calendar_watch.py): an event
        # that left it, or a meeting task whose person isn't in it that day.
        # Asked, never acted on; right after "Probably done?", since both
        # are about days that are here now.
        _cal_q = []
        if cfg.get("calendar"):
            try:
                import calendar_watch as CW
                _cw = CW.look(today)
                _seen_ids = set(cfg.get("tray_seen") or [])

                def _dayname(iso):
                    _d = M.parse_date(iso)
                    _n = (_d - today).days if _d else None
                    return ("today" if _n == 0 else "tomorrow" if _n == 1
                            else _d.strftime("%A %-d %b") if _d else iso)

                def _clean(t):
                    return MD.plain(re.sub(r"\s*\((?:due|waiting until|urgent)[^)]*\)", "",
                                           re.sub(r"~\s*(?:\d+h\d*|\d+m)\b", "", t))).strip()
                for _g, _tt, _tw in CW.touches(_cw["gone"], ws):
                    _cqid = "calgone-" + MD.taskkey(_g["iso"] + _g["title"])
                    if _cqid in _seen_ids:
                        continue
                    _key = MD.taskkey(MD.bare(_tt)) if _tt else ""
                    _cal_q.append(tray_item(
                        _cqid, "confirm", "Gone from your calendar: " + _g["title"],
                        '<div class="pdrow"><span class="pdtext">'
                        + e(_g["title"]) + ", " + e(_dayname(_g["iso"]))
                        + (" at " + e(_g["hhmm"]) if _g["hhmm"] else "")
                        + ", is no longer in your calendar."
                        + (" The task &ldquo;" + e(_clean(_tt)) + "&rdquo; may be off too."
                           if _tt else "") + "</span>"
                        + (f'<button class="mini" data-pdact="drop" data-pdkey="{_key}">'
                           "Drop the task</button>" if _tt else "")
                        + f'<button class="mini" data-trayseen="{e(_cqid)}">Got it</button></div>'))
                for _o in CW.orphans(ws, _cw["now"], today):
                    _key = MD.taskkey(MD.bare(_o["text"]))
                    _cqid = "calnot-" + _key
                    if _cqid in _seen_ids:
                        continue
                    _cal_q.append(tray_item(
                        _cqid, "confirm", "Not in your calendar: " + _clean(_o["text"]),
                        '<div class="pdrow"><span class="pdtext">&ldquo;'
                        + e(_clean(_o["text"])) + "&rdquo; is due " + e(_dayname(_o["iso"]))
                        + ", and nothing in your calendar that day mentions "
                        + e(_o["name"]) + ". Is it still on?</span>"
                        f'<button class="mini" data-pdact="drop" data-pdkey="{_key}">'
                        "Cancelled, drop it</button>"
                        f'<button class="mini" data-trayseen="{e(_cqid)}">Still on</button></div>'))
            except Exception:                            # noqa: BLE001
                _cal_q = []
        _at = 1 if _pd_html else 0
        tray_confirm[_at:_at] = _cal_q
        _pstamp = _plan_time()
        # One quiet bar on the title's line: the stamp is a fact, not a
        # control, so it reads as faint text beside the button (7 Oct: as a
        # pill on its own row it looked like a second button).
        V["today"].append('<section id="today" class="todaywrap"'
                          + (' data-stale="1"' if stale_plan else '') + '>')
        if today_md.strip():
            # The daily update (her priority, 24 Sep): the brain sees the
            # laptop and nothing else. Gone once today's update is in —
            # counted from the queue, so the phone and the page agree.
            # It comes before the plan bar: the bar floats on the plan
            # title's line, and with the update between them it sat on a
            # row of its own above it (8 Oct, her ask).
            _upd_in = date.today() in M.update_days(since_days=1)
            V["today"].append(
                '<div class="updnudge" id="updnudge" hidden'
                + (' data-done="1"' if _upd_in else '') + '><span>'
                + ico("mic") + '<b>Daily update</b> &middot; what happened '
                'away from the laptop?</span>'
                '<button class="mini" id="updgo">Tell the brain</button>'
                '<button class="mini" id="updlater">Later</button></div>')
        V["today"].append('<div class="planbar">'
                     + ('<span class="skinx skinx-planstamp">'
                        + (f"{plan_day:%A}&rsquo;s plan" if stale_plan
                           else "plan updated " + _pstamp) + "</span>"
                        if (_pstamp or stale_plan) else "")
                     + _resug + _undo
                     + '<button class="mini planrefresh needs-server" id="planrefresh"'
                     f' title="Have {AG.short()} rewrite today&rsquo;s plan from the brain as it'
                     ' stands now. This runs on your subscription.">'
                     "&#8635; Refresh plan</button></div>")
        if today_md.strip():
            # People and workstreams named in the plan are doors: Casey opens
            # her People row, a project opens its drawer.
            # The evening check — the accountability half of the loop. After
            # 17:00 (JS gates it) the plan turns into a mirror: what landed,
            # and a spoken decision for everything that didn't. Carry rolls it
            # into tomorrow deliberately; Drop retires it out loud. Nothing
            # silently vanishes, nothing silently piles up.
            #
            # The decisions are NOT a second copy of the list. They ship as
            # templates keyed by the same MD.taskkey the plan's own rows
            # already carry, and the JS grafts them onto those rows at 17:00 —
            # one list, two modes. Printing today's four tasks again directly
            # under the plan is what made the evening page read as a stutter,
            # and a done/carrying/dropped row needs nothing here at all: the
            # plan's own row says so already.
            ev_tpl, ev_done, ev_open = [], 0, 0
            for ln in today_md.split("\n"):
                mt = re.match(r"^\s*[-*]\s+\[([ xX])\]\s+(.*)$", ln)
                if not mt:
                    continue
                raw = mt.group(2)
                if MD.DROPPED.search(raw) or MD.CARRYING.search(raw) \
                        or MD.UNTIL.search(raw):
                    continue
                if mt.group(1).lower() == "x":
                    ev_done += 1
                    continue
                key = MD.taskkey(MD.bare(raw))
                ev_open += 1
                ev_tpl.append(
                    f'<template class="evtpl" data-evkey="{key}">'
                    f'<button class="mini evact" data-evact="carry" data-evkey="{key}"'
                    ' title="Still matters: move it into tomorrow&rsquo;s plan">Carry &#8594;</button>'
                    f'<button class="mini evact" data-evact="drop" data-evkey="{key}"'
                    ' title="Turned out not to be yours: retire it, and the plan keeps a note that you did">Drop</button>'
                    "</template>")
            _pl = (f"{plan_day:%A}&rsquo;s plan" if stale_plan
                   else "today&rsquo;s plan")
            if ev_done or ev_open:
                # Say WHERE the decision happens. "The open ones need a
                # decision" left her asking what to do with the box (31 Aug)
                # — the buttons this section grafts live on the plan's own
                # rows below, and the copy has to point there.
                if not ev_open:
                    head = f"Everything on {_pl} is done."
                elif not ev_done:
                    head = (f"Nothing on {_pl} is ticked. Close "
                            "each line below: <b>Carry &#8594;</b> "
                            "moves it into tomorrow, <b>Drop</b> retires it.")
                else:
                    head = (f"{ev_done} of {ev_done + ev_open} landed. Close "
                            "the rest on their lines below: <b>Carry &#8594;</b> "
                            "moves one into tomorrow, <b>Drop</b> retires it.")
                # Above the list, not below it: the count is a frame for the
                # rows it describes, and putting it under them was half of why
                # the page looked like it started the day over.
                # Then the box asks how it went, and keeps the answer as
                # the journal, in her words (the close's second half).
                ev_html = (
                    '<section class="evwrap" id="evening" hidden>'
                    '<h3 class="area">How did '
                    + (f"{plan_day:%A}" if stale_plan else "today")
                    + ' go?</h3>'
                    f'<p class="evhead">{head}</p>'
                    '<button class="mini evjournal needs-server" data-box'
                    ' data-box-intent="journal">&#10022; Say how it went</button>'
                    + "".join(ev_tpl) + "</section>")
            else:
                ev_html = ""
            doc_html = linkify_html(MD.render(today_md, task_source="today.md",
                                              ws_lookup=plan_ws_lookup(ws, cfg),
                                              row_extra=plan_reading))
            # The evening check sits under the day's title and summary, just
            # above the first list: above the title it pushed the day's name
            # down the card and read as the card's headline (7 Oct).
            _h2 = doc_html.find("<h2")
            doc_html = (doc_html[:_h2] + ev_html + doc_html[_h2:] if _h2 >= 0
                        else ev_html + doc_html)
            # The plan's chases join the owed replies in Quick replies below:
            # "Two-minute chases" here and "Two-minute sweep" under the plan
            # were one idea under two names (28 Sep review, fixed 7 Oct). The
            # rows keep their ticks; an empty "None today" note just goes.
            _mc = re.search(r'<h2[^>]*>\s*Two-minute chases\s*</h2>\s*'
                            r'(<ul class="tasks">.*?</ul>|<p>.*?</p>)\s*',
                            doc_html, re.S)
            if _mc:
                if _mc.group(1).startswith("<ul"):
                    plan_chases = _mc.group(1)
                doc_html = doc_html[:_mc.start()] + doc_html[_mc.end():]
            V["today"].append('<div class="todaydoc doc">' + doc_html + "</div>")
            # What this plan looked at, from the run's own record (8 Oct,
            # her ask: the plan had no way to show its sources).
            try:
                import plan_sources as _PS
                V["today"].append(_PS.fold_html(today_md, e))
            except Exception:                            # noqa: BLE001
                pass
            V["today"].append(week_strip(cfg, today, day_md))
        # Below the plan: every front of her life, short ranked lists.
        V["today"].append(fronts_block(b["live"], cfg, PLAN_TOKS,
                                       shown_already, claim))
        # Everything else due, once (the fewer-doors plan, 7 Oct): every open
        # task due by the day after tomorrow, late ones included, grouped by
        # area with each area's extra rows folded. It replaced four cards that
        # each showed a slice of due work — School today (its late work only
        # as a count), the quick wins (stopped at eight), the week ahead's
        # lists, and the plan's optional "then" section — so her rule holds:
        # nothing due is left off, and nothing shows twice. Built live from
        # the fronts, it can't go stale after the morning plan. Expired tasks
        # (a class or meeting date gone by) wait in For you's "Probably done?".
        _soon = today + timedelta(days=2)
        # The plan's own tickable rows. A late task is skipped only when it
        # is one of them: one the plan merely names ("Not today, and why")
        # still belongs in the late count, or Today and the Week disagree.
        _plan_rows = [_sig_tokens(_m.group(1)) for _m in re.finditer(
            r"(?m)^\s*[-*]\s+\[[ xX]\]\s+(.*)$", today_md)]
        due_items = []
        for w in ws:
            if not w.get("live"):
                continue
            for t in w["tasks"]:
                if (t["done"] or t.get("parked") or t.get("dropped")
                        or t.get("expired") or not t.get("due")):
                    continue
                _dd = M.parse_date(t["due"])
                if not _dd or _dd > _soon:
                    continue
                if (any(_same_thing(t["text"], _r) for _r in _plan_rows if _r)
                        if _dd < today else shown_already(t["text"])):
                    continue
                due_items.append({"t": t, "w": w, "d": _dd})
        for _q in due_items:
            claim(_q["t"]["text"])
        # Late work is listed too, folded behind one line: seventeen overdue
        # tickboxes above the plan made a second to-do list on 24 Sep, and a
        # count she couldn't open hid them. The line's figure is counted from
        # these same rows, so the number and the list never disagree.
        _late_items = [q for q in due_items if q["d"] < today]
        _soon_items = [q for q in due_items if q["d"] >= today]
        rlab = room_labels(cfg)

        def _due_row(q):
            return taskrow(q["t"], "workstreams.md", q["w"]["name"],
                           show_ws=True,
                           ws_label=rlab.get(q["w"]["name"], ""))
        _by = (lambda q: (q["d"], -(q["t"].get("pressure") or 0),  # noqa: E731
                          q["t"]["text"]))
        if _soon_items:
            sweep_quick = area_groups(_soon_items,
                                      lambda q: q["w"].get("area"), _by, _due_row)
        if _late_items:
            _dflt = M.capacity_cfg(cfg)["default_task_minutes"]
            _m = sum(q["t"].get("est") or _dflt for q in _late_items)
            _amt = (f"about {round(_m / 60)} hours" if _m >= 90 else
                    "about an hour" if _m >= 50 else f"{_m} minutes")
            _n = len(_late_items)
            late_fold = (
                '<details class="behind" id="behind"><summary>'
                f'<b>{_n} late task{"s" if _n != 1 else ""}</b>, {_amt} of work'
                '</summary>'
                + area_groups(_late_items, lambda q: q["w"].get("area"),
                              _by, _due_row)
                + '<p class="behindgo"><a class="mini" href="#/plate">'
                'Re-date or drop some &rarr;</a></p></details>')
        # What the day actually held, from the marks it left: commits in the
        # project folders, ticks, Touched dates, drafts. Evening only — at
        # nine in the morning it is a card about nothing, and the plan is
        # what matters then. It reports and does not grade: the plan already
        # says what is undone, and saying it twice is nagging with a second
        # voice.
        # Built from midday so it is there whatever hour the page was last
        # rebuilt; the page shows it from 17:00 on her own clock (page.css,
        # body[data-eve]).
        if datetime.now().hour >= 12:
            try:
                import day as DAY
                dd = DAY.gather(today)
            except Exception:
                dd = None
            if dd and (dd["projects"] or dd["ticked"] or dd["touched"]
                       or dd["drafts"] or dd.get("answered")
                       or dd.get("files")):
                rows = []
                # Names on the face, the counts in each name's tooltip:
                # "The brain (82)" and a row called "Uncommitted" were the
                # machine's words, not hers (28 Sep review).
                #
                # Files changed on disk — the half of a working day that
                # never reaches a commit. Three of her folders are not
                # repositories at all, so an afternoon on a client
                # dossier used to leave no trace anywhere in the brain.
                # Work sitting uncommitted in an app's folder is still work
                # on that app, so it joins "Worked on" (the tooltip says which).
                ch = [p for p in (dd.get("files") or [])
                      if p["kind"] == "changed"]
                un = {p["place"]: p["n"] for p in (dd.get("files") or [])
                      if p["kind"] == "uncommitted"}
                worked = []
                for p in dd["projects"][:4]:
                    n = len(p["commits"])
                    tip = f'{n} commit{"s" if n != 1 else ""} today'
                    if un.get(p["project"]):
                        k = un.pop(p["project"])
                        tip += (f', and {k} file{"s" if k != 1 else ""}'
                                " changed, not committed yet")
                    worked.append((p["project"], tip))
                for place, k in list(un.items())[:3]:
                    worked.append((place, f'{k} file{"s" if k != 1 else ""} '
                                   "changed, not committed yet"))

                def _names(pairs):
                    return ", ".join(f'<span title="{e(t)}">{e(n)}</span>'
                                     for n, t in pairs)
                if worked:
                    rows.append("<dt>Worked on</dt><dd>" + _names(worked)
                                + "</dd>")
                if ch:
                    rows.append("<dt>Files changed</dt><dd>" + _names(
                        (p["place"], f'{p["n"]} file{"s" if p["n"] != 1 else ""}'
                         " changed today") for p in ch[:4]) + "</dd>")
                if dd["ticked"]:
                    # Whole titles, clamped to two lines in CSS (page.md):
                    # a hard slice at 70 printed "20 Oct mo…" (28 Sep).
                    items = "".join(
                        f'<li title="{e(t["text"])}">' + e(t["text"])
                        + "</li>" for t in dd["ticked"][:5])
                    more = (f'<li class="dmore">+{len(dd["ticked"]) - 5} more</li>'
                            if len(dd["ticked"]) > 5 else "")
                    rows.append("<dt>Closed</dt><dd><ul class='dayl'>"
                                + items + more + "</ul></dd>")
                if dd.get("answered"):
                    n_a = dd["answered"]
                    rows.append("<dt>Answered</dt><dd>"
                                f"{n_a} open question{'s' if n_a > 1 else ''}"
                                "</dd>")
                other = [w for w in dd["touched"]
                         if not any(w == p["project"] for p in dd["projects"])]
                if other:
                    rows.append("<dt>Also moved</dt><dd>"
                                + e(", ".join(other[:5])) + "</dd>")
                if dd["drafts"]:
                    rows.append("<dt>Wrote</dt><dd>"
                                + e("; ".join(dd["drafts"][:3])) + "</dd>")
                daycard_ix = len(V["todayrail"])
                V["todayrail"].append(
                    '<section class="railcard daycard">'
                    '<h3 class="area">Today, so far</h3>'
                    '<dl class="dayd">' + "".join(rows) + "</dl>"
                    # A footnote, not a .meta: the skins draw .meta as a
                    # bordered chip, and this read as a button (28 Sep).
                    '<p class="dayfoot">Taken from your project folders and '
                    'ticks. Tell the brain what else you did.</p>'
                    "</section>")
        # Today's rhythm: the non-computer half of the day in one card —
        # the habits to tick, tonight's dinner, today's routine lines. Her
        # named failure mode is the laptop eating these; they sit beside the
        # plan so they are never a page away. The habits' history lives on
        # Life, where there is room to look back.
        _rhythm = rhythm_lines(today, today_md)
        if habits or _rhythm:
            V["todayrail"].append('<section class="railcard rhythmcard">'
                                  '<h3 class="area">Today&rsquo;s rhythm</h3>'
                                  + ('<div class="habits2">' if habits else ""))
        if habits:
            for hb in habits:
                cls = ("done" if hb["done_today"]
                       else ("late" if not hb["on_track"] else ""))
                # An auto habit counts itself (a journal entry for the day is
                # the tick), so it gets a mark, not a button — nothing to
                # press, nothing to forget.
                if hb.get("auto"):
                    tickel = (
                        '<span class="h2tick auto" title="This one ticks '
                        'itself when you write an entry for the day">'
                        f'{"&#10003;" if hb["done_today"] else ""}</span>')
                else:
                    tickel = (
                        f'<button class="h2tick needs-server" data-habit="{e(hb["name"])}"'
                        f' aria-pressed="{"true" if hb["done_today"] else "false"}"'
                        f' title="{"Done today" if hb["done_today"] else "Did it today"}">'
                        f'{"&#10003;" if hb["done_today"] else ""}</button>')
                # A routine wears its steps as the reminder they are. Two
                # missed days running and it shows the FLOOR instead: the
                # short version that survives a hotel or a morning on campus.
                # Standing there at full size after a bad week is how a
                # routine turns into a thing you have already failed.
                steps = hb.get("steps") or []
                floor = hb.get("floor") or []
                # Which days are floor days (slipping, or just moved house)
                # is model.py's call. A plain habit with a floor shows a line
                # only then; a routine shows its steps the rest of the time.
                show = floor if hb.get("floor_day") else steps
                is_floor = bool(show) and show is floor
                # The cue leads the line: the moment it follows, which comes
                # along between houses where an hour does not.
                cue = hb.get("cue") or ""
                line = " · ".join(show)
                if cue:
                    line = cue + (": " + line if line else "")
                stepline = ""
                if line:
                    stepline = (
                        f'<span class="h2steps{" floor" if is_floor else ""}"'
                        + (' title="The short version, which counts as done">'
                           if is_floor else '>')
                        + e(line) + "</span>")
                # Spare days as dots beside the count: filled while they
                # last, hollow once spent. A reserve works because it is
                # seen (model.py has the why).
                spare = ""
                if hb.get("spares"):
                    left = hb["spares_left"]
                    tip = (f'{left} spare day{"" if left == 1 else "s"} left '
                           "this week" if left
                           else "No spare days left this week")
                    spare = (f'<span class="h2spare" title="{tip}">'
                             + "<i></i>" * left
                             + '<i class="used"></i>' * (hb["spares"] - left)
                             + "</span>")
                V["todayrail"].append(
                    f'<div class="habit2 {cls}">' + tickel +
                    f'<span class="h2name">{e(hb["name"])}</span>'
                    f'<span class="h2count">{hb["week_count"]}/{hb["target"]}</span>'
                    + spare +
                    f'<button class="hmenu needs-server" data-habittarget="{e(hb["name"])}"'
                    f' data-target="{hb["target"]}" aria-label="Change the weekly target">'
                    "&#8943;</button>" + stepline + "</div>")
            V["todayrail"].append("</div>")
        if habits or _rhythm:
            V["todayrail"].append(
                (f'<div class="rhlines">{_rhythm}</div>' if _rhythm else "")
                + "</section>")
        V["today"].append("</section>")
        # Under the plan: the Friday hour on its day, then everything else
        # due, then Quick replies — the plan's chases and the replies she
        # owes — then For you.
        V["today"].append(friday_block(b, cfg, today))
        # A reply the plan already chases is not owed twice on one screen.
        if plan_chases and _owed_close:
            _pc = re.sub(r"<[^>]+>", " ", plan_chases).lower()

            def _chased(r):
                m = re.search(r'class="dname">Reply to ([^<]+)<', r)
                return bool(m) and m.group(1).split()[0].lower() in _pc
            sweep_reply = "".join(r for r in _orows if not _chased(r))
        # Job-hunt chases ride with the owed replies: the same two-minute
        # kind of job (a note to someone who has gone quiet).
        try:
            import tab_jobs
            sweep_reply += tab_jobs.sweep_rows(cfg, today)
        except Exception:                                # noqa: BLE001
            pass
        if sweep_quick or late_fold:
            V["today"].append(
                '<section class="alsodue" id="alsodue">'
                + (f'<h3 class="area">Also due by {_soon:%A}</h3>' + sweep_quick
                   if sweep_quick else "")
                + late_fold + "</section>")
        if sweep_reply or plan_chases:
            V["today"].append(
                '<section class="sweep" id="sweep">'
                '<h3 class="area">Quick replies</h3>'
                + plan_chases
                + (f'<div class="swreply">{sweep_reply}</div>' if sweep_reply else "")
                + "</section>")
        V["today"].append("<!--FORYOU-->")

    # The fronts: each area of her life by the last time anything in it
    # moved, longest-quiet on top. Productive procrastination starves a
    # front silently — this card is where the starving shows.
    if b["live"]:
        fronts = {}
        for w in b["live"]:
            t = M.parse_date(w.get("touched") or "")
            prev = fronts.get(w["area"])
            if t and (prev is None or t > prev):
                fronts[w["area"]] = t
            else:
                fronts.setdefault(w["area"], None)
        frows = []
        for name, t in sorted(fronts.items(),
                              key=lambda kv: kv[1] or date.min):
            days = (today - t).days if t else None
            sev = ("f-never" if days is None else
                   "f-fresh" if days <= 2 else
                   "f-ok" if days <= 7 else
                   "f-warm" if days <= 14 else "f-cold")
            lab = "never" if days is None else ago(days)
            frows.append(f'<div class="frow {sev}"><i class="fdot"{LN.attrs(name)}></i>'
                         f'<span class="fname">{e(name)}</span>'
                         f'<span class="fago">{lab}</span></div>')
        fronts_html = (
            '<h3 class="area fr2">Where your attention went</h3>'
            + "".join(frows)
            + '<p class="hnote">Each area of your life, with the one '
            "that has been quiet longest at the top.</p>")
        if daycard_ix is not None:
            # Evening: ride inside "Today, so far" — one box about the day,
            # not two side by side saying overlapping things.
            card = V["todayrail"][daycard_ix]
            assert card.endswith("</section>")
            V["todayrail"][daycard_ix] = (card[:-len("</section>")]
                                          + fronts_html + "</section>")
        else:
            V["todayrail"].append(
                '<section class="railcard">' + fronts_html + "</section>")

    # The three horizons, directly under the plan.
    #
    # A deadline beats an ambition every single morning, so drawing the day's
    # work off one sorted stack means the ambition never gets a morning at
    # all. The pools are the fix, and they only work if she can SEE them —
    # which is also the only place "nothing is forcing this" can be said out
    # loud without it reading as nagging.
    if b["live"]:
        pools = {"now": [], "push": [], "slow": []}
        for w in b["live"]:
            if w.get("batched"):
                continue          # waits for its weekly hour, not a lane
            pools.get(w.get("horizon") or "slow", pools["slow"]).append(w)
        # Named after what to do with each lane, the way the Eisenhower
        # matrix names its boxes; its "hand it off" box has no lane here,
        # since nothing in the brain hands work on. The third lane holds
        # Family and Health on a quiet week, so it never says "can wait"
        # (her pick, 9 Oct: the old names read as written by a model).
        HZ = (("now", "Do now",
               "a date is close, or it's late"),
              ("push", "Your focus",
               "you picked it, or a finish line is near"),
              ("slow", "No date yet",
               "give it one, or let it go"))
        hrows = []
        for kind, title, note in HZ:
            pool = pools[kind]
            n = len(pool)
            # The "now" lane sorts exactly the way the hero does, so pool[0]
            # was structurally incapable of showing anything but the hero —
            # the same errand, twice, a screen apart. Skip the hero and the
            # lane finally says something the top of the page didn't. Anything
            # whose next move is already on the page goes too: a lane exists to
            # add a name, and repeating one adds nothing.
            if kind == "now":
                fresh = [w for w in pool if not shown_already(next_line(w))]
                pool = fresh or pool
            if not pool:
                # An empty pool is information: say it, don't drop the lane.
                hrows.append(
                    f'<div class="hzrow hz-{kind} hz-empty">'
                    f'<span class="hzkind" title="{e(note)}">{title}</span>'
                    '<span class="hznone">'
                    + ("everything with a date on it is already above"
                       if kind == "now" and n else
                       "nothing is close to its date"
                       if kind == "now" else
                       "no focus set: pick something and it gets a slot"
                       if kind == "push" else
                       "everything has a date or a focus")
                    + "</span></div>")
                continue
            n = len(pool)
            # Within a horizon, whoever has waited longest earns the slot —
            # except in "now", where the loudest does.
            pick = (pool[0] if kind == "now" else
                    max(pool, key=lambda w: (w.get("days_untouched") or 0,
                                             w.get("goal_pull") or 0)))
            nxt = pick.get("next_action") or pick.get("pressed_task") or ""
            if not nxt:
                open_t = [t for t in pick["tasks"]
                          if not t["done"] and not t.get("parked")
                          and not t.get("dropped")]
                nxt = open_t[0]["text"] if open_t else ""
            claim(nxt)
            claim(pick["name"])
            days = pick.get("days_untouched")
            since = (f"untouched {span(days)}" if days else "not started")
            if kind == "now":
                d = pick.get("pressed_act_days")
                if d is not None:
                    since = (f"{abs(d)}d late" if d < 0
                             else "act today" if d == 0
                             else f"act within {d}d")
            goal = ""
            if pick.get("goal_text") and pick.get("goal_days") is not None:
                goal = (f'<span class="hzgoal">{e(clip(pick["goal_text"], 90))} '
                        f'&middot; ' + (f'in {pick["goal_days"]}d'
                                       if pick["goal_days"] >= 0
                                       else f'{-pick["goal_days"]}d late')
                        + '</span>')
            # Under the work, not the lane label, with the others named on
            # hover (28 Sep review: it sat alone in the left column).
            others = [w2["name"] for w2 in pool if w2 is not pick]
            more = (f'<span class="hzmore" title="{e(", ".join(others))}">'
                    f'+{n - 1} more</span>' if n > 1 else "")
            # EVERY lane gets a verb, not just the slow one. Naming three
            # starving things and offering a button on one of them is a list
            # of complaints with a single exit — and the two silent lanes were
            # the ones with a clock on them.
            #
            # The verb differs because the need does. A dated thing wants
            # doing, so it gets the ✦ that hands the legwork to Claude; the
            # one she already chose wants the same; the one nothing is forcing
            # wants promoting into the week before it can be worked on at all.
            if kind == "slow":
                act = ('<button class="mini hzpush needs-server" '
                       f'data-ws="{e(pick["name"])}">Push this week &rarr;</button>')
            elif nxt:
                act = ('<button class="mini hzstart needs-server" '
                       f'data-claudestart="{e(nxt)}" data-claudews="{e(pick["name"])}"'
                       f' title="{AG.short()} starts the legwork on this now, such as '
                       'looking up options or drafting a message. '
                       'It never sends anything.">&#10022; Start it</button>')
            else:
                # The card lives on the Plate now, so #/plate went nowhere:
                # open the project's own drawer instead.
                act = (f'<a class="mini hzopen" href="#/plate"'
                       f' data-wsopen="{e(pick["name"])}">Open it &rarr;</a>')
            # Three columns — the lane, the work, the verb. Laid out as one
            # grid of loose spans, the lane's two-line "21 days past the
            # moment to act" stretched whichever row of the work it sat
            # beside, so the goal line floated a gap below Next on one lane
            # and sat tight on the next (28 Sep).
            hrows.append(
                f'<div class="hzrow hz-{kind}">'
                f'<div class="hzlane"><span class="hzkind" title="{e(note)}">{title}</span>'
                f'<span class="hzsince">{since}</span></div>'
                f'<div class="hzbody"><a class="hzname" href="#/plate"'
                f' data-wsopen="{e(pick["name"])}">'
                f'{e(clip(pick["name"], 40))}</a>'
                # "Next" turns a description into an instruction. The line was
                # already the next action; nothing on the row said so, so it
                # read as a subtitle and got skipped.
                + (f'<span class="hznext"><b>Next</b>{e(nxt)}</span>'
                   if nxt else "")
                + goal + more
                + f'</div><div class="hzact">{act}</div>'
                + "</div>")
        V["today"].append(
            '<section class="hzcard">'
            + cardhead('<div><p class="eyebrow">Your three '
                       'horizons</p><span class="wav"></span></div>',
                       artvid("kite", 46))
            + "".join(hrows)
            + '</section>')

    # Offers stay beside the plan (they are work); questions and the forecast
    # move to the awareness rail — status never outranks action.
    V["today"].extend(build_offers())

    # What the ranking cannot see. The scorer's failure is silent by nature: a
    # task whose deadline lives in its words rather than its marker does not
    # rank low with a warning, it ranks as though it had no deadline. Saying
    # so — with the fix one tap away — is the difference between a ranking she
    # can trust and one she has to second-guess.
    spots = M.blind_spots(ws, cfg=cfg, today=today)
    gaps = M.prep_gaps(ws, cfg=cfg, today=today)
    if spots or gaps:
        # A filing due next February does not belong on today's page. Near
        # gaps only — the far ones keep their weight and wait their turn.
        dates = [s for s in spots
                 if s["kind"] == "prose_date" and s["weight"] >= 70][:3]
        expired = [s for s in spots if s["kind"] == "expired"][:3]
        vague = [s for s in spots if s["kind"] == "vague"][:2]
        # Two a day at most, soonest first: a dozen rewordings at once is a
        # chore list, not help.
        unclear = sorted((s for s in spots if s["kind"] == "unclear"),
                         key=lambda s: (s["days"] is None, s["days"] or 0,
                                        -s["weight"]))[:2]
        goalless = [s for s in spots if s["kind"] == "no_goal"]
        rows = []

        def _chip(s):
            # Every task shown away from its front names it (page.md).
            return f'<span class="fc-proj">{e(clip(s.get("room") or s["ws"], 40))}</span>'
        # Soonest first, and a commitment happening tomorrow with nothing
        # readying her for it outranks any missing marker.
        for g in gaps[:2]:
            when = "today" if g["days"] == 0 else (
                "tomorrow" if g["days"] == 1 else f'in {g["days"]} days')
            # The prep wants doing before the thing, so it is due the day
            # before — or right now if the thing is already tomorrow.
            due = max(today, date.fromisoformat(g["when"]) - timedelta(days=1))
            # This becomes a real line in her file, so it has to read like one
            # she wrote: the event's own words, first sentence only, no
            # parenthetical address and no trailing ellipsis.
            label = re.sub(r"\s*\([^)]*\)", "", g["event"])
            label = re.split(r"(?<=[a-z0-9])\.\s", label)[0]
            label = label.replace(":", "").strip(" .,-—")
            if len(label) > 58:
                label = label[:58].rsplit(",", 1)[0].rstrip(" ,")
            if len(label) > 90:
                # The event line now comes whole (prep_gaps); the task made
                # from it stays a line, ending on a word.
                label = label[:90].rsplit(" ", 1)[0].rstrip(" ,")
            rows.append(
                '<div class="bspot"><div class="bstext">'
                f'<b title="{e(g["event"])}">{e(g["event"])}</b>'
                f'<span class="bswhy">Happens {when}, with nothing on your '
                'plate to get ready.</span></div>'
                '<div class="bsfix"><button class="mini bsprep needs-server" '
                f'data-ws="{e(g["ws"])}" data-due="{due.isoformat()}" '
                f'data-text="Prep: {e(label)}">'
                'Add the prep</button></div></div>')
        for s in dates:
            key = MD.taskkey(s["task"])
            guess = ""
            if s.get("days") is not None:
                g = today + timedelta(days=s["days"])
                guess = g.isoformat()
            rows.append(
                '<div class="bspot"><div class="bstext">'
                f'<b title="{e(s["task"])}">{e(s["task"])}</b>{_chip(s)}'
                # "carries no date" read as a flat contradiction to a line
                # that plainly says "4–7 September". The date is THERE, in
                # the sentence; the due date is what is missing. One plain
                # line (28 Sep review: the old one explained the sorter).
                f'<span class="bswhy">Says &ldquo;{e(s.get("saw", ""))}&rdquo; but '
                'has no due date, so it sorts too low.</span></div>'
                f'<div class="bsfix"><input type="date" class="bsdate" value="{guess}" '
                f'aria-label="date for {e(clip(s["task"], 40))}">'
                f'<button class="mini bsgo needs-server" data-bskey="{key}">'
                'Set it</button></div></div>')
        for s in expired:
            key = MD.taskkey(s["task"])
            rows.append(
                '<div class="bspot"><div class="bstext">'
                f'<b title="{e(s["task"])}">{e(s["task"])}</b>{_chip(s)}'
                '<span class="bswhy">Its date has passed.</span></div>'
                f'<div class="bsfix"><button class="mini bsdrop needs-server" '
                f'data-bskey="{key}">Retire it</button></div></div>')
        for s in vague:
            # The task panel already rewords a line and keeps its date,
            # estimate and urgency; .fc-task opens it for a task named by its
            # words rather than by a row on this page.
            rows.append(
                '<div class="bspot"><div class="bstext">'
                f'<b title="{e(s["task"])}">{e(s["task"])}</b>{_chip(s)}'
                '<span class="bswhy">No first step in its words, so it tends '
                'to wait.</span></div>'
                '<div class="bsfix"><button class="mini fc-task needs-server" '
                'data-src="workstreams.md" '
                f'data-task="{MD.taskkey(s["task"])}" '
                f'data-text="{e(s["task"])}" data-ws="{e(s["ws"])}">'
                'Reword</button></div></div>')
        for s in unclear:
            # Her 8 Oct feedback ("Gate: segment scoring…", "M4 —…"): a line
            # she has to decode. With a wording the brain drafted, taking it
            # is one tap and keeps the date, size and urgency (serve.py's
            # "reword" action, which also notes the old words under it).
            key = MD.taskkey(s["task"])
            if s.get("suggest"):
                why = f'Clearer: &ldquo;{e(s["suggest"])}&rdquo;'
                act = ('<button class="mini go bsuse needs-server" '
                       f'data-bskey="{key}" data-until="{e(s["suggest"])}">'
                       'Use this wording</button>')
            else:
                why = f'It {e(s["says"])}.'
                act = ('<button class="mini fc-task needs-server" '
                       f'data-src="workstreams.md" data-task="{key}" '
                       f'data-text="{e(s["task"])}" data-ws="{e(s["ws"])}">'
                       'Reword</button>')
            rows.append(
                '<div class="bspot"><div class="bstext">'
                f'<b title="{e(s["task"])}">{e(s["task"])}</b>{_chip(s)}'
                f'<span class="bswhy">{why}</span></div>'
                f'<div class="bsfix">{act}<button class="mini bskeep '
                f'needs-server" data-bskey="{key}">Keep as is</button>'
                '</div></div>')
        if goalless:
            names = ", ".join(e(s.get("room") or clip(s["ws"], 26))
                              for s in goalless[:4])
            more = f" and {len(goalless) - 4} more" if len(goalless) > 4 else ""
            rows.append(
                '<div class="bspot"><div class="bstext">'
                f'<b>No finish line: {names}{more}</b>'
                '<span class="bswhy">Nothing pulls these forward until they go '
                'stale.</span></div>'
                # A bare rooms.html lands back on the Plate; the finish-line
                # box is on the project's own page, so open the first one.
                '<div class="bsfix"><a class="mini bsgoals" href="rooms.html'
                + next((f'#room/{r["slug"]}' for s in goalless
                        for r in M.all_rooms(cfg)
                        if s.get("room") and r.get("slug")
                        and r.get("name") == s["room"]), "")
                + '">Set goals</a></div></div>')
        if rows:
            # Each row is a decision with its own button, so it is a For you
            # line, not a card on the Plate's side (7 Oct).
            tray_confirm.append(tray_item(
                "blind", "confirm", "What the ranking can't see",
                '<div class="bscard intray">' + "".join(rows) + "</div>",
                len(rows)))

    if b["live"]:
        _fc = M.forecast(
            items=ws, people=people, cfg=cfg, today=today,
            now_minutes=now_minutes(), plan_tasks=plan_estimates(day_md),
            starts_by_day=calendar_starts(M.capacity_cfg(cfg)["horizon_days"] + 1))
        # The week ahead lives on the Plate's Week view now (route_views);
        # Today keeps one behind figure, the late fold under "Also due"
        # (7 Oct: seven "behind" signals on one page was seven nags).
        V["todayrail"].append(forecastcard(_fc))
    _money = moneycard(cfg)
    if _money:
        V["todayrail"].append(_money)
    # The questions themselves are in For you (collected above).

    # The cross-domain digest: what is burning in the other tabs, so one
    # glance at Today covers everything. Each row is a door, not a control.
    def drow(sev, name, why, dest):
        return (f'<a class="drow {sev}" href="#/{dest}">'
                f'<span class="dname">{e(name)}</span>'
                f'<span class="dwhy">{why}</span>'
                '<span class="darrow" aria-hidden="true">&rarr;</span></a>')
    digest = []
    # The digest is the LAST thing on Today that can name a workstream, so it
    # yields to every block above it. A row here that repeats the horizons is
    # pure cost: it is a door to another tab, and a door labelled with a
    # sentence you just read tells you nothing about where it goes.
    # Scans the whole urgent stack, not the top few: if the first five are all
    # already on Today, the honest sixth is still worth a door, and stopping
    # early would leave this empty while real work sat unnamed.
    for w in urgent[1:]:
        if shown_already(w["name"]) or shown_already(next_line(w)):
            continue
        claim(w["name"])
        claim(next_line(w))
        digest.append(drow(sevclass(w), w["name"],
                           why_line(w, plain_urgent=True), "plate"))
        if len(digest) >= 3:
            break
    # RANK, then cut. This took the first four in file order, and people.md is
    # alphabetical — so with 86 people qualifying it showed Bay, Perry,
    # Amy and Oakley every single day, and the only two she actually owed a
    # reply to sat at positions 49 and 83 and were never seen. One of them was
    # Frankie, whose trip the hero at the top of the page is about.
    #
    # The severity colours below (owed is loud, quiet is grey) could not fire
    # either, because an owed person never survived the slice.
    #
    # Order: a reply you owe, then a promise you made, then a dated birthday,
    # then how far past the rhythm SHE chose — over_by, not raw silence, so a
    # weekly friend at ten days outranks a quarterly one at ninety.
    def _person_rank(pp):
        bucket = (0 if pp["owed"] else 1 if pp.get("promised")
                  else 2 if pp.get("bday_soon") else 3)
        return (bucket,
                pp.get("bday_in") or 0 if pp.get("bday_soon") else 0,
                -(pp.get("over_by") or 0),
                -(pp.get("days_since") or 0))

    shown_people = sorted(
        (pp for pp in warm
         if (pp["owed"] or pp["overdue"] or pp.get("promised")
             or pp.get("bday_soon") or pp.get("reconnect"))
         and pp["name"] not in _owed_shown),
        key=_person_rank)
    # The week's reconnect pick keeps the last seat (see People's five).
    _rc = next((pp for pp in shown_people if pp.get("reconnect")), None)
    shown_people = (shown_people[:4] if not _rc or _rc in shown_people[:4]
                    else shown_people[:3] + [_rc])
    for pp in shown_people:
        bits = []
        if pp["owed"]:
            # One phrase carrying both facts. It used to append "12d quiet" as
            # a second clause, which is the same fact said twice and the part
            # that got cut when the row ran out of room.
            d = pp["days_since"]
            bits.append(
                '<b class="dico" title="you owe them a reply'
                + ("; they wrote last" if d is not None and d <= 1
                   else f"; they wrote {d} days ago" if d else "") + '">'
                + ico("reply")
                + ("new" if d is not None and d <= 1 else f"{d}d" if d else "owed")
                + "</b>")
        if pp.get("promised"):
            first = pp["open_promises"][0]["text"]
            bits.append("you promised: " + e(first[:60]))
        if pp.get("bday_soon"):
            d = pp["bday_in"]
            bits.append('<b class="dico" title="birthday">' + ico("cake")
                        + ("today" if d == 0 else f"in {d}d") + "</b>")
        if pp["overdue"] and not pp["owed"]:
            bits.append(ago(pp["days_since"]).replace(" ago", "") + " quiet")
        if pp.get("reconnect"):
            bits.append('<b class="dico" title="This week&rsquo;s suggestion '
                        'of someone to get back in touch with">' + ico("clock")
                        + "reconnect</b>")
        # A promise you made and have not kept is the one thing here that is
        # genuinely late; an unanswered reply warns instead.
        sev = ("sev-bad" if pp.get("promised")
               else "sev-wait" if pp["owed"]
               else "sev-soon" if pp.get("bday_soon") else "sev-cold")
        if pp["days_since"] is not None and not pp["overdue"] and not pp["owed"]:
            bits.append(ago(pp["days_since"]).replace(" ago", "") + " quiet"
                        if pp["days_since"] > 1 else "")
        bits = [x for x in bits if x]
        # An owed reply is closable right here: one tap says "answered them".
        btn = (f'<button class="mini prepl needs-server" data-replied="{e(pp["name"])}"'
               f' title="Mark that you answered them today">'
               "&#10003; Replied</button>" if pp["owed"] else "")
        digest.append(f'<div class="drow {sev}">'
                      f'<span class="dname">{e(pp["name"])}</span>'
                      f'<span class="dwhy">{" &middot; ".join(bits)}</span>{btn}'
                      f'<a class="darrow" href="#people" data-plink="{e(pp["name"])}"'
                      f' aria-label="Open {e(pp["name"])} on People">&rarr;</a></div>')
    if digest:
        # Undated people rows read flat — no "6 weeks quiet", no severity. The
        # honest cause is an unsorted chat pile, so say that once, not per row.
        dnote = ""
        if any(pp["never"] for pp in shown_people):
            dnote = ('<p class="dnote">Undated rows are unsorted chats &middot; '
                     '<a href="#people">sort them</a></p>')
        # When most of the address book is overdue, the honest reading is that
        # the rhythms are wrong, not that she is failing eighty people. Say so
        # once, out loud, and leave the fix to her — a circle is her judgement
        # and this brain does not get to reassign one. Same logic the habits
        # page uses: a target missed every week is the wrong target.
        n_over = sum(1 for pp in warm if M.is_past_rhythm(pp))
        if n_over >= 25:
            dnote += (f'<p class="dnote" title="With this many, the rhythms '
                      'are probably set too tight. A quarterly circle is '
                      'meant to be quiet for most of the year.">'
                      f'<b>{n_over}</b> past their rhythm &middot; '
                      '<a href="#people">review the rhythms</a></p>')
        V["todayrail"].append('<section class="digestwrap railcard">'
                              '<h3 class="area">Also needs you</h3>'
                              '<div class="digest">' + "".join(digest) + "</div>"
                              + dnote + "</section>")

    # Interests — the life beyond the to-dos. Quiet by design: no decay, no
    # counts, just each interest and its next small spark.
    try:
        intr = M.parse(read("interests.md"))
    except Exception:
        intr = []
    intr = [i for i in intr if i["fields"].get("spark") or i["fields"].get("what")]
    if _B.PRESENTING:
        intr = []           # her interests are her life outside the work
    if intr:
        irows = []
        for i in intr:
            spark = M._plain(i["fields"].get("spark", ""))
            irows.append('<div class="intr"><b>' + e(i["name"]) + "</b>"
                         + (f'<span class="intspark">{e(spark)}</span>' if spark else "")
                         + "</div>")
        V["todayrail"].append(
            '<details class="ghost intwrap"><summary>'
            '<img class="sumart" src="art/watering.png?v=2" alt="" width="26" height="26">'
            f'Interests ({len(intr)})</summary>'
            '<div class="intgrid">' + "".join(irows) + "</div>"
            '<p class="meta">Kept in interests.md, with no dates on them. '
            f"Tell {AG.short()} when you want to start on one and it "
            "becomes a task.</p></details>")
    return actpend, actqs, habits, parked_qhtml, today_md

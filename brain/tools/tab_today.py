"""The Today tab: build()'s TODAY section, in its own file.

build() calls render() where the section used to sit, passing what the
sections above it worked out; render() returns what the ones below read.
The page helpers come from build.py, so run the page with build.py.
"""

from datetime import date
from datetime import datetime
from datetime import timedelta
import md as MD
import model as M
import os
import re

from build import (BRAIN, _greeting, _mailtasks_tray, _offer_verb, _plan_time,
    _probablydone_tray, _same_thing, _school_tray, _sig_tokens, _tid, ago,
    area_groups, artvid, calendar_starts, cardhead, clip, countdown_card,
    dayshape, e, forecastcard, friday_block, fronts_block, glance_row,
    heroline, ico, linkify_html, moneycard, next_line, now_minutes,
    plan_estimates, plan_tokens, plan_ws_lookup, read, rhythm_lines,
    room_labels, routine_card, school_strip, school_view, security_card, sevclass, span,
    taskrow, tray_item, week_strip, why_line)


def render(V, b, cfg, pending, people, today, tray_answer, tray_confirm,
           urgent, warm, ws, WS_OUTCOMES):
    today_md = read("today.md")
    # Today's plan, tokenised once. Every block below that could restate a
    # task the plan already carries checks itself against this. The hero is
    # the one exception: it is allowed to be the plan's task, because being
    # the most pressed thing is its entire job — so it publishes what it took
    # and the others avoid THAT too.
    PLAN_TOKS = plan_tokens(today_md)

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
        ORB.deck_html(today_md, countdown_rows(today),
                      (cfg.get("now") or {}).get("place") or "",
                      greeting=_greeting(today_md), next_md=read("next.md")))
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
            ("Start with you", "where you are in life, where you live, what you're studying or building"),
            ("What fills your days", "the projects, work or study taking your time"),
            ("The people", "family, close friends, the ones far away you don't want to drift from"),
            ("What's weighing on you", "a deadline, something you're dreading, a decision you keep putting off"),
            ("Loose threads", "what you owe someone, who owes you, a reply you've been meaning to send"),
            ("What you're building in yourself", "habits or routines, and honestly how often"),
            ("Anything else", "small nagging things, or something that doesn't fit a box but matters"),
        ]
        cuelist = "".join(f'<li><b>{c}</b> &mdash; {d}</li>' for c, d in cues)
        V["today"].append(
            '<section class="hero sev-none">'
            + heroline('<p class="eyebrow">Welcome</p>',
                       '<video class="artvid cardart" autoplay muted loop playsinline poster="art/waving.png?v=2" width="72" height="72" aria-hidden="true"><source src="art/waving.mp4?v=2" type="video/mp4"></video>')
            + "<h1>Let's fill your brain</h1>"
            '<p class="hero-why hero-calmnote">Just talk &mdash; who you are, what\'s '
            "going on, what's on your mind, in whatever order it arrives. These are "
            "only nudges "
            "if you get stuck; wander off them freely. Claude sorts all of it and "
            "checks with you before writing anything down.</p>"
            f'<ol class="onboard-cues">{cuelist}</ol>'
            '<button class="dumpstart needs-server" id="startdump">'
            "Start talking</button>"
            '<p class="meta" style="margin-top:12px">Prefer the terminal? Open Claude '
            "Code here and run <code>/onboard</code>.</p></section>")

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
        n_prep = sum(1 for _, txt, wn, _ in dupes if _prepped(txt, wn))
        if not soon_tasks and n_prep:
            sec_offers.append(
                '<section class="offercard slim">'
                '<a class="offersee" href="#/today">&#10022; Claude has already '
                f'found options for {"something" if n_prep == 1 else f"{n_prep} things"} '
                'on today&rsquo;s list &mdash; open the '
                + ("card" if n_prep == 1 else "cards") + "</a></section>")
        if soon_tasks:
            rows3 = []
            for dd, txt, wn, verb in soon_tasks[:3]:
                when = "today" if dd == 0 else f"in {dd}d"
                seen_prep = _prepped(txt, wn)     # work already landed?
                claim(txt)
                rows3.append(
                    f'<div class="offer"><span class="offerwhen">{when}</span>'
                    f'<span class="offertext">{e(txt)}'
                    + ('<a class="offersee" href="#/today">&#10022; Claude found '
                       "options &mdash; open the card</a>"
                       if seen_prep else f'<span class="offerwould">{verb}</span>')
                    + "</span>"
                    f'<button class="mini offerbtn needs-server" data-claudestart="{e(txt)}"'
                    f' data-claudews="{e(wn)}">'
                    + ("Run it again" if seen_prep else "Start it for me")
                    + "</button></div>")
            sec_offers.append(
                '<section class="offercard"><p class="eyebrow">Claude can get ahead '
                'of these</p><span class="wav"></span>'
                + "".join(rows3)
                # A faint line, not the skin's .meta pill, which looked like
                # a button (28 Sep review).
                + '<p class="offerfoot">It never sends anything.</p>'
                "</section>")
        return sec_offers

    # Open questions from the brain — the second half of any dump's interview.
    # Claude writes them to questions.md when there's nobody to ask; answering
    # one hands it back to Claude, who files the answer and ticks the box.
    qtext = read("questions.md")
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
            qtxt = MD.plain(MD.UNTIL.sub("", raw))
            key = _qkey(raw)
            _qstart = len(rows)
            rows.append(
                '<li class="qrow">'
                f'<span class="qq"><span class="ttext">{e(qtxt)}</span>'
                f'<span class="qinline needs-server">'
                f'<input class="qin" data-q="{e(qtxt)}" autocomplete="off"'
                ' placeholder="Type the answer&hellip;">'
                f'<button class="mini qgo" data-qkey="{key}">file it</button>'
                f'<button class="mini qlater" data-qlater="{key}"'
                ' title="Cannot answer this yet — park it until it can be'
                ' answered">not yet&hellip;</button>'
                # Was a checkbox in front of every question (24 Sep: "too
                # many different check boxes"). Typing the answer is the
                # action; this is the rarer "already settled elsewhere".
                '<button class="mini tick qdone" aria-pressed="false"'
                f' data-src="questions.md" data-key="{key}"'
                ' title="Answered elsewhere &mdash; tick it off">already '
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
            "&mdash; waiting for a date you cannot pick yet</summary>"
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
                "</p><p class=\"qlead\">Every open question is parked until it "
                "can actually be answered.</p>" + parked_html + "</section>")
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
    V["todayrail"].append(dayshape(cfg, today, today_md))
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
            # The row says the action, and the wait in words: "Reply to Reese
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
                         f' title="Opens Beeper{where} on your chat with them'
                         ' — nothing is sent"'
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

    habits = M.load_habits(today=today)
    habits_hist = ""
    if not today_md.strip() and not habits:
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
                      ' title="The day has drifted from this morning&rsquo;s plan '
                      '&mdash; have Claude re-rank what is left">'
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
            _wparts[0]["title"] = (_wfull + " — the place follows "
                                   "config’s “now”; just tell "
                                   "Claude you moved")
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
                "slides", "confirm", "Found in your slides", _sc_html,
                _sc_html.count('class="mtrow"')))
        # School on Today is one thin strip: classes today and what is due in
        # three days. The tray, the tracker, the guides and each front moved
        # to the School tab, where there is room for them.
        V["today"].append(school_strip(cfg, shown_already, claim))
        V["school"].append(school_view(cfg))
        # Tasks whose moment has passed, asking to be closed — never closed
        # by the machine on its own.
        _pd_html = _probablydone_tray(b["live"], bare=True)
        if _pd_html:
            tray_confirm.insert(0, tray_item(
                "done", "confirm", "Probably done?", _pd_html,
                _pd_html.count('class="pdrow"')))
        _pstamp = _plan_time()
        V["today"].append('<section id="today" class="todaywrap">'
                     + ('<span class="skinx skinx-planstamp">plan updated '
                        + _pstamp + "</span>" if _pstamp else "")
                     + '<button class="mini planrefresh needs-server" id="planrefresh"'
                     ' title="Have Claude rewrite today&rsquo;s plan from the brain as it'
                     ' stands right now \u2014 runs on your subscription">'
                     "&#8635; Refresh plan</button>" + _undo + _resug)
        if today_md.strip():
            # People and workstreams named in the plan are doors: Kit opens
            # her People row, a project opens its drawer.
            # The daily update (her priority, 24 Sep): the brain sees the
            # laptop and nothing else. Gone once today's update is in —
            # counted from the queue, so the phone and the page agree.
            _upd_in = date.today() in M.update_days(since_days=1)
            V["today"].append(
                '<div class="updnudge" id="updnudge" hidden'
                + (' data-done="1"' if _upd_in else '') + '><span>'
                + ico("mic") + '<b>Daily update</b> &middot; what happened '
                'away from the laptop?</span>'
                '<button class="mini" id="updgo">Tell the brain</button>'
                '<button class="mini" id="updlater">Later</button></div>')
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
                    ' title="Still matters &mdash; roll it into tomorrow&rsquo;s plan deliberately">Carry &#8594;</button>'
                    f'<button class="mini evact" data-evact="drop" data-evkey="{key}"'
                    ' title="Turned out not to be yours &mdash; retire it, on the record">Drop</button>'
                    "</template>")
            if ev_done or ev_open:
                # Say WHERE the decision happens. "The open ones need a
                # decision" left her asking what to do with the box (31 Aug)
                # — the buttons this section grafts live on the plan's own
                # rows below, and the copy has to point there.
                if not ev_open:
                    head = "All of it landed &mdash; clean close."
                elif not ev_done:
                    head = ("The plan didn&rsquo;t happen &mdash; some days go "
                            "somewhere else, and that is worth recording, not "
                            "grading. Close each line below: <b>Carry &#8594;</b> "
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
                V["today"].append(
                    '<section class="evwrap" id="evening" hidden>'
                    '<h3 class="area">How did today actually go?</h3>'
                    f'<p class="evhead">{head}</p>'
                    '<button class="mini evjournal needs-server" data-box'
                    ' data-box-intent="journal">&#10022; Say how it went</button>'
                    + "".join(ev_tpl) + "</section>")
            V["today"].append('<div class="todaydoc doc">'
                         + linkify_html(MD.render(today_md, task_source="today.md",
                                                  ws_lookup=plan_ws_lookup(ws, cfg)))
                         + "</div>")
            V["today"].append(week_strip(cfg, today, today_md))
        # Below the plan: every front of her life, short ranked lists.
        V["today"].append(fronts_block(b["live"], cfg, PLAN_TOKS,
                                       shown_already, claim))
        # The small, pressed tasks worth clearing now — quick wins pulled out
        # of the plate so they stop hiding there. Weekend-aware: office-hours
        # errands wait under a fold instead of nagging on a Saturday.
        # Anything already in today's three (or its chases) must not appear
        # again below — one app's demo showing up in four places at once is
        # what makes the page feel like it is repeating itself.
        qw = [_q for _q in M.quick_wins(ws, today=today)
              if not shown_already(_q["t"]["text"])]
        # Cheapest first, so the top of this card is the fastest thing on the
        # page. It was in workstream order, which meant the two-minute job
        # could be sixth and a reader with five spare minutes had to price the
        # whole list themselves. Anything unestimated sorts as the default
        # rather than as free.
        _dflt = M.capacity_cfg(cfg)["default_task_minutes"]
        qw.sort(key=lambda _q: _q["t"].get("est") or _dflt)
        for _q in qw:
            claim(_q["t"]["text"])
        if qw:
            rlab = room_labels(cfg)
            def _qw_row(q):
                return taskrow(q["t"], "workstreams.md", q["w"]["name"],
                               show_ws=True,
                               ws_label=rlab.get(q["w"]["name"], ""))
            # By area of her life, cheapest first inside each — so the
            # fastest win in every part of her life is visible, not just the
            # fastest overall (her rule, 16 Sep 2026).
            _cost = lambda q: (q["t"].get("est") or _dflt, q["t"]["text"])  # noqa: E731
            now_rows = area_groups([q for q in qw if not q["monday"]],
                                   lambda q: q["w"].get("area"), _cost,
                                   _qw_row)
            mon_rows = area_groups([q for q in qw if q["monday"]],
                                   lambda q: q["w"].get("area"), _cost,
                                   _qw_row)
            frag = ['<div class="qwins">']
            if now_rows:
                frag.append(now_rows)
            if mon_rows:
                frag.append(
                    '<details class="ghost"><summary>Waits for Monday '
                    '&mdash; needs offices open</summary>'
                    f'{mon_rows}</details>')
            if not now_rows and mon_rows:
                frag.insert(1, '<p class="meta">Nothing quick needs a '
                            'weekend hour &mdash; the rest waits for Monday.</p>')
            frag.append("</div>")
            # Into the sweep, beside the owed replies — printed after the plan.
            sweep_quick = "".join(frag)
        # What the day actually held, from the marks it left: commits in the
        # project folders, ticks, Touched dates, drafts. Evening only — at
        # nine in the morning it is a card about nothing, and the plan is
        # what matters then. It reports and does not grade: the plan already
        # says what is undone, and saying it twice is nagging with a second
        # voice.
        if datetime.now().hour >= 16:
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
                    # Cut at a word, and let a title take a second line:
                    # a hard slice at 70 printed "20 Oct mo…" (28 Sep).
                    items = "".join(
                        f'<li title="{e(t["text"])}">'
                        + e(re.sub(r"\s*[→>]+…$", "…", clip(t["text"], 90)))
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
                    '<p class="dayfoot">Only what the laptop saw. '
                    'Tell the brain the rest.</p>'
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
                        '<span class="h2tick auto" title="Counts itself — '
                        'an entry for the day is the tick">'
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
                        + (' title="The short version — it counts as done">'
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
            hist = []
            for hb in habits:
                grid = "".join(
                    '<span class="hgrow">' + "".join(
                        '<i class="' + ("on" if c["on"] else "")
                        + (" today" if c["today"] else "")
                        + (" future" if c["future"] else "")
                        + f'" title="{c["date"]}"></i>'
                        for c in wk) + "</span>"
                    for wk in hb["grid"])
                pills = "".join(
                    f'<span class="wpill {"ok" if wk["count"] >= hb["goal"] else "low"}'
                    f'{" cur" if wk["current"] else ""}"'
                    f' title="week of {wk["start"]}">{wk["count"]}</span>'
                    for wk in hb["weeks"])
                hist.append(f'<div class="hhrow"><b>{e(hb["name"])}</b>'
                            f'<div class="hgrid">{grid}</div>'
                            f'<div class="wpills">{pills}</div></div>')
            habits_hist = (
                '<details class="ghost"><summary>History &mdash; the last month, '
                "and the weeks before</summary>"
                + "".join(hist)
                + '<p class="hnote">Each row is a week, Monday to Sunday, this '
                "week last; the numbers are days per week, oldest left.</p>"
                "</details>")
        if habits or _rhythm:
            V["todayrail"].append(
                (f'<div class="rhlines">{_rhythm}</div>' if _rhythm else "")
                + "</section>")
        V["today"].append("</section>")
        # Under the plan: the Friday hour on its day, then the two-minute
        # sweep — owed replies and the small pressed errands — then For you.
        V["today"].append(friday_block(b, cfg, today))
        if sweep_reply or sweep_quick:
            V["today"].append(
                '<section class="sweep" id="sweep">'
                '<h3 class="area">Two-minute sweep</h3>'
                + (f'<div class="swreply">{sweep_reply}</div>' if sweep_reply else "")
                + sweep_quick + "</section>")
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
            frows.append(f'<div class="frow {sev}"><i class="fdot"></i>'
                         f'<span class="fname">{e(name)}</span>'
                         f'<span class="fago">{lab}</span></div>')
        fronts_html = (
            '<h3 class="area fr2">Where your attention went</h3>'
            + "".join(frows)
            + '<p class="hnote">Each front, by when anything in it last moved '
            "&mdash; longest quiet on top.</p>")
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
        HZ = (("now", "A clock is on it",
               "these have dates, and the dates are doing the choosing"),
              ("push", "You chose this",
               "you set a focus or a finish line &mdash; before the week eats it"),
              ("slow", "Nothing is forcing it",
               "no date, so it can only ever reach you by going stale"))
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
                    f'<span class="hzkind">{title}</span>'
                    '<span class="hznone">'
                    + ("everything with a date on it is already above"
                       if kind == "now" and n else
                       "nothing has a date on it right now"
                       if kind == "now" else
                       "nothing chosen &mdash; pick something and it gets a slot"
                       if kind == "push" else
                       "everything you have is spoken for")
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
                        f'&mdash; ' + (f'in {pick["goal_days"]}d'
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
                       ' title="Claude does the legwork on this now: options '
                       'researched, numbers looked up, anything to send drafted. '
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
                f'<div class="hzlane"><span class="hzkind">{title}</span>'
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
        goalless = [s for s in spots if s["kind"] == "no_goal"]
        rows = []
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
            rows.append(
                '<div class="bspot"><div class="bstext">'
                f'<b>{e(clip(g["event"], 88))}</b>'
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
                f'<b>{e(clip(s["task"], 88))}</b>'
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
                f'<b>{e(clip(s["task"], 88))}</b>'
                '<span class="bswhy">Its date has passed.</span></div>'
                f'<div class="bsfix"><button class="mini bsdrop needs-server" '
                f'data-bskey="{key}">Retire it</button></div></div>')
        for s in vague:
            # The task panel already rewords a line and keeps its date,
            # estimate and urgency; .fc-task opens it for a task named by its
            # words rather than by a row on this page.
            rows.append(
                '<div class="bspot"><div class="bstext">'
                f'<b>{e(clip(s["task"], 88))}</b>'
                '<span class="bswhy">No first step in its words, so it tends '
                'to wait.</span></div>'
                '<div class="bsfix"><button class="mini fc-task needs-server" '
                'data-src="workstreams.md" '
                f'data-task="{MD.taskkey(s["task"])}" '
                f'data-text="{e(s["task"])}" data-ws="{e(s["ws"])}">'
                'Reword</button></div></div>')
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
            V["today"].append(
                '<section class="bscard">'
                + cardhead('<div><p class="eyebrow">What the ranking '
                           'can\'t see</p><span class="wav"></span></div>',
                           artvid("sleuthing", 46))
                + "".join(rows)
                + "</section>")

    if b["live"]:
        V["todayrail"].append(forecastcard(M.forecast(
            items=ws, people=people, cfg=cfg, today=today,
            now_minutes=now_minutes(), plan_tasks=plan_estimates(today_md),
            starts_by_day=calendar_starts(M.capacity_cfg(cfg)["horizon_days"] + 1))))
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
    # alphabetical — so with 86 people qualifying it showed Bay, Oakley,
    # Amy and Jules every single day, and the only two she actually owed a
    # reply to sat at positions 49 and 83 and were never seen. One of them was
    # Lennox, whose trip the hero at the top of the page is about.
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
                + (" &mdash; theirs is the last word" if d is not None and d <= 1
                   else f" &mdash; {d} days now" if d else "") + '">'
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
            bits.append('<b class="dico" title="This week&rsquo;s dormant tie '
                        '&mdash; a message after a long silence lands better '
                        'than the sender expects">' + ico("clock")
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
               f' title="You answered them &mdash; clears the debt, stamps today">'
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
            dnote += (f'<p class="dnote" title="At that number it is the '
                      'rhythms that need the work: a quarterly circle spends '
                      'most of the year quiet, which is what quarterly means.">'
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
            'Interests &mdash; the life '
            f'beyond the to-dos ({len(intr)})</summary>'
            '<div class="intgrid">' + "".join(irows) + "</div>"
            '<p class="meta">Kept in interests.md &mdash; sparks, not chores. '
            "Tell Claude when one comes alive and it becomes real work; "
            "nothing here ever goes &ldquo;overdue&rdquo;.</p></details>")
    return actpend, actqs, habits, habits_hist, parked_qhtml, today_md

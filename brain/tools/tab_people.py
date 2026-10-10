"""The People tab: build()'s PEOPLE section, in its own file.

build() calls render() where the section used to sit, passing what the
sections above it worked out; render() returns what the ones below read.
The page helpers come from build.py, so run the page with build.py.
"""

from datetime import date
from datetime import datetime
import json
import model as M
import os

from build import (BRAIN, _avatar, ago, artimg, cardhead, clip, e, glance_row,
    hint, personrow, shelf, tray_item)


def _synced_ago(gap):
    """When Beeper last synced, in the page's one way of writing time."""
    h = int(gap.total_seconds() // 3600)
    if h < 1:
        return "just now"
    if gap.days == 0:
        return f"{h} hour{'s' if h != 1 else ''} ago"
    return ago(gap.days)


def render(V, cfg, people, today, tray_confirm, warm):
    # The triage lives ON the page, not behind a button: the newest unsorted
    # chats render inline from the cache the syncs keep fresh, a few at a
    # time, so sorting is a daily nibble instead of a chore you go find.
    review = {}
    try:
        with open(os.path.join(BRAIN, ".beeper-review.json"), encoding="utf-8") as f:
            review = json.load(f)
    except Exception:
        pass
    unsorted_chats = (review.get("unmatched") or [])
    # Belt and braces: never render a chat she has hidden, even if the cache
    # predates the hide.
    try:
        with open(os.path.join(BRAIN, "people-ignored.json"), encoding="utf-8") as f:
            _ign = {x.lower() for x in json.load(f)}
        unsorted_chats = [u for u in unsorted_chats
                          if (u.get("name") or "").strip().lower() not in _ign]
    except Exception:
        pass
    # Chats whose whole name is a phone number. beeper.py stops adding them at
    # the source, but the cached queue on disk predates that, so the filter
    # runs here too and the count comes from what was ACTUALLY dropped rather
    # than from a field that could be stale. Guarded import: build.py has to
    # work on a machine where Beeper was never set up.
    try:
        from beeper import is_bare_number as _bare_number
    except Exception:
        def _bare_number(_n):
            return False
    _keep = [u for u in unsorted_chats if not _bare_number(u.get("name"))]
    n_numeric = len(unsorted_chats) - len(_keep)
    unsorted_chats = _keep

    circle_list = [c for c in M.circles(cfg).values()
                   if c["name"].lower() not in ("one-off", "oneoff")]

    _known_people = {pp["name"].lower() for pp in people}

    def _rvmembers(u):
        """A group's members, as chips: known ones marked, unknown ones one
        tap from becoming contacts."""
        mem = u.get("members") or []
        if not u.get("group") or not mem:
            return ""
        chips = []
        for m in mem[:8]:
            if m.lower() in _known_people:
                chips.append(f'<span class="rvmem known" title="Already in your '
                             f'people">{e(m)} &#10003;</span>')
            else:
                chips.append(f'<button class="rvmem" data-mem="{e(m)}" '
                             f'data-memgroup="{e(u.get("name", ""))}" '
                             f'title="Add them as a contact">{e(m)} +</button>')
        more = f'<span class="rvmem dim">+{len(mem) - 8}</span>' if len(mem) > 8 else ""
        return f'<div class="rvmembers">{"".join(chips)}{more}</div>'

    def _chatname(nm):
        """A chat's name as a person would write it. Some Instagram names are
        spelled out letter by letter ("A L F I E"), which on the page read as
        a letter-spaced section label (28 Sep). The row keeps the chat's real
        name in data-chat; sorting files the person under this one
        (model.spelled_name, the same rule serve.py uses)."""
        return M.spelled_name(nm)

    def rvrow(u):
        chips = "".join(
            f'<button class="cchip" data-circle="{e(c["name"])}"'
            f' title="{e(c["every"] or "no set rhythm")}">{e(c["name"])}</button>'
            for c in circle_list) + (
            '<button class="cchip cchipnew" data-newcircle'
            ' title="Create a new group right here">+ new</button>')
        name = e(u.get("name", ""))
        _d = u.get("days")
        return ('<div class="rv" data-chat="' + name.replace("'", "&#39;") + '">'
                '<div class="rvtop"><span class="rvname">' + e(_chatname(u.get("name", "")))
                + (' <span class="rvgroup">group</span>' if u.get("group") else "")
                + '</span><span class="rvmeta">'
                + e(u.get("network", "")) + " &middot; "
                + (ago(_d) if _d is not None else "no date") + "</span></div>"
                + _rvmembers(u)
                + '<div class="rvacts"><span class="cchips">' + chips + '</span>'
                '<span class="rvminor">'
                '<input data-rv="link" class="rvlink" list="peopledl" '
                'placeholder="or same person as&hellip;"'
                ' title="Already in your people under another name? Pick them'
                ' and this chat joins them.">'
                '<button data-rv="oneoff">one-off</button>'
                '<button data-rv="ignore">hide</button></span></div></div>')

    if not people:
        # A new brain: the tab used to render nothing at all, so the Add,
        # Sync and LinkedIn buttons other screens point to were nowhere
        # (7 Oct audit). Same ids as the full header, so page.js wires them.
        # A key, not the registration file: Disconnect deletes the key
        # and keeps the registration (8 Oct).
        try:
            import beeper as _beep
            _bee = _beep.connected()
        except Exception:
            _bee = False
        V["people"].append(
            '<section id="people"><h2>People</h2>'
            '<p class="sub">The people you want to stay close to. Add the ones '
            'who matter and give each a circle and a rhythm, and this page '
            'reminds you when you owe someone a reply or it has been a while.</p>'
            '<p class="emptyacts">'
            '<button class="addbutton needs-server" data-addkind="person">+ Add someone</button>'
            + ('<button class="addbutton needs-server" id="syncppl">Sync from Beeper</button>'
               if _bee else "")
            + '<button class="addbutton needs-server" id="shotbtn">From a screenshot</button>'
            '<button class="addbutton needs-server" id="limgr">From LinkedIn</button></p>'
            + ('' if _bee else
               '<p class="sub">To fill in when you last spoke to people without '
               'logging anything, connect Beeper under the gear, in Connections.</p>')
            + '</section>')

    if people:
        V["people"].append('<datalist id="peopledl">'
                     + "".join(f'<option value="{e(pp["name"])}"></option>' for pp in people)
                     + "</datalist>")
        # Last-synced time rides ON the sync pill — "does this run itself?"
        # should never need a hunt. (It does: every morning at 7.)
        try:
            _bmt = os.path.getmtime(os.path.join(BRAIN, ".beeper-review.json"))
            _bd = datetime.now() - datetime.fromtimestamp(_bmt)
            _bago = _synced_ago(_bd)
        except Exception:
            _bago = ""
        _me = ""
        for _ext in (".jpg", ".png", ".webp", ".gif"):
            if os.path.exists(os.path.join(BRAIN, "avatars", "me" + _ext)):
                _me = "avatars/me" + _ext
                break
        V["people"].append('<section id="people">'
                     '<img class="artpng h2art" src="art/waiting.png?v=2" alt=""'
                     ' width="34" height="34" aria-hidden="true">'
                     '<h2>People'
                     '<button class="addbutton needs-server" data-addkind="person">'
                     "+ Add someone</button>"
                     '<button class="addbutton needs-server" id="syncppl">'
                     "Sync from Beeper"
                     + (f' <span class="csub">{e(_bago)}</span>' if _bago else "")
                     + "</button>"
                     '<details class="hmore"><summary aria-label="More">&#8943;</summary>'
                     '<div class="hmorepanel">'
                     '<button class="addbutton needs-server" id="shotbtn">'
                     "From a screenshot</button>"
                     '<button class="addbutton needs-server" id="newgroup">'
                     "+ New group</button>"
                     '<button class="addbutton needs-server" id="limgr">'
                     "From LinkedIn</button>"
                     '<button class="addbutton needs-server" id="tplmgr">'
                     "Message templates</button>"
                     '<button class="addbutton needs-server" id="mephoto"'
                     ' title="Your face for the centre of Circles">'
                     + (f'<img class="mepill" src="{_me}?v=1" alt=""> Change photo'
                        if _me else "Your photo")
                     + "</button></div></details>"
                     '<input type="file" id="mephotofile" accept="image/*" hidden>'
                     + hint("Each morning at 7, Beeper fills in when you last "
                            "chatted with each person. It reads chat names and "
                            "dates, not the messages. Sort the chats below "
                            "into your circles.")
                     + "</h2>"
                     '<p class="sub" id="pplnote" hidden></p>')
        # A one-line orientation. Deliberately NOT "250 need you" — a number
        # that big is unactionable and the eye slides off it. The page
        # surfaces five a day; the rest wait their turn silently.
        n_un = len(unsorted_chats)
        # For you asks only about chats that moved this week: the long tail
        # of old unsorted ones would sit there forever and teach her to skip
        # the list. The full sorter stays on People.
        _fresh_chats = [u for u in unsorted_chats
                        if u.get("days") is not None and u["days"] <= 7
                        and not u.get("group")]
        if _fresh_chats:
            tray_confirm.append(tray_item(
                "chats", "confirm", "New chats to sort into your circles",
                '<p class="trnames">' + " &middot; ".join(
                    e(clip(_chatname(u.get("name") or "?"), 28)) for u in _fresh_chats[:8])
                + '</p><a class="mini" href="#/everyone" data-sortgo>Sort them'
                ' on People &rarr;</a>', len(_fresh_chats)))
        # The headcount belongs to the big sentence below, which already says
        # it with the circles attached — repeating it here made the top of the
        # page say "343" twice in two lines. This line keeps only what the
        # sentence cannot: what there is to DO.
        tally = []
        if warm:
            tally.append(f"{min(5, len(warm))} for today")
        if n_un:
            tally.append('<a href="#/everyone" class="pcountgo">'
                         f'{n_un} chats to sort</a>')
        if tally:
            V["people"].append('<p class="pcount">' + " &middot; ".join(tally) + "</p>")
        # The design's opening line for this page: the state of the whole
        # ledger in one honest sentence, so the shelves below don't have to
        # shout it. Calm on purpose — 237 lapsed people is a fact, not an
        # emergency, and reading it as guilt is what killed the old page.
        _circ = len({p["circle"] for p in people if p.get("circle")})
        _owed = len([p for p in people if p.get("owed")])
        _lapsed = sum(1 for p in people if M.is_past_rhythm(p))
        _held = len([p for p in people if p.get("held")])
        # As chips (28 Sep). "11 owe you a reply" also read backwards: the
        # flag means SHE owes them.
        _bits = []
        if _owed:
            _bits.append({"icon": "reply", "text": f"{_owed} to answer",
                          "title": f"you owe {_owed} people a reply"})
        if _lapsed:
            _bits.append({"icon": "clock", "text": f"{_lapsed} past rhythm",
                          "title": f"{_lapsed} are past the rhythm you set"})
        if _held:
            _bits.append({"icon": "calendar", "text": f"{_held} on hold",
                          "title": f"{_held} are on hold"})
        V["people"].append(
            f'<p class="psub">{len(people)} kept, across {_circ} circles.</p>'
            + glance_row(_bits, cls="coach pledger"))
        # The Dunbar reality check: what all the rhythms ADD UP to, per day.
        # Research (Dunbar's layers) puts stable circles near 5 intimate /
        # 15 close / 50 friends / 150 meaningful names — and real capacity at
        # a handful of deliberate touches a day. This line converts her own
        # settings into that currency, so over-commitment is visible as a
        # number instead of a vague guilt.
        _load = sum(1.0 / pp["every_days"] for pp in people
                    if pp.get("every_days") and not pp.get("oneoff")
                    and not pp.get("held"))
        if _load:
            _n_rhythm = sum(1 for pp in people
                            if pp.get("every_days") and not pp.get("oneoff")
                            and not pp.get("held"))
            # Plain words, not a tally of people (9 Oct, her rule against
            # anything that sounds like counting friends).
            _msg = (f"Keeping up with the {_n_rhythm} people at the rhythms you "
                    f"set means about <b>{_load:.1f} messages a day</b>. ")
            if _load > 6:
                _msg += ("That's more than most people keep up. Give a big group "
                         "a slower rhythm with the pill on its heading, or none.")
            elif _load > 3:
                _msg += ("That's a lot. Keep the tight rhythms for the people "
                         "closest to you.")
            else:
                _msg += "That's a pace you can keep."
            V["people"].append(
                '<div class="pintro" id="pintro" hidden>'
                '<button class="pintro-x" id="pintrox" title="Hide this">'
                '&times;</button>'
                f'<p class="dunbar">{_msg}</p>')
        # What you DID, before what you owe: a ledger that only shows debts
        # becomes a page you feel bad opening, and then you stop opening it.
        recent = sorted((pp for pp in people
                         if pp["days_since"] is not None and pp["days_since"] <= 6
                         and not pp.get("oneoff")),
                        key=lambda pp: pp["days_since"])
        if recent:
            names = [pp["name"] for pp in recent[:3]]
            extra = len(recent) - len(names)
            lst = (", ".join(names) if extra > 0        # "A, B, C and 38 more"
                   else names[0] if len(names) == 1
                   else " and ".join([", ".join(names[:-1]), names[-1]]))
            V["people"].append(
                '<p class="weekline">This week you were in touch with '
                f'{e(lst)}{f" and {extra} others" if extra > 0 else ""}.</p>')
        # When Beeper last brought dates in, and when it will again — the sync
        # should never be a mystery.
        try:
            bmt = os.path.getmtime(os.path.join(BRAIN, ".beeper-review.json"))
            bd = (datetime.now() - datetime.fromtimestamp(bmt))
            bago = _synced_ago(bd)
            V["people"].append(
                f'<p class="beepnote">Beeper last synced {bago}. It syncs itself '
                "every morning at 7, or tap <b>Sync from Beeper</b> above to "
                "sync now.</p>")
        except Exception:
            pass
        V["people"].append("</div>")     # closes the dismissible intro

        # The sort queue is real work but it should not bury the people you have
        # already sorted — it lives behind a toggle, open only when it is short.
        if unsorted_chats:
            V["people"].append(
                f'<details class="ghost sortwrap pall"{" open" if n_un <= 6 else ""}>'
                f'<summary>Sort {n_un} new contact{"s" if n_un != 1 else ""} from Beeper</summary>'
                '<div class="rvlist" id="sortstrip">'
                + "".join(rvrow(u) for u in unsorted_chats[:6])
                + "</div>"
                + (f'<button class="addbutton needs-server" id="reviewmore">'
                   f"Open the full sorter, with search and filters ({n_un})</button>" if n_un > 6 else "")
                + "</details>")

        # Possible duplicate people: close spellings that survived the dump
        # (dictation invents variants). Conservative on purpose — Marco and
        # Marcia are different people; Kaitlyn and Katelyn are not.
        def _lev(a, b):
            if abs(len(a) - len(b)) > 2:
                return 9
            prev = list(range(len(b) + 1))
            for i, ca in enumerate(a):
                cur = [i + 1]
                for j, cb in enumerate(b):
                    cur.append(min(prev[j + 1] + 1, cur[j] + 1,
                                   prev[j] + (ca != cb)))
                prev = cur
            return prev[-1]

        # Edit distance alone flags Dallas/Ember and Winter/Zephyr — real distinct
        # people one letter apart. Dictation variants of ONE name keep their
        # consonants (Kaitlyn/Katelyn -> ktln); different names don't
        # (ivan/ivar -> vn/vr). So: close spelling AND same consonant skeleton.
        # Short names are too ambiguous for skeletons (Lea/Leo both -> l) —
        # under five letters only accent/case variants (Rowan/Harper) qualify.
        import unicodedata as _ud

        def _deaccent(s):
            s = _ud.normalize("NFKD", s)
            return "".join(ch for ch in s if not _ud.combining(ch))

        def _skel(s):
            out = []
            for ch in _deaccent(s):
                if ch.isalpha() and ch not in "aeiouy":
                    if not out or out[-1] != ch:
                        out.append(ch)
            return "".join(out)

        dup_pairs = []
        _names = [pp["name"] for pp in people if not pp.get("oneoff")]
        for i2 in range(len(_names)):
            for j2 in range(i2 + 1, len(_names)):
                a2, b2 = _names[i2].lower(), _names[j2].lower()
                d2 = _lev(a2, b2)
                if min(len(a2), len(b2)) < 5:
                    close = a2 != b2 and _deaccent(a2) == _deaccent(b2)
                else:
                    close = ((d2 == 1 or (d2 == 2 and min(len(a2), len(b2)) >= 7))
                             and _skel(a2) == _skel(b2))
                if close:
                    dup_pairs.append((_names[i2], _names[j2]))
        if dup_pairs:
            rows2 = []
            for a3, b3 in dup_pairs[:6]:
                key3 = e(a3) + "|" + e(b3)
                rows2.append(
                    f'<div class="duprow" data-dupkey="{key3}">'
                    f'<span class="duplbl">{e(a3)} &harr; {e(b3)}</span>'
                    f'<button class="mini dupmerge needs-server" data-dupa="{e(a3)}"'
                    f' data-dupb="{e(b3)}">Merge &rarr; {e(b3)}</button>'
                    f'<button class="mini dupmerge needs-server" data-dupa="{e(b3)}"'
                    f' data-dupb="{e(a3)}">Merge &rarr; {e(a3)}</button>'
                    f'<button class="mini dupdismiss" data-dupkey="{key3}">Not the same</button>'
                    "</div>")
            V["people"].append(
                '<div class="dupcard pall" id="dupcard"><p class="eyebrow">Possible '
                "duplicates</p>" + "".join(rows2) + "</div>")

        # A quick filter across every section at once: who owes whom, who has
        # drifted. Clears back to everyone.
        # The finding tools belong to the directory (Everyone, 7 Oct).
        V["people"].append(
            '<div class="pall pfind">'
            '<input class="psearch" id="psearch" type="search" autocomplete="off" '
            'placeholder="Search by name, company, role or note…" aria-label="Search people">'
            '<div class="pfilters" role="group" aria-label="Filter people">'
            '<button class="pfilter active" data-pfilter="">Everyone</button>'
            '<button class="pfilter" data-pfilter="owe-them">I owe them</button>'
            '<button class="pfilter" data-pfilter="owe-me">They owe me</button>'
            '<button class="pfilter" data-pfilter="quiet">Gone quiet</button>'
            '<button class="pfilter" data-pfilter="focus">Focus</button>'
            "</div></div>")
        # The trip-planning question ("I'm in Madrid next week — who should I
        # see?") as one control, not a taxonomy of overlapping chips.
        placecount = {}
        for pp in people:
            for v in ([pp["where"]] if pp.get("where") else []) + pp.get("tags", []):
                placecount[v] = placecount.get(v, 0) + 1
        if placecount:
            popts = "".join(
                f'<option value="{e(v)}">{e(v)} ({c2})</option>'
                for v, c2 in sorted(placecount.items(), key=lambda x: -x[1]))
            V["people"].append(
                '<div class="pfilters pwhererow pall" role="group" aria-label="Filter by place">'
                '<label class="pwhere">I&rsquo;m in&hellip; '
                '<select id="pplacesel"><option value="">anywhere</option>'
                + popts + "</select></label>"
                '<span class="pwherenote">pick a place and the directory shows '
                "everyone there</span></div>")

        # 1) Focus — the handful of relationships being deliberately invested
        #    in right now. Always visible, always first: this block is the
        #    definition of the star.
        focus_people = [pp for pp in people if pp["focus"] and not pp.get("oneoff")]
        if focus_people:
            V["people"].append(
                '<div class="pgroup pneedonly" id="pfocus"><h3 class="area">Focus</h3>'
                '<p class="phint">They surface sooner when quiet. The &#9733; on any '
                "person adds them.</p>"
                '<div class="stack">'
                + "".join(personrow(pp, ledger=True) for pp in focus_people)
                + "</div></div>")

        # 2) Today's five — the whole daily ask, finishable on purpose. Ranked
        #    by lapse relative to each person's own rhythm, weighted by
        #    closeness (family and inner rings outrank acquaintances).
        #    A RATION, not a live query: the names lock at the first build of
        #    the day, so clearing one is progress, not a summons for the next
        #    — and clearing all five is a real finish line.
        import json as _j5
        ffocus = {pp["name"] for pp in focus_people}
        cand = [pp for pp in warm
                if not pp.get("oneoff") and pp["name"] not in ffocus]
        by_name = {pp["name"]: pp for pp in people}
        five_fp = os.path.join(BRAIN, ".today-five.json")
        five_names = None
        try:
            with open(five_fp, encoding="utf-8") as f5:
                st5 = _j5.load(f5)
            if st5.get("date") == today.isoformat():
                five_names = [n for n in st5.get("names", []) if n in by_name]
        except Exception:
            pass
        if five_names is None:
            five = cand[:5]
            # The week's reconnect pick always gets the fifth seat: nine
            # owed replies would otherwise keep a dormant tie out for good.
            rc = next((pp for pp in cand if pp.get("reconnect")), None)
            if rc and rc not in five:
                five = cand[:4] + [rc]
            five_names = [pp["name"] for pp in five]
            try:
                with open(five_fp, "w", encoding="utf-8") as f5:
                    _j5.dump({"date": today.isoformat(), "names": five_names}, f5)
            except OSError:
                pass
        five = [by_name[n] for n in five_names]
        open_five = [pp for pp in five if pp["flags"]]
        done_five = [pp for pp in five if not pp["flags"]]
        waiting = len([pp for pp in cand if pp["name"] not in set(five_names)])

        def _reachedrow(pp):
            return ('<div class="row pdone">' + _avatar(pp["name"])
                    + f'<span class="rowname">{e(pp["name"])}</span>'
                    '<span class="pdonewhy">&#10003; reached today</span></div>')

        if five and not open_five:
            # The finish line: all five closed. Celebrate and fold — done
            # should FEEL done, or the page never gives anything back.
            _n5 = [pp["name"] for pp in five]
            names5 = (", ".join(_n5[:-1]) + " and " + _n5[-1]
                      if len(_n5) > 1 else _n5[0])
            V["people"].append(
                '<div class="pgroup pneedonly" id="pneeds"><h3 class="area">Today&rsquo;s five</h3>'
                '<div class="fivedone">'
                '<video class="artvid" autoplay muted loop playsinline'
                ' poster="art/celebrating.png?v=2" width="110" height="110"'
                ' aria-hidden="true"><source src="art/celebrating.mp4?v=2"'
                ' type="video/mp4"></video>'
                '<p class="fivedone-h">That&rsquo;s the five &#10003;</p>'
                f'<p class="meta">You were in touch with {e(names5)} today. '
                "The next five come tomorrow.</p>"
                "</div></div>")
        elif five:
            V["people"].append(
                '<div class="pgroup pneedonly" id="pneeds"><h3 class="area" title="Get'
                ' in touch with these five and you are done for the day. The ones'
                ' furthest past the rhythm you set come first, closest circles'
                ' ahead.">Today&rsquo;s'
                ' five'
                + (f' <span class="csub">{len(done_five)} of {len(five)} done</span>'
                   if done_five else "")
                + "</h3>"
                '<div class="stack">'
                + "".join(_reachedrow(pp) for pp in done_five)
                + "".join(personrow(pp, ledger=True) for pp in open_five)
                + "</div>"
                + (f'<p class="pwait">+{waiting} more &middot; the next five '
                   "tomorrow</p>" if waiting > 0 else "")
                + "</div>")
        else:
            V["people"].append('<div class="pgroup pneedonly" id="pneeds">'
                         '<h3 class="area">Today&rsquo;s five</h3>'
                         '<p class="empty art"><img src="art/sleeping.png?v=2" alt="" width="64" height="64"> '
                         "Nobody is owed a reply and nobody has "
                         "gone quiet past the rhythm you set.</p></div>")

        # 2b) Who else needs her (7 Oct, the fewer-doors plan): People opens
        #     on this view, with the shelves behind Everyone. Replies she owes,
        #     freshest first, then the people past the rhythm she set — the
        #     people half of the Plate's old "Also needs you". Today's five
        #     and Focus already hold their own; a dormant tie comes back only
        #     as the week's reconnect pick, never here.
        _taken = set(five_names) | ffocus

        def _needgroup(gid, title, hint, rows, show=6):
            if not rows:
                return ""
            more = rows[show:]
            return (f'<div class="pgroup pneedonly" id="{gid}"><h3 class="area">'
                    f'{title}</h3><p class="phint">{hint}</p><div class="stack">'
                    + "".join(personrow(pp, ledger=True) for pp in rows[:show])
                    + "</div>"
                    + (f'<details class="ghost"><summary>{len(more)} more</summary>'
                       '<div class="stack">'
                       + "".join(personrow(pp, ledger=True) for pp in more)
                       + "</div></details>" if more else "")
                    + "</div>")
        _owe = sorted((pp for pp in people
                       if pp.get("owed") and not pp.get("oneoff")
                       and not pp.get("held") and pp["name"] not in _taken),
                      key=lambda pp: (pp.get("days_since")
                                      if pp.get("days_since") is not None else 9999))
        _quiet = sorted((pp for pp in people
                         if M.is_past_rhythm(pp) and not pp.get("dormant")
                         and not pp.get("oneoff") and not pp.get("owed")
                         and not pp.get("held") and pp["name"] not in _taken),
                        key=lambda pp: (-M.circle_weight(pp["circle"]),
                                        -(pp.get("days_since") or 0)))
        V["people"].append(
            _needgroup("powed", "You owe a reply", "They wrote last.", _owe)
            + _needgroup("pquiet", "Gone quiet",
                         "Past the rhythm you set, closest circles first.",
                         _quiet))

        # 2c) Up next — the dated people-moments, on a 30-day horizon. Today's
        #     five answers "who do I reach today"; this answers "what is
        #     coming that I cannot do late". A birthday can only be wished on
        #     the day, so seeing it three weeks out is the whole point.
        #     Silent when there is nothing dated: an empty block on a page
        #     with 400 people is clutter, not a prompt.
        upnext = []
        for pp in people:
            if pp.get("oneoff"):
                continue
            bi = pp.get("bday_in")
            if bi is not None and bi <= 30:
                upnext.append((bi, pp["name"], "sev-soon",
                               "birthday " + ("today" if bi == 0 else
                                              "tomorrow" if bi == 1 else
                                              f"in {bi} days")))
            if pp.get("held") and pp.get("hold"):
                try:
                    hd = (date.fromisoformat(pp["hold"]) - today).days
                except ValueError:
                    hd = None
                if hd is not None and hd <= 30:
                    upnext.append((hd, pp["name"], "sev-cold",
                                   "together until then &middot; the rhythm "
                                   "restarts " + ("tomorrow" if hd <= 1
                                                  else f"in {hd} days")))
        if upnext:
            upnext.sort(key=lambda x: (x[0], x[1].lower()))
            shown_up, rest_up = upnext[:8], upnext[8:]
            # In the side column (7 Oct): permanently useful, so the 40% the
            # dock keeps for an opened person never stands empty.
            V["peoplerail"].append(
                '<div class="pgroup railcard" id="pnext"><h3 class="area">Up next</h3>'
                '<p class="phint">Dated in the next 30 days.</p>'
                '<div class="digest">'
                + "".join(
                    f'<div class="drow {sev}"><span class="dname">{e(nm)}</span>'
                    f'<span class="dwhy">{why}</span>'
                    f'<a class="darrow" href="#people" data-plink="{e(nm)}"'
                    f' aria-label="Open {e(nm)} on People">&rarr;</a></div>'
                    for _d, nm, sev, why in shown_up)
                + "</div>"
                + (f'<p class="pwait">{len(rest_up)} more further out.</p>'
                   if rest_up else "")
                + "</div>")

        # 2d) Outreach — everyone with a Stage, in the order an approach
        #     moves: to reach, asked, talking, met. Silent when nobody has
        #     one. An ask quiet past the chase line leads its column, with
        #     the nudge one tap away.
        staged = [pp for pp in people if pp.get("stage") and not pp.get("oneoff")]
        if staged:
            cols = []
            for st in M.STAGES:
                grp = [pp for pp in staged if pp["stage"] == st]
                grp.sort(key=lambda pp: (not pp.get("chase"),
                                         -(pp.get("stage_days") or 0),
                                         pp["name"].lower()))
                rows = []
                for pp in grp[:12]:
                    rc = " at ".join(x for x in (pp.get("role"), pp.get("company")) if x)
                    sd = pp.get("stage_days")
                    rows.append(
                        f'<li class="orow{" chase" if pp.get("chase") else ""}">'
                        f'<a class="plink oname" href="#people" data-plink="{e(pp["name"])}">'
                        f'{e(pp["name"])}</a>'
                        + (f'<span class="owork">{e(clip(rc, 40))}</span>' if rc else "")
                        + (f'<span class="odays" title="{st} {ago(sd)}">{sd}d</span>'
                           if sd else "")
                        + f'<button class="mini needs-server" data-writeto="{e(pp["name"])}"'
                        f' data-tpluse="{"nudge" if pp.get("chase") else ""}">'
                        + ("Nudge" if pp.get("chase") else "Write") + "</button></li>")
                more = (f'<li class="omore">+{len(grp) - 12} more</li>'
                        if len(grp) > 12 else "")
                cols.append(f'<div class="ocol"><h4>{e(st)} <span class="csub">'
                            f'{len(grp)}</span></h4>'
                            + (f'<ul>{"".join(rows)}{more}</ul>' if rows else
                               '<p class="phint">nobody</p>')
                            + "</div>")
            n_chase = sum(1 for pp in staged if pp.get("chase"))
            V["people"].append(
                '<div class="pgroup pneedonly" id="poutreach"><h3 class="area">Outreach'
                + (f' <span class="csub">{n_chase} to nudge</span>' if n_chase else "")
                + '</h3><div class="ocols">' + "".join(cols) + "</div></div>")

        # 2e) Leaving a place: two weeks before `now.until`, For you asks who
        #     from here to keep. A term, an exchange or a season ends and the
        #     people it put next to you scatter; the ones you choose now get
        #     a rhythm (or Focus) before that happens.
        _now = cfg.get("now") or {}
        _place = str(_now.get("place") or "").strip()
        try:
            _left = (date.fromisoformat(str(_now.get("until"))) - today).days
        except (TypeError, ValueError):
            _left = None
        if _place and _left is not None and 0 <= _left <= 14:
            _here = [pp for pp in people if not pp.get("oneoff") and _place.lower() in
                     (pp.get("where", "") + " " + " ".join(pp.get("tags") or [])).lower()]
            if _here:
                tray_confirm.append(tray_item(
                    "leaving-" + str(_now.get("until")), "confirm",
                    f"You leave {_place} "
                    + ("today" if _left == 0 else f"in {_left} days")
                    + ": who from here do you keep?",
                    '<p class="trnames">' + " &middot; ".join(
                        e(clip(pp["name"], 24)) for pp in _here[:8])
                    + (f" and {len(_here) - 8} more" if len(_here) > 8 else "")
                    + f'</p><a class="mini" href="#/people" data-leavego="{e(_place)}">'
                    "Choose on People &rarr;</a>", len(_here)))

        # The sort queue's side card went on 7 Oct: For you lists the chats
        # that moved this week, and the full sorter is the fold under
        # Everyone.

        # 3) The directory: EVERYONE, once, in circle folds — a neutral address
        #    book for finding people, not a second debt list. The circles
        #    appear exactly here and nowhere else; the shouting stays above.
        # The shelves' own header: what the ordering means, and the one
        # filter that matters on a page this size — show me only who is
        # slipping. (The old Directory heading became this.)
        V["people"].append(
            '<div class="shelvesbar pall" id="shelvesbar">'
            '<p class="eyebrow">The shelves</p>'
            '<span class="shelvesnote" title="ordered by how far through each '
            "person&rsquo;s own rhythm you are\">steadiest first</span>"
            '<span class="shelvestoggle">'
            '<button class="pill on" data-shfilter="all">All circles</button>'
            '<button class="pill" data-shfilter="slip">Only slipping</button>'
            '<button class="pill" id="shopen" data-open="1"'
            ' title="Whether circles start open. Remembered on this device.">'
            "Collapse all</button>"
            "</span></div>")
        order = [c["name"] for c in M.circles(cfg).values()]
        oneoff = [pp for pp in people if pp.get("oneoff")]
        sorted_rest = [pp for pp in people if not pp.get("oneoff")]
        groups = {}
        for pp in sorted_rest:
            key = next((cn for cn in order if cn.lower() == pp["circle"].lower()),
                       pp["circle"])
            groups.setdefault(key, []).append(pp)
        seq = [cn for cn in order if cn.lower() not in ("one-off", "oneoff")]
        seq += [cn for cn in groups if cn not in seq]     # any custom circle
        for cn in seq:
            grp = groups.get(cn)
            if not grp:
                continue
            grp.sort(key=lambda p: (-(p["days_since"] or 0), p["name"].lower()))
            # The group's rhythm, visible and clickable right on the heading —
            # "how often do I want to reach these people" is a live dial, not
            # a decision buried at group creation.
            cev = M.circle_meta(cn).get("every") or ""
            faces = shelf(grp, own=not cev)
            # A circle is normally its shelf of faces, with the rows a click
            # away. But `shelf()` draws nothing under three people — so a
            # group of one rendered a shelf that wasn't there over rows that
            # CSS was hiding, and opening it showed an empty box. Too small
            # for a shelf means the rows ARE the group.
            V["people"].append(
                f'<details class="csection pgroup pall{"" if faces else " aslist"}"'
                f' data-circle="{e(cn)}">'
                f'<summary class="area circlehead">{e(cn)} '
                f'<span class="csub">{len(grp)}</span>'
                f'<button class="crhythm needs-server" data-crhythm="{e(cn)}"'
                f' data-every="{e(cev)}" title="The default rhythm for everyone here. '
                f'Click to change it">{e(cev or "no rhythm")}</button>'
                f'<button class="crename needs-server" data-crename="{e(cn)}"'
                ' title="Rename this group, keeping everyone in it">'
                'rename</button></summary>'
                + faces
                + '<div class="stack">' + "".join(personrow(pp) for pp in grp) + "</div></details>")
        # Dormant: a fold, not a count. The tie is resting; the week's
        # reconnect pick is how one comes back (model.py has the why).
        dormant = [pp for pp in people if pp.get("dormant")]
        if dormant:
            dormant.sort(key=lambda p: (-M.circle_weight(p["circle"]),
                                        p["name"].lower()))
            V["people"].append(
                f'<details class="ghost pall"><summary>Dormant ({len(dormant)})'
                '</summary><p class="phint">People you have not been in touch '
                'with for three times their rhythm. They no longer show as late. '
                'Each week one comes back as someone to reconnect with, from '
                'where you are now when there is one.</p><div class="stack quiet">'
                + "".join(personrow(pp) for pp in dormant) + "</div></details>")
        if oneoff:
            oneoff.sort(key=lambda p: (-(p["days_since"] or 0), p["name"].lower()))
            V["people"].append(
                f'<details class="ghost pall"><summary>One-off &amp; archived '
                f"({len(oneoff)})</summary><div class=\"stack quiet\">"
                + "".join(personrow(pp) for pp in oneoff) + "</div></details>")
        V["people"].append("</section>")

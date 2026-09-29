"""The Plate tab: build()'s PLATE section, in its own file.

build() calls render() where the section used to sit, passing what the
sections above it worked out; render() returns what the ones below read.
The page helpers come from build.py, so run the page with build.py.
"""

from datetime import datetime
import md as MD
import os

from build import (BRAIN, calmrow, dayfirst, e, finish_lines, plate_foot, read,
                   stackrow)


def render(V, b, calm, cfg, closed, today, urgent, ws):
    if not b["live"]:
        V["plate"].append(
            '<section class="firstrun"><p class="eyebrow">Your plate</p>'
            '<span class="wav"></span>'
            '<p class="coach">Everything you have on lives here, ranked by '
            'what is rotting fastest. Nothing is on it yet.</p>'
            '<div class="frdo"><button class="btnp needs-server" data-job="discover">'
            'Find my projects on this Mac</button>'
            '<button class="mini needs-server" id="frcapture">'
            'or just tell it what you have on</button></div></section>')
    _TILE_TIPS = {"overdue": "Past a date you set",
                  "chase": "Waiting on someone who has gone quiet",
                  "cold": "Untouched by you for a while",
                  "me": "The next move is yours",
                  "them": "The next move is someone else's"}

    def tile(n, label, kind, f):
        if not n:
            return ""                    # a zero filter is noise, not a filter
        return (f'<button class="tile t-{kind}" data-filter="{f}"'
                f' title="{_TILE_TIPS.get(f, "")}">'
                f"<b>{n}</b><span>{label}</span></button>")
    # The plate opens by saying, in words, what shape the whole pile is in \u2014
    # the design's "18 moving \u00b7 3 waiting on others \u00b7 2 past their date",
    # then one coaching sentence naming the genuinely worrying part.
    _mv = len([w for w in b["live"] if w["ball"] != "them"])
    _tr = [f"{_mv} moving"]
    if b["theirs"]:
        _tr.append(f'{len(b["theirs"])} waiting on others')
    if b["overdue"]:
        _tr.append(f'{len(b["overdue"])} past their date')
    # The coaching sentence under it ("4 of these have not been touched in a
    # fortnight…") went on 28 Sep: the chips just below say "4 going cold".
    V["plate"].append(
        '<section class="platehead"><p class="eyebrow">Your plate</p>'
        '<span class="wav"></span>'
        f'<p class="triage">{e(" · ".join(_tr))}.</p></section>')
    # The finish lines she set, nearest first — pinned above the list they
    # pull on (the strip used to head the rooms' floor plan).
    V["plate"].append(finish_lines(cfg, today))
    V["plate"].append(
        '<input class="psearch" id="tsearch" type="search" autocomplete="off" '
        'placeholder="Search every task, done ones too" '
        'aria-label="Search tasks">')
    V["plate"].append('<div class="tiles">'
                 + tile(len(b["overdue"]), "overdue", "bad", "overdue")
                 + tile(len(b["chase"]), "to chase", "wait", "chase")
                 + tile(len(b["cold"]), "going cold", "cold", "cold")
                 + tile(len(b["yours"]), "on you", "mine", "me")
                 + tile(len(b["theirs"]), "on others", "unk", "them")
                 + '<button class="tile clearf" data-filter="" hidden>'
                   "<b>&times;</b><span>show all</span></button>"
                 + "</div>")

    if urgent:
        # Grouped by front (her call, 2026-09-10): one flat global stack made
        # "rank 7" read as a scold. The order inside a front is the global
        # one; the rank itself is only the card's tooltip (28 Sep: printed,
        # it ran 1, 6, 7, 8, 2… and looked broken).
        V["plate"].append('<section id="attention"><h2>Needs you</h2>')
        _gidx = {w["name"]: i + 1 for i, w in enumerate(urgent)}
        _fr = {}
        for w in urgent:
            _fr.setdefault(w["area"], []).append(w)
        for _area in sorted(_fr, key=lambda a: min(_gidx[w["name"]]
                                                   for w in _fr[a])):
            V["plate"].append(f'<h3 class="area">{e(_area)}</h3>'
                              '<div class="stack">')
            V["plate"].extend(stackrow(w, _gidx[w["name"]], cfg)
                              for w in _fr[_area])
            V["plate"].append("</div>")
        V["plate"].append("</section>")

    if calm:
        V["plate"].append('<section id="all"><h2>Ticking over'
                     '<button class="addbutton needs-server" data-addkind="workstream">'
                     '+ New workstream</button></h2><div class="stack quiet">')
        areas = {}
        for w in calm:
            areas.setdefault(w["area"], []).append(w)
        for area in sorted(areas, key=str.lower):
            V["plate"].append(f'<h3 class="area">{e(area)}</h3>')
            V["plate"].extend(calmrow(w, cfg) for w in areas[area])
        V["plate"].append("</div></section>")

    snoozed = b.get("snoozed", [])
    if snoozed:
        # Asleep on purpose — parked with a wake date, out of every list until
        # then. One fold so the clutter is gone but nothing is hidden for real.
        V["plate"].append(f'<section id="asleep"><details class="ghost"><summary>'
                     f"Asleep &mdash; snoozed on purpose &middot; {len(snoozed)}</summary>")
        for w in snoozed:
            when = (f'wakes {e(dayfirst(w["snooze"]))}'
                    + (f' &middot; in {w["snooze_days"]}d'
                       if w.get("snooze_days") is not None else ""))
            V["plate"].append(
                f'<div class="asleeprow"><span class="rowname">{e(w["name"])}</span>'
                f'<span class="meta">{when}</span>'
                f'<button class="mini needs-server" data-wake="{e(w["name"])}">'
                "Wake now</button></div>")
        V["plate"].append("</details></section>")

    if closed:
        V["plate"].append(f'<section id="closed"><details class="ghost"><summary>Finished '
                     f"and dropped &middot; {len(closed)}</summary><div class=\"stack quiet\">")
        V["plate"].extend(calmrow(w, cfg) for w in closed)
        V["plate"].append("</div></details></section>")

    hood_inbox = ""
    for name, tid, add in (("waiting.md", "waiting",
                            '<button class="addbutton needs-server" data-addkind="waiting">'
                            "+ Add someone</button>"),
                           ("inbox.md", "inbox", "")):
        text = read(name)
        if tid == "inbox":
            # Under the hood since 28 Sep: Claude empties the inbox, and what
            # she sees of it is the receipt each capture gets. The raw file
            # stays readable there, for the times she wants to look.
            body = (MD.render(text, task_source=name) if text.strip()
                    else '<p class="empty">Empty. Anything you save with the '
                         "box lands here until Claude files it.</p>")
            hood_inbox = (
                '<details class="refblock hoodinbox" id="inbox"><summary>The raw '
                'inbox' + (f'<span class="reffresh">{text.count(chr(10) + "- ")} '
                           'lines</span>' if text.strip() else "")
                + f'</summary><div class="doc">{body}</div></details>')
            continue
        _ls = [ln.lstrip() for ln in text.split("\n")]
        n_owed = (max(0, sum(ln.startswith("|") for ln in _ls) - 2)   # header + rule
                  + sum(ln.startswith(("- ", "* ")) for ln in _ls))
        if tid == "waiting" and not n_owed:
            # Nothing owed: one faint line and the button, not a table of
            # column headers with no rows. The header's "3 waiting on others"
            # counts projects whose ball is with someone, so this line says
            # where those are rather than seeming to contradict it (28 Sep).
            n_theirs = len(b["theirs"])
            where = (f" The {n_theirs} project{'s' if n_theirs != 1 else ''}"
                     " waiting on someone "
                     + ("are" if n_theirs != 1 else "is")
                     + " in the lists above." if n_theirs else "")
            V["plate"].append(f'<section id="{tid}" class="waitempty">'
                              "<h2>Small things owed to you</h2>"
                              f'<p class="waitnone">None open.{where}</p>'
                              + add + "</section>")
        elif text.strip():
            V["plate"].append(f'<section id="{tid}" class="doc">'
                         + MD.render(text, task_source=name) + add + "</section>")

    def _fresh(name):
        try:
            mt = os.path.getmtime(os.path.join(BRAIN, name))
            d = (datetime.now() - datetime.fromtimestamp(mt)).days
            return "today" if d == 0 else "yesterday" if d == 1 else f"{d}d ago"
        except Exception:
            return ""

    ref = []
    for name, tid, label in (("next.md", "next", "Claude's ranking, and why"),
                             ("synced.md", "synced", "What your project folders say"),
                             ("decisions.md", "decisions", "Decisions you have made")):
        text = read(name)
        if text.strip():
            fr = _fresh(name)
            ref.append(f'<details class="refblock" id="{tid}"><summary>{label}'
                       + (f'<span class="reffresh">updated {fr}</span>' if fr else "")
                       + f'</summary><div class="doc">{MD.render(text, task_source=name)}</div>'
                       "</details>")
    # Reference is the brain's memory, not her plate: under the hood.
    hood_ref = "".join(ref)
    # The foot of the plate: pages with no open work, the big questions, the
    # idea shelf, an audit per area.
    V["plate"].append(plate_foot(cfg, ws))
    return hood_inbox, hood_ref

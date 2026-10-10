#!/usr/bin/env python3
"""Build brain/index.html — the page you actually read.

    python3 brain/tools/build.py

GENERATED. Never hand-edit index.html; edit the markdown and rebuild, or your
change disappears the next time anything runs. The markdown is the system; this
file only decides how it looks.

The design has one idea: the page is a ranked answer to "what deserves my next
hour?", not a wall of equal cards. The top priority gets the hero; the rest of
the urgent list is a numbered stack with decay bars; everything calm is pushed
down and quieted so the urgent things own the contrast.

Self-contained: everything it needs is bundled, so it renders with no netwraries. Works opened as
a plain file, but the buttons only write when it is served (see serve.py).
"""

import html
import json
import os
import re
import urllib.parse
import time
import sys
from datetime import date, datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import md as MD          # noqa: E402
import model as M        # noqa: E402
import usage as USAGE    # noqa: E402  (per-job "last ran" on the Claude tab)
import tour as TOUR      # noqa: E402  (the guided walkthrough)
import chrome as CHROME  # noqa: E402  (one nav for every page)
import talk as TALK      # noqa: E402  (dictation on Claude-facing inputs)
import news as NEWS      # noqa: E402  (the briefing on the News tab)
import agents as AG      # noqa: E402  (the page's fixed wording names the agent that runs)
import lines as LN       # noqa: E402  (each area as a subway line, for the New York style)

BRAIN = M.BRAIN
OUT = os.path.join(BRAIN, "index.html")


def now_minutes():
    """Minutes since midnight, in one place, so every part of the page agrees
    about what time it is. Before this, exactly one line in the whole builder
    read the clock — which is how the routine card came to say "Evening" while
    the hero above it still said "Your next hour" and the forecast still
    offered three hours that had already gone.

    BRAIN_NOW=HH:MM overrides it. That is for checking the page at nine in the
    morning and at ten at night without waiting thirteen hours.
    """
    stamp = os.environ.get("BRAIN_NOW", "").strip()
    if stamp:
        m = re.match(r"^(\d{1,2}):(\d{2})$", stamp)
        if m:
            return min(23, int(m.group(1))) * 60 + min(59, int(m.group(2)))
    n = datetime.now()
    return n.hour * 60 + n.minute


def hero_eyebrow():
    """The hero's label follows the day. "Your next hour" is a promise the
    page cannot keep at ten at night, and breaking it is what made the whole
    top of the page read as stale."""
    return {"morning": "Your next hour",
            "evening": "Still open tonight",
            "closed": "First thing tomorrow"}[day_phase()]


def day_phase():
    """morning | evening | closed — the day as the page should speak about it.
    17:00 is where the routine already turns the plan into a mirror, and 22:00
    is where the When card already stops drawing the day."""
    mins = now_minutes()
    if mins >= M.DAY_END_MINUTES:
        return "closed"
    return "evening" if mins >= 17 * 60 else "morning"


def read(name):
    try:
        # errors="replace": one stray Latin-1 byte in a synced file or the
        # inbox stopped the whole page build (9 Oct audit).
        with open(os.path.join(BRAIN, name), encoding="utf-8",
                  errors="replace") as f:
            return f.read()
    except FileNotFoundError:
        return ""


def e(s):
    return html.escape(str(s or ""), quote=True)


# --------------------------------------------------------------------------
# The queue — requests written from the page, worked by Claude Code.

# The People intro (rhythm-load advice + sync note) is read-once: one
# dismiss hides it on this device until the text would matter again.
_PINTRO_JS = """<script>
(function(){
  var pi = document.getElementById('pintro');
  if(!pi) return;
  var seen = null;
  try { seen = localStorage.getItem('people-intro-seen'); } catch(e){}
  if(!seen) pi.hidden = false;
  var x = document.getElementById('pintrox');
  if(x) x.onclick = function(){
    pi.hidden = true;
    try { localStorage.setItem('people-intro-seen', '1'); } catch(e){}
  };
})();
</script>"""

_WS_ROOM_CACHE = None


def _ws_room_slug(name):
    """workstream -> its room on rooms.html, from the rooms config."""
    global _WS_ROOM_CACHE
    if _WS_ROOM_CACHE is None:
        _WS_ROOM_CACHE = {}
        try:
            with open(os.path.join(BRAIN, "config.json"), encoding="utf-8") as f:
                cfg = json.load(f)
            for room in M.all_rooms(cfg):
                sl = room.get("slug") or M.room_slug(room.get("name", ""))
                for wsn in (room.get("ws") or []):
                    _WS_ROOM_CACHE[wsn] = sl
        except Exception:
            pass
    return _WS_ROOM_CACHE.get(name, "")


def queue_items():
    qdir = os.path.join(BRAIN, "queue")
    out = []
    if not os.path.isdir(qdir):
        return out
    for fn in sorted(os.listdir(qdir)):
        if not fn.endswith(".md") or fn.startswith("_"):
            continue
        try:
            with open(os.path.join(qdir, fn), encoding="utf-8",
                      errors="replace") as f:
                text = f.read()
        except OSError:
            continue
        meta, body = MD.split_frontmatter(text)
        outcome = ""
        m = re.search(r"^##\s+Outcome\s*$(.*)", body, re.M | re.S)
        if m:
            outcome = m.group(1).strip()
            body = body[:m.start()]
        out.append({
            "file": fn,
            "title": meta.get("title", fn[:-3]),
            "status": (meta.get("status") or "pending").lower(),
            "mode": meta.get("mode", ""),
            "created": meta.get("created", ""),
            "body": body.strip(),
            "outcome": outcome,
        })
    rank = {"working": 0, "pending": 1, "done": 2, "dropped": 3}
    # Active items oldest-first (a queue is FIFO); finished ones newest-first
    # (what just happened belongs on top of the pile).
    active = sorted((q for q in out if rank.get(q["status"], 9) < 2),
                    key=lambda q: (rank[q["status"]], q["created"]))
    closed = sorted((q for q in out if rank.get(q["status"], 9) >= 2),
                    key=lambda q: q["created"], reverse=True)
    return active + closed


# --------------------------------------------------------------------------
# Derived display pieces

def artvid(name, size=132, cls="cardart"):
    """A looping mascot clip. Poster and video share a base name and the same
    framing, so nothing jumps when the video takes over.

    Video cannot carry alpha, so these rely on `mix-blend-mode: multiply`
    against the paper — which only disappears if the clip's ground is PURE
    white, and Veo's is a few points under. The CSS lifts it the rest of the
    way; see .artvid.
    """
    return (f'<video class="artvid {cls}" autoplay muted loop playsinline '
            f'poster="art/{name}.png?v=2" width="{size}" height="{size}" '
            f'aria-hidden="true">'
            f'<source src="art/{name}.mp4?v=2" type="video/mp4"></video>')


def artimg(name, size=72, cls="cardart"):
    """A still. These are real transparent PNGs, so they must NOT get the
    multiply treatment — it would darken the olive against the paper for no
    reason. Different class on purpose."""
    return (f'<img class="artpng {cls}" src="art/{name}.png?v=2" alt="" '
            f'width="{size}" height="{size}" aria-hidden="true">')


def cardhead(inner, art=""):
    """A card's heading with its mascot beside it, as a flex row.

    Floating the art instead put it in the flow of the rows below, and an
    `<li>` that is a flex container is a block-formatting-context root — so
    it shortens itself to avoid a float. That is exactly why one row's
    buttons sat left of every other row's. A row of its own cannot collide
    with anything.
    """
    if not art:
        return inner
    return f'<div class="cardhead">{inner}<span class="cardhead-art">{art}</span></div>'


def heroline(eyebrow_html, art=""):
    """The hero's eyebrow and its mascot on one row — the same shape every
    other card uses.

    The hero used to float its mascot right, which parked it a gutter's width
    from the routine card's own mascot: two brains at the same height staring
    at each other across the page. On the left of its own heading it reads as
    this section's picture, like every other one, and the two are at opposite
    ends of the row.
    """
    return cardhead(f'<div class="heroline">{eyebrow_html}</div>', art)


def clip(s, n):
    """Cut to a word boundary, not mid-word. A label ending "finish &" reads
    like a bug even when the data behind it is right."""
    s = (s or "").strip()
    if len(s) <= n:
        return s
    cut = s[:n].rsplit(" ", 1)[0].rstrip(" ,;:—-&")
    return (cut or s[:n]) + "…"


def why_line(w, hero=False, skip_task="", plain_urgent=False):
    """The one sentence that says why this is at the top. Plain words a person
    can act on beat a coloured dot they have to decode.

    `skip_task` is the text the CALLER is already showing. The reason and the
    task name are two different fields that usually resolve to the same
    sentence, and the hero was printing both four lines apart — the urgency
    ("needed doing 13 days ago") is the part she cannot work out for herself,
    so that stays and the restatement goes.

    `plain_urgent` drops the "you marked this urgent" badge and leads with the
    task. She marks nearly everything urgent, so the flag lands on a third of
    the priority stack and most of the digest — at that density it sorts
    nothing, and it eats the width the row needs to say WHICH thing it is.
    """
    def tail(task):
        task = task or ""
        if not task or (skip_task and _same_thing(task, skip_task)):
            return ""
        return f": {e(task)}"

    bits = []
    if w["overdue"]:
        d = abs(w["days_to_due"])
        bits.append(f"<b>{d}d overdue</b>")
    elif w["due_soon"]:
        d = w["days_to_due"]
        bits.append("<b>due today</b>" if d == 0 else f"due in <b>{d}d</b>")
    # The lead-time reason first, because it is the one she cannot work out
    # for herself. "Due the 24th" looks calm in the middle of the month; "the
    # seat should have been bought a week ago" is the same fact, acted on.
    if w.get("pressed_late"):
        d = abs(w.get("pressed_act_days") or 0)
        bits.append(f'<b title="needed doing {d} days ago">{d}d late</b>'
                    + tail(w.get("pressed_task", "")))
    elif w.get("pressed_lead") and (w.get("pressed_act_days") or 99) <= 7:
        d = w.get("pressed_act_days") or 0
        when = "today" if d == 0 else f"in {d}d"
        bits.append(f"<b>do {when}</b>" + tail(w.get("pressed_task", "")))
    elif w.get("task_overdue"):
        bits.append("<b>task overdue</b>"
                    + tail(w.get("next_due_task", "")))
    elif w.get("task_urgent"):
        t = w.get("next_due_task", "")
        if not plain_urgent:
            bits.append("<b>marked urgent</b>" + tail(t))
        elif t and not (skip_task and _same_thing(t, skip_task)):
            # WHICH task she flagged still discriminates even where the flag
            # itself doesn't — unless the row already has that task on its
            # face, in which case the whole reason line goes quiet. A row with
            # nothing to add says nothing.
            bits.append(e(t))
    elif w.get("task_due_soon") and not w["due_soon"] and not w["overdue"]:
        bits.append("task due soon"
                    + tail(w.get("next_due_task", "")))
    if w.get("goal_overdue") and w.get("goal_text"):
        # A slipped finish line is a reason the card is red, so it says so.
        # Unsaid, an app's card was red with nothing on it that was late
        # (8 Oct).
        d = abs(w.get("goal_days") or 0)
        bits.append(f'finish line <b>{d}d</b> late: {e(w["goal_text"])}')
    if w.get("goal_pull") and not w.get("goal_overdue"):
        d = w.get("goal_days")
        if d is not None and d <= 45:
            bits.append(f'finish line in <b>{d}d</b>: {e(w.get("goal_text", ""))}')
    if w["chase"]:
        who = f"{e(w['ball_who'])} " if w["ball_who"] else ""
        bits.append(f'<span title="silence for {w["days_waiting"]} days">'
                    f"{who}silent <b>{span(w['days_waiting'])}</b></span>")
    if w["cold"]:
        bits.append(f'<span title="untouched for {w["days_untouched"]} days">'
                    f"untouched <b>{span(w['days_untouched'])}</b></span>")
    if w["never_touched"] and not w["cold"]:
        bits.append("never started")
    if w.get("stale_text"):
        s2 = w["stale_text"][0]
        bits.append(f'<span title="written before {e(s2["label"])}, which has'
                    ' passed. The next session will reword it">stale'
                    f' &middot; <b>{e(s2["label"])}</b> passed</span>')
    if w["status"] == "blocked" and not bits:
        bits.append("blocked")
    return " &middot; ".join(bits)


def decay(w, cfg):
    """0..1: how far this item has slid toward its threshold. The bar under
    each priority row — you can see things rotting before they're rotten."""
    if w["overdue"]:
        return 1.0
    vals = []
    if w["ball"] == "them" and w["days_waiting"] is not None:
        vals.append(w["days_waiting"] / max(int(cfg.get("chase_days", 7)), 1))
    if w["days_untouched"] is not None:
        vals.append(w["days_untouched"] / max(int(cfg.get("cold_days", 14)), 1))
    if w["days_to_due"] is not None and w["days_to_due"] >= 0:
        # Deadline pressure: full as the date arrives.
        span = max(int(cfg.get("soon_days", 7)), 1)
        vals.append(1.0 - min(w["days_to_due"], span) / span)
    if w["never_touched"]:
        vals.append(0.85)
    return min(max(vals, default=0.0), 1.0)


# The chip must say what it means on its own: whose court the next move is in.
BALLS = {"me": ("on you", "mine"), "them": ("with them", "wait"),
         "nobody": ("no one waiting", "unk")}


def ballchip(w):
    label, cls = BALLS[w["ball"]]
    who = f" &middot; {e(w['ball_who'])}" if w["ball"] == "them" and w["ball_who"] else ""
    return f'<span class="v v-{cls}">{label}{who}</span>'


def actions(w, labelled=False):
    """Grouped, not five identical pills in a row: what you do most (add a
    task, mark it worked) sits on the left, whose-court is one labelled
    control, and Claude is the odd one out on the right. `labelled` names
    the workstream in the row — on the hero, other cards sit between the
    title and these buttons and the scope stops being obvious.

    Ten controls on the hero was more decision than the thing itself needed.
    "Not today" and "Snooze" were one gesture wearing two labels, so Snooze
    keeps it and says how long; "Done" is irreversible and sat directly beside
    "Worked on it today", the one you press most, so it moves to the far end.

    Eight was still eight, all the same shape, and reading them took longer
    than doing any of them. Four now — add work, mark it worked, whose move,
    the way in — and the five you reach for occasionally live behind one "…".
    Done goes in there on purpose: it cannot be undone and should not be one
    stray tap from the button you press most.
    """
    n = e(w["name"])
    lab = (f'<span class="actsfor">for {n}:</span>' if labelled else "")
    me = " on" if w["ball"] == "me" else ""
    them = " on" if w["ball"] == "them" else ""
    focused = bool(w.get("focus_until"))
    foc = "&#9733; Focused" if focused else "&#9734; Focus on this"
    # The front's own page — its room — is where the whole project lives.
    _rsl = _ws_room_slug(w["name"])
    room = (f'<a class="act" href="rooms.html#room/{_rsl}" title="The whole'
            ' project: tasks, finish lines, people, its folder, its'
            ' conversations">Its page &rarr;</a>' if _rsl else "")
    return ('<div class="acts needs-server">' + lab
            + f'<button class="act" data-addtask="{n}"><b>+</b> Task</button>'
            + f'<button class="act" data-touch="{n}" title="Records today as the last '
            f'day you worked on this, so it stops showing as untouched">Worked on it today</button>'
            '<span class="ballgroup" role="group" aria-label="Whose court">'
            '<span class="balllabel" title="Whose move is next on this">Next move</span>'
            f'<button class="ball{me}" data-ball="me" data-name="{n}">mine</button>'
            f'<button class="ball{them}" data-ball="them" data-name="{n}">theirs</button>'
            "</span>"
            f'<button class="act" data-wsopen="{n}" title="The whole project on one '
            'side screen: dates, people, tasks, notes, its folder">Details</button>'
            + room
            # everything below is real but occasional — one button, not five
            + '<span class="moreWrap">'
            + f'<button class="act moreBtn" aria-haspopup="true" aria-expanded="false"'
            f' data-more="{n}" title="Focus, snooze, tell {AG.short()}, mark it done">'
            '&hellip;</button>'
            + '<span class="moreMenu" hidden>'
            + f'<button class="mi wsfocus{" on" if focused else ""}"'
            f' data-wsfocus="{n}" data-until="{e(w.get("focus_until") or "")}"'
            ' title="Keeps this at the top of the list for a few days without '
            'a new task. It lapses by itself">' + foc + "</button>"
            + f'<button class="mi" data-snooze="{n}" title="Hides this until a date '
            'you pick, then brings it back">Snooze&hellip;</button>'
            + f'<button class="mi" data-box data-box-ws="{n}" title="Opens the box'
            ' already holding this project">&#10022; Talk about it</button>'
            + '<span class="misep"></span>'
            + f'<button class="mi danger wsdone" data-wsdone="{n}"'
            ' title="Mark it finished and take it off the plate">&#10003; Done</button>'
            + "</span></span>"
            "</div>")


# Names of everyone in people.md, longest first — set once per build so task
# text can link "Frankie" straight to Frankie on the People tab.
PERSON_NAMES = []
# Presenting mode (privacy.py, PRIVACY-PLAN.md phase 6): while she shares her
# screen the pages are built WITHOUT the private parts, so the text is not in
# the HTML at all. Set at the top of build(); the tabs read it from here.
PRESENTING = None
PRESENT_HIDDEN_KEYS = set()
PRESENT_KEPT_KEYS = set()
PRESENT_NAMES_RX = None
PRESENT_NOTE = ('<section class="lifecard"><p class="lcnone">Hidden while '
                'presenting.</p></section>')
PRESENT_BANNER = (
    '<div id="presenting" style="position:sticky;top:0;z-index:9999;'
    'display:flex;gap:12px;align-items:center;justify-content:center;'
    'padding:8px 14px;background:var(--ink,#222);color:var(--paper,#fff);'
    'font:600 13px/1.3 var(--sans,system-ui)">Presenting: private parts hidden'
    '<button class="needs-server" data-unpresent style="font:inherit;'
    'padding:4px 10px;border-radius:6px;border:1px solid currentColor;'
    'background:transparent;color:inherit;cursor:pointer">Turn off</button>'
    '</div><script>document.addEventListener("click",function(ev){'
    'var b=ev.target.closest("[data-unpresent]");if(!b)return;b.disabled=true;'
    'fetch("/api/privacy/presenting",{method:"POST",headers:{"Content-Type":'
    '"application/json"},body:JSON.stringify({on:false})}).then(function(){'
    'setTimeout(function(){location.reload();},1500);});});</script>')


def present_md(text):
    """Today's plan while presenting: headings and task lines only, minus
    the tasks of the hidden areas. Free text goes, because it can name
    anyone; so do the two-minute chases, which name people by design."""
    out, skip = [], False
    lines = (text or "").splitlines()
    # The header block (updated: and the rest) stays: other code reads it.
    if lines and lines[0].strip() == "---" and "---" in [x.strip() for x in lines[1:]]:
        end = 1 + [x.strip() for x in lines[1:]].index("---")
        out, lines = lines[:end + 1], lines[end + 1:]
    for line in lines:
        if line.startswith("#"):
            skip = bool(re.match(r"#+\s*Two-minute chases", line, re.I))
            if not skip:
                out.append(line)
            continue
        if skip:
            continue
        # Only a line that is a kept task: one worded a little differently
        # from its hidden original got through (8 of 8 in the 9 Oct audit).
        m = re.match(r"\s*[-*]\s+\[[ xX]\]\s+(.*)$", line)
        if (m and MD.taskkey(MD.bare(m.group(1))) in PRESENT_KEPT_KEYS
                and not (PRESENT_NAMES_RX and PRESENT_NAMES_RX.search(m.group(1)))):
            out.append(line)
    return "\n".join(out) + "\n"
# alias → the person it belongs to ("Mum" → "Maman"), set per build
PERSON_ALIAS = {}


_ESCAPED = {"key": None, "names": [], "aliases": []}


def _escaped_people():
    """PERSON_NAMES and PERSON_ALIAS escaped once per build, not once per
    call — linknames runs two thousand times a build."""
    key = (id(PERSON_NAMES), len(PERSON_NAMES), id(PERSON_ALIAS), len(PERSON_ALIAS))
    if _ESCAPED["key"] != key:
        _ESCAPED.update(
            key=key, names=[e(nm) for nm in PERSON_NAMES],
            aliases=[(al, e(al)) for al in
                     sorted(PERSON_ALIAS, key=len, reverse=True)])
    return _ESCAPED["names"], _ESCAPED["aliases"]


# After a name: not inside a tag (no ">" before the next "<"), and not in a
# link's own text (no "</a>" before the next tag).
_OUTSIDE_LINKS = r"(?![^<]*>)(?![^<]*</a>)"


def linknames(escaped):
    """Wrap known person names in already-escaped text with a People-tab link.
    Aliases count: "Mum" is a door to Maman, because that is the word she
    writes — and the alias pass runs LAST behind a placeholder, so the
    canonical pass cannot rewrite a name sitting inside the link it just
    made (which produced nested anchors)."""
    # The plain substring test first: it is C-fast and rules out nearly every
    # name, where compiling a pattern per name per call was half the build.
    names, aliases = _escaped_people()
    for enm in names:
        if enm not in escaped:
            continue
        # Not inside a tag, and not inside a link already made: names go
        # longest first, so "Bexley" found itself in the "Bexley Yael"
        # link and printed its markup as text (9 Oct audit).
        pat = re.compile(r"\b" + re.escape(enm) + r"\b" + _OUTSIDE_LINKS)
        if not M.name_in(enm, escaped):
            continue                 # "May merge…" is grammar, not the person
        if pat.search(escaped):
            # A function, not a template: a backslash in a name read as a
            # group reference and stopped the whole build (9 Oct audit).
            link = f'<a class="plink" href="#people" data-plink="{enm}">{enm}</a>'
            escaped = pat.sub(lambda _m, link=link: link, escaped, count=1)
    # Aliases afterwards, with the target name hidden in a placeholder so no
    # later pass can see it as prose.
    for al, eal in aliases:
        if eal not in escaped:
            continue
        if "data-plink" in escaped and eal in escaped.split(">")[0]:
            continue
        if not M.name_in(eal, escaped):
            continue
        pat = re.compile(r"\b" + re.escape(eal) + r"\b" + _OUTSIDE_LINKS)
        if pat.search(escaped):
            who = "\x00" + e(PERSON_ALIAS[al]) + "\x00"
            link = f'<a class="plink" href="#people" data-plink="{who}">{eal}</a>'
            escaped = pat.sub(lambda _m, link=link: link, escaped, count=1)
    return escaped.replace("\x00", "")


# Live workstream names, longest first — set per build alongside PERSON_NAMES.
WS_NAMES = []
# Recent done queue outcomes attached to their workstreams — set per build.
WS_OUTCOMES = {}


def prepared_fold(wsname, open_fresh=False):
    """The '✦ Claude prepared this' block: recent outcomes rendered ON the
    thing they belong to — the train options live on the Frankie hero, not
    only in the Claude tab archive. Open by default when the work landed
    today and the caller asks (the hero); a quiet fold everywhere else."""
    its = WS_OUTCOMES.get((wsname or "").lower(), [])
    if not its:
        return ""
    today_s = date.today().isoformat()
    is_open = open_fresh and (its[0]["created"] or "")[:10] == today_s
    # Only the NEWEST outcome shows in full — an older card's "what you need
    # to do" list is stale the moment newer work supersedes it. Earlier items
    # fold away instead of stacking up as clutter.
    def _item(i):
        return ('<div class="prepitem">' + linkify_html(MD.render(i["outcome"]))
                + f'<p class="meta">{e(dayfirst((i["created"] or "")[:10]))} &middot; '
                '<a href="#/hood" data-hoodgo="finished">the full card</a></p></div>')
    inner = _item(its[0])
    if len(its) > 1:
        inner += ('<details class="prepolder"><summary>earlier work '
                  f'({len(its) - 1}), since replaced</summary>'
                  + "".join(_item(i) for i in its[1:3]) + "</details>")
    # The response is a conversation, not a verdict: a follow-up asked right
    # here continues from what was already found instead of starting over.
    ask = ('<div class="prepask needs-server">'
           f'<input class="prepin" data-prepctx="{e(its[0]["title"][:90])}"'
           f' data-prepws="{e(wsname)}" autocomplete="off"'
           ' placeholder="Ask a follow-up to this&hellip;">'
           '<button class="mini prepgo">ask &amp; run</button>'
           f'<button class="mini prepshot" data-shotctx="{e(its[0]["title"][:90])}"'
           f' data-shotws="{e(wsname)}" title="Once it is bought or done, attach the '
           f'confirmation screenshot. {AG.short()} ticks the task and files the '
           'details">done: add screenshot</button></div>')
    return (f'<details class="prep"{" open" if is_open else ""}>'
            f'<summary>&#10022; {AG.short()} prepared this'
            f'{f" &middot; {len(its)}" if len(its) > 1 else ""}</summary>'
            + inner + ask + "</details>")


def ready_marks(drafts, qitems, ws, today_md):
    """Finished Claude work, mapped back to the task row it came from.

    She asks for help from a task row, the work lands in a draft or a queue
    outcome, and then she has to go looking for it — which is the whole
    complaint. Two links already exist in the data and were going unused: a
    draft's `task:` field, and the task name the row's &#10022; button writes
    into the ask's title. Both resolve to the row's own tick key, so the row
    can say "this one is answered" and open the answer.

    Returns {taskkey: [{kind, file, label, id, created}, ...]}, newest first.
    """
    # Every task the page can show a row for, keyed the way its tickbox is.
    rows = {}                      # taskkey -> normalised text
    def _add(raw):
        try:
            key = MD.taskkey(MD.bare(raw))
        except Exception:
            return
        n = M._dnorm(MD.plain(raw))
        if len(n) >= 16:
            rows.setdefault(key, n)
    for mt in re.finditer(r"^\s*[-*]\s+\[[ xX]\]\s+(.*)$", today_md or "", re.M):
        _add(mt.group(1))
    for w in ws:
        for t in w["tasks"]:
            _add(t["text"])

    marks = {}
    def _hit(needle, kind, file, label, created, ident):
        if len(needle) < 16:
            return
        for key, n in rows.items():
            # A queue title is truncated to ~60 chars, so a prefix counts.
            if needle in n or n in needle or n.startswith(needle):
                marks.setdefault(key, []).append(
                    {"kind": kind, "file": file, "label": label,
                     "created": created, "id": ident})
                return

    for d in drafts:
        if d.get("stale") or not d.get("task"):
            continue
        _hit(M._dnorm(d["task"]), "draft", d["file"],
             {"email": "draft ready", "message": "draft ready",
              "form": "form text ready"}.get(d["kind"], "notes ready"),
             d.get("created", ""), "d:" + d["file"])

    for it in qitems:
        if it["status"] != "done" or not it["outcome"]:
            continue
        m = re.search(r"(?:for me|task)\s*:\s*[\"“]([^\"”]+)",
                      it["title"] or "")
        if not m:
            continue
        _hit(M._dnorm(m.group(1)), "work", it["file"], AG.short() + " answered",
             it.get("created", ""), "q:" + it["file"])

    for key in marks:
        marks[key].sort(key=lambda x: x["created"] or "", reverse=True)
    return marks


def ready_templates(marks):
    """The grafts themselves. Templates rather than inline markup because the
    same row is rendered in three places (the plan, the plate, a drawer) and
    the JS puts the pill on whichever copies exist."""
    if not marks:
        return ""
    out = ['<div id="rdytpls" hidden>']
    for key, its in marks.items():
        i = its[0]
        extra = f' &middot; {len(its)}' if len(its) > 1 else ""
        out.append(
            f'<template class="rdytpl" data-rdykey="{e(key)}"'
            f' data-rdyid="{e(i["id"])}">'
            f'<button class="rdy" data-rdykind="{e(i["kind"])}"'
            f' data-rdyfile="{e(i["file"])}" data-rdyid="{e(i["id"])}"'
            f' title="{AG.short()} already did this one. Open what it wrote">'
            f'&#10022; {e(i["label"])}{extra}</button></template>')
    out.append("</div>")
    return "".join(out)


def ask_label(item, cap=64):
    """A short human label for a queued ask — markdown stripped, cut at a word
    boundary. An ask sent from a room opens with a context preamble the page
    wrote, so every card in a room read "About the project X (workstream…" and
    none of them said what she had actually asked. Her own words follow "The
    ask:", and those are the label when they are there."""
    body = item.get("body") or ""
    m = re.search(r"The ask:\s*(.+)", body)
    src = (m.group(1) if m
           else (item.get("title") or body or item.get("file") or "")).strip()
    t = re.sub(r"\s+", " ", MD.plain(src.split("\n")[0]))
    if len(t) > cap:
        t = t[:cap].rsplit(" ", 1)[0] + "…"
    return t


def draft_label(fname):
    """A draft's file name as words: 2026-09-10-lease-reply-landlord.md reads
    "the lease reply landlord draft". The date goes; she knows when."""
    stem = re.sub(r"\.md$", "", fname)
    stem = re.sub(r"^\d{4}-\d{2}-\d{2}-", "", stem)
    words = stem.replace("-", " ").replace("_", " ").strip()
    return f"the {words} draft" if words else "the draft"


def linkify_html(html):
    """Turn plain mentions inside already-rendered HTML into doors: person
    names to their People row, workstream names to their drawer. The feed
    becomes the connective tissue of the app instead of a transcript."""
    parts = re.split(r"(<[^>]+>)", html)
    for i, seg in enumerate(parts):
        if not seg or seg.startswith("<"):
            continue
        seg = linknames(seg)
        for wn in WS_NAMES:
            ewn = e(wn)
            pat = re.compile(r"\b" + re.escape(ewn) + r"\b" + _OUTSIDE_LINKS)
            if pat.search(seg):
                link = f'<a class="plink" href="#" data-wsopen="{ewn}">{ewn}</a>'
                seg = pat.sub(lambda _m, link=link: link, seg, count=1)
        # A draft mentioned by path becomes a door to the draft itself.
        # "(draft ready in drafts/)" — the shorthand she actually sees
        seg = re.sub(r"\bdrafts/(?![A-Za-z0-9._\-]*\.md)",
                     '<a class="plink draftjump" href="#/today">For you'
                     ' &#8599;</a>', seg)
        # Named, because two drafts in one paragraph both reading "the draft"
        # is a link she has to click to identify.
        seg = re.sub(r"brain/drafts/([A-Za-z0-9._\-]+\.md)",
                     lambda m2: ('<a class="plink draftjump" href="#/today"'
                                 f' data-draftjump="{m2.group(1)}">'
                                 + e(draft_label(m2.group(1)))
                                 + " &#8599;</a>"),
                     seg)
        parts[i] = seg
    return iso_prose("".join(parts))


def room_labels(cfg):
    """Workstream name -> the short room name she uses for it.

    "Export — wine dossier for the client" is the workstream's full name and
    the wrong size for a chip; the room it sits in is called "Wine Dossier".
    Falls back to the workstream name when a workstream has no room.
    """
    out = {}
    for room in M.all_rooms(cfg):
        for name in (room.get("ws") or []):
            if room.get("name"):
                out[name] = room["name"]
    return out


TALK_SVG = ('<svg viewBox="0 0 24 24" fill="none" stroke="currentColor"'
            ' stroke-width="2" stroke-linecap="round" stroke-linejoin="round"'
            ' aria-hidden="true"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0'
            ' 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>')


# Line icons for the glance rows (her ask, 28 Sep: fewer words to read,
# more to see). Path data only; ico() wraps it in the same stroke style as
# TALK_SVG so they sit in the text's colour on every skin.
_CLOUD = '<path d="M4 14.9A7 7 0 1 1 15.7 8h1.8a4.5 4.5 0 0 1 2.5 8.2"/>'
ICONS = {
    "pin": '<path d="M20 10c0 5-5.5 10.2-7.4 11.8a1 1 0 0 1-1.2 0C9.5 20.2 4 15'
           ' 4 10a8 8 0 0 1 16 0"/><circle cx="12" cy="10" r="3"/>',
    "sun": '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4'
           ' 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M6.3 17.7l-1.4 1.4M19.1 4.9l-1.4'
           ' 1.4"/>',
    "cloudsun": '<path d="M12 2v2M4.9 4.9l1.4 1.4M20 12h2M19.1 4.9l-1.4 1.4M15.9'
                ' 12.7a4 4 0 0 0-5.9-4.1"/><path d="M13 22H7a5 5 0 1 1 4.9-6H13a3'
                ' 3 0 0 1 0 6Z"/>',
    "cloud": '<path d="M17.5 19H9a7 7 0 1 1 6.7-9h1.8a4.5 4.5 0 1 1 0 9Z"/>',
    "rain": _CLOUD + '<path d="M16 14v6M8 14v6M12 16v6"/>',
    "drizzle": _CLOUD + '<path d="M8 19v1M8 14v1M16 19v1M16 14v1M12 21v1M12 16v1"/>',
    "storm": '<path d="M6 16.3A7 7 0 1 1 15.7 8h1.8a4.5 4.5 0 0 1 .5 9"/>'
             '<path d="m13 12-3 5h4l-3 5"/>',
    "snow": _CLOUD + '<path d="M8 15h.01M8 19h.01M12 17h.01M12 21h.01M16'
                     ' 15h.01M16 19h.01"/>',
    "fog": _CLOUD + '<path d="M16 17H7M17 21H9"/>',
    "umbrella": '<path d="M22 12a10 10 0 0 0-20 0Z"/><path d="M12 12v8a2 2 0 0 0'
                ' 4 0M12 2v1"/>',
    "sunset": '<path d="M12 10V2M4.9 10.9l1.4 1.4M2 18h2M20 18h2M19.1 10.9l-1.4'
              ' 1.4M22 22H2M16 6l-4 4-4-4M16 18a4 4 0 0 0-8 0"/>',
    "wind": '<path d="M12.8 19.6A2 2 0 1 0 14 16H2M17.5 8a2.5 2.5 0 1 1 2 4H2M9.8'
            ' 4.4A2 2 0 1 1 11 8H2"/>',
    "cap": '<path d="M21.4 10.9a1 1 0 0 0 0-1.8l-8.6-3.9a2 2 0 0 0-1.7 0L2.6 9.1a1'
           ' 1 0 0 0 0 1.8l8.6 3.9a2 2 0 0 0 1.7 0zM22 10v6M6 12.5V16a6 3 0 0 0'
           ' 12 0v-3.5"/>',
    "calendar": '<rect x="3" y="4" width="18" height="18" rx="2"/><path d="M16'
                ' 2v4M8 2v4M3 10h18"/>',
    "flag": '<path d="M4 22V4a1 1 0 0 1 .4-.8A6 6 0 0 1 8 2c3 0 5 2 7.3 2A6 6 0 0'
            ' 0 19 3.2a1 1 0 0 1 1 .8v10a1 1 0 0 1-.4.8A6 6 0 0 1 16 16c-3 0-5-2'
            '-8-2a6 6 0 0 0-4 1.3"/>',
    "doc": '<path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z"/>'
           '<path d="M14 2v4a2 2 0 0 0 2 2h4M9 15l2 2 4-4"/>',
    "reply": '<path d="m9 17-5-5 5-5"/><path d="M20 18v-2a4 4 0 0 0-4-4H4"/>',
    "cake": '<path d="M20 21v-8a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8M4 16s.5-1 2-1 2.5'
            ' 2 4 2 2.5-2 4-2 2.5 2 4 2 2-1 2-1M2 21h20M7 8v3M12 8v3M17 8v3"/>',
    "clock": '<circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/>',
    "mic": '<path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z"/>'
           '<path d="M19 10v2a7 7 0 0 1-14 0v-2M12 19v3"/>',
    "play": '<path d="M7 4v16l13-8Z"/>',
    "image": '<rect x="3" y="3" width="18" height="18" rx="2"/>'
             '<circle cx="9" cy="9" r="2"/><path d="m21 15-3.1-3.1a2 2 0 0 0'
             '-2.8 0L6 21"/>',
    "alert": '<path d="m21.7 18-8-14a2 2 0 0 0-3.4 0l-8 14A2 2 0 0 0 4 21h16'
             'a2 2 0 0 0 1.7-3Z"/><path d="M12 9v4M12 17h.01"/>',
    "send": '<path d="m22 2-7 20-4-9-9-4Z"/><path d="M22 2 11 13"/>',
    "grip": '<circle cx="9" cy="6" r="1"/><circle cx="9" cy="12" r="1"/>'
            '<circle cx="9" cy="18" r="1"/><circle cx="15" cy="6" r="1"/>'
            '<circle cx="15" cy="12" r="1"/><circle cx="15" cy="18" r="1"/>',
}


def ico(name):
    return ('<svg class="ico" viewBox="0 0 24 24" fill="none" stroke="currentColor"'
            ' stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"'
            ' aria-hidden="true">' + ICONS.get(name, "") + "</svg>")


def security_card():
    """The security alarm (sentinel.py): a change to the brain's safety code
    she has not confirmed. It sits above the plan because only she can
    answer it, and it stays until she does, with Touch ID.

    Approving clears the alarm and changes no code, so the card carries the
    evidence, one fold per change: what it guards, when, the commits since
    her last approval (an automatic save says so, since its message says
    nothing), how many lines in which functions, and the lines themselves.
    Her ask (7 Oct): clear enough to approve properly, not to get it over
    with. Until then a change was a label and a time, the rest in a tooltip."""
    try:
        import sentinel
        d = sentinel.details()
    except Exception as exc:                             # noqa: BLE001
        # Failing quiet read as "nothing changed" (9 Oct audit). Say it.
        print("SECURITY: the alarm could not check the safety code:", exc)
        return ('<section class="seccard" id="security"><h3 class="area">'
                "The security alarm couldn&rsquo;t check</h3>"
                f'<p class="draftnote">{e(str(exc)[:200])}. Until it can, a '
                "change to the brain&rsquo;s safety code would not show here."
                "</p></section>")
    ch = d["items"]
    if not ch:
        return ""
    today = date.today().strftime("%d %b")

    def when_of(txt):
        # git's "07 Oct 13:37" reads "today 13:37" on the day itself
        txt = txt or ""
        return ("today " + txt[7:]) if txt[:6] == today else txt

    def line(l):
        cls = ("add" if l.startswith("+") else "del" if l.startswith("-")
               else "hunk" if l.startswith("@@") else "")
        return f'<span class="{cls}">{e(l)}</span>' if cls else e(l)

    def item(c):
        # sentinel.py's labels are fixed wording ("the sandbox rules for
        # Claude runs"): they name the agent that runs. The one that lists
        # all three agents stays as written.
        w = c["what"] if "Codex" in c["what"] else AG.say(c["what"])
        what = w[:1].upper() + w[1:]
        if c["kind"] == "state":
            # Boxed and opening like the code items, to what the setting
            # says now (9 Oct: loose lines with a bare key glued on).
            ev = "".join(f"<li>{e(x)}</li>" for x in c.get("evidence") or [])
            return (f'<li class="secitem"><details><summary><b>{e(what)}</b>'
                    f'<span class="secwhen">{e(c["label"])}</span></summary>'
                    f'<div class="secbody"><ul class="secstate">{ev}</ul></div>'
                    "</details></li>")
        latest = c["commits"][0]["when"] if c["commits"] else ""
        bits = ["not saved yet" if c["uncommitted"] else
                (when_of(latest) if latest else "changed")]
        if c["kind"] == "built":
            bits.append("rebuilt")
        elif c["added"] or c["removed"]:
            bits.append(f'+{c["added"]} &minus;{c["removed"]} lines')
        where = c["part"] or ", ".join(c["funcs"][:3])
        if where:
            bits.append("in " + e(where))
        commits = "".join(
            f'<li><span class="secwhen">{e(when_of(m["when"]))}</span> '
            + ('<i>automatic save, its message says nothing about this</i>'
               if m["auto"] else e(m["subject"])) + "</li>"
            for m in c["commits"])
        if c["uncommitted"]:
            commits += '<li><i>changed on disk, not saved to git yet</i></li>'
        diff = ("<pre class=\"secdiff\">" + "\n".join(line(l) for l in c["diff"])
                + "</pre>") if c["diff"] else ""
        return (f'<li class="secitem"><details><summary><b>{e(what)}</b>'
                f'<span class="secwhen">{" &middot; ".join(bits)}</span></summary>'
                f'<div class="secbody"><p class="secfile">{e(c["key"])}</p>'
                f'<ul class="seccommits">{commits}</ul>{diff}</div></details></li>')

    since = ""
    try:
        since = datetime.fromisoformat(d["since"]).strftime("%-d %b, %H:%M")
    except (TypeError, ValueError):
        pass
    ask = ("Go through the security changes waiting for my approval, one by "
           "one. Run python3 brain/tools/sentinel.py --diff, then for each "
           "change say in plain words what it does, why it was likely made, "
           "and whether it weakens any protection. Change nothing.")
    n = len(ch)
    return ('<section class="secalarm" role="alert">'
            '<p class="eyebrow">Security</p>'
            f"<h2>{n} change{'' if n == 1 else 's'} to the brain&rsquo;s "
            "safety code to check</h2>"
            + (f'<p class="secsince">Since you last approved, {e(since)}. '
               "Open each one.</p>" if since else "")
            + f'<ul class="secitems">{"".join(item(c) for c in ch)}</ul>'
            '<div class="secacts">'
            '<button class="ghostbtn" data-box data-box-intent="investigate" '
            f'data-box-text="{e(ask)}">Ask {AG.short()} to explain them</button>'
            '<button class="btnp needs-server" id="secseen">'
            "I&rsquo;ve checked them: approve with Touch ID</button></div>"
            '<p class="secnote">Approving only clears this alarm; it changes no '
            f"code. If one looks wrong, ask {AG.short()} to undo it first.</p>"
            "</section>")


def glance_row(parts, cls="wxline"):
    """A line of icon + value chips. Each part: icon, text, and optionally a
    small leading label, a title (the words, on hover) and a kind that the
    CSS can colour. The words stay in the title so nothing is lost."""
    out = []
    for p in parts:
        if not p.get("text"):
            continue
        k = (" gl-" + p["kind"]) if p.get("kind") else ""
        lab = (f'<span class="gll">{e(p["label"])}</span>'
               if p.get("label") else "")
        out.append(f'<span class="gl{k}" title="{e(p.get("title", ""))}">'
                   f'{lab}{ico(p["icon"])}<span>{p["text"] if p.get("html") else e(p["text"])}'
                   "</span></span>")
    return (f'<p class="{cls} glance">' + "".join(out) + "</p>") if out else ""


def taskrow(t, src="workstreams.md", ws="", show_ws=False, ws_label="",
            lead=""):
    """One task: the tick, then ✦ (hand it to Claude) and ⋯ (dates,
    rewording, dropping). What follows a tick is typed on the line that
    opens under it (page.js, serve.py task_follow)."""
    key = MD.taskkey(MD.bare(t["text"]))
    cls = " ".join(filter(None, [
        "done" if t["done"] else "",
        "parked" if t.get("parked") else "",
        "dropped" if t.get("dropped") else ""]))
    note = ""
    if t.get("dropped"):
        note = f'<span class="tnote">dropped</span>'
    elif t.get("parked"):
        d = t.get("until_days")
        when = "tomorrow" if d == 1 else f"in {d} days" if d and d < 32 else ""
        note = (f'<span class="tnote">waiting until {e(dayfirst(t["until"]))}'
                + (f" &middot; {when}" if when else "") + "</span>")
    elif t.get("due") and not t["done"]:
        dd = t.get("due_days")
        lab = dayfirst(t.get("due_label") or t.get("due"))   # "30 Oct", not ISO
        if dd is not None and dd < 0:
            when = f"{abs(dd)}d overdue"
            cls += " tdue-bad"
        elif dd == 0:
            when = "due today"; cls += " tdue-soon"
        elif t.get("due_fuzzy"):
            # a window, not a day: show it as words/range ("due this week")
            when = f"due {lab}"
            if dd is not None and dd <= 7:
                cls += " tdue-soon"
        elif dd is not None and dd <= 7:
            when = f"due in {dd}d"; cls += " tdue-soon"
        else:
            when = f"due {lab}"
        note = f'<span class="tnote tdue">{when}</span>'
    # How long she said it takes, wherever the task appears. "Off your plate in
    # minutes" was listing six things with no durations at all, so the heading
    # was asking to be trusted rather than showing its working — and half of
    # them read long while actually being fifteen-minute jobs.
    est = ""
    if t.get("est") and not t["done"]:
        est = f'<span class="test">{e(M.fmt_dur(t["est"]))}</span>'
    # Which project this belongs to, wherever the task has been lifted out of
    # its workstream. On the plate the heading above already says it; in "Off
    # your plate in minutes" five tasks from five projects looked like one
    # undifferentiated list, and "ask for the cellar breakdown" means nothing
    # without knowing whose cellar.
    wschip = ""
    if show_ws and ws:
        wschip = (f'<button class="tws"{LN.ws_attr(ws)} data-wsopen="{e(ws)}" title="Open the'
                  f' project: {e(ws)}">' + e(ws_label or ws) + "</button>")
    ctx = taskctx(t)
    # ✦ and ⋯ come from md.py, the one copy the plan rows use too.
    buttons = MD.row_buttons(
        t["text"], key, src, ws,
        open_=not t["done"] and not t.get("parked") and not t.get("dropped"))
    return (f'<li class="{cls}">'
            f'<button class="box tick" aria-pressed="{"true" if t["done"] else "false"}"'
            f' data-src="{src}" data-key="{key}" title="Tick it off">'
            f'{"&#10003;" if t["done"] else ""}</button>'
            f'<span class="ttext">{lead}{iso_prose(linknames(e(t["text"])))}{est}{note}{ctx}'
            f'{reading_line(t)}</span>'
            f"{wschip}{buttons}"
            "</li>")


def taskctx(t):
    """The task's own notes — the indented lines under it in the file — as
    one faint line that opens to the rest on a tap. A task lifted onto Today
    or School arrives without the conversation it was filed in; this line is
    what says which method, whose token, why now. Open tasks only: a done
    task's notes are history, and the workstream page still has them."""
    # A reading's "File:" note is for the brain; the row shows its
    # speed-read button instead (reading_line).
    notes = [n for n in t.get("notes") or [] if not _file_note(n)]
    if not notes or t.get("done"):
        return ""
    rest = "".join(f"<p>{iso_prose(MD.inline(n))}</p>" for n in notes[1:])
    return (f'<details class="tctx"><summary>{iso_prose(MD.inline(notes[0]))}'
            f"</summary>{rest}</details>")


_FILE_NOTE_RX = re.compile(r"^(?:file|pdf)\s*:\s*\S", re.I)


def _file_note(n):
    return bool(_FILE_NOTE_RX.match(n or ""))


_READINGS = {}


def reading_line(t):
    """A class reading's speed-read button, and what the fast read skips.

    Only for an open "Read …" task whose PDF is in her class folder
    (reading.py finds it). The warning is the point: the fast read takes the
    running text, so an appendix, a table or a chart the argument rests on
    is named, with its page, before she starts. Tapping it opens the PDF."""
    if t.get("done") or t.get("dropped") or t.get("parked") \
            or not re.match(r"(?i)read(ing)?\b", t.get("text") or ""):
        return ""
    key = t.get("text")
    if key not in _READINGS:
        try:
            import reading as RD
            f = RD.file_for(t)
            _READINGS[key] = RD.summary(f) if f else None
        except Exception:                                # noqa: BLE001
            _READINGS[key] = None
    s = _READINGS[key]
    if not s or not s.get("words"):
        return ""
    title = re.sub(r"(?i)^read(ing)?\s+", "", _task_head_plain(t["text"]))
    title = title[:1].upper() + title[1:]
    go = ('<button class="rdgo" data-reading="%s" data-title="%s"'
          ' data-warn="%s" data-kind="%s"'
          ' title="Speed-read it, one word at a time">%s'
          "<span>Speed-read &middot; ~%d min</span></button>"
          % (e(s["rel"]), e(title[:90]), e(s.get("warn", "")),
             e(s.get("kind", "")), ico("play"), s["minutes"]))
    chip = ""
    if s.get("chip"):
        chip = ('<button class="rdwarn%s" data-readopen="%s" title="%s">%s'
                "<span>%s</span></button>"
                % ("" if s.get("kind") == "warn" else " rdsoft", e(s["rel"]),
                   e(s["warn"] + " Opens the PDF."),
                   ico("alert" if s.get("kind") == "warn" else "image"),
                   e(s["chip"])))
    return '<span class="rdline needs-server">%s%s</span>' % (go, chip)


_TWINS = None


def plan_reading(bare_text):
    """reading_line for a plan row: today.md quotes the task without its
    notes, so the File: note is borrowed from the workstream's own copy."""
    global _TWINS
    if not re.match(r"(?i)read(ing)?\b", bare_text or ""):
        return ""
    if _TWINS is None:
        _TWINS = {}
        for w in M.load():
            for t in w.get("tasks") or []:
                if not t.get("done"):
                    _TWINS.setdefault(MD.bare(t["text"]), t)
    return reading_line(_TWINS.get(bare_text) or {"text": bare_text})


def _task_head_plain(text):
    t = re.sub(r"\s*\((?:class|urgent|due [^)]*|waiting until [^)]*)\)", "",
               text or "")
    t = re.sub(r"\s+~\d+\s*[hm]\w*\b", "", t)
    return re.split(r"\s+[—–]\s+", t)[0].strip()


def _task_order(t):
    """Open work first, the most pressing at the top (her ask, 8 Oct: the
    urgent item first); then waiting, dropped, and done at the bottom. Ties
    keep the file's order, which is often a sequence ("first step")."""
    if t["done"]:
        return (3, 0)
    if t.get("dropped"):
        return (2, 0)
    if t.get("parked"):
        return (1, 0)
    return (0, -(t.get("pressure") or 0))


def tasklist(w):
    # A slipped finish line leads the list: it is the late thing here, and
    # it lives in goals.md rather than among the tasks.
    goal = ""
    if w.get("goal_overdue") and w.get("goal_text"):
        g = {"text": w["goal_text"], "done": False,
             "due": w.get("goal_label") or "late",
             "due_label": w.get("goal_label") or "",
             "due_days": w.get("goal_days")}
        goal = taskrow(g, src="goals.md", ws=w["name"],
                       lead='<span class="tgoal">Finish line</span>')
    if not w["tasks"] and not goal:
        return ""
    return ('<ul class="tasks">' + goal
            + "".join(taskrow(t, ws=w["name"])
                      for t in sorted(w["tasks"], key=_task_order))
            + "</ul>")


def sevclass(w):
    if w["overdue"] or w.get("task_overdue") or w.get("task_urgent") \
            or w.get("urgent_name"):
        return "sev-bad"
    if w["chase"]:
        return "sev-wait"
    if w["cold"] or w["never_touched"]:
        return "sev-cold"
    if w["due_soon"] or w.get("task_due_soon"):
        return "sev-soon"
    return "sev-none"


def plate_sev(w, grace=7, red=None):
    """The Plate's card colour, stricter than sevclass (28 Sep review: eight
    of ten Needs-you cards wore the alarm fill, so it warned of nothing).
    Alarm only when a date SHE set has passed: the workstream's own due
    date, a finish line, or a task's due date more than a week gone.
    "Marked urgent", "untouched" and a task a few days over are not late
    in that sense; a date within a week either side is "soon". Expired
    tasks (the moment itself passed) count for nothing here — the ranking
    card offers to retire them."""
    live_ts = [t for t in w.get("tasks") or []
               if not t["done"] and not t.get("parked") and not t.get("dropped")
               and not t.get("expired")]
    if (w["overdue"] or w.get("goal_overdue")
            or any((t.get("due_days") or 0) < -grace for t in live_ts)):
        # Only the day's red few keep the alarm fill (model.red_names); the
        # rest say they are late in their reason line alone (8 Oct).
        return "sev-bad" if red is None or w["name"] in red else "sev-late"
    if w["chase"]:
        return "sev-wait"
    if w["cold"] or w["never_touched"]:
        return "sev-cold"
    if (w["due_soon"] or w.get("task_due_soon")
            or any(t.get("due_days") is not None and t["due_days"] < 0
                   for t in live_ts)):
        return "sev-soon"
    return "sev-none"


def ordinal(n):
    """1st, 2nd, 3rd, 4th … 11th, 12th, 13th, 21st."""
    if 10 <= n % 100 <= 20:
        return f"{n}th"
    return str(n) + {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")


_DM_RX = re.compile(r"^(\d{4}-\d{2}-\d{2})"
                    r"(?:\s*(?:\.\.|–|—|to)\s*(\d{4}-\d{2}-\d{2}))?$")


def dayfirst(s, today=None):
    """A date for her eyes: "28 Sep", "5–8 Oct", "21 Sep – 1 Oct", with the
    year only when it is not this one. Anything that is not an ISO date or
    an ISO range comes back as it was, so a fuzzy due ("end of October")
    still reads."""
    s = (s or "").strip()
    m = _DM_RX.match(s)
    if not m:
        return s
    try:
        a = date.fromisoformat(m.group(1))
        b = date.fromisoformat(m.group(2)) if m.group(2) else a
    except ValueError:
        return s
    yr = (today or date.today()).year

    def one(d, year=True):
        return (f"{d.day} {d.strftime('%b')}"
                + (f" {d.year}" if year and d.year != yr else ""))
    if a == b:
        return one(a)
    if (a.year, a.month) == (b.year, b.month):
        return f"{a.day}–{one(b)}"
    return f"{one(a, a.year != b.year)} – {one(b)}"


# A date standing on its own in saved prose: not glued to a letter, digit,
# slash, dash, underscore or dot, so "2026-09-10-lease-reply.md" and
# "transcripts/2026-09-28-…" stay file names. A full stop after it ends the
# sentence unless a letter follows (".md").
_ISO_ANY = re.compile(r"\d{4}-\d{2}-\d{2}")
_ISO_PROSE = re.compile(r"(?<![\w/.\-=#])\d{4}-\d{2}-\d{2}"
                        r"(?:(?:\.\.|\s?[–—]\s?)\d{4}-\d{2}-\d{2})?"
                        r"(?![\w/\-]|\.[\w.])")
# Code, a link, a text box or a draft she edits: a date there is part of
# what the element holds, so it stays as written.
_ISO_KEEP = {"a", "code", "pre", "textarea", "script", "style", "time"}


def _iso_span(m):
    shown = dayfirst(m.group(0))
    if shown == m.group(0):
        return shown                    # not a real date (2026-13-40)
    return f'<span data-iso="{m.group(0)}">{shown}</span>'


def iso_prose(html_s):
    """Saved prose with its ISO dates said her way, on rendered HTML: "Touched
    date updated to 2026-09-27" reads "… to 27 Sep" (her yes, 28 Sep). Only
    the words between tags change; tags and attributes never do, so a tick's
    hash, an id or a data- value keeps the raw text. Each date keeps its ISO
    in data-iso, which the task menu puts back when she rewords a task, so
    the file never learns the display form."""
    if not html_s or not _ISO_ANY.search(html_s):
        return html_s
    parts = re.split(r"(<[^>]+>)", html_s)
    keep, depth = None, 0
    for i, seg in enumerate(parts):
        if not seg:
            continue
        if seg[0] == "<":
            m = re.match(r"<(/?)([A-Za-z][\w-]*)", seg)
            if not m:
                continue
            tag, shut = m.group(2).lower(), bool(m.group(1))
            if keep:
                if tag == keep and not seg.endswith("/>"):
                    depth += -1 if shut else 1
                    if depth == 0:
                        keep = None
            elif not shut and not seg.endswith("/>") and (
                    tag in _ISO_KEEP or "contenteditable" in seg):
                keep, depth = tag, 1
            continue
        if keep is None:
            parts[i] = _ISO_PROSE.sub(_iso_span, seg)
    return "".join(parts)



def hint(text):
    """A small ? that opens the explanation on tap. The explanation still
    exists; it just stops occupying the page while you already know it."""
    return ('<span class="hintwrap"><button class="hint" aria-expanded="false"'
            ' aria-label="What is this?">?</button>'
            f'<span class="tip" role="note" hidden>{text}</span></span>')


def _mon_day(d):
    """"17 Oct" without strftime's %-d, which Windows spells %#d. Day first,
    her way of writing a date (page review, 28 Sep)."""
    return str(d.day) + " " + d.strftime("%b")


def _day_range(d1, d2):
    """"3–4 Oct" inside one month, "22 Sep – 24 Jan" across two."""
    if d2 == d1:
        return _mon_day(d1)
    if (d1.year, d1.month) == (d2.year, d2.month):
        return f"{d1.day}&ndash;{_mon_day(d2)}"
    return f"{_mon_day(d1)} &ndash; {_mon_day(d2)}"


def _seasonchip(i):
    """A bucket item as a draggable chip — on a day of the grid or in the
    idea tray. Click opens the exact-date box (also the touch path, since
    touch has no drag-and-drop)."""
    key = MD.taskkey(MD.bare(i["text"]))
    planned = i["planned"]["start"].isoformat() if i["planned"] else ""
    pend = (i["planned"]["end"].isoformat()
            if i["planned"] and i["planned"]["end"] != i["planned"]["start"]
            else "")
    span = ""
    if pend:
        span = f'<span class="szspan">&rarr; {_mon_day(i["planned"]["end"])}</span>'
    who = (f'<span class="szwho">{e(", ".join(i["with"]))}</span>'
           if i["with"] else "")
    rep = ""
    if i["repeat"]:
        n = len(i["did"])
        rep = ('<span class="szrep">' + e(i["repeat"])
               + (f" &middot; {n}&times;" if n else "") + "</span>")
    # Its last day, once it is near (9 Oct): an exhibition closing in nine
    # days is the reason to pick it this weekend.
    ends = ""
    if i.get("ends") and not i["planned"]:
        left = (i["ends"] - date.today()).days
        if left < 0:
            ends = f'<span class="szends gone">ended {_mon_day(i["ends"])}</span>'
        elif left <= 21:
            ends = ('<span class="szends">'
                    + ("ends today" if left == 0 else "ends tomorrow" if left == 1
                       else f"ends in {left} days") + "</span>")
    # title=: the tray clips a chip to one line, so the full wording of a long
    # idea has to be reachable without opening anything.
    return (f'<button class="szchip needs-server" draggable="true"'
            f' data-key="{key}" data-planned="{planned}" data-pend="{pend}"'
            f' data-title="{e(i["text"])}" title="{e(i["text"])}">'
            f'{e(clip(i["text"], 72))}{who}{span}{rep}{ends}</button>')


def _seasonrow(i):
    """A bucket item in the list below the grid: tickable, with its people
    and its day where the eye already is."""
    key = MD.taskkey(MD.bare(i["text"]))
    notes = []
    if i["with"]:
        notes.append('<span class="szwho">'
                     + e("with " + ", ".join(i["with"])) + "</span>")
    # A day that has passed with the item still open is a question, not a
    # plan: ask it beside the tick, and offer the way back to the tray.
    # Done stays hers — nothing here ticks anything (page review SE2).
    if i["planned"]:
        lab = _day_range(i["planned"]["start"], i["planned"]["end"])
        if not i["done"] and i["planned"]["end"] < date.today():
            notes.append(f'<span class="tnote szask">{lab}: did it'
                         ' happen? <button class="szunslot needs-server"'
                         f' data-szunslot="{key}" title="Takes it off that'
                         ' day and back to the ideas without a day. The tick'
                         ' says it did.">It didn&rsquo;t</button></span>')
        else:
            notes.append(f'<span class="tnote">{lab}</span>')
    elif i["when_label"] and not i["done"]:
        notes.append(f'<span class="tnote">sometime {e(i["when_label"])}</span>')
    if i["repeat"]:
        n = len(i["did"])
        notes.append('<span class="szrep">' + e(i["repeat"])
                     + (f" &middot; {n}&times; so far" if n else "") + "</span>")
    est = (f'<span class="test">{e(M.fmt_dur(i["est"]))}</span>'
           if i.get("est") and not i["done"] else "")
    tick_tip = ("It happened. Logs the date and keeps it for next time"
                if i["repeat"] else "It happened")
    return (f'<li class="{"done" if i["done"] else ""}">'
            f'<button class="box tick" aria-pressed="{"true" if i["done"] else "false"}"'
            f' data-src="season.md" data-key="{key}" title="{tick_tip}">'
            f'{"&#10003;" if i["done"] else ""}</button>'
            f'<span class="ttext">{iso_prose(linknames(e(i["text"])))}{est}{"".join(notes)}</span>'
            f'<button class="tmenu needs-server" data-task="{key}" data-src="season.md"'
            ' title="More for this idea"'
            ' aria-label="More ways to close this">&#8943;</button>'
            "</li>")


_EVLINE = re.compile(
    r"^- (?:(\d{4}-\d{2}-\d{2})(?:\.\.(\d{4}-\d{2}-\d{2}))?\s+[—–-]+\s+)?(.+)$")
_EVURL = re.compile(r"https?://[^\s)\]<>]+")
_MONTHNAMES = ("January February March April May June July August September "
               "October November December").split()


def _events(today):
    """The scouted going-out list in brain/events.md, rewritten weekly by
    /scout, as (meta, groups). Each group is {"label", "items"}; each item
    a dict of d1, d2, text, url, unc (unconfirmed) and pick. Past items drop
    out here, so a missed scout week shrinks the list instead of letting it
    lie.

    A pick is a line the scout starred, ★ before the title: the few best
    fits for her taste. They lead the Season tab's list and fill Life's
    overview card (8 Oct, her ask: "highlight the events that might be
    most interesting")."""
    path = os.path.join(BRAIN, "events.md")
    try:
        with open(path, encoding="utf-8") as f:
            raw = f.read()
    except OSError:
        return {}, []
    meta, groups, cur = {}, [], None
    lines = raw.splitlines()
    if lines and lines[0].strip() == "---":
        for n, ln in enumerate(lines[1:], 1):
            if ln.strip() == "---":
                lines = lines[n + 1:]
                break
            k, _, v = ln.partition(":")
            meta[k.strip()] = v.strip()
    for ln in lines:
        ln = ln.rstrip()
        if ln.startswith("## "):
            cur = {"label": ln[3:].strip(), "items": []}
            groups.append(cur)
            continue
        # The star goes after the date; a scout that puts it first still
        # gets its date read.
        pick = ln.startswith("- ★")
        if pick:
            ln = "- " + ln[3:].lstrip()
        m = _EVLINE.match(ln)
        if not m or cur is None:
            continue
        d1 = d2 = None
        try:
            if m.group(1):
                d1 = date.fromisoformat(m.group(1))
                d2 = date.fromisoformat(m.group(2)) if m.group(2) else d1
        except ValueError:
            pass
        if d2 and d2 < today:
            continue        # it happened; the list only looks forward
        text = m.group(3).strip()
        if text.startswith("★"):
            pick, text = True, text.lstrip("★").strip()
        url = ""
        um = _EVURL.search(text)
        if um:
            url = um.group(0).rstrip(".,;")
            text = _EVURL.sub("", text)
        unconfirmed = bool(re.search(r"\(?unconfirmed\)?", text, re.I))
        text = re.sub(r"\(?unconfirmed\)?", "", text, flags=re.I)
        # Lifting the URL and the unconfirmed tag out of the middle of a line
        # leaves its separators behind, so strip every trailing one, not one.
        text = re.sub(r"(?:\s*[—–]+)+\s*$", "", text.strip()).strip()
        if text:
            cur["items"].append({"d1": d1, "d2": d2, "text": text, "url": url,
                                 "unc": unconfirmed, "pick": pick})
    return meta, [g for g in groups if g["items"]]


def _ev_lab(d1, d2):
    if not d1:
        return ""
    if d2 != d1:
        return _day_range(d1, d2)
    return d1.strftime("%a") + " " + _mon_day(d1)


def _ev_title(text):
    """The event's name without its price: what the season holds."""
    return clip(re.sub(r"\s*[—–]\s*(?:€|from €|free\b|included\b).*$", "",
                       text, flags=re.I).strip(), 150)


def _ev_add(it):
    """What "+ Season" writes into season.md. A one-day event lands already
    slotted; a run of dates (an exhibition open for four months) lands in
    the tray with its month, because pinning a Monet show to its opening
    day would be a guess she then has to undo."""
    t = _ev_title(it["text"])
    if not it["d1"]:
        return t
    if it["d2"] != it["d1"]:
        # Its closing day rides along (9 Oct), so the tray can count down to
        # it and stop holding a show that has closed.
        return (f"{t} (when: {_MONTHNAMES[it['d1'].month - 1]})"
                + (f" (ends: {it['d2'].isoformat()})" if it["d2"] else ""))
    return f"{t} (planned: {it['d1'].isoformat()})"


def _season_titles(today):
    """The season's live ideas, lowercased, so an event already added says
    so instead of offering itself again after the page reloads."""
    try:
        s = M.load_season(today=today) or {}
    except Exception:
        return set()
    return {re.sub(r"\s+", " ", i["text"]).strip().lower()
            for i in (s.get("items") or []) if not i.get("dropped")}


def _ev_addbtn(it, in_season):
    """The one way to put an event in the season, worded on its face: a
    bare ＋ next to Book read as decoration (8 Oct, her review). No date,
    no button: the "Watching for" lines are announcements to catch ("that
    show is sold out"), not things she can put on a day."""
    if not it["d1"]:
        return ""
    if re.sub(r"\s+", " ", _ev_title(it["text"])).strip().lower() in in_season:
        return ('<span class="szouta szadded" title="Already in your season">'
                '&#10003; In season</span>')
    tip = ("Put it in your season on its day" if it["d2"] == it["d1"] else
           "Put it in your season&rsquo;s ideas for "
           + _MONTHNAMES[it["d1"].month - 1])
    return (f'<button class="szouta needs-server" data-add="{e(_ev_add(it))}"'
            f' title="{tip}">&#43; Season</button>')


def _eventsview(today):
    """The "Out there" block on the Season tab: the scouted going-out
    shortlist (`_events`). Returns (html, count): the count feeds the chip
    at the top of the tab, because this block sits below a full-height
    planner and was invisible without one.

    Each row carries the two things a listing is for: the booking link, and
    "+ Season", which writes the item to season.md already slotted on its
    date. Slotting stays HER action: a button she presses, never something
    a run decides. The scout's picks come first, in a group of their own."""
    meta, groups = _events(today)
    if not groups:
        return "", 0
    where = meta.get("where", "")
    in_season = _season_titles(today)

    def _search(text):
        """Everything the listing doesn't answer — is it any good, who else
        is playing, what the room is like. Always present, including on the
        lines that have no ticket page at all."""
        q = re.sub(r"\s*[—–]\s*(?:€|from €|free\b).*$", "", text, flags=re.I)
        q = re.sub(r"\([^)]*\)", "", q).strip()
        return ("https://duckduckgo.com/?q="
                + urllib.parse.quote_plus(f"{q} {where}".strip()))

    def _row(it):
        url = MD.safe_href(it["url"])     # scouted from the web: links only
        book = (f'<a class="szoutb" href="{e(url)}" target="_blank"'
                ' rel="noopener noreferrer">Book &#8599;</a>' if url else "")
        # The title is the link too. On a wide screen the button at the
        # far right is a metre away from the words being read, which is
        # how a row full of links reads as a row with none.
        t = e(it["text"])
        title = (f'<a class="szoutt" href="{e(url)}" target="_blank"'
                 f' rel="noopener noreferrer">{t}</a>' if url
                 else f'<span class="szoutt">{t}</span>')
        lab = _ev_lab(it["d1"], it["d2"])
        return ('<li' + (' class="szpick"' if it["pick"] else "") + '>'
                + (f'<span class="szoutd">{lab}</span>' if lab else "")
                + title
                + ('<span class="szunc" title="Not verified on an official '
                   'page, so check before you count on it">unconfirmed</span>'
                   if it["unc"] else "")
                + f'<a class="szouti" href="{e(_search(it["text"]))}"'
                ' target="_blank" rel="noopener noreferrer" title="Search the'
                ' web for reviews and the lineup">info'
                ' &#8599;</a>' + book + _ev_addbtn(it, in_season) + "</li>")

    # By the day she could first go, and among those already on, the one
    # closing soonest: a fair ending Sunday before a show open till January.
    picks = sorted((it for g in groups for it in g["items"] if it["pick"]),
                   key=lambda it: (max(it["d1"] or today, today),
                                   it["d2"] or today))
    rows, n = [], 0
    if picks:
        rows.append('<p class="szglabel szpicks">&#9733; Top picks</p>'
                    '<ul class="szout">' + "".join(_row(it) for it in picks)
                    + "</ul>")
    for g in groups:
        rest = [it for it in g["items"] if not it["pick"]]
        # the undated "Watching for" notes are announcements, not things
        # she can go to: they don't count
        n += sum(1 for it in g["items"] if it["d1"])
        if rest:
            rows.append(f'<p class="szglabel">{e(g["label"])}</p>'
                        '<ul class="szout">' + "".join(_row(it) for it in rest)
                        + "</ul>")
    scouted = meta.get("updated", "")
    stale = ""
    try:
        sd = date.fromisoformat(scouted)
        scouted = _mon_day(sd)
        if (date.today() - sd).days > 7:
            # "runs weekly" under a two-week-old list is the page lying.
            # The night log knows why it didn't; say that instead. Its own
            # names: this used to reuse `n`, so the count of dated events
            # returned below became the count of skipped nights — the
            # "7 things on" the Season tab showed over 23 (28 Sep).
            import night_config
            skipped, why = night_config.skipped_streak()
            stale = (f"the night shift skipped {skipped} nights: {why}"
                     if skipped > 1 else "the weekly look is overdue")
    except (ValueError, ImportError):
        pass
    # On the face, what she needs: when the list was found. Where, and why a
    # list is old, are the machinery — they ride in the tooltip.
    tip = " · ".join(x for x in (
        where, stale or "Looked for again each week") if x)
    note = (f"Events found {scouted}" if scouted else "Not looked for yet")
    return ('<h3 class="szh" id="szout">Out there'
            + f' <span class="szhint" title="{e(tip)}">{note}</span>'
            + '<button class="mini needs-server" data-job="scout"'
            ' title="Search the web now for what is on where you are. Nothing'
            ' is ever booked.">Scout now</button>'
            + "</h3>" + "".join(rows)), n


def seasonview(cfg, today):
    """The Season tab: the bucket list for this stretch of life, and the two
    months it has to land in. Ideas without a day sit in the tray; dragging
    one onto a day writes its (planned: …) in brain/season.md. Nothing here
    decays — the number of weekends left is the only pressure."""
    s = M.load_season(today=today)
    if not s:
        return ('<section class="season"><p class="eyebrow">Season</p>'
                '<span class="wav"></span>'
                + AG.say('<div class="empty">No season yet. Tell Claude the stretch of '
                         'life you are in and when it ends, like &ldquo;my last term, '
                         'until December 11&rdquo;. Its bucket list will '
                         'live here.</div></section>'))
    items = [i for i in s["items"] if not i["dropped"]]
    done = [i for i in items if i["done"]]
    opens = [i for i in items if not i["done"]]
    slotted = [i for i in opens if i["planned"]]
    tray = [i for i in opens if not i["planned"]]

    stats = []
    if s["end"]:
        wl = s["weekends_left"]
        stats.append(f'<span class="szstat"><b>{wl}</b> weekend'
                     f'{"s" if wl != 1 else ""} left</span>')
        # "season ends": the School tab's "term ends" is config's date for
        # the term; this one is season.md's, and they need not agree.
        stats.append(f'<span class="szstat">season ends {_mon_day(s["end"])}'
                     "</span>")
    # No "happened · to go" tally: a count turns the bucket into a list of
    # things to collect. The weekends left stay — an ending in sight is what
    # makes people savour a stretch (research page, 28 Sep).
    # The events block lives below a full-height planner, so from up here it
    # may as well not exist. This is its doorbell.
    evhtml, evn = _eventsview(today)
    if evn:
        stats.append(f'<button class="mini" id="szgo"><b>{evn}</b> things on'
                     ' &darr;</button>')
    stats.append(AG.say('<button class="mini needs-server" id="szplan"'
                        ' title="Claude proposes a day for every idea in the tray,'
                        ' and you drag the ones you agree with">Plan my month</button>'))
    stats.append('<button class="mini needs-server" id="szsub"'
                 ' title="Subscribe your calendar app to the season: slotted'
                 ' ideas appear as all-day events and move when you drag'
                 ' them">Show in my calendar</button>')
    stats.append(hint(
        "Slotted items double as a calendar feed: subscribe to "
        "<code>http://&lt;this machine&gt;:7718/season.ics</code> from any "
        "calendar app and they appear as all-day events, moving when you "
        "drag them."))

    # Which days already hold real life, so a free Saturday looks free and a
    # booked one doesn't lie. The horizon reaches the season's end (stepped
    # to 30-day marks so the cache key holds still for weeks), and it keeps
    # times and titles — the views show the day's real shape, not a dot.
    busy, calnote, calok = {}, "", False
    hz = 62
    if s["end"] and s["end"] > today:
        hz = min(180, max(62, (((s["end"] - today).days + 14 + 29) // 30) * 30))
    def _dedupe(evs):
        """The school feed lists most classes twice — a short spelling and a
        long one with lecturer and room. Same time + one title a prefix of
        the other = one event; keep the detailed spelling."""
        out = []
        for hhmm, t in evs:
            t = html.unescape(t).strip()
            for o in out:
                if o[0] == hhmm and (o[1].lower().startswith(t.lower())
                                     or t.lower().startswith(o[1].lower())):
                    if len(t) > len(o[1]):
                        o[1] = t
                    break
            else:
                out.append([hhmm, t])
        return out

    if cfg.get("calendar"):
        try:
            import calendar_read
            for when, t in calendar_read.events(hz):
                if re.match(r"\s*canceled", t, re.I):
                    continue          # a cancelled slot is a FREE slot
                d8, _, hhmm = when.partition(" ")
                busy.setdefault(d8, []).append([hhmm[:5], t])
            busy = {k: _dedupe(v) for k, v in busy.items()}
            st = calendar_read.status(hz)
            calok = st == "ok"
            if not busy and st != "ok":
                # An unshaded month after a failed or unfinished read must
                # not pass for a free month.
                # This warning is load-bearing: an unshaded grid without it
                # reads as a free month. It goes ABOVE the grid, styled as a
                # warning — as a grey caption underneath it was mistaken for
                # a footnote, which is the one way it could fail.
                calnote = ('<p class="sznote">Your calendar is being read in '
                           'the background. The busy shading joins '
                           'the grid on the next rebuild.</p>'
                           if st == "warming" else
                           AG.say('<p class="sznote warn">Your calendar could not be '
                                  'read, so the days below show no busy shading '
                                  'even where you have plans. Tell Claude if it '
                                  'persists.</p>'))
        except Exception:
            busy, calok = {}, False

    # The recurring week shades the season too: a fixed-evening routine
    # (volleyball) books its days as surely as any calendar event does.
    try:
        import routines as RT
        rblocks = []
        for r in RT.load():
            m = RT._CLOCK.search(r["time"] or "")
            rota_days = [dw for dw in RT.DAYS
                         if any(v for v in (r["rota"].get(dw) or []))]
            if m and rota_days:
                rblocks.append((rota_days,
                                f"{int(m.group(1)):02d}:{m.group(2)}",
                                r["name"]))
        for i in range(hz if rblocks else 0):
            d = today + timedelta(days=i)
            dw = RT.DAYS[d.weekday()]
            for rota_days, hhmm, name in rblocks:
                if dw in rota_days:
                    busy.setdefault(d.isoformat(), []).append([hhmm, name])
        for k in busy:
            busy[k].sort()
    except Exception:
        pass

    # The planner renders client-side from this payload: three views (week,
    # month, two months) over the same data, navigable to the season's end
    # without a rebuild.
    payload = {
        "today": today.isoformat(),
        "start": s["start"].isoformat() if s["start"] else "",
        "end": s["end"].isoformat() if s["end"] else "",
        # Whether the calendar was actually read. Without it the weekends view
        # would stamp "free" on every card precisely when it knows least —
        # the same lie the note above the grid exists to prevent.
        "calok": calok,
        "events": busy,
        "chips": [{
            "key": MD.taskkey(MD.bare(i["text"])),
            "title": i["text"],
            "label": clip(i["text"], 44),
            "planned": i["planned"]["start"].isoformat(),
            "pend": (i["planned"]["end"].isoformat()
                     if i["planned"]["end"] != i["planned"]["start"] else ""),
            "with": "" if PRESENTING else ", ".join(i["with"]),
            "repeat": i["repeat"],
            "times": len(i["did"]),
        } for i in slotted],
    }
    pjson = MD.json_for_script(payload, ensure_ascii=False)
    months = (
        calnote
        + '<div class="szbar">'
        '<div class="sznav">'
        '<button class="mini" id="szprev" aria-label="Earlier">&lsaquo;</button>'
        '<b id="szlabel"></b>'
        '<button class="mini" id="sznext" aria-label="Later">&rsaquo;</button>'
        '</div>'
        # The key to the shading sits beside the switch that changes the
        # view it explains — under the grid it read as a stray footnote.
        # Swatches, not "darker": on a dark style the fuller day is the
        # lighter cell, and the words read backwards there (8 Oct).
        + ('<span class="szhint szkey" title="One or two things that day:'
           ' busy. Three or more: full. Your calendar and what you slotted'
           ' here both count. A green edge: nothing on yet."><i class="szsw szfreesw">'
           '</i>free &middot; <i class="szsw szbz1"></i>busy &middot; '
           '<i class="szsw szbz2"></i>full</span>'
           if busy else "")
        + '<div class="szviews" role="tablist">'
        '<button class="szvbtn" data-v="we">Weekends</button>'
        '<button class="szvbtn" data-v="w">Week</button>'
        '<button class="szvbtn" data-v="m">Month</button>'
        '<button class="szvbtn" data-v="mm">2 months</button>'
        '</div></div>'
        '<div id="szplanner"></div>'
        + f'<script type="application/json" id="szdata">{pjson}</script>')

    # The tray groups by the (when:) intention — twenty loose chips are a
    # wall; "September / October / whenever" is a plan taking shape.
    # Items with no month fall back to (fits:), which answers the question
    # actually being asked of the tray: a free Saturday is here, what can
    # land on it? "An afternoon in Paris" and "a day out of Paris" are
    # different answers; sorting them by topic would not be.
    buckets, seen = [], {}
    # A window that has closed gets its own group at the end (9 Oct): the
    # chip opens the box where "Not this season" lets it go, or a new day
    # keeps it. It used to sit under its month forever.
    gone = [i for i in tray if i.get("ends") and i["ends"] < today]
    for i in tray:
        if i in gone:
            continue
        lab = (i["when_label"] or "").strip()
        fits = "" if lab else (i["fits"] or "").strip()
        k = (lab or fits).lower()
        if k not in seen:
            pd = M.parse_due(lab, today) if lab else None
            seen[k] = {"label": lab or fits, "end": pd["end"] if pd else None,
                       "dated": bool(lab), "items": []}
            buckets.append(seen[k])
        seen[k]["items"].append(i)
    # Months first in date order, then the fits groups alphabetically, then
    # the untagged remainder last — it is the pile that still needs a think.
    buckets.sort(key=lambda b: (not b["dated"], b["end"] or date.max,
                                not b["label"], b["label"].lower()))
    if gone:
        buckets.append({"label": "Missed it?", "end": None, "dated": False,
                        "items": gone, "gone": True})
    rows = []
    for b in buckets:
        lab = e(b["label"]) if b["label"] else "whenever"
        if len(buckets) == 1 and not b["label"]:
            lab = ""
        rows.append('<div class="szgroup">'
                    + (f'<span class="szglabel">{lab}</span>' if lab else "")
                    + "".join(_seasonchip(i) for i in b["items"]) + "</div>")

    trayhtml = ('<div class="sztray" data-day="">'
                '<div class="sztrayhead">'
                '<p class="eyebrow">Ideas without a day'
                + (f' &middot; {len(tray)}' if tray else "") + '</p>'
                '<span class="szhint">drag onto a day &middot; click for more</span>'
                '</div>'
                + ("".join(rows) if tray else
                   '<p class="meta">Every idea has a day. Add another below.</p>')
                + '<div class="szadd needs-server">'
                '<input id="szaddin" type="text" maxlength="300"'
                ' placeholder="Something this season should hold&hellip;">'
                '<button class="mini" id="szaddbtn">Add</button></div>'
                "</div>")

    # Only the things that have a day. The tray above already shows every
    # idea that doesn't, and listing all of them twice — chip and row, same
    # words, same order — was most of this page's length.
    bucket = ""
    if slotted:
        # In date order, so the passed ones asking "did it happen?" sit
        # together at the top instead of wherever the file put them.
        bucket = ('<h3 class="szh">Has a day</h3><ul class="tasks">'
                  + "".join(_seasonrow(i) for i in sorted(
                      slotted, key=lambda i: i["planned"]["start"]))
                  + "</ul>")
    donehtml = ""
    if done:
        donehtml = ('<h3 class="szh">Happened</h3><ul class="tasks szdone">'
                    + "".join(_seasonrow(i) for i in done) + "</ul>")

    return ('<section class="season"><p class="eyebrow">Season</p>'
            '<span class="wav"></span>'
            f'<h2 class="szname">{e(s["name"])}</h2>'
            + (f'<p class="coach">{e(s["why"])}</p>' if s["why"] else "")
            + f'<div class="szstats">{"".join(stats)}</div>'
            + months + trayhtml + bucket + donehtml
            + evhtml + "</section>")


def season_ics(today=None):
    """brain/season.ics — the slotted season items as all-day events, one
    feed any calendar app can subscribe to (her phone over the tailnet, a
    friend's Outlook on Windows). Regenerated on every rebuild, so a dragged
    chip moves its event on the subscriber's next refresh. This EXPORTS the
    brain's own plans; it never reads or touches her real calendars —
    that direction stays calendar_read/calendar_write's job."""
    s = M.load_season(today=today or date.today())
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0",
             "PRODID:-//life-brain//season//EN",
             "X-WR-CALNAME:Season", "CALSCALE:GREGORIAN"]
    for i in (s["items"] if s else []):
        if not i["planned"] or i["dropped"]:
            continue
        summ = i["text"] + (" (with " + ", ".join(i["with"]) + ")"
                            if i["with"] else "")
        summ = (summ.replace("\\", "\\\\").replace(";", "\\;")
                .replace(",", "\\,").replace("\n", " "))
        lines += ["BEGIN:VEVENT",
                  f"UID:{MD.taskkey(i['text'])}@life-brain",
                  f"DTSTAMP:{stamp}",
                  # DTEND is exclusive: a one-day event ends the next morning.
                  f"DTSTART;VALUE=DATE:{i['planned']['start'].strftime('%Y%m%d')}",
                  ("DTEND;VALUE=DATE:"
                   + (i["planned"]["end"] + timedelta(days=1)).strftime("%Y%m%d")),
                  f"SUMMARY:{summ}",
                  "END:VEVENT"]
    lines.append("END:VCALENDAR")
    path = os.path.join(BRAIN, "season.ics")
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write("\r\n".join(lines) + "\r\n")
    return path


def _nwpara(p):
    m = re.match(r"(Term worth knowing:|Terms from the week:)\s*(.*)", p)
    if m:
        return (f"<p><b>{html.escape(m.group(1))}</b> "
                f"{html.escape(m.group(2))}</p>")
    return f"<p>{html.escape(p)}</p>"


def _nwglossary(cfg=None):
    """brain/news-glossary.md as a rail box. The file keeps journal order;
    the page answers 'what was that word again', so it groups the terms by
    topic (her rule for any list mixing areas), newest few showing and the
    rest folded. A term she knew already leaves with one tap and waits in
    the last fold, where one more tap puts it back."""
    try:
        with open(os.path.join(BRAIN, "news-glossary.md"),
                  encoding="utf-8") as f:
            body = f.read()
    except Exception:
        return ""
    learn, knew = NEWS.glossary_parts(body)
    rx = r"^- \*\*(.+?)\*\* — (.+?)(?:\s*\*\((.+?)\)\*)?\s*$"
    entries = re.findall(rx, learn, flags=re.M)
    known = re.findall(rx, knew, flags=re.M)
    if not entries and not known:
        return ""

    def cap(s):
        s = s.strip()
        return s[:1].upper() + s[1:]

    # The file tags each term "2026-09-28, Money & markets": the topic is
    # the group's heading, so the row only says "28 Sep".
    groups = {}
    for n, (term, definition, tag) in enumerate(entries):
        m = re.match(r"(\d{4}-\d{2}-\d{2}),?\s*(.*)$", tag or "")
        day, topic = (m.group(1), m.group(2)) if m else ("", tag or "")
        groups.setdefault(topic.strip() or "Other", []).append(
            (day, n, term, definition))

    def row(day, term, definition):
        when = ""
        try:
            td = date.fromisoformat(day)
            when = "%d %s" % (td.day, td.strftime("%b"))
        except ValueError:
            pass
        return ('<div class="nwg">'
                f"<dt>{html.escape(cap(term))}</dt>"
                '<dd class="nwgside">'
                '<button class="nwread nwknew needs-server"'
                f' data-term="{html.escape(term)}" title="I knew this'
                ' already: take it off, and the breakdowns pitch above it">'
                "knew it</button>"
                + (f'<span class="nwgdate">{when}</span>' if when else "")
                + f'</dd><dd class="nwgdef">{html.escape(cap(definition))}'
                "</dd></div>")

    # Topics in the order she follows them, so the groups never swap
    # places from one morning to the next.
    order = [i.get("topic", "")
             for i in ((cfg or {}).get("news") or {}).get("interests") or []]
    keys = sorted(groups, key=lambda k: (
        order.index(k) if k in order else len(order), k))
    show = 4
    parts = []
    for k in keys:
        items = sorted(groups[k], reverse=True)
        rest = items[show:]
        parts.append(
            f'<p class="nwgh">{html.escape(k)}<b>{len(items)}</b></p>'
            "<dl>" + "".join(row(d, t, df) for d, _, t, df in items[:show])
            + "</dl>"
            + (f'<details class="nwgmore"><summary>{len(rest)} more'
               "</summary><dl>"
               + "".join(row(d, t, df) for d, _, t, df in rest)
               + "</dl></details>" if rest else ""))
    if known:
        parts.append(
            '<details class="nwgknew"><summary>Knew already'
            f"<b>{len(known)}</b></summary><ul>"
            + "".join(
                f"<li><span>{html.escape(cap(t))}</span>"
                '<button class="nwread nwknew needs-server" data-back="1"'
                f' data-term="{html.escape(t)}"'
                ' title="Put it back in the glossary">put back</button></li>'
                for t, _, _ in reversed(known))
            + "</ul></details>")
    return ('<div class="nrbox nwgloss"><p class="eyebrow">Your glossary</p>'
            '<p class="meta">One term a day, from the breakdowns.</p>'
            + "".join(parts) + "</div>")


def _readmin(text):
    """Minutes at an ordinary reading pace. Only ever called on text the
    page actually holds — a guess from a headline would be a number she
    could not trust, so items without their text simply say nothing."""
    words = len((text or "").split())
    return max(1, round(words / 240)) if words else 0


def _nwitem(i):
    disc = ""
    # Feed links are the outlet's words, not ours: a javascript: one would
    # run on her page, so anything but a web address links nowhere.
    link = MD.safe_href(i["link"]) or "#"
    if i.get("discuss") and i["link"] != i["discuss"] and MD.safe_href(i["discuss"]):
        disc = (f' &middot; <a href="{html.escape(MD.safe_href(i["discuss"]))}"'
                ' target="_blank" rel="noopener">discussion</a>')
    # The reader gets the full article where it can: Guardian text rides in
    # .news.json; other outlets are pulled reader-mode on her click, with
    # the summary as the honest fallback (paywalls, offline).
    tip = ("Speed-read the full article"
           if i.get("body") else
           "Speed-read the article, or its summary when the article can't be pulled")
    read = (f'<button class="nwread" data-link="{html.escape(i["link"])}"'
            f' data-title="{html.escape(i["title"])}" title="{tip}">'
            "speed-read</button>") if i.get("summary") or i.get("body") else ""
    talk = (f'<button class="nwread nwtalk needs-server"'
            f' data-link="{html.escape(i["link"])}"'
            f' data-title="{html.escape(i["title"])}"'
            f' data-outlet="{html.escape(i["outlet"])}"'
            ' title="Open a conversation about this article">'
            f"talk to {AG.short()}</button>")
    # The same three actions sit under all thirty-odd stories. At rest the
    # line is just the outlet and the time — what she actually scans.
    # How long it takes to read, but only where the page holds the article.
    # Most outlets arrive as a headline, so most stories carry no number.
    mins = _readmin(i.get("body"))
    dur = f" &middot; {mins} min" if mins else ""
    acts = ('<span class="nwacts">' + disc
            + (f" &middot; {read}" if read else "")
            + f" &middot; {talk}</span>")
    return ('<article class="nwitem">'
            f'<a class="nwhead" href="{html.escape(link)}" target="_blank"'
            f' rel="noopener">{html.escape(i["title"])}</a>'
            f'<p class="meta">{html.escape(NEWS._item_meta(i))}{dur}{acts}</p>'
            + (f'<p class="nwsum">{html.escape(i["summary"])}</p>'
               if i.get("summary") else "")
            + "</article>")


def newsview(cfg):
    """The News tab: the day's briefing, built mechanically by news.py from
    the outlets in config — no model reads or writes a word of it. The
    morning job refreshes it; so do /brief, /wrap and the Refresh button."""
    data = None
    try:
        with open(os.path.join(BRAIN, ".news.json"), encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        pass
    ncfg = cfg.get("news") or {}

    def tg(name, on):
        # The paper plane is Telegram's own mark: lit when the topic rides
        # in the morning message, faint when she left it out.
        return (f'<button class="nwtg needs-server{" on" if on else ""}"'
                f' data-topic="{html.escape(name)}"'
                f' aria-pressed="{"true" if on else "false"}"'
                f' aria-label="{html.escape(name)} in the Telegram message"'
                ' title="In the morning Telegram message: tap to switch">'
                + ico("send") + "</button>")

    # Ranked, most important first: a higher topic claims a shared story
    # and leads on the page and in the message. Drag by the grip, or focus
    # it and use the arrow keys.
    rows = "".join(
        f'<li class="nwtopic" data-topic="{html.escape(t)}">'
        '<button class="nwgrip needs-server" aria-label="Move '
        f'{html.escape(t)}" title="Drag to rank it">' + ico("grip")
        + f'</button><span class="nwtname">{html.escape(t)}</span>'
        + tg(t, i.get("telegram") is not False)
        + f'<button class="nwdel needs-server" data-topic="{html.escape(t)}"'
        f' title="Stop following {html.escape(t)}">&times;</button></li>'
        for i in ncfg.get("interests") or [] for t in [i.get("topic", "")])
    toplist = ('<div class="nwtopic nwfixed"><span></span>'
               f'<span class="nwtname">{html.escape(NEWS.FRONT)}</span>'
               + tg(NEWS.FRONT, ncfg.get("front_telegram") is not False)
               + '<span></span></div>'
               f'<ol class="nwtopics" id="nwtopics">{rows}</ol>')
    upd = ""
    if data:
        try:
            dt = datetime.strptime(data["updated"], "%Y-%m-%d %H:%M")
            upd = (dt.strftime("%A %d %B").replace(" 0", " ")
                   + " &middot; updated " + dt.strftime("%H:%M"))
            if (datetime.now() - dt).total_seconds() > 18 * 3600:
                upd += ". Press Refresh for today&rsquo;s"
        except Exception:
            upd = f'updated {html.escape(data["updated"])}'
    # Topic ideas she asked for: a dashed chip to follow, an × to never see
    # it again, and the one line saying what in her life it ties to.
    sugs = "".join(
        '<li><span class="nwsugrow">'
        f'<button class="nwsugadd needs-server" data-topic="{html.escape(s["topic"])}"'
        f' title="Follow {html.escape(s["topic"])}">+ {html.escape(s["topic"])}'
        "</button>"
        f'<button class="nwsugno needs-server" data-topic="{html.escape(s["topic"])}"'
        ' title="Not for me: never suggested again">&times;</button></span>'
        + (f'<span class="nwsugwhy">{html.escape(s["why"])}</span>'
           if s.get("why") else "")
        + "</li>" for s in NEWS.suggestions())
    topicbox = ('<div class="nrbox"><div class="nrhead">'
                '<p class="eyebrow">Following</p>'
                '<button class="mini needs-server" id="nwsuggest"'
                ' title="Ideas from your projects and interests; tap one to'
                ' follow it">Suggest topics</button></div>'
                + toplist + '<div class="nwints">'
                '<input id="nwaddin" class="needs-server" maxlength="60"'
                ' placeholder="Follow a topic&hellip;" autocomplete="off">'
                '<button class="mini needs-server" id="nwaddbtn">Add</button>'
                "</div>"
                + (f'<ul class="nwsugs">{sugs}</ul>' if sugs else "")
                + "</div>")
    # Refresh rides on the freshness line it changes. Pushed to the right of
    # a 54px headline it floated mid-row, tied to nothing (page review N2).
    head = ('<section class="newsv"><p class="eyebrow">News</p>'
            '<div class="nwtop"><h2>Your briefing</h2></div>'
            + f'<p class="nwdate">{upd}'
            '<button class="mini needs-server" id="nwrefresh">Refresh</button>'
            "</p>")
    have = data and (data.get("front")
                     or any(t["items"] for t in data.get("topics", [])))
    if not have:
        return (head + topicbox
                + '<div class="empty">No briefing yet. Press Refresh, and '
                "after that it rebuilds itself each morning.</div>"
                "</section>")
    main = []
    if data.get("guardian") == "rss":
        main.append(AG.say('<p class="meta">The Guardian is on headlines only. '
                           "With its free API key you get full excerpts. Tell "
                           "Claude to set it up.</p>"))

    def expbox(eyebrow, text):
        paras = "".join(_nwpara(p.strip())
                        for p in text.splitlines() if p.strip())
        # The breakdown looks like a wall next to the headlines around it.
        # Its length is the one thing she can't see before starting, so say it.
        return ('<div class="nwexplain"><div class="nwexphead">'
                f'<p class="eyebrow">{eyebrow}</p>'
                f'<span class="nwexpact">{_readmin(text)} min &middot; '
                '<button class="nwread" title="Speed-read this">'
                "speed-read</button></span></div>" + paras + "</div>")

    def block(title, items, explainer=""):
        if not items:
            return
        exp = expbox("In plain terms", explainer) if explainer else ""
        main.append(f'<div class="nwsec"><h3>{html.escape(title)}</h3>' + exp
                    + "".join(_nwitem(i) for i in items) + "</div>")

    block("The front page", data.get("front") or [])
    for t in data.get("topics", []):
        block(t["topic"], t["items"], t.get("explainer") or "")
    for r in data.get("recaps") or []:
        if r.get("text"):
            main.append('<div class="nwsec">'
                        f'<h3>The week in {html.escape(r["topic"])}</h3>'
                        + expbox("Sunday recap", r["text"]) + "</div>")
    if data.get("failed"):
        names = ", ".join(f["name"] for f in data["failed"])
        main.append(f'<p class="meta">Couldn&rsquo;t reach {html.escape(names)}'
                    " on the last fetch.</p>")
    # The reading column keeps a text measure; the rail spends the rest of
    # a wide screen on the controls and the glossary instead of whitespace.
    # The rail's first box lines up with the first story, not with the label
    # above it: an invisible copy of a section label takes the label's exact
    # height in whichever skin is on (page review N1).
    lead = ('<div class="nwsec nwlead" aria-hidden="true"><h3>&#8203;</h3></div>'
            if main and main[0].startswith('<div class="nwsec">') else "")
    return (head + '<div class="newsgrid"><div class="newsmain">'
            + "".join(main) + "</div>"
            + '<aside class="newsrail">' + lead + topicbox + _nwglossary(cfg)
            + "</aside></div></section>")



# --------------------------------------------------------------------------
# Appearance: the palette is generated from three seeds so it can be a
# person's own — a neutral BASE (paper tint), an ACCENT (the "yours/good"
# hue), and a FONT pairing. The semantic colours (bad/wait/cold) stay fixed
# because they carry meaning; only personality moves.

BASES = {          # neutral hue, and a chroma multiplier for how tinted it is
    "warm":  (100, 1.0),
    "cool":  (250, 0.9),
    "rose":  (20, 1.0),
    "mono":  (100, 0.18),
}
ACCENTS = {        # the primary/"yours" hue
    "olive": 135, "forest": 150, "teal": 185, "ocean": 245,
    "indigo": 280, "plum": 325, "rose": 12, "amber": 70,
}
FONTS = {
    "editorial": ("'Literata',Georgia,serif", "'Schibsted',-apple-system,sans-serif"),
    "clean":     ("'Schibsted',-apple-system,sans-serif", "'Schibsted',-apple-system,sans-serif"),
    # Chunky, characterful headings over a clean body — the hand-drawn layer.
    "playful":   ("'Bricolage',Georgia,sans-serif", "'Schibsted',-apple-system,sans-serif"),
    # The 2026 redesign's own pairing: a tall condensed display voice over a
    # quiet workhorse sans, with Petrona italic carrying the coaching lines.
    "brain":     ("'Darker','Bricolage',Georgia,sans-serif",
                  "'Figtree','Schibsted',-apple-system,sans-serif"),
}
# The coaching voice — the italic margin-note sentences — is its own slot,
# because it must stay a serif whatever pairing the display/body use.
COACH_FONT = "'Petrona','Literata',Georgia,serif"
# A palette is the whole look at once — the accent, the paper it sits on,
# the type, and the map's dot scheme — because picking a hue on its own
# barely moved the page and made the controls feel dead.
# Each palette carries the three colours its chip shows: the paper it puts
# under everything, the accent that does the work, and the warm second voice.
# The chip is a tiny page — paper with two inks on it — rather than three
# stripes, which only ever read as a flag.
PALETTES = {
    "blush":     {"accent": "plum",   "base": "rose", "font": "brain",     "dots": "berry",
                  "label": "Blush", "note": "plum on blush",
                  "sw": ("oklch(96% .012 340)", "oklch(50% .13 325)", "oklch(52% .13 356)")},
    "forest":    {"accent": "forest", "base": "warm", "font": "brain",     "dots": "clay",
                  "label": "Forest", "note": "green on cream",
                  "sw": ("oklch(96.5% .012 100)", "oklch(48% .11 150)", "oklch(55% .12 40)")},
    "harbour":   {"accent": "ocean",  "base": "cool", "font": "clean",     "dots": "ocean",
                  "label": "Harbour", "note": "blue on cool grey",
                  "sw": ("oklch(96.5% .01 250)", "oklch(52% .12 245)", "oklch(56% .11 250)")},
    "olive":     {"accent": "olive",  "base": "warm", "font": "editorial", "dots": "clay",
                  "label": "Olive", "note": "olive on cream, serif",
                  "sw": ("oklch(96.5% .014 100)", "oklch(48% .11 135)", "oklch(58% .1 45)")},
    "ember":     {"accent": "amber",  "base": "warm", "font": "playful",   "dots": "sunset",
                  "label": "Ember", "note": "amber and red",
                  "sw": ("oklch(96.5% .015 90)", "oklch(60% .12 70)", "oklch(54% .17 25)")},
    "midnight":  {"accent": "indigo", "base": "cool", "font": "brain",     "dots": "ink",
                  "label": "Midnight", "note": "indigo on cool grey",
                  "sw": ("oklch(96% .01 260)", "oklch(50% .13 280)", "oklch(46% .14 288)")},
    "paper":     {"accent": "teal",   "base": "mono", "font": "editorial", "dots": "ink",
                  "label": "Paper", "note": "teal on near-white, serif",
                  "sw": ("oklch(96.5% .004 200)", "oklch(52% .11 185)", "oklch(44% .03 90)")},
}


def palette_chips(cfg):
    """The palette picker. Each chip names itself — a 34px swatch cannot tell
    you what "Harbour" is, and an unlabelled grid of seven made choosing a
    look into guesswork."""
    ap = (cfg.get("appearance") or {})
    cur = ap.get("palette") or ""
    if not cur:
        # Changing the style alone drops the saved palette name (the server
        # treats any change as hand-tuning), though every colour still is
        # that palette's. Name it again when accent, paper and type all match,
        # so the picker shows what she is looking at (28 Sep review, H2).
        cur = next((k for k, p in PALETTES.items()
                    if all(ap.get(f) == p[f] for f in ("accent", "base", "font"))),
                   "")
    out = []
    for key, p in PALETTES.items():
        paper, ink, second = p["sw"]
        on = " on" if key == cur else ""
        out.append(
            f'<button class="palchip{on}" data-palette="{key}" title="{p["note"]}" '
            f'style="--pp:{paper};--pi:{ink};--p2:{second}">'
            '<span class="palswatch" aria-hidden="true"></span>'
            f'<span class="pallabel">{p["label"]}</span></button>')
    # Picking an accent on its own leaves no palette selected, which used to
    # look like a bug. Say what actually happened instead.
    if not cur:
        out.append('<p class="palnote">Mixed by hand below. Pick a '
                   'palette to reset all four at once.</p>')
    return "".join(out)

# One exception to "semantic colours stay fixed": the map's relationship
# dots may be re-dressed (appearance.dots). Every option keeps the same
# hot-to-calm ordering — overdue is always the loudest, cold the quietest —
# so the colour still MEANS what it always meant; only the wardrobe changes.
# "moving" is untouched everywhere: good news stays the page's accent green.
DOTS = {
    "clay":   ({}, {}),                      # the built-in terracotta scheme
    "berry":  ({"overdue": "oklch(50% .15 356)", "soon": "oklch(59% .12 330)",
                "chase": "oklch(64% .09 300)", "cold": "oklch(56% .05 262)"},
               {"overdue": "oklch(72% .14 356)", "soon": "oklch(74% .11 330)",
                "chase": "oklch(76% .09 300)", "cold": "oklch(70% .05 262)"}),
    "ocean":  ({"overdue": "oklch(46% .14 288)", "soon": "oklch(56% .11 250)",
                "chase": "oklch(63% .08 225)", "cold": "oklch(70% .05 200)"},
               {"overdue": "oklch(74% .13 288)", "soon": "oklch(77% .1 250)",
                "chase": "oklch(80% .08 225)", "cold": "oklch(82% .05 200)"}),
    "sunset": ({"overdue": "oklch(54% .17 25)", "soon": "oklch(63% .13 55)",
                "chase": "oklch(72% .11 85)", "cold": "oklch(62% .06 320)"},
               {"overdue": "oklch(72% .15 25)", "soon": "oklch(76% .12 55)",
                "chase": "oklch(80% .1 85)", "cold": "oklch(72% .06 320)"}),
    # All greys, so ink also sets the two quiet states the others leave to
    # the page: its "with someone else" was the page's grey, one step from
    # "due soon" and darker than "they have gone quiet" (28 Sep).
    "ink":    ({"overdue": "oklch(28% .03 90)", "soon": "oklch(44% .025 90)",
                "chase": "oklch(57% .02 90)", "cold": "oklch(70% .015 90)",
                "waiting": "oklch(81% .012 90)", "closed": "oklch(93% .008 90)"},
               {"overdue": "oklch(92% .02 90)", "soon": "oklch(76% .02 90)",
                "chase": "oklch(62% .02 90)", "cold": "oklch(48% .015 90)",
                "waiting": "oklch(37% .012 90)", "closed": "oklch(28% .008 90)"}),
}
DAY_HUE = 55       # the "today" terracotta pop — warm, and left constant

# ---------------------------------------------------------------- styles
# The skin registry lives in skins.py: preview blocks (all skins, tiny,
# instant picker preview) and full skins (skins/<key>.css + fonts, baked
# only for the active one). serve.py validates against STYLES.
import skins as SK
import switches as SW
STYLES = SK.SKINS
style_css = SK.preview_css
style_chips = SK.chips


def _ok(l, c, h):
    return f"oklch({l}% {round(c, 4)} {h})"


def _mix_hue(h1, h2, k):
    """Blend two hues along the shorter way round the wheel (k=0 → h1, 1 → h2)."""
    d = ((h2 - h1 + 180) % 360) - 180
    return round((h1 + d * k) % 360, 1)


def _palette(base, accent, dark=False):
    nh, cm = BASES.get(base, BASES["warm"])
    ah = ACCENTS.get(accent, ACCENTS["olive"])
    # The neutrals — paper, text, lines — lean toward the accent hue, so
    # choosing an accent recolours the whole page and not just the FAB. Their
    # chroma is nudged up a touch so the tint actually reads. Mono has no base
    # temperature of its own, but the ACCENT still tints its greys — it just
    # does so gently, so mono reads as "your colour on grey," not a full wash.
    if base == "mono":
        th, cmn = ah, 0.5
    else:
        th, cmn = _mix_hue(nh, ah, .5), cm
    if not dark:
        n = {
            "paper": _ok(96.5, .014 * cmn, th), "surface": _ok(98.2, .009 * cmn, th),
            "sunken": _ok(93.8, .02 * cmn, th), "ink": _ok(25, .022 * cmn, th + 15),
            "dim": _ok(45, .026 * cmn, th + 10), "faint": _ok(60, .024 * cmn, th + 5),
            "line": _ok(89, .02 * cmn, th), "line2": _ok(81, .026 * cmn, th),
            "green": _ok(43, .105, ah), "greenbg": _ok(92, .05, ah),
            "terra": _ok(54, .11, DAY_HUE),
            "bad": _ok(49, .13, 32), "badbg": _ok(93, .035, 32),
            "wait": _ok(55, .1, 78), "waitbg": _ok(93.5, .045, 85),
            "cold": _ok(50, .05, 245), "coldbg": _ok(92.5, .02, 240),
            "shadow": "0 1px 2px oklch(25% .02 " + str(th + 15) + " / .06)",
            "shadow-lift": ("0 1px 2px oklch(25% .02 " + str(th + 15) + " / .05),"
                            "0 14px 36px -18px oklch(25% .04 " + str(th + 15) + " / .22)"),
        }
    else:
        n = {
            "paper": _ok(20, .016 * cmn, th + 10), "surface": _ok(23.5, .02 * cmn, th + 10),
            "sunken": _ok(17.5, .018 * cmn, th + 10), "ink": _ok(91, .018 * cmn, th),
            "dim": _ok(69, .026 * cmn, th + 5), "faint": _ok(54, .026 * cmn, th + 5),
            "line": _ok(30.5, .024 * cmn, th + 10), "line2": _ok(38, .028 * cmn, th + 10),
            "green": _ok(77, .12, ah), "greenbg": _ok(33, .06, ah),
            "terra": _ok(72, .1, DAY_HUE + 5),
            "bad": _ok(70, .12, 30), "badbg": _ok(29.5, .05, 30),
            "wait": _ok(76, .1, 85), "waitbg": _ok(30.5, .045, 85),
            "cold": _ok(72, .06, 240), "coldbg": _ok(28.5, .03, 240),
            "shadow": "none",
            "shadow-lift": "0 14px 36px -18px oklch(0% 0 0 / .5)",
        }
    out = "".join(f"--{k}:{v};" for k, v in n.items())
    # ---- the 2026 redesign's vocabulary, aliased onto the generated palette.
    # The design names its tokens card/wash/ink2/ink3/rule/accent/red/amber/
    # blue; mapping rather than hard-coding keeps her accent, paper and dark
    # switches working — pick a different accent and the whole design moves
    # with it, exactly as before.
    alias = {
        # --bg/--text are the map's and the tour's names for paper and ink.
        # The brain page never defined them, so shared components that used
        # them (the tour's Next button asked for color:var(--bg)) fell back
        # to inherited dark text on a dark button — unreadable. Defining
        # them here fixes every such component at once.
        "bg": "var(--paper)", "text": "var(--ink)",
        "card": "var(--surface)", "wash": "var(--sunken)",
        "ink2": "var(--dim)", "ink3": "var(--faint)",
        "rule": "var(--line2)", "rule2": "var(--line)",
        "accent": "var(--green)", "atint": "var(--greenbg)",
        "red": "var(--bad)", "redt": "var(--badbg)",
        "amber": "var(--wait)", "ambert": "var(--waitbg)",
        "blue": "var(--cold)", "bluet": "var(--coldbg)",
        # the design's --green means "healthy/moving", which in her semantic
        # palette is the success hue, not the accent
        "ok": _ok(50, .068, 155) if not dark else _ok(77, .07, 155),
        "okt": _ok(94.5, .028, 155) if not dark else _ok(31, .05, 155),
    }
    return out + "".join(f"--{k}:{v};" for k, v in alias.items())


def palette_css(cfg):
    ap = cfg.get("appearance", {}) or {}
    base = ap.get("base", "warm")
    accent = ap.get("accent", "olive")
    font = ap.get("font", "editorial")
    serif, sans = FONTS.get(font, FONTS["editorial"])
    scale = ("--serif:" + serif + ";--sans:" + sans + ";"
             "--coach:" + COACH_FONT + ";"
             "--s1:4px;--s2:8px;--s3:12px;--s4:16px;--s5:24px;--s6:32px;--s7:48px;--s8:64px;--s9:96px;"
             "--t-xs:.75rem;--t-sm:.8125rem;--t-base:.9375rem;--t-lg:1.1875rem;--t-xl:1.5rem;"
             "--t-2xl:1.875rem;--r-xl:18px;--r-lg:16px;--r-card:14px;--r-md:12px;"
             "--r-btn:10px;--r-sm:8px;--ease:cubic-bezier(.16,1,.3,1);")
    light = _palette(base, accent, dark=False)
    dark = _palette(base, accent, dark=True)
    ap_style = SK.active(cfg)
    return (":root{" + light + scale + "}\n"
            ":root[data-theme=\"dark\"]{" + dark + "}\n"
            "@media (prefers-color-scheme:dark){:root:not([data-theme=\"light\"]){"
            + dark + "}}\n"
            # After the theme blocks on purpose: a style block of equal
            # specificity must win by order, in both light and auto-dark.
            + style_css()
            # The ACTIVE skin's fonts and full stylesheet, last so it wins
            # over its own preview block. Other skins ship preview only.
            + "\n" + SK.faces_css(ap_style)
            + "\n" + SK.full_css(ap_style)
            + "\n" + LN.strip_css()
            # Every tab switch, one look per style, after the skin so it
            # wins over a skin's leftovers (switches.py, 8 Oct).
            + "\n" + SW.css())



def _offer_verb(text):
    """What Claude would actually do for this task, or "" when the answer is
    nothing. A dated line like "Bachelorette: 4-7 September (Montenegro)" is
    a fact in her calendar, not a job — offering to start it was noise."""
    t = (text or "").lower()
    for words, what in (
        (("book", "buy", "train", "flight", "ticket", "reserve"),
         "would price the real options and put the links on this task"),
        (("call", "phone", "ring"),
         "would find the number and the hours"),
        (("email", "message", "write", "reply", "send", "draft", "text"),
         "would write a draft for you to approve"),
        (("submit", "form", "apply", "register", "renew"),
         "would find what the form needs and pre-fill what it can"),
        (("find", "research", "compare", "look into", "quote", "price"),
         "would do the search and bring back the shortlist"),
        (("read", "review", "check"),
         "would read it and tell you what matters in it"),
    ):
        if any(w in t for w in words):
            return what
    return ""


def routine_card(today):
    """The routine, one step at a time — whichever moment she is actually in.

    Two lives, both terse. For the first fortnight it teaches the shape: the
    step, its button, and one faint line (what comes next, day N of 14).
    After that it shrinks to the imperative and its button. All reasoning
    lives behind the one fold. The steps and their words come from
    brain/routine.md, so editing the file changes the card (that file says
    so, and means it)."""
    try:
        raw = read("routine.md")
    except Exception:
        return ""
    meta, body = MD.split_frontmatter(raw)
    started = M.parse_date(meta.get("started", "")) if meta.get("started") else None
    day_n = (today - started).days + 1 if started else 1
    learning = day_n <= 14

    # Each step: heading match, when it applies, and the control that does it.
    hour = now_minutes() // 60
    steps = []
    for m in re.finditer(r"^## ([^\n]+)\n(.*?)(?=\n## |\Z)", body, re.S | re.M):
        head, chunk = m.group(1).strip(), m.group(2).strip()
        if head.lower().startswith("how this adapts") or head.lower().startswith("what it"):
            continue
        # the lead is a paragraph and wraps; taking its first line only was
        # what cut "…Questions for you, then" off mid-sentence
        ml = re.search(r"^\*\*.+?(?=\n\s*\n|\n\s*-\s|\Z)", chunk, re.S | re.M)
        lead = re.sub(r"\s+", " ", ml.group(0)).strip() if ml else ""
        # the "why" bullet wraps across lines in the file, so take it whole
        mw = re.search(r"-\s*Why it works:\s*(.+?)(?=\n\s*-\s|\n\s*\n|\Z)",
                       chunk, re.S | re.I)
        why = re.sub(r"\s+", " ", mw.group(1)).strip() if mw else ""
        if why:
            why = why[0].upper() + why[1:]
        steps.append({"head": head, "lead": lead, "why": why, "body": chunk})
    if not steps:
        return ""

    # Which moment of the DAY is it? The weekly step never takes the day's
    # place — it rides underneath on Sundays.
    idx = 0
    if hour >= 17:
        idx = min(2, len(steps) - 1)
    elif hour >= 11:
        idx = min(1, len(steps) - 1)
    step = steps[idx]
    weekly = steps[3] if (today.weekday() == 6 and len(steps) > 3) else None
    ACTION = {0: ('<button class="mini needs-server" data-job="today">'
                  "Rewrite today&rsquo;s plan</button>"
                  '<button class="mini needs-server" id="rt-upd">What happened?</button>'),
              1: ('<button class="mini needs-server" id="rt-cap">'
                  "Capture a thought</button>"),
              2: ('<button class="mini" id="rt-eve">Go to the evening check</button>'),
              3: ('<a class="mini" href="rooms.html">Audit a wing</a>'
                  '<a class="mini" href="#questions">Answer the questions</a>')}
    def _name(st):
        return st["head"].split("·")[0].strip()

    def _when(st):
        return st["head"].split("·")[1].strip() if "·" in st["head"] else ""

    # The card's job is to say what to do, in one line, and hand over the
    # button that does it. The lead in routine.md is an imperative followed by
    # a sentence or two of elaboration; only the imperative belongs on the
    # face of the card.
    _m_imp = re.match(r"^\*\*(.+?)\*\*\s*(.*)$", step["lead"] or "", re.S)
    imperative = (_m_imp.group(1) if _m_imp else step["lead"] or "").strip()
    lead_html = (f'<p class="rtlead">{linkify_html(MD.inline(imperative))}</p>'
                 if imperative else "")
    # The first sentence after the imperative names what the card is about.
    # Without it the slim card was a four-word aphorism with no subject —
    # "Capture, never file." meant nothing on sight (her report, 10 Sep).
    _elab = (_m_imp.group(2) if _m_imp else "").strip()
    elab_first = (re.split(r"(?<=[.!?])\s+",
                           re.sub(r"\s+", " ", _elab))[0] if _elab else "")
    extra = ""
    if weekly:
        wk_head = ('<p class="rtstep"><b>' + e(_name(weekly)) + "</b>"
                   + (f'<span class="rtwhen">{e(_when(weekly))}</span>'
                      if _when(weekly) else "")
                   + "</p>")
        extra = ('<div class="rtweekly">'
                 + cardhead(wk_head, artimg("wayfinding", 46))
                 + (linkify_html(MD.render(weekly["lead"])) if weekly["lead"] else "")
                 + f'<div class="rtacts">{ACTION.get(3, "")}</div></div>')
    whole = ('<details class="ghost rtall"><summary>The whole routine</summary>'
             + linkify_html(MD.render(body)) + "</details>")

    # Settled: the habit is hers, so the card keeps its promise and gets out
    # of the way — the imperative and its button on one line, the file one
    # fold away. Sundays still bring the weekly step.
    if not learning:
        return ('<section class="railcard routinecard rtslim">'
                + '<p class="eyebrow">Routine</p>'
                + '<div class="rtrow">' + lead_html
                + f'<div class="rtacts">{ACTION.get(idx, "")}</div></div>'
                + (f'<p class="rtsub">{linkify_html(MD.inline(elab_first))}</p>'
                   if elab_first else "")
                + extra + whole + "</section>")

    # Teaching: the step and its button, plus ONE faint line of context —
    # what comes next and how far into the fortnight she is. The reasoning
    # stays in the file, one fold away; prose on the card's face reads as
    # filler no matter how true it is.
    day_steps = steps[:3]
    n = day_steps[(idx + 1) % len(day_steps)]
    foot = (f'{"Tomorrow" if idx + 1 >= len(day_steps) else "Next"}: '
            + e(_name(n).lower())
            + (f', {e(_when(n))}' if _when(n) else ""))
    if started:
        foot += f' &middot; day {day_n} of 14'
    # A face per moment — the evening step is the one she skips, and a
    # picture of sitting down is a better argument than another sentence.
    MOMENT_ART = {2: "evening", 3: "wayfinding"}
    return ('<section class="railcard routinecard">'
            + cardhead('<h3 class="area">The routine</h3>',
                       artimg(MOMENT_ART[idx], 46) if idx in MOMENT_ART else "")
            + f'<p class="rtstep"><b>{e(_name(step))}</b>'
            + (f'<span class="rtwhen">{e(_when(step))}</span>' if _when(step) else "")
            + "</p>"
            + lead_html
            + f'<div class="rtacts">{ACTION.get(idx, "")}</div>'
            + f'<p class="rtfoot">{foot}</p>'
            + extra
            + whole + "</section>")


def countdown_card(today):
    """Counting down — the owner's days-until numbers, from
    brain/countdowns.md, plus every Season idea she has put on a day. One
    line per event; a date in words resolves to the day it starts; past
    dates drop off the page on their own. The card face is just the rows —
    the anticipation is the content."""
    rows = [] if PRESENTING else countdown_rows(today)
    if not rows:
        return ""
    body = "".join(
        f'<p class="cdrow"><span class="cdlab">{e(lab)}</span>'
        f'<b class="cdn">{e(when)}</b>'
        f'<span class="cddate">{d.day} {d.strftime("%b")}</span></p>'
        for n, lab, when, d in rows)
    return ('<section class="railcard cdcard">'
            '<h3 class="area">Counting down</h3>' + body + "</section>")


def countdown_rows(today):
    """[(days, label, when, date)], soonest first: the card's rows, also
    read by Orbit's deck (orb.py)."""
    try:
        raw = read("countdowns.md")
    except Exception:
        raw = ""
    rows, seen = [], set()

    def add(d, label):
        label = re.sub(r"\(\s*\)", "", label).strip(" .,·—–-")
        if not d or d < today or (label.lower(), d) in seen:
            return
        seen.add((label.lower(), d))
        n = (d - today).days
        when = "today" if n == 0 else ("tomorrow" if n == 1 else f"{n} days")
        rows.append((n, label, when, d))

    for ln in raw.split("\n"):
        m = re.match(r"^\s*[-*]\s+(.*)$", ln)
        if not m:
            continue
        txt = m.group(1).strip()
        d, label = None, txt
        md = re.search(r"\d{4}-\d{2}-\d{2}", txt)
        if md:
            d = M.parse_date(md.group(0))
            label = txt.replace(md.group(0), "")
        else:
            parts = re.split(r"\s+[—–-]\s+", txt, maxsplit=1)
            if len(parts) == 2:
                pd = M.parse_due(parts[1], today)
                if pd:
                    d, label = pd["start"], parts[0]
        add(d, label)
    # Fun she has put on a day counts down with nothing to maintain. The
    # file alone held only deadlines, and looking forward to an experience
    # is a good part of its pleasure (research page, 28 Sep).
    try:
        s = M.load_season(today=today)
    except Exception:
        s = None
    for i in (s or {}).get("items", []):
        if i["planned"] and not i["done"] and not i["dropped"]:
            add(i["planned"]["start"], i["text"])
    rows.sort(key=lambda r: r[0])
    return rows


def week_strip(cfg, today, today_md=""):
    """This week as seven columns she can rearrange. Placed tasks come from
    week-plan.md, today's column mirrors today.md, events come from the
    calendar, and each day carries its load against her capacity. Dragging
    (or tapping) a task is a decision the files record — never a model call.
    Collapsed to one line when nothing is placed and no events are known."""
    try:
        raw = read("week-plan.md")
    except Exception:
        raw = ""
    if PRESENTING:
        raw = present_md(raw)     # the work outside the hidden areas only
    cap = cfg.get("capacity") or {}
    daily = int(cap.get("daily_minutes") or 180)
    dflt = int(cap.get("default_task_minutes") or 30)

    def est_mins(text):
        mm = re.search(r"~\s*(\d+)h(\d*)\b|~\s*(\d+)m\b", text, re.I)
        if not mm:
            return None
        if mm.group(3):
            return int(mm.group(3))
        return int(mm.group(1)) * 60 + int(mm.group(2) or 0)

    def disp(text):
        # The plan's own notes ("(at 18:30, walking out of campus)") are for
        # the plan; a day's column shows the task (8 Oct).
        return MD.plain(re.sub(
            r"\s*\((?:due|waiting until|urgent|carrying|at|short)\b[^)]*\)", "",
            re.sub(r"~\s*(?:\d+h\d*|\d+m)\b", "", text, flags=re.I))).strip()

    def alike(a, b):
        """The same task in two wordings: two shared words, at least half of
        the shorter title (stricter than _same_thing, where one long shared
        word would merge the Session 2 reflection with the reflection
        paper)."""
        sa, sb = _sig_tokens(disp(a)), _sig_tokens(disp(b))
        sh = sa & sb
        return len(sh) >= 2 and 2 * len(sh) >= min(len(sa), len(sb))

    # A week-plan copy of a task since done, parked or dropped on its front
    # is not on a day any more (8 Oct: the residence task, parked until
    # 10 Oct, still sat in Today's column from Monday's sketch).
    closed, still_open = [], []
    home = lambda _t: None                             # noqa: E731
    try:
        _items = M.load(cfg=cfg)
        # Each task names its project (8 Oct: "M4 —…" alone in a column
        # said nothing about which front it was).
        home = plan_ws_lookup(_items, cfg)
        for _w in _items:
            for _t in _w["tasks"]:
                (closed if (_t["done"] or _t.get("parked") or _t.get("dropped"))
                 else still_open).append(_t["text"])
    except Exception:
        pass

    def gone_elsewhere(text):
        return (any(alike(text, c) for c in closed)
                and not any(alike(text, o) for o in still_open))

    placed = {}
    for ms in re.finditer(r"^## [^\n]*?(\d{4}-\d{2}-\d{2})[^\n]*$\n(.*?)(?=\n## |\Z)",
                          raw, re.M | re.S):
        d = M.parse_date(ms.group(1))
        if not d:
            continue
        for mt in re.finditer(r"^\s*[-*]\s+\[([ xX])\]\s+(.*)$", ms.group(2), re.M):
            placed.setdefault(d, []).append(
                {"text": mt.group(2).strip(), "done": mt.group(1) != " ",
                 "key": MD.taskkey(MD.bare(mt.group(2)))})

    # Yesterday's unmoved placements ride today's column with their old day
    # on them — a slipped plan that hides is a plan that lies.
    slipped = []
    for d in sorted(placed):
        if d < today:
            slipped += [dict(t, was=d.strftime("%a")) for t in placed[d]
                        if not t["done"]]

    ttasks = []
    for mt in re.finditer(r"^\s*[-*]\s+\[([ xX])\]\s+(.*)$", today_md or "", re.M):
        rawt = mt.group(2)
        if mt.group(1) != " " or MD.DROPPED.search(rawt) or MD.UNTIL.search(rawt):
            continue
        ttasks.append({"text": rawt, "key": MD.taskkey(MD.bare(rawt))})

    ev = {}
    # The day's room uses the same reading as the week-ahead card: measured
    # event lengths, plus her fixed hours (8 Oct).
    _starts = (calendar_starts(7) or {}) if cfg.get("calendar") else {}
    if cfg.get("calendar"):
        try:
            import calendar_read
            for when, title in calendar_read.events(7):
                if re.match(r"(?i)\s*cancell?ed\b", title or ""):
                    continue
                hhmm = when.split(" ")[1][:5] if " " in when else ""
                ev.setdefault(when.split(" ")[0], []).append(
                    ("" if hhmm == "00:00" else hhmm, title))
        except Exception:
            pass
    nowm = now_minutes()

    n_placed = sum(len(v) for d, v in placed.items() if d >= today) + len(slipped)
    # ONE TASK, ONE DAY. Today's column is filled from today.md first, so a
    # week-plan placement of the same task later in the week is a sketch the
    # plan has already overtaken. Drawing both put "Call the doctor" on Monday
    # and Sunday at once — the line repeated, and its twenty minutes were
    # booked against two days' capacity, so neither day's bar told the truth.
    seen_keys, seen_texts = set(), []
    drawn_week = 0          # placements actually drawn, so the count can't
    cols = []               # promise a task the columns no longer show
    for k in range(7):
        d = today + timedelta(days=k)
        iso = d.isoformat()
        if k == 0:
            day_tasks = ([dict(t, src="today") for t in ttasks]
                         + [dict(t, src="week") for t in slipped]
                         + [dict(t, src="week") for t in placed.get(d, [])])
        else:
            day_tasks = [dict(t, src="week") for t in placed.get(d, [])]
        rows = []
        used = 0
        for t in day_tasks:
            # One task, one place, in any wording: the plan's line and the
            # week sketch's copy of it showed side by side (8 Oct).
            if t["key"] in seen_keys or any(alike(t["text"], x) for x in seen_texts):
                continue
            if t["src"] == "week" and gone_elsewhere(t["text"]):
                continue
            seen_keys.add(t["key"])
            seen_texts.append(t["text"])
            if t["src"] == "week":
                drawn_week += 1
            if not t.get("done"):
                used += est_mins(t["text"]) or dflt
            rows.append(
                f'<div class="wtask{" wdone" if t.get("done") else ""}"'
                f' draggable="true" data-key="{t["key"]}" data-wsrc="{t["src"]}"'
                + (' title="Drag to another day, or click to pick one"'
                   if not t.get("done") else "")
                + f'><span class="wtx" title="{e(disp(t["text"]))}">{e(disp(t["text"]))}</span>'
                + (lambda h: f'<span class="fc-proj">{e(h[1] or h[0])}</span>'
                   if h else "")(home(disp(t["text"])))
                + (f'<i>{e(t["was"])}</i>' if t.get("was") else "")
                + "</div>")
        evs = ev.get(iso) or []
        # Tasks against the day's room: the daily figure, never more than
        # the calendar leaves free — the same rule as the week-ahead card.
        # This used to add an hour per event to the TASK budget, and every
        # class is listed twice (with and without its room), so four classes
        # made Monday "over by ~6h55" before a single task (28 Sep).
        room = daily
        _end = M.day_hours(cfg)[1]
        if k == 0:
            room = min(room, max(0, _end - nowm))
        _fixed = [(fa, fb - fa) for fa, fb, _fl in M.fixed_blocks(cfg, d)]
        if evs or _fixed:
            room = min(room, M.free_minutes(list(_starts.get(iso, ())) + _fixed,
                                            day_end=_end,
                                            after=nowm if k == 0 else None))
        evline = ""
        if evs:
            # The calendar in neutral ink, each event with its time, up to
            # three; the rest as "+N more" with every title in the tooltip
            # (8 Oct: one title and "+3 more" said nothing about the day).
            # A class listed with and without its room counts once.
            uniq = []
            for hhmm, tl in sorted(evs, key=lambda x: x[0] or "00:00"):
                low = tl.strip().lower()
                # A class arrives twice at one time, with and without its
                # room, and the two can part ways after a long shared start.
                if not any(low.startswith(u[1].lower()) or u[1].lower().startswith(low)
                           or (hhmm and hhmm == u[0] and low[:20] == u[1].lower()[:20])
                           for u in uniq):
                    uniq.append((hhmm, tl.strip()))
            tip = chr(10).join((h + " " if h else "") + t for h, t in uniq)
            evline = (f'<ul class="wevents" title="{e(tip)}">'
                      + "".join(f'<li>{f"<b>{e(h)}</b> " if h else ""}{e(t)}</li>'
                                for h, t in uniq[:3])
                      + (f'<li class="wevmore">+{len(uniq) - 3} more</li>'
                         if len(uniq) > 3 else "") + "</ul>")
        pct = min(100, round(used * 100 / room)) if room else (100 if used else 0)
        # The thin bar is the day's load; it says so on hover.
        load_tip = ("How full the day is: nothing planned yet" if not used else
                    f"How full the day is: about {M.fmt_dur(used)} planned, "
                    f"{M.fmt_dur(room)} free")
        over = (f'<p class="wcolover">over by ~{e(M.fmt_dur(used - room))}</p>'
                if used > room else "")
        head = "Today" if k == 0 else f'{d.strftime("%a")} {d.day}'
        cols.append(
            f'<div class="wcol{" wtoday" if k == 0 else ""}" data-date="{iso}"'
            f' data-today="{1 if k == 0 else 0}">'
            f'<p class="wchead">{e(head)}'
            f'<button class="wadd" data-dow="{e(d.strftime("%A"))}"'
            ' title="Capture something for this day">+</button></p>'
            + evline + "".join(rows)
            + f'<div class="wload" title="{e(load_tip)}"><div class="wbar">'
            f'<i style="width:{pct}%"></i></div></div>'
            + over + "</div>")
    n_placed = drawn_week
    # It is the Week view's whole content now (28 Sep), so it opens.
    openattr = " open"
    sketch = ("" if n_placed else
              '<p class="wsketchrow"><button class="mini needs-server" '
              'id="wsketch">Sketch my week</button></p>')
    return (f'<details class="weekstrip"{openattr}><summary>This week'
            + (f' &middot; {n_placed} placed' if n_placed else "")
            + f'</summary>{sketch}'
            # The strip never said what it was FOR — "is the idea for me to
            # move things around?" (31 Aug). One line, above the columns.
            # It moves what is already on a day (there is no pile of unplaced
            # tasks here), and a phone cannot drag, so the touch line says tap.
            '<p class="whint"><span class="wh-mouse">Drag a task to another '
            'day, or click it to pick one.</span><span class="wh-touch">Tap a '
            'task to move it to another day.</span> + adds a note to that day.</p>'
            f'<div class="wcols">{"".join(cols)}</div></details>')


def dayshape(cfg, today, today_md="", ws_lookup=None):
    """WHEN — the day as a vertical timeline: the fixed things (calendar
    events, her own fixed hours), the free windows between them, and today's
    unfinished tasks slotted into the windows they fit, so the plan is read
    against real hours rather than an imaginary empty day.

    Since 8 Oct: an event is as long as the calendar measured it (a 12-hour
    course had read as one hour), volleyball and an evening off block their
    time (model.fixed_blocks), the day ends where she says (config
    week.day_end), an all-day entry is a note rather than busy time, and a
    parked task is never offered a window. A slotted task shows whole, with
    its project (`ws_lookup`, plan_ws_lookup's function), as every task
    shown away from its front does (page.md)."""
    timed, untimed = [], []          # timed: (start, end, label, kind)
    if cfg.get("calendar"):
        try:
            import calendar_read
            lens = calendar_read.lengths()
            byt = {}
            for when, title in calendar_read.events(1):
                hhmm = when.split(" ")[-1][:5] if " " in when else ""
                if re.match(r"(?i)\s*cancell?ed\b", title or ""):
                    continue
                if not hhmm or hhmm == "00:00":
                    untimed.append((title, "allday"))
                    continue
                byt.setdefault(hhmm, []).append((title, lens.get((when, title))))
            # A class arrives twice at one time ("Scale up" and "Scale up -
            # PROF - S210 - EN"); the longer twin is dropped, or the day
            # listed every class twice and offered each free gap twice.
            for hhmm, pairs in byt.items():
                titles = [t for t, _m in pairs]
                longest = max((m or 0) for _t, m in pairs) or None
                for title in dict.fromkeys(titles):
                    if not any(o != title and title.startswith(o) for o in titles):
                        a = int(hhmm[:2]) * 60 + int(hhmm[3:5])
                        timed.append((a, a + (longest or 60), title, "cal"))
        except Exception:
            pass
    blocks = M.fixed_blocks(cfg, today)
    for a, b, label in blocks:
        timed.append((a, b, label, "fixed"))
    if M.in_term(cfg, today) and not any(b == M.day_hours(cfg)[1] for _a, b, _l in blocks):
        # This weekday's standing notes, unless an evening off already said it.
        key = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"][today.weekday()]
        for label in (((cfg.get("week") or {}).get("days") or {}).get(key) or []):
            untimed.append((label, "week"))
    # Today's still-open tasks, in the plan's own order, with any estimate.
    tasks = []
    for ln in (today_md or "").split("\n"):
        mt = re.match(r"^\s*[-*]\s+\[([ xX])\]\s+(.*)$", ln)
        if not mt:
            continue
        raw = mt.group(2)
        if MD.DROPPED.search(raw):
            continue
        mu = MD.UNTIL.search(raw)
        parked = bool(mu and mu.group(1) > today.isoformat())
        est, em = "", None
        me = re.search(r"~\s*(\d+)h(\d*)\b|~\s*(\d+)m\b", raw, re.I)
        if me:
            est = me.group(0).lstrip("~").strip()
            em = (int(me.group(3)) if me.group(3)
                  else int(me.group(1)) * 60 + int(me.group(2) or 0))
        # The plan's own notes ("(at 21:00, after class)", "(short: …)") are
        # for the plan; the card shows the task.
        txt = MD.plain(re.sub(
            r"\s*\((?:due|waiting until|urgent|carrying|at|short)\b[^)]*\)", "",
            re.sub(r"~\s*(?:\d+h\d*|\d+m)\b", "", raw, flags=re.I))).strip()
        if not txt:
            continue
        tasks.append({"t": txt, "done": mt.group(1).lower() == "x", "est": est,
                      "mins": em, "parked": parked,
                      "carry": bool(MD.CARRYING.search(raw))})
    # Nothing fixed today means there is no day-shape to draw — the plan
    # under the hero already lists the tasks, so a card holding only a "now"
    # marker is dead weight. Show it only when something is actually fixed.
    if not timed and not untimed:
        return ""

    timed.sort(key=lambda x: (x[0], x[1]))
    now_dt = datetime.now()
    now = now_dt.strftime("%H:%M")
    nowm = now_dt.hour * 60 + now_dt.minute
    DAY_START, DAY_END = M.day_hours(cfg)

    def hm(x):
        x = min(x, 24 * 60)
        return f"{x // 60:02d}:{x % 60:02d}"

    # The gaps between the fixed things, where work can actually happen.
    # 30 minutes is the smallest window worth offering: a task only goes
    # into a gap it fits, so a 40-minute lunch gap can hold a 30-minute prep.
    free, cur = [], DAY_START
    for a, b, _label, _kind in timed:
        if a - cur >= 30:
            free.append((cur, a))
        cur = max(cur, b)
    if DAY_END - cur >= 30:
        free.append((cur, DAY_END))
    free = [(max(a, nowm), b) for a, b in free if b - max(a, nowm) >= 30]

    # A task that readies her for something stops being worth a free slot
    # once that thing is over: at 19:30 the rail offered "Prep for the
    # Venture meeting with Devon" six hours after the meeting (8 Oct).
    # The thing is a calendar entry today that has ended and shares two real
    # words with the task. A follow-up ("notes from the meeting") has no
    # prep word, so it is still offered after.
    _common = {"with", "from", "into", "about", "this", "that", "after",
               "before", "meeting", "session", "class", "call", "then"}

    def _moot(txt):
        low = txt.lower()
        if not re.search(r"\b(?:prep|prepare|ahead of|before|get ready)\b", low):
            return False
        words = set(re.findall(r"[a-zà-ÿ]{4,}", low))
        return any(kind == "cal" and b <= nowm
                   and len((set(re.findall(r"[a-zà-ÿ]{4,}", label.lower()))
                            - _common) & words) >= 2
                   for _a, b, label, kind in timed)

    # Each window takes the next open task that fits it; a task too long for
    # one gap waits for a bigger one, and a parked task waits for its day.
    dflt = M.capacity_cfg(cfg)["default_task_minutes"]
    queue = [t for t in tasks
             if not t["done"] and not t["parked"] and not _moot(t["t"])]
    slots = []
    for a, b in free:
        pick = next((t for t in queue if (t["mins"] or dflt) <= b - a), None)
        if pick:
            queue.remove(pick)
            slots.append((a, b, pick))

    rows, placed_now = [], False
    entries = ([(a, 0, ("fix", a, b, label)) for a, b, label, _k in timed]
               + [(a, 1, ("free", a, b, t)) for a, b, t in slots])
    for start, _o, ent in sorted(entries, key=lambda x: (x[0], x[1])):
        if not placed_now and start > nowm:
            rows.append(f'<li class="wnow"><i></i><b>{e(now)}</b> &middot; now</li>')
            placed_now = True
        if ent[0] == "fix":
            _f, a, b, label = ent
            span = hm(a) + (f"&ndash;{hm(b)}" if b - a >= 90 else "")
            _lc = LN.colour_attr("School") if _is_school_event(label) else ""
            rows.append(f'<li class="wfix"{_lc}><span class="wt">{span}</span>'
                        f'<span class="wl">{e(clip(label, 80))}</span></li>')
        else:
            _f, a, b, t = ent
            home = ws_lookup(t["t"]) if ws_lookup else None
            rows.append(
                f'<li class="wfree"{LN.ws_attr(home[0]) if home else ""}>'
                f'<span class="wt">{e(hm(a))}&ndash;{e(hm(b))} '
                '&middot; free</span>'
                f'<span class="wtask"{LN.attrs(LN.ws_area(home[0])) if home else ""}>'
                f'<span class="wtx" title="{e(t["t"])}">'
                f'{e(t["t"])}</span>'
                + (f'<span class="fc-proj">{e(home[1] or home[0])}</span>'
                   if home else "")
                + (f'<em>{e(t["est"])}</em>' if t["est"] else "")
                + ("<em>carrying</em>" if t["carry"] else "")
                + "</span></li>")
    for label, _kind in untimed:
        rows.append(f'<li class="wfix wweek"><span class="wl">{e(clip(label, 80))}</span></li>')
    if not placed_now:
        rows.append(f'<li class="wnow past"><i></i><b>{e(now)}</b> &middot; now</li>')
    done_n = len([t for t in tasks if t["done"]])
    sub = f'{today.strftime("%A")} {today.day} {today.strftime("%B")}'
    return ('<section class="whenwrap railcard"><p class="eyebrow">When</p>'
            '<span class="wav"></span>'
            f'<p class="whenday">{e(sub)}</p>'
            f'<p class="whensub">{e(now)}'
            + (f' &middot; {done_n} of {len(tasks)} done' if tasks else "")
            + "</p>"
            f'<ul class="when">{"".join(rows)}</ul></section>')


def conn_allow(*rows):
    """The one fold every Connections row ends with (8 Oct): what switching
    it on lets the brain do, under the same labels on every row, so the
    cost is read before the switch. `rows` are (label, html); empty skipped."""
    body = "".join(f"<dt>{k}</dt><dd>{v}</dd>" for k, v in rows if v)
    return ('<details class="connhow"><summary>What you&rsquo;re allowing'
            f'</summary><dl class="allow">{body}</dl></details>')


def _ps_mail_on(cfg):
    try:
        import plan_sources
        return plan_sources.on("mail", cfg)
    except Exception:                                    # noqa: BLE001
        return False


def _mailread_row(cfg, have_account=True):
    """Reading mail: the switch, the button, and what the last look found.

    Separate from the Mail row above because the two directions are different
    promises. Sending is her pressing send. Reading is a stranger getting to
    put text near Claude, which is why it is headers only. Since 8 Oct it
    may also run at 7, Mail app only, when she turns on the morning plan's
    mail switch (plan_sources.py)."""
    on = bool(((cfg.get("email") or {}).get("read") or {}).get("on"))
    try:
        import email_read as _er
        st = _er.last_check()
    except Exception:                                    # noqa: BLE001
        st = {}
    owed = [] if PRESENTING else (st.get("owed") or [])
    if owed:
        who = ", ".join(e(n) for n in owed[:4])
        more = f" and {len(owed) - 4} more" if len(owed) > 4 else ""
        found = (f'<span class="mrfound">Waiting on a reply from you: '
                 f"<b>{who}</b>{more}.</span>")
    elif st.get("checked"):
        found = ('<span class="mrfound">Last look found nobody waiting on '
                 "you.</span>")
    else:
        found = ""
    rd = ((cfg or {}).get("email") or {}).get("read") or {}
    if not have_account:
        state = ("Needs a mail account first: it reads with the app password "
                 "you set up for sending, above.")
    elif on:
        state = ("On. Reads who wrote to you and when"
                 + (", from your account and the Mac&rsquo;s Mail app "
                    "(Outlook too). " if rd.get("mac_mail") else ". ")
                 + '<button class="mini" id="mr-check">Check now</button> '
                 '<button class="mini" id="mr-off">Turn off</button>')
    else:
        state = ("Off. The brain can&rsquo;t see who is waiting on a reply. "
                 '<button class="mini" id="mr-on">Turn on</button>')
    return (
        '<div class="connrow needs-server"><i class="cdot'
        + (" on" if on else "") + '"></i><b>Mail in</b><span>'
        + state
        + '<span class="mshelp" id="mr-help"></span>'
        + found
        + conn_allow(
            ("It can", "Read the From, To and Cc lines and the date of the "
             f"last {int(rd.get('days') or 14)} days of mail, and flag people "
             "on your list who wrote after your last reply."),
            ("It can&rsquo;t", "See a subject or a body. "
             + ("It runs on your Check now, and at 7 each morning from the "
                "Mail app, because the morning plan&rsquo;s mail switch is on. "
                if _ps_mail_on(cfg) else
                "Only your Check now runs it, unless you turn on Who emailed "
                "you under What the morning plan checks. ")
             + "Messages stay unread."),
            ("Risk", "Low. It uses the app password you already gave for "
             "sending, and senders you don&rsquo;t track are counted and "
             "dropped, so strangers leave nothing behind."))
        + "</span></div>")


def _mailtasks_tray(cfg=None, bare=False):
    """The suggestions themselves, on Today. Accepting one writes a line to
    the inbox for normal triage; dismissing closes it. The whitelist that
    feeds this lives in Connections — that part IS a setting."""
    try:
        import mail_tasks as _mt
        pend = _mt.pending()
    except Exception:                                    # noqa: BLE001
        pend = []
    if not pend:
        return ""
    # The email itself, one click away — in HER mail client, not here. The
    # message-id (or, for older suggestions, the subject) makes a Gmail
    # search URL; the brain still stores nothing of what the mail said.
    _gmail = any((a.get("provider") == "gmail")
                 for a in (((cfg or {}).get("email") or {})
                           .get("accounts") or []))

    def _maillink(s):
        if not _gmail:
            return ""
        import urllib.parse as _up
        mid = (s.get("msgid") or "").strip().strip("<>")
        q = ("rfc822msgid:" + mid) if mid else (
            'subject:"' + s["subject"][:60] + '"' if s.get("subject") else "")
        if not q:
            return ""
        return ("https://mail.google.com/mail/u/0/#search/"
                + _up.quote(q, safe=""))

    def _row(s):
        due = (f' <span class="mtdue">due {e(s["due"])}</span>'
               if s.get("due") else "")
        src = s.get("subject") or s.get("from") or ""
        link = _maillink(s)
        srchtml = (f'<a href="{e(link)}" target="_blank" rel="noopener"'
                   ' title="Open the email itself in your mail">'
                   + e(src) + "</a>") if link else e(src)
        # The details she accepts with it (8 Oct), shown before she does.
        det = "".join(f'<i class="mtdet">{e(d)}</i>'
                      for d in (s.get("details") or [])[:4])
        return ('<div class="mtrow"><span class="mttask">'
                f'{e(s["task"])}{due}{det}<i>{srchtml}</i></span>'
                f'<button class="mini" data-mtact="accept" data-mtid="{e(s["id"])}">'
                "Add</button>"
                f'<button class="mini" data-mtact="dismiss" data-mtid="{e(s["id"])}">'
                "No</button></div>")

    # A suggestion whose date has passed stopped being a question worth the
    # page's front — folded, not hidden: she may still want to No them away.
    _today = date.today().isoformat()
    fresh = [s for s in pend if not (s.get("due") and s["due"] < _today)]
    stale = [s for s in pend if s.get("due") and s["due"] < _today]
    rows = [_row(s) for s in fresh[:12]]
    if stale:
        rows.append('<details class="ghost mtstale"><summary>'
                    f'{len(stale)} whose date has passed</summary>'
                    + "".join(_row(s) for s in stale[:12]) + "</details>")
    more = (f'<p class="mtmore">and {len(fresh) - 12} more</p>'
            if len(fresh) > 12 else "")
    # The feedback span lives IN the tray. Errors used to land in #mt-help,
    # a span inside the Connections settings row on another part of the page
    # — so a failed Add looked like a dead button (her report, 10 Sep).
    if bare:
        # For you's copy: the rows and their feedback line, no card chrome.
        return ('<div class="mttray needs-server">' + "".join(rows) + more
                + '<span class="mshelp" id="mttray-help"></span></div>')
    return ('<section class="mttray needs-server"><h2>From your email'
            + hint(AG.say("Tasks proposed from the senders you whitelisted. Add puts "
                          "one in your inbox for Claude to file; No drops it and "
                          "teaches the reader what not to suggest again. The grey "
                          "line under each is the email itself; click it to open "
                          "the message in your mail."))
            + f'</h2>{"".join(rows)}{more}'
            '<span class="mshelp" id="mttray-help"></span></section>')


def mailcheck_button(cfg=None):
    """The task-mail check, for Today and the School tab: (html, days since
    the last check). Empty when no sender is whitelisted. The settings row
    under the hood keeps its own copy; this one exists because nobody opens
    the gear to read their mail (5 Oct: unchecked for four weeks)."""
    try:
        import mail_tasks as _mt
        if not _mt.senders(cfg):
            return "", None
        last = _mt.last_check()
    except Exception:                                    # noqa: BLE001
        return "", None
    days = (date.today() - last).days if last else None
    when = ("last checked " + ago(days)) if days is not None else "never checked"
    return ('<button class="ghostbtn mtcheck" title="Reads mail from the senders'
            ' you whitelisted and suggests tasks for you to accept. Asks for'
            ' your fingerprint.">Check mail for tasks</button>'
            '<span class="mshelp mtcheckhelp">%s</span>' % e(when)), days


def _school_tray(cfg=None, part="all"):
    """Dates found in the class slides, waiting on a yes or a no.

    Blackboard has no API worth having and the syllabi carry almost no dates —
    they sit in the decks. school.py reads whatever lands in the class folder
    and proposes what looks like a commitment; this is where she answers.
    Accepting writes a line to the inbox, the same road as anything else."""
    try:
        import school as _sc
        pend = _sc.pending()
    except Exception:                                    # noqa: BLE001
        pend = []
    # The card stays even with an empty tray: when a deck lands mid-week she
    # needs a way to say "read them now", and a card that only appears when
    # the brain already found something is no way at all.
    seen, last = 0, ""
    try:
        with open(os.path.join(BRAIN, ".school.json")) as fh:
            seen = len((json.load(fh).get("seen") or {}))
        last = ago((date.today() - date.fromtimestamp(os.path.getmtime(
            os.path.join(BRAIN, ".school.json")))).days)
    except Exception:                                    # noqa: BLE001
        pass
    # What the button does, said plainly: school.scan() reads only the decks
    # that are new or changed since the last look, and proposes the dates in
    # them. "Read the class slides now" sounded like all of them, every time.
    scan = ('<div class="scacts"><button class="ghostbtn" id="scscan"'
            ' title="Reads any deck that is new or changed in your class'
            ' folder and suggests the dates in it, and any new reading, due'
            ' at the next class. Nothing is filed until you say yes.">'
            'Check the class folder</button>'
            '<span class="mshelp" id="scscanhelp">%s</span>%s</div>'
            % (e(" \u00b7 ".join(x for x in (
                ("%d files read" % seen) if seen else "",
                ("last looked %s" % last) if last else "") if x)),
               mailcheck_button(cfg)[0]))
    # Since 28 Sep the suggestions live in For you (part="rows") and the
    # School tab keeps only the way to ask for a fresh read (part="scan").
    if part == "rows" and not pend:
        return ""
    # One slim line, not a card: a heading and one button in a big box was
    # most of the tab's first screen (page review S4, 28 Sep).
    if part == "scan" or not pend:
        return ('<section class="mttray scslides needs-server">'
                '%s</section>' % scan)

    def _row(s):
        due = (f' <span class="mtdue">due {e(s["due"])}</span>'
               if s.get("due") else "")
        guess = ((" · from a %d deck, probably last year's date"
                  % s["old_year"]) if s.get("old_year")
                 else "" if s.get("exact") else " · year inferred")
        src = f'{s.get("course", "")}{guess}'
        return ('<div class="mtrow"><span class="mttask">'
                f'{e(s["task"])}{due}<i title="{e(s.get("line", ""))}">'
                f'{e(src)}</i></span>'
                f'<button class="mini" data-scact="accept" data-scid="{e(s["id"])}">'
                "Add</button>"
                f'<button class="mini" data-scact="dismiss" data-scid="{e(s["id"])}">'
                "No</button></div>")

    _today = date.today().isoformat()
    fresh = [s for s in pend if not (s.get("due") and s["due"] < _today)]
    stale = [s for s in pend if s.get("due") and s["due"] < _today]
    rows = [_row(s) for s in fresh[:12]]
    if stale:
        rows.append('<details class="ghost mtstale"><summary>'
                    f'{len(stale)} whose date has passed</summary>'
                    + "".join(_row(s) for s in stale[:12]) + "</details>")
    if part == "rows":
        return ('<div class="mttray needs-server">' + "".join(rows)
                + '<span class="mshelp" id="sctray-help"></span></div>')
    return ('<section class="mttray needs-server"><h2>Found in your class folder'
            + hint(AG.say("Dates the brain read out of the decks in your class "
                          "folder, and readings that arrived there since. Add puts "
                          "a date in your inbox for Claude to file and a reading "
                          "straight on your list, due at the next class; "
                          "No drops it. Hover the grey line to see the slide's own "
                          "words. Check any marked \"year inferred\": the "
                          "slide gave a day and a month but no year."))
            + f'</h2>{"".join(rows)}'
            + scan
            + '<span class="mshelp" id="sctray-help"></span></section>')


SCHOOL_WS = ("School", "Venture", "Class lead")

# Words that mark a calendar entry as school rather than life. Course names
# come from her class folder; these cover what a course name doesn't — the
# programme itself, her project, and the accelerator stream. The school's own name
# is config (school.names), matched as a whole word: as a substring, a
# short one fires inside ordinary words, and a dentist checkup became class.
_SCHOOL_MARKS = ("mba", "studio course", "venture", "venture lab",
                 "accelerator", "startup accelerator", "capstone", "e-lab", "elab")
_SCHOOL_NAME_RX = []


def _school_name_rx():
    if not _SCHOOL_NAME_RX:
        _SCHOOL_NAME_RX.append(re.compile(
            "|".join(r"\b" + re.escape(n) + r"\b" for n in M.school_names())
            or r"(?!)"))
    return _SCHOOL_NAME_RX[0]


def _is_school_event(title, known=None):
    """True for a class or a school commitment, false for lunch with a friend.

    Without this the School views listed every calendar entry, so a lunch sat
    between Entrepreneurial Finance and Managing Innovation as if it were a
    session."""
    low = (title or "").lower()
    if any(m in low for m in _SCHOOL_MARKS) or _school_name_rx().search(low):
        return True
    for c in (known or []):
        if sum(1 for w in c["words"] if w in low) >= 2:
            return True
        if any(p in low for p in c["profs"]):
            return True
    return False


def area_groups(items, area_of, sort_key, row, cap=3, group_key=None,
                line_area=None):
    """A mixed task list, split into one subsection per area of her life.

    Her rule (16 Sep 2026): in one ranked list a busy area crowds out the
    single important task from another part of her life — eight Venture
    rows and the one class-lead deadline scrolls away. So every area gets its
    own small heading, the areas lead with their most pressing item (the
    same order "Front by front" uses), and when more than one area shares a
    list each shows only its top few, with the rest folded under it. A list
    holding a single area is never capped: there is nothing to protect.

    Each heading carries its subway line (lines.py) for the New York style;
    `line_area` names the real area when the groups are workstreams."""
    taken = set()
    groups = {}
    for it in items:
        groups.setdefault(area_of(it) or "Other", []).append(it)
    if not groups:
        return ""
    for g in groups.values():
        g.sort(key=sort_key)
    order = sorted(groups, key=(lambda a: group_key(groups[a])) if group_key
                   else (lambda a: sort_key(groups[a][0])))
    limit = cap if len(groups) > 1 else None
    out = []
    for a in order:
        g = groups[a]
        shown, rest = (g[:limit], g[limit:]) if limit else (g, [])
        _la = line_area(g[0]) if line_area else a
        html = ('<div class="agroup"%s><h3 class="area agh"%s>%s'
                '<span class="agn">%d</span></h3><ul class="tasks">%s</ul>'
                % (LN.colour_attr(_la), LN.attrs(_la, a, taken), e(a), len(g),
                   "".join(row(it) for it in shown)))
        if rest:
            html += ('<details class="ghost amore"><summary>'
                     '<span class="amc">Show %d more</span>'
                     '<span class="amo">Show fewer</span></summary>'
                     '<ul class="tasks">%s</ul></details>'
                     % (len(rest), "".join(row(it) for it in rest)))
        out.append(html + "</div>")
    return "".join(out)


def _school_open():
    """Every open school task with its workstream, enriched by model.py.

    One reader for the School tab and the Today strip, so the two can never
    disagree about what is due."""
    out = []
    ws = M.load()
    if PRESENTING:
        # A fresh load skipped the filter, and the School tab printed every
        # task's notes on the projector (9 Oct audit).
        import privacy as _PRIV
        ws = _PRIV.present_filter(ws, M.load_people(), PRESENTING["areas"])[0]
    for w in ws:
        if not w.get("name", "").startswith(SCHOOL_WS):
            continue
        # A snoozed front is out of every list until its wake date, and a
        # closed one is closed: the School tab listed both (9 Oct).
        if not w.get("live", True):
            continue
        for t in w.get("tasks") or []:
            if t.get("done") or t.get("dropped") or t.get("parked"):
                continue
            out.append((w, t))
    return out


def _ws_short(name):
    if name.startswith("Venture"):
        return "Venture"
    if name.startswith("Class lead"):
        return "Class lead"
    return "Courses"


def _task_head(text):
    """What a school row shows: the instruction, not the reasoning after it.

    These tasks were filed with their why attached, which is right in the
    file and wrong on a card — her rule is an imperative and one faint line.
    The full text stays in the tooltip, and the tick is still keyed to it."""
    t = re.sub(r"\s*\((?:class|urgent)\)", "", text or "").strip()
    head = re.split(r"\s+[—–]\s+", t)[0].strip()
    return head if len(head) >= 14 else t


def _school_row(w, t, chip=True):
    """A school task as the page's own task row, made quieter.

    Tickable, and the tick is keyed to the full text, so only what is shown
    changes: the instruction without its reasoning (full line in the tooltip),
    and one faint line under it for when it is due and how long it takes —
    "Tomorrow · 1h" — instead of an estimate pill in the sentence and a red
    "due in 1d" under every row of a week that is, by definition, soon."""
    name = w.get("name", "")
    row = taskrow(t, src="workstreams.md", ws=name, show_ws=chip,
                  ws_label=_ws_short(name))
    full = iso_prose(linknames(e(t["text"])))
    short = iso_prose(linknames(e(_task_head(t["text"]))))
    if short != full:
        row = row.replace('<span class="ttext">' + full,
                          '<span class="ttext" title="%s">' % e(t["text"])
                          + short, 1)
    dur = ""
    if t.get("est") and not t.get("done"):
        dur = M.fmt_dur(t["est"])
        row = row.replace('<span class="test">%s</span>' % e(dur), "", 1)
    meta = " · ".join(x for x in (_due_words(t), dur) if x)
    if t.get("due_days") in (0, 1):
        row = row.replace('<li class="', '<li class="tdue-now ', 1)
    m = re.search(r'<span class="tnote tdue">.*?</span>', row)
    if m:
        row = (row[:m.start()] + '<span class="tnote tdue">%s</span>' % e(meta)
               + row[m.end():])
    elif meta:
        i = row.find('<span class="ttext"')
        j = row.find('<details class="tctx"', i)
        k = row.find('<span class="rdline', i)
        if k >= 0 and (j < 0 or k < j):
            j = k
        if j < 0:
            j = row.find("</span>", i)
        if i >= 0 and j > i:
            row = row[:j] + '<span class="tnote tdue">%s</span>' % e(meta) + row[j:]
    return row


def _due_words(t):
    """When a task is due, the way she would say it."""
    dd = t.get("due_days")
    if dd is None:
        return ""
    if dd < 0:
        return "%d day%s late" % (-dd, "" if dd == -1 else "s")
    if dd == 0:
        return "Today"
    if dd == 1:
        return "Tomorrow"
    if t.get("due_fuzzy") and t.get("due_label"):
        return str(t["due_label"])
    d = date.today() + timedelta(days=dd)
    if dd < 7:
        return d.strftime("%A")
    return "%d %s" % (d.day, d.strftime("%b"))     # day first: "8 Oct"


def _by_due(pairs):
    return sorted(pairs, key=lambda p: (
        p[1]["due_days"] if p[1].get("due_days") is not None else 9999,
        p[1]["text"]))


def _due_key(p):
    t = p[1]
    return (t["due_days"] if t.get("due_days") is not None else 9999,
            t["text"])


def _front_groups(pairs, cap=3):
    # Fronts in the order "Front by front" ranks them (her Focus and her own
    # word included), each one's tasks by date inside it. Ordering the fronts
    # by their soonest date put Venture's late gate work above the two
    # things she had named first (8 Oct).
    return area_groups(pairs, lambda p: _ws_short(p[0].get("name", "")),
                       _due_key, lambda p: _school_row(p[0], p[1], chip=False),
                       cap=cap,
                       group_key=lambda g: -max(p[0].get("score") or 0
                                                for p in g),
                       line_area=lambda p: p[0].get("area"))


def _school_card(title, pairs, extra_cls=""):
    if not pairs:
        return ""
    return ('<section class="pdtray schoolcard %s"><h2>%s'
            '<span class="sccount">%d</span></h2>%s</section>'
            % (extra_cls, e(title), len(pairs), _front_groups(pairs)))


_SHORT_CLASS = (("entrepreneurial finance", "Entrepreneurial Finance"),
                ("managing innovation", "Managing Innovation"),
                ("innovative marketing", "Innovative Marketing"),
                ("scale", "Scale-up"),
                # before "studio course": the course folder is named for
                # both, and the Backbone is the course; LbD is its option
                ("venture strategy", "Venture Strategy"),
                ("studio course", "Studio Course"),
                ("venture", "Venture"))


_CLASS_NAME_RX = re.compile(
    r"(?i)\b(?:%s|scale-?\s?ups?)\b" % "|".join(
        re.escape(x) for k, s in _SHORT_CLASS if k != "venture"
        for x in (k, s) if x != "scale"))


def _sans_class(text):
    """A school task without its class's name, for the page's one-owner
    register. Two tasks for one class share that name, and the register
    counts one shared long word as the same piece of work: a plan line
    naming Managing Innovation hid tomorrow's readings for it (30 Sep)."""
    return _CLASS_NAME_RX.sub(" ", text or "")


def _short_class(name):
    low = (name or "").lower()
    for key, short in _SHORT_CLASS:
        if key in low:
            return short + (" kick-off" if "kick" in low else "")
    n = name.strip()
    return n if len(n) <= 34 else n[:32].rstrip() + "…"


def _school_events(days):
    """School calendar entries as {day: [(time, short name)]}, deduplicated.

    Her calendar carries each class twice (two feeds, one with the title
    HTML-escaped), so names are unescaped and deduplicated per day."""
    import html as _h
    # The calendar is read only when she switched it on. These two school
    # helpers used to ask it regardless, so a brain with the calendar off
    # still read the Mac's Calendar app (found 28 Sep).
    if not M.load_config().get("calendar"):
        return {}
    try:
        import calendar_read
        import school as _sc
        known = _sc.courses()
        evs = calendar_read.events(days)
    except Exception:                                    # noqa: BLE001
        return {}
    out = {}
    for when, title in evs:
        t = _h.unescape(_h.unescape(title or ""))
        if not _is_school_event(t, known):
            continue
        name = _short_class(re.split(r"\s+-\s+", t)[0])
        day, hm = str(when)[:10], str(when)[11:16]
        got = out.setdefault(day, [])
        # A twin is the same class at the same TIME. Matching on the name
        # alone kept only the first session of a block day, so four
        # Scale-up sessions showed as one at 09:40 (her report, 28 Sep).
        if (hm, name) not in got:
            got.append((hm, name))
    return {d: sorted(v) for d, v in out.items()}


def _group_sessions(slots):
    """[(hm, name)] -> [(first hm, name, [every hm])], in day order: a class
    with several sessions in one day reads as one line with all its times."""
    out, where = [], {}
    for hm, name in slots:
        if name in where:
            out[where[name]][2].append(hm)
        else:
            where[name] = len(out)
            out.append((hm, name, [hm]))
    return out


def _term_hero(cfg, today, pairs):
    """The School tab's headline, in the same voice as Today's."""
    now = (cfg or {}).get("now") or {}
    until = M.parse_date(now.get("until", "")) if now.get("until") else None
    if until and until >= today:
        weeks = max(1, -(-(until - today).days // 7))
        head = "%s. %d week%s left." % (now.get("phase") or "This term",
                                       weeks, "" if weeks == 1 else "s")
    else:
        head = "School."
    bits = []
    nxt = [p for p in _by_due(pairs)
           if p[1].get("due_days") is not None and p[1]["due_days"] >= 0
           and "(class)" in p[1]["text"]]
    if nxt:
        dd = nxt[0][1]["due_days"]
        when = ("today" if dd == 0 else "tomorrow" if dd == 1 else
                (today + timedelta(days=dd)).strftime("%A") if dd < 7 else
                "in %d days" % dd)
        name = re.split(r"\s+\(|,\s", _task_head(nxt[0][1]["text"]))[0]
        if len(name) > 48:
            name = name[:48].rsplit(" ", 1)[0] + "\u2026"
        bits.append({"icon": "doc", "text": "%s \u00b7 %s" % (
            name, "%dd" % dd if dd >= 7 else when),
            "title": "Next hand-in: %s, %s" % (name, when)})
    for w in M.load():
        if w.get("name", "").startswith("Venture") and w.get("due"):
            d = M.parse_date(str(w["due"]))
            if d and d >= today:
                bits.append({"icon": "flag",
                             "text": "Jury \u00b7 %dd" % (d - today).days,
                             "title": "Venture jury in %d days" % (d - today).days})
    if until:
        # "term ends", not "ends": Season shows its own end date (the bucket
        # list's, from season.md) and the two read as one contradicting fact.
        bits.append({"icon": "calendar",
                     "text": "term ends %d %s" % (until.day, until.strftime("%b")),
                     "title": "Term ends %s %d %s" % (
                         until.strftime("%a"), until.day, until.strftime("%b"))})
    return ('<h2 class="skinx skinx-greet">%s</h2>' % e(head)
            + glance_row(bits))


def _tracker_card():
    """The shared class sheet's gaps, with one button to copy them.

    It never writes to the sheet — classmates plan around it, so a row lands
    there because she pasted it. Rows she decides the class doesn't need are
    dismissed (kept in config, restorable) and drop out of the copy too."""
    try:
        import tracker as _tr
        if not _tr.sheet_url():
            return ""
        raw = _tr.compare_cached()
        data = _tr.without_dismissed(raw)
        gaps = data.get("missing") or []
        gone = data.get("dismissed_rows") or []
        if not gaps and not gone:
            return ""
        lines = _tr.paste_rows(data=raw)
    except Exception:                                    # noqa: BLE001
        return ""

    def when(g):
        try:
            d = date.fromisoformat(str(g["due"])[:10])
            return "%d %s" % (d.day, d.strftime("%b"))
        except ValueError:
            return str(g.get("due") or "")

    live = "".join(
        '<li data-row="%s"><span>%s</span><i>%s &middot; %s</i>'
        '<button class="scx" data-trkey="%s" title="The class sheet doesn\'t '
        'need this. Leave it out of the copy" aria-label="Dismiss">&times;'
        "</button></li>"
        % (e(line), e(g["assignment"][:90]), e(_short_class(g["course"])),
           e(when(g)), e(_tr.gap_key(g)))
        for g, line in zip(gaps, lines))
    body = ('<ul class="scgaps">%s</ul>' % live if gaps else
            '<p class="scsub">Nothing missing.</p>')
    if gaps:
        body += ('<div class="scacts"><button class="ghostbtn scopy" '
                 'data-rows="%s">Copy %d row%s to paste</button>'
                 '<span class="schelp"></span></div>'
                 % (e("\n".join(lines)), len(gaps), "" if len(gaps) == 1 else "s"))
    if gone:
        body += ('<details class="ghost scgone"><summary>%d dismissed</summary>'
                 '<ul class="scgaps">%s</ul></details>'
                 % (len(gone), "".join(
                     '<li><span>%s</span><i>%s</i><button class="screstore" '
                     'data-trkey="%s" data-restore>Restore</button></li>'
                     % (e(g["assignment"][:90]), e(when(g)), e(_tr.gap_key(g)))
                     for g in gone)))
    return ('<section class="pdtray schoolcard sctracker needs-server">'
            '<h2>Class tracker<span class="sccount">%d</span></h2>'
            '<p class="scsub">Missing from the sheet your classmates use.</p>'
            "%s</section>" % (len(gaps), body))


def _week_rail():
    """This week's classes: a day, then its classes one per line with the
    time in its own column — they used to run together on one wrapped line."""
    ev = _school_events(7)
    if not ev:
        return ""
    today = date.today()
    blocks = ""
    for day in sorted(ev)[:7]:
        try:
            d = date.fromisoformat(day)
        except ValueError:
            continue
        gap = (d - today).days
        label = ("Today" if gap == 0 else "Tomorrow" if gap == 1
                 else "%s %d" % (d.strftime("%a"), d.day))
        slots = "".join(
            '<span class="scslot"><em>%s</em><span>%s%s</span></span>'
            % (e(hm), e(n),
               ('<small class="scthen">then %s</small>'
                % e(" \u00b7 ".join(hms[1:]))) if len(hms) > 1 else "")
            for hm, n, hms in _group_sessions(ev[day]))
        blocks += ('<div class="scday%s"><b>%s</b><div class="scslots">%s</div>'
                   "</div>" % (" sctoday" if gap == 0 else "", e(label), slots))
    return ('<section class="railcard scweek"><h3 class="area">Classes this '
            "week</h3>%s</section>" % blocks)


def _left_out_of_guides():
    """The class files that are not slides, folded under one line. Guides
    are built from slides alone (25 Sep): a case, an article or a guest's
    deck may be something the professor would rather not see in a model, so
    it only goes in when she says so, one file at a time. They are still
    read on this Mac for dates."""
    try:
        import school as _sc
        files = _sc.files()
        extra = _sc.guide_extras()
    except Exception:                                    # noqa: BLE001
        return ""
    rows = []
    for f in sorted(files, key=lambda f: (f["course"], f["name"].lower())):
        low = f["name"].lower()
        if os.path.splitext(low)[1] not in (".pdf", ".pptx") \
                or _sc.is_slides(f["name"]) or "syllabus" in low \
                or "recommended reading" in low or _sc.is_confidential(low):
            continue
        on = f["rel"] in extra
        rows.append(
            '<div class="scbook"><span>%s<i>%s</i></span>'
            '<button class="scbuild needs-server" data-guideadd="%s" '
            'data-on="%s">%s</button></div>'
            % (e(os.path.splitext(f["name"])[0]),
               e(_short_class(f["course"])), e(f["rel"]),
               "0" if on else "1",
               "Take out of the guide" if on else "Add to guide"))
    if not rows:
        return ""
    return ('<details class="scbooks"><summary>Left out of the guides'
            '<b>%d</b></summary>%s</details>' % (len(rows), "".join(rows)))


def _guides_rail():
    """The guides, and the books that don't have one yet.

    Course guides and finished book guides are links. A book being read shows
    how far it has got. The rest sit folded under one line, each with a Build
    button — one at a time, since a book is a few dozen calls against her
    subscription."""
    root = os.path.join(BRAIN, "school", "guides")
    rows = []
    if os.path.isdir(root):
        for course in sorted(os.listdir(root)):
            cdir = os.path.join(root, course)
            if course.startswith(".") or not os.path.isdir(cdir):
                continue
            if os.path.exists(os.path.join(cdir, "_course.html")):
                # The course's own name from its guide data: the folder is a
                # lowercase slug, and a course the short-name list doesn't
                # know ("founders workshop") showed as one.
                title = course.replace("-", " ")
                try:
                    with open(os.path.join(root, ".data", course, "_course.json"),
                              encoding="utf-8") as f:
                        title = json.load(f).get("title") or title
                except (OSError, ValueError):
                    pass
                rows.append('<a href="school/guides/%s/_course.html" target="_blank" '
                            'rel="noopener">%s<i>course guide</i></a>'
                            % (e(course), e(_short_class(title))))
    try:
        import guide as _gd
        books = _gd.book_status()
    except Exception:                                    # noqa: BLE001
        books = []
    busy = any(b["running"] for b in books)
    for bk in books:
        if bk["guide"] and not bk["running"]:
            rows.append('<a href="%s" target="_blank" rel="noopener">%s'
                        "<i>book guide</i></a>" % (e(bk["href"]), e(bk["title"])))
    for bk in books:
        if bk["running"]:
            rows.append('<div class="scbuilding" data-book="%s"><span>%s</span>'
                        "<i>%s</i></div>" % (e(bk["slug"]), e(bk["title"]),
                                             e(bk["stage"] or "Starting")))
    # The other kind of guide — the book on its own terms — is a second row
    # per book, which would double this card. Folded, it stays one line.
    gen = [bk for bk in books if bk.get("general")]
    if gen:
        rows.append(
            '<details class="scbooks"><summary>The books on their own terms'
            "<b>%d</b></summary>%s</details>"
            % (len(gen), "".join(
                '<a href="%s" target="_blank" rel="noopener">%s'
                "<i>the book itself</i></a>" % (e(bk["general_href"]),
                                                e(bk["title"]))
                for bk in gen)))
    rows.append(_left_out_of_guides())
    todo = [bk for bk in books if not bk["guide"] and not bk["running"]]
    if todo:
        items = "".join(
            '<div class="scbook"><span>%s%s</span>'
            '<button class="scbuild" data-bookbuild="%s"%s>%s</button></div>'
            % (e(bk["title"]),
               ('<i>%s</i>' % e(bk["author"])) if bk["author"] else "",
               e(bk["slug"]), " disabled" if busy else "",
               "Try again" if bk["failed"] else "Build")
            for bk in todo)
        rows.append('<details class="scbooks"><summary>Guides for the other books'
                    '<b>%d</b></summary>%s<p class="scbhelp">%s</p></details>'
                    % (len(todo), items,
                       "One is being built. The next can start when it's done."
                       if busy else
                       "Reads the book, then writes the guide. About ten minutes."))
    if not rows:
        return ""
    return ('<section class="railcard scguides needs-server">'
            '<h3 class="area">Guides</h3>%s</section>' % "".join(rows))


def _class_recordings_rail():
    """This term's class recordings, newest first: the class, the day, and
    the transcript one tap away. The twice-daily pass names each one for the
    session on her calendar (transcribe.py); the transcripts stay in the
    brain, because her class folder is read-only."""
    root = os.path.join(BRAIN, "transcripts")
    try:
        import docs as _dc
        names = sorted(os.listdir(root), reverse=True)
    except Exception:                                    # noqa: BLE001
        return ""
    rows = []
    for fn in names:
        if not fn.endswith(".md") or len(rows) >= 8:
            continue
        p = os.path.join(root, fn)
        try:
            with open(p, encoding="utf-8") as f:
                head = f.read(800)
        except OSError:
            continue
        fm = dict(re.findall(r"^(class|session|minutes):[ \t]*(.*)$", head, re.M))
        if not fm.get("class"):
            continue
        try:
            d = datetime.strptime(fm.get("session", "")[:16], "%Y-%m-%d %H:%M")
            when = "%s %d %s" % (d.strftime("%a"), d.day, d.strftime("%b"))
        except ValueError:
            when = ""
        try:
            mins = "%d min" % round(float(fm.get("minutes") or 0))
        except ValueError:
            mins = ""
        rows.append('<div class="screc"><span>%s<i>%s</i></span>'
                    '<button class="scbuild" data-openfile="%s">Open</button>'
                    "</div>" % (e(_short_class(fm["class"])),
                                e(" \u00b7 ".join(x for x in (when, mins) if x)),
                                e(_dc._id(p))))
    if not rows:
        return ""
    return ('<section class="railcard scguides needs-server">'
            '<h3 class="area">Class recordings</h3>%s</section>' % "".join(rows))


def _recordings_rail():
    """The meeting recordings sitting in the projects' own folders.

    They stay where she and her team keep them; this only says which ones
    have a transcript beside them and starts the ones that do not. Nothing
    transcribes itself: it is twenty minutes of GPU and her call."""
    try:
        import transcribe as TR
        items = TR.meetings()[:8]
    except Exception:                                    # noqa: BLE001
        return ""
    if not items:
        return ""
    busy = any(m["running"] for m in items)
    rows = []
    for m in items:
        mins = ("%g min" % m["minutes"]) if m["minutes"] else ""
        try:                        # day first on the page: "23 Sep"
            wd = date.fromisoformat(m["when"][:10])
            when = "%d %s" % (wd.day, wd.strftime("%b"))
        except (ValueError, TypeError):
            when = m["when"][:10]
        meta = " &middot; ".join(x for x in (when, mins) if x)
        if m["running"]:
            rows.append('<div class="scbuilding" data-rec="%s"><span>%s</span>'
                        "<i>%s</i></div>"
                        % (e(m["path"]), e(m["name"]), e(m["stage"] or "starting")))
        elif m["transcript"]:
            rows.append('<div class="screc"><span>%s<i>%s &middot; transcript '
                        'beside it</i></span>'
                        '<button class="scbuild" data-reveal="%s">Show it</button>'
                        "</div>" % (e(m["name"]), meta, e(m["transcript"])))
        else:
            rows.append('<div class="screc"><span>%s<i>%s</i></span>'
                        '<button class="scbuild" data-transcribe="%s"%s>%s</button>'
                        "</div>" % (e(m["name"]), meta, e(m["path"]),
                                    " disabled" if busy else "",
                                    "Try again" if m["failed"] else "Transcribe"))
    note = ("One is running. The next can start when it is done."
            if busy else
            "Runs on this Mac, about five minutes per half hour of audio.")
    return ('<section class="railcard scguides needs-server">'
            '<h3 class="area">Recordings</h3>%s'
            '<p class="scbhelp">%s</p></section>' % ("".join(rows), note))


def school_view(cfg=None):
    """The School tab: the term in one place, for as long as the term lasts.

    Every task appears once, grouped by when it is due, with its front as a
    chip — Venture, class lead or courses. Built from the page's own parts
    (task rows, cards, the Today grid) so the skin styles it like everything
    else."""
    today = date.today()
    pairs = _school_open()
    late, week, soon, later = [], [], [], []
    for p in _by_due(pairs):
        dd = p[1].get("due_days")
        if dd is None or dd > 21:
            later.append(p)
        elif dd < 0:
            late.append(p)
        elif dd <= 7:
            week.append(p)
        else:
            soon.append(p)
    main = [_term_hero(cfg, today, pairs),
            _school_tray(cfg, part="scan"),
            _school_card("Late", late, "sclate"),
            _school_card("This week", week),
            _school_card("Next two weeks", soon),
            _tracker_card()]
    if later:
        main.append('<details class="ghost schoolmore"><summary>Later this '
                    "term &middot; %d</summary>%s</details>"
                    % (len(later), _front_groups(later, cap=None)))
    rail = [_week_rail(), countdown_card(today), _class_recordings_rail(),
            _recordings_rail(), _guides_rail()]
    return ('<div class="todaygrid schoolview"><div class="todaymain">%s</div>'
            '<aside class="todayrail">%s</aside></div>'
            % ("".join(m for m in main if m), "".join(r for r in rail if r)))


def _classes_today(cfg=None):
    """Today's classes, each with its guide if one exists.

    The calendar already holds the whole term and the page was not using it
    for this. Between sessions the question is "what am I in next, and where
    is the material" — two clicks that should be none."""
    if not M.load_config().get("calendar"):
        return ""                     # off means off: never read the calendar
    try:
        import calendar_read
        evs = calendar_read.events(1)
    except Exception:                                    # noqa: BLE001
        return ""
    import html as _h
    seen, rows = set(), []
    guides = {}
    groot = os.path.join(BRAIN, "school", "guides")
    if os.path.isdir(groot):
        for course in os.listdir(groot):
            if course.startswith("."):
                continue
            cdir = os.path.join(groot, course)
            if not os.path.isdir(cdir):
                continue
            for fn in sorted(os.listdir(cdir)):
                if fn.endswith(".html"):
                    guides.setdefault(course, []).append(
                        ("school/guides/%s/%s" % (course, fn), fn[:-5]))
    try:
        import school as _sc
        known = _sc.courses()
    except Exception:                                    # noqa: BLE001
        known = []

    times = {}
    for when, title in evs:
        t = _h.unescape(title or "")
        if _is_school_event(t, known):
            nm = re.split(r"\s+-\s+", t)[0].strip().lower()
            hm = str(when)[-5:]
            if nm and hm not in times.setdefault(nm, []):
                times[nm].append(hm)
    for when, title in evs:
        t = _h.unescape(title or "")
        if not _is_school_event(t, known):
            continue
        name = re.split(r"\s+-\s+", t)[0].strip()
        if not name or name.lower() in seen:
            continue
        seen.add(name.lower())
        # Which course folder is this, so the right guides attach.
        low = name.lower()
        slug = ""
        for c in known:
            if sum(1 for w in c["words"] if w in low) >= 2:
                slug = re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-",
                                                 c["name"].lower())).strip("-")
                break
        link = ""
        if slug and guides.get(slug):
            href, label = guides[slug][-1]
            link = ('<a href="%s" target="_blank" rel="noopener">guide</a>'
                    % e(href))
        rows.append('<div class="mtrow"><span class="mttask">%s'
                    '<i>%s</i></span>%s</div>'
                    % (e(name[:70]),
                       e(" \u00b7 ".join(sorted(times.get(name.lower())
                                                 or [str(when)[-5:]]))), link))
    if not rows:
        return ""
    return ('<section class="mttray"><h2>Today'
            + hint("From your calendar, with the guide for that class when "
                   "one has been built.")
            + "</h2>%s</section>" % "".join(rows[:8]))


def _guides_card(cfg=None):
    """The class guides, openable from here.

    They are single files next to the page, so a plain relative link opens
    one in the same browser — which is the whole point of building them as
    HTML rather than as notes in a folder."""
    root = os.path.join(BRAIN, "school", "guides")
    if not os.path.isdir(root):
        return ""
    found = []
    for course in sorted(os.listdir(root)):
        # .data holds the cached content the guides are rendered from — a
        # sibling of the courses, not one of them.
        if course.startswith("."):
            continue
        cdir = os.path.join(root, course)
        if not os.path.isdir(cdir):
            continue
        for fn in sorted(os.listdir(cdir)):
            if not fn.endswith(".html"):
                continue
            full = os.path.join(cdir, fn)
            title = fn[:-5].replace("-", " ")
            try:
                with open(full, encoding="utf-8") as f:
                    head = f.read(3000)
                m = re.search(r"<title>(.*?)(?: &mdash; | — )", head, re.S)
                if m:
                    title = m.group(1).strip()
                mt = os.path.getmtime(full)
            except OSError:
                mt = 0
            found.append((mt, course, title,
                          "school/guides/%s/%s" % (course, fn)))
    if not found:
        return ""
    found.sort(reverse=True)
    # The whole-course guide leads its course: in December that is the one
    # she opens, and a session guide is what she opens the week of the class.
    found.sort(key=lambda r: (0 if r[3].endswith("_course.html") else 1))
    rows = "".join(
        '<div class="mtrow"><span class="mttask">'
        '<a href="%s" target="_blank" rel="noopener">%s</a>'
        "<i>%s</i></span></div>"
        % (e(href),
           e("%s: everything so far" % course.replace("-", " ").title()
             if href.endswith("_course.html") else title),
           e(course.replace("-", " ")))
        for _, course, title, href in found[:10])
    return ('<section class="mttray"><h2>Class guides'
            + hint("Built from the slides and your own notes on that class. "
                   "They open in a new tab and work offline.")
            + "</h2>%s</section>" % rows)


def _mailtasks_row(cfg, have_account=True):
    """Task suggestions from whitelisted mail. The whitelist is hers, the
    reader has no tools, and nothing moves without her Accept — the full
    boundary is in mail_tasks.py and decisions.md (2026-09-08)."""
    if not have_account:
        return ""
    try:
        import mail_tasks as _mt
        allowed = _mt.senders(cfg)
        pend = _mt.pending()
    except Exception:                                    # noqa: BLE001
        allowed, pend = [], []
    on = bool(allowed)
    # The suggestions themselves live on Today (_mailtasks_tray) — a queue
    # waiting on her is not a setting. Here, just how many are waiting.
    tray = (f'<span class="mrfound">{len(pend)} waiting on Today.</span>'
            if pend else "")
    chips = "".join(
        f'<span class="mtchip">{e(s)}<button class="mtx" data-mtrm="{e(s)}" '
        'title="Remove">&times;</button></span>' for s in allowed)
    adder = ('<input id="mt-add" placeholder="name@school.fr or @school.fr" '
             'size="22"><button class="mini" id="mt-addbtn">Allow</button>'
             # No address hunting (9 Oct): who emailed her lately, to tap.
             ' <button class="mini" id="mt-pick" title="Lists who emailed you in'
             ' the last two weeks, from the From lines only. Nothing is saved'
             ' until you press Allow.">Choose from your mail</button>'
             '<div class="mtpick" id="mt-picklist" hidden></div>')
    if on:
        state = (chips + " " + adder
                 + ' <button class="mini" id="mt-check">Check for tasks</button>')
    else:
        state = ("Off. Allow a sender and their mail can suggest tasks. "
                 + adder)
    # Where the bodies go is the cost of this row, so it names the real
    # reader: Claude unless config routes the job to a local model.
    _llm = (cfg or {}).get("llm") or {}
    local = (_llm.get("provider") == "ollama"
             and (_llm.get("ollama") or {}).get("model"))
    return (
        '<div class="connrow needs-server"><i class="cdot'
        + (" on" if on else "") + '"></i><b>Task mail</b><span>'
        + state
        + '<span class="mshelp" id="mt-help"></span>'
        + tray
        + conn_allow(
            ("Set up", "Press Choose from your mail and allow the senders "
             "whose emails carry tasks, or type an address or a whole domain "
             "such as @school.fr. A person with an email address also has a "
             "switch on their card in People. Then press Check for tasks."),
            ("It can", "Read the full text of new mail from the senders you "
             "allow and suggest up to three tasks, which wait on Today for "
             "you to accept or dismiss."),
            ("It can&rsquo;t", "Act on what it reads. The reader has no "
             "tools, and accepting a suggestion adds one line to your inbox. "
             "Mail your server can&rsquo;t confirm really came from that "
             "sender (DMARC) is skipped."),
            ("Risk", ("The emails&rsquo; text is read by the model on this "
                      "Mac. " if local else
                      f"The emails&rsquo; full text goes to {AG.short()} to be read. ")
             + "Anyone on your list, or someone who took over their account, "
             "can put suggestions in front of you, so read each one before "
             "you accept it."),
            ("To stop", "Remove every sender with its &times;."))
        + "</span></div>")


def _calblock_row(cfg):
    """Where "Block time for it…" writes. A local calendar stays on the Mac;
    one belonging to an account is what puts blocks on her phone."""
    try:
        import calendar_write
        cals = calendar_write.calendars(max_age=6 * 3600)
    except Exception:
        cals = []
    if not cals:
        return ""
    cur = (cfg.get("calendar_target") or "").strip()
    opts = ['<option value=""' + ("" if cur else " selected")
            + '>Brain (local to this Mac)</option>']
    for c in cals:
        opts.append(f'<option value="{e(c)}"'
                    + (" selected" if c == cur else "") + f">{e(c)}</option>")
    return ('<span class="msteps">Time blocks go to: '
            f'<select id="cal-target">{"".join(opts)}</select> '
            '<span id="cal-tnote"></span><br>'
            # One sentence here; which calendar reaches her phone, and how
            # to make one, sit in the row's fold (tab_hood, 28 Sep review).
            'The brain only ever adds blocks to it.</span>')


def draftcard(d, email_ready=False, from_addr=""):
    """One thing Claude prepared. The send affordance depends on channel AND
    on the person's circle — an Inner/Close draft gets copy only, by design."""
    kind = d["kind"]
    icon = {"email": "&#9993;", "message": "&#128172;", "form": "&#9999;",
            "note": "&#128196;"}.get(kind, "&#128196;")
    head = e(d["subject"] or d["to"] or d["person"] or d.get("title")
             or kind.title())
    to = []
    if d["to"]:
        to.append("to " + e(d["to"]))
    elif d["person"]:
        to.append("to " + e(d["person"])
                  + (f' <span class="v v-unk">{e(d["circle"])}</span>' if d["circle"] else ""))
    if d.get("channel") == "linkedin":
        to.append("on LinkedIn")
    if d["task"]:
        to.append("for &ldquo;" + e(d["task"][:50]) + "&rdquo;")
    if d.get("stale"):
        to.append(f'<span class="dstale">{e(d.get("stale_why", ""))}</span>')
    seen = M.parse_date(d.get("contact"))
    if seen:
        # In touch since it was written: ask, so the tap records whether
        # drafts get used (model.py --drafts counts them).
        to.append(f'<span class="dseen">in touch {seen.day} {seen:%b} &middot; sent?</span>')
    meta = " &middot; ".join(to)

    # Actions, gated. Email always → open in the owner's own mail client.
    acts = []
    if kind == "email" and not d["to"]:
        # No address on file yet: the mail app opens with the text in it and
        # the To line empty, for her to fill.
        acts.append(f'<button class="act" data-mailto=""'
                    f' data-subject="{e(d["subject"])}" data-file="{e(d["file"])}">'
                    "Open in email</button>")
    if kind == "email" and d["to"]:
        if email_ready and not d["personal"]:
            acts.append(f'<button class="act send" data-sendemail="{e(d["file"])}"'
                        f' data-to="{e(d["to"])}" data-subject="{e(d["subject"])}"'
                        f' data-from="{e(from_addr)}" data-seal="{M.draft_seal(d)}">'
                        'Approve &amp; send</button>')
        acts.append(f'<button class="act{"" if email_ready else " send"}" '
                    f'data-mailto="{e(d["to"])}"'
                    f' data-subject="{e(d["subject"])}" data-file="{e(d["file"])}">'
                    "Open in email</button>")
    if kind == "message" and d["channel"] == "beeper":
        if d["personal"]:
            acts.append('<span class="draftnote">Personal circle: copy it and send it '
                        "yourself</span>")
        else:
            acts.append(f'<button class="act send" data-beeper="{e(d["file"])}"'
                        f' data-who="{e(d["person"])}" data-seal="{M.draft_seal(d)}">'
                        'Review &amp; send via Beeper</button>')
    if d.get("channel") == "linkedin" and MD.safe_href(d.get("linkedin")):
        # LinkedIn has no sending API: copy it, then paste it on their profile.
        acts.append(f'<a class="act" href="{e(MD.safe_href(d["linkedin"]))}" target="_blank"'
                    ' rel="noopener">Open their profile &#8599;</a>')
    acts.append(f'<button class="act" data-copy="{e(d["file"])}">Copy</button>')
    sendable = kind in ("email", "message")
    acts.append(f'<button class="mini" data-draftsent="{e(d["file"])}"'
                + (' data-outreach="1"' if d.get("stage") else "")
                + f'>{"Sent it" if sendable else "Mark done"}</button>')
    if d.get("limit"):
        n = len(d["body"])
        acts.append(f'<span class="dlimit{" over" if n > d["limit"] else ""}"'
                    f' title="LinkedIn cuts a note past {d["limit"]} characters">'
                    f'{n}/{d["limit"]}</span>')
    acts.append(f'<button class="mini" data-draftdiscard="{e(d["file"])}">'
                f'{"Didn&rsquo;t use" if sendable else "Discard"}</button>')

    fn = e(d["file"])
    # The body is directly editable (free) and has a small revise box that
    # sends only this draft to Claude, not the whole brain.
    return (f'<details class="draft" data-file="{fn}"><summary>'
            f'<span class="dkind">{icon}</span>'
            f'<span class="dmain"><span class="dhead">{head}</span>'
            f'<span class="dmeta">{meta}</span></span>'
            '<span class="dedit">Edit</span></summary>'
            f'<div class="dbody" id="d-{fn}" contenteditable="false" '
            f'spellcheck="true">{e("Hidden while presenting." if PRESENTING else d["body"])}</div>'
            '<div class="drevise needs-server">'
            f'<input class="drevin" placeholder="Tell {AG.short()} a change, '
            'like warmer or shorter">'
            f'<button class="mini rev" data-revise="{fn}">Revise</button>'
            '<span class="revnote"></span></div>'
            f'<div class="acts needs-server">{"".join(acts)}'
            f'<button class="mini dsave" data-save="{fn}" hidden>Save edit</button>'
            "</div></details>")


def writingcard():
    """The voice guide, shown and editable on the page.

    Her rules for how anything a third party reads gets written. They were
    only ever visible by opening the file, which meant the one thing she was
    told to edit freely was the one thing she never saw. Rendered here, with
    the raw markdown behind an Edit toggle — the frontmatter is kept by the
    server, so she edits prose, not a header she has to preserve."""
    raw = read("writing-rules.md")
    if not raw.strip():
        return ""
    meta, body = MD.split_frontmatter(raw)
    updated = (meta or {}).get("updated", "")
    when = (f'<span class="wrwhen">last changed {e(dayfirst(str(updated)))}</span>'
            if updated else "")
    # One line under the drafts, not a section of its own: it is the
    # setting behind every card above it, and a heading plus a card for one
    # link was a screen of air on the Claude tab (28 Sep).
    # Copy, on the card's face (her ask, 2 Oct: find it and paste it into
    # other tools). Both versions come from style.py, which takes the
    # brain's own instructions off; the find box's "writing" shortcut
    # copies the same two.
    import style as ST
    full, short = ST.full(), ST.short()
    copy = ""
    if full:
        tips = [("wr-full", "Copy full",
                 f"The whole guide, {len(full.strip()):,} characters. For "
                 "a Claude project, a custom GPT or anything else with room.")]
        if short:
            tips.append(("wr-short", "Copy short",
                         f"{len(short.strip()):,} characters. Fits ChatGPT's "
                         "custom instructions (1,500)."
                         + (" Written before your last rule change: ask "
                            f"{AG.short()} to refresh it." if ST.stale() else "")))
        copy = ('<span class="wrcopy">' + "".join(
            f'<button class="mini" type="button" data-wrcopy="{i}" '
            f'title="{e(t)}">{lbl}</button>' for i, lbl, t in tips)
            + "</span>")
        stash = (f'<textarea id="wr-full" hidden>{e(full)}</textarea>'
                 + (f'<textarea id="wr-short" hidden>{e(short)}</textarea>'
                    if short else ""))
    else:
        stash = ""
    return ('<section id="writing" class="wrmini">' + stash +
            '<details class="wrules"><summary><span class="wrsum">Your '
            'writing style</span>' + copy + when + "</summary>"
            f'<div class="wrbody">{MD.render(body)}</div>'
            '<div class="acts needs-server">'
            '<button class="mini" id="wr-edit">Edit them</button></div>'
            '<form class="wredit needs-server" id="wr-form" hidden>'
            f'<textarea id="wr-text" spellcheck="true">{e(body.strip())}</textarea>'
            '<div class="acts"><button type="submit" class="act send">Save</button>'
            '<button type="button" class="mini" id="wr-cancel">Cancel</button>'
            '<span class="wrnote" id="wr-note"></span></div></form>'
            "</details></section>")


def dayword(n):
    """"1 day", "2 days". Every count on this page had `{n} days` hardcoded,
    so a horizon touched yesterday read "1 days untouched"."""
    n = abs(int(n or 0))
    return f"{n} day" + ("" if n == 1 else "s")


def span(n):
    """A gap as a glance: 3d, 5w, 4mo, 2y. For rows where the number is the
    fact and the words around it were only reading (28 Sep)."""
    n = abs(int(n or 0))
    if n < 28:
        return f"{n}d"
    if n < 61:
        return f"{round(n / 7)}w"
    if n < 330:
        return f"{round(n / 30.4)}mo"
    return f"{max(1, round(n / 365))}y"


def ago(days):
    """A last-spoke gap in words a person actually uses. '157 days' is a number
    you have to decode; '5 months ago' you just feel."""
    if days is None:
        return ""
    if days == 0:
        return "today"
    if days == 1:
        return "yesterday"
    if days < 14:
        return f"{days} days ago"     # "3d ago" was a fifth way of writing it
    if days < 61:
        w = round(days / 7)
        return f"{w} week{'s' if w != 1 else ''} ago"
    if days < 330:                    # 330+ says "a year", never "12 months"
        mo = round(days / 30)
        return f"{mo} month{'s' if mo != 1 else ''} ago"
    y = max(1, round(days / 365))
    return f"{y} year{'s' if y != 1 else ''} ago"


def rhythm_word(label):
    """A person's rhythm as it reads after a time: "monthly", or "every 3
    days" — "today · 3 days" read as two gaps, not a gap and a rhythm."""
    label = (label or "").strip()
    if label in ("no rhythm set", "no set rhythm"):
        return ""
    return f"every {label}" if label[:1].isdigit() else label


def day_month(iso):
    """'2026-10-05' as '5 Oct', the way every visible date on the page reads."""
    try:
        d = date.fromisoformat(iso)
    except (TypeError, ValueError):
        return iso or ""
    return f"{d.day} {d:%b}"


def _avatar(name, drag=False):
    """The real face when the Beeper sync has cached one (brain/avatars/,
    local copies of Beeper's own media cache); otherwise the initial on a
    hue that is stable per person, so the eye learns 'the green M is Maman'
    and scanning replaces reading.

    `drag=True` makes the face itself the handle for moving that person to
    another group. Rows ask for it; shelf faces do not, because there the
    whole button is the handle and a draggable inside a draggable is a
    coin-toss over which one the browser picks up.
    """
    import unicodedata
    import zlib
    # An <img> is natively draggable and would otherwise drag its own file
    # URL, so the attribute is spelled out either way — off for shelf faces.
    dr = (f' draggable="true" data-dragname="{e(name)}"' if drag
          else ' draggable="false"')
    # Slug must stay identical to beeper.avatar_slug — same person, same file.
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^A-Za-z0-9]+", "-", s).strip("-").lower() or "x"
    hue = zlib.crc32(name.encode("utf-8")) % 360
    init = next((ch for ch in name if ch.isalpha()), "?").upper()
    for ext in (".jpg", ".png", ".webp", ".gif"):
        if os.path.exists(os.path.join(BRAIN, "avatars", slug + ext)):
            # The photo sits ON its initial rather than instead of it. A
            # lazy photo that has not arrived yet (every face below the fold,
            # and every face in a screenshot) was a blank beige disc that
            # read as a broken image (28 Sep).
            return (f'<span class="pav pavph{" pavdrag" if drag else ""}"'
                    f' style="--pavh:{hue}"{dr}>{e(init)}'
                    f'<img class="pavimg" src="avatars/{slug}{ext}" alt=""'
                    ' width="30" height="30" loading="lazy" draggable="false">'
                    "</span>")
    return (f'<span class="pav{" pavdrag" if drag else ""}"'
            f' style="--pavh:{hue}"{dr}>{e(init)}</span>')


def shelf(group, own=False):
    """A circle as a shelf of faces — the design's glance layer. Steady on
    the left, slipping on the right, so who needs you is a shape rather
    than a paragraph. It sits ABOVE the rows rather than replacing them:
    the rows carry every control (spoke, hold, rhythm, merge) and a face
    the size of a thumbnail is a place to look, not a place to work.

    One deliberate departure from the mock: the lapsed do NOT fade. Fading
    them would hide the answer to the only question this page asks; they
    keep the state colour instead, which is the language everywhere else.

    `own=True` is a circle with no rhythm of its own, where anyone late is
    late against the rhythm set on them.
    """
    if len(group) < 3:
        return ""                     # three faces is a row, not a shelf
    def rank(p):
        return (2 if p["owed"] else 1 if p["overdue"] else 0,
                p.get("lapse_ratio") or 0, p["name"].lower())
    faces = []
    for p in sorted(group, key=rank):
        # The caption has to explain the ORDER, or the shelf looks broken:
        # someone four days into a quarterly rhythm is steadier than someone
        # two days into a weekly one, and "spoke 4d ago" next to "spoke 2d
        # ago" reads as a sorting bug unless the rhythm is on show.
        # One way of writing time on the whole page (28 Sep): "3 days ago",
        # "4 months ago", with the rhythm after a dot. The ring's colour says
        # late; the words say how long and against what.
        rhy = rhythm_word(p.get("every_label"))
        tip = ""
        if p.get("held"):
            st, why = "held", f'on hold until {day_month(p.get("hold", ""))}'
        elif p["owed"]:
            # The flag is ball-on-her: SHE owes them (it said "owes you").
            st, why = "owed", "you owe a reply"
        elif p["overdue"]:
            gap = ago(p["days_since"])
            st, why = "late", (f"{gap} · {rhy}" if rhy else gap)
            tip = ", past their rhythm"
        elif p["days_since"] is None:
            st, why = "ok", "never logged"
        else:
            gap = ago(p["days_since"])
            st, why = "ok", (f"{gap} · {rhy}" if rhy else f"spoke {gap}")
        # A face with its name and where it stands — the design's shelf reads
        # as people, not as beads. Beyond a dozen the shelf folds, because a
        # 164-strong circle is a wall, not a glance.
        slipping = "1" if ((p["owed"] and not p.get("held"))
                           or M.is_past_rhythm(p)) else "0"
        faces.append(
            f'<button class="shface sh-{st}" data-shjump="{e(p["name"])}"'
            f' data-slip="{slipping}" draggable="true"'
            f' title="{e(p["name"])}: {e(why)}{tip}. '
            'Drag onto another group to move them.">'
            + _avatar(p["name"])
            + f'<span class="shname">{e(p["name"])}</span>'
            + f'<span class="shwhy">{e(why)}</span>'
            + "</button>")
    # Said as the two things it counts. "9 of 175 need you" under a "no
    # rhythm" pill read as a contradiction: those nine carry a rhythm of
    # their own, set on the person rather than the circle.
    n_owed = sum(1 for p in group if p["owed"] and not p.get("held"))
    n_late = sum(1 for p in group if M.is_past_rhythm(p))
    n_need = n_owed + n_late
    shown, rest = faces[:12], faces[12:]
    more = (f'<button class="shmore" data-shmore>+{len(rest)} more</button>'
            if rest else "")
    hidden = (f'<span class="shrest" hidden>{"".join(rest)}</span>' if rest else "")
    parts = ([f"you owe {n_owed} a reply"] if n_owed else []) + (
        [f"{n_late} past their {'own ' if own else ''}rhythm"] if n_late else [])
    note = " &middot; ".join(parts) or "all steady"
    return (f'<div class="shelf" data-need="{n_need}">'
            f'<div class="shrow">{"".join(shown)}{hidden}{more}</div>'
            f'<p class="shnote">{note}'
            '<button class="shlist" data-shlist>read as a list</button>'
            "</p></div>")


_MT_STATE = {}


def _mt_state():
    """(has a mail account, the task-mail senders), read once per config
    change: personrow runs for every person on every build."""
    try:
        mt = os.path.getmtime(os.path.join(BRAIN, "config.json"))
    except OSError:
        mt = 0
    if _MT_STATE.get("mt") != mt:
        try:
            import email_send as _es
            import mail_tasks as _mtk
            _MT_STATE.update(mt=mt, val=(bool(_es.accounts()),
                                         {x.lower() for x in _mtk.senders()}))
        except Exception:                                # noqa: BLE001
            _MT_STATE.update(mt=mt, val=(False, set()))
    return _MT_STATE["val"]


def _mt_person_btn(p):
    """Read their emails for tasks (9 Oct): a person's own switch for task
    mail, so their address never has to be typed. Only with a mail account."""
    ems = [x for x in (p.get("emails") or []) if "@" in x]
    has, allowed = _mt_state()
    if not has:
        return ""
    if not ems:
        # No address filed yet: the first tap asks for it, then files it.
        return (f'<button class="act" data-mtperson="{e(p["name"])}" data-on="1"'
                ' data-needaddr="1" title="Their emails can suggest tasks, which'
                ' wait on Today for your yes. Asks for their address the first'
                ' time and files it on their card.">Read their emails for tasks'
                '&hellip;</button>')
    doms = [d for d in {"@" + x.split("@", 1)[1] for x in ems} if d in allowed]
    if doms and not any(x in allowed for x in ems):
        return (f'<button class="act on" disabled title="Their domain, {e(doms[0])},'
                ' is on your task-mail list">Their emails suggest tasks</button>')
    on = any(x in allowed for x in ems)
    return (f'<button class="act{" on" if on else ""}" data-mtperson="{e(p["name"])}"'
            f' data-on="{0 if on else 1}" title="Their emails can suggest tasks,'
            ' which wait on Today for your yes. The email&rsquo;s text is read by'
            f' {AG.short()} to find them.">'
            + ("&#10003; Their emails suggest tasks" if on else
               "Read their emails for tasks") + "</button>")


def personrow(p, ledger=False):
    """One person. Two registers, one grammar:

    ledger=True (Today's five, Focus) — the debt view: what is owed, how far
    past their own rhythm, a lapse bar you can see without reading, and the
    action to close it right on the row.

    ledger=False (the directory) — a neutral address book: name, when you
    spoke, who they are. It is for FINDING people, so it stays flat —
    the urgency lives in the ledger above."""
    bits = []
    if p.get("held"):
        bits.append('<span class="heldnote">together, on hold until '
                    f'{e(day_month(p["hold"]))}</span>')
    if p["owed"]:
        # "owe a reply · spoke today" reads like a contradiction until you know
        # what the flag means: the last word is THEIRS. Say that when the two
        # collide. (The sync clears this flag by itself once you answer.)
        d = p["days_since"]
        tip = ("you owe them a reply"
               + ("; theirs is the last word" if d is not None and d <= 1
                  else f" ({d} days)" if d else ""))
        # Time in the page's one scheme ("3 days ago"), not the glance form
        # ("3d", "11mo") that made Today's five read differently (28 Sep).
        bits.append(f'<b class="dico" title="{tip}">{ico("reply")}'
                    + ("new" if d is not None and d <= 1 else ago(d) if d
                       else "owed") + "</b>")
    # Owed already carries the day count; a clock or "spoke 3 days ago" after
    # it would say the same number twice.
    if p["owed"]:
        pass
    elif p["overdue"]:
        g = ago(p["days_since"]).replace(" ago", "")
        bits.append(f'<span class="dico" title="{g} since you spoke &middot; you'
                    f' wanted {e(p["every_label"])}">{ico("clock")}'
                    f'{ago(p["days_since"])}</span> &middot; '
                    f'{e(rhythm_word(p["every_label"]))}')
    elif p.get("dormant"):
        # Three times past the rhythm: the state of the tie, not a debt.
        bits.append(f'<span class="dico" title="dormant: you wanted '
                    f'{e(p["every_label"])}. One dormant tie comes back each '
                    f'week">{ico("clock")}{ago(p["days_since"])}</span> &middot; '
                    + ("reconnect this week" if p.get("reconnect")
                       else "dormant"))
    elif p["never"]:
        bits.append("never logged"
                    + (f" &middot; {e(rhythm_word(p['every_label']))}"
                       if ledger and rhythm_word(p["every_label"]) else ""))
    elif p["days_since"] is not None:
        d = p["days_since"]
        bits.append("spoke today" if d == 0 else
                    "spoke yesterday" if d == 1 else f"spoke {ago(d)}")
    if p.get("bday_soon"):
        d = p["bday_in"]
        bits.append('<b class="dico" title="birthday">' + ico("cake")
                    + ("today" if d == 0 else "tomorrow" if d == 1
                       else f"in {d} days") + "</b>")
    if p.get("promised"):
        n = len(p["open_promises"])
        bits.append(f"{n} promise{'s' if n != 1 else ''} open")
    if p.get("stage"):
        # Where an outreach stands, as a chip: the words live in the title.
        sdays = p.get("stage_days")
        stip = (f"{p['stage']} {ago(sdays)}" if sdays else p["stage"]) + (
            ", no reply yet. A nudge is ready" if p.get("chase") else "")
        bits.append(f'<span class="pstage st-{p["stage"].replace(" ", "-")}'
                    f'{" chase" if p.get("chase") else ""}" title="{stip}">'
                    f'{e(p["stage"])}'
                    + (f' {sdays}d' if sdays else "") + "</span>")
    why = f'<p class="matters">{e(p["why"])}</p>' if p["why"] else ""
    # Professional block: role at company, a clickable LinkedIn, how/where you
    # met. The networking half of the relationship, when it exists.
    prof = []
    rc = " at ".join(x for x in [p.get("role"), p.get("company")] if x)
    if rc:
        prof.append(f"<b>{e(rc)}</b>")
    if p.get("how"):
        prof.append(e(p["how"]))
    if p.get("met"):
        prof.append("met " + e(p["met"]))
    if MD.safe_href(p.get("linkedin")):
        prof.append(f'<a class="lilink" href="{e(MD.safe_href(p["linkedin"]))}" target="_blank" '
                    f'rel="noopener">LinkedIn &#8599;</a>')
    profline = (f'<p class="prof">{" &middot; ".join(prof)}</p>' if prof else "")
    facts = []
    if p.get("pronouns"):
        facts.append(e(p["pronouns"]))
    for tg in p.get("tags", []):
        facts.append(f'<span class="ptag">{e(tg)}</span>')
    if p.get("where"):
        facts.append(e(p["where"]))
    if p.get("reach"):
        facts.append(f'reach via {e(p["reach"])}')
    if p.get("birthday"):
        # stored "MM-DD"; shown day-first like every date (2000 is a leap
        # year, so a 29 Feb birthday parses)
        facts.append(f"birthday {e(day_month('2000-' + p['birthday']))}")
    factline = (f'<p class="meta">{" &middot; ".join(facts)}</p>' if facts else "")
    # The chat names folded into this person. Without this a merged WhatsApp
    # contact simply vanishes: not in the unsorted list, not findable by the
    # name you knew them under.
    if p.get("also"):
        factline += ('<p class="palso">also answers to '
                     + ", ".join(f"<b>{e(a)}</b>" for a in p["also"])
                     + "</p>")
    promises = ""
    if p.get("promises"):
        promises = ('<ul class="tasks">'
                    + "".join(taskrow(t_, src="people.md") for t_ in p["promises"])
                    + "</ul>")
    # Open tasks elsewhere that name this person — the other half of linking.
    if p.get("mentions"):
        lis = "".join(f'<li>{e(txt)} <span class="mws">&middot; {e(wsn)}</span></li>'
                      for wsn, txt in p["mentions"])
        promises += (f'<div class="pmentions"><p class="meta">Comes up in</p>'
                     f"<ul>{lis}</ul></div>")
    notes = (f'<div class="notes">{MD.render(chr(10).join(p["notes"]))}</div>'
             if p["notes"] else "")
    focus = '<span class="pstar" title="Focus: they come up sooner after a quiet spell">&#9733;</span>' if p["focus"] else ""
    # The tier as a small grey word — only in the ledger, where rows from
    # different circles mix; the directory's rows sit under their own heading.
    tier = (f'<span class="ptier">{e(p["circle"].lower())}</span>'
            if ledger and p["circle"] and p["circle"] != "Everyone else" else "")
    # An owed reply needs attention, but nothing about it is late in the way
    # a passed date is late — it warns, it does not block. sev-cold still
    # carries "gone quiet", which is the same blue everywhere else.
    sev = ("sev-wait" if p["owed"] else
           ("sev-cold" if p["overdue"] or p["never"] else "")) if ledger else ""
    # The lapse in a channel you can see without reading: a thin bar that
    # fills as the debt grows past their own rhythm (full = 3x over).
    pbar = ""
    if ledger and p.get("lapse_ratio"):
        pct = round(min(p["lapse_ratio"], 3.0) / 3.0 * 100)
        pbar = f'<span class="bar pbar"><i style="width:{pct}%"></i></span>'
    # The action, not a label, on the right rail: close the debt from the row.
    act = ""
    # Which template the Write button opens on: a nudge for an ask gone
    # quiet, a thank-you while "Follow up on meeting" is open, a keep-in-touch
    # for the later follow-ups. The dialog still lists them all.
    tpl_use = ""
    if p.get("chase"):
        tpl_use = "nudge"
    else:
        for t_ in p.get("open_promises", []):
            tl = t_["text"].lower()
            if tl.startswith("follow up on meeting"):
                tpl_use = "thanks"
                break
            if tl.startswith(("check back in with", "keep ")):
                tpl_use = "keep"
    if p.get("chase"):
        act = (f'<button class="mini prepl needs-server" data-writeto="{e(p["name"])}"'
               f' data-tpluse="nudge" title="Asked {p.get("stage_days")} days ago, no'
               ' reply: a short nudge, ready to send">Nudge</button>')
    elif p["owed"]:
        act = (f'<button class="mini prepl needs-server" data-replied="{e(p["name"])}"'
               f' title="You answered them. Clears the reply you owed and logs today">'
               "&#10003; Replied</button>")
    elif ledger and (p["overdue"] or p["never"]):
        act = (f'<button class="mini prepl needs-server" data-spoke="{e(p["name"])}"'
               f' title="You spoke to them. Logs today as the last time you spoke">'
               "&#10003; Spoke</button>")
    # Role at company sits under the name so the People page reads as a
    # directory for professional contacts, not just a warmth tracker.
    rowsub = f'<span class="rowsub">{e(rc)}</span>' if rc else ""
    # What the search box looks through besides names: "who do I know at
    # McKinsey" is a company, and "the one from the volleyball dinner" sits in
    # a note. Notes are capped so a long entry doesn't bloat the page.
    find = " ".join(x for x in [p.get("role"), p.get("company"), p.get("how"),
                                p.get("where"), " ".join(p.get("tags", [])),
                                p.get("stage", ""),
                                MD.plain(" ".join(p.get("notes", [])))[:400]] if x)
    return (f'<details class="row person {sev}" data-name="{e(p["name"])}"'
            f' data-find="{e(find.lower())}"'
            f' data-flags="{" ".join(p["flags"])}" data-ball="{p["ball"]}"'
            f' data-focus="{"1" if p["focus"] else "0"}"'
            f' data-places="{e(" | ".join(([p["where"]] if p.get("where") else []) + p.get("tags", [])))}"'
            f' data-also="{e(" | ".join(p.get("also", [])))}">'
            "<summary>"
            + _avatar(p["name"], drag=True) +
            '<span class="rowmain">'
            f'<span class="rowname">{e(p["name"])}{focus}{tier}</span>'
            f'<span class="rowwhy">{" &middot; ".join(bits)}</span>'
            f'{rowsub}'
            "</span>"
            f"{act}{pbar}"
            f'<button class="pmenu needs-server" data-pmenu="{e(p["name"])}"'
            ' aria-label="Rename, merge, archive or delete">&#8943;</button>'
            "</summary>"
            f'<div class="rowbody">{why}{profline}{factline}{promises}{notes}'
            '<div class="acts needs-server">'
            f'<button class="act" data-openchat="{e(p["name"])}" title="Opens your chat '
            'with them in Beeper Desktop without sending anything">Open the chat &#8599;</button>'
            f'<button class="act" data-spoke="{e(p["name"])}">Spoke today</button>'
            + (f'<button class="act" data-unhold="{e(p["name"])}" title="You&rsquo;re '
               'apart again, so their rhythm and owed replies come back">End hold</button>'
               if p.get("held") else
               f'<button class="act" data-hold="{e(p["name"])}" title="For when you&rsquo;re '
               'living or travelling with them: owed replies and their rhythm pause '
               'until the date you pick">Together / hold&hellip;</button>')
            + f'<button class="act" data-writeto="{e(p["name"])}" data-tpluse="{tpl_use}"'
            ' title="Pick a message template; it fills in their name and work">'
            'Write to them</button>'
            + _mt_person_btn(p)
            + f'<button class="act" data-pnote="{e(p["name"])}"><b>+</b> Note</button>'
            + f'<button class="act" data-detail="{e(p["name"])}"><b>+</b> Details</button>'
            f'<button class="act" data-claudetalkperson="{e(p["name"])}"'
            ' title="A live conversation that starts out knowing them. Use it to'
            ' plan what to say or what they&rsquo;d enjoy">Talk it through</button>'
            f'<button class="act" data-promise="{e(p["name"])}"><b>+</b> Promise</button>'
            f'<label class="pcircle">Circle '
            f'<select data-pcircle="{e(p["name"])}">{circleopts_for(p["circle"])}</select>'
            "</label>"
            f'<label class="pcircle" title="Where an outreach to them stands">Stage '
            f'<select data-pstage="{e(p["name"])}"><option value="">none</option>'
            + "".join(f'<option{" selected" if p.get("stage") == st else ""}>{st}</option>'
                      for st in M.STAGES)
            + "</select></label>"
            + f'<button class="act" data-pevery="{e(p["name"])}"'
            f' data-cur="{e("" if p["every_from_circle"] else p["every_label"])}"'
            ' title="This person&rsquo;s own rhythm (&ldquo;3 days&rdquo;, &ldquo;weekly&rdquo;), '
            'which overrides the group&rsquo;s. Leave it empty to use the group&rsquo;s again.">'
            + ("Rhythm: " + e(p["every_label"])
               + ('<span class="rfrom">from ' + e(p["circle"]) + '</span>'
                  if p["every_from_circle"] else
                  ('<span class="rfrom own">set for them</span>'
                   if p["every_label"] != "no rhythm set" else "")))
            + "</button>"
            + (f'<button class="mini pfocus on" data-pfocus="{e(p["name"])}"'
               ' title="Focus is on: they come up sooner after a quiet spell. '
               'Click to stop.">&#9733; Focus</button>' if p["focus"] else
               f'<button class="mini pfocus" data-pfocus="{e(p["name"])}"'
               ' title="Focus brings them up sooner after a quiet spell, without '
               'moving them to a closer circle.">'
               "&#9734; Focus</button>")
            + '<span class="ballgroup" role="group" aria-label="Who owes a message">'
            '<span class="balllabel" title="Who owes whom a reply right now">Reply owed by</span>'
            f'<button class="ball{" on" if p["ball"]=="me" else ""}"'
            f' data-pball="me" data-name="{e(p["name"])}">me</button>'
            f'<button class="ball{" on" if p["ball"]=="them" else ""}"'
            f' data-pball="them" data-name="{e(p["name"])}">them</button>'
            f'<button class="ball{" on" if p["ball"]=="nobody" else ""}"'
            f' data-pball="nobody" data-name="{e(p["name"])}">no one</button>'
            "</span>"
            f'<button class="act right" data-ask="{e(p["name"])}">Tell {AG.short()}</button>'
            "</div></div></details>")


def circleopts_for(current):
    """Circle <option>s for a person row, from config, current one selected."""
    opts = []
    for c in M.circles().values():
        sel = " selected" if c["name"].lower() == (current or "").lower() else ""
        opts.append(f'<option{sel}>{e(c["name"])}</option>')
    if current and current.lower() not in M.circles():
        opts.insert(0, f'<option selected>{e(current)}</option>')
    return "".join(opts)




_STOP = {"with", "from", "that", "this", "your", "into", "about", "them",
         "then", "when", "have", "will", "what", "pour", "dans", "avec",
         "the", "and", "for", "her", "him", "une", "les", "des"}


def _sig_tokens(s):
    """The words that carry a task's identity — lowercase, punctuation off,
    stopwords out. Used to tell whether the hero and the plan agree.

    Bare numbers are out too: every dated task carries its year in the
    "(due 2026-…)" suffix, so "2026" plus one shared word made two
    different readings "the same thing" (30 Sep)."""
    return {t for t in re.findall(r"[a-zà-ÿ0-9€]+", (s or "").lower())
            if len(t) >= 4 and t not in _STOP and not t.isdigit()}


def _same_thing(a, b):
    """Do two strings name the same piece of work? Two shared significant
    words, or one long one. Deliberately loose: "Book train Lyon → Paris →
    Nantes" and "Decide Thursday or Friday, then book the train" are the
    same errand to a person, and the page should not print both."""
    shared = _sig_tokens(a) & (b if isinstance(b, set) else _sig_tokens(b))
    return len(shared) >= 2 or any(len(x) >= 7 for x in shared)


def plan_tokens(today_md):
    """Today's plan, as one token-set per task line. Parsed once per build.

    Open lines only. A ticked line's own task is ticked with it (serve.py
    mirrors the tick), so all it could still claim is somebody else's work:
    "Find the prep for Managing Innovation", done, hid tomorrow's two
    readings from School today (30 Sep)."""
    out = []
    for ln in (today_md or "").split("\n"):
        m = re.match(r"^\s*[-*]\s+\[ \]\s+(.*)$", ln)
        if m:
            toks = _sig_tokens(MD.plain(MD.AT.sub("", MD.SHORT.sub("", m.group(1)))))
            if toks:
                out.append(toks)
    return out


def plan_ws_lookup(items, cfg):
    """Which project a plan task belongs to. Exact text first (the plan quotes
    workstream tasks verbatim — that is the tick-mirror rule), then the same
    loose token match `_same_thing` uses, then the workstream's own name
    appearing in the task's words. Gives "Do these three" rows their chip."""
    rlab = room_labels(cfg)
    exact, loose, names = {}, [], []
    for w in items:
        if not w.get("live"):
            continue
        ntoks = _sig_tokens(w["name"]) | _sig_tokens(rlab.get(w["name"], ""))
        if ntoks:
            names.append((ntoks, w["name"]))
        for t in w.get("tasks", []):
            if t["done"] or t.get("dropped"):
                continue
            exact[MD.plain(t["text"]).strip().lower()] = w["name"]
            toks = _sig_tokens(t["text"])
            if toks:
                loose.append((toks, w["name"]))

    def look(text):
        name = exact.get((text or "").strip().lower())
        if name:
            return (name, rlab.get(name, ""))
        # The best match, not the first: "Prep for the Venture meeting with
        # Devon" went to School, whose tasks come first and also say
        # "meeting" (8 Oct). The project's own name in the words counts most.
        toks = _sig_tokens(text)
        score = {}
        for ntoks, nm in names:
            if ntoks & toks:
                score[nm] = score.get(nm, 0) + 3 * len(ntoks & toks)
        best = {}
        for ptoks, nm in loose:
            shared = toks & ptoks
            if len(shared) >= 2 or any(len(x) >= 7 for x in shared):
                best[nm] = max(best.get(nm, 0), len(shared)
                               + sum(1 for x in shared if len(x) >= 7))
        for nm, n in best.items():
            score[nm] = score.get(nm, 0) + n
        if not score:
            return None
        name = max(score, key=lambda nm: score[nm])
        return (name, rlab.get(name, ""))

    return look


def plan_estimates(today_md):
    """Today's open plan tasks as {label, min} for the forecast — the `~30m`
    when the task carries one, None when it doesn't, so the forecast can fall
    back to the configured default and still count the task."""
    out = []
    for ln in (today_md or "").split("\n"):
        m = re.match(r"^\s*[-*]\s+\[ \]\s+(.*)$", ln)
        if not m:
            continue
        raw = m.group(1)
        if MD.DROPPED.search(raw) or MD.UNTIL.search(raw):
            continue
        core = MD.AT.sub("", MD.SHORT.sub("", raw))  # a ~ in it is not the estimate
        est = M.EST.search(core)
        txt = re.sub(r"\s*\(urgent\)", "", M.EST.sub("", core), flags=re.I)
        out.append({"label": MD.plain(MD.CARRYING.sub("", txt)).strip(),
                    "min": M.est_to_minutes(est.group(1)) if est else None,
                    "raw": raw})
    return out


def next_line(w):
    """The one sentence a workstream would show as its next move. Every block
    that names a workstream ends up printing this, which is why they all have
    to agree about who said it first."""
    return w.get("next_action") or next(
        (t["text"] for t in w.get("tasks", []) if not t["done"]), "")


def in_plan(text, toks):
    """Is this already on today's list? The one rule that keeps a task from
    appearing in five blocks at once.

    This existed for a year as a closure inside "Off your plate in minutes",
    which is why that block alone was clean while the hero, the horizons and
    the offer card printed the same train journey six times between them.
    """
    return any(_same_thing(text, p) for p in (toks or []))


def hero_plan_link(w, today_md):
    """One honest chip: is the hero the plan's task one, elsewhere in the
    plan, or has the day moved since the plan was written? Nothing when
    there is no written plan to disagree with."""
    tasks = re.findall(r"^\s*-\s+\[([ xX])\]\s+(.*)$", today_md or "", re.M)
    if not tasks:
        return ""
    mine = _sig_tokens(w["name"]) | _sig_tokens(w.get("next_action", ""))
    for t in w.get("tasks", []):
        if not t["done"]:
            mine |= _sig_tokens(t["text"])
            break
    hit, hit_done = None, False
    for i, (mark, text) in enumerate(tasks):
        shared = mine & _sig_tokens(text)
        if len(shared) >= 2 or any(len(x) >= 6 for x in shared):
            hit, hit_done = i, mark.lower() == "x"
            break
    if hit is None:
        return ('<a class="heroplan off" href="#today">not in the written plan. '
                'The day may have moved: &#8635; refresh it &darr;</a>')
    if hit_done:
        return '<a class="heroplan" href="#today">already ticked in today&rsquo;s plan &#10003;</a>'
    if hit == 0:
        return '<a class="heroplan" href="#today">task one in today&rsquo;s plan &darr;</a>'
    # Naming the POSITION is what "also in the plan" never did. The hero is a
    # workstream and the plan is a list of tasks, so "Book train from Lyon
    # to Paris" up here and "Decide Thursday or Friday? Then book the train"
    # as item three down there read as two separate jobs unless the page says
    # they are one. Ordinals, because "task 3" is something you can look for.
    ORD = ("one", "two", "three", "four", "five", "six", "seven", "eight")
    where = ORD[hit] if hit < len(ORD) else str(hit + 1)
    return (f'<a class="heroplan" href="#today">task {where} in today&rsquo;s '
            "plan &darr;</a>")


def _legend_html(b, counts=True):
    """The Field Manual header legend: the five states with live counts.
    Hidden furniture (.skinx) until a skin shows it. Plate's copy is the
    plain key (counts=False): its tiles already count, and this "moving"
    is not the triage line's "17 moving", so two numbers would disagree."""
    moving = len([w for w in b["live"]
                  if not (w["overdue"] or w["chase"] or w["cold"]
                          or w["never_touched"] or w["due_soon"])])
    bits = [("red", "past due", len(b["overdue"])),
            ("amber", "they went quiet", len(b["chase"])),
            ("blue", "you went quiet", len(b["cold"])),
            ("terra", "due soon", len(b["soon"])),
            ("ok", "moving", moving)]
    return "".join(
        f'<span class="lgch"><i class="lg-{k}"></i>{lbl}'
        + (f" {n}" if counts else "") + "</span>"
        for k, lbl, n in bits)


def _greeting(today_md):
    """"Friday evening. One thing left." — the day's name, its phase, and the
    honest count of the plan. The Soft Brutalism skin's headline; computed
    for every build because it is four string operations."""
    now = datetime.now()
    day = now.strftime("%A")
    phase = ("morning" if now.hour < 12 else
             "afternoon" if now.hour < 17 else "evening")
    m = re.search(r"##\s*Do these three\n(.*?)(?=\n##|\Z)", today_md or "", re.S)
    block = m.group(1) if m else ""
    total = len(re.findall(r"^\s*-\s*\[[ xX]\]", block, re.M))
    done = len(re.findall(r"^\s*-\s*\[[xX]\]", block, re.M))
    left = total - done
    if not total:
        return f"{day} {phase}." if phase != "morning" else f"{day}."
    if phase == "morning":
        return f"{day}. " + ({3: "Three things.", 2: "Two things.",
                              1: "One thing."}.get(total, f"{total} things."))
    if left <= 0:
        return f"{day} {phase}. All {total} are done."
    if phase == "evening":
        # Never a count after dark. "3 things left" at 21:00 is a scoreboard
        # she can no longer change, and it read as an accusation on a day
        # that simply went somewhere else (packing day, 31 Aug — her words:
        # "stresses me out"). The evening asks; the review below listens.
        return f"{day} evening. How did it go?"
    if left == 1:
        return f"{day} {phase}. One thing left."
    return f"{day} {phase}. {left} things left."


def _plan_time():
    """When today's plan was last written, as HH:MM — or ""."""
    try:
        ts = os.path.getmtime(os.path.join(BRAIN, "today.md"))
        return datetime.fromtimestamp(ts).strftime("%H:%M")
    except OSError:
        return ""


def _days_ago(datestr):
    try:
        n = (date.today() - date.fromisoformat(datestr)).days
    except (TypeError, ValueError):
        return ""
    return "today" if n == 0 else ("yesterday" if n == 1 else f"{n} days ago")


def hero(w, cfg, today_md="", ntotal=0):
    """The single most expensive thing to keep ignoring, given the whole top
    of the page. One item, huge, with its reason and its next move."""
    pct = round(decay(w, cfg) * 100)
    # What "Do this" is about to say, so the reason above it doesn't say the
    # same sentence again four lines earlier.
    nextline = next_line(w)
    reason = why_line(w, hero=True, skip_task=nextline)
    h = [f'<section class="hero {sevclass(w)}" data-name="{e(w["name"])}"'
         f' data-flags="{" ".join(w["flags"])} {w["ball"]}">']
    # Being late on something still winnable is the one hero state that was
    # never drawn. It is also the one she most needs to feel.
    art = artvid("hurrying", 72) if w.get("pressed_late") else ""
    h.append(heroline(f'<p class="eyebrow">{hero_eyebrow()}</p>'
                      '<span class="wav"></span>', art))
    # Skin furniture (hidden unless the active skin asks for it): the
    # provenance line the print-flavoured skins stamp under the eyebrow.
    prov = []
    pt = _plan_time()
    if pt:
        prov.append("chosen " + pt)
    if ntotal:
        prov.append(f"rank 1 of {ntotal}")
    if w.get("area"):
        prov.append(e(w["area"]))
    if prov:
        h.append('<p class="skinx skinx-prov">' + " &middot; ".join(prov) + "</p>")
    h.append(f'<h1>{e(w["name"])}</h1>')
    if reason:
        h.append(f'<p class="hero-why">{reason}</p>')
    if nextline:
        # "Done" lives on the line itself. "Worked on it today" only resets
        # the clock, and the ✓ in the … menu retires the whole workstream —
        # neither says "this next move is finished". If the line is a real
        # checkbox it ticks like any other; if it is the Next: field, the
        # field clears, the touch clock resets, and the next open task
        # inherits the slot on rebuild.
        tk = next((t for t in w.get("tasks", [])
                   if not t.get("done") and not t.get("parked")
                   and not t.get("dropped") and t.get("text") == nextline
                   and t.get("key")), None)
        if tk:
            tickbtn = ('<button class="box tick needs-server" aria-pressed="false"'
                       f' data-src="workstreams.md" data-key="{tk["key"]}"'
                       ' title="Done: tick it off"></button>')
        else:
            tickbtn = ('<button class="box tick needs-server" aria-pressed="false"'
                       f' data-nextdone="{e(w["name"])}"'
                       ' title="Done: clears this next move and logs today as '
                       'worked on"></button>')
        h.append(f'<p class="hero-next"><span>Do this</span>{tickbtn}'
                 f'{e(nextline)}</p>')
    # No ball chip here. The "Next move: mine / theirs" toggle sits in the same
    # band a few pixels below, showing the same fact AND able to change it — so
    # the chip was a read-only echo of the control right next to it. It stays
    # on the plate rows, where the toggle is folded away inside the row.
    meta = []
    link = hero_plan_link(w, today_md)
    if link:
        meta.append(link)
    if w["why"]:
        meta.append(f'<span class="hero-matters">{e(w["why"])}</span>')
    h.append('<div class="hero-meta">' + " ".join(meta) + "</div>")
    # No "Claude prepared this" here. The hero's job is the ONE next move; a
    # numbered account of what was filed, ticked and reworded is a record, and
    # a record belongs where you go to look one up — it is still on the
    # workstream's row and in its details panel. Anything actually needing her
    # hand arrives as a draft under "Ready for you".
    # The spec rows the Field Manual skin renders as its ruled table; other
    # skins leave them hidden. Same facts the hero already implies, made flat.
    opens = [t for t in (w.get("tasks") or []) if not t.get("done")]
    spec = [("Owner", "You" if w["ball"] == "me"
             else ("Nobody's" if w["ball"] == "nobody" else "Them"))]
    if w.get("touched"):
        spec.append(("Last touch", _days_ago(w["touched"]) or e(w["touched"])))
    if w.get("due"):
        spec.append(("Deadline", e(w.get("due_label") or w["due"])))
    if w.get("tasks"):
        spec.append(("Open tasks", f"{len(opens)} of {len(w['tasks'])}"))
    h.append('<dl class="skinx skinx-spec">'
             + "".join(f"<div><dt>{k}</dt><dd>{v}</dd></div>" for k, v in spec)
             + "</dl>")
    h.append(f'<div class="bar"><i style="width:{pct}%"></i></div>')
    h.append(actions(w, labelled=True))
    h.append("</section>")
    return "".join(h)


_DUMP_CUES = """<ol class="dumpcuelist" id="dumpcuelist">
        <li data-cue><b>Start with you:</b> where you live, and what you're studying or building</li>
        <li data-cue><b>What fills your days:</b> the work or study taking your time right now</li>
        <li data-cue><b>The people:</b> family and close friends, including the ones far away you don't want to drift from</li>
        <li data-cue><b>What's weighing on you:</b> a deadline you're dreading, or a decision you keep putting off</li>
        <li data-cue><b>Loose threads:</b> what you owe people, and what they owe you</li>
        <li data-cue><b>What you're trying to build in yourself:</b> habits or routines, and how often you manage them now</li>
        <li data-cue><b>Anything else:</b> the small nagging things, or whatever doesn't fit a box</li>
      </ol>"""


# The step before the dump, on a brand-new brain: which subscription is
# paying for this, and what that means the brain may do on its own. It comes
# FIRST because the build run it leads into is the biggest single spend of
# the first day — asking afterwards would be asking after the money is gone.
# One tap is enough; the rest folds away for whoever wants it.
_AI_SETUP = """<div class="aiset" id="aiset" hidden>
      <p class="eyebrow">First, one question</p>
      <h2 class="dumph">How much Claude?</h2>
      <p class="dumplead">This brain runs on your own Claude subscription.
        The pages and reminders are plain code that costs nothing to run.
        The thinking parts draw on the same
        allowance as everything else you do with Claude, so it matters which
        plan you&rsquo;re on.</p>
      <div class="aipick">
        <button class="aicard" data-plan="pro">
          <b>I&rsquo;m on Pro</b>
          <span>No 7am plan. Haiku by default. Once your plan is 75%
            used, a run you start asks first.</span>
        </button>
        <button class="aicard" data-plan="max">
          <b>I&rsquo;m on Max</b>
          <span>Tomorrow&rsquo;s plan writes itself at 7am, Sonnet by
            default, and the day&rsquo;s tasks get prepared ahead of you.</span>
        </button>
      </div>
      <p class="aihint" id="aihint">If you&rsquo;re not sure, pick Pro. It&rsquo;s
        the careful one, and you can change any of this later under the hood,
        in Usage.</p>
      <details class="aimore">
        <summary>Set each one myself</summary>
        <div class="airows" id="airows">
          <div class="airow" data-key="morning">
            <span class="ail"><b>The 7am plan</b>
              <em>Writes today&rsquo;s plan before you&rsquo;re up, at the
                cost of one run a day.</em></span>
            <span class="aiseg" data-seg="morning">
              <button data-v="auto">Follow the plan</button>
              <button data-v="on">On</button><button data-v="off">Off</button>
            </span>
          </div>
          <div class="airow" data-key="model">
            <span class="ail"><b>Default model</b>
              <em>What a run uses when you don&rsquo;t pick. Haiku costs about
                a tenth of Sonnet; Opus drains a small allowance fastest.
                Fable writes the best prose and costs the most, so save it
                for drafting.</em></span>
            <span class="aiseg" data-seg="model">
              <button data-v="auto">Follow the plan</button>
              <button data-v="haiku">Haiku</button>
              <button data-v="sonnet">Sonnet</button>
              <button data-v="opus">Opus</button>
              <button data-v="fable">Fable</button>
            </span>
          </div>
          <div class="airow" data-key="openers">
            <span class="ail"><b>Openers</b>
              <em>The morning run also preps the day: it looks up the
                number and drafts the first message. It never sends
                anything.</em></span>
            <span class="aiseg" data-seg="openers">
              <button data-v="auto">Follow the plan</button>
              <button data-v="on">On</button><button data-v="off">Off</button>
            </span>
          </div>
          <div class="airow" data-key="news">
            <span class="ail"><b>News breakdowns</b>
              <em>A plain-language explainer once a day on the subjects
                you&rsquo;re learning. About 2k tokens a topic.</em></span>
            <span class="aiseg" data-seg="news">
              <button data-v="auto">Follow the plan</button>
              <button data-v="on">On</button><button data-v="off">Off</button>
            </span>
          </div>
          <div class="airow" data-key="extras">
            <span class="ail"><b>Morning extras</b>
              <em>Small calls the morning job makes besides the plan: clearer
                task wording, dates from class slides, study guides, a weekly
                writing lesson.</em></span>
            <span class="aiseg" data-seg="extras">
              <button data-v="auto">Follow the plan</button>
              <button data-v="on">On</button><button data-v="off">Off</button>
            </span>
          </div>
          <div class="airow" data-key="plan_pct">
            <span class="ail"><b>Plan limit</b>
              <em>Once your Claude plan&rsquo;s five-hour window or week
                passes this share, a run you start asks first. It counts all
                your Claude use, so the rest stays yours.</em></span>
            <span class="aiseg aipct">
              <button data-pct="">No limit</button><button data-pct="50">50%</button>
              <button data-pct="75">75%</button><button data-pct="90">90%</button>
            </span>
          </div>
          <div class="airow" data-key="daily_runs">
            <span class="ail"><b>Run limit</b>
              <em>After this many runs in a day, a run you start asks first.
                With a plan limit, this counts only while the plan can&rsquo;t
                be read. Scheduled work is never blocked.</em></span>
            <span class="aiseg aicap">
              <button data-cap="">No limit</button><button data-cap="5">5 runs</button>
              <button data-cap="10">10 runs</button><button data-cap="20">20 runs</button>
            </span>
          </div>
          <div class="airow" data-key="night">
            <span class="ail"><b>Night shift</b>
              <em>The heavy jobs run at 1am, in a usage window your own day
                never wanted. It helps most on a small plan, and it needs
                one setup command in a terminal first.</em></span>
            <span class="aiseg ainight">
              <button data-night="on">On</button><button data-night="off">Off</button>
            </span>
          </div>
          <div class="airow" data-key="privacy">
            <span class="ail"><b>Privacy</b>
              <em>Your journal stays out of runs on a timer at every level.
                Guarded also keeps transcripts and money out of them and asks
                for your fingerprint on every send; Locked keeps notes on
                people out too and sends nothing. Each switch is on the
                Privacy page later.</em></span>
            <span class="aiseg aiplevel">
              <button data-plevel="everyday">Everyday</button><button data-plevel="guarded">Guarded</button><button data-plevel="locked">Locked</button>
            </span>
          </div>
        </div>
      </details>
      <div class="aistyle">
        <p class="eyebrow">And how should it look?</p>
        <p class="dumplead">Tap one and this whole page changes with it.
          The gear at the top keeps these and the colours, any time.</p>
        <div class="aprow styles" id="ai-style">__AISTYLECHIPS__</div>
      </div>
      <div class="aifoot">
        <button class="primary" id="aigo">Now let&rsquo;s fill your brain</button>
        <span class="aisaved" id="aisaved"></span>
      </div>
    </div>"""


def _dumpcopy(sheet, fresh, cfg=None):
    """The dump overlay speaks differently to an empty brain and a full one.
    First time it's an interview; after that it's an update that MERGES —
    same engine, different promise."""
    sheet = AG.say(sheet)
    if fresh:
        return (sheet
                .replace("__DUMPH__", "Tell the brain about you")
                .replace("__DUMPLEAD__", AG.say(
                         "Tell it about yourself and what's going on, in any "
                         "order. The prompts below are there if you dry up, and "
                         "you can skip any of them. Claude sorts it all and "
                         "checks with you before writing anything down."))
                .replace("__DUMPCUES__", _DUMP_CUES)
                .replace("__AISETUP__",
                         AG.say(_AI_SETUP).replace("__AISTYLECHIPS__",
                                                   style_chips(cfg or {})))
                .replace("__DUMPBTN__", "Build my brain"))
    return (sheet
            .replace("__AISETUP__", "")
            .replace("__DUMPH__", "Add to your brain")
            .replace("__DUMPLEAD__", AG.say(
                     "Say what's new in any order: projects, people, updates "
                     "or worries. Claude merges it into what's already here, "
                     "so a person or project you've mentioned before is "
                     "updated instead of added twice. Anything it needs from "
                     "you goes in the questions list on Today."))
            .replace("__DUMPCUES__", "")
            .replace("__DUMPBTN__", "Add to my brain"))


def calendar_starts(days):
    """iso date -> start minutes of that day's fixed things, for the
    forecast's room. Twin entries (a class listed with and without its room)
    share a start and collapse. Cached reads only; None when no calendar is
    readable, so the forecast falls back to the flat daily figure rather
    than calling every day empty of commitments."""
    try:
        import calendar_read
        evs = calendar_read.events(days)
    except Exception:
        return None
    if not evs:
        return None
    # (start, length) pairs since 8 Oct: the calendar measures most events,
    # and every one used to count as 90 minutes. Twins share a start and keep
    # the longer length; an all-day entry (00:00) is a note, not busy time;
    # a cancelled one is free.
    try:
        lens = calendar_read.lengths()
    except Exception:
        lens = {}
    out = {}
    for when, title in evs:
        m = re.match(r"(\d{4}-\d{2}-\d{2}) (\d{2}):(\d{2})", when or "")
        if not m or (m.group(2), m.group(3)) == ("00", "00") \
                or re.match(r"(?i)\s*cancell?ed\b", title or ""):
            continue
        a = int(m.group(2)) * 60 + int(m.group(3))
        day = out.setdefault(m.group(1), {})
        day[a] = max(day.get(a) or 0, lens.get((when, title)) or 0)
    first = date.today()
    for i in range(days):
        out.setdefault((first + timedelta(days=i)).isoformat(), {})
    return {k: sorted((a, ln or None) for a, ln in v.items()) for k, v in out.items()}


def _fc_item(i):
    """One forecast entry as a door to its home, so the week ahead is
    somewhere to act, not only to read: a task opens the same menu it has on
    the Plate (done, park, drop), a project opens its drawer, a reply or a
    birthday opens the person."""
    lbl = e(i["label"])
    tk = i.get("tick")
    if tk:
        key = MD.taskkey(MD.bare(tk["text"]))
        return (f'<button class="fc-go fc-task needs-server" data-task="{key}"'
                f' data-src="{tk["src"]}" data-text="{e(MD.bare(tk["text"]))}"'
                + (f' data-ws="{e(i["ws"])}"' if i.get("ws") else "")
                + f'>{lbl}</button>')
    if i.get("ws"):
        return (f'<button class="fc-go" data-wsopen="{e(i["ws"])}">'
                f'{lbl}</button>')
    if i.get("who"):
        return (f'<a class="fc-go plink" href="#people" data-plink="{e(i["who"])}">'
                f'{lbl}</a>')
    return lbl


def forecastcard(fc):
    """Motion's 'will I make it', in the brain's voice: one verdict, the days
    ahead as a short ledger (when · what · how long), and the late backlog on
    its own line. Rebuilt 28 Sep — the old card summed overdue work into
    today and printed cumulative totals per row ("needs ~16h40, room for
    ~6h"), numbers nobody could act on."""
    d = M.fmt_dur
    if not fc["has_data"]:
        return ('<section class="forecast"><p class="eyebrow">The week ahead</p>'
                '<span class="wav"></span>'
                '<div class="empty">Give a task a rough time and a date, like '
                '<em>- [ ] draft the deck ~2h (due 2026-09-20)</em>. Each morning '
                'I&rsquo;ll then tell you whether the week fits the hours '
                'you have, and which deadline is going to bite first.</div></section>')
    td, late = fc["today"], fc.get("late") or {"min": 0}
    today = date.today()

    def dayname(n):
        if n == 0:
            return "Today"
        if n == 1:
            return "Tomorrow"
        dd = today + timedelta(days=n)
        return dd.strftime("%a ") + str(dd.day)

    def meter(need, cap, lbl):
        # The hours as a bar: planned against free, red when it spills.
        pct = min(100, round(100 * need / cap)) if cap else 100
        return (f'<span class="fc-meter{" over" if need > cap else ""}"'
                f' aria-hidden="true"><i style="width:{pct}%"></i></span>{lbl}')

    # The verdict: one line, the first day that breaks — or that it fits.
    first = fc["at_risk"][0] if fc["at_risk"] else None
    late_said = False       # the verdict already named the late hours
    if td.get("day_over"):
        head, tone = "The day is done.", "done"
        sub = (f"About {d(td['min'])} was planned; what didn&rsquo;t land "
               "carries or drops." if td["min"] else "")
    elif first:
        head = (f"{dayname(first['days'])} is {d(first['short'])} over.")
        tone = "over"
        sub = meter(first["need"], first["cap"],
                    f"<b>~{d(first['need'])}</b> of work &middot; "
                    f"~{d(first['cap'])} free by then")
    else:
        head, tone = "The next two weeks fit.", "ok"
        # A late pile is part of the answer. "The next two weeks fit." sat
        # directly above twelve hours of overdue work and read as a clean
        # bill (28 Sep review), so the verdict says both in one sentence.
        if late.get("min"):
            lm = late["min"]
            hrs = (f"{round(lm / 60)} hours" if lm >= 90 else
                   "an hour" if lm >= 45 else f"{lm} minutes")
            head = f"The next two weeks fit, but about {hrs} of work is already late."
            late_said = True
        sub = (meter(td["min"], td["left"],
                     f"<b>~{d(td['min'])}</b> of ~{d(td['left'])} free today")
               if td["min"] else f"~{d(td['left'])} free today, nothing planned")
        if fc["pull"]:
            p = fc["pull"]
            sub += (f" &middot; room for <b>{e(p['label'])}</b> "
                    f"~{d(p['min'])}, {dayname(p['days']).lower()}")
    out = ['<section class="forecast"><p class="eyebrow">The week ahead</p>'
           '<span class="wav"></span>',
           f'<p class="fc-head {tone}">{head}</p>',
           f'<p class="fc-sub">{sub}</p>' if sub else ""]

    # Each day is a list of whole titles, its project beside each, three on
    # show and the rest one click away in the same list (8 Oct: titles cut
    # at 52 characters, no project, and "and 7 more" that opened on its own
    # line left her guessing what "Gate: segment scoring model…" was for).
    _rl = room_labels(M.load_config())

    def _clean(t):
        return MD.plain(re.sub(
            r"\s*\((?:due|waiting until|urgent|carrying|at|short)\b[^)]*\)", "",
            re.sub(r"~\s*(?:\d+h\d*|\d+m)\b", "", t, flags=re.I))).strip()

    def _li(i):
        j = dict(i)
        if (i.get("tick") or {}).get("text"):
            j["label"] = _clean(i["tick"]["text"])
        proj = (_rl.get(i.get("ws") or "") or i.get("ws") or "") if i.get("tick") else ""
        return ("<li>" + _fc_item(j)
                + (f'<span class="fc-proj">{e(clip(proj, 28))}</span>' if proj else "")
                + "</li>")

    def _items(its, show=3):
        rest = its[show:]
        return ('<ul class="fc-items">' + "".join(_li(i) for i in its[:show])
                + (f'<li class="fc-moreli"><details class="fc-rest"><summary>Show '
                   f'{len(rest)} more</summary><ul class="fc-items">'
                   + "".join(_li(i) for i in rest) + "</ul></details></li>"
                   if rest else "") + "</ul>")

    rows = []
    for dl in fc["deadlines"][:7]:
        cls = ' class="over"' if dl["at_risk"] else ""
        rows.append(f'<li{cls}><span class="fc-when">{dayname(dl["days"])}</span>'
                    + _items([dict(i) for i in dl["items"]])
                    + f'<span class="fc-min">{d(dl["own"])}</span></li>')
    if rows:
        out.append('<ul class="fc-days">' + "".join(rows) + "</ul>")
    more = len(fc["deadlines"]) - 7
    if more > 0:
        out.append(f'<p class="fc-more">+{more} more dates in the next '
                   f'{fc["cap"]["horizon_days"]} days</p>')

    if late.get("min"):
        bits = []
        if late.get("tasks"):
            bits.append(f'{late["tasks"]} task' + ("s" if late["tasks"] != 1 else ""))
        if late.get("replies"):
            bits.append(f'{late["replies"]} repl' + ("ies" if late["replies"] != 1 else "y"))
        top = _items([dict(i) for i in late["items"]]) if late.get("items") else ""
        out.append('<div class="fc-late">'
                   '<p><b>Already late</b> &middot; '
                   + ("" if late_said else f'~{d(late["min"])} &middot; ')
                   + f'{" and ".join(bits)}</p>'
                   + top
                   + '<a class="mini" href="#/plate">Re-date or drop some</a>'
                   "</div>")
    out.append("</section>")
    return "".join(out)


def moneycard(cfg=None):
    """The bank feed's rail card: what you have, the month so far, the burn,
    and how fresh each bank's numbers are. Reads only the aggregate file —
    the raw transactions never reach the page."""
    # Hidden for now at her word (24 Sep): `finance.on_page: false` in
    # config. The feed keeps pulling; only the card is off.
    if not ((cfg or {}).get("finance") or {}).get("on_page", True):
        return ""
    try:
        with open(os.path.join(BRAIN, "finance", "summary.json")) as f:
            s = json.load(f)
    except Exception:
        return ""
    if not s.get("balances"):
        return ""
    eur = sum(float(b["amount"]) for b in s["balances"]
              if b.get("amount") and (b.get("currency") or "") == "EUR")
    banks = sorted({b["bank"] for b in s["balances"]})
    day = lambda iso: (lambda d: f'{d.day} {d.strftime("%b")}')(date(*map(int, iso.split("-"))))
    h = ['<section class="railcard money"><h3 class="area">Money</h3>',
         f'<p class="mo-total"><b>{eur:,.0f}&nbsp;&euro;</b>'
         f'<span class="mo-across"> across {e(" + ".join(banks))}</span></p>']
    ym = date.today().isoformat()[:7]
    m = (s.get("months") or {}).get(ym)
    if m:
        h.append(f'<p class="mo-line">{date.today().strftime("%B")} so far: '
                 f'in {m["in"]:,.0f}&nbsp;&euro;, out {m["out"]:,.0f}&nbsp;&euro;</p>')
    burn = s.get("monthly_burn_estimate")
    if burn is not None:
        h.append(f'<p class="mo-line">Roughly {burn:,.0f}&nbsp;&euro;/month going out, '
                 "averaged over the last three months</p>"
                 if burn > 0 else
                 '<p class="mo-line">More coming in than going out, averaged '
                 "over the last three months</p>")
    inv = s.get("investments") or []
    if inv:
        parts = " + ".join(f'{e(i["name"])} {(i.get("eur") or 0):,.0f}' for i in inv)
        asof = max((i.get("as_of") or "") for i in inv)
        h.append(f'<p class="mo-line">Invested: <b>{(s.get("investments_total_eur") or 0):,.0f}'
                 f'&nbsp;&euro;</b>: {parts}'
                 + (f' <span class="mo-across">as of {day(asof)}</span>' if asof else "")
                 + "</p>")
    bits = []
    for bank, info in sorted((s.get("banks") or {}).items()):
        fd, cd = (info.get("fetched") or "")[:10], (info.get("consent_until") or "")[:10]
        bit = f"{e(bank)}: fresh today" if fd == date.today().isoformat() \
            else f"{e(bank)}: numbers from {day(fd)}" if fd else f"{e(bank)}: nothing pulled yet"
        if cd and cd < date.today().isoformat():
            bit += ", renew to refresh"
        elif cd and (date(*map(int, cd.split("-"))) - date.today()).days <= 14:
            bit += f", <b>re-approve by {day(cd)}</b>"
        bits.append(bit)
    if bits:
        h.append('<p class="mo-fresh">' + " &middot; ".join(bits) + "</p>")
    h.append("</section>")
    return "".join(h)


def stackrow(w, rank, cfg, red=None):
    """One row of the priority stack: rank, name, the next move, why it is
    ranked here, details behind a click so the list stays scannable.

    The next action used to live inside the fold, which meant the one line she
    could act on was the one line she had to click for, while the row face
    showed the reason twice over — once as the reason, once as the task
    fragment `why_line` tacks on. Now the move is the face and the reason is
    the small print under it; `skip_task` stops it being said twice.

    No "on you" chip here. Under a heading that says "Needs you" it is on
    every row, and a badge that never varies is width spent on nothing — the
    same argument that took the urgent flag out of the digest. "with them
    &middot; Devon" still earns its place: that one tells you not to bother.
    """
    # 28 Sep review: the rank number left the face. Grouped by area (rule 7)
    # the numbers ran 1, 6, 7, 8, 2… and read as a broken list; the order
    # inside each area is still the global one, and the rank is the tooltip.
    # The decay bar went too: at full it only restated "untouched 12d" or
    # "silent 5w" from the line beside it, and unlabelled it read as progress.
    h = [f'<details class="row {plate_sev(w, red=red)}" data-name="{e(w["name"])}"'
         f' data-flags="{" ".join(w["flags"])} {w["ball"]}">']
    tchip = (f'<span class="tcount" title="Open tasks inside. Click to see them">'
             f'{w["open_tasks"]} task{"s" if w["open_tasks"] != 1 else ""} &#9662;</span>'
             if w["open_tasks"] else "")
    nxt = w["next_action"]
    # Who has the ball is said once, on the chip, by its short name: accelerator's
    # Ball ("accelerator, next session sets the next deadline") printed on the chip,
    # in the reason line and again in the Next line (28 Sep review).
    chip = ""
    if w["ball"] != "me":
        label, cls = BALLS[w["ball"]]
        who = w["ball_who"] if w["ball"] == "them" else ""
        short = (re.split(r"\s*[,;(]|\s+[—–-]\s+", who)[0].strip() or who) if who else ""
        chip = (f'<span class="v v-{cls}"'
                + (f' title="{e(who)}"' if short != who else "") + f">{label}"
                + (f" &middot; {e(short)}" if short else "") + "</span>")
    why = why_line(dict(w, ball_who="") if w["ball"] == "them" else w,
                   skip_task=nxt or "", plain_urgent=True)
    h.append(f'<summary title="Ranked {ordinal(rank)} overall">'
             '<span class="rowmain">'
             f'<span class="rowname">{e(w["name"])}</span>'
             + (f'<span class="rownext">{e(nxt)}</span>' if nxt else "")
             + (f'<span class="rowwhy">{why}</span>' if why else "")
             + "</span>"
             f'{tchip}{chip}'
             "</summary>")
    inner = []
    if w["why"]:
        inner.append(f'<p class="matters">{e(w["why"])}</p>')
    meta = []
    if w["due"]:
        meta.append("Due " + dayfirst(w.get("due_label") or w["due"]))
    if w["touched"]:
        meta.append(f"Last touched {dayfirst(w['touched'])}")
    if w["ball"] == "them" and w["since"]:
        meta.append(f"Waiting since {dayfirst(w['since'])}")
    if meta:
        inner.append('<p class="meta">' + " &middot; ".join(e(m) for m in meta) + "</p>")
    inner.append(tasklist(w))
    if w["notes"]:
        inner.append(f'<div class="notes">{MD.render(chr(10).join(w["notes"]))}</div>')
    inner.append(prepared_fold(w["name"]))
    inner.append(actions(w))
    h.append(f'<div class="rowbody">{"".join(inner)}</div>')
    h.append("</details>")
    return "".join(h)


def fronts_block(live, cfg, plan_toks=None, seen=None, claim=None):
    """Every front of her life, each with its own short ranked list of next
    moves. This replaced the hero (2026-09-10, her call): one giant top item
    read as a monument, and on a school-prep day the monument was a
    renovation she could do nothing about. The question a morning actually
    asks is per-front — given School, given Dad, given the apps, what moves
    next? Order inside a front is the same score the whole page agrees on;
    the fronts themselves lead with their loudest member."""
    if not live:
        return ""
    fronts = {}
    for w in live:
        fronts.setdefault(w["area"], []).append(w)
    order = sorted(fronts, key=lambda a: -max(x["score"] for x in fronts[a]))
    rlab = room_labels(cfg)
    out = ['<section class="frontswrap" id="fronts">'
           '<p class="eyebrow">Front by front</p><span class="wav"></span>']
    for area in order:
        group = sorted(fronts[area], key=lambda x: -x["score"])
        out.append(f'<div class="front"><h3 class="area">{e(area)}</h3>')
        for w in group[:3]:
            # No tickbox here (24 Sep, her call: "too many different check
            # boxes"). This block is a map of her fronts; ticking happens on
            # the plan above or in the project's drawer.
            nxt = next_line(w)
            toks = plan_toks or []
            planned = bool(nxt) and in_plan(nxt, toks)
            shown = planned or bool(nxt and seen and seen(nxt))
            if shown:
                # Its first move is already on the page, so name the one
                # after it. A bare "ABOVE" in green capitals read as a stray
                # heading (her words, 25 Sep).
                nxt = next((t["text"] for t in sorted(
                    (t for t in w.get("tasks", [])
                     if not (t.get("done") or t.get("parked")
                             or t.get("dropped") or t.get("expired"))),
                    key=lambda t: -(t.get("pressure") or 0))
                    if t["text"] != nxt and not in_plan(t["text"], toks)
                    and not (seen and seen(t["text"]))), "")
            if nxt and claim:
                claim(nxt)
            # "(class)" is a marker for the tracker, not words to read.
            face_txt = re.sub(r"\s*\(class\)", "", nxt or "")
            if face_txt:
                face = '<span class="fnext">' + e(face_txt) + "</span>"
            elif shown:
                face = ('<span class="fnext fnote">'
                        + ("already in today&rsquo;s plan" if planned
                           else "already further up the page") + "</span>")
            else:
                face = '<span class="fnext fnote">nothing queued</span>'
            out.append(
                f'<div class="frow {sevclass(w)}">'
                f'<button class="tws"{LN.ws_attr(w["name"])} data-wsopen="{e(w["name"])}"'
                f' title="Open the project: {e(w["name"])}">'
                + e(rlab.get(w["name"], w["name"])) + "</button>"
                + face + "</div>")
        if len(group) > 3:
            _n = len(group) - 3
            out.append(f'<p class="fmore">and {_n} more {e(area)} '
                       f'workstream{"s" if _n != 1 else ""} on the plate</p>')
        out.append("</div>")
    out.append("</section>")
    return "".join(out)


def _probablydone_tray(live, bare=False):
    """Tasks whose moment has passed: a same-day errand seen days later, a
    booking verb after its date. model.py already dropped them from every
    ranking; here the page asks instead of nagging. Nothing is marked done
    without her click — done still means she said so — but one click IS her
    saying so, eight at a time."""
    rows, extra = [], 0
    for w in live:
        for t in w.get("tasks", []):
            if not t.get("expired") or t.get("done") or t.get("dropped") \
                    or t.get("parked"):
                continue
            if len(rows) >= 8:
                extra += 1
                continue
            key = t.get("key") or MD.taskkey(t["text"])
            # A task the brain could check for itself (model.SETTLED) says
            # what it checked, so "Done" is her confirming a fact, not a guess.
            # Prep for a named day says which day went (model.event_passed).
            why = t.get("settled") or t.get("passed_said")
            said = f' &middot; {e(why)}' if why else ""
            rows.append(
                '<div class="pdrow">'
                f'<span class="pdtext">{e(t["text"])}'
                f'<i>{e(w["name"])}{said}</i></span>'
                f'<button class="mini" data-pdact="done" data-pdkey="{key}">'
                "Done &#10003;</button>"
                f'<button class="mini" data-pdact="revive" data-pdkey="{key}">'
                "Still open</button></div>")
    if not rows:
        return ""
    allbtn = ('<button class="mini" id="pdall">All of these happened</button>'
              if len(rows) > 1 else "")
    more = f'<p class="mtmore">and {extra} more behind these</p>' if extra else ""
    if bare:
        return ('<div class="pdtray needs-server">' + "".join(rows) + allbtn
                + more + '<span class="mshelp" id="pd-help"></span></div>')
    return ('<section class="pdtray needs-server"><h2>Probably done?'
            + hint("The moment on these has passed, so they stopped counting "
                   "in the rankings. Done closes one for real; Still open "
                   "removes the passed date so it counts in the rankings again.")
            + f'</h2>{"".join(rows)}{allbtn}{more}'
            '<span class="mshelp" id="pd-help"></span></section>')


def calmrow(w, cfg):
    """A quiet one-liner. These are fine; they must not compete for contrast
    with the stack above — that is the whole hierarchy of the page."""
    h = [f'<details class="row calm" data-name="{e(w["name"])}"'
         f' data-flags="{" ".join(w["flags"])} {w["ball"]}">']
    bits = []
    if w["next_action"]:
        bits.append(e(w["next_action"]))
    if w["open_tasks"]:
        bits.append(f"{w['open_tasks']} open")
    if w["due"]:
        bits.append("due " + dayfirst(w.get("due_label") or w["due"]))
    h.append('<summary>'
             '<span class="dot"></span>'
             '<span class="rowmain">'
             f'<span class="rowname">{e(w["name"])}</span>'
             f'<span class="rowwhy">{" &middot; ".join(bits)}</span>'
             "</span>"
             f'{ballchip(w)}'
             "</summary>")
    inner = [tasklist(w)]
    if w["why"]:
        inner.append(f'<p class="matters">{e(w["why"])}</p>')
    if w["notes"]:
        inner.append(f'<div class="notes">{MD.render(chr(10).join(w["notes"]))}</div>')
    inner.append(actions(w))
    h.append(f'<div class="rowbody">{"".join(inner)}</div>')
    h.append("</details>")
    return "".join(h)


def _src_for(w, sources):
    """Which configured project folder belongs to this workstream — best token
    overlap between the workstream name and the source name, singular/plural
    tolerated ('Renovations' finds 'House renovation')."""
    def toks(s):
        return {t.lower().rstrip("s") for t in re.findall(r"[A-Za-zà-ÿ]+", s or "")
                if len(t) >= 4}
    wt = toks(w["name"])
    best, score = None, 0
    for s in sources or []:
        n = len(wt & toks(s.get("name", "")))
        if n > score:
            best, score = s, n
    return best


def wsdetail(w, sources):
    """One workstream as a whole little screen: status, the dated tasks as a
    timeline, every task tickable, the people inside it, notes, and the folder
    on disk — with the read-my-computer trigger right there."""
    n = e(w["name"])
    out = [f'<div class="wsdetail" data-for="{n}" hidden>']
    out.append(f'<p class="eyebrow">{e(w.get("area") or "Workstream")}</p>')
    out.append(f"<h2>{n}</h2>")
    reason = why_line(w)
    if reason:
        out.append(f'<p class="rowwhy wsd-why">{reason}</p>')
    meta = []
    if w["due"]:
        meta.append("Due " + dayfirst(w.get("due_label") or w["due"]))
    if w["touched"]:
        meta.append(f"Last touched {dayfirst(w['touched'])}")
    if w["ball"] == "them" and w["since"]:
        meta.append(f"Waiting since {dayfirst(w['since'])}")
    if meta:
        out.append('<p class="meta">' + " &middot; ".join(e(m) for m in meta) + "</p>")
    if w["why"]:
        out.append(f'<p class="matters">{e(w["why"])}</p>')
    dated = sorted((t for t in w["tasks"]
                    if not t["done"] and not t.get("dropped")
                    and t.get("due_days") is not None),
                   key=lambda t: t["due_days"])
    if dated:
        out.append('<h3 class="wsd-h">Coming up</h3><ul class="wsd-when">')
        for t in dated[:8]:
            dd = t["due_days"]
            lab = ("today" if dd == 0 else
                   f"{abs(dd)}d overdue" if dd < 0 else f"in {dd}d")
            out.append(f'<li><span class="wsd-date{" bad" if dd < 0 else ""}">{lab}</span>'
                       f"{iso_prose(linknames(e(t['text'])))}</li>")
        out.append("</ul>")
    hay = " ".join([w["name"], w.get("next_action") or "", w.get("why") or "",
                    w.get("ball_who") or "",
                    " ".join(t["text"] for t in w["tasks"])] + w["notes"]
                   + [n for t in w["tasks"] for n in t.get("notes") or []])
    found = list(w.get("linked_people", []))          # hand-made links first
    found += [nm for nm in PERSON_NAMES if nm not in found and M.name_in(nm, hay)]
    out.append('<h3 class="wsd-h">People in this</h3><p class="wsd-people">'
               + " ".join(f'<a class="plink" href="#people" data-plink="{e(nm)}">{e(nm)}</a>'
                          for nm in found[:10])
               + f' <button class="mini wsaddp needs-server" data-wsaddp="{n}">'
               "+ link a person</button></p>")
    prep = prepared_fold(w["name"])
    if prep:
        out.append(f'<h3 class="wsd-h">{AG.short()} prepared</h3>' + prep)
    _rsl = _ws_room_slug(n)
    if _rsl:
        out.append(f'<p class="meta"><a href="rooms.html#room/{_rsl}">'
                   'Its page &rarr;</a></p>')
    out.append('<h3 class="wsd-h">Tasks</h3>'
               + (tasklist(w) or '<p class="meta">None open.</p>'))
    if w["notes"]:
        out.append('<h3 class="wsd-h">Notes</h3><div class="notes">'
                   + MD.render(chr(10).join(w["notes"])) + "</div>")
    src = _src_for(w, sources)
    out.append('<h3 class="wsd-h">On your computer</h3>')
    if src:
        out.append('<p class="meta">Syncs from '
                   f'<button class="flink needs-server" data-reveal="{e(src.get("path", ""))}"'
                   f' title="Open the folder">{e(src.get("path", ""))} &#8599;</button></p>'
                   f'<button class="mini wssearch needs-server" data-wssearch="{n}"'
                   f' data-wspath="{e(src.get("path", ""))}">Read the folder &amp; update this</button> '
                   f'<button class="mini wsrun needs-server" data-wsrun="{n}"'
                   f' data-wspath="{e(src.get("path", ""))}" title="One {AG.label()} run '
                   'inside that repo, following its own CLAUDE.md. You can watch it from the bar here">'
                   "Quick run in this repo&hellip;</button>")
    else:
        out.append('<p class="meta">No folder linked yet.</p>'
                   f'<button class="mini wssearch needs-server" data-wssearch="{n}">'
                   "Search my computer for this</button>")
    out.append(actions(w))
    out.append("</div>")
    return "".join(out)


# ── For you: one tray for everything the brain proposes (28 Sep) ────────────
# Seven review lists lived in seven places: drafts on the Claude tab,
# questions in Today's rail, "probably done" and the mail tasks on Today, the
# slide dates on School, new files on the Claude tab, chats to sort on People.
# They are one thing — the brain proposing, her deciding — so they are one
# list, in one order (send, answer, confirm, read), each keeping the controls
# it already had. Today carries it; the box shows it on every page, from
# .tray.json, as doors back to here.
TRAY_KIND = {"new": "New today", "send": "Send", "answer": "Answer",
             "confirm": "Confirm", "read": "Read"}


def _tid(prefix, text):
    """A tray item's id: stable across builds, safe in a URL and an id."""
    slug = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return (prefix + ":" + slug)[:100].rstrip("-")


def tray_item(tid, kind, title, body, count=0, sub="", chip=""):
    """One line of For you: what kind of decision, what it is about, and its
    own controls one click down. `chip` says what the thing is when the
    title can't: a draft's row carries its task's words, so "Post the setup
    link…" read as a task, not a message ready to copy (9 Oct)."""
    return {"id": tid, "k": TRAY_KIND[kind], "t": title,
            "html": iso_prose(
                f'<details class="tray tk-{kind}" id="tray-{e(tid)}">'
                f'<summary><span class="trk">{TRAY_KIND[kind]}</span>'
                f'<span class="trt" title="{e(title)}">{e(title)}</span>'
                + (f'<span class="trchip">{e(chip)}</span>' if chip else "")
                + (f'<span class="trn">{count}</span>' if count else "")
                + (f'<span class="trs">{e(sub)}</span>' if sub else "")
                + f'</summary><div class="trbody">{body}</div></details>')}


def tray_card(items, action=""):
    """Today's For you, and the list the box reads. The first few show; the
    rest fold, so a heavy day does not push the plan's company off screen.
    `action` sits beside the heading, always in view: the mail check, which
    under the hood went four weeks unpressed."""
    try:
        with open(os.path.join(BRAIN, ".tray.json"), "w", encoding="utf-8") as f:
            json.dump([{"id": i["id"], "k": i["k"], "t": i["t"]} for i in items],
                      f, ensure_ascii=False)
    except OSError:
        pass
    if not items and not action:
        return ""
    # Five on show, the rest one click away (7 Oct; four had become 4 and
    # "Show 16 more").
    head, rest = items[:5], items[5:]
    # Five drafts on show folded every question the page asks, the one kind
    # of line only she can settle (10 Oct). Then the fifth goes to the first.
    ans = TRAY_KIND["answer"]
    if rest and not any(i["k"] == ans for i in head):
        q1 = next((i for i in rest if i["k"] == ans), None)
        if q1:
            rest.remove(q1)
            rest.insert(0, head.pop())
            head.append(q1)

    # The kind said once, as a heading over its run of lines. Four rows that
    # each said CONFIRM told her nothing the first one hadn't (28 Sep
    # review); the per-row label stays in the markup for the box, hidden
    # here by the page's CSS.
    def run(its, prev):
        out = []
        for i in its:
            if i["k"] != prev:
                out.append(f'<p class="trgroup trg-{i["k"].lower()}">'
                           f'{i["k"]}</p>')
                prev = i["k"]
            out.append(i["html"])
        return "".join(out), prev
    head_html, last = run(head, None)
    rest_html = run(rest, last)[0] if rest else ""
    return ('<section class="foryou" id="foryou">'
            f'<h3 class="area">For you <span class="csub">{len(items) or ""}</span></h3>'
            + (f'<div class="fyact needs-server">{action}</div>' if action else "")
            + head_html
            + (f'<details class="ghost trmore"><summary>'
               f'<span class="amc">Show {len(rest)} more</span>'
               '<span class="amo">Show fewer</span></summary>'
               + rest_html + "</details>" if rest else "")
            + "</section>")


def _tonight(today, today_md=""):
    """Tonight's dinner: the week's plan in the kitchen, else the line the
    morning plan wrote."""
    try:
        raw = read("cooking/plan.md")
    except Exception:
        raw = ""
    monday = today - timedelta(days=today.weekday())
    day = today.strftime("%a")
    block = re.search(r"^##\s+Week of\s+" + monday.isoformat() + r"\s*$(.*?)(?=^## |\Z)",
                      raw, re.M | re.S)
    if block:
        m = re.search(r"^\s*-\s+" + day + r":\s*(.+?)\s*$", block.group(1), re.M)
        if m:
            return re.sub(r"\s*\{[^}]*\}", "", m.group(1)).strip()
    m = re.search(r"\*Tonight:\*\s*(.+?)\s*$", today_md or "", re.M)
    return m.group(1).strip() if m else ""


def _routine_today(today):
    """Today's line of each routine that has one, and any cadence that is
    due — short, the way the rhythm card and Life say them."""
    try:
        import routines as _rt
        rs = _rt.load()
    except Exception:
        return []
    day = _rt.DAYS[today.weekday()] if hasattr(_rt, "DAYS") else today.strftime("%a")
    out = []
    for r in rs:
        vals = r["rota"].get(day) or []
        pairs = [f"{lab}: {v}" for lab, v in zip(r["rota_labels"], vals) if v]
        if pairs:
            out.append((r["name"], " · ".join(pairs)))
            continue
        d = _rt.due(r, today)
        if d and d[0] == "due":
            out.append((r["name"], "due"))
    return out


def rhythm_lines(today, today_md=""):
    """The non-computer half of the day, as rows for Today's rhythm card:
    tonight's dinner and today's routine lines. Habits sit above them."""
    rows = []
    import parts as PARTS
    _pcfg = PARTS.load()
    dinner = _tonight(today, today_md) if PARTS.on("kitchen", _pcfg) else ""
    if dinner:
        rows.append(f'<a class="rhrow" href="cook.html"><span class="rhk">Tonight</span>'
                    f'<span class="rht">{e(dinner)}</span></a>')
    for name, line in (_routine_today(today)[:4]
                       if PARTS.on("routines", _pcfg) else []):
        # The routine's short name: "Skincare & beauty" printed as
        # "SKINCARE &…" in the label column (28 Sep review). The full name
        # stays in the tooltip.
        short = re.split(r"\s+[&—–-]\s+|\s*\(", name)[0].strip() or name
        rows.append(f'<a class="rhrow" href="routines.html"><span class="rhk"'
                    f' title="{e(name)}">{e(clip(short, 22))}</span>'
                    f'<span class="rht">{e(line)}</span></a>')
    return "".join(rows)


def _lifecard(key, title, main, faint="", href="", go="", extra=""):
    """One card on Life's overview: the part, today's slice of it, one faint
    line, and the way in. No prose — the slice is the content."""
    link = (f'<a class="lcgo" href="{href}">{go} &rarr;</a>' if href else "")
    return (f'<section class="lifecard lc-{key}"><div class="lchead">'
            f'<h3 class="area">{title}</h3>{link}</div>'
            + (f'<div class="lcmain">{main}</div>' if main else "")
            + (f'<p class="lcfaint">{faint}</p>' if faint else "")
            + extra + "</section>")


# Life's overview: a wide main column led by the habits, and a side stack
# of the small parts. Four equal stacks left the lower half of a laptop
# screen empty and folded the one card with real content (8 Oct). The
# page decides the stacks itself: the browser's column balancing put every
# card in the first column in her browser (5 Oct). On a phone the cards
# run tonight first, in the `order` page.css gives each `.lc-<key>`.
LIFE_MAIN = (("habits",), ("season", "outthere"))
LIFE_SIDE = ("tonight", "routine", "learn", "journal")
# Each card's part under the gear (parts.py).
LIFE_CARD_PART = {"habits": "habits", "season": "season", "outthere": "season",
                  "tonight": "kitchen", "routine": "routines",
                  "learn": "learning", "journal": "journal"}


def part_off_note(part):
    """What a view says when its part is switched off: someone with an old
    link lands on the way back, not on a blank page."""
    import parts as PARTS
    return ('<section class="partoff"><p class="eyebrow">Switched off</p>'
            f'<h2>{e(PARTS.NAMES.get(part) or part.capitalize())} is off</h2>'
            '<a class="mini" href="#/hood" data-nav="hood">Turn it on under'
            ' the gear &rarr;</a></section>')


def _life_habits(habits):
    """The habits as a table: each one's last eight weeks as counts, then
    this week day by day, then this week's count. Chronological left to
    right, so the week she is in reads as the end of the run."""
    week = habits[0]["grid"][-1]
    head = ('<div class="lhrow lhhd"><span class="lhname"></span>'
            '<span class="lhweeks" title="Days a week, oldest left">'
            'Last 8 weeks</span><span class="lhdays">'
            + "".join(f'<i{" class=today" if c["today"] else ""}>{d}</i>'
                      for d, c in zip("MTWTFSS", week))
            + '</span><span class="lhcount"></span></div>')
    rows = []
    for hb in habits:
        # An empty week is a blank, not a zero: unlogged, not missed.
        weeks = "".join(
            f'<span class="wpill {"ok" if w["count"] >= hb["goal"] else "low"}'
            f'{"" if w["count"] else " none"}" title="Week of {w["start"]}">'
            f'{w["count"] or ""}</span>'
            for w in hb["weeks"][-9:-1])
        days = "".join(
            '<i class="' + " ".join(k for k in ("on", "today", "future") if c[k])
            + f'" title="{c["date"]}"></i>' for c in hb["grid"][-1])
        ok = " ok" if hb["week_count"] >= hb["goal"] else ""
        rows.append(f'<div class="lhrow{ok}"><span class="lhname">{e(hb["name"])}</span>'
                    f'<span class="lhweeks">{weeks}</span>'
                    f'<span class="lhdays">{days}</span>'
                    f'<span class="lhcount"><b>{hb["week_count"]}</b>/{hb["target"]}'
                    "</span></div>")
    return f'<div class="lhgrid">{head}{"".join(rows)}</div>'


def life_view(cfg, today, today_md, habits):
    """Life: how she lives, as opposed to what she owes. The overview carries
    today's slice of each part; each part is one tap away. Obligations never
    come here — Health and Family are fronts, their tasks live on the Plate."""
    cards = {}
    # Tonight
    dinner = _tonight(today, today_md)
    try:
        # What is left to buy: the "Probably have" fold is not on the list,
        # and counting it said 17 over a list of 13 (8 Oct).
        shop = sum(1 for ln in read("cooking/shopping.md")
                   .split("## Probably have")[0].split("\n")
                   if re.match(r"^\s*-\s+\[ \]", ln))
    except Exception:
        shop = 0
    cards["tonight"] = (_lifecard("tonight",
        "Tonight", e(dinner) if dinner else '<span class="lcnone">Nothing planned</span>',
        f"{shop} on the shopping list" if shop else "", "cook.html", "Kitchen"))
    # Routine
    rt = _routine_today(today)
    cards["routine"] = (_lifecard("routine",
        "Routine today",
        # The routine's name on its own line over today's value: run together
        # it read "Skincare & beauty Face: Retinal" (page review L2).
        "".join(f'<p class="lcrow lcrt"><b>{e(n)}</b><span>{e(l)}</span></p>'
                for n, l in rt[:5])
        or '<span class="lcnone">Nothing on today</span>',
        "", "routines.html", "Routine"))
    # Habits: the widest card, the weeks open rather than one fold down
    if habits:
        cards["habits"] = _lifecard("habits", "Habits", _life_habits(habits))
    # Season: the next thing planned, and the nearest countdown. "Nothing
    # planned yet" was said over three slotted days that had all passed
    # (page review B5): say what is true — nothing on a day ahead — and
    # count the passed ones that are waiting on a "did it happen?".
    main, faint = "", ""
    try:
        s = M.load_season(today=today) or {}
        live = [i for i in (s.get("items") or [])
                if not i.get("done") and not i.get("dropped")]
        planned = sorted(
            (i for i in live
             if i.get("planned") and i["planned"]["start"] >= today),
            key=lambda i: i["planned"]["start"])
        passed = sum(1 for i in live
                     if i.get("planned") and i["planned"]["end"] < today)
        if planned:
            p = planned[0]
            ps = p["planned"]["start"]
            main = (f'{e(p["text"])} <span class="lcwhen">'
                    f'{ps.strftime("%a")} {_mon_day(ps)}</span>')
        else:
            main = '<span class="lcnone">Nothing on a day ahead</span>'
        if passed:
            main += ('<p class="lcrow lcask">%d %s passed. Did %s'
                     ' happen?</p>' % (passed, "has" if passed == 1 else "have",
                                      "it" if passed == 1 else "they"))
        left = s.get("days_left")
        if left is not None and s.get("name"):
            faint = f'{e(s["name"])} &middot; {left} days left'
    except Exception:
        pass
    cards["season"] = (_lifecard("season", "Season", main or '<span class="lcnone">No season yet</span>',
                           faint, "#/season", "Season"))
    # Out there: the scout's top picks, so the best of the week's finds is
    # seen without going to the foot of the Season tab (8 Oct, her ask).
    # News had this slot until it got its own place in the bar the same day.
    try:
        _m, evgroups = _events(today)
    except Exception:
        evgroups = []
    dated = [it for g in evgroups for it in g["items"] if it["d1"]]
    shown = ([it for it in dated if it["pick"]]
             or sorted(dated, key=lambda it: it["d1"]))
    shown.sort(key=lambda it: (max(it["d1"], today), it["d2"]))
    in_season = _season_titles(today) if shown else set()
    evrows = []
    for it in shown[:4]:
        d1, d2 = it["d1"], it["d2"]
        when = (f"until {_mon_day(d2)}" if d2 != d1 and d1 <= today
                else _ev_lab(d1, d2))
        name = re.sub(r"\s*\([^)]*\)", "", _ev_title(it["text"])).strip()
        url = MD.safe_href(it["url"])
        name = (f'<a class="lcevn" href="{e(url)}" target="_blank"'
                f' rel="noopener noreferrer" title="{e(it["text"])}">{e(name)}</a>'
                if url else
                f'<span class="lcevn" title="{e(it["text"])}">{e(name)}</span>')
        evrows.append(f'<p class="lcrow lcev"><span class="lcwhen">{when}</span>'
                      f'{name}{_ev_addbtn(it, in_season)}</p>')
    cards["outthere"] = _lifecard(
        "outthere", "Out there",
        "".join(evrows) or '<span class="lcnone">Nothing scouted yet</span>',
        "", "#/season", "All events")
    # Learn: the topics she is learning with /teach
    topics = []
    ldir = os.path.join(BRAIN, "learning")
    try:
        for fn in sorted(os.listdir(ldir)):
            if fn.endswith(".md"):
                m = re.search(r"^#\s+(.+)$", read("learning/" + fn), re.M)
                topics.append(m.group(1).strip() if m else fn[:-3])
    except OSError:
        pass
    cards["learn"] = (_lifecard("learn",
        "Learn",
        "".join(f'<p class="lcrow">{e(t)}</p>' for t in topics[:4])
        or '<span class="lcnone">No topic yet</span>', "", "", "",
        '<div class="lcacts">'
        + ('<button class="mini needs-server" data-box data-box-text="Review my due '
           'recall cards, the way .claude/commands/teach.md does with no topic.">'
           '&#10022; Review what&rsquo;s due</button>' if topics else "")
        + '<button class="mini needs-server" data-box data-box-text="Teach me ">'
          '&#10022; Teach me something</button></div>'))
    # Journal: the date of the last entry — never its words
    last = ""
    try:
        days = sorted(fn[:10] for fn in os.listdir(os.path.join(BRAIN, "journal"))
                      if re.match(r"\d{4}-\d{2}-\d{2}\.md$", fn))
        if days:
            d = date.fromisoformat(days[-1])
            last = "today" if d == today else ago((today - d).days)
    except (OSError, ValueError):
        pass
    if PRESENTING:
        last = None          # presenting: no journal card at all
    cards["journal"] = None if PRESENTING else (_lifecard("journal",
        "Journal", (f"Last written {e(last)}" if last
                    else '<span class="lcnone">No entry yet</span>'),
        # True and plain: runs she is not watching never load the journal.
        f"Private: {AG.short()} reads it only in a session you&rsquo;re in.",
        "", "",
        '<div class="lcacts"><button class="mini needs-server" data-box'
        ' data-box-intent="journal">&#10022; Write today&rsquo;s</button></div>'))
    # A part switched off under the gear takes its card with it (parts.py).
    import parts as PARTS
    for k, part in LIFE_CARD_PART.items():
        if not PARTS.on(part, cfg):
            cards.pop(k, None)
    cards = {k: v for k, v in cards.items() if v is not None}
    main = "".join(
        (f'<div class="lcpair">{"".join(cards[k] for k in row if k in cards)}</div>'
         if len(row) > 1 else cards[row[0]])
        for row in LIFE_MAIN if any(k in cards for k in row))
    side = "".join(cards[k] for k in LIFE_SIDE if k in cards)
    return ('<section class="lifehead"><p class="eyebrow">Life</p>'
            f'<h2>{today.strftime("%A")}, away from the plate</h2></section>'
            f'<div class="lifegrid"><div class="lifemain">{main}</div>'
            f'<div class="lifeside">{side}</div></div>')


def finish_lines(cfg, today):
    """The nearest finish lines across every front, pinned above the Plate —
    the strip that used to head the rooms' floor plan."""
    try:
        goals = M.load_goals(today=today) or {}
    except Exception:
        return ""
    rooms = {(r.get("name") or "").strip().lower(): r for r in M.all_rooms(cfg)}
    by_ws = {}
    for r in rooms.values():
        for n in (r.get("ws") or []):
            by_ws[n.strip().lower()] = r
    rows = []
    for heading, gs in goals.items():
        room = rooms.get(heading) or by_ws.get(heading)
        for g in gs:
            if g["done"] or g["days_to_due"] is None:
                continue
            rows.append((g["days_to_due"], room, heading, g))
    if not rows:
        return ""
    rows.sort(key=lambda x: x[0])
    chips = []
    for dd, room, heading, g in rows[:5]:
        name = room["name"] if room else heading.title()
        when = (f"{abs(dd)}d late" if dd < 0 else "today" if dd == 0 else f"{dd}d")
        href = f'rooms.html#room/{room["slug"]}' if room else "#/plate"
        chips.append(f'<a class="flchip{" bad" if dd < 0 else ""}" href="{href}"'
                     f' title="{e(g["text"])}"><b>{e(name)}</b>'
                     f'<span>{e(clip(g["text"], 48))}</span><i>{when}</i></a>')
    return ('<div class="finishlines"><p class="eyebrow">Finish lines</p>'
            '<div class="flchips">' + "".join(chips) + "</div></div>")


def present_synced(text):
    """What the project folders say, while presenting: a hidden area's
    folders go (the summary showed two family projects' task lists), and so
    does any line naming family or friends."""
    hide = {a.strip().lower() for a in PRESENTING["areas"]}
    gone = {(r.get("source") or "").strip().lower() for r in M.all_rooms(M.load_config())
            if (r.get("area") or "").strip().lower() in hide} - {""}
    out, skip = [], False
    for line in text.splitlines():
        h = re.match(r"#{2,4}\s+(.*?)\s*$", line)
        if h:
            skip = h.group(1).strip().lower() in gone or bool(
                PRESENT_NAMES_RX and PRESENT_NAMES_RX.search(h.group(1)))
        if skip or (PRESENT_NAMES_RX and PRESENT_NAMES_RX.search(line)):
            continue
        out.append(line)
    return "\n".join(out) + "\n"


def _present_ideas(text):
    """The idea shelf while presenting: an idea (a dated heading or a bold
    bullet, with the lines under it) that names family or friends goes."""
    out, block = [], []

    def flush():
        if not any(PRESENT_NAMES_RX.search(x) for x in block):
            out.extend(block)
        block.clear()
    for line in text.splitlines():
        if re.match(r"#{1,2}\s|-\s+\*\*", line):
            flush()
        block.append(line)
    flush()
    return "\n".join(out) + "\n"


def plate_foot(cfg, items):
    """The foot of the Plate: the pages with no open work, the big questions,
    the idea shelf, and a way to audit one area of her life. These used to be
    the rooms' floor plan and its wing audits."""
    live = {w["name"] for w in items if w["live"]}
    by_name = {w["name"]: w for w in items}
    sources = {s.get("name"): s for s in (cfg.get("sources") or [])}
    rooms = M.all_rooms(cfg)
    if PRESENTING:
        # The hidden areas' pages and audit buttons, and any page named for
        # family or friends, stay off the projector.
        hide = {a.strip().lower() for a in PRESENTING["areas"]}
        rooms = [r for r in rooms if (r.get("area") or "").strip().lower() not in hide
                 and not (PRESENT_NAMES_RX and PRESENT_NAMES_RX.search(r["name"]))]
    out = []
    bq = [r for r in rooms if r["area"] == M.BIG_QUESTIONS]
    for r in bq:
        out.append('<a class="pfbigq" href="rooms.html#room/' + r["slug"] + '">'
                   '<span class="eyebrow">Under everything</span>'
                   f'<b>{e(r["name"])}</b><span class="bqgo">&rarr;</span></a>')
    quiet = [r for r in rooms if r["area"] != M.BIG_QUESTIONS
             and not r.get("habits")
             and not any(n in live for n in (r.get("ws") or []))]
    if quiet:
        out.append('<div class="platequiet"><p class="eyebrow">Pages with no open work</p>'
                   + "".join(f'<a class="pqchip" href="rooms.html#room/{r["slug"]}">'
                             f'{e(r["name"])}</a>' for r in quiet) + "</div>")
    try:
        ideas = read("ideas.md")
    except Exception:
        ideas = ""
    # Ideas, not section headings: a dated "## 2026-10-06: …" heading or a
    # "- **Name**" line under a section. Counting every "## " showed her
    # shelf as 7 (its section names) and the starter's as one per idea.
    n_ideas = (len(re.findall(r"^##\s+\d{4}-\d\d-\d\d", ideas, re.M))
               + len(re.findall(r"^-\s+\*\*", ideas, re.M)))
    if ideas.strip() and PRESENTING and PRESENT_NAMES_RX:
        ideas = _present_ideas(ideas)
    if ideas.strip():
        out.append('<details class="ghost ideashelf"><summary>The idea shelf'
                   + (f" &middot; {n_ideas}" if n_ideas else "")
                   + '</summary><div class="doc">'
                   + MD.render(ideas, task_source="ideas.md") + "</div></details>")
    # One audit per area — the wing audits, regrouped the way the plate is.
    areas = {}
    for r in rooms:
        if r["area"] != M.BIG_QUESTIONS and not r.get("habits"):
            areas.setdefault(r["area"], []).append(r)
    btns = []
    for area, rs in areas.items():
        lines = []
        for r in rs:
            ln = r["name"]
            wss = [n for n in (r.get("ws") or []) if n in by_name]
            if wss:
                ln += " (workstreams: " + ", ".join(wss) + ")"
            src = sources.get(r.get("source") or "")
            if src:
                ln += " [folder " + src.get("path", "") + "]"
            lines.append("- " + ln)
        text = ("Audit one part of my life: “" + area + "”. Its projects:\n"
                + "\n".join(lines)
                + "\n\nFor each: read the workstream and, where a folder is listed, "
                "its key files. Compare what the files say with the open tasks. "
                "Tell me plainly what is drifting, what is stale, and ask me what "
                "is missing. When your Outcome talks about a project, name it "
                "like: workstream “X” — that is how the findings "
                "land back on its page. Propose, don’t restructure; tick "
                "nothing.")
        btns.append(f'<button class="mini needs-server" data-audit="{e(text)}"'
                    f' data-auditarea="{e(area)}">{e(area)}</button>')
    if btns:
        out.append('<div class="plateaudit"><p class="eyebrow">Audit an area</p>'
                   '<div class="paacts">' + "".join(btns) + "</div></div>")
    return ('<section class="platefoot">' + "".join(out) + "</section>") if out else ""


def friday_block(b, cfg, today):
    """The Friday hour (her term-mode call, 24 Sep): on the batch day, the
    fronts she parks all week sit under the plan, one next move each."""
    now = cfg.get("now") or {}
    batch = now.get("batch") or {}
    day = (batch.get("day") or "").strip()
    if not day or today.strftime("%A").lower() != day.lower():
        return ""
    until = M.parse_date(now.get("until") or "")
    if until and until < today:
        return ""
    live = {w["name"]: w for w in b["live"]}
    rows = []
    for n in batch.get("workstreams") or []:
        w = live.get(n)
        if not w:
            continue
        nxt = next_line(w)
        rows.append(f'<div class="frrow"><button class="tws"{LN.ws_attr(n)} data-wsopen="{e(n)}">'
                    f'{e(n)}</button><span class="fnext">{e(nxt or "nothing queued")}'
                    "</span></div>")
    if not rows:
        return ""
    return ('<section class="fridaywrap" id="friday"><h3 class="area">The '
            f'{e(day)} hour</h3>' + "".join(rows) + "</section>")


def route_views(V):
    """Today answers one question — what do I do now — and everything built
    for deciding moves to the Plate (28 Sep, her call).

    The builders above each drop their card on Today; this is the one place
    that decides where cards live, run once the page is built, so moving a
    card is a line here rather than surgery in the builder that made it.
    Before this Today held about fifteen cards and the same task could show
    four times on it ("Load the house plans into the app": horizons, front by
    front, not today, the week ahead) — which is where the paralysis came
    from.
    """
    def has(x, *marks):
        return any(m in x[:300] for m in marks)

    # Today's work column. The week grid and the deciding cards go to the
    # Plate; "Front by front" goes entirely — the Plate IS that list,
    # grouped by area, with every task under it.
    keep, to_plate, to_plate_rail = [], [], []
    for x in V["today"]:
        if has(x, 'class="weekstrip"'):
            to_plate.append(x)
        elif has(x, 'id="fronts"'):
            continue
        elif has(x, 'class="hzcard"', 'class="offercard"', 'class="bscard"'):
            to_plate_rail.append(x)
        else:
            keep.append(x)
    # The three things lead: they are the answer to the question the page
    # asks. The plan card is several entries (its open tag, the nudge, the
    # evening check, the plan itself, its close), taken as one slice.
    try:
        a = next(i for i, x in enumerate(keep) if has(x, 'id="today" class="todaywrap"'))
        z = next(i for i in range(a + 1, len(keep)) if keep[i].strip() == "</section>")
        first = next((i for i, x in enumerate(keep) if x.lstrip().startswith("<section")), a)
        if first < a:
            keep = keep[:first] + keep[a:z + 1] + keep[first:a] + keep[z + 1:]
    except StopIteration:
        pass
    V["today"] = keep

    # The rail: group entries into cards first (the habits card arrives as
    # a dozen pieces), then sort each card to its place.
    cards = []
    for x in V["todayrail"]:
        if not cards or x.lstrip().startswith(("<section", '<details class="ghost intwrap"')):
            cards.append(x)
        else:
            cards[-1] += x
    order = ('class="whenwrap', 'rhythmcard', 'daycard')
    rail, to_season, to_week = [], [], []
    for c in cards:
        if has(c, "routinecard"):
            continue        # its two buttons sit on the plan card and header
        elif has(c, 'class="forecast"'):
            # Whether the fortnight fits is planning, so it lives on the
            # Plate's Week view (7 Oct); Today keeps one behind figure.
            to_week.append(c)
        elif has(c, "cdcard", "intwrap"):
            to_season.append(c)
        elif has(c, 'area">Also needs you<'):
            # Gone from the Plate (7 Oct): its fronts are the Plate's own
            # Needs you, and its people lead People's first view.
            continue
        elif has(c, "Where your attention went"):
            # Deciding, not doing: the Plate's rail (28 Sep).
            to_plate_rail.append(c)
        else:
            rail.append(c)

    def rank(c):
        for i, m in enumerate(order):
            if has(c, m):
                return i
        return len(order)
    V["todayrail"] = sorted(rail, key=rank)

    # On the Plate the week grid sits under the tiles, before the list it
    # plans from; the deciding cards take the rail beside the list.
    pos = next((i + 1 for i, x in enumerate(V["plate"])
                if has(x, 'class="tiles"')), 0)
    # The week grid is the Plate's Week view of its own (28 Sep): planning
    # the week wants the whole width, not a card between the tiles and the list.
    V["week"] = to_plate + to_week + list(V.get("week") or [])
    V["platerail"] = to_plate_rail + list(V.get("platerail") or [])
    V["season"].extend(to_season)


# When this build began reading the brain. Builds overlap all day (the
# server after each tap, each Claude session after its edits), and the one
# that began later read the newer files. 8 Oct: she approved the security
# card, the page reloaded, and a build that had started a few seconds
# before her tap finished after it and put the card back for half a minute.
STARTED = 0.0


def _write_newest(path, text):
    """Write a generated page, unless a build that started after this one
    has already written it: that page is newer than anything this build
    read. Atomic, so a reload never catches half a page."""
    stamps = os.path.join(BRAIN, ".build-stamps.json")
    key = os.path.basename(path)
    try:
        import fcntl
    except ImportError:              # Windows: no lock, the check still helps
        fcntl = None
    with open(os.path.join(BRAIN, ".build.lock"), "a") as lk:
        if fcntl:
            fcntl.flock(lk, fcntl.LOCK_EX)
        try:
            try:
                with open(stamps, encoding="utf-8") as f:
                    seen = json.load(f)
            except (OSError, ValueError):
                seen = {}
            last = seen.get(key) or 0
            # A stamp from the future is a clock that moved, not a newer
            # build; it must never freeze the page.
            if STARTED < last <= time.time() + 60:
                return False
            tmp = path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                f.write(text)
            os.replace(tmp, path)
            seen[key] = STARTED
            with open(stamps + ".tmp", "w", encoding="utf-8") as f:
                json.dump(seen, f)
            os.replace(stamps + ".tmp", stamps)
            return True
        finally:
            if fcntl:
                fcntl.flock(lk, fcntl.LOCK_UN)


def build():
    global STARTED
    STARTED = time.time()
    cfg = M.load_config()
    ws = M.load(cfg=cfg)
    global PRESENTING, PRESENT_HIDDEN_KEYS
    import privacy as _PRIV
    PRESENTING = _PRIV.presenting()
    PRESENT_HIDDEN_KEYS = set()
    if PRESENTING:
        # The hidden areas' workstreams go before anything is built from
        # them, and the money card with them (finance.on_page off, in this
        # build's copy of config only).
        # privacy.present_filter: the hidden areas, anything naming family
        # or friends, and every note go; the same rules map.py and rooms.py
        # apply.
        global PRESENT_NAMES_RX, PRESENT_KEPT_KEYS
        ws, PRESENT_HIDDEN_KEYS, PRESENT_NAMES_RX = _PRIV.present_filter(
            ws, M.load_people(), PRESENTING["areas"])
        PRESENT_KEPT_KEYS = {MD.taskkey(MD.bare(t["text"]))
                             for w in ws for t in w.get("tasks") or []}
        cfg = dict(cfg, finance=dict(cfg.get("finance") or {}, on_page=False))
    b = M.briefing(ws, cfg)
    # Presenting: no queue at all. Her asks and Claude's outcomes are
    # written about her life, and they feed For you and the drawers.
    q = [] if PRESENTING else queue_items()
    pending = [x for x in q if x["status"] in ("pending", "working")]
    today = date.today()

    urgent = [w for w in b["live"] if w["flags"]]
    calm = [w for w in b["live"] if not w["flags"]]
    closed = b["closed"]

    # Presenting: no people at all. The People tab, Quick replies, name
    # links and For you's people items all come from this one list.
    # Switched off under the gear (parts.py), the same: none at all.
    import parts as PARTS
    people = ([] if PRESENTING or not PARTS.on("people", cfg)
              else M.load_people(today=today))
    warm = [pp for pp in people if pp["flags"]]
    rest = [pp for pp in people if not pp["flags"]]
    # Task text can now point at people: longest names first so "Frankie Chang"
    # wins over "Frankie". Skip very short names — too many false hits.
    global PERSON_NAMES, PERSON_ALIAS
    # The names she actually writes. "Call Mum" should reach Maman, whose
    # entry lists Mum as an alias — matching only the filed name meant the
    # word she uses every day linked to nothing.
    PERSON_ALIAS = {}
    for pp in people:
        for al in pp.get("also", []):
            if len(al) >= 3 and al.lower() != pp["name"].lower():
                PERSON_ALIAS.setdefault(al, pp["name"])
    PERSON_NAMES = sorted((pp["name"] for pp in people if len(pp["name"]) >= 3),
                          key=len, reverse=True)
    global WS_NAMES
    WS_NAMES = sorted((w2["name"] for w2 in b["live"] if len(w2["name"]) >= 4),
                      key=len, reverse=True)

    # What Claude prepared, attached to the thing it belongs to. A finished
    # queue outcome names its workstream explicitly ('in the workstream "X"')
    # and also mentions the people and words of the work — match both ways,
    # so the train options surface on the Frankie hero, not only in the
    # Claude tab's archive.
    global WS_OUTCOMES
    WS_OUTCOMES = {}
    _cut = (today - __import__("datetime").timedelta(days=7)).isoformat()
    for _it in q:
        if _it["status"] != "done" or not _it["outcome"]:
            continue
        if (_it["created"] or "")[:10] < _cut:
            continue
        blob = ((_it["title"] or "") + " " + (_it["body"] or "")
                + " " + (_it["outcome"] or "")[:2000])
        explicit = set()
        for m_ in re.finditer(r'workstream\s+[“"]([^”"]+)[”"]', blob):
            explicit.add(m_.group(1).strip().lower())
        btoks = _sig_tokens(blob)
        tokhits = []
        for w2 in b["live"]:
            if w2["name"].lower() in explicit:
                continue
            shared = _sig_tokens(w2["name"]) & btoks
            if len(shared) >= 2 or any(len(x) >= 6 for x in shared):
                tokhits.append(w2["name"].lower())
        # Explicit mentions ALWAYS attach; token guesses fill what's left.
        # (A set sliced unsorted here once dropped the hero at random.)
        for h_ in (sorted(explicit) + sorted(tokhits))[:4]:
            WS_OUTCOMES.setdefault(h_, []).append(_it)
    for _v in WS_OUTCOMES.values():
        _v.sort(key=lambda x: x["created"], reverse=True)
    # And the reverse: which open tasks mention each person, so their row can
    # answer "what's happening that involves them" without a hunt.
    mention_map = {}
    for w2 in ws:
        if not w2["live"]:
            continue
        for t2 in w2["tasks"]:
            if t2["done"] or t2.get("parked") or t2.get("dropped"):
                continue
            for nm in PERSON_NAMES:
                if re.search(r"\b" + re.escape(nm) + r"\b", t2["text"]):
                    mention_map.setdefault(nm, []).append((w2["name"], t2["text"]))
                    break                      # longest name wins; one credit per task
    for pp in people:
        pp["mentions"] = mention_map.get(pp["name"], [])[:5]

    # Four views, one file. Tabs are the architecture now: Today is the
    # morning ritual, Plate is the work ledger, People is the relationships
    # ledger, Claude is the delegation console.
    # "todayrail" is Today's right column in the 2026 redesign: everything
    # that is awareness rather than action — habits, forecast, questions,
    # the digest, interests. The wide left column stays the work itself, so
    # the hero never competes with status for attention.
    V = {"today": [], "todayrail": [], "school": [], "jobs": [], "plate": [], "people": [],
         "peoplerail": [], "claude": [], "clauderail": [], "season": [],
         "news": [], "week": [], "life": [], "hood": [], "hoodrail": []}
    # For you, collected across the whole build and printed on Today once
    # everything that can propose something has spoken. Order is the order a
    # decision costs her: send it, answer it, confirm it, read it.
    tray_send, tray_answer, tray_confirm, tray_read = [], [], [], []

    # ================= TODAY =================
    # Each tab renders in its own file (tab_*.py). They are imported here,
    # not at the top, because they import their helpers from this module.
    import tab_today
    actpend, actqs, habits, parked_qhtml, today_md = tab_today.render(
        V=V, b=b, cfg=cfg, pending=pending, people=people, today=today,
        tray_answer=tray_answer, tray_confirm=tray_confirm, urgent=urgent,
        warm=warm, ws=ws, WS_OUTCOMES=WS_OUTCOMES)

    # ================= PLATE =================
    import tab_plate
    hood_inbox, hood_ref = tab_plate.render(V=V, b=b, calm=calm, cfg=cfg,
                                            closed=closed, today=today,
                                            urgent=urgent, ws=ws)

    # ================= PEOPLE =================
    import tab_people
    tab_people.render(V=V, cfg=cfg, people=people, today=today,
                      tray_confirm=tray_confirm, warm=warm)

    # ================= JOBS =================
    import tab_jobs
    tab_jobs.render(V=V, cfg=cfg, today=today)

    # ================= UNDER THE HOOD =================
    import tab_hood
    drafts = tab_hood.render(V=V, cfg=cfg, hood_inbox=hood_inbox,
                             hood_ref=hood_ref, parked_qhtml=parked_qhtml,
                             pending=pending, q=q, today=today,
                             tray_confirm=tray_confirm, tray_read=tray_read,
                             tray_send=tray_send)

    # ================= LIFE =================
    V["life"].append(PRESENT_NOTE if PRESENTING
                     else life_view(cfg, today, today_md, habits)
                     if PARTS.life_on(cfg) else part_off_note("life"))

    # ================= SEASON =================
    if PARTS.on("season", cfg):
        V["season"].append(PRESENT_NOTE if PRESENTING
                           else seasonview(cfg, date.today()))
        try:
            season_ics()
        except Exception:
            pass      # the feed is a bonus; it must never sink the page

    # ================= NEWS =================
    V["news"].append(newsview(cfg) if PARTS.on("news", cfg)
                     else part_off_note("news"))

    # The learning loop's lines: lessons to keep or bin, and the profile
    # block when it changed since she pasted it (tray_lessons.py).
    import tray_lessons
    tray_lessons.render(tray_send, tray_confirm)

    # One new feature a day for a new brain, first in For you (tips.py).
    import tips as TIPS
    _tip, tray_new = TIPS.current(cfg), []
    if _tip:
        tray_new.append(tray_item("tip:" + _tip["id"], "new", _tip["title"],
                                  TIPS.tray_body(_tip, e)))

    # For you, now that everything that can propose something has spoken.
    _fy = (PRESENT_NOTE if PRESENTING else
           tray_card(tray_new + tray_send + tray_answer + tray_confirm + tray_read,
                     mailcheck_button(cfg)[0]))
    V["today"] = [_fy if x == "<!--FORYOU-->" else x for x in V["today"]]

    route_views(V)
    # The countdowns route to the Season; switched off, they go with it.
    if not PARTS.on("season", cfg):
        V["season"] = [part_off_note("season")]
    if not PARTS.on("people", cfg):
        V["people"], V["peoplerail"] = [part_off_note("people")], []
    parts = []
    for vname in ("today", "school", "jobs", "plate", "week", "people", "life",
                  "season", "news", "hood"):
        inner = "".join(V[vname])
        if vname == "today" and V["todayrail"]:
            # wide work column + the awareness rail beside it
            inner = ('<div class="todaygrid"><div class="todaymain">' + inner
                     + '</div><aside class="todayrail">'
                     + "".join(V["todayrail"]) + "</aside></div>")
        if vname == "today":
            # Above both columns, full width: Orbit's deck (orb.py). Its own
            # slot, so the "three things lead" reorder never moves it.
            inner = "".join(V.get("todaytop") or []) + inner
        if vname in ("plate", "people"):
            # 60/40: the ranked list keeps a readable measure, and an opened
            # row's detail docks beside it instead of shoving the ranking
            # down the page. The dock is filled by moving the row's own body
            # into it, so every control inside keeps working.
            eyebrow = "Open row" if vname == "plate" else "Who this is"
            inner = (f'<div class="dockgrid"><div class="dockmain">' + inner
                     + f'</div><aside class="dockside" id="{vname}dock" hidden'
                     f' data-dockfor="{vname}">'
                     f'<div class="pdtop"><p class="eyebrow">{eyebrow}</p>'
                     '<button class="mini dockclose">Close</button></div>'
                     '<span class="wav"></span>'
                     '<h2 class="dockname"></h2>'
                     '<p class="coach dockwhy"></p>'
                     '<div class="pdstats dockstats"></div>'
                     '<div class="dockbody"></div></aside>'
                     # The dock column is 40% of a 1420px page and stands
                     # EMPTY until a row is opened. Anything permanently
                     # useful belongs in it — otherwise the width is reserved
                     # for a maybe and the list is squeezed for nothing.
                     # The Plate's rail is several cards; loose in the grid
                     # they flowed into BOTH columns, below the list, and the
                     # rows aligned into tall gaps (28 Sep review). One
                     # column beside the list, as the layout meant.
                     + ('<div class="platerail">' + "".join(V["platerail"])
                        + "</div>" if vname == "plate" and V.get("platerail")
                        else "".join(V.get(vname + "rail") or []))
                     + "</div>")
        if vname == "hood":
            # The jobs and the look on the left; connections, spend and the
            # brain's memory on the right. The sub-row reaches Usage and the
            # full list of conversations.
            inner = (CHROME.claude_subnav("hood", in_app=True)
                     + '<div class="claudegrid hoodgrid"><div class="claudemain">'
                     + inner + '</div><div class="clauderail">'
                     + "".join(V["hoodrail"]) + "</div></div>")
        if vname in ("plate", "week"):
            # List, Week, Map: one plate, three ways to look at it.
            inner = ('<div class="pvrow">'
                     + CHROME.plate_views("list" if vname == "plate" else "week",
                                          in_app=True)
                     + "</div>" + inner)
        if vname in ("life", "season") and PARTS.life_on(cfg):
            # Life's overview and its parts, one switch across all of them.
            # News left Life for a place of its own in the bar (8 Oct).
            inner = ('<div class="pvrow">'
                     + CHROME.life_views(vname, in_app=True)
                     + "</div>" + inner)
        if vname == "people" and PARTS.on("people", cfg):
            # List, Circles: the same people, as rows or on rings.
            inner = ('<div class="pvrow">' + CHROME.people_views("needs", in_app=True)
                     + "</div>" + inner)
        parts.append(f'<div class="view" data-view="{vname}">' + inner + "</div>")

    # Answers, grafted back onto the rows that asked for them. Outside the tab
    # views because one task row appears on the plan, the plate and in a
    # drawer, and all three deserve the pill.
    parts.append(ready_templates(ready_marks(drafts, q, ws, today_md)))

    # The workstream drawer: every live project as a little side screen,
    # opened by any Details button. Lives outside the tab views so it works
    # from Today's hero and the Plate alike.
    _sources = cfg.get("sources", []) or []
    # The speed reader lives outside the tab views: any page text can call
    # window.rsvpRead(text, title) — News uses it today, others can later.
    parts.append(
        '<div id="rsvp" class="rsvp" role="dialog" aria-modal="true"'
        ' aria-label="Speed reader" hidden><div class="rsvpinner">'
        '<p class="rsvptitle meta" id="rsvptitle"></p>'
        # A class reading's warning: what the fast read leaves behind.
        '<p class="rsvpwarn" id="rsvpwarn" hidden><span></span>'
        '<button class="mini" id="rsvpopen">Open the PDF</button></p>'
        '<div class="rsvpword"><span class="rpre"></span>'
        '<span class="rpiv"></span><span class="rpost"></span></div>'
        '<div class="rsvpbar"><i></i></div>'
        '<div class="rsvpctl">'
        '<button class="mini" id="rsvpprev" hidden>&lsaquo; previous</button>'
        '<button class="mini" id="rsvpslow" title="Slower">&minus;</button>'
        '<button class="mini" id="rsvpplay">Pause</button>'
        '<button class="mini" id="rsvpfast" title="Faster">+</button>'
        '<span class="meta" id="rsvpwpm"></span>'
        '<button class="mini" id="rsvpnext" hidden>next &rsaquo;</button>'
        '<button class="mini" id="rsvpclose">Close</button></div>'
        '<p class="rsvphint">space pauses &middot; &larr; &rarr; step words '
        "&middot; &uarr; &darr; previous / next article &middot; esc "
        "closes</p></div></div>")
    parts.append('<aside id="wsdrawer" class="wsdrawer" hidden'
                 ' aria-label="Workstream details">'
                 '<button class="mini wsdclose" id="wsdclose">&times; close</button>'
                 + "".join(wsdetail(w, _sources) for w in b["live"])
                 + "</aside>")

    # One bar for the whole app, index.html included — see chrome.py. The
    # page has no foot since 28 Sep: it said "Generated … from the markdown
    # in brain/", a note for whoever maintains the page, and the bar's pill
    # already says on every page when the brain last synced.

    owner = cfg.get("owner", "My")
    ap_cur = cfg.get("appearance", {}) or {}
    ap_accent = ap_cur.get("accent", "olive")
    ap_base = ap_cur.get("base", "warm")
    ap_font = ap_cur.get("font", "editorial")
    ap_style = ap_cur.get("style", "workroom")
    _circles = list(M.circles(cfg).values())
    circleopts = "".join(
        f'<option{" selected" if c["name"]=="Friends" else ""}>{e(c["name"])}</option>'
        for c in _circles)
    circlesjs = MD.json_for_script([[c["name"], (c["every"] or "no set rhythm")]
                                    for c in _circles if c["name"].lower() not in ("one-off","oneoff")])
    # One pass, so a value holding another placeholder's name stays text.
    _head = {"TITLE": e(f"{owner} brain"), "FONT": ap_font,
             "STYLE": ap_style, "PALETTE": palette_css(cfg)}
    page = (re.sub(r"__(TITLE|FONT|STYLE|PALETTE)__",
                   lambda m: _head[m.group(1)], HEAD) + f"""
{CHROME.header_html("today", owner=owner, in_app=True,
                    legend_html='<span class="skinx skinx-legend">' + _legend_html(b) + "</span>")}
<div class="banner" id="filebanner" hidden>
  Read-only: this is the page opened as a file. Double-click <b>Open Brain</b>
  for the live version.
</div>
<main>
{''.join(parts)}
</main>
<div id="runbar" class="runbar needs-server" data-pending="{len(pending)}"{"" if pending else " hidden"}
     title="Tap to open the activity drawer">
  <img src="logo-96.png?v=5" width="20" height="20" alt="">
  <span class="rbspin" id="rb-spin" hidden aria-hidden="true"></span>
  <span id="rb-txt">{len(pending)} waiting for {AG.short()}</span>
  <button class="rb-go" id="rb-run">Run now</button>
</div>
<aside id="actdrawer" class="actdrawer" hidden aria-label="{AG.short()} activity">
  <div class="acthead"><b id="act-title">{AG.short()}</b>
    <button class="mini" id="act-close">&times; close</button></div>
  <p class="meta actstatus" id="act-status"></p>
  <div id="act-feed" class="feed actfeed" hidden></div>
  {actpend}
  {actqs}
  <div class="actacts">
    <button class="mini" id="act-run">Work the queue</button>
    <a class="mini actlink" href="#/hood">Jobs and runs</a>
  </div>
</aside>
""" + _dumpcopy(SHEET, fresh=not b["live"] and not people, cfg=cfg)
            # page.js says "Claude" only in fixed wording: named for the agent
            + AG.say(SCRIPT + PEOPLE_SCRIPT)
            + TALKCHAT + CHROME.ask_block()
            + TOUR.brain_block() + TALK.block() + _PINTRO_JS
            + "<script>" + AG.say(__import__("tips").SCRIPT) + "</script>" + "\n</body></html>")
    page = page.replace("__CIRCLEOPTS__", circleopts).replace("__CIRCLESJS__", circlesjs)
    # The calendar-block button exists only where calendar_write can work.
    page = page.replace("__SZCAL__", "1" if sys.platform == "darwin" else "0")

    # A page with broken script is worse than a stale page: it renders blank
    # AND kills the auto-refresh that would have rescued it. So the inline
    # script must parse before the old page is replaced. Node does the check
    # when present; without node the write proceeds as before.
    import shutil as _sh
    import subprocess as _sp
    import tempfile as _tf
    node = _sh.which("node")
    if node:
        # EVERY script block, not just the first — the People script is its own
        # <script> precisely so it survives the main one, and a gate that only
        # checks script #1 would let a broken script #2 ship silently.
        for js in re.findall(r"<script>(.*?)</script>", page, re.S):
            with _tf.NamedTemporaryFile("w", suffix=".js", delete=False,
                                        encoding="utf-8") as tmp:
                tmp.write(js)
            try:
                r = _sp.run([node, "--check", tmp.name], capture_output=True,
                            text=True, timeout=20)
                if r.returncode != 0:
                    raise SystemExit("REFUSING to write index.html — a page "
                                     "script does not parse:\n"
                                     + r.stderr.strip()[:600])
            finally:
                os.unlink(tmp.name)

    # The shared look for pages this script does not render (sessions.html):
    # the same font faces and the same :root tokens, regenerated on every
    # build so the appearance panel reaches them too.
    faces = "\n".join(re.findall(r"@font-face\{[^}]+\}", HEAD))
    faces += ("\n@font-face{font-family:'Petrona';"
              "src:url('fonts/petrona-i.woff2') format('woff2');"
              "font-weight:400 600;font-style:italic;font-display:swap}")
    with open(os.path.join(BRAIN, "appearance.css"), "w", encoding="utf-8") as f:
        f.write(faces + "\n" + palette_css(cfg))

    # sessions.html is hand-written, but its Claude sub-row must be the same
    # strip chrome.py renders on the Claude tab and usage.html — a pasted
    # copy drifted apart once already, which read as three different bars.
    # Re-stamp it every build; the fresh markup matches the pattern again,
    # so this stays idempotent.
    spath = os.path.join(BRAIN, "sessions.html")
    try:
        with open(spath, encoding="utf-8") as f:
            sh = f.read()
        fresh = CHROME.claude_subnav("sessions")
        new = re.sub(r"<style>\s*\.clsub\{.*?</nav>", lambda m: fresh, sh,
                     count=1, flags=re.S)
        # The top bar too (28 Sep): the page's own pasted copy still listed
        # Rooms, Map and Claude. The conversations light the gear's family.
        new = re.sub(r'<nav class="appnav">.*?</nav>',
                     lambda m: CHROME.nav_html("sessions", cls="appnav"),
                     new, count=1, flags=re.S)
        if 'class="hoodlink' not in new:
            new = new.replace("✦ Ask</button></div></header>",
                              "✦ Ask</button>" + CHROME.hood_link("sessions")
                              + "</div></header>", 1)
        new = new.replace(
            '<div style="padding:4px 24px 8px;border-bottom:1px solid '
            'var(--rule);background:var(--card)">' + fresh,
            '<div style="padding:10px 24px 0">' + fresh)
        # The whole bar since 28 Sep: the page's own strip carried the
        # Settings/Usage/Conversations switch and the "needs an answer" pill
        # inside it, the third kind of header. It is chrome's bar now, like
        # every page's, with the switch and the pill in the row under it.
        # Marked, so the next build finds its own copy again.
        _pill = re.search(r'<button id="needspill".*?</button>', new, flags=re.S)
        _bar = ('<div class="sesshdr"><!--bar--><style>' + CHROME.NAV_CSS
                + CHROME.HEADER_CSS + "</style>"
                + CHROME.header_html(
                    "sessions", owner=owner,
                    sub_html='<div id="clwrap">' + fresh + "</div>"
                    + (_pill.group(0) if _pill else ""))
                + "<!--/bar--></div>")
        new = re.sub(r'<div class="sesshdr">(?:<!--bar-->.*?<!--/bar-->'
                     r'|<header class="apptop">.*?</header>\s*)</div>',
                     lambda m: _bar, new, count=1, flags=re.S)
        # The style attribute rides the same re-stamp: sessions.html links
        # appearance.css, so the attribute is all it needs to wear the style.
        new = re.sub(r'<html lang="en"[^>]*>',
                     '<html lang="en" data-style="%s">' % ap_style,
                     new, count=1)
        if "brain-style" not in new:
            new = new.replace(
                '<link rel="stylesheet" href="appearance.css">',
                '<link rel="stylesheet" href="appearance.css">'
                "<script>try{var _bs=localStorage.getItem('brain-style');"
                "if(_bs)document.documentElement.setAttribute('data-style',_bs);}"
                "catch(e){}</script>", 1)
        # The Ask panel rides the same re-stamp: sessions.html carried a
        # pasted copy that had already fallen behind chrome.py's (no chats
        # list, no model picker, no full screen). The block is the last
        # thing before </body>, so the greedy match ends at its own script.
        # ask_block() brings its own <style> in front of the panel, so the
        # match takes any earlier copies of that style with it. Matching from
        # the panel alone left the old style behind on every build, and 460
        # builds later the page carried 460 copies of it (5 MB).
        new = re.sub(r'(?:<style>\s*\.askopen\{.*?</style>\s*)*'
                     r'<div class="askscrim".*</script>',
                     lambda m: CHROME.ask_block(), new, count=1, flags=re.S)
        if new != sh:
            with open(spath, "w", encoding="utf-8") as f:
                f.write(new)
    except Exception:
        pass          # a missing sessions.html must not sink the build

    if PRESENTING:
        page = re.sub(r"(<body[^>]*>)", lambda m: m.group(1) + PRESENT_BANNER,
                      page, count=1)
    _write_newest(OUT, page)

    # The usage page rides every build: it links appearance.css (written just
    # above) and shares the chrome, so building them together is what keeps
    # them from drifting apart.
    import usage_page
    usage_page.build(cfg)
    # The Privacy page shares the Usage page's stylesheet and chrome
    # (privacy_page.py), so they are built together too.
    import privacy_page
    privacy_page.build(cfg)

    # The kitchen page rides along too — same chrome, same palette. A
    # missing recipe library must never sink the main build.
    try:
        import cook as _cook
        _cook.build(cfg)
    except Exception:
        pass

    return OUT, len(ws), len(pending)


# The page's stylesheet and main script live as real files in page/ beside
# this one, so they can be read, highlighted and checked as CSS and
# JavaScript rather than as Python strings. They are inlined here, byte for
# byte, so the built page stays one self-contained file.
PAGE_DIR = os.path.join(HERE, "page")


def _page_file(name):
    with open(os.path.join(PAGE_DIR, name), encoding="utf-8") as f:
        return f.read()


HEAD = """<!doctype html>
<html lang="en" data-font="__FONT__" data-style="__STYLE__"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>__TITLE__</title>
<link rel="manifest" href="manifest.webmanifest">
<link rel="icon" href="logo-192.png?v=5" type="image/png">
<link rel="apple-touch-icon" href="logo-180.png?v=5">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-title" content="Brain">
<meta name="theme-color" content="#f4efe6" media="(prefers-color-scheme: light)">
<meta name="theme-color" content="#1c1b16" media="(prefers-color-scheme: dark)">
<script>if("serviceWorker" in navigator)navigator.serviceWorker.register("sw.js")</script>
<style>
""" + _page_file("page.css") + CHROME.HEADER_CSS + """</style>
<script>document.addEventListener("DOMContentLoaded",function(){
requestAnimationFrame(function(){var s=document.getElementById("bootsk");
if(s){s.classList.add("gone");setTimeout(function(){s.remove()},250)}})})</script>
</head><body>
<div class="bootsk" id="bootsk" aria-hidden="true">
<div class="bootsk-top"><i class="logo"></i><i class="name"></i><i class="nav"></i><i class="btn"></i><i class="ask"></i></div>
<div class="bootsk-deck">
<div class="bootsk-col"><i class="h"></i><i class="row"></i><i class="row short"></i><i class="row"></i><i class="h"></i><i class="row short"></i><i class="row short"></i></div>
<div class="bootsk-mid"><i class="orb"></i><i class="line"></i><i class="sub"></i></div>
<div class="bootsk-col"><i class="h"></i><i class="row"></i><i class="row short"></i><i class="h"></i><i class="card"></i><i class="card"></i></div>
</div></div>
"""

# The quick-capture sheet. Everything about it is thumb-first: the button sits
# in the bottom-right thumb arc, the sheet rises from the bottom edge, and the
# send button stays low rather than above the keyboard. It exists because the
# alternative was scrolling the whole page to reach the box, which is exactly
# the friction that kills a capture habit.
SHEET = """
<div id="tscrim" class="scrim" hidden></div>
<div id="wscrim" class="scrim" hidden></div>
<div id="weekdlg" class="taskdlg" role="dialog" aria-modal="true" hidden>
  <p class="tdtitle" id="wdtitle"></p>
  <div class="tdopts" id="wdopts"></div>
</div>
<div id="taskdlg" class="taskdlg" role="dialog" aria-modal="true" hidden>
  <p class="tdtitle" id="tdtitle"></p>
  <p class="tdsub" id="tdsub" hidden></p>
  <div class="tdopts">
    <button class="tdopt" id="td-done" data-ta="done">
      <span class="tdico ok">&#10003;</span>Mark it done</button>
    <button class="tdopt" id="td-undone" data-ta="undone" hidden>
      <span class="tdico">&#8634;</span>Put it back</button>
    <p class="tdgrp">When</p>
    <button class="tdopt" id="td-due">
      <span class="tdico soon">&#9200;</span>Set a deadline&hellip;</button>
    <div class="parkrow" id="duerow" hidden>
      <button class="preset" data-duedays="1">Tomorrow</button>
      <button class="preset" data-duephrase="this week">This week</button>
      <button class="preset" data-duephrase="this month">This month</button>
      <input type="date" id="duedate">
      <button class="primary" id="duego">Set</button>
    </div>
    <button class="tdopt" id="td-est">
      <span class="tdico">&#8987;</span>How long will it take&hellip;</button>
    <div class="parkrow" id="estrow" hidden>
      <button class="estpreset" data-estmin="15">15m</button>
      <button class="estpreset" data-estmin="30">30m</button>
      <button class="estpreset" data-estmin="60">1h</button>
      <button class="estpreset" data-estmin="120">2h</button>
      <button class="estpreset" data-estmin="240">4h</button>
      <button class="mini" id="estclear">clear</button>
    </div>
    <button class="tdopt" id="td-unpark" hidden>
      <span class="tdico ok">&#8617;</span>Un-park: back on the list</button>
    <button class="tdopt" id="td-park">
      <span class="tdico wait">&#10073;&#10073;</span>Park until&hellip;</button>
    <div class="parkrow" id="parkrow" hidden>
      <button class="preset" data-days="7">Next week</button>
      <button class="preset" data-days="30">In a month</button>
      <input type="date" id="parkdate">
      <button class="primary" id="parkgo">Park</button>
    </div>
    <button class="tdopt needs-server" id="td-block">
      <span class="tdico">&#128197;</span>Block time for it&hellip;</button>
    <div class="parkrow" id="blockrow" hidden>
      <input type="date" id="blockday">
      <input type="time" id="blocktime" step="900">
      <select id="blockmin"><option value="30">30m</option>
        <option value="60" selected>1h</option><option value="90">1h30</option>
        <option value="120">2h</option><option value="180">3h</option></select>
      <button class="primary" id="blockgo">Block it</button>
      <span class="mshelp">Goes into its own &ldquo;Brain&rdquo; calendar,
        separate from your other calendars.</span>
    </div>
    <p class="tdgrp">Change</p>
    <button class="tdopt" id="td-edit">
      <span class="tdico">&#9998;</span>Edit the wording&hellip;</button>
    <div class="parkrow" id="editrow" hidden>
      <input type="text" id="editline" maxlength="500" placeholder="New wording">
      <button class="primary" id="editgo">Save</button>
    </div>
    <button class="tdopt" id="td-drop" data-ta="drop">
      <span class="tdico bad">&times;</span>Drop it: not mine to do</button>
    <p class="tdgrp" id="plansep" hidden>On today&rsquo;s three</p>
    <button class="tdopt needs-server" id="td-kick" hidden>
      <span class="tdico">&#10005;</span>Kick it: the next best takes its place</button>
    <button class="tdopt needs-server" id="td-swap" hidden>
      <span class="tdico">&#8644;</span>Swap it for&hellip;</button>
    <div class="parkrow" id="swaprow" hidden></div>
    <button class="tdopt needs-server" id="td-planday" hidden>
      <span class="tdico">&#8594;</span>Not today: pick a day&hellip;</button>
    <div class="parkrow" id="dayrow" hidden></div>
    <div class="planmove" id="planmove" hidden>
      <button class="preset" id="td-up">&#8593; Move up</button>
      <button class="preset" id="td-down">&#8595; Move down</button>
    </div>
  </div>
  <button class="ghostbtn tdcancel" id="td-cancel">Cancel</button>
</div>
<div id="persondlg" class="taskdlg" role="dialog" aria-modal="true" hidden>
  <p class="tdtitle" id="pdtitle"></p>
  <div class="tdopts">
    <button class="tdopt" id="pd-rename">
      <span class="tdico">&#9998;</span>Rename&hellip;</button>
    <div class="parkrow" id="renamerow" hidden>
      <input type="text" id="renameline" maxlength="80" placeholder="New name">
      <button class="primary" id="renamego">Save</button>
    </div>
    <button class="tdopt" id="pd-merge">
      <span class="tdico">&#8646;</span>Merge into another person&hellip;</button>
    <div class="parkrow" id="mergerow" hidden>
      <input id="mergesel" list="peopledl" placeholder="type their name&hellip;">
      <button class="primary" id="mergego">Merge</button>
    </div>
    <button class="tdopt" id="pd-archive">
      <span class="tdico wait">&#10073;&#10073;</span>Archive: keep them, without a rhythm</button>
    <button class="tdopt" id="pd-delete">
      <span class="tdico bad">&times;</span>Delete from your people</button>
  </div>
  <button class="ghostbtn tdcancel" id="pd-cancel">Cancel</button>
</div>
<div id="promisedlg" class="taskdlg" role="dialog" aria-modal="true" hidden>
  <p class="tdtitle" id="prtitle"></p>
  <p class="prhint">Something you said you'd do for them. It sits under their
    name and stays on your list until it's ticked.</p>
  <div class="parkrow">
    <input type="text" id="prline" maxlength="200"
           placeholder="e.g. send the flat details to the agency">
    <button class="primary" id="prgo">Save</button>
  </div>
  <button class="ghostbtn tdcancel" id="pr-cancel">Cancel</button>
</div>
<div id="askdlg2" class="taskdlg" role="dialog" aria-modal="true" hidden>
  <p class="tdtitle" id="ad-title"></p>
  <p class="prhint" id="ad-hint" hidden></p>
  <div class="adfield" id="ad-f1"><label id="ad-l1" for="ad-i1"></label>
    <input type="text" id="ad-i1" maxlength="200"></div>
  <div class="adfield" id="ad-f2" hidden><label id="ad-l2" for="ad-i2"></label>
    <input type="text" id="ad-i2" maxlength="200"></div>
  <div class="adfield" id="ad-fsel" hidden><label id="ad-lsel" for="ad-sel"></label>
    <select id="ad-sel"></select></div>
  <label class="adcheck" id="ad-fchk" hidden>
    <input type="checkbox" id="ad-chk"><span id="ad-chkl"></span></label>
  <div class="adrow">
    <button class="primary" id="ad-go">Save</button>
    <button class="ghostbtn" id="ad-cancel">Cancel</button>
  </div>
</div>
<div id="tpldlg" class="taskdlg tpldlg" role="dialog" aria-modal="true" hidden>
  <p class="tdtitle" id="tpl-title"></p>
  <div id="tpl-list" class="tpllist"></div>
  <div id="tpl-edit" class="tpledit" hidden>
    <div class="adfield"><label for="tpl-name">Name</label>
      <input type="text" id="tpl-name" maxlength="80"></div>
    <div class="tplrow">
      <label>Channel <select id="tpl-channel">
        <option value="linkedin">LinkedIn</option>
        <option value="email">Email</option>
        <option value="message">Message</option></select></label>
      <label>Character limit <input type="text" id="tpl-limit" inputmode="numeric"
        size="4" placeholder="none"></label>
      <label>Once sent, they move to <select id="tpl-stage">
        <option value="">no change</option><option>to reach</option>
        <option>asked</option><option>talking</option><option>met</option></select></label>
    </div>
    <div class="adfield" id="tpl-subjrow"><label for="tpl-subject">Subject</label>
      <input type="text" id="tpl-subject" maxlength="140"></div>
    <textarea id="tpl-body" rows="8" spellcheck="true"></textarea>
    <p class="prhint">Fills in {first} {name} {company} {role} {how} {met} {where} {me}.
      Anything in [brackets] stays for you to write.</p>
    <div class="adrow">
      <button class="primary" id="tpl-save">Save template</button>
      <button class="ghostbtn" id="tpl-archive">Archive</button>
      <button class="ghostbtn" id="tpl-back">Back</button>
    </div>
  </div>
  <div id="tpl-draft" class="tpldraft" hidden>
    <p class="prhint" id="tpl-dmeta"></p>
    <input type="text" id="tpl-dsubject" class="tplsubj" hidden>
    <textarea id="tpl-dbody" rows="9" spellcheck="true"></textarea>
    <p class="tplcount" id="tpl-count"></p>
    <div class="adrow tplacts">
      <button class="primary" id="tpl-copy">Copy</button>
      <a class="act" id="tpl-profile" target="_blank" rel="noopener" hidden>Open their profile &#8599;</a>
      <button class="act" id="tpl-mail" hidden>Open in email</button>
      <button class="act" id="tpl-sent">Sent it</button>
      <button class="ghostbtn" id="tpl-keep">Keep as a draft</button>
      <button class="ghostbtn" id="tpl-other">Other templates</button>
    </div>
  </div>
  <div class="adrow tplfoot">
    <button class="ghostbtn" id="tpl-new">+ New template</button>
    <button class="ghostbtn" id="tpl-cancel">Close</button>
  </div>
</div>
<div id="lidlg" class="taskdlg lidlg" role="dialog" aria-modal="true" hidden>
  <p class="tdtitle">From LinkedIn</p>
  <p class="prhint" id="li-status">Looking for your LinkedIn export&hellip;</p>
  <div class="adrow" id="li-fillrow" hidden>
    <button class="primary" id="li-fill"></button></div>
  <details class="lihow"><summary>Get or update your export</summary>
    <p class="prhint">On LinkedIn: Settings, then Data privacy, then Get a copy of
      your data, and tick Connections. LinkedIn emails you a download link, usually
      within the hour. Download it and the brain finds it in Downloads, or upload
      it here.</p>
    <label class="attachbtn">Upload the export zip
      <input type="file" id="li-file" accept=".zip,application/zip" hidden></label>
  </details>
  <div class="adfield lirow"><label for="li-targets">Companies or fields you&rsquo;re
    aiming at (they rank first)</label>
    <span class="lirowin"><input type="text" id="li-targets" placeholder="e.g. McKinsey, climate, fintech">
    <button class="mini" id="li-tsave">Save</button></span></div>
  <input class="psearch" id="li-search" type="search" autocomplete="off"
         placeholder="Search your connections">
  <div id="li-list" class="lilist"></div>
  <button class="ghostbtn" id="li-more" hidden>Show more</button>
  <button class="ghostbtn tdcancel" id="li-cancel">Close</button>
</div>
<div id="dumpover" class="dumpover" hidden role="dialog" aria-modal="true" aria-label="Brain dump">
  <div class="dumpwrap">
    <button class="dumpx" id="dumpclose" aria-label="Close">&times;</button>
    __AISETUP__
    <div class="dumpcues">
      <p class="eyebrow">Just talk</p>
      <h2 class="dumph">__DUMPH__</h2>
      <p class="dumplead">__DUMPLEAD__</p>
      __DUMPCUES__
    </div>
    <div class="dumpwrite">
      <textarea id="dumpbox" placeholder="Start wherever and keep going. &ldquo;So I'm in my last year of a degree, I'm building an app on the side, and the thing on my mind is&hellip;&rdquo;"></textarea>
      <div class="dumpfoot">
        <button id="dumpmic" class="micbtn" aria-label="Dictate" aria-pressed="false">
          <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor"
               stroke-width="2" stroke-linecap="round" aria-hidden="true">
            <rect x="9" y="2" width="6" height="12" rx="3"/><path d="M5 11a7 7 0 0 0 14 0M12 18v4"/>
          </svg>
        </button>
        <label class="dumpsearch"><input type="checkbox" id="dumpfiles-cb" checked>
          Let Claude search my computer for context on what I mention</label>
        <span id="dumpnote" class="sheetnote"></span>
        <button id="dumpbuild" class="primary">__DUMPBTN__</button>
      </div>
    </div>
    <div id="dumpprog" class="dumpprog" hidden>
      <div class="dp-holder" aria-hidden="true"><video class="artvid " autoplay muted loop playsinline poster="art/thinking.png?v=2" width="120" height="120" aria-hidden="true"><source src="art/thinking.mp4?v=2" type="video/mp4"></video></div>
      <h2 class="dumph" id="dp-stage">Claude is reading&hellip;</h2>
      <p class="dumplead" id="dp-sub">Your words are being sorted into workstreams,
        people, dates and habits. This usually takes a few minutes. You can
        close this and it keeps working (watch it live in Jobs, under the hood).</p>
      <pre class="dp-tail" id="dp-tail"></pre>
      <p class="dp-elapsed" id="dp-elapsed"></p>
      <div id="dp-done" hidden>
        <div class="dp-holder"><video class="artvid " autoplay muted loop playsinline poster="art/celebrating.png?v=2" width="130" height="130" aria-hidden="true"><source src="art/celebrating.mp4?v=2" type="video/mp4"></video></div>
        <h2 class="dumph" id="dp-donehead">Your brain is built</h2>
        <p class="dumplead" id="dp-summary"></p>
        <p class="dumplead" id="dp-questions" hidden></p>
        <button class="primary" id="dp-tour">Show me around</button>
""" + ('<button class="ghostbtn" id="dp-sort">Sort your chat contacts</button>'
       if os.path.exists(os.path.join(BRAIN, ".beeper-client.json")) else "") + """
        <button class="ghostbtn" id="dp-open">Open your brain</button>
      </div>
    </div>
  </div>
</div>
<div id="scrim" class="scrim" hidden></div>
<div id="sheet" class="sheet" hidden role="dialog" aria-modal="true" aria-label="Capture">
  <div class="grab"></div>
  <div class="seg" role="tablist">
    <button class="segbtn on" data-dest="claude" role="tab" aria-selected="true">Tell Claude</button>
    <button class="segbtn" data-dest="save" role="tab" aria-selected="false">Just save it</button>
  </div>
  <p class="segnote" id="segnote" hidden></p>
  <p class="segwhat" id="segwhat">Saved word for word to your inbox. Nothing happens
    to it until Claude tidies up later. Use it when you just need it out of your head.</p>

  <div id="addform" class="addform" hidden>
    <div class="addseg">
      <button class="addbtn on" data-kind="note">Note</button>
      <button class="addbtn" data-kind="task">Task</button>
      <button class="addbtn" data-kind="waiting">Waiting on someone</button>
      <button class="addbtn" data-kind="workstream">New workstream</button>
      <button class="addbtn" data-kind="person">Person</button>
    </div>
    <div data-form="task">
      <select id="f-task-ws"></select>
      <input id="f-task-text" placeholder="What needs doing?">
      <input id="f-task-due" placeholder="Due (optional): a date, &ldquo;friday&rdquo;, &ldquo;this week&rdquo;&hellip;">
    </div>
    <div data-form="waiting" hidden>
      <input id="f-wait-what" placeholder="What are you waiting for?">
      <input id="f-wait-who" placeholder="From who?">
      <input id="f-wait-chase" placeholder="Chase when? (e.g. no reply by Friday)">
    </div>
    <div data-form="workstream" hidden>
      <input id="f-ws-name" placeholder="Name it">
      <select id="f-ws-area">
        <option value="Dad">Dad</option>
        <option value="School">School</option>
        <option value="Business">Business</option>
        <option value="Personal" selected>Personal</option>
      </select>
      <select id="f-ws-ball">
        <option value="me">Ball is with me</option>
        <option value="them">Waiting on someone else</option>
        <option value="nobody">Nobody / not started</option>
      </select>
      <input id="f-ws-next" placeholder="Next physical step (optional)">
      <input id="f-ws-due" type="date">
    </div>
    <div data-form="person" hidden>
      <input id="f-p-name" placeholder="Who?">
      <select id="f-p-every">
        <option value="3 days">Every few days</option>
        <option value="weekly">Weekly</option>
        <option value="2 weeks">Every couple of weeks</option>
        <option value="monthly" selected>Monthly</option>
        <option value="quarterly">Every few months</option>
      </select>
      <select id="f-p-circle">__CIRCLEOPTS__</select>
      <select id="f-p-ball">
        <option value="nobody" selected>We are even</option>
        <option value="me">I owe them a reply</option>
        <option value="them">They owe me one</option>
      </select>
      <input id="f-p-where" placeholder="Where do they live? (optional)">
      <input id="f-p-bday" placeholder="Birthday, MM-DD (optional)">
      <input id="f-p-how" placeholder="How do you know them? (optional)">
      <input id="f-p-role" placeholder="Their job title (optional)">
      <input id="f-p-company" placeholder="Where they work (optional)">
      <input id="f-p-linkedin" placeholder="LinkedIn link or handle (optional)">
      <label class="chk"><input type="checkbox" id="f-p-focus">
        Someone I want to grow closer to this season</label>
    </div>
  </div>

  <div id="chatform" class="addform" hidden>
    <select id="f-chat-person"></select>
    <p class="segwhat">Paste the chat text (or attach a screenshot below). Claude files
      anything you promised on that person and saves nothing else from the
      chat.</p>
  </div>
  <textarea id="sheetbox" rows="4"
    placeholder="What's on your mind? Tap the mic and just say it."></textarea>
  <div id="sheetmode" class="sheetmode" hidden>
    <select id="sheetmodesel">
      <option value="just-do-it">Just do it</option>
      <option value="update">Daily update: tick off what happened</option>
      <option value="dump">Organize a brain-dump</option>
      <option value="journal">Journal my day</option>
      <option value="investigate">Look into it first</option>
      <option value="draft">Draft something for me</option>
      <option value="question">Just answer the question</option>
      <option value="critic">Tear it apart</option>
      <option value="consult">Run the frameworks on it</option>
      <option value="chat">From a chat: file what I promised</option>
    </select>
    <select id="sheetmodel" title="Bigger models think harder and use more of your plan">
      <option value="haiku">Haiku: fastest, for filing and simple asks</option>
      <option value="sonnet">Sonnet: balanced, for most things</option>
      <option value="opus">Opus: deepest, for hard thinking</option>
      <option value="fable">Fable: the writer, for drafts and prose (costs the most)</option>
    </select>
    <div class="attachrow">
      <label class="attachbtn">
        <input type="file" id="sheetfiles" multiple hidden
               accept=".pdf,.png,.jpg,.jpeg,.webp,.gif,.txt,.md,.csv,.docx,.xlsx,.ics">
        Attach documents
      </label>
      <span id="filelist" class="filelist"></span>
    </div>
  </div>
  <div class="sheetrow">
    <button id="mic" class="micbtn" aria-label="Dictate" aria-pressed="false">
      <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor"
           stroke-width="2" stroke-linecap="round" aria-hidden="true">
        <rect x="9" y="2" width="6" height="12" rx="3"/>
        <path d="M5 11a7 7 0 0 0 14 0M12 18v4"/>
      </svg>
    </button>
    <span id="sheetnote" class="sheetnote"></span>
    <button id="sheetrun" class="ghostbtn" hidden>Run now</button>
    <button id="sheetsend" class="primary">Save</button>
    <button id="sheetclose" class="ghostbtn">Close <kbd>esc</kbd></button>
  </div>
</div>
"""

# ── "Talk it through": the box, scoped to one task or person ──────────────
# The speech-bubble button on a task row (and "Talk it through" on a person)
# used to open a drawer of its own. Since 28 Sep it opens the box on every
# page (chrome.py) already holding that task or person: the same context
# pack context.py builds, the same conversation record on the Sessions page,
# one box instead of two. Capture phase, so the row's own click never fires.
TALKCHAT = """
<script>
(function(){
  // A task's own talk button folded into its ✦ on 7 Oct (page.js); a
  // person's stays here.
  document.addEventListener('click', function(ev){
    if(!ev.target.closest || !window.brainBox) return;
    var pb = ev.target.closest('[data-claudetalkperson]');
    if(pb){
      ev.preventDefault(); ev.stopPropagation();
      window.brainBox.open({scope: {kind: 'person',
                                    name: pb.dataset.claudetalkperson}});
    }
  }, true);
})();
</script>
"""

# The page's one big script — the tab router and every button on the page.
# It lives in page/page.js so an editor can read it as JavaScript.
SCRIPT = "\n<script>\n" + _page_file("page.js") + "</script>\n"


# A deliberately separate, self-contained script. The People page's filter and
# remembered-collapse must keep working even if the big main script throws
# somewhere upstream, so they live here with no dependency on its scope.
PEOPLE_SCRIPT = """
<script>
(function(){
  function lg(k){ try { return localStorage.getItem(k); } catch(e){ return null; } }
  function ls(k, v){ try { localStorage.setItem(k, v); } catch(e){} }
  var pf = '', pq = '', pplace = '', chipLabel = '';

  // Circles start OPEN — the people are the page, and having to click into
  // every band to see anyone was the complaint. One preference sets the
  // default; each circle still remembers being opened or shut by hand.
  var circDefault = lg('circles-default') !== '0';
  document.querySelectorAll('.csection').forEach(function(d){
    var key = 'ppl-open:' + d.dataset.circle, s = lg(key);
    d.open = (s === '0') ? false : (s === '1') ? true : circDefault;
    // A filter opens circles by itself; persisting THAT would quietly undo
    // every circle she collapsed by hand. Only her own clicks are saved.
    d.addEventListener('toggle', function(){
      if(!pf && !pq && !pplace) ls(key, d.open ? '1' : '0'); });
  });
  (function(){
    var btn = document.getElementById('shopen');
    if(!btn) return;
    function label(){ btn.textContent = circDefault ? 'Collapse all' : 'Open all'; }
    label();
    btn.onclick = function(){
      circDefault = !circDefault;
      ls('circles-default', circDefault ? '1' : '0');
      document.querySelectorAll('.csection').forEach(function(d){
        ls('ppl-open:' + d.dataset.circle, circDefault ? '1' : '0');
        d.open = circDefault;
      });
      label();
      // This runs inside the People script, which is deliberately isolated
      // from the main one \u2014 so it cannot reach the main script's toast().
      btn.title = circDefault ? 'Circles start open. Click to collapse them.'
                              : 'Circles start collapsed. Click to open them.';
    };
  })();

  function match(r){
    if(pf){
      var fl = (r.dataset.flags || '').split(/\\s+/);
      if(pf === 'owe-them'){ if(fl.indexOf('owed') < 0) return false; }
      else if(pf === 'owe-me'){ if(r.dataset.ball !== 'them') return false; }
      else if(pf === 'quiet'){ if(fl.indexOf('overdue') < 0 && fl.indexOf('never') < 0) return false; }
      else if(pf === 'focus'){ if(r.dataset.focus !== '1') return false; }
    }
    // Search matches the names a person ANSWERS to, not just the one you
    // filed them under — otherwise a merged chat name is unfindable. Then
    // their work, how you know them, places and notes (data-find), so
    // "mckinsey" finds everyone there.
    if(pq && ((r.dataset.name || '') + ' ' + (r.dataset.also || '') + ' '
              + (r.dataset.find || '')).toLowerCase().indexOf(pq) < 0) return false;
    if(pplace && (r.dataset.places || '').toLowerCase().indexOf(pplace) < 0) return false;
    return true;
  }
  function apply(){
    var filtering = !!pf || !!pq || !!pplace;
    // rows carry the match; faces cannot show why they matched
    var pw = document.getElementById('people');
    if(pw) pw.classList.toggle('filtering', filtering);
    document.querySelectorAll('#people .row.person').forEach(function(r){
      r.classList.toggle('phide', !match(r)); });
    document.querySelectorAll('#people .pgroup').forEach(function(g){
      var vis = g.querySelectorAll('.row.person:not(.phide)').length;
      g.classList.toggle('phide', filtering && vis === 0);
      if(g.classList.contains('csection')){
        if(filtering){ if(vis > 0) g.open = true; }
        else { g.open = lg('ppl-open:' + g.dataset.circle) !== '0'; }
      }
    });
    var shown = document.querySelectorAll('#people .row.person:not(.phide)').length;
    var msg = document.getElementById('pfilterempty');
    if(!msg){
      var anchor = document.querySelector('#people .pfilters');
      if(anchor){ msg = document.createElement('p'); msg.id = 'pfilterempty';
        msg.className = 'empty'; anchor.insertAdjacentElement('afterend', msg); }
    }
    if(msg){
      if(filtering && shown === 0){
        msg.textContent = pq ? ('No one matching \\u201c' + pq + '\\u201d.')
                             : ('No one under \\u201c' + (chipLabel || 'that filter') + '\\u201d right now.');
        msg.style.display = '';
      } else { msg.style.display = 'none'; }
    }
  }
  document.addEventListener('click', function(e){
    var b = e.target.closest ? e.target.closest('.pfilter') : null;
    if(!b) return;
    if(b.classList.contains('pplace')){
      // place/context chips toggle, independent of the who-owes-whom chips
      var was = b.classList.contains('active');
      document.querySelectorAll('.pplace').forEach(function(x){ x.classList.remove('active'); });
      pplace = was ? '' : (b.dataset.pplace || '').toLowerCase();
      if(!was) b.classList.add('active');
      chipLabel = b.dataset.pplace || '';
      apply();
      return;
    }
    pf = b.dataset.pfilter || '';
    chipLabel = b.textContent.toLowerCase();
    document.querySelectorAll('.pfilter:not(.pplace)').forEach(function(x){
      x.classList.toggle('active', x === b); });
    apply();
  });
  var box = document.getElementById('psearch');
  if(box) box.addEventListener('input', function(){
    pq = box.value.trim().toLowerCase(); apply(); });
  // "I'm in…" — the trip question as one control: pick a place, the
  // directory folds open on everyone there.
  var psel = document.getElementById('pplacesel');
  if(psel) psel.addEventListener('change', function(){
    pplace = (psel.value || '').toLowerCase();
    chipLabel = psel.value || '';
    apply();
  });

  // ---- circle drag-to-reorder (persists the closeness order) ----------------
  // Each circle section carries a small handle; drop reorders the sections and
  // POSTs the new order so it sticks everywhere circles are used. Server-only —
  // on the read-only file view the handles simply do nothing.
  var wrap = document.getElementById('people');
  var dragging = null;
  function sections(){ return Array.prototype.slice.call(document.querySelectorAll('#people .csection')); }
  function afterElement(y){
    var els = sections().filter(function(s){ return s !== dragging; });
    var closest = null, cd = -Infinity;
    els.forEach(function(s){ var box = s.getBoundingClientRect();
      var off = y - box.top - box.height / 2;
      if(off < 0 && off > cd){ cd = off; closest = s; } });
    return closest;
  }
  function adjSection(sec, dir){
    var s = dir < 0 ? sec.previousElementSibling : sec.nextElementSibling;
    while(s && !s.classList.contains('csection'))
      s = dir < 0 ? s.previousElementSibling : s.nextElementSibling;
    return s;
  }
  document.querySelectorAll('#people .csection').forEach(function(sec){
    var h = sec.querySelector('summary');
    if(!h) return;
    var grip = document.createElement('span');
    grip.className = 'cgrip'; grip.title = 'Drag to reorder'; grip.draggable = true;
    grip.textContent = '\\u2261';
    h.insertBefore(grip, h.firstChild);
    // Clicking the grip must not fold the section — only dragging should act.
    grip.addEventListener('click', function(e){ e.preventDefault(); e.stopPropagation(); });
    grip.addEventListener('dragstart', function(e){ dragging = sec; sec.classList.add('cdrag');
      try { e.dataTransfer.effectAllowed = 'move'; e.dataTransfer.setData('text/plain', sec.dataset.circle); } catch(x){} });
    grip.addEventListener('dragend', function(){ sec.classList.remove('cdrag'); dragging = null; persistOrder(); });
    // Touch has no drag-and-drop, so give every section up/down arrows too.
    var moves = document.createElement('span');
    moves.className = 'cmove';
    [['\\u2191', -1, 'Move up'], ['\\u2193', 1, 'Move down']].forEach(function(m){
      var btn = document.createElement('button');
      btn.className = 'cmovebtn'; btn.type = 'button'; btn.textContent = m[0];
      btn.setAttribute('aria-label', m[2]);
      btn.addEventListener('click', function(e){
        e.preventDefault(); e.stopPropagation();
        var t = adjSection(sec, m[1]);
        if(!t) return;
        if(m[1] < 0) wrap.insertBefore(sec, t); else wrap.insertBefore(t, sec);
        persistOrder();
      });
      moves.appendChild(btn);
    });
    h.appendChild(moves);
    // On a phone, rename and the arrows wait behind one ⋯ (28 Sep): on
    // every shelf at once they were most of the heading. On a laptop the
    // same controls show when the pointer or the keyboard reaches the
    // heading, so this button stays hidden there (page.css).
    var hmore = document.createElement('button');
    hmore.className = 'cheadmore'; hmore.type = 'button'; hmore.textContent = '\\u22ef';
    hmore.setAttribute('aria-label', 'Rename or move ' + (sec.dataset.circle || 'this group'));
    hmore.setAttribute('aria-expanded', 'false');
    hmore.addEventListener('click', function(e){
      e.preventDefault(); e.stopPropagation();
      var on = h.classList.toggle('chopen');
      hmore.setAttribute('aria-expanded', on ? 'true' : 'false');
    });
    h.appendChild(hmore);
  });
  if(wrap) wrap.addEventListener('dragover', function(e){
    if(!dragging) return; e.preventDefault();
    var after = afterElement(e.clientY);
    if(after){ wrap.insertBefore(dragging, after); }
    else {                                   // dropped below all — keep it inside the circle block
      var others = sections().filter(function(s){ return s !== dragging; });
      var last = others[others.length - 1];
      if(last) wrap.insertBefore(dragging, last.nextSibling);
    }
  });
  function persistOrder(){
    var order = sections().map(function(s){ return s.dataset.circle; });
    try {
      fetch('/api/circles/reorder', {method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify({order: order})}).catch(function(){});
    } catch(x){}
  }

  // ---- person links in task text: jump to them on the People tab -----------
  document.addEventListener('click', function(e){
    var a = e.target.closest ? e.target.closest('.plink,.darrow[data-plink]') : null;
    if(!a) return;
    e.preventDefault(); e.stopPropagation();
    // A row on Needs you first; someone only on a shelf opens Everyone, with
    // their shelf unfolded (7 Oct).
    var hit = null;
    document.querySelectorAll('#people .row.person').forEach(function(r){
      if(r.dataset.name !== a.dataset.plink) return;
      if(!hit || (hit.closest('.pall') && !r.closest('.pall'))) hit = r;
    });
    location.hash = hit && hit.closest('.pall') ? '#/everyone' : '#/people';
    setTimeout(function(){
      if(!hit) return;
      for(var p = hit.parentElement; p; p = p.parentElement)
        if(p.tagName === 'DETAILS') p.open = true;
      hit.open = true;
      hit.scrollIntoView({behavior:'smooth', block:'center'});
      hit.classList.add('rowflash');
      setTimeout(function(){ hit.classList.remove('rowflash'); }, 1800);
    }, 150);
  });

  // The six-stop post-dump tour lived here. Its first stop pointed at the
  // removed hero, Esc did not close it, and a browser closed mid-way made it
  // restart on every load (7 Oct audit). "Show me around" now starts the
  // page's own tour (tour.py) with ?tour, and For you teaches the rest one
  // thing a day (tips.py).

  // Search every task ever written — the answer to "I know I wrote it down,
  // where is it?". Matches row names and task text, done tasks included;
  // matching rows open with the hits highlighted.
  var ts = document.getElementById('tsearch');
  if(ts) ts.addEventListener('input', function(){
    var q = ts.value.trim().toLowerCase();
    document.querySelectorAll('.view[data-view="plate"] details.row').forEach(function(r){
      if(!q){ r.classList.remove('phide'); r.open = false; return; }
      var hit = (r.dataset.name || '').toLowerCase().indexOf(q) >= 0;
      r.querySelectorAll('.ttext').forEach(function(el){
        var m = el.textContent.toLowerCase().indexOf(q) >= 0;
        el.classList.toggle('tsearchhit', m && !!q);
        if(m) hit = true;
      });
      r.classList.toggle('phide', !hit);
      r.open = hit && !!q;
    });
    // ghosts (closed / quiet folds) open themselves when they hold a match
    document.querySelectorAll('.view[data-view="plate"] details.ghost').forEach(function(g){
      if(!q) return;
      if(g.querySelector('details.row:not(.phide)')) g.open = true;
    });
    // area headings with nothing visible under them step aside too
    document.querySelectorAll('.view[data-view="plate"] h3.area').forEach(function(h){
      var any = false, n2 = h.nextElementSibling;
      while(n2 && n2.classList && n2.classList.contains('row')){
        if(!n2.classList.contains('phide')) any = true;
        n2 = n2.nextElementSibling;
      }
      h.classList.toggle('phide', !!q && !any);
    });
  });

  // Anyone asking for reduced motion gets the still drawings, not the films.
  try {
    if(window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches){
      document.querySelectorAll('video.artvid').forEach(function(v){
        var img = document.createElement('img');
        img.className = v.className; img.src = v.poster;
        img.width = v.width; img.height = v.height; img.alt = '';
        v.parentNode.replaceChild(img, v);
      });
    }
  } catch(e){}
})();
</script>
"""


def repetition_report(path=None):
    """How many times does the Today tab say the same thing?

    Every point fix in this file is one block taught to check itself. Nothing
    stops the NEXT block from printing the plan again, and that is exactly how
    one train journey came to be on screen six times. So the build counts.

    It warns and never fails: a genuine double is occasionally right (the hero
    IS allowed to be the plan's task), and a build that refuses to run is
    worse than a page that repeats.
    """
    try:
        with open(path or OUT, encoding="utf-8") as f:
            doc = f.read()
    except OSError:
        return []
    m = re.search(r'<div class="view" data-view="today">(.*?)(?=<div class="view" '
                  r'data-view=|</main>)', doc, re.S)
    seg = m.group(1) if m else ""
    if not seg:
        return []
    # Visible text only — an attribute the hand never reads is not a repeat.
    seg = re.sub(r"<(script|style)\b.*?</\1>", " ", seg, flags=re.S | re.I)
    seg = re.sub(r"<template\b.*?</template>", " ", seg, flags=re.S | re.I)
    text = html.unescape(re.sub(r"<[^>]+>", "\n", seg))
    # Cluster by MEANING, not by matching strings. Every block phrases the
    # same errand its own way — "Book train Lyon → Paris → Nantes" and
    # "…Thursday or Friday? Then book the train" are one job to a person — so
    # exact-signature counting sails straight past the thing it exists to
    # catch.
    #
    # The threshold is STRICTER than in_plan's, on purpose, and it is a RATIO
    # rather than a count. in_plan compares a task against a known plan line
    # and can afford to be eager. Here every line meets every other, including
    # narration — and two paragraphs about the same afternoon share "Devon"
    # and "the country house" without being a repeat of anything. Counting shared
    # words flagged those; asking what FRACTION of the two lines is shared
    # does not, while still catching the same errand worded three ways.
    def _guard_match(toks, seed):
        shared = toks & seed
        if len(shared) < 3:
            return False
        return len(shared) / len(toks | seed) >= 0.5

    clusters = []
    for line in text.split("\n"):
        line = " ".join(line.split())
        if len(line) < 18:
            continue
        toks = _sig_tokens(line)
        if len(toks) < 3:
            continue
        for c in clusters:
            if _guard_match(toks, c["toks"]):
                c["hits"].append(line)
                break
        else:
            clusters.append({"toks": toks, "hits": [line]})
    return [(c["hits"][0], c["hits"]) for c in clusters if len(c["hits"]) > 2]


def _main():
    path, n, pend = build()
    extra = f", {pend} queued ask{'s' if pend != 1 else ''}" if pend else ""
    print(f"Built {path} — {n} workstream{'s' if n != 1 else ''}{extra}")
    for key, hits in repetition_report(path):
        print(f'  ⚠ "{clip(hits[0], 58)}" appears {len(hits)}× on Today')
    # The linter: mechanical integrity checks on the files just rendered.
    # A crash in it must never block the page build.
    try:
        import check
        for prob in check.check():
            print(f"  ⚠ {prob}")
    except Exception as ex:
        print(f"  (check.py failed: {ex})")


if __name__ == "__main__":
    # Run as the module `build`, not as __main__: the tab files import
    # their helpers from `build`, and one copy of this file must hold the
    # state build() sets (PERSON_NAMES and the rest).
    import build as _self
    _self._main()

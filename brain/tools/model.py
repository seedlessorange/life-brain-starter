#!/usr/bin/env python3
"""Read brain/workstreams.md into structured data, and work out what is rotting.

This is the one file that decides what "needs a chase", "going cold" and
"overdue" mean. Everything else — the page, the map, the briefing — reads its
answers rather than re-deriving them, so the page and the map can never
disagree about whether something is on fire.

The markdown stays the source of truth. Nothing here writes.
"""

import json
import os
import re
from datetime import date, datetime, timedelta

WEEKDAY_IDX = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5,
               "sun": 6}

HERE = os.path.dirname(os.path.abspath(__file__))
BRAIN = os.path.dirname(HERE)
ROOT = os.path.dirname(BRAIN)

FIELD = re.compile(r"^\s*-\s+\*\*([A-Za-z ]+):\*\*\s*(.*)$")
TASK = re.compile(r"^\s*-\s+\[([ xX])\]\s*(.*)$")
# A task you cannot start yet is not a task you are failing to do. This suffix
# parks one until a date, after which it silently becomes normal again.
# Deliberately NOT anchored to the end of the line: suffixes arrive in any
# order ("… (waiting until 2026-09-01) ~30m" is a hand-edit away), and an
# anchored pattern silently un-parks the task the day something follows it.
UNTIL = re.compile(r"\s*\(waiting until (\d{4}-\d{2}-\d{2})\)")
DROPPED = re.compile(r"\s*\(dropped (\d{4}-\d{2}-\d{2})\)")
# The evening check's deliberate roll-forward — state, not part of the words.
CARRYING = re.compile(r"\s*\(carrying (\d{4}-\d{2}-\d{2})\)")
DUE = re.compile(r"\s*\(due ([^)]+)\)")
# When the WORK has to happen, as opposed to when the thing it serves happens.
# A trip on the 20th wants its ticket bought a fortnight earlier; writing
# `(by 2026-08-06)` says so outright. Left off, the verb decides — see LEAD.
BY = re.compile(r"\s*\(by ([^)]+)\)")
# A rough time cost for a task: ~2h, ~90m, ~1h30. The single tilde is
# deliberately distinct from ~~strikethrough~~, and the h/m suffix is REQUIRED
# — a bare "~5" in prose ("call ~5 people") must never silently become a
# five-minute estimate. The picker always writes suffixed tokens.
# \d+h\d*m? accepts the natural "~1h30m" spelling alongside "~1h30".
EST = re.compile(r"~\s*(\d+h\d*m?|\d+m)\b", re.I)
# Season suffixes (brain/season.md): who it's with, the loose intention, and
# the concrete slot the page writes when a chip lands on a day. Same contract
# as (due …): a suffix the brain cannot read keeps its words, and md.bare
# strips these identically so a slot moving never moves the tick hash.
WITH = re.compile(r"\s*\(with: ([^)]+)\)")
WHEN = re.compile(r"\s*\(when: ([^)]+)\)")
PLANNED = re.compile(r"\s*\(planned: ([^)]+)\)")
# What kind of slot an undated idea needs — free text, e.g. "an afternoon in
# Paris", "a day out of Paris", "the cohort". A month tells you when a thing
# should happen; this tells you which free day it can actually land on, which
# is the question the tray gets asked. Only used for grouping.
FITS = re.compile(r"\s*\(fits: ([^)]+)\)")
# A recurring season item never reaches [x]: each tick stamps a date into
# (did: …) — the habits-Log pattern — and the item returns to the tray.
# Validation is baked into the regexes, so "(repeat: after every win)" and
# "(did: nothing wrong)" keep their words.
REPEAT = re.compile(r"\s*\(repeat: (weekly|fortnightly|monthly)\)", re.I)
DID = re.compile(r"\s*\(did: (\d{4}-\d{2}-\d{2}(?: \d{4}-\d{2}-\d{2})*)\)")

# Statuses that mean the thing is still live. Anything else is out of the way
# and must never appear in a count of what needs attention.
LIVE = {"moving", "stalled", "blocked", "waiting", "not started"}
CLOSED = {"done", "dropped", "parked"}

DEFAULTS = {
    "cold_days": 14,     # yours, untouched this long = going cold
    "chase_days": 7,     # theirs, silent this long = time to chase
    "soon_days": 7,      # a deadline inside this many days is "soon"
}


def load_config():
    path = os.path.join(BRAIN, "config.json")
    cfg = dict(DEFAULTS)
    try:
        with open(path, encoding="utf-8") as f:
            cfg.update(json.load(f))
    except Exception:
        pass
    return cfg


def parse_date(s):
    """YYYY-MM-DD, forgivingly. Anything else is None rather than a crash —
    a typo'd date should lose you a warning, not the whole page."""
    if not s:
        return None
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", str(s))
    if not m:
        return None
    try:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


_MABBR = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
_MONTHS = {}
for _i, _names in enumerate([("january", "jan"), ("february", "feb"), ("march", "mar"),
                             ("april", "apr"), ("may",), ("june", "jun"), ("july", "jul"),
                             ("august", "aug"), ("september", "sep", "sept"), ("october", "oct"),
                             ("november", "nov"), ("december", "dec")], start=1):
    for _nm in _names:
        _MONTHS[_nm] = _i


def _last_dom(y, m):
    return (date(y, 12, 31) if m == 12 else date(y, m + 1, 1) - timedelta(days=1))


def _range_label(a, b):
    if a == b:
        return a.isoformat()
    # Day first, the way she writes dates: "5–8 Oct", "21 Sep – 1 Oct".
    # This label is what the page prints ("Sep 21 – Oct 1" on Today, 28 Sep).
    if a.year == b.year and a.month == b.month:
        return f"{a.day}–{b.day} {_MABBR[a.month]}"
    if a.year == b.year:
        return f"{a.day} {_MABBR[a.month]} – {b.day} {_MABBR[b.month]}"
    return (f"{a.day} {_MABBR[a.month]} {a.year} – "
            f"{b.day} {_MABBR[b.month]} {b.year}")


def _mk(a, b, label):
    return {"start": a, "end": b, "fuzzy": a != b, "label": label}


def parse_due(s, today=None):
    """A deadline that need not be a single day.

    Accepts an exact date (2026-09-15), an explicit range
    (2026-09-10..2026-09-20), or a fuzzy window in plain words — 'this week',
    'next month', 'mid-September', 'end of October', 'within 2 weeks'. Returns
    {start, end, fuzzy, label} or None. The END is the hard deadline everything
    downstream keys off; START and the friendly label carry the softness.
    """
    today = today or date.today()
    s = (s or "").strip()
    if not s:
        return None
    # Em/en dashes too: the brain's files use — everywhere and macOS smart
    # substitution writes it unasked, so "mid—September" must read as
    # "mid September" rather than silently parsing to no deadline at all.
    low = re.sub(r"[-_/—–]", " ", s.lower())
    low = re.sub(r"\s+", " ", low).strip()

    if ".." in s:
        a, b = s.split("..", 1)
        da, db = parse_date(a), parse_date(b)
        if da and db:
            if db < da:
                da, db = db, da
            return {"start": da, "end": db, "fuzzy": True, "label": _range_label(da, db)}
        return None
    if re.search(r"\d{4}-\d{2}-\d{2}", s):
        d = parse_date(s)
        if d:
            return _mk(d, d, d.isoformat())

    def eow(t):
        return t + timedelta(days=6 - t.weekday())

    if low in ("today",):
        return _mk(today, today, "today")
    if low in ("tomorrow", "tmrw"):
        d = today + timedelta(days=1)
        return _mk(d, d, "tomorrow")
    if low in ("this week", "week", "end of week", "eow"):
        return _mk(today, eow(today), "this week")
    if low == "next week":
        s2 = today + timedelta(days=7 - today.weekday())
        return _mk(s2, s2 + timedelta(days=6), "next week")
    if low in ("this weekend", "weekend"):
        # On a Sunday "this weekend" is the one you are standing in, not next
        # Saturday six days out.
        sat = (today - timedelta(days=1) if today.weekday() == 6
               else today + timedelta(days=(5 - today.weekday()) % 7))
        return _mk(sat, sat + timedelta(days=1), "this weekend")
    if low in ("this month", "month", "end of month", "eom"):
        return _mk(today, _last_dom(today.year, today.month), "this month")
    if low == "next month":
        ny, nm = (today.year + (today.month == 12), (today.month % 12) + 1)
        return _mk(date(ny, nm, 1), _last_dom(ny, nm), "next month")

    # Weekday words: "friday" = the coming Friday (today if said on a Friday),
    # "next tuesday" = Tuesday of NEXT week — never more than 13 days out.
    _WDAYS = {"monday": 0, "mon": 0, "tuesday": 1, "tue": 1, "tues": 1,
              "wednesday": 2, "wed": 2, "thursday": 3, "thu": 3, "thurs": 3,
              "friday": 4, "fri": 4, "saturday": 5, "sat": 5, "sunday": 6, "sun": 6}
    m = re.match(r"(this |next )?([a-z]+)$", low)
    if m and m.group(2) in _WDAYS:
        ahead = (_WDAYS[m.group(2)] - today.weekday()) % 7
        if (m.group(1) or "").strip() == "next":
            ahead += 7
        d = today + timedelta(days=ahead)
        return _mk(d, d, s.strip())

    m = re.match(r"(early|mid|middle of|late|end of|beginning of|start of)?\s*([a-z]+)$", low)
    if m and m.group(2) in _MONTHS:
        seg, mon = (m.group(1) or ""), _MONTHS[m.group(2)]
        yr = today.year if mon >= today.month else today.year + 1
        last = _last_dom(yr, mon)
        if seg in ("early", "beginning of", "start of"):
            a, b = date(yr, mon, 1), date(yr, mon, 10)
        elif seg in ("mid", "middle of"):
            a, b = date(yr, mon, 11), date(yr, mon, 20)
        elif seg in ("late", "end of"):
            a, b = date(yr, mon, 21), last
        else:
            a, b = date(yr, mon, 1), last
        return _mk(a, b, s.strip())

    m = re.match(r"(within|in) (\d+) (day|days|week|weeks|d|w)$", low)
    if m:
        n, mult = int(m.group(2)), (7 if m.group(3).startswith("w") else 1)
        d = today + timedelta(days=n * mult)
        unit = "w" if mult == 7 else "d"
        if m.group(1) == "within":
            return _mk(today, d, f"within {n}{unit}")
        return _mk(d, d, f"in {n}{unit}")
    return None


_MONTH_ALT = "|".join(sorted(_MONTHS, key=len, reverse=True))
_PROSE_DATE_RX = re.compile(
    r"\b(\d{1,2})(?:st|nd|rd|th)?\s+(" + _MONTH_ALT + r")(?:\s+(\d{4}))?\b"
    r"|\b(" + _MONTH_ALT + r")\s+(\d{1,2})(?:st|nd|rd|th)?(?:,?\s+(\d{4}))?\b"
    r"|(\d{4}-\d{2}-\d{2})", re.I)


def stale_mentions(text, today=None, grace=2):
    """Dates written into prose — 'Ember goes on holiday 14 August' — that
    have since passed. A `(due …)` suffix ages out by itself; a date inside a
    sentence sits on the page sounding current forever. Only a full day+month
    (or ISO date) counts: a bare month name is a season, not an event.
    Returns the matched labels, oldest first."""
    today = today or date.today()
    seen, out = set(), []
    for m in _PROSE_DATE_RX.finditer(text or ""):
        before = (text or "")[:m.start()]
        # Two shapes that legitimately mention a past date and must not flag:
        # provenance in parentheses — "(her words, 16 Aug)" — and a past
        # event used as a name — "the 18 August meeting". Only a bare date in
        # running prose ("goes on holiday 14 August") is a claim that ages.
        if before.count("(") > before.count(")"):
            continue
        if re.search(r"\bthe\s+$", before, re.I):
            continue
        if m.group(7):
            d = parse_date(m.group(7))
        else:
            day = int(m.group(1) or m.group(5))
            mon = _MONTHS[(m.group(2) or m.group(4)).lower()]
            yr = m.group(3) or m.group(6)
            try:
                d = date(int(yr), mon, day) if yr else date(today.year, mon, day)
            except ValueError:
                continue
            # No year written and the date reads far ahead: it almost always
            # meant the one that just passed ("20 December", said in January).
            if not yr and (d - today).days > 183:
                try:
                    d = d.replace(year=d.year - 1)
                except ValueError:
                    continue
        if d and (today - d).days > grace and m.group(0) not in seen:
            seen.add(m.group(0))
            out.append((d, m.group(0)))
    out.sort(key=lambda p: p[0])
    return [lb for _, lb in out]


def _plain(s):
    s = re.sub(r"\*\*|\*|`|~~", "", s or "")
    return re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", s).strip()


def est_to_minutes(tok):
    """'2h'->120, '90m'->90, '1h30'->90, '45'->45 (bare number = minutes)."""
    if isinstance(tok, (int, float)):     # already minutes, not a token
        return int(tok)
    tok = (tok or "").lower().replace(" ", "")
    if "h" in tok:
        h, _, m = tok.partition("h")
        m = m.rstrip("m")            # "1h30m" — the minutes may keep their m
        return int(h or 0) * 60 + (int(m) if m else 0)
    if tok.endswith("m"):
        return int(tok[:-1] or 0)
    return int(tok or 0)


def fmt_dur(mins):
    """Minutes as a human span: 45 -> '45m', 150 -> '2h30', 120 -> '2h'."""
    mins = max(int(round(mins)), 0)
    if mins < 60:
        return f"{mins}m"
    h, m = divmod(mins, 60)
    return f"{h}h{m:02d}" if m else f"{h}h"


def clip(s, n):
    """Shorten to ~n chars at a word boundary, with an ellipsis. A hard slice
    prints 'wildfire preventio' on the hero and reads as a bug, not a cut."""
    s = (s or "").strip()
    if len(s) <= n:
        return s
    cut = s[:n].rsplit(" ", 1)[0].rstrip(" ,;:—–-")
    return (cut or s[:n]) + "…"


# --------------------------------------------------------------------------
# Cost of delay — when a thing must be STARTED, not when it happens
#
# The ranking used to key off one date: when a thing was due. That is the
# wrong date for most of what actually gets missed. A trip on the 20th does
# not need a ticket on the 20th — it needs one a fortnight earlier, while the
# seat still exists and still costs €25. A meeting on Tuesday needs its prep
# on Monday. Ranking on the event date leaves both looking calm right up to
# the day they become impossible, which is how a train in four days sat
# quietly behind three projects that merely sorted earlier in the alphabet.
#
# So every dated thing gets a second date: the last day acting still works.
# Urgency is measured against THAT one. An explicit `(by YYYY-MM-DD)` always
# wins; otherwise the verb decides, because "book a flight" and "reply to
# Anna" carry their lead times in their own words.

LEAD = (
    # (pattern, days of lead, worthless once the date passes)
    (r"\b(book|buy|reserve|r[ée]serv\w*|purchase)\b.{0,40}"
     r"\b(flight|plane|avion|train|ticket|billet|hotel|h[ôo]tel|airbnb|"
     r"hostel|rental)\b", 14, True),
    (r"\b(flight|plane|avion|train|billet|ticket)\b.{0,40}"
     r"\b(book|buy|reserve|r[ée]serv\w*)\b", 14, True),
    (r"\b(appl\w+|submit|renew|visa|passport|permis|dossier|deposit)\b", 21, False),
    (r"\b(book|buy|reserve|r[ée]serv\w*|order|commander)\b", 7, True),
    (r"\b(prep|prepare|pr[ée]par\w*|rehearse|revise|brief)\b", 2, True),
    (r"\b(rsvp|confirm|confirmer)\b", 3, True),
    (r"\b(draft|write|[ée]crire)\b", 3, False),
)


# A moment, not a deadline: "pick up the car ~5 PM today". Once the day has
# passed, the task has almost always already happened in real life — it stops
# scoring and the page ASKS ("probably done?") instead of nagging forever.
SAMEDAY = re.compile(
    r"\b(today|tonight|this\s+(?:morning|afternoon|evening)|"
    r"ce\s+soir|aujourd\W?hui)\b", re.I)


# An appointment, not a job: "Session 2 — 17:00 with Emery". Once its date
# is behind us it happened or it didn't; either way it is not work to plan.
# A clock time is the tell (colon only — "~2h30" is an estimate, not a time).
MOMENT = re.compile(r"^(?:\S+\s+)?session\s+\d+\s*[—–:-]|"
                    r"\b(?:[01]?\d|2[0-3]):[0-5]\d\b", re.I)


def lead_time(text):
    """How many days ahead of its date this has to actually happen, and
    whether it is worthless afterwards. Returns (days, expires)."""
    low = (text or "").lower()
    for pat, days, expires in LEAD:
        if re.search(pat, low):
            return days, expires
    return 0, False


def pressure(act_days, horizon=21):
    """What one more day of waiting costs, 0..140.

    Past the last responsible moment it keeps climbing: late on something
    still possible is the loudest state there is. Before it the curve is
    convex, not linear — a fortnight out barely registers, three days out is
    most of the way up. A straight line would give a fortnight-out task a
    third of the weight of a tomorrow task, and the page would fill with work
    that genuinely can wait.
    """
    if act_days is None:
        return 0.0
    if act_days < 0:
        return 100.0 + min(-act_days, 40)
    if act_days > horizon:
        return 0.0
    x = act_days / float(horizon)
    return round(95.0 * (1.0 - x) ** 2, 1)


def parse(text):
    """Split workstreams.md into a list of workstreams.

    A workstream is an `## ` heading followed by `- **Field:** value` lines,
    then free prose, then `- [ ]` tasks. Fields and tasks may be interleaved;
    prose is everything that is neither.
    """
    items = []
    cur = None
    last = None      # the task an indented line below it belongs to
    for raw in text.split("\n"):
        h = re.match(r"^##\s+(.*)$", raw.strip())
        if h:
            if cur:
                items.append(cur)
            cur = {"name": _plain(h.group(1)), "fields": {}, "tasks": [],
                   "notes": [], "line": None}
            last = None
            continue
        if cur is None:
            continue
        # An indented line under a task is that task's context, not the
        # workstream's: "the method" means nothing two weeks later unless the
        # line that says which method travels with it. A blank line or
        # unindented prose ends the run.
        if last is not None and raw[:1] in (" ", "\t") and raw.strip() \
                and not TASK.match(raw):
            last["notes"].append(re.sub(r"^[-*]\s+", "", raw.strip()))
            continue
        if not raw.strip() or raw[:1] not in (" ", "\t"):
            last = None
        f = FIELD.match(raw)
        if f:
            cur["fields"][f.group(1).strip().lower()] = f.group(2).strip()
            continue
        t = TASK.match(raw)
        if t:
            body = t.group(2)
            m_until = UNTIL.search(body)
            m_drop = DROPPED.search(body)
            m_est = EST.search(body)
            # "(due …)" is only a deadline if its content actually parses as
            # one. "review the contract (due diligence doc)" keeps its words —
            # a suffix the brain cannot read must never be silently deleted.
            m_due = DUE.search(body)
            due_raw = m_due.group(1).strip() if m_due else ""
            if due_raw and parse_due(due_raw) is None:
                m_due, due_raw = None, ""
            # Same rule for "(by …)": only a date the brain can read becomes
            # state. "(by the way)" keeps its words.
            m_by = BY.search(body)
            by_raw = m_by.group(1).strip() if m_by else ""
            if by_raw and parse_due(by_raw) is None:
                m_by, by_raw = None, ""
            m_carry = CARRYING.search(body)
            # Season suffixes, same only-if-it-parses rule as (due …).
            m_when = WHEN.search(body)
            when_raw = m_when.group(1).strip() if m_when else ""
            if when_raw and parse_due(when_raw) is None:
                m_when, when_raw = None, ""
            m_planned = PLANNED.search(body)
            planned_raw = m_planned.group(1).strip() if m_planned else ""
            if planned_raw and parse_due(planned_raw) is None:
                m_planned, planned_raw = None, ""
            m_with = WITH.search(body)
            m_fits = FITS.search(body)
            m_rep = REPEAT.search(body)
            m_did = DID.search(body)
            clean = UNTIL.sub("", DROPPED.sub("", CARRYING.sub("", body)))
            if m_due:
                clean = clean.replace(m_due.group(0), "")
            if m_by:
                clean = clean.replace(m_by.group(0), "")
            for m_sz in (m_when, m_planned, m_with, m_fits, m_rep, m_did):
                if m_sz:
                    clean = clean.replace(m_sz.group(0), "")
            clean = EST.sub("", clean)
            cur["tasks"].append({
                "done": t.group(1).lower() == "x",
                "text": _plain(clean),
                "until": m_until.group(1) if m_until else "",
                "dropped": m_drop.group(1) if m_drop else "",
                "carrying": m_carry.group(1) if m_carry else "",
                "due_raw": due_raw,
                "by_raw": by_raw,
                "when_raw": when_raw,
                "planned_raw": planned_raw,
                "with": ([p.strip() for p in m_with.group(1).split(",")
                          if p.strip()] if m_with else []),
                "fits": m_fits.group(1).strip() if m_fits else "",
                "repeat": m_rep.group(1).lower() if m_rep else "",
                "did": m_did.group(1).split() if m_did else [],
                "est": est_to_minutes(m_est.group(1)) if m_est else 0,
                "notes": [],
            })
            last = cur["tasks"][-1]
            continue
        if raw.strip() and not raw.strip().startswith("---"):
            cur["notes"].append(raw.strip())
    if cur:
        items.append(cur)
    return items


def room_slug(name):
    """One slug rule for a room, shared by rooms.py, serve.py and the notes
    files under brain/rooms/ — they must all name the same file."""
    s = re.sub(r"[^a-zA-Z0-9]+", "-", (name or "").lower()).strip("-")
    return s[:60].rstrip("-")


# Rooms used to sit under "wings" in config, a second grouping of her life
# beside the workstreams' Area — one renovation was "Dad" on the plate and
# "Home" on the rooms page. Since 28 Sep (decisions.md) there is one grouping: a room
# carries the Area of the workstream it holds, and config keeps the rooms as
# one flat list. The old shape still reads, so a starter install that has not
# migrated keeps working; these are what its wings meant.
WING_AREA = {"entrepreneurship": "Business", "work & school": "School",
             "home": "Personal", "people": "Personal",
             "life admin & health": "Personal", "health": "Personal",
             "the big questions": "Big questions"}
BIG_QUESTIONS = "Big questions"


def _ws_areas():
    """Workstream name -> its Area, read straight from the file. Cheap: a
    regex pass, not the whole model."""
    out, cur = {}, None
    try:
        with open(os.path.join(BRAIN, "workstreams.md"), encoding="utf-8") as f:
            for line in f:
                m = re.match(r"^##\s+(.+?)\s*$", line)
                if m:
                    cur = m.group(1)
                    continue
                m = re.match(r"^\s*-\s+\*\*Area:\*\*\s*(.+?)\s*$", line)
                if m and cur and cur not in out:
                    out[cur] = m.group(1)
    except OSError:
        pass
    return out


def all_rooms(cfg=None):
    """Every room in config, flat, in her order. Each is a copy of its config
    entry plus `slug` and `area`.

    Area: the room's own `area` if it names one, else the Area of the first
    workstream it holds, else what its old wing meant, else Personal."""
    cfg = cfg or load_config()
    rc = cfg.get("rooms") or {}
    raw = [dict(r) for r in (rc.get("list") or []) if isinstance(r, dict)]
    for wing in (rc.get("wings") or []):
        for r in (wing.get("rooms") or []):
            r = dict(r)
            r["_wing"] = wing.get("name", "")
            raw.append(r)
    ws_area = None
    out = []
    for r in raw:
        r["slug"] = r.get("slug") or room_slug(r.get("name", ""))
        area = (r.get("area") or "").strip()
        if not area and r.get("ws"):
            if ws_area is None:
                ws_area = _ws_areas()
            area = next((ws_area[n] for n in r["ws"] if n in ws_area), "")
        if not area:
            area = WING_AREA.get((r.get("_wing") or "").strip().lower(), "")
        r["area"] = area or "Personal"
        out.append(r)
    return out


def season_areas(cfg=None, today=None):
    """The areas this season is about (config `now.areas`), while the season
    lasts. The page gives the first of them a tab of its own — School for
    Term 4 — and the tab steps aside the day `now.until` passes."""
    cfg = cfg or load_config()
    now = cfg.get("now") or {}
    until = parse_date(now.get("until") or "")
    today = today or date.today()
    if until and until < today:
        return []
    return [a for a in (now.get("areas") or []) if a]


def school_tab_on(cfg=None, today=None):
    """Whether the School tab belongs in the bar right now."""
    return "School" in season_areas(cfg, today)


def load_goals(path=None, today=None):
    """brain/goals.md — the finish lines the owner sets for herself. One
    `## <room name>` per project, milestones as ordinary checkboxes with the
    same `(due ...)` syntax as every task. Returns {heading_lower: [goal]}."""
    path = path or os.path.join(BRAIN, "goals.md")
    today = today or date.today()
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read()
    except FileNotFoundError:
        return {}
    out = {}
    for block in parse(text):
        goals = []
        for t in block["tasks"]:
            due = parse_due(t.get("due_raw") or "", today) \
                if t.get("due_raw") else None
            dd = (due["end"] - today).days if due else None
            goals.append({
                "text": t["text"], "done": t["done"],
                "due_label": due["label"] if due else "",
                "due_end": due["end"].isoformat() if due else "",
                "days_to_due": dd,
                "overdue": bool(not t["done"] and dd is not None and dd < 0),
                "due_soon": bool(not t["done"] and dd is not None
                                 and 0 <= dd <= 14),
            })
        if goals:
            out[block["name"].strip().lower()] = goals
    return out


def load_season(path=None, today=None):
    """brain/season.md — the bucket list for the current season of life.
    The FIRST `## <name>` block is the active season: From/Until/Why fields,
    then plain checkboxes that may carry (with: …), (when: …) and the
    (planned: …) the page writes. Nothing here decays; the countdown is the
    pressure. Returns None when there is no season yet."""
    path = path or os.path.join(BRAIN, "season.md")
    today = today or date.today()
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read()
    except FileNotFoundError:
        return None
    blocks = parse(text)
    if not blocks:
        return None
    b = blocks[0]
    start = parse_date(b["fields"].get("from", ""))
    end = parse_date(b["fields"].get("until", ""))
    items = []
    for t in b["tasks"]:
        planned = (parse_due(t["planned_raw"], today)
                   if t.get("planned_raw") else None)
        items.append({
            "text": t["text"], "done": t["done"],
            "with": t.get("with") or [],
            "est": t.get("est") or 0,
            "when_label": t.get("when_raw") or "",
            "fits": t.get("fits") or "",
            "planned": planned,
            "dropped": t.get("dropped") or "",
            "repeat": t.get("repeat") or "",
            "did": t.get("did") or [],
        })
    weekends = 0
    if end and end >= today:
        # Weekends the season actually contains. A season still ahead must not
        # count the weekends before it starts — this number is the page's only
        # source of pressure, so an inflated one is worse than none.
        d = max(today, start) if start else today
        while d <= end:
            if d.weekday() == 5:
                weekends += 1
            d += timedelta(days=1)
    return {"name": b["name"], "start": start, "end": end,
            "why": b["fields"].get("why", ""), "items": items,
            "days_left": (end - today).days if end else None,
            "weekends_left": weekends}


def _goal_overdue_names(cfg, today=None):
    """Workstream names that must shout because a self-imposed goal in their
    room slipped past its date. Headings in goals.md name rooms; a heading
    that names a workstream directly works too (matched in enrich)."""
    goals = load_goals(today=today)
    late = {h for h, gs in goals.items() if any(g["overdue"] for g in gs)}
    names = set()
    if late:
        for room in all_rooms(cfg):
            if (room.get("name") or "").strip().lower() in late:
                names.update(room.get("ws") or [])
    return names, late


def _goal_pull(cfg, today=None):
    """The pull a goal exerts BEFORE it is blown.

    A finish line that only matters once it has been missed is not a finish
    line, it is a post-mortem. The old model gave a goal exactly one moment of
    influence — the day after it slipped. So a September launch was invisible
    all August, which is the same failure as the train: nothing that pays off
    later can ever compete with something that hurts today.

    The answer is not to let long goals outrank real deadlines. It is to give
    them a small, permanent claim on attention that grows as their date nears,
    so they surface on the quiet days instead of never. Returns
    {name_or_heading_lower: {"days", "text", "pull"}} for the nearest open goal.
    """
    goals = load_goals(today=today)
    by_heading = {}
    for heading, gs in goals.items():
        live = [g for g in gs if not g["done"] and g["days_to_due"] is not None]
        if not live:
            continue
        near = min(live, key=lambda g: g["days_to_due"])
        # Half weight and a 45-day horizon: present all quarter, never louder
        # than a train leaving on Thursday.
        by_heading[heading] = {
            "days": near["days_to_due"], "text": near["text"],
            "label": near["due_label"],
            "pull": round(pressure(max(near["days_to_due"], 0), horizon=45) * 0.5, 1),
        }
    by_ws = {}
    for room in all_rooms(cfg):
        g = by_heading.get((room.get("name") or "").strip().lower())
        if g:
            for nm in (room.get("ws") or []):
                by_ws[nm] = g
    return by_ws, by_heading


def _room_urgent_names(cfg):
    """Workstream names bumped by an '(urgent)' in their room's notes
    (brain/rooms/<slug>.md). The same marker as everywhere else — context
    the owner types in a room is allowed to move the ranking too."""
    names = set()
    for room in all_rooms(cfg):
        fp = os.path.join(BRAIN, "rooms",
                          (room.get("slug") or room_slug(room.get("name")))
                          + ".md")
        try:
            with open(fp, encoding="utf-8") as f:
                body = f.read()
        except OSError:
            continue
        if "(urgent)" in body.lower():
            names.update(room.get("ws") or [])
    return names


def _session_blocked(cfg):
    """Workstream name -> the question a Claude conversation is paused on.

    `sessions.py` parks a conversation in state "ask" when its last turn
    ended in a question, and nothing moves in that project until she answers.
    That is the same shape of stall as a decision blocked on her in a project
    brain's handoff — except the handoff's version was display-only, so a
    thread frozen on a one-line question never reached her day at all. Read
    straight from the file rather than importing sessions.py: this runs on
    every command, and the module owns a lock and a thread table it does not
    need to hand out for one read.
    """
    try:
        with open(os.path.join(BRAIN, "sessions.json"), encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {}
    asked = {}
    for c in (data.get("convos") or []):
        if c.get("ended") or c.get("state") != "ask":
            continue
        src = c.get("src") or ""
        if src and src not in asked:
            asked[src] = (c.get("question") or "").strip()
    if not asked:
        return {}
    out = {}
    for room in all_rooms(cfg):
        q = asked.get(room.get("source") or "")
        if q is None:
            continue
        for nm in (room.get("ws") or []):
            out[nm] = q
    return out


def enrich(items, cfg=None, today=None):
    """Add the derived truth: who has the ball, and what is decaying.

    Everything downstream reads these keys. Nothing downstream recomputes them.
    """
    cfg = cfg or load_config()
    today = today or date.today()
    cold_days = int(cfg.get("cold_days", 14))
    chase_days = int(cfg.get("chase_days", 7))
    soon_days = int(cfg.get("soon_days", 7))
    room_urgent = _room_urgent_names(cfg)
    sess_asked = _session_blocked(cfg)
    goal_ws, goal_headings = _goal_overdue_names(cfg, today)
    pull_ws, pull_headings = _goal_pull(cfg, today)
    # The season of work she declared (config "now": place, phase, areas).
    # An Area named there gets a steady lift while the phase lasts — this is
    # how "school-prep week" outranks a bulk import without touching a file.
    now_cfg = cfg.get("now") or {}
    now_until = parse_date(now_cfg.get("until"))
    phase_areas = set()
    if not now_until or now_until >= today:
        phase_areas = {a.strip().lower()
                       for a in (now_cfg.get("areas") or []) if a.strip()}
    # The weekly hour (config "now" -> "batch"): fronts she chose to handle in
    # one sitting a week — Dad, the houses, the admin — go quiet on every other
    # day, so a term week is not re-litigated against them each morning. They
    # are not parked: on the batch day they rank as normal.
    batch = now_cfg.get("batch") or {}
    batch_names, batch_gap = set(), 0
    bday = WEEKDAY_IDX.get((batch.get("day") or "").strip().lower()[:3])
    if ((not now_until or now_until >= today) and bday is not None
            and today.weekday() != bday):
        batch_names = {n.strip() for n in (batch.get("workstreams") or [])}
        batch_gap = (bday - today.weekday()) % 7

    for w in items:
        f = w["fields"]
        status = _plain(f.get("status", "")).lower() or "not started"
        w["status"] = status
        # Snoozed = deliberately out of sight until a wake date: not closed,
        # not urgent, just not now. It re-enters the live lists by itself the
        # day the date arrives; a past date is inert.
        snz = parse_date(f.get("snooze"))
        w["snooze"] = snz.isoformat() if snz else ""
        w["snoozed"] = bool(status not in CLOSED and snz and snz > today)
        w["snooze_days"] = (snz - today).days if w["snoozed"] else None
        w["live"] = status not in CLOSED and not w["snoozed"]
        w["area"] = _plain(f.get("area", "")) or "Everything else"
        w["phase_area"] = bool(w["live"] and w["area"].lower() in phase_areas)
        w["why"] = _plain(f.get("why", ""))
        # "I want to work on this for a few days" — a whole-project focus,
        # with no task invented to carry it. Expires by itself.
        w["focus_until"] = ""
        fu = _plain(f.get("focus", ""))
        if fu:
            d = parse_date(fu)
            if d and d >= today:
                w["focus_until"] = d.isoformat()
        w["next_action"] = _plain(f.get("next", ""))
        # Explicit person links — `- **People:** Dad (tester), Ember` — the
        # hand-made half; the derived half comes from scanning text for known
        # names. A parenthesised label is that person's role in THIS project.
        w["linked_people"], w["people_roles"] = [], {}
        for x in _plain(f.get("people", "")).split(","):
            x = x.strip()
            if not x:
                continue
            pm = re.match(r"^(.*?)\s*\(([^)]+)\)$", x)
            if pm:
                w["linked_people"].append(pm.group(1).strip())
                w["people_roles"][pm.group(1).strip()] = pm.group(2).strip()
            else:
                w["linked_people"].append(x)

        ball_raw = _plain(f.get("ball", ""))
        low = ball_raw.lower()
        if low.startswith(("me", "mine", "you")):
            w["ball"] = "me"
        elif low.startswith(("them", "him", "her", "they")) or (ball_raw and not low.startswith(("nobody", "no one", "none"))):
            w["ball"] = "them"
        else:
            w["ball"] = "nobody"
        # Whatever came after the dash is who, exactly. "Them — solicitor".
        who = re.split(r"[—\-–:]", ball_raw, maxsplit=1)
        w["ball_who"] = who[1].strip() if len(who) > 1 else ""

        due_pd = parse_due(f.get("due"), today)
        due = due_pd["end"] if due_pd else None
        w["due_label"] = due_pd["label"] if due_pd else ""
        w["due_start"] = due_pd["start"].isoformat() if due_pd else ""
        w["due_fuzzy"] = bool(due_pd and due_pd["fuzzy"])
        touched = parse_date(f.get("touched"))
        since = parse_date(f.get("since")) or touched
        w["due"] = due.isoformat() if due else ""
        w["touched"] = touched.isoformat() if touched else ""
        w["since"] = since.isoformat() if since else ""

        w["days_untouched"] = (today - touched).days if touched else None
        w["days_to_due"] = (due - today).days if due else None
        w["days_waiting"] = (today - since).days if since and w["ball"] == "them" else None

        # "(urgent)" in a task is the owner's own priority language — dumps
        # write it naturally. Prose the scorer cannot see is prose that gets
        # ignored (the portfolio-hero incident: every real urgency was
        # invisible, so "never started" won the page).
        for t in w["tasks"]:
            t["urgent"] = "(urgent)" in t["text"].lower()
            # The marker is data, not prose: once read, it leaves the text —
            # the red row and the why-line say it; the words don't repeat it.
            # serve._bare strips it identically or tick keys would drift.
            t["text"] = re.sub(r"\s*\(urgent\)", "", t["text"],
                               flags=re.I).strip()
        # A parked task is still open, but it must not make anything look
        # urgent or unfinished until its date arrives.
        for t in w["tasks"]:
            d = parse_date(t.get("until"))
            t["parked"] = bool(d and d > today)
            t["until_days"] = (d - today).days if d else None
            tpd = parse_due(t.get("due_raw"), today)
            dd = tpd["end"] if tpd else None
            t["due"] = dd.isoformat() if dd else ""
            t["due_label"] = tpd["label"] if tpd else ""
            t["due_start"] = tpd["start"].isoformat() if tpd else ""
            t["due_fuzzy"] = bool(tpd and tpd["fuzzy"])
            t["due_days"] = (dd - today).days if dd else None
            t["overdue"] = bool(dd and not t["done"] and (dd - today).days < 0)
            t["due_soon"] = bool(dd and not t["done"] and 0 <= (dd - today).days <= soon_days)

            # The second date: when the WORK has to happen. For a fuzzy range
            # the anchor is its START — you need the ticket before the trip
            # begins, not before it ends.
            anchor = tpd["start"] if tpd else None
            lead_days, expires = lead_time(t["text"])
            bypd = parse_due(t.get("by_raw"), today)
            if bypd:
                t["act_by"] = bypd["end"].isoformat()
                t["lead_days"], t["lead_said"] = 0, "you set the date"
            elif anchor and lead_days:
                t["act_by"] = (anchor - timedelta(days=lead_days)).isoformat()
                t["lead_days"] = lead_days
                t["lead_said"] = f"{lead_days} days before it happens"
            else:
                t["act_by"] = t["due"]
                t["lead_days"], t["lead_said"] = 0, ""
            ab = parse_date(t["act_by"])
            t["act_days"] = (ab - today).days if ab else None
            # Worthless after the fact: a ticket for a departed train, prep
            # for a finished meeting. It stops scoring instead of sitting
            # permanently overdue and outranking everything still winnable.
            # Same for a moment-task ("pick up the car ~5 PM today") once its
            # day is behind us — dated by its window's end, or, with no date
            # at all, by the workstream's last touch (imperfect on purpose:
            # the page only ASKS, and "still open" costs one click).
            sameday = bool(SAMEDAY.search(t["text"]))
            # A class deliverable past its date was handed in or missed; a
            # dated meeting happened or didn't. The MAHA was planned four
            # mornings after Blackboard closed (24 Sep) — the page asks now.
            moment = bool("(class)" in t["text"].lower()
                          or MOMENT.search(t["text"]))
            t["expired"] = bool(not t["done"] and (
                (dd and (dd - today).days < 0
                 and (expires or sameday or moment))
                or (not dd and sameday and touched and touched < today)))
            t["late_start"] = bool(not t["done"] and not t["expired"]
                                   and t["act_days"] is not None
                                   and t["act_days"] < 0
                                   and t.get("lead_days"))
            t["pressure"] = 0.0 if (t["done"] or t.get("parked")
                                    or t.get("dropped") or t["expired"]) \
                else pressure(t["act_days"])
            if t.get("urgent") and not t["done"]:
                # Her own word for it. A floor, not a bucket — a dated task
                # that is genuinely later must still be able to outrank it.
                t["pressure"] = max(t["pressure"], 72.0)
        w["open_tasks"] = sum(1 for t in w["tasks"]
                              if not t["done"] and not t["parked"]
                              and not t.get("dropped"))
        w["parked_tasks"] = sum(1 for t in w["tasks"] if t["parked"])
        w["done_tasks"] = sum(1 for t in w["tasks"] if t["done"])

        # The three states this whole system exists to surface.
        w["overdue"] = bool(w["live"] and due and (due - today).days < 0)
        w["due_soon"] = bool(w["live"] and due and 0 <= (due - today).days <= soon_days)
        w["chase"] = bool(w["live"] and w["ball"] == "them"
                          and w["days_waiting"] is not None
                          and w["days_waiting"] >= chase_days)
        w["cold"] = bool(w["live"] and w["ball"] != "them"
                         and w["days_untouched"] is not None
                         and w["days_untouched"] >= cold_days
                         and status != "not started")
        # Never touched and never started is not "cold" — it was never warm.
        # It is still a problem, so it gets its own flag rather than silence.
        w["never_touched"] = bool(w["live"] and not touched)
        # A dated task inside is the workstream's problem too: "Personal admin"
        # is calm until the cleaner-payment task inside it goes overdue — then
        # the whole workstream must shout, or the date was decoration.
        open_ts = [t2 for t2 in w["tasks"]
                   if not t2["done"] and not t2.get("parked") and not t2.get("dropped")]
        # Expired work is still open, but it is no longer worth ranking. It
        # gets counted so the page can offer to retire it, and excluded from
        # everything that decides loudness.
        w["expired_tasks"] = [t2 for t2 in open_ts if t2.get("expired")]
        live_ts = [t2 for t2 in open_ts if not t2.get("expired")]
        w["task_pressure"] = max([t2.get("pressure") or 0.0
                                  for t2 in live_ts], default=0.0)
        w["pressed_task"] = ""
        w["pressed_act_days"] = None
        w["pressed_late"] = False
        w["pressed_lead"] = ""
        if live_ts:
            top = max(live_ts, key=lambda t2: t2.get("pressure") or 0.0)
            if (top.get("pressure") or 0) > 0:
                w["pressed_task"] = clip(top["text"], 70)
                w["pressed_act_days"] = top.get("act_days")
                w["pressed_late"] = bool(top.get("late_start"))
                w["pressed_lead"] = top.get("lead_said") or ""
        w["task_overdue"] = bool(w["live"] and any(t2["overdue"] for t2 in open_ts))
        w["task_due_soon"] = bool(w["live"] and any(t2["due_soon"] for t2 in open_ts))
        w["task_urgent"] = bool(w["live"] and any(t2.get("urgent") for t2 in open_ts))
        w["urgent_name"] = bool(w["live"] and (
            w["name"].lower().startswith("urgent")
            or "(urgent)" in (w["next_action"] or "").lower()))
        w["room_urgent"] = bool(w["live"] and w["name"] in room_urgent)
        w["session_asked"] = sess_asked.get(w["name"], "") if w["live"] else ""
        w["session_blocked"] = bool(w["live"] and w["name"] in sess_asked)
        w["goal_overdue"] = bool(w["live"] and (
            w["name"] in goal_ws or w["name"].strip().lower() in goal_headings))
        w["next_action"] = re.sub(r"\s*\(urgent\)", "", w["next_action"] or "",
                                  flags=re.I).strip()
        w["next_due_task"] = ""
        dated = sorted((t2 for t2 in open_ts if t2.get("due_days") is not None),
                       key=lambda t2: t2["due_days"])
        if dated:
            w["next_due_task"] = clip(dated[0]["text"], 60)
        elif w["task_urgent"]:
            w["next_due_task"] = clip(next(t2["text"] for t2 in open_ts
                                           if t2.get("urgent")), 60)

        # A goal's pull, before its date rather than only after it.
        g = pull_ws.get(w["name"]) or pull_headings.get(w["name"].strip().lower())
        w["goal_pull"] = (g or {}).get("pull") or 0.0
        w["goal_days"] = (g or {}).get("days")
        w["goal_text"] = (g or {}).get("text") or ""
        w["goal_label"] = (g or {}).get("label") or ""

        # The workstream's own date deserves the same lead-time treatment its
        # tasks get: "Portfolio site" due the 30th with nothing booked is the
        # same shape of problem as the train.
        w["ws_pressure"] = 0.0
        if w["live"] and w["days_to_due"] is not None:
            w["ws_pressure"] = pressure(w["days_to_due"])

        # Dates living in prose rather than a (due) suffix go quietly stale —
        # the page kept saying "Ember goes on holiday 14 August" eleven days
        # after he left. Flagged here so the next session rewords the line;
        # it never makes anything louder, it just stops the page lying.
        w["stale_text"] = []
        if w["live"]:
            for where, txt in (("Next", w["next_action"]), ("Why", w["why"])):
                for lb in stale_mentions(txt, today):
                    w["stale_text"].append({"where": where, "label": lb})
        w["stale_dates"] = bool(w["stale_text"])

        # Quiet until the weekly hour — unless a date inside lands before that
        # hour comes round, because a deadline does not wait for Friday.
        w["batched"] = False
        if w["live"] and w["name"] in batch_names and not w["overdue"]:
            clock = any(t2.get("due_days") is not None
                        and 0 <= t2["due_days"] < batch_gap for t2 in live_ts)
            if not (clock or (w["days_to_due"] is not None
                              and 0 <= w["days_to_due"] < batch_gap)):
                w["batched"] = True
                for k in ("due_soon", "chase", "cold", "never_touched",
                          "task_overdue", "task_due_soon", "task_urgent",
                          "urgent_name", "room_urgent", "session_blocked",
                          "goal_overdue", "pressed_late"):
                    w[k] = False

        w["score"] = _score(w)
        w["horizon"] = _horizon(w)
        w["flags"] = [k for k in ("overdue", "task_overdue", "goal_overdue",
                                  "task_urgent", "urgent_name", "room_urgent",
                                  "session_blocked", "chase", "cold",
                                  "due_soon", "task_due_soon", "never_touched",
                                  "stale_dates")
                      if w.get(k)]
    # Ties used to fall through to the name, so the order of her day was
    # decided by the first letter of a project. Break on things that mean
    # something instead: what has to be acted on soonest, then what has been
    # neglected longest.
    items.sort(key=lambda w: (
        -w["score"],
        w.get("pressed_act_days") if w.get("pressed_act_days") is not None else 9999,
        w["days_to_due"] if w.get("days_to_due") is not None else 9999,
        -(w.get("days_untouched") or 0),
        w["name"]))
    return items


# How far away the payoff is. The day's list is drawn from these pools rather
# than off the top of one sorted stack — otherwise deadlines win every slot,
# every day, and the things with no deadline (the ones that decide the year)
# never get a single hour.
def _horizon(w):
    if not w["live"]:
        return ""
    if w.get("batched"):
        return "batch"
    # "Now" means a clock is running on it — not merely that it scores high.
    # Focus is a high score with no clock, and it belongs in Push: the whole
    # point of the pools is that choosing something must not disguise itself
    # as an emergency.
    # 60 put eleven of fifteen workstreams in "now" (2026-09-10) — a pool
    # that big is just the sorted list wearing a label. 80 means a clock
    # inside roughly the next two days, and the pools mean something again.
    if (w["overdue"] or w.get("pressed_late")
            or max(w.get("ws_pressure") or 0, w.get("task_pressure") or 0) >= 80
            or w.get("urgent_name") or w.get("room_urgent")
            or w.get("session_blocked")
            or w.get("goal_overdue") or w["chase"]):
        return "now"
    if w.get("focus_until") or w.get("goal_pull") or w.get("phase_area"):
        return "push"         # she chose it, or a finish line is pulling
    return "slow"             # matters, nothing forcing it — the year's work


def _score(w):
    """How loudly this should be shouting. Ordering only — the number is not
    shown anywhere, so it never needs defending to a human.

    The spine is time pressure measured against the day the WORK has to
    happen (see `pressure`), taken as the worst of the workstream's own date
    and its tasks'. Everything else adjusts that: her explicit choices lift
    it, a goal's approach lifts it a little, neglect lifts it slowly.

    What this replaced: fixed bonuses per bucket — any task due inside a week
    added exactly 45, whether it was due tomorrow or next Sunday. Six live
    workstreams collapsed onto four distinct totals, and the day's order came
    down to a tiebreak on the project's name.
    """
    if not w["live"]:
        return -1
    if w.get("batched"):
        return 0.0       # waiting for its weekly hour, below everything live
    # The loudest real deadline in here, not a bucket it happens to fall in.
    s = max(w.get("ws_pressure") or 0.0, w.get("task_pressure") or 0.0)
    # "URGENT:" in the name is the same claim as "(urgent)" on a task inside
    # it, so it raises the floor rather than stacking on top. Adding both is
    # how a project she labelled urgent in June outranked a train leaving on
    # Thursday: two constants, neither of which ever decays.
    if w.get("urgent_name") or w.get("room_urgent"):
        s = max(s, 72.0)
    # A conversation frozen on a question costs a minute to unblock and is
    # holding a whole thread still. It sits just under the urgents because
    # she did not declare it — the machine noticed it — and it raises the
    # floor rather than stacking, for the same reason they do.
    if w.get("session_blocked"):
        s = max(s, 65.0)
    if w.get("focus_until"):
        s += 90                      # her deliberate choice beats decay
    if w.get("phase_area"):
        s += 30    # the declared season of work (config "now") lifts its areas
    if w.get("goal_overdue"):
        s += 80          # a slipped self-imposed finish line shouts, on purpose
    else:
        s += w.get("goal_pull") or 0.0   # and pulls gently before it slips
    if w["chase"]:
        s += 40 + min(w["days_waiting"] or 0, 40)
    if w["cold"]:
        s += 20 + min(w["days_untouched"] or 0, 40)
    if w["status"] == "blocked":
        s += 15
    if w["never_touched"]:
        s += 10
    if w["ball"] == "me":
        s += 5
    return round(s, 1)


# Dates written the way a person writes them, in the middle of a sentence:
# "the trip 20-25 Aug", "meeting Tuesday 18 August", "sometime in September".
# The ranking cannot read any of these — only the `(due …)` suffix — so a task
# can name its own deadline in plain words and still be sorted as undated.
_MONTH_WORD = (r"(?:January|February|March|April|May|June|July|August|"
               r"September|October|November|December|"
               r"Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sept|Sep|Oct|Nov|Dec)")
PROSE_DATE = re.compile(
    # A day number attached to a month, either way round, including ranges.
    r"\b\d{1,2}\s*(?:[-–—]\s*\d{1,2}\s*)?" + _MONTH_WORD + r"\b"
    r"|\b" + _MONTH_WORD + r"\.?\s+\d{1,2}\b"
    # A bare month, but only capitalised — otherwise "may" the ordinary verb
    # turns half the plate into false alarms.
    r"|\b" + _MONTH_WORD + r"\b"
    r"|\b(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\b"
    r"|\b(?:tomorrow|next week|next month|this weekend)\b")
# "for March expenses" names which expenses, not when. A month directly after
# "for"/"from" is describing something, not dating it.
PROSE_DESCRIPTOR = re.compile(r"\b(?:for|from|since|of)\s+" + _MONTH_WORD + r"\b")


def guess_prose_date(frag, today=None):
    """Turn a fragment a person wrote — "20-25 Aug", "4–7 September" — into
    the date it starts. Only used to judge how urgently to ASK about it;
    nothing is ever written from a guess."""
    today = today or date.today()
    mm = re.search(_MONTH_WORD, frag)
    if mm:
        mon = _MONTHS.get(mm.group(0).lower()[:3])
        if mon:
            dm = re.search(r"\b(\d{1,2})\b", frag)     # the first of a range
            day = int(dm.group(1)) if dm else 1
            for yr in (today.year, today.year + 1):
                try:
                    d = date(yr, mon, min(day, _last_dom(yr, mon).day))
                except ValueError:
                    continue
                if d >= today:
                    return d
    pd = parse_due(frag, today)
    return pd["start"] if pd else None


def prose_date_frag(line):
    """The date fragment worth reading from a line. A line can hold several —
    "Meeting: Tuesday 18 Aug" — and the leftmost is not the truest: a bare
    weekday resolves to whichever one is nearest (a week-old meeting read as
    happening "today"), while "18 Aug" says which day it actually was. Prefer
    a match that carries a day number."""
    ms = list(PROSE_DATE.finditer(line))
    for m in ms:
        if any(c.isdigit() for c in m.group(0)):
            return m
    return ms[0] if ms else None


# Things that happen AT a time and are usually preceded by work: the meeting
# you want to have read something before, the visit you should have a list for.
COMMITMENT = re.compile(
    r"\b(meeting|meet|visit|call|appointment|interview|rendez-?vous|"
    r"dinner|lunch|viewing|deadline|exam|presentation|pitch|hand-?in)\b", re.I)
PREP_VERB = re.compile(
    r"\b(prep|prepare|pr[ée]par\w*|read|review|revise|draft|write|plan|"
    r"pack|print|bring|question|agenda|rehearse)\b", re.I)


def prep_gaps(items, cfg=None, today=None, within=4):
    """Something is happening within days, and nothing on the plate readies
    her for it.

    A dated commitment written into a workstream's notes — "Meeting: Tuesday
    18 Aug, 10h at Les Riceys" — is invisible to a ranking that only reads
    task lines and `(due …)` markers. So the meeting arrives on time and the
    preparation for it never existed as work at all. This finds those and
    offers the missing task; it never writes one.
    """
    today = today or date.today()
    out = []
    for w in items:
        if not w["live"] or w.get("batched"):
            continue
        open_ts = [t for t in w["tasks"]
                   if not t["done"] and not t.get("parked") and not t.get("dropped")]
        prepped = [t["text"].lower() for t in open_ts if PREP_VERB.search(t["text"])]
        seen = set()
        for line in ((w.get("notes") or []) + [t["text"] for t in open_ts]
                     + [n for t in open_ts for n in t.get("notes") or []]):
            if not COMMITMENT.search(line):
                continue
            m = prose_date_frag(line)
            if not m:
                continue
            when = guess_prose_date(m.group(0), today)
            if not when or not (0 <= (when - today).days <= within):
                continue
            label = _plain(re.sub(r"\s+", " ", line)).strip("-*• ")[:90]
            if label.lower() in seen:
                continue
            seen.add(label.lower())
            # Already covered? A prep task sharing real words with the event
            # line is close enough — this is a nudge, not an audit.
            words = {x for x in re.findall(r"[a-zà-ÿ]{4,}", label.lower())}
            if any(len(words & set(re.findall(r"[a-zà-ÿ]{4,}", p))) >= 2
                   for p in prepped):
                continue
            out.append({"ws": w["name"], "event": label,
                        "when": when.isoformat(),
                        "days": (when - today).days})
    out.sort(key=lambda g: g["days"])
    return out


def bench(items, plan_md="", n=6):
    """The ranked open tasks not already on today's plan — what would fill a
    freed slot. Plain code, no model call: the plate's own ranking IS the
    order. Plan lines are reworded copies of tasks, so exclusion goes by
    shared words as well as by key — "bedroom floors" in the plan covers the
    workstream's own wording of it."""
    import md as MD
    plan_keys, raw = set(), []
    for ln in (plan_md or "").split("\n"):
        m = re.match(r"^\s*[-*]\s+\[[ xX]\]\s+(.*)$", ln)
        if m:
            plan_keys.add(MD.taskkey(MD.bare(m.group(1))))
            raw.append(m.group(1))

    def toks(s):
        return {x.rstrip("s") for x in re.split(r"[^a-z0-9]+", s.lower())
                if len(x) >= 5}

    plan_toks = toks(" ".join(raw))
    out, used = [], set(plan_keys)
    for w in items:
        if not w["live"]:
            continue
        for t in w["tasks"]:
            if t["done"] or t.get("parked") or t.get("dropped"):
                continue
            k = MD.taskkey(t["text"])
            if k in used:
                continue
            used.add(k)
            tt = toks(t["text"])
            if tt and len(tt & plan_toks) >= 2:
                continue
            out.append({"text": t["text"], "key": k, "ws": w["name"]})
            if len(out) >= n:
                return out
    return out


# Openings that name a topic rather than a move. A task line is meant to be
# the action, readable cold; these are the ones that are not.
VAGUE_STARTS = ("look into", "look at", "see about", "see if", "see what",
                "see with", "see how", "think about", "work on", "sort out",
                "deal with", "figure out", "explore", "consider", "continue",
                "finish", "handle", "plan ", "organise", "organize",
                "progress on", "get started", "start on", "keep working",
                "voir ", "s'occuper", "réfléchir")


def vague_start(text):
    """The vague opening a task line starts with, or ""."""
    low = (text or "").strip().lower()
    return next((v.strip() for v in VAGUE_STARTS if low.startswith(v)), "")


def blind_spots(items, cfg=None, today=None):
    """What the ranking cannot see, and what each gap is costing her.

    The scorer is only as good as the dates and finish lines it is given, and
    its failure mode is silent: a task whose deadline lives in its words
    rather than its `(due …)` marker does not rank low with a warning, it
    ranks as though it had no deadline at all. So the brain says so, names the
    specific item, and offers the one edit that fixes it.

    Ordered by what would move the ranking most. Each entry carries `fix`,
    which the page turns into a single tap.
    """
    cfg = cfg or load_config()
    today = today or date.today()
    # Goals are filed by room, so a gap has to name the room it belongs to or
    # the one-tap fix has nowhere to write.
    room_of = {}
    for room in all_rooms(cfg):
        for nm in (room.get("ws") or []):
            room_of[nm] = room.get("name") or ""
    out = []
    for w in items:
        if not w["live"] or w.get("batched"):
            continue
        room = room_of.get(w["name"], "")
        first_open = next((t for t in w["tasks"] if not t["done"]
                           and not t.get("parked") and not t.get("dropped")
                           and not t.get("expired")), None)
        for t in w["tasks"]:
            if t["done"] or t.get("parked") or t.get("dropped"):
                continue
            if t.get("expired"):
                out.append({
                    "kind": "expired", "ws": w["name"], "room": room,
                    "task": t["text"],
                    "says": "its date has passed, so it can no longer be done",
                    "costs": "it sits in the plate looking open forever",
                    "fix": "retire", "weight": 70})
                continue
            # Worded as a topic, not a move ("look into the visa"). Abstract
            # wording is what gets put off (McCrea et al. 2008) — and for her
            # it is where the uncomfortable fronts hide. Only the tasks the
            # ranking would actually offer: the project's first open one, or
            # one with a date or her (urgent) on it.
            vague = vague_start(t["text"])
            if vague and (t is first_open or t.get("urgent") or t.get("due")):
                out.append({
                    "kind": "vague", "ws": w["name"], "room": room,
                    "task": t["text"], "saw": vague,
                    "says": f'starts with "{vague}", which names no first move',
                    "costs": "vague tasks are the ones that get put off",
                    "fix": "reword", "weight": 35})
            if t.get("due") or t.get("by_raw"):
                continue
            m = prose_date_frag(t["text"])
            if not m or PROSE_DESCRIPTOR.search(t["text"]):
                continue
            # How soon the words seem to point decides how much this matters.
            # A trip this month is worth interrupting her for; a filing next
            # February is worth noting once and leaving alone.
            guess = guess_prose_date(m.group(0), today)
            days = (guess - today).days if guess else None
            wt = 100 if (days is not None and days <= 45) else (
                70 if (days is not None and days <= 120) else 40)
            out.append({
                "kind": "prose_date", "ws": w["name"], "room": room,
                "task": t["text"],
                "saw": m.group(0), "days": days,
                "says": f'says "{m.group(0)}" in its words, but carries no date the ranking can read',
                "costs": "ranked as if it had no deadline at all",
                "fix": "date", "weight": wt})
        # A project with no finish line can only ever surface by rotting.
        # Only worth saying about something with real work in it — a one-line
        # errand does not need a finish line, it needs doing.
        if not w.get("goal_pull") and not w.get("goal_overdue") \
                and not w["due"] and w["horizon"] == "slow" \
                and w["open_tasks"] >= 2:
            out.append({
                "kind": "no_goal", "ws": w["name"], "room": room, "task": "",
                "says": "has no finish line and no date",
                "costs": "it can only reach your day by going stale first",
                "fix": "goal", "weight": 60})
        if w["live"] and not w["next_action"] and w["open_tasks"] == 0:
            out.append({
                "kind": "no_next", "ws": w["name"], "room": room, "task": "",
                "says": "has nothing written down as the next move",
                "costs": "nothing here can ever be offered to you",
                "fix": "next", "weight": 50})
    out.sort(key=lambda b: (-b["weight"], b["ws"]))
    return out


# A task is "quick" when it carries a small estimate or starts like an
# errand. "Pressed" when it, or its workstream, has any time pressure.
QUICK_STARTS = ("call ", "pay ", "book ", "send ", "reply", "respond",
                "email ", "text ", "message ", "submit ", "sign ", "renew ",
                "cancel ", "order ", "confirm ", "chase ", "transfer ",
                "invoice ", "get reimbursed", "share ", "forward ",
                "appeler ", "payer ", "réserver ")
# Things that need offices, lines or business hours — pushing them on a
# weekend is nagging, not helping.
WEEKDAY_HINTS = ("cpam", "ameli", "bank", "banque", "mairie", "préfecture",
                 "prefecture", "urssaf", "impôt", "impot", "insurance",
                 "assurance", "notaire", "doctor", "dentist", "docteur",
                 "office", "administration", "consulate", "embassy")


def quick_wins(items, today=None):
    """The small, time-pressed tasks worth clearing right now — surfaced on
    Today so they stop hiding inside the plate. Quick AND at least a little
    pressed, never one without the other. Weekend-aware: a task that needs
    offices open is grouped under "waits for Monday" instead of pushed on a
    Saturday. Returns [{"w": workstream, "t": task, "monday": bool}]."""
    today = today or date.today()
    weekend = today.weekday() >= 5
    out = []
    for w in items:
        if not w["live"] or w.get("batched"):
            continue
        pressed_ws = (w["overdue"] or w["due_soon"] or w["chase"]
                      or w.get("urgent_name") or w.get("room_urgent")
                      or w.get("goal_overdue") or w.get("task_overdue")
                      or w.get("task_urgent") or w.get("task_due_soon"))
        for t in w["tasks"]:
            if t["done"] or t.get("parked") or t.get("dropped"):
                continue
            low = t["text"].lower()
            mins = t["est"] if t.get("est") else None  # already minutes
            quick = ((mins is not None and mins <= 30)
                     or low.startswith(QUICK_STARTS))
            pressed = (t.get("urgent") or t.get("overdue")
                       or (t.get("due_days") is not None
                           and t["due_days"] <= 7)
                       or pressed_ws)
            if not (quick and pressed):
                continue
            out.append({"w": w, "t": t,
                        "monday": bool(weekend and any(
                            h in low for h in WEEKDAY_HINTS))})
    out.sort(key=lambda q: (
        not (q["t"].get("urgent") or q["t"].get("overdue")),
        9e9 if q["t"].get("due_days") is None else q["t"]["due_days"],
        q["t"]["text"].lower()))
    return out[:8]


def load(path=None, cfg=None, today=None):
    path = path or os.path.join(BRAIN, "workstreams.md")
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read()
    except FileNotFoundError:
        return []
    return enrich(parse(text), cfg, today)


# The one sentence every daily update opens with, wherever it came from —
# the page's Tell the brain, a Telegram voice note, an "update:" text. It
# tells the run to reconcile rather than file, and it is how the Daily
# update habit recognises an update in the queue.
DAILY_UPDATE_PRE = (
    "Daily update. Reconcile, do not just file: anything she says is DONE "
    "gets ticked in the workstream it lives in (and Touched stamped); new "
    "priorities re-rank next.md; corrections update the source files; "
    "genuinely new items get filed where they belong. Only ask if something "
    "truly cannot be placed.")


def update_days(since_days=120):
    """Days she sent the brain a daily update. The queue keeps every ask
    forever and titles it with its opening words, so an ask titled "Daily
    update" is the log — no button, nothing to remember to tick."""
    out = set()
    qdir = os.path.join(BRAIN, "queue")
    floor = (date.today() - timedelta(days=since_days)).isoformat()
    try:
        names = os.listdir(qdir)
    except OSError:
        return out
    for n in names:
        if not n.endswith(".md") or n[:10] < floor:
            continue
        try:
            with open(os.path.join(qdir, n), encoding="utf-8") as f:
                head = f.read(400)
        except OSError:
            continue
        if re.search(r"^title:\s*Daily update\b", head, re.M | re.I):
            d = parse_date(n[:10])
            if d:
                out.add(d)
    return out


def settling_in(today=None):
    """True for the first three days after she arrives in a house.

    Habits hang on the cues of a place, and a move takes the cues away
    (Wood, Tam & Witt 2005: students changing university kept a habit only
    where the setting stayed the same). `now.since` in config.json is the
    day she arrived; until the fourth day every habit shows its floor.
    """
    since = parse_date(str((load_config().get("now") or {}).get("since") or ""))
    today = today or date.today()
    return bool(since) and 0 <= (today - since).days < 3


def load_habits(path=None, today=None):
    """Parse brain/habits.md: a heading, a weekly Target, a Log of dates.

    Derived per habit: whether it was done today, this week's count against
    the target, and the last 14 days as booleans for the dot strip. Weeks run
    Monday to Sunday. No streaks on purpose — a rest day breaking a "streak"
    punishes the schedule the target explicitly allows.
    """
    from datetime import timedelta
    path = path or os.path.join(BRAIN, "habits.md")
    today = today or date.today()
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read()
    except FileNotFoundError:
        return []
    habits = []
    cur = None
    for raw in text.split("\n"):
        h = re.match(r"^##\s+(.*)$", raw.strip())
        if h:
            cur = {"name": _plain(h.group(1)), "target": 0, "dates": set(),
                   "auto": "", "steps": [], "floor": [], "when": "",
                   "spares": None, "cue": ""}
            habits.append(cur)
            continue
        if cur is None:
            continue
        f = FIELD.match(raw)
        if not f:
            continue
        key, val = f.group(1).strip().lower(), f.group(2)
        if key == "target":
            m = re.search(r"\d+", val)
            cur["target"] = min(int(m.group()) if m else 0, 7)
        elif key == "spares":
            m = re.search(r"\d+", val)
            cur["spares"] = int(m.group()) if m else 0
        elif key in ("from", "source"):
            # A habit that counts itself. "journal" means the log is the
            # files in brain/journal/ — an entry for the day IS the tick,
            # and the page shows no button to press.
            if "journal" in val.lower():
                cur["auto"] = "journal"
            elif "update" in val.lower():
                cur["auto"] = "updates"
        elif key in ("steps", "floor"):
            # A ROUTINE: several small things that happen as one. Filed as
            # separate habits they would be eight headings and eight buttons,
            # and a page you stop reading. One habit, one tick, the steps
            # shown as the reminder they are.
            #
            # Floor is the version that survives a bad day — a hotel, a 1am
            # arrival, a campus morning. When the setting changes the floor
            # is what carries, because a target she hits builds the habit and
            # a target she misses builds the guilt. Her rule, applied.
            cur[key] = [s.strip() for s in re.split(r"[,;·]", _plain(val))
                        if s.strip()]
        elif key == "when":
            # The hour it belongs to, for the phone nudge and for the page to
            # show it when it is actually relevant.
            m = re.search(r"(\d{1,2})[:h.](\d{2})", val)
            if m:
                cur["when"] = f"{int(m.group(1)):02d}:{m.group(2)}"
        elif key == "cue":
            # The moment it follows: "after brushing my teeth at night".
            # If-then plans had a medium-to-large effect across 94 studies
            # (Gollwitzer & Sheeran 2006), and a cue comes along between
            # houses where an hour does not (Wood, Tam & Witt 2005).
            cur["cue"] = _plain(val).strip()
        elif key == "log":
            for m in re.finditer(r"\d{4}-\d{2}-\d{2}", val):
                d = parse_date(m.group())
                if d:
                    cur["dates"].add(d)
    monday = today - timedelta(days=today.weekday())
    settling = settling_in(today)
    for hb in habits:
        if hb.get("auto") == "journal":
            try:
                names = os.listdir(os.path.join(BRAIN, "journal"))
            except OSError:
                names = []
            for n in names:
                m = re.match(r"(\d{4}-\d{2}-\d{2})\.md$", n)
                d = parse_date(m.group(1)) if m else None
                if d:
                    hb["dates"].add(d)
        elif hb.get("auto") == "updates":
            hb["dates"] |= update_days()
        hb["dates_list"] = sorted(d.isoformat() for d in hb["dates"])
        # Last 12 weeks, oldest first, each as (monday, count) — the history
        # view runs on this instead of re-deriving weeks in the template.
        hb["weeks"] = []
        for i in range(11, -1, -1):
            wstart = monday - timedelta(days=7 * i)
            wend = wstart + timedelta(days=6)
            n = sum(1 for d in hb["dates"] if wstart <= d <= wend)
            hb["weeks"].append({"start": wstart.isoformat(), "count": n,
                                "current": i == 0})
        hb["done_today"] = today in hb["dates"]
        hb["week_count"] = sum(1 for d in hb["dates"] if monday <= d <= today)
        hb["last14"] = [(today - timedelta(days=13 - i)) in hb["dates"]
                        for i in range(14)]
        # The month as a grid: the last five Mon-Sun weeks, current week
        # last. A day that hasn't happened yet is "future", not a miss.
        hb["grid"] = []
        for i in range(4, -1, -1):
            wstart = monday - timedelta(days=7 * i)
            hb["grid"].append([
                {"date": (wstart + timedelta(days=j)).isoformat(),
                 "on": (wstart + timedelta(days=j)) in hb["dates"],
                 "today": (wstart + timedelta(days=j)) == today,
                 "future": (wstart + timedelta(days=j)) > today}
                for j in range(7)])
        # Spare days — Sharif & Shu's "emergency reserves" (2021): a hard
        # target with two spares kept people going longer than the hard
        # target alone or an easy one, because a spent spare is not a
        # failure and a visible reserve gets guarded. Without them a
        # 7-a-week habit missed on Monday had lost its week by Tuesday,
        # which is the moment people drop the whole thing. A daily habit
        # gets two unless the file says otherwise; the week is kept at
        # target minus spares.
        if hb["spares"] is None:
            hb["spares"] = 2 if hb["target"] == 7 else 0
        hb["spares"] = min(hb["spares"], hb["target"])
        hb["goal"] = hb["target"] - hb["spares"]
        missed = (today.weekday()
                  - (hb["week_count"] - (1 if hb["done_today"] else 0)))
        used = max(0, missed - (7 - hb["target"]))
        hb["spares_left"] = max(0, hb["spares"] - used)
        # "On track" = the week can still be kept. It only dims once the
        # week genuinely cannot be saved — a 3x/week habit is not "behind"
        # on Tuesday just because Monday was a rest day.
        remaining = (6 if hb["done_today"] else 7) - today.weekday()
        hb["on_track"] = hb["week_count"] + max(remaining, 0) >= hb["goal"]
        # The floor day. Slipping means it WAS running and stopped: two
        # missed days in a row for a daily habit, proportionally longer for
        # a weekly one, which rests between times as a matter of course. A
        # habit never done once is new, not slipping — a new habit that
        # introduces itself at its smallest has already talked you down
        # before you tried it. The first days in a new house count too.
        run = 0
        for on in reversed(hb["last14"][:-1]):
            if on:
                break
            run += 1
        need = (min(13, max(2, round(14 / hb["target"])))
                if hb["target"] else 13)
        # A log that has gone quiet is unlogged, not slipping: she does about
        # half her habits and ticks few of them (28 Sep), so "was running"
        # means ticked in the last two weeks. Before this, a month without
        # ticks put the morning routine on its floor every single day.
        hb["quiet"] = not any(hb["last14"])
        hb["slipping"] = (any(hb["last14"][:-1]) and not hb["done_today"]
                          and run >= need)
        hb["floor_day"] = bool(hb["floor"]) and (hb["slipping"] or settling)
    return habits


EVERY = {"daily": 1, "weekly": 7, "fortnightly": 14, "monthly": 30,
         "quarterly": 91, "yearly": 365}

# The relationship tiers, each with the rhythm it defaults to. Assigning a
# circle is the one judgement only she can make; the cadence then follows from
# it, so triaging a person is a single choice, not two. Order = closeness.
_DEFAULT_CIRCLES = [
    {"name": "Inner", "every": "weekly", "personal": True},
    {"name": "Close", "every": "fortnightly", "personal": True},
    {"name": "Friends", "every": "monthly", "personal": True},
    {"name": "Acquaintances", "every": "quarterly", "personal": True},
    {"name": "Network", "every": "quarterly", "personal": False},
    {"name": "One-off", "every": "", "personal": True},
]


# Every circle ever seen as personal, kept where no run can write (runs are
# sandboxed out of brain/tools/). config.json is writable by any run, so a
# flipped `personal: false` there must not open sends to family. Taking a
# circle OUT of this file is a deliberate hand edit, never something code does.
PERSONAL_PIN = os.path.join(HERE, ".run-policy", "personal-circles.json")
# The week's reconnect pick, locked once drawn (see load_people).
RECONNECT_FILE = os.path.join(BRAIN, ".reconnect.json")
_pin_cache = {"mtime": None, "names": set()}


def _pinned_personal():
    try:
        mt = os.stat(PERSONAL_PIN).st_mtime
    except OSError:
        return set()
    if _pin_cache["mtime"] != mt:
        try:
            with open(PERSONAL_PIN, encoding="utf-8") as f:
                data = json.load(f)
            names = data if isinstance(data, list) else []
            _pin_cache["names"] = {str(n).strip().lower() for n in names if str(n).strip()}
        except (OSError, ValueError):
            _pin_cache["names"] = set()
        _pin_cache["mtime"] = mt
    return _pin_cache["names"]


def _pin_personal(names):
    """Add circles to the pin. Best effort: inside a sandboxed run the folder
    is unwritable, and that is the sandbox working, not an error."""
    have = _pinned_personal()
    new = sorted({n for n in names if n.lower() not in have})
    if not new:
        return
    try:
        try:
            with open(PERSONAL_PIN, encoding="utf-8") as f:
                cur = json.load(f)
            cur = cur if isinstance(cur, list) else []
        except (OSError, ValueError):
            cur = []
        os.makedirs(os.path.dirname(PERSONAL_PIN), exist_ok=True)
        tmp = PERSONAL_PIN + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(sorted(set(cur) | set(new), key=str.lower), f, indent=1)
            f.write("\n")
        os.replace(tmp, PERSONAL_PIN)
    except OSError:
        pass


def school_names(cfg=None):
    """Her school's own name as it appears in calendar titles and slides,
    lowercase, from config school.names. Kept out of the code so the code
    carries nobody's school."""
    cfg = cfg or load_config()
    return [str(n).strip().lower()
            for n in ((cfg.get("school") or {}).get("names") or [])
            if str(n).strip()]


_circles_cache = {"key": None, "cs": None}


def _config_circles():
    """config.json's circles, re-read only when the file changes. A page
    build asks for circles thousands of times; parsing 20KB of config for
    each was a measurable slice of every rebuild."""
    try:
        st = os.stat(os.path.join(BRAIN, "config.json"))
        key = (st.st_mtime_ns, st.st_size)
    except OSError:
        key = None
    if key is None or _circles_cache["key"] != key:
        _circles_cache.update(key=key, cs=load_config().get("circles"))
    return _circles_cache["cs"]


def circles(cfg=None):
    """The relationship groups, from config.json so they are the owner's own.
    Each: name, default cadence, and `personal` (family/friends = never
    messageable by Claude). A group not in config defaults to personal=True,
    which is the safe assumption for the send boundary. A group once seen as
    personal stays personal (the pin above), whatever config says now."""
    cs = (cfg.get("circles") if cfg else _config_circles()) or _DEFAULT_CIRCLES
    pinned = _pinned_personal()
    out, seen_personal = {}, []
    for c in cs:
        nm = (c.get("name") or "").strip()
        if nm:
            personal = bool(c.get("personal", True))
            if personal:
                seen_personal.append(nm)
            out[nm.lower()] = {"name": nm, "every": c.get("every", ""),
                               "personal": personal or nm.lower() in pinned,
                               "weight": c.get("weight")}
    if seen_personal:
        _pin_personal(seen_personal)
    return out


def circle_meta(name, cfg=None):
    cs = circles(cfg)
    return cs.get((name or "").strip().lower(),
                  {"name": name, "every": "", "personal": True, "weight": None})


# Names that are also ordinary English words. "May merge into the old repo" is
# grammar, not the person May — but "ask May about it" is her.
AMBIGUOUS_NAMES = {"may", "will", "june", "april", "august", "march", "grace",
                   "joy", "guy", "mark", "art", "sky", "rose", "dawn", "bill",
                   "sunny", "hope", "iris", "jasmine", "summer"}


def name_in(nm, hay):
    """True when `nm` appears in `hay` as a NAME. For ambiguous names, a
    sentence-initial hit (start of text, or after ./!/?/:) is treated as
    grammar and skipped; anything mid-sentence counts."""
    for m in re.finditer(r"\b" + re.escape(nm) + r"\b", hay):
        if nm.lower() in AMBIGUOUS_NAMES:
            pre = hay[:m.start()].rstrip()
            if not pre or pre.endswith((".", "!", "?", ":")):
                continue
        return True
    return False


def spelled_name(nm):
    """A chat name as a person would write it. Some Instagram names are
    spelled out letter by letter ("A L F I E"); that is Greer (her word,
    28 Sep). The People page shows this, and a chat sorted into a circle is
    filed under it, with the chat's own name kept as an `Also:` so the sync
    still finds the chat word for word. Anything else comes back as it was."""
    toks = (nm or "").split(" ")
    if len(toks) >= 3 and all(len(t) == 1 and t.isalpha() for t in toks):
        word = "".join(toks)
        return word[0].upper() + word[1:].lower()
    return nm


def circle_weight(name, cfg=None):
    """How much a lapse with this group matters. A quiet month from family or
    the inner rings outranks the same month from a friend, which outranks an
    acquaintance — closeness scales the whole debt. Override per circle with
    a `weight:` in config; these are just honest defaults."""
    cm = circle_meta(name, cfg)
    if cm.get("weight"):
        try:
            return float(cm["weight"])
        except (TypeError, ValueError):
            pass
    n = (name or "").strip().lower()
    if n in ("inner", "close", "family", "dating"):
        return 1.5
    if cm.get("personal"):
        return 1.0
    return 0.7


# Cadence lookup kept for callers that only want the default rhythm.
def circle_cadence(name, cfg=None):
    return circle_meta(name, cfg).get("every", "")


def parse_every(s):
    """`weekly`, `3 days`, `2 weeks`, `monthly` -> days. None if unset."""
    s = (s or "").strip().lower()
    if not s:
        return None
    if s in EVERY:
        return EVERY[s]
    m = re.match(r"(\d+)\s*(day|week|month|year)s?", s)
    if m:
        n, unit = int(m.group(1)), m.group(2)
        return n * {"day": 1, "week": 7, "month": 30, "year": 365}[unit]
    return None


# Where an outreach stands, in order. `people.md` writes `Stage: asked
# 2026-10-03`; the page and serve.py move it along.
STAGES = ("to reach", "asked", "talking", "met")
STAGE_RE = re.compile(r"^(to reach|asked|talking|met)\b\s*(\d{4}-\d{2}-\d{2})?")


def load_people(path=None, today=None):
    """Parse brain/people.md — the relationships you have decided to keep warm.

    Holds no message content — it never stores what was said. It does hold the
    context YOU choose to keep: how you know someone, their role and company, a
    LinkedIn link, so a professional connection is more than a name and a date.
    The two questions it always answers stay the same: who has gone quiet, and
    who is waiting on you.
    """
    path = path or os.path.join(BRAIN, "people.md")
    today = today or date.today()
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read()
    except FileNotFoundError:
        return []

    people, cur = [], None
    for raw in text.split("\n"):
        h = re.match(r"^##\s+(.*)$", raw.strip())
        if h:
            cur = {"name": _plain(h.group(1)), "fields": {}, "notes": [], "promises": []}
            people.append(cur)
            continue
        if cur is None:
            continue
        f = FIELD.match(raw)
        if f:
            cur["fields"][f.group(1).strip().lower()] = f.group(2).strip()
            continue
        tk = TASK.match(raw)
        if tk:
            # A checkbox under a person is a promise — something said in a
            # chat that must not evaporate with the chat.
            body = tk.group(2)
            m_until = UNTIL.search(body)
            m_drop = DROPPED.search(body)
            cur["promises"].append({
                "done": tk.group(1).lower() == "x",
                "text": _plain(UNTIL.sub("", DROPPED.sub("", CARRYING.sub("", body)))),
                "until": m_until.group(1) if m_until else "",
                "dropped": m_drop.group(1) if m_drop else "",
            })
            continue
        if raw.strip() and not raw.strip().startswith("---"):
            cur["notes"].append(raw.strip())

    chase_days = int(((load_config().get("people") or {}).get("chase_days")) or 7)
    for p in people:
        f = p["fields"]
        p["why"] = _plain(f.get("why", ""))
        p["focus"] = _plain(f.get("focus", "")).lower() in ("yes", "true", "y")
        p["circle"] = _plain(f.get("circle", "")) or "Everyone else"
        p["how"] = _plain(f.get("how", ""))
        # Professional / networking context — how you know them and where they
        # sit. Entered by you (often pasted from a LinkedIn profile), never
        # scraped. LinkedIn is normalised to a real URL from a full link, a
        # bare linkedin.com/in path, or just a handle.
        p["role"] = _plain(f.get("role", "")) or _plain(f.get("title", ""))
        p["company"] = _plain(f.get("company", "")) or _plain(f.get("org", ""))
        p["met"] = _plain(f.get("met", ""))
        li = (f.get("linkedin") or f.get("li") or "").strip()
        mmd = re.search(r"\((https?://[^)]+)\)", li)   # markdown [text](url)
        if mmd:
            li = mmd.group(1)
        if li and not li.startswith("http"):
            if "linkedin.com" in li.lower():
                li = "https://" + li.lstrip("/")
            elif re.match(r"[\w.\-]+$", li):
                li = "https://www.linkedin.com/in/" + li
        p["linkedin"] = li
        cm = circle_meta(p["circle"])
        p["personal"] = cm["personal"]      # the send boundary, from the group
        explicit = _plain(f.get("every", ""))
        default = cm.get("every")
        # An `Every:` the parser cannot read falls back to the circle's
        # rhythm rather than silently switching the person's decay off.
        p["every_days"] = parse_every(explicit) or parse_every(default)
        p["every_label"] = explicit or (default or "no rhythm set")
        p["every_from_circle"] = not explicit and bool(default)

        ball = _plain(f.get("ball", "")).lower()
        p["ball"] = ("me" if ball.startswith(("me", "mine", "you"))
                     else "them" if ball.startswith(("them", "they", "him", "her"))
                     else "nobody")

        last = parse_date(f.get("last"))
        p["last"] = last.isoformat() if last else ""
        p["days_since"] = (today - last).days if last else None

        p["where"] = _plain(f.get("where", ""))
        p["pronouns"] = _plain(f.get("pronouns", ""))
        # The chat names this person also answers to. A merge writes them
        # here, which is how a WhatsApp contact "disappears" — it became an
        # alias of someone already kept. Surfaced so that is visible.
        p["also"] = [a.strip() for a in _plain(f.get("also", "")).split(",")
                     if a.strip()]
        # How she prefers to reach THIS person — WhatsApp, Instagram, SMS,
        # email, a call. `Reach:`, `Channel:` and `Via:` all work. Drafts
        # and chase suggestions should honour it.
        p["reach"] = (_plain(f.get("reach", "")) or _plain(f.get("channel", ""))
                      or _plain(f.get("via", "")))
        # The addresses a send may go to for this person. Written by the
        # first approved send (email_send.py) and checked on every later one,
        # so a draft can't quietly swap in someone else's address.
        p["emails"] = [e.strip().strip("<>").lower()
                       for e in re.split(r"[,;\s]+", _plain(f.get("email", "")))
                       if "@" in e]
        # Free contexts — "Provence", "school", "volleyball" — many per person.
        # Deliberately NOT circles: a person has one closeness and one rhythm,
        # but any number of worlds they belong to.
        p["tags"] = [x.strip() for x in (f.get("tags") or "").split(",") if x.strip()]
        # Birthday: YYYY-MM-DD or MM-DD. Days-until wraps the year boundary.
        p["birthday"] = ""
        p["bday_in"] = None
        m = re.search(r"(?:(\d{4})-)?(\d{2})-(\d{2})", f.get("birthday", "") or "")
        if m:
            try:
                mo, dy = int(m.group(2)), int(m.group(3))

                def _bday(yr):
                    # A Feb-29 birthday lands on the 28th in a non-leap
                    # year rather than vanishing from the list entirely.
                    if (mo, dy) == (2, 29):
                        try:
                            return date(yr, 2, 29)
                        except ValueError:
                            return date(yr, 2, 28)
                    return date(yr, mo, dy)

                nxt = _bday(today.year)
                if nxt < today:
                    nxt = _bday(today.year + 1)
                p["birthday"] = f"{mo:02d}-{dy:02d}"
                p["bday_in"] = (nxt - today).days
            except ValueError:
                pass
        for t_ in p["promises"]:
            d = parse_date(t_.get("until"))
            t_["parked"] = bool(d and d > today)
            t_["until_days"] = (d - today).days if d else None
        p["open_promises"] = [t_ for t_ in p["promises"]
                              if not t_["done"] and not t_["parked"] and not t_["dropped"]]
        p["oneoff"] = p["circle"].lower() in ("one-off", "oneoff", "archived")
        # On hold: you're TOGETHER — living with family for the summer, on a
        # trip with them. No reply is owed and no rhythm ticks while you share
        # a roof; the hold lifts itself the day it ends.
        hd = parse_date(f.get("hold"))
        p["hold"] = hd.isoformat() if hd else ""
        p["held"] = bool(hd and hd > today)
        # Overdue means past the rhythm YOU chose. Focus people get a shorter
        # fuse, because the whole point of marking one is to catch it earlier.
        # A one-off has no rhythm by definition, so it can never be overdue.
        due = None if p["oneoff"] else p["every_days"]
        if due and p["focus"]:
            due = max(1, int(due * 0.75))
        p["overdue"] = bool(due and p["days_since"] is not None and p["days_since"] > due)
        p["over_by"] = (p["days_since"] - due) if (p["overdue"] and due) else 0
        # Neglect is relative to THEIR OWN rhythm: ten months on quarterly
        # (3.3x) must outrank three weeks on fortnightly (1.5x). Absolute
        # days measure recency; the ratio measures the broken promise.
        p["lapse_ratio"] = (round(p["days_since"] / due, 2)
                            if due and p["days_since"] is not None else None)
        # Dormant: three times past a monthly-or-slower rhythm. Past that
        # point the silence is the state of the tie, not a debt — and eighty
        # such debts buried the few friendships actually slipping (28 Sep:
        # Remy, quiet since 2021, ranked above Avery). A message after a
        # long silence is welcomed more than the sender expects (Liu et al.
        # 2023), so a dormant tie comes back with a reason instead: a
        # birthday, or the week's reconnect pick below. Weekly and
        # fortnightly rhythms never go dormant, and neither does Focus: the
        # inner rings are where silence costs most (Roberts & Dunbar 2015).
        p["dormant"] = bool(p["overdue"] and due > 14 and not p["focus"]
                            and (p["lapse_ratio"] or 0) >= 3)
        if p["dormant"]:
            p["overdue"], p["over_by"] = False, 0
        p["never"] = last is None
        p["owed"] = p["ball"] == "me"
        # Outreach: where an approach to someone stands. Written as
        # `Stage: asked 2026-10-03`, the date it got there. Asked and silent
        # past `people.chase_days` (default 7) is a chase. Any contact dated
        # after the ask counts as an answer, so a reply the sync saw never
        # nags; a same-day date is the ask itself going out.
        sm = STAGE_RE.match(_plain(f.get("stage", "")).lower())
        p["stage"] = sm.group(1) if sm else ""
        sd = parse_date(sm.group(2)) if sm and sm.group(2) else None
        p["stage_since"] = sd.isoformat() if sd else ""
        p["stage_days"] = (today - sd).days if sd else None
        p["chase"] = bool(p["stage"] == "asked" and p["stage_days"] is not None
                          and p["stage_days"] >= chase_days
                          and not (last and last > sd) and not p["oneoff"])

        p["bday_soon"] = bool(p["bday_in"] is not None and p["bday_in"] <= 7
                              and not p["oneoff"])
        p["promised"] = bool(p["open_promises"]) and not p["oneoff"]
        s = 0
        if p["owed"]:
            s += 50                       # a reply you owe outranks a rhythm
        if p["promised"]:
            s += 45                       # a promise is a debt with a name on it
        if p["chase"]:
            s += 35                       # an ask gone quiet: nudge while it's warm
        if p["bday_soon"]:
            s += 40 - min(p["bday_in"] or 0, 30)
        if p["overdue"]:
            s += 20 + min(round(22 * (p["lapse_ratio"] or 1)), 70)
        if p["never"] and not p["oneoff"]:
            s += 20
        if p["focus"]:
            s += 10
        # Closeness scales the whole debt: the same silence weighs more from
        # the inner rings than from an acquaintance.
        p["score"] = round(s * circle_weight(p["circle"]))
        p["flags"] = [k for k in ("owed", "promised", "chase", "bday_soon", "overdue",
                                  "never")
                      if p.get(k)]
        if p["oneoff"]:
            p["flags"] = [k for k in p["flags"] if k in ("promised",)]
        if p["held"]:
            # a promise survives cohabitation; nothing else nags
            p["flags"] = [k for k in p["flags"] if k in ("promised",)]
            p["score"] = 45 if p["flags"] else 0
    # The week's reconnect pick: one dormant tie, drawn with the closer
    # circles likelier, and from the house she is in when anyone dormant
    # lives there. One a week is a message she can send; eighty is a guilt
    # she cannot pay. Locked once drawn, like Today's five: reaching them
    # ends the week's pick rather than summoning the next one.
    import random
    iso = today.isocalendar()
    week = f"{iso[0]}-W{iso[1]:02d}"
    live = today == date.today()          # a look-ahead never locks a week
    kept = {}
    if live:
        try:
            with open(RECONNECT_FILE, encoding="utf-8") as f:
                kept = json.load(f)
        except (OSError, ValueError):
            kept = {}
    by_name = {p["name"]: p for p in people}
    pick = by_name.get(kept.get("name")) if kept.get("week") == week else None
    if pick is None:
        pool = [p for p in people
                if p["dormant"] and not p["held"] and not p["oneoff"]]
        here = str((load_config().get("now") or {}).get("place") or "").lower()
        near = [p for p in pool if here and here in
                (p.get("where", "") + " " + " ".join(p.get("tags") or [])).lower()]
        pool = near or pool
        if pool:
            pick = random.Random(iso[0] * 100 + iso[1]).choices(
                pool, weights=[circle_weight(p["circle"]) for p in pool])[0]
            if live:
                try:
                    with open(RECONNECT_FILE, "w", encoding="utf-8") as f:
                        json.dump({"week": week, "name": pick["name"]}, f)
                except OSError:
                    pass
    if pick is not None and pick["dormant"]:
        pick["reconnect"] = True
        pick["flags"].append("reconnect")
        pick["score"] += round(25 * circle_weight(pick["circle"]))
    people.sort(key=lambda p: (-p["score"], p["name"]))
    return people


def is_past_rhythm(p):
    """The one "past their rhythm" count. People, the Plate's "Also needs
    you" and the Circles chip each counted it their own way and printed 90,
    89 and 89 (28 Sep). An owed reply is its own count and its own colour, so
    it is left out here, and on hold means no rhythm is ticking."""
    return bool(p.get("overdue") and not p.get("owed") and not p.get("held")
                and not p.get("oneoff"))


def _dnorm(s):
    """Task text, comparable: suffixes off, punctuation flattened."""
    s = re.sub(r"\((?:due|by|waiting until|planned|urgent|short:|at \d)[^)]*\)",
               "", s or "", flags=re.I)
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


SUBJECT_LINE = re.compile(r"^\s*\**(subject|objet|asunto|betreff|oggetto)\s*\**\s*:\s*\**\s*(.+?)\s*\**\s*$",
                          re.I)


def split_subject(body):
    """An email draft's subject when it was written as the body's first line
    ("Subject: …", "Objet : …") instead of in the frontmatter. Returns
    (subject, body without that line). Five of six email drafts were written
    that way (29 Sep), and Approve & send went out as "(no subject)" with the
    subject pasted into the message."""
    lines = (body or "").split("\n")
    for i, ln in enumerate(lines):
        if not ln.strip():
            continue
        m = SUBJECT_LINE.match(ln)
        if not m:
            break
        rest = lines[i + 1:]
        while rest and not rest[0].strip():
            rest = rest[1:]
        return m.group(2).strip(), "\n".join(rest)
    return "", body or ""


def load_drafts(today=None, items=None):
    """Things Claude has written for the owner to send or submit — emails,
    messages, form text, research notes. Each is a file in brain/drafts/ with
    frontmatter. The owner acts; Claude only prepares.

    Carries `personal`: true when the draft is to an Inner or Close person, in
    which case the page must offer NO send path at all, only copy. This is a
    boundary enforced in data, not just in the prompt.

    Also carries `stale`: a draft written for a moment that has passed should
    stop presenting itself as ready. Three ways that happens — its `expires:`
    date (optional frontmatter, for drafts tied to an event) is behind us;
    the task it names is now done, dropped or expired (or its workstream
    closed); or it has sat unsent past `drafts.fresh_days` (config, default
    14). Stale drafts fold on the page rather than disappear — the owner
    retires them, not the clock.
    """
    import glob
    ddir = os.path.join(BRAIN, "drafts")
    people = {p["name"].lower(): p for p in load_people(today=today)}
    today = today or date.today()
    cfg = load_config()
    fresh_days = int((cfg.get("drafts") or {}).get("fresh_days", 14))
    if items is None:
        items = load(cfg=cfg, today=today)
    closed = set()
    for w in items:
        for t in w["tasks"]:
            if (not w["live"]) or t["done"] or t.get("dropped") \
                    or t.get("expired"):
                n = _dnorm(t["text"])
                if len(n) >= 16:
                    closed.add(n)
    try:
        import run_policy
        _untrusted = run_policy.untrusted_drafts()
    except Exception:
        _untrusted = set()
    out = []
    for path in sorted(glob.glob(os.path.join(ddir, "*.md"))):
        try:
            with open(path, encoding="utf-8") as f:
                text = f.read()
        except OSError:
            continue
        meta, body = {}, text
        m = re.match(r"\A---\n(.*?)\n---\n(.*)\Z", text, re.S)
        if m:
            for line in m.group(1).splitlines():
                if ":" in line:
                    k, v = line.split(":", 1)
                    meta[k.strip().lower()] = v.strip()
            body = m.group(2).strip()
        status = meta.get("status", "draft").lower()
        if status in ("sent", "discarded"):
            continue
        kind = meta.get("kind", "note").lower()
        subject = meta.get("subject", "")
        if kind == "email" and not subject:
            subject, body = split_subject(body)
        person = meta.get("person", "")
        circle = ""
        # personal = never messageable by Claude. Default True (safe) when the
        # person or their group is unknown; otherwise the group's own flag.
        personal = True
        if person and person.lower() in people:
            pp = people[person.lower()]
            circle = pp.get("circle", "")
            personal = pp.get("personal", True)
        # Written by a run that was reading someone else's words: copy-only,
        # like a personal draft, whoever it is to (run_policy.py keeps the
        # list, outside any run's reach).
        untrusted = os.path.basename(path) in _untrusted
        personal = personal or untrusted
        # A label for drafts with bare frontmatter: the body's first heading
        # or line, so nothing renders as a blank "Note" row.
        title = ""
        for ln in body.splitlines():
            if ln.strip():
                title = re.sub(r"^#+\s*", "", ln.strip())[:60]
                break
        created = parse_date(meta.get("created"))
        expires = parse_date(meta.get("expires"))
        # Evidence it may have gone out: she and the person were in touch on
        # or after the day it was written. Beeper and mail move Last on
        # activity in either direction, so the page asks; it never marks.
        contact = ""
        if kind in ("email", "message") and created and person.lower() in people:
            last = parse_date(people[person.lower()].get("last"))
            if last and last >= created:
                contact = last.isoformat()
        tnorm = _dnorm(meta.get("task", ""))
        stale, why = False, ""
        if expires and expires < today:
            stale, why = True, "its date has passed"
        elif tnorm and len(tnorm) >= 16 and any(
                tnorm in c or c in tnorm for c in closed):
            stale, why = True, "the task it was written for is closed"
        elif created and (today - created).days > fresh_days:
            stale, why = True, f"sitting here {(today - created).days} days"
        out.append({
            "file": os.path.basename(path),
            "kind": kind,
            "contact": contact,
            "channel": meta.get("channel", "").lower(),
            "to": meta.get("to", ""),
            "subject": subject,
            "person": person,
            # Outreach drafts (outreach.py): the Stage sending it moves the
            # person to, LinkedIn's character limit, and their profile link.
            "stage": meta.get("stage", "").lower(),
            "limit": int(meta["limit"]) if meta.get("limit", "").isdigit() else 0,
            "linkedin": (people[person.lower()].get("linkedin", "")
                         if person and person.lower() in people else ""),
            "task": meta.get("task", ""),
            "circle": circle,
            "personal": personal,
            "untrusted": untrusted,
            "created": meta.get("created", ""),
            "expires": meta.get("expires", ""),
            "title": title,
            "stale": stale,
            "stale_why": why,
            "body": body,
        })
    return out


def drafts_record():
    """How many of the drafts meant to go to someone actually went: the
    closed loop on "draft by default". Counts every email and message draft
    by status, sent / not used / still open, from the files alone."""
    import glob
    rows = {}
    for path in glob.glob(os.path.join(BRAIN, "drafts", "*.md")):
        try:
            with open(path, encoding="utf-8") as f:
                head = f.read(2000)
        except OSError:
            continue
        m = re.match(r"\A---\n(.*?)\n---\n", head, re.S)
        meta = dict((k.strip().lower(), v.strip()) for k, v in
                    (l.split(":", 1) for l in (m.group(1).splitlines() if m else [])
                     if ":" in l))
        kind = meta.get("kind", "note").lower()
        if kind not in ("email", "message"):
            continue
        st = meta.get("status", "draft").lower()
        st = {"discarded": "not used"}.get(st, st if st == "sent" else "open")
        rows.setdefault(kind, {"sent": 0, "not used": 0, "open": 0})[st] += 1
    return rows


def briefing(items, cfg=None):
    """The four questions, answered from the files. Costs nothing to compute,
    which is why the page can show it every time it loads."""
    cfg = cfg or load_config()
    live = [w for w in items if w["live"]]
    return {
        "overdue": [w for w in live if w["overdue"]],
        "chase": [w for w in live if w["chase"]],
        "cold": [w for w in live if w["cold"] or w["never_touched"]],
        "soon": [w for w in live if w["due_soon"] and not w["overdue"]],
        "yours": [w for w in live if w["ball"] == "me"],
        "theirs": [w for w in live if w["ball"] == "them"],
        "live": live,
        "snoozed": [w for w in items if w.get("snoozed")],
        "closed": [w for w in items if not w["live"] and not w.get("snoozed")],
        "open_tasks": sum(w["open_tasks"] for w in live),
        "cold_days": int(cfg.get("cold_days", 14)),
        "chase_days": int(cfg.get("chase_days", 7)),
    }


def capacity_cfg(cfg=None):
    """How much time you actually have, and what to assume when a task has no
    estimate. A student's realistic *discretionary* project time — not 8 hours."""
    cfg = cfg or load_config()
    c = dict(cfg.get("capacity") or {})
    return {
        "daily_minutes": int(c.get("daily_minutes", 180)),
        "default_task_minutes": int(c.get("default_task_minutes", 30)),
        "reply_minutes": int(c.get("reply_minutes", 10)),
        "birthday_minutes": int(c.get("birthday_minutes", 20)),
        "horizon_days": int(c.get("horizon_days", 14)),
    }


DAY_END_MINUTES = 22 * 60      # the same 22:00 the When card draws the day to


def _plan_toks(s):
    """Words carrying a task's identity, for telling whether today's plan and
    a dated task are the same job. Deliberately crude — it only has to stop
    one errand being charged for twice."""
    return {w for w in re.findall(r"[a-zà-ÿ0-9€]+", (s or "").lower())
            if len(w) >= 4}


def free_minutes(starts, day_start=8 * 60, day_end=DAY_END_MINUTES,
                 after=None, block=90):
    """Minutes of a day the calendar leaves open. The calendar gives start
    times only, so each fixed thing is taken as `block` long — a class here
    runs 1h40, a meeting less; 90 errs slightly generous. `after` clips to
    what is still ahead (today)."""
    lo = day_start if after is None else max(day_start, after)
    busy = sorted((max(s, lo), min(s + block, day_end)) for s in starts)
    free, cur = 0, lo
    for a, b in busy:
        if b <= cur:
            continue
        if a > cur:
            free += a - cur
        cur = max(cur, b)
    return free + max(0, day_end - cur)


def forecast(items=None, people=None, cfg=None, today=None, now_minutes=None,
             plan_tasks=None, starts_by_day=None):
    """Motion's one honest question — will I make it? — answered from the files.

    Every open, dated thing becomes (when it's due, how long it takes). A task's
    time is its ~estimate or a default; a workstream's is the sum of its open
    tasks; an owed reply or a birthday is a small fixed cost. Then, for each
    deadline, the CUMULATIVE work due on or before it is checked against the
    time between now and then — because to hit Friday you must also clear
    everything due before Friday. Where the work outruns the time, it's at risk,
    and by how much. Nothing here writes; it only tells the truth about load.

    Late work is kept apart (28 Sep). Charged to today, nine overdue tasks
    and eleven owed replies made a two-hour plan read "today needs 14h20" —
    true of nothing she could act on. Late is a backlog to re-date or drop,
    so it is its own line, and the days ahead are judged without it.

    `starts_by_day` (iso date -> list of event start minutes) caps each day's
    room at what the calendar leaves free; without it every day is the flat
    `daily_minutes`.
    """
    from datetime import timedelta
    cfg = cfg or load_config()
    today = today or date.today()
    cap = capacity_cfg(cfg)
    if items is None:
        items = load(cfg=cfg, today=today)
    if people is None:
        try:
            people = load_people(today=today)
        except Exception:
            people = []
    daily, dflt, horizon = cap["daily_minutes"], cap["default_task_minutes"], cap["horizon_days"]

    # How much of today is actually LEFT. `daily_minutes` is a whole day's
    # discretionary time, so quoting it at nine at night promises hours that
    # have already gone — which is how the page came to say "you have ~3h" at
    # 22:11. Only TODAY's line is clamped; the multi-day deadline maths keeps
    # the full daily figure, because clamping that would tip every deadline
    # into the red every single evening and then quietly recover by morning.
    day_over = now_minutes is not None and now_minutes >= DAY_END_MINUTES
    left = (daily if now_minutes is None
            else max(0, min(daily, DAY_END_MINUTES - now_minutes)))
    starts_by_day = starts_by_day or {}

    def room(day):
        """A day's usable minutes: the daily figure, never more than the
        calendar leaves open."""
        starts = starts_by_day.get(day.isoformat())
        if day == today:
            if starts is None:
                return left
            return min(left, free_minutes(starts, after=now_minutes))
        if starts is None:
            return daily
        return min(daily, free_minutes(starts))

    dated = []          # every open, dated commitment
    for w in items:
        if not w["live"]:
            continue
        for t in w["tasks"]:
            if (t["done"] or t.get("parked") or t.get("dropped")
                    or not t.get("due")):
                continue
            d = parse_date(t["due"])
            if d:
                # `full` is the untruncated text, kept for matching only. The
                # 52-char label cut "…(for Guillau" mid-word, and a plan task
                # naming Lennox then failed to recognise its own twin.
                dated.append({"when": d, "min": t.get("est") or dflt,
                              "label": clip(t["text"], 52) or w["name"],
                              "full": t["text"], "kind": "task",
                              "ws": w["name"],
                              "tick": {"src": "workstreams.md", "text": t["text"]}})
        wd = parse_date(w.get("due"))
        if wd:
            rem, counted = 0, False
            for t in w["tasks"]:
                if (t["done"] or t.get("parked") or t.get("dropped")
                        or t.get("due")):
                    continue
                rem += (t.get("est") or dflt)
                counted = True
            dated.append({"when": wd, "min": rem if counted else dflt,
                          "label": w["name"], "kind": "workstream",
                          "ws": w["name"]})
    for p in (people or []):
        if p.get("oneoff"):
            continue
        if p.get("owed"):
            # Owed already, so late by definition: the backlog, not today.
            dated.append({"when": today - timedelta(days=1),
                          "min": cap["reply_minutes"],
                          "label": f"reply to {p['name']}", "kind": "person",
                          "who": p["name"]})
        bi = p.get("bday_in")
        if bi is not None and 0 <= bi <= horizon:
            dated.append({"when": today + timedelta(days=bi), "min": cap["birthday_minutes"],
                          "label": f"{p['name']}'s birthday", "kind": "birthday",
                          "who": p["name"]})

    # Today's PLAN counts as due today. Without this the forecast answered a
    # question nobody asked: it saw only things carrying an explicit due date,
    # so a day whose list was four real tasks reported "about 20m due" — the
    # 20m being two owed replies, and not one of the four. The page then said
    # "0 of 4 done" and "20m was due" a few inches apart, describing sets with
    # nothing in common.
    for pt in (plan_tasks or []):
        label = (pt.get("label") or "").strip()
        if not label:
            continue
        lt = _plan_toks(label)
        # BEST match, not the first, and three shared words rather than two.
        # Two was enough for "Buy return ticket Nantes → Paris" to be
        # swallowed by "Book train Lyon → Paris → Nantes" on the
        # strength of the two place names, which quietly deleted a task from
        # the day's total.
        scored = sorted(((len(lt & _plan_toks(d.get("full") or d["label"])), i, d)
                         for i, d in enumerate(dated)),
                        key=lambda x: -x[0])
        twin = scored[0][2] if scored and scored[0][0] >= 3 else None
        if twin is not None:
            # Same job, already dated. Putting it on the plan is her deciding
            # to do it TODAY, so pull it forward rather than adding a second
            # copy — one errand must not be charged for twice, and it must not
            # drop out of today's total either just because its own deadline
            # is later in the week.
            if twin["when"] > today:
                twin["when"] = today
            continue
        dated.append({"when": today, "min": pt.get("min") or dflt,
                      "label": clip(label, 52), "kind": "plan",
                      "tick": ({"src": "today.md", "text": pt["raw"]}
                               if pt.get("raw") else None)})

    horizon_date = today + timedelta(days=horizon)
    inview = [d for d in dated if d["when"] <= horizon_date]
    for d in inview:
        d["days"] = (d["when"] - today).days

    late = [d for d in inview if d["days"] < 0]
    ahead = [d for d in inview if d["days"] >= 0]
    today_items = [d for d in ahead if d["days"] == 0]
    today_min = sum(d["min"] for d in today_items)
    left = room(today)

    def _door(d):
        """An entry as the page lists it: its words and time, plus where it
        lives (the task's tick, its project, its person), so the card can
        make it a door to that home."""
        return {k: d[k] for k in ("label", "min", "kind", "ws", "who", "tick")
                if d.get(k) is not None}

    deadlines, capm = [], 0
    for i in range(horizon + 1):
        D = today + timedelta(days=i)
        capm += room(D)
        due_here = [d for d in ahead if d["when"] == D]
        if not due_here:
            continue
        need = sum(d["min"] for d in ahead if d["when"] <= D)
        deadlines.append({
            "when": D.isoformat(), "days": i,
            "need": need, "cap": capm, "at_risk": need > capm,
            "short": max(need - capm, 0),
            "own": sum(d["min"] for d in due_here),
            "label": (due_here[0]["label"] if len(due_here) == 1
                      else f"{len(due_here)} things"),
            "items": [_door(d) for d in due_here],
        })
    at_risk = [d for d in deadlines if d["at_risk"]]

    pull = None
    if today_min < left and at_risk:
        nxt = sorted((d for d in ahead if d["days"] > 0),
                     key=lambda d: (d["when"], -d["min"]))
        if nxt:
            pull = {"label": nxt[0]["label"], "min": nxt[0]["min"],
                    "days": nxt[0]["days"]}

    late.sort(key=lambda d: -d["min"])
    return {
        "cap": cap,
        "today": {"min": today_min, "daily": daily, "left": left,
                  "day_over": day_over, "fits": today_min <= left,
                  "over": max(today_min - left, 0),
                  "items": [{"label": d["label"], "min": d["min"]} for d in today_items]},
        "late": {"min": sum(d["min"] for d in late),
                 "tasks": sum(1 for d in late if d["kind"] != "person"),
                 "replies": sum(1 for d in late if d["kind"] == "person"),
                 "items": [_door(d) for d in late if d["kind"] != "person"]},
        "deadlines": deadlines, "at_risk": at_risk, "pull": pull,
        "has_data": bool(inview),
    }


if __name__ == "__main__":
    import sys

    if "--people" in sys.argv:
        # The cheap path for the people-touching commands: the flagged subset
        # in a few hundred bytes, instead of pinning all of people.md (~17k
        # tokens) on every later turn of a run.
        people = load_people()
        flagged = [p for p in people if p.get("flags")]
        print(f"{len(people)} people, {len(flagged)} flagged, "
              f"{sum(1 for p in people if p.get('dormant'))} dormant")
        LABELS = {"owed": "YOU OWE THEM A REPLY",
                  "promised": "A PROMISE IS DUE",
                  "chase": "ASKED, NO REPLY YET (CHASE)",
                  "bday_soon": "BIRTHDAY SOON",
                  "overdue": "QUIET PAST THEIR RHYTHM",
                  "reconnect": "RECONNECT THIS WEEK (A DORMANT TIE)",
                  "never": "NEVER BEEN IN TOUCH"}
        for key in ("owed", "promised", "chase", "bday_soon", "overdue",
                    "reconnect", "never"):
            rows = [p for p in flagged if key in p["flags"]]
            if not rows:
                continue
            print(f"\n{LABELS[key]}")
            for p in rows:
                bits = [p["circle"], f"every {p['every_label']}",
                        f"last {p['last'] or 'never'}"]
                if p.get("reach"):
                    bits.append(f"reach: {p['reach']}")
                if p.get("where"):
                    bits.append(p["where"])
                if key == "chase":
                    bits.append(f"asked {p['stage_since']}")
                print(f"  - {p['name']}  ({', '.join(bits)})")
        sys.exit(0)

    if "--drafts" in sys.argv:
        rec = drafts_record()
        tot = {k: sum(r[k] for r in rec.values()) for k in ("sent", "not used", "open")}
        closed = tot["sent"] + tot["not used"]
        print(f"Drafts to people: {tot['sent']} sent, {tot['not used']} not used, "
              f"{tot['open']} open"
              + (f" ({round(100 * tot['sent'] / closed)}% of closed ones used)"
                 if closed else ""))
        for kind, r in sorted(rec.items()):
            print(f"  {kind:8} {r['sent']} sent, {r['not used']} not used, {r['open']} open")
        waiting = [d for d in load_drafts() if d.get("contact")]
        if waiting:
            print("\nIn touch since written, not marked yet:")
            for d in waiting:
                print(f"  - {d['person']}  ({d['file']}, in touch {d['contact']})")
        sys.exit(0)

    ws = load()
    b = briefing(ws)
    print(f"{len(ws)} workstreams, {len(b['live'])} live, {b['open_tasks']} open tasks")
    for key, label in (("overdue", "OVERDUE"), ("chase", "NEEDS A CHASE"),
                       ("cold", "GOING COLD"), ("soon", "DUE SOON")):
        if b[key]:
            print(f"\n{label}")
            for w in b[key]:
                print(f"  - {w['name']}  ({w['status']}, ball: {w['ball']})")
    stale = [w for w in b["live"] if w.get("stale_text")]
    if stale:
        print("\nSTALE WORDING (a date in the line has passed — reword it "
              "to what is true today, in workstreams.md)")
        for w in stale:
            for s2 in w["stale_text"]:
                print(f"  - {w['name']}: {s2['where']} says \"{s2['label']}\"")
    # The plan's opening move: every live workstream already carries a
    # now/push/slow horizon — printing it here is what lets /today pick the
    # top item without reading workstreams.md raw.
    print("\nHORIZON")
    for hz in ("now", "push", "slow"):
        for w in b["live"]:
            if w.get("horizon") == hz:
                print(f"  {hz:<5} {w['name']}")
    held = [w for w in b["live"] if w.get("horizon") == "batch"]
    if held:
        day = ((load_config().get("now") or {}).get("batch") or {}).get("day", "")
        print(f"\nWEEKLY HOUR ({day}) — quiet until then, not in today's pools")
        for w in held:
            print(f"  - {w['name']}")

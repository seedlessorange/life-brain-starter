#!/usr/bin/env python3
"""The school day, phone-shaped: classes, what to read, who is speaking,
what is due.

    python3 brain/tools/school_brief.py             # tomorrow, as the evening push
    python3 brain/tools/school_brief.py --today     # today, as the morning block

The Telegram bridge sends the evening version once a day at 18:30 and folds
the morning version under the plan. "school" to the bot asks for it any time.

Everything here is a lookup over files the brain already keeps, with no model
call:

- Classes come from the calendar cache, matched against the course folders.
  The school's timetable feed titles its events "Course - SURNAME, First - Room - EN",
  which is where the room and the professor come from.
- Assignments are the open `(class)` tasks: the deliverables every classmate
  also owes, with a date inside the next seven days or already past.
- Readings are School tasks worded "Read …" with `(due <session date>)`.
- Guest speakers live in school/speakers.md. A LinkedIn line is used as given;
  without one the brief links a LinkedIn search for the name and company, and
  the brain never opens a profile itself.
- "Today's slides" checks whether a deck for each class that met today has
  landed in the class folder, in Downloads, or in the caught decks. It looks at
  names and dates only and opens nothing.
"""
import os
import re
import sys
import urllib.parse
from datetime import date, datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
BRAIN = os.path.dirname(HERE)
if HERE not in sys.path:
    sys.path.insert(0, HERE)

SPEAKERS = os.path.join(BRAIN, "school", "speakers.md")
SESSION_MINUTES = 90        # one class session; back-to-back ones are 100 apart
DUE_WINDOW = 7
READ_RX = re.compile(r"^(?:read|reading|listen|watch)\b", re.I)
# Homework is what a class sets, tagged `(class)` or not: "Complete the small
# Scaleup homework assignment" carried no tag and never reached the evening
# message (2 Oct). Late homework rides along for a week, then it is the
# plan's business, not tomorrow's.
HOMEWORK_RX = re.compile(r"\b(?:homework|assignments?|exercises?|problem sets?|"
                         r"essays?|papers?|quiz(?:zes)?|deliverables?)\b", re.I)
LATE_WINDOW = 7
ROOM_RX = re.compile(r"^[A-Z]{1,3}\s?\d{2,4}[A-Z]?$")
DAYNAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday",
            "Saturday", "Sunday"]


def _norm(s):
    return re.sub(r"[^a-z]", "", (s or "").lower())


def _nice(d):
    return f"{DAYNAMES[d.weekday()]} {d.day} {d.strftime('%b')}"


# --------------------------------------------------------------------------
# classes, from the calendar cache

def _courses():
    try:
        import school as S
        return [c["name"] for c in S.courses()]
    except Exception:
        return []


def _course_of(part, courses):
    """The course folder a calendar title names, or ""."""
    n = _norm(part)
    if len(n) < 6:
        return ""
    for c in courses:
        cn = _norm(c)
        if n == cn or n in cn or cn in n:
            return c
    return ""


def _events(day):
    """[(HH:MM, title)] for one day, from whatever the cache holds. Never
    waits on Calendar.app: a stale answer beats a bridge stuck for 100 s."""
    try:
        import calendar_read as CAL
        evs = CAL.events(7)
    except Exception:
        return []
    key = day.isoformat()
    return sorted({(str(s)[11:16], t) for s, t in evs if str(s)[:10] == key})


def schedule(day, courses=None):
    """(classes, others). A class is one course's sessions that day merged
    into a block: {"course", "start", "end", "room", "prof"}."""
    courses = _courses() if courses is None else courses
    blocks, others = {}, []
    for hhmm, title in _events(day):
        parts = [p.strip() for p in re.split(r"\s+-\s+", title) if p.strip()]
        course = _course_of(parts[0] if parts else title, courses)
        timetable = len(parts) >= 3 and any(ROOM_RX.match(p) for p in parts)
        if not course and timetable:
            course = parts[0]
        if not course:
            others.append((hhmm, title))
            continue
        b = blocks.setdefault(course, {"course": course, "starts": set(),
                                       "room": "", "prof": ""})
        b["starts"].add(hhmm)
        for p in parts[1:]:
            if ROOM_RX.match(p) and not b["room"]:
                b["room"] = p
            elif "," in p and not b["prof"]:
                last, first = [x.strip() for x in p.split(",", 1)]
                b["prof"] = f"{first} {last.title()}".strip()
    classes = []
    for b in blocks.values():
        starts = sorted(b.pop("starts"))
        end = (datetime.strptime(starts[-1], "%H:%M")
               + timedelta(minutes=SESSION_MINUTES)).strftime("%H:%M")
        b.update(start=starts[0], end=end)
        classes.append(b)
    classes.sort(key=lambda b: b["start"])
    return classes, others


def _class_line(b):
    extra = ", ".join(x for x in (b["room"], b["prof"]) if x)
    return (f"• {b['course']}  {b['start']}–{b['end']}"
            + (f"  ({extra})" if extra else ""))


# --------------------------------------------------------------------------
# assignments and readings, from the workstreams

def _tidy(text):
    t = re.sub(r"\s*\((?:class|reading|urgent)\)", "", text, flags=re.I)
    t = re.sub(r"\s*~\d+\s*(?:h\d*|m|min)\b", "", t)
    t = re.sub(r"\s*\(from syllabus[^)]*\)", "", t, flags=re.I)
    t = t.strip(" —-")
    return t if len(t) <= 90 else t[:88].rstrip() + "…"


def _open_school_tasks():
    try:
        import model as M
        items = M.load()
    except Exception:
        return []
    out = []
    for w in items:
        if not w["live"] or w["area"] != "School":
            continue
        for t in w["tasks"]:
            if t["done"] or t.get("parked") or t.get("dropped"):
                continue
            out.append(t)
    return out


def _due_date(t):
    dd = t.get("due_days")
    return None if dd is None else date.today() + timedelta(days=dd)


def assignments(day, window=DUE_WINDOW, tasks=None):
    """Open (class) tasks due up to `window` days after `day`, late ones
    included. [(due date, text)] soonest first."""
    tasks = _open_school_tasks() if tasks is None else tasks
    out = []
    for t in tasks:
        if "(class)" not in t["text"].lower() or READ_RX.match(t["text"]):
            continue
        d = _due_date(t)
        if d is None or (d - day).days > window:
            continue
        out.append((d, _tidy(t["text"])))
    return sorted(out)


def homework(day, tasks=None):
    """Homework due on `day`, plus any still open from the week before it.
    [(due date, text)] soonest first."""
    tasks = _open_school_tasks() if tasks is None else tasks
    out = []
    for t in tasks:
        if READ_RX.match(t["text"]):
            continue
        if not (HOMEWORK_RX.search(t["text"])
                or "(class)" in t["text"].lower()):
            continue
        d = _due_date(t)
        if d is not None and 0 <= (day - d).days <= LATE_WINDOW:
            out.append((d, _tidy(t["text"])))
    return sorted(out)


def _late(d, day):
    """" (was due Thursday)" for a date before `day`, else ""."""
    if d >= day:
        return ""
    n = (date.today() - d).days
    return ("  (was due today)" if n == 0 else
            "  (was due yesterday)" if n == 1 else
            f"  (was due {DAYNAMES[d.weekday()]})" if n < 7 else
            f"  ({n} days late)")


def readings(day, tasks=None):
    """'Read …' School tasks due on `day` or already past."""
    tasks = _open_school_tasks() if tasks is None else tasks
    out = []
    for t in tasks:
        d = _due_date(t)
        if READ_RX.match(t["text"]) and d is not None and d <= day:
            out.append((d, _tidy(t["text"])))
    return sorted(out)


def _when(d):
    """A due date said the way a person would, counted from today."""
    n = (d - date.today()).days
    if n < 0:
        return f"{-n} day{'s' if n < -1 else ''} late"
    if n == 0:
        return "today"
    if n == 1:
        return "tomorrow"
    return f"{DAYNAMES[d.weekday()][:3]} {d.day} {d.strftime('%b')}"


# --------------------------------------------------------------------------
# guest speakers, from school/speakers.md

def _linkedin(raw, name, company):
    v = (raw or "").strip().strip("<>")
    if v:
        if v.startswith("http"):
            return v
        if v.startswith(("linkedin.com", "www.linkedin.com")):
            return "https://" + v.lstrip("/")
        return "https://www.linkedin.com/in/" + v.split("in/")[-1].strip("/")
    q = urllib.parse.quote(" ".join(x for x in (name, company) if x))
    return f"https://www.linkedin.com/search/results/people/?keywords={q}"


def speakers(day=None):
    """Every speaker on file, or those on `day`. Fenced blocks are the
    format example, never a speaker."""
    try:
        with open(SPEAKERS, encoding="utf-8") as f:
            text = f.read()
    except OSError:
        return []
    text = re.sub(r"```.*?```", "", text, flags=re.S)
    out = []
    for m in re.finditer(r"^## (.+?)\n(.*?)(?=^## |\Z)", text, re.M | re.S):
        body = m.group(2)
        fields = {k.lower(): v.strip() for k, v in re.findall(
            r"^- \*\*(\w+):\*\*\s*(.*)$", body, re.M)}
        brief = " ".join(ln.strip() for ln in body.split("\n")
                         if ln.strip() and not ln.strip().startswith("- **"))
        try:
            import model as M
            d = M.parse_date(fields.get("date", ""))
        except Exception:
            d = None
        if day and d != day:
            continue
        name = m.group(1).strip()
        out.append({"name": name, "date": d, "class": fields.get("class", ""),
                    "role": fields.get("role", ""),
                    "company": fields.get("company", ""),
                    "link": _linkedin(fields.get("linkedin"), name,
                                      fields.get("company", "")),
                    "brief": brief})
    return out


def _speaker_lines(s):
    who = ", ".join(x for x in (s["role"], s["company"]) if x)
    head = f"• {s['name']}" + (f" — {who}" if who else "")
    if s["class"]:
        head += f"  ({s['class']})"
    lines = [head, "  " + s["link"]]
    if s["brief"]:
        b = s["brief"]
        lines.append("  " + (b if len(b) <= 420 else b[:418].rstrip() + "…"))
    return lines


# --------------------------------------------------------------------------
# did today's slides make it in?

def slides_landed(day, courses):
    """{course: bool} for the courses that met on `day`: has a deck file
    dated that day reached the class folder, the caught decks or Downloads?
    Names and dates only; nothing is opened."""
    try:
        import school as S
    except Exception:
        return {}
    got = {c: False for c in courses}
    if not got:
        return got
    key = day.isoformat()
    known = S.courses()
    try:
        for f in S.files():
            if date.fromtimestamp(f["mtime"]).isoformat() != key:
                continue
            c = f["course"] if f["course"] in got else S.classify_name(
                f["name"], known)
            if c in got:
                got[c] = True
    except Exception:
        pass
    dl = os.path.expanduser("~/Downloads")
    try:
        for de in os.scandir(dl):
            if not de.is_file() or S.is_confidential(de.name):
                continue
            if os.path.splitext(de.name)[1].lower() not in S.READABLE:
                continue
            if date.fromtimestamp(de.stat().st_mtime).isoformat() != key:
                continue
            c = S.classify_name(de.name, known)
            if c in got:
                got[c] = True
    except OSError:
        pass
    return got


# --------------------------------------------------------------------------
# the messages

def evening(today=None, force=False):
    """The brief for tomorrow, or None on an evening with nothing worth a
    message. Sunday always sends, as the week ahead.

    It only ever says what is on (her rule, 2 Oct): no "No classes.", no
    "Readings: none on file." Something late rides along but never sends
    the message alone: a Saturday ping about Thursday's reading is noise."""
    today = today or date.today()
    tom = today + timedelta(days=1)
    courses = _courses()
    tasks = _open_school_tasks()
    classes, others = schedule(tom, courses)
    reads = readings(tom, tasks)
    work = homework(tom, tasks)
    spk = speakers(tom)
    shown = {t for _, t in work}
    due = [x for x in assignments(tom, tasks=tasks) if x[1] not in shown]
    if not (force or classes or spk or today.weekday() == 6
            or any(d == tom for d, _ in reads + work + due)):
        return None

    out = [f"🎓 School tomorrow — {_nice(tom)}"]
    if classes:
        out += ["", "🏫 Classes"] + [_class_line(b) for b in classes]
    if reads:
        out += ["", "📖 Read before class"] + [
            "• " + t + _late(d, tom) for d, t in reads]
    if work:
        out += ["", "✏️ Homework"] + [
            "• " + t + _late(d, tom) for d, t in work]
    if spk:
        out += ["", "🎤 Guest speaker" + ("s" if len(spk) > 1 else "")]
        for s in spk:
            out += _speaker_lines(s)
    if due:
        out += ["", f"📅 Due in the next {DUE_WINDOW} days"] + [
            f"• {_when(d)}: {t}" for d, t in due]
    if others:
        out += ["", "🗓️ Also tomorrow"] + [f"• {h} {t}" for h, t in others]
    met, _ = schedule(today, courses)
    if met:
        landed = slides_landed(today, [b["course"] for b in met])
        missing = [c for c, ok in landed.items() if not ok]
        have = [c for c, ok in landed.items() if ok]
        out += ["", "🗂️ Today's slides"]
        out += [f"• {c}: in ✓" for c in have]
        out += [f"• {c}: not yet. Download it from Blackboard into "
                "Downloads and tomorrow morning's run files it."
                for c in missing]
    if len(out) == 1:
        out += ["", "Nothing on file for tomorrow."]
    return "\n".join(out).strip()


def morning(today=None):
    """A short school block for under the morning plan, or ""."""
    today = today or date.today()
    tasks = _open_school_tasks()
    classes, _ = schedule(today)
    spk = speakers(today)
    reads = readings(today, tasks)
    work = [x for x in homework(today, tasks) if x[0] == today]
    shown = {t for _, t in work}
    due = [x for x in assignments(today, window=1, tasks=tasks)
           if x[1] not in shown]
    if not (classes or spk or reads or work or due):
        return ""
    out = ["🎓 School today"]
    out += [_class_line(b) for b in classes]
    for s in spk:
        out += ["🎤 " + ln if not i else ln
                for i, ln in enumerate(_speaker_lines(s))]
    out += ["📖 " + t for _, t in reads]
    out += [f"✏️ {t}" for _, t in work]
    out += [f"✏️ Due {_when(d)}: {t}" for d, t in due]
    return "\n".join(out)


def on_demand(now=None):
    """What 'school' to the bot answers: tomorrow after 15:00, else today."""
    now = now or datetime.now()
    if now.hour >= 15:
        return evening(now.date(), force=True)
    today = now.date()
    courses = _courses()
    tasks = _open_school_tasks()
    classes, others = schedule(today, courses)
    out = [f"School today — {_nice(today)}"]
    out += ([""] + [_class_line(b) for b in classes]) if classes \
        else ["", "No classes."]
    reads = readings(today, tasks)
    if reads:
        out += ["", "Read before class"] + ["• " + t for _, t in reads]
    spk = speakers(today)
    if spk:
        out += ["", "Guest speaker" + ("s" if len(spk) > 1 else "")]
        for s in spk:
            out += _speaker_lines(s)
    due = assignments(today, tasks=tasks)
    if due:
        out += ["", f"Due in the next {DUE_WINDOW} days"] + [
            f"• {_when(d)}: {t}" for d, t in due]
    return "\n".join(out)


if __name__ == "__main__":
    if "--today" in sys.argv:
        print(morning() or "(nothing school-shaped today)")
    else:
        print(evening(force=True))

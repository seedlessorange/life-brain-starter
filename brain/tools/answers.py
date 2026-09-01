#!/usr/bin/env python3
"""Mechanical answers, so the phone rarely needs to spend anything.

    python3 brain/tools/answers.py "what's on tomorrow"

Most of what she asks a phone is a lookup, not a thought: what is on
tomorrow, who is owed a reply, what is overdue, where am I, what is on the
shopping list. Every one of those is already sitting in a markdown file, and
sending it to a model to be re-read is paying for a grep.

So the Telegram bridge tries this module FIRST and only falls through to
`ask:` when nothing here matches. Each route is a plain function over the
files; there is no model call anywhere in this file, and there must not be.

Adding a route: write the matcher into ROUTES with a phrase list and a
function returning text (or None to fall through). Keep the answers phone
shaped — short lines, no markdown furniture, no tables.
"""
import json
import os
import re
import sys
from datetime import date, datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
BRAIN = os.path.dirname(HERE)

DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday",
        "Sunday"]


def _read(name):
    try:
        with open(os.path.join(BRAIN, name), encoding="utf-8") as f:
            return f.read()
    except OSError:
        return ""


def _model():
    import model
    return model


def _tasks_of(w):
    """Open task texts of a workstream, deadline suffixes kept."""
    out = []
    for t in w.get("tasks") or []:
        txt = t.get("text") if isinstance(t, dict) else str(t)
        done = t.get("done") if isinstance(t, dict) else False
        if txt and not done:
            out.append(txt)
    return out


def _workstreams():
    M = _model()
    return M.parse(_read("workstreams.md"))


def _clean(s):
    """Strip the markdown furniture a phone should never see."""
    s = re.sub(r"\*\*(.+?)\*\*", r"\1", s)
    s = re.sub(r"`([^`]+)`", r"\1", s)
    s = re.sub(r"^\s*[-*]\s+\[([ xX])\]\s*", lambda m:
               "done: " if m.group(1).lower() == "x" else "- ", s)
    return s.strip()


# ---------------------------------------------------------------- routes

def r_tomorrow(_q):
    """Tomorrow, from the week sketch plus anything actually dated to it."""
    M = _model()
    tm = date.today() + timedelta(days=1)
    iso, label = tm.isoformat(), DAYS[tm.weekday()]
    lines = []

    body = _read("week-plan.md")
    block = re.search(rf"^##\s+.*{re.escape(iso)}.*$(.*?)(?=^##\s|\Z)",
                      body, re.M | re.S)
    if not block:
        block = re.search(rf"^##\s+{label}\b.*$(.*?)(?=^##\s|\Z)",
                          body, re.M | re.S)
    if block:
        for ln in block.group(1).strip().splitlines():
            if ln.strip():
                lines.append(_clean(ln))

    dated = []
    for w in _workstreams():
        for t in _tasks_of(w):
            d = M.parse_due(t, today=date.today())
            end = None
            if isinstance(d, dict):
                end = d.get("end") or d.get("date")
            elif d:
                end = d
            if end and str(end)[:10] == iso:
                dated.append(f"- {M._plain(t)}  ({w['name']})")
    if dated:
        lines.append("")
        lines.append("Dated to tomorrow:")
        lines += dated

    if not lines:
        return (f"Nothing written for {label} {tm.strftime('%d %b')} yet. "
                "Sunday's plan sketches the week; the morning run fills the "
                "day in.")
    return f"{label} {tm.strftime('%d %b')}\n\n" + "\n".join(lines)


def r_today(_q):
    from telegram_bridge import _plan_text
    return _plan_text()


def r_week(_q):
    body = _read("week-plan.md")
    if not body.strip():
        return None
    out = []
    for ln in body.splitlines():
        if ln.startswith("# ") or not ln.strip():
            continue
        out.append(_clean(ln) if not ln.startswith("## ")
                   else "\n" + ln[3:].strip())
    return "The week\n" + "\n".join(out[:40])


def r_overdue(_q):
    M = _model()
    today = date.today()
    late = []
    for w in _workstreams():
        due = (w["fields"].get("Due") or "").strip()
        if due:
            d = M.parse_date(due)
            if d and d < today:
                late.append(f"- {w['name']} — due {due}, "
                            f"{(today - d).days}d ago")
        for t in _tasks_of(w):
            d = M.parse_due(t, today=today)
            end = d.get("end") if isinstance(d, dict) else d
            if end and str(end)[:10] < today.isoformat():
                late.append(f"- {M._plain(t)}  ({w['name']})")
    if not late:
        return "Nothing is past its date. "
    return f"{len(late)} past their date\n\n" + "\n".join(late[:20])


def r_chase(_q):
    out = []
    for w in _workstreams():
        f = w["fields"]
        ball = (f.get("Ball") or "").strip()
        since = (f.get("Since") or "").strip()
        if ball.lower().startswith("them"):
            days = ""
            d = _model().parse_date(since)
            if d:
                days = f", {(date.today() - d).days}d"
            out.append(f"- {w['name']} — {ball}{days}")
    rows = []
    body = _read("waiting.md")
    for ln in body.splitlines():
        if ln.startswith("|") and "---" not in ln and "Waiting for" not in ln:
            cells = [c.strip() for c in ln.strip("|").split("|")]
            if len(cells) >= 3 and cells[0]:
                rows.append(f"- {cells[0]} — {cells[1]} (since {cells[2]})")
    parts = []
    if out:
        parts.append("Ball with them\n" + "\n".join(out))
    if rows:
        parts.append("Waiting on\n" + "\n".join(rows))
    return "\n\n".join(parts) if parts else "Nothing is sitting with anyone else."


def r_people(_q):
    """Who is owed a reply, and who has gone quiet. Straight off model.py, so
    it costs a parse and nothing else."""
    import subprocess
    try:
        out = subprocess.run(
            [sys.executable, os.path.join(HERE, "model.py"), "--people"],
            capture_output=True, text=True, timeout=60).stdout
    except Exception:
        return None
    keep, section = [], ""
    for ln in out.splitlines():
        if ln and not ln.startswith(" ") and ln.isupper():
            section = ln
            keep.append("\n" + ln.title())
            continue
        if ln.strip().startswith("-") and section:
            keep.append(_clean(ln))
    if not keep:
        return "Nobody is overdue. "
    return "\n".join(keep[:26]).strip()


def r_next(_q):
    body = _read("next.md")
    items = re.findall(r"^\s*\d+\.\s+(.+?)(?=^\s*\d+\.|\n---|\Z)",
                       body, re.M | re.S)
    if not items:
        return None
    out = []
    for i, it in enumerate(items[:5], 1):
        out.append(f"{i}. " + _clean(re.sub(r"\s+", " ", it)).strip())
    return "Worth your next hour\n\n" + "\n\n".join(out)


def r_where(_q):
    """Where she is, and what that makes of the day.

    The brain already changes its plan with the house — the weather place,
    the kitchen mode, the people near her — but all of that was only visible
    on the page. This is that answer, on the phone."""
    bits = []
    place = ""
    try:
        w = json.loads(_read(".weather.json") or "{}")
        place = w.get("place") or ""
        t = w.get("today") or {}
        if place:
            bits.append(f"You are set to {place}.")
        if t:
            bits.append(f"Today there: {t.get('low')}–{t.get('high')}°C, "
                        f"rain {t.get('rain')}%, sunset {t.get('sunset')}.")
        tm = w.get("tomorrow") or {}
        if tm:
            bits.append(f"Tomorrow: {tm.get('low')}–{tm.get('high')}°C, "
                        f"rain {tm.get('rain')}%.")
    except Exception:
        pass
    try:
        import cook
        p = cook.load_pantry()
        bits.append("Kitchen is on " +
                    ("dorm — two burners, no oven." if p.get("kitchen") == "dorm"
                     else "full kitchen."))
    except Exception:
        pass
    near = []
    if place:
        town = place.split(",")[0].strip().lower()
        for blk in re.split(r"^## ", _read("people.md"), flags=re.M)[1:]:
            name = blk.splitlines()[0].strip()
            m = re.search(r"^-\s+\*\*Where:\*\*\s*(.+)$", blk, re.M)
            if m and town and town[:5] in m.group(1).strip().lower():
                near.append(name)
    if near:
        bits.append("Near you: " + ", ".join(near[:8]) + ".")
    cap = ""
    try:
        cfg = json.loads(_read("config.json") or "{}")
        mins = ((cfg.get("capacity") or {}).get("daily_minutes"))
        if mins:
            cap = (f"A normal day here is about {mins // 60}h{mins % 60 or ''} "
                   "of real work.")
    except Exception:
        pass
    if cap:
        bits.append(cap)
    if not bits:
        return None
    bits.append("\nIf that is the wrong house, say “here: <place>” and I will "
                "move the weather and the plan with you.")
    return "\n".join(bits)


def r_habits(_q):
    body = _read("habits.md")
    today = date.today()
    monday = today - timedelta(days=today.weekday())
    out = []
    for blk in re.split(r"^## ", body, flags=re.M)[1:]:
        name = blk.splitlines()[0].strip()
        tgt = re.search(r"^-\s+\*\*Target:\*\*\s*(\d+)", blk, re.M)
        log = re.search(r"^-\s+\*\*Log:\*\*\s*(.*)$", blk, re.M)
        if not tgt:
            continue
        dates = re.findall(r"\d{4}-\d{2}-\d{2}", log.group(1) if log else "")
        n = sum(1 for d in dates if d >= monday.isoformat())
        out.append(f"- {name}: {n}/{tgt.group(1)} this week")
    return "Habits\n\n" + "\n".join(out) if out else None


def r_shopping(_q):
    body = _read("cooking/shopping.md")
    items = [_clean(ln) for ln in body.splitlines()
             if re.match(r"^\s*[-*]\s+\[ \]", ln)]
    if not items:
        return "The shopping list is empty. Build one from a week's plan on "\
               "the Cook page."
    return f"Shopping — {len(items)} left\n\n" + "\n".join(items[:40])


def r_cooking(_q):
    body = _read("cooking/plan.md")
    today = date.today()
    monday = (today - timedelta(days=today.weekday())).isoformat()
    blk = re.search(rf"^##\s+Week of {monday}(.*?)(?=^##\s|\Z)",
                    body, re.M | re.S)
    if not blk or not blk.group(1).strip():
        return "No dinners planned this week. Plan my week on the Cook page "\
               "picks a set that shares its shopping."
    lines = [_clean(re.sub(r"\{id:[^}]*\}", "", ln))
             for ln in blk.group(1).strip().splitlines() if ln.strip()]
    return "Dinners this week\n\n" + "\n".join(lines)


def r_countdowns(_q):
    M = _model()
    out = []
    for ln in _read("countdowns.md").splitlines():
        m = re.match(r"^-\s+(.+?)\s+—\s+(.+)$", ln.strip())
        if not m:
            continue
        d = M.parse_date(m.group(2).strip())
        if d and d >= date.today():
            out.append(f"- {m.group(1)}: {(d - date.today()).days}d "
                       f"({d.strftime('%d %b')})")
    return "Counting down\n\n" + "\n".join(out) if out else None


ROUTES = [
    (("tomorrow", "demain", "what's on tomorrow", "whats on tomorrow"),
     r_tomorrow),
    (("today", "plan", "aujourd'hui"), r_today),
    (("week", "this week", "the week", "week ahead", "week plan"), r_week),
    (("overdue", "late", "past due", "what's late", "whats late", "en retard"),
     r_overdue),
    (("chase", "chasing", "waiting on", "waiting for", "who owes me",
      "ball with them"), r_chase),
    (("who do i owe", "owe a reply", "people", "who is quiet", "gone quiet",
      "who should i message", "replies"), r_people),
    (("next", "next hour", "what should i do", "what now"), r_next),
    (("where am i", "where", "which house", "the day's shape", "here"),
     r_where),
    (("habits", "streak", "streaks"), r_habits),
    (("shopping", "shopping list", "courses", "groceries"), r_shopping),
    (("dinners", "dinner", "meal plan", "what's for dinner",
      "whats for dinner", "cooking"), r_cooking),
    (("countdown", "countdowns", "days until", "how long until"),
     r_countdowns),
]


FILLER = re.compile(r"^(?:what(?:'s| is|s)?|whats|show me|show|tell me|give me"
                    r"|list|the|my|me|on|for|is|are|do i have|any)\b\s*")


def answer(query, strict=False):
    """A string in, a phone-shaped string out, or None when this module
    cannot help and the question deserves a model.

    `strict` is what keeps "call the plumber tomorrow" a task rather than a
    lookup: it demands the message be essentially the phrase itself, so only
    a bare "tomorrow" reaches the route. The bridge uses strict for anything
    that does not already read as a question."""
    q = " ".join((query or "").lower().split()).strip(" ?.!")
    if not q:
        return None
    bare = q
    for _ in range(3):
        bare = FILLER.sub("", bare).strip()
    best, best_len = None, 0
    for phrases, fn in ROUTES:
        for p in phrases:
            # a whole-phrase match, so "next" does not swallow "what's on
            # tomorrow" and "week" does not swallow "weekend"
            if not re.search(rf"(?<![a-z]){re.escape(p)}(?![a-z])", q):
                continue
            if strict:
                # the message must BE the question, not merely contain it
                rest = re.sub(rf"(?<![a-z]){re.escape(p)}(?![a-z])", "",
                              bare).strip(" ?.!,")
                if len(rest.split()) > 1:
                    continue
            if len(p) > best_len:
                best, best_len = fn, len(p)
    if not best:
        return None
    try:
        return best(q)
    except Exception as exc:                            # noqa: BLE001
        return f"That lookup broke: {exc}"


if __name__ == "__main__":
    q = " ".join(sys.argv[1:])
    if not q:
        print(__doc__)
        print("routes:", ", ".join(p[0] for p, _ in ROUTES))
        sys.exit(0)
    out = answer(q)
    print(out if out else "(no mechanical answer — this one needs ask:)")

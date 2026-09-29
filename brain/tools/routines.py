#!/usr/bin/env python3
"""Build brain/routines.html — the routines she runs her days on.

    python3 brain/tools/routines.py            # build the page
    python3 brain/tools/routines.py --today    # one line per routine, for /today

GENERATED. Never hand-edit routines.html.

One markdown file per routine in brain/routines/. The file is hers — prose,
tables, whatever the routine needs — with a small header the parser reads:

    # Skincare & beauty
    - **When:** morning, night
    - **Time:** ~10 min morning, ~10 min night
    - **Days:** daily — the night active rotates

`When` names the day's slots (morning, midday, afternoon, evening, night).
If the file contains a table whose first column is Mon..Sun, that is the
week's rotation: the page highlights today's row and `--today` prints it,
which is how the daily plan knows what tonight asks of her.
"""

import html
import json
import os
import re
import sys
from datetime import date, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import md as MD          # noqa: E402

BRAIN = os.path.dirname(HERE)
RDIR = os.path.join(BRAIN, "routines")
OUT = os.path.join(BRAIN, "routines.html")

SLOTS = ["morning", "midday", "afternoon", "evening", "night"]
DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
DAY_FULL = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday",
            "Saturday", "Sunday"]
DAY_MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep",
           "Oct", "Nov", "Dec"]


def _field(body, name):
    m = re.search(r"^- \*\*" + name + r":\*\*\s*(.+)$", body, re.M | re.I)
    return m.group(1).strip() if m else ""


def _week_table(body):
    """The first table whose data rows start Mon..Sun: {day: [(label, val)]}.

    Returns (labels, rows) — labels are the header's other columns, rows map
    a day to its values in header order. Empty cells are dropped later.
    """
    lines = body.split("\n")
    for i, ln in enumerate(lines):
        if not (ln.strip().startswith("|") and ln.strip().endswith("|")):
            continue
        header = [c.strip() for c in ln.strip().strip("|").split("|")]
        # need a separator row then at least one day row
        if i + 2 >= len(lines):
            continue
        if not re.match(r"^\s*\|[\s:|-]+\|\s*$", lines[i + 1]):
            continue
        rows = {}
        j = i + 2
        while j < len(lines):
            s = lines[j].strip()
            if not (s.startswith("|") and s.endswith("|")):
                break
            cells = [c.strip() for c in s.strip("|").split("|")]
            day = cells[0][:3].title()
            if day not in DAYS:
                break
            rows[day] = cells[1:]
            j += 1
        # A rota is a table where EVERY row is a day — two rows is a real
        # schedule (volleyball), but one day-looking row in a bigger table
        # is a coincidence.
        ended_clean = not (j < len(lines)
                           and lines[j].strip().startswith("|")
                           and lines[j].strip().endswith("|"))
        if len(rows) >= 2 and ended_clean:
            return header[1:], rows
    return [], {}


def load():
    """Every routine, parsed. Sorted by filename so she controls the order
    with a number prefix if she ever wants one."""
    out = []
    if not os.path.isdir(RDIR):
        return out
    for fn in sorted(os.listdir(RDIR)):
        if not fn.endswith(".md") or fn.startswith("."):
            continue
        with open(os.path.join(RDIR, fn), encoding="utf-8") as f:
            _, body = MD.split_frontmatter(f.read())
        m = re.search(r"^#\s+(.+)$", body, re.M)
        name = m.group(1).strip() if m else os.path.splitext(fn)[0]
        when = [s for s in SLOTS
                if re.search(r"\b" + s + r"\b", _field(body, "When"), re.I)]
        labels, rota = _week_table(body)
        # A cadence rather than a weekly rhythm: `Every: 14 days` (or
        # `2 weeks`), and `Last: YYYY-MM-DD` filed each time she does it.
        ev = _field(body, "Every")
        m2 = re.search(r"\d+", ev)
        every = int(m2.group()) if m2 else 0
        if every and re.search(r"week", ev, re.I):
            every *= 7
        last = None
        m3 = re.match(r"\d{4}-\d{2}-\d{2}", _field(body, "Last"))
        if m3:
            try:
                last = date.fromisoformat(m3.group())
            except ValueError:
                pass
        out.append({
            "file": fn,
            "name": name,
            "when": when,
            "time": _field(body, "Time"),
            "days": _field(body, "Days"),
            "every": every,
            "last": last,
            "rota_labels": labels,
            "rota": rota,
            "body": body,
        })
    return out


def due(r, on=None):
    """(state, line) for an every-N-days routine, else None. States:
    'due', 'later', 'unlogged'."""
    if not r["every"]:
        return None
    if not r["last"]:
        return ("unlogged", "no date yet — tell Claude when you last did it")
    days = ((on or date.today()) - r["last"]).days
    left = r["every"] - days
    if left <= 0:
        return ("due", f"due — the last one was {days} days ago")
    return ("later", f"next in {left} days")


def today_line(r, day=None):
    """One line the daily plan can read: name, slots, and today's rotation."""
    day = day or DAYS[date.today().weekday()]
    bits = [r["name"]]
    if r["when"]:
        bits.append(" + ".join(r["when"])
                    + (f" ({r['time']})" if r["time"] else ""))
    elif r["days"]:
        bits.append(r["days"])
    vals = r["rota"].get(day) or []
    pairs = [f"{lab}: {v}" for lab, v in zip(r["rota_labels"], vals) if v]
    if pairs:
        bits.append("today — " + " · ".join(pairs))
    elif r["rota"]:
        bits.append("nothing today")
    d = due(r)
    if d:
        bits.append(d[1])
    return " — ".join(bits)


def load_habits():
    """Name, weekly target and clock time for each habit — the grid pins
    the timed ones to their hour, the rest ride the loose lane."""
    out = []
    try:
        with open(os.path.join(BRAIN, "habits.md"), encoding="utf-8") as f:
            _, body = MD.split_frontmatter(f.read())
    except OSError:
        return out
    for sec in re.split(r"^## +", body, flags=re.M)[1:]:
        name = sec.split("\n", 1)[0].strip()
        when = _field(sec, "When")
        m = re.search(r"\b(\d{1,2}):(\d{2})\b", when)
        tgt = _field(sec, "Target")
        out.append({"name": name,
                    "t": f"{int(m.group(1)):02d}:{m.group(2)}" if m else "",
                    "target": tgt})
    return out


_CLOCK = re.compile(r"(\d{1,2})[:h](\d{2})\s*[–—-]\s*(\d{1,2})[:h](\d{2})")


def week_data(routines):
    """Everything the week grid draws, in one bag.

    Days are the next seven starting today. Events come from the calendar's
    ten-minute cache (calendar_read stale-serves and refreshes behind the
    build, so this never waits on the Calendar app). Routines whose Time is
    a clock range become blocks on their rota days; habits with a clock
    become daily pins; the rest are the week's loose load.
    """
    today_d = date.today()
    days = []
    for i in range(7):
        d = today_d + timedelta(days=i)
        days.append({"iso": d.isoformat(), "dow": DAYS[d.weekday()],
                     "label": ("Today" if i == 0 else DAYS[d.weekday()])
                     + d.strftime(" %d").replace(" 0", " ")})

    events = []
    try:
        import calendar_read
        # Lengths, where the calendar gave one: a box as tall as the class
        # (28 Sep — every box was an hour whatever it held).
        try:
            lens = calendar_read.lengths()
        except Exception:
            lens = {}
        seen = set()
        for when, title in calendar_read.events(7):
            if re.match(r"\s*canceled", title, re.I):
                continue
            if (when, title) in seen:
                continue
            seen.add((when, title))
            d, t = (when.split(" ") + ["00:00"])[:2]
            events.append({"d": d, "t": t, "title": title[:90],
                           "allday": t == "00:00",
                           "m": lens.get((when, title))})
    except Exception:
        pass

    blocks, loose = [], []
    for r in routines:
        m = _CLOCK.search(r["time"] or "")
        rota_days = [d for d in DAYS if any(v for v in (r["rota"].get(d) or []))]
        if m and rota_days:
            blocks.append({
                "days": rota_days,
                "start": f"{int(m.group(1)):02d}:{m.group(2)}",
                "end": f"{int(m.group(3)):02d}:{m.group(4)}",
                "name": r["name"]})
            continue
        if r["rota"]:
            continue                    # its week strip already tells the story
        d = due(r)
        note = r["days"] or (d[1] if d else "") or r["time"]
        loose.append({"name": r["name"], "note": note})

    pins = [{"t": h["t"], "name": h["name"]} for h in load_habits() if h["t"]]

    # Season days already slotted ride the grid too — free time has to be
    # judged against everything she has said yes to, not just the calendar.
    season = []
    try:
        with open(os.path.join(BRAIN, "season.md"), encoding="utf-8") as f:
            stext = f.read()
        for m in re.finditer(r"^- \[[ x]\] (.+)$", stext, re.M):
            pm = re.search(r"\(planned:\s*(\d{4}-\d{2}-\d{2})\)", m.group(1))
            if not pm or not any(d["iso"] == pm.group(1) for d in days):
                continue
            label = re.sub(r"\s*\((?:planned|with|when):[^)]*\)", "",
                           m.group(1)).strip()
            season.append({"d": pm.group(1), "title": label[:60]})
    except OSError:
        pass

    return {"days": days, "events": events, "blocks": blocks,
            "pins": pins, "loose": loose, "season": season,
            "sugg": suggest(routines, days, events, blocks)}


def _mins(t):
    h, m = t.split(":")
    return int(h) * 60 + int(m)


def _fmt(m):
    return f"{m // 60:02d}:{m % 60:02d}"


def suggest(routines, days, events, blocks):
    """Where the flexible routines could land this week.

    Free time is computed against the calendar (an event blocks its own
    length, or 90 minutes when the calendar did not give one), the fixed
    routines, and each suggestion
    already made. Evenings 17:30–21:30 are the working window, weekend
    mornings 09:00–12:00 the fallback; a fixed-evening day (volleyball)
    takes no suggestions at all. These are proposals, not bookings — locking
    one in means giving the routine real days, which is one sentence to
    Claude.
    """
    busy = {d["iso"]: [] for d in days}
    for e in events:
        if not e["allday"] and e["d"] in busy:
            t = _mins(e["t"])
            busy[e["d"]].append((t, t + (e.get("m") or 90)))
    dow2iso = {d["dow"]: d["iso"] for d in days}
    fixed_days = set()
    for b in blocks:
        fixed_days.update(b["days"])
        for dw in b["days"]:
            iso = dow2iso.get(dw)
            if iso:
                busy[iso].append((_mins(b["start"]), _mins(b["end"])))

    def gap(iso, lo, hi, need):
        cur = lo
        for s, e in sorted(busy[iso]):
            if s - cur >= need and cur + need <= hi:
                return cur
            cur = max(cur, e)
            if cur + need > hi:
                return None
        return cur if cur + need <= hi else None

    def slots_wanted(r):
        if r["every"]:
            d = due(r)
            return 1 if d and d[0] in ("due", "unlogged") else 0
        t = (r["days"] or "").lower()
        if "once" in t:
            return 1
        if "twice" in t:
            return 2
        m = re.search(r"\d+", t)
        return min(int(m.group()), 7) if m else 0

    def duration(r):
        t = (r["time"] or "").lower()
        m = re.search(r"(\d+)\s*h\s*(\d+)?", t)
        if m:
            return int(m.group(1)) * 60 + int(m.group(2) or 0)
        m = re.search(r"(\d+)\s*min", t)
        return int(m.group(1)) if m else 60

    out = []
    taken = set()                          # days already holding a suggestion
    for r in routines:
        if r["rota"] or _CLOCK.search(r["time"] or ""):
            continue                       # it already knows its days
        n, need = slots_wanted(r), duration(r)
        if not n:
            continue
        cands = []
        for d in days:
            if d["dow"] in fixed_days:
                continue
            g = gap(d["iso"], 17 * 60 + 30, 21 * 60 + 30, need)
            if g is None and d["dow"] in ("Sat", "Sun"):
                g = gap(d["iso"], 9 * 60, 12 * 60, need)
            if g is not None:
                cands.append((d["iso"], g))
        # One suggestion per day where the week allows it — three dashed
        # boxes stacked on one Thursday read as noise, not as a plan.
        fresh = [c for c in cands if c[0] not in taken]
        if len(fresh) >= n:
            cands = fresh
        if len(cands) > n:                 # spread across the week, not a clump
            idx = sorted({round(i * (len(cands) - 1) / max(n - 1, 1))
                          for i in range(n)})
            cands = [cands[i] for i in idx]
        for iso, g in cands[:n]:
            busy[iso].append((g, g + need))
            taken.add(iso)
            out.append({"d": iso, "start": _fmt(g), "end": _fmt(g + need),
                        "name": r["name"]})
    return out


# ── the page ─────────────────────────────────────────────────────────────

def _esc(s):
    return html.escape(str(s or ""), quote=True)


def _slot_part(r, slot):
    """The part of a routine's Time (and Days) that belongs to one slot.

    Under Morning, "~10 min morning, ~10 min night" is "~10 min" — the whole
    string in both columns read as a copy (28 Sep). A clause of Days that
    names the slot ("the night active rotates…") joins that slot only. A
    Time that names no slot at all belongs to every slot the routine has."""
    word = re.compile(r"\b" + slot + r"\b", re.I)
    any_slot = re.compile(r"\b(?:" + "|".join(SLOTS) + r")\b", re.I)
    parts = [p.strip() for p in re.split(r"[,;]", r["time"] or "") if p.strip()]
    if any(any_slot.search(p) for p in parts):
        bits = [re.sub(r"\s+", " ", word.sub("", p)).strip(" -—")
                for p in parts if word.search(p)]
    else:
        bits = [r["time"]] if r["time"] else []
    bits += [c.strip() for c in re.split(r"\s+[—–-]\s+|[;,]\s*", r["days"] or "")
             if c.strip() and word.search(c)]
    return " · ".join(b for b in bits if b)


_ISO = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")


def _day_first(html_text):
    """Dates her files spell 2026-09-14 show as "14 Sep" (the year only when
    it isn't this one). Text only — never inside a tag — and the file keeps
    its own spelling."""
    def one(m):
        try:
            d = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return m.group(0)
        s = f"{d.day} {DAY_MON[d.month - 1]}"
        return s if d.year == date.today().year else f"{s} {d.year}"
    return re.sub(r">([^<]+)<",
                  lambda m: ">" + _ISO.sub(one, m.group(1)) + "<", html_text)


def _slot_strip(routines):
    """The day as columns: which routine shows up in which part of it."""
    cols = []
    for slot in SLOTS:
        here = [r for r in routines if slot in r["when"]]
        if not here and slot in ("midday", "afternoon"):
            continue                       # only show quiet slots that exist
        chips = "".join(
            f'<a class="rchip" href="#r-{_esc(r["file"])}">{_esc(r["name"])}'
            + (f'<span>{_esc(_slot_part(r, slot))}</span>'
               if _slot_part(r, slot) else "")
            + "</a>"
            for r in here) or '<div class="rnone">nothing planned</div>'
        cols.append(f'<div class="rslot"><h3>{slot.title()}</h3>{chips}</div>')
    return '<div class="rstrip">' + "".join(cols) + "</div>"


def _week_strip(r, today):
    if not r["rota"]:
        return ""
    cells = []
    for d in DAYS:
        vals = [v for v in (r["rota"].get(d) or []) if v]
        first = vals[0] if vals else "—"
        on = ' class="on"' if d == today else ""
        cells.append(f"<div{on}><b>{_esc(d)}</b><span>{_esc(first)}</span></div>")
    return '<div class="rweek">' + "".join(cells) + "</div>"


def build():
    sys.path.insert(0, HERE)
    import build as B
    import chrome as CHROME

    cfg = {}
    try:
        with open(os.path.join(BRAIN, "config.json"), encoding="utf-8") as f:
            cfg = json.load(f)
    except (OSError, ValueError):
        pass

    routines = load()
    today = DAYS[date.today().weekday()]
    today_full = DAY_FULL[date.today().weekday()]

    # Today's card: what the day asks, one line per routine that says so.
    # Cadence routines appear only when they need her — due, or never filed.
    tlines = []
    for r in routines:
        vals = r["rota"].get(today) or []
        # name in its own column, each label quieter than its value — bold
        # label after bold name read "Skincare & beauty Face: Retinal" (28 Sep)
        pairs = [f'<span class="rtl">{_esc(lab)}:</span> {_esc(v)}'
                 for lab, v in zip(r["rota_labels"], vals) if v]
        if pairs:
            tlines.append(f'<div class="rtoday-line">'
                          f'<span class="rtn">{_esc(r["name"])}</span><span>'
                          + " &middot; ".join(pairs) + "</span></div>")
        d = due(r)
        if d and d[0] in ("due", "unlogged"):
            tlines.append(f'<div class="rtoday-line">'
                          f'<span class="rtn">{_esc(r["name"])}</span>'
                          f'<span>{_esc(d[1])}</span></div>')
    today_card = (
        '<section class="rtoday"><h2>' + _esc(today_full) + "</h2>"
        + ("".join(tlines) if tlines
           else '<div class="rnone">no rotation lands today</div>')
        + "</section>")

    cards = []
    for r in routines:
        d = due(r)
        cadence = ""
        if r["every"]:
            cadence = f"every {r['every']} days"
            if d:
                cadence += " · " + d[1]
        meta = " &middot; ".join(_esc(x) for x in
                                 [", ".join(r["when"]), r["time"], r["days"],
                                  cadence]
                                 if x)
        cards.append(
            f'<section class="rcard" id="r-{_esc(r["file"])}">'
            f'<h2>{_esc(r["name"])}</h2>'
            + (f'<div class="rmeta">{meta}</div>' if meta else "")
            + _week_strip(r, today)
            + '<details><summary>Open the whole routine</summary>'
            + '<div class="rdoc">' + _day_first(MD.render(r["body"]))
            + "</div></details>"
            + "</section>")

    empty = ('<section class="rcard"><h2>No routines yet</h2>'
             '<p class="rnone">Tell Claude the shape of one — when it '
             "happens, what it involves — and it lands here.</p></section>")

    page = TEMPLATE
    page = page.replace("__STYLE__",
                        (cfg.get("appearance", {}) or {}).get("style",
                                                              "workroom"))
    page = page.replace("__PALETTE__", B.palette_css(cfg))
    page = page.replace("__HEADER__", CHROME.header_html(
        current="routine", owner=cfg.get("owner", "")))
    page = page.replace("__NAVCSS__", CHROME.NAV_CSS + CHROME.HEADER_CSS)
    page = page.replace("__ASK__", CHROME.ask_block())
    page = page.replace("__TODAY__", today_card)
    page = page.replace("__STRIP__", _slot_strip(routines) if routines else "")
    page = page.replace("__CARDS__", "".join(cards) if cards else empty)
    page = page.replace("__WEEK__",
                        MD.json_for_script(week_data(routines), ensure_ascii=False))

    from shutil import which
    node = which("node")
    if node:
        import subprocess as _sp
        import tempfile as _tf
        for js in re.findall(r"<script>(.*?)</script>", page, re.S):
            with _tf.NamedTemporaryFile("w", suffix=".js",
                                        delete=False, encoding="utf-8") as tmp:
                tmp.write(js)
            try:
                r = _sp.run([node, "--check", tmp.name],
                            capture_output=True, text=True, timeout=20)
                if r.returncode != 0:
                    raise SystemExit("REFUSING to write routines.html — its "
                                     "script does not parse:\n"
                                     + r.stderr.strip()[:600])
            finally:
                os.unlink(tmp.name)

    with open(OUT, "w", encoding="utf-8") as f:
        f.write(page)
    return OUT


TEMPLATE = r"""<!doctype html>
<html lang="en" data-style="__STYLE__"><head>
<script>try{var _bs=localStorage.getItem('brain-style');
if(_bs)document.documentElement.setAttribute('data-style',_bs);}catch(e){}</script>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>Routine &mdash; the brain</title>
<link rel="icon" href="logo-192.png?v=5" type="image/png">
<link rel="apple-touch-icon" href="logo-180.png?v=5">
<link rel="stylesheet" href="appearance.css">
<style>
__PALETTE__
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--paper);color:var(--ink);
  font:400 var(--t-base)/1.55 var(--sans)}
a{color:var(--ink)}
__NAVCSS__
/* as wide as the Kitchen: a week with clashes needs the room to lay them
   side by side. The bottom padding keeps the floating button off the
   last card. */
.rwrap{max-width:1060px;margin:0 auto;
  padding:20px 20px calc(100px + env(safe-area-inset-bottom,0px))}
.rwrap>h1{font:700 clamp(26px,4vw,34px)/1.15 var(--serif,'Literata',Georgia,serif);
  margin:14px 0 4px}
.rlede{color:var(--dim);margin:0 0 22px;font-size:14.5px;max-width:70ch}
.rtoday{border:1px solid var(--line);border-radius:14px;background:var(--surface);
  padding:16px 18px;margin:0 0 18px}
.rtoday h2{margin:0 0 8px;font:600 15px/1.2 var(--serif,'Literata',Georgia,serif)}
.rtoday-line{font-size:14px;margin:4px 0;display:grid;
  grid-template-columns:12em 1fr;gap:2px 16px;align-items:baseline}
.rtoday-line>.rtn{font-weight:600}
.rtl{color:var(--dim)}
@media(max-width:520px){
  .rtoday-line{grid-template-columns:1fr;gap:0;margin:0 0 8px}
}
.rstrip{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));
  gap:10px;margin:0 0 26px}
.rslot{border:1px solid var(--line);border-radius:12px;padding:11px 13px;
  background:var(--paper)}
.rslot h3{margin:0 0 7px;font-size:10.5px;font-weight:700;letter-spacing:.09em;
  text-transform:uppercase;color:var(--faint)}
.rchip{display:block;font-size:13.5px;font-weight:600;text-decoration:none;
  padding:6px 9px;border:1px solid var(--line2);border-radius:9px;
  background:var(--surface);margin:0 0 6px}
.rchip:hover{border-color:var(--dim)}
.rchip span{display:block;font-weight:400;font-size:11.5px;color:var(--faint)}
.rnone{color:var(--faint);font-size:12.5px}
.rcard{border:1px solid var(--line);border-radius:14px;padding:18px 20px;
  margin:0 0 16px;background:var(--paper)}
.rcard>h2{margin:0 0 3px;font:600 19px/1.2 var(--serif,'Literata',Georgia,serif)}
.rmeta{color:var(--dim);font-size:13px;margin:0 0 12px}
.rweek{display:grid;grid-template-columns:repeat(7,1fr);gap:5px;margin:0 0 14px}
.rweek>div{border:1px solid var(--line);border-radius:9px;padding:7px 4px 8px;
  text-align:center;background:var(--surface)}
.rweek>div.on{border-color:var(--green,var(--ink));background:var(--paper);
  box-shadow:0 1px 4px rgba(0,0,0,.07)}
.rweek b{display:block;font-size:10.5px;letter-spacing:.06em;
  text-transform:uppercase;color:var(--faint);margin-bottom:2px}
.rweek>div.on b{color:var(--green,var(--ink))}
.rweek span{font-size:11.5px;line-height:1.25;display:block}
/* The week grid: her real calendar plus the fixed routines, hour by hour.
   Zoomed out it is the schedule; zoomed in the habits and the loose load
   appear too. */
.rzoomrow{display:flex;gap:8px;align-items:baseline;margin:0 0 10px}
.rzoomrow h2{margin:0;font:600 17px/1.2 var(--serif,'Literata',Georgia,serif);
  flex:1}
.rzoomrow button{font:inherit;font-size:12px;font-weight:600;cursor:pointer;
  border:1px solid var(--line2);background:var(--paper);color:var(--dim);
  border-radius:999px;padding:4px 12px}
.rzoomrow button.on{background:var(--green,var(--ink));color:var(--paper);
  border-color:transparent}
.rloose{display:flex;flex-wrap:wrap;gap:6px;margin:0 0 10px}
.rloose[hidden]{display:none}
.rloose span{font-size:12px;border:1px dashed var(--line2);border-radius:999px;
  padding:4px 11px;color:var(--dim);background:var(--surface)}
.rloose b{font-weight:600;color:var(--ink)}
.rgridwrap{overflow-x:auto;margin:0 0 26px}
.rgrid{display:grid;grid-template-columns:44px repeat(7,minmax(96px,1fr));
  gap:0 6px;min-width:760px}
.rgrid .rdayh{font-size:11px;font-weight:700;letter-spacing:.05em;
  text-transform:uppercase;color:var(--faint);text-align:center;
  padding:0 0 6px;white-space:nowrap}
.rgrid .rdayh.today{color:var(--green,var(--ink))}
.rallday{min-height:0;margin:0 0 4px}
.rallday span{display:block;font-size:10.5px;line-height:1.3;
  border:1px solid var(--line);border-radius:6px;padding:2px 5px;
  margin:0 0 3px;background:var(--surface);color:var(--dim);
  overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.rcol{position:relative;border:1px solid var(--line);border-radius:10px;
  background:var(--paper)}
.rcol.today{border-color:var(--green,var(--ink))}
.rgut{position:relative}
.rgut i{position:absolute;right:8px;font-style:normal;font-size:10px;
  color:var(--faint);transform:translateY(-50%)}
.rhline{position:absolute;left:0;right:0;border-top:1px solid var(--line);
  opacity:.45}
.rev{position:absolute;left:3px;right:3px;box-sizing:border-box;border-radius:8px;overflow:hidden;
  font-size:11px;line-height:1.3;padding:3px 7px;
  background:var(--paper);border:1px solid var(--line2);
  border-left:3px solid var(--dim);
  box-shadow:0 1px 3px rgba(0,0,0,.08)}
.rev i{display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;
  overflow:hidden;font-style:normal}
/* a one-line box keeps its title on the line and cuts it there — wrapping
   left "15:40…" with no title at all */
.rev i.r1{display:block;white-space:nowrap;text-overflow:ellipsis}
.rev.rb{background:color-mix(in oklch,var(--green,var(--ink)) 14%,var(--paper));
  border-left-color:var(--green,var(--ink));border-color:transparent;
  font-weight:600}
.rev.rs{background:var(--paper);border:1.5px dashed var(--dim);border-radius:9px;
  color:var(--dim);box-shadow:none;font-weight:500}
.rev.rs b{font-weight:700}
/* side by side: the padding tightens; the day column widens instead of the
   text shrinking (see the lane floor in render) */
.rev.rsplit{padding:3px 5px}
.rcol.wkend{background:var(--surface)}
.rallday span.rsn{border-style:dashed;
  border-color:var(--green,var(--ink));color:var(--ink)}
.rlegend{font-size:11.5px;color:var(--faint);margin:7px 2px 0}
.rpin{position:absolute;left:3px;right:3px;font-size:10px;color:var(--faint);
  border-top:1px dotted var(--dim);padding:1px 4px 0;white-space:nowrap;
  overflow:hidden;text-overflow:ellipsis}
.rgrid[data-z="sched"] .rpin{display:none}
.rcard details>summary{cursor:pointer;font-size:13px;font-weight:600;
  color:var(--green,var(--ink))}
.rcard details>summary:hover{text-decoration:underline}
.rdoc{margin-top:14px;font-size:14.5px;line-height:1.6}
.rdoc h2{font:600 17px/1.25 var(--serif,'Literata',Georgia,serif);margin:20px 0 8px}
.rdoc h3{font:600 14.5px/1.25 var(--sans);margin:16px 0 6px}
.rdoc p{margin:0 0 10px}
.rdoc>p,.rdoc>ul,.rdoc>ol{max-width:72ch}
.rdoc ul,.rdoc ol{margin:0 0 10px;padding-left:22px}
.rdoc li{margin:0 0 4px}
.rdoc hr{border:0;border-top:1px solid var(--line);margin:16px 0}
.rdoc .tw{overflow-x:auto;margin:0 0 12px}
.rdoc table{border-collapse:collapse;font-size:13.5px}
.rdoc th,.rdoc td{border:1px solid var(--line);padding:6px 10px;
  text-align:left;vertical-align:top}
.rdoc th{background:var(--surface)}
@media(max-width:640px){
  .rweek span{font-size:10px}
}
/* A phone (28 Sep): seven to a row left each day about 33px, so the words
   were 10px and a long one ("Uriage mask, thin layer") still pushed the
   page 3px sideways at 360. Four to a row, at a size you can read. */
@media(max-width:520px){
  .rweek{grid-template-columns:repeat(4,minmax(0,1fr))}
  .rweek span{font-size:12px}
}
</style></head><body>
__HEADER__
<div class="rwrap">
<h1>Routine</h1>
<p class="rlede">What your days hold, so the plan works around it.
To change any of it, tell Claude and it changes here.</p>
__TODAY__
<div class="rzoomrow"><h2>The week</h2>
  <button data-z="sched">Schedule</button>
  <button data-z="all">Everything</button>
</div>
<div class="rloose" id="rloose" hidden></div>
<div class="rgridwrap"><div class="rgrid" id="rgrid"></div>
<div class="rlegend" id="rlegend" hidden>Solid is booked; dashed is a
suggestion for the flexible routines &mdash; tell Claude to lock one in or
move it.</div></div>
__STRIP__
__CARDS__
</div>
__ASK__
<script>
(function(){
var W = __WEEK__;
var grid = document.getElementById('rgrid'),
    loose = document.getElementById('rloose');
var H0 = 7, H1 = 23.5;              // recomputed each render to fit the week
var HH = 44;                        // px per hour, set by the zoom
var MINPX = 26;                     // the shortest box that still holds a line
function mins(t){
  var p = t.split(':');
  return (+p[0]) * 60 + (+p[1]);
}
// minutes since midnight → px down a day column
function ypx(m){
  m = Math.min(Math.max(m, H0 * 60), H1 * 60);
  return (m - H0 * 60) / 60 * HH;
}
function hm(m){ return Math.floor(m / 60) + ':' + ('0' + m % 60).slice(-2); }
// Everything timed on one day — calendar events, fixed routines,
// suggestions. An event is as long as the calendar says; one it gave no
// length gets an hour (28 Sep: every box was the same height, so a
// 90-minute class looked like a coffee).
function dayItems(d){
  var items = [], groups = [];
  W.events.forEach(function(e){
    if(e.d !== d.iso || e.allday) return;
    var known = typeof e.m === 'number' && e.m > 0;
    var s0 = mins(e.t), e0 = s0 + (known ? e.m : typeof e.m === 'number' ? 0 : 60);
    // A class arrives twice — "Scale up" and "Scale up - PROF - S210 -
    // EN": one box, and the longer twin's details go in the tooltip.
    var g = groups.filter(function(x){
      return x.s === s0 && x.titles.some(function(y){
        return y.indexOf(e.title) === 0 || e.title.indexOf(y) === 0; });
    })[0];
    if(g){ g.titles.push(e.title); g.e = Math.max(g.e, e0); g.known = g.known || known; }
    else groups.push({s: s0, e: e0, known: known, titles: [e.title]});
  });
  groups.forEach(function(g){
    var ts = g.titles;
    var brief = ts.reduce(function(a, b){ return b.length < a.length ? b : a; });
    var full = ts.filter(function(x){
      return !ts.some(function(y){ return y !== x && y.indexOf(x) === 0; }); });
    var at = hm(g.s), span = g.known ? at + '–' + hm(g.e) : at;
    items.push({s: g.s, e: g.e, cls: 'rev', tip: span + ' ' + full.join(' + '),
      html1: '<b>' + at + '</b> ' + esc(brief),
      html2: '<b>' + span + '</b> ' + esc(brief)});
  });
  W.blocks.forEach(function(b){
    if(b.days.indexOf(d.dow) < 0) return;
    var span = b.start + '–' + b.end;
    items.push({s: mins(b.start), e: mins(b.end), cls: 'rev rb',
      tip: b.name + ' ' + span, html1: esc(b.name) + ' ' + span});
  });
  (W.sugg || []).forEach(function(sg){
    if(sg.d !== d.iso) return;
    var span = sg.start + '–' + sg.end;
    items.push({s: mins(sg.start), e: mins(sg.end), cls: 'rev rs',
      tip: sg.name + ' ' + span + ' — a suggestion; tell Claude to lock it in or move it',
      html1: '<b>' + esc(sg.name) + '?</b> ' + span});
  });
  return items;
}
// Clusters of things that touch ON SCREEN (a 20-minute meeting is drawn
// taller than 20 minutes), then the first free lane in each. Returns the
// most lanes any moment of the day needs; the day's column is sized from
// it, so a clash gets room instead of shrinking to "HO…" (28 Sep).
function lay(items){
  var minMin = MINPX / HH * 60;
  items.sort(function(x, y){ return x.s - y.s || y.e - x.e; });
  var cluster = [], cEnd = -1, most = 1;
  function place(cl){
    var ends = [];
    cl.forEach(function(it){
      var k = 0;
      while(k < ends.length && ends[k] > it.s) k++;
      ends[k] = it.ve; it.lane = k;
    });
    cl.forEach(function(it){ it.lanes = ends.length; });
    most = Math.max(most, ends.length);
  }
  items.forEach(function(it){
    it.ve = Math.max(it.e, it.s + minMin);
    if(cluster.length && it.s >= cEnd){ place(cluster); cluster = []; }
    cluster.push(it); cEnd = Math.max(cEnd, it.ve);
  });
  if(cluster.length) place(cluster);
  return most;
}
var narrowQ = window.matchMedia ? window.matchMedia('(max-width:639px)') : null;
// Quotes too: calendar titles land in title="…", and an invite's title is
// written by whoever sent it.
function esc(s){ return String(s == null ? '' : s)
  .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
  .replace(/"/g,'&quot;').replace(/'/g,'&#39;'); }
function zoom(){
  var z = 'sched';
  try { z = localStorage.getItem('rzoom') || 'sched'; } catch(e){}
  return z;
}
function render(){
  var z = zoom();
  grid.dataset.z = z;
  // Size the grid to the hours the week actually uses (plus an hour of
  // air each side) — a 07:00–23:30 frame around an evening-only week
  // crushed everything legible into the bottom sixth.
  // Tall enough that an hour-long meeting holds two lines of its title.
  HH = z === 'all' ? 56 : 44;
  var byDay = W.days.map(dayItems);
  var lo = 24 * 60, hi = 0;
  function see(s, e){ lo = Math.min(lo, s); hi = Math.max(hi, e); }
  byDay.forEach(function(items){
    items.forEach(function(it){ see(it.s, Math.max(it.e, it.s + 30)); }); });
  if(z === 'all') W.pins.forEach(function(p){ see(mins(p.t), mins(p.t) + 30); });
  if(hi <= lo){ lo = 9 * 60; hi = 18 * 60; }
  H0 = Math.max(0, Math.floor(lo / 60) - 1);
  H1 = Math.min(24, Math.ceil(hi / 60) + 1);
  if(H1 - H0 < 6) H1 = Math.min(24, H0 + 6);
  var colh = (H1 - H0) * HH;
  // Each day is as wide as its clashes need: a floor per lane, and the
  // spare width shared out a little in favour of the busy days. Too wide
  // for the screen, and the week scrolls sideways (a phone shows ~3 days).
  var lanes = byDay.map(lay);
  var narrow = !!(narrowQ && narrowQ.matches);
  var LANE = narrow ? 72 : 84, DAYMIN = narrow ? 88 : 96;
  var floors = lanes.map(function(l){ return Math.max(DAYMIN, l * LANE); });
  grid.style.gridTemplateColumns = '44px ' + lanes.map(function(l, i){
    return 'minmax(' + floors[i] + 'px,' + (1 + .6 * (l - 1)) + 'fr)';
  }).join(' ');
  grid.style.minWidth = (44 + 7 * 6
    + floors.reduce(function(a, b){ return a + b; }, 0)) + 'px';
  document.querySelectorAll('.rzoomrow button').forEach(function(b){
    b.classList.toggle('on', b.dataset.z === z);
  });
  // The flexible load only appears zoomed in — the schedule view is what
  // the week is committed to; Everything is what it also has to hold.
  loose.hidden = z !== 'all' || !W.loose.length;
  loose.innerHTML = W.loose.map(function(l){
    return '<span><b>' + esc(l.name) + '</b>'
      + (l.note ? ' — ' + esc(l.note) : '') + '</span>';
  }).join('');

  var out = ['<div></div>'];
  W.days.forEach(function(d){
    out.push('<div class="rdayh' + (d.label.indexOf('Today') === 0 ? ' today' : '')
      + '">' + esc(d.label) + '</div>');
  });
  // all-day badges and planned season days ride above the timed columns
  out.push('<div></div>');
  W.days.forEach(function(d){
    var ad = W.events.filter(function(e){ return e.d === d.iso && e.allday; })
      .map(function(e){
        return '<span title="' + esc(e.title) + '">' + esc(e.title) + '</span>';
      });
    (W.season || []).forEach(function(s){
      if(s.d === d.iso)
        ad.push('<span class="rsn" title="' + esc(s.title) + '">&#10022; '
          + esc(s.title) + '</span>');
    });
    out.push('<div class="rallday">' + ad.join('') + '</div>');
  });
  // the hour gutter
  var gut = '<div class="rgut" style="height:' + colh + 'px">';
  for(var h = H0; h <= H1 - .5; h++)
    gut += '<i style="top:' + ypx(h * 60) + 'px">' + h + '</i>';
  out.push(gut + '</div>');
  // habits sharing a clock time merge into one pin — two labels on the
  // same line print through each other
  var pinsByT = {};
  W.pins.forEach(function(p){ (pinsByT[p.t] = pinsByT[p.t] || []).push(p.name); });
  W.days.forEach(function(d, di){
    var wk = d.dow === 'Sat' || d.dow === 'Sun';
    var c = '<div class="rcol' + (d.label.indexOf('Today') === 0 ? ' today' : '')
      + (wk ? ' wkend' : '') + '" style="height:' + colh + 'px">';
    for(var h = H0 + 1; h < H1; h++)
      c += '<div class="rhline" style="top:' + ypx(h * 60) + 'px"></div>';
    // The way a calendar app draws it: each box from its start to its end,
    // clashes side by side in their lanes, the whole title in the tooltip.
    // A box too short for its words shows the start and as much title as
    // fits; with room for two lines it shows start–end.
    byDay[di].forEach(function(it){
      var top = ypx(it.s), px = Math.max(ypx(it.e) - top, MINPX);
      var w = 100 / it.lanes;
      var lines = Math.max(1, Math.floor((px - 10) / 14.3));
      c += '<div class="' + it.cls + (it.lanes > 1 ? ' rsplit' : '')
        + '" style="top:' + (top + 1) + 'px;height:' + (px - 2) + 'px;left:calc('
        + (it.lane * w) + '% + 2px);width:calc(' + w + '% - 4px);right:auto"'
        + ' title="' + esc(it.tip) + '"><i' + (lines < 2 ? ' class="r1"' : '')
        + ' style="-webkit-line-clamp:' + lines + ';line-clamp:' + lines + '">'
        + (lines >= 2 && it.html2 ? it.html2 : it.html1) + '</i></div>';
    });
    // habits at their hour — the zoomed-in layer
    Object.keys(pinsByT).forEach(function(t){
      c += '<div class="rpin" style="top:' + ypx(mins(t)) + 'px">'
        + t + ' ' + esc(pinsByT[t].join(' · ')) + '</div>';
    });
    c += '</div>';
    out.push(c);
  });
  grid.innerHTML = out.join('');
  var leg = document.getElementById('rlegend');
  if(leg) leg.hidden = !(W.sugg || []).length;
}
document.querySelectorAll('.rzoomrow button').forEach(function(b){
  b.onclick = function(){
    try { localStorage.setItem('rzoom', b.dataset.z); } catch(e){}
    render();
  };
});
// the lane floor is smaller on a phone, so crossing that width redraws
if(narrowQ && narrowQ.addEventListener) narrowQ.addEventListener('change', render);
render();
})();
</script>
</body></html>
"""


if __name__ == "__main__":
    if "--today" in sys.argv:
        rs = load()
        for r in rs:
            print(today_line(r))
        try:
            w = week_data(rs)
            ts = [s for s in w["sugg"] if s["d"] == date.today().isoformat()]
            if ts:
                print("Would fit today: " + "; ".join(
                    f"{s['name']} {s['start']}–{s['end']}" for s in ts))
        except Exception:
            pass
    else:
        print("Built", build())

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
        return ("unlogged", "no session filed yet — say when you last did it")
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
        seen = set()
        for when, title in calendar_read.events(7):
            if re.match(r"\s*canceled", title, re.I):
                continue
            if (when, title) in seen:
                continue
            seen.add((when, title))
            d, t = (when.split(" ") + ["00:00"])[:2]
            events.append({"d": d, "t": t, "title": title[:90],
                           "allday": t == "00:00"})
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

    Free time is computed against the calendar (an event blocks 90 minutes —
    starts are all it gives us), the fixed routines, and each suggestion
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
            busy[e["d"]].append((t, t + 90))
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


def _slot_strip(routines):
    """The day as columns: which routine shows up in which part of it."""
    cols = []
    for slot in SLOTS:
        here = [r for r in routines if slot in r["when"]]
        if not here and slot in ("midday", "afternoon"):
            continue                       # only show quiet slots that exist
        chips = "".join(
            f'<a class="rchip" href="#r-{_esc(r["file"])}">{_esc(r["name"])}'
            + (f'<span>{_esc(r["time"])}</span>' if r["time"] else "")
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
        pairs = [f"<b>{_esc(lab)}:</b> {_esc(v)}"
                 for lab, v in zip(r["rota_labels"], vals) if v]
        if pairs:
            tlines.append(f'<div class="rtoday-line">'
                          f'<span>{_esc(r["name"])}</span>'
                          + " &middot; ".join(pairs) + "</div>")
        d = due(r)
        if d and d[0] in ("due", "unlogged"):
            tlines.append(f'<div class="rtoday-line">'
                          f'<span>{_esc(r["name"])}</span>{_esc(d[1])}</div>')
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
                cadence += " — " + d[1]
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
            + '<div class="rdoc">' + MD.render(r["body"]) + "</div></details>"
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
                        json.dumps(week_data(routines), ensure_ascii=False))

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
.rwrap{max-width:900px;margin:0 auto;padding:20px 20px 90px}
.rwrap>h1{font:700 clamp(26px,4vw,34px)/1.15 var(--serif,'Literata',Georgia,serif);
  margin:14px 0 4px}
.rlede{color:var(--dim);margin:0 0 22px;font-size:14.5px}
.rtoday{border:1px solid var(--line);border-radius:14px;background:var(--surface);
  padding:16px 18px;margin:0 0 18px}
.rtoday h2{margin:0 0 8px;font:600 15px/1.2 var(--serif,'Literata',Georgia,serif)}
.rtoday-line{font-size:14px;margin:3px 0}
.rtoday-line>span{font-weight:600;margin-right:8px}
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
.rev{position:absolute;left:3px;right:3px;border-radius:8px;overflow:hidden;
  font-size:11px;line-height:1.3;padding:3px 7px;
  background:var(--paper);border:1px solid var(--line2);
  border-left:3px solid var(--dim);
  box-shadow:0 1px 3px rgba(0,0,0,.08)}
.rev i{display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;
  overflow:hidden;font-style:normal}
.rev.rb{background:color-mix(in oklch,var(--green,var(--ink)) 14%,var(--paper));
  border-left-color:var(--green,var(--ink));border-color:transparent;
  font-weight:600}
.rev.rs{background:none;border:1.5px dashed var(--dim);border-radius:9px;
  color:var(--dim);box-shadow:none;font-weight:500}
.rev.rs b{font-weight:700}
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
</style></head><body>
__HEADER__
<div class="rwrap">
<h1>Routine</h1>
<p class="rlede">What your days hold, so the plan works around it.
Change any of it by telling Claude &mdash; this page follows the files.</p>
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
var H0 = 7, H1 = 23.5;              // the grid runs 07:00 to 23:30
function mins(t){
  var p = t.split(':');
  return (+p[0]) * 60 + (+p[1]);
}
function pct(t){
  var m = Math.min(Math.max(mins(t), H0 * 60), H1 * 60);
  return ((m - H0 * 60) / ((H1 - H0) * 60) * 100) + '%';
}
function esc(s){ return String(s == null ? '' : s)
  .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }
function zoom(){
  var z = 'sched';
  try { z = localStorage.getItem('rzoom') || 'sched'; } catch(e){}
  return z;
}
function render(){
  var z = zoom();
  grid.dataset.z = z;
  var hh = z === 'all' ? 44 : 26;              // px per hour
  var colh = (H1 - H0) * hh;
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
    gut += '<i style="top:' + pct((h < 10 ? '0' : '') + h + ':00') + '">'
        + h + '</i>';
  out.push(gut + '</div>');
  var evH = Math.max(hh, 34);              // an event block always fits 2 lines
  W.days.forEach(function(d){
    var wk = d.dow === 'Sat' || d.dow === 'Sun';
    var c = '<div class="rcol' + (d.label.indexOf('Today') === 0 ? ' today' : '')
      + (wk ? ' wkend' : '') + '" style="height:' + colh + 'px">';
    for(var h = H0 + 1; h < H1; h++)
      c += '<div class="rhline" style="top:' + pct((h < 10 ? '0' : '') + h + ':00') + '"></div>';
    // calendar events: same-time ones merge into one block; blocks that
    // land within an hour of each other cascade right so both stay legible
    var evs = W.events.filter(function(e){ return e.d === d.iso && !e.allday; });
    var byT = {};
    evs.forEach(function(e){ (byT[e.t] = byT[e.t] || []).push(e.title); });
    var times = Object.keys(byT).sort();
    times.forEach(function(t, i){
      var lane = 0;
      for(var k = i - 1; k >= 0; k--)
        if(mins(t) - mins(times[k]) < 60) lane++;
      var left = Math.min(lane * 14, 42);
      c += '<div class="rev" style="top:' + pct(t) + ';height:' + evH
        + 'px;left:' + (3 + left) + 'px;z-index:' + (2 + lane)
        + '" title="' + esc(byT[t].join(' + ')) + '"><i><b>'
        + t.replace(/^0/, '') + '</b> ' + esc(byT[t].join(' · ')) + '</i></div>';
    });
    // fixed routines (volleyball): real start and end
    W.blocks.forEach(function(b){
      if(b.days.indexOf(d.dow) < 0) return;
      var px = (mins(b.end) - mins(b.start)) / 60 * hh;
      c += '<div class="rev rb" style="top:' + pct(b.start) + ';height:'
        + Math.max(px, 30) + 'px">' + esc(b.name) + ' ' + b.start + '–' + b.end
        + '</div>';
    });
    // the suggestions: where the flexible routines would fit this week
    (W.sugg || []).forEach(function(s){
      if(s.d !== d.iso) return;
      var px = (mins(s.end) - mins(s.start)) / 60 * hh;
      c += '<div class="rev rs" style="top:' + pct(s.start) + ';height:'
        + Math.max(px, 30) + 'px" title="A suggestion — tell Claude to lock '
        + 'it in or move it"><i><b>' + esc(s.name) + '?</b> ' + s.start + '–'
        + s.end + '</i></div>';
    });
    // habits at their hour — the zoomed-in layer
    W.pins.forEach(function(p){
      c += '<div class="rpin" style="top:' + pct(p.t) + '">'
        + p.t + ' ' + esc(p.name) + '</div>';
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

#!/usr/bin/env python3
"""Build brain/proto.html — THE DESK: the redesign's home screen, live.

    python3 brain/tools/proto.py

GENERATED, and a prototype on purpose: it runs beside the real pages at
/proto.html so the redesign can be judged by living in it. Real data, real
ticks, the real queue behind the bar. See REDESIGN-DESIGN.md.

This revision, from the owner's screenshots: the loved today-box frames the
plan again (title, narrative, mascot mood); ticked items leave and the list
refills from a ranked bench instead of lying around struck-through; habits
are labelled pills, not mystery dots; chips wrap instead of truncating;
"Claude finished" explains itself with cleaned titles; action links look
like buttons; and everything cross-links to its room.
"""

import html
import json
import os
import re
import subprocess
import sys
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import md as MD        # noqa: E402
import model as M      # noqa: E402
import build as B      # noqa: E402  (palette + queue items)
import talk as K       # noqa: E402  (the bar's mic)

BRAIN = M.BRAIN
OUT = os.path.join(BRAIN, "proto.html")


def e(s):
    return html.escape(str(s), quote=True)


# The same suffix-stripping the tick writer does, so keys match.
_UNTIL = re.compile(r"\s*\(waiting until \d{4}-\d{2}-\d{2}\)\s*$")
_DROPPED = re.compile(r"\s*\(dropped \d{4}-\d{2}-\d{2}\)\s*$")
_DUE = re.compile(r"\s*\(due ([^)]+)\)")
_EST = re.compile(r"\s*~\s*(?:\d+h\d*|\d+m)\b", re.I)


def bare(text):
    text = text.split("\n")[0]
    text = _UNTIL.sub("", text)
    text = _DROPPED.sub("", text)
    m = _DUE.search(text)
    if m and M.parse_due(m.group(1)):
        text = _DUE.sub("", text, count=1)
    text = _EST.sub("", text)
    return re.sub(r"\s*\(urgent\)", "", text, flags=re.I).strip()


def today_file():
    try:
        with open(os.path.join(BRAIN, "today.md"), encoding="utf-8") as f:
            return f.read()
    except OSError:
        return ""


def plan_sections(text):
    """The three + the chases from today.md, keyed for ticking. Display
    splits a line at its em dash: the act big, the coaching small."""
    def block(title):
        m = re.search(rf"^## {title}\s*$(.*?)(?=^## |\Z)", text, re.M | re.S)
        return m.group(1) if m else ""

    def tasks(chunk):
        out = []
        for m in re.finditer(r"^- \[([ xX])\] (.*(?:\n(?![-#]).*)*)",
                             chunk, re.M):
            first = " ".join(m.group(2).split())
            title, _, sub = first.partition(" — ")
            out.append({"done": m.group(1) != " ", "t": title.strip(),
                        "sub": sub.strip(), "k": MD.taskkey(bare(first))})
        return out

    return tasks(block("Do these three")), tasks(block("Two-minute chases"))


def today_header(text):
    """The title and narrative intro — the today-box voice the owner likes."""
    m = re.search(r"^# (.+)$", text, re.M)
    if not m:
        return "Today", ""
    rest = text[m.end():]
    stop = rest.find("\n## ")
    intro = " ".join(rest[:stop if stop >= 0 else len(rest)].split())
    return m.group(1).strip(), intro


def clean_title(s):
    """Queue titles are raw asks — strip the machinery so the tray reads."""
    s = re.sub(r"^(start this( task)? for me|from the desk[^:]*|daily update"
               r"|about the (workstream|project)[^:]*|follow-up on[^:]*)"
               r"[:.]?\s*", "", s.strip(), flags=re.I)
    s = s.strip(" \"'“”‘’")
    if not s:
        return "A finished ask"
    return (s[0].upper() + s[1:])[:70]


def ws_room_map(config):
    """workstream name -> room slug, from the rooms config."""
    out = {}
    for wing in ((config.get("rooms") or {}).get("wings") or []):
        for room in (wing.get("rooms") or []):
            sl = room.get("slug") or M.room_slug(room.get("name", ""))
            for wsn in (room.get("ws") or []):
                out[wsn] = sl
    return out


def build():
    config = M.load_config()
    items = M.load(cfg=config)
    b = M.briefing(items, config)
    people = M.load_people()
    habits = M.load_habits()
    qw = M.quick_wins(items)
    q = B.queue_items()
    today = date.today()

    tmd = today_file()
    three, chases = plan_sections(tmd)
    ttitle, tintro = today_header(tmd)
    chases = [c for c in chases if not c["done"]]
    plan_keys = {t["k"] for t in three} | {t["k"] for t in chases}

    # quick sweep: quick wins not already in the plan
    chips = []
    for w in qw:
        k = MD.taskkey(w["t"]["text"])
        if k in plan_keys:
            continue
        mins = M.est_to_minutes(w["t"]["est"]) if w["t"].get("est") else None
        chips.append({"t": w["t"]["text"], "k": k, "ws": w["w"]["name"],
                      "mins": mins, "monday": w["monday"],
                      "urgent": bool(w["t"].get("urgent")),
                      "why": ("you marked it urgent" if w["t"].get("urgent")
                              else "due today" if w["t"].get("due_days") == 0
                              else f"due in {w['t']['due_days']}d"
                              if w["t"].get("due_days") is not None
                              else "quick, and its project is pressed")})

    # the bench: ranked open tasks not on the desk — they refill the plan
    # as things get ticked, so finishing work reveals work. The plan lines
    # are reworded copies of tasks, so exclusion is by token overlap too,
    # not just by key — "bedroom floors" in the plan covers the ws task.
    raw_plan = " ".join(t["t"] + " " + t["sub"]
                        for t in three + chases).lower()
    plan_toks = {x.rstrip("s") for x in re.split(r"[^a-z0-9]+", raw_plan)
                 if len(x) >= 5}
    def reason(w, t, rank):
        bits = []
        if t.get("urgent"):
            bits.append("you marked it urgent")
        elif t.get("overdue"):
            bits.append(f"{abs(t['due_days'])}d past its date")
        elif t.get("due_days") is not None:
            bits.append("due today" if t["due_days"] == 0
                        else f"due in {t['due_days']}d")
        if w["overdue"]:
            bits.append("its project is past a date")
        elif w.get("goal_overdue"):
            bits.append("a goal there slipped")
        elif w["chase"]:
            bits.append(f"waiting on {w['ball_who'] or 'someone'} "
                        f"{w['days_waiting']}d")
        elif w.get("task_urgent") and not t.get("urgent"):
            bits.append("that project is shouting")
        if not bits:
            bits.append(f"#{rank} on the plate right now")
        return f"from {w['name']} · " + ", ".join(bits[:2])

    bench, used = [], set(plan_keys) | {c["k"] for c in chips}
    for rank, w in enumerate(items, 1):
        if not w["live"]:
            continue
        for t in w["tasks"]:
            if t["done"] or t.get("parked") or t.get("dropped"):
                continue
            k = MD.taskkey(t["text"])
            if k in used:
                continue
            used.add(k)
            toks = [x.rstrip("s") for x in
                    re.split(r"[^a-z0-9]+", t["text"].lower())
                    if len(x) >= 5]
            if toks and sum(1 for x in toks if x in plan_toks) >= 2:
                continue
            bench.append({"t": t["text"], "k": k, "ws": w["name"],
                          "why": reason(w, t, rank)})
        if len(bench) >= 8:
            break

    # the plan's slots: undone three, topped up from the bench — a done
    # item does not lie around struck through, the list repopulates
    slots = [{"t": t["t"], "sub": t["sub"], "k": t["k"], "src": "today.md"}
             for t in three if not t["done"]]
    bi = 0
    while len(slots) < 3 and bi < len(bench):
        nb = bench[bi]
        bi += 1
        title, _, sub = nb["t"].partition(" — ")
        slots.append({"t": title.strip(),
                      "sub": (sub.strip() + " · " if sub.strip() else "")
                             + nb["why"],
                      "k": nb["k"], "src": "workstreams.md",
                      "next": True, "ws": nb["ws"]})
    bench = bench[bi:]

    # Claude's finished work, last 2 days, titles cleaned
    tray = []
    for it in q:
        if it["status"] != "done" or not it["outcome"].strip():
            continue
        try:
            age = (today - date.fromisoformat(it["created"])).days
        except ValueError:
            continue
        if age <= 2:
            tray.append({"title": clean_title(it["title"]),
                         "date": it["created"],
                         "html": MD.render(it["outcome"])})
        if len(tray) >= 3:
            break
    pending = sum(1 for it in q if it["status"] in ("pending", "working"))

    # slipping: decaying workstreams not already on the desk
    plan_text = " ".join(s["t"] + " " + s["sub"] for s in slots).lower()
    covered = {c["ws"] for c in chips}

    def on_desk(w):
        if w["name"] in covered:
            return True
        toks = [t for t in re.split(r"[^a-z0-9]+", w["name"].lower())
                if len(t) >= 5]
        return any(t in plan_text for t in toks)

    slipping, more = [], 0
    for w in items:
        if not w["live"] or not w["flags"] or on_desk(w):
            continue
        if len(slipping) >= 3:
            more += 1
            continue
        if w["overdue"]:
            why = f"{abs(w['days_to_due'] or 0)} days past its date"
        elif w.get("task_overdue"):
            why = "a task inside is late"
        elif w["chase"]:
            who = w["ball_who"] or "them"
            why = f"no word from {who} in {w['days_waiting']} days"
        elif w["cold"] or w["never_touched"]:
            why = ("never started" if w["never_touched"]
                   else f"untouched {w['days_untouched']} days")
        elif w.get("task_urgent") or w.get("urgent_name") \
                or w.get("room_urgent"):
            why = "you marked this urgent"
        elif w.get("session_blocked"):
            why = "a conversation here is paused on a question for you"
        elif w.get("goal_overdue"):
            why = "a goal here slipped its date"
        else:
            why = w["flags"][0].replace("_", " ")
        slipping.append({"name": w["name"], "why": why,
                         "next": (w["next_action"] or w["next_due_task"]
                                  or "")[:90]})

    # people beat: owed first, then recently-slipped; ancient quiet is an
    # archive question, not today's beat
    cands = []
    for p in people:
        if p.get("oneoff") or p.get("held"):
            continue
        if p["owed"]:
            cands.append((0, 0, p, "owes a reply"))
        elif p["overdue"] and p["days_since"] is not None \
                and p["days_since"] <= 120:
            cands.append((1, p["days_since"], p,
                          f"quiet {p['days_since']}d"))
    cands.sort(key=lambda c: (c[0], c[1]))
    beat = [{"n": p["name"], "why": why, "owed": rank == 0}
            for rank, _, p, why in cands[:4]]
    beat_more = max(0, len(cands) - 4)

    pressed = len(b["overdue"]) + len(b["chase"])
    rest = []
    if pressed:
        rest.append(f"{pressed} pressed")
    if tray:
        rest.append(f"✦ {len(tray)} ready")
    if pending:
        rest.append(f"{pending} queued")
    if not pressed:
        rest.append("all else calm")

    # the mascot has moods — the cute is load-bearing: it reads the day
    if three and all(t["done"] for t in three):
        mood = "celebrating"
    elif pressed:
        mood = "thinking"
    elif not chips and not slipping:
        mood = "sleeping"
    else:
        mood = "reading"

    data = {
        "slots": slots, "bench": bench, "chases": chases, "chips": chips,
        "tray": tray, "slipping": slipping, "more": more,
        "beat": beat, "beat_more": beat_more,
        "habits": [{"n": h["name"], "done": h["done_today"],
                    "wk": h["week_count"], "tg": h["target"]}
                   for h in habits],
        "roommap": ws_room_map(config),
        "mood": mood, "title": ttitle, "intro": tintro,
        "stale": bool(any(t["done"] for t in three)
                      or (ttitle and today.strftime("%A").lower()
                          not in ttitle.lower())),
        "alldone": bool(three and all(t["done"] for t in three)),
    }

    page = TEMPLATE
    page = page.replace("__DAY__", e(today.strftime("%A")))
    page = page.replace("__REST__", e(" · ".join(rest)))
    page = page.replace("__MOOD__", e(mood))
    page = page.replace("__DATA__", json.dumps(data).replace("</", "<\\/"))
    page = page.replace("__TALK__", K.block())

    node = __import__("shutil").which("node")
    if node:
        import tempfile as _tf
        for js in re.findall(r"<script>(.*?)</script>", page, re.S):
            with _tf.NamedTemporaryFile("w", suffix=".js", delete=False) as tf:
                tf.write(js)
            try:
                r = subprocess.run([node, "--check", tf.name],
                                   capture_output=True, text=True, timeout=20)
                if r.returncode != 0:
                    raise SystemExit("REFUSING to write proto.html — a page "
                                     "script does not parse:\n"
                                     + r.stderr.strip()[:600])
            finally:
                os.unlink(tf.name)

    with open(OUT, "w", encoding="utf-8") as f:
        f.write(page)
    return OUT


TEMPLATE = """<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>The desk</title>
<link rel="icon" href="logo-192.png?v=5" type="image/png">
<link rel="apple-touch-icon" href="logo-180.png?v=5">
<script>
var _t = null;
try { _t = localStorage.getItem('brain-theme'); } catch(e){}
if(_t && _t !== 'auto') document.documentElement.setAttribute('data-theme', _t);
</script>
<link rel="stylesheet" href="appearance.css">
<style>
*{box-sizing:border-box}
html,body{margin:0}
body{background:var(--paper);color:var(--ink);
  font-family:var(--sans,'Schibsted',-apple-system,sans-serif);
  font-size:15px;line-height:1.5;
  padding-bottom:calc(170px + env(safe-area-inset-bottom))}
/* 620px was a phone column stretched across a laptop: everything crammed
   into the middle third with the text wrapping far too early. Wider measure,
   real side room, and the whole page breathes at a scale that follows the
   viewport rather than a fixed 40px gutter. */
main{max-width:820px;margin:0 auto;padding:26px clamp(20px,4vw,40px) 0}
button{font-family:inherit}
/* ---- pulse: mascot + one line of state ---- */
.pulse{display:flex;gap:12px;align-items:center;font-size:13px;color:var(--faint);
  padding:4px 0 0}
.pulse img{width:44px;height:44px;flex:none}
.pulse b{font-weight:700;color:var(--ink)}
.menu{position:relative;margin-left:auto}
.menu>button{border:0;background:none;font-size:16px;color:var(--faint);
  cursor:pointer;padding:8px;line-height:1}
.menu>button:hover{color:var(--ink)}
.mpop{position:absolute;right:0;top:34px;z-index:30;background:var(--surface);
  border:1px solid var(--line);border-radius:12px;padding:6px;min-width:170px;
  box-shadow:0 10px 30px rgba(0,0,0,.16)}
.mpop a{display:block;padding:9px 12px;border-radius:8px;color:var(--ink);
  text-decoration:none;font-size:14px}
.mpop a:hover{background:var(--sunken)}
.mpop[hidden]{display:none}
/* the other pages, out in the open — wraps rather than scrolls, so nothing
   ever hides past the right edge */
.deskinav{display:flex;flex-wrap:wrap;gap:8px;margin:14px 0 0}
.deskinav a{display:inline-block;padding:6px 13px;border-radius:999px;
  border:1px solid var(--line);background:var(--surface);color:var(--dim);
  text-decoration:none;font-size:12.5px;font-weight:600;line-height:1.4}
.deskinav a:hover{color:var(--ink);border-color:var(--dim)}
/* ---- zones ---- */
.zone{margin:52px 0 0}
.zl{display:flex;align-items:center;gap:12px;margin:0 0 12px;
  font-weight:700;font-size:11px;line-height:1;font-family:inherit;
  letter-spacing:.16em;text-transform:uppercase;color:var(--green)}
/* The rule beside a zone label is the brain page's hand-drawn squiggle, not
   a flat hairline — same wave, same mask trick, so the two pages read as one
   product. It fills whatever room is left after the words. */
.zl::after{content:'';flex:1;height:8px;background:var(--green);opacity:.55;
  -webkit-mask:url("data:image/svg+xml,%3Csvg%20xmlns='http://www.w3.org/2000/svg'%20width='36'%20height='10'%20viewBox='0%200%2036%2010'%3E%3Cpath%20d='M1%206C4%203%208%203%2011%206S18%209%2021%206S28%203%2035%206'%20fill='none'%20stroke='%23000'%20stroke-width='1.8'%20stroke-linecap='round'/%3E%3C/svg%3E") space left center/36px 8px;
  mask:url("data:image/svg+xml,%3Csvg%20xmlns='http://www.w3.org/2000/svg'%20width='36'%20height='10'%20viewBox='0%200%2036%2010'%3E%3Cpath%20d='M1%206C4%203%208%203%2011%206S18%209%2021%206S28%203%2035%206'%20fill='none'%20stroke='%23000'%20stroke-width='1.8'%20stroke-linecap='round'/%3E%3C/svg%3E") space left center/36px 8px}
.zsub{font-size:12.5px;color:var(--faint);margin:-6px 0 12px}
/* ---- the today box: the plan, framed and voiced ---- */
.todaybox{margin:26px 0 0;background:var(--surface);border:1px solid var(--line);
  border-radius:18px;padding:26px 28px 22px}
.tb-title{margin:0;font-family:var(--serif,'Literata',Georgia,serif);
  font-weight:600;font-size:22px;line-height:1.25;letter-spacing:-.01em}
.tb-intro{margin:8px 0 0;font-family:var(--serif,'Literata',Georgia,serif);
  font-style:italic;font-size:14.5px;line-height:1.5;color:var(--dim)}
.now{list-style:none;margin:16px 0 0;padding:0}
.now li{display:grid;grid-template-columns:28px 1fr 30px;gap:3px 14px;
  align-items:start;padding:13px 0;overflow:hidden;
  transition:opacity .3s ease-out}
.now li.leaving{opacity:0}
.now .tick{width:26px;height:26px;cursor:pointer;margin-top:3px;
  border:2px solid var(--line2);border-radius:8px;background:transparent;
  font-size:14px;line-height:1;color:var(--paper);padding:0}
.now .tick:hover{border-color:var(--green)}
.now .t{font-family:var(--serif,'Literata',Georgia,serif);
  font-weight:500;font-size:18px;line-height:1.35}
.now .sub{grid-column:2;font-size:13px;color:var(--faint)}
.now .nextup{display:inline-block;font-weight:700;font-size:9.5px;
  letter-spacing:.12em;text-transform:uppercase;color:var(--terra);
  margin-right:7px;vertical-align:2px}
.delegate{border:0;background:none;color:var(--line2);cursor:pointer;
  font-size:16px;padding:4px 6px;line-height:1;margin-top:4px}
.delegate:hover{color:var(--terra)}
.chase{list-style:none;margin:12px 0 0;padding:10px 0 0;
  border-top:1px solid var(--line);font-size:14px;color:var(--dim)}
.chase li{display:flex;gap:10px;align-items:center;padding:4px 0;
  transition:opacity .3s ease-out}
.chase li.leaving{opacity:0}
.chase .tick{width:19px;height:19px;min-width:19px;border:1.5px solid var(--line2);
  border-radius:6px;background:transparent;cursor:pointer;padding:0;
  color:var(--paper);font-size:11px;line-height:1}
.chase .tick:hover{border-color:var(--green)}
/* touch: a fingertip needs ~34px — the ::after grows the tap area
   without moving a pixel of layout */
@media(pointer:coarse){
  .tick,.delegate{position:relative}
  .tick::after,.delegate::after{content:"";position:absolute;inset:-7px}
}
.alldone{display:flex;gap:14px;align-items:center;margin:16px 0 4px;
  color:var(--dim);font-size:14px}
.alldone img{width:56px;height:56px}
/* ---- habits: labelled pills ---- */
.habrow{display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin:14px 2px 0}
.hlab{font-weight:700;font-size:9.5px;letter-spacing:.14em;text-transform:uppercase;
  color:var(--faint);margin-right:2px}
.hab{display:inline-flex;gap:7px;align-items:center;cursor:pointer;
  font-weight:600;font-size:12.5px;line-height:1;font-family:inherit;
  color:var(--dim);background:transparent;border:1.5px solid var(--line2);
  border-radius:999px;padding:8px 13px;min-height:34px}
.hab:hover{border-color:var(--green)}
.hab.on{background:var(--greenbg);border-color:var(--green);color:var(--ink)}
.hab .c{color:var(--faint);font-weight:400}
/* ---- quick sweep: filled chips, full text, urgency is a dot ---- */
.chips{display:flex;gap:8px;flex-wrap:wrap}
.chip{display:inline-flex;gap:8px;align-items:center;cursor:pointer;
  font-weight:600;font-size:13px;line-height:1.35;font-family:inherit;
  text-align:left;color:var(--ink);background:var(--sunken);
  border:1px solid transparent;border-radius:14px;padding:10px 14px;
  max-width:100%}
.chip:hover{border-color:var(--dim)}
.chip .udot{width:7px;height:7px;min-width:7px;border-radius:50%;background:var(--bad)}
.chip .est{color:var(--faint);font-weight:400;white-space:nowrap}
.chip.mon{background:transparent;border:1.5px dashed var(--line2);color:var(--faint)}
.chipx{margin:10px 0 0;padding:13px 16px;background:var(--sunken);
  border-radius:14px;font-size:14px}
.chipx[hidden]{display:none}
.chipx .from{color:var(--faint);font-size:12px;margin-bottom:6px}
.chipx .from a{color:var(--dim)}
.chipx .acts{display:flex;gap:8px;flex-wrap:wrap;margin-top:10px}
.chipx button{font-weight:600;font-size:13px;line-height:1;font-family:inherit;
  padding:10px 14px;border-radius:10px;border:1px solid var(--line);
  background:var(--paper);color:var(--ink);cursor:pointer;min-height:38px}
.chipx button.pri{background:var(--green);color:var(--paper);border-color:transparent}
/* ---- Claude finished ---- */
.tray details{margin:0 0 10px;border-left:2px solid var(--green);padding-left:13px}
.tray summary{cursor:pointer;font-weight:600;font-size:14px;color:var(--ink);
  line-height:1.4}
.tray summary .dt{color:var(--faint);font-weight:400;font-size:12px;
  margin-left:8px;white-space:nowrap}
.tray .body{font-size:14px;color:var(--dim);overflow-x:auto;margin-top:6px}
/* ---- slipping: accent bars, real buttons ---- */
.slip{list-style:none;margin:0;padding:0}
.slip li{padding:2px 0 2px 13px;border-left:2px solid var(--terra);margin:0 0 18px}
.slip li.late{border-left-color:var(--bad)}
.slip .n{font-weight:700;font-size:15px}
.slip .why{color:var(--dim);font-size:13px;margin-top:1px}
.slip .acts{display:flex;gap:8px;margin-top:8px;flex-wrap:wrap}
.slip .acts button, .slip .acts a{display:inline-flex;align-items:center;
  font-weight:600;font-size:12.5px;line-height:1;font-family:inherit;
  color:var(--ink);background:var(--paper);border:1px solid var(--line);
  border-radius:9px;padding:9px 12px;cursor:pointer;text-decoration:none;
  min-height:34px}
.slip .acts button:hover, .slip .acts a:hover{border-color:var(--dim)}
.moreline{font-size:13px;color:var(--faint);margin:2px 0 0}
.moreline a{color:var(--dim)}
/* ---- people: bare faces ---- */
.beat{display:flex;gap:4px;flex-wrap:wrap}
.face{display:flex;gap:9px;align-items:center;border:0;border-radius:10px;
  padding:7px 10px;background:transparent;cursor:pointer;
  font-weight:600;font-size:13.5px;line-height:1.2;font-family:inherit;
  color:var(--ink);min-height:40px;text-decoration:none}
.face:hover{background:var(--sunken)}
.face .av{width:28px;height:28px;border-radius:50%;background:var(--sunken);
  display:inline-flex;align-items:center;justify-content:center;
  font-size:11px;font-weight:700;color:var(--dim)}
.face.owed .av{background:var(--badbg);color:var(--bad);
  box-shadow:0 0 0 1.5px var(--bad)}
.face .d{color:var(--faint);font-weight:400;font-size:12px}
.face.morep{color:var(--faint)}
/* ---- the bar ---- */
.barwrap{position:fixed;left:0;right:0;bottom:0;z-index:20;
  padding:14px 16px calc(12px + env(safe-area-inset-bottom));
  background:linear-gradient(to top, var(--paper) 72%, transparent)}
.bar{max-width:620px;margin:0 auto;display:flex;gap:8px;align-items:flex-end;
  background:var(--surface);border:1.5px solid var(--line);border-radius:18px;
  padding:8px 10px;box-shadow:0 6px 28px var(--shadow,rgba(0,0,0,.14))}
.bar textarea{flex:1;border:0;background:none;resize:none;
  font-family:inherit;font-size:15px;line-height:1.45;
  color:var(--ink);padding:8px 6px;max-height:120px;outline:none}
.bar .go{border:0;background:var(--green);color:var(--paper);
  font-weight:700;font-size:14px;line-height:1;font-family:inherit;
  border-radius:12px;padding:12px 16px;cursor:pointer;min-height:44px}
.bar .go[disabled]{opacity:.5}
.barhint{max-width:620px;margin:6px auto 0;font-size:11.5px;color:var(--faint);
  padding:0 8px}
.receipt{color:var(--green);font-weight:600}
.talkmic{align-self:flex-end;margin-bottom:2px}
.toast{position:fixed;left:50%;transform:translateX(-50%);
  bottom:calc(118px + env(safe-area-inset-bottom));z-index:40;background:var(--ink);
  color:var(--paper);font-size:13px;padding:9px 18px;border-radius:999px;
  opacity:0;transition:opacity .18s;pointer-events:none}
.toast.on{opacity:1}
.apill{font-size:12px;font-weight:600;color:var(--terra);white-space:nowrap}
.staleline{margin:10px 0 0;font-size:13px;color:var(--terra);
  display:flex;gap:10px;align-items:center;flex-wrap:wrap}
.staleline button{font-family:inherit;font-weight:600;font-size:12.5px;
  line-height:1;padding:8px 12px;border-radius:9px;border:1px solid var(--line);
  background:var(--paper);color:var(--ink);cursor:pointer}
.staleline button:hover{border-color:var(--dim)}
.whyline{display:block;font-weight:400;font-size:11px;color:var(--faint);
  margin-top:3px}
.empty{color:var(--faint);font-size:14px}
.rowacts{display:flex;flex-direction:column;align-items:center}
.addrow2{display:block;width:100%;margin:12px 0 0;padding:10px 0 2px;
  border:0;border-top:1px dashed var(--line);background:none;cursor:pointer;
  font-family:inherit;font-size:12.5px;font-weight:600;color:var(--faint);
  text-align:left}
.addrow2:hover{color:var(--ink)}
.picker{margin:10px 0 2px;padding:13px 16px;background:var(--sunken);
  border-radius:14px;font-size:14px}
.picker .from{color:var(--faint);font-size:12px;margin-bottom:8px}
.picker .acts{display:flex;gap:8px;flex-wrap:wrap;margin-top:12px}
.picker .pickin{flex:1;min-width:180px;font-family:inherit;font-size:13.5px;
  padding:9px 12px;border:1px solid var(--line);border-radius:10px;
  background:var(--paper);color:var(--ink)}
.picker button{font-family:inherit;font-weight:600;font-size:13px;line-height:1;
  padding:10px 14px;border-radius:10px;border:1px solid var(--line);
  background:var(--paper);color:var(--ink);cursor:pointer}
.picker button.pri{background:var(--green);color:var(--paper);border-color:transparent}
.picker .chips .chip{background:var(--paper)}
.connpanel{position:fixed;left:50%;top:50%;transform:translate(-50%,-50%);
  z-index:60;width:min(480px,calc(100vw - 36px));max-height:80vh;overflow:auto;
  background:var(--surface);border:1.5px solid var(--line);border-radius:18px;
  padding:20px 24px;box-shadow:0 16px 50px rgba(0,0,0,.25)}
.connpanel h2{margin:0 0 4px;font-family:var(--serif,Georgia,serif);
  font-weight:600;font-size:20px}
.connpanel h3{margin:16px 0 4px;font-size:13px;font-weight:700}
.connpanel p{margin:0;font-size:13.5px;line-height:1.55;color:var(--dim)}
.connx{position:absolute;top:10px;right:14px;border:0;background:none;
  font-size:20px;color:var(--faint);cursor:pointer;padding:4px}
[hidden]{display:none !important}
@media(prefers-reduced-motion: reduce){
  .now li,.chase li{transition:none}
}
</style></head><body>
<main>
  <div class="pulse">
    <img src="art/__MOOD__.png?v=2" alt="">
    <span><b>__DAY__</b> &middot; __REST__</span>
    <span class="apill" id="apill" hidden></span>
    <span class="menu">
      <button id="mbtn" aria-label="Everything else" aria-expanded="false">&#9776;</button>
      <span class="mpop" id="mpop" hidden>
        <a href="index.html">The brain</a>
        <a href="index.html#/plate">Plate — everything</a>
        <a href="index.html#/people">People</a>
        <a href="rooms.html">Rooms</a>
        <a href="map.html">Map</a>
        <a href="sessions.html">Sessions</a>
        <a href="index.html#/claude">History &amp; queue</a>
        <a href="#" id="connlink">Connections&hellip;</a>
      </span>
    </span>
  </div>
  <!-- The other pages were only reachable through the hamburger, which is a
       closed door on a page meant to be a desk. They are links now; the menu
       keeps the long tail. -->
  <nav class="deskinav">
    <a href="index.html">The brain</a>
    <a href="rooms.html">Rooms</a>
    <a href="map.html">Map</a>
    <a href="sessions.html">Sessions</a>
    <a href="index.html#/people">People</a>
    <a href="index.html#/plate">Plate</a>
  </nav>
  <div id="desk"></div>
</main>
<div class="barwrap">
  <div class="bar">
    <textarea id="bar" rows="1" data-mic
      placeholder="Say anything — what happened, a new task, an ask&hellip;"></textarea>
    <button class="go" id="bargo">Go</button>
  </div>
  <div class="barhint" id="barhint">I file it, tick it, or start on it.
    I never send or delete without you. Paste a screenshot to attach it.</div>
</div>
<div class="toast" id="toast" hidden></div>
__TALK__
<script>
var D = __DATA__;

function el(t, cls, text){
  var n = document.createElement(t);
  if(cls) n.className = cls;
  if(text != null) n.textContent = text;
  return n;
}
var toastT = null;
function toast(msg){
  var t = document.getElementById('toast');
  t.textContent = msg; t.hidden = false;
  requestAnimationFrame(function(){ t.classList.add('on'); });
  if(toastT) clearTimeout(toastT);
  toastT = setTimeout(function(){
    t.classList.remove('on');
    setTimeout(function(){ t.hidden = true; }, 200);
  }, 2400);
}
function post(path, body){
  return fetch(path, {method:'POST', headers:{'Content-Type':'application/json'},
                      body: JSON.stringify(body)})
    .then(function(r){ return r.json().then(function(j){
      if(!r.ok) throw new Error(j.error || r.status);
      return j;
    }); });
}
function roomLink(ws){
  return D.roommap[ws] ? 'rooms.html#room/' + D.roommap[ws] : '';
}
function delegateBtn(text){
  var b = el('button', 'delegate', '✦');
  b.title = 'Hand to Claude — research, drafts, prep. Never sends or pays.';
  b.onclick = function(){
    b.disabled = true;
    post('/api/queue', {mode: 'just-do-it',
      text: 'Start this for me: “' + text + '”. Do the part Claude can do — '
        + 'research real options into a note under the task, find numbers and '
        + 'links, draft any message into brain/drafts/. Never book, pay, send '
        + 'or submit; end the Outcome with exactly what remains for me.'})
      .then(function(){ b.disabled = false; toast('Queued for Claude ✦'); })
      .catch(function(err){ b.disabled = false; toast(err.message); });
  };
  return b;
}

var desk = document.getElementById('desk');

// ---- the today box -------------------------------------------------------
var box = el('section', 'todaybox');
box.appendChild(el('h1', 'tb-title', D.title || 'Today'));
if(D.intro) box.appendChild(el('p', 'tb-intro', D.intro));
if(D.stale){
  var st = el('p', 'staleline');
  st.appendChild(document.createTextNode(
    'Life moved since this was written — some of it is already done. '));
  var rw = el('button', '', '↻ Rewrite the plan');
  rw.onclick = function(){
    if(!confirm('Have Claude rewrite today\u2019s plan around what\u2019s '
                + 'actually left? It reads everything and takes a minute or '
                + 'two — the page refreshes itself when the new plan lands.'))
      return;
    rw.disabled = true;
    rw.textContent = 'Rewriting — a minute or two\u2026';
    post('/api/agent', {job: 'today'})
      .then(function(){ agentPoll(); nudgePoll(); })
      .catch(function(err){
        rw.disabled = false;
        rw.textContent = '↻ Rewrite the plan';
        toast(err.message);
      });
  };
  st.appendChild(rw);
  box.appendChild(st);
  window.__staleBtn = rw;
}
var nowUl = el('ul', 'now');

function slotRow(s){
  var li = el('li');
  var tick = el('button', 'tick');
  tick.title = 'Done';
  tick.onclick = function(){
    tick.disabled = true;
    post('/api/task', {src: s.src, key: s.k, action: 'done'})
      .then(function(){
        toast('Done ✓');
        li.classList.add('leaving');
        setTimeout(function(){
          li.remove();
          refill();
          nudgePoll();
        }, 320);
      })
      .catch(function(err){ tick.disabled = false; toast(err.message); });
  };
  li.appendChild(tick);
  var t = el('span', 't', s.t);
  if(s.next){
    var tag = el('span', 'nextup', 'next up');
    t.textContent = '';
    t.appendChild(tag);
    t.appendChild(document.createTextNode(s.t));
  }
  li.appendChild(t);
  var ra = el('span', 'rowacts');
  ra.appendChild(delegateBtn(s.t + (s.sub ? ' — ' + s.sub : '')));
  var mm = el('button', 'delegate', '⋯');
  mm.title = 'Not this — swap it or take it off today';
  mm.onclick = function(){
    if(!confirm('Take “' + s.t.slice(0, 50) + '” off today? It stays in its '
        + 'workstream — then pick or type a replacement below.'))
      return;
    mm.disabled = true;
    var fin = function(){
      li.classList.add('leaving');
      setTimeout(function(){ li.remove(); openPicker(); }, 300);
    };
    if(s.src === 'today.md')
      post('/api/plan/set', {remove: s.k})
        .then(fin).catch(function(err){ mm.disabled = false; toast(err.message); });
    else fin();               // a bench suggestion was never in the plan file
  };
  ra.appendChild(mm);
  li.appendChild(ra);
  if(s.sub) li.appendChild(el('span', 'sub', s.sub));
  return li;
}
function refill(){
  // finishing work reveals work: the bench tops the plan back up to three
  while(nowUl.children.length < 3 && D.bench.length){
    var nb = D.bench.shift();
    var parts = nb.t.split(' — ');
    nowUl.appendChild(slotRow({t: parts[0], sub: parts.slice(1).join(' — ')
      || ('from ' + nb.ws), k: nb.k, src: 'workstreams.md', next: true}));
  }
  if(!nowUl.children.length){
    var ad = el('div', 'alldone');
    var im = document.createElement('img');
    im.src = 'art/celebrating.png?v=2'; im.alt = '';
    ad.appendChild(im);
    ad.appendChild(el('span', '', 'All landed. The bench is empty too — '
      + 'enjoy it, or ask the bar for what could come next.'));
    nowUl.parentNode.insertBefore(ad, nowUl);
  }
}
D.slots.forEach(function(s){ nowUl.appendChild(slotRow(s)); });
box.appendChild(nowUl);
var addRow = el('button', 'addrow2', '+ Add to today — pick or type your own');
var picker = el('div', 'picker'); picker.hidden = true;
function planAdd(text, after){
  post('/api/plan/set', {add: text})
    .then(function(){ toast('Planned ✓'); if(after) after(); nudgePoll(); })
    .catch(function(err){ toast(err.message); });
}
function openPicker(){
  picker.innerHTML = '';
  picker.appendChild(el('div', 'from',
    'The loudest waiting tasks — tap to plan one, or type your own:'));
  var pc = el('div', 'chips');
  D.bench.slice(0, 5).forEach(function(nb){
    var c = el('button', 'chip');
    c.appendChild(document.createTextNode(nb.t));
    if(nb.why) c.appendChild(el('span', 'whyline', nb.why));
    c.onclick = function(){
      c.disabled = true;
      planAdd(nb.t, function(){ c.remove(); picker.hidden = true; });
    };
    pc.appendChild(c);
  });
  picker.appendChild(pc);
  var row = el('div', 'acts');
  var inp = document.createElement('input');
  inp.placeholder = 'Or your own — “call the notaire before lunch”…';
  inp.className = 'pickin';
  var gob = el('button', 'pri', 'Plan it');
  gob.onclick = function(){
    var v = inp.value.trim();
    if(v) planAdd(v, function(){ picker.hidden = true; });
  };
  inp.addEventListener('keydown', function(ev3){
    if(ev3.key === 'Enter') gob.click();
  });
  row.appendChild(inp); row.appendChild(gob);
  var cl = el('button', '', 'Close');
  cl.onclick = function(){ picker.hidden = true; };
  row.appendChild(cl);
  picker.appendChild(row);
  picker.hidden = false;
}
addRow.onclick = openPicker;
box.appendChild(addRow);
box.appendChild(picker);
if(D.alldone && !D.bench.length && !D.slots.length){ refill(); }
if(D.chases.length){
  var cu = el('ul', 'chase');
  D.chases.forEach(function(t){
    var li = el('li');
    var tick = el('button', 'tick');
    tick.title = 'Done';
    tick.onclick = function(){
      tick.disabled = true;
      post('/api/task', {src: 'today.md', key: t.k, action: 'done'})
        .then(function(){
          toast('Done ✓');
          li.classList.add('leaving');
          setTimeout(function(){ li.remove(); nudgePoll(); }, 320);
        })
        .catch(function(err){ tick.disabled = false; toast(err.message); });
    };
    li.appendChild(tick);
    li.appendChild(el('span', '', t.t + (t.sub ? ' — ' + t.sub : '')));
    cu.appendChild(li);
  });
  box.appendChild(cu);
}
desk.appendChild(box);

// ---- habits: labelled pills ---------------------------------------------
if(D.habits.length){
  var hr = el('div', 'habrow');
  hr.appendChild(el('span', 'hlab', 'Habits'));
  D.habits.forEach(function(h){
    var p = el('button', 'hab' + (h.done ? ' on' : ''));
    var short = h.n;
    p.appendChild(document.createTextNode((h.done ? '✓ ' : '') + short));
    p.appendChild(el('span', 'c', h.wk + '/' + h.tg));
    p.title = h.n + ' — ' + h.wk + ' of ' + h.tg + ' this week';
    p.onclick = function(){
      p.disabled = true;
      post('/api/habit', {name: h.n})
        .then(function(j){
          p.disabled = false;
          p.classList.toggle('on', j.done);
          p.firstChild.textContent = (j.done ? '✓ ' : '') + short;
          toast(j.done ? 'Logged ✓' : 'Unlogged');
        })
        .catch(function(err){ p.disabled = false; toast(err.message); });
    };
    hr.appendChild(p);
  });
  desk.appendChild(hr);
}

// ---- quick sweep ---------------------------------------------------------
if(D.chips.length){
  var z2 = el('section', 'zone');
  z2.appendChild(el('p', 'zl', 'Quick sweep'));
  z2.appendChild(el('p', 'zsub',
    'Small and time-pressed — each is minutes, not an hour.'));
  var wrap = el('div', 'chips');
  var xp = el('div', 'chipx'); xp.hidden = true;
  D.chips.forEach(function(c){
    var chip = el('button', 'chip' + (c.monday ? ' mon' : ''));
    if(c.urgent && !c.monday) chip.appendChild(el('span', 'udot'));
    chip.appendChild(document.createTextNode(c.t));
    if(c.mins) chip.appendChild(el('span', 'est', c.mins + 'm'));
    if(c.monday) chip.appendChild(el('span', 'est', 'Mon'));
    chip.onclick = function(){
      xp.innerHTML = '';
      var fr = el('div', 'from');
      var rl = roomLink(c.ws);
      if(rl){
        fr.appendChild(document.createTextNode('from '));
        var a = document.createElement('a');
        a.href = rl; a.textContent = c.ws;
        fr.appendChild(a);
      } else fr.textContent = 'from ' + c.ws;
      if(c.why) fr.appendChild(document.createTextNode(' · ' + c.why));
      if(c.monday) fr.appendChild(document.createTextNode(
        ' · needs offices open — it can wait for Monday'));
      xp.appendChild(fr);
      xp.appendChild(el('div', '', c.t));
      var acts = el('div', 'acts');
      var done = el('button', 'pri', 'Done ✓');
      done.onclick = function(){
        done.disabled = true;
        post('/api/task', {src: 'workstreams.md', key: c.k, action: 'done'})
          .then(function(){ chip.remove(); xp.hidden = true;
            toast('Done ✓'); nudgePoll(); })
          .catch(function(err){ done.disabled = false; toast(err.message); });
      };
      var dg = delegateBtn(c.t); dg.textContent = '✦ Start for me';
      dg.className = '';
      var nt = el('button', '', 'Not today');
      nt.onclick = function(){ xp.hidden = true; };
      acts.appendChild(done); acts.appendChild(dg); acts.appendChild(nt);
      xp.appendChild(acts);
      xp.hidden = false;
    };
    wrap.appendChild(chip);
  });
  z2.appendChild(wrap); z2.appendChild(xp);
  desk.appendChild(z2);
}

// ---- Claude finished -----------------------------------------------------
if(D.tray.length){
  var z3 = el('section', 'zone tray');
  z3.appendChild(el('p', 'zl', '✦ Claude finished'));
  z3.appendChild(el('p', 'zsub',
    'Things you handed over, done — tap one to read the result.'));
  D.tray.forEach(function(t){
    var d = document.createElement('details');
    var s = document.createElement('summary');
    s.textContent = t.title;
    s.appendChild(el('span', 'dt', t.date));
    d.appendChild(s);
    var bd = el('div', 'body'); bd.innerHTML = t.html;
    d.appendChild(bd);
    z3.appendChild(d);
  });
  desk.appendChild(z3);
}

// ---- slipping ------------------------------------------------------------
if(D.slipping.length){
  var z4 = el('section', 'zone');
  z4.appendChild(el('p', 'zl', 'Slipping'));
  var sl = el('ul', 'slip');
  D.slipping.forEach(function(s){
    var li = el('li', s.why.indexOf('past its date') >= 0 ? 'late' : '');
    li.appendChild(el('div', 'n', s.name));
    li.appendChild(el('div', 'why', s.why
      + (s.next ? ' · next: ' + s.next : '')));
    var acts = el('div', 'acts');
    var tell = el('button', '', '✦ Hand to Claude');
    tell.onclick = function(){
      tell.disabled = true;
      post('/api/queue', {mode: 'just-do-it',
        text: 'The workstream “' + s.name + '” is slipping (' + s.why
          + '). Move it: do what Claude can (research, drafts, chasing '
          + 'text prepared), and say exactly what remains for me.'})
        .then(function(){ tell.disabled = false; toast('Queued ✦'); })
        .catch(function(err){ tell.disabled = false; toast(err.message); });
    };
    var sn = el('button', '', 'Snooze 7d');
    sn.onclick = function(){
      sn.disabled = true;
      post('/api/ws/snooze', {name: s.name, days: '7'})
        .then(function(){ li.style.opacity = '.4'; toast('Asleep ✓');
          nudgePoll(); })
        .catch(function(err){ sn.disabled = false; toast(err.message); });
    };
    var opn = document.createElement('a');
    var rl = roomLink(s.name);
    opn.href = rl || 'index.html#/plate';
    opn.textContent = rl ? 'Its room' : 'On the plate';
    acts.appendChild(tell); acts.appendChild(sn); acts.appendChild(opn);
    li.appendChild(acts);
    sl.appendChild(li);
  });
  z4.appendChild(sl);
  if(D.more)
    z4.appendChild(el('p', 'moreline')).innerHTML =
      'and ' + D.more + ' more on <a href="index.html#/plate">the plate</a>.';
  desk.appendChild(z4);
}

// ---- people beat ---------------------------------------------------------
if(D.beat.length){
  var z5 = el('section', 'zone');
  z5.appendChild(el('p', 'zl', 'People'));
  var bt = el('div', 'beat');
  D.beat.forEach(function(p){
    var f = el('button', 'face' + (p.owed ? ' owed' : ''));
    var av = el('span', 'av', p.n.split(' ').map(function(x){
      return x[0] || ''; }).join('').slice(0, 2).toUpperCase());
    f.appendChild(av);
    f.appendChild(document.createTextNode(p.n));
    f.appendChild(el('span', 'd', p.why));
    f.onclick = function(){
      if(!confirm(p.n + ' — mark spoken today? (Cancel = ask Claude to '
                  + 'draft a message instead)')){
        post('/api/queue', {mode: 'draft',
          text: 'Draft a short message to ' + p.n + ' (' + p.why + '). '
            + 'Use their preferred channel and my writing rules. Draft '
            + 'only — I send it.'})
          .then(function(){ toast('Draft queued ✦'); })
          .catch(function(err){ toast(err.message); });
        return;
      }
      post('/api/person/spoke', {name: p.n})
        .then(function(){ f.style.opacity = '.4'; toast('Stamped today ✓');
          nudgePoll(); })
        .catch(function(err){ toast(err.message); });
    };
    bt.appendChild(f);
  });
  if(D.beat_more){
    var mf = el('a', 'face morep', '+' + D.beat_more + ' more');
    mf.href = 'index.html#/people';
    bt.appendChild(mf);
  }
  z5.appendChild(bt);
  desk.appendChild(z5);
}

// ---- the bar -------------------------------------------------------------
var bar = document.getElementById('bar'), go = document.getElementById('bargo');
var barFiles = [];
bar.addEventListener('input', function(){
  bar.style.height = 'auto';
  bar.style.height = Math.min(bar.scrollHeight, 120) + 'px';
});
bar.addEventListener('keydown', function(ev2){
  if(ev2.key === 'Enter' && !ev2.shiftKey){ ev2.preventDefault(); go.click(); }
});
bar.addEventListener('paste', function(ev2){
  var items = Array.prototype.filter.call(
    (ev2.clipboardData || {}).items || [],
    function(it){ return it.type && it.type.indexOf('image/') === 0; });
  if(!items.length) return;
  ev2.preventDefault();
  Promise.all(items.map(function(it){
    var f = it.getAsFile();
    return new Promise(function(res, rej){
      var r = new FileReader();
      r.onload = function(){
        res({name: 'pasted-' + (Date.now() % 100000) + '.'
               + ((f.type || '').split('/')[1] || 'png').replace('jpeg', 'jpg'),
             data: String(r.result)});
      };
      r.onerror = rej;
      r.readAsDataURL(f);
    });
  })).then(function(out){
    barFiles = barFiles.concat(out);
    toast('Attached (' + barFiles.length + ') ✓');
  }).catch(function(){ toast('Could not read the paste'); });
});
go.onclick = function(){
  var text = bar.value.trim();
  if(!text && !barFiles.length) return;
  go.disabled = true;
  var pre = 'From the desk. Work out what this is and act accordingly: '
    + 'things that happened get ticked where they live (Touched stamped); '
    + 'new tasks get filed in the right workstream; questions get answered '
    + 'in the Outcome; asks get done. Reconcile, never duplicate. ';
  var chain = barFiles.length
    ? post('/api/upload', {files: barFiles}).then(function(j){ return j.saved; })
    : Promise.resolve([]);
  chain.then(function(saved){
    return post('/api/queue', {text: pre + (text || 'See the attached files.'),
                               mode: 'dump', files: saved});
  }).then(function(){
    bar.value = ''; bar.style.height = 'auto'; barFiles = []; go.disabled = false;
    var h = document.getElementById('barhint');
    h.innerHTML = '<span class="receipt">Taken ✓</span> — runs with the '
      + 'queue; the result lands under ✦ Claude finished.';
    return post('/api/agent', {job: 'queue'}).catch(function(){});
  }).then(function(){ nudgePoll(); })
    .catch(function(err){ go.disabled = false; toast(err.message); });
};

// ---- connections: where the outside world plugs in -----------------------
var conn = el('div', 'connpanel'); conn.hidden = true;
conn.innerHTML = '<button class="connx" aria-label="Close">×</button>'
  + '<h2>Connections</h2>'
  + '<h3>Chats — WhatsApp, Instagram, Telegram…</h3>'
  + '<p>Through <b>Beeper Desktop</b>: bridge your networks inside Beeper '
  + 'once, keep it open, and the brain reads chat names and dates (never '
  + 'messages) each morning — or tap <i>Sync from Beeper</i> on the People '
  + 'page. That is how “last spoke” stays true by itself.</p>'
  + '<h3>Telegram — talk TO the brain</h3>'
  + '<p>A two-minute bot: message <b>@BotFather</b> → /newbot, put the token '
  + 'in <i>brain/.telegram.json</i>, then message your bot anything. From '
  + 'then on “brain: buy socks” from any queue lands in your inbox, “plan” '
  + 'answers with today, and the morning plan arrives as a message.</p>'
  + '<h3>Calendar</h3>'
  + '<p>On a Mac, add accounts to the <b>Calendar</b> app (System Settings '
  + '→ Internet Accounts) and the plan reads them locally. On any OS, '
  + 'subscribe a feed: <i>calendar_read.py --add-feed</i> with your '
  + 'calendar&rsquo;s private ICS address.</p>'
  + '<h3>Email sending</h3>'
  + '<p id="connmail">Checking…</p>';
document.body.appendChild(conn);
conn.querySelector('.connx').onclick = function(){ conn.hidden = true; };
document.getElementById('connlink').onclick = function(ev4){
  ev4.preventDefault();
  mp.hidden = true;
  conn.hidden = false;
  fetch('/api/email/status').then(function(r){ return r.json(); })
    .then(function(j){
      var n = (j.accounts || []).length;
      document.getElementById('connmail').innerHTML = n
        ? 'Set up ✓ — ' + j.accounts.join(', ') + '. Drafts get an '
          + '“Approve &amp; send” button (never for close circles).'
        : 'Not set up. Ask the bar: “set up my email for sending” — it '
          + 'takes an app password from your provider; the password lives '
          + 'in the Keychain, and every send stays a button you press.';
    })
    .catch(function(){
      document.getElementById('connmail').textContent =
        'Could not check — is the server running?';
    });
};

// ---- the run, visible: nothing Claude does is ever silent ----------------
var apill = document.getElementById('apill'), apT = null;
function agentPoll(){
  fetch('/api/agent').then(function(r){ return r.json(); }).then(function(j){
    if(j.running){
      apill.hidden = false;
      apill.textContent = '✦ Claude is working — '
        + (j.job === 'today' ? 'rewriting the plan' : j.job)
        + '… usually a minute or two';
      if(window.__staleBtn && j.job === 'today'){
        window.__staleBtn.disabled = true;
        window.__staleBtn.textContent = 'Rewriting — a minute or two\u2026';
      }
      if(!apT) apT = setInterval(agentPoll, 4000);
    } else {
      if(apT){ clearInterval(apT); apT = null;
        nudgePoll();                 // a run just ended — fetch the result
      }
      if(j.pending > 0){
        apill.hidden = false;
        apill.textContent = j.pending + ' waiting for Claude';
      } else apill.hidden = true;
    }
  }).catch(function(){ apill.hidden = true; });
}
agentPoll();

// ---- menu, version poll --------------------------------------------------
var mb = document.getElementById('mbtn'), mp = document.getElementById('mpop');
mb.onclick = function(){
  mp.hidden = !mp.hidden;
  mb.setAttribute('aria-expanded', String(!mp.hidden));
};
document.addEventListener('click', function(ev2){
  if(!mp.hidden && !mp.contains(ev2.target) && ev2.target !== mb)
    mp.hidden = true;
});
var VER = null, verFastT = null;
function verCheck(){
  fetch('/api/version').then(function(r){ return r.json(); }).then(function(j){
    if(VER === null){ VER = j.version; return; }
    if(j.building) return;
    if(j.version !== VER){
      var a = document.activeElement;
      if(a && (a.tagName === 'TEXTAREA' || a.tagName === 'INPUT')) return;
      location.reload();
    }
  }).catch(function(){});
}
verCheck();
setInterval(function(){ if(!document.hidden) verCheck(); }, 20000);
function nudgePoll(){
  if(verFastT) return;
  var n = 0;
  verFastT = setInterval(function(){
    n++;
    if(n > 24){ clearInterval(verFastT); verFastT = null; return; }
    if(!document.hidden) verCheck();
  }, 2500);
}
</script></body></html>
"""


if __name__ == "__main__":
    path = build()
    print(f"Built {path}")

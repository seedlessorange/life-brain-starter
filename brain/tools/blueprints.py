#!/usr/bin/env python3
"""The blueprints: four working drawings of how the brain works.

    python3 brain/tools/blueprints.py            # brain/blueprints/*.html
    python3 brain/tools/blueprints.py --export   # plus a PDF and a PNG per sheet

Sheet 1 follows one request from a front door to the folder; sheet 2 is the
skill backbone (area, chore, command, what starts it); sheet 3 is where
everything lives; sheet 4 is a day of what runs by itself. The numbers in
the title block and the times on sheet 4 are read live (model.py, the
commands folder, the self-test, config), so a rerun keeps the drawings true.

Made 28 Sep for her to understand the brain in detail and present it; it
first went out as a private artifact, and she asked for it outside one.
The page is served by the brain's server (blueprints/ under the brain) and
opens from the file too. `--export` renders the PDF and PNGs (both themes)
with the headless Chrome the gstack tools install, and skips quietly when
there is none. The output folder is gitignored: regenerate, don't commit.
"""
import glob
import json
import os
import subprocess
import sys
from datetime import date
from html import escape as h

HERE = os.path.dirname(os.path.abspath(__file__))
BRAIN = os.path.dirname(HERE)
ROOT = os.path.dirname(BRAIN)
OUTDIR = os.path.join(BRAIN, "blueprints")
OUT = os.path.join(OUTDIR, "life-brain-blueprints.html")
sys.path.insert(0, HERE)
import agents as AG  # noqa: E402  (which agent the brain runs, named at build time)


def _config():
    try:
        with open(os.path.join(BRAIN, "config.json"), encoding="utf-8") as f:
            return json.load(f) or {}
    except Exception:
        return {}


def _hm(s, default):
    """'19:30' -> 19.5 hours."""
    try:
        hh, mm = str(s or default).split(":")[:2]
        return int(hh) + int(mm) / 60
    except ValueError:
        hh, mm = default.split(":")
        return int(hh) + int(mm) / 60


def times(cfg):
    """The clock times the drawings print, from her own settings."""
    recs = (cfg.get("recordings_auto") or {}).get("times") or ["12:30", "19:30"]
    return {"night": str((cfg.get("night") or {}).get("at") or "01:00"),
            "recs": [str(t) for t in recs]}


def quick_models(cfg):
    """'Haiku or Sonnet': which Claude answers the no-tool calls (config
    voice.model for spoken answers, llm.model and llm.models for the rest)."""
    llm = cfg.get("llm") or {}
    names = [(cfg.get("voice") or {}).get("model"), llm.get("model")]
    names += list((llm.get("models") or {}).values())
    seen = []
    for n in names:
        n = str(n or "haiku").strip().capitalize()
        if n not in seen:
            seen.append(n)
    if llm.get("provider") == "ollama":
        seen.append("a local model")
    return " or ".join(seen[:2])


def pronouns(cfg):
    """The owner's pronouns from config `owner_pronouns` (they/them when
    unset: never a guess), as the words the drawings need, verbs agreeing."""
    p = str(cfg.get("owner_pronouns") or "they/them").strip().lower()
    if p.startswith("she"):
        d = {"she": "she", "her": "her", "s": "s", "has": "has", "is": "is"}
    elif p.startswith("he"):
        d = {"she": "he", "her": "his", "s": "s", "has": "has", "is": "is"}
    else:
        d = {"she": "they", "her": "their", "s": "", "has": "have", "is": "are"}
    d["She"], d["Her"], d["HER"] = d["she"].capitalize(), d["her"].capitalize(), d["her"].upper()
    return d


P = pronouns({})


def say(s):
    """A label or sentence with the owner's pronouns filled in."""
    return s.format(**P) if "{" in s else s


def areas():
    """'school, business, family and houses': the owner's busiest areas."""
    try:
        import model as M
        from collections import Counter
        c = Counter(str(w.get("area") or "").strip().lower()
                    for w in M.load() if w.get("live") and w.get("area"))
        names = [a.capitalize() for a, _n in c.most_common(4) if a]
    except Exception:
        names = []
    if len(names) < 2:
        return ""
    return ", ".join(names[:-1]) + " and " + names[-1]


def numbers():
    """What the title block says, read live."""
    out = {"fronts": None, "live": None, "commands": None, "checks": None, "ok": None}
    try:
        import model as M
        ws = M.load()
        out["fronts"], out["live"] = len(ws), sum(1 for w in ws if w.get("live"))
    except Exception:
        pass
    out["commands"] = len(glob.glob(os.path.join(ROOT, ".claude", "commands", "*.md")))
    try:
        import contextlib
        import io
        import selftest as ST
        with contextlib.redirect_stdout(io.StringIO()):
            ST.run()
        out["checks"], out["ok"] = ST.CHECKS, not ST.FAILURES
    except Exception:
        pass
    return out


def marker(mid, cls=""):
    fill = 'fill="currentColor"' if not cls else f'class="{cls}"'
    return (f'<marker id="{mid}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" '
            f'markerHeight="7" orient="auto-start-reverse"><path d="M0,0L10,5L0,10z" {fill}/></marker>')


def box(x, y, w, hgt, title=None, lines=(), cls="bx", tx=None, ty=None, center=False, tcls="t"):
    out = [f'<rect class="{cls}" x="{x}" y="{y}" width="{w}" height="{hgt}" rx="4"/>']
    ax = x + w / 2 if center else (tx if tx is not None else x + 14)
    anchor = " mid" if center else ""
    yy = ty if ty is not None else y + 25
    if title:
        out.append(f'<text class="{tcls}{anchor}" x="{ax:g}" y="{yy:g}">{h(say(title))}</text>')
        yy += 20
    for ln in lines:
        out.append(f'<text class="s{anchor}" x="{ax:g}" y="{yy:g}">{h(say(ln))}</text>')
        yy += 17
    return "".join(out)


def arrow(d, red=False, both=False, mid="a"):
    m = ("r" if red else "a") + mid
    cls = "ln-red" if red else "ln"
    s = f' marker-start="url(#{m})"' if both else ""
    return f'<path class="{cls}" d="{d}"{s} marker-end="url(#{m})"/>'


def text(x, y, s, cls="s", extra=""):
    return f'<text class="{cls}" x="{x:g}" y="{y:g}"{extra}>{h(say(s))}</text>'


# ---------------------------------------------------------------- sheet 1
def sheet1():
    k = "1"
    g = [f'<defs>{marker("a" + k)}{marker("r" + k, "rf")}</defs>']
    for x, s in ((120, "FRONT DOORS"), (380, "THE BRIDGE"), (675, "THE ROUTER"), (995, "WHAT COMES OUT")):
        g.append(text(x, 30, s, "hd mid"))
    doors = [("The page", "on the Mac and the phone"),
             ("Talk orb", "speak, and hear it answer"),
             ("Telegram bot", "text, voice notes, photos"),
             ("Brain Pen", "rewrites text in any app"),
             (AG.label(), "in the terminal or editor"),
             ("{Her} app repos", "report facts with tell.py")]
    ends = [174, 208, 242, 276, 310, 344]
    for i, (t, s) in enumerate(doors):
        y = 48 + i * 72
        g.append(box(20, y, 200, 60, t, [s]))
        g.append(arrow(f"M220,{y + 30} L288,{ends[i]}", mid=k))
    # local speech and the server
    g.append(box(290, 48, 180, 74, "Local speech", ["Whisper hears,", "Kokoro speaks"], ty=72))
    g.append(arrow("M380,124 L380,148", both=True, mid=k))
    g.append(text(390, 140, "hear + speak"))
    g.append(box(290, 150, 180, 210, "The server",
                 ["serve.py on this Mac", "port 7718", "", "takes every ask,", "from every door", "",
                  "runs no AI itself"], cls="bx2", ty=178))
    # router
    g.append(text(675, 98, "cheapest level first", "s mid"))
    tiers = [("1 · No model", ["instant and free", "lookups, notes, open a page"]),
             ("2 · One model call", [quick_models(_config()) + ", no tools",
                                     "spoken answers, rewording"]),
             (f"3 · Full {AG.short()} run", [f"{AG.label()}, sandboxed", "/today /brief /queue /wrap"])]
    for i, (t, ls) in enumerate(tiers):
        y = 110 + i * 116
        g.append(box(560, y, 230, 86, t, ls, ty=y + 26))
    g.append(arrow("M470,195 L558,155", mid=k))
    g.append(arrow("M470,255 L558,269", mid=k))
    g.append(arrow("M470,315 L558,383", mid=k))
    g.append(text(486, 222, "sorts"))
    g.append(text(486, 236, "each ask"))
    g.append(arrow("M775,198 L775,224", mid=k))
    g.append(arrow("M775,314 L775,340", mid=k))
    g.append(text(768, 216, "not enough", "s end"))
    g.append('<rect class="fence" x="548" y="332" width="254" height="146" rx="8"/>')
    g.append(text(558, 452, "sandbox: no network,", "s red"))
    g.append(text(558, 468, "writes only in the brain", "s red"))
    # outputs, her click, sent
    g.append(box(880, 150, 230, 90, "Outputs", ["today's plan, drafts,", "study guides, the pages"], ty=176))
    g.append('<path class="ln" d="M790,269 H830 V222 H878" marker-end="url(#a1)"/>')
    g.append('<path class="ln" d="M790,385 H830 V222"/>')
    g.append(text(836, 262, "writes"))
    g.append(box(880, 290, 170, 80, "{Her} click", ["one message at a time", "Touch ID for email"],
                 cls="gate", ty=316))
    g.append(arrow("M965,240 L965,288", red=True, mid=k))
    g.append(text(973, 268, "drafts wait here", "s red"))
    g.append(box(880, 410, 170, 50, "Sent", ["to one person"], ty=432))
    g.append(arrow("M965,370 L965,408", red=True, mid=k))
    g.append(arrow("M1085,498 L1085,242", mid=k))
    g.append('<text class="s mid" transform="translate(1102 370) rotate(-90)">pages rebuilt from the files</text>')
    # the folder
    g.append(box(290, 500, 810, 86, "The brain folder",
                 ["plain markdown: workstreams, people, next steps, plans, drafts",
                  "the journal inside it stays locked from unattended runs"], cls="bx2", tx=310, ty=528))
    g.append(arrow("M380,360 L380,498", mid=k))
    g.append(text(390, 440, "records every ask"))
    g.append(arrow("M760,480 L760,498", both=False, mid=k))
    g.append('<path class="ln" d="M760,430 L760,480"/>')
    g.append(text(768, 492, "reads + writes"))
    return g


# ---------------------------------------------------------------- sheet 2
CLOCK = ('<g class="ico"><circle cx="{x}" cy="{y}" r="7"/>'
         '<path d="M{x},{y} V{y4} M{x},{y} H{x3}"/></g>')
BOLT = ('<path class="ico-f" d="M{a},{b} L{c},{d} H{e} L{f},{g} L{i},{j} H{k} Z"/>')


def icon(kind, x, y):
    if kind == "clock":
        return CLOCK.format(x=x, y=y, y4=y - 4.5, x3=x + 3.5)
    if kind == "bolt":
        return (f'<path class="ico-f" d="M{x + 2},{y - 8} L{x - 4},{y + 1} H{x} '
                f'L{x - 2},{y + 8} L{x + 4},{y - 1} H{x} Z"/>')
    # manual: a finger pressing a button
    return (f'<g class="ico"><rect x="{x - 7}" y="{y + 1}" width="14" height="6" rx="2"/>'
            f'<path d="M{x},{y - 8} V{y - 2} M{x - 3},{y - 5} L{x},{y - 2} L{x + 3},{y - 5}"/></g>')


def sheet2():
    k = "2"
    g = [f'<defs>{marker("a" + k)}</defs>']
    tm = times(_config())
    night = ("nightly", tm["night"])
    recs = tm["recs"]
    rec_when = (f"{recs[0]} and", recs[1]) if len(recs) > 1 else ("daily at", recs[0])
    rows = [(60, "AREA"), (150, "BY HAND"), (252, "SKILL"), (270, "written once"),
            (356, "RUNS ITSELF")]
    for y, s in rows:
        g.append(text(12, y, s, "hd" if s.isupper() else "s"))
    cols = [
        ("PLANNING", ("plan", "my day"), "/today", "the day's three", "clock", ("daily", "07:00")),
        ("CATCHING UP", ("where do", "things stand"), "/brief", "status, inbox", "hand", ("a tile on", "the page")),
        ("THE QUEUE", ("do what", "I asked"), "/queue", "asks, done", "clock", night),
        ("CLOSING", ("fold the day", "back in"), "/wrap", "day into files", "clock", night),
        ("CAPTURE", ("empty", "my head"), "/dump", "ramble to tasks", "bolt", ("a voice note", "arrives")),
        ("RECORDINGS", ("file what", "was said"), "/transcribe", "audio to notes", "clock", rec_when),
        ("GOING OUT", ("what's on", "near me"), "/scout", "the events list", "clock", ("weekly,", "at night")),
        ("WRITING", ("write it", "as me"), "/write", "in {her} voice", "hand", ("manual on", "purpose")),
    ]
    for i, (area, task, cmd, what, trig, when) in enumerate(cols):
        x = 120 + i * 128
        cx = x + 60
        g.append(f'<rect class="bx" x="{x}" y="40" width="120" height="40" rx="4"/>')
        g.append(text(cx, 65, area, "ar mid"))
        g.append(arrow(f"M{cx},80 L{cx},118", mid=k))
        g.append(f'<rect class="bx" x="{x}" y="120" width="120" height="56" rx="4"/>')
        g.append(text(cx, 144, task[0], "tk mid"))
        g.append(text(cx, 161, task[1], "tk mid"))
        g.append(arrow(f"M{cx},176 L{cx},214", mid=k))
        g.append(f'<rect class="bx2" x="{x}" y="216" width="120" height="70" rx="4"/>')
        g.append(text(cx, 246, cmd, "cmd mid"))
        g.append(text(cx, 268, what, "s mid"))
        g.append(arrow(f"M{cx},286 L{cx},324", mid=k))
        cls = "bx dash" if trig == "hand" else "bx"
        g.append(f'<rect class="{cls}" x="{x}" y="326" width="120" height="56" rx="4"/>')
        g.append(icon(trig, x + 18, 354))
        g.append(text(x + 34, 350, when[0], "tk"))
        g.append(text(x + 34, 366, when[1], "tk"))
    # legend
    g.append(icon("clock", 128, 414) + text(142, 418, "on a schedule"))
    g.append(icon("bolt", 288, 414) + text(302, 418, "when something arrives"))
    g.append(icon("hand", 498, 414) + text(512, 418, "stays manual on purpose"))
    # her rules
    g.append(text(120, 462, "{HER} RULES OF THUMB", "hd"))
    rules = [("asked for three times", "→ it becomes a command"),
             ("anything that sends", "→ waits for {her} click"),
             ("unattended runs", "→ sandboxed, no code edits"),
             ("a new idea", "→ two weeks on the shelf first")]
    for i, (a, b) in enumerate(rules):
        x = 120 + i * 256
        g.append(f'<rect class="bx rule" x="{x}" y="474" width="247" height="62" rx="4"/>')
        g.append(text(x + 123.5, 500, a, "tk mid"))
        g.append(text(x + 123.5, 519, b, "tk mid"))
    return g


# ---------------------------------------------------------------- sheet 3
def sheet3():
    k = "3"
    g = [f'<defs>{marker("a" + k)}</defs>']
    g.append(box(460, 16, 220, 58, None, (), cls="bx2"))
    g.append(text(570, 43, "brain/", "cmd mid"))
    g.append(text(570, 62, "one folder of plain text", "s mid"))
    for zx in (180, 570, 960):
        g.append(f'<path class="ln" d="M570,74 V94 H{zx} V116" marker-end="url(#a3)"/>')
    zones = [
        (20, "COMING IN", "{she} drop{s} things here", [
            ("inbox.md", "a line, any time, triaged later"),
            ("queue/", "asks from page, Telegram, voice"),
            ("transcripts/", "recordings, turned into words"),
            ("synced.md", "read-only mirror of project folders"),
            ("files/", "uploads and photos")]),
        (410, "THE CORE", f"{AG.short()} keeps it organised", [
            ("workstreams.md", "every front: status, ball, next"),
            ("people.md", "who {she} keep{s} warm, and how often"),
            ("next.md · waiting.md", "the next hour; what others owe"),
            ("rooms/ · school/", "notes per project and per class"),
            ("decisions.md", "append-only; a new line reverses")]),
        (800, "GOING OUT", "plans and answers land here", [
            ("today.md", "the day's three, written at 07:00"),
            ("drafts/", "messages waiting for {her} send"),
            ("daily/", "one short digest per day"),
            ("the pages", "Today, Plate, People, Life, News"),
            ("graph.db", "a derived index, for recall")]),
    ]
    for zx, title, tag, files in zones:
        g.append(f'<rect class="zone" x="{zx}" y="118" width="320" height="392" rx="8"/>')
        g.append(text(zx + 160, 146, title, "ar mid"))
        g.append(text(zx + 160, 165, tag, "s mid"))
        for i, (fn, d) in enumerate(files):
            y = 184 + i * 64
            g.append(f'<rect class="bx" x="{zx + 20}" y="{y}" width="280" height="50" rx="4"/>')
            g.append(text(zx + 34, y + 21, fn, "fn"))
            g.append(text(zx + 34, y + 39, d))
    g.append(arrow("M340,314 L408,314", mid=k))
    g.append(text(374, 304, "triage", "s mid"))
    g.append(arrow("M730,314 L798,314", mid=k))
    g.append(text(764, 304, "writes", "s mid"))
    g.append(text(764, 332, "rebuilds", "s mid"))
    g.append(text(20, 540, f"HOW {AG.short().upper()} FINDS ITS WAY", "hd"))
    g.append(box(20, 552, 360, 58, "CLAUDE.md", ["the map, read every turn: which file for which task"],
                 tcls="fn", ty=575))
    g.append(box(390, 552, 360, 58, "reference/", ["the long why, loaded only when a task needs it"],
                 tcls="fn", ty=575))
    g.append(box(760, 552, 360, 58, "journal/", ["{her} words, locked from unattended runs"],
                 cls="gate", tcls="fn", ty=575))
    return g


# ---------------------------------------------------------------- sheet 4
def sheet4():
    g = []
    X0, X1, Y = 60, 1100, 170
    per_h = (X1 - X0) / 24

    def xh(hh):
        return X0 + hh * per_h
    # the night window: 23:00 to 06:00
    g.append(f'<rect class="band" x="{xh(23):.1f}" y="58" width="{X1 - xh(23):.1f}" height="196"/>')
    g.append(f'<rect class="band" x="{X0}" y="58" width="{xh(6) - X0:.1f}" height="196"/>')
    g.append(text(xh(3), 248, "night window", "s mid"))
    # sync ticks every 20 minutes
    for i in range(72):
        x = X0 + i * per_h / 3
        g.append(f'<line class="tick faint" x1="{x:.1f}" y1="{Y - 7}" x2="{x:.1f}" y2="{Y}"/>')
    g.append(f'<line class="ln" x1="{X0}" y1="{Y}" x2="{X1}" y2="{Y}"/>')
    for hh in range(25):
        x = xh(hh)
        g.append(f'<line class="tick" x1="{x:.1f}" y1="{Y}" x2="{x:.1f}" y2="{Y + 7}"/>')
        if hh % 3 == 0:
            g.append(text(x, Y + 22, f"{hh:02d}:00", "s mid"))
    g.append(text(xh(9.5), Y + 44, "a tick every 20 minutes: sync, and a saved version", "s"))
    cfg = _config()
    night = cfg.get("night") or {}
    recs = (cfg.get("recordings_auto") or {}).get("times") or ["12:30", "19:30"]
    upd = cfg.get("daily_update") or {}
    jobs = ", ".join(night.get("jobs") or ["queue", "wrap", "scout"])
    events = [(_hm(night.get("at"), "01:00"), "above", 96, "Night shift", jobs, "start"),
              (7, "below", 232, "Morning job", "the plan, news, a push to {her} phone", "mid")]
    if recs:
        events.append((_hm(recs[0], "12:30"), "above", 96, "Recordings",
                       "new voice memos transcribed", "mid"))
    if len(recs) > 1:
        events.append((_hm(recs[1], "19:30"), "above", 110, "Recordings", "the second pass", "end"))
    events.append((_hm(upd.get("at"), "20:30"), "below", 232, "Evening update",
                   "Telegram asks how it went", "mid"))
    events.append((_hm(upd.get("remind"), "22:30"), "above", 70, "Reminder",
                   "if the update is still open", "end"))
    for hh, pos, ty, title, sub, anchor in events:
        x = xh(hh)
        g.append(f'<circle class="dot" cx="{x:.1f}" cy="{Y}" r="4.5"/>')
        if pos == "above":
            g.append(f'<line class="ln" x1="{x:.1f}" y1="{Y - 5}" x2="{x:.1f}" y2="{ty + 22}"/>')
        else:
            g.append(f'<line class="ln" x1="{x:.1f}" y1="{Y + 5}" x2="{x:.1f}" y2="{ty - 16}"/>')
        ax = {"start": x - 4, "mid": x, "end": x + 4}[anchor]
        cls = {"start": "", "mid": " mid", "end": " end"}[anchor]
        g.append(text(ax, ty, title, "t" + cls))
        g.append(text(ax, ty + 17, sub, "s" + cls))
    # any time
    g.append(f'<path class="ln" d="M{xh(6)+6:.1f},276 H{xh(23)-6:.1f}"/>')
    g.append(f'<line class="ln" x1="{xh(6)+6:.1f}" y1="270" x2="{xh(6)+6:.1f}" y2="282"/>')
    g.append(f'<line class="ln" x1="{xh(23)-6:.1f}" y1="270" x2="{xh(23)-6:.1f}" y2="282"/>')
    g.append(text((xh(6) + xh(23)) / 2, 296, "any time {she} want{s}: the page, the talk orb, Telegram", "s mid"))
    return g


def day_label():
    cfg = _config()
    tm, upd = times(cfg), cfg.get("daily_update") or {}
    return (f"A 24-hour line with the night shift at {tm['night']}, the morning job at 07:00, "
            f"recordings at {' and '.join(tm['recs'])}, the evening update at "
            f"{upd.get('at') or '20:30'} and a reminder at {upd.get('remind') or '22:30'}.")


def svg(vb, label, parts, minw=880):
    return (f'<svg class="dg" viewBox="{vb}" role="img" aria-label="{h(say(label))}" '
            f'style="min-width:{minw}px">' + "".join(parts) + "</svg>")


SHEETS = [
    ("request", "A request, end to end",
     "Whatever door {she} use{s}, the ask reaches the same small server on {her} Mac, and the "
     "server runs no AI of its own. It passes each ask to the cheapest level that can answer "
     "it: a lookup in the files, then a single model call with no tools, then a full Claude Code run "
     "inside a sandbox. Anything meant for another person stops as a draft until {she} click{s} send.",
     lambda: svg("0 0 1140 610", "Six front doors lead to one server, which routes each ask to one of "
         "three levels; every level reads and writes the brain folder, and drafts wait for {her} "
         "click before anything is sent.", sheet1()),
     "Asks flow left to right and every write lands in the folder at the bottom. Red marks the "
     "sandbox around full runs and the one step only {she} can take."),
    ("skills", "The skill backbone",
     "Every area of {her} life produces the same few chores. Once {she} {has} asked for the same kind "
     "of thing three times, it gets written down once as a command, and Claude runs the command "
     "from then on. The reliable ones now start on a schedule or when something arrives, and "
     "writing for other people stays manual on purpose.",
     lambda: svg("0 0 1140 550", "Eight areas, each with a chore done by hand, the command that replaced "
         "it, and what starts that command now.", sheet2()),
     "Read each column top to bottom: the area, the chore in {her} words, the command, and what "
     "starts it."),
    ("memory", "Where it all lives",
     "Everything is plain text in one folder, so {she} can open any file and git keeps every "
     "version. Things come in on the left, Claude keeps the middle in order, and plans and "
     "drafts come out on the right. CLAUDE.md is the map Claude reads on every turn, which "
     "is how it knows which file to open for a task without searching the whole folder.",
     lambda: svg("0 0 1140 624", AG.say("The brain folder in three zones: files coming in, the core Claude "
         "keeps organised, and what goes out, with the map and the private journal below."),
         sheet3()),
     "The journal is the one place unattended runs cannot read."),
    ("day", "A day on its own",
     "Most of the upkeep happens while {she} sleep{s} or work{s}. The night shift clears the queue and "
     "folds the day in, the morning job writes the plan before {she} {is} up, and new voice memos "
     "are transcribed on the Mac twice a day. Every twenty minutes the brain syncs {her} project "
     "folders and saves a version.",
     lambda: svg("0 0 1140 310", day_label(), sheet4()),
     "Times come from {her} own settings. The shaded bands are the night window, the only "
     "hours the night shift may run."),
]

CSS = r"""
:root{
  --paper:#e9eef4; --sheet:#f6f8fb; --ink:#15365f; --ink2:#4e6a8d; --grid:#dce4ee;
  --grid2:#cbd7e5; --zone:#e1e8f1; --rule:#9fb2c9; --red:#b53a1f; --band:#dbe3ee;
  color-scheme:light;
}
@media (prefers-color-scheme:dark){
  :root:not([data-theme="light"]){
    --paper:#0d2a4d; --sheet:#10325a; --ink:#e3ecf6; --ink2:#a0b7d3; --grid:#133660;
    --grid2:#1a416f; --zone:#12375f; --rule:#3b6190; --red:#ff8d6f; --band:#123a66;
    color-scheme:dark;
  }
}
:root[data-theme="dark"]{
  --paper:#0d2a4d; --sheet:#10325a; --ink:#e3ecf6; --ink2:#a0b7d3; --grid:#133660;
  --grid2:#1a416f; --zone:#12375f; --rule:#3b6190; --red:#ff8d6f; --band:#123a66;
  color-scheme:dark;
}
*{box-sizing:border-box}
body{
  background-color:var(--paper);
  background-image:
    linear-gradient(var(--grid2) 1px,transparent 1px),linear-gradient(90deg,var(--grid2) 1px,transparent 1px),
    linear-gradient(var(--grid) 1px,transparent 1px),linear-gradient(90deg,var(--grid) 1px,transparent 1px);
  background-size:60px 60px,60px 60px,12px 12px,12px 12px;
  color:var(--ink); font:16px/1.62 "IBM Plex Sans",system-ui,-apple-system,sans-serif;
  padding-inline:20px;
}
.wrap{max-width:1180px;margin:0 auto;padding-block:44px 72px}
.tb{display:grid;grid-template-columns:1fr 320px;gap:28px;align-items:end;
  border-bottom:2px solid var(--ink);padding-bottom:26px}
.eyebrow,.sheet-no,.tb-block dt{font-family:"IBM Plex Mono",ui-monospace,monospace;font-size:11.5px;
  letter-spacing:.16em;text-transform:uppercase;color:var(--ink2);margin:0}
h1{font-family:"IBM Plex Sans Condensed","IBM Plex Sans",sans-serif;font-weight:600;
  font-size:clamp(40px,6vw,64px);line-height:1.02;letter-spacing:.01em;text-transform:uppercase;
  margin:10px 0 16px;text-wrap:balance}
.lede{max-width:64ch;margin:0;color:var(--ink)}
.tb-block{margin:0;border:1.5px solid var(--ink);background:var(--sheet);
  display:grid;grid-template-columns:auto 1fr}
.tb-block dt,.tb-block dd{padding:7px 12px;border-bottom:1px solid var(--rule)}
.tb-block dd{margin:0;font-family:"IBM Plex Mono",ui-monospace,monospace;font-size:13px;
  border-left:1px solid var(--rule);font-variant-numeric:tabular-nums}
.tb-block dt:nth-last-of-type(1),.tb-block dd:nth-last-of-type(1){border-bottom:0}
nav.toc{display:flex;flex-wrap:wrap;gap:8px 18px;margin:22px 0 0;
  font-family:"IBM Plex Mono",ui-monospace,monospace;font-size:13px}
nav.toc a{color:var(--ink);text-decoration:none;border-bottom:1px solid var(--rule);padding-bottom:1px}
nav.toc a:hover,nav.toc a:focus-visible{border-color:var(--ink)}
a:focus-visible{outline:2px solid var(--red);outline-offset:3px}
.sheet{margin-top:56px}
.sheet-head{display:flex;align-items:baseline;gap:16px;flex-wrap:wrap}
h2{font-family:"IBM Plex Sans Condensed","IBM Plex Sans",sans-serif;font-weight:600;
  font-size:clamp(24px,3vw,32px);letter-spacing:.02em;text-transform:uppercase;margin:4px 0 10px;
  text-wrap:balance}
.sheet-text{max-width:66ch;margin:0 0 18px}
figure{margin:0;border:1.5px solid var(--ink);background:var(--sheet);position:relative}
figure::before,figure::after{content:"";position:absolute;width:14px;height:14px;
  border-color:var(--ink2);border-style:solid;pointer-events:none}
figure::before{top:-7px;left:-7px;border-width:0 1.5px 1.5px 0;opacity:.7}
figure::after{bottom:-7px;right:-7px;border-width:1.5px 0 0 1.5px;opacity:.7}
.scroll{overflow-x:auto;padding:18px 16px 10px}
figcaption{border-top:1px solid var(--rule);padding:10px 16px;font-size:14px;color:var(--ink2);
  max-width:100%}
.dg{display:block;width:100%;height:auto;color:var(--ink)}
.dg text{fill:currentColor;font-family:"IBM Plex Mono",ui-monospace,monospace;font-size:11.5px}
.dg .t{font-family:"IBM Plex Sans Condensed","IBM Plex Sans",sans-serif;font-weight:600;font-size:15.5px}
.dg .s{fill:var(--ink2);font-size:11px}
.dg .hd{fill:var(--ink2);font-size:11px;letter-spacing:.16em}
.dg .ar{font-family:"IBM Plex Sans Condensed","IBM Plex Sans",sans-serif;font-weight:600;
  font-size:13px;letter-spacing:.08em}
.dg .tk{font-size:11.5px}
.dg .cmd{font-size:14.5px;font-weight:600}
.dg .fn{font-size:13px;font-weight:600}
.dg .red{fill:var(--red)}
.dg .mid{text-anchor:middle}
.dg .end{text-anchor:end}
.dg .bx{fill:var(--sheet);stroke:currentColor;stroke-width:1.2}
.dg .bx2{fill:var(--sheet);stroke:currentColor;stroke-width:2.2}
.dg .dash{stroke-dasharray:5 4}
.dg .rule{stroke:var(--rule)}
.dg .zone{fill:var(--zone);stroke:var(--rule);stroke-width:1}
.dg .gate{fill:var(--sheet);stroke:var(--red);stroke-width:2}
.dg .fence{fill:none;stroke:var(--red);stroke-width:1.4;stroke-dasharray:6 4}
.dg .ln{fill:none;stroke:currentColor;stroke-width:1.3}
.dg .ln-red{fill:none;stroke:var(--red);stroke-width:1.6}
.dg .rf{fill:var(--red)}
.dg .ico{fill:none;stroke:currentColor;stroke-width:1.4;stroke-linecap:round}
.dg .ico-f{fill:currentColor}
.dg .tick{stroke:var(--ink2);stroke-width:1}
.dg .faint{opacity:.55}
.dg .dot{fill:currentColor}
.dg .band{fill:var(--band)}
footer{margin-top:52px;padding-top:16px;border-top:1px solid var(--rule);
  font-family:"IBM Plex Mono",ui-monospace,monospace;font-size:12px;color:var(--ink2);
  display:flex;flex-wrap:wrap;gap:6px 20px;justify-content:space-between}
@media (max-width:760px){
  .tb{grid-template-columns:1fr}
  .scroll{padding:14px 12px 8px}
}
"""


def page():
    global P
    cfg = _config()
    P = pronouns(cfg)
    who = str(cfg.get("owner") or "").strip()
    who = who[:-2] if who.endswith(("'s", "’s")) else who
    # "My brain" is the default header, not a name.
    who = "" if who.lower() in ("my", "your") else who
    n = numbers()
    today = date.today()
    fronts = (f"{n['fronts']} · {n['live']} live" if n["fronts"] is not None else "n/a")
    checks = (f"{n['checks']}, " + ("all passing" if n["ok"] else "some failing")
              if n["checks"] else "n/a")
    toc = "".join(f'<a href="#{sid}">{i + 1} · {h(t)}</a>' for i, (sid, t, *_r) in enumerate(SHEETS))
    body = []
    for i, (sid, title, para, fig, cap) in enumerate(SHEETS):
        body.append(
            f'<section class="sheet" id="{sid}" aria-labelledby="{sid}-h">'
            f'<div class="sheet-head"><p class="sheet-no">Sheet {i + 1} of {len(SHEETS)}</p>'
            f'<h2 id="{sid}-h">{h(title)}</h2></div>'
            f'<p class="sheet-text">{h(say(AG.say(para)))}</p>'
            f'<figure><div class="scroll">{fig()}</div><figcaption>{h(say(AG.say(cap)))}</figcaption></figure>'
            "</section>")
    return f"""<title>Life Brain Blueprints</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;600&family=IBM+Plex+Sans+Condensed:wght@600&family=IBM+Plex+Sans:wght@400;500&display=swap">
<style>{CSS}</style>
<div class="wrap">
<header class="tb">
  <div>
    <p class="eyebrow">Working drawings</p>
    <h1>Life Brain Blueprints</h1>
    <p class="lede">These drawings show how {(h(who) + "'s") if who else "this"} life brain works: a folder of plain text, a
    small server on {P["her"]} Mac and a set of {AG.label()} commands that keep every area of
    {P["her"]} life moving{(": " + h(areas())) if areas() else ""}. Each sheet answers one question,
    from how a single ask travels to what runs while {P["she"]} sleep{P["s"]}.</p>
    <nav class="toc" aria-label="Sheets">{toc}</nav>
  </div>
  <dl class="tb-block">
    <dt>Drawn for</dt><dd>{h(who) or "its owner"}</dd>
    <dt>Date</dt><dd>{today.day} {today:%b %Y}</dd>
    <dt>Scale</dt><dd>not to scale</dd>
    <dt>Fronts</dt><dd>{h(fronts)}</dd>
    <dt>Commands</dt><dd>{n['commands']}</dd>
    <dt>Self-checks</dt><dd>{h(checks)}</dd>
  </dl>
</header>
{''.join(body)}
<footer><span>Life brain · working drawings · drawn {today.isoformat()}</span><span>Red marks what only {P["she"]} can do</span></footer>
</div>
"""


EXPORT_JS = r"""
const { chromium } = require(process.argv[2]);
const [,, , exe, html, outdir] = process.argv;
(async () => {
  const b = await chromium.launch({ executablePath: exe });
  for (const scheme of ['light', 'dark']) {
    const p = await (await b.newContext({ viewport: { width: 1280, height: 900 },
      deviceScaleFactor: 2, colorScheme: scheme })).newPage();
    await p.goto('file://' + html); await p.waitForTimeout(1200);
    const figs = await p.$$('figure');
    for (let i = 0; i < figs.length; i++)
      await figs[i].screenshot({ path: `${outdir}/sheet-${i + 1}-${scheme}.png` });
    if (scheme === 'light')
      await p.pdf({ path: `${outdir}/life-brain-blueprints.pdf`, width: '1280px',
                    printBackground: true, margin: { top: '24px', bottom: '24px' } });
  }
  await b.close();
})().catch(e => { console.error(e.message); process.exit(1); });
"""


def export():
    """PDF (light) and one PNG per sheet in both themes, via headless Chrome.
    Returns a line saying what happened."""
    pw = os.path.expanduser("~/.claude/skills/gstack/node_modules/playwright-core")
    shells = sorted(glob.glob(os.path.expanduser(
        "~/Library/Caches/ms-playwright/chromium_headless_shell-*/"
        "chrome-headless-shell-mac-arm64/chrome-headless-shell")))
    if not (os.path.isdir(pw) and shells):
        return "export skipped: no headless Chrome on this Mac"
    import tempfile
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as f:
        f.write(EXPORT_JS)
        js = f.name
    try:
        r = subprocess.run(["node", js, pw, shells[-1], OUT, OUTDIR],
                           capture_output=True, text=True, timeout=180)
    finally:
        os.remove(js)
    if r.returncode != 0:
        return "export failed: " + (r.stderr or r.stdout).strip()[:200]
    return "exported the PDF and a PNG per sheet, light and dark"


if __name__ == "__main__":
    os.makedirs(OUTDIR, exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(page())
    print(os.path.relpath(OUT, ROOT), os.path.getsize(OUT) // 1024, "KB")
    if "--export" in sys.argv:
        print(export())

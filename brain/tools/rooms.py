#!/usr/bin/env python3
"""Build brain/rooms.html — the projects level: wings and rooms.

    python3 brain/tools/rooms.py

GENERATED. The brain has two altitudes: Today (what do I do right now) and
the map (everything at once). This page is the missing middle: one room per
real project, grouped under the wings of your life. A room is a place you
enter to work, not a list you scan — it holds the project's tasks (tickable),
its people, its files and docs from the other repo, its own notes that ride
into every Claude session there, and the doors to "ask about this" and "run
a session in the repo" without re-explaining anything.

The wings and rooms live in config.json under "rooms", so rearranging your
life needs no code. Workstreams the config doesn't claim are pulled in by
name where the match is obvious, and named honestly on the floor plan where
it isn't — nothing silently disappears.
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

import md as MD        # noqa: E402  (task keys, shared with the server)
import model as M
import chrome as CHROME      # noqa: E402
import build as B      # noqa: E402  (shared palette, queue outcomes)
import tour as T       # noqa: E402  (the guided walkthrough)
import talk as K       # noqa: E402  (dictation on Claude-facing inputs)
import sync as S       # noqa: E402  (folder freshness helpers)

BRAIN = M.BRAIN
OUT = os.path.join(BRAIN, "rooms.html")
TODAY = date.today()

# Worst state first — a room wears the loudest state of its workstreams.
STATE_ORDER = ["overdue", "chase", "cold", "soon", "waiting", "moving"]


def cfg():
    try:
        with open(os.path.join(BRAIN, "config.json"), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def state_of(w):
    """Same vocabulary as the map, so a project never wears two colours."""
    if not w["live"]:
        return "closed"
    if w["overdue"] or w.get("task_overdue") or w.get("task_urgent") \
            or w.get("urgent_name") or w.get("room_urgent") \
            or w.get("goal_overdue"):
        return "overdue"
    if w["chase"]:
        return "chase"
    if w["cold"] or w["never_touched"]:
        return "cold"
    if w["due_soon"] or w.get("task_due_soon"):
        return "soon"
    if w["ball"] == "them":
        return "waiting"
    return "moving"


def ago_label(d):
    """'today', 'Tuesday', '12 days ago' — how a person says a date."""
    if not d:
        return ""
    try:
        dd = date.fromisoformat(str(d)[:10])
    except ValueError:
        return str(d)
    n = (date.today() - dd).days
    if n <= 0:
        return "today"
    if n == 1:
        return "yesterday"
    if n < 7:
        return dd.strftime("%A")
    return f"{n} days ago"


def git_pulse(path):
    """Last commit + the last five subjects — the honest 'is this alive'."""
    if not os.path.isdir(os.path.join(path, ".git")):
        return None
    try:
        r = subprocess.run(["git", "-C", path, "log", "-5",
                            "--format=%cs%x09%s"],
                           capture_output=True, text=True, timeout=8)
        if r.returncode != 0 or not r.stdout.strip():
            return None
        subs = []
        for line in r.stdout.strip().splitlines():
            d, _, s = line.partition("\t")
            subs.append([d, s[:110]])
        return {"last": subs[0][0], "subs": subs}
    except Exception:
        return None


def ship_state(src, expanded):
    """How far the build you gave people trails the code: the source's
    ship_marker file names the delivered commit (Satio's .claude/last-apk.txt),
    and git counts what testers haven't seen."""
    marker = (src or {}).get("ship_marker")
    if not marker or not expanded:
        return None
    try:
        with open(os.path.join(expanded, marker), encoding="utf-8") as f:
            head = f.read(300)
    except OSError:
        return None
    m = re.search(r"\b[0-9a-f]{7,40}\b", head)
    if not m:
        return None
    try:
        r = subprocess.run(["git", "-C", expanded, "rev-list", "--count",
                            m.group(0) + "..HEAD"],
                           capture_output=True, text=True, timeout=8)
        if r.returncode == 0 and r.stdout.strip().isdigit():
            return {"behind": int(r.stdout.strip())}
    except Exception:
        pass
    return None


def handoff_for(expanded):
    """What the project's own brain says about itself, in fifteen lines.

    A repo that runs the brain-kit generates `brain/handoff.md` beside its
    page — the worry headline, its top open actions, how many decisions are
    blocked on her, how many hand-checks are unconfirmed. Reading it here is
    what makes a room show the project's real state instead of only the state
    of the workstream she keeps about it.

    Deliberately a dumb reader of a generated file: it holds no opinion, and a
    project without a brain simply gets nothing. The upward half of this lives
    in each repo (`brain/tools/handoff.py`) and is the only thing allowed to
    write that file."""
    if not expanded:
        return None
    fp = os.path.join(expanded, "brain", "handoff.md")
    try:
        with open(fp, encoding="utf-8", errors="replace") as f:
            text = f.read()
    except OSError:
        return None

    def after(head):
        m = re.search(rf"^##\s+{head}\s*$(.*?)(?=^##\s|\Z)", text,
                      re.S | re.M | re.I)
        return (m.group(1).strip() if m else "")

    m = re.search(r"^\*\*What should worry you:\*\*\s*(.+)$", text, re.M)
    worry = m.group(1).strip() if m else ""

    nxt = []
    for line in after("Next here").split("\n"):
        m2 = re.match(r"^\s*[-*]\s+\[ \]\s+(.*)$", line)
        if m2 and m2.group(1).strip():
            t = m2.group(1).strip()
            yours = "(yours, not claude's)" in t.lower()
            t = re.sub(r"\s*\(yours, not Claude's\)\s*$", "", t, flags=re.I)
            nxt.append({"t": t[:120], "yours": yours})

    def count(head):
        m3 = re.match(r"^(\d+)\b", after(head))
        return int(m3.group(1)) if m3 else 0

    mu = re.search(r"^updated:\s*(\S+)", text, re.M)
    return {
        "updated": mu.group(1) if mu else "",
        "worry": worry[:200], "next": nxt[:4],
        "questions": count("Waiting on you"),
        "checks": count("Owed on your phone"),
        "page": os.path.isfile(os.path.join(expanded, "brain", "index.html")),
    }


def convos_for(srcname):
    """The live Claude conversations happening in this room.

    The Sessions page has always known which room a conversation belongs to —
    `snapshot()` takes a source-name-to-room map. The room knew nothing back,
    so a thread paused on a one-line question was invisible from the one page
    that claims to be the project's cockpit. Same join key both ways: a
    conversation stores the config source's name, a room stores it as
    `srcname`.

    Baked into the page for the floor plan's benefit and refreshed live once
    a room is open — a conversation's state changes on its own schedule, and
    nothing rebuilds this page when it does.
    """
    if not srcname:
        return []
    try:
        with open(os.path.join(BRAIN, "sessions.json"), encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return []
    hands = data.get("hands") or {}
    out = []
    for c in (data.get("convos") or []):
        if c.get("ended") or c.get("src") != srcname:
            continue
        out.append({
            "id": c.get("id") or "",
            "topic": (c.get("topic") or "New conversation")[:80],
            "state": c.get("state") or "quiet",
            "line": (c.get("line") or "")[:120],
            "question": (c.get("question") or "")[:220],
            "hands": hands.get(c.get("path") or "") == c.get("id"),
            "last": c.get("last") or "",
        })
    # newest first, then paused-on-a-question to the top: it is the only one
    # that needs her. Two stable passes, so the order inside each group holds.
    out.sort(key=lambda c: c["last"], reverse=True)
    out.sort(key=lambda c: c["state"] != "ask")
    return out[:6]


# Docs worth docking, in the order a reader wants them.
DOC_FIRST = ["CLAUDE.md", "README.md", "TODO.md", "TODOS.md", "AGENTS.md",
             "DECISIONS.md"]


def docs_for(src):
    """The repo's own brain, docked read-only: its key files, brain/ pages
    and PLAN files — listed here, rendered on demand, their repo stays the
    source of truth. Each doc carries its count of unticked checkboxes, so
    'all clear' can never hide a live TODO list."""
    base = os.path.expanduser(src.get("path", ""))
    if not os.path.isdir(base):
        return [], 0
    out, seen = [], set()

    def add(rel):
        if rel in seen or len(out) >= 16:
            return
        fp = os.path.join(base, rel)
        if not os.path.isfile(fp):
            return
        seen.add(rel)
        try:
            size = os.path.getsize(fp)
            d = date.fromtimestamp(os.path.getmtime(fp)).isoformat()
        except OSError:
            size, d = 0, ""
        n = 0
        if 0 < size <= 512_000:
            try:
                with open(fp, encoding="utf-8", errors="replace") as f:
                    for line in f:
                        if re.match(r"^\s*[-*]\s+\[ \]\s+", line):
                            n += 1
            except OSError:
                pass
        # "live" is the only reason a file deserves the reader's eye on
        # arrival: it moved this week, or it is holding unticked work. File
        # size never told her anything, so it isn't carried at all.
        age = None
        if d:
            try:
                age = (TODAY - date.fromisoformat(d)).days
            except ValueError:
                age = None
        out.append({"f": rel, "d": d, "n": n,
                    "live": bool(n) or (age is not None and age <= 7)})

    for rel in (src.get("files") or []):
        add(rel)
    for fn in DOC_FIRST:
        add(fn)
    # The repo's own brain/ pages outrank the PLAN pile — they are the
    # distilled truth, the PLANs are the working papers.
    bdir = os.path.join(base, "brain")
    if os.path.isdir(bdir):
        try:
            for fn in sorted(os.listdir(bdir)):
                if fn.endswith(".md"):
                    add("brain/" + fn)
        except OSError:
            pass
    try:
        top = sorted(os.listdir(base))
    except OSError:
        top = []
    for fn in top:
        if fn.startswith("PLAN") and fn.endswith(".md"):
            add(fn)
    more = max(0, sum(1 for fn in top if fn.endswith(".md")
                      and not fn.startswith(".")) - sum(
                          1 for o in out if "/" not in o["f"]))
    return out, more


def transcripts_for(slug):
    """Recordings transcribed into this room. The meeting is IN the brain once
    transcribe.py has run; this is where she reads it and turns it into
    work — newest first, capped, summarised-or-raw stated plainly."""
    tdir = os.path.join(BRAIN, "transcripts")
    if not os.path.isdir(tdir):
        return []
    out = []
    for fn in sorted(os.listdir(tdir), reverse=True):
        if not fn.endswith(".md"):
            continue
        fp = os.path.join(tdir, fn)
        try:
            with open(fp, encoding="utf-8", errors="replace") as f:
                txt = f.read(200_000)
        except OSError:
            continue
        m = re.search(r"^room:\s*(.+)$", txt[:600], re.M)
        if not m or m.group(1).strip() != slug:
            continue
        mm = re.search(r"^minutes:\s*([\d.]+)", txt[:600], re.M)
        try:
            d = date.fromtimestamp(os.path.getmtime(fp)).isoformat()
        except OSError:
            d = ""
        out.append({"f": fn, "d": d,
                    "mins": int(float(mm.group(1))) if mm else 0,
                    "read": "## What this was" in txt})
    return out[:8]


def build():
    config = cfg()
    items = M.load(cfg=config)
    people = M.load_people()
    habits = M.load_habits()
    goals_all = M.load_goals()
    pdays = {p["name"]: p["days_since"] for p in people}
    sources = {s.get("name"): s for s in (config.get("sources") or [])}
    by_name = {w["name"]: w for w in items}
    wings_cfg = ((config.get("rooms") or {}).get("wings")) or []

    # People a workstream touches: the hand links, then every field a name
    # can hide in. Same scan the map does.
    pnames = sorted((p["name"] for p in people if len(p["name"]) >= 3),
                    key=len, reverse=True)

    def ws_people(w):
        found = list(w.get("linked_people", []))
        hay = " ".join([w["name"], w.get("ball_who") or "",
                        w.get("next_action") or "", w.get("why") or ""]
                       + [t["text"] for t in w["tasks"] if not t["done"]])
        for nm in pnames:
            if nm not in found and M.name_in(nm, hay):
                found.append(nm)
        return found[:8]

    # ---- claim workstreams into rooms --------------------------------------
    claimed = {}
    room_specs = []          # (wing_name, rcfg, slug, ws_names)
    for wing in wings_cfg:
        for rcfg in (wing.get("rooms") or []):
            sl = rcfg.get("slug") or M.room_slug(rcfg.get("name", ""))
            ws_names = [n for n in (rcfg.get("ws") or []) if n in by_name]
            for n in ws_names:
                claimed[n] = sl
            room_specs.append((wing.get("name", ""), rcfg, sl, ws_names))

    # Pull-in pass: an unclaimed live workstream whose name contains a room's
    # obvious token ("URGENT: TapGate invitation…" → the TapGate room) joins
    # that room; the longest token wins so "tapgate" beats "gate".
    def toks(s):
        return {t for t in re.split(r"[^a-z0-9]+", (s or "").lower())
                if len(t) >= 4}

    room_tokens = []
    for wname, rcfg, sl, ws_names in room_specs:
        tk = toks(rcfg.get("name", ""))
        for n in ws_names:
            tk |= toks(n)
        tk -= {"urgent", "with", "after", "from", "help", "system",
               "invitation", "tasks", "direction", "admin", "events",
               "upcoming", "personal", "renovations", "being", "there",
               "finish", "host", "decide", "live", "december", "school"}
        room_tokens.append((sl, tk))
    for w in items:
        if not w["live"] or w["name"] in claimed:
            continue
        wl = w["name"].lower()
        best, blen = None, 0
        for sl, tk in room_tokens:
            for t in tk:
                if t in wl and len(t) > blen:
                    best, blen = sl, len(t)
        if best:
            claimed[w["name"]] = best
            for wname, rcfg, sl, ws_names in room_specs:
                if sl == best:
                    ws_names.append(w["name"])
    leftovers = [w["name"] for w in items if w["live"]
                 and w["name"] not in claimed]

    # ---- Claude's finished work, delivered to the room it belongs to -------
    q = B.queue_items()
    cutoff = 7

    def room_folds(room_name, ws_names):
        want = [t for n in ([room_name] + ws_names) for t in B._sig_tokens(n)]
        folds = []
        for it in q:
            if it["status"] != "done" or not it["outcome"].strip():
                continue
            try:
                agedays = (date.today()
                           - date.fromisoformat(it["created"])).days
            except ValueError:
                agedays = 99
            if agedays > cutoff:
                continue
            blob = (it["title"] + " " + it["body"]).lower()
            explicit = {m.group(1) for m in re.finditer(
                r'workstream\s+[“"]([^”"]+)[”"]', it["title"] + " "
                + it["body"] + " " + it["outcome"])}
            hit = bool(explicit & set(ws_names))
            if not hit:
                shared = [t for t in want if t in blob]
                hit = len(shared) >= 2 or any(len(t) >= 6 for t in shared)
            if hit:
                folds.append({"title": it["title"][:90],
                              "date": it["created"],
                              "html": MD.render(it["outcome"])})
            if len(folds) >= 3:
                break
        return folds

    # ---- assemble ----------------------------------------------------------
    wings, rooms = [], []
    for wing in wings_cfg:
        wname = wing.get("name", "")
        slugs, quiet = [], 0
        for wn2, rcfg, sl, ws_names in room_specs:
            if wn2 != wname:
                continue
            slugs.append(sl)
            name = rcfg.get("name", "")
            wss = [w for w in items if w["name"] in set(ws_names)]
            src = sources.get(rcfg.get("source") or "")
            path = (src or {}).get("path", "")
            expanded = os.path.expanduser(path) if path else ""

            # state: the loudest member state; open work; the one next thing
            states = [state_of(w) for w in wss if w["live"]]
            state = next((s for s in STATE_ORDER if s in states),
                         "moving" if states else "quiet")
            open_n = sum(w["open_tasks"] for w in wss if w["live"])
            done_n = sum(w["done_tasks"] for w in wss)
            touched = max((w["touched"] for w in wss if w["touched"]),
                          default="")
            top = next((w for w in wss if w["live"]), None)
            nxt = ""
            if top:
                nxt = top["next_action"] or top["next_due_task"] or ""
                if not nxt:
                    for t in top["tasks"]:
                        if not t["done"] and not t.get("parked") \
                                and not t.get("dropped"):
                            nxt = t["text"]
                            break
            ball = ""
            if top and top["ball"] == "them":
                ball = "ball with " + (top["ball_who"] or "them")
            elif top and top["ball"] == "me":
                ball = "ball with you"

            # freshness for the pulse + the wing health line
            pulse = git_pulse(expanded) if expanded else None
            changed = ""
            if not pulse and expanded and os.path.isdir(expanded):
                mt = S.newest_mtime(expanded)
                if mt:
                    changed = date.fromtimestamp(mt).isoformat()
            last_alive = max([d for d in (
                touched, (pulse or {}).get("last", ""), changed) if d],
                default="")
            alive_days = None
            if last_alive:
                try:
                    alive_days = (date.today()
                                  - date.fromisoformat(last_alive[:10])).days
                except ValueError:
                    alive_days = None
            if rcfg.get("habits"):
                pass                       # the habits room is never "quiet"
            elif alive_days is None or alive_days >= 14:
                quiet += 1

            # merged open tasks, loudest first, capped
            tasks = []
            for w in wss:
                if not w["live"]:
                    continue
                for t in w["tasks"]:
                    if t["done"] or t.get("parked") or t.get("dropped"):
                        continue
                    tasks.append({"t": t["text"], "k": MD.taskkey(t["text"]),
                                  "dd": t.get("due_days"),
                                  "u": bool(t.get("urgent")),
                                  "ws": w["name"]})
            tasks.sort(key=lambda t: (not t["u"],
                                      9e9 if t["dd"] is None else t["dd"]))
            tasks = tasks[:10]

            # People, with what they ARE to this project ("Dad (tester)")
            # and how recently you actually heard from them — people.md's
            # Last dates, kept true by the Beeper sync, for free.
            proles = {}
            for w in wss:
                proles.update(w.get("people_roles") or {})
            ppl = []
            for w in wss:
                for nm in ws_people(w):
                    if nm not in [p2["n"] for p2 in ppl]:
                        ppl.append({"n": nm, "role": proles.get(nm, ""),
                                    "days": pdays.get(nm)})
            ppl = ppl[:8]

            # The finish lines: goals.md headings name rooms (or their
            # workstreams — both work).
            gsrc = list(goals_all.get(name.strip().lower(), []))
            for wsn in ws_names:
                for g in goals_all.get(wsn.strip().lower(), []):
                    if g["text"] not in [x["text"] for x in gsrc]:
                        gsrc.append(g)
            goals = [{"t": g["text"],
                      "k": MD.taskkey(re.sub(r"\s*\(urgent\)", "", g["text"],
                                             flags=re.I)),
                      "dd": g["days_to_due"], "done": g["done"],
                      "label": g["due_label"], "over": g["overdue"]}
                     for g in gsrc]
            g_undone = [g for g in goals if not g["done"]]
            g_dated = sorted([g for g in g_undone if g["dd"] is not None],
                             key=lambda g: g["dd"])
            next_goal = None
            if g_dated:
                next_goal = {"t": g_dated[0]["t"][:60], "dd": g_dated[0]["dd"]}
            elif g_undone:
                next_goal = {"t": g_undone[0]["t"][:60], "dd": None}
            if any(g["over"] for g in g_undone):
                state = "overdue"

            docs, more = docs_for(src) if src else ([], 0)
            hoff = handoff_for(expanded)
            convos = convos_for((src or {}).get("name", ""))
            asking = [c for c in convos if c["state"] == "ask"]
            notes = ""
            try:
                with open(os.path.join(BRAIN, "rooms", sl + ".md"),
                          encoding="utf-8") as f:
                    notes = f.read().rstrip()
            except OSError:
                pass

            hab = None
            if rcfg.get("habits"):
                state = "moving"
                hab = [{"name": h["name"], "count": h["week_count"],
                        "target": h["target"], "done": h["done_today"],
                        "ok": h["on_track"]} for h in habits]
                on = sum(1 for h2 in hab if h2["ok"])
                nxt = f"{on} of {len(hab)} habits on track this week" \
                    if hab else "no habits tracked yet"

            # The card's one line — and it must not lie: a room whose
            # workstream is clear but whose folder holds a live TODO list
            # says so instead of "all clear".
            funticked = sum(d2.get("n", 0) for d2 in docs)
            parts = []
            if open_n:
                parts.append(f"{open_n} open")
            elif funticked:
                parts.append(f"{funticked} unticked in its folder")
            elif wss:
                parts.append("all clear")
            if touched:
                parts.append("touched " + ago_label(touched))
            if ball:
                parts.append(ball)
            # A decision blocked on her is the most expensive kind of stall —
            # the project cannot move and nothing in her workstream says so.
            if hoff and hoff["questions"]:
                parts.append(f"{hoff['questions']} for you to decide")
            # Same stall, arriving from the other page: a conversation that
            # asked something and stopped. A minute of hers restarts a thread.
            if asking:
                parts.append(f"{len(asking)} conversation"
                             + ("s" if len(asking) > 1 else "")
                             + " waiting on you")
            if not parts:
                # a room with no workstream still says how alive it is
                if pulse:
                    parts.append("last commit " + ago_label(pulse["last"]))
                elif changed:
                    parts.append("a file changed " + ago_label(changed))
                if not wss and (pulse or changed):
                    parts.append("no workstream yet")
            stateline = " · ".join(parts)

            rooms.append({
                "slug": sl, "name": name, "wing": wname, "state": state,
                "open": open_n, "done": done_n, "stateline": stateline,
                "next": nxt[:120], "tasks": tasks, "people": ppl,
                "wss": [w["name"] for w in wss],
                "srcname": (src or {}).get("name", ""), "srcpath": path,
                "keyfiles": (src or {}).get("files") or [],
                "docs": docs, "docmore": more, "handoff": hoff,
                "convos": convos,
                "tr": transcripts_for(sl),
                "goals": goals, "goal": next_goal,
                "ship": ship_state(src, expanded),
                "pulse": pulse, "changed": changed,
                "notes": notes, "folds": room_folds(name, ws_names),
                "habits": hab,
            })
        health = ""
        nreal = sum(1 for wn2, rcfg, sl, ws in room_specs
                    if wn2 == wname and not rcfg.get("habits"))
        if nreal:
            health = (f"{quiet} of {nreal} rooms untouched for 2+ weeks"
                      if quiet else "every room touched this fortnight")
        wopen = sum(r["open"] for r in rooms if r["wing"] == wname)
        wings.append({"name": wname, "rooms": slugs, "health": health,
                      "quiet": quiet, "open": wopen})

    total_open = sum(r["open"] for r in rooms)

    # The floor plan's headline: the nearest finish lines across all rooms.
    upcoming = []
    for r in rooms:
        for g in r["goals"]:
            if not g["done"] and g["dd"] is not None:
                upcoming.append({"slug": r["slug"], "room": r["name"],
                                 "t": g["t"][:60], "dd": g["dd"]})
    upcoming.sort(key=lambda g: g["dd"])
    upcoming = upcoming[:4]

    page = TEMPLATE
    page = page.replace("__STYLE__", (config.get("appearance", {}) or {}).get("style", "workroom"))
    rooms_json = json.dumps(rooms).replace("</", "<\\/")
    page = page.replace("__ROOMS__", rooms_json)
    page = page.replace("__WINGS__", json.dumps(wings))
    page = page.replace("__GOALSTRIP__", json.dumps(upcoming))
    page = page.replace("__LEFTOVERS__", json.dumps(leftovers))
    page = page.replace("__HEADER__", CHROME.header_html(
        current="rooms", owner=config.get("owner", ""),
        right_html='<input id="search" type="search" '
                   'placeholder="Search all your brains&hellip;" '
                   'aria-label="Search all project docs">'))
    page = page.replace("__TOUR__",
                        CHROME.ask_block() + T.rooms_block() + K.block())
    page = page.replace("__DATE__", date.today().isoformat())
    page = page.replace("__TOTAL__", str(total_open))

    # The publish gate the brain page has: never overwrite a working page
    # with one whose script cannot parse — stale beats blank.
    import shutil as _sh
    import tempfile as _tf
    node = _sh.which("node")
    if node:
        for js in re.findall(r"<script>(.*?)</script>", page, re.S):
            with _tf.NamedTemporaryFile("w", suffix=".js",
                                        delete=False) as tmp:
                tmp.write(js)
            try:
                r = subprocess.run([node, "--check", tmp.name],
                                   capture_output=True, text=True, timeout=20)
                if r.returncode != 0:
                    raise SystemExit(
                        "REFUSING to write rooms.html — a page script does "
                        "not parse:\n" + r.stderr.strip()[:600])
            finally:
                os.unlink(tmp.name)

    with open(OUT, "w", encoding="utf-8") as f:
        f.write(page)
    return OUT, len(rooms)


TEMPLATE = """<!doctype html>
<html lang="en" data-style="__STYLE__"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>The rooms</title>
<link rel="icon" href="logo-192.png?v=5" type="image/png">
<link rel="apple-touch-icon" href="logo-180.png?v=5">
<script>
var _t = null;
try { _t = localStorage.getItem('brain-theme'); } catch(e){}
if(_t && _t !== 'auto') document.documentElement.setAttribute('data-theme', _t);
try { var _s = localStorage.getItem('brain-style');
  if(_s) document.documentElement.setAttribute('data-style', _s); } catch(e){}
</script>
<link rel="stylesheet" href="appearance.css">
<style>
:root{
  --bg:var(--paper); --text:var(--ink);
  --overdue:var(--bad); --chase:var(--wait); --cold:var(--cold);
  --soon:var(--terra); --waiting:var(--faint); --moving:var(--green);
  --quiet:var(--line2);
}
*{box-sizing:border-box}
html,body{margin:0}
body{background:var(--bg);color:var(--text);
  font:15px/1.55 var(--sans,'Schibsted',-apple-system,'Segoe UI',Roboto,sans-serif)}
/* The page's own title strip, UNDER the app header rather than instead of it:
   rooms used to put the nav hard against the left edge with no wordmark, so
   arriving here from Today felt like arriving at a different app. */
.bar{display:flex;gap:10px;align-items:baseline;flex-wrap:wrap;
  padding:14px 20px 4px;max-width:1280px;margin:0 auto;background:none;border:0}
.bar b{font:600 20px/1.2 var(--serif,'Literata',Georgia,serif)}
/* The rooms are the one place you are meant to be orienting yourself, so the
   mascot arrives with its map. A transparent PNG, so no blend mode. */
.barart{display:block;flex:none;margin:-3px 0 -3px -2px}
@media(max-width:720px){.barart{display:none}}
.bar .n{color:var(--faint);font-size:12px}
a.back{display:inline-flex;align-items:center;gap:5px;font-weight:600;font-size:13px;
  text-decoration:none;color:var(--text);background:var(--surface);
  border:1px solid var(--line);border-radius:9px;padding:5px 10px}
.bar svg{width:15px;height:15px;flex:none}
/* Search keeps its place in the header — it is what this page does that no
   other page does, which is exactly what the header's right slot is for. */
#search{font:inherit;font-size:13px;width:min(260px,32vw);
  padding:6px 12px;border:1px solid var(--line);border-radius:999px;
  background:var(--surface);color:var(--text)}
#search:focus{outline:2px solid var(--moving);outline-offset:1px;border-color:transparent}
@media(max-width:820px){#search{width:150px}}
@media(max-width:600px){#search{display:none}}
main{max-width:1280px;margin:0 auto;padding:18px 16px 90px}
/* ---- the floor plan ---- */
.wing{margin:0 0 14px;border:1px solid var(--line);border-radius:16px;
  background:var(--surface);overflow:hidden}
.wing>header{display:flex;gap:10px;align-items:baseline;flex-wrap:wrap;
  padding:13px 16px;cursor:pointer}
.wing h2{margin:0;font:600 17px/1.2 var(--serif,'Literata',Georgia,serif)}
.whealth{font-size:12px;color:var(--faint)}
.whealth.worry{color:var(--soon)}
.waudit{margin-left:auto;font-weight:600;font-size:12px;line-height:1;color:var(--dim);
  cursor:pointer;background:var(--bg);border:1px solid var(--line);border-radius:999px;
  padding:6px 11px;font-family:inherit}
.waudit:hover{color:var(--text);border-color:var(--dim)}
.wcaret{color:var(--faint);font-size:12px}
.roomgrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(235px,1fr));
  gap:10px;padding:0 14px 14px}
.wing.closed .roomgrid{display:none}
.room{position:relative;text-align:left;font:inherit;color:var(--text);cursor:pointer;
  background:var(--bg);border:1px solid var(--line);border-radius:13px;padding:12px 14px;
  display:flex;flex-direction:column;align-items:flex-start;justify-content:flex-start}
.room:hover{border-color:var(--dim)}
.room.quiet{opacity:.68}
.room.quiet:hover{opacity:1}
.room h3{margin:0 0 3px;font-size:15px;display:flex;gap:8px;align-items:center}
.dot{width:9px;height:9px;min-width:9px;border-radius:50%;display:inline-block}
.room .line{font-size:12px;color:var(--faint)}
.room .next{margin-top:7px;font-size:12.5px;color:var(--dim);display:-webkit-box;
  -webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.gitdot{position:absolute;top:12px;right:12px;width:7px;height:7px;border-radius:50%}
.gitdot.fresh{background:var(--moving)} .gitdot.warm{background:var(--soon)}
.gitdot.stale{background:var(--quiet)}
.strip{margin:16px 2px 0;font-size:12.5px;color:var(--faint)}
.strip b{color:var(--dim);font-weight:600}
.goalstrip{margin:2px 2px 16px;display:flex;gap:8px;align-items:center;flex-wrap:wrap;
  font-size:12.5px;color:var(--faint)}
.gchip{font-weight:600;font-size:12px;line-height:1.4;font-family:inherit;cursor:pointer;
  color:var(--dim);background:var(--surface);border:1px solid var(--line);
  border-radius:999px;padding:6px 12px;text-align:left}
.gchip:hover{color:var(--text);border-color:var(--dim)}
.gchip.bad{color:var(--overdue);border-color:var(--overdue)}
.gline{margin-top:6px;font-size:12px;color:var(--dim)}
.gline.bad{color:var(--overdue)}
/* ---- inside a room ---- */
#roomview{max-width:860px;margin:0 auto}
/* A room is a workspace, not a column: with room, the work (what's next,
   goals, asking) takes the wider left, and what the room KNOWS (its memory,
   its own docs, its people, its pulse) sits beside it instead of below the
   fold. The header and state line stay full width. */
@media(min-width:1080px){
  /* Each side is its own flex column. The grid used to place every zone in a
     shared row, so a tall memory on the right held its row open and left a
     screen of white under "the next thing" on the left. Two independent
     columns pack independently. */
  #roomview{max-width:1240px;display:grid;gap:22px 28px;
    grid-template-columns:minmax(0,1.25fr) minmax(0,1fr);align-items:start}
  #roomview>.rhead,#roomview>.rline{grid-column:1 / -1}
  #roomview>.rcolL{grid-column:1}
  #roomview>.rcolR{grid-column:2}
  #roomview .rcol{display:flex;flex-direction:column;gap:22px;min-width:0}
  #roomview .rcol>.zone{margin:0}
  #roomview.bigq{grid-template-columns:minmax(0,1fr);max-width:760px}
  #roomview.bigq>.zone{grid-column:1}
}
/* the big questions: paper, not dashboard */
#roomview.bigq .dot{display:none}
#roomview.bigq .zone{background:transparent;border:0;padding:0;
  margin-bottom:34px}
#roomview.bigq .rline{display:none}
#roomview.bigq h1{font-size:30px}
/* the questions themselves live in the room's memory — so in this room the
   memory is not a form field, it is the page */
#roomview.bigq #notes{font:400 16.5px/1.8 'Petrona',Georgia,serif;
  min-height:60vh;background:transparent;border:0;padding:0;resize:none;
  color:var(--text)}
#roomview.bigq #notes:focus{outline:0;box-shadow:none}
#roomview.bigq .memread{font-size:16.5px;line-height:1.8}
#roomview.bigq .memread h2{font:600 21px/1.35 'Literata',Georgia,serif;
  text-transform:none;letter-spacing:0;color:var(--text);margin:26px 0 8px}
/* The room's memory, read rather than edited. */
.memread{font:400 14.5px/1.7 'Petrona',Georgia,serif;color:var(--text);
  max-width:68ch}
.memread>:first-child{margin-top:0}
.memread h2,.memread h3,.memread h4,.memread h5{font-family:'Literata',Georgia,serif;
  color:var(--text);text-transform:none;letter-spacing:0}
.memread h2{font-size:17px;font-weight:600;margin:20px 0 6px}
.memread h3{font-size:15px;font-weight:600;margin:16px 0 5px}
.memread h4,.memread h5{font-size:13.5px;font-weight:600;margin:13px 0 4px;color:var(--dim)}
.memread p{margin:0 0 10px}
.memread ul,.memread ol{margin:0 0 10px;padding-left:20px}
.memread li{margin:0 0 4px}
.memread li.sub{margin-left:14px;font-size:.95em;color:var(--dim)}
.memread code{font:400 .9em/1.4 ui-monospace,SFMono-Regular,Menlo,monospace;
  background:var(--surface);border:1px solid var(--line);border-radius:5px;padding:0 4px}
.memread blockquote{margin:0 0 10px;padding-left:12px;color:var(--dim);font-style:italic}
.memread hr{border:0;border-top:1px solid var(--line);margin:16px 0}
.memread a{color:var(--moving)}
.mdbox{display:inline-block;width:11px;height:11px;margin-right:7px;
  border:1.4px solid var(--line2);border-radius:3px;vertical-align:baseline}
.mdbox.on{background:var(--moving);border-color:var(--moving)}
.memempty{color:var(--faint);font-style:italic}
.noterow .flink{background:none;border:0;color:var(--faint);cursor:pointer;
  font-size:12px;padding:6px 4px}
#roomview.bigq .z-mem h2{font-size:13px;letter-spacing:.12em;
  text-transform:uppercase;color:var(--faint);font-weight:600}
.rhead{margin:4px 0 6px}
.rhead .wingtag{display:block;margin:0 0 5px;font-size:10.5px;font-weight:700;
  text-transform:uppercase;letter-spacing:.11em;color:var(--faint)}
.rtitle{display:flex;gap:16px;align-items:baseline;flex-wrap:wrap}
.rhead h1{margin:0;font:600 27px/1.15 var(--serif,'Literata',Georgia,serif)}
.rhead h1 .dot{width:10px;height:10px;margin-right:2px}
/* the two links are metadata, not siblings of the title */
.rmeta{display:flex;gap:14px;align-items:baseline;flex-wrap:wrap;min-width:0}
.rml{font:inherit;font-size:12.5px;color:var(--faint);background:none;border:0;
  padding:0;cursor:pointer;text-decoration:none;white-space:nowrap;
  max-width:46ch;overflow:hidden;text-overflow:ellipsis}
.rml:hover{color:var(--moving)}
.rmi{margin-left:3px;opacity:.6;font-size:11px}
.rline{color:var(--dim);font-size:13px;margin:0 0 14px}
.zone{background:var(--surface);border:1px solid var(--line);border-radius:14px;
  padding:14px 16px;margin:0 0 12px}
.zone h2{margin:0 0 9px;font-weight:700;font-size:11.5px;line-height:1;
  font-family:inherit;text-transform:uppercase;letter-spacing:.1em;color:var(--faint)}
/* every box folds on its heading; the room remembers which ones stay shut */
.zone>h2{cursor:pointer;user-select:none}
.zone>h2::after{content:'\\25be';float:right;color:var(--faint);font-size:11px}
.zone.shut>h2{margin:0}
.zone.shut>h2::after{content:'\\25b8'}
.zone.shut>*:not(h2){display:none}
#roomview.bigq .zone>h2{cursor:default}
#roomview.bigq .zone>h2::after{content:none}
/* a memory that has grown long starts folded to a page */
.memread.clamp{max-height:400px;overflow:hidden;
  -webkit-mask-image:linear-gradient(#000 75%,transparent);
  mask-image:linear-gradient(#000 75%,transparent)}
.memmore{background:none;border:0;color:var(--moving);cursor:pointer;
  font:inherit;font-size:12.5px;padding:6px 0 0}
.memread[hidden]+.memmore{display:none}
.tasks{list-style:none;margin:0;padding:0;font-size:14px}
.tasks li{padding:4px 0;display:flex;gap:9px;align-items:flex-start}
.ptick{width:17px;height:17px;min-width:17px;margin-top:2px;border:1.5px solid var(--line2);
  border-radius:5px;background:transparent;cursor:pointer;padding:0}
.ptick:hover{border-color:var(--moving)}
.tws{font-size:11px;color:var(--faint);white-space:nowrap;margin-left:auto;padding-left:8px}
.pdd{font-style:normal;font-size:11px;color:var(--soon);white-space:nowrap}
.pdd.bad{color:var(--overdue)}
.urg{font-size:10.5px;font-weight:700;color:var(--overdue);letter-spacing:.05em}
.prep{margin:10px 0 0;border-top:1px solid var(--line);padding-top:9px;font-size:13.5px}
.prep summary{cursor:pointer;color:var(--dim);font-weight:600}
.prep .meta{color:var(--faint);font-size:11.5px}
.askrow{display:flex;gap:8px;flex-wrap:wrap}
.askrow textarea{flex:1 1 100%;min-width:200px;font:inherit;font-size:13.5px;padding:9px 12px;
  border:1px solid var(--line);border-radius:10px;background:var(--bg);color:var(--text);
  resize:vertical;min-height:38px}
.askrow select,.askrow button, .noterow button{font:inherit;font-size:13px;padding:8px 12px;
  border:1px solid var(--line);border-radius:10px;background:var(--bg);color:var(--text);
  cursor:pointer}
button.go{background:var(--moving);color:var(--bg);border-color:transparent;font-weight:700}
.hint{font-size:11.5px;color:var(--faint);margin:7px 0 0}
/* the conversations open in this room */
.convos{display:flex;flex-direction:column;gap:2px}
.convo{display:flex;gap:10px;align-items:flex-start;text-decoration:none;color:inherit;
  padding:8px 10px;margin:0 -10px;border-radius:10px}
.convo:hover{background:var(--wash,var(--bg))}
.cdot{width:8px;height:8px;min-width:8px;margin-top:6px;border-radius:50%;
  background:var(--line2);display:block}
.convo.st-ask .cdot{background:var(--overdue)}
.convo.st-working .cdot{background:var(--moving)}
.cmid{display:flex;flex-direction:column;gap:2px;min-width:0;flex:1}
.ctop{font-size:14px;font-weight:600;display:flex;gap:8px;align-items:baseline;
  flex-wrap:wrap}
.chands{font-size:10px;font-weight:700;letter-spacing:.07em;text-transform:uppercase;
  color:var(--faint)}
.cline{font-size:12.5px;color:var(--dim);line-height:1.45}
.convo.st-ask .cline{color:var(--text)}
.cwhen{font-size:11px;font-weight:700;color:var(--faint);white-space:nowrap;
  margin-top:4px}
.convo.st-ask .cwhen{color:var(--overdue)}
.convoall{display:inline-block;margin-top:9px;font-size:12px;font-weight:600;
  color:var(--moving);text-decoration:none}
.convoall:hover{text-decoration:underline}
#notes{width:100%;font:13.5px/1.5 ui-monospace,Menlo,monospace;min-height:110px;
  padding:10px 12px;border:1px solid var(--line);border-radius:10px;
  background:var(--bg);color:var(--text);resize:vertical}
.noterow{display:flex;gap:8px;align-items:center;margin-top:8px}
.savednote{font-size:12px;color:var(--moving)}
.docs{list-style:none;margin:0;padding:0;font-size:13.5px}
.docs li{display:flex;gap:8px;align-items:baseline;padding:3px 0}
.doclink{border:0;background:none;padding:0;font:inherit;color:var(--text);
  cursor:pointer;text-align:left}
.doclink:hover{color:var(--moving);text-decoration:underline}
.docmeta{color:var(--faint);font-size:11px;margin-left:auto;white-space:nowrap}
.docmore{border:0;background:none;padding:4px 0;margin-top:2px;font:inherit;
  font-size:12px;color:var(--faint);cursor:pointer;text-align:left}
.docmore:hover{color:var(--moving)}
.docreveal{border:0;background:none;color:var(--faint);cursor:pointer;font-size:12px}
.docreveal:hover{color:var(--text)}
/* the handoff: what the project's own brain says, without opening it */
.hoff{margin:0 0 14px;padding:12px 14px;border:1px solid var(--line);
  border-left:3px solid var(--moving);border-radius:10px;background:var(--bg)}
.hoffworry{margin:0;font-size:13.5px;font-weight:600;color:var(--text)}
.hoffnext{margin:9px 0 0;padding:0 0 0 17px;font-size:13px;color:var(--dim)}
.hoffnext li{margin:2px 0}
.hoffyours{margin-left:7px;font-size:10.5px;font-weight:700;letter-spacing:.04em;
  text-transform:uppercase;color:var(--overdue,var(--moving))}
.hoffmeta{margin:9px 0 0;font-size:12px;color:var(--faint)}
.hoffrow{display:flex;gap:10px;align-items:center;margin-top:11px}
.hoffopen{font:inherit;font-size:12px;font-weight:700;line-height:1;cursor:pointer;
  padding:7px 12px;border-radius:999px;border:1.5px solid var(--line);
  background:var(--surface);color:var(--text)}
.hoffopen:hover{border-color:var(--moving);color:var(--moving)}
.hoffas{font-size:11px;color:var(--faint)}
.docbody{margin:10px 0 4px;padding:12px 14px;border:1px solid var(--line);
  border-radius:10px;background:var(--bg);overflow-x:auto;font-size:13.5px}
.docbody h1,.docbody h2,.docbody h3{font-family:var(--serif,'Literata',Georgia,serif)}
.docbody pre{overflow-x:auto;background:var(--sunken);padding:10px;border-radius:8px}
.docbody table{border-collapse:collapse}
.docbody td,.docbody th{border:1px solid var(--line);padding:4px 8px;font-size:12.5px}
.docbody[hidden]{display:none}
/* acting on a recording, right where she finishes reading it */
.tract{display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin:14px 0 2px;
  padding-top:12px;border-top:1px solid var(--line)}
.tract button{font:inherit;font-size:13px;padding:8px 12px;border:1px solid var(--line);
  border-radius:10px;background:var(--bg);color:var(--text);cursor:pointer}
.tract button.go{background:var(--moving);color:var(--bg);border-color:transparent;font-weight:700}
.tract .hint{flex-basis:100%;margin:0}
.gprog{font-size:12px;color:var(--faint);margin:0 0 8px}
.tl{position:relative;height:24px;margin:12px 4px 4px}
.tl::before{content:'';position:absolute;left:0;right:0;top:11px;height:2px;
  background:var(--line)}
.tl i{position:absolute;top:7px;width:10px;height:10px;border-radius:50%;
  background:var(--bg);border:2px solid var(--faint);box-sizing:border-box}
.tl i.done{background:var(--moving);border-color:var(--moving)}
.tl i.over{background:var(--overdue);border-color:var(--overdue)}
.tl i.now{left:0;top:5px;width:2.5px;height:14px;border-radius:1px;
  background:var(--terra);border:0}
.addrow{display:flex;gap:8px;margin-top:10px;flex-wrap:wrap}
.addrow input{flex:1;min-width:150px;font:inherit;font-size:13px;padding:8px 11px;
  border:1px solid var(--line);border-radius:10px;background:var(--bg);color:var(--text)}
.addrow input.due{flex:0 1 170px}
.addrow input:focus{outline:2px solid var(--moving);outline-offset:1px;border-color:transparent}
.addrow button,.addrow select{font:inherit;font-size:13px;padding:8px 12px;
  border:1px solid var(--line);border-radius:10px;background:var(--bg);
  color:var(--text);cursor:pointer}
.addrow button.go{background:var(--moving);color:var(--bg);border-color:transparent;
  font-weight:700}
.pquiet{color:var(--soon)}
.shipline{margin-top:9px;font-size:13px;color:var(--dim)}
.shipline.warn{color:var(--soon)}
.ppl{display:flex;gap:6px;flex-wrap:wrap}
.pchip{font-weight:600;font-size:12px;line-height:1;font-family:inherit;
  text-decoration:none;color:var(--dim);
  border:1px solid var(--line);border-radius:999px;padding:6px 10px}
.pchip:hover{color:var(--text);border-color:var(--dim)}
.pulse{font-size:13px;color:var(--dim)}
.pulse ul{list-style:none;margin:6px 0 0;padding:0}
.pulse li{padding:2px 0;display:flex;gap:10px}
.pulse .cd{color:var(--faint);font-size:11.5px;white-space:nowrap;min-width:78px}
.habits{list-style:none;margin:0;padding:0;font-size:14px}
.habits li{display:flex;gap:10px;align-items:center;padding:4px 0}
.hcount{margin-left:auto;color:var(--faint);font-size:12px}
.flink{border:0;background:none;padding:0;font:inherit;font-size:12.5px;
  color:var(--moving);cursor:pointer}
.flink:hover{text-decoration:underline}
.empty{color:var(--faint);font-size:13px}
#results{max-width:1060px;margin:0 auto}
.hit{padding:7px 0;border-bottom:1px solid var(--line);font-size:13.5px}
.hit .where{color:var(--faint);font-size:11.5px}
.toast{position:fixed;left:50%;transform:translateX(-50%);bottom:56px;z-index:14;
  background:var(--ink);color:var(--bg);font-size:13px;padding:9px 18px;
  border-radius:999px;opacity:0;transition:opacity .18s ease-out;pointer-events:none}
.toast.on{opacity:1}
.agentbar{position:fixed;left:16px;bottom:14px;z-index:12;display:flex;gap:9px;
  align-items:center;background:var(--surface);border:1.5px solid var(--line);
  border-radius:999px;padding:7px 8px 7px 13px;font-weight:600;font-size:13px;
  line-height:1;color:var(--dim);
  box-shadow:0 4px 20px var(--shadow,rgba(0,0,0,.12))}
.agentbar[hidden]{display:none}
.agentbar button{font-weight:700;font-size:12px;line-height:1;font-family:inherit;
  background:var(--moving);color:var(--bg);
  border:0;border-radius:999px;padding:7px 12px;cursor:pointer}
[hidden]{display:none !important}
@media(max-width:640px){
  .roomgrid{grid-template-columns:1fr 1fr}
  #search{width:100%;order:9}
}
""" + CHROME.NAV_CSS + CHROME.HEADER_CSS + """
</style></head><body>
__HEADER__
<div class="bar">
  <img class="barart" src="art/wayfinding.png?v=2" alt="" width="30" height="30"
       aria-hidden="true">
  <b id="bartitle">The rooms</b>
  <span class="n" id="barcount">__TOTAL__ open &middot; __DATE__</span>
</div>
<main>
  <div id="floor"></div>
  <div id="results" hidden></div>
  <div id="roomview" hidden></div>
</main>
<div class="toast" id="toast" hidden></div>
<div class="agentbar" id="agentbar" hidden>
  <span id="ab-txt"></span><button id="ab-run">Run now</button>
</div>
<script>
var ROOMS = __ROOMS__, WINGS = __WINGS__, LEFTOVERS = __LEFTOVERS__,
    GOALS = __GOALSTRIP__;
var byslug = {};
ROOMS.forEach(function(r){ byslug[r.slug] = r; });

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
    setTimeout(function(){ t.hidden = true; }, 220);
  }, 2600);
}
function post(path, body){
  return fetch(path, {method:'POST', headers:{'Content-Type':'application/json'},
                      body: JSON.stringify(body)})
    .then(function(r){ return r.json().then(function(j){
      if(!r.ok) throw new Error(j.error || r.status);
      return j;
    }); });
}
function daysAgo(iso){
  if(!iso) return null;
  return Math.round((Date.now() - new Date(iso + 'T12:00:00')) / 86400000);
}
function agoTxt(iso){
  var n = daysAgo(iso);
  if(n == null) return '';
  if(n <= 0) return 'today';
  if(n === 1) return 'yesterday';
  return n + ' days ago';
}

// ---- the floor plan -------------------------------------------------------
function ddTxt(dd){
  return dd < 0 ? Math.abs(dd) + 'd late' : dd === 0 ? 'today' : 'in ' + dd + 'd';
}
function drawFloor(){
  var root = document.getElementById('floor');
  root.innerHTML = '';
  if(GOALS.length){
    var gs = el('div', 'goalstrip');
    gs.appendChild(el('b', '', 'Finish lines:'));
    GOALS.forEach(function(g){
      var b = el('button', 'gchip' + (g.dd < 0 ? ' bad' : ''),
        g.room + ' \\u00b7 ' + g.t + ' \\u2014 ' + ddTxt(g.dd));
      b.onclick = function(){ location.hash = '#room/' + g.slug; };
      gs.appendChild(b);
    });
    root.appendChild(gs);
  }
  WINGS.forEach(function(wg){
    var sec = el('section', 'wing');
    var closed = false;
    try { closed = localStorage.getItem('room-wing-' + wg.name) === 'closed'; } catch(e){}
    if(closed) sec.classList.add('closed');
    var hd = el('header');
    hd.appendChild(el('h2', '', wg.name));
    if(wg.open) hd.appendChild(el('span', 'whealth', wg.open + ' open'));
    if(wg.health)
      hd.appendChild(el('span', 'whealth' + (wg.quiet ? ' worry' : ''), wg.health));
    var au = el('button', 'waudit', 'Audit this part');
    au.title = 'Queue Claude to read this wing\\u2019s rooms and say what\\u2019s drifting';
    au.onclick = function(ev){ ev.stopPropagation(); wingAudit(wg); };
    hd.appendChild(au);
    hd.appendChild(el('span', 'wcaret', closed ? '\\u25b8' : '\\u25be'));
    hd.onclick = function(){
      var c = sec.classList.toggle('closed');
      hd.querySelector('.wcaret').textContent = c ? '\\u25b8' : '\\u25be';
      try { localStorage.setItem('room-wing-' + wg.name, c ? 'closed' : 'open'); } catch(e){}
    };
    sec.appendChild(hd);
    var grid = el('div', 'roomgrid');
    wg.rooms.forEach(function(sl){
      var r = byslug[sl]; if(!r) return;
      var card = el('button', 'room' + (r.state === 'quiet' ? ' quiet' : ''));
      var h = el('h3');
      var dot = el('i', 'dot');
      dot.style.background = 'var(--' + r.state + ')';
      h.appendChild(dot); h.appendChild(document.createTextNode(r.name));
      card.appendChild(h);
      if(r.stateline) card.appendChild(el('div', 'line', r.stateline));
      if(r.next) card.appendChild(el('div', 'next', r.next));
      if(r.goal)
        card.appendChild(el('div',
          'gline' + (r.goal.dd != null && r.goal.dd < 0 ? ' bad' : ''),
          '\\u25c7 ' + r.goal.t
            + (r.goal.dd == null ? '' : ' \\u00b7 ' + ddTxt(r.goal.dd))));
      if(r.pulse){
        var n = daysAgo(r.pulse.last);
        var g = el('i', 'gitdot ' + (n <= 7 ? 'fresh' : n <= 21 ? 'warm' : 'stale'));
        g.title = 'last commit ' + agoTxt(r.pulse.last);
        card.appendChild(g);
      }
      card.onclick = function(){ location.hash = '#room/' + r.slug; };
      grid.appendChild(card);
    });
    sec.appendChild(grid);
    root.appendChild(sec);
  });
  if(LEFTOVERS.length){
    var s = el('p', 'strip');
    s.appendChild(document.createTextNode('Not in any room yet: '));
    s.appendChild(el('b', '', LEFTOVERS.join(' \\u00b7 ')));
    s.appendChild(document.createTextNode(' \\u2014 still on the map and in Today.'));
    root.appendChild(s);
  }
}

function wingAudit(wg){
  var names = wg.rooms.map(function(sl){ return byslug[sl]; })
    .filter(Boolean).filter(function(r){ return !r.habits; });
  if(!names.length) return;
  var lines = names.map(function(r){
    var l = r.name;
    if(r.wss.length) l += ' (workstreams: ' + r.wss.join(', ') + ')';
    if(r.srcpath) l += ' [folder ' + r.srcpath + ']';
    return '- ' + l;
  });
  if(!confirm('Queue an audit of \\u201c' + wg.name + '\\u201d? Claude reads what\\u2019s '
              + 'in these rooms, compares it with the tasks, and says what\\u2019s drifting.'))
    return;
  post('/api/queue', {mode: 'investigate',
    text: 'Audit one part of my life: \\u201c' + wg.name + '\\u201d. Its rooms:\\n'
      + lines.join('\\n') + '\\n\\nFor each room: read the workstream and, where a '
      + 'folder is listed, its key files. Compare what the files say with the open '
      + 'tasks. Tell me plainly what is drifting, what is stale, and ask me what is '
      + 'missing. When your Outcome talks about a project, name it like: workstream '
      + '\\u201cX\\u201d \\u2014 that is how the findings land back in the right room. '
      + 'Propose, don\\u2019t restructure; tick nothing.'})
    .then(function(){ toast('Audit queued \\u2014 run it from the pill below \\u2713'); abPoll(); })
    .catch(function(e){ toast(e.message); });
}

// ---- reading a room's memory ----------------------------------------------
// Small on purpose: exactly the markdown these notes actually use. Rendering
// happens here rather than server-side so that what you see after saving is
// what you just typed, with no rebuild in between.
function esc(s){
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}
function mdInline(s){
  s = esc(s);
  s = s.replace(/`([^`]+)`/g, '<code>$1</code>');
  s = s.replace(/\\*\\*([^*]+)\\*\\*/g, '<strong>$1</strong>');
  s = s.replace(/(^|[\\s(])\\*([^*\\n]+)\\*(?=[\\s).,;:!?]|$)/g, '$1<em>$2</em>');
  s = s.replace(/\\[([^\\]]+)\\]\\(([^)\\s]+)\\)/g,
                '<a href="$2" target="_blank" rel="noopener">$1</a>');
  return s;
}
// A note whose first line repeats the room's own name printed the title twice.
function stripOwnTitle(txt, roomName){
  var lines = txt.split('\\n');
  var m = (lines[0] || '').match(/^#\\s+(.*)$/);
  if(m){
    var a = m[1].toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim();
    var b = (roomName || '').toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim();
    if(a.indexOf(b) === 0 || b.indexOf(a.split(' room memory')[0].trim()) === 0){
      lines.shift();
      while(lines.length && !lines[0].trim()) lines.shift();
      return lines.join('\\n');
    }
  }
  return txt;
}
function mdToHtml(txt){
  var out = [], list = null, para = [], i;
  function flushPara(){
    if(para.length){ out.push('<p>' + mdInline(para.join(' ')) + '</p>'); para = []; }
  }
  function flushList(){
    // items stay raw text until here, so a bullet wrapped over indented
    // lines is one item — and bold that spans the wrap still matches
    if(list){ out.push('<' + list.tag + '>' + list.items.map(function(it){
                return '<li' + it.cls + '>' + it.mark + mdInline(it.body) + '</li>';
              }).join('') + '</' + list.tag + '>');
              list = null; }
  }
  var lines = txt.split('\\n');
  for(i = 0; i < lines.length; i++){
    var ln = lines[i], t = ln.trim();
    if(!t){ flushPara(); flushList(); continue; }
    var h = t.match(/^(#{1,4})\\s+(.*)$/);
    if(h){ flushPara(); flushList();
           var lvl = Math.min(h[1].length + 1, 5);
           out.push('<h' + lvl + '>' + mdInline(h[2]) + '</h' + lvl + '>'); continue; }
    if(/^(---|\\*\\*\\*|___)\\s*$/.test(t)){ flushPara(); flushList(); out.push('<hr>'); continue; }
    var b = t.match(/^[-*+]\\s+(?:\\[([ xX])\\]\\s+)?(.*)$/);
    var n = t.match(/^\\d+[.)]\\s+(.*)$/);
    if(b || n){
      flushPara();
      var tag = b ? 'ul' : 'ol';
      if(!list || list.tag !== tag){ flushList(); list = {tag: tag, items: []}; }
      var body = b ? b[2] : n[1];
      var mark = b && b[1] !== undefined
        ? '<span class="mdbox' + (b[1].toLowerCase() === 'x' ? ' on' : '') + '"></span>'
        : '';
      // a nested bullet keeps its indent rather than being flattened
      var indent = (ln.match(/^\\s*/) || [''])[0].length >= 2 ? ' class="sub"' : '';
      list.items.push({cls: indent, mark: mark, body: body});
      continue;
    }
    if(/^>\\s?/.test(t)){ flushPara(); flushList();
      out.push('<blockquote>' + mdInline(t.replace(/^>\\s?/, '')) + '</blockquote>'); continue; }
    if(list && /^\\s/.test(ln)){
      // an indented line under an open list is the bullet above, wrapped
      list.items[list.items.length - 1].body += ' ' + t;
      continue;
    }
    para.push(t);
  }
  flushPara(); flushList();
  return out.join('');
}

// ---- inside a room --------------------------------------------------------
var CUR = null;
function drawRoom(r){
  CUR = r;
  var root = document.getElementById('roomview');
  root.innerHTML = '';
  // The big questions are held, not worked: no state colour, no progress,
  // no card chrome — a journal page, which is what they deserve.
  root.classList.toggle('bigq', (r.slug || '') === 'big-questions');
  // Eyebrow, then title, then the links as metadata. All four used to sit on
  // one centre-aligned row, so a 10px uppercase wing tag, a 24px serif title
  // and two accent-coloured links competed as equals \u2014 and the two links
  // looked identical despite one opening Finder and the other a web page.
  var hd = el('header', 'rhead');
  hd.appendChild(el('span', 'wingtag', r.wing));
  var trow = el('div', 'rtitle');
  var h1 = el('h1');
  var dot = el('i', 'dot'); dot.style.background = 'var(--' + r.state + ')';
  h1.appendChild(dot); h1.appendChild(document.createTextNode(' ' + r.name));
  trow.appendChild(h1);
  var meta = el('div', 'rmeta');
  if(r.srcpath){
    var fb = el('button', 'rml', r.srcpath);
    fb.title = 'Reveal this folder in Finder';
    fb.appendChild(el('span', 'rmi', '\\u2197'));
    fb.onclick = function(){
      post('/api/reveal', {path: r.srcpath})
        .then(function(){ toast('Opened in Finder \\u2713'); })
        .catch(function(e){ toast(e.message); });
    };
    meta.appendChild(fb);
  }
  if(r.wss.length){
    var pl = document.createElement('a');
    pl.className = 'rml'; pl.href = 'index.html#/plate';
    pl.textContent = 'on the plate';
    pl.appendChild(el('span', 'rmi', '\\u2197'));
    pl.title = 'The same project as a workstream row';
    meta.appendChild(pl);
  }
  var rf = el('button', 'rml', 'refresh');
  rf.appendChild(el('span', 'rmi', '\\u21bb'));
  rf.title = 'Re-read the project folders and rebuild this page';
  rf.onclick = function(){
    rf.disabled = true;
    post('/api/sync', {})
      .then(function(){
        toast('Re-read \\u2713 \\u2014 reloading');
        setTimeout(function(){ location.reload(); }, 500);
      })
      .catch(function(e){ rf.disabled = false; toast(e.message); });
  };
  meta.appendChild(rf);
  if(meta.children.length) trow.appendChild(meta);
  hd.appendChild(trow);
  root.appendChild(hd);
  if(r.stateline) root.appendChild(el('p', 'rline', r.stateline));

  // 1 — the next thing
  var z1 = el('section', 'zone z-next');
  z1.appendChild(el('h2', '', 'The next thing'));
  if(r.habits){
    var hl = el('ul', 'habits');
    r.habits.forEach(function(h){
      var li = el('li');
      var cb = el('button', 'ptick');
      cb.title = 'Did it today';
      cb.style.borderColor = h.done ? 'var(--moving)' : '';
      cb.textContent = h.done ? '\\u2713' : '';
      cb.onclick = function(){
        cb.disabled = true;
        post('/api/habit', {name: h.name})
          .then(function(){ toast('Logged \\u2713'); nudgePoll(); })
          .catch(function(e){ cb.disabled = false; toast(e.message); });
      };
      li.appendChild(cb);
      li.appendChild(el('span', '', h.name));
      li.appendChild(el('span', 'hcount', h.count + '/' + h.target
                        + (h.ok ? ' \\u00b7 on track' : '')));
      hl.appendChild(li);
    });
    z1.appendChild(r.habits.length ? hl : el('p', 'empty', 'No habits tracked yet.'));
  } else if(r.tasks.length || r.next){
    // the next move shows even when nothing is tickable — a front like
    // "keep dogfooding" is still the next thing. It earns its line only when
    // it isn't already the top checkbox: the same sentence twice, once as a
    // heading and once as a task, reads as a bug.
    var nrm = function(s){
      return String(s || '').toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim();
    };
    if(r.next && !(r.tasks.length && nrm(r.tasks[0].t) === nrm(r.next)))
      z1.appendChild(el('p', 'rline', '\\u2192 ' + r.next));
    var tl = el('ul', 'tasks');
    r.tasks.forEach(function(t){
      var li = el('li');
      var cb = el('button', 'ptick'); cb.title = 'Mark done';
      cb.onclick = function(){
        cb.disabled = true;
        post('/api/task', {src: 'workstreams.md', key: t.k, action: 'done'})
          .then(function(){
            sp.style.textDecoration = 'line-through'; sp.style.opacity = '.55';
            toast('Done \\u2713'); nudgePoll();
          })
          .catch(function(e){ cb.disabled = false; toast(e.message); });
      };
      var sp = el('span', '', t.t);
      li.appendChild(cb); li.appendChild(sp);
      if(t.u) li.appendChild(el('em', 'urg', 'URGENT'));
      if(t.dd != null){
        var dd = el('em', 'pdd' + (t.dd < 0 ? ' bad' : ''),
          t.dd < 0 ? Math.abs(t.dd) + 'd late' : t.dd === 0 ? 'today' : 'in ' + t.dd + 'd');
        li.appendChild(dd);
      }
      if(r.wss.length > 1) li.appendChild(el('span', 'tws', t.ws));
      tl.appendChild(li);
    });
    if(r.tasks.length) z1.appendChild(tl);
  } else {
    z1.appendChild(el('p', 'empty', r.wss.length
      ? 'Nothing open here \\u2014 all clear.'
      : 'No workstream yet \\u2014 ask below and Claude can start one.'));
  }
  // Adding work happens where the work is listed. With a workstream the line
  // lands on it directly; without one it goes to the inbox for triage.
  var ar = el('div', 'addrow');
  var ati = document.createElement('input');
  ati.type = 'text'; ati.setAttribute('data-mic', '1');
  ati.placeholder = r.wss.length
    ? 'Add a task \\u2014 what needs doing?'
    : 'Add to the inbox \\u2014 triage will file it\\u2026';
  var asel = null;
  if(r.wss.length > 1){
    asel = document.createElement('select');
    r.wss.forEach(function(n){
      var o = document.createElement('option');
      o.value = n; o.textContent = n; asel.appendChild(o);
    });
  }
  var adu = null;
  if(r.wss.length){
    adu = document.createElement('input');
    adu.type = 'text'; adu.className = 'due';
    adu.placeholder = 'due? \\u201cfriday\\u201d, \\u201cthis week\\u201d\\u2026';
  }
  var ab = el('button', 'go', 'Add');
  function addTask(){
    var t = ati.value.trim();
    if(!t) return;
    ab.disabled = true;
    var req = r.wss.length
      ? post('/api/add/task', {name: asel ? asel.value : r.wss[0], text: t,
                               due: adu.value.trim()})
      : post('/api/capture', {text: '[' + r.name + '] ' + t});
    req.then(function(){
        ab.disabled = false; ati.value = ''; if(adu) adu.value = '';
        toast('Added \\u2713 \\u2014 reloading');
        setTimeout(function(){ location.reload(); }, 500);
      })
      .catch(function(e){ ab.disabled = false; toast(e.message); });
  }
  ab.onclick = addTask;
  ati.addEventListener('keydown', function(ev){
    if(ev.key === 'Enter') addTask();
  });
  ar.appendChild(ati); if(asel) ar.appendChild(asel);
  if(adu) ar.appendChild(adu);
  ar.appendChild(ab);
  z1.appendChild(ar);
  r.folds.forEach(function(f){
    var d = document.createElement('details'); d.className = 'prep';
    var s = document.createElement('summary');
    s.textContent = '\\u2726 Claude prepared this \\u00b7 ' + f.date;
    d.appendChild(s);
    var b = el('div'); b.innerHTML = f.html;
    d.appendChild(b);
    var m = el('p', 'meta', f.title);
    d.appendChild(m);
    z1.appendChild(d);
  });
  root.appendChild(z1);

  // 1b — goals: the finish lines you set for yourself
  if(!r.habits){
    var zg = el('section', 'zone z-goals');
    zg.appendChild(el('h2', '', 'Goals'));
    var gdone = r.goals.filter(function(g){ return g.done; }).length;
    if(r.goals.length)
      zg.appendChild(el('p', 'gprog', gdone + ' of ' + r.goals.length + ' reached'));
    if(r.goals.length){
      var gul = el('ul', 'tasks');
      r.goals.forEach(function(g){
        var li = el('li');
        var cb = el('button', 'ptick'); cb.title = 'Reached';
        var sp = el('span', '', g.t);
        if(g.done){
          cb.textContent = '\\u2713'; cb.style.borderColor = 'var(--moving)';
          sp.style.textDecoration = 'line-through'; sp.style.opacity = '.55';
        }
        cb.onclick = function(){
          if(g.done) return;
          cb.disabled = true;
          post('/api/task', {src: 'goals.md', key: g.k, action: 'done'})
            .then(function(){
              sp.style.textDecoration = 'line-through'; sp.style.opacity = '.55';
              cb.textContent = '\\u2713';
              toast('Reached \\u2713'); nudgePoll();
            })
            .catch(function(e){ cb.disabled = false; toast(e.message); });
        };
        li.appendChild(cb); li.appendChild(sp);
        if(!g.done && g.dd != null)
          li.appendChild(el('em', 'pdd' + (g.dd < 0 ? ' bad' : ''), ddTxt(g.dd)));
        else if(!g.done && g.label)
          li.appendChild(el('em', 'pdd', g.label));
        gul.appendChild(li);
      });
      zg.appendChild(gul);
      // the timeline: today at the left edge, every dated goal a dot
      var dated = r.goals.filter(function(g){ return g.dd != null; });
      if(dated.length){
        var maxd = Math.max(14, Math.max.apply(null,
          dated.map(function(g){ return g.dd; })));
        var tl = el('div', 'tl');
        tl.appendChild(el('i', 'now'));
        dated.forEach(function(g){
          var pct = Math.max(0, Math.min(100, g.dd / maxd * 100));
          var dot = el('i', g.done ? 'done' : (g.dd < 0 ? 'over' : ''));
          dot.style.left = 'calc(' + pct.toFixed(1) + '% - 5px)';
          dot.title = g.t + (g.label ? ' \\u2014 ' + g.label : '');
          tl.appendChild(dot);
        });
        zg.appendChild(tl);
      }
    } else {
      zg.appendChild(el('p', 'empty',
        'No finish lines yet \\u2014 a date you set yourself is what makes '
        + 'a project real.'));
    }
    var gar = el('div', 'addrow');
    var gi = document.createElement('input');
    gi.placeholder = 'A finish line \\u2014 \\u201cclosed beta on 10 phones\\u201d\\u2026';
    var gd = document.createElement('input'); gd.className = 'due';
    gd.placeholder = 'by when? \\u201cmid-September\\u201d';
    var gb = el('button', 'go', '+ Goal');
    gb.onclick = function(){
      var v = gi.value.trim(); if(!v) return;
      gb.disabled = true;
      post('/api/room/goal', {room: r.name, text: v, due: gd.value.trim()})
        .then(function(){
          gi.value = ''; gd.value = ''; gb.disabled = false;
          toast('Goal set \\u2713'); nudgePoll();
        })
        .catch(function(e){ gb.disabled = false; toast(e.message); });
    };
    gar.appendChild(gi); gar.appendChild(gd); gar.appendChild(gb);
    zg.appendChild(gar);
    root.appendChild(zg);
  }

  // 2 — ask / do
  var z2 = el('section', 'zone z-ask');
  z2.appendChild(el('h2', '', 'Ask / do'));
  var row = el('div', 'askrow');
  var ta = document.createElement('textarea');
  ta.setAttribute('data-mic', '1');
  ta.placeholder = 'Ask about this project, empty your head about it, or say '
    + 'what to run in the repo \\u2014 Claude knows which room this is\\u2026';
  ta.rows = 2;
  var mdl = document.createElement('select');
  [['','Model: auto'],['haiku','Haiku \\u00b7 fastest'],
   ['sonnet','Sonnet \\u00b7 balanced'],['opus','Opus \\u00b7 deepest']]
    .forEach(function(o){
      var op = document.createElement('option');
      op.value = o[0]; op.textContent = o[1]; mdl.appendChild(op);
    });
  // attachments: pick files, or just ⌘V a screenshot into the box
  var afiles = [];
  var af = document.createElement('input');
  af.type = 'file'; af.multiple = true; af.hidden = true;
  af.accept = '.pdf,.png,.jpg,.jpeg,.webp,.gif,.txt,.md,.csv,.docx,.xlsx,.ics';
  var fnote = el('span', 'talknote', '');
  function readF(f){
    return new Promise(function(res, rej){
      var rd = new FileReader();
      rd.onload = function(){ res({name: f.name, data: String(rd.result)}); };
      rd.onerror = rej;
      rd.readAsDataURL(f);
    });
  }
  function fLabel(){
    fnote.textContent = afiles.length
      ? afiles.length + ' attached \\u2713' : '';
  }
  var attach = el('button', '', 'Attach');
  attach.title = 'Attach documents or screenshots to this ask';
  attach.onclick = function(){ af.click(); };
  af.onchange = function(){
    Promise.all(Array.prototype.map.call(af.files, readF))
      .then(function(out){ afiles = afiles.concat(out); fLabel(); af.value = ''; })
      .catch(function(){ toast('Could not read that file'); });
  };
  ta.addEventListener('paste', function(ev){
    var items = Array.prototype.filter.call(
      (ev.clipboardData || {}).items || [],
      function(it){ return it.type && it.type.indexOf('image/') === 0; });
    if(!items.length) return;                // plain text pastes as normal
    ev.preventDefault();
    Promise.all(items.map(function(it){
      var f = it.getAsFile();
      return readF(f).then(function(o){
        o.name = 'pasted-' + Date.now() % 100000 + '.'
          + ((f.type || '').split('/')[1] || 'png').replace('jpeg', 'jpg');
        return o;
      });
    })).then(function(out){
      afiles = afiles.concat(out); fLabel();
      toast('Screenshot attached \\u2713');
    }).catch(function(){ toast('Could not read the paste'); });
  });
  var ask = el('button', 'go', 'Queue it');
  ask.onclick = function(){
    var q = ta.value.trim();
    if(!q && !afiles.length) return;
    ask.disabled = true;
    var ctx = 'About the project \\u201c' + r.name + '\\u201d'
      + (r.wss.length ? ' (workstream' + (r.wss.length > 1 ? 's' : '') + ' \\u201c'
         + r.wss.join('\\u201d, \\u201c') + '\\u201d)' : '')
      + (r.srcpath ? ', folder ' + r.srcpath : '')
      + (r.notes ? '. My room notes for it:\\n' + r.notes + '\\n\\n' : '. ')
      + 'The ask: ' + (q || 'See the attached files.')
      + ' \\u2014 when you write the Outcome, name the project like: workstream \\u201c'
      + (r.wss[0] || r.name) + '\\u201d so it lands back in this room.';
    var chain = afiles.length
      ? post('/api/upload', {files: afiles}).then(function(j){ return j.saved; })
      : Promise.resolve([]);
    chain.then(function(saved){
      return post('/api/queue', {text: ctx, mode: 'just-do-it',
                                 model: mdl.value, files: saved});
    }).then(function(){
      ta.value = ''; ask.disabled = false;
      afiles = []; fLabel();
      toast('Queued \\u2014 run it from the pill below \\u2713'); abPoll();
    }).catch(function(e){ ask.disabled = false; toast(e.message); });
  };
  var dmp = el('button', '', 'Dump it in');
  dmp.title = 'A brain dump about this project \\u2014 Claude sorts every line '
    + 'into the brain and puts its questions in the Outcome';
  dmp.onclick = function(){
    var q = ta.value.trim();
    if(q.length < 8){ toast('Tell me a bit more first'); return; }
    dmp.disabled = true;
    var head = 'This is a brain dump about the project \\u201c' + r.name + '\\u201d'
      + (r.wss.length ? ' (workstream \\u201c' + r.wss.join('\\u201d, \\u201c')
         + '\\u201d)' : '')
      + '. Sort all of it into the brain \\u2014 tasks onto this workstream '
      + 'where they belong, facts and decisions where they live \\u2014 and put '
      + 'any questions in the Outcome. Lose nothing.\\n\\n';
    post('/api/queue', {text: head + q, mode: 'dump', model: mdl.value})
      .then(function(){
        ta.value = ''; dmp.disabled = false;
        toast('Queued as a dump \\u2014 run it from the pill below \\u2713');
        abPoll();
      })
      .catch(function(e){ dmp.disabled = false; toast(e.message); });
  };
  // One box, three verbs. She has one thought at a time; making her pick
  // which of three identical-looking textareas it belongs in was the tax.
  row.appendChild(ta); row.appendChild(mdl);
  row.appendChild(attach); row.appendChild(ask); row.appendChild(dmp);
  if(r.srcpath){
    var run = el('button', '', 'Quick run');
    run.title = 'Run it in ' + r.srcpath;
    run.onclick = function(){
      var t = ta.value.trim();
      if(!t) return;
      if(!confirm('Start Claude Code inside ' + r.srcpath + '? Runs on your Mac, '
                  + 'on your subscription; the repo\\u2019s own CLAUDE.md steers it.'))
        return;
      run.disabled = true;
      post('/api/agent', {job: 'project', path: r.srcpath, text: t, model: mdl.value})
        .then(function(){
          ta.value = ''; run.disabled = false;
          toast('Running in that repo \\u2014 watch the pill below \\u2713');
          setTimeout(abPoll, 800);
        })
        .catch(function(e){ run.disabled = false; toast(e.message); });
    };
    row.appendChild(run);
  }
  row.appendChild(af); row.appendChild(fnote);
  z2.appendChild(row);
  if(r.srcpath){
    // "Sessions" meant conversations on the Sessions page AND one-shot runs
    // here, which is exactly the collision the two names exist to prevent.
    z2.appendChild(el('p', 'hint',
      'Quick run works in ' + r.srcpath + ' and reads your room notes first. '
      + 'For work that takes more than one answer, start a conversation instead.'));
  }
  root.appendChild(z2);

  // 2b — the conversations already open in this room. The Sessions page has
  // always known which room a conversation is in; the room knew nothing back,
  // so a thread paused on a one-line question was invisible from the page
  // that calls itself this project's cockpit.
  if(r.srcname){
    var zc = el('section', 'zone z-convos');
    zc.appendChild(el('h2', '', 'Conversations here'));
    var clist = el('div', 'convos');
    zc.appendChild(clist);
    paintConvos(clist, r.convos || [], r.srcname);
    convoWatch(clist, r.srcname);
    root.appendChild(zc);
  }

  // 3 — the room's memory
  var z3 = el('section', 'zone z-mem');
  z3.appendChild(el('h2', '', 'The room\\u2019s memory'));
  // The memory was a raw markdown textarea, so its own headings showed as
  // "## What do I do post-graduation?" — which is why the big questions
  // looked like there were none. It reads as prose now and only becomes a
  // field when you ask it to.
  var read3 = el('div', 'memread');
  var ta3 = document.createElement('textarea');
  ta3.setAttribute('data-mic', '1');
  ta3.id = 'notes';
  ta3.placeholder = 'Notes that stay with this room \\u2014 decisions, context, '
    + 'preferences. Claude reads them before every session here. '
    + 'Write (urgent) anywhere to bump this project\\u2019s rank.';
  ta3.value = r.notes || '';
  ta3.hidden = true;
  function paintMem(){
    var txt = (r.notes || '').trim();
    if(!txt){
      read3.innerHTML = '<p class="memempty">Nothing held here yet. '
        + 'Anything you write stays with this room, and Claude reads it '
        + 'before every session here.</p>';
    } else {
      read3.innerHTML = mdToHtml(stripOwnTitle(txt, r.name));
    }
  }
  paintMem();
  z3.appendChild(read3);
  z3.appendChild(ta3);
  var nr = el('div', 'noterow');
  var edit = el('button', 'go', 'Edit');
  var save = el('button', 'go', 'Save notes');
  var cancel = el('button', 'flink', 'Cancel');
  var saved = el('span', 'savednote', '');
  save.hidden = true; cancel.hidden = true;
  function setEditing(on){
    ta3.hidden = !on; read3.hidden = on;
    edit.hidden = on; save.hidden = !on; cancel.hidden = !on;
    if(on) ta3.focus();
  }
  edit.onclick = function(){ setEditing(true); };
  cancel.onclick = function(){ ta3.value = r.notes || ''; setEditing(false); };
  save.onclick = function(){
    save.disabled = true;
    post('/api/room/notes', {slug: r.slug, text: ta3.value})
      .then(function(){
        save.disabled = false; r.notes = ta3.value.trim();
        paintMem(); setEditing(false);
        saved.textContent = 'Saved \\u2713';
        setTimeout(function(){ saved.textContent = ''; }, 2500);
        nudgePoll();
      })
      .catch(function(e){ save.disabled = false; toast(e.message); });
  };
  nr.appendChild(edit); nr.appendChild(save); nr.appendChild(cancel);
  nr.appendChild(saved);
  z3.appendChild(nr);
  root.appendChild(z3);

  // 4 — its own brain (the docked docs)
  if(r.srcname){
    var z4 = el('section', 'zone z-brain');
    z4.appendChild(el('h2', '', 'Its own brain'));
    // What the project's brain says about itself, read from the handoff file
    // it generates. This is the part worth reading without opening anything:
    // the worry, the top actions, and what is blocked on her.
    if(r.handoff){
      var ho = el('div', 'hoff');
      if(r.handoff.worry)
        ho.appendChild(el('p', 'hoffworry', r.handoff.worry));
      if(r.handoff.next.length){
        var hul = el('ul', 'hoffnext');
        r.handoff.next.forEach(function(n){
          var li2 = el('li', '', n.t);
          if(n.yours) li2.appendChild(el('span', 'hoffyours', 'only you'));
          hul.appendChild(li2);
        });
        ho.appendChild(hul);
      }
      var hb = [];
      if(r.handoff.questions)
        hb.push(r.handoff.questions + ' decision'
                + (r.handoff.questions === 1 ? '' : 's') + ' waiting on you');
      if(r.handoff.checks)
        hb.push(r.handoff.checks + ' hand-check'
                + (r.handoff.checks === 1 ? '' : 's') + ' unconfirmed');
      if(hb.length)
        ho.appendChild(el('p', 'hoffmeta', hb.join(' \\u00b7 ')));
      var hrow = el('div', 'hoffrow');
      if(r.handoff.page){
        var ob = el('button', 'hoffopen', 'Open its brain');
        ob.title = 'Opens that project\\u2019s own page in your browser';
        ob.onclick = function(){
          post('/api/reveal', {path: r.srcpath + '/brain/index.html'})
            .then(function(){ toast('Opened its brain \\u2713'); })
            .catch(function(e){ toast(e.message); });
        };
        hrow.appendChild(ob);
      }
      if(r.handoff.updated)
        hrow.appendChild(el('span', 'hoffas',
          'its brain, as of ' + agoTxt(r.handoff.updated)));
      ho.appendChild(hrow);
      z4.appendChild(ho);
    }
    if((r.tr || []).length){
      var th = el('h3'); th.textContent = 'Recordings';
      z4.appendChild(th);
      var tl = el('ul', 'docs');
      var kf = (r.keyfiles || []).slice(0, 8);
      // Acting on a recording happens where she finishes reading it: the end
      // of an open transcript carries two doors — a one-shot run that folds
      // it into the folder's files, and a Sessions conversation seeded with
      // it for work that needs back-and-forth.
      function trActs(d){
        var wrap = el('div', 'tract');
        if(r.srcpath){
          var up = el('button', 'go', 'Update the room\\u2019s files from this');
          up.onclick = function(){
            if(!confirm('Start Claude Code inside ' + r.srcpath + '? It reads this '
                        + 'recording and folds it into the files there. Runs on '
                        + 'your Mac, on your subscription.')) return;
            up.disabled = true;
            var p = 'Read ~/life-brain/brain/transcripts/' + d.f
              + ' (transcript of a real conversation). Fold what it answered or '
              + 'decided into this folder\\u2019s files'
              + (kf.length ? ' \\u2014 ' + kf.join(', ') + ' \\u2014' : '')
              + ': mark answered questions with their answers, work new facts '
              + 'and corrections into the sections where they belong, and leave '
              + 'what the transcript doesn\\u2019t touch alone. Then say plainly '
              + 'what changed in each file and what new tasks or open questions '
              + 'came out of it.';
            post('/api/agent', {job: 'project', path: r.srcpath, text: p, model: mdl.value})
              .then(function(){
                up.disabled = false;
                toast('Running in that folder \\u2014 watch the pill below \\u2713');
                setTimeout(abPoll, 800);
              })
              .catch(function(e){ up.disabled = false; toast(e.message); });
          };
          wrap.appendChild(up);
        }
        if(r.srcname){
          var tk = el('button', '', 'Talk about this in Sessions');
          tk.onclick = function(){
            tk.disabled = true;
            var p = 'Read ~/life-brain/brain/transcripts/' + d.f
              + ' (transcript of a real conversation). Tell me briefly what it '
              + 'settles and what it leaves open, then help me act on it.';
            post('/api/sessions/new', {src: r.srcname, text: p, model: mdl.value})
              .then(function(j){
                location.href = 'sessions.html#' + encodeURIComponent(j.id);
              })
              .catch(function(e){ tk.disabled = false; toast(e.message); });
          };
          wrap.appendChild(tk);
        }
        if(r.srcpath && kf.length)
          wrap.appendChild(el('p', 'hint', 'Updates ' + kf.join(' \\u00b7 ')));
        return wrap;
      }
      r.tr.forEach(function(d){
        var li = el('li');
        var open = el('button', 'doclink', d.f.replace(/\\.md$/, ''));
        var body = el('div', 'docbody'); body.hidden = true;
        var loaded = false;
        open.onclick = function(){
          if(loaded){ body.hidden = !body.hidden; return; }
          open.disabled = true;
          fetch('/api/transcript?file=' + encodeURIComponent(d.f))
            .then(function(x){ return x.json(); })
            .then(function(j){
              open.disabled = false;
              if(j.error){ toast(j.error); return; }
              loaded = true; body.innerHTML = j.html;
              if(r.srcpath || r.srcname) body.appendChild(trActs(d));
              body.hidden = false;
            })
            .catch(function(e){ open.disabled = false; toast(e.message); });
        };
        li.appendChild(open);
        li.appendChild(el('span', 'docmeta',
          (d.mins ? d.mins + ' min \\u00b7 ' : '') + agoTxt(d.d)
          + ' \\u00b7 ' + (d.read ? 'summarised' : 'raw')));
        var wk = el('button', 'docreveal', '\\u270e');
        wk.title = 'Work on this \\u2014 prefill the ask box with this transcript';
        wk.onclick = function(){
          var p = 'Read ~/life-brain/brain/transcripts/' + d.f
            + ' (transcript of a real conversation) and apply it here: ';
          ta.value = p;
          ta.scrollIntoView({behavior: 'smooth', block: 'center'});
          ta.focus();
          toast('Say what to change, then run it \\u2713');
        };
        li.appendChild(wk);
        var rvt = el('button', 'docreveal', '\\u2197');
        rvt.title = 'Show this file in Finder';
        rvt.onclick = function(){
          post('/api/reveal', {path: '~/life-brain/brain/transcripts/' + d.f,
                               select: 1})
            .then(function(){ toast('Shown in Finder \\u2713'); })
            .catch(function(e){ toast(e.message); });
        };
        li.appendChild(rvt);
        tl.appendChild(li);
        tl.appendChild(body);
      });
      z4.appendChild(tl);
    }
    if(r.docs.length){
      var dl = el('ul', 'docs');
      // Only the files that moved this week or hold unticked work arrive
      // open; with none of those, the anchors (CLAUDE.md, README) stand in.
      // The rest wait behind one line — thirteen equal rows was the page's
      // biggest dead zone.
      var lead = r.docs.filter(function(d){ return d.live; }).slice(0, 4);
      if(!lead.length) lead = r.docs.slice(0, 3);
      var hid = [];
      r.docs.forEach(function(d){
        var li = el('li');
        if(lead.indexOf(d) < 0){ li.hidden = true; hid.push(li); }
        var open = el('button', 'doclink', d.f);
        var body = el('div', 'docbody'); body.hidden = true;
        var loaded = false;
        open.onclick = function(){
          if(loaded){ body.hidden = !body.hidden; return; }
          open.disabled = true;
          fetch('/api/roomdoc?src=' + encodeURIComponent(r.srcname)
                + '&file=' + encodeURIComponent(d.f))
            .then(function(x){ return x.json(); })
            .then(function(j){
              open.disabled = false;
              if(j.error){ toast(j.error); return; }
              loaded = true; body.innerHTML = j.html; body.hidden = false;
            })
            .catch(function(e){ open.disabled = false; toast(e.message); });
        };
        li.appendChild(open);
        li.appendChild(el('span', 'docmeta', agoTxt(d.d)
                          + (d.n ? ' \\u00b7 ' + d.n + ' unticked' : '')));
        var rv = el('button', 'docreveal', '\\u2197');
        rv.title = 'Reveal in Finder';
        rv.onclick = function(){
          post('/api/reveal', {path: r.srcpath + '/' + d.f, select: 1})
            .then(function(){ toast('Opened in Finder \\u2713'); })
            .catch(function(e){ toast(e.message); });
        };
        li.appendChild(rv);
        dl.appendChild(li);
        dl.appendChild(body);
      });
      z4.appendChild(dl);
      if(hid.length){
        var more = el('button', 'docmore',
          'Show ' + hid.length + ' quieter file' + (hid.length > 1 ? 's' : ''));
        more.onclick = function(){
          var show = hid[0].hidden;
          hid.forEach(function(x){ x.hidden = !show; });
          more.textContent = show
            ? 'Hide the quieter files'
            : 'Show ' + hid.length + ' quieter file'
              + (hid.length > 1 ? 's' : '');
        };
        z4.appendChild(more);
      }
      if(r.docmore > 0)
        z4.appendChild(el('p', 'hint', r.docmore
          + ' more markdown files live in that folder \\u2014 open it above to browse.'));
      z4.appendChild(el('p', 'hint',
        'Docked read-only: the repo stays the source of truth.'));
    } else {
      z4.appendChild(el('p', 'empty', 'No docs found in that folder yet.'));
    }
    root.appendChild(z4);
  }

  // 5 — people in this: who they are TO this project, and whether
  // they've gone quiet on you (people.md's Last dates, for free)
  if(!r.habits){
    var z5 = el('section', 'zone z-people');
    z5.appendChild(el('h2', '', 'People in this'));
    if(r.people.length){
      var pp = el('div', 'ppl');
      r.people.forEach(function(p){
        var a = document.createElement('a');
        a.className = 'pchip';
        a.href = 'map.html#circles'; a.title = 'Open their circle';
        a.appendChild(document.createTextNode(
          p.n + (p.role ? ' \\u00b7 ' + p.role : '')));
        if(p.days != null)
          a.appendChild(el('span', p.days > 7 ? 'pquiet' : '',
            '\\u00a0\\u00b7 ' + (p.days === 0 ? 'spoke today'
              : p.days > 7 ? 'quiet ' + p.days + 'd'
              : 'heard ' + p.days + 'd ago')));
        pp.appendChild(a);
      });
      z5.appendChild(pp);
    }
    if(r.wss.length){
      var pr = el('div', 'addrow');
      var pi = document.createElement('input');
      pi.placeholder = 'Link a person and their role \\u2014 \\u201cDad (tester)\\u201d\\u2026';
      var pb = el('button', 'go', '+ Person');
      pb.onclick = function(){
        var v = pi.value.trim(); if(!v) return;
        var m2 = v.match(/^(.*?)\\s*\\(([^)]+)\\)$/);
        pb.disabled = true;
        post('/api/ws/person', {name: r.wss[0],
                                person: m2 ? m2[1].trim() : v,
                                role: m2 ? m2[2].trim() : ''})
          .then(function(){
            pi.value = ''; pb.disabled = false;
            toast('Linked \\u2713'); nudgePoll();
          })
          .catch(function(e){ pb.disabled = false; toast(e.message); });
      };
      pr.appendChild(pi); pr.appendChild(pb);
      z5.appendChild(pr);
    }
    var fr = el('div', 'addrow');
    var fi = document.createElement('input');
    fi.setAttribute('data-mic', '1');
    fi.placeholder = 'Log feedback \\u2014 \\u201cDad: crashed on login\\u201d\\u2026';
    var fbtn = el('button', 'go', 'Log it');
    fbtn.onclick = function(){
      var v = fi.value.trim(); if(!v) return;
      fbtn.disabled = true;
      post('/api/room/feedback', {slug: r.slug, text: v})
        .then(function(){
          fi.value = ''; fbtn.disabled = false;
          toast('Logged \\u2014 every session here reads it \\u2713'); nudgePoll();
        })
        .catch(function(e){ fbtn.disabled = false; toast(e.message); });
    };
    fr.appendChild(fi); fr.appendChild(fbtn);
    z5.appendChild(fr);
    root.appendChild(z5);
  }

  // 6 — pulse
  var z6 = el('section', 'zone z-pulse');
  z6.appendChild(el('h2', '', 'Pulse'));
  var pv = el('div', 'pulse');
  if(r.pulse){
    pv.appendChild(el('div', '', 'Last commit ' + agoTxt(r.pulse.last) + ':'));
    var ul = el('ul');
    r.pulse.subs.forEach(function(c){
      var li = el('li');
      li.appendChild(el('span', 'cd', c[0]));
      li.appendChild(el('span', '', c[1]));
      ul.appendChild(li);
    });
    pv.appendChild(ul);
  } else if(r.changed){
    pv.appendChild(el('div', '', 'A file changed ' + agoTxt(r.changed)
      + ' \\u2014 no git history in this folder.'));
  } else {
    pv.appendChild(el('div', 'empty', 'No folder is linked to this room.'));
  }
  if(r.ship)
    pv.appendChild(el('div', 'shipline' + (r.ship.behind > 0 ? ' warn' : ''),
      r.ship.behind > 0
        ? 'The build you delivered is ' + r.ship.behind + ' commit'
          + (r.ship.behind === 1 ? '' : 's')
          + ' behind \\u2014 your testers haven\\u2019t seen recent work.'
        : 'Your testers are on the latest build.'));
  z6.appendChild(pv);
  root.appendChild(z6);

  if(!root.classList.contains('bigq')){
    // Two independent columns — see the layout CSS for why.
    var colL = el('div', 'rcol rcolL'), colR = el('div', 'rcol rcolR');
    ['z-next', 'z-goals', 'z-ask', 'z-convos'].forEach(function(c){
      var n = root.querySelector('.' + c); if(n) colL.appendChild(n);
    });
    ['z-mem', 'z-brain', 'z-people', 'z-pulse'].forEach(function(c){
      var n = root.querySelector('.' + c); if(n) colR.appendChild(n);
    });
    root.appendChild(colL); root.appendChild(colR);
    // Every box folds on its heading, and the room remembers which ones
    // you keep shut.
    root.querySelectorAll('.zone').forEach(function(z){
      var h = z.querySelector(':scope > h2');
      if(!h) return;
      var cls = (z.className.match(/z-[a-z]+/) || [''])[0];
      var key = 'roomshut:' + r.slug + ':' + cls;
      try{ if(localStorage.getItem(key) === '1') z.classList.add('shut'); }
      catch(e){}
      h.onclick = function(){
        var shut = z.classList.toggle('shut');
        try{
          if(shut) localStorage.setItem(key, '1');
          else localStorage.removeItem(key);
        }catch(e){}
      };
    });
    // A memory that has grown long starts folded to a page.
    setTimeout(function(){
      var mr = root.querySelector('.z-mem .memread');
      if(!mr || mr.scrollHeight <= 520) return;
      mr.classList.add('clamp');
      var mb = el('button', 'memmore', 'Show the whole memory');
      mb.onclick = function(){
        var on = mr.classList.toggle('clamp');
        mb.textContent = on ? 'Show the whole memory' : 'Fold it back up';
      };
      mr.after(mb);
    }, 0);
  }
}

// ---- search across all the brains ----------------------------------------
var searchT = null;
document.getElementById('search').addEventListener('input', function(){
  var q = this.value.trim();
  if(searchT) clearTimeout(searchT);
  if(q.length < 2){ route(); return; }
  searchT = setTimeout(function(){
    fetch('/api/brainsearch?q=' + encodeURIComponent(q))
      .then(function(r){ return r.json(); })
      .then(function(j){
        var root = document.getElementById('results');
        root.innerHTML = '';
        root.appendChild(el('p', 'strip',
          (j.hits.length >= 60 ? 'First 60 hits' : j.hits.length + ' hit'
           + (j.hits.length === 1 ? '' : 's')) + ' across your brains:'));
        var SRC = {};
        ROOMS.forEach(function(r){ if(r.srcname) SRC[r.srcname] = r.srcpath; });
        j.hits.forEach(function(h){
          var d = el('div', 'hit');
          d.appendChild(el('div', 'where', h.source + ' \\u00b7 ' + h.file
                           + ':' + h.line));
          d.appendChild(el('div', '', h.text));
          if(SRC[h.source]){
            d.style.cursor = 'pointer';
            d.title = 'Reveal in Finder';
            d.onclick = function(){
              post('/api/reveal', {path: SRC[h.source] + '/' + h.file,
                                   select: 1})
                .then(function(){ toast('Opened in Finder \\u2713'); })
                .catch(function(e){ toast(e.message); });
            };
          }
          root.appendChild(d);
        });
        if(!j.hits.length) root.appendChild(el('p', 'empty', 'Nothing found.'));
        document.getElementById('floor').hidden = true;
        document.getElementById('roomview').hidden = true;
        root.hidden = false;
      })
      .catch(function(){});
  }, 280);
});

// ---- one hash router ------------------------------------------------------
var BARTXT = document.getElementById('barcount').textContent;
function showFloor(){
  document.getElementById('results').hidden = true;
  document.getElementById('roomview').hidden = true;
  document.getElementById('floor').hidden = false;
  document.getElementById('bartitle').textContent = 'The rooms';
  document.getElementById('barcount').textContent = BARTXT;
  document.getElementById('backlink').querySelector('span').textContent = 'Brain';
  document.getElementById('backlink').href = 'index.html';
  CUR = null;
}
function route(){
  var m = (location.hash || '').match(/^#room\\/([a-z0-9-]+)$/);
  if(m && byslug[m[1]]){
    document.getElementById('floor').hidden = true;
    document.getElementById('results').hidden = true;
    document.getElementById('search').value = '';
    drawRoom(byslug[m[1]]);
    document.getElementById('roomview').hidden = false;
    document.getElementById('bartitle').textContent = byslug[m[1]].name;
    document.getElementById('barcount').textContent =
      byslug[m[1]].open ? byslug[m[1]].open + ' open here' : '';
    var bl = document.getElementById('backlink');
    bl.querySelector('span').textContent = 'Rooms';
    bl.href = '#';
    bl.onclick = function(ev){ ev.preventDefault(); location.hash = ''; };
    scrollTo(0, 0);
  } else {
    var bl2 = document.getElementById('backlink');
    bl2.onclick = null;
    showFloor();
  }
}
addEventListener('hashchange', route);
drawFloor();
route();

// ---- version poll: the page refreshes itself when the brain changes ------
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
addEventListener('pagehide', function(){
  try { sessionStorage.setItem('rooms-hash', location.hash || ''); } catch(e){}
});
try {
  var saved = sessionStorage.getItem('rooms-hash');
  if(saved && !location.hash && saved.indexOf('#room/') === 0){
    location.hash = saved;
  }
} catch(e){}

// ---- the same queue pill the map has -------------------------------------
// ---- the conversations open in this room ---------------------------------
// Baked into the page so the floor plan's state lines are true on load, then
// refreshed live while a room is open: a conversation's state changes on its
// own schedule and nothing rebuilds this page when it does.
function paintConvos(box, list, srcname){
  box.innerHTML = '';
  if(!list.length){
    box.appendChild(el('p', 'empty',
      'Nothing open in this room. A quick run above does one thing; a '
      + 'conversation keeps its context across turns.'));
  }
  list.forEach(function(c){
    var a = document.createElement('a');
    a.className = 'convo st-' + c.state;
    a.href = 'sessions.html#' + encodeURIComponent(c.id);
    a.appendChild(el('i', 'cdot'));
    var mid = el('span', 'cmid');
    var top = el('span', 'ctop', c.topic);
    if(c.hands) top.appendChild(el('span', 'chands', 'has the hands'));
    mid.appendChild(top);
    // The question in full, not a state word: it is usually one line, and
    // reading it is most of the work of answering it.
    mid.appendChild(el('span', 'cline',
      c.state === 'ask' ? (c.question || 'Asked you something and stopped.')
                        : (c.line || '')));
    a.appendChild(mid);
    a.appendChild(el('span', 'cwhen', c.state === 'ask' ? 'answer it'
                                    : c.state === 'working' ? 'working' : ''));
    box.appendChild(a);
  });
  var f = document.createElement('a');
  f.className = 'convoall'; f.href = 'sessions.html';
  f.textContent = list.length ? 'Open Sessions' : 'Start one on Sessions';
  box.appendChild(f);
}
function convoWatch(box, srcname){
  if(window.__cvT) clearInterval(window.__cvT);
  var tick = function(){
    if(document.hidden) return;
    if(!box.isConnected){ clearInterval(window.__cvT); window.__cvT = null; return; }
    fetch('/api/sessions/room?src=' + encodeURIComponent(srcname))
      .then(function(x){ return x.json(); })
      .then(function(j){
        var fp = JSON.stringify(j.convos || []);
        if(fp === box.__fp) return;      // don't rebuild identical DOM
        box.__fp = fp; paintConvos(box, j.convos || [], srcname);
      })
      .catch(function(){});
  };
  window.__cvT = setInterval(tick, 8000);
  tick();
}

var agentbar = document.getElementById('agentbar'), abTimer = null;
function abPoll(){
  fetch('/api/agent').then(function(r){ return r.json(); }).then(function(j){
    if(j.running){
      agentbar.hidden = false;
      document.getElementById('ab-txt').textContent = 'Claude is working\\u2026';
      document.getElementById('ab-run').style.display = 'none';
      if(!abTimer) abTimer = setInterval(abPoll, 3000);
    } else {
      if(abTimer){ clearInterval(abTimer); abTimer = null; }
      if(j.pending > 0){
        agentbar.hidden = false;
        document.getElementById('ab-txt').textContent = j.pending + ' waiting for Claude';
        document.getElementById('ab-run').style.display = '';
      } else agentbar.hidden = true;
    }
  }).catch(function(){ agentbar.hidden = true; });
}
document.getElementById('ab-run').onclick = function(){
  if(!confirm('Start Claude Code to work the queue? Runs on your Mac, on your subscription.')) return;
  post('/api/agent', {job: 'queue'}).then(function(){ abPoll(); }).catch(function(){});
};
abPoll();
</script>
__TOUR__</body></html>
"""


if __name__ == "__main__":
    path, n = build()
    print(f"Built {path} — {n} room{'s' if n != 1 else ''}")

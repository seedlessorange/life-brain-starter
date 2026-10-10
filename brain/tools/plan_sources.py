"""What the morning plan checks, and what it looked at (her ask, 8 Oct 2026).

Two halves of one list.

The switches. Each thing the 7am plan reads, on or off under the gear
("What the morning plan checks"). The core four have no switch: there is no
plan without her projects, yesterday's plan, the shape of her week and what
she asked for. A source that belongs to a part (People, the Kitchen...)
follows that part's switch in parts.py. Config `plan_sources` holds only
what differs from the default: {"weather": false, "mail": true}.

The record. After a plan run, plain code reads the run's own transcript
(the tool calls Claude Code saved under ~/.claude/projects) and writes
brain/.plan-trace.json: when it ran, which sources it looked at, which were
on but not looked at. Today shows it under the plan as "How this plan was
made". It is what the run did, never the run's account of itself, and it
keeps source names only: no file contents, no commands.

Mail is the one source with a job of its own: "Who emailed you" runs the
header check each morning before the plan (email_read.check, mac_only), from
the Mail app's index, through the server, which holds the Full Disk Access
that index needs. Never the password, so never a Touch ID prompt with nobody
there, and never a subject or a body.

    python3 brain/tools/plan_sources.py               what is on (the /today run reads this)
    python3 brain/tools/plan_sources.py off weather   switch one off (or on)
    python3 brain/tools/plan_sources.py mail          who is waiting on a reply by email
    python3 brain/tools/plan_sources.py mail-check    the 7am header check (morning.sh)
    python3 brain/tools/plan_sources.py trace [--result FILE | --session ID] [--by morning]
    python3 brain/tools/plan_sources.py show          print the record
"""
import glob
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
BRAIN = os.path.dirname(HERE)
ROOT = os.path.dirname(BRAIN)
CONFIG = os.path.join(BRAIN, "config.json")
TODAY = os.path.join(BRAIN, "today.md")
TRACE = os.path.join(BRAIN, ".plan-trace.json")
sys.path.insert(0, HERE)

# id, name, the faint line, on by default, the part it follows, has a switch.
# Order is the page's order: the core first, then the switches, then the
# ones a part decides.
SOURCES = (
    ("projects", "Your projects", "Tasks, due dates and who has the ball", True, "", False),
    ("yesterday", "Yesterday's plan", "What you ticked and what carried over", True, "", False),
    ("about", "About you and your week", "The house you're in and the shape of your week", True, "", False),
    ("asks", "Your requests", "What you sent from the page, and its questions to you", True, "", False),
    ("calendar", "Calendar", "Today and the next seven days", True, "", True),
    ("folders", "Project folders", "The to-do files in the folders you track", True, "", True),
    ("goals", "Goals", "The finish lines you set", True, "", True),
    ("track", "Your track record", "How much of past plans you finished", True, "", True),
    ("weather", "Weather", "For anything outdoors", True, "", True),
    ("voice", "What you told the orb", "Yesterday's spoken notes", True, "", True),
    ("mail", "Who emailed you", "Who wrote and is waiting on a reply, from the Mail app. Never a subject or a line of text", False, "", True),
    ("journal", "Your journal", "One plain line about yesterday. The entry itself only in a plan you start", True, "journal", False),
    ("people", "People", "Owed replies, birthdays, who has gone quiet", True, "people", False),
    ("habits", "Habits", "So the plan never lists them as tasks", True, "habits", False),
    ("routines", "Routines", "Today's skincare and training lines", True, "routines", False),
    ("kitchen", "Meal plan", "Tonight's dinner", True, "kitchen", False),
    ("season", "Season list", "Plans for this stretch", True, "season", False),
    ("jobs", "Job hunt", "Applications to chase", True, "jobs", False),
)
BY = {s[0]: s for s in SOURCES}
NAMES = {s[0]: s[1] for s in SOURCES}

# Which source a tool call belongs to, from the file it read or the command
# it ran. First match per rule; one call can touch several sources.
RULES = (
    ("yesterday", r"brain/today\.md"),
    ("asks", r"model\.py\s+--asks|brain/queue"),
    ("people", r"model\.py\s+--people|people\.md|\.people-digest\.md"),
    ("projects", r"model\.py(?!\s+--(?:asks|people))|workstreams\.md|blind_spots"),
    ("about", r"about-me\.md|config\.json|interests\.md|week-plan\.md"),
    ("folders", r"synced\.md"),
    ("goals", r"goals\.md"),
    ("track", r"calibrate\.py"),
    ("calendar", r"calendar_read\.py"),
    ("weather", r"weather\.py|\.weather\.json"),
    ("voice", r"brain/voice/"),
    ("mail", r"plan_sources\.py\s+mail\b|\.email-read\.json"),
    ("journal", r"journal-trace\.md|brain/journal/"),
    ("habits", r"habits\.md"),
    ("routines", r"routines\.py|brain/routines/"),
    ("kitchen", r"brain/cooking/"),
    ("season", r"season\.md|events\.md"),
    ("jobs", r"jobs\.py|jobs\.md|\.jobs-state"),
)
_RULES = [(sid, re.compile(rx)) for sid, rx in RULES]
# Commands that read nothing for the plan: saving, rebuilding, recording.
_IGNORE = re.compile(r"^\s*(git\s+(add|commit|push)|python3\s+\S*(rebuild|build|"
                     r"plan_sources)\.py\s*(--|$|trace|show))")


def load():
    try:
        with open(CONFIG, encoding="utf-8") as f:
            return json.load(f) or {}
    except (OSError, ValueError):
        return {}


def on(sid, cfg=None):
    """Whether the morning plan checks this source. Unknown or unreadable
    counts as on, like parts.py: a config problem never hides anything,
    except mail, which is off unless she turned it on."""
    c = load() if cfg is None else (cfg or {})
    s = BY.get(sid)
    if not s:
        return True
    try:
        if s[4]:
            import parts
            if not parts.on(s[4], c):
                return False
        if not s[5]:
            return True
        if unset(sid, c):
            return False
        v = (c.get("plan_sources") or {}).get(sid)
        return s[3] if v is None else bool(v)
    except Exception:                                       # noqa: BLE001
        return s[3]


def unset(sid, cfg):
    """Why a source can't be read in this brain yet, or "": a calendar never
    connected, no project folders tracked. Off until it is, so a brain
    without one never reads "on, but not looked at" every morning."""
    if sid == "calendar" and not cfg.get("calendar"):
        return "No calendar connected"
    if sid == "folders" and not cfg.get("sources"):
        return "No project folders tracked yet"
    return ""


def why_off(sid, cfg=None):
    """Plain words for why a source is off: its own switch or its part's."""
    c = load() if cfg is None else (cfg or {})
    s = BY.get(sid)
    if s and s[4]:
        import parts
        if not parts.on(s[4], c):
            return f"the {parts.NAMES.get(s[4], s[4])} part is off"
    return unset(sid, c).lower() or "switched off"


def mail_ready(cfg=None):
    """(ready, why not): the 7am check needs mail reading on, with the Mac's
    Mail app, at a privacy level that allows the mail check."""
    c = load() if cfg is None else (cfg or {})
    rd = ((c.get("email") or {}).get("read") or {})
    if not rd.get("on"):
        return False, "Needs Mail in turned on under Connections first"
    if not rd.get("mac_mail"):
        return False, "Needs the Mac's Mail app switched on for reading"
    try:
        import privacy
        if not privacy.value("mail_check"):
            return False, "Your privacy level has the mail check off"
    except Exception:                                       # noqa: BLE001
        pass
    return True, ""


def setting(cfg, sid, value):
    """("plan_sources", {...}) for switching one source. Pure, like
    parts.setting, so the server and the command line write it their way."""
    s = BY.get(sid)
    if not s or not s[5]:
        raise ValueError("the morning plan has no switch called %r" % sid)
    if value and sid == "mail":
        ok, why = mail_ready(cfg)
        if not ok:
            raise ValueError(why)
    p = dict(cfg.get("plan_sources") or {})
    if bool(value) == s[3]:
        p.pop(sid, None)
    else:
        p[sid] = bool(value)
    return "plan_sources", p


def set_on(sid, value):
    cfg = load()
    key, val = setting(cfg, sid, value)
    cfg[key] = val
    import config_io
    config_io.save(CONFIG, cfg)


def summary(cfg=None):
    c = load() if cfg is None else cfg
    ons = [NAMES[s[0]] for s in SOURCES if on(s[0], c)]
    offs = [f"{NAMES[s[0]]} ({why_off(s[0], c)})" for s in SOURCES
            if not on(s[0], c)]
    out = ["The morning plan checks: " + ", ".join(ons) + "."]
    if offs:
        out.append("Off: " + ", ".join(offs) + ". Skip the step for each one"
                   " and leave it out of the plan.")
    return "\n".join(out)


# ---- mail -----------------------------------------------------------------

def mail_line(cfg=None):
    """Who is waiting on her reply by email, from the last header check:
    names and a time, never anything a sender wrote."""
    if not on("mail", cfg):
        return "Who emailed you is off."
    try:
        import email_read
        st = email_read.last_check()
    except Exception:                                       # noqa: BLE001
        st = {}
    if not st.get("checked"):
        return "No mail check has run yet. Leave email out of today's plan."
    when = st["checked"][:16].replace("T", " ")
    # Only this morning's look counts: a list from days ago names people
    # who have long since had their reply (28 Sep's sat ten days).
    if st["checked"][:10] != datetime.now().date().isoformat():
        return (f"No mail check today (the last was {when}). Leave email out"
                " of today's plan.")
    owed = [re.sub(r"[\u2800\u200b-\u200f\u2060\ufeff]", "", n).strip()
            for n in (st.get("owed") or [])]
    owed = [n for n in owed if n]
    if not owed:
        return f"Nobody is waiting on your reply by email (checked {when})."
    return (f"Waiting on your reply by email: {', '.join(owed)} (checked {when})."
            " Names only: the brain never sees a subject or a line of the mail.")


def mail_check(cfg=None):
    """The 7am header check, asked of the server: it holds the Full Disk
    Access the Mail app's index needs, and the morning job does not. A
    server that is down, or older than this, just answers no."""
    c = load() if cfg is None else cfg
    if not on("mail", c):
        print("mail: the morning plan's mail switch is off")
        return 0
    ok, why = mail_ready(c)
    if not ok:
        print("mail: " + why)
        return 1
    import urllib.request
    port = int(os.environ.get("BRAIN_PORT", "7718"))
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}/api/email/morning", data=b"{}",
        headers={"Content-Type": "application/json"}, method="POST")
    import urllib.error
    try:
        with urllib.request.urlopen(req, timeout=150) as r:
            j = json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as exc:
        # A refusal carries its reason (a switch off, the alarm waiting).
        try:
            j = json.loads(exc.read() or b"{}")
        except ValueError:
            j = {"error": f"the server refused ({exc.code})"}
    except Exception as exc:                                # noqa: BLE001
        print(f"mail: the server did not answer ({type(exc).__name__})")
        return 1
    if j.get("error"):
        print("mail: " + str(j["error"]))
        return 1
    print(f"mail: {j.get('scanned', 0)} messages, "
          f"{len(j.get('owed') or [])} waiting on a reply")
    return 0


# ---- the record -------------------------------------------------------------

def projects_dir():
    """Where Claude Code keeps this brain's transcripts."""
    base = os.environ.get("CLAUDE_CONFIG_DIR") or os.path.expanduser("~/.claude")
    return os.path.join(base, "projects",
                        re.sub(r"[^A-Za-z0-9]", "-", os.path.realpath(ROOT)))


def fingerprint(today_md=None):
    """Which plan this is: its date, title and opening paragraph. Ticks, the
    evening check's markers and swaps leave these alone; a new plan run
    rewrites them, so a record never describes a plan it didn't make."""
    if today_md is None:
        try:
            with open(TODAY, encoding="utf-8") as f:
                today_md = f.read()
        except OSError:
            return ""
    m = re.search(r"updated:\s*(\S+)", today_md or "")
    lines = [ln.strip() for ln in (today_md or "").split("\n")]
    head, para = "", ""
    for i, ln in enumerate(lines):
        if ln.startswith("# "):
            head = ln
            for nxt in lines[i + 1:]:
                if nxt and not nxt.startswith("#"):
                    para = nxt
                    break
                if nxt.startswith("#"):
                    break
            break
    if not head:
        return ""
    raw = "|".join((m.group(1) if m else "", head, para))
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def _calls(path):
    """(timestamp, tool, target) for each tool call in a transcript, and
    the timestamps of its writes to today.md."""
    calls, writes, first = [], [], ""
    with open(path, encoding="utf-8", errors="replace") as f:
        for ln in f:
            if '"tool_use"' not in ln and not first:
                try:
                    first = json.loads(ln).get("timestamp") or ""
                except ValueError:
                    pass
                continue
            if '"tool_use"' not in ln:
                continue
            try:
                d = json.loads(ln)
            except ValueError:
                continue
            ts = d.get("timestamp") or ""
            first = first or ts
            for b in ((d.get("message") or {}).get("content") or []):
                if not isinstance(b, dict) or b.get("type") != "tool_use":
                    continue
                i = b.get("input") or {}
                name = b.get("name") or ""
                tgt = str(i.get("file_path") or i.get("command") or i.get("pattern")
                          or i.get("path") or "")
                if name in ("Write", "Edit", "MultiEdit"):
                    if tgt.endswith("brain/today.md"):
                        writes.append(ts)
                    continue
                if name == "Grep" and i.get("path"):
                    tgt = f'{i.get("pattern", "")} {i["path"]}'
                calls.append((ts, name, tgt))
    return first, calls, writes


def _find_session(within_s=900):
    """The newest transcript that wrote today.md in the last quarter hour:
    the run that is asking, when it records itself."""
    best, best_ts = "", ""
    now = datetime.now().timestamp()
    for p in sorted(glob.glob(os.path.join(projects_dir(), "*.jsonl")),
                    key=os.path.getmtime, reverse=True)[:12]:
        if now - os.path.getmtime(p) > within_s:
            break
        try:
            _first, _calls_, writes = _calls(p)
        except OSError:
            continue
        if writes and writes[-1] > best_ts:
            best, best_ts = p, writes[-1]
    return best


def _local(ts):
    try:
        return (datetime.fromisoformat(ts.replace("Z", "+00:00"))
                .astimezone().replace(tzinfo=None))
    except (ValueError, AttributeError):
        return None


def trace(session="", result="", by=""):
    """Record what the latest plan run looked at, from its own transcript."""
    if result and not session:
        try:
            with open(result, encoding="utf-8") as f:
                session = (json.load(f) or {}).get("session_id") or ""
        except (OSError, ValueError):
            session = ""
    path = (os.path.join(projects_dir(), session + ".jsonl") if session
            else _find_session())
    if not path or not os.path.isfile(path):
        print("trace: no transcript found for this plan")
        return 1
    first, calls, writes = _calls(path)
    if not writes:
        print("trace: that run never wrote today's plan")
        return 1
    seen, entry = [], False
    for _ts, _tool, tgt in calls:
        if _IGNORE.search(tgt):
            continue
        # The entry itself, not the one-line summary: only an attended run
        # can open it, and the record says which it was.
        entry = entry or bool(re.search(r"brain/journal/", tgt))
        for sid, rx in _RULES:
            if sid not in seen and rx.search(tgt):
                seen.append(sid)
    cfg = load()
    t0, t1 = _local(first), _local(writes[-1])
    rec = {
        "fp": fingerprint(),
        "session": os.path.basename(path)[:-6],
        "by": by,
        "started": t0.isoformat(timespec="seconds") if t0 else "",
        "wrote": t1.isoformat(timespec="seconds") if t1 else "",
        "seconds": int((t1 - t0).total_seconds()) if t0 and t1 else 0,
        "calls": len(calls),
        "looked": [s[0] for s in SOURCES if s[0] in seen],
        "skipped": [s[0] for s in SOURCES if s[0] not in seen and on(s[0], cfg)],
        "off": [s[0] for s in SOURCES if not on(s[0], cfg)],
        "journal_entry": entry,
    }
    tmp = TRACE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(rec, f, indent=2)
        f.write("\n")
    os.replace(tmp, TRACE)
    print(f"trace: {len(rec['looked'])} sources looked at, "
          f"{len(rec['skipped'])} on but not looked at")
    return 0


def record(today_md=None):
    """The record for the plan on the page, or {} when it describes another."""
    try:
        with open(TRACE, encoding="utf-8") as f:
            rec = json.load(f) or {}
    except (OSError, ValueError):
        return {}
    fp = fingerprint(today_md)
    return rec if fp and rec.get("fp") == fp else {}


def _names(ids, rec=None):
    out = []
    for i in ids:
        if i == "journal" and rec is not None:
            out.append("Your journal (the entry)" if rec.get("journal_entry")
                       else "Your journal (its one-line summary)")
        elif i in NAMES:
            out.append(NAMES[i])
    return out


def fold_html(today_md, e=None, presenting=False):
    """How this plan was made, under the plan on Today."""
    import html
    esc = e or html.escape
    rec = record(today_md)
    hood = ('<a href="#/hood" data-hoodgo="plansources">Choose what it '
            'checks</a>')
    if not rec:
        return ('<details class="plantrace"><summary>How this plan was made'
                '</summary><p class="lcfaint">No record for this version of the'
                ' plan: it was written or changed outside a plan run. '
                + hood + '.</p></details>')
    wrote = rec.get("wrote") or rec.get("started") or ""
    at = wrote[11:16] if len(wrote) >= 16 else ""
    secs = int(rec.get("seconds") or 0)
    took = (f"{secs // 60} min {secs % 60} s" if secs >= 60 else f"{secs} s") if secs else ""
    who = {"morning": "the 7am run", "page": "Refresh plan"}.get(rec.get("by"), "")
    bits = [b for b in (at, who, took) if b]
    rows = [("Looked at", _names(rec.get("looked") or [], rec))]
    if rec.get("skipped"):
        rows.append(("On, but not looked at", _names(rec["skipped"])))
    if rec.get("off"):
        rows.append(("Switched off", _names(rec["off"])))
    body = "".join(
        f'<p class="ptrow"><b>{esc(lab)}</b> {esc(" · ".join(ns))}</p>'
        for lab, ns in rows if ns)
    return ('<details class="plantrace"><summary>How this plan was made'
            + (' <span class="lcfaint">&middot; ' + esc(", ".join(bits))
               + '</span>' if bits else '') + '</summary>' + body
            + '<p class="ptrow"><b>Never</b> Your mailbox or your chat apps:'
            ' every plan run is refused those folders.</p>'
            '<p class="lcfaint">Read from the run&rsquo;s own record of what it'
            ' opened, not from what it says about itself. Each of the three'
            ' shows its project on its line. ' + hood + '.</p></details>')


def main(argv):
    if not argv:
        print(summary())
        return 0
    cmd = argv[0]
    if cmd in ("-h", "--help"):
        print(__doc__)
        return 0
    if cmd in ("on", "off") and len(argv) == 2:
        try:
            set_on(argv[1], cmd == "on")
        except ValueError as exc:
            print(exc)
            return 2
        print("%s is %s. Rebuild the page: python3 brain/tools/rebuild.py"
              % (NAMES[argv[1]], cmd))
        return 0
    if cmd == "mail":
        print(mail_line())
        return 0
    if cmd == "mail-check":
        return mail_check()
    if cmd == "trace":
        opts = dict(zip(argv[1::2], argv[2::2]))
        return trace(session=opts.get("--session", ""),
                     result=opts.get("--result", ""), by=opts.get("--by", ""))
    if cmd == "show":
        try:
            with open(TRACE, encoding="utf-8") as f:
                print(f.read().strip())
        except OSError:
            print("No record yet.")
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

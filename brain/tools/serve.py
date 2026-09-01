#!/usr/bin/env python3
"""Serve the brain locally so the page can actually write things.

    python3 brain/tools/serve.py          # http://127.0.0.1:7718

This tiny server is the whole trick. A page opened with file:// cannot write
anything — browsers deliberately forbid it, and rightly so, or any web page you
opened could rewrite your files. So the page is not opened as a file: it is
served by this script, which you started, and which is allowed to do what you
are allowed to do. The page POSTs; this writes markdown.

No AI runs in here. Nothing leaves your machine. It listens on 127.0.0.1,
which means your laptop and nothing else on the network can reach it.

The one exception is the "Work the queue now" button, which starts Claude Code
on your machine — and that is Claude Code doing the work, on your normal
subscription, not this server.
"""

import base64
import functools
import json
import mimetypes
import os
import re
import subprocess
import sys
import threading
import webbrowser
from datetime import date, datetime, timedelta
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

# Calendar apps subscribing to season.ics expect the real content type.
mimetypes.add_type("text/calendar", ".ics")

HERE = os.path.dirname(os.path.abspath(__file__))
BRAIN = os.path.dirname(HERE)
ROOT = os.path.dirname(BRAIN)
sys.path.insert(0, HERE)

import md as MD        # noqa: E402  (shared: the page and the writer must agree on task keys)
import model as M      # noqa: E402
import rooms as ROOMS  # noqa: E402  (a room's live conversations, read the same way both pages read them)
import sessions as SESS  # noqa: E402  (the Sessions page: concurrent conversations)
import usage           # noqa: E402  (the one ledger every model call writes to)
import llm             # noqa: E402  (routes the small no-tool jobs: Haiku, or local Ollama)

PORT = int(os.environ.get("BRAIN_PORT", "7718"))
# 127.0.0.1 = this Mac only, and that is the right default: the page has no
# login, so whoever can reach it can read and write the brain. For phone
# access prefer `tailscale serve --bg 7718` (tailnet-only, HTTPS, keeps this
# bind). BRAIN_BIND=0.0.0.0 opens it to whatever network you are on — only
# ever do that on a network where you trust every device.
BIND = os.environ.get("BRAIN_BIND", "127.0.0.1")

# --- request-origin guard ---------------------------------------------------
# The page has no login, so the only thing standing between the brain and a
# malicious web page you happen to be visiting is: does the request actually
# come from your own page? Two headers answer that. Origin catches classic
# cross-site POSTs; Host catches DNS-rebinding (where a site rebinds its name
# to 127.0.0.1 — the browser still sends the site's name in Host). Populated
# in main() from the addresses actually bound. When BIND is 0.0.0.0 the owner
# has deliberately opened it network-wide and no header can tell friend from
# foe, so the guard steps aside (documented as the risky mode).
ALLOWED_HOSTS = {"127.0.0.1", "localhost", "::1"}
GUARD_ENFORCED = BIND != "0.0.0.0"


def _host_only(value):
    """The bare hostname from a Host or Origin header — no scheme, no port."""
    v = (value or "").strip()
    if "://" in v:
        v = v.split("://", 1)[1]
    v = v.split("/", 1)[0]
    if v.startswith("["):                 # [::1]:7718  ->  ::1
        return v[1:].split("]", 1)[0].lower()
    if v.count(":") == 1:                 # host:port  ->  host  (not bare IPv6)
        head, _, port = v.partition(":")
        # Only a numeric port is a port. "127.0.0.1:7718.evil.com" is not a
        # host of ours with a port — it must NOT reduce to "127.0.0.1".
        if port.isdigit():
            v = head
    return v.lower()


def request_is_own(host_header, origin_header, allowed):
    """True if this request could only have come from the owner's own page.

    Reject when the browser reached us under a name that isn't ours
    (rebinding), or when an Origin from another site is present (CSRF). A
    request with neither header set is a same-origin navigation and passes.
    """
    if host_header and _host_only(host_header) not in allowed:
        return False
    o = (origin_header or "").strip()
    if o and o.lower() != "null" and _host_only(o) not in allowed:
        return False
    return True


def tailnet_ip():
    """(address, is_tailscale_installed). Phones on the same tailnet can reach
    the address; nothing else can, and the traffic is WireGuard-encrypted.

    The second value separates "installed but not connected" — worth a note,
    it means the phone URL they expect is missing — from "never installed",
    which is the ordinary case and deserves no remark at all. Someone opening
    this for the first time should not be told about software they don't have.
    """
    installed = False
    for exe in ("/Applications/Tailscale.app/Contents/MacOS/Tailscale",
                "tailscale",
                r"C:\Program Files\Tailscale\tailscale.exe"):
        try:
            r = subprocess.run([exe, "ip", "-4"], capture_output=True, text=True, timeout=10)
        except Exception:
            continue
        installed = True
        ip = (r.stdout or "").strip().split("\n")[0].strip()
        if r.returncode == 0 and ip.startswith("100."):
            return ip, True
    return None, installed


def resolve_binds(want):
    """Which addresses to listen on.

    localhost is ALWAYS one of them. Binding only to the Tailscale address
    silently breaks every bookmark to 127.0.0.1, which is how this is opened
    at the desk — so the tailnet address is an addition, never a replacement.
    """
    binds, note = ["127.0.0.1"], None
    if want == "tailnet":
        ip, installed = tailnet_ip()
        if ip:
            binds.append(ip)
        elif installed:
            note = "Tailscale is installed but not connected, so the page is only available on this machine."
    elif want not in ("127.0.0.1", "localhost"):
        binds = [want]              # an explicit address means the caller meant it
    return binds, note


def open_folder(path, select=False):
    """Show a folder in the OS file manager (Finder / Explorer / whatever).
    With select, show the file itself selected in its folder instead of
    handing it to the default app."""
    if sys.platform == "darwin":
        subprocess.Popen(["open", "-R", path] if select else ["open", path])
    elif os.name == "nt":
        if select:
            subprocess.Popen(["explorer", "/select,", path])
        else:
            os.startfile(path)  # noqa — Windows-only, absent elsewhere
    else:
        subprocess.Popen(["xdg-open",
                          os.path.dirname(path) if select else path])
QUEUE = os.path.join(BRAIN, "queue")
WORKSTREAMS = os.path.join(BRAIN, "workstreams.md")
RUNS = os.path.join(BRAIN, ".agent-runs.json")

# Files the page is allowed to tick a checkbox in. An allowlist, because "the
# page told me which file" is not a good enough reason to write to a path.
TICKABLE = {"workstreams.md", "next.md", "waiting.md", "inbox.md", "today.md",
            "people.md", "questions.md", "goals.md", "season.md"}
MODES = {"just-do-it", "investigate", "draft", "question", "tidy", "dump", "chat",
         "journal", "critic", "consult"}
# Which model runs a job. Filing and tidying do not need the expensive one,
# and picking per job is the difference between a cheap week and a costly one.
MODELS = {"haiku", "sonnet", "opus"}
MAX_BODY = 2 * 1024 * 1024

_agent = {"running": False, "proc": None, "lines": [], "started": None,
          "job": None, "finished": False, "summary": None, "cost": None,
          "seconds": None}


# --------------------------------------------------------------------------
# helpers

def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def write(path, text):
    # The temp name carries the thread id: this server is threaded, and two
    # writers sharing one `.tmp` truncate each other's half-written file.
    tmp = f"{path}.{threading.get_ident()}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, path)


# Every page write is read-modify-write on a markdown file, and the server is
# threaded: two quick ticks used to read the same file and then write over
# each other, so one of them vanished and the next one landed on "that item
# has changed". Hold this across the whole read-modify-write and a burst of
# clicks behaves like the sequence it looked like.
EDIT = threading.RLock()


def serialized(fn):
    """One writer at a time. The lock is re-entrant, so a writer that calls
    another (set_ball calls set_field twice) still passes straight through."""
    @functools.wraps(fn)
    def go(*a, **kw):
        with EDIT:
            return fn(*a, **kw)
    return go


def rebuild(map_too=True):
    """Regenerate the pages. A stale page is the one failure this whole thing
    exists to prevent, so every writer calls this before it answers — except
    the map, whose requests defer it: the map shows the change optimistically
    and reloads itself once /api/version says the fresh page landed, so a drag
    never sits through the ~10 s regeneration."""
    if getattr(_req_ctx, "defer_rebuild", False):
        _rebuild_soon()
        return
    _rb["building"] = True
    try:
        for job in (["build.py"] + (["map.py", "rooms.py", "proto.py"] if map_too else [])):
            try:
                subprocess.run([sys.executable, os.path.join(HERE, job)],
                               capture_output=True, timeout=60)
            except Exception:
                pass
    finally:
        _rb["building"] = False


_req_ctx = threading.local()          # per-request: does this caller defer?
_rb = {"building": False, "again": False}
_rb_lock = threading.Lock()


def _rebuild_note(msg):
    """Rebuild failures go somewhere a person can find them."""
    try:
        with open(os.path.join(BRAIN, ".rebuild-errors.log"), "a",
                  encoding="utf-8") as fh:
            fh.write(f"{datetime.now().isoformat(timespec='seconds')}  {msg}\n")
    except Exception:
        pass


def _rebuild_soon():
    """One background rebuild at a time; writes that land mid-build queue a
    single follow-up pass, so the last state always wins and never races."""
    with _rb_lock:
        if _rb["building"]:
            _rb["again"] = True
            return
        _rb["building"] = True

    def go():
        while True:
            for job in ("build.py", "map.py", "rooms.py", "proto.py"):
                try:
                    r = subprocess.run([sys.executable, os.path.join(HERE, job)],
                                       capture_output=True, timeout=90, text=True)
                    if r.returncode != 0:
                        _rebuild_note(f"{job} exited {r.returncode}: "
                                      + (r.stderr or "")[-400:])
                except Exception as exc:
                    # A rebuild that fails silently is why the page sat stale
                    # for a whole session while every write "succeeded".
                    _rebuild_note(f"{job} raised {type(exc).__name__}: {exc}")
            with _rb_lock:
                if _rb["again"]:
                    _rb["again"] = False
                    continue
                _rb["building"] = False
                return

    threading.Thread(target=go, daemon=True).start()


def email_send_ready():
    """Is there a mail account with its app password still in the Keychain?
    Reading borrows that same credential, so this gates both."""
    try:
        import email_send
        return any(email_send.kc_get(a["address"]) for a in email_send.accounts())
    except Exception:                                    # noqa: BLE001
        return False


def load_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def save_json(path, obj):
    write(path, json.dumps(obj, indent=2) + "\n")


def slug(s, n=44):
    s = re.sub(r"[^a-zA-Z0-9]+", "-", (s or "").lower()).strip("-")
    return s[:n].rstrip("-") or "request"


# --------------------------------------------------------------------------
# writers

def tick(src, key, done):
    """Flip a checkbox, found by the hash of its own text rather than by line
    number — checks get reordered, and a tick landing on the wrong line is
    worse than one that fails to land."""
    task_action(src, key, "done" if done else "undone")


@serialized
def task_action(src, key, action, until="", text=""):
    """Ticking is not the only way a task ends.

    Three of them are real: you did it, you cannot start it yet, or it turned
    out not to be yours. Only offering "done" makes the list lie, because the
    honest state of "put my school deadlines in" in August is neither done
    nor undone — it is waiting for a syllabus that does not exist yet.
    """
    if src not in TICKABLE:
        raise ValueError(f"not a file the page may write to: {src}")
    if action not in ("done", "undone", "defer", "drop", "due", "undue",
                      "est", "unest", "edit", "carry", "unpark", "next"):
        raise ValueError("unknown action")
    path = os.path.join(BRAIN, src)
    lines = read(path).split("\n")
    hits = []
    for i, line in enumerate(lines):
        m = re.match(r"^(\s*[-*]\s+)\[([ xX])\]\s+(.*)$", line)
        if m and MD.taskkey(_bare(m.group(3))) == key:
            hits.append((i, m))
    if not hits:
        raise ValueError("that item has changed — reload the page")
    if len(hits) > 1:
        raise ValueError("two items have identical wording; make one of them "
                         "different so the action knows where to land")
    i, m = hits[0]
    bare = _bare(m.group(3))
    today = date.today().isoformat()
    # The time estimate is stripped by _bare (so the key stays stable), but it
    # is not a state — setting a deadline or parking a task must not silently
    # erase how long it takes. Carry it across every action that keeps the task.
    m_est = re.search(r"~\s*(\d+h\d*|\d+m)\b", m.group(3), re.I)
    keep = f" ~{m_est.group(1)}" if m_est else ""
    # (urgent) is her own word for priority and it is not a completion state
    # either: a tick followed by an untick used to erase it, so a task came
    # back from the sofa quietly demoted. Carried the same way as the size.
    urg = " (urgent)" if re.search(r"\(urgent\)", m.group(3), re.I) else ""
    keep = urg + keep
    # A season item's memory — who it was with, when it was planned — must
    # survive its tick: the end-of-season retrospective is made of exactly
    # these. Only suffixes _bare stripped are re-added, so no duplicates.
    sk = ""
    for pref in ("with", "when", "planned"):
        m_sz = re.search(r"\(%s: ([^)]+)\)" % pref, m.group(3))
        if m_sz and (pref == "with" or M.parse_due(m_sz.group(1))):
            sk += " " + m_sz.group(0)

    m_rep = (src == "season.md") and re.search(
        r"\(repeat: (weekly|fortnightly|monthly)\)", m.group(3), re.I)

    if action == "done" and m_rep:
        # A recurring season item never reaches [x]: the tick stamps today
        # into (did: …), the slot clears, and the item returns to the tray
        # for its next round — one line forever, so twin wording (which the
        # tick hashes cannot tell apart) can never appear.
        m_did = re.search(r"\(did: ([^)]+)\)", m.group(3))
        dates = (m_did.group(1).split() if m_did else []) + [today]
        txt = re.sub(r"\s*\((?:did|planned): [^)]+\)", "", m.group(3)).strip()
        lines[i] = f"{m.group(1)}[ ] {txt} (did: {' '.join(dates)})"
    elif action == "done":
        # `keep` here too. Every other branch carries the estimate across;
        # this one dropped it, so a tick followed by an untick erased how
        # long the task takes — and the week forecast is built out of exactly
        # those numbers. Ticking from the phone makes that round trip common.
        lines[i] = f"{m.group(1)}[x] {bare}{keep}{sk}"
    elif action == "next":
        # The commonest way a task ends: finished, and it grew a follow-up.
        # One gesture ticks this line and files the next one right under it,
        # same project, optionally parked until the day it becomes real.
        t = (text or "").strip()
        if not t:
            raise ValueError("give the follow-up task")
        lines[i] = f"{m.group(1)}[x] {bare}"
        follow = f"{m.group(1)}[ ] {t}"
        d = M.parse_date(until) if until else None
        if d and d > date.today():
            follow += f" (waiting until {d.isoformat()})"
        lines.insert(i + 1, follow)
    elif action == "undone" and m_rep and re.search(r"\(did: ", m.group(3)):
        # Un-ticking a recurring item takes back the LAST stamp only.
        m_did = re.search(r"\(did: ([^)]+)\)", m.group(3))
        dates = m_did.group(1).split()[:-1]
        txt = re.sub(r"\s*\(did: [^)]+\)", "", m.group(3)).strip()
        lines[i] = (f"{m.group(1)}[ ] {txt}"
                    + (f" (did: {' '.join(dates)})" if dates else ""))
    elif action == "undone":
        lines[i] = f"{m.group(1)}[ ] {bare}{keep}{sk}"
    elif action == "defer":
        d = M.parse_date(until)
        if not d:
            raise ValueError("give a date to wait until")
        if d <= date.today():
            raise ValueError("pick a date in the future")
        lines[i] = f"{m.group(1)}[ ] {bare}{keep} (waiting until {d.isoformat()})"
    elif action == "due":
        pd = M.parse_due(until, date.today())
        if not pd:
            raise ValueError("give a date, a range (2026-09-10..2026-09-20), or "
                             "a window like 'this week' or 'mid-September'")
        # Resolve a fuzzy window to concrete dates so it stays put instead of
        # rolling forever; a single day stays a single day.
        val = (pd["start"].isoformat() if pd["start"] == pd["end"]
               else pd["start"].isoformat() + ".." + pd["end"].isoformat())
        lines[i] = f"{m.group(1)}[ ] {bare}{keep} (due {val})"
    elif action == "undue":
        lines[i] = f"{m.group(1)}[ ] {bare}{keep}"
    elif action == "est":
        try:
            mins = int(until or 0)
        except ValueError:
            mins = 0
        if mins <= 0:
            raise ValueError("give a time in minutes")
        # Estimate rides on the text as a ~token; keep any (due …) suffix in
        # place so a deadline and a time can live on the same task.
        txt = re.sub(r"\s*~\s*(?:\d+h\d*|\d+m)\b", "", m.group(3), flags=re.I).strip()
        tok = "~" + M.fmt_dur(mins)
        mdue = re.search(r"\s*\(due [^)]+\)\s*$", txt)
        if mdue:
            txt = f"{txt[:mdue.start()].rstrip()} {tok} {txt[mdue.start():].strip()}"
        else:
            txt = f"{txt} {tok}"
        lines[i] = f"{m.group(1)}[{m.group(2)}] {txt}"
    elif action == "unest":
        txt = re.sub(r"\s*~\s*(?:\d+h\d*|\d+m)\b", "", m.group(3), flags=re.I).strip()
        lines[i] = f"{m.group(1)}[{m.group(2)}] {txt}"
    elif action == "unpark":
        # Parking was a one-way door: nothing in the UI could bring a task
        # back before its date. Strips only the waiting-until, so a deadline
        # or an estimate on the same line survives.
        txt = re.sub(r"\s*\(waiting until \d{4}-\d{2}-\d{2}\)\s*$", "",
                     m.group(3)).strip()
        lines[i] = f"{m.group(1)}[{m.group(2)}] {txt}"
    elif action == "carry":
        # The evening check's "still matters": stays unticked, and the marker
        # tells tomorrow's plan this was a deliberate carry, not drift.
        lines[i] = f"{m.group(1)}[ ] {bare}{keep} (carrying {today})"
    elif action == "edit":
        # Rewrite the task's own words; the suffixes that are state — urgency,
        # estimate, deadline, waiting-until — survive the rewording untouched.
        new = (until or "").strip()
        if not new:
            raise ValueError("give the new wording")
        if "\n" in new or len(new) > 500:
            raise ValueError("one line, under 500 characters")
        kept = []
        # Urgency is state, not wording. Fixing a typo used to quietly clear it,
        # which drops the task down the ranking for a reason she never chose.
        if re.search(r"\(urgent\)", m.group(3), re.I):
            kept.append("(urgent)")
        mm = re.search(r"~\s*(?:\d+h\d*m?|\d+m)\b", m.group(3), re.I)
        if mm:
            kept.append(mm.group(0).strip())
        mm = re.search(r"\(due ([^)]+)\)", m.group(3))
        if mm and M.parse_due(mm.group(1)):
            kept.append(mm.group(0).strip())
        mm = re.search(r"\(by ([^)]+)\)", m.group(3))
        if mm and M.parse_due(mm.group(1)):
            kept.append(mm.group(0).strip())
        mm = re.search(r"\(waiting until \d{4}-\d{2}-\d{2}\)", m.group(3))
        if mm:
            kept.append(mm.group(0).strip())
        # The evening check's roll-forward marker is state too — a typo fix
        # must not turn a deliberate carry back into drift.
        mm = re.search(r"\(carrying \d{4}-\d{2}-\d{2}\)", m.group(3))
        if mm:
            kept.append(mm.group(0).strip())
        if sk:
            kept.append(sk.strip())
        lines[i] = f"{m.group(1)}[{m.group(2)}] " + " ".join([new] + kept)
    else:
        # Ticked so it leaves the list, annotated so the record stays honest.
        # Never deleted — a task that vanishes is one you cannot argue with.
        lines[i] = f"{m.group(1)}[x] {bare} (dropped {today})"
    write(path, "\n".join(lines))

    # A season item that happened WITH people is the cheapest truth about the
    # People page: their Last becomes today and nobody owes a reply. Names
    # that don't match anyone ("MBA friends") just don't match — this is a
    # bonus, never an error.
    if src == "season.md" and action == "done":
        m_w = re.search(r"\(with: ([^)]+)\)", m.group(3))
        for nm in (m_w.group(1).split(",") if m_w else []):
            nm = nm.strip()
            try:
                person_spoke(nm)
            except Exception:
                # "Casey" should still find "## Casey Ember" — but only
                # when the first name points at exactly one person.
                try:
                    heads = [MD.plain(h.group(1)) for h in re.finditer(
                        r"^##\s+(.*)$",
                        read(os.path.join(BRAIN, "people.md")), re.M)]
                    hits = [h for h in heads
                            if h.split()[0].lower() == nm.lower()]
                    if len(hits) == 1:
                        person_spoke(hits[0])
                except Exception:
                    pass

    if src == "workstreams.md" and action in ("done", "defer", "drop"):
        owner = _owning_workstream(lines, i)
        if owner:
            set_field(owner, "Touched", today)
            # "Next" must never name something already finished. The hero and
            # every row show that field, so a stale one puts a done task at
            # the top of her day — which is exactly what happened to the
            # Zephyr email once TapGate stepped aside.
            _advance_next(owner, bare)

    # A plan item on Today is usually a copy of a workstream task. Ticking
    # the copy must clear the original too, or "done" on Today quietly
    # stays open on the Plate — the exact lie this file exists to prevent.
    # Matching is by the same text-hash; a reworded plan line simply won't
    # match, which is why /today quotes task wording exactly.
    if src == "today.md" and action in ("done", "undone"):
        try:
            task_action("workstreams.md", key, action)
        except ValueError:
            # The exact-hash mirror only works while /today quotes the task
            # verbatim, and a run that paraphrases ("Send email to Zephyr
            # confirming Tuesday" for "Send email to Zephyr (De Lane)
            # confirming Tuesday vineyard visit") silently leaves the
            # original open, so the page keeps offering work she has done.
            # Fall back to the words that carry the meaning.
            try:
                _mirror_by_words(_bare(m.group(3)), action)
            except Exception:
                pass


def task_progress(src, key, who="", days=7, rewrite=""):
    """Half a task done, and the other half is somebody else's move.

    Ticking is for finished and parking is for "not yet mine to start".
    Neither says the most ordinary thing that happens to a real task: she did
    her part, the next move belongs to a person, and she wants it off her
    screen until it is worth a chase. Recording that took four separate
    actions — reword the task, park it, flip the ball, stamp the date — which
    is exactly why it never got recorded and the list drifted out of true.

    One call: the words become what is actually left, the task waits until the
    check-back day, and the workstream's ball moves with its Since date so the
    chase reminder has something to chase.
    """
    from datetime import timedelta
    who = (who or "").strip()
    if not who:
        raise ValueError("say who the next move belongs to")
    if "\n" in who or len(who) > 60:
        raise ValueError("a name, not a paragraph")
    try:
        days = int(days or 7)
    except (TypeError, ValueError):
        days = 7
    days = max(1, min(365, days))
    until = (date.today() + timedelta(days=days)).isoformat()

    # Reword first, because it changes the words the key is hashed from.
    rewrite = (rewrite or "").strip()
    if rewrite:
        task_action(src, key, "edit", rewrite)
        # Hash the bare text, exactly as the lookup does — hashing the raw
        # rewrite (with ~est / (due …) still attached) orphans the key and
        # leaves the task reworded but never parked.
        key = MD.taskkey(_bare(rewrite))
    task_action(src, key, "defer", until)

    # The ball is the whole point, and Since is what makes it chaseable — the
    # two never move apart.
    if src == "workstreams.md":
        lines = read(os.path.join(BRAIN, src)).split("\n")
        for i, line in enumerate(lines):
            m = re.match(r"^(\s*[-*]\s+)\[([ xX])\]\s+(.*)$", line)
            if m and MD.taskkey(_bare(m.group(3))) == key:
                owner = _owning_workstream(lines, i)
                if owner:
                    set_field(owner, "Ball", f"Them — {who}")
                    set_field(owner, "Since", date.today().isoformat())
                    set_field(owner, "Touched", date.today().isoformat())
                break
    return {"until": until, "who": who}


_MIRROR_STOP = {"the", "a", "an", "to", "for", "and", "with", "from", "into",
                "this", "that", "your", "you", "it", "in", "on", "of", "by",
                "is", "are", "be", "at", "or", "as", "if", "so", "then"}


def _sig(text):
    return {w for w in re.findall(r"[a-zà-ÿ0-9]+", (text or "").lower())
            if len(w) >= 3 and w not in _MIRROR_STOP}


def _mirror_by_words(plan_text, action):
    """Tick the workstream task a plan line is clearly a copy of. Requires a
    strong overlap and exactly one candidate — a guess that ticks the wrong
    task is worse than a mirror that fails."""
    want = _sig(plan_text)
    if len(want) < 3:
        return
    lines = read(WORKSTREAMS).split("\n")
    hits = []
    for j, line in enumerate(lines):
        mm = re.match(r"^(\s*[-*]\s+)\[([ xX])\]\s+(.*)$", line)
        if not mm:
            continue
        got = _sig(_bare(mm.group(3)))
        if not got:
            continue
        overlap = len(want & got) / max(len(want), 1)
        if overlap >= 0.6 and len(want & got) >= 3:
            hits.append((j, mm, overlap))
    if len(hits) != 1:
        return                        # ambiguous: leave it alone
    j, mm, _ = hits[0]
    bare2 = _bare(mm.group(3))
    lines[j] = (f"{mm.group(1)}[x] {bare2}" if action == "done"
                else f"{mm.group(1)}[ ] {mm.group(3)}")
    write(WORKSTREAMS, "\n".join(lines))
    owner = _owning_workstream(lines, j)
    if owner:
        set_field(owner, "Touched", date.today().isoformat())
        if action == "done":
            _advance_next(owner, bare2)


def _advance_next(owner, finished_text):
    """If a workstream's Next line describes the task just finished, move it
    on to the first task still open — or clear it when nothing is left."""
    want = _sig(finished_text)
    if not want:
        return
    lines = read(WORKSTREAMS).split("\n")
    start = None
    for i, line in enumerate(lines):
        h = re.match(r"^##\s+(.*)$", line.strip())
        if h and MD.plain(h.group(1)).strip().lower() == (owner or "").strip().lower():
            start = i
            break
    if start is None:
        return
    end = len(lines)
    for j in range(start + 1, len(lines)):
        if lines[j].startswith("## "):
            end = j
            break
    cur = ""
    for j in range(start + 1, end):
        mf = re.match(r"^\s*-\s+\*\*Next:\*\*\s*(.*)$", lines[j])
        if mf:
            cur = mf.group(1).strip()
            break
    if not cur:
        return
    got = _sig(MD.plain(cur))
    if not got or len(want & got) / max(len(want), 1) < 0.6:
        return                        # Next is about something else: leave it
    nxt = ""
    for j in range(start + 1, end):
        mt = re.match(r"^\s*[-*]\s+\[ \]\s+(.*)$", lines[j])
        if mt:
            t = _bare(mt.group(1))
            if not re.search(r"\(waiting until", mt.group(1)):
                nxt = MD.plain(t)
                break
    set_field(owner, "Next", nxt)


def _bare(text):
    """A task's own words, without any suffix the page added. One definition,
    in md.py, because serve.py, the renderer and the evening check all hash it
    and any drift between them lands every action on "that item has changed"."""
    return MD.bare(text)


# --------------------------------------------------------------------------
# editing today's plan — thumb-work, never a model call

PLAN_UNDO = os.path.join(BRAIN, ".plan-undo.json")
WEEK = os.path.join(BRAIN, "week-plan.md")


def _plan_snapshot(ttext):
    """One level of undo: today.md and week-plan.md as they were before the
    last plan edit. A file, not memory, so it survives the page reload every
    edit triggers."""
    try:
        wtext = read(WEEK)
    except Exception:
        wtext = None
    tmp = PLAN_UNDO + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"today": ttext, "week": wtext}, f)
    os.replace(tmp, PLAN_UNDO)


def _plan_trail(lines, note, head="## Changed today"):
    """A dated line under the trail heading, so the evening check, /wrap and
    calibrate read plan edits as decisions rather than drift."""
    entry = f"- {datetime.now().strftime('%H:%M')} {note}"
    for i, ln in enumerate(lines):
        if ln.strip().lower() == head.lower():
            j = i + 1
            while j < len(lines) and not lines[j].startswith("## "):
                j += 1
            while j > i + 1 and not lines[j - 1].strip():
                j -= 1
            lines.insert(j, entry)
            return
    while lines and not lines[-1].strip():
        lines.pop()
    lines += ["", head, "", entry, ""]


def _find_plan_task(lines, key):
    """The one checkbox line this key names, or a clear error."""
    hits = []
    for j, ln in enumerate(lines):
        mm = re.match(r"^(\s*[-*]\s+)\[([ xX])\]\s+(.*)$", ln)
        if mm and MD.taskkey(_bare(mm.group(3))) == key:
            hits.append((j, mm))
    if not hits:
        raise ValueError("that item has changed — reload the page")
    if len(hits) > 1:
        raise ValueError("two items have identical wording; make one "
                         "different so the edit knows where to land")
    return hits[0]


def _into_today(lines, text):
    """A task line joins today's plan, after the last task of the first
    checkbox block."""
    last = None
    for j, ln in enumerate(lines):
        if re.match(r"^\s*[-*]\s+\[[ xX]\]\s+", ln):
            last = j
        elif last is not None and ln.startswith("## "):
            break
    if last is None:
        raise ValueError("no plan to add to — write today's plan first")
    lines.insert(last + 1, f"- [ ] {text}")


def _week_file_add(d, task_line):
    """File a task under its day in week-plan.md, creating whatever is
    missing. Headings are `## Thursday 2026-08-27` — found by the ISO date."""
    try:
        text = read(WEEK)
    except Exception:
        text = ("# Week plan\n\nThe week's sketch, one day per heading. "
                "Reality wins; the morning plan reads this as your intent.\n")
    lines = text.split("\n")
    for i, ln in enumerate(lines):
        if ln.startswith("## ") and d.isoformat() in ln:
            j = i + 1
            while j < len(lines) and not lines[j].startswith("## "):
                j += 1
            while j > i + 1 and not lines[j - 1].strip():
                j -= 1
            lines.insert(j, task_line)
            break
    else:
        while lines and not lines[-1].strip():
            lines.pop()
        lines += ["", f"## {d.strftime('%A')} {d.isoformat()}", "", task_line]
    write(WEEK, "\n".join(lines) + "\n")


@serialized
def plan_edit(op, key="", pick="", day=""):
    """Kick, swap, reorder, reschedule or pull today's plan around — plain
    file edits on today.md (and week-plan.md), instant and token-free. A
    kicked line is recorded in the day's own trail and its task stays
    untouched in the workstream: a plan entry is a pointer, not the task."""
    tpath = os.path.join(BRAIN, "today.md")

    if op == "undo":
        try:
            with open(PLAN_UNDO, encoding="utf-8") as f:
                snap = json.load(f)
        except Exception:
            raise ValueError("nothing to undo")
        write(tpath, snap["today"])
        if snap.get("week") is not None:
            write(WEEK, snap["week"])
        elif os.path.exists(WEEK):
            os.remove(WEEK)        # the edit being undone is what created it
        os.remove(PLAN_UNDO)
        return "Put back as it was ✓"

    ttext = read(tpath)

    def short(s):
        return s if len(s) <= 60 else s[:60].rsplit(" ", 1)[0] + "…"

    # The week's side of the board: a placed task moves days, comes into
    # today, or leaves the sketch. Same file honesty as today's: a trail,
    # never a silent vanish.
    if op in ("wday", "wkick", "wtoday"):
        try:
            wtext = read(WEEK)
        except Exception:
            raise ValueError("no week plan yet")
        _plan_snapshot(ttext)
        wlines = wtext.split("\n")
        i, m = _find_plan_task(wlines, key)
        gone = short(_bare(m.group(3)))
        if op == "wkick":
            del wlines[i]
            _plan_trail(wlines, f"removed “{gone}” from the sketch",
                        head="## Changed")
            write(WEEK, "\n".join(wlines))
            said = "Out of the week ✓ — its task still lives in the plate"
        elif op == "wtoday":
            tlines = ttext.split("\n")
            if any(MD.taskkey(_bare(mm.group(1))) == key
                   for mm in (re.match(r"^\s*[-*]\s+\[[ xX]\]\s+(.*)$", ln)
                              for ln in tlines) if mm):
                raise ValueError("already on today's plan")
            _into_today(tlines, m.group(3).strip())
            del wlines[i]
            _plan_trail(tlines, f"pulled “{gone}” in from the week")
            write(WEEK, "\n".join(wlines))
            write(tpath, "\n".join(tlines))
            said = "On today's plan ✓"
        else:
            d = M.parse_date(day)
            if not d or d <= date.today():
                raise ValueError("pick a coming day")
            del wlines[i]
            write(WEEK, "\n".join(wlines))
            _week_file_add(d, f"- [{m.group(2)}] {m.group(3).strip()}")
            said = f"Moved to {d.strftime('%A')} ✓"
        return said

    lines = ttext.split("\n")
    i = m = None
    if op != "pull":
        i, m = _find_plan_task(lines, key)

    _plan_snapshot(ttext)

    if op in ("kick", "swap"):
        b = M.bench(M.load(), ttext)
        if op == "swap":
            rep = next((x for x in b if x["key"] == pick), None)
            if not rep:
                raise ValueError("that bench item has changed — reopen the list")
        else:
            rep = b[0] if b else None
        gone = short(_bare(m.group(3)))
        if rep:
            lines[i] = f"{m.group(1)}[ ] {rep['text']}"
            _plan_trail(lines, f"kicked “{gone}” — “{short(rep['text'])}” "
                               f"(from {rep['ws']}) took the slot")
            said = f"Kicked ✓ — “{short(rep['text'])}” slid in"
        else:
            del lines[i]
            _plan_trail(lines, f"kicked “{gone}” — nothing benched, the day shrinks")
            said = "Kicked ✓ — the day just got shorter"

    elif op in ("up", "down"):
        step = -1 if op == "up" else 1
        j = i + step
        while 0 <= j < len(lines) and not lines[j].startswith("## "):
            if re.match(r"^\s*[-*]\s+\[[ xX]\]\s+", lines[j]):
                lines[i], lines[j] = lines[j], lines[i]
                break
            j += step
        else:
            raise ValueError("already at the edge of its list")
        said = "Moved ✓"

    elif op == "day":
        d = M.parse_date(day)
        if not d or d <= date.today():
            raise ValueError("pick a coming day")
        txt = re.sub(r"\s*\(carrying \d{4}-\d{2}-\d{2}\)", "", m.group(3)).strip()
        _week_file_add(d, f"- [ ] {txt}")
        gone = short(_bare(m.group(3)))
        del lines[i]
        _plan_trail(lines, f"moved “{gone}” to {d.strftime('%A %-d %B')}")
        said = f"Moved to {d.strftime('%A')} ✓"

    elif op == "pull":
        b = M.bench(M.load(), ttext)
        rep = next((x for x in b if x["key"] == pick), None)
        if not rep:
            raise ValueError("that bench item has changed — reopen the list")
        _into_today(lines, rep["text"])
        _plan_trail(lines, f"pulled in “{short(rep['text'])}” (from {rep['ws']})")
        said = "Added ✓"

    else:
        raise ValueError("unknown plan edit")

    write(tpath, "\n".join(lines))
    return said


def _owning_workstream(lines, idx):
    for j in range(idx, -1, -1):
        h = re.match(r"^##\s+(.*)$", lines[j].strip())
        if h:
            return MD.plain(h.group(1))
    return None


@serialized
def set_field(name, field, value):
    """Set `- **Field:** value` inside a workstream, adding it if absent."""
    lines = read(WORKSTREAMS).split("\n")
    start = None
    for i, line in enumerate(lines):
        h = re.match(r"^##\s+(.*)$", line.strip())
        if h and MD.plain(h.group(1)).lower() == (name or "").strip().lower():
            start = i
            break
    if start is None:
        raise ValueError(f"no workstream called {name!r}")
    end = len(lines)
    for j in range(start + 1, len(lines)):
        if re.match(r"^##\s+", lines[j].strip()):
            end = j
            break

    pat = re.compile(r"^\s*-\s+\*\*" + re.escape(field) + r":\*\*", re.I)
    for j in range(start + 1, end):
        if pat.match(lines[j]):
            lines[j] = f"- **{field}:** {value}"
            write(WORKSTREAMS, "\n".join(lines))
            return
    # Not there — put it after the last existing field, or straight after the
    # heading, so the field block stays together and the file stays readable.
    insert = start + 1
    for j in range(start + 1, end):
        if re.match(r"^\s*-\s+\*\*[A-Za-z ]+:\*\*", lines[j]):
            insert = j + 1
    lines.insert(insert, f"- **{field}:** {value}")
    write(WORKSTREAMS, "\n".join(lines))


@serialized
def set_ball(name, ball):
    who = ""
    if ball == "them":
        cur = [w for w in M.load() if w["name"].lower() == name.lower()]
        who = cur[0]["ball_who"] if cur else ""
    label = {"me": "Me", "them": "Them", "nobody": "Nobody"}[ball]
    set_field(name, "Ball", f"{label} — {who}" if who else label)
    # "Since" is what makes a chase reminder possible, so the two move together.
    set_field(name, "Since", date.today().isoformat())
    if ball == "me":
        set_field(name, "Touched", date.today().isoformat())


@serialized
def capture(text):
    path = os.path.join(BRAIN, "inbox.md")
    body = read(path) if os.path.exists(path) else "# Inbox\n"
    if not body.endswith("\n"):
        body += "\n"
    write(path, body + f"- [ ] {text.strip()}  ({date.today().isoformat()})\n")


@serialized
def set_habit_target(name, target):
    """Change a habit's weekly target in place. The log is untouched — past
    weeks get judged against the target she had then, near enough."""
    try:
        n = max(1, min(7, int(target)))
    except (TypeError, ValueError):
        raise ValueError("target must be a number of days, 1 to 7")
    path = os.path.join(BRAIN, "habits.md")
    lines = read(path).split("\n")
    start = None
    for i, line in enumerate(lines):
        h = re.match(r"^##\s+(.*)$", line.strip())
        if h and MD.plain(h.group(1)).lower() == (name or "").strip().lower():
            start = i
            break
    if start is None:
        raise ValueError(f"no habit called {name!r}")
    for j in range(start + 1, len(lines)):
        if re.match(r"^##\s+", lines[j].strip()):
            break
        if re.match(r"^\s*-\s+\*\*Target:\*\*", lines[j], re.I):
            lines[j] = f"- **Target:** {n}"
            write(path, "\n".join(lines))
            return n
    raise ValueError(f"habit {name!r} has no Target line")


@serialized
def toggle_habit(name):
    """Add or remove today's date on a habit's Log line. A toggle, not an
    append, so a mis-tap undoes itself instead of needing a text editor."""
    path = os.path.join(BRAIN, "habits.md")
    lines = read(path).split("\n")
    start = None
    for i, line in enumerate(lines):
        h = re.match(r"^##\s+(.*)$", line.strip())
        if h and MD.plain(h.group(1)).lower() == (name or "").strip().lower():
            start = i
            break
    if start is None:
        raise ValueError(f"no habit called {name!r}")
    today = date.today().isoformat()
    for j in range(start + 1, len(lines)):
        if re.match(r"^##\s+", lines[j].strip()):
            break
        m = re.match(r"^(\s*-\s+\*\*Log:\*\*)\s*(.*)$", lines[j], re.I)
        if m:
            # Deduplicate: a Log line that somehow holds a date twice would
            # otherwise be un-untoggleable (remove() takes one copy, the
            # other keeps the button stuck on "done").
            dates = sorted(set(re.findall(r"\d{4}-\d{2}-\d{2}", m.group(2))))
            if today in dates:
                dates.remove(today)
            else:
                dates.append(today)
            dates.sort(reverse=True)
            lines[j] = f"{m.group(1)} {', '.join(dates)}".rstrip()
            write(path, "\n".join(lines))
            return today in dates
    raise ValueError(f"habit {name!r} has no Log line")


@serialized
def add_task(name, text, due=""):
    """Append a `- [ ]` to a workstream. The task goes at the end of that
    workstream's block, so it lands under the right heading no matter what
    else is in the file. A due phrase ("friday", "2026-09-15", "this week")
    becomes a real (due …) suffix — dated at birth beats dated never."""
    text = " ".join((text or "").split())
    if not text:
        raise ValueError("nothing to add")
    if (due or "").strip():
        pd = M.parse_due(due)
        if not pd:
            raise ValueError("that deadline didn't parse — a date, 'friday', "
                             "'this week' and 'mid-September' all work")
        val = (pd["start"].isoformat() if pd["start"] == pd["end"]
               else pd["start"].isoformat() + ".." + pd["end"].isoformat())
        text += f" (due {val})"
    lines = read(WORKSTREAMS).split("\n")
    start = None
    for i, line in enumerate(lines):
        h = re.match(r"^##\s+(.*)$", line.strip())
        if h and MD.plain(h.group(1)).lower() == (name or "").strip().lower():
            start = i
            break
    if start is None:
        raise ValueError(f"no workstream called {name!r}")
    end = len(lines)
    for j in range(start + 1, len(lines)):
        if re.match(r"^##\s+", lines[j].strip()):
            end = j
            break
    # Two checkboxes with identical wording would make ticking ambiguous, and
    # the tick writer refuses rather than guess — so refuse at the door.
    for j in range(start + 1, end):
        m = re.match(r"^\s*[-*]\s+\[[ xX]\]\s*(.*)$", lines[j])
        if m and MD.plain(m.group(1)).lower() == text.lower():
            raise ValueError("that task is already on this one")
    insert = end
    while insert > start + 1 and not lines[insert - 1].strip():
        insert -= 1                       # keep the blank line before the next heading
    new = [f"- [ ] {text}"]
    # A task butted straight against the field block reads as another field.
    if re.match(r"^\s*-\s+\*\*[A-Za-z ]+:\*\*", lines[insert - 1]):
        new.insert(0, "")
    lines[insert:insert] = new
    write(WORKSTREAMS, "\n".join(lines))
    set_field(name, "Touched", date.today().isoformat())


@serialized
def add_workstream(name, area, ball, why, next_action, due):
    """Create a workstream from the page, in the exact field format the
    parser expects — so a thing added here behaves identically to one Claude
    wrote."""
    name = " ".join((name or "").split())
    if not name:
        raise ValueError("it needs a name")
    body = read(WORKSTREAMS)
    for line in body.split("\n"):
        h = re.match(r"^##\s+(.*)$", line.strip())
        if h and MD.plain(h.group(1)).lower() == name.lower():
            raise ValueError(f"you already have one called {name!r}")
    today = date.today().isoformat()
    ball = ball if ball in ("me", "them", "nobody") else "me"
    block = [f"\n## {name}", "",
             "- **Status:** Moving",
             "- **Ball:** " + {"me": "Me", "them": "Them", "nobody": "Nobody"}[ball],
             f"- **Area:** {area.strip() or 'Personal'}",
             f"- **Touched:** {today}"]
    if ball == "them":
        block.append(f"- **Since:** {today}")
    if due:
        d = M.parse_date(due)
        if d:
            block.append(f"- **Due:** {d.isoformat()}")
    if next_action.strip():
        block.append(f"- **Next:** {next_action.strip()}")
    if why.strip():
        block.append(f"- **Why:** {why.strip()}")
    write(WORKSTREAMS, body.rstrip("\n") + "\n" + "\n".join(block) + "\n")
    return name


PEOPLE = os.path.join(BRAIN, "people.md")


def set_person_field(name, field, value):
    """Same shape as set_field, against people.md."""
    lines = read(PEOPLE).split("\n")
    start = None
    for i, line in enumerate(lines):
        h = re.match(r"^##\s+(.*)$", line.strip())
        if h and MD.plain(h.group(1)).lower() == (name or "").strip().lower():
            start = i
            break
    if start is None:
        raise ValueError(f"nobody called {name!r}")
    end = len(lines)
    for j in range(start + 1, len(lines)):
        if re.match(r"^##\s+", lines[j].strip()):
            end = j
            break
    pat = re.compile(r"^\s*-\s+\*\*" + re.escape(field) + r":\*\*", re.I)
    for j in range(start + 1, end):
        if pat.match(lines[j]):
            lines[j] = f"- **{field}:** {value}"
            write(PEOPLE, "\n".join(lines))
            return
    insert = start + 1
    for j in range(start + 1, end):
        if re.match(r"^\s*-\s+\*\*[A-Za-z ]+:\*\*", lines[j]):
            insert = j + 1
    lines.insert(insert, f"- **{field}:** {value}")
    write(PEOPLE, "\n".join(lines))


def person_spoke(name):
    """One tap after a call or a message. Sets the date and clears the debt —
    if you just spoke, nobody owes anybody a reply."""
    today = date.today().isoformat()
    set_person_field(name, "Last", today)
    set_person_field(name, "Ball", "Nobody")
    return today


def _person_block(lines, name):
    """(start, end) of a person's section in people.md, or raises."""
    start = None
    for i, line in enumerate(lines):
        h = re.match(r"^##\s+(.*)$", line.strip())
        if h and MD.plain(h.group(1)).lower() == (name or "").strip().lower():
            start = i
            break
    if start is None:
        raise ValueError(f"nobody called {name!r}")
    end = len(lines)
    for j in range(start + 1, len(lines)):
        if re.match(r"^##\s+", lines[j].strip()):
            end = j
            break
    return start, end


def _append_alias(lines, start, end, alias):
    """Add a name to the section's Also: line (create it if missing)."""
    alias = (alias or "").strip()
    if not alias:
        return
    for j in range(start + 1, end):
        m = re.match(r"^(\s*-\s+\*\*Also:\*\*\s*)(.*)$", lines[j])
        if m:
            have = [a.strip().lower() for a in m.group(2).split(",")]
            if alias.lower() not in have:
                lines[j] = m.group(1) + m.group(2).rstrip() + ", " + alias
            return
    lines.insert(start + 1, f"- **Also:** {alias}")


def person_rename(name, new):
    """New name on the same person. The old name becomes an Also: alias so
    chat-sync and old task wording keep matching them."""
    new = " ".join((new or "").split())
    if not new:
        raise ValueError("give the new name")
    lines = read(PEOPLE).split("\n")
    try:
        _person_block(lines, new)
        raise ValueError(f"{new} already exists — use merge instead")
    except ValueError as exc:
        if "already exists" in str(exc):
            raise
    start, end = _person_block(lines, name)
    lines[start] = f"## {new}"
    _append_alias(lines, start, end, name)
    write(PEOPLE, "\n".join(lines))
    return new


def person_merge(name, into):
    """Fold one entry into another: promises, notes and any fields the target
    lacks move over; the source name becomes an alias; the source entry goes."""
    if (name or "").strip().lower() == (into or "").strip().lower():
        raise ValueError("that's the same person")
    lines = read(PEOPLE).split("\n")
    s0, s1 = _person_block(lines, name)
    src = lines[s0 + 1:s1]
    src_fields, src_rest = {}, []
    for ln in src:
        m = re.match(r"^\s*-\s+\*\*([A-Za-z ]+):\*\*\s*(.*)$", ln)
        if m:
            src_fields[m.group(1).strip().lower()] = m.group(2).strip()
        elif ln.strip():
            src_rest.append(ln)
    del lines[s0:s1]
    t0, t1 = _person_block(lines, into)
    tgt_fields = set()
    for j in range(t0 + 1, t1):
        m = re.match(r"^\s*-\s+\*\*([A-Za-z ]+):\*\*", lines[j])
        if m:
            tgt_fields.add(m.group(1).strip().lower())
    _append_alias(lines, t0, t1, name)
    t0, t1 = _person_block(lines, into)          # alias insert moved the end
    for al in (src_fields.get("also") or "").split(","):
        if al.strip():
            _append_alias(lines, t0, t1, al)
            t0, t1 = _person_block(lines, into)
    add = []
    for k, v in src_fields.items():
        # Last: keep the more recent date; others: only fill gaps.
        if k == "also":
            continue
        if k == "last" and "last" in tgt_fields:
            continue
        if k not in tgt_fields and v:
            add.append(f"- **{k.title()}:** {v}")
    if src_rest:
        add.extend([""] + src_rest)
    if add:
        lines[t1:t1] = add
    write(PEOPLE, "\n".join(lines))


def person_delete(name, archive=False):
    """Archive parks them in One-off (kept, no rhythm); delete removes the
    entry outright — the page confirms before calling this."""
    if archive:
        set_person_field(name, "Circle", "One-off")
        return
    lines = read(PEOPLE).split("\n")
    s0, s1 = _person_block(lines, name)
    del lines[s0:s1]
    while s0 < len(lines) and not lines[s0].strip():
        del lines[s0]
    write(PEOPLE, "\n".join(lines))


def add_person(name, every, circle, ball, why, focus, how="", where="", birthday=""):
    name = " ".join((name or "").split())
    if not name:
        raise ValueError("they need a name")
    body = read(PEOPLE)
    for line in body.split("\n"):
        h = re.match(r"^##\s+(.*)$", line.strip())
        if h and MD.plain(h.group(1)).lower() == name.lower():
            raise ValueError(f"{name} is already on the list")
    ball = ball if ball in ("me", "them", "nobody") else "nobody"
    circle = (circle or "Friends").strip()
    # The rhythm follows from the circle unless she typed her own — so
    # triaging a person is one choice (the circle), not two.
    if not (every or "").strip():
        every = M.circle_cadence(circle) or "monthly"
    block = [f"\n## {name}", "",
             "- **Ball:** " + {"me": "Me", "them": "Them", "nobody": "Nobody"}[ball],
             f"- **Circle:** {circle}"]
    if (every or "").strip():
        block.append(f"- **Every:** {every.strip()}")
    if how.strip():
        block.append(f"- **How:** {how.strip()}")
    if (where or "").strip():
        block.append(f"- **Where:** {where.strip()}")
    if (birthday or "").strip():
        block.append(f"- **Birthday:** {birthday.strip()}")
    if focus:
        block.append("- **Focus:** yes")
    if why.strip():
        block.append(f"- **Why:** {why.strip()}")
    write(PEOPLE, body.rstrip("\n") + "\n" + "\n".join(block) + "\n")
    return name


@serialized
def add_promise(name, text):
    """A `- [ ]` under a person: something said in a chat that must not
    evaporate with the chat. Same anatomy as every other task, so ticking,
    parking and dropping all just work."""
    text = " ".join((text or "").split())
    if not text:
        raise ValueError("say what was promised")
    lines = read(PEOPLE).split("\n")
    start = None
    for i, line in enumerate(lines):
        h = re.match(r"^##\s+(.*)$", line.strip())
        if h and MD.plain(h.group(1)).lower() == (name or "").strip().lower():
            start = i
            break
    if start is None:
        raise ValueError(f"nobody called {name!r}")
    end = len(lines)
    for j in range(start + 1, len(lines)):
        if re.match(r"^##\s+", lines[j].strip()):
            end = j
            break
    for j in range(start + 1, end):
        m = re.match(r"^\s*[-*]\s+\[[ xX]\]\s*(.*)$", lines[j])
        if m and MD.plain(m.group(1)).lower() == text.lower():
            raise ValueError("that promise is already on them")
    insert = end
    while insert > start + 1 and not lines[insert - 1].strip():
        insert -= 1
    new_lines = [f"- [ ] {text}"]
    if re.match(r"^\s*-\s+\*\*[A-Za-z ]+:\*\*", lines[insert - 1]):
        new_lines.insert(0, "")
    lines[insert:insert] = new_lines
    write(PEOPLE, "\n".join(lines))


@serialized
def add_waiting(what, who, chase_when):
    """A row in the waiting table — the small stuff that does not deserve a
    whole workstream (a parcel, an RSVP, a plumber who said Tuesday)."""
    what = " ".join((what or "").split())
    if not what:
        raise ValueError("say what you are waiting for")
    path = os.path.join(BRAIN, "waiting.md")
    lines = read(path).split("\n")
    row = (f"| {what} | {who.strip() or '—'} | {date.today().isoformat()} "
           f"| {chase_when.strip() or '—'} |")
    for i, line in enumerate(lines):
        # Insert directly under the table header separator, so the newest
        # thing you are waiting on is the first one you read.
        if re.match(r"^\s*\|[\s:|-]+\|\s*$", line):
            lines.insert(i + 1, row)
            write(path, "\n".join(lines))
            return
    raise ValueError("the waiting table is missing its header")


FILES = os.path.join(BRAIN, "files")
# Aligned to what Claude actually accepts, so a too-big upload fails HERE with
# a clear message rather than mid-run with a cryptic API error. Images: the
# model reads ~5 MB max per image; PDFs up to ~32 MB / 100 pages; up to 20
# images per request. These are the guard rails, not a preference.
MAX_IMAGE_BYTES = 5 * 1024 * 1024
MAX_DOC_BYTES = 32 * 1024 * 1024
MAX_ATTACHMENTS = 20
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
SAFE_EXT = IMAGE_EXT | {".pdf", ".txt", ".md", ".csv", ".docx", ".xlsx", ".ics", ".json"}


def save_files(files):
    """Store uploads under brain/files/YYYY-MM-DD/ and return their paths.

    This is how a document gets into the brain — drop a syllabus in, then ask
    Claude to pull the dates out of it. Kept as ordinary files on disk so they
    are readable by anything, including her.
    """
    if len(files) > MAX_ATTACHMENTS:
        raise ValueError(f"Too many at once — {MAX_ATTACHMENTS} files max per ask. "
                         "Send the rest as a second one.")
    saved = []
    day = date.today().isoformat()
    folder = os.path.join(FILES, day)
    os.makedirs(folder, exist_ok=True)
    for f in files[:MAX_ATTACHMENTS]:
        name = os.path.basename(f.get("name") or "file")
        name = re.sub(r"[^A-Za-z0-9._-]+", "-", name).strip("-.") or "file"
        ext = os.path.splitext(name)[1].lower()
        if ext not in SAFE_EXT:
            raise ValueError(f"{name}: only documents and images, not {ext or 'that'}")
        raw = f.get("data") or ""
        if "," in raw:
            raw = raw.split(",", 1)[1]           # strip the data: URL prefix
        try:
            blob = base64.b64decode(raw, validate=True)
        except Exception:
            raise ValueError(f"{name}: could not be read")
        is_image = ext in IMAGE_EXT
        cap = MAX_IMAGE_BYTES if is_image else MAX_DOC_BYTES
        if len(blob) > cap:
            mb = cap // (1024 * 1024)
            hint = " — a screenshot works better than a photo" if is_image else ""
            raise ValueError(f"{name} is {len(blob)//(1024*1024)} MB; Claude reads "
                             f"images up to {mb} MB{hint}." if is_image
                             else f"{name} is too big ({len(blob)//(1024*1024)} MB); "
                                  f"the limit is {mb} MB.")
        target = os.path.join(folder, name)
        n = 1
        while os.path.exists(target):
            stem, e = os.path.splitext(name)
            target = os.path.join(folder, f"{stem}-{n}{e}")
            n += 1
        with open(target, "wb") as fh:
            fh.write(blob)
        saved.append(os.path.relpath(target, BRAIN))
    return saved


MAX_ASK_CHARS = 200_000     # ~50k tokens of text — a wall past this errors the run


@serialized
def queue_request(text, mode, model="", files=None):
    if mode not in MODES:
        mode = "just-do-it"
    model = model if model in MODELS else ""
    if len(text or "") > MAX_ASK_CHARS:
        raise ValueError("That's a very long ask — split it into a couple, or "
                         "attach the long part as a file, so Claude doesn't choke on it.")
    os.makedirs(QUEUE, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d-%H%M%S")
    title = " ".join(text.strip().split())[:70]
    path = os.path.join(QUEUE, f"{stamp}-{slug(title)}.md")
    body = [text.strip()]
    if files:
        body.append("\n## Attached files\n")
        body += [f"- `{p}`" for p in files]
        body.append("\nRead these with the Read tool before acting on the request.")
    write(path, "---\n"
                f"title: {title}\n"
                f"mode: {mode}\n"
                + (f"model: {model}\n" if model else "")
                + "status: pending\n"
                f"created: {date.today().isoformat()}\n"
                + (f"files: {len(files)}\n" if files else "")
                + "---\n\n"
                + "\n".join(body) + "\n")
    return os.path.basename(path)


@serialized
def journal_keep(text, via):
    """Keep a journal entry mechanically — her words straight to disk, no
    Claude run and no queue item. Farming (Last dates, tasks, ticks) waits
    for the next attended session: the journal is private to unattended runs
    (private_gate.py), so a queued run could never touch it anyway, and
    capture should cost nothing. An entry landing before 04:00 is about the
    evening before, so it files under yesterday's date."""
    text = (text or "").strip()
    if not text:
        raise ValueError("nothing to keep")
    now = datetime.now()
    day = (now - timedelta(hours=4)).date().isoformat()
    folder = os.path.join(BRAIN, "journal")
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, day + ".md")
    block = (f"---\nwritten: {now.date().isoformat()}\nvia: {via}\n---\n\n"
             + text + "\n")
    exists = os.path.exists(path) and os.path.getsize(path) > 0
    with open(path, "a", encoding="utf-8") as f:
        f.write(("\n" if exists else "") + block)
    return day


# --------------------------------------------------------------------------
# auto-sync: the "keep itself up to date" half.
#
# Two loops, both cheap and both local:
#   * every `auto_sync_minutes` (default 20) the server re-reads the project
#     folders and rebuilds the page — the live feed with no button pressed;
#   * /api/version answers with a fingerprint of every brain markdown file,
#     so the page can notice ANY change (a tick, an edit in a text editor, a
#     Claude session finishing) and reload itself.
# No AI runs in either loop. Cost: a directory walk.

@serialized
def plan_set(remove_key="", add_text=""):
    """Rewrite today's 'Do these three': drop a line (unplanned, not done)
    and/or add one. Re-prioritising is always the owner's call — Claude
    proposes a plan, she disposes."""
    path = os.path.join(BRAIN, "today.md")
    text = read(path)
    if not text.strip():
        raise ValueError("no plan today yet — ask for one first")
    lines = text.split("\n")
    try:
        start = next(i for i, ln in enumerate(lines)
                     if ln.strip().lower().startswith("## do these three"))
    except StopIteration:
        raise ValueError("today's plan has no 'Do these three' section")
    end = next((i for i in range(start + 1, len(lines))
                if lines[i].startswith("## ")), len(lines))
    if remove_key:
        hit = None
        for i in range(start + 1, end):
            m = re.match(r"^- \[[ xX]\]\s+(.*)$", lines[i])
            if m and MD.taskkey(_bare(m.group(1))) == remove_key:
                hit = i
                break
        if hit is None:
            raise ValueError("that plan item has changed — reload the page")
        j = hit + 1                     # swallow wrapped continuation lines
        while j < end and lines[j].strip() \
                and not lines[j].startswith(("- ", "#")):
            j += 1
        del lines[hit:j]
        end -= (j - hit)
    if add_text:
        add_text = " ".join(add_text.split())
        line = f"- [ ] {add_text}"
        if any(ln.strip() == line for ln in lines):
            raise ValueError("that exact wording is already planned — "
                             "twins break the tickboxes")
        k = end
        while k > start + 1 and not lines[k - 1].strip():
            k -= 1
        lines.insert(k, line)
    write(path, "\n".join(lines))


GOALS_HEADER = """---
maintained-by: you and claude, together
---

# Goals — the finish lines you set for yourself

One `## <room name>` per project (the names on the rooms page), milestones as
checkboxes. `(due ...)` takes a date, a range, or words — "mid-September",
"end of October". Add them from a room's Goals box or by hand here.
A goal past its date makes its whole room shout, on purpose.
"""


@serialized
def add_goal(room, text, due=""):
    """Append a milestone under the room's heading in brain/goals.md,
    creating the file or the heading if needed. The owner's own date words
    are kept verbatim — the parser reads them again on every load."""
    room = (room or "").strip()
    text = (text or "").strip()
    if not room or not text:
        raise ValueError("say the room and the goal")
    if due:
        if not M.parse_due(due):
            raise ValueError("I can't read that date — try 2026-09-15, "
                             "'mid-September', 'within 3 weeks'")
        text += f" (due {due.strip()})"
    fp = os.path.join(BRAIN, "goals.md")
    try:
        with open(fp, encoding="utf-8") as f:
            cur = f.read()
    except FileNotFoundError:
        cur = GOALS_HEADER
    line = f"- [ ] {text}"
    lines = cur.rstrip("\n").split("\n")
    if any(ln.strip() == line for ln in lines):
        raise ValueError("a goal with that exact wording already exists — "
                         "twins break the tickboxes")
    idx = next((i for i, ln in enumerate(lines)
                if ln.strip().lower() == ("## " + room).lower()), None)
    if idx is None:
        if lines and lines[-1].strip():
            lines.append("")
        lines += ["## " + room, "", line]
    else:
        j = idx + 1
        while j < len(lines) and not lines[j].startswith("## "):
            j += 1
        while j > idx + 1 and not lines[j - 1].strip():
            j -= 1
        lines.insert(j, line)
    write(fp, "\n".join(lines) + "\n")


SEASON_HEADER = """---
maintained-by: you and claude, together
---

# Season — the things you want this stretch of life to hold

One `## <season name>` heading with **From:**/**Until:** dates and a one-line
**Why:**, then the bucket: plain checkboxes that may carry `(with: names)`,
`(when: October)` and the `(planned: 2026-10-17)` the page writes when you
drag one onto a day.
"""


@serialized
def season_slot(key, day):
    """Move a bucket item onto a day (or a range), or clear it back to the
    idea tray. The page's drag writes this. (planned: …) is state, stripped
    from the hash input, so the item's tick key never moves with it."""
    fp = os.path.join(BRAIN, "season.md")
    day = (day or "").strip()
    val = ""
    if day:
        pd = M.parse_due(day, date.today())
        if not pd:
            raise ValueError("give a date like 2026-10-17, or a range "
                             "2026-10-17..2026-10-18")
        val = (pd["start"].isoformat() if pd["start"] == pd["end"]
               else pd["start"].isoformat() + ".." + pd["end"].isoformat())
    lines = read(fp).split("\n")
    hits = []
    for i, line in enumerate(lines):
        m = re.match(r"^(\s*[-*]\s+)\[([ xX])\]\s+(.*)$", line)
        if m and MD.taskkey(_bare(m.group(3))) == key:
            hits.append((i, m))
    if not hits:
        raise ValueError("that item has changed — reload the page")
    if len(hits) > 1:
        raise ValueError("two items have identical wording; make one of them "
                         "different so the move knows where to land")
    i, m = hits[0]
    txt = re.sub(r"\s*\(planned: [^)]+\)", "", m.group(3)).rstrip()
    if val:
        txt += f" (planned: {val})"
    lines[i] = f"{m.group(1)}[{m.group(2)}] {txt}"
    write(fp, "\n".join(lines))


@serialized
def season_add(text):
    """A new idea for the season's bucket, from the page's little input.
    Appends at the end of the file — the active season is the only block, so
    the end of the file is the end of its bucket."""
    text = (text or "").strip()
    if not text:
        raise ValueError("say the thing you want to do")
    if "\n" in text or len(text) > 300:
        raise ValueError("one line, under 300 characters")
    fp = os.path.join(BRAIN, "season.md")
    try:
        cur = read(fp)
    except FileNotFoundError:
        cur = SEASON_HEADER + "\n## This season\n"
    key = MD.taskkey(_bare(text))
    for ln in cur.split("\n"):
        mm = re.match(r"^\s*[-*]\s+\[[ xX]\]\s+(.*)$", ln)
        if mm and MD.taskkey(_bare(mm.group(1))) == key:
            raise ValueError("that's already on the list — reword it if it's "
                             "a different thing")
    lines = cur.rstrip("\n").split("\n")
    lines.append(f"- [ ] {text}")
    write(fp, "\n".join(lines) + "\n")


def room_notes_path(room_slug):
    """brain/rooms/<slug>.md — the room's memory, editable on the rooms page.
    The slug is validated hard because it becomes a filename."""
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,59}", room_slug or ""):
        raise ValueError("not a room I know")
    return os.path.join(BRAIN, "rooms", room_slug + ".md")


def room_notes_for_path(src_path):
    """The room-notes body for a configured source path, or "". This is how
    context typed once in a room travels into every project session there."""
    cfg = load_json(os.path.join(BRAIN, "config.json"), {})
    by_name = {s.get("name"): s.get("path") for s in (cfg.get("sources") or [])}
    for wing in ((cfg.get("rooms") or {}).get("wings") or []):
        for room in (wing.get("rooms") or []):
            if by_name.get(room.get("source") or "") != src_path:
                continue
            sl = room.get("slug") or M.room_slug(room.get("name", ""))
            try:
                with open(os.path.join(BRAIN, "rooms", sl + ".md"),
                          encoding="utf-8") as f:
                    return f.read().strip()
            except OSError:
                return ""
    return ""


def connections_status():
    """What is actually plugged in right now, as facts rather than setup prose.

    The Connections popover was five blocks of instructions with one live
    line in it, and that line said "could not check". You could read the
    whole thing and still not know whether your calendar was feeding the
    morning plan. Every row below is evidence already on disk — a token, a
    cache stamp, a log's mtime — so this stays a fast local read with no
    network in it: a popover must never hang because a mail server is slow.
    """
    def ago(ts):
        if not ts:
            return ""
        try:
            d = datetime.fromtimestamp(ts) if isinstance(ts, (int, float)) \
                else datetime.fromisoformat(str(ts)[:19])
        except (ValueError, OSError, OverflowError):
            return ""
        secs = (datetime.now() - d).total_seconds()
        if secs < 90:
            return "just now"
        if secs < 5400:
            return f"{int(secs // 60)} min ago"
        if secs < 172800:
            return "today" if d.date() == date.today() else "yesterday"
        return f"{int(secs // 86400)} days ago"

    def mtime(name):
        try:
            return os.path.getmtime(os.path.join(BRAIN, name))
        except OSError:
            return 0

    cfg = load_json(os.path.join(BRAIN, "config.json"), {})
    out = []

    # Chats — the token is the setup, the review file's stamp is the proof.
    try:
        import beeper
        tok = bool(beeper.keychain_get())
    except Exception:
        tok = False
    rev = load_json(os.path.join(BRAIN, ".beeper-review.json"), {})
    unmatched = len(rev.get("unmatched") or [])
    out.append({
        "id": "chats", "name": "Chats",
        "on": tok,
        "line": (("last read " + (ago(rev.get("when")) or "not yet"))
                 + (f" \u00b7 {unmatched} chats not yet sorted" if unmatched else ""))
        if tok else "Not connected \u2014 “last spoke” dates stay manual",
        "act": ("Sync now", "/api/beeper/sync") if tok else ("", ""),
    })

    # Telegram — a token alone is half a setup; the chat id is the pairing.
    tg = load_json(os.path.join(BRAIN, ".telegram.json"), {})
    paired = bool(tg.get("token") and tg.get("chat_id"))
    out.append({
        "id": "telegram", "name": "Telegram",
        "on": paired,
        "line": ("paired \u00b7 morning plan sent "
                 + (ago(tg.get("plan_sent")) or "not yet")) if paired
        else ("token set, not paired yet \u2014 message the bot to finish"
              if tg.get("token") else "Not set up"),
        "act": ("", ""),
    })

    # Calendar — on/off, and what the last read actually found.
    try:
        import calendar_read as CAL
        cal_on = CAL.enabled()
        nfeeds = len(CAL.feeds())
    except Exception:
        cal_on, nfeeds = False, 0
    cache = load_json(os.path.join(BRAIN, ".calendar-cache.json"), {})
    nev = len(cache.get("events") or [])
    out.append({
        "id": "calendar", "name": "Calendar",
        "on": bool(cal_on or nfeeds),
        "line": (f"{nev} event" + ("" if nev == 1 else "s") + " today \u00b7 read "
                 + (ago(cache.get("at")) or "not yet")
                 + (f" \u00b7 {nfeeds} feed" + ("" if nfeeds == 1 else "s")
                    if nfeeds else ""))
        if (cal_on or nfeeds) else "Off \u2014 the morning plan cannot see your day",
        "act": ("", ""),
    })

    # Email — two switches, not one: sending and reading are separate powers.
    try:
        import email_send, email_read
        addrs = [a["address"] for a in email_send.accounts()]
        reading = email_read.reading_on()
        last = email_read.last_check()
    except Exception:
        addrs, reading, last = [], False, None
    out.append({
        "id": "mailsend", "name": "Email sending",
        "on": bool(addrs),
        "line": (", ".join(addrs) + " \u00b7 every send stays a button you press")
        if addrs else "Not set up",
        "act": ("", ""),
    })
    out.append({
        "id": "mailread", "name": "Email reading",
        "on": bool(reading),
        "line": ("headers only \u00b7 checked " + (ago(last) or "not yet"))
        if reading else "Off \u2014 nothing reads your mail",
        "act": ("Check now", "/api/email/check") if reading else ("", ""),
    })

    # Night shift — the switch, what it is allowed to do, and whether it ran.
    try:
        import night_config
        night = night_config.load()
    except Exception:
        night = {}
    ran = mtime(".night.log")
    out.append({
        "id": "night", "name": "Night shift",
        "on": bool(night.get("enabled")),
        "line": (f"{night.get('at', '01:00')} \u00b7 "
                 + ", ".join(night.get("jobs") or []) + " \u00b7 "
                 + str(night.get("model") or "")
                 + (" \u00b7 last ran " + ago(ran) if ran else " \u00b7 not run yet"))
        if night.get("enabled")
        else ("Off" + (" \u00b7 last ran " + ago(ran) if ran else "")),
        "act": ("", ""),
    })
    return out


def recent_source_files(days=4, cap=40):
    """Markdown that appeared or changed in her project folders in the last
    few days. Sync mirrors checkboxes; these files often have none (a task
    menu of 75 numbered items, a walkthrough log), so nothing about them
    reaches the brain until someone reads them. This is that list."""
    cfg = load_json(os.path.join(BRAIN, "config.json"), {})
    cutoff = datetime.now().timestamp() - days * 86400
    out = []
    for src in (cfg.get("sources") or []):
        root = os.path.expanduser(src.get("path") or "")
        if not os.path.isdir(root):
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            if dirpath.count(os.sep) - root.count(os.sep) > 3:
                dirnames[:] = []
                continue
            dirnames[:] = [d for d in dirnames
                           if not d.startswith(".") and d not in
                           ("node_modules", "build", "dist", "venv", "__pycache__")]
            for fn in filenames:
                if not fn.lower().endswith(".md"):
                    continue
                p = os.path.join(dirpath, fn)
                try:
                    st = os.stat(p)
                except OSError:
                    continue
                if st.st_mtime < cutoff:
                    continue
                out.append({"path": p, "name": fn, "source": src.get("name", ""),
                            "kb": max(1, round(st.st_size / 1000)),
                            "when": datetime.fromtimestamp(st.st_mtime)
                                            .strftime("%d %b %H:%M"),
                            "mtime": st.st_mtime})
    out.sort(key=lambda x: x["mtime"], reverse=True)
    return out[:cap]


_sync = {"last": None}
# The live state of a transcription run, watched by the page.
_tr = {"running": False, "name": "", "note": "", "done": "", "error": ""}


def room_from_words(text):
    """The room a caption names, or "". Exact-ish: a room only wins if its
    name (or slug) appears whole, so "the kitchen" doesn't become a room and
    a wrong guess doesn't file a conversation under the wrong project."""
    words = re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()
    if not words:
        return ""
    cfg = load_json(os.path.join(BRAIN, "config.json"), {})
    for wing in (cfg.get("rooms") or {}).get("wings", []):
        for room in wing.get("rooms", []):
            name = room.get("name", "")
            sl = room.get("slug") or M.room_slug(name)
            flat = re.sub(r"[^a-z0-9]+", " ", name.lower()).strip()
            if flat and re.search(rf"\b{re.escape(flat)}\b", words):
                return sl
            if sl and re.search(rf"\b{re.escape(sl.replace('-', ' '))}\b", words):
                return sl
    return ""


def telegram_voice(path, meta, reply):
    """A voice note from the phone, taken the rest of the way.

    Download, transcribe on this Mac's own GPU, file the transcript, queue the
    ask that turns it into tasks, delete the audio. It runs on its own thread
    because whisper takes minutes and the bridge has a chat to keep answering;
    it shares `_tr` with the page's transcribe button, because two whisper runs
    on one GPU are slower than either alone.

    The audio is deleted once the transcript is written — her instruction, and
    a voice note is worth keeping as words, not megabytes. The transcript is
    the record, so nothing said is lost."""
    import transcribe as TR

    if _tr["running"]:
        reply("Already transcribing " + (_tr["name"] or "something") +
              " — send it again when that's through.")
        try:
            os.remove(path)
        except OSError:
            pass
        return

    _tr.update({"running": True, "name": os.path.basename(path),
                "note": "from Telegram", "done": "", "error": ""})

    # What the caption says decides what happens to the words:
    #   a room name  -> the tasks the conversation created, in that project
    #   "journal"    -> tonight's journal entry, kept in her words
    #   "dump"       -> sorted into the brain like a /dump, nothing forced
    #   nothing      -> a dump, because a voice note with no context is her
    #                   emptying her head, not minuting a meeting
    # Any other caption is passed to whisper as a hint, which is what makes it
    # spell Riocour and Faverolles right.
    caption = (meta.get("caption") or "").strip()
    # "met" first, before the room check: a caption like "met Thiago at HEC"
    # names a person, not a project, and the person is the whole point.
    as_met = bool(re.match(r"(?i)^met\b[:,\-—]?\s*", caption))
    as_journal = (not as_met) and bool(re.match(r"(?i)^journal\b", caption))
    room = "" if (as_met or as_journal) else room_from_words(caption)
    as_dump = (not room and not as_met and not as_journal) and (
        not caption or re.match(r"(?i)^dump\b", caption.strip()))
    # The rest of a "met" caption is still worth handing whisper — it is
    # usually the name it would otherwise spell four different ways.
    prompt = "" if (room or as_journal or as_dump and not caption) else caption[:400]

    def go():
        try:
            dest = TR.transcribe(path, "fr", prompt, room,
                                 progress=lambda m: _tr.__setitem__("note", m))
            name = os.path.basename(dest)
            if as_met:
                queue_request(TR.met_ask_text(name), "just-do-it")
            elif as_journal:
                # The transcript text IS the entry — keep it now, mechanically,
                # minus the transcript's own frontmatter and title line.
                with open(dest, encoding="utf-8") as tf:
                    words = tf.read()
                words = re.sub(r"^---\n.*?\n---\n+", "", words, flags=re.S)
                words = re.sub(r"^#\s+.*\n+", "", words)
                journal_keep(words, "telegram")
            elif as_dump:
                queue_request(TR.dump_ask_text(name), "dump")
            else:
                queue_request(TR.ask_text(name, room), "just-do-it")
            _tr.update({"done": name, "note": "queued the update"})
            mins = round((meta.get("seconds") or 0) / 60, 1)
            what = ("queued to become people, with follow-ups at 3 days, "
                    "3 weeks and 3 months" if as_met
                    else "kept as the day's journal entry, in your words — "
                    "the next session folds it into the brain"
                    if as_journal
                    else "queued to be sorted into the brain" if as_dump
                    else f"queued to become tasks in {room or 'the right project'}")
            reply(f"Transcribed{f' ({mins} min)' if mins else ''} ✓ — filed as "
                  f"{name} and {what}. The recording is deleted; the words "
                  "are kept.")
        except Exception as exc:
            _tr["error"] = str(exc)[:300]
            reply("The transcription failed: " + str(exc)[:200] +
                  "\n\nThe recording is still on the Mac — nothing lost.")
            return                       # keep the audio when there's no text
        finally:
            _tr["running"] = False
            _rebuild_soon()
        try:
            os.remove(path)
        except OSError:
            pass

    threading.Thread(target=go, daemon=True).start()


_ask = {"running": False}


def _ask_roots():
    """Where a file may be read from and sent back: the brain, plus the
    project folders config already points at. Her documents live in those
    folders — a renovation plan, a school folder — and a guard that
    only allowed the brain silently dropped every file Claude offered."""
    roots = [os.path.realpath(ROOT)]
    try:
        cfg = load_json(os.path.join(BRAIN, "config.json"), {})
        for s in cfg.get("sources") or []:
            p = os.path.realpath(os.path.expanduser((s or {}).get("path") or ""))
            if p and os.path.isdir(p):
                roots.append(p)
    except Exception:                                    # noqa: BLE001
        pass
    return roots


def telegram_ask(question, reply, history=""):
    """A question from the phone, answered by Claude, in the brain's folder.

    Deliberately NOT `start_agent`: that one is the page's streaming queue
    runner and only one may exist, so a phone question would either be
    refused mid-queue or steal the feed. This is a short read-and-answer run
    with its own lock and a hard timeout, because a question typed on a bus
    should never turn into a twenty-minute spend.

    It can name one file to send back. The path is resolved inside the brain
    folder and nowhere else — the journal included, since a phone chat is not
    where her own words belong."""
    if _ask["running"]:
        reply("Still working on the last question — one at a time.")
        return
    claude = shutil_which("claude")
    if not claude:
        reply("Claude Code isn't on this machine's PATH, so I can only file "
              "and fetch, not think.")
        return

    prompt = (
        "Answer this question from the owner, who is on her phone. She is "
        "reading the reply in Telegram, so: plain text, no markdown "
        "headings, no tables, under 1500 characters unless she asked for "
        "something long.\n\n"
        "You may read anything in this brain AND in the project folders "
        "listed under `sources` in brain/config.json — her documents "
        "usually live in those folders, not in the brain itself.\n\n"
        "IF SHE IS ASKING FOR A FILE, A DOCUMENT, A LIST OR A PLAN, sending "
        "it is the answer. Do not describe it and stop — that is the single "
        "most annoying thing you can do here. Find it, then end your reply "
        "with a line of exactly this form:\n"
        "FILE: /absolute/path/to/the/file\n"
        "One short sentence of context above it is plenty. An absolute path "
        "is safest; a path relative to the brain also works.\n\n"
        "Never modify or delete an existing file, and never send anything to "
        "anyone. If she asks for a document that does not exist yet, write "
        "ONE new file under brain/drafts/ and return it the same way.\n\n"
        + (f"The last few messages in the chat, for context — 'it' and "
           f"'that' probably refer to something here:\n{history}\n\n"
           if history else "")
        + f"Her message now:\n{question}")

    def go():
        _ask["running"] = True
        try:
            proc = subprocess.run(
                [claude, "-p", prompt, "--permission-mode", "bypassPermissions",
                 "--output-format", "text"],
                cwd=ROOT, stdin=subprocess.DEVNULL, capture_output=True,
                text=True, timeout=240)
            out = (proc.stdout or "").strip()
            if not out:
                reply("Claude came back with nothing. "
                      + ((proc.stderr or "").strip()[:300] or "No error given."))
                return
            path = None
            m = re.search(r"^FILE:\s*(.+)$", out, re.M)
            if m:
                out = out[:m.start()].rstrip()
                raw = os.path.expanduser(m.group(1).strip().strip("`'\""))
                cand = os.path.realpath(
                    raw if os.path.isabs(raw) else os.path.join(ROOT, raw))
                private = os.path.realpath(os.path.join(BRAIN, "journal"))
                inside = any(cand == r or cand.startswith(r + os.sep)
                             for r in _ask_roots())
                if inside and os.path.isfile(cand) \
                        and not cand.startswith(private + os.sep):
                    path = cand
            if path:
                reply(out or os.path.basename(path), path)
            else:
                reply(out)
        except subprocess.TimeoutExpired:
            reply("That took longer than four minutes, so I stopped it. Ask "
                  "something narrower, or work it from the page.")
        except Exception as exc:                        # noqa: BLE001
            reply(f"That run failed: {exc}")
        finally:
            _ask["running"] = False

    threading.Thread(target=go, daemon=True).start()


def _fingerprint():
    """One number that changes when any brain markdown or the config does.
    mtimes, not content hashes — this runs every 20 s and must stay free."""
    stamp = 0
    try:
        for fn in sorted(os.listdir(BRAIN)):
            if fn.endswith((".md", ".json")) and not fn.startswith("."):
                stamp ^= hash((fn, int(os.path.getmtime(os.path.join(BRAIN, fn)))))
        # the generated pages too: with deferred rebuilds, "the brain changed"
        # only matters to a client once the fresh page has actually landed
        for fn in ("index.html", "map.html", "rooms.html", "proto.html"):
            p = os.path.join(BRAIN, fn)
            if os.path.exists(p):
                stamp ^= hash((fn, int(os.path.getmtime(p))))
        rdir = os.path.join(BRAIN, "rooms")
        if os.path.isdir(rdir):
            for fn in sorted(os.listdir(rdir)):
                if fn.endswith(".md"):
                    stamp ^= hash(("rooms/" + fn,
                                   int(os.path.getmtime(os.path.join(rdir, fn)))))
        qdir = os.path.join(BRAIN, "queue")
        if os.path.isdir(qdir):
            for fn in sorted(os.listdir(qdir)):
                if fn.endswith(".md"):
                    stamp ^= hash((fn, int(os.path.getmtime(os.path.join(qdir, fn)))))
    except OSError:
        pass
    return stamp & 0xFFFFFFFF


def _autosync_loop():
    import sync
    cfg = M.load_config()
    minutes = float(cfg.get("auto_sync_minutes", 20) or 0)
    if minutes <= 0:
        return                                  # switched off in config.json
    interval = max(minutes, 1) * 60
    while True:
        try:
            before = _fingerprint()
            sync.sync()
            _sync["last"] = datetime.now()
            # Refresh contact dates + the triage cache too. Beeper closed or
            # not connected is normal — never let it break the folder sync.
            try:
                import beeper
                beeper.collect(write=True)
            except Exception:
                pass
            # Two-machine bridge: commit what the page wrote, take what the
            # other machine pushed, hand ours back. Never fatal — gitsync
            # aborts a conflicted rebase and leaves this machine as it was.
            pulled = False
            try:
                import gitsync
                pulled = gitsync.cycle()
            except Exception:
                pass
            # Only rebuild when the sync actually changed something — an idle
            # rebuild every 20 minutes would churn mtimes and force the page
            # to reload under the reader for no reason.
            if pulled or _fingerprint() != before:
                rebuild()
        except Exception:
            pass                                # a failed sync waits for the next tick
        threading.Event().wait(interval)


# --------------------------------------------------------------------------
# running Claude Code from the page

AUDIT_PROMPT = """Audit the brain for load-bearing gaps — the missing facts that
make prioritisation wrong — and ASK for them. Look for: tasks whose words imply
a deadline but carry no (due …); things that sound urgent but aren't marked
(urgent); workstreams whose Next is stale or empty; Ball: Them with no Since;
people mentioned in tasks but absent from people.md; anything contradictory;
circles whose size × rhythm implies an unsustainable daily reach-out load
(Dunbar layers: ~5/15/50/150 — suggest loosening, don't lecture).
Write AT MOST 6 questions to brain/questions.md as `- [ ]` lines — each sharp,
self-contained, and answerable in one line (they get inline answer boxes on the
page). Prefer the questions whose answers would most change the ranking.
Change nothing else. Rebuild (python3 brain/tools/build.py) and end with one
line: how many questions you asked and which gap matters most."""

JOBS = {"queue": "/queue", "brief": "/brief", "wrap": "/wrap", "sync": "/sync",
        "discover": "/discover", "today": "/today", "audit": AUDIT_PROMPT,
        "usageaudit": "/usage-audit", "scout": "/scout"}

# Mechanical jobs: reading folders and refreshing synced.md takes no judgment,
# so these default to Haiku even in Full mode. A model picked on the run, or
# an explicit default set on the Usage page, still wins — the light default
# only replaces the PRESET's choice, never hers.
LIGHT_JOBS = {"sync", "discover"}


def ai_mode():
    """'careful' fits a Pro plan (shared 5-hour window: no scheduled runs,
    cheapest model unless asked); 'full' fits Max. Stored in config.json so
    the morning script and the page read the same answer."""
    try:
        with open(os.path.join(BRAIN, "config.json"), encoding="utf-8") as f:
            return "careful" if json.load(f).get("ai") in ("low", "careful", "pro") else "full"
    except Exception:
        return "full"


def set_ai_mode(mode):
    if mode not in ("careful", "full"):
        raise ValueError("mode must be careful or full")
    _config_set("ai", mode)


# What each preset means, in one place. The Usage page's per-feature switches
# override these key by key; a key absent from config's `ai_features` follows
# the preset. serve.py, morning.sh/.ps1 and sessions.py all resolve through
# the same config keys, so the page and the runs cannot disagree.
AI_DEFAULTS = {
    "careful": {"morning": False, "model": "haiku", "openers": False,
                "news": True},
    "full": {"morning": True, "model": "sonnet", "openers": True,
             "news": True},
}

# The two recommended shapes, named after the plan they fit. Applying one
# clears every per-feature override so the preset governs again — the point
# of "recommended" is a known state, not a merge with whatever was there.
# Anything not listed here (the night shift, extra privacy) keeps its own
# switch, because turning those on means a step the page cannot take alone.
AI_PLANS = {
    "pro":  {"ai": "careful", "features": {"daily_cap": 2.0}},
    "max":  {"ai": "full", "features": {}},
}

AI_FEATURE_BOOLS = ("morning", "openers", "news")
AI_FEATURE_KEYS = AI_FEATURE_BOOLS + ("model", "daily_cap")


def ai_features():
    """The effective per-feature settings: preset defaults, then overrides."""
    mode = ai_mode()
    try:
        with open(os.path.join(BRAIN, "config.json"), encoding="utf-8") as f:
            ov = json.load(f).get("ai_features") or {}
    except Exception:
        ov = {}
    eff = dict(AI_DEFAULTS[mode])
    for key in AI_FEATURE_BOOLS:
        if isinstance(ov.get(key), bool):
            eff[key] = ov[key]
    if ov.get("model") in ("haiku", "sonnet", "opus"):
        eff["model"] = ov["model"]
    # The ceiling has no preset default — absent means no ceiling — so it
    # rides in the overrides only, which is also where the page reads it.
    eff["overrides"] = {k: ov[k] for k in AI_FEATURE_KEYS if k in ov}
    eff["plan"] = ai_plan_match(mode, eff["overrides"])
    return eff


def ai_plan_match(mode, overrides):
    """Which recommended shape the settings are currently in, or 'custom'.
    The page uses this to show one of the two as chosen rather than making
    someone read six switches to answer 'am I set up for Pro?'."""
    for name, plan in AI_PLANS.items():
        if plan["ai"] == mode and overrides == plan["features"]:
            return name
    return "custom"


def set_ai_plan(name):
    """Apply a whole recommended shape in one write: the preset, and the
    overrides that shape needs. Everything else goes back to following the
    preset."""
    if name not in AI_PLANS:
        raise ValueError("plan must be pro or max")
    plan = AI_PLANS[name]
    _config_set("ai", plan["ai"])
    _config_set("ai_features", dict(plan["features"]))
    return ai_features()


def set_ai_feature(key, value):
    """One switch from the Usage page. value None clears the override, so the
    feature follows the preset again."""
    if key in AI_FEATURE_BOOLS:
        if value is not None and not isinstance(value, bool):
            raise ValueError(f"{key} must be true, false or null")
    elif key == "model":
        if value is not None and value not in ("haiku", "sonnet", "opus"):
            raise ValueError("model must be haiku, sonnet, opus or null")
    elif key == "daily_cap":
        # A number of dollars, or null for no ceiling. Stored as a float so
        # the comparison never depends on how the page typed it.
        if value is not None:
            try:
                value = round(float(value), 2)
            except (TypeError, ValueError):
                raise ValueError("the ceiling must be a number of dollars")
            if value < 0:
                raise ValueError("the ceiling cannot be negative")
            if value == 0:
                value = None            # zero means no ceiling, not "block all"
    else:
        raise ValueError("unknown switch: " + repr(key))
    try:
        with open(os.path.join(BRAIN, "config.json"), encoding="utf-8") as f:
            ov = json.load(f).get("ai_features") or {}
    except Exception:
        ov = {}
    if value is None:
        ov.pop(key, None)
    else:
        ov[key] = value
    _config_set("ai_features", ov)


def privacy_state():
    """The Extra privacy switch, read from config's `private` list. The key
    absent means the default (the journal is private), so absent counts as
    on — the switch never has a third state the page would have to explain."""
    try:
        with open(os.path.join(BRAIN, "config.json"), encoding="utf-8") as f:
            priv = json.load(f).get("private")
    except Exception:
        priv = None
    return {"on": priv is None or bool(priv)}


def set_privacy(on):
    """Config keeps the honest form — the list of protected paths. The
    switch writes the common case (the journal). A hand-edited longer list
    is replaced by the default if the switch is turned off and on again —
    anyone editing the list by hand can also read this comment."""
    _config_set("private", ["brain/journal/"] if on else [])


def _config_set(key, value):
    path = os.path.join(BRAIN, "config.json")
    try:
        with open(path, encoding="utf-8") as f:
            cfg = json.load(f)
    except Exception:
        cfg = {}
    cfg[key] = value
    write(path, json.dumps(cfg, indent=2) + "\n")


def night_state():
    """What the page shows for the night shift, including whether it is
    actually scheduled — a config flag set to true with no schedule installed
    would sit there claiming to run and never run."""
    import night_config
    n = night_config.load()
    if sys.platform == "darwin":
        plist = os.path.expanduser(
            "~/Library/LaunchAgents/com.lifebrain.night.plist")
        scheduled = os.path.exists(plist)
    else:
        try:
            r = subprocess.run(["schtasks", "/query", "/tn",
                                "LifeBrain Night Shift"],
                               capture_output=True, timeout=10)
            scheduled = r.returncode == 0
        except Exception:
            scheduled = False
    return {"enabled": bool(n.get("enabled")), "at": n.get("at"),
            "jobs": n.get("jobs"), "model": n.get("model"),
            "scheduled": scheduled}


def set_night(enabled):
    """Flip the night shift on or off. Scheduling stays a deliberate one-time
    setup step (setup_night.sh) — installing a launchd agent is not something
    a toggle on a web page should do behind her back."""
    import night_config
    n = night_config.load()
    n["enabled"] = bool(enabled)
    n.pop("_comment", None)
    path = os.path.join(BRAIN, "config.json")
    try:
        with open(path, encoding="utf-8") as f:
            cfg = json.load(f)
    except Exception:
        cfg = {}
    keep = cfg.get("night") or {}
    keep["enabled"] = bool(enabled)
    cfg["night"] = keep
    write(path, json.dumps(cfg, indent=2) + "\n")
    return night_state()


def _split_draft(text):
    m = re.match(r"\A(---\n.*?\n---\n)(.*)\Z", text, re.S)
    if m:
        return m.group(1), m.group(2)
    return "", text


def _draft_meta(front):
    out = {}
    for line in front.split("\n"):
        if ":" in line and not line.startswith("---"):
            k, v = line.split(":", 1)
            out[k.strip().lower()] = v.strip()
    return out


@serialized
def draft_edit(fn, body):
    """Save a hand-edited draft body. Zero tokens — this is the owner typing."""
    dpath = os.path.join(BRAIN, "drafts", os.path.basename(fn))
    if not (fn.endswith(".md") and os.path.isfile(dpath)):
        raise ValueError("no such draft")
    front, _ = _split_draft(read(dpath))
    write(dpath, front + (body or "").strip() + "\n")


REVISE_SYS = ("You revise one short message (an email or a chat message) in the "
              "author's own voice. Output ONLY the revised message text — no "
              "preamble, no sign-off you were not asked for, no explanation, no "
              "surrounding quotes. Keep every real fact, name, and number.")


def draft_revise(fn, instruction):
    """Reword a single draft with a FOCUSED model call.

    The whole point: this loads only the draft, who it's to, the task, and her
    voice rules — a few thousand tokens — not the 150k-token brain a normal
    run pulls in. llm.py decides where it runs: Haiku with tools disabled from
    a temp dir (cents), or a local Ollama model when config routes it (free,
    and the text never leaves the machine).
    """
    instruction = (instruction or "").strip()
    if not instruction:
        raise ValueError("say what to change")
    dpath = os.path.join(BRAIN, "drafts", os.path.basename(fn))
    if not (fn.endswith(".md") and os.path.isfile(dpath)):
        raise ValueError("no such draft")

    front, body = _split_draft(read(dpath))
    meta = _draft_meta(front)
    kind = meta.get("kind", "message")
    who = meta.get("person") or meta.get("to") or "the recipient"
    task = meta.get("task", "")

    # Her voice guide is the one piece of brain context a rewrite genuinely
    # needs. Everything else stays out.
    try:
        voice = read(os.path.join(BRAIN, "writing-rules.md"))
    except OSError:
        voice = ""
    ctx = [f"This is a {kind} to {who}."]
    if task:
        ctx.append(f"It is about: {task}.")
    if voice:
        ctx.append("\nHER VOICE RULES (follow them):\n" + voice)
    prompt = ("\n".join(ctx)
              + "\n\nCURRENT DRAFT:\n" + body.strip()
              + "\n\nCHANGE REQUESTED: " + instruction
              + "\n\nReturn only the revised " + kind + ".")

    started = datetime.now()
    try:
        res = llm.complete("revise", prompt, system=REVISE_SYS, timeout=90,
                           env=SESS.claude_env())
    except ValueError:
        # A failed call still cost something and still gets a line —
        # "too small to bother recording" is how ledgers start lying.
        usage.record("revise", "draft revise", model="haiku",
                     usage={"input_tokens": len(prompt) // 4},
                     secs=(datetime.now() - started).total_seconds(), ok=False)
        raise
    usage.record("revise", "draft revise", model=res["model"],
                 usage=res["usage"],
                 secs=(datetime.now() - started).total_seconds(), ok=True)
    write(dpath, front + res["text"] + "\n")
    return res["text"]


_MODEL_TIER = {"haiku": 0, "sonnet": 1, "opus": 2}


def _queue_model_choice():
    """The strongest `model:` any PENDING queue item carries, or ''."""
    best = ""
    try:
        for fn in os.listdir(QUEUE):
            if not fn.endswith(".md") or fn.startswith("_"):
                continue
            front, _ = _split_draft(read(os.path.join(QUEUE, fn)))
            meta = _draft_meta(front)
            if meta.get("status") != "pending":
                continue
            m = (meta.get("model") or "").strip().lower()
            if m in MODELS and (not best or _MODEL_TIER[m] > _MODEL_TIER[best]):
                best = m
    except Exception:
        return ""
    return best


def _spend_cap_hit():
    """The message to refuse with when today has reached her ceiling, else "".

    A ceiling for people who would rather the brain stopped than surprised
    them — a Pro plan's five-hour window is a real constraint, and "it just
    kept going" is the thing that makes someone turn a tool off entirely.

    Deliberately narrow. It only ever blocks a run STARTED FROM THE PAGE, it
    never blocks the scheduled work (that half is small and predictable, and
    silently skipping the morning plan would look like a bug), and it is one
    click to go ahead anyway. A cap that removes a feature is a worse tool;
    this only asks a second time.
    """
    cfg2 = load_json(os.path.join(BRAIN, "config.json"), {})
    try:
        cap = float(((cfg2.get("ai_features") or {}).get("daily_cap") or 0))
    except (TypeError, ValueError):
        return ""
    if cap <= 0:
        return ""
    today = date.today().isoformat()
    spent = 0.0
    try:
        with open(os.path.join(BRAIN, ".usage.jsonl"), encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    row = json.loads(line)
                except ValueError:
                    continue
                if (row.get("at") or "")[:10] == today:
                    spent += float(row.get("cost") or 0)
    except OSError:
        return ""
    if spent < cap:
        return ""
    return (f"Today has reached your ceiling ({spent:.2f} of {cap:.2f}). "
            "Press again to run anyway — nothing is turned off, this just "
            "asks twice.")


def _queue_pending_count():
    """How many queue items are waiting — counted EXACTLY as the page counts
    them, including the missing-status default.

    If this and the button's "N waiting" ever disagree, the button refuses to
    start work the page says is there, which is worse than the wasted run
    this guard exists to prevent. Same rule, one place to change it.
    """
    n = 0
    try:
        for fn in os.listdir(QUEUE):
            if not fn.endswith(".md") or fn.startswith("_"):
                continue
            front, _ = _split_draft(read(os.path.join(QUEUE, fn)))
            status = (_draft_meta(front).get("status") or "pending").lower()
            if status in ("pending", "working"):
                n += 1
    except Exception:
        return -1               # unknown: never block on a failed count
    return n


def start_agent(job, model=""):
    """Spawn a headless Claude Code run. Three things here were established by
    testing rather than assumed, and all three are load-bearing:

      * stdin MUST be closed. With an open stdin, `claude -p` hangs forever
        producing nothing, which looks exactly like unsupported flags.
      * `acceptEdits` denies Bash, so the run cannot do real work. It needs
        bypassPermissions. That is a deliberate trade — it runs on your own
        machine, in your own folder, and never pushes anywhere.
      * stream-json emits one JSON object per line, which is the only reason
        a live feed on the page is possible at all.
    """
    if _agent["running"]:
        raise ValueError("already running")
    claude = shutil_which("claude")
    if not claude:
        raise ValueError("Claude Code is not installed, or not on your PATH. "
                         "Install it, then try again.")
    # A "project:" job runs IN another repo — Satio, TapGate, Perch — with
    # that repo's own CLAUDE.md steering it. The brain becomes the cockpit
    # for every project, not only itself. cwd is validated by the caller
    # against config sources; here it must simply exist.
    cwd, label = ROOT, job
    if job.startswith("project:"):
        cwd = os.path.expanduser(job.split(":", 2)[1])
        if not os.path.isdir(cwd):
            raise ValueError("that project folder doesn't exist")
        prompt = job.split(":", 2)[2]
        label = "project: " + os.path.basename(cwd)
    else:
        prompt = JOBS.get(job, "/queue")
    # The resolved path, not the bare name: on Windows `claude` is claude.cmd,
    # which Popen will not find from a list argv without the full path.
    cmd = [claude, "-p", prompt,
           "--permission-mode", "bypassPermissions",
           "--output-format", "stream-json", "--verbose"]
    # Real browser hands (Playwright MCP driving her installed Chrome): a run
    # can open a booking site, run the actual search, and read the real
    # options — dynamic prices that no scraper or WebFetch can see. The
    # prompts carry the boundary: never log in, never enter payment.
    mcpcfg = os.path.join(HERE, "mcp-browser.json")
    if os.path.exists(mcpcfg):
        cmd += ["--mcp-config", mcpcfg]
    if job == "queue" and model not in MODELS:
        # She may have picked a model on the queue card itself — that choice
        # is her deciding what to spend, and it must survive to the run. With
        # several pending items the strongest pick wins (one run serves all).
        model = _queue_model_choice()
    if model not in MODELS:
        # Nobody picked: the default is the mode's, unless the Usage page set
        # one explicitly. A picked model — card or page — is never overridden;
        # an explicit choice is her deciding what to spend. Mechanical jobs
        # drop to Haiku when the default would only come from the preset.
        feat = ai_features()
        if job in LIGHT_JOBS and "model" not in feat["overrides"]:
            model = "haiku"
        else:
            model = feat["model"]
    if model in MODELS:
        cmd += ["--model", model]
    # utf-8 with errors="replace": Windows consoles default to cp1252, and one
    # smart quote in the stream must not kill the whole feed.
    proc = subprocess.Popen(cmd, cwd=cwd, stdin=subprocess.DEVNULL,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, encoding="utf-8", errors="replace",
                            bufsize=1, env=SESS.claude_env())
    _agent.update({"running": True, "proc": proc, "lines": ["Starting Claude Code...", ""],
                   "started": datetime.now().isoformat(timespec="seconds"),
                   "job": label, "finished": False, "summary": None,
                   "tokens": None, "out_tokens": None, "seconds": None,
                   "model": model or "", "usage": None, "cost": None,
                   "turns": None})
    threading.Thread(target=_pump, args=(proc,), daemon=True).start()


def _pump(proc):
    for raw in proc.stdout:
        line = _summarise(raw)
        if line:
            _agent["lines"].append(line)
            del _agent["lines"][:-400]      # the feed is a tail, not an archive
    proc.wait()
    ok = proc.returncode == 0
    _agent["running"] = False
    _agent["finished"] = True
    _agent["lines"].append("\nFinished." if ok
                           else f"\nFAILED (exit {proc.returncode}). Nothing was lost — "
                                "your queued asks are still pending.")
    _record_run(ok, proc.returncode)
    rebuild()


def _record_run(ok, code):
    """Keep what happened. Without this the live feed vanishes on the next
    page load and a run that failed looks identical to one that never ran —
    which is exactly what it looked like the first time this was used."""
    # The permanent ledger first: RUNS keeps only the last 20 for the page's
    # history list, so it is a tail, not a record of what this has cost.
    usage.record("run", _agent.get("job") or "run",
                 model=_agent.get("model") or "",
                 usage=_agent.get("usage"), secs=_agent.get("seconds") or 0,
                 cost=_agent.get("cost"), ok=ok, turns=_agent.get("turns"))
    runs = load_json(RUNS, [])
    runs.insert(0, {
        "started": _agent.get("started"),
        "finished": datetime.now().isoformat(timespec="seconds"),
        "job": _agent.get("job"),
        "ok": ok,
        "exit": code,
        "seconds": _agent.get("seconds"),
        "tokens": _agent.get("tokens"),
        "out_tokens": _agent.get("out_tokens"),
        "summary": _agent.get("summary") or ("Finished" if ok else "Failed to run"),
        "log": "\n".join(_agent.get("lines", [])[-120:]),
    })
    save_json(RUNS, runs[:20])


def _usage_audit():
    """The latest /usage-audit report, for the Usage page. The frontmatter's
    `updated:` date is split out; the body ships as markdown the page's own
    tiny renderer draws."""
    path = os.path.join(BRAIN, "usage-audit.md")
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read()
    except OSError:
        return None
    updated = ""
    m = re.match(r"---\s*\n(.*?)\n---\s*\n", text, re.S)
    if m:
        dm = re.search(r"^updated:\s*(\S+)", m.group(1), re.M)
        updated = dm.group(1) if dm else ""
        text = text[m.end():]
    return {"updated": updated, "md": text.strip()}


def _week_usage():
    """Every model call over the last 7 days — page runs, the morning plan, the
    night shift, Sessions turns, draft revisions. Not a percentage of the plan
    (Claude Code does not expose subscription limits to a script) but enough to
    answer "am I leaning on this a lot this week?", and now complete: it reads
    the ledger rather than the 20-item history list the page shows."""
    s = usage.summary(7)
    return {"runs": s["window"]["calls"], "tokens": s["window"]["tokens"],
            "seconds": s["window"]["secs"], "cost": s["window"]["cost"],
            "today": s["today"], "perDay": s["per_day"],
            "byJob": dict(list(s["by_job"].items())[:6]),
            "byModel": s["by_model"], "byDay": s["by_day"]}


def _summarise(raw):
    """One stream-json event, as a line a person can read."""
    raw = raw.strip()
    if not raw:
        return None
    try:
        ev = json.loads(raw)
    except ValueError:
        return raw[:300]
    t = ev.get("type")
    if t == "assistant":
        out = []
        for block in ev.get("message", {}).get("content", []):
            if block.get("type") == "text" and block.get("text", "").strip():
                text = block["text"].strip()
                # The last thing it says is the closest thing to a report,
                # so keep it as the headline for the history list.
                _agent["summary"] = text[:220]
                out.append(text[:400])
            elif block.get("type") == "tool_use":
                inp = block.get("input", {}) or {}
                detail = inp.get("file_path") or inp.get("command") or inp.get("pattern") or ""
                out.append(f"  · {block.get('name')} {str(detail)[:120]}".rstrip())
        return "\n".join(out) or None
    if t == "result":
        secs = round(ev.get("duration_ms", 0) / 1000)
        _agent["seconds"] = secs
        # total_cost_usd is what these tokens WOULD have cost at API rates.
        # On a subscription nothing is billed, so it is kept only as a rough
        # size signal and never shown as money — that was misleading.
        u = ev.get("usage") or {}
        _agent["usage"] = u
        _agent["cost"] = ev.get("total_cost_usd")
        _agent["turns"] = ev.get("num_turns")
        _agent["tokens"] = ((u.get("input_tokens") or 0)
                            + (u.get("output_tokens") or 0)
                            + (u.get("cache_read_input_tokens") or 0)
                            + (u.get("cache_creation_input_tokens") or 0))
        _agent["out_tokens"] = u.get("output_tokens") or 0
        if ev.get("is_error"):
            _agent["summary"] = str(ev.get("result") or "The run reported an error")[:220]
        return f"\nDone in {secs}s."
    return None


def shutil_which(name):
    from shutil import which
    return which(name)


# --------------------------------------------------------------------------
# the server

class Handler(SimpleHTTPRequestHandler):
    # Python's table has no .webmanifest; without this Chrome refuses the
    # manifest and the home-screen icon silently falls back to a screenshot.
    extensions_map = {**SimpleHTTPRequestHandler.extensions_map,
                      ".webmanifest": "application/manifest+json",
                      ".svg": "image/svg+xml"}

    def __init__(self, *a, **kw):
        super().__init__(*a, directory=BRAIN, **kw)

    def log_message(self, *a):
        pass                                     # the terminal stays readable

    def end_headers(self):
        # The page is regenerated constantly; a cached copy is a stale copy.
        if "/api/" in (self.path or ""):
            self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def _json(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _guard(self):
        """Reject a request that a foreign web page could have forged. Returns
        True if it's safe to proceed; sends 403 and returns False otherwise."""
        if not GUARD_ENFORCED:
            return True
        if request_is_own(self.headers.get("Host"),
                          self.headers.get("Origin"), ALLOWED_HOSTS):
            return True
        try:
            body = json.dumps({"error": "cross-site request refused"}).encode()
            self.send_response(403)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except Exception:
            pass
        return False

    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        if n > MAX_BODY:
            raise ValueError("too much data")
        return json.loads(self.rfile.read(n) or b"{}")

    def do_GET(self):
        if self.path.startswith("/enablebanking/callback"):
            # the bank lands her browser here after she approves a link
            q = parse_qs(urlparse(self.path).query)
            import finance
            try:
                bank = finance.finish_link((q.get("code") or [""])[0],
                                           (q.get("state") or [""])[0])
                msg = "Linked %s. You can close this tab." % bank
            except Exception as e:
                msg = "Link failed: %s" % e
            body = ("<meta name=viewport content='width=device-width'>"
                    "<p style='font:18px system-ui;margin:3em'>%s</p>" % msg).encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        # /api reads can return the whole brain (people, drafts, connections),
        # so a rebinding page must not reach them. Static files and the bank
        # callback above stay open — they carry nothing an attacker wants.
        if self.path.startswith("/api/") and not self._guard():
            return
        if self.path.startswith("/api/email/status"):
            import email_send
            import email_read
            return self._json({"accounts": [a["address"] for a in email_send.accounts()],
                               "default": email_send.default_account(),
                               "reading": email_read.reading_on(),
                               "last_check": email_read.last_check()})
        if self.path.startswith("/api/connections"):
            return self._json({"rows": connections_status()})
        if self.path.startswith("/api/plan/bench"):
            # what would fill a freed slot — plain code, computed fresh
            try:
                tmd = read(os.path.join(BRAIN, "today.md"))
            except Exception:
                tmd = ""
            return self._json({"bench": M.bench(M.load(), tmd)})
        if self.path.startswith("/api/newfiles"):
            return self._json({"files": recent_source_files()})
        if self.path.startswith("/api/transcribe"):
            import transcribe as TR
            return self._json({"state": _tr, "busy": TR.whisper_busy(),
                               "recordings": [
                                   {k: r[k] for k in ("path", "name", "minutes",
                                                      "when", "done", "transcript")}
                                   for r in TR.recordings()[:12]]})
        if self.path.startswith("/api/news/article"):
            # Reader-mode text for the speed reader — her click, one story,
            # and news.article_text only serves links from today's briefing.
            from urllib.parse import urlparse, parse_qs
            import news
            url = (parse_qs(urlparse(self.path).query).get("url") or [""])[0]
            try:
                return self._json({"ok": True, "text": news.article_text(url)})
            except Exception as e:
                return self._json({"ok": False, "error": str(e)[:200]})
        if self.path.startswith("/api/version"):
            ago = None
            if _sync["last"]:
                ago = int((datetime.now() - _sync["last"]).total_seconds())
            return self._json({"version": _fingerprint(), "synced_ago": ago,
                               "building": _rb["building"]})
        if self.path.startswith("/api/agent"):
            pend = 0
            try:
                for fn in os.listdir(QUEUE):
                    if fn.endswith(".md") and not fn.startswith("_"):
                        with open(os.path.join(QUEUE, fn), encoding="utf-8") as f:
                            head = f.read(400)
                        sm = re.search(r"^status:\s*(\w+)", head, re.M)
                        if sm and sm.group(1) in ("pending", "working"):
                            pend += 1
            except Exception:
                pass
            return self._json({"running": _agent["running"], "job": _agent["job"],
                               "started": _agent["started"],
                               "finished": _agent["finished"],
                               "pending": pend,
                               "lines": _agent["lines"][-200:],
                               "history": load_json(RUNS, [])[:8],
                               "week": _week_usage(),
                               "night": night_state(),
                               "ai": ai_mode(),
                               "features": ai_features()})
        if self.path.startswith("/api/sessions/feed"):
            from urllib.parse import parse_qs, urlparse
            cid = (parse_qs(urlparse(self.path).query).get("id") or [""])[0]
            return self._json(SESS.feed(cid))
        if self.path.startswith("/api/sessions/emu"):
            try:
                png = SESS.emu_screenshot()
            except ValueError as exc:
                return self._json({"error": str(exc)}, 404)
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.send_header("Content-Length", str(len(png)))
            self.end_headers()
            self.wfile.write(png)
            return None
        if self.path.startswith("/api/sessions/doc"):
            # An outcome file, rendered on demand: read-only, .md only, and it
            # must really live inside that conversation's project folder.
            from urllib.parse import parse_qs, urlparse
            q = parse_qs(urlparse(self.path).query)
            cid = (q.get("id") or [""])[0]
            rel = (q.get("file") or [""])[0]
            data = SESS._load()
            convo = next((c for c in data["convos"] if c["id"] == cid), None)
            if not convo:
                return self._json({"error": "no such conversation"}, 400)
            base = os.path.realpath(convo["path"])
            fp = os.path.realpath(rel if os.path.isabs(rel)
                                  else os.path.join(base, rel))
            if not fp.startswith(base + os.sep) \
                    or not fp.lower().endswith(".md") or not os.path.isfile(fp):
                return self._json({"error": "not a doc I can show"}, 400)
            if os.path.getsize(fp) > 512_000:
                return self._json({"error": "that file is too big to render"}, 400)
            with open(fp, encoding="utf-8", errors="replace") as f:
                _, docbody = MD.split_frontmatter(f.read())
            return self._json({"file": os.path.relpath(fp, base),
                               "html": MD.render(docbody)})
        if self.path.startswith("/api/sessions/transcript"):
            from urllib.parse import parse_qs, urlparse
            cid = (parse_qs(urlparse(self.path).query).get("id") or [""])[0]
            return self._json({"events": SESS.transcript(cid)})
        if self.path.startswith("/api/sessions/room"):
            # One room's live conversations, for the rooms page. Deliberately
            # not /api/sessions: that one walks every source, probes each
            # preview port and scans the drafts folder, which is a lot of work
            # to answer "is anything waiting on me in TapGate".
            from urllib.parse import parse_qs, urlparse
            src = (parse_qs(urlparse(self.path).query).get("src") or [""])[0]
            return self._json({"convos": ROOMS.convos_for(src)})
        if self.path.startswith("/api/sessions/brainbits"):
            # What the brain already knows about this project, offered to the
            # composer so she hands context over instead of typing it out.
            from urllib.parse import parse_qs, urlparse
            src = (parse_qs(urlparse(self.path).query).get("src") or [""])[0]
            cfg = load_json(os.path.join(BRAIN, "config.json"), {})
            match = next((s for s in (cfg.get("sources") or [])
                          if s.get("name") == src), None)
            if not match:
                return self._json({"error": "not a tracked project"}, 400)
            bits = []
            ws_names = set()
            for wing in (cfg.get("rooms", {}).get("wings") or []):
                for room in (wing.get("rooms") or []):
                    if room.get("source") == src:
                        ws_names.update(room.get("ws") or [])
            try:
                for w in M.load():
                    if w.get("name") in ws_names:
                        line = w.get("next_action") or ""
                        if w.get("due"):
                            line += f" (due {w['due']})"
                        if line.strip():
                            bits.append({"label": "The workstream's next move",
                                         "text": line.strip()})
                        opens = [t.get("text", "") for t in (w.get("tasks") or [])
                                 if not t.get("done")][:5]
                        if opens:
                            bits.append({"label": "Its open tasks",
                                         "text": "\n".join("- " + t for t in opens)})
            except Exception:
                pass
            notes = room_notes_for_path(match.get("path", ""))
            if notes:
                bits.append({"label": "Your room notes", "text": notes[:2000]})
            base = os.path.expanduser(match.get("path", ""))
            hand = os.path.join(base, "brain", "handoff.md")
            if os.path.isfile(hand):
                try:
                    with open(hand, encoding="utf-8", errors="replace") as f:
                        boxes = [ln.strip() for ln in f
                                 if ln.strip().startswith("- [ ]")][:3]
                    if boxes:
                        bits.append({"label": "The project brain's top actions",
                                     "text": "\n".join(boxes)})
                except OSError:
                    pass
            # Starred files last, and this project's own first among them: a
            # file she chose beats anything computed, but it is also the long
            # one, so it sits at the bottom of the list.
            stars = list(cfg.get("starred") or [])
            stars.sort(key=lambda s: not os.path.expanduser(s).startswith(base))
            for s in stars:
                full = os.path.expanduser(s)
                try:
                    with open(full, encoding="utf-8", errors="replace") as f:
                        body_text = f.read()
                except OSError:
                    bits.append({"label": os.path.basename(s), "star": s,
                                 "missing": True,
                                 "text": "This starred file is not there any more."})
                    continue
                title = next((ln.lstrip("# ").strip() for ln in
                              body_text.splitlines()[:8]
                              if ln.startswith("# ")), os.path.basename(s))
                bits.append({"label": "★ " + title, "star": s,
                             "text": body_text[:6000].strip(),
                             "where": s})
            return self._json({"bits": bits, "base": base})
        if self.path.startswith("/api/sessions"):
            cfg = load_json(os.path.join(BRAIN, "config.json"), {})
            room_names = {}
            for wing in (cfg.get("rooms", {}).get("wings") or []):
                for room in (wing.get("rooms") or []):
                    if room.get("source"):
                        room_names[room["source"]] = room.get("name", "")
            snap = SESS.snapshot(cfg.get("sources") or [], room_names)
            snap["ai"] = ai_mode()
            # drafts waiting on her, so the page can point at ready-for-you
            teed = []
            ddir = os.path.join(BRAIN, "drafts")
            if os.path.isdir(ddir):
                for fn in sorted(os.listdir(ddir)):
                    if not fn.endswith(".md"):
                        continue
                    try:
                        with open(os.path.join(ddir, fn),
                                  encoding="utf-8", errors="replace") as f:
                            head = f.read(800)
                        if re.search(r"^status:\s*draft", head, re.M):
                            person = re.search(r"^person:\s*(.+)$", head, re.M)
                            kind = re.search(r"^kind:\s*(\w+)", head, re.M)
                            task = re.search(r"^task:\s*(.+)$", head, re.M)
                            teed.append({"file": fn,
                                         "person": person.group(1).strip() if person else "",
                                         "kind": kind.group(1) if kind else "note",
                                         "task": task.group(1).strip() if task else ""})
                    except OSError:
                        continue
            snap["teed"] = teed[:20]
            return self._json(snap)
        if self.path.startswith("/api/usage"):
            # The Usage page's one read: the ledger two ways, every switch's
            # current state, and the latest audit, so one fetch paints the
            # whole page.
            return self._json({"ai": ai_mode(), "features": ai_features(),
                               "night": night_state(),
                               "privacy": privacy_state(),
                               "week": usage.summary(7),
                               "month": usage.summary(30),
                               "audit": _usage_audit(),
                               "running": _agent["running"],
                               "job": _agent["job"]})
        if self.path.startswith("/api/status"):
            items = M.load()
            b = M.briefing(items)
            return self._json({k: [w["name"] for w in b[k]]
                               for k in ("overdue", "chase", "cold", "soon", "yours", "theirs")})
        if self.path.startswith("/api/roomdoc"):
            # A docked doc, rendered on demand: read-only, .md only, and the
            # file must really live inside the configured source folder.
            from urllib.parse import parse_qs, urlparse
            q = parse_qs(urlparse(self.path).query)
            src = (q.get("src") or [""])[0]
            rel = (q.get("file") or [""])[0]
            cfg = load_json(os.path.join(BRAIN, "config.json"), {})
            match = next((s for s in (cfg.get("sources") or [])
                          if s.get("name") == src), None)
            if not match:
                return self._json({"error": "not a tracked project"}, 400)
            base = os.path.realpath(os.path.expanduser(match.get("path", "")))
            fp = os.path.realpath(os.path.join(base, rel))
            if not (fp == base or fp.startswith(base + os.sep)) \
                    or not fp.lower().endswith(".md") or not os.path.isfile(fp):
                return self._json({"error": "not a doc I can show"}, 400)
            if os.path.getsize(fp) > 512_000:
                return self._json({"error": "that file is too big to render"}, 400)
            with open(fp, encoding="utf-8", errors="replace") as f:
                _, docbody = MD.split_frontmatter(f.read())
            return self._json({"file": rel, "html": MD.render(docbody)})
        if self.path.startswith("/api/transcript"):
            # A transcript, rendered on demand: read-only, basename only,
            # always from brain/transcripts/ — the room page's viewer.
            from urllib.parse import parse_qs, urlparse
            q = parse_qs(urlparse(self.path).query)
            fn = os.path.basename((q.get("file") or [""])[0])
            fp = os.path.join(BRAIN, "transcripts", fn)
            if not fn.endswith(".md") or not os.path.isfile(fp):
                return self._json({"error": "no such transcript"}, 400)
            with open(fp, encoding="utf-8", errors="replace") as f:
                _, tbody = MD.split_frontmatter(f.read())
            return self._json({"file": fn, "html": MD.render(tbody)})
        if self.path.startswith("/api/brainsearch"):
            # Search across all the brains: a plain grep over the configured
            # sources' markdown, two levels deep, read-only, bounded.
            from urllib.parse import parse_qs, urlparse
            q = (parse_qs(urlparse(self.path).query).get("q") or [""])[0].strip()
            if len(q) < 2:
                return self._json({"hits": []})
            ql, hits = q.lower(), []
            cfg = load_json(os.path.join(BRAIN, "config.json"), {})
            import sync as _sync_mod
            for s in (cfg.get("sources") or []):
                base = os.path.expanduser(s.get("path", ""))
                if not os.path.isdir(base) or len(hits) >= 60:
                    continue
                seen = 0
                for dirpath, dirs, files in os.walk(base):
                    at_base = os.path.relpath(dirpath, base) == "."
                    dirs[:] = [d for d in dirs if d not in _sync_mod.SKIP_DIRS
                               and not d.startswith(".")] if at_base else []
                    for fn in sorted(files):
                        if not fn.lower().endswith(".md") or seen >= 200:
                            continue
                        seen += 1
                        fp = os.path.join(dirpath, fn)
                        try:
                            if os.path.getsize(fp) > 512_000:
                                continue
                            with open(fp, encoding="utf-8",
                                      errors="replace") as f:
                                for i, line in enumerate(f, 1):
                                    if ql in line.lower():
                                        hits.append({
                                            "source": s.get("name", ""),
                                            "file": os.path.relpath(fp, base),
                                            "line": i,
                                            "text": line.strip()[:200]})
                                        if len(hits) >= 60:
                                            break
                        except OSError:
                            continue
                        if len(hits) >= 60:
                            break
                    if len(hits) >= 60:
                        break
            return self._json({"hits": hits})
        if self.path.startswith("/api/cook/recipe"):
            from urllib.parse import parse_qs, urlparse
            rid = (parse_qs(urlparse(self.path).query).get("id") or [""])[0]
            import cook as COOK
            return self._json(COOK.recipe_detail(rid))
        if self.path in ("/", ""):
            self.path = "/index.html"
        return super().do_GET()

    def do_POST(self):
        # Refuse anything a foreign page could have forged before it can act.
        if not self._guard():
            return
        # The map's and rooms' writes never wait for regeneration: they show
        # the change optimistically and reload when the version stamp moves.
        _ref = self.headers.get("Referer") or ""
        # Every page defers now, not only the map. Waiting for a full
        # rebuild before answering is what made each button feel like it
        # lagged: the click landed, then nothing moved for eight seconds.
        # The page shows the change immediately and reloads itself when the
        # version stamp says the fresh build is on disk.
        _req_ctx.defer_rebuild = bool(_ref)
        try:
            body = self._body()
            if self.path.startswith("/api/cook/"):
                # The kitchen writes only its own files under brain/cooking/
                # and rebuilds only its own page — never the whole set.
                import cook as COOK
                with EDIT:
                    out = COOK.api(self.path[len("/api/cook/"):], body)
                    if not out.get("error"):
                        try:
                            COOK.build()
                        except Exception:
                            pass
                return self._json(out)
            if self.path == "/api/tick":
                tick(body.get("src", ""), body.get("key", ""), bool(body.get("done")))
                # Ticks arrive in bursts — three things get checked off in
                # five seconds — and a blocking rebuild per tick made each
                # one wait on the last. The background rebuild coalesces
                # them into one pass, and the page reloads itself when
                # /api/version says that pass has landed.
                _rebuild_soon()
                return self._json({"ok": True})
            if self.path == "/api/touch":
                set_field(body.get("name", ""), "Touched", date.today().isoformat())
                rebuild()
                return self._json({"ok": True})
            if self.path == "/api/ball":
                ball = body.get("ball", "")
                if ball not in ("me", "them", "nobody"):
                    raise ValueError("ball must be me, them or nobody")
                set_ball(body.get("name", ""), ball)
                rebuild()
                return self._json({"ok": True})
            if self.path == "/api/ws/snooze":
                # Out of sight on purpose until a wake date — it returns by
                # itself. Days from the quick options, or any date parse_due
                # understands ("2026-09-15", "next month", "friday").
                from datetime import timedelta
                days = body.get("days")
                raw = (body.get("until") or "").strip()
                if days:
                    until = date.today() + timedelta(days=int(days))
                elif raw:
                    pd = M.parse_due(raw, date.today())
                    if not pd:
                        raise ValueError("couldn't read that date — try "
                                         "2026-09-15 or 'next month'")
                    until = pd["end"]
                else:
                    raise ValueError("say how long")
                if until <= date.today():
                    raise ValueError("that date is already past")
                set_field(body.get("name", ""), "Snooze", until.isoformat())
                rebuild()
                return self._json({"ok": True, "until": until.isoformat()})
            if self.path == "/api/ws/wake":
                set_field(body.get("name", ""), "Snooze", "")
                rebuild()
                return self._json({"ok": True})
            if self.path == "/api/me/photo":
                # Your face for the centre of the circles view. Local file,
                # gitignored folder, replaceable any time.
                import base64
                data = (body.get("data") or "")
                m = re.match(r"^data:image/(png|jpe?g|webp|gif);base64,(.+)$", data)
                if not m:
                    raise ValueError("that doesn't look like an image")
                raw = base64.b64decode(m.group(2))
                if len(raw) > 8_000_000:
                    raise ValueError("that image is huge — pick something smaller")
                ext = {"jpeg": ".jpg", "jpg": ".jpg", "png": ".png",
                       "webp": ".webp", "gif": ".gif"}[m.group(1)]
                avdir = os.path.join(BRAIN, "avatars")
                os.makedirs(avdir, exist_ok=True)
                for old in (".jpg", ".png", ".webp", ".gif"):
                    try:
                        os.unlink(os.path.join(avdir, "me" + old))
                    except OSError:
                        pass
                with open(os.path.join(avdir, "me" + ext), "wb") as f:
                    f.write(raw)
                rebuild()
                return self._json({"ok": True})
            if self.path == "/api/person/hold":
                # Together until a date: no owed replies, no rhythm, and it
                # lifts itself the day you part. Days or any date parse_due
                # reads ("2026-09-30", "end of september").
                from datetime import timedelta
                days = body.get("days")
                raw = (body.get("until") or "").strip()
                if days:
                    until = date.today() + timedelta(days=int(days))
                elif raw:
                    pd = M.parse_due(raw, date.today())
                    if not pd:
                        raise ValueError("couldn't read that date — try "
                                         "2026-09-30 or 'end of september'")
                    until = pd["end"]
                else:
                    raise ValueError("say until when")
                if until <= date.today():
                    raise ValueError("that date is already past")
                set_person_field(body.get("name", ""), "Hold", until.isoformat())
                rebuild()
                return self._json({"ok": True, "until": until.isoformat()})
            if self.path == "/api/person/every":
                # A person's own rhythm — "3 days", "weekly" — overrides the
                # group's. Empty hands them back to the group default.
                ev = (body.get("every") or "").strip()
                if ev and not M.parse_every(ev):
                    raise ValueError("couldn't read that rhythm — try 'weekly', "
                                     "'3 days', 'monthly'")
                set_person_field(body.get("name", ""), "Every", ev)
                rebuild()
                return self._json({"ok": True, "every": ev})
            if self.path == "/api/person/unhold":
                set_person_field(body.get("name", ""), "Hold", "")
                rebuild()
                return self._json({"ok": True})
            if self.path == "/api/ws/focus":
                # "I want to work on this for a few days" — no invented task,
                # no permanent flag. It expires by itself.
                from datetime import timedelta
                if body.get("off"):
                    set_field(body.get("name", ""), "Focus", "")
                    rebuild()
                    return self._json({"ok": True, "until": ""})
                days = int(body.get("days") or 3)
                days = max(1, min(30, days))
                until = date.today() + timedelta(days=days)
                set_field(body.get("name", ""), "Focus", until.isoformat())
                rebuild()
                return self._json({"ok": True, "until": until.isoformat()})
            if self.path == "/api/ws/done":
                # Finished, said plainly — the whole thing leaves the plate.
                set_field(body.get("name", ""), "Status", "Done")
                set_field(body.get("name", ""), "Touched", date.today().isoformat())
                rebuild()
                return self._json({"ok": True})
            if self.path == "/api/ws/due":
                # A workstream with no date can't be placed on the horizon —
                # this is how a dot leaves the "No date" pile and joins the
                # timeline. Empty clears it back to undated.
                raw = (body.get("due") or "").strip()
                if raw:
                    pd = M.parse_due(raw, date.today())
                    if not pd:
                        raise ValueError("give a date, a range, or a window "
                                         "like 'this week' or 'mid-September'")
                    val = (pd["start"].isoformat() if pd["start"] == pd["end"]
                           else pd["start"].isoformat() + ".." + pd["end"].isoformat())
                else:
                    val = ""
                set_field(body.get("name", ""), "Due", val)
                rebuild()
                return self._json({"ok": True, "due": val})
            if self.path == "/api/ws/person":
                # A hand-made person link on a workstream. The scan finds
                # names in text; this is for the ones it can't see. An
                # optional role ("tester", "contractor") labels what they
                # are to THIS project — written as `Name (role)`.
                who = (body.get("person") or "").strip()
                wsn = (body.get("name") or "").strip()
                role = (body.get("role") or "").strip().strip("()")
                known = {p["name"].lower(): p["name"] for p in M.load_people()}
                if who.lower() not in known:
                    raise ValueError(f"no one called '{who}' in your people — "
                                     "add them first, or check the spelling")
                who = known[who.lower()]
                cur = next((w for w in M.load()
                            if w["name"].lower() == wsn.lower()), None)
                if cur is None:
                    raise ValueError(f"no workstream called '{wsn}'")
                have = list(cur.get("linked_people", []))
                roles = dict(cur.get("people_roles") or {})
                if who not in have:
                    have.append(who)
                if role:
                    roles[who] = role
                set_field(cur["name"], "People", ", ".join(
                    nm + (f" ({roles[nm]})" if roles.get(nm) else "")
                    for nm in have))
                rebuild()
                return self._json({"ok": True, "person": who})
            if self.path == "/api/reveal":
                # Open a project folder in the file manager — a door from the
                # brain to the files. Home directory only; nothing else is
                # reachable.
                p = os.path.expanduser((body.get("path") or "").strip())
                rp = os.path.realpath(p)
                home = os.path.realpath(os.path.expanduser("~"))
                if rp != home and not rp.startswith(home + os.sep):
                    raise ValueError("outside your home folder")
                if not os.path.exists(rp):
                    raise ValueError("that folder doesn't exist")
                open_folder(rp, select=bool(body.get("select")))
                return self._json({"ok": True})
            if self.path == "/api/task":
                task_action(body.get("src", ""), body.get("key", ""),
                            body.get("action", ""), body.get("until", ""),
                            body.get("text", ""))
                rebuild(map_too=False)
                return self._json({"ok": True})
            if self.path == "/api/plan":
                said = plan_edit(body.get("op", ""), body.get("key", ""),
                                 body.get("pick", ""), body.get("day", ""))
                rebuild(map_too=False)
                return self._json({"ok": True, "said": said})
            if self.path == "/api/task/progress":
                got = task_progress(body.get("src", ""), body.get("key", ""),
                                    body.get("who", ""), body.get("days", 7),
                                    body.get("rewrite", ""))
                rebuild()
                return self._json({"ok": True, **got})
            if self.path == "/api/upload":
                return self._json({"ok": True, "saved": save_files(body.get("files", []))})
            if self.path == "/api/add/task":
                add_task(body.get("name", ""), body.get("text", ""), body.get("due", ""))
                rebuild()
                return self._json({"ok": True})
            if self.path == "/api/add/workstream":
                nm = add_workstream(body.get("name", ""), body.get("area", ""),
                                    body.get("ball", "me"), body.get("why", ""),
                                    body.get("next", ""), body.get("due", ""))
                rebuild()
                return self._json({"ok": True, "name": nm})
            if self.path == "/api/add/waiting":
                add_waiting(body.get("what", ""), body.get("who", ""),
                            body.get("chase", ""))
                rebuild(map_too=False)
                return self._json({"ok": True})
            if self.path.startswith("/api/beeper/"):
                import beeper
                what = self.path.rsplit("/", 1)[-1]
                if what == "sync":
                    upd, un, total = beeper.collect(write=True)
                    rebuild(map_too=False)
                    return self._json({"ok": True, "updated": upd,
                                       "unmatched": un, "total": total})
                if what == "focus":
                    got = beeper.focus_chat((body.get("person") or "").strip())
                    return self._json({"ok": True, **got})
                if what == "review":
                    _, un, total = beeper.collect(write=False)
                    return self._json({"ok": True, "unmatched": un, "total": total,
                                       "people": [w["name"] for w in M.load_people()]})
                if what == "link":
                    beeper.link_alias(body.get("chat", ""), body.get("person", ""))
                    beeper.collect(write=True)      # apply the date immediately
                    rebuild(map_too=False)
                    return self._json({"ok": True})
                if what == "ignore":
                    # One name or many. Hiding must STICK: write the ignore
                    # list, purge the cached review file the page renders
                    # from, and rebuild — otherwise the row resurrects on the
                    # next reload and the button looks like a lie.
                    names = [n for n in (body.get("chats") or [body.get("chat", "")])
                             if (n or "").strip()]
                    for n in names:
                        beeper.ignore_chat(n)
                    low = {n.strip().lower() for n in names}
                    cache = os.path.join(BRAIN, ".beeper-review.json")
                    try:
                        data = load_json(cache, {})
                        data["unmatched"] = [u for u in (data.get("unmatched") or [])
                                             if (u.get("name") or "").strip().lower() not in low]
                        save_json(cache, data)
                    except Exception:
                        pass
                    rebuild(map_too=False)
                    return self._json({"ok": True, "hidden": len(names)})
                if what == "adopt":
                    circle = body.get("circle", "Friends")
                    # A One-off is someone she does not want a rhythm with:
                    # keep the record, but it never surfaces. Anyone else gets
                    # their circle's cadence, then a date sync fills in "last".
                    add_person(body.get("chat", ""), "", circle, "nobody", "", False,
                               body.get("how", ""))
                    beeper.collect(write=True)
                    rebuild(map_too=False)
                    return self._json({"ok": True})
                if what == "adopt-batch":
                    made = []
                    for it in (body.get("items") or [])[:400]:
                        try:
                            add_person(it.get("chat", ""), "", it.get("circle", "Friends"),
                                       "nobody", "", False, "")
                            made.append(it.get("chat"))
                        except ValueError:
                            pass
                    beeper.collect(write=True)
                    rebuild(map_too=False)
                    return self._json({"ok": True, "added": made})
                return self._json({"error": "no such beeper action"}, 404)
            if self.path.startswith("/api/draft/"):
                what = self.path.rsplit("/", 1)[-1]
                fn = os.path.basename(body.get("file", ""))
                dpath = os.path.join(BRAIN, "drafts", fn)
                if not (fn.endswith(".md") and os.path.isfile(dpath)):
                    raise ValueError("no such draft")
                if what == "edit":
                    draft_edit(fn, body.get("body", ""))
                    rebuild(map_too=False)
                    return self._json({"ok": True})
                if what == "revise":
                    nb = draft_revise(fn, body.get("instruction", ""))
                    rebuild(map_too=False)
                    return self._json({"ok": True, "body": nb})
                if what in ("sent", "discard"):
                    txt = read(dpath)
                    st = "sent" if what == "sent" else "discarded"
                    if re.search(r"^status:", txt, re.M):
                        txt = re.sub(r"^status:.*$", f"status: {st}", txt, count=1, flags=re.M)
                    else:
                        txt = txt.replace("\n---\n", f"\nstatus: {st}\n---\n", 1)
                    write(dpath, txt)
                    rebuild(map_too=False)
                    return self._json({"ok": True})
                if what == "send-email":
                    d = {x["file"]: x for x in M.load_drafts()}.get(fn)
                    if not d:
                        raise ValueError("draft not found or already sent")
                    if d["personal"]:
                        raise ValueError("that person is personal (Inner/Close/etc) "
                                         "— email is draft-only for them")
                    if d["kind"] != "email" or not d["to"]:
                        raise ValueError("not an email draft with a recipient")
                    import email_send
                    ok, detail = email_send.send(d["to"], d["subject"], d["body"],
                                                 body.get("from") or None,
                                                 person=d.get("person") or None)
                    if not ok:
                        raise ValueError(detail)
                    txt = read(dpath)
                    txt = re.sub(r"^status:.*$", "status: sent", txt, count=1, flags=re.M)
                    write(dpath, txt)
                    rebuild(map_too=False)
                    return self._json({"ok": True})
                if what == "beeper-send":
                    # The hard boundary: never send to Inner/Close, ever, even
                    # if the draft file claims otherwise. Re-derive from people.
                    drafts = {d["file"]: d for d in M.load_drafts()}
                    d = drafts.get(fn)
                    if not d:
                        raise ValueError("draft not found or already sent")
                    if d["personal"]:
                        raise ValueError("that person is in your Inner/Close circle "
                                         "— Claude can't send to them, only draft")
                    if d["channel"] != "beeper":
                        raise ValueError("not a Beeper draft")
                    import beeper
                    ok, msg = beeper.send_message(d["person"], d["body"])
                    if not ok:
                        raise ValueError(msg)
                    txt = read(dpath)
                    txt = re.sub(r"^status:.*$", "status: sent", txt, count=1, flags=re.M)
                    write(dpath, txt)
                    rebuild(map_too=False)
                    return self._json({"ok": True})
                raise ValueError("unknown draft action")
            if self.path == "/api/person/promise":
                add_promise(body.get("name", ""), body.get("text", ""))
                rebuild(map_too=False)
                return self._json({"ok": True})
            if self.path == "/api/person/circle":
                circle = (body.get("circle") or "").strip()
                if circle and circle.lower() not in M.circles():
                    raise ValueError(f"{circle!r} isn't one of your groups")
                set_person_field(body.get("name", ""), "Circle", circle)
                rebuild()
                return self._json({"ok": True})
            if self.path == "/api/circle/add":
                nm = (body.get("name") or "").strip()
                if not nm:
                    raise ValueError("give the group a name")
                cfg = load_json(os.path.join(BRAIN, "config.json"), {})
                cs = cfg.get("circles") or [dict(c) for c in M._DEFAULT_CIRCLES]
                if any((c.get("name") or "").lower() == nm.lower() for c in cs):
                    raise ValueError(f"you already have a {nm} group")
                every = (body.get("every") or "monthly").strip()
                personal = bool(body.get("personal", True))
                # New groups go before One-off so it stays last.
                idx = next((i for i, c in enumerate(cs)
                            if (c.get("name") or "").lower() in ("one-off", "oneoff")), len(cs))
                cs.insert(idx, {"name": nm, "every": every, "personal": personal})
                cfg["circles"] = cs
                write(os.path.join(BRAIN, "config.json"), json.dumps(cfg, indent=2) + "\n")
                rebuild(map_too=True)
                return self._json({"ok": True, "name": nm})
            if self.path == "/api/circle/edit":
                nm = (body.get("name") or "").strip()
                cfg = load_json(os.path.join(BRAIN, "config.json"), {})
                cs = cfg.get("circles") or [dict(c) for c in M._DEFAULT_CIRCLES]
                hit = next((c for c in cs
                            if (c.get("name") or "").lower() == nm.lower()), None)
                if not hit:
                    raise ValueError(f"no group called '{nm}'")
                # Empty every is a real choice: no rhythm, nobody in the group
                # ever goes "quiet". A rhythm set on one person still wins.
                hit["every"] = (body.get("every") or "").strip()
                if "personal" in body:
                    hit["personal"] = bool(body.get("personal"))
                cfg["circles"] = cs
                write(os.path.join(BRAIN, "config.json"), json.dumps(cfg, indent=2) + "\n")
                rebuild(map_too=True)
                return self._json({"ok": True, "name": hit["name"],
                                   "every": hit["every"]})
            if self.path == "/api/circle/rename":
                # Renaming a group has to take its people with it. The circle
                # lives in two places — the list in config.json and a `Circle:`
                # line on every person — and changing only the first orphans
                # everybody into a group that no longer exists.
                old = (body.get("name") or "").strip()
                new = (body.get("to") or "").strip()
                if not new:
                    raise ValueError("give the group its new name")
                if len(new) > 60 or "\n" in new:
                    raise ValueError("a name, not a paragraph")
                cfg = load_json(os.path.join(BRAIN, "config.json"), {})
                cs = cfg.get("circles") or [dict(c) for c in M._DEFAULT_CIRCLES]
                hit = next((c for c in cs
                            if (c.get("name") or "").lower() == old.lower()), None)
                clash = next((c for c in cs
                              if (c.get("name") or "").lower() == new.lower()
                              and c is not hit), None)
                # Renaming onto a group she already has is a MERGE, and it is
                # the one-click fix for a stray group like "Friends (guess)".
                # It has to be deliberate, so it is asked for by name.
                if clash and not body.get("merge"):
                    raise ValueError(f"you already have a {clash['name']} group — "
                                     "tick merge to fold this one into it")
                if hit and clash:
                    cs = [c for c in cs if c is not hit]
                elif hit:
                    hit["name"] = new
                elif not clash:
                    raise ValueError(f"no group called '{old}'")
                cfg["circles"] = cs
                write(os.path.join(BRAIN, "config.json"),
                      json.dumps(cfg, indent=2) + "\n")
                # Every person filed under the old name, moved. Matching is
                # case-insensitive on the whole field so "friends (guess)"
                # and "Friends (Guess)" both travel.
                moved, lines = 0, read(PEOPLE).split("\n")
                for i, line in enumerate(lines):
                    m = re.match(r"^(\s*-\s+\*\*Circle:\*\*\s*)(.*?)\s*$", line)
                    if m and m.group(2).lower() == old.lower():
                        lines[i] = m.group(1) + new
                        moved += 1
                if moved:
                    write(PEOPLE, "\n".join(lines))
                rebuild(map_too=True)
                return self._json({"ok": True, "name": new, "moved": moved,
                                   "merged": bool(clash)})
            if self.path == "/api/circles/reorder":
                order = body.get("order") or []
                cfg = load_json(os.path.join(BRAIN, "config.json"), {})
                cs = cfg.get("circles") or [dict(c) for c in M._DEFAULT_CIRCLES]
                by = {(c.get("name") or "").lower(): c for c in cs}
                seen, newcs = set(), []
                for nm in order:                       # the circles she reordered, in her order
                    c = by.get((nm or "").lower())
                    if c and c["name"].lower() not in seen:
                        newcs.append(c); seen.add(c["name"].lower())
                for c in cs:                            # keep the rest (empty circles, one-off) as-is
                    if (c.get("name") or "").lower() not in seen:
                        newcs.append(c); seen.add((c.get("name") or "").lower())
                cfg["circles"] = newcs
                write(os.path.join(BRAIN, "config.json"), json.dumps(cfg, indent=2) + "\n")
                rebuild()
                return self._json({"ok": True})
            if self.path == "/api/person/rename":
                nm = person_rename(body.get("name", ""), body.get("new", ""))
                rebuild()
                return self._json({"ok": True, "name": nm})
            if self.path == "/api/person/merge":
                person_merge(body.get("name", ""), body.get("into", ""))
                rebuild()
                return self._json({"ok": True})
            if self.path == "/api/person/remove":
                person_delete(body.get("name", ""),
                              archive=bool(body.get("archive")))
                rebuild()
                return self._json({"ok": True})
            if self.path == "/api/person/focus":
                set_person_field(body.get("name", ""), "Focus",
                                 "yes" if body.get("focus") else "no")
                rebuild()
                return self._json({"ok": True})
            if self.path == "/api/person/spoke":
                person_spoke(body.get("name", ""))
                rebuild()
                return self._json({"ok": True})
            if self.path == "/api/person/ball":
                ball = body.get("ball", "")
                if ball not in ("me", "them", "nobody"):
                    raise ValueError("ball must be me, them or nobody")
                set_person_field(body.get("name", ""), "Ball",
                                 {"me": "Me", "them": "Them", "nobody": "Nobody"}[ball])
                rebuild(map_too=False)
                return self._json({"ok": True})
            if self.path == "/api/add/person":
                nm = add_person(body.get("name", ""), body.get("every", ""),
                                body.get("circle", ""), body.get("ball", "nobody"),
                                body.get("why", ""), bool(body.get("focus")),
                                body.get("how", ""), body.get("where", ""),
                                body.get("birthday", ""))
                rebuild(map_too=False)
                return self._json({"ok": True, "name": nm})
            if self.path == "/api/habit/target":
                n = set_habit_target(body.get("name", ""), body.get("target"))
                rebuild(map_too=False)
                return self._json({"ok": True, "target": n})
            if self.path == "/api/habit":
                done = toggle_habit(body.get("name", ""))
                rebuild(map_too=False)
                return self._json({"ok": True, "done": done})
            if self.path == "/api/season/slot":
                season_slot(body.get("key", ""), body.get("day", ""))
                rebuild(map_too=False)
                return self._json({"ok": True})
            if self.path == "/api/season/add":
                season_add(body.get("text", ""))
                rebuild(map_too=False)
                return self._json({"ok": True})
            if self.path == "/api/news/refresh":
                import news
                news.fetch()
                rebuild(map_too=False)
                return self._json({"ok": True})
            if self.path == "/api/news/interest":
                import news
                add = (body.get("add") or "").strip()
                remove = (body.get("remove") or "").strip()
                if add:
                    news.add_interest(add)
                if remove and not news.remove_interest(remove):
                    raise ValueError("no such topic")
                news.fetch()
                rebuild(map_too=False)
                return self._json({"ok": True})
            if self.path == "/api/capture":
                text = (body.get("text") or "").strip()
                if not text:
                    raise ValueError("nothing to capture")
                capture(text)
                rebuild(map_too=False)
                return self._json({"ok": True})
            if self.path == "/api/question/answer":
                # The answer is WRITTEN first. Only queuing it meant a reload
                # wiped what she had typed and the question came back empty,
                # which is how an answer got lost.
                key = (body.get("key") or "").strip()
                ans = (body.get("answer") or "").strip()
                if not ans:
                    raise ValueError("nothing to file")
                path = os.path.join(BRAIN, "questions.md")
                lines = read(path).split("\n")
                hit = None
                for i, line in enumerate(lines):
                    m = re.match(r"^(\s*[-*]\s+)\[([ xX])\]\s+(.*)$", line)
                    if m and MD.taskkey(_bare(m.group(3))) == key:
                        hit = (i, m)
                        break
                if not hit:
                    raise ValueError("that question has changed — reload the page")
                i, m = hit
                lines[i] = (f"{m.group(1)}[x] {m.group(3)}\n"
                            f"      **You said:** {ans}")
                write(path, "\n".join(lines))
                queue_request(
                    "A question in brain/questions.md now carries her answer: "
                    f"\u201c{MD.plain(m.group(3))}\u201d \u2014 she said: {ans}\n\n"
                    "Put that fact where it actually lives (config, "
                    "workstreams, people, about-me), then tidy the question "
                    "away. Do not ask her again.", "just-do-it")
                rebuild(map_too=False)
                # Her answer IS "run it again" \u2014 a question the brain asked
                # and she unblocked shouldn't also need her to find a button.
                # If a run is already going, the item waits for the next one.
                started = False
                try:
                    start_agent("queue")
                    started = True
                except ValueError:
                    pass
                return self._json({"ok": True, "started": started})
            if self.path == "/api/queue":
                text = (body.get("text") or "").strip()
                if not text:
                    raise ValueError("nothing to queue")
                # A journal entry is kept, not queued: the words go straight
                # to brain/journal/ with no Claude run. The next attended
                # session farms it.
                if body.get("mode") == "journal":
                    day = journal_keep(text, "page")
                    rebuild(map_too=False)
                    return self._json({"ok": True, "journal": day})
                name = queue_request(text, body.get("mode", "just-do-it"),
                                     body.get("model", ""), body.get("files") or [])
                rebuild(map_too=False)
                return self._json({"ok": True, "file": name})
            if self.path == "/api/sync":
                import sync
                n, items, brains = sync.sync()
                _sync["last"] = datetime.now()
                rebuild()
                return self._json({"ok": True, "sources": n, "items": items,
                                   "brains": brains})
            if self.path == "/api/appearance":
                import build as _b
                ap = {}
                for k, allowed in (("base", _b.BASES), ("accent", _b.ACCENTS),
                                   ("font", _b.FONTS), ("dots", _b.DOTS),
                                   ("style", _b.STYLES)):
                    v = body.get(k)
                    if v in allowed:
                        ap[k] = v
                # A whole palette in one click: it fills in everything the
                # individual controls set, and any explicit value still wins.
                pal = body.get("palette")
                if pal in _b.PALETTES:
                    base = dict(_b.PALETTES[pal])
                    base.update(ap)
                    ap = base
                    ap["palette"] = pal
                cfg = load_json(os.path.join(BRAIN, "config.json"), {})
                cur = cfg.get("appearance", {}) or {}
                if ap.get("palette") is None and cur.get("palette"):
                    cur.pop("palette", None)      # hand-tuned: no longer a preset
                cur.update(ap)
                cfg["appearance"] = cur
                write(os.path.join(BRAIN, "config.json"), json.dumps(cfg, indent=2) + "\n")
                rebuild(map_too=True)
                return self._json({"ok": True, "appearance": cur})
            if self.path == "/api/telegram/setup":
                # The token pasted straight into the page — validated against
                # Telegram before it's saved, so a bad paste fails loudly now
                # instead of silently never pairing.
                token = (body.get("token") or "").strip()
                if not re.fullmatch(r"\d+:[A-Za-z0-9_-]{30,}", token):
                    raise ValueError("that doesn't look like a bot token — "
                                     "it's digits, a colon, then a long code")
                import urllib.request as _ur
                try:
                    with _ur.urlopen("https://api.telegram.org/bot"
                                     + token + "/getMe", timeout=10) as r:
                        me = json.load(r)
                except Exception:
                    me = {}
                if not me.get("ok"):
                    raise ValueError("Telegram didn't accept that token — "
                                     "copy it again from BotFather")
                tf = os.path.join(BRAIN, ".telegram.json")
                conf = load_json(tf, {})
                conf["token"] = token
                if not conf.get("chat_id") and not conf.get("pair_code"):
                    # Bot usernames are public; pairing needs this code, so
                    # a stranger finding the bot first gets nothing.
                    import secrets as _sec
                    conf["pair_code"] = f"{_sec.randbelow(900000) + 100000}"
                write(tf, json.dumps(conf, indent=2) + "\n")
                rebuild(map_too=False)
                return self._json({"ok": True, "bot":
                                   (me.get("result") or {}).get("username", ""),
                                   "pair_code": conf.get("pair_code", "")})
            if self.path == "/api/calendar":
                cfgp = os.path.join(BRAIN, "config.json")
                cfg = load_json(cfgp, {})
                cfg["calendar"] = bool(body.get("on"))
                write(cfgp, json.dumps(cfg, indent=2) + "\n")
                rebuild(map_too=False)
                return self._json({"ok": True, "calendar": cfg["calendar"]})
            if self.path == "/api/calendar/block":
                # A block SHE asked for, written to the Brain calendar only —
                # calendar_write.py carries the leash (never touches other
                # calendars or events; delete the Brain calendar, all gone).
                import calendar_write
                title = (body.get("title") or "").strip()
                d = M.parse_date((body.get("day") or "").strip())
                if not d:
                    raise ValueError("give the day as a date")
                m2 = re.fullmatch(r"(\d{1,2}):(\d{2})",
                                  (body.get("time") or "").strip())
                if not m2:
                    raise ValueError("give a start time like 14:00")
                when = datetime(d.year, d.month, d.day,
                                int(m2.group(1)), int(m2.group(2)))
                if when < datetime.now():
                    raise ValueError("that time is already past")
                out = calendar_write.block(title, when,
                                           int(body.get("minutes") or 60))
                return self._json({"ok": True, **out})
            if self.path == "/api/transcribe/adopt":
                # She has already run whisper herself — file that transcript
                # and go straight to the part that matters.
                import transcribe as TR
                src = (body.get("path") or "").strip()
                known = {t["path"] for t in TR.existing_transcripts()}
                if src not in known:
                    raise ValueError("that isn't a transcript I can see")
                room = (body.get("room") or "").strip()[:60]
                dest = TR.adopt(src, room, (body.get("language") or "fr")[:8])
                name = os.path.basename(dest)
                queue_request(TR.ask_text(name, room), "just-do-it")
                rebuild(map_too=False)
                return self._json({"ok": True, "transcript": name})
            if self.path == "/api/transcribe":
                # Long work (minutes to an hour), so it runs in a thread and
                # the page watches _tr. One at a time: two whisper runs on
                # one GPU is slower than either alone.
                import transcribe as TR
                if _tr["running"]:
                    raise ValueError("already transcribing " + _tr["name"])
                src = (body.get("path") or "").strip()
                known = {r["path"] for r in TR.recordings()}
                if src not in known:
                    raise ValueError("that isn't one of the recordings I can see")
                lang = (body.get("language") or "fr").strip()[:8]
                room = (body.get("room") or "").strip()[:60]
                prompt = (body.get("prompt") or "").strip()[:400]
                _tr.update({"running": True, "name": os.path.basename(src),
                            "note": "starting", "done": "", "error": ""})

                def go():
                    try:
                        dest = TR.transcribe(
                            src, lang, prompt, room,
                            progress=lambda m: _tr.__setitem__("note", m))
                        name = os.path.basename(dest)
                        # The transcript is only half the point: queue the ask
                        # that turns it into this project's tasks.
                        queue_request(TR.ask_text(name, room), "just-do-it")
                        _tr.update({"done": name, "note": "queued the update"})
                    except Exception as exc:
                        _tr["error"] = str(exc)[:300]
                    finally:
                        _tr["running"] = False
                        _rebuild_soon()

                threading.Thread(target=go, daemon=True).start()
                return self._json({"ok": True})
            if self.path == "/api/calendar/target":
                # Which calendar blocks land in. One that belongs to an
                # account (her HEC/Exchange one) is what makes them appear
                # in Outlook on her phone; "" keeps them Mac-local.
                import calendar_write
                t = (body.get("target") or "").strip()
                if t and t not in calendar_write.calendars():
                    raise ValueError("that isn't a writable calendar here")
                cfgp = os.path.join(BRAIN, "config.json")
                cfg = load_json(cfgp, {})
                cfg["calendar_target"] = t
                write(cfgp, json.dumps(cfg, indent=2) + "\n")
                rebuild(map_too=False)
                return self._json({"ok": True, "target": t})
            if self.path == "/api/calendar/test":
                # One real read, so "connected" means seen-with-own-eyes. The
                # first run makes macOS ask permission — that's the point.
                import calendar_read
                evs = calendar_read.events(7)
                return self._json({"ok": True, "count": len(evs),
                                   "sample": [t for _, t in evs[:3]]})
            if self.path == "/api/email/setup":
                import email_send
                addr = email_send.add_account(body.get("address", ""),
                                              body.get("provider", ""),
                                              body.get("app_password", ""))
                rebuild(map_too=False)
                return self._json({"ok": True, "address": addr})
            if self.path == "/api/aifeature":
                set_ai_feature(body.get("key", ""), body.get("value"))
                return self._json({"ok": True, "features": ai_features()})
            if self.path == "/api/aimode":
                set_ai_mode(body.get("mode", ""))
                rebuild(map_too=False)
                return self._json({"ok": True, "ai": ai_mode()})
            if self.path == "/api/aiplan":
                feat = set_ai_plan((body.get("plan") or "").strip())
                rebuild(map_too=False)
                return self._json({"ok": True, "ai": ai_mode(),
                                   "features": feat})
            if self.path == "/api/night":
                st = set_night(bool(body.get("enabled")))
                rebuild(map_too=False)
                return self._json({"ok": True, "night": st})
            if self.path == "/api/privacy":
                set_privacy(bool(body.get("on")))
                return self._json({"ok": True, "privacy": privacy_state()})
            if self.path == "/api/plan/set":
                plan_set((body.get("remove") or "").strip(),
                         (body.get("add") or "").strip())
                rebuild(map_too=True)
                return self._json({"ok": True})
            if self.path == "/api/room/goal":
                add_goal(body.get("room", ""), body.get("text", ""),
                         body.get("due", ""))
                rebuild(map_too=True)
                return self._json({"ok": True})
            if self.path == "/api/room/feedback":
                # Tester feedback, logged where it can't evaporate: dated,
                # in the room's notes — so every session there reads it.
                path = room_notes_path((body.get("slug") or "").strip())
                fb = (body.get("text") or "").strip()
                if not fb:
                    raise ValueError("nothing to log")
                try:
                    with open(path, encoding="utf-8") as f:
                        cur = f.read()
                except OSError:
                    cur = ""
                if "## Feedback" not in cur:
                    cur = (cur.rstrip() + "\n\n" if cur.strip() else "") \
                        + "## Feedback\n"
                cur = cur.rstrip() + f"\n- {date.today().isoformat()} — {fb}\n"
                os.makedirs(os.path.dirname(path), exist_ok=True)
                write(path, cur)
                rebuild(map_too=True)
                return self._json({"ok": True})
            if self.path == "/api/email/read":
                # Consent, as a switch with one owner. Reading stays off until
                # this writes the flag, and turning it off deletes it — there
                # is no half state where something reads "just this once".
                import email_read
                on = bool(body.get("on"))
                if on and not email_send_ready():
                    raise ValueError("connect a mail account first — reading uses "
                                     "the app password that is already in your Keychain")
                email_read.set_reading(on, int(body.get("days") or 14))
                rebuild(map_too=False)
                return self._json({"ok": True, "reading": on})
            if self.path == "/api/email/check":
                # Headers only, on her click, never on a schedule. The morning
                # job and the night shift do not call this.
                import email_read
                r = email_read.check(days=body.get("days"),
                                     write=bool(body.get("write")))
                rebuild(map_too=False)
                return self._json(r)
            if self.path == "/api/writing":
                # Her voice guide, edited from the page. The frontmatter is
                # the server's job — she edits prose and the `updated:` stamp
                # follows on its own, which is the only way a date stays true.
                text = (body.get("text") or "").strip()
                if not text:
                    raise ValueError("that would leave Claude with no voice guide")
                path = os.path.join(BRAIN, "writing-rules.md")
                try:
                    with open(path, encoding="utf-8") as f:
                        meta, _ = MD.split_frontmatter(f.read())
                except OSError:
                    meta = {}
                meta = dict(meta or {})
                meta["updated"] = date.today().isoformat()
                meta.setdefault("maintained-by",
                                "the owner (edit freely — this is her voice guide, verbatim)")
                head = "---\n" + "".join(f"{k}: {v}\n" for k, v in meta.items()) + "---\n\n"
                write(path, head + text + "\n")
                rebuild()
                return self._json({"ok": True})
            if self.path == "/api/room/notes":
                # the room's memory: saved as plain markdown, prepended to
                # every project session in that repo by room_notes_for_path
                path = room_notes_path((body.get("slug") or "").strip())
                text = (body.get("text") or "").rstrip()
                os.makedirs(os.path.dirname(path), exist_ok=True)
                write(path, text + "\n" if text else "")
                rebuild(map_too=True)
                return self._json({"ok": True})
            if self.path == "/api/agent":
                job = body.get("job", "queue")
                if job == "project":
                    # a session in another repo: path must be a configured
                    # source, the ask must be real, and the repo's own
                    # CLAUDE.md steers the run
                    p = (body.get("path") or "").strip()
                    text = (body.get("text") or "").strip()
                    if not text:
                        raise ValueError("say what Claude should do there")
                    if len(text) > MAX_ASK_CHARS:
                        raise ValueError("That's a very long ask — split it "
                                         "up, or attach the long part as a "
                                         "file, so Claude doesn't choke on it.")
                    cfg2 = load_json(os.path.join(BRAIN, "config.json"), {})
                    okpaths = {s.get("path") for s in (cfg2.get("sources") or [])}
                    if p not in okpaths:
                        raise ValueError("that folder isn't a tracked project")
                    notes = room_notes_for_path(p)
                    if notes:
                        text = ("Context from the owner's room notes for this "
                                "project — read this first, it travels into "
                                "every session here:\n\n" + notes
                                + "\n\n---\n\n" + text)
                    job = ("project:" + p + ":"
                           + text + "\n\nWhen you finish, end with a short "
                           "plain-language summary of what you did and what "
                           "remains — it becomes the run's report.")
                if job == "queue" and _queue_pending_count() == 0:
                    # A run costs the same whether it finds five items or
                    # none: the whole brain is loaded before the first tool
                    # call. One run in the last twenty did exactly this —
                    # twenty-one cents to report "no pending items".
                    raise ValueError("Nothing is waiting in the queue — "
                                     "a run would cost the same as a full "
                                     "one and find nothing to do.")
                # The day's ceiling, when she has set one. Scheduled work is
                # never blocked (it is the cheap, predictable half); this
                # stops a page-started run from opening a new one without her
                # saying so a second time.
                cap = _spend_cap_hit()
                if cap and not body.get("anyway"):
                    raise ValueError(cap)
                start_agent(job, body.get("model", ""))
                return self._json({"ok": True})
            if self.path == "/api/agent/stop":
                p = _agent.get("proc")
                if p and _agent["running"]:
                    p.terminate()
                return self._json({"ok": True})
            if self.path == "/api/sessions/new":
                # Task- and person-scoped conversations ("Talk it through")
                # live in the brain's own folder, opened with a context pack
                # assembled mechanically — the task, its workstream, the
                # people it names. The brain's CLAUDE.md steers them, so
                # every boundary (drafts only, no sending) rides along free.
                kind = (body.get("kind") or "").strip()
                if kind in ("task", "person"):
                    import context as CTX
                    packtext, label = CTX.pack(kind, body)
                    convo = SESS.new_convo("brain", ROOT,
                                           body.get("text") or label,
                                           topic=label, pack=packtext)
                    text = (body.get("text") or "").strip()
                    if text:
                        SESS.say(convo["id"], text, body.get("model", ""),
                                 ai_mode(), "")
                    return self._json({"ok": True, "id": convo["id"]})
                src = (body.get("src") or "").strip()
                cfg2 = load_json(os.path.join(BRAIN, "config.json"), {})
                match = next((s for s in (cfg2.get("sources") or [])
                              if s.get("name") == src), None)
                if not match:
                    raise ValueError("that folder isn't a tracked project")
                path = os.path.expanduser(match.get("path", ""))
                if not os.path.isdir(path):
                    raise ValueError("that project folder doesn't exist")
                convo = SESS.new_convo(src, path, body.get("text") or "")
                text = (body.get("text") or "").strip()
                if text:
                    SESS.say(convo["id"], text, body.get("model", ""),
                             ai_mode(), room_notes_for_path(match.get("path", "")))
                return self._json({"ok": True, "id": convo["id"]})
            if self.path == "/api/sessions/say":
                cid = body.get("id") or ""
                data = SESS._load()
                convo = next((c for c in data["convos"] if c["id"] == cid), None)
                if not convo:
                    raise ValueError("no such conversation")
                notes = ""
                if not convo.get("sid"):
                    cfg2 = load_json(os.path.join(BRAIN, "config.json"), {})
                    match = next((s for s in (cfg2.get("sources") or [])
                                  if s.get("name") == convo["src"]), None)
                    if match:
                        notes = room_notes_for_path(match.get("path", ""))
                text = body.get("text") or ""
                # Attachments land in brain/files/ (the queue's own store) and
                # travel as absolute paths — the session's Read tool takes it
                # from there. Screenshots pasted into the box arrive this way.
                if body.get("files"):
                    saved = save_files(body["files"])
                    text += "\n\n" + "\n".join(
                        "[Attached — read it with your Read tool: "
                        + os.path.join(BRAIN, p) + "]" for p in saved)
                c2, queued = SESS.say(cid, text, body.get("model", ""),
                                      ai_mode(), notes)
                return self._json({"ok": True, "queued": queued,
                                   "outbox": len(c2.get("outbox") or [])})
            if self.path == "/api/sessions/compact":
                SESS.say(body.get("id") or "", "/compact", "", ai_mode())
                return self._json({"ok": True})
            if self.path == "/api/sessions/read":
                SESS.mark_read(body.get("id") or "")
                return self._json({"ok": True})
            if self.path == "/api/sessions/unqueue":
                SESS.unqueue(body.get("id") or "", int(body.get("i", -1)))
                return self._json({"ok": True})
            if self.path == "/api/sessions/hands":
                SESS.move_hands(body.get("id") or "")
                return self._json({"ok": True})
            if self.path == "/api/sessions/mode":
                SESS.set_careful(body.get("id") or "", body.get("careful"))
                return self._json({"ok": True})
            if self.path == "/api/sessions/stop":
                return self._json({"ok": SESS.stop(body.get("id") or "")})
            if self.path == "/api/sessions/end":
                SESS.end(body.get("id") or "")
                return self._json({"ok": True})
            if self.path == "/api/sessions/reopen":
                SESS.reopen(body.get("id") or "")
                return self._json({"ok": True})
            if self.path == "/api/sessions/tobrain":
                # The one path back out of a conversation. The session running
                # in her project folder never writes here; this does, from the
                # brain's own process, into the file she already empties her
                # head into.
                text = (body.get("text") or "").strip()
                if not text:
                    return self._json({"error": "nothing to send"}, 400)
                snap = SESS.snapshot(
                    (load_json(os.path.join(BRAIN, "config.json"), {})
                     .get("sources") or []), {})
                where, topic = "", ""
                for p in snap["projects"]:
                    for c in p["convos"] + p["history"]:
                        if c["id"] == (body.get("id") or ""):
                            where, topic = p["name"], c["topic"]
                lines = text[:1500].splitlines()
                head = (f'From the “{topic}” conversation in {where}:'
                        if topic else "From a conversation:")
                block = ("- " + head + "\n"
                         + "\n".join("  " + ln.strip() for ln in lines if ln.strip()))
                inbox = os.path.join(BRAIN, "inbox.md")
                cur = read(inbox) if os.path.isfile(inbox) else ""
                if cur and not cur.endswith("\n"):
                    cur += "\n"
                write(inbox, cur + block + "\n")
                rebuild()
                return self._json({"ok": True})
            if self.path in ("/api/sessions/star", "/api/sessions/unstar"):
                cfg3 = load_json(os.path.join(BRAIN, "config.json"), {})
                stars = list(cfg3.get("starred") or [])
                raw = (body.get("path") or "").strip()
                if not raw:
                    return self._json({"error": "which file?"}, 400)
                if self.path.endswith("unstar"):
                    stars = [s for s in stars if s != raw]
                else:
                    # A bare name is resolved against the project she is in,
                    # then the brain — the two places a file she cares about
                    # actually lives.
                    cands = ([raw] if raw.startswith(("/", "~"))
                             else [os.path.join(body.get("base") or "", raw),
                                   os.path.join(BRAIN, raw)])
                    hit = next((c for c in cands
                                if c and os.path.isfile(os.path.expanduser(c))), None)
                    if not hit:
                        return self._json({"error": "no file at that path"}, 400)
                    hit = os.path.expanduser(hit).replace(
                        os.path.expanduser("~"), "~", 1)
                    if hit in stars:
                        return self._json({"error": "already starred"}, 400)
                    stars.append(hit)
                cfg3["starred"] = stars
                save_json(os.path.join(BRAIN, "config.json"), cfg3)
                return self._json({"ok": True, "starred": stars})
            if self.path == "/api/sessions/dev":
                cfg2 = load_json(os.path.join(BRAIN, "config.json"), {})
                srcs = cfg2.get("sources") or []
                if body.get("action") == "stop":
                    return self._json({"ok": SESS.dev_stop(body.get("src") or "")})
                return self._json({"ok": True,
                                   "state": SESS.dev_start(body.get("src") or "", srcs)})
            return self._json({"error": "no such endpoint"}, 404)
        except (ValueError, RuntimeError) as exc:
            return self._json({"error": str(exc)}, 400)
        except Exception as exc:                  # noqa: BLE001 - never 500 silently
            return self._json({"error": f"{type(exc).__name__}: {exc}"}, 500)


def _snapshot():
    """Commit whatever is uncommitted when the server starts. The page edits
    files all day; this guarantees a restore point exists before it does."""
    try:
        if subprocess.run(["git", "-C", ROOT, "status", "--porcelain"],
                          capture_output=True, text=True, timeout=10).stdout.strip():
            subprocess.run(["git", "-C", ROOT, "add", "-A"],
                           capture_output=True, timeout=10)
            subprocess.run(["git", "-C", ROOT, "commit", "-m", "page session snapshot"],
                           capture_output=True, timeout=10)
    except Exception:
        pass                                    # no git is fine; no crash is mandatory


def main():
    _snapshot()
    # Sync the folders once on startup, so the page you open is already fresh,
    # then keep syncing in the background on the config's cadence.
    try:
        import sync
        sync.sync()
        _sync["last"] = datetime.now()
    except Exception:
        pass
    rebuild()
    threading.Thread(target=_autosync_loop, daemon=True).start()
    # The brain as a contact: idles until brain/.telegram.json has a token
    # (see telegram_bridge.py for the two-minute setup). Capture, read-back
    # and voice notes — spend beyond the local transcriber stays a button on
    # the page, and a voice note queues its ask rather than running it.
    import telegram_bridge
    threading.Thread(
        target=telegram_bridge.run,
        args=(capture, _rebuild_soon, telegram_voice,
              lambda t, mode="dump", files=None: (
                  journal_keep(t, "telegram")
                  if mode == "journal"
                  else queue_request(t, mode, files=files)),
              telegram_ask,
              lambda key: tick("today.md", key, True),
              draft_revise),
        daemon=True).start()
    binds, note = resolve_binds(BIND)
    # Whatever we actually listen on is, by definition, a name the owner uses
    # to reach her own page — so it's allowed. The tailnet IP lands here, which
    # is what keeps phone access working through the guard.
    ALLOWED_HOSTS.update(_host_only(a) for a in binds)
    servers = []
    for addr in binds:
        try:
            servers.append(ThreadingHTTPServer((addr, PORT), Handler))
        except OSError as exc:
            print(f"\n  Could not listen on {addr}:{PORT} — {exc}")
    if not servers:
        sys.exit(f"Nothing could listen on port {PORT}. Is the brain already running?")
    srv = servers[0]
    for extra in servers[1:]:
        threading.Thread(target=extra.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{PORT}/"
    # From the sockets that actually bound, not the ones that were asked for:
    # a tailnet address that failed to bind was still being advertised as the
    # phone URL, right under the error saying it hadn't worked.
    phone = [s.server_address[0] for s in servers
             if s.server_address[0] not in ("127.0.0.1", "localhost")]
    items = M.load()
    b = M.briefing(items)
    print(f"\n  Your brain is at  {url}")
    if phone:
        print(f"  On your phone:    http://{phone[0]}:{PORT}/")
    if note:
        print(f"  Note: {note}")
    print(f"\n  {len(b['live'])} live workstreams · {len(b['overdue'])} overdue · "
          f"{len(b['chase'])} need a chase · {len(b['cold'])} going cold")
    print("\n  Leave this window open. Ctrl-C when you're done.\n")
    threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("  Closed.\n")


if __name__ == "__main__":
    main()

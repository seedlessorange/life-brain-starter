#!/usr/bin/env python3
"""What the brain did: one log, the bell that reads it, and the notices.

    python3 brain/tools/activity.py                     # print the last 30
    python3 brain/tools/activity.py start "What" --by morning     # -> id
    python3 brain/tools/activity.py finish ID [--failed] [--result "…"]

Her ask (7 Oct 2026): "I clicked Catch me up, there was a popup to allow it
to run, then nothing happened." The run had worked; nothing said so where she
was looking. Most of the brain's work was like that: folder syncs, the mail
check, the job scan, transcripts, the 7am plan and the night shift each
answered with a silent page reload or nothing at all, and only runs started
from the page left a trace (the last eight, under the hood).

So everything that starts work writes here: a line when it starts, a line
when it ends, with who started it (`by`), one plain sentence of what came of
it (`result`), the files a run changed (read from the run's own Edit and
Write steps, never from what the model says it did) and a link to where the
result lives. The bell on every page reads this file; a notice pops up when
something starts or ends while a page is open.

The file is append-only JSON lines: an entry is folded from every line with
its id, so a start and its finish never race over one record, and a shell
script can append too. It is a dot-file on purpose: the page's 20-second
version check skips those, so a log line never reloads a page.
"""

import json
import os
import re
import sys
import threading
import uuid
from datetime import datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
BRAIN = os.path.dirname(HERE)
ROOT = os.path.dirname(BRAIN)
LOG = os.path.join(BRAIN, ".activity.jsonl")
SEEN = os.path.join(BRAIN, ".activity-seen.json")
KEEP_LINES = 3000           # trimmed back to this when the file passes MAX_BYTES
MAX_BYTES = 1_500_000
STALE = timedelta(hours=4)  # "working" longer than this: the server lost track

# Who started it, as the panel says it: whole phrases, because "by" in
# front of each read "by on its own" (8 Oct).
BY = {"you": "you started it", "auto": "ran on its own",
      "morning": "the 7am plan started it", "night": "the night shift started it",
      "telegram": "from Telegram", "voice": "from your voice",
      "answer": "after your answer"}

# Where a link may point: the brain's own pages, nothing else. A link is
# data the page renders as an href, so it is checked here, once.
_HREF = re.compile(r"^(?:index|map|rooms|sessions|usage|cook|routines)\.html"
                   r"(?:#[\w/.:%-]*)?$")

_lock = threading.Lock()


def _now():
    return datetime.now().isoformat(timespec="seconds")


def _append(rec):
    line = json.dumps(rec, ensure_ascii=False) + "\n"
    with _lock:
        try:
            with open(LOG, "a", encoding="utf-8") as f:
                f.write(line)
            if os.path.getsize(LOG) > MAX_BYTES:
                with open(LOG, encoding="utf-8") as f:
                    tail = f.readlines()[-KEEP_LINES:]
                tmp = LOG + ".tmp"
                with open(tmp, "w", encoding="utf-8") as f:
                    f.writelines(tail)
                os.replace(tmp, LOG)
        except OSError:
            pass            # a log that can't be written never breaks the work


def _link(link):
    """{href, label} to a page of the brain, or {file, label} to a file in
    the box's Files (docs.py id). Anything else is dropped."""
    if not link:
        return None
    label = str(link.get("label") or "Open")[:40]
    if link.get("file") and re.fullmatch(r"[0-9a-f]{16}", link["file"]):
        return {"file": link["file"], "label": label}
    if link.get("path"):
        fid = file_id(link["path"])
        return {"file": fid, "label": label} if fid else None
    href = str(link.get("href") or "")
    return {"href": href, "label": label} if _HREF.match(href) else None


def file_id(path):
    """The box's id for a file it lists (docs.py), or "" when the box does
    not list it: the page never gets a path."""
    try:
        import docs
        rp = os.path.realpath(path if os.path.isabs(path)
                              else os.path.join(ROOT, path))
        e = docs.find(docs._id(rp))
        return e["id"] if e else ""
    except Exception:                                   # noqa: BLE001
        return ""


def start(what, by="you", kind="", link=None, result=""):
    """A line for work that has begun. Returns its id, for finish()."""
    aid = datetime.now().strftime("%Y%m%d%H%M%S") + uuid.uuid4().hex[:4]
    rec = {"id": aid, "at": _now(), "what": str(what)[:120],
           "by": by if by in BY else "you", "kind": kind, "state": "working"}
    if result:
        rec["result"] = str(result)[:240]
    lk = _link(link)
    if lk:
        rec["link"] = lk
    _append(rec)
    if kind == "run":
        # Every Claude run starts here (the page, the 7am plan, the night
        # shift), so this is where the plan meter is read for the "before"
        # half of what the run moved (usage.record pairs it).
        try:
            import plan_usage
            plan_usage.note_start()
        except Exception:                               # noqa: BLE001
            pass
    return aid


def finish(aid, ok=True, result="", link=None, files=None, detail="",
           what="", run=""):
    """The same entry, ended. `files` are paths the work changed; `detail`
    is longer text (a run's report); `run` is the run's start stamp, which
    finds its steps in the run history."""
    if not aid:
        return
    rec = {"id": aid, "end": _now(), "state": "done" if ok else "failed"}
    if what:
        rec["what"] = str(what)[:120]
    if result:
        rec["result"] = str(result)[:240]
    if detail:
        rec["detail"] = str(detail)[:2400]
    if run:
        rec["run"] = run
    lk = _link(link)
    if lk:
        rec["link"] = lk
    if files:
        rec["files"] = _files(files)
    _append(rec)


def note(what, ok=True, by="you", kind="", result="", link=None, files=None,
         detail=""):
    """Something done in one go: started and finished on one line."""
    aid = start(what, by=by, kind=kind)
    finish(aid, ok=ok, result=result, link=link, files=files, detail=detail)
    return aid


class doing:
    """with activity.doing("Checked your mail", kind="mail") as a:
           r = check()
           a.result = "2 people are waiting on a reply"
    Logs the start, then the end; an exception ends it as failed with the
    error said plainly, and goes on being raised."""

    def __init__(self, what, by="you", kind="", link=None):
        self.what, self.by, self.kind, self.link = what, by, kind, link
        self.result, self.files, self.detail, self.done_what = "", None, "", ""
        self.id = ""

    def __enter__(self):
        self.id = start(self.what, by=self.by, kind=self.kind)
        return self

    def __exit__(self, et, ev, tb):
        if et is None:
            finish(self.id, ok=True, result=self.result, link=self.link,
                   files=self.files, detail=self.detail, what=self.done_what)
        else:
            finish(self.id, ok=False, result=str(ev)[:240] or et.__name__,
                   link=self.link)
        return False


# ---- the files a run changed, from its own steps -----------------------

_STEP = re.compile(r"·\s+(?:Edit|Write|MultiEdit|NotebookEdit)\s+(\S+)")


def files_from_steps(lines):
    """Paths a run wrote, read from its feed lines ("  · Edit /…/x.md"),
    first mention first, each once."""
    out = []
    for ln in lines or []:
        m = _STEP.search(ln or "")
        if m and m.group(1) not in out:
            out.append(m.group(1))
    return out


def _private(rp):
    return rp.startswith(os.path.join(os.path.realpath(BRAIN), "journal") + os.sep)


def visible(paths):
    """The paths the panel may name: never the journal, even as a name."""
    out = []
    for p in paths or []:
        p = str(p)
        if not _private(os.path.realpath(p if os.path.isabs(p)
                                         else os.path.join(ROOT, p))):
            out.append(p)
    return out


def _files(paths):
    """[{name, file?}]: a name to show, and the box's id when it lists it."""
    try:
        import docs
        listed = {e["id"] for e in docs.index()}
    except Exception:                                   # noqa: BLE001
        docs, listed = None, set()
    out = []
    for p in visible(paths)[:40]:
        p = str(p)
        rp = os.path.realpath(p if os.path.isabs(p) else os.path.join(ROOT, p))
        try:
            rel = os.path.relpath(rp, BRAIN)
            name = rel if not rel.startswith("..") else os.path.basename(rp)
        except ValueError:
            name = os.path.basename(rp)
        e = {"name": name}
        fid = docs._id(rp) if docs else ""
        if fid in listed:
            e["file"] = fid
        out.append(e)
    return out


# ---- what a job changed, said plainly ------------------------------------
# The folder sync logged "Something changed in your folders" every twenty
# minutes and opened onto nothing (8 Oct): changed what, where? A job
# snapshots the brain's own files before it starts and says, after, which
# people, which projects' to-dos and which files moved.

FIELD_WORDS = {"last": "last spoke", "ball": "whose reply", "since": "since",
               "where": "place", "circle": "circle", "role": "role",
               "company": "company", "also": "other names",
               "how": "how you know them", "why": "why they matter"}
FILE_WORDS = {"workstreams.md": "projects", "people.md": "people",
              "inbox.md": "inbox", "next.md": "next up", "goals.md": "finish lines",
              "decisions.md": "decisions", "ideas.md": "ideas", "habits.md": "habits",
              "season.md": "season", "config.json": "settings",
              "synced.md": "project folders"}


def snapshot():
    """Her brain files' text (not the generated pages, not the journal)."""
    out = {}
    names = [f for f in os.listdir(BRAIN)
             if f.endswith(".md") and not f.startswith(".")] + ["config.json"]
    rdir = os.path.join(BRAIN, "rooms")
    if os.path.isdir(rdir):
        names += ["rooms/" + f for f in os.listdir(rdir) if f.endswith(".md")]
    for rel in names:
        try:
            with open(os.path.join(BRAIN, rel), encoding="utf-8") as f:
                out[rel] = f.read()
        except OSError:
            pass
    return out


def _moved(a, b):
    """Lines only in a, lines only in b, each with the heading above it."""
    import difflib
    al, bl = (a or "").split("\n"), (b or "").split("\n")

    def heads(lines):
        h, out = "", []
        for ln in lines:
            m = re.match(r"^#{2,3}\s+(.*)", ln)
            if m:
                h = m.group(1).strip()
            out.append(h)
        return out

    ha, hb = heads(al), heads(bl)
    gone, new = [], []
    sm = difflib.SequenceMatcher(None, al, bl, autojunk=False)
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op in ("replace", "delete"):
            gone += [(ha[i], al[i]) for i in range(i1, i2) if al[i].strip()]
        if op in ("replace", "insert"):
            new += [(hb[j], bl[j]) for j in range(j1, j2) if bl[j].strip()]
    return gone, new


def _names(xs, n=3):
    xs = list(dict.fromkeys(x for x in xs if x))
    return ", ".join(xs[:n]) + (f" and {len(xs) - n} more" if len(xs) > n else "")


def changes(before, after, only=None):
    """(one sentence, a few lines of detail, the files) for what moved
    between two snapshots. `only` limits it to the files the job itself
    writes, so another session's edit during the job is not credited to it."""
    parts, detail, files = [], [], []
    for rel in sorted(set(before) | set(after)):
        if only is not None and rel not in only:
            continue
        a, b = before.get(rel), after.get(rel)
        if a == b:
            continue
        files.append(os.path.join(BRAIN, rel))
        gone, new = _moved(a, b)
        if rel == "people.md":
            fields = {}
            for who, ln in new + gone:
                m = re.match(r"^- \*\*([^*:]+):\*\*", ln.strip())
                if who:
                    fields.setdefault(who, set())
                    if m:
                        fields[who].add(FIELD_WORDS.get(m.group(1).strip().lower(),
                                                        m.group(1).strip().lower()))
            if fields:
                parts.append("people: " + _names(fields))
                detail += ["People:"] + [
                    f"  {who}" + (": " + ", ".join(sorted(fs)) if fs else "")
                    for who, fs in list(fields.items())[:15]]
            continue
        if rel == "synced.md":
            todo = re.compile(r"^- \[[ xX]\]\s+")
            added = [(h, todo.sub("", ln)) for h, ln in new
                     if todo.match(ln) and (h, ln) not in gone]
            closed = [(h, todo.sub("", ln)) for h, ln in gone
                      if todo.match(ln) and not any(x == ln for _, x in new)]
            worked = [ln.split("|")[1].strip() for _, ln in new
                      if ln.startswith("|") and "---" not in ln
                      and "Project" not in ln]
            bits = []
            if added:
                bits.append(f"{len(added)} new to-do{'s' if len(added) > 1 else ''}"
                            f" in {_names([h for h, _ in added], 2)}")
            if closed:
                bits.append(f"{len(closed)} gone from {_names([h for h, _ in closed], 2)}")
            if worked and not bits:
                bits.append("work seen in " + _names(worked, 2))
            if bits:
                parts.append("project folders: " + "; ".join(bits))
            if added:
                detail += ["New in your project folders:"] + [
                    f"  {h}: {t}" for h, t in added[:10]]
            if closed:
                detail += ["No longer listed:"] + [f"  {h}: {t}" for h, t in closed[:8]]
            if worked:
                detail += ["Worked on lately: " + _names(worked, 6)]
            continue
        word = FILE_WORDS.get(rel, rel[:-3] if rel.endswith(".md") else rel)
        parts.append(word)
        n = len(new) + len(gone)
        detail.append(f"{word.capitalize()}: {n} line{'s' if n != 1 else ''} changed")
    sentence = "; ".join(parts)
    return (sentence[:1].upper() + sentence[1:]) if sentence else "", \
        "\n".join(detail), files


# ---- reading it back ----------------------------------------------------

def entries(limit=80):
    """Folded entries, newest first."""
    try:
        with open(LOG, encoding="utf-8") as f:
            lines = f.readlines()[-KEEP_LINES:]
    except OSError:
        return []
    by_id, order = {}, []
    for ln in lines:
        try:
            r = json.loads(ln)
        except ValueError:
            continue
        aid = r.get("id")
        if not aid:
            continue
        if aid not in by_id:
            by_id[aid] = {}
            order.append(aid)
        by_id[aid].update(r)
    now = datetime.now()
    out = []
    for aid in reversed(order):
        e = by_id[aid]
        if "at" not in e:
            continue        # a finish whose start was trimmed away
        if (e.get("kind") == "sync" and e.get("by") == "auto"
                and str(e.get("result", "")).startswith("Something changed")):
            continue        # the old sync line, which named nothing (8 Oct)
        if e.get("state") == "working":
            try:
                if now - datetime.fromisoformat(e["at"]) > STALE:
                    e["state"] = "lost"
            except ValueError:
                pass
        e["who"] = BY.get(e.get("by"), BY["you"])
        out.append(e)
        if len(out) >= limit:
            break
    return out


def seen_at():
    try:
        with open(SEEN, encoding="utf-8") as f:
            return json.load(f).get("at", "")
    except (OSError, ValueError):
        return ""


def mark_seen():
    tmp = SEEN + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"at": _now()}, f)
    os.replace(tmp, SEEN)


def payload(limit=80):
    """What the bell needs: the entries, how many ended since she last
    looked, how many are working now."""
    items = entries(limit)
    seen = seen_at()
    unseen = sum(1 for e in items if e.get("state") in ("done", "failed")
                 and (e.get("end") or e["at"]) > seen)
    return {"items": items, "unseen": unseen, "now": _now(), "seen": seen,
            "working": sum(1 for e in items if e.get("state") == "working")}


# ---- the page: the bell, the panel, the notices ----------------------------

def button_html():
    return ('<button class="didbell needs-server" id="didbell" type="button"'
            ' aria-haspopup="dialog" aria-expanded="false"'
            ' title="What the brain did" aria-label="What the brain did">'
            '<svg viewBox="0 0 24 24" width="17" height="17" fill="none"'
            ' stroke="currentColor" stroke-width="1.9" stroke-linecap="round"'
            ' stroke-linejoin="round" aria-hidden="true">'
            '<path d="M6 8a6 6 0 1 1 12 0c0 7 3 9 3 9H3s3-2 3-9"/>'
            '<path d="M10.3 21a1.9 1.9 0 0 0 3.4 0"/></svg>'
            '<b class="didcount" hidden></b></button>')


CSS = r"""
.didbell{position:relative;display:inline-flex;align-items:center;justify-content:center;
  width:32px;height:32px;flex:none;border-radius:999px;color:var(--dim);cursor:pointer;
  background:none;border:1px solid transparent;padding:0}
.didbell:hover,.didbell[aria-expanded="true"]{color:var(--ink);background:var(--surface)}
.didbell.busy::after{content:"";position:absolute;inset:-1px;border-radius:999px;
  border:1.5px solid transparent;border-top-color:var(--green);animation:didspin 1.1s linear infinite}
.didcount{position:absolute;top:-3px;right:-4px;min-width:16px;height:16px;padding:0 4px;
  border-radius:999px;background:var(--green);color:var(--paper);
  font:700 10px/16px var(--sans,system-ui);text-align:center}
.didcount[hidden]{display:none}
@keyframes didspin{to{transform:rotate(360deg)}}

.didpanel{position:fixed;z-index:97;top:58px;right:12px;width:min(400px,calc(100vw - 24px));
  max-height:min(72vh,640px);display:flex;flex-direction:column;
  background:var(--paper);color:var(--ink);border:1px solid var(--line2);
  border-radius:var(--r-card,10px);box-shadow:var(--shadow-lift,0 18px 44px -22px rgba(0,0,0,.5));
  font:400 14px/1.45 var(--sans,system-ui)}
.didpanel[hidden]{display:none}
.didhead{display:flex;align-items:baseline;justify-content:space-between;gap:8px;
  padding:12px 14px 8px;border-bottom:1px solid var(--line)}
.didhead h2{margin:0;font:600 14px/1.3 var(--sans,system-ui)}
.didhead a{font-size:12.5px;color:var(--dim);text-decoration:none}
.didhead a:hover{color:var(--green)}
.didlist{overflow:auto;padding:4px 0 8px;overscroll-behavior:contain}
.didday{margin:10px 14px 2px;font:600 11px/1.3 var(--sans,system-ui);letter-spacing:.08em;
  text-transform:uppercase;color:var(--faint)}
.didrow{display:grid;grid-template-columns:18px 1fr auto;gap:2px 8px;align-items:start;
  width:100%;padding:7px 14px;text-align:left;background:none;border:0;color:inherit;
  font:inherit;cursor:pointer}
.didrow:not(.flat):hover{background:var(--surface)}
.didrow.focus{background:color-mix(in oklab,var(--green) 10%,var(--surface))}
.didicon{grid-row:span 2;width:16px;height:16px;margin-top:2px;border-radius:999px;
  display:inline-flex;align-items:center;justify-content:center;font-size:10px;font-weight:700}
.didicon.done{color:var(--ok,var(--green));border:1.5px solid currentColor}
.didicon.failed,.didicon.lost{color:var(--bad,#c0392b);border:1.5px solid currentColor}
.didicon.working{border:1.5px solid var(--line2);border-top-color:var(--green);
  animation:didspin 1.1s linear infinite}
.didwhat{font-weight:500}
.didtime{font-size:12px;color:var(--faint);white-space:nowrap}
.didsub{grid-column:2/4;font-size:12.5px;color:var(--dim)}
.didrow.unseen .didwhat::before{content:"";display:inline-block;width:6px;height:6px;
  margin:0 6px 2px 0;border-radius:999px;background:var(--green)}
.didmore{padding:2px 14px 10px 40px;font-size:13px}
.didmore[hidden]{display:none}
.didmore .diddetail{margin:4px 0;white-space:pre-wrap;color:var(--ink);
  max-height:260px;overflow:auto}
.didrow.flat{cursor:default}
.didmore .didfiles{margin:6px 0 0;padding:0;list-style:none;font-size:12.5px;color:var(--dim)}
.didmore .didfiles li{margin:2px 0}
.didmore .didfiles button,.didgo{font:inherit;color:var(--green);background:none;border:0;
  padding:0;cursor:pointer;text-decoration:none}
.didmore .didfiles button:hover,.didgo:hover{text-decoration:underline}
.didgo{display:inline-block;margin-top:6px;font-weight:600}
.didsteps{margin-top:6px}
.didsteps summary{cursor:pointer;color:var(--dim);font-size:12.5px}
.didsteps pre{max-height:220px;overflow:auto;margin:6px 0 0;padding:8px;
  background:var(--surface);border-radius:var(--r-btn,6px);
  font:400 11.5px/1.5 var(--mono,ui-monospace,monospace);white-space:pre-wrap}
.didempty{padding:18px 14px;color:var(--dim)}

.didtoasts{position:fixed;z-index:98;top:62px;right:12px;display:flex;flex-direction:column;
  gap:8px;width:min(340px,calc(100vw - 24px));pointer-events:none}
.didtoast{pointer-events:auto;display:grid;grid-template-columns:18px 1fr auto;gap:2px 8px;
  align-items:start;padding:10px 12px;background:var(--paper);color:var(--ink);
  border:1px solid var(--line2);border-radius:var(--r-card,10px);
  box-shadow:var(--shadow-lift,0 18px 44px -22px rgba(0,0,0,.5));
  font:400 13.5px/1.4 var(--sans,system-ui);cursor:pointer;
  animation:didin .18s ease-out}
.didtoast .didicon{grid-row:span 2}
.didtoast .didsub{grid-column:2/3}
.didtoast .didgo{margin:0;grid-row:span 2;align-self:center;white-space:nowrap}
.didtoast .didx{grid-column:3;grid-row:1;justify-self:end;display:none}
@keyframes didin{from{opacity:0;transform:translateY(-6px)}}
@media (prefers-reduced-motion:reduce){
  .didbell.busy::after,.didicon.working{animation:none}
  .didtoast{animation:none}
}
@media (max-width:760px){
  .didpanel{top:auto;bottom:calc(64px + env(safe-area-inset-bottom));left:8px;right:8px;
    width:auto;max-height:70vh}
  .didtoasts{top:auto;bottom:calc(72px + env(safe-area-inset-bottom));left:12px;right:12px;
    width:auto}
}
"""

HTML = """
<div class="didpanel" id="didpanel" role="dialog" aria-label="What the brain did" hidden>
  <div class="didhead"><h2>What the brain did</h2>
    <a href="index.html#/hood" data-nav="hood">Jobs and runs</a></div>
  <div class="didlist" id="didlist"><p class="didempty">Nothing yet.</p></div>
</div>
<div class="didtoasts" id="didtoasts" aria-live="polite"></div>
"""

JS = r"""
(function(){
var bell = document.getElementById('didbell'), panel = document.getElementById('didpanel');
var list = document.getElementById('didlist'), toasts = document.getElementById('didtoasts');
if(!bell || !panel) return;
var cnt = bell.querySelector('.didcount');
var known = null;            // id -> state, from the last poll (null: none yet)
var items = [], seenAt = '', fastUntil = 0, timer = null, openId = '';
var shown = {};
try { shown = JSON.parse(sessionStorage.getItem('act-shown') || '{}'); } catch(e){}
var LOADED = Date.now();

function esc(s){ return String(s == null ? '' : s).replace(/[&<>"]/g, function(c){
  return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]; }); }
function hm(iso){ return iso ? iso.slice(11, 16) : ''; }
function dayOf(iso){
  var d = new Date(iso.slice(0, 10) + 'T12:00:00'), t = new Date();
  var k = function(x){ return x.toISOString().slice(0, 10); };
  t.setHours(12, 0, 0, 0);
  if(k(d) === k(t)) return 'Today';
  t.setDate(t.getDate() - 1);
  if(k(d) === k(t)) return 'Yesterday';
  return d.toLocaleDateString(undefined, {weekday: 'short', day: 'numeric', month: 'short'});
}
function mins(a, b){
  var s = Math.max(0, Math.round((new Date(b) - new Date(a)) / 1000));
  return s < 60 ? s + 's' : Math.round(s / 60) + ' min';
}
function verb(e){
  if(e.state === 'working') return 'started ' + hm(e.at);
  if(e.state === 'lost') return 'lost track';
  return (e.state === 'failed' ? 'failed ' : '') + hm(e.end || e.at);
}
function sub(e){
  var bits = [];
  if(e.result) bits.push(e.result);
  else if(e.state === 'working') bits.push('Working since ' + hm(e.at));
  else if(e.state === 'lost') bits.push('The brain lost track of this one: it may have stopped when the server restarted');
  bits.push(e.who);
  if(e.end && e.state !== 'working' && new Date(e.end) - new Date(e.at) >= 1000) bits.push(mins(e.at, e.end));
  return bits.join(' · ');
}
function goHtml(lk){
  if(!lk) return '';
  if(lk.file) return '<button class="didgo" type="button" data-didfile="' + esc(lk.file) + '">' + esc(lk.label) + ' →</button>';
  return '<a class="didgo" href="' + esc(lk.href) + '">' + esc(lk.label) + ' →</a>';
}
function icon(e){
  var st = e.state || 'done';
  return '<i class="didicon ' + st + '" aria-hidden="true">'
    + (st === 'done' ? '✓' : (st === 'failed' || st === 'lost') ? '!' : '') + '</i>';
}
function more(e){
  var h = '';
  if(e.detail) h += '<div class="diddetail">' + esc(e.detail)
    .replace(/\*\*([^*\n]+)\*\*/g, '<b>$1</b>').replace(/^#{1,4}\s+/gm, '') + '</div>';
  if(e.files && e.files.length){
    h += '<ul class="didfiles"><li>Changed:</li>' + e.files.map(function(f){
      return '<li>' + (f.file ? '<button type="button" data-didfile="' + esc(f.file) + '">'
        + esc(f.name) + '</button>' : esc(f.name)) + '</li>'; }).join('') + '</ul>';
  }
  if(e.run) h += '<details class="didsteps" data-didrun="' + esc(e.run) + '"><summary>Every step it took</summary><pre>…</pre></details>';
  return h + goHtml(e.link);
}
function draw(){
  if(!items.length){ list.innerHTML = '<p class="didempty">Nothing yet. Anything the brain starts shows up here.</p>'; return; }
  var h = '', last = '';
  items.forEach(function(e){
    var d = dayOf(e.at);
    if(d !== last){ h += '<h3 class="didday">' + esc(d) + '</h3>'; last = d; }
    var unseen = (e.state === 'done' || e.state === 'failed') && (e.end || e.at) > seenAt;
    var m = more(e);
    h += '<button class="didrow' + (unseen ? ' unseen' : '') + (e.id === openId ? ' focus' : '')
      + (m ? '' : ' flat') + '" type="button" data-didid="' + esc(e.id) + '"'
      + (m ? ' aria-expanded="' + (e.id === openId) + '"' : '') + '>'
      + icon(e) + '<span class="didwhat">' + esc(e.what) + '</span>'
      + '<span class="didtime">' + esc(verb(e)) + '</span>'
      + '<span class="didsub">' + esc(sub(e)) + '</span></button>'
      + (m ? '<div class="didmore"' + (e.id === openId ? '' : ' hidden') + '>' + m + '</div>' : '');
  });
  list.innerHTML = h;
}
function setBell(j){
  bell.classList.toggle('busy', !!j.working);
  var n = j.unseen || 0;
  cnt.hidden = !n; cnt.textContent = n > 9 ? '9+' : String(n);
  bell.title = j.working ? (j.working === 1 ? 'One thing working now' : j.working + ' things working now')
    : (n ? n + ' finished since you last looked' : 'What the brain did');
}

function toast(e){
  var key = e.id + ':' + e.state;
  if(shown[key]) return;
  shown[key] = 1;
  try { sessionStorage.setItem('act-shown', JSON.stringify(shown)); } catch(err){}
  // One notice per job: the end replaces its "started".
  toasts.querySelectorAll('[data-didtoast="' + e.id + '"]').forEach(function(o){ o.remove(); });
  var t = document.createElement('div');
  t.className = 'didtoast';
  t.setAttribute('data-didtoast', e.id);
  t.setAttribute('role', 'status');
  var title = e.state === 'working' ? e.what : e.what + (e.state === 'failed' ? ': it failed' : '');
  t.innerHTML = icon(e) + '<span class="didwhat">' + esc(title) + '</span>'
    + (e.state === 'working' ? '' : goHtml(e.link))
    + '<span class="didsub">' + esc(e.state === 'working' ? 'Started · the bell has it when it ends' : (e.result || 'Done')) + '</span>';
  t.addEventListener('click', function(ev){
    if(ev.target.closest('.didgo')) { t.remove(); return; }
    t.remove(); openPanel(e.id);
  });
  toasts.appendChild(t);
  while(toasts.children.length > 3) toasts.firstChild.remove();
  setTimeout(function(){ t.remove(); }, e.state === 'failed' ? 15000 : (e.state === 'working' ? 5000 : 9000));
}

function poll(){
  clearTimeout(timer);
  if(document.hidden){ timer = setTimeout(poll, 15000); return; }
  fetch('/api/activity').then(function(r){ return r.json(); }).then(function(j){
    items = j.items || []; seenAt = j.seen || '';
    setBell(j);
    var now = {};
    items.forEach(function(e){
      now[e.id] = e.state;
      var fresh;
      if(known === null){
        // A page that loads just after something ended still says so:
        // a click that reloads the page must not swallow its own notice.
        fresh = e.state !== 'working' && e.end
          && (new Date(j.now) - new Date(e.end)) < 25000;
      } else {
        fresh = known[e.id] !== e.state;
      }
      if(fresh && e.state !== 'lost') toast(e);
    });
    known = now;
    if(!panel.hidden) draw();
    timer = setTimeout(poll, (j.working || Date.now() < fastUntil) ? 3000 : 15000);
  }).catch(function(){ timer = setTimeout(poll, 30000); });
}

function openPanel(id){
  openId = id || '';
  panel.hidden = false; bell.setAttribute('aria-expanded', 'true');
  draw();
  if(id){ var r = list.querySelector('[data-didid="' + id + '"]'); if(r) r.scrollIntoView({block: 'nearest'}); }
  fetch('/api/activity/seen', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: '{}'})
    .then(function(){ cnt.hidden = true; }).catch(function(){});
  loadSteps();
}
function closePanel(){
  if(panel.hidden) return;
  panel.hidden = true; bell.setAttribute('aria-expanded', 'false');
  seenAt = new Date(Date.now() - new Date().getTimezoneOffset() * 60000).toISOString().slice(0, 19);
}
function loadSteps(){
  list.querySelectorAll('.didmore:not([hidden]) details[data-didrun]:not(.got)').forEach(function(d){
    d.classList.add('got');
    d.addEventListener('toggle', function once(){
      if(!d.open) return;
      d.removeEventListener('toggle', once);
      fetch('/api/activity/steps?run=' + encodeURIComponent(d.dataset.didrun))
        .then(function(r){ return r.json(); })
        .then(function(j){ d.querySelector('pre').textContent = j.log || 'The steps of runs this old are no longer kept.'; })
        .catch(function(){ d.querySelector('pre').textContent = 'Could not reach the brain.'; });
    });
  });
}

bell.addEventListener('click', function(e){
  e.stopPropagation();
  panel.hidden ? openPanel('') : closePanel();
});
list.addEventListener('click', function(e){
  var f = e.target.closest('[data-didfile]');
  if(f){
    e.preventDefault(); closePanel();
    if(window.brainBox && window.brainBox.openFile) window.brainBox.openFile(f.dataset.didfile);
    return;
  }
  var r = e.target.closest('.didrow');
  if(!r || r.classList.contains('flat')) return;
  var m = r.nextElementSibling, on = m.hidden;
  m.hidden = !on; r.setAttribute('aria-expanded', String(on));
  if(on) loadSteps();
});
toasts.addEventListener('click', function(e){
  var f = e.target.closest('[data-didfile]');
  if(f && window.brainBox && window.brainBox.openFile){ e.preventDefault(); window.brainBox.openFile(f.dataset.didfile); }
});
document.addEventListener('click', function(e){
  if(!panel.hidden && !panel.contains(e.target) && !e.target.closest('.didtoast')) closePanel();
});
document.addEventListener('keydown', function(e){ if(e.key === 'Escape') closePanel(); });
document.addEventListener('visibilitychange', function(){ if(!document.hidden) poll(); });

// Any click that writes to the brain may have started something: look
// right away, then keep looking quickly for a minute.
var f0 = window.fetch;
window.fetch = function(u, o){
  var p = f0.apply(this, arguments);
  var url = String(u && u.url || u || '');
  if(o && /post/i.test(o.method || '') && url.indexOf('/api/') !== -1 && url.indexOf('/api/activity') === -1){
    fastUntil = Date.now() + 60000;
    // Once while it works (a long job says it started), once when it answers.
    setTimeout(poll, 700);
    p.then(function(){ setTimeout(poll, 250); }, function(){});
  }
  return p;
};
window.brainActivity = {open: openPanel, poll: poll};
setTimeout(poll, 600);
})();
"""


def block():
    return "<style>" + CSS + "</style>" + HTML + "<script>" + JS + "</script>"


# ---- for the shell scripts (the 7am plan, the night shift) ---------------

def _cli(argv):
    import argparse
    ap = argparse.ArgumentParser(prog="activity.py")
    sp = ap.add_subparsers(dest="cmd")
    s = sp.add_parser("start")
    s.add_argument("what")
    s.add_argument("--by", default="you")
    s.add_argument("--kind", default="")
    f = sp.add_parser("finish")
    f.add_argument("id")
    f.add_argument("--failed", action="store_true")
    f.add_argument("--result", default="")
    f.add_argument("--detail-file", default="")
    f.add_argument("--result-json", default="",
                   help="a `claude -p --output-format json` result: its report")
    f.add_argument("--href", default="")
    f.add_argument("--label", default="Open")
    a = ap.parse_args(argv)
    if a.cmd == "start":
        print(start(a.what, by=a.by, kind=a.kind))
    elif a.cmd == "finish":
        detail = ""
        if a.detail_file and os.path.exists(a.detail_file):
            with open(a.detail_file, encoding="utf-8", errors="replace") as fh:
                detail = fh.read()[-2400:]
        if a.result_json and os.path.exists(a.result_json):
            try:
                with open(a.result_json, encoding="utf-8") as fh:
                    rj = json.load(fh)
                detail = str(rj.get("result") or "").strip()[:2400] or detail
                if rj.get("is_error"):
                    a.failed = True
            except (OSError, ValueError, AttributeError):
                pass
        finish(a.id, ok=not a.failed, result=a.result, detail=detail,
               link={"href": a.href, "label": a.label} if a.href else None)
    else:
        for e in entries(30):
            print(f'{e["at"][5:16]}  {e.get("state", ""):8} {e["what"]}'
                  + (f'  ({e["result"]})' if e.get("result") else ""))


if __name__ == "__main__":
    _cli(sys.argv[1:])

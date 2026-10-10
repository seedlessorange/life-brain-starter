#!/usr/bin/env python3
"""Keep the shared assignment tracker honest against what the brain knows.

    python3 brain/tools/tracker.py                 # the two-way diff
    python3 brain/tools/tracker.py --rows          # paste-ready rows for the gaps
    python3 brain/tools/tracker.py --pull          # sheet rows the brain lacks -> tray
    python3 brain/tools/tracker.py --connect URL   # remember which sheet

The tracker is a Google Sheet she shares with her specialization classmates,
so it has two jobs at once: her own memory, and something other people plan
around. That second job is why this tool **never writes to it**. A row that
appears in six people's planner because a script decided it should is the
kind of thing that is only wrong once. It reads, it compares, and it hands
back rows to paste.

What it compares against: the dated tasks under her school workstreams —
which is where `school.py` deposits what it finds in the slides, and where
the syllabi were filed. So the chain runs: a deck lands in the class folder →
the date is read out of it → she accepts it → it shows up here as a row the
shared sheet is missing.

The sheet must be link-readable ("Anyone with the link can view"), which it
already is by virtue of being shared with the class. Nothing is sent to it.
"""

import argparse
import csv
import difflib
import io
import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import date, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
BRAIN = os.path.dirname(HERE)
sys.path.insert(0, HERE)

TIMEOUT = 25
UA = "life-brain/1.0 (personal planner; reads one sheet the owner shared)"

# Her courses, and every way a sheet row or a task line might name one, live
# in config (school.tracker.courses: [{"name", "aliases"}]) rather than here,
# so the shared starter carries no one's timetable. The first spelling is
# what gets written into a paste row, so it matches the sheet's dropdown. A
# teacher who takes two courses is not evidence of either: leave their name
# out of both, and the workstream a task sits in decides.
def courses():
    out = []
    for c in (((_config().get("school") or {}).get("tracker") or {})
              .get("courses") or []):
        if isinstance(c, dict) and c.get("name"):
            out.append((str(c["name"]), [str(a).lower() for a in c.get("aliases") or []]))
    return out


def _config():
    try:
        with open(os.path.join(BRAIN, "config.json"), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def sheet_url():
    return (((_config().get("school") or {}).get("tracker") or {})
            .get("url") or "")


def set_url(url):
    p = os.path.join(BRAIN, "config.json")
    c = _config()
    c.setdefault("school", {}).setdefault("tracker", {})["url"] = url.strip()
    with open(p, "w", encoding="utf-8") as f:
        json.dump(c, f, indent=2, ensure_ascii=False)
        f.write("\n")
    return url.strip()


# --------------------------------------------------------------------------
# reading the sheet

def _sheet_id(url):
    m = re.search(r"/spreadsheets/d/([A-Za-z0-9_-]+)", url or "")
    return m.group(1) if m else ""


def fetch(url=None):
    """The first tab, as rows of dicts. Read-only, and it stays that way.

    Note the export URL carries no `gid`: pinning gid=0 fetches "the tab whose
    id is 0", which is not the first tab unless the sheet has never been
    reordered — hers 400s on it. No gid means the first tab, which is what
    "the tracker" means to a person."""
    url = url or sheet_url()
    sid = _sheet_id(url)
    if not sid:
        raise ValueError("that doesn't look like a Google Sheets link")
    export = ("https://docs.google.com/spreadsheets/d/%s/export?format=csv"
              % sid)
    req = urllib.request.Request(export, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            raw = r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403, 404):
            raise ValueError(
                "the sheet isn't readable by link — in Google Sheets: Share → "
                "General access → Anyone with the link → Viewer")
        raise ValueError("Google said %s" % exc.code)
    except urllib.error.URLError as exc:
        raise ValueError("couldn't reach Google (%s)" % exc.reason)
    if raw.lstrip().startswith("<"):
        raise ValueError("Google returned a web page, not the sheet — check "
                         "link sharing is on")
    rdr = csv.DictReader(io.StringIO(raw))
    rows = []
    for r in rdr:
        clean = {(k or "").strip(): (v or "").strip() for k, v in r.items()}
        if any(clean.values()):
            rows.append(clean)
    return rdr.fieldnames or [], rows


def _col(fields, *names):
    """The sheet's own column name for a thing, whatever she called it."""
    for want in names:
        for f in fields or []:
            if (f or "").strip().lower() == want:
                return f
    for want in names:
        for f in fields or []:
            if want in (f or "").strip().lower():
                return f
    return ""


def _iso(s):
    """9/21/2026, 21/09/2026, 2026-09-21 → 2026-09-21."""
    s = (s or "").strip()
    if not s:
        return ""
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y", "%m/%d/%y", "%d/%m/%y",
                "%d %B %Y", "%B %d, %Y"):
        try:
            return datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            continue
    return ""


# --------------------------------------------------------------------------
# what the brain knows

def course_of(text):
    low = (text or "").lower()
    for name, aliases in courses():
        if any(a in low for a in aliases):
            return name
    return ""


# The marker that says "this one belongs in the shared tracker". A school
# workstream holds two very different kinds of line: real class deliverables,
# which every classmate also owes, and her own prep — decide which courses to
# take, work out what the technology is, line up interviews. Only the first
# kind may be proposed for a sheet other people plan around, and no heuristic
# can reliably tell them apart. So it is marked, once, when the task is filed.
CLASS_MARK = re.compile(r"\(class\)", re.I)


def brain_rows(today=None, all_tasks=False):
    """The class deliverables — the brain's side of the comparison.

    Only tasks carrying `(class)`. Everything else in these workstreams is
    hers, and a shared sheet is the wrong place for it."""
    import model
    today = today or date.today()
    out = []
    for w in model.load():
        name = w.get("name", "")
        if not name.startswith(("School", "Venture")):
            continue
        default = "Studio Course" if name.startswith("Venture") else ""
        for t in w.get("tasks", []):
            if t.get("done") or not t.get("due"):
                continue
            if not all_tasks and not CLASS_MARK.search(t["text"]):
                continue
            due = str(t["due"])[:10]
            if due < today.isoformat():
                continue
            out.append({
                # For a Venture task the workstream is the authority: a line
                # can mention another course without belonging to it.
                "course": default or course_of(t["text"]) or "",
                "assignment": _title(t["text"]),
                "due": due,
                "text": t["text"],
                "workstream": name,
            })
    return out


def _title(text):
    """A task line as an assignment name: drop the brain's coaching tail."""
    t = CLASS_MARK.sub("", text)
    t = re.split(r"\s+[—–]\s+", t)[0]
    t = re.sub(r"^(?:[A-Z][\w'’\- ]{2,28}):\s*", "", t)   # "Course: x" -> "x"
    t = re.split(r"\s*\((?:due|from|waiting|urgent)\b", t)[0]
    return " ".join(t.split())[:90].rstrip(",;")


# Words that say nothing about which assignment this is. Without dropping
# them "Final Slides" and "Draft Jury Slides" look like near-twins.
_STOP = {"the", "a", "an", "and", "or", "of", "for", "to", "in", "on", "with",
         "your", "you", "my", "it", "is", "be", "at", "as", "by", "plus",
         "into", "that", "this", "more", "than", "from", "up", "out", "own"}


def _words(s):
    s = re.sub(r"[^a-z0-9 ]", " ", (s or "").lower())
    return {w for w in s.split() if w not in _STOP and len(w) > 2}


def _acronyms(s):
    """MAHA, PCM, TAM — a shared one of these is near-proof on its own, and
    they are exactly the words two people shorten differently around
    ("Personal MAHA" / "MAHA Exercise")."""
    return {w for w in re.findall(r"\b[A-Z]{3,}\b", s or "")
            if w not in ("PDF", "AI", "THE", "AND", "FOR")}


def _same(a, b):
    """Two names for one assignment.

    Sequence ratio alone fails here, because the brain writes "Business plan,
    Word or PDF, line spacing 1.5 or more, plus the detailed Excel business
    model" where the sheet says "Business Plan (Word/PDF + Excel Business
    model)" — the same thing at four times the length, which any
    character-level measure scores as different. Shared significant words
    survive that."""
    if _acronyms(a) & _acronyms(b):
        return True
    x, y = _words(a), _words(b)
    if not x or not y:
        return False
    if difflib.SequenceMatcher(None, " ".join(sorted(x)),
                               " ".join(sorted(y))).ratio() >= 0.85:
        return True
    overlap = len(x & y)
    return overlap >= 2 and overlap / min(len(x), len(y)) >= 0.6


# --------------------------------------------------------------------------
# the diff

def compare(url=None, today=None):
    today = today or date.today()
    fields, rows = fetch(url)
    c_course = _col(fields, "course", "class")
    c_task = _col(fields, "assignment", "task", "deliverable")
    c_due = _col(fields, "due date", "due", "date")

    sheet = []
    for r in rows:
        sheet.append({"course": r.get(c_course, ""),
                      "assignment": r.get(c_task, ""),
                      "due": _iso(r.get(c_due, "")),
                      "raw": r})

    mine = brain_rows(today)

    def matched(a, b):
        if not _same(a["assignment"], b["assignment"]):
            return False
        # Same wording under two courses is two different assignments.
        if a["course"] and b["course"] and not _same(a["course"], b["course"]):
            return False
        return True

    missing = [m for m in mine
               if not any(matched(m, s) for s in sheet if s["assignment"])]
    extra = [s for s in sheet
             if s["assignment"]
             and not any(matched(m, s) for m in mine)
             and (not s["due"] or s["due"] >= today.isoformat())]
    clashes = []
    for m in mine:
        for s in sheet:
            if matched(m, s) and s["due"] and s["due"] != m["due"]:
                clashes.append({"assignment": s["assignment"],
                                "sheet": s["due"], "brain": m["due"]})
    return {"fields": fields, "sheet_rows": len(sheet), "missing": missing,
            "extra": extra, "clashes": clashes,
            "cols": {"course": c_course, "task": c_task, "due": c_due}}


# A Venture deliverable is the team's by default — but not the ones each
# member owes personally, and putting "Group" against "sign the charter" in a
# sheet five people read is a small wrong answer repeated five times.
_PERSONAL = re.compile(
    r"\b(your|personal|individual|resume|cv|sign|charter|reflection|"
    r"learning report|essay|journal|swot|maha|interview)\b", re.I)


def _kind(m):
    if _PERSONAL.search(m["text"]):
        return "Individual"
    return "Group" if m["workstream"].startswith("Venture") else "Individual"


# Rows she has said the class sheet doesn't need. Kept in config.json, not
# the browser: a dismissal made on the laptop has to hold on the phone, and it
# has to hold for the Copy rows button as much as for the list.
def gap_key(m):
    """A missing row by what it is and when it's due — stable across rebuilds
    and independent of how the task happens to be worded in the brain."""
    name = re.sub(r"[^a-z0-9]+", " ", (m.get("assignment") or "").lower())
    return "%s|%s" % (name.strip(), str(m.get("due") or "")[:10])


def dismissed():
    return set(((_config().get("school") or {}).get("tracker") or {})
               .get("dismissed") or [])


def set_dismissed(key, on=True):
    key = (key or "").strip()
    if not key:
        raise ValueError("nothing to dismiss")
    c = _config()
    tr = c.setdefault("school", {}).setdefault("tracker", {})
    cur = [k for k in (tr.get("dismissed") or []) if k != key]
    if on:
        cur.append(key)
    tr["dismissed"] = cur
    p = os.path.join(BRAIN, "config.json")
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(c, f, indent=2, ensure_ascii=False)
        f.write("\n")
    os.replace(tmp, p)
    return cur


def without_dismissed(data):
    """The comparison with her dismissed rows taken out of "missing" and kept
    aside, so they can be restored."""
    gone = dismissed()
    d = dict(data or {})
    rows = list((data or {}).get("missing") or [])
    d["missing"] = [m for m in rows if gap_key(m) not in gone]
    d["dismissed_rows"] = [m for m in rows if gap_key(m) in gone]
    return d


CACHE = os.path.join(BRAIN, ".tracker-cache.json")
CACHE_AGE = 1800          # the class sheet changes a few times a week


def compare_cached(max_age=CACHE_AGE):
    """compare(), but safe to call from a page that rebuilds constantly.

    The page rebuilds on every tick, and a fetch to Google each time is both
    slow (0.6s) and pointless for a sheet that changes a few times a week —
    and offline it would hang every rebuild on the network timeout. A failed
    fetch serves the last good answer instead of breaking the tab."""
    import time
    try:
        with open(CACHE, encoding="utf-8") as f:
            hit = json.load(f)
        if time.time() - hit.get("at", 0) < max_age:
            return hit["data"]
    except (OSError, ValueError, KeyError):
        hit = None
    try:
        data = compare()
    except Exception:                                    # noqa: BLE001
        return (hit or {}).get("data") or {"missing": [], "extra": [],
                                           "clashes": []}
    tmp = CACHE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"at": time.time(), "data": data}, f, default=str)
    os.replace(tmp, CACHE)
    return data


def paste_rows(url=None, today=None, data=None):
    """The gaps, as tab-separated lines in her sheet's own column order —
    select the first empty cell, paste, done. She pastes; nothing here does.

    `data` takes a comparison already made (the page passes the cached one),
    so the School tab can offer these rows without a fetch."""
    today = today or date.today()
    d = without_dismissed(data if data is not None else compare(url, today))
    fields = d["fields"] or ["Course", "Assignment", "Type", "Due date"]
    cols = d["cols"]
    c_days = _col(fields, "days left")
    c_type = _col(fields, "type")
    out = []
    for m in d["missing"]:
        cells = []
        for f in fields:
            if f == cols["course"]:
                cells.append(m["course"])
            elif f == cols["task"]:
                cells.append(m["assignment"])
            elif f == cols["due"]:
                y, mo, dd = m["due"].split("-")
                cells.append("%d/%d/%s" % (int(mo), int(dd), y))
            elif f == c_days:
                cells.append(str((date.fromisoformat(m["due"]) - today).days))
            elif f == c_type:
                cells.append(_kind(m))
            else:
                cells.append("")
        out.append("\t".join(cells))
    return out


def pull(url=None, today=None):
    """Rows her classmates added that the brain hasn't got — into the same
    tray the slide scan uses, so they arrive by the one road she already
    knows. Classmates' text is somebody else's writing: it becomes a
    suggestion to accept, never a task that files itself."""
    import hashlib
    import school
    today = today or date.today()
    d = compare(url, today)
    st = school._state()
    sugs = st.setdefault("suggestions", [])
    added = 0
    for s in d["extra"]:
        if not s["due"]:
            continue
        sid = hashlib.sha1(
            ("tracker" + s["assignment"] + s["due"]).encode()).hexdigest()[:10]
        if any(x.get("id") == sid for x in sugs):
            continue
        sugs.append({"id": sid, "status": "pending",
                     "course": s["course"] or "the shared tracker",
                     "task": s["assignment"][:140], "due": s["due"],
                     "exact": True, "line": "from the shared tracker",
                     "source": "assignment tracker",
                     "found": today.isoformat()})
        added += 1
    school._save(st)
    return {"added": added, "pending": len(school.pending())}


# --------------------------------------------------------------------------
# cli

def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--connect", metavar="URL")
    ap.add_argument("--rows", action="store_true")
    ap.add_argument("--pull", action="store_true")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    if a.connect:
        set_url(a.connect)
        try:
            fields, rows = fetch()
        except ValueError as exc:
            print("Saved, but: %s" % exc)
            return 1
        print("Connected. %d rows, columns: %s"
              % (len(rows), ", ".join(f for f in fields if f)))
        return 0

    if not sheet_url():
        print("No tracker yet — python3 brain/tools/tracker.py --connect <url>")
        return 1

    try:
        if a.rows:
            rows = paste_rows()
            if not rows:
                print("Nothing missing — the sheet has everything the brain "
                      "has.")
                return 0
            print("Paste these into the first empty row "
                  "(they're tab-separated, so they land one per column):\n")
            for r in rows:
                print(r)
            return 0
        if a.pull:
            r = pull()
            print("%d row%s from the tracker are now waiting in the tray."
                  % (r["added"], "" if r["added"] == 1 else "s")
                  if r["added"] else
                  "Nothing in the tracker that the brain doesn't have.")
            return 0
        d = without_dismissed(compare())
        if a.json:
            print(json.dumps(d, indent=2, default=str))
            return 0
        print("Tracker: %d rows.\n" % d["sheet_rows"])
        if d["missing"]:
            print("In your brain, missing from the shared sheet:")
            for m in d["missing"]:
                print("  %s  %-14s %s" % (m["due"], (m["course"] or "?")[:14],
                                          m["assignment"][:58]))
            print("\n  --rows gives these ready to paste.")
        if d["extra"]:
            print("\nIn the sheet, not in your brain:")
            for s in d["extra"]:
                print("  %s  %-14s %s" % (s["due"] or "no date",
                                          (s["course"] or "?")[:14],
                                          s["assignment"][:58]))
            print("\n  --pull puts these in the tray to accept.")
        if d["clashes"]:
            print("\nDates that disagree:")
            for c in d["clashes"]:
                print("  %-42s sheet %s / brain %s"
                      % (c["assignment"][:42], c["sheet"], c["brain"]))
        if not (d["missing"] or d["extra"] or d["clashes"]):
            print("In step — nothing to do.")
        return 0
    except ValueError as exc:
        print(exc)
        return 1


if __name__ == "__main__":
    sys.exit(main() or 0)

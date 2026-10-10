#!/usr/bin/env python3
"""Read the class folder, find the dates hiding in the slides.

    python3 brain/tools/school.py              # what's new, and what it found
    python3 brain/tools/school.py --scan       # read the new decks, fill the tray
    python3 brain/tools/school.py --pending    # the tray
    python3 brain/tools/school.py --accept ID
    python3 brain/tools/school.py --dismiss ID
    python3 brain/tools/school.py --guides     # a study guide per deck that lacks one

The problem this solves: Blackboard has no API worth having, and the syllabi
turn out not to carry the dates. Of five syllabi for Term 4, exactly one names
a deadline. Every other date — the business plan, the jury, the personal SWOT
due on a Monday — was sitting in a slide deck, in a bullet, in a PDF nobody
would reread.

So the folder is the bridge. Whatever lands in it gets read: PDF, PowerPoint,
Word, plain text. Lines that look like a commitment with a date attached
become suggestions in a tray. She accepts or dismisses each one, and accepting
appends a line to inbox.md — the same path as anything she captures herself.

Nothing files itself. Nothing is written into her class folder: this reads
there and writes only inside the brain.
"""

import argparse
import hashlib
import json
import os
import re
import unicodedata
import subprocess
import sys
import zipfile
from datetime import date, datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
BRAIN = os.path.dirname(HERE)
sys.path.insert(0, HERE)

STATE = os.path.join(BRAIN, ".school.json")
SCHOOL = os.path.join(BRAIN, "school")
GUIDES = os.path.join(SCHOOL, "guides")
# Decks caught out of ~/Downloads live here, inside the brain. They are never
# filed back into her class folder: the brain does not write outside itself,
# and a script that reorganises someone's Desktop is a script they stop
# trusting the first time it guesses wrong.
DECKS = os.path.join(SCHOOL, "decks")

READABLE = {".pdf", ".pptx", ".docx", ".txt", ".md"}
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv"}
MAX_CHARS = 60000          # a deck is slides, not a novel
MAX_SUGGESTIONS = 12       # a tray nobody can finish is a tray nobody opens


# --------------------------------------------------------------------------
# where the class folder is

def _config():
    try:
        with open(os.path.join(BRAIN, "config.json"), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def root():
    """The class folder, from the source named in config.json."""
    for src in _config().get("sources", []):
        if src.get("name", "").startswith("School"):
            return os.path.expanduser(src.get("path", ""))
    return os.path.expanduser("~/Desktop/School")


def term_root():
    """This term's subfolder if there is one, else the whole class folder.
    A term folder keeps the scan off four years of old decks."""
    for name in ("Specialization", "Term 4"):
        p = os.path.join(root(), name)
        if os.path.isdir(p):
            return p
    return root()


# --------------------------------------------------------------------------
# reading what landed

def _pdf_text(path):
    try:
        r = subprocess.run(["pdftotext", "-layout", path, "-"],
                           capture_output=True, text=True, timeout=120)
        return r.stdout if r.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def _ooxml_text(path, member_match):
    """PowerPoint and Word are zipped XML. Pulling the text out needs no
    library — strip the tags and keep what a person would read."""
    out = []
    try:
        with zipfile.ZipFile(path) as z:
            names = sorted(n for n in z.namelist() if member_match(n))
            for n in names:
                try:
                    xml = z.read(n).decode("utf-8", "replace")
                except (KeyError, OSError):
                    continue
                xml = re.sub(r"</a:p>|</w:p>", "\n", xml)
                xml = re.sub(r"<[^>]+>", "", xml)
                out.append(xml)
    except (zipfile.BadZipFile, OSError):
        return ""
    import html
    return html.unescape("\n".join(out))


def extract(path):
    """The readable text of one file, or "" when it can't be read."""
    ext = os.path.splitext(path)[1].lower()
    if ext == ".pdf":
        text = _pdf_text(path)
    elif ext == ".pptx":
        text = _ooxml_text(path, lambda n: n.startswith("ppt/slides/slide")
                           and n.endswith(".xml"))
    elif ext == ".docx":
        text = _ooxml_text(path, lambda n: n == "word/document.xml")
    elif ext in (".txt", ".md"):
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                text = f.read()
        except OSError:
            text = ""
    else:
        return ""
    return text[:MAX_CHARS]


def courses():
    """This term's courses, and how to recognise one in a slide deck.

    The class folder already answers this: one subfolder per course, named
    by her. The syllabus filenames inside carry the professors' surnames in
    brackets, which is often the only name printed on a deck's footer."""
    out = []
    base = term_root()
    try:
        names = sorted(d for d in os.listdir(base)
                       if os.path.isdir(os.path.join(base, d))
                       and not d.startswith("."))
    except OSError:
        return out
    for name in names:
        words = {w for w in re.sub(r"[^a-z ]", " ", name.lower()).split()
                 if len(w) > 3 and w not in ("and", "the", "for", "with",
                                             "real", "world")}
        profs = set()
        try:
            for fn in os.listdir(os.path.join(base, name)):
                for m in re.findall(r"\(([^)]*)\)", fn):
                    for part in re.split(r"[.\s]+", m):
                        part = part.strip("-")
                        if len(part) > 3 and part[:1].isupper():
                            profs.add(part.lower())
        except OSError:
            pass
        out.append({"name": name, "words": words, "profs": profs})
    return out


# --------------------------------------------------------------------------
# class sessions, from the calendar
#
# The calendar knows when each class meets; the class folder knows what the
# courses are called. Together they say which class a recording was made in
# and when a reading is due. Only the calendar cache is read (calendar_read.
# cached_all): nothing here waits on Calendar.app.

SESSION_MINUTES = 90       # a class whose length the calendar never measured


def course_of(title, known=None):
    """The course a calendar entry is a session of, or "". Two of the
    course's words, or its professor's surname, and a clear winner."""
    low = (title or "").lower()
    best, score, runner = "", 0, 0
    for c in (known if known is not None else courses()):
        hit = sum(1 for w in c["words"] if w in low)
        hit += 2 * sum(1 for p in c["profs"] if p in low)
        if hit > score:
            best, score, runner = c["name"], hit, score
        elif hit > runner:
            runner = hit
    return best if score >= 2 and score > runner else ""


def short_course(name):
    """"Managing Innovation in Established Firms" → "Managing Innovation":
    a long course name stops at its first small word. Short ones stay."""
    words = (name or "").split()
    if len(words) < 4:
        return (name or "").strip()
    out = []
    for w in words:
        if out and w.lower() in ("in", "and", "of", "for", "through", "&"):
            break
        out.append(w)
    return " ".join(out)


def class_page(course):
    """The class's own page in brain/school/, by its title's first part
    ("# Venture Strategy — the Backbone"). "" when none fits."""
    words = {w for w in re.sub(r"[^a-z ]", " ", (course or "").lower()).split()
             if len(w) > 3}
    best, score = "", 0
    try:
        names = sorted(os.listdir(SCHOOL))
    except OSError:
        return ""
    for fn in names:
        if not fn.endswith(".md") or fn.lower() in ("readme.md",):
            continue
        try:
            with open(os.path.join(SCHOOL, fn), encoding="utf-8") as f:
                head = f.readline()
        except OSError:
            continue
        if not head.startswith("# "):
            continue
        first = re.split(r"\s+[—–-]\s+", head[2:].strip())[0].lower()
        hit = sum(1 for w in words if w in first)
        if hit > score:
            best, score = os.path.join(SCHOOL, fn), hit
    return best if score >= 1 else ""


def sessions(course=None, known=None):
    """[(start datetime, minutes, course)] for class sessions the calendar
    cache holds, one per time (her calendar carries each class twice)."""
    try:
        import calendar_read
        evs = calendar_read.cached_all()
    except Exception:                                    # noqa: BLE001
        return []
    known = known if known is not None else courses()
    out = {}
    for when, title, mins in evs:
        c = course_of(title, known)
        if not c or (course and c != course):
            continue
        try:
            start = datetime.strptime(when[:16], "%Y-%m-%d %H:%M")
        except ValueError:
            continue
        key = (start, c)
        if key not in out or (mins and not out[key]):
            out[key] = mins
    return sorted((s, m or SESSION_MINUTES, c) for (s, c), m in out.items())


def class_at(start, minutes, known=None):
    """The class a recording was made in: the session it overlaps most, by
    at least ten minutes or half the recording. None when it fits none."""
    end = start + timedelta(minutes=minutes or 1)
    need = min(10.0, max(1.0, (minutes or 1) * 0.5))
    best, got = None, 0.0
    for s, m, c in sessions(known=known):
        e = s + timedelta(minutes=m)
        over = (min(end, e) - max(start, s)).total_seconds() / 60
        if over >= need and over > got:
            best, got = (s, m, c), over
    if not best:
        return None
    s, m, c = best
    nxt = next_session(c, start + timedelta(minutes=minutes or 1), known)
    return {"course": c, "short": short_course(c), "page": class_page(c),
            "start": s, "minutes": m, "next": nxt}


def next_session(course, after=None, known=None):
    """When the course next meets after `after` (now by default), or None.
    A class day is one meeting: once a session has started that day, the
    rest of the day's sessions are the same class, and prep "for next time"
    is due the next day it meets."""
    after = after or datetime.now()
    ss = [x[0] for x in sessions(course, known)]
    begun = any(x.date() == after.date() and x <= after for x in ss)
    for x in ss:
        if x > after and not (begun and x.date() == after.date()):
            return x
    return None


# Material that must never reach a model, whatever else happens.
#
# A project can carry an NDA: a partner's unpublished work that may not go
# into AI tools. A local text extractor is not a model and nothing leaves the
# Mac when one runs — but a guide IS a model call, and the gap between those
# two is exactly where a mistake would happen. So the rule is enforced at the
# earliest point instead: a file whose NAME matches any of these is never
# opened, never copied, never summarised. Anything marked sensitive gets one
# of these words in its filename.
#
# Patterns live in config.json under school.confidential so she can add to
# them without touching code. Matching is on the filename alone, which is the
# only thing that can be checked without reading the file.
CONFIDENTIAL_DEFAULT = ["nda", "confidential", "under embargo",
                        "do not distribute", "patent", "unpublished",
                        # Her call, 9 Oct: the French markings too.
                        "confidentiel", "brevet", "ne pas diffuser"]


# Whole folders the deck scanner must not enter, by name. The Venture
# working folder sits inside the class folder, and its charters, trackers and
# run sheets are project work, not class sessions: without this each one would
# become a deck folded into the course guide.
PROTECTED_DIRS_DEFAULT = ["Studio Course"]


def protected_dirs():
    cfg = (_config().get("school") or {}).get("protected_folders")
    return [str(x).lower() for x in (cfg or PROTECTED_DIRS_DEFAULT)]


def confidential_patterns():
    # The defaults always hold: config.json is writable by the brain's own
    # runs, and an emptied list would send an NDA deck to a model.
    cfg = (_config().get("school") or {}).get("confidential") or []
    return list(dict.fromkeys(str(x).lower() for x in
                              list(CONFIDENTIAL_DEFAULT) + list(cfg)))


def _guard_norm(s):
    """A name as the guard reads it: compatibility forms folded (full-width
    ＮＤＡ), accents and dotted capitals dropped, dotted initials joined
    (N.D.A.), and _ - . turned into spaces (Do-Not-Distribute)."""
    s = unicodedata.normalize("NFKD", unicodedata.normalize("NFKC", s or ""))
    s = "".join(c for c in s if not unicodedata.combining(c)).casefold()
    s = re.sub(r"\b(?:[a-z]\.){2,}", lambda m: m.group(0).replace(".", ""), s)
    return re.sub(r"[_\-.\s]+", " ", s)


def is_confidential(name):
    """Checked on the name alone (CLAUDE.md). The file's own name matches
    as before, and now also after normalising, so separators and look-alike
    letters don't slip past; every folder above it counts too, as whole
    words, so a file inside "NDA material/" is held (9 Oct audit). A path on
    disk is also checked whole and with links followed: run from inside
    "NDA material/", or through a plainly named link, the folder was unseen."""
    names = [name]
    try:
        if name and os.path.exists(name):
            names += [os.path.abspath(name), os.path.realpath(name)]
    except (OSError, ValueError):
        pass
    return any(_confidential_name(n) for n in dict.fromkeys(names))


def _confidential_name(name):
    pats = confidential_patterns()
    base = os.path.basename(name or "")
    nb = " " + _guard_norm(base) + " "
    for p in pats:
        np_ = _guard_norm(p).strip()
        if len(np_) <= 3:
            # A short marking counts as a word of its own: "nda" inside
            # Agenda, Monday and Calendar held back 170 class files (her
            # call, 9 Oct). "NDA_deck", "N.D.A." and "ＮＤＡ" still match.
            if re.search(r"(?<![a-z0-9])" + re.escape(np_) + r"(?![a-z0-9])", nb):
                return True
        elif p in base.lower() or np_ in nb:
            return True
    for part in os.path.dirname(name or "").replace("\\", "/").split("/"):
        np = " " + _guard_norm(part) + " "
        if part and any(" " + _guard_norm(p).strip() + " " in np for p in pats):
            return True
    return False


# What goes into a study guide on its own: the session slides, known by
# their names ("Slides Class MBA …", "Managing innovation session 1").
# Everything else in a class folder — cases, articles, worksheets, a guest's
# company deck — is a professor's material that may not be meant for a
# model. It is read on this Mac for dates and nothing else, until she adds
# it to a guide from the School tab (her call, 25 Sep).
SLIDES_RX = re.compile(r"(?i)(?<![a-z])(slides?|session|lecture)(?![a-z])")


def is_slides(name):
    return bool(SLIDES_RX.search(os.path.basename(name or "")))


def guide_extras():
    return set((_config().get("school") or {}).get("guide_extra") or [])


def guide_courses():
    """Courses whose every deck goes into the guide, whatever it is named.
    Some classes name their decks only by school, year and number, which
    no class-name match catches (her call, 2 Oct: the new slides fold in as
    they arrive)."""
    return {c.lower() for c in
            (_config().get("school") or {}).get("guide_courses") or []}


def in_guide(f):
    """Slides by name, plus anything she added with Add to guide, plus every
    deck of a course she opted in whole."""
    return (is_slides(f["name"]) or f["rel"] in guide_extras()
            or (f.get("course") or "").lower() in guide_courses())


def set_guide_extra(rel, on):
    """Add a class file to its course guide, or take it back out. The
    confidential name guard wins over her click: a file it blocks never
    reaches a model, whoever asks."""
    rel = (rel or "").strip()
    if not rel:
        raise ValueError("which file?")
    if on and is_confidential(rel):
        raise ValueError("That file's name marks it confidential, so it "
                         "stays out of the guides.")
    path = os.path.join(BRAIN, "config.json")
    with open(path, encoding="utf-8") as fh:
        cfg = json.load(fh)
    sch = cfg.setdefault("school", {})
    cur = [x for x in (sch.get("guide_extra") or []) if x != rel]
    if on:
        cur.append(rel)
    sch["guide_extra"] = sorted(cur)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(cfg, indent=2) + "\n")
    os.replace(tmp, path)
    return {"ok": True, "guide_extra": sch["guide_extra"]}


def stale_year(name):
    """The year a reused deck was made for, when that is an earlier one.
    Profs reuse last year's deck under last year's name, and its dates are
    last year's too: the 2025 Managing Innovation overview put 3 October —
    a Saturday this year — into the inbox as a class (found 25 Sep)."""
    ys = [int(y) for y in re.findall(r"(?<!\d)(20\d\d)(?!\d)",
                                     os.path.basename(name or ""))]
    now = date.today().year
    if not ys or any(y >= now for y in ys):
        return None
    return max(ys)


# Before asking which course a file belongs to, ask whether it is coursework
# at all. Without this a LinkedIn profile that happens to say
# "entrepreneurship" gets filed as a lecture.
SCHOOL_MARK = re.compile(
    r"\b(school|mba|syllabus|specialization|specialisation|"
    r"lecture|session \d|professor|blackboard)\b", re.I)


def classify_name(filename, known=None):
    """Which course, from the filename alone — nothing is opened.

    Weaker than reading the file, and deliberately so: it is the only check
    that can run on something the brain must not look inside."""
    stem = " " + re.sub(r"[^a-z0-9]+", " ", os.path.splitext(
        os.path.basename(filename or ""))[0].lower()) + " "
    best, score, runner = "", 0, 0
    for c in (known if known is not None else courses()):
        hit = sum(1 for w in c["words"] if (" " + w + " ") in stem
                  or w in stem)
        hit += 2 * sum(1 for p in c["profs"] if p in stem)
        if hit > score:
            best, score, runner = c["name"], hit, score
        elif hit > runner:
            runner = hit
    return best if score >= 2 and score > runner else ""


def classify(text, known=None):
    """Which course a deck belongs to, from what is printed on it.

    Counts how often each course's words occur, rather than whether they
    occur. A deck's own course is in the footer of every page; other courses
    get named once in an agenda slide. Presence alone filed the track
    introduction — which lists all five courses — under whichever one it
    happened to mention first."""
    body = " ".join((text or "").lower().split())
    if not body or not SCHOOL_MARK.search(body[:20000]):
        return ""
    best, score, runner = "", 0.0, 0.0
    for c in (known if known is not None else courses()):
        hit = 0.0
        for w in c["words"]:
            hit += min(body.count(w), 12)
        for pr in c["profs"]:
            hit += 3 * min(body.count(pr), 12)
        if hit > score:
            best, score, runner = c["name"], hit, score
        elif hit > runner:
            runner = hit
    # A clear winner, not a coin toss between two courses.
    if score < 6 or (runner and score < runner * 1.4):
        return ""
    return best


def _already_have(name, size):
    """She downloaded it and filed it into her own class folder herself.

    Downloads keeps the original and adds "(1)" to a re-download, so the copy
    on her Desktop and the one in Downloads differ by a filename suffix and
    nothing else. Catching it again builds a second guide for the same deck
    under a second name."""
    stem = re.sub(r"\s*\(\d+\)$", "", os.path.splitext(name)[0]).strip().lower()
    for f in files():
        if f["size"] != size:
            continue
        other = re.sub(r"\s*\(\d+\)$", "",
                       os.path.splitext(f["name"])[0]).strip().lower()
        if other == stem:
            return True
    return False


def catch(hours=96, apply=True, deep=False):
    """Class material sitting in ~/Downloads, copied in and filed by course.

    Blackboard posts the slides on the morning of the class, so they arrive
    named things like "Session 3 v2 (1).pdf" in a folder with everything else
    she has ever downloaded. Rather than asking her to sort them, this files
    them by course. Copies, never moves: her Downloads folder is hers, and a
    file that vanishes is a file she goes looking for.

    By default it decides from the FILENAME and opens nothing. That is the
    weaker signal and it is the right default, because ~/Downloads is also
    where confidential Venture material will land, and a rule that depends
    on remembering to be careful is not a rule. `deep=True` reads the text
    too — still locally, still no model — and even then it refuses anything
    whose name is on the confidential list.

    Files it cannot place are reported, not guessed at."""
    import shutil
    import time
    dl = os.path.expanduser("~/Downloads")
    if not os.path.isdir(dl):
        return {"found": [], "why": "no Downloads folder"}
    cutoff = time.time() - hours * 3600
    known, out = courses(), []
    for fn in sorted(os.listdir(dl)):
        if os.path.splitext(fn)[1].lower() not in (".pdf", ".pptx", ".docx"):
            continue
        full = os.path.join(dl, fn)
        try:
            if os.path.getmtime(full) < cutoff or os.path.getsize(full) < 20000:
                continue
        except OSError:
            continue
        if is_confidential(fn):
            out.append({"file": fn, "course": "", "protected": True})
            continue
        if _already_have(fn, os.path.getsize(full)):
            continue
        course = classify_name(fn, known)
        if not course and deep:
            course = classify(extract(full), known)
        if not course:
            out.append({"file": fn, "course": "", "unplaced": True})
            continue
        dest_dir = os.path.join(DECKS, course)
        dest = os.path.join(dest_dir, fn)
        if os.path.exists(dest):
            out.append({"file": fn, "course": course, "already": True})
            continue
        if apply:
            os.makedirs(dest_dir, exist_ok=True)
            shutil.copy2(full, dest)
        out.append({"file": fn, "course": course, "copied": apply})
    return {"found": out}


def files():
    """Every readable file this term, from her class folder and from what was
    caught out of Downloads."""
    base = term_root()
    found = []
    for root_dir in (base, DECKS):
        if not os.path.isdir(root_dir):
            continue
        found += _walk(root_dir, base if root_dir == base else DECKS)
    # Her own folder wins over a caught copy of the same bytes.
    seen, out = set(), []
    for f in found:
        stem = re.sub(r"\s*\(\d+\)$", "",
                      os.path.splitext(f["name"])[0]).strip().lower()
        key = (f["size"], stem)
        if key in seen:
            continue
        seen.add(key)
        out.append(f)
    return sorted(out, key=lambda f: f["mtime"], reverse=True)


def _walk(base, rel_to):
    found = []
    prot = protected_dirs()
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = [d for d in dirnames
                       if d not in SKIP_DIRS and not d.startswith(".")
                       and d.lower() not in prot]
        for fn in filenames:
            if fn.startswith(".") or fn.startswith("~$"):
                continue
            if is_confidential(fn):
                continue
            if os.path.splitext(fn)[1].lower() not in READABLE:
                continue
            full = os.path.join(dirpath, fn)
            rel = os.path.relpath(full, rel_to)
            course = rel.split(os.sep)[0] if os.sep in rel else "(loose)"
            try:
                mtime = os.path.getmtime(full)
                size = os.path.getsize(full)
            except OSError:
                continue
            found.append({"path": full, "rel": rel, "course": course,
                          "name": fn, "mtime": mtime, "size": size})
    return found


def _fingerprint(f):
    """Cheap and good enough: a file whose size and mtime are unchanged has
    not changed. Hashing 100MB of epubs to learn nothing is not free."""
    return hashlib.sha1(
        f"{f['rel']}|{int(f['mtime'])}|{f['size']}".encode()).hexdigest()[:12]


# --------------------------------------------------------------------------
# finding a date in a line of a slide

MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun",
     "jul", "aug", "sep", "oct", "nov", "dec"], 1)}

_MONTH_RE = ("jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|"
             "jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t|tember)?|oct(?:ober)?|"
             "nov(?:ember)?|dec(?:ember)?")

DATE_PATTERNS = [
    # 2026-11-23
    (re.compile(r"\b(20\d\d)-(\d{1,2})-(\d{1,2})\b"),
     lambda m: (int(m.group(1)), int(m.group(2)), int(m.group(3)))),
    # Nov 23th, December 9th 2026, Sept 21
    (re.compile(r"\b(" + _MONTH_RE + r")\.?\s+(\d{1,2})(?:st|nd|rd|th)?"
                r"(?:\s*,?\s*(20\d\d))?\b", re.I),
     lambda m: (int(m.group(3)) if m.group(3) else None,
                MONTHS[m.group(1)[:3].lower()], int(m.group(2)))),
    # 23 November 2026, 9th December
    (re.compile(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+(" + _MONTH_RE + r")\.?"
                r"(?:\s*,?\s*(20\d\d))?\b", re.I),
     lambda m: (int(m.group(3)) if m.group(3) else None,
                MONTHS[m.group(2)[:3].lower()], int(m.group(1)))),
    # 23/11/2026 and 23/11 — day first, this is France
    (re.compile(r"\b(\d{1,2})/(\d{1,2})(?:/(20\d\d|\d\d))?\b"),
     lambda m: (_yy(m.group(3)), int(m.group(2)), int(m.group(1)))),
]

# "Module 1/2" is not the first of February. A bare slash pair is only a date
# when the line says outright that something is owed — a named month needs no
# such proof, a pair of digits does.
STRICT_DUE = re.compile(
    r"\b(due|deadline|submit|submission|hand[- ]?in|upload|by)\b", re.I)

# "by Monday 21rd", "by the 30th" — a day with no month at all. Slides do
# this constantly and mean the one coming up. Only trusted on a line that
# already sounds like a commitment, and never marked exact.
BARE_DAY = re.compile(
    r"\b(?:by|before|on|due)\s+(?:the\s+)?"
    r"(?:mon|tues?|wed(?:nes)?|thur?s?|fri|sat(?:ur)?|sun)(?:day)?\s*"
    r"(\d{1,2})(?:st|nd|rd|th)?\b"
    r"|\b(?:by|before|due)\s+the\s+(\d{1,2})(?:st|nd|rd|th)\b", re.I)

# A line has to sound like a commitment, not just mention a month.
COMMITMENT = re.compile(
    r"\b(due|deadline|submit|submission|hand[- ]?in|deliver|deliverable|"
    r"upload|send|present|presentation|pitch|jury|exam|quiz|test|"
    r"assignment|paper|report|essay|memo|draft|final|key date|"
    r"at home|prepare|read|before class|by |"
    r"business plan|plan|model|canvas|slides|deck|charter|interview|"
    r"kick[- ]?off|milestone|workshop|field trip|guest)\b", re.I)

# ...and these are how a slide says "this is not a date to act on".
NOT_A_DEADLINE = re.compile(
    r"\b(copyright|©|all rights reserved|founded|since \d{4}|"
    r"born|graduated|version|page \d)\b", re.I)


def _yy(g):
    if not g:
        return None
    n = int(g)
    return n if n > 100 else 2000 + n


def _term_year(month, today=None):
    """A slide that says "Nov 23th" means the next 23 November from now.
    An academic year straddles New Year, so the year has to be inferred and
    inferring it backwards is how a deadline lands in the past and is
    silently ignored."""
    today = today or date.today()
    y = today.year
    try:
        if date(y, month, 1) < date(today.year, today.month, 1):
            y += 1
    except ValueError:
        return None
    return y


def _next_day_of_month(d, today):
    """The next time the month hits this day number. "by Monday 21rd" on a
    16 September slide means 21 September, not 21 October."""
    if not 1 <= d <= 31:
        return None
    y, mo = today.year, today.month
    for _ in range(13):
        try:
            when = date(y, mo, d)
        except ValueError:
            when = None
        if when and when >= today:
            return when
        mo += 1
        if mo > 12:
            mo, y = 1, y + 1
    return None


def _one_line(line, today):
    """The date owed by a single line of text, or None."""
    if NOT_A_DEADLINE.search(line) or not COMMITMENT.search(line):
        return None
    for i, (rx, unpack) in enumerate(DATE_PATTERNS):
        m = rx.search(line)
        if not m:
            continue
        try:
            y, mo, d = unpack(m)
        except (KeyError, ValueError):
            continue
        if not (1 <= mo <= 12 and 1 <= d <= 31):
            continue
        is_slash = i == len(DATE_PATTERNS) - 1
        if is_slash and y is None and not STRICT_DUE.search(line):
            continue
        exact = y is not None
        if y is None:
            y = _term_year(mo, today)
        if y is None:
            continue
        try:
            when = date(y, mo, d)
        except ValueError:
            continue
        # A date already well past is a date from last year's deck.
        if (today - when).days > 14:
            continue
        return {"date": when.isoformat(), "exact": exact}
    m = BARE_DAY.search(line)
    if m:
        when = _next_day_of_month(int(m.group(1) or m.group(2)), today)
        if when:
            return {"date": when.isoformat(), "exact": False}
    return None


def find_dates(text, today=None):
    """Lines that name a date and sound like something owed.

    A slide's text does not respect line breaks — "DUE FRIDAY," and "OCTOBER
    30th, 5pm" arrive as two lines, and either alone is unreadable. So each
    line is tried on its own and then joined to the one after it.

    Returns [{"date": "2026-11-23", "line": "...", "exact": bool}]."""
    today = today or date.today()
    lines = [" ".join(r.split()) for r in text.splitlines()]
    out, seen = [], set()
    for i, line in enumerate(lines):
        nxt = lines[i + 1] if i + 1 < len(lines) else ""
        for cand in (line, (line + " " + nxt).strip() if nxt else ""):
            if not (6 <= len(cand) <= 300):
                continue
            hit = _one_line(cand, today)
            if not hit:
                continue
            key = (hit["date"], re.sub(r"[^a-z0-9]", "", cand.lower())[:45])
            if key in seen:
                continue
            # The joined version repeats the single line's find; keep the
            # first one that worked and move on.
            if any(h["date"] == hit["date"]
                   and re.sub(r"[^a-z0-9]", "", h["line"].lower())[:45]
                   in re.sub(r"[^a-z0-9]", "", cand.lower()) for h in out):
                break
            seen.add(key)
            out.append({"date": hit["date"], "line": cand,
                        "exact": hit["exact"]})
            break
    return out


# --------------------------------------------------------------------------
# the tray

def _state():
    try:
        with open(STATE, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {"seen": {}, "suggestions": []}


def _save(st):
    st["suggestions"] = st.get("suggestions", [])[-200:]
    tmp = STATE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(st, f, indent=2, ensure_ascii=False)
        f.write("\n")
    os.replace(tmp, STATE)


def pending():
    return [s for s in _state().get("suggestions", [])
            if s.get("status") == "pending"]


def _already(st, course, when, line):
    """The same date turns up on the agenda slide, the deliverables slide and
    next week's recap. One tray line each would be three."""
    key = re.sub(r"[^a-z0-9]", "", line.lower())[:40]
    for s in st.get("suggestions", []):
        if s.get("course") == course and s.get("due") == when:
            if re.sub(r"[^a-z0-9]", "", s.get("line", "").lower())[:40] == key:
                return True
            return True   # same course, same day — she only needs telling once
    return False


def _in_brain(when, line):
    """Already filed by hand, or by an earlier accept."""
    words = set(re.sub(r"[^a-z0-9 ]", " ", line.lower()).split())
    for name in ("workstreams.md", "inbox.md"):
        try:
            with open(os.path.join(BRAIN, name), encoding="utf-8") as f:
                body = f.read()
        except OSError:
            continue
        for row in body.splitlines():
            if when in row:
                rw = set(re.sub(r"[^a-z0-9 ]", " ", row.lower()).split())
                if len(words & rw) >= max(2, len(words) // 4):
                    return True
    return False


def _phrase(line, course):
    """A tray line she can read without opening the slide. The model tidies
    it when it can; the slide's own words are the fallback, which is honest
    if clumsy. One small no-tool call per date found, routed by llm.py."""
    try:
        import llm
        r = llm.complete(
            "school",
            "Slide line from the course %r:\n\n%s\n\n"
            "Rewrite it as one task starting with a verb, under 15 words, "
            "no date in the text, no quotes, no preamble. If it is not "
            "something a student must do, reply exactly: SKIP" % (course, line),
            system="You turn slide bullets into task lines. Reply with the "
                   "line only.",
            timeout=45)
        text = (r.get("text") or "").strip().strip('"').splitlines()[0]
        if text.upper().startswith("SKIP"):
            return None
        if 3 < len(text) < 140:
            return text
    except Exception:
        pass
    return line[:140]


DUMP = os.path.join(SCHOOL, "venture-inbox.md")


def _dump_waiting(st):
    """She pastes raw Venture notes into venture-inbox.md. Sorting them
    needs judgement, so it is a session's job, not this scan's — but a file
    nobody is told about is a file nobody sorts. One inbox line per batch,
    keyed on length so the same paste isn't announced every morning."""
    try:
        with open(DUMP, encoding="utf-8") as f:
            body = f.read()
    except OSError:
        return False
    body = body.split("---", 1)[-1].strip()
    if len(body) < 40:
        return False
    mark = "dump:%d" % len(body)
    if st.get("dump") == mark:
        return False
    st["dump"] = mark
    line = ("- [ ] Sort the Venture notes — there's pasted material waiting "
            "in the school folder's Venture inbox\n")
    path = os.path.join(BRAIN, "inbox.md")
    try:
        with open(path, encoding="utf-8") as f:
            cur = f.read()
    except OSError:
        cur = ""
    if "Sort the Venture notes" not in cur:
        with open(path, "w", encoding="utf-8") as f:
            f.write((cur.rstrip() + "\n" if cur.strip() else "") + line)
    return True


def scan(use_model=True, limit=MAX_SUGGESTIONS):
    """Read what's new, propose what it found. Never files anything."""
    st = _state()
    seen = st.setdefault("seen", {})
    sugs = st.setdefault("suggestions", [])
    report = {"read": [], "skipped": 0, "new": 0}

    for f in files():
        fp = _fingerprint(f)
        if seen.get(f["rel"]) == fp:
            report["skipped"] += 1
            continue
        text = extract(f["path"])
        seen[f["rel"]] = fp
        if not text.strip():
            continue
        hits = find_dates(text)
        report["read"].append({"file": f["rel"], "course": f["course"],
                               "dates": len(hits)})
        for h in hits:
            if report["new"] >= limit:
                break
            if _already(st, f["course"], h["date"], h["line"]):
                continue
            if _in_brain(h["date"], h["line"]):
                continue
            # Only guide material is phrased by a model; the rest keeps the
            # slide's own words, so nothing from it leaves this Mac.
            task = (_phrase(h["line"], f["course"])
                    if use_model and in_guide(f) else h["line"])
            if not task:
                continue
            sugs.append({
                "id": hashlib.sha1(
                    (f["rel"] + h["date"] + h["line"]).encode()).hexdigest()[:10],
                "status": "pending",
                "course": f["course"],
                "task": task,
                "due": h["date"],
                "exact": h["exact"],
                "line": h["line"],
                "source": f["name"],
                "found": date.today().isoformat(),
                "old_year": stale_year(f["name"]),
            })
            report["new"] += 1

    report["readings"] = _propose_readings(st)
    report["dump_waiting"] = _dump_waiting(st)
    _save(st)
    report["pending"] = pending()
    return report


# --------------------------------------------------------------------------
# readings: a new PDF in a class folder is prep for the next session
#
# Blackboard posts a case or an article; she downloads it into the class
# folder. Anything there that is not slides, a syllabus or an overview, and
# that arrived since the tray last looked, is proposed as a reading due at
# the class's next session. Adding it writes the task with its file attached,
# so it gets Speed-read at once. Files that were there before this started
# (readings_since) are left alone: a term's worth of old PDFs is not news.

NOT_A_READING = re.compile(
    r"(?i)syllabus|overview|outline|recommended reading|reading list"
    r"|schedule|planning|template|rubric|grading|guidelines"
    # in-class handouts: done in the room, not read before it
    r"|exerci[cs]e|worksheet|handout|memo.?card|canvas|quiz|guess your")
READING_WINDOW_DAYS = 10


def _reading_title(name):
    stem = re.sub(r"\s*\(\d+\)$", "", os.path.splitext(name)[0])
    stem = re.sub(r"[_]+", " ", stem)
    stem = re.sub(r"\s+", " ", stem).strip()
    return stem[:1].upper() + stem[1:]


def _linked_rels():
    """The class files a task already points at, open or done."""
    try:
        import model as M
        import reading as RD
    except Exception:                                    # noqa: BLE001
        return set()
    out = set()
    for w in M.load():
        for t in w.get("tasks") or []:
            f = RD.file_for(t)
            if f:
                out.add(f["rel"])
    return out


def _propose_readings(st, since=None, now=None):
    now = now or datetime.now()
    since = since or st.setdefault("readings_since", now.date().isoformat())
    try:
        cutoff = max(datetime.fromisoformat(since),
                     now - timedelta(days=READING_WINDOW_DAYS)).timestamp()
    except ValueError:
        cutoff = (now - timedelta(days=READING_WINDOW_DAYS)).timestamp()
    known = courses()
    names = {c["name"] for c in known}
    sugs = st.setdefault("suggestions", [])
    have = {x.get("id") for x in sugs}
    linked, new = None, 0
    for f in files():
        if (f["course"] not in names or f["mtime"] < cutoff
                or not f["name"].lower().endswith(".pdf")
                or is_slides(f["name"]) or NOT_A_READING.search(f["name"])
                or stale_year(f["name"])):
            continue
        sid = hashlib.sha1(("reading|" + f["rel"]).encode()).hexdigest()[:10]
        if sid in have:
            continue
        if linked is None:
            linked = _linked_rels()
        if f["rel"] in linked:
            continue
        nxt = next_session(f["course"], now, known)
        sugs.append({
            "id": sid, "status": "pending", "kind": "reading",
            "course": f["course"],
            "task": 'Read "%s" for %s' % (_reading_title(f["name"]),
                                          short_course(f["course"])),
            "due": nxt.date().isoformat() if nxt else "",
            "exact": True,
            "line": "New in your %s folder: %s" % (
                short_course(f["course"]), f["name"]),
            "source": f["name"], "rel": f["rel"],
            "found": now.date().isoformat(),
        })
        have.add(sid)
        new += 1
    return new


def _add_school_task(line, notes=()):
    """Append one task to the School workstream, straight into
    workstreams.md, and stamp Touched: she said yes to it on the page. A
    line already there, word for word, is not added twice (the page's ticks
    find a line by its words)."""
    path = os.path.join(BRAIN, "workstreams.md")
    with open(path, encoding="utf-8") as f:
        text = f.read()
    if line in text.split("\n"):
        return False
    lines = text.split("\n")
    start = next((i for i, ln in enumerate(lines)
                  if ln.startswith("## School")), None)
    if start is None:
        return False
    end = next((i for i in range(start + 1, len(lines))
                if lines[i].startswith("## ")), len(lines))
    last = max((i for i in range(start, end)
                if re.match(r"^(- \[[ xX]\]|\s{2,}- )", lines[i])),
               default=None)
    at = (last + 1) if last is not None else end
    lines[at:at] = [line] + ["  - " + n for n in notes]
    today = date.today().isoformat()
    for i in range(start, end):
        if lines[i].startswith("- **Touched:**"):
            lines[i] = "- **Touched:** " + today
            break
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    os.replace(tmp, path)
    return True


def _reading_line(sug):
    """The task a reading suggestion becomes, with how long it takes to
    read properly (200 words a minute, to the next five)."""
    est = ""
    try:
        import reading as RD
        f = next((x for x in RD._files() if x["rel"] == sug.get("rel")), None)
        words = RD.analyse(f["path"]).get("words", 0) if f else 0
        if words:
            est = " ~%dm" % (5 * -(-words // 1000))
    except Exception:                                    # noqa: BLE001
        pass
    due = " (due %s)" % sug["due"] if sug.get("due") else ""
    return "- [ ] %s%s%s" % (sug["task"], due, est)


def act(sid, action):
    if action not in ("accept", "dismiss"):
        raise ValueError("action must be accept or dismiss")
    st = _state()
    sug = next((s for s in st.get("suggestions", [])
                if s.get("id") == sid and s.get("status") == "pending"), None)
    if not sug:
        raise ValueError("that suggestion is gone — scan again")
    if action == "accept" and sug.get("kind") == "reading":
        # A reading is her prep, not a class deliverable: no (class), and
        # written straight into the School workstream with its file, so the
        # row has Speed-read the moment she says yes.
        same = [f for f in files() if f["name"] == sug.get("source")]
        note = "File: " + (sug["source"] if len(same) <= 1 else sug["rel"])
        _add_school_task(_reading_line(sug), [note])
    elif action == "accept":
        # A date printed on a course's own slides is a deliverable the whole
        # class owes, so it carries (class) and reaches the shared tracker.
        # Her own prep never gets the marker — see tracker.py.
        line = "- [ ] %s (class) (due %s) — %s, from %s" % (
            sug["task"], sug["due"], sug["course"], sug["source"])
        if sug.get("old_year"):
            line += (" — a %d deck, so probably last year's date: check "
                     "this year's before filing" % sug["old_year"])
        path = os.path.join(BRAIN, "inbox.md")
        try:
            with open(path, encoding="utf-8") as f:
                cur = f.read()
        except OSError:
            cur = ""
        with open(path, "w", encoding="utf-8") as f:
            f.write((cur.rstrip() + "\n" if cur.strip() else "") + line + "\n")
    sug["status"] = "accepted" if action == "accept" else "dismissed"
    _save(st)
    return {"ok": True, "pending": pending()}


# --------------------------------------------------------------------------
# guides

def _slug(s):
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", s.lower())).strip("-")


def guide(path, force=False):
    """A study guide for one deck, written into the brain beside the class
    files. The deck itself is never touched."""
    import llm
    course = os.path.relpath(path, term_root()).split(os.sep)[0]
    out_dir = os.path.join(GUIDES, _slug(course))
    out = os.path.join(out_dir, _slug(os.path.splitext(
        os.path.basename(path))[0]) + ".md")
    if os.path.exists(out) and not force:
        return {"skipped": out}
    text = extract(path)
    if len(text.strip()) < 400:
        return {"skipped": out, "why": "too little text to work from"}
    r = llm.complete(
        "school",
        "These are the slides from a session of %r on an School MBA "
        "entrepreneurship specialization.\n\nWrite a study guide in markdown:\n"
        "- a two-sentence summary of what this session is about\n"
        "- the key ideas, each with the one line that makes it usable\n"
        "- any framework or model named, with what it is for\n"
        "- anything the student must do, with its date if one is given\n"
        "- three questions the professor could reasonably ask in class\n\n"
        "Plain language. No preamble, no closing summary. Slides:\n\n%s"
        % (course, text[:40000]),
        system="You write tight study guides from lecture slides.",
        timeout=180)
    os.makedirs(out_dir, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        f.write("# %s\n\n*From the slides: %s*\n\n%s\n" % (
            os.path.splitext(os.path.basename(path))[0],
            os.path.basename(path), (r.get("text") or "").strip()))
    return {"wrote": out, "provider": r.get("provider")}


def guides(force=False):
    done = []
    for f in files():
        if os.path.splitext(f["name"])[1].lower() not in (".pdf", ".pptx"):
            continue
        low = f["name"].lower()
        if "syllabus" in low or "reading" in low:
            continue
        try:
            done.append(guide(f["path"], force=force))
        except Exception as exc:
            done.append({"failed": f["rel"], "why": str(exc)[:120]})
    return done


# --------------------------------------------------------------------------
# cli

def _status():
    st = _state()
    seen = st.get("seen", {})
    fs = files()
    fresh = [f for f in fs if seen.get(f["rel"]) != _fingerprint(f)]
    print("Class folder: %s" % term_root())
    print("%d readable files, %d not read yet." % (len(fs), len(fresh)))
    by_course = {}
    for f in fs:
        by_course.setdefault(f["course"], []).append(f)
    for course in sorted(by_course):
        n = len(by_course[course])
        new = sum(1 for f in by_course[course]
                  if seen.get(f["rel"]) != _fingerprint(f))
        print("  %-52s %2d file%s%s" % (
            course[:52], n, "" if n == 1 else "s",
            "  (%d new)" % new if new else ""))
    p = pending()
    if p:
        print("\n%d waiting in the tray — school.py --pending" % len(p))


def _show(items):
    if not items:
        print("Nothing in the tray.")
        return
    for s in items:
        flag = "" if s.get("exact") else "  (year inferred)"
        print("\n[%s]  %s%s" % (s["id"], s["due"], flag))
        print("  %s" % s["task"])
        print("  %s — %s" % (s["course"], s["source"]))
        print("  slide said: %s" % s["line"][:150])


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--scan", action="store_true")
    ap.add_argument("--pending", action="store_true")
    ap.add_argument("--accept", metavar="ID")
    ap.add_argument("--dismiss", metavar="ID")
    ap.add_argument("--catch", action="store_true",
                    help="file class material out of ~/Downloads")
    ap.add_argument("--hours", type=int, default=96)
    ap.add_argument("--deep", action="store_true",
                    help="also read file contents to place them (local only, "
                         "never for anything named confidential)")
    ap.add_argument("--guides", action="store_true")
    ap.add_argument("--guide", metavar="FILE")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--no-model", action="store_true",
                    help="find dates without any model call")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    if a.accept or a.dismiss:
        r = act(a.accept or a.dismiss, "accept" if a.accept else "dismiss")
        print("Done. %d left in the tray." % len(r["pending"]))
        return
    if a.pending:
        _show(pending())
        return
    if a.guide:
        print(json.dumps(guide(a.guide, force=a.force), indent=2))
        return
    if a.guides:
        for r in guides(force=a.force):
            print(json.dumps(r))
        return
    if a.catch:
        r = catch(hours=a.hours, deep=a.deep)
        got = [x for x in r["found"] if x.get("copied")]
        prot = [x for x in r["found"] if x.get("protected")]
        unp = [x for x in r["found"] if x.get("unplaced")]
        for x in got:
            print("  %-52s -> %s" % (x["file"][:52], x["course"]))
        print("%d file%s filed." % (len(got), "" if len(got) == 1 else "s")
              if got else "Nothing new in Downloads that looks like class "
                          "material.")
        if prot:
            print("\n%d left untouched, name says confidential:" % len(prot))
            for x in prot:
                print("  %s" % x["file"][:64])
        if unp:
            print("\n%d couldn't be placed from the name alone:" % len(unp))
            for x in unp:
                print("  %s" % x["file"][:64])
            print("  Move them into the class folder yourself, or rerun with "
                  "--deep to read them.")
        return
    if a.scan:
        # Reading dates with a model is one of the morning extras; with the
        # switch off the scan still runs, on the no-model reader alone.
        import usage
        r = scan(use_model=not a.no_model and usage.switch("extras"))
        if a.json:
            print(json.dumps(r, indent=2))
            return
        print("Read %d file%s, %d unchanged." % (
            len(r["read"]), "" if len(r["read"]) == 1 else "s", r["skipped"]))
        for x in r["read"]:
            if x["dates"]:
                print("  %s — %d date%s" % (x["file"][:60], x["dates"],
                                            "" if x["dates"] == 1 else "s"))
        print("\n%d new suggestion%s." % (r["new"],
                                          "" if r["new"] == 1 else "s"))
        _show(r["pending"])
        return
    _status()


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""A class reading, made ready for the speed reader.

    python3 brain/tools/reading.py "case.pdf"          # what the fast read skips
    python3 brain/tools/reading.py "case.pdf" --text   # the text it reads

A reading is a School task worded "Read …" (school_brief's rule) whose file
sits in her class folder: named in a `File:` note under the task, or found by
its title. This reads the PDF on this Mac with pdftotext and no model. A
case or an article is the professor's material and reaches a model only when
she adds it to a guide (25 Sep); reading it to her one word at a time is not
that.

What comes out is the running text, with page numbers, running heads, pull
quotes, footnote markers and the appendices taken out, and a list of what the
fast read leaves behind: each exhibit, table or appendix with its page, and
the pictures. The page shows that list on the task before she starts, so a
chart the argument rests on is not something she finds out about in class.

Nothing is written into her class folder. The text is cached inside the brain
(school/.readings/, gitignored), keyed to the file's size and date.
"""

import hashlib
import json
import os
import re
import subprocess
import sys
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
BRAIN = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import school  # noqa: E402

CACHE = os.path.join(BRAIN, "school", ".readings")
VERSION = 5              # bump when the cleaning changes: old caches re-read
WPM = 320                # the speed reader's own default

READ_RX = re.compile(r"^(?:read|reading)\b", re.I)
FILE_NOTE_RX = re.compile(r"^(?:file|pdf)\s*:\s*(.+?)\s*$", re.I)

# A caption that names something to look at rather than read through.
CAPTION_RX = re.compile(
    r"^(appendix|annex|annexe|exhibit|figure|fig\.|chart|table|graph)"
    r"\s+([0-9]+|[IVX]+|[A-Z])\b\s*[:.\-–—]?\s*(.*)$", re.I)
# The credit line magazines print for their artwork: pictures on a page
# that carries one are the article's illustrations, not its evidence.
ART_RX = re.compile(r"^(about the (art|artist)|illustrations? by|photographs? by"
                    r"|artist\b|photo(graph)?:)", re.I)
ROMAN_RX = re.compile(r"^[ivxlc]+$", re.I)
# The small print on a case's cover or a reprint's last page.
BOILER_RX = re.compile(
    r"©|\bcopyright\b|all rights reserved|not to be (used|reproduced)"
    r"|may not be (digitized|photocopied|reproduced)|basis for class discussion"
    r"|\bcase (study )?(was|has been) (written|prepared|developed|compiled)"
    r"|this (business )?case was|authorized for use only|to order copies"
    r"|permission of the (owner|publisher)|permission is expressly granted"
    r"|harvard business publishing|hbsp\.harvard\.edu"
    r"|notice of use restrictions", re.I)
# A reprint number set into the last column: "HBR Reprint R2302F".
REPRINT_RX = re.compile(r"^(HBR )?Reprint [A-Z]?\d+[A-Z]?$")
SUFFIXES = ("tion", "tions", "sion", "ment", "ments", "ness", "ing", "ings",
            "ed", "es", "s", "ly", "ity", "ities", "ance", "ence", "able",
            "ible", "ure", "ures", "ive", "ives", "ary", "ous", "al", "er",
            "ers", "ist", "ists", "ize", "izes", "ise", "ture", "tive",
            "ical", "ically", "ship", "ful", "less", "ant", "ants", "ent",
            "ents", "age", "ages", "ism", "ogy", "ity")


# --------------------------------------------------------------------------
# which file a task means

_FILES = None


def _files():
    global _FILES
    if _FILES is None:
        try:
            _FILES = [f for f in school.files()
                      if f["name"].lower().endswith(".pdf")]
        except Exception:                                # noqa: BLE001
            _FILES = []
    return _FILES


def _words(s):
    return [w for w in re.findall(r"[a-z0-9]+", (s or "").lower())
            if len(w) >= 3 and w not in {"the", "and", "for", "with", "pdf"}]


def file_for(task):
    """The class file a reading task means, or None.

    A `File:` note wins. Without one, a file whose title words all appear
    in the task counts ("The hybrid start up.pdf" for 'Read "The Hybrid
    Start-up"'), and only when exactly one file fits: a guess between two
    is worse than no button."""
    text = task.get("text") or ""
    if not READ_RX.match(text.strip()):
        return None
    files = _files()
    for n in task.get("notes") or []:
        m = FILE_NOTE_RX.match(n)
        if not m:
            continue
        want = m.group(1).strip().strip("`\"'").lower()
        hits = [f for f in files if f["name"].lower() == want
                or f["rel"].lower() == want]
        return hits[0] if hits else None
    have = set(_words(text))
    fits = []
    for f in files:
        if school.is_slides(f["name"]) or "syllabus" in f["name"].lower():
            continue
        need = set(_words(os.path.splitext(f["name"])[0]))
        if need and need <= have and (len(need) >= 2
                                      or len(next(iter(need))) >= 4):
            fits.append(f)
    return fits[0] if len(fits) == 1 else None


def is_file_note(note):
    return bool(FILE_NOTE_RX.match(note or ""))


# --------------------------------------------------------------------------
# reading the PDF

def _lines(path):
    """Every line of the PDF with its page and box, from pdftotext's
    bounding-box output. Blocks are kept: they are the nearest thing a PDF
    has to paragraphs."""
    r = subprocess.run(["pdftotext", "-bbox-layout", path, "-"],
                       capture_output=True, text=True, timeout=120)
    if r.returncode != 0 or not r.stdout:
        return [], []
    # Control characters (a stray backspace in an HBR file) are not XML.
    xml = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", r.stdout)
    xml = re.sub(r"<!DOCTYPE[^>]*>", "", xml)
    xml = re.sub(r'\sxmlns="[^"]+"', "", xml, count=1)
    root = ET.fromstring(xml)
    out, pages = [], []
    for pno, page in enumerate(root.iter("page"), 1):
        pages.append((float(page.get("width")), float(page.get("height"))))
        for bno, block in enumerate(page.iter("block")):
            for line in block.iter("line"):
                ws = [(w.text or "", float(w.get("xMin")), float(w.get("xMax")))
                      for w in line.iter("word") if (w.text or "").strip()]
                text = " ".join(w[0] for w in ws).strip()
                if not text:
                    continue
                y0, y1 = float(line.get("yMin")), float(line.get("yMax"))
                out.append({"page": pno, "block": (pno, bno), "text": text,
                            "x0": float(line.get("xMin")),
                            "x1": float(line.get("xMax")),
                            "y0": y0, "h": round((y1 - y0) * 2) / 2,
                            "words": len(ws), "boxes": ws})
    return out, pages


def _spaced(ln):
    """A letter-spaced label: "E N T R E P R E N E U RS H I P"."""
    toks = ln["text"].split()
    return len(toks) >= 4 and sum(len(x) <= 2 for x in toks) >= len(toks) * 0.6


def _unspace(ln):
    """Put a letter-spaced line back together: the gaps between words are
    wider than the gaps between letters ("OM PA R ED WI TH" → "OMPARED
    WITH")."""
    bx = ln.get("boxes") or []
    if len(bx) < 2:
        return ln["text"]
    gaps = [b[1] - a[2] for a, b in zip(bx, bx[1:])]
    lo, hi = min(gaps), max(gaps)
    if hi < lo * 1.6:
        return "".join(b[0] for b in bx)
    cut = (lo + hi) / 2
    out = bx[0][0]
    for g, b in zip(gaps, bx[1:]):
        out += (" " if g > cut else "") + b[0]
    return out


def _caps_run(ln):
    """A section that opens in letter-spaced capitals mid-article: "A S TE
    CHNO LO GY B RE AKS down familiar barriers" → "As technology breaks
    down familiar barriers". None when the line doesn't open that way."""
    bx = ln.get("boxes") or []
    k = 0
    while k < len(bx) and re.fullmatch(r"[A-Z’']{1,5}", bx[k][0]):
        k += 1
    if k < 3 or k == len(bx) or sum(len(b[0]) <= 2 for b in bx[:k]) < 2:
        return None
    head = _unspace({"text": "", "boxes": bx[:k]}).lower()
    return head[:1].upper() + head[1:] + " " + " ".join(b[0] for b in bx[k:])


# Some slide exports map the "ti", "tt" and "ft" ligatures to stray
# characters: "Communica/on", "liXle", "organiza<on".
_LIG = re.compile(r"(?<=[a-z])[/<X>](?=[a-z])")


def _fix_ligatures(text):
    def one(m):
        w = m.group(0)
        if _in_dict(w.lower()) or not _LIG.search(w):
            return w
        for rep in ("ti", "tt", "ft", "fi", "fl", "ff", "ffi", "tf"):
            cand = _LIG.sub(rep, w)
            base = cand.lower()
            # The word list has stems, not inflections: "presenting" is
            # found as "present".
            if any(_in_dict(re.sub(suf, "", base)) for suf in
                   (r"$", r"(es|s)$", r"ing$", r"ed$", r"e?d$", r"ly$",
                    r"(ies)$", r"ings?$")):
                return cand
        return w
    return re.sub(r"[A-Za-z/<>]+", one, text)


def _images(path):
    """The pictures worth mentioning, per page, in square inches. Rules,
    bullets and logos the size of a stamp are left out."""
    try:
        r = subprocess.run(["pdfimages", "-list", path], capture_output=True,
                           text=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return {}
    big = {}
    for ln in r.stdout.splitlines()[2:]:
        c = ln.split()
        if len(c) < 14 or c[2] != "image":
            continue
        try:
            w, h, xp, yp = int(c[3]), int(c[4]), float(c[12]), float(c[13])
        except ValueError:
            continue
        area = (w / max(xp, 1)) * (h / max(yp, 1))
        if area >= 4:
            big.setdefault(int(c[0]), []).append(round(area, 1))
    return big


_DICT = None


def _in_dict(word):
    global _DICT
    if _DICT is None:
        try:
            with open("/usr/share/dict/words", encoding="utf-8") as f:
                _DICT = {w.strip().lower() for w in f}
        except OSError:
            _DICT = set()
    return word.lower() in _DICT


def _join(a, b):
    """Two lines of one paragraph. A hyphen at the end of the first is a
    word broken for the column ("busi-" "ness") unless the halves are a
    compound that keeps it ("start-" "up")."""
    if a.endswith("-") and not a.endswith("--") and b[:1].islower():
        left = re.search(r"([A-Za-z]+)-$", a)
        right = re.match(r"([a-z]+)", b)
        if left and right:
            whole = left.group(1) + right.group(1)
            if _in_dict(whole) or right.group(1) in SUFFIXES \
                    or (len(right.group(1)) > 3 and not _in_dict(right.group(1))
                        and not _in_dict(left.group(1))):
                return a[:-1] + b
        return a + b
    return a + " " + b


def _norm(s):
    return re.sub(r"[^a-z]+", " ", (s or "").lower()).strip()


def analyse(path):
    """The reading's running text and what it leaves out. Cached."""
    st = os.stat(path)
    key = hashlib.sha1(os.path.realpath(path).encode()).hexdigest()[:16]
    cpath = os.path.join(CACHE, key + ".json")
    try:
        with open(cpath, encoding="utf-8") as f:
            got = json.load(f)
        if (got.get("v") == VERSION and got.get("size") == st.st_size
                and got.get("mtime") == int(st.st_mtime)):
            return got
    except (OSError, ValueError):
        pass
    res = _analyse(path)
    res.update({"v": VERSION, "size": st.st_size, "mtime": int(st.st_mtime)})
    try:
        os.makedirs(CACHE, exist_ok=True)
        tmp = cpath + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(res, f)
        os.replace(tmp, cpath)
    except OSError:
        pass
    return res


def _analyse(path):
    lines, pages = _lines(path)
    images = _images(path)
    npages = len(pages)
    if not lines:
        return {"text": "", "words": 0, "pages": npages, "skipped": [],
                "pictures": [], "art": False, "scanned": True}

    # The body's type size: the height most of the words are set in.
    weight = {}
    for ln in lines:
        weight[ln["h"]] = weight.get(ln["h"], 0) + ln["words"]
    body_h = max(weight, key=weight.get)

    # Running heads and feet: the same words on many pages.
    seen = {}
    for ln in lines:
        k = re.sub(r"\d+", "", _norm(ln["text"]))
        if k:
            seen.setdefault(k, set()).add(ln["page"])
    furniture = {k for k, ps in seen.items()
                 if len(ps) >= max(3, npages * 0.3)}

    # What there is to look at: captions, by page. A caption inside a
    # sentence ("[Appendix 2: Details …]") is a pointer, not the thing.
    captions, art = [], False
    for i, ln in enumerate(lines):
        t = ln["text"]
        if ART_RX.match(t):
            art = True
        m = CAPTION_RX.match(t)
        if m and ln["words"] <= 16 and not t.rstrip().endswith((",", ";")):
            label = t
            nxt = lines[i + 1] if i + 1 < len(lines) else None
            if (nxt and nxt["block"] == ln["block"] and len(label) < 60
                    and not CAPTION_RX.match(nxt["text"])):
                label += " " + nxt["text"]
            captions.append({"i": i, "page": ln["page"],
                             "what": m.group(1).capitalize(),
                             "label": label[:110].rstrip(" :")})

    # Appendices at the back are where the read stops: the first one that
    # stands as a heading in the second half, and everything after it.
    cut = len(lines)
    for c in captions:
        if (c["what"] in ("Appendix", "Annex", "Annexe", "Exhibit")
                and c["page"] > npages / 2):
            cut = c["i"]
            break

    # Blocks: how wide, how many lines. The body column is the width most
    # body-sized words are set in; a box of text much narrower than that,
    # several lines long, is a sidebar ("Idea in Brief"), not the argument.
    blocks = {}
    for ln in lines:
        b = blocks.setdefault(ln["block"], {"x0": ln["x0"], "x1": ln["x1"],
                                            "n": 0, "words": 0})
        b["x0"], b["x1"] = min(b["x0"], ln["x0"]), max(b["x1"], ln["x1"])
        b["n"] += 1
        b["words"] += ln["words"] if ln["h"] == body_h else 0
    wide = {}
    for b in blocks.values():
        wid = round((b["x1"] - b["x0"]) / 10) * 10
        wide[wid] = wide.get(wid, 0) + b["words"]
    col = max(wide, key=wide.get) if wide else 0
    # Slides are set in many sizes and are all furniture-free "body": a
    # landscape deck with few words a page keeps every size but the title's.
    deck = (pages and pages[0][0] > pages[0][1]
            and len(lines) and sum(ln["words"] for ln in lines) / max(npages, 1) < 150)
    lo, hi = (0.6, 3.0) if deck else (0.85, 1.25)

    def sidebar(ln):
        b = blocks[ln["block"]]
        return (not deck and b["n"] >= 3 and col
                and (b["x1"] - b["x0"]) < col * 0.5)

    def heading(ln):
        # A section heading set larger than the body, in capitals — the
        # pull quotes are larger still and in sentence case.
        letters = re.sub(r"[^A-Za-z]", "", ln["text"])
        return (blocks[ln["block"]]["n"] == 1 and ln["words"] <= 12
                and body_h * 1.25 < ln["h"] <= body_h * 1.8
                and letters.isupper())

    # The magazine opening: a drop cap and a letter-spaced lead-in before
    # the first body line ("C" + "OM PA R ED WI TH" → "Compared with").
    lead = {}
    for i, ln in enumerate(lines[:cut]):
        if (_spaced(ln) and i and len(lines[i - 1]["text"]) == 1
                and lines[i - 1]["text"].isupper()
                and lines[i - 1]["h"] >= body_h * 2
                and lines[i - 1]["page"] == ln["page"]):
            words = (lines[i - 1]["text"] + _unspace(ln)).lower()
            lead[i] = words[:1].upper() + words[1:]

    # The first real paragraph: a body-sized block of three lines or more.
    # What comes before it on the cover (author lines, the art credit) is
    # dropped; what a case prints there (the dateline) is not, because a
    # case's first block is its first paragraph.
    start = 0
    for i, ln in enumerate(lines[:cut]):
        b = blocks[ln["block"]]
        if (not deck and ln["h"] == body_h and b["n"] >= 3
                and (b["x1"] - b["x0"]) >= col * 0.7):
            start = i
            break

    sidebars, kept = [], []
    for i, ln in enumerate(lines[:cut]):
        t = ln["text"]
        if i in lead:
            kept.append(dict(ln, text=lead[i], block=("lead",)))
            continue
        if i < start:
            continue
        if not (body_h * lo <= ln["h"] <= body_h * hi) and not heading(ln):
            continue
        if re.sub(r"\d+", "", _norm(t)) in furniture:
            continue
        if (re.fullmatch(r"[\d\s.,–-]+", t) or ROMAN_RX.match(t)
                or REPRINT_RX.match(t)):
            continue
        if _spaced(ln):
            continue
        if CAPTION_RX.match(t) and ln["words"] <= 16:
            continue
        if _caps_run(ln):
            ln = dict(ln, text=_caps_run(ln))
        if sidebar(ln):
            if not sidebars or sidebars[-1]["page"] != ln["page"]:
                sidebars.append({"page": ln["page"], "label": _box_title(
                    lines, i)})
            continue
        kept.append(ln)

    # Paragraphs: a block's lines joined; a block that stops mid-sentence
    # runs on into the next (a column or a page broke it, not the author).
    # A one-line block is a heading or a dateline and stands alone.
    paras, cur, prev = [], "", None
    for ln in kept:
        if cur and ln["block"] != prev:
            # A one-line block is a heading or a dateline when what follows
            # starts a sentence; "…Go Green. [Appendix" + "3: …]" is not.
            one_line = (prev != ("lead",) and blocks[prev]["n"] == 1
                        and ". " not in cur[-120:]
                        and re.match(r"[A-Z“\"‘]", ln["text"]))
            if (re.search(r"[.!?:\"”’)]$", cur) or cur.isupper() or one_line
                    or (deck and ln["page"] != prev[0])):
                paras.append(cur)
                cur = ln["text"]
            else:
                cur = _join(cur, ln["text"])
        else:
            cur = _join(cur, ln["text"]) if cur else ln["text"]
        prev = ln["block"]
    if cur:
        paras.append(cur)

    # A pull quote repeats a sentence of the body; the body keeps it. The
    # small print a case or a reprint carries (who wrote it, copyright,
    # licence) is not the reading.
    normed = [_norm(p) for p in paras]
    text_paras = []
    for i, p in enumerate(paras):
        n = normed[i]
        if BOILER_RX.search(p):
            continue
        if len(n.split()) >= 6 and any(
                j != i and n in normed[j] and len(normed[j]) > len(n)
                for j in range(len(paras))):
            continue
        # A bullet would flash on its own as a "word"; a semicolon pauses.
        p = re.sub(r"^\s*[•▪◦●■]\s*", "", p)
        p = re.sub(r"\s*[•▪◦●■]\s+", "; ", p)
        text_paras.append(_fix_ligatures(p))

    # Pictures: those under a caption belong to it; the rest are listed.
    capt_pages = {c["page"] for c in captions}
    skipped = []
    for c in captions:
        if c["i"] < cut and c["what"] not in ("Exhibit", "Figure", "Fig.",
                                              "Chart", "Table", "Graph"):
            continue
        kind = ("picture" if c["page"] in images else
                "table" if c["what"] == "Table" or _dense(lines, c) else
                "chart")
        skipped.append({"page": c["page"], "label": c["label"], "kind": kind})
    pictures = [{"page": p, "count": len(a)} for p, a in sorted(images.items())
                if p not in capt_pages]
    text = "\n\n".join(text_paras)
    return {"text": text, "words": len(text.split()), "pages": npages,
            "skipped": skipped, "pictures": pictures, "art": art,
            "sidebars": sidebars, "scanned": False}


def _box_title(lines, i):
    """What a sidebar is called: the short capitals line just above it
    ("I DE A I N BR IE F" → "Idea in brief"), else its first words."""
    for j in range(i - 1, max(-1, i - 4), -1):
        ln = lines[j]
        if ln["page"] != lines[i]["page"]:
            break
        t = _unspace(ln) if _spaced(ln) else ln["text"]
        if t.isupper() and len(t) <= 40:
            return t[:1] + t[1:].lower()
    return " ".join(lines[i]["text"].split()[:5]) + "…"


def _dense(lines, cap):
    """A caption followed by lots of small words on its page is a table."""
    n = sum(ln["words"] for ln in lines[cap["i"] + 1:]
            if ln["page"] == cap["page"])
    return n >= 40


# --------------------------------------------------------------------------
# what the page shows

def _pages(ps):
    ps = sorted(set(ps))
    if not ps:
        return ""
    if len(ps) == 1:
        return "p.%d" % ps[0]
    if ps == list(range(ps[0], ps[-1] + 1)):
        return "p.%d–%d" % (ps[0], ps[-1])
    return "p." + ", ".join(str(p) for p in ps)


def summary(f):
    """What the task row needs: minutes, and the warning in two lengths
    (a chip, and the sentence behind it)."""
    try:
        a = analyse(f["path"])
    except Exception:                                    # noqa: BLE001
        return None
    if not a.get("words"):
        return {"rel": f["rel"], "words": 0, "minutes": 0, "chip": "",
                "warn": "This PDF has no text layer (a scan), so there is "
                        "nothing to speed-read.", "kind": "warn"}
    sk, pics = a.get("skipped") or [], a.get("pictures") or []
    chip, warn, kind = "", "", ""
    if sk:
        chip = "skips %s" % _pages(s["page"] for s in sk)
        def item(s):
            m = re.match(r"(\S+ \S+?)\s*[:.\-–—]\s*(.+)$", s["label"])
            head, what = (m.group(1), m.group(2)) if m else (s["label"], "")
            return "%s (%s, p.%d)%s" % (head, s["kind"], s["page"],
                                        ", " + what if what else "")
        warn = "Skipped by the fast read: %s." % "; ".join(item(s) for s in sk)
        kind = "warn"
    npic = sum(p["count"] for p in pics)
    if npic:
        where = _pages(p["page"] for p in pics)
        if a.get("art"):
            line = ("%d picture%s (%s) are the article's artwork, not "
                    "charts." % (npic, "" if npic == 1 else "s", where))
        else:
            line = ("%d picture%s without a caption (%s): the fast read "
                    "skips them, so glance at those pages."
                    % (npic, "" if npic == 1 else "s", where))
        warn = (warn + " " + line).strip()
        if not chip:
            chip = ("%d illustration%s" if a.get("art") else
                    "%d picture%s") % (npic, "" if npic == 1 else "s")
            kind = "" if a.get("art") else "warn"
    return {"rel": f["rel"], "words": a["words"],
            "minutes": max(1, round(a["words"] / WPM)),
            "chip": chip, "warn": warn, "kind": kind}


def _allowed(rel):
    """A class file the brain already lists, and nothing else: the page
    names a file by its place in the class folder, never by a path."""
    rel = (rel or "").strip()
    if not rel or school.is_confidential(rel):
        raise ValueError("not a class reading")
    for f in _files():
        if f["rel"] == rel:
            return f
    raise ValueError("that file is not in the class folder any more")


def serve(rel):
    """The speed reader's text for one reading, on her click."""
    f = _allowed(rel)
    a = analyse(f["path"])
    s = summary(f) or {}
    return {"ok": True, "text": a.get("text", ""), "words": a.get("words", 0),
            "warn": s.get("warn", ""), "kind": s.get("kind", "")}


def open_file(rel):
    """Open the PDF itself, for the pages the fast read skips."""
    f = _allowed(rel)
    if sys.platform == "darwin":
        subprocess.run(["open", "--", f["path"]], check=False)
    return {"ok": True}


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        print(__doc__.strip().split("\n\n")[0])
        return
    want = args[0].lower()
    hits = [f for f in _files() if want in f["name"].lower()
            or want in f["rel"].lower()]
    if not hits:
        sys.exit("No class PDF matches %r." % args[0])
    f = hits[0]
    a = analyse(f["path"])
    if "--text" in sys.argv:
        print(a["text"])
        return
    s = summary(f) or {}
    print("%s: %d pages, %d words, ~%d min at %d wpm"
          % (f["rel"], a["pages"], a["words"], s.get("minutes", 0), WPM))
    for k in a["skipped"]:
        print("  skips p.%d  %s  (%s)" % (k["page"], k["label"], k["kind"]))
    for p in a["pictures"]:
        print("  picture%s on p.%d" % ("s" if p["count"] > 1 else "", p["page"]))
    print("  chip: %s\n  warn: %s" % (s.get("chip"), s.get("warn")))


if __name__ == "__main__":
    main()

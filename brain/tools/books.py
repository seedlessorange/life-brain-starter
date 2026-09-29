#!/usr/bin/env python3
"""Read a book and write down what's in it worth using.

    python3 brain/tools/books.py --list
    python3 brain/tools/books.py --read mom-test
    python3 brain/tools/books.py --read mom-test --lens "pitching the jury"

The books came with the entrepreneurship specialization, plus whatever
shelf she points it at, and nobody has a term in which to read ten books. This reads one properly — section by
section, in order, nothing skipped — and writes what it found into
brain/school/books/, so the book is available at the moment it is needed
rather than in the ideal world where it was read in September.

It is not a summary. A summary of High Output Management is worth nothing;
what's worth something is the six things in it that change how you run a
team of five MBAs for ten weeks. So every section is read against a lens —
by default the deeptech project she is actually running — and the output
ends in things to do, not things to know.

Each section is one small no-tool call, routed by llm.py — Sonnet on her
config, because this is reading and judgement rather than string work. A
whole book is a few dozen of those against the subscription, so read them
one at a time rather than starting eight at midnight. The books themselves
are never modified, and nothing is written outside the brain.
"""

import argparse
import html
import json
import os
import re
import sys
import zipfile
from datetime import date
from urllib.parse import unquote
from xml.etree import ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
BRAIN = os.path.dirname(HERE)
sys.path.insert(0, HERE)

OUT_DIR = os.path.join(BRAIN, "school", "books")

TARGET_CHUNK = 12000       # characters per model call — a chapter, roughly
MAX_CHUNKS = 28            # a ceiling, so a 900-page book stays affordable
MIN_CHUNK = 2500           # below this it is a title page, not a chapter

# What Venture is, in the words a class presentation would use — no more.
# The Mom Test guide was written without this and invented a Venture that
# sold to pharma R&D and semiconductor fabs. Deliberately limited to what the
# company is for, who the team is testing as buyers, and who does what: the
# guides apply a book to the project, they are not the place to restate it.
VENTURE = (
    "The class venture: describe here what it builds, for "
    "whom, and who on the team does what."
)

# The second kind of guide: the book on its own terms. No project, no "use
# it" — the concepts defined as the author defines them, and his own examples
# kept whole, so the book can be learned rather than mined.
GENERAL_LENS = (
    "someone learning this book properly. She wants the concepts, the "
    "author's own definitions and the examples he actually uses — not advice "
    "for a project of her own."
)

GENERAL_ACCURACY = (
    "Accuracy: every story, number, name, company and quote must come from "
    "the source exactly as it is there. Never add a figure, a price, a "
    "duration or a detail the source does not give, and never change whose "
    "story it is. Do not apply the book to any reader's work, company or "
    "studies, and do not invent a project for her: this guide is about the "
    "book. Where the author's evidence is thin or the claim is contested, "
    "say so plainly."
)

DEFAULT_LENS = (
    "an MBA student in her final term, with about six hours a week "
    "for her deeptech project. " + VENTURE
)

# The rule the first Mom Test guide broke: it turned the author's own
# half-million-dollar lesson about never asking to see customers' lawyers into
# "a lawyer validation startup", and added a $50 price nobody mentioned.
ACCURACY = (
    "Accuracy: every story, number, name, company and quote must come from the "
    "source exactly as it is there. Never add a figure, a price, a duration or "
    "a detail the source does not give, and never change whose story it is. "
    "When you apply an idea to Venture, say so plainly ('For Venture, ...' "
    "or 'Imagine ...') and keep it to what Venture actually does. All you "
    "know about Venture is the description above: don't name real companies, "
    "tools, conferences or agencies as its customers, competitors or channels, "
    "don't give it capabilities the description doesn't (rogue waves, a "
    "resolution, a price), and never write as if the team has decided "
    "something (a beachhead, a revenue plan) - put that as a question for her."
)


# --------------------------------------------------------------------------
# finding the books

def _school():
    import school
    return school


def shelves():
    """Where books live: this term's folder, plus any shelf she named.

    Her marketing books sit in a Business Books folder beside the term, not
    inside it, and a reading pile the tool cannot see is a reading pile that
    never gets read. Config: school.shelves, each a path relative to the
    class folder or an absolute one."""
    sc = _school()
    out = [sc.term_root()]
    for extra in (sc._config().get("school", {}).get("shelves") or []):
        p = os.path.expanduser(extra)
        if not os.path.isabs(p):
            p = os.path.join(sc.root(), p)
        if os.path.isdir(p) and p not in out:
            out.append(p)
    return out


def books():
    """Every book on the shelves the reader can open: epub, and the older
    Kindle .mobi — three of the pile only ever came in that format. Where a
    book is on the shelf both ways, the epub is the one read."""
    found, seen_paths = [], set()
    for base in shelves():
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = [d for d in dirnames if not d.startswith(".")]
            for fn in filenames:
                if not fn.lower().endswith((".epub", ".mobi")):
                    continue
                full = os.path.join(dirpath, fn)
                if full in seen_paths:
                    continue
                seen_paths.add(full)
                title, author = _title_author(fn)
                found.append({
                    "slug": _slug(title),
                    "title": title,
                    "author": author,
                    "path": full,
                    "done": os.path.exists(os.path.join(
                        OUT_DIR, _slug(title) + ".md")),
                    "general": os.path.exists(os.path.join(
                        OUT_DIR, _slug(title) + "-general.md")),
                })
    epubs = {b["slug"] for b in found if b["path"].lower().endswith(".epub")}
    found = [b for b in found if b["path"].lower().endswith(".epub")
             or b["slug"] not in epubs]
    return sorted(found, key=lambda b: b["title"].lower())


def _slug(s):
    s = re.sub(r"[^a-z0-9]+", "-", s.lower())
    return re.sub(r"-+", "-", s).strip("-")[:40]


def _title_author(filename):
    """Library exports name files "Title -- Author -- Year -- Publisher".
    Everything after the first separator is provenance nobody needs."""
    stem = os.path.splitext(filename)[0]
    # The other export shape: "Title (Author) (Z-Library)". Left alone, the
    # distributor rode into the title, the slug and the guide's heading.
    stem = re.sub(r"\s*\((?:z-library|libgen|annas archive)\)\s*$", "",
                  stem, flags=re.I).strip()
    tail = ""
    m = re.search(r"\s*\(([^()]{3,60})\)\s*$", stem)
    if m and "--" not in stem:
        tail = m.group(1).strip()
        stem = stem[:m.start()].strip()
    parts = [p.strip() for p in stem.split("--")]
    title = parts[0].strip(" _")
    # "Title_ subtitle", "Title: subtitle", and in the .mobi exports
    # "Title - subtitle".
    title = re.split(r"[_:]\s|\s-\s", title)[0].strip()
    author = ""
    if len(parts) > 1:
        author = _clean_author(parts[1])
    elif tail:
        author = _clean_author(tail)
    return title or stem, author


def _clean_author(raw):
    """"Oakley, Geoffrey A_" as a person would write it: "Geoffrey A. Oakley".

    Library exports put the surname first, use an underscore where a full
    stop was, and sometimes append a distributor after a semicolon."""
    a = raw.split(";")[0]
    a = re.sub(r"\b(19|20)\d\d\b", "", a)
    a = re.sub(r"(?<=\b[A-Z])_", ".", a).replace("_", " ")
    a = " ".join(a.split()).strip(" ,")
    if a.count(",") == 1:
        last, first = [x.strip() for x in a.split(",")]
        if first and last and " " not in last:
            a = "%s %s" % (first, last)
    return a


def find(needle):
    """One book, by slug or by any distinctive word in the title."""
    n = needle.lower().strip()
    all_ = books()
    for b in all_:
        if b["slug"] == n:
            return b
    hits = [b for b in all_ if n in b["slug"] or n in b["title"].lower()]
    if len(hits) == 1:
        return hits[0]
    if not hits:
        raise ValueError("no book matches %r — try --list" % needle)
    raise ValueError("%r matches several: %s"
                     % (needle, ", ".join(b["slug"] for b in hits)))


# --------------------------------------------------------------------------
# reading an epub — zipped xhtml, in the order the spine says

def _strip(xhtml):
    x = re.sub(r"(?is)<(script|style|head)[^>]*>.*?</\1>", " ", xhtml)
    x = re.sub(r"(?i)</(p|div|h[1-6]|li|br)\s*>", "\n", x)
    x = re.sub(r"<[^>]+>", " ", x)
    x = html.unescape(x)
    x = re.sub(r"[ \t ]+", " ", x)
    return re.sub(r"\n\s*\n\s*\n+", "\n\n", x).strip()


def sections(path):
    """The book's documents in reading order: [(name, text), ...]."""
    if path.lower().endswith(".mobi"):
        return _mobi_sections(path)
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        # container.xml points at the package file, which holds the spine.
        opf_path = None
        try:
            root = ET.fromstring(z.read("META-INF/container.xml"))
            for el in root.iter():
                if el.tag.endswith("rootfile") and el.get("full-path"):
                    opf_path = el.get("full-path")
                    break
        except (KeyError, ET.ParseError, OSError):
            pass
        if not opf_path:
            opf_path = next((n for n in names if n.lower().endswith(".opf")),
                            None)

        order, titles = [], {}
        if opf_path:
            try:
                opf = ET.fromstring(z.read(opf_path))
                base = os.path.dirname(opf_path)
                ids = {}
                for el in opf.iter():
                    if el.tag.endswith("item") and el.get("id"):
                        ids[el.get("id")] = el.get("href", "")
                for el in opf.iter():
                    if el.tag.endswith("itemref") and el.get("idref"):
                        href = ids.get(el.get("idref"), "")
                        if not href:
                            continue
                        full = os.path.normpath(
                            os.path.join(base, unquote(href))).replace("\\", "/")
                        if full in names:
                            order.append(full)
            except (KeyError, ET.ParseError, OSError):
                order = []
        if not order:
            order = sorted(n for n in names
                           if n.lower().endswith((".xhtml", ".html", ".htm")))

        # The table of contents gives the chapters their real names. EPUB 2
        # keeps it in an .ncx (navPoint/navLabel/content), EPUB 3 in a
        # nav.xhtml of ordinary links. Both are in the wild, often in the
        # same file, so both are read.
        for nav in [n for n in names
                    if n.lower().endswith((".ncx", "nav.xhtml", "toc.xhtml"))]:
            try:
                raw = z.read(nav).decode("utf-8", "replace")
            except (KeyError, OSError):
                continue
            pairs = [(href, label) for label, href in re.findall(
                r"<navLabel>\s*<text>(.*?)</text>\s*</navLabel>\s*"
                r'<content[^>]+src="([^"]+)"', raw, re.I | re.S)]
            pairs += re.findall(
                r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', raw, re.I | re.S)
            for href, label in pairs:
                key = os.path.basename(unquote(href.split("#")[0]))
                text = " ".join(_strip(label).split())[:90]
                if text and key and key not in titles:
                    titles[key] = text

        out = []
        for n in order:
            try:
                text = _strip(z.read(n).decode("utf-8", "replace"))
            except (KeyError, OSError):
                continue
            if len(text) < 200:
                continue
            out.append((titles.get(os.path.basename(n), ""), text))
    return out


# --------------------------------------------------------------------------
# reading a .mobi — a Palm database of compressed text records, one long
# html document cut into chapters by its own table of contents

def _mobi_trailing(rec, flags):
    """Bytes of index data a record carries after its text. Each entry
    stores its size backwards from the record's end; left in, they come
    out of the decompressor as garbage mid-sentence."""
    def entry(size):
        shift = result = 0
        while size > 0:
            v = rec[size - 1]
            result |= (v & 0x7F) << shift
            shift += 7
            size -= 1
            if v & 0x80 or shift >= 28:
                break
        return result
    n, f = 0, flags >> 1
    while f:
        if f & 1:
            n += entry(len(rec) - n)
        f >>= 1
    if flags & 1:                      # a character split across records
        n += (rec[len(rec) - n - 1] & 0x3) + 1
    return n


def _palmdoc(data):
    """PalmDOC compression: literals, runs, and back-references."""
    out, i = bytearray(), 0
    while i < len(data):
        c = data[i]
        i += 1
        if 1 <= c <= 8:
            out += data[i:i + c]
            i += c
        elif c < 0x80:
            out.append(c)
        elif c >= 0xC0:
            out += b" " + bytes([c ^ 0x80])
        else:
            c = (c << 8) | data[i]
            i += 1
            dist, n = (c >> 3) & 0x7FF, (c & 7) + 3
            for _ in range(n):
                out.append(out[-dist])
    return bytes(out)


def _mobi_html(path):
    """The book's whole text as bytes, and its encoding. None for a file
    it cannot read: encrypted (a Kindle purchase), or the rarer HUFF/CDIC
    compression."""
    import struct
    with open(path, "rb") as f:
        d = f.read()
    if d[60:68] != b"BOOKMOBI":
        return None, None
    n = struct.unpack(">H", d[76:78])[0]
    offs = [struct.unpack(">I", d[78 + 8 * i:82 + 8 * i])[0]
            for i in range(n)] + [len(d)]
    r0 = d[offs[0]:offs[1]]
    comp, _, _, nrec, _, crypt = struct.unpack(">HHIHHH", r0[:14])
    if crypt or comp not in (1, 2):
        return None, None
    hlen, _, codepage = struct.unpack(">III", r0[20:32])
    flags = struct.unpack(">H", r0[0xF2:0xF4])[0] if hlen >= 0xE4 else 0
    text = bytearray()
    for i in range(1, min(nrec, n - 1) + 1):
        rec = d[offs[i]:offs[i + 1]]
        rec = rec[:len(rec) - _mobi_trailing(rec, flags)]
        text += _palmdoc(rec) if comp == 2 else rec
    return bytes(text), ("utf-8" if codepage == 65001 else "cp1252")


def _mobi_sections(path):
    """Chapters, cut where the table of contents points.

    A contents link is `<a filepos=N>` with N a byte offset into the text.
    Only forward links with words in them count: the contents page sits
    before the chapters, while footnotes and the index link to page
    numbers and chapter headings link back up. Everything before the first
    chapter is the cover and the contents page itself."""
    raw, enc = _mobi_html(path)
    if not raw:
        return []
    links = []
    for m in re.finditer(
            rb"<a[^>]*filepos=[\"']?0*(\d+)[\"']?[^>]*>(.*?)</a>", raw, re.S | re.I):
        pos = int(m.group(1))
        label = " ".join(_strip(m.group(2).decode(enc, "replace")).split())
        if m.start() < pos < len(raw) \
                and len(re.findall(r"[^\W\d_]", label)) >= 3:
            links.append((pos, label))
    # A label on many links is navigation ("Click here to jump to a
    # summary"), not a chapter name.
    seen = {}
    for _, label in links:
        seen[label] = seen.get(label, 0) + 1
    names = {}
    for pos, label in links:
        have = names.setdefault(pos, []) if seen[label] < 3 else []
        if seen[label] < 3 and label not in have:
            have.append(label)
    names = {p: v for p, v in names.items() if v}
    cuts = sorted(names)
    if not cuts:
        # No usable contents: pagebreaks if there are any, else one long
        # text that chunks() will cut at paragraph edges.
        cuts = [m.start() for m in re.finditer(rb"<mbp:pagebreak", raw)] or [0]
    out = []
    for a, b in zip(cuts, cuts[1:] + [len(raw)]):
        text = _strip(raw[a:b].decode(enc, "replace"))
        if len(text) < 200:
            continue
        out.append((": ".join(names.get(a, []))[:90], text))
    return out


def chunks(secs):
    """Sections grouped into model-sized pieces, in order. Front matter and
    the index are dropped — an acknowledgements page costs the same as a
    chapter and teaches nothing."""
    junk = re.compile(
        r"^(cover|title page|copyright|contents|table of contents|"
        r"acknowledg|about the (author|publisher)|index|notes|endnotes|bibliograph|"
        r"praise for|also by|dedication|colophon|permissions)", re.I)
    keep = [(t, x) for t, x in secs if not junk.match((t or "").strip())]
    if not keep:
        keep = secs

    # Size the chunk to the book, so a 650-page book still fits the ceiling
    # without any of it being dropped. A long chapter is split rather than
    # truncated — a truncated chapter is the failure that looks like success.
    total = sum(len(t) for _, t in keep)
    target = max(TARGET_CHUNK, -(-total // MAX_CHUNKS))
    hard = int(target * 1.5)

    out, buf, names = [], "", []

    def flush():
        if buf:
            out.append((" / ".join(names[:2]) or "—", buf))

    for title, text in keep:
        if title:
            names.append(title)
        # A half-full buffer plus a whole chapter overflows the ceiling the
        # split below is there to enforce. Close the buffer first.
        if buf and len(buf) + len(text) > hard:
            flush()
            buf, names = "", ([title] if title else [])
        # Break a long chapter at paragraph edges, never mid-sentence.
        while len(text) > hard:
            cut = text.rfind("\n\n", target, hard)
            if cut < 0:
                cut = text.rfind(" ", target, hard)
            if cut < 0:
                cut = hard
            head, text = text[:cut], text[cut:].lstrip()
            buf = (buf + "\n\n" + head).strip() if buf else head
            flush()
            buf, names = "", ([title + " (cont.)"] if title else [])
        buf = (buf + "\n\n" + text).strip() if buf else text
        if len(buf) >= target:
            flush()
            buf, names = "", []
    if len(buf) >= MIN_CHUNK:
        flush()
    elif buf and out:
        out[-1] = (out[-1][0], out[-1][1] + "\n\n" + buf)
    return out


# --------------------------------------------------------------------------
# the read

SECTION_SYSTEM = (
    "You extract what is usable from a book, for one specific reader. You "
    "never pad, never praise the book, never write a preamble. If a passage "
    "is filler, you say less rather than inventing substance."
)


def read(slug, lens=None, force=False, verbose=True, general=False):
    import llm
    b = find(slug)
    import school
    if school.is_confidential(b["path"]):
        return {"failed": b["title"],
                "why": "that filename is on the confidential list"}
    lens = lens or (GENERAL_LENS if general else DEFAULT_LENS)
    rule = GENERAL_ACCURACY if general else ACCURACY
    out = os.path.join(OUT_DIR,
                       b["slug"] + ("-general.md" if general else ".md"))
    if os.path.exists(out) and not force:
        return {"skipped": out, "why": "already read — pass --force to redo"}

    pieces = chunks(sections(b["path"]))
    if not pieces:
        return {"failed": b["title"],
                "why": "no readable text in that file — an encrypted Kindle "
                       "book can't be read"}

    # Reading the sections is the expensive half — twenty minutes of small
    # calls — and the synthesis at the end is one big call that can time out.
    # Three books lost a full read that way on 24 Sep, so the notes are
    # cached the moment they exist and a re-run picks them up.
    cache = os.path.join(BRAIN, ".book-notes",
                         b["slug"] + ("-general" if general else "") + ".json")
    notes, total_in, total_out = _cached_notes(cache, len(pieces)), 0, 0
    for i, (name, text) in enumerate(pieces[len(notes):], len(notes) + 1):
        if verbose:
            print("  %2d/%d  %s" % (i, len(pieces), (name or "—")[:56]),
                  flush=True)
        r = llm.complete(
            "books",
            "Reader: %s\n\n"
            "Below is section %d of %d of %r by %s.\n\n"
            % (lens, i, len(pieces), b["title"], b["author"] or "the author")
            + ("Write, in markdown:\n"
               "- **What it says** — the argument, 2-4 bullets, specific not "
               "generic. Keep the author's own terms and any numbers.\n"
               "- **The example** — the case, study or story the section "
               "uses, named, with what it is meant to show. Omit this "
               "heading if the section has none.\n\n"
               if general else
               "Write, in markdown:\n"
               "- **What it says** — the argument, 2-4 bullets, specific not "
               "generic. Keep the author's own terms and any numbers.\n"
               "- **Use it** — 1-3 things this reader could do differently. "
               "Omit this heading entirely if the section gives her nothing.\n\n")
            + "No heading of your own, no preamble, under 200 words.\n\n"
            "%s\n\n"
            "SECTION:\n%s" % (rule, text),
            system=SECTION_SYSTEM, timeout=150)
        notes.append((name, (r.get("text") or "").strip()))
        _save_notes(cache, len(pieces), notes)
        u = r.get("usage") or {}
        total_in += u.get("input_tokens") or 0
        total_out += u.get("output_tokens") or 0

    if verbose:
        print("  synthesising…", flush=True)
    joined = "\n\n".join("### %s\n%s" % (n or "—", t) for n, t in notes)
    shape = ("## The argument\n"
             "Five lines. What the book claims, why it thinks so.\n\n"
             "## The vocabulary\n"
             "Every term the book coins or redefines, one line each, defined "
             "the way the author defines it. This is the part someone who has "
             "not read the book needs most.\n\n"
             "## The ten things worth remembering\n"
             "A numbered list. Keep the author's own names for things.\n\n"
             "## The examples\n"
             "The book's own cases, studies and stories — named, with what "
             "each one is there to show. Keep his numbers.\n\n"
             "## Where it is thin\n"
             "Where the evidence is weak, the claim is contested by other "
             "work, or the material has dated. If it holds up, say that.\n\n"
             "## Read these pages for real\n"
             "2-4 sections worth reading in the book itself, and why.\n"
             if general else
             "## The argument\n"
             "Five lines. What the book claims, why it thinks so. If you "
             "disagree with the book or it is dated, say so in one line.\n\n"
             "## The ten things worth remembering\n"
             "A numbered list. Each one concrete enough to act on. Keep the "
             "author's own names for things.\n\n"
             "## What this changes for her\n"
             "3-6 bullets, each a specific change to what she does in the "
             "next ten weeks. Name the deliverable or the moment it applies "
             "to. If the book genuinely changes nothing for her, say that "
             "instead of inventing.\n\n"
             "## Read these pages for real\n"
             "2-4 sections worth reading in the book itself, and why.\n")
    r = llm.complete(
        "books",
        "Reader: %s\n\n"
        "These are section notes from %r by %s, in order:\n\n%s\n\n"
        "Now write, in markdown, no preamble:\n\n%s\n%s"
        % (lens, b["title"], b["author"] or "the author", joined[:90000],
           shape, rule),
        system=SECTION_SYSTEM, timeout=420)
    u = r.get("usage") or {}
    total_in += u.get("input_tokens") or 0
    total_out += u.get("output_tokens") or 0

    os.makedirs(OUT_DIR, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        f.write("# %s\n\n" % b["title"])
        if b["author"]:
            f.write("*%s*\n\n" % b["author"])
        f.write("Read %s, %d sections. %s\n\n---\n\n"
                % (date.today().isoformat(), len(pieces),
                   "The book on its own terms." if general
                   else "Read for: " + lens))
        f.write((r.get("text") or "").strip() + "\n\n---\n\n")
        f.write("## Section by section\n\n")
        for n, t in notes:
            f.write("### %s\n\n%s\n\n" % (n or "—", t))

    try:
        os.remove(cache)               # the guide is written; the scratch goes
    except OSError:
        pass
    if not general:
        _mark_done(b)
    return {"wrote": out, "sections": len(pieces),
            "provider": r.get("provider"),
            "tokens_in": total_in, "tokens_out": total_out}


def _cached_notes(path, n_pieces):
    """Section notes from an earlier attempt at this same book and mode."""
    try:
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
    except (OSError, ValueError):
        return []
    if d.get("pieces") != n_pieces:
        return []                      # the book was re-split; start over
    return [(x[0], x[1]) for x in d.get("notes") or []][:n_pieces]


def _save_notes(path, n_pieces, notes):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"pieces": n_pieces,
                   "notes": [[n, t] for n, t in notes]}, f)
    os.replace(tmp, path)


def _mark_done(b):
    """Tick the book off in the reading pile so the list stays true."""
    p = os.path.join(BRAIN, "school", "books.md")
    try:
        with open(p, encoding="utf-8") as f:
            s = f.read()
    except OSError:
        return
    key = b["title"].split(":")[0].strip()[:24]
    out = []
    for row in s.splitlines():
        if row.startswith("|") and key.lower() in row.lower() \
                and row.rstrip().endswith("| — |"):
            row = row.rstrip()[:-4] + "| [read](books/%s.md) |" % b["slug"]
        out.append(row)
    with open(p, "w", encoding="utf-8") as f:
        f.write("\n".join(out) + "\n")


# --------------------------------------------------------------------------
# cli

def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--read", metavar="BOOK")
    ap.add_argument("--lens", default="")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--general", action="store_true",
                    help="the book on its own terms: concepts, vocabulary "
                         "and the author's examples, applied to nothing")
    ap.add_argument("--sections", metavar="BOOK",
                    help="show how it would split the book, no model call")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    if a.sections:
        b = find(a.sections)
        cs = chunks(sections(b["path"]))
        print("%s — %d sections, %d chars" % (
            b["title"], len(cs), sum(len(t) for _, t in cs)))
        for i, (n, t) in enumerate(cs, 1):
            print("  %2d  %-58s %6d" % (i, (n or "—")[:58], len(t)))
        return
    if a.read:
        r = read(a.read, lens=a.lens or None, force=a.force,
                 general=a.general)
        print(json.dumps(r, indent=2))
        return
    bs = books()
    if a.json:
        print(json.dumps(bs, indent=2))
        return
    if not bs:
        print("No books found on %s" % ", ".join(shelves()))
        return
    print("%d books on the shelves:\n" % len(bs))
    for b in bs:
        marks = [m for m, on in (("read", b["done"]),
                                 ("the book", b["general"])) if on]
        print("  %-22s %s%s" % (b["slug"], b["title"][:46],
                                "   ✓ " + " · ".join(marks) if marks else ""))
    print("\n  python3 brain/tools/books.py --read <name>")


if __name__ == "__main__":
    main()

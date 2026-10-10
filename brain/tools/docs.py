#!/usr/bin/env python3
"""What the brain made, in one list: the box's Files (28 Sep).

    python3 brain/tools/docs.py          # print the list

Drafts, transcripts, study guides and book notes, the Word files and PDFs
it wrote into the brain, and the markdown that changed lately in her project
folders. Her question was where to see a transcript or a new document, open
it and fix it; the answer used to be four places and mostly read-only.

The page never names a file by path. Every entry gets an id here, and
reading, editing and opening all go by id, looked up again in a fresh list.
Nothing outside this list can be read or opened through it: an endpoint
that took any path was a finding in the security review (security.md, 11).

Editing is Markdown inside brain/ only. Files in her project folders are
hers, and the brain never edits them (CLAUDE.md hard rule 3); those open in
their own app or in the Finder instead. The journal is private and never
listed.
"""

import hashlib
import os
import re
import subprocess
import sys
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
BRAIN = os.path.dirname(HERE)
sys.path.insert(0, HERE)

TEXT = (".md", ".txt")
# Types that open in their own app. Never a script, an app or a shortcut:
# `open` on those runs them.
OPENABLE = (".md", ".txt", ".docx", ".doc", ".pdf", ".xlsx", ".pptx", ".rtf",
            ".csv", ".html")
MAX_READ = 400_000          # characters shown in the reader
KIND_ORDER = ("Draft", "Transcript", "Guide", "Book notes", "Document",
              "Project file")


def _id(path):
    return hashlib.sha1(os.path.realpath(path).encode("utf-8")).hexdigest()[:16]


def _in_brain(path):
    return os.path.realpath(path).startswith(os.path.realpath(BRAIN) + os.sep)


def _private(path):
    rp = os.path.realpath(path)
    return rp.startswith(os.path.realpath(os.path.join(BRAIN, "journal")) + os.sep)


def _pretty(stem):
    # A name she typed ("2026 0927 … - Pre Work V2") stays as she typed it;
    # only a slug ("2026-09-26-class-notes-6") gets its dashes undone.
    if " " in stem:
        return stem.strip()
    stem = re.sub(r"^\d{4}-\d{2}-\d{2}-", "", stem)
    return re.sub(r"[-_]+", " ", stem).strip() or stem


def _title(path):
    """The name a document gives itself: an HTML page's <title> up to its
    dash, a Markdown file's first heading. Empty when it gives none."""
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            head = f.read(4000)
    except OSError:
        return ""
    if path.lower().endswith(".html"):
        m = re.search(r"<title>(.*?)</title>", head, re.S | re.I)
        if not m:
            return ""
        import html as H
        return H.unescape(m.group(1)).split(" \u2014 ")[0].strip()
    body = re.sub(r"^---\n.*?\n---\n", "", head, count=1, flags=re.S)
    m = re.search(r"^#\s+(.+)$", body, re.M)
    return m.group(1).strip().strip("*") if m else ""


def _book_where(path, course=""):
    """Every course book has two guides: read against the course, and the
    book on its own terms (the `-general` file). Say which."""
    alone = os.path.splitext(path)[0].endswith("-general")
    return " \u00b7 ".join(x for x in (course, "the book on its own" if alone
                                        else ("" if course else "against the course"))
                           if x)


def _frontmatter(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            head = f.read(1500)
    except OSError:
        return {}
    m = re.match(r"^---\n(.*?)\n---", head, re.S)
    out = {}
    for ln in (m.group(1).split("\n") if m else []):
        k, _, v = ln.partition(":")
        if v:
            out[k.strip().lower()] = v.strip()
    return out


def _entry(path, kind, label="", where=""):
    try:
        st = os.stat(path)
    except OSError:
        return None
    ext = os.path.splitext(path)[1].lower()
    inb = _in_brain(path)
    url = ""
    if ext == ".html" and inb:
        url = os.path.relpath(path, BRAIN).replace(os.sep, "/")
    return {"id": _id(path), "path": path,
            "name": label or _pretty(os.path.splitext(os.path.basename(path))[0]),
            "kind": kind, "where": where, "mtime": st.st_mtime,
            "when": datetime.fromtimestamp(st.st_mtime).strftime("%d %b %H:%M").lstrip("0"),
            "ext": ext, "text": ext in TEXT,
            "editable": inb and ext == ".md" and not _private(path),
            "openable": ext in OPENABLE, "url": url}


def _walk(rel, exts, skip=(), keep=()):
    root = os.path.join(BRAIN, rel)
    if not os.path.isdir(root):
        return
    for dp, dn, fn in os.walk(root):
        dn[:] = [d for d in dn if not d.startswith((".", "_")) and d not in skip]
        for f in fn:
            if f.startswith((".", "_", "~$")) and f not in keep:
                continue
            if os.path.splitext(f)[1].lower() in exts:
                yield os.path.join(dp, f)


def index(project_files=None, days=7):
    """Every document, newest first. `project_files` is serve.py's
    recent_source_files (passed in rather than imported: the server calls
    this from inside itself)."""
    out, seen = [], set()

    def add(e):
        if e and e["id"] not in seen and not _private(e["path"]):
            seen.add(e["id"])
            out.append(e)

    # Drafts: the messages, notes and documents Claude wrote for her.
    for p in _walk("drafts", (".md", ".docx", ".pdf", ".txt")):
        fm = _frontmatter(p) if p.endswith(".md") else {}
        label = fm.get("subject") or fm.get("task") or ""
        who = fm.get("person") or fm.get("to") or ""
        st = fm.get("status", "")
        add(_entry(p, "Draft", label,
                   " \u00b7 ".join(x for x in (("to " + who) if who else "",
                                                st if st in ("sent", "discarded") else "")
                                    if x)))
    # Transcripts: in the brain, and beside each recording in its project.
    try:
        import json
        import model as M
        with open(os.path.join(BRAIN, "config.json"), encoding="utf-8") as f:
            rooms = {r.get("slug"): r["name"] for r in M.all_rooms(json.load(f))}
    except Exception:                                   # noqa: BLE001
        rooms = {}
    # The job hunt's CVs and cover letters (career.py), outside git because
    # they carry her phone and email.
    for p in _walk(os.path.join("files", "cv"), (".docx",)):
        add(_entry(p, "Application", "", "job hunt"))
    for p in _walk("transcripts", TEXT):
        fm = _frontmatter(p)
        rec = os.path.splitext(fm.get("recording", ""))[0]
        mins = fm.get("minutes", "")
        try:
            mins = f"{round(float(mins))} min" if mins else ""
        except ValueError:
            mins = ""
        # A class recording says which class; the pass names it for the
        # session, so its heading is the better name than a timestamp.
        where = ((rooms.get(fm["room"]) or _pretty(fm["room"])) if fm.get("room")
                 else fm.get("class", ""))
        add(_entry(p, "Transcript", (_title(p) if fm.get("class") else "") or rec,
                   " \u00b7 ".join(x for x in (where, mins) if x)))
    try:
        import transcribe as TR
        for m in TR.meetings():
            t = m.get("transcript")
            if t and os.path.isfile(t):
                add(_entry(t, "Transcript",
                           os.path.splitext(m.get("name") or "")[0],
                           m.get("project") or ""))
    except Exception:                                   # noqa: BLE001
        pass
    # Study guides and the notes from reading the course books.
    for p in _walk(os.path.join("school", "guides"), (".md", ".html"),
                   keep=("_course.html",)):
        course = _title(os.path.join(os.path.dirname(p), "_course.html")) \
            or _pretty(os.path.basename(os.path.dirname(p)))
        if os.path.basename(p) == "_course.html":
            add(_entry(p, "Guide", course + ", the course guide"))
        else:
            add(_entry(p, "Guide", _title(p), _book_where(p, course)))
    for p in _walk(os.path.join("school", "books"), (".md",)):
        add(_entry(p, "Book notes", _title(p), _book_where(p)))
    # Other documents it wrote into the brain: minutes, briefs, Word files.
    for p in _walk("school", (".docx", ".pdf"),
                   skip=("decks", "notes", "guides", "books")):
        add(_entry(p, "Document"))
    # What changed lately in her project folders — read-only here.
    try:
        for f in (project_files(days=days) if project_files else []):
            if f.get("source") == "The brain" or _in_brain(f.get("path", "")):
                continue
            # The handoff is rewritten by every sync: always "new", never news.
            if os.path.basename(f.get("path", "")).lower() == "handoff.md":
                continue
            add(_entry(f["path"], "Project file", _title(f["path"]),
                       f.get("source") or ""))
    except Exception:                                   # noqa: BLE001
        pass
    # A draft she discarded is still hers to find, just not first.
    out.sort(key=lambda e: (e["where"].endswith("discarded"), -e["mtime"]))
    return out[:200]


def extra():
    """What the find box opens that the Files list leaves out (8 Oct): the
    class files and the class notes. They are not news, so they stay out of
    Files, but a teacher's name she searches for lives in them."""
    out = []
    root = os.path.join(BRAIN, "school")
    for f in sorted(os.listdir(root)) if os.path.isdir(root) else []:
        p = os.path.join(root, f)
        if f.endswith(".md") and f != "README.md" and os.path.isfile(p):
            e = _entry(p, "School", _title(p))
            if e:
                e["tags"] = _fields(p)
                e["head"] = next((v for v in e["tags"]
                                  if v.lower().startswith("teacher")), "")
                out.append(e)
    for p in _walk(os.path.join("school", "notes"), (".md",)):
        e = _entry(p, "Class notes", _title(p))
        if e:
            out.append(e)
    return [e for e in out if not _private(e["path"])]


def _fields(path):
    """A class file's `- **Teacher:** …` lines, as "Teacher: …"."""
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            head = f.read(3000)
    except OSError:
        return []
    return [f"{k}: {re.sub(r'[*`]', '', v).strip()}"
            for k, v in re.findall(r"(?m)^- \*\*([^*:]+):\*\*\s*(.+)$", head)]


def reports():
    """The brain's own check reports (fix.py), newest ten (8 Oct). Opened
    from Fix and improve and from the box's attachment; never listed, since
    they are not news, and never edited: a report says what was found."""
    ps = sorted(_walk(os.path.join("files", "fix"), (".md",)), reverse=True)[:10]
    out = []
    for p in ps:
        e = _entry(p, "Brain check", _title(p))
        if e:
            e["editable"] = False
            out.append(e)
    return out


def find(fid, project_files=None):
    """The entry with this id, from a fresh list, or None."""
    if not re.fullmatch(r"[0-9a-f]{16}", fid or ""):
        return None
    return next((e for e in index(project_files) + extra() + reports()
                 if e["id"] == fid), None)


def summary(e):
    """What the page may know about an entry: never its path."""
    return {k: e[k] for k in ("id", "name", "kind", "where", "when", "ext",
                              "text", "editable", "openable", "url")}


W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def _docx_html(path):
    """A Word file, readable in the box: paragraphs, bold, headings, bullet
    and numbered lists, tables. Read on this Mac from the file's own XML;
    nothing else is needed and nothing leaves. Returns "" when it can't."""
    import html as H
    import zipfile
    import xml.etree.ElementTree as ET
    try:
        with zipfile.ZipFile(path) as z:
            root = ET.fromstring(z.read("word/document.xml"))
    except (zipfile.BadZipFile, KeyError, OSError, ET.ParseError):
        return ""
    body = root.find(W + "body")
    if body is None:
        return ""

    def runs(el):
        out = []
        for r in el.iter(W + "r"):
            b = r.find(W + "rPr/" + W + "b")
            bold = b is not None and b.get(W + "val") not in ("0", "false")
            t = ""
            for c in r:
                if c.tag == W + "t":
                    t += H.escape(c.text or "")
                elif c.tag == W + "tab":
                    t += " "
                elif c.tag == W + "br":
                    t += "<br>"
            if t:
                out.append(f"<b>{t}</b>" if bold and t.strip() else t)
        return "".join(out)

    html, lst, num = [], "", 0

    def close():
        nonlocal lst
        if lst:
            html.append(f"</{lst}>")
            lst = ""
    for el in body:
        if el.tag == W + "tbl":
            close()
            rows = []
            for tr in el.iter(W + "tr"):
                cells = ["<br>".join(runs(p) for p in tc.iter(W + "p"))
                         for tc in tr.iter(W + "tc")]
                rows.append("<tr>" + "".join(f"<td>{c}</td>" for c in cells) + "</tr>")
            html.append("<table>" + "".join(rows) + "</table>")
            continue
        if el.tag != W + "p":
            continue
        st = el.find(W + "pPr/" + W + "pStyle")
        style = (st.get(W + "val") if st is not None else "") or ""
        text = runs(el)
        if not text.strip():
            close()
            continue
        numbered = style.startswith("ListNumber")
        bullet = (style.startswith("ListBullet")
                  or (el.find(W + "pPr/" + W + "numPr") is not None and not numbered))
        if numbered or bullet:
            tag = "ol" if numbered else "ul"
            if lst != tag:
                close()
                if numbered:
                    # Word counts on across the paragraphs between items.
                    html.append(f'<ol start="{num + 1}">' if num else "<ol>")
                else:
                    html.append("<ul>")
                lst = tag
            num += numbered
            html.append(f"<li>{text}</li>")
            continue
        close()
        m = re.match(r"(?i)heading\s*(\d)|title", style)
        if m:
            lvl = min(4, 1 + int(m.group(1) or 1))
            html.append(f"<h{lvl}>{text}</h{lvl}>")
        else:
            html.append(f"<p>{text}</p>")
    close()
    return "".join(html)


def _guarded(e):
    """A file named as confidential is never opened by the brain, a preview
    included (CLAUDE.md, the one hard line in the school tools)."""
    try:
        import school
        return school.is_confidential(e["path"])
    except Exception:                                   # noqa: BLE001
        return True


def read(e):
    """The entry's text and, for Markdown, its rendered page."""
    import md as MD
    out = summary(e)
    if _guarded(e):
        out["html"] = ("<p class=\"asknoview\">This one is marked confidential, "
                       "so the brain doesn't open it. Open it in its own app.</p>")
        return out
    if e["ext"] == ".docx":
        out["html"] = _docx_html(e["path"])
        return out
    if not e["text"]:
        return out
    with open(e["path"], encoding="utf-8", errors="replace") as f:
        raw = f.read(MAX_READ + 1)
    cut = len(raw) > MAX_READ
    raw = raw[:MAX_READ]
    out["raw"] = raw if e["editable"] and not cut else ""
    if e["ext"] == ".md":
        body = raw
        if body.startswith("---\n"):          # the frontmatter is not reading
            end = body.find("\n---", 4)
            if end > 0:
                body = body[end + 4:]
        out["html"] = MD.render(body)
    else:
        import html as H
        out["html"] = "<pre class=\"askpre\">" + H.escape(raw) + "</pre>"
    if cut:
        out["html"] += "<p><i>Long file: the rest opens in its own app.</i></p>"
    return out


def save(e, text):
    """Write her edit back. Markdown inside brain/ only; git keeps the old
    version, so an edit can always be undone."""
    if not e["editable"]:
        raise ValueError("this file can't be edited here")
    if len(text) > MAX_READ:
        raise ValueError("too long to save from the page")
    tmp = e["path"] + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, e["path"])


def open_in_app(e):
    """Hand the file to its own app (Word, Preview, a text editor)."""
    if not e["openable"]:
        raise ValueError("this kind of file doesn't open from here")
    p = e["path"]
    if sys.platform == "darwin":
        subprocess.Popen(["open", p])
    elif os.name == "nt":
        os.startfile(p)                    # noqa — Windows only
    else:
        subprocess.Popen(["xdg-open", p])


if __name__ == "__main__":
    for e in index():
        print(f'{e["when"]:>13}  {e["kind"]:<12} {e["name"][:60]}'
              + (f'  · {e["where"]}' if e["where"] else ""))

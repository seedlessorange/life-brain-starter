#!/usr/bin/env python3
"""Take what you just downloaded into the brain.

    python3 brain/tools/grab.py                 # what landed in ~/Downloads lately
    python3 brain/tools/grab.py --take 1,3      # bring those two in
    python3 brain/tools/grab.py --take contract.pdf
    python3 brain/tools/grab.py --hours 72

The friction this removes: a document arrives by mail, lands in ~/Downloads
with a name you didn't choose, and getting it into the brain meant hunting for
it in a file picker. From the page it is now one click — Downloads, tick, ask.

It copies. The brain never writes outside its own folder, and deleting your
originals out of ~/Downloads would be exactly that; bin them yourself when you
are done with them.

This file also owns the limits on what may come in at all — the page's Attach
button reads them from here, so both doors have the same lock.
"""

import argparse
import os
import shutil
import subprocess
import sys
from datetime import date, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
BRAIN = os.path.dirname(HERE)
FILES = os.path.join(BRAIN, "files")

# Claude reads images up to ~5 MB; PDFs up to ~32 MB / 100 pages; up to 20
# attachments per request. These are the guard rails, not a preference.
MAX_IMAGE_BYTES = 5 * 1024 * 1024
MAX_DOC_BYTES = 32 * 1024 * 1024
MAX_ATTACHMENTS = 20
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
SAFE_EXT = IMAGE_EXT | {".pdf", ".txt", ".md", ".csv", ".docx", ".xlsx",
                        ".ics", ".json"}

# Overridable so a machine that keeps its downloads elsewhere still works.
DOWNLOADS = os.path.expanduser(os.environ.get("BRAIN_DOWNLOADS", "~/Downloads"))


def _ago(ts):
    """How long ago, in the words a person uses about their own downloads."""
    mins = max(0, int((datetime.now().timestamp() - ts) // 60))
    if mins < 1:
        return "just now"
    if mins < 60:
        return f"{mins} min ago"
    hours = mins // 60
    if hours < 24:
        return f"{hours} hour{'s' if hours > 1 else ''} ago"
    days = hours // 24
    return f"{days} day{'s' if days > 1 else ''} ago"


def _size(n):
    if n >= 1024 * 1024:
        return f"{n / (1024 * 1024):.1f} MB"
    return f"{max(1, n // 1024)} KB"


def recent(hours=48, limit=12):
    """The readable files that landed in ~/Downloads lately, newest first.

    Top level only: a downloaded folder is someone else's structure, and
    walking into it is how a picker turns into a file browser.
    """
    if not os.path.isdir(DOWNLOADS):
        return []
    cutoff = datetime.now().timestamp() - float(hours) * 3600
    out = []
    for name in os.listdir(DOWNLOADS):
        if name.startswith("."):
            continue
        path = os.path.join(DOWNLOADS, name)
        ext = os.path.splitext(name)[1].lower()
        # .download / .crdownload are still arriving — offering one means
        # copying half a file.
        if ext not in SAFE_EXT or not os.path.isfile(path):
            continue
        try:
            st = os.stat(path)
        except OSError:
            continue
        if st.st_mtime < cutoff:
            continue
        cap = MAX_IMAGE_BYTES if ext in IMAGE_EXT else MAX_DOC_BYTES
        out.append({"name": name, "bytes": st.st_size, "size": _size(st.st_size),
                    "when": _ago(st.st_mtime), "mtime": st.st_mtime,
                    "toobig": st.st_size > cap})
    out.sort(key=lambda f: f["mtime"], reverse=True)
    return out[:limit]


def docx_twin(target):
    """Claude's Read tool has no Word parser, so every session handed a .docx
    re-derived one from unzip and XML in front of her. Convert once on the way
    in (textutil ships with macOS) and hand the session the text twin; the
    original stays next to it. Returns the path to read, twin or original."""
    if os.path.splitext(target)[1].lower() != ".docx":
        return target
    twin = os.path.splitext(target)[0] + ".txt"
    try:
        subprocess.run(["textutil", "-convert", "txt", target, "-output", twin],
                       check=True, timeout=20, capture_output=True)
        return twin
    except Exception:
        return target          # the .docx path still works, just clumsier


def _free_name(folder, name):
    target = os.path.join(folder, name)
    n = 1
    while os.path.exists(target):
        stem, ext = os.path.splitext(name)
        target = os.path.join(folder, f"{stem}-{n}{ext}")
        n += 1
    return target


def take(names):
    """Copy the named downloads into brain/files/<today>/ and return their
    paths inside the brain — the same shape an upload returns, so an ask can
    carry them without caring which door they came through."""
    names = [n for n in (names or []) if n]
    if not names:
        raise ValueError("nothing picked")
    if len(names) > MAX_ATTACHMENTS:
        raise ValueError(f"Too many at once — {MAX_ATTACHMENTS} max. "
                         "Take the rest as a second batch.")
    folder = os.path.join(FILES, date.today().isoformat())
    os.makedirs(folder, exist_ok=True)
    saved = []
    for raw in names:
        # Only a plain name from that one folder: the page saying which path
        # to read is not a good enough reason to read a path.
        name = os.path.basename(str(raw))
        if not name or name.startswith("."):
            raise ValueError("that is not a file I can take")
        src = os.path.join(DOWNLOADS, name)
        if not os.path.isfile(src):
            raise ValueError(f"{name} is not in your Downloads any more")
        ext = os.path.splitext(name)[1].lower()
        if ext not in SAFE_EXT:
            raise ValueError(f"{name}: only documents and images, not {ext or 'that'}")
        size = os.path.getsize(src)
        cap = MAX_IMAGE_BYTES if ext in IMAGE_EXT else MAX_DOC_BYTES
        if size > cap:
            raise ValueError(f"{name} is {size // (1024 * 1024)} MB; the limit "
                             f"is {cap // (1024 * 1024)} MB")
        target = _free_name(folder, name)
        shutil.copy2(src, target)              # copy2 keeps the download's date
        saved.append(os.path.relpath(docx_twin(target), BRAIN))
    return saved


def main():
    ap = argparse.ArgumentParser(description="Take recent downloads into the brain")
    ap.add_argument("--hours", type=float, default=48,
                    help="how far back to look (default 48)")
    ap.add_argument("--take", default="",
                    help="numbers from the list, or file names, comma-separated")
    ap.add_argument("--all", action="store_true", help="take everything listed")
    a = ap.parse_args()

    files = recent(a.hours, limit=40)
    if not files:
        print(f"Nothing readable in {DOWNLOADS} in the last {a.hours:g} hours.")
        return 0

    if not a.take and not a.all:
        print(f"In {DOWNLOADS}, last {a.hours:g} hours:\n")
        for i, f in enumerate(files, 1):
            flag = "  (too big to attach)" if f["toobig"] else ""
            print(f"  {i:2}. {f['name']}  ·  {f['size']}  ·  {f['when']}{flag}")
        print("\nBring some in:  python3 brain/tools/grab.py --take 1,2")
        return 0

    if a.all:
        picked = [f["name"] for f in files if not f["toobig"]]
    else:
        picked = []
        for bit in a.take.split(","):
            bit = bit.strip()
            if not bit:
                continue
            if bit.isdigit() and 1 <= int(bit) <= len(files):
                picked.append(files[int(bit) - 1]["name"])
            else:
                picked.append(bit)

    saved = take(picked)
    print("Copied into the brain (your originals stay in Downloads):")
    for p in saved:
        print("  " + p)
    return 0


if __name__ == "__main__":
    sys.exit(main())

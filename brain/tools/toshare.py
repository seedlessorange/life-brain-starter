#!/usr/bin/env python3
"""Put a finished file where she can find it to send: the To share folder.

    python3 brain/tools/toshare.py FILE --kind CVs --title "CV - Acme"
    python3 brain/tools/toshare.py FILE --kind School          # title from the name
    python3 brain/tools/toshare.py cv.md --kind CVs --title "CV - Acme" --pdf
    python3 brain/tools/toshare.py --list                      # the folders

Her ask (7 Oct 2026): files she has to share were landing deep inside the
brain, and a file she has to hunt for is a file she cannot send. So every
finished thing someone else will read (a CV, a write-up, minutes, a deck)
gets a copy in `To share/<kind>/` at the top of the brain folder, named
`YYYY-MM-DD Title.ext` so the newest sorts last and the name says what it is.

A markdown file is turned into Word on the way (todocx.py): nobody can
upload a .md. The working copy stays where it was, so nothing that reads it
breaks. The folders come from config.json `to_share.folders`; the first
time one is used it is created. It never overwrites: a second copy on the
same day gets "(2)".

`--pdf` makes the copy a PDF instead (topdf.py: the page printed by Chrome),
for the applications and forms that take nothing else (7 Oct: her CV, after a
conversation failed twelve ways to make one).
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
BRAIN = os.path.dirname(HERE)
ROOT = os.path.dirname(BRAIN)
SHARE = os.path.join(ROOT, "To share")
DEFAULT_FOLDERS = ["CVs", "School", "Work", "Personal"]


def folders():
    try:
        with open(os.path.join(BRAIN, "config.json"), encoding="utf-8") as f:
            got = (json.load(f).get("to_share") or {}).get("folders")
        return [str(x) for x in got] if got else DEFAULT_FOLDERS
    except (OSError, ValueError):
        return DEFAULT_FOLDERS


def _title_from(path):
    """A readable title from a file name: dates and slugs out, words in."""
    name = os.path.splitext(os.path.basename(path))[0]
    name = re.sub(r"^\d{4}[- ]?\d{2}[- ]?\d{2}[ _-]*", "", name)
    name = re.sub(r"[-_]\d{4}-\d{2}-\d{2}$", "", name)
    name = re.sub(r"[_]+", " ", name).strip(" -")
    return name[:1].upper() + name[1:] if name else "Untitled"


def _free(path):
    if not os.path.exists(path):
        return path
    stem, ext = os.path.splitext(path)
    n = 2
    while os.path.exists(f"{stem} ({n}){ext}"):
        n += 1
    return f"{stem} ({n}){ext}"


def put(src, kind, title="", day=None, keep_name=False, pdf=False):
    """Copy one finished file into To share/<kind>/. Returns the new path."""
    src = os.path.abspath(os.path.expanduser(src))
    if not os.path.isfile(src):
        raise ValueError(f"no such file: {src}")
    # Renaming it here would take the marking out of its name, and with it
    # the only thing the guard can see (9 Oct audit).
    import school
    if school.is_confidential(src):
        raise ValueError("that file is marked confidential, so it stays out "
                         "of To share")
    match = [k for k in folders() if k.lower() == (kind or "").strip().lower()]
    if not match:
        raise ValueError(f"unknown kind {kind!r}; one of: {', '.join(folders())}")
    dest_dir = os.path.join(SHARE, match[0])
    os.makedirs(dest_dir, exist_ok=True)
    ext = os.path.splitext(src)[1].lower()
    out_ext = ".pdf" if pdf else ".docx" if ext == ".md" else ext
    if keep_name:
        name = os.path.splitext(os.path.basename(src))[0]
    else:
        clean = re.sub(r'[\\/:*?"<>|]+', " ", title or _title_from(src)).strip()
        name = f"{(day or date.today()).isoformat()} {clean}"
    dest = _free(os.path.join(dest_dir, name + out_ext))
    if pdf and ext != ".pdf":
        import topdf
        topdf.make(src, dest)
    elif ext == ".md":
        r = subprocess.run([sys.executable, os.path.join(HERE, "todocx.py"), src, dest],
                           capture_output=True, text=True, timeout=120)
        if r.returncode != 0 or not os.path.isfile(dest):
            raise RuntimeError("could not make the Word file: "
                               + (r.stderr or r.stdout).strip()[-300:])
    else:
        shutil.copy2(src, dest)
    return dest


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("file", nargs="?")
    ap.add_argument("--kind", help="which folder: " + ", ".join(folders()))
    ap.add_argument("--title", default="", help='e.g. "CV - Acme"')
    ap.add_argument("--date", default="", help="YYYY-MM-DD for the name (default today)")
    ap.add_argument("--keep-name", action="store_true",
                    help="keep the file's own name (a name a class requires)")
    ap.add_argument("--pdf", action="store_true",
                    help="make the copy a PDF (from .md, .docx, .html or .txt)")
    ap.add_argument("--list", action="store_true")
    a = ap.parse_args()
    if a.list or not a.file:
        print(SHARE)
        for k in folders():
            print("  " + k)
        return
    day = date.fromisoformat(a.date) if a.date else None
    try:
        print(put(a.file, a.kind, a.title, day, a.keep_name, a.pdf))
    except (ValueError, RuntimeError) as exc:
        sys.exit(str(exc))


if __name__ == "__main__":
    main()

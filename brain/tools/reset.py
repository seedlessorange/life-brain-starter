#!/usr/bin/env python3
"""Wipe the brain — a section or all of it — without ever deleting anything.

    python3 brain/tools/reset.py --list
    python3 brain/tools/reset.py habits goals            # preview (dry run)
    python3 brain/tools/reset.py habits goals --yes      # actually do it
    python3 brain/tools/reset.py --all --yes             # start fresh

Nothing is deleted, ever: current content moves to a timestamped folder under
brain/archive/, and the core files are reseeded with their own preamble (the
format guide above the first `## ` heading), so a fresh file still explains
itself. Git is snapshotted before and after, so even the archive step has an
undo. Runs the page rebuild at the end.

Without --yes this only PRINTS what would move — a safe preview.
"""

import argparse
import os
import shutil
import subprocess
import sys
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
BRAIN = os.path.dirname(HERE)
ROOT = os.path.dirname(BRAIN)

# section name -> (files or globs relative to brain/, reseed?)
# reseed=True: after archiving, write the file's own preamble back so the
# format guide survives the wipe. Directories just empty out.
SECTIONS = {
    "workstreams": (["workstreams.md"], True),
    "people":      (["people.md"], True),
    "habits":      (["habits.md"], True),
    "goals":       (["goals.md"], True),
    "season":      (["season.md"], True),
    "inbox":       (["inbox.md"], True),
    "next":        (["next.md"], True),
    "waiting":     (["waiting.md"], True),
    "today":       (["today.md"], True),
    "questions":   (["questions.md"], True),
    "queue":       (["queue/*.md"], False),          # keeps _index.md
    "rooms":       (["rooms/*.md"], False),          # per-room notes
    "daily":       (["daily/*.md"], False),          # session digests
    "drafts":      (["drafts/*.md"], False),
    "decisions":   (["decisions.md"], True),         # only when named explicitly
}
# --all takes everything EXCEPT decisions unless it is asked for by name —
# the decision log is the brain's memory of why things are the way they are.
ALL_DEFAULT = [s for s in SECTIONS if s != "decisions"]


def files_for(section):
    import glob
    pats, _ = SECTIONS[section]
    out = []
    for pat in pats:
        for fp in sorted(glob.glob(os.path.join(BRAIN, pat))):
            base = os.path.basename(fp)
            if section == "queue" and base.startswith("_"):
                continue
            if os.path.isfile(fp):
                out.append(fp)
    return out


def preamble(path):
    """Everything above the first `## ` heading — the file's own format
    guide — or a minimal frontmatter if the file never had one."""
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read()
    except OSError:
        return "---\nmaintained-by: you and claude, together\n---\n"
    head = []
    for line in text.split("\n"):
        if line.startswith("## "):
            break
        head.append(line)
    kept = "\n".join(head).rstrip()
    return (kept + "\n") if kept else \
        "---\nmaintained-by: you and claude, together\n---\n"


def snapshot(msg):
    try:
        subprocess.run(["git", "-C", ROOT, "add", "-A"],
                       capture_output=True, timeout=20)
        subprocess.run(["git", "-C", ROOT, "commit", "-m", msg],
                       capture_output=True, timeout=20)
    except Exception:
        pass


def main():
    ap = argparse.ArgumentParser(
        description="Archive-and-reseed parts of the brain. "
                    "Default is a dry run; nothing moves without --yes.")
    ap.add_argument("sections", nargs="*", help="which parts to wipe")
    ap.add_argument("--all", action="store_true",
                    help="every section except the decision log")
    ap.add_argument("--list", action="store_true", help="name the sections")
    ap.add_argument("--yes", action="store_true",
                    help="actually do it (otherwise: preview only)")
    args = ap.parse_args()

    if args.list or (not args.sections and not args.all):
        print("Sections:", "  ".join(sorted(SECTIONS)))
        print("Usage: reset.py <section...> [--yes]   or   --all [--yes]")
        print("Without --yes nothing moves — you get a preview.")
        return

    wanted = ALL_DEFAULT if args.all else args.sections
    bad = [s for s in wanted if s not in SECTIONS]
    if bad:
        sys.exit(f"Unknown section(s): {', '.join(bad)} — try --list")

    moves = {s: files_for(s) for s in wanted}
    total = sum(len(v) for v in moves.values())
    stamp = datetime.now().strftime("reset-%Y%m%d-%H%M%S")
    arch = os.path.join(BRAIN, "archive", stamp)

    for s in wanted:
        _, reseed = SECTIONS[s]
        what = ", ".join(os.path.relpath(f, BRAIN) for f in moves[s]) or "(nothing there)"
        print(f"{s:12} -> archive {what}" + ("  + reseed fresh" if reseed and moves[s] else ""))
    if not args.yes:
        print(f"\nDry run — nothing moved. {total} file(s) would go to "
              f"brain/archive/{stamp}/. Re-run with --yes to do it.")
        return
    if total == 0:
        print("Nothing to do.")
        return

    snapshot(f"before {stamp}: the state being wiped, kept forever")
    os.makedirs(arch, exist_ok=True)
    for s in wanted:
        _, reseed = SECTIONS[s]
        for fp in moves[s]:
            rel = os.path.relpath(fp, BRAIN)
            dst = os.path.join(arch, rel)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            head = preamble(fp) if reseed else None
            shutil.move(fp, dst)
            if head is not None:
                with open(fp, "w", encoding="utf-8") as f:
                    f.write(head)
    print(f"Moved {total} file(s) to brain/archive/{stamp}/ — nothing deleted.")

    for job in ("build.py", "map.py", "rooms.py"):
        try:
            subprocess.run([sys.executable, os.path.join(HERE, job)],
                           capture_output=True, timeout=60)
        except Exception:
            pass
    snapshot(f"after {stamp}: fresh start, old state under brain/archive/")
    print("Pages rebuilt. The old state is archived and in git history.")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Read the folders you actually work in, and write down what they say.

    python3 brain/tools/sync.py

This is the "live feed" half. Every folder listed in brain/config.json gets
read for unticked `- [ ]` items and for when it was last touched, and the
result is written to brain/synced.md — which is GENERATED, so never edit it.

Nothing in your project folders is deleted, and nothing you wrote is changed.
The one exception is deliberate: a project that keeps its own brain gets asked
to regenerate `brain/handoff.md`, its own generated fifteen-line summary, so
this sync reads something current instead of something remembered. No model
runs, and no other file is touched.

The point is not to mirror every task. It is to answer one question per
project: is anything happening here, and when did it last happen? A project
folder nobody has saved a file in for five weeks is the signal.
"""

import json
import os
import re
import subprocess
import sys
from datetime import date, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
BRAIN = os.path.dirname(HERE)
OUT = os.path.join(BRAIN, "synced.md")
# Last-known snapshot per source, committed to git so it travels between
# machines. synced.md itself is generated and git-ignored; this state is what
# lets the desktop show "Recipes, as the laptop last saw it" for a folder
# that only exists on the laptop, instead of a blank.
STATE = os.path.join(BRAIN, ".synced-state.json")

# Looked for at the top of each source folder when no explicit list is given.
DEFAULT_FILES = ["TODO.md", "TODOS.md", "TASKS.md", "NEXT.md", "todo.md",
                 "README.md", "CLAUDE.md", "notes.md"]

MAX_ITEMS_PER_SOURCE = 12      # a wall of 200 tasks is not a briefing
SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", "build",
             "dist", ".next", "target", ".gradle", "Pods"}


def load_config():
    try:
        with open(os.path.join(BRAIN, "config.json"), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def expand(p):
    return os.path.abspath(os.path.expanduser(os.path.expandvars(p)))


def git_last_commit(path):
    """When code was last committed here. The most honest 'last worked on'
    signal a project folder has, and free to ask for."""
    try:
        r = subprocess.run(["git", "-C", path, "log", "-1", "--format=%cI"],
                           capture_output=True, text=True, timeout=8)
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.strip()[:10]
    except Exception:
        pass
    return None


def newest_mtime(path, depth=2):
    """Most recent modification anywhere in the folder, ignoring build noise.
    Build output and dependency folders change without anyone doing any work,
    which is exactly the false 'this is active' signal we do not want."""
    newest = 0.0
    base_depth = path.rstrip(os.sep).count(os.sep)
    for root, dirs, files in os.walk(path):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith(".")]
        if root.count(os.sep) - base_depth >= depth:
            dirs[:] = []
        for fn in files:
            if fn.startswith("."):
                continue
            try:
                m = os.path.getmtime(os.path.join(root, fn))
                if m > newest:
                    newest = m
            except OSError:
                continue
    return newest or None


def open_items(path, files):
    """Unticked checkboxes, with the file they came from."""
    found = []
    for rel in files:
        fp = os.path.join(path, rel)
        if not os.path.isfile(fp):
            continue
        try:
            with open(fp, encoding="utf-8", errors="replace") as f:
                text = f.read()
        except OSError:
            continue
        for line in text.split("\n"):
            m = re.match(r"^\s*[-*]\s+\[ \]\s+(.*)$", line)
            if m and m.group(1).strip():
                found.append({"text": m.group(1).strip()[:160], "file": rel})
    return found


NEW_FILE_DAYS = 7
# Documents, not assets: a logo or a research dump is not a sign of progress.
DOC_EXT = {".docx", ".doc", ".md", ".pdf", ".pptx", ".key", ".xlsx", ".csv",
           ".txt", ".html", ".pages", ".numbers"}


def new_files(path, listed, today, days=NEW_FILE_DAYS, depth=3, cap=10):
    """Documents saved in a prose folder in the last week that are not on its
    `files:` list — one entry per name, whatever formats it was saved in.

    The watched list is frozen the day the source is added. Venture's was
    five files from 17 Sep, so the Session 2 minutes, recording and
    transcript of 23 Sep sat in the folder while the brain kept planning
    Session 2 and the Session 1 minutes it had already recorded as sent.
    A new file named for a meeting or deliverable is the cheapest evidence
    of progress there is; this names them so the morning plan can see them.
    Names only: nothing is opened. A subfolder two levels down that gained
    more than five (a research dump) is one entry, named with its count; the
    project's own folder never collapses, since that is where minutes land."""
    listed = {os.path.normpath(f) for f in listed}
    cutoff = datetime.now().timestamp() - days * 86400
    base_depth = path.rstrip(os.sep).count(os.sep)
    seen, per_dir = {}, {}
    for root, dirs, files in os.walk(path):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith(".")]
        if root.count(os.sep) - base_depth >= depth:
            dirs[:] = []
        for fn in files:
            if fn.startswith((".", "~$", "Backup of ")) or fn == "CLAUDE.md" \
                    or os.path.splitext(fn)[1].lower() not in DOC_EXT:
                continue
            fp = os.path.join(root, fn)
            if os.path.normpath(os.path.relpath(fp, path)) in listed:
                continue
            try:
                m = os.path.getmtime(fp)
            except OSError:
                continue
            if m < cutoff:
                continue
            stem = os.path.splitext(fn)[0]
            per_dir.setdefault(root, {})
            if m > per_dir[root].get(stem, 0):
                per_dir[root][stem] = m
    for root, stems in per_dir.items():
        if len(stems) > 5 and root.count(os.sep) - base_depth >= 2:
            seen[f"{os.path.basename(root)} folder, {len(stems)} new files"] = \
                max(stems.values())
        else:
            for stem, m in stems.items():
                seen[stem] = max(m, seen.get(stem, 0))
    out = sorted(seen.items(), key=lambda kv: -kv[1])
    return [(stem, datetime.fromtimestamp(m).date()) for stem, m in out[:cap]], \
        max(len(out) - cap, 0)


def candidate_files(path, src):
    if src.get("files"):
        return src["files"]
    return [f for f in DEFAULT_FILES if os.path.isfile(os.path.join(path, f))]


def refresh_handoff(path, src=None):
    """Ask a project that keeps its own brain to re-summarise itself.

    A repo running the brain-kit generates `brain/handoff.md` — its worry, its
    top actions, what is blocked on her — and that file is what this sync then
    reads. Regenerating it here rather than trusting it is the maintenance
    rule applied across the boundary: it refreshes when the page is built in
    that repo, but nobody should have to remember to build it.

    Free and safe by construction: the script runs no model, reads only that
    project's own markdown, and writes only that one file. A repo without it,
    or a failure of any kind, just leaves whatever is already on disk.

    Opt-in per source (`"handoff": true` in config.json), because this runs
    that folder's own code every twenty minutes: fine for her app repos,
    not for any folder something else can drop a brain/tools/ into.
    Downloads is refused outright for that reason."""
    if not (src or {}).get("handoff"):
        return False
    real = os.path.realpath(path)
    downloads = os.path.realpath(os.path.expanduser("~/Downloads"))
    if real == downloads or real.startswith(downloads + os.sep):
        return False
    # Never a folder inside the brain: config.json is writable by the
    # brain's own runs, and a source pointed at brain/drafts/x with its own
    # brain/tools/handoff.py was a way out of their sandbox.
    brain_root = os.path.realpath(os.path.join(HERE, "..", ".."))
    if real == brain_root or real.startswith(brain_root + os.sep):
        return False
    tool = os.path.join(path, "brain", "tools", "handoff.py")
    if not os.path.isfile(tool):
        return False
    try:
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
        r = subprocess.run(_handoff_fence(real) + [sys.executable, tool],
                           cwd=path, capture_output=True, text=True,
                           timeout=20, env=env)
        return r.returncode == 0
    except Exception:
        return False


def _handoff_fence(repo):
    """The handoff script is the repo's own code, and a Claude run working in
    that repo can rewrite it. So on a Mac it runs inside the system sandbox:
    no network, no Keychain, and the one file it exists to write. Checked
    28 Sep with a canary Keychain item: readable outside, not inside."""
    if sys.platform != "darwin" or not os.path.exists("/usr/bin/sandbox-exec"):
        return []
    home = os.path.realpath(os.path.expanduser("~"))
    q = lambda p: '"%s"' % p.replace("\\", "\\\\").replace('"', '\\"')
    profile = (
        "(version 1)(allow default)"
        "(deny network*)(allow network* (remote unix-socket))"
        '(deny mach-lookup (global-name-regex #"^com\\.apple\\.secur")'
        ' (global-name-regex #"^com\\.apple\\.trustd") (global-name "com.apple.ocspd"))'
        '(deny process-exec (literal "/usr/bin/security"))'
        "(deny file-read* (subpath %s) (subpath \"/Library/Keychains\"))"
        "(deny file-write*)"
        "(allow file-write* (literal %s) (subpath \"/private/var/folders\")"
        " (subpath \"/private/tmp\") (subpath \"/dev\"))"
        % (q(os.path.join(home, "Library", "Keychains")),
           q(os.path.join(repo, "brain", "handoff.md"))))
    return ["/usr/bin/sandbox-exec", "-p", profile]


def _load_state():
    try:
        with open(STATE, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _age_words(days):
    return "unknown" if days is None else (
        "today" if days == 0 else f"{days} day{'s' if days != 1 else ''} ago")


def sync():
    cfg = load_config()
    sources = cfg.get("sources", [])
    today = date.today()
    rows, blocks = [], []
    total_items = 0
    brains = 0
    missing = []
    stale = []
    prev_state = _load_state()
    state = {}

    for src in sources:
        name = src.get("name") or os.path.basename(src.get("path", "?"))
        path = expand(src.get("path", ""))
        if not os.path.isdir(path):
            # Not on this machine (the desktop, usually). Show the last
            # snapshot any machine took, marked stale, rather than a blank —
            # a project does not vanish because the laptop is closed.
            prev = prev_state.get(name)
            if not prev:
                missing.append((name, src.get("path", "")))
                continue
            stale.append(name)
            state[name] = prev
            last = prev.get("last")
            try:
                days = (today - date.fromisoformat(last)).days if last else None
            except ValueError:
                days = None
            rows.append(f"| {name} | {_age_words(days)} | "
                        f"{prev.get('items', 0)} | {last or '—'} |")
            blocks.append(f"### {name}")
            blocks.append(f"*not on this machine — as another machine last "
                          f"saw it, {prev.get('date', 'date unknown')}*")
            blocks.extend(prev.get("block", []))
            blocks.append("")
            continue

        fresh = refresh_handoff(path, src)
        files = candidate_files(path, src)
        items = open_items(path, files)
        total_items += len(items)
        if fresh:
            brains += 1

        commit = git_last_commit(path)
        mt = newest_mtime(path)
        mtime = datetime.fromtimestamp(mt).date().isoformat() if mt else None
        last = commit or mtime
        try:
            days = (today - date.fromisoformat(last)).days if last else None
        except ValueError:
            # One folder with a garbled git date must not kill the whole sync.
            days = None

        rows.append(f"| {name} | {_age_words(days)} | {len(items)} | {last or '—'} |")

        sblock = []
        detail = []
        if commit:
            detail.append(f"last commit {commit}")
        if mtime and mtime != commit:
            detail.append(f"a file changed {mtime}")
        detail.append(f"`{src.get('path', path)}`")
        sblock.append("*" + ", ".join(detail) + "*")
        # Prose folders only. A repo's commits are its progress signal, and
        # its new files are code.
        if src.get("files") and not commit:
            fresh_docs, more = new_files(path, files, today)
            if fresh_docs:
                sblock.append("New this week, not on the watched list: "
                              + "; ".join(f"{stem} ({d.day} {d.strftime('%b')})"
                                          for stem, d in fresh_docs)
                              + (f"; and {more} more" if more else ""))
        if items:
            shown = items[:MAX_ITEMS_PER_SOURCE]
            for it in shown:
                sblock.append(f"- [ ] {it['text']}")
            if len(items) > len(shown):
                sblock.append(f"- *...and {len(items) - len(shown)} more in that folder.*")
        else:
            where = ", ".join(f"`{f}`" for f in files) if files else "no checklist files"
            sblock.append(f"No open checkboxes found ({where}).")
        blocks.append(f"### {name}")
        blocks.extend(sblock)
        blocks.append("")
        # The commit date apart from the file date: model.py counts a commit
        # as work on the front, and a file date never (the brain writes
        # handoff files into these folders itself).
        state[name] = {"last": last, "commit": commit or "",
                       "items": len(items),
                       "date": today.isoformat(), "block": sblock}

    out = [
        "---",
        f"updated: {today.isoformat()}",
        "generated: true",
        "---",
        "",
        "## From your project folders",
        "",
        "Generated from the folders in `brain/config.json`. A read-only mirror: "
        "tick things where they live.",
        "",
    ]
    if rows:
        out += ["| Project | Last worked on | Open items | Date |",
                "|---|---|---|---|"] + rows + [""]
    if missing:
        out += ["**Folders listed in the config that do not exist "
                "(and no machine has synced them yet):**", ""]
        out += [f"- {n} — `{p}`" for n, p in missing] + [""]
    if not sources:
        out += ["Nothing configured yet. Add your project folders to the `sources` "
                "list in `brain/config.json` — the page re-reads them on its own "
                "every 20 minutes, or click the green dot in the header to sync now.",
                ""]
    out += blocks

    with open(OUT, "w", encoding="utf-8") as f:
        f.write("\n".join(out).rstrip() + "\n")
    # Only rewrite the state when it changed — it is committed to git, and
    # an idle rewrite every 20 minutes would churn history for nothing.
    if state != prev_state:
        try:
            with open(STATE, "w", encoding="utf-8") as f:
                json.dump(state, f, indent=1, ensure_ascii=False)
        except OSError:
            pass
    return len(sources) - len(missing) - len(stale), total_items, brains


if __name__ == "__main__":
    n, items, brains = sync()
    print(f"Read {n} folder{'s' if n != 1 else ''}, {items} open items"
          + (f", {brains} with their own brain" if brains else "")
          + f" -> {OUT}")
    try:
        sys.path.insert(0, HERE)
        import build
        build.build()
        print("Rebuilt the page.")
    except Exception as exc:
        print(f"(Page not rebuilt: {exc})")

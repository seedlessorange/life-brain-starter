"""What actually happened today, assembled from what the day left behind.

The brain does not watch her screen and never will. It does not need to: a
working day leaves marks in places that are already hers — commits in the
project folders, ticks in the plate, Touched dates, habit logs, drafts. This
reads those marks and says the day back to her.

The reason it exists: the evening check counted the three planned tasks and
nothing else, so a day spent entirely on TapGate — six commits, a draft
written, two chases closed — reported "none of the three moved today". That
is both demoralising and false, and it is the sentence most likely to make
someone stop opening the page.

Mechanical throughout. No model call, so it costs nothing and can run every
evening, on a laptop with no network, forever.

    python3 brain/tools/day.py            # the day, as a person would say it
    python3 brain/tools/day.py --json     # the same, for the page
    python3 brain/tools/day.py --date 2026-08-26
"""
import json
import os
import re
import subprocess
import sys
from datetime import date, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
BRAIN = os.path.dirname(HERE)
if HERE not in sys.path:
    sys.path.insert(0, HERE)


# The brain's own checkpoints, and the usual machine-made commits. None of
# them is a thing she chose to do.
SNAPSHOT = re.compile(
    r"^(pre-\w+ snapshot|morning run|night run|checkpoint|wip|auto[- ]|"
    r"snapshot\b|rebuild pages?)\b", re.I)


def _cfg():
    try:
        with open(os.path.join(BRAIN, "config.json"), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _git(path, *args, timeout=8):
    """Read-only git, never failing loudly: a folder that isn't a repo, or a
    repo mid-rebase, is a thing to skip, not a thing to crash the evening."""
    try:
        out = subprocess.run(("git", "-C", path) + args, capture_output=True,
                             text=True, timeout=timeout)
        return out.stdout if out.returncode == 0 else ""
    except Exception:
        return ""


def commits(day):
    """Commits landed in the tracked project folders on this date.

    The truest record of a building day, and one she never has to write down.
    Only her own: a repo with collaborators (or a vendored dependency's
    history) would otherwise report other people's work as hers.
    """
    since = f"{day.isoformat()} 00:00"
    until = f"{day.isoformat()} 23:59"
    me = (_git(BRAIN, "config", "user.email").strip()
          or _git(BRAIN, "config", "user.name").strip())
    out = []
    for src in _cfg().get("sources") or []:
        path = os.path.expanduser(src.get("path") or "")
        if not os.path.isdir(os.path.join(path, ".git")):
            continue
        args = ["log", "--no-merges", f"--since={since}", f"--until={until}",
                "--pretty=%H%x1f%an%x1f%ae%x1f%cd%x1f%s%x1f%b",
                "--date=format:%H:%M"]
        rows, assisted = [], 0
        for block in _git(path, *args).split("\n"):
            parts = block.split("\x1f")
            if len(parts) < 5:
                continue
            _, an, ae, at, subj = parts[:5]
            body = parts[5] if len(parts) > 5 else ""
            if me and me not in (an, ae):
                continue
            subj = subj.strip()
            # Snapshots are the brain checkpointing itself before a run. They
            # are bookkeeping, not a thing she did, and thirty of them bury
            # the eight commits that were actually the day's work.
            if SNAPSHOT.match(subj):
                continue
            # An agent commit still carries her name — every run commits as
            # her. The Claude trailer is the only honest way to tell "I built
            # this" from "I directed this", and the difference is worth
            # keeping: the report would otherwise credit her with thirty-six
            # commits she did not write.
            if "Claude" in body and "Co-Authored-By" in body:
                assisted += 1
            rows.append({"at": at, "subject": subj})
        if rows:
            rows.reverse()                       # morning first, like the day
            out.append({"project": src.get("name") or path, "commits": rows,
                        "assisted": assisted})
    out.sort(key=lambda p: -len(p["commits"]))
    return out


# Folders that are never a thing she did: dependency trees, build output,
# caches, version-control internals. Left in, a single `npm install` reports
# forty thousand files changed and buries the one spreadsheet that mattered.
SKIP_DIRS = {
    ".git", ".hg", ".svn", "node_modules", "__pycache__", ".venv", "venv",
    "env", ".mypy_cache", ".pytest_cache", ".ruff_cache", "dist", "build",
    ".next", ".nuxt", ".cache", ".parcel-cache", "target", "Pods",
    ".gradle", ".idea", ".vscode", "vendor", ".terraform", "coverage",
    ".DS_Store", "Library", ".Trash", ".expo", ".turbo", ".svelte-kit",
    "site-packages", ".tox", ".eggs", "bower_components", ".sass-cache",
}
# Files that change as a side effect of something else, or that nobody would
# call work. Lock files in particular move every time a tool runs.
SKIP_FILE = re.compile(
    r"(^\.|~\$|\.(pyc|pyo|log|tmp|swp|swo|lock|map|min\.js|min\.css)$"
    r"|^(package-lock\.json|yarn\.lock|pnpm-lock\.yaml|poetry\.lock|"
    r"Cargo\.lock|Gemfile\.lock|\.DS_Store)$)", re.I)
MAX_PER_PLACE = 400          # a folder louder than this is a tool, not a day

TICKABLE = ("workstreams.md", "today.md", "season.md", "people.md",
            "goals.md", "questions.md")


def ticked(day):
    """Items that went from open to done in the brain's own history today.

    A tick writes [x] but stamps no date, so the file cannot say WHEN. Git
    can: every change to the brain is committed, so the day's diff is an
    exact, dated record of what she closed. Anything not yet committed is
    read from the working tree, or the last hour of an evening would be
    missing from its own report.
    """
    since = f"{day.isoformat()} 00:00"
    until = f"{day.isoformat()} 23:59"
    # From the repo ROOT, not brain/: git resolves a pathspec against the
    # working directory, so "brain/workstreams.md" asked from inside brain/
    # names a file that does not exist — and a pathspec that matches nothing
    # returns an empty diff rather than an error, so this failed in silence.
    root = os.path.dirname(BRAIN)
    first = _git(root, "rev-list", "-n", "1", f"--before={since}",
                 "HEAD").strip()
    if not first:
        return []
    # Both ends of the day, not "the day's start until now". Diffing a past
    # date against the working tree reported every tick since, so yesterday
    # and the day before came back with the same list.
    ends = [first]
    if day == date.today():
        ends.append("")                      # working tree: the last hour counts
    else:
        last = _git(root, "rev-list", "-n", "1", f"--before={until}:59",
                    "HEAD").strip()
        if not last or last == first:
            return []
        ends.append(last)
    args = ["diff", "--unified=0"] + [x for x in ends if x] + ["--"]
    diff = _git(root, *args, *[os.path.join("brain", f) for f in TICKABLE],
                timeout=15)
    done, undone, cur = [], set(), ""
    for line in diff.split("\n"):
        if line.startswith("+++ b/"):
            cur = os.path.basename(line[6:])
            continue
        m = re.match(r"^([+-])\s*[-*]\s+\[([ xX])\]\s+(.*)$", line)
        if not m:
            continue
        text = re.sub(r"\s*\((?:due|waiting until|did|planned|with|when)[^)]*\)",
                      "", m.group(3)).strip()
        text = re.sub(r"\s*~\s*\d+h?\d*m?\b", "", text).strip()
        if not text:
            continue
        if m.group(1) == "+" and m.group(2).lower() == "x":
            done.append({"text": text, "file": cur})
        elif m.group(1) == "-" and m.group(2).lower() == "x":
            undone.add(text)
    # A line that was already [x] before today shows as +[x] whenever anything
    # else on it changed. Its matching -[x] is in the same diff, so dropping
    # those leaves only the ones that genuinely closed today.
    seen, out = set(), []
    for d in done:
        if d["text"] in undone or d["text"] in seen:
            continue
        seen.add(d["text"])
        out.append(d)
    # The same task lives in today's plan and on its workstream, and the
    # workstream copy usually grew an outcome note when it was ticked
    # ("… — approved, Twilio unblocked"). Exact matching misses that, so one
    # thing done showed up as two. Keep the copy that says more.
    out.sort(key=lambda d: -len(d["text"]))
    kept = []
    for d in out:
        low = d["text"].lower()
        if any(k["text"].lower().startswith(low[:max(len(low) - 4, 12)])
               for k in kept):
            continue
        kept.append(d)
    return kept


def _find_changed(root, day, budget=MAX_PER_PLACE):
    """Files under root last modified on `day`, pruned hard.

    `find` does this in C and returns in milliseconds on trees that take
    Python seconds to walk — this runs on every page build, so it has to be
    cheap enough that nobody notices it.
    """
    nxt = day.fromordinal(day.toordinal() + 1)
    prune = []
    for d in sorted(SKIP_DIRS):
        prune += ["-name", d, "-o"]
    cmd = (["find", "-L", root, "-maxdepth", "6",
            "("] + prune[:-1] + [")", "-prune", "-o",
           "-type", "f",
           "-newermt", day.isoformat(),
           "!", "-newermt", nxt.isoformat(),
           "-print"])
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=12)
        paths = [p for p in out.stdout.split("\n") if p.strip()]
    except Exception:
        return [], 0
    keep = []
    for p in paths:
        if SKIP_FILE.search(os.path.basename(p)):
            continue
        keep.append(p)
        if len(keep) > budget:
            break
    keep.sort(key=lambda p: os.path.getmtime(p) if os.path.exists(p) else 0)
    return keep, len(keep)


def files(day):
    """What changed on disk today, per place — the half of a working day that
    never reaches a commit.

    Three of her folders are not repositories at all: Faverolles, the HEC
    class content, the champagne dossier. A day spent on a spreadsheet for
    her father produced no commit, no tick and no Touched date, so the report
    said she had done nothing. Modification times are the only record that
    day leaves, and they are already on the disk.

    Inside a repo the commits already say it, so only UNCOMMITTED work is
    counted there — otherwise every file in a commit would be reported twice.
    """
    out, seen_roots = [], []
    places = []
    for src in _cfg().get("sources") or []:
        p = os.path.expanduser(src.get("path") or "")
        if os.path.isdir(p):
            places.append((src.get("name") or os.path.basename(p), p))
    # Anything else she asks it to watch. Desktop and Documents by default:
    # that is where a day of admin, a dossier or a deck actually happens.
    extra = ((_cfg().get("day") or {}).get("watch")
             if isinstance(_cfg().get("day"), dict) else None)
    if extra is None:
        extra = ["~/Desktop", "~/Documents"]
    for p in extra:
        p = os.path.expanduser(p)
        if os.path.isdir(p) and not any(os.path.samefile(p, q)
                                        for _, q in places
                                        if os.path.exists(q)):
            places.append((os.path.basename(p.rstrip("/")) or p, p))
    for name, path in places:
        # A folder already covered by one listed above it (Desktop/Faverolles
        # under Desktop) must not be counted in both.
        if any(path.startswith(r.rstrip("/") + "/") for r in seen_roots):
            continue
        # The repo is not always at the top of the folder she tracks: Perch's
        # lives one level down, in perch/. Missed, its whole source tree got
        # reported as loose files changed — 343 of them, which reads as chaos
        # rather than as an afternoon's work sitting uncommitted.
        repo = path if os.path.isdir(os.path.join(path, ".git")) else ""
        if not repo:
            try:
                kids = [os.path.join(path, k) for k in sorted(os.listdir(path))
                        if k not in SKIP_DIRS
                        and os.path.isdir(os.path.join(path, k, ".git"))]
            except OSError:
                kids = []
            repo = kids[0] if len(kids) == 1 else ""
        is_repo = bool(repo)
        if is_repo:
            path = repo
            # Working-tree changes only: committed work is already reported.
            dirty = [l[3:].strip().strip('"')
                     for l in _git(path, "status", "--porcelain").split("\n")
                     if l.strip()]
            paths = []
            for rel in dirty:
                full = os.path.join(path, rel)
                if not os.path.isfile(full) or SKIP_FILE.search(
                        os.path.basename(full)):
                    continue
                try:
                    if date.fromtimestamp(os.path.getmtime(full)) == day:
                        paths.append(full)
                except OSError:
                    pass
        else:
            paths, _ = _find_changed(path, day)
        seen_roots.append(path)
        if not paths:
            continue
        # "Changed" and "not yet committed" are different facts. In a repo the
        # committed work is already listed above, so a number here is work
        # still sitting in the working tree — worth saying in those words,
        # because it is also a nudge.
        out.append({"place": name, "n": len(paths),
                    "kind": "uncommitted" if is_repo else "changed",
                    "names": [os.path.relpath(p, path) for p in paths[-8:]]})
    out.sort(key=lambda p: -p["n"])
    return out


def touched(day):
    """Workstreams whose Touched date is today — the plate's own record of
    where her attention went, including work that produced no commit."""
    import model as M
    iso = day.isoformat()
    out = []
    for w in M.load():
        if not w.get("live"):
            continue
        t = w.get("touched")
        if (t.isoformat() if hasattr(t, "isoformat") else str(t or "")) == iso:
            out.append(w["name"])
    return out


def habits_done(day):
    import model as M
    return [h["name"] for h in M.load_habits(today=day)
            if day.isoformat() in (h.get("dates_list") or [])]


def drafts(day):
    """Drafts written today — the work that produced words rather than code."""
    out = []
    d = os.path.join(BRAIN, "drafts")
    for name in sorted(os.listdir(d)) if os.path.isdir(d) else []:
        if not name.endswith(".md"):
            continue
        try:
            with open(os.path.join(d, name), encoding="utf-8") as f:
                head = f.read(600)
        except OSError:
            continue
        m = re.search(r"^created:\s*(\d{4}-\d{2}-\d{2})", head, re.M)
        if m and m.group(1) == day.isoformat():
            # The draft's own name, never its task: line — the plan and the
            # week strip already say the task, and the evening card quoting
            # it back verbatim was a third copy of one sentence on screen.
            out.append(name[:-3].replace("-", " "))
    return out


def journaled(day):
    return os.path.exists(os.path.join(BRAIN, "journal",
                                       day.isoformat() + ".md"))


def gather(day=None):
    day = day or date.today()
    # An answered question is a whole paragraph — the question, then her
    # answer. Listed beside three-word tasks it buries them, and nine of them
    # is a wall. They keep their own line, as a count.
    tk = ticked(day)
    return {"date": day.isoformat(), "projects": commits(day),
            "files": files(day),
            "ticked": [t for t in tk if t["file"] != "questions.md"],
            "answered": sum(1 for t in tk if t["file"] == "questions.md"),
            "touched": touched(day),
            "habits": habits_done(day), "drafts": drafts(day),
            "journal": journaled(day)}


def as_text(d, phone=False):
    """The day said out loud. Evidence only — this reports, it never grades.

    Nothing here counts what she did NOT do: the plan already says that, and
    saying it twice in one evening is nagging with extra steps.
    """
    lines = []
    if d["projects"]:
        names = ", ".join(f"{p['project']} ({len(p['commits'])})"
                          for p in d["projects"][:4])
        lines.append(f"Worked on: {names}")
        if not phone:
            # The last few per project. A full day's log is a wall she will
            # not read at nine in the evening, and the point is recognition,
            # not an audit trail — git already is the audit trail.
            for p in d["projects"]:
                for c in p["commits"][-6:]:
                    lines.append(f"    {c['at']}  {p['project']} — {c['subject']}")
                if len(p["commits"]) > 6:
                    lines.append(f"    …and {len(p['commits']) - 6} earlier "
                                 f"in {p['project']}")
    if d.get("files"):
        ch = [p for p in d["files"] if p["kind"] == "changed"]
        un = [p for p in d["files"] if p["kind"] == "uncommitted"]
        if ch:
            lines.append("Files: " + ", ".join(
                f'{p["place"]} ({p["n"]})' for p in ch[:4]))
        if un:
            lines.append("Not committed yet: " + ", ".join(
                f'{p["place"]} ({p["n"]})' for p in un[:3]))
        if not phone:
            for p in d["files"]:
                for n in p["names"]:
                    lines.append(f"    {p['place']}/{n}")
                if p["n"] > len(p["names"]):
                    lines.append(f"    …and {p['n'] - len(p['names'])} more "
                                 f"in {p['place']}")
    if d["ticked"]:
        # Answered questions run long — a whole paragraph each. Cut them to
        # the length of a thing you recognise, which is all this needs to be.
        def short(t):
            s = t["text"]
            return s if len(s) <= 62 else s[:59].rstrip(" ,;—-") + "…"
        lines.append("Closed: " + "; ".join(short(t) for t in d["ticked"][:6])
                     + (f" (+{len(d['ticked']) - 6})" if len(d["ticked"]) > 6 else ""))
    if d.get("answered"):
        n = d["answered"]
        lines.append(f"Answered {n} open question{'s' if n > 1 else ''}")
    other = [w for w in d["touched"]
             if not any(w == p["project"] for p in d["projects"])]
    if other:
        lines.append("Also moved: " + ", ".join(other[:5]))
    if d["drafts"]:
        lines.append("Wrote: " + "; ".join(d["drafts"][:3]))
    if d["habits"]:
        lines.append("Kept: " + ", ".join(d["habits"]))
    if not lines:
        # A day with no marks is not a wasted day — it is a day that happened
        # away from the keyboard, which for her is usually the good kind.
        return ("Nothing landed in the files today. If the day went somewhere "
                "the computer cannot see, tell me and I'll file it.")
    return "\n".join(lines)


def main():
    args = sys.argv[1:]
    day = date.today()
    if "--date" in args:
        try:
            day = datetime.strptime(args[args.index("--date") + 1],
                                    "%Y-%m-%d").date()
        except Exception:
            pass
    d = gather(day)
    if "--json" in args:
        print(json.dumps(d, indent=1))
    else:
        print(as_text(d, phone="--phone" in args))


if __name__ == "__main__":
    main()

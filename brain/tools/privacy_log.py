#!/usr/bin/env python3
"""Where her words went: a hook every Claude run the brain starts carries.

    (a PostToolUse hook; run_policy.settings() adds it with the run's profile)
    python3 brain/tools/privacy_log.py --summary      # the last 7 days, plainly

For each file a run opened (Read, Grep, Glob) or a command named (Bash), it
records the KIND of material: journal, people, money, transcripts, drafts,
school, the rest of the brain, a project folder, or somewhere outside them.
Nothing else: no content, no file name, no command. Outside the named
folders it keeps only the top folder ("~/Documents"), which is what the
reading fence's dry run needs (PRIVACY-PLAN.md phase 2).

Only runs the brain starts carry it, so her own Claude Code sessions are
never logged (her call, 8 Oct: they stay as they are). Codex and Gemini runs
have no hooks; the page says "not tracked" for them.

Two uses on the Privacy page:

* **Proof.** Runs on a timer opening the journal should always read 0.
* **Tripwire.** A run on a timer that OPENED (a Read, Grep or Glob that
  succeeded; PostToolUse fires only then) a kind its level locks is written
  with `trip`, and the security alarm shows it (sentinel.py). A command that
  merely names a path is "named", never a trip: the sandbox refuses the read
  and the command still returns.

The log lives where no run can write it (run_policy.SERVER_STATE), and the
hook itself runs outside the run's sandbox. It never blocks: any failure
exits quietly with no output, because an "allow" here would override the
run's permission rules (the approve_gate lesson, 26 Sep).
"""

import hashlib
import json
import os
import re
import sys
from datetime import datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
BRAIN = os.path.dirname(HERE)
ROOT = os.path.dirname(BRAIN)
HOME = os.path.expanduser("~")
LOG = os.path.join(BRAIN, ".privacy-log.jsonl")
MAX_BYTES = 2_000_000
TIMER = ("scheduled",)            # the profiles runs on a timer use

# First match wins. Brain-relative prefixes.
KINDS = [
    # Not journal-trace.md: it is the neutral line per day the 7am plan is
    # told to read instead of the journal (/today step 9), so counting it as
    # the journal tripped the alarm every morning (9 Oct, a false alarm).
    # The locked kinds match privacy.py's LOCK_PATHS exactly, so the alarm
    # trips on what the fence locks and nothing else: the 7am plan reading
    # .people-digest.md (the stand-in it is told to read) or yesterday's
    # voice notes (never locked) raised a red card every morning (9 Oct
    # audit). Those count as the brain, and voice notes as their own kind.
    ("journal", ("brain/journal/",)),
    ("people", ("brain/people.md",)),
    ("money", ("brain/finance/",)),
    ("transcripts", ("brain/transcripts/",)),
    ("voice", ("brain/voice/", "brain/.voice/")),
    ("drafts", ("brain/drafts/",)),
    ("school", ("brain/school/",)),
]
LOCKS = {"transcripts": "lock_transcripts", "money": "lock_money",
         "people": "lock_people"}
SYSTEM = ("/usr/", "/opt/", "/bin/", "/sbin/", "/System/", "/Library/",
          "/private/tmp/", "/tmp/", "/private/var/folders/", "/var/folders/",
          "/dev/", "/Applications/")
PATHISH = re.compile(r"""(?:~|/|\bbrain/)[^\s'"`;|&<>()]*""")


def _sources():
    try:
        with open(os.path.join(BRAIN, "config.json"), encoding="utf-8") as f:
            cfg = json.load(f)
    except (OSError, ValueError):
        return []
    out = []
    for s in cfg.get("sources") or []:
        p = s.get("path") if isinstance(s, dict) else s
        if isinstance(p, str) and p.strip():
            out.append(os.path.abspath(os.path.expanduser(p.strip())))
    return out


def kind_of(path, cwd=ROOT, sources=None):
    """(kind, outside-label). outside-label is "~/Documents"-style for a
    path outside the brain and the named folders, else ""."""
    p = os.path.abspath(os.path.join(cwd, os.path.expanduser(path)))
    if p == ROOT or p.startswith(ROOT + os.sep):
        rel = os.path.relpath(p, ROOT).replace(os.sep, "/")
        for kind, prefixes in KINDS:
            if any(rel == pre.rstrip("/") or rel.startswith(pre) for pre in prefixes):
                return kind, ""
        return "brain", ""
    if any(p == s or p.startswith(s + os.sep) for s in (sources or [])):
        return "projects", ""
    if p.startswith(SYSTEM) or (p + "/").startswith(SYSTEM):
        return "", ""
    if p.startswith(HOME + os.sep):
        top = p[len(HOME) + 1:].split(os.sep, 1)[0]
        return "outside", "~/" + top
    if p == HOME:
        return "outside", "~"
    return "outside", "/" + p.strip("/").split("/", 1)[0]


def _locked_now():
    try:
        sys.path.insert(0, HERE)
        import privacy
        vals = privacy.effective()["values"]
        return {k for k, key in LOCKS.items() if vals.get(key)} | {"journal"}
    except Exception:
        return {"journal", "transcripts", "money", "people"}


def entry(payload, profile):
    tool = payload.get("tool_name") or ""
    inp = payload.get("tool_input") or {}
    cwd = payload.get("cwd") or ROOT
    srcs = _sources()
    if tool in ("Read", "Grep", "Glob"):
        how = "opened"
        paths = [inp.get(k) for k in ("file_path", "path") if inp.get(k)]
        if tool in ("Grep", "Glob") and not paths:
            paths = [cwd]
        # A Glob's pattern is where it looks ("brain/journal/*.md" was
        # logged as just "brain"); its fixed part is the folder.
        pat = inp.get("pattern") if tool == "Glob" else inp.get("glob")
        if isinstance(pat, str) and pat.strip():
            fixed = re.split(r"[*?\[{]", pat, 1)[0]
            if fixed:
                base = paths[0] if paths and not os.path.isabs(fixed) else ""
                paths.append(os.path.join(str(base), fixed) if base else fixed)
    elif tool == "Bash":
        how = "named"
        paths = PATHISH.findall(inp.get("command") or "")
    else:
        return None
    kinds, outside = set(), set()
    for path in paths:
        k, o = kind_of(str(path), cwd, srcs)
        if k:
            kinds.add(k)
        if o:
            outside.add(o)
    if not kinds:
        return None
    sid = hashlib.sha256(str(payload.get("session_id") or "").encode()).hexdigest()[:8]
    out = {"t": datetime.now().isoformat(timespec="seconds"), "p": profile,
           "s": sid, "tool": tool, "how": how, "k": sorted(kinds)}
    if outside:
        out["o"] = sorted(outside)[:5]
    if how == "opened" and profile in TIMER:
        trips = sorted(kinds & _locked_now())
        if trips:
            out["trip"] = trips
    return out


def _append(line):
    try:
        if os.path.getsize(LOG) > MAX_BYTES:
            with open(LOG, encoding="utf-8") as f:
                keep = f.readlines()[-4000:]
            with open(LOG, "w", encoding="utf-8") as f:
                f.writelines(keep)
    except OSError:
        pass
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(line) + "\n")


def read(days=7):
    since = (datetime.now() - timedelta(days=days)).isoformat(timespec="seconds")
    out = []
    try:
        with open(LOG, encoding="utf-8") as f:
            for raw in f:
                try:
                    e = json.loads(raw)
                except ValueError:
                    continue
                if e.get("t", "") >= since:
                    out.append(e)
    except OSError:
        pass
    return out


def summary(days=7):
    """What the Privacy page shows: runs by watched and timer, each kind's
    opens split the same way, the folders outside the named ones, and trips."""
    rows = read(days)
    runs = {"timer": set(), "watched": set()}
    kinds = {}
    outside = {}
    trips = []
    for e in rows:
        side = "timer" if e.get("p") in TIMER else "watched"
        runs[side].add(e.get("s"))
        for k in e.get("k") or []:
            d = kinds.setdefault(k, {"timer": 0, "watched": 0, "named": 0})
            if e.get("how") == "opened":
                d[side] += 1
            else:
                d["named"] += 1
        for o in e.get("o") or []:
            outside[o] = outside.get(o, 0) + 1
        if e.get("trip"):
            trips.append({"t": e["t"], "k": e["trip"]})
    return {"days": days, "runs": {k: len(v) for k, v in runs.items()},
            "kinds": kinds,
            "outside": dict(sorted(outside.items(), key=lambda kv: -kv[1])[:12]),
            "trips": trips[-10:], "since": rows[0]["t"] if rows else ""}


def trips_fingerprint():
    """For the security alarm: changes when a new trip is written."""
    t = [e["t"] for e in read(30) if e.get("trip")]
    return (str(len(t)) + ":" + t[-1]) if t else "none"


def main(argv):
    if argv and argv[0] == "--summary":
        print(json.dumps(summary(), indent=1))
        return 0
    profile = (argv[0] if argv else "unknown")[:20]
    try:
        payload = json.load(sys.stdin)
        line = entry(payload, profile)
        if line:
            _append(line)
    except Exception:
        pass
    return 0            # no output, ever: an answer here would decide for the run


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

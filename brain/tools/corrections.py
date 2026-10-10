#!/usr/bin/env python3
"""The correction rate: how often a Claude session needed the owner to say
it was wrong. It is the brain's headline measure of whether AI work was
right the first time.

    python3 brain/tools/corrections.py           # weekly table + projects
    python3 brain/tools/corrections.py --json    # also write the files below
    python3 brain/tools/corrections.py --check 30   # 30 random matches, to judge

Plain code, no model, reads only. Two sources:

- Claude Code transcripts, ~/.claude/projects/*/*.jsonl, one per session,
  every repo. Only interactive sessions count (an `entrypoint` that is not
  an SDK one): the page's runs, the morning and night jobs and every other
  `claude -p` launch leave no entrypoint, or an `sdk-*` one, and are
  skipped at their first record. Subagent sidechains, tool results, hook
  and system injections, task notifications, messages from other sessions,
  compaction summaries and slash commands are not hers and are skipped.
- The page's conversations, brain/sessions/*.json (her turns are `k: her`).

A session whose first message is the journal (`/journal`, `journal:`) is
skipped before anything else in it is read, and brain/journal/ is never
opened.

Her text is cleaned before matching: pasted blocks, quoted lines, code
fences and every tag block (<pasted_content>, <system-reminder>,
<command-...>, <ide_...>) are cut, so a match is always in words she typed.

The unit is a session-week: a session counts in each week she typed in it,
and is corrected in that week when one of her messages that week matched.
A correction needs something to correct, so a session's opening message
only counts for the patterns in OPENER_PATTERNS (a "still broken" can carry
over from yesterday's session; a "doesn't work" in an opener is a bug
report).

Outputs, on --json:
- brain/evals/corrections-rate.json  counts only (committed)
- brain/.corrections-lines.jsonl     her matched lines, 200 chars each,
                                      for tuning the patterns (gitignored)
"""

import argparse
import glob
import json
import os
import random
import re
import sys
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
BRAIN = os.path.dirname(HERE)
PROJECTS = os.path.expanduser("~/.claude/projects")
PAGE_SESSIONS = os.path.join(BRAIN, "sessions")
OUT_JSON = os.path.join(BRAIN, "evals", "corrections-rate.json")
LINES = os.path.join(BRAIN, ".corrections-lines.jsonl")

# The audit (reference/claude-audit.md, 28 Sep 2026): 18% of Claude Code
# sessions had a correction, 10 Aug to 28 Sep 2026.
BASELINE = {"rate": 0.18, "from": "2026-08-10", "to": "2026-09-28",
            "what": "Claude Code sessions with a correction, at the audit"}

# ---------------------------------------------------------------------------
# The patterns. Tune here. Matched against her cleaned text, lowercased, with
# curly apostrophes made straight. `'?` lets "dont" and "don't" both match.

# "still" is spelled "stil" often enough to allow it: `still?`.
_STILL = (r"\bstill? (not|isn'?t|doesn'?t|didn'?t|won'?t|can'?t|cannot)\b"
          r"(?! (sure|need|want|decided|know|clear on))")
_STILL_SEEING = (r"\bstill? (seeing|showing|shows|getting|appearing|happening|"
                 r"broken|the same|there|missing|empty|failing|running|cut off|"
                 r"overlapping|looking|looks|seems? (to be )?(off|wrong|broken|"
                 r"the old|empty|cut)|says|reads|sounds|too \w+|very \w+|"
                 r"a bit|wrong|old|blank|no luck|nothing|have (a|some|the|this)|"
                 r"has (a|some|the|this)|stuck|loading|reloading|crash\w*)\b")
_THOUGHT_FIXED = (r"\b(i )?(thought|tohught|thougth|thougt|tought|thot) "
                  r"(we|you|it) (had |were |was )?"
                  r"(fixed|solved|changed|removed|did|added|updated|done)\b")
_PUSH = (r"\b(did|have) you (push|pushed|commit|committed)\b",
         r"\bis (it|this|that|everything|all) (pushed|committed|push)\b",
         r"\b(has|have) (it|this|that|these|all (of )?(this|these|that)|"
         r"everything)( updates?| changes?)? been (pushed|push|committed)\b")
_CANT_FIND = (r"\bwhere (can|do|would|should) i (see|find|open|access) "
              r"(this|that|it|them|these|those|the (new |long |updated |final )?"
              r"(file|doc|output|link|draft|transcript|pdf|report|minutes|page|"
              r"copy))\b",
              r"\bi (can(no|')?t|could(n'?t| not)) find\b",
              r"\bwhere (is|are) (the|that|this|those|these)( new| long| "
              r"updated| final)? (file|doc|docs|document|output|link|draft|"
              r"transcript|pdf|csv|report|minutes|copy)s?\b")

PATTERNS = {
    "not_fixed": [
        _STILL, _STILL_SEEING, _THOUGHT_FIXED,
        r"\b(isn'?t|wasn'?t|aren'?t|is not|was not|are not|not been|hasn'?t "
        r"been|haven'?t been) (yet )?(fixed|solved|resolved)\b",
        r"\b(didn'?t|did not|doesn'?t|does not|isn'?t|is not|not) "
        r"(really )?(work|working|log|logging|save|saving|stick|sticking)\b",
        r"\bnothing (changed|has changed|happens|happened|shows|showed)\b",
        r"\bno luck\b", r"\bsame (problem|issue|error|bug)\b",
        r"\b(i'?m|i am|im) (still )?not (seeing|getting)\b",
        r"\b(this|it|that) (is|seems|looks) (still )?broken\b",
        r"\b(it'?s|its) (still )?broken\b",
        r"\bkeeps (reappearing|coming back|reloading|crashing|resetting)\b",
        r"\btoujours pas\b", r"\b(ça|ca) (ne )?(marche|fonctionne) "
        r"(toujours )?pas\b", r"\brien n'?a chang",
    ],
    "sounds_ai": [
        r"\b(sounds?|sounding|seems?|looks?|reads?|feels?)( very| so| a bit|"
        r" a little| too| quite| still| less| more| kind of| kinda)* ai\b"
        r"(?! (model|session|run|tool|coach|agent))",
        r"\b(too|less|very|more|so) ai[- ]?(like|ish|ey|y)\b",
        r"\bai[- ]sounding\b", r"\bsounds? like (an? )?(ai|chatgpt|a robot)\b",
        r"\b(contains?|has|have|had|still|there'?s|there are|using|uses|used|"
        r"with|remove|removed|no more|any|saw|found|left)\b[^.\n]{0,30}"
        r"\bem[- ]?dash",
        r"\b(sounds?|too|very|so|bit|little) robotic\b",
        r"\b(fait|trop) (très )?ia\b",
    ],
    "over_limit": [
        r"\b(way|still|much|far|a bit|a little|bit|is|it'?s|its|was|are|"
        r"that'?s|this is|seems|looks|feels) too (long|wordy|verbose)\b",
        r"\b(less wordy|more succinct|more concise|make (it|this|that|them) "
        r"(shorter|tighter)|cut it down)\b",
        r"\bover the (word |character |page |slide )?limit\b",
        r"\b(remove|cut) \d+ (more )?(words|characters|slides)\b",
        r"\b(reach|under|within) (the |a )?\d+[- ]?(word|character|slide)s?"
        r"( limit)?\b",
        r"\bmax(imum)? \d+ (words|slides|characters|pages|minutes)\b",
        r"\btrop long\b",
    ],
    "ruled_out": [
        r"\bi (said|told you|asked( you)?|wrote|specified)( that)? (not|no|"
        r"never|don'?t|to not|without)\b",
        r"\bi (already )?told you\b",
        r"\bi already (said|asked|mentioned|explained|answered)\b",
        r"\bwe already (discussed|agreed|decided|said|talked about|covered)\b",
        r"\bnot what i (asked|wanted|meant|said)\b",
        r"\bthat'?s not what i\b",
        r"(?<!sorry )(?<!sorry, )(?<!think )(?<!guess )\bi meant\b",
        r"(?<!should )(?<!to )(?<!we )(?<!i )\bremember (that )?(we|i'?m|i am|"
        r"we'?re|we are|my)\b",
        r"\bje (t'?ai|vous ai) (déjà )?dit\b", r"\bj'?ai dit (non|pas)\b",
    ],
    "invented_fact": [
        r"\b(that'?s|that is|this is|it'?s|it is|thats) (not (true|right|"
        r"correct|accurate)|wrong|incorrect|false)\b",
        r"\bi never (said|asked|told|did|went|started|wrote|mentioned|agreed|"
        r"sent|met|had|was|clicked|triggered|chose|picked|booked)\b",
        r"\bi (didn'?t|did not) (really )?(say|ask|tell|start|trigger|click|"
        r"send|write|mention|do|go|agree|meet|book|choose|pick)\b",
        r"\b(it|that|this) was actually\b", r"\bactually (it|that) was\b",
        r"\bi'?m \d+ (years|yo)\b", r"\bi am \d+ years\b",
        r"\bwhere did you get\b", r"\bare you sure\b",
        r"\bc'?est faux\b", r"\bje n'?ai jamais\b",
        r"\bce n'?est pas (vrai|correct|ça)\b",
    ],
    "cant_find": list(_CANT_FIND),
    "push": list(_PUSH),
}

# What may count in a session's opening message (see the docstring): a
# carry-over from an earlier session, never a fresh bug report.
OPENER_PATTERNS = {
    "not_fixed": [_STILL, _STILL_SEEING, _THOUGHT_FIXED],
    "push": list(_PUSH),
    "cant_find": list(_CANT_FIND),
}

# A match is dropped when its sentence, before the match, is conditional or
# hedged ("if it's too long", "i am not saying it is wrong"), or reports
# someone else ("people said it was too long"), or when its line is a pasted
# rule ("- Never use em dashes") or a pasted table row. In a very long
# message (a paste with her framing around it) only the start and the end
# are hers often enough to read.
_CONDITIONAL = re.compile(
    r"\b(if|whether|in case|unless|maybe|might|would|could|not saying)\b|"
    r"\b(people|someone|somebody|they|he|she|users?|others|friends?) "
    r"(said|say|says|told|think|thinks|felt|feel|found)\b", re.I)
LONG, EDGE = 3000, 1000
_RULE_LINE = re.compile(r"^\s*([-*•]|\d+[.)])?\s*(never|avoid|always|no |"
                        r"do not|don'?t|use |make sure|rule)", re.I)

COMPILED = {t: [re.compile(p, re.I) for p in ps] for t, ps in PATTERNS.items()}
COMPILED_OPENER = {t: [re.compile(p, re.I) for p in ps]
                   for t, ps in OPENER_PATTERNS.items()}

# ---------------------------------------------------------------------------
# cleaning: only her own typed words survive

_TAG_BLOCK = re.compile(
    r"<(pasted_content|system-reminder|task-notification|"
    r"command-[\w-]+|local-command-[\w-]+|ide_\w+|[a-z]+[-_][\w-]+)"
    r"\b[^>]*>.*?</\1\s*>", re.S | re.I)
_TAG_OPEN = re.compile(
    r"<(pasted_content|system-reminder|ide_\w+|command-[\w-]+|"
    r"local-command-[\w-]+)\b[^>]*>.*", re.S | re.I)
_FENCE = re.compile(r"```.*?(```|\Z)", re.S)
_IMAGE = re.compile(r"\[(image|message truncated)[^\]]*\]", re.I)
_URL = re.compile(r"\b(https?://|www\.)\S+", re.I)   # links can carry tokens
_NOT_HERS = ("[request interrupted", "another claude session sent",
             "this session is being continued", "caveat: the messages below")


def clean(text):
    """Her typed words only, or '' when nothing of hers is left."""
    if not text:
        return ""
    t = _TAG_BLOCK.sub(" ", text)
    t = _TAG_OPEN.sub(" ", t)
    t = _FENCE.sub(" ", t)
    t = _IMAGE.sub(" ", t)
    t = _URL.sub("[link]", t)
    lines =[ln for ln in t.splitlines() if not ln.lstrip().startswith(">")]
    t = "\n".join(lines).strip()
    if t.lower().startswith(_NOT_HERS):
        return ""
    return t


def _norm(text):
    return (text.replace("’", "'").replace("‘", "'")
            .replace("ʼ", "'"))


def is_journal(text):
    s = (text or "").lstrip().lower()
    return (s.startswith("/journal") or s.startswith("journal:")
            or "<command-name>/journal" in s)


def _counts(text, m):
    a = m.start()
    line_start = text.rfind("\n", 0, a) + 1
    line_end = text.find("\n", a)
    line = text[line_start:line_end if line_end >= 0 else len(text)]
    if "\t" in line or _RULE_LINE.match(line):
        return False
    sent = max(text.rfind(c, 0, a) for c in ".?!\n") + 1
    return not _CONDITIONAL.search(text[sent:a])


def find(text, opener=False):
    """[(type, matched line)] for one cleaned message, one per type."""
    t = _norm(text)
    if len(t) > LONG:
        t = t[:EDGE] + "\n" + t[-EDGE:]
    hits = []
    for typ, pats in (COMPILED_OPENER if opener else COMPILED).items():
        for p in pats:
            m = next((m for m in p.finditer(t) if _counts(t, m)), None)
            if m:
                hits.append((typ, _line_at(t, m.start(), m.end())))
                break
    return hits


def _line_at(text, a, b, width=200):
    start = text.rfind("\n", 0, a) + 1
    end = text.find("\n", b)
    end = len(text) if end < 0 else end
    line = text[start:end].strip()
    if len(line) <= width:
        return line
    mid = (a - start + b - start) // 2
    lo = max(0, min(len(line) - width, mid - width // 2))
    return line[lo:lo + width]

# ---------------------------------------------------------------------------
# reading the sources


def _local(ts):
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone()
    except (AttributeError, ValueError):
        return None


def _text_of(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        if any(isinstance(b, dict) and b.get("type") == "tool_result"
               for b in content):
            return None
        return "\n".join(b.get("text", "") for b in content
                         if isinstance(b, dict) and b.get("type") == "text")
    return None


_SKIP_TURN = {"task_notification", "peer", "scheduled", "system"}


def _hers(r):
    """Her raw typed text from one transcript record, or None."""
    t = r.get("type")
    if t == "attachment":
        a = r.get("attachment") or {}
        if (a.get("type") == "queued_command"
                and (a.get("origin") or {}).get("kind") == "human"
                and not a.get("isMeta") and isinstance(a.get("prompt"), str)):
            return a["prompt"]
        return None
    if t != "user":
        return None
    if (r.get("isSidechain") or r.get("isMeta") or r.get("isCompactSummary")
            or r.get("isVisibleInTranscriptOnly")):
        return None
    if (r.get("origin") or {}).get("kind") not in (None, "human"):
        return None
    if r.get("promptSource") == "system" or r.get("turnOrigin") in _SKIP_TURN:
        return None
    return _text_of((r.get("message") or {}).get("content"))


def read_code_session(path):
    """One Claude Code transcript -> session dict, or None when it is not an
    interactive session of hers (or is the journal)."""
    msgs, project, sid, decided = [], None, None, False
    assistant_seen, seen_text = False, set()
    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            if ('"type":"user"' not in line and '"type":"assistant"' not in line
                    and '"queued_command"' not in line):
                continue
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if r.get("isSidechain"):
                continue
            if r.get("type") == "assistant":
                assistant_seen = True
                continue
            if not decided and r.get("type") == "user":
                ep = r.get("entrypoint") or ""
                if not ep or ep.startswith("sdk"):
                    return None          # a launched run, not her at the keys
                decided = True
                project = os.path.basename((r.get("cwd") or "").rstrip("/")) \
                    or os.path.basename(os.path.dirname(path))
                sid = r.get("sessionId") or os.path.basename(path)[:-6]
            raw = _hers(r)
            if raw is None:
                continue
            if not msgs and is_journal(raw):
                return None
            if raw.lstrip().startswith(("<command-name>", "<command-message>")):
                continue                 # a slash command, not prose
            text = clean(raw)
            if not text or text[:200] in seen_text:
                continue
            seen_text.add(text[:200])
            when = _local(r.get("timestamp") or "")
            if when is None:
                continue
            msgs.append({"when": when, "text": text,
                         "opener": not msgs and not assistant_seen})
    if not msgs:
        return None
    return {"source": "code", "project": project, "id": sid, "msgs": msgs}


def read_page_session(path):
    name = os.path.basename(path)[:-5]
    m = re.match(r"(\d{8})-(\d{6})-(.+)$", name)
    if not m:
        return None
    try:
        with open(path, encoding="utf-8") as f:
            turns = json.load(f)
        day = datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M%S")
    except (OSError, ValueError):
        return None
    if not isinstance(turns, list):
        return None
    msgs, claude_seen, last = [], False, None
    for t in turns:
        if not isinstance(t, dict):
            continue
        if t.get("k") in ("claude", "work"):
            claude_seen = True
            continue
        if t.get("k") != "her":
            continue
        raw = t.get("t") or ""
        if not msgs and is_journal(raw):
            return None
        text = clean(raw)
        if not text:
            continue
        when = day
        at = re.match(r"(\d{1,2}):(\d{2})", t.get("at") or "")
        if at:
            when = day.replace(hour=int(at.group(1)), minute=int(at.group(2)),
                               second=0)
            if last and when < last - timedelta(hours=1):
                when += timedelta(days=1)       # the talk ran past midnight
                day += timedelta(days=1)
        last = when
        msgs.append({"when": when, "text": text,
                     "opener": not msgs and not claude_seen})
    if not msgs:
        return None
    return {"source": "page", "project": "page: " + m.group(3), "id": name,
            "msgs": msgs}


def sessions():
    for path in glob.glob(os.path.join(PROJECTS, "*", "*.jsonl")):
        try:
            s = read_code_session(path)
        except OSError:
            continue
        if s:
            yield s
    for path in glob.glob(os.path.join(PAGE_SESSIONS, "*.json")):
        s = read_page_session(path)
        if s:
            yield s

# ---------------------------------------------------------------------------
# counting


def week_of(d):
    y, w, _ = d.isocalendar()
    return f"{y}-W{w:02d}"


def week_start(key):
    y, w = key.split("-W")
    return date.fromisocalendar(int(y), int(w), 1)


def scan():
    """Session-weeks plus every match: ([row], [hit])."""
    rows, hits = [], []
    for s in sessions():
        weeks = defaultdict(lambda: {"msgs": 0, "types": Counter()})
        for m in s["msgs"]:
            wk = week_of(m["when"].date())
            weeks[wk]["msgs"] += 1
            for typ, line in find(m["text"], opener=m["opener"]):
                weeks[wk]["types"][typ] += 1
                hits.append({"date": m["when"].date().isoformat(),
                             "project": s["project"], "session": s["id"],
                             "source": s["source"], "type": typ,
                             "line": line[:200]})
        for wk, v in weeks.items():
            rows.append({"week": wk, "project": s["project"],
                         "source": s["source"], "session": s["id"],
                         "msgs": v["msgs"], "types": v["types"],
                         "first": min(m["when"] for m in s["msgs"]).date()})
    return rows, hits


def tally(rows):
    sess = {(r["source"], r["session"]) for r in rows}
    corr = {(r["source"], r["session"]) for r in rows if r["types"]}
    by_type = Counter()
    for r in rows:
        for t in r["types"]:
            by_type[t] += 1            # sessions with that type, not mentions
    n, k = len(sess), len(corr)
    return {"sessions": n, "corrected": k,
            "rate": round(k / n, 3) if n else None,
            "by_type": dict(by_type.most_common())}


def report(rows, today=None, weeks=10, project_weeks=4):
    today = today or date.today()
    this = week_start(week_of(today))
    keys = [week_of(this - timedelta(weeks=i)) for i in range(weeks - 1, -1, -1)]
    out = {"generated": today.isoformat(), "baseline": BASELINE,
           "unit": "session-week", "weeks": [], "projects": []}
    for k in keys:
        wr = [r for r in rows if r["week"] == k]
        t = tally(wr)
        t.update({"week": k, "start": week_start(k).isoformat(),
                  "code": tally([r for r in wr if r["source"] == "code"]),
                  "page": tally([r for r in wr if r["source"] == "page"])})
        out["weeks"].append(t)
    recent = set(keys[-project_weeks:])
    by_proj = defaultdict(list)
    for r in rows:
        if r["week"] in recent:
            by_proj[r["project"]].append(r)
    for p, pr in sorted(by_proj.items(), key=lambda x: -len(x[1])):
        t = tally(pr)
        t["project"] = p
        out["projects"].append(t)
    out["project_weeks"] = keys[-project_weeks:]
    # The audit's window, counted the audit's way: whole Claude Code
    # sessions that began in it.
    a0 = date.fromisoformat(BASELINE["from"])
    a1 = date.fromisoformat(BASELINE["to"])
    win = [r for r in rows if r["source"] == "code" and a0 <= r["first"] <= a1]
    out["audit_window"] = tally(win)
    return out


def _pct(x):
    return "  -" if x is None else f"{round(x * 100):>3d}%"


def print_report(out):
    print("Correction rate per week (a session counts in each week she typed"
          " in it)\n")
    print(f"{'week':<9} {'starts':<10} {'sessions':>8} {'corrected':>9} "
          f"{'rate':>5}  by type")
    for w in out["weeks"]:
        types = ", ".join(f"{k} {v}" for k, v in w["by_type"].items())
        print(f"{w['week']:<9} {w['start']:<10} {w['sessions']:>8} "
              f"{w['corrected']:>9} {_pct(w['rate']):>5}  {types}")
    print(f"\nBy project, {out['project_weeks'][0]} to "
          f"{out['project_weeks'][-1]}\n")
    print(f"{'project':<34} {'sessions':>8} {'corrected':>9} {'rate':>5}  by type")
    for p in out["projects"]:
        types = ", ".join(f"{k} {v}" for k, v in p["by_type"].items())
        print(f"{p['project'][:34]:<34} {p['sessions']:>8} "
              f"{p['corrected']:>9} {_pct(p['rate']):>5}  {types}")
    a = out["audit_window"]
    print(f"\nThe audit's window ({BASELINE['from']} to {BASELINE['to']}, "
          f"Claude Code only): {a['corrected']} of {a['sessions']} sessions, "
          f"{_pct(a['rate']).strip()} (the audit said 18%).")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--json", action="store_true",
                    help="write the counts file and the lines file")
    ap.add_argument("--check", type=int, metavar="N",
                    help="print N random matches to judge by hand")
    ap.add_argument("--type", help="with --check: only this type")
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args(argv)

    rows, hits = scan()
    if args.check:
        pool = [h for h in hits if not args.type or h["type"] == args.type]
        random.Random(args.seed).shuffle(pool)
        for i, h in enumerate(pool[:args.check], 1):
            print(f"{i:>2}. [{h['type']}] {h['date']} {h['project']}: "
                  f"{h['line']}")
        print(f"\n{len(pool)} matches in all.")
        return
    out = report(rows)
    print_report(out)
    if args.json:
        os.makedirs(os.path.dirname(OUT_JSON), exist_ok=True)
        with open(OUT_JSON, "w", encoding="utf-8") as f:
            json.dump(out, f, indent=1, default=str)
            f.write("\n")
        with open(LINES, "w", encoding="utf-8") as f:
            for h in sorted(hits, key=lambda h: h["date"]):
                f.write(json.dumps({k: h[k] for k in
                                    ("date", "project", "session", "type",
                                     "line")}, ensure_ascii=False) + "\n")
        print(f"\nWrote {os.path.relpath(OUT_JSON, os.path.dirname(BRAIN))} "
              f"and {os.path.relpath(LINES, os.path.dirname(BRAIN))}.")


if __name__ == "__main__":
    sys.exit(main())

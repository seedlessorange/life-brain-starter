#!/usr/bin/env python3
"""Do her writing rules actually hold? Replays her corrections as tests.

Every "Learned from corrections" entry in writing-rules.md came from a draft
she had to fix. brain/evals/corrections.md turns each one into a case: the
Before text, the phrases that must not survive, the facts that must. This
script sends every Before through the revise call the page uses (same system
prompt, same prompt builder, same model routing) with a plain ask that does
not name the mistake, then scores the rewrite twice:

- mechanically: a Gone phrase survived, a Keep fact went missing, or an em
  dash appeared (her one absolute rule). No model involved.
- by a judge: one no-tools call on Opus that reads the lesson and says
  whether the same mistake is still there in other words.

A case passes only when both do. Two calls per case, on demand only, never
from a schedule. Each run appends one line to brain/evals/history.jsonl and
rewrites brain/evals/last-run.md with every rewrite, so a failure can be read
without paying for the run again.

    python3 brain/tools/drafteval.py                 # all cases
    python3 brain/tools/drafteval.py --list          # the cases, no model calls
    python3 brain/tools/drafteval.py --case mirrored-antithesis [--case ...]
    python3 brain/tools/drafteval.py --rules /tmp/rules-draft.md   # test an edit first
    python3 brain/tools/drafteval.py --model haiku   # which model follows her rules

A full run is ~26 calls and a few minutes; run it under `caffeinate -ims` so
the Mac does not sleep mid-call.
"""

import hashlib
import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
BRAIN = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import llm                # noqa: E402
import serve              # noqa: E402  (revise_prompt + REVISE_SYS: the page's own call)
import sessions as SESS   # noqa: E402
import usage              # noqa: E402

CASES = os.path.join(BRAIN, "evals", "corrections.md")
HISTORY = os.path.join(BRAIN, "evals", "history.jsonl")
LAST_RUN = os.path.join(BRAIN, "evals", "last-run.md")
RULES = os.path.join(BRAIN, "writing-rules.md")
DEFAULT_ASK = "Get this ready to send."
WORKERS = 3
# The judge is Opus on purpose: on 2026-09-27 Sonnet failed a rewrite for
# using her own fix's wording ("chiffrage sérieux") three times over, and
# flipped its verdict on a re-read. Opus got all of those right. It is ~13
# short calls a run; a judge that fails her own words is worse than none.
JUDGE_MODEL = "opus"

FIELD_RE = re.compile(r"^- \*\*([^:*]+):\*\*\s*(.*)$")

JUDGE_SYS = ("You grade one rewrite against one writing lesson. Reply with "
             "JSON only, no preamble.")

JUDGE_PROMPT = """THE LESSON (from a correction she made to an earlier draft):
{lesson}
{fix}
BEFORE:
{before}

AFTER (the rewrite you are grading):
{after}

Does AFTER still make the mistake the lesson describes, either with the same
words or with the same move in different words? Judge this lesson only and
ignore every other style issue. A sentence the rewrite deleted cannot fail.
Her own fix, when given, is the standard: any word or phrase she used in it
is hers and never counts as the mistake, and wording near it passes.

Reply with only this JSON:
{{"fixed": true or false, "quote": "the offending sentence from AFTER, or empty", "why": "one short sentence"}}"""


def parse_cases(text):
    """corrections.md -> [{name, fields..., before}]. Everything above the
    first `## ` heading is the file's own explanation and is skipped."""
    cases = []
    for block in re.split(r"^## ", text, flags=re.M)[1:]:
        lines = block.splitlines()
        case = {"name": lines[0].strip()}
        quote, in_before = [], False
        for line in lines[1:]:
            m = FIELD_RE.match(line)
            if m and not in_before:
                case[m.group(1).strip().lower()] = m.group(2).strip()
            elif line.strip().lower() == "before:":
                in_before = True
            elif in_before and line.startswith(">"):
                quote.append(line[1:].removeprefix(" "))
        case["before"] = "\n".join(quote).strip()
        cases.append(case)
    return cases


def _split(value):
    return [p.strip() for p in (value or "").split("|") if p.strip()]


def problems(case):
    """Why a case can't run, or [] when it can."""
    out = []
    if not case.get("lesson"):
        out.append("no Lesson")
    if not case["before"]:
        out.append("no Before quote")
    return out


def mechanical(case, after):
    """The checks no model is needed for. Returns a list of failures."""
    low = after.lower()
    fails = [f'"{g}" survived' for g in _split(case.get("gone"))
             if g.lower() in low]
    fails += [f'lost "{k}"' for k in _split(case.get("keep"))
              if k.lower() not in low]
    if "—" in after:
        fails.append("em dash")
    return fails


def _judge(case, after):
    fix = f"Her own fix at the time: {case['her fix']}\n" if case.get("her fix") else "Her own fix: not recorded.\n"
    prompt = JUDGE_PROMPT.format(lesson=case["lesson"], fix=fix,
                                 before=case["before"], after=after)
    res = llm.complete("drafteval", prompt, system=JUDGE_SYS, timeout=120,
                       env=SESS.claude_env(), model=JUDGE_MODEL)
    m = re.search(r"\{.*\}", res["text"], re.S)
    try:
        verdict = json.loads(m.group(0)) if m else None
    except json.JSONDecodeError:
        verdict = None
    if not isinstance(verdict, dict) or "fixed" not in verdict:
        return {"fixed": None, "why": "judge reply unreadable: " + res["text"][:120]}
    return verdict


def run_case(case, voice, model):
    """Revise the Before exactly as the page would, then score it."""
    meta = {k: case[k] for k in ("kind", "task") if case.get(k)}
    meta["to"] = case.get("to", "")
    prompt = serve.revise_prompt(meta, case["before"],
                                 case.get("ask") or DEFAULT_ASK, voice=voice)
    started = time.time()
    try:
        res = llm.complete("revise", prompt, system=serve.REVISE_SYS,
                           timeout=90, env=SESS.claude_env(), model=model)
    except ValueError as exc:
        usage.record("revise", "draft eval: " + case["name"], model=model or "",
                     usage={"input_tokens": len(prompt) // 4},
                     secs=time.time() - started, ok=False)
        return {"name": case["name"], "pass": False, "error": str(exc)}
    # "revise" is a self-recorded job in llm.py, so the line is written here,
    # labelled as the eval rather than as a real draft.
    usage.record("revise", "draft eval: " + case["name"], model=res["model"],
                 usage=res["usage"], secs=time.time() - started, ok=True)
    after = res["text"].strip()
    fails = mechanical(case, after)
    try:
        verdict = _judge(case, after)
    except ValueError as exc:
        verdict = {"fixed": None, "why": f"judge failed: {exc}"}
    ok = not fails and verdict.get("fixed") is True
    return {"name": case["name"], "pass": ok, "mechanical": fails,
            "judge": verdict, "after": after, "model": res["model"]}


def _last_score(rules_label):
    try:
        with open(HISTORY, encoding="utf-8") as f:
            rows = [json.loads(l) for l in f if l.strip()]
    except (OSError, json.JSONDecodeError):
        return None
    # Only a run with the same rules file and the same judge is comparable.
    rows = [r for r in rows if r.get("rules") == rules_label and r.get("full")
            and r.get("judge") == JUDGE_MODEL]
    return rows[-1] if rows else None


def _reason(r):
    if r.get("error"):
        return "call failed: " + r["error"]
    bits = list(r["mechanical"])
    j = r["judge"]
    if j.get("fixed") is not True:
        q = j.get("quote")
        bits.append("judge: " + (j.get("why") or "not fixed")
                    + (f' ("{q}")' if q else ""))
    return "; ".join(bits)


def write_last_run(results, header):
    out = [f"# Draft eval, last run\n\n{header}\n"]
    for r in results:
        mark = "pass" if r["pass"] else "FAIL"
        out.append(f"## {r['name']} ({mark})\n")
        if not r["pass"]:
            out.append(_reason(r) + "\n")
        elif r.get("judge", {}).get("why"):
            out.append(r["judge"]["why"] + "\n")
        if r.get("after"):
            out.append("\n".join("> " + l if l else ">"
                                 for l in r["after"].splitlines()) + "\n")
    with open(LAST_RUN, "w", encoding="utf-8") as f:
        f.write("\n".join(out))


def main(argv):
    names, rules_path, model = [], RULES, None
    i = 0
    while i < len(argv):
        a = argv[i]
        if a in ("--case", "--rules", "--model") and i + 1 < len(argv):
            v = argv[i + 1]
            if a == "--case":
                names.append(v)
            elif a == "--rules":
                rules_path = os.path.abspath(v)
            else:
                model = v
            i += 2
        elif a == "--list":
            names = None
            i += 1
        else:
            print(__doc__)
            return 2

    try:
        with open(CASES, encoding="utf-8") as f:
            cases = parse_cases(f.read())
    except OSError:
        cases = []
    if not cases:
        print("No cases yet. Each correction to a draft adds one to "
              "brain/evals/corrections.md (format in its header).")
        return 0

    if names is None:
        for c in cases:
            bad = problems(c)
            print(f"  {c['name']:34} {'BROKEN: ' + ', '.join(bad) if bad else c.get('lesson', '')[:70]}")
        print(f"\n{len(cases)} cases in {os.path.relpath(CASES, os.path.dirname(BRAIN))}")
        return 0

    if names:
        unknown = set(names) - {c["name"] for c in cases}
        if unknown:
            print("no such case: " + ", ".join(sorted(unknown)))
            return 2
        cases = [c for c in cases if c["name"] in names]
    broken = [(c["name"], problems(c)) for c in cases if problems(c)]
    if broken:
        for n, bad in broken:
            print(f"case {n}: {', '.join(bad)}")
        return 2

    with open(rules_path, encoding="utf-8") as f:
        voice = f.read()
    rules_label = os.path.relpath(rules_path, BRAIN) if rules_path.startswith(BRAIN) else rules_path
    model_label = model or llm.model_for("revise")
    print(f"Running {len(cases)} case(s): revise on {model_label}, "
          f"rules from {rules_label} ...", flush=True)

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        results = list(pool.map(lambda c: run_case(c, voice, model), cases))

    passed = sum(r["pass"] for r in results)
    header = (f"{passed}/{len(results)} lessons hold. Rules: {rules_label}. "
              f"Revise on {model_label}, judged by {JUDGE_MODEL}. {datetime.now():%Y-%m-%d %H:%M}.")
    full = not names
    prev = _last_score(rules_label) if full else None

    print("\n" + header + "\n")
    for r in results:
        print(("  ok    " if r["pass"] else "  FAIL  ") + r["name"]
              + ("" if r["pass"] else "\n        " + _reason(r)))
    if prev:
        was = {k: v["pass"] for k, v in prev["cases"].items()}
        turned = [r["name"] for r in results if was.get(r["name"]) is True and not r["pass"]]
        fixed = [r["name"] for r in results if was.get(r["name"]) is False and r["pass"]]
        print(f"\nLast full run ({prev['at'][:10]}): {prev['passed']}/{prev['total']}.")
        if turned:
            print("  newly failing: " + ", ".join(turned))
        if fixed:
            print("  newly holding: " + ", ".join(fixed))

    write_last_run(results, header)
    row = {"at": datetime.now().isoformat(timespec="seconds"), "rules": rules_label,
           "rules_sha": hashlib.sha1(voice.encode()).hexdigest()[:10],
           "model": model_label, "judge": JUDGE_MODEL, "full": full, "passed": passed,
           "total": len(results),
           "cases": {r["name"]: {"pass": r["pass"], "why": _reason(r)}
                     for r in results}}
    with open(HISTORY, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"\nRewrites: {os.path.relpath(LAST_RUN, os.path.dirname(BRAIN))}")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

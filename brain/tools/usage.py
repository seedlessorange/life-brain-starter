#!/usr/bin/env python3
"""brain/tools/usage.py — one ledger for every model call the brain makes.

    python3 brain/tools/usage.py              # today, this week, by job, by model
    python3 brain/tools/usage.py --days 30    # a longer window
    python3 brain/tools/usage.py --json       # for the page

Before this, usage was recorded in two places that each knew half the story:
`.agent-runs.json` had tokens but no cost and only page-started runs, and
`sessions.json` had cost but no tokens. The morning run, the night shift and
draft revisions recorded nothing at all, so the honest answer to "how much did
yesterday cost" was "no idea".

Everything writes here now, through `record()`. The file is append-only JSON
Lines: a crashed run loses its own line and nothing else, and a year of daily
use is well under a megabyte.

**Recording must never break the thing being recorded.** `record()` swallows
every error, because a full disk is not a reason for the morning plan to fail.

The money is a SIZE SIGNAL, not a bill. On a subscription nothing is charged;
the dollar figure is what these tokens would have cost at published API rates,
which is the only stable way to compare a Haiku run against an Opus one.
"""

import argparse
import json
import os
import sys
import time
from collections import defaultdict
from datetime import datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
BRAIN = os.path.dirname(HERE)
LEDGER = os.path.join(BRAIN, ".usage.jsonl")

# Per million tokens, in USD. Only used when a run does not report its own
# total_cost_usd — Claude Code usually does, and its number wins.
RATES = {
    "haiku":  {"in": 1.00, "out": 5.00,  "cache_read": 0.10, "cache_write": 1.25},
    "sonnet": {"in": 3.00, "out": 15.00, "cache_read": 0.30, "cache_write": 3.75},
    "opus":   {"in": 5.00, "out": 25.00, "cache_read": 0.50, "cache_write": 6.25},
    # Fable/Mythos tier sits above Opus — booking it at Sonnet rates would
    # make the ledger quietly understate a run by 3x.
    "fable":  {"in": 10.00, "out": 50.00, "cache_read": 1.00, "cache_write": 12.50},
    # A local Ollama model bills nobody; the row exists so those calls land
    # in the ledger as what they are instead of being priced as Sonnet.
    "ollama": {"in": 0.00, "out": 0.00, "cache_read": 0.00, "cache_write": 0.00},
    # Codex and Gemini (agents.py) bill their owner's own plan. Their rows
    # keep the token counts and leave the price out rather than guess it
    # at Claude's rates.
    "codex":  {"in": 0.00, "out": 0.00, "cache_read": 0.00, "cache_write": 0.00},
    "gemini": {"in": 0.00, "out": 0.00, "cache_read": 0.00, "cache_write": 0.00},
}
DEFAULT_MODEL = "sonnet"        # what Claude Code picks when nothing is passed

# The models a picker may offer, and what the CLI wants to be called for each.
# Claude Code takes a short alias for the three it ships with; Fable has none
# (`--model fable` comes back 404) and goes by its full name. Every picker in
# the brain reads this list, so adding a model is one edit here — the server,
# the Sessions page and the night shift all agree by construction.
PICKABLE = ("haiku", "sonnet", "opus", "fable")
CLI_ID = {"fable": "claude-fable-5"}


# What each preset means, switch by switch. serve.py's ai_features() builds
# on this table, and a tool that decides for itself whether to spend (the
# morning extras) asks switch(), so the page and the tools cannot disagree.
PRESETS = {
    "careful": {"morning": False, "model": "haiku", "openers": False,
                "news": True, "recordings": False, "extras": False},
    "full": {"morning": True, "model": "sonnet", "openers": True,
             "news": True, "recordings": True, "extras": True},
}


def preset(cfg):
    return "careful" if (cfg or {}).get("ai") in ("low", "careful", "pro") else "full"


def switch(key, cfg=None):
    """Whether one of the Usage page's on/off switches is on: her explicit
    On or Off, else what the preset says."""
    if cfg is None:
        try:
            with open(os.path.join(BRAIN, "config.json"), encoding="utf-8") as f:
                cfg = json.load(f)
        except Exception:
            cfg = {}
    ov = (cfg.get("ai_features") or {}).get(key)
    if isinstance(ov, bool):
        return ov
    return bool(PRESETS[preset(cfg)].get(key, True))


def cli_model(name):
    """What to pass to `claude --model` for a picked name."""
    return CLI_ID.get(name, name)


def _family(model):
    """'claude-sonnet-5' and 'sonnet' are the same row in the rate table."""
    m = (model or "").lower()
    for name in ("ollama", "codex", "gemini"):
        if m.startswith(name):
            return name
    for name in ("haiku", "sonnet", "opus", "fable", "mythos"):
        if name in m:
            return "fable" if name == "mythos" else name
    return DEFAULT_MODEL


def estimate_cost(model, tokens):
    r = RATES[_family(model)]
    return round(
        (tokens.get("in", 0) / 1e6) * r["in"]
        + (tokens.get("out", 0) / 1e6) * r["out"]
        + (tokens.get("cache_read", 0) / 1e6) * r["cache_read"]
        + (tokens.get("cache_write", 0) / 1e6) * r["cache_write"], 4)


# A run is a Claude session working the brain: a page run, the 7am plan, the
# night shift, or a conversation turn. Every other line is a small call, one
# no-tools answer from llm.py (a task-wording check, a Pen rewrite, a draft
# reword). On 8 Oct, 145 small calls came to 14k tokens, less than one
# conversation turn, and each had counted as a run against the daily limit.
RUN_KINDS = ("run", "morning", "night")


def is_run(row):
    kind = row.get("kind")
    return kind in RUN_KINDS or (
        kind == "session"
        and str(row.get("label") or "").startswith("conversation"))


def _plan_change(secs):
    """How the plan's meters moved across a run that ends now and took
    `secs`: {"w": [before, after], "h": [before, after]}, either one only
    when both readings fall in the same window. None when there is no
    reading from the run's start or no fresh one now.

    Her own Claude use in the same minutes moves the meters too, so one
    run's figure is an upper bound; the page only ever shows an average."""
    if (secs or 0) > STALL_SECS:
        return None
    import plan_usage as PU
    before = PU.reading_before(time.time() - (secs or 0))
    if not before:
        return None
    after = PU.status(force=True, timeout=4)
    if not after.get("fresh") or time.time() - float(after.get("at") or 0) > 120:
        return None
    out = {}
    for short, key in (("w", "week"), ("h", "five_hour")):
        m = after.get(key) or {}
        if (before.get(short) is not None and m.get("pct") is not None
                and PU.same_window(before.get(short + "r"), m.get("resets"))):
            out[short] = [before[short], m["pct"]]
    return out or None


def record(kind, label, model="", usage=None, secs=0, cost=None, ok=True,
           turns=None, flags=None):
    """Append one line. Never raises — see the module docstring.

    kind    run | session | revise | morning | night
    label   the job, the conversation, the draft — whatever names it for a human
    usage   a stream-json `usage` dict, or any dict with the same key names
    cost    total_cost_usd if the run reported one; estimated otherwise
    flags   short strings from llm.py's text check ("redone", "still: …"),
            so the times text for someone else needed fixing can be counted
    """
    try:
        u = usage or {}
        tokens = {
            "in": u.get("input_tokens") or 0,
            "out": u.get("output_tokens") or 0,
            "cache_read": u.get("cache_read_input_tokens") or 0,
            "cache_write": u.get("cache_creation_input_tokens") or 0,
        }
        row = {
            "at": datetime.now().isoformat(timespec="seconds"),
            "kind": kind,
            "label": (label or "")[:120],
            "model": _family(model),
            **tokens,
            "total": sum(tokens.values()),
            "secs": round(secs or 0),
            # `is not None`, not truthiness: a run that honestly reports
            # $0.00 must not be silently replaced with an estimate.
            "cost": round(cost, 4) if cost is not None else estimate_cost(model, tokens),
            "ok": bool(ok),
        }
        if turns:
            row["turns"] = turns
        if flags:
            row["flags"] = [str(x)[:120] for x in list(flags)[:6]]
        if is_run(row):
            try:
                plan = _plan_change(secs)
            except Exception:                           # noqa: BLE001
                plan = None
            if plan:
                row["plan"] = plan
        with open(LEDGER, "a", encoding="utf-8") as f:
            f.write(json.dumps(row) + "\n")
        return row
    except Exception:
        return None


def load(days=None):
    """Every row, newest last. A malformed line is skipped, not fatal — the
    ledger is appended to by several processes and a torn write must not make
    the whole history unreadable."""
    rows = []
    cutoff = ((datetime.now() - timedelta(days=days)).isoformat()
              if days else "")
    try:
        with open(LEDGER, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except ValueError:
                    continue
                if cutoff and (row.get("at") or "") < cutoff:
                    continue
                rows.append(row)
    except OSError:
        pass
    return rows


# A run's seconds are wall-clock, and a model call hangs rather than fails
# while the Mac sleeps: the 7am plan has logged 2, 5 and 35 hours for a job
# that takes two to four minutes awake. Nothing the brain runs does real work
# for this long, so a longer run counts as stalled and its time is left out
# of "secs" — the rows keep the raw number (28 Sep review, U1).
STALL_SECS = 15 * 60
# A job's share of the week is shown once this many of its runs were
# measured: the meter moves in whole points, so one run says little.
MIN_MEASURED = 3


def _week_moves(rows):
    """Each measured run's change in the weekly meter, in points."""
    out = []
    for r in rows:
        w = (r.get("plan") or {}).get("w") if isinstance(r.get("plan"), dict) else None
        if isinstance(w, list) and len(w) == 2:
            try:
                out.append(max(0.0, float(w[1]) - float(w[0])))
            except (TypeError, ValueError):
                continue
    return out


def _sum(rows):
    stalled = [r for r in rows if (r.get("secs") or 0) > STALL_SECS]
    moves = _week_moves(rows)
    return {
        "calls": len(rows),
        "runs": sum(1 for r in rows if is_run(r)),
        "measured": len(moves),
        "week_pct": (round(sum(moves) / len(moves), 2)
                     if len(moves) >= MIN_MEASURED else None),
        "tokens": sum(r.get("total") or 0 for r in rows),
        "out": sum(r.get("out") or 0 for r in rows),
        "cost": round(sum(r.get("cost") or 0 for r in rows), 2),
        "secs": sum(r.get("secs") or 0 for r in rows
                    if (r.get("secs") or 0) <= STALL_SECS),
        "stalled": len(stalled),
        "stalled_secs": sum(r.get("secs") or 0 for r in stalled),
    }


def summary(days=7):
    """What the page and the CLI both read."""
    rows = load(days)
    today = datetime.now().date().isoformat()
    by_day, by_kind, by_model = defaultdict(list), defaultdict(list), defaultdict(list)
    for r in rows:
        by_day[(r.get("at") or "")[:10]].append(r)
        by_kind[r.get("label") or r.get("kind")].append(r)
        by_model[r.get("model") or "?"].append(r)
    # "average day" divides by the window it claims to average over, not by
    # days-with-data — 2 busy days out of 7 is not a 7-day average.
    days_seen = days or len(by_day) or 1
    week = _sum(rows)
    return {
        "days": days,
        "today": _sum(by_day.get(today, [])),
        "window": week,
        "per_day": {k: round(v / days_seen, 2) if k == "cost"
                    else round(v / days_seen) for k, v in week.items()
                    if k not in ("week_pct", "measured")},
        "by_day": {d: _sum(v) for d, v in sorted(by_day.items())},
        "by_job": {k: _sum(v) for k, v in
                   sorted(by_kind.items(), key=lambda kv: -_sum(kv[1])["cost"])},
        "by_model": {k: _sum(v) for k, v in by_model.items()},
    }


def runs_today():
    """Today's number of runs (is_run: small calls left out): the "Today: N
    runs" card on the Usage page, and what a runs-a-day limit is measured
    against. Both come from summary()'s `today`, so the card and the limit
    cannot disagree."""
    return summary(1)["today"]["runs"]


def _tok(n):
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n // 1000}k"
    return str(n)


def record_result_file(path, kind, label, model=""):
    """Record a `claude -p --output-format json` result, and print its text.

    This is how the shell scripts reach the ledger: they redirect Claude's JSON
    to a file, then hand it here. Printing the text back means the morning and
    night logs stay readable prose rather than a wall of JSON — the reason
    those runs were never recorded in the first place was that switching to
    JSON would have made their logs useless.
    """
    try:
        with open(path, encoding="utf-8") as f:
            ev = json.load(f)
    except Exception:
        return 1
    if isinstance(ev, list):                     # some versions emit an array
        ev = next((e for e in reversed(ev) if e.get("type") == "result"), {})
    # A Codex or Gemini run (agents.py) names itself; the tier the script
    # passed was only Claude's name for the size it wanted.
    own = str(ev.get("model") or "")
    if own.startswith(("codex", "gemini")):
        model = own
    record(kind, label, model=model or ev.get("model") or "",
           usage=ev.get("usage"), secs=(ev.get("duration_ms") or 0) / 1000,
           cost=ev.get("total_cost_usd"), ok=not ev.get("is_error"),
           turns=ev.get("num_turns"))
    text = ev.get("result") or ""
    if text:
        print(text)
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--record", metavar="FILE",
                    help="record a claude -p --output-format json result file")
    ap.add_argument("--kind", default="run")
    ap.add_argument("--label", default="")
    ap.add_argument("--model", default="")
    args = ap.parse_args()

    if args.record:
        return record_result_file(args.record, args.kind,
                                  args.label or args.kind, args.model)

    s = summary(args.days)
    if args.json:
        print(json.dumps(s, indent=2))
        return 0

    if not s["window"]["calls"]:
        print("Nothing recorded yet. The ledger fills as runs happen.")
        print(f"({LEDGER})")
        return 0

    def line(name, d):
        print(f"  {name:<22} {d['runs']:>4} runs {d['calls'] - d['runs']:>4} small"
              f"  {_tok(d['tokens']):>7}  ${d['cost']:>6.2f}"
              f"  {d['secs'] // 60}m{d['secs'] % 60:02d}s"
              + (f"  ~{d['week_pct']:.1f}% of the week each"
                 if d.get("week_pct") is not None else ""))

    print(f"\nLast {args.days} days")
    line("total", s["window"])
    line("today", s["today"])
    p = s["per_day"]
    print(f"  {'average day':<22} {p['runs']:>4} runs {p['calls'] - p['runs']:>4} small"
          f"  {_tok(p['tokens']):>7}  ${p['cost']:>6.2f}")

    print("\nBy job")
    for k, v in list(s["by_job"].items())[:12]:
        line(k, v)

    print("\nBy model")
    for k, v in sorted(s["by_model"].items(), key=lambda kv: -kv[1]["cost"]):
        line(k, v)

    print("\nBy day")
    for k, v in s["by_day"].items():
        line(k, v)

    print("\nThe dollars are what these tokens would cost at API rates — a size")
    print("signal for comparing runs. On a subscription nothing is billed;")
    print("`python3 brain/tools/plan_usage.py` shows where the plan stands.\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())

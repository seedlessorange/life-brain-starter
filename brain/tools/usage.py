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
}
DEFAULT_MODEL = "sonnet"        # what Claude Code picks when nothing is passed


def _family(model):
    """'claude-sonnet-5' and 'sonnet' are the same row in the rate table."""
    m = (model or "").lower()
    if m.startswith("ollama"):
        return "ollama"
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


def record(kind, label, model="", usage=None, secs=0, cost=None, ok=True,
           turns=None):
    """Append one line. Never raises — see the module docstring.

    kind    run | session | revise | morning | night
    label   the job, the conversation, the draft — whatever names it for a human
    usage   a stream-json `usage` dict, or any dict with the same key names
    cost    total_cost_usd if the run reported one; estimated otherwise
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


def _sum(rows):
    return {
        "calls": len(rows),
        "tokens": sum(r.get("total") or 0 for r in rows),
        "out": sum(r.get("out") or 0 for r in rows),
        "cost": round(sum(r.get("cost") or 0 for r in rows), 2),
        "secs": sum(r.get("secs") or 0 for r in rows),
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
                    else round(v / days_seen) for k, v in week.items()},
        "by_day": {d: _sum(v) for d, v in sorted(by_day.items())},
        "by_job": {k: _sum(v) for k, v in
                   sorted(by_kind.items(), key=lambda kv: -_sum(kv[1])["cost"])},
        "by_model": {k: _sum(v) for k, v in by_model.items()},
    }


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
        print(f"  {name:<22} {d['calls']:>4} calls  {_tok(d['tokens']):>7}"
              f"  ${d['cost']:>6.2f}  {d['secs'] // 60}m{d['secs'] % 60:02d}s")

    print(f"\nLast {args.days} days")
    line("total", s["window"])
    line("today", s["today"])
    p = s["per_day"]
    print(f"  {'average day':<22} {p['calls']:>4} calls  {_tok(p['tokens']):>7}"
          f"  ${p['cost']:>6.2f}")

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
    print("`/usage` inside Claude Code is what shows your plan limits.\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())

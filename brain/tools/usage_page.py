#!/usr/bin/env python3
"""Build brain/usage.html — what Claude spends here, and a switch for each
thing that spends.

    python3 brain/tools/build.py     # builds this page too

GENERATED. Never hand-edit usage.html.

Why this page exists: the Careful/Full control on the Claude tab is all or
nothing, which is the wrong shape for someone on a Pro plan — they may want
the morning plan OFF but Sonnet ON, or the other way round. This page gives
each spending path its own switch, shows where the plan stands (the
five-hour window and the week, the numbers /usage shows in Claude Code, from
plan_usage.py), and shows the ledger, which otherwise only exists as a
terminal command.

The switches write `ai_features` in config.json through the local server.
A switch left on "Follow the mode" does whatever Careful/Full says; an
explicit On/Off wins over the mode. The server side lives in serve.py
(`ai_features()`, /api/usage, /api/aifeature); the morning script and the
model pickers read the same config keys, so the page, the scheduler and the
runs can never disagree.
"""

import json
import os
import re
import sys
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import chrome as CHROME      # noqa: E402

BRAIN = os.path.dirname(HERE)
OUT = os.path.join(BRAIN, "usage.html")


def build(cfg=None):
    import build as B        # already loaded when called from build.py
    if cfg is None:
        try:
            with open(os.path.join(BRAIN, "config.json"), encoding="utf-8") as f:
                cfg = json.load(f)
        except Exception:
            cfg = {}

    night = cfg.get("night") or {}
    # Said as what each job does, not as its slash-command (28 Sep review).
    from tab_hood import night_plain
    night_jobs = night_plain(night.get("jobs"))

    # The page's wording names the agent the brain runs (agents.say); the
    # plan meter and its notes read Claude's own plan whatever runs the
    # brain, so they are written __CLAUDE__ and stay Claude.
    import agents
    page = agents.say(TEMPLATE).replace("__CLAUDE__", "Claude")
    # Codex and Gemini have no plan reading (plan_usage.py), so the plan
    # limit row hides (its script still fills it) and the note on how
    # Claude's plan meters goes.
    claude = agents.provider() == "claude"
    page = page.replace("__PLANROW__", "" if claude else ' style="display:none"')
    page = page.replace("__METERSUM__", "How a subscription meters Claude"
                        if claude else "How heavy each run is")
    page = re.sub(r"<!--claude-only-->(.*?)<!--/claude-only-->",
                  r"\1" if claude else "", page, flags=re.S)
    page = page.replace("__STYLE__", (cfg.get("appearance", {}) or {}).get("style", "workroom"))
    page = page.replace("__PALETTE__", B.palette_css(cfg))
    # The gear's sub-row rides under the bar, on main's measure, so it
    # holds still between Settings, Usage, Privacy and Conversations
    # (8 Oct: inside this page's narrow column it jumped 256px).
    page = page.replace("__HEADER__", CHROME.header_html(
        current="claude", owner=cfg.get("owner", ""),
        sub_html=CHROME.claude_subnav("usage")))
    page = page.replace("__SUBNAV__", "")
    page = page.replace("__ASK__", CHROME.ask_block())
    page = page.replace("__NIGHTJOBS__", night_jobs)
    page = page.replace("__NIGHTAT__", night.get("at") or "01:00")
    page = page.replace("__DATE__", date.today().isoformat())
    page = page.replace("__CORRECTIONS__", corrections_line())

    # Same publish gate as the other pages: a page whose script cannot parse
    # is worse than a stale one.
    from shutil import which
    node = which("node")
    if node:
        import subprocess as _sp
        import tempfile as _tf
        for js in re.findall(r"<script>(.*?)</script>", page, re.S):
            with _tf.NamedTemporaryFile("w", suffix=".js", delete=False,
                                        encoding="utf-8") as tmp:
                tmp.write(js)
            try:
                r = _sp.run([node, "--check", tmp.name], capture_output=True,
                            text=True, timeout=20)
                if r.returncode != 0:
                    raise SystemExit("REFUSING to write usage.html — its "
                                     "script does not parse:\n"
                                     + r.stderr.strip()[:600])
            finally:
                os.unlink(tmp.name)

    with open(OUT, "w", encoding="utf-8") as f:
        f.write(page)
    return OUT


def corrections_line():
    """One line from corrections.py's counts (evals/corrections-rate.json):
    the share of sessions she had to correct, latest two weeks. Nothing when
    the file is missing or holds no sessions."""
    from datetime import timedelta
    from html import escape
    try:
        with open(os.path.join(BRAIN, "evals", "corrections-rate.json"),
                  encoding="utf-8") as f:
            d = json.load(f)
        weeks = [w for w in d.get("weeks", []) if w.get("sessions")][-2:]
    except Exception:
        return ""
    if not weeks:
        return ""
    today = date.today()
    names = {"%d-W%02d" % today.isocalendar()[:2]: "this week so far",
             "%d-W%02d" % (today - timedelta(days=7)).isocalendar()[:2]:
             "last week"}
    parts = []
    for w in reversed(weeks):
        try:
            day = date.fromisoformat(w["start"])
            name = names.get(w["week"]) or "the week of %d %s" % (
                day.day, day.strftime("%b"))
            parts.append("%d%% %s (%d of %d)" % (
                round(w["corrected"] * 100 / w["sessions"]), name,
                w["corrected"], w["sessions"]))
        except Exception:
            continue
    if not parts:
        return ""
    text = "Sessions where you had to correct Claude: " + ", ".join(parts) + "."
    base = (d.get("baseline") or {}).get("rate")
    if isinstance(base, (int, float)):
        text += " The audit found %d%%." % round(base * 100)
    return '<p class="usub" id="corrections">' + escape(text) + "</p>"


TEMPLATE = """<!doctype html>
<html lang="en" data-style="__STYLE__"><head>
<script>try{var _bs=localStorage.getItem('brain-style');
if(_bs)document.documentElement.setAttribute('data-style',_bs);}catch(e){}</script>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>Usage &middot; the brain</title>
<link rel="icon" href="logo-192.png?v=5" type="image/png">
<link rel="apple-touch-icon" href="logo-180.png?v=5">
<link rel="stylesheet" href="appearance.css">
<style>
__PALETTE__
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--paper);color:var(--ink);
  font:400 var(--t-base)/1.6 var(--sans)}
a{color:var(--ink)}
""" + CHROME.NAV_CSS + CHROME.HEADER_CSS + """
.uwrap{max-width:860px;margin:0 auto;padding:16px 20px 80px}
.uwrap h1{font:600 var(--t-2xl)/1.2 var(--serif);letter-spacing:-.01em;margin:18px 0 10px}
.uwrap h2{font:600 var(--t-lg)/1.3 var(--serif);margin:40px 0 6px}
.ulede{color:var(--dim);max-width:62ch;margin:0 0 6px}
.usub{color:var(--faint);font-size:var(--t-sm);max-width:62ch;margin:0 0 14px}
.ucards{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:10px;margin:14px 0}
.ucard{background:var(--surface);border:1px solid var(--line);border-radius:var(--r-card);padding:14px 16px}
.ucard .ulab{font-size:var(--t-xs);font-weight:700;letter-spacing:.07em;text-transform:uppercase;color:var(--faint)}
.ucard .ubig{font:600 var(--t-xl)/1.2 var(--serif);margin:4px 0 2px}
.ucard .usml{font-size:var(--t-sm);color:var(--dim)}
.ubars{display:flex;align-items:flex-end;gap:4px;height:74px;margin:14px 2px 4px}
.ubars i{flex:1;min-width:6px;background:var(--sunken,var(--surface));
  border:1px solid var(--line);border-bottom-width:2px;border-radius:4px 4px 0 0;display:block}
.ubars i.hot{background:var(--greenbg,var(--surface));border-color:var(--green,var(--dim))}
.umeter{position:relative;display:block;height:8px;border-radius:4px;margin:10px 0 8px;
  background:var(--sunken,var(--line))}
.umeter i{position:absolute;left:0;top:0;bottom:0;border-radius:4px;background:var(--green,var(--ink))}
.umeter.wait i{background:var(--wait,var(--ink))}
.umeter.bad i{background:var(--bad,var(--ink))}
/* where the plan limit sits, so the line is visible before it is crossed */
.umeter b{position:absolute;top:-4px;bottom:-4px;width:2px;margin-left:-1px;background:var(--ink);opacity:.45}
.ubarlab{display:flex;justify-content:space-between;font-size:var(--t-xs);color:var(--faint);margin:0 2px 8px}
table.ujobs{width:100%;border-collapse:collapse;margin:10px 0 4px;font-size:var(--t-sm)}
table.ujobs td{padding:6px 8px 6px 0;border-top:1px solid var(--line);vertical-align:top}
table.ujobs td:last-child{text-align:right;white-space:nowrap;color:var(--dim)}
.unote{font-size:var(--t-xs);color:var(--faint);max-width:62ch}
.uoffline{background:var(--surface);border:1px dashed var(--line2);border-radius:var(--r-card);
  padding:14px 16px;color:var(--dim);font-size:var(--t-sm)}
.urow{display:flex;gap:14px;align-items:flex-start;justify-content:space-between;
  padding:16px 0;border-top:1px solid var(--line);flex-wrap:wrap}
.urow:first-of-type{border-top:0}
.uinfo{flex:1 1 320px;min-width:260px}
.uinfo b{font-weight:650}
.udetail{display:block;color:var(--dim);font-size:var(--t-sm);max-width:56ch;margin-top:2px}
.unow{display:block;color:var(--faint);font-size:var(--t-xs);margin-top:5px}
/* the mechanics of a switch are read once; the label is read every time */
.uwhy{margin-top:6px}
.uwhy>summary{display:inline-block;list-style:none;cursor:pointer;
  font-size:var(--t-xs);color:var(--faint);border-bottom:1px dotted var(--line2)}
.uwhy>summary::-webkit-details-marker{display:none}
.uwhy>summary::marker{content:""}
.uwhy>summary:hover{color:var(--dim)}
.uwhy p{color:var(--dim);font-size:var(--t-sm);max-width:56ch;margin:7px 0 0}
.udoc>summary{display:block;list-style:none;cursor:pointer;
  font:600 var(--t-lg)/1.3 var(--serif);margin:40px 0 6px}
.udoc>summary::-webkit-details-marker{display:none}
.udoc>summary::marker{content:""}
.udoc>summary::after{content:" \\203a";color:var(--faint);display:inline-block;
  transition:transform .15s}
.udoc[open]>summary::after{transform:rotate(90deg)}
/* its look, like every switch's, is switches.py's */
.useg{display:inline-flex;flex:none}
.ubtn{font:600 var(--t-xs)/1 var(--sans);padding:7px 13px;border:1px solid var(--line2);
  border-radius:var(--r-btn);background:var(--surface);color:var(--ink);cursor:pointer;margin-left:4px}
.ubtn:hover{border-color:var(--green,var(--dim))}
.ubtn:disabled{opacity:.45;cursor:default}
.ureport{background:var(--surface);border:1px solid var(--line);border-radius:var(--r-card);
  padding:4px 18px 10px;margin:12px 0 0;font-size:var(--t-sm);line-height:1.6}
.ureport h3{font:600 var(--t-base)/1.3 var(--serif);margin:14px 0 4px}
.ureport p{margin:6px 0}
.ureport ul{margin:6px 0;padding-left:20px}
.ureport li{margin:0 0 4px}
.ureport code{font-family:ui-monospace,Menlo,monospace;font-size:.9em;
  background:var(--sunken,var(--paper));padding:1px 4px;border-radius:4px}
.ureport .uwhen{font-size:var(--t-xs);color:var(--faint);margin:10px 0 0}
.ufree{margin:8px 0 0;padding:0;list-style:none;columns:2;column-gap:28px;font-size:var(--t-sm);color:var(--dim)}
.ufree li{margin:0 0 6px;break-inside:avoid}
.ufree li::before{content:"\\2713\\00a0\\00a0";color:var(--green,var(--dim))}
.uweights{margin:10px 0 0;padding:0;list-style:none;font-size:var(--t-sm)}
.uweights li{display:flex;justify-content:space-between;gap:16px;padding:7px 0;border-top:1px solid var(--line)}
.uweights li:first-child{border-top:0}
.uweights .uw{color:var(--dim);white-space:nowrap}
@media(max-width:640px){.ufree{columns:1}
  /* the numbers wrap on a phone; nowrap pushed the page 75px wide */
  table.ujobs td:last-child{white-space:normal;min-width:9em}
  /* a weight that cannot sit beside its job goes under it: at 360 "tiny —
     one Haiku call…" ran 12px past the edge (28 Sep) */
  .uweights li{flex-wrap:wrap;row-gap:2px}}
</style>
</head><body>
__HEADER__
<main class="uwrap">
__SUBNAV__

<h1>What Claude spends here</h1>
<p class="ulede">The brain runs on your Claude subscription. Most of it (the
pages, the syncing, the tickboxes, the reminders) runs no AI at all.
This page covers the part that does: where your plan stands, what the brain
ran lately, and a switch for each thing that spends.</p>

<h2>Your plan</h2>
<div id="plan"></div>
<p class="usub">The same numbers <code>/usage</code> shows in __CLAUDE__ Code. They
count everything you do with __CLAUDE__, not only the brain.</p>

<!-- "Lately", not "This week": the cards under it are today, 7 and 30 days. -->
<h2>Lately</h2>
<div id="live">
  <div class="uoffline">Live numbers need the brain&rsquo;s local server.
  Open the page through <b>Open Brain</b> and they appear here.</div>
</div>
__CORRECTIONS__

<h2>Start from your plan</h2>
<p class="usub">One tap sets everything below to the shape that fits your
subscription. Change any switch afterwards and this reads
&ldquo;your own mix&rdquo;.</p>

<div class="urow" data-plan-row>
  <div class="uinfo"><b>Recommended settings</b>
    <span class="udetail">Pro keeps the brain inside a small allowance;
    Max lets it run.</span>
    <span class="unow" id="now-plan"></span>
    <details class="uwhy"><summary>what each one sets</summary>
    <p><b>Pro</b>: no 7am plan and no morning extras, Haiku is the default
    model, and once your plan passes 75% a run you start from a button asks
    first (after 10 runs in a day when the plan can&rsquo;t be read).
    <b>Max</b>: the morning plan writes itself with its extras, Sonnet is the
    default, openers get prepared, no limit.</p>
    <p>Neither one touches the night shift, which needs a setup step a
    button can&rsquo;t take, or your privacy settings, which have
    <a href="privacy.html">their own page</a>.</p></details></div>
  <span class="useg" id="planseg">
    <button data-plan="pro" disabled>Pro</button>
    <button data-plan="max" disabled>Max</button>
  </span>
</div>

<h2>The switches</h2>
<p class="usub">An explicit On or Off on a switch wins over the preset.
Changes apply from the next run.</p>

<div class="urow" data-mode-row>
  <div class="uinfo"><b>The preset</b>
    <span class="udetail">Careful fits a Pro plan, Full fits Max.</span>
    <span class="unow" id="now-mode"></span>
    <details class="uwhy"><summary>what each one does</summary>
    <p><b>Careful</b>: the 7am plan and the morning extras are off, and
    Haiku is the default. The news breakdowns still run unless you switch
    them off. <b>Full</b>: the morning plan runs itself with its extras,
    Sonnet is the default, and openers get prepared.</p></details></div>
  <span class="useg" id="modeseg">
    <button data-mode="careful" disabled>Careful</button>
    <button data-mode="full" disabled>Full</button>
  </span>
</div>

<div class="urow" data-key="morning">
  <div class="uinfo"><b>The 7am plan</b>
    <span class="udetail">Writes today&rsquo;s plan before you&rsquo;re up.</span>
    <span class="unow" id="now-morning"></span>
    <details class="uwhy"><summary>what it costs, what happens if it&rsquo;s off</summary>
    <p>One small-to-medium run every day, so it is the steadiest cost here. Off, the
    morning still syncs and rebuilds for free, and &ldquo;Refresh today&rsquo;s
    plan&rdquo; stays a manual choice.</p></details></div>
  <span class="useg" data-seg="morning">
    <button data-v="auto" disabled>Follow the preset</button>
    <button data-v="on" disabled>On</button>
    <button data-v="off" disabled>Off</button>
  </span>
</div>

<div class="urow" data-key="model">
  <div class="uinfo"><b>Default model</b>
    <span class="udetail">What a run uses when you don&rsquo;t pick one.</span>
    <span class="unow" id="now-model"></span>
    <details class="uwhy"><summary>how the three compare</summary>
    <p>Haiku costs roughly a tenth of Sonnet and handles routine queue work;
    Sonnet is the all-rounder; Opus is the most capable and drains a Pro
    allowance fastest. A model picked on a queue card always wins. The two
    mechanical jobs, folder sync and the project scan, default to Haiku
    unless you set a model here.</p></details></div>
  <span class="useg" data-seg="model">
    <button data-v="auto" disabled>Follow the preset</button>
    <button data-v="haiku" disabled>Haiku</button>
    <button data-v="sonnet" disabled>Sonnet</button>
    <button data-v="opus" disabled>Opus</button>
  </span>
</div>

<div class="urow" data-key="openers">
  <div class="uinfo"><b>Openers</b>
    <span class="udetail">The morning plan also preps the day&rsquo;s tasks.</span>
    <span class="unow" id="now-openers"></span>
    <details class="uwhy"><summary>what &ldquo;preps&rdquo; means</summary>
    <p>It looks up the number, drafts the first message, researches the train
    times. Costs a little more per run; never sends anything.</p></details></div>
  <span class="useg" data-seg="openers">
    <button data-v="auto" disabled>Follow the preset</button>
    <button data-v="on" disabled>On</button>
    <button data-v="off" disabled>Off</button>
  </span>
</div>

<div class="urow" data-key="recordings">
  <div class="uinfo"><b>Recordings</b>
    <span class="udetail">Twice a day, new voice memos get filed into the brain.</span>
    <span class="unow" id="now-recordings"></span>
    <details class="uwhy"><summary>what it costs</summary>
    <p>Transcribing is free: Whisper runs on this Mac. Filing is a Claude
    run, once per pass and only when something new was recorded. Off, the
    transcripts still get made and wait for the night run or Run now.</p></details></div>
  <span class="useg" data-seg="recordings">
    <button data-v="auto" disabled>Follow the preset</button>
    <button data-v="on" disabled>On</button>
    <button data-v="off" disabled>Off</button>
  </span>
</div>

<div class="urow" data-key="news">
  <div class="uinfo"><b>News breakdowns</b>
    <span class="udetail">A plain-language explainer on the topics
    you&rsquo;re learning.</span>
    <span class="unow" id="now-news"></span>
    <details class="uwhy"><summary>the smallest thing on this page</summary>
    <p>One Haiku call per learning topic per day, written once and reused by
    every refresh. That is about 2k tokens each, and the only model call the
    morning job makes when the 7am plan is off. Off, the briefing itself still
    arrives; it just stops explaining the jargon.</p></details></div>
  <span class="useg" data-seg="news">
    <button data-v="auto" disabled>Follow the preset</button>
    <button data-v="on" disabled>On</button>
    <button data-v="off" disabled>Off</button>
  </span>
</div>

<div class="urow" data-key="extras">
  <div class="uinfo"><b>Morning extras</b>
    <span class="udetail">Small model calls the morning job makes besides
    the plan.</span>
    <span class="unow" id="now-extras"></span>
    <details class="uwhy"><summary>what they are</summary>
    <p>Clearer wording for task titles that won&rsquo;t read cold, dates
    read from new class slides, the study guides kept up to date, and once a
    week a writing lesson from the drafts you corrected. Each is a small call
    of a few thousand tokens. Off, new slides are still read for dates,
    without a model.</p></details></div>
  <span class="useg" data-seg="extras">
    <button data-v="auto" disabled>Follow the preset</button>
    <button data-v="on" disabled>On</button>
    <button data-v="off" disabled>Off</button>
  </span>
</div>

<div class="urow" data-key="plan_pct"__PLANROW__>
  <div class="uinfo"><b>Plan limit</b>
    <span class="udetail">Once your five-hour window or your week passes
    this share, a run you start from a button asks first.</span>
    <span class="unow" id="now-pct"></span>
    <details class="uwhy"><summary>what it counts, and what it stops</summary>
    <p>It reads the meters at the top of this page, so it counts everything
    you do with __CLAUDE__, not only the brain: past the line, what is left of
    the window stays yours. It only ever stops a run you start from a button,
    and saying yes when it asks lets that run go ahead. The 7am plan and the
    night shift are never blocked.</p>
    <p>When there is no recent reading (__CLAUDE__ Code&rsquo;s sign-in has
    lapsed, or the brain runs on a computer other than a Mac), the run limit
    below takes over.</p></details></div>
  <span class="useg pctseg">
    <button data-pct="" disabled>No limit</button>
    <button data-pct="50" disabled>50%</button>
    <button data-pct="75" disabled>75%</button>
    <button data-pct="90" disabled>90%</button>
  </span>
</div>

<div class="urow" data-key="daily_runs">
  <div class="uinfo"><b>Run limit</b>
    <span class="udetail">After this many runs in a day, a run you start
    from a button asks first.</span>
    <span class="unow" id="now-cap"></span>
    <details class="uwhy"><summary>what it counts, and what it stops</summary>
    <p>It counts the same runs as the Today card at the top: the morning
    plan, each run you start, each night job and each conversation turn.
    Small calls don&rsquo;t count: a Pen rewrite, a draft reword or a
    task-wording check is a few hundred to a few thousand tokens. It only
    ever stops a run you start from a button, and saying yes when it asks
    lets that run go ahead. The scheduled work is never blocked.</p>
    <p>With a plan limit set, this one only counts while the plan can&rsquo;t
    be read.</p></details></div>
  <span class="useg capseg">
    <button data-cap="" disabled>No limit</button>
    <button data-cap="5" disabled>5 runs</button>
    <button data-cap="10" disabled>10 runs</button>
    <button data-cap="20" disabled>20 runs</button>
  </span>
</div>

<div class="urow" data-night-row>
  <div class="uinfo"><b>Night shift</b>
    <span class="udetail">At __NIGHTAT__, while you sleep, it __NIGHTJOBS__.</span>
    <span class="unow" id="now-night"></span>
    <details class="uwhy"><summary>why run it at night at all</summary>
    <p>The heavy work stops competing with your day for the same five-hour
    window. It draws on the same weekly allowance. On Pro, where the
    five-hour window is the limit you reach first, that usually keeps the
    brain and your own work from colliding. In Careful mode it runs on
    Haiku.</p></details></div>
  <span class="useg" id="nightseg">
    <button data-night="on" disabled>On</button>
    <button data-night="off" disabled>Off</button>
  </span>
</div>

<div class="urow" data-privacy-row>
  <div class="uinfo"><b>Privacy</b>
    <span class="udetail">What runs on a timer may open, and what may send,
    has its own page now.</span></div>
  <a class="ubtn" href="privacy.html" style="text-decoration:none">Open Privacy</a>
</div>

<h2>The audit</h2>
<p class="usub">Claude reads its own ledger, the recent runs and a few of
your conversations, then writes up where the usage went, which habits cost
extra, and what would cost less without losing anything. One run, a few
minutes. <button class="ubtn" id="auditrun" disabled>Run the audit</button>
<span class="unow" id="auditnote"></span></p>
<div id="auditbody" class="ureport">
  <p class="unote">No audit yet. The first one appears here after you
  run it, or after you ask Claude for a usage audit.</p>
</div>

<details class="udoc">
<summary>__METERSUM__</summary>
<!--claude-only--><p class="ulede">A Pro or Max plan has no per-use bill. Instead there are two
meters, shared with everything else you do with __CLAUDE__: a <b>five-hour
window</b> (use a lot at once and __CLAUDE__ pauses until the window rolls over)
and a <b>weekly cap</b>. Max is the same system with a bigger allowance
(roughly 5&times; or 20&times; Pro&rsquo;s, depending on the tier).
Anthropic doesn&rsquo;t publish the allowances in tokens, only how much of
each window you have used, which is why this page measures in percent. The
meters at the top are read from Anthropic with __CLAUDE__ Code&rsquo;s own
sign-in, on a Mac.</p><!--/claude-only-->
<p class="ulede">What the brain&rsquo;s runs weigh, roughly:</p>
<ul class="uweights">
  <li><span>Work the queue &middot; Catch me up &middot; Tidy the brain</span>
      <span class="uw">the heavy ones: minutes of model time each</span></li>
  <li><span>The 7am plan</span><span class="uw">about a third of a queue run</span></li>
  <li><span>A conversation turn (Sessions, Ask)</span><span class="uw">small</span></li>
  <li><span>Revising a draft, naming a conversation</span><span class="uw">tiny: one Haiku call, a few thousand tokens</span></li>
  <li><span>A Brain Pen rewrite, a task-wording check</span><span class="uw">tiny: one small call each</span></li>
  <li><span>A study guide update</span><span class="uw">small: one call per new class session</span></li>
</ul>
<p class="usub">Once a few runs of a job have been measured, the table under
Lately gives its share of your week instead.</p>
<p class="usub">The comfortable shape on Pro: one or two batched runs a day on
Haiku or Sonnet, the 7am plan off, and several queue items handled in one run
instead of one run each. On Max, everything on this page can stay on.</p>
</details>

<h2>What never spends</h2>
<p class="usub">These run as plain code and use none of your plan:</p>
<ul class="ufree">
  <li>Rebuilding the pages</li>
  <li>Folder sync every 20 minutes</li>
  <li>Ticking tasks and habits</li>
  <li>Beeper &amp; calendar reading</li>
  <li>The map, rooms and people views</li>
  <li>Deadline &amp; chase reminders</li>
  <li>Bank feed &amp; freshness checks</li>
  <li>LinkedIn import &amp; person tools</li>
</ul>

<p class="unote">Every model call the brain makes writes one line to its
ledger, and the numbers under Lately are read from it live.</p>
</main>
__ASK__
<script>
(function(){
'use strict';
var FEAT = null;

function $(id){ return document.getElementById(id); }
function post(url, body){
  return fetch(url, {method:'POST', headers:{'Content-Type':'application/json'},
                     body: JSON.stringify(body)})
    .then(function(r){ if(!r.ok) throw new Error('The server said no ('+r.status+')');
                       return r.json(); });
}
function tok(n){
  if(!n) return '0';
  if(n >= 1000000) return (n/1000000).toFixed(1) + 'M';
  if(n >= 1000) return Math.round(n/1000) + 'k';
  return String(n);
}
// Minutes as she would say them: "6 min", "1 h 12 min". Stalled runs are
// already out of these seconds (usage.py STALL_SECS).
function mins(s){
  if(!s) return '';
  if(s < 60) return s + ' s of model time';
  var m = Math.round(s/60);
  return (m < 60 ? m + ' min' : Math.floor(m/60) + ' h ' + (m % 60) + ' min')
    + ' of model time';
}
// A server started before the stall count existed sends raw wall-clock
// seconds (a 35-hour "run"), so without the count the minutes stay off.
function timed(v){ return v.secs && v.stalled !== undefined; }
// Day first, like every other date on the pages: "15 Sep".
var MON = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
function dm(ymd){
  var p = String(ymd || '').split('-');
  return p.length === 3 ? (+p[2]) + ' ' + MON[(+p[1]) - 1] : String(ymd || '');
}
// The ledger labels its jobs the way the scripts do ("morning /today",
// "night /scout"); the page says what each one is.
var JOBNAMES = {'morning /today': 'Morning plan', 'today': 'Today\\u2019s plan, by hand',
  'queue': 'Queue', 'night /queue': 'Night queue', 'night /wrap': 'Night wrap-up',
  'night /scout': 'Events scout', 'scout': 'Events scout', 'wrap': 'Wrap-up',
  'brief': 'Catch me up', 'discover': 'Project folder scan', 'sync': 'Folder sync',
  'audit': 'What\\u2019s missing', 'usageaudit': 'Usage audit', 'news': 'News breakdowns',
  'drafteval': 'Draft checks', 'draft revise': 'Revising a draft',
  'naming a conversation': 'Naming a conversation'};
function jobLabel(k){
  if(JOBNAMES[k]) return JOBNAMES[k];
  var m = String(k).match(/^(conversation|project|draft eval):\\s*(.*)$/);
  if(m) return {conversation: 'Conversation', project: 'Run in',
                'draft eval': 'Draft check'}[m[1]] + ': ' + m[2];
  k = String(k).replace(/^(morning|night)\\s+\\//, '$1 ').replace(/^\\//, '');
  return k.charAt(0).toUpperCase() + k.slice(1);
}

// ---- the plan ---------------------------------------------------------------
var DAYS = ['Sunday','Monday','Tuesday','Wednesday','Thursday','Friday','Saturday'];
function hm(d){
  return String(d.getHours()).padStart(2, '0') + ':' + String(d.getMinutes()).padStart(2, '0');
}
function resetWhen(iso, week){
  var d = new Date(iso);
  if(isNaN(d)) return '';
  // Anthropic says 19:59:59.8 for a window that resets at 20:00.
  d = new Date(Math.round(d.getTime() / 60000) * 60000);
  return week ? DAYS[d.getDay()] + ' ' + hm(d) : hm(d);
}
// A reading recent enough for the plan limit to act on (serve.py
// _run_limit_hit uses plan_usage.current, the same thirty minutes).
function usable(p){
  return !!(p && p.at && (p.week || p.five_hour) && Date.now() / 1000 - p.at < 1800);
}
function used(m){
  if(!m) return null;
  // A window whose reset has passed since the reading has rolled over.
  return m.resets && new Date(m.resets) < new Date() ? 0 : Math.round(m.pct);
}
function meterCard(label, m, week, lim){
  var pct = used(m);
  if(pct === null) return '';
  var tone = pct >= 90 ? ' bad' : pct >= (lim || 75) ? ' wait' : '';
  return '<div class="ucard"><span class="ulab">' + label + '</span>'
    + '<div class="ubig">' + pct + '% used</div>'
    + '<span class="umeter' + tone + '" role="meter" aria-valuemin="0" aria-valuemax="100"'
    + ' aria-valuenow="' + pct + '" aria-label="' + label + ' used"><i style="width:'
    + Math.min(100, pct) + '%"></i>' + (lim ? '<b style="left:' + lim + '%"></b>' : '') + '</span>'
    + '<span class="usml">' + (m.resets ? 'Resets ' + resetWhen(m.resets, week) : '')
    + (lim ? (m.resets ? ' \\u00b7 ' : '') + 'asks first at ' + lim + '%' : '') + '</span></div>';
}
function renderPlan(p, f){
  var box = $('plan');
  // Another agent runs the brain (plan_usage.py says off): one line saying
  // so, and the note about /usage under it goes.
  var under = box.nextElementSibling;
  if(under && under.classList.contains('usub')) under.style.display = p && p.off ? 'none' : '';
  if(p && p.off){
    var why = String(p.why || 'this plan has no reading here');
    box.innerHTML = '<div class="uoffline">' + esc(why.charAt(0).toUpperCase() + why.slice(1))
      + '.</div>';
    return;
  }
  if(!p || (!p.week && !p.five_hour)){
    box.innerHTML = '<div class="uoffline">No reading from your plan yet'
      + (p && p.why ? ': ' + esc(p.why) : '') + '. What the brain ran is still counted below.</div>';
    return;
  }
  var lim = (f && f.plan_pct) || 0;
  box.innerHTML = '<div class="ucards">' + meterCard('This week', p.week, true, lim)
    + meterCard('Five-hour window', p.five_hour, false, lim) + '</div>'
    + (p.fresh ? '' : '<p class="unote">Last known reading, ' + ago(p.at)
       + (p.why ? ' (' + esc(p.why) + ')' : '') + '.</p>');
}
function ago(ts){
  var m = Math.round((Date.now() / 1000 - ts) / 60);
  return m < 60 ? m + ' min ago' : Math.round(m / 60) + ' h ago';
}

// ---- live usage -----------------------------------------------------------
// A run is a Claude session working the brain; everything else is a small
// call (usage.py is_run). A server older than the split sends no `runs`.
function runsOf(v){ return v.runs !== undefined ? v.runs : (v.calls || 0); }
function plural(n, word){ return n + ' ' + word + (n === 1 ? '' : 's'); }
function weekShare(x){
  return x < 0.05 ? 'too little to move your week'
    : 'about ' + (x < 1 ? x.toFixed(1) : Math.round(x)) + '% of your week each';
}
function renderUsage(j){
  var w = j.week || {}, m = j.month || {};
  var t = w.today || {}, ww = w.window || {}, mw = m.window || {};
  var html = '<div class="ucards">'
    + card('Today', t)
    + card('Last 7 days', ww)
    + card('Last 30 days', mw)
    + '</div>';

  // one bar per day, last 14 with data-or-not, tallest = busiest.
  // Local dates, not toISOString(): the ledger stamps local time, and a UTC
  // key would move "today" to the wrong bar every evening.
  function ymd(dt){
    return dt.getFullYear() + '-' + String(dt.getMonth() + 1).padStart(2, '0')
      + '-' + String(dt.getDate()).padStart(2, '0');
  }
  var byDay = m.by_day || {}, days = [], d = new Date();
  for(var i = 13; i >= 0; i--){
    days.push(ymd(new Date(d.getTime() - i*86400000)));
  }
  var max = 1, peak = '';
  days.forEach(function(k){ var v = byDay[k]; if(v && v.tokens > max){ max = v.tokens; peak = k; } });
  function dayTip(k, v){
    var r = runsOf(v), small = (v.calls || 0) - r;
    return dm(k) + ': ' + plural(r, 'run')
      + (small ? ' and ' + plural(small, 'small call') : '')
      + ', ' + tok(v.tokens) + ' tokens';
  }
  html += '<div class="ubars">' + days.map(function(k){
    var v = byDay[k] || {tokens:0, calls:0};
    var h = Math.max(3, Math.round(70 * v.tokens / max));
    return '<i class="' + (v.tokens ? 'hot' : '') + '" style="height:' + h + 'px"'
      + ' title="' + esc(dayTip(k, v)) + '" aria-label="' + esc(dayTip(k, v)) + '"></i>';
  }).join('') + '</div>'
  + '<div class="ubarlab"><span>' + dm(days[0]) + '</span><span>today</span></div>'
  // A phone has no hover, so the one number worth knowing is written down.
  + (peak ? '<p class="unote">Busiest of the fortnight: ' + esc(dayTip(peak, byDay[peak]))
     + '. Hover a bar for its day.</p>' : '');

  var jobs = m.by_job || {}, names = Object.keys(jobs).slice(0, 10);
  if(names.length){
    html += '<table class="ujobs">' + names.map(function(k){
      var v = jobs[k], r = runsOf(v);
      var n = r ? plural(r, /^conversation:/.test(k) ? 'turn' : 'run')
                : plural(v.calls, 'small call');
      return '<tr><td>' + esc(jobLabel(k)) + '</td><td>' + n
        + (v.stalled ? ' (' + v.stalled + ' stalled)' : '') + ' \\u00b7 '
        + tok(v.tokens) + ' tokens' + (timed(v) ? ' \\u00b7 ' + mins(v.secs) : '')
        + (v.week_pct !== null && v.week_pct !== undefined
           ? '<br>' + weekShare(v.week_pct) : '') + '</td></tr>';
    }).join('') + '</table>'
    + '<p class="unote">A job&rsquo;s share of your week appears once three of its runs '
    + 'have been measured: the plan is read as each run starts and ends. Your own '
    + '__CLAUDE__ use in the same minutes counts in too, so the shares run high.</p>';
  }
  // Runs that hung while the Mac slept logged hours for minutes of work.
  // Their time is out of every number above; say so once, plainly.
  if(mw.stalled){
    var worst = names.filter(function(k){ return jobs[k].stalled; })
      .sort(function(a, b){ return jobs[b].stalled - jobs[a].stalled; })[0];
    html += '<p class="unote">' + mw.stalled + ' run' + (mw.stalled === 1 ? '' : 's')
      + ' in the last 30 days sat stalled for hours, most likely while the Mac slept'
      + (worst ? ' (' + (jobs[worst].stalled === mw.stalled ? 'all' : jobs[worst].stalled)
         + ' of them the ' + esc(jobLabel(worst).toLowerCase()) + ')' : '')
      + '. Their time is left out of the minutes above.</p>';
  }
  var models = m.by_model || {};
  var mline = Object.keys(models).sort(function(a, b){
      return models[b].calls - models[a].calls; })
    .map(function(k){ return k.charAt(0).toUpperCase() + k.slice(1) + ' '
      + models[k].calls; }).join(', ');
  html += '<p class="unote">' + (mline ? 'Runs by model over 30 days: ' + esc(mline) + '. ' : '')
    + 'Nothing here is a bill: on a subscription these tokens are already '
    + 'paid for. Where you stand on the plan is the meters at the top.</p>';
  $('live').innerHTML = html;
}
function card(label, v){
  var r = runsOf(v), small = (v.calls || 0) - r;
  return '<div class="ucard"><span class="ulab">' + label + '</span>'
    + '<div class="ubig">' + plural(r, 'run') + '</div>'
    + '<span class="usml">' + (small ? plural(small, 'small call') + ' \\u00b7 ' : '')
    + tok(v.tokens || 0) + ' tokens'
    + (timed(v) ? ' \\u00b7 ' + mins(v.secs) : '') + '</span></div>';
}
// Quotes too, so the result is safe inside an attribute as well as text.
function esc(s){ return String(s == null ? '' : s)
  .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
  .replace(/"/g,'&quot;').replace(/'/g,'&#39;'); }

// ---- the audit ------------------------------------------------------------
// Just enough markdown for the report: ## headings, - bullets, **bold**,
// `code`. Anything richer belongs in the file itself, opened in an editor.
function inl(s){
  return esc(s).replace(/\\*\\*(.+?)\\*\\*/g, '<b>$1</b>')
    .replace(/\\u0060([^\\u0060]+)\\u0060/g, '<code>$1</code>');
}
function miniMd(t){
  var out = [], list = false;
  (t || '').split('\\n').forEach(function(line){
    var s = line.trim();
    if(/^##\\s+/.test(s)){
      if(list){ out.push('</ul>'); list = false; }
      out.push('<h3>' + inl(s.replace(/^##\\s+/, '')) + '</h3>');
      return;
    }
    var m = s.match(/^[-*]\\s+(.*)/);
    if(m){ if(!list){ out.push('<ul>'); list = true; } out.push('<li>' + inl(m[1]) + '</li>'); return; }
    if(list){ out.push('</ul>'); list = false; }
    if(s) out.push('<p>' + inl(s) + '</p>');
  });
  if(list) out.push('</ul>');
  return out.join('');
}
var AUDIT_WAS_RUNNING = false;
function renderAudit(j){
  var a = j.audit, body = $('auditbody'), note = $('auditnote'), btn = $('auditrun');
  var auditing = !!j.running && j.job === 'usageaudit';
  btn.disabled = !!j.running;   // any run blocks starting another
  if(auditing){
    note.textContent = 'Running. This section updates itself when it finishes.';
    AUDIT_WAS_RUNNING = true;
  } else {
    note.textContent = '';
    AUDIT_WAS_RUNNING = false;
  }
  if(a && a.md){
    body.innerHTML = miniMd(a.md)
      + (a.updated ? '<p class="uwhen">Audited on ' + esc(a.updated) + '.</p>' : '');
  }
}

// ---- switches -------------------------------------------------------------
function renderSwitches(j){
  FEAT = j.features || {};
  var ov = FEAT.overrides || {};
  var mode = j.ai || 'full';

  var plan = FEAT.plan || 'custom';
  document.querySelectorAll('#planseg button').forEach(function(b){
    b.disabled = false;
    b.classList.toggle('on', b.dataset.plan === plan);
  });
  $('now-plan').textContent = plan === 'pro'
    ? 'Right now: the Pro shape.'
    : plan === 'max' ? 'Right now: the Max shape.'
    : 'Right now: your own mix. Tap one to reset to a recommended shape.';

  document.querySelectorAll('#modeseg button').forEach(function(b){
    b.disabled = false;
    b.classList.toggle('on', b.dataset.mode === mode);
  });
  $('now-mode').textContent = mode === 'careful'
    ? 'Right now: Careful, built for a Pro plan.'
    : 'Right now: Full, built for a Max plan.';

  seg('morning', ov.hasOwnProperty('morning') ? (ov.morning ? 'on' : 'off') : 'auto');
  // Set to run is not the same as scheduled: on a new install nothing has
  // installed the 7am job yet, and this line used to say it ran (7 Oct).
  $('now-morning').textContent = 'Right now: '
    + (!FEAT.morning ? 'skipped. The free parts still run.'
       : j.morning_scheduled === false
         ? 'set to run, but not scheduled on this computer yet. '
           + (/Windows/.test(navigator.userAgent)
              ? 'Double-click Set Up Mornings (Windows).bat in the brain\\u2019s folder, once.'
              : 'Run zsh brain/tools/setup_morning.sh once in Terminal, in the brain\\u2019s folder.')
         : 'runs every morning.');

  seg('model', ov.model || 'auto');
  $('now-model').textContent = 'Right now: ' + (FEAT.model || 'sonnet')
    + ' unless a run picks its own.';

  seg('openers', ov.hasOwnProperty('openers') ? (ov.openers ? 'on' : 'off') : 'auto');
  $('now-openers').textContent = 'Right now: '
    + (FEAT.openers ? 'tasks get opened when the plan runs.' : 'plan only, nothing prepared unasked.');

  seg('recordings', ov.hasOwnProperty('recordings') ? (ov.recordings ? 'on' : 'off') : 'auto');
  var held = j.privacy && j.privacy.held && j.privacy.held.recordings;
  $('now-recordings').textContent = held
    ? 'Right now: held by Privacy. Transcribed at each pass, then filed in a run you start.'
    : 'Right now: '
      + (FEAT.recordings ? 'transcribed and filed at each pass.' : 'transcribed, then filed at the night run.');

  seg('news', ov.hasOwnProperty('news') ? (ov.news ? 'on' : 'off') : 'auto');
  $('now-news').textContent = 'Right now: '
    + (FEAT.news ? 'explained once a day.' : 'headlines only, no model call.');

  seg('extras', ov.hasOwnProperty('extras') ? (ov.extras ? 'on' : 'off') : 'auto');
  $('now-extras').textContent = 'Right now: '
    + (FEAT.extras ? 'on, each morning.' : 'off. The morning job asks no model for them.');

  var pct = FEAT.plan_pct || 0, p = j.plan, live = usable(p);
  document.querySelectorAll('.pctseg button').forEach(function(b){
    b.disabled = false;
    b.classList.toggle('on', (b.dataset.pct === '' ? 0 : +b.dataset.pct) === pct);
  });
  var stand = live ? ' Your week is at ' + used(p.week) + '%'
    + (p.five_hour ? ', the five-hour window at ' + used(p.five_hour) + '%.' : '.') : '';
  $('now-pct').textContent = 'Right now: ' + (!pct ? 'no limit.' + stand
    : live ? 'asks first past ' + pct + '%.' + stand
    : pct + '%, but there is no recent reading, so the run limit is in charge.');

  // The checked number the server refuses with, in runs; the old dollar
  // key is never read.
  var cap = FEAT.daily_runs || 0;
  document.querySelectorAll('.capseg button').forEach(function(b){
    b.disabled = false;
    b.classList.toggle('on', (b.dataset.cap === '' ? 0 : +b.dataset.cap) === cap);
  });
  // Say where today stands against it, not just what the number is — a
  // limit you cannot see yourself approaching is one you only meet by
  // being stopped by it. Same count as the Today card.
  var ran = (j.week && j.week.today) ? runsOf(j.week.today) : 0;
  $('now-cap').textContent = (cap
    ? 'Right now: ' + ran + ' of ' + cap + ' runs today.'
    : 'Right now: no limit, ' + plural(ran, 'run') + ' today.')
    + (cap && pct && live ? ' Standing by while the plan limit can read your plan.' : '');

  var n = j.night || {};
  document.querySelectorAll('#nightseg button').forEach(function(b){
    b.disabled = false;
    b.classList.toggle('on', (b.dataset.night === 'on') === !!n.enabled);
  });
  $('now-night').textContent = n.enabled
    ? (n.scheduled ? 'Right now: on and scheduled.'
       : 'Right now: on, but not scheduled on this Mac yet. Ask Claude to schedule it.')
    : 'Right now: off.';

}
function seg(key, val){
  document.querySelectorAll('[data-seg="' + key + '"] button').forEach(function(b){
    b.disabled = false;
    b.classList.toggle('on', b.dataset.v === val);
  });
}

function load(){
  return fetch('/api/usage')
    .then(function(r){ if(!r.ok) throw new Error('offline'); return r.json(); })
    .then(function(j){ renderUsage(j); renderSwitches(j); renderPlan(j.plan, j.features);
                       renderAudit(j); })
    .catch(function(){ /* static page: explainer stands, switches stay off */ });
}

var AUDIT_TIMER = null;
$('auditrun').onclick = function(){
  if(!confirm('Run the usage audit? Claude reads the ledger, the recent runs '
      + 'and a few conversations, then writes its report here. One run, a '
      + 'few minutes, on your subscription.')) return;
  post('/api/agent', {job: 'usageaudit'}).then(function(){
    $('auditrun').disabled = true;
    $('auditnote').textContent = 'Starting\\u2026';
    if(AUDIT_TIMER) clearInterval(AUDIT_TIMER);
    AUDIT_TIMER = setInterval(function(){
      load().then(function(){
        if(!AUDIT_WAS_RUNNING && AUDIT_TIMER){
          // it either finished or never became visible yet; keep polling
          // briefly after the flag drops so the fresh report lands
          fetch('/api/usage').then(function(r){ return r.json(); })
            .then(function(j){ if(!j.running){ clearInterval(AUDIT_TIMER); AUDIT_TIMER = null; } });
        }
      });
    }, 8000);
  }).catch(function(e){ alert(e.message); });
};

document.querySelectorAll('#planseg button').forEach(function(b){
  b.onclick = function(){
    if(!confirm('Set everything to the recommended ' + b.dataset.plan.toUpperCase()
        + ' settings? Any switch you changed yourself goes back to following '
        + 'the preset.')) return;
    post('/api/aiplan', {plan: b.dataset.plan}).then(load)
      .catch(function(e){ alert(e.message); });
  };
});
document.querySelectorAll('#modeseg button').forEach(function(b){
  b.onclick = function(){
    post('/api/aimode', {mode: b.dataset.mode}).then(load)
      .catch(function(e){ alert(e.message); });
  };
});
document.querySelectorAll('[data-seg]').forEach(function(group){
  var key = group.dataset.seg;
  group.querySelectorAll('button').forEach(function(b){
    b.onclick = function(){
      var v = b.dataset.v;
      var value = v === 'auto' ? null
        : (key === 'model' ? v : v === 'on');
      post('/api/aifeature', {key: key, value: value}).then(load)
        .catch(function(e){ alert(e.message); });
    };
  });
});
document.querySelectorAll('.capseg button').forEach(function(b){
  b.onclick = function(){
    var v = b.dataset.cap;
    post('/api/aifeature', {key: 'daily_runs', value: v === '' ? null : +v})
      .then(load).catch(function(e){ alert(e.message); });
  };
});
document.querySelectorAll('.pctseg button').forEach(function(b){
  b.onclick = function(){
    var v = b.dataset.pct;
    post('/api/aifeature', {key: 'plan_pct', value: v === '' ? null : +v})
      .then(load).catch(function(e){ alert(e.message); });
  };
});
document.querySelectorAll('#nightseg button').forEach(function(b){
  b.onclick = function(){
    var on = b.dataset.night === 'on';
    if(on && !confirm('Turn on the night shift? It runs Claude unattended '
        + 'every night, spending from the same weekly allowance.')) return;
    post('/api/night', {enabled: on}).then(load)
      .catch(function(e){ alert(e.message); });
  };
});

load();
setInterval(function(){ if(!document.hidden) load(); }, 60000);
})();
</script>
</body></html>
"""


if __name__ == "__main__":
    print("Built", build())

#!/usr/bin/env python3
"""Build brain/usage.html — what Claude spends here, and a switch for each
thing that spends.

    python3 brain/tools/build.py     # builds this page too

GENERATED. Never hand-edit usage.html.

Why this page exists: the Careful/Full control on the Claude tab is all or
nothing, which is the wrong shape for someone on a Pro plan — they may want
the morning plan OFF but Sonnet ON, or the other way round. This page gives
each spending path its own switch, explains how a subscription actually
meters Claude (five-hour window + weekly cap), and shows the ledger, which
otherwise only exists as a terminal command.

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
    night_jobs = ", ".join("/" + j for j in (night.get("jobs") or ["queue"]))

    page = TEMPLATE
    page = page.replace("__STYLE__", (cfg.get("appearance", {}) or {}).get("style", "workroom"))
    page = page.replace("__PALETTE__", B.palette_css(cfg))
    page = page.replace("__HEADER__", CHROME.header_html(
        current="claude", owner=cfg.get("owner", "")))
    page = page.replace("__SUBNAV__", CHROME.claude_subnav("usage"))
    page = page.replace("__ASK__", CHROME.ask_block())
    page = page.replace("__NIGHTJOBS__", night_jobs)
    page = page.replace("__NIGHTAT__", night.get("at") or "01:00")
    # Windows has no file lock that denies reads, and only honesty ages
    # well: the copy says so on the machines where it is true.
    page = page.replace("__PRIVWIN__", (
        " (On Windows the lock is advisory today: the run is told to stay"
        " out, but the files are not made unreadable.)"
        if os.name == "nt" else ""))
    page = page.replace("__DATE__", date.today().isoformat())

    # Same publish gate as the other pages: a page whose script cannot parse
    # is worse than a stale one.
    from shutil import which
    node = which("node")
    if node:
        import subprocess as _sp
        import tempfile as _tf
        for js in re.findall(r"<script>(.*?)</script>", page, re.S):
            with _tf.NamedTemporaryFile("w", suffix=".js", delete=False) as tmp:
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


TEMPLATE = """<!doctype html>
<html lang="en" data-style="__STYLE__"><head>
<script>try{var _bs=localStorage.getItem('brain-style');
if(_bs)document.documentElement.setAttribute('data-style',_bs);}catch(e){}</script>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>Usage &mdash; the brain</title>
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
.uwrap{max-width:860px;margin:0 auto;padding:28px 20px 80px}
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
.useg{display:inline-flex;border:1px solid var(--line2);border-radius:var(--r-btn);overflow:hidden;flex:none}
.useg button{font:500 var(--t-xs)/1 var(--sans);padding:8px 12px;border:0;cursor:pointer;
  background:transparent;color:var(--dim)}
.useg button+button{border-left:1px solid var(--line2)}
.useg button.on{background:var(--greenbg,var(--sunken,var(--surface)));color:var(--green,var(--ink));font-weight:700}
.useg button:disabled{opacity:.45;cursor:default}
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
@media(max-width:640px){.ufree{columns:1}}
</style>
</head><body>
__HEADER__
<main class="uwrap">
__SUBNAV__

<h1>What Claude spends here</h1>
<p class="ulede">The brain runs on your Claude subscription. Most of it &mdash;
the pages, the syncing, the tickboxes, the reminders &mdash; runs no AI at all.
This page covers the part that does: how your plan meters it, what this week
actually used, and a switch for each thing that spends.</p>

<h2>This week</h2>
<div id="live">
  <div class="uoffline">Live numbers need the brain&rsquo;s local server &mdash;
  open the page through <b>Open Brain</b> and they appear here. The ledger
  itself is <code>python3 brain/tools/usage.py</code> in a terminal.</div>
</div>

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
    <p><b>Pro</b>: nothing runs unasked, Haiku is the default model, and a $2
    daily ceiling asks a second time before a run that would push past it.
    <b>Max</b>: the morning plan writes itself, Sonnet is the default, openers
    get prepared, no ceiling.</p>
    <p>Neither one touches the night shift or extra privacy &mdash; those two
    have consequences a button should not decide for you.</p></details></div>
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
    <p><b>Careful</b>: nothing runs unasked and the cheapest model is the
    default. <b>Full</b>: the morning plan runs itself, Sonnet is the default,
    and openers get prepared.</p></details></div>
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
    <p>One small-to-medium run every day &mdash; the steady spender. Off, the
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
    mechanical jobs &mdash; folder sync and the project scan &mdash; always
    default to Haiku unless you set a model here.</p></details></div>
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

<div class="urow" data-key="news">
  <div class="uinfo"><b>News breakdowns</b>
    <span class="udetail">A plain-language explainer on the topics
    you&rsquo;re learning.</span>
    <span class="unow" id="now-news"></span>
    <details class="uwhy"><summary>the smallest thing on this page</summary>
    <p>One Haiku call per learning topic per day, written once and reused by
    every refresh &mdash; pennies-scale, and the only model call the morning
    job makes when the 7am plan is off. Off, the briefing itself still
    arrives; it just stops explaining the jargon.</p></details></div>
  <span class="useg" data-seg="news">
    <button data-v="auto" disabled>Follow the preset</button>
    <button data-v="on" disabled>On</button>
    <button data-v="off" disabled>Off</button>
  </span>
</div>

<div class="urow" data-key="daily_cap">
  <div class="uinfo"><b>Daily ceiling</b>
    <span class="udetail">Stop starting runs from the page once a day costs
    this much.</span>
    <span class="unow" id="now-cap"></span>
    <details class="uwhy"><summary>what it does and does not stop</summary>
    <p>It only ever stops a run you start from a button, and one more press
    goes ahead anyway &mdash; nothing is switched off, it just asks twice.
    The scheduled work is never blocked: that half is small and predictable,
    and a morning plan that silently did not happen looks like a fault.</p>
    <p>Useful on a Pro plan, where the five-hour window is the real limit and
    &ldquo;it just kept going&rdquo; is what makes people turn a tool off
    altogether.</p></details></div>
  <span class="useg capseg">
    <button data-cap="" disabled>No ceiling</button>
    <button data-cap="1" disabled>$1</button>
    <button data-cap="2" disabled>$2</button>
    <button data-cap="5" disabled>$5</button>
  </span>
</div>

<div class="urow" data-night-row>
  <div class="uinfo"><b>Night shift</b>
    <span class="udetail">Runs __NIGHTJOBS__ at __NIGHTAT__ while you sleep.</span>
    <span class="unow" id="now-night"></span>
    <details class="uwhy"><summary>why run it at night at all</summary>
    <p>The heavy work stops competing with your day for the same five-hour
    window. It draws on the same weekly allowance &mdash; on Pro, where the
    five-hour window is the pinch, that is often the difference between the
    brain and your own work colliding. In Careful mode it runs on
    Haiku.</p></details></div>
  <span class="useg" id="nightseg">
    <button data-night="on" disabled>On</button>
    <button data-night="off" disabled>Off</button>
  </span>
</div>

<div class="urow" data-privacy-row>
  <div class="uinfo"><b>Extra privacy</b>
    <span class="udetail">With this on, unattended runs cannot read your
    journal.</span>
    <span class="unow" id="now-privacy"></span>
    <details class="uwhy"><summary>how the lock works, and what it costs you</summary>
    <p>The night shift and the 7am plan run while nobody is watching; for the
    length of those runs the journal is locked shut, so your most personal
    writing never enters a model call you didn&rsquo;t witness.__PRIVWIN__
    The trade: the morning plan starts the day without yesterday&rsquo;s
    entry, so anything in it you want acted on waits for the next session
    you actually open. Sessions you are in read the journal as they always
    did.</p></details></div>
  <span class="useg" id="privacyseg">
    <button data-privacy="on" disabled>On</button>
    <button data-privacy="off" disabled>Off</button>
  </span>
</div>

<h2>The audit</h2>
<p class="usub">Claude reads its own ledger, the recent runs and a few of
your conversations, then writes up where the usage went, which habits cost
extra, and what would cost less without losing anything. One run, a few
minutes. <button class="ubtn" id="auditrun" disabled>Run the audit</button>
<span class="unow" id="auditnote"></span></p>
<div id="auditbody" class="ureport">
  <p class="unote">No audit yet &mdash; the first one appears here after you
  run it (or ask for <code>/usage-audit</code> in a session).</p>
</div>

<details class="udoc">
<summary>How a subscription meters Claude</summary>
<p class="ulede">A Pro or Max plan has no per-use bill. Instead there are two
meters, shared with everything else you do with Claude: a <b>five-hour
window</b> (use a lot at once and Claude pauses until the window rolls over)
and a <b>weekly cap</b>. Max is the same system with a bigger allowance
&mdash; roughly 5&times; or 20&times; Pro&rsquo;s, depending on the tier.
Anthropic doesn&rsquo;t publish exact numbers; the one true reading of where
you stand is <code>/usage</code> typed inside Claude Code.</p>
<p class="ulede">What the brain&rsquo;s runs weigh, roughly:</p>
<ul class="uweights">
  <li><span>Work the queue &middot; Catch me up &middot; Tidy the brain</span>
      <span class="uw">the heavy ones &mdash; minutes of model time each</span></li>
  <li><span>The 7am plan</span><span class="uw">about a third of a queue run</span></li>
  <li><span>A conversation turn (Sessions, Ask)</span><span class="uw">small</span></li>
  <li><span>Revising a draft, naming a conversation</span><span class="uw">tiny &mdash; Haiku, pennies-scale</span></li>
</ul>
<p class="usub">The comfortable shape on Pro: one or two batched runs a day on
Haiku or Sonnet, the 7am plan off, and several queue items handled in one run
instead of one run each. On Max, everything on this page can stay on.</p>
</details>

<h2>What never spends</h2>
<p class="usub">These run as plain code, with no model and no meter:</p>
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

<p class="unote">Ledger last rebuilt into this page on __DATE__. The live
numbers above always come from <code>brain/.usage.jsonl</code>, where every
model call the brain makes writes one line.</p>
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
function mins(s){
  if(!s) return '';
  return s >= 60 ? Math.round(s/60) + ' min of model time' : s + 's of model time';
}

// ---- live usage -----------------------------------------------------------
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
  var max = 1;
  days.forEach(function(k){ var v = byDay[k]; if(v && v.tokens > max) max = v.tokens; });
  html += '<div class="ubars">' + days.map(function(k){
    var v = byDay[k] || {tokens:0, calls:0};
    var h = Math.max(3, Math.round(70 * v.tokens / max));
    return '<i class="' + (v.tokens ? 'hot' : '') + '" style="height:' + h + 'px"'
      + ' title="' + k + ': ' + v.calls + ' call' + (v.calls === 1 ? '' : 's')
      + ', ' + tok(v.tokens) + ' tokens"></i>';
  }).join('') + '</div>'
  + '<div class="ubarlab"><span>' + days[0] + '</span><span>today</span></div>';

  var jobs = m.by_job || {}, names = Object.keys(jobs).slice(0, 7);
  if(names.length){
    html += '<table class="ujobs">' + names.map(function(k){
      var v = jobs[k];
      return '<tr><td>' + esc(k) + '</td><td>' + v.calls + ' \\u00d7 \\u00b7 '
        + tok(v.tokens) + ' tokens' + (v.secs ? ' \\u00b7 ' + mins(v.secs) : '') + '</td></tr>';
    }).join('') + '</table>';
  }
  var models = m.by_model || {};
  var mline = Object.keys(models).map(function(k){
    return k + ' \\u00d7' + models[k].calls; }).join(', ');
  html += '<p class="unote">' + (mline ? 'By model over 30 days: ' + esc(mline) + '. ' : '')
    + 'Nothing here is a bill \\u2014 on a subscription these tokens are already '
    + 'paid for. The numbers say how hard you are leaning on the plan\\u2019s '
    + 'five-hour and weekly meters.</p>';
  $('live').innerHTML = html;
}
function card(label, v){
  return '<div class="ucard"><span class="ulab">' + label + '</span>'
    + '<div class="ubig">' + (v.calls || 0) + ' run' + (v.calls === 1 ? '' : 's') + '</div>'
    + '<span class="usml">' + tok(v.tokens || 0) + ' tokens'
    + (v.secs ? ' \\u00b7 ' + mins(v.secs) : '') + '</span></div>';
}
function esc(s){ return String(s == null ? '' : s)
  .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }

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
    note.textContent = 'Running \\u2014 this section rewrites itself when it finishes.';
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
    : 'Right now: your own mix \\u2014 tap one to reset to a recommended shape.';

  document.querySelectorAll('#modeseg button').forEach(function(b){
    b.disabled = false;
    b.classList.toggle('on', b.dataset.mode === mode);
  });
  $('now-mode').textContent = mode === 'careful'
    ? 'Right now: Careful \\u2014 built for a Pro plan.'
    : 'Right now: Full \\u2014 built for a Max plan.';

  seg('morning', ov.hasOwnProperty('morning') ? (ov.morning ? 'on' : 'off') : 'auto');
  $('now-morning').textContent = 'Right now: '
    + (FEAT.morning ? 'runs every morning.' : 'skipped \\u2014 the free parts still run.');

  seg('model', ov.model || 'auto');
  $('now-model').textContent = 'Right now: ' + (FEAT.model || 'sonnet')
    + ' unless a run picks its own.';

  seg('openers', ov.hasOwnProperty('openers') ? (ov.openers ? 'on' : 'off') : 'auto');
  $('now-openers').textContent = 'Right now: '
    + (FEAT.openers ? 'tasks get opened when the plan runs.' : 'plan only, nothing prepared unasked.');

  seg('news', ov.hasOwnProperty('news') ? (ov.news ? 'on' : 'off') : 'auto');
  $('now-news').textContent = 'Right now: '
    + (FEAT.news ? 'explained once a day.' : 'headlines only, no model call.');

  var cap = ov.daily_cap || 0;
  document.querySelectorAll('.capseg button').forEach(function(b){
    b.disabled = false;
    b.classList.toggle('on', (b.dataset.cap === '' ? 0 : +b.dataset.cap) === cap);
  });
  // Say where today stands against it, not just what the number is — a
  // ceiling you cannot see yourself approaching is one you only meet by
  // being stopped by it.
  var spent = (j.week && j.week.today && j.week.today.cost) || 0;
  $('now-cap').textContent = cap
    ? 'Right now: ' + spent.toFixed(2) + ' of ' + cap.toFixed(2) + ' today.'
    : 'Right now: no ceiling \\u2014 ' + spent.toFixed(2) + ' spent today.';

  var n = j.night || {};
  document.querySelectorAll('#nightseg button').forEach(function(b){
    b.disabled = false;
    b.classList.toggle('on', (b.dataset.night === 'on') === !!n.enabled);
  });
  $('now-night').textContent = n.enabled
    ? (n.scheduled ? 'Right now: on and scheduled.'
       : 'Right now: on, but not scheduled yet \\u2014 run zsh brain/tools/setup_night.sh once.')
    : 'Right now: off.';

  var p = j.privacy || {};
  document.querySelectorAll('#privacyseg button').forEach(function(b){
    b.disabled = false;
    b.classList.toggle('on', (b.dataset.privacy === 'on') === !!p.on);
  });
  $('now-privacy').textContent = p.on
    ? 'Right now: on \\u2014 unattended runs cannot read the journal.'
    : 'Right now: off \\u2014 every run may read everything.';
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
    .then(function(j){ renderUsage(j); renderSwitches(j); renderAudit(j); })
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
    post('/api/aifeature', {key: 'daily_cap', value: v === '' ? null : +v})
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
document.querySelectorAll('#privacyseg button').forEach(function(b){
  b.onclick = function(){
    var on = b.dataset.privacy === 'on';
    if(!on && !confirm('Turn extra privacy off? The overnight and morning '
        + 'runs will be able to read your journal again.')) return;
    post('/api/privacy', {on: on}).then(load)
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

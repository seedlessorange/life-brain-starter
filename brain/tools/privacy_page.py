#!/usr/bin/env python3
"""Build brain/privacy.html: what the brain may read and send, as three
levels and a switch each (privacy.py; PRIVACY-PLAN.md, 8 Oct 2026).

    python3 brain/tools/build.py     # builds this page too

GENERATED. Never hand-edit privacy.html.

The Usage page's shape, on purpose: a level applied in one tap, a switch per
thing that can differ from it, and "your own mix" once one does. What
differs is where the settings live (privacy.py says why) and that loosening
asks for her fingerprint; the server enforces both, and this page only shows
what the server says. Its look is the Usage page's own stylesheet, taken from
usage_page.py, so the two cannot drift apart.
"""

import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import chrome as CHROME      # noqa: E402
import usage_page as UP      # noqa: E402

BRAIN = os.path.dirname(HERE)
OUT = os.path.join(BRAIN, "privacy.html")

# The Usage page's stylesheet, whole (it carries the palette placeholder).
STYLE = UP.TEMPLATE.split("<style>", 1)[1].split("</style>", 1)[0]


def build(cfg=None):
    import build as B        # already loaded when called from build.py
    if cfg is None:
        try:
            with open(os.path.join(BRAIN, "config.json"), encoding="utf-8") as f:
                cfg = json.load(f)
        except Exception:
            cfg = {}
    # The page's wording names the agent the brain runs (agents.say); what
    # holds for Claude Code alone is written __CLAUDE__ and stays Claude.
    import agents
    page = agents.say(TEMPLATE).replace("__CLAUDE__", "Claude")
    # Where a run's reading is processed: the company behind the agent.
    page = page.replace("__MAKER__", {"codex": "OpenAI", "gemini": "Google"}.get(
        agents.provider(), "Anthropic"))
    page = page.replace("__USAGESTYLE__", STYLE)
    page = page.replace("__STYLE__", (cfg.get("appearance", {}) or {}).get("style", "workroom"))
    page = page.replace("__PALETTE__", B.palette_css(cfg))
    # The gear's sub-row rides under the bar, on main's measure, so it
    # holds still between Settings, Usage, Privacy and Conversations
    # (8 Oct: inside this page's narrow column it jumped 256px).
    page = page.replace("__HEADER__", CHROME.header_html(
        current="claude", owner=cfg.get("owner", ""),
        sub_html=CHROME.claude_subnav("privacy")))
    page = page.replace("__SUBNAV__", "")
    page = page.replace("__ASK__", CHROME.ask_block())
    page = page.replace("__FINGER__", (
        "Loosening asks for your fingerprint." if sys.platform == "darwin" else
        "Loosening asks you to confirm. This computer has no fingerprint "
        "check, so a confirm step is all there is."))

    # The same publish gate as the Usage page: a page whose script cannot
    # parse is worse than a stale one.
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
                    raise SystemExit("REFUSING to write privacy.html: its "
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
<title>Privacy &middot; the brain</title>
<link rel="icon" href="logo-192.png?v=5" type="image/png">
<link rel="apple-touch-icon" href="logo-180.png?v=5">
<link rel="stylesheet" href="appearance.css">
<style>
__USAGESTYLE__
.plevels{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:10px;margin:14px 0 6px}
.plevel{background:var(--surface);border:1px solid var(--line);border-radius:var(--r-card);
  padding:14px 16px;text-align:left;cursor:pointer;font:inherit;color:inherit;
  display:flex;flex-direction:column;justify-content:flex-start}
.plevel:disabled{cursor:default;opacity:.6}
.plevel b{display:block;font:600 var(--t-lg)/1.2 var(--serif);margin:0 0 4px}
.plevel span{display:block;color:var(--dim);font-size:var(--t-sm)}
.plevel.on{border-color:var(--green,var(--ink));box-shadow:0 0 0 1px var(--green,var(--ink)) inset}
.plevel.on b::after{content:"  \\2713";color:var(--green,var(--ink));font-size:var(--t-base)}
.pwarn{background:var(--surface);border:1px solid var(--bad,var(--line2));border-radius:var(--r-card);
  padding:12px 16px;margin:12px 0;color:var(--ink);font-size:var(--t-sm)}
table.preach{width:100%;border-collapse:collapse;margin:10px 0 4px;font-size:var(--t-sm)}
table.preach th{text-align:left;font-weight:650;padding:6px 8px 6px 0;color:var(--dim)}
table.preach td{padding:7px 8px 7px 0;border-top:1px solid var(--line);vertical-align:top}
.pnote{color:var(--faint);font-size:var(--t-xs)}
.plist{list-style:none;margin:8px 0 12px;padding:0}
.plist li{display:flex;gap:12px;align-items:center;justify-content:space-between;
  padding:8px 0;border-top:1px solid var(--line);font-size:var(--t-sm)}
.plist li:first-child{border-top:0}
.plist li span{overflow-wrap:anywhere}
.pst{display:inline-block;width:1.4em;font-weight:700}
.pst.ok{color:var(--green,var(--ink))}.pst.warn{color:var(--bad,var(--ink))}.pst.info{color:var(--faint)}
table.plog{width:100%;border-collapse:collapse;margin:10px 0 4px;font-size:var(--t-sm)}
table.plog th{text-align:right;font-weight:600;color:var(--dim);padding:4px 0 4px 10px}
table.plog th:first-child,table.plog td:first-child{text-align:left;padding-left:0}
table.plog td{text-align:right;padding:6px 0 6px 10px;border-top:1px solid var(--line)}
@media(max-width:640px){table.preach th:nth-child(4),table.preach td:nth-child(4){display:none}}
</style>
</head><body>
__HEADER__
<main class="uwrap">
__SUBNAV__

<h1>What the brain may read and send</h1>
<p class="ulede">A level sets everything below in one tap. Any switch can
differ from its level; the level then reads &ldquo;your own mix&rdquo;.
Tightening is one tap. __FINGER__</p>
<div id="broken"></div>
<div class="uoffline" id="offline">The switches need the brain&rsquo;s local
server: open the page through <b>Open Brain</b> and they appear here.</div>

<div class="urow" id="presentrow">
  <div class="uinfo"><b>Presenting</b>
    <span class="udetail">Before you share your screen: the pages are rebuilt
    without your private parts until you turn it off.</span>
    <span class="unow" id="now-present"></span>
    <details class="uwhy"><summary>what it leaves out, and what it doesn&rsquo;t</summary>
    <p>Left out of the page itself, not covered up: the journal card, the
    People tab and every list of names, Quick replies, money, drafts, the
    free text of today&rsquo;s plan, the work in the areas ticked below, and
    the same on the map and the project pages. The find box searches only
    the work that is left, and the morning notification waits.</p>
    <p>Still there: a name written inside a work task, and the Conversations,
    Usage, Routine and Kitchen pages, which presenting doesn&rsquo;t change.</p>
    </details>
    <div id="presentareas"></div></div>
  <span class="useg" id="presentseg">
    <button data-present="on" disabled>On</button>
    <button data-present="off" disabled>Off</button>
  </span>
</div>

<h2>At every level</h2>
<p class="usub">These hold whatever the level. They are fixed in the
brain&rsquo;s code, and no switch here reaches them.</p>
<ul class="ufree" style="columns:1">
  <li>Every run the brain starts is fenced. It reaches the internet only for
    the weather, can&rsquo;t read passwords or keys, and can&rsquo;t change
    its own rules.</li>
  <li>Family and friends get Copy, never a send button.</li>
  <li>A draft made from someone else&rsquo;s words never gets a send button.</li>
  <li>Runs on a timer can&rsquo;t send anything, and can&rsquo;t open your
    journal.</li>
  <li>A file with NDA or confidential in its name is never opened.</li>
  <li>A change to the brain&rsquo;s safety code shows the red card until
    your fingerprint clears it.</li>
</ul>
<p class="unote">Runs on a timer: the 7am plan, the night shift and the
twice-daily recordings pass. A run you start yourself, from a button, the box,
Telegram or a conversation, is yours.</p>

<h2>Your level</h2>
<div class="plevels" id="levels">
  <button class="plevel" data-level="everyday" disabled><b>Everyday</b>
    <span>What you have now. The brain reads what it needs.</span></button>
  <button class="plevel" data-level="guarded" disabled><b>Guarded</b>
    <span>Transcripts and money stay out of runs on a timer, every send asks
    for your fingerprint, and task mail is off.</span></button>
  <button class="plevel" data-level="locked" disabled><b>Locked</b>
    <span>Runs on a timer also lose notes on people, nothing sends from the
    page, the mail check is off, and Telegram only takes things in.</span></button>
</div>
<span class="unow" id="now-level"></span>

<h2>The switches</h2>
<div id="rows"></div>

<h2>Set on their own</h2>
<p class="usub">No level changes these: each one trades something other than
convenience.</p>
<div id="solo"></div>

<h2>Folders runs may read</h2>
<p class="usub">Under a reading fence, a run reads the brain and the folders
here, nothing else in your home folder. Adding one asks for your fingerprint.</p>
<div id="folders"><p class="unote">Shown once the server answers.</p></div>

<h2>What runs on a timer can&rsquo;t open</h2>
<div id="private"><p class="unote">Shown once the server answers.</p></div>

<h2>Where your words went</h2>
<p class="usub">What the brain&rsquo;s own runs opened this week, by kind of
material, without the contents or the file names. Whatever a run opens goes to
the company that runs the model.</p>
<div id="log"><p class="unote">Shown once the server answers.</p></div>

<h2>The Mac check</h2>
<p class="usub">The things outside the brain&rsquo;s code. The check is plain
code without AI, and it looks at GitHub and npm once each.
<button class="ubtn" id="macrun" disabled>Check now</button></p>
<div id="mac"><p class="unote">Shown once the server answers.</p></div>

<details class="udoc">
<summary>What can reach your files on this Mac</summary>
<table class="preach">
<tr><th>Who</th><th>Can read</th><th>Can change</th><th>Internet</th></tr>
<tr><td>Runs the brain starts</td><td>At Everyday, most of the disk except a
  list of secret places (keys, Mail, Messages, Photos and the like). Under a
  reading fence, the brain and the folders you let in</td><td>The brain
  folder, except its own rules</td><td>The weather only</td></tr>
<tr><td>The brain&rsquo;s own code (no AI)</td><td>Your project folders,
  Voice Memos, the Mail app&rsquo;s index, Calendar, and Downloads when you
  pick a file</td><td>The brain folder</td><td>The services you
  connected</td></tr>
<tr><td>Brain Pen</td><td>The text box you&rsquo;re typing in, when you
  press &#8963;&#8997;R</td><td>That box</td><td>Through Claude</td></tr>
<tr><td>Your own Claude Code sessions</td><td>Everything you can</td>
  <td>Everything you can</td><td>Anywhere</td></tr>
</table>
<p class="usub">Whatever a run reads goes to __MAKER__ to be processed. The
reading fence is worked out each time a run starts, so a folder made during a
run is not on it, and the names inside a folder that holds one of yours stay
visible.</p>
</details>
</main>
__ASK__
<script>
(function(){
function $(id){ return document.getElementById(id); }
function esc(s){ return String(s == null ? '' : s)
  .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }
function post(url, body){
  return fetch(url, {method:'POST', headers:{'Content-Type':'application/json'},
                     body: JSON.stringify(body)})
    .then(function(r){
      return r.json().catch(function(){ return {}; }).then(function(j){
        if(!r.ok) throw new Error(j.error || ('The server said no (' + r.status + ')'));
        return j;
      });
    });
}
var NAMES = {everyday: 'Everyday', guarded: 'Guarded', locked: 'Locked'};
// One row per switch: its choices loosest first, as privacy.py orders them.
var ROWS = [
  {k: 'lock_transcripts', label: 'Transcripts, in runs on a timer',
   detail: 'Recordings and meeting transcripts.',
   vals: [[false, 'Open'], [true, 'Locked']],
   cost: 'Locked: recordings and transcripts are filed only in a run you start, and the recordings pass stops starting runs by itself.'},
  {k: 'lock_money', label: 'Money files, in runs on a timer',
   detail: 'Balances and spending from the bank feed.',
   vals: [[false, 'Open'], [true, 'Locked']],
   cost: 'Locked: money questions wait for a run you start.'},
  {k: 'lock_people', label: 'Notes on people, in runs on a timer',
   detail: 'The notes on everyone in your people list.',
   vals: [[false, 'Open'], [true, 'Locked']],
   cost: 'Locked: the 7am plan still gets a short list, made before the run starts, of replies waiting on you and people you have not been in touch with lately. It no longer sees the notes, and Last dates from the night wait for a run you start.'},
  {k: 'send_email', label: 'Sending email',
   detail: 'The Approve & send button on an email draft.',
   vals: [['on', 'As set up'], ['touch', 'Fingerprint each time'], ['off', 'Off']],
   cost: 'Off: Open in email and Copy still work, and you press send in your own mail app.'},
  {k: 'send_chat', label: 'Sending chat messages',
   detail: 'Send on a draft to a work contact, through Beeper.',
   vals: [['click', 'On your click'], ['touch', 'Fingerprint each time'], ['off', 'Off']],
   cost: 'Off: Copy still works.'},
  {k: 'mail_check', label: 'Mail check',
   detail: 'Who wrote to you, from the headers only, on your click.',
   vals: [[true, 'On'], [false, 'Off']],
   cost: 'Off: the page stops knowing who is waiting on an email reply.'},
  {k: 'mail_tasks', label: 'Task mail',
   detail: 'Reads mail from the senders on your list and suggests tasks, on your click.',
   vals: [[true, 'On'], [false, 'Off']],
   cost: 'Off: school admin mail stops turning into suggested tasks. Suggestions already in the tray stay.'},
  {k: 'reach', label: 'What runs you start may read',
   detail: 'Runs from a button, the box, Telegram or a conversation.',
   vals: [['anywhere', 'Most of the disk'], ['named', 'Brain and your folders'], ['brain', 'The brain only']],
   cost: 'Brain and your folders: a run can\u2019t open a file anywhere else; attach it instead. The brain only: Sync my projects stops, and a conversation in an app folder reads only that folder.'},
  {k: 'reach_timer', label: 'What runs on a timer may read',
   detail: 'The 7am plan, the night shift and the recordings pass.',
   vals: [['anywhere', 'Most of the disk'], ['named', 'Brain and your folders'], ['brain', 'The brain only']],
   cost: 'The brain only: these runs work from what the brain already holds, including the folder harvest that plain code writes every 20 minutes.'},
  {k: 'telegram', label: 'Telegram',
   detail: 'What the bot sends back through Telegram.',
   vals: [['full', 'Answers and plans'], ['capture', 'Capture only']],
   cost: 'Capture only: lines, voice notes and photos still land in the brain. The bot stops answering, sending files and sending the day\\u2019s plan and tasks.'}
];
var SOLO = [
  {k: 'small_jobs', label: 'Small jobs',
   detail: 'Pen rewrites, draft rewording, conversation names, task wording, news breakdowns, the voice.',
   vals: [['claude', 'Claude'], ['local_first', 'This Mac first'], ['local_only', 'This Mac only']],
   cost: 'This Mac first: a local model answers when it is running, and Claude when it is not. This Mac only: the text never leaves; when the local model is off, those jobs stop and say so. Local models write less well than Claude.'},
  {k: 'backup', label: 'Backup to GitHub',
   detail: 'The off-site copy of the brain, in your private repo.',
   vals: [[true, 'On'], [false, 'Off']],
   cost: 'Off: local git only. A lost Mac loses the brain unless Time Machine runs. What GitHub already holds stays there.'}
];
var STATE = null;

function rowHtml(r, solo){
  return '<div class="urow" data-row="' + r.k + '"><div class="uinfo"><b>' + esc(r.label)
    + '</b><span class="udetail">' + esc(r.detail) + '</span>'
    + '<span class="unow" id="now-' + r.k + '"></span>'
    + '<details class="uwhy"><summary>what it costs</summary><p>' + esc(r.cost)
    + '</p></details></div><span class="useg">'
    + r.vals.map(function(v, i){
        return '<button data-key="' + r.k + '" data-i="' + i + '" disabled>' + esc(v[1]) + '</button>';
      }).join('') + '</span></div>';
}
$('rows').innerHTML = ROWS.map(function(r){ return rowHtml(r); }).join('');
$('solo').innerHTML = SOLO.map(function(r){ return rowHtml(r, true); }).join('');

function rowOf(k){
  return ROWS.concat(SOLO).filter(function(r){ return r.k === k; })[0];
}
function idx(r, v){
  for(var i = 0; i < r.vals.length; i++) if(r.vals[i][0] === v) return i;
  return -1;
}
var PLAIN_PATH = {'brain/journal/': 'Your journal', 'brain/transcripts/': 'Transcripts',
  'brain/finance/': 'Money files', 'brain/people.md': 'Notes on people',
  'brain/.anon/': 'The keys for hidden names'};

function render(j){
  STATE = j;
  $('offline').style.display = 'none';
  $('broken').innerHTML = j.broken
    ? '<div class="pwarn">The settings file could not be read, so everything is at Locked until it is set again.</div>'
    : '';
  document.querySelectorAll('.plevel').forEach(function(b){
    b.disabled = false;
    b.classList.toggle('on', b.dataset.level === j.match);
  });
  $('now-level').textContent = j.match === 'custom'
    ? 'Right now: your own mix, starting from ' + NAMES[j.level] + '.'
    : 'Right now: ' + NAMES[j.match] + '.';
  ROWS.concat(SOLO).forEach(function(r){
    var v = j.values[r.k], cur = idx(r, v);
    document.querySelectorAll('[data-key="' + r.k + '"]').forEach(function(b){
      b.disabled = false;
      b.classList.toggle('on', +b.dataset.i === cur);
    });
    var own = j.overrides && Object.prototype.hasOwnProperty.call(j.overrides, r.k);
    var lvl = j.levels && j.levels[j.level] ? j.levels[j.level][r.k] : undefined;
    var note = 'Right now: ' + (cur >= 0 ? r.vals[cur][1] : String(v));
    if(own) note += ' (your change; ' + NAMES[j.level] + ' says ' + r.vals[idx(r, lvl)][1] + ')';
    $('now-' + r.k).textContent = note + '.';
  });
  // A local model has to answer before "this Mac" means anything.
  document.querySelectorAll('[data-key="small_jobs"]').forEach(function(b){
    if(+b.dataset.i > 0 && !j.ollama && !b.classList.contains('on')) b.disabled = true;
  });
  if(!j.ollama) $('now-small_jobs').textContent += ' This Mac needs a local model first: install Ollama '
    + '(ollama.com), run \u201collama pull llama3.2\u201d, and put that name in the llm block of config.json.';
  $('private').innerHTML = '<ul class="ufree" style="columns:1">'
    + (j.private || []).map(function(p){
        return '<li>' + esc(PLAIN_PATH[p] || p) + '</li>';
      }).join('') + '</ul>'
    + '<p class="unote">The journal is on this list at every level. Extra paths can be added by hand to the private list in config.json; that list can only add.</p>';
}

var KINDNAMES = {journal: 'Your journal', people: 'Notes on people', money: 'Money files',
  transcripts: 'Transcripts', voice: 'Voice notes', drafts: 'Drafts', school: 'School',
  brain: 'The rest of the brain', projects: 'Your project folders', outside: 'Outside your folders'};
function renderFolders(j){
  var h = '';
  var item = function(f, btn){ return '<li><span>' + esc(f) + '</span>' + btn + '</li>'; };
  h += (j.folders || []).length
    ? '<ul class="plist">' + j.folders.map(function(f){
        return item(f, '<button class="ubtn" data-unfolder="' + esc(f) + '">Remove</button>'); }).join('') + '</ul>'
    : '<p class="unote">None yet. Under a fence, runs read the brain only until you add one.</p>';
  if((j.pending || []).length){
    h += '<p class="usub">Your project folders runs can\u2019t read yet:</p><ul class="plist">'
      + j.pending.map(function(f){
          return item(f, '<button class="ubtn" data-folder="' + esc(f) + '">Let runs read it</button>'); }).join('')
      + '</ul>';
  }
  if((j.dropped || []).length){
    h += '<div class="pwarn">These sit inside a folder too full for this version of __CLAUDE__ Code to fence one '
      + 'by one, so a fenced run can\u2019t read them: ' + j.dropped.map(esc).join(', ')
      + '. Moving them out of that folder fixes it.</div>';
  }
  $('folders').innerHTML = h;
}
function renderLog(j){
  var L = j.log || {}, K = L.kinds || {};
  var h = '';
  if(j.agent && j.agent !== 'claude')
    h += '<p class="unote">Runs on ' + esc(j.agent) + ' are not tracked: only __CLAUDE__ Code runs carry the record.</p>';
  if(!L.since){
    $('log').innerHTML = h + '<p class="unote">Nothing recorded yet. The record starts with the next run the brain starts.</p>';
    return;
  }
  var R = L.runs || {};
  h += '<p class="usub">Last ' + L.days + ' days: ' + (R.watched || 0) + ' run' + (R.watched === 1 ? '' : 's')
    + ' you started, ' + (R.timer || 0) + ' on a timer.</p>';
  h += '<table class="plog"><tr><th>Opened</th><th>by your runs</th><th>by timer runs</th><th>named in a command</th></tr>'
    + Object.keys(KINDNAMES).filter(function(k){ return K[k]; }).map(function(k){
        return '<tr><td>' + KINDNAMES[k] + '</td><td>' + K[k].watched + '</td><td>' + K[k].timer
          + '</td><td>' + K[k].named + '</td></tr>'; }).join('') + '</table>';
  var out = Object.keys(L.outside || {});
  if(out.length) h += '<p class="unote">Outside your folders: ' + out.map(function(o){
      return esc(o) + ' (' + L.outside[o] + ')'; }).join(', ') + '. A reading fence would have refused these.</p>';
  if((L.trips || []).length) h += '<div class="pwarn">A run on a timer opened something your level locks: '
    + L.trips.map(function(t){ return esc(t.k.join(', ')) + ' on ' + esc(t.t.slice(0, 16).replace('T', ' ')); }).join('; ')
    + '. The red card on Today asks you about it.</div>';
  $('log').innerHTML = h;
}
var MARK = {ok: '\u2713', warn: '!', info: 'i'};
function renderMac(j){
  var m = j.mac, h = '';
  $('macrun').disabled = false;
  h += m ? '<ul class="plist">' + m.items.map(function(it){
      return '<li><span><span class="pst ' + it.state + '">' + MARK[it.state] + '</span><b>'
        + esc(it.label) + '</b>: ' + esc(it.line) + '</span></li>'; }).join('') + '</ul>'
      + '<p class="unote">Checked ' + esc(m.at.slice(0, 16).replace('T', ' ')) + '.</p>'
    : '<p class="unote">Not checked yet.</p>';
  h += '<p class="usub">No code can check these, so they wait for your tick:</p><ul class="plist">'
    + (j.reminders || []).map(function(r){
        return '<li><span>' + esc(r.line) + '</span><button class="ubtn" data-tick="' + r.id + '" data-on="'
          + (r.ticked ? '0' : '1') + '">' + (r.ticked ? 'Done ' + esc(r.ticked.slice(5)) : 'Mark done') + '</button></li>';
      }).join('') + '</ul>';
  $('mac').innerHTML = h;
}

function renderPresent(j){
  var on = !!j.presenting;
  document.querySelectorAll('#presentseg button').forEach(function(b){
    b.disabled = false;
    b.classList.toggle('on', (b.dataset.present === 'on') === on);
  });
  $('now-present').textContent = on
    ? 'Right now: on since ' + esc((j.presenting.since || '').replace('T', ' ')) + '. Every page shows a bar to turn it off.'
    : 'Right now: off.';
  var chosen = on ? j.presenting.areas : (j.present_areas || []);
  var low = chosen.map(function(a){ return a.toLowerCase(); });
  $('presentareas').innerHTML = (j.areas || []).length
    ? '<p class="unote" style="margin-top:8px">Areas to leave out: ' + j.areas.map(function(a){
        return '<label style="margin-right:12px;white-space:nowrap"><input type="checkbox" data-parea="'
          + esc(a) + '"' + (low.indexOf(a.toLowerCase()) >= 0 ? ' checked' : '') + '> ' + esc(a) + '</label>';
      }).join('') + '</p>'
    : '';
}

function load(){
  return fetch('/api/privacy')
    .then(function(r){ if(!r.ok) throw new Error('offline'); return r.json(); })
    .then(function(j){ render(j); renderFolders(j); renderLog(j); renderMac(j); renderPresent(j); })
    .catch(function(){ /* static page: the explanation stands, switches stay off */ });
}

function loosens(r, i){
  return STATE && i < idx(r, STATE.values[r.k]);
}
function ask(loose){
  if(!loose) return true;
  return confirm('This loosens a setting.'
    + (STATE && STATE.touch ? ' Your Mac will ask for your fingerprint next.' : ''));
}

document.querySelectorAll('.plevel').forEach(function(b){
  b.onclick = function(){
    var lv = b.dataset.level;
    if(!STATE || lv === STATE.match) return;
    var loose = STATE.levels && Object.keys(STATE.levels[lv]).some(function(k){
      var r = rowOf(k); return r && idx(r, STATE.levels[lv][k]) < idx(r, STATE.values[k]);
    });
    if(!ask(loose)) return;
    post('/api/privacy/level', {level: lv}).then(load)
      .catch(function(e){ alert(e.message); load(); });
  };
});
document.addEventListener('click', function(ev){
  var b = ev.target.closest('button[data-key]');
  if(!b || b.disabled) return;
  var r = rowOf(b.dataset.key), i = +b.dataset.i;
  if(!r || !STATE || i === idx(r, STATE.values[r.k])) return;
  if(!ask(loosens(r, i))) return;
  post('/api/privacy/switch', {key: r.k, value: r.vals[i][0]}).then(load)
    .catch(function(e){ alert(e.message); load(); });
});

document.addEventListener('click', function(ev){
  var b = ev.target.closest('button[data-folder],button[data-unfolder],button[data-tick]');
  if(!b || !STATE) return;
  if(b.dataset.tick){
    post('/api/privacy/tick', {id: b.dataset.tick, on: b.dataset.on === '1'}).then(load)
      .catch(function(e){ alert(e.message); });
    return;
  }
  var list = (STATE.folders || []).slice();
  if(b.dataset.folder){
    if(!ask(true)) return;
    list.push(b.dataset.folder);
  } else {
    list = list.filter(function(f){ return f !== b.dataset.unfolder; });
  }
  post('/api/privacy/folders', {folders: list}).then(load)
    .catch(function(e){ alert(e.message); load(); });
});
document.querySelectorAll('#presentseg button').forEach(function(b){
  b.onclick = function(){
    var on = b.dataset.present === 'on';
    var areas = [].slice.call(document.querySelectorAll('[data-parea]:checked'))
      .map(function(c){ return c.dataset.parea; });
    b.disabled = true;
    post('/api/privacy/presenting', on ? {on: true, areas: areas} : {on: false}).then(load)
      .catch(function(e){ alert(e.message); load(); });
  };
});
document.addEventListener('change', function(ev){
  var c = ev.target.closest('[data-parea]');
  if(!c || !STATE || !STATE.presenting) return;    // off: read when turned on
  var areas = [].slice.call(document.querySelectorAll('[data-parea]:checked'))
    .map(function(x){ return x.dataset.parea; });
  post('/api/privacy/presenting', {areas: areas}).then(load)
    .catch(function(e){ alert(e.message); load(); });
});
$('macrun').onclick = function(){
  $('macrun').disabled = true;
  $('macrun').textContent = 'Checking\u2026';
  post('/api/privacy/maccheck', {}).then(function(){ $('macrun').textContent = 'Check now'; load(); })
    .catch(function(e){ $('macrun').textContent = 'Check now'; alert(e.message); load(); });
};

load();
setInterval(function(){ if(!document.hidden) load(); }, 60000);
})();
</script>
</body></html>
"""


if __name__ == "__main__":
    print("Built", build())

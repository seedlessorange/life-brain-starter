"""The app's chrome — one navigation, defined once, rendered on every page.

There were four of these. index.html had tabs for Today/Plate/People/Claude
and pills for Rooms/Sessions/Map; rooms.html and map.html had a three-link
strip that could not reach Plate, People or Claude at all; the desk had a
hamburger AND a second row of links underneath it, added because the
hamburger was "a closed door". They also disagreed about names: the same
destination was "Today" on one page, "Brain" on two others and "The brain" on
the fourth, and Claude was "History & queue" in one menu.

So: one list, one order, one set of names, everywhere. A page that adds a
destination adds it here and every other page grows the link.

The nav carries PLACES ONLY. Actions (capture, brain dump, what happened)
sat in the same pill row as Rooms and Map and looked identical to them, which
is what made the row read as a jumble — half of it navigates, half of it opens
a dialog, and nothing said which was which.
"""

# id, label, href from a page that is NOT index.html
# Sessions and Usage are not here: they live under Claude — one subject, the
# AI working for her — reached through claude_subnav() below. Their pages
# highlight "claude" in this bar.
PLACES = [
    ("today", "Today", "index.html#/today"),
    ("plate", "Plate", "index.html#/plate"),
    ("people", "People", "index.html#/people"),
    ("season", "Season", "index.html#/season"),
    ("news", "News", "index.html#/news"),
    ("cook", "Cook", "cook.html"),
    ("rooms", "Rooms", "rooms.html"),
    ("map", "Map", "map.html"),
    ("claude", "Claude", "index.html#/claude"),
]

# The views inside index.html rather than their own file.
IN_APP = {"today", "plate", "people", "season", "news", "claude"}


def nav_html(current="", in_app=False, cls="appnav"):
    """The navigation row.

    `current` is the place id to mark. `in_app` is True only for index.html,
    where the first four are router views and must stay hash-only so the SPA
    switches without a page load — a full reload there would lose scroll,
    open panels and any half-typed capture.
    """
    out = []
    for pid, label, href in PLACES:
        if in_app and pid in IN_APP:
            href = "#/" + pid
        on = ' class="on" aria-current="page"' if pid == current else ""
        out.append(f'<a href="{href}" data-nav="{pid}"{on}>{label}</a>')
    return f'<nav class="{cls}">' + "".join(out) + "</nav>"


# Styling for pages that do not already have a nav of their own (rooms, map,
# the desk). index.html keeps its own .topnav rules; this is deliberately
# scoped to .appnav so including it twice is harmless.
NAV_CSS = """
.appnav{display:flex;gap:2px;align-items:center;flex-wrap:wrap;min-width:0}
.appnav a{color:var(--dim);text-decoration:none;font-size:var(--t-sm,14px);
  font-weight:500;padding:6px 10px;border-radius:8px;white-space:nowrap}
.appnav a:hover{color:var(--ink);background:var(--surface)}
.appnav a.on{color:var(--ink);background:var(--sunken,var(--surface))}
@media (max-width:720px){
  .appnav{overflow-x:auto;-webkit-overflow-scrolling:touch;flex-wrap:nowrap}
}
"""


# The Claude family: the tab itself (jobs + the queue), the conversations,
# and the ledger. One sub-row at the top of all three moves between them.
CLAUDE_PAGES = [
    ("jobs", "Jobs", "index.html#/claude"),
    ("sessions", "Sessions", "sessions.html"),
    ("usage", "Usage", "usage.html"),
]

SUBNAV_CSS = """
.clsub{display:inline-flex;gap:2px;align-items:center;margin:14px 0 16px;
  padding:3px;border:1px solid var(--line);border-radius:999px;
  background:var(--surface);position:relative;z-index:2}
.clsub a{color:var(--dim);text-decoration:none;font-size:13px;font-weight:500;
  padding:5px 14px;border-radius:999px;white-space:nowrap}
.clsub a:hover{color:var(--ink)}
.clsub a.on{color:var(--ink);background:var(--paper);font-weight:600;
  box-shadow:0 1px 2px rgba(0,0,0,.10)}
"""


def claude_subnav(current, in_app=False):
    """The sub-row shared by the Claude tab, sessions.html and usage.html.
    Carries its own style tag so every page that drops it in is done.
    `in_app` is True on index.html, where the Jobs link must stay hash-only
    so the SPA switches without a reload."""
    out = []
    for pid, label, href in CLAUDE_PAGES:
        if in_app and pid == "jobs":
            href = "#/claude"
        on = ' class="on" aria-current="page"' if pid == current else ""
        out.append(f'<a href="{href}"{on}>{label}</a>')
    return ("<style>" + SUBNAV_CSS + "</style>"
            + '<nav class="clsub" aria-label="Claude pages">'
            + "".join(out) + "</nav>")


def header_html(current, owner="", right_html="", in_app=False):
    """The whole top bar, same shape on every page.

    The nav was shared but nothing around it was, so each page still opened
    looking like a different app: index had a wordmark on the left and the
    links pushed right, rooms had the links hard against the left edge with
    no wordmark at all, sessions had a hand-rolled strip that could not even
    reach Sessions. Same three zones everywhere now — who you are, where you
    can go, what THIS page does — and the third zone is the only part a page
    fills in.
    """
    brand = (f'<a class="apbrand" href="index.html#/today">'
             f'<img class="aplogo" src="logo-96.png?v=5" alt="" width="24" height="24">'
             f'<span>{owner} <b>brain</b></span></a>') if owner else ""
    return ('<header class="apptop">' + brand
            + nav_html(current, in_app=in_app, cls="appnav")
            + '<div class="apright">' + right_html + ask_button_html()
            + "</div></header>")


HEADER_CSS = """
.apptop{position:sticky;top:0;z-index:20;display:flex;gap:14px;align-items:center;
  padding:10px 20px;background:color-mix(in oklch,var(--paper) 86%,transparent);
  -webkit-backdrop-filter:blur(12px);backdrop-filter:blur(12px);
  border-bottom:1px solid var(--line)}
.apbrand{display:inline-flex;align-items:center;gap:9px;flex:none;
  font:600 1.125rem/1 var(--serif,'Literata',Georgia,serif);letter-spacing:-.01em;
  white-space:nowrap;color:var(--ink);text-decoration:none}
.apbrand b{font-weight:800}
.apbrand .aplogo{flex:none}
/* the links sit against the page's own controls, not against the wordmark */
.apptop>.appnav{margin-left:auto;flex:0 1 auto;min-width:80px;flex-wrap:nowrap;
  overflow-x:auto;overflow-y:hidden;scrollbar-width:none}
.apptop>.appnav::-webkit-scrollbar{display:none}
.apright{display:flex;gap:8px;align-items:center;flex:none}
@media(max-width:1000px){
  .apbrand span{display:none}
}
@media(max-width:720px){
  .apptop{padding:8px 12px;gap:8px}
  /* the right cluster shrinks and scrolls rather than pushing the page
     wide — a long pill there was the one thing that made pages side-scroll */
  .apright{flex:0 1 auto;min-width:0;overflow-x:auto;scrollbar-width:none}
  .apright::-webkit-scrollbar{display:none}
}
"""


def ask_button_html():
    return ('<button class="askopen" id="askopen" '
            # A real dash. Escaped, this printed the six characters — in
            # the tooltip — HTML is not JavaScript.
            'title="Ask the brain anything — ⌘K">'
            '✦ Ask</button>')


# ---------------------------------------------------------------------------
# Ask, from anywhere
#
# Every page could START Claude working — a queue item here, a quick run
# there, a conversation on Sessions — but only Sessions could show you what
# came back. So "just ask it something" meant navigating first and choosing a
# project second, for a question that had nothing to do with a project.
#
# This is one conversation, in the brain's own folder, opened from a button
# in every header and from Cmd/Ctrl-K. It is deliberately the SAME record the
# Sessions page shows: one place the turns live, one ledger they bill to. The
# panel is a small window onto it, not a second chat with its own memory.
#
# Cost is why it defaults to Haiku: a panel that is one keystroke away gets
# used like a search box, and the expensive models should be a deliberate
# choice made on the Sessions page.
# ---------------------------------------------------------------------------

ASK_SRC = "The brain"

ASK_CSS = """
.askopen{font:inherit;font-size:var(--t-sm,13px);font-weight:600;cursor:pointer;
  color:var(--ink);background:var(--surface);border:1px solid var(--line2);
  border-radius:var(--r-btn,10px);padding:6px 12px;white-space:nowrap}
.askopen:hover{border-color:var(--dim)}
/* Above the tour (79-82), which lays a full-screen transparent button over
   the page to catch "click anywhere to advance". At 60/61 the Ask panel
   opened UNDERNEATH that button: every click in the panel was swallowed by
   the tour while the keyboard, which does not hit-test, went on working. A
   panel she opened on purpose is the topmost thing on the page. */
.askscrim{position:fixed;inset:0;z-index:95;background:rgba(0,0,0,.22);
  opacity:0;transition:opacity .16s ease-out}
.askscrim.on{opacity:1}
.askscrim[hidden]{display:none}
.askpanel{position:fixed;top:0;right:0;bottom:0;z-index:96;width:min(440px,100vw);
  display:flex;flex-direction:column;background:var(--paper);
  border-left:1px solid var(--line);box-shadow:-8px 0 34px rgba(0,0,0,.14);
  transform:translateX(100%);transition:transform .2s cubic-bezier(.16,1,.3,1)}
.askpanel.on{transform:none}
.askpanel[hidden]{display:none}
.askhead{display:flex;gap:10px;align-items:center;padding:13px 16px;
  border-bottom:1px solid var(--line);flex:none}
.askhead h2{margin:0;font:600 15px/1.2 var(--serif,'Literata',Georgia,serif)}
.askhead .asksub{font-size:11.5px;color:var(--faint)}
.askx{border:0;background:none;color:var(--faint);cursor:pointer;
  font-size:20px;line-height:1;padding:2px 4px}
.askx:hover{color:var(--ink)}
.askfull{margin-left:auto;font-size:11.5px;font-weight:600;color:var(--green,var(--ink));
  text-decoration:none;white-space:nowrap}
.askfull:hover{text-decoration:underline}
.asknew{border:0;background:none;cursor:pointer;font:inherit;font-size:11.5px;
  font-weight:600;color:var(--green,var(--ink));white-space:nowrap;padding:0}
.asknew:hover{text-decoration:underline}
.asknew[hidden]{display:none}
.askthread{flex:1;overflow-y:auto;padding:16px;display:flex;flex-direction:column;
  gap:14px;font-size:14px;line-height:1.55}
.askmsg{max-width:92%}
.askmsg.her{align-self:flex-end;background:var(--sunken,var(--surface));
  border-radius:12px 12px 4px 12px;padding:10px 13px;white-space:pre-wrap}
.askmsg.claude .askwho{font-size:10.5px;font-weight:700;letter-spacing:.09em;
  text-transform:uppercase;color:var(--faint);margin-bottom:5px}
.askmsg.claude .askbody p{margin:0 0 8px}
.askmsg.claude .askbody p:last-child{margin:0}
.askmsg.claude .askbody li{margin:0 0 3px}
.askmsg.claude .askbody ul{margin:0 0 8px;padding-left:20px}
.askmsg.claude .askbody code{font-family:ui-monospace,Menlo,monospace;font-size:12.5px;
  background:var(--surface);padding:1px 4px;border-radius:4px}
.askmsg.note{align-self:center;font-size:12px;color:var(--faint);text-align:center}
.askempty{margin:auto 0;color:var(--faint);font-size:13.5px;text-align:center;
  padding:0 10px}
.askwork{display:flex;gap:8px;align-items:center;color:var(--faint);font-size:12.5px}
.askwork i{width:7px;height:7px;border-radius:50%;background:var(--green,var(--ink));
  animation:askpulse 1.3s ease-in-out infinite}
@keyframes askpulse{0%,100%{opacity:1}50%{opacity:.3}}
@media(prefers-reduced-motion:reduce){
  .askwork i{animation:none}
  .askpanel{transition:none}
}
/* What it should look at. "everything" is the whole brain; picking chips
   narrows the question — cheaper, and the answer stops wandering off into
   the other eleven files. Nothing selected is a plain chat: no files read. */
.askctx{flex:none;display:flex;flex-wrap:wrap;gap:5px;align-items:center;
  padding:9px 14px;border-bottom:1px solid var(--line);background:var(--surface)}
.askctxlab{font-size:10.5px;font-weight:700;letter-spacing:.08em;
  text-transform:uppercase;color:var(--faint);margin-right:3px}
.ctxchip{font:inherit;font-size:12px;cursor:pointer;border:1px solid var(--line2);
  background:var(--paper);color:var(--dim);border-radius:999px;padding:4px 10px}
.ctxchip:hover{border-color:var(--dim);color:var(--ink)}
.ctxchip.on{background:var(--green,var(--ink));border-color:transparent;
  color:var(--paper);font-weight:600}
.askfoot{flex:none;border-top:1px solid var(--line);padding:11px 13px;
  display:flex;gap:8px;align-items:flex-end;flex-wrap:wrap}
/* Attachments: the paperclip, and what is waiting to go with the next ask. */
.askclip{flex:none;font:inherit;font-size:15px;cursor:pointer;color:var(--dim);
  background:var(--surface);border:1px solid var(--line);border-radius:10px;
  padding:8px 11px;line-height:1}
.askclip:hover{border-color:var(--dim);color:var(--ink)}
.askfiles{flex-basis:100%;display:flex;flex-wrap:wrap;gap:5px;order:-1}
.askfiles:empty{display:none}
.askfile{display:inline-flex;align-items:center;gap:6px;font-size:11.5px;
  background:var(--surface);border:1px solid var(--line);border-radius:999px;
  padding:3px 5px 3px 9px;color:var(--dim);max-width:190px}
.askfile span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.askfile b{font-weight:400;cursor:pointer;padding:0 3px;color:var(--faint)}
.askfile b:hover{color:var(--ink)}
.askfile img{width:22px;height:22px;border-radius:4px;object-fit:cover;flex:none}
.askfoot textarea{flex:1;font:inherit;font-size:14px;padding:9px 12px;resize:none;
  min-height:40px;max-height:150px;border:1px solid var(--line);border-radius:10px;
  background:var(--surface);color:var(--ink)}
.askfoot textarea:focus{outline:2px solid var(--green,var(--ink));outline-offset:1px;
  border-color:transparent}
.asksend{flex:none;font:inherit;font-size:13px;font-weight:700;cursor:pointer;
  border:0;border-radius:10px;padding:10px 15px;
  background:var(--green,var(--ink));color:var(--paper)}
.asksend:disabled{opacity:.45;cursor:default}
/* Floating corner buttons — the capture FAB, the tour's "?", the agent pill —
   live exactly where the panel's own send button lands. They step aside while
   it is open rather than sitting on top of it. */
body.asking .fab,body.asking .btour-btn,body.asking .agentbar{display:none}

"""


def ask_html():
    return ("""
<div class="askscrim" id="askscrim" hidden></div>
<aside class="askpanel" id="askpanel" hidden aria-label="Ask the brain">
  <div class="askhead">
    <div><h2>Ask the brain</h2>
      <div class="asksub" id="asksub">anything &mdash; it reads your whole brain</div></div>
    <a class="askfull" id="askfull" href="sessions.html">open in Sessions</a>
    <button class="asknew" id="asknew" hidden>new chat</button>
    <button class="askx" id="askx" aria-label="Close">&times;</button>
  </div>
  <div class="askctx" id="askctx">
    <span class="askctxlab">Looking at</span>
    <button class="ctxchip on" data-f="">everything</button>
    <button class="ctxchip" data-f="brain/today.md">today</button>
    <button class="ctxchip" data-f="brain/workstreams.md">the plate</button>
    <button class="ctxchip" data-f="brain/people.md">people</button>
    <button class="ctxchip" data-f="brain/habits.md">habits</button>
    <button class="ctxchip" data-f="brain/about-me.md">about you</button>
    <button class="ctxchip" data-f="brain/writing-rules.md">writing style</button>
  </div>
  <div class="askthread" id="askthread"></div>
  <div class="askfoot">
    <div class="askfiles" id="askfiles"></div>
    <input type="file" id="askfilein" multiple hidden
      accept=".pdf,.png,.jpg,.jpeg,.webp,.gif,.txt,.md,.csv,.docx,.xlsx,.ics,.json">
    <button class="askclip" id="askclip" title="Attach documents or images"
      aria-label="Attach documents or images">&#128206;</button>
    <textarea id="asktext" data-mic="1" rows="1"
      placeholder="Ask anything"></textarea>
    <!-- askgo, not asksend: the Today page already has an asksend. -->
    <button class="asksend" id="askgo">Ask</button>
  </div>
</aside>
""")


ASK_JS = r"""
(function(){
var SRC = __ASKSRC__;
var panel = document.getElementById('askpanel');
if(!panel) return;
// Look INSIDE the panel, never across the page. This panel is injected into
// every page in the brain, so any id it uses is one a page might already
// have — and getElementById hands back whichever came first in the document.
// The Today page has its own "Add to the queue" button called asksend, so the
// panel's Ask button was wiring its click to a hidden button on another
// widget: pressing Ask did nothing, while Enter (bound to the textarea, which
// happened to be unique) worked fine.
function E(id){ return panel.querySelector('#' + id); }
var scrim = document.getElementById('askscrim'), thread = E('askthread'),
    ta = E('asktext'), send = E('askgo'),
    sub = E('asksub'), full = E('askfull'), fresh = E('asknew'),
    ctx = E('askctx'), clip = E('askclip'),
    filein = E('askfilein'), filebar = E('askfiles');
var CID = null, TIMER = null, WORKING = false, STAMP = '';
var PENDING = [];   // {name, data} waiting to go with the next ask

function esc(s){ return String(s == null ? '' : s)
  .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }
// Just enough markdown for an answer to be readable — bold, code, bullets,
// paragraphs. Anything richer belongs on the Sessions page, which is one
// click away in the header.
function mini(t){
  var out = [], list = false;
  (t || '').split('\n').forEach(function(line){
    var s = line.trim();
    var m = s.match(/^[-*]\s+(.*)/);
    if(m){ if(!list){ out.push('<ul>'); list = true; } out.push('<li>' + inl(m[1]) + '</li>'); return; }
    if(list){ out.push('</ul>'); list = false; }
    if(s) out.push('<p>' + inl(s) + '</p>');
  });
  if(list) out.push('</ul>');
  return out.join('');
}
function inl(s){ return esc(s).replace(/\*\*(.+?)\*\*/g, '<b>$1</b>')
  .replace(/`([^`]+)`/g, '<code>$1</code>'); }

// The last record we were given, what she has just said but the record does
// not know about yet, and anything the panel needs to tell her. Kept apart so
// a note about a failure never wipes the conversation it happened in.
var LAST = [], ECHO = '', NOTE = '';
function note(msg){ NOTE = msg || ''; paint(); }
function paint(events){
  if(events) LAST = events;
  thread.innerHTML = '';
  var shown = 0;
  // Once the record carries what she said, the optimistic copy retires.
  if(ECHO && LAST.some(function(ev){
      return ev.k === 'her' && (ev.t || '').indexOf(ECHO) >= 0; })) ECHO = '';
  LAST.forEach(function(ev){
    var d = document.createElement('div');
    if(ev.k === 'her'){ d.className = 'askmsg her'; d.textContent = ev.t; }
    else if(ev.k === 'claude'){
      d.className = 'askmsg claude';
      d.innerHTML = '<div class="askwho">Claude</div><div class="askbody">'
                    + mini(ev.t) + '</div>';
    }
    else if(ev.k === 'note'){ d.className = 'askmsg note'; d.textContent = ev.t; }
    else return;                       // tool steps stay on the Sessions page
    thread.appendChild(d); shown++;
  });
  if(ECHO){
    var h = document.createElement('div');
    h.className = 'askmsg her'; h.textContent = ECHO;
    thread.appendChild(h); shown++;
  }
  if(WORKING || ECHO){
    var w = document.createElement('div');
    w.className = 'askwork'; w.innerHTML = '<i></i> thinking…';
    thread.appendChild(w); shown++;
  }
  if(NOTE){
    var nd = document.createElement('div');
    nd.className = 'askmsg note'; nd.textContent = NOTE;
    thread.appendChild(nd); shown++;
  }
  if(!shown){
    var e2 = document.createElement('p');
    e2.className = 'askempty';
    e2.textContent = 'Ask anything about your brain — what is on your plate, '
      + 'who you owe a reply, what to do first. Answers land here; nothing is '
      + 'emailed or messaged to anyone.';
    thread.appendChild(e2);
  }
  thread.scrollTop = thread.scrollHeight;
}

function setLink(){
  full.href = CID ? ('sessions.html#' + encodeURIComponent(CID)) : 'sessions.html';
  fresh.hidden = !CID;
}

// "new chat" ends the conversation the panel is attached to and clears the
// feed; the next ask starts a fresh one. The old thread stays on the
// Sessions page and can be reopened. The server refuses while a turn is
// running — its message lands here as a note.
fresh.onclick = function(){
  if(!CID) return;
  fetch('/api/sessions/end', {method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({id: CID})})
    .then(function(r){ return r.json().catch(function(){ return {}; }); })
    .then(function(j){
      if(j.error){ note(j.error); return; }
      CID = null; WORKING = false; STAMP = ''; ECHO = ''; NOTE = '';
      setLink(); paint([]);
      ta.focus();
    })
    .catch(function(){
      note('Could not reach the brain — is it still running?');
    });
};

// ── what it should look at ────────────────────────────────────────────────
// "everything" is the whole brain. Choosing files turns the question into
// "answer from these" — faster and cheaper. Nothing selected is a plain
// chat: no files are read at all.
function ctxFiles(){
  return Array.prototype.filter.call(ctx.querySelectorAll('.ctxchip'), function(b){
    return b.classList.contains('on') && b.dataset.f;
  }).map(function(b){ return b.dataset.f; });
}
function ctxAll(){
  return ctx.querySelector('.ctxchip[data-f=""]').classList.contains('on');
}
ctx.addEventListener('click', function(e){
  var b = e.target.closest('.ctxchip'); if(!b) return;
  var all = ctx.querySelector('.ctxchip[data-f=""]');
  if(!b.dataset.f){                       // "everything" toggles; on clears the rest
    var on = !all.classList.contains('on');
    ctx.querySelectorAll('.ctxchip').forEach(function(x){ x.classList.remove('on'); });
    all.classList.toggle('on', on);
  } else {
    b.classList.toggle('on');
    if(b.classList.contains('on')) all.classList.remove('on');
  }
  sub.textContent = ctxAll() ? 'anything — it reads your whole brain'
    : ctxFiles().length ? 'answering from what you picked'
    : 'plain chat — it reads nothing';
});

// ── attachments ───────────────────────────────────────────────────────────
function paintFiles(){
  filebar.innerHTML = '';
  PENDING.forEach(function(f, i){
    var d = document.createElement('span');
    d.className = 'askfile';
    var thumb = /^data:image\//.test(f.data)
      ? '<img src="' + f.data + '" alt="">' : '';
    d.innerHTML = thumb + '<span>' + esc(f.name) + '</span><b data-i="' + i + '">&times;</b>';
    filebar.appendChild(d);
  });
}
filebar.addEventListener('click', function(e){
  if(e.target.tagName !== 'B') return;
  PENDING.splice(+e.target.dataset.i, 1); paintFiles();
});
function addFiles(list){
  Array.prototype.forEach.call(list, function(file){
    if(PENDING.length >= 20) return;
    var r = new FileReader();
    r.onload = function(){
      PENDING.push({name: file.name || 'pasted.png', data: r.result});
      paintFiles();
    };
    r.readAsDataURL(file);
  });
}
clip.onclick = function(){ filein.click(); };
filein.onchange = function(){ addFiles(filein.files); filein.value = ''; };
// Paste a screenshot straight into the box — the way she actually sends one.
ta.addEventListener('paste', function(e){
  var items = (e.clipboardData || {}).items || [], got = [];
  for(var i = 0; i < items.length; i++){
    if(items[i].kind === 'file'){ var f = items[i].getAsFile(); if(f) got.push(f); }
  }
  if(got.length){ e.preventDefault(); addFiles(got); }
});
// Drop them on the panel too.
panel.addEventListener('dragover', function(e){ e.preventDefault(); });
panel.addEventListener('drop', function(e){
  if(!e.dataTransfer || !e.dataTransfer.files.length) return;
  e.preventDefault(); addFiles(e.dataTransfer.files);
});

function pull(){
  if(!CID) return Promise.resolve();
  return fetch('/api/sessions/transcript?id=' + encodeURIComponent(CID))
    .then(function(r){ return r.json(); })
    .then(function(j){ paint(j.events || []); });
}

// Which conversation this is: the newest live one in the brain's own folder,
// so the panel and the Sessions page are looking at the same record rather
// than each keeping a private thread.
function attach(){
  return fetch('/api/sessions/room?src=' + encodeURIComponent(SRC))
    .then(function(r){ return r.json(); })
    .then(function(j){
      var live = (j.convos || []);
      if(live.length){
        CID = live[live.length - 1].id;
        WORKING = live.some(function(c){ return c.id === CID && c.state === 'working'; });
      }
      setLink();
      return CID ? pull() : paint([]);
    })
    // The server being down looked exactly like having nothing to say: an
    // empty panel with a working-looking box. Say which one it is.
    .catch(function(){
      paint([]);
      note('The brain is not answering on this Mac — start it and reopen this.');
    });
}

function poll(){
  if(TIMER) clearInterval(TIMER);
  TIMER = setInterval(function(){
    if(document.hidden || panel.hidden) return;
    fetch('/api/sessions/room?src=' + encodeURIComponent(SRC))
      .then(function(r){ return r.json(); })
      .then(function(j){
        var me = (j.convos || []).filter(function(c){ return c.id === CID; })[0];
        var was = WORKING;
        WORKING = !!(me && me.state === 'working');
        if(me && me.last === STAMP && was === WORKING) return;
        if(me) STAMP = me.last;
        pull();
      })
      .catch(function(){});
  }, 2200);
}

function open(){
  panel.hidden = false; scrim.hidden = false;
  document.body.classList.add('asking');
  requestAnimationFrame(function(){ panel.classList.add('on'); scrim.classList.add('on'); });
  ta.focus();
  attach().then(poll);
}
function close(){
  panel.classList.remove('on'); scrim.classList.remove('on');
  document.body.classList.remove('asking');
  if(TIMER){ clearInterval(TIMER); TIMER = null; }
  setTimeout(function(){ panel.hidden = true; scrim.hidden = true; }, 190);
}

// The files go up first and come back as paths in the brain; the ask itself
// carries the paths, so the session reads them the same way it reads anything
// else. Nothing is uploaded anywhere but this Mac.
function upload(){
  if(!PENDING.length) return Promise.resolve([]);
  return fetch('/api/upload', {method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({files: PENDING})})
    .then(function(r){ return r.json(); })
    .then(function(j){
      if(j.error) throw new Error(j.error);
      // The upload endpoint answers relative to brain/, but a conversation
      // runs from the folder above it — so "files/x.png" would be a path to
      // nothing. Say where the file is from where the session is standing.
      return (j.saved || []).map(function(p){
        return /^brain\//.test(p) ? p : 'brain/' + p;
      });
    });
}

function ask(){
  var t = ta.value.trim();
  // Every way this can decline has to SAY so. Both of these used to return
  // in silence, which from the outside is a button that does nothing: you
  // press Ask, your words stay in the box, and the panel goes on showing the
  // same empty state it showed before.
  if(!t && !PENDING.length){ ta.focus(); return; }
  if(WORKING){
    note('Still working on the last one — it will answer here.');
    return;
  }
  send.disabled = true;
  // Her words go up the moment she presses, before the upload and the post.
  // The gap between the press and the first poll was dead air with nothing
  // in it, and dead air after a button press reads as a broken button.
  ECHO = t; NOTE = '';
  paint();
  upload().then(function(saved){
    var parts = [];
    var files = ctxFiles();
    if(files.length)
      parts.push('For this question read ' + files.join(' and ')
                 + ' and answer from those; do not go looking through the rest '
                 + 'of the brain unless they cannot answer it.');
    else if(!ctxAll())
      parts.push('Plain chat: answer from the conversation itself, '
                 + 'without reading the brain\'s files.');
    if(t) parts.push(t);
    if(saved.length)
      parts.push('Attached, read them: ' + saved.join(', '));
    sendAsk(parts.join('\n\n'));
  }).catch(function(e){
    send.disabled = false; ECHO = '';
    note('That did not go: ' + (e && e.message ? e.message : 'unknown'));
  });
}

function sendAsk(t){
  var body = JSON.stringify(CID ? {id: CID, text: t, model: 'haiku'}
                                : {src: SRC, text: t, model: 'haiku'});
  fetch(CID ? '/api/sessions/say' : '/api/sessions/new',
        {method: 'POST', headers: {'Content-Type': 'application/json'}, body: body})
    // A refusal from the server arrives as a status, and asking a failed
    // response for .json() throws inside the promise where nobody sees it.
    // Read the body either way and let the message reach her.
    .then(function(r){ return r.text().then(function(txt){
      var j = {};
      try { j = JSON.parse(txt); } catch(e){ j = {error: txt.slice(0, 200)}; }
      if(!r.ok && !j.error) j.error = 'the brain answered ' + r.status;
      return j;
    }); })
    .then(function(j){
      send.disabled = false;
      if(j.error){
        ECHO = '';
        note(j.error);
        return;
      }
      NOTE = '';
      if(j.id) CID = j.id;
      setLink();
      ta.value = ''; ta.style.height = '';
      PENDING = []; paintFiles();
      WORKING = true; pull(); poll();
    })
    .catch(function(e){
      send.disabled = false; ECHO = '';
      note('Could not reach the brain — is it still running? ('
           + (e && e.message ? e.message : 'no reply') + ')');
    });
}

var btn = document.getElementById('askopen');
if(btn) btn.onclick = open;
E('askx').onclick = close;
scrim.onclick = close;
send.onclick = ask;
ta.addEventListener('input', function(){
  ta.style.height = 'auto'; ta.style.height = Math.min(ta.scrollHeight, 150) + 'px';
});
ta.addEventListener('keydown', function(e){
  if(e.key === 'Enter' && !e.shiftKey){ e.preventDefault(); ask(); }
});
addEventListener('keydown', function(e){
  if((e.metaKey || e.ctrlKey) && (e.key === 'k' || e.key === 'K')){
    e.preventDefault(); panel.hidden ? open() : close();
  }
  if(e.key === 'Escape' && !panel.hidden) close();
});
})();
"""


def ask_block(indent=""):
    """Panel + styles + script, ready to drop in before </body>."""
    import json as _json
    return ("<style>" + ASK_CSS + "</style>" + ask_html()
            + "<script>" + ASK_JS.replace("__ASKSRC__", _json.dumps(ASK_SRC))
            + "</script>")

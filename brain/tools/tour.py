#!/usr/bin/env python3
"""The guided tour — how the brain teaches itself to a new person.

Each generated page appends `block(key, steps, ...)` before </body>: a
spotlight walkthrough of that page's important features. It starts by itself
on a device's first visit, can always be re-run from the round "?" button,
resumes mid-tour if the page reloads under it, and chains page to page
(brain → map → rooms) so the whole system is one continuous walkthrough.

A step: {"el": "#askbox", "title": "...", "body": "...",
         "pre": {"hash": "#/claude"} or {"click": ".room"}}
`el` None centres the card with no spotlight. A step whose element is
missing or hidden is skipped silently — empty states never break the tour.
"""

import json

CSS = """
.btour-btn{position:fixed;right:16px;bottom:14px;z-index:79;width:40px;height:40px;
  border-radius:50%;border:1.5px solid var(--line);background:var(--surface);
  color:var(--dim);font-weight:700;font-size:17px;line-height:1;font-family:inherit;
  cursor:pointer;box-shadow:0 4px 20px var(--shadow,rgba(0,0,0,.12))}
.btour-btn:hover{color:var(--text);border-color:var(--dim)}
/* It shares the bottom-right corner with the capture button on the brain
   page, and sat right on top of it. The script below measures whatever
   floating control is already parked there and lifts the ? clear of it, so
   this works on every page without each page having to know. */
.btour-btn.lifted{bottom:var(--btour-lift,86px)}
.btour-hole{position:fixed;z-index:80;border-radius:12px;pointer-events:none;
  box-shadow:0 0 0 9999px color-mix(in oklch, var(--ink) 45%, transparent);
  outline:2px solid var(--green);outline-offset:2px;
  transition:all .28s cubic-bezier(.16,1,.3,1)}
.btour-hole.bare{outline:none}
.btour-block{position:fixed;inset:0;z-index:81;background:transparent;border:0;
  padding:0;margin:0;cursor:default}
.btour-card{position:fixed;z-index:82;width:min(340px,calc(100vw - 32px));
  box-sizing:border-box;max-height:min(70vh,440px);overflow:auto;
  background:var(--surface);border:1.5px solid var(--line);border-radius:16px;
  padding:16px 18px 13px;box-shadow:0 12px 40px rgba(0,0,0,.25);
  transition:all .28s cubic-bezier(.16,1,.3,1)}
.btour-card h3{margin:0 0 6px;font:600 16px/1.3 var(--serif,Georgia,serif);
  color:var(--text)}
.btour-card p{margin:0;font-size:13.5px;line-height:1.55;color:var(--dim)}
.btour-row{display:flex;gap:8px;align-items:center;margin-top:13px}
.btour-row .tn{font-size:11px;color:var(--faint);margin-right:auto}
.btour-row button{font:inherit;font-size:12.5px;font-weight:600;cursor:pointer;
  border:1px solid var(--line);border-radius:9px;background:var(--bg);
  color:var(--text);padding:7px 12px}
.btour-row button.tgo{background:var(--green);color:var(--bg);border-color:transparent;
  font-weight:700}
.btour-skip{border:0;background:none;font:inherit;font-size:11.5px;cursor:pointer;
  color:var(--faint);padding:4px 2px;margin-top:4px}
.btour-skip:hover{color:var(--dim)}
@media(max-width:640px){
  .btour-card{left:16px !important;right:16px;width:auto;bottom:16px;top:auto !important}
}
@media(prefers-reduced-motion: reduce){
  .btour-hole,.btour-card{transition:none}
}
"""

ENGINE = r"""
(function(){
var KEY = '__KEY__', STEPS = __STEPS__, NEXT = __NEXT__;
var cur = -1, hole = null, card = null, block = null, btn = null;

function lsGet(k){ try { return localStorage.getItem(k); } catch(e){ return null; } }
function lsSet(k, v){ try { localStorage.setItem(k, v); } catch(e){} }
function ssGet(k){ try { return sessionStorage.getItem(k); } catch(e){ return null; } }
function ssSet(k, v){ try { v === null ? sessionStorage.removeItem(k)
                                       : sessionStorage.setItem(k, v); } catch(e){} }

function target(step){
  if(!step.el) return null;
  var els = document.querySelectorAll(step.el);
  for(var i = 0; i < els.length; i++)
    if(els[i].offsetParent !== null || els[i].tagName === 'svg') return els[i];
  return null;
}

function build(){
  if(card) return;
  hole = document.createElement('div'); hole.className = 'btour-hole'; hole.hidden = true;
  block = document.createElement('button'); block.className = 'btour-block';
  block.setAttribute('aria-label', 'Next');
  // Clicking outside advances — except on the last step, where it must
  // dismiss: "anywhere I tap drags me into another page's tour" is a trap.
  block.onclick = function(){
    if(cur === STEPS.length - 1) end(true, false);
    else go(1);
  };
  card = document.createElement('div'); card.className = 'btour-card';
  card.setAttribute('role', 'dialog');
  card.innerHTML = '<h3></h3><p></p>'
    + '<div class="btour-row"><span class="tn"></span>'
    + '<button class="tback">Back</button>'
    + '<button class="tgo">Next</button></div>'
    + '<button class="btour-skip">Skip for now — the ? brings it back here</button>';
  card.querySelector('.tback').onclick = function(ev){ ev.stopPropagation(); go(-1); };
  card.querySelector('.tgo').onclick = function(ev){ ev.stopPropagation(); go(1); };
  card.querySelector('.btour-skip').onclick = function(ev){
    ev.stopPropagation();
    // Mid-tour: leave, keeping the place. Last step: done — and pointedly
    // NOT swept into the next page's tour.
    if(cur === STEPS.length - 1) end(true, false);
    else end();
  };
  card.onclick = function(ev){ ev.stopPropagation(); };
  document.body.appendChild(block);
  document.body.appendChild(hole);
  document.body.appendChild(card);
}

function place(){
  var step = STEPS[cur];
  if(!step) return;
  var t = target(step);
  if(t && t.scrollIntoView){
    var r0 = t.getBoundingClientRect();
    if(r0.top < 0 || r0.bottom > innerHeight)
      t.scrollIntoView({block: 'center'});
  }
  var r = t ? t.getBoundingClientRect() : null;
  if(r){
    var pad = 6;
    hole.hidden = false;
    hole.classList.remove('bare');
    hole.style.left = (r.left - pad) + 'px';
    hole.style.top = (r.top - pad) + 'px';
    hole.style.width = (r.width + pad * 2) + 'px';
    hole.style.height = (r.height + pad * 2) + 'px';
  } else {
    hole.hidden = false;
    hole.classList.add('bare');
    hole.style.left = '50%'; hole.style.top = '50%';
    hole.style.width = '0px'; hole.style.height = '0px';
  }
  // Inline resets every time: the host page may style generic dialogs or
  // share a class name — nothing it does may stretch or shift this card.
  card.style.bottom = 'auto';
  card.style.right = 'auto';
  card.style.height = 'auto';
  card.style.transform = 'none';
  card.style.margin = '0';
  var ch = card.offsetHeight || 170, cw = card.offsetWidth || 340;
  var cx, cy;
  if(r && r.height < innerHeight * 0.7){
    cy = (r.bottom + 14 + ch < innerHeight) ? r.bottom + 14
       : (r.top - 14 - ch > 0) ? r.top - 14 - ch
       : Math.max(16, innerHeight - ch - 20);
    cx = Math.max(16, Math.min(r.left, innerWidth - cw - 16));
  } else if(r){
    // the target is most of the screen — sit at the bottom centre, over it
    cy = Math.max(16, innerHeight - ch - 24);
    cx = innerWidth / 2 - cw / 2;
  } else {
    cy = Math.max(16, innerHeight / 2 - ch / 2);
    cx = innerWidth / 2 - cw / 2;
  }
  card.style.left = cx + 'px';
  card.style.top = cy + 'px';
}

function show(i, dir){
  dir = dir || 1;
  if(i < 0) i = 0;
  if(i >= STEPS.length){ end(true); return; }
  var step = STEPS[i];
  var was = cur; cur = i;
  var apply = function(){
    if(step.el && !target(step) && !(step.pre)){    // nothing to point at
      show(i + dir, dir); return;
    }
    build();
    var last = i === STEPS.length - 1;
    card.querySelector('h3').textContent = step.title;
    card.querySelector('p').textContent = step.body;
    card.querySelector('.tn').textContent = (i + 1) + ' of ' + STEPS.length;
    card.querySelector('.tback').style.visibility = i === 0 ? 'hidden' : '';
    card.querySelector('.tgo').textContent =
      last ? (NEXT ? NEXT.label + ' →' : 'Done ✓') : 'Next';
    // The skip is the exit, so it exists on every step. Without NEXT the
    // last step's Done button already IS the exit — only then is it spare.
    var sk = card.querySelector('.btour-skip');
    sk.style.display = (last && !NEXT) ? 'none' : '';
    sk.textContent = last ? 'Finish here — skip the next tour'
                          : 'Skip for now — the ? brings it back here';
    ssSet('tour-step-' + KEY, String(i));
    place();
    setTimeout(place, 320);              // after any scroll/layout settles
  };
  if(step.pre){
    if(step.pre.hash !== undefined && location.hash !== step.pre.hash)
      location.hash = step.pre.hash;
    if(step.pre.click){
      var el = document.querySelector(step.pre.click);
      if(el) el.click();
    }
    setTimeout(function(){
      if(step.el && !target(STEPS[cur])){ show(i + dir, dir); return; }
      apply();
    }, 380);
  } else apply();
}

function go(dir){
  if(cur === STEPS.length - 1 && dir === 1){ end(true); return; }
  show(cur + dir, dir);
}

function end(finished, navigate){
  lsSet('tour-done-' + KEY, '1');
  ssSet('tour-step-' + KEY, null);
  // Leaving is never losing your place: the ? button resumes from here,
  // in this session or any later one.
  try {
    if(finished) localStorage.removeItem('tour-left-' + KEY);
    else if(cur >= 0) localStorage.setItem('tour-left-' + KEY, String(cur));
  } catch(e){}
  if(hole){ hole.remove(); hole = null; }
  if(card){ card.remove(); card = null; }
  if(block){ block.remove(); block = null; }
  var was = cur; cur = -1;
  if(finished && navigate !== false && NEXT && was === STEPS.length - 1)
    location.href = NEXT.url + '?tour';
}

function start(){
  if(cur >= 0) return;
  show(0, 1);
}

document.addEventListener('keydown', function(e){
  if(cur < 0) return;
  if(e.key === 'Escape'){ end(); }
  else if(e.key === 'ArrowRight'){ e.preventDefault(); go(1); }
  else if(e.key === 'ArrowLeft'){ e.preventDefault(); go(-1); }
});
addEventListener('resize', function(){ if(cur >= 0) place(); });
addEventListener('scroll', function(){ if(cur >= 0) place(); }, true);

btn = document.createElement('button');
btn.className = 'btour-btn'; btn.textContent = '?';
btn.title = 'Show me around';
btn.setAttribute('aria-label', 'Start the tour of this page');
btn.onclick = function(){
  end();
  var left = lsGet('tour-left-' + KEY);      // resume where they left off
  show(left !== null ? (parseInt(left, 10) || 0) : 0, 1);
};
document.body.appendChild(btn);

// Lift clear of any other floating control in the same corner (the capture
// button on the brain page). Measured, not hardcoded, because that button
// moves up on narrow screens to clear the tab bar.
function lift(){
  var other = document.querySelector('.fab');
  var r = other && !other.hidden ? other.getBoundingClientRect() : null;
  if(!r || !r.height || r.right < innerWidth - 140){
    btn.classList.remove('lifted'); return;
  }
  btn.style.setProperty('--btour-lift',
    Math.round(innerHeight - r.top + 12) + 'px');
  btn.classList.add('lifted');
}
lift();
addEventListener('resize', lift);

var resume = ssGet('tour-step-' + KEY);
var forced = /[?&]tour\b/.test(location.search);
if(forced){
  try { history.replaceState(null, '',
    location.pathname + location.hash); } catch(e){}
}
if(resume !== null){
  setTimeout(function(){ show(parseInt(resume, 10) || 0, 1); }, 700);
} else if(forced || (!lsGet('tour-done-' + KEY)
                     && lsGet('tour-pending') !== '1')){
  // tour-pending means the page's own post-dump tour is about to run —
  // never talk over it
  setTimeout(start, 900);
}
})();
"""


def block(key, steps, next_url="", next_label=""):
    """The whole tour as one self-contained <style>+<script> block."""
    nxt = json.dumps({"url": next_url, "label": next_label} if next_url
                     else None)
    js = (ENGINE
          .replace("__KEY__", key)
          .replace("__STEPS__", json.dumps(steps).replace("</", "<\\/"))
          .replace("__NEXT__", nxt))
    return "<style>" + CSS + "</style>\n<script>" + js + "</script>\n"


# ---------------------------------------------------------------------------
# The walkthroughs themselves. One voice throughout: what a thing IS, then
# the one behaviour worth knowing. The chain is brain → map → rooms.

BRAIN_STEPS = [
    {"el": None, "title": "The brain",
     "body": "This page tracks your tasks, projects, people and habits, all "
             "stored as plain markdown files. Claude keeps the files "
             "updated; you use the page to see what needs attention and to "
             "tick things off."},
    {"el": ".topnav", "pre": {"hash": "#/today"}, "title": "One bar, everywhere",
     "body": "The first four are views of this page: Today is the day's "
             "plan, Plate every workstream, People your relationships, "
             "Claude where queued work runs. Rooms, Map and Sessions are "
             "their own pages — same bar on each, so you are never more "
             "than one tap from anywhere. On a phone it lives at the "
             "bottom, with the pages under More."},
    {"el": ".box.tick", "title": "Checkboxes",
     "body": "Tap one to mark a task done — it is written back to the "
             "underlying file immediately. The ✦ button beside a task "
             "queues Claude to start it: research, drafts and numbers get "
             "filed under the task for you."},
    {"el": ".forecast", "pre": {"hash": "#/today"}, "title": "Will the week fit?",
     "body": "The forecast adds up what is due soon — each task's deadline "
             "and rough ~time — against the hours you actually have, and "
             "answers honestly, before the week bites. Give a task a date "
             "and a size and the brain can plan around it."},
    {"el": ".hacts", "title": "The buttons up here, in order",
     "body": "Three actions and one panel. What happened? — ramble about "
             "your day; Claude ticks what got done, re-ranks the rest and "
             "corrects the files. Brain dump — a guided flow for emptying "
             "your whole head at once. Capture — one line straight to your "
             "inbox, filed later. Then ⋯ opens your connections (next "
             "stop) and appearance: palette, light or dark, accent and "
             "type."},
    {"el": "#apbtn", "title": "Where the outside world plugs in",
     "body": "The ⋯ panel lists the connections and whether each is on. "
             "Beeper keeps every “last spoke” date true from your real "
             "chats — names and dates only, never messages. A Telegram bot "
             "lets you text or voice-note your brain from anywhere. Your "
             "calendar shapes the morning plan. And email drafts get an "
             "approve-and-send button — sending is always your click. Each "
             "takes minutes to switch on; ask Claude for any of them."},
    {"el": '.view[data-view="plate"] details.row', "pre": {"hash": "#/plate"},
     "title": "The plate",
     "body": "One row per workstream: its status, who has the ball, the "
             "next action, any deadline. Open a row to see its tasks, its "
             "linked people, and any work Claude has prepared for it."},
    {"el": '.view[data-view="people"] [data-name]', "pre": {"hash": "#/people"},
     "title": "People",
     "body": "Each person has a closeness circle and a contact rhythm. The "
             "page flags who is owed a reply and who is past their rhythm. "
             "Last-contact dates are read from your chat list "
             "automatically — nothing to log."},
    {"el": ".habits2", "pre": {"hash": "#/today"}, "title": "Habits",
     "body": "Each habit has a weekly target. Tap ✓ on a day you did "
             "it; the page counts the week and keeps the recent history "
             "under the fold."},
    {"el": "#askbox", "pre": {"hash": "#/claude"}, "title": "The ask box",
     "body": "Type any request — a draft, research, filing, a change to "
             "this page. Paste a screenshot straight in (⌘V) and it is "
             "attached to the ask; the Capture sheet takes pastes too. "
             "It joins a queue; press Run to have Claude work through it. "
             "Results come back as ✦ folds on the item they relate to."},
    {"el": None, "pre": {"hash": "#/today"}, "title": "Three more pages",
     "body": "The Map shows everything on one screen. The Rooms give each "
             "project its own workspace. Sessions holds live Claude "
             "conversations — one per project, resumable, several at once. "
             "Tour the map next, or finish here — the ? brings any tour "
             "back."},
]

MAP_STEPS = [
    # Colour is NOT named here on purpose: the Colours button re-dresses
    # every dot (clay, berry, ocean, sunset, ink), so any sentence naming
    # "red" and "amber" is wrong the moment she changes palette. The legend
    # always shows the current colours next to their meanings — point at it
    # instead of duplicating it.
    {"el": ".barkey", "title": "The map",
     "body": "Every workstream and person as a dot on one screen, coloured "
             "by what state it is in. This row is the key — each chip shows "
             "its own colour, its meaning and how many are in it. The "
             "loudest colour is always the most urgent, whichever palette "
             "you pick with the Palette button."},
    {"el": ".modes", "pre": {"click": "#m-horizon"}, "title": "Three views",
     "body": "Horizon places work by when it needs you — leftmost is "
             "soonest. Web shows how areas, projects and people connect. "
             "Circles shows your relationships by closeness."},
    {"el": ".barkey", "title": "The key is the filter",
     "body": "Tap a chip and that colour leaves the map — its dot goes "
             "hollow so you can see what you have hidden, and Show all "
             "brings them back. A greyed chip means nothing is in that "
             "state today."},
    {"el": "#svg", "title": "Tap a dot",
     "body": "Its panel opens: tick or add tasks, snooze the workstream, "
             "queue an ask, or start a quick Claude run in that project's "
             "repo. Drag to pan, scroll to zoom, press / to search by name."},
    {"el": "#svg", "pre": {"click": "#m-web"}, "title": "The web view",
     "body": "Lines connect areas to their workstreams; dashed lines mean "
             "two things share a person. Tap an open project again and its "
             "tasks fan out — tap a task to tick it. The slider at the "
             "bottom replays the last month."},
    {"el": "#svg", "pre": {"click": "#m-circles"}, "title": "The circles view",
     "body": "Each ring is a closeness circle, each dot a person: red if "
             "you owe them a reply, terracotta if past their contact "
             "rhythm. Drag a dot onto another ring to change their circle."},
    {"el": None, "pre": {"click": "#m-horizon"}, "title": "Next: the rooms",
     "body": "One workspace page per project."},
]

ROOMS_STEPS = [
    {"el": None, "title": "The rooms",
     "body": "One room per project, grouped into wings — the areas of your "
             "life. Each room holds that project's tasks, goals, people, "
             "files and Claude's work on it."},
    {"el": ".goalstrip", "title": "Finish lines",
     "body": "The nearest goal deadlines across all projects. Tap one to "
             "open its room."},
    {"el": ".wing", "title": "A wing",
     "body": "A wing groups related rooms and counts their open work. "
             "“Audit this part” queues Claude to read the wing's "
             "rooms and folders and report what has drifted."},
    {"el": ".room", "title": "A room card",
     "body": "The dot shows the room's state; the line shows open work, "
             "when it was last touched and who has the ball. The corner "
             "dot shows how recent the repo's last commit is. Tap the card "
             "to enter."},
    {"el": ".z-next", "pre": {"click": ".room"}, "title": "The next thing",
     "body": "The project's open tasks — tick them here and the workstream "
             "file is updated. ✦ folds hold finished Claude work for "
             "this project."},
    {"el": ".z-goals", "title": "Goals",
     "body": "Milestones with dates — dates can be written in words, like "
             "“mid-September”. Tick one when reached. A goal past "
             "its date marks the whole project overdue, here, on the map "
             "and in the morning plan."},
    {"el": ".z-ask", "title": "Ask, or quick run",
     "body": "One box, three verbs. Type the thought, then pick what happens "
             "to it: Queue it asks Claude about this project, Dump it in "
             "sorts a brain dump into the brain, Quick run starts a single "
             "Claude Code run inside the repo. The room's context is "
             "attached either way — for an ongoing conversation, the "
             "Sessions page holds one per project."},
    {"el": ".z-mem", "title": "The room's memory",
     "body": "Notes saved with the room. Every Claude session in this repo "
             "reads them first, so decisions and preferences written here "
             "apply to all future runs. “(urgent)” anywhere in "
             "them raises the project's priority."},
    {"el": ".z-people", "title": "People in this",
     "body": "People linked to this project. Add one as “Name "
             "(role)” — e.g. Dad (tester) — and the chip shows how "
             "long since you last spoke. The feedback box appends dated "
             "notes that sessions read too."},
    {"el": ".z-brain", "title": "Its docs",
     "body": "The project's own markdown files. Tap one to read it here; "
             "↗ opens the folder. Read-only — the repo stays the "
             "source of truth."},
    {"el": "#search", "title": "Search",
     "body": "Searches the markdown of every tracked project folder at "
             "once."},
    {"el": None, "title": "That's everything",
     "body": "Day to day: check Today, tick as you go, capture what comes "
             "up, and let Claude handle the filing. Longer builds live on "
             "the Sessions page — one conversation per project, resumable "
             "any time."},
]


def brain_block():
    return block("brain", BRAIN_STEPS, "map.html", "Tour the map")


def map_block():
    return block("map", MAP_STEPS, "rooms.html", "Tour the rooms")


def rooms_block():
    return block("rooms", ROOMS_STEPS)

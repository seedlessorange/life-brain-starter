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
var KEY = '__KEY__', STEPS = __STEPS__, NEXT = __NEXT__, SEEN = __SEEN__;
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
  // Tell the brain, not just this browser. Skipping means "stop showing me
  // tours" — on this page, the other pages, the desk and the phone alike —
  // and only the server can answer for all of them. The ? still starts any
  // tour on demand afterwards. Chaining to the next page is the exception:
  // finishing a tour that leads somewhere is a yes, not a dismissal.
  if(!(finished && NEXT)){
    try { fetch('/api/tour', {method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({done: true})}); } catch(e){}
    SEEN = true;
  }
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
} else if(forced || (!SEEN && !lsGet('tour-done-' + KEY)
                     && lsGet('tour-pending') !== '1')){
  // tour-pending means the page's own post-dump tour is about to run —
  // never talk over it
  setTimeout(start, 900);
}
})();
"""


def _seen():
    """Has the owner already been shown around? Kept in config.json — NOT in
    the browser — because browser storage is per-address: the same brain
    reached at 127.0.0.1, at its tailnet address and on a phone is three
    separate memories, so a tour dismissed at the desk would ambush her again
    on every other one. Safari also evicts that storage after a week idle.
    One flag in the brain answers for every device and every address."""
    import os
    here = os.path.dirname(os.path.abspath(__file__))
    try:
        with open(os.path.join(os.path.dirname(here), "config.json"),
                  encoding="utf-8") as f:
            return bool((json.load(f) or {}).get("tour_done"))
    except Exception:                                    # noqa: BLE001
        return False


def block(key, steps, next_url="", next_label=""):
    """The whole tour as one self-contained <style>+<script> block."""
    nxt = json.dumps({"url": next_url, "label": next_label} if next_url
                     else None)
    js = (ENGINE
          .replace("__KEY__", key)
          .replace("__STEPS__", json.dumps(steps).replace("</", "<\\/"))
          .replace("__SEEN__", "true" if _seen() else "false")
          .replace("__NEXT__", nxt))
    return "<style>" + CSS + "</style>\n<script>" + js + "</script>\n"


# ---------------------------------------------------------------------------
# The walkthroughs themselves. One voice throughout: what a thing IS, then
# the one behaviour worth knowing. The chain is brain → map → rooms.

BRAIN_STEPS = [
    {"el": None, "title": "The brain",
     "body": "Your tasks, projects, people and habits, kept as plain markdown "
             "files. Claude maintains the files; you use this page to see "
             "what needs attention and tick things off."},
    {"el": '.view[data-view="plate"] details.row', "pre": {"hash": "#/plate"},
     "title": "The plate",
     "body": "One row per workstream: its status, who has the ball, the next "
             "action, any deadline. Open a row for its tasks, its people and "
             "any work Claude has prepared."},
    {"el": ".box.tick", "pre": {"hash": "#/today"}, "title": "Hand a task over",
     "body": "Tick a task and the file behind it is updated. The ✦ beside "
             "one gives it to Claude instead — research, drafts and numbers "
             "come back filed under that task."},
    {"el": ".forecast", "pre": {"hash": "#/today"}, "title": "Will the week fit?",
     "body": "The forecast weighs what is due against the hours you actually "
             "have, and answers before the week bites. Give a task a date and "
             "a rough size and the brain can plan around it."},
    {"el": '.view[data-view="people"] [data-name]', "pre": {"hash": "#/people"},
     "title": "People",
     "body": "Each person has a closeness circle and a contact rhythm, and "
             "the page flags who is owed a reply or has gone quiet. "
             "Last-contact dates come from your chat list — nothing to log."},
    {"el": "#askbox", "pre": {"hash": "#/claude"}, "title": "The ask box",
     "body": "Type any request — a draft, research, filing, a change to this "
             "page — and press Run. Screenshots paste straight in. Results "
             "come back as ✦ folds on whatever they relate to."},
    {"el": None, "pre": {"hash": "#/today"}, "title": "Three more pages",
     "body": "The Map shows everything on one screen, the Rooms give each "
             "project a workspace, and Sessions holds live Claude "
             "conversations. Tour the map next, or finish here — the ? in "
             "the corner brings any tour back."},
]

MAP_STEPS = [
    # Colour is NOT named here on purpose: the Palette button re-dresses every
    # dot (clay, berry, ocean, sunset, ink), so any sentence naming "red" and
    # "amber" is wrong the moment she changes palette. The legend always shows
    # the current colours next to their meanings — point at it instead.
    {"el": ".barkey", "title": "The map",
     "body": "Every workstream and person as a dot on one screen, coloured by "
             "state. This row is the key, and it filters: tap a chip to hide "
             "that colour. The loudest colour is always the most urgent, "
             "whichever palette you pick."},
    {"el": ".modes", "pre": {"click": "#m-horizon"}, "title": "Three views",
     "body": "Horizon places work by when it needs you. Web shows how areas, "
             "projects and people connect. Circles shows relationships by "
             "closeness — drag someone to another ring to change it."},
    {"el": "#svg", "title": "Tap a dot",
     "body": "Its panel opens: tick or add tasks, snooze the workstream, "
             "queue an ask, or start a Claude run in that project's repo. "
             "Drag to pan, scroll to zoom, press / to search."},
    {"el": None, "pre": {"click": "#m-horizon"}, "title": "Next: the rooms",
     "body": "One workspace page per project."},
]

ROOMS_STEPS = [
    {"el": None, "title": "The rooms",
     "body": "One room per project, grouped into wings — the areas of your "
             "life. Each room holds that project's tasks, goals, people, "
             "files and Claude's work on it."},
    {"el": ".z-next", "pre": {"click": ".room"}, "title": "Inside a room",
     "body": "The project's open tasks — tick them here and the workstream "
             "file is updated. ✦ folds hold finished Claude work for it."},
    {"el": ".z-goals", "title": "Goals",
     "body": "Milestones with dates, which can be written in words like "
             "“mid-September”. A goal past its date marks the whole "
             "project overdue — here, on the map and in the morning plan."},
    {"el": ".z-ask", "title": "Ask, or quick run",
     "body": "One box, three verbs: Queue it asks Claude about this project, "
             "Dump it in sorts a brain dump, Quick run starts a Claude Code "
             "run inside the repo. The room's context is attached either way."},
    {"el": ".z-mem", "title": "The room's memory",
     "body": "Notes saved with the room. Every Claude session in this repo "
             "reads them first, so what you write here shapes all future "
             "runs. “(urgent)” anywhere in them raises the "
             "project's priority."},
    {"el": None, "title": "That's everything",
     "body": "Day to day: check Today, tick as you go, capture what comes up, "
             "and let Claude handle the filing. Longer builds live on the "
             "Sessions page — one conversation per project, resumable any "
             "time."},
]


def brain_block():
    return block("brain", BRAIN_STEPS, "map.html", "Tour the map")


def map_block():
    return block("map", MAP_STEPS, "rooms.html", "Tour the rooms")


def rooms_block():
    return block("rooms", ROOMS_STEPS)

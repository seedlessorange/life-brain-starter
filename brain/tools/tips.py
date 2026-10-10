#!/usr/bin/env python3
"""One new thing a day: how the brain introduces itself after the first fill.

A new brain shows everything at once, and most of it is never explained (an
audit on 7 Oct 2026 found Talk, Hide the names, Files, the find box, the
bell, the Kitchen, News, Learn and Brain Pen introduced nowhere). Instead,
For you carries one "New today" line a day for the first few weeks: one
feature, one or two sentences, a Show me that spotlights it where it lives,
Got it, and a way to stop the tips altogether.

The order is by usefulness: the daily loop first, then people, then the
quieter features. A tip is skipped when it does not apply (no Telegram tip
once Telegram is paired, no Brain Pen tip off a Mac), so nobody is told
about something they already use or cannot have.

State lives in config.json under `tips`, so a tip dismissed at the desk is
gone on the phone too (the reason tray_seen and tour_done live there):
    {"on": true, "seen": ["today", "save"], "last": "2026-10-08"}
`on` is false or absent for an existing brain; the starter package ships it
on. `last` is the day of the last Got it, which keeps it to one a day.
"""
import json
import os
import sys
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
BRAIN = os.path.dirname(HERE)

# Each tip: id, title, body, where Show me goes (a page hash and an element
# to spotlight), and an optional test of whether it applies.
TIPS = [
    {"id": "today", "title": "Today's three",
     "body": "Each morning the brain picks three things you can finish today. "
             "Tick one when it is done, and the front it belongs to is ticked too.",
     "hash": "#/today", "el": ".box.tick"},
    {"id": "save", "title": "Tell the box anything",
     "body": "Press ⌘K or Ask and say it the way you would to a person. The "
             "brain works out whether to tick something off, file it or write "
             "a draft. To keep a thought word for word with no AI, pick Just "
             "save it under ⋯.",
     "hash": "", "el": "#askopen"},
    {"id": "follow", "title": "What happens next",
     "body": "Tick a task and a line opens under it. Type what follows, if "
             "anything: the next step, the answer that came back, or who has "
             "it now. The brain files it in the right place.",
     "hash": "#/today", "el": ".box.tick"},
    {"id": "evening", "title": "Close the day",
     "body": "After 17:00, each open task on Today gets Carry, which puts it at "
             "the top of tomorrow, or Drop, which retires it on the record.",
     "hash": "#/today", "el": ".box.tick"},
    {"id": "people", "title": "The people who matter",
     "body": "People reminds you when you owe someone a reply. Put someone in "
             "a circle with a rhythm, and they come up again when it has been "
             "a while.",
     "hash": "#/people", "el": "a[data-nav=\"people\"]", "part": "people"},
    {"id": "spark", "title": "Hand a task to Claude",
     "body": "The ✦ beside a task opens the box on it. Start it for me has "
             "Claude do the first step, such as finding options and prices or "
             "writing the message. Sending and paying stay with you.",
     "hash": "#/today", "el": ".tstart"},
    {"id": "foryou", "title": "For you",
     "body": "Drafts to send and the brain's questions wait here. Each answer "
             "makes tomorrow's plan a little more accurate.",
     "hash": "#/today", "el": "#foryou"},
    {"id": "find", "title": "Find anything",
     "body": "Press / and type a name, a place or a word to search everything "
             "the brain knows. Start with + to drop a note straight into the inbox.",
     "hash": "", "el": "#findq"},
    {"id": "talk", "title": "Talk to it",
     "body": "Press Talk at the top, or Space when you are not typing, and "
             "say what you need. Pause, and it answers out loud.",
     "hash": "", "el": ".vorbbtn", "mac": True},
    {"id": "hide", "title": "Hide the names",
     "body": "Before you ask about something sensitive, pick Hide the names in "
             "the box's ⋯. Names and contact details are masked on your Mac, "
             "and you see exactly what would leave. Paste the other AI's answer "
             "the same way and the names come back.",
     "hash": "", "el": "#askopen"},
    {"id": "parts", "title": "Only the parts you use",
     "body": "Under the gear, Parts of the brain switches off what you don't "
             "use, such as News or the Kitchen. Its files stay, so turning it "
             "back on brings it all back.",
     "hash": "#/hood", "el": "#parts"},
    {"id": "plate", "title": "The whole plate",
     "body": "Plate lists every front by area. Week puts the tasks on days, and "
             "Map shows everything by when it needs you.",
     "hash": "#/plate", "el": "a[data-nav=\"plate\"]"},
    {"id": "files", "title": "Everything it made",
     "body": "The box has a Files tab: the drafts, transcripts and documents the "
             "brain made, newest first, each with a preview.",
     "hash": "", "el": "#askopen"},
    {"id": "phone", "title": "The brain on your phone",
     "body": "Connect Telegram under the gear, in Connections. The plan arrives "
             "in the morning, and anything you send it lands in the inbox.",
     "hash": "#/today", "el": ".hoodlink", "unless": "telegram"},
    {"id": "calendar", "title": "Plan around your meetings",
     "body": "Switch on the calendar under the gear, in Connections. The plan "
             "then fits around what is booked; it reads titles and times only.",
     "hash": "#/today", "el": ".hoodlink", "unless": "calendar"},
    {"id": "morning", "title": "Mornings that run themselves",
     "body": "Your plan is set to be written at 7:00, but nothing has scheduled "
             "it yet. " + ("Double-click Set Up Mornings (Windows).bat in the "
             "brain's folder, once." if sys.platform.startswith("win") else
             "Run this once in Terminal, inside the brain's folder: "
             "zsh brain/tools/setup_morning.sh"),
     "hash": "", "el": None, "only": "morning_unscheduled"},
    {"id": "season", "title": "The season",
     "body": "Life, then Season, holds the fun you want this stretch of life to "
             "have. Drag an idea onto a day when you are ready.",
     "hash": "#/life", "el": "a[data-nav=\"life\"]", "part": "season"},
    {"id": "kitchen", "title": "Dinner, planned",
     "body": "Life, then Kitchen, plans dinners that share ingredients and "
             "builds the shopping list from them.",
     "hash": "#/life", "el": "a[data-nav=\"life\"]", "part": "kitchen"},
    {"id": "news", "title": "Your briefing",
     "body": "News is a morning paper from feeds you choose, with plain "
             "explanations for the topics you are learning about.",
     "hash": "#/news", "el": "a[data-nav=\"news\"]", "part": "news"},
    {"id": "learn", "title": "Learn anything",
     "body": "Ask the box to teach you a topic, or use Learn on the Life page. "
             "It checks what you know first, then goes one step at a time.",
     "hash": "#/life", "el": "a[data-nav=\"life\"]", "part": "learning"},
    {"id": "journal", "title": "A private journal",
     "body": "Write the day in your own words from Life, then Journal. The runs "
             "that happen while you sleep never read it.",
     "hash": "#/life", "el": "a[data-nav=\"life\"]", "part": "journal"},
    {"id": "bell", "title": "What the brain did",
     "body": "The bell lists everything the brain started and finished, and what "
             "it changed. Open a row to see every step.",
     "hash": "", "el": "#didbell"},
    {"id": "usage", "title": "What it costs",
     "body": "Under the gear, Usage shows how much of your Claude plan the brain "
             "has used, with the switches that keep it light.",
     "hash": "#/today", "el": ".hoodlink"},
    {"id": "night", "title": "The night shift",
     "body": "Switch it on under the gear, in Connections, and the queue and the "
             "tidy-up run at 1:00 while you sleep. It never sends anything.",
     "hash": "#/today", "el": ".hoodlink", "unless": "night"},
    {"id": "pen", "title": "Brain Pen",
     "body": "Rewrite any text box in your voice with ⌃⌥R. Build it once "
             "with zsh brain/tools/make_pen_app.sh, then allow Accessibility "
             "when it asks.",
     "hash": "", "el": None, "mac": True},
]


def _cfg():
    try:
        with open(os.path.join(BRAIN, "config.json"), encoding="utf-8") as f:
            return json.load(f) or {}
    except (OSError, ValueError):
        return {}


def _has(what, cfg):
    """Is this already in use? Then its tip has nothing to teach."""
    if what == "telegram":
        try:
            with open(os.path.join(BRAIN, ".telegram.json"), encoding="utf-8") as f:
                return bool((json.load(f) or {}).get("chat_id"))
        except (OSError, ValueError):
            return False
    if what == "calendar":
        return bool(cfg.get("calendar"))
    if what == "night":
        return bool((cfg.get("night") or {}).get("enabled"))
    return False


def morning_wanted(cfg):
    feats = cfg.get("ai_features") or {}
    if "morning" in feats:
        return bool(feats["morning"])
    return cfg.get("ai") == "full"


def morning_scheduled():
    """Whether the 7am plan is installed on this machine, the way the night
    shift's check does it. A page that promises a morning plan nothing will
    write is the gap this tip closes."""
    if sys.platform == "darwin":
        return os.path.exists(os.path.expanduser(
            "~/Library/LaunchAgents/com.lifebrain.morning.plist"))
    if os.name == "nt":
        import subprocess
        try:
            r = subprocess.run(["schtasks", "/query", "/tn", "Life brain morning"],
                               capture_output=True, timeout=10)
            return r.returncode == 0
        except Exception:                                   # noqa: BLE001
            return False
    return True                     # Linux and Docker: cron, not ours to check


def applies(tip, cfg):
    if tip.get("mac") and sys.platform != "darwin":
        return False
    if tip.get("part"):
        # A part switched off under the gear has nothing to show (parts.py).
        import parts as PARTS
        if not PARTS.on(tip["part"], cfg):
            return False
    if tip.get("unless") and _has(tip["unless"], cfg):
        return False
    if tip.get("only") == "morning_unscheduled":
        return morning_wanted(cfg) and not morning_scheduled()
    return True


def brain_filled():
    """Tips start once there is something to point at: an empty brain is
    for the welcome card, not for a lesson about the plate."""
    try:
        sys.path.insert(0, HERE)
        import model as M
        return bool(M.load()) or bool(M.load_people())
    except Exception:                                       # noqa: BLE001
        return False


def current(cfg=None, today=None):
    """Today's tip, or None: tips off, nothing to point at yet, today's
    already seen, or every tip seen."""
    cfg = _cfg() if cfg is None else cfg
    t = cfg.get("tips") or {}
    if not t.get("on"):
        return None
    today = (today or date.today()).isoformat()
    if t.get("last") == today:
        return None
    seen = set(t.get("seen") or [])
    for tip in TIPS:
        if tip["id"] not in seen and applies(tip, cfg):
            if not brain_filled():
                return None
            # Fixed wording: it names the agent the runs use.
            import agents as AG
            return dict(tip, title=AG.say(tip["title"]),
                        body=AG.say(tip["body"]))
    return None


def remaining(cfg=None):
    cfg = _cfg() if cfg is None else cfg
    seen = set((cfg.get("tips") or {}).get("seen") or [])
    return sum(1 for tip in TIPS if tip["id"] not in seen and applies(tip, cfg))


def tray_body(tip, esc):
    """The line's inside: the sentence and its three buttons. `esc` is the
    page's HTML escaper, passed in so this module needs nothing from build."""
    show = ""
    if tip.get("el") or tip.get("hash"):
        show = (f'<button class="mini" data-tipshow="{esc(tip["id"])}"'
                f' data-tiphash="{esc(tip.get("hash") or "")}"'
                f' data-tipel="{esc(tip.get("el") or "")}"'
                f' data-tiptitle="{esc(tip["title"])}"'
                f' data-tipbody="{esc(tip["body"])}">Show me</button>')
    return (f'<p>{esc(tip["body"])}</p><div class="tipbtns needs-server">{show}'
            f'<button class="mini" data-tipseen="{esc(tip["id"])}">Got it</button>'
            '<button class="ghostbtn tipoff" data-tipoff="1">Stop these tips</button>'
            '</div>')


# The page side: Show me spotlights the feature where it lives (going to
# its page first if needed, through sessionStorage so it survives the hash
# change), Got it and Stop post to /api/tips. The spotlight borrows the
# tour's look (.btour-hole, .btour-card), which every page already carries.
SCRIPT = r"""
(function(){
  function post(body){
    return fetch('/api/tips', {method: 'POST', headers: {'Content-Type': 'application/json'},
                               body: JSON.stringify(body)})
      .then(function(r){ return r.json(); });
  }
  function spot(d){
    // the first visible match: a phone shows the places in a bottom bar
    var el = d.el ? [].filter.call(document.querySelectorAll(d.el),
      function(x){ return x.offsetParent !== null; })[0] || null : null;
    var hole = document.createElement('div'); hole.className = 'btour-hole';
    var card = document.createElement('div'); card.className = 'btour-card';
    card.setAttribute('role', 'dialog');
    card.innerHTML = '<h3></h3><p></p><div class="btour-row"><span class="tn">New today</span>'
      + '<button class="tgo">Got it</button></div>';
    card.querySelector('h3').textContent = d.title;
    card.querySelector('p').textContent = d.body;
    document.body.appendChild(hole); document.body.appendChild(card);
    function close(){ hole.remove(); card.remove(); removeEventListener('keydown', key); }
    function key(e){ if(e.key === 'Escape') close(); }
    addEventListener('keydown', key);
    hole.onclick = close;
    card.querySelector('.tgo').onclick = close;
    if(el){
      // instant: the page scrolls smoothly, and the hole is measured once
      el.scrollIntoView({block: 'center', behavior: 'instant'});
      setTimeout(function(){
        var r = el.getBoundingClientRect(), pad = 6;
        hole.style.left = (r.left - pad) + 'px'; hole.style.top = (r.top - pad) + 'px';
        hole.style.width = (r.width + pad * 2) + 'px'; hole.style.height = (r.height + pad * 2) + 'px';
        var ch = card.offsetHeight || 160, cw = card.offsetWidth || 340;
        var below = r.bottom + 14 + ch < innerHeight;
        card.style.top = (below ? r.bottom + 14 : Math.max(16, r.top - 14 - ch)) + 'px';
        card.style.left = Math.max(16, Math.min(r.left, innerWidth - cw - 16)) + 'px';
      }, 60);
    } else {
      hole.classList.add('bare');
      hole.style.left = '50%'; hole.style.top = '50%'; hole.style.width = '0'; hole.style.height = '0';
      card.style.left = 'calc(50% - 170px)'; card.style.top = '30vh';
    }
  }
  document.addEventListener('click', function(e){
    var b = e.target.closest('[data-tipshow]');
    if(b){
      e.preventDefault(); e.stopPropagation();
      var d = {el: b.dataset.tipel, title: b.dataset.tiptitle, body: b.dataset.tipbody};
      if(b.dataset.tiphash && location.hash !== b.dataset.tiphash){
        location.hash = b.dataset.tiphash;
        setTimeout(function(){ spot(d); }, 450);
      } else spot(d);
      return;
    }
    var s = e.target.closest('[data-tipseen]');
    if(s){
      e.preventDefault(); s.disabled = true;
      post({seen: s.dataset.tipseen}).then(function(){
        var line = s.closest('.tray'); if(line) line.remove();
      }).catch(function(){ s.disabled = false; });
      return;
    }
    var o = e.target.closest('[data-tipoff], [data-tipon]');
    if(o){
      e.preventDefault(); o.disabled = true;
      post({on: !!o.dataset.tipon}).then(function(){
        var line = o.closest('.tray');
        if(line) line.remove(); else location.reload();
      }).catch(function(){ o.disabled = false; });
    }
  });
})();
"""


if __name__ == "__main__":
    c = _cfg()
    tip = current(c)
    print("tips:", "on" if (c.get("tips") or {}).get("on") else "off",
          "| today:", tip["id"] if tip else "none", "| left:", remaining(c))

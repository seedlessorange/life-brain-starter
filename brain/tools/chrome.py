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

# Five places and one box (28 Sep, "The brain, redrawn" — decisions.md).
# Each place answers one question: Today, what do I do now; the Plate, what
# is on my plate this week; School, what this term needs (a tab only while
# the season is about school); People, who needs me; Life, how am I living.
# News joined them on 8 Oct, her ask: what is going on out there.
# Talking to Claude is not a place: it is the box, on every page. The
# machinery — connections, jobs, spend, the look — sits behind the gear.
#
# id, label, href from a page that is NOT index.html
PLACES = [
    ("today", "Today", "index.html#/today"),
    ("plate", "Plate", "index.html#/plate"),
    ("school", "School", "index.html#/school"),
    ("jobs", "Jobs", "index.html#/jobs"),
    ("people", "People", "index.html#/people"),
    ("life", "Life", "index.html#/life"),
    # News was a part of Life until 8 Oct, when she asked for it in the bar:
    # two clicks down, the morning paper went unread.
    ("news", "News", "index.html#/news"),
]

# The views inside index.html rather than their own file.
IN_APP = {"today", "school", "jobs", "plate", "week", "people", "life", "season",
          "news", "hood"}

# Pages and views that belong to a place without being one: they light
# their place in the bar. Map and the rooms are the Plate drawn other ways;
# Circles is People on rings; the kitchen, routines and season are parts
# of Life; usage and the conversations list live under the hood.
FAMILY = {"week": "plate", "map": "plate", "rooms": "plate",
          "circles": "people",
          "season": "life", "cook": "life", "routine": "life",
          "usage": "hood", "sessions": "hood", "hood": "hood",
          "claude": "hood"}


def place_of(view):
    """The place a view or page lights in the bar."""
    return FAMILY.get(view, view)


def school_on():
    """School is the season slot: a tab while config's `now` says the season
    is about school, gone the day the term ends. Never let a config problem
    take the nav down with it."""
    try:
        import model as M
        return M.school_tab_on()
    except Exception:
        return True


def jobs_on():
    """Jobs is a season slot too: a tab while config `jobs.on` says a job
    hunt is live (jobs.py). Off unless switched on."""
    try:
        import jobs as J
        return J.is_on()
    except Exception:
        return False


def hidden_places():
    """The places that leave the bar: School and Jobs out of season, and a
    place whose parts are switched off under the gear (parts.py). Life goes
    only when every one of its parts is off."""
    out = set()
    if not school_on():
        out.add("school")
    if not jobs_on():
        out.add("jobs")
    try:
        import parts as P
        cfg = P.load()
        for pid in ("people", "news"):
            if not P.on(pid, cfg):
                out.add(pid)
        if not P.life_on(cfg):
            out.add("life")
    except Exception:
        pass
    return out


def nav_html(current="", in_app=False, cls="appnav"):
    """The navigation row.

    `current` is the page or view id; it lights its place (see FAMILY).
    `in_app` is True only for index.html, where the places are router views
    and must stay hash-only so the SPA switches without a page load — a full
    reload there would lose scroll, open panels and any half-typed capture.
    """
    lit = place_of(current)
    hidden = hidden_places()
    links = []
    for pid, label, href in PLACES:
        if pid in hidden:
            continue
        if in_app and pid in IN_APP:
            href = "#/" + pid
        on = ' class="on" aria-current="page"' if pid == lit else ""
        links.append(f'<a href="{href}" data-nav="{pid}"{on}>{label}</a>')
    return f'<nav class="{cls}">' + "".join(links) + "</nav>"


def hood_link(current="", in_app=False):
    """The gear: the way under the hood, the same spot on every page."""
    on = " on" if place_of(current) == "hood" else ""
    href = "#/hood" if in_app else "index.html#/hood"
    return (f'<a class="hoodlink{on}" href="{href}" data-nav="hood"'
            ' title="Under the hood: connections, jobs, spending and the look"'
            ' aria-label="Under the hood">'
            '<svg viewBox="0 0 24 24" width="17" height="17" fill="none"'
            ' stroke="currentColor" stroke-width="1.9" stroke-linecap="round"'
            ' stroke-linejoin="round" aria-hidden="true">'
            '<circle cx="12" cy="12" r="3"/>'
            '<path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1'
            'a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1'
            'a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8'
            'l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1'
            'A1.7 1.7 0 0 0 4.6 9a1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8'
            'l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1'
            'a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8'
            'l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4'
            'h-.1a1.7 1.7 0 0 0-1.5 1z"/></svg></a>')


# Styling for pages that do not already have a nav of their own (rooms, map,
# the desk). index.html keeps its own .topnav rules; this is deliberately
# scoped to .appnav so including it twice is harmless.
NAV_CSS = """
.appnav{display:flex;gap:2px;align-items:center;flex-wrap:wrap;min-width:0}
.appnav a{color:var(--dim);text-decoration:none;font-size:var(--t-sm,14px);
  font-weight:500;padding:6px 10px;border-radius:8px;white-space:nowrap}
.appnav a:hover{color:var(--ink);background:var(--surface)}
.appnav a.on{color:var(--ink);background:var(--sunken,var(--surface))}
.navmore{position:relative}
.navmore>summary{list-style:none;cursor:pointer;color:var(--dim);
  font-size:var(--t-sm,14px);font-weight:500;padding:6px 10px;border-radius:8px;
  white-space:nowrap}
.navmore>summary::-webkit-details-marker{display:none}
.navmore>summary::after{content:" \\25BE";font-size:.85em}
.navmore>summary:hover,.navmore[open]>summary{color:var(--ink)}
.navmore:has(a.on)>summary{color:var(--ink);font-weight:600}
.navmenu{position:absolute;top:calc(100% + 8px);left:0;z-index:60;min-width:170px;
  display:flex;flex-direction:column;gap:2px;padding:6px;
  background:var(--surface,#fff);border:1px solid var(--line);border-radius:12px;
  box-shadow:0 12px 36px rgba(0,0,0,.14)}
.navmenu a{display:block}
/* The gear: under the hood. An icon, not a word — it is the rare trip. */
.hoodlink{display:inline-flex;align-items:center;justify-content:center;
  width:32px;height:32px;flex:none;border-radius:999px;color:var(--dim);
  text-decoration:none;border:1px solid transparent}
.hoodlink:hover{color:var(--ink);background:var(--surface)}
.hoodlink.on{color:var(--ink);background:var(--sunken,var(--surface));
  border-color:var(--line)}
@media (max-width:720px){
  .appnav{overflow-x:auto;-webkit-overflow-scrolling:touch;flex-wrap:nowrap}
}
"""


# Under the hood: the settings view itself (connections, jobs, the look, the
# brain's memory), what Claude spends, and every conversation at full size.
# One sub-row at the top of all three moves between them. It keeps the
# .clsub markup the Claude tab used, because build.py re-stamps it into the
# hand-written sessions.html by that pattern.
HOOD_PAGES = [
    ("hood", "Settings", "index.html#/hood"),
    ("usage", "Usage", "usage.html"),
    ("privacy", "Privacy", "privacy.html"),
    ("sessions", "Conversations", "sessions.html"),
]
CLAUDE_PAGES = HOOD_PAGES       # the old name, for anything still calling it

# Layout only: how every switch looks, per style, is switches.py's. Every
# switch row sits 16px under the header's rule, on every page (8 Oct: they
# ranged from touching it to 42px).
SUBNAV_CSS = """
.clsub{display:inline-flex;align-items:center;margin:16px 0;
  position:relative;z-index:2}
.clsub a{text-decoration:none;white-space:nowrap}
/* in the sub-row under the bar, the row gives the 16px */
.apsub .clsub{margin:0}
"""


# Each switch entry: id, label, href from another page, and the hash to use
# inside index.html (None when the view is a page of its own).
PLATE_PAGES = [
    ("list", "List", "index.html#/plate", "#/plate"),
    ("week", "Week", "index.html#/week", "#/week"),
    ("map", "Map", "map.html", None),
]
# The rooms are not a way of looking at the plate any more: a room is one
# front's own page, opened from its row. The floor plan's grouping by wing
# retired with the wings (28 Sep); the list, grouped by area, is the plan.

PLATEVIEWS_CSS = """
.pvnav{display:inline-flex;align-items:center;flex:none}
.pvnav a{text-decoration:none;white-space:nowrap}
.pvrow{margin:16px 0}
/* phone (28 Sep): at 360 wide Life's five ran 30px past the edge and the
   whole page scrolled sideways, so the switch scrolls inside itself
   (switches.py) rather than the page. */
"""


# People's views: who needs her (the page opens here), everyone (the
# shelves, search and sorter: a directory), and Circles — everyone on rings
# by how close she keeps them, drawn by the map page (28 Sep, her call).
# Needs you and Everyone are one view with a switch (page.js, data-ppl),
# so the people search and the jumps to a person keep their one section.
PEOPLE_PAGES = [
    ("needs", "Needs you", "index.html#/people", "#/people"),
    ("everyone", "Everyone", "index.html#/everyone", "#/everyone"),
    ("circles", "Circles", "map.html#circles", None),
]

# Life: how she lives, as opposed to what she owes. The overview carries
# today's slice of each part; the rest are the parts themselves.
LIFE_PAGES = [
    ("life", "Overview", "index.html#/life", "#/life"),
    ("season", "Season", "index.html#/season", "#/season"),
    ("cook", "Kitchen", "cook.html", None),
    ("routine", "Routine", "routines.html", None),
]


def _views(pages, current, in_app, label, style=True):
    out = []
    for pid, name, href, app_hash in pages:
        if in_app and app_hash:
            href = app_hash
        on = ' class="on" aria-current="page"' if pid == current else ""
        out.append(f'<a href="{href}" data-view="{pid}"{on}>{name}</a>')
    return (("<style>" + PLATEVIEWS_CSS + "</style>" if style else "")
            + f'<nav class="pvnav" aria-label="{label}">'
            + "".join(out) + "</nav>")


def plate_views(current, in_app=False, style=True):
    """The Plate's three ways of looking at the same workstreams — the
    ranked list, the week, the map — as one switch in the same spot on
    each. `in_app` is True on index.html, where the in-app views stay
    hash-only so the SPA switches without a reload. Carries its own style
    tag."""
    return _views(PLATE_PAGES, current, in_app, "Ways to see your plate", style)


def people_views(current, in_app=False, style=True):
    """People's Needs you · Everyone · Circles switch, the twin of
    plate_views."""
    return _views(PEOPLE_PAGES, current, in_app, "Ways to see your people",
                  style)


# Life's switch entries, by the part under the gear that each one shows.
LIFE_PART = {"season": "season", "cook": "kitchen", "routine": "routines"}


def life_views(current, in_app=False, style=True):
    """Life's switch: the overview and its parts, less the parts switched
    off under the gear (parts.py)."""
    try:
        import parts as P
        cfg = P.load()
        pages = [pg for pg in LIFE_PAGES
                 if P.on(LIFE_PART.get(pg[0], ""), cfg)]
    except Exception:
        pages = LIFE_PAGES
    return _views(pages, current, in_app, "The parts of your life", style)


def claude_subnav(current, in_app=False):
    """The sub-row under the hood, shared by the settings view, usage.html
    and sessions.html. Carries its own style tag so every page that drops it
    in is done. `in_app` is True on index.html, where the settings link must
    stay hash-only so the SPA switches without a reload."""
    out = []
    for pid, label, href in HOOD_PAGES:
        if in_app and pid == "hood":
            href = "#/hood"
        on = ' class="on" aria-current="page"' if pid == current else ""
        out.append(f'<a href="{href}"{on}>{label}</a>')
    return ("<style>" + SUBNAV_CSS + "</style>"
            + '<nav class="clsub" aria-label="Under the hood">'
            + "".join(out) + "</nav>")


hood_subnav = claude_subnav


def _esc(s):
    import html as _html
    return _html.escape(str(s or ""), quote=True)


def _built_hm():
    """The page's build time, for the pill before its first check lands."""
    from datetime import datetime
    return datetime.now().strftime("%H:%M")


def header_html(current, owner="", right_html="", in_app=False, sub_html="",
                legend_html=""):
    """The whole top bar, the same markup on every page.

    The nav was shared but nothing around it was, so each page still opened
    looking like a different app. By 28 Sep there were still three bars:
    index.html wrote its own (the date pill, the find box), the kitchen,
    routines and usage had a thin strip with neither and a grey box for the
    lit place, and the map and the conversations packed their own controls
    into the strip until it wrapped into three rows on a phone. So this one
    function writes the bar for every page, index.html included, with
    index's class names — every skin already styles those, so a skin that
    dresses one page's bar now dresses them all.

    Who you are, where you can go, find, talk, the box, the gear: nothing a page
    does goes in the bar. A page's own controls — `sub_html`, or the older
    `right_html` — sit in a row UNDER it. `legend_html` is the one
    exception: the skins that draw a colour key in the bar (index only).
    The phone's tab bar comes with it, because below 760px it IS the nav.
    """
    home = "#/today" if in_app else "index.html#/today"
    # On Today the name also scrolls back to the top.
    up = (' onclick="if(location.hash===\'#/today\')window.scrollTo('
          '{top:0,behavior:\'smooth\'})"' if in_app else "")
    brand = ('<div class="brand"><a class="brandhome" href="%s" title="Home"%s>'
             '<img class="logo" src="logo-96.png?v=5" alt="" width="24" height="24">'
             '<span class="wordmark">%s <b>brain</b></span></a>'
             % (home, up, _esc(owner or "My")))
    # The pill: when the brain last synced, and the button that syncs it now.
    # On index.html the page's own script drives it; elsewhere a small one
    # in ask_block does (data-lite).
    from datetime import datetime
    stamp = datetime.now().strftime("%a %d %b").upper()
    brand += ('<button class="syncstate needs-server" id="syncstate"'
              + ("" if in_app else ' data-lite="1"')
              + ' title="Syncs itself on a timer. Click to sync now.">'
              '<i></i><span class="skinx skinx-stamp">' + stamp + ' &middot;</span>'
              '<span id="synctext">updated ' + _built_hm() + '</span></button></div>')
    find = ('<div class="findwrap needs-server">'
            '<span class="findicon" aria-hidden="true"><svg viewBox="0 0 24 24" '
            'width="15" height="15" fill="none" stroke="currentColor" '
            'stroke-width="2.2" stroke-linecap="round"><circle cx="10.5" '
            'cy="10.5" r="6.5"/><path d="M15.5 15.5 21 21"/></svg></span>'
            '<input id="findq" type="search" placeholder="Find anything, or + to jot"'
            ' autocomplete="off" aria-label="Find anything in your brain"'
            ' spellcheck="false">'
            '<div id="findout" class="findout" hidden></div></div>')
    # A page that is a part of Life (the kitchen, the routines) carries
    # Life's own switch under the bar, the way the Plate's pages carry theirs.
    sub = ""
    if place_of(current) == "life" and current != "life":
        sub += life_views(current, in_app=in_app)
    sub += (right_html or "") + (sub_html or "")
    return ('<header class="top">' + brand
            + nav_html(current, in_app=in_app, cls="topnav appnav")
            + find
            + '<div class="hacts">' + (legend_html or "")
            # Talk, back in the bar on every style (9 Oct, her ask: "chatting
            # back and forth is very important and it seems hidden"). From
            # 7 Oct it was only the box's mic, or Orbit's orb on Today.
            + orb_button_html() + ask_button_html() + activity_button_html()
            + hood_link(current, in_app=in_app) + "</div></header>"
            + ('<div class="apsub">' + sub + "</div>" if sub else "")
            + tabbar_html(current, in_app=in_app))


# The phone's nav: the five places along the bottom, in the thumb's reach.
# It was index.html's alone, so on every other page a phone got the links
# squeezed into the top bar instead — Life cut off on the kitchen (28 Sep).
_TAB_ICONS = {
    "today": '<circle cx="12" cy="12" r="4"/><path d="M12 3v2M12 19v2M3 12h2M19 '
             '12h2M5.6 5.6l1.4 1.4M17 17l1.4 1.4M18.4 5.6L17 7M7 17l-1.4 1.4"/>',
    "plate": '<circle cx="12" cy="12" r="8.5"/><circle cx="12" cy="12" r="5"/>',
    "school": '<path d="M2.5 9L12 4.5 21.5 9 12 13.5z"/><path d="M6.5 11v4.5c0 '
              '1.4 2.5 2.8 5.5 2.8s5.5-1.4 5.5-2.8V11"/>',
    "jobs": '<rect x="3" y="7" width="18" height="13" rx="2"/><path d="M9 7V5.5A1.5 '
            '1.5 0 0 1 10.5 4h3A1.5 1.5 0 0 1 15 5.5V7M3 13h18"/>',
    "people": '<circle cx="9" cy="8.5" r="3.2"/><path d="M3.5 19c.8-3.2 3-5 5.5-5s4.7 '
              '1.8 5.5 5"/><circle cx="16.8" cy="9.5" r="2.4"/><path d="M15.6 '
              '14.2c2.3.2 4.2 1.8 4.9 4.8"/>',
    "life": '<path d="M5 19c.5-8.5 6-13.5 14.5-14-.4 8.6-5.6 14-14.5 14z"/>'
            '<path d="M5 19l7.5-7.5"/>',
    "news": '<path d="M4 5.5h12.5v13A1.5 1.5 0 0 0 18 20H5.5A1.5 1.5 0 0 1 4 18.5z"/>'
            '<path d="M16.5 9H20v9.5a1.5 1.5 0 0 1-3 0M7 9h6.5M7 12.5h6.5M7 16h4"/>',
}


def tabbar_html(current="", in_app=False):
    """`in_app` is index.html, whose main already leaves room for the bar;
    elsewhere the bar asks the page for that room itself (data-pad)."""
    lit = place_of(current)
    hidden = hidden_places()
    out = []
    for pid, label, href in PLACES:
        if pid in hidden:
            continue
        if in_app and pid in IN_APP:
            href = "#/" + pid
        on = ' class="on" aria-current="page"' if pid == lit else ""
        out.append('<a href="%s" data-nav="%s"%s><svg viewBox="0 0 24 24" '
                   'width="21" height="21" fill="none" stroke-width="1.8" '
                   'stroke-linecap="round" stroke-linejoin="round" '
                   'aria-hidden="true">%s</svg>%s</a>'
                   % (href, pid, on, _TAB_ICONS.get(pid, ""), label))
    return ('<nav class="tabbar" aria-label="Sections"'
            + ("" if in_app else " data-pad") + ">" + "".join(out) + "</nav>")


# The bar, its sub-row and the phone's tab bar — the one stylesheet for
# them, on every page (index.html too, after page.css). The class names are
# index's own because the five skins style those; a rule here must stay at
# class-level specificity so the skins' [data-style] rules keep winning.
HEADER_CSS = """
/* the pages under it set their own type and box model; the bar sets its own */
.top,.top *,.tabbar,.tabbar *{box-sizing:border-box}
.top{position:sticky;top:0;z-index:20;display:flex;gap:var(--s4);align-items:center;
  padding:var(--s3) var(--s5);font:400 var(--t-base)/1.55 var(--sans);
  background:color-mix(in oklch,var(--paper) 86%,transparent);
  -webkit-backdrop-filter:blur(12px);backdrop-filter:blur(12px);
  border-bottom:1px solid var(--line)}
.brand{font:600 1.125rem/1 var(--serif);letter-spacing:-.01em;white-space:nowrap;
  display:inline-flex;align-items:center;gap:9px;color:var(--ink)}
.brand .logo{flex:none}
/* the name is the way home, from any page */
.brandhome{display:inline-flex;align-items:center;gap:9px;min-width:0;color:inherit;
  text-decoration:none}
.brand b{font-weight:800}
.syncstate{display:inline-flex;align-items:center;gap:6px;margin-left:var(--s2);
  font:400 var(--t-xs)/1 var(--sans);color:var(--faint);background:none;border:0;
  padding:6px;border-radius:var(--r-sm);cursor:pointer;white-space:nowrap}
.syncstate:hover{color:var(--dim);background:var(--surface)}
.syncstate i{width:7px;height:7px;border-radius:50%;background:var(--green);
  animation:appulse 3s infinite}
.syncstate.stale i{background:var(--faint);animation:none}
.syncstate.working i{background:var(--terra);animation:appulse 1.1s infinite}
.syncstate.working{color:var(--terra)}
@keyframes appulse{0%{box-shadow:0 0 0 0 color-mix(in oklch,var(--green) 40%,transparent)}
  70%{box-shadow:0 0 0 7px transparent}100%{box-shadow:0 0 0 0 transparent}}
@media(prefers-reduced-motion:reduce){.syncstate i{animation:none}}
/* a skin shows its own extras (the date stamp); :where keeps this below it */
:where(.top) .skinx{display:none}
.topnav{display:flex;gap:2px;align-items:center;margin-left:auto;flex-wrap:nowrap;
  min-width:0}
.topnav a{color:var(--dim);text-decoration:none;font-size:var(--t-sm);font-weight:500;
  padding:6px 10px;border-radius:var(--r-sm);white-space:nowrap}
.topnav a:hover{color:var(--ink);background:var(--surface)}
.topnav a.on{color:var(--ink);background:var(--sunken)}
.hacts{display:flex;gap:var(--s2);align-items:center;flex:none}
/* Find anything: the graph, from the bar. A magnifier until it is used —
   at every width, so a phone's bar stays one row (28 Sep); "/" still
   focuses it from anywhere. */
.findwrap{position:relative;flex:0 0 36px;min-width:36px;height:36px}
/* the icon is its own element: the skin's input rule sets `background`
   with more specificity than anything here, and wiped a background icon */
.findicon{display:block;position:absolute;right:10.5px;top:50%;height:15px;
  transform:translateY(-50%);color:var(--dim);pointer-events:none;z-index:31}
/* Closed, no padding: 12px + 32px of it made the "36px" button 48px
   wide, with the magnifier sitting right of centre (28 Sep). */
.findwrap input{position:absolute;top:0;right:0;box-sizing:border-box;
  width:36px;height:36px;padding:0;border-radius:99px;font:inherit;font-size:13px;
  border:1px solid var(--line);background:var(--card);color:transparent;
  outline:none;cursor:pointer;transition:width .16s ease}
.findwrap input::placeholder{color:transparent}
.findwrap input:focus,.findwrap input:not(:placeholder-shown){width:300px;
  padding:6px 32px 6px 12px;color:var(--ink);cursor:text;z-index:30;
  border-color:var(--accent)}
.findwrap input:focus::placeholder{color:var(--faint)}
.findout{position:absolute;top:calc(100% + 6px);right:0;width:min(460px,88vw);
  max-height:60vh;overflow:auto;background:var(--card);border:1px solid var(--line);
  border-radius:10px;box-shadow:0 10px 40px rgba(0,0,0,.16);padding:6px;z-index:300}
.findout .fr{display:block;padding:7px 9px;border-radius:7px;font-size:13px;
  line-height:1.45;color:var(--ink);text-decoration:none}
.findout .fr:hover,.findout .fr.fon{background:var(--wash)}
.findout .fr b{font-weight:600}
.findout .fr i{display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;
  overflow:hidden;font-style:normal;font-size:11.5px;color:var(--dim);margin-top:1px}
.findout mark{background:color-mix(in srgb,var(--accent) 22%,transparent);
  color:inherit;border-radius:2px}
.findout .fhead{padding:6px 9px 3px;font-size:11px;text-transform:uppercase;
  letter-spacing:.05em;color:var(--dim)}
.findout .fhead:not(:first-child){margin-top:4px;padding-top:9px;
  border-top:1px solid var(--line)}
.findout .fmore>summary{padding:4px 9px 6px;font-size:12px;color:var(--dim);
  cursor:pointer;list-style:none}
.findout .fmore>summary::-webkit-details-marker{display:none}
.findout .fmore>summary:hover{color:var(--ink)}
.findout .fmore[open]>summary{display:none}
.findout .fnone{padding:10px;font-size:13px;color:var(--dim)}
.findout .fstyle{display:flex;align-items:center;gap:6px;flex-wrap:wrap}
.findout .fstyle b{margin-right:auto}
.findout .fstyle button{border:1px solid var(--line);border-radius:999px;
  padding:3px 10px;font-size:11.5px;cursor:pointer;background:var(--card);
  color:var(--ink)}
/* A phone has no 300px beside the magnifier: open, the field lays over the
   bar's whole row, and the results hang under it at full width. */
@media(max-width:820px){
  .findwrap:focus-within{position:static}
  .findwrap:focus-within .findicon{display:none}
  /* 44px: the bar's tallest button (a look's ✦ Ask) peeked out round a
     40px field (28 Sep) */
  .findwrap input:focus{position:absolute;top:50%;left:var(--s4);right:var(--s4);
    width:auto;height:44px;transform:translateY(-50%);padding:6px 12px}
  /* put down, it folds back to the magnifier and keeps what was typed */
  .findwrap input:not(:focus):not(:placeholder-shown){width:36px;padding:0;
    color:transparent;-webkit-text-fill-color:transparent;border-color:var(--accent)}
  .findwrap:focus-within .findout{left:var(--s4);right:var(--s4);width:auto;
    top:calc(100% - 4px)}
}
/* The bar's two small ones, the logo home and the sync dot, get a
   fingertip's tap area on a touch screen; nothing moves (28 Sep). */
@media(pointer:coarse){
  .brandhome,.syncstate{position:relative}
  .brandhome::after,.syncstate::after{content:"";position:absolute;inset:-10px -4px}
}
/* An iPhone zooms the whole page into any field typed smaller than 16px
   the moment it is tapped, and leaves it zoomed. Every field was 11-15px
   (8 Oct phone check), so on a touch screen they all type at 16px. */
@media(pointer:coarse){
  input:not([type=checkbox]):not([type=radio]):not([type=range]):not([type=color]):not([type=file]):not([type=button]):not([type=submit]),
  textarea,select{font-size:16px!important}
}
/* What this page does, in a row under the bar: the Life switch, the map's
   views and tools, the conversations' own switch. */
/* On main's own measure, so the Life switch sits on the same left edge on
   the Kitchen and Routine as on Overview and Season (8 Oct). */
.apsub{display:flex;flex-wrap:wrap;gap:10px;align-items:center;
  padding:16px var(--s5) 0;box-sizing:border-box;max-width:1420px;
  margin:0 auto}
.apsub:empty{display:none}
.tabbar{display:none}
/* Around a laptop's 1140px the bar ran 18px past the window: the sync
   pill carried the date AND "synced 10 min ago", the date already being in
   the hero. The date goes first when room runs out (28 Sep). */
@media (max-width:1280px){.syncstate .skinx-stamp{display:none}}
/* Narrower still, the words go and the dot stays — its colour is the
   state, and hovering it still says when. */
@media (max-width:1100px){.syncstate #synctext{display:none}}
/* Then the name: the logo beside it is the same link home. 1100px since
   9 Oct, when Talk came back: a long name ("the owner's brain") pushed
   News under the find button between 980 and 1100px. */
@media (max-width:1100px){.brand .wordmark{display:none}}
/* Last, the tabs close up: with School, Jobs and News on and Talk in the
   bar, a tablet's 768 to 860px pushed News under the find button (9 Oct).
   html:root outranks each style's own tab padding, here and nowhere else. */
@media (min-width:761px) and (max-width:860px){
  html:root .top .topnav a{padding-left:7px;padding-right:7px}
  html:root .top .topnav{gap:0}}
@media(max-width:760px){
  /* the phone's nav is the tab bar along the bottom */
  .topnav{display:none}
  .top{gap:var(--s2);padding:var(--s3) var(--s4)}
  .brand{flex:0 1 auto;min-width:0}
  .syncstate{margin-left:0;flex:none;padding:6px}
  .hacts{margin-left:auto}
  .apsub{padding:10px var(--s4) 0;flex-wrap:nowrap;overflow-x:auto;
    scrollbar-width:none}
  .apsub::-webkit-scrollbar{display:none}
  .apsub>*{flex:none}
  /* A conversation waiting on her is the one thing in the row she must not
     have to swipe to find: it takes a line of its own (28 Sep). */
  .apsub:has(>#needspill){flex-wrap:wrap}
  .apsub>#needspill{order:2}
  .tabbar{position:fixed;left:0;right:0;bottom:0;z-index:40;display:flex;
    background:color-mix(in oklch,var(--surface) 92%,transparent);
    -webkit-backdrop-filter:blur(14px);backdrop-filter:blur(14px);
    border-top:1px solid var(--line);
    padding:6px var(--s2) calc(6px + env(safe-area-inset-bottom))}
  .tabbar a{flex:1;display:flex;flex-direction:column;align-items:center;gap:3px;
    padding:6px 2px;text-decoration:none;color:var(--faint);border-radius:var(--r-btn);
    font:500 10px/1 var(--sans)}
  .tabbar a svg{stroke:currentColor}
  .tabbar a.on{color:var(--green)}
  /* the last of the page scrolls clear of the tab bar and the corner column */
  body:has(.tabbar[data-pad]){padding-bottom:calc(120px + env(safe-area-inset-bottom))}
}
"""


def orb_button_html():
    import orb as ORB
    return ORB.button_html()


def activity_button_html():
    import activity as ACT
    return ACT.button_html()


def ask_button_html():
    return ('<button class="askopen" id="askopen" '
            # A real dash. Escaped, this printed the six characters — in
            # the tooltip — HTML is not JavaScript.
            'title="Tell the brain anything (⌘K)">'
            '✦ Ask</button>')


# ---------------------------------------------------------------------------
# The box: talking to the brain, from anywhere
#
# Every page could START Claude working — a queue item here, a quick run
# there, a conversation on Sessions — but only Sessions could show you what
# came back. So "just ask it something" meant navigating first and choosing a
# project second, for a question that had nothing to do with a project.
#
# Since 28 Sep this panel is the one way to talk to the brain (decisions.md,
# "The brain, redrawn"). What used to be a dozen doors — the capture sheet,
# What happened?, Talk it through, a room's Ask and Quick run, the Claude
# tab's nine modes — is this box, opened three ways:
#
#   * plain, from the header, the ✦ corner button or Cmd/Ctrl-K: a
#     conversation in the brain's own folder;
#   * scoped, from a task, a person, a workstream or a project room
#     (window.brainBox.open({scope: ...})): the conversation opens already
#     holding that thing's context, or runs in that project's own folder;
#   * with an intent, from ⋯: just save it, tick off what happened, draft,
#     look into it first, tear it apart, the frameworks, keep it as the
#     journal, or queue it for later. Most intents are a conversation with an
#     instruction in front; three never start one (save, journal, later).
#
# Above the thread: For you (everything the brain is waiting on her for, the
# same list Today shows) and Working on (what Claude is running). Under each
# answer: a receipt saying which of her files the turn changed, read from the
# turn's own steps rather than from anything the model says about itself.
#
# It is deliberately the SAME record the Sessions page shows: one place the
# turns live, one ledger they bill to. Cost is why it defaults to Haiku: a
# panel one keystroke away gets used like a search box.
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
  transform:translateX(100%);
  transition:transform .2s cubic-bezier(.16,1,.3,1),width .2s ease}
.askpanel.on{transform:none}
.askpanel[hidden]{display:none}
/* Full screen: the same panel, the whole window. The thread keeps a reading
   column in the middle; the chats list becomes a real sidebar. */
.askpanel.wide{width:100vw;border-left:0}
.askpanel.wide .askctx,.askpanel.wide .askthread,.askpanel.wide .askfoot{
  padding-left:max(24px,calc((100% - 760px)/2));
  padding-right:max(24px,calc((100% - 760px)/2))}
.askmain{position:relative;display:flex;flex:1;min-height:0}
.askcol{flex:1;display:flex;flex-direction:column;min-width:0}
.asklist{flex:none;width:250px;overflow-y:auto;padding:10px;
  border-right:1px solid var(--line);background:var(--surface)}
.asklist[hidden]{display:none}
/* In the side panel the list lays over the thread instead of squeezing it. */
.askpanel:not(.wide) .asklist{position:absolute;inset:0;width:auto;z-index:6;
  background:var(--paper);border-right:0}
.asklistnew{display:block;width:100%;font:inherit;font-size:13px;font-weight:600;
  cursor:pointer;text-align:left;color:var(--ink);background:var(--paper);
  border:1px solid var(--line2);border-radius:10px;padding:8px 11px;
  margin-bottom:10px}
.asklistnew:hover{border-color:var(--dim)}
.asklab{font-size:10.5px;font-weight:700;letter-spacing:.08em;
  text-transform:uppercase;color:var(--faint);margin:10px 4px 5px}
.askitem{display:block;width:100%;font:inherit;cursor:pointer;text-align:left;
  border:0;background:none;border-radius:9px;padding:7px 9px;color:var(--dim)}
.askitem:hover{background:var(--sunken,var(--surface));color:var(--ink)}
.askitem.on{background:var(--sunken,var(--surface));color:var(--ink)}
.askitem .askitop{display:block;font-size:13px;font-weight:500;
  overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.askitem .askimeta{display:block;font-size:11px;color:var(--faint);margin-top:1px}
.askitem .askimeta.busy{color:var(--green,var(--ink));font-weight:600}
/* A file the answer names opens right here, rendered — never a trip to the
   Finder for a draft the chat just wrote. */
.askdoc{color:var(--green,var(--ink));text-decoration:underline;cursor:pointer}
.askdocview{position:absolute;inset:0;z-index:7;display:flex;flex-direction:column;
  background:var(--paper)}
.askdocview[hidden]{display:none}
.askdochead{flex:none;display:flex;gap:12px;align-items:center;padding:11px 16px;
  border-bottom:1px solid var(--line)}
.askdocback{font:inherit;font-size:12px;font-weight:600;cursor:pointer;border:0;
  background:none;color:var(--green,var(--ink));padding:0;white-space:nowrap}
.askdocback:hover{text-decoration:underline}
.askdocname{font-size:11.5px;color:var(--faint);overflow:hidden;
  text-overflow:ellipsis;white-space:nowrap}
.askdocbody{flex:1;overflow-y:auto;padding:18px 20px;font-size:14px;line-height:1.6}
.askdocbody table{border-collapse:collapse;font-size:12.5px;margin:0 0 12px;
  display:block;overflow-x:auto;max-width:100%}
.askdocbody td,.askdocbody th{border:1px solid var(--line);padding:4px 8px;
  vertical-align:top;text-align:left}
.askdocbody:has(.askframe){padding:0!important;overflow:hidden}
.askframe{display:block;width:100%;height:100%;border:0;background:var(--paper)}
.askpanel.wide .askdocbody{padding-left:max(24px,calc((100% - 760px)/2));
  padding-right:max(24px,calc((100% - 760px)/2))}
.askdocbody h1,.askdocbody h2,.askdocbody h3{
  font-family:var(--serif,'Literata',Georgia,serif);margin:14px 0 8px;line-height:1.25}
.askdocbody h1{font-size:20px}
.askdocbody h2{font-size:16px}
.askdocbody h3{font-size:14px}
.askdocbody p{margin:0 0 9px}
.askdocbody ul,.askdocbody ol{margin:0 0 9px;padding-left:22px}
.askdocbody li{margin:0 0 3px}
.askdocbody code{font-family:ui-monospace,Menlo,monospace;font-size:12.5px;
  background:var(--surface);padding:1px 4px;border-radius:4px}
.askdocbody blockquote{margin:0 0 9px;padding:2px 0 2px 12px;
  border-left:3px solid var(--line);color:var(--dim)}
.askhead{display:flex;gap:10px;align-items:center;padding:13px 16px;
  border-bottom:1px solid var(--line);flex:none}
.askhead>div{flex:1;min-width:0}
.askhead h2{margin:0;font:600 15px/1.2 var(--serif,'Literata',Georgia,serif)}
.askhead .asksub{font-size:11.5px;color:var(--faint);overflow:hidden;
  text-overflow:ellipsis;white-space:nowrap}
.askhead .asksub.waiting{white-space:normal;display:-webkit-box;
  -webkit-line-clamp:2;-webkit-box-orient:vertical}
.askico{flex:none;border:0;background:none;cursor:pointer;color:var(--dim);
  font-size:15px;line-height:1;padding:4px 5px;border-radius:8px}
.askico:hover{color:var(--ink);background:var(--surface)}
.askico.on{color:var(--ink);background:var(--sunken,var(--surface))}
.askx{border:0;background:none;color:var(--faint);cursor:pointer;
  font-size:20px;line-height:1;padding:2px 4px}
.askx:hover{color:var(--ink)}
/* A new conversation, one tap from the header: the list behind ☰ was the
   only way, and nobody found it (her question, 28 Sep). */
.asknew{flex:none;font:inherit;font-size:12px;font-weight:600;cursor:pointer;
  color:var(--ink);background:var(--surface);border:1px solid var(--line2);
  border-radius:999px;padding:4px 11px;white-space:nowrap}
.asknew:hover{border-color:var(--dim)}
.askfull{flex:none;font-size:11.5px;font-weight:600;color:var(--green,var(--ink));
  text-decoration:none;white-space:nowrap}
.askfull:hover{text-decoration:underline}
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
.askmsg.claude .askbody pre{margin:0 0 8px;padding:9px 11px;overflow-x:auto;
  font:12px/1.5 ui-monospace,Menlo,monospace;background:var(--surface);
  border:1px solid var(--line);border-radius:8px;white-space:pre}
.askmsg.claude .askbody table{border-collapse:collapse;margin:0 0 8px;
  font-size:13px;display:block;overflow-x:auto;max-width:100%}
.askmsg.claude .askbody th,.askmsg.claude .askbody td{border:1px solid var(--line);
  padding:4px 9px;text-align:left;vertical-align:top}
.askmsg.claude .askbody th{background:var(--surface)}
.askmsg.claude .askbody hr{border:0;border-top:1px solid var(--line);margin:10px 0}
.askmsg.note{align-self:center;font-size:12px;color:var(--faint);text-align:center}
/* The steps a turn took: one quiet line, open for the detail. */
.asksteps{align-self:stretch;font-size:12.5px;color:var(--dim);margin-bottom:-6px}
.asksteps>summary{cursor:pointer;list-style:none;display:inline-flex;gap:6px;
  align-items:center;color:var(--faint)}
.asksteps>summary::-webkit-details-marker{display:none}
.asksteps>summary::before{content:"\\25B8";font-size:10px}
.asksteps[open]>summary::before{content:"\\25BE"}
.asksteps>summary:hover{color:var(--ink)}
.asksteps .bad{color:var(--terra,#c0573e)}
.asksteps ol{margin:8px 0 0;padding:8px 10px 8px 28px;background:var(--surface);
  border:1px solid var(--line);border-radius:9px;display:flex;flex-direction:column;gap:6px}
.asksteps li{padding-left:2px}
.asksteps li .say{display:block;color:var(--faint);font-style:italic}
.asksteps li .did{color:var(--ink);font-family:ui-monospace,Menlo,monospace;
  font-size:11.5px;word-break:break-word}
.asksteps li.bad .did{color:var(--terra,#c0573e)}
.asksteps li i{font-style:normal}
/* Her attachments, as files instead of the note written for Claude. */
.askatts{display:flex;flex-wrap:wrap;gap:6px;margin-top:6px}
.askatt{font-size:12px;color:var(--ink);text-decoration:none;border:1px solid var(--line2);
  border-radius:8px;padding:3px 8px;background:var(--paper);white-space:nowrap;
  max-width:100%;overflow:hidden;text-overflow:ellipsis}
.askatt.img{padding:0;border:0;background:none;line-height:0}
.askatt.img img{max-width:180px;max-height:120px;border-radius:8px;object-fit:cover;
  border:1px solid var(--line)}
/* A question's answers, one tap each. */
.askchoices{display:flex;flex-wrap:wrap;gap:6px;margin-top:-4px}
.askchoice{font:inherit;font-size:13px;cursor:pointer;text-align:left;color:var(--ink);
  background:var(--paper);border:1px solid var(--line2);border-radius:999px;
  padding:6px 13px;max-width:100%}
.askchoice:hover{border-color:var(--green,var(--ink));color:var(--green,var(--ink))}
.askreceipt .askdoc{color:var(--dim)}
/* In a conversation, the shortcuts step aside so the thread has the room. */
/* The empty screen: the shortcuts, centred in the space a thread will use. */
.askstart{margin:auto 0;display:flex;flex-direction:column;align-items:center;
  gap:12px;text-align:center;padding:8px 4px}
.askstart[hidden]{display:none}
.askstarth{margin:0;font:600 16px/1.3 var(--serif,'Literata',Georgia,serif);color:var(--ink)}
.askstart .askskills{display:grid;grid-template-columns:1fr 1fr;gap:8px;
  width:100%;max-width:340px;padding:0}
.askstart .skillchip{border-radius:12px;padding:10px 12px;font-size:13.5px;
  white-space:normal}
.askstart .skillall{grid-column:1/-1;margin:2px 0 0;justify-self:center}
.askstart .planmeter.slim{padding:0;justify-content:center;width:100%;max-width:340px}
.askstartnote{margin:0;font-size:12px;color:var(--faint)}
/* What goes with the message, beside the box. */
.askopts{flex-basis:100%;display:flex;flex-wrap:wrap;gap:6px;align-items:center;order:-2}
.askopt{font:inherit;font-size:12px;cursor:pointer;color:var(--dim);
  background:var(--paper);border:1px solid var(--line2);border-radius:999px;
  padding:3px 10px;white-space:nowrap}
.askopt b{font-weight:600;color:var(--ink)}
.askopt:hover,.askopt[aria-expanded="true"]{border-color:var(--dim)}
.askopt.on{background:var(--green,var(--ink));border-color:transparent;color:var(--paper)}
.askopt.on b{color:inherit}
.askopt[hidden],.askopts .scopechip[hidden]{display:none}
.askfoot{position:relative}
.askpop{position:absolute;left:12px;bottom:calc(100% + 6px);z-index:8;
  width:min(320px,calc(100% - 24px));background:var(--paper);
  border:1px solid var(--line2);border-radius:14px;
  box-shadow:0 12px 36px rgba(0,0,0,.18);padding:10px 12px 12px}
.askpop[hidden]{display:none}
.askpop .asklab{margin:2px 2px 7px}
.askpop .askctx{padding:0;border:0;background:none}
.askpopnote{margin:9px 2px 0;font-size:11.5px;color:var(--faint)}
.askmodelopt{font:inherit;font-size:13px;width:100%;text-align:left;cursor:pointer;
  border:0;background:none;border-radius:8px;padding:6px 8px;color:var(--ink);
  display:flex;justify-content:space-between;gap:10px}
.askmodelopt:hover{background:var(--surface)}
.askmodelopt.on{background:var(--sunken,var(--surface));font-weight:600}
.askmodelopt span{color:var(--faint);font-size:11.5px;font-weight:400}
.askfoot .askmenu{bottom:calc(100% + 6px);max-height:min(62vh,560px)}
.askpop{max-height:min(62vh,560px);overflow-y:auto}
.asklist .askfull{display:block;margin:10px 4px 2px;font-size:12px}
.askhead .asksub:empty{display:none}
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
/* Talk, in the box since 7 Oct: the same mic the fields use, sized to sit
   beside the clip and ⋯. */
.askstartit{background:var(--green,var(--ink));color:var(--paper);border-color:transparent;font-weight:600}
.askstartit:hover{filter:brightness(1.08)}
.askstartit[hidden]{display:none}
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
  min-height:40px;max-height:40vh;border:1px solid var(--line);border-radius:10px;
  background:var(--surface);color:var(--ink)}
/* Past one line the box takes its own row above the buttons (8 Oct): wedged
   between them it was a column a few words wide. fit() in ASK_JS sets it. */
.askfoot.askgrow textarea{flex-basis:100%;order:-1}
.askfoot.askgrow .asksend{margin-left:auto}
/* An attachment the reader can open: its name is the way in. */
.askfileread{font:inherit;color:inherit;background:none;border:0;padding:0;
  cursor:pointer;text-decoration:underline;text-underline-offset:2px;
  overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.askfileread:hover{color:var(--ink)}
.askfoot textarea:focus{outline:2px solid var(--green,var(--ink));outline-offset:1px;
  border-color:transparent}
.asksend{flex:none;font:inherit;font-size:13px;font-weight:700;cursor:pointer;
  border:0;border-radius:10px;padding:10px 15px;
  background:var(--green,var(--ink));color:var(--paper)}
.asksend:disabled{opacity:.45;cursor:default}
/* Which Claude answers. Haiku is the default because this box gets used like
   a search box; the bigger ones are a choice she makes per chat. */
.askmodel{flex:none;font:inherit;font-size:12px;font-weight:600;cursor:pointer;
  color:var(--dim);background:var(--surface);border:1px solid var(--line);
  border-radius:10px;padding:9px 6px;max-width:88px}
.askmodel:hover{border-color:var(--dim);color:var(--ink)}
/* Floating corner buttons — the corner stack, the agent pill — live exactly
   where the panel's own send button lands. They step aside while it is open
   rather than sitting on top of it. */
body.asking .fabstack,body.asking .fab,body.asking .btour-btn,
body.asking .agentbar{display:none}
/* The panel opens UNDER the bar, not over it (28 Sep). Laid over the top it
   hid the links, the find box and the gear at every laptop width, so going
   anywhere meant closing it first. --asktop is the bar's height, measured
   when it opens. The bar rises above the scrim so what hangs from it — the
   find box's results — lands on top of the panel rather than under it. */
@media(min-width:761px){
  .askpanel,.askscrim{top:var(--asktop,0px)}
  body.asking .top,body.asking .bar:has(>.top){z-index:97}
}

/* ── the box's own furniture (28 Sep) ─────────────────────────────────── */
/* For you: everything the brain is waiting on her for. The same list Today
   shows; each line takes her to it. */
.asktray{flex:none;border-bottom:1px solid var(--line);background:var(--surface)}
.asktray[hidden]{display:none}
.asktray>summary{list-style:none;cursor:pointer;padding:9px 16px;font-size:13px;
  display:flex;gap:8px;align-items:center;color:var(--ink)}
.asktray>summary::-webkit-details-marker{display:none}
.asktray>summary b{font-weight:700}
.asktray>summary .asktrayn{font-size:11.5px;font-weight:700;color:var(--paper);
  background:var(--ink);border-radius:999px;padding:1px 7px}
.asktray>summary::after{content:"\\25BE";margin-left:auto;color:var(--faint);font-size:11px}
.asktray[open]>summary::after{content:"\\25B4"}
.asktrayitems{padding:0 10px 10px;display:flex;flex-direction:column;gap:2px;
  max-height:32vh;overflow-y:auto}
.asktrayitem{display:grid;grid-template-columns:auto 1fr;gap:8px;align-items:baseline;
  width:100%;font:inherit;font-size:13px;text-align:left;cursor:pointer;border:0;
  background:none;border-radius:8px;padding:6px 6px;color:var(--ink)}
.asktrayitem:hover{background:var(--sunken,var(--paper))}
.asktrayitem .k{font-size:10px;font-weight:700;letter-spacing:.07em;
  text-transform:uppercase;color:var(--faint);min-width:52px}
/* Working on: what Claude is running right now, one line. */
.askworking{flex:none;display:flex;gap:8px;align-items:center;padding:8px 16px;
  font-size:12.5px;color:var(--dim);border-bottom:1px solid var(--line)}
.askworking[hidden]{display:none}
.askskills{flex:none;display:flex;flex-wrap:wrap;align-items:center;gap:6px;
  padding:8px 16px 0}
.askskillslab{font-size:10.5px;letter-spacing:.16em;text-transform:uppercase;
  color:var(--dim);margin-right:2px}
.skillchip{font:inherit;font-size:12.5px;cursor:pointer;color:var(--ink);
  background:var(--surface);border:1px solid var(--line2);border-radius:999px;
  padding:4px 11px;white-space:nowrap}
.skillchip:hover{border-color:var(--dim)}
.skillall{margin-left:auto;font-size:12px;color:var(--dim);white-space:nowrap}
.skillall:hover{color:var(--ink)}
.askworking i{width:7px;height:7px;border-radius:50%;flex:none;
  background:var(--green,var(--ink));animation:askpulse 1.3s ease-in-out infinite}
.askworking a{margin-left:auto;color:var(--green,var(--ink));font-weight:600;
  text-decoration:none;white-space:nowrap}
.askworking a:hover{text-decoration:underline}
/* What the box is about, and how it will handle the next thing said. */
.askscope{flex:none;display:flex;flex-wrap:wrap;gap:6px;align-items:center;
  padding:8px 14px;border-bottom:1px solid var(--line)}
.scopechip,.intentchip{font:inherit;font-size:12px;border-radius:999px;
  padding:3px 10px;border:1px solid var(--line2);background:var(--paper);
  color:var(--dim);white-space:nowrap;max-width:100%;overflow:hidden;
  text-overflow:ellipsis}
.scopechip.on{color:var(--ink);font-weight:600;border-color:var(--ink)}
.scopechip b,.intentchip b{font-weight:400;cursor:pointer;margin-left:4px;
  color:var(--faint)}
.scopechip b:hover,.intentchip b:hover{color:var(--ink)}
.intentchip{color:var(--paper);background:var(--green,var(--ink));
  border-color:transparent;font-weight:600}
.intentchip b{color:inherit;opacity:.75}
.intentchip[hidden]{display:none}
/* ⋯: the overrides, one layer down so the box itself stays one field. */
.askmenu{position:absolute;right:12px;bottom:64px;z-index:8;width:min(330px,calc(100% - 24px));
  max-height:70%;overflow-y:auto;background:var(--paper);border:1px solid var(--line2);
  border-radius:14px;box-shadow:0 12px 36px rgba(0,0,0,.18);padding:10px 12px 12px}
.askmenu[hidden]{display:none}
.askmenu .asklab{margin:8px 2px 5px}
.askmenu .asklab:first-child{margin-top:2px}
.askintents{display:flex;flex-direction:column;gap:1px}
.askintent{font:inherit;font-size:13px;text-align:left;cursor:pointer;border:0;
  background:none;border-radius:8px;padding:6px 8px;color:var(--ink);
  display:flex;justify-content:space-between;gap:10px}
.askintent:hover{background:var(--surface)}
.askintent.on{background:var(--sunken,var(--surface));font-weight:600}
.askintent span{color:var(--faint);font-size:11.5px;font-weight:400}
.askmenu .askctx{padding:0;border:0;background:none}
.askmenu .askmodel{max-width:none;width:100%}
/* The list's two halves: conversations, and the files the brain made. */
.asktabs{display:flex;gap:4px;margin:0 0 10px;padding:3px;border:1px solid var(--line2);
  border-radius:999px;background:var(--paper)}
.asktab{flex:1;font:inherit;font-size:12.5px;font-weight:600;cursor:pointer;border:0;
  border-radius:999px;padding:6px 8px;background:none;color:var(--dim)}
.asktab.on{background:var(--ink);color:var(--paper)}
.askfilekinds{display:flex;flex-wrap:wrap;gap:4px;margin:0 0 8px}
.askfilekind{font:inherit;font-size:11.5px;cursor:pointer;border:1px solid var(--line2);
  border-radius:999px;padding:3px 9px;background:var(--paper);color:var(--dim)}
.askfilekind.on{background:var(--green,var(--ink));color:var(--paper);border-color:transparent}
.askfile2{display:block;width:100%;font:inherit;cursor:pointer;text-align:left;border:0;
  background:none;border-radius:9px;padding:7px 9px;color:var(--ink)}
.askfile2:hover{background:var(--sunken,var(--surface))}
.askfile2 .askitop{display:block;font-size:13px;font-weight:500;overflow:hidden;
  text-overflow:ellipsis;white-space:nowrap}
.askfile2 .askimeta{display:block;font-size:11px;color:var(--faint);margin-top:1px}
/* The reader's tools: edit, its own app, the Finder. */
.askdoctools{flex:none;display:flex;flex-wrap:wrap;gap:6px;padding:8px 16px;
  border-bottom:1px solid var(--line)}
.askdoctools[hidden]{display:none}
.anontext{white-space:pre-wrap;word-wrap:break-word;margin:0 0 12px}
.anonrep{font-size:12px;color:var(--dim);margin:0 0 12px}
.anonlab{font-size:11.5px;color:var(--faint);margin:10px 0 6px}
.anonbusy{display:flex;align-items:center;gap:10px;margin:4px 0 10px}
.anonspin{flex:none;width:16px;height:16px;border-radius:50%;border:2px solid var(--line);
  border-top-color:var(--green,var(--ink));animation:anonspin .8s linear infinite}
@keyframes anonspin{to{transform:rotate(360deg)}}
@media (prefers-reduced-motion:reduce){.anonspin{animation:none;background:var(--green,var(--ink))}}
.anonsecs{color:var(--faint);font-size:12px;font-variant-numeric:tabular-nums}
.anonlimits{margin:16px 0 4px;padding:10px 12px;border:1px solid var(--line);border-radius:8px;
  font-size:12.5px;color:var(--dim);line-height:1.5}
.anonlimits .anonlab{margin:0 0 4px}
.anonlimits ul{margin:0 0 6px;padding-left:18px}
.anonwarn{color:var(--red,var(--ink))}
.anonchip{font:inherit;font-size:12px;cursor:pointer;margin:0 6px 6px 0;padding:3px 10px;
  border-radius:999px;border:1px solid var(--line);background:var(--surface);color:var(--ink)}
.anonchip:hover{border-color:var(--ink)}
.anonseen summary{font-size:12px;color:var(--faint);cursor:pointer;margin:0 0 8px}
.anonseen .anontext{font-size:12.5px;color:var(--dim);padding-left:10px;
  border-left:2px solid var(--line)}
.askdoctools button,.askdoctools a{font:inherit;font-size:12px;font-weight:600;cursor:pointer;
  border:1px solid var(--line2);border-radius:999px;padding:4px 11px;background:var(--surface);
  color:var(--ink);text-decoration:none}
.askdoctools .go{background:var(--green,var(--ink));color:var(--paper);border-color:transparent}
.askedit{width:100%;min-height:60vh;font:13px/1.55 ui-monospace,Menlo,monospace;
  padding:12px;border:1px solid var(--line);border-radius:10px;background:var(--surface);
  color:var(--ink);resize:vertical}
.askpre{white-space:pre-wrap;font:12.5px/1.55 ui-monospace,Menlo,monospace}
.asknoview{color:var(--faint);font-size:13.5px}
/* Where the turn landed, read from its own steps. */
.askreceipt{align-self:flex-start;font-size:12px;color:var(--dim);
  border-left:3px solid var(--green,var(--ink));padding:1px 0 1px 9px;margin-top:-6px}
.askreceipt b{font-weight:600;color:var(--ink)}
/* ── the corner stack (28 Sep) ────────────────────────────────────────
   The ✦, the tour's ? and Today's ramble note each floated on their own,
   and the ✦ sat beside the bar's own ✦ Ask — two doors to one box (the
   ramble note folded into the box on 7 Oct). Now they stand in
   one column in the bottom-right corner, icon-sized, words in the tooltip.
   The ✦ shows only while the bar's Ask is out of sight (.near hides it),
   and the pages keep a lane clear for the column (page.css, index). */
.fabstack{position:fixed;right:14px;bottom:calc(14px + env(safe-area-inset-bottom,0px));
  z-index:70;display:flex;flex-direction:column;align-items:center;gap:10px;
  transition:transform .25s var(--ease),opacity .25s var(--ease)}
/* ducks while the page scrolls — never on top of the row being read */
.fabstack.away{transform:translateY(24px);opacity:0;pointer-events:none}
.fabstack>.askfab,.fabstack>.btour-btn{position:static;
  flex:none;width:40px;height:40px;margin:0;padding:0;border-radius:50%;
  display:grid;place-items:center;cursor:pointer;line-height:1;font-family:inherit;
  letter-spacing:0;text-transform:none}
.fabstack>.btour-btn{font-size:16px;font-weight:700}
.fabstack>.askfab.near{display:none}
/* The look sits at class weight (:where), so each skin's .fab rules
   dress the column the way they dress the rest. */
:where(.fabstack)>.askfab{font-size:18px;font-weight:700;color:var(--paper);
  background:var(--green,var(--ink));border:0;box-shadow:0 6px 20px rgba(0,0,0,.2)}
:where(.fabstack)>.askfab:hover{filter:brightness(1.08)}
:where(.fabstack)>.btour-btn{
  color:var(--dim);background:var(--surface);border:1.5px solid var(--line2);
  box-shadow:0 4px 16px rgba(0,0,0,.10)}
:where(.fabstack)>.btour-btn:hover{color:var(--ink)}
.askfab[hidden]{display:none}
/* the capture sheet rises from the same corner */
body:has(#sheet:not([hidden])) .fabstack{display:none}
@media(max-width:760px){
  /* above the tab bar, and a size smaller */
  .fabstack{right:12px;bottom:calc(74px + env(safe-area-inset-bottom,0px));gap:8px}
  .fabstack>.askfab,.fabstack>.btour-btn{width:36px;height:36px}
  body.has-runbar .fabstack{bottom:calc(126px + env(safe-area-inset-bottom,0px))}
}
/* ── phone: ? in the bar (28 Sep) ─────────────────────────────────────
   Nothing fixed may sit over the words at rest on a phone, and the corner
   column did, at the right edge of every page. The script moves ? into the
   bar, before ✦ Ask. The corner ✦ does not show at all here: the bar is
   pinned on every page, so its ✦ Ask is always in reach. */
@media(max-width:760px){
  .fabstack>.askfab{display:none}
  .hacts>.btour-btn{position:static;flex:none;width:36px;height:36px;
    margin:0;padding:0;border-radius:50%;display:grid;place-items:center;cursor:pointer;
    line-height:1;font-family:inherit;font-size:15px;font-weight:700;letter-spacing:0;
    text-transform:none;z-index:auto}
  .hacts>.btour-btn{color:var(--dim);background:var(--surface);
    border:1.5px solid var(--line2);box-shadow:none}
}
/* A phone: the panel already fills the screen, so full screen goes, and
   what the box is about gets two lines instead of "it reads your wh…".
   ☰ and × keep their size and get a fingertip's tap area (28 Sep). */
@media(max-width:440px){
  #askwide{display:none}
  .askhead .asksub{white-space:normal;display:-webkit-box;-webkit-line-clamp:2;
    -webkit-box-orient:vertical}
}
@media(pointer:coarse){
  .askhead .askico,.askhead .askx{position:relative}
  .askhead .askico::after,.askhead .askx::after{content:"";position:absolute;
    inset:-8px -6px}
}
@media(prefers-reduced-motion:reduce){.askworking i{animation:none}
  .fabstack{transition:none}}
"""


def ask_html():
    import agents
    return agents.say("""
<div class="askscrim" id="askscrim" hidden></div>
<aside class="askpanel" id="askpanel" hidden aria-label="Tell the brain">
  <div class="askhead">
    <button class="askico" id="asklistbtn" title="Your conversations"
      aria-label="Your conversations">&#9776;</button>
    <div><h2 id="asktitle">Tell the brain</h2>
      <div class="asksub" id="asksub"></div></div>
    <button class="asknew" id="asknew" title="Start a new conversation">&#65291; New</button>
    <button class="askico" id="askwide" title="Full screen"
      aria-label="Full screen">&#x26F6;</button>
    <button class="askx" id="askx" aria-label="Close">&times;</button>
  </div>
  <div class="askmain">
    <nav class="asklist" id="asklist" hidden aria-label="Your conversations and files">
      <div class="asktabs" role="tablist">
        <button class="asktab on" data-tab="convos" role="tab">Conversations</button>
        <button class="asktab" data-tab="files" role="tab">Files</button>
      </div>
      <div id="askconvopane">
        <button class="asklistnew" id="asklistnew">&#65291; New conversation</button>
        <div id="asklistitems"></div>
        <a class="askfull" id="askfull" href="sessions.html">The full Conversations page</a>
      </div>
      <div id="askfilepane" hidden>
        <div class="askfilekinds" id="askfilekinds"></div>
        <div id="askfileitems"><p class="asklab">Looking&hellip;</p></div>
      </div>
    </nav>
    <div class="askcol">
      <details class="asktray" id="asktray" hidden>
        <summary><b>For you</b><span class="asktrayn" id="asktrayn"></span></summary>
        <div class="asktrayitems" id="asktrayitems"></div>
      </details>
      <div class="askworking" id="askworking" hidden></div>
      <div class="askthread" id="askthread"></div>
      <!-- The empty screen: the shortcuts live here, not above every
           conversation (7 Oct). paint() moves it into the thread. -->
      <div class="askstart" id="askstart" hidden>
        <p class="askstarth">What do you need?</p>
        <div class="askskills" id="askskills" role="group" aria-label="Run a skill">
          <button class="skillchip" data-skill="today" title="Write today's plan: three tasks across your fronts">Plan today</button>
          <button class="skillchip" data-skill="brief" title="Where things stand, and the inbox triaged">Catch me up</button>
          <a class="skillall" href="index.html#/hood">All jobs</a>
        </div>
        <div class="planmeter slim" data-planmeter hidden></div>
        <p class="askstartnote">Answers land here. Nothing is sent to anyone.</p>
      </div>
      <div class="askdocview" id="askdocview" hidden>
        <div class="askdochead">
          <button class="askdocback" id="askdocback">&larr; back</button>
          <span class="askdocname" id="askdocname"></span>
        </div>
        <div class="askdoctools" id="askdoctools" hidden></div>
        <div class="askdocbody" id="askdocbody"></div>
      </div>
      <div class="askfoot">
        <div class="askmenu" id="askmenu" hidden>
          <!-- Since 7 Oct Claude reads the mode from her words (box_rules.py).
               What stays here changes where the words go, which is never
               Claude's to guess. -->
          <p class="asklab">Instead of a conversation</p>
          <div class="askintents" id="askintents">
            <button class="askintent" data-intent="save">Just save it<span>to the inbox, word for word, no AI</span></button>
            <button class="askintent" data-intent="journal">Private journal<span>kept as you wrote it</span></button>
            <button class="askintent" data-intent="hide">Hide the names<span>for another AI, and back</span></button>
          </div>
        </div>
        <!-- What goes with the message, chosen beside the box (7 Oct): what it
             reads, which Claude, names hidden. Each chip opens one of these. -->
        <div class="askpop" id="askreads" hidden>
          <p class="asklab">What it reads before answering</p>
          <div class="askctx" id="askctx">
            <button class="ctxchip on" data-f="">everything</button>
            <button class="ctxchip" data-f="brain/today.md">today</button>
            <button class="ctxchip" data-f="brain/workstreams.md">the plate</button>
            <button class="ctxchip" data-f="brain/people.md">people</button>
            <button class="ctxchip" data-f="brain/habits.md">habits</button>
            <button class="ctxchip" data-f="brain/about-me.md">about you</button>
            <button class="ctxchip" data-f="brain/writing-rules.md">writing style</button>
          </div>
          <p class="askpopnote">Fewer files: cheaper, and the answer stays on topic.
            None picked: a plain chat.</p>
        </div>
        <div class="askpop" id="askmodels" hidden>
          <p class="asklab">Which Claude answers</p>
          <button class="askmodelopt" data-model="haiku"><b>Haiku</b><span>fastest, costs cents</span></button>
          <button class="askmodelopt" data-model="sonnet"><b>Sonnet</b><span>balanced, the usual</span></button>
          <button class="askmodelopt" data-model="opus"><b>Opus</b><span>deepest thinking</span></button>
          <button class="askmodelopt" data-model="fable"><b>Fable</b><span>writes best, costs most</span></button>
        </div>
        <div class="askopts" id="askopts">
          <button class="askopt" id="optreads" aria-haspopup="true" aria-expanded="false"
            title="What Claude reads before it answers">Reads: <b id="optreadsv">everything</b> &#9662;</button>
          <span class="scopechip" id="scopechip" hidden></span>
          <!-- Opened from a task's ✦: the legwork run is one tap (page.js
               window.brainStart); what she types goes with it as precisions. -->
          <button class="askopt askstartit needs-server" id="askstartit" hidden
            title="Claude does the legwork, such as finding options or drafting a message. It never sends anything.">&#10022; Start it for me</button>
          <button class="askopt" id="optmodel" aria-haspopup="true" aria-expanded="false"
            title="Which Claude answers"><b id="optmodelv">Sonnet</b> &#9662;</button>
          <span class="intentchip" id="intentchip" hidden></span>
          <select class="askmodel" id="askmodel" hidden aria-hidden="true" tabindex="-1">
            <option value="haiku">Haiku</option>
            <option value="sonnet">Sonnet</option>
            <option value="opus">Opus</option>
            <option value="fable">Fable</option>
          </select>
        </div>
        <div class="askfiles" id="askfiles"></div>
        <input type="file" id="askfilein" multiple hidden
          accept=".pdf,.png,.jpg,.jpeg,.webp,.gif,.txt,.md,.csv,.docx,.xlsx,.ics,.json">
        <button class="askclip" id="askclip" title="Attach documents or images"
          aria-label="Attach documents or images">&#128206;</button>
        <textarea id="asktext" rows="1"
          placeholder="Tell the brain anything"></textarea>
        <!-- No mic here since 9 Oct: Talk is back in the bar, and one door
             to it is enough. Space still talks when nothing is typed. -->
        <button class="askclip" id="askmore" title="Just save it, private journal, hide the names"
          aria-label="Options" aria-expanded="false">&#8943;</button>
        <!-- askgo, not asksend: an older page may still carry an asksend. -->
        <button class="asksend" id="askgo">Send</button>
      </div>
    </div>
  </div>
</aside>
<div class="fabstack" id="fabstack">
  <button class="askfab fab near" id="askfab" title="Tell the brain anything"
    aria-label="Tell the brain"><svg viewBox="0 0 24 24" width="20" height="20"
    fill="currentColor" aria-hidden="true"><path d="M12 2.5l2.3 6.6 6.7 2.4-6.7
    2.4L12 20.5l-2.3-6.6-6.7-2.4 6.7-2.4z"/></svg></button>
</div>
""")


ASK_JS = r"""
(function(){
var DEFAULT_SRC = __ASKSRC__;
var CHAT_MODEL = __ASKMODEL__;
var panel = document.getElementById('askpanel');
if(!panel) return;
// Look INSIDE the panel, never across the page. This panel is injected into
// every page in the brain, so any id it uses is one a page might already
// have — and getElementById hands back whichever came first in the document.
function E(id){ return panel.querySelector('#' + id); }
var scrim = document.getElementById('askscrim'), thread = E('askthread'),
    ta = E('asktext'), send = E('askgo'),
    sub = E('asksub'), full = E('askfull'),
    ctx = E('askctx'), clip = E('askclip'),
    filein = E('askfilein'), filebar = E('askfiles'),
    list = E('asklist'), listbtn = E('asklistbtn'),
    listnew = E('asklistnew'), listitems = E('asklistitems'),
    widebtn = E('askwide'), modelsel = E('askmodel'),
    docview = E('askdocview'), docback = E('askdocback'),
    docname = E('askdocname'), docbody = E('askdocbody'),
    tray = E('asktray'), trayn = E('asktrayn'), trayitems = E('asktrayitems'),
    working = E('askworking'), scopechip = E('scopechip'),
    intentchip = E('intentchip'), menu = E('askmenu'), morebtn = E('askmore'),
    intents = E('askintents');
var fab = document.getElementById('askfab');
var convopane = E('askconvopane'), filepane = E('askfilepane'),
    filekinds = E('askfilekinds'), fileitems = E('askfileitems'),
    doctools = E('askdoctools');
var FILES = [], FKIND = '', TAB = 'convos', DOCID = '';
var CID = null, TIMER = null, WORKING = false, STAMP = '', TICK = 0;
var LIVE = [], PAST = [], LISTKEY = '';   // the conversations list, and its change key
var ENDED = false, HANDS = true;          // where the attached conversation stands
var HOLDER = '';                          // the busy conversation it waits on, if any
var STEP = '';                            // what the running turn is doing now
var TOPIC = '';                           // what the attached conversation is about
var PENDING = [];   // {name, data} waiting to go with the next ask
var PATHS = [];     // files already in the brain (relative to brain/) to name
var READS = {};     // path -> the reader's id, for an attachment she can open
var SCOPE = null;   // what the box is about; null is the whole brain
var INTENT = 'talk';
var FRESH = false;  // opened for a purpose: start clean, not in an old thread
var WAITS = false;  // it said it will finish once the other conversation is done
var CTITLE = '';    // the attached conversation's name, for the header
var startbox = E('askstart'), optreads = E('optreads'), optmodel = E('optmodel'),
    startit = E('askstartit');
var START = null;   // a task its ✦ handed over: {text, ws}
var POPS = {reads: E('askreads'), models: E('askmodels')};
var CHIPS = {reads: optreads, models: optmodel};
var MODELNAME = {haiku: 'Haiku', sonnet: 'Sonnet', opus: 'Opus', fable: 'Fable'};

// localStorage can refuse (private windows) — losing the preference is fine,
// losing the panel is not.
function keep(k, v){ try {
  v == null ? localStorage.removeItem(k) : localStorage.setItem(k, v);
} catch(e){} }
function kept(k){ try { return localStorage.getItem(k); } catch(e){ return null; } }

// Which Claude answers: the conversation's own pick, kept on the server,
// else the default from settings. Not the browser's memory: a cheap pick
// made once for a quick question stuck to every conversation after it, and
// a CV for a job came out of Haiku (7 Oct).
keep('askmodel', null);
modelsel.value = CHAT_MODEL;
function useModel(m){
  modelsel.value = /^(haiku|sonnet|opus|fable)$/.test(m || '') ? m : CHAT_MODEL;
}
modelsel.onchange = function(){
  if(CID) jpost('/api/sessions/model', {id: CID, model: modelsel.value})
    .catch(function(){});
};

// Quotes too, so the result is safe inside an attribute as well as text.
function esc(s){ return String(s == null ? '' : s)
  .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
  .replace(/"/g,'&quot;').replace(/'/g,'&#39;'); }
// Just enough markdown for an answer to be readable — bold, code, bullets,
// fenced blocks, tables, rules, paragraphs.
function mini(t){
  var out = [], list = false, code = false, buf = [], tbl = [];
  function endList(){ if(list){ out.push('</ul>'); list = false; } }
  function endTbl(){
    if(!tbl.length) return;
    var h = '<table>';
    tbl.forEach(function(cells, i){
      var tag = i === 0 ? 'th' : 'td';
      h += '<tr>' + cells.map(function(c){
        return '<' + tag + '>' + inl(c) + '</' + tag + '>';
      }).join('') + '</tr>';
    });
    out.push(h + '</table>');
    tbl = [];
  }
  (t || '').split('\n').forEach(function(line){
    if(/^```/.test(line.trim())){
      if(code){ out.push('<pre>' + esc(buf.join('\n')) + '</pre>'); buf = []; }
      else { endList(); endTbl(); }
      code = !code; return;
    }
    if(code){ buf.push(line); return; }
    var s = line.trim();
    if(/^\|.*\|$/.test(s)){
      var cells = s.slice(1, -1).split('|').map(function(c){ return c.trim(); });
      if(cells.every(function(c){ return /^:?-{2,}:?$/.test(c); })) return;
      endList(); tbl.push(cells); return;
    }
    endTbl();
    if(/^(-{3,}|\*{3,})$/.test(s)){ endList(); out.push('<hr>'); return; }
    var m = s.match(/^[-*]\s+(.*)/);
    if(m){ if(!list){ out.push('<ul>'); list = true; } out.push('<li>' + inl(m[1]) + '</li>'); return; }
    endList();
    if(s) out.push('<p>' + inl(s) + '</p>');
  });
  if(code && buf.length) out.push('<pre>' + esc(buf.join('\n')) + '</pre>');
  endTbl(); endList();
  return out.join('');
}
// A markdown link. A file link (file://, a full path, a brain path) opens
// here, rendered, or shows in the Finder; the browser itself refuses file://
// from a page, so "Done, saved to [the CV](file:///…)" used to do nothing.
function link(txt, url){
  var label = String(txt).replace(/`/g, '');
  var u = url.replace(/^file:\/\//i, '');
  try { u = decodeURI(u); } catch(e){}
  if(/^https?:\/\//i.test(url))
    return '<a href="' + esc(url) + '" target="_blank" rel="noopener">' + esc(label) + '</a>';
  if(/^mailto:/i.test(url)) return '<a href="' + esc(url) + '">' + esc(label) + '</a>';
  if(u.charAt(0) === '/' || /^(brain|To share)\//.test(u)){
    if(label.indexOf('/') >= 0) label = label.replace(/\/+$/, '').split('/').pop();
    if(/\.md$/i.test(u)) return '<a href="#" class="askdoc" data-f="' + esc(u) + '">' + esc(label) + '</a>';
    return '<a href="#" class="askdoc askshare" data-p="' + esc(u)
      + '" title="Show in Finder">' + esc(label) + '</a>';
  }
  return esc(label);
}
function inl(s){
  var links = [];
  s = String(s == null ? '' : s).replace(/\[([^\]\n]+)\]\(([^)\s]+)\)/g, function(_, t, u){
    links.push(link(t, u)); return '\u0000' + (links.length - 1) + '\u0000';
  });
  s = esc(s).replace(/\*\*(.+?)\*\*/g, '<b>$1</b>')
    .replace(/`([^`]+)`/g, '<code>$1</code>');
  // A file in To share shows itself in the Finder, ready to send.
  s = s.replace(/((?:[\w~.\/-]*\/)?To share\/[^<>\n|*`]*?\.(?:docx|pdf|pptx|xlsx|png|jpg))/g, function(p){
    return '<a href="#" class="askdoc askshare" data-p="'
      + p.replace(/^.*?(?=To share\/)/, '') + '" title="Show in Finder">' + p + '</a>';
  });
  // A finished file the brain made (a PDF beside the CV, a Word draft)
  // shows itself in the Finder the same way.
  s = s.replace(/((?:[\w~.\/-]*\/)?brain\/(?:files|drafts)\/[^<>\n|*`]*?\.(?:docx|pdf|pptx|xlsx|png|jpg))/g, function(p){
    var rel = p.charAt(0) === '/' ? p : p.replace(/^(?:.*?\/)?(?=brain\/)/, '');
    return '<a href="#" class="askdoc askshare" data-p="' + rel
      + '" title="Show in Finder">' + p.split('/').pop() + '</a>';
  });
  // A named markdown file becomes a link that opens rendered, right here.
  // A full path goes as-is (the server checks it sits in the conversation's
  // folder); a partial one is cut at the folder called exactly "brain", so
  // ".../life-brain/brain/files" does not become "brain/brain/files".
  return s.replace(/((?:[\w~.\/-]*\/)?brain\/[\w.\/-]+\.md)/g, function(p){
    var rel = p.charAt(0) === '/' ? p.replace(/^\/+/, '/')
                                  : p.replace(/^(?:.*?\/)?(?=brain\/)/, '');
    return '<a href="#" class="askdoc" data-f="' + rel + '">' + p + '</a>';
  }).replace(/\u0000(\d+)\u0000/g, function(_, i){ return links[+i] || ''; });
}

// The rendered view of a file the conversation named — read-only, .md only.
// ── names hidden (anonymize.py) ──────────────────────────────────────────
// Shown in the document pane, which stays up over a conversation: what
// would leave, then Claude's answer or the restored text, each with Copy.
var ANONT = null;
function anonShow(title, html, buttons){
  if(ANONT){ clearInterval(ANONT); ANONT = null; }
  docname.textContent = title;
  docbody.innerHTML = html;
  doctools.innerHTML = '';
  buttons.forEach(function(b){
    var el = document.createElement('button');
    el.textContent = b[0]; if(b[2]) el.className = 'go';
    el.onclick = b[1]; doctools.appendChild(el);
  });
  doctools.hidden = !buttons.length;
  DOCID = ''; docview.hidden = false; docbody.scrollTop = 0;
}
// Something is running: say what, where, and for how long so far. The
// hiding takes about ten seconds (the name model loading), long enough to
// look broken without a sign of life.
function anonBusy(title, msg, sub){
  var t0 = Date.now();
  anonShow(title, '<div class="anonbusy" role="status"><span class="anonspin" aria-hidden="true">'
    + '</span><span>' + esc(msg) + '</span><span class="anonsecs" id="anonsecs">0 s</span></div>'
    + (sub ? '<p class="anonrep">' + esc(sub) + '</p>' : ''), []);
  ANONT = setInterval(function(){
    var el = document.getElementById('anonsecs');
    if(el) el.textContent = Math.round((Date.now() - t0) / 1000) + ' s';
  }, 1000);
}
function anonFail(title, msg){
  anonShow(title, '<p class="anonrep anonwarn">' + esc(msg) + '</p>', []);
}
function anonCopy(text){
  return function(){
    navigator.clipboard.writeText(text)
      .then(function(){ note('Copied.'); }, function(){ note('Could not copy: select the text instead.'); });
  };
}
// What she typed, and her taps on the preview: a guessed name to keep
// visible, a visible word to hide. Each tap masks the text again.
var ANON = {text: '', keep: [], also: []};
function anonChips(words, act){
  return words.map(function(w){
    return '<button class="anonchip" data-anon="' + act + '" data-w="' + esc(w) + '">'
      + esc(w) + '</button>';
  }).join('');
}
function anonPreview(j){
  var failed = j.model && j.model.indexOf('failed') === 0;
  anonShow('Names hidden: this is all that would leave',
    '<div class="anontext">' + esc(j.text) + '</div>'
      + '<p class="anonrep">' + esc(j.summary) + ' Done on this Mac, offline: nothing '
      + 'leaves until you press Ask Claude or Copy.</p>'
      + (failed ? '<p class="anonrep anonwarn">The local name model did not run, so '
                  + 'lowercase names may still show.</p>' : '')
      + (j.guessed.length ? '<p class="anonlab">Guessed. Tap one to leave it visible.</p>'
                            + anonChips(j.guessed, 'keep') : '')
      + (j.visible.length ? '<p class="anonlab">Left visible. Tap any that is a name.</p>'
                            + anonChips(j.visible, 'also') : '')
      + '<div class="anonlimits"><p class="anonlab">What it can still miss</p><ul>'
      + '<li>A name in lowercase that is also a word, like “waiting on faith”.</li>'
      + '<li>A nickname or initials it has never seen.</li>'
      + '<li>Details that point to someone without naming them: a job, a field of '
      + 'study, a date, a small place, a quote.</li></ul>'
      + 'Read it once before it leaves. Tap a word above to hide it, or edit your text '
      + 'in the box and press Hide again.</div>',
    [['Ask Claude', function(){ anonAsk(j); }, true], ['Copy', anonCopy(j.text)]]);
}
docbody.addEventListener('click', function(e){
  var c = e.target.closest('.anonchip'); if(!c) return;
  ANON[c.dataset.anon].push(c.dataset.w);
  anonBusy('Hiding the names', 'Hiding the names again, on this Mac');
  jpost('/api/anon/mask', ANON)
    .then(function(j){ anonPreview(j); })
    .catch(function(err){ anonFail('Could not hide the names', err.message); });
});
function anonAsk(j){
  anonBusy('Asking Claude', 'Claude is answering',
           'Claude sees only the hidden version. Its answer comes back here with the names in.');
  jpost('/api/anon/ask', {text: j.text, key: j.key, model: modelsel.value || CHAT_MODEL})
    .then(function(r){
      anonShow('Claude\'s answer, names back',
        '<div class="anonmd">' + mini(r.answer) + '</div>'
          + (r.strays.length ? '<p class="anonrep">Not from your text, left as is: '
             + esc(r.strays.join(', ')) + '</p>' : '')
          + '<details class="anonseen"><summary>What Claude saw and said</summary>'
          + '<div class="anontext">' + esc(j.text) + '</div><div class="anontext">'
          + esc(r.seen) + '</div></details>',
        [['Copy', anonCopy(r.answer), true]]);
    })
    .catch(function(e){ anonFail('Claude did not answer', e.message); });
}
function anonRestored(j){
  var warn = (j.unsure ? 'More than one recent masking fits this answer; the newest '
              + 'was used, so check the names. ' : '')
    + (j.strays.length ? 'Not in that masking, left as is: ' + j.strays.join(', ') + '.' : '');
  anonShow('Names put back',
    '<div class="anontext">' + esc(j.text) + '</div>'
      + (warn ? '<p class="anonrep">' + esc(warn) + '</p>' : ''),
    [['Copy', anonCopy(j.text), true]]);
}

function openDoc(f){
  if(!CID) return;
  doctools.hidden = true; DOCID = '';
  fetch('/api/sessions/doc?id=' + encodeURIComponent(CID)
        + '&file=' + encodeURIComponent(f))
    .then(function(r){ return r.json(); })
    .then(function(j){
      if(j.error){ note(j.error); return; }
      docname.textContent = j.file || f;
      docbody.innerHTML = j.html || '';
      docview.hidden = false;
      docbody.scrollTop = 0;
    })
    .catch(function(){ note('Could not open ' + f); });
}

// ── scope and intent ─────────────────────────────────────────────────────
// A scope is what the box is about. task / ws / person: a conversation in
// the brain's own folder that opens holding that thing's context pack
// (context.py). src: a conversation inside a project's own folder, steered
// by that project's CLAUDE.md. None: the whole brain.
function normScope(s){
  if(!s) return null;
  var o = {kind: s.kind || (s.src ? 'src' : s.name ? 'person'
                           : s.task ? 'task' : 'ws')};
  ['src', 'ws', 'task', 'name'].forEach(function(k){ if(s[k]) o[k] = s[k]; });
  if(o.kind === 'src' && !o.src) return null;
  if(o.kind === 'person' && !o.name) return null;
  if((o.kind === 'task' || o.kind === 'ws') && !o.task && !o.ws) return null;
  o.label = s.label || (o.kind === 'person' ? o.name : o.kind === 'task' ? o.task
                        : o.kind === 'src' ? o.src : o.ws);
  return o;
}
function scopeSrcs(){
  if(!SCOPE) return [DEFAULT_SRC, 'brain'];
  return [SCOPE.kind === 'src' ? SCOPE.src : 'brain'];
}
function scopeKey(){
  if(!SCOPE) return 'askcid';
  return 'askcid:' + SCOPE.kind + ':' + (SCOPE.src || SCOPE.ws || '')
    + '|' + (SCOPE.task || SCOPE.name || '');
}
// Does this conversation already belong to the scope? The server titles a
// scoped conversation with its label: the task, the workstream, or
// "About <person>".
function ofScope(c){
  if(!SCOPE || SCOPE.kind === 'src') return false;
  var t = (c.topic || '').toLowerCase();
  if(SCOPE.kind === 'person') return t.indexOf('about ' + SCOPE.name.toLowerCase()) === 0;
  return t === (SCOPE.task || SCOPE.ws || '').toLowerCase();
}

var LABEL = {save: 'Just save it', update: 'Tick off what happened',
  draft: 'Draft it', investigate: 'Look into it first', question: 'Just answer',
  critic: 'Tear it apart', consult: 'Run the frameworks',
  journal: 'Private journal', later: 'Queue it for later',
  dump: 'Sort a brain dump', hide: 'Hide the names', unhide: 'Put the names back'};
// Most intents are a conversation with an instruction in front. The
// instructions are the queue's own modes (.claude/commands/queue.md), said
// once, here. Since 7 Oct only buttons that know what they want send one
// (Prepare application drafts, the security card looks into it first); in
// the box itself Claude reads the mode from her words (box_rules.py).
var PREFIX = {
  update: __ASKUPDATE__,
  draft: 'Draft this for me. Load brain/writing-rules.md first, save the draft '
    + 'in brain/drafts/ in the draft format, and show me the text here: ',
  investigate: 'Look into this and report back before changing any file: ',
  question: 'Just answer; change nothing: ',
  critic: 'Critique this with .claude/commands/critic.md, in full: verdict '
    + 'first, damage ranked, questions to close. Do not rewrite it: ',
  consult: 'Run .claude/commands/consult.md in analyze mode on this: ',
  dump: 'A brain dump. Sort all of it into the brain with the sorting rules in '
    + '.claude/commands/dump.md, lose nothing, and ask your follow-up '
    + 'questions here at the end: '
};
var HINT = {save: 'Saved to your inbox as is', update: 'What got done?',
  draft: 'Draft what, for whom?', investigate: 'Look into what?',
  question: 'Ask it anything', critic: 'Paste what you made',
  consult: 'The business question', journal: 'How did today go?',
  later: 'For the next run', dump: 'Everything on your mind',
  hide: 'Paste what has names in it, or an AI\'s answer to put them back',
  unhide: 'Paste the AI\'s answer'};

function ctxFiles(){
  return Array.prototype.filter.call(ctx.querySelectorAll('.ctxchip'), function(b){
    return b.classList.contains('on') && b.dataset.f;
  }).map(function(b){ return b.dataset.f; });
}
function ctxAll(){
  return ctx.querySelector('.ctxchip[data-f=""]').classList.contains('on');
}
function paintScope(){
  // A conversation about one thing reads that thing's pack, so the chip
  // says what it is about instead of what it reads.
  scopechip.hidden = !SCOPE;
  optreads.hidden = !!SCOPE;
  if(SCOPE){
    scopechip.className = 'scopechip on';
    scopechip.innerHTML = 'about ' + esc(SCOPE.label)
      + '<b data-clear="scope" role="button" tabindex="0" title="About everything'
      + ' instead" aria-label="Clear">&times;</b>';
  } else {
    var picked = Array.prototype.filter.call(ctx.querySelectorAll('.ctxchip.on'),
      function(b){ return b.dataset.f; }).map(function(b){ return b.textContent; });
    E('optreadsv').textContent = ctxAll() ? 'everything'
      : picked.length ? picked.join(', ') : 'nothing';
  }
  E('optmodelv').textContent = MODELNAME[modelsel.value] || modelsel.value;
  panel.querySelectorAll('.askmodelopt').forEach(function(b){
    b.classList.toggle('on', b.dataset.model === modelsel.value);
  });
  E('asktitle').textContent = CTITLE || (SCOPE ? SCOPE.label : 'Tell the brain');
  if(INTENT !== 'talk'){
    intentchip.hidden = false;
    intentchip.innerHTML = esc(LABEL[INTENT] || INTENT)
      + '<b data-clear="intent" role="button" tabindex="0" title="Back to a'
      + ' conversation" aria-label="Clear">&times;</b>';
  } else {
    intentchip.hidden = true;
  }
  // The field is narrow on a phone, beside the clip, the mic and ⋯.
  var narrow = innerWidth < 480;
  startit.hidden = !(START && window.brainStart);
  ta.placeholder = HINT[INTENT]
    || (START && window.brainStart
        ? (narrow ? 'Anything it should know?'
                  : 'Anything it should know first? Or talk it through')
        : '')
    || (SCOPE ? (narrow ? 'Ask about ' + SCOPE.label + '…'
                        : 'Ask about ' + SCOPE.label + ', or hand it a task')
              : (narrow ? 'Tell the brain…' : 'Tell the brain anything'));
  send.textContent = {save: 'Save', journal: 'Keep', later: 'Queue', hide: 'Hide',
                      unhide: 'Put back'}[INTENT] || 'Send';
  // The header line is for one thing only now: waiting on another
  // conversation. What it reads is the chip beside the box.
  sub.textContent = '';
  // Another conversation is mid-change in this folder: this one can read
  // and talk, and the next send takes over once that one finishes.
  var waiting = !!(CID && !HANDS && HOLDER);
  sub.classList.toggle('waiting', waiting);
  if(waiting)
    sub.textContent = WAITS ? 'carries on when “' + HOLDER + '” finishes'
                            : 'edits wait for “' + HOLDER + '”';
  intents.querySelectorAll('.askintent').forEach(function(b){
    b.classList.toggle('on', b.dataset.intent === INTENT);
  });
}
// Intents whose work lands in the brain's own files. A conversation inside
// a project's folder never writes to the brain, so these move to the
// brain's side of the same front, where they can.
var BRAINSIDE = {update: 1, draft: 1, dump: 1};
function setIntent(i){
  INTENT = LABEL[i] || i === 'talk' ? i : 'talk';
  if(BRAINSIDE[INTENT] && SCOPE && SCOPE.kind === 'src')
    setScope(SCOPE.ws ? {kind: 'ws', ws: SCOPE.ws, label: SCOPE.label} : null);
  paintScope();
}
function setScope(s){
  s = normScope(s);
  var same = JSON.stringify(s) === JSON.stringify(SCOPE);
  SCOPE = s;
  if(!same){
    START = null;
    CID = null; ENDED = false; HANDS = true; HOLDER = ''; WORKING = false;
    STAMP = ''; ECHO = ''; NOTE = ''; TOPIC = ''; CTITLE = ''; LAST = []; LISTKEY = '';
    docview.hidden = true;
    if(!panel.hidden){ paint([]); attach(); }
  }
  paintScope();
}
panel.addEventListener('click', function(e){
  var x = e.target.closest('[data-clear]');
  if(x){
    if(x.dataset.clear === 'scope') setScope(null);
    else setIntent('talk');
    ta.focus();
    return;
  }
  if(!menu.hidden && !e.target.closest('#askmenu') && e.target !== morebtn)
    showMenu(false);
  if(!e.target.closest('.askpop') && !e.target.closest('.askopt')) showPop(null);
});

// ── the chips beside the box, and their lists ────────────────────────────
function showPop(name){
  Object.keys(POPS).forEach(function(k){
    POPS[k].hidden = k !== name;
    CHIPS[k].setAttribute('aria-expanded', String(k === name));
  });
  if(name) showMenu(false);
}
optreads.onclick = function(e){ e.stopPropagation(); showPop(POPS.reads.hidden ? 'reads' : null); };
optmodel.onclick = function(e){ e.stopPropagation(); showPop(POPS.models.hidden ? 'models' : null); };
POPS.models.addEventListener('click', function(e){
  var b = e.target.closest('.askmodelopt'); if(!b) return;
  useModel(b.dataset.model);
  modelsel.onchange();
  showPop(null);
  paintScope();
  ta.focus();
});

// ── ⋯: how it should handle this ────────────────────────────────────────
function showMenu(on){
  if(on) showPop(null);
  menu.hidden = !on;
  morebtn.setAttribute('aria-expanded', String(on));
}
morebtn.onclick = function(e){ e.stopPropagation(); showMenu(menu.hidden); };
intents.addEventListener('click', function(e){
  var b = e.target.closest('.askintent'); if(!b) return;
  setIntent(b.dataset.intent);
  showMenu(false);
  ta.focus();
});
startit.onclick = function(){
  if(!START || !window.brainStart) return;
  startit.disabled = true;
  window.brainStart(START.text, START.ws, ta.value.trim())
    .then(function(){
      startit.disabled = false; START = null;
      done('Claude is on it. The work lands on the task and in For you.');
    })
    .catch(function(e){ startit.disabled = false; note(e.message); });
};
// A line she has not sent stays in the box from page to page: what the ✎
// note was for, until 7 Oct. Its leftover draft moves in once.
try {
  var DRAFT0 = localStorage.getItem('ask-draft') || localStorage.getItem('ramble-draft') || '';
  if(DRAFT0 && !ta.value) ta.value = DRAFT0;
  if(localStorage.getItem('ramble-draft') != null){
    localStorage.setItem('ask-draft', ta.value);
    localStorage.removeItem('ramble-draft');
  }
} catch(e){}
function keepDraft(){
  try {
    if(ta.value.trim()) localStorage.setItem('ask-draft', ta.value);
    else localStorage.removeItem('ask-draft');
  } catch(e){}
}
ta.addEventListener('input', keepDraft);
// The box grows with what is in it (8 Oct): a door's prompt landed in a
// one-line box and showed as half a clipped sentence, because only typing
// ever resized it. Past one line it takes its own row; it gives the row
// back only once emptied, or it would flick between widths as she types.
function fit(){
  var f = ta.parentNode;
  if(!ta.value.trim()) f.classList.remove('askgrow');
  ta.style.height = 'auto';
  if(ta.scrollHeight > ta.clientHeight + 2){
    f.classList.add('askgrow');
    ta.style.height = 'auto';
  }
  ta.style.height = Math.min(ta.scrollHeight + 2, Math.round(innerHeight * 0.4)) + 'px';
}
// A door's words replace the last door's (8 Oct). "Change how it works"
// pressed after "Something's wrong?" left the first prompt and its report
// in the box: the box only took a door's words when it was empty. Her own
// words never go: typed after a door's words, they stay behind the new
// ones; a line of her own stays above them.
var DOOR = kept('ask-door') || '', DOORPATHS = [];
function door(text, paths, reads){
  var v = ta.value;
  if(DOOR && v.indexOf(DOOR) >= 0) v = v.replace(DOOR, text);
  else v = v.trim() ? v.replace(/\s+$/, '') + '\n\n' + text : text;
  PATHS = PATHS.filter(function(p){ return DOORPATHS.indexOf(p) < 0; });
  DOORPATHS = paths.filter(function(p){ return PATHS.indexOf(p) < 0; });
  PATHS = PATHS.concat(DOORPATHS);
  Object.keys(reads || {}).forEach(function(p){ READS[p] = reads[p]; });
  DOOR = text; keep('ask-door', text);
  ta.value = v; keepDraft(); paintFiles();
}
function forgetDoor(){ DOOR = ''; DOORPATHS = []; keep('ask-door', null); }
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
  paintScope();
});

// ── the thread ───────────────────────────────────────────────────────────
// Where a turn landed, from the turn's own steps: the files it wrote or
// edited, said the way she would say them. Anything unnamed stays unsaid —
// a receipt that guesses is worse than none.
var PLAIN = {'workstreams.md': 'the Plate', 'people.md': 'People',
  'today.md': "today's plan", 'inbox.md': 'the inbox',
  'questions.md': 'questions for you', 'waiting.md': 'waiting on others',
  'next.md': 'the ranking', 'habits.md': 'habits', 'season.md': 'the season list',
  'goals.md': 'finish lines', 'ideas.md': 'the idea shelf',
  'decisions.md': 'decisions', 'about-me.md': 'about you', 'events.md': 'events',
  'countdowns.md': 'countdowns', 'interests.md': 'interests',
  'writing-rules.md': 'writing rules', 'config.json': 'settings',
  'plan.md': "the week's dinners", 'shopping.md': 'the shopping list',
  'routine.md': 'your routine', 'journal-trace.md': ''};
function landed(steps){
  var out = [], seen = {};
  (steps || []).forEach(function(s){
    var m = /^(Wrote|Edited) (.+)$/.exec(s.s || ''); if(!m) return;
    var f = m[2], name = PLAIN[f];
    if(name === undefined){
      if(/^\d{4}-\d{2}-\d{2}\.md$/.test(f)) name = 'your journal';
      else if(/(^|\n)status:\s*draft/.test(s.d || '')) name = 'a draft';
      // its own name: "acme 2026 10 07" read as a broken label
      else name = f;
    }
    if(!name || seen[name]) return;
    seen[name] = 1;
    out.push({name: name, verb: m[1] === 'Wrote' ? 'Saved' : 'Updated',
              path: s.f || ''});
  });
  return out;
}
function receipt(got){
  var by = {};
  got.forEach(function(g){
    var h = g.path && !PLAIN[g.path.split('/').pop()]
      ? link(g.name, g.path) : '<b>' + esc(g.name) + '</b>';
    (by[g.verb] = by[g.verb] || []).push(h);
  });
  return Object.keys(by).map(function(v){
    return v + ' ' + by[v].join(', ');
  }).join(' &middot; ');
}
// The steps a turn took, folded under the answer's opening: what it did,
// with the line it said before each, and which ones did not work.
function stepsFold(steps, label){
  var bad = steps.filter(function(s){ return s.bad; }).length;
  var d = document.createElement('details');
  d.className = 'asksteps';
  var head = (label || (steps.length + ' steps')).replace(/^worked (0m 0?)?/, 'Worked ')
    .replace(/\b1 steps\b/, '1 step');
  d.innerHTML = '<summary>' + esc(head)
    + (bad ? ' &middot; <span class="bad">' + bad + ' didn’t work</span>' : '')
    + '</summary><ol>' + steps.map(function(s){
      return '<li class="' + (s.bad ? 'bad' : '') + '">'
        + (s.say ? '<span class="say">' + esc(s.say) + '</span>' : '')
        + '<span class="did">' + (s.bad ? '<i aria-label="did not work">&#10007;</i> ' : '')
        + esc(s.s || '') + '</span></li>';
    }).join('') + '</ol>';
  return d;
}
// Her message without the note the brain adds for Claude ("[Attached — read
// it with your Read tool: /Users/…]"): the files show as files instead.
var ATT = /\n*\[Attached — read it with your Read tool: ([^\]\n]+)\]/g;
function herMsg(ev){
  var d = document.createElement('div');
  d.className = 'askmsg her';
  var files = [], m;
  ATT.lastIndex = 0;
  while((m = ATT.exec(ev.t || ''))) files.push(m[1]);
  var words = (ev.t || '').replace(ATT, '').trim();
  if(words){ var w = document.createElement('div'); w.textContent = words; d.appendChild(w); }
  if(files.length){
    var row = document.createElement('div');
    row.className = 'askatts';
    files.forEach(function(f){
      var name = f.split('/').pop();
      if(/\.(png|jpe?g|gif|webp)$/i.test(f) && CID){
        var a = document.createElement('a');
        a.className = 'askatt img'; a.href = '#'; a.dataset.p = f; a.title = name;
        a.innerHTML = '<img alt="" loading="lazy" src="/api/sessions/attachment?id='
          + encodeURIComponent(CID) + '&f=' + encodeURIComponent(f) + '">';
        row.appendChild(a);
      } else {
        var c = document.createElement('a');
        c.className = 'askatt'; c.href = '#'; c.dataset.p = f; c.title = 'Show in Finder';
        c.textContent = name;
        row.appendChild(c);
      }
    });
    d.appendChild(row);
  }
  return d;
}
var LAST = [], ECHO = '', NOTE = '';
function note(msg){ NOTE = msg || ''; paint(); }
function paint(events){
  if(events) LAST = events;
  thread.innerHTML = '';
  var shown = 0, steps = [], wlabel = '';
  if(ECHO && LAST.some(function(ev){
      return ev.k === 'her' && (ev.t || '').indexOf(ECHO) >= 0; })) ECHO = '';
  var lastAt = -1;
  LAST.forEach(function(ev, i){ if(ev.k !== 'work') lastAt = i; });
  LAST.forEach(function(ev, i){
    if(ev.k === 'work'){
      steps = steps.concat(ev.steps || []); wlabel = ev.label || ''; return;
    }
    var d = document.createElement('div');
    if(ev.k === 'her'){ steps = []; wlabel = ''; d = herMsg(ev); }
    else if(ev.k === 'claude'){
      if(steps.length){ thread.appendChild(stepsFold(steps, wlabel)); }
      d.className = 'askmsg claude';
      d.innerHTML = '<div class="askwho">Claude</div><div class="askbody">'
                    + mini(ev.t) + '</div>'
                    + '<button class="askhear" data-hear="1" title="Read this answer aloud">'
                    + '<span aria-hidden="true">&#9656;</span><span> Hear it</span></button>';
      thread.appendChild(d); shown++;
      var got = landed(steps); steps = []; wlabel = '';
      if(got.length){
        var r = document.createElement('div');
        r.className = 'askreceipt';
        r.innerHTML = receipt(got);
        thread.appendChild(r);
      }
      // A question with its answers ready: one tap sends one.
      if(i === lastAt && (ev.choices || []).length && !WORKING && !ECHO){
        var ch = document.createElement('div');
        ch.className = 'askchoices';
        ev.choices.forEach(function(c){
          var b = document.createElement('button');
          b.type = 'button'; b.className = 'askchoice'; b.textContent = c;
          b.dataset.choice = c;
          ch.appendChild(b);
        });
        thread.appendChild(ch);
      }
      return;
    }
    else if(ev.k === 'note'){
      if(steps.length){ thread.appendChild(stepsFold(steps, wlabel)); steps = []; }
      d.className = 'askmsg note'; d.textContent = ev.t;
    }
    else return;
    thread.appendChild(d); shown++;
  });
  if(ECHO){
    var h = document.createElement('div');
    h.className = 'askmsg her'; h.textContent = ECHO;
    thread.appendChild(h); shown++;
  }
  if(WORKING || ECHO){
    var w = document.createElement('div');
    w.className = 'askwork';
    w.innerHTML = '<i></i> <span class="askstep">' + esc(STEP || 'thinking…') + '</span>';
    thread.appendChild(w); shown++;
  }
  if(NOTE){
    var nd = document.createElement('div');
    nd.className = 'askmsg note'; nd.textContent = NOTE;
    thread.appendChild(nd); shown++;
  }
  if(!shown && !SCOPE){
    startbox.hidden = false;
    thread.appendChild(startbox);
  } else if(!shown){
    var e2 = document.createElement('p');
    e2.className = 'askempty';
    e2.textContent = 'Ask about ' + SCOPE.label + ', or hand it something to do. '
      + 'The answer lands here.';
    thread.appendChild(e2);
  }
  // Once a conversation is under way the box is for reading it: the Run
  // shortcuts and the plan meter step aside until a new conversation.
  panel.classList.toggle('talking', LAST.length > 0 || !!ECHO);
  thread.scrollTop = thread.scrollHeight;
}

function setLink(){
  full.href = CID ? ('sessions.html#' + encodeURIComponent(CID)) : 'sessions.html';
}

// ── the conversations list ───────────────────────────────────────────────
function ago(iso){
  var t = new Date(String(iso || '').replace(' ', 'T'));
  if(isNaN(t)) return '';
  var s = (Date.now() - t.getTime()) / 1000;
  if(s < 90) return 'just now';
  if(s < 3600) return Math.round(s / 60) + ' min ago';
  if(s < 129600) return Math.round(s / 3600) + ' h ago';
  return Math.round(s / 86400) + ' days ago';
}
function showList(on){
  list.hidden = !on;
  listbtn.classList.toggle('on', on);
}
function paintList(){
  var key = JSON.stringify([LIVE, PAST, CID]);
  if(key === LISTKEY) return;              // repainting every poll eats hovers
  LISTKEY = key;
  listitems.innerHTML = '';
  function group(label, items){
    if(!items.length) return;
    var h = document.createElement('div');
    h.className = 'asklab'; h.textContent = label;
    listitems.appendChild(h);
    items.forEach(function(c){
      var b = document.createElement('button');
      b.className = 'askitem' + (c.id === CID ? ' on' : '');
      b.dataset.id = c.id;
      var busy = c.state === 'working';
      var meta = busy ? 'working…'
        : c.state === 'ask' ? 'waiting on you'
        : ago(c.last);
      b.innerHTML = '<span class="askitop">' + esc(c.topic) + '</span>'
        + '<span class="askimeta' + (busy || c.state === 'ask' ? ' busy' : '')
        + '">' + esc(meta) + '</span>';
      listitems.appendChild(b);
    });
  }
  group('Open', LIVE);
  group('Earlier', PAST);
  if(!LIVE.length && !PAST.length){
    var p = document.createElement('div');
    p.className = 'asklab'; p.textContent = 'No conversations yet';
    listitems.appendChild(p);
  }
}
function pick(id){
  var c = LIVE.concat(PAST).filter(function(x){ return x.id === id; })[0];
  if(!c) return;
  CID = c.id; ENDED = !!c.ended; HANDS = !!c.hands; HOLDER = c.hands ? '' : (c.holder || '');
  WAITS = !!c.waits; useModel(c.model); CTITLE = c.topic || '';
  WORKING = c.state === 'working';
  STAMP = c.last || ''; ECHO = ''; NOTE = '';
  TOPIC = (!SCOPE && c._src !== DEFAULT_SRC) ? (c.topic || '') : '';
  docview.hidden = true;
  keep(scopeKey(), CID);
  setLink(); LISTKEY = ''; paintList(); paintScope();
  pull();
}
listitems.addEventListener('click', function(e){
  var b = e.target.closest('.askitem'); if(!b) return;
  pick(b.dataset.id);
  if(!panel.classList.contains('wide')) showList(false);
  ta.focus();
});
listbtn.onclick = function(){ showList(list.hidden); };

// "New conversation" ends the one the panel is attached to; the next ask
// starts a fresh one, in the same scope.
function newChat(){
  function done(){
    CID = null; ENDED = false; HANDS = true; HOLDER = ''; TOPIC = '';
    WORKING = false; STAMP = ''; ECHO = ''; NOTE = ''; WAITS = false;
    CTITLE = ''; useModel('');
    docview.hidden = true;
    keep(scopeKey(), null);
    setLink(); paint([]); paintScope();
    refresh();
    if(!panel.classList.contains('wide')) showList(false);
    ta.focus();
  }
  if(!CID || ENDED){ done(); return; }
  fetch('/api/sessions/end', {method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({id: CID})})
    .then(function(r){ return r.json().catch(function(){ return {}; }); })
    .then(function(j){
      if(j.error){ note(j.error); return; }
      done();
    })
    .catch(function(){
      note('Could not reach the brain. Is it still running?');
    });
}
listnew.onclick = newChat;
E('asknew').onclick = newChat;

// ── attachments ──────────────────────────────────────────────────────────
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
  PATHS.forEach(function(p, i){
    var d = document.createElement('span'), name = esc(p.split('/').pop());
    d.className = 'askfile';
    d.innerHTML = (READS[p]
      ? '<button type="button" class="askfileread" data-read="' + esc(READS[p])
        + '" title="Read it">' + name + '</button>'
      : '<span>' + name + '</span>') + '<b data-p="' + i + '">&times;</b>';
    filebar.appendChild(d);
  });
}
filebar.addEventListener('click', function(e){
  var r = e.target.closest('[data-read]');
  if(r){ openFile(r.dataset.read); return; }
  if(e.target.tagName !== 'B') return;
  if(e.target.dataset.p != null) PATHS.splice(+e.target.dataset.p, 1);
  else PENDING.splice(+e.target.dataset.i, 1);
  paintFiles();
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
ta.addEventListener('paste', function(e){
  var items = (e.clipboardData || {}).items || [], got = [];
  for(var i = 0; i < items.length; i++){
    if(items[i].kind === 'file'){ var f = items[i].getAsFile(); if(f) got.push(f); }
  }
  if(got.length){ e.preventDefault(); addFiles(got); }
});
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

// One fetch per source feeds the thread and the list. With no scope the list
// holds the brain's own conversations and the ones about a task or person.
function refresh(){
  var srcs = scopeSrcs();
  return Promise.all(srcs.map(function(s){
    return fetch('/api/sessions/room?src=' + encodeURIComponent(s) + '&hist=1')
      .then(function(r){ return r.json(); })
      .then(function(j){
        (j.convos || []).concat(j.history || []).forEach(function(c){ c._src = s; });
        return j;
      });
  })).then(function(js){
    var live = [], past = [];
    js.forEach(function(j){ live = live.concat(j.convos || []);
                            past = past.concat(j.history || []); });
    function newest(a, b){ return String(b.last || '').localeCompare(String(a.last || '')); }
    live.sort(newest); past.sort(newest);
    if(SCOPE && SCOPE.kind !== 'src'){
      // Scoped to a task or person: only its own conversations.
      live = live.filter(ofScope); past = past.filter(ofScope);
    }
    LIVE = live; PAST = past.slice(0, 30);
    paintList();
    return js;
  });
}

// Which conversation to show on open: one already about this scope, else the
// one she was in last time here, else (with no scope) the newest of the
// brain's own, else an empty panel ready for a first ask.
function attach(){
  return refresh()
    .then(function(){
      if(FRESH){
        // A daily update, a journal entry, a draft: its own conversation.
        // Carrying on the last one would drag an unrelated history along,
        // and every turn pays for the whole history.
        FRESH = false;
        CID = null; TOPIC = ''; CTITLE = ''; useModel(''); setLink(); paint([]); paintScope();
        return;
      }
      var saved = kept(scopeKey());
      var all = LIVE.concat(PAST);
      var c = all.filter(function(x){ return x.id === saved; })[0]
        || (SCOPE && SCOPE.kind !== 'src' ? LIVE[0] : null)
        || (!SCOPE ? LIVE.filter(function(x){ return x._src === DEFAULT_SRC; })[0] : null);
      // Opened plain, the box does not walk her back into a conversation
      // that has been quiet for hours (the bio thread from a week before
      // was reopening every time, 28 Sep). It stays in the list; a new
      // question gets a new conversation. Scoped doors still resume: a
      // task's own thread is the context she came for.
      if(c && !SCOPE && c.state !== 'working' && c.state !== 'ask'){
        var t = new Date(String(c.last || '').replace(' ', 'T'));
        if(!isNaN(t) && Date.now() - t.getTime() > 6 * 3600 * 1000) c = null;
      }
      if(c){ pick(c.id); }
      else { CID = null; TOPIC = ''; CTITLE = ''; useModel(''); setLink(); paint([]); paintScope(); }
    })
    .catch(function(){
      paint([]);
      note('The brain is not answering on this Mac. Start it and reopen this.');
    });
}

function feedTick(){
  if(!WORKING || !CID){ STEP = ''; return; }
  fetch('/api/sessions/feed?id=' + encodeURIComponent(CID))
    .then(function(r){ return r.json(); })
    .then(function(j){
      if(!j.running || !WORKING) return;
      var last = (j.steps || []).length ? j.steps[j.steps.length - 1].s : '';
      var e = j.elapsed || 0;
      var t = e >= 60 ? Math.floor(e / 60) + ' min ' + (e % 60) + 's' : e + 's';
      STEP = (last || 'thinking') + ' · ' + t;
      var el = thread.querySelector('.askstep');
      if(el) el.textContent = STEP;
    })
    .catch(function(){});
}

// ── For you and Working on ───────────────────────────────────────────────
// For you is the tray Today carries — everything the brain is waiting on her
// for — as a list of doors. Acting on an item happens where it lives.
var onApp = !!document.querySelector('.view[data-view="today"]');
function goTray(id){
  try { sessionStorage.setItem('tray-focus', id); } catch(e){}
  if(onApp){
    close();
    if(location.hash !== '#/today') location.hash = '#/today';
    else if(window.trayFocus) window.trayFocus();
  } else {
    location.href = 'index.html#/today';
  }
}
function paintTray(j){
  var items = (j && j.items) || [];
  tray.hidden = !items.length;
  if(!items.length) return;
  trayn.textContent = items.length;
  trayitems.innerHTML = '';
  items.forEach(function(it){
    var b = document.createElement('button');
    b.className = 'asktrayitem';
    b.innerHTML = '<span class="k">' + esc(it.k) + '</span><span>' + esc(it.t) + '</span>';
    b.onclick = function(){ goTray(it.id); };
    trayitems.appendChild(b);
  });
}
function trayTick(){
  fetch('/api/tray').then(function(r){ return r.json(); })
    .then(paintTray).catch(function(){ tray.hidden = true; });
}
function workTick(){
  fetch('/api/agent').then(function(r){ return r.json(); })
    .then(function(j){
      var bits = [];
      if(j.running) bits.push('Claude is working' + (j.job ? ' on ' + String(j.job).split(':')[0] : ''));
      else if(j.pending > 0) bits.push(j.pending + ' ask' + (j.pending > 1 ? 's' : '') + ' waiting to run');
      var others = LIVE.filter(function(c){ return c.state === 'working' && c.id !== CID; }).length;
      if(others) bits.push(others + ' other conversation' + (others > 1 ? 's' : '') + ' working');
      working.hidden = !bits.length;
      if(!bits.length) return;
      working.innerHTML = (j.running || others ? '<i></i>' : '')
        + '<span>' + esc(bits.join(' · ')) + '</span>'
        + '<a href="' + (onApp ? '#/hood' : 'index.html#/hood') + '">Jobs</a>';
    }).catch(function(){ working.hidden = true; });
}
working.addEventListener('click', function(e){
  if(e.target.closest('a') && onApp) close();
});
// Run: the commands she reaches for most, one tap from the box. Their own
// attribute, not data-job: page.js already answers data-job on Today, and
// both answering would start the run twice.
E('askskills').addEventListener('click', function(e){
  var b = e.target.closest('[data-skill]');
  if(!b) return;
  e.preventDefault();
  var label = b.textContent.trim();
  if(!confirm('Start Claude Code to ' + label.toLowerCase()
              + '? It runs on your Mac, on your subscription.')) return;
  function go(anyway){
    var body = {job: b.dataset.skill};
    if(anyway) body.anyway = true;
    return jpost('/api/agent', body).then(function(){
      note(label + ' is running. It shows under Working on; the report lands in Jobs.');
      workTick();
    });
  }
  go(false).catch(function(err){
    var m = (err && err.message) || String(err);
    if(/you set( for today|[.])/.test(m) && confirm(m + '\n\nRun this one anyway?')){
      go(true).catch(function(e2){ note((e2 && e2.message) || String(e2)); });
      return;
    }
    note(m);
  });
});
if(onApp && E('askskills').querySelector('.skillall'))
  E('askskills').querySelector('.skillall').setAttribute('href', '#/hood');
E('askskills').querySelector('.skillall').addEventListener('click', function(){
  if(onApp) close();
});

function poll(){
  if(TIMER) clearInterval(TIMER);
  TIMER = setInterval(function(){
    if(document.hidden || panel.hidden) return;
    TICK++;
    feedTick();
    if(TICK % 4 === 0){ workTick(); }
    if(TICK % 12 === 0){ trayTick(); }
    refresh()
      .then(function(){
        var me = LIVE.filter(function(c){ return c.id === CID; })[0];
        var was = WORKING;
        WORKING = !!(me && me.state === 'working');
        if(was && !WORKING) USED = Date.now();   // the answer landed: time to read it
        if(!WORKING) STEP = '';
        if(me){
          ENDED = false; HANDS = !!me.hands;
          var h = me.hands ? '' : (me.holder || '');
          if(h !== HOLDER || !!me.waits !== WAITS || (me.topic || '') !== CTITLE){
            HOLDER = h; WAITS = !!me.waits; CTITLE = me.topic || ''; paintScope();
          }
        }
        if(me && me.last === STAMP && was === WORKING) return;
        if(me) STAMP = me.last;
        pull();
      })
      .catch(function(){});
  }, 2200);
}

// Full screen is the same panel across the whole window, the list shown as
// a sidebar. It sticks until she shrinks it back.
function setWide(on){
  panel.classList.toggle('wide', on);
  keep('askwide', on ? '1' : null);
  widebtn.title = on ? 'Back to the side panel' : 'Full screen';
  widebtn.classList.toggle('on', on);
  showList(on);
}
widebtn.onclick = function(){ setWide(!panel.classList.contains('wide')); };

// The panel opens under the bar (ASK_CSS): how tall the bar is — on the
// map, the whole fixed strip it sits in — measured, since it differs by
// page and by skin.
function setTop(){
  var h = document.querySelector('header.top');
  if(!h) return;
  var p = h.parentElement;
  if(p && p !== document.body && getComputedStyle(p).position === 'fixed') h = p;
  document.documentElement.style.setProperty('--asktop',
    Math.max(0, Math.round(h.getBoundingClientRect().bottom)) + 'px');
}
addEventListener('resize', function(){ if(!panel.hidden) setTop(); });
// Measured only at open, a panel left open reopened on load and caught the
// bar before its styles landed: 187px tall instead of 68, so the panel and
// its shade hung halfway down the page and the page looked stuck (7 Oct).
// Measure again whenever the bar changes size, and once the page has loaded.
if('ResizeObserver' in window && document.querySelector('header.top'))
  new ResizeObserver(function(){ if(!panel.hidden) setTop(); })
    .observe(document.querySelector('header.top'));
addEventListener('load', function(){ if(!panel.hidden) setTop(); });
function open(auto){
  setTop();
  panel.hidden = false; scrim.hidden = false;
  document.body.classList.add('asking');
  keep('askon', '1');
  USED = Date.now();
  setWide(kept('askwide') === '1');
  paintScope();
  requestAnimationFrame(function(){ panel.classList.add('on'); scrim.classList.add('on'); });
  fit();
  if(auto !== true){
    ta.focus();
    ta.setSelectionRange(ta.value.length, ta.value.length);
  }
  trayTick(); workTick();
  attach().then(poll);
}
// The page's own refresh waits while the box is in use. Open is not in use:
// she leaves it open for days, and holding every refresh for as long as it
// was open showed her a two-day-old page with her ticks undone (7 Oct). In
// use is an answer coming, words or files waiting to send, or a touch in the
// last ten minutes. A reload reopens the box on the same conversation.
var USED = Date.now();
['pointerdown', 'keydown', 'wheel', 'input'].forEach(function(ev){
  panel.addEventListener(ev, function(){ USED = Date.now(); }, true);
});
window.brainAsk = {busy: function(){
  if(panel.hidden) return false;
  return WORKING || !!ta.value.trim() || FILES.length > 0 || PENDING.length > 0
      || Date.now() - USED < 10 * 60 * 1000;
}};
function close(){
  panel.classList.remove('on'); scrim.classList.remove('on');
  document.body.classList.remove('asking');
  keep('askon', null);
  showMenu(false);
  if(TIMER){ clearInterval(TIMER); TIMER = null; }
  // Only if it is still closed: reopening inside the slide-out (a door
  // clicked right after Esc) must not be hidden by the old close.
  setTimeout(function(){
    if(panel.classList.contains('on')) return;
    panel.hidden = true; scrim.hidden = true;
  }, 190);
}
// The pages reload themselves when the brain rebuilds — which is exactly
// when an answer has just landed. If one happens anyway, the conversation
// comes straight back instead of vanishing mid-read.
if(kept('askon') === '1') open(true);

// Files ride with the ask itself: the server keeps them in the brain and
// names them by full path, so a conversation in any folder can read them.
function done(msg){
  send.disabled = false;
  ta.value = ''; fit(); keepDraft(); forgetDoor();
  PENDING = []; PATHS = []; paintFiles();
  setIntent('talk');
  note(msg);
}
function jpost(path, body){
  return fetch(path, {method: 'POST', headers: {'Content-Type': 'application/json'},
                      body: JSON.stringify(body)})
    .then(function(r){ return r.text().then(function(txt){
      var j = {};
      try { j = JSON.parse(txt); } catch(e){ j = {error: txt.slice(0, 200)}; }
      if(!r.ok && !j.error) j.error = 'the brain answered ' + r.status;
      if(j.error) throw new Error(j.error);
      return j;
    }); });
}
function about(){
  if(!SCOPE) return '';
  return SCOPE.kind === 'person' ? 'About ' + SCOPE.name + ': '
    : SCOPE.kind === 'src' ? 'About the project “' + SCOPE.label + '”: '
    : 'About the workstream “' + (SCOPE.ws || SCOPE.label) + '”'
      + (SCOPE.task ? ', the task “' + SCOPE.task + '”' : '') + ': ';
}
function upload(){
  if(!PENDING.length) return Promise.resolve([]);
  return jpost('/api/upload', {files: PENDING}).then(function(j){ return j.saved || []; });
}

function ask(){
  var t = ta.value.trim();
  // Every way this can decline has to SAY so: a button that does nothing
  // in silence reads as broken.
  if(!t && !PENDING.length && !PATHS.length){ ta.focus(); return; }
  showMenu(false);
  if(INTENT === 'hide' || INTENT === 'unhide'){
    if(!t){ note(INTENT === 'hide' ? 'Paste the text first.' : 'Paste the answer first.'); return; }
    send.disabled = true;
    // One switch both ways: text carrying the placeholders the masking
    // writes ("[Person 1]") is an AI's answer coming back.
    var hiding = INTENT === 'hide' && !/\[[A-Z][A-Za-z]*(?: [A-Za-z]+)? \d+\]/.test(t);
    if(hiding){
      ANON = {text: t, keep: [], also: []};
      anonBusy('Hiding the names', 'Hiding the names on this Mac, offline',
               'About ten seconds. Nothing is sent while this runs.');
    } else {
      anonBusy('Putting the names back', 'Putting the names back, on this Mac');
    }
    return jpost(hiding ? '/api/anon/mask' : '/api/anon/unmask',
                 hiding ? ANON : {text: t})
      .then(function(j){
        // Hiding keeps the text in the box, so a detail can be cut and hidden again.
        if(hiding){ send.disabled = false; anonPreview(j); }
        else { done(''); anonRestored(j); }
      })
      .catch(function(e){
        send.disabled = false;
        anonFail(hiding ? 'Could not hide the names' : 'Could not put the names back', e.message);
      });
  }
  if(INTENT === 'save'){
    if(!t){ note('Type what to save. Attachments go with a conversation.'); return; }
    send.disabled = true;
    return jpost('/api/capture', {text: t})
      .then(function(){ done('Saved to your inbox. Claude files it on the next run.'); })
      .catch(function(e){ send.disabled = false; note(e.message); });
  }
  if(INTENT === 'journal'){
    if(!t){ note('Say how the day went first.'); return; }
    send.disabled = true;
    return jpost('/api/queue', {text: t, mode: 'journal'})
      .then(function(){ done('Kept in your journal, in your words.'); })
      .catch(function(e){ send.disabled = false; note(e.message); });
  }
  if(INTENT === 'later'){
    send.disabled = true;
    return upload().then(function(saved){
      return jpost('/api/queue', {text: about() + (t || 'See the attached files.'),
                                  mode: 'just-do-it', model: modelsel.value,
                                  files: saved.concat(PATHS)});
    }).then(function(){ done('Queued. The next queue run does it; its answer comes back in For you.'); })
      .catch(function(e){ send.disabled = false; note(e.message); });
  }
  if(WORKING){
    note('Still working on the last one. It will answer here.');
    return;
  }
  send.disabled = true;
  ECHO = t; NOTE = '';
  paint();
  var parts = [];
  if(!SCOPE){
    var files = ctxFiles();
    if(files.length)
      parts.push('For this question read ' + files.join(' and ')
                 + ' and answer from those; do not go looking through the rest '
                 + 'of the brain unless they cannot answer it.');
    else if(!ctxAll())
      parts.push('Plain chat: answer from the conversation itself, '
                 + 'without reading the brain\'s files.');
  }
  var pre = PREFIX[INTENT] || '';
  if(t || pre) parts.push(pre + (t || 'see the attached files.'));
  var body = {text: parts.join('\n\n'), model: modelsel.value || CHAT_MODEL,
              files: PENDING, paths: PATHS};
  ready().then(function(){ sendAsk(body); });
}

// A conversation picked back up from "Earlier" is ended on the server: wake
// it, and take the folder's hands back when they are free.
function ready(){
  var steps = Promise.resolve();
  if(CID && ENDED)
    steps = steps.then(function(){
      return jpost('/api/sessions/reopen', {id: CID})
        .then(function(){ ENDED = false; }).catch(function(){});
    });
  if(CID && !HANDS)
    steps = steps.then(function(){
      return jpost('/api/sessions/hands', {id: CID})
        .then(function(){ HANDS = true; }).catch(function(){});
    });
  return steps;
}

function newBody(b){
  if(!SCOPE) b.src = DEFAULT_SRC;
  else if(SCOPE.kind === 'src') b.src = SCOPE.src;
  else if(SCOPE.kind === 'person'){ b.kind = 'person'; b.name = SCOPE.name; }
  else { b.kind = 'task'; b.ws = SCOPE.ws || ''; b.task = SCOPE.task || ''; }
  return b;
}
function sendAsk(b){
  var path = CID ? '/api/sessions/say' : '/api/sessions/new';
  if(CID) b.id = CID; else newBody(b);
  jpost(path, b)
    .then(function(j){
      send.disabled = false;
      NOTE = '';
      if(j.id) CID = j.id;
      keep(scopeKey(), CID);
      setLink();
      ta.value = ''; fit(); keepDraft(); forgetDoor();
      PENDING = []; PATHS = []; paintFiles();
      setIntent('talk');
      WORKING = true; pull(); poll(); refresh();
    })
    .catch(function(e){
      send.disabled = false; ECHO = '';
      note(e.message && /fetch/i.test(e.message)
           ? 'Could not reach the brain. Is it still running?' : e.message);
    });
}

// ── Files: what the brain made ───────────────────────────────────────────
// Drafts, transcripts, guides, book notes, Word files, and what changed in
// her project folders, newest first. By id only (docs.py): the page never
// names a path. Markdown the brain keeps can be edited here; everything
// opens in its own app or shows in the Finder.
function showTab(t){
  TAB = t;
  panel.querySelectorAll('.asktab').forEach(function(b){
    b.classList.toggle('on', b.dataset.tab === t); });
  convopane.hidden = t !== 'convos';
  filepane.hidden = t !== 'files';
  if(t === 'files') loadFiles();
}
panel.querySelector('.asktabs').addEventListener('click', function(e){
  var b = e.target.closest('.asktab'); if(b) showTab(b.dataset.tab);
});
function loadFiles(){
  return fetch('/api/files').then(function(r){ return r.json(); })
    .then(function(j){ FILES = j.items || []; paintFileList(); })
    .catch(function(){ fileitems.innerHTML = '<p class="asklab">Could not list the files.</p>'; });
}
function paintFileList(){
  var kinds = {};
  FILES.forEach(function(f){ kinds[f.kind] = (kinds[f.kind] || 0) + 1; });
  filekinds.innerHTML = '';
  [['', 'All']].concat(Object.keys(kinds).map(function(k){ return [k, k]; }))
    .forEach(function(kv){
      var b = document.createElement('button');
      b.className = 'askfilekind' + (kv[0] === FKIND ? ' on' : '');
      b.textContent = kv[1] + (kv[0] ? ' ' + kinds[kv[0]] : '');
      b.onclick = function(){ FKIND = kv[0]; paintFileList(); };
      filekinds.appendChild(b);
    });
  fileitems.innerHTML = '';
  var shown = FILES.filter(function(f){ return !FKIND || f.kind === FKIND; });
  if(!shown.length){
    fileitems.innerHTML = '<p class="asklab">Nothing here yet</p>'; return;
  }
  shown.slice(0, 120).forEach(function(f){
    var b = document.createElement('button');
    b.className = 'askfile2' + (f.id === DOCID ? ' on' : '');
    b.innerHTML = '<span class="askitop">' + esc(f.name) + '</span>'
      + '<span class="askimeta">' + esc([f.kind, f.where, f.when].filter(Boolean).join(' · '))
      + '</span>';
    b.onclick = function(){ openFile(f.id); };
    fileitems.appendChild(b);
  });
}
function fileTool(label, fn, cls){
  var b = document.createElement('button');
  b.textContent = label; if(cls) b.className = cls;
  b.onclick = fn; doctools.appendChild(b); return b;
}
function openFile(id){
  return fetch('/api/files/read?id=' + encodeURIComponent(id))
    .then(function(r){ return r.json(); })
    .then(function(f){
      if(f.error){ note(f.error); return; }
      DOCID = f.id;
      docname.textContent = f.name + (f.where ? ' · ' + f.where : '');
      // A study guide is a page of its own: shown whole, in a frame.
      docbody.innerHTML = f.html
        || (f.url ? '<iframe class="askframe" src="/' + esc(f.url) + '"></iframe>'
            : '<p class="asknoview">No preview for this kind of file. '
              + 'Open it in its own app.</p>');
      doctools.innerHTML = '';
      if(f.editable && f.raw) fileTool('Edit', function(){ editFile(f); });
      if(f.url){
        var a = document.createElement('a');
        a.href = '/' + f.url; a.target = '_blank'; a.rel = 'noopener';
        a.textContent = 'Open the page ↗'; doctools.appendChild(a);
      }
      if(f.openable && !f.url) fileTool('Open in its app', function(){ fileAct(f.id, false); });
      fileTool('Show in Finder', function(){ fileAct(f.id, true); });
      doctools.hidden = false;
      docview.hidden = false;
      docbody.scrollTop = 0;
      if(!panel.classList.contains('wide')) showList(false);
    })
    .catch(function(){ note('Could not open that file.'); });
}
function fileAct(id, reveal){
  jpost('/api/files/open', {id: id, reveal: reveal})
    .catch(function(e){ note(e.message); });
}
function editFile(f){
  docbody.innerHTML = '';
  var t = document.createElement('textarea');
  t.className = 'askedit'; t.value = f.raw; t.spellcheck = true;
  docbody.appendChild(t);
  doctools.innerHTML = '';
  fileTool('Save', function(){
    jpost('/api/files/save', {id: f.id, text: t.value})
      .then(function(){ openFile(f.id); })
      .catch(function(e){ note(e.message); });
  }, 'go');
  fileTool('Cancel', function(){ openFile(f.id); });
  t.focus();
}

// ── the ways in ──────────────────────────────────────────────────────────
// window.brainBox.open({scope, intent, text, paths}) from any page script;
// or any element carrying data-box: data-box-ws, data-box-task,
// data-box-person, data-box-src (+ data-box-label), data-box-intent,
// data-box-text, data-box-fresh.
// Also: fresh (a new conversation, not the last one), reads ({path: id}:
// attachments the reader can open).
window.brainBox = {
  open: function(o){
    o = o || {};
    setScope(o.scope || null);
    START = o.start || null;
    setIntent(o.intent || 'talk');
    FRESH = !!(o.fresh || (o.intent && o.intent !== 'talk'));
    if(o.text != null) door(o.text, o.paths || [], o.reads);
    else if(o.paths && o.paths.length){
      PATHS = PATHS.concat(o.paths.filter(function(p){ return PATHS.indexOf(p) < 0; }));
      paintFiles();
    }
    open();
    // The talk orb hands over what it cannot do itself: she already said
    // it out loud, so it goes, rather than waiting on a Send she didn't see.
    if(o.send && ta.value.trim()) setTimeout(ask, 80);
  },
  close: close,
  // One conversation, by id: the voice's "Open in the box" for the work a
  // spoken update, ramble or request started.
  openConvo: function(id){
    setScope(null); setIntent('talk');
    open(true);
    refresh().then(function(){ pick(id); }).catch(function(){});
  },
  // One file from the list, open in the reader (For you's Open button).
  openFile: function(id){
    if(panel.hidden) open(true);
    showTab('files');
    openFile(id);
  }
};
document.addEventListener('click', function(ev){
  var of = ev.target.closest && ev.target.closest('[data-openfile]');
  if(of){
    ev.preventDefault(); ev.stopPropagation();
    window.brainBox.openFile(of.dataset.openfile);
    return;
  }
  var b = ev.target.closest && ev.target.closest('[data-box]');
  if(!b) return;
  ev.preventDefault(); ev.stopPropagation();
  var d = b.dataset, scope = null;
  if(d.boxSrc) scope = {kind: 'src', src: d.boxSrc, label: d.boxLabel};
  else if(d.boxPerson) scope = {kind: 'person', name: d.boxPerson};
  else if(d.boxTask) scope = {kind: 'task', ws: d.boxWs || '', task: d.boxTask};
  else if(d.boxWs) scope = {kind: 'ws', ws: d.boxWs, label: d.boxLabel};
  window.brainBox.open({scope: scope, intent: d.boxIntent || 'talk',
                        text: d.boxText || null, fresh: d.boxFresh != null});
}, true);

var btn = document.getElementById('askopen');
// The bar's ✦ Ask opens the box, and closes it again: with the panel under
// the bar now, the button stays in reach while it is open.
if(btn) btn.onclick = function(){ panel.hidden ? window.brainBox.open({}) : close(); };
// One door on screen at a time (28 Sep): the ✦ in the corner shows only
// while the bar's ✦ Ask is out of sight — scrolled off, or not drawn at
// this width. Two buttons side by side opening one box read as two things.
if(fab){
  fab.onclick = function(){ window.brainBox.open({}); };
  if(btn && 'IntersectionObserver' in window){
    new IntersectionObserver(function(es){
      fab.classList.toggle('near', es[es.length - 1].isIntersecting);
    }).observe(btn);
  } else if(!btn) fab.classList.remove('near');
}
// The corner column gathers the page's other floating buttons — Today's
// ramble, the tour's ? — once every script has made its own. None of them
// has to know where the others are.
// On a phone they stand in the bar instead, just before ✦ Ask (28 Sep): a
// phone has no strip beside the text to keep clear, so at rest the column
// sat on the right edge of the words. --barbottom tells ramble's note
// where to open, under them.
var PHONEBAR = window.matchMedia ? matchMedia('(max-width:760px)') : null;
function gather(){
  var st = document.getElementById('fabstack');
  if(!st) return;
  var tour = document.querySelector('.btour-btn'),
      hacts = PHONEBAR && PHONEBAR.matches
        ? document.querySelector('header.top .hacts') : null;
  var home = hacts || st, at;
  if(hacts){
    at = document.getElementById('askopen');
    if(!at || at.parentNode !== hacts) at = hacts.firstChild;
  } else {
    at = document.getElementById('askfab');
    if(!at || at.parentNode !== st) at = null;
  }
  if(tour) home.insertBefore(tour, at);
  var top = document.querySelector('header.top');
  if(top) document.documentElement.style.setProperty('--barbottom',
    Math.round(top.getBoundingClientRect().height) + 'px');
}
if(document.readyState === 'loading') document.addEventListener('DOMContentLoaded', gather);
else setTimeout(gather, 0);
if(PHONEBAR){
  if(PHONEBAR.addEventListener) PHONEBAR.addEventListener('change', gather);
  else if(PHONEBAR.addListener) PHONEBAR.addListener(gather);
}
// It ducks while the page scrolls and comes back half a second after.
(function(){
  var st = document.getElementById('fabstack'), t = null, y = window.scrollY || 0;
  if(!st) return;
  window.addEventListener('scroll', function(){
    var ny = window.scrollY || 0;
    if(Math.abs(ny - y) > 4) st.classList.add('away');
    y = ny;
    if(t) clearTimeout(t);
    t = setTimeout(function(){ st.classList.remove('away'); }, 500);
  }, {passive: true});
})();
E('askx').onclick = close;
scrim.onclick = close;
send.onclick = ask;
docback.onclick = function(){ docview.hidden = true; doctools.hidden = true; DOCID = ''; };
thread.addEventListener('click', function(e){
  var c = e.target.closest('.askchoice');
  if(c){
    if(WORKING) return;
    ta.value = c.dataset.choice;
    ask();
    return;
  }
  var at = e.target.closest('.askatt');
  if(at){
    e.preventDefault();
    jpost('/api/reveal', {path: at.dataset.p, select: true})
      .catch(function(){ note('Could not show ' + at.dataset.p.split('/').pop()); });
    return;
  }
  var a = e.target.closest('.askdoc'); if(!a) return;
  e.preventDefault();
  if(a.dataset.p){
    jpost('/api/reveal', {path: a.dataset.p, select: true})
      .catch(function(){ note('Could not show ' + a.dataset.p); });
    return;
  }
  openDoc(a.dataset.f);
});
ta.addEventListener('input', fit);
ta.addEventListener('keydown', function(e){
  if(e.key === 'Enter' && !e.shiftKey){ e.preventDefault(); ask(); }
});
addEventListener('keydown', function(e){
  if((e.metaKey || e.ctrlKey) && (e.key === 'k' || e.key === 'K')){
    e.preventDefault(); panel.hidden ? window.brainBox.open({}) : close();
  }
  if(e.key === 'Escape' && !panel.hidden){
    // Esc peels the layers one at a time: the menu, an open document, the
    // list laid over the thread, then the panel itself.
    if(!menu.hidden) showMenu(false);
    else if(!docview.hidden){ docview.hidden = true; doctools.hidden = true; }
    else if(!list.hidden && !panel.classList.contains('wide')) showList(false);
    else close();
  }
});
paintScope();
})();
"""


# More opens under its own word. CSS alone could not do that everywhere:
# the links scroll sideways, a scroller clips what hangs below it, so the
# menu is anchored to the header instead — and on the map the header sits
# inside a two-tier bar, so "the header's right edge" landed below the colour
# key, nowhere near More (found 28 Sep). Measured on open instead, against
# whatever box the menu is positioned in, and kept inside the window.
NAV_JS = """
(function(){
  function place(d){
    var m = d.querySelector('.navmenu'), s = d.querySelector('summary');
    if(!m || !s) return;
    m.style.right = 'auto'; m.style.left = '0px'; m.style.top = '0px';
    var cb = (m.offsetParent || document.body).getBoundingClientRect();
    var r = s.getBoundingClientRect();
    var left = r.left - cb.left;
    var over = r.left + m.offsetWidth - (window.innerWidth - 8);
    if(over > 0) left -= over;
    m.style.left = Math.max(8 - cb.left, left) + 'px';
    m.style.top = (r.bottom - cb.top + 6) + 'px';
  }
  document.querySelectorAll('details.navmore').forEach(function(d){
    d.addEventListener('toggle', function(){ if(d.open) place(d); });
  });
  document.addEventListener('click', function(ev){
    document.querySelectorAll('details.navmore[open]').forEach(function(d){
      if(!d.contains(ev.target)) d.open = false;
    });
  });
  document.addEventListener('keydown', function(ev){
    if(ev.key !== 'Escape') return;
    document.querySelectorAll('details.navmore[open]').forEach(function(d){ d.open = false; });
  });
  window.addEventListener('resize', function(){
    document.querySelectorAll('details.navmore[open]').forEach(place);
  });
})();
"""


# ---- find anything: the graph, from the bar --------------------------------
# recall.py answers in about 30ms with no model call, so this can run while
# she is still typing. It lived in index.html's script alone; since the bar is
# the same on every page (28 Sep) it rides ask_block, which every page has.
FIND_JS = r"""
(function(){
  var box = document.getElementById('findq'),
      out = document.getElementById('findout');
  if(!box || !out) return;
  if(!/^https?:$/.test(location.protocol)){
    box.closest('.findwrap').hidden = true; return; }
  var timer = null, last = '';
  function post(path, body){
    return fetch(path, {method: 'POST', headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify(body)})
      .then(function(r){ return r.json().then(function(j){
        if(!r.ok || j.error) throw new Error(j.error || ('the brain answered ' + r.status));
        return j; }); });
  }
  function esc(t){ var d = document.createElement('div');
    d.textContent = t == null ? '' : t; return d.innerHTML; }
  function attr(t){ return esc(t).replace(/"/g, '&quot;'); }
  var cur = -1, WS = [];
  function hide(){ out.hidden = true; out.innerHTML = ''; cur = -1; }
  // It used to ask the graph, which walks out from whole names: a friend's
  // name came back as eight "<city>, based in …" rows before the friend, and
  // a teacher named only in a class file came back as nothing (8 Oct).
  // /api/find (find.py) searches the files as text, names first, and
  // each row opens the thing it names.
  //
  // Her words, marked where they landed. Accents fold one letter for one,
  // so a mark found in the folded line sits at the same place in the real one.
  function fold(t){
    return Array.prototype.map.call(String(t || ''), function(c){
      var d = c.normalize ? c.normalize('NFD').charAt(0) : c;
      return (d.toLowerCase().charAt(0) || c);
    }).join('');
  }
  function words(q){
    var ws = fold(q).split(/[^a-z0-9]+/).filter(Boolean),
        long = ws.filter(function(w){ return w.length > 1; });
    return long.length ? long : ws;
  }
  function mark(t, ws){
    t = String(t || '');
    var f = fold(t), spans = [], html = '', at = 0;
    ws.forEach(function(w){
      var re = new RegExp('(^|[^a-z0-9])(' + w.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + ')', 'g'), m;
      while((m = re.exec(f))) spans.push([m.index + m[1].length, m.index + m[0].length]);
    });
    spans.sort(function(a, b){ return a[0] - b[0]; });
    spans.forEach(function(s){
      if(s[0] < at) return;
      html += esc(t.slice(at, s[0])) + '<mark>' + esc(t.slice(s[0], s[1])) + '</mark>';
      at = s[1];
    });
    return html + esc(t.slice(at));
  }
  function row(it){
    var g = it.go || {}, a;
    if(g.file) a = 'href="#" data-openfile="' + attr(g.file) + '"';
    else if(g.person) a = 'href="index.html#/people" data-fperson="' + attr(g.person) + '"';
    else if(g.ws) a = 'href="index.html#/plate" data-fws="' + attr(g.ws) + '"';
    else a = 'href="' + (/^[a-z]+\.html(#[\w\/-]*)?$/.test(g.href || '') ? g.href : '#') + '"';
    return '<a class="fr" ' + a + '><b>' + mark(it.t, WS) + '</b><i>'
      + mark(it.s, WS) + '</i></a>';
  }
  // A person opens on their card: on People here, or on the way there.
  function personRow(name){
    var hit = null;
    document.querySelectorAll('#people .row.person').forEach(function(r){
      if(r.dataset.name !== name) return;
      if(!hit || (hit.closest('.pall') && !r.closest('.pall'))) hit = r;
    });
    return hit;
  }
  function peopleSearch(q){
    var ps = document.getElementById('psearch');
    if(!ps){ handOff({people: q}, 'index.html#/everyone'); return; }
    location.hash = '#/everyone';
    ps.value = q; ps.dispatchEvent(new Event('input'));
    setTimeout(function(){ ps.scrollIntoView({block: 'center'}); }, 150);
  }
  function goPerson(name){
    var r = personRow(name);
    if(r && window.brainReveal){ window.brainReveal(r); r.open = true; return; }
    if(document.getElementById('people')){ peopleSearch(name); return; }
    handOff({person: name}, 'index.html#/people');
  }
  // A project with no page of its own opens in the Plate's drawer.
  function goWs(name){
    var b = null;
    document.querySelectorAll('[data-wsopen]').forEach(function(x){
      if(!b && x.dataset.wsopen === name) b = x; });
    if(b){ b.click(); return; }
    try { sessionStorage.setItem('wsdrawer-open', name); } catch(e){}
    if(document.getElementById('wsdclose')) location.reload();
    else location.href = 'index.html#/plate';
  }
  function handOff(what, href){
    try { sessionStorage.setItem('find-go', JSON.stringify(what)); } catch(e){}
    location.href = href;
  }
  setTimeout(function(){
    var w = null;
    try { w = JSON.parse(sessionStorage.getItem('find-go') || 'null');
          sessionStorage.removeItem('find-go'); } catch(e){}
    if(!w || !document.getElementById('people')) return;
    if(w.person) goPerson(w.person); else if(w.people) peopleSearch(w.people);
  }, 300);
  function rowsShown(){
    // a closed fold's rows still have a box in Chrome; skip them by the fold
    return Array.prototype.filter.call(out.querySelectorAll('a.fr'), function(a){
      return !a.closest('details:not([open])'); });
  }
  function pick(i){
    var rs = rowsShown();
    if(!rs.length) return;
    cur = (i + rs.length) % rs.length;
    rs.forEach(function(a, j){ a.classList.toggle('fon', j === cur); });
    rs[cur].scrollIntoView({block: 'nearest'});
  }
  // Her writing style, to paste into another tool (2 Oct). Typing
  // "writing" or "style" finds it with its Copy buttons; the hood's card
  // carries the same buttons. Pages without the card fetch the text first,
  // so the copy itself stays inside her click.
  var STYLE_Q = /^\s*(my\s+)?(writ|style|voice|tone)/i;
  function styleRow(){
    if(!document.getElementById('wr-full'))
      fetch('/api/style').then(function(r){ return r.json(); }).then(function(j){
        [['wr-full', j.full], ['wr-short', j.short]].forEach(function(p){
          if(!p[1] || document.getElementById(p[0])) return;
          var ta = document.createElement('textarea');
          ta.id = p[0]; ta.hidden = true; ta.value = p[1];
          document.body.appendChild(ta);
        });
      }).catch(function(){});
    return '<span class="fr fstyle"><b>Your writing style</b>'
      + '<button type="button" data-wrcopy="wr-full">Copy full</button>'
      + '<button type="button" data-wrcopy="wr-short">Copy short</button>'
      + '<i>Paste-ready, for another AI. Short fits ChatGPT\u2019s custom instructions.</i></span>';
  }
  function copyText(txt){
    if(navigator.clipboard && window.isSecureContext)
      return navigator.clipboard.writeText(txt).then(function(){ return true; },
                                                     function(){ return legacy(txt); });
    return Promise.resolve(legacy(txt));
  }
  function legacy(txt){
    var ta = document.createElement('textarea');
    ta.value = txt; ta.style.position = 'fixed'; ta.style.opacity = '0';
    document.body.appendChild(ta); ta.select();
    var ok = false; try { ok = document.execCommand('copy'); } catch(e){}
    document.body.removeChild(ta);
    return ok;
  }
  document.addEventListener('click', function(ev){
    var b = ev.target.closest && ev.target.closest('[data-wrcopy]');
    if(!b) return;
    ev.preventDefault(); ev.stopPropagation();   // inside a summary: no toggle
    var src = document.getElementById(b.getAttribute('data-wrcopy')),
        label = b.getAttribute('data-label') || b.textContent;
    b.setAttribute('data-label', label);
    if(!src || !src.value){ b.textContent = 'Not ready, try again'; return; }
    copyText(src.value).then(function(ok){
      b.textContent = ok ? 'Copied \u2713' : 'Copy failed';
      setTimeout(function(){ b.textContent = label; }, 1800);
    });
  }, true);
  // Grouped by kind, the group with the best match first; five each, and
  // the rest fold open in place.
  function show(d, q){
    var html = STYLE_Q.test(q || '') ? styleRow() : '';
    WS = words(q); cur = -1;
    (d.groups || []).forEach(function(g){
      var its = g.items || [], more = its.slice(5);
      html += '<p class="fhead">' + esc(g.label) + '</p>' + its.slice(0, 5).map(row).join('');
      // People's own filter reads fewer fields than this does, so the row
      // promises the search, not a count it might not match.
      if(g.id === 'people' && g.total > 5)
        more = more.concat([{t: 'Search People for “' + q + '”', go: {people: q}}]);
      // The fold's count is the rows it opens; past the server's cap, a
      // line says how many more there are.
      var left = g.total - its.length;
      if(more.length)
        html += '<details class="fmore"><summary>'
          + (its.length > 5 ? 'Show ' + (its.length - 5) + ' more' : 'More')
          + '</summary>'
          + more.map(function(it){
              return it.go.people != null
                ? '<a class="fr" href="index.html#/everyone" data-fpeople="' + attr(q) + '"><b>'
                  + esc(it.t) + '</b></a>'
                : row(it); }).join('')
          + (left > 0 && g.id !== 'people'
             ? '<p class="fnone">' + left + ' more. Add a word to narrow it.</p>' : '')
          + '</details>';
    });
    if(!html)
      html = '<p class="fnone">Nothing in the brain on “' + esc(q) + '”.</p>'
        + '<a class="fr" href="#" data-fask="' + attr(q) + '"><b>Ask Claude</b>'
        + '<i>about \u201c' + esc(q) + '\u201d</i></a>';
    out.innerHTML = html;
    out.hidden = false;
  }
  // Capture, like the box's own file opener: it stops a data-openfile
  // click before it would bubble up to a listener on the dropdown.
  document.addEventListener('click', function(ev){
    var a = out.contains(ev.target) && ev.target.closest && ev.target.closest('a.fr');
    if(!a) return;
    var d = a.dataset;
    if(d.fperson != null){ ev.preventDefault(); goPerson(d.fperson); }
    else if(d.fpeople != null){ ev.preventDefault(); peopleSearch(d.fpeople); }
    else if(d.fws != null){ ev.preventDefault(); goWs(d.fws); }
    else if(d.fask != null){
      ev.preventDefault();
      if(window.brainBox) window.brainBox.open({text: d.fask});
    }
    // data-openfile: the box's own handler opens it in the reader
    box.blur();
    setTimeout(leave, 0);
  }, true);
  box.addEventListener('input', function(){
    var q = box.value.trim();
    if(timer) clearTimeout(timer);
    // A line starting with + is a note, not a question. Same field,
    // because in a lecture the two things she does are "where is that"
    // and "write this down", and a second box is a second thing to find.
    if(q.charAt(0) === '+'){
      out.innerHTML = '<p class="fhead">Press enter to put this in your '
        + 'inbox</p><span class="fr"><b>' + esc(q.slice(1).trim())
        + '</b><i>Claude files it on the next run</i></span>';
      out.hidden = false;
      return;
    }
    if(q.length < 2){ hide(); return; }
    timer = setTimeout(function(){
      if(q === last && !out.hidden) return; last = q;
      post('/api/find', {q: q}).then(function(d){
        if(box.value.trim() === q) show(d, q); })
        .catch(function(){ STYLE_Q.test(q) ? show({}, q) : hide(); });
    }, 120);
  });
  // Closing is leaving (8 Oct: "I cannot close the search"). Clicking away
  // used to hide the results but leave her words in an open field, and the
  // next click brought them back; a button that stops its click (the bell)
  // left the results up. So focus leaving the field closes it and empties
  // it, except a half-typed "+" note. A press on a result keeps the focus,
  // so the click lands before anything closes.
  out.addEventListener('mousedown', function(ev){ ev.preventDefault(); });
  function leave(){
    if(box.value.trim().charAt(0) !== '+'){ box.value = ''; last = ''; }
    if(timer) clearTimeout(timer);
    hide();
  }
  box.addEventListener('blur', function(){
    setTimeout(function(){ if(document.activeElement !== box && !box.disabled) leave(); }, 0);
  });
  box.addEventListener('keydown', function(ev){
    if(ev.key === 'Escape'){ box.value = ''; hide(); box.blur(); }
    if((ev.key === 'ArrowDown' || ev.key === 'ArrowUp') && !out.hidden){
      ev.preventDefault(); pick(cur + (ev.key === 'ArrowDown' ? 1 : -1)); return; }
    if(ev.key === 'Enter' && box.value.trim().charAt(0) !== '+' && !out.hidden){
      var rs = rowsShown();
      if(rs.length){ ev.preventDefault(); rs[cur >= 0 ? cur : 0].click(); }
      return;
    }
    if(ev.key === 'Enter' && box.value.trim().charAt(0) === '+'){
      var note = box.value.trim().slice(1).trim();
      if(!note) return;
      box.disabled = true;
      post('/api/capture', {text: note}).then(function(){
        box.value = ''; box.disabled = false;
        out.innerHTML = '<p class="fnone">In your inbox ✓</p>';
        setTimeout(hide, 1600); box.focus();
      }).catch(function(e){
        box.disabled = false;
        out.innerHTML = '<p class="fnone">' + esc(e.message) + '</p>';
      });
    }
  });
  document.addEventListener('click', function(ev){
    if(!out.hidden && !out.contains(ev.target) && ev.target !== box) hide();
  });
  // "/" focuses it from anywhere, unless she is already typing somewhere.
  document.addEventListener('keydown', function(ev){
    var t = ev.target || {}, tag = (t.tagName || '').toLowerCase();
    if(ev.key === '/' && tag !== 'input' && tag !== 'textarea'
       && !t.isContentEditable){ ev.preventDefault(); box.focus(); }
  });
})();
"""

# ---- the sync pill, on pages index.html's script does not drive ------------
# The same pill as Today's: when the brain last synced, and a tap syncs it
# now. After a sync the page reloads once the rebuild has landed.
PILL_JS = r"""
(function(){
  var ss = document.querySelector('#syncstate[data-lite]');
  if(!ss) return;
  var st = document.getElementById('synctext');
  if(!/^https?:$/.test(location.protocol)){ ss.classList.add('stale'); return; }
  function ago(s){
    if(s == null) return 'never';
    if(s < 90) return 'just now';
    if(s < 5400) return Math.round(s/60) + ' min ago';
    return Math.round(s/3600) + ' h ago';
  }
  function check(){
    return fetch('/api/version').then(function(r){ return r.json(); }).then(function(j){
      ss.classList.remove('stale');
      ss.classList.toggle('working', !!j.building);
      if(st) st.textContent = j.building ? 'updating…' : 'synced ' + ago(j.synced_ago);
      return j;
    }).catch(function(){
      ss.classList.add('stale');
      if(st) st.textContent = 'server gone';
    });
  }
  check();
  setInterval(function(){ if(!document.hidden) check(); }, 30000);
  ss.onclick = function(){
    if(st) st.textContent = 'syncing…';
    fetch('/api/sync', {method: 'POST', headers: {'Content-Type': 'application/json'},
                        body: '{}'}).then(function(){
      var saw = false, n = 0;
      var t = setInterval(function(){
        n++;
        check().then(function(j){
          if(j && j.building) saw = true;
          else if(saw || n > 15){ clearInterval(t); location.reload(); }
        });
      }, 1000);
    }).catch(function(){ if(st) st.textContent = 'could not sync'; });
  };
})();
"""


def chat_model():
    """Which Claude the box answers with when nobody picked one for the
    conversation: the Usage page's explicit default if she set one, else
    Sonnet (Haiku in careful mode). Until 7 Oct the box quietly defaulted to
    Haiku, and a CV for a job came out of the cheapest model."""
    import json
    import os
    here = os.path.dirname(os.path.abspath(__file__))
    try:
        with open(os.path.join(os.path.dirname(here), "config.json"),
                  encoding="utf-8") as f:
            cfg = json.load(f)
    except (OSError, ValueError):
        cfg = {}
    pick = (cfg.get("ai_features") or {}).get("model")
    if pick in ("haiku", "sonnet", "opus", "fable"):
        return pick
    return "haiku" if cfg.get("ai") == "careful" else "sonnet"


def ask_block(indent=""):
    """Panel + styles + script, ready to drop in before </body>. Carries the
    nav's script too, since every page drops this in exactly once — and the
    bar's find box and sync pill with it."""
    import md as MD
    import orb as ORB
    import activity as ACT
    import box_rules as BR
    import agents
    return ("<style>" + ASK_CSS + "</style>" + ask_html()
            + "<script>" + agents.say(ASK_JS)
            .replace("__ASKSRC__", MD.json_for_script(ASK_SRC))
            .replace("__ASKUPDATE__", MD.json_for_script(BR.RECONCILE + "What I have to say: "))
            .replace("__ASKMODEL__", MD.json_for_script(chat_model()))
            + agents.say(NAV_JS + FIND_JS + PILL_JS) + "</script>"
            + ORB.block() + ACT.block())

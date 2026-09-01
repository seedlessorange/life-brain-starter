#!/usr/bin/env python3
"""Build brain/map.html — everything you have on, as one picture, two ways.

    python3 brain/tools/map.py

GENERATED. The map has two layouts you toggle between:

  * HORIZON — every open thing placed by *when it needs you*, left to right:
    past its date, now, this week, this month, later, no date. Your rows are
    the areas of your life; birthdays and people you owe a reply sit in their
    own row. This answers "what is coming at me, and when."

  * WEB — the same work as a mind-map: each area is a hub, its workstreams
    hang off it, and whenever the ball is with a named person a line runs to
    them. This answers "what connects to what, and who is the bottleneck."

Colour is always the state (red = late, amber = they've gone quiet, blue =
you've gone quiet, terracotta = due soon, green = moving). Size is how many
open items it holds. Positions are computed here, not in the browser, so the
map looks the same every time — a map that reshuffles is one you cannot build
a memory of. The palette is the same one you chose on the brain, so the map
wears your accent too.
"""

import html
import json
import math
import os
import re
import sys
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import md as MD        # noqa: E402  (task keys, shared with the server)
import model as M
import chrome as CHROME      # noqa: E402
import build as B      # noqa: E402  (only for the shared palette)
import tour as T       # noqa: E402  (the guided walkthrough)
import talk as K       # noqa: E402  (dictation on Claude-facing inputs)

BRAIN = M.BRAIN
OUT = os.path.join(BRAIN, "map.html")

W, H = 1400, 900


def cfg():
    try:
        with open(os.path.join(BRAIN, "config.json"), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def history(days=30):
    """The map, day by day: for each of the last N days, every workstream's
    state as it stood at that day's last commit. Past days are immutable, so
    they cache forever (.map-history.json); only today is always live.
    Returns oldest-first: [{'d': 'YYYY-MM-DD', 's': {name: state}}, ...]."""
    import subprocess
    import tempfile
    from datetime import timedelta
    root = os.path.dirname(BRAIN)
    cache_fp = os.path.join(BRAIN, ".map-history.json")
    try:
        with open(cache_fp, encoding="utf-8") as f:
            cache = json.load(f)
    except Exception:
        cache = {}
    today = date.today()
    out, changed = [], False
    for i in range(days, 0, -1):                     # oldest first, today excluded
        d = (today - timedelta(days=i)).isoformat()
        if d in cache:
            out.append({"d": d, "s": cache[d]["s"]})
            continue
        try:
            commit = subprocess.run(
                ["git", "-C", root, "rev-list", "-1",
                 "--before", d + " 23:59:59", "HEAD", "--", "brain/workstreams.md"],
                capture_output=True, text=True, timeout=10).stdout.strip()
            if not commit:
                continue                             # before the brain existed
            text = subprocess.run(
                ["git", "-C", root, "show", commit + ":brain/workstreams.md"],
                capture_output=True, text=True, timeout=10).stdout
            if not text.strip():
                continue
            with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False,
                                             encoding="utf-8") as tf:
                tf.write(text)
                tmp = tf.name
            try:
                then = M.load(path=tmp, today=date.fromisoformat(d))
            finally:
                os.unlink(tmp)
            states = {w["name"]: state_of(w) for w in then if w["live"]}
            cache[d] = {"c": commit, "s": states}
            changed = True
            out.append({"d": d, "s": states})
        except Exception:
            continue                                 # a bad day never blocks the map
    if changed:
        for k in list(cache):                        # prune beyond the window
            if k < (today - timedelta(days=days)).isoformat():
                del cache[k]
                changed = True
        try:
            with open(cache_fp, "w", encoding="utf-8") as f:
                json.dump(cache, f)
        except OSError:
            pass
    return out


def past_due(w):
    """Whether a DATE has actually gone by. state_of's loudest state covers
    both real deadlines and things she marked urgent by hand, so the two have
    to be told apart before anything claims a date was missed — the drawer
    used to print "338 days past its date" about a workstream due in 2027."""
    return bool(w["overdue"] or w.get("task_overdue") or w.get("goal_overdue"))


def urgency_of(w):
    """Why this is in the loudest state, in her words. None when it isn't."""
    if w["overdue"] or w.get("task_overdue"):
        return "date"
    if w.get("goal_overdue"):
        return "goal"
    if w.get("task_urgent") or w.get("urgent_name"):
        return "urgent"
    return None


def state_of(w):
    """One function decides colour and legend, so a dot and the legend beside
    it can never disagree. Add a state here or nowhere."""
    if not w["live"]:
        return "closed"
    if w["overdue"] or w.get("task_overdue") or w.get("task_urgent") \
            or w.get("urgent_name") or w.get("goal_overdue"):
        return "overdue"
    if w["chase"]:
        return "chase"
    if w["cold"] or w["never_touched"]:
        return "cold"
    if w["due_soon"] or w.get("task_due_soon"):
        return "soon"
    if w["ball"] == "them":
        return "waiting"
    return "moving"


LEGEND = [
    # Not "Past its date": this state also covers work she marked urgent by
    # hand, and right now every dot wearing it is urgent rather than late.
    # The COLUMN called "Past its date" means only the date, so the two must
    # not share a name.
    ("overdue", "Late or urgent"),
    ("chase", "They have gone quiet"),
    ("cold", "You have gone quiet"),
    ("soon", "Due soon"),
    ("waiting", "With someone else"),
    ("moving", "Moving"),
    ("closed", "Done or dropped"),
]

# The columns are the three horizons — the same now/push/slow pools Today
# ranks from, and the same words it uses for them.
#
# They used to be calendar buckets (Past its date / Now / This week / This
# month / Later / No date). With two of sixteen workstreams carrying a date,
# that axis put nearly everything in one pile and spent 46% of the canvas on
# four empty lanes. Worse, the drawing ALREADY said the horizon — as the
# ring's dash pattern, the least readable channel it has — while position,
# the most readable, said almost nothing. This swaps them.
HCOLS = ["A clock is on it", "You chose this", "Nothing is forcing it"]
HSUB = ["the dates are doing the choosing",
        "you set a focus or a finish line",
        "it can only reach you by going stale"]
HZCOL = {"now": 0, "push": 1, "slow": 2}


# --------------------------------------------------------------------------
# geometry helpers

def horizon(items, people):
    """Place live work by time-to-due across columns, one row per area, with a
    final row for the dated people-things (owed replies, birthdays)."""
    live = [w for w in items if w["live"]]
    areas = sorted({w["area"] for w in live},
                   key=lambda a: (-sum(x["open_tasks"] for x in live if x["area"] == a),
                                  a.lower()))
    events = []
    # Owed replies: a handful of named dots, freshest first, then one
    # aggregate — ninety identical red dots said nothing except "too much".
    owed_pp = sorted((p for p in people if p.get("owed") and not p.get("oneoff")),
                     key=lambda p: (p.get("days_since")
                                    if p.get("days_since") is not None else 999))
    for p in owed_pp[:5]:
        events.append({"label": p["name"], "sub": "you owe a reply",
                       "state": "cold", "col": 0})
    if len(owed_pp) > 5:
        events.append({"label": f"+{len(owed_pp) - 5} more owed replies",
                       "sub": "the full list is on People",
                       "state": "cold", "col": 0})
    for p in people:
        if p.get("oneoff"):
            continue
        bi = p.get("bday_in")
        if bi is not None and 0 <= bi <= 45:
            # A birthday is the purest "a clock is on it" there is.
            events.append({"label": p["name"], "sub": "birthday",
                           "state": "soon", "col": 0})
    nrows = len(areas) + (1 if events else 0)

    LEFT, TOP, RIGHT, BOT = 168, 78, 40, 44
    ncol = len(HCOLS)
    rowh = (H - TOP - BOT) / max(nrows, 1)
    row_of = {a: i for i, a in enumerate(areas)}

    # ---- pass one: which column does everything fall in? Nothing is placed
    # yet, because the columns size themselves to their contents.
    def col_of(w):
        return HZCOL.get(w.get("horizon") or "slow", 2)
    per_col = [0] * ncol
    for w in live:
        per_col[col_of(w)] += 1
    for ev in events:
        per_col[ev["col"]] += 1

    # ---- proportional columns. Equal sixths made a board that is mostly
    # empty lanes with one unreadable pile — these are ordinal buckets, not
    # a linear timeline, so width can follow content. Empty columns keep a
    # slim lane (they still mean something: nothing is due this week).
    avail = W - LEFT - RIGHT
    busiest = max(per_col) or 1
    weights = [1 + 2.4 * (n / busiest) for n in per_col]
    tot_w = sum(weights)
    MINW = 118.0
    widths = [max(MINW, avail * wt / tot_w) for wt in weights]
    scale = avail / sum(widths)                  # re-fit after the minimums
    widths = [wd * scale for wd in widths]
    edges = [LEFT]
    for wd in widths:
        edges.append(edges[-1] + wd)

    def colx(ci):
        return edges[ci] + widths[ci] / 2

    def rowy(ri):
        return TOP + rowh * (ri + 0.5)

    # ---- pass two: stack, don't scatter. The golden-angle spread fanned the
    # DOTS apart but their labels (drawn underneath) still collided into an
    # unreadable pile. A cell now lays its items out in a column — sorted so
    # the most urgent sits top — wrapping into a second sub-column only when
    # the row cannot hold them.
    order = {"overdue": 0, "chase": 1, "soon": 2, "cold": 3, "moving": 4}
    seq = {}
    for w in sorted(live, key=lambda x: (order.get(state_of(x), 9),
                                         -x["open_tasks"], x["name"].lower())):
        seq.setdefault((row_of[w["area"]], col_of(w)), []).append(("ws", w))
    if events:
        eri = len(areas)
        for ev in events:
            seq.setdefault((eri, ev["col"]), []).append(("ev", ev))

    def item_h(kind, obj):
        """The vertical room one item actually needs: its own diameter plus
        the caption drawn under it. Spacing used to be a flat 34px whatever
        the dot, so two loud workstreams (r goes to 27) sat 34px apart and
        covered each other — Perch under TapGate, Ibiza under Faverolles."""
        r = node_r(obj) if kind == "ws" else 7.0
        return 2 * r + 21.0

    nodes, ev_nodes = {}, []
    for (ri, ci), group in seq.items():
        room = rowh - 26
        hs = [item_h(k, o) for k, o in group]
        # Fill a stack until the next item would not fit, then start another
        # beside it. Sized stacks, not a fixed count per stack.
        stacks, cur, cur_h = [], [], 0.0
        for idx, ih in enumerate(hs):
            if cur and cur_h + ih > room:
                stacks.append(cur)
                cur, cur_h = [], 0.0
            cur.append(idx)
            cur_h += ih
        if cur:
            stacks.append(cur)
        subw = widths[ci] / (len(stacks) + 1)
        for s_i, stack in enumerate(stacks):
            x = (edges[ci] + subw * (s_i + 1)) if len(stacks) > 1 else colx(ci)
            y = rowy(ri) - sum(hs[i] for i in stack) / 2
            for i in stack:
                kind, obj = group[i]
                cy = y + hs[i] / 2
                y += hs[i]
                if kind == "ws":
                    nodes[obj["name"]] = (round(x, 1), round(cy, 1))
                else:
                    ev_nodes.append({**obj, "x": round(x, 1), "y": round(cy, 1)})

    # Each column says what it means underneath its name. The old axis needed
    # a nudge here ("17 of 19 — tap one, then Set a date…") because an undated
    # pile was a defect it could not draw around. On this axis "nothing is
    # forcing it" is a true and useful state, not a filing error, so the nudge
    # retires.
    axis = [{"label": HCOLS[i], "x": round(colx(i), 1), "y": round(TOP - 44, 1),
             "sub": "nothing" if not per_col[i] else HSUB[i]}
            for i in range(ncol)]
    guides = [round(edges[i], 1) for i in range(1, ncol)]          # column lines
    rowlabels = [{"label": a, "x": round(LEFT - 12, 1), "y": round(rowy(i), 1)}
                 for i, a in enumerate(areas)]
    if events:
        rowlabels.append({"label": "People & dates", "x": round(LEFT - 12, 1),
                          "y": round(rowy(len(areas)), 1)})
    return nodes, ev_nodes, axis, guides, rowlabels, round(colx(0), 1)


def node_r(w):
    """A dot's radius: how loudly it is asking for you. One definition, used
    by the layout and by the renderer, so the space reserved for a node is
    the space it actually takes."""
    return round(10 + min(w.get("score") or 0, 140) / 140 * 17, 1)


def label_box(name):
    """What a caption occupies. The renderer truncates past 26 characters and
    draws at roughly 11px, so this is close enough to keep two of them apart."""
    chars = min(len(name or ""), 26)
    return max(46.0, chars * 6.1 + 10), 15.0


# The caption hangs BELOW its dot — see layoutChrome, which draws at
# y + r + 13. Reserving space around the dot's centre instead was why big
# bubbles printed straight over their own neighbours' names.
LABEL_DROP = 13.0
HALO = 7.0                      # the "in today's plan" ring sits outside r


# Where a caption may sit relative to its dot. Trying to solve dot placement
# and caption placement in one relaxation deadlocked: every push that cleared
# a caption off a dot created a new dot-on-dot overlap, and it settled into a
# local minimum with both. Separating them makes each well-behaved — pack the
# dots first, then choose each caption's side with the dots already fixed.
SIDES = ("below", "above", "right", "left")


def label_at(x, y, r, name, side):
    """Centre of the caption box for a node at (x, y) with radius r."""
    w, h = label_box(name)
    if side == "below":
        return x, y + r + LABEL_DROP, w, h
    if side == "above":
        return x, y - r - LABEL_DROP + 2, w, h
    if side == "right":
        return x + r + 8 + w / 2, y + 3, w, h
    return x - r - 8 - w / 2, y + 3, w, h


def _pack_dots(xy, rad, rounds=200):
    """Circle packing, and nothing else. Always solvable, always converges."""
    names = list(xy)
    for _ in range(rounds):
        moved = 0.0
        for i in range(len(names)):
            for j in range(i + 1, len(names)):
                a, b = names[i], names[j]
                (ax, ay), (bx, by) = xy[a], xy[b]
                dx, dy = bx - ax, by - ay
                d = math.hypot(dx, dy) or 0.01
                need = rad[a] + rad[b] + 8
                if d >= need:
                    continue
                s = (need - d) / 2 + 0.3
                ux, uy = dx / d, dy / d
                xy[a] = (ax - ux * s, ay - uy * s)
                xy[b] = (bx + ux * s, by + uy * s)
                moved += s
        for nm in names:
            x, y = xy[nm]
            xy[nm] = (min(max(x, 90.0), W - 90.0), min(max(y, 80.0), H - 70.0))
        if moved < 0.4:
            break


def _place_labels(xy, rad):
    """With the dots settled, give each caption the side that costs least.

    Biggest dots choose first — they are the ones whose caption has the
    furthest to travel, and the ones most likely to sit on somebody else.
    """
    order = sorted(xy, key=lambda nm: -rad[nm])
    taken, sides = [], {}
    for nm in order:
        x, y = xy[nm]
        best, best_cost = "below", None
        for si, side in enumerate(SIDES):
            lx, ly, lw, lh = label_at(x, y, rad[nm], nm, side)
            cost = si * 0.35                      # prefer below, then above…
            # off the canvas is worse than any overlap
            if lx - lw / 2 < 4 or lx + lw / 2 > W - 4 or ly < 10 or ly > H - 10:
                cost += 40
            for other in xy:                      # over somebody's dot?
                if other == nm:
                    continue
                ox, oy = xy[other]
                cx = min(max(ox, lx - lw / 2), lx + lw / 2)
                cy = min(max(oy, ly - lh / 2), ly + lh / 2)
                over = rad[other] + 2 - math.hypot(ox - cx, oy - cy)
                if over > 0:
                    cost += 6 + over * 0.4
            for (tx, ty, tw, th) in taken:        # over somebody's caption?
                ox = (lw + tw) / 2 - abs(tx - lx)
                oy = (lh + th) / 2 - abs(ty - ly)
                if ox > 0 and oy > 0:
                    cost += 5 + min(ox, oy) * 0.3
            if best_cost is None or cost < best_cost:
                best, best_cost = side, cost
        sides[nm] = best
        taken.append(label_at(x, y, rad[nm], nm, best))
    return sides


def _relax_labels(xy, radii=None, rounds=200):
    """Pack the dots, then place the captions. Returns each caption's side."""
    radii = radii or {}
    rad = {nm: (radii.get(nm, 12.0) + HALO) for nm in xy}
    if len(xy) < 2:
        return {nm: "below" for nm in xy}
    _pack_dots(xy, rad, rounds)
    return _place_labels(xy, rad)


def count_overlaps(xy, radii=None, sides=None):
    """Every collision still standing, by kind — so the layout has to prove
    it earned its place rather than just moving things around."""
    names = list(xy)
    radii = radii or {}
    sides = sides or {}
    rad = {nm: (radii.get(nm, 12.0) + HALO) for nm in names}
    rect = {nm: label_at(xy[nm][0], xy[nm][1], rad[nm], nm,
                         sides.get(nm, "below")) for nm in names}
    out = {"dot/dot": 0, "dot/label": 0, "label/label": 0}
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            a, b = names[i], names[j]
            (ax, ay), (bx, by) = xy[a], xy[b]
            if math.hypot(bx - ax, by - ay) < rad[a] + rad[b]:
                out["dot/dot"] += 1
            for owner, other in ((a, b), (b, a)):
                lx, ly, lw, lh = rect[owner]
                ox, oy = xy[other]
                cx = min(max(ox, lx - lw / 2), lx + lw / 2)
                cy = min(max(oy, ly - lh / 2), ly + lh / 2)
                if math.hypot(ox - cx, oy - cy) < rad[other]:
                    out["dot/label"] += 1
            lax, lay, law, lah = rect[a]
            lbx, lby, lbw, lbh = rect[b]
            if (law + lbw) / 2 - abs(lbx - lax) > 0 and (lah + lbh) / 2 - abs(lby - lay) > 0:
                out["label/label"] += 1
    return out


def web(items, people):
    """Area hubs on a ring, workstreams spiralled around each, and a person
    node wherever the ball is with someone named — with the lines to prove it."""
    live_by_area = {}
    for w in items:
        live_by_area.setdefault(w["area"], []).append(w)
    names = sorted(live_by_area, key=lambda a: (-len(live_by_area[a]), a.lower()))

    cx, cy = W / 2, H / 2
    k = len(names)
    ws_xy, hubs = {}, []

    # Wedges in proportion to what is in them. Equal angles gave a one-item
    # area the same quarter of the canvas as a six-item one, which is where
    # the big holes and the crowded corners both came from.
    weights = [math.sqrt(len(live_by_area[a])) for a in names]
    total_w = sum(weights) or 1.0
    spreads = [26 + 20 * math.sqrt(len(live_by_area[a]))
               + 1.4 * max((node_r(w) for w in live_by_area[a]), default=12)
               for a in names]
    # Push each hub out far enough that its own cluster clears the middle.
    base_ring = min(W, H) * (0.0 if k == 1 else 0.26)

    acc = 0.0
    for ci, area in enumerate(names):
        group = live_by_area[area]
        n, spread = len(group), spreads[ci]
        span = (weights[ci] / total_w) * math.tau
        ang = acc + span / 2 - math.pi / 2
        acc += span
        ring = 0.0 if k == 1 else base_ring + spread * 0.55
        gx = cx + math.cos(ang) * ring
        gy = cy + math.sin(ang) * ring * 0.80
        for i, w in enumerate(group):
            if n == 1:
                px, py = gx, gy
            else:
                # Sunflower packing: even density, no clumping. The old
                # three-radius rule (i % 3) put whole groups of nodes on the
                # same circle, which is how labels ended up stacked.
                r = spread * math.sqrt((i + 0.55) / n)
                a = i * 2.399963229728653 + ci * 0.7      # golden angle
                px, py = gx + math.cos(a) * r, gy + math.sin(a) * r * 0.86
            ws_xy[w["name"]] = (px, py)
        hubs.append({"name": area, "x": round(gx, 1), "y": round(gy, 1),
                     "laby": 0.0, "count": n,
                     "live": sum(1 for w in group if w["live"])})

    lab_sides = _relax_labels(ws_xy, {w["name"]: node_r(w) for w in items})
    for h in hubs:
        group = live_by_area[h["name"]]
        h["laby"] = round(min((ws_xy[w["name"]][1] for w in group),
                              default=h["y"]) - 26, 1)
    ws_xy = {nm: (round(x, 1), round(y, 1)) for nm, (x, y) in ws_xy.items()}

    # People the ball is with. Match ball_who to a known person where we can,
    # otherwise keep the raw name so "solicitor" still shows up.
    known = {p["name"].lower(): p["name"] for p in people}
    person_xy, person_links = {}, {}
    for w in items:
        if w["ball"] != "them" or not w["ball_who"]:
            continue
        raw = w["ball_who"].strip()
        nm = known.get(raw.lower())
        for pk, pv in known.items():
            if not nm and (raw.lower().startswith(pk) or pk.startswith(raw.lower())):
                nm = pv
        nm = nm or raw
        person_links.setdefault(nm, []).append(w["name"])
    for nm, wss in person_links.items():
        pts = [ws_xy[x] for x in wss if x in ws_xy]
        if not pts:
            continue
        ax = sum(p[0] for p in pts) / len(pts)
        ay = sum(p[1] for p in pts) / len(pts)
        # push the person outward from centre so the line reads as "beyond"
        vx, vy = ax - cx, ay - cy
        d = math.hypot(vx, vy) or 1
        person_xy[nm] = (round(ax + vx / d * 60, 1), round(ay + vy / d * 60, 1))
    return ws_xy, hubs, person_xy, person_links, lab_sides


def avatar_slug(name):
    """Must match beeper.avatar_slug / build._avatar — same person, same file."""
    import unicodedata
    s = unicodedata.normalize("NFKD", name or "").encode("ascii", "ignore").decode()
    s = re.sub(r"[^A-Za-z0-9]+", "-", s).strip("-").lower()
    return s or "x"


def dots_css(config):
    """The dots' wardrobe: appearance.dots picks one of B.DOTS. Emitted after
    the static state-colour block so the chosen palette wins the cascade;
    'clay' emits nothing and the built-in scheme shows through."""
    name = (config.get("appearance", {}) or {}).get("dots", "clay")
    light, dark = B.DOTS.get(name, B.DOTS["clay"])
    if not light:
        return ""
    lt = "".join(f"--{k}:{v};" for k, v in light.items())
    dk = "".join(f"--{k}:{v};" for k, v in dark.items())
    return (":root{" + lt + "}\n"
            ":root[data-theme=\"dark\"]{" + dk + "}\n"
            "@media (prefers-color-scheme:dark){:root:not([data-theme=\"light\"]){"
            + dk + "}}")


def circles_layout(people, config):
    """The bullseye: you at the centre, one ring per circle in closeness
    order, every person a dot at a stable angle on their ring. Crowded rings
    sit further out and stagger their dots so eighty acquaintances still read
    as a ring, not a smear."""
    order = [c["name"] for c in M.circles(config).values()
             if c["name"].lower() not in ("one-off", "oneoff")]
    groups = {}
    for p in people:
        if p.get("oneoff"):
            continue
        key = next((cn for cn in order
                    if cn.lower() == p["circle"].lower()), p["circle"])
        groups.setdefault(key, []).append(p)
    seq = [cn for cn in order if cn in groups]
    seq += [cn for cn in groups if cn not in seq]
    cx, cy = W / 2, H / 2
    rings, xy, sizes = [], {}, {}
    r = 88.0
    nring = max(len(seq), 1)
    for ri, cn in enumerate(seq):
        grp = sorted(groups[cn], key=lambda p: p["name"].lower())
        n = len(grp)
        r += 34 + min(40, 4 + n * 0.6)
        needy = sum(1 for p in grp
                    if not p.get("held") and (p["owed"] or p["overdue"]))
        # Every ring's name rides its own ellipse at its own bearing. The old
        # fix alternated them above and below, which did nothing: concentric
        # rings all share the vertical axis, so thirteen labels still landed
        # in one column at twelve and six o'clock, printing through each
        # other and through the dots. The pile-up was the axis, not the side.
        # Distinct angles cannot stack, however many circles she adds.
        ang = -math.pi / 2 + (ri + 0.5) * math.tau / nring
        lr = r + 15
        ca = math.cos(ang)
        anchor = "start" if ca > 0.28 else "end" if ca < -0.28 else "middle"
        labx = cx + ca * lr + (7 if anchor == "start" else -7 if anchor == "end" else 0)
        laby = cy + math.sin(ang) * lr * 0.94
        rings.append({"name": cn, "r": round(r, 1), "count": n, "needy": needy,
                      "labx": round(labx, 1), "laby": round(laby, 1),
                      "lanchor": anchor})
        # Crowded rings: smaller dots, wider stagger — 164 people must read
        # as a ring, not a smear.
        dot = 11 if n <= 40 else 9 if n <= 100 else 7.5
        stagger = 0 if n <= 22 else 9 if n <= 100 else 13
        for i, p in enumerate(grp):
            a = -math.pi / 2 + (i / max(n, 1)) * math.tau
            jr = r + (stagger if i % 2 else -stagger)
            xy[p["name"]] = (round(cx + math.cos(a) * jr, 1),
                             round(cy + math.sin(a) * jr * 0.94, 1))
            sizes[p["name"]] = dot
    return xy, rings, sizes


def build():
    items = M.load()
    people = M.load_people()

    hxy, ev_nodes, axis, guides, rowlabels, nowx = horizon(items, people)
    wxy, hubs, pxy, plinks, lab_sides = web(items, people)

    # Names + source folders, so a workstream node can carry its people and
    # its folder — the drill-down the panel offers.
    pnames = sorted((p["name"] for p in people if len(p["name"]) >= 3),
                    key=len, reverse=True)
    sources = (cfg().get("sources") or [])

    def ws_people(w):
        # Hand-made links first, then every field a person can hide in: the
        # name ("Respond to Tatum"), the next move ("demo for Dad"), the
        # why, the ball-holder, the tasks.
        found = list(w.get("linked_people", []))
        hay = " ".join([w["name"], w.get("ball_who") or "",
                        w.get("next_action") or "", w.get("why") or ""]
                       + [t["text"] for t in w["tasks"] if not t["done"]])
        for nm in pnames:
            if nm not in found and M.name_in(nm, hay):
                found.append(nm)
        return found[:6]

    def ws_folder(w):
        # Best match wins, not first match: "Faverolles (Burgundy)" must beat
        # the generic "House renovation" token overlap.
        wl = w["name"].lower()
        best, score = "", 0
        for s in sources:
            sl = (s.get("name") or "").lower()
            if not sl:
                continue
            sc = 0
            if sl in wl or wl in sl:
                sc = len(sl)
            else:
                toks = [t for t in re.split(r"[^a-z0-9]+", sl)
                        if len(t) > 4 and t in wl]
                sc = max((len(t) for t in toks), default=0)
            if sc > score:
                best, score = s.get("path", ""), sc
        return best

    # Each area gets its own ring colour, so which world a dot belongs to is
    # visible without reading — the fill keeps meaning state, the ring means area.
    area_names = sorted({w["area"] for w in items})
    _HUES = [25, 85, 145, 205, 265, 325, 55, 175]
    area_ring = {a: f"oklch(60% .11 {_HUES[i % len(_HUES)]})"
                 for i, a in enumerate(area_names)}

    nodes, index = [], {}
    for w in items:
        st = state_of(w)
        h = hxy.get(w["name"])
        wpos = wxy.get(w["name"])
        index[w["name"]] = len(nodes)
        nodes.append({
            "kind": "ws", "name": w["name"], "area": w["area"], "state": st,
            "ring": area_ring.get(w["area"], ""),
            "status": w["status"], "ball": w["ball"], "who": w["ball_who"],
            "open": w["open_tasks"], "due": w["due"], "touched": w["touched"],
            "next": w["next_action"], "why": w["why"],
            "people": ws_people(w), "folder": ws_folder(w),
            "done": w["done_tasks"],
            "tasks": [{"t": t["text"], "k": MD.taskkey(t["text"]),
                       "dd": t.get("due_days")}
                      for t in w["tasks"]
                      if not t["done"] and not t.get("parked")
                      and not t.get("dropped")][:8],
            "days_untouched": w["days_untouched"], "days_waiting": w["days_waiting"],
            "days_to_due": w["days_to_due"], "live": w["live"],
            # Why it is loud, so the drawer can say the true sentence. Without
            # this the panel reached for days_to_due whatever the reason, and
            # an absolute value turned "due in 338 days" into "338 days past".
            "urgency": urgency_of(w) or "",
            # Which pool it belongs to: a clock is on it, she chose it, or
            # nothing is forcing it. This is the X axis now, not the ring.
            "horizon": w.get("horizon") or "",
            # Whether a real calendar date is on it — what the ring says.
            "dated": bool(w["due"]),
            "score": round(w.get("score") or 0, 1),
            "pressed": w.get("pressed_task") or "",
            "pressed_days": w.get("pressed_act_days"),
            # Size is loudness, so the map and the ranking cannot disagree.
            # It used to be the open-task count, which made a fat, calm
            # project look more urgent than a single task leaving on Thursday.
            "r": node_r(w),
            "lside": lab_sides.get(w["name"], "below"),
            "hx": h[0] if h else None, "hy": h[1] if h else None,
            "wx": wpos[0] if wpos else None, "wy": wpos[1] if wpos else None,
        })

    edges = []
    for hub in hubs:
        for w in items:
            if w["area"] == hub["name"] and w["name"] in index:
                edges.append({"a": "area:" + hub["name"], "b": index[w["name"]],
                              "kind": "area"})
    # hub nodes
    for hub in hubs:
        index["area:" + hub["name"]] = len(nodes)
        nodes.append({"kind": "area", "name": hub["name"], "state": "hub",
                      "count": hub["count"], "live": hub["live"], "r": 6,
                      "hx": None, "hy": None, "wx": hub["x"], "wy": hub["y"],
                      "laby": hub["laby"]})
    # person nodes + waiting edges — enriched with role/company where the name
    # matches a contact, so a professional shows their title on the map too.
    by_name = {p["name"].lower(): p for p in people}

    def prof(nm):
        p = by_name.get((nm or "").lower())
        if not p:
            return "", "", ""
        rc = " at ".join(x for x in [p.get("role"), p.get("company")] if x)
        return rc, p.get("how", ""), p.get("circle", "")

    for nm, (px, py) in pxy.items():
        rc, how, circ = prof(nm)
        index["person:" + nm] = len(nodes)
        nodes.append({"kind": "person", "name": nm, "state": "waiting", "r": 9,
                      "waiting_on": plinks.get(nm, []), "rc": rc, "how": how, "circle": circ,
                      "hx": None, "hy": None, "wx": px, "wy": py})
        for wname in plinks.get(nm, []):
            if wname in index:
                edges.append({"a": "person:" + nm, "b": index[wname], "kind": "wait"})

    # Professional contacts (a role or company set) become a Network cluster in
    # the web view — your people-with-titles, not only workstreams. Empty until
    # you fill those fields in, so it simply doesn't appear before then.
    shown = {k[len("person:"):] for k in index if k.startswith("person:")}
    contacts = [p for p in people
                if (p.get("role") or p.get("company")) and not p.get("oneoff")
                and p["name"] not in shown]
    if contacts:
        # The exact centre belongs to the mascot; the Network ring sits just
        # above it so the two never collide.
        #
        # A LinkedIn export puts hundreds of people here, and drawing all of
        # them made one hairball: every contact took a spoke back to the hub,
        # so the middle of the map became a solid fan of lines with the real
        # work hidden behind it. Two rules keep it a picture:
        #   * only the ones you have a reason to see get a dot of their own —
        #     a focus flag, a circle you set, or something you owe them;
        #   * the rest are one dot that says how many.
        # Nothing is lost: the People page is the full list.
        NET_SHOWN = 18

        def _net_rank(p):
            # Whoever you have the most context on comes first: someone you
            # chose to focus on, gave a circle, owe a reply, or wrote down how
            # you met. Alphabetical is the last resort, not the rule.
            return (0 if p.get("focus") else 1,
                    0 if (p.get("circle") or "").strip() else 1,
                    0 if p.get("ball") == "Me" else 1,
                    0 if (p.get("how") or "").strip() else 1,
                    0 if (p.get("last") or p.get("met")) else 1,
                    p["name"].lower())
        contacts.sort(key=_net_rank)
        hidden_n = max(0, len(contacts) - NET_SHOWN)
        contacts = contacts[:NET_SHOWN]
        cx, cy = W / 2, H / 2 - 150
        n = len(contacts)
        spread = 20 + 12 * math.sqrt(n)
        index["area:Network"] = len(nodes)
        nodes.append({"kind": "area", "name": "Network", "state": "hub",
                      "count": n + hidden_n, "live": n + hidden_n, "r": 6,
                      "labtext": (f"Network  ({n} of {n + hidden_n})"
                                  if hidden_n else None),
                      "hx": None, "hy": None,
                      "wx": round(cx, 1), "wy": round(cy, 1),
                      "laby": round(cy - spread - 24, 1)})
        for i, p in enumerate(contacts):
            if n == 1:
                px, py = cx, cy
            else:
                a = (i / n) * math.tau
                r = spread * (0.5 + 0.5 * ((i % 3) / 2.0))
                px, py = cx + math.cos(a) * r, cy + math.sin(a) * r * 0.86
            rc = " at ".join(x for x in [p.get("role"), p.get("company")] if x)
            idx = len(nodes)
            # Smaller than a workstream on purpose: a contact you have not
            # promised anything is context, not a claim on your day.
            nodes.append({"kind": "contact", "name": p["name"], "state": "moving",
                          "r": 6, "rc": rc, "how": p.get("how", ""),
                          "circle": p.get("circle", ""),
                          "hx": None, "hy": None, "wx": round(px, 1), "wy": round(py, 1)})
            # kind "net", not "area": these spokes are drawn only while the
            # Network is the thing you are looking at. Sitting in the ring is
            # already how a contact says which cluster it belongs to.
            edges.append({"a": index["area:Network"], "b": idx, "kind": "net"})
    # Two workstreams that share a person are RELATED: draw the tissue. This
    # is what turns a star diagram into a graph — "Tatum connects the
    # trip and the demo" becomes something you can see.
    ws_ppl = {w["name"]: set(ws_people(w)) for w in items if w["live"]}
    _wsn = sorted(ws_ppl)
    for i1 in range(len(_wsn)):
        for j1 in range(i1 + 1, len(_wsn)):
            shared = ws_ppl[_wsn[i1]] & ws_ppl[_wsn[j1]]
            if shared and _wsn[i1] in index and _wsn[j1] in index:
                edges.append({"a": index[_wsn[i1]], "b": index[_wsn[j1]],
                              "kind": "kin", "who": ", ".join(sorted(shared)[:3])})

    # Today's plan, projected onto the universe: nodes in the written plan
    # get a soft halo, so the map and the morning agree in one glance.
    tmd = ""
    try:
        with open(os.path.join(BRAIN, "today.md"), encoding="utf-8") as f:
            tmd = f.read()
    except OSError:
        pass

    def _tok(s):
        return {t for t in re.findall(r"[a-zà-ÿ0-9€]+", (s or "").lower())
                if len(t) >= 4}
    plan_toks = [_tok(t) for t in
                 re.findall(r"^\s*-\s+\[ \]\s+(.*)$", tmd, re.M)]
    for n in nodes:
        if n["kind"] != "ws" or not n.get("live"):
            continue
        mine = _tok(n["name"]) | _tok(n.get("next") or "")
        for t in n.get("tasks", []):
            mine |= _tok(t["t"])
        n["today"] = any(len(mine & pt) >= 2 or any(len(x) >= 6 for x in mine & pt)
                         for pt in plan_toks)

    # The circles view: every non-one-off person as a dot on their circle's
    # ring — colour says whether the relationship needs you, a face where the
    # sync found one.
    cxy, rings, csizes = circles_layout(people, cfg())
    avdir = os.path.join(BRAIN, "avatars")
    # a tap on a face should answer "what is between us right now": the open
    # tasks that name them, and the workstreams they are part of
    wsnodes = [n for n in nodes if n["kind"] == "ws"]
    for p in people:
        pos = cxy.get(p["name"])
        if not pos:
            continue
        st = ("waiting" if p.get("held") else
              "overdue" if p["owed"] else
              "soon" if p["overdue"] else
              "cold" if p["never"] else "moving")
        av = ""
        slug = avatar_slug(p["name"])
        for ext in (".jpg", ".png", ".webp", ".gif"):
            if os.path.exists(os.path.join(avdir, slug + ext)):
                av = "avatars/" + slug + ext
                break
        ptasks, pwss = [], []
        for wn in wsnodes:
            mine = [t for t in wn["tasks"] if M.name_in(p["name"], t["t"])]
            if mine or p["name"] in wn["people"]:
                pwss.append(wn["name"])
            ptasks.extend(mine)
        nodes.append({"kind": "circ", "name": p["name"], "state": st,
                      "circle": p["circle"], "r": csizes.get(p["name"], 11),
                      "av": av,
                      "focus": p["focus"], "held": p.get("held", False),
                      "hold": p.get("hold", ""),
                      "owed": p["owed"], "pover": p["overdue"],
                      "every": p["every_label"], "days": p["days_since"],
                      "rc": " at ".join(x for x in [p.get("role"), p.get("company")] if x),
                      "how": p.get("how", ""), "where": p.get("where", ""),
                      "reach": p.get("reach", ""),
                      "bday": p.get("birthday", ""), "ball": p.get("ball", "nobody"),
                      "pwhy": p.get("why", ""),
                      "tasks": ptasks[:8], "wss": pwss[:6],
                      "hx": None, "hy": None, "wx": None, "wy": None,
                      "px": pos[0], "py": pos[1]})

    # event nodes (horizon-only)
    for ev in ev_nodes:
        nodes.append({"kind": "event", "name": ev["label"], "sub": ev["sub"],
                      "state": ev["state"], "r": 8,
                      "hx": ev["x"], "hy": ev["y"], "wx": None, "wy": None})

    # resolve edge "a" names (area:/person:) to indices
    for e in edges:
        if isinstance(e["a"], str):
            e["a"] = index[e["a"]]

    counts = {}
    for n in nodes:
        if n["kind"] == "ws":
            counts[n["state"]] = counts.get(n["state"], 0) + 1
    # The key doubles as the filter, so each chip says what it is worth doing:
    # a state with nothing in it is shown (it is still part of the key) but
    # cannot be clicked, and says so rather than looking merely broken.
    chips = []
    for k, label in LEGEND:
        n = counts.get(k, 0)
        tip = (f"Hide the {label.lower()} dots" if n
               else f"Nothing is {label.lower()} right now")
        chips.append(
            f'<button class="lg lg-{k}" data-state="{k}" '
            f'title="{html.escape(tip)}"{"" if n else " disabled"}>'
            f'<i></i>{html.escape(label)}<span class="c">{n}</span></button>')
    legend = "".join(chips)

    total_live = sum(1 for w in items if w["live"])

    # The mascot has moods: waving at an empty brain, sleeping when nothing
    # is flagged, celebrating the day Today's five all land — thinking
    # otherwise. Same art the brain page uses; the universe wears a face.
    flagged = any(w["flags"] for w in items if w["live"])
    mood = "thinking"
    if not total_live:
        mood = "waving"
    elif not flagged:
        mood = "sleeping"
    try:
        with open(os.path.join(BRAIN, ".today-five.json"), encoding="utf-8") as f:
            st5 = json.load(f)
        if st5.get("date") == date.today().isoformat() and st5.get("names"):
            pf = {p["name"]: p for p in people}
            named = [pf[n2] for n2 in st5["names"] if n2 in pf]
            if named and all(not p2["flags"] for p2 in named):
                mood = "celebrating"
    except Exception:
        pass
    mascot_name = str(cfg().get("mascot") or "")

    # The month, replayable: past days from git (cached — history is
    # immutable), today live at the end of the slider.
    hist = history()
    hist.append({"d": date.today().isoformat(),
                 "s": {w["name"]: state_of(w) for w in items if w["live"]}})

    # Your face at the centre of your universe, when you've given it one.
    me_photo = ""
    for ext in (".jpg", ".png", ".webp", ".gif"):
        if os.path.exists(os.path.join(BRAIN, "avatars", "me" + ext)):
            me_photo = "avatars/me" + ext
            break

    page = TEMPLATE
    page = page.replace("__STYLE__", (cfg().get("appearance", {}) or {}).get("style", "workroom"))
    page = page.replace("__RINGS__", json.dumps(rings))
    page = page.replace("__MEPHOTO__", json.dumps(me_photo))
    page = page.replace("__HISTORY__", json.dumps(hist))
    page = page.replace("__MOOD__", mood)
    page = page.replace("__MASCOTNAME__", json.dumps(mascot_name))
    page = page.replace("__DOTS__", dots_css(cfg()))
    page = page.replace("__DOTPALS__", json.dumps(
        {k: [lt, dk] for k, (lt, dk) in B.DOTS.items()}))
    page = page.replace("__DOTCUR__", json.dumps(
        (cfg().get("appearance", {}) or {}).get("dots", "clay")))
    page = page.replace("__NODES__", json.dumps(nodes))
    page = page.replace("__EDGES__", json.dumps(edges))
    page = page.replace("__AXIS__", json.dumps(axis))
    page = page.replace("__GUIDES__", json.dumps(guides))
    page = page.replace("__ROWLABELS__", json.dumps(rowlabels))
    page = page.replace("__NOWX__", str(nowx))
    page = page.replace("__MAPEMPTY__",
        "" if total_live else
        '<div class="mapempty"><img src="art/map.png?v=2" alt="" width="190">'
        "<p>Nothing on the map yet &mdash; add a workstream or run a brain dump, "
        "and your world draws itself here.</p></div>")
    page = page.replace("__LEGEND__", legend)
    page = page.replace("__DATE__", date.today().isoformat())
    page = page.replace("__W__", str(W)).replace("__H__", str(H))
    page = page.replace("__TOTAL__", str(total_live))
    page = page.replace("__HEADER__", CHROME.header_html(
        current="map", owner=cfg().get("owner", ""),
        right_html=(
            '<span class="modes" role="tablist" aria-label="View">'
            '<button id="m-horizon" class="on" role="tab" aria-selected="true">'
            '<svg viewBox="0 0 12 12" aria-hidden="true"><line x1="0.5" y1="6" x2="11.5" y2="6"/>'
            '<circle cx="3.5" cy="6" r="2"/><circle cx="8.5" cy="6" r="2"/></svg>'
            'Horizon</button>'
            '<button id="m-web" role="tab" aria-selected="false">'
            '<svg viewBox="0 0 12 12" aria-hidden="true"><line x1="6" y1="6" x2="10.5" y2="2"/>'
            '<line x1="6" y1="6" x2="10.8" y2="8.6"/><line x1="6" y1="6" x2="1.6" y2="9.6"/>'
            '<circle cx="6" cy="6" r="2.1"/><circle cx="10.5" cy="2" r="1.3"/>'
            '<circle cx="10.8" cy="8.6" r="1.3"/><circle cx="1.6" cy="9.6" r="1.3"/></svg>'
            'Web</button>'
            '<button id="m-circles" role="tab" aria-selected="false">'
            '<svg viewBox="0 0 12 12" aria-hidden="true"><circle cx="6" cy="6" r="5" fill="none"/>'
            '<circle cx="6" cy="6" r="2.2"/></svg>'
            'Circles</button></span>'
            '<span class="zoomers"><span class="zgrp">'
            '<button class="tool" id="zout" aria-label="Zoom out">&minus;</button>'
            '<button class="tool" id="zin" aria-label="Zoom in">+</button></span>'
            '<button class="tool" id="fit" title="Frame everything on screen">Fit</button>'
            '<button class="tool" id="dots" title="The dots’ colours — '
            'tap to try the next palette">Palette</button></span>')))
    page = page.replace("__TOUR__",
                        CHROME.ask_block() + T.map_block() + K.block())

    with open(OUT, "w", encoding="utf-8") as f:
        f.write(page)
    return OUT, total_live


TEMPLATE = """<!doctype html>
<html lang="en" data-style="__STYLE__"><head>
<script>try{var _bs=localStorage.getItem('brain-style');
if(_bs)document.documentElement.setAttribute('data-style',_bs);}catch(e){}</script>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>The map</title>
<link rel="icon" href="logo-192.png?v=5" type="image/png">
<link rel="apple-touch-icon" href="logo-180.png?v=5">
<link rel="stylesheet" href="appearance.css">
<style>
/* The map speaks in states; each maps onto the palette you already chose, so
   the accent (moving) and the warning colours stay in step with the brain. */
:root{
  --bg:var(--paper); --text:var(--ink);
  --overdue:var(--bad); --chase:var(--wait); --cold:var(--cold);
  --soon:var(--terra); --waiting:var(--faint); --moving:var(--green);
  --closed:var(--line2); --hub:var(--dim);
}
__DOTS__
*{box-sizing:border-box}
html,body{height:100%;margin:0}
body{background:var(--bg);color:var(--text);overflow:hidden;
  font:14px/1.5 var(--sans,'Schibsted',-apple-system,'Segoe UI',Roboto,sans-serif)}
/* The bar used to be one wrapping row of fifteen identically-shaped pills:
   site links, a title, a view switch, a colour key and four zoom tools, all
   the same weight, breaking wherever the window happened to end. Two tiers
   instead. The top one is where you are and what you are looking at; the
   bottom one is the colour key, which is also the filter. Neither wraps —
   the key scrolls sideways when it runs out of room, so the bar is the same
   height whatever the day's colours are. */
.bar{position:fixed;top:0;left:0;right:0;z-index:10;
  background:var(--bg);border-bottom:1px solid var(--line)}
/* The top tier IS the shared app header now — same wordmark, same links, same
   right-hand slot as every other page — with the map's view switch and zoom
   tools filling that slot. The bar itself keeps the fixed position and the
   border, so the header inside it gives both up. */
.bar>.apptop{position:static;padding:9px 14px 7px;border-bottom:0;
  background:none;-webkit-backdrop-filter:none;backdrop-filter:none}
/* a row that runs off the edge says so — a link sliced mid-word reads as
   broken, a link fading out reads as "there is more this way" */
.scrolls{-webkit-mask-image:linear-gradient(90deg,#000 calc(100% - 24px),transparent);
  mask-image:linear-gradient(90deg,#000 calc(100% - 24px),transparent)}
.bartitle{display:flex;align-items:baseline;gap:8px;flex:none}
.bartitle b{font:600 15px/1.2 var(--serif,'Literata',Georgia,serif);white-space:nowrap}
.bartitle .n{color:var(--faint);font-size:12px;white-space:nowrap}
.vr{flex:none;width:1px;height:20px;background:var(--line2);opacity:.6}
.push{flex:1 1 auto;min-width:8px}
/* The one you press lives at the front and wears the ink. Five identical
   ghost pills meant "mark it done" and "merge two people" asked for the eye
   equally, and the first is the whole reason the drawer opens. */
.pacts .tool.primary{background:var(--moving);border-color:transparent;color:var(--bg);
  font-weight:700;order:-1}
a.back,button.tool{font:inherit;font-size:13px;text-decoration:none;color:var(--text);
  background:var(--surface);border:1px solid var(--line);border-radius:9px;padding:5px 10px;cursor:pointer}
button.tool:hover{border-color:var(--dim)}
/* The three views are what the page IS; the pills to their right are mere
   tools. A sunken track, a glyph per view and a filled active segment keep
   the switcher from reading as four more buttons. */
.modes{display:inline-flex;flex:none;background:var(--sunken);
  border:1px solid var(--line2);border-radius:12px;padding:3px;gap:2px}
.modes button{display:inline-flex;align-items:center;gap:6px;font:inherit;
  font-size:13px;border:0;background:none;color:var(--dim);
  border-radius:9px;padding:6px 13px;cursor:pointer;white-space:nowrap}
.modes button svg{width:12px;height:12px;flex:none;opacity:.7;
  fill:currentColor;stroke:currentColor;stroke-width:1.1}
.modes button:hover{color:var(--ink)}
.modes button.on{background:var(--ink);color:var(--paper);font-weight:600}
.modes button.on svg{opacity:1}
/* the key / filter strip */
.barkey{display:flex;align-items:center;gap:4px;padding:0 14px 7px;
  overflow-x:auto;overflow-y:hidden;scrollbar-width:none}
.barkey::-webkit-scrollbar{display:none}
.keylab{flex:none;margin-right:4px;font-size:10px;font-weight:700;letter-spacing:.09em;
  text-transform:uppercase;color:var(--faint)}
.lg{display:inline-flex;align-items:center;gap:6px;flex:none;white-space:nowrap;
  font:inherit;font-size:12px;cursor:pointer;color:var(--dim);
  background:none;border:1px solid transparent;border-radius:999px;padding:4px 9px}
.lg:hover{background:var(--surface);border-color:var(--line);color:var(--ink)}
.lg i{width:9px;height:9px;border-radius:50%;display:inline-block;flex:none}
.lg .c{font:inherit;font-size:11px;font-weight:700;color:var(--faint)}
.lg-overdue i{background:var(--overdue)} .lg-chase i{background:var(--chase)}
.lg-cold i{background:var(--cold)} .lg-soon i{background:var(--soon)}
.lg-waiting i{background:var(--waiting)} .lg-moving i{background:var(--moving)}
.lg-closed i{background:var(--closed)}
/* hidden reads as a hollow dot, not as a faded chip you might mistake for
   an empty state — the two used to look the same */
.lg.off{color:var(--faint)}
.lg.off i{background:none;box-shadow:inset 0 0 0 1.5px var(--line2)}
.lg.off .c{text-decoration:line-through}
.lg[disabled]{opacity:.34;cursor:default}
.lg[disabled]:hover{background:none;border-color:transparent;color:var(--dim)}
.lgclear{flex:none;margin-left:4px;font:inherit;font-size:11.5px;font-weight:600;
  color:var(--moving);background:none;border:0;padding:4px 6px;cursor:pointer}
.lgclear[hidden]{display:none}
.lgclear.on{background:var(--moving);color:var(--bg);border-radius:999px;padding:4px 9px}
#svg{position:fixed;inset:0;width:100%;height:100%;cursor:grab;touch-action:none;
  transition:width .18s ease-out}
/* With room, the detail panel DOCKS as its own column and the map gives up
   the width rather than hiding underneath it — the design's fix for a panel
   that used to cover whatever you had just tapped. Narrow windows keep the
   floating panel, because there is no width to give. */
@media(min-width:1100px){
  body.docked #svg{width:calc(100% - 424px)}
  body.docked .panel{position:fixed;right:0;top:0;bottom:0;left:auto;
    width:424px;max-height:none;border-radius:0;
    border-left:1px solid var(--line);border-right:0;border-top:0;
    border-bottom:0;overflow:auto;padding:26px 24px 30px}
  body.docked .hint{display:none}
}
#svg.drag{cursor:grabbing}
.bar svg{width:16px;height:16px;flex:none}
/* A ring's name now rides its own ring rather than sitting in the margin, so
   it can land on a dot. The halo lets it punch through whatever is behind it
   instead of the two smearing together — same trick the dot captions use. */
.cl{fill:var(--faint);font-size:12px;font-weight:600;text-transform:uppercase;
  letter-spacing:.09em;text-anchor:middle;pointer-events:none;
  paint-order:stroke;stroke:var(--bg);stroke-width:4.5px;stroke-linejoin:round}
.nl{fill:var(--dim);font-size:11.5px;text-anchor:middle;pointer-events:none;paint-order:stroke;
  stroke:var(--bg);stroke-width:3px;stroke-linejoin:round}
.ax{fill:var(--ink);font-size:12.5px;font-weight:700;text-transform:uppercase;
  letter-spacing:.07em;text-anchor:middle;pointer-events:none}
/* the undated column says how big it is and how to shrink it */
.axsub{fill:var(--faint);font-size:10.5px;font-weight:600;text-anchor:middle;
  pointer-events:none;letter-spacing:.02em}
.rl{fill:var(--dim);font-size:12px;font-weight:700;text-anchor:start;pointer-events:none;paint-order:stroke;
  stroke:var(--bg);stroke-width:3px;stroke-linejoin:round}
/* the strips the axis text sits on, so panned dots slide cleanly under it */
.axbg{fill:var(--bg);opacity:.94;pointer-events:none}
.guide{stroke:var(--line);stroke-width:1;stroke-dasharray:3 6}
.nowline{stroke:var(--terra);stroke-width:1.5;opacity:.5}
.edge{stroke:var(--line2);stroke-width:1;fill:none}
.edge.wait{stroke:var(--waiting);stroke-width:1.4;stroke-dasharray:4 4;opacity:.75}
/* two workstreams that share a person — the tissue of the graph */
.edge.kin{stroke:var(--soon);stroke-width:1.2;stroke-dasharray:2 5;opacity:.55}
/* Captions sat directly on the threads and had to be decoded. A paper-coloured
   halo drawn behind the glyphs fixes it with no extra elements and no cost per
   frame — a backing rect would need a getBBox on every pan. */
text.nl,text.hub{paint-order:stroke fill;stroke:var(--paper);stroke-width:3.6px;
  stroke-linejoin:round;stroke-linecap:round}
/* Focusing one area quietens the rest rather than hiding them — the shape of
   the whole is the reason to be on this page at all. */
.stage.focusing .node:not(.infocus),
.stage.focusing .deco:not(.infocus){opacity:.16}
.stage.focusing .edge{opacity:.1 !important}
.chrome.focusing text:not(.infocus){opacity:.2}
/* A quietened dot must stop asking for you. The overdue pulse is a keyframe
   animation, and an animated opacity beats a plain declaration — a dimmed
   dot went on flashing at full strength, which is the one dot that should
   not have been the loudest thing on a dimmed canvas. */
.stage.focusing .node:not(.infocus),
.stage.nearing .node:not(.near){animation:none}
/* Tapping one dot answers the question the web view exists for: what does
   this touch? Its area, whoever is holding it up, and the work that shares a
   person with it stay lit; the rest of the universe steps back. The threads
   that survive get brighter rather than merely staying put — at .13 dashed
   they were invisible against a dimmed field. */
.stage.nearing .node:not(.near),
.stage.nearing .deco:not(.near){opacity:.12}
.stage.nearing .edge:not(.near){opacity:.05 !important}
.stage.nearing .node.near{opacity:1}
.stage.nearing .edge.near{opacity:.95 !important;stroke-width:2}
.chrome.nearing text:not(.near):not(.bl){opacity:.14}
/* A bundle's name is the answer you just asked for, so it does not get
   quietened along with the labels you didn't ask about — it was being shown
   and dimmed in the same breath, which read as a rendering fault. */
.chrome.nearing text.kinlab.lit,
.chrome.focusing text.kinlab.lit{opacity:.95}
circle.node{cursor:pointer;stroke:var(--bg);stroke-width:2}
/* today's plan projected onto the universe */
/* "in today's plan": a soft disc BEHIND the dot, not another ring around it */
.halo{fill:color-mix(in oklch, var(--moving) 22%, transparent);stroke:none;
  pointer-events:none}
/* "a real date is on it" — its own ring, with air. One state, no dashes:
   the horizon it used to encode is the X axis now. */
.hzring{fill:none;stroke:var(--text);opacity:.5;stroke-width:1.6;pointer-events:none}
/* progress worn further out again, so it reads as an arc and not a ring */
.parc{fill:none;stroke:var(--moving);opacity:.85;stroke-width:2.4;
  stroke-linecap:round;pointer-events:none}
/* a bloomed task leaf: tap to tick */
.bud{fill:var(--bg);stroke:var(--moving);stroke-width:2;cursor:pointer}
.bud.bad{stroke:var(--overdue)}
.budedge{stroke:var(--line2);stroke-width:1;stroke-dasharray:2 3}
text.bl{font:400 9.5px 'Schibsted',sans-serif;fill:var(--faint)}
/* the universe is alive — gently, and never for reduced-motion */
@media (prefers-reduced-motion: no-preference){
  .mascot.breathe{animation:breathe 5s ease-in-out infinite;
    transform-box:fill-box;transform-origin:center}
  @keyframes breathe{0%,100%{transform:scale(1)}50%{transform:scale(1.04)}}
  circle.node.ws{animation:drift 8s ease-in-out infinite alternate;
    transform-box:fill-box;transform-origin:center}
  circle.node.ws:nth-of-type(2n){animation-duration:10s;animation-delay:-4s}
  circle.node.ws:nth-of-type(3n){animation-duration:12s;animation-delay:-7s}
  @keyframes drift{from{transform:translateY(0)}to{transform:translateY(3px)}}
  circle.node.pulse{animation:drift 8s ease-in-out infinite alternate,
    pulse 2.8s ease-in-out infinite}
  @keyframes pulse{0%,100%{opacity:1}50%{opacity:.55}}
}
/* progress bar in the panel */
.pprog{position:relative;height:6px;border-radius:3px;background:var(--line);
  margin:8px 0 2px;overflow:hidden}
.pprog i{position:absolute;inset:0 auto 0 0;background:var(--moving);border-radius:3px}
.pprog span{position:absolute;right:0;top:8px;font-size:10.5px;color:var(--faint)}
.pprog{margin-bottom:16px}
.pprog[hidden]{display:none}
.pdd{margin-left:auto;font-style:normal;font-size:10.5px;color:var(--soon);white-space:nowrap}
.pdd.bad{color:var(--overdue)}
circle.node.faded{opacity:.1;pointer-events:none}
circle.hub{fill:var(--hub);opacity:.5}
circle.person{fill:var(--waiting)}
circle.event{stroke-dasharray:2 2}
.panel{position:fixed;right:14px;bottom:14px;width:320px;max-height:62vh;overflow:auto;z-index:12;
  background:var(--surface);border:1px solid var(--line);border-radius:14px;padding:14px 16px;
  box-shadow:0 4px 20px rgba(0,0,0,.13)}
.panel[hidden]{display:none}
.panel h2{margin:0 0 3px;font-size:16px}
.panel .area{color:var(--faint);font-size:11px;text-transform:uppercase;letter-spacing:.09em}
.panel dl{margin:12px 0 0;display:grid;grid-template-columns:auto 1fr;gap:5px 12px;font-size:13px}
.panel dt{color:var(--faint)} .panel dd{margin:0}
.panel .close{position:absolute;top:10px;right:12px;border:0;background:none;color:var(--faint);
  font-size:19px;cursor:pointer;line-height:1}
/* Above the agent pill (bottom-left) and clear of the replay scrub
   (bottom-centre) — at bottom:14 all three fought for the same strip. */
.hint{position:fixed;left:14px;bottom:68px;color:var(--faint);font-size:11.5px;
  z-index:11;max-width:min(620px,calc(100vw - 380px))}
/* every action answers out loud, wherever the panel is */
.mtoast{position:fixed;left:50%;transform:translateX(-50%);bottom:52px;z-index:14;
  background:var(--ink);color:var(--bg);font-size:13px;padding:9px 18px;
  border-radius:999px;opacity:0;transition:opacity .18s ease-out;pointer-events:none}
.mtoast.on{opacity:1}
/* the month, replayable */
.scrub{position:fixed;left:50%;transform:translateX(-50%);bottom:12px;z-index:12;
  display:flex;gap:10px;align-items:center;background:var(--surface);
  border:1px solid var(--line);border-radius:999px;padding:8px 16px}
.scrub[hidden]{display:none}
.scrub input{width:min(300px,38vw);accent-color:var(--moving);display:block}
/* The days that were actually about something, marked under the track: a
   workstream finished, a new one started, or a day when several changed at
   once. A bare slider made you hunt for them one drag-frame at a time. The
   marks sit BELOW the track rather than over it, so a tap on one jumps
   there without ever stealing a drag from the thumb. */
.sc-track{position:relative;display:block;padding-bottom:9px}
.sc-ticks{position:absolute;left:0;right:0;bottom:0;height:9px;pointer-events:none}
.sc-ticks button{position:absolute;bottom:1px;width:3px;height:7px;padding:0;
  border:0;border-radius:2px;background:var(--line2);cursor:pointer;
  pointer-events:auto;transform:translateX(-50%)}
.sc-ticks button:hover{background:var(--moving);height:9px}
.sc-ticks button.done{background:var(--moving)}
.sc-ticks button.on{background:var(--ink);height:9px}
.sc-lab{font-size:10px;letter-spacing:.12em;text-transform:uppercase;color:var(--faint)}
#sc-date{font-size:12px;min-width:80px;color:var(--text)}
#svg.past{filter:sepia(.22) saturate(.85)}
.ptasks{list-style:none;margin:12px 0 0;padding:10px 0 0;border-top:1px solid var(--line);
  font-size:12.5px;color:var(--dim)}
.ptasks li{padding:3px 0;display:flex;gap:8px;align-items:flex-start}
.ptick{width:16px;height:16px;min-width:16px;margin-top:1px;border:1.5px solid var(--line2);
  border-radius:5px;background:transparent;cursor:pointer;padding:0}
.ptick:hover{border-color:var(--moving)}
.flink{border:0;background:none;padding:0;font:inherit;color:var(--moving);
  cursor:pointer;text-align:left;word-break:break-all}
.flink:hover{text-decoration:underline}
/* the circles view: rings, your face, and who needs you */
.cring{fill:none;stroke:var(--line);stroke-width:1.2}
.mering{fill:var(--bg);stroke:var(--line);stroke-width:2}
.focusring{fill:none;stroke:var(--soon);stroke-width:1.6;stroke-dasharray:3 3}
.heldp{opacity:.42}
.okp{opacity:.45}
.dragghost{opacity:.95;pointer-events:none}
.cring.ringhot{stroke:var(--moving);stroke-width:2.5}
circle.node.circ{cursor:pointer}
.ptasks[hidden]{display:none}
.ppeople{display:flex;gap:5px;flex-wrap:wrap;margin-top:10px}
.ppeople[hidden]{display:none}
.pchip{font:600 11px/1 'Schibsted',sans-serif;text-decoration:none;color:var(--dim);
  border:1px solid var(--line);border-radius:999px;padding:5px 9px}
.pchip:hover{color:var(--text);border-color:var(--dim)}
.pacts{display:flex;gap:6px;flex-wrap:wrap;margin-top:12px;padding-top:10px;
  border-top:1px solid var(--line)}
.pacts[hidden]{display:none}
.pnote{margin:8px 0 0;font-size:12px;color:var(--moving)}
.pnote[hidden]{display:none}
.mapbar{position:fixed;left:14px;bottom:44px;z-index:12;display:flex;gap:9px;align-items:center;
  background:var(--surface);border:1.5px solid var(--line);border-radius:999px;
  padding:7px 8px 7px 13px;font:600 13px/1 'Schibsted',sans-serif;color:var(--dim);
  box-shadow:0 4px 20px rgba(0,0,0,.12)}
.mapbar[hidden]{display:none}
.mapempty{position:fixed;inset:0;display:flex;flex-direction:column;gap:14px;
  align-items:center;justify-content:center;text-align:center;color:var(--dim);
  font-size:14px;pointer-events:none}
.mapempty p{max-width:34ch}
.mscrim{position:fixed;inset:0;background:rgba(0,0,0,.28);z-index:19}
.mscrim[hidden]{display:none}
.mdlg{position:fixed;left:50%;top:38%;transform:translate(-50%,-50%);z-index:20;
  width:min(430px,calc(100vw - 40px));background:var(--surface);border:1.5px solid var(--line);
  border-radius:16px;padding:18px 20px;box-shadow:0 12px 40px rgba(0,0,0,.2)}
.mdlg[hidden]{display:none}
.md-title{margin:0 0 12px;font:700 16px/1.3 'Literata',Georgia,serif}
.md-field{margin:0 0 12px}
.md-field label{display:block;font:700 10.5px/1 'Schibsted',sans-serif;letter-spacing:.08em;
  text-transform:uppercase;color:var(--faint);margin:0 0 6px}
.md-field input{width:100%;font:400 14px/1.3 'Schibsted',sans-serif;padding:10px 12px;
  border:1px solid var(--line);border-radius:10px;background:var(--bg);color:var(--text);
  box-sizing:border-box}
.md-field input:focus{outline:2px solid var(--moving);outline-offset:1px;border-color:transparent}
.md-row{display:flex;gap:8px}
.md-go{font:700 13px/1 'Schibsted',sans-serif;background:var(--moving);color:var(--bg);
  border:0;border-radius:10px;padding:10px 16px;cursor:pointer}
.mapbar button{font:700 12px/1 'Schibsted',sans-serif;background:var(--moving);
  color:var(--bg);border:0;border-radius:999px;padding:7px 12px;cursor:pointer}
/* The brain at the centre is also the way back: tap it and the map returns to
   the whole thing — nothing focused, nothing filtered, everything in frame.
   The hit test is geometric (see tapAt), so this rule only has to give the
   hover its cursor and let the tooltip through. */
.mascot{pointer-events:none}
.mascot.home{pointer-events:auto;cursor:pointer}
/* which area you are looking at, and the way out of it */
.focuschip{position:fixed;left:50%;transform:translateX(-50%);top:calc(var(--barh,52px) + 10px);
  z-index:40;font:700 12px/1 'Schibsted',sans-serif;background:var(--moving);color:var(--bg);
  border:0;border-radius:999px;padding:8px 14px;cursor:pointer;box-shadow:0 4px 14px rgba(0,0,0,.18)}
.focuschip[hidden]{display:none}
/* the key: what size, ring and halo actually mean. It was never said anywhere. */
.keycard{position:fixed;right:12px;bottom:12px;z-index:38;max-width:330px;
  background:var(--surface);border:1px solid var(--line);border-radius:12px;
  padding:10px 14px 12px;font:400 12.5px/1.55 'Schibsted',sans-serif;color:var(--text);
  box-shadow:0 6px 20px rgba(0,0,0,.12)}
/* The summary carries a real close control on its right, not a word tacked
   onto the title. It used to read "What the drawing means 3 close" — a CSS
   en-dash escape that Python ate on the way out. */
.keycard summary{font-weight:700;cursor:pointer;list-style:none;color:var(--faint);
  position:relative;padding-right:34px;font-size:13px}
.keycard summary::-webkit-details-marker{display:none}
.keycard summary::after{content:"?";position:absolute;right:0;top:50%;
  transform:translateY(-50%);width:20px;height:20px;border-radius:50%;
  border:1px solid var(--line);display:grid;place-items:center;
  font-size:12px;line-height:1;opacity:.75}
.keycard[open] summary{margin-bottom:8px;color:var(--text)}
.keycard[open] summary::after{content:"\\00d7";font-size:15px}
.keycard summary:hover::after{border-color:var(--faint);opacity:1}
/* icon | what it is | what it means — the label used to wrap under itself */
.keyrow{display:grid;grid-template-columns:20px 74px 1fr;align-items:center;
  gap:9px;padding:3.5px 0}
/* The key describes ONE view. It used to be a single static block shown over
   all three, so on the circles it explained an outer arc, a soft glow and a
   curved thread that are only ever drawn on the web — and told her size meant
   urgency when on that view it means how crowded the ring is. A caption that
   describes a different picture is worse than none: she read the drawing
   through it and drew the wrong conclusion. */
.keyrow[data-off],.keysec[data-off],.keynote[data-off]{display:none}
.kr-state{border-color:var(--overdue);border-width:2.5px;opacity:1}
.kr-focus{border-color:var(--soon);border-style:dashed;opacity:1}
.kr-tint{border-color:var(--overdue);border-width:2.5px;opacity:1;
  background:color-mix(in oklch,var(--overdue) 22%,var(--bg))}
.keyrow b{font-weight:700}
.keydots{display:flex;align-items:center;gap:1px}
.keydot{border-radius:50%;background:var(--faint);flex:none}
.kd1{width:7px;height:7px}
.kd2{width:13px;height:13px}
.keyring{width:15px;height:15px;border-radius:50%;flex:none;background:transparent;
  border:1.6px solid var(--text);opacity:.55}
.keyfill{width:15px;height:15px;border-radius:50%;flex:none;background:var(--overdue);
  border:1px solid color-mix(in oklch,var(--overdue) 72%,black)}
.keyhalo{width:13px;height:13px;border-radius:50%;flex:none;background:var(--faint);
  box-shadow:0 0 0 4px color-mix(in oklab,var(--moving) 22%,transparent)}
.keyarc{width:15px;height:15px;border-radius:50%;flex:none;background:transparent;
  border:2.4px solid transparent;border-top-color:var(--moving);border-right-color:var(--moving)}
.keysec{margin:10px 0 4px;font-weight:700;font-size:11px;letter-spacing:.05em;
  text-transform:uppercase;color:var(--faint)}
.keysec:first-of-type{margin-top:4px}
.keyalts{display:block;font-size:11.5px;color:var(--faint);line-height:1.7}
.keyalts i{font-style:normal}
.keycard{max-width:340px}
.keyline{width:18px;height:8px;flex:none;border-bottom:1.6px dashed var(--soon);
  border-radius:0 0 9px 9px}
.keynote{margin:6px 0 0;font-size:11px;color:var(--faint)}
@media(max-width:720px){.keycard{display:none}}
/* the bundle's caption, at the bend of the thread */
text.kinlab{font:600 9.5px/1 'Schibsted',sans-serif;fill:var(--soon);opacity:.75;
  paint-order:stroke fill;stroke:var(--paper);stroke-width:3px;stroke-linejoin:round}
a.back.home{display:inline-flex;align-items:center;gap:5px;font-weight:600;
  background:var(--surface);border:1px solid var(--line)}
.legends{display:contents}
/* minus and plus are one control, so they are drawn as one */
.zoomers{display:flex;gap:6px;align-items:center;flex:none}
.zoomers .tool{font-size:13px;line-height:1;padding:6px 10px}
.zgrp{display:inline-flex}
.zgrp .tool{min-width:34px;font-size:16px;padding:5px 10px;border-radius:0;margin-left:-1px}
.zgrp .tool:first-child{border-radius:9px 0 0 9px;margin-left:0}
.zgrp .tool:last-child{border-radius:0 9px 9px 0}
.zgrp .tool:hover{position:relative;z-index:1}
/* A phone cannot hold the links, the view switch and four tools on one line
   without squeezing the links to nothing. So the links take a line of their
   own and the switch takes the next — and the zoom buttons go, because on a
   touch screen you pinch. Fit and Palette have no gesture, so they stay. */
@media(max-width:720px){
  .bar>.apptop{flex-wrap:wrap;padding:6px 10px 4px;gap:6px}
  .bar>.apptop>.appnav{flex:1 0 100%;order:-1;margin-left:0}
  .modes button{padding:6px 12px}
  .zgrp{display:none}
  .zoomers .tool{min-height:34px}
  .barkey{padding:0 10px 6px}
  .keylab{display:none}
  .hint{display:none}
  .panel{right:8px;left:8px;width:auto;bottom:8px;max-height:52vh}
}
""" + CHROME.NAV_CSS + CHROME.HEADER_CSS + """
</style></head><body>
<div class="bar">
  __HEADER__
  <div class="barkey">
    <span class="keylab">Showing</span>
    <span class="legends">__LEGEND__</span>
    <button class="lgclear" id="lgneedy" hidden>Only who needs you</button>
    <button class="lgclear" id="lgclear" hidden>Show all</button>
  </div>
</div>
<button id="focuschip" class="focuschip" hidden><span></span>&nbsp;&times;</button>
<details class="keycard" id="keycard" open>
  <summary>What the drawing means</summary>
  <p class="keysec" data-modes="web horizon">Every dot says four things, from the inside out</p>
  <div class="keyrow" data-modes="web horizon"><span class="keyfill"></span><b>Fill colour</b> its state &mdash; the seven colours in the bar above</div>
  <div class="keyrow" data-modes="web horizon"><span class="keydots"><span class="keydot kd1"></span><span class="keydot kd2"></span></span>
    <b>Size</b> <span>how loudly it is asking for you, the same number that ranks your day</span></div>
  <div class="keyrow" data-modes="web horizon"><span class="keyring kr-now"></span><b>Thin ring</b>
    <span>a real calendar date is on it &mdash; which column it sits in says
    what is forcing it</span></div>
  <div class="keyrow" data-modes="web horizon"><span class="keyarc"></span><b>Outer arc</b> how much of it you have finished</div>
  <p class="keysec" data-modes="web horizon">And around it</p>
  <div class="keyrow" data-modes="web horizon"><span class="keyhalo"></span><b>Soft glow</b> it is in today's plan</div>
  <div class="keyrow" data-modes="web"><span class="keyline"></span><b>Curved thread</b> two areas sharing a person &mdash; tap either end to see who</div>
  <p class="keynote" data-modes="web horizon">Which area a dot belongs to is its cluster, not its colour.
    Tap an area's name to focus it.</p>
  <p class="keysec" data-modes="circles">Every face says three things</p>
  <div class="keyrow" data-modes="circles"><span class="keyring kr-state"></span><b>Ring colour</b>
    <span>where the relationship stands &mdash; the colours in the bar above</span></div>
  <div class="keyrow" data-modes="circles"><span class="keydots"><span class="keydot kd1"></span><span class="keydot kd2"></span></span>
    <b>Size</b> <span>how crowded that circle is, nothing more &mdash; four people on a ring
    draw bigger than a hundred</span></div>
  <div class="keyrow" data-modes="circles"><span class="keyring kr-focus"></span><b>Warm dashes</b>
    <span>someone you have put focus on, so they surface sooner</span></div>
  <p class="keysec" data-modes="circles">And around it</p>
  <div class="keyrow" data-modes="circles"><span class="keyring kr-tint"></span><b>Interior</b>
    <span>their face if the sync found one, otherwise a wash of the same colour.
    Which it is says nothing about them</span></div>
  <p class="keynote" data-modes="circles">Which ring someone sits on is how close you keep them,
    and where they sit on it never moves &mdash; so you can learn where to look.</p>
</details>
<!-- Named by class as well as id: every dimming rule is written .stage/.chrome,
     and without the class none of them matched. Focusing an area has been
     toggling a class nothing selected on. -->
<svg id="svg"><g id="stage" class="stage"></g><g id="chrome" class="chrome"></g></svg>
<div class="panel" id="panel" hidden>
  <button class="close" id="close">&times;</button>
  <div class="area" id="p-area"></div><h2 id="p-name"></h2>
  <div id="p-prog" class="pprog" hidden><i></i><span id="p-progtxt"></span></div>
  <div id="p-why"></div><dl id="p-dl"></dl>
  <ul id="p-tasks" class="ptasks"></ul>
  <div id="p-people" class="ppeople"></div>
  <div id="p-pacts" class="pacts" hidden>
    <button class="tool primary" id="pp-spoke" title="You reached them — stamps today, clears any owed reply">&#10003; Spoke / replied</button>
    <button class="tool" id="pp-chat" title="Opens Beeper Desktop on your chat with them — nothing is sent">Open the chat &#8599;</button>
    <button class="tool" id="pp-hold" title="You're together — no owed replies, no rhythm, until the date you pick">Together / hold&hellip;</button>
    <button class="tool" id="pp-every" title="How often you want to reach out — overrides their circle's rhythm">Rhythm&hellip;</button>
    <button class="tool" id="pp-merge" title="Two entries, one person: notes, promises and aliases fold into the entry you keep">Merge&hellip;</button>
  </div>
  <div id="p-acts" class="pacts" hidden>
    <button class="tool" id="pa-add">+ Task</button>
    <button class="tool" id="pa-start" title="Claude does the legwork now: options researched into the task, numbers found, drafts written. It never sends anything.">&#10022; Start for me</button>
    <button class="tool" id="pa-due" title="Give it a date and it leaves the No-date pile for the timeline">Set a date&hellip;</button>
    <button class="tool" id="pa-snooze" title="Out of every list until a wake date you pick — comes back by itself">Snooze</button>
    <button class="tool" id="pa-ask">Ask Claude</button>
    <button class="tool" id="pa-scan" hidden title="Queue Claude to read this workstream's folder and propose new tasks">Read its folder</button>
    <button class="tool" id="pa-run" hidden title="One Claude Code run inside that repo, steered by its own CLAUDE.md &mdash; for an ongoing conversation, use the Sessions page">Quick run&hellip;</button>
  </div>
  <p class="pnote" id="p-note" hidden></p>
</div>
<div class="hint" id="hint">Tap a dot for detail &middot; drag to pan &middot; scroll to zoom</div>
<div class="mtoast" id="mtoast" hidden></div>
<div class="scrub" id="scrub" hidden>
  <span class="sc-lab">replay</span>
  <span class="sc-track">
    <input type="range" id="sc-r" min="0" max="0" value="0" aria-label="Which day">
    <span class="sc-ticks" id="sc-ticks"></span>
  </span>
  <b id="sc-date">today</b>
</div>
<div class="mapbar" id="mapbar" hidden>
  <span id="mb-txt"></span><button id="mb-run">Run now</button>
</div>
<div class="mscrim" id="mscrim" hidden></div>
<div class="mdlg" id="mdlg" hidden role="dialog" aria-modal="true">
  <p class="md-title" id="md-title"></p>
  <div class="md-field"><label id="md-l1" for="md-i1"></label>
    <input type="text" id="md-i1" maxlength="300" data-mic></div>
  <div class="md-field" id="md-f2" hidden><label id="md-l2" for="md-i2"></label>
    <input type="text" id="md-i2" maxlength="120"></div>
  <div class="md-row"><button class="md-go" id="md-go">Save</button>
    <button class="tool" id="md-cancel">Cancel</button></div>
</div>
__MAPEMPTY__
<script>
var NODES = __NODES__, EDGES = __EDGES__, AXIS = __AXIS__,
    GUIDES = __GUIDES__, ROWLABELS = __ROWLABELS__, NOWX = __NOWX__, WH = __H__;
var MASCOT = __MASCOTNAME__;
var RINGS = __RINGS__, MEPHOTO = __MEPHOTO__;
var DOTPALS = __DOTPALS__, DOTCUR = __DOTCUR__;
var DOTORDER = ['clay', 'berry', 'ocean', 'sunset', 'ink'];
// Trying a palette is instant (CSS vars flip in place); the choice persists
// via /api/appearance and comes back baked into every future build.
function applyDots(name){
  var pal = DOTPALS[name]; if(!pal) return;
  var root = document.documentElement;
  var dark = root.dataset.theme === 'dark' ||
    (root.dataset.theme !== 'light' &&
     matchMedia('(prefers-color-scheme: dark)').matches);
  var vals = pal[dark ? 1 : 0] || {};
  ['overdue', 'soon', 'chase', 'cold'].forEach(function(k){
    if(vals[k]) root.style.setProperty('--' + k, vals[k]);
    else root.style.removeProperty('--' + k);
  });
}
var HIST = __HISTORY__;
var SCRUB = HIST.length - 1;          // last entry = today, live
function inPast(){ return SCRUB < HIST.length - 1; }
var svg = document.getElementById('svg'), stage = document.getElementById('stage'),
    chrome = document.getElementById('chrome'), panel = document.getElementById('panel');
var NS = 'http://www.w3.org/2000/svg';
var off = {}, MODE = 'horizon';
// The dots live in `stage`, which is panned and zoomed by a transform. Every
// piece of TEXT lives in `chrome`, which is NOT transformed — its labels are
// repositioned each frame to sit over the right dot/column/row, but never
// scale. So you can zoom the map to nothing and the words stay readable, and
// the axis headers and row names stay pinned like a real chart.
var view = {tx:0, ty:0, k:1};
var KMIN = 0.12, KMAX = 4;
var ROWX = 14, LEFTSTRIP = 150;
// The toolbar wraps to two rows on narrow screens, so the axis strip cannot sit
// at a fixed y — it must start below whatever height the bar actually is.
function barH(){ var b = document.querySelector('.bar'); return (b ? b.offsetHeight : 56) + 4; }
// Anything pinned under the bar (the focus chip) reads its real height from
// here rather than a guessed constant that a two-tier bar makes wrong.
function syncBarVar(){
  var b = document.querySelector('.bar');
  document.documentElement.style.setProperty('--barh',
    (b ? b.offsetHeight : 56) + 'px');
  ['.barmain .appnav', '.barkey'].forEach(function(sel){
    var r = document.querySelector(sel);
    if(r) r.classList.toggle('scrolls', r.scrollWidth > r.clientWidth + 2);
  });
}

function el(t, attrs, text){
  var n = document.createElementNS(NS, t);
  for(var k in attrs) n.setAttribute(k, attrs[k]);
  if(text != null) n.textContent = text;
  return n;
}
function clamp(v, a, b){ return Math.max(a, Math.min(b, v)); }
function visible(n){
  if(MODE === 'horizon') return n.hx != null;
  if(MODE === 'circles') return n.px != null;
  return n.wx != null;
}
function nx(n){ return MODE === 'horizon' ? n.hx : MODE === 'circles' ? n.px : n.wx; }
function ny(n){ return MODE === 'horizon' ? n.hy : MODE === 'circles' ? n.py : n.wy; }
function hasLabel(n){
  return true;   // every dot says what it is — hunting via hover was the complaint
}
function ctext(cls, txt, type, wx, wy, o, anchor){
  var t = el('text', {'class':cls}, txt);
  t.dataset.type = type; t.dataset.wx = wx; t.dataset.wy = wy; t.dataset.o = o || 0;
  if(anchor) t.setAttribute('text-anchor', anchor);
  chrome.appendChild(t); return t;
}

function draw(){
  stage.innerHTML = ''; chrome.innerHTML = '';
  if(MODE === 'circles'){
    // the bullseye: rings in closeness order, you at the centre
    var defs = el('defs', {});
    var cp = el('clipPath', {id: 'cclip', clipPathUnits: 'objectBoundingBox'});
    cp.appendChild(el('circle', {cx: 0.5, cy: 0.5, r: 0.5}));
    defs.appendChild(cp); stage.appendChild(defs);
    RINGS.forEach(function(rg){
      var rel = el('ellipse', {cx: __W__/2, cy: __H__/2,
        rx: rg.r, ry: rg.r * 0.94, 'class': 'cring'});
      rel.dataset.ring = rg.name;
      stage.appendChild(rel);
      ctext('cl', rg.name + ' \\u00b7 ' + rg.count
            + (rg.needy ? ' \\u00b7 ' + rg.needy + ' need you' : ''),
            'hub', rg.labx, rg.laby, 0, rg.lanchor);
    });
    var cmasc;
    if(MEPHOTO){
      stage.appendChild(el('circle', {cx: __W__/2, cy: __H__/2, r: 42, 'class': 'mering'}));
      cmasc = el('image', {href: MEPHOTO + '?v=1',
        x: __W__/2 - 40, y: __H__/2 - 40, width: 80, height: 80,
        preserveAspectRatio: 'xMidYMid slice',
        'clip-path': 'url(#cclip)', 'class': 'mascot home'});
    } else {
      cmasc = el('image', {href: 'art/__MOOD__.png?v=2',
        x: __W__/2 - 40, y: __H__/2 - 40, width: 80, height: 80,
        'class': 'mascot breathe home'});
    }
    cmasc.appendChild(el('title', {}, 'Back to the whole map'));
    stage.appendChild(cmasc);
    if(MASCOT || !MEPHOTO)
      ctext('cl', MASCOT || 'you', 'hub', __W__/2, __H__/2 + 56, 0, 'middle');
  } else if(MODE === 'horizon'){
    GUIDES.forEach(function(x, i){
      stage.appendChild(el('line', {x1:x, y1:44, x2:x, y2:WH-30,
        // Every divider is a plain guide now. The first one used to be drawn
        // as a "now line" because the axis was a timeline and that edge was
        // today. On a horizon axis no column edge is a moment.
        'class': 'guide'})); });
    // sticky strips behind the axis text so dots scroll cleanly underneath
    var cb = el('rect', {'class':'axbg'}); cb.dataset.type = 'colbg'; chrome.appendChild(cb);
    var rb = el('rect', {'class':'axbg'}); rb.dataset.type = 'rowbg'; chrome.appendChild(rb);
    AXIS.forEach(function(a){
      ctext('ax', a.label, 'col', a.x, 0, 0, 'middle');
      // the undated pile explains itself, and says how to empty it
      if(a.sub) ctext('axsub', a.sub, 'colsub', a.x, 0, 0, 'middle');
    });
    ROWLABELS.forEach(function(r){ ctext('rl', r.label, 'row', 0, r.y, 0, 'start'); });
  } else {
    EDGES.forEach(function(e){
      var a = NODES[e.a], b = NODES[e.b];
      if(!a || !b || a.wx == null || b.wx == null || off[b.state]) return;
      // The Network's spokes only exist while you are looking at the Network.
      // Drawn always, forty lines into one point sat on top of everything.
      if(e.kind === 'net' && FOCUS !== 'Network') return;
      // Both ends written on the line, so selecting a dot can find every
      // thread that touches it without walking the graph again per frame.
      stage.appendChild(el('line', {x1:a.wx, y1:a.wy, x2:b.wx, y2:b.wy,
                                    'data-ea':e.a, 'data-eb':e.b,
                                    'class':'edge' + (e.kind === 'wait' ? ' wait' : '')}));
    });
    // Relatedness: two workstreams sharing a person. Every such link between
    // the same PAIR of areas is routed through one shared waypoint, so eight
    // separate threads crossing the canvas become one visible relationship
    // between Business and Dad. Bundling first, then draw.
    var hubOf = {}, waypoints = {};
    NODES.forEach(function(n){ if(n.kind === 'area') hubOf[n.name] = n; });
    EDGES.forEach(function(e2){
      if(e2.kind !== 'kin') return;
      var a = NODES[e2.a], b = NODES[e2.b];
      if(!a || !b || a.wx == null || b.wx == null) return;
      if(a.area === b.area) return;                 // inside one cluster: no thread
      var key = [a.area, b.area].sort().join('\\u0000');
      if(!waypoints[key]){
        var ha = hubOf[a.area], hb = hubOf[b.area];
        var ax = ha ? ha.wx : a.wx, ay = ha ? ha.wy : a.wy;
        var bx = hb ? hb.wx : b.wx, by = hb ? hb.wy : b.wy;
        var mx0 = (ax + bx) / 2, my0 = (ay + by) / 2;
        // Bow the waypoint away from the middle so nothing runs through the
        // mascot sitting at the centre of its universe.
        var vx0 = mx0 - __W__ / 2, vy0 = my0 - __H__ / 2;
        var d0 = Math.hypot(vx0, vy0) || 1;
        var bow0 = Math.min(Math.hypot(bx - ax, by - ay) * 0.26, 150);
        waypoints[key] = {x: mx0 + vx0 / d0 * bow0, y: my0 + vy0 / d0 * bow0,
                          who: {}, n: 0};
      }
      var wp = waypoints[key];
      wp.n++;
      (e2.who || '').split(', ').forEach(function(x){ if(x) wp.who[x] = 1; });
      var len = Math.hypot(b.wx - a.wx, b.wy - a.wy);
      var ln = el('path', {d: 'M' + a.wx + ' ' + a.wy
                              + ' Q' + wp.x.toFixed(1) + ' ' + wp.y.toFixed(1)
                              + ' ' + b.wx + ' ' + b.wy,
                           'data-ea': e2.a, 'data-eb': e2.b, 'data-kin': key,
                           'class': 'edge kin'});
      ln.style.opacity = Math.max(0.13, 0.42 - len / 2600);
      ln.appendChild(el('title', {}, 'shared: ' + (e2.who || '')));
      stage.appendChild(ln);
    });
    // Name each bundle once, at its waypoint — but only while you are looking
    // at something it touches. Printed always, one person who bridges four
    // areas wrote their own name four times across four patches of empty
    // canvas, answering a question nobody had asked. The names now wait for a
    // focused area or a selected dot (litKin), which also means a bundle of
    // one thread can afford its caption: it is no longer competing for the
    // canvas, it is the answer to what you just tapped.
    Object.keys(waypoints).forEach(function(key){
      var wp = waypoints[key], who = Object.keys(wp.who);
      if(!who.length) return;
      var kt = ctext('kinlab', who.slice(0, 2).join(', ') + (who.length > 2 ? '…' : ''),
                     'node', wp.x, wp.y, 0, 'middle');
      kt.dataset.kin = key;
    });
    EDGES.forEach(function(e2){
      if(e2.kind !== 'kin') return;
      var a = NODES[e2.a], b = NODES[e2.b];
      if(!a || !b || a.wx == null || b.wx == null) return;
      if(a.area !== b.area) return;                 // handled by the bundler
      var ln = el('path', {d: 'M' + a.wx + ' ' + a.wy + ' L' + b.wx + ' ' + b.wy,
                           'class': 'edge kin'});
      ln.appendChild(el('title', {}, 'shared: ' + (e2.who || '')));
      stage.appendChild(ln);
    });
    // The brain itself, at the centre of its universe — with a mood: waving
    // at emptiness, sleeping when all is calm, celebrating a finished five.
    var masc = el('image', {href:'art/__MOOD__.png?v=2', x:__W__/2 - 44, y:__H__/2 - 44,
                            width:88, height:88, 'class':'mascot breathe home'});
    masc.appendChild(el('title', {}, 'Back to the whole map'));
    stage.appendChild(masc);
    if(MASCOT) ctext('cl', MASCOT, 'hub', __W__/2, __H__/2 + 58, 0, 'middle');
    NODES.forEach(function(n){
      if(n.kind !== 'area' || n.wx == null) return;
      var ht = ctext('cl', n.labtext || (n.name + '  (' + n.live + ')'), 'hub', n.wx,
                     (n.laby != null ? n.laby : n.wy - 12), 0, 'middle');
      // named, so focus and selection can find the heading by its area rather
      // than by guessing from the words in it
      ht.dataset.area = n.name;
    });
  }
  var past = inPast();
  NODES.forEach(function(n, ni){
    if(!visible(n) || n.kind === 'area') return;
    if(n.kind === 'circ'){
      // a person on their ring: face when we have one, state worn as the
      // ring around it; focus keeps its star via a warm second ring
      var g = [];
      // healthy relationships recede at overview: the reds and terracottas
      // are the question this view answers
      var calm = (n.state === 'moving' || n.state === 'cold') && !n.focus;
      // Both kinds of dot wear state in the SAME channel: the ring. A face
      // always did; a photo-less dot used to wear it as a solid fill, which
      // made "no photo on file" read as visual weight — the heaviest shapes
      // in the drawing were whoever the avatar sync hadn't found, and they
      // outshouted the people she is closest to. The interior is identity
      // now (a face, or a tint of the state), the ring is state, everywhere.
      var base = el('circle', {cx: n.px, cy: n.py, r: n.r,
                               'class': 'node circ' + (off[n.state] ? ' faded' : '')
                                 + (n.held ? ' heldp' : '') + (calm ? ' okp' : ''),
                               fill: n.av ? 'var(--bg)'
                                 : 'color-mix(in oklch, var(--' + n.state + ') 22%, var(--bg))'});
      base.style.stroke = 'var(--' + n.state + ')';
      base.style.strokeWidth = '2.5px';
      base.appendChild(el('title', {}, n.name));
      base.dataset.pn = n.name;
      stage.appendChild(base);
      if(n.av){
        var im = el('image', {href: n.av + '?v=1',
          x: n.px - n.r + 2, y: n.py - n.r + 2,
          width: (n.r - 2) * 2, height: (n.r - 2) * 2,
          preserveAspectRatio: 'xMidYMid slice',
          'clip-path': 'url(#cclip)',
          'class': (n.held ? 'heldp' : '') + (calm ? ' okp' : '')});
        im.style.pointerEvents = 'none';
        im.dataset.pn = n.name;
        stage.appendChild(im);
      }
      if(n.focus)
        stage.appendChild(el('circle', {cx: n.px, cy: n.py, r: n.r + 4,
                                        'class': 'focusring'}));
      if(!off[n.state]){
        // 343 names at once was the whole problem: a name earns its place
        // only once you zoom into a neighbourhood
        var tx2 = ctext('nl', n.name.length > 18 ? n.name.slice(0, 17) + '\\u2026' : n.name,
              'node', n.px, n.py, n.r, 'middle');
        tx2.dataset.mink = '1.05';
      }
      return;
    }
    // replaying a past day: workstreams wear that day's state, and ones
    // that didn't exist yet simply aren't there
    var st = n.state;
    if(past && n.kind === 'ws'){
      st = HIST[SCRUB].s[n.name];
      if(!st) return;
    }
    // today's plan projected onto the map: a soft halo (today only)
    // "In today's plan" was a hard ring at r+6, which put FOUR concentric
    // strokes inside six pixels — state fill, area ring, progress arc, halo —
    // with white slivers between them. It is a soft filled disc now, so it
    // reads as a glow behind the dot instead of another data ring.
    // Every ring, glow and arc carries the index of the dot it belongs to, so
    // dimming a dot takes its decorations with it. Tagged only on the circle,
    // a quietened dot kept a bright halo and a bright progress arc around a
    // ghost — the loudest thing on screen was the work you had not asked about.
    if(n.today && !past && !off[n.state])
      stage.appendChild(el('circle', {cx:nx(n), cy:ny(n), r:n.r + 9,
                                      'data-ni':ni, 'class':'halo deco'}));
    var c = el('circle', {cx:nx(n), cy:ny(n), r:n.r,
                          'class':'node ' + n.kind
                            + (off[n.state] ? ' faded' : '')
                            + (st === 'overdue' && !past && !off[n.state] ? ' pulse' : ''),
                          fill:'var(--' + st + ')'});
    // The dot carries ONE thing: the state, as its fill. Area used to be a
    // coloured ring here, but the clusters and their headings already say
    // which area a node is in — it was a whole layer spent on a repeat.
    c.style.stroke = 'color-mix(in oklch, var(--' + st + ') 72%, black)';
    c.style.strokeWidth = '1px';
    c.appendChild(el('title', {}, n.name + (n.sub ? ' — ' + n.sub : '')));
    c.dataset.ni = ni;
    n.el = c;
    if(FOCUS) c.classList.toggle('infocus',
      n.area === FOCUS || (n.kind === 'area' && n.name === FOCUS));
    stage.appendChild(c);
    // The ring used to carry the horizon in three dash patterns. The columns
    // say that now, in the channel you can read without the legend, so the
    // ring takes the one fact the axis stopped showing: whether a real
    // calendar date is on this. Present or absent, nothing to decode.
    if(n.kind === 'ws' && n.dated && !past && !off[n.state]){
      var hr = el('circle', {cx:nx(n), cy:ny(n), r:n.r + 4.5,
                             'data-ni':ni, 'class':'hzring deco'});
      stage.appendChild(hr);
    }
    // Progress, further out again so it cannot be mistaken for the horizon
    // ring: an arc from twelve o'clock = tasks done / (done + open).
    if(n.kind === 'ws' && !past && !off[n.state] && (n.done || 0) + (n.open || 0) > 0){
      var frac = (n.done || 0) / ((n.done || 0) + (n.open || 0));
      if(frac > 0){
        var arc = el('circle', {cx:nx(n), cy:ny(n), r:n.r + 8.5,
                                'data-ni':ni, 'class':'parc deco',
                                pathLength:100,
                                'stroke-dasharray': Math.round(frac * 100) + ' 100',
                                transform:'rotate(-90 ' + nx(n) + ' ' + ny(n) + ')'});
        stage.appendChild(arc);
      }
    }
    if(hasLabel(n) && !off[n.state]){
      var lab = n.name + (n.sub ? ' ' + n.sub : '');
      var side = n.lside || 'below';
      var t = ctext('nl', lab.length > 26 ? lab.slice(0, 25) + '…' : lab, 'node',
                    nx(n), ny(n), n.r,
                    side === 'right' ? 'start' : side === 'left' ? 'end' : 'middle');
      t.dataset.side = side;
      // Which dot this caption belongs to, so focusing an area or selecting a
      // dot can quieten the right names instead of matching on the text.
      t.dataset.ni = ni;
      t.dataset.area = n.area || '';
      // Forty contact names at overview drowned out eleven workstreams that
      // actually want something from you. They come back as you zoom in.
      if(n.kind === 'contact') t.dataset.mink = '1.15';
    }
  });
  clearBuds();
  layoutChrome();
  // A redraw builds fresh elements, so a selection or a focus made before it
  // would lose its lighting without this — filtering the key with a dot
  // selected used to put the whole universe back at full strength.
  if(FOCUS) markFocusParts();
  if(NEAR != null) applyNear();
}

function layoutChrome(){
  var cw = svg.clientWidth || 900, ch = svg.clientHeight || WH;
  var top = barH(), coly = top + 20, kids = chrome.childNodes;
  var placed = [];   // boxes of node labels already kept, for the collision pass
  for(var i = 0; i < kids.length; i++){
    var t = kids[i]; if(t.nodeType !== 1) continue;
    var type = t.dataset.type, wx = +t.dataset.wx, wy = +t.dataset.wy, o = +(t.dataset.o || 0);
    if(type === 'col'){ t.setAttribute('x', view.tx + wx * view.k); t.setAttribute('y', coly); }
    else if(type === 'colsub'){ t.setAttribute('x', view.tx + wx * view.k);
      t.setAttribute('y', coly + 13); }
    else if(type === 'row'){ t.setAttribute('x', ROWX); t.setAttribute('y', view.ty + wy * view.k); }
    else if(type === 'hub'){
      var hx = view.tx + wx * view.k, hy = view.ty + wy * view.k;
      t.setAttribute('x', hx); t.setAttribute('y', hy);
      // an area's name outranks any dot's, so it claims its box first
      var hw = (t.textContent || '').length * 6.4 + 8;
      // Ring names are anchored left or right of their point now, not centred
      // on it, so a box drawn around the centre would reserve the wrong half
      // and let dot captions print into the real one.
      var han = t.getAttribute('text-anchor') || 'middle';
      var hx0 = han === 'start' ? hx - 4 : han === 'end' ? hx - hw + 4 : hx - hw / 2;
      placed.push({x0:hx0, y0:hy - 12, x1:hx0 + hw, y1:hy + 4});
    }
    else if(type === 'node'){
      // A bundle's caption is an answer, not a fixture: it appears when you
      // focus its area or select a dot it touches, and is simply absent the
      // rest of the time. Lit, it also skips the collision pass below — you
      // asked for this one name, so it outranks whatever it lands near.
      if(t.dataset.kin){
        var klit = t.classList.contains('lit');
        t.style.display = klit ? '' : 'none';
        if(!klit) continue;
        t.setAttribute('x', view.tx + wx * view.k);
        t.setAttribute('y', view.ty + wy * view.k);
        continue;
      }
      // The caption sits on whichever side the layout found room on — forcing
      // every one of them underneath was what printed names through the
      // bubbles below them.
      var sd = t.dataset.side || 'below', px = view.tx + wx * view.k,
          py = view.ty + wy * view.k, rr = (o + 7) * view.k;
      if(sd === 'above'){ t.setAttribute('x', px); t.setAttribute('y', py - rr - 6); }
      else if(sd === 'right'){ t.setAttribute('x', px + rr + 7); t.setAttribute('y', py + 4); }
      else if(sd === 'left'){ t.setAttribute('x', px - rr - 7); t.setAttribute('y', py + 4); }
      else { t.setAttribute('x', px); t.setAttribute('y', py + rr + 13); }
      // per-label zoom gate: circle-view names need real zoom to earn a place
      t.style.display = view.k < +(t.dataset.mink || 0.32) ? 'none' : '';
      // Two names printed through each other are worse than one name: whoever
      // got here first (the layout emits the loudest dots first) keeps the
      // space, the other waits until you zoom in far enough to make room.
      if(t.style.display !== 'none'){
        var lx = +t.getAttribute('x'), ly = +t.getAttribute('y'),
            lw = (t.textContent || '').length * 5.9 + 6, lh = 13,
            x0 = sd === 'right' ? lx : sd === 'left' ? lx - lw : lx - lw / 2;
        var box = {x0:x0, y0:ly - lh + 3, x1:x0 + lw, y1:ly + 3};
        for(var q = 0; q < placed.length; q++){
          var b = placed[q];
          if(box.x0 < b.x1 && box.x1 > b.x0 && box.y0 < b.y1 && box.y1 > b.y0){
            t.style.display = 'none'; break;
          }
        }
        if(t.style.display !== 'none') placed.push(box);
      }
    }
    else if(type === 'colbg'){ t.setAttribute('x', 0); t.setAttribute('y', top - 2);
      t.setAttribute('width', cw); t.setAttribute('height', 46); }
    else if(type === 'rowbg'){ t.setAttribute('x', 0); t.setAttribute('y', top + 32);
      t.setAttribute('width', LEFTSTRIP - 6); t.setAttribute('height', ch); }
  }
}

function applyT(){
  stage.setAttribute('transform', 'translate(' + view.tx + ' ' + view.ty + ') scale(' + view.k + ')');
  layoutChrome();
}
function screenToWorld(px, py){
  var r = svg.getBoundingClientRect();
  return {x: (px - r.left - view.tx) / view.k, y: (py - r.top - view.ty) / view.k};
}

function worldBox(){
  var vis = NODES.filter(visible);
  var y0 = 1e9, y1 = -1e9;
  if(MODE === 'horizon'){
    if(!AXIS.length) return null;
    var colw = AXIS.length > 1 ? (AXIS[1].x - AXIS[0].x) : 200;
    var x0 = AXIS[0].x - colw / 2, x1 = AXIS[AXIS.length - 1].x + colw / 2;
    ROWLABELS.forEach(function(r){ y0 = Math.min(y0, r.y - 16); y1 = Math.max(y1, r.y + 16); });
    vis.forEach(function(n){ y0 = Math.min(y0, ny(n) - n.r); y1 = Math.max(y1, ny(n) + n.r); });
    if(y0 > y1){ y0 = 60; y1 = WH - 60; }
    return {x0:x0, y0:y0, x1:x1, y1:y1};
  }
  if(!vis.length) return null;
  var wx0 = 1e9, wx1 = -1e9;
  vis.forEach(function(n){
    wx0 = Math.min(wx0, nx(n) - n.r); wx1 = Math.max(wx1, nx(n) + n.r);
    y0 = Math.min(y0, ny(n) - n.r); y1 = Math.max(y1, ny(n) + n.r);
    if(n.kind === 'area' && n.laby != null) y0 = Math.min(y0, n.laby - 8);
  });
  // Ring names sit outside the outermost dots now, so fitting to the dots
  // alone cropped whichever one landed at three or nine o'clock.
  if(MODE === 'circles') RINGS.forEach(function(rg){
    var w = (rg.name.length + 14) * 3.6;
    wx0 = Math.min(wx0, rg.labx - w); wx1 = Math.max(wx1, rg.labx + w);
    y0 = Math.min(y0, rg.laby - 14); y1 = Math.max(y1, rg.laby + 6);
  });
  return {x0:wx0, y0:y0, x1:wx1, y1:y1};
}

function fit(){
  var b = worldBox(); if(!b) return;
  var cw = svg.clientWidth || 900, ch = svg.clientHeight || WH;
  var padX = 28, padTop = barH() + 58, padBot = 46;
  var leftGutter = MODE === 'horizon' ? LEFTSTRIP : padX;
  var bw = Math.max(b.x1 - b.x0, 1), bh = Math.max(b.y1 - b.y0, 1);
  var k = clamp(Math.min((cw - leftGutter - padX) / bw, (ch - padTop - padBot) / bh), KMIN, 1.4);
  view.k = k;
  var availH = ch - padTop - padBot;
  view.ty = padTop + (availH - bh * k) / 2 - b.y0 * k;
  if(MODE === 'horizon') view.tx = leftGutter + 6 - b.x0 * k;   // left-align after row labels
  else view.tx = (cw - (b.x0 + b.x1) * k) / 2;
  applyT();
}
function centerPt(){ var r = svg.getBoundingClientRect(); return {x:r.left + r.width/2, y:r.top + r.height/2}; }
function zoomAt(cx, cy, factor){
  var r = svg.getBoundingClientRect(), sx = cx - r.left, sy = cy - r.top;
  var nk = clamp(view.k * factor, KMIN, KMAX), f = nk / view.k;
  view.tx = sx - (sx - view.tx) * f; view.ty = sy - (sy - view.ty) * f; view.k = nk; applyT();
}

// ---- task buds: a second look at a node blooms its open tasks ------------
var BUDS = [], BUDHITS = [];
function clearBuds(){
  BUDS.forEach(function(x){ if(x.parentNode) x.parentNode.removeChild(x); });
  BUDS = []; BUDHITS = [];
}
function budTasks(n){
  clearBuds();
  if(MODE !== 'web' || n.kind !== 'ws' || !(n.tasks || []).length) return;
  var m = Math.min(n.tasks.length, 8);
  n.tasks.slice(0, m).forEach(function(t, i){
    var a = -Math.PI / 2 + (i / m) * Math.PI * 2;
    var lx = n.wx + Math.cos(a) * (n.r + 26),
        ly = n.wy + Math.sin(a) * (n.r + 26);
    var ln = el('line', {x1:n.wx, y1:n.wy, x2:lx, y2:ly, 'class':'budedge'});
    var c = el('circle', {cx:lx, cy:ly, r:5.5,
                          'class':'bud' + (t.dd != null && t.dd < 0 ? ' bad' : '')});
    c.appendChild(el('title', {}, t.t + ' \\u2014 tap to mark done'));
    stage.appendChild(ln); stage.appendChild(c);
    var short = t.t.length > 20 ? t.t.slice(0, 19) + '\\u2026' : t.t;
    var tx = ctext('bl', short, 'node', lx, ly, 4, 'middle');
    BUDS.push(ln, c, tx);
    BUDHITS.push({x: lx, y: ly, t: t});
  });
  layoutChrome();
}

// ---- fly-to: the camera glides to a tapped node --------------------------
function flyTo(n){
  var cw = svg.clientWidth || 900, ch = svg.clientHeight || WH;
  var k2 = Math.max(view.k, 0.9);
  // leave room for the panel on wide screens so the node is not under it
  var cx = cw > 760 ? (cw - 340) / 2 : cw / 2;
  var tx1 = cx - nx(n) * k2;
  var ty1 = barH() + (ch - barH()) / 2 - ny(n) * k2;
  if(matchMedia('(prefers-reduced-motion: reduce)').matches){
    view.tx = tx1; view.ty = ty1; view.k = k2; applyT(); return;
  }
  var s = {tx: view.tx, ty: view.ty, k: view.k}, t0 = null;
  function step(ts){
    if(!t0) t0 = ts;
    var p = Math.min((ts - t0) / 380, 1), q = 1 - Math.pow(1 - p, 3);
    view.tx = s.tx + (tx1 - s.tx) * q;
    view.ty = s.ty + (ty1 - s.ty) * q;
    view.k = s.k + (k2 - s.k) * q;
    applyT();
    if(p < 1) requestAnimationFrame(step);
  }
  requestAnimationFrame(step);
}

function drow(dl, k, v){
  if(!v && v !== 0) return;
  dl.appendChild(Object.assign(document.createElement('dt'), {textContent:k}));
  dl.appendChild(Object.assign(document.createElement('dd'), {textContent:v}));
}
function show(n, still){
  document.getElementById('p-area').textContent =
    n.kind === 'circ' ? (n.circle + (n.held ? ' \\u00b7 together, on hold until ' + n.hold : ''))
    : n.kind === 'contact' ? (n.circle || 'Contact')
    : n.kind === 'person' ? 'Waiting on them'
    : n.kind === 'event' ? (n.sub || '') : (n.area || '');
  document.getElementById('p-name').textContent = n.name;
  var why = [];
  if(n.rc) why.push(n.rc);
  if(n.kind === 'circ' && !n.held){
    if(n.owed) why.push('You owe them a reply.');
    else if(n.pover) why.push((n.days != null ? n.days + ' days' : 'A while')
      + ' since you spoke \\u2014 you wanted ' + (n.every || 'a rhythm') + '.');
    else if(n.days != null) why.push('Spoke ' + (n.days === 0 ? 'today' : n.days + 'd ago') + '.');
    else why.push('Never logged yet.');
  }
  if(n.kind === 'person' && n.waiting_on && n.waiting_on.length) why.push('The ball is with them on: ' + n.waiting_on.join(', ') + '.');
  // No Math.abs here, ever. It was what let a date 338 days in the FUTURE
  // print as 338 days in the past: only a negative days_to_due is late.
  if(n.urgency === 'date' && n.days_to_due != null && n.days_to_due < 0)
    why.push(-n.days_to_due + ' days past its date.');
  else if(n.urgency === 'date') why.push('A task on it is past its date.');
  else if(n.urgency === 'goal') why.push('A goal on it has slipped its date.');
  else if(n.urgency === 'urgent') why.push('You marked this urgent'
    + (n.days_to_due != null && n.days_to_due >= 0
       ? '. Its own date is ' + n.days_to_due + ' days out.' : '.'));
  if(n.state === 'chase') why.push('No word' + (n.who ? ' from ' + n.who : '') + ' in ' + n.days_waiting + ' days.');
  if(n.state === 'cold') why.push(n.days_untouched == null ? 'Never started.'
      : "You haven't touched this in " + n.days_untouched + ' days.');
  if(n.state === 'soon' && n.days_to_due != null) why.push('Due in ' + n.days_to_due + ' days.');
  document.getElementById('p-why').textContent = why.join(' ');
  var dl = document.getElementById('p-dl'); dl.innerHTML = '';
  if(n.kind === 'ws'){
    drow(dl, 'Status', n.status);
    drow(dl, 'Ball', n.ball === 'me' ? 'You' : n.ball === 'them' ? ('Them' + (n.who ? ' — ' + n.who : '')) : 'Nobody');
    drow(dl, 'Next', n.next); drow(dl, 'Due', n.due); drow(dl, 'Last touched', n.touched);
    drow(dl, 'Open items', n.open); drow(dl, 'Why it matters', n.why);
    if(n.folder){
      // the related files, as a door: tap the path, the file manager opens on it
      dl.appendChild(Object.assign(document.createElement('dt'), {textContent:'Folder'}));
      var fdd = document.createElement('dd');
      var fb = document.createElement('button'); fb.className = 'flink';
      fb.textContent = n.folder + ' \\u2197'; fb.title = 'Open the folder';
      fb.onclick = function(ev){ ev.stopPropagation();
        api('/api/reveal', {path: n.folder}, 'Opened the folder \\u2713', false); };
      fdd.appendChild(fb); dl.appendChild(fdd);
    }
  }
  if(n.kind === 'circ'){
    drow(dl, 'Rhythm', n.every);
    drow(dl, 'Last spoke', n.days == null ? 'never logged'
         : n.days === 0 ? 'today' : n.days + ' days ago');
    if(n.ball === 'me') drow(dl, 'Ball', 'with you \\u2014 you owe them');
    else if(n.ball === 'them') drow(dl, 'Ball', 'with them');
    drow(dl, 'Where', n.where);
    drow(dl, 'Reach via', n.reach);
    drow(dl, 'Birthday', n.bday);
    drow(dl, 'Why they matter', n.pwhy);
  }
  if(n.how) drow(dl, 'How you know them', n.how);
  CURN = n;
  // Progress worn plainly: tasks done over total, as a bar and a phrase.
  var prog = document.getElementById('p-prog');
  var tot = (n.done || 0) + (n.open || 0);
  if(n.kind === 'ws' && tot > 0){
    prog.hidden = false;
    prog.querySelector('i').style.width = Math.round((n.done || 0) / tot * 100) + '%';
    document.getElementById('p-progtxt').textContent = (n.done || 0) + ' of ' + tot + ' done';
  } else prog.hidden = true;
  // Open tasks, tickable right here — the map is a place to act, not only
  // look. Dated ones (soonest first) wear their deadline.
  var tl = document.getElementById('p-tasks'); tl.innerHTML = '';
  var ts = (n.tasks || []).slice().sort(function(a, b){
    return (a.dd == null ? 9e9 : a.dd) - (b.dd == null ? 9e9 : b.dd); });
  ts.forEach(function(t){
    var li = document.createElement('li');
    var cb = document.createElement('button'); cb.className = 'ptick';
    cb.title = 'Mark done';
    cb.onclick = function(ev){ ev.stopPropagation();
      cb.disabled = true;
      api('/api/task', {src:'workstreams.md', key:t.k, action:'done'},
          'Done \\u2713', true, function(){
        sp.style.textDecoration = 'line-through'; sp.style.opacity = '.55';
      }); };
    var sp = document.createElement('span'); sp.textContent = t.t;
    li.appendChild(cb); li.appendChild(sp);
    if(t.dd != null){
      var dd = document.createElement('em'); dd.className = 'pdd' + (t.dd < 0 ? ' bad' : '');
      dd.textContent = t.dd < 0 ? Math.abs(t.dd) + 'd late'
        : t.dd === 0 ? 'today' : 'in ' + t.dd + 'd';
      li.appendChild(dd);
    }
    tl.appendChild(li);
  });
  tl.hidden = !(n.tasks && n.tasks.length);
  // ...and the same tasks bloom around the node itself.
  budTasks(n);
  // ...and the rest of the universe steps back, so the threads left standing
  // are this dot's own.
  setNear(n);
  // The camera follows the tap on the circles too. flyTo already leaves room
  // for the panel on a wide screen, so this is the fix for opening a face and
  // finding the drawer parked on top of it — it only ever ran on the web.
  if(!still && ((MODE === 'web' && n.wx != null) || (MODE === 'circles' && n.px != null)))
    flyTo(n);
  // The people this workstream touches — plus the hand link for the ties
  // the text scan can't see.
  var pl = document.getElementById('p-people'); pl.innerHTML = '';
  (n.people || []).forEach(function(nm){
    var a = document.createElement('a'); a.className = 'pchip';
    a.textContent = nm; a.href = 'index.html#/people';
    pl.appendChild(a);
  });
  if(n.kind === 'ws'){
    var ap = document.createElement('button'); ap.className = 'pchip addp';
    ap.textContent = '+ person'; ap.title = 'Link a person to this by hand';
    ap.onclick = function(ev){ ev.stopPropagation();
      mdlgOpen('Link a person \\u2014 ' + n.name, 'Who (exact name)',
               'Dad, Sloan, Maman\\u2026', null, null, 'Link them',
        function(v1){
          if(v1) api('/api/ws/person', {name: n.name, person: v1},
                     'Linked \\u2713', true);
        });
    };
    pl.appendChild(ap);
  }
  if(n.kind === 'circ')
    // what you share, as doors: tap a workstream to open it in the web view
    (n.wss || []).forEach(function(wn){
      var b = document.createElement('button'); b.className = 'pchip';
      b.textContent = wn; b.title = 'Open this workstream';
      b.onclick = function(ev){ ev.stopPropagation();
        var t = null;
        NODES.forEach(function(m){ if(m.kind === 'ws' && m.name === wn) t = m; });
        if(t){ if(MODE === 'circles') setMode('web'); show(t); } };
      pl.appendChild(b);
    });
  pl.hidden = !((n.people && n.people.length) || n.kind === 'ws'
                || (n.wss && n.wss.length));
  var acts = document.getElementById('p-acts');
  acts.hidden = n.kind !== 'ws';
  document.getElementById('p-pacts').hidden = n.kind !== 'circ';
  // The chat button names the channel it will land in. She files that per
  // person as Reach, and "Open the chat" made her guess which app opens.
  // Where Reach is a phone call or seeing them, there is no chat to open and
  // the button goes — a door onto the wrong room is worse than no door.
  var chatb = document.getElementById('pp-chat');
  if(chatb && n.kind === 'circ'){
    var rv = (n.reach || '').trim().toLowerCase();
    var offline = /^(call|phone|in person|in-person|voice)/.test(rv);
    var app = /^(whatsapp|instagram|insta|sms|imessage|signal|telegram|messenger)/.test(rv);
    chatb.hidden = offline;
    chatb.textContent = (app ? 'Open ' + n.reach.trim() : 'Open the chat') + ' \\u2197';
  }
  document.getElementById('pa-scan').hidden = !(n.kind === 'ws' && n.folder);
  document.getElementById('pa-run').hidden = !(n.kind === 'ws' && n.folder);
  document.getElementById('p-note').hidden = true;
  panel.hidden = false;
  // dock it: the map narrows instead of sitting under the panel
  document.body.classList.add('docked');
  // Docking narrows #svg but does not move the drawing, so a dot on the
  // right of the board ends up hidden behind the panel that was opened to
  // describe it. Narrowing was only ever half the fix; this is the pan.
  if(window.innerWidth >= 1100)
    setTimeout(function(){ reveal(n, still); }, 190);
}
// Bring a node back inside the visible strip, and only when it has actually
// fallen outside it — an unconditional recentre would yank the board on
// every tap and lose the layout she had just read.
function reveal(n, still){
  applyT();
  if(still) return;
  var x = nx(n), y = ny(n);
  if(x == null || y == null) return;
  var cw = svg.clientWidth || 900, sx = x * view.k + view.tx;
  var margin = (n.r || 12) * view.k + 96;
  if(sx > cw - margin) view.tx -= sx - (cw - margin);
  else if(sx < margin) view.tx += margin - sx;
  else return;
  applyT();
}
var CURN = null;
function pnote(msg){
  var el = document.getElementById('p-note');
  el.textContent = msg; el.hidden = false;
}
function api(path, body, okmsg, reloadAfter, onOk){
  // The server answers before it regenerates the pages, so the confirmation
  // is instant; reloadAfter no longer reloads blind — it polls the version
  // stamp fast and lets the page refresh itself once the fresh build lands.
  fetch(path, {method:'POST', headers:{'Content-Type':'application/json'},
               body: JSON.stringify(body)})
    .then(function(r){ return r.json().then(function(j){
      if(!r.ok) throw new Error(j.error || r.status);
      if(okmsg){ pnote(okmsg); toast(okmsg); }
      if(onOk) onOk(j);
      if(reloadAfter) nudgePoll();
    }); })
    .catch(function(e){ pnote(e.message); toast(e.message); });
}
var toastT = null;
function toast(msg){
  var t = document.getElementById('mtoast');
  t.textContent = msg; t.hidden = false;
  requestAnimationFrame(function(){ t.classList.add('on'); });
  if(toastT) clearTimeout(toastT);
  toastT = setTimeout(function(){
    t.classList.remove('on');
    setTimeout(function(){ t.hidden = true; }, 220);
  }, 2400);
}
var mdCb = null;
function mdlgOpen(title, l1, ph1, l2, ph2, go, cb){
  mdCb = cb;
  document.getElementById('md-title').textContent = title;
  document.getElementById('md-l1').textContent = l1;
  var i1 = document.getElementById('md-i1'); i1.value = ''; i1.placeholder = ph1 || '';
  var f2 = document.getElementById('md-f2'); f2.hidden = !l2;
  if(l2){ document.getElementById('md-l2').textContent = l2;
    var i2 = document.getElementById('md-i2'); i2.value = ''; i2.placeholder = ph2 || ''; }
  document.getElementById('md-go').textContent = go || 'Save';
  document.getElementById('mdlg').hidden = false;
  document.getElementById('mscrim').hidden = false;
  setTimeout(function(){ i1.focus(); }, 60);
}
function mdlgClose(){
  document.getElementById('mdlg').hidden = true;
  document.getElementById('mscrim').hidden = true; mdCb = null;
}
document.getElementById('md-go').onclick = function(){
  if(!mdCb) return;
  var cb = mdCb;
  var v1 = document.getElementById('md-i1').value.trim();
  var v2 = document.getElementById('md-i2').value.trim();
  mdlgClose(); cb(v1, v2);
};
document.getElementById('md-cancel').onclick = mdlgClose;
document.getElementById('mscrim').onclick = mdlgClose;
document.getElementById('md-i1').addEventListener('keydown', function(e){
  if(e.key === 'Enter'){ e.preventDefault(); document.getElementById('md-go').click(); }
});
addEventListener('keydown', function(e){ if(e.key === 'Escape') mdlgClose(); });

document.getElementById('pa-add').onclick = function(){
  if(!CURN) return;
  mdlgOpen('New task \\u2014 ' + CURN.name, 'What needs doing?', '',
           'Deadline (optional)', 'a date, friday, this week\\u2026', 'Add task',
    function(v1, v2){
      if(v1) api('/api/add/task', {name: CURN.name, text: v1, due: v2},
                 'Added \\u2713', true);
    });
};
document.getElementById('pa-start').onclick = function(){
  if(!CURN) return;
  var first = (CURN.tasks && CURN.tasks[0]) ? CURN.tasks[0].t : CURN.next || CURN.name;
  mdlgOpen('\\u2726 Start for me \\u2014 ' + first.slice(0, 40),
           'Anything Claude should know? (optional)',
           'dates, route, budget, preferences\\u2026', null, null, 'Go',
    function(v1){
      api('/api/queue', {mode: 'just-do-it',
           text: 'Start this for me: \\u201c' + first + '\\u201d (workstream \\u201c'
             + CURN.name + '\\u201d). '
             + (v1 ? 'My precisions \\u2014 follow these over any guess: ' + v1 + '. ' : '')
             + 'Do the part Claude can do: research real options '
             + '(times, prices, links \\u2014 use web search) into a note under the task, '
             + 'look up any phone numbers or contacts into the task text, draft any '
             + 'message into brain/drafts/. You have REAL browser tools (the mcp '
             + 'browser server): for live options open the booking site, run my '
             + 'exact search, and copy the top 3\\u20135 actual results (times, '
             + 'PRICES as shown) into the task note with the direct link. Never '
             + 'log in, never fill personal or payment fields. '
             + 'NEVER book, pay, send or submit \\u2014 stop '
             + 'where a human hand is needed and end the Outcome with exactly what '
             + 'remains for me. If a detail is missing that would change the answer, '
             + 'still do your best AND write each missing detail as a - [ ] question '
             + 'in brain/questions.md \\u2014 I answer those on the Today page and the '
             + 'next run refines with my answers.'},
          'Queued \\u2014 run it from the pill below \\u2713', false);
    });
};
document.getElementById('pa-snooze').onclick = function(){
  if(!CURN) return;
  mdlgOpen('Snooze \\u2014 ' + CURN.name, 'For how long?',
           '7, 14, 30 \\u2014 or a date, \\u201cnext month\\u201d, \\u201cfriday\\u201d',
           null, null, 'Snooze it',
    function(v1){
      if(!v1) return;
      var body = {name: CURN.name};
      if(/^\\d+$/.test(v1)) body.days = v1; else body.until = v1;
      api('/api/ws/snooze', body, 'Asleep \\u2713', true);
    });
};
document.getElementById('pa-ask').onclick = function(){
  if(!CURN) return;
  mdlgOpen('Ask Claude \\u2014 ' + CURN.name, 'What should Claude do?',
           'look something up, draft a message, add dates\\u2026', null, null, 'Queue it',
    function(v1){
      if(v1) api('/api/queue', {text: 'About the workstream \\u201c' + CURN.name + '\\u201d: ' + v1,
                                mode: 'just-do-it'},
                 'Queued \\u2014 run it from the pill below \\u2713', false);
    });
};
document.getElementById('pp-chat').onclick = function(){
  if(!CURN) return;
  var b = document.getElementById('pp-chat');
  b.disabled = true;
  fetch('/api/beeper/focus', {method:'POST',
      headers:{'Content-Type':'application/json'},
      body: JSON.stringify({person: CURN.name})})
    .then(function(r){ return r.json(); })
    .then(function(j){
      b.disabled = false;
      if(j.error){ toast(j.error); return; }
      toast('Beeper is opening the chat \\u2713');
    })
    .catch(function(){ b.disabled = false;
      toast('Beeper must be open on this Mac for that'); });
};
document.getElementById('pp-spoke').onclick = function(){
  if(!CURN) return;
  var n = CURN;
  api('/api/person/spoke', {name: n.name}, 'Stamped today \\u2713', true,
    function(){
      n.owed = false; n.pover = false; n.days = 0;
      if(!n.held) n.state = 'moving';
      draw(); show(n, true);
    });
};
document.getElementById('pp-hold').onclick = function(){
  if(!CURN) return;
  var n = CURN;
  mdlgOpen('Together with ' + n.name, 'Until (days or a date)',
           '30, 2026-09-30, end of september\\u2026', null, null, 'Hold',
    function(v1){
      if(!v1) return;
      var body = {name: n.name};
      if(/^\\d+$/.test(v1)) body.days = v1; else body.until = v1;
      api('/api/person/hold', body, 'On hold \\u2713', true, function(j){
        n.held = true; n.hold = j.until || v1; n.state = 'waiting';
        draw(); show(n, true);
      });
    });
};
document.getElementById('pp-every').onclick = function(){
  if(!CURN) return;
  var n = CURN;
  mdlgOpen('Reach out how often \\u2014 ' + n.name, 'Every',
           '3 days, weekly, monthly\\u2026', null, null, 'Set rhythm',
    function(v1){
      if(!v1) return;
      api('/api/person/every', {name: n.name, every: v1},
          'Rhythm set \\u2713', true, function(j){
        n.every = j.every || v1; show(n, true);
      });
    });
};
document.getElementById('pp-merge').onclick = function(){
  if(!CURN) return;
  var n = CURN;
  mdlgOpen('Merge ' + n.name + ' into\\u2026', 'Keep which entry?',
           'their other name, exactly', null, null, 'Merge them',
    function(v1){
      if(!v1) return;
      api('/api/person/merge', {name: n.name, into: v1},
          'Merged ' + n.name + ' into ' + v1 + ' \\u2713', true, function(){
        // the folded entry leaves the rings right away
        NODES = NODES.filter(function(m){
          return !(m.kind === 'circ' && m.name === n.name); });
        hidePanel(); draw();
      });
    });
};
document.getElementById('pa-run').onclick = function(){
  if(!CURN || !CURN.folder) return;
  mdlgOpen('Session in ' + CURN.folder, 'What should Claude do there?',
           'fix the failing build, continue the feature, tidy TODOs\\u2026',
           null, null, 'Run it',
    function(v1){
      if(!v1) return;
      api('/api/agent', {job: 'project', path: CURN.folder, text: v1},
          'Running in that repo \\u2014 watch the pill below \\u2713', false);
      setTimeout(mbPoll, 800);
    });
};
document.getElementById('pa-due').onclick = function(){
  if(!CURN) return;
  var n = CURN;
  mdlgOpen('When does ' + n.name + ' need to be done?', 'Date or window',
           '2026-09-15, next week, mid-September, or empty to clear',
           null, null, 'Set the date',
    function(v1){
      api('/api/ws/due', {name: n.name, due: v1 || ''},
          v1 ? 'Dated \\u2014 it moves onto the timeline \\u2713'
             : 'Date cleared \\u2713', true);
    });
};
document.getElementById('pa-scan').onclick = function(){
  if(!CURN || !CURN.folder) return;
  api('/api/queue', {text: 'Read the key files in ' + CURN.folder + ' for the workstream '
       + '\\u201c' + CURN.name + '\\u201d, compare with its current tasks, and add any '
       + 'clearly-new concrete tasks marked \\u201c(from folder \\u2014 confirm)\\u201d. '
       + 'Propose, don\\u2019t restructure; tick nothing.',
       mode: 'just-do-it'},
      'Queued a folder check \\u2014 run it from the pill below \\u2713', false);
};
function hidePanel(){ panel.hidden = true; CURN = null; clearBuds(); setNear(null);
  document.body.classList.remove('docked');
  if(window.innerWidth >= 1100) setTimeout(applyT, 190); }
document.getElementById('close').onclick = hidePanel;

// ---- type-to-jump: press / and name a node, the camera goes there --------
addEventListener('keydown', function(e){
  if(e.key !== '/' || e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA')
    return;
  e.preventDefault();
  mdlgOpen('Jump to', 'Name (or part of one)', 'the house, Mum, the app\\u2026',
           null, null, 'Go',
    function(v1){
      if(!v1) return;
      var q = v1.toLowerCase(), best = null;
      NODES.forEach(function(n){
        if(!visible(n) || n.kind === 'area') return;
        var nm = n.name.toLowerCase();
        if(nm.indexOf(q) < 0) return;
        if(!best || nm.indexOf(q) < best.name.toLowerCase().indexOf(q)) best = n;
      });
      if(best){ show(best); if(MODE === 'horizon') flyTo(best); }
      else pnote('Nothing called \\u201c' + v1 + '\\u201d on this view');
    });
});

// ---- the scrub: drag through your month ----------------------------------
var scrubEl = document.getElementById('scrub'), scR = document.getElementById('sc-r'),
    scTicks = document.getElementById('sc-ticks');
function scrubUI(){
  scrubEl.hidden = !(MODE === 'web' && HIST.length > 1);
}
// The days the month was actually about. HIST holds one live-state map per
// day, so an inflection is a diff between neighbours: work that stopped being
// live (finished or dropped), work that appeared, or a day when several dots
// changed state at once. Ordinary drift gets no mark — a mark on every day is
// the same as no marks, which is what a bare track already was.
function milestones(){
  var out = [];
  for(var i = 1; i < HIST.length; i++){
    var a = HIST[i - 1].s || {}, b = HIST[i].s || {};
    var gone = [], came = [], moved = 0, k;
    for(k in a){ if(!(k in b)) gone.push(k); else if(a[k] !== b[k]) moved++; }
    for(k in b){ if(!(k in a)) came.push(k); }
    if(!gone.length && !came.length && moved < 3) continue;
    // Half the board changing overnight is a gap in the history, not a day
    // she had. Marking it would send her to a snapshot that means nothing.
    var n0 = Object.keys(a).length;
    if(n0 && (gone.length > n0 / 2 || came.length > n0 / 2)) continue;
    var what = [];
    if(gone.length) what.push(gone.slice(0, 2).join(', ')
      + (gone.length > 2 ? ' +' + (gone.length - 2) : '') + ' closed');
    if(came.length) what.push(came.slice(0, 2).join(', ')
      + (came.length > 2 ? ' +' + (came.length - 2) : '') + ' started');
    if(!what.length) what.push(moved + ' changed');
    out.push({i:i, d:HIST[i].d, done:gone.length > 0, what:what.join(' \\u00b7 ')});
  }
  return out;
}
function scrubApply(){
  var live = !inPast();
  document.getElementById('sc-date').textContent = live ? 'today' : HIST[SCRUB].d;
  svg.classList.toggle('past', !live);
  hidePanel(); draw();
  if(scTicks){
    var bs = scTicks.querySelectorAll('button');
    for(var i = 0; i < bs.length; i++)
      bs[i].classList.toggle('on', +bs[i].dataset.i === SCRUB);
  }
}
function buildTicks(){
  if(!scTicks) return;
  scTicks.innerHTML = '';
  var span = HIST.length - 1;
  milestones().forEach(function(m){
    var p = m.i / span;
    var b = document.createElement('button');
    b.type = 'button'; b.dataset.i = m.i;
    if(m.done) b.className = 'done';
    // The thumb's centre runs from 8px to 8px-from-the-right, so a mark that
    // wants to sit under a given day has to travel the same inset track.
    b.style.left = 'calc(8px + ' + (p * 100).toFixed(2) + '% - '
                 + (p * 16).toFixed(2) + 'px)';
    b.title = m.d + ' \\u2014 ' + m.what;
    b.setAttribute('aria-label', b.title);
    b.onclick = function(){ SCRUB = m.i; scR.value = m.i; scrubApply(); };
    scTicks.appendChild(b);
  });
}
if(HIST.length > 1){
  scR.max = HIST.length - 1; scR.value = HIST.length - 1;
  scR.addEventListener('input', function(){ SCRUB = +scR.value; scrubApply(); });
  buildTicks();
}
// The key describes ONE view. Rows name the modes they are true on; the rest
// are simply absent, rather than explaining an arc this drawing doesn't have.
function syncKeyModes(m){
  document.querySelectorAll('[data-modes]').forEach(function(x){
    if(x.dataset.modes.split(' ').indexOf(m) < 0) x.setAttribute('data-off', '1');
    else x.removeAttribute('data-off');
  });
  // "Only who needs you" asks a question about relationships. On the work
  // views these state names mean something else, so the button goes with it —
  // and takes its filter with it, or the web view opens mysteriously empty.
  var lgn = document.getElementById('lgneedy');
  if(!lgn) return;
  lgn.hidden = m !== 'circles';
  if(m !== 'circles' && lgn.classList.contains('on')){
    lgn.classList.remove('on'); off = {}; syncKey();
  }
}

function setMode(m){
  MODE = m;
  if(m !== 'web' && inPast()){           // the replay lives on the web view
    SCRUB = HIST.length - 1; scR.value = SCRUB;
    document.getElementById('sc-date').textContent = 'today';
    svg.classList.remove('past');
  }
  scrubUI();
  ['horizon','web','circles'].forEach(function(k){
    var b = document.getElementById('m-' + k);
    b.classList.toggle('on', m === k);
    b.setAttribute('aria-selected', m === k ? 'true' : 'false');
  });
  syncKeyModes(m);
  document.getElementById('hint').textContent = m === 'horizon'
    ? 'Left = needs you sooner · rows are your areas · tap a dot'
    : m === 'circles'
    ? 'You at the centre · rings = your circles, closest first · red = you owe a reply · terracotta = past your rhythm · tap a face'
    : 'Tight ring = its world · soft halo = in today\\u2019s plan · tap a dot to light what it touches · tap the brain to come back';
  hidePanel(); draw(); fit();
}
scrubUI();
document.getElementById('m-horizon').onclick = function(){ setMode('horizon'); };
document.getElementById('m-web').onclick = function(){ setMode('web'); };
document.getElementById('m-circles').onclick = function(){ setMode('circles'); };

// The key is also the filter, so it has to say when it is filtering: hiding
// a colour used to leave nothing on screen explaining where those dots went.
var lgclear = document.getElementById('lgclear');
function syncKey(){
  var hidden = 0;
  document.querySelectorAll('.lg').forEach(function(b){
    var isOff = !!off[b.dataset.state];
    b.classList.toggle('off', isOff);
    if(isOff && !b.disabled) hidden++;
    if(!b.disabled) b.title = (isOff ? 'Show the ' : 'Hide the ') +
      b.textContent.replace(/\\d+$/, '').trim().toLowerCase() + ' dots';
  });
  if(lgclear){
    lgclear.hidden = !hidden;
    lgclear.textContent = 'Show all (' + hidden + ' hidden)';
  }
}
document.querySelectorAll('.lg').forEach(function(b){
  if(b.disabled) return;
  b.onclick = function(){ off[b.dataset.state] = !off[b.dataset.state];
    syncKey(); draw(); };
});
if(lgclear) lgclear.onclick = function(){ off = {}; syncKey(); draw(); };
// One press for the question this view exists to answer. It was always
// reachable — turn off moving, cold, waiting and chase by hand — but four
// presses is not an answer, it is a chore. Nobody moves: the same dots stay
// on the same bearings, the rest simply step out.
var lgneedy = document.getElementById('lgneedy');
if(lgneedy) lgneedy.onclick = function(){
  var on = !lgneedy.classList.contains('on');
  document.querySelectorAll('.lg').forEach(function(b){
    var s = b.dataset.state;
    off[s] = on && !(s === 'overdue' || s === 'soon');
  });
  lgneedy.classList.toggle('on', on);
  syncKey(); draw();
};
syncKeyModes(MODE);

// ---- one pointer path for pan, pinch and tap ----------------------------
// A press that does not move is a TAP: it hit-tests the nearest dot and opens
// its panel (or closes the panel on empty space). A press that moves is a pan.
var pts = new Map(), panning = null, pinch = null, moved = false;
function dist(a, b){ return Math.hypot(a.x-b.x, a.y-b.y); }
function mid(a, b){ return {x:(a.x+b.x)/2, y:(a.y+b.y)/2}; }
function tapAt(px, py){
  if(inPast()) return;          // the past is for looking, not touching
  var w = screenToWorld(px, py);
  // a bloomed task leaf first: tapping it ticks it, same as the panel row
  for(var i = 0; i < BUDHITS.length; i++){
    var bh = BUDHITS[i];
    if(dist({x: bh.x, y: bh.y}, w) <= 9 / Math.max(view.k, 0.5)){
      api('/api/task', {src:'workstreams.md', key: bh.t.k, action:'done'},
          'Done \\u2713', true);
      return;
    }
  }
  var best = null, bd = 1e9;
  NODES.forEach(function(n){
    if(!visible(n) || n.kind === 'area' || off[n.state]) return;
    var d = dist({x:nx(n), y:ny(n)}, w);
    if(d <= n.r + 8 / view.k && d < bd){ best = n; bd = d; }
  });
  if(best){ show(best); return; }
  // The brain at the centre, which is the one thing on this map that was pure
  // decoration: it is the way back. Once you have zoomed into a cluster,
  // hidden three states and selected a dot, getting out again meant undoing
  // each of those in turn. Checked here rather than by a click handler on the
  // image so it can never intercept a dot underneath it. Its 44pt radius is
  // in world units, the same as the drawing, so it holds at every zoom.
  if(MODE !== 'horizon' && dist({x:__W__/2, y:__H__/2}, w) <= 44){
    var was = FOCUS || NEAR != null || Object.keys(off).length;
    off = {}; syncKey();
    setFocus(null); hidePanel(); draw(); fit();
    toast(was ? 'The whole map \\u2713' : 'This is all of it');
    return;
  }
  // An area hub, or its name: focus that cluster. The map had no browsing
  // verb at all — you could look at the whole thing or squint at one dot.
  if(MODE === 'web'){
    var hub = null, hd = 1e9;
    NODES.forEach(function(n){
      if(n.kind !== 'area' || n.wx == null) return;
      var d1 = dist({x:n.wx, y:n.wy}, w);
      var d2 = dist({x:n.wx, y:(n.laby != null ? n.laby : n.wy - 12)}, w);
      var d3 = Math.min(d1, d2);
      if(d3 <= 46 / view.k && d3 < hd){ hub = n; hd = d3; }
    });
    if(hub){ setFocus(hub.name === FOCUS ? null : hub.name); return; }
  }
  if(FOCUS){ setFocus(null); return; }
  hidePanel();
}

// ---- what one dot touches ------------------------------------------------
// The web view's claim is that this work is connected, and it could draw the
// threads but never let you ask a single dot which of them were its own. So a
// full canvas answered every question at once, which reads the same as
// answering none. Tapping a dot now lights that dot, its area, whoever is
// holding it up, and the work it shares a person with — one hop and no more,
// because two hops is the hairball again with extra steps.
var ADJ = null, HUBIDX = null;
function adj(){
  if(ADJ) return ADJ;
  ADJ = NODES.map(function(){ return []; });
  HUBIDX = {};
  NODES.forEach(function(n, i){ if(n.kind === 'area') HUBIDX[n.name] = i; });
  EDGES.forEach(function(e){
    if(ADJ[e.a] && ADJ[e.b]){ ADJ[e.a].push(e.b); ADJ[e.b].push(e.a); }
  });
  return ADJ;
}
var NEAR = null;                      // index of the selected node, or null
function nearSet(){
  var a = adj(), lit = {};
  if(NEAR == null) return lit;
  lit[NEAR] = 1;
  (a[NEAR] || []).forEach(function(i){ lit[i] = 1; });
  // its area, which is a heading on this map rather than an edge
  var n0 = NODES[NEAR];
  if(n0 && n0.area && HUBIDX[n0.area] != null) lit[HUBIDX[n0.area]] = 1;
  return lit;
}
function applyNear(){
  var on = NEAR != null && MODE === 'web';
  stage.classList.toggle('nearing', on);
  chrome.classList.toggle('nearing', on);
  var lit = on ? nearSet() : {};
  // One pass over everything that carries a dot's index — the circle and its
  // rings alike — so a dot and its decorations never disagree about whether
  // they are in the neighbourhood.
  var parts = stage.querySelectorAll('[data-ni]');
  for(var p = 0; p < parts.length; p++)
    parts[p].classList.toggle('near', !!lit[+parts[p].dataset.ni]);
  // A thread survives only if it actually ends on the dot you tapped. Lighting
  // every thread between two lit nodes would drag in the neighbours' own
  // relationships, which is the hop too far.
  var kins = {}, eds = stage.querySelectorAll('.edge');
  for(var i2 = 0; i2 < eds.length; i2++){
    var ee = eds[i2], ea = +ee.dataset.ea, eb = +ee.dataset.eb;
    var hot = on && (ea === NEAR || eb === NEAR);
    ee.classList.toggle('near', hot);
    if(hot && ee.dataset.kin) kins[ee.dataset.kin] = 1;
  }
  var txs = chrome.querySelectorAll('text'), area0 = on && NODES[NEAR]
    ? (NODES[NEAR].area || '') : '';
  for(var j = 0; j < txs.length; j++){
    var t2 = txs[j];
    if(t2.dataset.kin){ t2.classList.toggle('lit', !!kins[t2.dataset.kin]); continue; }
    if(t2.dataset.ni != null){ t2.classList.toggle('near', !!lit[+t2.dataset.ni]); continue; }
    if(t2.dataset.type === 'hub')
      t2.classList.toggle('near', !!area0 && (t2.dataset.area || '') === area0);
  }
  layoutChrome();
}
function setNear(n){
  var i = (n == null) ? -1 : NODES.indexOf(n);
  NEAR = i < 0 ? null : i;
  applyNear();
}

// ---- focusing one area ---------------------------------------------------
var FOCUS = null;
// Same one pass as applyNear, over every element that names the dot it draws:
// the circle, its glow, its date ring, its progress arc. Called after a redraw
// as well as on the click, because a redraw builds all of it fresh.
function markFocusParts(){
  var parts = stage.querySelectorAll('[data-ni]');
  for(var i = 0; i < parts.length; i++){
    var n = NODES[+parts[i].dataset.ni];
    parts[i].classList.toggle('infocus', !!FOCUS && !!n && (n.area === FOCUS
      || (n.kind === 'area' && n.name === FOCUS)));
  }
}
function setFocus(area){
  FOCUS = area || null;
  // Focusing an area and selecting a dot are two answers to two questions;
  // both at once dims the same canvas twice and neither reads. The newer ask
  // wins.
  if(FOCUS && NEAR != null) setNear(null);
  stage.classList.toggle('focusing', !!FOCUS);
  chrome.classList.toggle('focusing', !!FOCUS);
  var pts = [];
  NODES.forEach(function(n){
    if(!!FOCUS && (n.area === FOCUS || (n.kind === 'area' && n.name === FOCUS))
       && n.wx != null) pts.push(n);
  });
  markFocusParts();
  var labs = chrome.querySelectorAll('text');
  for(var i = 0; i < labs.length; i++){
    var t = labs[i], nm = t.textContent || '';
    // A bundle names itself while one of the two areas it joins is the one
    // you are looking at — that is the moment "who connects these" is a
    // question you are actually asking.
    if(t.dataset.kin){
      t.classList.toggle('lit', !!FOCUS
        && t.dataset.kin.split('\\u0000').indexOf(FOCUS) >= 0);
      continue;
    }
    t.classList.toggle('infocus', !!FOCUS && (
      nm.indexOf(FOCUS) === 0 || (t.dataset.area || '') === FOCUS));
  }
  layoutChrome();
  var chip = document.getElementById('focuschip');
  if(chip){
    chip.hidden = !FOCUS;
    if(FOCUS) chip.firstChild.textContent = FOCUS;
  }
  if(!FOCUS){ fit(); return; }
  // Zoom to the cluster, with room for its captions.
  var x0 = 1e9, y0 = 1e9, x1 = -1e9, y1 = -1e9;
  pts.forEach(function(n){
    x0 = Math.min(x0, n.wx - n.r - 60); x1 = Math.max(x1, n.wx + n.r + 60);
    y0 = Math.min(y0, n.wy - n.r - 40); y1 = Math.max(y1, n.wy + n.r + 34);
  });
  if(x0 > x1) return;
  var cw = svg.clientWidth || 900, ch = svg.clientHeight || WH;
  var padTop = barH() + 58;
  var k = clamp(Math.min((cw - 56) / Math.max(x1 - x0, 1),
                         (ch - padTop - 46) / Math.max(y1 - y0, 1)), KMIN, 1.9);
  view.k = k;
  view.tx = (cw - (x0 + x1) * k) / 2;
  view.ty = padTop + ((ch - padTop - 46) - (y1 - y0) * k) / 2 - y0 * k;
  applyT();
}
// drag a face to another ring = move them to that circle, right on the map
var dragP = null, dragGhost = null, dragRing = null, dragDim = [];
function circAt(px, py){
  if(MODE !== 'circles') return null;
  var w = screenToWorld(px, py), best = null, bd = 1e9;
  NODES.forEach(function(n){
    if(n.kind !== 'circ' || n.px == null || off[n.state]) return;
    var d = dist({x: n.px, y: n.py}, w);
    if(d <= n.r + 6 / view.k && d < bd){ best = n; bd = d; }
  });
  return best;
}
function ringNear(wx, wy){
  var dx = wx - __W__/2, dy = (wy - __H__/2) / 0.94;
  var d = Math.hypot(dx, dy), best = null, bd = 40;
  RINGS.forEach(function(rg){
    var dd = Math.abs(d - rg.r);
    if(dd < bd){ best = rg.name; bd = dd; }
  });
  return best;
}
function dragCleanup(){
  if(dragGhost && dragGhost.parentNode) dragGhost.parentNode.removeChild(dragGhost);
  dragGhost = null; dragRing = null;
  dragDim.forEach(function(x){ x.style.opacity = ''; });
  dragDim = [];
  stage.querySelectorAll('.cring.ringhot').forEach(function(x){
    x.classList.remove('ringhot'); });
}
svg.addEventListener('pointerdown', function(e){
  pts.set(e.pointerId, {x:e.clientX, y:e.clientY});
  svg.setPointerCapture(e.pointerId);
  if(pts.size === 1){
    var hit = circAt(e.clientX, e.clientY);
    if(hit){ dragP = {n: hit}; panning = null; moved = false; return; }
    panning = {x:e.clientX, y:e.clientY, tx:view.tx, ty:view.ty}; moved = false; svg.classList.add('drag');
  }
  else if(pts.size === 2){ panning = null; if(dragP){ dragP = null; dragCleanup(); }
    var p = Array.from(pts.values()); pinch = {d: dist(p[0], p[1])}; }
});
svg.addEventListener('pointermove', function(e){
  if(!pts.has(e.pointerId)) return;
  pts.set(e.pointerId, {x:e.clientX, y:e.clientY});
  if(pinch && pts.size >= 2){
    var p = Array.from(pts.values()), d = dist(p[0], p[1]);
    if(d > 0 && pinch.d > 0){ var m = mid(p[0], p[1]); zoomAt(m.x, m.y, d / pinch.d); pinch.d = d; }
    return;
  }
  if(dragP && pts.size === 1){
    var w = screenToWorld(e.clientX, e.clientY);
    var start = {x: dragP.n.px, y: dragP.n.py};
    if(!moved && dist(w, start) * view.k > 6) moved = true;
    if(moved){
      if(!dragGhost){
        // the ghost IS the friend: their face lifts off the ring and rides
        // the finger, while what stays behind fades until the drop decides
        var gn = dragP.n;
        dragGhost = el('g', {'class': 'dragghost'});
        var gc = el('circle', {cx: 0, cy: 0, r: gn.r + 1,
                               fill: gn.av ? 'var(--bg)' : 'var(--' + gn.state + ')'});
        gc.style.stroke = 'var(--' + gn.state + ')';
        gc.style.strokeWidth = '2.5px';
        dragGhost.appendChild(gc);
        if(gn.av){
          var gi = el('image', {href: gn.av + '?v=1',
            x: -(gn.r - 1), y: -(gn.r - 1),
            width: (gn.r - 1) * 2, height: (gn.r - 1) * 2,
            preserveAspectRatio: 'xMidYMid slice',
            'clip-path': 'url(#cclip)'});
          gi.style.pointerEvents = 'none';
          dragGhost.appendChild(gi);
        }
        stage.appendChild(dragGhost);
        dragDim = [];
        stage.querySelectorAll('[data-pn]').forEach(function(el2){
          if(el2.dataset.pn === gn.name){ dragDim.push(el2); el2.style.opacity = '.22'; } });
      }
      dragGhost.setAttribute('transform', 'translate(' + w.x + ' ' + w.y + ')');
      var rg = ringNear(w.x, w.y);
      if(rg !== dragRing){
        dragRing = rg;
        stage.querySelectorAll('.cring').forEach(function(x){
          x.classList.toggle('ringhot', x.dataset.ring === rg); });
      }
    }
    return;
  }
  if(!panning) return;
  var dx = e.clientX - panning.x, dy = e.clientY - panning.y;
  if(Math.abs(dx) + Math.abs(dy) > 4) moved = true;
  view.tx = panning.tx + dx; view.ty = panning.ty + dy; applyT();
});
['pointerup','pointercancel'].forEach(function(ev){
  svg.addEventListener(ev, function(e){
    var tapCandidate = pts.size === 1 && panning && !moved;
    var x = e.clientX, y = e.clientY;
    pts.delete(e.pointerId);
    if(pts.size < 2) pinch = null;
    if(dragP && pts.size === 0){
      var n = dragP.n, target = dragRing;
      var wasDrag = moved;
      dragP = null; dragCleanup();
      if(ev === 'pointerup'){
        if(!wasDrag){ show(n); }
        else if(target && target !== n.circle){
          // the dot stays exactly where the finger left it — the move is
          // visible before the server even answers; the canonical layout
          // swaps in when the background rebuild lands
          var w2 = screenToWorld(x, y);
          n.circle = target; n.px = w2.x; n.py = w2.y;
          draw();
          api('/api/person/circle', {name: n.name, circle: target},
              'Moved ' + n.name + ' \\u2192 ' + target + ' \\u2713', true);
        }
      }
      return;
    }
    if(pts.size === 0){
      svg.classList.remove('drag');
      if(ev === 'pointerup' && tapCandidate) tapAt(x, y);
      panning = null;
    }
  });
});
document.getElementById('zin').onclick = function(){ var c = centerPt(); zoomAt(c.x, c.y, 1.3); };
document.getElementById('zout').onclick = function(){ var c = centerPt(); zoomAt(c.x, c.y, 0.77); };
document.getElementById('fit').onclick = fit;
document.getElementById('dots').onclick = function(){
  var i = DOTORDER.indexOf(DOTCUR);
  DOTCUR = DOTORDER[(i + 1) % DOTORDER.length];
  applyDots(DOTCUR);
  api('/api/appearance', {dots: DOTCUR},
      'Colours: ' + DOTCUR + ' \\u2713', false);
};
addEventListener('resize', function(){ syncBarVar(); fit(); });
syncBarVar(); syncKey();
svg.addEventListener('wheel', function(e){
  e.preventDefault();
  zoomAt(e.clientX, e.clientY, e.deltaY > 0 ? 0.9 : 1.11);
}, {passive:false});

// ---- a place you leave open: the camera survives every reload ------------
// Ticks reload the page; the version poll reloads it when the brain changes
// elsewhere. Both restore exactly where you were — same view, same zoom,
// same open panel — so refresh never feels like starting over.
addEventListener('pagehide', function(){
  try {
    sessionStorage.setItem('map-state', JSON.stringify(
      {tx: view.tx, ty: view.ty, k: view.k, mode: MODE,
       open: CURN ? CURN.name : ''}));
  } catch(e){}
});
var SAVED = null;
try { SAVED = JSON.parse(sessionStorage.getItem('map-state') || 'null'); } catch(e){}
if(SAVED && SAVED.mode){
  MODE = SAVED.mode;
  document.getElementById('m-horizon').classList.toggle('on', MODE === 'horizon');
  document.getElementById('m-web').classList.toggle('on', MODE === 'web');
  scrubUI();
  draw();
  view.tx = SAVED.tx; view.ty = SAVED.ty; view.k = SAVED.k || 1;
  applyT();
  if(SAVED.open){
    var reopen = null;
    NODES.forEach(function(n){ if(n.name === SAVED.open && visible(n)) reopen = n; });
    if(reopen) show(reopen, true);
  }
} else { draw(); fit(); }
// A direct door: index's "Circles view" button lands here already in mode.
if(location.hash === '#circles' && MODE !== 'circles') setMode('circles');

var VER = null, verFastT = null;
function verCheck(){
  fetch('/api/version').then(function(r){ return r.json(); }).then(function(j){
    if(VER === null){ VER = j.version; return; }
    if(j.building) return;             // the fresh page hasn't landed yet
    if(j.version !== VER) location.reload();       // pagehide keeps the camera
  }).catch(function(){});
}
verCheck();                            // baseline now, not 20 s from now
setInterval(function(){ if(!document.hidden) verCheck(); }, 20000);
// An action just wrote the brain: the rebuild runs behind the scenes, so
// check fast for a minute — the canonical page swaps in the moment it lands.
function nudgePoll(){
  if(verFastT) return;
  var n = 0;
  verFastT = setInterval(function(){
    n++;
    if(n > 24){ clearInterval(verFastT); verFastT = null; return; }
    if(!document.hidden) verCheck();
  }, 2500);
}

// The same queue visibility the brain page has: waiting work and live runs
// show here too, so leaving for the map never means losing sight of Claude.
var mapbar = document.getElementById('mapbar'), mbTimer = null;
function mbPoll(){
  fetch('/api/agent').then(function(r){ return r.json(); }).then(function(j){
    if(j.running){
      mapbar.hidden = false;
      document.getElementById('mb-txt').textContent = 'Claude is working\\u2026';
      document.getElementById('mb-run').style.display = 'none';
      if(!mbTimer) mbTimer = setInterval(mbPoll, 3000);
    } else {
      if(mbTimer){ clearInterval(mbTimer); mbTimer = null; }
      if(j.pending > 0){
        mapbar.hidden = false;
        document.getElementById('mb-txt').textContent =
          j.pending + ' waiting for Claude';
        document.getElementById('mb-run').style.display = '';
      } else mapbar.hidden = true;
    }
  }).catch(function(){ mapbar.hidden = true; });
}
document.getElementById('mb-run').onclick = function(){
  if(!confirm('Start Claude Code to work the queue? Runs on your Mac, on your subscription.')) return;
  fetch('/api/agent', {method:'POST', headers:{'Content-Type':'application/json'},
                       body: JSON.stringify({job:'queue'})})
    .then(function(){ mbPoll(); }).catch(function(){});
};
mbPoll();
</script>
__TOUR__</body></html>
"""


if __name__ == "__main__":
    path, n = build()
    print(f"Built {path} — {n} open workstream{'s' if n != 1 else ''}")

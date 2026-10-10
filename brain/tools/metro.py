"""Your lines: the whole plate drawn as a subway map, for the New York style.

Each area of her life is a line in its colour (lines.py). The lines leave a
"Today" interchange side by side, like a trunk, and peel off at 45 degrees
to their own rows, so no two lines ever run on top of each other. Its live
projects are the stations, the most pressing nearest the interchange, so a
long line is a busy area and a stub is a quiet one. Station names are set
at an angle, as on a transit map. A filled stop needs her, a red ring is
past its date, and a stop opens its project like any pill does
(data-wsopen). It is skin furniture (.skinx): every other style hides it.
"""
from html import escape as _e

import lines as LN

ROW = 84              # between lines; room for the angled names above
TOPPAD = 74           # above the first line, for its names
HX = 40               # the interchange's centre
BUNDLE = 13           # between lines where they run side by side
STEP, STEP_MIN = 118, 92
LABEL_CHARS = 18


def _clip(s, n=LABEL_CHARS):
    return s if len(s) <= n else s[:n - 1].rstrip() + "…"


def _own(name):
    s = name[8:] if name.upper().startswith("URGENT: ") else name
    s = s.split(" — ")[0].strip()
    if ": " in s:                      # "Brain: smarter context" -> "Smarter context"
        rest = s.split(": ", 1)[1].strip()
        s = rest[:1].upper() + rest[1:]
    return s


def _labels(live, rlab):
    """A station's name: its room's short name, unless two projects share a
    room ("Tasks from Dad" and "Family" both sit in Family): then each keeps
    its own name, so no stop shows up twice on the map."""
    want = {w["name"]: _own(rlab.get(w["name"]) or w["name"]) for w in live}
    seen = {}
    for v in want.values():
        seen[v] = seen.get(v, 0) + 1
    return {n: (v if seen[v] == 1 else _own(n)) for n, v in want.items()}


def _routes(n):
    """Each line's row, its place in the trunk, and where it peels off.

    Lines above the middle peel upward, the outermost first; lines below
    mirror them. Each turn sits 5px after the one outside it, which keeps
    the parallel diagonals one trunk-gap apart and never lets them cross."""
    rows = [TOPPAD + i * ROW for i in range(n)]
    hub_y = (rows[0] + rows[-1]) / 2
    out = []
    for i, y in enumerate(rows):
        yb = hub_y + (i - (n - 1) / 2) * BUNDLE
        rank = i if y < yb else (n - 1 - i)
        xt = HX + 40 + rank * 5
        out.append((y, yb, xt, xt + abs(y - yb)))
    return hub_y, out


def render(live, urgent, overdue, rlab):
    """The map's section, "" when there is nothing to draw."""
    order = list(LN.table())
    by = {}
    for w in live:
        a = w.get("area") or ""
        if a in order:
            by.setdefault(a, []).append(w)
    lines = [a for a in order if by.get(a)]
    if not lines:
        return ""
    label = _labels([w for a in lines for w in by[a]], rlab)
    first = {w["name"]: i for i, w in enumerate(urgent)}
    late = {w["name"] for w in overdue}
    for a in lines:
        by[a].sort(key=lambda w: (first.get(w["name"], 999),
                                  -(w.get("score") or 0), w["name"].lower()))
    n = len(lines)
    hub_y, routes = _routes(n)
    x0 = max(r[3] for r in routes) + 40
    longest = max(len(by[a]) for a in lines)
    step = STEP if longest < 2 else max(STEP_MIN, min(STEP, 640 / (longest - 1)))

    paths, stops, ends, right = [], [], [], 0
    for a, (y, yb, xt, xr) in zip(lines, routes):
        letter = LN.table()[a][0]
        last = x0 + (len(by[a]) - 1) * step
        tail = last + 36
        lc = LN.colour_attr(a)
        paths.append(f'<path class="mline"{lc} d="M{HX},{yb:.0f} L{xt:.0f},{yb:.0f} '
                     f'L{xr:.0f},{y:.0f} L{tail:.0f},{y:.0f}"/>')
        ends.append(f'<g class="mend"{lc}><circle cx="{tail + 14:.0f}" cy="{y:.0f}" r="14"/>'
                    f'<text x="{tail + 14:.0f}" y="{y + 5:.0f}">{_e(letter)}</text>'
                    f'<title>{_e(a)}</title></g>')
        right = max(right, tail + 30)
        for j, w in enumerate(by[a]):
            x = x0 + j * step
            cls = ("mst" + (" mneed" if w["name"] in first else "")
                   + (" mlate" if w["name"] in late else ""))
            tx, ty = x + 5, y - 13
            name = _clip(label[w["name"]])
            stops.append(
                f'<g class="{cls}" data-wsopen="{_e(w["name"])}" role="button" tabindex="0">'
                f'<title>{_e(w["name"])}</title>'
                f'<circle cx="{x:.0f}" cy="{y:.0f}" r="7"/>'
                f'<text x="{tx:.0f}" y="{ty:.0f}" transform="rotate(-30 {tx:.0f} {ty:.0f})">'
                f'{_e(name)}</text></g>')
            right = max(right, tx + len(name) * 6.2 + 12)
    top, bot = routes[0][1] - BUNDLE, routes[-1][1] + BUNDLE
    hub = (f'<g class="mhub"><rect x="{HX - 13}" y="{top:.0f}" width="26" '
           f'height="{bot - top:.0f}" rx="13"/>'
           f'<text x="{HX}" y="{bot + 22:.0f}">Today</text></g>')
    height = routes[-1][0] + 40
    svg = (f'<svg class="metro" viewBox="0 0 {right:.0f} {height:.0f}" role="img" '
           f'aria-label="Your areas as subway lines, with their projects as stations">'
           + "".join(paths) + hub + "".join(stops) + "".join(ends) + "</svg>")
    return ('<section class="skinx skinx-metro"><p class="eyebrow">Your lines</p>'
            f'<div class="metrowrap">{svg}</div>'
            '<p class="meta">A filled stop needs you; a red ring is past its date. '
            'Tap a stop to open it.</p></section>')

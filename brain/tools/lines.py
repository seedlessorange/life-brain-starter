"""The areas of her life as subway lines: a letter and a colour each.

Only the New York style draws them. The page builder writes them on every
area heading as data-line (the letter) and data-lc (the colour); every
other style ignores both. Colours come from config `lines` ({area: colour})
so they never move when an area is added; an area missing there takes the
first free colour, in alphabetical order. A workstream group inside an
area (School's Courses, Venture) keeps its area's colour and takes its own
letter, the way the subway's A, C and E are all blue.
"""
import model as M

COLOURS = ("blue", "orange", "purple", "brown", "lime",
           "red", "green", "yellow", "grey")
# The subway's trunk-line colours, the same table nyc.css maps data-lc to
HEX = {"blue": "#0039A6", "orange": "#FF6319", "purple": "#B933AD",
       "brown": "#996633", "lime": "#6CBE45", "red": "#EE352E",
       "green": "#00933C", "yellow": "#FCCC0A", "grey": "#808183"}
_TABLE = {}


def _letter(name, taken):
    """The name's first letter or digit not already on another line."""
    for ch in name.upper():
        if ch.isalnum() and ch not in taken:
            taken.add(ch)
            return ch
    return (name[:1] or "?").upper()


def _table():
    if not _TABLE:
        cfg = M.load_config()
        pinned = {a: c for a, c in (cfg.get("lines") or {}).items()
                  if c in COLOURS}
        rest = sorted({a for a in M._ws_areas().values()
                       if a and a not in pinned}, key=str.lower)
        colour, used = dict(pinned), set(pinned.values())
        for a in rest:
            free = [c for c in COLOURS if c not in used] or list(COLOURS)
            colour[a] = free[0]
            used.add(free[0])
        taken = set()
        _TABLE.update({a: (_letter(a, taken), colour[a])
                       for a in list(pinned) + rest})
    return _TABLE


def table():
    """{area: (letter, colour)} in line order: pinned areas first."""
    return dict(_table())


_WS = {}


def ws_area(ws):
    """The area a workstream belongs to, "" when it has none."""
    if not _WS:
        _WS.update(M._ws_areas())
    return _WS.get(ws or "", "")


def colour_attr(area):
    """' data-lc="blue"' for anything that rides an area's line without
    naming it (a project pill, a stop on the day, a group of rows)."""
    line = _table().get(area or "")
    return ' data-lc="%s"' % line[1] if line else ""


def ws_attr(ws):
    return colour_attr(ws_area(ws))


def attrs(area, label=None, taken=None):
    """' data-line="S" data-lc="blue"' for an area heading, "" when the area
    is unknown. Pass `label` for a group inside the area and one `taken` set
    per list, so its letters stay unique."""
    line = _table().get(area or "")
    if not line:
        return ""
    ch = line[0]
    if label and label != area:
        ch = _letter(label, taken if taken is not None else set())
    return ' data-line="%s" data-lc="%s"' % (ch, line[1])


def strip_css():
    """Her lines in order, as the New York style's header strip and the
    tiles round Today's title, so both follow her colours (Dad went from
    brown to red, 9 Oct) instead of a fixed five."""
    cols = [HEX[c] for _l, c in _table().values()][:6]
    if not cols:
        return ""
    n = len(cols)
    strip = ",".join("%s %.2f%% %.2f%%" % (c, i * 100 / n, (i + 1) * 100 / n)
                     for i, c in enumerate(cols))
    tiles = ",".join("%s %dpx %dpx,var(--paper) %dpx %dpx"
                     % (c, i * 15, i * 15 + 13, i * 15 + 13, i * 15 + 15)
                     for i, c in enumerate(cols))
    return (':root[data-style="nyc"]{--ny-strip:linear-gradient(90deg,%s);'
            "--ny-tiles:repeating-linear-gradient(90deg,%s)}" % (strip, tiles))

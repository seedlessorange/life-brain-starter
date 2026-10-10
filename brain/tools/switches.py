"""Every tab switch on every page, drawn one way per style.

The page has seven of them, written in five files: the view switches
(List · Week · Map, Needs you · Everyone · Circles, Overview · Season ·
Kitchen · Routine), the gear's sub-row, the Season's range, the map's
Horizon · Web, the settings toggles on Usage and Privacy, and the
Kitchen's own section tabs. Each file used to draw its own, so inside one
style the chosen tab was a dark pill in one place, a white chip in the
next and a pale fill in a third, and each style's skin dressed a
different subset of them (8 Oct review).

Now each family's own CSS keeps only its layout, and the look lives here,
read from a handful of --sw-* settings that every style sets once. A new
style that sets none gets the Workroom switch, never a broken one.

Three kinds, one family each:
- a SWITCH between views of a page (the view switches, the gear's row,
  the map's modes, which share the map's bar with List · Week · Map);
- the same switch one size down for a picker inside a page (the Season's
  range, the settings toggles);
- SECTION TABS within a page (the Kitchen): underlined words, so they never
  stack under the Life switch as its twin.

palette_css() ships this on every page, after the active skin, so these
rules win over anything a skin still says about the same elements.
"""

# The switch, by default (Workroom): a pill track, the chosen view inked.
_DEFAULTS = (
    "--sw-bg:var(--surface);--sw-bd:1px solid var(--line2);--sw-r:999px;"
    "--sw-pad:3px;--sw-gap:2px;--sw-sh:none;--sw-ir:999px;"
    "--sw-div:0 solid transparent;"
    "--sw-ff:var(--sans);--sw-fw:500;--sw-fs:13px;--sw-fs2:12px;"
    "--sw-tt:none;--sw-ls:0;--sw-ip:7px 14px;--sw-ip2:5px 11px;"
    "--sw-off:var(--dim);"
    "--sw-hov:color-mix(in oklab,var(--ink) 7%,transparent);"
    "--sw-on-bg:var(--ink);--sw-on-fg:var(--paper);--sw-on-fw:600;"
    "--sw-on-sh:none;"
    "--tab-line:var(--green);--tab-lw:2px;--tab-gap:22px;"
    "--tab-rule:1px solid var(--line)")

# Each style's switch, in its own language. Only what differs is set.
STYLE_VARS = {
    "workroom": "",
    # a finely printed broadsheet: square, ink hairline, the amber rule
    "print": (
        "--sw-bg:var(--paper);--sw-bd:1.5px solid var(--ink);--sw-r:0;"
        "--sw-pad:2px;--sw-ir:0;"
        "--sw-on-sh:inset 0 -3px 0 var(--pr-amber,var(--terra));"
        "--tab-line:var(--pr-amber,var(--terra));--tab-lw:3px"),
    # ink outlines, offset shadows, candy tints
    "softbrut": (
        "--sw-bd:2px solid var(--line2);--sw-r:16px;--sw-gap:3px;--sw-ir:12px;"
        "--sw-sh:3px 3px 0 color-mix(in oklab,var(--ink) 70%,transparent);"
        "--sw-fw:600;--sw-on-bg:var(--sb-amber,var(--waitbg));"
        "--sw-on-fg:var(--ink);--sw-on-fw:800;"
        "--sw-on-sh:inset 0 0 0 2px var(--line2);"
        "--tab-line:var(--ink);--tab-lw:3px"),
    # editorial: a hairline track on the paper, the chosen view an ink pill
    "midcentury": (
        "--sw-bg:transparent;--sw-r:24px;--sw-ir:20px;"
        "--tab-line:var(--terra)"),
    # a spec sheet: one fused square strip, typed in mono capitals
    "manual": (
        "--sw-bg:transparent;--sw-r:0;--sw-pad:0;--sw-gap:0;--sw-ir:0;"
        "--sw-div:1px solid var(--line2);"
        "--sw-ff:var(--mono,ui-monospace,monospace);--sw-fw:600;"
        "--sw-fs:10.5px;--sw-fs2:10px;--sw-tt:uppercase;--sw-ls:.08em;"
        "--sw-ip:10px 13px;--sw-ip2:8px 11px;--sw-hov:var(--sunken);"
        "--tab-line:var(--fm-signal,var(--terra))"),
    # the geometry teacher: a 2px ink block, the chosen view filled solid
    "bauhaus": (
        "--sw-bd:2px solid var(--ink);--sw-r:0;--sw-pad:0;--sw-gap:0;"
        "--sw-ir:0;--sw-div:2px solid var(--ink);"
        "--sw-ff:var(--serif);--sw-fw:600;--sw-fs:11.5px;--sw-fs2:11px;"
        "--sw-tt:uppercase;--sw-ls:.08em;--sw-ip:9px 14px;--sw-ip2:7px 12px;"
        "--sw-hov:var(--sunken);"
        "--tab-line:var(--ink);--tab-lw:4px"),
    # two inks on cream: blue track, the chosen view printed solid blue
    "riso": (
        "--sw-bg:transparent;--sw-bd:1.5px solid var(--ink);--sw-r:4px;"
        "--sw-ir:2px;--sw-fw:600;"
        "--tab-line:var(--ri-pink,var(--terra));--tab-lw:3px"),
    # a dark command deck: a hairline track, the chosen side lit
    "orbit": (
        "--sw-bg:transparent;--sw-r:6px;--sw-pad:2px;--sw-ir:4px;"
        "--sw-hov:color-mix(in oklab,var(--ink) 10%,transparent)"),
}

_SWITCH = ".pvnav,.clsub,.szviews,.modes,.useg"
_ITEM = ".pvnav>a,.clsub>a,.szviews>button,.modes>button,.useg>button"
_SMALL = ".szviews>button,.useg>button"

# html[data-style] lifts every rule above the families' own CSS and the
# skins' (main a, :is() blankets) without !important.
_RULES = """
html[data-style] :is(%(sw)s){display:inline-flex;align-items:center;
  gap:var(--sw-gap);padding:var(--sw-pad);border:var(--sw-bd);
  border-radius:var(--sw-r);background:var(--sw-bg);box-shadow:var(--sw-sh);
  overflow:hidden}
html[data-style] :is(%(it)s){display:inline-flex;align-items:center;gap:6px;
  margin:0;border:0;border-radius:var(--sw-ir);background:transparent;
  box-shadow:none;cursor:pointer;text-decoration:none;white-space:nowrap;
  font:var(--sw-fw) var(--sw-fs)/1.15 var(--sw-ff);
  text-transform:var(--sw-tt);letter-spacing:var(--sw-ls);
  color:var(--sw-off);padding:var(--sw-ip)}
html[data-style] :is(%(sm)s){font-size:var(--sw-fs2);padding:var(--sw-ip2)}
html[data-style] :is(%(it)s)+:is(a,button){border-left:var(--sw-div)}
html[data-style] :is(%(it)s):hover:not(.on){background:var(--sw-hov);
  color:var(--ink)}
html[data-style] :is(%(it)s).on{background:var(--sw-on-bg);
  color:var(--sw-on-fg);font-weight:var(--sw-on-fw);box-shadow:var(--sw-on-sh)}
html[data-style] :is(%(it)s):focus-visible{outline:2px solid var(--green);
  outline-offset:-2px}
html[data-style] :is(%(it)s):disabled{opacity:.45;cursor:default}

html[data-style] .ktabs{display:flex;width:max-content;max-width:100%%;
  gap:var(--tab-gap);padding:0;border:0;border-bottom:var(--tab-rule);
  border-radius:0;background:transparent;box-shadow:none}
html[data-style] .ktabs>a{margin:0 0 -1px;padding:10px 1px 9px;border:0;
  border-bottom:var(--tab-lw) solid transparent;border-radius:0;
  background:transparent;box-shadow:none;text-decoration:none;
  white-space:nowrap;font:var(--sw-fw) var(--sw-fs)/1.15 var(--sw-ff);
  text-transform:var(--sw-tt);letter-spacing:var(--sw-ls);color:var(--sw-off)}
html[data-style] .ktabs>a:hover{color:var(--ink)}
html[data-style] .ktabs>a.on{color:var(--ink);font-weight:var(--sw-on-fw);
  border-bottom-color:var(--tab-line)}

@media (max-width:760px){
  html[data-style] :is(.pvnav,.clsub)>a{padding-left:10px;padding-right:10px}
  html[data-style] :is(.pvnav,.clsub,.ktabs){max-width:100%%;overflow-x:auto;
    scrollbar-width:none}
  html[data-style] :is(.pvnav,.clsub,.ktabs)::-webkit-scrollbar{display:none}
  html[data-style] .ktabs{gap:16px}
}
""" % {"sw": _SWITCH, "it": _ITEM, "sm": _SMALL}


def css():
    """The switches' look for every style, in one block for palette_css()."""
    blocks = [":root{" + _DEFAULTS + "}"]
    for key, decl in STYLE_VARS.items():
        if decl:
            blocks.append(':root[data-style="%s"]{%s}' % (key, decl))
    return "\n".join(blocks) + "\n" + _RULES

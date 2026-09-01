"""The brain's visual skins.

Two layers per skin:
- a PREVIEW block (small, shipped for every skin on every page) — the token
  approximation that lets the picker restyle instantly;
- a FULL stylesheet (skins/<key>.css, baked only for the ACTIVE skin at
  build time) plus its vendored fonts — the real look, faithful to the
  mockups in design/skins/ (specs in design/skins/SPECS.md).

State-color MEANINGS survive every skin; faces and dots stay round.
"""
import os as _os

# ---------------------------------------------------------------- styles
# A STYLE is the page's whole posture — corner radii, borders, shadows, the
# display face, how loud the tint washes are — while the PALETTE stays the
# owner of hue. Two independent axes, like circle and rhythm. The six styles
# come from DESIGN-STYLES.md; "workroom" is the incumbent and deliberately
# empty. Every block is written against the BASE tokens (--ink/--paper/
# --line/--greenbg…) so the aliases follow and both themes adapt through
# color-mix instead of needing hand-tuned dark twins — except where a style
# PINS state hues (bauhaus), which carries its own dark blocks.

# The hand-drawn squiggle is drawn two ways (a .wav element, and ::after on
# section titles); a style that turns it off must silence both.
_SQUIG = ([".wav"] +
          [s + "::after" for s in (
              "h3.area", ".qcard .eyebrow", ".offercard .eyebrow",
              "#queue>h2", "#drafts>h2", "#connections>h2", "#recordings>h2",
              "#newfiles>h2", "#people>h2", "#attention>h2", "#all>h2",
              ".doc h2", ".todaydoc h2")])

# The big boxed surfaces, for styles whose signature lives on the card edge
# (outlines, offset shadows). Most of these draw their own border rather
# than riding a token, so the styles address them by name.
_CARDS = (".railcard,.panel,.todaywrap,.hzcard,.offercard,.bscard,.qcard,"
          ".daycard,.dupcard,.forecast,.draftcard,.stackrow,.appanel")


def _card_rule(key, body):
    sels = ",".join('[data-style="%s"] %s' % (key, s) for s in _CARDS.split(","))
    return sels + "{" + body + "}\n"


def _no_squiggle(key):
    sels = ",".join('[data-style="%s"] %s' % (key, s) for s in _SQUIG)
    return sels + "{display:none}\n"


_BAUHAUS_DARK = ("--bad:oklch(71% .14 30);--badbg:oklch(30% .06 30);"
                 "--wait:oklch(78% .12 85);--waitbg:oklch(32% .055 88);"
                 "--cold:oklch(74% .1 255);--coldbg:oklch(30% .045 252);"
                 "--terra:oklch(73% .11 55);")

STYLES = {
    "workroom": {
        "label": "Workroom", "note": "the current look — warm paper, soft ink",
        "chip": ("border-radius:7px;border:1px solid var(--line2);"
                 "box-shadow:0 1px 2px color-mix(in oklab,var(--ink) 14%,transparent);"
                 "font-family:var(--serif);font-weight:800"),
        "css": "",
    },
    "print": {
        "label": "Print Shop", "note": "a finely printed broadsheet — dark hairlines, mono margins",
        "chip": ("border-radius:3px;border:1.5px solid var(--ink);"
                 "font-family:ui-monospace,Menlo,monospace"),
        "css": (
            ':root[data-style="print"]{'
            "--r-xl:9px;--r-lg:8px;--r-card:7px;--r-md:6px;--r-btn:5px;--r-sm:4px;"
            "--line:color-mix(in oklab,var(--ink) 24%,var(--paper));"
            "--line2:color-mix(in oklab,var(--ink) 56%,var(--paper));"
            "--shadow:none;"
            "--shadow-lift:0 16px 32px -24px color-mix(in oklab,var(--ink) 60%,transparent)}\n"
            '[data-style="print"] .meta{font-family:ui-monospace,Menlo,monospace;'
            "font-size:.71rem;letter-spacing:.04em}\n"
            '[data-style="print"] .eyebrow,[data-style="print"] .area{'
            "font-family:ui-monospace,Menlo,monospace;letter-spacing:.2em;font-weight:600}\n"
        ) + _card_rule("print",
                       "border:1.5px solid color-mix(in oklab,var(--ink) 56%,var(--paper))"),
    },
    "softbrut": {
        "label": "Soft Brutalism", "note": "ink outlines, offset shadows, candy tints — the family-hub look",
        "chip": ("border-radius:9px;border:2px solid var(--ink);"
                 "box-shadow:3px 3px 0 var(--ink);"
                 "font-family:'Bricolage',sans-serif;font-weight:800"),
        "css": (
            ':root[data-style="softbrut"]{'
            "--r-xl:24px;--r-lg:20px;--r-card:16px;--r-md:14px;--r-btn:12px;--r-sm:10px;"
            "--serif:'Bricolage',Georgia,sans-serif;"
            "--line:color-mix(in oklab,var(--ink) 38%,var(--paper));"
            "--line2:color-mix(in oklab,var(--ink) 74%,var(--paper));"
            "--shadow:3px 3px 0 color-mix(in oklab,var(--ink) 70%,transparent);"
            "--shadow-lift:6px 6px 0 color-mix(in oklab,var(--ink) 70%,transparent);"
            "--sunken:color-mix(in oklab,var(--ink) 6%,var(--paper));"
            "--greenbg:color-mix(in oklab,var(--green) 20%,var(--paper));"
            "--badbg:color-mix(in oklab,var(--bad) 18%,var(--paper));"
            "--waitbg:color-mix(in oklab,var(--wait) 22%,var(--paper));"
            "--coldbg:color-mix(in oklab,var(--cold) 18%,var(--paper))}\n"
            '[data-style="softbrut"] .ballpill{box-shadow:inset 0 0 0 1.5px '
            "color-mix(in oklab,currentColor 45%,transparent)}\n"
        ) + _card_rule("softbrut",
                       "border:2px solid color-mix(in oklab,var(--ink) 74%,var(--paper));"
                       "box-shadow:3px 3px 0 color-mix(in oklab,var(--ink) 70%,transparent)"),
    },
    "midcentury": {
        "label": "Mid-century", "note": "editorial serif, warm optimism, little arc marks",
        "chip": ("border-radius:7px 7px 0 7px;border:1px solid var(--line2);"
                 "background:color-mix(in oklab,var(--terra) 18%,var(--paper));"
                 "font-family:'Literata',serif;font-weight:600"),
        "css": (
            ':root[data-style="midcentury"]{'
            "--r-xl:16px;--r-lg:14px;--r-card:12px;--r-md:10px;--r-btn:9px;--r-sm:7px;"
            "--serif:'Literata',Georgia,serif;"
            "--shadow:none;"
            "--shadow-lift:0 20px 44px -26px color-mix(in oklab,var(--ink) 45%,transparent);"
            "--greenbg:color-mix(in oklab,var(--green) 15%,var(--paper))}\n"
            '[data-style="midcentury"] .coach{font-size:1.07em}\n'
            '[data-style="midcentury"] .hero h1{font-weight:800}\n'
            '[data-style="midcentury"] .eyebrow::before{content:"";display:inline-block;'
            "width:9px;height:9px;background:var(--terra);border-radius:9px 9px 0 9px;"
            "margin-right:7px;vertical-align:-1px}\n"
        ),
    },
    "manual": {
        "label": "Field Manual", "note": "spec-sheet flat — hairline rules, mono labels, color as marks",
        "chip": ("border-radius:2px;border:1px solid var(--ink);"
                 "font-family:ui-monospace,Menlo,monospace;letter-spacing:.06em"),
        "css": (
            ':root[data-style="manual"]{'
            "--r-xl:3px;--r-lg:3px;--r-card:2px;--r-md:2px;--r-btn:2px;--r-sm:2px;"
            "--serif:'Darker','Schibsted',-apple-system,sans-serif;"
            "--surface:var(--paper);"
            "--sunken:color-mix(in oklab,var(--ink) 5%,var(--paper));"
            "--line:color-mix(in oklab,var(--ink) 20%,var(--paper));"
            "--line2:color-mix(in oklab,var(--ink) 38%,var(--paper));"
            "--shadow:none;"
            "--shadow-lift:0 12px 26px -20px color-mix(in oklab,var(--ink) 55%,transparent);"
            "--greenbg:color-mix(in oklab,var(--green) 11%,var(--paper));"
            "--badbg:color-mix(in oklab,var(--bad) 10%,var(--paper));"
            "--waitbg:color-mix(in oklab,var(--wait) 12%,var(--paper));"
            "--coldbg:color-mix(in oklab,var(--cold) 10%,var(--paper))}\n"
            '[data-style="manual"] .meta{font-family:ui-monospace,Menlo,monospace}\n'
            '[data-style="manual"] .eyebrow,[data-style="manual"] .area{'
            "font-family:ui-monospace,Menlo,monospace;letter-spacing:.18em;font-weight:600}\n"
            '[data-style="manual"] .hero h1{font-weight:800;letter-spacing:.01em}\n'
            + _no_squiggle("manual")
        ) + _card_rule("manual",
                       "border:1px solid var(--line);box-shadow:none"),
    },
    "bauhaus": {
        "label": "Bauhaus", "note": "sharp grid, muted primaries, square marks — form follows function",
        "chip": ("border-radius:0;border:2px solid var(--ink);"
                 "font-family:Futura,'Avenir Next',sans-serif;letter-spacing:.02em"),
        "css": (
            ':root[data-style="bauhaus"]{'
            "--r-xl:0px;--r-lg:0px;--r-card:0px;--r-md:0px;--r-btn:0px;--r-sm:0px;"
            "--serif:'Futura','Avenir Next','Figtree',sans-serif;"
            "--line:color-mix(in oklab,var(--ink) 30%,var(--paper));"
            "--line2:color-mix(in oklab,var(--ink) 68%,var(--paper));"
            "--shadow:none;"
            "--shadow-lift:10px 10px 0 color-mix(in oklab,var(--ink) 12%,var(--paper));"
            "--bad:oklch(51% .16 30);--badbg:oklch(92.5% .05 30);"
            "--wait:oklch(60% .14 82);--waitbg:oklch(93.5% .06 88);"
            "--cold:oklch(44% .12 258);--coldbg:oklch(92.5% .035 252);"
            "--terra:oklch(56% .13 50)}\n"
            '@media (prefers-color-scheme:dark){:root[data-style="bauhaus"]'
            ':not([data-theme="light"]){' + _BAUHAUS_DARK + "}}\n"
            ':root[data-style="bauhaus"][data-theme="dark"]{' + _BAUHAUS_DARK + "}\n"
            '[data-style="bauhaus"] .ballpill{border-radius:0}\n'
            '[data-style="bauhaus"] .eyebrow{letter-spacing:.24em}\n'
            '[data-style="bauhaus"] .eyebrow::before{content:"";display:inline-block;'
            "width:8px;height:8px;background:var(--green);margin-right:7px}\n"
            + _no_squiggle("bauhaus")
        ) + _card_rule("bauhaus",
                       "border:2px solid color-mix(in oklab,var(--ink) 68%,var(--paper))"),
    },
}


def style_css():
    """Every style's rules, shipped on every page — switching is an attribute
    flip, so the picker can preview instantly before the rebuild lands."""
    return "\n".join(s["css"] for s in STYLES.values() if s["css"])


def style_chips(cfg):
    """The style picker: each chip is a tiny specimen of its style — its own
    border, corner and shadow around an Aa in its display face."""
    ap = (cfg.get("appearance") or {})
    cur = ap.get("style") or "workroom"
    out = []
    for key, s in STYLES.items():
        on = " on" if key == cur else ""
        out.append(
            f'<button class="stchip{on}" data-style="{key}" title="{s["note"]}">'
            f'<span class="stbox" aria-hidden="true" style="{s["chip"]}">Aa</span>'
            f'<span class="pallabel">{s["label"]}</span></button>')
    return "".join(out)


SKINS = STYLES            # canonical name; build.py re-exports STYLES
preview_css = style_css   # every skin's small preview block
chips = style_chips       # the picker

_DIR = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "skins")

# Which vendored font files each skin's FULL stylesheet needs. The files live
# in brain/fonts/ (latin subsets); faces are emitted only for the active skin.
FONT_FILES = {
    "print":      ["hanken", "hanken-i", "spline-mono", "newsreader-i"],
    "softbrut":   ["figtree-full", "hanken", "hanken-i", "newsreader-i"],
    "midcentury": ["instrument", "instrument-i", "karla", "newsreader-i"],
    "manual":     ["archivo", "plex-sans", "plex-mono", "newsreader-i"],
    "bauhaus":    ["jost", "public-sans", "newsreader-i"],
}

_FACE = "@font-face{font-family:'%s';src:url('fonts/%s.woff2') format('woff2');font-weight:%s;font-style:%s;font-display:swap}"
FACES = {
    "hanken":        _FACE % ("Hanken Grotesk", "hanken", "400 700", "normal"),
    "hanken-i":      _FACE % ("Hanken Grotesk", "hanken-i", "400 700", "italic"),
    "spline-mono":   _FACE % ("Spline Sans Mono", "spline-mono", "400 600", "normal"),
    "newsreader-i":  _FACE % ("Newsreader", "newsreader-i", "400 600", "italic"),
    "instrument":    _FACE % ("Instrument Serif", "instrument", "400", "normal"),
    "instrument-i":  _FACE % ("Instrument Serif", "instrument-i", "400", "italic"),
    "karla":         _FACE % ("Karla", "karla", "300 800", "normal"),
    "archivo":       _FACE % ("Archivo", "archivo", "400 800", "normal"),
    "plex-sans":     (_FACE % ("IBM Plex Sans", "plex-sans", "400", "normal")
                      + _FACE % ("IBM Plex Sans", "plex-sans-500", "500", "normal")
                      + _FACE % ("IBM Plex Sans", "plex-sans-600", "600", "normal")),
    "plex-mono":     (_FACE % ("IBM Plex Mono", "plex-mono", "400", "normal")
                      + _FACE % ("IBM Plex Mono", "plex-mono-500", "500", "normal")
                      + _FACE % ("IBM Plex Mono", "plex-mono-600", "600", "normal")),
    "jost":          _FACE % ("Jost", "jost", "400 700", "normal"),
    "public-sans":   _FACE % ("Public Sans", "public-sans", "400 700", "normal"),
    "figtree-full":  _FACE % ("Figtree Full", "figtree-full", "300 900", "normal"),
}


def active(cfg):
    return ((cfg.get("appearance") or {}).get("style")) or "workroom"


def full_css(key):
    """The active skin's real stylesheet — empty until its file exists."""
    try:
        with open(_os.path.join(_DIR, key + ".css"), encoding="utf-8") as f:
            return f.read()
    except OSError:
        return ""


def faces_css(key):
    return "\n".join(FACES[s] for s in FONT_FILES.get(key, []) if s in FACES)

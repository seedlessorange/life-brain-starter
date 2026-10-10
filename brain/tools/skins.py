"""The brain's visual skins.

Two layers per skin:
- a PREVIEW block (small, shipped for every skin on every page) — the token
  approximation that lets the picker restyle instantly;
- a FULL stylesheet (skins/<key>.css, baked only for the ACTIVE skin at
  build time) plus its vendored fonts — the real look, faithful to the
  mockups in design/skins/ (specs in design/skins/SPECS.md).

State-color MEANINGS survive every skin; faces and dots stay round.

Each style also has a picture in the look picker (brain/art/looks/). After
changing how a style looks, re-shoot it: `python3 brain/tools/look_shots.py
<key>`; `--check` lists the stale ones.
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


_RISO_DARK = ("--paper:#1e2233;--surface:#1e2233;--ink:#f1e8d4;"
              "--line:color-mix(in oklab,var(--ink) 18%,var(--paper));"
              "--line2:color-mix(in oklab,var(--ink) 45%,var(--paper));"
              "--bad:oklch(70% .15 27);--wait:oklch(80% .12 85);"
              "--cold:oklch(74% .11 245);--terra:oklch(74% .13 50);--ok:oklch(75% .13 155);")

_NYC_DARK = ("--paper:#101010;--surface:#181818;--ink:#f2f2f2;--dim:#c4c4c4;"
             "--faint:#9a9a9a;--line:#2e2e2e;--line2:#5a5a5a;--green:#f2f2f2;--greenbg:#232323;")

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
            + _no_squiggle("midcentury")
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
    # A two-colour riso print: Federal Blue for every word, Fluorescent Pink
    # as the second drum. The preview carries the inks and the flat cards;
    # the grain, pinholes and the misregistered heads live in skins/riso.css.
    "riso": {
        "label": "Risograph", "note": "two inks on cream paper, a hair out of register",
        "chip": ("border-radius:2px;border:1.5px solid oklch(38.5% .1 266);"
                 "background:#f5efe2;color:oklch(30% .1 266);"
                 "text-shadow:-1.5px 1.5px 0 #ff48b0;"
                 "font-family:'Anybody','Archivo',sans-serif;font-weight:800;"
                 "font-stretch:125%"),
        "css": (
            ':root[data-style="riso"]{'
            "--r-xl:3px;--r-lg:3px;--r-card:3px;--r-md:3px;--r-btn:3px;--r-sm:2px;"
            "--paper:#f5efe2;--surface:#f5efe2;"
            "--ink:oklch(38.5% .1 266);"
            "--dim:color-mix(in oklab,var(--ink) 78%,var(--paper));"
            "--faint:color-mix(in oklab,var(--ink) 58%,var(--paper));"
            "--sunken:color-mix(in oklab,var(--ink) 7%,var(--paper));"
            "--line:color-mix(in oklab,var(--ink) 22%,var(--paper));"
            "--line2:color-mix(in oklab,var(--ink) 50%,var(--paper));"
            "--green:var(--ink);--greenbg:color-mix(in oklab,var(--ink) 10%,var(--paper));"
            "--bad:oklch(52% .19 27);--wait:oklch(56% .12 72);"
            "--cold:oklch(52% .14 245);--terra:oklch(55% .15 45);--ok:oklch(50% .13 155);"
            "--shadow:none;--shadow-lift:none}\n"
            '@media (prefers-color-scheme:dark){:root[data-style="riso"]'
            ':not([data-theme="light"]){' + _RISO_DARK + "}}\n"
            ':root[data-style="riso"][data-theme="dark"]{' + _RISO_DARK + "}\n"
            '[data-style="riso"] .evwrap{background:'
            "color-mix(in oklab,#ff48b0 34%,var(--paper));border:0}\n"
            + _no_squiggle("riso")
        ) + _card_rule("riso", "border:0;border-top:3px solid var(--ink);"
                               "border-radius:0;box-shadow:none;background:transparent"),
    },
    # The New York subway's signs: black panels in Helvetica, and a line
    # badge for each area (lines.py writes the letters and colours). The
    # preview carries the paper, the ink and the black signs; the badges,
    # the day as a subway line and the platform clock live in skins/nyc.css.
    "nyc": {
        "label": "New York", "note": "the subway's signs: black panels, Helvetica, a coloured line for each area",
        "chip": ("border-radius:4px;border:0;color:#fff;"
                 "background:linear-gradient(#fff,#fff) 0 4px/100% 1.5px no-repeat,#151515;"
                 "font-family:'Helvetica Neue',Helvetica,Arial,sans-serif;font-weight:700"),
        "css": (
            ':root[data-style="nyc"]{'
            "--r-xl:6px;--r-lg:6px;--r-card:6px;--r-md:5px;--r-btn:5px;--r-sm:4px;"
            "--paper:#f6f6f3;--surface:#fff;--ink:#141414;--dim:#4a4a4a;--faint:#6e6e6e;"
            "--line:#d9d9d4;--line2:#9a9a96;--green:#141414;--greenbg:#ececE8;"
            "--serif:'Helvetica Neue',Helvetica,Arial,sans-serif;"
            "--sans:'Helvetica Neue',Helvetica,Arial,sans-serif;"
            "--shadow:none;--shadow-lift:none}\n"
            '@media (prefers-color-scheme:dark){:root[data-style="nyc"]'
            ':not([data-theme="light"]){' + _NYC_DARK + "}}\n"
            ':root[data-style="nyc"][data-theme="dark"]{' + _NYC_DARK + "}\n"
            '[data-style="nyc"] .eyebrow,[data-style="nyc"] h3.area{background:#151515;'
            "color:#fff;text-transform:none;letter-spacing:0;padding:.5em .7em;border-radius:3px}\n"
            + _no_squiggle("nyc")
        ) + _card_rule("nyc", "border:0;border-radius:0;box-shadow:none;background:transparent"),
    },
    # Dark in both themes: it pins the base tokens outright instead of
    # mixing from them, so the light/dark switch does not move it.
    "orbit": {
        "label": "Orbit", "note": "a dark command deck under quiet stars",
        "chip": ("border-radius:6px;border:1px solid oklch(.6 .08 172);"
                 "background:oklch(.16 .012 195);color:oklch(.94 .01 175);"
                 "box-shadow:inset 0 0 0 3px oklch(.16 .012 195),"
                 "inset 0 0 0 4px oklch(.45 .06 172),0 0 14px -4px oklch(.7 .12 170);"
                 "font-family:'IBM Plex Mono',ui-monospace,Menlo,monospace;"
                 "font-weight:400;letter-spacing:.06em"),
        "css": (
            ':root[data-style="orbit"]{color-scheme:dark;'
            "--paper:oklch(.15 .01 195);--surface:oklch(.19 .013 190);"
            "--sunken:oklch(.125 .009 195);--ink:oklch(.94 .01 175);"
            "--dim:oklch(.80 .014 180);--faint:oklch(.68 .016 180);"
            "--line:oklch(.28 .014 185);--line2:oklch(.39 .02 180);"
            "--green:oklch(.84 .105 172);--greenbg:oklch(.27 .045 172);"
            "--orb:oklch(82% .13 170);--orb-listen:oklch(88% .11 195);"
            "--orb-glow:oklch(72% .13 170 / .16);"
            "--terra:oklch(.81 .085 52);"
            "--bad:oklch(.73 .13 25);--badbg:oklch(.26 .05 25);"
            "--wait:oklch(.84 .105 85);--waitbg:oklch(.27 .04 85);"
            "--cold:oklch(.77 .075 250);--coldbg:oklch(.26 .035 252);"
            "--ok:oklch(.82 .13 138);--okt:oklch(.27 .045 138);"
            "--shadow:none;--shadow-lift:0 18px 44px -22px oklch(0 0 0 / .85);"
            "--r-xl:10px;--r-lg:9px;--r-card:8px;--r-md:7px;--r-btn:6px;--r-sm:5px;"
            "--serif:'Archivo','Helvetica Neue',-apple-system,sans-serif}\n"
            '[data-style="orbit"] .eyebrow,[data-style="orbit"] .area{'
            "font-family:ui-monospace,Menlo,monospace;letter-spacing:.2em;"
            "font-weight:500;color:var(--dim)}\n"
            + _no_squiggle("orbit")
        ) + _card_rule("orbit", "border:1px solid var(--line);box-shadow:none"),
    },
}


def style_css():
    """Every style's rules, shipped on every page — switching is an attribute
    flip, so the picker can preview instantly before the rebuild lands."""
    return "\n".join(s["css"] for s in STYLES.values() if s["css"])


_LOOKS = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))),
                       "art", "looks")


def _shot_stamps():
    """Which styles have a picture (look_shots.py), and its version."""
    import json
    try:
        with open(_os.path.join(_LOOKS, "stamp.json"), encoding="utf-8") as f:
            st = json.load(f)
    except (OSError, ValueError):
        return {}
    return {k: v for k, v in st.items()
            if _os.path.exists(_os.path.join(_LOOKS, k + ".jpg"))}


def style_chips(cfg):
    """The style picker. A chip shows its style's picture: the demo brain's
    Today page in that style, so the choice is seen before the brain is
    rebuilt in it. A style without one yet shows a tiny specimen instead,
    its own border and corner around an Aa in its display face."""
    ap = (cfg.get("appearance") or {})
    cur = ap.get("style") or "workroom"
    shots = _shot_stamps()
    out = []
    for key, s in STYLES.items():
        on = " on" if key == cur else ""
        face = (f'<img class="stshot" src="art/looks/{key}.jpg?v={shots[key]}" alt=""'
                ' width="320" height="200" loading="lazy" decoding="async">'
                if key in shots else
                f'<span class="stbox" aria-hidden="true" style="{s["chip"]}">Aa</span>')
        out.append(
            f'<button class="stchip{on}" data-style="{key}" title="{s["note"]}">'
            f'{face}<span class="pallabel">{s["label"]}</span></button>')
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
    "orbit":      ["archivo-var", "darker-var", "plex-sans", "plex-mono"],
    "riso":       ["anybody"],
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
    # the same variable file, its whole weight axis: Orbit's display words
    # sit at 250-300, which the 400-800 face above would clamp to 400
    "archivo-var":   _FACE % ("Archivo", "archivo", "100 900", "normal"),
    # Darker Grotesque's narrow figures for Orbit's clock and counts, under
    # its own family name so the page's 400-800 'Darker' face is untouched
    "darker-var":    _FACE % ("Darker Grotesque", "darker", "300 900", "normal"),
    "plex-sans":     (_FACE % ("IBM Plex Sans", "plex-sans", "400", "normal")
                      + _FACE % ("IBM Plex Sans", "plex-sans-500", "500", "normal")
                      + _FACE % ("IBM Plex Sans", "plex-sans-600", "600", "normal")),
    "plex-mono":     (_FACE % ("IBM Plex Mono", "plex-mono", "400", "normal")
                      + _FACE % ("IBM Plex Mono", "plex-mono-500", "500", "normal")
                      + _FACE % ("IBM Plex Mono", "plex-mono-600", "600", "normal")),
    "jost":          _FACE % ("Jost", "jost", "400 700", "normal"),
    "public-sans":   _FACE % ("Public Sans", "public-sans", "400 700", "normal"),
    "figtree-full":  _FACE % ("Figtree Full", "figtree-full", "300 900", "normal"),
    # Risograph's heads: a variable file with a width axis, so the face
    # declares its stretch range or font-stretch would clamp to normal
    "anybody":       ("@font-face{font-family:'Anybody';src:url('fonts/anybody.woff2') "
                      "format('woff2');font-weight:100 900;font-stretch:50% 150%;"
                      "font-style:normal;font-display:swap}"),
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

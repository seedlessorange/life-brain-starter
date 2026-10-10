#!/usr/bin/env python3
"""Build brain/cook.html — the kitchen: the week's dinners, the shopping
list, and the ~6,300 recipes from her own cookbooks.

    python3 brain/tools/cook.py

GENERATED. Never hand-edit cook.html.

The recipe library lives in brain/recipes-library/ (markdown per book,
photos, and pantry_db.json with normalised ingredients — extracted from her
own EPUB/MOBI/PDF cookbooks). This script derives a compact index
(brain/cook-data.json, loaded by the page) and caches the full one with
byte offsets (brain/cooking/.recipes.json) so the detail API can hand back
any recipe's method without re-parsing 13 MB of markdown.

Her state lives in brain/cooking/ as plain markdown she can edit by hand:
plan.md (the week's dinners), shopping.md (tickable, her additions kept),
pantry.md (staples + fresh), cooked.md (the log + saved recipes). The page
writes them through /api/cook/* in serve.py, which calls api() here.
"""

import html
import json
import os
import re
import sys
from datetime import date, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

BRAIN = os.path.dirname(HERE)
LIB = os.path.join(BRAIN, "recipes-library")
COOKDIR = os.path.join(BRAIN, "cooking")
CACHE = os.path.join(COOKDIR, ".recipes.json")
DATA_OUT = os.path.join(BRAIN, "cook-data.json")
OUT = os.path.join(BRAIN, "cook.html")

PLAN = os.path.join(COOKDIR, "plan.md")
SHOPPING = os.path.join(COOKDIR, "shopping.md")
PANTRY = os.path.join(COOKDIR, "pantry.md")
COOKED = os.path.join(COOKDIR, "cooked.md")
# Her own recipes — things she was told, found, or worked out. Same shape as
# a book file, but it lives in cooking/ because it is HERS: it commits, it
# survives a re-extraction of the library, and she can edit it by hand.
MINE_SRC = "my-recipes.md"
MINE = os.path.join(COOKDIR, MINE_SRC)
MINE_BOOK = "My recipes"
# What the page's "Add a recipe" brings in lands under this heading, after
# the groups she arranged by hand. Photos for her recipes live beside them
# (they commit with her recipes; the books' photos are the library's), and
# notes.md holds her notes on any recipe, the books' too.
ADDED_HEAD = "# Added from the page"
PHOTOS = os.path.join(COOKDIR, "photos")
NOTES = os.path.join(COOKDIR, "notes.md")
# What she likes in her own words, and what she actually buys. The week
# planner reads both: taste.md is hers to write and overrides everything,
# basket.md is counted up from the receipts she uploads.
TASTE = os.path.join(COOKDIR, "taste.md")
BASKET = os.path.join(COOKDIR, "basket.md")


def src_path(src):
    """Where a recipe's markdown actually lives. Everything comes from the
    library except her own file, which is the one source she owns."""
    return MINE if src == MINE_SRC else os.path.join(LIB, src)

DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

# Assumed in the cupboard — same set as the library's own pantry.py.
STAPLES_DEFAULT = ["salt", "pepper", "olive oil", "oil", "butter", "flour",
                   "sugar", "water"]

# Bump when the derived fields change, so the cache rebuilds.
INDEX_V = 8

# What the "≤5 ingredients" flag does NOT count: things a stocked cupboard
# and spice rack already hold. Matching is exact or ends-with ("smoked
# paprika" → paprika, "dijon mustard" → mustard) so "mustard greens" still
# counts as a real ingredient — see _is_cupboard.
CUPBOARD = {
    "salt", "kosher salt", "sea salt", "pepper", "black pepper",
    "white pepper", "oil", "olive oil", "vegetable oil", "canola oil",
    "neutral oil", "sesame oil", "butter", "flour", "sugar", "water",
    "paprika", "cumin", "turmeric", "cinnamon", "nutmeg", "cardamom",
    "cloves", "cayenne", "chili powder", "chile powder", "chili flakes",
    "red pepper flakes", "oregano", "bay leaf", "bay leaves",
    "curry powder", "garam masala", "five-spice powder", "allspice",
    "star anise", "fennel seeds", "cumin seeds", "coriander seeds",
    "mustard seeds", "sesame seeds", "peppercorns", "garlic powder",
    "onion powder", "vanilla", "vanilla extract", "baking powder",
    "baking soda", "bicarbonate", "yeast", "cornstarch", "cornflour",
    "vinegar", "soy sauce", "tamari", "mustard", "honey",
}

# Shelf-stable but load-bearing — these ARE the recipe, never cupboard.
NOT_CUPBOARD = ("peanut butter", "almond butter", "cashew butter",
                "apple butter", "cocoa butter", "mustard greens",
                "honeydew", "rye flour", "almond flour",
                "buckwheat flour", "chickpea flour", "rice flour",
                "spelt flour", "einkorn flour", "semolina flour")


def _is_cupboard(ing):
    i = ing.strip().lower()
    if i.startswith("fresh ") or i in NOT_CUPBOARD:
        return False
    if i in CUPBOARD:
        return True
    return any(i.endswith(" " + t) for t in CUPBOARD)

# What an American cookbook asks for vs what a medium French supermarket
# stocks. Keys match normalised ingredient names (substring); values are
# the swap, with the French shelf name where that's the trick.
SWAPS = {
    "kale": "chou vert frisé or blettes — same cooking; épinards if it just wilts in",
    "collard greens": "chou vert, leaves only, stems out",
    "buttermilk": "25 cl milk + 1 tbsp lemon juice, rest 5 min (or lait ribot)",
    "sour cream": "crème fraîche épaisse, squeeze of lemon",
    "heavy cream": "crème liquide entière 30%",
    "half-and-half": "half milk, half crème liquide",
    "cream cheese": "Philadelphia or St Môret",
    "monterey jack": "emmental or young comté",
    "pepper jack": "emmental + a pinch of piment",
    "sharp cheddar": "comté or mimolette",
    "cotija": "feta, crumbled, or parmesan",
    "queso fresco": "feta, rinsed to soften the salt",
    "pancetta": "lardons",
    "guanciale": "lardons fumés",
    "prosciutto": "jambon cru (Bayonne or Serrano)",
    "italian sausage": "saucisse de Toulouse + fennel seeds",
    "andouille sausage": "saucisse de Montbéliard",
    "tomatillos": "green (unripe) tomatoes + extra lime",
    "poblano": "poivron vert + a pinch of piment",
    "jalapeño": "piment vert from the Antilles shelf, or Espelette",
    "serrano chile": "piment vert or Espelette",
    "chipotle": "paprika fumé + a little harissa",
    "corn tortillas": "wheat tortillas, or skip to rice bowls",
    "masa harina": "hard to swap — polenta fine at a pinch",
    "black beans": "haricots rouges (canned)",
    "pinto beans": "haricots rouges or borlotti",
    "cannellini": "haricots blancs",
    "gochujang": "sriracha + 1 tsp honey, or harissa + sugar",
    "gochugaru": "piment d'Espelette + paprika",
    "kimchi": "asian aisle sometimes; else pickled cabbage + sriracha",
    "miso": "bio aisle sometimes; else soy sauce and halve the salt",
    "mirin": "1 tbsp white wine + 1 tsp sugar",
    "sake": "dry white wine",
    "dashi": "fish stock cube, or water + a few drops of nuoc-mâm",
    "rice vinegar": "cider vinegar + a pinch of sugar",
    "panko": "chapelure, the coarsest one",
    "fish sauce": "nuoc-mâm — asian aisle, easy find under that name",
    "tahini": "purée de sésame, bio aisle",
    "molasses": "vergeoise + a little honey",
    "corn syrup": "sirop de glucose (baking aisle) or honey",
    "brown sugar": "cassonade (light) or vergeoise (dark)",
    "graham cracker": "spéculoos or petits-beurre",
    "saltine": "TUC or crackers salés",
    "cornmeal": "polenta",
    "grits": "polenta",
    "self-rising flour": "T45 + 1 sachet levure chimique per 250 g",
    "cake flour": "farine T45",
    "bread flour": "farine T65",
    "scallions": "oignons nouveaux or cebettes",
    "bok choy": "chou chinois (pak choï) or blettes",
    "napa cabbage": "chou chinois",
    "daikon": "radis noir, or navets cooked",
    "delicata squash": "potimarron",
    "acorn squash": "potimarron",
    "okra": "hard to find — green beans cook the same way, texture differs",
    "tempeh": "tofu ferme",
    "edamame": "fèves or petits pois (frozen)",
    "shishito": "pimientos de padrón, Spanish shelf",
    "za'atar": "thym + toasted sesame; sumac from the world aisle",
    "sumac": "lemon zest",
    "preserved lemon": "world aisle sometimes; else lemon zest + salt",
    "pomegranate molasses": "balsamic reduction + honey",
}


# ---------------------------------------------------------------- index

def _slug(s):
    s = re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")
    return s[:60] or "recipe"


def _norm_title(s):
    return re.sub(r"[^a-z0-9]+", "", s.lower())


def _undouble(name):
    """"garlic garlic" is "garlic": the extraction sometimes repeats a word,
    and the shopping list printed it twice (8 Oct, her screenshot)."""
    return re.sub(r"\b([a-z][\w'-]*)(?: \1\b)+", r"\1", name)


MEATY = {"chicken", "beef", "pork", "lamb", "veal", "sausage", "bacon",
         "pancetta", "prosciutto", "ham", "chorizo", "duck", "turkey",
         "steak", "brisket", "guanciale", "anchovy", "anchovies", "fish",
         "salmon", "tuna", "shrimp", "prawns", "cod", "trout", "mussels",
         "clams", "squid", "octopus", "crab", "lobster", "sardines",
         "mackerel", "halibut", "scallops", "oysters", "snapper", "bass",
         "haddock", "swordfish", "hake", "eel", "herring", "fish sauce"}

FISHY = {"fish", "salmon", "tuna", "shrimp", "prawns", "cod", "trout",
         "mussels", "clams", "squid", "octopus", "crab", "lobster",
         "sardines", "mackerel", "halibut", "scallops", "oysters",
         "snapper", "bass", "haddock", "swordfish", "hake", "monkfish"}

BIRDY = {"chicken", "turkey", "duck", "poussin", "quail"}

REDMEAT = {"beef", "pork", "lamb", "veal", "sausage", "bacon", "pancetta",
           "prosciutto", "ham", "chorizo", "steak", "brisket", "guanciale",
           "ribs", "meatballs"}

SWEET_BOOKS = {"dessert_person", "flour_power", "king_arthur_bakers_companion"}

# A real protein anchor for the high-protein flag. Checked against whole
# ingredient phrases, skipping stocks/sauces/pastes so "chicken broth" and
# "fish sauce" don't count as chicken and fish.
PROTEINS = (BIRDY | FISHY | REDMEAT
            | {"egg", "eggs", "tofu", "tempeh", "seitan", "paneer",
               "halloumi", "cottage cheese", "shrimp", "prawns",
               "lentils", "chickpeas", "black beans", "white beans",
               "cannellini", "edamame", "beans"})
NOT_PROTEIN_RX = re.compile(r"stock|broth|bouillon|sauce|paste|powder")


# Dorm-friendly means a weeknight MEAL — not a spritz, a dip or a jam.
NOT_A_MEAL = {"Sweets & baking", "Drinks", "Basics & sauces",
              "Snacks & starters"}

# Meal-prep: keeps and reheats. Salads and eggs don't, whatever the yield;
# stews, legumes and grains do by nature; anything else qualifies when the
# book says so ("keeps well", "leftovers", "freeze") or it's a big batch.
PREP_NEVER = NOT_A_MEAL | {"Salads", "Eggs"}
PREP_BY_NATURE = {"Soups & stews", "Beans & lentils", "Rice & grains"}


def _is_prep(cat, sec, y):
    if cat in PREP_NEVER:
        return False
    if cat in PREP_BY_NATURE:
        return True
    if sec and sec.get("prep_text"):
        return True
    return (_serves(y) or 0) >= 6


def _is_protein(ings, cat):
    if cat in ("Sweets & baking", "Drinks", "Basics & sauces"):
        return False
    for i in ings:
        if NOT_PROTEIN_RX.search(i):
            continue
        toks = set(i.split())
        if toks & PROTEINS or i in PROTEINS:
            return True
    return False

# Ordered chapter rules — first hit wins.
CAT_RULES = [
    ("Sweets & baking", r"dessert|sweet|cake|cookie|baking|bread|happy endings|"
     r"dolci|pastry|pie|tart|chocolate|fruit desserts|custard|ice cream|"
     r"babka|brioche|croissant|scone|muffin|yeast|sourdough|desem|crackers|"
     r"all about butter|treat|pudding|flan|crêpe|crepe|confectionery|jam"),
    ("Drinks", r"drink|sips|cocktail|beverage"),
    ("Breakfast", r"breakfast|brunch|morning"),
    ("Soups & stews", r"soup|stew|chili|braise|broth"),
    ("Salads", r"salad|slaw"),
    ("Pasta & noodles", r"pasta|noodle|lasagn|risotto|gnocchi|dumpling"),
    ("Rice & grains", r"\brice\b|grain|polenta|couscous|farro"),
    ("Beans & lentils", r"bean|lentil|chickpea|legume"),
    ("Eggs", r"\begg"),
    ("Fish & seafood", r"fish|seafood|shellfish"),
    ("Chicken & poultry", r"chicken|poultry|bird|licken"),
    ("Meat", r"\bmeat\b|beef|pork|lamb|steak|chops|sausage"),
    ("Vegetables", r"vegetable|veg\b|greens|roots|tubers|sides|shoots"),
    ("Basics & sauces", r"sauce|basic|pantry|staple|condiment|dressing|stock"),
    ("Snacks & starters", r"snack|appetizer|starter|hors|canap|antipasti|dip"),
]


# Unambiguous dessert words for titles — needed because some books chapter
# by technique ("10 Caramelize"), not by food. The veto stops savory
# classics (salmon mousse, Yorkshire pudding) from reading as dessert.
SWEET_TITLE_RX = re.compile(
    r"\bflan\b|custard|pudding|ice cream|sorbet|gelato|mousse|meringue|"
    r"brownie|blondie|cookies?\b|macaron|shortbread|cheesecake|pavlova|"
    r"tiramisu|panna cotta|cr[eè]me br[uû]l|clafoutis|churro|doughnut|"
    r"donut|cupcake|fudge|tarte tatin|baklava|halva|nougat|marshmallow|"
    r"sticky toffee|milkshake|frosting|ganache|granita|dessert", re.I)
SAVORY_VETO_RX = re.compile(
    r"chicken|salmon|\bham\b|fish|shrimp|crab|tomato|onion|garlic|potato|"
    r"pork|beef|liver|yorkshire|black pudding|cheese\b", re.I)


def _title_sweet(title):
    return bool(SWEET_TITLE_RX.search(title)
                and not SAVORY_VETO_RX.search(title))


def _category(book_src, chapter, ings, title=""):
    ch = (chapter or "").lower()
    if book_src in SWEET_BOOKS:
        return "Sweets & baking"
    for name, rx in CAT_RULES:
        if re.search(rx, ch):
            return name
    if _title_sweet(title):
        return "Sweets & baking"
    s = set(ings)
    joined = " ".join(ings)
    if s & BIRDY:
        return "Chicken & poultry"
    if s & FISHY:
        return "Fish & seafood"
    if s & REDMEAT:
        return "Meat"
    if "pasta" in joined or "noodle" in joined:
        return "Pasta & noodles"
    if re.search(r"\brice\b|polenta|couscous|farro|quinoa", joined):
        return "Rice & grains"
    if re.search(r"\bbeans?\b|lentil|chickpea", joined):
        return "Beans & lentils"
    # eggs last among proteins: half the pantry contains an egg somewhere
    if ("eggs" in s or "egg" in s) and len(ings) <= 8:
        return "Eggs"
    return "Vegetables"


def _is_veg(ings):
    joined = " " + " ".join(ings) + " "
    for m in MEATY:
        if " " + m + " " in joined or any(i == m or i.endswith(" " + m)
                                          for i in ings):
            return False
    return True


# The book's own stated total time ("Total: 4 hrs.", "Total Time: 1 hour
# 25 minutes") — the honest planning number when active time undersells it.
TOTAL_RX = re.compile(r"total(?:\s*time)?\s*:\s*([^\n|]{0,40})", re.I)
SLOW_RX = re.compile(r"overnight|\b\d+\s*(?:to\s*\d+\s*)?(?:hours?|hrs?)\b",
                     re.I)


def _parse_total(body):
    m = TOTAL_RX.search(body)
    if not m:
        return None
    seg = (m.group(1).replace("½", ".5").replace("¼", ".25")
           .replace("¾", ".75"))
    mins = 0.0
    h = re.search(r"(\d+(?:\.\d+)?)\s*(?:hours?|hrs?)\b", seg, re.I)
    if h:
        mins += float(h.group(1)) * 60
    mm = re.search(r"(\d+)\s*(?:minutes?|mins?)\b", seg, re.I)
    if mm:
        mins += int(mm.group(1))
    return int(mins) or None


# The book saying, in its own words, that a dish keeps or reheats.
PREP_RX = re.compile(r"leftovers?|reheat|make.ahead|meal.prep|"
                     r"keeps?,? (?:well|for|up to|in the)|"
                     r"freezes? (?:well|beautifully|for)|freezer.friendly|"
                     r"refrigerate for up to|(?:store|keep) (?:in|for) "
                     r"(?:the )?(?:fridge|refrigerator)|up to \d+ days",
                     re.I)


def _serves(y):
    if not y:
        return None
    m = re.search(r"(?:serves|for|feeds)\s*(\d+)", str(y), re.I)
    return int(m.group(1)) if m else None


OVEN_RX = re.compile(r"\boven\b|\bbaked?\b|\bbakes\b|\bbroil|\broast|"
                     r"preheat|air fryer|\bgrill", re.I)
EQUIP_RX = re.compile(r"blender|food processor|stand mixer|hand mixer|"
                      r"waffle iron|ice cream maker|slow cooker|"
                      r"pressure cooker|instant pot|deep[- ]fry", re.I)
VESSEL_RX = re.compile(r"skillet|frying pan|saut[eé] pan|saucepan|\bpot\b|"
                       r"dutch oven|\bwok\b|griddle", re.I)


def _analyse_method(body):
    """What the method actually demands: numbered steps, stovetop vessels,
    and whether it needs an oven or machine a dorm kitchen lacks."""
    m = body.split("**Method**", 1)
    mtext = m[1] if len(m) == 2 else body
    # a dutch oven is a pot on a burner, not an oven
    clean = re.sub(r"[Dd]utch oven", "heavypot", mtext)
    steps = len(re.findall(r"^\*\*\d+\.\*\*", mtext, re.M))
    vessels = len({v.lower().replace("é", "e")
                   for v in VESSEL_RX.findall(clean)})
    return {"steps": steps,
            "vessels": vessels,
            "oven": bool(OVEN_RX.search(clean)),
            "equip": bool(EQUIP_RX.search(clean)),
            "tot": _parse_total(body),
            "slow": bool(SLOW_RX.search(mtext)),
            "prep_text": bool(PREP_RX.search(body))}


def _md_sections(path):
    """Every `## ` recipe section in a book file: (title, img, start, end)."""
    with open(path, encoding="utf-8") as f:
        text = f.read()
    out = []
    marks = [m for m in re.finditer(r"^## (.+)$", text, re.M)]
    for i, m in enumerate(marks):
        start = m.start()
        end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
        body = text[start:end]
        img = None
        im = re.search(r"^!\[[^\]]*\]\(([^)]+)\)", body, re.M)
        if im:
            img = im.group(1)
        sec = {"title": m.group(1).strip(), "img": img,
               "a": start, "z": end}
        sec.update(_analyse_method(body))
        out.append(sec)
    return out


# Longest-first, and \b after the unit. Both matter: with "l" ahead of
# "litres?" the alternation eats the first letter of a word, so "1 lemon"
# normalised to "emon" and "greek yoghurt" to "reek".
_UNITS = (r"tablespoons?|teaspoons?|litres?|handfuls?|pinch(?:es)?|bunch(?:es)?|"
          r"cloves?|slices?|pieces?|scoops?|thumbs?|sprigs?|stalks?|sticks?|"
          r"tbsp|tsp|cups?|tins?|cans?|jars?|packs?|kg|ml|cl|oz|lb|g|l")
_QTY_RX = re.compile(
    r"^[\d\s./¼½¾⅓⅔⅛-]*\s*"
    rf"(?:(?:{_UNITS})\b\s*)?"
    r"(?:of\s+)?", re.I)
_SIZE_RX = re.compile(r"^(?:large|small|medium|whole|fresh|frozen|cooked|"
                      r"ripe|good|dried|ground)\s+", re.I)


def _norm_ing(line):
    """"- 150 g broccoli, in small florets" -> "broccoli". Rough on purpose:
    it feeds the pantry matcher and the facet counts, which compare short
    names, and a wrong-but-close name costs a missed match, never a crash."""
    s = re.sub(r"^\s*[-*]\s*", "", line).strip()
    s = re.sub(r"\([^)]*\)", "", s)          # (drained), (optional)
    s = s.split(",")[0]                       # prep notes live after the comma
    s = _QTY_RX.sub("", s, count=1)
    for _ in range(2):                        # "1 large fresh tomato"
        s = _SIZE_RX.sub("", s)
    s = re.sub(r"\s+", " ", s).strip(" .").lower()
    return s


def _mine_records():
    """Her own recipes as index records, shaped like pantry_db.json rows so
    everything downstream — search, facets, planning, shopping — cannot tell
    the difference between her file and a cookbook."""
    if not os.path.exists(MINE):
        return []
    out = []
    for sec in _md_sections(MINE):
        with open(MINE, encoding="utf-8") as f:
            body = f.read()[sec["a"]:sec["z"]]
        parts = re.split(r"\*\*Ingredients\*\*", body, maxsplit=1)
        if len(parts) != 2:
            continue                          # a prose section, not a recipe
        block = re.split(r"\*\*Method\*\*", parts[1], maxsplit=1)[0]
        raw = [ln.strip()[2:].strip() for ln in block.splitlines()
               if ln.strip().startswith("- ")]
        ings = [i for i in (_norm_ing(x) for x in raw) if i]
        if not ings:
            continue
        ch = re.search(r"<sub>(.*?)</sub>", body)
        yd = re.search(r"^Serves\s+([^\n·]+)", body, re.M | re.I)
        out.append({"t": sec["title"], "b": MINE_BOOK,
                    "c": (ch.group(1).strip() if ch else ""),
                    "p": None,
                    "y": ("Serves " + yd.group(1).strip()) if yd else None,
                    "m": None, "n": ings, "raw": raw, "src": MINE_SRC})
    return out


def build_index(force=False):
    """The full recipe index, cached. Joins pantry_db.json (ingredients,
    time, yield) with the markdown (image, byte offsets for the detail API)."""
    db_path = os.path.join(LIB, "pantry_db.json")
    if not os.path.exists(db_path) and not os.path.exists(MINE):
        return []
    # Her file is part of the stamp: edit a recipe of her own and the index
    # must notice, exactly as it does when the library changes.
    stamp = int(os.path.getmtime(db_path)) if os.path.exists(db_path) else 0
    if os.path.exists(MINE):
        # To the millisecond: the page can add a recipe and edit it within
        # the same second, and a whole-second stamp kept the stale index.
        stamp += os.stat(MINE).st_mtime_ns // 1_000_000
    if not force and os.path.exists(CACHE):
        try:
            with open(CACHE, encoding="utf-8") as f:
                cached = json.load(f)
            if cached.get("stamp") == stamp and cached.get("v") == INDEX_V:
                return cached["recipes"]
        except Exception:
            pass

    db = []
    if os.path.exists(db_path):
        with open(db_path, encoding="utf-8") as f:
            db = json.load(f)
    db = _mine_records() + db      # hers first: same id space, no collisions

    sections = {}          # src -> list of md sections
    by_title = {}          # (src, normtitle) -> [section indexes]
    for src in sorted({r["src"] for r in db}):
        path = src_path(src)
        if not os.path.exists(path):
            sections[src] = []
            continue
        secs = _md_sections(path)
        sections[src] = secs
        for i, s in enumerate(secs):
            by_title.setdefault((src, _norm_title(s["title"])), []).append(i)

    used = {}              # (src, normtitle) -> how many consumed
    seen_ids = {}
    recipes = []
    for r in db:
        src = r["src"]
        key = (src, _norm_title(r["t"]))
        sec = None
        idxs = by_title.get(key) or []
        u = used.get(key, 0)
        if u < len(idxs):
            sec = sections[src][idxs[u]]
            used[key] = u + 1
        ings = [_undouble(i) for i in (r.get("n") or [])]
        rid = src.rsplit(".", 1)[0] + "/" + _slug(r["t"])
        n = seen_ids.get(rid, 0)
        seen_ids[rid] = n + 1
        if n:
            rid += f"-{n + 1}"
        cat = _category(src.rsplit(".", 1)[0], r.get("c"), ings, r["t"])
        ns = sum(1 for i in ings if not _is_cupboard(i))
        m = r.get("m")
        steps = (sec or {}).get("steps", 0)
        tot = (sec or {}).get("tot")
        slow = (sec or {}).get("slow")
        if tot:                       # the book's stated total wins
            quick = tot <= 30
        elif m:                       # active time only — trust it unless
            quick = m <= 30 and not slow   # the method hints at hours
        else:
            quick = 0 < steps <= 3 and ns <= 8 and not slow
        recipes.append({
            "id": rid,
            "t": r["t"],
            "b": r["b"],
            "c": r.get("c") or "",
            "pg": r.get("p"),
            "y": r.get("y"),
            "m": m,
            "tot": tot,
            "n": ings,
            "img": (sec or {}).get("img"),
            "cat": cat,
            "veg": _is_veg(ings),
            "quick": bool(quick),
            "few": bool(ings and ns <= 5),
            "prot": _is_protein(ings, cat),
            "dorm": bool(sec and not sec["oven"] and not sec["equip"]
                         and sec["vessels"] <= 2
                         and cat not in NOT_A_MEAL),
            "prep": _is_prep(cat, sec, r.get("y")),
            "src": src,
            "a": (sec or {}).get("a", -1),
            "z": (sec or {}).get("z", -1),
        })

    os.makedirs(COOKDIR, exist_ok=True)
    with open(CACHE, "w", encoding="utf-8") as f:
        json.dump({"stamp": stamp, "v": INDEX_V, "recipes": recipes}, f)
    return recipes


_INDEX = None


def index():
    global _INDEX
    if _INDEX is None:
        _INDEX = build_index()
    return _INDEX


def _forget_index():
    """The server keeps the index for its whole life; a recipe added from
    the page must be in the very next build, not the next restart."""
    global _INDEX
    _INDEX = None


def _img_url(img):
    """A recipe's photo as the page addresses it: hers sit in cooking/photos,
    the books' inside the library."""
    if not img:
        return None
    return img if img.startswith("cooking/") else "recipes-library/" + img


def by_id(rid):
    for r in index():
        if r["id"] == rid:
            return r
    return None


def recipe_detail(rid):
    """The full recipe: headnote, ingredients, method — parsed on demand."""
    r = by_id(rid)
    if not r:
        return {"error": "unknown recipe"}
    out = {"id": r["id"], "t": r["t"], "b": r["b"], "c": r["c"],
           "pg": r["pg"], "y": r["y"], "m": r["m"], "tot": r.get("tot"),
           "img": _img_url(r["img"]), "raw": [], "headnote": "", "method": "",
           "source": "", "mine": r["src"] == MINE_SRC}
    raw = None
    if r["src"] == MINE_SRC:
        # Her own file carries its ingredients in the markdown itself —
        # there is no pantry_db row to look them up in.
        for e in _mine_records():
            if _norm_title(e["t"]) == _norm_title(r["t"]):
                raw = e.get("raw")
                break
    else:
        db_path = os.path.join(LIB, "pantry_db.json")
        try:
            with open(db_path, encoding="utf-8") as f:
                for e in json.load(f):
                    if e["src"] == r["src"] and _norm_title(e["t"]) == _norm_title(r["t"]):
                        raw = e.get("raw")
                        break
        except Exception:
            pass
    out["raw"] = raw or []
    if r["a"] < 0:
        return out
    try:
        with open(src_path(r["src"]), encoding="utf-8") as f:
            f.seek(0)
            text = f.read()
        body = text[r["a"]:r["z"]]
    except Exception:
        return out
    # strip the heading, the <sub> line and the image line
    body = re.sub(r"^## .+\n", "", body)
    body = re.sub(r"^<sub>.*?</sub>\s*\n", "", body, flags=re.M)
    body = re.sub(r"^!\[[^\]]*\]\([^)]*\)\s*\n", "", body, flags=re.M)
    parts = re.split(r"\*\*Ingredients\*\*", body, maxsplit=1)
    if len(parts) == 2:
        out["headnote"] = parts[0].strip()
        if r["src"] == MINE_SRC:
            # The drawer already shows Serves and the time in their own
            # fields; leaving the line in prints them twice. The link to
            # where a recipe came from gets its own place too.
            src = re.search(r"^Source:\s*(https?://\S+)\s*$", out["headnote"],
                            re.M | re.I)
            out["source"] = src.group(1) if src else ""
            out["headnote"] = re.sub(
                r"\n*^(?:Serves\b|Total\s*:|Source\s*:)[^\n]*$", "",
                out["headnote"], flags=re.M | re.I).strip()
        rest = re.split(r"\*\*Method\*\*", parts[1], maxsplit=1)
        if len(rest) == 2:
            out["method"] = rest[1].strip()
        else:
            out["method"] = parts[1].strip()
        if r["src"] == MINE_SRC:
            # A group heading of her file ("# Eggs") sits after the last
            # recipe before it, and showed as that recipe's final step.
            out["method"] = re.split(r"^(?:# |---\s*$)", out["method"],
                                     maxsplit=1, flags=re.M)[0].strip()
    else:
        out["method"] = body.strip()
    if r["src"] == MINE_SRC:
        # What the page's edit form starts from.
        yd = re.search(r"^Serves\s+([^\n·]+)", body, re.M | re.I)
        out["edit"] = {"kind": r["c"], "serves": yd.group(1).strip() if yd else "",
                       "steps": _steps_of(out["method"]), "photo": r["img"] or ""}
    return out


def _steps_of(method):
    """A method as one line per step, the way the edit form shows it."""
    parts = re.split(r"(?:^|\n)\s*\*\*\d+\.\*\*\s*", method or "")
    if len([p for p in parts if p.strip()]) < 2:
        parts = re.split(r"\n\s*\n", method or "")
    return [re.sub(r"\s+", " ", p).strip() for p in parts if p.strip()]


# ---------------------------------------------------------------- state

def _read(path):
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except OSError:
        return ""


def _write(path, text):
    os.makedirs(COOKDIR, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def monday(d=None):
    d = d or date.today()
    return d - timedelta(days=d.weekday())


ENTRY_RX = re.compile(r"^- (Mon|Tue|Wed|Thu|Fri|Sat|Sun):\s*(.+?)"
                      r"(?:\s*\{id:\s*([^}]+)\})?"
                      r"(\s*\(leftovers\))?\s*$")


def load_plan():
    """plan.md -> {week_iso: {day: [{title, id, lo}]}} — `lo` marks a
    leftovers night: same dish, nothing to cook, nothing to buy."""
    out = {}
    week = None
    for line in _read(PLAN).splitlines():
        m = re.match(r"^## Week of (\d{4}-\d{2}-\d{2})", line)
        if m:
            week = m.group(1)
            out.setdefault(week, {})
            continue
        if week is None:
            continue
        m = ENTRY_RX.match(line.strip())
        if m:
            out[week].setdefault(m.group(1), []).append(
                {"title": m.group(2).strip(),
                 "id": (m.group(3) or "").strip(),
                 "lo": bool(m.group(4))})
    return out


def save_plan(plan):
    lines = ["# Meal plan", "",
             "The week's dinners. The page writes this; edit freely — one",
             "line per day, `- Mon: Recipe title`.", ""]
    for week in sorted(plan):
        entries = plan[week]
        if not any(entries.get(d) for d in DAYS):
            continue
        lines.append(f"## Week of {week}")
        lines.append("")
        for d in DAYS:
            for e in entries.get(d) or []:
                tid = f" {{id: {e['id']}}}" if e.get("id") else ""
                lo = " (leftovers)" if e.get("lo") else ""
                lines.append(f"- {d}: {e['title']}{tid}{lo}")
        lines.append("")
    _write(PLAN, "\n".join(lines).rstrip() + "\n")


# What Find opens with: the filters she last set, kept beside the kitchen
# switch so the desk and the phone open on the same ones (8 Oct, her ask:
# "default the filters so it saves what you last set"). Absent until she
# first changes one; the page then opens on Weeknight.
FIND_KEYS = ("weeknight", "quick", "few", "protein", "dorm-friendly",
             "meal-prep", "pantry", "veg", "saved")


def load_pantry():
    staples, fresh, group = [], [], None
    kitchen = "full"
    find = None
    for line in _read(PANTRY).splitlines():
        if line.startswith("## Staples"):
            group = staples
        elif line.startswith("## Fresh"):
            group = fresh
        elif line.startswith("## Kitchen"):
            group = None
        elif line.startswith("## Find"):
            group, find = "find", []
        elif group == "find":
            if line.startswith("- ") and line[2:].strip():
                find.append(line[2:].strip())
        elif line.startswith("- ") and group is not None:
            item = line[2:].strip()
            if item:
                group.append(item)
        elif line.strip() in ("- full", "- dorm"):
            kitchen = line.strip()[2:]
    if not staples and not fresh and not _read(PANTRY):
        staples = list(STAPLES_DEFAULT)
    return {"staples": staples, "fresh": fresh, "kitchen": kitchen,
            "find": find}


def save_pantry(p):
    lines = ["# Pantry", "",
             "What the kitchen holds. Staples are assumed by the recipe",
             "matcher; Fresh is this week's perishables.", "",
             "## Staples", ""]
    lines += [f"- {i}" for i in p["staples"]]
    lines += ["", "## Fresh right now", ""]
    lines += [f"- {i}" for i in p["fresh"]]
    lines += ["", "## Kitchen", "",
              "full = anything goes; dorm = two burners, no oven.", "",
              f"- {p.get('kitchen', 'full')}"]
    if p.get("find") is not None:
        lines += ["", "## Find", "",
                  "The filters Find opens with. The page keeps it as you "
                  "change them.", ""]
        lines += [f"- {k}" for k in p["find"]]
    _write(PANTRY, "\n".join(lines) + "\n")


def load_cooked():
    log, saved, section = [], [], None
    for line in _read(COOKED).splitlines():
        if line.startswith("## Log"):
            section = "log"
        elif line.startswith("## Saved"):
            section = "saved"
        elif line.startswith("- ") and section:
            body = line[2:].strip()
            m = re.match(r"^(\d{4}-\d{2}-\d{2}) — (.+)$", body)
            if section == "log" and m:
                rest = m.group(2)
                rid = ""
                idm = re.search(r"\{id:\s*([^}]+)\}", rest)
                if idm:
                    rid = idm.group(1).strip()
                    rest = rest.replace(idm.group(0), "").strip()
                note = ""
                if " — " in rest:
                    rest, note = rest.split(" — ", 1)
                log.append({"date": m.group(1), "title": rest.strip(),
                            "id": rid, "note": note.strip()})
            elif section == "saved":
                rid = ""
                idm = re.search(r"\{id:\s*([^}]+)\}", body)
                if idm:
                    rid = idm.group(1).strip()
                    body = body.replace(idm.group(0), "").strip()
                saved.append({"title": body, "id": rid})
    return {"log": log, "saved": saved}


def save_cooked(c):
    lines = ["# Cooked", "",
             "What actually got made, and the recipes worth keeping.", "",
             "## Log", ""]
    for e in c["log"]:
        tid = f" {{id: {e['id']}}}" if e.get("id") else ""
        note = f" — {e['note']}" if e.get("note") else ""
        lines.append(f"- {e['date']} — {e['title']}{tid}{note}")
    lines += ["", "## Saved", ""]
    for e in c["saved"]:
        tid = f" {{id: {e['id']}}}" if e.get("id") else ""
        lines.append(f"- {e['title']}{tid}")
    _write(COOKED, "\n".join(lines) + "\n")


def load_taste():
    """taste.md -> {love, avoid, bored} — her words, one item per line.
    These are matched against ingredient names and recipe titles, so
    "fennel" kills a recipe and "lemon" lifts one. Hers to edit; nothing
    writes here except her and an explicit ask."""
    out = {"love": [], "avoid": [], "bored": []}
    section = None
    for line in _read(TASTE).splitlines():
        low = line.strip().lower()
        if low.startswith("## love"):
            section = "love"
        elif low.startswith("## avoid"):
            section = "avoid"
        elif low.startswith("## bored"):
            section = "bored"
        elif low.startswith("## "):
            section = None
        elif line.startswith("- ") and section:
            item = line[2:].strip()
            if item:
                out[section].append(item)
    return out


def save_taste(t):
    lines = ["# Taste", "",
             "What you like and what you would rather not see, in your own",
             "words. The week planner reads this and it outranks anything",
             "the counting infers. One item per line.", "",
             "## Love", ""]
    lines += [f"- {x}" for x in t.get("love", [])]
    lines += ["", "## Avoid", ""]
    lines += [f"- {x}" for x in t.get("avoid", [])]
    lines += ["", "## Bored of", ""]
    lines += [f"- {x}" for x in t.get("bored", [])]
    _write(TASTE, "\n".join(lines).rstrip() + "\n")


BASKET_RX = re.compile(r"^- (.+?) — (\d+) · last (\d{4}-\d{2}-\d{2})\s*$")

# A till line is not an ingredient line: it carries a multiplier in front
# ("2 X POIREAUX"), a pack size behind ("SAUMON FRAIS 300G"), a price, and
# shop shorthand. _norm_ing alone leaves those on and then "poireaux" and
# "2 x poireaux" count as two different things forever.
_TILL_LEAD_RX = re.compile(r"^\s*\d+[.,]?\d*\s*(?:x|\*)?\s*", re.I)
_TILL_TAIL_RX = re.compile(
    r"\s*(?:x\s*\d+|\d+[.,]?\d*\s*(?:g|kg|gr|ml|cl|l|pcs?|pieces?)\b|"
    r"\d+[.,]\d{2}\s*(?:€|eur)?)\s*$", re.I)


NOTES_HEAD = ("# Recipe notes\n\nYour notes on recipes, the books' and your "
              "own: what you changed, what to try next time. The Cook page "
              "writes them, and you can edit them here.\n")


def load_notes():
    """{recipe id: {"title", "text"}} from notes.md (`## Title {id}`, then
    the note)."""
    out = {}
    for m in re.finditer(r"^## (.*?) \{([^}\n]+)\}[ \t]*\n(.*?)(?=^## |\Z)",
                         _read(NOTES), re.M | re.S):
        text = m.group(3).strip()
        if text:
            out[m.group(2).strip()] = {"title": m.group(1).strip(), "text": text}
    return out


def save_notes(notes):
    parts = [NOTES_HEAD]
    for rid, v in notes.items():
        title = re.sub(r"[{}\n]", "", v.get("title") or rid).strip()
        parts.append(f"## {title} {{{rid}}}\n\n{v['text'].strip()}\n")
    _write(NOTES, "\n".join(parts))


def _one_line(s, cap):
    """A field the form sends as one line: no heading marks, no breaks."""
    s = re.sub(r"\s+", " ", str(s or "")).strip()
    return re.sub(r"^#+\s*", "", s)[:cap]


def _free_text(s, cap):
    """A headnote or a note: paragraphs kept, and no line that the parser
    would read as a new recipe, a list section or a photo."""
    out = []
    for ln in str(s or "").replace("\r", "").split("\n"):
        ln = re.sub(r"^\s*#+\s+", "", ln.rstrip())
        ln = re.sub(r"\*\*(Ingredients|Method)\*\*", r"\1", ln)
        ln = re.sub(r"^(\s*)!\[", r"\1[", ln)
        ln = re.sub(r"^(\s*)Source\s*:", r"\1Source -", ln, flags=re.I)
        out.append(ln)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(out)).strip()[:cap]


def _fmt_total(mins):
    h, m = divmod(int(mins), 60)
    if not h:
        return f"{m} minutes"
    return f"{h} hour{'s' if h > 1 else ''}" + (f" {m} minutes" if m else "")


def _save_photo(data_url, slug):
    """The page always sends a JPEG it has already shrunk."""
    import base64
    m = re.match(r"^data:image/jpeg;base64,([A-Za-z0-9+/=]+)$", data_url or "")
    blob = base64.b64decode(m.group(1)) if m else b""
    if blob[:3] != b"\xff\xd8\xff" or len(blob) > 4_000_000:
        raise ValueError("that photo could not be read")
    os.makedirs(PHOTOS, exist_ok=True)
    name, n = slug, 1
    while os.path.exists(os.path.join(PHOTOS, name + ".jpg")):
        n += 1
        name = f"{slug}-{n}"
    with open(os.path.join(PHOTOS, name + ".jpg"), "wb") as f:
        f.write(blob)
    return f"cooking/photos/{name}.jpg"


def _mine_id(title):
    return MINE_SRC.rsplit(".", 1)[0] + "/" + _slug(title)


def add_recipe(b):
    """A recipe from the page's form into my-recipes.md, in the file's own
    shape, so it searches, plans and shops like every other. `replace` names
    the title being edited. Returns {"ok", "id"} or {"error"}."""
    title = _one_line(b.get("title"), 120)
    if not title:
        return {"error": "give it a title"}
    ings = [re.sub(r"^[-*•–]\s*", "", _one_line(x, 200))
            for x in (b.get("ingredients") or [])][:80]
    ings = [x for x in ings if x]
    if not ings:
        return {"error": "add at least one ingredient"}
    steps = [re.sub(r"^(?:step\s*)?\d+\s*[.):-]\s*|^\*\*\d+\.\*\*\s*", "",
                    _one_line(x, 1500), flags=re.I)
             for x in (b.get("steps") or [])][:60]
    steps = [x for x in steps if x]
    kind = re.sub(r"[<>]", "", _one_line(b.get("kind"), 40))
    serves = _one_line(b.get("serves"), 40)
    try:
        total = max(0, min(int(float(b.get("total") or 0)), 7 * 1440))
    except (TypeError, ValueError):
        total = 0
    source = _one_line(b.get("source"), 500)
    if not re.match(r"^https?://\S+$", source):
        source = ""
    headnote = _free_text(b.get("headnote"), 2000)

    text = _read(MINE)
    secs = _md_sections(MINE) if text else []
    by_title = {_norm_title(s["title"]): s for s in secs}
    replace = _one_line(b.get("replace"), 120)
    old = by_title.get(_norm_title(replace)) if replace else None
    if replace and not old:
        return {"error": "that recipe is no longer in My recipes"}
    clash = by_title.get(_norm_title(title))
    if clash and clash is not old:
        return {"error": f"you already have a recipe called {clash['title']}"}
    # The id is the name's first 60 letters: two long names that start the
    # same shared one, and a note or a removal hit the wrong recipe.
    twin = next((s for s in secs if s is not old
                 and _slug(s["title"]) == _slug(title)), None)
    if twin:
        return {"error": f"{twin['title']} starts the same way; change the "
                         "first words of this one's name"}

    photo = str(b.get("photo") or "")
    if photo.startswith("data:"):
        photo = _save_photo(photo, _slug(title))
    elif not re.match(r"^cooking/photos/[\w.-]+\.jpg$", photo):
        photo = ""

    lines = [f"## {title}"] + ([f"<sub>{kind}</sub>"] if kind else []) + [""]
    if photo:
        lines += [f"![photo]({photo})", ""]
    if headnote:
        lines += [headnote, ""]
    if source:
        lines += [f"Source: {source}", ""]
    meta = ([f"Serves {serves}"] if serves else []) + (
        [f"Total: {_fmt_total(total)}"] if total else [])
    if meta:
        lines += [" · ".join(meta), ""]
    lines += ["**Ingredients**", ""] + [f"- {x}" for x in ings] + [""]
    if steps:
        lines += ["**Method**", ""]
        for i, s in enumerate(steps, 1):
            lines += [f"**{i}.** {s}", ""]
    section = "\n".join(lines).rstrip() + "\n"

    if old:
        # Keep a group heading that sat after the old recipe: it belongs to
        # the recipes that follow.
        body = text[old["a"]:old["z"]]
        tail = re.search(r"^(?:# |---[ \t]*$)", body, re.M)
        keep = body[tail.start():] if tail else ""
        text = text[:old["a"]] + section + "\n" + keep + text[old["z"]:]
    else:
        if not text:
            text = "# My recipes\n"
        if ADDED_HEAD not in text:
            text = text.rstrip() + "\n\n" + ADDED_HEAD + "\n"
        text = text.rstrip() + "\n\n" + section
    os.makedirs(COOKDIR, exist_ok=True)
    _write(MINE, text)
    _forget_index()

    rid = _mine_id(title)
    notes = load_notes()
    if old:
        notes.pop(_mine_id(old["title"]), None)
    note = _free_text(b.get("note"), 3000)
    if note:
        notes[rid] = {"title": title, "text": note}
    if notes != load_notes():
        save_notes(notes)
    return {"ok": True, "id": rid}


def remove_recipe(rid):
    """One of her own recipes out of my-recipes.md. Its photo stays on disk
    and git keeps the text."""
    secs = [s for s in (_md_sections(MINE) if os.path.exists(MINE) else [])
            if _mine_id(s["title"]) == rid]
    if not secs:
        return {"error": "only your own recipes can be removed"}
    s = secs[0]
    text = _read(MINE)
    body = text[s["a"]:s["z"]]
    tail = re.search(r"^(?:# |---[ \t]*$)", body, re.M)
    text = text[:s["a"]] + (body[tail.start():] if tail else "") + text[s["z"]:]
    _write(MINE, text.rstrip() + "\n")
    _forget_index()
    notes = load_notes()
    if notes.pop(rid, None):
        save_notes(notes)
    return {"ok": True}


def _norm_basket(raw):
    """One till line -> one short generic name, or "" when nothing survives."""
    s = str(raw).strip()
    s = re.sub(r"\([^)]*\)", "", s)
    s = _TILL_LEAD_RX.sub("", s)
    for _ in range(3):                    # "SAUMON 300G 6.49" has two tails
        new = _TILL_TAIL_RX.sub("", s)
        if new == s:
            break
        s = new
    s = _norm_ing(s)
    # shop adjectives carry no meaning for matching a recipe
    s = re.sub(r"\b(bio|frais|fraiche|surgel[ée]s?|nature|entier|demi|"
               r"organic|fresh|frozen|plain)\b", " ", s, flags=re.I)
    s = re.sub(r"\s+", " ", s).strip(" .-")
    return s if len(s) > 1 else ""


def load_basket():
    """basket.md -> [{item, n, last}] — how often each thing has appeared on
    a receipt she uploaded, most bought first."""
    out = []
    for line in _read(BASKET).splitlines():
        m = BASKET_RX.match(line.strip())
        if m:
            out.append({"item": m.group(1).strip(),
                        "n": int(m.group(2)), "last": m.group(3)})
    out.sort(key=lambda x: (-x["n"], x["item"]))
    return out


def save_basket(items):
    lines = ["# The basket", "",
             "What you actually buy, counted from the receipts you upload.",
             "The week planner leans toward recipes built on the things near",
             "the top. Delete a line and it stops counting.", "",
             "## Counts", ""]
    for it in sorted(items, key=lambda x: (-x["n"], x["item"])):
        lines.append(f"- {it['item']} — {it['n']} · last {it['last']}")
    _write(BASKET, "\n".join(lines).rstrip() + "\n")


def basket_add(names, when=None):
    """Fold one receipt into the running counts. Names arrive as whatever
    the till printed, so they are normalised the same way ingredients are;
    anything that normalises to nothing is dropped rather than guessed at."""
    when = when or date.today().isoformat()
    have = {it["item"]: it for it in load_basket()}
    added = []
    for raw in names:
        name = _norm_basket(raw)
        if not name:
            continue
        if name in have:
            have[name]["n"] += 1
            have[name]["last"] = when
        else:
            have[name] = {"item": name, "n": 1, "last": when}
        added.append(name)
    save_basket(list(have.values()))
    return added


# ------------------------------------------------------------- shopping

AISLES = [
    ("Produce", r"lemon|lime|orange|apple|pear|banana|berr|grape|melon|"
     r"peach|plum|mango|avocado|tomato|onion|shallot|garlic|ginger|potato|"
     r"carrot|celery|pepper[s]?$|chile|chili pepper|cucumber|zucchini|"
     r"squash|eggplant|aubergine|broccoli|cauliflower|cabbage|kale|chard|"
     r"spinach|lettuce|arugula|greens|herb|parsley|cilantro|coriander"
     r"|basil|mint|dill|thyme|rosemary|sage|scallion|leek|fennel|radish|"
     r"beet|turnip|mushroom|corn\b|peas|green bean|asparagus|bok choy|"
     r"sprouts|pumpkin|sweet potato|plantain|date[s]?$|fig"),
    ("Meat & fish", r"chicken|beef|pork|lamb|veal|sausage|bacon|pancetta|"
     r"prosciutto|ham\b|chorizo|duck|turkey|steak|fish|salmon|tuna|shrimp|"
     r"prawn|cod|trout|mussel|clam|squid|crab|lobster|sardine|mackerel|"
     r"halibut|scallop|anchov"),
    ("Dairy & eggs", r"milk|cream|yogurt|yoghurt|butter|cheese|parmesan|"
     r"mozzarella|feta|ricotta|cheddar|egg|crème|creme fraiche|mascarpone|"
     r"halloumi|paneer|burrata"),
    ("Bakery", r"bread|baguette|pita|tortilla|naan|bun[s]?$|roll[s]?$|"
     r"croissant|brioche"),
    ("Pantry", r"pasta|noodle|rice|grain|flour|sugar|oil\b|vinegar|bean|"
     r"lentil|chickpea|stock|broth|tomatoes$|canned|coconut milk|tahini|"
     r"soy sauce|fish sauce|mustard|honey|maple|nut[s]?$|almond|walnut|"
     r"peanut|cashew|pistachio|seed|oat|couscous|polenta|quinoa|harissa|"
     r"gochujang|miso|sriracha|chocolate|vanilla|yeast|cornstarch|panko|"
     r"breadcrumb|caper|olive[s]?$|jam|wine|mirin|sake|sesame"),
    ("Spices", r"salt|pepper$|paprika|cumin|turmeric|cinnamon|nutmeg|"
     r"cardamom|clove|coriander seed|chili powder|cayenne|oregano|"
     r"bay lea|za'atar|sumac|garam|curry powder|fennel seed|mustard seed|"
     r"peppercorn|saffron|allspice|star anise"),
]


def _aisle(name):
    for aisle, rx in AISLES:
        if re.search(rx, name):
            return aisle
    return "Everything else"


def _pantry_has(name, pantry_words):
    nt = set(name.split())
    for h in pantry_words:
        if h == name or h in nt or h in name or name in h:
            return True
        if any(t.startswith(h) or h.startswith(t)
               for t in nt if len(t) > 3 and len(h) > 3):
            return True
    return False


def load_shopping():
    out = {"built": "", "week": "", "sections": [], "additions": [],
           "have": []}
    section = None
    for line in _read(SHOPPING).splitlines():
        m = re.match(r"^Built (\d{4}-\d{2}-\d{2}) for week of "
                     r"(\d{4}-\d{2}-\d{2})", line)
        if m:
            out["built"], out["week"] = m.group(1), m.group(2)
            continue
        m = re.match(r"^## (.+)$", line)
        if m:
            name = m.group(1).strip()
            if name == "Your additions":
                section = "additions"
            elif name.startswith("Probably have"):
                section = "have"
            else:
                section = {"name": name, "items": []}
                out["sections"].append(section)
            continue
        m = re.match(r"^- \[( |x)\] (.+)$", line)
        if m and section is not None:
            done = m.group(1) == "x"
            body = m.group(2).strip()
            text, detail = body, ""
            if " — " in body:
                text, detail = body.split(" — ", 1)
            item = {"text": text.strip(), "detail": detail.strip(),
                    "done": done}
            if section == "additions":
                out["additions"].append(item)
            elif section == "have":
                out["have"].append(item)
            else:
                section["items"].append(item)
    return out


def save_shopping(s):
    lines = ["# Shopping list", ""]
    if s.get("built"):
        lines.append(f"Built {s['built']} for week of {s['week']}. "
                     "Rebuilding keeps your ticks and additions.")
        lines.append("")
    for sec in s["sections"]:
        if not sec["items"]:
            continue
        lines.append(f"## {sec['name']}")
        lines.append("")
        for it in sec["items"]:
            box = "x" if it["done"] else " "
            detail = f" — {it['detail']}" if it.get("detail") else ""
            lines.append(f"- [{box}] {it['text']}{detail}")
        lines.append("")
    lines.append("## Your additions")
    lines.append("")
    for it in s["additions"]:
        box = "x" if it["done"] else " "
        lines.append(f"- [{box}] {it['text']}")
    lines.append("")
    if s["have"]:
        lines.append("## Probably have (from the pantry)")
        lines.append("")
        for it in s["have"]:
            lines.append(f"- [ ] {it['text']}"
                         + (f" — {it['detail']}" if it.get("detail") else ""))
    _write(SHOPPING, "\n".join(lines).rstrip() + "\n")


def build_shopping(week_iso):
    """Merge the week's planned recipes into an aisle-grouped list,
    fold out what the pantry covers, keep ticks and hand additions."""
    old = load_shopping()
    ticked = {it["text"].lower() for sec in old["sections"]
              for it in sec["items"] if it["done"]}
    plan = load_plan().get(week_iso) or {}
    # leftovers nights re-eat what's already bought — never re-shop them
    rids = [e["id"] for d in DAYS for e in (plan.get(d) or [])
            if e.get("id") and not e.get("lo")]
    pantry = load_pantry()
    pantry_words = [w.strip().lower() for w in
                    pantry["staples"] + pantry["fresh"] if w.strip()]

    merged = {}            # normalised ingredient -> {refs, raws}
    for rid in rids:
        r = by_id(rid)
        if not r:
            continue
        for n in r["n"]:
            n = n.strip().lower()
            if not n:
                continue
            e = merged.setdefault(n, {"refs": []})
            if r["t"] not in e["refs"]:
                e["refs"].append(r["t"])

    # attach one raw quantity line per recipe where findable
    raw_by_ing = {}
    db_path = os.path.join(LIB, "pantry_db.json")
    try:
        with open(db_path, encoding="utf-8") as f:
            db = json.load(f)
        want = {(_norm_title(by_id(rid)["t"]), by_id(rid)["src"])
                for rid in rids if by_id(rid)}
        for e in db:
            if (_norm_title(e["t"]), e["src"]) in want:
                for raw in e.get("raw") or []:
                    rl = raw.lower()
                    for n in map(_undouble, e.get("n") or []):
                        if n in rl:
                            raw_by_ing.setdefault(n, []).append(raw)
                            break
    except Exception:
        pass

    sections = {}
    have = []
    for name in sorted(merged):
        e = merged[name]
        detail = " · ".join(e["refs"][:3])
        if len(e["refs"]) > 3:
            detail += f" +{len(e['refs']) - 3}"
        # a raw line only helps when it carries a quantity — "1 lb ground
        # beef" yes, "DATES" no; without one, the recipe names stay.
        quals = [q.strip() for q in (raw_by_ing.get(name) or [])
                 if re.search(r"\d", q)]
        if quals:
            detail = " + ".join(dict.fromkeys(quals[:3]))
        item = {"text": name, "detail": detail,
                "done": name in ticked}
        if _pantry_has(name, pantry_words):
            have.append(item)
        else:
            sections.setdefault(_aisle(name), []).append(item)

    order = [a for a, _ in AISLES] + ["Everything else"]
    out = {
        "built": date.today().isoformat(), "week": week_iso,
        "sections": [{"name": a, "items": sections[a]}
                     for a in order if a in sections],
        "additions": old["additions"],
        "have": have,
    }
    save_shopping(out)
    return out


# ------------------------------------------------------------------ api

def api(path, body):
    """Dispatch for serve.py — every write rewrites its markdown file,
    then the caller rebuilds cook.html."""
    if path == "recipe":
        return recipe_detail(body.get("id", ""))

    if path == "addrecipe":
        out = add_recipe(body)
        if out.get("ok"):
            out["notes"] = {k: v["text"] for k, v in load_notes().items()}
        return out

    if path == "delrecipe":
        out = remove_recipe((body.get("id") or "").strip())
        if out.get("ok"):
            out["notes"] = {k: v["text"] for k, v in load_notes().items()}
        return out

    if path == "note":
        rid = (body.get("id") or "").strip()
        if not rid or not by_id(rid):
            return {"error": "unknown recipe"}
        notes = load_notes()
        text = _free_text(body.get("text"), 3000)
        if text:
            notes[rid] = {"title": by_id(rid)["t"], "text": text}
        else:
            notes.pop(rid, None)
        save_notes(notes)
        return {"ok": True, "notes": {k: v["text"] for k, v in notes.items()}}

    if path == "plan":
        plan = load_plan()
        week = body.get("week") or monday().isoformat()
        day = body.get("day")
        if day not in DAYS:
            return {"error": "bad day"}
        entries = plan.setdefault(week, {}).setdefault(day, [])
        if body.get("remove"):
            plan[week][day] = [e for e in entries
                               if e.get("id") != body.get("id")
                               or e.get("title") != body.get("title")]
        else:
            r = by_id(body.get("id", ""))
            title = body.get("title") or (r["t"] if r else "")
            if not title:
                return {"error": "no recipe"}
            entries.append({"title": title, "id": body.get("id", ""),
                            "lo": bool(body.get("lo"))})
        save_plan(plan)
        return {"ok": True, "plan": plan}

    if path == "taste":
        t = load_taste()
        group = body.get("group")
        item = (body.get("item") or "").strip()
        if group not in t or not item:
            return {"error": "bad taste entry"}
        if body.get("remove"):
            t[group] = [x for x in t[group] if x.lower() != item.lower()]
        elif not any(x.lower() == item.lower() for x in t[group]):
            t[group].append(item)
        save_taste(t)
        return {"ok": True, "taste": t}

    if path == "basketadd":
        names = body.get("items") or []
        if not isinstance(names, list):
            return {"error": "items must be a list"}
        added = basket_add(names, body.get("date"))
        return {"ok": True, "added": added, "basket": load_basket()[:120]}

    if path == "basketdel":
        want = (body.get("item") or "").strip().lower()
        items = [it for it in load_basket() if it["item"].lower() != want]
        save_basket(items)
        return {"ok": True, "basket": items[:120]}

    if path == "shopbuild":
        week = body.get("week") or monday().isoformat()
        return {"ok": True, "shopping": build_shopping(week)}

    if path == "shoptick":
        s = load_shopping()
        want = (body.get("text") or "").strip().lower()
        done = bool(body.get("done"))
        pools = [it for sec in s["sections"] for it in sec["items"]]
        pools += s["additions"]
        for it in pools:
            if it["text"].strip().lower() == want:
                it["done"] = done
        save_shopping(s)
        return {"ok": True}

    if path == "shopadd":
        s = load_shopping()
        text = (body.get("text") or "").strip()
        if not text:
            return {"error": "empty"}
        if any(it["text"].lower() == text.lower() for it in s["additions"]):
            return {"ok": True}
        s["additions"].append({"text": text, "detail": "", "done": False})
        save_shopping(s)
        return {"ok": True}

    if path == "shopdel":
        s = load_shopping()
        want = (body.get("text") or "").strip().lower()
        s["additions"] = [it for it in s["additions"]
                          if it["text"].lower() != want]
        save_shopping(s)
        return {"ok": True}

    if path == "shopclear":
        # Her "we should be able to empty it" (8 Oct): everything, her own
        # additions too. The page asks for a second tap; git keeps the old
        # list should she want a line back.
        save_shopping({"built": "", "week": "", "sections": [],
                       "additions": [], "have": []})
        return {"ok": True}

    if path == "find":
        on = body.get("on") or []
        if not isinstance(on, list):
            return {"error": "on must be a list"}
        p = load_pantry()
        p["find"] = [k for k in on if k in FIND_KEYS]
        kind = (body.get("kind") or "").strip()
        if kind and kind in {r["cat"] for r in index()}:
            p["find"].append("kind: " + kind)
        save_pantry(p)
        return {"ok": True}

    if path == "kitchen":
        p = load_pantry()
        p["kitchen"] = "dorm" if body.get("mode") == "dorm" else "full"
        save_pantry(p)
        return {"ok": True, "pantry": p}

    if path == "pantry":
        p = load_pantry()
        group = "staples" if body.get("group") == "staples" else "fresh"
        item = (body.get("item") or "").strip()
        if not item:
            return {"error": "empty"}
        if body.get("remove"):
            p[group] = [i for i in p[group] if i.lower() != item.lower()]
        elif item.lower() not in (i.lower() for i in p[group]):
            p[group].append(item)
        save_pantry(p)
        return {"ok": True, "pantry": p}

    if path == "cooked":
        c = load_cooked()
        title = (body.get("title") or "").strip()
        if not title:
            return {"error": "empty"}
        c["log"].insert(0, {"date": body.get("date")
                            or date.today().isoformat(),
                            "title": title, "id": body.get("id", ""),
                            "note": (body.get("note") or "").strip()})
        save_cooked(c)
        return {"ok": True}

    if path == "save":
        c = load_cooked()
        rid = (body.get("id") or "").strip()
        title = (body.get("title") or "").strip()
        if body.get("on"):
            if not any(e.get("id") == rid and rid or e["title"] == title
                       for e in c["saved"]):
                c["saved"].append({"title": title, "id": rid})
        else:
            c["saved"] = [e for e in c["saved"]
                          if not ((rid and e.get("id") == rid)
                                  or e["title"] == title)]
        save_cooked(c)
        return {"ok": True}

    return {"error": "unknown cook endpoint"}


# ----------------------------------------------------------------- page

def _page_data():
    """The compact per-recipe index the page loads: id, title, book,
    category, veg, minutes, yield, ingredients, image."""
    slim = []
    for r in index():
        fl = ((1 if r.get("quick") else 0) | (2 if r.get("few") else 0)
              | (4 if r.get("prot") else 0) | (8 if r.get("dorm") else 0)
              | (16 if r.get("prep") else 0))
        slim.append({"id": r["id"], "t": r["t"], "b": r["b"], "c": r["c"],
                     "y": r["y"], "m": r["m"], "tt": r.get("tot"),
                     "n": r["n"],
                     "img": _img_url(r["img"]),
                     "cat": r["cat"], "veg": r["veg"], "f": fl})
    return slim


def build(cfg=None):
    import build as B
    if cfg is None:
        try:
            with open(os.path.join(BRAIN, "config.json"), encoding="utf-8") as f:
                cfg = json.load(f)
        except Exception:
            cfg = {}
    import chrome as CHROME
    import md as MD

    os.makedirs(COOKDIR, exist_ok=True)
    if not os.path.exists(PANTRY):
        save_pantry(load_pantry())
    if not os.path.exists(PLAN):
        save_plan({})
    if not os.path.exists(COOKED):
        save_cooked({"log": [], "saved": []})
    if not os.path.exists(TASTE):
        save_taste(load_taste())
    if not os.path.exists(BASKET):
        save_basket(load_basket())

    # the data file only rewrites when the index cache did
    data = json.dumps(_page_data(), ensure_ascii=False,
                      separators=(",", ":"))
    old = _read(DATA_OUT)
    if old != data:
        with open(DATA_OUT, "w", encoding="utf-8") as f:
            f.write(data)

    this_week = monday().isoformat()
    next_week = (monday() + timedelta(days=7)).isoformat()
    state = {
        "plan": load_plan(),
        "shopping": load_shopping(),
        "pantry": load_pantry(),
        "cooked": load_cooked(),
        "taste": load_taste(),
        "basket": load_basket()[:120],
        "notes": {k: v["text"] for k, v in load_notes().items()},
        "weeks": [this_week, next_week],
        "today": date.today().isoformat(),
        "dow": date.today().weekday(),
    }

    page = TEMPLATE
    page = page.replace("__STYLE__",
                        (cfg.get("appearance", {}) or {}).get("style",
                                                              "workroom"))
    page = page.replace("__PALETTE__", B.palette_css(cfg))
    page = page.replace("__HEADER__", CHROME.header_html(
        current="cook", owner=cfg.get("owner", "")))
    page = page.replace("__ASK__", CHROME.ask_block())
    page = page.replace("__STATE__", MD.json_for_script(state, ensure_ascii=False))
    page = page.replace("__SWAPS__", MD.json_for_script(SWAPS, ensure_ascii=False))

    # same publish gate as the other pages: a page whose script cannot
    # parse is worse than a stale one.
    from shutil import which
    node = which("node")
    if node:
        import subprocess as _sp
        import tempfile as _tf
        for js in re.findall(r"<script>(.*?)</script>", page, re.S):
            with _tf.NamedTemporaryFile("w", suffix=".js",
                                        delete=False, encoding="utf-8") as tmp:
                tmp.write(js)
            try:
                r = _sp.run([node, "--check", tmp.name],
                            capture_output=True, text=True, timeout=20)
                if r.returncode != 0:
                    raise SystemExit("REFUSING to write cook.html — its "
                                     "script does not parse:\n"
                                     + r.stderr.strip()[:600])
            finally:
                os.unlink(tmp.name)

    with open(OUT, "w", encoding="utf-8") as f:
        f.write(page)
    return OUT


TEMPLATE = r"""<!doctype html>
<html lang="en" data-style="__STYLE__"><head>
<script>try{var _bs=localStorage.getItem('brain-style');
if(_bs)document.documentElement.setAttribute('data-style',_bs);}catch(e){}</script>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>Cook &mdash; the brain</title>
<link rel="icon" href="logo-192.png?v=5" type="image/png">
<link rel="apple-touch-icon" href="logo-180.png?v=5">
<link rel="stylesheet" href="appearance.css">
<style>
__PALETTE__
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--paper);color:var(--ink);
  font:400 var(--t-base)/1.55 var(--sans)}
a{color:var(--ink)}
""" + "NAVCSS_HEADERCSS" + r"""
/* the bottom padding keeps the last row clear of the floating button */
.kwrap{max-width:1060px;margin:0 auto;
  padding:20px 20px calc(100px + env(safe-area-inset-bottom,0px))}
/* the Kitchen's sections: underlined words in every style, so they never
   stack under the Life switch as its twin (switches.py draws them) */
.ktabs{margin:4px 0 20px}
.kh1{font:600 var(--t-2xl)/1.2 var(--serif);letter-spacing:-.01em;margin:6px 0 4px}
.kh2{font:600 var(--t-lg)/1.25 var(--serif);letter-spacing:-.01em;margin:6px 0 2px}
.klede{color:var(--dim);margin:0 0 16px;max-width:64ch}
.kfaint{color:var(--faint);font-size:var(--t-sm)}
/* Every button here also carries the main page's `act` (and the "+ plan"
   slots `mini`), so the active skin draws them exactly as it draws the rest
   of the app. The kitchen's own look is the fallback under :where(), which
   weighs nothing, so any skin rule wins it (28 Sep: the skin's chunky
   buttons stopped at the kitchen door). The ink primary keeps its fill and,
   like the main page's ink pills, casts no shadow. */
:where(.kbtn){display:inline-flex;align-items:center;gap:6px;border:1px solid var(--line);
  border-radius:9px;background:var(--surface);color:var(--ink);
  font:500 14px/1 var(--sans);padding:9px 14px;cursor:pointer}
:where(.kbtn):hover{background:var(--sunken,var(--surface))}
.kbtn.primary{background:var(--ink);color:var(--paper);border-color:var(--ink);
  box-shadow:none}
.kbtn.primary:hover{background:var(--ink);color:var(--paper);box-shadow:none}
:where(.kbtn.small){padding:6px 10px;font-size:13px}
.kbtn:disabled{opacity:.45;cursor:default}
a.kbtn{text-decoration:none}
/* tonight hero — the photo box only exists when there is a photo */
.khero{display:flex;gap:18px;border:1px solid var(--line);
  border-radius:var(--r-card,14px);background:var(--surface);
  overflow:hidden;margin:0 0 22px}
.khero .kimg{width:230px;min-height:150px;background:var(--sunken,#eee);
  background-size:cover;background-position:center;flex:none}
.khero .kbody{padding:16px 18px 14px;display:flex;flex-direction:column;gap:6px;
  min-width:0;flex:1}
.khero h2{font:600 var(--t-xl)/1.25 var(--serif);margin:0}
.khero .kacts{margin-top:auto;display:flex;gap:8px;flex-wrap:wrap;padding-top:10px}
.ksug{display:grid;grid-template-columns:repeat(auto-fill,minmax(160px,1fr));
  gap:10px;margin-top:12px}
.ksug .kcimg{height:88px}
.ksug .kct{font-size:13.5px;padding:8px 10px 2px}
.ksug .kcm{font-size:12px;padding:0 10px 8px}
.ksugbtn{margin:0 10px 10px}
/* week grid */
.kweekhead{display:flex;align-items:baseline;gap:6px 12px;margin:26px 0 8px;
  flex-wrap:wrap}
.kweekhead h3{font:600 var(--t-lg)/1.2 var(--serif);margin:0;white-space:nowrap}
.kdays{display:grid;grid-template-columns:repeat(7,1fr);gap:8px}
.kday{border:1px solid var(--line);border-radius:12px;background:var(--surface);
  padding:8px;min-height:118px;display:flex;flex-direction:column;gap:6px}
.kday.today{border-color:var(--ink);box-shadow:0 0 0 1px var(--ink)}
.kday .kd{font-size:var(--t-xs);font-weight:700;letter-spacing:.06em;
  text-transform:uppercase;color:var(--faint)}
.kday.today .kd{color:var(--ink)}
.kslot{border:1px dashed var(--line);border-radius:9px;color:var(--faint);
  font-size:13px;padding:8px;cursor:pointer;text-align:center;background:none;width:100%}
.kslot:hover{color:var(--ink);border-color:var(--ink)}
/* an empty night is the skin's small button, dashed: same family, still a gap */
.kslot.mini{border-style:dashed;border-color:var(--line);color:var(--dim);
  box-shadow:none;justify-content:center}
.kslot.klo{border-style:solid;color:var(--dim);font-style:italic}
.kmeal{border:1px solid var(--line);border-radius:9px;overflow:hidden;
  cursor:pointer;background:var(--paper)}
.kmeal .kmimg{height:52px;background-size:cover;background-position:center;
  background-color:var(--sunken,#eee)}
.kmeal .kmt{font-size:12.5px;line-height:1.3;padding:6px 7px;font-weight:500}
.kmeal .kmx{float:right;color:var(--faint);border:none;background:none;
  cursor:pointer;font-size:12px;padding:2px 4px}
.kmeal .kmx:hover{color:var(--ink)}
.kbalance{margin:10px 0 0;color:var(--dim);font-size:var(--t-sm)}
/* week planner */
.kplanbar{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin:0 0 10px}
.kplanbar label{display:flex;align-items:center;gap:6px;font-size:var(--t-sm)}
.kpn{border:1px solid var(--line);border-radius:8px;background:var(--bg);
  color:var(--ink);font:inherit;font-size:var(--t-sm);padding:3px 6px}
.kplan{border:1px solid var(--line);border-radius:var(--r-card);
  background:var(--card,var(--bg));padding:10px 12px;margin:0 0 14px}
.kprow{display:flex;align-items:center;gap:10px;padding:7px 0;
  border-bottom:1px solid var(--line)}
.kprow:last-of-type{border-bottom:0}
.kpimg{width:52px;height:52px;flex:none;border-radius:10px;
  background:var(--line) center/cover no-repeat}
.kpt{flex:1;min-width:0}
.kpt b{display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.kplanfoot{display:flex;align-items:center;gap:12px;flex-wrap:wrap;
  padding-top:10px;border-top:1px solid var(--line);margin-top:4px}
.kplanfoot .kacts{margin-left:auto}
@media(max-width:640px){.kplanfoot .kacts{margin-left:0}}
/* find */
.kctrl{display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin:0 0 12px}
.kctrl input[type=search]{flex:1 1 240px;border:1px solid var(--line);
  border-radius:9px;background:var(--surface);color:var(--ink);
  font:400 15px/1.3 var(--sans);padding:9px 12px;min-width:0}
.kchip{border:1px solid var(--line);border-radius:999px;background:var(--surface);
  color:var(--dim);font:500 13px/1 var(--sans);padding:7px 12px;cursor:pointer}
.kchip.on{background:var(--ink);color:var(--paper);border-color:var(--ink)}
.kctrl select{border:1px solid var(--line);border-radius:9px;
  background:var(--surface);color:var(--ink);font:400 14px/1.3 var(--sans);
  padding:8px 10px;max-width:210px}
.kgrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(190px,1fr));gap:12px}
.kcard{border:1px solid var(--line);border-radius:12px;background:var(--surface);
  overflow:hidden;cursor:pointer}
.kcard:hover{border-color:var(--ink)}
.kcard .kcimg{height:118px;background-size:cover;background-position:center;
  background-color:var(--sunken,#eee)}
.kcard .kct{font-weight:600;font-size:14px;line-height:1.3;padding:9px 11px 2px}
.kcard .kcm{color:var(--faint);font-size:12.5px;padding:0 11px 10px}
.kmore{margin:16px auto;display:block}
/* shopping */
.kshop{max-width:640px}
.kaisle{font:600 var(--t-base)/1.3 var(--serif);margin:20px 0 6px}
.kitem{display:flex;align-items:baseline;gap:10px;padding:7px 2px;
  border-bottom:1px solid var(--line)}
.kitem input{width:18px;height:18px;flex:none;accent-color:var(--ink)}
.kitem.done .kit{text-decoration:line-through;color:var(--faint)}
.kit{font-size:15px}
.kidet{color:var(--faint);font-size:12.5px}
.kitem .kmx{margin-left:auto;color:var(--faint);border:none;background:none;cursor:pointer}
/* the × is a 15px glyph: its tap area grows on a touch screen, the layout
   does not (phone sweep, 28 Sep) */
@media(pointer:coarse){
  .kmx{position:relative}
  .kmx::after{content:"";position:absolute;inset:-10px -8px}
}
.kaddrow{display:flex;gap:8px;margin:14px 0}
.kaddrow input{flex:1;border:1px solid var(--line);border-radius:9px;
  background:var(--surface);color:var(--ink);font:400 15px/1.3 var(--sans);
  padding:9px 12px}
details.khave{margin:18px 0;color:var(--dim)}
details.khave summary{cursor:pointer;font-weight:600}
/* pantry */
.kchips{display:flex;flex-wrap:wrap;gap:8px;margin:8px 0 20px}
.kpc{display:inline-flex;align-items:center;gap:7px;border:1px solid var(--line);
  border-radius:999px;background:var(--surface);padding:7px 13px;font-size:14px}
.kpc button{border:none;background:none;color:var(--faint);cursor:pointer;
  font-size:13px;padding:0}
.kpc button:hover{color:var(--ink)}
/* drawer */
.kdrawer{position:fixed;inset:0;z-index:60;display:none}
.kdrawer.open{display:block}
.kdrawer .kscrim{position:absolute;inset:0;background:rgba(0,0,0,.42)}
.kdrawer .kpanel{position:absolute;top:0;right:0;bottom:0;width:min(620px,100%);
  background:var(--paper);overflow-y:auto;box-shadow:-8px 0 40px rgba(0,0,0,.25)}
.kdrawer .kdimg{height:250px;background-size:cover;background-position:center;
  background-color:var(--sunken,#eee)}
.kdrawer .kdbody{padding:18px 24px 60px}
.kdrawer h2{font:600 var(--t-xl)/1.25 var(--serif);margin:2px 0 4px}
.kdmeta{color:var(--dim);font-size:var(--t-sm);margin:0 0 12px}
.kdacts{display:flex;gap:8px;flex-wrap:wrap;margin:12px 0 18px}
.kding li{margin:3px 0}
.kswap{color:var(--faint);font-size:12.5px;font-style:italic;margin:1px 0 3px}
.kdhead{font-style:italic;color:var(--dim);margin:0 0 12px}
.kdmethod p{margin:0 0 12px}
/* her notes on a recipe, and the add / edit form, both in the drawer */
.knotes{border-left:3px solid var(--line);padding:2px 0 2px 12px;margin:0 0 16px}
.knotes p{margin:0 0 8px}
.knotehd{font-size:var(--t-sm);color:var(--dim);margin:0 0 4px}
.klink{border:0;background:none;padding:0;font:inherit;color:var(--dim);
  text-decoration:underline;cursor:pointer}
.khead{display:flex;align-items:center;justify-content:space-between;gap:12px;
  flex-wrap:wrap}
.kform label{display:block;font-size:var(--t-sm);color:var(--dim);margin:14px 0 4px}
.kform input,.kform textarea{display:block;width:100%;box-sizing:border-box;
  border:1px solid var(--line);border-radius:9px;background:var(--surface);
  color:var(--ink);font:400 16px/1.45 var(--sans);padding:9px 12px}
.kform textarea{resize:vertical}
.kform .krow{display:flex;gap:10px;flex-wrap:wrap}
.kform .krow>div{flex:1 1 110px;min-width:0}
.kphoto{height:190px;border:1px dashed var(--line);border-radius:12px;margin:4px 0 0;
  background:var(--surface) center/cover no-repeat;display:flex;gap:8px;
  align-items:flex-end;padding:10px;box-sizing:border-box}
.kphoto.has{border-style:solid}
/* the buttons sit on the photo, so they carry their own ground; four
   classes, because Orbit's own rule for .act weighs three */
.kform .kphoto .kbtn.act{background:var(--paper);border:1px solid var(--line);
  padding:6px 12px}
/* display:block above beat the hidden attribute: the file picker and
   "Remove the photo" showed when they should not */
.kform [hidden]{display:none!important}
.kformmsg{min-height:1.3em;color:var(--dim);font-size:var(--t-sm);margin:4px 0 0}
.kformmsg.bad{color:var(--bad,#b3261e)}
.kclose{position:absolute;top:12px;right:14px;z-index:2;border:none;
  background:rgba(0,0,0,.45);color:#fff;width:34px;height:34px;
  border-radius:999px;font-size:17px;cursor:pointer}
/* day picker + cookmode */
.kpick{position:fixed;inset:0;z-index:70;display:none;align-items:center;
  justify-content:center}
.kpick.open{display:flex}
.kpick .kscrim{position:absolute;inset:0;background:rgba(0,0,0,.42)}
.kpick .kbox{position:relative;background:var(--paper);border-radius:14px;
  padding:20px 22px;min-width:280px;box-shadow:0 20px 60px rgba(0,0,0,.3)}
.kpick .kbox h3{margin:0 0 12px;font:600 var(--t-lg)/1.2 var(--serif)}
.kpick .kdaybtns{display:grid;grid-template-columns:repeat(2,1fr);gap:8px}
.kcookmode{position:fixed;inset:0;z-index:80;background:var(--paper);
  display:none;flex-direction:column;padding:26px clamp(20px,6vw,80px)}
.kcookmode.open{display:flex}
.kcookmode .kstep{flex:1;display:flex;align-items:center;
  font:400 clamp(20px,3.2vw,30px)/1.55 var(--serif);max-width:30em}
.kcookmode .kcnav{display:flex;gap:10px;align-items:center;padding:16px 0}
.kcookmode .kcount{color:var(--faint)}
.kcookmode .kctitle{color:var(--dim);font-size:15px}
@media(max-width:860px){
  .kdays{grid-template-columns:repeat(2,1fr)}
  .kday{min-height:90px}
  .khero{flex-direction:column}
  .khero .kimg{width:100%;height:170px}
  /* stacked, the body must not inherit the grid's wide minimum — without
     this the suggestion cards ran past the right edge of the screen */
  .khero .kbody{max-width:100%;box-sizing:border-box}
}
</style>
</head><body>
__HEADER__
<div class="kwrap">
<nav class="ktabs" id="ktabs">
<a href="#week" data-t="week">Week</a>
<a href="#find" data-t="find">Find</a>
<a href="#shop" data-t="shop">Shopping</a>
<a href="#pantry" data-t="pantry">Pantry</a>
<a href="#cooked" data-t="cooked">Cooked</a>
</nav>
<main id="kmain"></main>
</div>

<div class="kdrawer" id="kdrawer"><div class="kscrim"></div>
<div class="kpanel"><button class="kclose" id="kdclose">&times;</button>
<div id="kdcontent"></div></div></div>

<div class="kpick" id="kpick"><div class="kscrim"></div>
<div class="kbox"><h3 id="kpicktitle">Plan it</h3>
<div class="kdaybtns" id="kpickdays"></div></div></div>

<div class="kcookmode" id="kcookmode">
<div class="kctitle" id="kctitle"></div>
<div class="kstep" id="kstep"></div>
<div class="kcnav">
<button class="kbtn act" id="kprev">&larr; Back</button>
<button class="kbtn act primary" id="knext">Next &rarr;</button>
<span class="kcount" id="kcount"></span>
<button class="kbtn act" id="kexit" style="margin-left:auto">Done</button>
</div></div>

__ASK__
<script>
"use strict";
var STATE = __STATE__;
var SWAPS = __SWAPS__;
var SWAPKEYS = Object.keys(SWAPS);
function swapFor(name){
  var n=(name||"").toLowerCase();
  for(var i=0;i<SWAPKEYS.length;i++){
    if(n.indexOf(SWAPKEYS[i])>=0)return SWAPS[SWAPKEYS[i]];}
  return null;
}
var DATA = [];
var DAYS = ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"];
var DAYFULL = {Mon:"Monday",Tue:"Tuesday",Wed:"Wednesday",Thu:"Thursday",
  Fri:"Friday",Sat:"Saturday",Sun:"Sunday"};
var byId = {};
var esc = function(s){return String(s==null?"":s).replace(/[&<>"']/g,
  function(c){return {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c];});};
// A value going into an onclick="…" call. The browser decodes &#39; back to
// ' before the handler runs, so esc() alone let "Grandma's pie" end the
// string and break its buttons. A JSON literal survives the decoding.
var jsa = function(s){return esc(JSON.stringify(String(s==null?"":s)));};

function post(path, body){
  return fetch("/api/cook/"+path,{method:"POST",
    headers:{"Content-Type":"application/json"},
    body:JSON.stringify(body||{})}).then(function(r){return r.json();});
}

/* ---- pantry matching, same logic as the library's pantry.py ---- */
function pantryWords(){
  return STATE.pantry.staples.concat(STATE.pantry.fresh)
    .map(function(s){return s.trim().toLowerCase();}).filter(Boolean);
}
function covered(need, have){
  var nt = need.split(/\s+/);
  for(var i=0;i<have.length;i++){var h=have[i];
    if(h===need||nt.indexOf(h)>=0) return true;
    if(need.indexOf(h)>=0||h.indexOf(need)>=0) return true;
    for(var j=0;j<nt.length;j++){var t=nt[j];
      if(t.length>3&&h.length>3&&(t.indexOf(h)===0||h.indexOf(t)===0)) return true;}}
  return false;
}
function hash(s){
  var h=0;for(var i=0;i<s.length;i++){h=(h*31+s.charCodeAt(i))|0;}
  return h&0x7fffffff;
}
/* planning time: the stated total when the book gives one, else active */
function timeOf(r){return r.tt||r.m;}
function fmtT(min){
  if(!min)return "";
  if(min>=90)return (Math.round(min/30)*30/60)+" h";
  return min+" min";
}
/* dates on the page are day-first ("28 Sep"); the year only when it isn't this one */
var MON=["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
function fmtD(iso){
  var m=/^(\d{4})-(\d{2})-(\d{2})/.exec(iso||"");
  if(!m)return iso||"";
  return (+m[3])+" "+MON[+m[2]-1]+
    (m[1]!==String(STATE.today).slice(0,4)?" "+m[1]:"");
}
function missingCount(r, have){
  var miss=0;
  for(var i=0;i<r.n.length;i++){if(!covered(r.n[i],have)) miss++;}
  return miss;
}

/* ------------------------------- router ------------------------------- */
function tab(){
  var h=(location.hash||"#week").slice(1);
  return ["week","find","shop","pantry","cooked"].indexOf(h)>=0?h:"week";
}
function render(){
  var t=tab();
  document.querySelectorAll("#ktabs a").forEach(function(a){
    a.classList.toggle("on",a.dataset.t===t);});
  var m=document.getElementById("kmain");
  if(t==="week") m.innerHTML=weekView();
  if(t==="find"){m.innerHTML=findView();bindFind();}
  if(t==="shop") m.innerHTML=shopView();
  if(t==="pantry") m.innerHTML=pantryView();
  if(t==="cooked") m.innerHTML=cookedView();
}
window.addEventListener("hashchange",render);

/* -------------------------------- week -------------------------------- */
function planFor(week){return STATE.plan[week]||{};}
function todayEntry(){
  var wk=STATE.weeks[0], d=DAYS[STATE.dow];
  var e=(planFor(wk)[d]||[])[0];
  return e||null;
}
function recipeOf(e){return e&&e.id?byId[e.id]:null;}

function suggestions(n){
  var have=pantryWords();
  var savedIds={}; STATE.cooked.saved.forEach(function(s){if(s.id)savedIds[s.id]=1;});
  var cookedIds={}; STATE.cooked.log.forEach(function(e){if(e.id)cookedIds[e.id]=1;});
  var MAINS={"Pasta & noodles":1,"Chicken & poultry":1,"Fish & seafood":1,
    "Meat":1,"Soups & stews":1,"Rice & grains":1,"Beans & lentils":1,"Eggs":1};
  var dorm=STATE.pantry.kitchen==="dorm";
  var scored=[];
  for(var i=0;i<DATA.length;i++){var r=DATA[i];
    if(r.cat==="Sweets & baking"||r.cat==="Drinks"||r.cat==="Basics & sauces"||
       r.cat==="Snacks & starters") continue;
    if(!r.img) continue;                          // yummy means showable
    if(r.n.length<(MAINS[r.cat]?4:6)) continue;   // fried eggs are not dinner
    if(r.cat==="Eggs"&&r.n.length<5) continue;
    if(dorm&&!(r.f&8)) continue;
    var tm=timeOf(r); if(tm&&tm>60) continue;     // tonight, not a Sunday project
    var s=0;
    var isSaved=!!savedIds[r.id];
    if(isSaved) s+=cookedIds[r.id]?6:9;           // want-to-try first, then loved
    if(r.f&8) s+=2;                               // fits the dorm
    if(r.f&4) s+=2;                               // real protein
    if(r.f&1) s+=2;                               // quick
    if(r.veg) s+=1;
    var miss=missingCount(r,have);
    if(miss===0) s+=4; else if(miss===1) s+=2;
    if(s>5) scored.push([s+Math.random()*2,r,isSaved]);
  }
  scored.sort(function(a,b){return b[0]-a[0];});
  var out=[],seen={};
  for(var j=0;j<scored.length&&out.length<n;j++){
    var key=scored[j][1].t.toLowerCase();
    if(seen[key])continue; seen[key]=1;
    out.push({r:scored[j][1],saved:scored[j][2]});
  }
  return out;
}

/* ------------------------- the week planner --------------------------
   Picks N dinners that deliberately share ingredients, weighted by what
   she has said she likes (taste.md), what she actually buys (basket.md),
   and what she has saved or cooked. Greedy rather than exhaustive: a real
   optimum over 6,000 recipes is not worth the wait, and the shuffle
   button covers the cases where greed picks badly. */
var PLANPICK=null;               /* the proposal on screen, until accepted */

function tasteOf(){
  var t=STATE.taste||{love:[],avoid:[],bored:[]};
  var low=function(a){return (a||[]).map(function(s){
    return String(s).toLowerCase().trim();}).filter(Boolean);};
  return {love:low(t.love),avoid:low(t.avoid),bored:low(t.bored)};
}
/* her words are phrases ("fish, especially oily"), so match on any word of
   4+ letters rather than the whole string, which would never hit */
function phraseWords(p){
  return p.split(/[^a-zà-ÿ]+/).filter(function(w){return w.length>3;});
}
function hitsRecipe(phrase,r,hay){
  var ws=phraseWords(phrase);
  if(!ws.length) return hay.indexOf(phrase)>=0;
  for(var i=0;i<ws.length;i++){if(hay.indexOf(ws[i])>=0) return true;}
  return false;
}
function basketMap(){
  var m={},b=STATE.basket||[];
  for(var i=0;i<b.length;i++){m[String(b[i].item).toLowerCase()]=b[i].n;}
  return m;
}
/* staples are in the cupboard already, so two recipes "sharing" olive oil
   have not saved a single line on the shopping list */
function stapleSet(){
  var s={};(STATE.pantry.staples||[]).forEach(function(x){
    s[String(x).trim().toLowerCase()]=1;});
  return s;
}
function buyable(r,staples){
  var out=[];
  for(var i=0;i<r.n.length;i++){
    var n=r.n[i];
    if(!staples[n]) out.push(n);
  }
  return out;
}

function planCandidates(){
  var T=tasteOf(), B=basketMap(), have=pantryWords(), staples=stapleSet();
  var savedIds={}; STATE.cooked.saved.forEach(function(s){if(s.id)savedIds[s.id]=1;});
  var recent={}, cut=addDays(STATE.today,-21);
  STATE.cooked.log.forEach(function(e){if(e.id&&e.date>=cut)recent[e.id]=1;});
  var dorm=STATE.pantry.kitchen==="dorm";
  var out=[];
  for(var i=0;i<DATA.length;i++){
    var r=DATA[i];
    if(r.cat==="Sweets & baking"||r.cat==="Drinks"||r.cat==="Basics & sauces"||
       r.cat==="Snacks & starters") continue;
    if(r.n.length<5) continue;                 /* not a dinner */
    /* Minimising new shopping rewards tiny recipes, so scrambled eggs and
       aioli win a week unless dinner is defined properly: something to buy,
       and a protein or a vegetable dish behind it. */
    if(!(r.f&4)&&!r.veg) continue;
    if(dorm&&!(r.f&8)) continue;
    var tm=timeOf(r); if(tm&&tm>75) continue;
    var hay=(r.t+" "+r.n.join(" ")).toLowerCase();
    var veto=false;
    for(var a=0;a<T.avoid.length;a++){
      if(hitsRecipe(T.avoid[a],r,hay)){veto=true;break;}}
    if(veto) continue;
    var s=0;
    if(savedIds[r.id]) s+=9;
    if(recent[r.id]) s-=8;                     /* just had it */
    var loved=0;
    for(var l=0;l<T.love.length;l++){if(hitsRecipe(T.love[l],r,hay))loved++;}
    s+=Math.min(loved,2)*4;
    for(var bo=0;bo<T.bored.length;bo++){if(hitsRecipe(T.bored[bo],r,hay))s-=5;}
    var buy=buyable(r,staples), bs=0;
    for(var k=0;k<buy.length;k++){
      var n=B[buy[k]]||0;
      if(!n){for(var key in B){if(B[key]&&(buy[k].indexOf(key)>=0||
        key.indexOf(buy[k])>=0)){n=B[key];break;}}}
      if(n) bs+=Math.min(n,4);
    }
    if(buy.length) s+=Math.min(6,6*bs/(4*buy.length)*2);
    if(r.f&4) s+=2;
    if(r.f&1) s+=2;
    if(r.veg) s+=1;
    if(r.img) s+=1;
    var miss=missingCount(r,have);
    if(miss===0) s+=4; else if(miss===1) s+=2;
    if(buy.length<4) continue;                 /* a component, not a dinner */
    out.push({r:r,base:s,buy:buy});
  }
  return out;
}

/* One greedy run from a given opener: then take whatever adds most while
   re-using what the set already needs. `ow` is the overlap weight, kept a
   parameter so it can be turned off and measured against. */
/* "Cheese Tart" and "Cheese Tarts" are the same dinner twice. Exact-match
   dedup does not catch that, and the books are full of near-repeats. */
function titleKey(t){
  return t.toLowerCase().replace(/[^a-zà-ÿ ]/g," ")
    .replace(/\b(s|es)\b/g," ").replace(/s\b/g,"")
    .replace(/\s+/g," ").trim();
}
function tooSimilar(key,keys){
  if(keys[key]) return true;
  for(var k in keys){
    if(k.length>10&&key.length>10&&(k.indexOf(key)===0||key.indexOf(k)===0))
      return true;
  }
  return false;
}

function greedyFrom(pool,startIdx,n,ow){
  var start=pool[startIdx];
  if(!start) return [];
  var chosen=[start], need={}, keys={}, cats={}, used={};
  keys[titleKey(start.r.t)]=1; cats[start.r.cat]=1; used[startIdx]=1;
  start.buy.forEach(function(x){need[x]=1;});
  var capCat=Math.max(2,Math.ceil(n/3));   /* variety is not negotiable */
  while(chosen.length<n){
    var best=-1,bestS=-1e9;
    for(var i=0;i<pool.length;i++){
      if(used[i]) continue;
      var c=pool[i];
      if(tooSimilar(titleKey(c.r.t),keys)) continue;
      if((cats[c.r.cat]||0)>=capCat) continue;
      var shared=0;
      for(var j=0;j<c.buy.length;j++){if(need[c.buy[j]])shared++;}
      var fresh=c.buy.length-shared;
      /* Both halves matter. Rewarding shared alone picks big dishes that
         happen to touch everything; penalising fresh alone picks the
         smallest recipe in the book. */
      var s=c.base*0.55+shared*1.5*ow-fresh*0.85*ow-(cats[c.r.cat]||0)*1.4;
      if(s>bestS){bestS=s;best=i;}
    }
    if(best<0) break;
    used[best]=1;
    var pick=pool[best];
    chosen.push(pick);
    keys[titleKey(pick.r.t)]=1;
    cats[pick.r.cat]=(cats[pick.r.cat]||0)+1;
    pick.buy.forEach(function(x){need[x]=1;});
  }
  return chosen;
}

function distinctOf(chosen){
  var seen={};
  chosen.forEach(function(c){c.buy.forEach(function(x){seen[x]=1;});});
  return Object.keys(seen).length;
}

/* The opener decides most of the outcome, so try a spread of them and keep
   the set that feeds her best for the fewest distinct things to buy. `spin`
   moves to the next-best set, which is what the shuffle button wants. */
function planWeek(n,spin,ow){
  var cands=planCandidates();
  if(!cands.length) return [];
  if(ow===undefined) ow=1.15;
  cands.sort(function(a,b){return b.base-a.base;});
  var pool=cands.slice(0,320);
  var runs=[];
  for(var s=0;s<14&&s<pool.length;s++){
    var set=greedyFrom(pool,s,n,ow);
    if(set.length<Math.min(n,2)) continue;
    var taste=0;set.forEach(function(c){taste+=c.base;});
    runs.push({set:set,score:taste-2.6*distinctOf(set)});
  }
  if(!runs.length) return [];
  runs.sort(function(a,b){return b.score-a.score;});
  return runs[(spin||0)%runs.length].set;
}

function planStats(chosen){
  var staples=stapleSet(), seen={}, dup=0, total=0;
  chosen.forEach(function(c){
    c.buy.forEach(function(x){
      total++;
      if(seen[x])dup++; else seen[x]=1;});});
  var distinct=Object.keys(seen).length;
  var shared=[];
  var count={};
  chosen.forEach(function(c){c.buy.forEach(function(x){
    count[x]=(count[x]||0)+1;});});
  for(var k in count){if(count[k]>1)shared.push([k,count[k]]);}
  shared.sort(function(a,b){return b[1]-a[1];});
  return {distinct:distinct,total:total,dup:dup,
          shared:shared.slice(0,8).map(function(x){return x[0];})};
}

window.doPlanWeek=function(week,spin){
  var n=parseInt((document.getElementById("kpn")||{}).value||"5",10);
  PLANPICK={week:week,spin:spin||0,items:planWeek(n,spin||0)};
  render();
};
window.planSwap=function(idx){
  if(!PLANPICK)return;
  var n=PLANPICK.items.length;
  var fresh=planWeek(n,PLANPICK.spin+7+idx);
  var have={};PLANPICK.items.forEach(function(c,i){if(i!==idx)have[c.r.id]=1;});
  for(var i=0;i<fresh.length;i++){
    if(!have[fresh[i].r.id]){PLANPICK.items[idx]=fresh[i];break;}}
  render();
};
window.planDrop=function(){PLANPICK=null;render();};
window.planAccept=function(){
  if(!PLANPICK)return;
  var week=PLANPICK.week, p=STATE.plan[week]=STATE.plan[week]||{};
  var free=DAYS.filter(function(d){return !(p[d]||[]).length;});
  var items=PLANPICK.items.slice(0,free.length);
  items.forEach(function(c,i){
    var d=free[i];
    (p[d]=p[d]||[]).push({title:c.r.t,id:c.r.id,lo:false});
    post("plan",{week:week,day:d,id:c.r.id,title:c.r.t});
  });
  PLANPICK=null;
  render();
};

function plannerPanel(week){
  var free=DAYS.filter(function(d){
    return !((planFor(week)[d])||[]).length;}).length;
  var head='<div class="kplanbar">'+
    '<button class="kbtn act primary" onclick="doPlanWeek('+jsa(week)+',0)">'+
    'Plan my week</button>'+
    '<label class="kfaint">meals <select id="kpn" class="kpn">'+
    [3,4,5,6,7].map(function(v){
      return '<option'+(v===5?" selected":"")+'>'+v+'</option>';}).join("")+
    '</select></label>'+
    '<span class="kfaint">'+free+' free '+(free===1?"day":"days")+
    ' this week</span></div>';
  if(!PLANPICK||PLANPICK.week!==week) return head;
  var st=planStats(PLANPICK.items);
  var rows=PLANPICK.items.map(function(c,i){
    var r=c.r, bits=[];
    if(timeOf(r))bits.push(fmtT(timeOf(r)));
    bits.push(r.b);
    return '<div class="kprow">'+
      (r.img?'<div class="kpimg" style="background-image:url(\''+
        encodeURI(r.img)+'\')"></div>':'<div class="kpimg"></div>')+
      '<div class="kpt"><b>'+esc(r.t)+'</b><div class="kfaint">'+
      esc(bits.join(" · "))+'</div></div>'+
      '<button class="kbtn act small" onclick="openDetail('+jsa(r.id)+
      ')">Recipe</button>'+
      '<button class="kbtn act small" onclick="planSwap('+i+')">Swap</button>'+
      '</div>';
  }).join("");
  var overlap=st.shared.length
    ? "They share "+st.shared.length+" ingredients: "+
      st.shared.map(esc).join(", ")+"."
    : "Nothing shared, which is unusual — try shuffling.";
  return head+'<div class="kplan">'+rows+
    '<div class="kplanfoot"><div class="kfaint">'+st.distinct+
    ' things to buy for '+PLANPICK.items.length+' dinners. '+overlap+
    '</div><div class="kacts">'+
    '<button class="kbtn act primary" onclick="planAccept()">Use these</button>'+
    '<button class="kbtn act" onclick="doPlanWeek('+jsa(week)+','+
    (PLANPICK.spin+1)+')">Shuffle</button>'+
    '<button class="kbtn act" onclick="planDrop()">Discard</button>'+
    '</div></div></div>';
}

function mealCard(e,week,day){
  var r=recipeOf(e);
  var img=r&&r.img?'<div class="kmimg" style="background-image:url(\''+
    encodeURI(r.img)+'\')"></div>':"";
  return '<div class="kmeal" data-id="'+esc(e.id)+'" onclick="openDetail('+
    jsa(e.id)+')">'+img+'<div class="kmt">'+
    '<button class="kmx" title="Remove" onclick="unplan(event,'+jsa(week)+
    ','+jsa(day)+','+jsa(e.id)+',this)">&times;</button>'+
    (e.lo?'<span class="kfaint">&#8635; </span>':"")+
    esc(e.title)+
    (e.lo?' <span class="kfaint">leftovers</span>'
     :(r&&timeOf(r)?' <span class="kfaint">'+fmtT(timeOf(r))+'</span>':""))+
    '</div></div>';
}

function weekView(){
  var wk=STATE.weeks[0];
  var out='<h1 class="kh1">The week</h1>';
  var t=todayEntry(), r=recipeOf(t);
  if(t){
    // no photo, no box: the text takes the width (an empty beige block
    // sat on top of the card on a phone)
    var img=r&&r.img?'<div class="kimg" style="background-image:url(\''+
      encodeURI(r.img)+'\')"></div>':"";
    out+='<div class="khero">'+img+'<div class="kbody">'+
      '<div class="kfaint">Tonight</div><h2>'+
      (t.lo?'&#8635; ':"")+esc(t.title)+'</h2>'+
      (r?'<div class="kfaint">'+(t.lo?'leftovers &middot; ':"")+esc(r.b)+
        (!t.lo&&timeOf(r)?' &middot; '+fmtT(timeOf(r)):"")+
        (r.y?' &middot; '+esc(r.y):"")+'</div>':"")+
      '<div class="kacts">'+
      (t.id?'<button class="kbtn act primary" onclick="cookMode('+jsa(t.id)+')">Cook</button>':"")+
      (t.id?'<button class="kbtn act" onclick="openDetail('+jsa(t.id)+')">Recipe</button>':"")+
      '<button class="kbtn act" onclick="logCooked('+jsa(t.id||"")+','+
        jsa(t.title)+')">Cooked it</button>'+
      '</div></div></div>';
  } else {
    var lohero="";
    if(STATE.dow>0){
      var yd=(planFor(STATE.weeks[0])[DAYS[STATE.dow-1]]||[]).filter(
        function(e){var r=recipeOf(e);return !e.lo&&r&&(r.f&16);})[0];
      if(yd)lohero='<button class="kbtn act primary" onclick="planLeftovers('+
        jsa(STATE.weeks[0])+',\''+DAYS[STATE.dow]+'\','+jsa(yd.id)+
        ','+jsa(yd.title)+')">&#8635; Leftovers of '+
        esc(yd.title)+'</button>';
    }
    var sug=suggestions(4);
    out+='<div class="khero"><div class="kbody" style="padding:18px;width:100%">'+
      '<div class="kfaint">Tonight</div><h2>Nothing planned yet</h2>'+
      (lohero?'<div class="kacts" style="margin:8px 0 2px">'+lohero+'</div>':"")+
      '<div class="ksug">'+sug.map(function(x){var r=x.r;
        var bits=[];if(timeOf(r))bits.push(fmtT(timeOf(r)));
        bits.push(r.b);
        return '<div class="kcard" onclick="openDetail('+jsa(r.id)+')">'+
          '<div class="kcimg" style="background-image:url(\''+encodeURI(r.img)+
          '\')"></div><div class="kct">'+(x.saved?'&#9733; ':"")+esc(r.t)+
          '</div><div class="kcm">'+esc(bits.join(" · "))+
          '</div><button class="kbtn act small ksugbtn" onclick="planTonight(event,'+
          jsa(r.id)+','+jsa(r.t)+')">+ tonight</button></div>';
      }).join("")+'</div>'+
      '<div class="kacts" style="margin-top:10px">'+
      '<a class="kbtn act" href="#find">Browse everything &rarr;</a></div></div></div>';
  }
  STATE.weeks.forEach(function(wk,wi){
    var p=planFor(wk);
    var planned=[]; DAYS.forEach(function(d){(p[d]||[]).forEach(function(e){
      var r=recipeOf(e); if(r)planned.push({r:r,lo:e.lo});});});
    var veg=planned.filter(function(x){return x.r.veg;}).length;
    var fish=planned.filter(function(x){return x.r.cat==="Fish & seafood";}).length;
    var times=planned.filter(function(x){return !x.lo;})
      .map(function(x){return timeOf(x.r);})
      .filter(Boolean).sort(function(a,b){return a-b;});
    var med=times.length?times[Math.floor(times.length/2)]:null;
    out+='<div class="kweekhead"><h3>'+(wi===0?"This week":"Next week")+
      '</h3><span class="kfaint">week of '+esc(fmtD(wk))+'</span>'+
      '<button class="kbtn act small" style="margin-left:auto" '+
      'onclick="buildShopping('+jsa(wk)+')">Build shopping list</button></div>';
    if(wi===0) out+=plannerPanel(wk);
    out+='<div class="kdays">'+DAYS.map(function(d,di){
      var isToday=wi===0&&di===STATE.dow;
      var meals=(p[d]||[]).map(function(e){return mealCard(e,wk,d);}).join("");
      var ghost="";
      if(!(p[d]||[]).length){
        // yesterday cooked a keeper → tonight can just reheat it
        var prev=di>0?(p[DAYS[di-1]]||[])
          :(wi===1?((planFor(STATE.weeks[0])||{})["Sun"]||[]):[]);
        for(var gi=0;gi<prev.length;gi++){
          var pe=prev[gi],pr=recipeOf(pe);
          if(!pe.lo&&pr&&(pr.f&16)){
            var short=pe.title.length>24?pe.title.slice(0,22)+"\u2026":pe.title;
            ghost='<button class="kslot mini klo" onclick="planLeftovers('+
              jsa(wk)+',\''+d+'\','+jsa(pe.id)+','+
              jsa(pe.title)+')">&#8635; leftovers of '+
              esc(short)+'</button>';
            break;}}}
      return '<div class="kday'+(isToday?" today":"")+'"><div class="kd">'+d+
        '</div>'+meals+ghost+'<button class="kslot mini" onclick="pickFor('+jsa(wk)+
        ',\''+d+'\')">+ plan</button></div>';
    }).join("")+'</div>';
    // Counts, never advice: nights with a dinner on them, and a kind only
    // once there is one ("0 veg" read as a scolding, 28 Sep).
    var counts=[];
    var nights=DAYS.filter(function(d){return (p[d]||[]).length;}).length;
    if(nights){counts.push(nights+(nights===1?" dinner":" dinners")+" planned");
      if(veg)counts.push(veg+" vegetarian"); if(fish)counts.push(fish+" with fish");
      if(med)counts.push("typically "+med+" min");}
    var cookedThisWk=STATE.cooked.log.filter(function(e){
      return e.date>=wk&&e.date<addDays(wk,7);}).length;
    if(wi===0&&cookedThisWk)counts.push(cookedThisWk+" cooked so far");
    if(counts.length)out+='<div class="kbalance">'+counts.join(" &middot; ")+'</div>';
  });
  return out;
}
function addDays(iso,n){
  var d=new Date(iso+"T12:00:00");d.setDate(d.getDate()+n);
  return d.toISOString().slice(0,10);
}
window.unplan=function(ev,week,day,id,el){
  ev.stopPropagation();
  var e=(STATE.plan[week]&&STATE.plan[week][day]||[]).filter(function(x){
    return x.id===id;})[0];
  if(!e)return;
  STATE.plan[week][day]=STATE.plan[week][day].filter(function(x){return x!==e;});
  post("plan",{week:week,day:day,id:id,title:e.title,remove:true});
  render();
};
window.planTonight=function(ev,id,title){
  ev.stopPropagation();
  var week=STATE.weeks[0],day=DAYS[STATE.dow];
  if(!STATE.plan[week])STATE.plan[week]={};
  if(!STATE.plan[week][day])STATE.plan[week][day]=[];
  STATE.plan[week][day].push({title:title,id:id,lo:false});
  post("plan",{week:week,day:day,id:id,title:title});
  render();
};
window.planLeftovers=function(week,day,id,title){
  if(!STATE.plan[week])STATE.plan[week]={};
  if(!STATE.plan[week][day])STATE.plan[week][day]=[];
  STATE.plan[week][day].push({title:title,id:id,lo:true});
  post("plan",{week:week,day:day,id:id,title:title,lo:true});
  render();
};
window.buildShopping=function(week){
  post("shopbuild",{week:week}).then(function(res){
    if(res.shopping){STATE.shopping=res.shopping;location.hash="#shop";render();}
  });
};
window.logCooked=function(id,title){
  post("cooked",{id:id,title:title}).then(function(){
    STATE.cooked.log.unshift({date:STATE.today,id:id,title:title,note:""});
    render();
  });
};

/* ---- the day picker: plan a recipe into a day ---- */
var pickTarget=null;   // {week,day} slot waiting for a recipe
var pickRecipe=null;   // recipe waiting for a slot
window.pickFor=function(week,day){
  pickTarget={week:week,day:day};
  location.hash="#find";
  render();
  var q=document.getElementById("kq");
  if(q){q.placeholder="Pick for "+DAYFULL[day]+" — search...";q.focus();}
};
window.planPick=function(id,title){
  pickRecipe={id:id,title:title};
  if(pickTarget){placeMeal(pickTarget.week,pickTarget.day);return;}
  var box=document.getElementById("kpickdays");
  box.innerHTML=STATE.weeks.map(function(wk,wi){
    return DAYS.map(function(d){
      return '<button class="kbtn act" onclick="placeMeal('+jsa(wk)+',\''+d+
        '\')">'+(wi?"next ":"")+DAYFULL[d]+'</button>';
    }).join("");
  }).join("");
  document.getElementById("kpicktitle").textContent="Which night?";
  document.getElementById("kpick").classList.add("open");
};
window.placeMeal=function(week,day){
  var r=pickRecipe; if(!r)return;
  document.getElementById("kpick").classList.remove("open");
  closeDetail();
  if(!STATE.plan[week])STATE.plan[week]={};
  if(!STATE.plan[week][day])STATE.plan[week][day]=[];
  STATE.plan[week][day].push({title:r.title,id:r.id});
  post("plan",{week:week,day:day,id:r.id,title:r.title});
  pickRecipe=null;pickTarget=null;
  location.hash="#week";render();
};
document.getElementById("kpick").querySelector(".kscrim")
  .addEventListener("click",function(){
    document.getElementById("kpick").classList.remove("open");});

/* -------------------------------- find -------------------------------- */
/* Find opens on the filters she last set (pantry.md's ## Find, so the desk
   and the phone agree), and the first time on Weeknight: her "easy to cook,
   yummy, cheap, time friendly, even meal-prep friendly" (8 Oct). The
   search box and the book are per visit. */
var FINDKEYS={weeknight:"wk",quick:"qk",few:"few",protein:"prot",
  "dorm-friendly":"dorm","meal-prep":"prep",pantry:"pantry",veg:"veg",saved:"saved"};
var find={q:"",wk:false,qk:false,few:false,prot:false,prep:false,dorm:false,
  pantry:false,veg:false,saved:false,book:"",cat:"",shown:60};
(STATE.pantry.find==null?["weeknight"]:STATE.pantry.find).forEach(function(k){
  if(FINDKEYS[k])find[FINDKEYS[k]]=true;
  else if(k.indexOf("kind:")===0)find.cat=k.slice(5).trim();
});
if(STATE.pantry.kitchen==="dorm")find.dorm=true;
function findOn(){
  for(var k in FINDKEYS){if(find[FINDKEYS[k]])return true;}
  return !!find.cat;
}
var findSaveT=null;
function saveFind(){
  var on=[];
  for(var k in FINDKEYS){if(find[FINDKEYS[k]])on.push(k);}
  STATE.pantry.find=on.concat(find.cat?["kind: "+find.cat]:[]);
  /* a burst of chip taps is one write */
  clearTimeout(findSaveT);
  findSaveT=setTimeout(function(){post("find",{on:on,kind:find.cat});},700);
}
/* Weeknight: a dinner from the photographed books (the modern weeknight
   ones; a photo is the best "yummy" signal the library has) or her own
   recipes, in about 45 minutes or a batch that keeps, 11 ingredients at
   most, no pricey cut. Measured 8 Oct: about 150 of 6,348, nearly all real
   dinners, where Quick + Meal-prep + 5 ingredients gave compotes, hare
   and kidneys from the one French encyclopedia. */
var WK_NOTMEAL={"Sweets & baking":1,"Drinks":1,"Basics & sauces":1,
  "Snacks & starters":1,"Breakfast":1};
var WK_MAINS={"Pasta & noodles":1,"Chicken & poultry":1,"Fish & seafood":1,
  "Meat":1,"Soups & stews":1,"Rice & grains":1,"Beans & lentils":1,"Eggs":1};
var WK_PRICEY=/lobster|scallop|\bveal\b|\blamb\b|\bduck\b|\bhare\b|rabbit|venison|foie|truffle|caviar|saffron|\bcrab\b|oyster|tenderloin|filet mignon|rib-?eye|sirloin|\bsteaks?\b|pine nuts|langoustine|monkfish|halibut|swordfish|sea bass|short ribs|prime rib|wagyu|porcini|morel|pistachio|marrow/i;
var WK_NOTDINNER=/\btartes?\b|\btarts?\b|caramel|compote|coulis|\bjam\b|negroni|cocktail|spritz|martini|margarita|lemonade|syrup|granola|porridge|oatmeal|pancake|waffle|muffin|\bbread\b|\bnaan\b|biscuit|scone|crumble|cobbler|\bcakes?\b|cookie|\bpie\b|galette|sorbet|custard|pudding|frangipane|brownie|fudge|\btoast\b|clafout|caf[eé] de|coffee|\bchai\b/i;
var WK_COMPONENT=/\b(sauce|gravy|dip|dressing|vinaigrette|pesto|salsa|stock|broth|steamed rice)\s*$/i;
/* Two books are illustrated, not photographed: an onion drawing heading
   the list sold nothing (8 Oct). A photo of the dish ranks first. */
var DRAWN={"Essentials of Classic Italian Cooking":1,"Salt, Fat, Acid, Heat":1};
function picOf(r){return r.img?(DRAWN[r.b]?1:2):0;}
function weeknight(r){
  if(WK_NOTMEAL[r.cat])return false;
  var mine=r.b==="My recipes";
  if(!r.img&&!mine)return false;
  if(WK_NOTDINNER.test(r.t))return false;
  /* a sauce is not a dinner, a dinner in a sauce is: the title's head */
  var head=r.t.split(/:| with /i)[0];
  if(WK_COMPONENT.test(head)&&!/\b(in|on|over)\b/i.test(head))return false;
  if(!(WK_MAINS[r.cat]||(r.f&4)||mine))return false;
  if(r.n.length<(WK_MAINS[r.cat]?4:6)||r.n.length>11)return false;
  if(r.cat==="Eggs"&&r.n.length<5)return false;
  if(WK_PRICEY.test(r.n.join(" ")+" "+r.t))return false;
  var tm=timeOf(r);
  return !!((r.f&1)||(tm&&tm<=45)||((r.f&16)&&(!tm||tm<=90)));
}
function findView(){
  var books={};DATA.forEach(function(r){books[r.b]=1;});
  var cats={};DATA.forEach(function(r){cats[r.cat]=1;});
  return '<div class="khead"><h1 class="kh1">Find a recipe</h1>'+
  '<button class="kbtn act" onclick="addRecipe()">+ Add a recipe</button></div>'+
  '<p class="klede">'+DATA.length.toLocaleString("en")+' recipes from your own cookbooks.</p>'+
  '<div class="kctrl">'+
  '<input type="search" id="kq" placeholder="Search title or ingredient..." value="'+esc(find.q)+'">'+
  '<button class="kchip'+(find.wk?" on":"")+'" data-f="wk" title="A dinner in about 45 minutes or a batch that keeps, 11 ingredients at most, no pricey cuts">Weeknight</button>'+
  '<button class="kchip'+(find.qk?" on":"")+'" data-f="qk" title="Under 30 minutes, or very few steps">Quick</button>'+
  '<button class="kchip'+(find.few?" on":"")+'" data-f="few" title="At most 5 ingredients beyond the cupboard — spices, oils, vinegars and condiments don\'t count">&le;5 ingredients</button>'+
  '<button class="kchip'+(find.prot?" on":"")+'" data-f="prot" title="Built around meat, fish, eggs, tofu or legumes">High protein</button>'+
  '<button class="kchip'+(find.dorm?" on":"")+'" data-f="dorm" title="A real meal on two burners — no oven, no machines">Dorm-friendly</button>'+
  '<button class="kchip'+(find.prep?" on":"")+'" data-f="prep" title="Keeps and reheats — stews, legumes, big batches, or the book says so">Meal-prep</button>'+
  '<button class="kchip'+(find.pantry?" on":"")+'" data-f="pantry">From my pantry</button>'+
  '<button class="kchip'+(find.veg?" on":"")+'" data-f="veg">Veg</button>'+
  '<button class="kchip'+(find.saved?" on":"")+'" data-f="saved">Saved &#9733;</button>'+
  '<select id="kbook"><option value="">All books</option>'+
    Object.keys(books).sort().map(function(b){
      return '<option'+(find.book===b?" selected":"")+'>'+esc(b)+'</option>';
    }).join("")+'</select>'+
  '<select id="kcat"><option value="">All kinds</option>'+
    Object.keys(cats).sort().map(function(c){
      return '<option'+(find.cat===c?" selected":"")+'>'+esc(c)+'</option>';
    }).join("")+'</select>'+
  '</div><div id="kresults"></div>';
}
function bindFind(){
  var q=document.getElementById("kq");
  var t;q.addEventListener("input",function(){
    clearTimeout(t);t=setTimeout(function(){
      find.q=q.value;find.shown=60;results();},180);});
  document.querySelectorAll(".kchip").forEach(function(c){
    c.addEventListener("click",function(){
      var f=c.dataset.f;
      if(f==="wk")find.wk=!find.wk;
      if(f==="qk")find.qk=!find.qk;
      if(f==="few")find.few=!find.few;
      if(f==="prot")find.prot=!find.prot;
      if(f==="dorm")find.dorm=!find.dorm;
      if(f==="prep")find.prep=!find.prep;
      if(f==="pantry")find.pantry=!find.pantry;
      if(f==="veg")find.veg=!find.veg;
      if(f==="saved")find.saved=!find.saved;
      saveFind();find.shown=60;render();results();});});
  document.getElementById("kbook").addEventListener("change",function(e){
    find.book=e.target.value;find.shown=60;results();});
  document.getElementById("kcat").addEventListener("change",function(e){
    find.cat=e.target.value;saveFind();find.shown=60;results();});
  results();
}
function results(){
  var el=document.getElementById("kresults");if(!el)return;
  var q=find.q.trim().toLowerCase();
  var have=find.pantry?pantryWords():null;
  var savedIds={},savedTitles={};
  STATE.cooked.saved.forEach(function(s){
    if(s.id)savedIds[s.id]=1;savedTitles[s.title.toLowerCase()]=1;});
  var hits=[];
  for(var i=0;i<DATA.length;i++){var r=DATA[i];
    if(find.book&&r.b!==find.book)continue;
    if(find.cat&&r.cat!==find.cat)continue;
    if(find.wk&&!weeknight(r))continue;
    if(find.qk&&!(r.f&1))continue;
    if(find.few&&!(r.f&2))continue;
    if(find.prot&&!(r.f&4))continue;
    if(find.dorm&&!(r.f&8))continue;
    if(find.prep&&!(r.f&16))continue;
    if(find.veg&&!r.veg)continue;
    if(find.saved&&!(savedIds[r.id]||savedTitles[r.t.toLowerCase()]))continue;
    var miss=0;
    if(have){miss=missingCount(r,have);if(miss>1)continue;if(r.n.length<3)continue;}
    if(q){
      var hay=r.t.toLowerCase();
      if(hay.indexOf(q)<0&&r.n.join(" ").indexOf(q)<0)continue;}
    hits.push([miss,r]);
  }
  var isSaved=function(r){return savedIds[r.id]||savedTitles[r.t.toLowerCase()]?1:0;};
  if(have)hits.sort(function(a,b){return a[0]-b[0];});
  else hits.sort(function(a,b){
    // saved first, the nearest thing the library has to "she liked it";
    // then photos, then a stable shuffle so the books mix instead of
    // one book monopolising the first screens
    var s=isSaved(b[1])-isSaved(a[1]);
    var d=picOf(b[1])-picOf(a[1]);
    return s||d||hash(a[1].id)-hash(b[1].id);});
  var shown=hits.slice(0,find.shown);
  el.innerHTML='<p class="kfaint">'+hits.length+' recipes'+
  (findOn()?' &middot; <a href="#" id="kclear">clear filters</a>':"")+'</p>'+
  '<div class="kgrid">'+shown.map(function(h){var r=h[1];
    var img=r.img?'<div class="kcimg" style="background-image:url(\''+
      encodeURI(r.img)+'\')"></div>':'<div class="kcimg"></div>';
    var bits=[r.b];if(timeOf(r))bits.push(fmtT(timeOf(r)));
    if(have&&h[0])bits.push(h[0]+" missing");
    return '<div class="kcard" onclick="openDetail('+jsa(r.id)+')">'+img+
      '<div class="kct">'+esc(r.t)+'</div><div class="kcm">'+
      esc(bits.join(" · "))+'</div></div>';
  }).join("")+'</div>'+
  (hits.length>find.shown?'<button class="kbtn act kmore" id="kmorebtn">Show more</button>':"");
  var mb=document.getElementById("kmorebtn");
  if(mb)mb.addEventListener("click",function(){find.shown+=60;results();});
  var cl=document.getElementById("kclear");
  if(cl)cl.addEventListener("click",function(e){
    e.preventDefault();
    for(var k in FINDKEYS)find[FINDKEYS[k]]=false;
    find.cat="";saveFind();find.shown=60;render();});
}

/* ------------------------------- detail ------------------------------- */
var currentDetail=null;
window.openDetail=function(id){
  var r=byId[id];
  var d=document.getElementById("kdrawer");
  var c=document.getElementById("kdcontent");
  d.classList.add("open");document.body.style.overflow="hidden";
  c.innerHTML='<div class="kdbody"><p class="kfaint">Loading&hellip;</p></div>';
  fetch("/api/cook/recipe?id="+encodeURIComponent(id))
  .then(function(x){return x.json();})
  .then(function(det){
    currentDetail=det;
    var saved=STATE.cooked.saved.some(function(s){return s.id===id;});
    var have=pantryWords();
    var img=det.img?'<div class="kdimg" style="background-image:url(\''+
      encodeURI(det.img)+'\')"></div>':"";
    var meta=[det.b,det.c].filter(Boolean).join(" · ");
    if(det.pg)meta+=" · p."+det.pg;
    var bits=[];if(det.y)bits.push(det.y);
    if(det.tot&&det.m&&det.tot>det.m)
      bits.push(det.m+" min active, "+fmtT(det.tot)+" total");
    else if(det.tot)bits.push(fmtT(det.tot));
    else if(det.m)bits.push(det.m+" min");
    var note=(STATE.notes||{})[id]||"";
    var orig=/^https?:\/\//.test(det.source||"")?' · <a href="'+esc(det.source)+
      '" target="_blank" rel="noopener noreferrer">the original</a>':"";
    c.innerHTML=img+'<div class="kdbody">'+
      '<h2>'+esc(det.t)+'</h2>'+
      '<p class="kdmeta">'+esc(meta)+(bits.length?' — '+esc(bits.join(", ")):"")+orig+'</p>'+
      '<div class="kdacts">'+
      '<button class="kbtn act primary" onclick="planPick('+jsa(id)+','+
        jsa(det.t)+')">Plan it</button>'+
      '<button class="kbtn act" onclick="cookMode('+jsa(id)+')">Cook mode</button>'+
      '<button class="kbtn act" onclick="logCooked('+jsa(id)+','+
        jsa(det.t)+');this.textContent=\'Logged\'">Cooked it</button>'+
      '<button class="kbtn act" id="ksave">'+(saved?"&#9733; Saved":"&#9734; Save")+'</button>'+
      (note?"":'<button class="kbtn act" onclick="editNote('+jsa(id)+')">Add a note</button>')+
      (det.mine?'<button class="kbtn act" onclick="editRecipe('+jsa(id)+')">Edit</button>':"")+
      '</div>'+
      '<div id="knotebox">'+(note?'<div class="knotes"><div class="knotehd">Your notes &middot; '+
        '<button class="klink" onclick="editNote('+jsa(id)+')">edit</button></div>'+
        mdlite(note)+'</div>':"")+'</div>'+
      (det.headnote?'<p class="kdhead">'+mdlite(det.headnote)+'</p>':"")+
      (det.raw&&det.raw.length?'<h3>Ingredients</h3><ul class="kding">'+
        det.raw.map(function(x){
          var ok=covered(normIng(x),have);
          var sw=swapFor(x);
          return '<li'+(ok?' style="opacity:.55"':"")+'>'+esc(x)+
            (ok?' <span class="kfaint">have</span>':"")+
            (sw?'<div class="kswap">hard at the shop &rarr; '+esc(sw)+'</div>':"")+
            '</li>';
        }).join("")+'</ul>':"")+
      (det.method?'<h3>Method</h3><div class="kdmethod">'+mdlite(det.method)+'</div>':"")+
      '</div>';
    document.getElementById("ksave").addEventListener("click",function(){
      var on=!STATE.cooked.saved.some(function(s){return s.id===id;});
      post("save",{id:id,title:det.t,on:on});
      if(on)STATE.cooked.saved.push({id:id,title:det.t});
      else STATE.cooked.saved=STATE.cooked.saved.filter(function(s){return s.id!==id;});
      this.innerHTML=on?"&#9733; Saved":"&#9734; Save";
    });
  });
};
function normIng(raw){
  return raw.toLowerCase().replace(/[\d/½¼¾⅓⅔⅛,().]+/g," ")
    .replace(/\b(cups?|cup|tablespoons?|teaspoons?|pounds?|ounces?|grams?|kg|g|ml|large|small|medium|fresh|chopped|minced|sliced|diced|for serving|to taste|kosher|freshly ground|extra-virgin)\b/g," ")
    .replace(/\s+/g," ").trim();
}
function closeDetail(){
  document.getElementById("kdrawer").classList.remove("open");
  document.body.style.overflow="";
}
document.getElementById("kdclose").addEventListener("click",closeDetail);
document.getElementById("kdrawer").querySelector(".kscrim")
  .addEventListener("click",closeDetail);
function mdlite(md){
  return esc(md)
    .replace(/\*\*(.+?)\*\*/g,"<b>$1</b>")
    .replace(/\*(.+?)\*/g,"<i>$1</i>")
    .replace(/^- (.*)$/gm,"&bull; $1")
    .split(/\n\n+/).map(function(p){return "<p>"+p.replace(/\n/g,"<br>")+"</p>";}).join("");
}

/* --------------------------- notes, and adding --------------------------- */
function sentence(s){
  s=String(s||"something went wrong");
  return s.charAt(0).toUpperCase()+s.slice(1)+(/[.!?]$/.test(s)?"":".");
}
function val(id){var e=document.getElementById(id);return e?e.value.trim():"";}
window.editNote=function(id){
  var box=document.getElementById("knotebox");if(!box)return;
  var title=currentDetail&&currentDetail.id===id?currentDetail.t:(byId[id]||{}).t;
  box.innerHTML='<div class="kform knotes"><label for="kntext">Your notes</label>'+
    '<textarea id="kntext" rows="4" placeholder="What you changed, what to try next time">'+
    esc((STATE.notes||{})[id]||"")+'</textarea>'+
    '<div class="kdacts"><button class="kbtn act primary" id="knsave">Save the note</button>'+
    '<button class="kbtn act" id="kncancel">Cancel</button></div></div>';
  document.getElementById("kntext").focus();
  document.getElementById("kncancel").onclick=function(){openDetail(id);};
  document.getElementById("knsave").onclick=function(){
    this.disabled=true;
    post("note",{id:id,title:title,text:val("kntext")}).then(function(j){
      if(j.notes)STATE.notes=j.notes;
      openDetail(id);
    });
  };
};
function drawerWith(html){
  var d=document.getElementById("kdrawer");
  d.classList.add("open");document.body.style.overflow="hidden";
  document.getElementById("kdcontent").innerHTML=html;
  d.querySelector(".kpanel").scrollTop=0;
}
/* every photo is shrunk here before it travels: a phone's 4 MB picture
   becomes a JPEG of a few hundred KB, and the server only ever gets that */
function shrink(src, done){
  var im=new Image();
  im.onload=function(){
    var k=Math.min(1,1400/Math.max(im.naturalWidth,im.naturalHeight));
    var cv=document.createElement("canvas");
    cv.width=Math.round(im.naturalWidth*k);cv.height=Math.round(im.naturalHeight*k);
    cv.getContext("2d").drawImage(im,0,0,cv.width,cv.height);
    try{done(cv.toDataURL("image/jpeg",0.85));}catch(e){done("");}
  };
  im.onerror=function(){done("");};
  im.src=src;
}
window.addRecipe=function(){
  drawerWith('<div class="kdbody kform"><h2>Add a recipe</h2>'+
    '<p class="kdmeta">From a link or the recipe&rsquo;s text. You check it before it is saved.</p>'+
    '<label for="kaurl">Link to the recipe</label>'+
    '<input id="kaurl" type="url" inputmode="url" autocomplete="off" placeholder="https://">'+
    '<label for="katext">Or paste the recipe</label>'+
    '<textarea id="katext" rows="7"></textarea>'+
    '<div class="kdacts"><button class="kbtn act primary" id="karead">Read it</button>'+
    '<button class="kbtn act" id="kablank">Type it in</button></div>'+
    '<p class="kformmsg" id="kamsg"></p></div>');
  var msg=document.getElementById("kamsg");
  document.getElementById("kablank").onclick=function(){recipeForm({},null);};
  document.getElementById("karead").onclick=function(){
    var url=val("kaurl"),text=val("katext"),b=this;
    if(!url&&!text){msg.className="kformmsg bad";
      msg.textContent="Paste a link or the recipe first.";return;}
    b.disabled=true;msg.className="kformmsg";
    msg.textContent=url?"Reading the page…":"Reading the recipe…";
    fetch("/api/recipe/import",{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify(url?{url:url}:{text:text})})
    .then(function(r){return r.json();})
    .then(function(j){
      if(j.error||!j.draft){b.disabled=false;msg.className="kformmsg bad";
        msg.textContent=sentence(j.error);return;}
      recipeForm(j.draft,null);
    }).catch(function(){b.disabled=false;msg.className="kformmsg bad";
      msg.textContent="The brain did not answer. Is it running?";});
  };
};
window.editRecipe=function(id){
  var det=currentDetail;if(!det||det.id!==id||!det.edit)return;
  recipeForm({title:det.t,kind:det.edit.kind,serves:det.edit.serves,total:det.tot||"",
    headnote:det.headnote,ingredients:det.raw,steps:det.edit.steps,source:det.source,
    note:(STATE.notes||{})[id]||"",photo:det.edit.photo},{id:id,title:det.t});
};
var FORMPHOTO="";
function recipeForm(d, edit){
  var lines=function(a){return (a||[]).join("\n");};
  drawerWith('<div class="kdbody kform">'+
    '<h2>'+(edit?"Edit the recipe":"Check the recipe")+'</h2>'+
    (d.read_by==="model"?'<p class="kdmeta">Read by the model, so check the quantities.</p>':
     d.read_by==="page"?'<p class="kdmeta">Read from the page.</p>':"")+
    '<div class="kphoto" id="kaphoto"><button class="kbtn act" id="kaphotobtn">Add a photo</button>'+
    '<button class="kbtn act" id="kaphotodel" hidden>Remove the photo</button></div>'+
    '<input type="file" id="kafile" accept="image/*" hidden>'+
    '<label for="kat">Title</label><input id="kat" value="'+esc(d.title)+'">'+
    '<div class="krow"><div><label for="kas">Serves</label>'+
    '<input id="kas" inputmode="numeric" value="'+esc(d.serves)+'"></div>'+
    '<div><label for="kam">Total minutes</label>'+
    '<input id="kam" inputmode="numeric" value="'+esc(d.total||"")+'"></div>'+
    '<div><label for="kak">Kind</label>'+
    '<input id="kak" placeholder="Soup, dessert…" value="'+esc(d.kind)+'"></div></div>'+
    '<label for="kai">Ingredients, one per line</label>'+
    '<textarea id="kai" rows="9">'+esc(lines(d.ingredients))+'</textarea>'+
    '<label for="kasteps">Method, one step per line</label>'+
    '<textarea id="kasteps" rows="9">'+esc(lines(d.steps))+'</textarea>'+
    '<label for="kah">About it</label><textarea id="kah" rows="3">'+esc(d.headnote)+'</textarea>'+
    '<label for="kasrc">Link to the original</label>'+
    '<input id="kasrc" type="url" value="'+esc(d.source)+'">'+
    '<label for="kan">Your notes</label><textarea id="kan" rows="3" '+
    'placeholder="What you changed, what to try next time">'+esc(d.note)+'</textarea>'+
    '<div class="kdacts"><button class="kbtn act primary" id="kasave">'+
    (edit?"Save changes":"Add to my recipes")+'</button>'+
    (edit?'<button class="kbtn act" id="kadel">Remove</button>':
          '<button class="kbtn act" id="kaback">Back</button>')+'</div>'+
    '<p class="kformmsg" id="kamsg"></p></div>');
  var box=document.getElementById("kaphoto"),file=document.getElementById("kafile");
  var addb=document.getElementById("kaphotobtn"),delb=document.getElementById("kaphotodel");
  var msg=document.getElementById("kamsg");
  function show(src){
    FORMPHOTO=src||"";
    box.style.backgroundImage=FORMPHOTO?"url('"+encodeURI(FORMPHOTO)+"')":"";
    box.classList.toggle("has",!!FORMPHOTO);
    addb.textContent=FORMPHOTO?"Change the photo":"Add a photo";
    delb.hidden=!FORMPHOTO;
  }
  show("");
  if(/^data:image\//.test(d.photo||""))shrink(d.photo,show);
  else if(/^cooking\/photos\//.test(d.photo||""))show(d.photo);
  addb.onclick=function(){file.click();};
  delb.onclick=function(){show("");};
  file.onchange=function(){
    var f=file.files&&file.files[0];if(!f)return;
    var rd=new FileReader();
    rd.onload=function(){shrink(rd.result,function(j){
      if(j)show(j);else{msg.className="kformmsg bad";
        msg.textContent="That photo could not be read here. Try a JPEG or PNG.";}});};
    rd.readAsDataURL(f);
  };
  var back=document.getElementById("kaback");
  if(back)back.onclick=addRecipe;
  var del=document.getElementById("kadel");
  if(del)del.onclick=function(){
    if(!del.dataset.sure){del.dataset.sure=1;del.textContent="Tap again to remove it";return;}
    post("delrecipe",{id:edit.id}).then(function(j){
      if(j.error){msg.className="kformmsg bad";msg.textContent=sentence(j.error);return;}
      if(j.notes)STATE.notes=j.notes;
      reloadData(null);
    });
  };
  document.getElementById("kasave").onclick=function(){
    var b=this;
    var body={title:val("kat"),serves:val("kas"),total:val("kam"),kind:val("kak"),
      ingredients:val("kai").split("\n"),steps:val("kasteps").split("\n"),
      headnote:val("kah"),source:val("kasrc"),note:val("kan"),photo:FORMPHOTO,
      replace:edit?edit.title:""};
    if(!body.title){msg.className="kformmsg bad";msg.textContent="Give it a title.";return;}
    b.disabled=true;msg.className="kformmsg";msg.textContent="Saving…";
    post("addrecipe",body).then(function(j){
      if(j.error){b.disabled=false;msg.className="kformmsg bad";
        msg.textContent=sentence(j.error);return;}
      if(j.notes)STATE.notes=j.notes;
      reloadData(j.id);
    }).catch(function(){b.disabled=false;msg.className="kformmsg bad";
      msg.textContent="The brain did not answer. Is it running?";});
  };
}
/* the server rebuilt cook-data.json before it answered; take it and show
   the recipe where it now lives */
function reloadData(openId){
  fetch("cook-data.json?v="+Date.now()).then(function(r){return r.json();})
  .then(function(d){
    DATA=d;byId={};d.forEach(function(r){byId[r.id]=r;});
    if(tab()!=="find")location.hash="#find";else render();
    if(openId)openDetail(openId);else closeDetail();
  });
}

/* ----------------------------- cook mode ----------------------------- */
var steps=[],stepAt=0,wakeLock=null;
window.cookMode=function(id){
  var go=function(det){
    var m=det.method||"";
    steps=m.split(/\n(?=\*\*\d+\.\*\*)/).map(function(s){return s.trim();})
      .filter(Boolean);
    if(steps.length<2)steps=m.split(/\n\n+/).filter(Boolean);
    if(!steps.length)steps=["No method text for this one — open your copy of "+det.b+
      (det.pg?", page "+det.pg:"")+"."];
    stepAt=0;
    document.getElementById("kctitle").textContent=det.t;
    document.getElementById("kcookmode").classList.add("open");
    closeDetail();showStep();
    if(navigator.wakeLock)navigator.wakeLock.request("screen")
      .then(function(l){wakeLock=l;}).catch(function(){});
  };
  if(currentDetail&&currentDetail.id===id)go(currentDetail);
  else fetch("/api/cook/recipe?id="+encodeURIComponent(id))
    .then(function(x){return x.json();}).then(go);
};
function showStep(){
  document.getElementById("kstep").innerHTML=mdlite(steps[stepAt]);
  document.getElementById("kcount").textContent=(stepAt+1)+" / "+steps.length;
  document.getElementById("kprev").disabled=stepAt===0;
  document.getElementById("knext").textContent=
    stepAt===steps.length-1?"That's it":"Next \u2192";
}
document.getElementById("kprev").addEventListener("click",function(){
  if(stepAt>0){stepAt--;showStep();}});
document.getElementById("knext").addEventListener("click",function(){
  if(stepAt<steps.length-1){stepAt++;showStep();}
  else document.getElementById("kexit").click();});
document.getElementById("kexit").addEventListener("click",function(){
  document.getElementById("kcookmode").classList.remove("open");
  if(wakeLock){wakeLock.release().catch(function(){});wakeLock=null;}});

/* ------------------------------ shopping ------------------------------ */
function shopView(){
  var s=STATE.shopping;
  var out='<div class="kshop"><h1 class="kh1">Shopping</h1>';
  if(s.built)out+='<p class="klede">Built '+esc(fmtD(s.built))+' from the week of '+
    esc(fmtD(s.week))+'.</p>';
  else out+='<p class="klede">No list yet — plan some dinners, then build it from the Week tab.</p>';
  var open=0,total=0;
  s.sections.forEach(function(sec){sec.items.forEach(function(it){
    total++;if(!it.done)open++;});});
  s.additions.forEach(function(it){total++;if(!it.done)open++;});
  var empty=(total||s.have.length)?'<a href="#" id="kempty">empty the list</a>':"";
  if(total)out+='<p class="kfaint">'+open+' of '+total+' still to get &middot; '+
    '<a href="#" id="kcopy">copy the list</a> &middot; '+empty+'</p>';
  else if(empty)out+='<p class="kfaint">'+empty+'</p>';
  s.sections.forEach(function(sec){
    out+='<div class="kaisle">'+esc(sec.name)+'</div>';
    sec.items.forEach(function(it){out+=shopItem(it,false);});
  });
  out+='<div class="kaisle">Your additions</div>';
  s.additions.forEach(function(it){out+=shopItem(it,true);});
  out+='<div class="kaddrow"><input id="kaddinput" placeholder="Add something...">'+
    '<button class="kbtn act" id="kaddbtn">Add</button></div>';
  if(s.have.length){
    out+='<details class="khave"><summary>Probably have ('+s.have.length+
      ')</summary>';
    s.have.forEach(function(it){out+='<div class="kitem"><span class="kit">'+
      esc(it.text)+'</span> <span class="kidet">'+esc(it.detail)+'</span></div>';});
    out+='</details>';
  }
  out+='</div>';
  setTimeout(bindShop,0);
  return out;
}
function shopItem(it,own){
  var sw=own?null:swapFor(it.text);
  return '<label class="kitem'+(it.done?" done":"")+'">'+
    '<input type="checkbox" data-shop="'+esc(it.text)+'"'+(it.done?" checked":"")+
    '><span class="kit">'+esc(it.text)+
    (sw?'<div class="kswap">not there? &rarr; '+esc(sw)+'</div>':"")+'</span>'+
    (it.detail?' <span class="kidet">'+esc(it.detail)+'</span>':"")+
    (own?'<button class="kmx" data-del="'+esc(it.text)+'">&times;</button>':"")+
    '</label>';
}
function bindShop(){
  document.querySelectorAll("[data-shop]").forEach(function(cb){
    cb.addEventListener("change",function(){
      var text=cb.dataset.shop,done=cb.checked;
      cb.closest(".kitem").classList.toggle("done",done);
      var s=STATE.shopping;
      s.sections.forEach(function(sec){sec.items.forEach(function(it){
        if(it.text===text)it.done=done;});});
      s.additions.forEach(function(it){if(it.text===text)it.done=done;});
      post("shoptick",{text:text,done:done});
    });});
  document.querySelectorAll("[data-del]").forEach(function(b){
    b.addEventListener("click",function(e){
      e.preventDefault();
      var text=b.dataset.del;
      STATE.shopping.additions=STATE.shopping.additions.filter(function(it){
        return it.text!==text;});
      post("shopdel",{text:text});render();
    });});
  var add=function(){
    var inp=document.getElementById("kaddinput");
    var v=inp.value.trim();if(!v)return;
    STATE.shopping.additions.push({text:v,detail:"",done:false});
    post("shopadd",{text:v});inp.value="";render();
    setTimeout(function(){var i=document.getElementById("kaddinput");
      if(i)i.focus();},0);
  };
  var btn=document.getElementById("kaddbtn");
  if(btn)btn.addEventListener("click",add);
  var inp=document.getElementById("kaddinput");
  if(inp)inp.addEventListener("keydown",function(e){if(e.key==="Enter")add();});
  /* Empty: two taps, because the list holds her own additions too and one
     stray tap should not cost them (8 Oct). */
  var em=document.getElementById("kempty");
  if(em)em.addEventListener("click",function(e){
    e.preventDefault();
    if(em.dataset.armed!=="1"){
      em.dataset.armed="1";em.textContent="tap again to empty it";
      setTimeout(function(){em.dataset.armed="";
        em.textContent="empty the list";},3500);
      return;}
    post("shopclear",{}).then(function(r){
      if(r&&r.error){em.dataset.armed="";
        em.textContent="could not empty it, try again";return;}
      STATE.shopping={built:"",week:"",sections:[],additions:[],have:[]};
      render();})
    .catch(function(){em.dataset.armed="";
      em.textContent="could not empty it, try again";});
  });
  var cp=document.getElementById("kcopy");
  if(cp)cp.addEventListener("click",function(e){
    e.preventDefault();
    var lines=[];
    STATE.shopping.sections.forEach(function(sec){
      var open=sec.items.filter(function(it){return !it.done;});
      if(!open.length)return;
      lines.push(sec.name.toUpperCase());
      open.forEach(function(it){lines.push("- "+it.text);});
      lines.push("");
    });
    var adds=STATE.shopping.additions.filter(function(it){return !it.done;});
    if(adds.length){lines.push("ALSO");
      adds.forEach(function(it){lines.push("- "+it.text);});}
    navigator.clipboard.writeText(lines.join("\n")).then(function(){
      cp.textContent="copied";
      setTimeout(function(){cp.textContent="copy the list";},1500);});
  });
}

/* ------------------------------- pantry ------------------------------- */
function pantryView(){
  var p=STATE.pantry;
  var chips=function(group,items){
    return '<div class="kchips">'+items.map(function(i){
      return '<span class="kpc">'+esc(i)+'<button data-pdel="'+esc(i)+
        '" data-pg="'+group+'" title="Remove">&times;</button></span>';
    }).join("")+
    '<span class="kpc"><input id="kp-'+group+'" placeholder="add..." '+
    'style="border:none;background:none;color:var(--ink);width:90px;'+
    'font:inherit;outline:none"></span></div>';
  };
  setTimeout(bindPantry,0);
  return '<h1 class="kh1">Pantry</h1>'+
    '<p class="klede">What the kitchen holds. The matcher and the shopping '+
    'list both read it.</p>'+
    '<div class="kaisle">The kitchen</div>'+
    '<div class="kchips">'+
    '<button class="kchip'+(p.kitchen!=="dorm"?" on":"")+'" data-kit="full">Full kitchen</button>'+
    '<button class="kchip'+(p.kitchen==="dorm"?" on":"")+'" data-kit="dorm">Dorm — two burners, no oven</button>'+
    '</div>'+
    '<p class="kfaint">Dorm mode keeps suggestions and the search to '+
    'stovetop recipes that fit two pans.</p>'+
    '<div class="kaisle">Staples</div>'+chips("staples",p.staples)+
    '<div class="kaisle">Fresh right now '+
    '<button class="kbtn act small" id="kpclear" style="margin-left:8px">Clear'+
    '</button></div>'+
    '<p class="kfaint">New kitchen, new week — clear this when you move houses.</p>'+
    chips("fresh",p.fresh)+tasteBlock()+basketBlock();
}

/* Taste and basket both feed the week planner, and both belong here: this
   is the page for what the kitchen is like, not what is on the calendar. */
function tasteBlock(){
  var t=STATE.taste||{love:[],avoid:[],bored:[]};
  var group=function(key,label){
    return '<div class="kaisle">'+label+'</div><div class="kchips">'+
      (t[key]||[]).map(function(i){
        return '<span class="kpc">'+esc(i)+'<button data-tdel="'+esc(i)+
          '" data-tg="'+key+'" title="Remove">&times;</button></span>';
      }).join("")+
      '<span class="kpc"><input id="kt-'+key+'" placeholder="add..." '+
      'style="border:none;background:none;color:var(--ink);width:150px;'+
      'font:inherit;outline:none"></span></div>';
  };
  setTimeout(bindTaste,0);
  return '<h2 class="kh2" style="margin-top:26px">Taste</h2>'+
    '<p class="kfaint">Whole phrases work: "anything with lemon", "no offal". '+
    'Plan my week reads these before anything it has counted.</p>'+
    group("love","Love")+group("avoid","Avoid")+group("bored","Bored of");
}
function basketBlock(){
  var b=(STATE.basket||[]).slice(0,24);
  if(!b.length){
    return '<h2 class="kh2" style="margin-top:26px">The basket</h2>'+
      '<p class="kfaint">Nothing counted yet. Send a photo of a till receipt '+
      'to the Telegram bot and what you bought lands here, so the planner '+
      'leans toward the things you actually buy.</p>';
  }
  return '<h2 class="kh2" style="margin-top:26px">The basket</h2>'+
    '<p class="kfaint">Counted from your receipts, most bought first.</p>'+
    '<div class="kchips">'+b.map(function(i){
      return '<span class="kpc">'+esc(i.item)+
        ' <span class="kfaint">'+i.n+'</span>'+
        '<button data-bdel="'+esc(i.item)+'" title="Remove">&times;</button>'+
        '</span>';
    }).join("")+'</div>';
}
function bindTaste(){
  ["love","avoid","bored"].forEach(function(g){
    var inp=document.getElementById("kt-"+g);
    if(inp)inp.addEventListener("keydown",function(e){
      if(e.key!=="Enter")return;
      var v=inp.value.trim(); if(!v)return;
      inp.value="";
      STATE.taste[g]=(STATE.taste[g]||[]).concat([v]);
      post("taste",{group:g,item:v});render();
    });});
  document.querySelectorAll("[data-tdel]").forEach(function(b){
    b.addEventListener("click",function(){
      var g=b.dataset.tg,v=b.dataset.tdel;
      STATE.taste[g]=(STATE.taste[g]||[]).filter(function(x){return x!==v;});
      post("taste",{group:g,item:v,remove:true});render();
    });});
  document.querySelectorAll("[data-bdel]").forEach(function(b){
    b.addEventListener("click",function(){
      var v=b.dataset.bdel;
      STATE.basket=(STATE.basket||[]).filter(function(x){return x.item!==v;});
      post("basketdel",{item:v});render();
    });});
}
function bindPantry(){
  document.querySelectorAll("[data-kit]").forEach(function(b){
    b.addEventListener("click",function(){
      var mode=b.dataset.kit;
      STATE.pantry.kitchen=mode;
      find.dorm=mode==="dorm";
      post("kitchen",{mode:mode});render();
    });});
  ["staples","fresh"].forEach(function(g){
    var inp=document.getElementById("kp-"+g);
    if(inp)inp.addEventListener("keydown",function(e){
      if(e.key!=="Enter")return;
      var v=inp.value.trim();if(!v)return;
      STATE.pantry[g].push(v);
      post("pantry",{group:g,item:v});render();
      setTimeout(function(){var i=document.getElementById("kp-"+g);
        if(i)i.focus();},0);
    });});
  document.querySelectorAll("[data-pdel]").forEach(function(b){
    b.addEventListener("click",function(){
      var g=b.dataset.pg,v=b.dataset.pdel;
      STATE.pantry[g]=STATE.pantry[g].filter(function(i){return i!==v;});
      post("pantry",{group:g,item:v,remove:true});render();
    });});
  var clr=document.getElementById("kpclear");
  if(clr)clr.addEventListener("click",function(){
    var items=STATE.pantry.fresh.slice();
    STATE.pantry.fresh=[];
    items.forEach(function(i){post("pantry",{group:"fresh",item:i,remove:true});});
    render();
  });
}

/* ------------------------------- cooked ------------------------------- */
function cookedView(){
  var c=STATE.cooked;
  var out='<h1 class="kh1">Cooked</h1>'+
    '<p class="klede">What actually got made. Star what deserves a repeat '+
    '— saved recipes float up in suggestions.</p>';
  if(!c.log.length)out+='<p class="kfaint">Nothing logged yet. "Cooked it" '+
    'on any recipe lands here.</p>';
  out+='<div class="kshop">';
  c.log.forEach(function(e){
    var saved=c.saved.some(function(s){return (e.id&&s.id===e.id)||s.title===e.title;});
    out+='<div class="kitem"><span class="kfaint" style="min-width:88px">'+
      esc(fmtD(e.date))+'</span><span class="kit"'+(e.id?' style="cursor:pointer" '+
      'onclick="openDetail('+jsa(e.id)+')"':"")+'>'+esc(e.title)+'</span>'+
      (e.note?' <span class="kidet">'+esc(e.note)+'</span>':"")+
      '<button class="kmx" style="font-size:15px" title="Save" '+
      'onclick="toggleSave('+jsa(e.id||"")+','+
      jsa(e.title)+',this)">'+
      (saved?"&#9733;":"&#9734;")+'</button></div>';
  });
  out+='</div>';
  if(c.saved.length){
    out+='<div class="kaisle">Saved</div><div class="kchips">'+
      c.saved.map(function(s){
        return '<span class="kpc"'+(s.id?' style="cursor:pointer" '+
          'onclick="openDetail('+jsa(s.id)+')"':"")+'>&#9733; '+
          esc(s.title)+'</span>';
      }).join("")+'</div>';
  }
  return out;
}
window.toggleSave=function(id,title,el){
  var c=STATE.cooked;
  var on=!c.saved.some(function(s){return (id&&s.id===id)||s.title===title;});
  if(on)c.saved.push({id:id,title:title});
  else c.saved=c.saved.filter(function(s){return !((id&&s.id===id)||s.title===title);});
  post("save",{id:id,title:title,on:on});
  el.innerHTML=on?"&#9733;":"&#9734;";
};

/* -------------------------------- boot -------------------------------- */
fetch("cook-data.json").then(function(r){return r.json();})
.then(function(d){
  DATA=d;
  d.forEach(function(r){byId[r.id]=r;});
  render();
});
render();
</script>
</body></html>
"""


def _finish_template():
    import chrome as CHROME
    global TEMPLATE
    TEMPLATE = TEMPLATE.replace("NAVCSS_HEADERCSS",
                                CHROME.NAV_CSS + CHROME.HEADER_CSS)


_finish_template()


if __name__ == "__main__":
    force = "--reindex" in sys.argv
    if force:
        build_index(force=True)
    out = build()
    print(f"wrote {out} — {len(index())} recipes indexed")

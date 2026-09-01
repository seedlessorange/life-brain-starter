#!/usr/bin/env python3
"""Build a clean copy of the brain to give to a friend.

    python3 brain/tools/share.py            # preview what would go in
    python3 brain/tools/share.py --yes      # build dist/life-brain/ + a zip

The repo itself is NOT shareable: its git history and markdown carry the
owner's whole life. This script builds a fresh brain instead — the code and
the page, with every data file reseeded to its empty format guide — and then
REFUSES to finish if anything personal slips through:

- Files are copied from an explicit ALLOWLIST. Nothing is copied because it
  happened to be in the folder.
- The core markdown files are reseeded the same way reset.py does it: only
  the format guide above the first `## ` heading survives.
- A denylist scan runs over every text file in the finished package — the
  owner's name, git identity and email must appear nowhere. A hit fails the
  whole build and names the file, so drift in any source file gets caught
  here rather than shipped.

The result lands in dist/ (git-ignored). Send the zip; the friend unzips it
anywhere, double-clicks the launcher for their OS, and runs /onboard in
Claude Code for the first fill.
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import zipfile
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
BRAIN = os.path.dirname(HERE)
ROOT = os.path.dirname(BRAIN)
TEMPLATES = os.path.join(HERE, "share-templates")
DIST = os.path.join(ROOT, "dist")
STAGE = os.path.join(DIST, "life-brain")
MARKER = ".share-package"          # proves a dir is ours before we replace it

sys.path.insert(0, HERE)
from reset import preamble  # noqa: E402 — the same reseed rule as a wipe

# ---------------------------------------------------------------------------
# what goes in (allowlist — nothing else is copied)

ROOT_FILES = [
    "README.md",
    # The per-OS walkthroughs and their diagnostics. README.md assumes
    # someone comfortable in a terminal; these assume nothing at all, which
    # is what a friend receiving this folder actually needs. Both ship
    # regardless of platform — the sender rarely knows which one they use,
    # and the wrong one is four unread KB rather than a missing step.
    "START HERE (Windows).md",
    "START HERE (Mac).md",
    # The pretty front door: one self-contained page that pitches the brain
    # and condenses both walkthroughs, for friends who won't open a .md.
    # Also what the owner sends alongside (or ahead of) the zip itself.
    "Start Here.html",
    # The brochure's source. brain/tools/brochure.py ships with every other
    # tool, and without this file it would only ever answer "missing
    # design/brochure.html" — so the friend can re-render the one-pager and
    # pass it on, the same way they can rebuild the package itself.
    os.path.join("design", "brochure.html"),
    "Check My Setup.bat",
    "Check My Setup.command",
    "Open Brain.bat",
    "Open Brain.command",
    "Set Up Mornings (Windows).bat",
    "Set Up Night Shift (Windows).bat",
    ".gitignore",
    ".gitattributes",
]
BRAIN_FILES = [
    "icon.svg",
    "manifest.webmanifest",
    "sessions.html",     # hand-written page; every generated page links to it
    "logo-96.png",
    "logo-180.png",
    "logo-192.png",
    "logo-512.png",
]
# reference/ ships scrubbed: CLAUDE.md routes to these files, so a package
# without them hands the friend a table of dead links. They name her repos,
# so they go through the same name scrub as the command files.
BRAIN_DIRS = ["fonts", "art", "reference"]
# reference/ is framework docs EXCEPT these: data wearing a reference path.
# history.md is the owner's life story, written by /import-history.
# going-out.md is their taste profile — twelve years of listening habits,
# the venues they like, who they contact how. Both ship as generic templates
# instead (share-templates/brain/reference/), because CLAUDE.md routes to
# them and a package without them hands the friend dead links.
REFERENCE_SKIP = {"history.md", "going-out.md"}
# share-templates SHIPS: it is what makes the friend's own onward share
# genericize their CLAUDE.md and commands instead of copying them verbatim.
TOOLS_SKIP = {"__pycache__"}

# Reseeded exactly like reset.py: format guide only, no entries.
SEED_FROM_PREAMBLE = [
    "workstreams.md", "people.md", "habits.md", "goals.md", "inbox.md",
    "next.md", "waiting.md", "questions.md", "decisions.md", "season.md",
]
# Written as fresh stubs — their live preambles could carry personal prose.
SEED_STUBS = {
    "today.md": (
        "---\nupdated: never\n---\n\n"
        "# Today\n\n"
        "Run /today in Claude Code each morning and the plan appears here.\n"
    ),
    "about-me.md": (
        "---\nmaintained-by: you and claude, together\n---\n\n"
        "# About me\n\n"
        "Stable facts about the owner live here: where they are in life,\n"
        "what fills their days, how they work. /onboard writes the first\n"
        "version; corrections land here immediately.\n"
    ),
    "writing-rules.md": (
        "---\nmaintained-by: the owner — edit only at their request\n---\n\n"
        "# Writing rules\n\n"
        "The owner's voice, for anything a third party will read. Fill this\n"
        "in early: how formal, which sign-off, words to avoid. Claude loads\n"
        "it before drafting any email or message.\n"
    ),
    "interests.md": (
        "---\nmaintained-by: you and claude, together\n---\n\n"
        "# Interests\n\n"
        "The life beyond the to-dos: things the owner loves doing when\n"
        "there's slack. /today may surface ONE of these on a light day.\n"
    ),
    "routine.md": (
        "---\nmaintained-by: the owner — edit only at their request\n---\n\n"
        "# The routine\n\n"
        "The shape of your ordinary day, in your own words: when you\n"
        "surface, where the good hours are, what evenings look like.\n"
        "/onboard starts it; the daily plan reads it so plans land in\n"
        "real gaps rather than on paper hours.\n"
    ),
    "countdowns.md": (
        "# Counting down\n\n"
        "Days-until numbers on the Today page. One line each: the thing, a\n"
        "dash, the date. Add or remove lines freely — a date in words\n"
        "(\"mid-September\") works too, and past dates leave the page on\n"
        "their own.\n"
    ),
    "ideas.md": (
        "---\nmaintained-by: you and claude, together\n---\n\n"
        "# The idea shelf\n\n"
        "New ventures land here, not in workstreams.md. The shelf gives each\n"
        "idea a home without letting it tax the projects already running.\n"
        "Nothing here decays, nags, or goes overdue.\n\n"
        "The rules:\n\n"
        "- A new idea gets a dated line and a paragraph, written the day it\n"
        "  strikes.\n"
        "- It becomes a workstream only if you still want it **two weeks\n"
        "  later** and can say what it displaces.\n"
        "- Ideas can die here with dignity: mark them `dead` with one line on\n"
        "  why. A dead idea on the shelf is a decision; a vanished one is a\n"
        "  loose end.\n"
    ),
    "news-glossary.md": (
        "---\nmaintained-by: news.py appends; edits and pruning are yours\n---\n\n"
        "# Glossary\n\n"
        "Terms picked up from the daily briefings, one a day, oldest first.\n"
        "Each learning topic on the News tab leaves one here.\n"
    ),
    # Their own recipes, indexed by the Cook page beside any cookbooks they
    # add. Ships as the format guide only — recipes are data.
    os.path.join("cooking", "my-recipes.md"): (
        "# My recipes\n\n"
        "Yours, not a cookbook's — things you found, were told, or worked\n"
        "out. They sit alongside any extracted cookbooks everywhere on the\n"
        "Cook page: search them, plan them, build a shopping list from them.\n\n"
        "Copy this shape. Only the `## title` and the **Ingredients** list\n"
        "are needed; `Total:` makes it count as quick, `Serves` feeds the\n"
        "shopping quantities, and `<sub>…</sub>` groups it.\n\n"
        "## Egg drop soup\n"
        "<sub>Fast dinners</sub>\n\n"
        "Ninety seconds of cooking, from things that keep in the cupboard.\n\n"
        "Serves 1 · Total: 5 minutes\n\n"
        "**Ingredients**\n\n"
        "- 500 ml chicken stock\n"
        "- 2 eggs\n"
        "- 1 spring onion, sliced\n\n"
        "**Method**\n\n"
        "**1.** Bring the stock to a rolling boil in a saucepan.\n\n"
        "**2.** Beat the eggs and pour them in a thin stream while stirring\n"
        "one way — they cook the moment they hit.\n\n"
        "**3.** Spring onion, and plenty of pepper.\n"
    ),
    "events.md": (
        "---\nupdated: never\nwhere:\n---\n\n"
        "# Out there — what's on, matched to your taste\n\n"
        "The Season tab renders this under the bucket list. `/scout` rewrites\n"
        "it about once a week from the profile in\n"
        "reference/going-out.md — fill that in first, or the shortlist is\n"
        "just listings.\n\n"
        "One line per thing, with its booking page last. The page turns the\n"
        "link into a Book button, and a single date into a one-click \"add to\n"
        "my season\":\n\n"
        "- 2026-10-09 — Who, where (why it suits you) — price — https://...\n"
        "- 2026-10-08..2026-10-11 — A run of dates, venue — https://...\n\n"
        "Sections are yours to name; Club nights / Concerts / Exhibitions /\n"
        "Tech & learning / Fairs & one-offs / Watching for is a good start.\n"
        "Past items drop off the page on their own.\n"
    ),
    "journal-trace.md": (
        "# Yesterday, in one line\n\n"
        "`/journal` leaves one neutral line per day here — the shape of the\n"
        "day (energy, screen vs physical, who was around), never your words\n"
        "or feelings. The morning plan reads this file when the journal\n"
        "itself is private to it. Delete any line you don't want kept.\n"
    ),
}
EMPTY_DIRS = ["queue", "rooms", "daily", "drafts", "files", "transcripts",
              "journal"]

# Files whose generic versions are maintained by hand in share-templates/.
# Anything there replaces the live file at the same relative path.
# (dump.md, today.md, wrap.md carry the owner's life as worked examples;
# CLAUDE.md and config.json are personal top to bottom.)

# Light-touch scrub applied to every copied command file: the owner's first
# name becomes "the owner". Anything heavier belongs in share-templates.
# The bot handle is stored reversed so this file passes its own scan.
NAME_SUBS = [("the owner's", "the owner's"), ("the owner", "the owner"),
             ("@" + "tob_niarb_ycul"[::-1], "@your_brain_bot"),
             # The four places her own houses, apps and school reach a
             # FRIEND'S screen: page placeholders and a hint, written from
             # her life because that is what made them concrete. Comments
             # and docstrings keep their examples; these do not.
             ('--place &quot;Lisbon&quot;', '--place &quot;Lisbon&quot;'),
             ('placeholder="e.g. send the flat details to the agency"',
              'placeholder="e.g. send the flat details to the agency"'),
             ("So I'm doing an MBA at HEC, finishing in December, and I'm "
              "building this app Perch, but honestly the thing on my mind "
              "is&hellip;",
              "So I&rsquo;m finishing a course in December, and there&rsquo;s "
              "an app I keep meaning to work on, but honestly the thing on "
              "my mind is&hellip;"),
             ("'Faverolles, Maman, TapGate\\\\u2026'",
              "'the house, Mum, the app\\\\u2026'")]

TEXT_EXT = {".md", ".py", ".sh", ".ps1", ".bat", ".command", ".json",
            ".txt", ".html", ".svg", ".webmanifest", ".gitignore",
            ".gitattributes", ""}


# ---------------------------------------------------------------------------

def denylist():
    """Markers that must appear NOWHERE in the package: the owner's name,
    git identity and email, plus known-personal words. Derived at run time,
    so the script also works for a friend who later shares onward."""
    marks = set()
    try:
        owner = json.load(open(os.path.join(BRAIN, "config.json"))).get("owner", "")
        owner = re.sub(r"['’]s$", "", owner).strip()
        if len(owner) > 2 and owner.lower() not in ("my", "our", "the"):
            marks.add(owner.lower())
    except Exception:
        pass
    for args in (["git", "config", "user.name"], ["git", "config", "user.email"]):
        try:
            r = subprocess.run(args, cwd=ROOT, capture_output=True, text=True, timeout=10)
            val = r.stdout.strip()
            if val:
                marks.add(val.lower())
                if "@" in val:
                    marks.add(val.split("@")[0].lower())
        except Exception:
            pass
    # Belt and braces for this brain specifically — harmless for anyone
    # else. Stored reversed so this file passes its own scan when shipped.
    marks |= {s[::-1] for s in ("enitnemelc", "elliuop", "elliuopo")}
    return sorted(m for m in marks if len(m) > 2)


def is_text(path):
    return os.path.splitext(path)[1].lower() in TEXT_EXT


# An entry, as opposed to a format guide: a checkbox line or a numbered
# item. preamble() stops at the first `## `, which is right for the files
# whose entries are headings (workstreams, people, decisions) and wrong for
# next.md and questions.md, whose entries are a numbered list and a
# checklist sitting directly under the guide — those shipped live content.
# The guides themselves document their fields as `- **Field:**` lines, so
# only these two shapes may cut.
ENTRY_LINE = re.compile(r"\s*(?:- \[[ xX]\]|\d+\.\s)")
# waiting.md keeps its entries in a table whose header belongs to the guide:
# keep the header and its rule, drop every row under it.
TABLE_RULE = re.compile(r"\s*\|[-\s|:]+\|\s*$")


def seed_head(path):
    """The file's format guide, and nothing the owner wrote under it."""
    head = preamble(path)
    out = []
    for line in head.split("\n"):
        if ENTRY_LINE.match(line):
            break
        out.append(line)
        if TABLE_RULE.match(line):
            break
    kept = "\n".join(out).rstrip().rstrip("-").rstrip()
    return (kept + "\n") if kept else \
        "---\nmaintained-by: you and claude, together\n---\n"


# Prose the FRIEND reads — reference docs and command files — names her
# actual repos, her supermarket and, in one line, a company registration.
# Code comments keep their examples (see NAME_SUBS); documentation does not,
# because a friend reading "installed in Satio, TapGate, ZoomIN" learns the
# author's project list instead of how the thing works.
PROSE_SUBS = [
    ("her app repos (TapGate,\n  Tinytools, ZoomIN, Perch, Satio's AINutritionist and the portfolio —\n  installed in each repo's",
     "every app repo you install it in\n  (via each repo's"),
    ("Satio's is the original; **`~/AINutritionist/brain-kit/` is the portable\ninstaller**",
     "**`brain-kit/` inside the first repo you set up is the portable\ninstaller**"),
    ("The project brain is\ninstalled in Satio, TapGate, Tinytools, ZoomIN and Perch; the recall hook\nadditionally runs in the portfolio repo, which has no project brain of its",
     "Install the project brain in\nwhichever repos you actually work in; the recall hook can also run alone in\na repo that has no project brain of its"),
    ("Added 2026-08-27 after Perch's SIRET approval sat unreported\nfor days while the daily plan kept chasing it.",
     "Added after a project's paperwork was approved and sat unreported for\ndays while the daily plan kept chasing it."),
    ("and Satio does the tracking.", "and a food-tracking app does that job."),
    ("Satio tracks eating; a receipt only stocks the kitchen.",
     "a food tracker handles eating; a receipt only stocks the kitchen."),
    ("Satio stays the food tracker — the Cook page",
     "A food tracker stays the food tracker — the Cook page"),
    ("**Auchan swaps** — `SWAPS` in cook.py maps ~60 American-cookbook\n  ingredients a medium French Auchan won't reliably stock",
     "**Shop swaps** — `SWAPS` in cook.py maps ~60 American-cookbook\n  ingredients a medium French supermarket won't reliably stock"),
    ("She shops\n  at Auchan; extend the dict when she reports a miss",
     "Extend the dict when the owner reports a miss"),
]


def scrub(text):
    for a, b in NAME_SUBS:
        text = text.replace(a, b)
    # A swapped-in "the owner" at a sentence start keeps its capital.
    text = re.sub(r"(?m)^the owner", "The owner", text)
    text = re.sub(r"(?<=\. )the owner", "The owner", text)
    return text


def copy_file(src, dst, do_scrub=False):
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    # Every text file gets the light name scrub, not only the flagged
    # groups — the brand line in a hand-written page leaks a name exactly
    # as well as a command file does.
    do_scrub = True
    if do_scrub and is_text(src):
        # newline="" both ways: the scrub must never rewrite line endings —
        # a .bat or .ps1 that loses its CRLF here ships broken to Windows.
        with open(src, encoding="utf-8", newline="") as f:
            text = f.read()
        text = name_scrub(scrub(text))
        # Documentation the friend reads gets the heavier prose pass too.
        norm = dst.replace("\\", "/")
        if "/brain/reference/" in norm or "/.claude/commands/" in norm:
            for a, b in PROSE_SUBS:
                text = text.replace(a, b)
        with open(dst, "w", encoding="utf-8", newline="") as f:
            f.write(text)
        # A fresh open() drops the source's mode, so a scrubbed .sh or
        # .command arrives non-executable. Nothing invokes those directly
        # today (it is always `zsh script.sh`), but a package where
        # ./setup_night.sh fails is a trap laid for whoever tries it.
        shutil.copymode(src, dst)
    else:
        shutil.copy2(src, dst)


def gather():
    """Every (source, package-relative destination, scrub?) the build makes.
    Template overlays win over live files at the same destination."""
    plan = []
    for name in ROOT_FILES:
        plan.append((os.path.join(ROOT, name), name, False))
    for name in BRAIN_FILES:
        plan.append((os.path.join(BRAIN, name), os.path.join("brain", name), False))
    for d in BRAIN_DIRS:
        base = os.path.join(BRAIN, d)
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = [x for x in dirnames if not x.startswith(".")]
            for fn in sorted(filenames):
                if fn.startswith("."):
                    continue
                if d == "reference" and fn in REFERENCE_SKIP:
                    continue
                src = os.path.join(dirpath, fn)
                rel = os.path.relpath(src, ROOT)
                plan.append((src, rel, d == "reference"))
    for dirpath, dirnames, filenames in os.walk(HERE):
        # .claude survives the dot-dir filter: share-templates carries the
        # generic command files under .claude/commands, and an onward share
        # without them ships the friend's personal commands verbatim.
        dirnames[:] = [x for x in dirnames if x not in TOOLS_SKIP
                       and (x == ".claude" or not x.startswith("."))]
        for fn in sorted(filenames):
            if fn.startswith("."):
                continue
            src = os.path.join(dirpath, fn)
            rel = os.path.relpath(src, ROOT)
            plan.append((src, rel, True))
    cmds = os.path.join(ROOT, ".claude", "commands")
    for fn in sorted(os.listdir(cmds)):
        if fn.endswith(".md"):
            plan.append((os.path.join(cmds, fn),
                         os.path.join(".claude", "commands", fn), True))
    # settings.json switches TodoWrite off, which is worth about a sixth of
    # every run — the friend on the smaller plan needs it more than she does.
    settings = os.path.join(ROOT, ".claude", "settings.json")
    if os.path.exists(settings):
        plan.append((settings, os.path.join(".claude", "settings.json"), False))
    qidx = os.path.join(BRAIN, "queue", "_index.md")
    if os.path.exists(qidx):
        plan.append((qidx, os.path.join("brain", "queue", "_index.md"), True))

    # Overlays: a template at the same relative path replaces the live copy.
    overlays = {}
    for dirpath, dirnames, filenames in os.walk(TEMPLATES):
        for fn in filenames:
            src = os.path.join(dirpath, fn)
            rel = os.path.relpath(src, TEMPLATES)
            overlays[rel] = src
    plan = [(src, rel, sc) for (src, rel, sc) in plan if rel not in overlays]
    for rel, src in sorted(overlays.items()):
        plan.append((src, rel, False))
    return plan


# Her projects, school and shop. Allowed in code comments (they are what
# made the examples concrete); never in the documentation and command files
# a friend actually reads. PROSE_SUBS removes them; this catches the day a
# new sentence adds one back.
# Whole words only: "conversation" contains "satio", and a substring check
# flags every command file that mentions one.
PROSE_MARKS = ["satio", "tapgate", "zoomin", "tinytools", "ainutritionist",
               "auchan", "perch", "siret"]
PROSE_MARK_RX = re.compile(r"\b(" + "|".join(PROSE_MARKS) + r")\b", re.I)
PROSE_DIRS = (os.path.join("brain", "reference"),
              os.path.join(".claude", "commands"))


# Names this check deliberately cannot catch, because they are also ordinary
# words, fonts or colours and would fire on every file: "Mark each in the
# plan", "font: Petrona, Georgia, serif", "brown sugar". A dictionary is no
# help — /usr/share/dict/words lists most common first names too. The trade
# is accepted knowingly: this guard exists for the names nobody would think
# to grep for, and a friend named Mark is a miss worth taking.
#
# Its blind spot, stated plainly: markers come from people.md, so a family
# member who lives only in about-me.md is not covered. Never write a real
# name into a comment — including in this file, which ships.
NAME_SAFE = {
    # kinship — "Maman" in an example reads as "mum", not as a person
    "maman", "papa", "mama", "mamie", "papi", "dad", "mum", "mom",
    # ordinary words that are also names
    "mark", "judge", "brown", "grace", "will", "page", "olive", "hope",
    "rose", "summer", "king", "baker", "cook", "walker", "hunter", "chase",
    "drew", "frank", "rich", "bill", "jack", "joy", "faith", "dawn", "sky",
    "amber", "ruby", "jade", "ivy", "holly", "daisy", "angel", "star",
    # fonts and palette names the pages ship with
    "georgia", "petrona", "archivo", "karla", "jost", "literata",
    # people.md headings that are not personal names — a service, a place,
    # an org, or a nickname that collides with an everyday word
    "house", "cleaners", "ibiza", "mbat", "vanilla", "melody",
}

# Stand-ins for the real people in examples. Deterministic, so a comment
# that mentions the same person twice still reads as one person.
# Wide on purpose: a comment like "Ember and Robin are different people"
# turns to nonsense when both names draw the same stand-in.
STANDINS = ["Robin", "Sam", "Jordan", "Casey", "Emery", "Morgan", "Avery",
            "Quinn", "Rowan", "Harper", "Reese", "Blair", "Emery", "Sage",
            "Devon", "Tatum", "Marlow", "Ellis", "Wren", "Bay", "Indigo",
            "Lennox", "Sloan", "Teagan", "Arden", "Bellamy", "Cody", "Dallas",
            "Ember", "Frankie", "Greer", "Hollis", "Isa", "Jules", "Kit",
            "Lane", "Micah", "Bexley", "Oakley", "Perry", "Remy", "Shay",
            "Tobin", "Harper", "Winter", "Yael", "Zephyr", "Ari", "Bexley"]
_NAME_RX = None
_NAME_MAP = None


def name_scrub(text):
    """Replace everyone from people.md with a stand-in.

    The examples in this codebase are real: comments about matching
    "Brittany" against "Robin", a page placeholder reading "Dad, Sloan,
    Maman…". They are what made the code concrete to write, and they are
    also a list of the owner's family, friends and contractors. Her copy
    keeps them; the package cannot."""
    global _NAME_RX, _NAME_MAP
    if _NAME_MAP is None:
        names = people_markers()
        # A stand-in that is itself someone she knows just moves the leak.
        known = set(names)
        pool = [s for s in STANDINS if s.lower() not in known] or ["Someone"]
        _NAME_MAP = {n: pool[i % len(pool)] for i, n in enumerate(names)}
        _NAME_RX = re.compile(
            r"\b(" + "|".join(re.escape(n) for n in
                              sorted(names, key=len, reverse=True)) + r")\b",
            re.I) if names else False
    if not _NAME_RX:
        return text

    def rep(mo):
        word = mo.group(0)
        stand = _NAME_MAP[word.lower()]
        return stand if word[:1].isupper() else stand.lower()
    return _NAME_RX.sub(rep, text)


def people_markers():
    """Every name in the owner's people.md, as denylist markers.

    The people in someone's life never agreed to appear in a package they
    give away, and a first name in a code comment travels exactly as far as
    one on the page. Deriving this from people.md rather than a hand-written
    list is the point: the list stays current as the file changes, and it
    catches the names nobody thought to search for."""
    try:
        with open(os.path.join(BRAIN, "people.md"), encoding="utf-8") as f:
            text = f.read()
    except OSError:
        return []
    names = set()
    for m in re.finditer(r"(?m)^##\s+(.+?)\s*$", text):
        full = re.sub(r"[*`_]", "", m.group(1)).strip()
        for part in re.split(r"[\s,/&()]+", full):
            part = part.strip(".'’-").lower()
            # 4+ letters, so initials and particles ("Eg", "de") never
            # become markers that match half the English language.
            if len(part) >= 4 and part.isalpha() and part not in NAME_SAFE:
                names.add(part)
    return sorted(names)


def verify_names(stage, names):
    """Fail if anyone from people.md is named anywhere in the package."""
    if not names:
        return []
    rx = re.compile(r"\b(" + "|".join(re.escape(n) for n in names) + r")\b",
                    re.I)
    hits = []
    for dirpath, dirnames, filenames in os.walk(stage):
        dirnames[:] = [d for d in dirnames if d != ".git"]
        for fn in filenames:
            path = os.path.join(dirpath, fn)
            if not is_text(path):
                continue
            try:
                with open(path, encoding="utf-8", errors="ignore") as f:
                    text = f.read()
            except OSError:
                continue
            for m in sorted({m.group(1).lower() for m in rx.finditer(text)}):
                hits.append((os.path.relpath(path, stage), m))
    return hits


def verify_prose(stage):
    """Fail if a project/shop name survives into shipped documentation."""
    hits = []
    for rel_dir in PROSE_DIRS:
        base = os.path.join(stage, rel_dir)
        for dirpath, _, filenames in os.walk(base):
            for fn in filenames:
                path = os.path.join(dirpath, fn)
                if not is_text(path):
                    continue
                try:
                    with open(path, encoding="utf-8", errors="ignore") as f:
                        text = f.read()
                except OSError:
                    continue
                for m in sorted({m.group(1).lower()
                                 for m in PROSE_MARK_RX.finditer(text)}):
                    hits.append((os.path.relpath(path, stage), m))
    return hits


def verify(stage, marks):
    """Fail if any denylist marker appears in any text file of the package."""
    hits = []
    for dirpath, dirnames, filenames in os.walk(stage):
        dirnames[:] = [d for d in dirnames if d != ".git"]
        for fn in filenames:
            path = os.path.join(dirpath, fn)
            if not is_text(path):
                continue
            try:
                with open(path, encoding="utf-8", errors="ignore") as f:
                    low = f.read().lower()
            except OSError:
                continue
            for m in marks:
                if m in low:
                    hits.append((os.path.relpath(path, stage), m))
    return hits


def run_tool(stage, name, timeout=120):
    r = subprocess.run([sys.executable, os.path.join(stage, "brain", "tools", name)],
                       cwd=stage, capture_output=True, text=True, timeout=timeout)
    return r.returncode, (r.stderr or r.stdout or "")[-400:]


def main():
    ap = argparse.ArgumentParser(description="Package a clean brain for a friend.")
    ap.add_argument("--yes", action="store_true",
                    help="actually build (otherwise: preview only)")
    args = ap.parse_args()

    plan = gather()
    marks = denylist()

    if not args.yes:
        print(f"Would package {len(plan)} files into dist/life-brain/:")
        by_top = {}
        for _, rel, _ in plan:
            top = rel.replace("\\", "/").split("/")[0]
            by_top[top] = by_top.get(top, 0) + 1
        for top, n in sorted(by_top.items()):
            print(f"  {top:24} {n} file(s)")
        print(f"\nCore markdown is reseeded empty; the scan then refuses the "
              f"build if any of these appear anywhere: {', '.join(marks)}")
        print("Re-run with --yes to build it.")
        return

    # A previous build is replaced only if it carries our marker — this
    # script never deletes a folder it cannot prove it created.
    if os.path.exists(STAGE):
        if not os.path.exists(os.path.join(STAGE, MARKER)):
            sys.exit(f"{STAGE} exists but wasn't built by this script — "
                     f"move it aside first.")
        shutil.rmtree(STAGE)
    os.makedirs(STAGE, exist_ok=True)
    with open(os.path.join(STAGE, MARKER), "w", encoding="utf-8") as f:
        f.write("built by brain/tools/share.py — safe to delete\n")

    for src, rel, sc in plan:
        if not os.path.exists(src):
            print(f"  (skipping missing {rel})")
            continue
        copy_file(src, os.path.join(STAGE, rel), do_scrub=sc)

    sbrain = os.path.join(STAGE, "brain")
    for name in SEED_FROM_PREAMBLE:
        head = seed_head(os.path.join(BRAIN, name))
        # A fresh brain does not carry the owner's last-edited stamp.
        head = re.sub(r"(?m)^updated:.*\n", "", head)
        with open(os.path.join(sbrain, name), "w", encoding="utf-8") as f:
            f.write(head)
    for name, text in SEED_STUBS.items():
        # A key may name a subfolder (cooking/my-recipes.md); the page build
        # that would otherwise create it runs after this.
        dest = os.path.join(sbrain, name)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with open(dest, "w", encoding="utf-8") as f:
            f.write(text)
    for d in EMPTY_DIRS:
        os.makedirs(os.path.join(sbrain, d), exist_ok=True)

    # Prove the fresh brain builds, using its own tools on its own files.
    print("Building the pages inside the package...")
    for tool in ("sync.py", "build.py", "map.py", "rooms.py"):
        code, tail = run_tool(STAGE, tool)
        if code != 0:
            sys.exit(f"FAILED: {tool} exited {code} in the package:\n{tail}")

    # The build was a smoke test, not content: pages generated on THIS
    # machine embed this machine — absolute paths, the voice-recordings
    # panel scanned from the owner's home folder. Strip every generated
    # artifact; the friend's first launch rebuilds them for their machine
    # (serve.py rebuilds on startup).
    for rel in ("index.html", "map.html", "rooms.html", "proto.html",
                "synced.md", "graph.db", "graph.db.tmp"):
        p = os.path.join(sbrain, rel)
        if os.path.exists(p):
            os.remove(p)
    for fn in os.listdir(sbrain):
        if fn.startswith(".") and os.path.isfile(os.path.join(sbrain, fn)):
            if fn != MARKER:
                os.remove(os.path.join(sbrain, fn))
    pyc = os.path.join(sbrain, "tools", "__pycache__")
    if os.path.isdir(pyc):
        shutil.rmtree(pyc)

    hits = verify(STAGE, marks)
    if hits:
        print("\nREFUSING to finish — personal markers found in the package:")
        for rel, m in hits[:20]:
            print(f"  {rel}  contains  '{m}'")
        print("\nFix the source (or add a share-templates overlay) and re-run.")
        sys.exit(1)

    phits = verify_prose(STAGE)
    if phits:
        print("\nREFUSING to finish — a project or shop name reached the "
              "documentation a friend reads:")
        for rel, m in phits[:20]:
            print(f"  {rel}  contains  '{m}'")
        print("\nAdd the sentence to PROSE_SUBS in share.py and re-run.")
        sys.exit(1)

    nhits = verify_names(STAGE, people_markers())
    if nhits:
        print("\nREFUSING to finish — someone from your people.md is named "
              "in the package:")
        for rel, m in nhits[:20]:
            print(f"  {rel}  names  '{m}'")
        print("\nThey did not agree to be in a package you give away. Rename "
              "the example at the source (or add the word to NAME_SAFE if it "
              "is not really a person).")
        sys.exit(1)

    # A fresh history, so day one has an undo and none of the owner's past.
    try:
        subprocess.run(["git", "init", "-q"], cwd=STAGE, capture_output=True, timeout=20)
        subprocess.run(["git", "add", "-A"], cwd=STAGE, capture_output=True, timeout=20)
        subprocess.run(["git", "-c", "user.name=life-brain",
                        "-c", "user.email=brain@localhost",
                        "commit", "-q", "-m", "a fresh brain"],
                       cwd=STAGE, capture_output=True, timeout=20)
    except Exception:
        print("  (git not available — the friend's brain starts without history)")

    zpath = os.path.join(DIST, f"life-brain-{date.today().isoformat()}.zip")
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        for dirpath, dirnames, filenames in os.walk(STAGE):
            for fn in filenames:
                full = os.path.join(dirpath, fn)
                z.write(full, os.path.join("life-brain",
                                           os.path.relpath(full, STAGE)))

    print(f"\nDone. The scan found none of: {', '.join(marks)}")
    print(f"  folder: {os.path.relpath(STAGE, ROOT)}/")
    print(f"  zip:    {os.path.relpath(zpath, ROOT)}")
    print("\nSend the zip. The friend unzips it, double-clicks the launcher")
    print("for their OS, and runs /onboard in Claude Code for the first fill.")


if __name__ == "__main__":
    main()

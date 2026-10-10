"""Context packs: the briefing a task- or person-scoped conversation opens
with, assembled mechanically — no model call, no cost.

The point is scope. A conversation about "Plan real time with Maman" needs
the task, its workstream, and Maman's people entry — not the whole brain.
Every turn of a conversation resends its context, so what goes in here is
paid for on every exchange: the pack is a page, and it stays a page. The
caps below are the feature, not a limit to raise.

The pack travels inside the first turn's prompt (sessions.py prepends it,
marked as data, not instructions) and never appears in the transcript.

The same file holds what every model call carries (the smarter-brain plan,
items 1, 2 and 4): card() is a short description of her, rules_for() the
slice of her rules one kind of task needs, rulings_for() her decisions on
one front, and for_call() the three together, capped. llm.py prepends it to
the small calls, recall_hook.py to her app repos' sessions.
"""

import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BRAIN = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import model  # noqa: E402

BLOCK_CAP = 2500      # chars any one verbatim block may bring
PACK_CAP = 9000       # chars the whole pack may reach


def _read(name):
    try:
        with open(os.path.join(BRAIN, name), encoding="utf-8") as f:
            return f.read()
    except OSError:
        return ""


def _section(text, heading):
    """One `## Heading` block, verbatim, capped."""
    m = re.search(r"(?ms)^## +" + re.escape(heading) + r"\s*?$(.*?)(?=^## |\Z)",
                  text)
    if not m:
        return ""
    return ("## " + heading + m.group(1)).strip()[:BLOCK_CAP]


def _people_headings():
    return re.findall(r"(?m)^## +(.+?)\s*$", _read("people.md"))


def _mentioned_people(texts):
    """Which people.md entries the given texts name. Full names match on any
    word boundary; a first name alone also counts when it is 3+ letters (so
    'Maman' finds '## Maman', 'Perry' finds '## Perry Eg Lisbon', but 'Al'
    can't hit half the file)."""
    hay = " " + " ".join(t or "" for t in texts) + " "
    found = []
    for full in _people_headings():
        first = full.split()[0] if full.split() else ""
        for probe in {full, first}:
            if len(probe) >= 3 and re.search(
                    r"(?i)(?<![\w])" + re.escape(probe) + r"(?![\w])", hay):
                found.append(full)
                break
    return found


def _norm(s):
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


# ------------------------------------------------------------- the card
#
# One short description of her that every model call can carry, from the
# voice to the job form filler. It is generated on every call from
# about-me.md and config.json `now`, never stored, so it cannot drift from
# the file she corrects. Plain code picks the lines: no model, no cost.
#
# What it may say is decided by section, not by judgement. Only the
# sections below are read; Family, Extended family, Health, Properties,
# the shape of things (it carries Mum's illness and the visa question) and
# the rest never reach a card. Inside the allowed sections a sentence that
# names a parent, a sister, health, money or dating is dropped as well, so a
# line added there later cannot leak by accident.

CARD_CAP = 1200       # chars, the whole full card
VOICE_CAP = 700       # chars, the voice card for text other people read
RULINGS_CAP = 1200    # chars, her rulings on one front
FOR_CALL_CAP = 3600   # chars, card plus rules for one call

# (heading in about-me.md, label on the card, chars it may use, newest last)
CARD_SECTIONS = (
    ("Who you are", "Who", 185, False),
    ("Education", "Education", 100, True),
    ("Languages", "Languages", 130, False),
    ("Her projects", "Projects", 190, False),
    ("How she works, honestly", "How she works", 335, False),
    ("Tone and style", "Style", 185, False),
)
VOICE_SECTIONS = (
    ("Languages", "Languages", 260, False),
    ("Tone and style", "Style", 200, False),
)

_SENSITIVE = re.compile(
    r"(?i)\b(mum|mom|maman|dad|papa|mother|father|parents?|sisters?|"
    r"brothers?|ALS|health|illness|diagnos\w*|weight|insulin|panic|anxiety|"
    r"vasovagal|medical|clinical|doctor|money|financ\w*|salary|debt|loan|"
    r"SCI|propert\w*|dating|boyfriend|girlfriend|married|kids|drink\w*|"
    r"visa)\b|€")
# Facts for one kind of errand (shopping, the car): about-me.md keeps them
# for the calls that need them, the card has no room.
_ERRAND = re.compile(r"^(Sizes|Drives)\b")


def _body(text, heading):
    """One `## Heading` block's body, uncapped, without the heading."""
    m = re.search(r"(?ms)^## +" + re.escape(heading) + r"[^\n]*$(.*?)(?=^## |\Z)",
                  text)
    return m.group(1).strip() if m else ""


def _bullets(body):
    """Top-level `- ` bullets, continuation lines folded in."""
    out, cur = [], None
    for ln in body.splitlines():
        if re.match(r"^[-*] ", ln):
            if cur:
                out.append(cur)
            cur = ln[2:].strip()
        elif cur is not None and ln.startswith(" ") and ln.strip():
            cur += " " + ln.strip()
        else:
            if cur:
                out.append(cur)
            cur = None
    if cur:
        out.append(cur)
    return out


def _plain(s):
    """Markdown and em dashes out, dated asides out: a card reads as plain
    prose, and a model shown em dashes writes them back."""
    s = re.sub(r"^\*\*([^*]+)\*\*\s*[—–]\s*", r"\1: ", s)
    s = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", s)
    s = s.replace("**", "").replace("`", "")
    s = re.sub(r"(?<!\w)\*([^*\n]+)\*(?!\w)", r"\1", s)
    s = re.sub(r"\s*\([^()]*\d[^()]*\)", "", s)
    s = re.sub(r"(?<=\d)–(?=\d)", "-", s)          # 3–4 stays a range
    s = re.sub(r"\s*[—–]\s*", ", ", s)
    return re.sub(r"\s+", " ", s).strip()


def _sentences(s, upto=0):
    """The first sentence, or as many whole sentences as fit in `upto`
    characters (always at least one)."""
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z\"“])", s)
    out = parts[0]
    for p in parts[1:]:
        if len(out) + 1 + len(p) > upto:
            break
        out += " " + p
    if out.count('"') % 2:
        out += '"'
    return out


def _first_sentence(s):
    return _sentences(s)


def _fill(bullets, budget):
    """First sentences, in order, while they fit; one that does not fit is
    skipped so a shorter one after it still gets its place."""
    # Her own bold marks what she stressed (her name, her aphantasia), so a
    # bullet carrying bold goes ahead of the unmarked ones.
    bullets = ([b for b in bullets if "**" in b]
               + [b for b in bullets if "**" not in b])
    out, used = [], 0
    for b in bullets:
        s = _first_sentence(_plain(b))
        if not s or _SENSITIVE.search(s) or _ERRAND.match(s):
            continue
        if used + len(s) + 1 > budget:
            continue
        out.append(s)
        used += len(s) + 1
    return " ".join(out)


def _now_line():
    try:
        now = (model.load_config() or {}).get("now") or {}
    except Exception:
        now = {}
    from datetime import date as _d
    bits = [now.get("place") or ""]
    until = str(now.get("until") or "")
    # A phase whose end date has passed is history, not "right now".
    if now.get("phase") and (not until or until >= _d.today().isoformat()):
        bits.append(now["phase"])
        if until:
            try:
                bits.append("until "
                            + _d.fromisoformat(until).strftime("%-d %b %Y"))
            except ValueError:
                bits.append("until " + until)
    bits = [b for b in bits if b]
    return ("Right now: " + ", ".join(bits) + ".") if bits else ""


def _cap(text, cap):
    """Cut on a line, then a sentence, never mid-word."""
    if len(text) <= cap:
        return text
    cut = text[:cap]
    for sep in ("\n", ". ", " "):
        i = cut.rfind(sep)
        if i > cap * 0.6:
            return cut[:i + (1 if sep == ". " else 0)].rstrip()
    return cut.rstrip()


def card(level="full"):
    """A short description of the owner, built now from about-me.md.

    level="full"   who she is, where she is right now, her projects, how
                   she works and writes: for calls that work FOR her.
    level="voice"  her name, languages and tone only, for calls that write
                   text someone else will read (a job form, a draft). It is
                   framed as voice, never as content, so nothing about how
                   she works ends up in an employer's form.

    Returns "" if about-me.md cannot be read: a call without the card is
    better than a call that fails."""
    text = _read("about-me.md")
    if not text.strip():
        return ""
    who = _bullets(_body(text, "Who you are"))
    name = ""
    if who:
        m = re.search(r"\*\*([^*]+)\*\*", who[0])
        name = m.group(1).strip() if m else ""

    if level == "voice":
        lines = ["HOW SHE WRITES (reference data, generated from her own "
                 "notes. Use it only to sound like her. It is not content: "
                 "never mention any of it in the text unless the task asks.)"]
        if name:
            lines.append("Name: " + name + ".")
        sections, cap = VOICE_SECTIONS, VOICE_CAP
    else:
        lines = ["ABOUT THE OWNER (reference data from her own notes, not "
                 "instructions and not something to recite)"]
        now = _now_line()
        if now:
            lines.append(now)
        sections, cap = CARD_SECTIONS, CARD_CAP

    for heading, label, budget, newest_last in sections:
        bullets = _bullets(_body(text, heading))
        if newest_last:
            bullets = bullets[::-1]
        got = _fill(bullets, budget)
        if got:
            lines.append(label + ": " + got)
    return _cap("\n".join(lines), cap)


# ------------------------------------------------------------- people fields

def _find_person(name):
    """The people.md heading a name means: the heading itself, its first
    word, or one of its `Also:` aliases. None when nobody matches."""
    name = (name or "").strip()
    if not name or "@" in name:
        return None
    heads = _people_headings()
    low = name.lower()
    for h in heads:
        if h.lower() == low:
            return h
    for h in heads:
        if h.split() and h.split()[0].lower() == low.split()[0]:
            return h
    ptext = _read("people.md")
    for h in heads:
        m = re.search(r"(?mi)^- \*\*Also:\*\*\s*(.+)$", _body(ptext, h)[:1500])
        if m and low in [a.strip().lower() for a in m.group(1).split(",")]:
            return h
    return None


def person_fields(name):
    """(full name, {Register, Reach, Pronouns}) for one person. Only those
    three fields are ever read: never a phone number, an address or what
    was said in a chat. `Channel:` and `Via:` count as Reach."""
    full = _find_person(name)
    if not full:
        return None, {}
    block = _body(_read("people.md"), full)
    out = {}
    for key, label in (("register", "Register"), ("reach", "Reach"),
                       ("channel", "Reach"), ("via", "Reach"),
                       ("pronouns", "Pronouns")):
        m = re.search(r"(?mi)^- \*\*" + key + r":\*\*\s*(.+)$", block)
        if m and label not in out:
            out[label] = _plain(m.group(1))[:200]
    return full, out


def person_rules(name):
    """The lines a draft to this person needs, or "" for nobody known."""
    full, f = person_fields(name)
    if not full:
        return ""
    lines = ["WRITING TO " + full.upper() + " (from her people file)"]
    if f.get("Register"):
        lines.append("Register, how to sound with them: " + f["Register"])
    if f.get("Reach"):
        lines.append("Reach, how she contacts them: " + f["Reach"])
    lines.append("Pronouns: " + (f.get("Pronouns") or
                                 "not on file, so they/them, never a guess "
                                 "from the name") + ".")
    return "\n".join(lines)


# ------------------------------------------------------------- rulings
#
# Her decisions are written down in decisions.md and, until now, never read
# before advice. rulings_for() hands a call the few that touch its front,
# matched mechanically on the front's names, so a ruled-out option does not
# come back into a plan. No model reads the file.

_DECISION = re.compile(r"(?m)^#{2,3} +(\d{4}-\d{2}-\d{2})\s*[—–-]+\s*(.+?)\s*$")
# Words in workstream names too common to tell one front from another.
_GENERIC = {
    "help", "tasks", "decide", "renovations", "school", "class", "personal",
    "upcoming", "family", "brain", "health", "finances", "portfolio",
    "entrepreneurship", "urgent", "respond", "call", "being", "there",
    "lead", "smarter", "context", "events", "admin", "direction", "dossier",
    "project", "site", "finish", "host", "habits", "big", "questions",
    "where", "live", "after", "with", "from", "january", "february",
    "march", "april", "june", "july", "august", "september", "october",
    "november", "december", "monday", "tuesday", "wednesday", "thursday",
    "friday", "saturday", "sunday", "the",
}


def _decisions():
    """[(date, title, body)] in file order (append-only, so oldest first)."""
    text = _read("decisions.md")
    heads = list(_DECISION.finditer(text))
    out = []
    for i, m in enumerate(heads):
        end = heads[i + 1].start() if i + 1 < len(heads) else len(text)
        out.append((m.group(1), m.group(2), text[m.end():end].strip()))
    return out


def _front_names(front):
    """The names a front goes by: the workstream, the room it sits in and
    the folder that room watches, whichever of those `front` was given."""
    front = (front or "").strip()
    names = {front} if front else set()
    try:
        cfg = model.load_config()
        rooms = model.all_rooms(cfg)
    except Exception:
        rooms = []
    low = front.lower()
    for room in rooms:
        ws = [w.strip() for w in (room.get("ws") or [])]
        if low in [w.lower() for w in ws] or low == (room.get("name") or "").lower():
            names.add(room.get("name") or "")
            names.update(ws)
            if room.get("source"):
                src = re.sub(r"\s*\(.*?\)", "", room["source"]).strip()
                names.add(src)
                _SOURCES.add(src)
    return {n for n in names if n}


_SOURCES = set()      # the folder names _front_names() has seen


def _other_front_words(names):
    """Every word in the names of the OTHER fronts: a word this front shares
    with another one ("Dad", "Renovations") cannot tell them apart."""
    low = {n.lower() for n in names}
    words = set()
    try:
        cfg = model.load_config()
        groups = [[w.get("name") or ""] for w in model.load(cfg=cfg)]
        for room in model.all_rooms(cfg):
            groups.append([room.get("name") or "", room.get("source") or ""]
                          + list(room.get("ws") or []))
    except Exception:
        groups = []
    for g in groups:
        if low & {n.strip().lower() for n in g}:
            continue                                    # this front itself
        words.update(w.lower() for n in g
                     for w in re.findall(r"[A-Za-z][A-Za-z0-9]*", n))
    return words


def _probes(front):
    """(phrases, words) a decision must contain to be about this front.
    A whole multi-word name matches in any case; a single word must be
    capitalised where it appears, as in graph.py, and must be either a
    front's whole one-word name (an app called Lumen) or a word no other
    front uses (the village a house sits in)."""
    names = _front_names(front)
    others = _other_front_words(names)
    phrases, words = set(), set()
    for n in names:
        n = n.strip()
        if " " in n:
            phrases.add(n)
            # A folder's name ("School") counts whole, never word by word:
            # "Paris" alone is a city, not a front.
            if n in _SOURCES:
                continue
        toks = [t.split(".")[0] for t in
                re.findall(r"[A-Za-z][A-Za-z0-9]*(?:\.[a-z]+)?", n)]
        for w in toks:
            if (len(w) < 3 or not any(c.isupper() for c in w)
                    or w.lower() in _GENERIC):
                continue
            if len(toks) == 1 or w.lower() not in others:
                words.add(w)
    return phrases, words


def _mention_at(text, phrases, words):
    """Where the text first names the front, or -1."""
    at = []
    for p in phrases:
        m = re.search(r"(?i)(?<!\w)" + re.escape(p) + r"(?!\w)", text)
        if m:
            at.append(m.start())
    for w in words:
        for m in re.finditer(r"(?i)(?<!\w)" + re.escape(w) + r"(?!\w)", text):
            if m.group(0)[:1].isupper():          # a name is capitalised
                at.append(m.start())
                break
    return min(at) if at else -1


def _mentions(text, phrases, words):
    return _mention_at(text, phrases, words) >= 0


def _excerpt(body, phrases, words, strong):
    """The part of an entry worth its characters. An entry about the front
    starts at its "Decided" line when it has one (the opening is usually
    the backstory); an entry that only mentions the front starts at the
    sentence that does."""
    text = _plain(re.sub(r"(?m)^#+\s*", "", body))
    if strong:
        m = re.search(r"\b(Decided|Decisions?)\b", text)
        return text[m.start():] if m else text
    at = _mention_at(text, phrases, words)
    if at <= 0:
        return text
    start = max(text.rfind(". ", 0, at), text.rfind(": ", 0, at))
    return text[start + 2:] if start >= 0 else text


def rulings_for(front, limit=3, cap=RULINGS_CAP):
    """Her most recent decisions on one front, newest first: an entry whose
    heading (or a `Front:` line) names the front comes before one that only
    mentions it in passing. "" when none match."""
    if not front:
        return ""
    phrases, words = _probes(front)
    if not phrases and not words:
        return ""
    strong, weak = [], []
    for d, title, body in reversed(_decisions()):
        tag = re.search(r"(?mi)^-?\s*\**Front:\**\s*(.+)$", body)
        if _mentions(title, phrases, words) or (
                tag and _mentions(tag.group(1), phrases, words)):
            strong.append((d, title, body))
        elif _mentions(body, phrases, words):
            weak.append((d, title, body))
    picked = (strong + weak)[:limit]
    if not picked:
        return ""
    head = ("HER RULINGS ON THIS FRONT (from her decisions file, newest "
            "first. She decided these: do not bring back what they rule out.)")
    each = max(160, (cap - len(head)) // len(picked) - 4)
    lines = [head]
    for d, title, body in picked:
        line = "- " + d + ", " + _plain(title) + ": " + _excerpt(
            body, phrases, words, (d, title, body) in strong)
        lines.append(_cap(line, each))
    return _cap("\n".join(lines), cap)


# ------------------------------------------------------------- rules by task

LIMIT_LINE = ("If the task names a limit in words, characters, slides or "
              "minutes, land at or under it and count.")
_CAPACITY = re.compile(
    r"(?i)classes a day|midnight|told everything|volleyball on|"
    r"productive procrastination|accountable")


def _style_short():
    t = _read("writing-style-short.md")
    return re.sub(r"(?s)^---.*?---\s*", "", t).strip()


def _capacity():
    """Her real capacity, in her words: the campus-day lines about evenings
    and load when she is in a term, and the row of her year for where she
    is now."""
    text = _read("about-me.md")
    try:
        now = (model.load_config() or {}).get("now") or {}
    except Exception:
        now = {}
    lines = []
    place = (now.get("place") or "").strip()
    if place:
        for row in _body(text, "The nomadic year").splitlines():
            cells = [c.strip() for c in row.strip().strip("|").split("|")]
            if len(cells) == 3 and place.lower() in cells[1].lower():
                lines.append(f"In {cells[1]}: {cells[2]}.")
                break
    pool = _bullets(_body(text, "How she works, honestly"))
    if "term" in (now.get("phase") or "").lower():
        pool = _bullets(_body(text, "The campus day")) + pool
    for b in pool:
        s = _plain(b)
        if _CAPACITY.search(s) and not _SENSITIVE.search(s):
            lines.append(_sentences(s, 220))
    if not lines:
        return ""
    return "HER REAL CAPACITY (her own words)\n" + "\n".join(
        "- " + ln for ln in lines[:6])


def rules_for(kind, person=None, front=None):
    """The slice of her rules one kind of call needs, or "".

    "other"  text someone else will read: the short writing style, the
             exact-limits rule, and the person's register, reach and
             pronouns when a person is named
    "plan"   her real capacity, plus her rulings on the front
    "her"    nothing beyond the card
    "code"   nothing
    """
    parts = []
    if kind == "other":
        style = _style_short()
        if style:
            parts.append("HER RULES FOR TEXT SOMEONE ELSE WILL READ (follow "
                         "them)\n" + style + "\nWhere the task asks for the "
                         "text alone, return only the text, with no note "
                         "around it.")
        parts.append(LIMIT_LINE)
        if person:
            pr = person_rules(person)
            if pr:
                parts.append(pr)
    elif kind == "plan":
        parts.append(_capacity())
        if front:
            parts.append(rulings_for(front))
    return "\n\n".join(p for p in parts if p)


def for_call(kind, person=None, front=None, cap=FOR_CALL_CAP):
    """Card plus rules for one model call, capped. A call writing for
    someone else gets the voice card; every other kind gets the full one."""
    level = "voice" if kind == "other" else "full"
    out = "\n\n".join(p for p in (card(level),
                                  rules_for(kind, person=person, front=front))
                      if p)
    return _cap(out, cap)


# ------------------------------------------------------------- the profile
#
# The block she pastes into claude.ai (Settings, Profile, personal
# preferences) and into ChatGPT's custom instructions. Until 7 Oct 2026 it
# was written by hand in reference/claude-audit.md, and it drifted from her
# notes. Now it has three parts:
# - her approved words from the 28 Sep audit: the persona, how she briefs,
#   the tone and what works (JARVIS_FIXED);
# - the facts, taken from card() so they say what about-me.md says;
# - what she keeps correcting (JARVIS_CORRECTING), from the audit. A re-run
#   of /claude-audit proposes a change to it, made only with her yes.
# Each text is held to 1,500 characters, counted here. evals/jarvis.json
# keeps both texts and their sha; the page asks her to paste again when the
# sha moves away from the one she last pasted.

JARVIS_CAP = 1500
JARVIS_FILE = os.path.join(BRAIN, "evals", "jarvis.json")
# Card lines that may go in, most important first. "Right now" stays out:
# it changes with every move, and a profile that asks to be re-pasted at
# every move gets ignored.
JARVIS_FACTS = ("Who", "Education", "Projects", "Languages", "How she works",
                "Style")
# The order the parts are filled in when 1,500 characters cannot hold them
# all. The fixed parts always go in; these are added while they fit. Each is
# (card label or "voice", how much): "each" adds the line's sentences one by
# one, 1 only its first sentence, "whole" the line or nothing (half of
# Languages would say she speaks English only).
_JARVIS_FILL = (("Who", "each"), ("Education", "each"), ("Projects", 1),
                ("voice", "whole"), ("Languages", "whole"),
                ("Projects", "each"), ("How she works", "each"),
                ("Style", "each"))

JARVIS_FIXED = {
    "claude": {
        "persona": (
            "You are my chief of staff: a former strategy consultant who "
            "later shipped software as a staff engineer, and who edits like "
            "an admissions-essay coach. You pick one recommendation and "
            "defend it with my real facts. You finish the whole job and "
            "check it against the real thing before you call it done."),
        "facts": "About me:",
        "brief": (
            "I keep patterns, not specifics, so you hold the specifics. I "
            "type fast and leave typos; read through them. I usually send "
            "one line and a paste. Work from the paste, and stop to ask only "
            "when a constraint I care about is missing."),
        "tone": ("Be direct and a little dry. Keep it short for me, and "
                 "finished for anyone else."),
        "correcting": "What I keep correcting:",
        "works": (
            "What works: one pick with the reason, real options side by side "
            "when I have to choose, feedback split per item so I can act "
            "line by line."),
        "voice": ('How I sound: "Reading this is taking 1 minute 15 and it '
                  'should be closer to 1 minute."'),
        "close": ("Before every answer, silently ask: what would {name} "
                  "correct here?"),
    },
    "chatgpt": {
        "persona": (
            "Act as my chief of staff: an ex-strategy consultant turned staff "
            "engineer who edits like an admissions-essay coach. Pick one "
            "recommendation and defend it with my real facts. Finish the "
            "whole job and check it before calling it done."),
        "facts": "Me:",
        "brief": (
            "I keep patterns, not specifics; you hold the specifics. I type "
            "fast with typos; read through them. I often send one line plus "
            "a paste: work from the paste, ask only if a constraint I care "
            "about is missing."),
        "tone": ("Tone: direct and a little dry, without emoji or "
                 "cheerleading. Short for me, finished for anyone else."),
        "correcting": "What I keep correcting:",
        "works": ("What works: one pick with the reason, real options side "
                  "by side when I must choose, feedback per item."),
        "voice": ('My voice: "Reading this is taking 1 minute 15 and it '
                  'should be closer to 1 minute."'),
        "close": ("Before answering, silently ask: what would {name} correct "
                  "here?"),
    },
}
JARVIS_CORRECTING = {
    "claude": (
        "Text other people will read must not sound like AI: no em dashes, "
        "no \"not X but Y\", no triplets, no tidy closing line.",
        "Limits are exact. Count words, characters, slides or minutes, and "
        "tell me what you cut.",
        "My \"no\" and \"don't\" are hard filters, not preferences.",
        "Never invent a fact about my life. Leave a marked blank.",
        "Don't say fixed until you've checked it against what I reported.",
    ),
    "chatgpt": (
        "Text for other people must not sound like AI: no em dashes, no "
        "\"not X but Y\", no lists of three, no tidy closing line.",
        "Limits are exact. Count words, characters, slides or minutes, and "
        "say what you cut.",
        "My \"no\" and \"don't\" are hard filters.",
        "Never invent a fact about my life. Leave a marked blank.",
        "Don't claim something works until you've checked it against what "
        "I reported.",
    ),
}


def _card_lines():
    """{label: text} from the full card, so the profile carries the card's
    facts word for word."""
    out = {}
    for ln in card("full").splitlines()[1:]:
        label, sep, text = ln.partition(": ")
        if sep and text:
            out[label] = text
    return out


def _jarvis_render(site, name, chosen):
    """One profile text from the fixed parts plus the chosen optional ones.
    `chosen` maps a card label to its kept sentences, and "voice" to True."""
    f = JARVIS_FIXED[site]
    facts = []
    for label in JARVIS_FACTS:
        if chosen.get(label):
            body = " ".join(chosen[label])
            facts.append(body if label == "Who" else label + ": " + body)
    parts = [f["persona"]]
    if facts:
        parts.append(f["facts"] + "\n" + "\n".join(facts))
    parts += [f["brief"], f["tone"],
              f["correcting"] + "\n" + "\n".join(
                  "- " + c for c in JARVIS_CORRECTING[site]),
              f["works"]]
    if chosen.get("voice"):
        parts.append(f["voice"])
    parts.append(f["close"].format(name=name))
    return "\n\n".join(parts)


def jarvis():
    """The paste-ready profile for claude.ai and for ChatGPT:
    {"claude": str, "chatgpt": str}, each at most JARVIS_CAP characters.
    The facts come from card(), filled sentence by sentence in _JARVIS_FILL
    order while they fit, so a longer about-me shortens the facts instead
    of breaking the limit."""
    lines = _card_lines()
    # The card's Who line glosses her nickname and her aphantasia in
    # brackets; the profile has no room for asides.
    if lines.get("Who"):
        lines["Who"] = re.sub(r"\s*\([^()]*\)", "", lines["Who"])
    who = lines.get("Who", "")
    name = who.split(" ")[0].strip(",.") if who else ""
    name = name or "I"
    out = {}
    for site in JARVIS_FIXED:
        chosen, used = {}, {}
        for label, how in _JARVIS_FILL:
            if label == "voice":
                trial = dict(chosen, voice=True)
                if len(_jarvis_render(site, name, trial)) <= JARVIS_CAP:
                    chosen = trial
                continue
            sents = _sentences_all(lines.get(label, ""))
            todo = [i for i in range(len(sents))
                    if i not in used.get(label, set())]
            if how == "whole":
                groups = [todo] if todo else []
            elif how == 1:
                groups = [[i] for i in todo[:1]]
            else:
                groups = [[i] for i in todo]
            for g in groups:
                trial = dict(chosen)
                have = set(used.get(label, set())) | set(g)
                trial[label] = [sents[i] for i in sorted(have)]
                if len(_jarvis_render(site, name, trial)) <= JARVIS_CAP:
                    chosen = trial
                    used[label] = have
        text = _jarvis_render(site, name, chosen)
        assert len(text) <= JARVIS_CAP, (site, len(text))
        assert "—" not in text and "–" not in text, site
        out[site] = text
    return out


def _sentences_all(s):
    """Every sentence of a card line, in order."""
    s = (s or "").strip()
    return [p for p in re.split(r"(?<=[.!?])\s+(?=[A-Z\"“])", s) if p] if s else []


def jarvis_sha(texts):
    import hashlib
    blob = texts["claude"] + "\n\x00\n" + texts["chatgpt"]
    return hashlib.sha1(blob.encode("utf-8")).hexdigest()[:12]


def jarvis_write(path=JARVIS_FILE):
    """Write evals/jarvis.json. `pasted_sha` (what she last pasted, set from
    the page) is kept; an unchanged text leaves the file untouched, so its
    `generated` date is the day the text last changed. Returns
    (texts, sha, changed)."""
    import json
    from datetime import date as _d
    texts = jarvis()
    sha = jarvis_sha(texts)
    old = {}
    try:
        with open(path, encoding="utf-8") as f:
            old = json.load(f)
    except (OSError, ValueError):
        old = {}
    if not isinstance(old, dict):
        old = {}
    if old.get("sha") == sha and old.get("claude") == texts["claude"]:
        return texts, sha, False
    data = {"claude": texts["claude"], "chatgpt": texts["chatgpt"],
            "sha": sha, "pasted_sha": old.get("pasted_sha"),
            "generated": _d.today().isoformat()}
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1, ensure_ascii=False)
        f.write("\n")
    os.replace(tmp, path)
    return texts, sha, True


def pack_task(ws_name, task_text):
    """The briefing for one task: the task, its workstream block, the people
    it names, and where it already sits in her plans."""
    wstext = _read("workstreams.md")
    parts, people_from = [], [task_text or "", ws_name or ""]

    block = _section(wstext, ws_name) if ws_name else ""
    if task_text:
        parts.append("THE TASK\n" + task_text.strip())
    if block:
        parts.append("ITS WORKSTREAM (from workstreams.md)\n" + block)
        people_from.append(block)
    elif not task_text:
        raise ValueError("nothing to talk about — no task and no workstream")

    ptext = _read("people.md")
    for name in _mentioned_people(people_from):
        pb = _section(ptext, name)
        if pb:
            parts.append("WHO " + name.upper()
                         + " IS (from people.md — her file, her words)\n" + pb)

    # Season ideas naming the same people, or the task itself: "plan time
    # with Maman" should know a picnic with Maman is already on the list.
    names = {n.split()[0].lower() for n in _mentioned_people(people_from)}
    season = [ln.strip() for ln in _read("season.md").splitlines()
              if ln.strip().startswith("- [")
              and (names & set(_norm(ln).split()))][:6]
    if season:
        parts.append("FROM HER SEASON LIST (season.md)\n" + "\n".join(season))

    if task_text and _norm(task_text)[:40] in _norm(_read("today.md")):
        parts.append("NOTE: this task is on today's plan.")

    # Her rulings on this front ride last, so a ruled-out option does not
    # come back while she talks the task through.
    parts.append(_safe(rulings_for, ws_name))

    label = (task_text or ws_name or "").strip()
    return _finish([_safe(card)] + parts), label


def pack_person(name):
    """The briefing for one person: their entry, the open work naming them,
    and any drafts already written to them."""
    ptext = _read("people.md")
    matches = [h for h in _people_headings()
               if h.lower() == name.lower()
               or h.split()[0].lower() == name.strip().lower()]
    if not matches:
        raise ValueError("no one by that name in people.md")
    full = matches[0]
    parts = ["WHO " + full.upper()
             + " IS (from people.md — her file, her words)\n"
             + _section(ptext, full)]

    first = full.split()[0]
    probe = re.compile(r"(?i)(?<![\w])" + re.escape(first) + r"(?![\w])")
    open_lines = []
    for fname in ("workstreams.md", "next.md", "waiting.md", "season.md"):
        for ln in _read(fname).splitlines():
            s = ln.strip()
            if probe.search(s) and (s.startswith("- [ ]") or s.startswith("- **Next:**")):
                open_lines.append(s)
    if open_lines:
        parts.append("OPEN WORK NAMING THEM\n" + "\n".join(open_lines[:10]))

    drafts_dir = os.path.join(BRAIN, "drafts")
    had = []
    for fn in sorted(os.listdir(drafts_dir) if os.path.isdir(drafts_dir) else []):
        if not fn.endswith(".md"):
            continue
        head = _read(os.path.join("drafts", fn))[:600]
        if re.search(r"(?mi)^person:\s*" + re.escape(first), head):
            had.append(fn)
    if had:
        parts.append("DRAFTS ALREADY WRITTEN TO THEM (brain/drafts/)\n"
                     + "\n".join("- " + f for f in had[:6]))
    # These conversations often end in a message to them, so the rules for
    # text someone else reads come along, with this person's register.
    parts.append(_safe(rules_for, "other", person=full))
    return _finish([_safe(card)] + parts), "About " + full


def _safe(fn, *a, **kw):
    """Card, rules and rulings are extras: a pack opens without them rather
    than not at all."""
    try:
        return fn(*a, **kw) or ""
    except Exception:
        return ""


def _finish(parts):
    out = "\n\n".join(p for p in parts if p)
    return _cap(out, PACK_CAP)


def pack(kind, body):
    """The one entry point serve.py calls. Returns (pack_text, label)."""
    if kind == "person":
        return pack_person((body.get("name") or "").strip())
    return pack_task((body.get("ws") or "").strip(),
                     (body.get("task") or "").strip())


def main(argv):
    """For a person checking what a call will carry, and for the commands:

        context.py card [full|voice]
        context.py rules other|plan|her|code [--person NAME] [--front NAME]
        context.py rulings FRONT
        context.py jarvis [--write]    the claude.ai and ChatGPT profile
    """
    import argparse
    ap = argparse.ArgumentParser(prog="context.py")
    ap.add_argument("what", choices=("card", "rules", "rulings", "call",
                                     "jarvis"))
    ap.add_argument("arg", nargs="?", default="")
    ap.add_argument("--person", default=None)
    ap.add_argument("--front", default=None)
    ap.add_argument("--write", action="store_true",
                    help="jarvis: also write brain/evals/jarvis.json")
    a = ap.parse_args(argv)
    if a.what == "jarvis":
        if a.write:
            texts, sha, changed = jarvis_write()
        else:
            texts = jarvis()
            sha, changed = jarvis_sha(texts), None
        for site, label in (("claude", "Claude (Settings, Profile, personal "
                             "preferences)"),
                            ("chatgpt", "ChatGPT (custom instructions)")):
            print(f"== {label}: {len(texts[site])} of {JARVIS_CAP} "
                  f"characters ==\n")
            print(texts[site] + "\n")
        print(f"sha {sha}" + ("" if changed is None else
                              ", written to brain/evals/jarvis.json" if changed
                              else ", unchanged, file left as it was"))
        return 0
    if a.what == "card":
        out = card(a.arg or "full")
    elif a.what == "rules":
        out = rules_for(a.arg or "her", person=a.person, front=a.front)
    elif a.what == "call":
        out = for_call(a.arg or "her", person=a.person, front=a.front)
    else:
        out = rulings_for(a.arg)
    print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

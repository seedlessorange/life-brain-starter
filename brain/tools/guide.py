#!/usr/bin/env python3
"""Turn a deck — plus your own notes on it — into a study guide you can open.

    python3 brain/tools/guide.py --deck "<path to a pdf or pptx>"
    python3 brain/tools/guide.py --course "Innovative Marketing"
    python3 brain/tools/guide.py --all
    python3 brain/tools/guide.py --list

Her existing guides are single-file interactive HTML — sticky header, nav
pills, accordions, tabs, callouts — and that format is the point: she made
them, she revises from them, and a markdown file is not the same object. So
this writes that format, using the same design tokens her own guides use.

What goes in: the slides, and whatever she wrote about that class in Notion.
Slides alone produce a guide that says what the professor said; slides plus
her notes produce one that knows what she found confusing, which is the thing
worth reviewing from.

The model returns structure, not HTML. Asking a model for 50KB of markup
gets you 50KB of markup with one unclosed div in it; asking for a list of
sections and blocks, and rendering those here, cannot break the page.
"""

import argparse
import html
import json
import os
import re
import shutil
import sys
from datetime import date, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
BRAIN = os.path.dirname(HERE)
sys.path.insert(0, HERE)

OUT = os.path.join(BRAIN, "school", "guides")
# The structured content behind every guide, one JSON per deck. This is the
# thing worth keeping: working out what matters in a deck is a model call, and
# it should happen once in the life of that deck. Rendering — a deck guide, or
# a course guide folding ten decks together — reads these and calls nothing.
# Adding a session costs one call; the course guide it feeds costs none.
DATA = os.path.join(OUT, ".data")
NOTES = os.path.join(BRAIN, "school", "notes")
# A deck with its picture slides described runs long — Managing Innovation
# session 2 is ~380 slides of images — and cutting it at 45k characters kept
# the first third of the class. Sonnet reads this comfortably.
MAX_DECK = 140000
MAX_NOTES = 18000
# Class recordings: the transcript's "## Notes" section, written once from the
# whole recording. The raw transcript is 25k words of crosstalk per three
# hours; the notes are what was taught, so they are what a guide reads.
TRANSCRIPTS = os.path.join(BRAIN, "transcripts")


def e(x):
    return html.escape(str(x if x is not None else ""), quote=True)


def _slug(s):
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", (s or "").lower())
                  ).strip("-")[:60] or "guide"


# --------------------------------------------------------------------------
# her notes on this course, if she has any

def notes_for(course):
    """Whatever she wrote about this class, from the Notion pull. Her class
    notes live inside the Class Planner database, as a section per course."""
    best = ""
    want = set(re.sub(r"[^a-z ]", " ", (course or "").lower()).split())
    for fn in sorted(os.listdir(NOTES)) if os.path.isdir(NOTES) else []:
        if not fn.endswith(".md"):
            continue
        try:
            with open(os.path.join(NOTES, fn), encoding="utf-8") as f:
                body = f.read()
        except OSError:
            continue
        # A section whose heading names this course.
        for m in re.finditer(r"^## (.+)$", body, re.M):
            head = set(re.sub(r"[^a-z ]", " ", m.group(1).lower()).split())
            if len(want & head) >= min(2, len(want)):
                start = m.end()
                nxt = body.find("\n## ", start)
                chunk = body[start:nxt if nxt > 0 else len(body)].strip()
                if len(chunk) > len(best):
                    best = chunk
    return best[:MAX_NOTES]


# --------------------------------------------------------------------------
# the model call — structure in, structure out

# Her own quality bar, from the StudyForge work she did in December 2025 —
# seven pillars written before the models could reliably hit them. The design
# was ahead of what a model could do then. It isn't now, so it is worth using.
PILLARS = """Seven rules, in priority order:

1. HOOK FIRST. Open a section with the reason to care — a choice, a paradox,
   a real consequence — before any definition. Never open with "X is...".
2. STRUCTURE OVER PROSE. Two things compared is a table. Four things is a
   grid of cards. A definition is a "define" block. Use a paragraph only when
   nothing more specific fits.
3. ANCHOR IT. Name the real company, number or year the slides used. A
   generic example is worth nothing.
4. EXAM STRATEGY. Say what must be known cold, what only needs understanding,
   and what can be looked up. Say what a phrase in a question is signalling.
5. NARRATIVE. Sections build on each other; later ones may refer back.
6. COGNITIVE LOAD. One idea per block, none longer than about 60 words.
   Split anything longer.
7. ACTIVE OVER PASSIVE. Prefer something she has to answer over something she
   reads."""

SCHEMA = """Reply with JSON only, no prose around it:

{
  "title": "...",
  "subtitle": "one line on what this is for",
  "tags": ["3 to 5 short topic chips"],
  "sections": [
    {"title": "...",
     "hook": "one sentence of tension or a question that makes her want the answer",
     "minutes": 6,
     "blocks": [ ...blocks, see below... ],
     "summary": {"takeaways": ["3-5"], "self_check": ["2-3 questions to ask herself"]},
     "teaser": "one line that pulls into the next section (omit on the last)"}
  ]
}

Blocks:
  {"type": "concept", "title": "...", "hook": "...", "explanation": "...",
   "example": "a real company, person or number from the material",
   "key_points": ["..."], "why": "why it matters", "analogy": "optional"}
  {"type": "check", "question": "...", "kind": "mc" or "tf",
   "options": ["..."], "answer": index of the right option (tf: 0 true, 1 false),
   "explanation": "why that is the answer"}
  {"type": "steps", "title": "...", "intro": "...",
   "items": [{"title": "...", "detail": "...", "tip": "optional"}]}
  {"type": "worked", "title": "...", "scenario": "...", "problem": "...",
   "strategy": "...", "steps": [{"title": "...", "detail": "..."}], "answer": "..."}
  {"type": "define", "term": "...", "definition": "...", "plain": "the same said out loud",
   "example": "...", "not_to_confuse": "optional"}
  {"type": "mistake", "title": "...", "wrong": "...", "why": "...", "right": "...", "tip": "..."}
  {"type": "compare", "title": "...", "head": ["..."], "rows": [["..."]]}
  {"type": "rules", "title": "...", "items": ["if ... then ..."], "tip": "...", "pitfall": "..."}
  {"type": "triggers", "title": "...", "items": [{"words": "phrases", "action": "what to do", "example": "..."}]}
  {"type": "insight", "text": "...", "why": "..."}
  {"type": "priority", "memorise": ["..."], "understand": ["..."], "lookup": ["..."]}

Rules: 4 to 8 sections. Every section opens with a hook, teaches through at
least one concept or define, and has at least one check that tests
understanding rather than recall of wording. Anything sequential is steps;
any choice between two or more options is compare; any calculation or case
decision is worked. The last section is titled "Test yourself" and holds only
4 to 6 checks. Keep the material's own names, numbers and examples. Plain
language. Never describe the source ("this deck covers...").

The reply must be valid JSON. When quoting someone inside a text field, use
curly quotes \u201c like this\u201d or single quotes — never a straight
double quote inside a string."""

# One section from her own StudyForge golden examples (Time Value of Money),
# carried into this schema. It shows the bar, not the subject: the model is
# told to match its quality, never to borrow its content.
GOLDEN = """QUALITY REFERENCE — one section at the standard expected. Match its
quality and shape; do not reuse its subject:

{"title": "The time value of money",
 "hook": "Would you rather have €100 today or €100 in exactly one year?",
 "minutes": 12,
 "blocks": [
  {"type": "concept", "title": "Why money today beats money tomorrow",
   "hook": "If both are €100, why does your gut instantly pick today?",
   "explanation": "Money now can be invested and grow; money promised later misses that growth and carries the risk it never arrives.",
   "example": "$1,000 put into Apple in 2010 was worth over $50,000 a decade and a half later.",
   "key_points": ["Money today can earn returns immediately", "Future money carries risk", "Inflation erodes what it buys"],
   "why": "Mortgages, retirement, every investment decision rests on this.",
   "analogy": "A promise of €100 next year is a seed you are not allowed to plant yet."},
  {"type": "check", "question": "To find what $1,000 grows to in 10 years, you:",
   "kind": "mc", "options": ["Divide by (1+r)^10", "Multiply by (1+r)^10", "Subtract r × 10"],
   "answer": 1, "explanation": "Moving money forward multiplies: FV = PV × (1+r)^t. Dividing moves it back to today."},
  {"type": "mistake", "title": "The most common slip",
   "wrong": "Multiplying when you should divide", "why": "formulas memorised without their direction",
   "right": "Forward (future value) multiplies, money grows; backward (present value) divides, money shrinks.",
   "tip": "FV is Forward, PV is Past-ward"},
  {"type": "triggers", "title": "Which one?", "items": [
   {"words": "how much will I have, what will it grow to", "action": "Future value", "example": "What will $10,000 be worth in 20 years?"},
   {"words": "what is it worth today, how much to invest now", "action": "Present value", "example": "How much now, to have $100,000 at 65?"}]}
 ],
 "summary": {"takeaways": ["Money today is worth more: opportunity cost plus risk", "Forward multiplies, backward divides"],
             "self_check": ["Can I explain why money today is worth more?", "Do I know when to multiply and when to divide?"]},
 "teaser": "Money can move through time. How do you judge a project with many cash flows on different dates?"}"""

FAILED = os.path.join(OUT, ".data", "_failed")


def _ask_json(prompt, system="", timeout=300, audience="her"):
    """One guide call that has to come back as JSON — asked twice if needed.

    A book like The Mom Test is full of quoted phrases, and one straight
    double quote inside a string breaks the whole reply; a long guide can
    also be cut off. The first failure is kept on disk to look at, and the
    model is asked again, told what went wrong. A second failure raises, and
    the job reports it rather than leaving an older guide looking current.

    audience="her" puts the card about her in front, so a guide knows who
    it teaches. The repairs and the book-on-its-own-terms guide pass None:
    they are told to add nothing, and a card of her projects invites that."""
    import llm
    r = llm.complete("guide", prompt, system=system, timeout=timeout,
                     audience=audience)
    raw = r.get("text") or ""
    try:
        r["_json"] = _json_from(raw)
        return r
    except ValueError:
        os.makedirs(FAILED, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        with open(os.path.join(FAILED, stamp + ".txt"), "w", encoding="utf-8") as f:
            f.write(raw)
        cut = raw.rstrip()[-1:] not in ("}", "`")
    r = llm.complete(
        "guide",
        prompt + "\n\nYOUR PREVIOUS REPLY COULD NOT BE PARSED AS JSON"
        + (" — it was cut off before the end" if cut else "")
        + ". Reply again with complete, valid JSON only. Inside text use curly "
          "quotes (\u201c \u201d) or single quotes, never a straight double "
          "quote. Keep blocks tight so the whole guide fits.",
        system=system, timeout=timeout, audience=audience)
    r["_json"] = _json_from(r.get("text") or "")
    r["_retried"] = True
    return r


def _json_from(text):
    """The first JSON object in a reply, however the model wrapped it."""
    t = (text or "").strip()
    t = re.sub(r"^```(?:json)?|```$", "", t, flags=re.M).strip()
    try:
        return json.loads(t)
    except ValueError:
        pass
    depth, start = 0, -1
    for i, ch in enumerate(t):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start >= 0:
                try:
                    return json.loads(t[start:i + 1])
                except ValueError:
                    start = -1
    raise ValueError("the model didn't return usable JSON")


def read_deck(path, course="", quiet=False):
    """What a deck says: its typed text, plus, for a PDF, what its picture
    slides show (slides.py — looked at once per file, cached after that).
    Falls back to the typed text alone if the pictures can't be read."""
    import school
    if path.lower().endswith(".pdf"):
        try:
            import slides
            text = slides.enrich(path, course=course, quiet=quiet)
            if text.strip():
                return text
        except Exception:                                # noqa: BLE001
            pass
    return school.extract(path)


def build_content(course, deck_name, deck_text, her_notes=""):
    import llm
    notes_part = ("\n\nHER OWN NOTES FROM THIS CLASS — these matter more than "
                  "the slides. Where they show confusion, answer it. Where "
                  "they record something the professor said that is not on "
                  "the slides, keep it:\n\n" + her_notes) if her_notes else ""
    r = _ask_json(
        "You are building a revision guide for an MBA student from "
        "the slides of one session of %r.\n\n%s\n\n%s\n\nSLIDES (%s):\n\n%s%s"
        % (course, PILLARS, SCHEMA + "\n\n" + GOLDEN, deck_name,
           deck_text[:MAX_DECK], notes_part),
        system="You turn lecture material into revision guides a student "
               "would actually reopen. You reply with JSON and nothing else.",
        timeout=300)
    data = r["_json"]
    data["_provider"] = r.get("provider")
    data["_model"] = r.get("model")
    return data


# --------------------------------------------------------------------------
# rendering — guide_ui.py holds the look; this only says where it goes

def guide_id_for(path):
    """A guide's stable name for its saved progress: its path in the brain."""
    return os.path.relpath(path, BRAIN).replace(os.sep, "/")


def render(data, course, source, out_path=""):
    import guide_ui
    return guide_ui.render(data, course, source,
                           guide_id_for(out_path) if out_path else _slug(course))


def _course_of(deck_path):
    import school
    for base in (school.term_root(), school.DECKS):
        if deck_path.startswith(base + os.sep):
            return os.path.relpath(deck_path, base).split(os.sep)[0]
    return os.path.basename(os.path.dirname(deck_path))


def content_for(deck_path, force=False, quiet=False):
    """The structured content for one deck, from cache when it exists.

    This is the only function in the file that costs anything. Everything
    else renders what it returns."""
    import school
    # The second lock. catch() will not bring confidential material in, but
    # she may put a file in the class folder herself, and this is the call
    # that would send it to a model.
    if school.is_confidential(deck_path):
        raise ValueError("that filename is on the confidential list — no "
                         "guide is built and nothing was read")
    course = _course_of(deck_path)
    stem = os.path.splitext(os.path.basename(deck_path))[0]
    cache = os.path.join(DATA, _slug(course), _slug(stem) + ".json")
    if os.path.exists(cache) and not force:
        try:
            with open(cache, encoding="utf-8") as f:
                return json.load(f), course, False
        except (OSError, ValueError):
            pass
    text = read_deck(deck_path, course=course, quiet=quiet)
    if len(text.strip()) < 400:
        raise ValueError("too little text in that file")
    her = notes_for(course)
    if not quiet:
        print("  reading %s%s" % (stem[:52],
                                  "  (+ your notes)" if her else ""),
              flush=True)
    data = build_content(course, os.path.basename(deck_path), text, her)
    data["_used_notes"] = bool(her)
    data["_deck"] = os.path.basename(deck_path)
    data["_built"] = date.today().isoformat()
    os.makedirs(os.path.dirname(cache), exist_ok=True)
    with open(cache, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1, ensure_ascii=False)
    return data, course, True


def one(deck_path, force=False, quiet=False):
    stem = os.path.splitext(os.path.basename(deck_path))[0]
    data, course, fresh = content_for(deck_path, force=force, quiet=quiet)
    out_dir = os.path.join(OUT, _slug(course))
    out = os.path.join(out_dir, _slug(stem) + ".html")
    if os.path.exists(out) and not fresh and not force:
        return {"skipped": out}
    os.makedirs(out_dir, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        f.write(render(data, course, data.get("_deck") or stem, out))
    return {"wrote": out, "sections": len(data.get("sections") or []),
            "used_notes": bool(data.get("_used_notes")),
            "model": data.get("_model"), "from_cache": not fresh}


def course_context(course, budget=9000):
    """What this course has actually covered, from the cached deck content.

    A book guide written blind gives you the book. Written against the course
    it gives you the parts of the book this professor is going to ask about,
    and skips the chapters the course already covered better."""
    cdir = os.path.join(DATA, _slug(course))
    if not os.path.isdir(cdir):
        return ""
    bits = []
    for fn in sorted(os.listdir(cdir)):
        if not fn.endswith(".json") or fn.startswith("book-"):
            continue
        try:
            with open(os.path.join(cdir, fn), encoding="utf-8") as f:
                d = json.load(f)
        except (OSError, ValueError):
            continue
        names = [s.get("title") or s.get("name") or ""
                 for s in d.get("sections") or []]
        bits.append("- %s: %s" % (d.get("title") or fn,
                                  "; ".join(n for n in names if n)))
    ctx = "\n".join(bits)
    her = notes_for(course)
    if her:
        ctx += "\n\nHer own notes from this course:\n" + her[:5000]
    return ctx[:budget]


def _book_text(b):
    import books as _bk
    return " ".join(t for _, t in _bk.sections(b["path"]))


_NUM = re.compile(
    r"(?:[$€£]\s?\d[\d,.]*\s*(?:k|m|million|billion|bn)?"
    r"|\d[\d,.]*\s*(?:%|percent|million|billion|months?|years?|weeks?|days?"
    r"|hours?|minutes?|people|customers|companies|startups))", re.I)


def unverified_specifics(data, source_text):
    """Figures in a guide that the book never states.

    A number is the easiest thing for a model to embellish and the easiest
    thing to check mechanically: every amount, percentage and count in the
    guide is looked for in the book. Lines that are explicitly about Venture
    or framed as "Imagine" are her own scenarios and are left alone."""
    src = " ".join(source_text.lower().split())
    src_digits = re.sub(r"[^0-9]", " ", src)
    found = []

    def walk(x):
        if isinstance(x, dict):
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)
        elif isinstance(x, str):
            low = x.lower()
            if "venture" in low or low.startswith(("imagine", "for venture")):
                return
            for m in _NUM.finditer(x):
                digits = re.sub(r"[^0-9]", "", m.group(0))
                words = re.sub(r"[^a-z]", "", m.group(0).lower())
                if not digits:
                    continue
                hit = (" " + digits + " ") in (" " + src_digits + " ")
                if digits.endswith("000") and not hit:
                    short = digits.rstrip("0")
                    hit = short and any(w in src for w in (short + " million",
                                        short + "m ", short + "k ", "half a million"))
                if not hit and words in ("million",) and digits in src_digits.split():
                    hit = True
                if not hit:
                    found.append(m.group(0).strip())

    walk(data.get("sections") or [])
    return sorted(set(found))


def _repair_specifics(data, unverified):
    """One call to take out what the book doesn't say, keeping the rest."""
    try:
        r = _ask_json(
            "This study guide JSON was written from a book, but these figures "
            "do not appear anywhere in the book: %s\n\nFor each one: if it "
            "belongs to the book's own example, restore the book's wording "
            "without the invented figure; if it was added for effect, remove "
            "it. Do not change anything else. Reply with the whole corrected "
            "JSON.\n\n%s" % ("; ".join(unverified),
                               json.dumps(data, ensure_ascii=False)),
            system="You correct factual slips in JSON without rewriting it. "
                   "You reply with JSON and nothing else.",
            timeout=1200, audience=None)
        fixed = r["_json"]
        return fixed if fixed.get("sections") else None
    except Exception:                                    # noqa: BLE001
        return None


def _strings(x, out):
    if isinstance(x, dict):
        for k, v in x.items():
            if not k.startswith("_"):
                _strings(v, out)
    elif isinstance(x, list):
        for v in x:
            _strings(v, out)
    elif isinstance(x, str):
        out.append(x)
    return out


_FW_LINE = re.compile(
    r"(?i)\bventure\b|\byour (?:team|teammates?|jury|business plan|financial model|"
    r"pitch|deck|beachhead)\b|\b(?:re)?insurers?\b|\bcat[- ]modell?ers?\b|"
    r"\bcatastrophe modell?ers?\b|\boffshore wind\b|\bports?\b|\bharbours?\b|"
    r"\bcoastal\b|\bearly[- ]warning\b|\b(?:CMO|CFO|COO)\b|\bchief strategy officer\b|"
    r"\bco-?founders?\b")
# Her teammates are classmates with roles, and the guides kept promoting them.
_FW_ROLE = re.compile(r"(?i)\bco-?founders?\b")
# The school's own name joins these from config (school.names) at use.
_FW_ALLOWED = {"venture", "venture lab", "paris", "mba", "ceo", "cto", "cmo", "tam",
               "roi", "r&d", "tv", "kpi", "okr", "b2b", "linkedin",
               "cfo", "coo", "cso", "i", "imagine", "for", "if", "when", "november",
               "december", "q&a", "ok"}
_FIGURE = re.compile(
    r"[€$£]\s?\d[\d.,]*\s?(?:[kKmMbB]n?|million|billion)?|\b\d[\d.,]*\s?(?:%|percent)"
    r"|\b(?:19|20)\d\d\b|\bQ[1-4]\b")


def venture_inventions(data, source_text):
    """Venture lines that name something or give a figure that neither the
    description of Venture nor the book contains.

    Everything the model knows about Venture is a paragraph with no names
    and no numbers in it, so a named regulator, rival, client, storm or
    percentage on a Venture line can only have been made up — however
    plausible it reads. Found mechanically, so fixing them can't touch
    anything else."""
    import books as _bk
    import model as _m
    desc = _bk.VENTURE.lower()
    allowed = _FW_ALLOWED | set(_m.school_names())
    words = set(re.findall(r"[a-z0-9][a-z0-9&'\-]*", source_text.lower()))
    flagged = []
    for t in dict.fromkeys(_strings(data.get("sections") or [], [])):
        if not _FW_LINE.search(t):
            continue
        bad = []
        for m in re.finditer(r"(?<![.!?:'‘“\"]\s)(?<![-'‘“\"])(?<!^)\b([A-Z][A-Za-z&\-]*[A-Za-z](?:\s(?:[A-Z][A-Za-z&\-]*|II|III|IV))*)", t):
            name = m.group(1)
            parts = name.lower().split()
            if all(p in allowed or p in desc for p in parts):
                continue
            if all(p in words for p in parts) and not name.isupper():
                continue
            bad.append(name)
        for m in _FIGURE.finditer(t):
            fig = m.group(0).strip()
            if fig.lower() in desc:
                continue
            bad.append(fig)
        bad += [m.group(0) for m in _FW_ROLE.finditer(t)]
        if bad:
            flagged.append((t, list(dict.fromkeys(bad))))
    return flagged


def _repair_venture(data, flagged):
    """One call that rewrites only the flagged lines, then swaps each back in
    where it is found word for word. Returns (data, applied, left)."""
    import books as _bk
    listing = "\n\n".join("LINE: %s\nREMOVE: %s" % (t, "; ".join(bad))
                          for t, bad in flagged)
    r = _ask_json(
        "These lines come from a study guide that applies a book to Venture, "
        "a student company. Everything known about Venture is this, and "
        "nothing more:\n%s\n\nEach line below contains details that are not "
        "in that description and were made up: named organisations, people, "
        "regulations, software, events, prices, percentages or years (listed "
        "under REMOVE). Rewrite each line without them. Use a generic role "
        "('a reinsurer', 'a port authority'), a plain phrase ('a pilot fee', "
        "'the accuracy gain you can prove'), or turn a made-up claim into a "
        "question for her. Keep the lesson, the voice and roughly the length; "
        "add nothing specific of your own. If a detail belongs to the book's "
        "own example rather than to Venture, keep it.\n\nReply with JSON "
        "{\"lines\": [{\"old\": \"the line exactly as given\", \"new\": "
        "\"...\"}]}. Inside strings use curly quotes, never a straight double "
        "quote.\n\n%s" % (_bk.VENTURE, listing),
        system="You remove invented facts from text without rewriting the rest. "
               "You reply with JSON and nothing else.",
        timeout=900, audience=None)
    swaps = {x.get("old"): x.get("new") for x in r["_json"].get("lines") or []
             if x.get("old") and x.get("new") and x.get("old") != x.get("new")}

    def swap(x):
        if isinstance(x, dict):
            return {k: (v if k.startswith("_") else swap(v)) for k, v in x.items()}
        if isinstance(x, list):
            return [swap(v) for v in x]
        if isinstance(x, str) and x in swaps:
            return swaps[x]
        return x
    data["sections"] = swap(data["sections"])
    applied = [t for t, _ in flagged if t in swaps]
    return data, applied


def clean_venture(b, data):
    """Take invented Venture facts out of a guide; logs what it changed."""
    text = _book_text(b)
    found = venture_inventions(data, text)
    log = {"found": len(found), "fixed": []}
    if found:
        try:
            data, fixed = _repair_venture(data, found)
            log["fixed"] = fixed
        except Exception as exc:                         # noqa: BLE001
            log["error"] = str(exc)[:160]
    log["left"] = [bad for _, bad in venture_inventions(data, text)]
    data["_venture_check"] = log
    return data


def clean_venture_book(book, course=""):
    """Run the Venture check on a guide that already exists, and redraw it."""
    import books as _bk
    b = _bk.find(book)
    course = course or _course_of(b["path"])
    cache = os.path.join(DATA, _slug(course), "book-" + b["slug"] + ".json")
    out = os.path.join(OUT, _slug(course), "book-" + b["slug"] + ".html")
    with open(cache, encoding="utf-8") as f:
        data = json.load(f)
    data = clean_venture(b, data)
    with open(cache, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1, ensure_ascii=False)
    source = "%s — %s" % (b["title"], b["author"]) if b["author"] else b["title"]
    with open(out, "w", encoding="utf-8") as f:
        f.write(render(data, course, source, out))
    c = data["_venture_check"]
    return {"wrote": out, "found": c["found"], "fixed": len(c["fixed"]),
            "left": c["left"]}


def book_guide(book, course="", force=False, rerender=False, general=False):
    """A guide to one book, written for what she is actually doing.

    `general` builds the other kind: the book on its own terms, from the
    general notes — the vocabulary, the author's own examples, no project and
    no course. Both live side by side; neither replaces the other.

    Reuses the section notes books.py already produced, so the book is read
    once and this is a single call on top of it. The content is cached, so a
    later change to how guides look re-renders it without another call
    (`rerender`)."""
    import books as _bk
    import school
    b = _bk.find(book)
    if school.is_confidential(b["path"]):
        raise ValueError("that filename is on the confidential list")
    course = course or _course_of(b["path"])
    out_dir = os.path.join(OUT, _slug(course))
    stem = "book-" + b["slug"] + ("-general" if general else "")
    out = os.path.join(out_dir, stem + ".html")
    cache = os.path.join(DATA, _slug(course), stem + ".json")
    source = "%s — %s" % (b["title"], b["author"]) if b["author"] else b["title"]

    if rerender and os.path.exists(cache):
        with open(cache, encoding="utf-8") as f:
            data = json.load(f)
        os.makedirs(out_dir, exist_ok=True)
        with open(out, "w", encoding="utf-8") as f:
            f.write(render(data, course, source, out))
        return {"wrote": out, "model_calls": 0}
    if os.path.exists(out) and not force:
        return {"skipped": out}

    notes_path = os.path.join(BRAIN, "school", "books",
                              b["slug"] + ("-general" if general else "") + ".md")
    if not os.path.exists(notes_path):
        raise ValueError(
            "read the book first: python3 brain/tools/books.py --read %s%s"
            % (b["slug"], " --general" if general else ""))
    with open(notes_path, encoding="utf-8") as f:
        learnings = f.read()

    import llm
    if general:
        r = _ask_json(
            "You are building a study guide to a BOOK for an MBA student who "
            "wants to learn the book itself, properly.\n\n%s\n\n%s\n\n%s\n\n"
            "Teach the book on its own terms: its argument, the vocabulary it "
            "coins or redefines, and the cases and numbers the author "
            "actually uses. Define every term the way the author defines it. "
            "Where the evidence is thin or the claim is contested, teach that "
            "too. Do NOT apply the book to any project, company or course of "
            "hers, do not invent a reader's situation, and add nothing the "
            "book does not contain.\n\n"
            "THE BOOK — %s by %s, already read and condensed:\n\n%s"
            % (PILLARS, SCHEMA, GOLDEN, b["title"],
               b["author"] or "the author", learnings[:60000]),
            system="You turn a book into something a student can learn from. "
                   "You reply with JSON and nothing else.",
            timeout=1200, audience=None)
        data = r["_json"]
        unverified = unverified_specifics(data, _book_text(b))
        if unverified:
            data = _repair_specifics(data, unverified) or data
            data["_unverified_after_repair"] = unverified_specifics(
                data, _book_text(b))
        data.setdefault("title", b["title"])
        data["_general"] = True
        data["_model"] = r.get("model")
        data["_built"] = date.today().isoformat()
        os.makedirs(os.path.dirname(cache), exist_ok=True)
        with open(cache, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=1, ensure_ascii=False)
        os.makedirs(out_dir, exist_ok=True)
        with open(out, "w", encoding="utf-8") as f:
            f.write(render(data, course, source, out))
        return {"wrote": out, "sections": len(data.get("sections") or []),
                "course": course, "model": r.get("model")}
    ctx = course_context(course)
    r = _ask_json(
        "You are building a study guide to a BOOK for an School MBA "
        "student, so she can use it on %r.\n\n%s\n\n%s\n\n%s\n\n"
        "HER PROJECT: %s\n\n%s\n\n"
        "WHAT THE COURSE HAS COVERED (connect the book to it, and skip what "
        "the course already does better):\n%s\n\n"
        "THE BOOK — %s by %s, already read and condensed:\n\n%s"
        % (course, PILLARS, SCHEMA, GOLDEN, _bk.VENTURE, _bk.ACCURACY,
           ctx or "(nothing cached yet)",
           b["title"], b["author"] or "the author", learnings[:60000]),
        system="You turn a book into something a student uses this month. "
               "You reply with JSON and nothing else.",
        timeout=1200)
    data = r["_json"]
    unverified = unverified_specifics(data, _book_text(b))
    if unverified:
        data = _repair_specifics(data, unverified) or data
        data["_unverified_after_repair"] = unverified_specifics(data, _book_text(b))
    data = clean_venture(b, data)
    data.setdefault("title", b["title"])
    data["_model"] = r.get("model")
    data["_built"] = date.today().isoformat()
    os.makedirs(os.path.dirname(cache), exist_ok=True)
    with open(cache, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1, ensure_ascii=False)
    os.makedirs(out_dir, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        f.write(render(data, course, source, out))
    return {"wrote": out, "sections": len(data.get("sections") or []),
            "course": course, "model": r.get("model")}


MIN_NEW_WORDS = 1200        # below this, wait for the next session
# One fold call takes at most this much material. Handed 51k words at once
# (Managing Innovation with its picture slides described), the model kept one
# theme and dropped the rest, and a one-call rebuild of Advanced
# Entrepreneurship came back at a third of its old size. A batch at a time is
# how the good guides were built in the first place.
FOLD_WORDS = 12000


def _course_state(course):
    p = os.path.join(DATA, _slug(course), "_course.json")
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f), p
    except (OSError, ValueError):
        return {"decks": [], "sections": [], "title": course,
                "subtitle": ""}, p


def _parts(name, text, limit=FOLD_WORDS):
    """A deck's text in pieces of at most `limit` words, cut between slides.
    [(key, label, text)] — one piece, keyed by the deck's name, when it fits."""
    if len(text.split()) <= limit:
        return [(name, name, text)]
    pieces, cur, n = [], [], 0
    for block in re.split(r"(?=^--- slide \d+ ---$)", text, flags=re.M):
        w = len(block.split())
        if cur and n + w > limit:
            pieces.append("".join(cur))
            cur, n = [], 0
        cur.append(block)
        n += w
    if cur:
        pieces.append("".join(cur))
    k = len(pieces)
    return [("%s#%d" % (name, i + 1), "%s (part %d of %d)" % (name, i + 1, k),
             p) for i, p in enumerate(pieces)]


def recordings(course):
    """This course's class recordings that have notes, as guide material.
    A recording whose notes are not written yet is left out, so it folds in
    on a later run rather than being marked done empty."""
    out = []
    want = (course or "").lower()
    try:
        names = sorted(os.listdir(TRANSCRIPTS))
    except OSError:
        return out
    for fn in names:
        if not fn.endswith(".md"):
            continue
        try:
            with open(os.path.join(TRANSCRIPTS, fn), encoding="utf-8") as f:
                body = f.read()
        except OSError:
            continue
        fm = dict(re.findall(r"^(class|session):[ \t]*(.*)$", body[:800], re.M))
        cls = fm.get("class", "").lower()
        if not cls or not want or (want not in cls and cls not in want):
            continue
        m = re.search(r"^## Notes\n(.*?)(?=^## Transcript\b|\Z)", body,
                      re.S | re.M)
        if not m or len(m.group(1).split()) < 60:
            continue
        try:
            when = datetime.strptime(fm.get("session", "")[:16],
                                     "%Y-%m-%d %H:%M")
        except ValueError:
            when = datetime.fromtimestamp(
                os.path.getmtime(os.path.join(TRANSCRIPTS, fn)))
        out.append({"name": "recording: " + fn, "mtime": when.timestamp(),
                    "label": "Class recording, %s %d %s %s (notes from the "
                             "transcript: what was said in class)"
                             % (when.strftime("%a"), when.day,
                                when.strftime("%b"), when.strftime("%H:%M")),
                    "text": m.group(1).strip()})
    return out


def update(course, force=False, min_words=MIN_NEW_WORDS, quiet=False,
           rebuild=False):
    """Fold whatever is new for this course into its one growing guide.

    The unit of work is the course, not the deck. Her decks run 500-800 words
    because the classes are discussions — a model call each was paying full
    price for a slide that says "Why CEO?" and nothing else. So new decks
    accumulate, their text is pulled out locally for free, and they are folded
    in once there is enough to be worth it: one call per ~12k words, a big
    deck split between slides. Progress is saved after every call, so a
    failure halfway keeps what landed and the next run carries on.

    Returns without calling anything when there isn't. `force` overrides,
    for the evening before an exam."""
    import school
    state, spath = _course_state(course)
    if rebuild:
        # Start the course guide again from every session, batch by batch.
        # Used when the guide format itself changes.
        state = {"decks": [], "parts": [], "sections": [], "title": course,
                 "subtitle": ""}
        force = True
    done = set(state.get("decks") or [])
    parts_done = set(state.get("parts") or [])
    pending = [f for f in decks(course) + recordings(course)
               if f["name"] not in done
               and not school.is_confidential(f["name"])]
    if not pending:
        return {"course": course, "nothing_new": True}
    pending.sort(key=lambda f: f["mtime"])     # oldest first: session order

    work, skipped = [], set()
    for f in pending:
        text = f.get("text") or read_deck(f["path"], course=course,
                                          quiet=quiet)
        if len(text.split()) < 60:
            skipped.add(f["name"])
            continue
        for key, label, part in _parts(f.get("label") or f["name"], text):
            key = key.replace(f.get("label") or f["name"], f["name"], 1)
            if key not in parts_done:
                work.append((f["name"], key, label, part))
    if not work:
        state["decks"] = sorted(done | {f["name"] for f in pending})
        _save_course(state, spath)
        return {"course": course, "nothing_new": True}

    words = sum(len(w[3].split()) for w in work)
    decks_in = sorted({w[0] for w in work})
    if words < min_words and not force:
        return {"course": course, "waiting": True, "words": words,
                "sessions": len(decks_in), "need": min_words}

    # A recording's notes get a call of their own. They are already distilled
    # from three hours of class, so they are dense in a way a deck is not:
    # four recordings and two decks in one call (Scaleup, 2 Oct) came back as
    # nine sections and lost whole topics, where one recording alone gave six.
    batches, cur, n = [], [], 0
    for item in work:
        w = len(item[3].split())
        rec = item[0].startswith("recording: ")
        if cur and (rec or n + w > FOLD_WORDS):
            batches.append(cur)
            cur, n = [], 0
        cur.append(item)
        n += w
        if rec:
            batches.append(cur)
            cur, n = [], 0
    if cur:
        batches.append(cur)
    if not quiet:
        print("  %s: folding in %d session%s, %d words, in %d call%s"
              % (course[:40], len(decks_in), "" if len(decks_in) == 1 else "s",
                 words, len(batches), "" if len(batches) == 1 else "s"),
              flush=True)

    notes = notes_for(course)
    model = None
    for bi, batch in enumerate(batches):
        body = "\n\n".join("### %s\n%s" % (label, text)
                            for _, _, label, text in batch)
        have = [s.get("title") or s.get("name") or ""
                for s in state.get("sections") or []]
        r = _ask_json(
            "You are extending a running study guide for an School MBA "
            "student on %r.\n\n%s\n\n%s\n\n"
            "The guide ALREADY has these sections, so do not repeat them — add "
            "what is new, and refer back where it connects:\n%s\n\n"
            "NEW MATERIAL from the sessions since:\n\n%s%s"
            % (course, PILLARS, SCHEMA + "\n\n" + GOLDEN,
               "; ".join(have) or "(none yet — this is the first)",
               body,
               ("\n\nHER OWN NOTES ON THIS COURSE — these matter more than "
                "the slides:\n\n" + notes) if notes else ""),
            system="You extend a running study guide. You reply with JSON and "
                   "nothing else.",
            timeout=max(420, 300 + len(body.split()) // 40))
        fresh = r["_json"]
        model = r.get("model")
        state.setdefault("sections", []).extend(fresh.get("sections") or [])
        got = set(state.get("parts") or []) | {k for _, k, _, _ in batch}
        state["parts"] = sorted(got)
        # A deck is done once every one of its parts has been folded.
        finished = {d for d in decks_in
                    if all(k in got for dd, k, _, _ in work if dd == d)}
        state["decks"] = sorted(done | finished | skipped)
        state["title"] = state.get("title") or fresh.get("title") or course
        state["subtitle"] = fresh.get("subtitle") or state.get("subtitle", "")
        state["tags"] = fresh.get("tags") or state.get("tags") or []
        state["_model"] = model
        _save_course(state, spath)
        if not quiet and len(batches) > 1:
            print("    call %d of %d: +%d sections"
                  % (bi + 1, len(batches), len(fresh.get("sections") or [])),
                  flush=True)
    out = render_course(course, state)
    return {"course": course, "wrote": out, "folded": len(decks_in),
            "calls": len(batches), "sections": len(state["sections"]),
            "model": model}


def _save_course(state, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=1, ensure_ascii=False)


def render_course(course, state=None):
    """The course guide, from what is already extracted. No model call."""
    if state is None:
        state, _ = _course_state(course)
    secs = state.get("sections") or []
    data = {"title": state.get("title") or course,
            "subtitle": state.get("subtitle")
            or "Everything from this course so far.",
            "tags": state.get("tags") or [],
            "sections": secs}
    out = os.path.join(OUT, _slug(course), "_course.html")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        got = state.get("decks") or []
        r = sum(1 for d in got if d.startswith("recording: "))
        n = len(got) - r
        f.write(render(data, course, "%d deck%s%s%s"
                       % (n, "" if n == 1 else "s",
                          ", %d class recording%s" % (r, "" if r == 1 else "s")
                          if r else "",
                          " and your notes" if notes_for(course) else ""),
                       out))
    return out


def course_guide(course, force=False):
    """One guide for a whole course, folded from every deck already read.

    No model call. Each deck's content was extracted once and cached; this
    stitches them in session order and renders. A new session therefore costs
    one call for that deck and nothing for the course guide it joins, which
    is what makes keeping a live course guide affordable at all."""
    cdir = os.path.join(DATA, _slug(course))
    if not os.path.isdir(cdir):
        return {"skipped": course, "why": "no decks read for this course yet"}
    parts = []
    for fn in sorted(os.listdir(cdir)):
        if not fn.endswith(".json"):
            continue
        try:
            with open(os.path.join(cdir, fn), encoding="utf-8") as f:
                parts.append(json.load(f))
        except (OSError, ValueError):
            continue
    if not parts:
        return {"skipped": course, "why": "nothing cached yet"}

    sections, notes_used = [], False
    for d in parts:
        notes_used = notes_used or bool(d.get("_used_notes"))
        label = d.get("title") or d.get("_deck") or "Session"
        # Each session becomes one section of the course guide, its own
        # sections demoted to blocks inside it, so the shape stays flat
        # enough to navigate in December.
        blocks = []
        if d.get("subtitle"):
            blocks.append({"type": "para", "text": d["subtitle"]})
        for sec in d.get("sections") or []:
            inner = sec.get("blocks") or []
            if not inner:
                continue
            blocks.append({"type": "para",
                           "text": "— " + (sec.get("name") or "")})
            blocks += inner
        sections.append({"name": label, "blocks": blocks})

    data = {"title": course,
            "subtitle": "Every session so far, in order.",
            "stats": [{"value": str(len(parts)), "label": "sessions"},
                      {"value": str(sum(len(s["blocks"]) for s in sections)),
                       "label": "blocks"}],
            "sections": sections, "_used_notes": notes_used}
    out = os.path.join(OUT, _slug(course), "_course.html")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        f.write(render(data, course, "%d sessions" % len(parts), out))
    return {"wrote": out, "sessions": len(parts), "model_calls": 0}


# --------------------------------------------------------------------------
# reading progress, kept by the brain so the laptop and the phone agree

PROGRESS = os.path.join(OUT, ".progress.json")
_GUIDE_ID = re.compile(r"^school/guides/[a-z0-9-]+/[a-z0-9_-]+\.html$")


def _read_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


# The server answers requests on several threads, and a quick run of clicks
# in a guide sends overlapping saves. A shared ".tmp" name let two of them
# collide (one replaced the other's file mid-write, and returned a 500). Each
# write now takes a lock and gets its own temporary file.
import threading as _threading
_LOCK = _threading.Lock()


def _write_json(path, data):
    import tempfile
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1)
    os.replace(tmp, path)


def progress_get(guide):
    if not _GUIDE_ID.match(guide or ""):
        raise ValueError("not a guide")
    return _read_json(PROGRESS, {}).get(guide) or {"done": [], "last": 0}


def progress_set(guide, done, last):
    if not _GUIDE_ID.match(guide or ""):
        raise ValueError("not a guide")
    with _LOCK:
        allp = _read_json(PROGRESS, {})
        allp[guide] = {"done": sorted({int(i) for i in (done or []) if int(i) >= 0}),
                       "last": max(0, int(last or 0)),
                       "at": date.today().isoformat()}
        _write_json(PROGRESS, allp)
        return allp[guide]


# --------------------------------------------------------------------------
# building a book guide from the page

JOBS = os.path.join(OUT, ".jobs.json")
JOBLOGS = os.path.join(OUT, ".jobs")


def _alive(pid):
    """Whether a book job is still working.

    A finished child lingers as a zombie until its parent collects it, and
    kill(pid, 0) still answers for a zombie — so a job the server started
    would read as running forever and block every other book. Collect it if
    it is ours; if it isn't (the server restarted since), ask ps."""
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return False
    if hasattr(os, "WNOHANG"):                      # Windows has no zombies
        try:
            got, _ = os.waitpid(pid, os.WNOHANG)
            if got == pid:
                return False
        except ChildProcessError:
            pass
        except OSError:
            return False
    import procs
    return procs.alive(pid)


def _stage(slug):
    try:
        with open(os.path.join(JOBLOGS, slug + ".log"), encoding="utf-8") as f:
            tail = f.read()[-3000:]
    except OSError:
        return ""
    if '"wrote"' in tail:
        return "Finishing up"
    if "synthesising" in tail:
        return "Writing the guide"
    got = re.findall(r"^\s*(\d+)/(\d+)\s", tail, re.M)
    if got:
        return "Reading, section %s of %s" % got[-1]
    if "already read" in tail:
        return "Writing the guide"
    return "Starting"


def _job_failed(slug):
    """Did the last build of this book end in an error? Read from the job's
    own exit line, not from whether a guide file exists — an older guide
    sitting there made a failed rebuild look like a success."""
    try:
        with open(os.path.join(JOBLOGS, slug + ".log"), encoding="utf-8") as f:
            tail = f.read()[-4000:]
    except OSError:
        return False
    m = re.findall(r"JOB-EXIT:(\d+)", tail)
    if m:
        return m[-1] != "0"
    # jobs started before the exit line existed: a crash is still a failure
    return "Traceback (most recent call last)" in tail


def book_status():
    """Every book in the class folder, and where its guide stands."""
    import books as _bk
    jobs = _read_json(JOBS, {})
    out = []
    for b in _bk.books():
        course = _course_of(b["path"])
        html = os.path.join(OUT, _slug(course), "book-" + b["slug"] + ".html")
        gen = os.path.join(OUT, _slug(course),
                           "book-" + b["slug"] + "-general.html")
        notes = os.path.join(BRAIN, "school", "books",
                             b["slug"] + "-general.md")
        job = jobs.get(b["slug"]) or {}
        running = bool(job) and _alive(job.get("pid"))
        out.append({"slug": b["slug"], "title": b["title"], "author": b["author"],
                    "course": course, "read": b["done"],
                    "guide": os.path.exists(html),
                    "href": guide_id_for(html) if os.path.exists(html) else "",
                    "general": os.path.exists(gen),
                    "general_href": (guide_id_for(gen)
                                     if os.path.exists(gen) else ""),
                    "general_notes": os.path.exists(notes),
                    "running": running,
                    "stage": _stage(b["slug"]) if running else "",
                    "failed": bool(job) and not running and _job_failed(b["slug"])})
    return out


def start_book(slug, reread=False, act_id=""):
    """Read one book and build its guide, in the background.

    One at a time: a book is a few dozen calls against her subscription, and
    starting all seven at once is how a week's allowance disappears in an
    afternoon. The environment drops any API key, so it bills the
    subscription — her rule."""
    import subprocess
    import books as _bk
    import school
    b = _bk.find(slug)
    if school.is_confidential(b["path"]):
        raise ValueError("that filename is on the confidential list")
    jobs = _read_json(JOBS, {})
    for other, job in jobs.items():
        if _alive(job.get("pid")):
            raise ValueError("another book is being read right now — one at a "
                             "time, so it doesn't eat the subscription")
    os.makedirs(JOBLOGS, exist_ok=True)
    log = open(os.path.join(JOBLOGS, b["slug"] + ".log"), "w", encoding="utf-8")
    env = dict(os.environ)
    env.pop("ANTHROPIC_API_KEY", None)
    env.pop("ANTHROPIC_AUTH_TOKEN", None)
    root = os.path.dirname(BRAIN)
    # `reread` reads the book again even if notes exist — for notes made
    # before these jobs moved from Haiku to Sonnet.
    # Read, then guide only if the read worked, then the exit code for the
    # log (_job_failed reads it), then the page. A few lines of Python
    # rather than /bin/sh, which Windows does not have.
    py = sys.executable if sys.platform == "win32" else "python3"
    read = [py, "-u", "brain/tools/books.py", "--read", b["slug"]] + (
        ["--force"] if reread else [])
    guide = [py, "-u", "brain/tools/guide.py", "--book", b["slug"], "--force"]
    runner = ("import subprocess\n"
              f"c = subprocess.call({read!r}) or subprocess.call({guide!r})\n"
              "print('JOB-EXIT:%d' % c, flush=True)\n"
              f"subprocess.call({[py, 'brain/tools/build.py']!r})\n")
    if act_id:
        # The bell's line for this job (activity.py) ends with it.
        done = [py, "brain/tools/activity.py", "finish", act_id]
        runner += (f"subprocess.call({done!r} + (['--failed', '--result', "
                   "'It stopped with an error. Its log is with the guides'] if c "
                   "else ['--result', '%s is ready', '--href', "
                   "'index.html#/school', '--label', 'Open School']))\n"
                   % b["title"].replace("'", "").replace("\\", "")[:80])
    # -I: `-c` puts the working folder (the repo root, run-writable) first
    # on the import path; a planted subprocess/ package there ran in place
    # of the real one (9 Oct audit). The runner needs only the stdlib.
    argv = [py, "-I", "-c", runner]
    # A read and a guide take the best part of an hour. If the Mac sleeps
    # meanwhile, the call in flight loses its connection and its timeout
    # doesn't count the time asleep, so the job hangs rather than failing.
    # caffeinate keeps the machine awake for exactly as long as the job runs.
    if shutil.which("caffeinate"):
        argv = ["caffeinate", "-ims"] + argv
    proc = subprocess.Popen(argv, cwd=root, stdout=log,
                            stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                            env=env, start_new_session=True)
    with _LOCK:
        jobs = {k: v for k, v in _read_json(JOBS, {}).items()
                if _alive(v.get("pid"))}
        jobs[b["slug"]] = {"pid": proc.pid, "started": date.today().isoformat()}
        _write_json(JOBS, jobs)
    return {"started": b["slug"], "title": b["title"]}


def decks(course=None):
    import school
    out = []
    for f in school.files():
        if os.path.splitext(f["name"])[1].lower() not in (".pdf", ".pptx"):
            continue
        low = f["name"].lower()
        if "syllabus" in low or "recommended reading" in low:
            continue
        # Slides only, plus what she added from the School tab.
        if not school.in_guide(f):
            continue
        if course and course.lower() not in f["course"].lower():
            continue
        out.append(f)
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--deck")
    ap.add_argument("--book", metavar="NAME",
                    help="build a guide to one of the course books")
    ap.add_argument("--course")
    ap.add_argument("--all", action="store_true",
                    help="fold new sessions into every course guide "
                         "(self-gating: no call until there is enough)")
    ap.add_argument("--update", action="store_true", help="same as --all")
    ap.add_argument("--now", action="store_true",
                    help="build even when there is little new material")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--rebuild", action="store_true",
                    help="rebuild a course guide from all its sessions (one call)")
    ap.add_argument("--fix-venture", action="store_true",
                    help="take invented Venture facts out of an existing book guide")
    ap.add_argument("--rerender", action="store_true",
                    help="redraw a book guide from its cached content, no call")
    ap.add_argument("--general", action="store_true",
                    help="with --book: the book on its own terms, from the "
                         "notes books.py --general wrote")
    a = ap.parse_args()

    if a.list:
        for f in decks(a.course):
            done = os.path.exists(os.path.join(
                OUT, _slug(f["course"]),
                _slug(os.path.splitext(f["name"])[0]) + ".html"))
            print("  %-56s %s%s" % (f["name"][:56], f["course"][:22],
                                    "   guide ✓" if done else ""))
        return 0
    if a.book and a.fix_venture:
        print(json.dumps(clean_venture_book(a.book, course=a.course or ""),
                         indent=2, ensure_ascii=False))
        return 0
    if a.book:
        print(json.dumps(book_guide(a.book, course=a.course or "",
                                    force=a.force, rerender=a.rerender,
                                    general=a.general),
                         indent=2))
        return 0
    if a.deck:
        print(json.dumps(one(a.deck, force=a.force), indent=2))
        return 0
    if (a.all or a.update) and not a.course:
        # The morning's guide update is one of the morning extras; a course
        # named by hand runs whatever the switch says.
        import usage
        if not usage.switch("extras"):
            print("guides: skipped, the morning extras are off")
            return 0
    if a.all or a.update or a.course:
        names = ([a.course] if a.course
                 else sorted({f["course"] for f in decks()}))
        if not names:
            print("No courses with decks yet.")
            return 0
        any_work = False
        for c in names:
            try:
                r = update(c, force=a.force or a.now, rebuild=a.rebuild)
            except Exception as exc:                     # noqa: BLE001
                print("  %s: failed — %s" % (c[:40], str(exc)[:110]))
                continue
            if r.get("wrote"):
                any_work = True
                print("     → %s  (%d sections)"
                      % (os.path.relpath(r["wrote"], BRAIN), r["sections"]))
            elif r.get("waiting"):
                print("  %s: %d new words across %d session%s — waiting for "
                      "%d. Use --now to build anyway."
                      % (c[:40], r["words"], r["sessions"],
                         "" if r["sessions"] == 1 else "s", r["need"]))
        if not any_work:
            print("\nNothing needed a model call.")
        return 0
    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)

#!/usr/bin/env python3
"""Facts whose date has passed become questions for the owner.

About you, the people file and the career profile hold present-tense facts
with an end date inside them ("away until end of September"). Nothing ages
them out, so the line keeps sounding true weeks after it stopped being. This
sweep finds them with plain code and asks one question per stale statement
in questions.md. It never rewrites a fact: the answer lands the usual way and
Claude corrects the source then.

    python3 brain/tools/stale_facts.py          # add the new questions
    python3 brain/tools/stale_facts.py --dry    # show what it would add

Plain code, no model. The shapes that count, high precision over recall:

  until    "until / till / through / jusqu'au <date>", "returning <date>",
           "for the second half of <month>", once that date has passed
  range    "from <date> to <date>", once the range has ended
  stamped  "currently / right now / for now / this week / this month /
           en ce moment" in a paragraph or line stamped with a date, as in
           "Right now (16 June 2026)" or "as of 16 Jun", older than 21 days
  section  a heading dated with a month and year only, "(June 2026)", more
           than 60 days after that month's last day

What is left alone: a past-tense clause ("lived there until 2019"), anything
that ended more than a year ago (history, not a stale present), and in the
people file everything but Where, Role, Company and the free-text fields
(How, Why, Note, loose notes). Last, Birthday and Met are meant to be past.

A date without a year is read from the day the line was written: the
paragraph's own stamp when it has one, else `git blame`. "Until end of
September" written in September means that September; written in October,
the next one, so it cannot fire early.

One question per paragraph or field. Each is remembered by a fingerprint in
brain/.cache/stale-facts.json and never asked twice, and a fact already
quoted in any question, open or ticked, is not asked again.
"""
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from bisect import bisect_right
from datetime import date, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
BRAIN = os.path.dirname(HERE)
ROOT = os.path.dirname(BRAIN)
sys.path.insert(0, HERE)
import model as M  # noqa: E402

# (path under brain/, kind). The kind picks the plain-words name.
SOURCES = (("about-me.md", "about"), ("people.md", "people"),
           ("career/profile.md", "career"))
QUESTIONS = os.path.join(BRAIN, "questions.md")
CACHE = os.path.join(BRAIN, ".cache", "stale-facts.json")

GRACE = 3            # days past the end before a fact counts as stale
STAMPED_DAYS = 21    # a "right now" paragraph older than this is asked about
SECTION_DAYS = 60    # a "(June 2026)" heading older than this is asked about
HISTORY_DAYS = 365   # ended longer ago than this: history, not a stale fact
QUOTE_MAX = 130

PEOPLE_FIELDS = {"where", "role", "company", "how", "why", "note", "notes"}

_MON = M._MONTH_ALT
# French month and position words, read as English before a date is parsed,
# so "jusqu'à fin septembre" reads as "end of september".
_FR = {"janvier": "january", "février": "february", "fevrier": "february",
       "mars": "march", "avril": "april", "mai": "may", "juin": "june",
       "juillet": "july", "août": "august", "aout": "august",
       "septembre": "september", "octobre": "october",
       "novembre": "november", "décembre": "december",
       "decembre": "december", "fin": "end of", "début": "beginning of",
       "debut": "beginning of", "mi": "mid"}
_FR_RX = re.compile(r"\b(" + "|".join(_FR) + r")\b", re.I)

_TRIGGER = re.compile(
    r"\b(?:until|till|through|returning|due back|back by)\b"
    r"|\bjusqu\s*['’]\s*(?:au|à|a)\b"
    r"|\bfor the (?:first|second) half of\b|\bfor the rest of\b", re.I)
_RANGE = re.compile(
    r"\bfrom\s+(?=[^.;:()]{0,30}?(?:\d|\b(?:" + _MON + r")\b))"
    r"[^.;:()]{1,30}?\s*(?:\bto\b|\buntil\b|\btill\b|\bthrough\b|[–—-])\s*",
    re.I)
_NOWISH = re.compile(
    r"\b(?:current|currently|right now|for now|this week|this month|"
    r"at the moment)\b"
    r"|\ben ce moment\b", re.I)
_SEG = (r"(?:(early|mid|middle of|late|end of|the end of|beginning of|"
        r"the beginning of|start of|the start of)[\s-]+)?")
_MONTH_PHRASE = re.compile(_SEG + r"(" + _MON + r")\b\.?(?:,?\s+(\d{4}))?\b",
                           re.I)
_LEAD = re.compile(r"\s*(?:the\s+|around\s+|about\s+|~\s*|le\s+|la\s+)?", re.I)
# A clause in the past tense is history: "lived there until 2019".
_PAST = re.compile(
    r"\b(?:was|were|had|lived|worked|stayed|grew up|studied|went|left|moved|"
    r"spent|used to|ran|ended|finished|lasted|did)\b", re.I)
# A stamp: a parenthesis that is just a date, with at most a short lead-in
# ("(16 June 2026)", "(her words, 16 Jun)", "(June 2026)"), or "as of <date>".
_PAREN = re.compile(r"\(([^()]{1,60})\)")
_ASOF = re.compile(r"\bas of\s+", re.I)
_HEADING = re.compile(r"^(#{2,4})\s+(.*?)\s*$")
_BULLET = re.compile(r"^\s*(?:[-*+]|\d+\.)\s+")
_FIELD = re.compile(r"^\s*-\s+\*\*([A-Za-z ]+):\*\*\s*(.*)$")


def _fr(s):
    return _FR_RX.sub(lambda m: _FR[m.group(1).lower()], s)


def _month_end(y, mon):
    return M._last_dom(y, mon)


def _date_at(text, pos, anchor, ahead=True):
    """The date a phrase starting at `pos` names, as (date, phrase_end) where
    the date is the END of the window ("end of September" is the 30th), or
    None. `anchor` supplies a missing year; `ahead` leans it forward (an end
    date) or back (a stamp, which is when something was written)."""
    head = text[pos:pos + 48]
    s = _fr(head)
    delta = len(head) - len(s)   # French words read as English shift offsets

    def stop(k):
        return pos + max(0, min(len(head), k + delta))

    p = _LEAD.match(s).end()
    m = M._PROSE_DATE_RX.match(s, p)
    if m:
        d = M.prose_date(m, anchor, ahead=ahead)
        return (d, stop(m.end())) if d else None
    m = _MONTH_PHRASE.match(s, p)
    if not m:
        return None
    seg = (m.group(1) or "").lower().replace("the ", "").strip()
    mon = M._MONTHS[m.group(2).lower()]
    yr = int(m.group(3)) if m.group(3) else None
    if yr is None:
        if ahead:
            # The same rule parse_due uses: this month or later this year,
            # else next year, counted from the day it was written.
            due = M.parse_due(f"{seg} {m.group(2)}".strip(), today=anchor)
            if not due:
                return None
            end = due["end"]
        else:
            yr = anchor.year if mon <= anchor.month else anchor.year - 1
            end = _month_end(yr, mon)
    else:
        due = M.parse_due(f"{seg} {m.group(2)}".strip(), today=date(yr, 1, 1))
        end = due["end"] if due else _month_end(yr, mon)
    return end, stop(m.end())


def _window_end(trigger, end):
    """'for the first half of June' ends on the 15th, not the 30th."""
    if "first half" in trigger.lower():
        return date(end.year, end.month, 15)
    return end


# ── reading the files ──────────────────────────────────────────────────────

def _blame(rel):
    """Line number (1-based) -> the day that line was last written."""
    try:
        out = subprocess.run(
            ["git", "-C", ROOT, "blame", "--line-porcelain", "--", rel],
            capture_output=True, text=True, timeout=60).stdout
    except Exception:
        return {}
    days, n = {}, 0
    for ln in out.splitlines():
        if ln.startswith("author-time "):
            n += 1
            try:
                days[n] = datetime.fromtimestamp(int(ln.split()[1])).date()
            except ValueError:
                pass
    return days


class Unit:
    """One paragraph, bullet or people-file field, lines joined."""

    def __init__(self, rel, kind, section, person, field, lines):
        self.rel, self.kind = rel, kind
        self.section, self.person, self.field = section, person, field
        self.line_nos = [n for n, _ in lines]
        parts, self.offsets, off = [], [], 0
        for _, t in lines:
            t = t.strip()
            self.offsets.append(off)
            parts.append(t)
            off += len(t) + 1
        self.text = " ".join(parts)

    def line_at(self, pos):
        return self.line_nos[max(0, bisect_right(self.offsets, pos) - 1)]


def _units(rel, kind):
    path = os.path.join(BRAIN, rel)
    try:
        raw = open(path, encoding="utf-8").read().split("\n")
    except OSError:
        return [], []
    units, headings = [], []
    section, person = "", ""
    cur, cur_field = [], None
    in_fm = raw[:1] == ["---"]
    fence = False
    started = kind != "people"   # the people file's intro is documentation

    def flush():
        nonlocal cur, cur_field
        if cur and started:
            units.append(Unit(rel, kind, section, person, cur_field, cur))
        cur, cur_field = [], None

    for i, line in enumerate(raw, start=1):
        if in_fm:
            if i > 1 and line.strip() == "---":
                in_fm = False
            continue
        if line.lstrip().startswith("```"):
            fence = not fence
            flush()
            continue
        if fence:
            continue
        h = _HEADING.match(line)
        if h:
            flush()
            section = h.group(2)
            if kind == "people" and len(h.group(1)) == 2:
                person, started = section, True
            headings.append((i, len(h.group(1)), section))
            continue
        s = line.strip()
        if not s or s.startswith(">") or s.startswith("#") or s == "---":
            flush()
            continue
        if s.startswith("|"):
            flush()
            cur = [(i, s)]
            flush()
            continue
        if _BULLET.match(line) and not line.startswith((" ", "\t")):
            flush()
            f = _FIELD.match(line)
            if kind == "people":
                if re.match(r"^\s*-\s+\[[ xX]\]", line):
                    cur_field = "promise"
                elif f:
                    cur_field = f.group(1).strip().lower()
                    line = f.group(2)
            cur = [(i, line)]
            continue
        cur.append((i, line))
    flush()
    if kind == "people":
        units = [u for u in units
                 if u.field is None or u.field in PEOPLE_FIELDS]
    return units, headings


# ── finding stale statements ───────────────────────────────────────────────

def _stamps(text, anchor):
    """Every date the paragraph is stamped with, as (date, label)."""
    out = []
    for m in _PAREN.finditer(text):
        body = m.group(1).strip().rstrip(".").strip()
        # The date must close the parenthesis, after at most a short lead-in
        # ending in a comma or dash: "(her words, 16 Jun)". A range inside
        # parentheses ("(Jan to Mar 2026)") is a span, not a stamp.
        if re.search(r"\bto\b|\s[–-]\s|\d\s*[–-]\s*\d|\.\.", body):
            continue
        for start in [0] + [k.end() for k in re.finditer(r"[,—–]\s*", body)]:
            if start > 30:
                break
            got = _date_at(body, start, anchor, ahead=False)
            if got and got[1] >= len(body) - 1:
                out.append((got[0], body[start:].strip()))
                break
    for m in _ASOF.finditer(text):
        got = _date_at(text, m.end(), anchor, ahead=False)
        if got:
            out.append((got[0], text[m.end():got[1]].strip()))
    return out


def _sentence(text, pos):
    """The sentence holding `pos`, trimmed to something quotable."""
    bounds = [0] + [m.end() for m in re.finditer(r"(?<=[.!?])\s+", text)]
    start = max(b for b in bounds if b <= pos)
    nxt = [b for b in bounds if b > pos]
    end = nxt[0] if nxt else len(text)
    sent = text[start:end].strip()
    rel = pos - start
    if len(sent) > QUOTE_MAX:
        # Keep the clause with the trigger, plus the one after if room.
        cuts = [0] + [m.end() for m in re.finditer(r"[,;:]\s+|\s[—–]\s", sent)]
        a = max(c for c in cuts if c <= rel)
        later = [c for c in cuts if c > rel]
        b = later[0] if later else len(sent)
        if len(later) > 1 and later[1] - a <= QUOTE_MAX:
            b = later[1]
        sent = sent[a:b]
    return sent


def _clean(s):
    s = M._plain(s)
    s = re.sub(r"\s*—\s*", ", ", s)
    s = s.replace("–", "-")
    s = re.sub(r"\s+", " ", s).strip().rstrip(" ,;:.")
    if len(s) > QUOTE_MAX:
        s = s[:QUOTE_MAX].rsplit(" ", 1)[0].rstrip(" ,;:") + "..."
    return s


def _day(d, today):
    lab = f"{d.day} {d.strftime('%B')}"
    return lab if d.year == today.year else f"{lab} {d.year}"


def _anchor(unit, pos, blame, today):
    return blame.get(unit.line_at(pos)) or today


def scan_unit(u, blame, today):
    """The one stale statement a unit holds, as a hit dict, or None."""
    text = u.text
    hits = []
    stamp_anchor = None
    stamps = _stamps(text, _anchor(u, 0, blame, today))
    if stamps:
        stamp_anchor = max(stamps)[0]

    def past_clause(pos):
        clause = re.split(r"[.;!?]\s", text[:pos])[-1]
        return bool(_PAST.search(clause))

    for m in _TRIGGER.finditer(text):
        anchor = stamp_anchor or _anchor(u, m.start(), blame, today)
        got = _date_at(text, m.end(), anchor, ahead=True)
        if not got:
            continue
        end = _window_end(m.group(0), got[0])
        if past_clause(m.start()):
            continue
        hits.append({"shape": "until", "pos": m.start(), "end": end,
                     "phrase": text[m.start():got[1]].strip(),
                     "written": anchor})
    for m in _RANGE.finditer(text):
        anchor = stamp_anchor or _anchor(u, m.start(), blame, today)
        got = _date_at(text, m.end(), anchor, ahead=True)
        if not got or past_clause(m.start()):
            continue
        hits.append({"shape": "range", "pos": m.start(), "end": got[0],
                     "phrase": text[m.start():got[1]].strip(),
                     "written": anchor})
    live = [h for h in hits
            if GRACE < (today - h["end"]).days <= HISTORY_DAYS]
    if live:
        h = min(live, key=lambda h: h["pos"])
        h["quote"] = _clean(_sentence(text, h["pos"]))
        return h
    if stamps:
        m = _NOWISH.search(text)
        newest, label = max(stamps)
        age = (today - newest).days
        if m and STAMPED_DAYS < age <= HISTORY_DAYS:
            return {"shape": "stamped", "pos": m.start(), "end": newest,
                    "phrase": m.group(0), "written": newest,
                    "stamp": label,
                    "quote": _clean(_sentence(text, m.start()))}
    return None


def scan_headings(rel, kind, headings, today):
    out = []
    for line_no, level, title in headings:
        if kind == "people" and level == 2:
            continue
        m = re.search(r"\(\s*(?:as of\s+)?([^()]+?)\s*\)\s*$", title, re.I)
        if not m:
            continue
        body = m.group(1)
        mm = re.fullmatch(r"(" + _MON + r")\.?,?\s+(\d{4})", body, re.I)
        if mm:
            y, mon = int(mm.group(2)), M._MONTHS[mm.group(1).lower()]
            stamp, label = _month_end(y, mon), f"{date(y, mon, 1):%B %Y}"
        else:
            dm = M._PROSE_DATE_RX.fullmatch(body)
            if not dm or not (dm.group(3) or dm.group(6) or dm.group(7)):
                continue
            stamp = M.prose_date(dm, today)
            if not stamp:
                continue
            label = f"{stamp.day} {stamp:%B %Y}"
        age = (today - stamp).days
        if SECTION_DAYS < age <= HISTORY_DAYS:
            out.append({"shape": "section", "rel": rel, "kind": kind,
                        "line": line_no, "end": stamp, "stamp": label,
                        "section": title[:m.start()].strip()})
    return out


# ── turning a hit into a question ──────────────────────────────────────────

def _where(kind, person):
    if kind == "people":
        return f"Your notes on {person}", "say"
    if kind == "career":
        return "Your career profile", "says"
    return "About you", "says"


def question(h, today):
    if h["shape"] == "section":
        name = {"about": "About you", "career": "your career profile"}.get(
            h["kind"], "the people list")
        return (f"The part of {name} headed “{_clean(h['section'])}” is dated "
                f"{h['stamp']}, more than two months ago. Is it still right, "
                f"or has something in it changed?")
    where, says = _where(h["kind"], h.get("person"))
    # A bullet led by a bold name ("**Garden** - ...") is about that thing;
    # name it when the quote alone would not say what it is about.
    subj = h.get("subject")
    if subj and _norm(subj) not in _norm(h["quote"]):
        where = f"{where}, on {subj},"
    if h["shape"] == "stamped":
        stamp = _clean(h["stamp"])
        dated = ("" if _norm(stamp) in _norm(h["quote"])
                 else f", dated {stamp}")
        return (f"{where} still {says} “{h['quote']}”{dated}. Is that still "
                f"true, and if not, what is true now?")
    return (f"{where} still {says} “{h['quote']}” (noted "
            f"{_day(h['written'], today)}), and that date has passed. "
            f"What is true now?")


def _norm(s):
    s = M._plain(s or "").lower()
    s = re.sub(r"[“”\"'’‘()\[\]*_.,;:!?—–-]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _reworded(h, quote, still_open):
    """Is an unanswered question about the same place already asking this
    fact? The line it quotes can change under it: an About-you line on where
    her parents were gained "Noted 16 September and not yet updated:" and was asked a second
    time (8 Oct), with the first still open. Most of the quote's words in
    one open question from the same place counts; answered ones never do,
    so a fact that goes stale again after her answer is asked again."""
    where = _norm(_where(h["kind"], h.get("person"))[0])
    words = {w for w in quote.split() if len(w) > 3}
    if len(words) < 4:
        return False
    for q in still_open:
        if q.startswith(where) and \
                len(words & set(q.split())) >= 0.7 * len(words):
            return True
    return False


def fingerprint(h):
    key = "|".join([h["rel"], h["shape"], h.get("person") or "",
                    _norm(h.get("quote") or h.get("section"))])
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]


def scan(today=None):
    today = today or date.today()
    hits = []
    for rel, kind in SOURCES:
        units, headings = _units(rel, kind)
        if not units and not headings:
            continue
        blame = _blame(os.path.join("brain", rel))
        for u in units:
            h = scan_unit(u, blame, today)
            if h:
                lead = re.match(r"(?:[-*+]|\d+\.)\s+\*\*([^*]{1,40})\*\*",
                                u.text)
                h.update(rel=rel, kind=kind, person=u.person,
                         section=u.section, line=u.line_at(h["pos"]),
                         subject=_clean(lead.group(1)).rstrip(":")
                         if lead and kind != "people" else None)
                hits.append(h)
        hits += scan_headings(rel, kind, headings, today)
    for h in hits:
        h["question"] = question(h, today)
        h["fp"] = fingerprint(h)
    return hits


def _load_cache():
    try:
        with open(CACHE, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data.get("asked"), dict) else {"asked": {}}
    except (OSError, ValueError, AttributeError):
        return {"asked": {}}


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--dry", action="store_true",
                    help="print what would be added, write nothing")
    ap.add_argument("--today", help="pretend today is YYYY-MM-DD (testing)")
    a = ap.parse_args()
    today = M.parse_date(a.today) if a.today else date.today()

    hits = scan(today)
    cache = _load_cache()
    try:
        qtext = open(QUESTIONS, encoding="utf-8").read()
    except OSError:
        qtext = ""
    asked = re.findall(r"^\s*- \[[ xX]\] (.+)$", qtext, re.M)
    asked_norm = [_norm(q) for q in asked]
    still_open = [_norm(q) for q in re.findall(r"^\s*- \[ \] (.+)$", qtext,
                                               re.M)]

    new = []
    for h in hits:
        why = None
        quote = _norm(h.get("quote") or "")
        if h["fp"] in cache["asked"]:
            why = "asked before"
        elif h["question"] in asked:
            why = "same line already there"
        elif len(quote) >= 15 and any(quote in q for q in asked_norm):
            why = "already quoted in a question"
        elif _reworded(h, quote, still_open):
            why = "an open question already asks this"
        h["skip"] = why
        if not why and h["question"] not in [n["question"] for n in new]:
            new.append(h)

    if a.dry:
        for h in hits:
            where = h["rel"] + ":" + str(h["line"])
            print(f"[{h['shape']}] {where}"
                  + (f"  (skip: {h['skip']})" if h["skip"] else ""))
            print(f"    - [ ] {h['question']}")
        print(f"stale facts: {len(hits)} found, {len(new)} would be asked")
        return 0

    if new:
        with open(QUESTIONS, "a", encoding="utf-8") as f:
            if qtext and not qtext.endswith("\n"):
                f.write("\n")
            for h in new:
                f.write(f"- [ ] {h['question']}\n")
        for h in new:
            cache["asked"][h["fp"]] = {"on": today.isoformat(),
                                       "question": h["question"]}
        os.makedirs(os.path.dirname(CACHE), exist_ok=True)
        tmp = CACHE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(cache, f, indent=1, ensure_ascii=False)
        os.replace(tmp, CACHE)
    print(f"stale facts: {len(hits)} found, {len(new)} new question(s)")
    for h in new:
        print(f"  - [ ] {h['question']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

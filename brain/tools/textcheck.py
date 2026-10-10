#!/usr/bin/env python3
"""Her hard writing rules, checked by code: em dashes, the AI tells, limits.

Two of her most common corrections are countable, so code counts them
instead of a model promising to: an em dash in text someone else reads (four
of the six failed draft tests on 27 Sep 2026), and a limit she named that the
result missed. A short list of AI tells rides along, the ones a regex finds
with almost no false alarms.

    import textcheck
    textcheck.problems(text)                          # [] when clean
    textcheck.problems(text, limit=(300, "words"))
    textcheck.limit_from("Keep it under 300 words")   # (300, "words")

    python3 brain/tools/textcheck.py                  # the self-test
    python3 brain/tools/textcheck.py FILE ...         # lint files

Precision beats recall here. A word her rules ban that is also a real term
in her work stays out: "robust" is numerics vocabulary in Venture, "customer
journey" is school vocabulary, "navigate to" belongs in a README. A warning
that cries wolf forty times a day gets ignored, and then so does the em dash
one. The judgement tells (aphorisms, triplets, mirrored contrasts) belong to
drafteval.py's judge, not to a regex.

Leading front matter and fenced code are never checked. Nothing here raises:
odd input gives [] or None.
"""

import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BRAIN = os.path.dirname(HERE)
CASES = os.path.join(BRAIN, "evals", "corrections.md")

EM = "\u2014"
EN = "\u2013"

_FRONT = re.compile(r"\A\ufeff?---[ \t]*\n(.*?)\n---[ \t]*(?:\n|\Z)", re.S)
_FENCE = re.compile(r"^[ \t]*(`{3,}|~{3,})[^\n]*\n.*?(?:^[ \t]*\1[ \t]*$|\Z)",
                    re.S | re.M)


def split_frontmatter(text):
    """(meta, body): the leading `---` block as a lowercase-keyed dict, and
    the rest. No block gives ({}, text)."""
    m = _FRONT.match(text or "")
    if not m:
        return {}, text or ""
    meta = {}
    for line in m.group(1).splitlines():
        if ":" in line and not line.startswith((" ", "\t")):
            k, v = line.split(":", 1)
            meta[k.strip().lower()] = v.strip().strip('"').strip("'")
    return meta, text[m.end():]


def _prose(body):
    """The words a reader reads: no code, no link targets, no HTML comments,
    curly apostrophes and French non-breaking spaces made plain so one
    pattern covers both spellings."""
    t = _FENCE.sub("\n", body)
    # By find, not ".*?": every unclosed "<!--" re-scanned to the end.
    out, i = [], 0
    while True:
        a = t.find("<!--", i)
        b = t.find("-->", a + 4) if a >= 0 else -1
        if b < 0:
            out.append(t[i:])
            break
        out.append(t[i:a] + " ")
        i = b + 3
    t = "".join(out)
    t = re.sub(r"`[^`\n]+`", " ", t)
    t = re.sub(r"\]\([^)\s]*\)", "]", t)
    t = re.sub(r"https?://\S+", " ", t)
    return (t.replace("\u2019", "'").replace("\u2018", "'")
             .replace("\u00a0", " ").replace("\u202f", " "))


# -- the tells ---------------------------------------------------------------
# (what it is, its plural, what to do, patterns); {it} becomes it or them. Every pattern is case-insensitive
# unless it opens with (?-i:...). One problem line per kind, not per hit.

_SENT = r"(?:^[ \t>*_#-]*|(?<=[.!?]) +)"          # start of a sentence

TELLS = [
    ("word her rules ban", "words her rules ban", "use the plain word or cut {it}", [
        r"\bdelv(?:e|es|ed|ing)\b", r"\btapestr(?:y|ies)\b",
        r"\btestament to\b", r"\bplethora\b", r"\bmyriad\b", r"\bbespoke\b",
        r"\bmeticulous(?:ly)?\b", r"\bintricate(?:ly)?\b", r"\brealms?\b",
        r"\bseamless(?:ly)?\b", r"\beffortless(?:ly)?\b", r"\bever-evolving\b",
        r"\bgame[- ]chang(?:er|ers|ing)\b",
        r"\bcutting-edge\b",                  # a blade's "cutting edge" is fine
        r"\btransformative\b", r"\bholistic(?:ally)?\b",
        r"(?-i:\bpivotal\b)",                 # not Pivotal, the company
        r"\bnuanced\b", r"\bembark(?:s|ed|ing)?\b",
        r"\bempower(?:s|ed|ing)?\b", r"\bstreamlin(?:e|es|ed|ing)\b",
        r"\bspearhead(?:s|ed|ing)?\b", r"\bresonat(?:e|es|ed|ing)\b",
        r"\bat the intersection of\b",
        # Verbs only: the noun ("an underscore", "a showcase", "the
        # leverage ratio", "a climbing harness") is innocent.
        r"\bunderscor(?:es|ed|ing)\b",
        r"\bunderscore (?:the|how|that|why|our|its|their|this)\b",
        r"\bshowcas(?:es|ed|ing)\b",
        r"\bshowcase (?:the|our|their|its|your|how|what|this)\b",
        r"\bleverag(?:es|ing)\b",
        r"\b(?:to|we|you|they|can|will|could) leverage\b",
        r"\bharness(?:es|ed|ing)? the (?:power|potential|energy)\b",
        r"\bunlock(?:s|ed|ing)? (?:the |your |our |their |its |new )?"
        r"(?:potential|value|growth|power|insights?|opportunit(?:y|ies))\b",
        r"\belevat(?:e|es|ing) (?:your|our|the|their|its|this)\b",
        # Lowercase only, so the architect Norman Foster is safe.
        r"(?-i:\bfoster(?:s|ed|ing)?\b)(?! (?:care|home|parent|famil|child|kid))",
        # "Competitive landscape" and "market landscape" are the standard
        # MBA terms, a slide title in every class deck, so they stay.
        r"\b(?:digital|tech|technology|evolving|ever-evolving|ever-changing|media"
        r"|startup|AI) landscape\b",
    ]),
    ("formal connective", "formal connectives", "drop {it}; a sentence works without one", [
        r"\bmoreover\b", r"\bfurthermore\b", r"\badditionally\b",
        r"\bnevertheless\b", r"\balbeit\b", r"\bcrucially\b",
        _SENT + r"(?P<w>thus|hence|indeed|notably)\b",
    ]),
    ("stock phrase", "stock phrases", "say the specific thing instead", [
        r"\bat a glance\b", r"\bin one place\b",
        r"\bI hope (?:this|my) (?:e-?mail |message |note |letter )?finds you well\b",
        r"\bj'esp[eè]re que (?:ce|mon) (?:message|mail|e-mail|courriel|mot) "
        r"(?:vous|te) trouve",
        r"\bwhat (?:nobody|no one) tells you\b",
        r"\bthe (?:quiet|simple) (?:joy|pleasure|satisfaction) of\b",
        r"\bthere(?:'s| is) something (?:satisfying|magical|special|beautiful) about\b",
        r"\binto people's hands\b", r"\b(?:out|off) into the wild\b",
        r"\blearning in public\b",
        # Her meta-narration correction on the wine letter (Aug 2026); the
        # 27 Sep eval rewrite kept it, so it is checked by name.
        r"\bfil conducteur\b",
    ]),
    ("throat-clearing opener", "throat-clearing openers", "start with the content", [
        r"\bit(?:'s| is) worth (?:noting|mentioning|pointing out)\b",
        r"\bit(?:'s| is) important to (?:note|understand|remember|recogni[sz]e)\b",
        r"\blet's (?:take a (?:closer )?look at|dive in)\b",
        r"\bil (?:est important|convient) de (?:noter|souligner|rappeler)\b",
        _SENT + r"(?P<w>in a world where|in today's (?:fast-paced|digital|ever-changing|rapidly)"
        r"|dans un monde o[uù])\b",
    ]),
    ("rhetorical question answered by the next line",
     "rhetorical questions answered by the next line", "state the point", [
        _SENT + r"(?P<w>the (?:result|answer|catch|kicker|twist|upshot|secret|takeaway)\?)",
        _SENT + r"(?P<w>(?:le r[ée]sultat|la r[ée]ponse) ?\?)",
        r"\bhere's the (?:thing|kicker|catch)\b",
        r"\bwhy does (?:this|it|that) matter\?",
    ]),
    ("\"not X, but Y\" construction", "\"not X, but Y\" constructions",
     "say what it is and stop", [
        r"\bnot (?:only|just|merely|simply)\b[^.!?\n]{1,80}?\bbut\b",
        r"\b(?:it|this|that)(?:'s| is) not\b[^.!?;\n]{1,60}?[,;:]\s*(?:it|this|that)(?:'s| is)\b",
        r"\b(?:it|this|that) isn't\b[^.!?;\n]{1,60}?[,;:]\s*(?:it|this|that)(?:'s| is)\b",
        r"\bmore than (?:just )?an? [^.!?,;\n]{1,40}[,;:]\s*(?:it|this|that)(?:'s| is)\b",
        r"\bce n'est pas\b[^.!?;\n]{1,60}?[,;:]\s*c'est\b",
        r"\bil ne s'agit pas\b[^.!?;\n]{1,60}?[,;:]\s*(?:il s'agit|c'est)\b",
    ]),
    ("closing coda", "closing codas", "end on the last real point", [
        r"\bin conclusion\b", r"\bat the end of the day\b", r"\bto sum up\b",
        r"\bin summary,", r"\ben conclusion\b",
    ]),
    ("leftover from a chat reply", "leftovers from a chat reply", "delete {it}", [
        r"\A\s*(?P<w>sure|certainly|of course|absolutely)[!,.]",
        r"\A\s*(?P<w>here(?:'s| is) (?:a |an |the |your )?(?:revised|rewritten|updated"
        r"|polished|cleaned[- ]up|tightened|shorter|final|new|edited)\b[^\n]{0,40}?"
        r"(?:version|draft|rewrite|text|email|message))",
        r"\bI hope this helps\b", r"\bas an AI\b",
    ]),
]

_CODA_START = re.compile(r"^(ultimately|overall|in short|all in all|en somme),",
                         re.I)


def _compile():
    out = []
    for one, many, fix, pats in TELLS:
        out.append((one, many, fix, [re.compile(p, re.I | re.M) for p in pats]))
    return out


_TELLS = _compile()
_GONE = None


def _gone_phrases():
    """The phrases she has already cut from a real draft: the Gone lists in
    brain/evals/corrections.md, the same lists drafteval.py scores against.
    Only phrases of four words or more: "did not happen" is ordinary English,
    "the cost of guessing wrong is the project" is not. Read once."""
    global _GONE
    if _GONE is None:
        _GONE = []
        try:
            with open(CASES, encoding="utf-8") as f:
                for line in f:
                    m = re.match(r"^- \*\*Gone:\*\*\s*(.*)$", line.strip())
                    if not m:
                        continue
                    for p in m.group(1).split("|"):
                        p = p.strip().replace("\u2019", "'")
                        if len(p.split()) >= 4 and p.lower() not in _GONE:
                            _GONE.append(p.lower())
        except OSError:
            pass
    return _GONE


def _s(n, one, many=None):
    return f"{n:,} {one if n == 1 else (many or one + 's')}"


def _quote(hits):
    shown = [f'"{h}"' for h in hits[:4]]
    if len(hits) > 4:
        shown.append(f"and {len(hits) - 4} more")
    return ", ".join(shown)


_MONTH = (r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?"
          r"|aug(?:ust)?|sept?(?:ember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?"
          r"|janv(?:ier)?|f[ée]vr?(?:ier)?|mars|avr(?:il)?|mai|juin|juil(?:let)?|ao[uû]t"
          r"|septembre|octobre|novembre|d[ée]c(?:embre)?|ene(?:ro)?|febrero|marzo"
          r"|abr(?:il)?|mayo|junio|perry|ago(?:sto)?|septiembre|octubre|noviembre"
          r"|dic(?:iembre)?)\.?")
_RANGE_FROM = re.compile(r"(?:\d[\d,.)]*|\b" + _MONTH + r")$", re.I)
_RANGE_TO = re.compile(r"(?:\d|" + _MONTH + r"$|(?:present|now|today|aujourd|pr[ée]sent"
                       r"|actualidad|hoy)\b)", re.I)


def _spaced_en(prose):
    """Spaced en dashes standing in for an em dash. A range is the en dash's
    own job and stays: "Feb 2018 – Jul 2025", "2025 – Present", "9 – 12"."""
    n = 0
    # Bounded: "\S+" went quadratic on a long unbroken run (a pasted link
    # or base64: 26 s on 80k characters, 9 Oct audit).
    for m in re.finditer(r"(\S{1,60}) " + EN + r" (\S{1,60})", prose):
        if not (_RANGE_FROM.search(m.group(1).lstrip("(")) and
                _RANGE_TO.match(m.group(2))):
            n += 1
    return n


def _dashes(prose):
    em = prose.count(EM) + len(re.findall(r"&(?:mdash|#8212|#x2014);", prose, re.I))
    en = _spaced_en(prose)
    dd = len(re.findall(r"(?<=\S) -- (?=\S)", prose))
    if not (em or en or dd):
        return None
    parts = []
    if em:
        parts.append(_s(em, "em dash", "em dashes"))
    if en:
        parts.append(_s(en, "spaced en dash", "spaced en dashes") + f' (" {EN} ") standing in for one')
    if dd:
        parts.append(_s(dd, "double hyphen") + ' (" -- ") standing in for one')
    which = "that sentence" if em + en + dd == 1 else "those sentences"
    return " and ".join(parts) + f": rewrite {which} with commas, colons or full stops"


def _tells(prose):
    out = []
    for kind, kinds, fix, pats in _TELLS:
        found = []
        for rx in pats:
            for m in rx.finditer(prose):
                h = (m.groupdict().get("w") or m.group(0)).strip().lower()
                found.append((m.start(), re.sub(r"\s+", " ", h)[:50]))
        hits = []
        for _, h in sorted(found):              # in the order she reads them
            if h not in hits:
                hits.append(h)
        if kind == "closing coda":
            paras = [p.strip() for p in re.split(r"\n\s*\n", prose) if p.strip()]
            real = [p for p in paras if len(p.split()) > 6]
            if real:
                m = _CODA_START.match(real[-1].lstrip("*_>#- \t"))
                if m and m.group(1).lower() not in hits:
                    hits.append(m.group(1).lower())
        if hits:
            it = "it" if len(hits) == 1 else "them"
            out.append(f"{_s(len(hits), kind, kinds)} ({_quote(hits)}): "
                       + fix.replace("{it}", it))
    low = prose.lower()
    gone = [g for g in _gone_phrases() if g in low]
    if gone:
        out.append(f"{_s(len(gone), 'phrase')} she already cut from a draft "
                   f"({_quote(gone)}): reword {'it' if len(gone) == 1 else 'them'} the way she did")
    n = len(re.findall(r"\bactually\b", prose, re.I))
    if n > 1:
        out.append(f'"actually" {n} times: keep at most one, where it corrects '
                   "an expectation")
    dots = len(re.findall(r"(?<![\[(])(?:\.{3,}|\u2026)(?![\])])", prose))
    if dots:
        out.append(f"{_s(dots, 'ellipsis', 'ellipses')}: finish the sentence "
                   "instead")
    return out


# -- limits ------------------------------------------------------------------

def _unit(u):
    u = (u or "").strip().lower()
    if u.startswith(("word", "mot", "palabra", "w")):
        return "words"
    if u.startswith(("char", "caract", "signe", "c")):
        return "characters"
    return None


def count(text, unit):
    """Words or characters in what the reader gets: front matter out, code
    kept (a README's reader reads its code). Words skip the markdown
    markers (#, -, >, 1.) and count link text, not link targets."""
    _, body = split_frontmatter(text)
    if unit == "characters":
        return len(body.strip())
    t = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", body)
    t = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", t)
    t = re.sub(r"<[^>\n]+>", " ", t)
    t = re.sub(r"(?m)^[ \t]*(?:(?:#{1,6}|>|[-*+]|\d+[.)])[ \t]+)+", "", t)
    return sum(1 for tok in t.split() if re.search(r"\w", tok))


def _limit_problem(text, limit):
    n, unit = limit
    if isinstance(n, str):
        n = int(re.sub(r"[^\d]", "", n))
    n, unit = int(n), _unit(unit)
    if not unit or n <= 0:        # slides, minutes: not countable from text
        return None
    have = count(text, unit)
    if have <= n:
        return None
    one = unit[:-1]
    return f"{have:,} {unit} against a {n:,}-{one} limit: cut {have - n:,}"


def problems(text, limit=None):
    """Plain-English problems with a text someone else will read, each
    saying what to fix. [] when clean, and on any odd input."""
    try:
        if isinstance(text, bytes):
            text = text.decode("utf-8", "replace")
        if not isinstance(text, str) or not text.strip():
            return []
        _, body = split_frontmatter(text)
        prose = _prose(body)
        out = []
        d = _dashes(prose)
        if d:
            out.append(d)
        if limit:
            try:
                lp = _limit_problem(text, limit)
                if lp:
                    out.append(lp)
            except (TypeError, ValueError):
                pass
        out += _tells(prose)
        return out
    except Exception:                                 # noqa: BLE001
        return []


_NUM = (r"(?P<num>\d+(?:[.,]\d+)?\s?k(?![a-z])"
        r"|\d{1,3}(?:[,.\u00a0\u202f ]\d{3})+(?!\d)|\d+)")
# Slides, minutes and pages are matched so they are not mistaken for
# anything else, then dropped: a slide count or a talk length cannot be
# counted from text. A deck tool can count slides itself later.
_UNITS = (r"(?P<unit>words?|mots?|palabras?|characters?|chars?|caract[eè]res?"
          r"|signes?|slides?|diapos?|diapositives?|minutes?|mins?|pages?)")
_LIMIT_RX = [
    re.compile(r"(?<![\w.,])" + _NUM + r"[ \t]*(?P<hy>-[ \t]*)?" + _UNITS + r"\b", re.I),
    re.compile(r"\b(?P<unit>word|character|char)s?[ \t]+(?:count|limit)[ \t]*"
               r"(?:of|:|is|=)?[ \t]*(?:max(?:imum)?[ \t]*)?" + _NUM, re.I),
]
_MAX_BEFORE = re.compile(r"(?:\bno|\bnot|\bnever|\bpas|ne pas)[ \t]+(?:more than|over|above"
                         r"|longer than|plus de|d[ée]passer)[ \t]*$")
_MIN_BEFORE = re.compile(r"(?:at least|minimum(?: of)?|\bmin\.?|au moins|au minimum|≥|>=|>"
                         r"|more than|\bover|above|plus de|longer than|no fewer than"
                         r"|not less than|pas moins de)[ \t]*$")
_APPROX_BEFORE = re.compile(r"(?:about|around|roughly|approximately|approx\.?|~|environ"
                            r"|à peu près|unos|unas)[ \t]*$")
_PER_AFTER = re.compile(r"^[ \t]*(?:per|each|every|par|chacun|chacune|pour chaque|por)\b")


def _num(s, hyphen):
    s = s.strip().lower()
    if s.endswith("k"):
        return int(round(float(s[:-1].strip().replace(",", ".")) * 1000))
    if hyphen and " " in s:       # "write 3 300-word posts" is 300, not 3300
        s = s.split()[-1]
    return int(re.sub(r"[,.\u00a0\u202f ]", "", s))


def limit_from(text):
    """The limit an instruction states, as (n, "words"|"characters"), or
    None. "under 300 words", "max 1,500 characters", "≤ 150 mots",
    "1500 caractères", "a 200-word bio" all count; "at least 500 words" is a
    minimum and does not. With several, hard limits beat "about" ones, and
    the tightest wins, a word counted as six characters to compare units."""
    try:
        if isinstance(text, bytes):
            text = text.decode("utf-8", "replace")
        if not isinstance(text, str):
            return None
        t = text.replace("\u00a0", " ").replace("\u202f", " ")
        found = []
        for rx in _LIMIT_RX:
            for m in rx.finditer(t):
                unit = _unit(m.group("unit"))
                if not unit:
                    continue
                before = t[max(0, m.start() - 30):m.start()].lower()
                if _PER_AFTER.match(t[m.end():m.end() + 20]):
                    continue
                if _MIN_BEFORE.search(before) and not _MAX_BEFORE.search(before):
                    continue
                try:
                    n = _num(m.group("num"), m.groupdict().get("hy"))
                except ValueError:
                    continue
                if n > 0:
                    found.append((bool(_APPROX_BEFORE.search(before)), n, unit))
        if not found:
            return None
        hard = [f for f in found if not f[0]] or found
        _, n, unit = min(hard, key=lambda f: f[1] * (6 if f[2] == "words" else 1))
        return (n, unit)
    except Exception:                                 # noqa: BLE001
        return None


# -- self-test ---------------------------------------------------------------

def _selftest():
    clean = ("Hi Frankie,\n\nCould you send the six benchmark outputs by "
             "Friday? We will build the animations from them.\n\nThanks,\n"
             "the owner")
    assert problems(clean) == [], problems(clean)

    p = problems("We met on Friday " + EM + " it went well " + EM + " and then left.")
    assert p and p[0].startswith("2 em dashes:"), p
    p = problems("We met on Friday " + EN + " it went well.")
    assert "spaced en dash" in p[0], p
    assert problems("Pages 9" + EN + "12 cover it.") == []      # a range is fine
    rng = ("School | 2025 " + EN + " 2027\nAvature (Feb 2018 " + EN + " Jul 2025)\n"
           "Office, Jun " + EN + " Aug 2016\nMBA | 2025 " + EN + " Present")
    assert problems(rng) == [], problems(rng)
    assert problems("Marketing " + EN + " 2024 plan")[0].startswith("1 spaced")
    p = problems("French (fluent " + EN + " C1)")
    assert p and p[0].startswith("1 spaced en dash"), p

    # Front matter and fenced code are not text a reader reads.
    fm = "---\nkind: email\nsubject: Notes " + EM + " part 2\n---\nAll good here.\n"
    assert problems(fm) == [], problems(fm)
    code = "Run this:\n\n```\necho 'a " + EM + " b seamless'\n```\n\nThen wait."
    assert problems(code) == [], problems(code)

    p = problems("It gives you everything at a glance, seamlessly.")
    assert any(s.startswith("1 stock phrase") for s in p), p
    assert any("word her rules ban" in s and '"seamlessly"' in s for s in p), p
    p = problems("I hope this email finds you well. Moreover, the delve was fun.")
    assert any("formal connective" in s for s in p), p
    p = problems("It's not a tool, it's a habit.")
    assert any("not X, but Y" in s for s in p), p
    p = problems("Ce n'est pas un outil, c'est une habitude.")
    assert any("not X, but Y" in s for s in p), p
    p = problems("We shipped. The result? Ten new users.")
    assert any("rhetorical" in s for s in p), p
    assert problems("What was the result? Tell me.") == []
    p = problems("Here's a revised version of the email:\n\nHi Ana, see you Friday.")
    assert any("leftover" in s for s in p), p
    p = problems("Mon fil conducteur est simple.")
    assert any("fil conducteur" in s for s in p), p
    p = problems("Remember: the cost of guessing wrong is the project.")
    assert any("already cut" in s for s in p), p
    p = problems("It actually works, and it actually ships.")
    assert any('"actually" 2 times' in s for s in p), p
    p = problems("So we waited... and waited.")
    assert any("ellipsis" in s for s in p), p
    para = "We tested it with eleven labs over the summer and the results held up."
    p = problems(para + "\n\nUltimately, the labs want faster runs on big grids.")
    assert any("closing coda" in s for s in p), p
    assert problems("Norman Foster designed it. We went to foster care.") == []
    assert problems("Keep the cutting edge away. Pivotal ran the competitive landscape.") == []

    words = "word " * 312
    assert problems(words, limit=(300, "words")) == \
        ["312 words against a 300-word limit: cut 12"]
    assert problems(words, limit=(312, "words")) == []
    assert count("# Title\n\n- one two\n> 1. [three](http://x.y/z)", "words") == 4
    assert problems("x" * 1612, limit=(1500, "characters")) == \
        ["1,612 characters against a 1,500-character limit: cut 112"]
    assert problems(words, limit=(5, "slides")) == []
    assert problems("---\nkind: note\n---\none two three", limit=(3, "words")) == []

    assert limit_from("Write a bio in 200 words") == (200, "words")
    assert limit_from("keep it under 300 words please") == (300, "words")
    assert limit_from("max 1,500 characters") == (1500, "characters")
    assert limit_from("≤ 150 mots, en français") == (150, "words")
    assert limit_from("1500 caractères espaces compris") == (1500, "characters")
    assert limit_from("1\u202f500 signes maximum") == (1500, "characters")
    assert limit_from("a 200-word summary") == (200, "words")
    assert limit_from("between 150 and 200 words") == (200, "words")
    assert limit_from("at least 500 words") is None
    assert limit_from("no more than 250 words") == (250, "words")
    assert limit_from("10 slides, 40 words per slide") is None
    assert limit_from("a 10-minute talk") is None
    assert limit_from("about 400 words, and never over 300 words") == (300, "words")
    assert limit_from("under 1,300 characters, about 300 words") == (1300, "characters")
    assert limit_from("Draft the email to Frankie") is None

    for odd in (None, 42, b"\xff\xfe", "", object()):
        assert problems(odd) == [] and limit_from(odd) is None
    assert problems("hi", limit=("lots", "words")) == []
    return True


def _main(argv):
    if not argv:
        _selftest()
        print("textcheck.py: self-test passed")
        return 0
    bad = 0
    for path in argv:
        try:
            with open(path, encoding="utf-8") as f:
                text = f.read()
        except OSError as exc:
            print(f"{path}: unreadable ({exc})")
            bad += 1
            continue
        meta, body = split_frontmatter(text)
        if meta.get("subject"):         # the subject is read too
            text = meta["subject"] + "\n\n" + body
        for p in problems(text):
            print(f"  {path}: {p}")
            bad += 1
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))

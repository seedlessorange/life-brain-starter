#!/usr/bin/env python3
"""The slides that are pictures: look at them, so the guide can read them.

    python3 brain/tools/slides.py "<deck.pdf>"            # which slides it would look at
    python3 brain/tools/slides.py "<deck.pdf>" --describe # look, and cache what they show

Text extraction reads what is typed on a slide. Her decks are mostly
something else: a framework drawn as boxes, a chart, a photo with a caption,
a screenshot of a case. Managing Innovation session 2 is 382 pages and 325 of
them carry fewer than thirty words, so the guide built from its text was
built from a tenth of the class.

So a slide with almost no text is rendered as an image and Claude says what
it shows: the words on it, what the chart or diagram means, the point it
makes. Those descriptions go back into the deck's text in page order, and
the guide is built from that, unchanged.

Three things keep it affordable, because a picture costs far more than its
words did:

- Only thin slides are looked at. A slide whose text already says it all
  gets no image.
- Animation builds are collapsed. A deck exported with its animations is the
  same slide five times, each with one more bullet; only the last one of a
  run is looked at. Identical slides anywhere (the agenda that comes back
  every section) are looked at once.
- The answer is cached per file content, forever. A deck downloaded twice,
  or a guide rebuilt next month, never pays again.

Nothing here decides what reaches a model on its own: guide.py calls it only
after the confidential-name check, and it checks again itself.
"""
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
BRAIN = os.path.dirname(HERE)
if HERE not in sys.path:
    sys.path.insert(0, HERE)

CACHE = os.path.join(BRAIN, "school", "guides", ".data", "_slides")
THIN_WORDS = 30          # under this, the text is not the slide
MAX_IMAGES = {"full": 400, "careful": 40}   # per deck, by the budget mode in
                         # config "ai"; past it the deck is sampled evenly
PER_CALL = 10            # images per model call
WIDTH = 1000             # px — chart labels stay legible, ~750 tokens each
BUILD_DIFF = 7.0         # mean grey-level change under which the next page
                         # is the same slide with one more thing on it
SAME_DIFF = 1.5          # effectively identical
BLANK_SPREAD = 4.0       # a plain background with nothing on it


def _pages(pdf):
    """Each page's text, split on pdftotext's form feeds."""
    try:
        r = subprocess.run(["pdftotext", "-layout", pdf, "-"],
                           capture_output=True, text=True, timeout=180)
    except (OSError, subprocess.SubprocessError):
        return []
    if r.returncode != 0:
        return []
    pages = r.stdout.split("\f")
    if pages and not pages[-1].strip():
        pages = pages[:-1]
    return pages


def _words(text):
    return len(re.findall(r"[A-Za-zÀ-ÿ]{2,}", text or ""))


def _thumbs(pdf, n):
    """{page: bytes} — every page as a 64x36 grey thumbnail, in one render."""
    out = {}
    with tempfile.TemporaryDirectory() as td:
        try:
            subprocess.run(["pdftoppm", "-gray", "-scale-to-x", "64",
                            "-scale-to-y", "36", pdf,
                            os.path.join(td, "t")],
                           capture_output=True, timeout=300)
        except (OSError, subprocess.SubprocessError):
            return out
        for fn in os.listdir(td):
            m = re.search(r"-(\d+)\.pgm$", fn)
            if not m:
                continue
            with open(os.path.join(td, fn), "rb") as f:
                raw = f.read()
            # binary PGM: "P5\n64 36\n255\n" then the pixels
            parts = raw.split(b"\n", 3)
            if len(parts) == 4 and parts[0] == b"P5":
                out[int(m.group(1))] = parts[3]
    return out


def _diff(a, b):
    if not a or not b or len(a) != len(b):
        return 255.0
    return sum(abs(x - y) for x, y in zip(a, b)) / len(a)


def _spread(a):
    if not a:
        return 0.0
    mean = sum(a) / len(a)
    return (sum((x - mean) ** 2 for x in a) / len(a)) ** 0.5


def _cap():
    try:
        with open(os.path.join(BRAIN, "config.json"), encoding="utf-8") as f:
            mode = str(json.load(f).get("ai") or "full").lower()
    except (OSError, ValueError):
        mode = "full"
    return MAX_IMAGES.get(mode, MAX_IMAGES["careful"])


def plan(pdf):
    """Which pages to look at, and which pages borrow another's look.

    Returns {"pages": n, "thin": [...], "look": [...], "same_as": {p: q},
    "sampled": bool}. Page numbers start at 1, as the deck shows them."""
    pages = _pages(pdf)
    n = len(pages)
    thin = [i + 1 for i, t in enumerate(pages) if _words(t) < THIN_WORDS]
    if not thin:
        return {"pages": n, "thin": [], "look": [], "same_as": {},
                "sampled": False}
    th = _thumbs(pdf, n)
    thin_set = set(thin)
    look, same_as, kept = [], {}, []
    for p in thin:
        img = th.get(p)
        if img is not None and _spread(img) < BLANK_SPREAD:
            continue                       # nothing on it
        nxt = th.get(p + 1)
        # A build step: the next page is this slide plus a little. Keep the
        # last of the run, which has everything the earlier ones had.
        if (p + 1 <= n and img is not None and nxt is not None
                and _diff(img, nxt) < BUILD_DIFF
                and _words(pages[p]) >= _words(pages[p - 1])):
            if p + 1 in thin_set:
                same_as[p] = p + 1
                continue
        twin = next((q for q in kept if _diff(th.get(q), img) < SAME_DIFF),
                    None)
        if twin:
            same_as[p] = twin
            continue
        kept.append(p)
    # Resolve chains (3 -> 4 -> 5) to the page actually looked at.
    for p in list(same_as):
        q, hops = same_as[p], 0
        while q in same_as and hops < 50:
            q, hops = same_as[q], hops + 1
        same_as[p] = q
    look = kept
    sampled = False
    cap = _cap()
    if len(look) > cap:
        step = len(look) / cap
        look = [look[int(i * step)] for i in range(cap)]
        sampled = True
    return {"pages": n, "thin": thin, "look": look, "same_as": same_as,
            "sampled": sampled}


def _key(pdf):
    h = hashlib.sha1()
    with open(pdf, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _cache_path(pdf):
    return os.path.join(CACHE, _key(pdf) + ".json")


def cached(pdf):
    try:
        with open(_cache_path(pdf), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _render(pdf, page, out_dir):
    stem = os.path.join(out_dir, "p%d" % page)
    subprocess.run(["pdftoppm", "-f", str(page), "-l", str(page), "-png",
                    "-scale-to-x", str(WIDTH), "-scale-to-y", "-1",
                    "-singlefile", pdf, stem],
                   capture_output=True, timeout=120)
    path = stem + ".png"
    return path if os.path.exists(path) else ""


PROMPT = (
    "These are slides from %r, a session of the MBA course %r. "
    "They are the slides whose meaning is in the picture rather than in "
    "typed text, and a revision guide is going to be built from your "
    "descriptions, so the student must be able to learn from them without "
    "seeing the slide.\n\n"
    "For each slide give: the words on it that matter, and what the "
    "picture shows — a framework's boxes and how they relate, a chart's "
    "axes, numbers and trend, a table's rows, what a photo or screenshot is "
    "of — then the point the slide makes, in one clause. At most 70 words "
    "a slide. A title card, section divider or purely decorative slide gets "
    "\"divider: <its title>\" and nothing more. Never invent a number or a "
    "name you cannot read.\n\n"
    "Reply with JSON only: {\"<slide number>\": \"<description>\"}.")


def describe(pdf, course="", force=False, quiet=False):
    """{page: description} for the slides worth looking at, cached per file
    content. Raises ValueError when the model cannot be reached; a partial
    result is kept, so a second run only pays for what is missing."""
    import school
    if school.is_confidential(pdf):
        raise ValueError("that filename is on the confidential list")
    have = None if force else cached(pdf)
    have = dict(have or {})
    got = {k: v for k, v in (have.get("slides") or {}).items()}
    # The plan is the slow half on a big deck (a minute of thumbnail
    # comparisons for 382 pages), and the file's bytes decide it — reuse it.
    if have.get("look") is not None and have.get("cap") == _cap():
        pl = {"pages": have.get("pages", 0), "thin": [0] * have.get("thin", 0),
              "look": have["look"], "sampled": have.get("sampled", False),
              "same_as": {int(k): v for k, v in
                          (have.get("same_as") or {}).items()}}
    else:
        pl = plan(pdf)
    todo = [p for p in pl["look"] if str(p) not in got]
    if todo:
        import llm
        name = os.path.basename(pdf)
        if not quiet:
            print("  looking at %d picture slide%s in %s"
                  % (len(todo), "" if len(todo) == 1 else "s", name[:50]),
                  flush=True)
        with tempfile.TemporaryDirectory() as td:
            for i in range(0, len(todo), PER_CALL):
                batch = todo[i:i + PER_CALL]
                imgs = [("Slide %d:" % p, _render(pdf, p, td)) for p in batch]
                imgs = [(lbl, path) for lbl, path in imgs if path]
                if not imgs:
                    continue
                r = llm.complete_images(
                    "slides", PROMPT % (name, course or "?"), imgs,
                    system="You read lecture slides for a student who "
                           "cannot see them. You reply with JSON only.",
                    timeout=300)
                from guide import _json_from
                try:
                    ans = _json_from(r.get("text") or "")
                except ValueError:
                    ans = {}
                for k, v in ans.items():
                    m = re.search(r"\d+", str(k))
                    if m and isinstance(v, str) and v.strip():
                        got[m.group(0)] = v.strip()
                have["model"] = r.get("model")
                _save(pdf, have, got, pl)
    else:
        _save(pdf, have, got, pl)
    return {int(k): v for k, v in got.items()}, pl


def _save(pdf, have, got, pl):
    os.makedirs(CACHE, exist_ok=True)
    have.update(deck=os.path.basename(pdf), pages=pl["pages"],
                thin=len(pl["thin"]), looked=len(pl["look"]),
                sampled=pl["sampled"], look=pl["look"], cap=_cap(),
                same_as={str(k): v for k, v in pl["same_as"].items()},
                slides=got)
    tmp = _cache_path(pdf) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(have, f, indent=1, ensure_ascii=False)
    os.replace(tmp, _cache_path(pdf))


def enrich(pdf, course="", quiet=False):
    """The deck's text with what each picture slide shows written in, page
    by page. Falls back to plain text when nothing could be looked at."""
    pages = _pages(pdf)
    try:
        seen, pl = describe(pdf, course=course, quiet=quiet)
    except Exception as exc:                            # noqa: BLE001
        if not quiet:
            print("  (couldn't look at the picture slides: %s)"
                  % str(exc)[:100], flush=True)
        seen, pl = {}, {"same_as": {}}
    same = {int(k): v for k, v in (pl.get("same_as") or {}).items()}
    out, told = [], set()
    for i, text in enumerate(pages):
        p = i + 1
        body = re.sub(r"[ \t]{2,}", "  ", text)
        body = re.sub(r"\n\s*\n\s*\n+", "\n\n", body).strip()
        src = same.get(p, p)
        desc = seen.get(src)
        if src != p:
            # a build step or a repeat: its content is on the page looked at
            if src > p:
                continue
            desc = None
        if not body and not desc:
            continue
        chunk = "--- slide %d ---\n%s" % (p, body) if body else \
            "--- slide %d ---" % p
        if desc and src not in told:
            told.add(src)
            if not desc.lower().startswith("divider"):
                chunk += "\n[what the slide shows: %s]" % desc
        out.append(chunk)
    return "\n\n".join(out)


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        print(__doc__)
        sys.exit(0)
    deck = args[0]
    if "--describe" in sys.argv:
        got, pl = describe(deck, force="--force" in sys.argv)
        print(json.dumps({str(k): got[k] for k in sorted(got)}, indent=1,
                         ensure_ascii=False))
    else:
        pl = plan(deck)
        print("%d pages, %d thin, %d to look at%s"
              % (pl["pages"], len(pl["thin"]), len(pl["look"]),
                 " (sampled)" if pl["sampled"] else ""))
        print("look at:", pl["look"][:120])

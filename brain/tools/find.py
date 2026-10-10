#!/usr/bin/env python3
"""brain/tools/find.py — the bar's find box: type a name, get the thing.

recall.py answers "who and what connect" for a model, walking the graph out
from whole names. Someone typing in a search box wants the thing they are
naming, first, while they are still typing it. On 8 Oct a friend's name
brought back eight "<city>, based in …" rows before the friend, and a
teacher's name brought back nothing, because it lives in a class file the
graph never reads.

So this searches the brain as text, ranked by where the words land: a name
beats a field, a field beats a mention in the prose, and a word she has only
half typed still counts. No model, no network. People, projects, tasks and
finish lines come from model.py's parsers; class files, transcripts, drafts,
guides and book notes from docs.py's list, by id, so the page opens one
without ever naming a path. A file named as confidential is never read.

    python3 brain/tools/find.py <a name or a few words>
"""

import html as H
import os
import re
import sys
import time
import unicodedata
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import model as M  # noqa: E402

BRAIN = M.BRAIN

# Where a word lands, and what that is worth. A level is how cleanly it
# matched: the whole word, the start of a word (she is still typing), or
# inside one (only for words long enough that this is not noise).
WHOLE, START, INSIDE = 3, 2, 1
WEIGHT = {"name": 10, "tag": 4, "body": 1.5}
# A tie goes to the kind of thing more often searched for.
KIND_BONUS = {"person": 3, "project": 2.5, "school": 2, "goal": 1.5,
              "task": 1, "file": 0}
GROUPS = (("people", "People", ("person",)),
          ("projects", "Projects", ("project", "goal")),
          ("tasks", "Tasks", ("task",)),
          ("files", "School and files", ("school", "file")))
PER_GROUP = 30

_FOLD = {}


def fold(s):
    """Lowercase and unaccent, one character for one character, so a
    position in the folded text is the same position in the original."""
    s = s or ""
    if not s.isascii():
        for c in set(s):
            if ord(c) > 127 and ord(c) not in _FOLD:
                d = "".join(x for x in unicodedata.normalize("NFKD", c)
                            if not unicodedata.combining(x)).lower()
                _FOLD[ord(c)] = d[:1] or " "
        s = s.translate(_FOLD)
    return s.lower()


def clean(s):
    """Markdown down to the words, on one line: what a snippet shows."""
    s = re.sub(r"^---\n.*?\n---\n", "", s or "", count=1, flags=re.S)
    s = re.sub(r"(?is)<(style|script)\b.*?</\1>", " ", s)
    s = re.sub(r"<[^>]{1,200}>", " ", s)
    s = H.unescape(s)
    s = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", s)
    s = re.sub(r"(?m)^\s*(?:#+|[-*]\s+\[[ xX]\]|[-*>]|\d+\.)\s+", "", s)
    s = re.sub(r"\*\*|__|`|~~", "", s)
    return re.sub(r"\s+", " ", s).strip()


def words(q):
    ws = [w for w in re.split(r"[^a-z0-9]+", fold(q)) if w]
    # A lone letter inside a longer search is noise ("d" in "d day").
    return [w for w in ws if len(w) > 1] or ws


def level(w, text, inside=True):
    """How cleanly w lands in already-folded text, and where it first does.
    Inside a word counts in a name or a field, never in prose: "odile" in a
    transcript's "Rodileo" is not her friend."""
    if not text or w not in text:
        return 0, -1
    m = re.search(r"(?<![a-z0-9])" + re.escape(w), text)
    if m:
        whole = re.search(r"(?<![a-z0-9])" + re.escape(w) + r"(?![a-z0-9])", text)
        return (WHOLE, whole.start()) if whole else (START, m.start())
    return (INSIDE, text.find(w)) if inside and len(w) >= 4 else (0, -1)


def snippet(text, pos, width=110):
    """About a line of text around a hit, cut at word edges."""
    a = max(0, pos - 40)
    if a:
        a = text.find(" ", a, pos) + 1 or a
    b = min(len(text), a + width)
    if b < len(text):
        b = text.rfind(" ", a, b) if text.rfind(" ", a, b) > pos else b
    return ("…" if a else "") + text[a:b].strip() + ("…" if b < len(text) else "")


# ---- what can be found -------------------------------------------------------
# Built once and kept while its sources are unchanged: she types a letter
# every tenth of a second, and the files change a few times an hour.
_CACHE = {"key": None, "items": [], "docs_at": 0, "docs": []}
_TEXT = {}          # path -> (mtime, cleaned text, folded text)


def _text(path):
    try:
        mt = os.stat(path).st_mtime
    except OSError:
        return "", ""
    hit = _TEXT.get(path)
    if hit and hit[0] == mt:
        return hit[1], hit[2]
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            raw = f.read(1_500_000)
    except OSError:
        raw = ""
    t = clean(raw)
    _TEXT[path] = (mt, t, fold(t))
    return t, _TEXT[path][2]


def _item(kind, title, go, names=(), tags=(), body="", sub="", label="",
          rank=0.0, closed=False, fbody=None):
    title = (title or "").strip()
    return {"kind": kind, "title": title, "go": go, "sub": sub, "label": label,
            "names": [fold(n) for n in (title,) + tuple(names) if n],
            "tags": [(t, fold(t)) for t in tags if t],
            "body": body, "fbody": fold(body) if fbody is None else fbody,
            "rank": rank, "closed": closed}


def _when(iso):
    d = M.parse_date(iso) if iso else None
    return f"{d.day} {d.strftime('%b')}" if d else ""


def _people(today):
    out = []
    for p in M.load_people(today=today):
        job = " at ".join(x for x in (p.get("role"), p.get("company")) if x)
        state = ("you owe a reply" if p.get("owed") else
                 "waiting on them" if p.get("ball") == "them" else
                 "past rhythm" if p.get("overdue") else "")
        last = _when(p.get("last"))
        sub = " · ".join(x for x in (
            p.get("circle"), job,
            p.get("where") if p.get("where", "").lower() != "unknown" else "",
            ("last spoke " + last) if last else "", state) if x)
        promises = " ".join(t.get("text", "") for t in p.get("promises", []))
        body = clean(" ".join([p.get("how", ""), p.get("why", ""), promises]
                              + p.get("notes", [])))
        out.append(_item(
            "person", p["name"], {"person": p["name"]}, names=p.get("also", []),
            tags=[p.get("circle", ""), p.get("role", ""), p.get("company", ""),
                  p.get("where", ""), p.get("met", "")] + p.get("tags", []),
            body=body, sub=sub, label=p.get("circle") or "Person",
            rank=M.circle_weight(p.get("circle", "")) / 10
            - (5 if p.get("oneoff") else 1 if p.get("dormant") else 0)))
    return out


def _room_of(cfg):
    slugs = {}
    for r in M.all_rooms(cfg):
        for wsn in r.get("ws") or []:
            slugs.setdefault(wsn, r["slug"])
    return slugs


def _projects(today, cfg):
    slugs = _room_of(cfg)
    names = {r["slug"]: r.get("name", r["slug"]) for r in M.all_rooms(cfg)}
    out = []

    def go(wsn):
        sl = slugs.get(wsn)
        return {"href": f"rooms.html#room/{sl}"} if sl else {"ws": wsn}

    room_areas = {}
    for w in M.load(today=today):
        room_areas.setdefault(slugs.get(w["name"]), set()).add(
            (w.get("area") or "").strip().lower())
        closed = w["status"] in ("done", "dropped")
        f = w["fields"]
        sub = " · ".join(x for x in (
            w.get("area"), w["status"].capitalize(),
            M._plain(f.get("next", ""))) if x)
        out.append(_item(
            "project", w["name"], go(w["name"]), label="Project",
            tags=[w.get("area", "")] + [M._plain(v) for k, v in f.items()
                                        if k not in ("touched", "since", "status")],
            body=clean(" ".join(w["notes"])), sub=sub, closed=closed))
        out[-1]["area"] = w.get("area", "")
        if closed:
            continue
        for t in w["tasks"]:
            if t["done"] or t["dropped"]:
                continue
            due = t.get("due_raw") or t.get("by_raw")
            out.append(_item(
                "task", t["text"], go(w["name"]), label="Task",
                body=clean(" ".join(t["notes"])),
                sub=" · ".join(x for x in (w["name"], ("due " + due) if due else "") if x),
                tags=[w["name"]]))
            out[-1]["area"] = w.get("area", "")
    # goals.md is keyed by the page's name, lowercased, not by its slug
    by_name = {n.lower(): sl for sl, n in names.items()}
    for key, goals in M.load_goals(today=today).items():
        slug = by_name.get(key) or M.room_slug(key)
        where = names.get(slug, key)
        for g in goals:
            if g.get("done"):
                continue
            out.append(_item(
                "goal", g["text"], {"href": f"rooms.html#room/{slug}"},
                label="Finish line", tags=[where],
                sub=" · ".join(x for x in ("Finish line for " + where,
                                           ("due " + g["due_label"]) if g.get("due_label") else "")
                               if x)))
            out[-1]["areas"] = room_areas.get(slug, set())
    # Her own notes on a project page, which she writes and the brain never
    # rewrites: a hit there opens that page.
    rdir = os.path.join(BRAIN, "rooms")
    for fn in sorted(os.listdir(rdir)) if os.path.isdir(rdir) else []:
        if fn.endswith(".md"):
            body, fb = _text(os.path.join(rdir, fn))
            slug = fn[:-3]
            out.append(_item("project", names.get(slug, slug),
                             {"href": f"rooms.html#room/{slug}"},
                             label="Project notes", body=body, fbody=fb,
                             sub="Your notes on its page"))
            out[-1]["notes"] = True
    return out


def _docs():
    """docs.py's list plus the class files: slow to walk (~0.1s), so it is
    walked at most once a minute."""
    now = time.time()
    if now - _CACHE["docs_at"] < 60:
        return _CACHE["docs"]
    import docs as D
    try:
        es = D.index() + D.extra()
    except Exception:                                   # noqa: BLE001
        es = []
    _CACHE.update(docs_at=now, docs=es)
    return es


def _files():
    try:
        import school
        guarded = school.is_confidential
    except Exception:                                   # noqa: BLE001
        def guarded(_p):
            return True
    out = []
    for e in _docs():
        kind = "school" if e["kind"] in ("School", "Class notes", "Guide",
                                         "Book notes") else "file"
        body, fb = "", ""
        # Read only what the brain may read: its own text files, never one
        # whose name marks it confidential.
        if (e.get("text") or e["ext"] == ".html") and not guarded(e["path"]):
            body, fb = _text(e["path"])
        head = e.get("head") or ""
        out.append(_item(
            kind, e["name"], {"file": e["id"]}, label=e["kind"],
            tags=[e.get("where", "")] + e.get("tags", []), body=body, fbody=fb,
            sub=" · ".join(x for x in (e["kind"], e.get("where"), head) if x),
            closed=e.get("where", "").endswith("discarded")))
    return out


def _sources_key(today):
    names = ("people.md", "workstreams.md", "goals.md", "config.json")
    mt = []
    for n in names:
        try:
            mt.append(os.stat(os.path.join(BRAIN, n)).st_mtime)
        except OSError:
            mt.append(0)
    rdir = os.path.join(BRAIN, "rooms")
    try:
        mt.append(os.stat(rdir).st_mtime)
    except OSError:
        pass
    return (today.isoformat(), tuple(mt))


def items(today=None):
    today = today or date.today()
    key = _sources_key(today)
    if _CACHE["key"] != key:
        cfg = M.load_config()
        _CACHE["items"] = _people(today) + _projects(today, cfg)
        _CACHE["key"] = key
    return _CACHE["items"] + _files()


# ---- ranking -----------------------------------------------------------------

def score(it, ws, q):
    """None when a word lands nowhere; else how well it all landed, and the
    text and spot to show when the best hit was not in the name."""
    total, show = 0.0, None
    for w in ws:
        best, where = 0.0, None
        for n in it["names"]:
            lv, _ = level(w, n)
            if lv and lv * WEIGHT["name"] > best:
                best, where = lv * WEIGHT["name"], None
        for raw, ft in it["tags"]:
            lv, pos = level(w, ft)
            if lv and lv * WEIGHT["tag"] > best:
                best, where = lv * WEIGHT["tag"], (raw, pos)
        if best < WHOLE * WEIGHT["tag"]:
            lv, pos = level(w, it["fbody"], inside=False)
            if lv and lv * WEIGHT["body"] > best:
                best, where = lv * WEIGHT["body"], (it["body"], pos)
        if not best:
            return None
        total += best
        if where and show is None:
            show = where
    t = it["names"][0] if it["names"] else ""
    fq = " ".join(ws)
    if t == fq or fq in it["names"][1:]:
        total += 40
    elif t.startswith(fq):
        total += 15
    total += KIND_BONUS.get(it["kind"], 0) + it["rank"]
    if it["closed"]:
        total -= 10
    return total, show


def find(q, today=None, per_group=PER_GROUP):
    """The groups that matched, best group first, best first inside each.
    What the page may know: titles, a line under each, where it opens."""
    t0 = time.perf_counter()
    ws = words(q)
    if not ws or len(" ".join(ws)) < 2:
        return {"groups": [], "total": 0, "ms": 0}
    hits = []
    # Presenting (privacy.py): what the pages hide, the find box hides too.
    # No people, no files, nothing from the hidden areas (a goal or her
    # notes by their page's areas), nothing naming someone in a personal
    # circle, and no notes: titles and tags only, as on the pages.
    import privacy
    pres = privacy.presenting()
    hide = {a.strip().lower() for a in pres["areas"]} if pres else set()
    if pres:
        names = privacy.present_names(M.load_people(today=today))
        rx = (re.compile(r"\b(?:" + "|".join(re.escape(n) for n in sorted(
            names, key=len, reverse=True)) + r")\b", re.I) if names else None)
    for it in items(today):
        if pres:
            if it["kind"] in ("person", "file") or it.get("notes") \
                    or (it.get("area") or "").strip().lower() in hide \
                    or (it.get("areas") or set()) & hide:
                continue
            if rx and any(rx.search(x or "") for x in
                          [it["title"], it["sub"]] + [t for t, _ in it["tags"]]):
                continue
            it = dict(it, body="", fbody="")
        s = score(it, ws, q)
        if s is None:
            continue
        total, show = s
        sub = it["sub"]
        if show and show[0] is not it["body"]:
            # A field hit: the usual line, with the field when it lacks it.
            if fold(show[0]) not in fold(sub):
                sub = " · ".join(x for x in (sub or it["label"],
                                             snippet(*show, width=80)) if x)
        elif show:
            sub = " · ".join(x for x in (it["label"], snippet(*show)) if x)
        hits.append((total, it, sub))
    hits.sort(key=lambda h: (-h[0], h[1]["title"].lower()))
    groups = []
    for gid, label, kinds in GROUPS:
        rows = [h for h in hits if h[1]["kind"] in kinds]
        if not rows:
            continue
        groups.append({"id": gid, "label": label, "total": len(rows),
                       "best": rows[0][0],
                       "items": [{"t": it["title"], "s": sub, "go": it["go"]}
                                 for _, it, sub in rows[:per_group]]})
    groups.sort(key=lambda g: -g["best"])
    for g in groups:
        del g["best"]
    return {"groups": groups, "total": len(hits),
            "ms": round((time.perf_counter() - t0) * 1000)}


def main():
    q = " ".join(sys.argv[1:])
    r = find(q)
    for g in r["groups"]:
        print(f"{g['label']} ({g['total']})")
        for it in g["items"][:6]:
            print(f"  {it['t']}\n      {it['s']}")
    print(f"\n{r['total']} found in {r['ms']} ms")


if __name__ == "__main__":
    main()

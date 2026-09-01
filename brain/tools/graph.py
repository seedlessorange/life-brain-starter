#!/usr/bin/env python3
"""brain/tools/graph.py — the brain as a graph, built from the markdown.

Three tables, which is what this model's facts need: a thing exists
(entities), two things connect (relations), a thing goes by another name
(aliases).

Nothing here is a new source of truth. Every row is derived from
workstreams.md, people.md, goals.md and config.json by the same parser the
pages use, so the markdown stays the only thing anyone edits. The whole
file is thrown away and rebuilt whenever one of those sources is newer —
delete brain/graph.db any time you like, the next recall rebuilds it.

Identity is computed, never looked up: an entity's id is a hash of its type
and its normalised name, so a room named in config.json and the same room
named in goals.md land on one node with no matching step in between.

Build it by hand with `python3 brain/tools/graph.py`; ask it questions with
`python3 brain/tools/recall.py "who signs off on Faverolles?"`.
"""

import os
import re
import sqlite3
import sys
import unicodedata
import uuid

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import model  # noqa: E402

DB = os.path.join(model.BRAIN, "graph.db")

# The ontology, kept small and closed on purpose. Both lists come from the
# questions this brain gets asked — who is involved, what is due, what does
# this room owe — not from what the files happen to contain.
ENTITY_TYPES = ("PERSON", "WORKSTREAM", "TASK", "ROOM", "WING",
                "AREA", "GOAL", "PLACE")
PREDICATES = ("involves", "ball_with", "in_room", "in_wing", "in_area",
              "has_task", "targets", "based_in")

SCHEMA = """
CREATE TABLE entities  (id TEXT PRIMARY KEY,
                        name TEXT, type TEXT,
                        description TEXT, source_doc TEXT);
CREATE TABLE relations (source_id TEXT, target_id TEXT,
                        predicate TEXT, source_doc TEXT,
                        PRIMARY KEY (source_id, target_id, predicate));
CREATE TABLE aliases   (entity_id TEXT, alias TEXT,
                        PRIMARY KEY (entity_id, alias));
CREATE INDEX rel_src ON relations(source_id);
CREATE INDEX rel_tgt ON relations(target_id);
CREATE INDEX alias_a ON aliases(alias);
"""

# Sources whose modification time decides whether the graph is stale.
SOURCES = ("workstreams.md", "people.md", "goals.md", "config.json")

# Words that are capitalised for reasons other than being a name — months
# and sentence-starters. Everything else is handled by the rule that a name
# must be capitalised where it appears, which is what keeps the group chat
# called "House" from matching "Tatum's house".
STOP_ALIASES = {"may", "march", "april", "june", "july", "august", "new",
                "will", "the", "and", "me", "team"}


def fold(s):
    """Unaccent and strip punctuation, keeping case. Case is what tells a
    person called House from a house."""
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^A-Za-z0-9]+", " ", s).strip()


def normalise(s):
    """fold(), lowercased. Two spellings of one name must produce one id,
    which is the whole reason this exists."""
    return fold(s).lower()


def entity_id(type_, name):
    """Identity is a hash of type and normalised name — never a lookup, so
    re-running the build merges instead of duplicating."""
    return str(uuid.uuid5(uuid.NAMESPACE_OID, f"{type_}:{normalise(name)}"))


class Builder:
    """Accumulates nodes and edges, then writes them once."""

    def __init__(self):
        self.entities = {}   # id -> row
        self.relations = {}  # (s, t, p) -> source_doc
        self.aliases = set()  # (id, normalised alias)

    def node(self, type_, name, description="", source_doc=""):
        name = (name or "").strip()
        if not name:
            return None
        eid = entity_id(type_, name)
        prev = self.entities.get(eid)
        # First writer wins on description, so the richer source (people.md
        # for a person, config.json for a room) should be added first.
        if prev is None:
            self.entities[eid] = (eid, name, type_, description, source_doc)
        elif not prev[3] and description:
            self.entities[eid] = (eid, prev[1], type_, description, source_doc)
        self.alias(eid, name)
        return eid

    def edge(self, src, tgt, predicate, source_doc=""):
        if src and tgt and src != tgt:
            self.relations.setdefault((src, tgt, predicate), source_doc)

    def alias(self, eid, text):
        a = normalise(text)
        if eid and len(a) >= 3:
            self.aliases.add((eid, a))

    def write(self, path):
        # A per-process temp name: the recall hook rebuilds from every repo,
        # and two prompts landing together must not delete each other's
        # half-written file — the loser's prompt would silently get no brain
        # context at all.
        tmp = f"{path}.{os.getpid()}.tmp"
        if os.path.exists(tmp):
            os.remove(tmp)
        db = sqlite3.connect(tmp)
        db.executescript(SCHEMA)
        db.executemany("INSERT INTO entities VALUES (?,?,?,?,?)",
                       self.entities.values())
        db.executemany(
            "INSERT OR IGNORE INTO relations VALUES (?,?,?,?)",
            [(s, t, p, d) for (s, t, p), d in self.relations.items()])
        db.executemany("INSERT OR IGNORE INTO aliases VALUES (?,?)",
                       self.aliases)
        db.commit()
        db.close()
        os.replace(tmp, path)
        return len(self.entities), len(self.relations), len(self.aliases)


def _person_desc(p):
    """The conditions live in the description — that is what makes a fact
    answerable without opening the file it came from."""
    bits = []
    if p.get("circle"):
        bits.append(f"{p['circle']} circle")
    if p.get("role"):
        bits.append(p["role"] + (f" at {p['company']}" if p.get("company")
                                 else ""))
    elif p.get("company"):
        bits.append(p["company"])
    if p.get("where"):
        bits.append(f"in {p['where']}")
    if p.get("reach"):
        bits.append(f"reach by {p['reach']}")
    if p.get("pronouns"):
        bits.append(p["pronouns"])
    if p.get("personal"):
        bits.append("personal circle — draft only, never send")
    if p.get("last"):
        bits.append(f"last spoke {p['last']}")
    if p.get("overdue"):
        bits.append("overdue for contact")
    if p.get("ball") == "me":
        bits.append("you owe them a reply")
    if p.get("how"):
        bits.append(p["how"].rstrip("."))
    if p.get("why"):
        bits.append(p["why"].rstrip("."))
    return "; ".join(b for b in bits if b)[:400]


def _ws_desc(w):
    bits = [w.get("status") or "no status"]
    ball = w.get("ball")
    if ball == "them":
        bits.append(f"ball with {w.get('ball_who') or 'them'}"
                    + (f" since {w['since']}" if w.get("since") else ""))
    elif ball == "me":
        bits.append("ball with you")
    if w.get("due_label"):
        bits.append(f"due {w['due_label']}"
                    + (" — OVERDUE" if w.get("overdue") else ""))
    if w.get("next_action"):
        bits.append(f"next: {w['next_action']}")
    if w.get("touched"):
        bits.append(f"last touched {w['touched']}")
    if w.get("why"):
        bits.append(w["why"])
    return "; ".join(b for b in bits if b)[:400]


def _task_desc(t):
    bits = []
    if t.get("due_label"):
        bits.append(f"due {t['due_label']}"
                    + (" — OVERDUE" if t.get("overdue") else ""))
    if t.get("est"):
        bits.append(model.fmt_dur(t["est"]))
    if t.get("urgent"):
        bits.append("urgent")
    if t.get("until"):
        bits.append(f"parked until {t['until']}")
    return "; ".join(bits)[:200]


def _people_matcher(people, ids):
    """One regex that finds any known person in a piece of prose.

    Full names and every `Also:` spelling always count. A first name counts
    only when it is unique across the whole file — sixteen of them are not,
    and wiring the wrong Bexley to a workstream is worse than missing one.
    """
    first_counts = {}
    for p in people:
        tok = normalise(p["name"]).split()
        if tok:
            first_counts[tok[0]] = first_counts.get(tok[0], 0) + 1

    by_alias = {}
    for p in people:
        eid = ids[p["name"]]
        forms = [p["name"]] + list(p.get("also") or [])
        tok = normalise(p["name"]).split()
        if tok and first_counts[tok[0]] == 1:
            forms.append(tok[0])
        for f in forms:
            a = normalise(f)
            if len(a) >= 3 and a not in STOP_ALIASES:
                by_alias.setdefault(a, set()).add(eid)

    # Longest alias first, so "Sam Whitfield Roofing" wins over "sam".
    keys = sorted(by_alias, key=len, reverse=True)
    if not keys:
        return None, {}
    rx = re.compile(r"(?<![A-Za-z0-9])(" +
                    "|".join(re.escape(k).replace(r"\ ", r"\s+")
                             for k in keys) + r")(?![A-Za-z0-9])",
                    re.IGNORECASE)
    return rx, by_alias


def _people_in(rx, by_alias, fragments):
    """Every person named across some fragments of prose.

    Fragments are kept apart on purpose: a name at the end of one line is
    not followed by the capital that starts the next one.

    Two rules do all the disambiguating. A match must be capitalised where
    it appears, which separates the group chat called "House" from
    "Tatum's house". And a one-word name followed by another capital is
    treated as part of a longer proper noun, which separates it again from
    "House Renovation Tracker".
    """
    found = set()
    if isinstance(fragments, str):
        fragments = [fragments]
    for frag in fragments:
        folded = fold(frag)
        for m in rx.finditer(folded):
            tok = m.group(1)
            if not tok[:1].isupper():
                continue
            if " " not in tok and folded[m.end():].lstrip()[:1].isupper():
                continue
            found.update(by_alias.get(normalise(tok), ()))
    return found


def build(path=None, cfg=None, today=None):
    """Rebuild the whole graph from the markdown. Returns (n_entities,
    n_relations, n_aliases)."""
    path = path or DB
    cfg = cfg or model.load_config()
    b = Builder()

    # People first, so their descriptions win over a bare name mentioned
    # in a workstream.
    people = model.load_people(today=today)
    pid = {}
    for p in people:
        eid = b.node("PERSON", p["name"], _person_desc(p), "people.md")
        pid[p["name"]] = eid
        for a in (p.get("also") or []):
            b.alias(eid, a)
        if p.get("where"):
            place = b.node("PLACE", p["where"], "", "people.md")
            b.edge(eid, place, "based_in", "people.md")

    # Rooms and wings come from config.json — the map she already drew.
    room_ws = {}
    for wing in ((cfg.get("rooms") or {}).get("wings") or []):
        wid = b.node("WING", wing.get("name") or "", "", "config.json")
        for room in (wing.get("rooms") or []):
            rname = room.get("name") or ""
            desc = (f"watches {room['source']}" if room.get("source") else "")
            rid = b.node("ROOM", rname, desc, "config.json")
            b.edge(rid, wid, "in_wing", "config.json")
            for w in (room.get("ws") or []):
                room_ws[normalise(w)] = rid

    # Goals hang off the room they name.
    for heading, goals in (model.load_goals(today=today) or {}).items():
        rid = room_ws.get(normalise(heading)) or \
            b.node("ROOM", heading, "", "goals.md")
        for g in goals:
            if g["done"]:
                continue
            gid = b.node("GOAL", g["text"], _task_desc(g) or "no date",
                         "goals.md")
            b.edge(gid, rid, "targets", "goals.md")

    rx, by_alias = _people_matcher(people, pid)

    items = model.load(cfg=cfg, today=today)
    for w in items:
        if (w.get("status") or "").lower() in ("done", "dropped"):
            continue
        wid = b.node("WORKSTREAM", w["name"], _ws_desc(w), "workstreams.md")
        if w.get("area"):
            b.edge(wid, b.node("AREA", w["area"], "", "workstreams.md"),
                   "in_area", "workstreams.md")
        rid = room_ws.get(normalise(w["name"]))
        if rid:
            b.edge(wid, rid, "in_room", "config.json")

        for t in (w.get("tasks") or []):
            if t.get("done") or t.get("dropped"):
                continue
            tid = b.node("TASK", t["text"], _task_desc(t), "workstreams.md")
            b.edge(wid, tid, "has_task", "workstreams.md")

        # The edge the markdown does not carry: who a workstream is about.
        # `People:` exists as a field but nothing uses it, so the names are
        # found in the prose where she actually writes them.
        hay = [w.get("why") or "", w.get("next_action") or "",
               w.get("ball_who") or "", w["name"]] \
            + list(w.get("notes") or []) \
            + [t["text"] for t in (w.get("tasks") or [])]
        if rx:
            for eid in _people_in(rx, by_alias, hay):
                b.edge(wid, eid, "involves", "workstreams.md")
            if w.get("ball") == "them":
                for eid in _people_in(rx, by_alias, w.get("ball_who") or ""):
                    b.edge(wid, eid, "ball_with", "workstreams.md")

    return b.write(path)


def stale(path=None):
    """True when any source is newer than the graph, or it is missing."""
    path = path or DB
    try:
        built = os.path.getmtime(path)
    except OSError:
        return True
    for name in SOURCES:
        try:
            if os.path.getmtime(os.path.join(model.BRAIN, name)) > built:
                return True
        except OSError:
            pass
    return False


def ensure_fresh(path=None):
    """Rebuild if the markdown moved. This is why the graph can never go
    stale and why it is not in the rebuild ritual."""
    path = path or DB
    if stale(path):
        build(path)
    return path


if __name__ == "__main__":
    e, r, a = build()
    print(f"graph: {e} entities, {r} relations, {a} aliases → {DB}")

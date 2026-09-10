#!/usr/bin/env python3
"""brain/tools/recall.py — ask the graph a question, get facts back.

Two jobs, which is what every graph lookup needs whatever the store is.
Seeding: match the words of a question against entity names and aliases.
Walking: collect everything connected to those seeds, hop by hop, and keep
the nearest of it. No model is involved in either — this is plain SQL over
a file that took 60ms to build, which is the entire point. The answer comes
back as text, shaped for something else to read.

    python3 brain/tools/recall.py "who is on the Ibiza renovation?"
    python3 brain/tools/recall.py --hops 2 --top-k 12 "what is due this week?"

The graph rebuilds itself here if the markdown moved, so this can never
answer from a stale file.
"""

import argparse
import os
import re
import sqlite3
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import graph  # noqa: E402

# Question words carry no entity. Dropping them stops "who" and "week"
# seeding half the brain.
NOISE = {
    "who", "what", "when", "where", "which", "whose", "why", "how", "the",
    "and", "for", "with", "from", "that", "this", "there", "their", "them",
    "they", "have", "has", "had", "does", "did", "doing", "done", "was",
    "were", "are", "is", "be", "been", "being", "should", "would", "could",
    "can", "will", "shall", "must", "need", "needs", "about", "into", "over",
    "under", "than", "then", "now", "still", "just", "any", "all", "some",
    "next", "last", "first", "not", "but", "off", "out", "get", "got",
    "know", "tell", "say", "said", "ask", "asked", "want", "wants", "much",
    "many", "more", "most", "make", "made", "take", "took", "give", "let",
    "one", "two", "each", "own", "same", "other", "before", "after", "left",
}

# When the walk brings back more than fits, these come first. A fact about
# who is involved beats a fact about which wing a room sits in.
PREDICATE_RANK = {
    "ball_with": 0, "involves": 1, "targets": 2, "has_task": 3,
    "in_room": 4, "in_area": 5, "based_in": 6, "in_wing": 7,
}

WALK = """
WITH RECURSIVE walk(entity_id, depth) AS (
  SELECT id, 0 FROM entities WHERE id IN ({seeds})
  UNION
  SELECT CASE WHEN r.source_id = w.entity_id
              THEN r.target_id ELSE r.source_id END,
         w.depth + 1
  FROM relations r JOIN walk w
    ON w.entity_id IN (r.source_id, r.target_id)
  WHERE w.depth < ?
)
SELECT entity_id, MIN(depth) FROM walk GROUP BY entity_id
"""


class Facts:
    """What came back: the triples, the notes behind them, and the cost."""

    def __init__(self, question, triples, notes, ms, seeds):
        self.question = question
        self.triples = triples      # (subject, predicate, object, source_doc)
        self.notes = notes          # [(name, description)]
        self.ms = ms
        self.seeds = seeds          # [name] — what the question matched on

    def __len__(self):
        return len(self.triples)

    def prune(self, keep):
        """Drop facts the caller has already said another way, and the notes
        left with nothing to explain."""
        self.triples = [t for t in self.triples if keep(*t)]
        live = {n for s, _, o, _ in self.triples for n in (s, o)}
        self.notes = [(n, d) for n, d in self.notes
                      if n.split(" (")[0] in live]
        return self

    def as_text(self):
        """The shape handed to a model. First line is the counts, so it can
        double as the one-line summary anything upstream wants to print."""
        if not self.triples:
            return (f"memory: no matches for this question "
                    f"({self.ms:.0f} ms)")
        head = (f"memory: {len(self.triples)} facts recalled in "
                f"{self.ms:.0f} ms")
        width = max(len(f"{s} --[{p}]--> {o}") for s, p, o, _ in self.triples)
        width = min(width, 72)
        lines = [head, ""]
        for s, p, o, doc in self.triples:
            line = f"{s} --[{p}]--> {o}"
            lines.append(f"{line.ljust(width)}  ({doc})" if doc else line)
        if self.notes:
            lines += ["", "where:"]
            lines += [f"  {n}: {d}" for n, d in self.notes if d]
        return "\n".join(lines)


def _seed(db, question, limit=6):
    """Find where in the graph a question starts.

    Whole aliases matching the question are the strong signal. A single
    distinctive word is the weak one, and it is what lets "Faverolles" reach
    a workstream actually called "Renovations — Faverolles (Burgundy)".
    """
    q = graph.normalise(question)
    q_words = {w for w in q.split() if len(w) >= 3 and w not in NOISE}
    if not q_words:
        return []

    scores = {}
    for eid, alias in db.execute("SELECT entity_id, alias FROM aliases"):
        if re.search(r"(?<![a-z0-9])" + re.escape(alias).replace(r"\ ", r"\s+")
                     + r"(?![a-z0-9])", q):
            scores[eid] = max(scores.get(eid, 0), 10 + len(alias))
            continue
        hit = q_words & set(alias.split())
        if hit:
            scores[eid] = max(scores.get(eid, 0), max(len(w) for w in hit))

    ranked = sorted(scores.items(), key=lambda kv: -kv[1])[:limit]
    return [eid for eid, _ in ranked]


def recall(question, hops=3, top_k=8, path=None, prefer=(), strict=False):
    """Facts for a question. Never raises on a question it cannot place —
    an empty result is a real answer and says so.

    `prefer` names entities the caller already cares about, and pulls facts
    touching them to the front. A hub like Dad sits on five workstreams, so
    a question naming him reaches all five equally; the caller usually knows
    which one it is standing in. `strict` drops the rest rather than ranking
    them down, which is what a session inside one project wants.
    """
    t0 = time.perf_counter()
    path = graph.ensure_fresh(path)
    db = sqlite3.connect(f"file:{path}?mode=ro", uri=True)

    pref_ids = set()
    if prefer:
        marks = ",".join("?" * len(prefer))
        pref_ids = {i for (i,) in db.execute(
            f"SELECT id FROM entities WHERE type='WORKSTREAM' "
            f"AND name IN ({marks})", list(prefer))}

    seeds = _seed(db, question)
    if not seeds:
        db.close()
        return Facts(question, [], [], (time.perf_counter() - t0) * 1000, [])

    depth = dict(db.execute(
        WALK.format(seeds=",".join("?" * len(seeds))), seeds + [hops]))

    rows = db.execute("""
        SELECT e1.name, r.predicate, e2.name, r.source_doc,
               r.source_id, r.target_id
        FROM relations r
        JOIN entities e1 ON e1.id = r.source_id
        JOIN entities e2 ON e2.id = r.target_id
    """).fetchall()

    seedset = set(seeds)
    scored = []
    for s_name, pred, o_name, doc, sid, tid in rows:
        if sid not in depth or tid not in depth:
            continue
        near_pref = 0 if (sid in pref_ids or tid in pref_ids) else 1
        if strict and pref_ids and near_pref:
            continue
        # What the caller is standing in first, then nearest, then the more
        # useful kind of fact, then a fact touching the question itself.
        scored.append((near_pref,
                       depth[sid] + depth[tid],
                       PREDICATE_RANK.get(pred, 9),
                       0 if (sid in seedset or tid in seedset) else 1,
                       (s_name, pred, o_name, doc), (sid, tid)))
    scored.sort(key=lambda x: x[:4])
    chosen = scored[:top_k]
    triples = [t for *_, t, _ in chosen]

    # Notes are fetched by id, never by name: a room and a workstream can
    # share a name (Perch, Faverolles) and a lookup by name returns both,
    # attached to whichever line mentioned either.
    seen = []
    for *_, (sid, tid) in chosen:
        for eid in (sid, tid):
            if eid not in seen:
                seen.append(eid)
    marks = ",".join("?" * len(seen))
    found = {i: (n, ty, d) for i, n, ty, d in db.execute(
        f"SELECT id, name, type, description FROM entities "
        f"WHERE id IN ({marks})", seen)}
    names = [found[e][0] for e in seen if e in found]
    notes = []
    for eid in seen:
        n, ty, d = found.get(eid, ("", "", ""))
        if d:
            notes.append((f"{n} ({ty.lower()})" if names.count(n) > 1 else n,
                          d))
    seed_names = [n for (n,) in db.execute(
        f"SELECT name FROM entities WHERE id IN "
        f"({','.join('?' * len(seeds))})", seeds)]
    db.close()
    return Facts(question, triples, notes,
                 (time.perf_counter() - t0) * 1000, seed_names)


def main():
    ap = argparse.ArgumentParser(description="Ask the brain's graph.")
    ap.add_argument("question", nargs="+")
    ap.add_argument("--hops", type=int, default=3)
    ap.add_argument("--top-k", type=int, default=8)
    ap.add_argument("--seeds", action="store_true",
                    help="show what the question matched on")
    a = ap.parse_args()
    f = recall(" ".join(a.question), hops=a.hops, top_k=a.top_k)
    if a.seeds:
        print(f"seeded on: {', '.join(f.seeds) or '(nothing)'}\n")
    print(f.as_text())


if __name__ == "__main__":
    main()

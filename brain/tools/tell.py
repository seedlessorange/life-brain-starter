#!/usr/bin/env python3
"""Report a fact up to the life-brain from anywhere on this Mac.

    python3 ~/life-brain/brain/tools/tell.py "SIRET approved — Twilio unblocked" --from Perch

Writes one pending item into brain/queue/ — the same shape the page's ask box
produces — so the next /queue or night-shift run files the fact where it
belongs. No server, no model, no tokens: it is safe to call from a project
repo's Claude session the moment something real-world changes state.
"""
import argparse
import os
import re
import sys
from datetime import date, datetime

BRAIN = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
QUEUE = os.path.join(BRAIN, "queue")


def slug(text):
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s[:40] or "tell"


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("text", help="what happened, one plain sentence")
    ap.add_argument("--from", dest="source", default="",
                    help="which project is reporting (Perch, TapGate, ...)")
    args = ap.parse_args()

    text = " ".join(args.text.strip().split())
    if not text:
        sys.exit("nothing to tell")
    if len(text) > 2000:
        sys.exit("keep it to a sentence or two — long reports belong in the "
                 "project's own brain, not the queue")

    body = text
    if args.source:
        body = (f"[reported by a {args.source} session — a status fact, "
                f"not her words]\n\n{text}")

    os.makedirs(QUEUE, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d-%H%M%S")
    title = text[:70]
    path = os.path.join(QUEUE, f"{stamp}-{slug(title)}.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write("---\n"
                f"title: {title}\n"
                "mode: just-do-it\n"
                "status: pending\n"
                f"created: {date.today().isoformat()}\n"
                + (f"source: {args.source}\n" if args.source else "")
                + "---\n\n"
                + body + "\n")
    print(f"queued: {os.path.basename(path)}")


if __name__ == "__main__":
    main()

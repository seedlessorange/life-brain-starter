#!/usr/bin/env python3
"""Mail rules in plain words, turned into a file Gmail imports.

    python3 brain/tools/mail_filters.py            # write brain/files/gmail-filters.xml
    python3 brain/tools/mail_filters.py --preview  # each label as a Gmail search

The sorting happens inside Gmail, as its own filters, so the brain never
reads a message to sort one. That keeps the one rule about email intact:
nothing here opens a mailbox, and nothing here can.

The rules live in brain/mail-rules.md, one heading per label:

    ## School
    - **From:** school.edu, blackboard.com       a name, an address or a domain
    - **To:** me@school.edu
    - **Words:** Venture, venture lab            anywhere in the mail
    - **Subject:** invoice, facture
    - **Not from:** someone@example.com       kept out of this label
    - **Skip inbox:** yes                     archive as well as label

Inside a label every line is its own filter, so any one of them matching is
enough. Only "Skip inbox" hides mail; every other label just tags it, and
nothing but a skip-inbox label is ever kept out of spam protection's way.

To load: Gmail > Settings > See all settings > Filters and Blocked
Addresses > Import filters > choose the file > Open file, tick "Apply new
filters to existing email", then Create filters. Importing again adds a
second copy of each rule, so delete the old ones first.
"""
import os
import re
import sys
from datetime import datetime, timezone
from xml.sax.saxutils import quoteattr

HERE = os.path.dirname(os.path.abspath(__file__))
BRAIN = os.path.dirname(HERE)
RULES = os.path.join(BRAIN, "mail-rules.md")
OUT = os.path.join(BRAIN, "files", "gmail-filters.xml")

FIELDS = ("from", "to", "words", "subject", "not from", "skip inbox")


def parse(path=RULES):
    """[{"label", "from": [...], "to": [...], "words": [...],
    "subject": [...], "not from": [...], "skip": bool}]"""
    with open(path, encoding="utf-8") as f:
        text = f.read()
    text = re.sub(r"^---\n.*?\n---\n", "", text, flags=re.S)
    out = []
    for m in re.finditer(r"^## (.+?)\n(.*?)(?=^## |\Z)", text, re.M | re.S):
        rule = {"label": m.group(1).strip(), "skip": False}
        for k in FIELDS:
            rule.setdefault(k, [])
        for key, val in re.findall(r"^- \*\*([^:*]+):\*\*\s*(.*)$",
                                   m.group(2), re.M):
            key = key.strip().lower()
            if key == "skip inbox":
                rule["skip"] = val.strip().lower() in ("yes", "true", "on")
            elif key in FIELDS:
                rule[key] += [t.strip() for t in val.split(",") if t.strip()]
        out.append(rule)
    return out


def _term(t):
    """One search term: a phrase gets quotes, an address or domain doesn't."""
    t = t.strip().strip('"')
    if re.fullmatch(r"[\w.@+\-']+", t):
        return t
    return '"%s"' % t


def _any(terms):
    return " OR ".join(_term(t) for t in terms)


def filters(rules):
    """[(label, {gmail property: value})] — one entry per matching line."""
    out = []
    for r in rules:
        keep_out = ("from:(%s)" % _any(r["not from"])) if r["not from"] else ""
        crit = []
        if r["from"]:
            crit.append({"from": _any(r["from"])})
        if r["to"]:
            crit.append({"to": _any(r["to"])})
        if r["words"]:
            crit.append({"hasTheWord": _any(r["words"])})
        if r["subject"]:
            crit.append({"subject": _any(r["subject"])})
        for c in crit:
            if keep_out:
                c["doesNotHaveTheWord"] = keep_out
            c["label"] = r["label"]
            if r["skip"]:
                c["shouldArchive"] = "true"
            else:
                c["shouldNeverSpam"] = "true"
            out.append((r["label"], c))
    return out


def xml(entries):
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    lines = ["<?xml version='1.0' encoding='UTF-8'?>",
             "<feed xmlns='http://www.w3.org/2005/Atom' "
             "xmlns:apps='http://schemas.google.com/apps/2006'>",
             "  <title>Mail Filters</title>",
             "  <updated>%s</updated>" % now]
    for _, props in entries:
        lines += ["  <entry>",
                  "    <category term='filter'></category>",
                  "    <title>Mail Filter</title>",
                  "    <updated>%s</updated>" % now,
                  "    <content></content>"]
        for k, v in props.items():
            lines.append("    <apps:property name=%s value=%s/>"
                         % (quoteattr(k), quoteattr(v)))
        lines.append("  </entry>")
    lines.append("</feed>")
    return "\n".join(lines) + "\n"


def preview(rules):
    """Each label as one Gmail search, to paste in and see what it catches."""
    out = []
    for r in rules:
        parts = []
        if r["from"]:
            parts.append("from:(%s)" % _any(r["from"]))
        if r["to"]:
            parts.append("to:(%s)" % _any(r["to"]))
        if r["words"]:
            parts.append("(%s)" % _any(r["words"]))
        if r["subject"]:
            parts.append("subject:(%s)" % _any(r["subject"]))
        q = "{%s}" % " ".join(parts) if len(parts) > 1 else "".join(parts)
        if r["not from"]:
            q += " -from:(%s)" % _any(r["not from"])
        out.append((r["label"], q))
    return out


def main():
    rules = parse()
    if "--preview" in sys.argv:
        for label, q in preview(rules):
            print("%s\n  %s\n" % (label, q))
        return 0
    entries = filters(rules)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(xml(entries))
    labels = [r["label"] + (" (skips the inbox)" if r["skip"] else "")
              for r in rules]
    print("Wrote %d filters for %d labels: %s" % (len(entries), len(rules),
                                                   ", ".join(labels)))
    print(OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())

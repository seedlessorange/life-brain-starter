"""Context packs: the briefing a task- or person-scoped conversation opens
with, assembled mechanically — no model call, no cost.

The point is scope. A conversation about "Plan real time with Maman" needs
the task, its workstream, and Maman's people entry — not the whole brain.
Every turn of a conversation resends its context, so what goes in here is
paid for on every exchange: the pack is a page, and it stays a page. The
caps below are the feature, not a limit to raise.

The pack travels inside the first turn's prompt (sessions.py prepends it,
marked as data, not instructions) and never appears in the transcript.
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
    'Maman' finds '## Maman', 'Sloan' finds '## Sloan Eg Ibiza', but 'Al'
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

    label = (task_text or ws_name or "").strip()
    return _finish(parts), label


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
    return _finish(parts), "About " + full


def _finish(parts):
    out = "\n\n".join(p for p in parts if p)
    return out[:PACK_CAP]


def pack(kind, body):
    """The one entry point serve.py calls. Returns (pack_text, label)."""
    if kind == "person":
        return pack_person((body.get("name") or "").strip())
    return pack_task((body.get("ws") or "").strip(),
                     (body.get("task") or "").strip())

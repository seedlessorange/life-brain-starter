#!/usr/bin/env python3
"""What changed in her calendar since the brain last looked, and the tasks a
change touches.

On 8 Oct the week ahead still listed "Meeting with Jack — Thursday" after the
meeting was cancelled and had left her calendar. Nothing compared the two.
This does, two ways, and only ever asks (For you, confirm):

- An event the brain saw for a coming day that is no longer there, or that
  now reads "Canceled: …", is reported once as gone, with the task it
  touches when one names it.
- A meeting task due in the next two days ("Meeting with Jack", "Call with
  Frankie") whose person no event that day mentions is asked about: still on?

The record (brain/.calendar-seen.json, gitignored) holds titles and times of
the coming two weeks only, the same facts the calendar cache already keeps.

    python3 brain/tools/calendar_watch.py    # what it would report now
"""

import json
import os
import re
import sys
from datetime import date, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
BRAIN = os.path.dirname(HERE)
SEEN = os.path.join(BRAIN, ".calendar-seen.json")
HORIZON = 14

_CANCEL = re.compile(r"(?i)^\s*(?:cancell?ed|annulé)\s*:\s*")
_MEET = re.compile(r"(?i)\b(?:meeting|call|session|coffee|lunch|dinner|catch-up)"
                   r"\s+with\s+([A-ZÀ-Ý][\w'’-]+)")


# Words every meeting shares; matching on them tied "Meeting with Jack" to
# "Venture Meeting with Devon".
_GENERIC = {"with", "meeting", "call", "session", "coffee", "lunch", "dinner",
            "from", "about", "this", "that", "into", "catch"}


def _norm(title):
    return " ".join((title or "").lower().split())


def _load():
    try:
        with open(SEEN, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _save(data):
    tmp = SEEN + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(tmp, SEEN)


def look(today=None, events=None, write=True):
    """Compare the calendar now with what was seen before. Returns
    {"gone": [{iso, hhmm, title}], "now": {iso: [titles]}}. With no events
    (calendar off, or a read that failed) nothing is concluded and the record
    is left alone: an empty read is not a cancelled week."""
    today = today or date.today()
    if events is None:
        try:
            import calendar_read
            calendar_read.events(HORIZON + 1)        # refreshes when stale
            # Only this window's own clean read: the stand-ins events()
            # serves (a wider read's slice, the last read) can predate an
            # event, which then read as cancelled.
            events = calendar_read.own_read(HORIZON + 1) or []
        except Exception:
            events = []
    if not events:
        return {"gone": [], "now": {}}
    end = today + timedelta(days=HORIZON)
    now, cancelled = {}, []
    for when, title in events:
        m = re.match(r"(\d{4}-\d{2}-\d{2})(?: (\d{2}:\d{2}))?", when or "")
        if not m or not (today.isoformat() <= m.group(1) <= end.isoformat()):
            continue
        if _CANCEL.match(title or ""):
            cancelled.append({"iso": m.group(1), "hhmm": m.group(2) or "",
                              "title": _CANCEL.sub("", title).strip()})
            continue
        now.setdefault(m.group(1), {})[_norm(title)] = (m.group(2) or "", title)
    data = _load()
    seen = data.get("seen") or {}
    gone = data.get("gone") or {}
    for iso, titles in seen.items():
        if not (today.isoformat() <= iso <= end.isoformat()):
            continue
        for low, (hhmm, title) in titles.items():
            if low not in now.get(iso, {}):
                gone.setdefault(f"{iso}|{low}", {"iso": iso, "hhmm": hhmm,
                                                 "title": title,
                                                 "at": today.isoformat()})
    for c in cancelled:
        gone.setdefault(f"{c['iso']}|{_norm(c['title'])}",
                        dict(c, at=today.isoformat()))
    # Back in the calendar (moved back, or a read that missed it): not gone.
    gone = {k: v for k, v in gone.items()
            if v["iso"] >= today.isoformat()
            and _norm(v["title"]) not in now.get(v["iso"], {})}
    if write:
        merged = {iso: dict(t) for iso, t in seen.items()
                  if iso >= (today - timedelta(days=1)).isoformat()}
        for iso, titles in now.items():
            merged.setdefault(iso, {}).update(titles)
        for k in list(merged):
            merged[k] = {low: v for low, v in merged[k].items()
                         if f"{k}|{low}" not in gone}
        _save({"seen": merged, "gone": gone})
    return {"gone": sorted(gone.values(), key=lambda g: (g["iso"], g["hhmm"])),
            "now": {iso: [v[1] for v in t.values()] for iso, t in now.items()}}


def orphans(items, now_titles, today=None, days=2):
    """Open meeting tasks due within `days` whose person no event that day
    mentions. `items` is model.load()'s workstreams; returns
    [{text, ws, iso, name}]. A day with no read at all is skipped, so a
    calendar that failed to load never makes every meeting look cancelled."""
    today = today or date.today()
    import model as M
    out = []
    for w in items or []:
        if not w.get("live"):
            continue
        for t in w["tasks"]:
            if t["done"] or t.get("parked") or t.get("dropped") or not t.get("due"):
                continue
            m = _MEET.search(t["text"])
            d = M.parse_date(t["due"])
            if not m or not d or not (today <= d <= today + timedelta(days=days)):
                continue
            iso = d.isoformat()
            if iso not in now_titles and not now_titles:
                continue
            name = m.group(1).lower()
            if any(name in _norm(x) for x in now_titles.get(iso, [])):
                continue
            out.append({"text": t["text"], "ws": w["name"], "iso": iso,
                        "name": m.group(1)})
    return out


def touches(gone, items):
    """For each gone event, the open task that names it, if exactly one does:
    its words share at least two distinctive ones (four letters or more, not
    "meeting" or "with") with the event's title. Returns
    [(gone, task-text or None, ws or None)]."""
    def toks(s):
        return {x for x in re.findall(r"[a-zà-ÿ0-9]+", (s or "").lower())
                if len(x) >= 4 and x not in _GENERIC}
    out = []
    for g in gone:
        gt = toks(g["title"])
        hits = []
        for w in items or []:
            if not w.get("live"):
                continue
            for t in w["tasks"]:
                if t["done"] or t.get("dropped"):
                    continue
                if len(gt & toks(t["text"])) >= 2:
                    hits.append((t["text"], w["name"]))
        out.append((g,) + (hits[0] if len(hits) == 1 else (None, None)))
    return out


if __name__ == "__main__":
    sys.path.insert(0, HERE)
    import model as M
    r = look(write=False)
    print(f"gone: {len(r['gone'])}")
    for g, t, w in touches(r["gone"], M.load()):
        print(f"  {g['iso']} {g['hhmm']} {g['title']}" + (f"  -> {t}" if t else ""))
    o = orphans(M.load(), r["now"])
    print(f"meetings with no event: {len(o)}")
    for x in o:
        print(f"  {x['iso']} {x['text']}  ({x['name']} not in that day's calendar)")

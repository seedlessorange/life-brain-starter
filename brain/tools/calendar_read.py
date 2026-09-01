#!/usr/bin/env python3
"""Read today's calendar, locally, so the morning plan knows your real day.

    python3 brain/tools/calendar_read.py            # today's events
    python3 brain/tools/calendar_read.py --days 7   # the week
    python3 brain/tools/calendar_read.py --add-feed <ics url or file>

Two local routes, used together when both exist:

- **macOS Calendar** (Mac only): reads whatever the Calendar app already
  subscribes to, via AppleScript. Add accounts once in System Settings >
  Internet Accounts and this sees them. The first read makes macOS ask
  permission for the terminal — that's expected, a local grant.
- **ICS feeds** (every OS): one calendar address or exported .ics file per
  line in `brain/.calendar-feeds`. Google Calendar calls the address
  "Secret address in iCal format" (calendar settings); Outlook.com has
  "publish calendar". The address is a key — anyone holding it can read
  that calendar — so the feeds file is git-ignored and stays on this
  machine. This tool fetches the feed and parses it here; no account or
  token is involved.

Off by default. Turn it on with `"calendar": true` in config.json; the morning
run then reads it and plans /today around your real commitments.

Titles and times only. It never reads notes, attendees, or locations, and it
writes nothing to any calendar.

Timezone note for Windows: exact TZID handling needs `pip install tzdata`.
Without it, feed times are read as local time — right for your own events,
possibly off for invites from another timezone.
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
from datetime import date, datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
BRAIN = os.path.dirname(HERE)
FEEDS = os.path.join(BRAIN, ".calendar-feeds")


def enabled():
    try:
        with open(os.path.join(BRAIN, "config.json"), encoding="utf-8") as f:
            return bool(json.load(f).get("calendar"))
    except Exception:
        return False


APPLESCRIPT = '''
set startDay to (current date) - (time of (current date))
set endDay to startDay + (%d * days)
set out to ""
tell application "Calendar"
  repeat with c in calendars
    try
      set evs to (every event of c whose start date >= startDay and start date < endDay)
      repeat with e in evs
        set sd to start date of e
        set out to out & (year of sd as string) & "-" & ¬
          (text -2 thru -1 of ("0" & (month of sd as integer))) & "-" & ¬
          (text -2 thru -1 of ("0" & (day of sd))) & " " & ¬
          (text -2 thru -1 of ("0" & (hours of sd))) & ":" & ¬
          (text -2 thru -1 of ("0" & (minutes of sd))) & "\\t" & (summary of e) & linefeed
      end repeat
    end try
  end repeat
end tell
return out
'''


# ---------------------------------------------------------------------------
# ICS feeds — the cross-platform route. Stdlib only, on purpose: the whole
# server runs without pip installs, and a calendar must not be the thing
# that breaks that.

def feeds():
    """The subscribed feeds: one URL or local path per line, # comments."""
    out = []
    try:
        with open(FEEDS, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    out.append(line)
    except OSError:
        pass
    return out


def _fetch_ics(src):
    """The raw text of one feed. A feed that fails reads as empty — the
    page must never break because a calendar server had a bad morning."""
    src = src.strip()
    if src.startswith("webcal://"):
        src = "https://" + src[len("webcal://"):]
    try:
        if src.startswith(("http://", "https://")):
            req = urllib.request.Request(src, headers={"User-Agent": "life-brain"})
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.read().decode("utf-8", errors="replace")
        path = src[len("file://"):] if src.startswith("file://") else src
        with open(os.path.expanduser(path), encoding="utf-8", errors="replace") as f:
            return f.read()
    except Exception:
        return ""


def _unfold(text):
    """ICS wraps long lines; a continuation starts with a space or tab."""
    out = []
    for raw in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if raw[:1] in (" ", "\t") and out:
            out[-1] += raw[1:]
        else:
            out.append(raw)
    return out


def _prop(line):
    """'DTSTART;TZID=Europe/Paris:20260818T090000' -> (name, params, value)."""
    head, _, value = line.partition(":")
    bits = head.split(";")
    params = {}
    for p in bits[1:]:
        k, _, v = p.partition("=")
        params[k.upper()] = v
    return bits[0].upper(), params, value


def _tz(name):
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo(name)
    except Exception:
        return None     # no tzdata (plain Windows): read the time as local


def _parse_dt(value, params):
    """An ICS date or datetime -> naive LOCAL datetime, or None."""
    value = value.strip()
    try:
        if re.fullmatch(r"\d{8}", value):                    # all-day
            return datetime.strptime(value, "%Y%m%d")
        utc = value.endswith("Z")
        dt = datetime.strptime(value.rstrip("Z"), "%Y%m%dT%H%M%S")
    except ValueError:
        return None
    if utc:
        from datetime import timezone
        return dt.replace(tzinfo=timezone.utc).astimezone().replace(tzinfo=None)
    tzname = params.get("TZID")
    if tzname:
        z = _tz(tzname)
        if z is not None:
            return dt.replace(tzinfo=z).astimezone().replace(tzinfo=None)
    return dt                                               # floating = local


_BYDAY = {"MO": 0, "TU": 1, "WE": 2, "TH": 3, "FR": 4, "SA": 5, "SU": 6}


def _rrule_within(start, rrule, exdates, lo, hi):
    """Occurrences of a recurring event inside [lo, hi).

    Plain enumeration from DTSTART with a step cap, because the window is
    always near today and the arithmetic shortcuts are where the bugs live.
    Covers FREQ daily/weekly/monthly/yearly, INTERVAL, BYDAY (weekly, and
    monthly ordinals like 2TU), UNTIL, COUNT. Anything stranger yields what
    it can rather than guessing."""
    rule = {}
    for part in rrule.split(";"):
        k, _, v = part.partition("=")
        rule[k.upper()] = v
    freq = rule.get("FREQ", "").upper()
    interval = max(1, int(rule.get("INTERVAL", "1") or 1))
    count = int(rule["COUNT"]) if rule.get("COUNT", "").isdigit() else None
    until = _parse_dt(rule["UNTIL"], {}) if "UNTIL" in rule else None
    byday = [d for d in rule.get("BYDAY", "").split(",") if d]

    out, made, steps = [], 0, 0

    def emit(dt):
        nonlocal made
        made += 1
        if dt >= hi or (until and dt > until):
            return False
        if lo <= dt and dt not in exdates:
            out.append(dt)
        return True

    if freq == "WEEKLY" and byday:
        # The series is week-blocks; each block holds the named weekdays.
        week0 = start - timedelta(days=start.weekday())
        block = 0
        while steps < 20000:
            wk = week0 + timedelta(weeks=block * interval)
            if wk >= hi:
                break
            for code in sorted(byday, key=lambda c: _BYDAY.get(c[-2:], 0)):
                dt = wk + timedelta(days=_BYDAY.get(code[-2:], 0))
                dt = dt.replace(hour=start.hour, minute=start.minute)
                steps += 1
                if dt < start:
                    continue
                if not emit(dt) or (count and made >= count):
                    return out
            block += 1
        return out

    cur = start
    while steps < 20000:
        steps += 1
        if not emit(cur) or (count and made >= count):
            break
        if freq == "DAILY":
            cur += timedelta(days=interval)
        elif freq == "WEEKLY":
            cur += timedelta(weeks=interval)
        elif freq == "MONTHLY":
            m = (cur.month - 1 + interval) % 12 + 1
            y = cur.year + (cur.month - 1 + interval) // 12
            if byday and re.fullmatch(r"-?\d[A-Z]{2}", byday[0]):
                cur = _nth_weekday(y, m, byday[0], cur)
            else:
                try:
                    cur = cur.replace(year=y, month=m)
                except ValueError:
                    return out          # e.g. the 31st of a short month
        elif freq == "YEARLY":
            try:
                cur = cur.replace(year=cur.year + interval)
            except ValueError:
                return out              # Feb 29
        else:
            break                        # unknown FREQ: the first hit stands
    return out


def _nth_weekday(year, month, code, like):
    """'2TU' -> the 2nd Tuesday of that month; '-1FR' -> the last Friday."""
    n, wd = int(code[:-2]), _BYDAY[code[-2:]]
    days = [datetime(year, month, d, like.hour, like.minute)
            for d in range(1, 32)
            if d <= 28 or _valid_day(year, month, d)]
    hits = [d for d in days if d.weekday() == wd]
    pick = hits[n - 1] if n > 0 else hits[n]
    return pick


def _valid_day(y, m, d):
    try:
        datetime(y, m, d)
        return True
    except ValueError:
        return False


def ics_events(days=1):
    """(datetime_str, title) from every subscribed feed, inside the window.
    Same shape as the Mac read, so everything downstream stays one code path."""
    urls = feeds()
    if not urls:
        return []
    lo = datetime.combine(date.today(), datetime.min.time())
    hi = lo + timedelta(days=days)
    out = []
    for url in urls:
        text = _fetch_ics(url)
        if "BEGIN:VEVENT" not in text:
            continue
        masters, moved, torn = [], {}, {}
        ev = None
        for line in _unfold(text):
            if line.startswith("BEGIN:VEVENT"):
                ev = {}
            elif line.startswith("END:VEVENT") and ev is not None:
                if "start" in ev:
                    if "recurrence_id" in ev:
                        # A moved instance: it appears where it moved TO, and
                        # the slot it moved FROM must not also fire.
                        torn.setdefault(ev.get("uid", ""), set()).add(ev["recurrence_id"])
                        moved.setdefault(ev.get("uid", ""), []).append(ev)
                    else:
                        masters.append(ev)
                ev = None
            elif ev is not None and ":" in line:
                name, params, value = _prop(line)
                if name == "DTSTART":
                    ev["start"] = _parse_dt(value, params)
                    if ev["start"] is None:
                        ev.pop("start", None)
                elif name == "SUMMARY":
                    ev["title"] = value.replace("\\,", ",").replace("\\;", ";") \
                                       .replace("\\n", " ").strip()
                elif name == "RRULE":
                    ev["rrule"] = value
                elif name == "UID":
                    ev["uid"] = value
                elif name == "RECURRENCE-ID":
                    ev["recurrence_id"] = _parse_dt(value, params)
                elif name == "EXDATE":
                    for v in value.split(","):
                        dt = _parse_dt(v, params)
                        if dt:
                            ev.setdefault("exdates", set()).add(dt)
                elif name == "STATUS" and value.strip().upper() == "CANCELLED":
                    ev["cancelled"] = True
        for ev in masters:
            if ev.get("cancelled"):
                continue
            title = ev.get("title", "(untitled)")
            ex = set(ev.get("exdates", set())) | torn.get(ev.get("uid", ""), set())
            if ev.get("rrule"):
                whens = _rrule_within(ev["start"], ev["rrule"], ex, lo, hi)
            else:
                whens = [ev["start"]] if lo <= ev["start"] < hi else []
            for dt in whens:
                out.append((dt.strftime("%Y-%m-%d %H:%M"), title))
        for evs in moved.values():
            for ev in evs:
                if ev.get("cancelled"):
                    continue
                if lo <= ev["start"] < hi:
                    out.append((ev["start"].strftime("%Y-%m-%d %H:%M"),
                                ev.get("title", "(untitled)")))
    return sorted(set(out))


CACHE = os.path.join(BRAIN, ".calendar-cache.json")
CACHE_TTL = 600          # ten minutes: a day's events do not move that fast


def _cached(days):
    try:
        with open(CACHE, encoding="utf-8") as f:
            c = json.load(f)
    except Exception:
        return None
    # One entry per horizon: the Season month grid asks for ~60 days while
    # the Today timeline asks for 1, and a single-slot cache made each evict
    # the other — a 15 s AppleScript wait on every second rebuild.
    ent = (c.get("entries") or {}).get(str(days))
    if ent is None:
        return None
    # Month-scale busyness moves slowly; a long horizon may keep its answer
    # for hours, where today's schedule stays on the ten-minute leash. A
    # FAILED read never earns the long shelf — it retries on the short one.
    ttl = CACHE_TTL if (days <= 7 or ent.get("err")) else 10800
    if time.time() - ent.get("at", 0) > ttl:
        return None
    return [tuple(x) for x in ent.get("events", [])]


def _store(days, evs, err=""):
    try:
        try:
            with open(CACHE, encoding="utf-8") as f:
                entries = json.load(f).get("entries") or {}
        except Exception:
            entries = {}
        now = time.time()
        entries = {k: v for k, v in entries.items()
                   if now - (v.get("at") or 0) < 86400}
        entries[str(days)] = {"at": now, "events": evs, "err": err}
        tmp = CACHE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"entries": entries}, f)
        os.replace(tmp, CACHE)
    except Exception:
        pass


def _raw_entry(days):
    try:
        with open(CACHE, encoding="utf-8") as f:
            return ((json.load(f).get("entries") or {}).get(str(days))) or {}
    except Exception:
        return {}


def last_error(days=1):
    """The mac route's error from the freshest read of this horizon, or "".
    Lets a page tell "a free month" apart from "could not look" — shading
    nothing and looking free when the read failed is a lie."""
    return _raw_entry(days).get("err") or ""


def status(days=1):
    """'ok' | 'warming' (a background read is on its way) | 'error'."""
    ent = _raw_entry(days)
    if ent.get("err"):
        return "error"
    if not ent or (ent.get("kicked") or 0) > (ent.get("at") or 0):
        return "warming"
    return "ok"


def _kick(days):
    """Refresh this horizon in a child process; the caller never waits.
    A long AppleScript scan (a month of events can take minutes) must not
    hang a page rebuild — the rebuild serves the stale answer now and the
    child updates the cache for the next one."""
    try:
        try:
            with open(CACHE, encoding="utf-8") as f:
                c = json.load(f)
        except Exception:
            c = {}
        entries = c.get("entries") or {}
        ent = entries.get(str(days)) or {}
        if time.time() - (ent.get("kicked") or 0) < 300:
            return                      # one child at a time per horizon
        ent["kicked"] = time.time()
        entries[str(days)] = ent
        tmp = CACHE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"entries": entries}, f)
        os.replace(tmp, CACHE)
        subprocess.Popen([sys.executable, os.path.abspath(__file__),
                          "--days", str(days), "--fresh", "--json"],
                         stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL)
    except Exception:
        pass


def _wake_calendar():
    """Make sure Calendar.app is running before we talk to it.

    AppleScript's own `tell application "Calendar" to launch` does NOT start a
    Calendar that is not already running — it fails with -600 ("Application
    isn't running"), and every read on this machine had been failing that way.
    `open -g -j` starts it in the background without stealing focus or opening
    a window, which is the behaviour `launch` was there to get.
    """
    if sys.platform != "darwin":
        return
    try:
        if subprocess.run(["pgrep", "-x", "Calendar"],
                          capture_output=True).returncode == 0:
            return
        subprocess.run(["open", "-g", "-j", "-a", "Calendar"],
                       capture_output=True, timeout=20)
        # It needs a moment to load its stores; querying too early answers
        # with an empty calendar list rather than an error.
        for _ in range(20):
            time.sleep(0.5)
            if subprocess.run(["pgrep", "-x", "Calendar"],
                              capture_output=True).returncode == 0:
                time.sleep(1.5)
                return
    except Exception:
        pass


def _mac_events(days):
    """The macOS Calendar app, via AppleScript. (events, error) — empty
    elsewhere; the error string says WHY a read came back with nothing."""
    if sys.platform != "darwin":
        return [], ""
    _wake_calendar()
    try:
        # These budgets look enormous because the query really is that slow:
        # AppleScript's `whose start date ...` filter walks every event in
        # every calendar, and one 120-day read on this machine measured ~124s.
        # Nothing waits on it — events() always serves the cache and refreshes
        # in a background child — so the only thing a short timeout bought was
        # a guaranteed failure. It must stay under _kick's 300s re-spawn guard
        # so two children never overlap.
        r = subprocess.run(["osascript", "-e", APPLESCRIPT % days],
                           capture_output=True, text=True,
                           timeout=120 if days <= 7 else 240)
    except Exception as exc:
        return [], str(exc)
    if r.returncode != 0:
        return [], (r.stderr or "calendar read failed").strip()[:200]
    out = []
    for line in (r.stdout or "").splitlines():
        if "\t" in line:
            when, title = line.split("\t", 1)
            out.append((when.strip(), title.strip()))
    return out, ""


def events(days=1, fresh=False):
    """List of (datetime_str, title) from every route this machine has:
    the macOS Calendar app on a Mac, plus any subscribed ICS feeds anywhere.

    Cached for ten minutes. Asking the Calendar app takes about thirty
    seconds through AppleScript, and the page rebuilds constantly — reading
    it every time made every rebuild crawl, which the whole page then wore
    as staleness."""
    if not fresh:
        hit = _cached(days)
        if hit is not None:
            return hit
        # Cache miss: serve whatever the last read found (stale beats a
        # blank month) and refresh in the background — a rebuild must never
        # sit through a slow Calendar.
        ent = _raw_entry(days)
        _kick(days)
        return [tuple(x) for x in ent.get("events", [])]
    mac, err = _mac_events(days)
    out = sorted(set(mac) | set(ics_events(days)))
    _store(days, out, err)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=1)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--fresh", action="store_true",
                    help="skip the ten-minute cache")
    ap.add_argument("--add-feed", metavar="URL",
                    help="subscribe to a calendar address or .ics file")
    args = ap.parse_args()
    if args.add_feed:
        got = feeds()
        if args.add_feed.strip() in got:
            print("Already subscribed.")
            return
        probe = _fetch_ics(args.add_feed)
        if "BEGIN:VEVENT" not in probe and "BEGIN:VCALENDAR" not in probe:
            sys.exit("That doesn't read as a calendar. For Google Calendar, "
                     "use Settings > your calendar > 'Secret address in iCal "
                     "format'; for Outlook.com, publish the calendar and use "
                     "the ICS link.")
        with open(FEEDS, "a", encoding="utf-8") as f:
            f.write(args.add_feed.strip() + "\n")
        print(f"Subscribed ({len(got) + 1} feed(s)). The address stays in "
              f"brain/.calendar-feeds on this machine — it is never committed.")
        if not enabled():
            print('Now set "calendar": true in brain/config.json so /today '
                  'reads it.')
        return
    evs = events(args.days, fresh=args.fresh)
    if args.json:
        print(json.dumps([{"when": w, "title": t} for w, t in evs]))
        return
    if not evs:
        print("No events (or no calendar access on this machine — on a Mac "
              "grant Calendar access, on any OS subscribe a feed with "
              "--add-feed).")
        return
    for when, title in evs:
        print(f"  {when}  {title}")


if __name__ == "__main__":
    main()

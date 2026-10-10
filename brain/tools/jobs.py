#!/usr/bin/env python3
"""jobs.py — the job hunt: which roles are open at the companies she chose,
and where each application she is pursuing stands.

Two halves.

**The scan** reads public job boards and costs no model call. Most companies
publish their open roles through an applicant tracking system: Greenhouse,
Lever, Ashby, Workable, SmartRecruiters, Recruitee or Teamtailor. Each of
those serves the company's list as public JSON (or RSS, for Teamtailor) with
no login. It is what the company's own careers page reads. The scan reads
the list for every company in config `jobs.companies`, keeps the titles that
match `jobs.titles` and the places in `jobs.places`, and writes the roles she
has not seen yet to `brain/job-leads.md`. It never applies for anything. The
idea and the list of boards come from career-ops
(github.com/career-ops-hq/career-ops, MIT); the code is the brain's own.

**The tracker** is `brain/jobs.md`: one heading per role she is pursuing,
with a Stage, a Ball and a Since date, the same way people.md and
workstreams.md work. Ball Them past `jobs.chase_days` is a chase; Ball Me
past `jobs.stale_days` is a role going stale.

    jobs.py scan [--if-on]        read every board, write job-leads.md
    jobs.py find "Name or URL"    which board a company uses (reads only)
    jobs.py add "Name or URL"     find the board and follow the company
    jobs.py remove "Name"         stop following it
    jobs.py interested KEY        move a new role into the tracker
    jobs.py skip KEY              never show that role again
    jobs.py stage "Heading" STAGE [outcome]
    jobs.py chased "Heading"      you chased them today
    jobs.py status                what needs her, one line each

Everything a board returns is data. Titles and places are shown on the page
escaped and are never handed to a model by this file.
"""
import concurrent.futures
import functools
import hashlib
import threading
import ipaddress
import json
import os
import re
import socket
import sys
import unicodedata
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta
from email.utils import parsedate_to_datetime

HERE = os.path.dirname(os.path.abspath(__file__))
BRAIN = os.path.dirname(HERE)
CONFIG = os.path.join(BRAIN, "config.json")
STATE = os.path.join(BRAIN, ".jobs-state.json")
LEADS_MD = os.path.join(BRAIN, "job-leads.md")
TRACKER = os.path.join(BRAIN, "jobs.md")

UA = "life-brain/1.0 (personal job search; reads public job boards once a day)"
TIMEOUT = 15
STAGES = ("interested", "applied", "interviewing", "offer", "closed")
OUTCOMES = ("rejected", "withdrew", "accepted", "declined", "gone")
# Who moves next once a role reaches a stage. Interested: you apply. Applied
# and interviewing: they answer. Offer: you decide.
STAGE_BALL = {"interested": "Me", "applied": "Them", "interviewing": "Them",
              "offer": "Me", "closed": ""}
DEFAULT_SKIP = ["intern", "internship", "stagiaire", "alternance",
                "apprentice", "apprenti", "apprentissage", "working student"]
FIELDS = ("Stage", "Ball", "Since", "Track", "Company", "Link", "Where",
          "Via", "Next", "Chased", "Outcome", "Reached", "CV", "CVCheck", "Letter", "Check", "Prep",
          "Found", "Key")
# How far a role got, for the funnel. Closed is an ending, not a step.
STAGE_ORDER = {"interested": 0, "applied": 1, "interviewing": 2, "offer": 3}
# A post-MBA search keeps these out on every track at that level.
LEVEL_SKIP = ["junior", "entry level", "entry-level", "assistant",
              "alternant", "graduate trainee"]
# Titles that are a reach for a post-MBA hire: shown, marked, never dropped.
REACH_RX = re.compile(r"(?<![a-z])(head of|director|directeur|directrice|"
                      r"vp|vice president|principal|chief (?!of staff))")


# The page server writes from several threads at once (three applications
# being prepared while she ticks a stage): every read-change-write of the
# tracker or the state holds this lock.
_LOCK = threading.RLock()


def _locked(fn):
    @functools.wraps(fn)
    def wrap(*a, **kw):
        with _LOCK:
            return fn(*a, **kw)
    return wrap


# ------------------------------------------------------------------ config

def _config():
    try:
        with open(CONFIG, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_config(cfg):
    import config_io
    config_io.save(CONFIG, cfg)


def jobs_cfg(cfg=None):
    j = dict((cfg if cfg is not None else _config()).get("jobs") or {})
    j.setdefault("on", False)
    j.setdefault("titles", [])
    j.setdefault("skip", list(DEFAULT_SKIP))
    j.setdefault("places", [])
    j.setdefault("companies", [])
    j.setdefault("chase_days", 7)
    j.setdefault("stale_days", 5)
    return j


def tracks(jc=None):
    """Her searches. A track is a name, the titles that count, the places,
    a level and her one line on why. A brain with no tracks yet has one,
    "My search", made from the plain role words and places."""
    jc = jc if jc is not None else jobs_cfg()
    raw = [t for t in jc.get("tracks") or []
           if isinstance(t, dict) and t.get("name") and t.get("titles")]
    if not raw and jc.get("titles"):
        raw = [{"name": "My search", "titles": jc["titles"],
                "places": jc.get("places") or []}]
    out = []
    for t in raw:
        level = t.get("level") or "post-mba"
        out.append({"name": t["name"].strip()[:60],
                    "titles": list(t["titles"]),
                    "places": list(t.get("places") or jc.get("places") or []),
                    "skip": list(jc.get("skip") or []) + list(t.get("skip") or [])
                    + (LEVEL_SKIP if level == "post-mba" else []),
                    "level": level, "why": (t.get("why") or "").strip()[:600]})
    return out


def all_titles(jc=None):
    seen, out = set(), []
    for t in tracks(jc):
        for x in t["titles"]:
            if x.lower() not in seen:
                seen.add(x.lower())
                out.append(x)
    return out


def track_matcher(jc=None, ignore_places=False):
    """role -> the names of the tracks it fits, in her order."""
    jc = jc if jc is not None else jobs_cfg()
    ms = [(t["name"], matcher(dict(jc, titles=t["titles"], skip=t["skip"],
                                   places=[] if ignore_places else t["places"])))
          for t in tracks(jc)]
    return lambda role: [n for n, ok in ms if ok(role)]


def is_reach(title):
    return bool(REACH_RX.search(fold(title)))


def set_tracks(items):
    """The tracks from the page: the whole list, in her order."""
    clean = []
    names = set()
    for t in items or []:
        name = re.sub(r"\s+", " ", str(t.get("name") or "")).strip()[:60]
        if not name or name.lower() in names:
            continue
        names.add(name.lower())
        def _list(v, n=40):
            if isinstance(v, str):
                v = v.split(",")
            out = []
            for x in v or []:
                x = re.sub(r"\s+", " ", str(x)).strip()[:60]
                if x and x.lower() not in [o.lower() for o in out]:
                    out.append(x)
            return out[:n]
        clean.append({"name": name, "titles": _list(t.get("titles")),
                      "places": _list(t.get("places"), 12),
                      "level": "any" if t.get("level") == "any" else "post-mba",
                      "why": re.sub(r"\s+", " ", str(t.get("why") or "")).strip()[:600]})
    cfg = _config()
    cfg.setdefault("jobs", {})["tracks"] = clean
    _save_config(cfg)
    return clean


def is_on(cfg=None):
    try:
        return bool(jobs_cfg(cfg).get("on"))
    except Exception:
        return False


def set_prefs(titles=None, places=None, skip=None):
    """Her words for what she looks for, from the page or the command line.
    Comma-separated text or a list; blanks dropped, order kept."""
    def _clean(v):
        if isinstance(v, str):
            v = v.split(",")
        out = []
        for x in v or []:
            x = re.sub(r"\s+", " ", str(x)).strip()
            if x and x.lower() not in [o.lower() for o in out]:
                out.append(x[:60])
        return out[:40]
    cfg = _config()
    j = cfg.setdefault("jobs", {})
    if titles is not None:
        j["titles"] = _clean(titles)
    if places is not None:
        j["places"] = _clean(places)
    if skip is not None:
        j["skip"] = _clean(skip)
    _save_config(cfg)
    return jobs_cfg(cfg)


# ------------------------------------------------------------------ boards

SLUG_RX = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,80}$")
SUB_RX = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")   # a slug that is a subdomain

# Each board: its API address for a slug, and the URL shapes that name one.
# The order is also the tie-break in find(): the boards with the richest
# public data first.
BOARDS = {
    "ashby": {
        "label": "Ashby",
        "api": "https://api.ashbyhq.com/posting-api/job-board/{s}",
        "urls": [r"jobs\.ashbyhq\.com/([^/?#]+)",
                 r"api\.ashbyhq\.com/posting-api/job-board/([^/?#]+)"],
    },
    "greenhouse": {
        "label": "Greenhouse",
        "api": "https://boards-api.greenhouse.io/v1/boards/{s}/jobs",
        "urls": [r"(?:job-)?boards(?:\.eu)?\.greenhouse\.io/(?!embed\b)([^/?#]+)",
                 r"boards-api\.greenhouse\.io/v1/boards/([^/?#]+)",
                 r"greenhouse\.io/embed/job_board\?for=([^&#]+)"],
    },
    "lever": {
        "label": "Lever",
        "api": "https://api.lever.co/v0/postings/{s}?mode=json",
        "urls": [r"(?<!eu\.)jobs\.lever\.co/([^/?#]+)",
                 r"(?<!eu\.)api\.lever\.co/v0/postings/([^/?#]+)"],
    },
    "lever-eu": {
        "label": "Lever",
        "api": "https://api.eu.lever.co/v0/postings/{s}?mode=json",
        "urls": [r"jobs\.eu\.lever\.co/([^/?#]+)",
                 r"api\.eu\.lever\.co/v0/postings/([^/?#]+)"],
    },
    "workable": {
        "label": "Workable",
        "api": "https://apply.workable.com/api/v1/widget/accounts/{s}",
        "urls": [r"apply\.workable\.com/(?!api\b|j\b)([^/?#]+)",
                 r"([a-z0-9-]+)\.workable\.com"],
    },
    "smartrecruiters": {
        "label": "SmartRecruiters",
        "api": ("https://api.smartrecruiters.com/v1/companies/{s}/postings"
                "?limit=100&offset={o}"),
        "urls": [r"(?:careers|jobs)\.smartrecruiters\.com/([^/?#]+)",
                 r"api\.smartrecruiters\.com/v1/companies/([^/?#]+)"],
    },
    "recruitee": {
        "label": "Recruitee",
        "api": "https://{s}.recruitee.com/api/offers/",
        "urls": [r"([a-z0-9-]+)\.recruitee\.com"],
        "sub": True,
    },
    "workday": {
        "label": "Workday",
        # The slug is "tenant/wdN/site": Workday hosts each employer on a
        # numbered pod, and one employer can run several career sites.
        "api": "https://{t}.{wd}.myworkdayjobs.com/wday/cxs/{t}/{site}/jobs",
        "urls": [r"([a-z0-9-]+)\.(wd\d{1,3})\.myworkdayjobs\.com/(?:[a-z]{2}-[A-Z]{2}/)?([A-Za-z0-9_-]+)"],
    },
    "teamtailor": {
        "label": "Teamtailor",
        "api": "https://{s}.teamtailor.com/jobs.rss",
        "urls": [r"([a-z0-9-]+)\.teamtailor\.com"],
        "sub": True,
    },
}
# Subdomains of the boards' own sites that are never a company.
_NOT_A_TENANT = {"www", "api", "app", "apply", "jobs", "careers", "boards",
                 "job-boards", "help", "support", "status", "blog", "eu"}


WORKDAY_RX = re.compile(r"^[a-z0-9-]{1,63}/wd\d{1,3}/[A-Za-z0-9_-]{1,80}$")


def _valid_slug(board, slug):
    if not slug or board not in BOARDS:
        return False
    if board == "workday":
        return bool(WORKDAY_RX.match(slug))
    if BOARDS[board].get("sub"):
        return bool(SUB_RX.match(slug)) and slug not in _NOT_A_TENANT
    return bool(SLUG_RX.match(slug)) and slug.lower() not in _NOT_A_TENANT


def board_from_url(text):
    """(board, slug) when the text is a job-board address, else None."""
    t = (text or "").strip()
    for board, b in BOARDS.items():
        for rx in b["urls"]:
            m = re.search(rx, t, re.I)
            if m and board == "workday":
                slug = "%s/%s/%s" % (m.group(1).lower(), m.group(2).lower(),
                                     m.group(3))
                if slug.split("/")[2].lower() in ("wday", "job", "details"):
                    continue
                if _valid_slug(board, slug):
                    return board, slug
                continue
            if m:
                slug = urllib.parse.unquote(m.group(1)).strip()
                if b.get("sub"):
                    slug = slug.lower()
                if _valid_slug(board, slug):
                    return board, slug
    return None


def api_url(board, slug, offset=0):
    if not _valid_slug(board, slug):
        raise ValueError("not a job board name: %r" % slug)
    if board == "workday":
        t, wd, site = slug.split("/")
        return BOARDS[board]["api"].format(t=t, wd=wd, site=site)
    return BOARDS[board]["api"].format(s=urllib.parse.quote(slug, safe=""),
                                       o=int(offset))


def _get(url, timeout=TIMEOUT, body=None):
    req = urllib.request.Request(url, headers={
        "User-Agent": UA, "Accept": "application/json, application/rss+xml, */*",
        **({"Content-Type": "application/json"} if body is not None else {})},
        data=json.dumps(body).encode() if body is not None else None)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read(8 * 1024 * 1024)


def _wd_where(text):
    # "2 Locations" names no place: unknown, so the place filter keeps it.
    t = (text or "").strip()
    return "" if re.fullmatch(r"\d+ Locations?", t, re.I) else t


def _workday(slug, titles):
    """Workday answers a search, twenty roles a page. A big employer lists
    thousands, so it is asked once per role word she looks for (or once for
    everything when she has none), at most a hundred roles each."""
    t, wd, site = slug.split("/")
    base = "https://%s.%s.myworkdayjobs.com" % (t, wd)
    seen, out = set(), []
    for q in (titles or [""])[:8]:
        for offset in range(0, 100, 20):
            j = json.loads(_get(api_url("workday", slug), body={
                "appliedFacets": {}, "limit": 20, "offset": offset,
                "searchText": q}))
            posts = j.get("jobPostings") or []
            for x in posts:
                path = x.get("externalPath") or ""
                if not path.startswith("/job/") or path in seen:
                    continue
                seen.add(path)
                out.append(_role("workday", slug, path.rsplit("_", 1)[-1],
                                 x.get("title"), "%s/en-US/%s%s" % (base, site, path),
                                 _wd_where(x.get("locationsText")), False, ""))
            if len(posts) < 20 or offset + 20 >= int(j.get("total") or 0):
                break
    return out


def _day(v):
    """Any of the boards' date shapes, as YYYY-MM-DD, or ""."""
    if v in (None, ""):
        return ""
    try:
        if isinstance(v, (int, float)):            # Lever: milliseconds
            return datetime.utcfromtimestamp(v / 1000).strftime("%Y-%m-%d")
        s = str(v).strip()
        if re.match(r"\d{4}-\d{2}-\d{2}", s):
            return s[:10]
        return parsedate_to_datetime(s).strftime("%Y-%m-%d")   # RSS
    except Exception:
        return ""


def _join(*parts):
    seen, out = set(), []
    for p in parts:
        p = re.sub(r"\s+", " ", str(p or "")).strip(" ,;")
        if p and p.lower() not in seen:
            seen.add(p.lower())
            out.append(p)
    return " · ".join(out)


def _flat(v):
    """One line. A board's location once carried a newline and a planted
    "- CV:" line into the tracker, and the filler attached that file."""
    return re.sub(r"\s+", " ", str(v or "")).strip()


def _role(board, slug, rid, title, url, where, remote=False, posted=""):
    return {"key": "%s:%s:%s" % (board, slug.lower(), rid),
            "title": _flat(title), "url": _flat(url), "where": _flat(where),
            "remote": bool(remote), "posted": _flat(posted)}


def _parse(board, slug, raw):
    """The board's answer, as roles in one shape."""
    out = []
    if board == "teamtailor":
        root = ET.fromstring(raw)
        ns = {"tt": "https://teamtailor.com/locations"}
        for it in root.iter("item"):
            locs = [_join(l.findtext("tt:city", "", ns) or
                          l.findtext("tt:name", "", ns),
                          l.findtext("tt:country", "", ns))
                    for l in it.findall("tt:locations/tt:location", ns)]
            rs = (it.findtext("remoteStatus") or "").lower()
            out.append(_role(board, slug, it.findtext("guid") or
                             it.findtext("link"), it.findtext("title"),
                             it.findtext("link"), " | ".join(locs),
                             rs in ("fully", "remote", "temporary"),
                             _day(it.findtext("pubDate"))))
        return out
    j = json.loads(raw)
    if board == "greenhouse":
        for x in j.get("jobs") or []:
            out.append(_role(board, slug, x.get("id"), x.get("title"),
                             x.get("absolute_url"),
                             (x.get("location") or {}).get("name", ""),
                             False, _day(x.get("first_published") or
                                         x.get("updated_at"))))
    elif board in ("lever", "lever-eu"):
        for x in j if isinstance(j, list) else []:
            c = x.get("categories") or {}
            locs = c.get("allLocations") or [c.get("location")]
            out.append(_role(board, slug, x.get("id"), x.get("text"),
                             x.get("hostedUrl"), " | ".join(filter(None, locs)),
                             (x.get("workplaceType") or "") == "remote",
                             _day(x.get("createdAt"))))
    elif board == "ashby":
        for x in j.get("jobs") or []:
            if x.get("isListed") is False:
                continue
            locs = [x.get("location")] + [
                (s or {}).get("location") for s in x.get("secondaryLocations") or []]
            out.append(_role(board, slug, x.get("id"), x.get("title"),
                             x.get("jobUrl"), " | ".join(filter(None, locs)),
                             bool(x.get("isRemote")) or
                             (x.get("workplaceType") or "").lower() == "remote",
                             _day(x.get("publishedAt"))))
    elif board == "workable":
        for x in j.get("jobs") or []:
            locs = [_join(l.get("city"), l.get("country"))
                    for l in x.get("locations") or [] if not l.get("hidden")]
            where = " | ".join(filter(None, locs)) or _join(x.get("city"),
                                                            x.get("country"))
            out.append(_role(board, slug, x.get("shortcode"), x.get("title"),
                             x.get("url") or x.get("shortlink"), where,
                             bool(x.get("telecommuting")),
                             _day(x.get("published_on"))))
    elif board == "smartrecruiters":
        for x in j.get("content") or []:
            loc = x.get("location") or {}
            out.append(_role(
                board, slug, x.get("id"), x.get("name"),
                "https://jobs.smartrecruiters.com/%s/%s"
                % (urllib.parse.quote(slug), x.get("id")),
                loc.get("fullLocation") or _join(loc.get("city"),
                                                 loc.get("country")),
                bool(loc.get("remote")), _day(x.get("releasedDate"))))
    elif board == "recruitee":
        for x in j.get("offers") or []:
            out.append(_role(board, slug, x.get("id") or x.get("guid"),
                             x.get("title") or x.get("sharing_title"),
                             x.get("careers_url"),
                             x.get("location") or _join(x.get("city"),
                                                        x.get("country")),
                             bool(x.get("remote")), _day(x.get("published_at"))))
    return [r for r in out if r["title"] and r["url"].startswith("https://")]


def fetch_board(board, slug, titles=None):
    """Every open role on one company's board."""
    if board == "workday":
        return _workday(slug, titles)
    if board == "smartrecruiters":
        roles, offset = [], 0
        while offset < 1000:                       # ten pages is plenty
            j = json.loads(_get(api_url(board, slug, offset)))
            roles += _parse(board, slug, json.dumps(j))
            offset += 100
            if offset >= int(j.get("totalFound") or 0):
                break
        return roles
    return _parse(board, slug, _get(api_url(board, slug)))


# ------------------------------------------------------------------ posting text

def _html_text(raw):
    """A posting's HTML as plain text, for reading only."""
    import html as _h
    t = _h.unescape(raw or "")
    t = re.sub(r"(?is)<(script|style)\b.*?</\1>", " ", t)
    t = re.sub(r"(?i)<br\s*/?>|</(p|li|div|h\d)>", "\n", t)
    t = re.sub(r"<[^>]+>", " ", t)
    t = _h.unescape(t)
    t = re.sub(r"[ \t\r\f\v]+", " ", t)
    return re.sub(r"\n\s*\n+", "\n\n", t).strip()


_LIST_CACHE = {}


def _from_list(board, slug, rid, field):
    """Boards with no per-role address: the role's text from the list."""
    k = (board, slug)
    if k not in _LIST_CACHE:
        raw = _get(api_url(board, slug).replace("?limit=100&offset=0", ""))
        _LIST_CACHE[k] = raw
    raw = _LIST_CACHE[k]
    if board == "teamtailor":
        for it in ET.fromstring(raw).iter("item"):
            if (it.findtext("guid") or it.findtext("link")) == rid:
                return _html_text(it.findtext("description"))
        return ""
    j = json.loads(raw)
    items = j.get("jobs") or j.get("offers") or []
    for x in items:
        if str(x.get("id") or x.get("shortcode") or x.get("guid")) == rid:
            return _html_text(" ".join(str(x.get(f) or "") for f in field))
    return ""


def job_text(role, limit=9000):
    """The full text of one posting, from the same public source the scan
    read. Untrusted: it goes to a model only in a no-tools call, as data."""
    key = role.get("key", "")
    kind, _, rest = key.partition(":")
    slug, _, rid = rest.rpartition(":")
    try:
        if kind == "greenhouse":
            j = json.loads(_get("https://boards-api.greenhouse.io/v1/boards/"
                                "%s/jobs/%s" % (urllib.parse.quote(slug), rid)))
            text = _html_text(j.get("content"))
        elif kind in ("lever", "lever-eu"):
            host = "api.eu.lever.co" if kind == "lever-eu" else "api.lever.co"
            j = json.loads(_get("https://%s/v0/postings/%s/%s" % (
                host, urllib.parse.quote(slug), rid)))
            text = "\n\n".join([j.get("descriptionPlain") or ""] + [
                (l.get("text") or "") + "\n" + _html_text(l.get("content"))
                for l in j.get("lists") or []] + [j.get("additionalPlain") or ""])
        elif kind == "ashby":
            # Ashby keys are lower-cased slugs; the list answers either way.
            text = _from_list("ashby", slug, rid, ["descriptionPlain"]) or \
                _from_list("ashby", slug, rid, ["descriptionHtml"])
        elif kind == "workable":
            _LIST_CACHE.setdefault(("workable", slug), _get(
                api_url("workable", slug) + "?details=true"))
            text = _from_list("workable", slug, rid, ["description"])
        elif kind == "smartrecruiters":
            j = json.loads(_get("https://api.smartrecruiters.com/v1/companies/"
                                "%s/postings/%s" % (urllib.parse.quote(slug), rid)))
            secs = ((j.get("jobAd") or {}).get("sections") or {})
            text = "\n\n".join(_html_text((v or {}).get("text"))
                                for v in secs.values() if isinstance(v, dict))
        elif kind == "recruitee":
            text = _from_list("recruitee", slug, rid, ["description",
                                                       "requirements"])
        elif kind == "teamtailor":
            text = _from_list("teamtailor", slug, rid, [])
        elif kind == "workday":
            t, wd, site = slug.split("/")
            path = "/job/" + role.get("url", "").split("/job/", 1)[-1]
            j = json.loads(_get("https://%s.%s.myworkdayjobs.com/wday/cxs/%s/"
                                "%s%s" % (t, wd, t, site, path)))
            text = _html_text((j.get("jobPostingInfo") or {}).get("jobDescription"))
        elif kind == "linkedin":
            raw = _get("https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/"
                       + urllib.parse.quote(rid)).decode("utf-8", "replace")
            m = re.search(r'(?s)class="show-more-less-html__markup[^"]*">(.*?)</div>', raw)
            text = _html_text(m.group(1) if m else raw)
        elif role.get("url", "").startswith("https://") and _public_https(role["url"]):
            text = _html_text(_get(role["url"]).decode("utf-8", "replace"))
        else:
            text = ""
    except Exception:                                           # noqa: BLE001
        text = ""
    return text[:limit]


# ------------------------------------------------------------------ finding

def _public_https(url):
    """A careers page she pasted may be read once to find the board it uses,
    but only over https and only on the public internet: never this Mac,
    the home network or the tailnet."""
    u = urllib.parse.urlparse(url)
    if u.scheme != "https" or not u.hostname:
        return False
    try:
        infos = socket.getaddrinfo(u.hostname, 443)
    except OSError:
        return False
    for info in infos:
        ip = ipaddress.ip_address(info[4][0].split("%")[0])
        if (ip.is_private or ip.is_loopback or ip.is_link_local
                or ip.is_reserved or ip.is_multicast
                or ip in ipaddress.ip_network("100.64.0.0/10")):
            return False
    return True


def _count(board, slug):
    if board == "workday":
        try:
            return int(json.loads(_get(api_url(board, slug), body={
                "appliedFacets": {}, "limit": 1, "offset": 0,
                "searchText": ""})).get("total") or 0)
        except Exception:
            return None
    try:
        return len(fetch_board(board, slug)) if board != "smartrecruiters" \
            else int(json.loads(_get(api_url(board, slug)
                                     .replace("limit=100", "limit=1")))
                     .get("totalFound") or 0)
    except Exception:
        return None


def _slug_guesses(name):
    base = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    base = re.sub(r"\b(sas|sa|inc|ltd|gmbh|ai|hq|group|labs?)\b\.?", " ",
                  base.lower()).strip()
    words = re.findall(r"[a-z0-9]+", base) or re.findall(r"[a-z0-9]+",
                                                         name.lower())
    out = []
    for g in ("".join(words), "-".join(words), words[0] if words else "",
              "".join(re.findall(r"[a-z0-9]+", name.lower()))):
        if g and g not in out:
            out.append(g)
    return out[:4]


def find(text):
    """Which job board a company uses, from its name, its careers page or a
    board address. Reads only. Returns {name, board, slug, count} or
    {error}."""
    t = (text or "").strip()
    if not t:
        return {"error": "type a company name or paste its careers page"}
    hit = board_from_url(t)
    name = ""
    if not hit and re.match(r"(?i)^https?://", t):
        # A company's own careers page: read it once for a link to its board.
        if not _public_https(t):
            return {"error": "that address is not a public https page"}
        try:
            page = _get(t, timeout=12).decode("utf-8", "replace")
        except Exception as ex:                                 # noqa: BLE001
            return {"error": "could not read that page (%s)" % type(ex).__name__}
        for m in re.finditer(r"https?://[^\s\"'<>]+", page):
            hit = board_from_url(m.group(0))
            if hit:
                break
        if not hit:
            host = urllib.parse.urlparse(t).hostname or ""
            name = re.sub(r"^(www|careers|jobs)\.", "", host).split(".")[0]
    if hit:
        n = _count(*hit)
        if n is None:
            return {"error": "%s has no public %s board under '%s'"
                    % (t, BOARDS[hit[0]]["label"], hit[1])}
        return {"name": _nice_name(name or hit[1]), "board": hit[0],
                "slug": hit[1], "count": n}
    name = name or t
    tries = [(b, s) for s in _slug_guesses(name) for b in BOARDS
             if b != "workday" and _valid_slug(b, s)]
    with concurrent.futures.ThreadPoolExecutor(12) as ex:
        counts = list(ex.map(lambda bs: _count(*bs), tries))
    best = None
    for (b, s), n in zip(tries, counts):
        if n and (best is None or n > best[2]):
            best = (b, s, n)
    if not best:
        return {"error": "found no public job board for %s. Paste its careers"
                " page and I'll look for the board it uses." % name}
    return {"name": _nice_name(name), "board": best[0], "slug": best[1],
            "count": best[2]}


def _nice_name(s):
    s = (s or "").strip()
    s = s.split("/")[0]                             # Workday: the tenant
    s = re.sub(r"(?<=[A-Za-z])\d+$", "", s)       # Ubisoft2 -> Ubisoft
    if s and s == s.lower() and not re.match(r"https?://", s):
        s = " ".join(w.capitalize() for w in re.split(r"[-_\s]+", s) if w)
    return s


def add_company(text, name=None, lock=None):
    """Follow a company. The board is found first (a web read); the config
    change after it runs under `lock`, the page server's write lock when it
    calls, so a page write landing meanwhile isn't lost."""
    r = find(text)
    with (lock or _LOCK):
        return _add_found(r, text, name)


def _add_found(r, text, name):
    if r.get("error"):
        # No public board: a careers page the browser helper can read, when
        # she has switched that helper on.
        t = (text or "").strip()
        try:
            import browser_core as BC
            scan_on = BC.switched_on().get("scan")
        except Exception:                                       # noqa: BLE001
            scan_on = False
        if scan_on and re.match(r"^https://", t) and _public_https(t):
            cfg = _config()
            pages = cfg.setdefault("jobs", {}).setdefault("pages", [])
            host = urllib.parse.urlparse(t).hostname or t
            nm = (name or "").strip() or _nice_name(
                re.sub(r"^(www|careers|jobs)\.", "", host).split(".")[0])
            if not any(p.get("url") == t for p in pages):
                pages.append({"name": nm, "url": t})
                _save_config(cfg)
            return {"name": nm, "page": True, "added": True, "count": 0}
        return r
    cfg = _config()
    j = cfg.setdefault("jobs", {})
    comps = j.setdefault("companies", [])
    nm = (name or "").strip() or r["name"]
    for c in comps:
        if (c.get("board"), str(c.get("slug", "")).lower()) == \
                (r["board"], r["slug"].lower()):
            return dict(r, name=c.get("name"), already=True)
    comps.append({"name": nm, "board": r["board"], "slug": r["slug"]})
    _save_config(cfg)
    return dict(r, name=nm, added=True)


def remove_company(name):
    cfg = _config()
    j = cfg.setdefault("jobs", {})
    pages = j.get("pages") or []
    if any(p.get("name") == name for p in pages):
        j["pages"] = [p for p in pages if p.get("name") != name]
        _save_config(cfg)
        return {"ok": True}
    before = j.get("companies") or []
    j["companies"] = [c for c in before
                      if (c.get("name") or "").lower() != (name or "").strip().lower()]
    if len(j["companies"]) == len(before):
        return {"error": "not following %s" % name}
    _save_config(cfg)
    st = _state()
    st["roles"] = {k: v for k, v in st["roles"].items()
                   if not (v.get("company") == name and v.get("status") == "new")}
    _save_state(st)
    write_leads(st)
    return {"ok": True}


# ------------------------------------------------------------------ matching

def fold(s):
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore")
    return re.sub(r"\s+", " ", s.decode().lower()).strip()


def _term(term, whole):
    """A keyword as a pattern. A role word matches from the start of a word
    ("product" finds "Product Manager", not "byproduct"); a skip word, and
    any word of three letters or fewer, must be the whole word, so "intern"
    never drops "International" and "PM" never fires inside "NPM"."""
    t = fold(term)
    if not t:
        return None
    body = re.escape(t).replace(r"\ ", r"[\s\-/]+")
    if whole or len(t) <= 3:
        return re.compile(r"(?<![a-z0-9])%s(?:s|es)?(?![a-z0-9])" % body)
    return re.compile(r"(?<![a-z0-9])%s" % body)


_REMOTE_WORDS = ["remote", "full remote", "fully remote", "teletravail",
                 "anywhere", "worldwide", "global", "hybrid", "or", "and"]
_REGIONS = ["emea", "europe", "eu", "european union", "cet", "timezone",
            "time zone", "utc", "gmt"]
_STAGE_RX = re.compile(r"^stage\b|[(\-|:]\s*stage\b|\bstage\s*[(\-|:)]")


def matcher(jc):
    pos = [p for p in (_term(t, False) for t in jc.get("titles") or []) if p]
    neg = [p for p in (_term(t, True) for t in jc.get("skip") or []) if p]
    places = [fold(p) for p in jc.get("places") or [] if fold(p)]
    # "Stage" is French for internship, but only where a title says so:
    # "Stage - Sales Analyst" or "Analyst (stage)", never "Late Stage
    # Investor". On whenever the skip list keeps interns out.
    intern_fr = any(fold(t) in ("stagiaire", "stage", "intern", "internship")
                    for t in jc.get("skip") or [])
    want_remote = any(p in _REMOTE_WORDS[:4] for p in places)

    def ok(role):
        title = fold(role.get("title"))
        if not pos or not any(p.search(title) for p in pos):
            return False
        if any(n.search(title) for n in neg):
            return False
        if intern_fr and _STAGE_RX.search(title):
            return False
        if not places:
            return True
        where = fold(role.get("where"))
        if not where:
            return True                    # the board did not say: keep it
        if any(p in where for p in places if p not in _REMOTE_WORDS):
            return True
        # Remote counts only when the posting names no other place: "Remote"
        # or "Remote, EMEA" yes, "Remote in Spain" no. Boards flag a job
        # remote within one country, and that country is the real filter.
        if want_remote and (role.get("remote") or "remote" in where):
            rest = re.sub(r"\b(%s)\b" % "|".join(_REMOTE_WORDS + _REGIONS),
                          " ", where)
            return not re.search(r"[a-z]{3,}", rest)
        return False
    return ok


# ------------------------------------------------------------------ state

def _state():
    try:
        with open(STATE, encoding="utf-8") as f:
            st = json.load(f)
    except Exception:
        st = {}
    st.setdefault("roles", {})
    st.setdefault("companies", {})
    return st


def _save_state(st):
    tmp = STATE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(st, f, indent=1, ensure_ascii=False)
    os.replace(tmp, STATE)


def scan(today=None):
    """Read every board she follows and keep what is new and matches."""
    today = today or date.today()
    jc = jobs_cfg()
    comps = [c for c in jc["companies"] if _valid_slug(c.get("board"),
                                                       c.get("slug"))]
    tm = track_matcher(jc)

    def one(c):
        try:
            return c, fetch_board(c["board"], c["slug"], all_titles(jc)), ""
        except Exception as ex:                                 # noqa: BLE001
            return c, None, "%s: %s" % (type(ex).__name__, str(ex)[:80])

    with concurrent.futures.ThreadPoolExecutor(8) as ex:
        results = list(ex.map(one, comps))
    # The network part is done; the state is read, merged and written under
    # the lock, so a CV being written meanwhile cannot be overwritten.
    with _LOCK:
        return _scan_merge(jc, comps, results, tm, today)


def _scan_merge(jc, comps, results, tm, today):
    st = _state()
    roles = st["roles"]
    found_n = st.setdefault("found", {})
    if not st.get("found_since"):
        # The funnel starts with what is already on the list, sorted into
        # the tracks it fits, so the first count is not zero.
        for v in roles.values():
            tr = v.get("tracks") or tm(v)
            if tr:
                v.setdefault("tracks", tr)
                found_n[tr[0]] = found_n.get(tr[0], 0) + 1
        st["found_since"] = str(today)
    names = {c["name"] for c in comps}
    new_total = 0
    for c, found, err in results:
        name = c["name"]
        info = {"board": c["board"], "slug": c["slug"],
                "at": datetime.now().strftime("%Y-%m-%d %H:%M")}
        if found is None:
            # A board that did not answer changes nothing: what it showed
            # yesterday stays until it answers again.
            prev = st["companies"].get(name) or {}
            info.update(error=err, open=prev.get("open", 0),
                        matched=prev.get("matched", 0))
            st["companies"][name] = info
            continue
        live = {r["key"] for r in found}
        match = []
        for r in found:
            tr = tm(r)
            if tr:
                match.append(dict(r, tracks=tr))
        mkeys = {r["key"] for r in match}
        for r in match:
            if r["key"] not in roles:
                roles[r["key"]] = dict(r, company=name, source=name,
                                       first=str(today), status="new",
                                       reach=is_reach(r["title"]))
                found_n[r["tracks"][0]] = found_n.get(r["tracks"][0], 0) + 1
                new_total += 1
            elif roles[r["key"]].get("status") == "new":
                roles[r["key"]]["tracks"] = r["tracks"]   # her tracks changed
        for k, v in list(roles.items()):
            if _src(v) != name:
                continue
            gone = k not in live
            if v.get("status") == "new" and (gone or k not in mkeys):
                del roles[k]               # filled, or no longer what she wants
            elif v.get("status") == "skipped" and gone:
                del roles[k]               # nothing left to keep away
            elif v.get("status") == "interested":
                if gone and not v.get("gone"):
                    v["gone"] = str(today)
                elif not gone:
                    v.pop("gone", None)
        info.update(open=len(found), matched=len(match), error="")
        st["companies"][name] = info
    # A role whose source she no longer follows goes, unless she is pursuing
    # it. The browser helper's sources are its own (merge_found).
    keep = names | set((st.get("sources") or {}).keys())
    for k, v in list(roles.items()):
        if _src(v) not in keep and v.get("status") != "interested":
            del roles[k]
    st["companies"] = {k: v for k, v in st["companies"].items() if k in names}
    st["scanned"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    st["new_last"] = new_total
    _save_state(st)
    write_leads(st)
    errs = {n: i["error"] for n, i in st["companies"].items() if i.get("error")}
    return {"companies": len(comps), "new": new_total,
            "waiting": sum(1 for v in roles.values() if v.get("status") == "new"),
            "errors": errs}


def _src(v):
    """Which source found a role: a followed company's name, or one of the
    browser helper's sources. Roles from before sources existed are their
    company's."""
    return v.get("source") or v.get("company")


@_locked
def merge_found(source, found, kind="page", today=None):
    """Roles the browser helper found (browser_scan.py), kept by the same
    rules as a board's. A search ("search") only shows the last week, so a
    role missing from it is not gone: it ages out after three weeks. A
    careers page ("page") is a full list, like a board."""
    today = today or date.today()
    jc = jobs_cfg()
    tm = track_matcher(jc)
    st = _state()
    roles = st["roles"]
    found_n = st.setdefault("found", {})
    have = {(fold(v.get("company")), fold(v.get("title")))
            for v in roles.values()}
    new = 0
    match = []
    for r in found:
        tr = tm(r)
        if tr:
            match.append(dict(r, tracks=tr))
    for r in match:
        twin = (fold(r.get("company")), fold(r.get("title")))
        if r["key"] in roles or twin in have:
            continue                     # the board scan, or another source, has it
        roles[r["key"]] = dict(r, source=source, first=str(today), status="new",
                               reach=is_reach(r["title"]))
        found_n[r["tracks"][0]] = found_n.get(r["tracks"][0], 0) + 1
        have.add(twin)
        new += 1
    live = {r["key"] for r in found}
    cut = str(today - timedelta(days=21))
    for k, v in list(roles.items()):
        if _src(v) != source:
            continue
        if kind == "search":
            if v.get("status") in ("new", "skipped") and v.get("first", "") < cut \
                    and k not in live:
                del roles[k]
        elif k not in live and v.get("status") in ("new", "skipped"):
            del roles[k]
    st.setdefault("sources", {})[source] = {
        "kind": kind, "at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "open": len(found), "matched": len(match)}
    _save_state(st)
    write_leads(st)
    return {"source": source, "new": new, "matched": len(match)}


def leads(st=None):
    """The roles waiting for her yes or no, newest first."""
    st = st or _state()
    out = [v for v in st["roles"].values() if v.get("status") == "new"]
    out.sort(key=lambda v: (v.get("first", ""), v.get("posted", "")),
             reverse=True)
    return out


def write_leads(st=None):
    st = st or _state()
    rows = leads(st)
    by = {}
    for r in rows:
        by.setdefault(r["company"], []).append(r)
    lines = ["---",
             "generated: by jobs.py scan; never hand-edit",
             "scanned: %s" % st.get("scanned", "never"),
             "---", "", "# New roles", "",
             "Open roles at the companies you follow that match what you look"
             " for and that you have not answered yet. Interested or not for"
             " me, on the Jobs tab.", ""]
    if not rows:
        lines.append("Nothing new.")
    for comp in sorted(by, key=lambda c: -len(by[c])):
        lines += ["## %s" % comp, ""]
        for r in by[comp]:
            bits = [r["title"]] + [x for x in (
                r.get("where"), "posted %s" % r["posted"] if r.get("posted")
                else "", "found %s" % r.get("first")) if x]
            lines.append("- %s · %s" % (" · ".join(bits), r["url"]))
        lines.append("")
    with open(LEADS_MD, "w", encoding="utf-8") as f:
        f.write("\n".join(lines).rstrip() + "\n")


# ------------------------------------------------------------------ tracker

TRACKER_HEAD = """---
updated: {today}
maintained-by: the brain; you move stages on the Jobs tab
---

# Job hunt

The roles you are pursuing, one heading each. Stage is interested, applied,
interviewing, offer or closed. Ball says who moves next and Since is the day
it changed hands, which is what the chase reminders count from. Anything you
write under a role that is not one of those fields stays as you wrote it.
"""


def _read_tracker():
    try:
        with open(TRACKER, encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return ""


def load_tracker(text=None):
    """[{heading, fields{}, notes[]}] in file order."""
    text = _read_tracker() if text is None else text
    out, cur = [], None
    for line in text.splitlines():
        m = re.match(r"^##\s+(.+?)\s*$", line)
        if m:
            cur = {"heading": m.group(1), "fields": {}, "notes": []}
            out.append(cur)
            continue
        if cur is None:
            continue
        f = re.match(r"^-\s+(%s):\s*(.*)$" % "|".join(FIELDS), line)
        if f:
            cur["fields"][f.group(1)] = f.group(2).strip()
        elif line.strip():
            cur["notes"].append(line)
    return out


def _write_tracker(text):
    text = re.sub(r"(?m)^updated: .*$", "updated: %s" % date.today(), text, 1)
    tmp = TRACKER + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text.rstrip() + "\n")
    os.replace(tmp, TRACKER)


@_locked
def _set_fields(heading, values):
    """Change fields under one heading in place; her own lines stay put."""
    text = _read_tracker()
    lines = text.splitlines()
    start = next((i for i, l in enumerate(lines)
                  if re.match(r"^##\s+%s\s*$" % re.escape(heading), l)), None)
    if start is None:
        raise ValueError("no role called %r in the tracker" % heading)
    end = next((i for i in range(start + 1, len(lines))
                if lines[i].startswith("## ")), len(lines))
    last_field = start
    for k, v in values.items():
        v = None if v is None else _flat(v)
        rx = re.compile(r"^-\s+%s:" % re.escape(k))
        hit = next((i for i in range(start + 1, end) if rx.match(lines[i])),
                   None)
        if hit is not None:
            if v in (None, ""):
                del lines[hit]
                end -= 1
            else:
                lines[hit] = "- %s: %s" % (k, v)
        elif v not in (None, ""):
            lf = max((i for i in range(start + 1, end)
                      if re.match(r"^-\s+(%s):" % "|".join(FIELDS), lines[i])),
                     default=start)
            lines.insert(lf + 1, "- %s: %s" % (k, v))
            end += 1
    _write_tracker("\n".join(lines))


@_locked
def track(key, today=None):
    """She is interested in a new role: it moves into the tracker."""
    today = today or date.today()
    st = _state()
    r = st["roles"].get(key)
    if not r:
        raise ValueError("that role is no longer on the list")
    text = _read_tracker() or TRACKER_HEAD.format(today=today)
    have = {t["heading"] for t in load_tracker(text)}
    head = "%s at %s" % (r["title"], r["company"])
    head = re.sub(r"\s+", " ", head.replace("#", "")).strip()
    n = 2
    base = head
    while head in have:
        head = "%s (%d)" % (base, n)
        n += 1
    block = ["", "## " + head, "- Stage: interested", "- Ball: Me",
             "- Since: %s" % today]
    if r.get("tracks"):
        block.append("- Track: %s" % _flat(r["tracks"][0]))
    block.append("- Company: %s" % _flat(r["company"]))
    if r.get("url"):
        block.append("- Link: %s" % _flat(r["url"]))
    if r.get("where"):
        block.append("- Where: %s" % _flat(r["where"]))
    block += ["- Found: %s" % _flat(r.get("first", today)),
              "- Key: %s" % _flat(key)]
    _write_tracker(text.rstrip() + "\n" + "\n".join(block))
    r["status"] = "interested"
    r["heading"] = head
    _save_state(st)
    write_leads(st)
    return {"ok": True, "heading": head}


# The one-tap why after "Not for me" (plan item 12): optional, and it feeds
# the weekly lesson tray (lessons.py). The page asks after the skip, so a
# second call with a reason on a role already skipped only adds the reason.
SKIP_REASONS = ("wrong role", "wrong place", "wrong level", "already on it")


@_locked
def skip(key, reason=""):
    st = _state()
    r = st["roles"].get(key)
    if not r:
        raise ValueError("that role is no longer on the list")
    if r.get("status") != "skipped":
        r["status"] = "skipped"
        r["skipped"] = str(date.today())
    if reason in SKIP_REASONS:
        r["skip_reason"] = reason
    _save_state(st)
    write_leads(st)
    return {"ok": True}


@_locked
def add_role(title, company, link="", where="", today=None, track=""):
    """A role she found herself (a friend's tip, a LinkedIn post): straight
    into the tracker as interested."""
    today = today or date.today()
    title, company = (title or "").strip(), (company or "").strip()
    if not title or not company:
        raise ValueError("a role needs a title and a company")
    if link and not re.match(r"^https?://", link):
        raise ValueError("the link should start with https://")
    key = "own:" + hashlib.sha1(("%s|%s" % (title.lower(), company.lower()))
                                .encode()).hexdigest()[:12]
    st = _state()
    tr = [track] if track else track_matcher()({"title": title, "where": ""}) \
        if tracks() else []
    st["roles"][key] = {"key": key, "title": title, "company": company,
                        "url": link, "where": where, "first": str(today),
                        "status": "new", "tracks": tr[:1]}
    _save_state(st)
    return track(key, today)


def set_stage(heading, stage, outcome="", today=None):
    today = today or date.today()
    stage = (stage or "").strip().lower()
    if stage not in STAGES:
        raise ValueError("stage is one of: %s" % ", ".join(STAGES))
    if stage == "closed" and outcome and outcome not in OUTCOMES:
        raise ValueError("outcome is one of: %s" % ", ".join(OUTCOMES))
    cur = next((t["fields"] for t in load_tracker()
                if t["heading"] == heading), {})
    was = (cur.get("Reached") or cur.get("Stage") or "interested").lower()
    reached = (stage if STAGE_ORDER.get(stage, -1) > STAGE_ORDER.get(was, 0)
               else was)
    _set_fields(heading, {"Stage": stage, "Ball": STAGE_BALL[stage],
                          "Since": str(today),
                          "Outcome": outcome if stage == "closed" else "",
                          "Chased": "",
                          "Reached": reached if reached != "interested" else ""})
    return {"ok": True}


def chased(heading, today=None):
    """She chased them: the clock restarts, the ball stays theirs."""
    today = today or date.today()
    _set_fields(heading, {"Ball": "Them", "Since": str(today),
                          "Chased": str(today)})
    return {"ok": True}


@_locked
def set_kit(heading, **paths):
    """Record where a role's CV, letter or prep lives (paths inside the
    brain), so the page can show the kit and open each piece."""
    vals = {}
    for k, v in paths.items():
        if v:
            rel = os.path.relpath(v, BRAIN) if os.path.isabs(v) else v
            vals[{"cv": "CV", "letter": "Letter", "prep": "Prep"}[k]] = rel
    if vals:
        _set_fields(heading, vals)


def set_ball(heading, ball, today=None):
    today = today or date.today()
    ball = "Me" if str(ball).lower() in ("me", "mine") else "Them"
    _set_fields(heading, {"Ball": ball, "Since": str(today)})
    return {"ok": True}


def applications(today=None, cfg=None):
    """The tracker, with each role's days-since and what it needs."""
    today = today or date.today()
    jc = jobs_cfg(cfg)
    st = _state()
    gone = {v.get("heading") or "": v.get("gone") for v in st["roles"].values()
            if v.get("status") == "interested" and v.get("gone")}
    out = []
    for t in load_tracker():
        f = t["fields"]
        stage = (f.get("Stage") or "interested").lower()
        try:
            since = date.fromisoformat(f.get("Since", "")[:10])
            days = (today - since).days
        except ValueError:
            days = None
        ball = f.get("Ball") or STAGE_BALL.get(stage, "")
        need = ""
        if stage != "closed" and days is not None:
            if ball == "Them" and days >= int(jc["chase_days"]):
                need = "chase"
            elif ball == "Me" and days >= int(jc["stale_days"]):
                need = "stale"
        out.append({"heading": t["heading"], "stage": stage, "ball": ball,
                    "days": days, "need": need,
                    "company": f.get("Company") or t["heading"].rsplit(" at ", 1)[-1],
                    "role": t["heading"].rsplit(" at ", 1)[0],
                    "link": f.get("Link", ""), "where": f.get("Where", ""),
                    "via": f.get("Via", ""), "next": f.get("Next", ""),
                    "outcome": f.get("Outcome", ""),
                    "track": f.get("Track", ""),
                    "cv": f.get("CV", ""), "letter": f.get("Letter", ""),
                    "check": f.get("Check", ""),
                    "cvcheck": f.get("CVCheck", ""),
                    "prep": f.get("Prep", ""),
                    "reached": (f.get("Reached") or (stage if stage != "closed"
                                                     else "interested")).lower(),
                    "gone": gone.get(t["heading"], ""), "notes": t["notes"]})
    return out


def funnel(today=None, cfg=None):
    """Per track: how many roles the scans found, and how far the ones she
    took on got. The point is the comparison: after a month, the track that
    turns applications into interviews and the one that does not."""
    st = _state()
    names = [t["name"] for t in tracks(jobs_cfg(cfg))]
    apps = applications(today, cfg)
    for a in apps:
        if a["track"] and a["track"] not in names:
            names.append(a["track"])
    if any(not a["track"] for a in apps):
        names.append("")
    out = []
    for n in names:
        mine = [a for a in apps if a["track"] == n]
        rank = [STAGE_ORDER.get(a["reached"], 0) for a in mine]
        row = {"track": n or "No track",
               "found": int((st.get("found") or {}).get(n, 0)) if n else 0,
               "pursued": len(mine),
               "applied": sum(1 for x in rank if x >= 1),
               "interviews": sum(1 for x in rank if x >= 2),
               "offers": sum(1 for x in rank if x >= 3),
               "open": sum(1 for a in mine if a["stage"] != "closed"),
               "rejected": sum(1 for a in mine if a["outcome"] == "rejected")}
        row["rate"] = (round(100 * row["interviews"] / row["applied"])
                       if row["applied"] else None)
        out.append(row)
    return out


def flags(today=None, cfg=None):
    """One line per role that needs her today: what the Today page and the
    morning plan read. A chase is a two-minute job; a stale one is a choice."""
    out = []
    for a in applications(today, cfg):
        if a["need"] == "chase":
            out.append(dict(a, text="Chase %s about %s" % (a["company"], a["role"]),
                            why="you %s %d days ago" % (
                                "applied" if a["stage"] == "applied"
                                else "last heard", a["days"])))
        elif a["need"] == "stale":
            out.append(dict(a, text=(
                "Answer the %s offer" % a["company"] if a["stage"] == "offer"
                else "Apply for %s at %s, or let it go" % (a["role"], a["company"])
                if a["stage"] == "interested"
                else "Write back to %s about %s" % (a["company"], a["role"])),
                why="%d days with you" % a["days"]))
        elif a["gone"] and a["stage"] == "interested":
            out.append(dict(a, text="The %s posting at %s is gone"
                            % (a["role"], a["company"]),
                            why="off their board since %s" % a["gone"]))
    return out


def status():
    jc = jobs_cfg()
    st = _state()
    apps = applications()
    lines = ["Job hunt: %s. %d companies, scanned %s." % (
        "on" if jc["on"] else "off", len(jc["companies"]),
        st.get("scanned", "never"))]
    n = len(leads(st))
    if n:
        lines.append("%d new role%s to answer." % (n, "" if n == 1 else "s"))
    live = [a for a in apps if a["stage"] != "closed"]
    if live:
        by = {}
        for a in live:
            by[a["stage"]] = by.get(a["stage"], 0) + 1
        lines.append("Pursuing %d: %s." % (len(live), ", ".join(
            "%d %s" % (by[s], s) for s in STAGES if s in by)))
    for fl in flags():
        lines.append("- %s (%s)" % (fl["text"], fl["why"]))
    errs = [n for n, i in st["companies"].items() if i.get("error")]
    if errs:
        lines.append("Did not answer: %s." % ", ".join(errs))
    return "\n".join(lines)


# ------------------------------------------------------------------ main

def main(argv):
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    cmd, rest = argv[0], argv[1:]
    arg = " ".join(rest).strip()
    if cmd == "scan":
        if os.environ.get("CLAUDECODE") or os.environ.get("LIFEBRAIN_UNATTENDED"):
            # Inside a Claude run the sandbox has no internet: every board
            # would "fail" and the page would say so (7 Oct). The morning
            # job and the page's button read the boards; a run reads status.
            import agents
            print(agents.say("The boards are read by the morning job and the page, not "
                             "from inside a Claude run.\n") + status())
            return 0
        if "--if-on" in rest and not is_on():
            print("Job hunt is off; nothing to scan.")
            return 0
        r = scan()
        print("Scanned %d companies: %d new, %d waiting for you."
              % (r["companies"], r["new"], r["waiting"]))
        for n, e in r["errors"].items():
            print("  %s did not answer (%s)" % (n, e))
        # The fit score rides the scan when there is a profile to score
        # against: a few small no-tools calls a day, capped.
        jc = jobs_cfg()
        if jc.get("score", True) and "--no-score" not in rest:
            import career
            if career.has_profile():
                sr = career.score(limit=int(jc.get("score_limit", 15)))
                print("Scored %d role(s)%s." % (sr["scored"], (
                    ", %d left for tomorrow" % sr["left"]) if sr.get("left") else ""))
    elif cmd == "find":
        print(json.dumps(find(arg), indent=1))
    elif cmd == "add":
        r = add_company(arg)
        print(json.dumps(r, indent=1))
        return 1 if r.get("error") else 0
    elif cmd == "remove":
        print(json.dumps(remove_company(arg)))
    elif cmd == "interested":
        print(json.dumps(track(arg)))
    elif cmd == "skip":
        print(json.dumps(skip(arg)))
    elif cmd == "stage":
        print(json.dumps(set_stage(rest[0], rest[1],
                                   rest[2] if len(rest) > 2 else "")))
    elif cmd == "chased":
        print(json.dumps(chased(arg)))
    elif cmd == "status":
        print(status())
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

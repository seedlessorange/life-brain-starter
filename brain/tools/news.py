"""The morning paper, made mechanically.

Fetches RSS from a fixed set of reputable outlets (config.json `news.feeds`),
keeps the items that match her topics (`news.interests`) plus a short front
page, and writes brain/news.md — the briefing the page's News tab renders.
Anything an earlier morning already showed is left out (.news-seen.json).
No model is involved: this costs a few seconds of network, nothing else.

    python3 brain/tools/news.py fetch          # rebuild the briefing
    python3 brain/tools/news.py fetch --explain  # + the day's finance breakdown
    python3 brain/tools/news.py guardian KEY   # store her Guardian API key
    python3 brain/tools/news.py guardian       # is the key set and working?
    python3 brain/tools/news.py list           # show the topics
    python3 brain/tools/news.py add "topic" [keyword,keyword]
    python3 brain/tools/news.py remove "topic"

Feeds are chosen in config, never discovered: a briefing that can grow its
own sources is a briefing that quietly stops being reputable.
"""
import concurrent.futures
import functools
import html as htmlmod
import json
import os
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

HERE = os.path.dirname(os.path.abspath(__file__))
BRAIN = os.path.dirname(HERE)
CONFIG = os.path.join(BRAIN, "config.json")
OUT_MD = os.path.join(BRAIN, "news.md")
OUT_JSON = os.path.join(BRAIN, ".news.json")
WEEK_LOG = os.path.join(BRAIN, ".news-week.json")   # 14 days of explainers
GLOSSARY = os.path.join(BRAIN, "news-glossary.md")  # terms she has learned
SEEN = os.path.join(BRAIN, ".news-seen.json")       # what earlier mornings showed

# Headlines that are furniture, not news: live blogs (a summary of a rolling
# page is whatever minute it was fetched), broadcast listings, podcasts,
# reader call-outs. Matched in the lowercased title; config `news.skip`
# replaces this list.
DEFAULT_SKIP = ["– live", "- live", "business live", "live updates", "live:",
                "as it happened", "en direct", "how to follow", "how to watch",
                "where to watch", "podcast", "send us your questions", "quiz"]

UA = "life-brain/1.0 (personal news reader; one fetch per feed per run)"
FETCH_TIMEOUT = 10

# Her Guardian API key (free personal tier, registered by her at
# open-platform.theguardian.com) lives in the OS keystore, never in a file —
# this repo is committed and sometimes pushed.
KC_SERVICE = "life-brain-news"
KC_ACCOUNT = "guardian"


def kc_set(value, account=KC_ACCOUNT):
    import keychain
    keychain.put(KC_SERVICE, account, value)


def kc_get(account=KC_ACCOUNT):
    import keychain
    return keychain.get(KC_SERVICE, account)


# Reader-mode pulls identify as a normal browser — that is what her click
# is. Feeds and APIs keep the honest life-brain UA above.
BROWSER_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
              "AppleWebKit/605.1.15 (KHTML, like Gecko) "
              "Version/17.5 Safari/605.1.15")

# A page whose "article" is subscription marketing is a paywall, not prose.
PAYWALL_MARKS = ("join now", "subscribe to read", "try unlimited access",
                 "register to read", "sign in to read", "subscribe now",
                 "complete digital access", "unlimited access to ft")


def _cookie_for(url):
    """Her stored session cookie for this site, if she saved one
    (news.py cookie <site> — Keychain account 'cookie:<site>')."""
    from urllib.parse import urlparse
    host = (urlparse(url).hostname or "").lower()
    parts = host.split(".")
    for i in range(max(len(parts) - 1, 1)):
        c = kc_get("cookie:" + ".".join(parts[i:]))
        if c:
            return c
    return None


def _config():
    try:
        with open(CONFIG, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_config(cfg):
    with open(CONFIG, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)
        f.write("\n")


def _news_cfg(cfg=None):
    return (cfg or _config()).get("news") or {}


# ---------------------------------------------------------------- fetching

def _localname(tag):
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _child_text(el, *names):
    for c in el:
        if _localname(c.tag) in names and (c.text or "").strip():
            return c.text.strip()
    return ""


def _atom_link(el):
    href = ""
    for c in el:
        if _localname(c.tag) == "link":
            rel = c.get("rel", "alternate")
            if c.get("href") and rel in ("alternate", ""):
                return c.get("href")
            href = href or c.get("href", "")
    return href


def _parse_date(s):
    if not s:
        return None
    try:
        return parsedate_to_datetime(s).astimezone(timezone.utc)
    except Exception:
        pass
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone.utc)
    except Exception:
        return None


def _clean_summary(raw, limit=430):
    """Feed descriptions arrive as HTML fragments; keep 1-3 plain sentences."""
    text = re.sub(r"<[^>]+>", " ", raw or "")
    text = htmlmod.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    # Boilerplate some outlets weave in: "[ Read More ]" tails, "The post X
    # appeared first on Y", the Guardian's newsletter plugs mid-description.
    text = re.sub(r"\[?\s*(Continue reading|Read More)[\s.…]*\]?\.?$",
                  "", text, flags=re.I).strip()
    text = re.sub(r"The post .*? appeared first on .*$", "", text).strip()
    sentences = re.split(r"(?<=[.!?…]) +", text)
    sentences = [s for s in sentences
                 if not re.search(r"breaking news email|Follow (updates|our|the) ",
                                  s)]
    text = " ".join(sentences).strip()
    if len(text) <= limit:
        return text
    parts = re.split(r"(?<=[.!?…]) +", text)
    out = ""
    for p in parts:
        if out and len(out) + len(p) > limit:
            break
        out = (out + " " + p).strip()
        if len(out) >= limit:
            break
    return out or text[:limit].rsplit(" ", 1)[0] + "…"


def _parse_hn(feed, raw):
    """Hacker News via the Algolia API: the front page with points and
    comment counts — what tech is actually talking about, not an editor's
    pick. Items carry `points`, so they rank by heat, not recency."""
    data = json.loads(raw)
    items = []
    for pos, h in enumerate(data.get("hits") or []):
        title = (h.get("title") or "").strip()
        if not title:
            continue
        discuss = f"https://news.ycombinator.com/item?id={h.get('objectID')}"
        when = _parse_date(h.get("created_at") or "")
        items.append({
            "title": title,
            "link": h.get("url") or discuss,
            "summary": "",
            "outlet": feed["name"],
            "topic": feed.get("topic", ""),
            "topics": feed.get("topics") or [],
            "front": False,
            "pos": pos,
            "ts": when.isoformat() if when else "",
            "points": h.get("points") or 0,
            "comments": h.get("num_comments") or 0,
            "discuss": discuss,
        })
    return items


def _parse_guardian(feed, raw):
    """The Guardian content API: real article text, on her own free key.
    The summary becomes the standfirst plus the opening sentences the
    standfirst didn't already say — a proper excerpt, not a teaser."""
    data = json.loads(raw)
    items = []
    for pos, a in enumerate((data.get("response") or {}).get("results") or []):
        title = (a.get("webTitle") or "").strip()
        if not title:
            continue
        f = a.get("fields") or {}
        trail = _clean_summary(f.get("trailText") or "", 260)
        if trail and not trail.endswith((".", "!", "?", "…")):
            trail += "."
        lead = _clean_summary(f.get("bodyText") or "", 560)
        extra = ""
        if lead:
            fresh = [s for s in re.split(r"(?<=[.!?…]) +", lead)
                     if s[:60].lower() not in trail.lower()]
            extra = " ".join(fresh[:3])
        body = re.sub(r"\s+", " ", f.get("bodyText") or "").strip()
        when = _parse_date(a.get("webPublicationDate") or "")
        items.append({
            "title": title,
            "link": (a.get("webUrl") or "").strip(),
            "summary": (trail + " " + extra).strip() if trail else lead,
            # Full article text rides along (never into news.md) so the
            # page's speed reader can offer the whole piece, not a teaser.
            "body": body,
            "outlet": feed["name"],
            "topic": feed.get("topic", ""),
            "topics": feed.get("topics") or [],
            "front": bool(feed.get("front")),
            "pos": pos,
            "ts": when.isoformat() if when else "",
            "live": a.get("type") == "liveblog",
        })
    return items


def _fetch_one(feed):
    """One feed → list of item dicts. Any failure returns [] plus the error."""
    url, kind = feed["url"], feed.get("kind", "")
    if kind == "guardian":
        key = kc_get()
        if key:
            url = url + ("&" if "?" in url else "?") + "api-key=" + key
        else:
            url, kind = feed.get("rss") or url, ""   # no key: plain RSS
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=FETCH_TIMEOUT) as r:
        raw = r.read()
    if kind == "hn":
        return _parse_hn(feed, raw)
    if kind == "guardian":
        return _parse_guardian(feed, raw)
    root = ET.fromstring(raw)
    items = []
    # RSS 2.0: rss/channel/item — Atom: feed/entry
    nodes = [el for el in root.iter() if _localname(el.tag) in ("item", "entry")]
    for pos, el in enumerate(nodes):
        title = _child_text(el, "title")
        if not title:
            continue
        link = _child_text(el, "link") or _atom_link(el)
        summary = _child_text(el, "description", "summary", "content")
        when = _parse_date(_child_text(el, "pubDate", "published", "updated", "date"))
        items.append({
            "title": htmlmod.unescape(title).strip(),
            "link": (link or "").strip(),
            "summary": _clean_summary(summary),
            "outlet": feed["name"],
            "topic": feed.get("topic", ""),
            "topics": feed.get("topics") or [],
            "front": bool(feed.get("front")),
            "pos": pos,
            "ts": when.isoformat() if when else "",
        })
    return items


# ---------------------------------------------------------------- matching

def _match_terms(interest):
    terms = [interest.get("topic", "")] + list(interest.get("keywords") or [])
    return [t.strip().lower() for t in terms if t.strip()]


@functools.lru_cache(maxsize=None)
def _term_rx(term):
    # Whole words only, plurals allowed: "market" finds "markets" but not
    # "supermarket" or "marketing", and "series a" no longer finds "series
    # about". Substrings let every long keyword leak into unrelated stories.
    return re.compile(r"\b" + re.escape(term) + r"(?:s|es)?\b")


def _hits(text, term):
    return _term_rx(term).search(text) is not None


def _skipped(item, skip):
    if item.get("live"):
        return True
    title = item["title"].lower()
    return any(s in title for s in skip)


# ---------------------------------------------------------------- memory

def _norm_link(link):
    # Feeds tack tracking queries onto links (?at_medium=RSS, ?syn-…) and
    # not always the same ones twice, so the address alone is the key.
    return re.sub(r"[?#].*$", "", (link or "").strip().lower()).rstrip("/")


def _seen_keys(item):
    keys = [re.sub(r"\W+", "", item["title"].lower())]
    if item.get("link"):
        keys.append(_norm_link(item["link"]))
    return keys


def _seen_load():
    try:
        with open(SEEN, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _seen_record(data, seen, today):
    """Stamp every story this briefing shows with the day it first
    appeared. A slow topic (a week-wide window) otherwise serves the same
    story five mornings running; with the stamp it appears once, and a quiet
    week simply shows nothing new. Kept a month, then forgotten."""
    items = list(data["front"])
    for t in data["topics"]:
        items.extend(t["items"])
    for i in items:
        for k in _seen_keys(i):
            seen.setdefault(k, today)
    cutoff = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
    seen = {k: d for k, d in seen.items() if d >= cutoff}
    with open(SEEN, "w", encoding="utf-8") as f:
        json.dump(seen, f, ensure_ascii=False, indent=0)


_NOT_NAMES = {
    "The", "A", "An", "In", "On", "At", "As", "And", "But", "For", "With",
    "After", "Before", "How", "Why", "What", "When", "Who", "Where", "This",
    "That", "These", "Those", "It", "He", "She", "They", "We", "You", "His",
    "Her", "Their", "Our", "Its", "New", "More", "Most", "Some", "Inside",
    "From", "Into", "Over", "Under", "Says", "Mr", "Ms", "Mrs", "Dr", "If",
    "Is", "Are", "Was", "Will", "Can", "Not", "No", "Live", "Monday",
    "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday",
    "US", "UK", "EU", "UN"}


def _names(text):
    # "Trump-Xi summit" is two names; "Xi" is two letters.
    words = re.findall(r"\b[A-Z][^\W\d_]+", text.replace("’", "'"))
    return set(words) - _NOT_NAMES


def _same_story(a, b):
    """Two outlets leading on the same event: they share a name in the
    headline and at least one more anywhere. Used on the front page only,
    where three slots should mean three events — inside a topic, sharing
    'Ferrari' is the point, not a duplicate."""
    ta, tb = _names(a["title"]), _names(b["title"])
    if not ta & tb:
        return False
    fa = ta | _names(a.get("summary") or "")
    fb = tb | _names(b.get("summary") or "")
    return len(fa & fb) >= 2


def _fresh(item, hours):
    if not item["ts"]:
        return True          # undated feeds still deserve their top items
    then = datetime.fromisoformat(item["ts"])
    return (datetime.now(timezone.utc) - then).total_seconds() <= hours * 3600


def _sort_key(item):
    return (item["ts"] or "0000", -item["pos"])


def build_briefing(cfg=None, seen=None):
    cfg = cfg or _config()
    ncfg = _news_cfg(cfg)
    feeds = ncfg.get("feeds") or []
    interests = ncfg.get("interests") or []
    per_topic = int(ncfg.get("per_topic") or 3)
    fresh_hours = int(ncfg.get("fresh_hours") or 36)

    all_items, failed = [], []
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        futs = {pool.submit(_fetch_one, f): f for f in feeds}
        for fut in concurrent.futures.as_completed(futs):
            feed = futs[fut]
            try:
                all_items.extend(fut.result())
            except Exception as e:
                failed.append({"name": feed["name"], "error": str(e)[:120]})

    guardian = ""
    if any(f.get("kind") == "guardian" for f in feeds):
        guardian = "api" if kc_get() else "rss"

    # A story an earlier morning already showed stays gone; one first shown
    # today survives a Refresh, so the page doesn't reshuffle under her.
    skip = [s.lower() for s in (ncfg.get("skip") or DEFAULT_SKIP)]
    today = datetime.now().strftime("%Y-%m-%d")
    seen = seen or {}
    all_items = [i for i in all_items
                 if not _skipped(i, skip)
                 and all(seen.get(k, today) >= today for k in _seen_keys(i))]

    fresh = [i for i in all_items if _fresh(i, fresh_hours)]
    taken = set()

    def take(item):
        key = item["link"] or re.sub(r"\W+", "", item["title"].lower())
        if key in taken:
            return False
        taken.add(key)
        return True

    # The front page: the top of each front feed, in the order its editors
    # chose — feed position is the outlet's own judgement of importance.
    # When two outlets lead on the same event, the second one's next story
    # takes the slot.
    front = []
    front_feeds = [f["name"] for f in feeds if f.get("front")]
    queues = {n: sorted((i for i in fresh if i["outlet"] == n and i["pos"] < 8),
                        key=lambda i: i["pos"]) for n in front_feeds}
    for _ in range(3):
        for name in front_feeds:
            q = queues[name]
            while q:
                i = q.pop(0)
                if not any(_same_story(i, f) for f in front) and take(i):
                    front.append(i)
                    break
    front = front[:int(ncfg.get("front_items") or 3)]

    # Candidates rank by points where a feed has them (Hacker News), by
    # recency everywhere else — a 900-point story beats a newer 40-point one.
    # Freshness is decided per interest below, not here: a sport with a
    # fortnight between races and a market that turns over hourly cannot
    # share one window. The front page keeps the global one.
    cands = sorted(all_items, reverse=True,
                   key=lambda i: (i.get("points") or 0, i["ts"] or "0000",
                                  -i["pos"]))
    topics = []
    for interest in interests:
        topic = interest.get("topic", "").strip()
        if not topic:
            continue
        terms = _match_terms(interest)
        cap = int(interest.get("count") or per_topic)
        hours = int(interest.get("fresh_hours") or fresh_hours)
        # No outlet may take more than a share of a topic while another has
        # something to offer, so a wire that republishes hourly can't crowd
        # out a paper that files four good pieces a day. The second pass
        # lifts the limit, so a topic with one real source still fills up.
        per_outlet = int(interest.get("per_outlet")
                         or ncfg.get("per_outlet") or 2)
        matched, byoutlet = [], {}

        def fits(i):
            # `topic` on a feed is exclusive: its items appear there and
            # nowhere else (Le Monde under France, Hacker News under the
            # trends). `topics` is a permission list — the feed may serve
            # any of them, and its keywords decide which. A feed with
            # neither is general and travels by keyword alone.
            if i["topic"]:
                return i["topic"] == topic
            if i.get("topics") and topic not in i["topics"]:
                return False
            title = i["title"].lower()
            if any(_hits(title, t) for t in terms):
                return True
            # A keyword only in the summary is enough from an outlet already
            # on the subject (TechCrunch under AI). A general outlet must
            # mention two: one passing word is how a war briefing landed in
            # Money & markets because a market burned outside Kyiv.
            text = title + " " + i["summary"].lower()
            stems = {re.sub(r"(es|s)$", "", t) for t in terms if _hits(text, t)}
            return len(stems) >= (1 if i.get("topics") else 2)

        for limit in (per_outlet, cap):
            for i in cands:
                if len(matched) >= cap:
                    break
                if byoutlet.get(i["outlet"], 0) >= limit:
                    continue
                if not _fresh(i, hours) or not fits(i) or not take(i):
                    continue
                matched.append(i)
                byoutlet[i["outlet"]] = byoutlet.get(i["outlet"], 0) + 1
        topics.append({"topic": topic, "items": matched})

    return {
        "updated": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "front": front,
        "topics": topics,
        "failed": failed,
        "guardian": guardian,
        "interests": [i.get("topic", "") for i in interests],
    }


# ---------------------------------------------------------------- output

def _when_line(item):
    if not item["ts"]:
        return ""
    then = datetime.fromisoformat(item["ts"]).astimezone()
    now = datetime.now().astimezone()
    if then.date() == now.date():
        return then.strftime("%H:%M")
    if (now.date() - then.date()).days == 1:
        return "yesterday " + then.strftime("%H:%M")
    return then.strftime("%d %b")


def _item_meta(i):
    when = _when_line(i)
    if "points" in i:
        return (f"{i['points']} points, {i['comments']} comments on "
                f"{i['outlet']}" + (f", {when}" if when else ""))
    return i["outlet"] + (f", {when}" if when else "")


def write_briefing(data):
    day = datetime.now().strftime("%A %d %B").replace(" 0", " ")
    lines = ["---",
             f"updated: {data['updated']}",
             "generated-by: brain/tools/news.py — never hand-edit",
             "---", "",
             f"# Your briefing — {day}", ""]

    def block(title, items, explainer=""):
        if not items:
            return
        lines.append(f"## {title}")
        lines.append("")
        if explainer:
            for p in explainer.splitlines():
                if p.strip():
                    lines.append(f"> {p.strip()}")
            lines.append("")
        for i in items:
            head = f"- **[{i['title']}]({i['link']})** — {_item_meta(i)}"
            if i.get("discuss") and i["link"] != i["discuss"]:
                head += f" ([discussion]({i['discuss']}))"
            lines.append(head)
            if i["summary"]:
                lines.append(f"  {i['summary']}")
        lines.append("")

    block("The front page", data["front"])
    for t in data["topics"]:
        block(t["topic"], t["items"], t.get("explainer") or "")
    for r in data.get("recaps") or []:
        if not r.get("text"):
            continue
        lines.append(f"## The week in {r['topic']}")
        lines.append("")
        for p in r["text"].splitlines():
            if p.strip():
                lines.append(f"> {p.strip()}")
        lines.append("")
    if data["failed"]:
        names = ", ".join(f["name"] for f in data["failed"])
        lines.append(f"*Couldn't reach: {names}.*")
        lines.append("")

    with open(OUT_MD, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)


def _lens(interest):
    return (interest.get("lens")
            or "how this field works").strip()


def article_text(url):
    """Reader-mode text for one story, on her click: fetch the article page
    and keep its readable paragraphs — what Safari's Reader does, one page
    at a time, for personal reading. Only URLs the briefing itself produced
    are allowed (this is what keeps the endpoint from being an open proxy),
    and a paywalled page simply yields too little text, so the caller falls
    back to the summary."""
    try:
        with open(OUT_JSON, encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        raise ValueError("no briefing yet")
    items = list(data.get("front") or [])
    for t in data.get("topics") or []:
        items.extend(t["items"])
    hit = next((i for i in items if i.get("link") == url), None)
    if hit is None:
        raise ValueError("not in today's briefing")
    if hit.get("body"):
        return hit["body"]
    headers = {"User-Agent": BROWSER_UA}
    cookie = _cookie_for(url)
    if cookie:
        headers["Cookie"] = cookie
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=12) as r:
        page = r.read(2_000_000).decode("utf-8", "replace")
    m = re.search(r"<article\b.*?</article>", page, flags=re.S | re.I)
    scope = m.group(0) if m else page
    scope = re.sub(r"<(script|style|noscript|aside|figure)\b.*?</\1>", " ",
                   scope, flags=re.S | re.I)
    out = []
    for p in re.findall(r"<p\b[^>]*>(.*?)</p>", scope, flags=re.S | re.I):
        text = re.sub(r"\s+", " ",
                      htmlmod.unescape(re.sub(r"<[^>]+>", " ", p))).strip()
        # Long paragraphs are prose; short ones are only kept once the
        # article has started, which drops nav crumbs and cookie banners.
        if len(text) >= 60 or (out and len(text) >= 25):
            out.append(text)
    text = " ".join(out)
    low = text[:500].lower()
    if len(text) < 600 or any(m in low for m in PAYWALL_MARKS):
        raise ValueError("paywalled — a logged-in cookie may unlock it "
                         "(news.py cookie <site>)")
    return text[:40000]


def _explain(topic, items, lens, known=()):
    """The learning breakdown: one small no-tool call through llm.py (Haiku,
    or local Ollama if config routes the 'news' job there) — cents, once a
    day per learning topic. She feels out of her depth with finance and is
    learning entrepreneurship; the briefing is where the stories arrive
    already translated, with their significance spelled out."""
    import llm
    stories = "\n".join(f"- {i['title']}. {i['summary']}" for i in items)
    # Left to itself the model picks "yield" every other morning; the
    # glossary is the list of what she has already been taught.
    avoid = (" She already knows these terms, so pick one that is not on "
             "this list and is not a variant of one: "
             + "; ".join(known[-80:]) + ".") if known else ""
    system = (f"You explain news to a smart beginner who wants to learn "
              f"{lens}. Plain words, short sentences; any technical term "
              "gets explained the moment it appears. Never give investment "
              "advice or predictions.")
    prompt = (f"Today's {topic} headlines:\n{stories}\n\n"
              "In 5-7 sentences of plain prose: what actually happened, and "
              "the significance — why it matters to someone learning "
              f"{lens}, and what it teaches about how this world works. "
              "Then one final line formatted exactly as "
              "'Term worth knowing: <term> — <one plain sentence>' — pick "
              f"the most useful term from these stories.{avoid} Plain text "
              "only: no "
              "headers, no bullets, no bold or markdown, no introduction "
              "line — start with the first fact.")
    out = llm.complete("news", prompt, system=system, timeout=120)["text"]
    return out.replace("**", "").strip()


def _term_from(explainer):
    """Pull (term, definition) out of the explainer's closing line."""
    m = re.search(r"Term worth knowing:\s*(.+)", explainer)
    if not m:
        return None
    rest = m.group(1).strip()
    m2 = re.match(r"(.{2,60}?)\s+[—–-]+\s+(.+)", rest)
    if m2:
        return m2.group(1).strip(" '\"“”"), m2.group(2).strip()
    m2 = re.match(r"(.{2,60}?)\s+(?:is|are|means)\s+.+", rest)
    if m2:
        return m2.group(1).strip(" '\"“”"), rest
    return None


def _term_norm(term):
    return re.sub(r"(es|s)$", "", term.strip().lower())


def _glossary_terms():
    try:
        with open(GLOSSARY, encoding="utf-8") as f:
            return re.findall(r"^- \*\*(.+?)\*\*", f.read(), flags=re.M)
    except OSError:
        return []


def _glossary_add(term, definition, topic, day):
    """One term a day flows into her glossary. Upsert by term, first
    definition wins — the file reads as a learning journal, oldest first.
    She may edit or prune it; only ever append."""
    try:
        with open(GLOSSARY, encoding="utf-8") as f:
            body = f.read()
    except FileNotFoundError:
        body = ("---\n"
                "maintained-by: news.py appends; edits and pruning are hers\n"
                "---\n\n# Glossary\n\n"
                "Terms picked up from the daily briefings, one a day, "
                "oldest first.\n\n")
    # "Bond yield" is already there as "bond yields": same term.
    if _term_norm(term) in {_term_norm(t) for t in _glossary_terms()}:
        return False
    line = f"- **{term}** — {definition} *({day}, {topic})*\n"
    with open(GLOSSARY, "w", encoding="utf-8") as f:
        f.write(body.rstrip("\n") + "\n" + line)
    return True


def _week_log_add(day, topic, explainer, titles):
    """Keep each day's breakdowns for the Sunday recaps — the daily
    paragraphs teach a fact, the recap is what makes them add up."""
    try:
        with open(WEEK_LOG, encoding="utf-8") as f:
            entries = json.load(f)
    except Exception:
        entries = []
    entries = [e for e in entries
               if not (e.get("date") == day
                       and e.get("topic", "Money & markets") == topic)][-27:]
    entries.append({"date": day, "topic": topic,
                    "explainer": explainer, "titles": titles})
    with open(WEEK_LOG, "w", encoding="utf-8") as f:
        json.dump(entries, f, ensure_ascii=False, indent=1)


def _recap(entries):
    import llm
    days = "\n\n".join(f"{e['date']}:\n{e['explainer']}" for e in entries)
    system = ("You explain news to a smart beginner who is learning this "
              "field. Plain words, short sentences; any technical term "
              "gets explained the moment it appears. Never give investment "
              "advice or predictions.")
    prompt = ("These are the daily plain-language breakdowns from "
              f"the past week:\n\n{days}\n\n"
              "In 5-7 sentences of plain prose, tell the story of the week: "
              "what the days added up to, what connects them, what to watch "
              "next week. Then a final block starting exactly 'Terms from "
              "the week:' with the two or three most useful terms that came "
              "up, one line each, as reminders for someone learning. Plain "
              "text: no headers, no markdown bold, no bullets except those "
              "term lines.")
    out = llm.complete("news", prompt, system=system, timeout=120)["text"]
    return out.replace("**", "").strip()


def _explainers_on():
    """The Usage page's switch for the daily breakdowns (`ai_features.news`).
    They are the only model call the morning job makes on a Careful plan, so
    someone running the brain on the smallest allowance can turn off the last
    scheduled spend without losing the briefing itself. Absent means on."""
    try:
        with open(os.path.join(BRAIN, "config.json"), encoding="utf-8") as f:
            ov = (json.load(f).get("ai_features") or {}).get("news")
    except Exception:
        return True
    return ov is not False


def fetch(explain=False):
    # The switch only stops NEW explainers being written; a cached one from
    # earlier today still shows, because deleting today's briefing halfway
    # through the day is not what turning off tomorrow's spend means.
    explain = explain and _explainers_on()
    prev = {}
    try:
        with open(OUT_JSON, encoding="utf-8") as f:
            prev = json.load(f)
    except Exception:
        pass
    today = datetime.now().strftime("%Y-%m-%d")
    seen = _seen_load()
    data = build_briefing(seen=seen)
    _seen_record(data, seen, today)
    # The explainer is written once a day (the morning run passes
    # --explain); every later refresh reuses it, so the Refresh button
    # stays fast and the model is never called in a loop.
    cached = ({t["topic"]: t for t in prev.get("topics", [])}
              if prev.get("explained_on") == today else {})
    by_topic = {i.get("topic"): i for i in _news_cfg().get("interests") or []}
    for t in data["topics"]:
        interest = by_topic.get(t["topic"]) or {}
        if not interest.get("explain"):
            continue
        old = cached.get(t["topic"]) or {}
        if old.get("explainer") and len(old.get("items") or []) >= 2:
            # The paragraph explains the stories it was written about, so a
            # Refresh keeps the two together until tomorrow's.
            t["items"] = old["items"]
            t["explainer"] = old["explainer"].replace("**", "")
            data["explained_on"] = today
        # One story is a headline, not a pattern: eight sentences about a
        # single breath-testing mask taught nothing the headline didn't.
        elif explain and len(t["items"]) >= 2:
            try:
                t["explainer"] = _explain(t["topic"], t["items"],
                                          _lens(interest), _glossary_terms())
                data["explained_on"] = today
            except Exception as e:
                print(f"explainer skipped: {e}", file=sys.stderr)
        if t.get("explainer"):
            _week_log_add(today, t["topic"], t["explainer"],
                          [i["title"] for i in t["items"]])
            got = _term_from(t["explainer"])
            if got:
                _glossary_add(got[0], got[1], t["topic"], today)

    # The Sunday recaps: one more small call per learning topic per week,
    # then carried until the next one. Needs a few logged days each.
    def _age(datestr):
        try:
            return (datetime.now()
                    - datetime.strptime(datestr, "%Y-%m-%d")).days
        except Exception:
            return 99
    recaps = [r for r in (prev.get("recaps") or [])
              if _age(r.get("on", "")) <= 7]
    if explain and datetime.now().weekday() == 6:
        try:
            with open(WEEK_LOG, encoding="utf-8") as f:
                entries = [e for e in json.load(f) if _age(e["date"]) <= 7]
        except Exception:
            entries = []
        for t in data["topics"]:
            if not (by_topic.get(t["topic"]) or {}).get("explain"):
                continue
            if any(r["topic"] == t["topic"] and _age(r["on"]) < 6
                   for r in recaps):
                continue
            mine = [e for e in entries
                    if e.get("topic", "Money & markets") == t["topic"]]
            if len(mine) >= 3:
                try:
                    recaps = ([r for r in recaps if r["topic"] != t["topic"]]
                              + [{"topic": t["topic"], "on": today,
                                  "text": _recap(mine)}])
                except Exception as e:
                    print(f"recap skipped: {e}", file=sys.stderr)
    if recaps:
        data["recaps"] = recaps
    write_briefing(data)
    got = len(data["front"]) + sum(len(t["items"]) for t in data["topics"])
    print(f"briefing: {got} stories, {len(data['failed'])} feeds unreachable")
    return data


# ---------------------------------------------------------------- topics

def add_interest(topic, keywords=None):
    cfg = _config()
    ncfg = cfg.setdefault("news", {})
    interests = ncfg.setdefault("interests", [])
    low = topic.strip().lower()
    if not low:
        return False
    for i in interests:
        if i.get("topic", "").lower() == low:
            if keywords:
                i["keywords"] = sorted(set((i.get("keywords") or []) + keywords))
                _save_config(cfg)
            return True
    interests.append({"topic": topic.strip(),
                      **({"keywords": keywords} if keywords else {})})
    _save_config(cfg)
    return True


def remove_interest(topic):
    cfg = _config()
    ncfg = cfg.setdefault("news", {})
    interests = ncfg.get("interests") or []
    kept = [i for i in interests if i.get("topic", "").lower() != topic.strip().lower()]
    if len(kept) == len(interests):
        return False
    ncfg["interests"] = kept
    _save_config(cfg)
    return True


def main(argv):
    cmd = argv[0] if argv else "fetch"
    if cmd == "fetch":
        fetch(explain="--explain" in argv)
    elif cmd == "list":
        for i in _news_cfg().get("interests") or []:
            kw = ", ".join(i.get("keywords") or [])
            print(i.get("topic", "") + (f"  ({kw})" if kw else ""))
    elif cmd == "add" and len(argv) > 1:
        kws = [k.strip() for k in argv[2].split(",")] if len(argv) > 2 else None
        add_interest(argv[1], kws)
        fetch()
    elif cmd == "remove" and len(argv) > 1:
        if remove_interest(argv[1]):
            fetch()
        else:
            print("no such topic")
    elif cmd == "cookie" and len(argv) > 1:
        host = argv[1].strip().lower().lstrip(".")
        if len(argv) > 2:
            kc_set(argv[2].strip(), "cookie:" + host)
            print(f"cookie stored for {host}")
        if not kc_get("cookie:" + host):
            print(f"No cookie stored for {host}. Log in to the site in your "
                  "browser, copy the Cookie header from any request to it "
                  "(DevTools → Network), then:\n"
                  f"  python3 brain/tools/news.py cookie {host} 'PASTE-IT'")
        else:
            try:
                with open(OUT_JSON, encoding="utf-8") as f:
                    data = json.load(f)
                items = list(data.get("front") or [])
                for t in data.get("topics") or []:
                    items.extend(t["items"])
                link = next((i["link"] for i in items
                             if host in i.get("link", "")), None)
            except Exception:
                link = None
            if not link:
                print("Stored. No story from that site in today's briefing "
                      "to test against — it gets used on the next pull.")
            else:
                try:
                    print(f"works — pulled {len(article_text(link))} "
                          "characters of article text")
                except Exception as e:
                    print(f"stored, but the pull still fails: {e}")
    elif cmd == "guardian":
        if len(argv) > 1:
            kc_set(argv[1].strip())
            print("key stored in the keychain — fetching with it now")
            fetch()
        elif not kc_get():
            print("No key stored. Register a free personal key at\n"
                  "  https://open-platform.theguardian.com/access/\n"
                  "(pick 'developer'; the key arrives by email), then run:\n"
                  "  python3 brain/tools/news.py guardian YOUR-KEY")
        else:
            feed = next((f for f in _news_cfg().get("feeds") or []
                         if f.get("kind") == "guardian"), None)
            if not feed:
                print("key stored, but no guardian feed in config")
            else:
                try:
                    n = len(_fetch_one(feed))
                    print(f"key works — {n} articles with full excerpts")
                except Exception as e:
                    print(f"key stored but the API call failed: {e}")
    else:
        print(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])

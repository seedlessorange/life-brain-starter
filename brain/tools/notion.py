#!/usr/bin/env python3
"""Pull your Notion class notes into the brain.

    python3 brain/tools/notion.py --connect <token>   # once, stores in Keychain
    python3 brain/tools/notion.py --list              # what it can see
    python3 brain/tools/notion.py --pull              # into brain/school/notes/

Notion has a real API, so this needs no scraping and no password. What it
needs once is an integration token:

    1. notion.so/my-integrations → New integration → internal, read-only
       (Read content is the only capability to tick)
    2. copy the token (starts `ntn_` or `secret_`)
    3. in Notion, open the page holding your class notes → ⋯ → Connections →
       add the integration. Sub-pages come with it.
    4. python3 brain/tools/notion.py --connect ntn_...

The token goes into the OS keystore, never into a file — this repo is
committed and sometimes pushed. It can only read the pages you connected in
step 3: an integration sees nothing you haven't handed it.

Pulled pages land in brain/school/notes/ as markdown. They are a copy, so
they are safe to reread and safe to lose; Notion stays the original. Nothing
is ever written back to Notion — this is read-only in both directions.
"""

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import date, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
BRAIN = os.path.dirname(HERE)
sys.path.insert(0, HERE)

OUT = os.path.join(BRAIN, "school", "notes")
API = "https://api.notion.com/v1"
VERSION = "2022-06-28"          # the stable public version
KC_SERVICE = "life-brain-notion"
KC_ACCOUNT = "token"
TIMEOUT = 20
MAX_PAGES = 250                 # her whole MBA is ~160 pages; that is the point
MAX_DEPTH = 4


# --------------------------------------------------------------------------
# the token

def kc_set(value):
    import keychain
    keychain.put(KC_SERVICE, KC_ACCOUNT, value)


def kc_get():
    import keychain
    return keychain.get(KC_SERVICE, KC_ACCOUNT)


def connected():
    return bool(kc_get())


# --------------------------------------------------------------------------
# the api

def _call(path, method="GET", body=None, _retries=3):
    token = kc_get()
    if not token:
        raise ValueError(
            "Notion isn't connected yet — see the top of notion.py for the "
            "four steps, then --connect <token>")
    req = urllib.request.Request(
        API + path, method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Authorization": "Bearer " + token,
                 "Notion-Version": VERSION,
                 "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return json.load(r)
    except urllib.error.HTTPError as exc:
        if exc.code == 429 and _retries:
            import time
            time.sleep(float(exc.headers.get("Retry-After") or 2))
            return _call(path, method, body, _retries - 1)
        detail = ""
        try:
            detail = (json.load(exc).get("message") or "")[:200]
        except Exception:                                # noqa: BLE001
            pass
        if exc.code == 401:
            raise ValueError("Notion refused the token — reconnect it")
        if exc.code == 404:
            raise ValueError("Notion can't see that page. In Notion: the "
                             "page → ⋯ → Connections → add the integration.")
        raise ValueError("Notion said %s%s" % (exc.code,
                                               " — " + detail if detail else ""))
    except urllib.error.URLError as exc:
        raise ValueError("couldn't reach Notion (%s)" % exc.reason)


def _title(obj):
    """A title, wherever this object type keeps it.

    A database's name is a rich-text list at `title`. A page's is inside
    `properties`, under whichever property has type "title". Checking
    properties first gets a database wrong every time — its schema also has
    a title-typed property, but that holds the column's definition, not the
    database's name, so everything comes back "Untitled"."""
    if obj.get("object") == "database" and obj.get("title"):
        return _rich(obj["title"]).strip() or "Untitled"
    props = obj.get("properties") or {}
    for prop in props.values():
        if prop.get("type") == "title":
            got = _rich(prop.get("title") or []).strip()
            if got:
                return got
    if obj.get("title"):
        return _rich(obj["title"]).strip() or "Untitled"
    return "Untitled"


def pages():
    """Every page and database the integration has been given.

    `parent` matters: a database's rows come back from search as ordinary
    pages, so without it a class planner of twelve courses is pulled once as
    a table and again as twelve loose files saying the same thing."""
    out, cursor = [], None
    while True:
        body = {"page_size": 100,
                "sort": {"direction": "descending",
                         "timestamp": "last_edited_time"}}
        if cursor:
            body["start_cursor"] = cursor
        data = _call("/search", "POST", body)
        for obj in data.get("results", []):
            parent = obj.get("parent") or {}
            out.append({
                "id": obj["id"],
                "kind": obj.get("object", "page"),
                "title": _title(obj),
                "edited": (obj.get("last_edited_time") or "")[:10],
                "url": obj.get("url", ""),
                "parent_db": parent.get("database_id", ""),
            })
        cursor = data.get("next_cursor")
        if not data.get("has_more") or not cursor or len(out) >= MAX_PAGES * 2:
            break
    return out


def _prop_text(prop):
    """One Notion property as something a person would read."""
    t = (prop or {}).get("type", "")
    v = (prop or {}).get(t)
    if t in ("title", "rich_text"):
        return _rich(v or [])
    if t == "select":
        return (v or {}).get("name", "")
    if t in ("multi_select",):
        return ", ".join(x.get("name", "") for x in (v or []))
    if t == "status":
        return (v or {}).get("name", "")
    if t == "date":
        if not v:
            return ""
        start, end = v.get("start") or "", v.get("end") or ""
        return ("%s → %s" % (start[:10], end[:10])) if end else start[:10]
    if t in ("number",):
        return "" if v is None else str(v)
    if t == "checkbox":
        return "yes" if v else "no"
    if t in ("url", "email", "phone_number"):
        return v or ""
    if t == "people":
        return ", ".join(x.get("name", "") for x in (v or []) if x.get("name"))
    if t == "files":
        return ", ".join(f.get("name", "") for f in (v or []))
    if t == "relation":
        return "%d linked" % len(v or []) if v else ""
    if t in ("created_time", "last_edited_time"):
        return (v or "")[:10]
    if t == "formula":
        return str((v or {}).get((v or {}).get("type", ""), "") or "")
    if t == "rollup":
        return str((v or {}).get("number", "") or "")
    return ""


def rows(db_id):
    """A database's rows, in its own order."""
    out, cursor = [], None
    while True:
        body = {"page_size": 100}
        if cursor:
            body["start_cursor"] = cursor
        data = _call("/databases/%s/query" % db_id, "POST", body)
        out += data.get("results", [])
        cursor = data.get("next_cursor")
        if not data.get("has_more") or not cursor or len(out) >= 300:
            break
    return out


CACHE = os.path.join(BRAIN, ".notion-cache.json")


def _cache():
    try:
        with open(CACHE, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _save_cache(c):
    tmp = CACHE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(c, f)
    os.replace(tmp, CACHE)


def _database_md(db_id, title):
    """A database as a markdown table, plus whatever she wrote inside each
    row — which for a class planner is the actual notes, and the reason to
    pull it at all.

    Row bodies are cached against the row's own last-edited stamp. Without
    that this walks every row of every database on every run: her thirteen
    databases hold ~100 rows, each needing its own blocks call, which turned
    a morning job into twenty minutes of API traffic to rediscover notes
    nobody had touched."""
    rs = rows(db_id)
    if not rs:
        return "*(empty)*"
    # The title column is the row's name, so it leads — Notion returns
    # properties in no particular order, and a planner whose "Course Name"
    # fell outside the first eight columns is a table of blanks.
    title_col, cols, seen = "", [], set()
    for r in rs:
        for name, prop in (r.get("properties") or {}).items():
            if prop.get("type") == "title" and not title_col:
                title_col = name
                continue
            if name not in seen and prop.get("type") != "relation":
                seen.add(name)
                cols.append(name)
    cols = ([title_col] if title_col else []) + cols[:7]
    lines = ["| " + " | ".join(cols) + " |",
             "|" + "|".join(["---"] * len(cols)) + "|"]
    bodies = []
    cache, changed = _cache(), [False]
    for r in rs:
        props = r.get("properties") or {}
        cells = [_prop_text(props.get(c, {})).replace("|", "\\|")[:80]
                 or "—" for c in cols]
        lines.append("| " + " | ".join(cells) + " |")
        name = next((_prop_text(p) for p in props.values()
                     if p.get("type") == "title"), "") or "Untitled"
        stamp = (r.get("last_edited_time") or "")
        hit = cache.get(r["id"])
        if hit and hit.get("edited") == stamp:
            body = hit.get("body", "")
        else:
            try:
                body = "\n".join(_blocks(r["id"]))
            except ValueError:
                body = ""
            cache[r["id"]] = {"edited": stamp, "body": body}
            changed[0] = True
        if body.strip():
            bodies.append("## %s\n\n%s" % (name, body.strip()))
    if changed[0]:
        _save_cache(cache)
    md = "\n".join(lines)
    if bodies:
        md += "\n\n" + "\n\n".join(bodies)
    return md


# --------------------------------------------------------------------------
# blocks to markdown

def _rich(items):
    out = []
    for r in items or []:
        t = r.get("plain_text", "")
        ann = r.get("annotations") or {}
        if not t.strip():
            out.append(t)
            continue
        if ann.get("code"):
            t = "`%s`" % t
        if ann.get("bold"):
            t = "**%s**" % t
        if ann.get("italic"):
            t = "*%s*" % t
        link = (r.get("href") or "")
        if link:
            t = "[%s](%s)" % (t, link)
        out.append(t)
    return "".join(out)


BLOCK_PREFIX = {
    "heading_1": "# ", "heading_2": "## ", "heading_3": "### ",
    "bulleted_list_item": "- ", "numbered_list_item": "1. ",
    "quote": "> ", "callout": "> ",
    "to_do": None,      # handled below, the tick matters
}


def _blocks(block_id, depth=0):
    """One page's content as markdown lines, children included."""
    if depth > MAX_DEPTH:
        return []
    lines, cursor = [], None
    while True:
        q = "?page_size=100" + (("&start_cursor=" + cursor) if cursor else "")
        data = _call("/blocks/%s/children%s" % (block_id, q))
        for b in data.get("results", []):
            t = b.get("type", "")
            payload = b.get(t) or {}
            text = _rich(payload.get("rich_text") or [])
            pad = "  " * max(0, depth - 1)
            if t == "to_do":
                mark = "x" if payload.get("checked") else " "
                lines.append("%s- [%s] %s" % (pad, mark, text))
            elif t == "code":
                lines.append("```%s\n%s\n```"
                             % (payload.get("language", ""), text))
            elif t == "divider":
                lines.append("---")
            elif t == "child_page":
                lines.append("%s- *(sub-page: %s)*"
                             % (pad, payload.get("title", "untitled")))
            elif t in BLOCK_PREFIX:
                lines.append(pad + (BLOCK_PREFIX[t] or "") + text)
            elif text.strip():
                lines.append(pad + text)
            if b.get("has_children") and t != "child_page":
                lines += _blocks(b["id"], depth + 1)
        cursor = data.get("next_cursor")
        if not data.get("has_more") or not cursor:
            break
    return lines


def _slug(s):
    s = re.sub(r"[^a-z0-9]+", "-", (s or "").lower())
    return re.sub(r"-+", "-", s).strip("-")[:48] or "untitled"


def pull(match="", limit=MAX_PAGES):
    """Every page the integration can see, as markdown, into school/notes/."""
    wrote, skipped = [], 0
    os.makedirs(OUT, exist_ok=True)
    everything = pages()
    dbs = {p["id"].replace("-", "") for p in everything
           if p["kind"] == "database"}
    for p in everything[:limit]:
        if match and match.lower() not in p["title"].lower():
            continue
        # A row of a database we are already pulling as a table.
        if (p.get("parent_db") or "").replace("-", "") in dbs:
            continue
        path = os.path.join(OUT, _slug(p["title"]) + ".md")
        # Unchanged since the last pull? Notion's own edit stamp says so.
        # A database's own last_edited_time does not move when a row is
        # edited, so a planner would freeze on its first pull. Databases are
        # always re-read; plain pages skip when Notion says nothing changed.
        if os.path.exists(path) and p["kind"] != "database":
            try:
                with open(path, encoding="utf-8") as f:
                    head = f.read(400)
                if ("edited: " + p["edited"]) in head:
                    skipped += 1
                    continue
            except OSError:
                pass
        try:
            body = (_database_md(p["id"], p["title"])
                    if p["kind"] == "database"
                    else "\n".join(_blocks(p["id"])))
        except ValueError as exc:
            wrote.append({"failed": p["title"], "why": str(exc)})
            continue
        with open(path, "w", encoding="utf-8") as f:
            f.write("---\nfrom: notion\nkind: %s\nedited: %s\npulled: %s\n"
                    "url: %s\n---\n\n# %s\n\n%s\n"
                    % (p["kind"], p["edited"], date.today().isoformat(),
                       p["url"], p["title"], body.strip()))
        wrote.append({"page": p["title"], "file": path})
    return {"wrote": [w for w in wrote if "file" in w],
            "failed": [w for w in wrote if "failed" in w],
            "unchanged": skipped}


# --------------------------------------------------------------------------
# cli

def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--connect", metavar="TOKEN")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--pull", action="store_true")
    ap.add_argument("--match", default="", help="only pages whose title "
                                                "contains this")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    if a.connect:
        tok = a.connect.strip()
        if not re.match(r"^(ntn_|secret_)", tok):
            print("that doesn't look like a Notion token (expected ntn_… "
                  "or secret_…)")
            return 1
        kc_set(tok)
        try:
            n = len(pages())
        except ValueError as exc:
            print("Stored, but Notion says: %s" % exc)
            return 1
        print("Connected. Notion is sharing %d page%s with the brain."
              % (n, "" if n == 1 else "s"))
        if n == 0:
            print("None yet — in Notion, open your class notes page → ⋯ → "
                  "Connections → add the integration.")
        return 0

    if not connected():
        print("Notion isn't connected yet. Four steps, once:\n\n"
              "  1. notion.so/my-integrations → New integration → internal,\n"
              "     and tick only Read content\n"
              "  2. copy the token (it starts ntn_ or secret_)\n"
              "  3. in Notion, open the page holding your class notes →\n"
              "     ⋯ → Connections → add the integration\n"
              "  4. python3 brain/tools/notion.py --connect <token>\n\n"
              "The token goes into the Keychain, never a file. The "
              "integration\ncan read only the pages you connect in step 3.")
        return 1

    if a.list:
        ps = pages()
        if a.json:
            print(json.dumps(ps, indent=2))
            return 0
        if not ps:
            print("Notion is sharing nothing yet. In Notion: the page → ⋯ → "
                  "Connections → add the integration.")
            return 0
        print("%d thing%s shared with the brain:\n"
              % (len(ps), "" if len(ps) == 1 else "s"))
        for p in ps:
            print("  %s  %-52s %s" % (p["edited"] or "----------",
                                      p["title"][:52], p["kind"]))
        return 0

    if a.pull:
        r = pull(match=a.match)
        if a.json:
            print(json.dumps(r, indent=2))
            return 0
        for w in r["wrote"]:
            print("  wrote  %s" % os.path.basename(w["file"]))
        for w in r["failed"]:
            print("  failed %s — %s" % (w["failed"], w["why"]))
        print("\n%d page%s written, %d unchanged."
              % (len(r["wrote"]), "" if len(r["wrote"]) == 1 else "s",
                 r["unchanged"]))
        return 0

    print("Connected. --list to see what Notion is sharing, --pull to bring "
          "it in.")
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)

#!/usr/bin/env python3
"""browser_scan.py — find roles the job-board scan cannot see.

    (started by the page: Jobs tab, "Check the boards", when the scan helper
    is switched on)

Two sources, both read-only and logged out:

  - LinkedIn's public job search: the same results anyone sees on
    linkedin.com/jobs without signing in, for each role word she looks for
    in each place she names, posted in the last week. Plain web requests, a
    few seconds apart, two pages per search at most.
  - Careers pages she adds (config `jobs.pages`): a company site with no
    public board. Opened in a hidden Chrome with no profile, so no login and
    no cookie of hers is ever there; the links whose text matches what she
    looks for become roles.

Welcome to the Jungle moved its job search behind a sign-in in 2026, and its
company pages list no roles to a visitor, so it is not read.

Everything found goes through jobs.merge_found(): the same title and place
filters, the same "never show a skipped role again", and the fit score on
the next scan.
"""
import html
import os
import random
import re
import sys
import time
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import browser_core as BC                                   # noqa: E402

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/140.0 Safari/537.36")
LI_SEARCH = ("https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/"
             "search?keywords={k}&location={l}&f_TPR=r604800&start={s}")


def _get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA,
                                               "Accept-Language": "en,fr;q=0.8"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read(3 * 1024 * 1024).decode("utf-8", "replace")


def _txt(m):
    return html.unescape(re.sub(r"\s+", " ", m.group(1))).strip() if m else ""


def linkedin_search(titles, places):
    out, seen = [], set()
    places = [p for p in places if p.lower() not in ("remote", "full remote",
                                                     "teletravail")][:2] or [""]
    for t in titles[:10]:
        for p in places:
            for start in (0, 25):
                try:
                    raw = _get(LI_SEARCH.format(k=urllib.parse.quote(t),
                                                l=urllib.parse.quote(p), s=start))
                except Exception:                               # noqa: BLE001
                    break
                cards = raw.split("<li")[1:]
                for c in cards:
                    jid = re.search(r"jobPosting:(\d+)", c)
                    if not jid or jid.group(1) in seen:
                        continue
                    seen.add(jid.group(1))
                    title = _txt(re.search(r'base-search-card__title[^>]*>(.*?)<', c, re.S))
                    comp = _txt(re.search(r'base-search-card__subtitle.*?<a[^>]*>(.*?)<', c, re.S)) \
                        or _txt(re.search(r'base-search-card__subtitle[^>]*>(.*?)<', c, re.S))
                    where = _txt(re.search(r'job-search-card__location[^>]*>(.*?)<', c, re.S))
                    posted = re.search(r'datetime="(\d{4}-\d{2}-\d{2})"', c)
                    if not title:
                        continue
                    out.append({"key": "linkedin:search:" + jid.group(1),
                                "title": title, "company": comp or "LinkedIn",
                                "url": "https://www.linkedin.com/jobs/view/" + jid.group(1),
                                "where": where, "remote": "remote" in where.lower(),
                                "posted": posted.group(1) if posted else ""})
                if len(cards) < 25:
                    break
                time.sleep(random.uniform(2.0, 4.5))
            time.sleep(random.uniform(2.0, 4.5))
    return out


PAGE_JS = r"""
() => [...document.querySelectorAll('a[href]')].map(a => ({
  href: a.href, text: (a.innerText || a.textContent || '').replace(/\s+/g, ' ').trim()
})).filter(x => x.text && x.text.length < 160 && /^https:/.test(x.href))
"""


def careers_pages(pages, ok_title):
    """Each page's links whose text reads like a role she wants."""
    import jobs as J
    from playwright.sync_api import sync_playwright
    results = {}
    with sync_playwright() as pw:
        ctx = BC.launch(pw, None, headless=True)     # no profile, no login
        page = ctx.new_page()
        for pg in pages:
            url, name = pg.get("url", ""), pg.get("name") or pg.get("url", "")
            if not J._public_https(url):
                results[name] = None
                continue
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=45000)
                try:
                    page.wait_for_load_state("networkidle", timeout=12000)
                except Exception:                               # noqa: BLE001
                    pass
                for _ in range(3):
                    page.mouse.wheel(0, 1600)
                    page.wait_for_timeout(900)
                links = page.evaluate(PAGE_JS)
            except Exception:                                   # noqa: BLE001
                results[name] = None
                continue
            host = urllib.parse.urlparse(url).hostname or ""
            found, seen = [], set()
            for l in links:
                if l["href"] in seen or not ok_title({"title": l["text"], "where": ""}):
                    continue
                seen.add(l["href"])
                path = urllib.parse.urlparse(l["href"]).path
                found.append({"key": "page:%s:%s" % (host, path[:180]),
                              "title": l["text"][:140], "company": name,
                              "url": l["href"], "where": "", "remote": False,
                              "posted": ""})
            results[name] = found
            time.sleep(random.uniform(1.5, 3.0))
        ctx.close()
    return results


def main(argv):
    BC.guard("scan")
    import jobs as J
    jc = J.jobs_cfg()
    BC.write_status("scan", state="reading")
    report = {}
    titles = J.all_titles(jc)
    if titles:
        places = []
        for t in J.tracks(jc):
            places += [p for p in t["places"] if p not in places]
        found = linkedin_search(titles, places)
        report["LinkedIn search"] = J.merge_found("LinkedIn search", found, "search")
    pages = [p for p in (jc.get("pages") or []) if isinstance(p, dict)]
    if pages:
        tm = J.track_matcher(jc, ignore_places=True)   # pages rarely say where
        ok = lambda r: bool(tm(r))                     # noqa: E731
        for name, found in careers_pages(pages, ok).items():
            report[name] = (J.merge_found(name, found, "page")
                            if found is not None else {"error": "did not open"})
    # Sources she removed stop counting.
    st = J._state()
    active = {"LinkedIn search"} | {p.get("name") or p.get("url") for p in pages}
    st["sources"] = {k: v for k, v in (st.get("sources") or {}).items()
                     if k in active}
    J._save_state(st)
    BC.write_status("scan", state="done", report=report,
                    new=sum(r.get("new", 0) for r in report.values()))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except SystemExit as ex:
        if isinstance(ex.code, str):
            BC.write_status("scan", state="error", error=ex.code)
        raise

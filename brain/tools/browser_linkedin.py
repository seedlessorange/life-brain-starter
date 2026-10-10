#!/usr/bin/env python3
"""browser_linkedin.py — read her LinkedIn connections in a browser she logs
into, into the same file LinkedIn's own export makes.

    (started by the page: Jobs tab, the LinkedIn helper)
    browser_linkedin.py login          open LinkedIn to log in, once
    browser_linkedin.py connections    read the connections list

LinkedIn's terms forbid automated reading, and an account that reads too fast
gets restricted. So this reads at a person's pace, once a day at most, and
only one page: her own connections list. It never opens anyone's profile,
never sends an invitation or a message, and clicks one thing only, the list's
own "Show more results" button.

What it keeps, per connection: the name, the headline (split into role and
company when it reads "Role at Company"), the profile link and nothing else.
It writes brain/files/linkedin/Connections-browser.csv in the export's own
columns, beside the real export. The From LinkedIn review on People reads
both, fills blank fields for people she already keeps, and adds no one
without her click.
"""
import csv
import json
import os
import random
import re
import sys
import time
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import browser_core as BC                                   # noqa: E402

BRAIN = os.path.dirname(HERE)
OUT = os.path.join(BRAIN, "files", "linkedin", "Connections-browser.csv")
LOG = os.path.join(BC.ROOT, "linkedin-log.json")
CONNECTIONS = "https://www.linkedin.com/mynetwork/invite-connect/connections/"
MAX_ROWS = 1500
MORE = re.compile(r"^(show more results|afficher plus de résultats|"
                  r"mostrar más resultados)$", re.I)

READ_JS = r"""
() => {
  const out = [], seen = new Set();
  document.querySelectorAll('a[href*="/in/"]').forEach(a => {
    const m = a.href.match(/linkedin\.com\/in\/([^/?#]+)/);
    if(!m || seen.has(m[1])) return;
    const card = a.closest('li') || a.closest('[data-view-name]') || a.parentElement;
    const lines = (card ? card.innerText : a.innerText).split('\n')
      .map(s => s.trim()).filter(Boolean)
      .filter(s => !/^(message|envoyer un message|mensaje|connected on|connecté le|.*\bconnected\b.*ago)$/i.test(s));
    if(!lines.length) return;
    seen.add(m[1]);
    out.push({url: 'https://www.linkedin.com/in/' + m[1], lines: lines.slice(0, 4)});
  });
  return out;
}
"""


def _log():
    try:
        with open(LOG, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_log(d):
    os.makedirs(BC.ROOT, exist_ok=True)
    with open(LOG, "w", encoding="utf-8") as f:
        json.dump(d, f)


def _split(headline):
    """'Product Manager at Brightloom' -> ('Product Manager', 'Brightloom')."""
    h = re.sub(r"\s+", " ", headline or "").strip()
    m = re.match(r"^(.{2,90}?)\s+(?:at|chez|en|@|\|)\s+(.{2,60}?)(?:\s*[|·•,].*)?$", h)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    return h[:90], ""


def _first_last(name):
    parts = name.split()
    return (parts[0], " ".join(parts[1:])) if len(parts) > 1 else (name, "")


def login():
    from playwright.sync_api import sync_playwright
    BC.write_status("linkedin", state="login")
    with sync_playwright() as pw:
        ctx = BC.launch(pw, "linkedin", headless=False)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto("https://www.linkedin.com/login", wait_until="domcontentloaded")
        end = time.time() + 600
        ok = False
        while time.time() < end:
            try:
                if re.search(r"linkedin\.com/(feed|mynetwork|in/)", page.url):
                    ok = True
                    break
                page.wait_for_timeout(2000)
            except Exception:                                   # noqa: BLE001
                break
        try:
            ctx.close()
        except Exception:                                       # noqa: BLE001
            pass
    BC.write_status("linkedin", state="logged in" if ok else "not logged in")
    return 0 if ok else 1


def connections():
    log = _log()
    today = str(date.today())
    if log.get("last") == today:
        BC.write_status("linkedin", state="error",
                        error="already read today; once a day keeps the "
                              "account safe")
        return 1
    from playwright.sync_api import sync_playwright
    BC.write_status("linkedin", state="reading", read=0)
    rows = {}
    with sync_playwright() as pw:
        ctx = BC.launch(pw, "linkedin", headless=False)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto(CONNECTIONS, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(4000)
        if "/login" in page.url or "/checkpoint" in page.url or "authwall" in page.url:
            ctx.close()
            BC.write_status("linkedin", state="error",
                            error="log in to LinkedIn first")
            return 1
        still = 0
        while len(rows) < MAX_ROWS and still < 4:
            before = len(rows)
            for r in page.evaluate(READ_JS):
                rows.setdefault(r["url"], r["lines"])
            BC.write_status("linkedin", state="reading", read=len(rows))
            page.mouse.wheel(0, random.randint(1400, 2200))
            page.wait_for_timeout(random.randint(1800, 3600))
            more = page.get_by_role("button", name=MORE)
            if more.count() and more.first.is_visible():
                more.first.click()               # the list's own button, only
                page.wait_for_timeout(random.randint(2500, 4500))
            still = still + 1 if len(rows) == before else 0
        ctx.close()
    out = []
    for url, lines in rows.items():
        name = lines[0]
        if not re.match(r"^[^\d@]{2,80}$", name):
            continue
        role, company = _split(lines[1] if len(lines) > 1 else "")
        first, last = _first_last(name)
        out.append({"First Name": first, "Last Name": last, "URL": url,
                    "Email Address": "", "Company": company, "Position": role,
                    "Connected On": ""})
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["First Name", "Last Name", "URL",
                                          "Email Address", "Company",
                                          "Position", "Connected On"])
        w.writeheader()
        w.writerows(out)
    log["last"] = today
    _save_log(log)
    BC.write_status("linkedin", state="done", read=len(out))
    return 0


def main(argv):
    BC.guard("linkedin")
    cmd = argv[0] if argv else "connections"
    if cmd == "login":
        return login()
    if cmd == "connections":
        return connections()
    print(__doc__)
    return 2


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except SystemExit as ex:
        if isinstance(ex.code, str):
            BC.write_status("linkedin", state="error", error=ex.code)
        raise

#!/usr/bin/env python3
"""The page's simplicity budget: how much the brain asks her to learn.

Every session can add a button and none has the job of removing one. On 28
Sep the redraw promised one box with no modes to pick, a task row of tick, ✦
and ⋯, and For you's top three on Today; nine days later the box had twelve
modes, every task had four buttons, and Today ran 3.4 screens. Nothing
noticed. These limits are what notices (the plan: design/fewer-doors.html).

Counts are read from the BUILT page, because that is what she sees. A change
that pushes a count over its limit fails the self-test until something else
is retired; lowering a limit after a cut is part of the cut.

    python3 brain/tools/budget.py            # the counts against their limits
    python3 brain/tools/budget.py --measure  # also page lengths, in a browser

The page lengths need a real layout, so they run only on --measure (at the
end of /finish), never in the one-second self-test.
"""

import json
import os
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BRAIN = os.path.dirname(HERE)
PAGE = os.path.join(BRAIN, "index.html")

# What each count means, and its ceiling. Lower a number when a phase cuts
# below it; raising one is a decision for her, never a fix for a failing build.
LIMITS = {
    # 13 since 8 Oct: her call to put News in the bar, out of Life. 14
    # since 9 Oct: her call to put Talk back in the bar on every style.
    "header":       (14, "controls in the header"),
    "box_choices":  (3,  "choices behind the box's ⋯"),
    "task_menu":    (7,  "choices behind a task's ⋯"),
    "row_controls": (3,  "buttons on a task row"),
    "sheet_items":  (20, "things the one-page sheet teaches"),
    "cut_titles":   (0,  "task titles cut short with …"),
}
# Where a task title is shown (page.md, "Whole titles", 8 Oct: "Alot of them
# are cut off"). A title wraps or clamps in CSS; one that ends in "…" in the
# HTML was cut in Python and can never be read whole, not even on hover.
_TITLES = ("wtx", "fc-go", "trt", "pdtext", "wtask")
# The one-page sheet (design/pocket-card): each thing it teaches carries
# data-learn. Her own brain only; the starter ships without it.
SHEET = os.path.join(os.path.dirname(BRAIN), "design", "pocket-card",
                     "brain-pocket-card.html")

# Laptop screens (1440×900), measured with Today pinned to 11:00 so the
# evening cards don't count against the daytime page. People is its Needs
# you view, the one it opens on. A page's length moves with the day's
# content, so each limit sits about a tenth above what it measured when it
# was last cut (7 Oct: Today 2.4, People 2.4, the Plate 4.7).
SCREENS = {
    "today":  2.7,
    "plate":  5.2,
    "people": 2.7,
}

# ⋯ choices that only exist on today's three, or replace another choice
# depending on the task's state (Put it back for a done task, Un-park for a
# parked one). They are not extra things to learn on an ordinary task.
_PLAN_ONLY = {"td-kick", "td-swap", "td-planday", "td-up", "td-down"}
_ALTERNATES = {"td-undone", "td-unpark"}
_ROW = ("tick", "ttalk", "tstart", "tmenu")


def counts(html=None):
    """The countable things on the built page, as {name: number}."""
    if html is None:
        with open(PAGE, encoding="utf-8") as f:
            html = f.read()
    out = {}
    i = html.find('<header class="top"')
    j = html.find("</header>", i)
    head = html[i:j] if i >= 0 and j > i else ""
    out["header"] = len(re.findall(r"<(?:a|button|input)\b", head))
    out["box_choices"] = (len(re.findall(r'class="askintent\b', html))
                          + len(re.findall(r'class="askdump\b', html)))
    i = html.find('id="taskdlg"')
    j = html.find('id="td-cancel"', i)
    menu = html[i:j] if i >= 0 and j > i else ""
    ids = set(re.findall(r'<button class="tdopt[^"]*" id="(td-[a-z]+)"', menu))
    out["task_menu"] = len(ids - _PLAN_ONLY - _ALTERNATES)
    out["row_controls"] = sum(
        1 for c in _ROW
        if re.search(r'class="[^"]*\b' + c + r'\b[^"]*"', html))
    if os.path.exists(SHEET):
        with open(SHEET, encoding="utf-8") as f:
            out["sheet_items"] = f.read().count("data-learn")
    out["cut_titles"] = len(cut_titles(html))
    return out


def cut_titles(html):
    """Task titles on the page that end in an ellipsis, as their last words."""
    cut = []
    rx = re.compile(r'class="(?:[^"]*\s)?(' + "|".join(_TITLES)
                    + r')(?:\s[^"]*)?"[^>]*>(.*?)</', re.S)
    for m in rx.finditer(html):
        txt = re.sub(r"<[^>]+>", " ", m.group(2)).strip()
        if txt.endswith(("…", "&hellip;", "&#8230;")):
            cut.append(txt[-50:])
    # .bstext's bold title, the evening card's closed list, Orbit's three.
    for m in re.finditer(r'class="bstext"><b[^>]*>([^<]*)</b>'
                         r'|<ul class=.dayl.>(.*?)</ul>'
                         r'|data-deckjump="today"[^>]*>([^<]*)<', html, re.S):
        for li in re.split(r"<li[^>]*>", m.group(m.lastindex) or ""):
            li = re.sub(r"<[^>]+>", "", li).strip()
            if li.endswith(("…", "&hellip;", "&#8230;")):
                cut.append(li[-50:])
    return cut


def over(found=None):
    """Lines describing every count above its limit (empty when within)."""
    found = found if found is not None else counts()
    bad = []
    for k, (cap, what) in LIMITS.items():
        n = found.get(k, 0)
        if n > cap:
            bad.append(f"{n} {what}, limit {cap}")
    return bad


_MEASURE_JS = r"""
// node -e puts the first argument at argv[1].
const {chromium} = require(process.argv[1]);
(async () => {
  const b = await chromium.launch();
  const p = await b.newPage({viewport: {width: 1440, height: 900}});
  await p.addInitScript(() => {
    const T = new Date(); T.setHours(11, 0, 0, 0);
    const D = Date;
    globalThis.Date = class extends D {
      constructor(...a) { if (a.length) super(...a); else super(T.getTime()); }
      static now() { return T.getTime(); }
    };
  });
  const out = {};
  for (const v of JSON.parse(process.argv[3])) {
    await p.goto('file://' + process.argv[2] + '#/' + v);
    await p.waitForTimeout(700);
    out[v] = await p.evaluate(() =>
      document.documentElement.scrollHeight / innerHeight);
  }
  console.log(JSON.stringify(out));
  await b.close();
})().catch(e => { console.error(String(e)); process.exit(2); });
"""


def measure():
    """Page lengths in laptop screens, or None when no browser is to hand."""
    pw = os.path.expanduser(
        "~/.claude/skills/gstack/node_modules/playwright-core")
    node = shutil.which("node")
    if not node or not os.path.isdir(pw):
        return None
    try:
        r = subprocess.run(
            [node, "-e", _MEASURE_JS, pw, PAGE, json.dumps(list(SCREENS))],
            capture_output=True, text=True, timeout=120)
        return json.loads(r.stdout.strip().splitlines()[-1])
    except Exception:
        return None


def main():
    found = counts()
    for k, (cap, what) in LIMITS.items():
        if k not in found:
            continue
        mark = "✗" if found[k] > cap else "✓"
        print(f"  {mark} {found[k]:>3} {what} (limit {cap})")
        if k == "cut_titles" and found[k] > cap:
            for t in cut_titles(open(PAGE, encoding="utf-8").read())[:5]:
                print(f"        …{t}")
    bad = over(found)
    if "--measure" in sys.argv:
        got = measure()
        if got is None:
            print("  · page lengths skipped: no node or playwright-core here")
        else:
            for v, cap in SCREENS.items():
                n = got.get(v, 0)
                mark = "✗" if n > cap else "✓"
                print(f"  {mark} {n:4.1f} screens on {v} (limit {cap})")
                if n > cap:
                    bad.append(f"{v} runs {n:.1f} screens, limit {cap}")
    if bad:
        print("over budget: " + "; ".join(bad))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

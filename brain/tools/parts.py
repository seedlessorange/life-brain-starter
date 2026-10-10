"""The parts of the brain a person can switch off.

Her ask (8 Oct 2026): news, a kitchen, people, routines and the rest are a
lot for someone who only wants a few of them. Each part here has a switch
under the gear. Off hides the part on every page and stops the work the
brain does for it on its own (the morning fetch, the night scout, the chat
syncs). Its files stay where they are, so switching it back on brings
everything back as it was.

Config `parts` holds only what is off: {"news": false}. A part missing from
it is on, so a brain that has never heard of this keeps every part. The job
hunt keeps its own switch, `jobs.on` (jobs.py), which starts off; this
module reads and writes it so the page has one list of switches.

    python3 brain/tools/parts.py              which parts are on
    python3 brain/tools/parts.py off news     switch one off (or on)
    python3 brain/tools/parts.py is-on news   exit 0 when on, 1 when off

A Claude run reads the first form before it plans: a part that is off is
not loaded, planned around or mentioned.
"""

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BRAIN = os.path.dirname(HERE)
CONFIG = os.path.join(BRAIN, "config.json")

# id, name, the one faint line on its switch. Order is the page's order.
PARTS = (
    ("people", "People", "Who you keep in touch with, and owed replies"),
    ("habits", "Habits", "The daily ticks"),
    ("routines", "Routines", "Skincare, training and the like"),
    ("kitchen", "Kitchen", "Dinners and the shopping list"),
    ("season", "Season", "Plans for this stretch, and events nearby"),
    ("learning", "Learning", "Topics Claude teaches you"),
    ("journal", "Journal", "Your private daily entries"),
    ("news", "News", "A morning briefing from feeds you choose"),
    ("jobs", "Job hunt", "Roles and applications"),
)
NAMES = {p: n for p, n, _ in PARTS}

# The parts that make up Life. With all of them off, Life leaves the bar.
LIFE = ("habits", "routines", "kitchen", "season", "learning", "journal")


def load():
    try:
        with open(CONFIG, encoding="utf-8") as f:
            return json.load(f) or {}
    except (OSError, ValueError):
        return {}


def on(part, cfg=None):
    """Whether a part is on. A part this module does not know, or a config
    it cannot read, counts as on: a config problem never hides anything."""
    try:
        c = load() if cfg is None else (cfg or {})
        if part.startswith("plan:"):        # a morning plan source (plan_sources.py)
            import plan_sources
            return plan_sources.on(part[5:], c)
        if part == "jobs":
            return bool((c.get("jobs") or {}).get("on"))
        return (c.get("parts") or {}).get(part, True) is not False
    except Exception:                                       # noqa: BLE001
        return True


def off(cfg=None):
    """The parts switched off, in the page's order."""
    c = load() if cfg is None else cfg
    return [p for p, _, _ in PARTS if not on(p, c)]


def life_on(cfg=None):
    c = load() if cfg is None else cfg
    return any(on(p, c) for p in LIFE)


def setting(cfg, part, value):
    """The config key and its new value for switching `part` on or off:
    ("parts", {...}) or ("jobs", {...}). Pure, so the server and the
    command line write it their own way."""
    if part.startswith("plan:"):
        # The morning plan's sources share these switches' endpoint and
        # button (8 Oct); their own rules live in plan_sources.py.
        import plan_sources
        return plan_sources.setting(cfg, part[5:], value)
    if part not in NAMES:
        raise ValueError("there is no part called %r" % part)
    if part == "jobs":
        return "jobs", dict(cfg.get("jobs") or {}, on=bool(value))
    p = dict(cfg.get("parts") or {})
    if value:
        p.pop(part, None)
    else:
        p[part] = False
    return "parts", p


def set_on(part, value):
    """Switch a part on or off in config.json (the command line's way)."""
    cfg = load()
    key, val = setting(cfg, part, value)
    cfg[key] = val
    tmp = CONFIG + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(json.dumps(cfg, indent=2) + "\n")     # as serve.py writes it
    os.replace(tmp, CONFIG)


def summary(cfg=None):
    c = load() if cfg is None else cfg
    gone = off(c)
    if not gone:
        return "Every part is on."
    return "Off: " + ", ".join(NAMES[p] for p in gone) + "."


def main(argv):
    if not argv:
        print(summary())
        return 0
    cmd = argv[0]
    if cmd in ("-h", "--help"):
        print(__doc__)
        return 0
    if cmd in ("on", "off", "is-on") and len(argv) == 2:
        part = argv[1]
        if part not in NAMES:
            print("No part called %r. Parts: %s" % (part, ", ".join(NAMES)))
            return 2
        if cmd == "is-on":
            return 0 if on(part) else 1
        set_on(part, cmd == "on")
        print("%s is %s. Rebuild the page: python3 brain/tools/rebuild.py"
              % (NAMES[part], cmd))
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

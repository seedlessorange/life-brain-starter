#!/usr/bin/env python3
"""Privacy and safety settings: what runs nobody is watching may open, what
may send, and what may leave this Mac, in three levels and a switch each
(PRIVACY-PLAN.md, her ask of 8 Oct 2026).

    python3 brain/tools/privacy.py        # the settings in force, plainly
    python3 brain/tools/privacy.py --json

Kept in brain/tools/.run-policy/privacy.json, the folder no Claude run can
write, attended or not. The Usage page's switches live in config.json, which
runs can write; that is harmless for spend and wrong here, because a run that
read a hostile page could loosen what the next run may read. Only the server
writes this file: one tap to tighten, her Touch ID to loosen (serve.py,
/api/privacy/*), and the security alarm watches it (sentinel.py).

Three rules hold everywhere this is read:

* **It only subtracts.** A switch can stop something that is set up; it
  never starts something that isn't. Mail reading still needs mail
  connected, a push still needs config's `git_push`.
* **No file means Everyday**, so an upgrade changes nothing. **An unreadable
  file means Locked**, and the page says so: it fails closed, visibly.
* **The floor is not here.** Personal circles, drafts made from other
  people's words, the sandbox, the confidential-name guard and the journal
  lock live in their own code. No key in this file reaches them, which is
  why the journal is in private_paths() whatever the level.

"Nobody watching" means a run started by a timer: the 7am plan, the night
shift and the recordings pass. A run she starts from a button, the box,
Telegram or a conversation is watched: she asked for it.
"""

import json
import os
import sys
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
BRAIN = os.path.dirname(HERE)
ROOT = os.path.dirname(BRAIN)
FILE = os.path.join(HERE, ".run-policy", "privacy.json")
DIGEST = os.path.join(BRAIN, ".people-digest.md")

LEVELS = ("everyday", "guarded", "locked")          # loosest first
NAMES = {"everyday": "Everyday", "guarded": "Guarded", "locked": "Locked"}

# Every switch a level sets: its values from loosest to strictest, then the
# value each level gives it. One table, read by the server, the pages and
# every tool that gates itself, so none of them can disagree.
SWITCHES = {
    # What runs nobody is watching can't open, beyond the journal.
    "lock_transcripts": ((False, True),
                         {"everyday": False, "guarded": True, "locked": True}),
    "lock_money": ((False, True),
                   {"everyday": False, "guarded": True, "locked": True}),
    "lock_people": ((False, True),
                    {"everyday": False, "guarded": False, "locked": True}),
    # Sending. "on" is email as she set it up (her fingerprint when the mail
    # password sits behind Touch ID); "touch" asks for it on every send.
    "send_email": (("on", "touch", "off"),
                   {"everyday": "on", "guarded": "touch", "locked": "off"}),
    "send_chat": (("click", "touch", "off"),
                  {"everyday": "click", "guarded": "touch", "locked": "off"}),
    # Mail: who wrote (headers only), and task mail (bodies, whitelist).
    "mail_check": ((True, False),
                   {"everyday": True, "guarded": True, "locked": False}),
    "mail_tasks": ((True, False),
                   {"everyday": True, "guarded": False, "locked": False}),
    # Telegram: everything, or capture into the inbox only.
    "telegram": (("full", "capture"),
                 {"everyday": "full", "guarded": "full", "locked": "capture"}),
    # The reading fence (phase 4): where on the disk a run may read. Runs she
    # starts, and runs on a timer. "named" is the brain plus the folders she
    # approved (`folders` in the settings file, never config's sources); a
    # run in an app repo reads only that repo at either fenced value.
    # Everyday stays "anywhere" until she decides, after the deep dive.
    "reach": (("anywhere", "named", "brain"),
              {"everyday": "anywhere", "guarded": "named", "locked": "brain"}),
    "reach_timer": (("anywhere", "named", "brain"),
                    {"everyday": "anywhere", "guarded": "brain", "locked": "brain"}),
}

# Set on their own: no level touches them, because each trades something
# other than convenience. Values loosest first, then the default.
STANDALONE = {
    # The off-site copy on GitHub. Off: local git only.
    "backup": ((True, False), True),
    # The small jobs (Pen, draft rewording, conversation names, task
    # wording, news breakdowns, the voice): Claude; this Mac first, falling
    # back to Claude; or this Mac only, which refuses rather than fall back.
    "small_jobs": (("claude", "local_first", "local_only"), "claude"),
}

# What each lock keeps from runs nobody is watching. The journal is the
# floor: in the list at every level, and no switch here unlocks it.
FLOOR_PATHS = ["brain/journal/"]
LOCK_PATHS = {
    "lock_transcripts": ["brain/transcripts/"],
    "lock_money": ["brain/finance/"],
    "lock_people": ["brain/people.md"],
}


def _order(key):
    return (SWITCHES.get(key) or STANDALONE.get(key))[0]


def valid(key, value):
    return (key in SWITCHES or key in STANDALONE) and value in _order(key) \
        and type(value) is type(_order(key)[0])


def _read():
    """(stored dict, problem). problem is None, "missing" or "unreadable"."""
    try:
        with open(FILE, encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        return {}, "missing"
    except (OSError, ValueError):
        return {}, "unreadable"
    if not isinstance(data, dict) or data.get("level") not in LEVELS:
        return {}, "unreadable"
    return data, None


def level_values(level):
    return {k: col[level] for k, (_, col) in SWITCHES.items()}


def effective():
    """The settings in force: the level's column, her overrides on top, the
    standalone switches, and which level they match (or "custom")."""
    data, problem = _read()
    level = "locked" if problem == "unreadable" else data.get("level", "everyday")
    values = level_values(level)
    ov = {}
    for k, v in (data.get("overrides") or {}).items():
        if k in SWITCHES and valid(k, v):
            values[k] = ov[k] = v
    for k, (order, default) in STANDALONE.items():
        v = (data.get("standalone") or {}).get(k)
        values[k] = v if valid(k, v) else default
    match = next((lv for lv in (level,) + LEVELS
                  if level_values(lv) == {k: values[k] for k in SWITCHES}),
                 "custom")
    return {"level": level, "name": NAMES[level], "values": values,
            "overrides": ov, "match": match,
            "broken": problem == "unreadable",
            "set_at": data.get("set_at", ""), "via": data.get("via", "")}


def value(key):
    return effective()["values"][key]


def locked(kind):
    """Whether runs nobody is watching are kept from `kind`: transcripts,
    money or people. (The journal always is.)"""
    return bool(value("lock_" + kind))


def private_paths():
    """Every path runs nobody is watching may not open: the journal, what
    the level locks, and anything hand-added to config's `private` list.
    Config can only ADD here: it is writable by runs, so an entry there
    never removes a lock, and an empty list no longer opens the journal."""
    vals = effective()["values"]
    paths = list(FLOOR_PATHS)
    for key, ps in LOCK_PATHS.items():
        if vals[key]:
            paths += ps
    try:
        with open(os.path.join(BRAIN, "config.json"), encoding="utf-8") as f:
            extra = json.load(f).get("private") or []
    except (OSError, ValueError, AttributeError):
        extra = []
    paths += [str(p) for p in extra if isinstance(p, str) and p.strip()]
    return list(dict.fromkeys(paths))


# Presenting mode (phase 6): while she shares her screen, the pages are
# rebuilt without the private parts. These areas' workstreams and tasks are
# left out along with the journal, people, money and draft text; she can
# change the list on the Privacy page. One tap either way: the risk is the
# people in the room, not a run, so turning it off needs no fingerprint.
PRESENT_AREAS = ["Personal", "Dad", "Family", "Health"]


def presenting():
    """None, or {"since", "areas"} while presenting mode is on."""
    data, problem = _read()
    p = data.get("presenting") or {}
    if not p.get("on"):
        return None
    areas = [a for a in (p.get("areas") or PRESENT_AREAS) if isinstance(a, str)]
    return {"since": p.get("since", ""), "areas": areas}


def present_names(people):
    """The names (and Also: names) of everyone in a personal circle: family,
    friends, dating. While presenting, nothing naming them is shown."""
    out = set()
    for p in people or []:
        if p.get("personal", True):
            for n in [p.get("name") or ""] + list(p.get("also") or []):
                if len(n.strip()) >= 3:
                    out.add(n.strip())
    return out


def present_filter(ws, people, areas):
    """What presenting leaves of the workstreams: (kept, hidden task keys,
    the names pattern). Gone: the hidden areas' workstreams, any workstream
    or task whose title names someone in a personal circle, every note, and
    any field (Why, Next...) that names one. Hiding a little too much is the
    right mistake on a shared screen. One function for index, map and rooms,
    so the three pages cannot disagree."""
    import re
    sys.path.insert(0, HERE)
    import md as MD
    names = present_names(people)
    rx = (re.compile(r"\b(?:" + "|".join(re.escape(n) for n in
                                         sorted(names, key=len, reverse=True))
                     + r")\b") if names else None)
    hit = (lambda s: bool(rx and isinstance(s, str) and rx.search(s)))
    hide = {a.strip().lower() for a in areas}
    kept, keys = [], set()
    for w in ws:
        tasks = w.get("tasks") or []
        if (w.get("area") or "").strip().lower() in hide or hit(w.get("name")):
            keys |= {MD.taskkey(MD.bare(t["text"])) for t in tasks}
            continue
        keep_t = []
        for t in tasks:
            if hit(t.get("text")):
                keys.add(MD.taskkey(MD.bare(t["text"])))
            else:
                t["notes"] = []
                keep_t.append(t)
        w["tasks"] = keep_t
        w["notes"] = []
        for k, v in list((w.get("fields") or {}).items()):
            if hit(v):
                w["fields"][k] = ""
        for k, v in list(w.items()):
            if k not in ("name", "area", "status") and hit(v):
                w[k] = ""
        kept.append(w)
    return kept, keys, rx


def reach_folders():
    """The folders she let runs read, from the settings file. Never from
    config's sources, which runs can write: a run must not be able to add a
    folder (or the whole home folder) to its own fence. None approved yet
    means none, so a fenced run reads the brain only."""
    data, _ = _read()
    out = []
    for p in data.get("folders") or []:
        if isinstance(p, str) and p.strip():
            ap = os.path.realpath(os.path.expanduser(p.strip()))
            home = os.path.realpath(os.path.expanduser("~"))
            if ap != home and not home.startswith(ap + os.sep) and ap != "/":
                out.append(ap)
    return list(dict.fromkeys(out))


def loosens(before, after):
    """The keys whose value moves toward the loose end."""
    out = []
    for k in list(SWITCHES) + list(STANDALONE):
        o = _order(k)
        if o.index(after[k]) < o.index(before[k]):
            out.append(k)
    return out


def plan(level=None, key=None, val=None, folders=None, ticks=None,
         present=None):
    """What a change would store, and what it would be: (new stored dict,
    the values it gives, what it loosens). A level clears the overrides,
    like the Usage page's recommended shapes; the standalone switches, the
    approved folders and the Mac check's ticks keep theirs. Adding a folder
    runs may read loosens; removing one tightens."""
    data, problem = _read()
    cur = effective()
    new = {"level": cur["level"], "overrides": dict(cur["overrides"]),
           "standalone": {k: cur["values"][k] for k in STANDALONE},
           "folders": reach_folders(),
           "ticks": dict(data.get("ticks") or {}),
           "presenting": dict(data.get("presenting") or {})}
    if problem == "unreadable":
        new["overrides"] = {}
    if level is not None:
        if level not in LEVELS:
            raise ValueError("the level must be Everyday, Guarded or Locked")
        new["level"], new["overrides"] = level, {}
    if key is not None:
        if not valid(key, val):
            raise ValueError("that is not a setting this switch has")
        if key in STANDALONE:
            new["standalone"][key] = val
        elif val == SWITCHES[key][1][new["level"]]:
            new["overrides"].pop(key, None)       # back to the level's own
        else:
            new["overrides"][key] = val
    loose_folders = []
    if folders is not None:
        clean = []
        home = os.path.realpath(os.path.expanduser("~"))
        for p in folders:
            ap = os.path.realpath(os.path.expanduser(str(p).strip()))
            if not os.path.isdir(ap):
                raise ValueError("that folder doesn't exist: " + str(p))
            if ap in ("/", home) or home.startswith(ap + os.sep):
                raise ValueError("a whole home folder can't be a reading folder")
            clean.append(ap)
        clean = list(dict.fromkeys(clean))
        loose_folders = [p for p in clean if p not in new["folders"]]
        new["folders"] = clean
    if ticks is not None:
        new["ticks"] = {str(k)[:40]: str(v)[:20] for k, v in ticks.items()}
    if present is not None:
        p = dict(new["presenting"])
        if "on" in present:
            p["on"] = bool(present["on"])
            p["since"] = (datetime.now().isoformat(timespec="minutes")
                          if p["on"] else "")
        if isinstance(present.get("areas"), list):
            p["areas"] = [str(a)[:60] for a in present["areas"]][:20]
        new["presenting"] = p
    vals = level_values(new["level"])
    vals.update(new["overrides"])
    vals.update(new["standalone"])
    loose = loosens(cur["values"], vals)
    if loose_folders:
        loose.append("folders")
    return new, vals, loose


def save(new, via):
    """Write the settings. Only the server calls this, after its checks."""
    os.makedirs(os.path.dirname(FILE), exist_ok=True)
    new = dict(new, set_at=datetime.now().isoformat(timespec="seconds"), via=via)
    tmp = FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(new, f, indent=1)
    os.replace(tmp, FILE)
    return effective()


def small_jobs():
    """claude, local_first or local_only. Unreadable settings count as
    local_only, as everything else fails closed."""
    try:
        return value("small_jobs")
    except Exception:
        return "local_only"


def confirm(reason):
    """Her fingerprint, through brainconfirm: True only when she touched.
    A Claude session can press a button; it cannot produce her Touch ID.
    Off a Mac there is no fingerprint, so this passes and the page's own
    confirm step is all there is (the Privacy page says so)."""
    if sys.platform != "darwin":
        return True
    exe = os.path.join(HERE, ".bin", "brainconfirm")
    if not os.access(exe, os.X_OK):
        raise ValueError("brainconfirm isn't built: "
                         "zsh brain/tools/make_brainmail.sh brainconfirm")
    import subprocess
    r = subprocess.run([exe, reason], capture_output=True, timeout=180)
    return r.returncode == 0


def fingerprint():
    """What the security alarm compares: the settings in force, so a hand
    edit that didn't come through the page shows up as a change."""
    e = effective()
    keys = sorted(e["values"])
    return (e["level"] + ":" + ",".join(f"{k}={e['values'][k]}" for k in keys)
            + "|folders=" + ",".join(sorted(reach_folders())))


def write_digest():
    """Before people.md is locked for a run nobody is watching: the short
    list that run may read instead (who is owed a reply, who has gone quiet,
    birthdays), made by plain code. Names, dates and flags; no notes."""
    import subprocess
    try:
        r = subprocess.run([sys.executable, os.path.join(HERE, "model.py"),
                            "--people"], capture_output=True, text=True,
                           timeout=60, cwd=ROOT)
        text = r.stdout.strip() if r.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        text = ""
    if not text:
        drop_digest()           # never leave an older list looking current
        return None
    with open(DIGEST, "w", encoding="utf-8") as f:
        f.write("# Who needs her: the short list for a run nobody is watching\n\n"
                "people.md is locked at this privacy level. This is model.py's "
                "flagged list, made before the lock. Changes to people.md wait "
                "for a run she starts.\n\n" + text + "\n")
    return DIGEST


def drop_digest():
    try:
        os.remove(DIGEST)
    except OSError:
        pass


PLAIN = {
    "lock_transcripts": ("Transcripts in runs on a timer", {False: "open", True: "locked"}),
    "lock_money": ("Money files in runs on a timer", {False: "open", True: "locked"}),
    "lock_people": ("Notes on people in runs on a timer", {False: "open", True: "locked (short list only)"}),
    "send_email": ("Sending email", {"on": "as set up", "touch": "fingerprint each time", "off": "off"}),
    "send_chat": ("Sending chat messages", {"click": "on your click", "touch": "fingerprint each time", "off": "off"}),
    "mail_check": ("Mail check", {True: "on your click", False: "off"}),
    "mail_tasks": ("Task mail", {True: "on your click", False: "off"}),
    "telegram": ("Telegram", {"full": "answers and pushes", "capture": "capture only"}),
    "reach": ("What runs you start may read", {"anywhere": "most of the disk", "named": "the brain and your folders", "brain": "the brain only"}),
    "reach_timer": ("What runs on a timer may read", {"anywhere": "most of the disk", "named": "the brain and your folders", "brain": "the brain only"}),
    "backup": ("Backup to GitHub", {True: "allowed", False: "off"}),
    "small_jobs": ("Small jobs", {"claude": "Claude", "local_first": "this Mac first",
                                  "local_only": "this Mac only"}),
}
# What a loosened folder list is called in her fingerprint prompt.
PLAIN_EXTRA = {"folders": "the folders runs may read"}


def main(argv):
    if "--presenting" in argv:          # for shell scripts: exit 0 while on
        return 0 if presenting() else 1
    e = effective()
    if "--json" in argv:
        print(json.dumps(dict(e, private=private_paths()), indent=1))
        return 0
    head = e["name"] if e["match"] == e["level"] else e["name"] + ", with your own changes"
    print("Privacy: " + head + (" (the settings file is unreadable, so Locked)"
                                if e["broken"] else ""))
    for k, (label, says) in PLAIN.items():
        print(f"  {label}: {says[e['values'][k]]}")
    print("  Runs on a timer can't open: " + ", ".join(private_paths()))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

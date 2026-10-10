#!/usr/bin/env python3
"""The Mac check: what sits outside the brain's code, checked on her click.

    python3 brain/tools/mac_check.py          # run every check, print it
    python3 brain/tools/mac_check.py --json

Plain code, no model: sending her setup to a model to check her privacy
would be the wrong way round. The items come from the security reference's
open list (brain/reference/security.md), which was prose that went stale.
Each check answers ok, warn or info with one line of what to do, and never
prints a secret: a key in Claude's allow rules is counted, never shown.

Two network reads, both on her click only: npm's registry for the latest
Claude Code version, and GitHub's public API without a login (a private repo
answers 404 there, which is the point). The result is cached in
brain/.mac-check.json for the Privacy page.

Her own Claude Code sessions are not judged here: she chose, 8 Oct, to
leave them as they are (decisions.md).
"""

import json
import os
import re
import stat
import subprocess
import sys
import urllib.request
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
BRAIN = os.path.dirname(HERE)
ROOT = os.path.dirname(BRAIN)
CACHE = os.path.join(BRAIN, ".mac-check.json")


def _run(cmd, timeout=15):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return (r.stdout + r.stderr).strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def _get(url, timeout=6):
    """(status, body) for a plain GET, or (0, "") offline."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "life-brain-mac-check"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read(200_000).decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, ""
    except Exception:
        return 0, ""


def filevault():
    out = _run(["fdesetup", "status"])
    if "is On" in out:
        return "ok", "FileVault is on: the disk is encrypted when the Mac is off."
    if not out:
        return "info", "FileVault could not be read here."
    return "warn", ("FileVault is off. Turn it on in System Settings, Privacy & "
                    "Security, FileVault.")


def firewall():
    out = _run(["/usr/libexec/ApplicationFirewall/socketfilterfw", "--getglobalstate"])
    if "enabled" in out.lower() and "disabled" not in out.lower():
        return "ok", "The Mac's firewall is on."
    if not out:
        return "info", "The firewall's state could not be read here."
    return "warn", ("The Mac's firewall is off. With the brain's server on this "
                    "Mac and your own devices it matters little; turning it on "
                    "in System Settings, Network, Firewall closes the rest.")


def _ver(s):
    m = re.search(r"(\d+)\.(\d+)\.(\d+)", s or "")
    return tuple(int(x) for x in m.groups()) if m else None


def claude_version():
    have = _ver(_run(["claude", "--version"]))
    if not have:
        return "info", "Claude Code's version could not be read."
    st, body = _get("https://registry.npmjs.org/@anthropic-ai/claude-code/latest")
    latest = None
    if st == 200:
        try:
            latest = _ver(json.loads(body).get("version"))
        except ValueError:
            latest = None
    shown = ".".join(map(str, have))
    if latest and latest > have:
        return "warn", (f"Claude Code is {shown}; {'.'.join(map(str, latest))} is "
                        "out. Updating changes how the sandbox reads its rules, so "
                        "rerun the fence probes on the new version first "
                        "(brain/reference/privacy.md).")
    if latest:
        return "ok", f"Claude Code is {shown}, the latest."
    return "info", f"Claude Code is {shown}; the latest version could not be read."


# A key pasted into a command Claude was allowed to run once stays in the
# allow rule forever. The name before the value is shown; the value never is.
SECRETISH = [
    re.compile(r"([A-Za-z0-9_.-]*(?:key|token|secret|password))[\"']?\s*[:=]\s*"
               r"[\"']?([A-Za-z0-9/+_.-]{16,})", re.I),
    re.compile(r"()(sk[-_](?:live|test|ant|proj)[-_][A-Za-z0-9]{16,})"),
    re.compile(r"()(eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,})"),
]


def keys_in_allow_rules():
    import hashlib
    path = os.path.expanduser("~/.claude/settings.json")
    try:
        with open(path, encoding="utf-8") as f:
            rules = (json.load(f).get("permissions") or {}).get("allow") or []
    except (OSError, ValueError):
        return "info", "Claude's own settings could not be read."
    # The local files too: "always allow" from a prompt lands there as often
    # (9 Oct audit; none held a key that day).
    for extra in (os.path.expanduser("~/.claude/settings.local.json"),
                  os.path.join(ROOT, ".claude", "settings.json"),
                  os.path.join(ROOT, ".claude", "settings.local.json")):
        try:
            with open(extra, encoding="utf-8") as f:
                rules = rules + list((json.load(f).get("permissions") or {})
                                     .get("allow") or [])
        except (OSError, ValueError, AttributeError):
            pass
    names, values, n_rules = {}, set(), 0
    for r in rules:
        if not isinstance(r, str):
            continue
        hit = False
        for rx in SECRETISH:
            for m in rx.finditer(r):
                hit = True
                values.add(hashlib.sha256(m.group(2).encode()).hexdigest())
                if m.group(1):
                    names[m.group(1)[-32:]] = names.get(m.group(1)[-32:], 0) + 1
        n_rules += hit
    if not values:
        return "ok", "No allow rule in Claude's settings looks like it holds a key."
    named = ", ".join(sorted(names, key=lambda k: -names[k])[:4])
    return "warn", (f"{len(values)} different keys sit in {n_rules} of Claude's allow "
                    f"rules{' (' + named + ')' if named else ''}: each was pasted "
                    "into a command once and kept. Rotate them where they were "
                    "issued, then delete those rules.")


def github_private():
    url = _run(["git", "-C", ROOT, "remote", "get-url", "origin"])
    m = re.search(r"github\.com[:/]([^/\s]+)/([^/\s]+?)(?:\.git)?$", url)
    if not m:
        return "info", "This brain has no GitHub copy."
    st, _ = _get(f"https://api.github.com/repos/{m.group(1)}/{m.group(2)}")
    if st == 404:
        return "ok", "The brain's GitHub copy is private: GitHub won't show it to anyone signed out."
    if st == 200:
        return "warn", ("The brain's GitHub copy is PUBLIC. Make it private in the "
                        "repo's settings on GitHub, today.")
    return "info", "GitHub could not be reached to check the copy is private."


def mail_touch_id():
    try:
        with open(os.path.join(BRAIN, "config.json"), encoding="utf-8") as f:
            cfg = json.load(f)
    except (OSError, ValueError):
        cfg = {}
    if not (cfg.get("email") or {}).get("accounts"):
        return "info", "No mail account is connected."
    if (cfg.get("email") or {}).get("touch_id"):
        return "ok", "The mail password opens only with your fingerprint."
    return "warn", ("The mail password opens without your fingerprint. Turn on "
                    "Touch ID for it in Connections.")


def telegram_token():
    p = os.path.join(BRAIN, ".telegram.json")
    if not os.path.exists(p):
        return "info", "Telegram is not connected."
    mode = stat.S_IMODE(os.stat(p).st_mode)
    if mode & 0o077:
        return "warn", "The Telegram key file can be read by other accounts on this Mac."
    return "ok", "The Telegram key file is readable by you alone."


# Facts no code can read: a reminder until she ticks it.
REMINDERS = {
    "github_2fa": "Two-step sign-in is on for your GitHub account "
                  "(github.com, Settings, Password and authentication).",
    "connectors": "Gmail, Drive and Calendar stay unconnected in claude.ai's "
                  "connectors, so no Claude chat or run gets your mailbox.",
}

CHECKS = [
    ("filevault", "Disk encryption", filevault),
    ("firewall", "Firewall", firewall),
    ("claude", "Claude Code", claude_version),
    ("keys", "Keys in Claude's settings", keys_in_allow_rules),
    ("github", "GitHub copy", github_private),
    ("mail", "Mail password", mail_touch_id),
    ("telegram", "Telegram key", telegram_token),
]


def run():
    items = []
    for cid, label, fn in CHECKS:
        try:
            state, line = fn()
        except Exception as exc:                # one broken check never sinks the rest
            state, line = "info", f"Could not check: {type(exc).__name__}"
        items.append({"id": cid, "label": label, "state": state, "line": line})
    out = {"at": datetime.now().isoformat(timespec="seconds"), "items": items}
    try:
        with open(CACHE, "w", encoding="utf-8") as f:
            json.dump(out, f, indent=1)
    except OSError:
        pass
    return out


def cached():
    try:
        with open(CACHE, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def main(argv):
    r = run()
    if "--json" in argv:
        print(json.dumps(r, indent=1))
        return 0
    for it in r["items"]:
        print(f"[{it['state']:>4}] {it['label']}: {it['line']}")
    for k, line in REMINDERS.items():
        print(f"[tick] {line}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

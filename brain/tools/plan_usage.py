#!/usr/bin/env python3
"""Where she stands on her Claude plan: the weekly and five-hour meters.

    python3 brain/tools/plan_usage.py          # prints the percentages

Claude Code shows this inside /usage and nowhere else; the brain's own
ledger (usage.py) only counts the brain's runs. This asks Anthropic the same
question Claude Code asks, with the login Claude Code already keeps in the
Keychain, and only reads:

- The token is read for the one request, sent only to api.anthropic.com
  (pinned here, not configurable), and never written to a file, a log or
  the page.
- It never refreshes the login. When the token has expired, the answer is
  the last one saved, with its age; Claude Code renews its own login the
  next time it runs.
- Only the percentages and reset times are kept, in brain/.plan-usage.json.
"""
import json
import os
import subprocess
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
BRAIN = os.path.dirname(HERE)
CACHE = os.path.join(BRAIN, ".plan-usage.json")
URL = "https://api.anthropic.com/api/oauth/usage"
KEYCHAIN_ITEM = "Claude Code-credentials"
TTL = 300                        # ask Anthropic at most every five minutes


def _token():
    """(token, why-not). The Keychain item holds Claude Code's own login."""
    try:
        r = subprocess.run(["security", "find-generic-password", "-s",
                            KEYCHAIN_ITEM, "-w"], capture_output=True,
                           text=True, timeout=10)
    except Exception:
        return None, "no Keychain"
    if r.returncode != 0 or not r.stdout.strip():
        return None, "Claude Code is not signed in on this Mac"
    try:
        o = (json.loads(r.stdout) or {}).get("claudeAiOauth") or {}
    except ValueError:
        return None, "the login could not be read"
    tok, exp = o.get("accessToken"), o.get("expiresAt")
    if not tok:
        return None, "Claude Code is not signed in on this Mac"
    try:
        if exp and float(exp) / 1000 < time.time():
            return None, "the login has expired until Claude Code next runs"
    except (TypeError, ValueError):
        pass
    return tok, ""


def _meter(d):
    if not isinstance(d, dict) or d.get("utilization") is None:
        return None
    try:
        pct = float(d.get("utilization"))
    except (TypeError, ValueError):
        return None
    return {"pct": round(pct, 1), "resets": d.get("resets_at") or ""}


def _load():
    try:
        with open(CACHE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _save(obj):
    tmp = CACHE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f)
    os.replace(tmp, CACHE)


def status(force=False):
    """{"at", "week", "five_hour", "week_opus", "week_sonnet", "fresh", "why"}
    where each meter is {"pct", "resets"} or None."""
    cached = _load()
    if not force and cached and time.time() - float(cached.get("at") or 0) < TTL:
        return dict(cached, fresh=True, why="")
    tok, why = _token()
    data = None
    if tok:
        req = urllib.request.Request(URL, headers={
            "Authorization": "Bearer " + tok,
            "anthropic-beta": "oauth-2025-04-20",
            "Content-Type": "application/json",
            "User-Agent": "life-brain"})
        tok = None
        try:
            with urllib.request.urlopen(req, timeout=8) as r:
                data = json.load(r)
        except Exception as exc:                        # noqa: BLE001
            why = "Anthropic did not answer" + (
                f" ({exc.code})" if hasattr(exc, "code") else "")
    if isinstance(data, dict):
        out = {"at": time.time(),
               "week": _meter(data.get("seven_day")),
               "five_hour": _meter(data.get("five_hour")),
               "week_opus": _meter(data.get("seven_day_opus")),
               "week_sonnet": _meter(data.get("seven_day_sonnet"))}
        try:
            _save(out)
        except OSError:
            pass
        return dict(out, fresh=True, why="")
    if cached:
        return dict(cached, fresh=False, why=why)
    return {"at": 0, "week": None, "five_hour": None, "fresh": False,
            "why": why}


if __name__ == "__main__":
    s = status(force=True)
    for k in ("five_hour", "week", "week_sonnet", "week_opus"):
        m = s.get(k)
        if m:
            print(f"{k:12} {m['pct']:5.1f}%   resets {m['resets']}")
    if s.get("why"):
        print("note:", s["why"])

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
- Only the percentages and reset times are kept, in brain/.plan-usage.json,
  and each fresh reading as one line of brain/.plan-history.jsonl (a week of
  them), so a run can be measured as the change in the week across it.
"""
import json
import os
import subprocess
import time
import urllib.request
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
BRAIN = os.path.dirname(HERE)
CACHE = os.path.join(BRAIN, ".plan-usage.json")
URL = "https://api.anthropic.com/api/oauth/usage"
KEYCHAIN_ITEM = "Claude Code-credentials"
TTL = 300                        # ask Anthropic at most every five minutes
HISTORY = os.path.join(BRAIN, ".plan-history.jsonl")
KEEP_SECS = 8 * 86400            # a week of readings, and a day of slack
# How old a reading may be and still decide anything: a run limit acting on
# an hour-old five-hour figure would be acting on a different window.
USABLE_SECS = 30 * 60


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


def _remember(out):
    """One line per fresh reading. A week is about 2,000 lines; the file is
    cut back to that whenever it grows past twice the size."""
    line = json.dumps({"at": round(out["at"]),
                       "w": (out.get("week") or {}).get("pct"),
                       "wr": (out.get("week") or {}).get("resets") or "",
                       "h": (out.get("five_hour") or {}).get("pct"),
                       "hr": (out.get("five_hour") or {}).get("resets") or ""})
    with open(HISTORY, "a", encoding="utf-8") as f:
        f.write(line + "\n")
    if os.path.getsize(HISTORY) > 400_000:
        keep = [r for r in history() if r["at"] > time.time() - KEEP_SECS]
        tmp = HISTORY + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write("".join(json.dumps(r) + "\n" for r in keep))
        os.replace(tmp, HISTORY)


def history():
    """Every saved reading, oldest first. A torn line is skipped."""
    rows = []
    try:
        with open(HISTORY, encoding="utf-8") as f:
            for line in f:
                try:
                    r = json.loads(line)
                except ValueError:
                    continue
                if isinstance(r, dict) and r.get("at"):
                    rows.append(r)
    except OSError:
        pass
    return rows


def _ts(iso):
    try:
        d = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
        return (d if d.tzinfo else d.replace(tzinfo=timezone.utc)).timestamp()
    except ValueError:
        return None


def same_window(a, b):
    """Two readings' reset times name the same window. Anthropic's reset
    time wobbles by a second between answers, so equal means within ten
    minutes."""
    ta, tb = _ts(a), _ts(b)
    return ta is not None and tb is not None and abs(ta - tb) < 600


def reading_before(start, slack=600):
    """The last saved reading taken at most `slack` seconds before `start`
    (and no later than a few seconds after it, as the run's own first call
    has not landed by then), or None."""
    best = None
    for r in history():
        if start - slack <= r["at"] <= start + 5:
            best = r
    return best


def current(s=None, max_age=USABLE_SECS):
    """{"week": pct, "five_hour": pct, "week_resets": iso, "five_hour_resets":
    iso} from a reading young enough to act on, or None. A meter whose reset
    time has passed counts as 0: that window has rolled over since."""
    if s is None:
        s = status()
    if not s or not s.get("at") or time.time() - float(s["at"]) > max_age:
        return None
    out = {}
    for k in ("week", "five_hour"):
        m = s.get(k)
        if not m:
            out[k] = None
            continue
        t = _ts(m.get("resets"))
        out[k] = 0.0 if t is not None and t < time.time() else m["pct"]
        out[k + "_resets"] = m.get("resets") or ""
    if out.get("week") is None and out.get("five_hour") is None:
        return None
    return out


def status(force=False, timeout=8):
    """{"at", "week", "five_hour", "week_opus", "week_sonnet", "fresh", "why"}
    where each meter is {"pct", "resets"} or None. "off" is set when the
    brain runs Codex or Gemini: their plans have no reading here, and a
    Claude login on the same Mac would show a plan the brain does not use."""
    import agents
    if agents.provider() != "claude":
        return {"at": 0, "week": None, "five_hour": None, "fresh": False,
                "off": True, "why": f"the brain runs {agents.label()}, "
                "whose plan the brain can't read"}
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
            with urllib.request.urlopen(req, timeout=timeout) as r:
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
            _remember(out)
        except OSError:
            pass
        return dict(out, fresh=True, why="")
    if cached:
        return dict(cached, fresh=False, why=why)
    return {"at": 0, "week": None, "five_hour": None, "fresh": False,
            "why": why}


def note_start():
    """A fresh reading at the moment a run starts, on a thread so the run
    does not wait for Anthropic: usage.record() pairs it with the reading
    taken when the run ends. Never raises."""
    import threading

    def _go():
        try:
            status(force=True)
        except Exception:                               # noqa: BLE001
            pass
    try:
        threading.Thread(target=_go).start()
    except Exception:                                   # noqa: BLE001
        pass


if __name__ == "__main__":
    s = status(force=True)
    for k in ("five_hour", "week", "week_sonnet", "week_opus"):
        m = s.get(k)
        if m:
            print(f"{k:12} {m['pct']:5.1f}%   resets {m['resets']}")
    if s.get("why"):
        print("note:", s["why"])

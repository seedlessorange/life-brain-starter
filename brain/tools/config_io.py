#!/usr/bin/env python3
"""config.json, saved safely by the tools that keep their own settings in it
(jobs, news, mail, the morning plan's sources).

Each of them read it with a {} fallback and wrote it back whole, so one bad
read (a hand edit's typo, a half-written file) left config.json holding one
key, and two taps at once could wipe it (9 Oct audit: 19 of 40 racing news
taps did). The server's own writes have the same guard in serve.write().
"""
import json
import os
import threading


def save(path, cfg):
    """Write cfg to path whole and atomically. Refuses to write over a file
    that can't be read, or to drop most of a readable file's keys."""
    try:
        with open(path, encoding="utf-8") as f:
            have = json.load(f)
    except FileNotFoundError:
        have = {}
    except (OSError, ValueError):
        raise ValueError("config.json can't be read (a typo in it?), so it "
                         "wasn't written over. Fix the file first")
    if isinstance(have, dict) and len(have) >= 6 and isinstance(cfg, dict) \
            and len(set(have) - set(cfg)) > len(have) // 2:
        raise ValueError("that change would have dropped most of config.json, "
                         "so it wasn't saved")
    tmp = "%s.%d.%d.tmp" % (path, os.getpid(), threading.get_ident())
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)
        f.write("\n")
    os.replace(tmp, path)

#!/usr/bin/env python3
"""Rebuild every generated page. The one command for it.

    python3 brain/tools/rebuild.py

The list of pages lives here and nowhere else. It used to be pasted into
fifteen places — the commands, the morning and night jobs, the server, reset,
update — and the copies drifted: most never rebuilt the Routine page, so it
sat stale after every /wrap. A page added to the app is added to PAGES.

Each page is its own process, so one that breaks cannot take the others
down with it. A failure is printed and sets the exit code; the rest still
build. build.py also writes the Cook and Usage pages, so they need no entry.
"""

import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

# The main page first: it is the one she is looking at.
PAGES = ["build.py", "map.py", "rooms.py", "routines.py"]


def run(jobs=None, tools=HERE, timeout=90, on_fail=None):
    """Run each page script; return [(job, message)] for the ones that
    failed. `tools` is the folder to run them from — update.py points it at
    the install it just updated. `on_fail(job, message)` is called as each
    failure happens, for callers that log rather than print."""
    failed = []
    for job in (PAGES if jobs is None else jobs):
        try:
            r = subprocess.run([sys.executable, os.path.join(tools, job)],
                               cwd=os.path.dirname(os.path.dirname(tools)),
                               capture_output=True, text=True, timeout=timeout)
            msg = (f"{job} exited {r.returncode}: " + (r.stderr or "")[-400:]
                   if r.returncode != 0 else "")
        except Exception as exc:
            msg = f"{job} raised {type(exc).__name__}: {exc}"
        if msg:
            failed.append((job, msg))
            if on_fail:
                on_fail(job, msg)
    return failed


def main():
    failed = run()
    for _, msg in failed:
        print(msg, file=sys.stderr)
    built = len(PAGES) - len(failed)
    print(f"Rebuilt {built} of {len(PAGES)} pages."
          + (" Failed: " + ", ".join(j for j, _ in failed) if failed else ""))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

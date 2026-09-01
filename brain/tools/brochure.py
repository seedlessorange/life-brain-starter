#!/usr/bin/env python3
"""Render the one-page brochure to a PNG she can send.

    python3 brain/tools/brochure.py

Source of truth is design/brochure.html — plain HTML, the page's own art and
fonts. This just photographs it: headless Chrome shoots a deliberately
over-tall window, then the trailing paper is trimmed so the image ends where
the page does. Output: dist/life-brain-brochure.png (git-ignored, like the
share zips).

The brochure is the thing she sends BEFORE the zip — no setup steps, no file
paths, just what the brain does. Keep it one page.
"""
import os
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
BRAIN = os.path.dirname(HERE)
ROOT = os.path.dirname(BRAIN)
SRC = os.path.join(ROOT, "design", "brochure.html")
OUT = os.path.join(ROOT, "dist", "life-brain-brochure.png")
WIDTH = 1440
TALL = 4200          # taller than the brochure will ever be; trimmed after

CHROMES = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    "chromium", "google-chrome",
]


def chrome():
    for c in CHROMES:
        if os.path.sep in c:
            if os.path.exists(c):
                return c
        else:
            from shutil import which
            if which(c):
                return which(c)
    sys.exit("No Chrome/Chromium found — install one, or open "
             "design/brochure.html and print it to PDF by hand.")


def trim(path):
    """Cut the empty paper below the last drawn row, keeping the page's own
    bottom padding. Skipped (with a note) if Pillow isn't installed."""
    try:
        from PIL import Image
    except ImportError:
        print("  (Pillow not installed — image left at full window height)")
        return
    im = Image.open(path).convert("RGB")
    w, h = im.size
    bg = im.getpixel((4, 4))
    px = im.load()
    last = h - 1
    while last > 0:
        row = range(0, w, 7)          # every 7th pixel is enough to spot ink
        if any(px[x, last] != bg for x in row):
            break
        last -= 1
    pad = int(round(62 * (w / WIDTH)))     # body's padding-bottom, scaled
    im.crop((0, 0, w, min(h, last + 1 + pad))).save(path)
    print(f"  trimmed to {w}x{min(h, last + 1 + pad)}")


def main():
    if not os.path.exists(SRC):
        sys.exit(f"missing {os.path.relpath(SRC, ROOT)}")
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with tempfile.TemporaryDirectory() as profile:
        # Old --headless on purpose: --headless=new sits and waits forever
        # here rather than writing the file.
        cmd = [chrome(), "--headless", "--disable-gpu", "--no-sandbox",
               "--no-first-run", "--disable-extensions", "--hide-scrollbars",
               "--allow-file-access-from-files",
               f"--user-data-dir={profile}",
               f"--window-size={WIDTH},{TALL}",
               f"--screenshot={OUT}", "file://" + SRC]
        # Chrome writes the screenshot and then keeps running on this
        # machine, so waiting for it to exit is waiting forever. Watch for
        # the file instead, and stop it once the size settles. Its log goes
        # to a file rather than a pipe: the helper processes inherit the
        # pipe and outlive the parent, which hangs a read the same way.
        log = os.path.join(profile, "chrome.log")
        if os.path.exists(OUT):
            os.remove(OUT)                 # never mistake yesterday's for new
        with open(log, "w") as f:
            proc = subprocess.Popen(cmd, stdout=f, stderr=subprocess.STDOUT)
        size, deadline = -1, time.time() + 120
        while time.time() < deadline:
            if proc.poll() is not None:
                break
            if os.path.exists(OUT):
                now = os.path.getsize(OUT)
                if now > 0 and now == size:
                    break                  # written, and no longer growing
                size = now
            time.sleep(0.5)
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
        tail = open(log, errors="ignore").read()[-600:]
    if not os.path.exists(OUT):
        sys.exit("Chrome wrote no image:\n" + tail)
    trim(OUT)
    print(f"  {os.path.relpath(OUT, ROOT)}")


if __name__ == "__main__":
    main()

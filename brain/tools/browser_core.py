#!/usr/bin/env python3
"""browser_core.py — what the job hunt's three browser helpers share.

The helpers, each off until she switches it on with her Touch ID:

  - apply     browser_apply.py fills an application form for a role she is
              tracking, then stops. It never clicks: she reads every field
              and presses Submit herself.
  - linkedin  browser_linkedin.py reads her LinkedIn connections list in a
              browser she logged into, into the same file LinkedIn's own
              export makes, for the From LinkedIn review on People.
  - scan      browser_scan.py reads LinkedIn's public job search and the
              careers pages she adds, for roles the job-board scan cannot
              see.

How they stay safe, and why each rule is there:

  - No model drives the browser. Plain code clicks, scrolls and types; a
    model only ever writes the text for a form, in a no-tools call. A page
    that hides instructions for an AI finds no AI holding the controls.
  - Her own Chrome profile is never opened. Each helper has its own profile
    under brain/.browser/profiles/ (git and the starter never see it; Claude
    runs cannot read it, run_policy.py). The scan uses no profile at all.
  - They start only from her click on the page. guard() refuses inside any
    Claude run, in the unattended jobs, and without the page's go-ahead;
    run_policy.py also denies the commands to every run.
  - Off means off: guard() refuses a helper she has not switched on, and
    switching one on takes her Touch ID on the page.
  - LinkedIn: a person's words in a chat or a profile are never stored, only
    the name, headline and profile link, the same fields the export carries.

The helpers run under the brain's own Python for the browser
(brain/.browser/env, made by `setup`), driving her installed Google Chrome.

    browser_core.py setup      make brain/.browser/env and install Playwright
    browser_core.py status     what is installed and switched on
"""
import json
import os
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
BRAIN = os.path.dirname(HERE)
ROOT = os.path.join(BRAIN, ".browser")
ENV = os.path.join(ROOT, "env")
PROFILES = os.path.join(ROOT, "profiles")
CONFIG = os.path.join(BRAIN, "config.json")
HELPERS = ("apply", "linkedin", "scan")
PLAYWRIGHT = "playwright==1.55.0"
CLICK_ENV = "LIFEBRAIN_PAGE_CLICK"

CHROME_CANDIDATES = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    os.path.expanduser("~/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    "/usr/bin/google-chrome", "/usr/bin/chromium", "/usr/bin/chromium-browser",
]


def env_python():
    for rel in ("bin/python", "Scripts/python.exe"):
        p = os.path.join(ENV, rel)
        if os.path.exists(p):
            return p
    return ""


def chrome_path():
    for p in CHROME_CANDIDATES:
        if os.path.exists(p):
            return p
    return ""


def _cfg():
    try:
        with open(CONFIG, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


SWITCHES = os.path.join(ROOT, "switches.json")


def switched_on(cfg=None):
    """The three switches live in brain/.browser/switches.json, not in
    config.json: config is a file Claude runs may edit, and this one no run
    can read or write (run_policy.py), so only the page's Touch ID button
    turns a helper on."""
    try:
        with open(SWITCHES, encoding="utf-8") as f:
            b = json.load(f)
    except Exception:
        b = {}
    return {h: bool(b.get(h)) for h in HELPERS}


def set_switch(helper, on):
    if helper not in HELPERS:
        raise ValueError("no browser helper called %r" % helper)
    cur = switched_on()
    cur[helper] = bool(on)
    os.makedirs(ROOT, exist_ok=True)
    with open(SWITCHES, "w", encoding="utf-8") as f:
        json.dump(cur, f)
    return cur


def status():
    return {"installed": bool(env_python()), "chrome": bool(chrome_path()),
            "on": switched_on(),
            "linkedin_profile": os.path.isdir(os.path.join(PROFILES, "linkedin"))}


def setup():
    """Make the browser's own Python inside the brain and install Playwright
    into it. Uses her Chrome, so no browser is downloaded."""
    os.makedirs(ROOT, exist_ok=True)
    if not env_python():
        subprocess.run([sys.executable, "-m", "venv", ENV], check=True,
                       timeout=300)
    r = subprocess.run([env_python(), "-m", "pip", "install", "-q",
                        "--disable-pip-version-check", PLAYWRIGHT],
                       capture_output=True, text=True, timeout=900,
                       env=dict(os.environ, PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD="1"))
    if r.returncode != 0:
        raise ValueError("installing Playwright failed: "
                         + (r.stderr or r.stdout).strip()[-200:])
    return status()


# --------------------------------------------------------------- the guard

def in_claude_run():
    """True inside any Claude Code process or an unattended job."""
    return bool(os.environ.get("CLAUDECODE") or os.environ.get("CLAUDE_CODE_ENTRYPOINT")
                or os.environ.get("LIFEBRAIN_UNATTENDED"))


def guard(helper):
    """Every helper calls this first. Raises SystemExit with a plain reason."""
    if in_claude_run():
        raise SystemExit("The browser helpers start only from your click on "
                         "the page, never from inside a Claude run.")
    if os.environ.get(CLICK_ENV) != "1":
        raise SystemExit("Start this from the Jobs tab.")
    if not switched_on().get(helper):
        raise SystemExit("The %s helper is switched off. Switch it on in the "
                         "Jobs tab first." % helper)
    if not chrome_path():
        raise SystemExit("Google Chrome is not installed.")


def launch(pw, helper=None, headless=False):
    """Chrome with the helper's own profile (or none, for helper=None)."""
    args = ["--no-first-run", "--no-default-browser-check",
            "--disable-features=Translate"]
    if helper:
        path = os.path.join(PROFILES, helper)
        os.makedirs(path, exist_ok=True)
        return pw.chromium.launch_persistent_context(
            path, executable_path=chrome_path(), headless=headless, args=args,
            viewport=None if not headless else {"width": 1280, "height": 900},
            accept_downloads=False)
    b = pw.chromium.launch(executable_path=chrome_path(), headless=headless,
                           args=args)
    return b.new_context(viewport={"width": 1280, "height": 900},
                         accept_downloads=False)


def status_path(helper):
    return os.path.join(ROOT, "status-%s.json" % helper)


def write_status(helper, **data):
    os.makedirs(ROOT, exist_ok=True)
    tmp = status_path(helper) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    os.replace(tmp, status_path(helper))


def read_status(helper):
    try:
        with open(status_path(helper), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def start(helper, args):
    """The page server's one way to run a helper: detached, under the
    browser's Python, with the page's go-ahead and no Claude markers."""
    if helper not in HELPERS:
        raise ValueError("no browser helper called %r" % helper)
    if not switched_on().get(helper):
        raise ValueError("switch the %s helper on first" % helper)
    py = env_python()
    if not py:
        raise ValueError("set up the browser first")
    # A second click while one is still opening fought over the same Chrome
    # profile and left the first stuck on "opening".
    try:
        busy = read_status(helper).get("state") in ("starting", "opening", "writing") \
            and time.time() - os.path.getmtime(status_path(helper)) < 900
    except OSError:
        busy = False
    if busy:
        raise ValueError("the %s helper is still busy; give it a minute" % helper)
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("CLAUDE", "ANTHROPIC_"))
           and k != "LIFEBRAIN_UNATTENDED"}
    env[CLICK_ENV] = "1"
    write_status(helper, state="starting")
    log = open(os.path.join(ROOT, "%s.log" % helper), "a", encoding="utf-8")
    subprocess.Popen([py, os.path.join(HERE, "browser_%s.py" % helper)] + list(args),
                     cwd=os.path.dirname(BRAIN), env=env, stdout=log,
                     stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                     start_new_session=True)
    return {"ok": True}


def main(argv):
    cmd = argv[0] if argv else "status"
    if cmd == "setup":
        print(json.dumps(setup(), indent=1))
    elif cmd == "status":
        print(json.dumps(status(), indent=1))
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

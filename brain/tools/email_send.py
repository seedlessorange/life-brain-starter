#!/usr/bin/env python3
"""Send email from the brain, directly, after the owner approves each message.

    python3 brain/tools/email_send.py setup     # connect an account (once)
    python3 brain/tools/email_send.py status

Gmail and Yahoo both work the same way: an **app password** over SMTP. That is
the private route — your Mac talks straight to the mail server, no OAuth, no
Google/Yahoo cloud consent, nothing stored with a third party. The app
password lives in the macOS Keychain, never in a file, and you can revoke it
from the provider in one click at any time.

Nothing here sends on its own. It is called only when the owner presses
"Approve & send" on one specific message, and never for anyone in a personal
circle.
"""

import argparse
import getpass
import json
import os
import re
import smtplib
import ssl
import subprocess
import sys
from email.message import EmailMessage
from email.utils import getaddresses

HERE = os.path.dirname(os.path.abspath(__file__))
BRAIN = os.path.dirname(HERE)
CONFIG = os.path.join(BRAIN, "config.json")
KC_SERVICE = "life-brain-email"
# The custom mail servers she set up herself, pinned where no run can write
# (runs are sandboxed out of brain/tools/). config.json is writable by a run,
# and a host swapped there would receive her app password at the next send.
HOST_PIN = os.path.join(HERE, ".run-policy", "email-hosts.json")

# host, port, mode. STARTTLS on 587, implicit SSL on 465.
PROVIDERS = {
    "gmail": ("smtp.gmail.com", 587, "starttls"),
    "yahoo": ("smtp.mail.yahoo.com", 465, "ssl"),
    "icloud": ("smtp.mail.me.com", 587, "starttls"),
    "outlook": ("smtp-mail.outlook.com", 587, "starttls"),
}

APP_PW_HELP = {
    "gmail": ("Google account > Security > 2-Step Verification must be ON, then "
              "'App passwords' > create one for 'Mail'. It's 16 letters."),
    "yahoo": ("Yahoo account > Account Security > 'Generate app password' (or "
              "'Manage app passwords') > Other app. It's a short code."),
    "icloud": "appleid.apple.com > Sign-In and Security > App-Specific Passwords.",
    "outlook": "Microsoft account > Security > Advanced > App passwords.",
}


# --------------------------------------------------------------------------
# secrets in the OS keystore (macOS Keychain; keyring elsewhere)

# Touch ID in front of the password (config email.touch_id, 28 Sep): the
# item is then created by brainmail (make_brainmail.sh), the one program the
# Keychain lets read it silently, and brainmail reads it only after her
# fingerprint. Anything else trying gets a macOS dialog instead.
BRAINMAIL = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         ".bin", "brainmail")


def touch_id_on():
    return bool((load_cfg().get("email") or {}).get("touch_id"))


def kc_set(account, value):
    import keychain
    if touch_id_on():
        _store_locked(account, value)
    else:
        keychain.put(KC_SERVICE, account, value)


def kc_get(account, reason="use your mail password"):
    """The password, or None when none is stored. Behind Touch ID when that
    is on; raises RuntimeError when she does not confirm."""
    import keychain
    if not touch_id_on():
        return keychain.get(KC_SERVICE, account)
    r = subprocess.run([BRAINMAIL, "get", KC_SERVICE, account, reason],
                       capture_output=True, text=True, timeout=180)
    if r.returncode == 5:
        return None
    if r.returncode == 4:
        raise RuntimeError("Touch ID wasn't confirmed")
    if r.returncode != 0:
        raise RuntimeError((r.stderr or "").strip() or "brainmail failed")
    return r.stdout


def kc_has(account):
    """Is a password stored? Never reads it, so it never asks for Touch ID."""
    import keychain
    return keychain.has(KC_SERVICE, account)


def _store_locked(account, value):
    import keychain
    if not os.access(BRAINMAIL, os.X_OK):
        raise RuntimeError("brainmail isn't built: zsh brain/tools/make_brainmail.sh")
    keychain.delete(KC_SERVICE, account)
    r = subprocess.run([BRAINMAIL, "store", KC_SERVICE, account],
                       input=value + "\n", capture_output=True, text=True,
                       timeout=30)
    if r.returncode != 0:
        raise RuntimeError("couldn't lock the password: " + (r.stderr or "").strip())


def set_touch_id(on):
    """Move every account's password behind Touch ID, or back. The password
    only passes through memory, and a failed step puts it back as it was.
    Returns the accounts moved."""
    import keychain
    if on == touch_id_on():
        return []
    moved = []
    for a in accounts():
        addr = a["address"]
        if on:
            pw = keychain.get(KC_SERVICE, addr)         # the open item
            if pw is None:
                continue
            try:
                _store_locked(addr, pw)
                if not keychain.has(KC_SERVICE, addr):
                    raise RuntimeError("the locked copy isn't there")
            except Exception:
                keychain.delete(KC_SERVICE, addr)
                keychain.put(KC_SERVICE, addr, pw)
                raise
        else:
            pw = kc_get(addr, "move your mail password back to the plain Keychain")
            if pw is None:
                continue
            keychain.delete(KC_SERVICE, addr)
            keychain.put(KC_SERVICE, addr, pw)
        moved.append(addr)
    cfg = load_cfg()
    cfg.setdefault("email", {})["touch_id"] = bool(on)
    save_cfg(cfg)
    return moved


# --------------------------------------------------------------------------
# config (accounts + which provider; NEVER the password)

def load_cfg():
    try:
        with open(CONFIG, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_cfg(cfg):
    tmp = CONFIG + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)
        f.write("\n")
    os.replace(tmp, CONFIG)


def accounts():
    return (load_cfg().get("email") or {}).get("accounts", [])


def default_account():
    em = load_cfg().get("email") or {}
    if em.get("default"):
        return em["default"]
    a = em.get("accounts", [])
    return a[0]["address"] if a else None


def add_account(address, provider, app_password, host="", port=0, mode=""):
    address = address.strip()
    provider = provider.strip().lower()
    if not address or "@" not in address:
        raise ValueError("that isn't an email address")
    if provider not in PROVIDERS and not host:
        raise ValueError(f"unknown provider {provider!r}; give host/port for a custom one")
    if not app_password.strip():
        raise ValueError("no app password given")
    if host and provider not in PROVIDERS:
        # Pinned first: if the pin can't be written, nothing is set up.
        _pin_host(address, host, int(port), mode or "starttls")
    kc_set(address, app_password.strip())        # to the Keychain, never config
    cfg = load_cfg()
    em = cfg.setdefault("email", {"accounts": []})
    entry = {"address": address, "provider": provider}
    if host and provider not in PROVIDERS:
        entry.update({"host": host, "port": int(port), "mode": mode or "starttls"})
    em["accounts"] = [a for a in em.get("accounts", []) if a["address"] != address]
    em["accounts"].append(entry)
    if not em.get("default"):
        em["default"] = address
    save_cfg(cfg)
    return address


# --------------------------------------------------------------------------
# sending

def _host_pins():
    try:
        with open(HOST_PIN, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _pin_host(address, host, port, mode):
    pins = _host_pins()
    pins[address.lower()] = [host, int(port), mode]
    os.makedirs(os.path.dirname(HOST_PIN), exist_ok=True)
    tmp = HOST_PIN + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(pins, f, indent=1)
        f.write("\n")
    os.replace(tmp, HOST_PIN)


def _smtp_for(entry):
    """Where the password goes. A known provider always uses the table — a
    `host` beside it in config is ignored. A custom server must match what
    was pinned when she set it up."""
    prov = (entry.get("provider") or "").lower()
    if prov in PROVIDERS:
        return PROVIDERS[prov]
    want = [entry.get("host"), int(entry.get("port", 587) or 0),
            entry.get("mode", "starttls")]
    pin = _host_pins().get((entry.get("address") or "").lower())
    if not entry.get("host") or pin != want:
        raise ValueError(f"the mail server for {entry.get('address')} changed "
                         "since you set it up — run the email setup again")
    return tuple(want)


# Anything that could turn one address into two, or into a new header line.
_NOT_IN_ADDRESS = re.compile(r"[\s,;<>\"'()\[\]\\]")


def clean_recipient(value):
    """The single address a send may go to, or "" when there isn't exactly one.

    Never falls back to the raw text: "a@x.com, b@evil.com" is two people,
    and a mail server handed that string delivers to both.
    """
    raw = value or ""
    if "\r" in raw or "\n" in raw:
        return ""
    pairs = [(n, a) for n, a in getaddresses([raw]) if n or a]
    if len(pairs) != 1:
        return ""
    addr = pairs[0][1].strip()
    if addr.count("@") != 1 or _NOT_IN_ADDRESS.search(addr):
        return ""
    local, domain = addr.split("@")
    if not local or "." not in domain.strip("."):
        return ""
    return addr


RECIPIENTS = os.path.join(HERE, ".run-policy", "email-recipients.json")


def _recipients(path=None):
    try:
        with open(path or RECIPIENTS, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def addresses_for(name, path=None):
    """The addresses she has sent to for this person, lower-case."""
    return _recipients(path).get((name or "").strip().lower(), [])


def remember_address(name, addr, path=None):
    """Trust on first use: the first address she approves a send to becomes
    the one on file, and every later send to that person must match it.

    Kept under brain/tools/.run-policy/, not in people.md: no Claude run can
    write there, so a run cannot put its own address on someone's card; and
    people.md holds no contact details (her rule). Only ever fills a blank.
    """
    path = path or RECIPIENTS
    data = _recipients(path)
    key = (name or "").strip().lower()
    if not key or data.get(key):
        return False
    data[key] = [addr.lower()]
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1, sort_keys=True)
    os.replace(tmp, path)
    return True


def send(to_addr, subject, body, from_account=None, person=None):
    """Send one message. Returns (ok, detail).

    The boundary lives HERE, not in the caller: a send must either name a
    tracked person (whose circle is re-derived from people.md right now —
    personal circles and unknown names refuse) or go to one of the owner's
    own connected addresses (the self-test). Unattended runs refuse outright.
    """
    if os.environ.get("LIFEBRAIN_UNATTENDED"):
        return False, "sending is disabled in unattended runs"
    to_addr = clean_recipient(to_addr)
    if not to_addr:
        return False, ("the To line isn't exactly one email address — a send "
                       "goes to one person only")
    bind_to = None
    if person:
        sys.path.insert(0, HERE)
        import model as M
        match = next((p for p in M.load_people()
                      if p["name"].lower() == person.strip().lower()), None)
        if match is None:
            return False, (f"{person} is not on your people list — sending "
                           "needs a tracked, non-personal person")
        if match.get("personal", True):
            return False, (f"{person} is in a personal circle — Claude can't "
                           "send to them, only draft")
        # The address must be the person's, not whatever the draft says.
        on_file = addresses_for(match["name"])
        if on_file and to_addr.lower() not in on_file:
            return False, (f"That address isn't the one on file for "
                           f"{match['name']} (the one you sent to before) — "
                       "change it in brain/tools/.run-policy/email-recipients.json "
                       "by hand if they really moved")
        if not on_file:
            bind_to = match["name"]
    elif to_addr.lower() not in {a["address"].lower() for a in accounts()}:
        return False, ("refusing: no person named for this recipient. Only a "
                       "self-test to your own connected address sends without one")
    # One line, always: a newline here would be a header of its own.
    subject = " ".join((subject or "").split())
    from_account = from_account or default_account()
    entry = next((a for a in accounts() if a["address"] == from_account), None)
    if not entry:
        return False, "that sending account isn't set up"
    try:
        pw = kc_get(from_account, reason=f"send the email to {to_addr}")
    except RuntimeError as exc:
        return False, f"not sent: {exc}"
    if not pw:
        return False, ("no app password in the Keychain for " + from_account
                       + " — run email setup again")
    try:
        host, port, mode = _smtp_for(entry)
    except ValueError as exc:
        return False, str(exc)

    msg = EmailMessage()
    msg["From"] = from_account
    msg["To"] = to_addr
    msg["Subject"] = subject or "(no subject)"
    msg.set_content(body or "")
    # The envelope names the one checked address, so no header can add a
    # recipient the checks above never saw.
    try:
        if mode == "ssl":
            with smtplib.SMTP_SSL(host, port, context=ssl.create_default_context(),
                                  timeout=30) as s:
                s.login(from_account, pw)
                s.send_message(msg, from_addr=from_account, to_addrs=[to_addr])
        else:
            with smtplib.SMTP(host, port, timeout=30) as s:
                s.starttls(context=ssl.create_default_context())
                s.login(from_account, pw)
                s.send_message(msg, from_addr=from_account, to_addrs=[to_addr])
    except smtplib.SMTPAuthenticationError:
        return False, ("the mail server refused the login — the app password is "
                       "wrong or expired. Generate a new one and run setup again.")
    except Exception as exc:                    # noqa: BLE001
        return False, f"{type(exc).__name__}: {exc}"
    if bind_to:
        try:
            remember_address(bind_to, to_addr.lower())
        except Exception:                       # noqa: BLE001
            pass    # the send happened; a missed Email line must not report failure
    return True, "sent"


# --------------------------------------------------------------------------
# cli

def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status")
    s = sub.add_parser("setup")
    s.add_argument("--address")
    s.add_argument("--provider", choices=list(PROVIDERS))
    t = sub.add_parser("test",
                       help="send a test message to one of your OWN connected "
                            "addresses (anything else refuses)")
    t.add_argument("to")
    ti = sub.add_parser("touchid", help="put the password behind Touch ID, or take it back out")
    ti.add_argument("state", choices=["on", "off", "status"])
    args = ap.parse_args()

    if args.cmd == "touchid":
        if args.state == "status":
            print("  Touch ID: " + ("ON" if touch_id_on() else "off"))
            return
        moved = set_touch_id(args.state == "on")
        print(f"  Touch ID {'on' if args.state == 'on' else 'off'}"
              + (f" for {', '.join(moved)}" if moved else " (nothing to move)"))
        return

    if args.cmd == "status":
        d = default_account()
        for a in accounts():
            has = "yes" if kc_has(a["address"]) else "NO PASSWORD"
            star = " (default)" if a["address"] == d else ""
            print(f"  {a['address']}  [{a['provider']}]  password: {has}{star}")
        if not accounts():
            print("  no accounts connected — run: python3 brain/tools/email_send.py setup")
        return

    if args.cmd == "setup":
        addr = args.address or input("Email address: ").strip()
        prov = args.provider or input("Provider (gmail/yahoo/icloud/outlook): ").strip().lower()
        print("\n  " + APP_PW_HELP.get(prov, "Create an app password in your account security settings.") + "\n")
        pw = getpass.getpass("App password (hidden): ")
        add_account(addr, prov, pw)
        print(f"\n  Connected {addr}. It's in your Keychain, not in any file.")
        print("  Test it:  python3 brain/tools/email_send.py test you@example.com\n")
        return

    if args.cmd == "test":
        ok, detail = send(args.to, "Brain email test",
                          "This is a test from your life-brain. If you got it, sending works.")
        print("  sent" if ok else "  failed: " + detail)


if __name__ == "__main__":
    main()

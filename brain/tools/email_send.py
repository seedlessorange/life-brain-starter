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
import smtplib
import ssl
import subprocess
import sys
from email.message import EmailMessage
from email.utils import parseaddr

HERE = os.path.dirname(os.path.abspath(__file__))
BRAIN = os.path.dirname(HERE)
CONFIG = os.path.join(BRAIN, "config.json")
KC_SERVICE = "life-brain-email"

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

def kc_set(account, value):
    if sys.platform == "darwin":
        subprocess.run(["security", "add-generic-password", "-U",
                        "-s", KC_SERVICE, "-a", account, "-w", value],
                       check=True, capture_output=True)
        return
    try:
        import keyring
    except ImportError:
        raise RuntimeError(
            "Storing the app password needs the 'keyring' package on this "
            "system (it uses Windows Credential Manager / Secret Service). "
            "Run: pip install keyring — then connect the account again."
        ) from None
    keyring.set_password(KC_SERVICE, account, value)


def kc_get(account):
    if sys.platform == "darwin":
        r = subprocess.run(["security", "find-generic-password",
                            "-s", KC_SERVICE, "-a", account, "-w"],
                           capture_output=True, text=True)
        return r.stdout.strip() if r.returncode == 0 else None
    try:
        import keyring
        return keyring.get_password(KC_SERVICE, account)
    except Exception:
        return None


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
    kc_set(address, app_password.strip())        # to the Keychain, never config
    cfg = load_cfg()
    em = cfg.setdefault("email", {"accounts": []})
    entry = {"address": address, "provider": provider}
    if host:
        entry.update({"host": host, "port": int(port), "mode": mode or "starttls"})
    em["accounts"] = [a for a in em.get("accounts", []) if a["address"] != address]
    em["accounts"].append(entry)
    if not em.get("default"):
        em["default"] = address
    save_cfg(cfg)
    return address


# --------------------------------------------------------------------------
# sending

def _smtp_for(entry):
    if entry.get("host"):
        return entry["host"], int(entry.get("port", 587)), entry.get("mode", "starttls")
    return PROVIDERS[entry["provider"]]


def send(to_addr, subject, body, from_account=None, person=None):
    """Send one message. Returns (ok, detail).

    The boundary lives HERE, not in the caller: a send must either name a
    tracked person (whose circle is re-derived from people.md right now —
    personal circles and unknown names refuse) or go to one of the owner's
    own connected addresses (the self-test). Unattended runs refuse outright.
    """
    if os.environ.get("LIFEBRAIN_UNATTENDED"):
        return False, "sending is disabled in unattended runs"
    to_addr = parseaddr(to_addr)[1] or to_addr.strip()
    if "@" not in (to_addr or ""):
        return False, "no valid recipient address"
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
    elif to_addr not in {a["address"] for a in accounts()}:
        return False, ("refusing: no person named for this recipient. Only a "
                       "self-test to your own connected address sends without one")
    from_account = from_account or default_account()
    entry = next((a for a in accounts() if a["address"] == from_account), None)
    if not entry:
        return False, "that sending account isn't set up"
    pw = kc_get(from_account)
    if not pw:
        return False, ("no app password in the Keychain for " + from_account
                       + " — run email setup again")
    host, port, mode = _smtp_for(entry)

    msg = EmailMessage()
    msg["From"] = from_account
    msg["To"] = to_addr
    msg["Subject"] = subject or "(no subject)"
    msg.set_content(body or "")
    try:
        if mode == "ssl":
            with smtplib.SMTP_SSL(host, port, context=ssl.create_default_context(),
                                  timeout=30) as s:
                s.login(from_account, pw)
                s.send_message(msg)
        else:
            with smtplib.SMTP(host, port, timeout=30) as s:
                s.starttls(context=ssl.create_default_context())
                s.login(from_account, pw)
                s.send_message(msg)
        return True, "sent"
    except smtplib.SMTPAuthenticationError:
        return False, ("the mail server refused the login — the app password is "
                       "wrong or expired. Generate a new one and run setup again.")
    except Exception as exc:                    # noqa: BLE001
        return False, f"{type(exc).__name__}: {exc}"


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
    args = ap.parse_args()

    if args.cmd == "status":
        d = default_account()
        for a in accounts():
            has = "yes" if kc_get(a["address"]) else "NO PASSWORD"
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

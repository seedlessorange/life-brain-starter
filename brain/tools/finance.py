#!/usr/bin/env python3
"""The bank feed: Revolut + Santander into brain/finance/, read-only.

    python3 brain/tools/finance.py status            # is the key good? what's linked?
    python3 brain/tools/finance.py banks ES          # exact bank names Enable Banking knows
    python3 brain/tools/finance.py link "Banco Santander" --country ES --days 1
    python3 brain/tools/finance.py fetch             # pull balances + transactions
    python3 brain/tools/finance.py summary           # rebuild the aggregate numbers

How the pieces fit: the private RSA key lives in the macOS Keychain
(service life-brain-bankfeed) and is streamed to openssl for signing —
it is never written to disk. `link` starts a bank's approval ceremony:
it prints a URL, she approves in the bank's own app, and the bank sends
her browser back to serve.py's /enablebanking/callback (via tailscale
serve), which calls finish_link() here. Raw transactions stay in
brain/finance/raw/ on this Mac and are gitignored; only the aggregates
in summary.json are meant to be read into a Claude context.

Access is account-information only under PSD2 — this app has no payment
scope, and the Enable Banking application is in restricted mode, locked
to her own linked accounts.
"""

import base64
import hashlib
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
from datetime import date, datetime, timedelta, timezone

TOOLS = os.path.dirname(os.path.abspath(__file__))
BRAIN = os.path.dirname(TOOLS)
FIN = os.path.join(BRAIN, "finance")
RAW = os.path.join(FIN, "raw")
STATE = os.path.join(FIN, "state.json")
SUMMARY = os.path.join(FIN, "summary.json")

API = "https://api.enablebanking.com"
KC_SERVICE = "life-brain-bankfeed"
KC_ACCOUNT = "enablebanking-key"


def _config():
    with open(os.path.join(BRAIN, "config.json")) as f:
        return json.load(f).get("finance") or {}


def _key_pem():
    r = subprocess.run(["security", "find-generic-password",
                        "-s", KC_SERVICE, "-a", KC_ACCOUNT, "-w"],
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError("no bank key in the Keychain (service %s)" % KC_SERVICE)
    return base64.b64decode(r.stdout.strip())


def _b64url(b):
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def _jwt(app_id):
    now = int(time.time())
    header = {"typ": "JWT", "alg": "RS256", "kid": app_id}
    payload = {"iss": "enablebanking.com", "aud": "api.enablebanking.com",
               "iat": now, "exp": now + 3600}
    signing_input = (_b64url(json.dumps(header, separators=(",", ":")).encode())
                     + "." +
                     _b64url(json.dumps(payload, separators=(",", ":")).encode()))
    # data as a temp file (not secret), key streamed on stdin (secret)
    tmp = os.path.join(FIN, ".signing-input")
    os.makedirs(FIN, exist_ok=True)
    with open(tmp, "w") as f:
        f.write(signing_input)
    try:
        r = subprocess.run(["openssl", "dgst", "-sha256", "-sign", "/dev/stdin", tmp],
                           input=_key_pem(), capture_output=True)
        if r.returncode != 0:
            raise RuntimeError("signing failed: " + r.stderr.decode())
        return signing_input + "." + _b64url(r.stdout)
    finally:
        os.unlink(tmp)


def _call(method, path, body=None):
    cfg = _config()
    req = urllib.request.Request(API + path, method=method)
    req.add_header("Authorization", "Bearer " + _jwt(cfg["app_id"]))
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, data, timeout=60) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")[:500]
        raise RuntimeError("%s %s -> HTTP %s: %s" % (method, path, e.code, detail)) from None


def _state():
    if os.path.exists(STATE):
        with open(STATE) as f:
            return json.load(f)
    return {"pending": {}, "sessions": {}}


def _save_state(st):
    os.makedirs(FIN, exist_ok=True)
    with open(STATE, "w") as f:
        json.dump(st, f, indent=1, default=str)


# --------------------------------------------------------------------------
# commands

def status():
    app = _call("GET", "/application")
    st = _state()
    print("Application:", app.get("name"), "—", app.get("environment"),
          "(restricted)" if app.get("services") else "")
    if not st["sessions"]:
        print("No bank sessions yet. Run: link \"<bank name>\" --country ES")
    for name, s in st["sessions"].items():
        print("  %s — %d account(s), consent until %s"
              % (name, len(s.get("accounts", [])), s.get("valid_until", "?")))


def banks(country):
    got = _call("GET", "/aspsps?country=" + country.upper())
    for a in got.get("aspsps", []):
        print("  %(name)s  (%(country)s)" % a)


def link(bank, country, days):
    cfg = _config()
    state_id = str(uuid.uuid4())
    valid = (datetime.now(timezone.utc) + timedelta(days=days)).replace(microsecond=0)
    body = {"access": {"valid_until": valid.isoformat()},
            "aspsp": {"name": bank, "country": country.upper()},
            "state": state_id,
            "redirect_url": cfg["redirect_url"],
            "psu_type": "personal"}
    got = _call("POST", "/auth", body)
    st = _state()
    st["pending"][state_id] = {"bank": bank, "country": country.upper(),
                               "started": datetime.now(timezone.utc).isoformat()}
    _save_state(st)
    print("Open this and approve in the bank's own login:\n")
    print("  " + got["url"])
    print("\nAfter approving you should land on a page saying 'Linked'. If you get")
    print("a 502 error page instead, that's fine: copy the full URL from the")
    print("address bar and give it to Claude — the code in it is all that's needed.")


def finish_link(code, state_id):
    """Called by serve.py's /enablebanking/callback. Returns the bank name."""
    st = _state()
    pending = st["pending"].pop(state_id, None)
    session = _call("POST", "/sessions", {"code": code})
    bank = (pending or {}).get("bank") or session.get("aspsp", {}).get("name", "bank")
    st["sessions"][bank] = {
        "session_id": session.get("session_id"),
        "valid_until": session.get("access", {}).get("valid_until"),
        "accounts": [{"uid": a.get("uid"),
                      "iban": (a.get("account_id") or {}).get("iban"),
                      "name": a.get("name") or a.get("product")}
                     for a in session.get("accounts", [])],
        "linked": datetime.now(timezone.utc).isoformat(),
    }
    _save_state(st)
    return bank


def _txn_key(t):
    ref = t.get("entry_reference")
    if ref:
        return ref
    blob = json.dumps([t.get("booking_date"), t.get("transaction_amount"),
                       t.get("remittance_information")], sort_keys=True)
    return hashlib.sha1(blob.encode()).hexdigest()[:16]


def fetch():
    st = _state()
    if not st["sessions"]:
        sys.exit("nothing linked yet — run `link` first")
    os.makedirs(RAW, exist_ok=True)
    for bank, s in st["sessions"].items():
        for acc in s.get("accounts", []):
            uid, iban = acc.get("uid"), acc.get("iban") or acc.get("uid")
            # One lapsed consent (Santander's lasts a day) must not stop the
            # other bank's fetch — stale-and-labelled beats all-or-nothing.
            try:
                bal = _call("GET", "/accounts/%s/balances" % uid)
            except RuntimeError as e:
                print("%s %s: skipped (%s)" % (bank, iban, str(e)[:80]))
                continue
            acc["balances"] = bal.get("balances", [])
            path = os.path.join(RAW, "%s.jsonl" % iban)
            seen = set()
            if os.path.exists(path):
                with open(path) as f:
                    seen = {_txn_key(json.loads(line)) for line in f if line.strip()}
            date_from = (date.today() - timedelta(days=90)).isoformat()
            new, cont = 0, None
            with open(path, "a") as out:
                while True:
                    q = "/accounts/%s/transactions?date_from=%s" % (uid, date_from)
                    if cont:
                        q += "&continuation_key=" + cont
                    got = _call("GET", q)
                    for t in got.get("transactions", []):
                        if _txn_key(t) not in seen:
                            seen.add(_txn_key(t))
                            out.write(json.dumps(t) + "\n")
                            new += 1
                    cont = got.get("continuation_key")
                    if not cont:
                        break
            s["fetched"] = datetime.now(timezone.utc).isoformat()
            print("%s %s: %d new transaction(s), balance %s"
                  % (bank, iban, new,
                     ", ".join("%s %s" % (b.get("balance_amount", {}).get("amount"),
                                          b.get("balance_amount", {}).get("currency"))
                               for b in acc["balances"][:1]) or "?"))
    _save_state(st)
    summary()


def summary():
    st = _state()
    months = {}
    for fn in (os.listdir(RAW) if os.path.isdir(RAW) else []):
        with open(os.path.join(RAW, fn)) as f:
            for line in f:
                if not line.strip():
                    continue
                t = json.loads(line)
                m = (t.get("booking_date") or t.get("value_date") or "")[:7]
                if not m:
                    continue
                amt = float((t.get("transaction_amount") or {}).get("amount") or 0)
                side = "out" if t.get("credit_debit_indicator") == "DBIT" else "in"
                months.setdefault(m, {"in": 0.0, "out": 0.0})[side] += abs(amt)
    balances = []
    for bank, s in st["sessions"].items():
        for acc in s.get("accounts", []):
            for b in (acc.get("balances") or [])[:1]:
                balances.append({"bank": bank, "iban": acc.get("iban"),
                                 "amount": (b.get("balance_amount") or {}).get("amount"),
                                 "currency": (b.get("balance_amount") or {}).get("currency")})
    full = [m for m in sorted(months) if m < date.today().isoformat()[:7]]
    burn = None
    if full:
        last = full[-3:]
        burn = round(sum(months[m]["out"] - months[m]["in"] for m in last) / len(last), 2)
    # Long-term holdings she reports by hand (manual.json): DEGIRO has no
    # official API, and a slow portfolio needs a dated number, not plumbing.
    manual = {}
    mp = os.path.join(FIN, "manual.json")
    if os.path.exists(mp):
        with open(mp) as f:
            manual = json.load(f)
    inv = manual.get("investments") or []
    out = {"updated": datetime.now(timezone.utc).isoformat(),
           "banks": {bank: {"fetched": s.get("fetched"),
                            "consent_until": s.get("valid_until")}
                     for bank, s in st["sessions"].items()},
           "investments": inv,
           "investments_total_eur": round(sum(i.get("eur") or 0 for i in inv), 2),
           "income_monthly_eur": manual.get("income_monthly_eur"),
           "balances": balances,
           "months": {m: {k: round(v, 2) for k, v in d.items()}
                      for m, d in sorted(months.items())},
           "monthly_burn_estimate": burn}
    os.makedirs(FIN, exist_ok=True)
    with open(SUMMARY, "w") as f:
        json.dump(out, f, indent=1)
    print("Balances:")
    for b in balances:
        print("  %(bank)s %(iban)s: %(amount)s %(currency)s" % b)
    if inv:
        print("Investments: %.2f EUR (%s)"
              % (out["investments_total_eur"],
                 ", ".join("%s %.0f as of %s" % (i["name"], i.get("eur") or 0,
                                                 i.get("as_of", "?")) for i in inv)))
    for m in sorted(months)[-4:]:
        d = months[m]
        print("  %s: in %.2f, out %.2f, net %+.2f" % (m, d["in"], d["out"], d["in"] - d["out"]))
    if burn is not None:
        print("Rough monthly burn (last %d full month(s)): %.2f" % (len(full[-3:]), burn))


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args or args[0] == "status":
        status()
    elif args[0] == "banks":
        banks(args[1] if len(args) > 1 else "ES")
    elif args[0] == "link":
        days = int(args[args.index("--days") + 1]) if "--days" in args else 89
        country = args[args.index("--country") + 1] if "--country" in args else "ES"
        link(args[1], country, days)
    elif args[0] == "fetch":
        fetch()
    elif args[0] == "summary":
        summary()
    else:
        sys.exit(__doc__)

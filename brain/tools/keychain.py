"""Store a secret in the macOS Keychain without putting it on a command line.

`security add-generic-password -w SECRET` puts the secret in the process's
arguments, where any process on the Mac can read it with `ps` while it runs.
`security -i` reads its commands from stdin instead, so the secret only ever
travels through a pipe. One helper so every tool that stores a token does it
the same way.

`get` and `put` are the cross-platform pair every tool uses: the macOS
Keychain, or elsewhere the `keyring` package (Windows Credential Manager,
Linux Secret Service). There were five private copies of them.
"""

import subprocess
import sys


def get(service, account):
    """The stored secret, or None when there is none (or no keystore)."""
    if sys.platform == "darwin":
        r = subprocess.run(["security", "find-generic-password",
                            "-s", service, "-a", account, "-w"],
                           capture_output=True, text=True)
        return r.stdout.strip() if r.returncode == 0 else None
    try:
        import keyring
        return keyring.get_password(service, account)
    except Exception:
        return None


def put(service, account, value):
    """Store a secret in the OS keystore. Raises when there is none."""
    if sys.platform == "darwin":
        set_password(service, account, value)
        return
    try:
        import keyring
    except ImportError:
        raise RuntimeError(
            "Storing a secret needs the 'keyring' package on this system "
            "(it uses Windows Credential Manager / Secret Service). "
            "Run: pip install keyring — then try again.") from None
    keyring.set_password(service, account, value)


def _quote(s):
    # security's interactive parser takes double-quoted words with backslash
    # escapes; checked by round-trip on quotes, backslashes, $ and accents.
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def has(service, account):
    """Is a secret stored? Reads the item's name only, never the secret, so
    it never asks for approval — status checks use this, not get()."""
    if sys.platform == "darwin":
        r = subprocess.run(["security", "find-generic-password",
                            "-s", service, "-a", account],
                           capture_output=True, text=True)
        return r.returncode == 0
    return get(service, account) is not None


def delete(service, account):
    """Remove a stored secret (macOS). True if one was removed."""
    r = subprocess.run(["security", "delete-generic-password",
                        "-s", service, "-a", account],
                       capture_output=True, text=True)
    return r.returncode == 0


def set_password(service, account, value, trusted=None):
    """Add or update (-U) a generic password. Raises CalledProcessError on
    failure, like the `check=True` calls it replaces."""
    value = str(value)
    if "\n" in value or "\r" in value or "\x00" in value:
        # a line break would end the command and run the rest as another one
        raise ValueError("a secret cannot contain a line break")
    # `trusted`: the only program that may read it without a macOS dialog
    # (-T). Unset, the default applies: `security` itself, so anything that
    # can run it reads the secret silently.
    t = f"-T {_quote(trusted)} " if trusted else ""
    cmd = (f"add-generic-password -U -s {_quote(service)} "
           f"-a {_quote(account)} {t}-w {_quote(value)}\n")
    r = subprocess.run(["security", "-i"], input=cmd, text=True,
                       capture_output=True)
    # `security -i` exits 0 even when a command inside it fails, so its
    # complaint on stderr is the only signal.
    if r.returncode != 0 or r.stderr.strip():
        raise subprocess.CalledProcessError(
            r.returncode or 1, ["security", "-i", "add-generic-password"],
            output=r.stdout, stderr=r.stderr)

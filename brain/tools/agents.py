#!/usr/bin/env python3
"""Which AI agent the brain runs: Claude Code, Codex or Gemini CLI.

    python3 brain/tools/agents.py                 # which one, and what is installed
    python3 brain/tools/agents.py use codex       # switch (claude | codex | gemini)
    python3 brain/tools/agents.py use gemini --model sonnet=gemini-2.5-pro
    python3 brain/tools/agents.py show codex brain   # the exact command, for reading

WHY THIS EXISTS. Until 5 Oct 2026 every run the brain started was Claude
Code: the page's Ask and Work the queue, the 7am plan, the night shift,
Sessions, the talk orb. People who pay for ChatGPT or Gemini instead
could not use the app at all. This file lets the same runs go to OpenAI's
Codex CLI or Google's Gemini CLI, signed in with that person's own plan.

How it fits in without touching the rest. Callers keep building their
Claude command exactly as before. When the choice here is not Claude, they
call argv() instead, which starts THIS file as a small wrapper around the
other CLI. The wrapper translates that CLI's output into the event stream
Claude Code prints (stream-json, or one json result, or plain text), so the
page's live feed, Sessions, the usage ledger and the morning log read it
without knowing the difference.

The fences are the point. Each run keeps its run_policy.py profile, built
from the same two lists (run_policy.fences):
  codex   a named permission profile passed on the command line: the folder
          writable, the brain's code, git's hooks and the launchers read-only,
          the key stores and (at night) the journal unreadable, no network.
          Codex enforces it with the Mac's own sandbox, the way Claude does.
  gemini  on a Mac, the whole Gemini process runs inside a sandbox profile
          this file writes (same read-only and unreadable paths), and its
          only way out is a proxy this file runs. The proxy opens tunnels
          to Google's Gemini API hosts, and only for Gemini's own process:
          a command Gemini runs reaches no network, the same as under the
          other two.
Choice and generated profiles live in brain/tools/.run-policy/, which no
run can write, so a run cannot switch the next one to a softer agent.

What stays Claude-only: the "asks first" mode in Sessions (it is a Claude
Code hook; under the others such a conversation runs read-only), reading
pictures (llm.complete_images), and the weekly events scout.
"""
import json
import os
import re
import select
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import run_policy as RP  # noqa: E402

ROOT, BRAIN = RP.ROOT, RP.BRAIN
CHOICE = os.path.join(RP.POLICY_DIR, "agent.json")
NAMES = {"claude": "Claude Code", "codex": "Codex", "gemini": "Gemini CLI"}
SPOKEN = {"claude": "Claude", "codex": "Codex", "gemini": "Gemini"}
INSTALL = {
    "claude": "Install Claude Code from claude.com/claude-code, then run `claude` once to sign in.",
    "codex": "Install Codex with `npm install -g @openai/codex`, then run `codex login` once to sign in with ChatGPT.",
    "gemini": "Install Gemini CLI with `npm install -g @google/gemini-cli`, then run `gemini` once to sign in with Google.",
}
NPM_PKG = {"codex": "@openai/codex", "gemini": "@google/gemini-cli"}
# The tier names the page picks (haiku/sonnet/opus/fable) mean nothing to the
# other agents. Without a mapping in agent.json their own default model runs.
TIERS = ("haiku", "sonnet", "opus", "fable")


# ── the choice ─────────────────────────────────────────────────────────────

def choice():
    try:
        with open(CHOICE, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        data = {}
    name = str(data.get("provider") or "claude").strip().lower()
    return {"provider": name if name in NAMES else "claude",
            "models": {k: str(v) for k, v in (data.get("models") or {}).items()
                       if k in TIERS and v}}


def provider():
    """'claude', 'codex' or 'gemini'. Anything unreadable is Claude."""
    return choice()["provider"]


def use(name, models=None):
    name = name.strip().lower()
    if name not in NAMES:
        raise ValueError(f"unknown agent {name!r}: claude, codex or gemini")
    cur = choice()
    data = {"provider": name,
            "models": dict(cur["models"], **(models or {}))
            if name == cur["provider"] else dict(models or {})}
    os.makedirs(RP.POLICY_DIR, exist_ok=True)
    tmp = CHOICE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1)
    os.replace(tmp, CHOICE)
    return data


def model_for(tier, name=None):
    """The model id for a picked tier under the current agent, or ''."""
    name = name or provider()
    if name == "claude":
        import usage
        return usage.cli_model(tier) if tier else ""
    return choice()["models"].get(tier or "", "")


def label():
    return NAMES[provider()]


def short():
    """The name in a sentence: "Claude files it on the next run"."""
    return SPOKEN[provider()]


def say(text):
    """Fixed page wording, in the name of the agent this brain runs.

    The page was written when every run was Claude, so its wording says
    "Claude" throughout, and a friend running Codex read "Claude" everywhere
    (8 Oct 2026). Builders pass their own template text through here, never
    her data: a task that mentions Claude must keep saying Claude. Under
    Claude this returns the text untouched, so her pages do not change."""
    name = provider()
    if name == "claude" or "Claude" not in text:
        return text
    return re.sub(r"\bClaude\b", SPOKEN[name],
                  text.replace("Claude Code", NAMES[name]))


# ── finding the program ────────────────────────────────────────────────────

def _npm_js(name):
    """On Windows an npm install is a .cmd shim, and a prompt handed to it
    goes through cmd.exe, which stops at the first line break (the reason
    run_policy refuses Claude's). So the shim is skipped: node runs the
    package's own script, found from the shim's folder."""
    shim = shutil.which(name + ".cmd")
    node = shutil.which("node")
    if not shim or not node:
        return None
    pkg = os.path.join(os.path.dirname(shim), "node_modules",
                       *NPM_PKG[name].split("/"))
    try:
        with open(os.path.join(pkg, "package.json"), encoding="utf-8") as f:
            bins = json.load(f).get("bin") or {}
    except (OSError, ValueError):
        return None
    rel = bins.get(name) if isinstance(bins, dict) else bins
    return [node, os.path.join(pkg, rel)] if rel else None


def program(name=None):
    """The command that starts an agent, as a list, or None."""
    name = name or provider()
    if name == "claude":
        p = RP.claude_path()
        return [p] if p else None
    if sys.platform == "win32":
        exe = shutil.which(name + ".exe")
        return [exe] if exe else _npm_js(name)
    p = shutil.which(name)
    return [p] if p else None


def missing(name=None):
    name = name or provider()
    if name == "claude":
        return RP.claude_missing()
    return f"{NAMES[name]} is not installed, or not on your PATH. " + INSTALL[name]


def installed():
    return {n: bool(program(n)) for n in NAMES}


def env(name=None):
    """The environment for a run. Claude always bills the subscription, never
    a key another project left in the shell. Codex and Gemini keep theirs: a
    free AI Studio key is an ordinary way to sign in to Gemini. Gemini's own
    sandbox switches go, since this file decides how it is fenced."""
    e = dict(os.environ)
    for k in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "GEMINI_SANDBOX",
              "SEATBELT_PROFILE", "GEMINI_SANDBOX_PROXY_COMMAND"):
        e.pop(k, None)
    return e


# ── the brain's commands, for agents that don't know them ──────────────────

COMMANDS = os.path.join(ROOT, ".claude", "commands")


def expand(prompt):
    """`/today Today is …` means a file under .claude/commands to Claude Code
    and nothing to the others, so they get the file itself."""
    m = re.match(r"\s*/([a-z][\w-]*)\b\s*(.*)", prompt or "", re.S)
    if not m:
        return prompt
    path = os.path.join(COMMANDS, m.group(1) + ".md")
    try:
        with open(path, encoding="utf-8") as f:
            body = f.read()
    except OSError:
        return prompt
    if body.startswith("---"):
        body = body.split("---", 2)[-1]
    rest = m.group(2).strip()
    if "$ARGUMENTS" in body:
        body = body.replace("$ARGUMENTS", rest)
        rest = ""
    head = (f"You are running the brain's /{m.group(1)} command. The steps "
            f"are below; follow them as written. Where they name a tool "
            f"(Read, Edit, Bash), use your own equivalent.\n\n")
    return head + body.strip() + (f"\n\nArguments: {rest}" if rest else "")


# ── the fences, translated ─────────────────────────────────────────────────

SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", "dist",
             "build", ".next"}


def _resolve(pattern, base):
    """One run_policy pattern as (kind, value): ('path', abs path) for a
    folder or file, ('glob', (abs dir, regex for the rest)) otherwise."""
    p = pattern
    if p.startswith("//"):
        p = p[1:]                                    # already absolute
    elif p.startswith("~/"):
        p = os.path.join(os.path.realpath(os.path.expanduser("~")), p[2:])
    elif p.startswith("*."):
        p = os.path.join(base, "**", p)              # anywhere in the folder
    else:
        p = os.path.join(os.path.realpath(base), p.lstrip("/"))
    if p.endswith("/**"):
        p = p[:-3]
    if "*" not in p:
        return "path", p
    root = p.split("*", 1)[0].rstrip("/") or "/"
    rx = re.escape(p[len(root):])
    rx = (rx.replace(r"/\*\*/", "/(?:.*/)?").replace(r"\*\*", ".*")
          .replace(r"\*", "[^/]*"))
    return "glob", (root, rx, p)


def _expand_glob(root, rx, _glob="", limit=400):
    """The files a glob matches today (Codex takes globs only for 'deny')."""
    out, pat = [], re.compile(rx + r"(?:/.*)?$")
    for dirpath, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for n in files + dirs:
            full = os.path.join(dirpath, n)
            if pat.match(full[len(root):]):
                out.append(full)
                if len(out) >= limit:
                    return out
    return out


# Codex takes a wildcard only to refuse a path outright, reads included. For
# most protected wildcards the files that exist today are listed one by one
# instead (a new launcher nobody runs is harmless). These ones are dangerous
# precisely when NEW, and no run needs to read them: a json.py at the top of
# the folder runs the next time a script imports json there (tested 5 Oct:
# without this, a Codex run could create one).
DENY_NEW = {"/*.py", "*.pth", "**/AGENTS.md", "**/GEMINI.md",
            # The same import trap a level down, and the files a run could
            # add to steer the next one (9 Oct audit).
            "brain/*.py", "/*/__init__.py", "brain/*/__init__.py",
            "**/CLAUDE.md", "**/.gitignore", "**/AGENTS.override.md", "**/.env"}


def _toml(s):
    return json.dumps(s)                  # a JSON string is a TOML basic string


def codex_profile(profile, cwd=ROOT):
    """A Codex permission profile for one run_policy profile, as the TOML
    inline table `-c permissions.brain=…` takes. Tested on Codex 0.160
    (5 Oct): folder writable, brain/tools and .git/hooks refused, the journal
    unreadable, no network, nothing written outside the folder."""
    base = os.path.realpath(ROOT if profile != "project" else cwd)
    reads, edits = RP.fences(profile, cwd)
    # Relative patterns are the brain's own files, wherever the run works:
    # resolved against a project folder, the brain's secrets went unfenced
    # (Claude's settings anchor them with _abs(p, ROOT); 9 Oct audit).
    home = os.path.realpath(ROOT)
    rules = {}

    def put(path, access):
        # deny beats read beats write when the same path comes up twice
        order = {"write": 0, "read": 1, "deny": 2}
        if order[access] >= order.get(rules.get(path), -1):
            rules[path] = access

    if profile in ("talk",):
        put(base, "read")
    elif profile == "readonly":
        put(base, "read")
        put(os.path.join(base, "brain", "drafts"), "write")
    else:
        put(base, "write")
        put(os.path.join(base, ".git"), "write")       # :workspace locks .git
    for pat in edits:
        kind, val = _resolve(pat, home)
        if kind == "path":
            put(val, "read")
        elif pat in DENY_NEW:
            put(val[2], "deny")
        else:
            for hit in _expand_glob(*val):
                put(hit, "read")
    for pat in reads:
        kind, val = _resolve(pat, home)
        if kind == "path":
            put(val, "deny")
        else:
            put(val[2], "deny")
    fs = ", ".join(f"{_toml(p)}={_toml(a)}" for p, a in sorted(rules.items()))
    # Codex's own :workspace makes the folder writable at the same weight as
    # a "read" here, and write wins a tie: the two look-only profiles start
    # from :read-only instead (tested 5 Oct, they could write before).
    start = ":read-only" if profile in ("talk", "readonly") else ":workspace"
    return ('{extends="' + start + '", filesystem={glob_scan_max_depth=8, '
            + fs + '}, network={enabled=false}}')


GEMINI_HOSTS = [
    # Signing in and the model itself: the hosts Gemini CLI calls with a
    # Google account or an AI Studio sign-in. Only Gemini's own process gets
    # through (_Proxy.allow_pid); a command it runs reaches nothing.
    "generativelanguage.googleapis.com", "cloudcode-pa.googleapis.com",
    "oauth2.googleapis.com", "www.googleapis.com", "accounts.google.com",
]
# Gemini's sign-in files. A command that swapped in someone else's login
# would have the run's conversation go to their account. The same list
# Gemini's own sandbox profiles refuse.
GEMINI_CREDS = ("oauth_creds.json", "google_accounts.json",
                "gemini-credentials.json", "mcp-oauth-tokens.json",
                "a2a-oauth-tokens.json", "trustedFolders.json",
                "trusted_hooks.json", "policy_integrity.json")


def _sb(s):
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _sb_regex(glob):
    """A glob as a sandbox-profile regex. Those strings are raw (a backslash
    escapes nothing: `\\.` matched no file in the 5 Oct test) and POSIX, so
    every special character goes in brackets and groups are plain."""
    out, i = "^", 0
    while i < len(glob):
        if glob.startswith("**/", i):
            out, i = out + "(.*/)?", i + 3
        elif glob.startswith("**", i):
            out, i = out + ".*", i + 2
        elif glob[i] == "*":
            out, i = out + "[^/]*", i + 1
        else:
            c = glob[i]
            out += c if c.isalnum() or c in "/_ -" else f"[{c}]"
            i += 1
    return out + "(/.*)?$"


def gemini_seatbelt(profile, cwd, port):
    """The Mac sandbox profile the whole Gemini process runs in. Later rules
    win in these profiles, so the order is: allow, then fence."""
    base = os.path.realpath(ROOT if profile != "project" else cwd)
    home = os.path.realpath(os.path.expanduser("~"))
    tmp = os.path.realpath(tempfile.gettempdir())
    reads, edits = RP.fences(profile, cwd)
    out = ["(version 1)", "(allow default)",
           "(deny network*)",
           f'(allow network-outbound (remote tcp "localhost:{port}"))',
           "(deny file-write*)",
           "(allow file-write*",
           f"  (subpath {_sb(tmp)}) (subpath \"/private/tmp\")",
           "  (subpath \"/private/var/folders\")",
           f"  (subpath {_sb(home + '/.gemini')}) (subpath {_sb(home + '/.cache')})",
           f"  (subpath {_sb(home + '/.npm')})",
           '  (literal "/dev/null") (literal "/dev/stdout") (literal "/dev/stderr")',
           '  (literal "/dev/dtracehelper") (regex #"^/dev/tty") (regex #"^/dev/fd/"))']
    if profile == "readonly":
        out.append(f"(allow file-write* (subpath {_sb(base + '/brain/drafts')}))")
    elif profile != "talk":
        out.append(f"(allow file-write* (subpath {_sb(base)}))")
    # Its own settings and policy files decide what the next run may do.
    out.append("(deny file-write* "
               + " ".join(f"(literal {_sb(home + '/.gemini/' + n)})"
                          for n in GEMINI_CREDS) + " "
               f"(literal {_sb(home + '/.gemini/settings.json')}) "
               f"(subpath {_sb(home + '/.gemini/policies')}) "
               f"(subpath {_sb(home + '/.gemini/extensions')}) "
               f"(literal {_sb(home + '/.gemini/.env')}) "
               f"(literal {_sb(home + '/.gemini/GEMINI.md')}))")

    def rule(pat):
        kind, val = _resolve(pat, os.path.realpath(ROOT))   # as codex_profile
        if kind == "path":
            return f"(subpath {_sb(val)})"
        return f'(regex #"{_sb_regex(val[2])}")'

    if edits:
        out.append("(deny file-write* " + " ".join(rule(p) for p in edits) + ")")
    if reads:
        out.append("(deny file-read* " + " ".join(rule(p) for p in reads) + ")")
    return "\n".join(out) + "\n"


def gemini_policy(profile):
    """Gemini's policy engine, at the admin tier so a user's own rules cannot
    loosen it. Anything not allowed here would ask, and a headless run
    cannot ask, so it is refused."""
    read = ["glob", "grep_search", "list_directory", "read_file",
            "read_many_files"]
    rules = [("allow", {"toolName": read})]
    if profile == "sealed":
        # llm.py's small jobs (complete()): no tools, as with Claude. The
        # talk policy gave the mail-task reader files and web search.
        rules = []
    if profile == "readonly":
        rules.append(("allow", {"toolName": "write_file",
                                "argsPattern": r'"file_path":"[^"]*brain/drafts/'}))
    elif profile != "talk":
        rules.append(("allow", {"toolName": ["write_file", "replace"]}))
        if RP.SANDBOX_OK:
            rules.append(("allow", {"toolName": "run_shell_command"}))
        else:
            # No Mac sandbox: the same short list run_policy gives Claude.
            for p in RP.BASH_ALLOW_NOSANDBOX:
                rules.append(("allow", {"toolName": "run_shell_command",
                                        "commandPrefix": p[5:-3]}))
    if profile in ("talk", "attended"):
        rules.append(("allow", {"toolName": "google_web_search"}))
    if profile == "sealed":
        rules = []
    deny = [("deny", {"toolName": "web_fetch"})]
    for p in RP.BASH_DENY:
        deny.append(("deny", {"toolName": "run_shell_command",
                              "commandPrefix": p[5:-3]}))
    lines = []
    for prio, group in ((100, rules), (900, deny)):
        for decision, r in group:
            lines.append("[[rule]]")
            for k, v in r.items():
                lines.append(f"{k} = {json.dumps(v)}")
            lines += [f'decision = "{decision}"', f"priority = {prio}", ""]
    return "\n".join(lines)


# ── the command a caller runs ──────────────────────────────────────────────

def argv(profile, prompt, cwd=ROOT, model="", resume="", fmt="stream-json",
         system="", name=None):
    """The command that runs `prompt` under `profile` with the chosen agent,
    printing Claude Code's events in `fmt` (stream-json | json | text).
    Not for Claude: callers keep their own Claude command."""
    name = name or provider()
    if name == "claude":
        raise ValueError("argv() is for the other agents")
    if not program(name):
        raise ValueError(missing(name))
    # -P: the folder a run can write never comes first on the import path.
    py = [sys.executable] + (["-P"] if sys.version_info >= (3, 11) else [])
    cmd = py + [os.path.abspath(__file__), "exec", name,
           profile, "--cwd", cwd, "--fmt", fmt]
    if model:
        cmd += ["--model", model]
    if resume:
        cmd += ["--resume", resume]
    if system:
        cmd += ["--system", system]
    return cmd + ["--", prompt]


def _codex_cmd(profile, cwd, prompt, model, resume, sealed=False):
    prog = program("codex")
    conf = ["-c", "permissions.brain=" + (
                '{extends=":read-only", filesystem={":minimal"="read", '
                '":workspace_roots"={"."="read"}}, network={enabled=false}}'
                if sealed else codex_profile(profile, cwd)),
            "-c", 'default_permissions="brain"',
            "-c", 'approval_policy="never"',
            "-c", 'web_search="%s"' % (
                "live" if profile in ("talk", "attended") and not sealed
                else "disabled"),
            "-c", 'project_doc_fallback_filenames=["CLAUDE.md"]',
            "-c", "project_doc_max_bytes=262144"]
    flags = ["--json", "--skip-git-repo-check", "--ignore-user-config",
             "--ignore-rules", "-C", cwd] + conf
    if sealed:
        flags.append("--ephemeral")
    if model:
        flags += ["-m", model]
    if resume:
        return prog + ["exec", "resume"] + flags + [resume, RP.safe_prompt(prompt)]
    return prog + ["exec"] + flags + [RP.safe_prompt(prompt)]


def _write_policy_file(name, text):
    os.makedirs(RP.POLICY_DIR, exist_ok=True)
    path = os.path.join(RP.POLICY_DIR, name)
    tmp = path + f".{os.getpid()}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, path)
    return path


def _gemini_cmd(profile, cwd, prompt, model, resume, port, tag):
    prog = program("gemini")
    pol = _write_policy_file(f"gemini-{tag}.toml", gemini_policy(profile))
    # Sealed is a policy, not a folder: its fences are talk's (read-only).
    profile = "talk" if profile == "sealed" else profile
    flags = ["-p", RP.safe_prompt(prompt), "--output-format", "stream-json",
             "--approval-mode", "default", "--admin-policy", pol,
             "--skip-trust", "--allowed-mcp-server-names", "none"]
    if model:
        flags += ["-m", model]
    flags += ["--resume", resume] if resume else []
    cmd = prog + flags
    if RP.SANDBOX_OK and sys.platform == "darwin":
        sb = _write_policy_file(f"gemini-{tag}.sb",
                                gemini_seatbelt(profile, cwd, port))
        cmd = ["/usr/bin/sandbox-exec", "-f", sb] + cmd
    return cmd


# ── the proxy Gemini talks through ─────────────────────────────────────────

def _peer_pids(port):
    """The processes holding a TCP connection on 127.0.0.1:port, from the
    Mac's own table (lsof), other than this one."""
    try:
        r = subprocess.run(["/usr/sbin/lsof", "-nP", f"-iTCP@127.0.0.1:{port}",
                            "-Fp"], capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return None
    pids = {int(ln[1:]) for ln in r.stdout.splitlines()
            if ln.startswith("p") and ln[1:].isdigit()}
    pids.discard(os.getpid())
    return pids


class _Proxy:
    """A CONNECT proxy on 127.0.0.1 that opens a tunnel only to the listed
    hosts, and only for one process. Inside the sandbox it is the one
    address the run can reach.

    WHY THE PROCESS CHECK. The sandbox cannot tell Gemini from a command
    Gemini runs: both may reach this port. Without the check, a command
    could send text to Google's API under a key someone planted in what the
    run read. So each connection is traced to the process that opened it
    and refused unless it is Gemini itself (allow_pid, a single process
    because GEMINI_CLI_NO_RELAUNCH stops it splitting in two). Tested
    5 Oct: Gemini still reaches Google; a child process of the allowed one
    is refused."""

    def __init__(self, hosts, allow_pid=None):
        self.hosts = {h.lower() for h in hosts}
        self.allow_pid = allow_pid
        self.sock = socket.socket()
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(32)
        self.port = self.sock.getsockname()[1]
        self.refused = []
        threading.Thread(target=self._serve, daemon=True).start()

    def _serve(self):
        while True:
            try:
                c, _ = self.sock.accept()
            except OSError:
                return
            threading.Thread(target=self._one, args=(c,), daemon=True).start()

    def _one(self, c):
        try:
            c.settimeout(30)
            head = b""
            while b"\r\n\r\n" not in head and len(head) < 8192:
                chunk = c.recv(4096)
                if not chunk:
                    return
                head += chunk
            line = head.split(b"\r\n", 1)[0].decode("latin-1")
            parts = line.split()
            if len(parts) < 2 or parts[0].upper() != "CONNECT":
                c.sendall(b"HTTP/1.1 405 Only CONNECT\r\n\r\n")
                return
            host, _, port = parts[1].rpartition(":")
            owner = _peer_pids(c.getpeername()[1])
            if not owner or owner != {self.allow_pid}:
                self.refused.append(parts[1] + " (not Gemini itself)")
                c.sendall(b"HTTP/1.1 403 Only the agent itself\r\n\r\n")
                return
            if host.lower() not in self.hosts or port != "443":
                self.refused.append(parts[1])
                c.sendall(b"HTTP/1.1 403 Not on the brain's list\r\n\r\n")
                return
            up = socket.create_connection((host, 443), timeout=30)
            c.sendall(b"HTTP/1.1 200 Connection established\r\n\r\n")
            c.settimeout(None)
            up.settimeout(None)
            socks = [c, up]
            while True:
                r, _, _ = select.select(socks, [], [], 300)
                if not r:
                    return
                for s in r:
                    data = s.recv(65536)
                    if not data:
                        return
                    (up if s is c else c).sendall(data)
        except OSError:
            pass
        finally:
            c.close()

    def close(self):
        try:
            self.sock.close()
        except OSError:
            pass


# ── translating their events into Claude Code's ────────────────────────────

SHORT = {"run_shell_command": "Bash", "write_file": "Write", "replace": "Edit",
         "read_file": "Read", "read_many_files": "Read", "glob": "Glob",
         "grep_search": "Grep", "list_directory": "LS",
         "google_web_search": "WebSearch", "web_fetch": "WebFetch"}


class _Out:
    """Writes Claude Code's event shapes in the format the caller asked for,
    and keeps what the final result needs."""

    def __init__(self, fmt, name):
        self.fmt, self.name = fmt, name
        self.sid, self.model = "", ""
        self.texts, self.error, self.turns = [], "", 0
        self.usage = {"input_tokens": 0, "output_tokens": 0,
                      "cache_read_input_tokens": 0}
        self.started = time.time()

    def emit(self, ev):
        if self.fmt == "stream-json":
            sys.stdout.write(json.dumps(ev) + "\n")
            sys.stdout.flush()

    def init(self, sid, model=""):
        self.sid, self.model = sid or self.sid, model or self.model
        self.emit({"type": "system", "subtype": "init",
                   "session_id": self.sid, "model": self.model,
                   "agent": self.name})

    def text(self, t):
        t = (t or "").strip()
        if t:
            self.texts.append(t)
            self.emit({"type": "assistant", "message": {"content": [
                {"type": "text", "text": t}]}})

    def delta(self, t):
        self.emit({"type": "stream_event", "event": {
            "type": "content_block_delta",
            "delta": {"type": "text_delta", "text": t}}})

    def tool(self, tid, name, inp):
        self.turns += 1
        self.emit({"type": "assistant", "message": {"content": [
            {"type": "tool_use", "id": tid, "name": name, "input": inp}]}})

    def tool_result(self, tid, body, bad=False):
        self.emit({"type": "user", "message": {"content": [
            {"type": "tool_result", "tool_use_id": tid,
             "content": str(body or "")[:4000], "is_error": bool(bad)}]}})

    def finish(self, code):
        bad = bool(code) or (bool(self.error) and not self.texts)
        result = (self.texts[-1] if self.texts and not bad
                  else (self.error or (self.texts[-1] if self.texts else ""))
                  or f"{NAMES[self.name]} stopped (exit {code})")
        ev = {"type": "result", "subtype": "error" if bad else "success",
              "is_error": bad, "result": result, "session_id": self.sid,
              "duration_ms": int((time.time() - self.started) * 1000),
              "num_turns": self.turns, "usage": self.usage,
              "total_cost_usd": None,
              "model": f"{self.name}:{self.model}" if self.model else self.name}
        if self.fmt == "stream-json":
            self.emit(ev)
        elif self.fmt == "json":
            sys.stdout.write(json.dumps(ev) + "\n")
        else:
            sys.stdout.write(result + "\n")
        sys.stdout.flush()
        return 1 if bad else 0


def _codex_event(out, ev):
    t = ev.get("type")
    if t == "thread.started":
        out.init(ev.get("thread_id") or "")
    elif t in ("item.started", "item.completed"):
        it = ev.get("item") or {}
        kind, iid = it.get("type"), it.get("id") or ""
        if kind == "agent_message" and t == "item.completed":
            out.text(it.get("text"))
        elif kind == "command_execution":
            if t == "item.started":
                out.tool(iid, "Bash", {"command": it.get("command") or ""})
            else:
                out.tool_result(iid, it.get("aggregated_output"),
                                (it.get("exit_code") or 0) != 0
                                or it.get("status") == "failed")
        elif kind == "file_change" and t == "item.completed":
            for i, ch in enumerate(it.get("changes") or []):
                tid = f"{iid}-{i}"
                out.tool(tid, "Write" if ch.get("kind") == "add" else "Edit",
                         {"file_path": ch.get("path") or ""})
                out.tool_result(tid, ch.get("kind") or "changed",
                                it.get("status") == "failed")
        elif kind == "web_search" and t == "item.completed":
            out.tool(iid, "WebSearch", {"query": it.get("query") or ""})
        elif kind == "mcp_tool_call" and t == "item.completed":
            out.tool(iid, str(it.get("tool") or "tool"), {})
        elif kind == "error" and t == "item.completed":
            out.error = str(it.get("message") or "")[:300]
    elif t == "turn.completed":
        u = ev.get("usage") or {}
        cached = u.get("cached_input_tokens") or 0
        out.usage["input_tokens"] += max(0, (u.get("input_tokens") or 0) - cached)
        out.usage["cache_read_input_tokens"] += cached
        out.usage["output_tokens"] += u.get("output_tokens") or 0
        out.error = ""
    elif t in ("turn.failed", "thread.failed"):
        out.error = str((ev.get("error") or {}).get("message")
                        or "the run failed")[:300]
    elif t == "error":
        out.error = str(ev.get("message") or "")[:300]


def _gemini_event(out, ev, buf):
    t = ev.get("type")
    if t == "init":
        out.init(ev.get("session_id") or "", ev.get("model") or "")
    elif t == "message" and ev.get("role") == "assistant":
        piece = ev.get("content") or ""
        buf.append(piece)
        out.delta(piece)
    elif t in ("tool_use", "tool_result", "result", "error"):
        if buf:
            out.text("".join(buf))
            buf.clear()
        if t == "tool_use":
            name = ev.get("tool_name") or "tool"
            p = ev.get("parameters") or {}
            inp = dict(p)
            for k in ("absolute_path", "path", "file_path"):
                if p.get(k):
                    inp["file_path"] = p[k]
                    break
            out.tool(ev.get("tool_id") or "", SHORT.get(name, name), inp)
        elif t == "tool_result":
            out.tool_result(ev.get("tool_id") or "",
                            ev.get("output") or (ev.get("error") or {}).get("message"),
                            ev.get("status") == "error")
        elif t == "error" and ev.get("severity") == "error":
            out.error = str(ev.get("message") or "")[:300]
        elif t == "result":
            s = ev.get("stats") or {}
            cached = s.get("cached") or s.get("cached_input_tokens") or 0
            out.usage["input_tokens"] += max(0, (s.get("input_tokens")
                                                 or s.get("input") or 0) - cached)
            out.usage["cache_read_input_tokens"] += cached
            out.usage["output_tokens"] += (s.get("output_tokens")
                                           or s.get("output") or 0)
            if ev.get("status") == "error":
                out.error = str((ev.get("error") or {}).get("message")
                                or "the run failed")[:300]


def _warm_weather():
    """Commands in a Codex or Gemini run reach no network at all (Claude's
    sandbox lets the weather service through), so the plan's weather is
    fetched here first, outside the run, and the run's own weather.py call
    lands on the hour-long cache. The morning script does the same for the
    calendar."""
    try:
        subprocess.run([sys.executable, os.path.join(HERE, "weather.py")],
                       cwd=ROOT, stdin=subprocess.DEVNULL,
                       capture_output=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        pass


def run(name, profile, prompt, cwd=ROOT, model="", resume="",
        fmt="stream-json", system=""):
    """Run one prompt with Codex or Gemini and print Claude Code's events.
    Returns the exit code."""
    if re.match(r"\s*/(today|brief)\b", prompt or "") and profile != "project":
        _warm_weather()
    prompt = expand(prompt)
    if name == "gemini" and os.path.exists(os.path.join(cwd, "CLAUDE.md")):
        # Codex is told to load CLAUDE.md through its own setting. Gemini's
        # equivalent lives only in settings files it trusts from an
        # administrator's folder (5 Oct), so it is told in words instead.
        prompt = ("Before anything else, read CLAUDE.md at the top of this "
                  "folder. It is this folder's standing instructions; it was "
                  "written for Claude and applies to you the same way.\n\n"
                  + prompt)
    if system:
        prompt = ("Standing instructions for this conversation:\n" + system
                  + "\n\n---\n\n" + prompt)
    out = _Out(fmt, name)
    proxy = None
    tag = f"{profile}-{os.getpid()}"
    try:
        if name == "codex":
            cmd = (_codex_cmd("talk", cwd, prompt, model, resume, sealed=True)
                   if profile == "sealed" else
                   _codex_cmd(profile, cwd, prompt, model, resume))
            e = env("codex")
        else:
            proxy = _Proxy(GEMINI_HOSTS)
            cmd = _gemini_cmd(profile, cwd, prompt, model, resume,
                              proxy.port, tag)
            e = env("gemini")
            e["GEMINI_CLI_NO_RELAUNCH"] = "true"   # one process, one pid
            if sys.platform == "darwin":
                e.update({k: f"http://127.0.0.1:{proxy.port}" for k in (
                    "HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy")})
                e.pop("NO_PROXY", None)
                e.pop("no_proxy", None)
        child = subprocess.Popen(cmd, cwd=cwd, stdin=subprocess.DEVNULL,
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                 text=True, encoding="utf-8", errors="replace",
                                 env=e)
    except (OSError, ValueError) as exc:
        out.error = str(exc)
        return out.finish(1)
    if proxy:
        # sandbox-exec, env and node each replace the one before in place,
        # so the pid started here is the pid that ends up running Gemini.
        proxy.allow_pid = child.pid

    def stop(*_):
        try:
            child.terminate()
        except OSError:
            pass
    signal.signal(signal.SIGTERM, stop)
    # run_policy's ceiling for scheduled runs (LIFEBRAIN_RUN_TIMEOUT): it
    # stopped only Claude runs, and a hung Codex run reported success.
    over = []
    limit = int(os.environ.get("LIFEBRAIN_RUN_TIMEOUT") or 0)
    if limit:
        timer = threading.Timer(limit, lambda: (over.append(1), stop()))
        timer.daemon = True
        timer.start()
    if hasattr(signal, "SIGHUP"):
        signal.signal(signal.SIGHUP, stop)
    errs = []
    threading.Thread(target=lambda: errs.extend(child.stderr), daemon=True).start()
    buf = []
    for line in child.stdout:
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        if name == "codex":
            _codex_event(out, ev)
        else:
            _gemini_event(out, ev, buf)
    code = child.wait()
    if over:
        out.error = f"stopped after {limit // 60} minutes with no end in sight"
        code = 124
    if buf:
        out.text("".join(buf))
    if code and not out.error:
        tail = [x.strip() for x in errs if x.strip()][-3:]
        out.error = (" ".join(tail) or f"exit {code}")[:300]
    if proxy:
        if proxy.refused:
            sys.stderr.write("agents: refused " + ", ".join(
                sorted(set(proxy.refused))[:8]) + "\n")
        proxy.close()
    for n in (f"gemini-{tag}.toml", f"gemini-{tag}.sb"):
        try:
            os.remove(os.path.join(RP.POLICY_DIR, n))
        except OSError:
            pass
    return out.finish(code)


def complete(prompt, system="", timeout=90, model="", name=None):
    """One sealed, no-file completion for llm.py: an empty temp folder, nothing
    readable beyond the system's own files, no network for commands. Returns
    (text, usage)."""
    name = name or provider()
    with tempfile.TemporaryDirectory() as td:
        full = (("Instructions:\n" + system + "\n\n---\n\n") if system
                else "") + prompt + (
            "\n\n(Answer directly in text. Do not run commands or open files.)")
        if name == "codex":
            cmd = _codex_cmd("talk", td, full, model, "", sealed=True)
        else:
            cmd = argv("sealed", full, cwd=td, model=model, fmt="json",
                       name="gemini")
        try:
            r = subprocess.run(cmd, cwd=td, stdin=subprocess.DEVNULL,
                               capture_output=True, text=True,
                               encoding="utf-8", errors="replace",
                               timeout=timeout, env=env(name))
        except subprocess.TimeoutExpired:
            raise ValueError("that took too long, try again")
    out = _Out("collect", name)
    for line in (r.stdout or "").splitlines():
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        if name == "codex":
            _codex_event(out, ev)
        elif ev.get("type") == "result":
            if ev.get("is_error"):
                raise ValueError("model call failed: " + str(ev.get("result"))[:160])
            out.texts.append(str(ev.get("result") or ""))
            out.usage = ev.get("usage") or out.usage
    text = (out.texts[-1] if out.texts else "").strip()
    if not text:
        raise ValueError("model call failed: " + (out.error or (r.stderr or "")
                                                  .strip()[-160:] or "empty reply"))
    return text, out.usage


# ── run_policy.py run, for the shell scripts ───────────────────────────────

def cli_run(profile, args):
    """`run_policy.py run <profile> -- <claude flags>` from morning.sh and
    night.sh, carried over: -p, --model and --output-format are read; the
    rest are Claude's and dropped."""
    prompt, model, fmt, i = "", "", "text", 0
    while i < len(args):
        a = args[i]
        if a in ("-p", "--print") and i + 1 < len(args):
            prompt, i = args[i + 1], i + 2
            continue
        if a == "--model" and i + 1 < len(args):
            model, i = args[i + 1], i + 2
            continue
        if a == "--output-format" and i + 1 < len(args):
            fmt, i = args[i + 1], i + 2
            continue
        i += 1
    tier = next((t for t in TIERS if t in (model or "").lower()), "")
    return run(provider(), profile, prompt, ROOT,
               model_for(tier) if tier else "", fmt=fmt)


def main(argv_):
    if argv_[:1] == ["exec"] and len(argv_) >= 3:
        name, profile, rest = argv_[1], argv_[2], argv_[3:]
        opts = {"--cwd": ROOT, "--fmt": "stream-json", "--model": "",
                "--resume": "", "--system": ""}
        while rest and rest[0] != "--":
            if rest[0] in opts and len(rest) > 1:
                opts[rest[0]] = rest[1]
                rest = rest[2:]
            else:
                rest = rest[1:]
        prompt = " ".join(rest[1:])
        return run(name, profile, prompt, opts["--cwd"], opts["--model"],
                   opts["--resume"], opts["--fmt"], opts["--system"])
    if argv_[:1] == ["use"] and len(argv_) >= 2:
        models = {}
        for i, a in enumerate(argv_):
            if a == "--model" and i + 1 < len(argv_) and "=" in argv_[i + 1]:
                k, v = argv_[i + 1].split("=", 1)
                models[k.strip()] = v.strip()
        try:
            data = use(argv_[1], models)
        except ValueError as exc:
            print(exc, file=sys.stderr)
            return 2
        print(f"The brain now runs {NAMES[data['provider']]}.")
        if not program(data["provider"]):
            print(missing(data["provider"]))
        # The page names the agent in its wording (say()), so it is rebuilt
        # now rather than at the next change.
        subprocess.run([sys.executable, os.path.join(HERE, "rebuild.py")],
                       cwd=ROOT, stdout=subprocess.DEVNULL)
        return 0
    if argv_[:1] == ["check"]:
        # For the setup checkers: is the agent this brain runs installed?
        name = provider()
        if program(name):
            print(f"  [ OK ]  {NAMES[name]} is installed, and the brain runs it.")
            return 0
        print(f"  [MISSING]  {NAMES[name]}, the agent this brain is set to run")
        print("")
        print("      The page still works without it, but the brain will")
        print("      not maintain itself.")
        print("")
        import textwrap
        print(textwrap.fill(INSTALL[name], 58, initial_indent="      ",
                            subsequent_indent="      "))
        others = [n for n in NAMES if n != name and program(n)]
        if others:
            print("")
            print(f"      Or use {NAMES[others[0]]}, which is installed: type")
            print(f"          python3 brain/tools/agents.py use {others[0]}")
        print("")
        print("      Already installed it? Close this window, open a NEW")
        print("      one, and run this check again.")
        print("")
        return 1
    if argv_[:1] == ["show"] and len(argv_) >= 3:
        name, profile = argv_[1], argv_[2]
        if name == "codex":
            print(" ".join(_codex_cmd(profile, ROOT, "<prompt>", "", "")))
        elif name == "gemini":
            print(gemini_policy(profile))
            print(gemini_seatbelt(profile, ROOT, 0))
        return 0
    c = choice()
    print(f"The brain runs: {NAMES[c['provider']]}")
    for n, ok in installed().items():
        print(f"  {NAMES[n]:<12} {'installed' if ok else 'not installed'}")
    if c["models"]:
        print("  models: " + ", ".join(f"{k}={v}" for k, v in c["models"].items()))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

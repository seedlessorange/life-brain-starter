#!/usr/bin/env python3
"""Route the small no-tool jobs to a model — decided once, here.

The brain has two kinds of model call. The heavy runs (/queue, /wrap,
/today) are Claude Code with tools, and they stay Claude: a cheaper model
quietly rotting the life-admin is the one failure this system exists to
prevent. But the small jobs — rewording one draft, naming a conversation —
are a prompt in, a short text out, no tools, no files. Those can run on a
local model just as well, for free, without the text leaving the machine.

Config, under `"llm"` in brain/config.json:

    "llm": {
      "provider": "claude",                  claude | ollama — the default route
      "model": "haiku",                      which Claude: haiku | sonnet | opus | fable
      "ollama": {
        "model": "",                         e.g. "llama3.2" — required to route here
        "url": "http://127.0.0.1:11434"      where Ollama listens
      },
      "jobs": {},                            per-job route, e.g. {"revise": "ollama"}
      "models": {}                           per-job model, e.g. {"books": "sonnet"}
    }

Job names in use: "revise" (draft rewording, serve.py), "name"
(conversation naming, sessions.py), "news" (the briefing's finance
breakdown, news.py), "school" (dates read out of class slides,
school.py) and "books" (reading a course book, books.py). The
fallback is always Claude: if
Ollama is down, not installed, or has no model configured, the call goes
to Claude exactly as before and the caller never notices. Friends without
a GPU never flip the setting and nothing changes for them — the package
ships code, never config values.

Ollama installs in one step on Mac/Windows/Linux (https://ollama.com),
then `ollama pull llama3.2` and set the model name above.
"""

import json
import os
import shutil
import subprocess
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
BRAIN = os.path.dirname(HERE)

DEFAULT_OLLAMA_URL = "http://127.0.0.1:11434"


def _cfg():
    try:
        with open(os.path.join(BRAIN, "config.json"), encoding="utf-8") as f:
            return (json.load(f) or {}).get("llm") or {}
    except Exception:
        return {}


def provider_for(job):
    """'ollama' or 'claude' — anything unrecognised is claude."""
    llm = _cfg()
    p = ((llm.get("jobs") or {}).get(job) or llm.get("provider") or "claude")
    return "ollama" if str(p).strip().lower() == "ollama" else "claude"


CLAUDE_MODELS = ("haiku", "sonnet", "opus", "fable")
DEFAULT_MODEL = "haiku"


def model_for(job):
    """Which Claude answers a small job.

    `llm.model` sets it for all of them; `llm.models` overrides per job, e.g.
    {"books": "sonnet", "revise": "haiku"}. The shipped default is Haiku,
    because a stranger cloning this repo may be on a small plan and a
    one-line draft reword does not need more. On a subscription with room,
    setting this to sonnet is the right call: these jobs are reading and
    judgement, not string manipulation, and that is where the difference
    shows."""
    llm = _cfg()
    m = ((llm.get("models") or {}).get(job) or llm.get("model")
         or DEFAULT_MODEL)
    m = str(m).strip().lower()
    return m if m in CLAUDE_MODELS else DEFAULT_MODEL


# Callers that already write their own ledger line; the rest are recorded
# here, so the Usage page finally sees the guides, slides and news calls.
SELF_RECORDED = {"name", "revise"}


def _record(job, out, started, ok=True):
    if job in SELF_RECORDED:
        return
    try:
        import time
        import usage
        usage.record("llm", job, model=(out or {}).get("model") or "",
                     usage=(out or {}).get("usage"),
                     secs=time.time() - started, ok=ok)
    except Exception:
        pass


def complete(job, prompt, system="", timeout=90, env=None, model=None):
    """One no-tool completion. Returns a dict:

        {"text": ..., "provider": "claude"|"ollama", "model": ...,
         "usage": {"input_tokens": n, "output_tokens": n}}

    plus a "note" key when Ollama was configured but Claude had to step in.
    Raises ValueError (with a message fit for the page) when no provider
    can answer.
    """
    import time
    started = time.time()
    note = ""
    if provider_for(job) == "ollama":
        try:
            return _ollama(_cfg().get("ollama") or {}, prompt, system, timeout)
        except Exception as exc:
            # Ollama being off is normal (machine rebooted, model not
            # pulled) — the job still has to finish, so Claude takes it.
            note = f"ollama unavailable ({exc.__class__.__name__}), used Claude"
    try:
        out = _claude(prompt, system, timeout, env, model or model_for(job))
    except ValueError:
        _record(job, {"model": model or model_for(job),
                      "usage": {"input_tokens": len(prompt) // 4}},
                started, ok=False)
        raise
    _record(job, out, started)
    if note:
        out["note"] = note
    return out


def complete_images(job, prompt, images, system="", timeout=300, model=None):
    """One no-tool completion over pictures: `images` is [(label, png path)],
    each label sent just before its image, then the prompt. Same return
    shape as complete(), with real token counts.

    Claude only. The CLI takes images through its stream-json input, which
    keeps the call exactly as sealed as a text one: no tools, a temp dir, her
    subscription. Ollama is skipped even when routed — a local text model
    cannot see."""
    import base64
    import tempfile
    import time
    started = time.time()
    import run_policy as RP
    claude = RP.claude_path()
    if not claude:
        raise ValueError(RP.claude_missing())
    content = []
    for label, path in images:
        with open(path, "rb") as f:
            data = base64.b64encode(f.read()).decode()
        if label:
            content.append({"type": "text", "text": label})
        content.append({"type": "image", "source": {
            "type": "base64", "media_type": "image/png", "data": data}})
    content.append({"type": "text", "text": prompt})
    msg = {"type": "user", "message": {"role": "user", "content": content}}
    env = dict(os.environ)
    env.pop("ANTHROPIC_API_KEY", None)
    env.pop("ANTHROPIC_AUTH_TOKEN", None)
    model = model or model_for(job)
    args = [claude, "-p", "--input-format", "stream-json",
            "--output-format", "stream-json", "--verbose",
            "--tools", "", "--model", model] + ISOLATE
    if system:
        args += ["--system-prompt", system]
    try:
        with tempfile.TemporaryDirectory() as td:
            r = subprocess.run(args, input=json.dumps(msg) + "\n", cwd=td,
                               capture_output=True, text=True,
                               timeout=timeout, env=env)
    except subprocess.TimeoutExpired:
        raise ValueError("that took too long — try again")
    result = None
    for line in (r.stdout or "").splitlines():
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        if ev.get("type") == "result":
            result = ev
    if r.returncode != 0 or not result or result.get("is_error"):
        why = (result or {}).get("result") or r.stderr or ""
        raise ValueError("model call failed: " + str(why).strip()[:160])
    text = (result.get("result") or "").strip()
    if not text:
        raise ValueError("got an empty reply back")
    u = result.get("usage") or {}
    out = {"text": text, "provider": "claude", "model": model,
           "usage": {"input_tokens": (u.get("input_tokens") or 0)
                     + (u.get("cache_read_input_tokens") or 0)
                     + (u.get("cache_creation_input_tokens") or 0),
                     "output_tokens": u.get("output_tokens") or 0}}
    _record(job, out, started)
    return out


# `--tools ""` removes the built-in tools only. Without these flags the call
# would still load her user settings (the global bypass default, plugins,
# hooks) and every MCP server she has, while reading mail bodies and articles.
ISOLATE = ["--setting-sources", "", "--strict-mcp-config",
           "--permission-mode", "dontAsk"]


def _ollama_url(cfg):
    """Ollama runs on this machine. config.json is writable by the brain's own
    Claude runs, so an address anywhere else would let one injected run
    route every later draft and mail prompt to a server of its choosing."""
    from urllib.parse import urlsplit
    url = (cfg.get("url") or DEFAULT_OLLAMA_URL).rstrip("/")
    try:
        host = (urlsplit(url).hostname or "").lower()
    except ValueError:
        host = ""
    if host not in ("127.0.0.1", "localhost", "::1"):
        raise ValueError("the Ollama address must be on this Mac (127.0.0.1)")
    return url


def _ollama(cfg, prompt, system, timeout):
    model = (cfg.get("model") or "").strip()
    if not model:
        raise ValueError("no ollama model configured")
    url = _ollama_url(cfg) + "/api/generate"
    body = json.dumps({"model": model, "prompt": prompt, "system": system,
                       "stream": False}).encode("utf-8")
    req = urllib.request.Request(
        url, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = json.load(r)
    text = (data.get("response") or "").strip()
    if not text:
        raise ValueError("empty response")
    return {"text": text, "provider": "ollama", "model": "ollama:" + model,
            "usage": {"input_tokens": data.get("prompt_eval_count")
                      or len(prompt) // 4,
                      "output_tokens": data.get("eval_count")
                      or len(text) // 4}}


def _claude(prompt, system, timeout, env, model=DEFAULT_MODEL):
    """No tools, from a temp dir so no CLAUDE.md and no file reads happen.
    Which Claude answers is model_for(job) — see there."""
    import run_policy as RP
    claude = RP.claude_path()
    if not claude:
        raise ValueError(RP.claude_missing())
    import tempfile
    # Her subscription, never an API key. A key another project exported into
    # the shell would otherwise be picked up by the CLI and billed silently —
    # the brain's rule is that its runs spend the plan she pays for.
    env = dict(env if env is not None else os.environ)
    env.pop("ANTHROPIC_API_KEY", None)
    env.pop("ANTHROPIC_AUTH_TOKEN", None)
    try:
        with tempfile.TemporaryDirectory() as td:
            r = subprocess.run(
                [claude, "-p", prompt, "--output-format", "text",
                 "--system-prompt", system, "--tools", "", "--model", model]
                + ISOLATE,
                cwd=td, stdin=subprocess.DEVNULL, capture_output=True,
                text=True, timeout=timeout, env=env)
    except subprocess.TimeoutExpired:
        raise ValueError("that took too long — try again")
    if r.returncode != 0:
        raise ValueError("model call failed: " + (r.stderr or "").strip()[:160])
    text = (r.stdout or "").strip()
    if not text:
        raise ValueError("got an empty reply back")
    # --output-format text carries no usage block, so sizes are estimated
    # from the characters that actually moved.
    return {"text": text, "provider": "claude", "model": model,
            "usage": {"input_tokens": len(prompt) // 4,
                      "output_tokens": len(text) // 4}}

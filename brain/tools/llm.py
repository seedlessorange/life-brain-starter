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
      "ollama": {
        "model": "",                         e.g. "llama3.2" — required to route here
        "url": "http://127.0.0.1:11434"      where Ollama listens
      },
      "jobs": {}                             per-job override, e.g. {"revise": "ollama"}
    }

Job names in use: "revise" (draft rewording, serve.py), "name"
(conversation naming, sessions.py) and "news" (the briefing's finance
breakdown, news.py). The fallback is always Claude: if
Ollama is down, not installed, or has no model configured, the call goes
to Haiku exactly as before and the caller never notices. Friends without
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


def complete(job, prompt, system="", timeout=90, env=None):
    """One no-tool completion. Returns a dict:

        {"text": ..., "provider": "claude"|"ollama", "model": ...,
         "usage": {"input_tokens": n, "output_tokens": n}}

    plus a "note" key when Ollama was configured but Claude had to step in.
    Raises ValueError (with a message fit for the page) when no provider
    can answer.
    """
    note = ""
    if provider_for(job) == "ollama":
        try:
            return _ollama(_cfg().get("ollama") or {}, prompt, system, timeout)
        except Exception as exc:
            # Ollama being off is normal (machine rebooted, model not
            # pulled) — the job still has to finish, so Claude takes it.
            note = f"ollama unavailable ({exc.__class__.__name__}), used Claude"
    out = _claude(prompt, system, timeout, env)
    if note:
        out["note"] = note
    return out


def _ollama(cfg, prompt, system, timeout):
    model = (cfg.get("model") or "").strip()
    if not model:
        raise ValueError("no ollama model configured")
    url = (cfg.get("url") or DEFAULT_OLLAMA_URL).rstrip("/") + "/api/generate"
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


def _claude(prompt, system, timeout, env):
    """The original path: Haiku, no tools, from a temp dir so no CLAUDE.md
    and no file reads happen. A one-line tweak should cost cents."""
    claude = shutil.which("claude") or shutil.which("claude.cmd")
    if not claude:
        raise ValueError("Claude Code is not installed, or not on your PATH.")
    import tempfile
    try:
        with tempfile.TemporaryDirectory() as td:
            r = subprocess.run(
                [claude, "-p", prompt, "--output-format", "text",
                 "--system-prompt", system, "--tools", "", "--model", "haiku"],
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
    return {"text": text, "provider": "claude", "model": "haiku",
            "usage": {"input_tokens": len(prompt) // 4,
                      "output_tokens": len(text) // 4}}

#!/usr/bin/env python3
"""Short clips to words, fast: the voice's ears.

    python3 brain/tools/hear.py some-clip.m4a        # prints what was said

One Whisper stays loaded in a worker process (hear_worker.py) and every
short clip goes through it: the talk orb, dictation on the page, and a
spoken question on Telegram. Long recordings keep their own path
(transcribe.py), which files a transcript and takes its time.

Nothing here downloads a model. The worker runs with the Hugging Face hub
offline, so a model named in config that is not already on this Mac fails
with a plain message instead of pulling gigabytes unasked.

Config, under "voice" in brain/config.json:
    "whisper_model": ""      empty = the model transcribe.py already uses
    "keep_warm_minutes": 10  how long the model stays loaded after a clip
"""
import json
import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
BRAIN = os.path.dirname(HERE)
sys.path.insert(0, HERE)

from warm import Warm  # noqa: E402

# What Whisper says when it hears nothing: subtitle credits and sign-offs it
# learned from film soundtracks. A clip that is only this is a clip of silence.
PHANTOMS = {
    "thank you", "thank you.", "thanks for watching!", "thanks for watching.",
    "you", "bye.", "bye", ".", "merci.", "merci", "merci d'avoir regardé.",
    "sous-titres réalisés para la communauté d'amara.org",
    "sous-titres réalisés par la communauté d'amara.org",
    "sous-titrage st' 501", "sous-titrage société radio-canada",
}


def _cfg():
    try:
        with open(os.path.join(BRAIN, "config.json"), encoding="utf-8") as f:
            return (json.load(f) or {}).get("voice") or {}
    except Exception:
        return {}


def model():
    import transcribe as TR
    return (_cfg().get("whisper_model") or "").strip() or TR.MODEL


def _python():
    """The interpreter mlx_whisper is installed in, read from the first line
    of its own launcher — the server's Python usually does not have it."""
    import transcribe as TR
    exe = TR._bin("mlx_whisper")
    if not exe:
        return ""
    try:
        with open(exe, "rb") as f:
            first = f.readline().decode("utf-8", "replace").strip()
    except OSError:
        first = ""
    if first.startswith("#!"):
        py = first[2:].strip().split()[0] if first[2:].strip() else ""
        if py and os.path.basename(py) != "env" and os.path.exists(py):
            return py
    cand = os.path.join(os.path.dirname(exe), "python")
    return cand if os.path.exists(cand) else ""


def _argv():
    py = _python()
    if not py:
        raise ValueError("no Whisper on this Mac — mlx_whisper is needed")
    idle = max(1.0, float(_cfg().get("keep_warm_minutes") or 10)) * 60
    return [py, os.path.join(HERE, "hear_worker.py"), str(int(idle)), model()]


_W = Warm(_argv, env={"HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1",
                      "TOKENIZERS_PARALLELISM": "false"})


def warm():
    """Load the model now, in the background, so the next clip is quick.
    Called when the talk panel opens: she is about to speak."""
    _W.warm()


def is_warm():
    return _W.alive()


def _kill():
    _W.kill()


def _to_wav(path, dest):
    import transcribe as TR
    ff = TR._bin("ffmpeg")
    if not ff:
        raise ValueError("ffmpeg is needed to read the recording")
    r = subprocess.run([ff, "-y", "-v", "error", "-i", path, "-ar", "16000",
                        "-ac", "1", "-c:a", "pcm_s16le", dest],
                       capture_output=True, timeout=90)
    if r.returncode != 0 or not os.path.exists(dest):
        raise ValueError("could not decode the recording")


def transcribe(path, language=None, prompt=None, timeout=180):
    """Any audio file in, (text, language) out. Empty text means silence."""
    with tempfile.TemporaryDirectory() as td:
        wav = os.path.join(td, "a.wav")
        _to_wav(path, wav)
        try:
            res = _W.ask({"path": wav, "language": language or "",
                          "prompt": prompt or ""}, timeout=timeout)
        except ValueError as exc:
            why = str(exc)
            if any(w in why.lower() for w in ("offline", "not found",
                                               "does not appear", "could not load")):
                why = (f"the model {model()} is not on this Mac yet — "
                       "download it once, or clear voice.whisper_model")
            raise ValueError("Whisper: " + why[:200])
    text = " ".join((res.get("text") or "").split())
    if text.lower().strip(" .!") in {p.strip(" .!") for p in PHANTOMS}:
        text = ""
    # A loop is not speech: one fragment said six times running, or a short
    # clip that is one word over and over ("инструмент инструмент инструмент").
    if re.search(r"(.{2,14}?)(?:\s*\1){5,}", text, re.I):
        text = ""
    words = [w.lower().strip(".,!?;:") for w in text.split()]
    if len(words) >= 3 and len(set(words)) <= max(1, len(words) // 3):
        text = ""
    # Noise that Whisper took for a language she does not speak (Russian,
    # 29 Sep) is noise. voice.languages lists hers; empty lets any through.
    langs = _cfg().get("languages")
    langs = [str(x).lower() for x in (["en", "fr", "es"] if langs is None else langs)]
    if text and langs and (res.get("language") or "") not in langs:
        text = ""
    return text, (res.get("language") or "")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(0)
    import time
    for p in sys.argv[1:]:
        t = time.time()
        words, lang = transcribe(p)
        print(f"[{lang} {time.time() - t:.1f}s] {words}")

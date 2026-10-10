#!/usr/bin/env python3
"""Short clips to words, fast: the voice's ears.

    python3 brain/tools/hear.py some-clip.m4a        # prints what was said

One Whisper stays loaded in a worker process (hear_worker.py) and every
short clip goes through it: the talk orb, dictation on the page, and a
spoken question on Telegram. Long recordings keep their own path
(transcribe.py), which files a transcript and takes its time.

Two engines, the same pair transcribe.py uses. An Apple-silicon Mac with
mlx_whisper and ffmpeg gets the quick one. Any other computer, or a Mac
without those two, uses faster-whisper, which reads the browser's recording
itself and needs no ffmpeg. A friend's Mac with neither showed "ffmpeg is
needed to read the recording" under the orb (8 Oct): now the orb names the
one command that sets talking up, before anyone speaks.

Nothing here downloads a model while she talks. The worker runs with the
Hugging Face hub offline, so a model named in config that is not already on
this Mac fails with a plain message instead of pulling gigabytes unasked.
The download happens once, when the owner runs:

    python3 brain/tools/hear.py --setup    # install and fetch what talking needs
    python3 brain/tools/hear.py --check    # one line: can this computer hear?

Config, under "voice" in brain/config.json:
    "whisper_model": ""      empty = the model transcribe.py already uses
    "keep_warm_minutes": 10  how long the model stays loaded after a clip
faster-whisper's size comes from BRAIN_WHISPER_MODEL, as for voice memos
(default "small").
"""
import json
import os
import re
import subprocess
import sys
import tempfile
import threading

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
    "dimatorzok",      # all that is left of a Russian subtitle credit
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


def engine():
    """Which ears this computer has: "mlx" (an Apple-silicon Mac with
    mlx_whisper and ffmpeg), "fw" (faster-whisper, any computer), or ""."""
    import transcribe as TR
    if sys.platform == "darwin" and TR._bin("ffmpeg") and _python():
        return "mlx"
    return "fw" if TR._has_fw() else ""


def _setup_line():
    """The command that sets talking up, written to be pasted into a
    Terminal opened anywhere: the friend who hit this had no idea where
    the brain's folder was."""
    py = "python" if os.name == "nt" else "python3"
    return f'{py} "{os.path.join(HERE, "hear.py")}" --setup'


def need():
    """What talking still needs on this computer, as one instruction the
    owner can follow; "" when the ears are ready. Shown by the orb the
    moment it opens, so nobody speaks into a mic that cannot hear."""
    eng = engine()
    if eng == "fw" and _fw_cached():
        return ""
    if eng == "mlx":
        return ""          # a missing model says so on the first clip
    return ("To talk, this computer needs its speech engine. In Terminal, "
            f"run  {_setup_line()}  then reopen the brain.")


# ---- faster-whisper: held in this process, freed after the idle time

_FW = {"model": None, "timer": None}
_FW_LOCK = threading.Lock()


def _fw_size():
    return (os.environ.get("BRAIN_WHISPER_MODEL") or "small").strip()


def _fw_cached():
    try:
        from faster_whisper import download_model
        download_model(_fw_size(), local_files_only=True)
        return True
    except Exception:
        return False


def _fw_idle():
    """Give the memory back after keep_warm_minutes, as the worker does."""
    idle = max(1.0, float(_cfg().get("keep_warm_minutes") or 10)) * 60
    if _FW["timer"]:
        _FW["timer"].cancel()

    def drop():
        with _FW_LOCK:
            _FW["model"] = None
    t = threading.Timer(idle, drop)
    t.daemon = True
    t.start()
    _FW["timer"] = t


def _fw_model():
    """Callers hold _FW_LOCK. Never downloads: --setup does that."""
    if _FW["model"] is None:
        from faster_whisper import WhisperModel
        try:
            _FW["model"] = WhisperModel(_fw_size(), device="auto",
                                        compute_type="auto",
                                        local_files_only=True)
        except Exception:
            if not _fw_cached():
                raise ValueError(need())
            _FW["model"] = WhisperModel(_fw_size(), device="cpu",
                                        compute_type="int8",
                                        local_files_only=True)
    return _FW["model"]


def _fw_transcribe(path, language, prompt):
    # The recording as the browser made it (WebM, MP4), read by PyAV, which
    # comes with faster-whisper: that is why this engine needs no ffmpeg.
    import transcribe as TR
    audio = TR.fw_audio(path)
    with _FW_LOCK:
        segs, info = _fw_model().transcribe(
            audio, language=language or None,
            initial_prompt=(prompt or "")[:400] or None,
            condition_on_previous_text=False,   # the worker's guard
            vad_filter=True)                    # silence must not read as speech
        text = " ".join(s.text.strip() for s in segs if s.text.strip())
    _fw_idle()
    return {"text": text, "language": getattr(info, "language", "") or ""}


def warm():
    """Load the model now, in the background, so the next clip is quick.
    Called when the talk panel opens: she is about to speak."""
    eng = engine()
    if eng == "mlx":
        _W.warm()
    elif eng == "fw" and _FW["model"] is None and _fw_cached():
        def load():
            try:
                with _FW_LOCK:
                    _fw_model()
                _fw_idle()
            except Exception:
                pass
        threading.Thread(target=load, daemon=True).start()


def is_warm():
    return _W.alive() or _FW["model"] is not None


def _kill():
    _W.kill()
    with _FW_LOCK:
        _FW["model"] = None


def _to_wav(path, dest):
    import transcribe as TR
    ff = TR._bin("ffmpeg")
    if not ff:
        raise ValueError(need() or "ffmpeg is needed to read the recording")
    r = subprocess.run([ff, "-y", "-v", "error", "-i", path, "-ar", "16000",
                        "-ac", "1", "-c:a", "pcm_s16le", dest],
                       capture_output=True, timeout=90)
    if r.returncode != 0 or not os.path.exists(dest):
        raise ValueError("could not decode the recording")


def _mlx_transcribe(path, language, prompt, timeout):
    with tempfile.TemporaryDirectory() as td:
        wav = os.path.join(td, "a.wav")
        _to_wav(path, wav)
        try:
            return _W.ask({"path": wav, "language": language or "",
                           "prompt": prompt or ""}, timeout=timeout)
        except ValueError as exc:
            why = str(exc)
            if any(w in why.lower() for w in ("offline", "not found",
                                               "does not appear", "could not load")):
                why = (f"the model {model()} is not on this Mac yet. In "
                       f"Terminal, run  {_setup_line()}  once, or clear "
                       "voice.whisper_model")
            raise ValueError("Whisper: " + why[:300])


def transcribe(path, language=None, prompt=None, timeout=180):
    """Any audio file in, (text, language) out. Empty text means silence."""
    eng = engine()
    if not eng:
        raise ValueError(need())
    if eng == "mlx":
        res = _mlx_transcribe(path, language, prompt, timeout)
    else:
        try:
            res = _fw_transcribe(path, language, prompt)
        except ValueError:
            raise
        except Exception as exc:                        # noqa: BLE001
            raise ValueError("Whisper: " + str(exc)[:200])
    import transcribe as TR
    langs = TR.languages()
    # No word in another alphabet ever reaches the screen, whatever language
    # Whisper thought it heard: Cyrillic reads as a hack (9 Oct). First, so
    # what is left of a Russian subtitle credit meets the phantoms below.
    text = TR.drop_foreign(" ".join((res.get("text") or "").split()), langs)
    if text.lower().strip(" .!") in {p.strip(" .!") for p in PHANTOMS}:
        text = ""
    # A loop is not speech: one fragment said six times running, or a short
    # clip that is one word over and over (a Russian word three times, 29 Sep).
    if re.search(r"(.{2,14}?)(?:\s*\1){5,}", text, re.I):
        text = ""
    words = [w.lower().strip(".,!?;:") for w in text.split()]
    if len(words) >= 3 and len(set(words)) <= max(1, len(words) // 3):
        text = ""
    # Noise that Whisper took for a language she does not speak (Russian,
    # 29 Sep) is noise. voice.languages lists hers; empty lets any through.
    if text and langs and (res.get("language") or "") not in langs:
        text = ""
    return text, (res.get("language") or "")


def setup():
    """The owner asked for it by running --setup: install faster-whisper when
    this computer has no engine, then fetch the model once. Returns an exit
    code."""
    if engine() == "mlx":
        repo = model()
        print(f"Fetching {repo} for Apple's Whisper, once (1.6 to 3 GB)...", flush=True)
        return subprocess.run(
            [_python(), "-c", "import sys; from huggingface_hub import "
             "snapshot_download as s; s(sys.argv[1])", repo]).returncode
    import transcribe as TR
    if not TR._has_fw():
        print("Installing faster-whisper, the speech engine...", flush=True)
        r = subprocess.run([sys.executable, "-m", "pip", "install",
                            "faster-whisper"])
        if r.returncode:
            print("\nThat install did not finish. The lines above say why.", flush=True)
            return r.returncode
    size = _fw_size()
    print(f"Fetching the '{size}' speech model, once"
          + (" (about 500 MB)" if size == "small" else "") + "...",
          flush=True)
    # A fresh Python: one that started before the install cannot see it.
    r = subprocess.run([sys.executable, "-c", "import sys; from faster_whisper "
                        "import download_model as d; d(sys.argv[1])", size])
    if r.returncode == 0:
        print("\nReady. Reopen the brain, then tap the orb and talk.", flush=True)
    return r.returncode


def check_line():
    """One line for Check My Setup. Talking is optional, so this never fails."""
    if need():
        return ("[ -- ]  Talking to the brain is off. To turn it on, run:\n"
                f"            {_setup_line()}")
    return "[ OK ]  Talking works" + (" (Apple's Whisper)." if engine() == "mlx"
                                      else " (faster-whisper).")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(0)
    if sys.argv[1] == "--setup":
        sys.exit(setup())
    if sys.argv[1] == "--check":
        print("  " + check_line())
        sys.exit(0)
    import time
    for p in sys.argv[1:]:
        t = time.time()
        words, lang = transcribe(p)
        print(f"[{lang} {time.time() - t:.1f}s] {words}")

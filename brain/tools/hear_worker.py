#!/usr/bin/env python3
"""The ears, kept warm: one Whisper model loaded once, answering many clips.

Run by hear.py under the Python that has mlx_whisper (a conda env, usually),
never by hand. Reads one JSON request per line on stdin:

    {"path": "/tmp/x.wav", "language": "fr", "prompt": "names to spell right"}

and writes one JSON line back: {"text": ..., "language": ...} or {"error": ...}.
The wav must already be 16 kHz mono 16-bit (hear.py converts), so this
process never needs ffmpeg on its PATH.

Why a worker: the command-line mlx_whisper reloads the 3 GB model on every
call, which was most of the seven seconds a one-second question took (timed
28 Sep). Held in memory, only the listening itself is paid. It exits on its
own after `idle` seconds without a request, and gives the memory back.

Its command line must never contain "mlx_whisper": transcribe.whisper_busy()
looks for that word to decide whether a long transcription is running, and a
warm worker that matched would hold the twice-daily recordings pass forever.
"""
import json
import select
import sys
import wave

IDLE = float(sys.argv[1]) if len(sys.argv) > 1 else 600.0
MODEL = sys.argv[2] if len(sys.argv) > 2 else "mlx-community/whisper-large-v3-mlx"


def _load(path):
    import numpy as np
    with wave.open(path, "rb") as w:
        frames = w.readframes(w.getnframes())
    return np.frombuffer(frames, np.int16).astype(np.float32) / 32768.0


def main():
    # The model's download bars and warnings go to stderr; stdout carries
    # nothing but the one-line answers hear.py waits for.
    out = sys.stdout
    sys.stdout = sys.stderr
    import numpy as np
    import mlx_whisper

    def say(obj):
        out.write(json.dumps(obj) + "\n")
        out.flush()

    try:
        # A second of silence loads and compiles the model now, so the first
        # real question is not the one that waits for it.
        mlx_whisper.transcribe(np.zeros(16000, np.float32),
                               path_or_hf_repo=MODEL)
    except Exception as exc:                            # noqa: BLE001
        say({"error": f"could not load {MODEL}: {exc}"[:300]})
        return
    say({"ready": True, "model": MODEL})

    while True:
        ready, _, _ = select.select([sys.stdin], [], [], IDLE)
        if not ready:
            return                          # idle long enough: free the memory
        line = sys.stdin.readline()
        if not line:
            return                          # the server went away
        try:
            req = json.loads(line)
            # The quality checks the long recordings use (transcribe.py):
            # without them a quiet or noisy clip came back as one syllable
            # repeated a hundred times ("Westroomroomroom...", 28 Sep).
            kw = {"path_or_hf_repo": MODEL,
                  "condition_on_previous_text": False,
                  "compression_ratio_threshold": 2.2,
                  "logprob_threshold": -1.0,
                  "no_speech_threshold": 0.5}
            if req.get("language"):
                kw["language"] = req["language"]
            if req.get("prompt"):
                kw["initial_prompt"] = str(req["prompt"])[:400]
            res = mlx_whisper.transcribe(_load(req["path"]), **kw)
            say({"text": (res.get("text") or "").strip(),
                 "language": res.get("language") or ""})
        except Exception as exc:                        # noqa: BLE001
            say({"error": str(exc)[:300]})


if __name__ == "__main__":
    main()

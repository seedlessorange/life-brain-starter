#!/usr/bin/env python3
"""The mouth, kept warm: Kokoro loaded once, speaking many answers.

Run by voice.py under brain/.speech/env/bin/python (Kokoro's own
environment, so its packages can never disturb the Whisper the recordings
use), never by hand. Arguments: idle seconds, the model folder. Reads one
JSON request per line on stdin:

    {"text": "...", "voice": "af_heart", "lang": "en-us", "speed": 1.0,
     "out": "/tmp/x.wav"}

writes the speech to `out` as 16-bit mono WAV, and answers one JSON line:
{"ok": true, "seconds": 5.2} or {"error": "..."}. Exits after `idle`
seconds without a request.
"""
import json
import os
import select
import sys
import wave

IDLE = float(sys.argv[1]) if len(sys.argv) > 1 else 600.0
MODELS = sys.argv[2] if len(sys.argv) > 2 else "."


def main():
    out = sys.stdout
    sys.stdout = sys.stderr

    def say(obj):
        out.write(json.dumps(obj) + "\n")
        out.flush()

    try:
        import numpy as np
        from kokoro_onnx import Kokoro
        k = Kokoro(os.path.join(MODELS, "kokoro-v1.0.onnx"),
                   os.path.join(MODELS, "voices-v1.0.bin"))
        k.create("Ready.", voice="af_heart", speed=1.0, lang="en-us")
    except Exception as exc:                            # noqa: BLE001
        say({"error": f"Kokoro would not load: {exc}"[:300]})
        return
    say({"ready": True, "voices": len(k.get_voices())})

    while True:
        ready, _, _ = select.select([sys.stdin], [], [], IDLE)
        if not ready:
            return
        line = sys.stdin.readline()
        if not line:
            return
        try:
            req = json.loads(line)
            samples, rate = k.create(str(req["text"])[:4000],
                                     voice=req.get("voice") or "af_heart",
                                     speed=float(req.get("speed") or 1.0),
                                     lang=req.get("lang") or "en-us")
            pcm = (np.clip(samples, -1, 1) * 32767).astype(np.int16)
            with wave.open(req["out"], "wb") as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(rate)
                w.writeframes(pcm.tobytes())
            say({"ok": True, "seconds": round(len(samples) / rate, 2)})
        except Exception as exc:                        # noqa: BLE001
            say({"error": str(exc)[:300]})


if __name__ == "__main__":
    main()

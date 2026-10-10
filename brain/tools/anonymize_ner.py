#!/usr/bin/env python3
"""The local name model behind anonymize.py: text in, names out, offline.

Runs inside brain/.venv-ner (its own Python, so the brain's tools never
depend on torch), with the model in brain/.models. anonymize.py starts it;
nothing else should. It reads {"text": ..., "probes": [[start, sentence], ...]}
as JSON on stdin and prints a JSON list of {"start", "end", "text", "label",
"score", "probe"}. The probes are single sentences holding an unknown
lowercase word, with that word capitalised (anonymize.py makes them): the
model leans on capitals and on short context, and finds "lol tell Dax." at
0.97 where it misses "dax" in a long message.

The network is switched off before the model loads (HF_HUB_OFFLINE), so a
text it reads can never leave the Mac through it, and a missing model is an
error rather than a download.

Install, once, from the repo root:

    python3 -m venv brain/.venv-ner
    PIP_NO_CACHE_DIR=1 brain/.venv-ner/bin/pip install gliner protobuf sentencepiece
    HF_HOME=brain/.models/hf brain/.venv-ner/bin/python -c \\
        "from gliner import GLiNER; GLiNER.from_pretrained('urchade/gliner_multi_pii-v1')"

The model (GLiNER multi PII, Apache 2.0) reads meaning rather than capitals,
which is what plain code cannot: a name typed in lowercase in a chat.
"""
import json
import os
import re
import sys
import warnings

MODEL = "urchade/gliner_multi_pii-v1"
LABELS = ["person", "organization", "company", "project name", "product",
          "street address", "username"]
THRESHOLD = 0.5
CHUNK = 1200        # characters; the model reads about 384 tokens at a time.
                    # Sentence-sized pieces were tried (7 Oct): they find a
                    # few more lowercase names but call "gym" and
                    # "investisseurs" names, and scored worse overall.


def chunks(text):
    """Pieces under CHUNK characters, cut at line or sentence ends, with
    their offsets, so a long document is read whole."""
    start = 0
    while start < len(text):
        end = min(len(text), start + CHUNK)
        if end < len(text):
            cut = max(text.rfind("\n", start, end), text.rfind(". ", start, end))
            if cut > start + CHUNK // 3:
                end = cut + 1
        yield start, text[start:end]
        start = end


def main():
    warnings.filterwarnings("ignore")
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
    os.environ["TRANSFORMERS_VERBOSITY"] = "error"
    req = json.load(sys.stdin)
    from gliner import GLiNER
    model = GLiNER.from_pretrained(MODEL)
    out = []
    if req.get("text"):
        out += read(model, chunks(req["text"]), req["text"], False)
    for start, piece in req.get("probes") or []:
        out += read(model, [(0, piece)], piece, True, start)
    json.dump(out, sys.stdout, ensure_ascii=False)


def read(model, pieces, text, probe, shift=0):
    out = []
    for off, piece in pieces:
        if not piece.strip():
            continue
        for e in model.predict_entities(piece, LABELS, threshold=THRESHOLD):
            s, t = e["start"] + off, e["end"] + off
            # The model's span can carry a trailing space or full stop.
            surface = text[s:t]
            trimmed = re.sub(r"[\s.,;:]+$", "", surface)
            out.append({"start": s + shift, "end": s + len(trimmed) + shift, "text": trimmed,
                        "label": e["label"], "score": round(float(e["score"]), 3),
                        "probe": probe})
    return out


if __name__ == "__main__":
    main()

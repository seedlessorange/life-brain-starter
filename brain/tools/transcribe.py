#!/usr/bin/env python3
"""Recordings become project updates.

The loop this replaces, by hand, every time: copy the file path into a
shell script, edit the language and the prompt, run it, wait, find the
.txt, read it, and type the to-do list it implies into the right place.

Here: pick a recording, say which room it belongs to, and the brain does
the rest — converts, transcribes locally (mlx_whisper on the Mac's own
GPU, nothing uploaded), files the transcript into brain/transcripts/,
and queues Claude to turn what was said into that project's tasks.

    python3 brain/tools/transcribe.py --list
    python3 brain/tools/transcribe.py "~/Downloads/Voice 260815.m4a" \
        --room renovation --language fr

Flag names have shifted between mlx_whisper releases, so the quality
flags are probed against --help and only passed if this build advertises
them (the lesson from her own script — a hard-coded flag list fails on
upgrade, and the failure looks like a transcription bug).
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import date, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
BRAIN = os.path.dirname(HERE)
OUT = os.path.join(BRAIN, "transcripts")
LEDGER = os.path.join(BRAIN, ".transcribed.json")
AUDIO_EXT = (".m4a", ".mp3", ".wav", ".mp4", ".aac", ".m4b", ".mov", ".opus")
MODEL = "mlx-community/whisper-large-v3-mlx"

# Where recordings land. Configurable (config.json "recordings"), because
# hers arrive via Downloads today and a synced Drive folder tomorrow.
DEFAULT_DIRS = ["~/Downloads"]


def _cfg():
    try:
        with open(os.path.join(BRAIN, "config.json"), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def watch_dirs():
    d = _cfg().get("recordings") or DEFAULT_DIRS
    if isinstance(d, str):
        d = [d]
    return [os.path.expanduser(x) for x in d]


def _ledger():
    try:
        with open(LEDGER, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _remember(src, out_name):
    led = _ledger()
    led[os.path.abspath(src)] = {"transcript": out_name,
                                 "at": datetime.now().isoformat(timespec="seconds")}
    tmp = LEDGER + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(led, f, indent=2)
    os.replace(tmp, LEDGER)


def duration_min(path):
    try:
        r = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                            "format=duration", "-of", "csv=p=0", path],
                           capture_output=True, text=True, timeout=30)
        return round(float(r.stdout.strip()) / 60, 1)
    except Exception:
        return None


def recordings():
    """Every audio file in the watched folders, newest first, each saying
    whether it has already been through here."""
    led, out = _ledger(), []
    for d in watch_dirs():
        if not os.path.isdir(d):
            continue
        for fn in os.listdir(d):
            if not fn.lower().endswith(AUDIO_EXT) or fn.startswith("."):
                continue
            p = os.path.join(d, fn)
            try:
                st = os.stat(p)
            except OSError:
                continue
            mins = duration_min(p)
            # Anything under a minute is a sound effect or a mascot clip,
            # not a conversation worth 20 minutes of GPU.
            if mins is not None and mins < 1:
                continue
            done = led.get(os.path.abspath(p))
            out.append({"path": p, "name": fn, "mb": round(st.st_size / 1e6, 1),
                        "when": datetime.fromtimestamp(st.st_mtime)
                                        .strftime("%Y-%m-%d %H:%M"),
                        "mtime": st.st_mtime,
                        "minutes": mins,
                        "done": bool(done),
                        "transcript": (done or {}).get("transcript", "")})
    out.sort(key=lambda x: x["mtime"], reverse=True)
    return out


def _bin(name):
    """mlx_whisper often lives in a conda env that isn't on the server's
    PATH — look there too rather than failing with 'not found'."""
    p = shutil.which(name)
    if p:
        return p
    for c in (os.path.expanduser(f"~/miniconda3/bin/{name}"),
              os.path.expanduser(f"~/anaconda3/bin/{name}"),
              f"/opt/homebrew/bin/{name}", f"/usr/local/bin/{name}"):
        if os.path.exists(c):
            return c
    return ""


def _quality_flags(exe):
    """Only the flags this build advertises. Each one is here to stop a
    known failure: a hallucinated loop seeding the next window, a
    repetitive window surviving, silence being read as speech."""
    try:
        helptext = subprocess.run([exe, "--help"], capture_output=True,
                                  text=True, timeout=60).stdout
    except Exception:
        helptext = ""
    want = [("--condition-on-previous-text", "False"),
            ("--compression-ratio-threshold", "2.2"),
            ("--no-speech-threshold", "0.5"),
            ("--logprob-threshold", "-1.0"),
            ("--word-timestamps", "True"),
            ("--hallucination-silence-threshold", "2.0")]
    flags = []
    for name, val in want:
        if name in helptext:
            flags += [name, val]
    return flags


def slug(s, n=48):
    s = re.sub(r"[^a-z0-9]+", "-", (s or "").lower()).strip("-")
    return (s[:n].rstrip("-") or "recording")


def whisper_busy():
    """True when a transcription is already running — hers from a terminal
    or the brain's own. Two whisper runs share one GPU and both crawl, so
    the brain waits rather than competing with a job she started."""
    try:
        r = subprocess.run(["pgrep", "-f", "mlx_whisper"],
                           capture_output=True, text=True, timeout=10)
        pids = [p for p in r.stdout.split() if p.strip()
                and p.strip() != str(os.getpid())]
        return bool(pids)
    except Exception:
        return False


def existing_transcripts():
    """Transcripts already produced outside the brain — her own script's
    output. Adopting one costs nothing and skips a 20-minute re-run."""
    # A whisper run leaves .txt/.vtt/.srt of the SAME conversation; she wants
    # one row per recording, and the plain text is the one to read.
    best, roots = {}, [os.path.expanduser(d) for d in
                       (list(watch_dirs()) + ["~/Downloads", "~/Documents"])]
    rank = {".txt": 0, ".vtt": 1, ".srt": 2}
    for root in roots:
        if not os.path.isdir(root):
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            if dirpath.count(os.sep) - root.count(os.sep) > 3:
                dirnames[:] = []
                continue
            dirnames[:] = [d for d in dirnames if not d.startswith(".")]
            for fn in filenames:
                if not fn.lower().endswith((".txt", ".vtt", ".srt")):
                    continue
                p = os.path.join(dirpath, fn)
                try:
                    st = os.stat(p)
                except OSError:
                    continue
                if st.st_size < 2000:          # too small to be a conversation
                    continue
                # a transcript, not a README: mostly prose, and sitting in a
                # folder whose name says what it is
                hay = (dirpath + "/" + fn).lower()
                if not any(k in hay for k in ("transcript", "whisper", "voice",
                                              "recording", "audio")):
                    continue
                stem, ext = os.path.splitext(fn)
                key = (dirpath, stem)
                if key in best and rank.get(ext.lower(), 9) >= best[key][0]:
                    continue
                folder = os.path.basename(dirpath)
                # "audio_16k" says nothing; the folder is the real name
                label = folder if stem.lower().startswith(
                    ("audio", "out", "full", "transcript")) else stem
                best[key] = (rank.get(ext.lower(), 9),
                             {"path": p, "name": fn, "folder": folder,
                              "label": label,
                              "kb": round(st.st_size / 1000),
                              "mtime": st.st_mtime,
                              "when": datetime.fromtimestamp(st.st_mtime)
                                              .strftime("%Y-%m-%d %H:%M")})
    out = [v[1] for v in best.values()]
    out.sort(key=lambda x: x["mtime"], reverse=True)
    return out[:12]


def adopt(src, room="", language="fr"):
    """File a transcript that already exists into the brain, unchanged."""
    src = os.path.expanduser(src)
    with open(src, encoding="utf-8", errors="replace") as f:
        body = f.read().strip()
    if not body:
        raise ValueError("that file is empty")
    os.makedirs(OUT, exist_ok=True)
    stem = os.path.basename(os.path.dirname(src)) or "transcript"
    if os.path.splitext(os.path.basename(src))[0].lower() not in ("out", "full",
                                                                 "audio", "transcript"):
        stem = os.path.splitext(os.path.basename(src))[0]
    name = f"{date.today().isoformat()}-{slug(stem)}.md"
    dest = os.path.join(OUT, name)
    head = ["---", f"source: {src}",
            f"filed: {datetime.now().isoformat(timespec='minutes')}",
            f"language: {language}", "transcribed-by: her own whisper run"]
    if room:
        head.append(f"room: {room}")
    head += ["---", "", f"# {stem}", "",
             "*Transcribed on this Mac before it got here. Raw.*", "",
             body, ""]
    tmp = dest + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write("\n".join(head))
    os.replace(tmp, dest)
    _remember(src, name)
    return dest


def transcribe(src, language="fr", prompt="", room="", model=MODEL,
               progress=None):
    """Convert → transcribe → file. Returns the transcript's path.
    `progress` is called with short human sentences as it goes."""
    def say(msg):
        if progress:
            progress(msg)

    src = os.path.expanduser(src)
    if not os.path.exists(src):
        raise FileNotFoundError(f"no recording at {src}")

    # Two local engines, one output. mlx_whisper (the Mac's own GPU) wins
    # where it exists; faster-whisper covers every other machine — CPU works,
    # an NVIDIA GPU makes it quick. Both run here; audio never leaves.
    if sys.platform == "darwin" and _bin("mlx_whisper"):
        body, mins = _run_mlx(src, language, prompt, model, say)
    elif _has_fw():
        body, mins = _run_fw(src, language, prompt, say)
    elif sys.platform == "darwin":
        raise RuntimeError("no transcriber on this Mac — install mlx_whisper "
                           "(Apple Silicon), or `pip install faster-whisper`")
    else:
        raise RuntimeError("no transcriber on this machine — run "
                           "`pip install faster-whisper` once and retry")

    os.makedirs(OUT, exist_ok=True)
    name = f"{date.today().isoformat()}-{slug(os.path.splitext(os.path.basename(src))[0])}.md"
    dest = os.path.join(OUT, name)
    head = ["---", f"recording: {os.path.basename(src)}",
            f"transcribed: {datetime.now().isoformat(timespec='minutes')}",
            f"language: {language}", f"minutes: {mins if mins else ''}"]
    if room:
        head.append(f"room: {room}")
    head += ["---", "",
             f"# {os.path.basename(src)}", "",
             "*Transcribed on this machine. Raw — nobody has read it yet.*", "",
             body, ""]
    tmp = dest + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write("\n".join(head))
    os.replace(tmp, dest)
    _remember(src, name)
    say(f"transcript saved — {len(body.split())} words")
    return dest


def _run_mlx(src, language, prompt, model, say):
    """The original engine: mlx_whisper's CLI on the Mac's GPU."""
    if whisper_busy():
        raise RuntimeError("a transcription is already running on this Mac — "
                           "wait for it rather than sharing the GPU")
    whisper, ff = _bin("mlx_whisper"), _bin("ffmpeg")
    if not ff:
        raise RuntimeError("ffmpeg isn't installed on this Mac")

    os.makedirs(OUT, exist_ok=True)
    work = os.path.join(OUT, ".work")
    os.makedirs(work, exist_ok=True)
    wav = os.path.join(work, "audio_16k.wav")

    mins = duration_min(src)
    say(f"converting the audio{f' — {mins:g} minutes of it' if mins else ''}")
    r = subprocess.run([ff, "-y", "-v", "error", "-i", src, "-ar", "16000",
                        "-ac", "1", "-c:a", "pcm_s16le", wav],
                       capture_output=True, text=True, timeout=1800)
    if r.returncode != 0:
        raise RuntimeError("ffmpeg couldn't read that file: "
                           + (r.stderr or "").strip()[-200:])

    est = f"roughly {max(2, int((mins or 20) * 0.3))}–{max(5, int((mins or 20) * 0.6))} minutes"
    say(f"transcribing locally, {est} — nothing leaves this Mac")
    cmd = [whisper, wav, "--model", model, "--language", language,
           "--task", "transcribe", "--output-format", "txt",
           "--output-dir", work, "--output-name", "out"]
    if prompt:
        cmd += ["--initial-prompt", prompt]
    cmd += _quality_flags(whisper)
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=6 * 3600)
    if r.returncode != 0:
        raise RuntimeError("mlx_whisper failed: "
                           + ((r.stderr or r.stdout or "").strip()[-300:]))

    txt_path = os.path.join(work, "out.txt")
    if not os.path.exists(txt_path):
        raise RuntimeError("the transcriber wrote nothing")
    with open(txt_path, encoding="utf-8") as f:
        body = f.read().strip()
    shutil.rmtree(work, ignore_errors=True)
    return body, mins


def _has_fw():
    try:
        import faster_whisper  # noqa: F401
        return True
    except ImportError:
        return False


FW_LOCK = os.path.join(OUT, ".fw-lock")


def _run_fw(src, language, prompt, say):
    """faster-whisper, in-process: any OS, CPU or NVIDIA GPU, no ffmpeg
    needed (it decodes the audio itself). Model size comes from the
    BRAIN_WHISPER_MODEL env var; 'small' is the honest CPU default —
    'medium' or 'large-v3' are better and slower on real GPUs."""
    from faster_whisper import WhisperModel

    # One run at a time, same rule as the Mac engine. A lock file because
    # this engine runs inside the server process; consider it stale after
    # six hours (a crash must not brick transcription forever). Refusing
    # must not clear a lock someone else holds — only ours, in the finally.
    os.makedirs(OUT, exist_ok=True)
    if os.path.exists(FW_LOCK) and \
            time.time() - os.path.getmtime(FW_LOCK) < 6 * 3600:
        raise RuntimeError("a transcription is already running on this "
                           "machine — wait for it rather than sharing "
                           "the processor")
    with open(FW_LOCK, "w", encoding="utf-8") as f:
        f.write(str(os.getpid()))
    try:
        size = os.environ.get("BRAIN_WHISPER_MODEL", "small")
        mins = duration_min(src)
        say(f"loading the '{size}' model — the first run downloads it, "
            f"later runs start instantly")
        try:
            m = WhisperModel(size, device="auto", compute_type="auto")
        except Exception:
            m = WhisperModel(size, device="cpu", compute_type="int8")

        say(f"transcribing locally"
            f"{f' — {mins:g} minutes of audio' if mins else ''} — "
            f"nothing leaves this machine")
        segments, _info = m.transcribe(
            src, language=language or None,
            initial_prompt=prompt or None,
            condition_on_previous_text=False,   # same guard as the Mac flags
            vad_filter=True)                    # silence must not read as speech
        parts, last_beat = [], 0.0
        for s in segments:
            text = s.text.strip()
            if text:
                parts.append(text)
            if s.end - last_beat > 300:         # a heartbeat every ~5 audio-min
                last_beat = s.end
                say(f"...{int(s.end / 60)} minutes in")
        return "\n".join(parts).strip(), mins
    finally:
        try:
            os.remove(FW_LOCK)
        except OSError:
            pass


def ask_text(transcript_name, room=""):
    """The ask that turns a transcript into project movement. Written so a
    run does the boring half (who owes what, by when) and never invents
    commitments nobody made."""
    where = f'the "{room}" room' if room else "the right project"
    return (
        f"Read brain/transcripts/{transcript_name} — a transcript of a real "
        f"conversation — and turn it into movement in {where}.\n\n"
        "Do this:\n"
        "1. Summarise what was actually decided, in her language, at the top "
        "of the transcript file under '## What this was'. Keep it short.\n"
        "2. Extract TWO task lists, separately: what SHE (or the household) "
        "has to do, and what each OTHER PERSON was asked for — name them "
        "(e.g. Isa). Add hers as tasks under the matching workstream in "
        "brain/workstreams.md; put the other person's list under '## For "
        "<name>' in the transcript file, ready to send.\n"
        "3. Mark every new task '(from the recording — confirm)' so she can "
        "prune, and put a (due …) on anything the conversation actually "
        "dated. Never invent a date or a commitment that wasn't said.\n"
        "4. If a person came up who isn't in people.md, ask about them in "
        "questions.md rather than adding them.\n"
        "5. Say plainly what you filed and what you weren't sure about — a "
        "transcript of a rambling conversation will have ambiguities, and "
        "guessing at them is worse than asking.")


def dump_ask_text(transcript_name):
    """The other kind of recording: not a meeting with people and actions in
    it, but her thinking out loud. Sorting it like a dump keeps the half-
    thoughts that a task extractor would throw away."""
    return (
        f"Read brain/transcripts/{transcript_name} — a voice note she recorded "
        "on her own, thinking out loud rather than meeting anyone.\n\n"
        "Treat it exactly as `/dump`: sort every item into the brain, lose "
        "nothing, and put the questions you cannot answer in the Outcome "
        "rather than guessing. Some of it will be tasks, some will be a worry, "
        "a date, a person she owes a reply, or an idea with nowhere to live "
        "yet — file each where it belongs and do not force the rest into a "
        "task list.\n\n"
        "Summarise what the recording was about at the top of the transcript "
        "file under '## What this was', in her language, short. Mark anything "
        "you filed '(from a voice note — confirm)' so she can prune, and never "
        "invent a date or a commitment she did not say.")


def journal_ask_text(transcript_name):
    """A recording captioned 'journal': her telling the day, to be kept in her
    words. The transcript is the entry; the farming is secondary."""
    return (
        f"Read brain/transcripts/{transcript_name} — she recorded a journal "
        "entry about her day.\n\n"
        "Follow `/journal`: copy the transcript text verbatim into "
        "brain/journal/ dated for the day it describes, then quietly farm it "
        "— people she mentions speaking to get their Last date set, promises "
        "and tasks get filed, done things get ticked. Never rewrite or "
        "summarize the entry itself.")


def met_ask_text(transcript_name):
    """The third kind of recording: she has just met someone and is saying who
    they are while she still remembers. A new contact is warm for about three
    days, so this one is about speed — the entry and its follow-ups exist
    before the evening, and the judgement left over is small enough to confirm
    in a glance."""
    return (
        f"Read brain/transcripts/{transcript_name} — she has just met someone "
        "and is recording who they are while it is fresh.\n\n"
        "For each person in the recording:\n"
        "1. Add them with `python3 brain/tools/person_add.py \"<name>\" "
        "--role --company --how --met --where --linkedin --ladder` — fill only "
        "the flags the recording actually supports, and never invent a job "
        "title or a company. `--ladder` sets the follow-ups at +3 days, +3 "
        "weeks and +3 months, which is the point of doing this today.\n"
        "2. If they are already on the list, re-run with `--update` instead: "
        "it fills the blanks and leaves everything she wrote alone.\n"
        "3. Anything said about them that is not a field — what they are "
        "working on, what to ask next time — goes as plain notes under their "
        "entry, in her words.\n"
        "4. If the recording names something SHE promised to do (send a deck, "
        "make an intro), add it as a checkbox under that person. Those are "
        "promises and they surface in her chases.\n\n"
        "Two things to say in the Outcome rather than decide: the tool files "
        "new people as `Circle: Network`, so list who you added and let her "
        "change it in one tap; and name anything you could not make out, "
        "because a misheard company is worse than a blank one.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("audio", nargs="?", help="the recording")
    ap.add_argument("--list", action="store_true", help="show what's waiting")
    ap.add_argument("--language", default="fr")
    ap.add_argument("--prompt", default="", help="names/jargon to expect")
    ap.add_argument("--room", default="")
    a = ap.parse_args()
    if a.list or not a.audio:
        for r in recordings():
            mark = "done" if r["done"] else "    "
            mins = f'{r["minutes"]:g}m' if r["minutes"] else "?"
            print(f'  {mark}  {r["when"]}  {mins:>6}  {r["name"]}')
        if not a.list:
            print("\nGive me one of those paths to transcribe it.")
        return
    dest = transcribe(a.audio, a.language, a.prompt, a.room,
                      progress=lambda m: print("==", m))
    print("\nSaved:", dest)
    print("\nNext, hand this to Claude:\n")
    print(ask_text(os.path.basename(dest), a.room))


if __name__ == "__main__":
    main()

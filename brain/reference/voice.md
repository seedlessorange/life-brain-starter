# The voice: talking to the brain, and hearing it answer

Load this when a task is about the talk orb, spoken answers, Telegram voice
replies, dictation speed, the plan meter, or the skills row in the box.
Built 28 Sep 2026, from ideas in an "agentic OS" video she sent: a voice
that answers, a router that sends each ask to the cheapest level that can
answer it, a usage gauge, and skills one tap away.

## What she can do

- **Page:** the Talk button in the bar (a live mini-orb in a ring) opens
  the panel and listens at once. She speaks and pauses; the brain answers
  out loud. It then listens again for about six seconds, so a conversation
  needs no more taps. Space talks or sends, Esc stops. The orbs draw in the
  skin's `--orb` colour, else its ink, so every skin gets its own.
- **Orbit's deck** (28 Sep, her screenshot of a "Jarvis" command centre):
  in the Orbit skin only, Today opens on a full-width deck above both
  columns (`V["todaytop"]`, `orb.deck_html()`): a large orb with an
  orbiting ring and signal pulses that talks in place when tapped (or on
  Space while the page is at its top), the day's greeting under it, the
  three, the plan meter, countdowns, "Your next hour" from next.md, the
  skill tiles and a clock. The big CLAUDE wordmark went on her word (she
  only uses Claude). The rest of Today follows below, unchanged. Other
  skins never show it (`skinx` furniture); its look is `skins/orbit.css`.
- **The voice picker** (under the hood, Voice): a Kokoro voice per
  language (American, British and French voices; "This Mac" hands a
  language to `say`), a pace, and "Hear it" to preview. Saved to
  `voice.kokoro` via `/api/voice/set`; previews through `/api/voice/preview`.
- **Telegram:** a voice note of up to a minute with no caption (or captioned
  "ask") is checked for a question. If it asks something, the answer comes
  back as text and as a voice note. If it doesn't, it is filed exactly as
  before (dump, update, journal, met, a room). A forwarded note is never
  answered: it is someone else's voice.
- **The box:** every answer has "Hear it". A Run row starts Plan today,
  Catch me up, Work the queue or Wrap up, and a slim line shows the plan
  meter.
- **Under the hood:** the plan meter in full, in AI and spend.

## How a spoken ask is answered (voice.py)

1. **No model.** "Open/show me the kitchen" navigates. "Note…", "remind
   me…", "rappelle-moi…" go to the inbox. An English question that
   answers.py matches with a short answer is said as it is.
2. **A small model, no tools** (`voice.model`, Haiku by default, through
   llm.py's sealed call). It gets a pack of about 2,000 tokens: today.md,
   next.md, the week sketch, waiting, countdowns, and model.py's flags and
   people. Ticked lines are rewritten as DONE and open ones as OPEN, because
   Haiku read `[x]` as still to do. When answers.py matched, that file text
   goes first as "the answer's source". French questions always come here,
   since the lookups are written in English.
3. **The full brain.** If she asks it to DO something, the small model
   answers `FULL: <request>`. The page hands that to the box and sends it;
   Telegram hands it to the existing read-and-answer run.
4. **Filed at once** (28 Sep, her ask: "does it actually update it based on
   what I say?"). When she TELLS it something (what happened, news, a
   decision, a date), the small model answers `UPDATE: <what to file>` and
   `SAY: <a short acknowledgement>`. serve.py's `voice_file_update` sends
   her words, with the box's own "tick off what happened" instruction, to
   one Claude conversation per day in the brain's folder ("Said out loud ·
   <date>", id kept in `brain/.voice/convo.json`), taking the folder's
   hands when they are free, as the box does. When another conversation is
   mid-task, the update goes to the queue as a dump instead.

**Whatever she says is handled** (her words, 28 Sep: "think of this like
either a ramble or a command or whatever"). A long monologue (over 60
words) is a ramble, sorted with /dump's rules, decided without a model so
the acknowledgement is instant. News is an update. A request (`FULL:`) is
done. All three go to the day's "Said out loud" conversation, each with its
own instruction (`VOICE_KINDS` in serve.py), while the voice carries on and
a line under the answer opens that conversation in the box
(`brainBox.openConvo`). Only a question is simply answered. After 20 s of
talking the orb allows 3.5 s pauses, and a ramble can run five minutes.

**Ending a talk is easy** (29 Sep, she struggled to end one: noise heard
after a reply came back as "инструмент инструмент инструмент", was
answered, and the orb listened again). An End button and a "say that's
all, or Esc" hint show while a talk is on. END_RX takes thanks, merci, ok,
c'est bon, stop, done, good night and the like. Listening again after a
reply needs louder, sustained speech (a quarter second over a higher bar)
and starts 0.7 s after the voice stops; if it hears nothing real, the talk
simply goes quiet. hear.py drops a transcript that is one word on repeat
or in a language outside `voice.languages` (default en, fr, es; an empty
list accepts any). On a touch screen the deck's hints drop Space and Esc. And a
spoken update never falls back to the queue just because the day's voice
conversation is still busy with the previous one: it waits its turn there.

**The page never reloads under a talk.** The page refreshes itself when the
brain changes, and a filed update changed it seconds after she spoke,
wiping the conversation. `brainVoice.busy()` holds that refresh (page.js,
map.py, rooms.py) while a talk is on or its words are on screen; the pill
says changes are waiting, and the refresh lands after Esc or two quiet
minutes.

The small model is **one Claude kept open** (`voice._Mind`, stream-json in
and out, sealed like llm.py): 3.8 s for a new session's first answer,
0.5 to 1 s after. The warm-up (when the orb opens) starts it and pays the
first answer with a one-word "ready", so her first question is quick too.
The notes ride along only when they changed. It restarts after twelve
turns, after the keep-warm time, or when `voice.model` changes. Replies are
at most two short sentences; the screen carries the detail. The voice's
language follows the reply's own words, never Whisper's guess about hers:
Whisper heard her English as French, and the French voice then read an
English answer.

Timings on her M4 (28 Sep, warm, in a real browser with a fake mic): from
the end of her pause to the first spoken word, about 4.5 s, made of
Whisper (about 2.2 s), the kept-open Claude (about 1 s) and Kokoro making
the opening phrase (about 0.7 s). The reply is spoken in two parts: the
phrase up to the first comma at once, the rest made while it plays
(`voice.first_breath`, the page fetches the tail from `/api/voice/say`).
Kokoro makes speech about three times faster than it plays; the Mac's
graphics chip (CoreML) did not speed it up.

The orb waits 2.2 s of silence before it sends (1.3 s cut her off), and
12 s for her to start. Space starts a talk anywhere she is not typing and
the box is closed, and Space again sends at once without waiting out the
pause. On Orbit's deck the orb steps back while she talks (`.talking`) and
the conversation gets the room, the whole answer shown. The first
clip after ten idle minutes adds a few seconds of loading. The small model
is told tomorrow's date outright: without it, Haiku once moved Wednesday's
goal to "demain".

## The ears (hear.py, hear_worker.py)

One Whisper stays loaded in a worker process for `keep_warm_minutes`
(10), then exits and gives back its memory. Short clips use
`whisper-large-v3-turbo` (installed 28 Sep, 1.6 GB in the Hugging Face
cache): 1.6 s a sentence against 2.2 s, measured with the GPU free. Long
recordings keep transcribe.py's large-v3. The talk panel warms it when it
opens. Dictation on the page uses it too, with the old cold command as the
fallback. The worker runs with the Hugging Face hub offline, so a model
that isn't on the Mac fails plainly instead of downloading. `voice.words`
in config lists names Whisper should spell right; live workstream names and
the current place are added automatically.

**Never let the worker's command line contain "mlx_whisper".**
`transcribe.whisper_busy()` looks for that word, and a match would hold
the recordings pass forever. The self-test checks this.

## The mouth (voice.synth)

**Kokoro** (installed 28 Sep on her go-ahead): its own Python environment
and model files in `brain/.speech/` (gitignored, about 500 MB), kept warm by
`speak_worker.py` through `warm.py`. English speaks as `af_heart`, French as
`ff_siwis` (Kokoro's only French voice; it says English loanwords the French
way). About a second per sentence once loaded. The first letter of a
Kokoro voice is its language (a/b English, f French…).

The Mac's `say` is the fallback whenever Kokoro is missing or fails, and
what a language set to "" in `voice.kokoro` uses. It picks the best
installed voice on its own: Premium, then Enhanced, then a known-good name,
never the novelty or Eloquence voices. On 28 Sep only Kit (Enhanced)
was installed beyond the basics.

Output: WAV/AIFF, then MP3 for the page or OGG/Opus for Telegram (ffmpeg).
"Hear it" reads at most about 1,500 characters and says the rest is on
screen.

## The plan meter (plan_usage.py)

The weekly and five-hour percentages that `/usage` shows inside Claude
Code. It reads Claude Code's own login from the Keychain for each request,
sends it only to `api.anthropic.com` (the address is fixed in the code),
and never refreshes the login. It keeps only the percentages, in
`brain/.plan-usage.json` (gitignored), and asks at most every five minutes.
When the login has expired, the meter shows the last known reading and its
age.

## Setting it up on another Mac

The voice runs on a Mac (Apple silicon for Whisper). With nothing extra
installed, the orb hears through the Whisper the recordings already use and
speaks with the Mac's own voices. Two optional installs make it better:

- **Kokoro**, the better voice, in its own environment so it never touches
  anything else:
  `python3 -m venv brain/.speech/env && brain/.speech/env/bin/pip install kokoro-onnx`,
  then download `kokoro-v1.0.onnx` and `voices-v1.0.bin` from the
  kokoro-onnx releases on GitHub into `brain/.speech/models/`. voice.py
  finds it on its own; `voice.engine` "say" turns it off.
- **Turbo Whisper**, quicker on short clips:
  `python -c "from huggingface_hub import snapshot_download as s; s('mlx-community/whisper-large-v3-turbo')"`
  with the Python that has mlx_whisper, then set `voice.whisper_model` to
  `mlx-community/whisper-large-v3-turbo`.

Both write outside the brain's own files (a Python environment, a model
cache), so each is the owner's call. The plan meter reads Claude Code's
login from the macOS Keychain; elsewhere it shows no reading.

## Config (`"voice"` in config.json)

`model`, `engine` (auto | kokoro | say), `kokoro` {en, fr, speed},
`voices` {fr, en} for `say`, `rate`, `telegram` (`when-spoken` | `never`),
`whisper_model`, `keep_warm_minutes`, `words`.

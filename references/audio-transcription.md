<!-- PRIMER: audio-transcription
  STATUS: drafted 2026-06-13 -->

# Transcribing audio (audio audits, voice responses)

This primer covers transcribing SurveyCTO audio captures into text using OpenAI.
It is the audio analog of user-data translation and uses the same OpenAI
credential handling.

Read [`openai-credentials.md`](openai-credentials.md) first (the same API key
works for translation and transcription). The user-data translation primer
([`user-data-translation.md`](user-data-translation.md)) shares the same design.

## Why this runs as a script, not in conversation

Audio recordings carry respondents' voices and frequently spoken PII. The content
must not pass through the agent's context, so the agent runs the shipped module
[`assets/transcribe-translate/transcription.py`](../assets/transcribe-translate/transcription.py),
which sends the audio to OpenAI and writes a transcripts CSV. The agent
orchestrates and reports; it does not listen to or ingest the audio. (A natural
follow-on: transcribe to a CSV, then translate the transcript column with
[`user-data-translation.md`](user-data-translation.md).)

## Model selection (cheapest is the default)

Transcription model menu:

- `fast` -> `gpt-4o-mini-transcribe` (DEFAULT; cheapest, ~$0.003/audio-min)
- `accurate` -> `gpt-4o-transcribe` (~$0.006/audio-min)
- `whisper` -> `whisper-1` (~$0.006/audio-min)

Pass `--model fast|accurate|whisper` (or an explicit model id).

### Long audio: which model, and automatic chunking

Real audio audits are often long (minutes to over an hour). The module handles
this automatically, but the behavior differs by model (verified against real
recordings):

- `whisper-1` has only the 25 MB request limit and no duration/token cap, so it
  transcribes a long file in a single request as long as it is under 25 MB. How
  many minutes that is depends entirely on the source bitrate (a 128 kbps export
  hits 25 MB at ~26 min; a 64 kbps file around twice that). Over 25 MB, it is
  split by size.
- `gpt-4o-mini-transcribe` / `gpt-4o-transcribe` additionally have a token/context
  limit and reject audio that is too long (roughly 15+ minutes of speech, content
  dependent). The module splits such files into ~10-minute windows and, if a
  window still comes back as "too large" on dense speech, recursively halves it
  and retries. Splits carry a ~1s overlap so words at a cut are not dropped.

Practical guidance: the default (`fast`) works for any length via chunking. For
very long or very dense recordings where you want the fewest seams, `whisper` is
the simplest (one request for any file under 25 MB). For best accuracy on hard audio, try
`accurate`. The chunking is lossless (it over-captures at seams rather than
dropping); a 1-3 word duplication can appear at a seam.

## What the module gives you

- `estimate_cost(audio_paths, model=None)` sums duration and returns the estimated
  USD cost, files whose duration could not be read in `unknown_duration`, and the
  PII warning.
- `transcribe_files(audio_paths, output_path, model=None, cache_path=None,
  confirm=False)` transcribes a batch and writes a CSV (`file`, `transcript`,
  `backend`, `duration_seconds`, `status`).

Built in: a confirm-gate cost check, per-file failure isolation (a bad file gets
an error status; the batch continues), caching (keyed on file bytes + model so
re-runs are free), automatic chunking, and sanitized errors (an API error never
echoes audio content).

## Workflow

1. **Confirm credentials and environment.** If "no OpenAI API key configured"
   appears, switch to the coaching in
   [`openai-credentials.md`](openai-credentials.md). Install the client library by
   running the bootstrap once (`python3 setup_env.py`); it prints a
   `VENV_PYTHON=<path>` line, and you run the module with that interpreter. Do not
   rely on a bare `pip install openai`, which fails with
   `externally-managed-environment` (PEP 668) on modern macOS and Debian/Ubuntu.
   Transcription also needs `ffmpeg` on PATH.
2. **Collect the audio paths.** SurveyCTO audio-audit and voice-response files are
   usually in the media folder of an export.
3. **Get the spoken language** if it matters (the models auto-detect; you can pass
   a hint to whisper-1 if needed).
4. **Estimate cost and show the PII warning.** Call `estimate_cost(...)`. Show the
   total duration, estimated USD cost, any `unknown_duration` files, and the
   privacy reminder that the audio is sent to OpenAI.
5. **Wait for explicit confirmation** before transcribing.
6. **Transcribe.** Call `transcribe_files(...)` with `confirm=True` and a
   `cache_path` so re-runs are cheap.
7. **Report, including spend.** Give the output CSV path and the stats
   (transcribed, cached, failed). For OpenAI runs, always tell the user what this
   run actually cost and the running total: report `actual_usd_display` ("this
   run") and `total_spend_usd_display` ("total so far on this machine"), on every
   paid run. Mention any files with an error status. Do not paste transcript
   content into chat unless asked for specific rows.

### Running it: use the CLI

Prefer the CLI: it handles credentials itself and prints JSON you can report
from. Run it with the interpreter that `setup_env.py` printed
(`VENV_PYTHON=<path>`); `python3` alone will not have `openai` installed.
`transcription.py` lives in the skill's `assets/transcribe-translate/` directory,
and ffmpeg/ffprobe must be on PATH.

```bash
PY=<the VENV_PYTHON path from setup_env.py>
# 1. estimate: shows known_seconds, estimated_usd_display, pii_warning -> show the user, get confirmation
"$PY" transcription.py estimate audio/r1.mp3 audio/r2.mp3
# 2. transcribe (only after confirmation)
"$PY" transcription.py transcribe audio/r1.mp3 audio/r2.mp3 \
    --output transcripts.csv --cache transcription-cache.db --confirm
```

Equivalent inside a generated Python script (run under the same interpreter):

```python
import openai_auth, transcription
openai_auth.configure_openai()
est = transcription.estimate_cost(["audio/r1.mp3","audio/r2.mp3"])
# show est["estimated_usd_display"], est["known_seconds"], est["pii_warning"]; confirm
stats = transcription.transcribe_files(
    ["audio/r1.mp3","audio/r2.mp3"], output_path="transcripts.csv",
    cache_path="transcription-cache.db", confirm=True)   # model="fast" by default
print(stats["output_path"], stats["transcribed"], stats["cached"], stats["failed"])
```

## Caching

Pass a `cache_path` (e.g. `transcription-cache.db`) so re-running a batch only
transcribes files not seen before (keyed on file bytes + model). The cache holds
transcript text, so it is sensitive: keep it with the user's data, not in a
shared or version-controlled location.

## Quality reminder

ASR quality varies with audio quality, accent, background noise, and language. For
anything high-stakes, recommend a fluent speaker review a sample against the
audio. Recommendation, not a gate.

Long audio that gets chunked has one extra caveat: chunks overlap slightly so no
word is cut at a boundary, and the duplicated words are removed when the pieces
are rejoined. A word genuinely repeated right at a seam (a stutter) can be
collapsed to one. It is rare and only affects files large enough to be split, but
it is another reason to spot-check a chunked long-audio transcript.

## Out of scope

- Speaker diarization, word-level timestamps, and streaming are not wired up here.
- Translating transcripts is a separate step: transcribe to a CSV, then use
  [`user-data-translation.md`](user-data-translation.md) on the transcript column.

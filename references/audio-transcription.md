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
which sends the audio to OpenAI and writes the transcripts. The agent orchestrates
and reports; it does not listen to or ingest the audio. (A natural follow-on:
transcribe with `--format txt`, then translate that document with the `translate-doc`
command in [`user-data-translation.md`](user-data-translation.md).)

## Model selection (cheapest is the default)

Transcription model menu:

- `fast` -> `gpt-4o-mini-transcribe` (DEFAULT; cheapest, ~$0.003/audio-min)
- `accurate` -> `gpt-4o-transcribe` (~$0.006/audio-min)
- `whisper` -> `whisper-1` (~$0.006/audio-min)

Pass `--model fast|accurate|whisper` (other model ids are rejected unless added to
the model menu with a rate in `pricing.json`, so the estimate stays accurate). The
`~$/min` figures above are indicative; the live rates come from `pricing.json`.
Present this choice to the user before running, defaulting to `fast`: name the
default and offer `accurate`/`whisper` for harder audio, with the cost difference.
Keep it to one offer, not an interrogation; proceed with `fast` if they have no
preference.

### Pricing and the in-flight price check

OpenAI publishes no pricing API, so the rates that turn usage into dollars live in
`assets/transcribe-translate/pricing.json` with the date they were last verified.
At the start of a transcription run, offer to check current prices online so the
estimate is accurate: "May I check OpenAI's current prices to estimate the cost?
Otherwise I'll use the stored rates from <rates_as_of>." If the user agrees, read
the pricing page (`pricing_source_url`), then update the rate with
`pricing.py set-transcription <model_id> --in-per-mtok ... --out-per-mtok ...
--est-per-min ... --as-of <today>` (whisper-1 uses `--usd-per-min`). If the user
declines, use the stored rates. Either way, tell the user which rates were used
and as of when (`estimate_cost` returns `rates_as_of` and `rates_source`).

The estimate is approximate: the gpt-4o-* models bill per token, so the pre-run
per-minute figure is a guide and the real cost (reported after the run) is
computed from the response's actual token counts. whisper-1 bills per minute, so
its estimate is close.

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
`accurate`. The chunking uses a small overlap at each seam to reduce the chance a
word is cut at a boundary; the overlap's duplicated words are then removed when
the pieces are stitched. That de-duplication can, rarely, collapse a word that was
genuinely repeated right at a seam (a stutter) -- see the quality reminder.

### Long audio: resumable passes under your command-timeout

Transcribing a long file can take longer than a single shell command is allowed to
run, and many environments hard-cap each command (some sandboxes as low as ~45s,
and you usually cannot raise that cap). So the module makes durable progress and
resumes instead of running as one unbounded job:

- Each chunk is transcribed and cached on its own (`--cache`), so a finished chunk
  is never transcribed or billed twice. The cache defaults to a local directory; do
  not point it at a mounted/network folder (SQLite cannot lock there).
- Each call does a bounded amount of new work (`--max-seconds`), then stops cleanly.
  If a file did not finish, the JSON result has `"incomplete": true` and the process
  exits with code 3.
- To finish a long file, re-run the EXACT same command (same `--output` and
  `--cache`) until the result shows `"incomplete": false`. Each pass resumes from
  the cached chunks and only pays for new audio.

First, know your cap. At the start of a media task, determine your environment's
per-command (Bash) time limit from what you know about the environment you are
running in. Then set `--max-seconds` to about 5 seconds below it. For example, if
your commands are capped at 45 seconds, run with `--max-seconds 40`. Never set
`--max-seconds` higher than 5 seconds below your cap, or a pass will be killed
mid-chunk (wasting an already-billed request). If you genuinely run with no cap, you
may use a large value for fewer passes, but the safe default fits a tight cap.

Run ONE pass per command. If a command exits with code 3, run the SAME command
again as a new command. Do NOT wrap it in a shell loop (`while ...; do`): the loop
itself will be cut off by the command-timeout and orphan a running process. Do not
background and poll either; some environments recycle background processes between
turns.

## What the module gives you

- `estimate_cost(audio_paths, model=None)` sums duration and returns the estimated
  USD cost, files whose duration could not be read in `unknown_duration`, and the
  PII warning.
- `transcribe_files(audio_paths, output_path, model=None, cache_path=None,
  confirm=False, language=None, max_seconds=None)` transcribes a batch and writes a
  CSV (`file`, `transcript`, `backend`, `duration_seconds`, `status`). `language` is
  an optional ISO-639-1 hint; omit to auto-detect. `max_seconds` bounds new work per
  call for resumability (the CLI sets it; the library defaults to running to
  completion). Returns counts `transcribed`, `cached`, `failed`, `pending`, and the
  `incomplete` flag (true when files remain to resume).

Built in: a confirm-gate cost check, per-file failure isolation (a bad file gets
an error status; the batch continues), chunk-level caching (keyed on file bytes +
model + language so re-runs are free and long files resume), automatic chunking,
and sanitized errors (an API error never echoes audio content).

## Workflow

1. **Confirm credentials and environment.** If "no OpenAI API key configured"
   appears, switch to the coaching in
   [`openai-credentials.md`](openai-credentials.md). Install the client library by
   running the bootstrap once (`python3 assets/transcribe-translate/setup_env.py`); it prints a
   `VENV_PYTHON=<path>` line, and you run the module with that interpreter. Do not
   rely on a bare `pip install openai`, which fails with
   `externally-managed-environment` (PEP 668) on modern macOS and Debian/Ubuntu.
   The bootstrap also installs `socksio` (the OpenAI client needs it when egress is
   routed through a SOCKS proxy, as some sandboxes do). Transcription also needs
   `ffmpeg` on PATH. Some sandboxes reset their filesystem between sessions, so the
   bootstrap may need re-running each session.
2. **Collect the audio paths, and know your command-timeout.** SurveyCTO audio-audit
   and voice-response files are usually in the media folder of an export. Determine
   your environment's per-command (Bash) time limit so you can set `--max-seconds`
   to about 5s below it (see "Long audio" above); default to `--max-seconds 40` if a
   ~45s cap is likely.
3. **Pick the output format by shape.** Many short clips (a dataset of audio audits
   or voice responses, one row per respondent) -> `--format csv`, which joins back to
   the data. A few long recordings -> `--format md` or `--format txt`, a readable
   document; a long transcript in a CSV cell is unwieldy.
4. **Spoken language is auto-detected** by default, so this is optional. If the
   user knows the language and wants slightly better accuracy/latency, pass it as
   an ISO-639-1 hint via `--language` (e.g. `--language sw`); omit it otherwise.
5. **Offer the in-flight price check, then estimate cost and show the PII
   warning.** First offer to check current OpenAI prices (see "Pricing and the
   in-flight price check"); refresh `pricing.json` if the user agrees. Then call
   `estimate_cost(...)` and show the total duration, estimated USD cost (noting it
   is approximate and as of `rates_as_of`), any `unknown_duration` files, and the
   privacy reminder that the audio is sent to OpenAI.
6. **Wait for explicit confirmation** before transcribing.
7. **Transcribe, one pass per command, resuming if needed.** Run the CLI with
   `--confirm` and `--max-seconds` set ~5s below your command-timeout. If the result
   has `"incomplete": true` (exit code 3), run the SAME command again as a new
   command, and keep going until it reports `"incomplete": false`. Never wrap it in a
   shell loop and do not background it. Tell the user what is happening each pass
   rather than going silent, e.g. "This recording is long, so I'm transcribing it in
   resumable passes. Pass 2: 5 of 7 chunks done; continuing." Each pass only pays for
   new audio.
8. **Report, including spend.** Give the output path and the stats (transcribed,
   cached, failed, and any still pending). For OpenAI runs, always tell the user what
   this run actually cost and the running total: report `actual_usd_display` ("this
   run") and `total_spend_usd_display` ("total so far on this machine"), on every
   paid run. When a long file took several passes, the meaningful figure is the
   cumulative total across the passes. This actual figure is the real post-run cost
   (token counts for the gpt-4o-* models, duration for whisper-1), not the pre-run
   estimate. Mention any files with an error status. Do not paste transcript content
   into chat unless asked for specific rows.
9. **To translate the transcripts**, transcribe with `--format txt` (or `md`), then
   use the document translator on that file (see
   [`user-data-translation.md`](user-data-translation.md), the `translate-doc`
   command). Do not feed a long transcript through the per-cell CSV translator.

### Running it: use the CLI

Prefer the CLI: it handles credentials itself and prints JSON you can report
from. Run it with the interpreter that `setup_env.py` printed
(`VENV_PYTHON=<path>`); `python3` alone will not have `openai` installed.
`transcription.py` lives in the skill's `assets/transcribe-translate/` directory,
and ffmpeg/ffprobe must be on PATH.

```bash
PY=<the VENV_PYTHON path from setup_env.py>
# 1. estimate: shows known_seconds, estimated_usd_display, pii_warning -> show the user, get confirmation
"$PY" assets/transcribe-translate/transcription.py estimate audio/r1.mp3 audio/r2.mp3
# 2. transcribe (only after confirmation). Use --max-seconds set ~5s below your
#    command-timeout (e.g. 40 for a 45s cap). Many short clips -> --format csv (joins
#    back to a dataset); a few long recordings -> --format md or txt (readable doc).
"$PY" assets/transcribe-translate/transcription.py transcribe audio/r1.mp3 audio/r2.mp3 \
    --output transcripts.csv --max-seconds 40 --confirm
```

Exit code 3 means "incomplete, re-run to resume"; 0 means done. For a long file,
issue the SAME command again as a new command each time it returns 3, until it
returns 0. Run one command per pass; never put it in a `while` loop (the loop is cut
off by the command-timeout and orphans a process). `--cache` defaults to a local
path; only pass one explicitly if you want a specific location (not a mounted
folder).

Equivalent inside a generated Python script (run under the same interpreter). The
helper modules live in the skill's `assets/transcribe-translate/` directory (whose
name has a hyphen, so it is not importable as a package); add it to `sys.path`
before importing:

```python
import sys
sys.path.insert(0, "assets/transcribe-translate")   # path to the skill's module dir
import openai_auth, transcription
openai_auth.configure_openai()
est = transcription.estimate_cost(["audio/r1.mp3","audio/r2.mp3"])
# show est["estimated_usd_display"], est["known_seconds"], est["pii_warning"]; confirm
stats = transcription.transcribe_files(
    ["audio/r1.mp3","audio/r2.mp3"], output_path="transcripts.csv",
    cache_path="transcription-cache.db", confirm=True)   # model="fast" by default
# library call defaults to running to completion; pass max_seconds=<n> to bound a
# call and re-call while stats["incomplete"] is True to resume long files.
print(stats["output_path"], stats["transcribed"], stats["cached"],
      stats["failed"], stats["incomplete"])
```

## Caching

Pass a `cache_path` (e.g. `transcription-cache.db`) so re-running a batch only
transcribes files not seen before (keyed on file bytes + model + language). The
cache holds transcript text, so it is sensitive: the module creates it chmod 0600,
but the `.gitignore` in this skill's source repo does not travel with the packaged
skill, so in the user's own project place the cache (and the output CSV) outside
any version-controlled folder, or add them to that project's ignore list.

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
- Translating transcripts is a separate step: transcribe with `--format txt`, then
  run the `translate-doc` command in
  [`user-data-translation.md`](user-data-translation.md) on that file.

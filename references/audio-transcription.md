<!-- PRIMER: audio-transcription
  STATUS: drafted 2026-06-13 -->

# Transcribing audio (audio audits, voice responses)

This primer covers transcribing SurveyCTO audio captures into text using OpenAI
(default) or a local Whisper model. It is the audio analog of user-data
translation and uses the same OpenAI credential handling.

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

## Model and provider selection (cheapest is the default)

Transcription model menu (OpenAI cloud):

- `fast` -> `gpt-4o-mini-transcribe` (DEFAULT; cheapest, ~$0.003/audio-min)
- `accurate` -> `gpt-4o-transcribe` (~$0.006/audio-min)
- `whisper` -> `whisper-1` (~$0.006/audio-min)

Pass `--model fast|accurate|whisper` (or an explicit model id). There is also a
local provider (`--provider local`) for data-residency/offline use; see "Local
provider" below for its requirements and what to expect.

### Local provider (faster-whisper): requirements and what to expect

`--provider local` runs Whisper on-device via faster-whisper (no API key, no
per-minute cost, audio never leaves the machine). Install it with
`python3 setup_env.py --local`. Pick the model with `--local-model`
(default `small`).

Who it is for: users with data-governance rules that forbid sending audio to a
third party, offline/air-gapped work, or large back-catalogs where the per-minute
cloud cost adds up. The trade-off is a one-time model download, local compute
time, and slightly lower accuracy than the cloud models.

Reassure the user about "on-device": the **first run downloads the model once
from the internet** (Hugging Face), and a harmless "unauthenticated requests to
the HF Hub / set a HF_TOKEN" notice may appear during that download. That is the
model weights being fetched, not the audio. After the model is cached,
transcription runs **fully offline, and the audio is never uploaded**.

Local is not the default. When the user's policy requires on-device processing,
pass `--provider local` on every transcription command; without it the default
cloud path uploads to OpenAI. The estimate's `pii_warning` reflects the chosen
provider, so check it says on-device before confirming a privacy-sensitive run.

Before picking a model, check the machine and let it recommend one. Run the
shipped checker (works on Windows, Linux, and macOS, standard library only):

```
python3 system_check.py            # human-readable specs + recommended model
python3 system_check.py --json     # machine-readable (os, cpu_cores, ram_gb, has_nvidia_gpu, recommendation)
```

It reports OS, CPU cores, RAM, and whether an NVIDIA GPU is present, then
recommends a `--local-model` and lists which models are feasible vs. best avoided
on that hardware. Use its `recommended` value as the default `--local-model`, and
tell the user the rationale (e.g. "your machine has no NVIDIA GPU and 8 GB RAM, so
`small` is the right fit; `medium`/`large-v3` would be slow here"). The mapping:
an NVIDIA GPU (CUDA) can run `large-v3`; a CPU-only machine (including Apple
Silicon, which CTranslate2 does not GPU-accelerate) should use `small` by default,
`base`/`tiny` on low RAM, and `medium`/`large-v3` only with ample RAM and patience.
If the machine is too weak for acceptable local quality, suggest the cloud
provider instead.

Hardware support (faster-whisper uses CTranslate2). It runs on Windows, Linux,
and macOS, on **any modern CPU** (Intel, AMD, or Apple Silicon); a GPU is optional:

- Any modern x86-64 CPU (Intel/AMD) on Windows or Linux, and Apple Silicon on
  macOS: works on the default `small` model (CPU execution; this is the common
  case and needs no GPU).
- NVIDIA GPU (CUDA): fastest, and makes the larger models practical. The only
  GPU acceleration CTranslate2 offers; Apple Silicon GPUs (Metal) are not used,
  so a Mac runs on its CPU.
- Old/low-core CPUs or low RAM (any platform): usable with `tiny`/`base`, but
  slow; avoid the larger models.

Models, download size, RAM, and measured CPU speed. The model is downloaded once
and then cached under `~/.cache/huggingface`. The download size and "CPU time"
columns for `small`/`medium`/`large-v3` are measured on a 14-core Apple Silicon
laptop (24 GB), CPU-only, transcribing one 7.8-minute (469s) recording; `tiny`
and `base` sizes are approximate (not run here) and RAM is approximate:

| `--local-model` | download | RAM (int8) | CPU time for ~7.8 min audio | accuracy |
| --- | --- | --- | --- | --- |
| `tiny`     | ~75 MB (approx)  | <1 GB | not benchmarked (fastest) | lowest |
| `base`     | ~145 MB (approx) | ~1 GB | not benchmarked | low |
| `small` (default) | 464 MB | ~2 GB | ~54s (~8-9x faster than real time) | good |
| `medium`   | 1.4 GB | ~5 GB | ~175s (~2.7x faster than real time) | high |
| `large-v3` | 2.9 GB | ~8 GB | ~286s (~1.6x faster than real time) | highest |

So on a recent multi-core CPU, expect roughly: `small` ~1 min of processing per
8-9 min of audio, `medium` ~1 min per ~3 min, `large-v3` close to real time. An
NVIDIA GPU is substantially faster and makes the large model practical; an old or
low-core CPU is slower, so prefer `small` (or `tiny`/`base`) there. All three
benchmarked models produced coherent transcripts of the same clip; `large-v3` is
the most accurate, `small` the best speed/quality balance for CPU-only machines.

Model-download time is one-time and bandwidth-bound. Estimates by size: the 464 MB
`small` model is ~12 min at 5 Mbps, ~2.5 min at 25 Mbps, ~40s at 100 Mbps; scale
up roughly 3x for `medium` (1.4 GB) and 6x for `large-v3` (2.9 GB). On the test
machine's connection the downloads themselves took only ~30-50s, but plan for the
slower end on a constrained link before choosing a large model.

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

- `estimate_cost(audio_paths, model=None, provider="openai")` sums duration and
  returns the estimated USD cost (0 for local), files whose duration could not be
  read in `unknown_duration`, and the PII warning.
- `transcribe_files(audio_paths, output_path, model=None, provider="openai",
  cache_path=None, confirm=False, local_model="small")` transcribes a batch and
  writes a CSV (`file`, `transcript`, `backend`, `duration_seconds`, `status`).

Built in: a confirm-gate cost check, per-file failure isolation (a bad file gets
an error status; the batch continues), caching (keyed on file bytes + model so
re-runs are free), automatic chunking, and sanitized errors (an API error never
echoes audio content).

## Workflow

1. **Confirm credentials and environment.** If "no OpenAI API key configured"
   appears, switch to the coaching in
   [`openai-credentials.md`](openai-credentials.md). Install the client library by
   running the bootstrap once (`python3 setup_env.py`, or
   `python3 setup_env.py --local` when using `--provider local`); it prints a
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
   privacy reminder that the audio is sent to OpenAI (or that `--provider local`
   keeps it on-device).
5. **Wait for explicit confirmation** before transcribing.
6. **Transcribe.** Call `transcribe_files(...)` with `confirm=True` and a
   `cache_path` so re-runs are cheap.
7. **Report, including spend.** Give the output CSV path and the stats
   (transcribed, cached, failed). For OpenAI runs, always tell the user what this
   run actually cost and the running total: report `actual_usd_display` ("this
   run") and `total_spend_usd_display` ("total so far on this machine"), on every
   paid run. (Local runs are free and report `$0.00`.) Mention any files with an
   error status. Do not paste transcript content into chat unless asked for
   specific rows.

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
# 2. transcribe (only after confirmation). Add --provider local to keep audio on-device.
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

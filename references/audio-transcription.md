<!-- PRIMER: audio-transcription
  STATUS: drafted 2026-06-06 -->

# Transcribing audio (audio audits, voice responses)

This primer covers **transcribing SurveyCTO audio captures** into text using
Google Cloud Speech-to-Text: audio-audit recordings and open-ended voice
responses. It is the audio analog of user-data translation and uses the same
credential handling.

Read [`google-cloud-credentials.md`](google-cloud-credentials.md) first (the
same service-account file works for both translation and transcription). The
user-data translation primer ([`user-data-translation.md`](user-data-translation.md))
shares the same design philosophy and is worth reading alongside this one.

## Why this runs as a script, not in conversation

Audio recordings carry respondents' voices and frequently spoken PII (names,
places). Like user-data translation, the content must not pass through the
agent's context. The agent runs the shipped module
[`assets/google-cloud/transcription.py`](../assets/google-cloud/transcription.py),
which reads the audio bytes, sends them directly to Google Cloud Speech-to-Text,
and writes a transcripts CSV to disk. The agent orchestrates and reports; it
does not listen to or ingest the audio.

A natural follow-on: once audio is transcribed to a CSV, the transcript column
can be translated with the user-data translation workflow.

## What the module gives you

[`assets/google-cloud/transcription.py`](../assets/google-cloud/transcription.py)
exposes:

- `estimate_cost(audio_paths, model="default")` sums audio duration and returns
  the estimated USD cost and free-tier status. It reads duration from WAV
  headers directly, and from other formats via `ffprobe` if it is installed;
  files whose duration cannot be determined are returned in
  `unknown_duration` so you can ask the user.
- `transcribe_files(audio_paths, language_code, output_path, model="default",
  cache_path=None, confirm=False)` transcribes a batch and writes a CSV.
- `transcribe_file(audio_path, language_code, model="default")` transcribes a
  single file and returns the result.

Built into `transcribe_files`:

- **Cost gate.** It refuses to run unless `confirm=True`. Always call
  `estimate_cost` and confirm with the user first.
- **Caching.** With a `cache_path`, transcripts are memoized in SQLite keyed on
  a hash of the file bytes, the language code, and the model. Re-running over the
  same files is free.
- **Per-file failure isolation.** A file that errors is recorded with an error
  status and an empty transcript; the rest of the batch still completes.
- **Never modifies the source audio.** Output is a new CSV with columns `file`,
  `transcript`, `confidence`, `duration_seconds`, `status`.

## Size and format notes

- The module sends audio inline, which Google limits to about 10 MB per file.
  Files over that limit are flagged with an error status rather than failing the
  whole batch. For longer recordings, split them into shorter clips, or upload to
  Google Cloud Storage and use the long-form API (out of scope for this helper).
- Common formats are recognized by extension (`.wav`, `.flac`, `.mp3`, `.ogg`,
  `.opus`, `.webm`, `.amr`). WAV and FLAC carry their encoding in the header, so
  those need no extra hints; for others the module passes the encoding hint
  Google needs.
- `language_code` is a BCP-47 code (`en-US`, `es-ES`, `sw-KE`, `fr-FR`, ...),
  not the ISO 639-1 code used for translation. Ask the user for the spoken
  language and region if it matters.

### FFmpeg (recommended for non-WAV audio)

Cost estimation needs each file's duration. WAV durations are read directly with
the standard library, but for compressed formats (`.mp3`, `.m4a`, `.ogg`,
`.flac`, ...) the module reads the duration with `ffprobe`, which ships with
FFmpeg. If FFmpeg is not installed, those files appear in `unknown_duration` and
the upfront cost estimate excludes them (transcription itself still works). When
the audio is not WAV and `estimate_cost` returns files in `unknown_duration`,
recommend installing FFmpeg so the estimate is complete:

- macOS: `brew install ffmpeg`
- Debian/Ubuntu: `sudo apt-get install ffmpeg`
- Windows: download from https://ffmpeg.org/download.html, or `choco install ffmpeg`

This is a recommendation, not a hard requirement: the workflow degrades
gracefully without it.

## Workflow: transcribe a batch of audio files

1. **Confirm credentials are set up.** If the credential check raises "no
   credentials configured", switch to the coaching flow in
   [`google-cloud-credentials.md`](google-cloud-credentials.md). Confirm the
   client library is installed (`pip install google-cloud-speech`).
2. **Collect the audio paths.** SurveyCTO audio-audit and voice-response files
   are usually in the media folder of an export. Ask the user where they are if
   unclear.
3. **Get the spoken language** as a BCP-47 code. Ask if unspecified.
4. **Estimate cost and show the PII warning.** Call `estimate_cost(...)`. Show
   the user the total duration, the estimated USD cost, free-tier status, and the
   list of any files whose duration could not be determined. Show the one-line
   privacy reminder that the audio will be sent to Google's servers.
5. **Wait for explicit confirmation.** Do not proceed until the user confirms,
   even if they said "just do it" up front.
6. **Transcribe.** Call `transcribe_files(...)` with `confirm=True` and a
   `cache_path` so re-runs are cheap.
7. **Report.** Tell the user the output CSV path and summarize the returned
   stats: how many files were transcribed, served from cache, and failed.
   Mention any files with an error status so the user can address them (often a
   too-large file or an unsupported format). Do not paste transcript content
   into the conversation unless the user explicitly asks to see specific rows.

Example (inside a generated script):

```python
import google_cloud_auth
import transcription

google_cloud_auth.configure_google_auth()

est = transcription.estimate_cost(["audio/r1.wav", "audio/r2.wav"])
# show est["estimated_usd"], est["known_seconds"], est["unknown_duration"],
# est["pii_warning"] to the user
# ... after the user confirms ...
stats = transcription.transcribe_files(
    ["audio/r1.wav", "audio/r2.wav"],
    language_code="en-US",
    output_path="transcripts.csv",
    cache_path="transcription-cache.db",
    confirm=True,
)
print(stats["output_path"], stats["transcribed"], stats["cached"], stats["failed"])
```

## Caching

Pass a `cache_path` (for example `transcription-cache.db`) so re-running a batch
only transcribes files not seen before. The cache contains transcript text, so
it is sensitive: store it with the user's data, not in a shared or
version-controlled location. The skill `.gitignore` template ignores the default
cache name.

## Quality reminder

Automatic speech recognition quality varies a lot with audio quality, accent,
background noise, and language coverage. The `confidence` column is a useful
triage signal: low-confidence rows deserve a human listen. For anything
high-stakes, recommend that a fluent speaker review a sample against the audio.
This is a recommendation, not a gate.

## Out of scope

- Speaker diarization, word-level timestamps, and streaming transcription are
  not wired up in this helper; they are available in the Speech-to-Text API if a
  future need warrants.
- Translating the transcripts is a separate step: transcribe to a CSV here, then
  use [`user-data-translation.md`](user-data-translation.md) on the transcript
  column.
- Audio formats beyond the recognized extensions, and files over the inline size
  limit, need preprocessing (conversion or splitting) the user performs first.

# Google Cloud helpers (translation and transcription)

Runtime modules the agent runs to translate user data and transcribe audio via
Google Cloud, keeping the user's service-account secret out of the conversation.

These support two reference primers; read those for the agent-facing workflow:

- [`references/google-cloud-credentials.md`](../../references/google-cloud-credentials.md)
  credential handling and the "never read the file" mandate (shared).
- [`references/user-data-translation.md`](../../references/user-data-translation.md)
  translating response/comment columns in a CSV.
- [`references/audio-transcription.md`](../../references/audio-transcription.md)
  transcribing audio captures.

## Files

| File | Purpose | Import-time deps |
| --- | --- | --- |
| `google_cloud_auth.py` | Resolve the credentials path and point Google at it via `GOOGLE_APPLICATION_CREDENTIALS`, without ever opening the file. Shared by both capabilities. | standard library only |
| `translation.py` | Estimate cost, detect languages, translate CSV columns, apply a glossary. | standard library only |
| `transcription.py` | Estimate cost, transcribe audio files to a CSV. | standard library only |

The Google client libraries are imported lazily, only when a call actually
reaches the API, so importing these modules and running their logic needs no
Google packages. Install what the task needs:

```
pip install google-cloud-translate     # translation
pip install google-cloud-speech        # transcription
```

For transcription cost estimates on non-WAV audio (`.mp3`, `.m4a`, `.ogg`,
`.flac`, ...), FFmpeg is recommended: its `ffprobe` reads the audio duration.
WAV durations need no extra tool. Without FFmpeg, non-WAV files are reported as
`unknown_duration` and excluded from the estimate; transcription still works.
Install with `brew install ffmpeg` (macOS), `sudo apt-get install ffmpeg`
(Debian/Ubuntu), or from https://ffmpeg.org/download.html (Windows).

## Quick use

```python
import google_cloud_auth, translation
google_cloud_auth.configure_google_auth()
est = translation.estimate_cost("data.csv", ["notes"], "en")   # show to user, confirm
translation.translate_csv("data.csv", ["notes"], "en", None,
                          "data_en.csv", cache_path="translation-cache.db",
                          confirm=True)
```

```python
import google_cloud_auth, transcription
google_cloud_auth.configure_google_auth()
est = transcription.estimate_cost(["a.wav"])                    # show to user, confirm
transcription.transcribe_files(["a.wav"], "en-US", "out.csv",
                               cache_path="transcription-cache.db", confirm=True)
```

Each module also has a CLI; run with `--help`.

## The credential rule, in code

`google_cloud_auth` never opens the service-account file. It only checks that
the file exists and reads or writes the *path string* (which is not secret). The
Google client library, constructed afterward, is the only thing that opens the
file. The cost functions and the `confirm=True` gate ensure no paid API call
runs without an explicit, cost-aware go-ahead.

## Tests

Offline tests (standard library only, no network, no Google packages) live in
the repo `tests/` directory:

```
python3 tests/test_google_cloud_auth.py
python3 tests/test_translation.py
python3 tests/test_transcription.py
```

They use injected fake clients, so they exercise all the surrounding logic
(credential resolution, the never-open guarantee, skip-list, cost math, caching,
de-duplication, glossary, backoff, per-file failure isolation) without reaching
Google.

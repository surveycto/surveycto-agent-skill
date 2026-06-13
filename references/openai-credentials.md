<!-- PRIMER: openai-credentials
  STATUS: drafted 2026-06-13 -->

# OpenAI credentials for translation and transcription

This primer covers how the skill authenticates to OpenAI for the user-data
translation ([`user-data-translation.md`](user-data-translation.md)) and audio
transcription ([`audio-transcription.md`](audio-transcription.md)) workflows,
without ever exposing the user's API key. Read this before either.

The mechanics live in
[`assets/transcribe-translate/openai_auth.py`](../assets/transcribe-translate/openai_auth.py),
so neither the agent nor a generated script reinvents credential handling.

## What the credential is

OpenAI authenticates with a **single API key string** that looks like
`sk-...`. Unlike a file path, the key value itself is the secret.

## AGENT INSTRUCTIONS: NEVER REVEAL THE KEY

You, the agent, must NEVER:

- Print, echo, repeat, or summarize the API key value, not in chat, not in a
  tool result, not in a code block, not in a commit, not in a log.
- Write the key into any output file, the translated/transcribed CSV, a config
  you might display, or the conversation transcript.
- Pass the key as a visible command-line argument that gets shown back to the
  user (store it once, then reference it via the helper or the environment).

The user may give you the key in chat. When they do, record it once with the
helper and then never reproduce it:

```python
import openai_auth
openai_auth.save_api_key("<the key the user gave you>")  # stored chmod 600; never printed
```

At the start of any script that calls OpenAI, point the SDK at the key without
revealing it:

```python
import openai_auth
openai_auth.configure_openai()   # sets OPENAI_API_KEY in the environment; never prints it
```

The helper enforces this in code: `save_api_key` writes the key to
`~/.surveycto-skill/openai-config.json` (chmod 600) and `credentials_status()`
only ever returns a masked form (`sk-abc12...wxyz`). Error messages never
contain key material.

## How resolution works

`configure_openai()` resolves the key in this order:

1. The `OPENAI_API_KEY` environment variable (OpenAI's standard convention; honored
   first, so a user with an existing setup needs no extra steps).
2. The key stored in `~/.surveycto-skill/openai-config.json`.
3. Otherwise it raises a clear error pointing here (with no key material).

Check setup state without revealing the key:

```
python3 openai_auth.py status      # prints the source and a masked key only
```

## COACHING THE USER

If `configure_openai()` raises a "no OpenAI API key configured" error, walk the
user through the steps below. The same key works for both translation and
transcription, so you only coach this once.

### Step 1: Create an OpenAI account and add billing

> 1. Go to https://platform.openai.com and sign in (or create an account).
> 2. Add a payment method under Settings, then Billing. The API is pay-as-you-go
>    and cheap for this use: transcription is roughly $0.003 to $0.006 per minute
>    of audio, and translating a column of survey responses is usually a few
>    cents. Consider setting a low monthly usage limit on the Billing page so
>    there are no surprises.

### Step 2: Create an API key

> 1. Go to https://platform.openai.com/api-keys
> 2. Click "Create new secret key", give it a name like "surveycto", and create it.
> 3. Copy the key now. OpenAI shows it only once. It looks like `sk-...`.

### Step 3: Give the agent the key (or set it yourself)

Paste the key to the agent in chat and it will store it securely, or set it
yourself in a terminal:

```
export OPENAI_API_KEY=sk-...        # for the current session, or
python3 openai_auth.py set sk-...     # stores it (readable only by you)
```

The agent will store it with the helper and will never show it back to you. If
you pasted the key into a chat, treat it as exposed there and rotate it later if
that chat is shared or logged.

### Step 4: Install the client library

Run the shipped bootstrap once. It creates an isolated environment and installs
`openai` into it:

```
python3 setup_env.py            # translation + transcription
```

It prints the environment's Python interpreter on the last line as
`VENV_PYTHON=<path>`. Use that interpreter to run every module from here on, for
example `<path> translation.py ...` and `<path> transcription.py ...`.

Do NOT rely on a bare `pip install openai`. On modern macOS (Homebrew) and recent
Debian/Ubuntu, the system Python is "externally managed" (PEP 668) and a direct
`pip install` fails with `error: externally-managed-environment`. `setup_env.py`
sidesteps this on every platform by installing into a dedicated virtual
environment, and it is idempotent (safe to re-run). The helper and the workflow
modules themselves import only the standard library; `openai` is needed only to
reach the API.

For transcription only, `ffmpeg` (which provides `ffprobe`) must also be on PATH;
it measures audio duration and splits long files. Install it with
`brew install ffmpeg` (macOS), `sudo apt-get install ffmpeg` (Debian/Ubuntu), or
from https://ffmpeg.org (Windows). Translation does not need it.

### Step 5: Retry

Once the key is stored and the library is installed, retry the operation. Never
ask the user to paste the key again or to show it back.

## Tracking spend

Both paid workflows record actual cost after each run in a small ledger at
`~/.surveycto-skill/spend-ledger.json` (costs and model names only, never source
text, transcripts, or the key). `translate_csv`/`transcribe_files` return
`actual_usd_display` (this run) and `total_spend_usd_display` (cumulative on this
machine); surface both to the user on every paid run so they always know what
they are spending.

The user (or you) can see the running total at any time:

```
python3 usage_ledger.py show     # prints cumulative OpenAI spend, by operation
python3 usage_ledger.py reset    # clears the history
```

## Security checklist for generated scripts

- [ ] Calls `openai_auth.configure_openai()`; never reads or prints the key value.
- [ ] Never writes the key into output CSVs, logs, a committed config, or chat.
- [ ] Treats any cache file (it contains source text or transcripts) as
      sensitive and keeps it out of version control (the skill `.gitignore`
      covers the default cache names).

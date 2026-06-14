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

- Ask the user to paste their API key into the chat, and never accept it there.
  Chat text is persisted in history and cloud/admin logs, so a pasted key is
  compromised from that moment and every other safeguard is moot. Use the file
  handoff in "Coaching the user" instead.
- Print, echo, repeat, or summarize the API key value, not in chat, not in a
  tool result, not in a code block, not in a commit, not in a log.
- Read or `cat` the user's key file or `~/.surveycto-skill/openai-config.json`
  into the conversation. Import the key file with the helper command (which never
  prints it); do not open it yourself.
- Write the key into any output file, the translated/transcribed CSV, a config
  you might display, or the conversation transcript.
- Pass the key as a visible command-line argument (e.g. `openai_auth.py set
  sk-...`) in an environment whose commands are logged; prefer the file handoff.

If the user pastes the key into chat anyway, tell them it should be treated as
exposed and rotated, and switch to the file handoff for the actual setup.

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

### Step 3: Hand the key over via a file (never via chat)

Do not have the user paste the key into the chat, and do not tell them to
`export OPENAI_API_KEY=...` in their own terminal. In hosted/sandboxed runtimes
(e.g. Cowork) the skill runs in an isolated environment that cannot see the
user's terminal, so a shell `export` or `openai_auth.py set` in their terminal
never reaches it; and anything typed in chat is logged. Use a file the user edits
in the working folder:

1. Write the key file for them:

   ```
   python3 openai_auth.py template        # writes ./openai-key.txt with a placeholder
   ```

2. Tell the user, in chat:

   > I created `openai-key.txt` in the working folder. Open it, replace the
   > placeholder line with your OpenAI API key (`sk-...`), save, and tell me when
   > it is ready. Do not paste the key into this chat.

3. When they confirm, import it. This stores the key in the chmod-600 config and
   deletes the file; it never prints the key:

   ```
   python3 openai_auth.py import-file openai-key.txt
   ```

Do not open, read, or `cat` `openai-key.txt` yourself; only run the import
command. (Advanced/non-sandboxed users who already have the key in their
environment can instead set `OPENAI_API_KEY`, which `configure_openai()` honors
first.)

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
- [ ] Onboards the key via the file handoff (`template` then `import-file`), never
      via chat-paste or a terminal `export`; never opens/`cat`s the key file or
      config (the skill `.gitignore` covers `openai-key.txt` and the config).
- [ ] Never writes the key into output CSVs, logs, a committed config, or chat.
- [ ] Treats any cache file (it contains source text or transcripts) as
      sensitive and keeps it out of version control (the skill `.gitignore`
      covers the default cache names).

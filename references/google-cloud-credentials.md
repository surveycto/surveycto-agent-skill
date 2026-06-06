<!-- PRIMER: google-cloud-credentials
  STATUS: drafted 2026-06-06 -->

# Google Cloud credentials for translation and transcription

This primer covers how the skill authenticates to Google Cloud services
(Translation and Speech-to-Text) **without ever exposing the user's secret to
the conversation or the logs**. Both the user-data translation workflow
([`user-data-translation.md`](user-data-translation.md)) and the audio
transcription workflow ([`audio-transcription.md`](audio-transcription.md))
depend on it. Read this before either.

The mechanics are implemented once, in
[`assets/google-cloud/google_cloud_auth.py`](../assets/google-cloud/google_cloud_auth.py),
so neither the agent nor any generated script needs to reinvent credential
handling.

## Why Google Cloud is different from a single API key

Google Cloud authenticates with a **service-account JSON file**, not a single
API key string. The user downloads that file from the Google Cloud Console; it
contains a private key.

The crucial distinction:

- **The file's contents are secret.** They include a private key that grants
  access to the user's Google Cloud project.
- **The path to the file is not secret.** It is just a location on disk.

Everything below follows from that distinction.

## AGENT INSTRUCTIONS: DO NOT READ THE CREDENTIALS FILE

The skill authenticates using a service-account JSON file at a path the user
provides. You, the agent, must NEVER do any of the following:

- Run `cat`, `view`, `head`, `tail`, `less`, `more`, or any other command that
  prints the credentials file.
- Open, parse, or otherwise inspect the JSON contents, even to "verify the
  project ID" or "check the client email".
- Pass the file contents as an argument to any command.
- Read the file in any generated script for any reason other than letting the
  Google client library read it via `GOOGLE_APPLICATION_CREDENTIALS`.
- Echo, print, or log the file contents anywhere, including in summaries to the
  user.

The path string itself is not secret. The user will tell you the path in
conversation; you may store it, say it back to confirm it, and pass it to
scripts. The *file at that path* must remain unread by you.

The only legitimate use of the path is to set the
`GOOGLE_APPLICATION_CREDENTIALS` environment variable before constructing a
Google client. The helper does exactly this and is the only entry point you
should use:

```python
import google_cloud_auth
google_cloud_auth.configure_google_auth()  # sets the env var; never opens the file
```

The helper enforces this in code: it only ever checks that the file exists
(`os.path.isfile`) and writes or reads the *path string*. It never opens the
service-account file. The Google client library, constructed afterward, is the
only thing that opens it, and it does so internally.

Checking that the file exists with `os.path.isfile` is fine. Reading its
contents is not.

## How resolution works

`configure_google_auth()` resolves the credentials path in this order:

1. The `GOOGLE_APPLICATION_CREDENTIALS` environment variable, if set (Google's
   official convention; honored first so a user with an existing setup works
   without extra configuration).
2. The path stored at `~/.surveycto-skill/google-cloud-config.json`.
3. If neither is present, it raises a clear error pointing here.

You record the path in step 2 once, at setup:

```python
import google_cloud_auth
google_cloud_auth.save_credentials_path("/Users/me/Documents/surveycto-cloud-key.json")
```

To check setup state without touching the file, use
`google_cloud_auth.credentials_status()` (returns the path and existence flags
only) or the CLI:

```
python google_cloud_auth.py status
```

## COACHING THE USER

If `configure_google_auth()` raises a "no credentials configured" error, walk
the user through the steps below. Do NOT attempt to create or download a service
account on their behalf. They must do this in their own browser.

The same service account works for both translation and transcription, so you
only coach this once per user.

### Step 1: Create a Google Cloud project and enable the API

> 1. Go to https://console.cloud.google.com in your browser.
> 2. Sign in with a Google account. A personal Gmail account works fine for
>    getting started.
> 3. At the top of the page, click the project dropdown (it may say "Select a
>    project") and click "NEW PROJECT". Give it a name like
>    "surveycto-cloud" and click "CREATE".
> 4. Once the project is created, select it from the dropdown.
> 5. In the search bar at the top, enable the API you need:
>    - For translation: search "Cloud Translation API" and click "ENABLE".
>    - For transcription: search "Cloud Speech-to-Text API" and click "ENABLE".
>    You can enable both now if you expect to use both.
> 6. Google will ask you to set up billing if you have not already. Both
>    services have a permanent free tier (Translation: 500,000 characters per
>    month; Speech-to-Text: 60 minutes per month), so typical SurveyCTO use is
>    often free, but Google requires a billing account on file.

### Step 2: Create a service account and download its key

> 1. In the search bar, type "Service Accounts" and select it.
> 2. Click "CREATE SERVICE ACCOUNT" at the top.
> 3. Give it a name like "surveycto-cloud" and click "CREATE AND CONTINUE".
> 4. For the role, add "Cloud Translation API User" and/or "Cloud Speech
>    Client" depending on what you enabled. Click "CONTINUE", then "DONE".
> 5. In the list of service accounts, click the one you just created.
> 6. Go to the "KEYS" tab.
> 7. Click "ADD KEY", then "Create new key", select "JSON", and click "CREATE".
> 8. A JSON file downloads to your computer. Move it somewhere you will
>    remember, like `~/Documents/surveycto-cloud-key.json` (macOS/Linux) or
>    `C:\Users\YourName\Documents\surveycto-cloud-key.json` (Windows). Note the
>    full path.

### Step 3: Restrict file permissions (macOS/Linux only)

> Open a terminal and run (adjust the path to where you saved the file):
>
>     chmod 600 ~/Documents/surveycto-cloud-key.json
>
> This makes the file readable only by your user account.

### Step 4: Tell the agent the path

Ask the user to paste the full path to the JSON file into chat. Once they do,
record it:

```python
import google_cloud_auth
google_cloud_auth.save_credentials_path("<the path the user gave>")
```

Confirm the path by saying it back to the user and asking them to confirm it is
correct. Do NOT open or read the file at that path. Verifying it exists is fine;
reading its contents is not.

### Step 5: Install the client library

The runtime scripts need the relevant Google client library. Install only what
the task needs:

```
pip install google-cloud-translate     # for translation
pip install google-cloud-speech        # for transcription
```

(Use `pip3`, `python -m pip`, or `uv pip` as appropriate for the user's
environment.) The helper and the workflow modules import only the standard
library; the Google packages are needed only to actually reach the API.

### Step 6: Retry

Once the path is recorded and the library is installed, retry the operation. Do
NOT ask the user to open or share the contents of the JSON file at any point.

## Security checklist for generated scripts

When you write a script that uses these services, confirm:

- [ ] It calls `google_cloud_auth.configure_google_auth()` and never reads the
      credentials file itself.
- [ ] It never prints, logs, or passes the file contents anywhere. The path
      string is fine; the contents are not.
- [ ] It does not write the credentials path or contents into the translated or
      transcribed output, into a committed config, or into the conversation.
- [ ] Any cache file (translation or transcription) is treated as sensitive: it
      contains source text or transcripts. Keep it out of version control (the
      skill `.gitignore` template covers the default names).

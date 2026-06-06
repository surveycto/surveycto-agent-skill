"""Credential resolution for Google Cloud services (Translation, Speech-to-Text).

Google Cloud authenticates with a *service-account JSON file*, not a single
API key. That file contains a private key, so its contents are secret. The
*path* to the file is not secret.

This module exists so that the agent never has to read, parse, or echo the
service-account file. It resolves the *path* from the environment or a small
config file, points the Google client libraries at it by setting
``GOOGLE_APPLICATION_CREDENTIALS``, and returns. The Google client library is
then the only thing that ever opens the file, which it does internally.

The single hard rule this module enforces in code: it never opens the
service-account file. It only ever checks that the file exists
(``os.path.isfile``) and writes/reads the *path string* to/from its own config
file. Error messages carry the path string (not secret) but never any file
contents.

Usage (Python)::

    import google_cloud_auth

    # one-time setup, after the user shares the path in conversation:
    google_cloud_auth.save_credentials_path(
        "/Users/me/Documents/surveycto-cloud-key.json")

    # at the start of any script that talks to Google Cloud:
    google_cloud_auth.configure_google_auth()

Usage (CLI)::

    python google_cloud_auth.py set /path/to/service-account.json
    python google_cloud_auth.py status     # prints path + whether it exists
                                            # never prints file contents

This helper is shared by the translation and audio-transcription capabilities.
See ``references/google-cloud-credentials.md`` for the agent-facing mandate and
the user-coaching walkthrough.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

CONFIG_DIR = Path.home() / ".surveycto-skill"
CONFIG_PATH = CONFIG_DIR / "google-cloud-config.json"

_ENV_VAR = "GOOGLE_APPLICATION_CREDENTIALS"
_CONFIG_KEY = "google_credentials_path"


def save_credentials_path(path: str) -> None:
    """Record the path to the user's Google service-account JSON file.

    Called once at setup, after the user shares the path in conversation. The
    path string is stored; the file at the path is never opened.

    :param path: Path to the service-account JSON file. ``~`` is expanded.
    :raises FileNotFoundError: If no file exists at the given path.
    """
    expanded = os.path.expanduser(path)
    if not os.path.isfile(expanded):
        raise FileNotFoundError(
            f"No file exists at '{path}'. Check the path and try again."
        )
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump({_CONFIG_KEY: expanded}, f, indent=2)
    # Best effort: keep the config (which holds only the path) readable by the
    # owner alone. Not security-critical, since the path is not secret.
    try:
        os.chmod(CONFIG_PATH, 0o600)
    except OSError:
        pass


def _resolve_credentials_path() -> str:
    """Resolve the credentials file path from the environment or config.

    Resolution order:

    1. ``GOOGLE_APPLICATION_CREDENTIALS`` environment variable (Google's
       official convention; honored first so existing setups work unchanged).
    2. Path stored in :data:`CONFIG_PATH`.
    3. Otherwise, raise.

    :returns: Path to the service-account JSON file.
    :raises RuntimeError: If no path is configured, or a path is configured but
        no file exists there. The message carries only the path string, never
        any file contents.
    """
    path = os.environ.get(_ENV_VAR)

    if not path and CONFIG_PATH.is_file():
        # Reading our own config file (which contains only the path) is fine.
        # The service-account file itself is never opened here.
        with open(CONFIG_PATH, encoding="utf-8") as f:
            config = json.load(f)
        path = config.get(_CONFIG_KEY)

    if not path:
        raise RuntimeError(
            "No Google Cloud credentials path configured. See the "
            "'COACHING THE USER' section of "
            "references/google-cloud-credentials.md for setup instructions."
        )

    path = os.path.expanduser(path)

    # Confirm the file exists, but do NOT open or read it.
    if not os.path.isfile(path):
        raise RuntimeError(
            f"Credentials path '{path}' is configured but no file exists at "
            f"that location. Re-run setup or correct the stored path."
        )

    return path


def configure_google_auth() -> str:
    """Point the Google client libraries at the user's credentials.

    Sets ``GOOGLE_APPLICATION_CREDENTIALS`` to the resolved path so the next
    Google client constructed in this process reads it. This function never
    opens or reads the credentials file.

    :returns: The resolved credentials path (not secret).
    :raises RuntimeError: If credentials are not configured. See
        :func:`_resolve_credentials_path`.
    """
    path = _resolve_credentials_path()
    os.environ[_ENV_VAR] = path
    return path


def credentials_status() -> dict:
    """Report whether credentials are configured, without opening the file.

    Lets the agent check setup state before running a job. Returns the path
    string (not secret) and existence flags only; never file contents.

    :returns: Dict with ``configured`` (bool), ``source`` (``"env"``,
        ``"config"``, or ``None``), ``path`` (str or ``None``), and
        ``file_exists`` (bool).
    """
    env_path = os.environ.get(_ENV_VAR)
    if env_path:
        expanded = os.path.expanduser(env_path)
        return {
            "configured": True,
            "source": "env",
            "path": expanded,
            "file_exists": os.path.isfile(expanded),
        }

    if CONFIG_PATH.is_file():
        with open(CONFIG_PATH, encoding="utf-8") as f:
            config = json.load(f)
        path = config.get(_CONFIG_KEY)
        if path:
            expanded = os.path.expanduser(path)
            return {
                "configured": True,
                "source": "config",
                "path": expanded,
                "file_exists": os.path.isfile(expanded),
            }

    return {"configured": False, "source": None, "path": None, "file_exists": False}


_USAGE = (
    "Usage:\n"
    "  python google_cloud_auth.py set /path/to/service-account.json\n"
    "  python google_cloud_auth.py status"
)


def _main(argv: list[str]) -> int:
    """CLI entry point. Never prints credentials-file contents."""
    if argv and argv[0] in ("-h", "--help"):
        print(_USAGE)
        return 0

    if len(argv) >= 2 and argv[0] == "set":
        try:
            save_credentials_path(argv[1])
        except FileNotFoundError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        status = credentials_status()
        print(f"Recorded credentials path: {status['path']}")
        print(f"Config written to: {CONFIG_PATH}")
        return 0

    if argv and argv[0] == "status":
        status = credentials_status()
        if not status["configured"]:
            print("No Google Cloud credentials configured.")
            print(
                "Run: python google_cloud_auth.py set /path/to/service-account.json"
            )
            return 0
        print(f"Configured via: {status['source']}")
        print(f"Path: {status['path']}")
        print(f"File exists: {status['file_exists']}")
        return 0 if status["file_exists"] else 1

    print(_USAGE, file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1:]))

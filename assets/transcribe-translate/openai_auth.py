"""OpenAI credential handling for the translation and transcription helpers.

OpenAI authenticates with a single API key string (``sk-...``). Unlike a file
path, the key itself is the secret, so the rule this module enforces is: the
agent must NEVER print, echo, log, or paste the key value anywhere. It is
resolved from the environment or a small config file, placed into the
``OPENAI_API_KEY`` environment variable so the OpenAI SDK picks it up, and never
emitted.

Resolution order:

1. ``OPENAI_API_KEY`` environment variable (OpenAI's standard convention).
2. ``~/.surveycto-skill/openai-config.json`` (key stored there, file chmod 600).
3. Raise a clear error pointing to the setup coaching, with NO key material.

Usage (Python)::

    import openai_auth
    openai_auth.save_api_key("sk-...")     # one-time setup; never printed back
    openai_auth.configure_openai()         # sets OPENAI_API_KEY for the SDK

Usage (CLI)::

    python3 openai_auth.py set sk-...        # stores the key (chmod 600)
    python3 openai_auth.py status            # prints source + masked key only

See ``references/openai-credentials.md`` for the agent mandate and the
user-coaching walkthrough.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

CONFIG_DIR = Path.home() / ".surveycto-skill"
CONFIG_PATH = CONFIG_DIR / "openai-config.json"

_ENV_VAR = "OPENAI_API_KEY"
_CONFIG_KEY = "openai_api_key"


def _mask(key: str) -> str:
    """Return a non-reversible display form of a key. Never reveals the secret."""
    if not key:
        return "(empty)"
    if len(key) <= 12:
        return key[:2] + "..." + "(short)"
    return f"{key[:7]}...{key[-4:]} (len {len(key)})"


def save_api_key(key: str) -> None:
    """Record the user's OpenAI API key in the config file (chmod 600).

    The key is written once and never echoed. A minimal sanity check rejects an
    obviously-wrong value, but the error never includes the key.

    :param key: The OpenAI API key string (e.g. ``sk-...``).
    :raises ValueError: If the key is empty or does not look like an API key.
    """
    key = (key or "").strip()
    if not key or not key.startswith("sk-") or len(key) < 20:
        raise ValueError(
            "That does not look like an OpenAI API key (expected an 'sk-...' "
            "string). Check the value and try again. (The key is not shown here.)"
        )
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    # Create the file atomically with 0600 (os.open applies the mode on creation,
    # masked only by umask), so the key is never briefly world-readable between a
    # default-mode create and a later chmod. O_TRUNC replaces any existing file.
    fd = os.open(CONFIG_PATH, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    # O_TRUNC does not reset the mode of a pre-existing file, so tighten it too.
    try:
        os.fchmod(fd, 0o600)
    except OSError:
        pass
    with os.fdopen(fd, "w", encoding="utf-8") as f:  # closes fd on exit
        json.dump({_CONFIG_KEY: key}, f, indent=2)


_KEY_FILE_PLACEHOLDER = "PASTE_YOUR_OPENAI_API_KEY_HERE"
_KEY_FILE_TEMPLATE = (
    "# SurveyCTO skill: OpenAI API key\n"
    "#\n"
    "# 1. Replace the placeholder line below with your OpenAI API key (it looks\n"
    "#    like sk-...). Get one at https://platform.openai.com/api-keys.\n"
    "# 2. Save this file.\n"
    "# 3. Tell the agent the key file is ready.\n"
    "#\n"
    "# Lines starting with '#' are ignored. The agent will import your key into a\n"
    "# private, owner-only config and delete this file; it will not read or repeat\n"
    "# the key. Do NOT paste your key into the chat.\n"
    + _KEY_FILE_PLACEHOLDER + "\n"
)


def write_key_template(path: str) -> str:
    """Write a placeholder key file for the user to edit. Returns the path.

    Onboarding without exposing the key in chat (the Cowork sandbox cannot see the
    user's terminal env, and chat text is logged): the agent writes this file, the
    user edits it in the working folder and saves, then the agent calls
    ``import_key_file`` to load it. This function never handles a real key.
    """
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(_KEY_FILE_TEMPLATE, encoding="utf-8")
    try:
        os.chmod(p, 0o600)
    except OSError:
        pass
    return str(p)


def import_key_file(path: str, delete_after: bool = True) -> str:
    """Read the key from a user-edited key file, store it, and delete the file.

    Reads the first non-blank, non-comment line as the key, validates and stores
    it via ``save_api_key`` (chmod 600), then removes the source file so the
    plaintext key does not linger in the working folder. Never prints the key.

    :returns: A masked form of the imported key (safe to show).
    :raises ValueError: If the file is missing, still holds the placeholder, or
        does not contain something that looks like an API key. Errors never
        include the key.
    """
    p = Path(path)
    if not p.is_file():
        raise ValueError(f"No key file at '{path}'. Create it with the template first.")
    candidate = ""
    for line in p.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if s and not s.startswith("#"):
            candidate = s
            break
    if candidate == _KEY_FILE_PLACEHOLDER or not candidate:
        raise ValueError(
            "The key file still contains the placeholder (or is empty). Open it, "
            "replace the placeholder with your OpenAI API key, save, and retry. "
            "(The key is not shown here.)")
    save_api_key(candidate)  # validates the sk- shape and stores chmod 600
    if delete_after:
        try:
            # best-effort overwrite before unlink so the plaintext does not linger
            with open(p, "w", encoding="utf-8") as f:
                f.write("# imported and removed\n")
            p.unlink()
        except OSError:
            pass
    return _mask(candidate)


def _read_config_key() -> str | None:
    """Read the stored key from the config file, or None if absent/unreadable.

    A missing, unreadable, or corrupt config returns None rather than raising:
    that keeps a malformed file from crashing the workflow, and avoids a JSON
    error message that could quote a fragment of the file (and thus of the key).
    """
    if not CONFIG_PATH.is_file():
        return None
    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            config = json.load(f)
        if not isinstance(config, dict):
            return None  # config edited to a non-object (list/number/string)
        value = config.get(_CONFIG_KEY)
        return value if isinstance(value, str) and value else None
    except (OSError, ValueError):
        return None


def _resolve_api_key() -> str:
    """Resolve the API key from the environment or config.

    :returns: The API key string.
    :raises RuntimeError: If no key is configured. The message contains NO key
        material, only setup guidance.
    """
    key = os.environ.get(_ENV_VAR) or _read_config_key()
    if not key:
        raise RuntimeError(
            "No OpenAI API key configured. See the 'COACHING THE USER' section "
            "of references/openai-credentials.md for setup, or set the "
            "OPENAI_API_KEY environment variable."
        )
    return key


def configure_openai() -> None:
    """Ensure ``OPENAI_API_KEY`` is set in the environment for the SDK.

    Resolves the key and exports it to the process environment so the OpenAI
    client constructed afterward reads it. Never prints the key.

    :raises RuntimeError: If no key is configured.
    """
    os.environ[_ENV_VAR] = _resolve_api_key()


def credentials_status() -> dict:
    """Report whether a key is configured, without revealing it.

    :returns: Dict with ``configured`` (bool), ``source`` (``"env"``,
        ``"config"`` or ``None``), and ``masked_key`` (a non-reversible hint).
    """
    env_key = os.environ.get(_ENV_VAR)
    if env_key:
        return {"configured": True, "source": "env", "masked_key": _mask(env_key)}
    key = _read_config_key()
    if key:
        return {"configured": True, "source": "config", "masked_key": _mask(key)}
    return {"configured": False, "source": None, "masked_key": None}


_USAGE = (
    "Usage:\n"
    "  python3 openai_auth.py template [path]   (write a key file for the user to edit;\n"
    "                                            default ./openai-key.txt)\n"
    "  python3 openai_auth.py import-file PATH   (import the edited key file, then delete it)\n"
    "  python3 openai_auth.py status            (show source + masked key)\n"
    "  python3 openai_auth.py set sk-...        (store a key passed as an argument;\n"
    "                                            avoid in Cowork/shared shells - it is logged)"
)

_DEFAULT_KEY_FILE = "openai-key.txt"


def _main(argv: list[str]) -> int:
    """CLI entry point. Never prints the raw key (only a masked form)."""
    if argv and argv[0] in ("-h", "--help"):
        print(_USAGE)
        return 0
    if argv and argv[0] == "template":
        path = argv[1] if len(argv) >= 2 else _DEFAULT_KEY_FILE
        written = write_key_template(path)
        print(f"Wrote key file: {written}")
        print("Ask the user to open it, replace the placeholder with their OpenAI "
              "API key, and save. Then run: python3 openai_auth.py import-file "
              f"{written}")
        return 0
    if len(argv) >= 2 and argv[0] == "import-file":
        try:
            masked = import_key_file(argv[1])
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        print(f"Imported and stored the key (masked: {masked}). The key file was "
              "removed. The key was never displayed.")
        return 0
    if len(argv) >= 2 and argv[0] == "set":
        try:
            save_api_key(argv[1])
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        st = credentials_status()
        print(f"OpenAI API key stored in {CONFIG_PATH} (masked: {st['masked_key']}).")
        return 0
    if argv and argv[0] == "status":
        st = credentials_status()
        if not st["configured"]:
            print("No OpenAI API key configured.")
            print("Set one up: python3 openai_auth.py template   (then have the user "
                  "edit the file and run import-file)")
            return 0
        print(f"Configured via: {st['source']}")
        print(f"Key (masked): {st['masked_key']}")
        return 0
    print(_USAGE, file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1:]))

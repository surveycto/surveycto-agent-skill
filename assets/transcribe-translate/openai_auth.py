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
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump({_CONFIG_KEY: key}, f, indent=2)
    try:
        os.chmod(CONFIG_PATH, 0o600)
    except OSError:
        pass


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


def _main(argv: list[str]) -> int:
    """CLI entry point. Never prints the raw key (only a masked form)."""
    if argv and argv[0] in ("-h", "--help"):
        print(
            "Usage:\n"
            "  python3 openai_auth.py set sk-...   (stores the key, chmod 600)\n"
            "  python3 openai_auth.py status"
        )
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
            print("Run: python3 openai_auth.py set sk-...   (or set OPENAI_API_KEY)")
            return 0
        print(f"Configured via: {st['source']}")
        print(f"Key (masked): {st['masked_key']}")
        return 0
    print(
        "Usage:\n"
        "  python3 openai_auth.py set sk-...\n"
        "  python3 openai_auth.py status",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1:]))

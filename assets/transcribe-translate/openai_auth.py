"""OpenAI credential handling for the translation and transcription helpers.

OpenAI authenticates with a single API key string (``sk-...``). The key itself is
the secret, so this module enforces one rule: NEVER print, echo, log, or paste the
key value anywhere. It is resolved from the environment or a small config file,
placed into ``OPENAI_API_KEY`` for the SDK, and never emitted.

Resolution order:

1. ``OPENAI_API_KEY`` environment variable (OpenAI's standard convention; how an
   advanced/local user who already has the key in their environment supplies it).
2. ``~/.surveycto-skill/openai-config.json`` (key stored there, file chmod 600).
3. Raise a clear error pointing to the setup coaching, with NO key material.

Preferred onboarding is a file handoff, so the key never appears in chat (where it
would be logged) or on a command line:

    python3 openai_auth.py template            # write ~/.surveycto-skill/openai-key.txt to edit
    # user pastes their key into that file and saves it; that is the whole setup.
    # the key file (chmod 600, in a hidden home folder) is read directly every run.
    python3 openai_auth.py status              # prints source + masked key only

In a script, point the SDK at the resolved key without revealing it::

    import openai_auth
    openai_auth.configure_openai()             # sets OPENAI_API_KEY for the SDK

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
    obviously-wrong value; the error never includes the key.

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
    # Create with 0600 at open time (os.open applies the mode on creation, masked
    # only by umask) so the key is never briefly world-readable between a
    # default-mode create and a later chmod. O_TRUNC replaces any existing file.
    fd = os.open(CONFIG_PATH, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    # O_TRUNC does not reset the mode of a pre-existing file, so tighten it too.
    try:
        os.fchmod(fd, 0o600)
    except OSError:
        pass
    with os.fdopen(fd, "w", encoding="utf-8") as f:  # closes fd on exit
        json.dump({_CONFIG_KEY: key}, f, indent=2)


_KEY_FILENAME = "openai-key.txt"


def default_key_path() -> Path:
    """Canonical key-file location: a hidden folder in the user's home directory. The
    key file lives here so it persists and is found from any working directory after
    the first setup, instead of cluttering (and being tied to) the working folder."""
    return CONFIG_DIR / _KEY_FILENAME
_KEY_FILE_PLACEHOLDER = "PASTE_YOUR_OPENAI_API_KEY_HERE"
_KEY_FILE_TEMPLATE = (
    "# SurveyCTO skill: OpenAI API key\n"
    "#\n"
    "# 1. Replace the placeholder line below with your OpenAI API key (it looks\n"
    "#    like sk-...). Get one at https://platform.openai.com/api-keys.\n"
    "# 2. Save this file.\n"
    "# 3. Tell the agent the key file is ready.\n"
    "#\n"
    "# Lines starting with '#' are ignored. This file is owner-only (chmod 600) and\n"
    "# read directly on each run, so you only set it up once. The agent will not\n"
    "# read or repeat the key. Do NOT paste it into the chat. Keep this file out of\n"
    "# version control (the skill gitignores it).\n"
    + _KEY_FILE_PLACEHOLDER + "\n"
)


def write_key_template(path: str) -> str:
    """Write a placeholder key file for the user to edit. Returns the path.

    Onboarding without exposing the key in chat (a hosted sandbox cannot see the
    user's terminal env, and chat text is logged): the agent writes this file, the
    user edits and saves it in the working folder, and from then on the key is read
    directly from it (chmod 600) on every run, so setup happens once. This function
    never handles a real key.

    :raises ValueError: If ``path`` is a symlink. Writing through a symlink would
        let a planted link redirect this write onto another file (e.g. the config),
        so a symlinked target is refused rather than followed.
    """
    p = Path(path)
    if p.is_symlink():
        raise ValueError(
            f"Refusing to write the key file through a symlink ('{path}'). Remove "
            "it and use a regular file path.")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(_KEY_FILE_TEMPLATE, encoding="utf-8")
    try:
        os.chmod(p, 0o600)
    except OSError:
        pass
    return str(p)


def _first_key_line(text: str) -> str:
    """First non-blank, non-comment line of a key file (``""`` if none)."""
    for line in text.splitlines():
        s = line.strip()
        if s and not s.startswith("#"):
            return s
    return ""


def _looks_like_key(s: str) -> bool:
    """Cheap shape check matching :func:`save_api_key` (never logs the value)."""
    return s.startswith("sk-") and len(s) >= 20


def _key_file_candidates() -> list[Path]:
    """Persistent key-file locations, in resolution order: the canonical hidden home
    location first (cwd-independent, where the template is written), then the working
    directory as a fallback for a key file placed there."""
    return [default_key_path(), Path(_KEY_FILENAME)]


def _read_key_file() -> str | None:
    """Read the API key directly from a persistent key file, or ``None``.

    The user-edited key file is itself the store: it is read on every run, so the
    key is set up once and simply reused. A symlinked or non-regular candidate is
    skipped (never followed), and a file still holding the placeholder or no
    key-shaped line yields ``None`` so setup coaching kicks in.
    """
    for p in _key_file_candidates():
        try:
            if p.is_symlink() or not p.is_file():
                continue
            line = _first_key_line(p.read_text(encoding="utf-8"))
        except OSError:
            continue
        if line and line != _KEY_FILE_PLACEHOLDER and _looks_like_key(line):
            return line
    return None


def import_key_file(path: str) -> str:
    """Validate a user-edited key file and copy it into the owner-only config.

    Optional: ``configure_openai`` reads the key file directly on every run, so
    importing is not required. It exists only to also store the key in the chmod-600
    config. The key file is left in place. Never prints the key.

    :returns: A masked form of the key (safe to show).
    :raises ValueError: If the file is missing, is a symlink, still holds the
        placeholder, or does not contain something that looks like an API key.
        Errors never include the key.
    """
    p = Path(path)
    if p.is_symlink():
        raise ValueError(
            f"Refusing to read the key file through a symlink ('{path}'). Remove it "
            "and use a regular file.")
    if not p.is_file():
        raise ValueError(f"No key file at '{path}'. Create it with the template first.")
    candidate = _first_key_line(p.read_text(encoding="utf-8"))
    if candidate == _KEY_FILE_PLACEHOLDER or not candidate:
        raise ValueError(
            "The key file still contains the placeholder (or is empty). Open it, "
            "replace the placeholder with your OpenAI API key, save, and retry. "
            "(The key is not shown here.)")
    save_api_key(candidate)  # validates the sk- shape and stores chmod 600
    return _mask(candidate)


def _read_config_key() -> str | None:
    """Read the stored key from the config file, or None if absent/unreadable.

    A missing, unreadable, or corrupt config returns None rather than raising: a
    malformed file must not crash the workflow, and a JSON error message could
    quote a fragment of the file (and thus of the key).
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
    """Resolve the API key from the environment, the config, or the key file.

    Order: ``OPENAI_API_KEY`` env var, then the chmod-600 config, then a persistent
    key file (read directly). When the key is found via a working-directory key file,
    it is promoted into the config so later commands resolve it regardless of the
    directory they run from (the key file is found relative to the cwd, which varies
    between commands; the config does not).

    :returns: The API key string.
    :raises RuntimeError: If no key is configured. The message contains NO key
        material, only setup guidance.
    """
    key = os.environ.get(_ENV_VAR) or _read_config_key()
    if key:
        return key
    key = _read_key_file()
    if key:
        try:
            save_api_key(key)  # promote so later commands find it from any cwd
        except (OSError, ValueError):
            pass  # best-effort; the key still resolves for this run
        return key
    raise RuntimeError(
        "No OpenAI API key configured. See the 'COACHING THE USER' section "
        "of references/openai-credentials.md for setup, or set the "
        "OPENAI_API_KEY environment variable."
    )


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
        ``"config"``, ``"key-file"`` or ``None``), and ``masked_key`` (a
        non-reversible hint).
    """
    env_key = os.environ.get(_ENV_VAR)
    if env_key:
        return {"configured": True, "source": "env", "masked_key": _mask(env_key)}
    key = _read_config_key()
    if key:
        return {"configured": True, "source": "config", "masked_key": _mask(key)}
    key = _read_key_file()
    if key:
        return {"configured": True, "source": "key-file", "masked_key": _mask(key)}
    return {"configured": False, "source": None, "masked_key": None}


_USAGE = (
    "Usage:\n"
    "  python3 openai_auth.py template [path]   (write a key file for the user to edit;\n"
    "                                            default ~/.surveycto-skill/openai-key.txt)\n"
    "  python3 openai_auth.py status            (show source + masked key)\n"
    "  python3 openai_auth.py import-file PATH   (optional: also copy the key into the\n"
    "                                            owner-only config)\n"
    "Once the key file is saved it is read directly on every run and reused. An\n"
    "advanced/local user can instead set OPENAI_API_KEY in the environment;\n"
    "configure_openai() honors it first."
)

def _main(argv: list[str]) -> int:
    """CLI entry point. Never prints the raw key (only a masked form)."""
    if argv and argv[0] in ("-h", "--help"):
        print(_USAGE)
        return 0
    if argv and argv[0] == "template":
        path = argv[1] if len(argv) >= 2 else str(default_key_path())
        written = write_key_template(path)
        print(f"Wrote key file: {written}")
        print("Ask the user to open it, replace the placeholder with their OpenAI "
              "API key, and save. That is the whole setup: the key is then read from "
              "this file on every run and reused.")
        return 0
    if len(argv) >= 2 and argv[0] == "import-file":
        try:
            masked = import_key_file(argv[1])
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        print(f"Stored the key in the owner-only config (masked: {masked}). The key "
              "file was left in place and will be reused. The key was never displayed.")
        return 0
    if argv and argv[0] == "status":
        st = credentials_status()
        if not st["configured"]:
            print("No OpenAI API key configured.")
            print("Set one up: python3 openai_auth.py template   (then have the user "
                  "edit the file and save it; that is all)")
            return 0
        print(f"Configured via: {st['source']}")
        print(f"Key (masked): {st['masked_key']}")
        return 0
    print(_USAGE, file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1:]))

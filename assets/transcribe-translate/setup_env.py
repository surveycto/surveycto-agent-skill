#!/usr/bin/env python3
"""Bootstrap a dedicated Python environment for the translate/transcribe modules.

Modern Python installs (Homebrew on macOS, system Python on Debian/Ubuntu) are
PEP 668 "externally managed": a plain ``pip install openai`` fails with
``error: externally-managed-environment``. This script sidesteps that by creating
an isolated virtual environment at ``~/.surveycto-skill/venv`` and installing the
dependencies there, so the install works the same way on every machine without
touching the system Python.

Run once before translating or transcribing:

    python3 setup_env.py            # installs the pinned openai

The OpenAI client is pinned to a verified version (``OPENAI_VERSION``); the script
installs exactly that and re-pins if a different version is present.

It prints the environment's Python interpreter path on the last line, prefixed
``VENV_PYTHON=``. Use that interpreter to run the modules, e.g.:

    <printed-python> translation.py --help

Idempotent: re-running reuses the existing environment and installs only what is
missing. Never prints or touches the OpenAI API key.

Standard library only, so it runs before anything is installed.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import venv
from pathlib import Path

VENV_DIR = Path.home() / ".surveycto-skill" / "venv"

# Pin the OpenAI client to a verified version. This dependency runs in a
# credential-bearing environment and handles survey payloads, so the version is
# fixed for reproducibility and supply-chain safety: a bare ``pip install openai``
# could pull a newer or compromised release. Bump only after testing against the
# live API. The error-detection and usage/billing handling in
# transcription.py/translation.py were verified against this version.
OPENAI_VERSION = "2.41.1"
OPENAI_REQUIREMENT = f"openai=={OPENAI_VERSION}"

# httpx (under the OpenAI client) needs socksio to reach a SOCKS proxy, as some
# sandboxes route egress through; without it the first API call fails. It is tiny,
# so install it unconditionally rather than guess whether the runtime is proxied.
SOCKS_REQUIREMENT = "socksio"


def _venv_python(venv_dir: Path) -> Path:
    """Path to the venv's interpreter (POSIX bin/, Windows Scripts/)."""
    win = venv_dir / "Scripts" / "python.exe"
    return win if win.exists() or os.name == "nt" else venv_dir / "bin" / "python"


def _installed_version(python: Path, module: str) -> str | None:
    """Return the installed module's ``__version__``, or None if not importable."""
    try:
        result = subprocess.run(
            [str(python), "-c",
             f"import {module} as m; print(getattr(m, '__version__', ''))"],
            capture_output=True, text=True, timeout=60,
        )
    except (subprocess.SubprocessError, OSError):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def _ffmpeg_hint() -> str:
    """Per-OS install command for ffmpeg."""
    if sys.platform == "darwin":
        return "brew install ffmpeg"
    if sys.platform.startswith("win"):
        return "download from https://ffmpeg.org/download.html and add it to PATH"
    return "sudo apt-get install ffmpeg   (or your distro's package manager)"


def _check_ffmpeg() -> bool:
    """Warn (do not fail) if ffmpeg/ffprobe is missing: transcription needs it for
    audio duration and chunking, translation does not. Returns True if present."""
    have = shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None
    if have:
        print("ffmpeg/ffprobe found on PATH.", flush=True)
    else:
        print("\nWARNING: ffmpeg/ffprobe was not found on PATH. Translation works "
              "without it, but TRANSCRIPTION needs it to measure audio duration and "
              "to split long files. Install it:\n  " + _ffmpeg_hint(), flush=True)
    return have


def _pip_install(python: Path, package: str) -> None:
    print(f"Installing {package} into {VENV_DIR} ...", flush=True)
    result = subprocess.run([str(python), "-m", "pip", "install", "--quiet", package])
    if result.returncode != 0:
        raise SystemExit(
            f"Failed to install {package}. Check network access and that "
            f"'{python}' can reach PyPI, then re-run."
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Set up the translate/transcribe environment.")
    parser.parse_args(argv)

    python = _venv_python(VENV_DIR)
    if not python.exists():
        print(f"Creating virtual environment at {VENV_DIR} ...", flush=True)
        VENV_DIR.parent.mkdir(parents=True, exist_ok=True)
        venv.EnvBuilder(with_pip=True).create(VENV_DIR)
        python = _venv_python(VENV_DIR)
    if not python.exists():
        raise SystemExit(f"Virtual environment creation did not produce {python}.")

    installed = _installed_version(python, "openai")
    if installed == OPENAI_VERSION:
        print(f"openai {OPENAI_VERSION} already installed.", flush=True)
    else:
        if installed:
            print(f"openai {installed} present; installing pinned {OPENAI_VERSION}.",
                  flush=True)
        _pip_install(python, OPENAI_REQUIREMENT)

    # SOCKS support for proxied sandboxes (see SOCKS_REQUIREMENT). Importing the
    # module name confirms presence; the pip name and import name match.
    if _installed_version(python, "socksio") is not None:
        print("socksio already installed.", flush=True)
    else:
        _pip_install(python, SOCKS_REQUIREMENT)

    # Transcription needs ffmpeg on PATH; warn at setup time rather than only when a
    # transcription run fails.
    _check_ffmpeg()

    # Last line, machine-readable, so the agent can capture the interpreter path.
    print(f"VENV_PYTHON={python}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

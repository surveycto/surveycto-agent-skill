#!/usr/bin/env python3
"""Bootstrap a dedicated Python environment for the translate/transcribe modules.

Modern Python installs (Homebrew on macOS, system Python on Debian/Ubuntu) are
PEP 668 "externally managed": a plain ``pip install openai`` fails with
``error: externally-managed-environment``. This script sidesteps that by creating
an isolated virtual environment at ``~/.surveycto-skill/venv`` and installing the
dependencies there, so the install works the same way on every machine without
touching the system Python.

Run once before translating or transcribing:

    python3 setup_env.py                    # installs openai (cloud translation + transcription)
    python3 setup_env.py --local            # + faster-whisper (on-device transcription)
    python3 setup_env.py --local-translate  # + NLLB deps (on-device translation)
    # combine --local and --local-translate for both on-device engines

It prints the path to the environment's Python interpreter on the last line,
prefixed with ``VENV_PYTHON=``. Use that interpreter to run the modules, e.g.:

    <printed-python> translation.py --help

It is idempotent: re-running reuses the existing environment and only installs
what is missing. It never prints or touches the OpenAI API key.

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


def _venv_python(venv_dir: Path) -> Path:
    """Path to the venv's interpreter (POSIX bin/, Windows Scripts/)."""
    win = venv_dir / "Scripts" / "python.exe"
    return win if win.exists() or os.name == "nt" else venv_dir / "bin" / "python"


def _installed(python: Path, module: str) -> bool:
    try:
        return subprocess.run(
            [str(python), "-c", f"import {module}"],
            capture_output=True, timeout=60,
        ).returncode == 0
    except (subprocess.SubprocessError, OSError):
        return False


def _ffmpeg_hint() -> str:
    """Per-OS install command for ffmpeg."""
    if sys.platform == "darwin":
        return "brew install ffmpeg"
    if sys.platform.startswith("win"):
        return "download from https://ffmpeg.org/download.html and add it to PATH"
    return "sudo apt-get install ffmpeg   (or your distro's package manager)"


def _check_ffmpeg() -> bool:
    """Warn (do not fail) if ffmpeg/ffprobe is missing: transcription needs it for
    audio duration and chunking; translation does not. Returns True if present."""
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
    parser.add_argument("--local", action="store_true",
                        help="also install faster-whisper for on-device transcription")
    parser.add_argument("--local-translate", action="store_true",
                        help="also install NLLB deps (transformers, torch, sentencepiece, "
                             "langdetect) for on-device translation")
    args = parser.parse_args(argv)

    python = _venv_python(VENV_DIR)
    if not python.exists():
        print(f"Creating virtual environment at {VENV_DIR} ...", flush=True)
        VENV_DIR.parent.mkdir(parents=True, exist_ok=True)
        venv.EnvBuilder(with_pip=True).create(VENV_DIR)
        python = _venv_python(VENV_DIR)
    if not python.exists():
        raise SystemExit(f"Virtual environment creation did not produce {python}.")

    if _installed(python, "openai"):
        print("openai already installed.", flush=True)
    else:
        _pip_install(python, "openai")

    if args.local:
        if _installed(python, "faster_whisper"):
            print("faster-whisper already installed.", flush=True)
        else:
            _pip_install(python, "faster-whisper")

    if args.local_translate:
        for mod, pkg in (("transformers", "transformers"), ("torch", "torch"),
                         ("sentencepiece", "sentencepiece"), ("langdetect", "langdetect")):
            if _installed(python, mod):
                print(f"{pkg} already installed.", flush=True)
            else:
                _pip_install(python, pkg)

    # Transcription needs ffmpeg on PATH; warn here so it is caught at setup time
    # rather than only when a transcription run fails.
    _check_ffmpeg()

    # Last line, machine-readable, so the agent can capture the interpreter path.
    print(f"VENV_PYTHON={python}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

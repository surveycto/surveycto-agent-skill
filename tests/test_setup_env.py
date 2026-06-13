#!/usr/bin/env python3
"""Offline tests for the environment bootstrap.

These do not create a venv or hit the network (that is exercised live). They lock
the interpreter-path resolution (POSIX bin/ vs Windows Scripts/) and the
machine-readable VENV_PYTHON contract the agent docs depend on.

Run: python3 tests/test_setup_env.py
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "assets" / "transcribe-translate"))

import setup_env as S  # noqa: E402


def test_venv_python_posix_layout() -> None:
    with tempfile.TemporaryDirectory() as d:
        v = Path(d) / "venv"
        (v / "bin").mkdir(parents=True)
        (v / "bin" / "python").write_text("#!/bin/sh\n")
        assert S._venv_python(v) == v / "bin" / "python"


def test_venv_python_windows_layout() -> None:
    with tempfile.TemporaryDirectory() as d:
        v = Path(d) / "venv"
        (v / "Scripts").mkdir(parents=True)
        (v / "Scripts" / "python.exe").write_text("")
        # Windows interpreter is picked up by its presence even off-Windows.
        assert S._venv_python(v) == v / "Scripts" / "python.exe"


def test_ffmpeg_hint_is_platform_specific() -> None:
    # the install hint must be actionable on the host platform
    hint = S._ffmpeg_hint()
    assert isinstance(hint, str) and hint
    assert any(tok in hint for tok in ("brew install ffmpeg", "apt-get install ffmpeg",
                                       "ffmpeg.org"))


def test_check_ffmpeg_returns_bool() -> None:
    # never raises; returns a bool reflecting PATH state
    assert isinstance(S._check_ffmpeg(), bool)


def test_venv_dir_is_under_home() -> None:
    # The docs promise a stable, per-user location; keep code and docs in lockstep.
    assert S.VENV_DIR == Path.home() / ".surveycto-skill" / "venv"


def main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"ok  {t.__name__}")
    print(f"\n{len(tests)} setup-env tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

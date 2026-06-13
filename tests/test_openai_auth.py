#!/usr/bin/env python3
"""Offline tests for OpenAI credential handling.

Central guarantee: the API key value is never printed/returned in clear; only a
masked form is exposed, and errors carry no key material. No network, no openai
package needed.

Run: python3 tests/test_openai_auth.py
"""

from __future__ import annotations

import io
import json
import os
import sys
import tempfile
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "assets" / "transcribe-translate"))

import openai_auth as auth  # noqa: E402

_FAKE = "sk-proj-THISisAfakeTESTkey000000000000000000000000"


def _fresh(tmp: Path) -> None:
    auth.CONFIG_DIR = tmp / ".surveycto-skill"
    auth.CONFIG_PATH = auth.CONFIG_DIR / "openai-config.json"
    os.environ.pop("OPENAI_API_KEY", None)


def test_save_then_resolve_via_config() -> None:
    with tempfile.TemporaryDirectory() as d:
        _fresh(Path(d))
        auth.save_api_key(_FAKE)
        assert auth.CONFIG_PATH.is_file()
        stored = json.loads(auth.CONFIG_PATH.read_text())["openai_api_key"]
        assert stored == _FAKE
        auth.configure_openai()
        assert os.environ["OPENAI_API_KEY"] == _FAKE


def test_env_takes_precedence() -> None:
    with tempfile.TemporaryDirectory() as d:
        _fresh(Path(d))
        auth.save_api_key(_FAKE)
        os.environ["OPENAI_API_KEY"] = "sk-env-override-000000000000000000000"
        assert auth._resolve_api_key() == "sk-env-override-000000000000000000000"


def test_missing_raises_without_key_material() -> None:
    with tempfile.TemporaryDirectory() as d:
        _fresh(Path(d))
        try:
            auth.configure_openai()
        except RuntimeError as exc:
            assert "No OpenAI API key configured" in str(exc)
            assert "sk-" not in str(exc)
            return
        raise AssertionError("expected RuntimeError")


def test_save_rejects_bad_key() -> None:
    with tempfile.TemporaryDirectory() as d:
        _fresh(Path(d))
        for bad in ["", "nope", "hello world"]:
            try:
                auth.save_api_key(bad)
            except ValueError as exc:
                assert bad not in str(exc) or bad == ""  # never echoes a real key
            else:
                raise AssertionError(f"expected ValueError for {bad!r}")


def test_status_and_mask_never_reveal_key() -> None:
    with tempfile.TemporaryDirectory() as d:
        _fresh(Path(d))
        auth.save_api_key(_FAKE)
        st = auth.credentials_status()
        assert st["configured"] and st["source"] == "config"
        assert st["masked_key"] and _FAKE not in st["masked_key"]
        # the mask shows only a prefix and suffix, not the middle
        assert "sk-proj" in st["masked_key"] and "0000" in st["masked_key"]
        assert "THISisAfake" not in st["masked_key"]


def test_cli_never_prints_raw_key() -> None:
    with tempfile.TemporaryDirectory() as d:
        _fresh(Path(d))
        out = io.StringIO()
        err = io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            auth._main(["set", _FAKE])
            auth._main(["status"])
        combined = out.getvalue() + err.getvalue()
        assert _FAKE not in combined, "raw key leaked to CLI output"
        assert "THISisAfake" not in combined


def test_config_file_is_chmod_600() -> None:
    import stat
    with tempfile.TemporaryDirectory() as d:
        _fresh(Path(d))
        auth.save_api_key(_FAKE)
        mode = stat.S_IMODE(auth.CONFIG_PATH.stat().st_mode)
        assert mode == 0o600, oct(mode)


def test_corrupt_config_is_handled_gracefully() -> None:
    with tempfile.TemporaryDirectory() as d:
        _fresh(Path(d))
        auth.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        # malformed JSON that embeds key-like material; must not crash or echo it
        auth.CONFIG_PATH.write_text('{"openai_api_key": "sk-broken', encoding="utf-8")
        st = auth.credentials_status()
        assert st["configured"] is False and st["masked_key"] is None, st
        # a valid-JSON but non-object config (hand-edited to an array) must not crash
        auth.CONFIG_PATH.write_text('["sk-not-a-dict-000000000000"]', encoding="utf-8")
        assert auth._read_config_key() is None
        assert auth.credentials_status()["configured"] is False
        try:
            auth.configure_openai()
        except RuntimeError as exc:
            assert "No OpenAI API key configured" in str(exc)
            assert "sk-broken" not in str(exc), "leaked file content in error"
            return
        raise AssertionError("expected RuntimeError on corrupt config with no env key")


def main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"ok  {t.__name__}")
    print(f"\n{len(tests)} openai-auth tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

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


def test_key_file_handoff_imports_and_deletes() -> None:
    import stat
    with tempfile.TemporaryDirectory() as d:
        _fresh(Path(d))
        kf = Path(d) / "openai-key.txt"
        auth.write_key_template(str(kf))
        # template carries the placeholder and no real key
        tmpl = kf.read_text()
        assert "PASTE_YOUR_OPENAI_API_KEY_HERE" in tmpl and _FAKE not in tmpl
        # importing while still a placeholder must refuse
        try:
            auth.import_key_file(str(kf))
        except ValueError as exc:
            assert "placeholder" in str(exc).lower() and "sk-" not in str(exc)
        else:
            raise AssertionError("expected refusal on un-edited placeholder")
        # user edits the file, then import: stores masked, deletes file, never echoes
        kf.write_text(f"# comment line\n{_FAKE}\n", encoding="utf-8")
        masked = auth.import_key_file(str(kf))
        assert _FAKE not in masked and "THISisAfake" not in masked
        assert not kf.exists(), "key file should be deleted after import"
        assert auth._resolve_api_key() == _FAKE          # stored and resolvable
        mode = stat.S_IMODE(auth.CONFIG_PATH.stat().st_mode)
        assert mode == 0o600, oct(mode)


def test_save_tightens_preexisting_loose_permissions() -> None:
    import stat
    with tempfile.TemporaryDirectory() as d:
        _fresh(Path(d))
        auth.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        auth.CONFIG_PATH.write_text("{}", encoding="utf-8")
        os.chmod(auth.CONFIG_PATH, 0o644)               # pre-existing world-readable
        auth.save_api_key(_FAKE)
        assert stat.S_IMODE(auth.CONFIG_PATH.stat().st_mode) == 0o600


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
        kf = Path(d) / "openai-key.txt"
        out = io.StringIO()
        err = io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            auth._main(["template", str(kf)])
            kf.write_text(_FAKE + "\n", encoding="utf-8")   # user edits the file
            auth._main(["import-file", str(kf)])
            auth._main(["status"])
        combined = out.getvalue() + err.getvalue()
        assert _FAKE not in combined, "raw key leaked to CLI output"
        assert "THISisAfake" not in combined
        # and there is no longer a `set` subcommand that takes the key on argv
        assert auth._main(["set", _FAKE]) == 2  # unknown command -> usage


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


def test_template_refuses_symlink_target() -> None:
    # writing the template through a symlink could redirect the write onto another
    # file (e.g. the config); refuse rather than follow it
    with tempfile.TemporaryDirectory() as d:
        _fresh(Path(d))
        real = Path(d) / "secret-config.json"
        real.write_text('{"keep":"me"}\n', encoding="utf-8")
        link = Path(d) / "openai-key.txt"
        link.symlink_to(real)
        try:
            auth.write_key_template(str(link))
        except ValueError as exc:
            assert "symlink" in str(exc).lower()
        else:
            raise AssertionError("expected refusal to write through a symlink")
        assert real.read_text(encoding="utf-8") == '{"keep":"me"}\n'  # target untouched


def test_import_refuses_symlink_target() -> None:
    # importing through a symlink would let the overwrite/delete hit another file
    with tempfile.TemporaryDirectory() as d:
        _fresh(Path(d))
        real = Path(d) / "secret-config.json"
        real.write_text('{"keep":"me"}\n', encoding="utf-8")
        link = Path(d) / "openai-key.txt"
        link.symlink_to(real)
        try:
            auth.import_key_file(str(link))
        except ValueError as exc:
            assert "symlink" in str(exc).lower() and "sk-" not in str(exc)
        else:
            raise AssertionError("expected refusal to import through a symlink")
        assert real.read_text(encoding="utf-8") == '{"keep":"me"}\n'  # target untouched


def test_import_reports_when_plaintext_cannot_be_removed() -> None:
    # if the plaintext key file survives deletion, import must NOT report a clean
    # success; it raises so the lingering key is surfaced
    import stat as _stat
    with tempfile.TemporaryDirectory() as d:
        _fresh(Path(d))
        sub = Path(d) / "ro"
        sub.mkdir()
        kf = sub / "openai-key.txt"
        kf.write_text(_FAKE + "\n", encoding="utf-8")
        os.chmod(sub, 0o500)  # read+exec only: file inside cannot be unlinked
        try:
            auth.import_key_file(str(kf))
        except RuntimeError as exc:
            assert "could not delete" in str(exc).lower()
            assert _FAKE not in str(exc) and "sk-" not in str(exc)
            assert auth._resolve_api_key() == _FAKE  # the key was still stored
        else:
            raise AssertionError("expected a cleanup error when the file cannot be removed")
        finally:
            os.chmod(sub, 0o700)  # restore so the temp dir can be cleaned up


def main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"ok  {t.__name__}")
    print(f"\n{len(tests)} openai-auth tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

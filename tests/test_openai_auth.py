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


def test_key_file_is_read_directly_and_kept(monkeypatch=None) -> None:
    # the persistent key file is the store: written once, read directly, never
    # deleted, and resolvable on later runs without an import step
    import stat, os as _os
    with tempfile.TemporaryDirectory() as d:
        _fresh(Path(d))
        kf = Path(d) / "openai-key.txt"
        auth.write_key_template(str(kf))
        tmpl = kf.read_text()
        assert "PASTE_YOUR_OPENAI_API_KEY_HERE" in tmpl and _FAKE not in tmpl
        # while still the placeholder, resolution finds no usable key
        cwd = _os.getcwd(); _os.chdir(d)
        try:
            assert auth._read_key_file() is None  # placeholder is not a key
            # user edits the file: now it resolves directly, no import, file kept
            kf.write_text(f"# comment line\n{_FAKE}\n", encoding="utf-8")
            assert auth._read_key_file() == _FAKE
            assert auth._resolve_api_key() == _FAKE
            assert kf.exists(), "key file must be kept (read directly, not deleted)"
            # the template was created owner-only
            assert stat.S_IMODE(kf.stat().st_mode) == 0o600, oct(kf.stat().st_mode)
        finally:
            _os.chdir(cwd)


def test_import_is_optional_and_keeps_the_file() -> None:
    # importing copies the key into the chmod-600 config but no longer deletes the
    # key file by default
    import stat
    with tempfile.TemporaryDirectory() as d:
        _fresh(Path(d))
        kf = Path(d) / "openai-key.txt"
        kf.write_text(f"# comment\n{_FAKE}\n", encoding="utf-8")
        # placeholder still refuses
        kf2 = Path(d) / "ph.txt"; auth.write_key_template(str(kf2))
        try:
            auth.import_key_file(str(kf2))
        except ValueError as exc:
            assert "placeholder" in str(exc).lower() and "sk-" not in str(exc)
        else:
            raise AssertionError("expected refusal on un-edited placeholder")
        masked = auth.import_key_file(str(kf))
        assert _FAKE not in masked and "THISisAfake" not in masked
        assert kf.exists(), "import must leave the key file in place"
        assert auth._read_config_key() == _FAKE   # also stored in the config
        assert stat.S_IMODE(auth.CONFIG_PATH.stat().st_mode) == 0o600


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
    # importing must not follow a symlink that could point at another file
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


def test_key_file_promoted_to_config_for_cwd_independence() -> None:
    # a key found in a working-directory key file is promoted into the config, so a
    # later command run from a different directory still resolves it
    import os as _os
    with tempfile.TemporaryDirectory() as d:
        _fresh(Path(d))
        a = Path(d) / "a"; a.mkdir()
        (a / "openai-key.txt").write_text(f"# key\n{_FAKE}\n", encoding="utf-8")
        cwd = _os.getcwd()
        try:
            _os.chdir(a)
            assert auth._resolve_api_key() == _FAKE   # reads cwd key file...
            assert auth._read_config_key() == _FAKE    # ...and promotes into config
        finally:
            _os.chdir(cwd)
        # from a different directory with no key file, the config still resolves it
        b = Path(d) / "b"; b.mkdir()
        try:
            _os.chdir(b)
            assert auth._resolve_api_key() == _FAKE
        finally:
            _os.chdir(cwd)


def test_template_defaults_to_hidden_home_and_resolves_anywhere() -> None:
    # the template (no explicit path) is written to the hidden home folder, and the
    # key there resolves from any working directory
    import io, os as _os
    from contextlib import redirect_stdout
    with tempfile.TemporaryDirectory() as d:
        _fresh(Path(d))
        with redirect_stdout(io.StringIO()):
            auth._main(["template"])
        kf = auth.default_key_path()
        assert kf.is_file() and kf.parent == auth.CONFIG_DIR, kf
        kf.write_text(f"{_FAKE}\n", encoding="utf-8")  # user pastes
        cwd = _os.getcwd()
        try:
            _os.chdir(d)  # a directory with no local key file
            assert auth._resolve_api_key() == _FAKE
        finally:
            _os.chdir(cwd)


def main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"ok  {t.__name__}")
    print(f"\n{len(tests)} openai-auth tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Offline tests for the shared Google Cloud credential helper.

The central guarantee under test: the helper resolves and points the Google
client library at the service-account file *without ever opening it*. These
tests run with no Google packages and no network.

Run: python3 tests/test_google_cloud_auth.py
"""

from __future__ import annotations

import builtins
import json
import os
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "assets" / "google-cloud"))

import google_cloud_auth as auth  # noqa: E402


def _fresh_config(tmp: Path) -> None:
    """Point the module's config at a temp dir and clear the env var."""
    auth.CONFIG_DIR = tmp / ".surveycto-skill"
    auth.CONFIG_PATH = auth.CONFIG_DIR / "google-cloud-config.json"
    os.environ.pop("GOOGLE_APPLICATION_CREDENTIALS", None)


def test_save_then_resolve_via_config() -> None:
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        _fresh_config(tmp)
        creds = tmp / "key.json"
        creds.write_text('{"type":"service_account"}')
        auth.save_credentials_path(str(creds))
        assert auth.CONFIG_PATH.is_file()
        stored = json.loads(auth.CONFIG_PATH.read_text())
        assert stored["google_credentials_path"] == str(creds)
        path = auth.configure_google_auth()
        assert path == str(creds)
        assert os.environ["GOOGLE_APPLICATION_CREDENTIALS"] == str(creds)


def test_env_var_takes_precedence() -> None:
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        _fresh_config(tmp)
        config_creds = tmp / "config.json"
        config_creds.write_text("{}")
        env_creds = tmp / "env.json"
        env_creds.write_text("{}")
        auth.save_credentials_path(str(config_creds))
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(env_creds)
        assert auth._resolve_credentials_path() == str(env_creds)


def test_missing_config_raises() -> None:
    with tempfile.TemporaryDirectory() as d:
        _fresh_config(Path(d))
        try:
            auth.configure_google_auth()
        except RuntimeError as exc:
            assert "No Google Cloud credentials path configured" in str(exc)
            return
        raise AssertionError("expected RuntimeError for missing config")


def test_configured_but_file_missing_raises() -> None:
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        _fresh_config(tmp)
        # Write the config to point at a path, then delete the file.
        creds = tmp / "key.json"
        creds.write_text("{}")
        auth.save_credentials_path(str(creds))
        creds.unlink()
        try:
            auth.configure_google_auth()
        except RuntimeError as exc:
            assert "no file exists" in str(exc).lower()
            return
        raise AssertionError("expected RuntimeError when file is gone")


def test_save_nonexistent_path_raises() -> None:
    with tempfile.TemporaryDirectory() as d:
        _fresh_config(Path(d))
        try:
            auth.save_credentials_path("/no/such/file.json")
        except FileNotFoundError:
            return
        raise AssertionError("expected FileNotFoundError")


def test_credentials_file_is_never_opened() -> None:
    """The core security guarantee: resolve/configure never open the file."""
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        _fresh_config(tmp)
        creds = tmp / "secret-key.json"
        creds.write_text('{"private_key":"DO-NOT-READ-ME"}')
        auth.save_credentials_path(str(creds))

        opened: list[str] = []
        real_open = builtins.open

        def tracking_open(file, *args, **kwargs):
            opened.append(os.fspath(file))
            return real_open(file, *args, **kwargs)

        builtins.open = tracking_open
        try:
            auth.configure_google_auth()
            auth.credentials_status()
        finally:
            builtins.open = real_open

        assert str(creds) not in opened, (
            f"credentials file was opened: {opened}"
        )
        # The config file (path only, not secret) is allowed to be opened.
        assert any("google-cloud-config.json" in p for p in opened)


def test_status_reports_without_opening() -> None:
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        _fresh_config(tmp)
        creds = tmp / "key.json"
        creds.write_text("{}")
        auth.save_credentials_path(str(creds))
        status = auth.credentials_status()
        assert status["configured"] is True
        assert status["source"] == "config"
        assert status["file_exists"] is True
        assert status["path"] == str(creds)


def main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"ok  {t.__name__}")
    print(f"\n{len(tests)} google-cloud-auth tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

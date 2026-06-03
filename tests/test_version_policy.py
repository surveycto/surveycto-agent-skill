#!/usr/bin/env python3
"""Standalone tests for scripts/build_version_policy.py.

Run directly (no pytest needed, matching this repo's test style):
    python3 tests/test_version_policy.py
Exits non-zero on the first failure.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from build_version_policy import build_policy  # noqa: E402


def _expect(cond: bool, msg: str) -> None:
    if not cond:
        raise AssertionError(msg)


def test_recommended_min_defaults_to_latest() -> None:
    policy = build_policy("1.0.0-beta.4", {"deprecated_below_version": "1.0.0-beta.3"})
    _expect(policy["latest_version"] == "1.0.0-beta.4", policy)
    _expect(policy["recommended_min_version"] == "1.0.0-beta.4", policy)
    _expect(policy["deprecated_below_version"] == "1.0.0-beta.3", policy)


def test_empty_source_collapses_to_latest() -> None:
    policy = build_policy("1.0.0-beta.4", {})
    _expect(policy["recommended_min_version"] == "1.0.0-beta.4", policy)
    _expect(policy["deprecated_below_version"] == "1.0.0-beta.4", policy)
    _expect(policy["latest_updates"] == [], policy)


def test_committed_source_file_is_valid_against_current_version() -> None:
    """The real source file must produce a consistent policy for the version
    currently declared in SKILL.md, so a release never fails validation."""
    source = json.loads((REPO_ROOT / "version-policy.source.json").read_text())
    source = {k: v for k, v in source.items() if not k.startswith("_")}
    skill_md = (REPO_ROOT / "SKILL.md").read_text()
    version = next(
        line.split('"')[1]
        for line in skill_md.splitlines()
        if line.strip().startswith("version:")
    )
    policy = build_policy(version, source)
    _expect(policy["latest_version"] == version, policy)
    _expect(len(policy["latest_updates"]) >= 1, policy)


def test_inconsistent_policy_rejected() -> None:
    try:
        build_policy("1.0.0-beta.4", {"deprecated_below_version": "2.0.0"})
    except SystemExit:
        return
    raise AssertionError("expected SystemExit for deprecated_below > latest")


def test_invalid_version_rejected() -> None:
    try:
        build_policy("not-a-version", {})
    except SystemExit:
        return
    raise AssertionError("expected SystemExit for invalid version")


def main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"ok  {t.__name__}")
    print(f"\n{len(tests)} version-policy tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

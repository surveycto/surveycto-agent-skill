#!/usr/bin/env python3
"""Build the skill ``version-policy.json`` release asset.

Merges the released version (the source of truth for "latest", derived from the
release tag) with the committed editorial overrides in
``version-policy.source.json`` and writes a self-contained policy document that
the SurveyCTO MCP server bakes into its image and serves to callers.

Derivation rules:
- ``latest_version``           = the released version (``--version``).
- ``recommended_min_version``  = override if set, else ``latest_version``.
- ``deprecated_below_version`` = override if set, else ``recommended_min_version``.
- ``latest_updates``           = override list if set, else empty.

Validation (fails the release on violation): every version parses as a real
semantic version and the policy is internally ordered,
``deprecated_below <= recommended_min <= latest``. Versions are compared with a
real parser, never as strings, because pre-release identifiers make
``1.0.0-beta.10`` newer than ``1.0.0-beta.9``.

Usage:
    python scripts/build_version_policy.py --version 1.0.0-beta.4 \
        --source version-policy.source.json --output version-policy.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict

from packaging.version import InvalidVersion, Version


def _parse(label: str, value: str) -> Version:
    try:
        return Version(value)
    except InvalidVersion as exc:
        raise SystemExit(f"{label} is not a valid version: {value!r} ({exc})")


def build_policy(version: str, source: Dict[str, Any]) -> Dict[str, Any]:
    latest = version.strip()
    recommended_min = (source.get("recommended_min_version") or latest).strip()
    deprecated_below = (
        source.get("deprecated_below_version") or recommended_min
    ).strip()
    updates = source.get("latest_updates") or []
    if not isinstance(updates, list):
        raise SystemExit("latest_updates must be a list of strings")

    v_latest = _parse("latest_version", latest)
    v_recommended = _parse("recommended_min_version", recommended_min)
    v_deprecated = _parse("deprecated_below_version", deprecated_below)
    if not (v_deprecated <= v_recommended <= v_latest):
        raise SystemExit(
            "version policy is inconsistent; expected "
            f"deprecated_below ({deprecated_below}) <= recommended_min "
            f"({recommended_min}) <= latest ({latest})"
        )

    return {
        "latest_version": latest,
        "recommended_min_version": recommended_min,
        "deprecated_below_version": deprecated_below,
        "latest_updates": [str(u) for u in updates],
    }


def _load_source(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise SystemExit(f"{path} must contain a JSON object")
    # Drop comment/underscore-prefixed keys so they never reach the asset.
    return {k: v for k, v in data.items() if not k.startswith("_")}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True, help="released skill version")
    parser.add_argument(
        "--source",
        default="version-policy.source.json",
        help="editorial overrides file",
    )
    parser.add_argument(
        "--output",
        default="version-policy.json",
        help="path to write the policy asset (use - for stdout)",
    )
    args = parser.parse_args(argv)

    policy = build_policy(args.version, _load_source(Path(args.source)))
    rendered = json.dumps(policy, indent=2) + "\n"
    if args.output == "-":
        sys.stdout.write(rendered)
    else:
        Path(args.output).write_text(rendered, encoding="utf-8")
        print(f"wrote {args.output}: {policy}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

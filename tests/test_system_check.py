#!/usr/bin/env python3
"""Offline tests for machine-spec detection and local-model recommendation.

The recommendation logic is exercised with injected specs so all tiers (GPU,
strong CPU, mid, low-RAM, very-low-RAM, unknown-RAM) are covered on any OS. A
smoke test runs the real detection on the host and checks the shape only (values
are machine-specific). No network.

Run: python3 tests/test_system_check.py
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "assets" / "transcribe-translate"))

import system_check as S  # noqa: E402


def _specs(os_="Linux", arch="x86_64", cores=8, ram=16.0, gpu=False, apple=False):
    return {"os": os_, "arch": arch, "cpu_cores": cores, "ram_gb": ram,
            "has_nvidia_gpu": gpu, "apple_silicon": apple}


def test_nvidia_gpu_gets_largest() -> None:
    r = S.recommend_model(_specs(gpu=True, ram=8.0, cores=4))
    assert r["recommended"] == "large-v3", r
    assert "CUDA" in r["accelerator"]
    assert r["avoid"] == [] and "large-v3" in r["feasible"]


def test_strong_cpu_gets_small_with_medium_feasible() -> None:
    r = S.recommend_model(_specs(ram=24.0, cores=14))
    assert r["recommended"] == "small", r
    assert "medium" in r["feasible"] and "large-v3" in r["avoid"]


def test_apple_silicon_notes_cpu_only() -> None:
    r = S.recommend_model(_specs(os_="Darwin", arch="arm64", ram=16.0, cores=8, apple=True))
    assert r["recommended"] == "small"
    assert "CPU only" in r["accelerator"] and "Apple Silicon" in r["accelerator"]


def test_mid_ram_avoids_large_models() -> None:
    r = S.recommend_model(_specs(ram=8.0, cores=4))
    assert r["recommended"] == "small"
    assert "medium" in r["avoid"] and "large-v3" in r["avoid"]


def test_low_ram_prefers_base() -> None:
    r = S.recommend_model(_specs(ram=4.0, cores=2))
    assert r["recommended"] == "base"
    assert "small" in r["avoid"]


def test_very_low_ram_uses_tiny() -> None:
    r = S.recommend_model(_specs(ram=2.0, cores=2))
    assert r["recommended"] == "tiny"
    assert r["feasible"] == ["tiny"]
    assert "cloud" in r["rationale"].lower()  # steer to cloud when local is marginal


def test_unknown_ram_is_conservative() -> None:
    r = S.recommend_model(_specs(ram=None, cores=16))
    # unknown RAM -> assume ~4 GB -> 'base', and say so
    assert r["recommended"] == "base"
    assert "could not be measured" in r["rationale"]


def test_detect_specs_shape_on_host() -> None:
    s = S.detect_specs()
    for k in ("os", "arch", "cpu_cores", "ram_gb", "has_nvidia_gpu", "apple_silicon",
              "has_ffmpeg"):
        assert k in s, s
    assert isinstance(s["has_nvidia_gpu"], bool)
    assert isinstance(s["has_ffmpeg"], bool)
    assert s["ram_gb"] is None or s["ram_gb"] > 0
    # assess() always attaches a recommendation with a download size
    a = S.assess()
    assert a["recommendation"]["recommended"] in {m["name"] for m in S._MODELS}
    assert a["recommendation"]["download"]
    assert a["translation"]["model"] == "nllb-200-distilled-600M"
    assert isinstance(a["translation"]["feasible"], bool)


def test_translation_recommendation_by_ram() -> None:
    assert S.recommend_translation(_specs(ram=16.0))["feasible"] is True
    low = S.recommend_translation(_specs(ram=2.0))
    assert low["feasible"] is False and "cloud" in low["note"].lower()


def main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"ok  {t.__name__}")
    print(f"\n{len(tests)} system-check tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

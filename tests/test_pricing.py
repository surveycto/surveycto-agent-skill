#!/usr/bin/env python3
"""Offline tests for the OpenAI rate table (pricing.py + pricing.json).

Cover: the shipped JSON loads and validates, the built-in fail-safe matches it,
a missing/corrupt file degrades to the built-in (never crashes), validation
rejects malformed tables, rate_for fails closed on unknown models, and the
set-* refresh path validates inputs and restamps last_verified.

Run: python3 tests/test_pricing.py
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
ASSET_DIR = REPO_ROOT / "assets" / "transcribe-translate"
sys.path.insert(0, str(ASSET_DIR))

import pricing as P  # noqa: E402


def test_shipped_json_loads_from_file() -> None:
    data, prov = P.load()
    assert prov["source"] == "file", prov
    assert prov["last_verified"] == data["last_verified"]
    assert data["currency"] == "USD"


def test_builtin_matches_shipped_json() -> None:
    # the fail-safe must stay byte-equivalent to the shipped file, so a fallback
    # never serves different numbers than a normal load
    on_disk = json.loads((ASSET_DIR / "pricing.json").read_text(encoding="utf-8"))
    assert on_disk == P._BUILTIN, "pricing.json and pricing._BUILTIN have diverged"


def test_rate_for_known_and_unknown() -> None:
    data, _ = P.load()
    assert P.rate_for(data, "transcription", "whisper-1")["usd_per_min"] == 0.006
    assert P.rate_for(data, "transcription", "gpt-4o-transcribe")["in_per_mtok"] == 2.5
    assert P.rate_for(data, "translation", "gpt-4.1-nano")["out_per_mtok"] == 0.4
    for kind, bad in (("transcription", "whisper-large-v3"), ("translation", "gpt-4o")):
        try:
            P.rate_for(data, kind, bad)
        except ValueError as exc:
            assert "No pricing" in str(exc)
        else:
            raise AssertionError(f"expected ValueError for unknown {kind} model")


def test_corrupt_or_missing_file_falls_back_to_builtin(monkeypatch=None) -> None:
    # point the loader at a throwaway file; corrupt and missing both degrade to
    # the built-in copy with provenance 'builtin', never raising
    orig = P._pricing_path
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d) / "pricing.json"
        P._pricing_path = lambda: tmp
        try:
            # missing file
            data, prov = P.load()
            assert prov["source"] == "builtin" and data == P._BUILTIN
            # corrupt file
            tmp.write_text("{not json", encoding="utf-8")
            data, prov = P.load()
            assert prov["source"] == "builtin"
            # structurally invalid (missing a model) also falls back
            tmp.write_text(json.dumps({"last_verified": "x", "transcription": {}, "translation": {}}),
                           encoding="utf-8")
            _, prov = P.load()
            assert prov["source"] == "builtin"
        finally:
            P._pricing_path = orig


def test_validate_rejects_bad_values() -> None:
    bad = json.loads(json.dumps(P._BUILTIN))
    bad["transcription"]["whisper-1"]["usd_per_min"] = -1
    try:
        P._validate(bad)
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError for a negative rate")
    bad2 = json.loads(json.dumps(P._BUILTIN))
    bad2["transcription"]["whisper-1"]["usd_per_min"] = "free"
    try:
        P._validate(bad2)
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError for a non-numeric rate")


def test_set_rate_updates_and_restamps() -> None:
    # operate on an isolated copy so the repo's pricing.json is untouched
    orig = P._pricing_path
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d) / "pricing.json"
        tmp.write_text(json.dumps(P._BUILTIN), encoding="utf-8")
        P._pricing_path = lambda: tmp
        try:
            prov = P._set_rate("transcription", "gpt-4o-transcribe",
                               {"in_per_mtok": 3.0, "out_per_mtok": 12.0,
                                "est_per_min": 0.007, "usd_per_min": None}, "2027-01-02")
            assert prov["last_verified"] == "2027-01-02"
            data, p2 = P.load()
            assert p2["source"] == "file" and data["last_verified"] == "2027-01-02"
            assert P.rate_for(data, "transcription", "gpt-4o-transcribe")["in_per_mtok"] == 3.0
            # unknown model is refused (refresh never invents models)
            try:
                P._set_rate("translation", "gpt-9", {"in_per_mtok": 1.0}, "2027-01-02")
            except ValueError as exc:
                assert "Unknown" in str(exc)
            else:
                raise AssertionError("expected ValueError for unknown model on set")
        finally:
            P._pricing_path = orig


def test_set_rate_validates_fields_by_billing_mode() -> None:
    # a refresh must not restamp last_verified unless it changes a rate that
    # actually applies to the model's billing mode
    orig = P._pricing_path
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d) / "pricing.json"
        tmp.write_text(json.dumps(P._BUILTIN), encoding="utf-8")
        P._pricing_path = lambda: tmp
        try:
            # whisper-1 is duration-billed: token fields do not apply
            try:
                P._set_rate("transcription", "whisper-1", {"in_per_mtok": 1.0}, "2027-01-01")
            except ValueError as exc:
                assert "do not apply" in str(exc)
            else:
                raise AssertionError("expected ValueError for irrelevant field on whisper-1")
            # gpt-4o-transcribe is token-billed: usd_per_min does not apply
            try:
                P._set_rate("transcription", "gpt-4o-transcribe", {"usd_per_min": 0.01}, "2027-01-01")
            except ValueError as exc:
                assert "do not apply" in str(exc)
            else:
                raise AssertionError("expected ValueError for usd_per_min on a token model")
            # no applicable field at all -> refuse (would restamp without a change)
            try:
                P._set_rate("translation", "gpt-4.1-nano", {"in_per_mtok": None, "out_per_mtok": None}, "2027-01-01")
            except ValueError as exc:
                assert "No applicable" in str(exc)
            else:
                raise AssertionError("expected ValueError when no applicable field given")
            # the file was never restamped by any of the rejected calls
            data, _ = P.load()
            assert data["last_verified"] == P._BUILTIN["last_verified"], data["last_verified"]
        finally:
            P._pricing_path = orig


def test_set_rate_rejects_non_iso_as_of() -> None:
    # last_verified provenance is only trustworthy if as-of is a real date; a free
    # word like "yesterday" must be refused and must not restamp the file
    orig = P._pricing_path
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d) / "pricing.json"
        tmp.write_text(json.dumps(P._BUILTIN), encoding="utf-8")
        P._pricing_path = lambda: tmp
        try:
            for bad in ("yesterday", "2027/01/02", "01-02-2027", "2027-13-40", ""):
                try:
                    P._set_rate("translation", "gpt-4.1-nano", {"in_per_mtok": 0.2}, bad)
                except ValueError as exc:
                    assert "YYYY-MM-DD" in str(exc), (bad, str(exc))
                else:
                    raise AssertionError(f"expected ValueError for as-of {bad!r}")
            # none of the rejected calls restamped or changed the stored rate
            data, _ = P.load()
            assert data["last_verified"] == P._BUILTIN["last_verified"], data["last_verified"]
            assert P.rate_for(data, "translation", "gpt-4.1-nano")["in_per_mtok"] == 0.1
        finally:
            P._pricing_path = orig


def main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"ok  {t.__name__}")
    print(f"\n{len(tests)} pricing tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

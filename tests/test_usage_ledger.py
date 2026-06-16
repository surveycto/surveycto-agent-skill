#!/usr/bin/env python3
"""Offline tests for the OpenAI spend ledger.

Cover: cumulative accumulation, sub-cent display, per-operation summary, and
graceful handling of a missing or corrupt ledger file. No network.

Run: python3 tests/test_usage_ledger.py
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "assets" / "transcribe-translate"))

import usage_ledger as UL  # noqa: E402


def _fresh() -> None:
    UL.LEDGER_DIR = Path(tempfile.mkdtemp())
    UL.LEDGER_PATH = UL.LEDGER_DIR / "spend-ledger.json"


def test_usd_display() -> None:
    assert UL.usd_display(0.0) == "$0.00"
    assert UL.usd_display(0.004) == "< $0.01"
    assert UL.usd_display(0.6) == "$0.60"
    assert UL.usd_display(12.5) == "$12.50"


def test_records_accumulate() -> None:
    _fresh()
    r1 = UL.record("translate", "gpt-4.1-nano", "1,000 tokens", 0.25)
    assert r1["run_usd"] == 0.25 and r1["total_usd"] == 0.25
    r2 = UL.record("transcribe", "gpt-4o-mini-transcribe", "10.0 audio-min", 0.03)
    assert abs(r2["total_usd"] - 0.28) < 1e-9, r2
    s = UL.summary()
    assert abs(s["total_usd"] - 0.28) < 1e-9
    assert s["by_operation"]["translate"] == 0.25
    assert abs(s["by_operation"]["transcribe"] - 0.03) < 1e-9
    assert s["runs_recorded"] == 2


def test_negative_is_clamped() -> None:
    _fresh()
    r = UL.record("translate", "m", "x", -5.0)
    assert r["run_usd"] == 0.0 and r["total_usd"] == 0.0


def test_missing_and_corrupt_ledger_are_safe() -> None:
    _fresh()
    # missing file -> empty summary, no crash
    s = UL.summary()
    assert s["total_usd"] == 0.0 and s["runs_recorded"] == 0
    # corrupt file -> treated as empty, and a record still works
    UL.LEDGER_DIR.mkdir(parents=True, exist_ok=True)
    UL.LEDGER_PATH.write_text("{not valid json", encoding="utf-8")
    assert UL.summary()["total_usd"] == 0.0
    r = UL.record("translate", "m", "x", 0.10)
    assert r["total_usd"] == 0.10


def test_history_is_bounded_but_totals_stay_exact() -> None:
    _fresh()
    n = UL._MAX_RUNS_KEPT + 50
    for _ in range(n):
        UL.record("translate", "m", "x", 0.001)
        UL.record("transcribe", "m", "x", 0.002)
    s = UL.summary()
    assert s["runs_recorded"] == UL._MAX_RUNS_KEPT                        # history capped
    assert abs(s["total_usd"] - n * 0.003) < 1e-6                         # grand total exact
    # per-operation totals are persisted, not derived from the trimmed runs,
    # so they still sum to the grand total well past the history cap
    assert abs(s["by_operation"]["translate"] - n * 0.001) < 1e-6, s
    assert abs(s["by_operation"]["transcribe"] - n * 0.002) < 1e-6, s
    assert abs(sum(s["by_operation"].values()) - s["total_usd"]) < 1e-6, s


def test_non_numeric_total_does_not_raise() -> None:
    # a hand-edited but valid-JSON ledger with a bad total must never crash the work
    _fresh()
    UL.LEDGER_DIR.mkdir(parents=True, exist_ok=True)
    UL.LEDGER_PATH.write_text('{"total_usd": "oops", "by_operation": {"translate": "bad"}}',
                              encoding="utf-8")
    assert UL.summary()["total_usd"] == 0.0          # coerced, not raised
    r = UL.record("translate", "m", "x", 0.10)       # recording still works
    assert r["total_usd"] == 0.10


def main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"ok  {t.__name__}")
    print(f"\n{len(tests)} usage-ledger tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

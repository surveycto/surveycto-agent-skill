#!/usr/bin/env python3
"""Offline tests for audio transcription.

A fake adapter stands in for google-cloud-speech, and WAV fixtures are built
with the stdlib ``wave`` module, so these tests run with no Google packages and
no network. They cover WAV duration/cost, unknown-duration handling, the
cost-confirmation gate, the happy path, caching, per-file failure isolation,
and the inline size limit.

Run: python3 tests/test_transcription.py
"""

from __future__ import annotations

import csv
import sys
import tempfile
import wave
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "assets" / "google-cloud"))

import transcription  # noqa: E402


class FakeSpeechAdapter:
    """Mimics the transcription adapter contract."""

    def __init__(self, transcript="hello world", confidence=0.95):
        self.calls = []
        self._transcript = transcript
        self._confidence = confidence

    def transcribe(self, content, language_code, encoding, sample_rate, model):
        self.calls.append(
            {
                "len": len(content),
                "language_code": language_code,
                "encoding": encoding,
                "sample_rate": sample_rate,
                "model": model,
            }
        )
        return {"transcript": self._transcript, "confidence": self._confidence}


def _make_wav(path: Path, seconds: float = 1.0, rate: int = 8000) -> None:
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"\x00\x00" * int(rate * seconds))


def _read_csv(path: Path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def test_wav_duration_and_cost() -> None:
    with tempfile.TemporaryDirectory() as d:
        a = Path(d) / "a.wav"
        _make_wav(a, seconds=20.0)  # 20s -> 2 billed 15s increments
        est = transcription.estimate_cost([str(a)])
        assert abs(est["known_seconds"] - 20.0) < 0.01, est
        assert est["estimated_usd"] == round(2 * 0.016, 4), est
        assert est["within_free_tier"] is True
        assert est["unknown_duration"] == []
        assert "PRIVACY" in est["pii_warning"]


def test_unknown_duration_listed() -> None:
    est = transcription.estimate_cost(["/no/such/file.wav", "/also/missing.mp3"])
    assert est["files"] == 2
    assert set(est["unknown_duration"]) == {
        "/no/such/file.wav",
        "/also/missing.mp3",
    }
    assert est["estimated_usd"] == 0.0


def test_billed_increments_rounds_up() -> None:
    assert transcription._billed_increments(1) == 1
    assert transcription._billed_increments(15) == 1
    assert transcription._billed_increments(16) == 2
    assert transcription._billed_increments(30) == 2
    assert transcription._billed_increments(31) == 3


def test_transcribe_requires_confirm() -> None:
    with tempfile.TemporaryDirectory() as d:
        a = Path(d) / "a.wav"
        out = Path(d) / "out.csv"
        _make_wav(a)
        try:
            transcription.transcribe_files(
                [str(a)], "en-US", str(out), client=FakeSpeechAdapter()
            )
        except PermissionError:
            assert not out.exists()
            return
        raise AssertionError("expected PermissionError without confirm=True")


def test_transcribe_happy_path() -> None:
    with tempfile.TemporaryDirectory() as d:
        a = Path(d) / "a.wav"
        b = Path(d) / "b.wav"
        out = Path(d) / "out.csv"
        _make_wav(a, seconds=2.0)
        _make_wav(b, seconds=3.0)
        adapter = FakeSpeechAdapter(transcript="some words")
        stats = transcription.transcribe_files(
            [str(a), str(b)], "en-US", str(out),
            client=adapter, confirm=True,
        )
        assert stats["transcribed"] == 2, stats
        assert stats["failed"] == 0, stats
        rows = _read_csv(out)
        assert len(rows) == 2
        assert rows[0]["transcript"] == "some words"
        assert rows[0]["status"] == "ok"
        # WAV sample rate is passed through to the adapter
        assert adapter.calls[0]["sample_rate"] == 8000
        assert adapter.calls[0]["encoding"] == "LINEAR16"


def test_transcribe_caches() -> None:
    with tempfile.TemporaryDirectory() as d:
        a = Path(d) / "a.wav"
        out1 = Path(d) / "out1.csv"
        out2 = Path(d) / "out2.csv"
        cache = Path(d) / "cache.db"
        _make_wav(a, seconds=2.0)

        a1 = FakeSpeechAdapter(transcript="cached words")
        s1 = transcription.transcribe_files(
            [str(a)], "en-US", str(out1),
            client=a1, cache_path=str(cache), confirm=True,
        )
        assert s1["transcribed"] == 1 and s1["cached"] == 0

        a2 = FakeSpeechAdapter(transcript="SHOULD NOT BE USED")
        s2 = transcription.transcribe_files(
            [str(a)], "en-US", str(out2),
            client=a2, cache_path=str(cache), confirm=True,
        )
        assert s2["cached"] == 1, s2
        assert s2["transcribed"] == 0, s2
        assert a2.calls == [], "cached run should not call the adapter"
        rows = _read_csv(out2)
        assert rows[0]["transcript"] == "cached words"


def test_failure_isolated_per_file() -> None:
    with tempfile.TemporaryDirectory() as d:
        good = Path(d) / "good.wav"
        out = Path(d) / "out.csv"
        _make_wav(good, seconds=1.0)
        missing = str(Path(d) / "missing.wav")
        stats = transcription.transcribe_files(
            [missing, str(good)], "en-US", str(out),
            client=FakeSpeechAdapter(), confirm=True,
        )
        assert stats["failed"] == 1, stats
        assert stats["transcribed"] == 1, stats
        rows = _read_csv(out)
        by_file = {Path(r["file"]).name: r for r in rows}
        assert by_file["missing.wav"]["status"].startswith("error")
        assert by_file["missing.wav"]["transcript"] == ""
        assert by_file["good.wav"]["status"] == "ok"


def test_inline_size_limit() -> None:
    original = transcription._MAX_INLINE_BYTES
    transcription._MAX_INLINE_BYTES = 10  # tiny, to trigger the guard
    try:
        with tempfile.TemporaryDirectory() as d:
            a = Path(d) / "a.wav"
            out = Path(d) / "out.csv"
            _make_wav(a, seconds=1.0)  # well over 10 bytes
            stats = transcription.transcribe_files(
                [str(a)], "en-US", str(out),
                client=FakeSpeechAdapter(), confirm=True,
            )
            assert stats["failed"] == 1, stats
            rows = _read_csv(out)
            assert "inline size limit" in rows[0]["status"]
    finally:
        transcription._MAX_INLINE_BYTES = original


def test_transcribe_file_single() -> None:
    with tempfile.TemporaryDirectory() as d:
        a = Path(d) / "a.wav"
        _make_wav(a, seconds=4.0)
        res = transcription.transcribe_file(
            str(a), "en-US", client=FakeSpeechAdapter(transcript="one two"),
            confirm=True,
        )
        assert res["transcript"] == "one two"
        assert res["status"] == "ok"
        assert abs(res["duration_seconds"] - 4.0) < 0.01


def test_transcribe_file_requires_confirm() -> None:
    with tempfile.TemporaryDirectory() as d:
        a = Path(d) / "a.wav"
        _make_wav(a, seconds=1.0)
        try:
            transcription.transcribe_file(
                str(a), "en-US", client=FakeSpeechAdapter()
            )
        except PermissionError:
            return
        raise AssertionError("expected PermissionError without confirm=True")


def test_non_numeric_confidence_is_coerced() -> None:
    class WeirdAdapter:
        def transcribe(self, content, language_code, encoding, sample_rate, model):
            return {"transcript": "some text", "confidence": "high"}

    with tempfile.TemporaryDirectory() as d:
        a = Path(d) / "a.wav"
        out = Path(d) / "out.csv"
        _make_wav(a, seconds=1.0)
        stats = transcription.transcribe_files(
            [str(a)], "en-US", str(out), client=WeirdAdapter(), confirm=True
        )
        assert stats["transcribed"] == 1 and stats["failed"] == 0, stats
        row = _read_csv(out)[0]
        assert row["status"] == "ok"
        assert float(row["confidence"]) == 0.0


def test_api_error_is_sanitized_in_status() -> None:
    """An adapter exception must not leak its message into the output CSV."""

    class LeakyAdapter:
        def transcribe(self, content, language_code, encoding, sample_rate, model):
            raise RuntimeError("SECRET-RESPONSE-CONTENT-should-not-appear")

    with tempfile.TemporaryDirectory() as d:
        a = Path(d) / "a.wav"
        out = Path(d) / "out.csv"
        _make_wav(a, seconds=1.0)
        stats = transcription.transcribe_files(
            [str(a)], "en-US", str(out), client=LeakyAdapter(), confirm=True
        )
        assert stats["failed"] == 1, stats
        status = _read_csv(out)[0]["status"]
        assert "SECRET-RESPONSE-CONTENT" not in status, status
        assert "transcription API call failed" in status
        assert "RuntimeError" in status


def test_ffprobe_duration_path_for_non_wav() -> None:
    """Exercise the ffprobe branch of _audio_duration_seconds on a non-WAV file.

    Required in CI (the workflow installs ffmpeg) so the non-WAV duration/cost
    path is verified before any release. Skipped on developer machines that do
    not have ffmpeg/ffprobe so they still pass locally.
    """
    import os
    import shutil
    import subprocess

    if not (shutil.which("ffprobe") and shutil.which("ffmpeg")):
        if os.environ.get("CI"):
            raise AssertionError(
                "ffmpeg/ffprobe must be installed in CI so the non-WAV audio "
                "duration and cost-estimate path is exercised before release. "
                "The CI workflow installs it; this failure means that step is "
                "missing or broke."
            )
        print(
            "  SKIP test_ffprobe_duration_path_for_non_wav "
            "(ffmpeg/ffprobe not installed locally)"
        )
        return

    with tempfile.TemporaryDirectory() as d:
        wav = Path(d) / "src.wav"
        mp3 = Path(d) / "clip.mp3"
        _make_wav(wav, seconds=3.0, rate=16000)
        # Transcode to MP3 so the duration cannot come from the stdlib wave
        # module and must be read via ffprobe.
        subprocess.run(
            ["ffmpeg", "-y", "-i", str(wav), str(mp3)],
            capture_output=True,
            check=True,
        )
        dur = transcription._audio_duration_seconds(str(mp3))
        assert dur is not None, "ffprobe should have measured the mp3 duration"
        assert abs(dur - 3.0) < 0.5, f"unexpected duration {dur}"
        est = transcription.estimate_cost([str(mp3)])
        assert est["unknown_duration"] == [], est
        assert est["known_seconds"] > 0, est


def main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"ok  {t.__name__}")
    print(f"\n{len(tests)} transcription tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

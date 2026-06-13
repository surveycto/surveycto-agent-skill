#!/usr/bin/env python3
"""Offline tests for OpenAI/local transcription.

A fake OpenAI audio client and monkeypatched ffmpeg/ffprobe shims let these run
with no network, no openai package, and no ffmpeg. Cover: model resolution, cost
estimate, single-request happy path, per-file failure isolation, the confirm
gate, sanitized errors, the fits-whole decision, and the adaptive recursive
split that handles audio the model rejects as too large.

Run: python3 tests/test_transcription.py
"""

from __future__ import annotations

import csv
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "assets" / "transcribe-translate"))

import transcription as X  # noqa: E402
import usage_ledger as _UL  # noqa: E402  (same module object X imported)

# Redirect the spend ledger to a throwaway path so tests never touch the real
# ~/.surveycto-skill ledger and stay hermetic.
_UL.LEDGER_DIR = Path(tempfile.mkdtemp())
_UL.LEDGER_PATH = _UL.LEDGER_DIR / "spend-ledger.json"


class BadRequestError(Exception):
    """Named to match the OpenAI SDK error class _is_too_large_error checks for."""


class _Resp:
    def __init__(self, text): self.text = text
class _Transcriptions:
    def __init__(self, handler): self._h = handler; self.calls = []
    def create(self, model, file):
        data = file.read()
        self.calls.append(len(data))
        return _Resp(self._h(data))
class _Audio:
    def __init__(self, tr): self.transcriptions = tr
class FakeClient:
    def __init__(self, handler=None):
        handler = handler or (lambda data: "hello world transcript")
        self.transcriptions = _Transcriptions(handler)
        self.audio = _Audio(self.transcriptions)


def _read(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def test_resolve_model() -> None:
    assert X.resolve_model(None)["id"] == "gpt-4o-mini-transcribe"
    assert X.resolve_model("fast")["id"] == "gpt-4o-mini-transcribe"
    assert X.resolve_model("whisper")["id"] == "whisper-1"
    assert X.resolve_model("whisper")["max_duration_sec"] is None
    assert X.resolve_model("accurate")["max_duration_sec"] == X._GPT4O_MAX_DURATION_SEC
    explicit = X.resolve_model("gpt-4o-transcribe")
    assert explicit["id"] == "gpt-4o-transcribe" and explicit["max_duration_sec"] is not None
    assert X.resolve_model("whisper-large-v3")["max_duration_sec"] is None


def test_estimate_cost() -> None:
    orig = X._audio_duration_seconds
    X._audio_duration_seconds = lambda p: 120.0  # 2 min each
    try:
        with tempfile.TemporaryDirectory() as d:
            a = Path(d) / "a.mp3"; a.write_bytes(b"audio")
            est = X.estimate_cost([str(a), "/no/such.mp3"], model="fast")
            assert abs(est["known_seconds"] - 120.0) < 0.01, est
            assert est["unknown_duration"] == ["/no/such.mp3"]
            assert est["estimated_usd"] == round(2.0 * 0.003, 4), est
            assert est["estimated_usd_display"] == "< $0.01", est  # 0.006 is sub-cent
            assert "PRIVACY" in est["pii_warning"]
            # local provider is free
            loc = X.estimate_cost([str(a)], provider="local")
            assert loc["estimated_usd"] == 0.0 and "free" in loc["estimated_usd_display"], loc
            # local mode must NOT claim the audio is uploaded; cloud mode must
            assert "will be sent to OpenAI" in est["pii_warning"], est
            assert "on-device" in loc["pii_warning"], loc
            assert "NOT sent to OpenAI" in loc["pii_warning"], loc
            assert "will be sent to OpenAI" not in loc["pii_warning"], loc
        assert X._usd_display(0.024) == "$0.02" and X._usd_display(0.0) == "$0.00"
    finally:
        X._audio_duration_seconds = orig


def test_transcribe_happy_path_and_cache() -> None:
    orig = X._audio_duration_seconds
    X._audio_duration_seconds = lambda p: 30.0
    try:
        with tempfile.TemporaryDirectory() as d:
            a = Path(d) / "a.mp3"; a.write_bytes(b"some audio bytes")
            out = Path(d) / "o.csv"; cache = Path(d) / "c.db"
            c = FakeClient(lambda data: "the borehole is dry")
            s = X.transcribe_files([str(a)], str(out), cache_path=str(cache),
                                   confirm=True, client=c)
            assert s["transcribed"] == 1 and s["failed"] == 0, s
            r = _read(out)
            assert r[0]["transcript"] == "the borehole is dry" and r[0]["status"] == "ok"
            assert r[0]["backend"] == "gpt-4o-mini-transcribe"
            # cached re-run: no client calls
            c2 = FakeClient(lambda data: "SHOULD NOT BE USED")
            out2 = Path(d) / "o2.csv"
            s2 = X.transcribe_files([str(a)], str(out2), cache_path=str(cache),
                                    confirm=True, client=c2)
            assert s2["cached"] == 1 and s2["transcribed"] == 0
            assert c2.transcriptions.calls == []
            assert _read(out2)[0]["transcript"] == "the borehole is dry"
    finally:
        X._audio_duration_seconds = orig


def test_confirm_gate() -> None:
    with tempfile.TemporaryDirectory() as d:
        a = Path(d) / "a.mp3"; a.write_bytes(b"x"); out = Path(d) / "o.csv"
        try:
            X.transcribe_files([str(a)], str(out), confirm=False, client=FakeClient())
        except PermissionError:
            assert not out.exists(); return
        raise AssertionError("expected PermissionError without confirm")


def test_failure_isolated_and_sanitized() -> None:
    orig = X._audio_duration_seconds
    X._audio_duration_seconds = lambda p: 10.0
    try:
        with tempfile.TemporaryDirectory() as d:
            good = Path(d) / "good.mp3"; good.write_bytes(b"ok")
            out = Path(d) / "o.csv"
            missing = str(Path(d) / "missing.mp3")
            leaky = FakeClient(lambda data: (_ for _ in ()).throw(Exception("SECRET_AUDIO_CONTENT")))
            # good file uses a separate client that succeeds
            # run missing + a file whose client raises a secret-bearing error
            bad = Path(d) / "bad.mp3"; bad.write_bytes(b"bad")
            s = X.transcribe_files([missing, str(bad)], str(out), confirm=True, client=leaky)
            assert s["failed"] == 2, s
            by = {Path(r["file"]).name: r for r in _read(out)}
            assert by["missing.mp3"]["status"].startswith("error")
            assert "transcription failed" in by["bad.mp3"]["status"]
            assert "SECRET_AUDIO_CONTENT" not in by["bad.mp3"]["status"], "leaked content"
    finally:
        X._audio_duration_seconds = orig


def test_fits_whole() -> None:
    orig_g = X.os.path.getsize; orig_d = X._audio_duration_seconds
    try:
        X.os.path.getsize = lambda p: 1000
        X._audio_duration_seconds = lambda p: 100.0
        assert X._fits_whole("x", X.resolve_model("fast")) is True          # small+short
        X._audio_duration_seconds = lambda p: 5000.0                        # 83 min
        assert X._fits_whole("x", X.resolve_model("fast")) is False         # over gpt-4o cap
        assert X._fits_whole("x", X.resolve_model("whisper")) is True       # whisper: no dur cap
        X.os.path.getsize = lambda p: X._MAX_BYTES + 1
        X._audio_duration_seconds = lambda p: 10.0
        assert X._fits_whole("x", X.resolve_model("whisper")) is False      # over size
    finally:
        X.os.path.getsize = orig_g; X._audio_duration_seconds = orig_d


def test_adaptive_split_succeeds_on_too_large() -> None:
    # fake ffmpeg: write `length` bytes; fake client: reject >40 bytes as too-large
    orig_ex = X._extract_chunk
    THRESH = 40
    X._extract_chunk = lambda src, start, length, dst: open(dst, "wb").write(b"x" * max(1, int(length)))
    def handler(data):
        if len(data) > THRESH:
            raise BadRequestError("Error code: 400 input_too_large")
        return f"<{len(data)}>"
    try:
        c = FakeClient(handler)
        text = X._transcribe_segment("src", 0.0, 100.0, "gpt-4o-mini-transcribe", c)
        # larger calls were the failed attempts that triggered splitting; the
        # leaves that actually produced text are within the limit
        assert text and ("<25>" in text or "<26>" in text), text
        assert any(n <= THRESH for n in c.transcriptions.calls), c.transcriptions.calls
    finally:
        X._extract_chunk = orig_ex


def test_adaptive_split_floor_raises() -> None:
    orig_ex = X._extract_chunk
    X._extract_chunk = lambda src, start, length, dst: open(dst, "wb").write(b"x" * max(1, int(length)))
    def handler(data):  # everything is "too large" -> must hit the split floor
        raise BadRequestError("input_too_large")
    try:
        try:
            X._transcribe_segment("src", 0.0, 100.0, "gpt-4o-mini-transcribe", FakeClient(handler))
        except RuntimeError as exc:
            assert "too large" in str(exc); return
        raise AssertionError("expected RuntimeError at the split floor")
    finally:
        X._extract_chunk = orig_ex


def test_stitch_removes_overlap_duplication() -> None:
    # the chunk overlap repeats words at the seam; _stitch must drop the repeat
    left = "the well has been dry since"
    right = "since early March and the pump"
    assert X._stitch(left, right) == "the well has been dry since early March and the pump"
    # punctuation/case differences in the overlap are still matched
    assert X._stitch("we visited the Village.", "village. it was empty") == \
        "we visited the Village. it was empty"
    # no overlap -> plain join, nothing dropped
    assert X._stitch("alpha beta", "gamma delta") == "alpha beta gamma delta"
    # empty pieces
    assert X._stitch("", "only right") == "only right"
    assert X._stitch("only left", "") == "only left"


def test_missing_file_status_has_no_path() -> None:
    with tempfile.TemporaryDirectory() as d:
        out = Path(d) / "o.csv"
        secret = str(Path(d) / "respondent_jane_doe_2024.mp3")  # path itself is sensitive
        s = X.transcribe_files([secret], str(out), confirm=True, client=FakeClient())
        assert s["failed"] == 1, s
        row = _read(out)[0]
        assert row["status"] == "error: audio file not found", row
        assert "jane_doe" not in row["status"], "leaked the file path into status"
        assert row["file"] == secret  # path still available in its own column


def test_unknown_exception_status_is_type_name_only() -> None:
    orig = X._audio_duration_seconds
    X._audio_duration_seconds = lambda p: 10.0
    try:
        with tempfile.TemporaryDirectory() as d:
            a = Path(d) / "a.mp3"; a.write_bytes(b"x"); out = Path(d) / "o.csv"
            leaky = FakeClient(lambda data: (_ for _ in ()).throw(
                RuntimeError("MODEL_ECHOED_THE_AUDIO_TRANSCRIPT_xyz")))
            s = X.transcribe_files([str(a)], str(out), confirm=True, client=leaky)
            assert s["failed"] == 1, s
            status = _read(out)[0]["status"]
            assert "MODEL_ECHOED" not in status, status
            assert status.startswith("error: transcription failed ("), status
    finally:
        X._audio_duration_seconds = orig


def test_too_large_detection_is_not_pinned_to_one_class() -> None:
    class APIStatusError(Exception):
        pass
    assert X._is_too_large_error(APIStatusError("maximum context length exceeded"))
    assert X._is_too_large_error(BadRequestError("input_too_large"))
    # real token-limit message from the API contains "too large"
    assert X._is_too_large_error(BadRequestError(
        "Total number of tokens in instructions + audio is too large"))
    assert not X._is_too_large_error(Exception("rate limit reached"))
    # a bare "413" inside an unrelated message must NOT be treated as too-large
    assert not X._is_too_large_error(Exception("request id req-1413abc rate limited"))
    # a structured 413 status IS too-large
    class Sized(Exception):
        status_code = 413
    assert X._is_too_large_error(Sized("payload"))
    class Coded(Exception):
        code = "context_length_exceeded"
    assert X._is_too_large_error(Coded("nope"))


def test_stitch_window_is_bounded() -> None:
    # a run longer than the overlap window is not fully collapsed (guards against
    # eating a long coincidental similarity between two distinct passages)
    left = "w " * 10
    right = ("w " * 10) + "end"
    out = X._stitch(left, right, max_overlap_words=8)
    assert out.split().count("w") == 12, out  # 10 + (10-8) kept, not collapsed to 10


def test_missing_ffmpeg_raises_actionable_error() -> None:
    orig = X.shutil.which
    X.shutil.which = lambda name: None
    try:
        with tempfile.TemporaryDirectory() as d:
            try:
                X._extract_chunk("src.mp3", 0.0, 10.0, str(Path(d) / "o.mp3"))
            except X.TranscriptionError as exc:
                assert "ffmpeg" in str(exc).lower(), exc
                return
            raise AssertionError("expected TranscriptionError when ffmpeg is absent")
    finally:
        X.shutil.which = orig


def test_windowed_multipart_path_stitches() -> None:
    # force chunking (dur > gpt-4o cap) and verify the top-level windowed loop runs
    orig_d = X._audio_duration_seconds; orig_g = X.os.path.getsize; orig_ex = X._extract_chunk
    X._audio_duration_seconds = lambda p: 1800.0          # 30 min > 600s cap -> chunks
    X.os.path.getsize = lambda p: 5_000_000               # whole-file > nothing special
    X._extract_chunk = lambda src, start, length, dst: open(dst, "wb").write(b"x" * 100)
    try:
        with tempfile.TemporaryDirectory() as d:
            a = Path(d) / "a.mp3"; a.write_bytes(b"x"); out = Path(d) / "o.csv"
            counter = {"n": 0}
            def handler(data):
                counter["n"] += 1
                return f"part{counter['n']}"
            s = X.transcribe_files([str(a)], str(out), confirm=True, client=FakeClient(handler))
            assert s["transcribed"] == 1 and s["failed"] == 0, s
            text = _read(out)[0]["transcript"]
            assert counter["n"] >= 3, "expected multiple windowed chunks"
            assert "part1" in text and f"part{counter['n']}" in text, text
    finally:
        X._audio_duration_seconds = orig_d; X.os.path.getsize = orig_g; X._extract_chunk = orig_ex


def test_actual_spend_billed_on_audio_minutes() -> None:
    orig = X._audio_duration_seconds
    X._audio_duration_seconds = lambda p: 120.0  # 2 min
    _UL.LEDGER_PATH.unlink(missing_ok=True)
    try:
        with tempfile.TemporaryDirectory() as d:
            a = Path(d) / "a.mp3"; a.write_bytes(b"x"); out = Path(d) / "o.csv"
            # fast model: $0.003/audio-min * 2 min = $0.006 -> sub-cent display
            s = X.transcribe_files([str(a)], str(out), confirm=True, client=FakeClient())
            assert abs(s["actual_usd"] - 0.006) < 1e-6, s
            assert s["actual_usd_display"] == "< $0.01"
            assert abs(s["total_spend_usd"] - 0.006) < 1e-6, s
            # local provider must record nothing (free) but still report the total
            orig_local = X._transcribe_local_file
            X._transcribe_local_file = lambda path, lm: "on-device text"
            try:
                b = Path(d) / "b.mp3"; b.write_bytes(b"y"); out2 = Path(d) / "o2.csv"
                s2 = X.transcribe_files([str(b)], str(out2), provider="local", confirm=True,
                                        client=FakeClient())
                assert s2["transcribed"] == 1 and s2["actual_usd"] == 0.0, s2
                assert abs(s2["total_spend_usd"] - 0.006) < 1e-6, s2  # unchanged by local run
            finally:
                X._transcribe_local_file = orig_local
    finally:
        X._audio_duration_seconds = orig


def test_cache_file_is_chmod_600() -> None:
    import stat
    orig = X._audio_duration_seconds
    X._audio_duration_seconds = lambda p: 30.0
    try:
        with tempfile.TemporaryDirectory() as d:
            a = Path(d) / "a.mp3"; a.write_bytes(b"x"); out = Path(d) / "o.csv"
            cache = Path(d) / "c.db"
            X.transcribe_files([str(a)], str(out), cache_path=str(cache),
                               confirm=True, client=FakeClient())
            mode = stat.S_IMODE(cache.stat().st_mode)
            assert mode == 0o600, oct(mode)
    finally:
        X._audio_duration_seconds = orig


def main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"ok  {t.__name__}")
    print(f"\n{len(tests)} transcription tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

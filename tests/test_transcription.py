#!/usr/bin/env python3
"""Offline tests for OpenAI transcription.

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
    """Mirrors the real openai.BadRequestError for the token-limit case: a 400 with
    structured code='input_too_large' (the fields _is_too_large_error keys off,
    confirmed against the live API)."""
    def __init__(self, message="", code="input_too_large", status_code=400):
        super().__init__(message)
        self.code = code
        self.status_code = status_code


class _Resp:
    def __init__(self, text): self.text = text
class _Transcriptions:
    def __init__(self, handler): self._h = handler; self.calls = []; self.languages = []
    def create(self, model, file, language=None):
        data = file.read()
        self.calls.append(len(data))
        self.languages.append(language)
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
    # a model id behind a menu name resolves to that entry's exact rate
    explicit = X.resolve_model("gpt-4o-transcribe")
    assert explicit["id"] == "gpt-4o-transcribe" and explicit["usd_per_min"] == 0.006
    assert X.resolve_model("gpt-4o-mini-transcribe")["usd_per_min"] == 0.003  # not the 0.006 default
    # an unknown id fails closed (pricing would be a guess)
    try:
        X.resolve_model("whisper-large-v3")
    except ValueError as exc:
        assert "Unknown transcription model" in str(exc)
    else:
        raise AssertionError("expected ValueError for an unknown model id")


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
            assert "PRIVACY" in est["pii_warning"] and "sent to OpenAI" in est["pii_warning"]
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


def test_egress_detection_is_sdk_typed() -> None:
    # deterministic: only the OpenAI SDK connection type counts as an egress error
    assert X._is_egress_error(OSError("boom")) is False
    try:
        import httpx
        from openai import APIConnectionError
    except Exception:
        print("  (skipped openai-typed assertion: openai not installed)")
        return
    exc = APIConnectionError(request=httpx.Request("POST", "https://api.openai.com/v1/audio/transcriptions"))
    assert X._is_egress_error(exc) is True


def test_no_egress_gives_actionable_error() -> None:
    try:
        import httpx
        from openai import APIConnectionError
    except Exception:
        print("  (skipped: openai not installed)")
        return
    exc = APIConnectionError(request=httpx.Request("POST", "https://api.openai.com/v1/audio/transcriptions"))
    orig = X._audio_duration_seconds
    X._audio_duration_seconds = lambda p: 10.0
    try:
        with tempfile.TemporaryDirectory() as d:
            a = Path(d) / "a.mp3"; a.write_bytes(b"x"); out = Path(d) / "o.csv"
            boom = FakeClient(lambda data: (_ for _ in ()).throw(exc))
            s = X.transcribe_files([str(a)], str(out), confirm=True, client=boom)
            assert s["failed"] == 1, s
            status = _read(out)[0]["status"]
            assert "api.openai.com" in status and "egress" in status.lower(), status
    finally:
        X._audio_duration_seconds = orig


def test_unmeasurable_duration_fails_no_silent_zero_spend() -> None:
    # if ffprobe can't read duration, a paid call must NOT happen and must NOT be
    # booked as $0.00 (that silently under-reports spend)
    orig = X._audio_duration_seconds
    X._audio_duration_seconds = lambda p: None
    _UL.LEDGER_PATH.unlink(missing_ok=True)
    try:
        with tempfile.TemporaryDirectory() as d:
            a = Path(d) / "a.mp3"; a.write_bytes(b"x"); out = Path(d) / "o.csv"
            c = FakeClient(lambda data: "SHOULD NOT BE CALLED")
            s = X.transcribe_files([str(a)], str(out), confirm=True, client=c)
            assert s["transcribed"] == 0 and s["failed"] == 1, s
            assert c.transcriptions.calls == [], "made a paid call with unknown duration"
            row = _read(out)[0]
            assert row["status"].startswith("error") and "duration" in row["status"], row
            assert s["total_spend_usd"] == 0.0, s  # nothing billed, nothing recorded
    finally:
        X._audio_duration_seconds = orig


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
        text, submitted = X._transcribe_segment("src", 0.0, 100.0, "gpt-4o-mini-transcribe", c)
        # larger calls were the failed attempts that triggered splitting; the
        # leaves that actually produced text are within the limit
        assert text and ("<25>" in text or "<26>" in text), text
        assert any(n <= THRESH for n in c.transcriptions.calls), c.transcriptions.calls
        # submitted seconds include the overlap re-sent at each seam -> > 100
        assert submitted > 100.0, submitted
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


def test_too_large_detection_uses_structured_fields() -> None:
    # Mirrors the real API responses (captured live):
    # token limit -> 400 BadRequestError, code='input_too_large'
    class TokenLimit(Exception):
        code = "input_too_large"; status_code = 400
    assert X._is_too_large_error(TokenLimit("Total number of tokens ... is too large"))
    # byte limit -> 413 APIStatusError, code=None
    class TooBig(Exception):
        code = None; status_code = 413
    assert X._is_too_large_error(TooBig("413: Maximum content size limit exceeded"))
    # unrelated errors are NOT too-large: a different 400 code, a rate-limit, or a
    # message that merely contains "413"/"too large" in prose
    class OtherBadRequest(Exception):
        code = "invalid_value"; status_code = 400
    assert not X._is_too_large_error(OtherBadRequest("unsupported file format"))
    assert not X._is_too_large_error(Exception("rate limit reached"))
    assert not X._is_too_large_error(Exception("request id req-1413abc; file is too large for email"))


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
            # a fully-cached re-run records nothing (no API call) but reports the total
            cache = Path(d) / "c.db"
            X.transcribe_files([str(a)], str(out), cache_path=str(cache), confirm=True, client=FakeClient())
            before = X.usage_ledger.summary()["total_usd"]
            s2 = X.transcribe_files([str(a)], str(out), cache_path=str(cache), confirm=True, client=FakeClient())
            assert s2["cached"] == 1 and s2["actual_usd"] == 0.0, s2
            assert abs(s2["total_spend_usd"] - before) < 1e-6, s2  # unchanged by a cached run
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


def test_language_hint_forwarded_to_api() -> None:
    orig = X._audio_duration_seconds
    X._audio_duration_seconds = lambda p: 30.0
    try:
        with tempfile.TemporaryDirectory() as d:
            a = Path(d) / "a.mp3"; a.write_bytes(b"x")
            c = FakeClient()
            X.transcribe_files([str(a)], str(Path(d) / "o.csv"), confirm=True,
                               client=c, language="es")
            assert c.transcriptions.languages == ["es"], c.transcriptions.languages
            c2 = FakeClient()
            X.transcribe_files([str(a)], str(Path(d) / "o2.csv"), confirm=True, client=c2)
            assert c2.transcriptions.languages == [None], c2.transcriptions.languages  # auto-detect
    finally:
        X._audio_duration_seconds = orig


def test_cache_keyed_by_language() -> None:
    orig = X._audio_duration_seconds
    X._audio_duration_seconds = lambda p: 30.0
    try:
        with tempfile.TemporaryDirectory() as d:
            a = Path(d) / "a.mp3"; a.write_bytes(b"x"); cache = Path(d) / "c.db"
            # auto-detect run populates the cache under language='auto'
            X.transcribe_files([str(a)], str(Path(d) / "o1.csv"), cache_path=str(cache),
                               confirm=True, client=FakeClient(lambda data: "auto transcript"))
            # a run with --language es must NOT reuse the auto transcript
            s2 = X.transcribe_files([str(a)], str(Path(d) / "o2.csv"), cache_path=str(cache),
                                    confirm=True, language="es",
                                    client=FakeClient(lambda data: "es transcript"))
            assert s2["transcribed"] == 1 and s2["cached"] == 0, s2  # cache miss
            assert _read(Path(d) / "o2.csv")[0]["transcript"] == "es transcript"
            # re-running es now hits the cache (no client call)
            c3 = FakeClient(lambda data: "SHOULD NOT BE USED")
            s3 = X.transcribe_files([str(a)], str(Path(d) / "o3.csv"), cache_path=str(cache),
                                    confirm=True, language="es", client=c3)
            assert s3["cached"] == 1 and c3.transcriptions.calls == [], s3
    finally:
        X._audio_duration_seconds = orig


def test_chunked_billing_includes_overlap() -> None:
    # force chunking (dur > gpt-4o cap, window capped at 600s) and confirm the
    # billed amount reflects the audio actually submitted (overlap), not just dur
    orig_d = X._audio_duration_seconds; orig_g = X.os.path.getsize; orig_ex = X._extract_chunk
    X._audio_duration_seconds = lambda p: 1800.0
    X.os.path.getsize = lambda p: 5_000_000
    X._extract_chunk = lambda src, start, length, dst: open(dst, "wb").write(b"x" * 100)
    _UL.LEDGER_PATH.unlink(missing_ok=True)
    try:
        with tempfile.TemporaryDirectory() as d:
            a = Path(d) / "a.mp3"; a.write_bytes(b"x"); out = Path(d) / "o.csv"
            s = X.transcribe_files([str(a)], str(out), confirm=True, client=FakeClient())
            file_only = round(X._billed_minutes(1800.0) * 0.003, 6)  # billing on dur alone
            assert s["transcribed"] == 1, s
            assert s["actual_usd"] > file_only, (s["actual_usd"], file_only)  # overlap counted
            assert s["actual_usd"] < file_only * 1.05, s  # but only slightly (a few seams)
    finally:
        X._audio_duration_seconds = orig_d; X.os.path.getsize = orig_g; X._extract_chunk = orig_ex


def main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"ok  {t.__name__}")
    print(f"\n{len(tests)} transcription tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

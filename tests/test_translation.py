#!/usr/bin/env python3
"""Offline tests for OpenAI user-data translation.

A fake OpenAI chat client stands in for the SDK, so these run with no network and
no openai package. Cover: skip-list, cost math, dedup, cache, glossary,
length-validated structured output (no silent truncation), sanitized errors,
the confirm gate, no-overwrite, ragged/duplicate headers, and special-char
round-trip.

Run: python3 tests/test_translation.py
"""

from __future__ import annotations

import csv
import json
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "assets" / "transcribe-translate"))

import translation as T  # noqa: E402
import usage_ledger as _UL  # noqa: E402  (same module object T imported)

# Redirect the spend ledger to a throwaway path so tests never touch the real
# ~/.surveycto-skill ledger and stay hermetic.
_UL.LEDGER_DIR = Path(tempfile.mkdtemp())
_UL.LEDGER_PATH = _UL.LEDGER_DIR / "spend-ledger.json"


class _Msg:
    def __init__(self, content): self.content = content
class _Choice:
    def __init__(self, content): self.message = _Msg(content)
class _Resp:
    def __init__(self, content): self.choices = [_Choice(content)]
class _Completions:
    def __init__(self, transform): self._t = transform; self.calls = []
    def create(self, model, temperature, response_format, messages):
        inputs = json.loads(messages[1]["content"])["inputs"]
        self.calls.append(list(inputs))
        return _Resp(json.dumps({"translations": self._t(inputs)}))
class _Chat:
    def __init__(self, comp): self.completions = comp
class FakeClient:
    """Mimics openai.OpenAI for chat.completions.create."""
    def __init__(self, transform=None):
        transform = transform or (lambda xs: [f"EN[{x}]" for x in xs])
        self.completions = _Completions(transform)
        self.chat = _Chat(self.completions)


def _write(path, fieldnames, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames); w.writeheader()
        for r in rows: w.writerow(r)
def _read(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def test_should_skip() -> None:
    for v in ["", "  ", "999", "-99", "N/A", ".", "5", "3.14", "x"]:
        assert T._should_skip(v), v
    for v in ["hola mundo", "está bien", "nan", "inf", "no se"]:
        assert not T._should_skip(v), v


def test_estimate_cost() -> None:
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "x.csv"
        _write(p, ["id", "note"], [{"id": "1", "note": "hola mundo"},
                                   {"id": "2", "note": "999"},
                                   {"id": "3", "note": "buenos dias"}])
        est = T.estimate_cost(str(p), ["note"], "en")
        assert est["cells_to_translate"] == 2, est
        assert est["cells_skipped"] == 1, est  # the "999" code
        assert est["billable_chars"] == len("hola mundo") + len("buenos dias")
        assert est["model"] == "gpt-4.1-nano"
        assert "PRIVACY" in est["pii_warning"]
        # sub-cent estimates must read as "< $0.01", never a misleading "$0.00"
        assert est["estimated_usd"] < 0.01 and est["estimated_usd_display"] == "< $0.01", est
    assert T._usd_display(0.0) == "$0.00"
    assert T._usd_display(0.004) == "< $0.01"
    assert T._usd_display(0.024) == "$0.02"
    assert T._usd_display(1.5) == "$1.50"


def test_translate_basic_skip_columns() -> None:
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "x.csv"; out = Path(d) / "o.csv"
        _write(p, ["id", "note"], [{"id": "1", "note": "hola"},
                                   {"id": "2", "note": "999"},
                                   {"id": "3", "note": "adios"}])
        c = FakeClient()
        s = T.translate_csv(str(p), ["note"], "en", "es", str(out), client=c, confirm=True)
        assert s["cells_translated"] == 2 and s["cells_skipped"] == 1, s
        r = _read(out)
        assert r[0]["note_en"] == "EN[hola]" and r[1]["note_en"] == "" and r[2]["note_en"] == "EN[adios]"
        assert r[0]["note"] == "hola"  # original preserved


def test_dedup_one_unique_sent() -> None:
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "x.csv"; out = Path(d) / "o.csv"
        _write(p, ["note"], [{"note": "hola"}, {"note": "hola"}, {"note": "hola"}])
        c = FakeClient()
        s = T.translate_csv(str(p), ["note"], "en", "es", str(out), client=c, confirm=True)
        assert s["cells_translated"] == 3
        sent = [t for batch in c.completions.calls for t in batch]
        assert sent == ["hola"], sent


def test_cache_free_rerun() -> None:
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "x.csv"; o1 = Path(d) / "o1.csv"; o2 = Path(d) / "o2.csv"
        cache = Path(d) / "c.db"
        _write(p, ["note"], [{"note": "hola"}, {"note": "adios"}])
        T.translate_csv(str(p), ["note"], "en", "es", str(o1), client=FakeClient(),
                        cache_path=str(cache), confirm=True)
        c2 = FakeClient()
        s2 = T.translate_csv(str(p), ["note"], "en", "es", str(o2), client=c2,
                             cache_path=str(cache), confirm=True)
        assert s2["cells_cached"] == 2 and s2["cells_translated"] == 0, s2
        assert c2.completions.calls == []
        assert _read(o1) == _read(o2)


def test_glossary_overlay_independent_of_cache() -> None:
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "x.csv"; o1 = Path(d) / "o1.csv"; o2 = Path(d) / "o2.csv"
        cache = Path(d) / "c.db"; gl = Path(d) / "g.csv"
        _write(p, ["note"], [{"note": "household"}])
        _write(gl, ["source", "target"], [{"source": "EN[household]", "target": "HH"}])
        # run 1 with glossary, populates cache with RAW translation
        T.translate_csv(str(p), ["note"], "en", "es", str(o1), client=FakeClient(),
                        cache_path=str(cache), glossary_path=str(gl), confirm=True)
        assert "HH" in _read(o1)[0]["note_en"]
        # run 2 no glossary, served from cache -> raw shows through
        c2 = FakeClient()
        s2 = T.translate_csv(str(p), ["note"], "en", "es", str(o2), client=c2,
                             cache_path=str(cache), confirm=True)
        assert s2["cells_cached"] == 1 and c2.completions.calls == []
        assert _read(o2)[0]["note_en"] == "EN[household]"


def test_length_mismatch_fails_loud_and_sanitized() -> None:
    # model returns the WRONG number of translations -> must error, never silently
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "x.csv"; out = Path(d) / "o.csv"
        secret = "RESPONDENT_PII_jane_at_42"
        _write(p, ["note"], [{"note": secret}, {"note": "otra cosa"}])
        bad = FakeClient(transform=lambda xs: ["only one"])  # returns 1 for 2
        try:
            T.translate_csv(str(p), ["note"], "en", "es", str(out), client=bad,
                            confirm=True, max_retries=0)
        except RuntimeError as exc:
            assert "translation API call failed" in str(exc)
            assert secret not in str(exc), "source text leaked in error"
            return
        raise AssertionError("expected RuntimeError on length mismatch")


def test_transient_error_retries_then_succeeds() -> None:
    real_sleep = T.time.sleep; T.time.sleep = lambda s: None
    try:
        class Flaky(FakeClient):
            def __init__(self):
                super().__init__(); self.n = 0
                outer = self
                class C:
                    def create(self2, **kw):
                        outer.n += 1
                        if outer.n < 2:
                            raise RuntimeError("503 service unavailable")
                        inputs = json.loads(kw["messages"][1]["content"])["inputs"]
                        return _Resp(json.dumps({"translations": [f"EN[{x}]" for x in inputs]}))
                self.chat = _Chat(C())
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "x.csv"; out = Path(d) / "o.csv"
            _write(p, ["note"], [{"note": "hola"}])
            c = Flaky()
            s = T.translate_csv(str(p), ["note"], "en", "es", str(out), client=c, confirm=True)
            assert s["cells_translated"] == 1 and c.n == 2
    finally:
        T.time.sleep = real_sleep


def test_confirm_gate() -> None:
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "x.csv"; out = Path(d) / "o.csv"
        _write(p, ["note"], [{"note": "hola"}])
        try:
            T.translate_csv(str(p), ["note"], "en", "es", str(out), client=FakeClient())
        except PermissionError:
            assert not out.exists()
            return
        raise AssertionError("expected PermissionError without confirm")


def test_no_overwrite() -> None:
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "x.csv"; out = Path(d) / "o.csv"
        _write(p, ["note", "note_en"], [{"note": "hola", "note_en": "x"}])
        try:
            T.translate_csv(str(p), ["note"], "en", "es", str(out), client=FakeClient(), confirm=True)
        except ValueError as exc:
            assert "already exists" in str(exc); return
        raise AssertionError("expected ValueError for existing output column")


def test_dup_header_rejected_and_ragged_ok() -> None:
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "dup.csv"
        p.write_text("note,note,id\na,b,1\n", encoding="utf-8")
        try:
            T.estimate_cost(str(p), ["note"], "en")
        except ValueError as exc:
            assert "duplicate column names" in str(exc)
        else:
            raise AssertionError("expected duplicate-header error")
        p2 = Path(d) / "rag.csv"; out = Path(d) / "o.csv"
        p2.write_text("id,note\n1,hola\n2,adios,EXTRA\n", encoding="utf-8")
        s = T.translate_csv(str(p2), ["note"], "en", "es", str(out), client=FakeClient(), confirm=True)
        assert s["cells_translated"] == 2


def test_special_chars_roundtrip() -> None:
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "x.csv"; out = Path(d) / "o.csv"
        tricky = 'dijo: "hola, qué tal", y se fue'
        _write(p, ["note"], [{"note": tricky}])
        # echo the input back as the "translation" to verify exact round-trip
        c = FakeClient(transform=lambda xs: list(xs))
        T.translate_csv(str(p), ["note"], "en", "es", str(out), client=c, confirm=True)
        r = _read(out)
        assert r[0]["note"] == tricky and r[0]["note_en"] == tricky


def test_length_mismatch_retries_then_succeeds() -> None:
    # a wrong-count response is a transient slip: retry, then succeed (no truncation)
    real_sleep = T.time.sleep; T.time.sleep = lambda s: None
    try:
        class Flaky(FakeClient):
            def __init__(self):
                super().__init__(); self.n = 0
                outer = self
                class C:
                    def create(self2, **kw):
                        outer.n += 1
                        inputs = json.loads(kw["messages"][1]["content"])["inputs"]
                        if outer.n < 2:
                            return _Resp(json.dumps({"translations": ["only one"]}))  # wrong count
                        return _Resp(json.dumps({"translations": [f"EN[{x}]" for x in inputs]}))
                self.chat = _Chat(C())
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "x.csv"; out = Path(d) / "o.csv"
            _write(p, ["note"], [{"note": "hola"}, {"note": "adios"}])
            c = Flaky()
            s = T.translate_csv(str(p), ["note"], "en", "es", str(out), client=c, confirm=True)
            assert s["cells_translated"] == 2 and c.n == 2, (s, c.n)
            assert _read(out)[0]["note_en"] == "EN[hola]"
    finally:
        T.time.sleep = real_sleep


def test_non_retryable_error_fails_fast() -> None:
    # an auth error must NOT be retried (don't hammer a bad key); one call, then fail
    real_sleep = T.time.sleep; T.time.sleep = lambda s: None
    try:
        class AuthBoom(FakeClient):
            def __init__(self):
                super().__init__(); self.n = 0
                outer = self
                class AuthenticationError(Exception):
                    pass
                class C:
                    def create(self2, **kw):
                        outer.n += 1
                        raise AuthenticationError("invalid api key")
                self.chat = _Chat(C())
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "x.csv"; out = Path(d) / "o.csv"
            _write(p, ["note"], [{"note": "hola"}])
            c = AuthBoom()
            try:
                T.translate_csv(str(p), ["note"], "en", "es", str(out), client=c, confirm=True)
            except RuntimeError as exc:
                assert c.n == 1, f"retried a non-retryable error ({c.n} calls)"
                assert "invalid api key" not in str(exc), "leaked error content"
                return
            raise AssertionError("expected RuntimeError on auth failure")
    finally:
        T.time.sleep = real_sleep


def test_actual_spend_recorded_and_accumulates() -> None:
    # a usage-bearing response -> actual cost billed on real tokens, accumulated
    class _Usage:
        prompt_tokens = 2_000_000
        completion_tokens = 1_000_000
    class _RespU(_Resp):
        def __init__(self, content): super().__init__(content); self.usage = _Usage()
    class _CompU(_Completions):
        def create(self, model, temperature, response_format, messages):
            inputs = json.loads(messages[1]["content"])["inputs"]
            self.calls.append(list(inputs))
            return _RespU(json.dumps({"translations": [f"EN[{x}]" for x in inputs]}))
    class UsageClient(FakeClient):
        def __init__(self):
            super().__init__(); self.completions = _CompU(lambda xs: xs)
            self.chat = _Chat(self.completions)
    _UL.LEDGER_PATH.unlink(missing_ok=True)  # start from a clean ledger
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "x.csv"; out = Path(d) / "o.csv"
        _write(p, ["note"], [{"note": "hola"}])
        # gpt-4.1-nano: in $0.10/Mtok, out $0.40/Mtok -> 2*0.10 + 1*0.40 = $0.60
        s1 = T.translate_csv(str(p), ["note"], "en", "es", str(out), client=UsageClient(), confirm=True)
        assert abs(s1["actual_usd"] - 0.60) < 1e-6, s1
        assert s1["actual_usd_display"] == "$0.60"
        assert abs(s1["total_spend_usd"] - 0.60) < 1e-6, s1
        out2 = Path(d) / "o2.csv"
        _write(Path(d) / "y.csv", ["note"], [{"note": "adios"}])
        s2 = T.translate_csv(str(Path(d) / "y.csv"), ["note"], "en", "es", str(out2),
                             client=UsageClient(), confirm=True)
        assert abs(s2["total_spend_usd"] - 1.20) < 1e-6, s2  # accumulated across runs


def test_fallback_spend_when_no_usage_reported() -> None:
    # FakeClient returns no usage -> char-based fallback; assert the dollar math
    _UL.LEDGER_PATH.unlink(missing_ok=True)
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "x.csv"; out = Path(d) / "o.csv"
        _write(p, ["note"], [{"note": "hola mundo"}])  # 10 chars, 1 cell
        s = T.translate_csv(str(p), ["note"], "en", "es", str(out), client=FakeClient(), confirm=True)
        # gpt-4.1-nano: in $0.10/Mtok, out $0.40/Mtok; tok_in=10/4+1*12=14.5, tok_out=2.5
        expected = 14.5 / 1e6 * 0.10 + 2.5 / 1e6 * 0.40
        assert abs(s["actual_usd"] - round(expected, 6)) < 1e-9, (s, expected)
        assert s["actual_usd_display"] == "< $0.01"


def test_all_cached_run_records_no_spend() -> None:
    _UL.LEDGER_PATH.unlink(missing_ok=True)
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "x.csv"; o1 = Path(d) / "o1.csv"; o2 = Path(d) / "o2.csv"
        cache = Path(d) / "c.db"
        _write(p, ["note"], [{"note": "hola"}])
        s1 = T.translate_csv(str(p), ["note"], "en", "es", str(o1), client=FakeClient(),
                             cache_path=str(cache), confirm=True)
        total_after_first = s1["total_spend_usd"]
        # second run is fully cached -> no API call -> this run costs nothing
        s2 = T.translate_csv(str(p), ["note"], "en", "es", str(o2), client=FakeClient(),
                             cache_path=str(cache), confirm=True)
        assert s2["cells_cached"] == 1 and s2["actual_usd"] == 0.0, s2
        assert s2["total_spend_usd"] == total_after_first, s2  # total unchanged


def test_cache_file_is_chmod_600() -> None:
    import stat
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "x.csv"; out = Path(d) / "o.csv"; cache = Path(d) / "c.db"
        _write(p, ["note"], [{"note": "hola"}])
        T.translate_csv(str(p), ["note"], "en", "es", str(out), client=FakeClient(),
                        cache_path=str(cache), confirm=True)
        mode = stat.S_IMODE(cache.stat().st_mode)
        assert mode == 0o600, oct(mode)


def test_no_egress_gives_actionable_error() -> None:
    real_sleep = T.time.sleep; T.time.sleep = lambda s: None
    try:
        class APIConnectionError(Exception):
            pass
        class Boom(FakeClient):
            def __init__(self):
                super().__init__()
                class C:
                    def create(self2, **kw):
                        raise APIConnectionError("Connection error.")
                self.chat = _Chat(C())
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "x.csv"; out = Path(d) / "o.csv"
            _write(p, ["note"], [{"note": "hola"}])
            try:
                T.translate_csv(str(p), ["note"], "en", "es", str(out), client=Boom(), confirm=True)
            except RuntimeError as exc:
                m = str(exc)
                assert "api.openai.com" in m and "egress" in m.lower(), m
                assert "hola" not in m  # no source text leaked
                return
            raise AssertionError("expected an egress RuntimeError")
    finally:
        T.time.sleep = real_sleep


def test_is_connection_error_classifies() -> None:
    class APITimeoutError(Exception): pass
    assert T._is_connection_error(APITimeoutError("x"))
    assert T._is_connection_error(Exception("Connection error."))
    assert T._is_connection_error(Exception("Failed to establish a new connection"))
    assert not T._is_connection_error(Exception("invalid api key"))


def test_glossary_is_word_bounded() -> None:
    g = {"id": "ID", "case": "CASE", "drinking water": "DW"}
    # whole-word matches replace; substrings inside larger words do not
    assert T.apply_glossary("the id field", g) == "the ID field"
    assert T.apply_glossary("a good idea", g) == "a good idea"          # not 'a good IDea'
    assert T.apply_glossary("heavy caseload here", g) == "heavy caseload here"
    assert T.apply_glossary("this case matters", g) == "this CASE matters"
    assert T.apply_glossary("no drinking water today", g) == "no DW today"  # multi-word
    # case-insensitive, and a replacement with regex-special chars stays literal
    assert T.apply_glossary("ID and Id and id", {"id": "x$1\\1"}) == "x$1\\1 and x$1\\1 and x$1\\1"


def main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"ok  {t.__name__}")
    print(f"\n{len(tests)} translation tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

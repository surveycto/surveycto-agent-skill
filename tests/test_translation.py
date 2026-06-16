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


def test_output_column_inserted_next_to_source() -> None:
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "x.csv"; out = Path(d) / "o.csv"
        # two source columns among others; each _en goes right after its source
        _write(p, ["id", "note", "extra", "comment"],
               [{"id": "1", "note": "hola", "extra": "x", "comment": "adios"}])
        T.translate_csv(str(p), ["note", "comment"], "en", "es", str(out),
                        client=FakeClient(), confirm=True)
        with open(out, newline="", encoding="utf-8") as f:
            header = next(csv.reader(f))
        assert header == ["id", "note", "note_en", "extra", "comment", "comment_en"], header


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


def test_dup_header_and_ragged_rows_rejected() -> None:
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "dup.csv"
        p.write_text("note,note,id\na,b,1\n", encoding="utf-8")
        try:
            T.estimate_cost(str(p), ["note"], "en")
        except ValueError as exc:
            assert "duplicate column names" in str(exc)
        else:
            raise AssertionError("expected duplicate-header error")
        # a ragged row (more fields than headers) must fail loudly with the row
        # number, not silently drop the overflow
        p2 = Path(d) / "rag.csv"; out = Path(d) / "o.csv"
        p2.write_text("id,note\n1,hola\n2,adios,EXTRA\n", encoding="utf-8")
        try:
            T.translate_csv(str(p2), ["note"], "en", "es", str(out),
                            client=FakeClient(), confirm=True)
        except ValueError as exc:
            assert "row 3" in str(exc) and "more field" in str(exc), str(exc)
            assert not out.exists()  # nothing written from malformed input
        else:
            raise AssertionError("expected a ragged-row error")


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


def _real_api_connection_error():
    """A genuine openai.APIConnectionError, or None if openai/httpx aren't installed."""
    try:
        import httpx
        from openai import APIConnectionError
    except Exception:
        return None
    return APIConnectionError(request=httpx.Request("POST", "https://api.openai.com/v1/chat/completions"))


def test_egress_detection_is_sdk_typed() -> None:
    # deterministic: a non-OpenAI exception is never an egress error
    assert T._is_egress_error(ValueError("boom")) is False
    assert T._is_egress_error(RuntimeError("invalid api key")) is False
    exc = _real_api_connection_error()
    if exc is None:
        print("  (skipped openai-typed assertion: openai not installed)")
        return
    assert T._is_egress_error(exc) is True  # the real SDK connection type


def test_no_egress_gives_actionable_error() -> None:
    exc = _real_api_connection_error()
    if exc is None:
        print("  (skipped: openai not installed)")
        return
    real_sleep = T.time.sleep; T.time.sleep = lambda s: None
    try:
        class Boom(FakeClient):
            def __init__(self):
                super().__init__()
                class C:
                    def create(self2, **kw):
                        raise exc
                self.chat = _Chat(C())
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "x.csv"; out = Path(d) / "o.csv"
            _write(p, ["note"], [{"note": "hola"}])
            try:
                T.translate_csv(str(p), ["note"], "en", "es", str(out), client=Boom(), confirm=True)
            except RuntimeError as e:
                m = str(e)
                assert "api.openai.com" in m and "egress" in m.lower(), m
                assert "hola" not in m
                return
            raise AssertionError("expected an egress RuntimeError")
    finally:
        T.time.sleep = real_sleep


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


def test_resolve_model_fails_closed_and_prices_known_ids() -> None:
    # the menu resolves to model ids; rates come from pricing.json
    assert T.resolve_model("cheap")["id"] == "gpt-4.1-nano"
    assert T.resolve_model("better")["id"] == "gpt-4o-mini"
    # a model id behind a menu name resolves to that entry
    assert T.resolve_model("gpt-4.1-nano")["id"] == "gpt-4.1-nano"
    assert T.resolve_model("gpt-4o-mini")["id"] == "gpt-4o-mini"
    # pricing for those ids is available and distinct
    import pricing  # noqa: PLC0415
    data, _ = pricing.load()
    assert pricing.rate_for(data, "translation", "gpt-4.1-nano")["in_per_mtok"] == 0.10
    assert pricing.rate_for(data, "translation", "gpt-4o-mini")["in_per_mtok"] == 0.15
    # an unsupported id (e.g. the pricier gpt-4o) fails closed rather than being
    # priced at the cheaper menu rate
    try:
        T.resolve_model("gpt-4o")
    except ValueError as exc:
        assert "Unknown translation model" in str(exc)
    else:
        raise AssertionError("expected ValueError for an unsupported model id")


def test_spend_recorded_when_a_later_batch_fails() -> None:
    # batch 1 succeeds (incurs OpenAI cost), batch 2 fails -> the ledger must still
    # record batch 1's real spend, not stay silent
    real_sleep = T.time.sleep; T.time.sleep = lambda s: None
    _UL.LEDGER_PATH.unlink(missing_ok=True)
    try:
        class _Usage:
            prompt_tokens = 2_000_000; completion_tokens = 1_000_000
        class _RespU(_Resp):
            def __init__(self, content): super().__init__(content); self.usage = _Usage()
        class _C:
            def __init__(self): self.n = 0
            def create(self, model, temperature, response_format, messages):
                self.n += 1
                inputs = json.loads(messages[1]["content"])["inputs"]
                if self.n >= 2:
                    raise ValueError("simulated non-retryable API failure")
                return _RespU(json.dumps({"translations": [f"EN[{x}]" for x in inputs]}))
        class Client(FakeClient):
            def __init__(self): super().__init__(); self.chat = _Chat(_C())
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "x.csv"; out = Path(d) / "o.csv"
            _write(p, ["note"], [{"note": "hola"}, {"note": "adios"}])  # 2 cells
            raised = False
            try:
                T.translate_csv(str(p), ["note"], "en", "es", str(out), client=Client(),
                                confirm=True, batch_size=1)  # force two batches
            except RuntimeError:
                raised = True
            assert raised, "expected the second batch to fail"
            # batch 1 billed 3M tokens at gpt-4.1-nano (0.10/0.40) = $0.60, recorded
            assert abs(_UL.summary()["total_usd"] - 0.60) < 1e-6, _UL.summary()
    finally:
        T.time.sleep = real_sleep


def test_fallback_billing_counts_unique_inputs_not_cells() -> None:
    # when the response carries no usage (fallback path), duplicate source strings
    # are sent once, so the per-item overhead is charged per unique input, not per
    # output cell -- otherwise duplicates inflate the bill
    _UL.LEDGER_PATH.unlink(missing_ok=True)
    with tempfile.TemporaryDirectory() as d:
        src = Path(d) / "in.csv"
        _write(src, ["uuid", "comment"],
               [{"uuid": str(i), "comment": "hola mundo"} for i in range(5)])
        out = Path(d) / "out.csv"
        s = T.translate_csv(str(src), ["comment"], target_language="en",
                            source_language=None, output_path=str(out),
                            confirm=True, client=FakeClient())  # _Resp has no usage
        assert s["cells_translated"] == 5 and s["unique_sent"] == 1, s
        chars = len("hola mundo")
        tok_out = chars / 4
        unique_usd = (chars / 4 + 1 * 12) / 1e6 * 0.10 + tok_out / 1e6 * 0.40
        cell_usd = (chars / 4 + 5 * 12) / 1e6 * 0.10 + tok_out / 1e6 * 0.40
        # the ledger rounds to 6 decimals; the unique-based figure is what we expect
        assert s["actual_usd"] == round(unique_usd, 6), (s["actual_usd"], unique_usd)
        assert round(unique_usd, 6) < round(cell_usd, 6)  # and it's lower than per-cell


def test_output_csv_is_chmod_600() -> None:
    import stat
    with tempfile.TemporaryDirectory() as d:
        src = Path(d) / "in.csv"
        _write(src, ["uuid", "comment"], [{"uuid": "1", "comment": "hola"}])
        out = Path(d) / "out.csv"
        T.translate_csv(str(src), ["comment"], target_language="en",
                        source_language=None, output_path=str(out),
                        confirm=True, client=FakeClient())
        mode = stat.S_IMODE(out.stat().st_mode)
        assert mode == 0o600, oct(mode)


def test_non_string_translation_item_is_retryable() -> None:
    # a non-string item (here a number) is a malformed response: it must NOT be
    # coerced with str() and cached; it should retry, then succeed
    attempts = {"n": 0}
    def transform(xs):
        attempts["n"] += 1
        if attempts["n"] == 1:
            return [123]            # malformed: not a string
        return [f"EN[{x}]" for x in xs]
    with tempfile.TemporaryDirectory() as d:
        src = Path(d) / "in.csv"
        _write(src, ["note"], [{"note": "hola"}])
        out = Path(d) / "out.csv"
        s = T.translate_csv(str(src), ["note"], target_language="en",
                            source_language=None, output_path=str(out),
                            confirm=True, client=FakeClient(transform))
        assert attempts["n"] == 2, attempts          # retried once
        assert _read(out)[0]["note_en"] == "EN[hola]"
        assert s["cells_translated"] == 1


def test_parse_columns_strips_and_rejects_empty() -> None:
    assert T._parse_columns("note, comment ,  x") == ["note", "comment", "x"]
    for bad in ("note,", "a,,b", " "):
        try:
            T._parse_columns(bad)
        except ValueError as exc:
            assert "Empty column name" in str(exc)
        else:
            raise AssertionError(f"expected ValueError for {bad!r}")


def test_output_csv_write_is_atomic_on_failure() -> None:
    # exercise _write_csv_atomic itself: if the final os.replace fails, a
    # pre-existing output must be left untouched and no .tmp file may linger
    import os as _os
    with tempfile.TemporaryDirectory() as d:
        out = Path(d) / "out.csv"
        out.write_text("PREEXISTING CONTENT\n", encoding="utf-8")
        real_replace = T.os.replace
        def boom_replace(*a, **k):
            raise OSError("simulated replace failure")
        T.os.replace = boom_replace
        raised = False
        try:
            T._write_csv_atomic(str(out), ["note"], [{"note": "hola"}])
        except OSError:
            raised = True
        finally:
            T.os.replace = real_replace
        assert raised, "expected the atomic write to surface the replace failure"
        assert out.read_text(encoding="utf-8") == "PREEXISTING CONTENT\n"  # untouched
        leftovers = [p.name for p in Path(d).iterdir() if p.suffix == ".tmp"]
        assert leftovers == [], leftovers  # the temp file was cleaned up on failure


def test_spend_recorded_for_billed_but_malformed_response() -> None:
    # a response that carries usage (it was billed) but whose payload is the wrong
    # length must still have its usage recorded, even when the batch ultimately
    # fails with no cell translated
    _UL.LEDGER_PATH.unlink(missing_ok=True)
    class _Usage:
        prompt_tokens = 2_000_000; completion_tokens = 1_000_000
    class _RespU(_Resp):
        def __init__(self, content): super().__init__(content); self.usage = _Usage()
    class _C:
        def create(self, model, temperature, response_format, messages):
            return _RespU(json.dumps({"translations": ["only one"]}))  # wrong length
    class Client(FakeClient):
        def __init__(self): super().__init__(); self.chat = _Chat(_C())
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "x.csv"; out = Path(d) / "o.csv"
        _write(p, ["note"], [{"note": "hola"}, {"note": "adios"}])
        raised = False
        try:
            T.translate_csv(str(p), ["note"], "en", "es", str(out), client=Client(),
                            confirm=True, max_retries=0)
        except RuntimeError:
            raised = True
        assert raised, "expected a length-mismatch failure"
        # 3M tokens at gpt-4.1-nano (0.10 in / 0.40 out) = $0.60, billed despite the
        # malformed payload and the absent output
        assert abs(_UL.summary()["total_usd"] - 0.60) < 1e-6, _UL.summary()


def test_nested_cache_path_is_created() -> None:
    # a --cache path in a not-yet-existing subdirectory must be created, not error
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "x.csv"; out = Path(d) / "o.csv"
        cache = Path(d) / "new" / "dir" / "c.db"
        _write(p, ["note"], [{"note": "hola"}])
        s = T.translate_csv(str(p), ["note"], "en", "es", str(out), client=FakeClient(),
                            cache_path=str(cache), confirm=True)
        assert s["cells_translated"] == 1 and cache.is_file(), s


def test_size_budgeted_batches_never_oversized() -> None:
    # a few large cells must not pack into one oversized request (the cause of the
    # length-mismatch failure); each request stays within the char budget
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "x.csv"; out = Path(d) / "o.csv"
        big = "palabra " * 800  # ~6400 chars, under the 8000 budget but two won't fit
        _write(p, ["note"], [{"note": big + "uno"}, {"note": big + "dos"}, {"note": big + "tres"}])
        c = FakeClient(transform=lambda xs: [x.upper() for x in xs])
        T.translate_csv(str(p), ["note"], "en", "es", str(out), client=c, confirm=True)
        assert c.completions.calls, "expected at least one request"
        for batch in c.completions.calls:
            assert len(batch) == 1, [len(b) for b in c.completions.calls]
            assert sum(len(x) for x in batch) <= T._MAX_BATCH_CHARS or len(batch) == 1


def test_translate_document_roundtrip() -> None:
    # a long document translates by segmenting, then stitches back with paragraphs
    with tempfile.TemporaryDirectory() as d:
        src = Path(d) / "doc.txt"; out = Path(d) / "doc_es.txt"
        src.write_text(
            "First paragraph here.\n\nSecond paragraph, two sentences. Indeed two.\n",
            encoding="utf-8")
        c = FakeClient(transform=lambda xs: [f"ES[{x}]" for x in xs])
        s = T.translate_document(str(src), str(out), "es", source_language="en",
                                 client=c, confirm=True)
        text = out.read_text(encoding="utf-8")
        assert s["incomplete"] is False and s["segments"] >= 2, s
        assert "ES[" in text and "\n\n" in text  # translated, paragraphs preserved


def test_translate_document_requires_confirm() -> None:
    with tempfile.TemporaryDirectory() as d:
        src = Path(d) / "doc.txt"; src.write_text("Hola mundo.\n", encoding="utf-8")
        try:
            T.translate_document(str(src), str(Path(d) / "o.txt"), "en", client=FakeClient())
        except PermissionError:
            return
        raise AssertionError("expected PermissionError without confirm")


def test_translation_resumes_under_budget_without_rebilling() -> None:
    # a budget-limited pass translates part, reports incomplete; a second pass resumes
    # from cache and finishes. Each unique cell is translated exactly once.
    _UL.LEDGER_PATH.unlink(missing_ok=True)
    orig_mono = T.time.monotonic
    class Clock:
        def __init__(self, step): self.t = 0.0; self.step = step
        def __call__(self): v = self.t; self.t += self.step; return v
    calls = {"n": 0}
    def transform(xs):
        calls["n"] += len(xs)
        return [f"EN[{x}]" for x in xs]
    try:
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "x.csv"; out = Path(d) / "o.csv"; cache = Path(d) / "c.db"
            _write(p, ["note"], [{"note": f"hola {i}"} for i in range(6)])
            # pass 1: tiny budget + advancing clock -> stops after the first batch
            T.time.monotonic = Clock(10.0)
            s1 = T.translate_csv(str(p), ["note"], "en", "es", str(out), client=FakeClient(transform),
                                 cache_path=str(cache), confirm=True, batch_size=1, max_seconds=25)
            assert s1["incomplete"] is True and s1["cells_pending"] > 0, s1
            done1 = calls["n"]
            assert 0 < done1 < 6, done1
            # pass 2: no budget -> resume from cache, finish the rest
            T.time.monotonic = orig_mono
            s2 = T.translate_csv(str(p), ["note"], "en", "es", str(out), client=FakeClient(transform),
                                 cache_path=str(cache), confirm=True, batch_size=1, max_seconds=None)
            assert s2["incomplete"] is False, s2
            assert calls["n"] == 6, calls  # each unique translated once across passes
            r = _read(out)
            assert all(row["note_en"].startswith("EN[") for row in r), r
    finally:
        T.time.monotonic = orig_mono


def main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"ok  {t.__name__}")
    print(f"\n{len(tests)} translation tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Offline tests for user-data translation.

A fake translation client stands in for google-cloud-translate, so these tests
run with no Google packages and no network. They cover the skip-list, cost
math, language detection aggregation, the cost-confirmation gate, caching,
de-duplication, output-column naming, the no-overwrite guard, glossary
application, and retry/backoff.

Run: python3 tests/test_translation.py
"""

from __future__ import annotations

import csv
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "assets" / "google-cloud"))

import translation  # noqa: E402


class FakeTranslateClient:
    """Mimics google.cloud.translate_v2.Client for the methods we use."""

    def __init__(self, detected="es"):
        self.translate_calls = []
        self.detect_calls = []
        self._detected = detected

    def translate(self, values, target_language=None, source_language=None, format_=None):
        self.translate_calls.append(list(values))
        return [
            {
                "translatedText": f"[{target_language}]{v}",
                "detectedSourceLanguage": self._detected,
                "input": v,
            }
            for v in values
        ]

    def detect_language(self, values):
        self.detect_calls.append(list(values))
        return [
            {"language": self._detected, "confidence": 0.98, "input": v}
            for v in values
        ]


def _write_csv(path: Path, fieldnames, rows) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in rows:
            writer.writerow(r)


def _read_csv(path: Path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def test_should_skip() -> None:
    skip = ["", "  ", "999", "-99", "N/A", "n/a", ".", "5", "3.14", "-2.5", "x"]
    for v in skip:
        assert translation._should_skip(v), f"expected skip: {v!r}"
    keep = ["hello world", "está bien", "12 goats in the field", "no"]
    for v in keep:
        assert not translation._should_skip(v), f"expected keep: {v!r}"


def test_estimate_cost() -> None:
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "data.csv"
        _write_csv(
            p,
            ["id", "notes"],
            [
                {"id": "1", "notes": "hola mundo"},  # 10 chars
                {"id": "2", "notes": "999"},  # skipped
                {"id": "3", "notes": ""},  # skipped
                {"id": "4", "notes": "adios"},  # 5 chars
            ],
        )
        est = translation.estimate_cost(str(p), ["notes"], "en")
        assert est["cells_to_translate"] == 2, est
        assert est["billable_chars"] == 15, est
        assert est["estimated_usd"] == round(15 / 1_000_000 * 20, 4), est
        assert est["within_free_tier"] is True
        assert "PRIVACY" in est["pii_warning"]


def test_estimate_cost_missing_column() -> None:
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "data.csv"
        _write_csv(p, ["id"], [{"id": "1"}])
        try:
            translation.estimate_cost(str(p), ["nope"], "en")
        except ValueError:
            return
        raise AssertionError("expected ValueError for missing column")


def test_detect_languages() -> None:
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "data.csv"
        _write_csv(
            p,
            ["notes"],
            [{"notes": "hola"}, {"notes": "999"}, {"notes": "buenos dias"}],
        )
        client = FakeTranslateClient(detected="es")
        res = translation.detect_languages(str(p), "notes", client=client)
        assert res["sampled"] == 2  # "999" skipped
        assert res["dominant"] == "es"
        assert res["confidence"] == 1.0
        assert res["counts"] == {"es": 2}


def test_translate_requires_confirm() -> None:
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "data.csv"
        out = Path(d) / "out.csv"
        _write_csv(p, ["notes"], [{"notes": "hola"}])
        try:
            translation.translate_csv(
                str(p), ["notes"], "en", "es", str(out),
                client=FakeTranslateClient(),
            )
        except PermissionError:
            assert not out.exists()
            return
        raise AssertionError("expected PermissionError without confirm=True")


def test_translate_basic_and_skip_and_columns() -> None:
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "data.csv"
        out = Path(d) / "out.csv"
        _write_csv(
            p,
            ["id", "notes"],
            [
                {"id": "1", "notes": "hola"},
                {"id": "2", "notes": "999"},
                {"id": "3", "notes": "adios"},
            ],
        )
        client = FakeTranslateClient()
        stats = translation.translate_csv(
            str(p), ["notes"], "en", "es", str(out),
            client=client, confirm=True,
        )
        assert stats["cells_translated"] == 2, stats
        assert stats["cells_skipped"] == 1, stats
        assert stats["chars_sent"] == len("hola") + len("adios"), stats
        rows = _read_csv(out)
        assert rows[0]["notes_en"] == "[en]hola"
        assert rows[1]["notes_en"] == ""  # skipped cell stays empty
        assert rows[2]["notes_en"] == "[en]adios"
        # original preserved
        assert rows[0]["notes"] == "hola"


def test_translate_dedupes_identical_text() -> None:
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "data.csv"
        out = Path(d) / "out.csv"
        _write_csv(
            p,
            ["notes"],
            [{"notes": "hola"}, {"notes": "hola"}, {"notes": "hola"}],
        )
        client = FakeTranslateClient()
        stats = translation.translate_csv(
            str(p), ["notes"], "en", "es", str(out),
            client=client, confirm=True,
        )
        # 3 cells filled, but only 1 unique string sent and 1 API batch
        assert stats["cells_translated"] == 3, stats
        sent = [t for batch in client.translate_calls for t in batch]
        assert sent == ["hola"], sent


def test_translate_no_overwrite_existing_column() -> None:
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "data.csv"
        out = Path(d) / "out.csv"
        _write_csv(p, ["notes", "notes_en"], [{"notes": "hola", "notes_en": "x"}])
        try:
            translation.translate_csv(
                str(p), ["notes"], "en", "es", str(out),
                client=FakeTranslateClient(), confirm=True,
            )
        except ValueError as exc:
            assert "already exists" in str(exc)
            return
        raise AssertionError("expected ValueError for existing output column")


def test_cache_avoids_second_api_call() -> None:
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "data.csv"
        out1 = Path(d) / "out1.csv"
        out2 = Path(d) / "out2.csv"
        cache = Path(d) / "cache.db"
        _write_csv(p, ["notes"], [{"notes": "hola"}, {"notes": "adios"}])

        c1 = FakeTranslateClient()
        s1 = translation.translate_csv(
            str(p), ["notes"], "en", "es", str(out1),
            client=c1, cache_path=str(cache), confirm=True,
        )
        assert s1["cells_translated"] == 2 and s1["cells_cached"] == 0

        c2 = FakeTranslateClient()
        s2 = translation.translate_csv(
            str(p), ["notes"], "en", "es", str(out2),
            client=c2, cache_path=str(cache), confirm=True,
        )
        assert s2["cells_cached"] == 2, s2
        assert s2["cells_translated"] == 0, s2
        assert c2.translate_calls == [], "second run should make no API calls"
        # output identical
        assert _read_csv(out1) == _read_csv(out2)


def test_apply_glossary_after() -> None:
    glossary = {"household": "hogar", "head of household": "jefe del hogar"}
    # longest match wins: "head of household" -> "jefe del hogar"
    text = "The head of household and the household"
    out = translation.apply_glossary(text, glossary)
    assert "jefe del hogar" in out
    assert "hogar and the hogar" in out


def test_apply_glossary_empty_source_does_not_hang() -> None:
    # An empty source key would match at every position; it must be skipped.
    out = translation.apply_glossary("some text", {"": "X", "text": "TEXT"})
    assert out == "some TEXT"


def test_glossary_loaded_and_applied_in_translate() -> None:
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "data.csv"
        out = Path(d) / "out.csv"
        gloss = Path(d) / "gloss.csv"
        _write_csv(p, ["notes"], [{"notes": "household survey"}])
        _write_csv(
            gloss,
            ["source", "target_en", "target_fr"],
            [{"source": "household", "target_en": "HOUSEHOLD", "target_fr": "ménage"}],
        )
        client = FakeTranslateClient()
        translation.translate_csv(
            str(p), ["notes"], "en", "es", str(out),
            client=client, glossary_path=str(gloss), confirm=True,
        )
        rows = _read_csv(out)
        # fake returns "[en]household survey", glossary rewrites "household"
        assert "HOUSEHOLD" in rows[0]["notes_en"], rows


def test_backoff_retries_then_succeeds() -> None:
    sleeps = []
    real_sleep = translation.time.sleep
    translation.time.sleep = lambda s: sleeps.append(s)

    class FlakyClient(FakeTranslateClient):
        def __init__(self):
            super().__init__()
            self.attempts = 0

        def translate(self, values, **kwargs):
            self.attempts += 1
            if self.attempts < 3:
                raise RuntimeError("429 rate limited")
            return super().translate(values, **kwargs)

    try:
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "data.csv"
            out = Path(d) / "out.csv"
            _write_csv(p, ["notes"], [{"notes": "hola"}])
            client = FlakyClient()
            stats = translation.translate_csv(
                str(p), ["notes"], "en", "es", str(out),
                client=client, confirm=True, max_retries=5,
            )
            assert stats["cells_translated"] == 1
            assert client.attempts == 3
            assert len(sleeps) == 2  # two retries before the third success
    finally:
        translation.time.sleep = real_sleep


def test_backoff_gives_up_and_raises() -> None:
    real_sleep = translation.time.sleep
    translation.time.sleep = lambda s: None

    class AlwaysFails(FakeTranslateClient):
        def translate(self, values, **kwargs):
            raise RuntimeError(f"persistent failure with {list(values)}")

    try:
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "data.csv"
            out = Path(d) / "out.csv"
            _write_csv(p, ["notes"], [{"notes": "hola"}])
            try:
                translation.translate_csv(
                    str(p), ["notes"], "en", "es", str(out),
                    client=AlwaysFails(), confirm=True, max_retries=2,
                )
            except RuntimeError as exc:
                # sanitized after retries exhausted: no original message/content
                assert "persistent failure" not in str(exc)
                assert "translation API call failed" in str(exc)
                return
            raise AssertionError("expected RuntimeError after retries exhausted")
    finally:
        translation.time.sleep = real_sleep


def test_should_skip_keeps_word_like_numbers() -> None:
    # "nan"/"inf" are real words in some languages and must not be skipped just
    # because float() would parse them; scientific/underscored forms are not
    # survey codes either.
    for v in ["nan", "inf", "-inf", "Infinity", "1e5", "1_000"]:
        assert not translation._should_skip(v), f"should not skip {v!r}"
    for v in ["999", "-99", "3.14", "-2.5", ".5", "42"]:
        assert translation._should_skip(v), f"should skip {v!r}"


def test_duplicate_header_rejected() -> None:
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "data.csv"
        # write a raw CSV with a duplicated header
        p.write_text("notes,notes,id\nhello,world,1\n", encoding="utf-8")
        try:
            translation.estimate_cost(str(p), ["notes"], "en")
        except ValueError as exc:
            assert "duplicate column names" in str(exc)
            return
        raise AssertionError("expected ValueError for duplicate header")


def test_ragged_row_does_not_crash() -> None:
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "data.csv"
        out = Path(d) / "out.csv"
        # second row has an extra field beyond the 2-column header
        p.write_text("id,notes\n1,hola\n2,adios,EXTRA\n", encoding="utf-8")
        stats = translation.translate_csv(
            str(p), ["notes"], "en", "es", str(out),
            client=FakeTranslateClient(), confirm=True,
        )
        assert stats["cells_translated"] == 2, stats
        rows = _read_csv(out)
        assert rows[0]["notes_en"] == "[en]hola"
        assert rows[1]["notes_en"] == "[en]adios"


def test_duplicate_columns_arg_deduped() -> None:
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "data.csv"
        out = Path(d) / "out.csv"
        _write_csv(p, ["notes"], [{"notes": "hola"}])
        stats = translation.translate_csv(
            str(p), ["notes", "notes"], "en", "es", str(out),
            client=FakeTranslateClient(), confirm=True,
        )
        # counted once, single output column
        assert stats["cells_translated"] == 1, stats
        with open(out, encoding="utf-8") as f:
            header = f.readline().strip()
        assert header.count("notes_en") == 1, header


def test_cache_is_glossary_independent() -> None:
    """Cache stores the raw translation; changing the glossary changes output
    without forcing a re-translation."""
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "data.csv"
        out1 = Path(d) / "out1.csv"
        out2 = Path(d) / "out2.csv"
        cache = Path(d) / "translation-cache.db"
        gloss = Path(d) / "gloss.csv"
        _write_csv(p, ["notes"], [{"notes": "household"}])
        _write_csv(gloss, ["source", "target"], [{"source": "household", "target": "HH"}])

        # run 1: glossary present, populates cache with RAW "[en]household"
        c1 = FakeTranslateClient()
        translation.translate_csv(
            str(p), ["notes"], "en", "es", str(out1),
            client=c1, cache_path=str(cache), glossary_path=str(gloss), confirm=True,
        )
        assert "HH" in _read_csv(out1)[0]["notes_en"]

        # run 2: same cache, NO glossary. Served from cache (no API call), and
        # the raw translation comes through without the glossary substitution.
        c2 = FakeTranslateClient()
        s2 = translation.translate_csv(
            str(p), ["notes"], "en", "es", str(out2),
            client=c2, cache_path=str(cache), confirm=True,
        )
        assert s2["cells_cached"] == 1 and s2["cells_translated"] == 0, s2
        assert c2.translate_calls == []
        assert _read_csv(out2)[0]["notes_en"] == "[en]household"


def test_non_retryable_error_fails_fast() -> None:
    sleeps = []
    real_sleep = translation.time.sleep
    translation.time.sleep = lambda s: sleeps.append(s)

    class BadArg(FakeTranslateClient):
        def __init__(self):
            super().__init__()
            self.attempts = 0

        def translate(self, values, **kwargs):
            self.attempts += 1
            raise ValueError("invalid argument")  # programming/permanent error

    try:
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "data.csv"
            out = Path(d) / "out.csv"
            _write_csv(p, ["notes"], [{"notes": "hola"}])
            client = BadArg()
            try:
                translation.translate_csv(
                    str(p), ["notes"], "en", "es", str(out),
                    client=client, confirm=True, max_retries=5,
                )
            except RuntimeError as exc:
                assert client.attempts == 1, "must not retry a non-retryable error"
                assert sleeps == [], "must not sleep before failing fast"
                # error is sanitized: type name only, no original message
                assert "ValueError" in str(exc)
                assert "invalid argument" not in str(exc)
                return
            raise AssertionError("expected sanitized RuntimeError to propagate")
    finally:
        translation.time.sleep = real_sleep


def test_translate_api_error_does_not_leak_source_text() -> None:
    """A translate() error that echoes the input must not reach the caller."""
    class LeakyClient(FakeTranslateClient):
        def translate(self, values, **kwargs):
            raise ValueError(
                ("Expected iterations to have same length", list(values), [])
            )

    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "data.csv"
        out = Path(d) / "out.csv"
        secret = "RESPONDENT_PII_jane_at_42_elm_street"
        _write_csv(p, ["notes"], [{"notes": secret}])
        try:
            translation.translate_csv(
                str(p), ["notes"], "en", "es", str(out),
                client=LeakyClient(), confirm=True, max_retries=0,
            )
        except RuntimeError as exc:
            assert secret not in str(exc), f"source text leaked: {exc}"
            assert "translation API call failed" in str(exc)
            return
        raise AssertionError("expected sanitized RuntimeError")


def test_detect_languages_api_error_is_sanitized() -> None:
    class LeakyClient(FakeTranslateClient):
        def detect_language(self, values):
            raise RuntimeError(f"bad input: {list(values)}")

    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "data.csv"
        secret = "SECRET_open_response_text"
        _write_csv(p, ["notes"], [{"notes": secret}])
        try:
            translation.detect_languages(str(p), "notes", client=LeakyClient())
        except RuntimeError as exc:
            assert secret not in str(exc), f"sample text leaked: {exc}"
            assert "language detection API call failed" in str(exc)
            return
        raise AssertionError("expected sanitized RuntimeError")


def test_detect_languages_surfaces_pii_warning() -> None:
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "data.csv"
        _write_csv(p, ["notes"], [{"notes": "hola mundo"}])
        res = translation.detect_languages(str(p), "notes", client=FakeTranslateClient())
        assert "PRIVACY" in res["pii_warning"]


def test_cache_connect_closes_on_unusable_path() -> None:
    # A non-sqlite file as the cache must raise, not leak the connection.
    with tempfile.TemporaryDirectory() as d:
        bogus = Path(d) / "not-a-db.db"
        bogus.write_text("this is plainly not an sqlite database file" * 50)
        try:
            translation._cache_connect(str(bogus))
        except Exception:
            return  # raised as expected; close-on-error path exercised
        raise AssertionError("expected an error opening a non-sqlite cache file")


def main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"ok  {t.__name__}")
    print(f"\n{len(tests)} translation tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

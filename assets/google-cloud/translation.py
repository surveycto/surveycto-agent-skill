"""Translate columns of user data in a CSV via Google Cloud Translation.

This supports the user-data translation workflow described in
``references/user-data-translation.md``. Unlike form-label translation (which
the agent does directly in conversation; see ``references/translation.md``),
user data is high-volume and sensitive: respondent free-text, enumerator
notes, audio transcriptions. It must not pass through the agent's context or
logs, so this module sends it straight to Google Cloud Translation from a
script and writes the result to a file. The agent orchestrates; it never sees
the cell contents.

Authentication is handled by :mod:`google_cloud_auth`, which points the Google
client library at the user's service-account file without ever opening it. Call
``google_cloud_auth.configure_google_auth()`` once before constructing a client
(generated scripts should do this at startup).

Design notes that matter for safe, cheap operation:

* **Cost gate.** :func:`translate_csv` refuses to run unless ``confirm=True``.
  Call :func:`estimate_cost` first, show the user the cost and the PII warning,
  and only pass ``confirm=True`` after explicit confirmation. No translation
  runs silently.
* **Caching.** With a ``cache_path``, translations are memoized in SQLite keyed
  on ``(source_lang, target_lang, sha256(source_text))``. Re-translating a
  re-downloaded dataset only pays for cells whose source text changed. The
  cache contains source text and translations, so treat it as sensitive (it is
  covered by the skill ``.gitignore`` template).
* **Skip-list.** Empty cells, pure numbers, single letters, and common survey
  codes (``N/A``, ``999``, ``-99`` ...) are never sent to the API.
* **Preserve originals.** Output adds a ``<column>_<target_language>`` column
  next to each source column; it never overwrites the original.

Dependency injection: every function that talks to Google accepts an optional
``client``. When omitted, a real ``google.cloud.translate_v2.Client`` is
constructed lazily (so importing this module needs no Google packages, and the
logic is unit-testable offline with a fake client). A ``client`` is any object
exposing ``translate(values, target_language=, source_language=, format_=)``
and ``detect_language(values)`` with the google-cloud-translate v2 return
shapes.

Standard library only at import time (``csv``, ``sqlite3``, ``hashlib``);
``google-cloud-translate`` is required only to actually reach the API.

CLI::

    python translation.py estimate data.csv --columns notes,comments --target en
    python translation.py translate data.csv --columns notes --target en \\
        --output data_en.csv --cache translation-cache.db --confirm
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sqlite3
import sys
import time
from pathlib import Path

# Rate for standard NMT translation, USD per million characters.
_USD_PER_MILLION_CHARS = 20.00
# Google Cloud Translation permanent free tier, characters per month.
_FREE_TIER_CHARS = 500_000

# Cells whose normalized value is in this set are never sent to the API. These
# are survey non-responses and codes, not natural language to translate.
_SKIP_VALUES = frozenset(
    {
        "",
        "n/a",
        "na",
        "none",
        ".",
        "-",
        "--",
        "999",
        "9999",
        "-77",
        "-88",
        "-99",
        "77",
        "88",
        "99",
    }
)

# A plain integer or decimal, optionally signed: a code or measure, not text.
# Deliberately stricter than float(), which would also match "nan", "inf",
# "1e5", and "1_000" (the first two can be real words; the latter are not
# survey codes).
_NUMERIC_RE = re.compile(r"^[+-]?(\d+(\.\d*)?|\.\d+)$")

_PII_WARNING = (
    "PRIVACY: the selected cell text will be sent to Google Cloud Translation "
    "(a third-party service) for processing. Do not translate columns that "
    "contain direct identifiers (names, phone numbers, GPS, national IDs) "
    "unless the user has confirmed that is acceptable for their data-governance "
    "rules."
)

# Maximum cells per translate() request. Google's v2 API accepts up to 128
# segments per call; 100 leaves headroom.
_DEFAULT_BATCH_SIZE = 100


def _should_skip(value: str) -> bool:
    """Return True if a cell value should not be sent to the API.

    Skips empty/whitespace cells, common survey non-response codes, pure
    numbers (including decimals and signed), and single characters.
    """
    if value is None:
        return True
    stripped = value.strip()
    if stripped.lower() in _SKIP_VALUES:
        return True
    if len(stripped) <= 1:
        return True
    if _NUMERIC_RE.match(stripped):
        return True
    return False


def _read_csv(csv_path: str) -> tuple[list[str], list[dict]]:
    """Read a CSV into (fieldnames, list-of-row-dicts). UTF-8, BOM-tolerant.

    Rejects CSVs with duplicate column names (DictReader would silently collapse
    them and drop data). Overflow values from ragged rows that have more fields
    than the header are dropped rather than crashing the later write.
    """
    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames or [])
        dupes = [c for c in set(fieldnames) if fieldnames.count(c) > 1]
        if dupes:
            raise ValueError(
                f"CSV has duplicate column names: {sorted(dupes)}. Rename the "
                f"duplicated columns and try again."
            )
        rows = []
        for r in reader:
            row = dict(r)
            # Values from rows with more fields than the header land under the
            # None key; drop them so DictWriter does not choke on the write.
            row.pop(None, None)
            rows.append(row)
    return fieldnames, rows


def _require_columns(fieldnames: list[str], columns: list[str]) -> None:
    missing = [c for c in columns if c not in fieldnames]
    if missing:
        raise ValueError(
            f"Column(s) not found in CSV: {missing}. Available columns: "
            f"{fieldnames}"
        )


def estimate_cost(
    csv_path: str,
    columns: list[str],
    target_language: str,
) -> dict:
    """Estimate the cost of translating ``columns`` in ``csv_path``.

    Counts characters only in cells that would actually be sent to the API
    (i.e. excluding cells caught by the skip-list). Google bills per character
    of source text.

    :param csv_path: Path to the source CSV file.
    :param columns: Column names to translate.
    :param target_language: ISO 639-1 target language code (recorded in the
        result for context; cost does not depend on it).
    :returns: Dict with ``total_chars`` (all non-skipped source chars),
        ``billable_chars`` (same; named for clarity at the call site),
        ``estimated_usd``, ``within_free_tier`` (naive: this run alone, not
        accounting for the user's monthly usage to date), ``cells_to_translate``,
        ``target_language``, and ``pii_warning``.
    """
    fieldnames, rows = _read_csv(csv_path)
    _require_columns(fieldnames, columns)

    billable_chars = 0
    cells_to_translate = 0
    for row in rows:
        for col in columns:
            value = row.get(col, "")
            if _should_skip(value):
                continue
            billable_chars += len(value.strip())
            cells_to_translate += 1

    estimated_usd = billable_chars / 1_000_000 * _USD_PER_MILLION_CHARS
    return {
        "total_chars": billable_chars,
        "billable_chars": billable_chars,
        "estimated_usd": round(estimated_usd, 4),
        "within_free_tier": billable_chars <= _FREE_TIER_CHARS,
        "cells_to_translate": cells_to_translate,
        "target_language": target_language,
        "pii_warning": _PII_WARNING,
    }


def _get_client(client):
    """Return the injected client, or construct a real v2 client lazily."""
    if client is not None:
        return client
    # Imported here so the module imports without google-cloud-translate and
    # stays unit-testable offline.
    from google.cloud import translate_v2  # noqa: PLC0415

    return translate_v2.Client()


def detect_languages(
    csv_path: str,
    column: str,
    sample_size: int = 100,
    client=None,
) -> dict:
    """Detect source languages in a column by sampling non-skipped cells.

    :param csv_path: Path to the source CSV file.
    :param column: Column name to sample.
    :param sample_size: Maximum number of non-skipped cells to sample (taken
        from the top of the file in order; deterministic).
    :param client: Optional translation client (see module docstring).
    :returns: Dict with ``counts`` (ISO 639-1 code -> count in the sample),
        ``sampled`` (number of cells sampled), ``dominant`` (most common code
        or ``None``), ``confidence`` (fraction of the sample that is the
        dominant language, 0.0-1.0), and ``pii_warning``. Note: detection is a
        metered Google Cloud Translation call ($20/M chars, same free tier as
        translation) and sends the sampled cell text to Google, so it carries
        the same privacy consideration as translation. It is bounded to
        ``sample_size`` cells, which for the default keeps it well inside the
        free tier.
    """
    fieldnames, rows = _read_csv(csv_path)
    _require_columns(fieldnames, [column])

    sample: list[str] = []
    for row in rows:
        value = row.get(column, "")
        if _should_skip(value):
            continue
        sample.append(value.strip())
        if len(sample) >= sample_size:
            break

    if not sample:
        return {
            "counts": {},
            "sampled": 0,
            "dominant": None,
            "confidence": 0.0,
            "pii_warning": _PII_WARNING,
        }

    client = _get_client(client)
    try:
        results = client.detect_language(sample)
    except Exception as exc:
        # Sanitize: a detection API error could echo the sampled source text.
        # Surface only the error type, never its message (which the agent logs).
        raise RuntimeError(
            f"language detection API call failed ({type(exc).__name__})"
        ) from None
    if isinstance(results, dict):
        results = [results]

    counts: dict[str, int] = {}
    for item in results:
        lang = item.get("language", "und")
        counts[lang] = counts.get(lang, 0) + 1

    dominant = max(counts, key=counts.get)
    confidence = counts[dominant] / len(sample)
    return {
        "counts": counts,
        "sampled": len(sample),
        "dominant": dominant,
        "confidence": round(confidence, 3),
        "pii_warning": _PII_WARNING,
    }


def _cache_connect(cache_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(cache_path)
    try:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS translations ("
            "source_lang TEXT NOT NULL, "
            "target_lang TEXT NOT NULL, "
            "source_hash TEXT NOT NULL, "
            "translated TEXT NOT NULL, "
            "PRIMARY KEY (source_lang, target_lang, source_hash))"
        )
    except Exception:
        # An unusable cache path (corrupt/non-db/read-only) must not leak the
        # just-opened connection.
        conn.close()
        raise
    return conn


def _text_hash(text: str) -> str:
    """Hash of the source text. The source/target language dimensions of the
    cache key are carried in the table's primary-key columns, not the hash."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _load_glossary(glossary_path: str, target_language: str) -> dict:
    """Load a glossary CSV into a ``{source_term: target_term}`` dict.

    Accepts either a ``target`` column, or a per-language ``target_<lang>``
    column (e.g. ``target_es``). The ``source`` column is required. Rows with an
    empty target for the requested language are ignored.
    """
    with open(glossary_path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        cols = list(reader.fieldnames or [])
        if "source" not in cols:
            raise ValueError(
                f"Glossary {glossary_path} must have a 'source' column. "
                f"Found: {cols}"
            )
        target_col = None
        for candidate in (f"target_{target_language}", "target"):
            if candidate in cols:
                target_col = candidate
                break
        if target_col is None:
            raise ValueError(
                f"Glossary {glossary_path} has no 'target_{target_language}' or "
                f"'target' column. Found: {cols}"
            )
        glossary: dict[str, str] = {}
        for row in reader:
            src = (row.get("source") or "").strip()
            tgt = (row.get(target_col) or "").strip()
            if src and tgt:
                glossary[src] = tgt
    return glossary


def apply_glossary(text: str, glossary: dict) -> str:
    """Apply a glossary to translated text by whole-phrase replacement.

    Replaces glossary source terms with their target renderings,
    case-insensitively, longest terms first so multi-word terms win over their
    sub-phrases. Applied *after* the API call by default (see the primer for the
    before/after trade-off): the model produces fluent output and the glossary
    then enforces the user's preferred terminology on top.

    This is a deliberately simple substring replacement. It does not handle
    inflection or agreement; advanced users who need that should curate their
    glossary accordingly or apply terms before translation.
    """
    if not glossary:
        return text
    result = text
    for source in sorted(glossary, key=len, reverse=True):
        if not source:
            # An empty source term would match at every position (infinite loop).
            continue
        target = glossary[source]
        # Case-insensitive replace while preserving the rest of the string.
        idx = 0
        lowered = result.lower()
        needle = source.lower()
        out = []
        while True:
            found = lowered.find(needle, idx)
            if found == -1:
                out.append(result[idx:])
                break
            out.append(result[idx:found])
            out.append(target)
            idx = found + len(needle)
        result = "".join(out)
    return result


def translate_csv(
    csv_path: str,
    columns: list[str],
    target_language: str,
    source_language: str | None,
    output_path: str,
    glossary_path: str | None = None,
    cache_path: str | None = None,
    client=None,
    confirm: bool = False,
    batch_size: int = _DEFAULT_BATCH_SIZE,
    max_retries: int = 5,
) -> dict:
    """Translate ``columns`` in a CSV and write the result to ``output_path``.

    Adds a ``<column>_<target_language>`` column next to each source column;
    never overwrites an existing column. Skips cells caught by the skip-list.
    Uses the SQLite cache at ``cache_path`` (if given) to avoid re-translating
    unchanged cells across runs.

    :param csv_path: Path to the source CSV file.
    :param columns: Column names to translate.
    :param target_language: ISO 639-1 target language code.
    :param source_language: ISO 639-1 source language code, or ``None`` to let
        the API auto-detect per cell.
    :param output_path: Where to write the translated CSV.
    :param glossary_path: Optional glossary CSV (``source`` + ``target`` or
        ``target_<lang>`` columns), applied after translation as a re-runnable
        overlay (the cache stores the raw translation, so changing the glossary
        does not force a re-translation).
    :param cache_path: Optional SQLite cache file path.
    :param client: Optional translation client (see module docstring).
    :param confirm: Must be ``True`` to run. The cost gate: call
        :func:`estimate_cost` and confirm with the user first.
    :param batch_size: Cells per API request.
    :param max_retries: Retries per batch on API error, with exponential
        backoff.
    :returns: Dict with ``cells_translated`` (newly translated via API),
        ``cells_cached`` (served from cache), ``cells_skipped``,
        ``chars_sent`` (billable characters actually sent this run), and
        ``output_path``.
    :raises PermissionError: If ``confirm`` is not ``True``.
    """
    if not confirm:
        raise PermissionError(
            "translate_csv requires confirm=True. Run estimate_cost(), show the "
            "user the cost and PII warning, and only proceed after explicit "
            "confirmation."
        )

    fieldnames, rows = _read_csv(csv_path)
    # De-duplicate the requested columns while preserving order, so a repeated
    # column name does not produce a duplicated output column or double-count.
    columns = list(dict.fromkeys(columns))
    _require_columns(fieldnames, columns)

    out_fieldnames = list(fieldnames)
    out_columns: dict[str, str] = {}
    for col in columns:
        out_col = f"{col}_{target_language}"
        if out_col in out_fieldnames:
            raise ValueError(
                f"Output column '{out_col}' already exists in the CSV. Refusing "
                f"to overwrite. Rename or remove it, or choose a different "
                f"target-language suffix."
            )
        out_columns[col] = out_col
        out_fieldnames.append(out_col)

    # The glossary is a re-runnable post-process overlay: the cache stores the
    # raw API translation, and the glossary is applied on every resolution (both
    # cache hits and fresh translations). That way changing the glossary changes
    # the output without forcing a re-translation, and the cache is glossary
    # independent.
    glossary = (
        _load_glossary(glossary_path, target_language) if glossary_path else None
    )

    def _finish(text: str) -> str:
        return apply_glossary(text, glossary) if glossary else text

    cache_conn = _cache_connect(cache_path) if cache_path else None
    cache_lang_key = source_language or "auto"

    stats = {
        "cells_translated": 0,
        "cells_cached": 0,
        "cells_skipped": 0,
        "chars_sent": 0,
    }

    try:
        # Pass 1: classify every target cell; collect the unique texts that must
        # hit the API (after cache lookup). Identical texts are de-duplicated so
        # we pay once per distinct string per run.
        # to_translate maps source text -> list of (row_index, out_col)
        to_translate: dict[str, list[tuple[int, str]]] = {}
        resolved: dict[tuple[int, str], str] = {}

        for i, row in enumerate(rows):
            for col in columns:
                out_col = out_columns[col]
                value = row.get(col, "")
                if _should_skip(value):
                    stats["cells_skipped"] += 1
                    resolved[(i, out_col)] = ""
                    continue
                text = value.strip()
                cached = None
                if cache_conn is not None:
                    cur = cache_conn.execute(
                        "SELECT translated FROM translations WHERE source_lang=? "
                        "AND target_lang=? AND source_hash=?",
                        (cache_lang_key, target_language, _text_hash(text)),
                    )
                    hit = cur.fetchone()
                    if hit is not None:
                        cached = hit[0]
                if cached is not None:
                    stats["cells_cached"] += 1
                    resolved[(i, out_col)] = _finish(cached)
                else:
                    to_translate.setdefault(text, []).append((i, out_col))

        # Pass 2: translate the unique pending texts in batches with backoff.
        client_obj = None
        pending_texts = list(to_translate)

        for start in range(0, len(pending_texts), batch_size):
            chunk = pending_texts[start : start + batch_size]
            if client_obj is None:
                client_obj = _get_client(client)
            results = _translate_with_backoff(
                client_obj, chunk, target_language, source_language, max_retries
            )
            for text, item in zip(chunk, results):
                raw = item.get("translatedText", "")
                stats["cells_translated"] += len(to_translate[text])
                stats["chars_sent"] += len(text)
                finished = _finish(raw)
                for (i, out_col) in to_translate[text]:
                    resolved[(i, out_col)] = finished
                if cache_conn is not None:
                    cache_conn.execute(
                        "INSERT OR REPLACE INTO translations VALUES (?,?,?,?)",
                        (cache_lang_key, target_language, _text_hash(text), raw),
                    )
            if cache_conn is not None:
                cache_conn.commit()

        # Write output.
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=out_fieldnames)
            writer.writeheader()
            for i, row in enumerate(rows):
                out_row = dict(row)
                for col in columns:
                    out_col = out_columns[col]
                    out_row[out_col] = resolved.get((i, out_col), "")
                writer.writerow(out_row)
    finally:
        if cache_conn is not None:
            cache_conn.close()

    stats["output_path"] = output_path
    return stats


# Exception types that indicate a bug in the call, not a transient API problem.
# These are never retried; retrying them just wastes the backoff budget before
# failing anyway.
_NON_RETRYABLE_TYPES = (
    TypeError,
    ValueError,
    AttributeError,
    KeyError,
    NotImplementedError,
)

# Names of Google API exception classes that represent permanent failures
# (bad credentials, bad request, missing resource). Matched by class name so
# this module needs no google import. Anything not named here and not a builtin
# programming error is treated as transient and retried.
_NON_RETRYABLE_NAMES = frozenset(
    {
        "Unauthenticated",
        "PermissionDenied",
        "InvalidArgument",
        "NotFound",
        "Forbidden",
        "BadRequest",
        "Unauthorized",
    }
)


def _is_retryable(exc: Exception) -> bool:
    if isinstance(exc, _NON_RETRYABLE_TYPES):
        return False
    if type(exc).__name__ in _NON_RETRYABLE_NAMES:
        return False
    return True


def _translate_with_backoff(
    client,
    chunk: list[str],
    target_language: str,
    source_language: str | None,
    max_retries: int,
) -> list[dict]:
    """Call ``client.translate`` on a chunk, retrying with exponential backoff.

    Only transient errors are retried; programming errors and permanent API
    errors (auth, invalid argument, not found) fail fast. Returns the list of
    per-value result dicts. Re-raises the last error if all retries are
    exhausted.
    """
    attempt = 0
    while True:
        try:
            results = client.translate(
                chunk,
                target_language=target_language,
                source_language=source_language,
                format_="text",
            )
            if isinstance(results, dict):
                results = [results]
            return results
        except Exception as exc:
            attempt += 1
            if attempt > max_retries or not _is_retryable(exc):
                # Sanitize: a translation API/library error can echo the source
                # text it was given (e.g. the v2 client's "Expected iterations
                # to have same length" ValueError includes the input values).
                # Surface only the error type so user data never reaches logs.
                raise RuntimeError(
                    f"translation API call failed ({type(exc).__name__})"
                ) from None
            time.sleep(min(2 ** attempt, 60))


def _main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Translate CSV columns.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    pe = sub.add_parser("estimate", help="estimate cost only")
    pe.add_argument("csv_path")
    pe.add_argument("--columns", required=True, help="comma-separated")
    pe.add_argument("--target", required=True)

    pd_ = sub.add_parser("detect", help="detect source languages in a column")
    pd_.add_argument("csv_path")
    pd_.add_argument("--column", required=True)
    pd_.add_argument("--sample-size", type=int, default=100)

    pt = sub.add_parser("translate", help="translate columns")
    pt.add_argument("csv_path")
    pt.add_argument("--columns", required=True, help="comma-separated")
    pt.add_argument("--target", required=True)
    pt.add_argument("--source", default=None)
    pt.add_argument("--output", required=True)
    pt.add_argument("--glossary", default=None)
    pt.add_argument("--cache", default=None)
    pt.add_argument(
        "--confirm",
        action="store_true",
        help="required; confirms the user accepted the estimated cost",
    )

    args = parser.parse_args(argv)

    if args.cmd in ("estimate", "translate", "detect"):
        # configure auth only when we will actually reach Google
        if args.cmd in ("translate", "detect"):
            import google_cloud_auth

            google_cloud_auth.configure_google_auth()

    if args.cmd == "estimate":
        result = estimate_cost(
            args.csv_path, args.columns.split(","), args.target
        )
        print(json.dumps(result, indent=2))
        return 0

    if args.cmd == "detect":
        result = detect_languages(
            args.csv_path, args.column, sample_size=args.sample_size
        )
        print(json.dumps(result, indent=2))
        return 0

    if args.cmd == "translate":
        if not args.confirm:
            print(
                "Refusing to translate without --confirm. Run 'estimate' "
                "first and confirm the cost with the user.",
                file=sys.stderr,
            )
            return 1
        result = translate_csv(
            args.csv_path,
            args.columns.split(","),
            args.target,
            args.source,
            args.output,
            glossary_path=args.glossary,
            cache_path=args.cache,
            confirm=True,
        )
        print(json.dumps(result, indent=2))
        return 0

    return 2


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1:]))

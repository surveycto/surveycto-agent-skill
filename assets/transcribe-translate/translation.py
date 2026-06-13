"""Translate columns of user data in a CSV via OpenAI chat models.

Supports the user-data translation workflow in
``references/user-data-translation.md``. Unlike form-label translation (which
the agent does directly in conversation; see ``references/translation.md``),
user data is high-volume and sensitive, so it is sent to OpenAI by a script and
written to a file; the agent orchestrates and reports without ingesting the cells.

Model selection (the user picks; the cheapest is the default):
    "cheap"  -> gpt-4.1-nano  (DEFAULT)
    "better" -> gpt-4o-mini
An explicit model id (e.g. "gpt-4o") is also accepted.

Design:
* Cost gate: ``translate_csv`` refuses to run unless ``confirm=True``; call
  ``estimate_cost`` and confirm with the user first.
* Structured output: each batch is sent with a strict instruction to return a
  JSON array of EXACTLY N translations for N inputs; the length is validated and
  a mismatch is retried (up to the retry budget), then fails loud, so the model
  can never silently drop or merge cells.
* De-duplication: identical source strings are translated once per run.
* Caching: with a ``cache_path``, raw translations are memoized (keyed on source
  language, target language, model, and a hash of the source text) so re-runs are
  cheap. The cache holds source text (sensitive); it is gitignored by the skill.
* Skip-list: empty cells, pure numbers, single letters, and common survey codes
  (N/A, 999, -99, ...) are never sent.
* Preserve originals: a ``<column>_<target_language>`` column is added next to
  each source column; existing columns are never overwritten.
* Sanitized errors: an API/library error never echoes the source text.

Auth via ``openai_auth.configure_openai()`` (never prints the key). Standard
library only at import time; ``openai`` is imported lazily.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import sqlite3
import sys
import time
from pathlib import Path

import usage_ledger

# Translation model menu. Token rates are list prices (verify on the pricing
# page); they drive only the cost estimate.
_MODELS = {
    "cheap":  {"id": "gpt-4.1-nano", "in_per_mtok": 0.10, "out_per_mtok": 0.40},
    "better": {"id": "gpt-4o-mini",  "in_per_mtok": 0.15, "out_per_mtok": 0.60},
}
DEFAULT_MODEL = "cheap"

_NUMERIC_RE = re.compile(r"^[+-]?(\d+(\.\d*)?|\.\d+)$")
_SKIP_VALUES = frozenset({"", "n/a", "na", "none", ".", "-", "--",
                          "999", "9999", "-77", "-88", "-99", "77", "88", "99"})

_PII_WARNING = (
    "PRIVACY: the selected cell text will be sent to OpenAI (a third-party "
    "service) for translation. Do not translate columns with direct identifiers "
    "(names, phone numbers, GPS, national IDs) unless the user has confirmed that "
    "is acceptable for their data-governance rules."
)

_DEFAULT_BATCH_SIZE = 40
_MAX_RETRIES = 2

_NON_RETRYABLE_TYPES = (TypeError, ValueError, KeyError, NotImplementedError)
_NON_RETRYABLE_NAMES = frozenset({
    "AuthenticationError", "PermissionDeniedError", "BadRequestError",
    "NotFoundError", "UnprocessableEntityError",
})


class _LengthMismatch(RuntimeError):
    """The model returned the wrong number of translations for a batch.

    Subclasses RuntimeError (not ValueError) so it is retryable: a malformed
    count is usually a transient formatting slip the model corrects on retry.
    After the retry budget is exhausted it fails loud, never silently truncating.
    """


def resolve_model(model: str | None) -> dict:
    """Resolve a menu name or explicit model id to a spec dict."""
    if not model:
        return dict(_MODELS[DEFAULT_MODEL])
    if model in _MODELS:
        return dict(_MODELS[model])
    return {"id": model, "in_per_mtok": 0.15, "out_per_mtok": 0.60}


def _should_skip(value: str) -> bool:
    if value is None:
        return True
    s = value.strip()
    if s.lower() in _SKIP_VALUES:
        return True
    if len(s) <= 1:
        return True
    if _NUMERIC_RE.match(s):
        return True
    return False


def _read_csv(csv_path: str) -> tuple[list[str], list[dict]]:
    """Read a CSV into (fieldnames, rows). UTF-8/BOM tolerant; rejects duplicate
    headers; drops the None overflow key from ragged rows."""
    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames or [])
        dupes = [c for c in set(fieldnames) if fieldnames.count(c) > 1]
        if dupes:
            raise ValueError(f"CSV has duplicate column names: {sorted(dupes)}.")
        rows = []
        for r in reader:
            row = dict(r)
            row.pop(None, None)
            rows.append(row)
    return fieldnames, rows


def _require_columns(fieldnames: list[str], columns: list[str]) -> None:
    missing = [c for c in columns if c not in fieldnames]
    if missing:
        raise ValueError(f"Column(s) not found: {missing}. Available: {fieldnames}")


def _usd_display(usd: float) -> str:
    """Human-readable cost so a sub-cent estimate never reads as free $0.00."""
    if usd <= 0:
        return "$0.00"
    if usd < 0.01:
        return "< $0.01"
    return f"${usd:.2f}"


def estimate_cost(csv_path: str, columns: list[str], target_language: str,
                  model: str | None = None) -> dict:
    """Estimate translation cost (token-based, approximate).

    OpenAI bills per token, so this is a rough estimate from character counts
    (~4 chars/token, input and output). De-duplication is not modeled, so the
    real cost is usually lower. Returns ``billable_chars``, ``cells_to_translate``,
    ``estimated_usd``, ``model``, ``target_language``, ``pii_warning``.
    """
    spec = resolve_model(model)
    fieldnames, rows = _read_csv(csv_path)
    columns = list(dict.fromkeys(columns))  # dedup, like translate_csv, for a consistent estimate
    _require_columns(fieldnames, columns)
    billable = 0
    cells = 0
    skipped = 0
    for row in rows:
        for col in columns:
            v = row.get(col, "")
            if _should_skip(v):
                skipped += 1
                continue
            billable += len(v.strip())
            cells += 1
    tok_in = billable / 4 + cells * 12   # rough: text + per-item overhead
    tok_out = billable / 4               # translation ~ similar length
    usd = tok_in / 1e6 * spec["in_per_mtok"] + tok_out / 1e6 * spec["out_per_mtok"]
    return {
        "billable_chars": billable,
        "cells_to_translate": cells,
        "cells_skipped": skipped,  # empty/numeric/survey-code cells not sent
        "estimated_usd": round(usd, 4),
        "estimated_usd_display": _usd_display(usd),
        "model": spec["id"],
        "target_language": target_language,
        "pii_warning": _PII_WARNING,
        "note": "Token-based estimate; de-duplication usually makes the real cost lower.",
    }


def _load_glossary(glossary_path: str, target_language: str) -> dict:
    with open(glossary_path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        cols = list(reader.fieldnames or [])
        if "source" not in cols:
            raise ValueError(f"Glossary {glossary_path} needs a 'source' column. Found {cols}")
        target_col = next((c for c in (f"target_{target_language}", "target") if c in cols), None)
        if target_col is None:
            raise ValueError(f"Glossary {glossary_path} needs 'target_{target_language}' or 'target'. Found {cols}")
        g: dict[str, str] = {}
        for row in reader:
            s = (row.get("source") or "").strip()
            t = (row.get(target_col) or "").strip()
            if s and t:
                g[s] = t
    return g


def apply_glossary(text: str, glossary: dict) -> str:
    """Case-insensitive whole-phrase replacement, longest terms first."""
    if not glossary:
        return text
    result = text
    for source in sorted(glossary, key=len, reverse=True):
        if not source:
            continue
        target = glossary[source]
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


def _text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _restrict_cache_permissions(cache_path: str) -> None:
    """Make the cache readable only by its owner. It holds source text (often
    sensitive), so it gets the same 0600 treatment as the API-key config."""
    try:
        os.chmod(cache_path, 0o600)
    except OSError:
        pass


def _cache_connect(cache_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(cache_path, timeout=30)
    _restrict_cache_permissions(cache_path)
    try:
        # tolerate concurrent skill runs sharing one cache instead of erroring out
        conn.execute("PRAGMA busy_timeout=30000")
        conn.execute(
            "CREATE TABLE IF NOT EXISTS translations ("
            "source_lang TEXT NOT NULL, target_lang TEXT NOT NULL, model TEXT NOT NULL, "
            "source_hash TEXT NOT NULL, translated TEXT NOT NULL, "
            "PRIMARY KEY (source_lang, target_lang, model, source_hash))")
    except Exception:
        conn.close()
        raise
    return conn


def _get_client(client):
    if client is not None:
        return client
    from openai import OpenAI  # noqa: PLC0415
    return OpenAI()


def _is_retryable(exc: Exception) -> bool:
    if isinstance(exc, _NON_RETRYABLE_TYPES):
        return False
    if type(exc).__name__ in _NON_RETRYABLE_NAMES:
        return False
    return True


def _usage_tokens(resp) -> tuple[int, int] | None:
    """(prompt_tokens, completion_tokens) from a chat response, or None if absent.

    Real OpenAI responses carry ``usage``; this lets the caller bill on actual
    tokens. A response without it (e.g. a test stub) yields None so the caller
    falls back to a character-based estimate.
    """
    usage = getattr(resp, "usage", None)
    if usage is None:
        return None
    pt = getattr(usage, "prompt_tokens", None)
    ct = getattr(usage, "completion_tokens", None)
    if pt is None or ct is None:
        return None
    return int(pt), int(ct)


def _translate_batch(client, texts: list[str], target_language: str,
                     source_language: str | None, model_id: str,
                     max_retries: int) -> tuple[list[str], tuple[int, int] | None]:
    """Translate a batch via OpenAI chat with strict length-validated JSON output.

    Returns ``(translations, usage)`` where ``usage`` is ``(prompt_tokens,
    completion_tokens)`` or None when the response carries no usage. Raises a
    sanitized RuntimeError on persistent failure or if the model will not return
    exactly len(texts) translations (never silently truncates).
    """
    src = f" The source language is {source_language}." if source_language else ""
    system = (
        "You are a professional survey-data translator. Translate each input "
        f"string into {target_language}." + src +
        " Translate faithfully and idiomatically. Preserve numbers, codes, and "
        "untranslatable tokens unchanged. If a string is already in the target "
        "language, return it unchanged. Return ONLY a JSON object of the form "
        '{\"translations\": [...]} whose array has EXACTLY the same number of '
        "items as the input, in the same order, one translation per input. No "
        "commentary."
    )
    user = json.dumps({"inputs": texts}, ensure_ascii=False)
    attempt = 0
    while True:
        try:
            resp = client.chat.completions.create(
                model=model_id,
                temperature=0,
                response_format={"type": "json_object"},
                messages=[{"role": "system", "content": system},
                          {"role": "user", "content": user}],
            )
            content = resp.choices[0].message.content
            data = json.loads(content)
            out = data.get("translations")
            if not isinstance(out, list) or len(out) != len(texts):
                raise _LengthMismatch(
                    f"model returned {0 if not isinstance(out, list) else len(out)} "
                    f"translations for {len(texts)} inputs")
            return [str(x) for x in out], _usage_tokens(resp)
        except Exception as exc:
            attempt += 1
            if attempt > max_retries or not _is_retryable(exc):
                raise RuntimeError(
                    f"translation API call failed ({type(exc).__name__})") from None
            time.sleep(min(2 ** attempt, 30))


def translate_csv(csv_path: str, columns: list[str], target_language: str,
                  source_language: str | None, output_path: str,
                  model: str | None = None, glossary_path: str | None = None,
                  cache_path: str | None = None, client=None, confirm: bool = False,
                  batch_size: int = _DEFAULT_BATCH_SIZE,
                  max_retries: int = _MAX_RETRIES) -> dict:
    """Translate ``columns`` in a CSV and write the result to ``output_path``.

    Adds a ``<column>_<target_language>`` column next to each source column;
    never overwrites. Skips skip-list cells. Caches raw translations (keyed on
    source/target language + model + text hash); the glossary is applied as a
    re-runnable overlay on every resolution.

    :raises PermissionError: If ``confirm`` is not ``True``.
    """
    if not confirm:
        raise PermissionError(
            "translate_csv requires confirm=True. Run estimate_cost(), show the "
            "user the cost and PII warning, and only proceed after confirmation.")
    spec = resolve_model(model)
    model_id = spec["id"]
    fieldnames, rows = _read_csv(csv_path)
    columns = list(dict.fromkeys(columns))
    _require_columns(fieldnames, columns)

    out_fieldnames = list(fieldnames)
    out_columns: dict[str, str] = {}
    for col in columns:
        oc = f"{col}_{target_language}"
        if oc in out_fieldnames:
            raise ValueError(f"Output column '{oc}' already exists. Refusing to overwrite.")
        out_columns[col] = oc
        out_fieldnames.append(oc)

    glossary = _load_glossary(glossary_path, target_language) if glossary_path else None

    def finish(text: str) -> str:
        return apply_glossary(text, glossary) if glossary else text

    cache_conn = _cache_connect(cache_path) if cache_path else None
    lang_key = source_language or "auto"
    stats = {"cells_translated": 0, "cells_cached": 0, "cells_skipped": 0, "chars_sent": 0}
    try:
        to_translate: dict[str, list[tuple[int, str]]] = {}
        resolved: dict[tuple[int, str], str] = {}
        for i, row in enumerate(rows):
            for col in columns:
                oc = out_columns[col]
                v = row.get(col, "")
                if _should_skip(v):
                    stats["cells_skipped"] += 1
                    resolved[(i, oc)] = ""
                    continue
                text = v.strip()
                cached = None
                if cache_conn is not None:
                    cur = cache_conn.execute(
                        "SELECT translated FROM translations WHERE source_lang=? AND "
                        "target_lang=? AND model=? AND source_hash=?",
                        (lang_key, target_language, model_id, _text_hash(text)))
                    hit = cur.fetchone()
                    if hit is not None:
                        cached = hit[0]
                if cached is not None:
                    stats["cells_cached"] += 1
                    resolved[(i, oc)] = finish(cached)
                else:
                    to_translate.setdefault(text, []).append((i, oc))

        client_obj = None
        pending = list(to_translate)
        tok_in_total = 0
        tok_out_total = 0
        have_usage = True
        for start in range(0, len(pending), batch_size):
            chunk = pending[start:start + batch_size]
            if client_obj is None:
                client_obj = _get_client(client)
            results, usage = _translate_batch(client_obj, chunk, target_language,
                                              source_language, model_id, max_retries)
            if usage is None:
                have_usage = False
            else:
                tok_in_total += usage[0]
                tok_out_total += usage[1]
            for text, raw in zip(chunk, results):
                stats["cells_translated"] += len(to_translate[text])
                stats["chars_sent"] += len(text)
                done = finish(raw)
                for (i, oc) in to_translate[text]:
                    resolved[(i, oc)] = done
                if cache_conn is not None:
                    cache_conn.execute(
                        "INSERT OR REPLACE INTO translations VALUES (?,?,?,?,?)",
                        (lang_key, target_language, model_id, _text_hash(text), raw))
            if cache_conn is not None:
                cache_conn.commit()

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=out_fieldnames)
            w.writeheader()
            for i, row in enumerate(rows):
                out_row = dict(row)
                for col in columns:
                    oc = out_columns[col]
                    out_row[oc] = resolved.get((i, oc), "")
                w.writerow(out_row)
    finally:
        if cache_conn is not None:
            cache_conn.close()
    stats["model"] = model_id
    stats["output_path"] = output_path

    # actual spend: bill on real tokens when the responses reported usage,
    # otherwise fall back to a character-based approximation of what was sent
    # (uses the same per-token formula; the dollar figure is approximate)
    if stats["cells_translated"] > 0:
        if have_usage and (tok_in_total or tok_out_total):
            actual_usd = (tok_in_total / 1e6 * spec["in_per_mtok"]
                          + tok_out_total / 1e6 * spec["out_per_mtok"])
            units = f"{tok_in_total + tok_out_total:,} tokens"
        else:
            chars = stats["chars_sent"]
            tok_in = chars / 4 + stats["cells_translated"] * 12
            actual_usd = (tok_in / 1e6 * spec["in_per_mtok"]
                          + chars / 4 / 1e6 * spec["out_per_mtok"])
            units = f"~{chars:,} chars (estimated)"
        spend = usage_ledger.record("translate", model_id, units, actual_usd)
    else:
        spend = usage_ledger.summary()
        spend = {"run_usd": 0.0, "run_usd_display": "$0.00",
                 "total_usd": spend["total_usd"],
                 "total_usd_display": spend["total_usd_display"]}
    stats["actual_usd"] = spend["run_usd"]
    stats["actual_usd_display"] = spend["run_usd_display"]
    stats["total_spend_usd"] = spend["total_usd"]
    stats["total_spend_usd_display"] = spend["total_usd_display"]
    return stats


def _main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(
        description="Translate CSV columns via OpenAI. Run 'estimate' first to "
                    "see cost and the privacy warning, then 'translate --confirm'.",
        epilog="Examples:\n"
               "  python translation.py estimate data.csv --columns notes,comment --target en\n"
               "  python translation.py translate data.csv --columns notes,comment \\\n"
               "      --target en --output data_en.csv --cache translation-cache.db --confirm\n"
               "Omit --source to auto-detect each cell's language (handles mixed columns).",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    pe = sub.add_parser("estimate", help="show cell count, approx cost, and the PII warning")
    pe.add_argument("csv_path", help="path to the exported CSV")
    pe.add_argument("--columns", required=True, help="comma-separated column names to translate")
    pe.add_argument("--target", required=True, help="target language ISO code (en, es, fr, ...)")
    pe.add_argument("--model", default=None, help="cheap (default, gpt-4.1-nano) | better | model id")
    pt = sub.add_parser("translate", help="translate the columns and write a new CSV")
    pt.add_argument("csv_path", help="path to the exported CSV")
    pt.add_argument("--columns", required=True, help="comma-separated column names to translate")
    pt.add_argument("--target", required=True, help="target language ISO code (en, es, fr, ...)")
    pt.add_argument("--source", default=None, help="source language ISO code; omit to auto-detect")
    pt.add_argument("--output", required=True, help="path for the result CSV (adds <col>_<target> columns)")
    pt.add_argument("--model", default=None, help="cheap (default, gpt-4.1-nano) | better | model id")
    pt.add_argument("--glossary", default=None, help="optional CSV with source,target term overrides")
    pt.add_argument("--cache", default=None, help="optional SQLite cache path so re-runs are cheap")
    pt.add_argument("--confirm", action="store_true", help="required: confirms you accepted the cost/PII")
    args = p.parse_args(argv)
    if args.cmd == "estimate":
        print(json.dumps(estimate_cost(args.csv_path, args.columns.split(","),
                                       args.target, args.model), indent=2))
        return 0
    if args.cmd == "translate":
        if not args.confirm:
            print("Refusing to translate without --confirm. Run 'estimate' first.",
                  file=sys.stderr)
            return 1
        import openai_auth
        openai_auth.configure_openai()
        print(json.dumps(translate_csv(
            args.csv_path, args.columns.split(","), args.target, args.source,
            args.output, model=args.model, glossary_path=args.glossary,
            cache_path=args.cache, confirm=True), indent=2))
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1:]))

"""Translate columns of user data in a CSV via OpenAI chat models.

Supports the user-data translation workflow in
``references/user-data-translation.md``. Unlike form-label translation (done by
the agent directly in conversation; see ``references/translation.md``), user data
is high-volume and sensitive, so it is sent to OpenAI by a script and written to a
file; the agent orchestrates and reports without ingesting the cells.

Model selection (the user picks; the cheapest is the default):
    "cheap"  -> gpt-4.1-nano  (DEFAULT)
    "better" -> gpt-4o-mini
The model id behind a menu name is also accepted; any other id is rejected, since
the cost estimate needs a known rate.

Design:
* Cost gate: ``translate_csv`` refuses to run unless ``confirm=True``; call
  ``estimate_cost`` and confirm first.
* Structured output: each batch is instructed to return a JSON array of EXACTLY N
  translations for N inputs; the length is validated and a mismatch is retried (up
  to the retry budget) then fails loud, so the model can never silently drop or
  merge cells.
* De-duplication: identical source strings are translated once per run.
* Caching: with a ``cache_path``, raw translations are memoized, keyed by (source
  language, target language, model, hash of the source text). The source text
  itself is not stored, only its hash. Translations can still be sensitive, so the
  cache is gitignored and chmod 600.
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
import signal
import sqlite3
import sys
import tempfile
import time
from pathlib import Path

import pricing
import usage_ledger

# Translation model menu. Holds the model id only; token rates live in
# pricing.json (loaded via pricing.py) so they can be refreshed without a code
# change.
_MODELS = {
    "cheap":  {"id": "gpt-4.1-nano"},
    "better": {"id": "gpt-4o-mini"},
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
# Cap each request by total source characters too, not just item count: a few large
# cells (e.g. a transcript pasted as one cell) must not pack into one oversized
# request the model cannot return a correct-length array for. ~8000 chars is a safe
# input size well under the model limits.
_MAX_BATCH_CHARS = 8000
# Default per-segment size when translating a long document (see translate_document).
_DEFAULT_SEGMENT_CHARS = 1200
_MAX_RETRIES = 2
# Default per-call work budget for resumable translation; see _DEFAULT_MAX_SECONDS
# in transcription.py. Callers set it ~5s below their environment's command timeout.
_DEFAULT_MAX_SECONDS = 40.0

# Local, non-mounted cache location (mounted/network folders cannot host SQLite).
LOCAL_CACHE_DIR = Path.home() / ".surveycto-skill" / "cache"

_NON_RETRYABLE_TYPES = (TypeError, ValueError, KeyError, NotImplementedError)
_NON_RETRYABLE_NAMES = frozenset({
    "AuthenticationError", "PermissionDeniedError", "BadRequestError",
    "NotFoundError", "UnprocessableEntityError",
})


class _LengthMismatch(RuntimeError):
    """The model returned the wrong number of translations for a batch.

    Subclasses RuntimeError (not ValueError) so it is retryable: a wrong count is
    usually a transient formatting slip the model corrects on retry. After the
    retry budget is exhausted it fails loud, never silently truncating.
    """


def resolve_model(model: str | None) -> dict:
    """Resolve a menu name or supported model id to a spec dict.

    Fails closed on unknown model ids: pricing drives the cost estimate,
    confirmation, and spend ledger, so a rate is never guessed. A menu name or a
    matching model id resolves to that entry; anything else raises with an
    actionable message.
    """
    if not model:
        return dict(_MODELS[DEFAULT_MODEL])
    if model in _MODELS:
        return dict(_MODELS[model])
    for spec in _MODELS.values():
        if spec["id"] == model:
            return dict(spec)
    known = ", ".join(sorted({s["id"] for s in _MODELS.values()}))
    raise ValueError(
        f"Unknown translation model '{model}'. Use a menu name (cheap, better) or a "
        f"supported model id ({known}). To use another model, add it to the model "
        "menu and its rate to pricing.json so the cost estimate stays accurate.")


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
    headers; rejects ragged rows (more fields than headers) instead of dropping the
    overflow, so malformed input is never silently truncated."""
    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames or [])
        dupes = [c for c in set(fieldnames) if fieldnames.count(c) > 1]
        if dupes:
            raise ValueError(f"CSV has duplicate column names: {sorted(dupes)}.")
        rows = []
        for n, r in enumerate(reader, start=2):  # row 1 is the header
            if None in r:
                extra = len(r[None]) if isinstance(r.get(None), list) else 1
                raise ValueError(
                    f"CSV row {n} has {extra} more field(s) than the {len(fieldnames)} "
                    "header columns. Fix the row (likely an unquoted comma) and retry.")
            rows.append(dict(r))
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

    Rough estimate from character counts (~4 chars/token, input and output).
    De-duplication is not modeled, so the real cost is usually lower; actual
    post-run spend is computed from the response's real token counts. Returns
    ``billable_chars``, ``cells_to_translate``, ``estimated_usd``, ``model``,
    ``target_language``, ``rates_as_of``/``rates_source``/``pricing_source_url``,
    ``pii_warning``.
    """
    spec = resolve_model(model)
    price_data, prov = pricing.load()
    rate = pricing.rate_for(price_data, "translation", spec["id"])
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
    usd = tok_in / 1e6 * rate["in_per_mtok"] + tok_out / 1e6 * rate["out_per_mtok"]
    return {
        "billable_chars": billable,
        "cells_to_translate": cells,
        "cells_skipped": skipped,  # empty/numeric/survey-code cells not sent
        "estimated_usd": round(usd, 4),
        "estimated_usd_display": _usd_display(usd),
        "model": spec["id"],
        "target_language": target_language,
        "rates_as_of": prov["last_verified"],
        "rates_source": prov["source"],
        "pricing_source_url": prov["source_url"],
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
    """Case-insensitive, whole-word replacement, longest terms first.

    Matches are bounded by Unicode word characters, so a term never replaces a
    substring inside a larger word (``id`` will not touch ``idea`` or ``paid``;
    ``case`` will not touch ``caseload``). Multi-word terms match as written.
    Matching is whole-word, not morphological, so it does not handle inflected
    forms; curate the glossary accordingly.
    """
    if not glossary:
        return text
    result = text
    for source in sorted(glossary, key=len, reverse=True):
        if not source:
            continue
        target = glossary[source]
        # (?<!\w)/(?!\w) keep the term from matching inside a larger word; \w is
        # Unicode-aware for str patterns. The lambda keeps re.sub from treating
        # backslashes or group refs in the replacement text specially.
        pattern = re.compile(r"(?<!\w)" + re.escape(source) + r"(?!\w)", re.IGNORECASE)
        result = pattern.sub(lambda _m, t=target: t, result)
    return result


def _text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _restrict_cache_permissions(cache_path: str) -> None:
    """Make the cache readable only by its owner. It holds translated text (keyed
    by a hash of the source, not the source itself), which can still be sensitive,
    so it gets the same 0600 treatment as the API-key config."""
    try:
        os.chmod(cache_path, 0o600)
    except OSError:
        pass


def _write_csv_atomic(output_path: str, fieldnames: list[str], rows: list[dict]) -> None:
    """Write the result CSV atomically and owner-only. Translated responses can
    contain PII, so the deliverable is created 0600 (mkstemp default) and only
    os.replace()d into place after a complete write: an existing output is never
    left truncated by a failed write, and the file is never briefly world-readable.
    The temp file is in the output's own directory so the replace is atomic."""
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(out.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames)
            w.writeheader()
            for r in rows:
                w.writerow(r)
        os.replace(tmp, output_path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _fallback_cache_path(original: str) -> str:
    """A deterministic local cache path for when ``original`` is on a filesystem that
    cannot host SQLite. Same input maps to the same fallback, so resume still works."""
    digest = hashlib.sha256(str(Path(original).resolve()).encode("utf-8")).hexdigest()[:16]
    return str(LOCAL_CACHE_DIR / f"{digest}.db")


def _cache_connect_at(cache_path: str) -> sqlite3.Connection:
    # create parent dirs like the output path does, so a nested --cache path
    # (e.g. runs/cache.db) does not fail with "unable to open database file"
    Path(cache_path).parent.mkdir(parents=True, exist_ok=True)
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


def _cache_connect(cache_path: str) -> sqlite3.Connection:
    """Open the cache, falling back to a local path if the requested one is on a
    filesystem SQLite cannot use (mounted/network folders raise 'disk I/O error' or
    locking errors). The fallback is deterministic so resume across calls still works."""
    try:
        return _cache_connect_at(cache_path)
    except (sqlite3.OperationalError, OSError):
        fallback = _fallback_cache_path(cache_path)
        if Path(fallback) == Path(cache_path):
            raise
        print(f"[cache] '{cache_path}' cannot host a SQLite cache (likely a mounted "
              f"or network folder); using a local cache at {fallback}.", file=sys.stderr)
        return _cache_connect_at(fallback)


_NO_OPENAI_MSG = (
    "the 'openai' package is not installed in this environment. Run "
    "'python3 setup_env.py' first (it creates ~/.surveycto-skill/venv with the "
    "pinned openai and socksio) and invoke this script with the venv interpreter "
    "it prints."
)


def _get_client(client):
    if client is not None:
        return client
    try:
        from openai import OpenAI  # noqa: PLC0415
    except ModuleNotFoundError as exc:
        raise RuntimeError(_NO_OPENAI_MSG) from exc
    return OpenAI()


def _is_retryable(exc: Exception) -> bool:
    if isinstance(exc, _NON_RETRYABLE_TYPES):
        return False
    if type(exc).__name__ in _NON_RETRYABLE_NAMES:
        return False
    return True


_NO_EGRESS_MSG = (
    "Could not reach OpenAI (api.openai.com). This environment likely has network "
    "egress disabled. On claude.ai: Settings > Capabilities > enable network "
    "egress; on Team/Enterprise the default blocks third-party APIs, so ask an "
    "admin to allowlist api.openai.com (Organization settings > Capabilities). "
    "See references/openai-credentials.md. No key or data was exposed."
)


def _is_egress_error(exc: Exception) -> bool:
    """True iff ``exc`` is the OpenAI SDK's connection-failure type.

    Keyed to the SDK's exception contract, not message text.
    ``openai.APIConnectionError`` is raised for any failure to reach the API (DNS,
    refused, unreachable); ``APITimeoutError`` subclasses it, so one isinstance
    check covers a blocked egress without misclassifying API/auth errors that did
    reach the server.
    """
    try:
        from openai import APIConnectionError  # noqa: PLC0415
    except Exception:  # noqa: BLE001 - openai not importable -> cannot be this type
        return False
    return isinstance(exc, APIConnectionError)


def _usage_tokens(resp) -> tuple[int, int] | None:
    """(prompt_tokens, completion_tokens) from a chat response, or None if absent.

    Real OpenAI responses carry ``usage``, letting the caller bill on actual
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
                     max_retries: int, on_usage) -> list[str]:
    """Translate a batch via OpenAI chat with strict length-validated JSON output.

    Returns the list of translations. ``on_usage`` is called with each response's
    usage (``(prompt_tokens, completion_tokens)`` or None) before its content is
    validated, so a billed-but-malformed response still has its usage recorded (the
    user is charged per response, not per valid one). Raises a sanitized
    RuntimeError on persistent failure or a wrong-length result; never truncates.
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
            # record billing before validating: OpenAI charges for the call whether
            # or not the payload below turns out valid
            on_usage(_usage_tokens(resp))
            content = resp.choices[0].message.content
            data = json.loads(content)
            out = data.get("translations")
            if not isinstance(out, list) or len(out) != len(texts):
                raise _LengthMismatch(
                    f"model returned {0 if not isinstance(out, list) else len(out)} "
                    f"translations for {len(texts)} inputs")
            if not all(isinstance(x, str) for x in out):
                # a non-string item (null, number, object) is a malformed response;
                # coercing it with str() would cache and write "None"/"{...}" as a
                # translation. Treat it as retryable so the model can correct it.
                raise _LengthMismatch(
                    "model returned a non-string translation item")
            return out
        except Exception as exc:
            attempt += 1
            if attempt > max_retries or not _is_retryable(exc):
                if _is_egress_error(exc):
                    raise RuntimeError(_NO_EGRESS_MSG) from None
                raise RuntimeError(
                    f"translation API call failed ({type(exc).__name__})") from None
            time.sleep(min(2 ** attempt, 30))


def _next_batch(items: list[str], start: int, max_items: int,
                max_chars: int) -> tuple[list[str], int]:
    """Take the next batch from ``items[start:]`` bounded by both ``max_items`` and
    ``max_chars`` of total source text. Always returns at least one item (even if it
    alone exceeds ``max_chars``) so progress is always made. Returns (batch, next)."""
    batch: list[str] = []
    chars = 0
    i = start
    while i < len(items):
        it = items[i]
        if batch and (len(batch) >= max_items or chars + len(it) > max_chars):
            break
        batch.append(it)
        chars += len(it)
        i += 1
    return batch, i


def translate_csv(csv_path: str, columns: list[str], target_language: str,
                  source_language: str | None, output_path: str,
                  model: str | None = None, glossary_path: str | None = None,
                  cache_path: str | None = None, client=None, confirm: bool = False,
                  batch_size: int = _DEFAULT_BATCH_SIZE,
                  max_retries: int = _MAX_RETRIES,
                  max_seconds: float | None = None) -> dict:
    """Translate ``columns`` in a CSV and write the result to ``output_path``.

    Adds a ``<column>_<target_language>`` column next to each source column; never
    overwrites. Skips skip-list cells. Caches raw translations (keyed on
    source/target language + model + text hash); the glossary is applied as a
    re-runnable overlay on every resolution. Batches are bounded by both item count
    and total characters so a few large cells never form one oversized request.

    With a ``max_seconds`` budget, a call translates until the budget is reached then
    stops cleanly, leaving the rest for a resume pass: untranslated cells stay empty,
    ``incomplete`` is True, and re-running the SAME command fills them from cache
    without re-billing finished ones.

    :raises PermissionError: If ``confirm`` is not ``True``.
    """
    if not confirm:
        raise PermissionError(
            "translate_csv requires confirm=True. Run estimate_cost(), show the "
            "user the cost and PII warning, and only proceed after confirmation.")
    spec = resolve_model(model)
    model_id = spec["id"]
    price_data, prov = pricing.load()
    rate = pricing.rate_for(price_data, "translation", model_id)
    fieldnames, rows = _read_csv(csv_path)
    columns = list(dict.fromkeys(columns))
    _require_columns(fieldnames, columns)

    out_columns: dict[str, str] = {}
    for col in columns:
        oc = f"{col}_{target_language}"
        if oc in fieldnames:
            raise ValueError(f"Output column '{oc}' already exists. Refusing to overwrite.")
        out_columns[col] = oc
    # place each translated column immediately after its source column
    out_fieldnames: list[str] = []
    for name in fieldnames:
        out_fieldnames.append(name)
        if name in out_columns:
            out_fieldnames.append(out_columns[name])

    glossary = _load_glossary(glossary_path, target_language) if glossary_path else None

    def finish(text: str) -> str:
        return apply_glossary(text, glossary) if glossary else text

    cache_conn = _cache_connect(cache_path) if cache_path else None
    lang_key = source_language or "auto"
    deadline = (time.monotonic() + max_seconds) if max_seconds else None
    stats = {"cells_translated": 0, "cells_cached": 0, "cells_skipped": 0,
             "chars_sent": 0, "unique_sent": 0, "cells_pending": 0,
             "incomplete": False}
    tok_in_total = 0
    tok_out_total = 0
    have_usage = True
    _spend_done = False

    def _record_usage(usage: tuple[int, int] | None) -> None:
        """Fold one response's token usage into the run totals, for every billed
        response (even ones that later fail validation), so spend is never lost."""
        nonlocal tok_in_total, tok_out_total, have_usage
        if usage is None:
            have_usage = False
        else:
            tok_in_total += usage[0]
            tok_out_total += usage[1]

    def _finalize_spend() -> None:
        """Record spend for whatever was billed, exactly once. The user is charged
        per API response, so this must run before re-raising a mid-run failure too,
        not only on the happy path."""
        nonlocal _spend_done
        if _spend_done:
            return
        _spend_done = True
        billed_tokens = tok_in_total or tok_out_total
        if stats["cells_translated"] > 0 or billed_tokens:
            # prefer exact token usage; cells_translated==0 means a run that billed
            # responses but completed no cells, which still bills the real tokens
            if billed_tokens and (have_usage or stats["cells_translated"] == 0):
                actual_usd = (tok_in_total / 1e6 * rate["in_per_mtok"]
                              + tok_out_total / 1e6 * rate["out_per_mtok"])
                units = f"{tok_in_total + tok_out_total:,} tokens"
            else:
                # no usage reported (e.g. a stub): char-based fallback. Overhead is
                # per unique input (duplicates are sent once), not per output cell.
                chars = stats["chars_sent"]
                tok_in = chars / 4 + stats["unique_sent"] * 12
                actual_usd = (tok_in / 1e6 * rate["in_per_mtok"]
                              + chars / 4 / 1e6 * rate["out_per_mtok"])
                units = f"~{chars:,} chars (estimated)"
            spend = usage_ledger.record("translate", model_id, units, actual_usd)
        else:
            s = usage_ledger.summary()
            spend = {"run_usd": 0.0, "run_usd_display": "$0.00",
                     "total_usd": s["total_usd"], "total_usd_display": s["total_usd_display"]}
        stats["actual_usd"] = spend["run_usd"]
        stats["actual_usd_display"] = spend["run_usd_display"]
        stats["total_spend_usd"] = spend["total_usd"]
        stats["total_spend_usd_display"] = spend["total_usd_display"]

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
        idx = 0
        batches_done = 0
        max_batch_secs = 0.0
        while idx < len(pending):
            # adaptive budget guard: do not START a new batch unless it will plausibly
            # finish in time (reserve the slowest batch seen, with margin), so a pass
            # is never killed mid-batch. Always do at least one batch per call.
            if deadline is not None and batches_done > 0:
                now = time.monotonic()
                if now >= deadline or now + max_batch_secs * 1.2 > deadline:
                    stats["incomplete"] = True
                    break
            chunk, idx = _next_batch(pending, idx, batch_size, _MAX_BATCH_CHARS)
            if client_obj is None:
                client_obj = _get_client(client)
            t0 = time.monotonic()
            results = _translate_batch(client_obj, chunk, target_language,
                                       source_language, model_id, max_retries,
                                       _record_usage)
            max_batch_secs = max(max_batch_secs, time.monotonic() - t0)
            batches_done += 1
            for text, raw in zip(chunk, results):
                stats["cells_translated"] += len(to_translate[text])
                stats["chars_sent"] += len(text)
                stats["unique_sent"] += 1  # one API item per unique source string
                done = finish(raw)
                for (i, oc) in to_translate[text]:
                    resolved[(i, oc)] = done
                if cache_conn is not None:
                    cache_conn.execute(
                        "INSERT OR REPLACE INTO translations VALUES (?,?,?,?,?)",
                        (lang_key, target_language, model_id, _text_hash(text), raw))
            if cache_conn is not None:
                cache_conn.commit()
        if stats["incomplete"]:
            # cells whose unique source was not reached this pass stay empty in the
            # output; a resume pass fills them from cache
            stats["cells_pending"] = sum(len(to_translate[t]) for t in pending[idx:])

        out_rows = []
        for i, row in enumerate(rows):
            out_row = dict(row)
            for col in columns:
                oc = out_columns[col]
                out_row[oc] = resolved.get((i, oc), "")
            out_rows.append(out_row)
        _write_csv_atomic(output_path, out_fieldnames, out_rows)
    except BaseException:
        # a later batch (or the output write) failed after earlier paid batches
        # already incurred cost; record that real spend before propagating
        _finalize_spend()
        raise
    finally:
        if cache_conn is not None:
            cache_conn.close()
    stats["model"] = model_id
    stats["output_path"] = output_path
    stats["rates_as_of"] = prov["last_verified"]
    stats["rates_source"] = prov["source"]
    _finalize_spend()
    return stats


def _write_text_atomic(output_path: str, text: str) -> None:
    """Write text atomically and owner-only (0600); a failed write never leaves a
    truncated file and translated text is not world-readable."""
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(out.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, output_path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _segment_text(text: str, max_chars: int) -> list[tuple[int, str]]:
    """Split ``text`` into ``(paragraph_index, segment)`` pairs no larger than
    ``max_chars``, preferring paragraph then sentence boundaries. Deterministic, so a
    resume re-segments identically and reuses the cache. The paragraph index lets the
    caller rejoin segments of the same paragraph when stitching the translation."""
    paragraphs = re.split(r"\n\s*\n", text.strip())
    out: list[tuple[int, str]] = []
    for pi, para in enumerate(paragraphs):
        para = para.strip()
        if not para:
            continue
        if len(para) <= max_chars:
            out.append((pi, para))
            continue
        cur = ""
        for sentence in re.split(r"(?<=[.!?])\s+", para):
            if cur and len(cur) + 1 + len(sentence) > max_chars:
                out.append((pi, cur))
                cur = sentence
            else:
                cur = f"{cur} {sentence}".strip() if cur else sentence
        if cur:
            out.append((pi, cur))
    return out


def _stitch_segments(segments: list[tuple[int, str]], translated: list[str]) -> str:
    """Rejoin translated segments: segments of one source paragraph are joined with a
    space, paragraphs with a blank line."""
    paras: dict[int, list[str]] = {}
    order: list[int] = []
    for (pi, _src), tr in zip(segments, translated):
        if pi not in paras:
            paras[pi] = []
            order.append(pi)
        paras[pi].append(tr)
    return "\n\n".join(" ".join(paras[pi]).strip() for pi in order).strip() + "\n"


def _doc_segment_csv(text: str, segment_chars: int, dir_: str) -> tuple[str, list[tuple[int, str]]]:
    """Write the document's segments to a one-column CSV in ``dir_`` and return
    (csv_path, segments). The CSV is the input to translate_csv, reusing its caching,
    budgeting, and billing."""
    segments = _segment_text(text, segment_chars)
    seg_csv = os.path.join(dir_, "segments.csv")
    with open(seg_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["segment"])
        w.writeheader()
        for _pi, s in segments:
            w.writerow({"segment": s})
    return seg_csv, segments


def estimate_document_cost(input_path: str, target_language: str,
                           model: str | None = None,
                           segment_chars: int = _DEFAULT_SEGMENT_CHARS) -> dict:
    """Estimate the cost of translating a long document (segments it the same way
    translate_document does, then reuses the CSV estimate)."""
    text = Path(input_path).read_text(encoding="utf-8")
    with tempfile.TemporaryDirectory() as d:
        seg_csv, segments = _doc_segment_csv(text, segment_chars, d)
        est = estimate_cost(seg_csv, ["segment"], target_language, model)
    est["segments"] = len(segments)
    return est


def translate_document(input_path: str, output_path: str, target_language: str,
                       source_language: str | None = None, model: str | None = None,
                       glossary_path: str | None = None, cache_path: str | None = None,
                       client=None, confirm: bool = False,
                       max_seconds: float | None = None,
                       segment_chars: int = _DEFAULT_SEGMENT_CHARS,
                       max_retries: int = _MAX_RETRIES) -> dict:
    """Translate a long text/markdown document by segmenting it, translating the
    segments (reusing translate_csv: cached, size-budgeted, resumable), and stitching
    the result back into a document at ``output_path``.

    This is the right path for long-form text (a transcript, a report): the per-cell
    CSV translator cannot handle one giant cell, but a document of many small segments
    translates cleanly. Resumable across calls via ``max_seconds`` and ``cache_path``;
    re-run the SAME command until ``incomplete`` is False.

    :raises PermissionError: If ``confirm`` is not ``True``.
    """
    if not confirm:
        raise PermissionError(
            "translate_document requires confirm=True. Run estimate_document_cost(), "
            "show the user the cost and PII warning, and only proceed after confirmation.")
    text = Path(input_path).read_text(encoding="utf-8")
    with tempfile.TemporaryDirectory() as d:
        seg_csv, segments = _doc_segment_csv(text, segment_chars, d)
        seg_out = os.path.join(d, "segments_translated.csv")
        stats = translate_csv(
            seg_csv, ["segment"], target_language, source_language, seg_out,
            model=model, glossary_path=glossary_path, cache_path=cache_path,
            client=client, confirm=True, max_retries=max_retries, max_seconds=max_seconds)
        with open(seg_out, newline="", encoding="utf-8") as f:
            translated = [r.get(f"segment_{target_language}", "")
                          for r in csv.DictReader(f)]
    _write_text_atomic(output_path, _stitch_segments(segments, translated))
    stats["output_path"] = output_path
    stats["segments"] = len(segments)
    return stats


def _parse_columns(raw: str) -> list[str]:
    """Split a --columns value on commas, trimming surrounding whitespace so
    ``note, comment`` yields ``['note', 'comment']`` not ``['note', ' comment']``
    (the latter would not match the header). Rejects empty names (a stray or
    trailing comma)."""
    names = [c.strip() for c in raw.split(",")]
    if any(not c for c in names):
        raise ValueError(
            "Empty column name in --columns (check for a stray or trailing comma).")
    return names


_MAX_SECONDS_HELP = ("per-call work budget. Set it about 5s below your environment's "
                     "per-command timeout (e.g. 40 for a 45s cap); default "
                     f"{_DEFAULT_MAX_SECONDS:.0f}s. The call stops cleanly when reached "
                     "and reports incomplete to resume. 0 runs to completion in one "
                     "call (only on an uncapped host).")


def _main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(
        description="Translate via OpenAI. 'estimate'/'translate' work on CSV columns "
                    "(many short cells); 'estimate-doc'/'translate-doc' work on a long "
                    "text/markdown document. Run an estimate first, then the matching "
                    "command with --confirm. If a run reports incomplete, re-run the "
                    "SAME command to resume (cached work is not re-billed).",
        epilog="Examples:\n"
               "  python translation.py estimate data.csv --columns notes --target en\n"
               "  python translation.py translate data.csv --columns notes \\\n"
               "      --target en --output data_en.csv --confirm\n"
               "  python translation.py translate-doc transcript.txt \\\n"
               "      --target es --output transcript_es.txt --confirm\n"
               "Omit --source to auto-detect. Resuming: keep the same --output and\n"
               "--cache and re-run once per command (do not wrap in a shell loop).",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    pe = sub.add_parser("estimate", help="show cell count, approx cost, and the PII warning")
    pe.add_argument("csv_path", help="path to the exported CSV")
    pe.add_argument("--columns", required=True, help="comma-separated column names to translate")
    pe.add_argument("--target", required=True, help="target language ISO code (en, es, fr, ...)")
    pe.add_argument("--model", default=None, help="cheap (default, gpt-4.1-nano) | better")
    pt = sub.add_parser("translate", help="translate the columns and write a new CSV")
    pt.add_argument("csv_path", help="path to the exported CSV")
    pt.add_argument("--columns", required=True, help="comma-separated column names to translate")
    pt.add_argument("--target", required=True, help="target language ISO code (en, es, fr, ...)")
    pt.add_argument("--source", default=None, help="source language ISO code; omit to auto-detect")
    pt.add_argument("--output", required=True, help="path for the result CSV (adds <col>_<target> columns)")
    pt.add_argument("--model", default=None, help="cheap (default, gpt-4.1-nano) | better")
    pt.add_argument("--glossary", default=None, help="optional CSV with source,target term overrides")
    pt.add_argument("--cache", default=None,
                    help="SQLite cache path; defaults to a local cache under ~/.surveycto-skill/cache")
    pt.add_argument("--confirm", action="store_true", help="required: confirms you accepted the cost/PII")
    pt.add_argument("--max-seconds", type=float, default=_DEFAULT_MAX_SECONDS, help=_MAX_SECONDS_HELP)
    ped = sub.add_parser("estimate-doc", help="cost/PII for translating a long text/markdown document")
    ped.add_argument("input", help="path to the text/markdown file")
    ped.add_argument("--target", required=True, help="target language ISO code")
    ped.add_argument("--model", default=None, help="cheap (default) | better")
    ped.add_argument("--segment-chars", type=int, default=_DEFAULT_SEGMENT_CHARS,
                     help=f"max characters per segment (default {_DEFAULT_SEGMENT_CHARS})")
    pdc = sub.add_parser("translate-doc", help="translate a long text/markdown document (chunked, resumable)")
    pdc.add_argument("input", help="path to the text/markdown file to translate")
    pdc.add_argument("--target", required=True, help="target language ISO code")
    pdc.add_argument("--source", default=None, help="source language ISO code; omit to auto-detect")
    pdc.add_argument("--output", required=True, help="path for the translated document")
    pdc.add_argument("--model", default=None, help="cheap (default, gpt-4.1-nano) | better")
    pdc.add_argument("--glossary", default=None, help="optional CSV with source,target term overrides")
    pdc.add_argument("--cache", default=None,
                     help="SQLite cache path; defaults to a local cache under ~/.surveycto-skill/cache")
    pdc.add_argument("--segment-chars", type=int, default=_DEFAULT_SEGMENT_CHARS,
                     help=f"max characters per segment (default {_DEFAULT_SEGMENT_CHARS})")
    pdc.add_argument("--confirm", action="store_true", help="required: confirms you accepted the cost/PII")
    pdc.add_argument("--max-seconds", type=float, default=_DEFAULT_MAX_SECONDS, help=_MAX_SECONDS_HELP)
    args = p.parse_args(argv)

    if args.cmd == "estimate":
        print(json.dumps(estimate_cost(args.csv_path, _parse_columns(args.columns),
                                       args.target, args.model), indent=2))
        return 0
    if args.cmd == "estimate-doc":
        print(json.dumps(estimate_document_cost(args.input, args.target, args.model,
                                                args.segment_chars), indent=2))
        return 0
    if args.cmd in ("translate", "translate-doc"):
        if not args.confirm:
            print("Refusing to translate without --confirm. Run the matching estimate "
                  "first.", file=sys.stderr)
            return 1
        # run cleanup (spend ledger, cache close) even if a wrapper sends SIGTERM
        # before the self-imposed budget exits
        signal.signal(signal.SIGTERM, lambda *_: sys.exit(143))
        import openai_auth
        openai_auth.configure_openai()
        cache = args.cache or str(LOCAL_CACHE_DIR / "translation-cache.db")
        if args.cmd == "translate":
            result = translate_csv(
                args.csv_path, _parse_columns(args.columns), args.target, args.source,
                args.output, model=args.model, glossary_path=args.glossary,
                cache_path=cache, confirm=True, max_seconds=(args.max_seconds or None))
        else:
            result = translate_document(
                args.input, args.output, args.target, args.source, model=args.model,
                glossary_path=args.glossary, cache_path=cache, confirm=True,
                max_seconds=(args.max_seconds or None), segment_chars=args.segment_chars)
        print(json.dumps(result, indent=2))
        if result.get("incomplete"):
            print(f"\nNOTE: {result.get('cells_pending', 0)} item(s) not finished "
                  "within the time budget. Re-run the SAME command to resume from the "
                  "cache (finished items are not re-billed). Do not wrap it in a shell "
                  "loop; run it once per command.", file=sys.stderr)
            return 3  # distinct from success(0) and error(1): "resume me"
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1:]))

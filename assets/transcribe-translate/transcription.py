"""Transcribe audio files to text via OpenAI.

Supports the audio-transcription workflow in
``references/audio-transcription.md``. SurveyCTO audio captures (audio-audit
recordings, open-ended voice responses) are sensitive, so the content is sent
straight to OpenAI by a script and the transcripts written to a CSV; the agent
orchestrates and reports without ingesting the audio.

Model selection (the user picks; the cheapest is the default):

    "fast"     -> gpt-4o-mini-transcribe   (DEFAULT; cheapest, ~$0.003/min)
    "accurate" -> gpt-4o-transcribe        (~$0.006/min)
    "whisper"  -> whisper-1                (~$0.006/min; no duration cap, only 25 MB)
  A model id behind a menu name is also accepted; any other id is rejected,
  since the cost estimate needs a known per-minute rate.

Long files are chunked automatically: OpenAI limits a request to ~25 MB, and the
gpt-4o-* models also cap audio by a token/context limit (~15 min of speech,
content dependent), so files over either limit are split with ffmpeg into
compliant chunks. A small overlap keeps words at a cut from being dropped; its
duplicated words are removed when the pieces are stitched. whisper-1 has no
duration cap, so a sub-25 MB long file goes in one request.

Auth: ``openai_auth.configure_openai()`` sets ``OPENAI_API_KEY`` for the SDK
without printing the key. Cost gate: ``transcribe_files`` refuses to run unless
``confirm=True``; call ``estimate_cost`` and confirm first. Cache: with a
``cache_path``, transcripts are memoized (keyed on file bytes + model + language)
so re-runs are free. An API error never echoes audio content.

Standard library only at import time; ``openai`` is imported lazily only when a
call is made.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import shutil
import signal
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pricing
import usage_ledger

# Conservative request limits (under OpenAI's caps, verified live).
_MAX_BYTES = 24 * 1024 * 1024          # OpenAI 25 MB request cap; use 24 for margin
# The gpt-4o-* transcribe models reject overly long audio with an
# "input_too_large" token-context error (not a clean duration cap; depends on
# speech density). Live testing: ~15 min of moderate speech works, ~23 min fails.
# Start with a conservative window and rely on the adaptive recursive split
# (_transcribe_segment) for denser audio that still hits the token limit.
_GPT4O_MAX_DURATION_SEC = 600          # 10 min initial window for gpt-4o-* models
_MIN_SPLIT_SEC = 30.0                  # do not split a segment below this

# Default per-call budget for new chunk work: the call stops cleanly when reached
# and reports ``incomplete`` to resume, rather than being killed mid-chunk (which
# wastes the in-flight, already-billed request). Callers raise it where longer
# commands are allowed, for fewer passes.
_DEFAULT_MAX_SECONDS = 40.0

# Transcription model menu. Holds behaviour only (model id, billing basis,
# chunking duration window); rates live in pricing.json (loaded via pricing.py)
# so they can be refreshed without a code change. Billing basis confirmed against
# the live API: gpt-4o-* return token usage (UsageTokens) and bill per token, so
# post-run spend is computed from the response's real token counts; whisper-1
# returns duration usage (UsageDuration) and bills per audio minute.
_MODELS = {
    "fast":     {"id": "gpt-4o-mini-transcribe", "billing": "token",
                 "max_duration_sec": _GPT4O_MAX_DURATION_SEC},
    "accurate": {"id": "gpt-4o-transcribe", "billing": "token",
                 "max_duration_sec": _GPT4O_MAX_DURATION_SEC},
    "whisper":  {"id": "whisper-1", "billing": "minute",
                 "max_duration_sec": None},
}
DEFAULT_MODEL = "fast"

_PII_WARNING = (
    "PRIVACY: the selected audio will be sent to OpenAI (a third-party service) "
    "for transcription. Audio recordings carry respondents' voices and often "
    "spoken PII (names, locations). Confirm this transfer is acceptable under the "
    "user's data-governance rules before transcribing."
)

_AUDIO_EXTS = {".wav", ".flac", ".mp3", ".m4a", ".ogg", ".opus", ".webm", ".aac", ".amr"}


def resolve_model(model: str | None) -> dict:
    """Resolve a menu name or supported model id to a spec dict.

    :param model: A menu key (``fast``/``accurate``/``whisper``), a model id that
        matches a known menu entry, or ``None`` for the default. Fails closed on
        any other id, since the cost estimate needs a known rate.
    :returns: Dict with ``id``, ``billing``, ``max_duration_sec``.
    """
    if not model:
        return dict(_MODELS[DEFAULT_MODEL])
    if model in _MODELS:
        return dict(_MODELS[model])
    for spec in _MODELS.values():
        if spec["id"] == model:
            return dict(spec)
    # fail closed: pricing drives the estimate, confirmation, and ledger
    known = ", ".join(sorted({s["id"] for s in _MODELS.values()}))
    raise ValueError(
        f"Unknown transcription model '{model}'. Use a menu name (fast, accurate, "
        f"whisper) or a supported model id ({known}). To use another model, add it "
        "to the model menu and its rate to pricing.json.")


_NO_EGRESS_MSG = (
    "could not reach OpenAI (api.openai.com); network egress is likely disabled. "
    "On claude.ai enable it under Settings > Capabilities; on Team/Enterprise the "
    "default blocks third-party APIs, so ask an admin to allowlist api.openai.com "
    "(see references/openai-credentials.md)"
)


def _is_egress_error(exc: Exception) -> bool:
    """True iff ``exc`` is the OpenAI SDK's connection-failure type.

    Keyed to the SDK's exception contract, not message text. ``APIConnectionError``
    is raised for any failure to reach the API; ``APITimeoutError`` subclasses it,
    so one isinstance check covers a blocked egress without misclassifying API/auth
    errors that did reach the server.
    """
    try:
        from openai import APIConnectionError  # noqa: PLC0415
    except Exception:  # noqa: BLE001 - openai not importable -> cannot be this type
        return False
    return isinstance(exc, APIConnectionError)


def _media_env() -> dict:
    """Environment for ffmpeg/ffprobe with the OpenAI key removed. The media tools
    never need it, and the CLI puts it in the process environment, so stripping it
    keeps a binary planted earlier on PATH from reading it. PATH and the rest are
    kept so ffmpeg still resolves its codecs/locale."""
    return {k: v for k, v in os.environ.items() if k != "OPENAI_API_KEY"}


def _audio_duration_seconds(path: str) -> float | None:
    """Return audio duration in seconds via ffprobe, or None if unavailable."""
    if not shutil.which("ffprobe"):
        return None
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", "--", path],
            capture_output=True, text=True, timeout=60, env=_media_env(),
        )
        value = out.stdout.strip()
        return float(value) if value else None
    except (subprocess.SubprocessError, ValueError, OSError):
        return None


def _billed_minutes(duration_seconds: float) -> float:
    """Audio minutes billed (rounded up to the nearest second, min 1 second)."""
    return max(1.0, math.ceil(duration_seconds)) / 60.0


def _usd_display(usd: float) -> str:
    """Human-readable cost so a sub-cent estimate never reads as free $0.00."""
    if usd <= 0:
        return "$0.00"
    if usd < 0.01:
        return "< $0.01"
    return f"${usd:.2f}"


def estimate_cost(audio_paths: list[str], model: str | None = None) -> dict:
    """Estimate transcription cost for the given files.

    :param audio_paths: Paths to audio files.
    :param model: Menu name or model id.
    :returns: Dict with ``known_seconds``, ``estimated_usd``, ``files``,
        ``unknown_duration`` (paths whose duration could not be read),
        ``model``, ``rates_as_of``/``rates_source``/``pricing_source_url``
        (how current the rates are), and ``pii_warning``.

    Pre-run approximation from a per-minute figure; the gpt-4o-* models bill per
    token, so actual post-run spend (from real token counts) can differ. whisper-1
    bills per minute, so its estimate is close.
    """
    spec = resolve_model(model)
    price_data, prov = pricing.load()
    rate = pricing.rate_for(price_data, "transcription", spec["id"])
    # per-minute figure for the estimate: est_per_min for token-billed models,
    # the actual per-minute rate for whisper-1
    per_min = rate.get("est_per_min", rate.get("usd_per_min", 0.0))
    known = 0.0
    unknown: list[str] = []
    usd = 0.0
    for p in audio_paths:
        if not os.path.isfile(p):
            unknown.append(p)
            continue
        dur = _audio_duration_seconds(p)
        if dur is None:
            unknown.append(p)
            continue
        known += dur
        usd += _billed_minutes(dur) * per_min
    return {
        "known_seconds": round(known, 2),
        "estimated_usd": round(usd, 4),
        "estimated_usd_display": _usd_display(usd),
        "estimate_basis": "approximate (per-minute); actual billed per token for gpt-4o-* models",
        "files": len(audio_paths),
        "unknown_duration": unknown,
        "model": spec["id"],
        "rates_as_of": prov["last_verified"],
        "rates_source": prov["source"],
        "pricing_source_url": prov["source_url"],
        "pii_warning": _PII_WARNING,
    }


# ---- chunking -------------------------------------------------------------

class TranscriptionError(RuntimeError):
    """A transcription failure whose message is safe to surface.

    Carries no source path, audio content, or model-response text, so it can be
    reported verbatim. Raised for known, actionable conditions (missing ffmpeg, a
    segment still too large at the split floor). Unexpected exceptions are reduced
    to their type name instead.
    """


def _stitch(left: str, right: str, max_overlap_words: int = 8) -> str:
    """Join two adjacent transcript pieces, removing the words duplicated by the
    ~1s chunk overlap (which exists so no word is cut at a boundary, but makes
    ``left``'s tail repeat as ``right``'s head). Drop the longest such repeat,
    matched case-insensitively and ignoring punctuation, within a bounded window so
    a long coincidental similarity cannot be collapsed. A word genuinely spoken
    twice across the seam (a stutter) is indistinguishable from overlap without
    per-word timestamps the models' plain-text output lacks, so it is treated as
    overlap; rare, chunked-audio-only, and called out in the quality reminder."""
    left, right = left.strip(), right.strip()
    if not left:
        return right
    if not right:
        return left
    lw, rw = left.split(), right.split()

    def norm(w: str) -> str:
        return "".join(ch for ch in w.lower() if ch.isalnum())

    ln = [norm(w) for w in lw]
    rn = [norm(w) for w in rw]
    limit = min(max_overlap_words, len(lw), len(rw))
    best = 0
    for k in range(limit, 0, -1):
        if ln[-k:] == rn[:k]:
            best = k
            break
    return (" ".join(lw) + " " + " ".join(rw[best:])).strip()


def _extract_chunk(src: str, start: float, length: float, dst: str) -> None:
    """Re-encode a [start, start+length] slice to a small valid mp3 (libmp3lame)."""
    if not shutil.which("ffmpeg"):
        raise TranscriptionError(
            "ffmpeg is required to split long audio but was not found on PATH "
            "(install it: 'brew install ffmpeg' or 'apt-get install ffmpeg').")
    cmd = ["ffmpeg", "-y", "-ss", f"{start}", "-t", f"{length}", "-i", src,
           "-ac", "1", "-ar", "16000", "-c:a", "libmp3lame", "-b:a", "64k", dst]
    subprocess.run(cmd, capture_output=True, timeout=600, check=True, env=_media_env())


def _is_too_large_error(exc: Exception) -> bool:
    """True if the OpenAI error means the audio request exceeded a request limit.

    Keyed to the structured fields the SDK exposes, confirmed by triggering both
    cases against the live API:
      * token/context limit (gpt-4o-* on long audio): ``openai.BadRequestError``,
        HTTP 400, ``code == "input_too_large"``.
      * byte limit (request body over 25 MB): ``openai.APIStatusError``, HTTP 413.
    Matching ``code`` and ``status_code`` (not message text) keeps detection from
    firing on unrelated 400s.
    """
    if getattr(exc, "code", None) == "input_too_large":
        return True
    return getattr(exc, "status_code", None) == 413


def _blank_usage() -> dict:
    """A zeroed usage accumulator. ``None`` distinguishes 'never reported' (caller
    falls back to a per-minute estimate) from a genuine zero. ``calls`` and
    ``with_tokens``/``with_seconds`` count how many API calls reported each kind of
    usage, so the caller can detect an incomplete run (some paid calls missing
    usage) and fall back rather than under-bill."""
    return {"input_tokens": None, "output_tokens": None, "seconds": None,
            "calls": 0, "with_tokens": 0, "with_seconds": 0}


def _resp_usage(resp) -> dict:
    """Billing usage from one transcription response, normalised to the accumulator
    shape (``calls=1``). Confirmed against the live API: gpt-4o-* carry
    ``usage.input_tokens``/``usage.output_tokens`` (token-billed); whisper-1 carries
    ``usage.seconds`` (duration-billed). A response without usage still counts as a
    call but reports nothing, marking the run incomplete so the caller estimates
    instead of under-billing."""
    u = getattr(resp, "usage", None)
    if u is None:
        return {"input_tokens": None, "output_tokens": None, "seconds": None,
                "calls": 1, "with_tokens": 0, "with_seconds": 0}
    it = getattr(u, "input_tokens", None)
    ot = getattr(u, "output_tokens", None)
    sec = getattr(u, "seconds", None)
    return {
        "input_tokens": it, "output_tokens": ot, "seconds": sec,
        "calls": 1,
        "with_tokens": 1 if (it is not None or ot is not None) else 0,
        "with_seconds": 1 if sec is not None else 0,
    }


def _add_usage(acc: dict, u: dict) -> dict:
    """Fold one response's usage into the accumulator (sum across chunks/files)."""
    for k in ("input_tokens", "output_tokens", "seconds"):
        v = u.get(k)
        if v is not None:
            acc[k] = (acc[k] or 0) + v
    for k in ("calls", "with_tokens", "with_seconds"):
        acc[k] = acc.get(k, 0) + u.get(k, 0)
    return acc


def _transcribe_openai_file(path: str, model_id: str, client=None,
                            language: str | None = None) -> tuple[str, dict]:
    """Transcribe one already-compliant file via the OpenAI audio API.

    ``language`` is an optional ISO-639-1 hint forwarded to the API to improve
    accuracy/latency; omit to let the model auto-detect. Returns ``(text, usage)``
    with ``usage`` the normalised billing usage (see :func:`_resp_usage`).
    """
    if client is None:
        try:
            from openai import OpenAI  # noqa: PLC0415
        except ModuleNotFoundError as exc:
            raise TranscriptionError(
                "the 'openai' package is not installed. Run 'python3 setup_env.py' "
                "first and use the venv interpreter it prints."
            ) from exc
        client = OpenAI()
    with open(path, "rb") as fh:
        kwargs = {"model": model_id, "file": fh}
        if language:
            kwargs["language"] = language
        resp = client.audio.transcriptions.create(**kwargs)
    return (getattr(resp, "text", "") or ""), _resp_usage(resp)


def _fits_whole(path: str, spec: dict, dur: float | None = None) -> bool:
    """Whether the file is within both the size and (model) duration limits.

    ``dur`` may be passed when the caller already measured it, to avoid a second
    ffprobe call; otherwise it is measured here.
    """
    if os.path.getsize(path) > _MAX_BYTES:
        return False
    md = spec.get("max_duration_sec")
    if md is None:
        return True
    if dur is None:
        dur = _audio_duration_seconds(path)
    if dur is None:
        return True  # cannot measure; size already fits, attempt whole
    return dur <= md


def _transcribe_segment(src: str, start: float, length: float, model_id: str,
                        client, depth: int = 0,
                        language: str | None = None,
                        acc: dict | None = None) -> tuple[str, float, dict]:
    """Transcribe a [start, start+length] segment, splitting recursively if the
    model rejects it as too large (adapts to dense audio / token limits).

    Returns ``(text, submitted_seconds, usage)``. ``submitted_seconds`` is the audio
    sent to OpenAI summed across splits, including the ~1s overlap re-sent at each
    seam (duration-billing basis); ``usage`` is the summed token usage (gpt-4o-*).

    ``acc`` is an optional shared accumulator (``{"usage": dict, "seconds": float}``).
    When given, each leaf folds its billing in as its call succeeds, so spend from
    done chunks survives a later sibling's failure. Only leaves fold (never
    double-counted); the returned values are independent of ``acc``.
    """
    with tempfile.TemporaryDirectory() as d:
        seg = os.path.join(d, "seg.mp3")
        _extract_chunk(src, start, length, seg)
        if os.path.getsize(seg) <= _MAX_BYTES:
            try:
                text, usage = _transcribe_openai_file(seg, model_id, client, language)
                if acc is not None:
                    _add_usage(acc["usage"], usage)
                    acc["seconds"] += length
                return text, length, usage
            except Exception as exc:
                if not _is_too_large_error(exc):
                    raise
        # too large (by size or token limit): split this segment and recurse
        if length <= _MIN_SPLIT_SEC or depth > 10:
            raise TranscriptionError(
                "audio segment is too large to transcribe even after splitting")
    half = length / 2
    overlap = 1.0
    lt, ls, lu = _transcribe_segment(src, start, half, model_id, client, depth + 1, language, acc)
    rt, rs, ru = _transcribe_segment(src, max(0.0, start + half - overlap),
                                     length - half + overlap, model_id, client, depth + 1, language, acc)
    usage = _add_usage(_add_usage(_blank_usage(), lu), ru)
    return _stitch(lt, rt), ls + rs, usage


def _plan_chunks(path: str, dur: float, spec: dict) -> tuple[list[tuple[float, float]], bool]:
    """Deterministic list of ``(start, length)`` windows to transcribe, plus a flag
    saying whether the whole file fits one request.

    The plan depends only on the file and model, so a window has the same identity
    across runs and resume finds its cached chunk again. Windows are as large as a
    request allows (model audio limit, or the size budget for a model with no
    duration cap), minimising seams, and carry a 1s overlap so no word is lost at a
    cut. A file that fits one request is a single seam-free window.
    """
    if _fits_whole(path, spec, dur):
        return [(0.0, dur)], True
    size = os.path.getsize(path)
    bytes_per_sec = size / dur if dur > 0 else 0
    window = 0.9 * _MAX_BYTES / bytes_per_sec if bytes_per_sec > 0 else dur
    md = spec.get("max_duration_sec")
    if md is not None:
        window = min(window, md)
    window = max(60.0, window)
    overlap = 1.0
    plan: list[tuple[float, float]] = []
    start = 0.0
    while start < dur:
        s = start if not plan else max(0.0, start - overlap)
        length = min(window, dur - s)
        plan.append((round(s, 3), round(length, 3)))
        start = s + length
        if length <= overlap:
            break
    return plan, False


def _transcribe_window(path: str, spec: dict, client, start: float, length: float,
                       is_whole: bool, dur: float, language: str | None,
                       bill: dict) -> str:
    """Transcribe one planned window and fold its billing into ``bill``.

    A whole-file window is sent as-is (no re-encode); a partial window is extracted
    with ffmpeg and transcribed via the adaptive splitter so a still-too-large slice
    is recursively divided. Returns the window's transcript text.
    """
    if is_whole:
        text, usage = _transcribe_openai_file(path, spec["id"], client, language)
        _add_usage(bill["usage"], usage)
        bill["seconds"] += dur
        return text
    text, _sub, _usage = _transcribe_segment(path, start, length, spec["id"], client,
                                             language=language, acc=bill)
    return text


# ---- cache ----------------------------------------------------------------

def _restrict_cache_permissions(cache_path: str) -> None:
    """Make the cache readable only by its owner. It holds transcript text (often
    spoken PII), so it gets the same 0600 treatment as the API-key config."""
    try:
        os.chmod(cache_path, 0o600)
    except OSError:
        pass


def _write_csv_atomic(output_path: str, fieldnames: list[str], rows: list[dict]) -> None:
    """Write a results CSV atomically and owner-only. Transcripts can contain
    spoken PII, so the deliverable is created 0600 (mkstemp default) and only
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


# Local, non-mounted cache location. SQLite needs file locking that mounted/network
# folders (where a sandbox places the user's files) often do not provide, so caches
# default and fall back here rather than next to the user's data.
LOCAL_CACHE_DIR = Path.home() / ".surveycto-skill" / "cache"


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
            "CREATE TABLE IF NOT EXISTS transcripts ("
            "file_hash TEXT NOT NULL, backend TEXT NOT NULL, language TEXT NOT NULL, "
            "transcript TEXT NOT NULL, PRIMARY KEY (file_hash, backend, language))"
        )
        # migrate a pre-language cache: the language hint affects the transcript,
        # so an old table (keyed only by file+backend) must not serve a row for a
        # different language. The cache is disposable, so rebuild it.
        cols = [r[1] for r in conn.execute("PRAGMA table_info(transcripts)")]
        if "language" not in cols:
            conn.execute("DROP TABLE transcripts")
            conn.execute(
                "CREATE TABLE transcripts ("
                "file_hash TEXT NOT NULL, backend TEXT NOT NULL, language TEXT NOT NULL, "
                "transcript TEXT NOT NULL, PRIMARY KEY (file_hash, backend, language))")
        # per-chunk results for long files: each finished window is committed on its
        # own (keyed by its [start, length)), so a timed-out run resumes from the
        # last finished chunk and never re-bills one already done.
        conn.execute(
            "CREATE TABLE IF NOT EXISTS transcript_chunks ("
            "file_hash TEXT NOT NULL, backend TEXT NOT NULL, language TEXT NOT NULL, "
            "chunk_start REAL NOT NULL, chunk_len REAL NOT NULL, transcript TEXT NOT NULL, "
            "PRIMARY KEY (file_hash, backend, language, chunk_start, chunk_len))")
    except Exception:
        conn.close()
        raise
    return conn


def _cache_connect(cache_path: str) -> sqlite3.Connection:
    """Open the cache, falling back to a local path if the requested one is on a
    filesystem SQLite cannot use. Network/mounted folders raise 'disk I/O error' or
    locking errors; the fallback is deterministic (same input -> same path) so resume
    across calls still works."""
    try:
        return _cache_connect_at(cache_path)
    except (sqlite3.OperationalError, OSError):
        fallback = _fallback_cache_path(cache_path)
        if Path(fallback) == Path(cache_path):
            raise
        print(f"[cache] '{cache_path}' cannot host a SQLite cache (likely a mounted "
              f"or network folder); using a local cache at {fallback}.", file=sys.stderr)
        return _cache_connect_at(fallback)


def _file_hash(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _write_text_atomic(output_path: str, text: str) -> None:
    """Write text atomically and owner-only (0600), mirroring _write_csv_atomic, so a
    failed write never leaves a truncated file and transcripts are not world-readable."""
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


def _render_transcripts(rows: list[dict], fmt: str) -> str:
    """Render result rows as a readable document. ``md`` uses a heading per file;
    ``txt`` uses a plain separator. Long-form recordings read far better this way
    than as one giant CSV cell."""
    parts = []
    for r in rows:
        name = os.path.basename(r["file"])
        meta = f'{r["backend"]}, {r["duration_seconds"]}s, {r["status"]}'
        if fmt == "md":
            parts.append(f"## {name}\n\n_{meta}_\n\n{r['transcript']}\n")
        else:  # txt
            parts.append(f"=== {name} ({meta}) ===\n{r['transcript']}\n")
    sep = "\n---\n\n" if fmt == "md" else "\n\n"
    head = "# Transcripts\n\n" if fmt == "md" else ""
    return head + sep.join(parts) + "\n"


# ---- public API -----------------------------------------------------------

def transcribe_files(audio_paths: list[str], output_path: str,
                     model: str | None = None,
                     cache_path: str | None = None, confirm: bool = False,
                     client=None, language: str | None = None,
                     max_seconds: float | None = None,
                     output_format: str = "csv") -> dict:
    """Transcribe audio files and write the results.

    ``output_format`` ``csv`` (default) writes columns ``file``, ``transcript``,
    ``backend``, ``duration_seconds``, ``status`` (one row per file, best for many
    short clips that join back to a dataset). ``md``/``txt`` write a readable
    document (best for a few long recordings). A file that errors gets an error
    token in its status and an empty transcript; the batch continues.

    Long files are split into durable, separately-cached chunks. With a
    ``cache_path`` and a ``max_seconds`` budget, a single call does bounded work and
    then stops cleanly, marking unfinished files ``incomplete`` in ``status`` and
    setting ``incomplete: True`` in the result; re-running the SAME command resumes
    from the cached chunks and never re-bills a finished one. This is how a file too
    long to transcribe inside one command-timeout is completed across several calls.

    :param audio_paths: Paths to audio files.
    :param output_path: Where to write the results CSV.
    :param model: Menu name (``fast``/``accurate``/``whisper``) or model id.
    :param cache_path: Optional SQLite cache path. Required for resume across calls;
        without it, each call starts the file from scratch.
    :param confirm: Must be ``True`` to run (cost gate).
    :param client: Optional injected client (testing).
    :param language: Optional ISO-639-1 hint (e.g. ``en``) forwarded to OpenAI to
        improve accuracy/latency; omit to let the model auto-detect.
    :param max_seconds: Per-call wall-clock budget for NEW chunk work. ``None``
        (default) means run to completion in one call; set it (the CLI defaults it)
        to make long files resumable under a command-timeout.
    :returns: Dict with ``transcribed``, ``cached``, ``failed``, ``pending``,
        ``incomplete``, ``backend``, ``output_path``.
    :raises PermissionError: If ``confirm`` is not ``True``.
    """
    if not confirm:
        raise PermissionError(
            "transcribe_files requires confirm=True. Run estimate_cost(), show "
            "the user the cost and PII warning, and only proceed after explicit "
            "confirmation."
        )
    spec = resolve_model(model)
    backend = spec["id"]
    price_data, prov = pricing.load()
    rate = pricing.rate_for(price_data, "transcription", backend)
    billing = spec.get("billing", "minute")
    lang_key = language or "auto"  # cache key: the hint changes the transcript
    cache_conn = _cache_connect(cache_path) if cache_path else None
    deadline = (time.monotonic() + max_seconds) if max_seconds else None
    stats = {"transcribed": 0, "cached": 0, "failed": 0, "pending": 0,
             "incomplete": False, "chunks_done": 0, "chunks_total": 0,
             "backend": backend, "output_path": output_path,
             "rates_as_of": prov["last_verified"], "rates_source": prov["source"]}
    run_usage = _blank_usage()  # summed token/duration usage from responses
    # shared billing accumulator: each finished request folds its usage and seconds
    # in immediately, so spend from done chunks survives a later chunk's failure.
    # ``seconds`` is the audio sent to OpenAI this run (duration basis).
    bill = {"usage": run_usage, "seconds": 0.0}
    _spend_done = False

    def _finalize_spend() -> None:
        """Record this run's real spend exactly once, even if a later step (e.g. the
        output write) fails after paid calls.

        Billing follows the model's mode: gpt-4o-* are token-billed, whisper-1 is
        duration-billed. If a paid call did not report the usage its mode needs (a
        mixed/incomplete run), fall back to the per-minute estimate for the whole
        run rather than billing only the calls that reported, which would
        under-report spend."""
        nonlocal _spend_done
        if _spend_done:
            return
        _spend_done = True
        billed_seconds = bill["seconds"]
        if billed_seconds > 0:
            calls = run_usage["calls"]
            if billing == "token":
                complete = calls > 0 and run_usage["with_tokens"] == calls
                in_tok, out_tok = run_usage["input_tokens"], run_usage["output_tokens"]
                if complete and (in_tok is not None or out_tok is not None):
                    in_tok, out_tok = in_tok or 0, out_tok or 0
                    actual_usd = (in_tok / 1e6 * rate["in_per_mtok"]
                                  + out_tok / 1e6 * rate["out_per_mtok"])
                    units = f"{in_tok + out_tok:,} tokens"
                else:
                    # no usage, or only some calls reported it: estimate the whole
                    # run per-minute so spend is never under-booked
                    actual_usd = _billed_minutes(billed_seconds) * rate.get("est_per_min", 0.0)
                    units = f"~{billed_seconds / 60:.1f} audio-min (estimated)"
            else:  # whisper-1: duration-billed; use the API's reported seconds only
                # if every call reported them, else the locally-measured submitted
                # duration (always complete by construction)
                complete = calls > 0 and run_usage["with_seconds"] == calls
                secs = run_usage["seconds"] if (complete and run_usage["seconds"] is not None) else billed_seconds
                actual_usd = _billed_minutes(secs) * rate["usd_per_min"]
                units = f"{secs / 60:.1f} audio-min"
            spend = usage_ledger.record("transcribe", backend, units, actual_usd)
        else:
            s = usage_ledger.summary()
            spend = {"run_usd": 0.0, "run_usd_display": "$0.00",
                     "total_usd": s["total_usd"], "total_usd_display": s["total_usd_display"]}
        stats["actual_usd"] = spend["run_usd"]
        stats["actual_usd_display"] = spend["run_usd_display"]
        stats["total_spend_usd"] = spend["total_usd"]
        stats["total_spend_usd_display"] = spend["total_usd_display"]

    rows: list[dict] = []
    try:
        for path in audio_paths:
            row = {"file": path, "transcript": "", "backend": backend,
                   "duration_seconds": "", "status": "ok"}
            try:
                if not os.path.isfile(path):
                    raise FileNotFoundError(f"No audio file at '{path}'.")
                key = _file_hash(path)
                # fast path: the whole file was already stitched on a prior run
                whole = None
                if cache_conn is not None:
                    hit = cache_conn.execute(
                        "SELECT transcript FROM transcripts WHERE file_hash=? AND "
                        "backend=? AND language=?", (key, backend, lang_key)).fetchone()
                    if hit is not None:
                        whole = hit[0]
                if whole is not None:
                    row["transcript"] = whole
                    row["duration_seconds"] = _audio_duration_seconds(path)  # info only
                    stats["cached"] += 1
                    rows.append(row)
                    continue
                # the per-call budget is spent: leave this file for a resume pass
                # rather than starting work that would be cut off
                if deadline is not None and time.monotonic() >= deadline:
                    row["status"] = "pending: not started; re-run to resume"
                    stats["pending"] += 1
                    stats["incomplete"] = True
                    rows.append(row)
                    continue
                # measure duration before any paid call so its cost can be reported;
                # an unmeasurable file would otherwise be sent and booked as $0.00
                dur = _audio_duration_seconds(path)
                if dur is None:
                    raise TranscriptionError(
                        "cannot measure this audio's duration (ffmpeg/ffprobe not "
                        "found or unreadable file); it is required before a paid "
                        "transcription so the cost can be reported. Install ffmpeg "
                        "(it provides ffprobe) and retry.")
                row["duration_seconds"] = dur
                plan, is_whole = _plan_chunks(path, dur, spec)
                stats["chunks_total"] += len(plan)
                try:
                    texts: list[str] = []
                    complete = True
                    new_chunks = 0
                    max_chunk_secs = 0.0  # slowest chunk this call, for the guard
                    for (cs, cl) in plan:
                        ctext = None
                        if cache_conn is not None:
                            chit = cache_conn.execute(
                                "SELECT transcript FROM transcript_chunks WHERE "
                                "file_hash=? AND backend=? AND language=? AND "
                                "chunk_start=? AND chunk_len=?",
                                (key, backend, lang_key, cs, cl)).fetchone()
                            if chit is not None:
                                ctext = chit[0]
                        if ctext is None:
                            # adaptive budget guard: do not START a new chunk unless
                            # it will plausibly finish before the deadline (reserve
                            # the slowest chunk seen, with margin), so a pass is never
                            # killed mid-chunk. Always do at least one chunk per call
                            # so progress is made.
                            if deadline is not None and new_chunks > 0:
                                now = time.monotonic()
                                if now >= deadline or now + max_chunk_secs * 1.2 > deadline:
                                    complete = False
                                    break
                            t0 = time.monotonic()
                            ctext = _transcribe_window(path, spec, client, cs, cl,
                                                       is_whole, dur, language, bill)
                            max_chunk_secs = max(max_chunk_secs, time.monotonic() - t0)
                            new_chunks += 1
                            if cache_conn is not None:
                                # commit each finished chunk on its own so a later
                                # interruption keeps this durable progress
                                cache_conn.execute(
                                    "INSERT OR REPLACE INTO transcript_chunks "
                                    "VALUES (?,?,?,?,?,?)",
                                    (key, backend, lang_key, cs, cl, ctext))
                                cache_conn.commit()
                        texts.append(ctext)
                    stats["chunks_done"] += len(texts)
                except TranscriptionError:
                    # message is safe by construction; surface as-is
                    raise
                except Exception as exc:
                    if _is_egress_error(exc):
                        raise TranscriptionError(_NO_EGRESS_MSG) from None
                    # sanitize: an API/library error could echo request content
                    raise TranscriptionError(
                        f"transcription failed ({type(exc).__name__})") from None
                if not complete:
                    row["status"] = (f"incomplete: {len(texts)}/{len(plan)} chunks "
                                     "done; re-run the same command to resume")
                    stats["pending"] += 1
                    stats["incomplete"] = True
                    rows.append(row)
                    continue
                stitched = ""
                for t in texts:
                    stitched = _stitch(stitched, t)
                row["transcript"] = stitched
                if cache_conn is not None:
                    cache_conn.execute(
                        "INSERT OR REPLACE INTO transcripts VALUES (?,?,?,?)",
                        (key, backend, lang_key, stitched))
                    cache_conn.commit()
                # a run that only stitched already-cached chunks billed nothing
                if new_chunks > 0:
                    stats["transcribed"] += 1
                else:
                    stats["cached"] += 1
            except FileNotFoundError:
                # never echo the path here; it is already in the `file` column
                row["status"] = "error: audio file not found"
                stats["failed"] += 1
            except TranscriptionError as exc:
                # message is sanitized by construction (no path/content)
                row["status"] = f"error: {exc}"
                stats["failed"] += 1
            except Exception as exc:  # noqa: BLE001 - record and continue
                # unknown exception: type name only, never its stringified content
                row["status"] = f"error: {type(exc).__name__}"
                stats["failed"] += 1
            rows.append(row)
        if output_format in ("md", "txt"):
            _write_text_atomic(output_path, _render_transcripts(rows, output_format))
        else:
            _write_csv_atomic(output_path, ["file", "transcript", "backend",
                                            "duration_seconds", "status"], rows)
    except BaseException:
        # paid calls may already have incurred cost before a later failure (e.g. the
        # output write); record that real spend before propagating
        _finalize_spend()
        raise
    finally:
        if cache_conn is not None:
            cache_conn.close()
    _finalize_spend()
    return stats


def _main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(
        description="Transcribe audio via OpenAI. Run 'estimate' first to see cost "
                    "and the privacy warning, then 'transcribe --confirm'. Long "
                    "files are split into cached chunks; if a run reports "
                    "incomplete, re-run the SAME command to resume (cached chunks "
                    "are not re-billed).",
        epilog="Examples:\n"
               "  python transcription.py estimate interview.mp3\n"
               "  python transcription.py transcribe interview.mp3 \\\n"
               "      --output transcripts.csv --cache transcription-cache.db --confirm\n"
               "Output CSV columns: file, transcript, backend, duration_seconds, status.\n"
               "Resuming long files: keep the same --output and --cache and re-run\n"
               "until the result shows \"incomplete\": false.\n"
               "Needs ffmpeg/ffprobe on PATH (duration + chunking).",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    pe = sub.add_parser("estimate", help="show duration, approx cost, and the PII warning")
    pe.add_argument("audio_paths", nargs="+", help="one or more audio file paths")
    pe.add_argument("--model", default=None, help="fast (default) | accurate | whisper")
    pt = sub.add_parser("transcribe", help="transcribe the audio and write a results CSV")
    pt.add_argument("audio_paths", nargs="+", help="one or more audio file paths")
    pt.add_argument("--output", required=True, help="path for the results CSV")
    pt.add_argument("--model", default=None,
                    help="fast (default, gpt-4o-mini-transcribe) | accurate | whisper")
    pt.add_argument("--cache", default=None,
                    help="SQLite cache path so re-runs/resume are free; defaults to a "
                         "local cache under ~/.surveycto-skill/cache")
    pt.add_argument("--format", default="csv", choices=("csv", "md", "txt"),
                    help="output format: csv (default, one row per file; best for many "
                         "short clips) | md | txt (readable document; best for a few "
                         "long recordings)")
    pt.add_argument("--language", default=None,
                    help="optional ISO-639-1 hint (e.g. en) to improve accuracy; omit to auto-detect")
    pt.add_argument("--confirm", action="store_true", help="required: confirms you accepted the cost/PII")
    pt.add_argument("--max-seconds", type=float, default=_DEFAULT_MAX_SECONDS,
                    help="per-call work budget for new chunks. Set it about 5s below "
                         "your environment's per-command timeout (e.g. 40 for a 45s "
                         f"cap); default {_DEFAULT_MAX_SECONDS:.0f}s. The call stops "
                         "cleanly when reached and reports incomplete to resume. 0 "
                         "runs to completion in one call (only on an uncapped host).")
    args = p.parse_args(argv)

    if args.cmd == "estimate":
        print(json.dumps(estimate_cost(args.audio_paths, args.model), indent=2))
        return 0
    if args.cmd == "transcribe":
        if not args.confirm:
            print("Refusing to transcribe without --confirm. Run 'estimate' first "
                  "and confirm the cost with the user.", file=sys.stderr)
            return 1
        # run cleanup (spend ledger, cache close) even if a wrapper sends SIGTERM
        # before the self-imposed budget exits: turn it into a normal exit so the
        # try/finally blocks run.
        signal.signal(signal.SIGTERM, lambda *_: sys.exit(143))
        import openai_auth
        openai_auth.configure_openai()
        cache = args.cache or str(LOCAL_CACHE_DIR / "transcribe-cache.db")
        result = transcribe_files(
            args.audio_paths, args.output, model=args.model,
            cache_path=cache, confirm=True, language=args.language,
            max_seconds=(args.max_seconds or None), output_format=args.format)
        print(json.dumps(result, indent=2))
        if result.get("incomplete"):
            print(f"\nNOTE: {result.get('pending', 0)} file(s) not finished within the "
                  "time budget. Re-run the SAME command to resume from the cached "
                  "chunks (already-done chunks are not re-billed). Do not wrap it in a "
                  "shell loop; run it once per command.", file=sys.stderr)
            return 3  # distinct from success(0) and error(1): "resume me"
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1:]))

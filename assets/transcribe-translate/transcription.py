"""Transcribe audio files to text via OpenAI.

Supports the audio-transcription workflow in
``references/audio-transcription.md``. SurveyCTO audio captures (audio-audit
recordings, open-ended voice responses) are sensitive, so the content is sent
straight to OpenAI by a script and the transcripts are written to a CSV; the
agent orchestrates and reports without ingesting the audio.

Model selection (the user picks; the cheapest is the default):

    "fast"     -> gpt-4o-mini-transcribe   (DEFAULT; cheapest, ~$0.003/min)
    "accurate" -> gpt-4o-transcribe        (~$0.006/min)
    "whisper"  -> whisper-1                (~$0.006/min; no duration cap, only 25 MB)
  An explicit model id (e.g. "gpt-4o-transcribe") is also accepted.

Long files are handled automatically: OpenAI limits a request to ~25 MB, and the
gpt-4o-* models also cap audio by a token/context limit (~15 min of speech,
content dependent), so files over either limit are split with ffmpeg into
compliant chunks (with a small overlap so words at a cut are not dropped; the
overlap's duplicated words are removed when the pieces are stitched). whisper-1
has no duration cap, so a sub-25 MB long file goes in one request.

Auth: ``openai_auth.configure_openai()`` sets ``OPENAI_API_KEY`` for the SDK
without ever printing the key. Cost gate: ``transcribe_files`` refuses to run
unless ``confirm=True``; call ``estimate_cost`` and confirm first. Cache: with a
``cache_path``, transcripts are memoized (keyed on file bytes + model) so re-runs
are free. Sanitized errors: an API error never echoes audio content.

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
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

import usage_ledger

# Conservative request limits (under OpenAI's caps, verified live).
_MAX_BYTES = 24 * 1024 * 1024          # OpenAI 25 MB request cap; use 24 for margin
# The gpt-4o-* transcribe models reject overly long audio with an
# "input_too_large" token-context error (not a clean duration cap; it depends on
# speech density). Live testing: ~15 min of moderate speech works, ~23 min fails.
# Use a conservative initial window and rely on the adaptive recursive split
# (_transcribe_segment) to handle denser audio that still hits the token limit.
_GPT4O_MAX_DURATION_SEC = 600          # 10 min initial window for gpt-4o-* models
_MIN_SPLIT_SEC = 30.0                  # do not split a segment below this

# Transcription model menu. usd_per_min are list rates (verify on the pricing
# page); they drive the estimate only, not behavior.
_MODELS = {
    "fast":     {"id": "gpt-4o-mini-transcribe", "usd_per_min": 0.003, "max_duration_sec": _GPT4O_MAX_DURATION_SEC},
    "accurate": {"id": "gpt-4o-transcribe",      "usd_per_min": 0.006, "max_duration_sec": _GPT4O_MAX_DURATION_SEC},
    "whisper":  {"id": "whisper-1",              "usd_per_min": 0.006, "max_duration_sec": None},
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
    """Resolve a menu name or explicit model id to a spec dict.

    :param model: One of the menu keys (``fast``/``accurate``/``whisper``), an
        explicit OpenAI model id, or ``None`` for the default.
    :returns: Dict with ``id``, ``usd_per_min``, ``max_duration_sec``.
    """
    if not model:
        return dict(_MODELS[DEFAULT_MODEL])
    if model in _MODELS:
        return dict(_MODELS[model])
    # explicit model id: assume the gpt-4o-* limits unless it is whisper
    is_whisper = "whisper" in model
    return {
        "id": model,
        "usd_per_min": 0.006,
        "max_duration_sec": None if is_whisper else _GPT4O_MAX_DURATION_SEC,
    }


_NO_EGRESS_MSG = (
    "could not reach OpenAI (api.openai.com); network egress is likely disabled. "
    "On claude.ai enable it under Settings > Capabilities; on Team/Enterprise the "
    "default blocks third-party APIs, so ask an admin to allowlist api.openai.com "
    "(see references/openai-credentials.md)"
)


def _is_connection_error(exc: Exception) -> bool:
    """True if the error looks like a blocked/failed network connection (so we can
    give actionable egress guidance). Matched on class name and generic phrases."""
    name = type(exc).__name__.lower()
    if any(k in name for k in ("connection", "timeout", "connecterror")):
        return True
    msg = str(exc).lower()
    return any(s in msg for s in (
        "connection error", "failed to establish", "getaddrinfo",
        "name or service not known", "temporary failure in name resolution",
        "network is unreachable", "connection refused", "no route to host",
    ))


def _audio_duration_seconds(path: str) -> float | None:
    """Return audio duration in seconds via ffprobe, or None if unavailable."""
    if not shutil.which("ffprobe"):
        return None
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", "--", path],
            capture_output=True, text=True, timeout=60,
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
        ``model``, and ``pii_warning``.
    """
    spec = resolve_model(model)
    rate = spec["usd_per_min"]
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
        usd += _billed_minutes(dur) * rate
    return {
        "known_seconds": round(known, 2),
        "estimated_usd": round(usd, 4),
        "estimated_usd_display": _usd_display(usd),
        "files": len(audio_paths),
        "unknown_duration": unknown,
        "model": spec["id"],
        "pii_warning": _PII_WARNING,
    }


# ---- chunking -------------------------------------------------------------

class TranscriptionError(RuntimeError):
    """A transcription failure whose message is safe to surface.

    Carries no source path, audio content, or model-response text, so it can be
    reported to the user verbatim. Raised for known, actionable conditions
    (missing ffmpeg, a segment still too large at the split floor). Genuinely
    unexpected exceptions are reduced to their type name instead.
    """


def _stitch(left: str, right: str, max_overlap_words: int = 8) -> str:
    """Join two adjacent transcript pieces, removing the words duplicated by the
    ~1s chunk overlap (the overlap exists so no word is cut at a boundary, but it
    makes ``left``'s tail repeat as ``right``'s head). Drop the longest such
    repeat, matched case-insensitively and ignoring punctuation, within a bounded
    window so a long coincidental similarity cannot be collapsed. A word genuinely
    spoken twice exactly across the seam (a stutter) cannot be told apart without
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
    subprocess.run(cmd, capture_output=True, timeout=600, check=True)


def _is_too_large_error(exc: Exception) -> bool:
    """True if the OpenAI error means the audio request exceeded the model limit.

    The condition surfaces under different SDK classes (a 400 for the token limit,
    a 413 for the byte limit), so detection spans class name, structured status,
    and message phrase rather than one class. It is intentionally inclusive: a
    false positive only wastes a split that fails safely at the floor, whereas a
    false negative fails the whole file. The 413 is matched on the status field,
    not a bare "413" substring (which would hit request ids in unrelated errors).
    """
    name = type(exc).__name__.lower()
    if "toolarge" in name or "payloadtoolarge" in name:
        return True
    status = getattr(exc, "status_code", None)
    if status == 413:
        return True
    code = str(getattr(exc, "code", "") or "").lower()
    if "context_length" in code or "too_large" in code:
        return True
    msg = str(exc).lower()
    return any(s in msg for s in (
        "input_too_large", "too large", "maximum context length",
        "exceeds the maximum", "request entity too large",
    ))


def _transcribe_openai_file(path: str, model_id: str, client=None) -> str:
    """Transcribe one already-compliant file via the OpenAI audio API."""
    if client is None:
        from openai import OpenAI  # noqa: PLC0415
        client = OpenAI()
    with open(path, "rb") as fh:
        resp = client.audio.transcriptions.create(model=model_id, file=fh)
    return getattr(resp, "text", "") or ""


def _fits_whole(path: str, spec: dict) -> bool:
    """Whether the file is within both the size and (model) duration limits."""
    if os.path.getsize(path) > _MAX_BYTES:
        return False
    md = spec.get("max_duration_sec")
    if md is None:
        return True
    dur = _audio_duration_seconds(path)
    if dur is None:
        return True  # cannot measure; size already fits, attempt whole
    return dur <= md


def _transcribe_segment(src: str, start: float, length: float, model_id: str,
                        client, depth: int = 0) -> str:
    """Transcribe a [start, start+length] segment, splitting recursively if the
    model rejects it as too large (adapts to dense audio / token limits)."""
    with tempfile.TemporaryDirectory() as d:
        seg = os.path.join(d, "seg.mp3")
        _extract_chunk(src, start, length, seg)
        if os.path.getsize(seg) <= _MAX_BYTES:
            try:
                return _transcribe_openai_file(seg, model_id, client)
            except Exception as exc:
                if not _is_too_large_error(exc):
                    raise
        # too large (by size or token limit): split this segment and recurse
        if length <= _MIN_SPLIT_SEC or depth > 10:
            raise TranscriptionError(
                "audio segment is too large to transcribe even after splitting")
    half = length / 2
    overlap = 1.0
    left = _transcribe_segment(src, start, half, model_id, client, depth + 1)
    right = _transcribe_segment(src, max(0.0, start + half - overlap),
                                length - half + overlap, model_id, client, depth + 1)
    return _stitch(left, right)


def _transcribe_one(path: str, spec: dict, client) -> str:
    """Transcribe one file: single-request, or windowed + adaptive chunks."""
    if _fits_whole(path, spec):
        try:
            return _transcribe_openai_file(path, spec["id"], client)
        except Exception as exc:
            if not _is_too_large_error(exc):
                raise
            # otherwise fall through to chunking
    dur = _audio_duration_seconds(path)
    if dur is None:
        raise TranscriptionError(
            "audio needs splitting but its duration could not be measured "
            "(install ffmpeg/ffprobe).")
    size = os.path.getsize(path)
    bytes_per_sec = size / dur if dur > 0 else 0
    window = 0.9 * _MAX_BYTES / bytes_per_sec if bytes_per_sec > 0 else dur
    md = spec.get("max_duration_sec")
    if md is not None:
        window = min(window, md)
    window = max(60.0, window)
    parts: list[str] = []
    overlap = 1.0
    start = 0.0
    while start < dur:
        s = start if not parts else max(0.0, start - overlap)
        length = min(window, dur - s)
        parts.append(_transcribe_segment(path, s, length, spec["id"], client))
        start = s + length
        if length <= overlap:
            break
    stitched = ""
    for p in parts:
        stitched = _stitch(stitched, p)
    return stitched


# ---- cache ----------------------------------------------------------------

def _restrict_cache_permissions(cache_path: str) -> None:
    """Make the cache readable only by its owner. It holds transcript text (often
    spoken PII), so it gets the same 0600 treatment as the API-key config."""
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
            "CREATE TABLE IF NOT EXISTS transcripts ("
            "file_hash TEXT NOT NULL, backend TEXT NOT NULL, "
            "transcript TEXT NOT NULL, PRIMARY KEY (file_hash, backend))"
        )
    except Exception:
        conn.close()
        raise
    return conn


def _file_hash(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


# ---- public API -----------------------------------------------------------

def transcribe_files(audio_paths: list[str], output_path: str,
                     model: str | None = None,
                     cache_path: str | None = None, confirm: bool = False,
                     client=None) -> dict:
    """Transcribe audio files and write a CSV of results.

    Output columns: ``file``, ``transcript``, ``backend``, ``duration_seconds``,
    ``status``. A file that errors gets an error token in ``status`` and an empty
    transcript; the batch continues.

    :param audio_paths: Paths to audio files.
    :param output_path: Where to write the results CSV.
    :param model: Menu name (``fast``/``accurate``/``whisper``) or model id.
    :param cache_path: Optional SQLite cache path.
    :param confirm: Must be ``True`` to run (cost gate).
    :param client: Optional injected client (testing).
    :returns: Dict with ``transcribed``, ``cached``, ``failed``, ``backend``,
        ``output_path``.
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
    cache_conn = _cache_connect(cache_path) if cache_path else None
    stats = {"transcribed": 0, "cached": 0, "failed": 0}
    billed_seconds = 0.0  # audio actually sent to OpenAI this run
    rows: list[dict] = []
    try:
        for path in audio_paths:
            row = {"file": path, "transcript": "", "backend": backend,
                   "duration_seconds": "", "status": "ok"}
            fresh = False
            try:
                if not os.path.isfile(path):
                    raise FileNotFoundError(f"No audio file at '{path}'.")
                key = _file_hash(path)
                cached = None
                if cache_conn is not None:
                    cur = cache_conn.execute(
                        "SELECT transcript FROM transcripts WHERE file_hash=? AND backend=?",
                        (key, backend))
                    hit = cur.fetchone()
                    if hit is not None:
                        cached = hit[0]
                if cached is not None:
                    row["transcript"] = cached
                    stats["cached"] += 1
                    row["duration_seconds"] = _audio_duration_seconds(path)  # info only
                else:
                    # Require a measurable duration BEFORE the paid call so its cost
                    # can be reported accurately. Otherwise a file with unreadable
                    # duration (no ffprobe) would still be sent and then booked as
                    # $0.00, silently under-reporting spend.
                    dur = _audio_duration_seconds(path)
                    if dur is None:
                        raise TranscriptionError(
                            "cannot measure this audio's duration (ffmpeg/ffprobe not "
                            "found or unreadable file); it is required before a paid "
                            "transcription so the cost can be reported. Install ffmpeg "
                            "(it provides ffprobe) and retry.")
                    try:
                        text = _transcribe_one(path, spec, client)
                    except TranscriptionError:
                        # message is safe by construction; surface as-is
                        raise
                    except Exception as exc:
                        # a blocked network is common in locked-down environments;
                        # give actionable egress guidance rather than an opaque name
                        if _is_connection_error(exc):
                            raise TranscriptionError(_NO_EGRESS_MSG) from None
                        # sanitize: an API/library error could echo request content
                        raise TranscriptionError(
                            f"transcription failed ({type(exc).__name__})"
                        ) from None
                    row["transcript"] = text
                    row["duration_seconds"] = dur
                    stats["transcribed"] += 1
                    fresh = True
                    billed_seconds += dur
                    if cache_conn is not None:
                        cache_conn.execute(
                            "INSERT OR REPLACE INTO transcripts VALUES (?,?,?)",
                            (key, backend, text))
                        cache_conn.commit()
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
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["file", "transcript", "backend",
                                              "duration_seconds", "status"])
            w.writeheader()
            for r in rows:
                w.writerow(r)
    finally:
        if cache_conn is not None:
            cache_conn.close()
    stats["backend"] = backend
    stats["output_path"] = output_path

    # actual spend: bill on the audio minutes actually sent to OpenAI this run
    # (cache hits are free and record nothing). Billed on each file's measured
    # duration; a chunked long file re-sends a ~1s overlap per seam, so this is a
    # close lower bound on true billed minutes, not exact.
    if billed_seconds > 0:
        actual_usd = _billed_minutes(billed_seconds) * spec["usd_per_min"]
        units = f"{billed_seconds / 60:.1f} audio-min"
        spend = usage_ledger.record("transcribe", spec["id"], units, actual_usd)
    else:
        s = usage_ledger.summary()
        spend = {"run_usd": 0.0, "run_usd_display": "$0.00",
                 "total_usd": s["total_usd"], "total_usd_display": s["total_usd_display"]}
    stats["actual_usd"] = spend["run_usd"]
    stats["actual_usd_display"] = spend["run_usd_display"]
    stats["total_spend_usd"] = spend["total_usd"]
    stats["total_spend_usd_display"] = spend["total_usd_display"]
    return stats


def _main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(
        description="Transcribe audio via OpenAI. Run 'estimate' first to see cost "
                    "and the privacy warning, then 'transcribe --confirm'. Long "
                    "files are chunked automatically.",
        epilog="Examples:\n"
               "  python transcription.py estimate interview.mp3\n"
               "  python transcription.py transcribe interview.mp3 \\\n"
               "      --output transcripts.csv --cache transcription-cache.db --confirm\n"
               "Output CSV columns: file, transcript, backend, duration_seconds, status.\n"
               "Needs ffmpeg/ffprobe on PATH (duration + chunking).",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    pe = sub.add_parser("estimate", help="show duration, approx cost, and the PII warning")
    pe.add_argument("audio_paths", nargs="+", help="one or more audio file paths")
    pe.add_argument("--model", default=None, help="fast (default) | accurate | whisper | model id")
    pt = sub.add_parser("transcribe", help="transcribe the audio and write a results CSV")
    pt.add_argument("audio_paths", nargs="+", help="one or more audio file paths")
    pt.add_argument("--output", required=True, help="path for the results CSV")
    pt.add_argument("--model", default=None,
                    help="fast (default, gpt-4o-mini-transcribe) | accurate | whisper | model id")
    pt.add_argument("--cache", default=None, help="optional SQLite cache path so re-runs are free")
    pt.add_argument("--confirm", action="store_true", help="required: confirms you accepted the cost/PII")
    args = p.parse_args(argv)

    if args.cmd == "estimate":
        print(json.dumps(estimate_cost(args.audio_paths, args.model), indent=2))
        return 0
    if args.cmd == "transcribe":
        if not args.confirm:
            print("Refusing to transcribe without --confirm. Run 'estimate' first "
                  "and confirm the cost with the user.", file=sys.stderr)
            return 1
        import openai_auth
        openai_auth.configure_openai()
        print(json.dumps(transcribe_files(
            args.audio_paths, args.output, model=args.model,
            cache_path=args.cache, confirm=True), indent=2))
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1:]))

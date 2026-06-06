"""Transcribe audio files via Google Cloud Speech-to-Text.

This supports the audio-transcription workflow described in
``references/audio-transcription.md``. SurveyCTO audio captures (audio-audit
recordings, open-ended voice responses) are sensitive: they contain
respondents' voices and often PII. Like user-data translation, the content must
not pass through the agent's context. This module reads the audio bytes and
sends them straight to Google Cloud Speech-to-Text from a script, writing
transcripts to a file the agent reports on but does not ingest cell-by-cell.

It deliberately reuses the same credential handling as translation: call
``google_cloud_auth.configure_google_auth()`` once before transcribing. The
agent never opens the service-account file (see
``references/google-cloud-credentials.md``).

Safety/efficiency features mirror translation.py:

* **Cost gate.** :func:`transcribe_files` refuses to run unless ``confirm=True``.
  Call :func:`estimate_cost` first and confirm with the user. Speech-to-Text is
  billed per 15 seconds of audio (rounded up per file).
* **Caching.** With a ``cache_path``, transcripts are memoized in SQLite keyed
  on ``(sha256(file_bytes), language_code, model)``. Re-running over the same
  files is free. The cache holds transcript text (sensitive); it is covered by
  the skill ``.gitignore`` template.
* **Never overwrite.** Output is a new CSV; the source audio is never modified.

Dependency injection: the actual Google call is isolated behind a small adapter
exposing ``transcribe(content, language_code, encoding, sample_rate, model) ->
{"transcript": str, "confidence": float}``. When no ``client`` is injected, a
real adapter over ``google.cloud.speech`` is built lazily, so this module
imports without the Google packages and the surrounding logic (duration, cost,
cache, CSV) is unit-testable offline with a fake adapter.

Standard library only at import time (``csv``, ``sqlite3``, ``hashlib``,
``wave``); ``google-cloud-speech`` is required only to reach the API. Audio
duration is read from WAV headers via the stdlib ``wave`` module, or via
``ffprobe`` if it is on PATH; otherwise it is reported as unknown so the agent
can ask the user.

CLI::

    python transcription.py estimate r1.wav r2.wav --language en-US
    python transcription.py transcribe r1.wav r2.wav --language en-US \\
        --output transcripts.csv --cache transcription-cache.db --confirm
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import wave
from pathlib import Path

# Standard model billing: USD per 15-second increment, rounded up per file.
_USD_PER_15_SEC = 0.016
# Free tier: 60 minutes per month (standard model).
_FREE_TIER_SECONDS = 60 * 60
# Inline content limit for the Speech-to-Text API (~10 MB). Larger files must
# go through Google Cloud Storage, which is out of scope for this helper.
_MAX_INLINE_BYTES = 10 * 1024 * 1024

# Map common audio extensions to Speech-to-Text encoding names. WAV and FLAC
# carry their format in the header, so the API can auto-detect; we still pass a
# hint where it is unambiguous.
_EXT_TO_ENCODING = {
    ".wav": "LINEAR16",
    ".flac": "FLAC",
    ".mp3": "MP3",
    ".ogg": "OGG_OPUS",
    ".opus": "OGG_OPUS",
    ".webm": "WEBM_OPUS",
    ".amr": "AMR",
}

_PII_WARNING = (
    "PRIVACY: the selected audio will be sent to Google Cloud Speech-to-Text (a "
    "third-party service). Audio recordings carry respondents' voices and often "
    "spoken PII (names, locations). Confirm this transfer is acceptable under "
    "the user's data-governance rules before transcribing."
)


def _audio_duration_seconds(path: str) -> float | None:
    """Return audio duration in seconds, or ``None`` if it can't be determined.

    Uses the stdlib ``wave`` module for ``.wav`` files. For other formats, uses
    ``ffprobe`` if available. Returns ``None`` when neither applies, so the
    caller can flag the file and ask the user.
    """
    ext = Path(path).suffix.lower()
    if ext == ".wav":
        try:
            with wave.open(path, "rb") as w:
                frames = w.getnframes()
                rate = w.getframerate()
                if rate:
                    return frames / float(rate)
        except (wave.Error, EOFError, OSError):
            return None
    if shutil.which("ffprobe"):
        try:
            out = subprocess.run(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-show_entries",
                    "format=duration",
                    "-of",
                    "default=noprint_wrappers=1:nokey=1",
                    "--",
                    path,
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )
            value = out.stdout.strip()
            if value:
                return float(value)
        except (subprocess.SubprocessError, ValueError, OSError):
            return None
    return None


def _billed_increments(duration_seconds: float) -> int:
    """Number of 15-second increments billed (rounded up, minimum 1)."""
    import math

    return max(1, math.ceil(duration_seconds / 15.0))


def estimate_cost(audio_paths: list[str], model: str = "default") -> dict:
    """Estimate the cost of transcribing the given audio files.

    :param audio_paths: Paths to audio files.
    :param model: Speech-to-Text model name (recorded for context).
    :returns: Dict with ``known_seconds`` (summed duration of files whose
        duration could be determined), ``estimated_usd`` (for those files),
        ``within_free_tier`` (naive: this run alone, vs the 60-min/month free
        tier), ``files`` (count), ``unknown_duration`` (list of paths whose
        duration could not be determined; their cost is not included), ``model``,
        and ``pii_warning``.
    """
    known_seconds = 0.0
    unknown: list[str] = []
    usd = 0.0
    for path in audio_paths:
        if not os.path.isfile(path):
            unknown.append(path)
            continue
        duration = _audio_duration_seconds(path)
        if duration is None:
            unknown.append(path)
            continue
        known_seconds += duration
        usd += _billed_increments(duration) * _USD_PER_15_SEC

    return {
        "known_seconds": round(known_seconds, 2),
        "estimated_usd": round(usd, 4),
        "within_free_tier": known_seconds <= _FREE_TIER_SECONDS,
        "files": len(audio_paths),
        "unknown_duration": unknown,
        "model": model,
        "pii_warning": _PII_WARNING,
    }


class _GoogleSpeechAdapter:
    """Adapter over ``google.cloud.speech``. Built lazily; needs the package."""

    def __init__(self):
        from google.cloud import speech  # noqa: PLC0415

        self._speech = speech
        self._client = speech.SpeechClient()

    def transcribe(
        self,
        content: bytes,
        language_code: str,
        encoding: str | None,
        sample_rate: int | None,
        model: str,
    ) -> dict:
        speech = self._speech
        config_kwargs = {"language_code": language_code}
        if encoding and encoding != "LINEAR16" and encoding != "FLAC":
            # WAV/FLAC carry encoding in the header; for the rest pass a hint.
            config_kwargs["encoding"] = getattr(
                speech.RecognitionConfig.AudioEncoding, encoding
            )
        if sample_rate:
            config_kwargs["sample_rate_hertz"] = sample_rate
        if model and model != "default":
            config_kwargs["model"] = model
        config = speech.RecognitionConfig(**config_kwargs)
        audio = speech.RecognitionAudio(content=content)
        # long_running_recognize is used with inline content (not a GCS URI) so
        # that recordings longer than the synchronous recognize() 1-minute audio
        # cap still work. The ~10 MB inline byte limit still applies and is
        # enforced by the caller; nothing here is uploaded to Cloud Storage.
        operation = self._client.long_running_recognize(config=config, audio=audio)
        response = operation.result()
        parts = []
        confidences = []
        for result in response.results:
            if result.alternatives:
                alt = result.alternatives[0]
                if alt.transcript and alt.transcript.strip():
                    # Only count confidence for results that contributed text,
                    # so an empty alternative does not skew the average.
                    parts.append(alt.transcript)
                    confidences.append(getattr(alt, "confidence", 0.0))
        transcript = " ".join(p.strip() for p in parts if p).strip()
        confidence = (
            round(sum(confidences) / len(confidences), 4) if confidences else 0.0
        )
        return {"transcript": transcript, "confidence": confidence}


def _get_adapter(client):
    return client if client is not None else _GoogleSpeechAdapter()


def _as_float(value) -> float:
    """Coerce a confidence value to float, defaulting to 0.0 on bad input.

    Guards against an adapter returning a non-numeric confidence, which would
    otherwise raise inside the cache write or output formatting and surface the
    value in an error message.
    """
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _cache_connect(cache_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(cache_path)
    try:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS transcripts ("
            "file_hash TEXT NOT NULL, "
            "language_code TEXT NOT NULL, "
            "model TEXT NOT NULL, "
            "transcript TEXT NOT NULL, "
            "confidence REAL NOT NULL, "
            "PRIMARY KEY (file_hash, language_code, model))"
        )
    except Exception:
        # An unusable cache path must not leak the just-opened connection.
        conn.close()
        raise
    return conn


def _file_hash(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def transcribe_file(
    audio_path: str,
    language_code: str,
    model: str = "default",
    client=None,
    confirm: bool = False,
) -> dict:
    """Transcribe a single audio file.

    :param audio_path: Path to the audio file.
    :param language_code: BCP-47 language code (e.g. ``en-US``, ``sw-KE``).
    :param model: Speech-to-Text model name.
    :param client: Optional adapter (see module docstring).
    :param confirm: Must be ``True`` to run. The cost gate: this makes a billed
        Speech-to-Text call, so call :func:`estimate_cost` and confirm with the
        user first, exactly as for :func:`transcribe_files`.
    :returns: Dict with ``transcript``, ``confidence``, ``duration_seconds``
        (or ``None``), and ``status`` (``"ok"`` or an error token).
    :raises PermissionError: If ``confirm`` is not ``True``.
    :raises FileNotFoundError: If the audio file does not exist.
    :raises ValueError: If the file exceeds the inline size limit.
    """
    if not confirm:
        raise PermissionError(
            "transcribe_file requires confirm=True. Run estimate_cost(), show "
            "the user the cost and PII warning, and only proceed after explicit "
            "confirmation."
        )
    if not os.path.isfile(audio_path):
        raise FileNotFoundError(f"No audio file at '{audio_path}'.")
    size = os.path.getsize(audio_path)
    if size > _MAX_INLINE_BYTES:
        raise ValueError(
            f"'{audio_path}' is {size} bytes, over the {_MAX_INLINE_BYTES}-byte "
            f"inline limit. Split it into shorter clips, or use Google Cloud "
            f"Storage (out of scope for this helper)."
        )
    with open(audio_path, "rb") as f:
        content = f.read()

    ext = Path(audio_path).suffix.lower()
    encoding = _EXT_TO_ENCODING.get(ext)
    sample_rate = None
    if ext == ".wav":
        try:
            with wave.open(audio_path, "rb") as w:
                sample_rate = w.getframerate()
        except (wave.Error, EOFError, OSError):
            sample_rate = None

    adapter = _get_adapter(client)
    try:
        result = adapter.transcribe(
            content, language_code, encoding, sample_rate, model
        )
    except Exception as exc:
        # Sanitize: an API error could echo request content.
        raise RuntimeError(
            f"transcription API call failed ({type(exc).__name__})"
        ) from None
    return {
        "transcript": result.get("transcript", ""),
        "confidence": _as_float(result.get("confidence", 0.0)),
        "duration_seconds": _audio_duration_seconds(audio_path),
        "status": "ok",
    }


def transcribe_files(
    audio_paths: list[str],
    language_code: str,
    output_path: str,
    model: str = "default",
    cache_path: str | None = None,
    client=None,
    confirm: bool = False,
) -> dict:
    """Transcribe audio files and write a CSV of results.

    The output CSV has columns: ``file``, ``transcript``, ``confidence``,
    ``duration_seconds``, ``status``. A file that errors is recorded with an
    error token in ``status`` and an empty transcript; processing continues.

    :param audio_paths: Paths to audio files.
    :param language_code: BCP-47 language code.
    :param output_path: Where to write the results CSV.
    :param model: Speech-to-Text model name.
    :param cache_path: Optional SQLite cache file path.
    :param client: Optional adapter (see module docstring).
    :param confirm: Must be ``True`` to run. The cost gate.
    :returns: Dict with ``transcribed`` (newly transcribed via API),
        ``cached`` (served from cache), ``failed``, and ``output_path``.
    :raises PermissionError: If ``confirm`` is not ``True``.
    """
    if not confirm:
        raise PermissionError(
            "transcribe_files requires confirm=True. Run estimate_cost(), show "
            "the user the cost and PII warning, and only proceed after explicit "
            "confirmation."
        )

    cache_conn = _cache_connect(cache_path) if cache_path else None
    adapter = None
    stats = {"transcribed": 0, "cached": 0, "failed": 0}
    rows_out: list[dict] = []

    try:
        for path in audio_paths:
            row = {
                "file": path,
                "transcript": "",
                "confidence": "",
                "duration_seconds": "",
                "status": "ok",
            }
            try:
                if not os.path.isfile(path):
                    raise FileNotFoundError(f"No audio file at '{path}'.")
                size = os.path.getsize(path)
                if size > _MAX_INLINE_BYTES:
                    raise ValueError(f"file over inline size limit ({size} bytes)")
                with open(path, "rb") as f:
                    content = f.read()
                key = _file_hash(content)

                cached = None
                if cache_conn is not None:
                    cur = cache_conn.execute(
                        "SELECT transcript, confidence FROM transcripts WHERE "
                        "file_hash=? AND language_code=? AND model=?",
                        (key, language_code, model),
                    )
                    hit = cur.fetchone()
                    if hit is not None:
                        cached = hit

                if cached is not None:
                    row["transcript"] = cached[0]
                    row["confidence"] = cached[1]
                    stats["cached"] += 1
                else:
                    ext = Path(path).suffix.lower()
                    encoding = _EXT_TO_ENCODING.get(ext)
                    sample_rate = None
                    if ext == ".wav":
                        try:
                            with wave.open(path, "rb") as w:
                                sample_rate = w.getframerate()
                        except (wave.Error, EOFError, OSError):
                            sample_rate = None
                    if adapter is None:
                        adapter = _get_adapter(client)
                    try:
                        result = adapter.transcribe(
                            content, language_code, encoding, sample_rate, model
                        )
                    except Exception as exc:
                        # Sanitize: an API error message could in principle echo
                        # request content. Record only the error type, never its
                        # text, in the output CSV.
                        raise RuntimeError(
                            f"transcription API call failed ({type(exc).__name__})"
                        ) from None
                    row["transcript"] = result.get("transcript", "")
                    row["confidence"] = _as_float(result.get("confidence", 0.0))
                    stats["transcribed"] += 1
                    if cache_conn is not None:
                        cache_conn.execute(
                            "INSERT OR REPLACE INTO transcripts VALUES (?,?,?,?,?)",
                            (
                                key,
                                language_code,
                                model,
                                row["transcript"],
                                row["confidence"],
                            ),
                        )
                        cache_conn.commit()
                row["duration_seconds"] = _audio_duration_seconds(path)
            except Exception as exc:  # noqa: BLE001 (record the error and continue)
                row["status"] = f"error: {type(exc).__name__}: {exc}"
                stats["failed"] += 1
            rows_out.append(row)

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=[
                    "file",
                    "transcript",
                    "confidence",
                    "duration_seconds",
                    "status",
                ],
            )
            writer.writeheader()
            for row in rows_out:
                writer.writerow(row)
    finally:
        if cache_conn is not None:
            cache_conn.close()

    stats["output_path"] = output_path
    return stats


def _main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Transcribe audio files.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    pe = sub.add_parser("estimate", help="estimate cost only")
    pe.add_argument("audio_paths", nargs="+")
    pe.add_argument("--model", default="default")

    pt = sub.add_parser("transcribe", help="transcribe audio files")
    pt.add_argument("audio_paths", nargs="+")
    pt.add_argument("--language", required=True, help="BCP-47, e.g. en-US")
    pt.add_argument("--output", required=True)
    pt.add_argument("--model", default="default")
    pt.add_argument("--cache", default=None)
    pt.add_argument(
        "--confirm",
        action="store_true",
        help="required; confirms the user accepted the estimated cost",
    )

    args = parser.parse_args(argv)

    if args.cmd == "estimate":
        print(json.dumps(estimate_cost(args.audio_paths, model=args.model), indent=2))
        return 0

    if args.cmd == "transcribe":
        if not args.confirm:
            print(
                "Refusing to transcribe without --confirm. Run 'estimate' "
                "first and confirm the cost with the user.",
                file=sys.stderr,
            )
            return 1
        import google_cloud_auth

        google_cloud_auth.configure_google_auth()
        result = transcribe_files(
            args.audio_paths,
            args.language,
            args.output,
            model=args.model,
            cache_path=args.cache,
            confirm=True,
        )
        print(json.dumps(result, indent=2))
        return 0

    return 2


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1:]))

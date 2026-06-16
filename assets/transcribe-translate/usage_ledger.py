"""Running record of actual OpenAI spend for the translate/transcribe helpers.

The pre-run estimate is a forecast; this module records what was *actually* billed
after each paid run and keeps a cumulative total, so the agent can report both
"this run cost $X" and "you have spent $Y so far". Only paid OpenAI calls are
recorded; fully-cached re-runs record nothing.

The ledger is a small JSON file at ``~/.surveycto-skill/spend-ledger.json``,
holding only costs and model names, never source text, transcripts, or the API
key.

The cumulative ``total_usd`` and per-operation totals are persisted directly (not
re-derived from the capped run history), so they stay exact after many runs. Reads
and writes tolerate a missing or corrupt file. The file is written atomically so a
crash cannot leave it truncated, but two runs finishing at the exact same instant
could still lose one update (cost display only, never the transcription output).

Standard library only.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

LEDGER_DIR = Path.home() / ".surveycto-skill"
LEDGER_PATH = LEDGER_DIR / "spend-ledger.json"

_MAX_RUNS_KEPT = 200  # bound the per-run history; persisted totals stay exact regardless


def usd_display(usd: float) -> str:
    """Human-readable cost so a sub-cent amount never reads as a flat $0.00."""
    if usd <= 0:
        return "$0.00"
    if usd < 0.01:
        return "< $0.01"
    return f"${usd:.2f}"


def _num(value, default: float = 0.0) -> float:
    """Coerce a ledger value to a float, never raising on a bad/edited file."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _empty() -> dict:
    return {"total_usd": 0.0, "by_operation": {}, "runs": []}


def _load() -> dict:
    """Load the ledger, tolerating a missing, corrupt, or hand-edited file.

    Every numeric field is coerced defensively so a malformed value (e.g. a string
    where a number is expected) can never raise into the calling work.
    """
    if not LEDGER_PATH.is_file():
        return _empty()
    try:
        with open(LEDGER_PATH, encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return _empty()
    except (OSError, ValueError):
        return _empty()
    total = _num(data.get("total_usd"))
    by_op_raw = data.get("by_operation")
    by_op = {str(k): _num(v) for k, v in by_op_raw.items()} if isinstance(by_op_raw, dict) else {}
    runs = data.get("runs")
    return {"total_usd": total, "by_operation": by_op,
            "runs": runs if isinstance(runs, list) else []}


def record(operation: str, model: str, units: str, usd: float) -> dict:
    """Append one paid run to the ledger and return a spend summary.

    :param operation: ``"translate"`` or ``"transcribe"``.
    :param model: The model id the run billed against.
    :param units: Short human description of what was billed (e.g. "1,240 tokens"
        or "7.8 audio-min").
    :param usd: The run's actual cost in USD.
    :returns: ``{"run_usd", "run_usd_display", "total_usd", "total_usd_display"}``.
    """
    usd = max(0.0, _num(usd))
    data = _load()
    data["total_usd"] = round(data["total_usd"] + usd, 6)
    data["by_operation"][operation] = round(data["by_operation"].get(operation, 0.0) + usd, 6)
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "operation": operation,
        "model": model,
        "units": units,
        "usd": round(usd, 6),
    }
    data["runs"] = (data["runs"] + [entry])[-_MAX_RUNS_KEPT:]
    try:
        LEDGER_DIR.mkdir(parents=True, exist_ok=True)
        # atomic write: a crash or interleaved run can never leave a torn file
        tmp = LEDGER_PATH.with_name(LEDGER_PATH.name + ".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, LEDGER_PATH)
        try:
            os.chmod(LEDGER_PATH, 0o600)
        except OSError:
            pass
    except OSError:
        pass  # a ledger we cannot persist must never break the actual work
    return {
        "run_usd": round(usd, 6),
        "run_usd_display": usd_display(usd),
        "total_usd": data["total_usd"],
        "total_usd_display": usd_display(data["total_usd"]),
    }


def summary() -> dict:
    """Return the cumulative spend without recording anything."""
    data = _load()
    total = round(data["total_usd"], 6)
    by_op = {k: round(v, 6) for k, v in data["by_operation"].items()}
    return {
        "total_usd": total,
        "total_usd_display": usd_display(total),
        "by_operation": by_op,
        "runs_recorded": len(data["runs"]),
        "ledger_path": str(LEDGER_PATH),
    }


def _main(argv: list[str]) -> int:
    import sys
    if argv and argv[0] in ("-h", "--help"):
        print("Usage:\n  python3 usage_ledger.py show    (print cumulative OpenAI spend)\n"
              "  python3 usage_ledger.py reset   (clear the spend history)")
        return 0
    if argv and argv[0] == "reset":
        try:
            LEDGER_PATH.unlink(missing_ok=True)
        except OSError:
            pass
        print("Spend ledger cleared.")
        return 0
    s = summary()
    print(f"OpenAI spend recorded by this skill: {s['total_usd_display']} "
          f"({s['runs_recorded']} run(s) tracked)")
    for op, amt in sorted(s["by_operation"].items()):
        print(f"  {op}: {usd_display(amt)}")
    print(f"Ledger: {s['ledger_path']}")
    return 0


if __name__ == "__main__":
    import sys
    raise SystemExit(_main(sys.argv[1:]))

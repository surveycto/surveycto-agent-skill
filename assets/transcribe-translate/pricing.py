"""OpenAI rate table for translation and transcription, kept as data, not code.

OpenAI publishes no programmatic pricing endpoint (verified), so the per-token and
per-minute rates that turn usage counts into dollars live in ``pricing.json`` next
to this module, each stamped with the date last verified and the pricing-page URL.
This keeps them refreshable without a code change and lets every estimate report
how current the numbers are.

Refresh flow (agent-orchestrated; see the primers). The agent asks the user for
permission to check current prices online. If granted, it reads ``source_url``
(the OpenAI pricing page) and writes the values back with ``pricing.py
set-transcription`` / ``set-translation`` (which validate inputs and stamp
``last_verified``); if declined, the stored values are used as-is. Either way the
output reports ``rates_as_of`` and ``rates_source``.

The spend math is exact: token counts come from the API response, the per-token
rate from this table. The only judgement step, reading a number off the pricing
page during a refresh, is user-gated and falls back to the stored value. If
``pricing.json`` is missing or malformed, the built-in copy below loads instead
(reported as ``rates_source: "builtin"``), so a bad file degrades to known rates
rather than crashing a paid run.

Standard library only.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path

# Fail-safe copy of the shipped rates, kept byte-for-byte in sync with
# pricing.json (a test asserts this). Loaded only when the JSON file cannot be
# read or does not validate, so the table always loads.
_BUILTIN: dict = {
    "last_verified": "2026-06-14",
    "source_url": "https://openai.com/api/pricing/",
    "currency": "USD",
    "transcription": {
        "gpt-4o-mini-transcribe": {"billing": "token", "in_per_mtok": 1.25, "out_per_mtok": 5.0, "est_per_min": 0.003},
        "gpt-4o-transcribe": {"billing": "token", "in_per_mtok": 2.5, "out_per_mtok": 10.0, "est_per_min": 0.006},
        "whisper-1": {"billing": "minute", "usd_per_min": 0.006},
    },
    "translation": {
        "gpt-4.1-nano": {"in_per_mtok": 0.1, "out_per_mtok": 0.4},
        "gpt-4o-mini": {"in_per_mtok": 0.15, "out_per_mtok": 0.6},
    },
}

_REQUIRED_FIELDS = {
    "token": ("in_per_mtok", "out_per_mtok", "est_per_min"),
    "minute": ("usd_per_min",),
}


def _pricing_path() -> Path:
    return Path(__file__).resolve().parent / "pricing.json"


def _validate(data: dict) -> None:
    """Raise ValueError unless ``data`` has the expected shape and every built-in
    model is present with the numeric fields its billing mode requires.

    Completeness is enforced so a valid file is always a full table; lookups never
    silently fall back to the built-in for an individual model, which would make
    ``rates_source`` a lie.
    """
    if not isinstance(data, dict):
        raise ValueError("pricing data is not an object")
    if not isinstance(data.get("last_verified"), str) or not data["last_verified"]:
        raise ValueError("pricing data missing 'last_verified'")
    for kind in ("transcription", "translation"):
        table = data.get(kind)
        if not isinstance(table, dict):
            raise ValueError(f"pricing data missing '{kind}' table")
        for model_id, builtin_rate in _BUILTIN[kind].items():
            rate = table.get(model_id)
            if not isinstance(rate, dict):
                raise ValueError(f"pricing data missing {kind} model '{model_id}'")
            billing = rate.get("billing", builtin_rate.get("billing"))
            required = _REQUIRED_FIELDS["minute" if billing == "minute" else "token"] \
                if kind == "transcription" else ("in_per_mtok", "out_per_mtok")
            for field in required:
                v = rate.get(field)
                if not isinstance(v, (int, float)) or isinstance(v, bool) or v < 0:
                    raise ValueError(
                        f"{kind} model '{model_id}' has a bad '{field}' value")


def load() -> tuple[dict, dict]:
    """Return ``(data, provenance)``.

    ``data`` is the validated pricing table (from ``pricing.json`` when readable
    and valid, otherwise the built-in copy). ``provenance`` is
    ``{"source": "file"|"builtin", "last_verified": ..., "source_url": ...}`` so
    callers can report how current the rates are.
    """
    path = _pricing_path()
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        _validate(data)
    except (OSError, ValueError, json.JSONDecodeError):
        data = json.loads(json.dumps(_BUILTIN))  # deep copy
        return data, {"source": "builtin",
                      "last_verified": _BUILTIN["last_verified"],
                      "source_url": _BUILTIN["source_url"]}
    return data, {"source": "file",
                  "last_verified": data["last_verified"],
                  "source_url": data.get("source_url", _BUILTIN["source_url"])}


def rate_for(data: dict, kind: str, model_id: str) -> dict:
    """Return the rate dict for one model. Fails closed on an unknown model.

    :param data: A table from :func:`load`.
    :param kind: ``"transcription"`` or ``"translation"``.
    :param model_id: The OpenAI model id (e.g. ``gpt-4o-transcribe``).
    """
    table = data.get(kind, {})
    if model_id in table:
        return table[model_id]
    known = ", ".join(sorted(table)) or "(none)"
    raise ValueError(
        f"No pricing for {kind} model '{model_id}'. Known: {known}. Add it to "
        "pricing.json (with its rate) so the cost estimate stays accurate.")


# ---- refresh (writes pricing.json) ---------------------------------------

def _write(data: dict) -> None:
    """Validate then atomically write the table to pricing.json (owner-only)."""
    _validate(data)
    path = _pricing_path()
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.write("\n")
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _set_rate(kind: str, model_id: str, fields: dict, as_of: str) -> dict:
    """Update one model's rate in pricing.json and stamp ``last_verified``.

    Refuses an unknown model id (refresh updates known models, never invents one).
    Validates the supplied fields against the model's billing mode and requires at
    least one applicable field, so ``last_verified`` is never restamped without a
    rate that actually applies. ``as_of`` must be a real ``YYYY-MM-DD`` date so the
    stamped provenance stays trustworthy. Returns the provenance dict.
    """
    try:
        datetime.strptime(as_of, "%Y-%m-%d")
    except (ValueError, TypeError):
        raise ValueError(
            f"--as-of must be a calendar date in YYYY-MM-DD form (got '{as_of}'). "
            "Use the date you verified the rate.") from None
    data, _ = load()
    table = data.setdefault(kind, {})
    if model_id not in table:
        known = ", ".join(sorted(table)) or "(none)"
        raise ValueError(
            f"Unknown {kind} model '{model_id}'. Known: {known}. Refresh updates "
            "existing models; do not add new ones here.")
    rate = dict(table[model_id])
    # which fields apply depends on how this model is billed
    if kind == "transcription":
        billing = rate.get("billing", "minute")
        allowed = ({"in_per_mtok", "out_per_mtok", "est_per_min"}
                   if billing == "token" else {"usd_per_min"})
    else:  # translation models are all token-billed
        allowed = {"in_per_mtok", "out_per_mtok"}
    provided = {k: v for k, v in fields.items() if v is not None}
    irrelevant = sorted(set(provided) - allowed)
    if irrelevant:
        raise ValueError(
            f"Field(s) {irrelevant} do not apply to {kind} model '{model_id}' "
            f"(allowed: {sorted(allowed)}). Refusing to write.")
    if not provided:
        raise ValueError(
            f"No applicable rate field given for {kind} model '{model_id}' (need at "
            f"least one of {sorted(allowed)}). Refusing to restamp last_verified "
            "without a rate change.")
    for k, v in provided.items():
        rate[k] = float(v)
    table[model_id] = rate
    data["last_verified"] = as_of
    _write(data)
    return {"source": "file", "last_verified": as_of,
            "source_url": data.get("source_url", _BUILTIN["source_url"])}


def _main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(
        description="Show or refresh the OpenAI rate table used for cost estimates "
                    "and spend reporting. 'show' prints current rates and how "
                    "current they are; 'set-*' updates a rate after you read it "
                    "from the pricing page (pass --as-of with today's date).",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("show", help="print the rate table and its provenance as JSON")

    pst = sub.add_parser("set-transcription", help="update a transcription model rate")
    pst.add_argument("model_id", help="e.g. gpt-4o-transcribe")
    pst.add_argument("--in-per-mtok", type=float, default=None, help="USD per 1M input tokens (token-billed models)")
    pst.add_argument("--out-per-mtok", type=float, default=None, help="USD per 1M output tokens (token-billed models)")
    pst.add_argument("--est-per-min", type=float, default=None, help="USD per audio minute, pre-run estimate (token-billed models)")
    pst.add_argument("--usd-per-min", type=float, default=None, help="USD per audio minute (whisper-1, duration-billed)")
    pst.add_argument("--as-of", required=True, help="date you verified the rate, YYYY-MM-DD")

    psl = sub.add_parser("set-translation", help="update a translation model rate")
    psl.add_argument("model_id", help="e.g. gpt-4.1-nano")
    psl.add_argument("--in-per-mtok", type=float, default=None, help="USD per 1M input tokens")
    psl.add_argument("--out-per-mtok", type=float, default=None, help="USD per 1M output tokens")
    psl.add_argument("--as-of", required=True, help="date you verified the rate, YYYY-MM-DD")

    args = p.parse_args(argv)
    if args.cmd == "show":
        data, prov = load()
        print(json.dumps({"provenance": prov, **data}, indent=2, ensure_ascii=False))
        return 0
    if args.cmd == "set-transcription":
        prov = _set_rate("transcription", args.model_id, {
            "in_per_mtok": args.in_per_mtok, "out_per_mtok": args.out_per_mtok,
            "est_per_min": args.est_per_min, "usd_per_min": args.usd_per_min,
        }, args.as_of)
        print(json.dumps(prov, indent=2))
        return 0
    if args.cmd == "set-translation":
        prov = _set_rate("translation", args.model_id, {
            "in_per_mtok": args.in_per_mtok, "out_per_mtok": args.out_per_mtok,
        }, args.as_of)
        print(json.dumps(prov, indent=2))
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1:]))

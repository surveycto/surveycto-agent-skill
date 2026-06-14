"""Detect machine specs and recommend a local Whisper model size.

Only relevant to the local transcription provider (``--provider local``), whose
speed and feasibility depend on the hardware. The cloud (OpenAI) path does not
need this. Run it before choosing ``--local-model`` so the choice fits the
machine:

    python3 system_check.py            # human-readable specs + recommendation
    python3 system_check.py --json     # machine-readable, for the agent

It detects OS, CPU cores, total RAM, and whether an NVIDIA GPU (CUDA) is present,
on Windows, Linux, and macOS, then maps that to a recommended faster-whisper
model. faster-whisper uses CTranslate2, which accelerates on NVIDIA CUDA GPUs but
runs CPU-only everywhere else (including Apple Silicon, which has no Metal
backend), so the recommendation keys off "NVIDIA GPU or not" plus RAM and cores.

Standard library only; detection degrades gracefully when a value cannot be read.
"""

from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import sys

# Model menu, smallest to largest, with the approximate RAM each needs (int8)
# and the measured download size. Mirrors references/audio-transcription.md.
_MODELS = [
    {"name": "tiny", "min_ram_gb": 1, "download": "~75 MB"},
    {"name": "base", "min_ram_gb": 1, "download": "~145 MB"},
    {"name": "small", "min_ram_gb": 2, "download": "464 MB"},
    {"name": "medium", "min_ram_gb": 5, "download": "1.4 GB"},
    {"name": "large-v3", "min_ram_gb": 8, "download": "2.9 GB"},
]


def _total_ram_gb() -> float | None:
    """Total physical RAM in GB, or None if it cannot be determined."""
    # Linux and most macOS Python builds expose this via sysconf.
    try:
        pages = os.sysconf("SC_PHYS_PAGES")
        page_size = os.sysconf("SC_PAGE_SIZE")
        if pages > 0 and page_size > 0:
            return pages * page_size / 1e9
    except (ValueError, OSError, AttributeError):
        pass
    system = platform.system()
    if system == "Darwin":
        try:
            out = subprocess.run(["sysctl", "-n", "hw.memsize"],
                                 capture_output=True, text=True, timeout=10)
            return int(out.stdout.strip()) / 1e9
        except (subprocess.SubprocessError, ValueError, OSError):
            pass
    if system == "Linux":
        try:
            with open("/proc/meminfo", encoding="utf-8") as f:
                for line in f:
                    if line.startswith("MemTotal:"):
                        return int(line.split()[1]) * 1024 / 1e9  # kB -> bytes
        except (OSError, ValueError, IndexError):
            pass
    if system == "Windows":
        try:
            import ctypes

            class _MemStatus(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_ulong),
                            ("dwMemoryLoad", ctypes.c_ulong),
                            ("ullTotalPhys", ctypes.c_ulonglong),
                            ("ullAvailPhys", ctypes.c_ulonglong),
                            ("ullTotalPageFile", ctypes.c_ulonglong),
                            ("ullAvailPageFile", ctypes.c_ulonglong),
                            ("ullTotalVirtual", ctypes.c_ulonglong),
                            ("ullAvailVirtual", ctypes.c_ulonglong),
                            ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]

            stat = _MemStatus()
            stat.dwLength = ctypes.sizeof(_MemStatus)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)):
                return stat.ullTotalPhys / 1e9
        except Exception:  # noqa: BLE001 - any ctypes/platform quirk -> unknown
            pass
    return None


def _has_nvidia_gpu() -> bool:
    """True if an NVIDIA GPU is detectable (nvidia-smi present and responsive)."""
    if shutil.which("nvidia-smi") is None:
        return False
    try:
        return subprocess.run(["nvidia-smi"], capture_output=True,
                              timeout=15).returncode == 0
    except (subprocess.SubprocessError, OSError):
        return False


def detect_specs() -> dict:
    """Detect OS, architecture, CPU cores, RAM, and NVIDIA-GPU presence."""
    system = platform.system()
    machine = platform.machine()
    ram = _total_ram_gb()
    apple_silicon = system == "Darwin" and machine.lower() in ("arm64", "aarch64")
    return {
        "os": system or "unknown",
        "arch": machine or "unknown",
        "cpu_cores": os.cpu_count(),
        "ram_gb": round(ram, 1) if ram else None,
        "has_nvidia_gpu": _has_nvidia_gpu(),
        "apple_silicon": apple_silicon,
        "has_ffmpeg": shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None,
    }


def recommend_model(specs: dict) -> dict:
    """Recommend a local model from detected specs.

    :returns: ``{"recommended", "rationale", "feasible", "avoid", "accelerator"}``.
    """
    ram = specs.get("ram_gb")
    cores = specs.get("cpu_cores") or 1
    gpu = bool(specs.get("has_nvidia_gpu"))
    # When RAM is unknown, assume a conservative 4 GB so we never over-recommend.
    eff_ram = ram if ram is not None else 4.0

    if gpu:
        return {
            "recommended": "large-v3",
            "accelerator": "NVIDIA GPU (CUDA)",
            "rationale": "An NVIDIA GPU was detected; CTranslate2 uses CUDA, so the "
                         "largest, most accurate model runs comfortably.",
            "feasible": ["tiny", "base", "small", "medium", "large-v3"],
            "avoid": [],
        }

    # CPU-only path (includes Apple Silicon: no Metal backend in CTranslate2).
    accel = "CPU only (Apple Silicon: GPU not used by CTranslate2)" if specs.get(
        "apple_silicon") else "CPU only"
    if eff_ram >= 16 and cores >= 8:
        rec, feasible, avoid = "small", ["tiny", "base", "small", "medium"], ["large-v3"]
        note = ("Plenty of RAM and cores: `small` is the best speed/quality balance; "
                "`medium` is feasible if you accept roughly 3x slower; `large-v3` is "
                "slow on CPU (near real time) and best left to a GPU machine.")
    elif eff_ram >= 8:
        rec, feasible, avoid = "small", ["tiny", "base", "small"], ["medium", "large-v3"]
        note = ("`small` runs well; `medium`/`large-v3` are heavy for this RAM/CPU and "
                "will be slow, so avoid them unless you are patient.")
    elif eff_ram >= 4:
        rec, feasible, avoid = "base", ["tiny", "base"], ["small", "medium", "large-v3"]
        note = ("Limited RAM: prefer `base` (or `tiny` for speed); larger models may "
                "swap or run very slowly.")
    else:
        rec, feasible, avoid = "tiny", ["tiny"], ["base", "small", "medium", "large-v3"]
        note = ("Low RAM: use `tiny`. For better accuracy, consider the cloud provider "
                "(no local model needed) instead.")
    if ram is None:
        note += " (RAM could not be measured, so this is a conservative guess.)"
    return {
        "recommended": rec,
        "accelerator": accel,
        "rationale": note,
        "feasible": feasible,
        "avoid": avoid,
    }


def recommend_translation(specs: dict) -> dict:
    """Feasibility note for on-device translation (NLLB-200 distilled-600M).

    A single model (not a size ladder); CPU-bound (CTranslate2/torch get no Metal
    on Apple Silicon, CUDA on NVIDIA). It needs roughly 3 GB RAM at runtime.
    """
    ram = specs.get("ram_gb")
    eff_ram = ram if ram is not None else 4.0
    ok = eff_ram >= 4
    return {
        "model": "nllb-200-distilled-600M",
        "feasible": ok,
        "note": ("NLLB-600M (~3 GB RAM, ~4.6 GB download) runs on this machine; "
                 "an NVIDIA GPU speeds it up, CPU is fine for survey text."
                 if ok else
                 "Low RAM for NLLB-600M (~3 GB needed); prefer the cloud provider "
                 "for translation, or close other apps before running."),
    }


def assess() -> dict:
    """Detect specs and attach model recommendations (transcription + translation)."""
    specs = detect_specs()
    rec = recommend_model(specs)
    dl = next((m["download"] for m in _MODELS if m["name"] == rec["recommended"]), "?")
    rec["download"] = dl
    return {"specs": specs, "recommendation": rec,
            "translation": recommend_translation(specs)}


def _main(argv: list[str]) -> int:
    if argv and argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    result = assess()
    if argv and argv[0] == "--json":
        print(json.dumps(result, indent=2))
        return 0
    s, r = result["specs"], result["recommendation"]
    ram = f"{s['ram_gb']} GB" if s["ram_gb"] is not None else "unknown"
    print("Machine:")
    print(f"  OS / arch : {s['os']} / {s['arch']}")
    print(f"  CPU cores : {s['cpu_cores']}")
    print(f"  RAM       : {ram}")
    print(f"  NVIDIA GPU: {'yes' if s['has_nvidia_gpu'] else 'no'}")
    print(f"  ffmpeg    : {'found' if s['has_ffmpeg'] else 'MISSING (needed for transcription)'}")
    print(f"  Accelerator for local Whisper: {r['accelerator']}")
    print("\nRecommended local model:")
    print(f"  --local-model {r['recommended']}  (download {r['download']})")
    print(f"  {r['rationale']}")
    print(f"  Feasible: {', '.join(r['feasible'])}"
          + (f"   Avoid: {', '.join(r['avoid'])}" if r["avoid"] else ""))
    tr = result["translation"]
    print("\nOn-device translation (NLLB):")
    print(f"  model {tr['model']}: {tr['note']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1:]))

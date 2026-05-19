#!/usr/bin/env python3
"""Remove local-machine metadata from public XLSX assets."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from tempfile import NamedTemporaryFile
from zipfile import ZipFile


REPO_ROOT = Path(__file__).resolve().parents[1]
ASSET_DIR = REPO_ROOT / "assets"
PUBLIC_AUTHOR = "SurveyCTO"

CREATOR_RE = re.compile(r"<dc:creator>.*?</dc:creator>")
LAST_MODIFIED_BY_RE = re.compile(r"<cp:lastModifiedBy>.*?</cp:lastModifiedBy>")
ABSPATH_ALT_CONTENT_RE = re.compile(
    r"<mc:AlternateContent\b[^>]*>\s*"
    r"(?:<mc:Choice\b[^>]*>\s*)?"
    r"<x15ac:absPath\b[^>]*/>\s*"
    r"(?:</mc:Choice>\s*)?"
    r"</mc:AlternateContent>",
    re.DOTALL,
)
ABSPATH_TAG_RE = re.compile(r"<x15ac:absPath\b[^>]*/>")


def default_workbooks() -> list[Path]:
    return sorted(ASSET_DIR.rglob("*.xlsx"))


def sanitize_core_xml(data: bytes) -> tuple[bytes, bool]:
    text = data.decode("utf-8")
    original = text

    if CREATOR_RE.search(text):
        text = CREATOR_RE.sub(f"<dc:creator>{PUBLIC_AUTHOR}</dc:creator>", text)

    if LAST_MODIFIED_BY_RE.search(text):
        text = LAST_MODIFIED_BY_RE.sub(
            f"<cp:lastModifiedBy>{PUBLIC_AUTHOR}</cp:lastModifiedBy>", text
        )

    return text.encode("utf-8"), text != original


def sanitize_workbook_xml(data: bytes) -> tuple[bytes, bool]:
    text = data.decode("utf-8")
    original = text
    text = ABSPATH_ALT_CONTENT_RE.sub("", text)
    text = ABSPATH_TAG_RE.sub("", text)
    return text.encode("utf-8"), text != original


def sanitize_workbook(path: Path) -> bool:
    changed = False

    with ZipFile(path, "r") as zin, NamedTemporaryFile(
        delete=False, dir=str(path.parent), suffix=".xlsx"
    ) as tmp:
        tmp_path = Path(tmp.name)

        with ZipFile(tmp, "w") as zout:
            for info in zin.infolist():
                data = zin.read(info.filename)

                if info.filename == "docProps/core.xml":
                    data, part_changed = sanitize_core_xml(data)
                    changed = changed or part_changed
                elif info.filename == "xl/workbook.xml":
                    data, part_changed = sanitize_workbook_xml(data)
                    changed = changed or part_changed

                zout.writestr(info, data)

    if changed:
        tmp_path.replace(path)
    else:
        tmp_path.unlink()

    return changed


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Remove author/path metadata that Excel may add to public XLSX assets."
    )
    parser.add_argument(
        "workbooks",
        nargs="*",
        type=Path,
        help="XLSX paths to sanitize. Defaults to every .xlsx under assets/.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    workbooks = args.workbooks or default_workbooks()

    if not workbooks:
        print("No XLSX assets found", file=sys.stderr)
        return 1

    for workbook in workbooks:
        if not workbook.exists():
            print(f"Missing workbook: {workbook}", file=sys.stderr)
            return 1
        if workbook.suffix.lower() != ".xlsx":
            print(f"Not an .xlsx file: {workbook}", file=sys.stderr)
            return 1

    changed_workbooks = [workbook for workbook in workbooks if sanitize_workbook(workbook)]

    if changed_workbooks:
        print("Sanitized XLSX assets:")
        for workbook in changed_workbooks:
            print(f"- {workbook}")
    else:
        print("No XLSX assets needed sanitizing")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Validate a SurveyCTO server dataset definition (.xml) before upload.

This helper supports the dataset-authoring workflow described in
``references/dataset-validation.md``. SurveyCTO's interactive console enforces a
set of rules when a dataset is created or edited, and the server rejects an
uploaded definition (or a publishing configuration) that breaks them. An agent
authoring dataset XML by hand cannot see those rules, so it tends to produce
definitions that look plausible but fail on upload or silently misbehave once a
form starts publishing into them.

This script re-implements those rules so the agent can validate and self-correct
locally, with no server round-trip. It works in two layers:

  1. Dataset-only checks (standard library ``xml.etree`` only): element order and
     required children, enumerations, id/title/idFormatOptions/caseManagementOptions
     value rules, fieldNames rules, and the field-map / data-link rules.
  2. Form cross-reference checks (``openpyxl``): when the referenced form
     ``.xlsx`` files are supplied, each form is parsed into a field list of
     ``{name, type, repeated}`` matching how the server builds its publishing
     field list, and the field map is checked against the real fields (every
     mapped field exists, joining field exists and is inside a repeat group for
     long format, repeated fields carry the ``*`` suffix, etc.).

Usage::

    python validate_dataset.py my_dataset.xml
    python validate_dataset.py my_dataset.xml --form household.xlsx --form roster.xlsx
    python validate_dataset.py my_dataset.xml --json

Findings are reported in four tiers:

  - ``error``        the server (or its XSD) rejects this on upload, or a
                     publishing rule that breaks data collection. Must be fixed.
  - ``warning``      the server accepts the upload but behavior is degraded or a
                     console-level publishing rule will reject the config later.
  - ``recommendation`` best practice / console convention; not enforced.
  - ``cannot_verify`` a real rule that needs a live server (form deployment,
                     uniqueness in stored data, license, id collisions); surfaced
                     so a clean result is not mistaken for a guarantee.

The process exits non-zero when any ``error`` is present.

Standard library only, plus ``openpyxl`` (already a skill dependency) and only
when ``--form`` files are supplied. No network access; nothing is uploaded.

This script does NOT validate the XLSForm itself (use the XLSForm tooling for
that), and it cannot replace a real upload: the rules below are derived from the
SurveyCTO server source and can drift if that source changes. See the rule
manifest in the module body for the source citations behind each rule.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import zipfile
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Rule manifest (source citations, for re-derivation on drift)
#
# Derived from the SurveyCTO server source as of 2026-06. Key sources:
#   - dataset.xsd: scto-commons-utils .../datasets/xml/dataset.xsd
#       element order, required children, enumerations.
#   - DatasetValidationUtils.java: scto-server-modules .../dataset/utils/
#       idFormatOptions (prefix/suffix alphanumeric <=10, numberOfDigits 4..8),
#       caseManagementOptions (displayMode, table-view must include id).
#   - DatasetServiceImpl.java: scto-server-modules .../dataset/service/
#       id/title/type rules, joiningField-in-fieldMap on definition import,
#       uniqueRecordField forced to "id" for CASES/ENUMERATORS.
#   - DatasetManagerImpl.java: scto-server .../datasets/manager/
#       duplicate field mapping, joiningField REPLACE + maps-to-uniqueRecordField,
#       standard column sets, max field-name length, reserved "rowId".
#   - XFormManagerImpl.java: scto-server .../forms/manager/
#       long-format publishing requirements and the publishing field list.
#   - DatasetUtils.java / ServerConstants.java: standard column constants.
# Ticket coverage: SCTO-15028 (enumerator columns), SCTO-15073 (joiningField in
# field map), SCTO-15074 (same field mapped twice).
# ---------------------------------------------------------------------------

# Element order enforced by the XSD xs:sequence for <definition> and <dataLink>.
DEFINITION_ORDER = [
    "id", "title", "datasetType", "fieldNames", "formLinks", "dataLinks",
    "caseManagementOptions", "idFormatOptions", "discriminator",
    "uniqueRecordField", "allowOfflineUpdates",
]
DEFINITION_REQUIRED = ["id", "title", "datasetType"]

DATALINK_ORDER = [
    "dataLinkClass", "dataLinkType", "dataLinkState", "dataLinkFormat",
    "linkObjectId", "fieldMap", "joiningField", "relevanceField",
    "isAutoConfigured",
]
DATALINK_REQUIRED = ["dataLinkClass", "dataLinkType", "linkObjectId"]

# xs:all blocks: order-independent, only presence matters.
CASE_MGMT_REQUIRED = ["displayMode", "showFinalizedSentWhenTree", "showColumnsWhenTable"]
CASE_MGMT_OPTIONAL = ["otherUserCode", "entryMode", "enumeratorDatasetId"]
ID_FORMAT_REQUIRED = ["numberOfDigits"]
ID_FORMAT_OPTIONAL = ["prefix", "suffix", "allowCapitalLetters"]

DATASET_TYPES = {"SERVER", "CLIENT", "REPORT"}
DISCRIMINATORS = {"CASES", "ENUMERATORS", "DATA"}
DATALINK_CLASSES = {"FORM", "FUSION_TABLE", "SPREADSHEET"}
DATALINK_TYPES = {"INCOMING", "OUTGOING"}
DATALINK_STATES = {"ENABLED", "DISABLED"}
ENTRY_MODES = {"LIST", "ENTRY", "SCAN"}
UPDATE_LOGIC_ACTIONS = {"REPLACE", "ADD_TO_NUMERIC_VALUE", "CONCATENATE_TO_TEXT"}

DATALINK_FORMAT_WIDE = 0
DATALINK_FORMAT_LONG = 1

# Standard column sets the console creates. id/name (enum) and id/label/formids
# (cases) are functionally required; the rest are conventional.
ENUM_REQUIRED_COLUMNS = ["id", "name"]
ENUM_STANDARD_COLUMNS = ["id", "name", "users"]
CASES_REQUIRED_COLUMNS = ["id", "label", "formids"]
CASES_STANDARD_COLUMNS = ["id", "label", "formids", "users", "roles", "sortby", "enumerators"]

RESERVED_FIELD_NAMES = {"rowId"}
MAX_FIELD_NAME_LENGTH = 60

# Metadata fields the server UNCONDITIONALLY appends to a form's incoming
# publishing field list (FormUtils.addMetadataFields). They are valid field-map
# sources even though they are not rows in the survey sheet.
METADATA_FIELDS = [
    ("SubmissionDate", "datetime"),
    ("formdef_version", "text"),
    ("review_quality", "text"),
    ("KEY", "text"),
]
# Fields available only in some publishing contexts or only when the form itself
# declares them: formdef_id appears in outgoing-publishing summaries, not the
# incoming form-to-dataset feed; review_status only for reviewed submissions;
# instanceID/instanceName are meta rows a form may or may not define. When a
# field map names one of these and it is not found in the supplied form, warn
# rather than hard-error, since availability cannot be determined offline.
CONDITIONAL_META_FIELD_NAMES = {"formdef_id", "review_status", "instanceID", "instanceName"}

# XLSForm survey `type` leading token -> publishing field type string, mirroring
# the server's discoverElementType / dataType mapping. Notes are excluded; group
# and repeat containers are structural, not fields.
XLSFORM_TYPE_MAP = {
    "text": "text",
    "integer": "integer",
    "decimal": "decimal",
    "range": "integer",
    "date": "date",
    "time": "time",
    "datetime": "datetime",
    "dateTime": "datetime",
    "select_one": "select_one",
    "select_multiple": "select_multiple",
    "select_one_from_file": "select_one",
    "select_multiple_from_file": "select_multiple",
    "rank": "text",
    "calculate": "text",
    "geopoint": "geopoint",
    "geoshape": "geoshape",
    "geotrace": "geotrace",
    "barcode": "barcode",
    "image": "image",
    "audio": "audio",
    "background-audio": "audio",
    "video": "video",
    "file": "file",
    "acknowledge": "text",
    "hidden": "text",
    "username": "text",
    "phonenumber": "text",
    "deviceid": "text",
    "subscriberid": "text",
    "simserial": "text",
    "start": "datetime",
    "end": "datetime",
    "today": "date",
    "audit": "binary",
    "comments": "text",
    "text audit": "binary",
    "sensor_statistic": "text",
    "sensor_stream": "text",
}
# XLSForm types that never become a publishable field.
NON_FIELD_TYPES = {"note", "begin group", "end group", "begin_group", "end_group",
                   "begin repeat", "end repeat", "begin_repeat", "end_repeat"}


# ---------------------------------------------------------------------------
# Findings
# ---------------------------------------------------------------------------

ERROR = "error"
WARNING = "warning"
RECOMMENDATION = "recommendation"
CANNOT_VERIFY = "cannot_verify"

_SEVERITY_ORDER = {ERROR: 0, WARNING: 1, RECOMMENDATION: 2, CANNOT_VERIFY: 3}


class Finding:
    def __init__(self, severity: str, rule: str, message: str,
                 location: str = "", fix: str = "") -> None:
        self.severity = severity
        self.rule = rule
        self.message = message
        self.location = location
        self.fix = fix

    def as_dict(self) -> dict:
        return {
            "severity": self.severity,
            "rule": self.rule,
            "message": self.message,
            "location": self.location,
            "fix": self.fix,
        }


class Report:
    def __init__(self) -> None:
        self.findings: list[Finding] = []

    def add(self, severity: str, rule: str, message: str,
            location: str = "", fix: str = "") -> None:
        self.findings.append(Finding(severity, rule, message, location, fix))

    def error(self, rule, message, location="", fix=""):
        self.add(ERROR, rule, message, location, fix)

    def warning(self, rule, message, location="", fix=""):
        self.add(WARNING, rule, message, location, fix)

    def recommend(self, rule, message, location="", fix=""):
        self.add(RECOMMENDATION, rule, message, location, fix)

    def cannot_verify(self, rule, message, location="", fix=""):
        self.add(CANNOT_VERIFY, rule, message, location, fix)

    @property
    def has_errors(self) -> bool:
        return any(f.severity == ERROR for f in self.findings)

    def counts(self) -> dict:
        out = {ERROR: 0, WARNING: 0, RECOMMENDATION: 0, CANNOT_VERIFY: 0}
        for f in self.findings:
            out[f.severity] = out.get(f.severity, 0) + 1
        return out


# ---------------------------------------------------------------------------
# Form field extraction (openpyxl)
# ---------------------------------------------------------------------------

class FormField:
    def __init__(self, name: str, ftype: str, repeated: bool, metadata: bool = False) -> None:
        self.name = name
        self.type = ftype
        self.repeated = repeated
        self.metadata = metadata

    def as_dict(self) -> dict:
        return {"name": self.name, "type": self.type,
                "repeated": self.repeated, "metadata": self.metadata}


def _xlsform_type(raw_type: str) -> str:
    token = raw_type.strip().split()[0] if raw_type.strip() else ""
    # `select_one listname`, `select_multiple listname`, and the *_from_file
    # variants collapse on their leading token.
    if token in ("select_one", "select_multiple"):
        return XLSFORM_TYPE_MAP[token]
    return XLSFORM_TYPE_MAP.get(token, XLSFORM_TYPE_MAP.get(raw_type.strip(), "text"))


def extract_form_fields(xlsx_path: str) -> list[FormField]:
    """Parse an XLSForm survey sheet into the field list the server publishes.

    Mirrors the server's publishing field list: notes are excluded, group and
    repeat containers are not fields, every other named row is a field, a field
    is ``repeated`` when any ancestor row is a ``begin repeat`` (nested groups do
    not make a field repeated), and the standard metadata fields are appended.
    Field names are the bare leaf ``name`` value.
    """
    try:
        from openpyxl import load_workbook
    except ImportError as exc:  # pragma: no cover - exercised via hard import in tests
        raise RuntimeError(
            "openpyxl is required to cross-check field maps against form files. "
            "Install it (pip install openpyxl) or run without --form."
        ) from exc

    _guard_xlsx_zip_bomb(xlsx_path)
    wb = load_workbook(filename=xlsx_path, read_only=True, data_only=True)
    try:
        if "survey" not in wb.sheetnames:
            raise ValueError(f"{xlsx_path}: no 'survey' worksheet; not an XLSForm.")
        ws = wb["survey"]

        rows = ws.iter_rows(values_only=True)
        try:
            header = next(rows)
        except StopIteration:
            return _with_metadata([])

        header_map: dict[str, int] = {}
        for idx, cell in enumerate(header):
            if cell is None:
                continue
            key = str(cell).strip().lower()
            # First occurrence wins; ignore translated/duplicate columns.
            header_map.setdefault(key, idx)

        if "type" not in header_map or "name" not in header_map:
            raise ValueError(f"{xlsx_path}: survey sheet missing 'type' or 'name' column.")
        type_idx = header_map["type"]
        name_idx = header_map["name"]

        fields: list[FormField] = []
        # Stack of "group" | "repeat" for the open containers above the current row.
        stack: list[str] = []

        for row in rows:
            raw_type = _cell(row, type_idx)
            name = _cell(row, name_idx)
            token = raw_type.strip().lower()

            if token in ("begin group", "begin_group"):
                stack.append("group")
                continue
            if token in ("begin repeat", "begin_repeat"):
                stack.append("repeat")
                continue
            if token in ("end group", "end_group", "end repeat", "end_repeat"):
                if stack:
                    stack.pop()
                continue
            if not raw_type.strip():
                continue
            if token == "note":
                continue
            if not name.strip():
                continue

            repeated = "repeat" in stack
            fields.append(FormField(name.strip(), _xlsform_type(raw_type), repeated, metadata=False))
    finally:
        wb.close()
    return _with_metadata(fields)


# A single XLSForm worksheet entry should never legitimately decompress to this
# much; a member larger than this is treated as a zip bomb and refused.
MAX_XLSX_MEMBER_BYTES = 100 * 1024 * 1024


def _guard_xlsx_zip_bomb(xlsx_path: str) -> None:
    try:
        with zipfile.ZipFile(xlsx_path) as zf:
            for info in zf.infolist():
                if info.file_size > MAX_XLSX_MEMBER_BYTES:
                    raise ValueError(
                        f"{xlsx_path}: entry {info.filename!r} decompresses to "
                        f"{info.file_size:,} bytes; refusing to load (possible zip bomb)."
                    )
    except zipfile.BadZipFile as exc:
        raise ValueError(f"{xlsx_path}: not a valid .xlsx (zip) file.") from exc


def _with_metadata(fields: list[FormField]) -> list[FormField]:
    existing = {f.name for f in fields}
    meta = [FormField(n, t, False, metadata=True) for n, t in METADATA_FIELDS if n not in existing]
    return fields + meta


def _cell(row: tuple, idx: int) -> str:
    if idx >= len(row):
        return ""
    val = row[idx]
    return "" if val is None else str(val)


# ---------------------------------------------------------------------------
# Dataset XML parsing
# ---------------------------------------------------------------------------

class DataLink:
    def __init__(self, index: int) -> None:
        self.index = index
        self.children: list[str] = []
        self.link_class: Optional[str] = None
        self.link_type: Optional[str] = None
        self.link_state: Optional[str] = None
        self.link_format: Optional[str] = None
        self.link_object_id: Optional[str] = None
        self.field_map_raw: Optional[str] = None
        self.joining_field: Optional[str] = None
        self.relevance_field: Optional[str] = None
        # Parsed field map as list of (formField, datasetField, updateLogicAction).
        self.field_map: Optional[list[tuple]] = None
        self.field_map_error: Optional[str] = None

    @property
    def is_long_format(self) -> bool:
        try:
            return int(self.link_format) == DATALINK_FORMAT_LONG
        except (TypeError, ValueError):
            return False


class Dataset:
    def __init__(self) -> None:
        self.definition_children: list[str] = []
        self.id: Optional[str] = None
        self.title: Optional[str] = None
        self.dataset_type: Optional[str] = None
        self.field_names_raw: Optional[str] = None
        self.field_names: list[str] = []
        self.discriminator: Optional[str] = None
        self.unique_record_field: Optional[str] = None
        self.allow_offline_updates: Optional[str] = None
        self.form_links: list[str] = []
        self.data_links: list[DataLink] = []
        self.case_mgmt: Optional[dict] = None
        self.id_format: Optional[dict] = None

    @property
    def has_long_format_link(self) -> bool:
        return any(dl.is_long_format for dl in self.data_links)


def _localname(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _text(el) -> str:
    return (el.text or "").strip() if el is not None else ""


def parse_field_map(raw: str) -> list[tuple]:
    """Parse a fieldMap into [(formField, datasetField, updateLogicAction)].

    Accepts both the modern array form
    ``[{"formField":..,"datasetField":..,"updateLogicAction":..}]`` and the
    legacy object form ``{"formField":"datasetField"}``.
    """
    data = json.loads(raw)
    out: list[tuple] = []
    if isinstance(data, dict):
        for k, v in data.items():
            ds = v if isinstance(v, str) else (v.get("datasetField") if isinstance(v, dict) else None)
            action = v.get("updateLogicAction", "REPLACE") if isinstance(v, dict) else "REPLACE"
            out.append((k, ds, action or "REPLACE"))
    elif isinstance(data, list):
        for entry in data:
            if not isinstance(entry, dict):
                raise ValueError("field map array entries must be JSON objects")
            out.append((
                entry.get("formField"),
                entry.get("datasetField"),
                entry.get("updateLogicAction") or "REPLACE",
            ))
    else:
        raise ValueError("field map must be a JSON array or object")
    return out


def _guard_doctype(data: bytes) -> None:
    # Defense against XXE / billion-laughs entity expansion. A DTD can only define
    # entities in the prolog, but rather than reason about where the prolog ends
    # (comments, processing instructions, and CDATA can each embed a literal
    # "<dataset" that confuses a prolog scanner, and each became a bypass), reject
    # any DOCTYPE anywhere in the file. A SurveyCTO dataset definition never
    # legitimately contains the literal string "<!doctype", so a whole-file scan
    # is bypass-proof and does not false-reject real definitions.
    if b"<!doctype" in data.lower():
        raise ValueError("dataset definition must not contain a DOCTYPE declaration")


def parse_dataset(xml_path: str) -> Dataset:
    import xml.etree.ElementTree as ET

    raw = Path(xml_path).read_bytes()
    _guard_doctype(raw)
    root = ET.fromstring(raw)
    if _localname(root.tag) != "dataset":
        raise ValueError(f"root element is <{_localname(root.tag)}>, expected <dataset>")

    ds = Dataset()
    definition = None
    for child in root:
        if _localname(child.tag) == "definition":
            definition = child
            break
    if definition is None:
        raise ValueError("missing <definition> element")

    for child in definition:
        name = _localname(child.tag)
        ds.definition_children.append(name)
        if name == "id":
            ds.id = _text(child)
        elif name == "title":
            ds.title = _text(child)
        elif name == "datasetType":
            ds.dataset_type = _text(child)
        elif name == "fieldNames":
            ds.field_names_raw = _text(child)
            ds.field_names = [c.strip() for c in ds.field_names_raw.split(",") if c.strip()] if ds.field_names_raw else []
        elif name == "discriminator":
            ds.discriminator = _text(child)
        elif name == "uniqueRecordField":
            ds.unique_record_field = _text(child)
        elif name == "allowOfflineUpdates":
            ds.allow_offline_updates = _text(child)
        elif name == "formLinks":
            for fl in child:
                for fid in fl:
                    if _localname(fid.tag) == "formId":
                        ds.form_links.append(_text(fid))
        elif name == "dataLinks":
            idx = 0
            for dl_el in child:
                if _localname(dl_el.tag) != "dataLink":
                    continue
                ds.data_links.append(_parse_data_link(dl_el, idx))
                idx += 1
        elif name == "caseManagementOptions":
            ds.case_mgmt = _parse_block(child)
        elif name == "idFormatOptions":
            ds.id_format = _parse_block(child)
    return ds


def _parse_data_link(dl_el, idx: int) -> DataLink:
    dl = DataLink(idx)
    for c in dl_el:
        name = _localname(c.tag)
        dl.children.append(name)
        if name == "dataLinkClass":
            dl.link_class = _text(c)
        elif name == "dataLinkType":
            dl.link_type = _text(c)
        elif name == "dataLinkState":
            dl.link_state = _text(c)
        elif name == "dataLinkFormat":
            dl.link_format = _text(c)
        elif name == "linkObjectId":
            dl.link_object_id = _text(c)
        elif name == "fieldMap":
            dl.field_map_raw = _text(c)
        elif name == "joiningField":
            dl.joining_field = _text(c)
        elif name == "relevanceField":
            dl.relevance_field = _text(c)
    if dl.field_map_raw:
        try:
            dl.field_map = parse_field_map(dl.field_map_raw)
        except Exception as exc:  # noqa: BLE001 - reported as a finding
            dl.field_map_error = str(exc)
    return dl


def _parse_block(el) -> dict:
    block = {"_children": []}
    for c in el:
        name = _localname(c.tag)
        block["_children"].append(name)
        if name == "showColumnsWhenTable":
            cols = [_text(cn) for cn in c if _localname(cn.tag) == "columnNames"]
            block[name] = cols
        else:
            block[name] = _text(c)
    return block


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

_ID_RE = re.compile(r"^[0-9a-z_-]+$")
# Latin alphanumeric, used by the server's otherUserCode check (isLatinAlphanumeric).
_ALNUM_RE = re.compile(r"^[A-Za-z0-9]+$")


def _is_unicode_alnum(value: str) -> bool:
    """Mirror Apache Commons StringUtils.isAlphanumeric: non-empty, and every
    character is a Unicode letter or digit. The server applies this to the
    idFormatOptions prefix and suffix, so an accented prefix like 'Énu' is valid.
    """
    return bool(value) and all(c.isalpha() or c.isdigit() for c in value)


def _check_sequence(children: list[str], order: list[str], report: Report,
                    rule: str, location: str) -> None:
    """Flag children not in the canonical order, and unknown children."""
    rank = {name: i for i, name in enumerate(order)}
    last_rank = -1
    last_name = None
    for name in children:
        if name not in rank:
            report.error(rule, f"Unexpected element <{name}> in {location}; "
                         f"the schema does not allow it here.", location)
            continue
        if rank[name] < last_rank:
            report.error(
                rule,
                f"<{name}> appears after <{last_name}> in {location}, but the "
                f"schema requires this order: {', '.join(order)}.",
                location,
                fix=f"Move <{name}> before <{last_name}>.",
            )
        last_rank = max(last_rank, rank[name])
        last_name = name


def validate_dataset(ds: Dataset, forms: dict[str, list[FormField]], report: Report) -> None:
    _validate_structure(ds, report)
    _validate_identity(ds, report)
    _validate_type_and_discriminator(ds, report)
    _validate_field_names(ds, report)
    _validate_id_format(ds, report)
    _validate_case_mgmt(ds, report)
    _validate_standard_columns(ds, report)
    _validate_unique_record_field(ds, report)
    _validate_data_links(ds, forms, report)
    _verify_offline_only(ds, report)


def _validate_structure(ds: Dataset, report: Report) -> None:
    _check_sequence(ds.definition_children, DEFINITION_ORDER, report,
                    "definition-order", "<definition>")
    for req in DEFINITION_REQUIRED:
        if req not in ds.definition_children:
            report.error("definition-required",
                         f"<definition> is missing the required <{req}> element.",
                         "<definition>")


def _validate_identity(ds: Dataset, report: Report) -> None:
    if not ds.id:
        report.error("id-blank", "Please specify an ID for the dataset.", "definition/id")
    else:
        # The server validates the ID case-insensitively against [0-9a-z_-].
        if not _ID_RE.match(ds.id.lower()):
            report.error(
                "id-chars",
                "The ID can only contain numbers, letters, dashes and underscores. "
                f"Got: {ds.id!r}.",
                "definition/id",
            )
        if ds.id.lower().endswith("_qc") and (ds.dataset_type != "REPORT"):
            report.error("id-qc-suffix",
                         "The ID can not end with '_qc'.", "definition/id")
    if not ds.title:
        report.error("title-blank", "Please specify a title for the dataset.", "definition/title")


def _validate_type_and_discriminator(ds: Dataset, report: Report) -> None:
    if ds.dataset_type is None:
        report.error("type-missing", "Please specify a dataset type (<datasetType>).",
                     "definition/datasetType")
    elif ds.dataset_type not in DATASET_TYPES:
        report.error("type-enum",
                     f"<datasetType> is {ds.dataset_type!r}; must be one of "
                     f"{', '.join(sorted(DATASET_TYPES))}.", "definition/datasetType")
    elif ds.dataset_type == "CLIENT":
        report.error("type-client",
                     "CLIENT (desktop) datasets are no longer supported. Use SERVER.",
                     "definition/datasetType",
                     fix="Set <datasetType>SERVER</datasetType>.")
    elif ds.dataset_type == "REPORT":
        report.error("type-report",
                     "REPORT datasets are system-managed (quality-check warnings) and "
                     "cannot be created from a definition. Use SERVER.",
                     "definition/datasetType",
                     fix="Set <datasetType>SERVER</datasetType>.")

    if ds.discriminator is not None and ds.discriminator not in DISCRIMINATORS:
        report.error("discriminator-enum",
                     f"<discriminator> is {ds.discriminator!r}; must be one of "
                     f"{', '.join(sorted(DISCRIMINATORS))}.", "definition/discriminator")


def _validate_field_names(ds: Dataset, report: Report) -> None:
    seen: set[str] = set()
    for col in ds.field_names:
        base = col[:-1] if col.endswith("*") else col
        if base in RESERVED_FIELD_NAMES:
            report.error("field-reserved",
                         f"The field name {base!r} is reserved and cannot be used.",
                         "definition/fieldNames")
        if len(base) > MAX_FIELD_NAME_LENGTH:
            report.error("field-too-long",
                         f"Dataset field names cannot be longer than {MAX_FIELD_NAME_LENGTH} "
                         f"characters. Conflicting field: {base!r}.", "definition/fieldNames")
        if base in seen:
            report.warning("field-duplicate",
                           f"Column {base!r} appears more than once in <fieldNames>.",
                           "definition/fieldNames")
        seen.add(base)


def _is_enumerators(ds: Dataset) -> bool:
    return ds.discriminator == "ENUMERATORS"


def _is_cases(ds: Dataset) -> bool:
    # Mirror looksLikeCasesDataset: discriminator, id == "cases", or the standard
    # column signature (>=6 cols including id,label,formids,users,roles,sortby).
    if ds.discriminator == "CASES":
        return True
    # The server compares the id case-sensitively against the literal "cases".
    if (ds.id or "") == "cases":
        return True
    cols = {c[:-1] if c.endswith("*") else c for c in ds.field_names}
    signature = {"id", "label", "formids", "users", "roles", "sortby"}
    return len(ds.field_names) >= 6 and signature.issubset(cols)


def _validate_id_format(ds: Dataset, report: Report) -> None:
    fmt = ds.id_format
    is_enum = _is_enumerators(ds)
    if fmt is None:
        if is_enum:
            report.error("idformat-required-enum",
                         "The ID format options are required for an enumerator dataset. "
                         "Add <idFormatOptions> with at least <numberOfDigits>.",
                         "definition/idFormatOptions")
        return

    if not is_enum:
        report.recommend("idformat-ignored",
                         "<idFormatOptions> only applies to enumerator datasets and is "
                         "ignored here.", "definition/idFormatOptions")

    children = fmt.get("_children", [])
    if "numberOfDigits" not in children:
        report.error("idformat-digits-required",
                     "<idFormatOptions> must contain <numberOfDigits>.",
                     "definition/idFormatOptions")

    # Value rules. The server applies these for enumerator datasets; for other
    # discriminators idFormatOptions is ignored, so only enforce there.
    if is_enum:
        prefix = fmt.get("prefix", "") or ""
        suffix = fmt.get("suffix", "") or ""
        if prefix and (len(prefix) > 10 or not _is_unicode_alnum(prefix)):
            report.error("idformat-prefix",
                         "Prefix can contain alphanumeric characters only and shouldn't "
                         f"exceed 10 characters. Got: {prefix!r}.", "definition/idFormatOptions")
        if suffix and (len(suffix) > 10 or not _is_unicode_alnum(suffix)):
            report.error("idformat-suffix",
                         "Suffix can contain alphanumeric characters only and shouldn't "
                         f"exceed 10 characters. Got: {suffix!r}.", "definition/idFormatOptions")
        digits = fmt.get("numberOfDigits")
        if digits not in (None, ""):
            try:
                n = int(digits)
                if n < 4 or n > 8:
                    report.error("idformat-digits-range",
                                 "Number of digits can't be less than 4 or higher than 8. "
                                 f"Got: {n}.", "definition/idFormatOptions")
            except ValueError:
                report.error("idformat-digits-number",
                             f"Number of digits should be a number. Got: {digits!r}.",
                             "definition/idFormatOptions")


def _validate_case_mgmt(ds: Dataset, report: Report) -> None:
    cm = ds.case_mgmt
    is_cases = _is_cases(ds)
    if cm is None:
        if ds.discriminator == "CASES":
            report.error("casemgmt-required",
                         "The cases management options are required for a cases dataset. "
                         "Add <caseManagementOptions>.", "definition/caseManagementOptions")
        return

    children = cm.get("_children", [])
    for req in CASE_MGMT_REQUIRED:
        if req not in children:
            report.error("casemgmt-required-child",
                         f"<caseManagementOptions> is missing the required <{req}> element.",
                         "definition/caseManagementOptions")

    display = cm.get("displayMode", "")
    if not display:
        report.error("casemgmt-displaymode-blank",
                     "Please select whether this cases dataset should be rendered as a "
                     "tree or as a table (<displayMode>).", "definition/caseManagementOptions")
    elif display == "tree":
        pass
    elif display == "table":
        cols = cm.get("showColumnsWhenTable")
        if not cols:
            report.error("casemgmt-table-empty",
                         "Please select which columns to display when rendered as a table "
                         "(<showColumnsWhenTable> with <columnNames> children).",
                         "definition/caseManagementOptions")
        elif "id" not in cols:
            report.error("casemgmt-table-id",
                         "The 'id' column should be included in the list of columns to "
                         "display (<showColumnsWhenTable>).", "definition/caseManagementOptions")
    else:
        report.error("casemgmt-displaymode-enum",
                     f"Unknown UI option for cases dataset: {display!r}. Use 'tree' or 'table'.",
                     "definition/caseManagementOptions")

    entry = cm.get("entryMode")
    if entry and entry not in ENTRY_MODES:
        report.error("casemgmt-entrymode-enum",
                     f"<entryMode> is {entry!r}; must be one of {', '.join(sorted(ENTRY_MODES))}.",
                     "definition/caseManagementOptions")

    other = cm.get("otherUserCode")
    if other and not _ALNUM_RE.match(other):
        report.error("casemgmt-otherusercode",
                     "'Other user code' field should be latin alphanumeric (letters and "
                     f"digits only). Got: {other!r}.", "definition/caseManagementOptions")

    if cm.get("enumeratorDatasetId"):
        report.cannot_verify("casemgmt-enum-dataset",
                             "Cannot verify that the linked enumeratorDatasetId exists and is "
                             "accessible without a live server.", "definition/caseManagementOptions")


def _base_columns(ds: Dataset) -> set[str]:
    return {c[:-1] if c.endswith("*") else c for c in ds.field_names}


def _validate_standard_columns(ds: Dataset, report: Report) -> None:
    if _is_enumerators(ds):
        cols = _base_columns(ds)
        for req in ENUM_REQUIRED_COLUMNS:
            if req not in cols:
                report.warning("enum-required-column",
                               f"Enumerator datasets need the {req!r} column; the upload "
                               "succeeds, but rows without it are rejected when enumerator data "
                               "is inserted.", "definition/fieldNames")
        if "users" not in cols:
            report.warning("enum-users-column",
                           "Enumerator datasets normally include a 'users' column. Without it "
                           "the dataset silently loses per-user enumerator filtering, "
                           "auto-selection, and the manager-code prompt.",
                           "definition/fieldNames",
                           fix="Add 'users' after 'name': id,name,users,...")
    if _is_cases(ds):
        cols = _base_columns(ds)
        for req in CASES_REQUIRED_COLUMNS:
            if req not in cols:
                report.warning("cases-required-column",
                               f"Cases datasets need the {req!r} column; the upload succeeds, but "
                               "the case list fails to render in Collect without it.",
                               "definition/fieldNames")
        for conv in ("users", "roles", "sortby", "enumerators"):
            if conv not in cols:
                report.recommend("cases-standard-column",
                                 f"Cases datasets normally include {conv!r}. Include the full "
                                 f"standard set ({','.join(CASES_STANDARD_COLUMNS)}) to match "
                                 "the console and keep filtering available.",
                                 "definition/fieldNames")


def _validate_unique_record_field(ds: Dataset, report: Report) -> None:
    urf = ds.unique_record_field
    if not urf:
        if _is_enumerators(ds) or _is_cases(ds):
            report.warning("urf-missing",
                           "Cases and enumerator datasets use 'id' as the unique record field. "
                           "Add <uniqueRecordField>id</uniqueRecordField>.",
                           "definition/uniqueRecordField")
        return
    if _is_enumerators(ds) or _is_cases(ds):
        if urf != "id":
            report.warning("urf-not-id",
                           f"Cases and enumerator datasets force the unique record field to "
                           f"'id'; got {urf!r}.", "definition/uniqueRecordField")
    # For long-format datasets the unique record field is the bare form field
    # name and is intentionally not a dataset column, so do not require it in
    # <fieldNames>.
    if not ds.has_long_format_link and ds.field_names and urf not in _base_columns(ds):
        report.warning("urf-not-a-column",
                       f"The unique record field {urf!r} is not listed in <fieldNames>. The "
                       "server requires it to be an existing dataset column.",
                       "definition/uniqueRecordField")


def _validate_data_links(ds: Dataset, forms: dict[str, list[FormField]], report: Report) -> None:
    for dl in ds.data_links:
        loc = f"dataLink[{dl.index}]"
        _check_sequence(dl.children, DATALINK_ORDER, report, "datalink-order", loc)
        for req in DATALINK_REQUIRED:
            if req not in dl.children:
                report.error("datalink-required",
                             f"{loc} is missing the required <{req}> element.", loc)

        if dl.link_class is not None and dl.link_class not in DATALINK_CLASSES:
            report.error("datalink-class-enum",
                         f"{loc}: <dataLinkClass> is {dl.link_class!r}; must be one of "
                         f"{', '.join(sorted(DATALINK_CLASSES))}.", loc)
        if dl.link_type is not None and dl.link_type not in DATALINK_TYPES:
            report.error("datalink-type-enum",
                         f"{loc}: <dataLinkType> is {dl.link_type!r}; must be INCOMING or OUTGOING.",
                         loc)
        if dl.link_state is not None and dl.link_state and dl.link_state not in DATALINK_STATES:
            report.error("datalink-state-enum",
                         f"{loc}: <dataLinkState> is {dl.link_state!r}; must be ENABLED or DISABLED.",
                         loc)

        if dl.field_map_error:
            report.error("fieldmap-json",
                         f"{loc}: the field map JSON is not valid: {dl.field_map_error}.",
                         loc)
            continue

        if dl.field_map is not None:
            _validate_field_map(ds, dl, forms, report, loc)

        if dl.link_object_id:
            report.cannot_verify("form-exists",
                                 f"{loc}: cannot verify that linked object {dl.link_object_id!r} "
                                 "is deployed on the server. Deploy referenced forms first.", loc)


def _validate_field_map(ds: Dataset, dl: DataLink, forms: dict[str, list[FormField]],
                        report: Report, loc: str) -> None:
    form_fields = [t[0] for t in dl.field_map]
    dataset_fields = [t[1] for t in dl.field_map]

    if any(f is None for f in form_fields) or any(d is None for d in dataset_fields):
        report.error("fieldmap-shape",
                     f"{loc}: every field map entry needs both a form field and a dataset field.",
                     loc)

    # SCTO-15074: a form field or dataset field must not be mapped twice.
    _flag_duplicates(form_fields, report, loc, "form field")
    _flag_duplicates(dataset_fields, report, loc, "dataset field")

    # updateLogicAction enum.
    for ff, _df, action in dl.field_map:
        if action not in UPDATE_LOGIC_ACTIONS:
            report.error("fieldmap-action-enum",
                         f"{loc}: updateLogicAction {action!r} for {ff!r} is not valid; use one "
                         f"of {', '.join(sorted(UPDATE_LOGIC_ACTIONS))}.", loc)

    joining = dl.joining_field
    if joining:
        # SCTO-15073: the joining field must be present in the field map.
        if joining not in form_fields:
            base_match = any(
                (ff or "").rstrip("*") == joining.rstrip("*") for ff in form_fields
            )
            if base_match:
                report.error("joining-field-suffix",
                             f"{loc}: the joining field {joining!r} is not in the field map; a "
                             "field with the same base name is, but the repeat '*' suffix differs. "
                             "Match the suffix on both.", loc)
            else:
                report.error("joining-field-in-map",
                             f"{loc}: the joining field is not included in the field map "
                             f"({joining}).", loc,
                             fix=f"Add a field map entry whose formField is {joining!r}.")
        else:
            # Joining field's update logic must be REPLACE.
            for ff, _df, action in dl.field_map:
                if ff == joining and action != "REPLACE":
                    report.error("joining-field-replace",
                                 f"{loc}: the joining field {joining!r} must use the default "
                                 "REPLACE update option.", loc)

        # Wide-format console rules tying the joining field to the dataset's
        # unique record field. These do not apply to long format, which has its
        # own semantics (the joining field is a bare form field, not a column).
        if not dl.is_long_format and ds.unique_record_field:
            urf = ds.unique_record_field
            mapped = [(_df or "").rstrip("*") for ff, _df, _a in dl.field_map if ff == joining]
            if mapped and mapped[0] != urf:
                report.warning("joining-merges-on-urf",
                               f"{loc}: the joining field maps to {mapped[0]!r}, but the dataset's "
                               f"unique record field is {urf!r}. The console rejects the publishing "
                               "configuration unless it merges on the unique record field.", loc)

    # Wide-format: the unique record field must be mapped by some entry.
    if not dl.is_long_format and ds.unique_record_field and dl.link_type == "INCOMING":
        urf = ds.unique_record_field
        if not any((df or "").rstrip("*") == urf for df in dataset_fields):
            report.warning("urf-not-mapped",
                           f"{loc}: the unique record field {urf!r} is not mapped by any entry. "
                           "An incoming form link must publish into the unique ID column.", loc)

    # Cross-reference against the form's real fields when available.
    form_obj = _resolve_form(dl.link_object_id, forms)
    if form_obj is not None:
        _cross_reference_form(ds, dl, form_obj, report, loc)
    elif forms:
        report.recommend("form-not-supplied",
                         f"{loc}: no form file was supplied for {dl.link_object_id!r}, so field "
                         "names in the map were not checked against the form.", loc)


def _flag_duplicates(values: list, report: Report, loc: str, label: str) -> None:
    seen: set = set()
    dupes: set = set()
    for v in values:
        if v is None:
            continue
        if v in seen:
            dupes.add(v)
        seen.add(v)
    for v in sorted(dupes):
        report.error("fieldmap-duplicate",
                     f"{loc}: the {label} {v!r} is mapped more than once. You can't map the same "
                     "field twice; the publishing configuration is rejected when it is saved or "
                     "edited in the console.", loc)


def _resolve_form(link_object_id: Optional[str],
                  forms: dict[str, list[FormField]]) -> Optional[list[FormField]]:
    if not link_object_id or not forms:
        return None
    if link_object_id in forms:
        return forms[link_object_id]
    # Allow a single supplied form to match regardless of id, to ease the common
    # one-form case where the file stem may differ from the form_id.
    if len(forms) == 1:
        return next(iter(forms.values()))
    return None


def _cross_reference_form(ds: Dataset, dl: DataLink, form_fields: list[FormField],
                          report: Report, loc: str) -> None:
    by_name = {f.name: f for f in form_fields}

    for ff, _df, _a in dl.field_map:
        if ff is None:
            continue
        base = ff[:-1] if ff.endswith("*") else ff
        field = by_name.get(base)
        if field is None:
            if base in CONDITIONAL_META_FIELD_NAMES:
                report.warning("fieldmap-conditional-meta",
                               f"{loc}: {base!r} is a metadata field that is only available in "
                               "certain publishing contexts or when the form declares it; it is "
                               "not in this form. Confirm it is published before relying on it.",
                               loc)
            else:
                report.error("fieldmap-form-field-missing",
                             f"{loc}: the form field {base!r} in the field map does not exist in "
                             "the form.", loc)
            continue
        if field.repeated and not ff.endswith("*"):
            report.error("fieldmap-repeat-suffix-missing",
                         f"{loc}: {base!r} is inside a repeat group in the form, so it must carry "
                         "a '*' suffix on both formField and datasetField.", loc)
        if not field.repeated and ff.endswith("*"):
            report.error("fieldmap-repeat-suffix-extra",
                         f"{loc}: {ff!r} has a '*' suffix but {base!r} is not inside a repeat "
                         "group in the form.", loc)

    joining = dl.joining_field
    if joining:
        jbase = joining[:-1] if joining.endswith("*") else joining
        jfield = by_name.get(jbase)
        if jfield is None:
            report.error("joining-field-form-missing",
                         f"{loc}: the joining field {jbase!r} is not part of the form definition.",
                         loc)
        elif dl.is_long_format and not jfield.repeated:
            report.error("joining-field-not-repeat",
                         f"{loc}: long-format publishing requires the joining field {jbase!r} to "
                         "be inside a repeat group in the form.", loc)

    if dl.relevance_field:
        rbase = dl.relevance_field.rstrip("*")
        if rbase and rbase not in by_name:
            report.warning("relevance-field-missing",
                           f"{loc}: the relevance field {rbase!r} is not part of the form "
                           "definition.", loc)


def _verify_offline_only(ds: Dataset, report: Report) -> None:
    if ds.form_links:
        report.cannot_verify("formlinks-exist",
                             "Cannot verify that forms in <formLinks> are deployed on the server. "
                             "Deploy them before uploading this definition.", "definition/formLinks")
    if ds.allow_offline_updates and ds.allow_offline_updates.lower() == "true":
        if not ds.unique_record_field:
            report.error("offline-requires-urf",
                         "You can't enable offline updates for a dataset without a unique record "
                         "field. The server rejects this on upload.",
                         "definition/allowOfflineUpdates",
                         fix="Add <uniqueRecordField> or set <allowOfflineUpdates>false</allowOfflineUpdates>.")
        report.cannot_verify("offline-license",
                             "Offline updates also require a subscription that supports them; "
                             "this cannot be verified offline.",
                             "definition/allowOfflineUpdates")


# ---------------------------------------------------------------------------
# CLI / output
# ---------------------------------------------------------------------------

def _load_forms(form_paths: list[str], report: Report) -> dict[str, list[FormField]]:
    forms: dict[str, list[FormField]] = {}
    for p in form_paths:
        stem = Path(p).stem
        try:
            forms[stem] = extract_form_fields(p)
        except Exception as exc:  # noqa: BLE001 - reported as a finding
            report.error("form-parse", f"Could not parse form {p!r}: {exc}", p)
    return forms


def run(xml_path: str, form_paths: list[str]) -> Report:
    report = Report()
    forms = _load_forms(form_paths, report)
    try:
        ds = parse_dataset(xml_path)
    except Exception as exc:  # noqa: BLE001 - top-level parse failure
        report.error("xml-parse", f"Could not parse dataset XML: {exc}", xml_path)
        return report
    validate_dataset(ds, forms, report)
    return report


_SEVERITY_LABEL = {
    ERROR: "ERROR",
    WARNING: "WARNING",
    RECOMMENDATION: "RECOMMENDATION",
    CANNOT_VERIFY: "CANNOT VERIFY OFFLINE",
}


def format_text(report: Report) -> str:
    lines: list[str] = []
    findings = sorted(report.findings, key=lambda f: _SEVERITY_ORDER[f.severity])
    for f in findings:
        head = f"[{_SEVERITY_LABEL[f.severity]}] {f.rule}"
        if f.location:
            head += f" ({f.location})"
        lines.append(head)
        lines.append(f"    {f.message}")
        if f.fix:
            lines.append(f"    fix: {f.fix}")
    counts = report.counts()
    lines.append("")
    lines.append(
        f"Summary: {counts[ERROR]} error(s), {counts[WARNING]} warning(s), "
        f"{counts[RECOMMENDATION]} recommendation(s), "
        f"{counts[CANNOT_VERIFY]} item(s) needing a live server."
    )
    if not report.has_errors:
        lines.append("No blocking errors found. Review warnings and recommendations above.")
    return "\n".join(lines)


def format_json(report: Report) -> str:
    return json.dumps({
        "ok": not report.has_errors,
        "counts": report.counts(),
        "findings": [f.as_dict() for f in report.findings],
    }, indent=2)


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate a SurveyCTO server dataset definition (.xml) before upload.")
    parser.add_argument("dataset", help="Path to the dataset definition .xml file.")
    parser.add_argument("--form", action="append", default=[], metavar="FORM.xlsx",
                        help="Referenced form XLSForm to cross-check the field map against. "
                             "Repeatable.")
    parser.add_argument("--json", action="store_true", help="Emit findings as JSON.")
    args = parser.parse_args(argv)

    report = run(args.dataset, args.form)
    print(format_json(report) if args.json else format_text(report))
    return 1 if report.has_errors else 0


if __name__ == "__main__":
    sys.exit(main())

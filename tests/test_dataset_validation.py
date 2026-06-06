#!/usr/bin/env python3
"""Standalone tests for assets/dataset-validation/validate_dataset.py.

Run directly (no pytest needed, matching this repo's test style):
    python3 tests/test_dataset_validation.py
Exits non-zero on the first failure.

openpyxl is imported unconditionally so the form-extraction tests fail loudly if
the dependency is missing, rather than silently skipping coverage.
"""

from __future__ import annotations

import sys
import tempfile
import warnings
from pathlib import Path

import openpyxl  # noqa: F401 - hard dependency for the form-extraction tests

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "assets" / "dataset-validation"))

import validate_dataset as vd  # noqa: E402

warnings.simplefilter("ignore")  # openpyxl emits noise about unsupported features

_TESTS: list = []


def test(fn):
    _TESTS.append(fn)
    return fn


def _expect(cond: bool, msg: str) -> None:
    if not cond:
        raise AssertionError(msg)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run_xml(xml: str, forms=None):
    """Write XML to a temp file, run the validator, return the Report."""
    with tempfile.NamedTemporaryFile("w", suffix=".xml", delete=False) as fh:
        fh.write(xml)
        path = fh.name
    return vd.run(path, forms or [])


def _codes(report, severity=None) -> set:
    return {f.rule for f in report.findings if severity is None or f.severity == severity}


def _wrap(definition_body: str, instance: str = "<instance><version>1</version></instance>") -> str:
    return (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
            f"<dataset><definition>{definition_body}</definition>{instance}</dataset>")


VALID_DATA = _wrap(
    "<id>lookup</id><title>Lookup</title><datasetType>SERVER</datasetType>"
    "<fieldNames>key,value</fieldNames>"
)


def _make_form(rows, path=None) -> str:
    """rows: list of (type, name). Build a minimal XLSForm with a survey sheet."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "survey"
    ws.append(["type", "name", "label"])
    for t, n in rows:
        ws.append([t, n, n])
    wb.create_sheet("choices")
    wb.create_sheet("settings")
    if path is None:
        fh = tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False)
        path = fh.name
        fh.close()
    wb.save(path)
    return path


# ---------------------------------------------------------------------------
# Structure / required / order
# ---------------------------------------------------------------------------

@test
def test_valid_data_dataset_has_no_errors():
    r = _run_xml(VALID_DATA)
    _expect(not r.has_errors, f"valid dataset produced errors: {_codes(r, vd.ERROR)}")


@test
def test_missing_required_children():
    r = _run_xml(_wrap("<title>No id or type</title>"))
    codes = _codes(r, vd.ERROR)
    _expect("definition-required" in codes, codes)


@test
def test_definition_order_enforced():
    # discriminator before idFormatOptions is out of order.
    r = _run_xml(_wrap(
        "<id>x</id><title>X</title><datasetType>SERVER</datasetType>"
        "<discriminator>DATA</discriminator><idFormatOptions><numberOfDigits>6</numberOfDigits></idFormatOptions>"
    ))
    _expect("definition-order" in _codes(r, vd.ERROR), _codes(r, vd.ERROR))


@test
def test_unknown_element_rejected():
    r = _run_xml(_wrap(
        "<id>x</id><title>X</title><datasetType>SERVER</datasetType><bogus>1</bogus>"
    ))
    _expect("definition-order" in _codes(r, vd.ERROR), _codes(r, vd.ERROR))


@test
def test_doctype_rejected():
    xml = ('<?xml version="1.0"?>\n<!DOCTYPE dataset [<!ENTITY x "y">]>\n'
           "<dataset><definition><id>x</id><title>X</title>"
           "<datasetType>SERVER</datasetType></definition></dataset>")
    r = _run_xml(xml)
    _expect("xml-parse" in _codes(r, vd.ERROR), _codes(r, vd.ERROR))


@test
def test_doctype_after_long_comment_rejected():
    # A long leading comment must not push a DOCTYPE past the guard (billion-laughs).
    xml = ('<?xml version="1.0"?>\n<!-- ' + ("A" * 9000) + " -->\n"
           '<!DOCTYPE lolz [<!ENTITY lol "lol">]>\n'
           "<dataset><definition><id>x</id><title>X</title>"
           "<datasetType>SERVER</datasetType></definition></dataset>")
    r = _run_xml(xml)
    _expect("xml-parse" in _codes(r, vd.ERROR), _codes(r, vd.ERROR))


@test
def test_doctype_comment_containing_dataset_tag_rejected():
    # A comment containing '<dataset' must not fool the prolog scanner into
    # treating a real DOCTYPE (which follows the comment but precedes the root)
    # as post-root content. Without comment-stripping, find(b'<dataset') hits the
    # string inside the comment and the DOCTYPE evades the guard.
    xml = ('<?xml version="1.0"?>\n'
           '<!-- <dataset this is a comment -->\n'
           '<!DOCTYPE lolz [<!ENTITY lol "INJECTED">]>\n'
           "<dataset><definition><id>x</id><title>X</title>"
           "<datasetType>SERVER</datasetType></definition></dataset>")
    r = _run_xml(xml)
    _expect("xml-parse" in _codes(r, vd.ERROR), _codes(r, vd.ERROR))


@test
def test_doctype_processing_instruction_containing_dataset_tag_rejected():
    # A processing instruction containing '<dataset' must not fool the prolog
    # scanner into treating a DOCTYPE that follows the PI as post-root content.
    # Without PI-stripping, find(b'<dataset') hits the string inside the PI and
    # the DOCTYPE evades the guard, allowing entity expansion to proceed.
    xml = ('<?xml version="1.0"?>\n'
           '<?pi <dataset this is a pi ?>\n'
           '<!DOCTYPE lolz [<!ENTITY lol "INJECTED">]>\n'
           "<dataset><definition><id>x</id><title>X</title>"
           "<datasetType>SERVER</datasetType></definition></dataset>")
    r = _run_xml(xml)
    _expect("xml-parse" in _codes(r, vd.ERROR), _codes(r, vd.ERROR))


# ---------------------------------------------------------------------------
# Identity / type / discriminator
# ---------------------------------------------------------------------------

@test
def test_id_bad_chars():
    r = _run_xml(_wrap("<id>has space</id><title>X</title><datasetType>SERVER</datasetType>"))
    _expect("id-chars" in _codes(r, vd.ERROR), _codes(r, vd.ERROR))


@test
def test_id_qc_suffix():
    r = _run_xml(_wrap("<id>data_qc</id><title>X</title><datasetType>SERVER</datasetType>"))
    _expect("id-qc-suffix" in _codes(r, vd.ERROR), _codes(r, vd.ERROR))


@test
def test_client_and_report_rejected():
    r1 = _run_xml(_wrap("<id>x</id><title>X</title><datasetType>CLIENT</datasetType>"))
    _expect("type-client" in _codes(r1, vd.ERROR), _codes(r1, vd.ERROR))
    r2 = _run_xml(_wrap("<id>x</id><title>X</title><datasetType>REPORT</datasetType>"))
    _expect("type-report" in _codes(r2, vd.ERROR), _codes(r2, vd.ERROR))


@test
def test_bad_discriminator():
    r = _run_xml(_wrap(
        "<id>x</id><title>X</title><datasetType>SERVER</datasetType>"
        "<discriminator>WRONG</discriminator>"))
    _expect("discriminator-enum" in _codes(r, vd.ERROR), _codes(r, vd.ERROR))


# ---------------------------------------------------------------------------
# idFormatOptions (enumerators)
# ---------------------------------------------------------------------------

@test
def test_enumerator_requires_id_format():
    r = _run_xml(_wrap(
        "<id>enum</id><title>E</title><datasetType>SERVER</datasetType>"
        "<fieldNames>id,name,users</fieldNames><discriminator>ENUMERATORS</discriminator>"
        "<uniqueRecordField>id</uniqueRecordField>"))
    _expect("idformat-required-enum" in _codes(r, vd.ERROR), _codes(r, vd.ERROR))


@test
def test_enumerator_prefix_and_digits_rules():
    r = _run_xml(_wrap(
        "<id>enum</id><title>E</title><datasetType>SERVER</datasetType>"
        "<fieldNames>id,name,users</fieldNames>"
        "<idFormatOptions><prefix>ENU-</prefix><numberOfDigits>2</numberOfDigits></idFormatOptions>"
        "<discriminator>ENUMERATORS</discriminator><uniqueRecordField>id</uniqueRecordField>"))
    codes = _codes(r, vd.ERROR)
    _expect("idformat-prefix" in codes, codes)
    _expect("idformat-digits-range" in codes, codes)


@test
def test_enumerator_valid_clean():
    r = _run_xml(_wrap(
        "<id>enum</id><title>E</title><datasetType>SERVER</datasetType>"
        "<fieldNames>id,name,users</fieldNames>"
        "<idFormatOptions><prefix>ENU</prefix><numberOfDigits>6</numberOfDigits></idFormatOptions>"
        "<discriminator>ENUMERATORS</discriminator><uniqueRecordField>id</uniqueRecordField>"))
    _expect(not r.has_errors, _codes(r, vd.ERROR))


@test
def test_enumerator_missing_users_is_warning_not_error():
    r = _run_xml(_wrap(
        "<id>enum</id><title>E</title><datasetType>SERVER</datasetType>"
        "<fieldNames>id,name</fieldNames>"
        "<idFormatOptions><numberOfDigits>6</numberOfDigits></idFormatOptions>"
        "<discriminator>ENUMERATORS</discriminator><uniqueRecordField>id</uniqueRecordField>"))
    _expect(not r.has_errors, f"missing users should not be an error: {_codes(r, vd.ERROR)}")
    _expect("enum-users-column" in _codes(r, vd.WARNING), _codes(r, vd.WARNING))


@test
def test_enumerator_missing_required_id_is_warning():
    # The upload is not rejected for a missing id column; it degrades at data
    # insert time, so this is a warning under server-truth tiering.
    r = _run_xml(_wrap(
        "<id>enum</id><title>E</title><datasetType>SERVER</datasetType>"
        "<fieldNames>name,users</fieldNames>"
        "<idFormatOptions><numberOfDigits>6</numberOfDigits></idFormatOptions>"
        "<discriminator>ENUMERATORS</discriminator><uniqueRecordField>id</uniqueRecordField>"))
    _expect(not r.has_errors, f"missing id column should not be an error: {_codes(r, vd.ERROR)}")
    _expect("enum-required-column" in _codes(r, vd.WARNING), _codes(r, vd.WARNING))


@test
def test_enumerator_unicode_prefix_accepted():
    # The server uses Apache isAlphanumeric (Unicode), so an accented prefix is valid.
    r = _run_xml(_wrap(
        "<id>enum</id><title>E</title><datasetType>SERVER</datasetType>"
        "<fieldNames>id,name,users</fieldNames>"
        "<idFormatOptions><prefix>Énu</prefix><numberOfDigits>6</numberOfDigits></idFormatOptions>"
        "<discriminator>ENUMERATORS</discriminator><uniqueRecordField>id</uniqueRecordField>"))
    _expect("idformat-prefix" not in _codes(r, vd.ERROR),
            f"unicode prefix must be accepted: {_codes(r, vd.ERROR)}")


@test
def test_uppercase_id_accepted():
    # The server lowercases the id before validating its character set.
    r = _run_xml(_wrap("<id>My_Lookup</id><title>X</title><datasetType>SERVER</datasetType>"))
    _expect("id-chars" not in _codes(r, vd.ERROR), _codes(r, vd.ERROR))


# ---------------------------------------------------------------------------
# caseManagementOptions
# ---------------------------------------------------------------------------

@test
def test_cases_table_requires_id_column():
    r = _run_xml(_wrap(
        "<id>cases</id><title>C</title><datasetType>SERVER</datasetType>"
        "<fieldNames>id,label,formids,users,roles,sortby,enumerators</fieldNames>"
        "<caseManagementOptions><displayMode>table</displayMode>"
        "<showFinalizedSentWhenTree>true</showFinalizedSentWhenTree>"
        "<showColumnsWhenTable><columnNames>label</columnNames></showColumnsWhenTable>"
        "</caseManagementOptions><discriminator>CASES</discriminator>"
        "<uniqueRecordField>id</uniqueRecordField>"))
    _expect("casemgmt-table-id" in _codes(r, vd.ERROR), _codes(r, vd.ERROR))


@test
def test_cases_bad_display_mode():
    r = _run_xml(_wrap(
        "<id>cases</id><title>C</title><datasetType>SERVER</datasetType>"
        "<fieldNames>id,label,formids,users,roles,sortby,enumerators</fieldNames>"
        "<caseManagementOptions><displayMode>grid</displayMode>"
        "<showFinalizedSentWhenTree>true</showFinalizedSentWhenTree>"
        "<showColumnsWhenTable/></caseManagementOptions>"
        "<discriminator>CASES</discriminator><uniqueRecordField>id</uniqueRecordField>"))
    _expect("casemgmt-displaymode-enum" in _codes(r, vd.ERROR), _codes(r, vd.ERROR))


@test
def test_cases_other_user_code_alnum():
    r = _run_xml(_wrap(
        "<id>cases</id><title>C</title><datasetType>SERVER</datasetType>"
        "<fieldNames>id,label,formids,users,roles,sortby,enumerators</fieldNames>"
        "<caseManagementOptions><displayMode>tree</displayMode>"
        "<showFinalizedSentWhenTree>true</showFinalizedSentWhenTree>"
        "<showColumnsWhenTable/><otherUserCode>OTHER-1</otherUserCode></caseManagementOptions>"
        "<discriminator>CASES</discriminator><uniqueRecordField>id</uniqueRecordField>"))
    _expect("casemgmt-otherusercode" in _codes(r, vd.ERROR), _codes(r, vd.ERROR))


@test
def test_cases_missing_required_column_is_warning():
    # Missing formids is accepted on upload; the case list fails to render at
    # runtime, so this is a warning, not an upload-blocking error.
    r = _run_xml(_wrap(
        "<id>cases</id><title>C</title><datasetType>SERVER</datasetType>"
        "<fieldNames>id,label</fieldNames>"
        "<caseManagementOptions><displayMode>tree</displayMode>"
        "<showFinalizedSentWhenTree>true</showFinalizedSentWhenTree>"
        "<showColumnsWhenTable/></caseManagementOptions>"
        "<discriminator>CASES</discriminator><uniqueRecordField>id</uniqueRecordField>"))
    _expect(not r.has_errors, f"missing cases column should not be an error: {_codes(r, vd.ERROR)}")
    _expect("cases-required-column" in _codes(r, vd.WARNING), _codes(r, vd.WARNING))


# ---------------------------------------------------------------------------
# fieldNames rules
# ---------------------------------------------------------------------------

@test
def test_reserved_rowid_rejected():
    r = _run_xml(_wrap(
        "<id>x</id><title>X</title><datasetType>SERVER</datasetType>"
        "<fieldNames>key,rowId</fieldNames>"))
    _expect("field-reserved" in _codes(r, vd.ERROR), _codes(r, vd.ERROR))


@test
def test_field_too_long():
    long_name = "f" * 61
    r = _run_xml(_wrap(
        "<id>x</id><title>X</title><datasetType>SERVER</datasetType>"
        f"<fieldNames>key,{long_name}</fieldNames>"))
    _expect("field-too-long" in _codes(r, vd.ERROR), _codes(r, vd.ERROR))


# ---------------------------------------------------------------------------
# dataLink / fieldMap rules
# ---------------------------------------------------------------------------

def _with_data_link(field_map: str, joining: str = "", fmt: str = "0",
                    unique_record: str = "", extra_fields: str = "key,value") -> str:
    urf = f"<uniqueRecordField>{unique_record}</uniqueRecordField>" if unique_record else ""
    join = f"<joiningField>{joining}</joiningField>" if joining else ""
    return _wrap(
        "<id>x</id><title>X</title><datasetType>SERVER</datasetType>"
        f"<fieldNames>{extra_fields}</fieldNames>"
        "<dataLinks><dataLink><dataLinkClass>FORM</dataLinkClass>"
        "<dataLinkType>INCOMING</dataLinkType>"
        f"<dataLinkFormat>{fmt}</dataLinkFormat><linkObjectId>f1</linkObjectId>"
        f"<fieldMap>{field_map}</fieldMap>{join}</dataLink></dataLinks>" + urf)


@test
def test_field_map_invalid_json():
    r = _run_xml(_with_data_link("{not valid json"))
    _expect("fieldmap-json" in _codes(r, vd.ERROR), _codes(r, vd.ERROR))


@test
def test_field_map_object_form_accepted():
    r = _run_xml(_with_data_link('{"a":"key","b":"value"}'))
    _expect("fieldmap-json" not in _codes(r, vd.ERROR), _codes(r, vd.ERROR))


@test
def test_duplicate_form_field_mapping():
    # SCTO-15074: same form field mapped twice (array form allows it).
    fm = ('[{"formField":"a","datasetField":"key"},'
          '{"formField":"a","datasetField":"value"}]')
    r = _run_xml(_with_data_link(fm))
    _expect("fieldmap-duplicate" in _codes(r, vd.ERROR), _codes(r, vd.ERROR))


@test
def test_duplicate_dataset_field_mapping():
    fm = ('[{"formField":"a","datasetField":"key"},'
          '{"formField":"b","datasetField":"key"}]')
    r = _run_xml(_with_data_link(fm))
    _expect("fieldmap-duplicate" in _codes(r, vd.ERROR), _codes(r, vd.ERROR))


@test
def test_joining_field_must_be_in_map():
    # SCTO-15073.
    fm = '[{"formField":"a","datasetField":"key"}]'
    r = _run_xml(_with_data_link(fm, joining="caseid"))
    _expect("joining-field-in-map" in _codes(r, vd.ERROR), _codes(r, vd.ERROR))


@test
def test_joining_field_suffix_mismatch():
    fm = '[{"formField":"caseid","datasetField":"key"}]'
    r = _run_xml(_with_data_link(fm, joining="caseid*", fmt="1"))
    _expect("joining-field-suffix" in _codes(r, vd.ERROR), _codes(r, vd.ERROR))


@test
def test_joining_field_replace_required():
    fm = ('[{"formField":"caseid","datasetField":"key","updateLogicAction":"ADD_TO_NUMERIC_VALUE"}]')
    r = _run_xml(_with_data_link(fm, joining="caseid"))
    _expect("joining-field-replace" in _codes(r, vd.ERROR), _codes(r, vd.ERROR))


@test
def test_bad_update_logic_action():
    fm = '[{"formField":"a","datasetField":"key","updateLogicAction":"BOGUS"}]'
    r = _run_xml(_with_data_link(fm))
    _expect("fieldmap-action-enum" in _codes(r, vd.ERROR), _codes(r, vd.ERROR))


@test
def test_datalink_order_enforced():
    # joiningField before fieldMap is out of order.
    body = (
        "<id>x</id><title>X</title><datasetType>SERVER</datasetType>"
        "<fieldNames>key</fieldNames>"
        "<dataLinks><dataLink><dataLinkClass>FORM</dataLinkClass>"
        "<dataLinkType>INCOMING</dataLinkType><linkObjectId>f1</linkObjectId>"
        '<joiningField>a</joiningField><fieldMap>{"a":"key"}</fieldMap>'
        "</dataLink></dataLinks>")
    r = _run_xml(_wrap(body))
    _expect("datalink-order" in _codes(r, vd.ERROR), _codes(r, vd.ERROR))


# ---------------------------------------------------------------------------
# Long-format / unique-record-field scoping (no false positives)
# ---------------------------------------------------------------------------

@test
def test_long_format_unique_record_field_not_a_column_is_ok():
    # uniqueRecordField is the bare form field, intentionally not in fieldNames.
    fm = ('[{"formField":"plot_id*","datasetField":"plot_id_key*","updateLogicAction":"REPLACE"},'
          '{"formField":"area_ha*","datasetField":"area_ha*","updateLogicAction":"REPLACE"}]')
    xml = _wrap(
        "<id>plots</id><title>P</title><datasetType>SERVER</datasetType>"
        "<fieldNames>plot_id_key,area_ha</fieldNames>"
        "<dataLinks><dataLink><dataLinkClass>FORM</dataLinkClass>"
        "<dataLinkType>INCOMING</dataLinkType><dataLinkFormat>1</dataLinkFormat>"
        f"<linkObjectId>f1</linkObjectId><fieldMap>{fm}</fieldMap>"
        "<joiningField>plot_id*</joiningField></dataLink></dataLinks>"
        "<discriminator>DATA</discriminator><uniqueRecordField>plot_id</uniqueRecordField>")
    r = _run_xml(xml)
    _expect(not r.has_errors, f"long-format example should be clean: {_codes(r, vd.ERROR)}")
    _expect("urf-not-a-column" not in _codes(r, vd.WARNING),
            "long-format uniqueRecordField must not warn about missing column")


# ---------------------------------------------------------------------------
# Form extraction + cross-reference
# ---------------------------------------------------------------------------

@test
def test_form_extraction_types_and_repeat():
    form = _make_form([
        ("text", "farmer_id"),
        ("note", "intro"),
        ("begin group", "g1"),
        ("integer", "age"),
        ("end group", "g1"),
        ("begin repeat", "plots"),
        ("text", "plot_id"),
        ("decimal", "area_ha"),
        ("select_one crops", "crop_type"),
        ("end repeat", "plots"),
        ("calculate", "computed"),
    ])
    fields = vd.extract_form_fields(form)
    by_name = {f.name: f for f in fields}
    _expect("intro" not in by_name, "notes must be excluded")
    _expect("g1" not in by_name, "group containers are not fields")
    _expect("plots" not in by_name, "repeat containers are not fields")
    _expect(by_name["age"].repeated is False, "field in plain group is not repeated")
    _expect(by_name["plot_id"].repeated is True, "field in repeat is repeated")
    _expect(by_name["area_ha"].repeated is True, "field in repeat is repeated")
    _expect(by_name["crop_type"].type == "select_one", by_name["crop_type"].type)
    _expect(by_name["computed"].type == "text", "calculate maps to text")
    _expect(by_name["SubmissionDate"].metadata is True, "metadata appended")
    _expect(by_name["KEY"].metadata is True, "KEY metadata appended")


@test
def test_cross_reference_missing_field():
    form = _make_form([("text", "real_field")])
    fm = '[{"formField":"ghost","datasetField":"key"}]'
    xml = _with_data_link(fm)
    r = _run_xml(xml, forms=[form])
    _expect("fieldmap-form-field-missing" in _codes(r, vd.ERROR), _codes(r, vd.ERROR))


@test
def test_cross_reference_repeat_suffix_missing():
    form = _make_form([
        ("begin repeat", "rep"), ("text", "in_repeat"), ("end repeat", "rep"),
    ])
    # in_repeat is repeated in the form but mapped without the '*' suffix.
    fm = '[{"formField":"in_repeat","datasetField":"key"}]'
    xml = _with_data_link(fm)
    r = _run_xml(xml, forms=[form])
    _expect("fieldmap-repeat-suffix-missing" in _codes(r, vd.ERROR), _codes(r, vd.ERROR))


@test
def test_cross_reference_long_format_joining_not_in_repeat():
    form = _make_form([
        ("text", "top_level"),
        ("begin repeat", "rep"), ("text", "inside"), ("end repeat", "rep"),
    ])
    # joining field is top_level (not in a repeat) but format is long.
    fm = '[{"formField":"top_level","datasetField":"key"}]'
    xml = _with_data_link(fm, joining="top_level", fmt="1")
    r = _run_xml(xml, forms=[form])
    _expect("joining-field-not-repeat" in _codes(r, vd.ERROR), _codes(r, vd.ERROR))


@test
def test_offline_updates_requires_unique_record_field():
    r = _run_xml(_wrap(
        "<id>x</id><title>X</title><datasetType>SERVER</datasetType>"
        "<fieldNames>key,value</fieldNames>"
        "<allowOfflineUpdates>true</allowOfflineUpdates>"))
    _expect("offline-requires-urf" in _codes(r, vd.ERROR), _codes(r, vd.ERROR))


@test
def test_conditional_metadata_field_is_warning_not_error():
    # formdef_id is not in the incoming form feed nor in the survey sheet, so
    # mapping it is a warning (availability unknown), not a hard missing-field error.
    form = _make_form([("text", "real_field")])
    fm = '[{"formField":"formdef_id","datasetField":"key"}]'
    r = _run_xml(_with_data_link(fm), forms=[form])
    _expect("fieldmap-form-field-missing" not in _codes(r, vd.ERROR), _codes(r, vd.ERROR))
    _expect("fieldmap-conditional-meta" in _codes(r, vd.WARNING), _codes(r, vd.WARNING))


@test
def test_cross_reference_clean_when_consistent():
    form = _make_form([
        ("text", "farmer_id"),
        ("begin repeat", "plots"), ("text", "plot_id"), ("decimal", "area_ha"),
        ("end repeat", "plots"),
    ])
    fm = ('[{"formField":"plot_id*","datasetField":"plot_id_key*","updateLogicAction":"REPLACE"},'
          '{"formField":"area_ha*","datasetField":"area_ha*","updateLogicAction":"REPLACE"}]')
    xml = _wrap(
        "<id>plots</id><title>P</title><datasetType>SERVER</datasetType>"
        "<fieldNames>plot_id_key,area_ha</fieldNames>"
        "<dataLinks><dataLink><dataLinkClass>FORM</dataLinkClass>"
        "<dataLinkType>INCOMING</dataLinkType><dataLinkFormat>1</dataLinkFormat>"
        f"<linkObjectId>f1</linkObjectId><fieldMap>{fm}</fieldMap>"
        "<joiningField>plot_id*</joiningField></dataLink></dataLinks>"
        "<discriminator>DATA</discriminator><uniqueRecordField>plot_id</uniqueRecordField>")
    r = _run_xml(xml, forms=[form])
    _expect(not r.has_errors, f"consistent cross-reference should be clean: {_codes(r, vd.ERROR)}")


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def main() -> int:
    failures = 0
    for fn in _TESTS:
        try:
            fn()
            print(f"  ok  {fn.__name__}")
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print(f"FAIL  {fn.__name__}: {exc}")
    print(f"\n{len(_TESTS) - failures}/{len(_TESTS)} passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())

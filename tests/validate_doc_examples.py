#!/usr/bin/env python3
"""Validate the XML examples embedded in the shipped reference docs.

Two checks, both over every ```xml fenced block in SKILL.md and references/*.md:

1. Well-formedness: tags are balanced and properly nested. Blocks may be
   fragments and may use undeclared namespace prefixes (common in XForm
   snippets), so each block is wrapped in a synthetic root and parsed with a
   non-namespace expat parser. This catches copy-paste breakage in any example.

2. Element ordering: several dataset-definition containers are ordered
   sequences in the server schema, so an out-of-order example would teach the
   model XML the server rejects. Every instance of those containers in the docs
   must list its children in the schema order.

This validates the documentation examples only. It does not perform full schema
validation against the server, and it does not guarantee model output at
runtime. The canonical orders below are transcribed from the server schema
(scto-commons: com/surveycto/commons/datasets/xml/dataset.xsd); if that schema
changes, update the orders here to match. Only xs:sequence containers are
listed: xs:all containers such as caseManagementOptions and idFormatOptions are
order-independent and intentionally omitted.
"""
from __future__ import annotations

import re
import sys
import xml.parsers.expat as expat
from pathlib import Path
from xml.etree import ElementTree

REPO_ROOT = Path(__file__).resolve().parents[1]
DOC_FILES = [REPO_ROOT / "SKILL.md"] + sorted((REPO_ROOT / "references").glob("*.md"))

# Tolerate an optional info-string tail after ```xml and both LF and CRLF newlines.
XML_BLOCK = re.compile(r"```xml[^\n]*\r?\n(.*?)```", re.S)

# Canonical child order of each ordered (xs:sequence) container in the dataset
# schema. Children may be omitted, but the ones present cannot be reordered.
# Keyed by the container element's tag; an element whose tag is not a key here
# is not order-checked.
CONTAINER_ORDER = {
    "definition": [
        "id",
        "title",
        "datasetType",
        "fieldNames",
        "formLinks",
        "dataLinks",
        "caseManagementOptions",
        "idFormatOptions",
        "discriminator",
        "uniqueRecordField",
        "allowOfflineUpdates",
    ],
    "dataLink": [
        "dataLinkClass",
        "dataLinkType",
        "dataLinkState",
        "dataLinkFormat",
        "linkObjectId",
        "fieldMap",
        "joiningField",
        "relevanceField",
        "isAutoConfigured",
        "publishPartialData",
    ],
}


def xml_blocks(doc: Path) -> list[str]:
    return XML_BLOCK.findall(doc.read_text(encoding="utf-8"))


def check_well_formed(block: str) -> str | None:
    parser = expat.ParserCreate()
    try:
        parser.Parse(f"<__root__>{block.strip()}</__root__>", True)
    except expat.ExpatError as exc:
        return f"not well-formed XML: {exc}"
    return None


def has_ordered_container(block: str) -> bool:
    return any(f"<{tag}>" in block or f"<{tag} " in block for tag in CONTAINER_ORDER)


def check_element_order(block: str) -> list[str]:
    if not has_ordered_container(block):
        return []
    try:
        root = ElementTree.fromstring(f"<__root__>{block.strip()}</__root__>")
    except ElementTree.ParseError as exc:
        return [f"example could not be parsed for order checking: {exc}"]
    problems: list[str] = []
    for element in root.iter():
        order = CONTAINER_ORDER.get(element.tag)
        if order is None:
            continue
        rank = {name: i for i, name in enumerate(order)}
        children = [child.tag for child in list(element)]
        unknown = [c for c in children if c not in rank]
        if unknown:
            problems.append(f"<{element.tag}> has unknown child element(s): {unknown}")
        ranks = [rank[c] for c in children if c in rank]
        if ranks != sorted(ranks):
            expected = [c for c in order if c in children]
            problems.append(
                f"<{element.tag}> children out of schema order: {children}; expected order {expected}"
            )
    return problems


def check_publishpartialdata_framing() -> list[str]:
    """Guard the publishPartialData framing in the dataset reference.

    publishPartialData enables real-time (partial) dataset publishing, a feature
    most servers do not yet support and reject on import. The reference must keep
    two invariants: omit it by default (so ordinary definitions deploy anywhere),
    and only author it as a gated exception when the user asks to enable the
    feature and confirms their server supports it. This locks that dual-mode
    framing so a future edit cannot reopen the door to emitting it by default,
    nor revert to presenting it as a normal optional field to set.
    """
    doc = REPO_ROOT / "references" / "datasets-xml.md"
    if not doc.exists():
        return ["references/datasets-xml.md is missing"]
    text = doc.read_text(encoding="utf-8")
    problems: list[str] = []
    forbidden = "leave it `false` or omit it"
    if forbidden in text:
        problems.append(
            "datasets-xml.md still presents publishPartialData as authorable by "
            f"default ({forbidden!r}); it must omit it by default."
        )
    required = {
        "Default: OMIT it": "the default-omit guidance",
        "Add it only to enable real-time dataset publishing": "the opt-in skeleton comment",
        "confirms their server supports it": "the gated-enable condition",
    }
    for needle, what in required.items():
        if needle not in text:
            problems.append(
                f"datasets-xml.md is missing {what} ({needle!r}) for publishPartialData."
            )
    return problems


def main() -> int:
    errors: list[str] = []
    blocks_checked = 0
    ordered_examples_checked = 0

    errors.extend(check_publishpartialdata_framing())

    for doc in DOC_FILES:
        if not doc.exists():
            continue
        for index, block in enumerate(xml_blocks(doc)):
            blocks_checked += 1
            label = f"{doc.relative_to(REPO_ROOT)} xml block #{index}"

            well_formed_error = check_well_formed(block)
            if well_formed_error:
                errors.append(f"{label}: {well_formed_error}")
                # ordering check needs parseable XML; skip it for this block
                continue

            if has_ordered_container(block):
                ordered_examples_checked += 1
            for problem in check_element_order(block):
                errors.append(f"{label}: {problem}")

    if blocks_checked == 0:
        errors.append("found no ```xml examples to validate (block finder may be broken)")
    if ordered_examples_checked == 0:
        errors.append("found no ordered dataset examples to order-check (finder may be broken)")

    if errors:
        print("Doc example validation failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1

    print(
        f"Doc example validation passed ({blocks_checked} xml blocks, "
        f"{ordered_examples_checked} with ordered dataset containers)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

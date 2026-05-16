"""Parse a CommCare XForms XML export into a clean Python dict for form conversion.

This helper supports the SurveyCTO form-conversion workflow described in
``references/form-conversion-commcare.md``. CommCare exports forms as XForms
XML files with several namespaces (XHTML, XForms, JavaRosa, OpenRosa,
Vellum, CommCare). Iterating those directly is finicky: every element name
is namespaced, ``itext`` lookups span multiple elements, and bind metadata
lives separately from the UI body. This helper does the namespace handling
and lookups once, returning a flat Python structure that's straightforward
to walk when emitting SurveyCTO XLSForm rows.

Usage::

    from commcare_xform_loader import load_xform

    form = load_xform("/path/to/case_followup.xml")
    print(form["form_title"], form["languages"])
    for q in form["questions"]:
        print(q["name"], q["type"], q["labels"])

Standard library only (``xml.etree.ElementTree``). No external dependencies.

This script does NOT emit SurveyCTO rows. It only normalizes the source.
The agent is expected to walk the returned structure, apply the conversion
rules from ``references/form-conversion-commcare.md`` (XForms type ->
XLSForm type mapping, XPath expression rewrites, case-management flagging,
etc.), and apply the resulting XLSForm edits through the SurveyCTO MCP
workflow.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

NS = {
    "h": "http://www.w3.org/1999/xhtml",
    "xf": "http://www.w3.org/2002/xforms",
    "jr": "http://openrosa.org/javarosa",
    "orx": "http://openrosa.org/jr/xforms",
    "vellum": "http://commcarehq.org/xforms/vellum",
    "cc": "http://commcarehq.org/xforms",
    "xsd": "http://www.w3.org/2001/XMLSchema",
}


def _q(tag: str) -> str:
    """Resolve a ``prefix:local`` tag to a Clark-notation qualified name."""
    if ":" in tag:
        prefix, local = tag.split(":", 1)
        return f"{{{NS[prefix]}}}{local}"
    return f"{{{NS['xf']}}}{tag}"


def _strip_ns(tag: str) -> str:
    """Return the local part of a Clark-notation tag."""
    return tag.split("}", 1)[1] if "}" in tag else tag


def load_xform(path: str | Path) -> dict[str, Any]:
    """Parse a CommCare XForms XML file into a normalized dict.

    :param path: filesystem path to the ``.xml`` form definition.
    :returns: a dict with keys ``form_title``, ``form_id``, ``languages``,
        ``default_language``, ``questions``, ``case_actions``,
        ``secondary_instances``, ``warnings``, ``raw_namespaces``.
        See module docstring for the per-question shape.
    """
    tree = ET.parse(str(path))
    root = tree.getroot()
    warnings: list[str] = []

    head = root.find(_q("h:head"))
    body = root.find(_q("h:body"))
    if head is None or body is None:
        raise ValueError(
            f"{path}: expected <h:head> and <h:body>; got root tag {root.tag!r}"
        )

    title_el = head.find(_q("h:title"))
    form_title = (title_el.text or "").strip() if title_el is not None else ""

    model = head.find(_q("xf:model"))
    if model is None:
        raise ValueError(f"{path}: no <model> element in <h:head>")

    primary_instance, secondary_instances = _split_instances(model, warnings)
    form_id = _form_id_from_instance(primary_instance, warnings)

    itext_languages, itext_map = _parse_itext(model)
    default_language = itext_languages[0] if itext_languages else ""

    binds, binds_by_id = _parse_binds(model)
    case_actions = _parse_case_actions(model)

    questions: list[dict[str, Any]] = []
    _walk_body(
        body,
        binds=binds,
        binds_by_id=binds_by_id,
        itext_map=itext_map,
        languages=itext_languages,
        parent_path=[],
        questions=questions,
        warnings=warnings,
    )

    _detect_name_collisions(questions, warnings)

    return {
        "form_title": form_title,
        "form_id": form_id,
        "languages": itext_languages,
        "default_language": default_language,
        "questions": questions,
        "case_actions": case_actions,
        "secondary_instances": secondary_instances,
        "warnings": warnings,
        "raw_namespaces": dict(NS),
    }


# --- instance handling -----------------------------------------------------


def _split_instances(model: ET.Element, warnings: list[str]) -> tuple[ET.Element, list[dict[str, Any]]]:
    """Return (primary_instance, secondary_instances_metadata)."""
    instances = model.findall(_q("xf:instance"))
    if not instances:
        raise ValueError("model has no <instance> elements")
    primary = instances[0]
    secondary: list[dict[str, Any]] = []
    for inst in instances[1:]:
        inst_id = inst.get("id") or ""
        src = inst.get("src") or ""
        secondary.append({"id": inst_id, "src": src, "element": inst})
        if inst_id == "casedb":
            warnings.append(
                "Form references the CommCare case database (instance 'casedb'); "
                "case-property reads must be re-pointed at a SurveyCTO dataset."
            )
        elif inst_id and inst_id not in ("commcaresession",):
            # commcaresession is metadata; other secondary instances are
            # usually external lookup data.
            pass
    return primary, secondary


def _form_id_from_instance(primary_instance: ET.Element, warnings: list[str]) -> str:
    """Pull a form_id from the primary instance root element.

    CommCare's primary instance typically has a single child element whose
    tag is the form identifier and whose ``xmlns`` is the form xmlns. We
    return that element's local tag name. The actual form xmlns (a URL)
    is more globally unique but rarely what a user wants as a SurveyCTO
    form_id.
    """
    children = list(primary_instance)
    if not children:
        warnings.append("Primary <instance> has no child element; form_id will be empty.")
        return ""
    root = children[0]
    return root.get("id") or root.get("name") or _strip_ns(root.tag)


# --- itext (translations) --------------------------------------------------


def _parse_itext(model: ET.Element) -> tuple[list[str], dict[str, dict[str, dict[str, str]]]]:
    """Return (language_codes_in_order, itext_map).

    ``itext_map[itext_id][lang][form] = value`` where ``form`` is one of
    ``"default"``, ``"long"``, ``"short"``, ``"audio"``, ``"image"``,
    ``"video"``, ``"markdown"``, etc.
    """
    itext = model.find(_q("xf:itext"))
    if itext is None:
        return [], {}

    languages: list[str] = []
    itext_map: dict[str, dict[str, dict[str, str]]] = {}

    for translation in itext.findall(_q("xf:translation")):
        lang = translation.get("lang", "")
        if lang and lang not in languages:
            languages.append(lang)
        for text in translation.findall(_q("xf:text")):
            text_id = text.get("id") or ""
            per_lang = itext_map.setdefault(text_id, {})
            per_form = per_lang.setdefault(lang, {})
            for value in text.findall(_q("xf:value")):
                form = value.get("form") or "default"
                per_form[form] = _flatten_text(value)
    return languages, itext_map


def _flatten_text(el: ET.Element) -> str:
    """Flatten an element's text content, including ``<output value="..."/>`` placeholders.

    ``<output value="/data/age"/>`` becomes the literal string ``${age}`` in
    the returned text so the caller can carry it into a SurveyCTO label.
    Note this is the *nodeset* path translated by ``_nodeset_to_ref``; the
    caller is responsible for any further safe-name sanitization.
    """
    parts: list[str] = []
    if el.text:
        parts.append(el.text)
    for child in el:
        tag = _strip_ns(child.tag)
        if tag == "output":
            ref = child.get("value") or child.get("ref") or ""
            parts.append(_nodeset_to_ref(ref))
        else:
            parts.append(_flatten_text(child))
        if child.tail:
            parts.append(child.tail)
    return "".join(parts).strip()


def _nodeset_to_ref(nodeset: str) -> str:
    """Convert a nodeset path like ``/data/group/age`` into ``${age}``.

    Only the leaf is used; group context is implicit in XLSForm references.
    """
    nodeset = nodeset.strip()
    if not nodeset:
        return ""
    leaf = nodeset.split("/")[-1].split("[")[0]
    return f"${{{leaf}}}" if leaf else ""


# --- binds ----------------------------------------------------------------


def _parse_binds(model: ET.Element) -> tuple[dict[str, dict[str, str]], dict[str, dict[str, str]]]:
    """Index <bind> elements by their nodeset path and optional bind id."""
    binds: dict[str, dict[str, str]] = {}
    binds_by_id: dict[str, dict[str, str]] = {}
    for bind in model.findall(_q("xf:bind")):
        nodeset = bind.get("nodeset") or bind.get("ref") or ""
        if not nodeset:
            continue
        bind_id = bind.get("id") or ""
        bind_data: dict[str, str] = {"nodeset": nodeset}
        if bind_id:
            bind_data["id"] = bind_id
        for attr in (
            "type",
            "required",
            "readonly",
            "relevant",
            "constraint",
            "calculate",
            f"{{{NS['jr']}}}constraintMsg",
            f"{{{NS['jr']}}}requiredMsg",
            f"{{{NS['jr']}}}preload",
            f"{{{NS['jr']}}}preloadParams",
        ):
            value = bind.get(attr)
            if value is not None:
                key = _strip_ns(attr) if attr.startswith("{") else attr
                bind_data[key] = value
        binds[nodeset] = bind_data
        if bind_id:
            binds_by_id[bind_id] = bind_data
    return binds, binds_by_id


# --- case actions ---------------------------------------------------------


def _parse_case_actions(model: ET.Element) -> list[dict[str, Any]]:
    """Collect case-create / case-update / case-close blocks for flagging.

    These live in the CommCare-specific xmlns; they don't translate to
    SurveyCTO automatically and the agent should surface them in the
    conversion report. We just collect the raw shapes here.
    """
    actions: list[dict[str, Any]] = []
    for inst in model.findall(_q("xf:instance")):
        case_el = inst.find(f".//{{{NS['orx']}}}case") or inst.find(".//{http://commcarehq.org/case/transaction/v2}case")
        if case_el is not None:
            actions.append({"location": "instance", "raw": ET.tostring(case_el, encoding="unicode")})
    # CommCare-specific xmlns for case actions varies by form version.
    for cc_ns in ("http://commcarehq.org/case/transaction/v2",):
        for action in model.findall(f".//{{{cc_ns}}}*"):
            tag = _strip_ns(action.tag)
            if tag in ("create", "update", "close", "case"):
                actions.append({"location": "model", "action": tag, "raw": ET.tostring(action, encoding="unicode")})
    return actions


# --- body walking ---------------------------------------------------------


_CONTROL_TAGS = {"input", "select", "select1", "upload", "trigger", "secret", "range"}
_GROUP_TAGS = {"group", "repeat"}


def _walk_body(
    parent: ET.Element,
    *,
    binds: dict[str, dict[str, str]],
    binds_by_id: dict[str, dict[str, str]],
    itext_map: dict[str, dict[str, dict[str, str]]],
    languages: list[str],
    parent_path: list[str],
    questions: list[dict[str, Any]],
    warnings: list[str],
) -> None:
    """Recursively walk the body, appending one dict per question/group/repeat."""
    for el in parent:
        tag = _strip_ns(el.tag)
        if tag in _GROUP_TAGS:
            nodeset = el.get("nodeset") or el.get("ref") or ""
            name = _leaf_name(nodeset) or ""
            group_q = _build_group_or_repeat(el, tag, nodeset, name, binds, itext_map, languages, parent_path)
            questions.append(group_q)
            child_path = parent_path + [name] if name else parent_path
            _walk_body(
                el,
                binds=binds,
                binds_by_id=binds_by_id,
                itext_map=itext_map,
                languages=languages,
                parent_path=child_path,
                questions=questions,
                warnings=warnings,
            )
            questions.append(
                {
                    "name": name,
                    "type": f"end_{'repeat' if tag == 'repeat' else 'group'}",
                    "nodeset": nodeset,
                    "parent_path": list(parent_path),
                }
            )
        elif tag in _CONTROL_TAGS:
            q = _build_control(el, tag, binds, binds_by_id, itext_map, languages, parent_path, warnings)
            if q is not None:
                questions.append(q)
        elif tag == "label" or tag == "hint":
            # Stray label/hint at the body root; ignore.
            continue
        else:
            # Unknown element; recurse but don't emit.
            _walk_body(
                el,
                binds=binds,
                binds_by_id=binds_by_id,
                itext_map=itext_map,
                languages=languages,
                parent_path=parent_path,
                questions=questions,
                warnings=warnings,
            )


def _leaf_name(nodeset: str) -> str:
    if not nodeset:
        return ""
    return nodeset.rstrip("/").split("/")[-1].split("[")[0]


def _build_group_or_repeat(
    el: ET.Element,
    tag: str,
    nodeset: str,
    name: str,
    binds: dict[str, dict[str, str]],
    itext_map: dict[str, dict[str, dict[str, str]]],
    languages: list[str],
    parent_path: list[str],
) -> dict[str, Any]:
    """Build a begin_group / begin_repeat marker dict.

    Looks up the group's own <bind> (if any) for group-level relevance /
    readonly / constraint, and captures repeat-specific attributes:
    ``jr:count`` (the count expression) and ``jr:noAddRemove`` (whether
    users can dynamically add/remove instances).
    """
    bind = binds.get(nodeset, {})
    labels = _resolve_label(el, itext_map, languages)
    appearance = el.get("appearance")
    out: dict[str, Any] = {
        "name": name,
        "nodeset": nodeset,
        "type": f"begin_{'repeat' if tag == 'repeat' else 'group'}",
        "labels": labels,
        "appearance": appearance,
        "relevant": bind.get("relevant") or None,
        "readonly": bind.get("readonly", "") in ("true()", "true", "yes"),
        "parent_path": list(parent_path),
    }
    if tag == "repeat":
        # jr:count (count expression) and jr:noAddRemove are repeat-only.
        jr_count = el.get(f"{{{NS['jr']}}}count")
        if jr_count is not None:
            out["repeat_count"] = jr_count
        no_add_remove = el.get(f"{{{NS['jr']}}}noAddRemove")
        if no_add_remove is not None:
            out["no_add_remove"] = no_add_remove in ("true()", "true", "yes")
    return out


def _build_control(
    el: ET.Element,
    tag: str,
    binds: dict[str, dict[str, str]],
    binds_by_id: dict[str, dict[str, str]],
    itext_map: dict[str, dict[str, dict[str, str]]],
    languages: list[str],
    parent_path: list[str],
    warnings: list[str],
) -> dict[str, Any] | None:
    ref = el.get("ref") or ""
    bind_id = el.get("bind") or ""
    bind = binds.get(ref, {}) if ref else binds_by_id.get(bind_id, {})
    if not ref and bind:
        ref = bind.get("nodeset", "")
    if not ref and bind_id:
        ref = bind_id
    if not ref:
        warnings.append(f"<{tag}> control without ref/bind; skipped")
        return None
    if not bind:
        bind = binds.get(ref, {})
    name = _leaf_name(ref)
    labels = _resolve_label(el, itext_map, languages)
    hints = _resolve_hint(el, itext_map, languages)
    media = _resolve_media(el, itext_map, languages)
    constraint_msg = _resolve_message(el, itext_map, languages, jr_attr=bind.get("constraintMsg", ""))
    required_msg = _resolve_message(el, itext_map, languages, jr_attr=bind.get("requiredMsg", ""))
    choices = None
    upload_mediatype = None
    if tag in ("select", "select1"):
        choices = _parse_choices(el, itext_map, languages)
    if tag == "upload":
        upload_mediatype = el.get("mediatype")

    return {
        "name": name,
        "nodeset": ref,
        "type": tag,
        "xforms_type": bind.get("type", ""),
        "appearance": el.get("appearance"),
        "labels": labels,
        "hints": hints,
        "media": media,
        "required": bind.get("required", "") in ("true()", "true", "yes"),
        "required_message": required_msg,
        "constraint": bind.get("constraint") or None,
        "constraint_message": constraint_msg,
        "relevant": bind.get("relevant") or None,
        "calculate": bind.get("calculate") or None,
        "readonly": bind.get("readonly", "") in ("true()", "true", "yes"),
        "default_from_instance": None,  # CommCare defaults usually live in the primary instance; resolve if needed.
        "choices": choices,
        "upload_mediatype": upload_mediatype,
        "preload": bind.get("preload"),
        "preload_params": bind.get("preloadParams"),
        "parent_path": list(parent_path),
    }


def _parse_choices(
    el: ET.Element,
    itext_map: dict[str, dict[str, dict[str, str]]],
    languages: list[str],
) -> list[dict[str, Any]]:
    choices: list[dict[str, Any]] = []
    for item in el.findall(_q("xf:item")):
        value_el = item.find(_q("xf:value"))
        value = (value_el.text or "").strip() if value_el is not None else ""
        labels = _resolve_label(item, itext_map, languages)
        choices.append({"value": value, "labels": labels})
    # Inline itemset (less common in CommCare) — record for the agent to handle.
    itemset = el.find(_q("xf:itemset"))
    if itemset is not None:
        choices.append({"_itemset": ET.tostring(itemset, encoding="unicode")})
    return choices


# --- label / hint / media resolution --------------------------------------


def _resolve_label(
    el: ET.Element,
    itext_map: dict[str, dict[str, dict[str, str]]],
    languages: list[str],
) -> dict[str, str]:
    label_el = el.find(_q("xf:label"))
    if label_el is None:
        return {}
    return _resolve_text_element(label_el, itext_map, languages, prefer_forms=("long", "default"))


def _resolve_hint(
    el: ET.Element,
    itext_map: dict[str, dict[str, dict[str, str]]],
    languages: list[str],
) -> dict[str, str]:
    hint_el = el.find(_q("xf:hint"))
    if hint_el is None:
        return {}
    return _resolve_text_element(hint_el, itext_map, languages, prefer_forms=("default",))


def _resolve_text_element(
    text_el: ET.Element,
    itext_map: dict[str, dict[str, dict[str, str]]],
    languages: list[str],
    prefer_forms: tuple[str, ...],
) -> dict[str, str]:
    """Resolve a <label> or <hint> element into ``{lang: text}``.

    If the element has ``ref="jr:itext('id')"``, look up the itext entry
    and pick the best ``form`` per ``prefer_forms``. If the element has
    inline text instead (no ref), return ``{"": <inline>}`` keyed by empty
    string (caller decides the language).
    """
    ref = text_el.get("ref") or ""
    if ref.startswith("jr:itext(") and ref.endswith(")"):
        text_id = ref[len("jr:itext("):-1].strip("'\"")
        per_lang = itext_map.get(text_id, {})
        out: dict[str, str] = {}
        for lang in languages or list(per_lang.keys()):
            forms = per_lang.get(lang, {})
            for form in prefer_forms:
                if form in forms:
                    out[lang] = forms[form]
                    break
        return out
    inline = _flatten_text(text_el)
    return {"": inline} if inline else {}


def _resolve_media(
    el: ET.Element,
    itext_map: dict[str, dict[str, dict[str, str]]],
    languages: list[str],
) -> dict[str, dict[str, str]]:
    """Return ``{form: {lang: jr_uri}}`` for image/audio/video/markdown forms attached via itext."""
    label_el = el.find(_q("xf:label"))
    if label_el is None:
        return {}
    ref = label_el.get("ref") or ""
    if not (ref.startswith("jr:itext(") and ref.endswith(")")):
        return {}
    text_id = ref[len("jr:itext("):-1].strip("'\"")
    per_lang = itext_map.get(text_id, {})
    out: dict[str, dict[str, str]] = {}
    for lang, forms in per_lang.items():
        for form_name, value in forms.items():
            if form_name in ("image", "audio", "video", "short", "markdown") and value.startswith("jr://"):
                out.setdefault(form_name, {})[lang] = value
    return out


def _resolve_message(
    el: ET.Element,
    itext_map: dict[str, dict[str, dict[str, str]]],
    languages: list[str],
    jr_attr: str,
) -> dict[str, str] | None:
    """Resolve a jr:constraintMsg / jr:requiredMsg into ``{lang: text}``.

    CommCare uses ``jr:itext('id')`` in jr:constraintMsg / jr:requiredMsg
    to point at an itext entry; if the attribute is a plain string, that
    string is the message in every language.
    """
    if not jr_attr:
        return None
    if jr_attr.startswith("jr:itext(") and jr_attr.endswith(")"):
        text_id = jr_attr[len("jr:itext("):-1].strip("'\"")
        per_lang = itext_map.get(text_id, {})
        out: dict[str, str] = {}
        for lang in languages or list(per_lang.keys()):
            forms = per_lang.get(lang, {})
            out[lang] = forms.get("default", "")
        return {k: v for k, v in out.items() if v}
    return {"": jr_attr}


# --- name-collision detection ---------------------------------------------


def _detect_name_collisions(questions: list[dict[str, Any]], warnings: list[str]) -> None:
    """Flag leaf-name collisions across questions and groups.

    CommCare nodesets are unique by path (``/data/group1/age`` vs
    ``/data/group2/age``), but XLSForm requires globally unique ``name``
    values across the entire form. When two questions or groups share a
    leaf name from different nodeset paths, we annotate each affected
    question with ``suggested_safe_name`` (the parent-disambiguated form)
    and add a warning describing the collision. The agent can then decide
    whether to use the suggested name or ask the user for a meaningful
    one.
    """
    by_name: dict[str, list[dict[str, Any]]] = {}
    for q in questions:
        name = q.get("name") or ""
        type_ = q.get("type", "")
        # Skip end markers (they share names with their begin markers by design).
        if type_.startswith("end_"):
            continue
        if not name:
            continue
        by_name.setdefault(name, []).append(q)

    for name, group in by_name.items():
        if len(group) <= 1:
            continue
        # Collision. Suggest disambiguated names using the parent path.
        for q in group:
            parent_path = q.get("parent_path") or []
            if parent_path:
                suggested = "_".join(list(parent_path) + [name])
            else:
                suggested = name
            q["suggested_safe_name"] = suggested
        nodesets = ", ".join(q.get("nodeset", "?") for q in group)
        warnings.append(
            f"Name collision on '{name}': {len(group)} occurrences at {nodesets}. "
            "XLSForm requires globally unique names; see each question's "
            "'suggested_safe_name' for a parent-path-disambiguated alternative, "
            "or ask the user for meaningful names."
        )


# --- CLI ------------------------------------------------------------------


def _main() -> None:
    import argparse
    import json
    import sys

    parser = argparse.ArgumentParser(description="Parse a CommCare XForms XML file.")
    parser.add_argument("path", help="Path to the .xml form definition.")
    args = parser.parse_args()
    form = load_xform(args.path)
    json.dump(form, sys.stdout, indent=2, default=str)
    sys.stdout.write("\n")


if __name__ == "__main__":
    _main()

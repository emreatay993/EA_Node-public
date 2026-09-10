# Purpose: Build bounded discovery and complete data-only Search snapshots on the native owner thread.
# Map: subsystems/addons.md
# Tests: tests/mechanical_catalogue/test_open_model.py, tests/mechanical_catalogue/test_search_tree.py, tests/mechanical_catalogue/test_result_tables.py, tests/mechanical_catalogue/test_scripts.py

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from typing import Any

from ea_node_editor.addons.mechanical.contracts import (
    CATALOGUE_COLUMNS,
    encode_selector,
    object_value,
    property_value,
    search_details_table,
)


SEARCH_FILTERS = (
    "name", "tag", "type", "state", "coordinate_system", "model",
    "graphics", "environment", "scoping", "property_name", "property_value",
)
_FORCE = "Ansys.ACT.Automation.Mechanical.BoundaryConditions.Force"
_FORCE_REACTION = "Ansys.ACT.Automation.Mechanical.Results.ProbeResults.ForceReaction"
_BOLT_PRETENSION = "Ansys.ACT.Automation.Mechanical.BoundaryConditions.BoltPretension"
_NAMED_SELECTION = "Ansys.ACT.Automation.Mechanical.NamedSelection"
_COORDINATE_SYSTEM = "Ansys.ACT.Automation.Mechanical.CoordinateSystem"
_CONTACT_REGION = "Ansys.ACT.Automation.Mechanical.Connections.ContactRegion"
_SCOPE_FIELDS = {
    _FORCE: (("primary", "Location"),),
    _NAMED_SELECTION: (("primary", "Location"),),
    _CONTACT_REGION: (("source", "SourceLocation"), ("target", "TargetLocation")),
    _COORDINATE_SYSTEM: (),
}


class SearchIncomplete(ValueError):
    pass


def _blank(identity: dict[str, Any], kind: str) -> dict[str, Any]:
    row = {name: None for name in CATALOGUE_COLUMNS}
    row.update({name: "" for name in CATALOGUE_COLUMNS if name not in {
        "schema_version", "model_revision", "producer_iteration", "object_id",
        "parent_id", "analysis_id", "scalar_value", "has_tabular_data",
        "row_count", "column_count", "view_index", "omitted_rows",
        "catalogue_complete", "related_object_id", "scope_count", "body_hidden",
    }})
    row.update(identity)
    row["record_kind"] = kind
    return row


def _safe(obj: Any, name: str, default: Any = None) -> Any:
    try:
        return getattr(obj, name)
    except Exception:  # native metadata getters are independently fallible
        return default


def _type_name(obj: Any) -> str:
    try:
        return str(obj.GetType().FullName)
    except Exception:
        return type(obj).__name__


def _path(obj: Any) -> str:
    parts: list[str] = []
    seen: set[int] = set()
    while obj is not None and id(obj) not in seen:
        seen.add(id(obj))
        name = str(_safe(obj, "Name", "")).strip()
        if name:
            parts.append(name)
        obj = _safe(obj, "Parent")
    return "/".join(reversed(parts))


def _read(obj: Any, name: str) -> tuple[bool, Any]:
    try:
        return True, getattr(obj, name)
    except Exception:
        return False, None


def _operand(text: str) -> str:
    text = text.strip()
    if not text.startswith('"'):
        if '"' in text:
            raise ValueError("Malformed quoted operand")
        return text
    try:
        value, end = json.JSONDecoder().raw_decode(text)
    except json.JSONDecodeError as exc:
        raise ValueError("Malformed JSON-style quoted operand") from exc
    if not isinstance(value, str) or text[end:].strip():
        raise ValueError("Quoted operand must be one complete JSON string")
    return value


def property_value_query(query: str) -> tuple[str | None, str, bool]:
    quoted = escaped = False
    delimiter = None
    for index, char in enumerate(query):
        if escaped:
            escaped = False
        elif quoted and char == "\\":
            escaped = True
        elif char == '"':
            quoted = not quoted
        elif char == "=" and not quoted:
            delimiter = index
            break
    if quoted or escaped:
        raise ValueError("Malformed JSON-style quoted operand")
    if delimiter is None:
        value = _operand(query)
        return None, value, bool(query.strip()) and value == ""
    caption = _operand(query[:delimiter])
    if not caption:
        raise ValueError("Property caption cannot be empty")
    value = _operand(query[delimiter + 1 :])
    return caption, value, value == ""


def _match_text(candidate: object, query: str, *, exact: bool, case_sensitive: bool) -> bool:
    left, right = str(candidate), query
    if not case_sensitive:
        left, right = left.casefold(), right.casefold()
    return left == right if exact else right in left


def _match_values(
    values: list[tuple[str, bool]], query: str, *, filter_code: str,
    exact: bool, case_sensitive: bool,
) -> bool:
    terms = query.split() if filter_code == "name" and not exact else [query]
    return all(
        any(
            str(value) == str(term)
            if identity
            else _match_text(value, term, exact=exact, case_sensitive=case_sensitive)
            for value, identity in values
        )
        for term in terms
    )


def _predicate(
    relation: Mapping[str, Any], query: str, *, filter_code: str,
    exact: bool, case_sensitive: bool, invert: bool,
) -> bool:
    status = relation["status"]
    if status == "not_applicable":
        return False
    if status == "unavailable":
        raise SearchIncomplete(f"mechanical.search_incomplete: {filter_code}")
    if status != "available":
        raise ValueError("Unknown search availability")
    matched = _match_values(
        list(relation.get("values", ())), query,
        filter_code=filter_code, exact=exact, case_sensitive=case_sensitive,
    )
    if not matched and relation.get("incomplete"):
        raise SearchIncomplete(f"mechanical.search_incomplete: {filter_code}")
    return not matched if invert else matched


def _relations_predicate(
    relations: list[Mapping[str, Any]], query: str, *, filter_code: str,
    exact: bool, case_sensitive: bool, invert: bool,
) -> tuple[bool, Mapping[str, Any] | None]:
    available = [item for item in relations if item["status"] == "available"]
    unknown = any(item["status"] == "unavailable" for item in relations)
    if not available and not unknown:
        return False, None
    matched = next(
        (
            item for item in available
            if _match_values(
                list(item.get("values", ())), query, filter_code=filter_code,
                exact=exact, case_sensitive=case_sensitive,
            )
        ),
        None,
    )
    if matched is None and (
        unknown or any(item.get("incomplete") for item in available)
    ):
        raise SearchIncomplete(f"mechanical.search_incomplete: {filter_code}")
    result = matched is not None
    return (not result if invert else result), (available[0] if invert and available else matched)


def _relation(status: str, values=(), **metadata: Any) -> dict[str, Any]:
    return {"status": status, "values": list(values), **metadata}


def _object_contexts(objects: list[Any]) -> list[dict[str, Any]]:
    ids = {int(_safe(obj, "ObjectId", -1)): obj for obj in objects}
    analysis_ids = {
        object_id
        for object_id, obj in ids.items()
        if object_id >= 0 and _type_name(obj).endswith(".Analysis")
    }
    contexts = []
    for obj in objects:
        object_id = int(_safe(obj, "ObjectId", -1))
        if object_id < 0:
            continue
        parent = _safe(obj, "Parent")
        parent_id = _safe(parent, "ObjectId") if parent is not None else None
        analysis_id = object_id if object_id in analysis_ids else None
        cursor = parent
        while analysis_id is None and cursor is not None:
            candidate = _safe(cursor, "ObjectId")
            if candidate is not None and int(candidate) in analysis_ids:
                analysis_id = int(candidate)
            cursor = _safe(cursor, "Parent")
        name_ok, name = _read(obj, "Name")
        try:
            api_type, type_ok = str(obj.GetType().FullName), True
        except Exception:
            api_type, type_ok = "", False
        category_ok, category = _read(obj, "DataModelObjectCategory")
        contexts.append({
            "native": obj,
            "object_id": object_id,
            "parent_id": None if parent_id is None else int(parent_id),
            "analysis_id": analysis_id,
            "object_path": _path(obj) or str(object_id),
            "display_name": str(name) if name_ok else "",
            "name_available": name_ok,
            "api_type": api_type,
            "type_available": type_ok,
            "category": str(category) if category_ok else "",
            "category_available": category_ok,
        })
    return contexts


def _tag_map(data_model: Any, objects: list[Any]) -> tuple[dict[int, list[str]], bool]:
    direct = {
        int(_safe(obj, "ObjectId", -1)): list(_safe(obj, "_corex_direct_tags", ()) or ())
        for obj in objects
    }
    remote_availability = [_safe(obj, "_corex_tags_available") for obj in objects]
    if remote_availability and all(type(value) is bool for value in remote_availability):
        return direct, all(remote_availability)
    if any(direct.values()):
        return direct, True
    ok, tags = _read(data_model, "ObjectTags") if data_model is not None else (False, None)
    if not ok:
        return direct, False
    try:
        for tag in list(tags):
            name = str(tag.Name)
            for obj in list(tag.Objects):
                direct.setdefault(int(obj.ObjectId), []).append(name)
    except Exception:
        return direct, False
    return direct, True


def _coordinate_relation(context: Mapping[str, Any]) -> dict[str, Any]:
    obj, api_type = context["native"], context["api_type"]
    if api_type == _NAMED_SELECTION:
        return _relation("available", [("Unspecified", False)], relation_role="assignment", property_key="")
    field = "CoordinateSystem" if api_type == _FORCE else "Orientation" if api_type == _FORCE_REACTION else ""
    if not field:
        return _relation("not_applicable")
    ok, value = _read(obj, field)
    if not ok:
        return _relation("unavailable", relation_role="assignment", property_key=field)
    if value is None:
        label = "Solution" if api_type == _FORCE_REACTION else "Unspecified"
        return _relation("available", [(label, False)], relation_role="assignment", property_key=field, related_label=label)
    try:
        return _relation(
            "available", [("Explicit assignment", False), (str(value.Name), False), (str(int(value.ObjectId)), True)],
            relation_role="assignment", property_key=field,
            related_label=str(value.Name), related_object_id=int(value.ObjectId),
        )
    except Exception:
        return _relation("unavailable", relation_role="assignment", property_key=field)


def _scope_kind(value: Any) -> tuple[str, str, int | None, int | None, bool]:
    if value is None:
        return "empty_explicit_scope", "", None, 0, False
    category_ok, category_value = _read(value, "DataModelObjectCategory")
    category = str(category_value) if category_ok else ""
    object_ok, object_value = _read(value, "ObjectId")
    name_ok, name_value = _read(value, "Name")
    object_id = int(object_value) if object_ok and object_value is not None else None
    name = str(name_value) if name_ok and name_value is not None else ""
    if category.endswith("NamedSelection") or category == "NamedSelection":
        count_ok, count_value = _read(value, "TotalSelection")
        count = int(count_value) if count_ok and type(count_value) is int and count_value >= 0 else None
        return "named_selection", name, object_id, count, not name_ok or object_id is None or count is None
    if object_id is not None:
        return (
            "referenced_object" if category_ok else "",
            name,
            object_id,
            None,
            not category_ok or not name_ok,
        )
    ok, selection_type = _read(value, "SelectionType")
    ids_ok, ids = _read(value, "Ids")
    if not ok or not ids_ok:
        raise ValueError("Unclassified scope value")
    identifiers = list(ids)
    if not identifiers:
        return "empty_explicit_scope", "", None, 0, False
    folded = str(selection_type).casefold()
    if "node" in folded:
        kind = "mesh_nodes"
    elif "element" in folded:
        kind = "mesh_elements"
    elif "geometr" in folded:
        kind = "geometry"
    else:
        raise ValueError("Unclassified SelectionType")
    return kind, "", None, len(identifiers), False


def _scope_relations(context: Mapping[str, Any]) -> list[dict[str, Any]]:
    fields = _SCOPE_FIELDS.get(context["api_type"])
    if fields is None:
        return [_relation("not_applicable")]
    if not fields:
        return [_relation("available", [("No explicit scope", False), ("no_explicit_scope", False)], relation_role="primary", scope_kind="no_explicit_scope")]
    relations = []
    for role, field in fields:
        ok, value = _read(context["native"], field)
        if not ok:
            relations.append(_relation("unavailable", relation_role=role))
            continue
        try:
            kind, label, object_id, count, incomplete = _scope_kind(value)
        except Exception:
            relations.append(_relation("unavailable", relation_role=role))
            continue
        visible = {
            "geometry": "Geometry", "mesh_nodes": "Mesh nodes", "mesh_elements": "Mesh elements",
            "named_selection": "Named selection", "referenced_object": "Referenced object",
            "empty_explicit_scope": "Empty explicit scope", "no_explicit_scope": "No explicit scope",
        }.get(kind, "")
        values = [(visible, False), (kind, False)] if kind else []
        if label:
            values.append((label, False))
        if object_id is not None:
            values.append((str(object_id), True))
        if count is not None:
            values.append((str(count), False))
        relations.append(_relation(
            "available", values, relation_role=role, related_label=label,
            related_object_id=object_id, scope_kind=kind, scope_count=count,
            incomplete=incomplete,
        ))
    return relations


def _environment_relations(
    context: Mapping[str, Any], contexts: list[dict[str, Any]], model: Any,
) -> list[dict[str, Any]]:
    analyses = [item for item in contexts if item["analysis_id"] == item["object_id"]]
    if context["analysis_id"] is not None:
        analysis = next(item for item in analyses if item["object_id"] == context["analysis_id"])
        return [_relation(
            "available", [(analysis["display_name"], False), (str(analysis["object_id"]), True)],
            relation_role="owner", related_label=analysis["display_name"],
            related_object_id=analysis["object_id"], activation_state="ObjectActive",
            incomplete=not analysis["name_available"],
        )]
    if context["api_type"] != _BOLT_PRETENSION:
        return [_relation("not_applicable")]
    relations = []
    for analysis in analyses:
        try:
            state = str(model.GetActivationStatusForAnalysis(context["object_id"], analysis["object_id"]))
        except Exception:
            relations.append(_relation("unavailable", relation_role="activation"))
            continue
        if state == "ObjectActive":
            relations.append(_relation(
                "available", [(analysis["display_name"], False), (str(analysis["object_id"]), True)],
                relation_role="activation", related_label=analysis["display_name"],
                related_object_id=analysis["object_id"], activation_state=state,
                incomplete=not analysis["name_available"],
            ))
        elif state == "ObjectInactive":
            relations.append(_relation("available", (), relation_role="activation", activation_state=state))
        elif state == "ObjectNotApplicable":
            relations.append(_relation("not_applicable", relation_role="activation", activation_state=state))
        else:
            relations.append(_relation("unavailable", relation_role="activation", activation_state=state))
    return relations or [_relation("not_applicable")]


def _object_relations(
    context: Mapping[str, Any], *, filter_code: str, contexts: list[dict[str, Any]],
    model: Any, identity: Mapping[str, Any], tags: Mapping[int, list[str]], tags_available: bool,
) -> list[dict[str, Any]]:
    obj = context["native"]
    if filter_code in {"coordinate_system", "graphics", "environment", "scoping"} and not context["type_available"]:
        return [_relation("unavailable")]
    if filter_code == "name":
        return [_relation("available", [(context["display_name"], False)])] if context["name_available"] else [_relation("unavailable")]
    if filter_code == "tag":
        return [_relation("available" if tags_available else "unavailable", [(name, False) for name in tags.get(context["object_id"], ())])]
    if filter_code == "type":
        values = [(context["api_type"], False)] if context["type_available"] else []
        if context["category"]:
            values.append((context["category"], False))
        return [_relation(
            "available" if values else "unavailable", values,
            incomplete=not context["type_available"] or not context["category_available"],
        )]
    if filter_code == "state":
        values, incomplete = [], False
        for field in ("ObjectState", "Suppressed"):
            ok, value = _read(obj, field)
            if not ok:
                incomplete = True
            elif field == "Suppressed":
                values.append(("Suppressed" if bool(value) else "Unsuppressed", False))
            else:
                native = str(value)
                values.append((native, False))
                if native == "LicenseConflict":
                    values.append(("Not licensed", False))
                elif native == "UnderDefined":
                    values.append(("Underdefined", False))
        return [_relation("available" if values else "unavailable", values, incomplete=incomplete)]
    if filter_code == "coordinate_system":
        return [_coordinate_relation(context)]
    if filter_code == "model":
        values = [("Current document", False), (identity["system_key"], False), (identity["document_id"], True), (identity["source_key"], True)]
        try:
            source_id = getattr(obj, "ImportableObjectSourceId")
            ok = True
        except AttributeError:
            source_id, ok = None, True
        except Exception:
            return [_relation(
                "available", values, relation_role="source",
                related_label="Current document", raw_source_id="", incomplete=True,
            )]
        if source_id not in {None, ""}:
            values.append((str(source_id), True))
        raw_source = "" if source_id in {None, ""} else str(source_id)
        return [_relation(
            "available", values, relation_role="source",
            related_label="Current document", raw_source_id=raw_source,
        )]
    if filter_code == "graphics":
        if context["api_type"] != "Ansys.ACT.Automation.Mechanical.Body":
            return [_relation("not_applicable")]
        ok, hidden = _read(obj, "Hidden")
        return [_relation("available", [("Hidden bodies" if hidden else "Shown bodies", False)], relation_role="body", body_hidden=bool(hidden))] if ok and type(hidden) is bool else [_relation("unavailable", relation_role="body")]
    if filter_code == "environment":
        return _environment_relations(context, contexts, model)
    if filter_code == "scoping":
        return _scope_relations(context)
    raise ValueError(f"Unknown Mechanical search filter: {filter_code}")


def _properties(obj: Any, include_hidden: bool) -> tuple[list[Any], str]:
    field = "Properties" if include_hidden else "VisibleProperties"
    ok, value = _read(obj, field)
    if not ok:
        return [], f"{field} unavailable"
    try:
        return list(value), ""
    except Exception as exc:
        return [], f"{field}: {type(exc).__name__}"


def _property_payload(context: Mapping[str, Any], prop: Any, ordinal: int, identity: Mapping[str, Any]) -> tuple[Any, dict[str, Any]]:
    api_name = str(_safe(prop, "APIName", "") or "")
    name = str(_safe(prop, "Name", "") or "")
    key = api_name if api_name not in {"", "None"} else name if name not in {"", "None"} else f"property:{ordinal}"
    caption_ok, caption = _read(prop, "Caption")
    value_ok, display = _read(prop, "StringValue")
    caption = str(caption) if caption_ok else key
    display = str(display) if value_ok else ""
    internal_error = False
    try:
        internal = getattr(prop, "InternalValue")
    except AttributeError:
        internal = None
    except Exception:
        internal, internal_error = None, True
    output_error = False
    if internal is None:
        output = None
    else:
        try:
            output = getattr(internal, "Output")
        except AttributeError:
            output = None
        except Exception:
            output, output_error = None, True
    inputs_ok, inputs = _read(internal, "Inputs") if output is not None else (True, [])
    try:
        input_count = len(list(inputs or ())) if inputs_ok else None
    except Exception:
        input_count = None
    definition_ok, definition_value = _read(output, "DefinitionType") if output is not None else (True, "")
    definition = str(definition_value) if definition_ok else ""
    count_ok, count_value = _read(output, "DiscreteValueCount") if output is not None else (True, None)
    count_valid = type(count_value) is int and count_value >= 0
    count = int(count_value) if count_valid else None
    formula_ok, formula_value = _read(output, "Formula") if output is not None else (True, "")
    formula = str(formula_value or "") if formula_ok else ""
    formula = "" if formula == "None" else formula
    unit = str(_safe(output, "Unit", "") or "")
    unit = "" if unit == "None" else unit
    has_tabular = definition == "Discrete" and count is not None and count > 1
    kind = "formula" if definition == "Formula" else "tabular" if has_tabular else "scalar"
    scalar = None
    if output is None:
        candidate = _safe(internal, "Value")
        if type(candidate) in {int, float} and math.isfinite(candidate):
            scalar = float(candidate)
        unit = str(_safe(internal, "Unit", unit) or unit)
    table_key = f"{context['object_id']}:{key}:field" if output is not None else ""
    tables = [{
        "table_key": table_key, "table_family": "field_definition",
        "definition_kind": "Field", "row_count": count,
        "column_count": None if input_count is None else input_count + 1,
    }] if has_tabular else []
    selector = encode_selector(
        "property", document_id=identity["document_id"], system_key=identity["system_key"],
        object_path=context["object_path"], native_id=key,
    )
    payload = {
        **{field: identity[field] for field in ("run_id", "session_id", "document_id", "source_key", "system_key", "model_revision")},
        "object_id": context["object_id"], "object_path": context["object_path"],
        "property_key": key, "caption": caption, "definition_kind": kind,
        "display_value": display, "value_status": "available" if value_ok else "unreadable",
        "scalar_value": scalar, "unit": unit,
        "quantity_name": str(_safe(output if output is not None else internal, "QuantityName", "") or ""),
        "formula": formula, "has_tabular_data": has_tabular, "tables": tables,
        "selector_code": selector,
    }
    search = {
        "caption": caption, "caption_available": caption_ok,
        "values": [(display, False)] if value_ok else [],
        "display_available": value_ok,
    }
    if formula:
        search["values"].append((formula, False))
    if has_tabular:
        search["values"].append(("Tabular data", False))
    search["value_available"] = bool(value_ok or formula or has_tabular)
    search["incomplete"] = (
        not value_ok
        or internal_error
        or output_error
        or output is not None
        and (
            not definition_ok
            or definition == "Formula" and not formula_ok
            or definition == "Discrete" and (not count_ok or not count_valid)
        )
    )
    return property_value(payload), search


def _object_value(context: Mapping[str, Any], identity: Mapping[str, Any]):
    return object_value({
        **{field: identity[field] for field in ("run_id", "session_id", "document_id", "source_key", "system_key", "model_revision")},
        **{field: context[field] for field in ("object_id", "parent_id", "object_path", "display_name", "api_type", "category", "analysis_id")},
        "selector_code": encode_selector(
            "object", document_id=identity["document_id"], system_key=identity["system_key"],
            object_path=context["object_path"], native_id=context["object_id"],
        ),
    })


def _detail(context: Mapping[str, Any], *, prop: Any = None, relation: Mapping[str, Any] | None = None, diagnostic: str = "") -> dict[str, Any]:
    payload = prop.payload if prop is not None else {}
    relation = relation or {}
    value_status = str(payload.get("value_status", ""))
    if value_status and value_status != "available" and not diagnostic:
        diagnostic = f"Property display value is {value_status}"
    return {
        "object_id": context["object_id"], "object_path": context["object_path"],
        "display_name": context["display_name"], "api_type": context["api_type"],
        "property_key": payload.get("property_key", relation.get("property_key", "")), "property_caption": payload.get("caption", ""),
        "display_value": payload.get("display_value", ""), "unit": payload.get("unit", ""),
        "definition_kind": payload.get("definition_kind", ""), "has_tabular_data": payload.get("has_tabular_data"),
        "relation_kind": relation.get("relation_kind", ""), "relation_role": relation.get("relation_role", ""),
        "related_label": relation.get("related_label", ""), "raw_source_id": relation.get("raw_source_id", ""),
        "scope_kind": relation.get("scope_kind", ""), "scope_count": relation.get("scope_count"),
        "body_hidden": relation.get("body_hidden"),
        "availability": value_status or relation.get("status", "available"),
        "diagnostic": diagnostic,
    }


def search_tree(
    *, tree: Any, model: Any, data_model: Any, identity: Mapping[str, Any],
    filter_code: str, query: str, match_mode: str, case_sensitive: bool,
    include_hidden_properties: bool, invert: bool,
    typed_selector: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    if filter_code not in SEARCH_FILTERS:
        raise ValueError(f"Unknown Mechanical search filter: {filter_code}")
    if match_mode not in {"contains", "exact"}:
        raise ValueError("Mechanical search Match must be contains or exact")
    if filter_code == "scoping" and typed_selector is None and query.strip().casefold() in {
        "partial", "partial scope", "partial scoping", "lost", "lost scope", "lost scoping",
    }:
        raise ValueError("Historical partial/lost scoping is unsupported")
    caption_query = value_query = None
    explicit_empty = False
    unrestricted = not query.strip() and typed_selector is None
    if filter_code == "property_value" and typed_selector is None:
        caption_query, value_query, explicit_empty = property_value_query(query)
        unrestricted = not query.strip() and not explicit_empty
    objects = list(tree.AllObjects)
    contexts = _object_contexts(objects)
    tags, tags_available = _tag_map(data_model, objects)
    matched_objects: list[Any] = []
    matched_properties: list[Any] = []
    details: list[dict[str, Any]] = []
    seen_properties: set[tuple[int, str]] = set()
    typed_matches = 0
    for context in contexts:
        if typed_selector is not None and typed_selector["kind"] == "object":
            object_match = (
                type(typed_selector["native_id"]) is int
                and typed_selector["native_id"] == context["object_id"]
                and typed_selector["object_path"] == context["object_path"]
            )
            if object_match:
                typed_matches += 1
            detail_relation = None
        elif filter_code in {"property_name", "property_value"} or typed_selector is not None:
            object_match = False
            detail_relation = None
        else:
            relations = _object_relations(
                context, filter_code=filter_code, contexts=contexts, model=model,
                identity=identity, tags=tags, tags_available=tags_available,
            )
            if unrestricted:
                applicable = [item for item in relations if item["status"] != "not_applicable"]
                object_match = bool(applicable) and not invert
                detail_relation = applicable[0] if applicable else None
            else:
                object_match, detail_relation = _relations_predicate(
                    relations, query, filter_code=filter_code,
                    exact=match_mode == "exact", case_sensitive=case_sensitive,
                    invert=invert,
                )
        needs_properties = (
            filter_code in {"property_name", "property_value"}
            or object_match
            or typed_selector is not None and typed_selector["kind"] == "property"
        )
        if not needs_properties:
            continue
        properties, property_error = _properties(context["native"], include_hidden_properties)
        property_values = []
        for ordinal, prop in enumerate(properties):
            value, search = _property_payload(context, prop, ordinal, identity)
            key = (context["object_id"], value.payload["property_key"])
            if key in seen_properties:
                continue
            property_match = False
            if typed_selector is not None and typed_selector["kind"] == "property":
                property_match = (
                    typed_selector["native_id"] == value.payload["property_key"]
                    and typed_selector["object_path"] == context["object_path"]
                )
            elif filter_code == "property_name":
                if unrestricted:
                    property_match = not invert
                elif not search["caption_available"]:
                    raise SearchIncomplete("mechanical.search_incomplete: property_name")
                else:
                    property_match = _match_text(search["caption"], query, exact=match_mode == "exact", case_sensitive=case_sensitive)
                    property_match = not property_match if invert else property_match
            elif filter_code == "property_value":
                if unrestricted:
                    property_match = not invert
                else:
                    caption_match = True
                    if caption_query is not None:
                        if not search["caption_available"]:
                            raise SearchIncomplete("mechanical.search_incomplete: property_value")
                        caption_match = _match_text(
                            search["caption"], caption_query, exact=match_mode == "exact",
                            case_sensitive=case_sensitive,
                        )
                    property_match = False
                    if caption_match:
                        if not search["value_available"]:
                            raise SearchIncomplete("mechanical.search_incomplete: property_value")
                        candidates = list(search["values"])
                        if explicit_empty:
                            if not search["display_available"]:
                                raise SearchIncomplete("mechanical.search_incomplete: property_value")
                            property_match = any(candidate == "" for candidate, _identity in candidates)
                        else:
                            property_match = _match_values(
                                candidates, value_query if value_query is not None else query,
                                filter_code="property_value", exact=match_mode == "exact",
                                case_sensitive=case_sensitive,
                            )
                            if not property_match and search["incomplete"]:
                                raise SearchIncomplete("mechanical.search_incomplete: property_value")
                    property_match = not property_match if invert else property_match
            if property_match:
                if typed_selector is not None:
                    typed_matches += 1
                seen_properties.add(key)
                matched_properties.append(value)
                details.append(_detail(context, prop=value))
                object_match = True
            property_values.append(value)
        if filter_code in {"property_name", "property_value"} and property_error and not properties:
            raise SearchIncomplete(f"mechanical.search_incomplete: {filter_code}: {context['object_path']}: {property_error}")
        if object_match:
            matched_objects.append(_object_value(context, identity))
            if filter_code not in {"property_name", "property_value"} and typed_selector is None:
                details.append(_detail(context, relation={**(detail_relation or {}), "relation_kind": {
                    "coordinate_system": "coordinate_system", "model": "source_model", "graphics": "body_visibility",
                    "environment": "environment", "scoping": "scope",
                }.get(filter_code, "")}, diagnostic=property_error))
                for value in property_values:
                    key = (context["object_id"], value.payload["property_key"])
                    if key not in seen_properties:
                        seen_properties.add(key)
                        matched_properties.append(value)
            elif typed_selector is not None and typed_selector["kind"] == "object":
                details.append(_detail(context, diagnostic=property_error))
                for value in property_values:
                    key = (context["object_id"], value.payload["property_key"])
                    if key not in seen_properties:
                        seen_properties.add(key)
                        matched_properties.append(value)
    if typed_selector is not None and typed_matches != 1:
        raise ValueError("mechanical.selector_missing: query selector is unavailable in the current Model")
    if len(matched_objects) + len(matched_properties) > 100_000:
        raise ValueError("mechanical.capacity_exceeded: search exceeds 100000 typed outputs")
    return {
        "objects": matched_objects,
        "properties": matched_properties,
        "details": search_details_table(details),
    }


def collect_catalogue_rows(
    *, tree: Any, graphics: Any, identity: dict[str, Any], systems: list[dict[str, str]],
    status: str = "opened", message: str = "", model: Any = None, data_model: Any = None,
    operations: list[Mapping[str, str]] | None = None,
) -> list[dict[str, Any]]:
    """Read descriptors only; never inspect table cells or execute authored scripts."""
    rows: list[dict[str, Any]] = []
    metadata_errors: list[str] = []
    summary = _blank(identity, "session")
    summary.update(status=status, message=message, catalogue_complete=True, omitted_rows=0)
    rows.append(summary)
    for operation in operations or ():
        row = _blank(identity, "operation")
        row.update(status=str(operation["status"]), message=str(operation["message"]))
        rows.append(row)
    for system in systems:
        row = _blank(identity, "system")
        key, label = str(system["key"]), str(system["label"])
        row.update(system_key=key, system_label=label)
        row["selector_code"] = encode_selector(
            "system", document_id=identity["document_id"], system_key=key,
            object_path="", native_id=key,
        )
        rows.append(row)
    if tree is None:
        for row in rows:
            row.pop("view_export_path", None)
        return rows
    objects = list(tree.AllObjects)
    contexts = _object_contexts(objects)
    contexts_by_id = {context["object_id"]: context for context in contexts}
    analysis_ids = {
        int(_safe(item, "ObjectId")): int(_safe(item, "ObjectId"))
        for item in objects if _type_name(item).endswith(".Analysis")
    }
    for obj in objects:
        object_id = int(_safe(obj, "ObjectId", -1))
        if object_id < 0:
            continue
        parent = _safe(obj, "Parent")
        parent_id = _safe(parent, "ObjectId") if parent is not None else None
        parent_id = int(parent_id) if parent_id is not None else None
        object_path = _path(obj) or str(object_id)
        analysis_id = object_id if object_id in analysis_ids else None
        cursor = parent
        while analysis_id is None and cursor is not None:
            candidate = _safe(cursor, "ObjectId")
            if candidate is not None and int(candidate) in analysis_ids:
                analysis_id = int(candidate)
            cursor = _safe(cursor, "Parent")
        row = _blank(identity, "object")
        row.update(
            object_id=object_id, parent_id=parent_id, analysis_id=analysis_id,
            object_path=object_path, display_name=str(_safe(obj, "Name", "")),
            api_type=_type_name(obj),
        )
        row["selector_code"] = encode_selector(
            "object", document_id=identity["document_id"],
            system_key=identity["system_key"], object_path=object_path,
            native_id=object_id,
        )
        rows.append(row)
        context = contexts_by_id[object_id]
        descriptors: list[tuple[str, str, str, int | None]] = []
        table = _safe(obj, "TabularData")
        if table is not None:
            try:
                keys = [str(key) for key in table.Keys]
            except Exception:
                keys = []
            descriptors.append((
                f"{object_id}:tabular_data", "result_history_summary", "ITable", len(keys)
            ))
        api_type = _type_name(obj)
        if api_type.endswith(".ForceReaction"):
            descriptors.append((
                f"{object_id}:force_reaction", "result_history_summary",
                "ForceReaction RetrieveResult", 6,
            ))
        elif (
            ".Results." in api_type
            and ".ProbeResults." not in api_type
            and not api_type.endswith(".Solution")
        ):
            descriptors.extend((
                (f"{object_id}:configured_summary", "result_history_summary", "Stored-set summary", 5),
                (f"{object_id}:plot_data", "spatial_samples", "PlotData", None),
            ))
        if api_type.endswith(".MeshControls.Mesh") or api_type.endswith(".MeshControlWorksheet"):
            descriptors.append((
                f"{object_id}:mesh_worksheet", "supported_worksheet", "Mesh-control worksheet", 5
            ))
        if api_type.endswith(".LayeredSection") or api_type.endswith(".LayeredSectionWorksheet"):
            descriptors.append((
                f"{object_id}:layered_section", "supported_worksheet", "Layered-section worksheet", 5
            ))
        for table_key, table_family, definition_kind, column_count in descriptors:
            trow = _blank(identity, "table")
            trow.update(
                object_id=object_id, analysis_id=analysis_id,
                object_path=object_path, display_name=str(_safe(obj, "Name", "")),
                api_type=api_type, table_key=table_key,
                table_family=table_family, definition_kind=definition_kind,
                row_count=None, column_count=column_count,
            )
            trow["selector_code"] = encode_selector(
                "table", document_id=identity["document_id"],
                system_key=identity["system_key"], object_path=object_path,
                native_id=table_key,
            )
            rows.append(trow)
        try:
            properties = list(obj.VisibleProperties)
        except Exception as exc:
            properties = []
            metadata_errors.append(f"{object_path}: VisibleProperties: {type(exc).__name__}")
        for ordinal, prop in enumerate(properties):
            value, search = _property_payload(context, prop, ordinal, identity)
            payload = value.payload
            if search["incomplete"]:
                metadata_errors.append(
                    f"{object_path}: {payload['property_key']}: property metadata incomplete"
                )
            prow = _blank(identity, "property")
            prow.update(
                object_id=object_id, analysis_id=analysis_id, object_path=object_path,
                display_name=str(_safe(obj, "Name", "")), api_type=_type_name(obj),
                property_key=payload["property_key"], property_caption=payload["caption"],
                display_value=payload["display_value"],
                definition_kind=payload["definition_kind"],
                scalar_value=payload["scalar_value"],
                has_tabular_data=payload["has_tabular_data"],
                unit=payload["unit"], quantity_name=payload["quantity_name"],
                formula=payload["formula"],
            )
            if payload["tables"]:
                descriptor = payload["tables"][0]
                prow.update(
                    table_key=descriptor["table_key"],
                    table_family=descriptor["table_family"],
                    row_count=descriptor["row_count"],
                    column_count=descriptor["column_count"],
                )
            prow["selector_code"] = payload["selector_code"]
            rows.append(prow)
            for descriptor in payload["tables"]:
                trow = _blank(identity, "table")
                trow.update(
                    object_id=object_id, analysis_id=analysis_id,
                    object_path=object_path, display_name=str(_safe(obj, "Name", "")),
                    api_type=_type_name(obj), property_key=payload["property_key"],
                    property_caption=payload["caption"],
                    table_key=descriptor["table_key"], table_family=descriptor["table_family"],
                    definition_kind=descriptor["definition_kind"],
                    row_count=descriptor["row_count"], column_count=descriptor["column_count"],
                    unit=payload["unit"], quantity_name=payload["quantity_name"],
                    formula=payload["formula"],
                )
                trow["selector_code"] = encode_selector(
                    "table", document_id=identity["document_id"],
                    system_key=identity["system_key"], object_path=object_path,
                    native_id=descriptor["table_key"],
                )
                rows.append(trow)
        relation_groups = {
            relation_kind: _object_relations(
                context, filter_code=filter_code, contexts=contexts, model=model,
                identity=identity, tags={}, tags_available=True,
            )
            for relation_kind, filter_code in (
                ("coordinate_system", "coordinate_system"),
                ("source_model", "model"),
                ("body_visibility", "graphics"),
                ("environment", "environment"),
                ("scope", "scoping"),
            )
        }
        for relation_kind, relations in relation_groups.items():
            for relation in relations:
                rrow = _blank(identity, "relation")
                rrow.update(
                    object_id=object_id, analysis_id=analysis_id,
                    object_path=object_path, display_name=str(_safe(obj, "Name", "")),
                    api_type=_type_name(obj), relation_kind=relation_kind,
                    property_key=str(relation.get("property_key", "")),
                    relation_role=str(relation.get("relation_role", "")),
                    related_label=str(relation.get("related_label", "")),
                    raw_source_id=str(relation.get("raw_source_id", "")),
                    scope_kind=str(relation.get("scope_kind", "")),
                    relation_status=str(relation["status"]),
                    activation_state=str(relation.get("activation_state", "")),
                    related_object_id=relation.get("related_object_id"),
                    scope_count=relation.get("scope_count"),
                    body_hidden=relation.get("body_hidden"),
                )
                rows.append(rrow)
                if relation["status"] == "unavailable" or relation.get("incomplete"):
                    metadata_errors.append(
                        f"{object_path}: {relation_kind}: unavailable"
                    )
    current = _blank(identity, "view")
    current.update(view_key="current", view_name="Current")
    current["selector_code"] = encode_selector(
        "view", document_id=identity["document_id"],
        system_key=identity["system_key"], object_path="", native_id="current",
    )
    rows.append(current)
    try:
        manager = graphics.ModelViewManager
        count = int(manager.NumberOfViews)
        # Names are exported by the documented API; numeric XML fields are ignored.
        export_path = identity["view_export_path"]
        manager.ExportModelViews(export_path)
        import xml.etree.ElementTree as ET
        views = [child.attrib.get("Name") for child in ET.parse(export_path).getroot()
                 if child.tag.split("}")[-1] == "ModelView"]
        if len(views) != count or any(name is None for name in views):
            raise ValueError("saved-view export schema/count is invalid")
        for index, name in enumerate(views):
            row = _blank(identity, "view")
            key = f"saved:{index}"
            row.update(view_index=index, view_key=key, view_name=str(name))
            row["selector_code"] = encode_selector(
                "view", document_id=identity["document_id"],
                system_key=identity["system_key"], object_path="", native_id=index,
            )
            rows.append(row)
    except Exception as exc:
        metadata_errors.append(f"saved views: {type(exc).__name__}: {exc}")
        summary["message"] = (
            summary["message"] + "; " if summary["message"] else ""
        ) + f"view metadata unreadable: {type(exc).__name__}: {exc}"
    unique: list[dict[str, Any]] = []
    selectors: set[str] = set()
    for row in rows:
        row.pop("view_export_path", None)
        selector = row["selector_code"]
        if selector and selector in selectors:
            continue
        if selector:
            selectors.add(selector)
        unique.append(row)
    omitted = max(0, len(unique) - 100_000)
    unique = unique[:100_000]
    while len(rows_json(unique).encode("utf-8")) > 64 * 1024 * 1024 and len(unique) > 1:
        unique.pop()
        omitted += 1
    remote_errors = list(getattr(tree, "metadata_errors", ())) if tree is not None else []
    metadata_errors.extend(remote_errors)
    unique[0]["catalogue_complete"] = omitted == 0 and not metadata_errors
    unique[0]["omitted_rows"] = omitted if not metadata_errors else None
    if metadata_errors:
        unique[0]["message"] = "; ".join(metadata_errors[:20])
    return unique


def rows_json(rows: list[dict[str, Any]]) -> str:
    return json.dumps(rows, ensure_ascii=False, allow_nan=False, separators=(",", ":"))


__all__ = ["collect_catalogue_rows", "rows_json"]

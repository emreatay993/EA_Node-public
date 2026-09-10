# Purpose: Project Mechanical selectors from accepted catalogue metadata only.
# Map: subsystems/addons.md
# Tests: tests/mechanical_catalogue/test_property_edit.py, tests/mechanical_catalogue/test_controls.py, tests/mechanical_catalogue/test_search_tree.py, tests/mechanical_catalogue/test_image_export.py, tests/mechanical_catalogue/test_standalone_save.py

from __future__ import annotations

import json
from collections import OrderedDict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from ea_node_editor.addons.mechanical.contracts import MODEL_TYPE_ID, encode_selector
from ea_node_editor.addons.property_edit_adapters import PropertyEditAdapterContext
from ea_node_editor.runtime_contracts import DataTree, RuntimeHandleRef, TableValue

_SELECTOR_KINDS = {
    "system": ("system",),
    "query": ("object", "property"),
    "source": ("object", "property"),
    "table": ("table",),
    "objects": ("object",),
    "views": ("view",),
    "environments": ("object",),
}
_INDEX_CACHE: OrderedDict[tuple[str, int], "_CatalogueIndex"] = OrderedDict()
_CACHE_LIMIT = 16
_INVALID = object()


@dataclass(frozen=True, slots=True)
class _CatalogueIndex:
    rows_by_kind: Mapping[str, tuple[tuple[Any, str], ...]]
    query_by_filter: Mapping[str, tuple[tuple[Any, str], ...]]
    components: tuple[tuple[str, str], ...]
    complete: bool
    omitted_rows: int | None
    table: TableValue
    locator: tuple[Any, ...]


_LOCATOR_FIELDS = (
    "catalogue_id",
    "producer_node_id",
    "producer_port",
    "producer_path",
    "run_id",
    "session_id",
    "model_revision",
    "producer_iteration",
    "document_id",
    "source_key",
    "system_key",
)


def _scalar(value: Any) -> Any:
    item = getattr(value, "item", None)
    return item() if callable(item) else value


def _table_rows(table: TableValue) -> list[dict[str, Any]]:
    from pandas import NA

    columns = [column.to_pandas_array() for column in table.columns]
    return [
        {name: None if value is NA else _scalar(value) for name, value in zip(table.column_names, row)}
        for row in zip(*columns)
    ]


def _catalogue_index(table: TableValue, rows: list[dict[str, Any]]) -> _CatalogueIndex:
    summary = rows[0]
    key = (str(summary["catalogue_id"]), int(summary["model_revision"]))
    cached = _INDEX_CACHE.get(key)
    if cached is not None and cached.table is table:
        _INDEX_CACHE.move_to_end(key)
        return cached
    rows_by_kind: dict[str, list[tuple[Any, str]]] = {}
    for row in rows[1:]:
        code = row.get("selector_code")
        kind = str(row.get("record_kind") or "")
        if not code or kind not in {"system", "object", "property", "table", "view"}:
            continue
        label = (
            row.get("system_label")
            if kind == "system"
            else row.get("view_name")
            if kind == "view"
            else row.get("property_caption")
            if kind == "property"
            else row.get("table_key")
            if kind == "table"
            else row.get("display_name")
        )
        path = str(row.get("object_path") or "")
        visible = str(label or path or code)
        if path and path != visible:
            visible = f"{visible} — {path}"
        rows_by_kind.setdefault(kind, []).append((code, visible))
        if kind == "object" and str(row.get("api_type") or "").endswith(
            ".BoltPretension"
        ):
            table_key = f"{int(row['object_id'])}:bolt_step_states"
            table_code = encode_selector(
                "table",
                document_id=str(row["document_id"]),
                system_key=str(row["system_key"]),
                object_path=path,
                native_id=table_key,
            )
            rows_by_kind.setdefault("table", []).append(
                (table_code, f"Bolt pretension step states — {path}")
            )
    queries: dict[str, list[tuple[Any, str]]] = {}
    for row in rows[1:]:
        kind = str(row.get("record_kind") or "")
        if kind == "object" and row.get("api_type"):
            queries.setdefault("type", []).append((row["api_type"], str(row["api_type"])))
            short_type = str(row["api_type"]).rsplit(".", 1)[-1]
            queries.setdefault("type", []).append((short_type, short_type))
        if kind != "relation" or row.get("relation_status") != "available":
            continue
        relation_kind = str(row.get("relation_kind") or "")
        if relation_kind == "coordinate_system" and row.get("related_label"):
            queries.setdefault("coordinate_system", []).append((row["related_label"], str(row["related_label"])))
        elif relation_kind == "source_model":
            value = row.get("raw_source_id") or row.get("related_label")
            if value:
                queries.setdefault("model", []).append((value, f"Source ID: {value}" if row.get("raw_source_id") else str(value)))
        elif relation_kind == "body_visibility" and row.get("body_hidden") is not None:
            value = "Hidden bodies" if bool(row["body_hidden"]) else "Shown bodies"
            queries.setdefault("graphics", []).append((value, value))
        elif relation_kind == "environment" and row.get("related_label"):
            queries.setdefault("environment", []).append((row["related_label"], str(row["related_label"])))
        elif relation_kind == "scope" and row.get("scope_kind"):
            label = str(row.get("related_label") or str(row["scope_kind"]).replace("_", " ").title())
            queries.setdefault("scoping", []).append((label, label))
            if row.get("object_id") is not None and row.get("object_path"):
                subject = encode_selector(
                    "object", document_id=str(row["document_id"]),
                    system_key=str(row["system_key"]), object_path=str(row["object_path"]),
                    native_id=int(row["object_id"]),
                )
                queries.setdefault("scoping", []).append(
                    (subject, f"{label} — {row['object_path']}")
                )
    queries["state"] = [
        ("Suppressed", "Suppressed"), ("Unsuppressed", "Unsuppressed"),
        ("Not licensed", "Not licensed"), ("Underdefined", "Underdefined"),
    ]
    for filter_code, values in queries.items():
        queries[filter_code] = list(dict.fromkeys(values))
    result = _CatalogueIndex(
        rows_by_kind={kind: tuple(values) for kind, values in rows_by_kind.items()},
        query_by_filter={kind: tuple(values) for kind, values in queries.items()},
        components=tuple(
            dict.fromkeys(
                ("Step state", "Step state")
                if str(row.get("api_type") or "").endswith(".BoltPretension")
                else (str(row.get("property_key") or ""), str(row.get("property_caption") or row.get("property_key") or ""))
                for row in rows[1:]
                if row.get("record_kind") == "property" and row.get("table_key")
                or row.get("record_kind") == "object" and str(row.get("api_type") or "").endswith(".BoltPretension")
            )
        ),
        complete=bool(summary["catalogue_complete"]),
        omitted_rows=None if summary.get("omitted_rows") is None else int(summary["omitted_rows"]),
        table=table,
        locator=tuple(summary.get(field) for field in _LOCATOR_FIELDS),
    )
    _INDEX_CACHE[key] = result
    _INDEX_CACHE.move_to_end(key)
    while len(_INDEX_CACHE) > _CACHE_LIMIT:
        _INDEX_CACHE.popitem(last=False)
    return result


def _model_values(value: Any) -> tuple[RuntimeHandleRef, ...]:
    values = (
        (item for _path, branch in value.branches for item in branch)
        if isinstance(value, DataTree)
        else (value,)
    )
    return tuple(
        item
        for item in values
        if isinstance(item, RuntimeHandleRef) and item.data_type_id == MODEL_TYPE_ID
    )


def _catalogue_for_model(
    model: RuntimeHandleRef,
    provider: Any,
) -> _CatalogueIndex | object | None:
    metadata = model.metadata
    output = provider(metadata["producer_node_id"], metadata["producer_port"])
    if not isinstance(output, DataTree):
        return None
    try:
        branch = output[tuple(metadata["producer_path"])]
    except (KeyError, TypeError):
        return None
    key = (str(metadata["catalogue_id"]), int(metadata["model_revision"]))
    expected_locator = tuple(
        json.dumps(metadata[field], separators=(",", ":"))
        if field == "producer_path"
        else metadata[field]
        for field in _LOCATOR_FIELDS
    )
    matches: list[_CatalogueIndex | tuple[TableValue, list[dict[str, Any]]]] = []
    for candidate in branch:
        if not isinstance(candidate, TableValue) or not candidate.row_count:
            continue
        cached = next(
            (index for index in _INDEX_CACHE.values() if index.table is candidate),
            None,
        )
        if cached is not None:
            if cached.locator == expected_locator:
                matches.append(cached)
            continue
        rows = _table_rows(candidate)
        summary = rows[0]
        try:
            producer_path = tuple(json.loads(str(summary.get("producer_path"))))
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
        if producer_path == tuple(metadata["producer_path"]) and tuple(
            summary.get(field) for field in _LOCATOR_FIELDS
        ) == expected_locator:
            matches.append((candidate, rows))
    if len(matches) != 1:
        return _INVALID if any(isinstance(item, TableValue) for item in branch) else None
    match = matches[0]
    if isinstance(match, _CatalogueIndex):
        _INDEX_CACHE.move_to_end(key)
        return match
    return _catalogue_index(*match)


def _connected_value(context: PropertyEditAdapterContext, port_key: str) -> Any:
    if context.current_output_provider is None:
        return None
    for edge in context.workspace_edges.values() if isinstance(context.workspace_edges, Mapping) else context.workspace_edges or ():
        if (
            edge.target_node_id == context.node.node_id
            and edge.target_port_key == port_key
            and getattr(edge, "enabled", True)
        ):
            return context.current_output_provider(edge.source_node_id, edge.source_port_key)
    return None


def _first_value(value: Any) -> Any:
    if isinstance(value, DataTree):
        return next((item for _path, branch in value.branches for item in branch), None)
    return value


class MechanicalPropertyEditAdapter:
    def rewrite_property_edit(self, context: PropertyEditAdapterContext, *, key: str, value: Any):
        return None

    def build_property_items(
        self,
        context: PropertyEditAdapterContext,
        items: Iterable[Mapping[str, Any]],
    ) -> list[dict[str, Any]]:
        result = [dict(item) for item in items]
        if not str(getattr(context.node, "type_id", "")).startswith("mechanical."):
            return result
        indexes: list[_CatalogueIndex] = []
        invalid = False
        if getattr(context.node, "type_id", "") == "mechanical.open_model":
            own = context.current_output_provider(context.node.node_id, "info") if context.current_output_provider else None
            for _path, branch in own.branches if isinstance(own, DataTree) else ():
                for table in branch:
                    if isinstance(table, TableValue) and table.row_count:
                        rows = _table_rows(table)
                        summary = rows[0]
                        if summary.get("producer_node_id") == context.node.node_id and summary.get("producer_port") == "info":
                            indexes.append(_catalogue_index(table, rows))
        else:
            model_port_key = (
                "source_model"
                if getattr(context.node, "type_id", "")
                in {
                    "mechanical.run_script",
                    "mechanical.apdl_snippet",
                    "mechanical.save_model",
                }
                else "model"
            )
            for model in _model_values(_connected_value(context, model_port_key)):
                index = _catalogue_for_model(model, context.current_output_provider)
                if index is _INVALID:
                    invalid = True
                elif index is not None:
                    indexes.append(index)
        save_node = getattr(context.node, "type_id", "") == "mechanical.save_model"
        save_format = _first_value(_connected_value(context, "format"))
        if save_format is None:
            save_format = (getattr(context.node, "properties", {}) or {}).get(
                "format", "auto"
            )
        save_file = _first_value(_connected_value(context, "file"))
        if save_file is None:
            save_file = (getattr(context.node, "properties", {}) or {}).get("file", "")
        resolved_save_format = (
            str(save_file).rsplit(".", 1)[-1].casefold()
            if str(save_format) == "auto" and "." in str(save_file)
            else str(save_format)
        )
        node_type = str(getattr(context.node, "type_id", ""))
        properties = getattr(context.node, "properties", {}) or {}
        open_file = _first_value(_connected_value(context, "file"))
        if open_file is None:
            open_file = properties.get("file", "")
        family = _first_value(_connected_value(context, "family"))
        if family is None:
            family = properties.get("family", "auto")
        steps = _first_value(_connected_value(context, "steps"))
        if steps is None:
            steps = properties.get("steps", "all")
        for item in result:
            item_key = str(item.get("key") or "")
            if (
                node_type == "mechanical.open_model"
                and item_key == "system"
                and str(open_file).strip().casefold().endswith(
                    (".mechdb", ".mechdat", ".mechpz")
                )
            ):
                reason = (
                    "Workbench projects and archives only; standalone sources do not consume this value."
                )
                item.update(
                    adapter_condition_enabled=False,
                    adapter_condition_reason=reason,
                    condition_enabled=False,
                    editor_enabled=False,
                    editor_disabled_reason=reason,
                )
                continue
            if (
                node_type == "mechanical.fea_table"
                and item_key == "sets"
                and str(family) in {"model_definition", "supported_worksheet"}
            ):
                reason = (
                    "Stored result sets do not apply to model definitions or worksheets."
                )
                item.update(
                    adapter_condition_enabled=False,
                    adapter_condition_reason=reason,
                    condition_enabled=False,
                    editor_enabled=False,
                    editor_disabled_reason=reason,
                )
                continue
            if (
                node_type == "mechanical.apdl_snippet"
                and item_key == "selected_steps"
                and str(steps) != "selected"
            ):
                reason = "Select Selected load steps before editing this list."
                item.update(
                    adapter_condition_enabled=False,
                    adapter_condition_reason=reason,
                    condition_enabled=False,
                    editor_enabled=False,
                    editor_disabled_reason=reason,
                )
                continue
            if save_node and item_key == "format":
                item.update(
                    enum_codes=["auto", "mechdb", "mechdat", "mechpz", "wbpj", "wbpz"],
                    enum_values=["Auto", "Mechanical database", "Mechanical model export", "Mechanical archive", "Workbench project", "Workbench archive"],
                    exact_selectors=True,
                )
                continue
            if save_node and (
                item_key == "include_external_imported_files" and resolved_save_format != "wbpz"
                or item_key in {"include_results", "include_user_files"}
                and resolved_save_format not in {"mechpz", "wbpz"}
            ):
                reason = (
                    "Workbench .wbpz archives only; other formats do not consume this value."
                    if item_key == "include_external_imported_files"
                    else ".mechpz/.wbpz archives only; this value is not consumed."
                )
                item.update(
                    adapter_condition_enabled=False,
                    adapter_condition_reason=reason,
                    condition_enabled=False,
                    editor_enabled=False,
                    editor_disabled_reason=reason,
                )
                continue
            if item_key == "filter":
                codes = ["name", "tag", "type", "state", "coordinate_system", "model", "graphics", "environment", "scoping", "property_name", "property_value"]
                item.update(
                    enum_codes=codes,
                    enum_values=["Name", "Tag", "Type", "State", "Coordinate System", "Model", "Graphics", "Environment", "Scoping", "Property Name", "Property Value"],
                    exact_selectors=True,
                )
                continue
            if item_key == "match":
                item.update(enum_codes=["contains", "exact"], enum_values=["Contains", "Exact"], exact_selectors=True)
                continue
            if item_key == "mode":
                item.update(
                    enum_codes=["background", "interactive"],
                    enum_values=["Background", "Interactive"],
                    exact_selectors=True,
                )
                continue
            if item_key == "version":
                from ea_node_editor.addons.mechanical.catalog import mechanical_release_choices
                releases = mechanical_release_choices()
                item.update(
                    enum_codes=[0, *releases],
                    enum_values=[
                        "Auto · 2026 R1 or newer",
                        *(f"20{code // 10:02d} R{code % 10} ({code})" for code in releases),
                    ],
                    exact_selectors=True,
                )
                continue
            if item_key == "family":
                item.update(
                    enum_codes=["auto", "model_definition", "result_history_summary", "spatial_samples", "supported_worksheet"],
                    enum_values=["Auto", "Model definition", "Result history / summary", "Spatial samples", "Supported worksheet"],
                    exact_selectors=True,
                )
                continue
            if item_key == "units":
                item.update(
                    enum_codes=["source", "si"],
                    enum_values=["Preserve source units", "SI"],
                    exact_selectors=True,
                )
                continue
            if item_key == "include":
                item.update(
                    enum_codes=["saved_and_current", "saved", "current"],
                    enum_values=[
                        "Saved views + current view",
                        "Saved views",
                        "Current view",
                    ],
                    exact_selectors=True,
                )
                continue
            if item_key == "background":
                item.update(
                    enum_codes=["white", "model"],
                    enum_values=["White", "Model background"],
                    exact_selectors=True,
                )
                continue
            if item_key == "scope":
                item.update(
                    enum_codes=["each_environment", "model_once"],
                    enum_values=["Each selected environment", "Model once"],
                    exact_selectors=True,
                )
                continue
            if item_key == "steps":
                item.update(
                    enum_codes=["all", "selected"],
                    enum_values=["All load steps", "Selected load steps"],
                    exact_selectors=True,
                )
                continue
            if item_key == "component":
                components = list(dict.fromkeys(
                    pair for index in indexes for pair in index.components
                ))
                item.update(
                    enum_codes=["all", *(code for code, _label in components)],
                    enum_values=["All", *(label for _code, label in components)],
                    exact_selectors=True,
                    searchable=True,
                    placeholder_text=(
                        "Accepted metadata unavailable" if not indexes else "All or an exact component"
                    ),
                )
                continue
            kinds = _SELECTOR_KINDS.get(item_key)
            if not kinds:
                continue
            options: list[tuple[Any, str]] = []
            connected_filter = _first_value(_connected_value(context, "filter"))
            filter_code = str(
                connected_filter
                if connected_filter is not None
                else (getattr(context.node, "properties", {}) or {}).get("filter", "name")
            )
            for index in indexes:
                if item_key == "query":
                    options.extend(index.query_by_filter.get(filter_code, ()))
                    picker_kinds = ("property",) if filter_code in {"property_name", "property_value"} else ("object",)
                    for kind in picker_kinds:
                        options.extend(index.rows_by_kind.get(kind, ()))
                else:
                    for kind in kinds:
                        options.extend(index.rows_by_kind.get(kind, ()))
            options = list(dict.fromkeys(options))
            contextual = {
                "coordinate_system": "Explicit assignment; missing does not imply Global",
                "model": "Current document or exact opaque Source ID",
                "graphics": "Shown bodies or Hidden bodies from Body.Hidden",
                "environment": "Owning analysis or proved native shared activation",
                "scoping": "Current scope only; Partial/lost scope is unsupported",
                "property_value": "Displayed value, formula, or Tabular data; no table cells",
            }.get(filter_code, "Type or choose a value")
            item.update(
                enum_codes=[code for code, _label in options],
                enum_values=[label for _code, label in options],
                exact_selectors=True,
                searchable=True,
                placeholder_text=(
                    "Accepted metadata unavailable"
                    if not indexes
                    else contextual
                ),
            )
            if item_key == "query":
                item["help_text"] = " ".join(filter(None, (item.get("help_text"), contextual)))
            if item.get("editor_mode") == "chip_list" or item.get("inline_editor") == "list":
                item.update(
                    list_item_enum_codes=list(item["enum_codes"]),
                    list_item_enum_values=list(item["enum_values"]),
                )
            incomplete = [index for index in indexes if not index.complete]
            if incomplete:
                omitted = sum(index.omitted_rows or 0 for index in incomplete)
                notice = (
                    f"Suggestions are incomplete ({omitted} omitted rows)."
                    if omitted
                    else "Suggestions are incomplete."
                )
                item["metadata_notice"] = notice
                item["placeholder_text"] = notice
                item["help_text"] = " ".join(filter(None, (item.get("help_text"), notice)))
            elif invalid:
                item["metadata_notice"] = "Accepted metadata is invalid."
                item["placeholder_text"] = item["metadata_notice"]
        return result


def create_mechanical_property_edit_adapters() -> tuple[MechanicalPropertyEditAdapter, ...]:
    return (MechanicalPropertyEditAdapter(),)


__all__ = ["MechanicalPropertyEditAdapter", "create_mechanical_property_edit_adapters"]

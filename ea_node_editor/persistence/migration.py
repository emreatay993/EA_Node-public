from __future__ import annotations

import copy
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from typing import Any

from ea_node_editor.custom_workflows import normalize_custom_workflow_metadata
from ea_node_editor.nodes.registry import NodeRegistry
from ea_node_editor.passive_style_normalization import (
    RETIRED_PASSIVE_NODE_STYLE_KEYS,
    normalize_passive_style_presets,
)
from ea_node_editor.persistence.artifact_store import normalize_artifact_store_metadata
from ea_node_editor.common.payload_tools import merge_defaults as merge_defaults_dict
from ea_node_editor.settings import (
    DEFAULT_WORKFLOW_SETTINGS,
    SCHEMA_VERSION,
)
from ea_node_editor.workspace.ownership import resolve_workspace_ownership


def _coerce_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "y", "on"}:
            return True
        if normalized in {"0", "false", "no", "n", "off"}:
            return False
    return default


_MAX_SCRIPT_EDITOR_PANEL_WIDTH = 4000.0
_LEGACY_SCHEMA_VERSION = 4
_RETIRED_NODE_TYPE_IDS = frozenset(
    {"core.start", "core.end", "core.branch", "core.on_failure", "hpc.on_status"}
)
_SUBNODE_PIN_TYPE_IDS = frozenset({"core.subnode_input", "core.subnode_output"})
_CONTROL_PIN_KINDS = frozenset({"exec", "completed", "failed"})
_CONTROL_PORT_KEYS = frozenset(
    {
        "exec",
        "exec_in",
        "exec_out",
        "completed",
        "done",
        "failed",
        "failed_in",
        "on_completed",
        "on_failed",
        "on_failure",
        "on_other",
        "true_out",
        "false_out",
    }
)


def _coerce_panel_width(value: Any) -> float:
    try:
        width = float(value)
    except (TypeError, ValueError):
        return 0.0
    # NaN or non-positive widths mean "unset"; the panel falls back to its
    # responsive default. Cap absurd values to keep the panel on screen.
    if width != width or width <= 0.0:
        return 0.0
    return min(width, _MAX_SCRIPT_EDITOR_PANEL_WIDTH)


def _as_dict(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, Mapping):
        return {str(key): item for key, item in value.items()}
    raise ValueError("Expected a JSON object.")


def _merge_defaults(values: Any, defaults: dict[str, Any]) -> dict[str, Any]:
    if values is None:
        return merge_defaults_dict({}, defaults)
    if not isinstance(values, Mapping):
        raise ValueError("Expected a JSON object.")
    return merge_defaults_dict({str(key): value for key, value in values.items()}, defaults)


def _copy_mapping_excluding(payload: Mapping[str, Any], *excluded_keys: str) -> dict[str, Any]:
    excluded = set(excluded_keys)
    return {
        str(key): copy.deepcopy(value)
        for key, value in payload.items()
        if str(key) not in excluded
    }


@dataclass(frozen=True, slots=True)
class ScriptEditorSessionState:
    visible: bool = False
    floating: bool = False
    width: float = 0.0

    @classmethod
    def from_mapping(cls, payload: Any) -> "ScriptEditorSessionState":
        state = _as_dict(payload)
        return cls(
            visible=_coerce_bool(state.get("visible"), False),
            floating=_coerce_bool(state.get("floating"), False),
            width=_coerce_panel_width(state.get("width")),
        )

    def to_mapping(self) -> dict[str, Any]:
        return {
            "visible": self.visible,
            "floating": self.floating,
            "width": self.width,
        }


@dataclass(frozen=True, slots=True)
class ProjectUiSessionMetadata:
    script_editor: ScriptEditorSessionState = field(default_factory=ScriptEditorSessionState)
    passive_style_presets: dict[str, Any] = field(default_factory=lambda: normalize_passive_style_presets(None))
    extra: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, payload: Any) -> "ProjectUiSessionMetadata":
        ui_metadata = _as_dict(payload)
        return cls(
            script_editor=ScriptEditorSessionState.from_mapping(ui_metadata.get("script_editor")),
            passive_style_presets=normalize_passive_style_presets(ui_metadata.get("passive_style_presets")),
            extra=_copy_mapping_excluding(ui_metadata, "script_editor", "passive_style_presets"),
        )

    def to_mapping(self) -> dict[str, Any]:
        payload = copy.deepcopy(self.extra)
        payload["script_editor"] = self.script_editor.to_mapping()
        payload["passive_style_presets"] = copy.deepcopy(self.passive_style_presets)
        return payload

    def with_script_editor_state(
        self, *, visible: bool, floating: bool, width: float = 0.0
    ) -> "ProjectUiSessionMetadata":
        return replace(
            self,
            script_editor=ScriptEditorSessionState(
                visible=bool(visible),
                floating=bool(floating),
                width=_coerce_panel_width(width),
            ),
        )


@dataclass(frozen=True, slots=True)
class ProjectSessionMetadata:
    ui: ProjectUiSessionMetadata = field(default_factory=ProjectUiSessionMetadata)
    workflow_settings: dict[str, Any] = field(default_factory=lambda: _merge_defaults({}, DEFAULT_WORKFLOW_SETTINGS))
    extra: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, payload: Any) -> "ProjectSessionMetadata":
        metadata = _as_dict(payload)
        return cls(
            ui=ProjectUiSessionMetadata.from_mapping(metadata.get("ui")),
            workflow_settings=_merge_defaults(metadata.get("workflow_settings"), DEFAULT_WORKFLOW_SETTINGS),
            extra=_copy_mapping_excluding(metadata, "ui", "workflow_settings"),
        )

    def to_mapping(self) -> dict[str, Any]:
        payload = copy.deepcopy(self.extra)
        payload["ui"] = self.ui.to_mapping()
        payload["workflow_settings"] = copy.deepcopy(self.workflow_settings)
        return payload

    def with_script_editor_state(
        self, *, visible: bool, floating: bool, width: float = 0.0
    ) -> "ProjectSessionMetadata":
        return replace(
            self,
            ui=self.ui.with_script_editor_state(visible=visible, floating=floating, width=width),
        )

    def with_workflow_settings(self, workflow_settings: Any) -> "ProjectSessionMetadata":
        return replace(
            self,
            workflow_settings=_merge_defaults(workflow_settings, DEFAULT_WORKFLOW_SETTINGS),
        )


class JsonProjectMigration:
    def __init__(self, registry: NodeRegistry) -> None:
        self._registry = registry
        self.last_report: tuple[str, ...] = ()
        self.source_schema_version: int | None = None

    def migrate(self, raw_doc: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(raw_doc, Mapping):
            raise ValueError("Project document must be a JSON object.")
        version = self._coerce_int(raw_doc.get("schema_version", 0), default=0)
        self.last_report = ()
        self.source_schema_version = None
        doc = copy.deepcopy(dict(raw_doc))
        if version > SCHEMA_VERSION:
            raise ValueError(f"Unsupported schema version: {version}")
        if version not in {_LEGACY_SCHEMA_VERSION, SCHEMA_VERSION}:
            raise ValueError(
                "Unsupported schema version: "
                f"{version}. Only schema versions {_LEGACY_SCHEMA_VERSION} and {SCHEMA_VERSION} are supported."
            )
        if version == _LEGACY_SCHEMA_VERSION:
            self._reject_unresolved_legacy_nodes(doc)
            report: list[str] = [
                f"Migrated project schema {_LEGACY_SCHEMA_VERSION} to {SCHEMA_VERSION}."
            ]
            doc = self._migrate_v4_document(doc, report=report)
            self.last_report = tuple(sorted(set(report)))
            self.source_schema_version = version
        doc["schema_version"] = SCHEMA_VERSION
        return self._normalize_document(doc)

    def _reject_unresolved_legacy_nodes(self, doc: Mapping[str, Any]) -> None:
        unresolved = sorted(
            {
                type_id
                for node_doc in self._iter_legacy_node_docs(doc)
                if (type_id := self._coerce_str(node_doc.get("type_id")))
                and type_id not in _RETIRED_NODE_TYPE_IDS
                and self._registry.spec_or_none(type_id) is None
            }
        )
        if unresolved:
            raise ValueError(
                "Legacy project contains unresolved add-ons: " + ", ".join(unresolved)
            )

    def _iter_legacy_node_docs(self, doc: Mapping[str, Any]):
        for workspace_doc in self.as_list(doc.get("workspaces", [])):
            if not isinstance(workspace_doc, Mapping):
                continue
            for node_doc in self.as_list(workspace_doc.get("nodes", [])):
                if isinstance(node_doc, Mapping):
                    yield node_doc
        metadata = doc.get("metadata")
        if not isinstance(metadata, Mapping):
            return
        for workflow in self.as_list(metadata.get("custom_workflows", [])):
            if not isinstance(workflow, Mapping):
                continue
            fragment = workflow.get("fragment")
            if not isinstance(fragment, Mapping):
                continue
            for node_doc in self.as_list(fragment.get("nodes", [])):
                if isinstance(node_doc, Mapping):
                    yield node_doc

    def _migrate_v4_document(
        self,
        doc: dict[str, Any],
        *,
        report: list[str],
    ) -> dict[str, Any]:
        migrated_workspaces: list[Any] = []
        for workspace_doc in self.as_list(doc.get("workspaces", [])):
            if not isinstance(workspace_doc, Mapping):
                continue
            workspace = copy.deepcopy(dict(workspace_doc))
            self._migrate_v4_graph_container(
                workspace,
                node_id_key="node_id",
                source_node_id_key="source_node_id",
                target_node_id_key="target_node_id",
                report=report,
            )
            workspace["dirty"] = True
            migrated_workspaces.append(workspace)
        doc["workspaces"] = migrated_workspaces

        metadata = self.as_dict(doc.get("metadata"))
        raw_workflows = self.as_list(metadata.get("custom_workflows", []))
        for workflow in raw_workflows:
            if isinstance(workflow, Mapping):
                self._report_legacy_custom_workflow_cutover(workflow, report=report)
        normalized_workflows = normalize_custom_workflow_metadata(raw_workflows)
        retained_ids = {str(item.get("workflow_id", "")).strip() for item in normalized_workflows}
        for workflow in raw_workflows:
            if not isinstance(workflow, Mapping):
                continue
            workflow_id = self._coerce_str(workflow.get("workflow_id"))
            if workflow_id and workflow_id not in retained_ids:
                report.append(f"Removed empty custom workflow {workflow_id}.")
        metadata["custom_workflows"] = normalized_workflows
        doc["metadata"] = metadata
        return doc

    def _report_legacy_custom_workflow_cutover(
        self,
        workflow: Mapping[str, Any],
        *,
        report: list[str],
    ) -> None:
        workflow_id = self._coerce_str(workflow.get("workflow_id"), "unnamed")
        fragment = workflow.get("fragment")
        if not isinstance(fragment, Mapping):
            return
        removed_ref_ids: set[str] = set()
        for raw_node in self.as_list(fragment.get("nodes", [])):
            if not isinstance(raw_node, Mapping):
                continue
            ref_id = self._coerce_str(raw_node.get("ref_id"))
            type_id = self._coerce_str(raw_node.get("type_id"))
            properties = raw_node.get("properties")
            pin_kind = (
                self._coerce_str(properties.get("kind")).lower()
                if isinstance(properties, Mapping)
                else ""
            )
            if type_id not in _RETIRED_NODE_TYPE_IDS and not (
                type_id in _SUBNODE_PIN_TYPE_IDS and pin_kind in _CONTROL_PIN_KINDS
            ):
                continue
            if ref_id:
                removed_ref_ids.add(ref_id)
            report.append(
                f"Removed retired node {ref_id or type_id} ({type_id}) "
                f"from custom workflow {workflow_id}."
            )
        for raw_edge in self.as_list(fragment.get("edges", [])):
            if not isinstance(raw_edge, Mapping):
                continue
            source_ref_id = self._coerce_str(raw_edge.get("source_ref_id"))
            target_ref_id = self._coerce_str(raw_edge.get("target_ref_id"))
            source_port_key = self._coerce_str(raw_edge.get("source_port_key"))
            target_port_key = self._coerce_str(raw_edge.get("target_port_key"))
            if (
                source_ref_id not in removed_ref_ids
                and target_ref_id not in removed_ref_ids
                and source_port_key not in _CONTROL_PORT_KEYS
                and target_port_key not in _CONTROL_PORT_KEYS
            ):
                continue
            report.append(
                "Removed control wire "
                f"{source_ref_id}.{source_port_key}->{target_ref_id}.{target_port_key} "
                f"from custom workflow {workflow_id}."
            )

    def _migrate_v4_graph_container(
        self,
        container: dict[str, Any],
        *,
        node_id_key: str,
        source_node_id_key: str,
        target_node_id_key: str,
        report: list[str],
    ) -> None:
        removed_node_ids: set[str] = set()
        migrated_nodes: list[dict[str, Any]] = []
        for raw_node in self.as_list(container.get("nodes", [])):
            if not isinstance(raw_node, Mapping):
                continue
            node = copy.deepcopy(dict(raw_node))
            node_id = self._coerce_str(node.get(node_id_key))
            type_id = self._coerce_str(node.get("type_id"))
            properties = node.get("properties")
            pin_kind = (
                self._coerce_str(properties.get("kind")).lower()
                if isinstance(properties, Mapping)
                else ""
            )
            if type_id in _RETIRED_NODE_TYPE_IDS or (
                type_id in _SUBNODE_PIN_TYPE_IDS and pin_kind in _CONTROL_PIN_KINDS
            ):
                if node_id:
                    removed_node_ids.add(node_id)
                report.append(f"Removed retired node {node_id or type_id} ({type_id}).")
                continue
            node.pop("settings_section_expanded", None)
            node.pop("advanced_section_expanded", None)
            node["port_modifiers"] = {}
            node["principal_input_port_id"] = None
            if type_id in _SUBNODE_PIN_TYPE_IDS and isinstance(properties, Mapping):
                node["properties"] = {**dict(properties), "data_access": "item"}
            migrated_nodes.append(node)

        for node in migrated_nodes:
            node.pop("locked_ports", None)
            for metadata_key in ("exposed_ports", "port_labels"):
                metadata = node.get(metadata_key)
                if not isinstance(metadata, Mapping):
                    continue
                node[metadata_key] = {
                    str(key): copy.deepcopy(value)
                    for key, value in metadata.items()
                    if str(key) not in _CONTROL_PORT_KEYS and str(key) not in removed_node_ids
                }

        migrated_edges: list[dict[str, Any]] = []
        next_input_order: dict[tuple[str, str], int] = {}
        for raw_edge in self.as_list(container.get("edges", [])):
            if not isinstance(raw_edge, Mapping):
                continue
            edge = copy.deepcopy(dict(raw_edge))
            source_node_id = self._coerce_str(edge.get(source_node_id_key))
            target_node_id = self._coerce_str(edge.get(target_node_id_key))
            source_port_key = self._coerce_str(edge.get("source_port_key"))
            target_port_key = self._coerce_str(edge.get("target_port_key"))
            if (
                source_node_id in removed_node_ids
                or target_node_id in removed_node_ids
                or source_port_key in _CONTROL_PORT_KEYS
                or target_port_key in _CONTROL_PORT_KEYS
            ):
                edge_id = self._coerce_str(edge.get("edge_id"), "wire")
                report.append(f"Removed control wire {edge_id}.")
                continue
            input_key = (target_node_id, target_port_key)
            edge["enabled"] = True
            edge["input_order"] = next_input_order.get(input_key, 0)
            next_input_order[input_key] = edge["input_order"] + 1
            migrated_edges.append(edge)

        container["nodes"] = migrated_nodes
        container["edges"] = migrated_edges

    @staticmethod
    def _coerce_str(value: Any, default: str = "") -> str:
        if isinstance(value, str):
            stripped = value.strip()
            return stripped if stripped else default
        if value is None:
            return default
        text = str(value).strip()
        return text if text else default

    @staticmethod
    def _coerce_int(value: Any, default: int = 0) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _coerce_float(value: Any, default: float = 0.0) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _coerce_bool(value: Any, default: bool = False) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"1", "true", "yes", "y", "on"}:
                return True
            if normalized in {"0", "false", "no", "n", "off"}:
                return False
        return default

    @staticmethod
    def as_dict(value: Any) -> dict[str, Any]:
        return _as_dict(value)

    @staticmethod
    def merge_defaults(values: Any, defaults: dict[str, Any]) -> dict[str, Any]:
        return _merge_defaults(values, defaults)

    @staticmethod
    def as_list(value: Any) -> list[Any]:
        if value is None:
            return []
        if isinstance(value, list):
            return list(value)
        raise ValueError("Expected a JSON array.")

    @staticmethod
    def _copy_mapping(value: Mapping[str, Any]) -> dict[str, Any]:
        return copy.deepcopy(dict(value))

    @staticmethod
    def normalize_metadata(source: Any, workspace_order: list[str]) -> dict[str, Any]:
        metadata = ProjectSessionMetadata.from_mapping(source).to_mapping()
        metadata["workspace_order"] = list(workspace_order)
        metadata["custom_workflows"] = normalize_custom_workflow_metadata(metadata.get("custom_workflows"))
        metadata["artifact_store"] = normalize_artifact_store_metadata(metadata.get("artifact_store"))
        return metadata

    def _normalize_document(self, doc: dict[str, Any]) -> dict[str, Any]:
        normalized_workspaces: dict[str, dict[str, Any]] = {}
        for workspace_doc in self.as_list(doc.get("workspaces", [])):
            if not isinstance(workspace_doc, Mapping):
                continue
            workspace_id = self._coerce_str(workspace_doc.get("workspace_id"))
            if not workspace_id or workspace_id in normalized_workspaces:
                continue
            normalized_workspaces[workspace_id] = self._normalize_workspace_doc(workspace_doc, workspace_id)

        ownership = resolve_workspace_ownership(
            normalized_workspaces,
            order_sources=(
                doc.get("workspace_order"),
                self.as_dict(doc.get("metadata")).get("workspace_order"),
            ),
            active_workspace_id=doc.get("active_workspace_id"),
        )

        metadata = self.normalize_metadata(doc.get("metadata"), ownership.workspace_order)

        return {
            "schema_version": SCHEMA_VERSION,
            "project_id": self._coerce_str(doc.get("project_id"), "proj_unknown"),
            "name": self._coerce_str(doc.get("name"), "untitled"),
            "active_workspace_id": ownership.active_workspace_id,
            "workspace_order": ownership.workspace_order,
            "workspaces": [normalized_workspaces[workspace_id] for workspace_id in ownership.workspace_order],
            "metadata": metadata,
        }

    def _normalize_workspace_doc(self, workspace_doc: Mapping[str, Any], workspace_id: str) -> dict[str, Any]:
        views_by_id: dict[str, dict[str, Any]] = {}
        for index, view_doc in enumerate(self.as_list(workspace_doc.get("views", [])), start=1):
            if not isinstance(view_doc, Mapping):
                continue
            view_id = self._coerce_str(view_doc.get("view_id"))
            if not view_id or view_id in views_by_id:
                continue
            views_by_id[view_id] = {
                "view_id": view_id,
                "name": self._coerce_str(view_doc.get("name"), f"V{index}"),
                "zoom": self._coerce_float(view_doc.get("zoom"), 1.0),
                "pan_x": self._coerce_float(view_doc.get("pan_x"), 0.0),
                "pan_y": self._coerce_float(view_doc.get("pan_y"), 0.0),
                "scope_path": [
                    self._coerce_str(item)
                    for item in self.as_list(view_doc.get("scope_path"))
                    if self._coerce_str(item)
                ],
                "hide_optional_ports": _coerce_bool(
                    view_doc.get("hide_optional_ports"),
                    False,
                ),
            }

        if not views_by_id:
            raise ValueError("Current schema workspace must include at least one view.")

        active_view_id = self._coerce_str(workspace_doc.get("active_view_id"))
        if active_view_id not in views_by_id:
            active_view_id = next(iter(views_by_id))

        nodes_by_id: dict[str, dict[str, Any]] = {}
        for node_doc in self.as_list(workspace_doc.get("nodes", [])):
            if not isinstance(node_doc, Mapping):
                continue
            normalized_node = self._normalize_node_doc(node_doc)
            if normalized_node is None:
                continue
            node_id = normalized_node["node_id"]
            if node_id in nodes_by_id:
                continue
            nodes_by_id[node_id] = normalized_node

        edges_by_id: dict[str, dict[str, Any]] = {}
        for edge_doc in self.as_list(workspace_doc.get("edges", [])):
            if not isinstance(edge_doc, Mapping):
                continue
            normalized_edge = self._normalize_edge_doc(
                edge_doc,
                valid_node_ids=set(nodes_by_id),
            )
            if normalized_edge is None:
                continue
            edge_id = normalized_edge["edge_id"]
            if edge_id in edges_by_id:
                continue
            edges_by_id[edge_id] = normalized_edge

        return {
            "workspace_id": workspace_id,
            "name": self._coerce_str(workspace_doc.get("name"), "Workspace"),
            "dirty": self._coerce_bool(workspace_doc.get("dirty"), False),
            "active_view_id": active_view_id,
            "views": list(views_by_id.values()),
            "nodes": list(nodes_by_id.values()),
            "edges": list(edges_by_id.values()),
        }

    def _normalize_node_doc(self, node_doc: Mapping[str, Any]) -> dict[str, Any] | None:
        node_id = self._coerce_str(node_doc.get("node_id"))
        type_id = self._coerce_str(node_doc.get("type_id"))
        if not node_id or not type_id:
            return None
        properties = node_doc.get("properties")
        pin_kind = (
            self._coerce_str(properties.get("kind")).lower()
            if isinstance(properties, Mapping)
            else ""
        )
        if type_id in _RETIRED_NODE_TYPE_IDS or (
            type_id in _SUBNODE_PIN_TYPE_IDS and pin_kind in _CONTROL_PIN_KINDS
        ):
            raise ValueError(f"Current project schema contains retired control node: {type_id}")
        legacy_engineering_viewer = type_id == "engineering.viewer"
        if legacy_engineering_viewer:
            type_id = "model.viewer"
        title_default = type_id
        spec = self._registry.spec_or_none(type_id)
        if spec is not None:
            title_default = spec.display_name
        normalized = self._copy_mapping(node_doc)
        normalized["node_id"] = node_id
        normalized["type_id"] = type_id
        title = self._coerce_str(node_doc.get("title"), title_default)
        if legacy_engineering_viewer and title == "Engineering Viewer":
            title = "Model Viewer"
        normalized["title"] = title
        normalized["x"] = self._coerce_float(node_doc.get("x"), 0.0)
        normalized["y"] = self._coerce_float(node_doc.get("y"), 0.0)
        normalized["collapsed"] = self._coerce_bool(node_doc.get("collapsed"), False)
        normalized.pop("settings_section_expanded", None)
        normalized.pop("advanced_section_expanded", None)
        normalized["properties"] = self.as_dict(node_doc.get("properties"))
        normalized["exposed_ports"] = {
            key: self._coerce_bool(value)
            for key, value in self.as_dict(node_doc.get("exposed_ports")).items()
            if key
        }
        port_labels = {
            key: self._coerce_str(value)
            for key, value in self.as_dict(node_doc.get("port_labels")).items()
            if key and self._coerce_str(value)
        }
        if "port_labels" in node_doc or port_labels:
            normalized["port_labels"] = port_labels
        port_modifiers = {
            key: [
                modifier
                for modifier in ("graft", "flatten", "simplify", "reverse", "clean")
                if modifier in {str(item).strip().lower() for item in value}
            ]
            for key, value in self.as_dict(node_doc.get("port_modifiers")).items()
            if key and isinstance(value, list | tuple)
        }
        normalized["port_modifiers"] = {
            key: value for key, value in port_modifiers.items() if value
        }
        normalized["principal_input_port_id"] = (
            self._coerce_str(node_doc.get("principal_input_port_id")) or None
        )
        if spec is None:
            visual_style = self.as_dict(node_doc.get("visual_style"))
            if "visual_style" in node_doc or visual_style:
                normalized["visual_style"] = visual_style
        elif str(spec.runtime_behavior or "").strip().lower() == "passive":
            visual_style = _copy_mapping_excluding(
                self.as_dict(node_doc.get("visual_style")),
                *RETIRED_PASSIVE_NODE_STYLE_KEYS,
            )
            if "visual_style" in node_doc or visual_style:
                normalized["visual_style"] = visual_style
        else:
            normalized.pop("visual_style", None)
        normalized["parent_node_id"] = self._coerce_str(node_doc.get("parent_node_id")) or None
        if "custom_width" in node_doc:
            normalized["custom_width"] = (
                self._coerce_float(node_doc["custom_width"])
                if node_doc.get("custom_width") is not None
                else None
            )
        if "custom_height" in node_doc:
            normalized["custom_height"] = (
                self._coerce_float(node_doc["custom_height"])
                if node_doc.get("custom_height") is not None
                else None
            )
        return normalized

    def _normalize_edge_doc(
        self,
        edge_doc: Mapping[str, Any],
        *,
        valid_node_ids: set[str],
    ) -> dict[str, Any] | None:
        edge_id = self._coerce_str(edge_doc.get("edge_id"))
        source_node_id = self._coerce_str(edge_doc.get("source_node_id"))
        source_port_key = self._coerce_str(edge_doc.get("source_port_key"))
        target_node_id = self._coerce_str(edge_doc.get("target_node_id"))
        target_port_key = self._coerce_str(edge_doc.get("target_port_key"))
        if (
            not edge_id
            or not source_node_id
            or not source_port_key
            or not target_node_id
            or not target_port_key
        ):
            return None
        if source_node_id not in valid_node_ids or target_node_id not in valid_node_ids:
            return None
        if source_port_key in _CONTROL_PORT_KEYS or target_port_key in _CONTROL_PORT_KEYS:
            raise ValueError("Current project schema contains a retired control wire.")
        normalized = self._copy_mapping(edge_doc)
        normalized["edge_id"] = edge_id
        normalized["source_node_id"] = source_node_id
        normalized["source_port_key"] = source_port_key
        normalized["target_node_id"] = target_node_id
        normalized["target_port_key"] = target_port_key
        normalized["enabled"] = self._coerce_bool(edge_doc.get("enabled"), True)
        normalized["input_order"] = max(
            0,
            self._coerce_int(edge_doc.get("input_order"), 0),
        )
        label = self._coerce_str(edge_doc.get("label"))
        if "label" in edge_doc or label:
            normalized["label"] = label
        visual_style = self.as_dict(edge_doc.get("visual_style"))
        if "visual_style" in edge_doc or visual_style:
            normalized["visual_style"] = visual_style
        return normalized

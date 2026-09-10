from __future__ import annotations

import copy
from collections.abc import Mapping
from typing import Any

from PyQt6.QtCore import QObject, QTimer
from PyQt6.QtGui import QGuiApplication

from ea_node_editor.graph.boundary_adapters import build_graph_boundary_adapters
from ea_node_editor.graph.registry_normalization import normalize_project_for_registry
from ea_node_editor.nodes.registry import NodeRegistry
from ea_node_editor.addons.property_edit_adapters import (
    create_property_edit_adapters,
    selector_metadata_signature,
)
from ea_node_editor.ui.support.node_presentation import has_focused_selector
from ea_node_editor.ui_qml.edge_routing import node_size
from ea_node_editor.ui_qml.graph_scene import (
    GraphSceneBridgeBase,
    GraphSceneCommandBridge,
    GraphScenePolicyBridge,
    GraphSceneReadBridge,
    _GraphScenePayloadCache,
    _GraphScenePendingSurfaceAction,
)
from ea_node_editor.ui_qml.graph_scene.context import _GraphSceneContext
from ea_node_editor.ui_qml.graph_scene_mutation_history import (
    GraphSceneMutationHistory,
    GraphSceneMutationPolicy,
)
from ea_node_editor.ui_qml.graph_scene_payload import GraphScenePayloadBuilder
from ea_node_editor.ui_qml.graph_scene_scope_selection import GraphSceneScopeSelection


class GraphSceneBridge(GraphSceneBridgeBase):
    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._boundary_adapters = build_graph_boundary_adapters(
            node_size_resolver=node_size,
        )
        self._model = None
        self._registry = None
        self._history = None
        self._current_output_provider = None
        self._selector_metadata_signatures = {}
        self._runtime_schema_pending = False
        app = QGuiApplication.instance()
        if isinstance(app, QGuiApplication):
            app.focusObjectChanged.connect(self._on_editor_focus_changed)
        self._payload_builder = GraphScenePayloadBuilder(
            boundary_adapters=self._boundary_adapters,
            current_input_provider=self._current_output_value,
            property_edit_adapters=create_property_edit_adapters(),
            keep_expanded_node_width_provider=lambda: self.graphics_keep_expanded_node_width,
        )
        self._scene_context = _GraphSceneContext(self, payload_builder=self._payload_builder)
        self._scope_selection = GraphSceneScopeSelection(self._scene_context)
        self._authoring_boundary = GraphSceneMutationHistory(
            self._scene_context,
            self._scope_selection,
            boundary_adapters=self._boundary_adapters,
        )
        self._policy_boundary = GraphSceneMutationPolicy(self._scene_context)
        self._workspace_id = ""
        self._scope_path = ()
        self._selected_node_ids = []
        self._selected_node_lookup = {}
        self._payload_cache = _GraphScenePayloadCache()
        self._graph_theme_bridge = None
        self._pending_surface_action = _GraphScenePendingSurfaceAction()
        self._state_bridge = GraphSceneReadBridge(self)
        self._command_bridge = GraphSceneCommandBridge(
            self,
            scope_selection=self._scope_selection,
            authoring_boundary=self._authoring_boundary,
            pending_surface_action=self._pending_surface_action,
        )
        self._policy_bridge = GraphScenePolicyBridge(self, self._policy_boundary)

    def set_current_output_provider(self, provider: Any) -> None:
        self._current_output_provider = provider

    def _current_output_value(self, node_id: str, port_key: str) -> Any:
        if self._model is None or self._current_output_provider is None:
            return None
        return self._current_output_provider(self._workspace_id, node_id, port_key)

    def refresh_current_output_properties(self) -> None:
        if self._model is None:
            return
        if has_focused_selector("graphInlinePropertiesLayer", "graphSelectorOptions"):
            self._runtime_schema_pending = True
            return
        self._runtime_schema_pending = False
        workspace = self._model.project.workspaces.get(self._workspace_id)
        for node in workspace.nodes.values() if workspace else ():
            spec = self._registry.resolve_spec(node.type_id, node.properties) if self._registry and self._registry.spec_or_none(node.type_id) else None
            if spec is None:
                continue
            items = self._payload_builder.build_inline_properties_payload(
                node=node,
                spec=spec,
                workspace=workspace,
                workspace_nodes=workspace.nodes,
                enabled_input_port_keys={port.key for port in spec.ports if port.direction == "in"},
                port_connection_counts={},
            )
            signature = selector_metadata_signature(items)
            key = (self._workspace_id, node.node_id)
            if signature and self._selector_metadata_signatures.get(key) != signature:
                self._selector_metadata_signatures[key] = signature
                self._scene_context.publish_node_payload_update(node.node_id, publication_path="current_output_schema")

    def _on_editor_focus_changed(self, _focused: QObject | None) -> None:
        if self._runtime_schema_pending:
            QTimer.singleShot(0, self.refresh_current_output_properties)

    def rebuild_registry(self, registry: NodeRegistry) -> None:
        previous_registry = self._registry
        workspace_snapshots = (
            {}
            if self._model is None
            else {
                workspace_id: (
                    workspace.capture_snapshot(),
                    workspace.mutation_revision,
                )
                for workspace_id, workspace in self._model.project.workspaces.items()
            }
        )
        previous_payload_cache = copy.deepcopy(self._payload_cache)
        previous_node_delta_payload = copy.deepcopy(
            self._state_bridge.node_delta_payload
        )
        self._registry = registry
        try:
            if self._model is None or self._registry is None:
                return
            normalize_project_for_registry(self._model.project, self._registry)
            self._scene_context.rebuild_models()
        except Exception:
            self._registry = previous_registry
            if self._model is not None:
                for workspace_id, (
                    snapshot,
                    mutation_revision,
                ) in workspace_snapshots.items():
                    workspace = self._model.project.workspaces[workspace_id]
                    workspace.restore_snapshot(snapshot)
                    workspace.mutation_revision = mutation_revision
            self._payload_cache = previous_payload_cache
            self._state_bridge.node_delta_payload = previous_node_delta_payload
            self.nodes_changed.emit()
            self.edges_changed.emit()
            raise

    def replace_registry(self, registry: NodeRegistry) -> None:
        """Replace the presentation registry without normalizing graph data."""

        if not isinstance(registry, NodeRegistry):
            raise TypeError("registry must be a NodeRegistry")
        previous_registry = self._registry
        previous_payload_cache = copy.deepcopy(self._payload_cache)
        previous_node_delta_payload = copy.deepcopy(
            self._state_bridge.node_delta_payload
        )
        self._registry = registry
        try:
            if self._model is not None:
                self._scene_context.rebuild_models()
        except Exception:
            self._registry = previous_registry
            self._payload_cache = previous_payload_cache
            self._state_bridge.node_delta_payload = previous_node_delta_payload
            self.nodes_changed.emit()
            self.edges_changed.emit()
            raise

    def resync_scene_payloads(self) -> None:
        """Defensive full resync: rebuild scene payload models from the graph
        model. Used by view-layer consumers (e.g. the visible-model duplicate
        guard) when they detect payloads that can only come from a corrupted
        cache; the graph model is the ground truth that restores consistency."""
        if self._model is None:
            return
        self._scene_context.rebuild_models()

    def library_drop_preview_payload(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        return self._payload_builder.build_library_preview_node_payload(
            model=self._model,
            registry=self._registry,
            workspace_id=self._workspace_id,
            library_payload=payload,
            graph_theme_bridge=self._graph_theme_bridge,
            show_port_labels=self.graphics_show_port_labels,
            graph_label_pixel_size=self.graphics_graph_label_pixel_size,
            graph_node_icon_pixel_size=self.graphics_node_title_icon_pixel_size,
            lightweight_canvas=self.graphics_lightweight_canvas,
        )


__all__ = [
    "GraphSceneBridge",
    "GraphSceneCommandBridge",
    "GraphScenePolicyBridge",
    "GraphSceneReadBridge",
]

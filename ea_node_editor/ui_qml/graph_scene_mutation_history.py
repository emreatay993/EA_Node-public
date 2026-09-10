from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any, Callable

from PyQt6.QtCore import QCoreApplication, QRectF

import ea_node_editor.ui_qml.graph_scene_mutation.alignment_and_distribution_ops as _alignment_ops
import ea_node_editor.ui_qml.graph_scene_mutation.clipboard_and_fragment_ops as _clipboard_ops
import ea_node_editor.ui_qml.graph_scene_mutation.collision_avoidance_ops as _collision_ops
import ea_node_editor.ui_qml.graph_scene_mutation.group_backdrop_ops as _group_backdrop_ops
import ea_node_editor.ui_qml.graph_scene_mutation.grouping_and_subnode_ops as _grouping_ops
import ea_node_editor.ui_qml.graph_scene_mutation.policy as _policy
import ea_node_editor.ui_qml.graph_scene_mutation.selection_and_scope_ops as _selection_ops
from ea_node_editor.ui_qml.graph_scene_mutation.node_creation_batch import create_nodes_batch
from ea_node_editor.graph.boundary_adapters import GraphBoundaryAdapters
from ea_node_editor.graph.fragment_payloads import (
    fragment_node_from_payload,
    graph_fragment_payload_is_valid,
)
from ea_node_editor.graph.hierarchy import root_node_ids_for_fragment, subtree_node_ids
from ea_node_editor.graph.node_links import node_link_targets_node
from ea_node_editor.graph.record_mutation_ops import GraphRecordMutation
from ea_node_editor.graph.workspace_state import WorkspaceData
from ea_node_editor.graph.records import NodeInstance
from ea_node_editor.graph.transform_fragment_ops import insert_graph_fragment
from ea_node_editor.graph.transforms import (
    LayoutNodeBounds,
    build_subtree_fragment_payload_data,
    collect_layout_node_bounds,
    expand_group_backdrop_fragment_node_ids,
    graph_fragment_bounds,
    normalize_layout_position_updates,
    snap_coordinate,
)
from ea_node_editor.graph.validated_mutation import ValidatedGraphMutation
from ea_node_editor.persistence.artifact_store import ProjectArtifactStore
from ea_node_editor.settings import PROJECT_ARTIFACT_STORE_METADATA_KEY
from ea_node_editor.ui.shell.runtime_clipboard import build_graph_fragment_payload
from ea_node_editor.ui.shell.runtime_history import (
    ACTION_DELETE_SELECTED,
    ACTION_MOVE_NODE,
)
from ea_node_editor.ui_qml.graph_surface_metrics import (
    node_surface_metrics,
    resolved_node_surface_size,
)

if TYPE_CHECKING:
    from ea_node_editor.nodes.node_specs import NodeTypeSpec
    from ea_node_editor.ui.shell.runtime_history import WorkspaceSnapshot
    from ea_node_editor.ui_qml.graph_scene.context import _GraphSceneContext
    from ea_node_editor.ui_qml.graph_scene_scope_selection import (
        GraphSceneScopeSelection,
    )

_ARTIFACT_RENAME_RETRY_COUNT = 20
_ARTIFACT_RENAME_RETRY_DELAY_SECONDS = 0.05
_COMPACT_PILL_VARIANTS = frozenset(
    {"boolean_toggle", "number_slider", "select", "trigger"}
)


class _TimedGraphMutationBoundary:
    def __init__(self, boundary: Any, scene_context: _GraphSceneContext) -> None:
        self._boundary = boundary
        self._scene_context = scene_context

    def __getattr__(self, name: str):
        attribute = getattr(self._boundary, name)
        if not callable(attribute):
            return attribute

        def _timed_call(*args, **kwargs):
            workspace = self._scene_context.workspace_or_none()
            before_node_ids = set(workspace.nodes) if workspace is not None else set()
            before_edge_ids = set(workspace.edges) if workspace is not None else set()
            start = time.perf_counter()
            try:
                return attribute(*args, **kwargs)
            finally:
                elapsed_ms = (time.perf_counter() - start) * 1000.0
                self._scene_context.record_mutation_timing_phase(
                    "graph_model_mutation_ms", elapsed_ms
                )
                after_workspace = self._scene_context.workspace_or_none()
                after_node_ids = (
                    set(after_workspace.nodes) if after_workspace is not None else set()
                )
                after_edge_ids = (
                    set(after_workspace.edges) if after_workspace is not None else set()
                )
                dirty_node_ids = before_node_ids.symmetric_difference(after_node_ids)
                dirty_edge_ids = before_edge_ids.symmetric_difference(after_edge_ids)
                if after_workspace is not None and not dirty_node_ids:
                    node_id = kwargs.get("node_id")
                    if node_id is None and args and "node" in name:
                        node_id = args[0]
                    normalized_node_id = str(node_id or "").strip()
                    if normalized_node_id in after_workspace.nodes:
                        dirty_node_ids.add(normalized_node_id)
                if after_workspace is not None and not dirty_edge_ids:
                    edge_id = kwargs.get("edge_id")
                    if edge_id is None and args and "edge" in name:
                        edge_id = args[0]
                    normalized_edge_id = str(edge_id or "").strip()
                    if normalized_edge_id in after_workspace.edges:
                        dirty_edge_ids.add(normalized_edge_id)
                self._scene_context.record_mutation_payload_metrics(
                    dirty_node_count=len(dirty_node_ids),
                    dirty_edge_count=len(dirty_edge_ids),
                    graph_delta_payload={
                        "operation": name,
                        "dirty_node_ids": sorted(dirty_node_ids),
                        "dirty_edge_ids": sorted(dirty_edge_ids),
                    },
                )

        return _timed_call


def _run_timed_graph_operation(
    scene_context: _GraphSceneContext,
    operation_name: str,
    operation: Callable[[], Any],
) -> Any:
    if not scene_context.mutation_timing_enabled():
        return operation()
    workspace = scene_context.workspace_or_none()
    before_node_ids = set(workspace.nodes) if workspace is not None else set()
    before_edge_ids = set(workspace.edges) if workspace is not None else set()
    start = time.perf_counter()
    try:
        return operation()
    finally:
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        scene_context.record_mutation_timing_phase(
            "graph_model_mutation_ms", elapsed_ms
        )
        after_workspace = scene_context.workspace_or_none()
        after_node_ids = (
            set(after_workspace.nodes) if after_workspace is not None else set()
        )
        after_edge_ids = (
            set(after_workspace.edges) if after_workspace is not None else set()
        )
        dirty_node_ids = before_node_ids.symmetric_difference(after_node_ids)
        dirty_edge_ids = before_edge_ids.symmetric_difference(after_edge_ids)
        scene_context.record_mutation_payload_metrics(
            dirty_node_count=len(dirty_node_ids),
            dirty_edge_count=len(dirty_edge_ids),
            graph_delta_payload={
                "operation": operation_name,
                "dirty_node_ids": sorted(dirty_node_ids),
                "dirty_edge_ids": sorted(dirty_edge_ids),
            },
        )


class GraphSceneMutationPolicy:
    def __init__(self, scene_context: _GraphSceneContext) -> None:
        self._scene_context = scene_context


class GraphSceneMutationHistory:
    def __init__(
        self,
        scene_context: _GraphSceneContext,
        scope_selection: GraphSceneScopeSelection,
        *,
        boundary_adapters: GraphBoundaryAdapters,
    ) -> None:
        self._scene_context = scene_context
        self._scope_selection = scope_selection
        self._boundary_adapters = boundary_adapters

    def set_node_property(self, node_id: str, key: str, value: Any) -> None:
        return _selection_ops.set_node_property(self, node_id, key, value)

    def set_node_secret(self, node_id: str, key: str, plaintext: str) -> bool:
        return _selection_ops.set_node_secret(self, node_id, key, plaintext)

    def clear_node_secret(self, node_id: str, key: str) -> bool:
        return _selection_ops.clear_node_secret(self, node_id, key)

    def move_nodes_by_delta(self, node_ids: list[Any], dx: float, dy: float) -> bool:
        return _alignment_ops.move_nodes_by_delta(self, node_ids, dx, dy)

    def delete_selected_graph_items(self, edge_ids: list[Any]) -> bool:
        model = self._scene_context.model
        registry = self._scene_context.registry
        if model is None or registry is None:
            return False
        workspace = model.project.workspaces.get(self._scene_context.workspace_id)
        if workspace is None:
            return False

        requested_edge_ids: list[str] = []
        seen_edge_ids: set[str] = set()
        for value in edge_ids:
            edge_id = str(value).strip()
            if not edge_id or edge_id in seen_edge_ids:
                continue
            seen_edge_ids.add(edge_id)
            requested_edge_ids.append(edge_id)

        removable_node_ids = self._removable_node_ids_for_fragment(workspace)
        if not requested_edge_ids and not removable_node_ids:
            return False

        mutations = self._record_mutations()
        removed_any = False
        edge_snapshots_by_id = dict(workspace.edges)
        removed_edge_ids = {
            edge_id for edge_id in requested_edge_ids if edge_id in edge_snapshots_by_id
        }
        incident_by_node: dict[str, set[str]] = {
            node_id: set() for node_id in removable_node_ids
        }
        removable_node_lookup = set(removable_node_ids)
        incoming_link_source_ids = {
            source_node.node_id
            for source_node in workspace.nodes.values()
            if source_node.node_id not in removable_node_lookup
            and any(
                node_link_targets_node(
                    record,
                    source_workspace_id=self._scene_context.workspace_id,
                    target_workspace_id=self._scene_context.workspace_id,
                    target_node_id=target_node_id,
                )
                for target_node_id in removable_node_lookup
                for record in source_node.links
            )
        }
        for edge in edge_snapshots_by_id.values():
            if (
                edge.source_node_id in removable_node_lookup
                or edge.target_node_id in removable_node_lookup
            ):
                removed_edge_ids.add(edge.edge_id)
            if edge.source_node_id in incident_by_node:
                incident_by_node[edge.source_node_id].add(edge.edge_id)
            if edge.target_node_id in incident_by_node:
                incident_by_node[edge.target_node_id].add(edge.edge_id)
        removed_edge_snapshots = [
            edge_snapshots_by_id[edge_id] for edge_id in removed_edge_ids
        ]
        dirty_node_ids = (
            self._scene_context.endpoint_node_ids_for_edges(removed_edge_snapshots)
            | removable_node_lookup
            | incoming_link_source_ids
        )
        history_group = self._scene_context.grouped_history_action(
            ACTION_DELETE_SELECTED,
            workspace,
            commit_if=lambda: removed_any,
        )
        with history_group:
            for edge_id in requested_edge_ids:
                if edge_id not in workspace.edges:
                    continue
                mutations.remove_edge(edge_id)
                removed_any = True
            for node_id in reversed(removable_node_ids):
                if node_id not in workspace.nodes:
                    continue
                mutations.remove_node(
                    node_id, incident_edge_ids=incident_by_node.get(node_id, set())
                )
                removed_any = True
        if not removed_any:
            return False

        remaining_selected = [
            node_id
            for node_id in self._scene_context.selected_node_ids
            if node_id in workspace.nodes
        ]
        self._scope_selection.set_selected_node_ids(
            remaining_selected, workspace=workspace
        )
        self._scene_context.publish_edge_topology_delta(
            updated_edge_ids=self._scene_context.related_edge_ids_for_edges(
                removed_edge_snapshots
            ),
            removed_edge_ids=removed_edge_ids,
            dirty_node_ids=dirty_node_ids,
            removed_node_ids=removable_node_lookup,
        )
        return True

    def notify_selected_node_context_updated(self, node_id: str) -> None:
        normalized_node_id = str(node_id or "").strip()
        if (
            normalized_node_id
            and normalized_node_id in self._scene_context.selected_node_lookup
        ):
            self._scene_context.emit_node_selected(normalized_node_id)

    @staticmethod
    def _normalize_title_value(title: Any) -> str:
        return str(title).strip()

    def _normalized_title_update(self, node: NodeInstance, title: Any) -> str | None:
        normalized = self._normalize_title_value(title)
        return None if not normalized or node.title == normalized else normalized

    def _apply_title_update(
        self,
        node_id: str,
        node: NodeInstance,
        spec: NodeTypeSpec,
        normalized_title: str,
    ) -> bool:
        compact_pill = (
            str(getattr(spec, "surface_family", "standard") or "standard").strip()
            == "standard"
            and str(getattr(spec, "surface_variant", "") or "").strip()
            in _COMPACT_PILL_VARIANTS
        )
        old_min_width = 0.0
        old_effective_width = 0.0
        graph_label_pixel_size = self._scene_context.graphics_graph_label_pixel_size
        if compact_pill:
            old_metrics = node_surface_metrics(
                node,
                spec,
                graph_label_pixel_size=graph_label_pixel_size,
            )
            old_min_width = float(old_metrics.min_width)
            old_effective_width = max(
                old_min_width,
                float(node.custom_width)
                if node.custom_width is not None
                else float(old_metrics.default_width),
            )
        previous_title = node.title
        self._rename_node_artifact_folder(
            node_id=node_id,
            old_title=previous_title,
            new_title=normalized_title,
            node_type=str(
                getattr(spec, "display_name", "")
                or getattr(node, "type_id", "")
                or "Node"
            ),
        )
        mutations = self._record_mutations()
        mutations.set_node_title(node_id, normalized_title)
        if self._scene_context.surface_title_sync_enabled(spec):
            node.properties["title"] = normalized_title
        if not compact_pill:
            return False
        new_metrics = node_surface_metrics(
            node,
            spec,
            graph_label_pixel_size=graph_label_pixel_size,
        )
        new_width = old_effective_width + float(new_metrics.min_width) - old_min_width
        if abs(new_width - old_effective_width) < 1e-6:
            return False
        new_x = float(node.x) + old_effective_width - new_width
        custom_width = (
            None
            if abs(new_width - float(new_metrics.default_width)) < 1e-6
            else new_width
        )
        mutations.set_node_geometry(
            node_id,
            new_x,
            float(node.y),
            custom_width,
            node.custom_height,
        )
        return True

    @staticmethod
    def _process_qt_events() -> None:
        app = QCoreApplication.instance()
        if app is not None:
            app.processEvents()

    def _scene_host(self) -> object | None:
        bridge = getattr(self._scene_context, "_bridge", None)
        parent = getattr(bridge, "parent", None)
        if not callable(parent):
            return None
        try:
            return parent()
        except (RuntimeError, TypeError):
            return None

    def _emit_artifact_rename_signal(
        self, host: object | None, signal_name: str, node_id: str
    ) -> None:
        command_bridge = (
            getattr(host, "graph_canvas_command_bridge", None)
            if host is not None
            else None
        )
        signal = getattr(command_bridge, signal_name, None)
        emit = getattr(signal, "emit", None)
        if callable(emit):
            emit(str(node_id))
            self._process_qt_events()

    @staticmethod
    def _emit_project_meta_changed(host: object | None) -> None:
        signal = (
            getattr(host, "project_meta_changed", None) if host is not None else None
        )
        emit = getattr(signal, "emit", None)
        if callable(emit):
            emit()

    def _project_artifact_store(
        self, host: object | None, metadata: dict[str, Any]
    ) -> tuple[ProjectArtifactStore, Any]:
        controller = (
            getattr(host, "project_session_controller", None)
            if host is not None
            else None
        )
        provider = getattr(controller, "project_artifact_store", None)
        if callable(provider):
            try:
                return provider(), getattr(
                    controller, "replace_project_artifact_store", None
                )
            except Exception:  # noqa: BLE001
                pass
        project_path = (
            str(getattr(host, "project_path", "") or "").strip()
            if host is not None
            else ""
        )
        return (
            ProjectArtifactStore.from_project_metadata(
                project_path=project_path or None,
                project_metadata=metadata,
            ),
            None,
        )

    def _rename_node_artifact_folder_once(
        self,
        store: ProjectArtifactStore,
        *,
        node_id: str,
        old_title: str,
        new_title: str,
        node_type: str,
    ) -> bool:
        return store.rename_node_artifact_folder(
            workspace_id=self._scene_context.workspace_id,
            node_id=node_id,
            old_title=old_title,
            new_title=new_title,
            node_type=node_type,
        )

    def _rename_node_artifact_folder_with_retry(
        self,
        store: ProjectArtifactStore,
        *,
        node_id: str,
        old_title: str,
        new_title: str,
        node_type: str,
    ) -> bool:
        for attempt in range(_ARTIFACT_RENAME_RETRY_COUNT):
            try:
                return self._rename_node_artifact_folder_once(
                    store,
                    node_id=node_id,
                    old_title=old_title,
                    new_title=new_title,
                    node_type=node_type,
                )
            except PermissionError:
                if attempt + 1 >= _ARTIFACT_RENAME_RETRY_COUNT:
                    raise
                self._process_qt_events()
                time.sleep(_ARTIFACT_RENAME_RETRY_DELAY_SECONDS)
                self._process_qt_events()
        return False

    def _rename_node_artifact_folder(
        self,
        *,
        node_id: str,
        old_title: str,
        new_title: str,
        node_type: str,
    ) -> None:
        model = self._scene_context.model
        if model is None:
            return
        project = model.project
        metadata = project.metadata if isinstance(project.metadata, dict) else {}
        host = self._scene_host()
        store, setter = self._project_artifact_store(host, metadata)
        self._emit_artifact_rename_signal(
            host, "managedArtifactRenameReleaseRequested", node_id
        )
        try:
            if not self._rename_node_artifact_folder_with_retry(
                store,
                node_id=node_id,
                old_title=old_title,
                new_title=new_title,
                node_type=node_type,
            ):
                return
            if callable(setter):
                setter(store)
            else:
                updated_metadata = dict(metadata)
                updated_metadata[PROJECT_ARTIFACT_STORE_METADATA_KEY] = store.metadata
                if project.replace_metadata(updated_metadata):
                    self._emit_project_meta_changed(host)
        finally:
            self._emit_artifact_rename_signal(
                host, "managedArtifactRenameReleaseFinished", node_id
            )

    def _node(self, node_id: str) -> NodeInstance | None:
        return self._scene_context.node(node_id)

    def _node_or_raise(self, node_id: str) -> NodeInstance:
        return self._scene_context.node_or_raise(node_id)

    def _resync_scene_after_stale_mutation(self) -> None:
        # A canvas mutation referenced a node the model cannot resolve in the
        # active workspace/scope. The request came from a rendered visual, so
        # the scene payloads are stale; rebuild them so phantom rows (and
        # their QML delegates) are flushed instead of lingering as inert,
        # undeletable nodes until app restart.
        model = self._scene_context.model
        if model is None:
            return
        if self._scene_context.workspace_id not in model.project.workspaces:
            return
        self._scene_context.rebuild_models()

    def _timed_boundary(self, boundary: Any) -> Any:
        if self._scene_context.mutation_timing_enabled():
            return _TimedGraphMutationBoundary(boundary, self._scene_context)
        return boundary

    def _validated_mutations(self) -> ValidatedGraphMutation:
        model, registry = self._scene_context.require_bound()
        mutations = model.validated_mutations(
            self._scene_context.workspace_id,
            registry,
            boundary_adapters=self._boundary_adapters,
        )
        return self._timed_boundary(mutations)

    def _record_mutations(self) -> GraphRecordMutation:
        model, _registry = self._scene_context.require_bound()
        mutations = GraphRecordMutation(
            model=model,
            workspace_id=self._scene_context.workspace_id,
        )
        return self._timed_boundary(mutations)

    def _run_graph_operation(
        self, operation_name: str, operation: Callable[[], Any]
    ) -> Any:
        return _run_timed_graph_operation(
            self._scene_context, operation_name, operation
        )

    def _find_model_edge_id(
        self,
        source_node_id: str,
        source_port: str,
        target_node_id: str,
        target_port: str,
    ) -> str | None:
        return self._scene_context.find_model_edge_id(
            source_node_id, source_port, target_node_id, target_port
        )

    def _selected_node_ids_in_workspace(self, workspace: WorkspaceData) -> list[str]:
        return self._scope_selection.selected_node_ids_in_workspace(workspace)

    def _expanded_selected_node_ids_for_fragment(
        self, workspace: WorkspaceData
    ) -> list[str]:
        selected_node_ids = self._selected_node_ids_in_workspace(workspace)
        if not selected_node_ids:
            return []
        return expand_group_backdrop_fragment_node_ids(
            workspace=workspace,
            selected_node_ids=selected_node_ids,
            backdrop_payloads=self._scene_context.backdrop_nodes_payload,
        )

    def _removable_node_ids_for_fragment(self, workspace: WorkspaceData) -> list[str]:
        selected_node_ids = self._expanded_selected_node_ids_for_fragment(workspace)
        if not selected_node_ids:
            return []
        return subtree_node_ids(
            workspace, root_node_ids_for_fragment(workspace, selected_node_ids)
        )

    def _selected_layout_metrics(
        self,
    ) -> tuple[WorkspaceData | None, list[LayoutNodeBounds]]:
        model = self._scene_context.model
        registry = self._scene_context.registry
        if model is None or registry is None:
            return None, []
        workspace = model.project.workspaces.get(self._scene_context.workspace_id)
        if workspace is None:
            return None, []
        selected_node_ids = self._selected_node_ids_in_workspace(workspace)
        if not selected_node_ids:
            return workspace, []
        return workspace, collect_layout_node_bounds(
            workspace=workspace,
            node_ids=selected_node_ids,
            spec_lookup=registry.get_spec,
            size_resolver=self._scene_node_size,
        )

    @staticmethod
    def _snap_coordinate(value: float, grid_size: float) -> float:
        return snap_coordinate(
            value, grid_size, default_step=_alignment_ops.SNAP_GRID_SIZE
        )

    def _scene_node_size(
        self,
        node: NodeInstance,
        spec: NodeTypeSpec,
        workspace_nodes: dict[str, NodeInstance] | None = None,
    ) -> tuple[float, float]:
        return resolved_node_surface_size(
            node,
            spec,
            workspace_nodes,
            show_port_labels=self._scene_context.graphics_show_port_labels,
            graph_label_pixel_size=self._scene_context.graphics_graph_label_pixel_size,
            graph_node_icon_pixel_size=self._scene_context.graphics_node_title_icon_pixel_size,
        )

    def _apply_layout_updates(
        self,
        workspace: WorkspaceData,
        updates: dict[str, tuple[float, float]],
        *,
        snap_to_grid: bool,
        grid_size: float,
    ) -> bool:
        model = self._scene_context.model
        if model is None or not updates:
            return False
        final_positions = normalize_layout_position_updates(
            workspace=workspace,
            updates=updates,
            snap_to_grid=snap_to_grid,
            grid_size=grid_size,
            default_grid_size=_alignment_ops.SNAP_GRID_SIZE,
        )
        if not final_positions:
            return False

        history_group = self._scene_context.grouped_history_action(
            ACTION_MOVE_NODE, workspace
        )
        mutations = self._record_mutations()
        with history_group:
            for node_id, (final_x, final_y) in final_positions.items():
                mutations.set_node_position(node_id, final_x, final_y)
        self._scene_context.rebuild_models()
        return True

    @staticmethod
    def _build_subgraph_fragment_payload(
        workspace: WorkspaceData, node_ids: list[str]
    ) -> dict[str, Any] | None:
        fragment_data = build_subtree_fragment_payload_data(
            workspace=workspace, selected_node_ids=node_ids
        )
        if fragment_data is None:
            return None
        return build_graph_fragment_payload(
            nodes=fragment_data["nodes"], edges=fragment_data["edges"]
        )

    @staticmethod
    def _node_from_fragment_payload(node_payload: dict[str, Any]) -> NodeInstance:
        return fragment_node_from_payload(node_payload)

    def _fragment_bounds(self, nodes_payload: list[dict[str, Any]]) -> QRectF | None:
        registry = self._scene_context.registry
        if registry is None:
            return None
        bounds = graph_fragment_bounds(
            nodes_payload=nodes_payload,
            registry=registry,
            size_resolver=self._scene_node_size,
        )
        return (
            None
            if bounds is None
            else QRectF(bounds.x, bounds.y, bounds.width, bounds.height)
        )

    def _fragment_types_and_ports_are_valid(
        self, fragment_payload: dict[str, Any]
    ) -> bool:
        registry = self._scene_context.registry
        if registry is None:
            return False
        return graph_fragment_payload_is_valid(
            fragment_payload=fragment_payload, registry=registry
        )

    def _insert_fragment(
        self,
        fragment_payload: dict[str, Any],
        *,
        action_type: str,
        delta_x: float,
        delta_y: float,
    ) -> list[str]:
        model = self._scene_context.model
        if model is None:
            return []
        workspace = model.project.workspaces.get(self._scene_context.workspace_id)
        if workspace is None or not self._fragment_types_and_ports_are_valid(
            fragment_payload
        ):
            return []
        inserted_node_ids: list[str] = []
        history_group = self._scene_context.grouped_history_action(
            action_type,
            workspace,
            commit_if=lambda: bool(inserted_node_ids),
        )
        with history_group:
            inserted_result = self._run_graph_operation(
                "insert_graph_fragment",
                lambda: insert_graph_fragment(
                    model=model,
                    workspace_id=workspace.workspace_id,
                    fragment_payload=fragment_payload,
                    delta_x=delta_x,
                    delta_y=delta_y,
                    registry=self._scene_context.registry,
                ),
            )
            inserted_node_ids = list(inserted_result or [])
        return inserted_node_ids

    def _capture_history_snapshot(self) -> WorkspaceSnapshot | None:
        return self._scene_context.capture_history_snapshot()

    def _record_history(
        self, action_type: str, before_snapshot: WorkspaceSnapshot | None
    ) -> None:
        self._scene_context.record_history(action_type, before_snapshot)


GraphSceneMutationPolicy.are_ports_compatible = _policy.are_ports_compatible
GraphSceneMutationPolicy.compatible_endpoint_snapshot = (
    _policy.compatible_endpoint_snapshot
)
GraphSceneMutationPolicy.compatible_rewire_endpoint_snapshot = (
    _policy.compatible_rewire_endpoint_snapshot
)

GraphSceneMutationHistory.add_node_from_type = _selection_ops.add_node_from_type
GraphSceneMutationHistory.add_subnode_shell_pin = _grouping_ops.add_subnode_shell_pin
GraphSceneMutationHistory.create_node_from_type = _selection_ops.create_node_from_type
GraphSceneMutationHistory.create_nodes_batch = create_nodes_batch
GraphSceneMutationHistory.add_edge = _selection_ops.add_edge
GraphSceneMutationHistory.request_rewire_edges = _selection_ops.request_rewire_edges
GraphSceneMutationHistory.move_edge_endpoint = _selection_ops.move_edge_endpoint
GraphSceneMutationHistory.connect_nodes = _selection_ops.connect_nodes
GraphSceneMutationHistory.remove_edge = _selection_ops.remove_edge
GraphSceneMutationHistory.remove_node_with_policy = (
    _selection_ops.remove_node_with_policy
)
GraphSceneMutationHistory.remove_node = _selection_ops.remove_node
GraphSceneMutationHistory.remove_workspace_node = _selection_ops.remove_workspace_node
GraphSceneMutationHistory.focus_node = _selection_ops.focus_node
GraphSceneMutationHistory.set_node_collapsed = _selection_ops.set_node_collapsed
GraphSceneMutationHistory.set_node_settings_group_expanded = (
    _selection_ops.set_node_settings_group_expanded
)
GraphSceneMutationHistory.set_node_locked = _selection_ops.set_node_locked
GraphSceneMutationHistory.expand_collision_avoidance_updates = (
    _collision_ops.expand_collision_avoidance_updates
)
GraphSceneMutationHistory.set_node_properties = _selection_ops.set_node_properties
GraphSceneMutationHistory.upsert_node_link = _selection_ops.upsert_node_link
GraphSceneMutationHistory.remove_node_link = _selection_ops.remove_node_link
GraphSceneMutationHistory.move_node_link = _selection_ops.move_node_link
GraphSceneMutationHistory.parameter_setup_link_options = (
    _selection_ops.parameter_setup_link_options
)
GraphSceneMutationHistory.parameter_setup_link_status = (
    _selection_ops.parameter_setup_link_status
)
GraphSceneMutationHistory.link_parameter_setup = (
    _selection_ops.link_parameter_setup
)
GraphSceneMutationHistory.unlink_parameter_setup = (
    _selection_ops.unlink_parameter_setup
)
GraphSceneMutationHistory.upsert_node_comment = _selection_ops.upsert_node_comment
GraphSceneMutationHistory.remove_node_comment = _selection_ops.remove_node_comment
GraphSceneMutationHistory.set_node_comment_resolved = (
    _selection_ops.set_node_comment_resolved
)
GraphSceneMutationHistory.set_node_comment_pinned = (
    _selection_ops.set_node_comment_pinned
)
GraphSceneMutationHistory.resolve_all_node_comments = (
    _selection_ops.resolve_all_node_comments
)
GraphSceneMutationHistory.mark_node_comments_read = (
    _selection_ops.mark_node_comments_read
)
GraphSceneMutationHistory.normalize_node_visual_style = staticmethod(
    _selection_ops.normalize_node_visual_style
)
GraphSceneMutationHistory.set_node_visual_style = _selection_ops.set_node_visual_style
GraphSceneMutationHistory.clear_node_visual_style = (
    _selection_ops.clear_node_visual_style
)
GraphSceneMutationHistory.propagate_passive_node_style = (
    _selection_ops.propagate_passive_node_style
)
GraphSceneMutationHistory.set_node_title = _selection_ops.set_node_title
GraphSceneMutationHistory.normalize_edge_label = staticmethod(
    _selection_ops.normalize_edge_label
)
GraphSceneMutationHistory.set_edge_label = _selection_ops.set_edge_label
GraphSceneMutationHistory.clear_edge_label = _selection_ops.clear_edge_label
GraphSceneMutationHistory.normalize_edge_visual_style = staticmethod(
    _selection_ops.normalize_edge_visual_style
)
GraphSceneMutationHistory.set_edge_visual_style = _selection_ops.set_edge_visual_style
GraphSceneMutationHistory.clear_edge_visual_style = (
    _selection_ops.clear_edge_visual_style
)
GraphSceneMutationHistory.set_edge_enabled = _selection_ops.set_edge_enabled
GraphSceneMutationHistory.set_edges_enabled = _selection_ops.set_edges_enabled
GraphSceneMutationHistory.set_edges_display_mode = _selection_ops.set_edges_display_mode
GraphSceneMutationHistory.set_exposed_port = _selection_ops.set_exposed_port
GraphSceneMutationHistory.set_hide_optional_ports = (
    _selection_ops.set_hide_optional_ports
)
GraphSceneMutationHistory.set_node_port_label = _selection_ops.set_node_port_label
GraphSceneMutationHistory.set_port_modifiers = _selection_ops.set_port_modifiers
GraphSceneMutationHistory.set_principal_input_port = (
    _selection_ops.set_principal_input_port
)
GraphSceneMutationHistory.insert_dynamic_port = _selection_ops.insert_dynamic_port
GraphSceneMutationHistory.remove_dynamic_port = _selection_ops.remove_dynamic_port
GraphSceneMutationHistory.rename_dynamic_port = _selection_ops.rename_dynamic_port
GraphSceneMutationHistory.move_node = _alignment_ops.move_node
GraphSceneMutationHistory.resize_node = _alignment_ops.resize_node
GraphSceneMutationHistory.set_node_geometry = _alignment_ops.set_node_geometry
GraphSceneMutationHistory.align_selected_nodes = _alignment_ops.align_selected_nodes
GraphSceneMutationHistory.distribute_selected_nodes = (
    _alignment_ops.distribute_selected_nodes
)
GraphSceneMutationHistory.set_selected_same_type_size = (
    _alignment_ops.set_selected_same_type_size
)
GraphSceneMutationHistory.straighten_selected_connections = (
    _alignment_ops.straighten_selected_connections
)
GraphSceneMutationHistory.wrap_nodes_in_group_backdrop = (
    _group_backdrop_ops.wrap_nodes_in_group_backdrop
)
GraphSceneMutationHistory.wrap_selected_nodes_in_group_backdrop = (
    _group_backdrop_ops.wrap_selected_nodes_in_group_backdrop
)
GraphSceneMutationHistory.group_selected_nodes = _grouping_ops.group_selected_nodes
GraphSceneMutationHistory.ungroup_selected_subnode = (
    _grouping_ops.ungroup_selected_subnode
)
GraphSceneMutationHistory.duplicate_selected_subgraph = (
    _clipboard_ops.duplicate_selected_subgraph
)
GraphSceneMutationHistory.serialize_selected_subgraph_fragment = (
    _clipboard_ops.serialize_selected_subgraph_fragment
)
GraphSceneMutationHistory.fragment_bounds_center = _clipboard_ops.fragment_bounds_center
GraphSceneMutationHistory.paste_subgraph_fragment = (
    _clipboard_ops.paste_subgraph_fragment
)

__all__ = ["GraphSceneMutationHistory", "GraphSceneMutationPolicy"]

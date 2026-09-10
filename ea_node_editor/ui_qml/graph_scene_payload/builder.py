from __future__ import annotations

"""Graph scene payload builder composition root."""


import copy
from collections import ChainMap
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, Mapping


from ea_node_editor.graph.group_backdrop_geometry import (
    GroupBackdropCandidate,
    compute_group_backdrop_membership,
)
from ea_node_editor.graph.boundary_adapters import GraphBoundaryAdapters, fallback_graph_boundary_adapters
from ea_node_editor.graph.hierarchy import ScopePath
from ea_node_editor.graph.hierarchy import is_node_in_scope, node_scope_path, scope_edges, scope_node_ids
from ea_node_editor.graph.model import GraphModel
from ea_node_editor.graph.records import NodeInstance
from ea_node_editor.graph.workspace_state import WorkspaceData
from ea_node_editor.app_preferences import (
    effective_graph_node_icon_pixel_size,
    normalize_graph_label_pixel_size,
)
from ea_node_editor.nodes.plugin_contracts import PluginProvenance
from ea_node_editor.nodes.registry import NodeRegistry
from ea_node_editor.settings import DEFAULT_GRAPH_LABEL_PIXEL_SIZE
from ea_node_editor.nodes.node_specs import NodeTypeSpec, PortSpec
from ea_node_editor.ui.shell.library_projection import projected_port_declared_data_types
from ea_node_editor.ui.graph_theme import (
    GraphThemeDefinition,
)
from ea_node_editor.ui.support.node_presentation import build_data_type_ui_projection
from ea_node_editor.ui_qml.edge_routing import _build_edge_payload_item, _edge_payload_lane_offsets

if TYPE_CHECKING:
    from ea_node_editor.ui_qml.graph_theme_bridge import GraphThemeBridge

from ea_node_editor.ui_qml.graph_scene_payload.backdrop_partitioner import (
    _GraphSceneBackdropPartitioner,
)
from ea_node_editor.ui_qml.graph_scene_payload.factory import (
    _GraphSceneNodePayloadFactory,
    _NodePresentationFacts,
)
from ea_node_editor.ui_qml.graph_scene_payload.kinds.plot import apply_plot_surface_payload
from ea_node_editor.ui_qml.graph_scene_payload.normalize import (
    _annotate_edge_payload_availability,
)
from ea_node_editor.ui_qml.graph_scene_payload.theme_inputs import (
    _GraphSceneThemeResolver,
)


class GraphScenePayloadBuilder:
    def __init__(self, boundary_adapters: GraphBoundaryAdapters | None = None, *, current_input_provider: Any = None, property_edit_adapters: Any = (), keep_expanded_node_width_provider: Callable[[], bool] | None = None) -> None:
        self.boundary_adapters = boundary_adapters or fallback_graph_boundary_adapters()
        self._theme_resolver = _GraphSceneThemeResolver()
        self._node_payload_factory = _GraphSceneNodePayloadFactory(
            self.boundary_adapters, current_input_provider, property_edit_adapters,
            keep_expanded_node_width_provider=keep_expanded_node_width_provider,
        )
        self._backdrop_partitioner = _GraphSceneBackdropPartitioner(self._node_payload_factory)
        self._mutation_timing_enabled = False
        self._last_mutation_phase_timings_ms: dict[str, float] = {}

    def build_inline_properties_payload(
        self,
        *,
        node: Any,
        spec: NodeTypeSpec,
        workspace: WorkspaceData,
        workspace_nodes: Mapping[str, Any],
        enabled_input_port_keys: set[str] | frozenset[str],
        port_connection_counts: Mapping[tuple[str, str], int],
    ) -> list[dict[str, Any]]:
        self._node_payload_factory._workspace_edges = workspace.edges
        return self._node_payload_factory.build_inline_properties_payload(
            node=node,
            spec=spec,
            workspace_nodes=workspace_nodes,
            enabled_input_port_keys=enabled_input_port_keys,
            port_connection_counts=port_connection_counts,
        )

    @staticmethod
    def _presentation_sizes(
        graph_label_pixel_size: object,
        graph_node_icon_pixel_size: object | None,
    ) -> tuple[int, int]:
        label_size = normalize_graph_label_pixel_size(graph_label_pixel_size)
        return label_size, effective_graph_node_icon_pixel_size(
            label_size,
            graph_node_icon_pixel_size,
        )

    def set_mutation_timing_enabled(self, enabled: bool) -> None:
        self._mutation_timing_enabled = bool(enabled)
        self._backdrop_partitioner.set_mutation_timing_enabled(enabled)
        if not self._mutation_timing_enabled:
            self._last_mutation_phase_timings_ms = {}

    def mutation_phase_timings_ms(self) -> dict[str, float]:
        return dict(self._last_mutation_phase_timings_ms)

    @staticmethod
    def _spec_and_provenance(
        registry: NodeRegistry,
        type_id: str,
        properties: Mapping[str, object] | None = None,
    ) -> tuple[NodeTypeSpec | None, PluginProvenance | None]:
        provenance = None
        descriptor_or_none = getattr(registry, "descriptor_or_none", None)
        descriptor = descriptor_or_none(type_id) if callable(descriptor_or_none) else None
        spec = descriptor.spec if descriptor is not None else None
        if descriptor is not None:
            provenance = descriptor.provenance
        if spec is None:
            spec = registry.spec_or_none(type_id)
        if provenance is None:
            provenance_or_none = getattr(registry, "provenance_or_none", None)
            if callable(provenance_or_none):
                provenance = provenance_or_none(type_id)
        if spec is not None and properties is not None:
            spec = registry.resolve_spec(type_id, properties)
        return spec, provenance

    @staticmethod
    def _library_preview_fallback_spec(payload: Mapping[str, Any]) -> NodeTypeSpec | None:
        type_id = str(payload.get("type_id", "") or "").strip()
        raw_ports = payload.get("ports", ())
        if not type_id or not isinstance(raw_ports, (list, tuple)):
            return None
        ports: list[PortSpec] = []
        for item in raw_ports:
            if not isinstance(item, Mapping):
                continue
            key = str(item.get("key", "") or "").strip()
            direction = str(item.get("direction", "") or "").strip().lower()
            kind = str(item.get("kind", "") or "").strip().lower()
            if not key or direction not in {"in", "out", "neutral"} or not kind:
                continue
            declared_types = projected_port_declared_data_types(item)
            if not declared_types:
                continue
            ports.append(
                PortSpec(
                    key,
                    direction,
                    kind,
                    declared_types[0],
                    label=str(item.get("label", "") or key),
                    required=bool(item.get("required", True)),
                    exposed=item.get("exposed", True) is not False,
                    side=str(item.get("side", "") or ""),
                    accepted_data_types=declared_types[1:],
                    data_access=str(item.get("data_access", "item") or "item"),
                )
            )
        return NodeTypeSpec(
            type_id=type_id,
            display_name=str(payload.get("display_name", "") or type_id),
            category_path=("Custom Workflows",),
            icon="",
            ports=tuple(ports),
            properties=(),
            runtime_behavior=str(payload.get("runtime_behavior", "active") or "active"),
            surface_family=str(payload.get("surface_family", "standard") or "standard"),
            surface_variant=str(payload.get("surface_variant", "") or ""),
        )

    def build_library_preview_node_payload(
        self,
        *,
        model: GraphModel | None,
        registry: NodeRegistry | None,
        workspace_id: str,
        library_payload: Mapping[str, Any],
        graph_theme_bridge: GraphThemeBridge | None,
        show_port_labels: bool = True,
        graph_label_pixel_size: int = DEFAULT_GRAPH_LABEL_PIXEL_SIZE,
        graph_node_icon_pixel_size: int | None = None,
        lightweight_canvas: bool = False,
    ) -> dict[str, Any]:
        type_id = str(library_payload.get("type_id", "") or "").strip()
        if not type_id:
            return {}
        spec = None
        provenance = None
        if registry is not None:
            spec, provenance = self._spec_and_provenance(registry, type_id)
        if spec is None:
            spec = self._library_preview_fallback_spec(library_payload)
        if spec is None:
            return dict(library_payload)

        workspace = None if model is None else model.project.workspaces.get(str(workspace_id))
        if workspace is None:
            workspace = WorkspaceData(workspace_id="__library_preview__", name="Library Preview")
            workspace.ensure_default_view()
        preview_node = NodeInstance(
            node_id="__library_drop_preview__",
            type_id=type_id,
            title=str(library_payload.get("display_name", "") or spec.display_name),
            x=0.0,
            y=0.0,
            properties=registry.default_properties(type_id) if registry is not None and registry.spec_or_none(type_id) else {},
        )
        if registry is not None and registry.spec_or_none(type_id) is not None:
            spec = registry.resolve_spec(type_id, preview_node.properties)
        workspace_nodes = ChainMap({preview_node.node_id: preview_node}, workspace.nodes)
        hide_optional_ports = _GraphSceneBackdropPartitioner.active_view_hide_optional_ports(workspace)
        graph_label_pixel_size, graph_node_icon_pixel_size = self._presentation_sizes(
            graph_label_pixel_size,
            graph_node_icon_pixel_size,
        )
        presentation_facts = self._node_payload_factory.build_presentation_facts(
            node=preview_node,
            spec=spec,
            provenance=provenance,
            workspace_nodes=workspace_nodes,
            enabled_input_port_keys=frozenset(),
            port_connection_counts={},
            hide_optional_ports=hide_optional_ports,
            show_port_labels=show_port_labels,
            graph_label_pixel_size=graph_label_pixel_size,
            graph_node_icon_pixel_size=graph_node_icon_pixel_size,
        )
        data_type_projection = (
            build_data_type_ui_projection(registry.data_types)
            if registry is not None
            else None
        )
        return self._node_payload_factory.build_node_payload(
            node=preview_node,
            spec=spec,
            provenance=provenance,
            workspace=workspace,
            workspace_nodes=workspace_nodes,
            port_connection_counts={},
            graph_theme=self.active_graph_theme(graph_theme_bridge),
            graph_theme_bridge=graph_theme_bridge,
            hide_optional_ports=hide_optional_ports,
            show_port_labels=show_port_labels,
            graph_label_pixel_size=graph_label_pixel_size,
            graph_node_icon_pixel_size=graph_node_icon_pixel_size,
            lightweight_canvas=lightweight_canvas,
            presentation_facts=presentation_facts,
            data_type_projection=data_type_projection,
        )

    def build_added_node_payloads_for_ids(
        self,
        *,
        model: GraphModel | None,
        registry: NodeRegistry | None,
        workspace_id: str,
        scope_path: ScopePath,
        node_ids: set[str],
        graph_theme_bridge: GraphThemeBridge | None,
        show_port_labels: bool = True,
        graph_label_pixel_size: int = DEFAULT_GRAPH_LABEL_PIXEL_SIZE,
        graph_node_icon_pixel_size: int | None = None,
        lightweight_canvas: bool = False,
        port_connection_counts: Mapping[tuple[str, str], int] | None = None,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
        if model is None or registry is None or not workspace_id or not node_ids:
            return [], [], []
        workspace = model.project.workspaces.get(workspace_id)
        if workspace is None:
            return [], [], []

        requested_ids = {
            normalized
            for value in node_ids
            if (normalized := str(value or "").strip())
        }
        if not requested_ids:
            return [], [], []
        workspace_edges = scope_edges(workspace, scope_path)
        if port_connection_counts is None:
            port_connection_counts = _GraphSceneBackdropPartitioner.port_connection_counts(workspace_edges)
        else:
            port_connection_counts = dict(port_connection_counts)
        enabled_input_port_keys_by_node = (
            _GraphSceneBackdropPartitioner.enabled_input_port_keys_by_node(
                workspace_edges
            )
        )
        graph_label_pixel_size, graph_node_icon_pixel_size = self._presentation_sizes(
            graph_label_pixel_size,
            graph_node_icon_pixel_size,
        )
        workspace_nodes = ChainMap({}, workspace.nodes)
        hide_optional_ports = _GraphSceneBackdropPartitioner.active_view_hide_optional_ports(workspace)
        graph_theme = self.active_graph_theme(graph_theme_bridge)
        data_type_projection = build_data_type_ui_projection(registry.data_types)

        nodes_payload: list[dict[str, Any]] = []
        backdrop_nodes_payload: list[dict[str, Any]] = []
        minimap_nodes_payload: list[dict[str, Any]] = []
        for node_id in sorted(requested_ids):
            node = workspace.nodes.get(node_id)
            if node is None or not is_node_in_scope(workspace, node_id, scope_path):
                continue
            spec, provenance = self._spec_and_provenance(
                registry, node.type_id, node.properties
            )
            if spec is None:
                continue
            presentation_facts = self._node_payload_factory.build_presentation_facts(
                node=node,
                spec=spec,
                provenance=provenance,
                workspace_nodes=workspace_nodes,
                enabled_input_port_keys=enabled_input_port_keys_by_node.get(
                    str(node_id), frozenset()
                ),
                port_connection_counts=port_connection_counts,
                hide_optional_ports=hide_optional_ports,
                show_port_labels=show_port_labels,
                graph_label_pixel_size=graph_label_pixel_size,
                graph_node_icon_pixel_size=graph_node_icon_pixel_size,
            )
            payload = self._node_payload_factory.build_node_payload(
                node=node,
                spec=spec,
                provenance=provenance,
                workspace=workspace,
                workspace_nodes=workspace_nodes,
                port_connection_counts=port_connection_counts,
                graph_theme=graph_theme,
                graph_theme_bridge=graph_theme_bridge,
                hide_optional_ports=hide_optional_ports,
                show_port_labels=show_port_labels,
                graph_label_pixel_size=graph_label_pixel_size,
                graph_node_icon_pixel_size=graph_node_icon_pixel_size,
                lightweight_canvas=lightweight_canvas,
                presentation_facts=presentation_facts,
                data_type_projection=data_type_projection,
            )
            is_group_backdrop = presentation_facts.is_group_backdrop
            _GraphSceneBackdropPartitioner.apply_group_backdrop_membership_payload(
                payload,
                None,
                is_group_backdrop=is_group_backdrop,
            )
            if is_group_backdrop:
                backdrop_nodes_payload.append(payload)
            else:
                nodes_payload.append(payload)
            minimap_nodes_payload.append(
                self._node_payload_factory.build_minimap_node_payload(
                    node=node,
                    spec=spec,
                    workspace=workspace,
                    workspace_nodes=workspace_nodes,
                    show_port_labels=show_port_labels,
                    port_connection_counts=port_connection_counts,
                    hide_optional_ports=hide_optional_ports,
                    graph_label_pixel_size=graph_label_pixel_size,
                    graph_node_icon_pixel_size=graph_node_icon_pixel_size,
                    presentation_facts=presentation_facts,
                )
            )
        return nodes_payload, backdrop_nodes_payload, minimap_nodes_payload

    def build_node_connection_payloads_for_ids(
        self,
        *,
        model: GraphModel | None,
        registry: NodeRegistry | None,
        workspace_id: str,
        scope_path: ScopePath,
        node_ids: set[str],
        graph_theme_bridge: GraphThemeBridge | None,
        show_port_labels: bool = True,
        graph_label_pixel_size: int = DEFAULT_GRAPH_LABEL_PIXEL_SIZE,
        graph_node_icon_pixel_size: int | None = None,
        lightweight_canvas: bool = False,
        port_connection_counts: Mapping[tuple[str, str], int] | None = None,
    ) -> dict[str, dict[str, Any]]:
        if model is None or registry is None or not workspace_id or not node_ids:
            return {}
        workspace = model.project.workspaces.get(workspace_id)
        if workspace is None:
            return {}
        visible_node_ids = set(scope_node_ids(workspace, scope_path))
        if port_connection_counts is None:
            port_connection_counts = _GraphSceneBackdropPartitioner.port_connection_counts(
                scope_edges(workspace, scope_path)
            )
        else:
            port_connection_counts = dict(port_connection_counts)
        workspace_nodes = dict(workspace.nodes)
        hide_optional_ports = _GraphSceneBackdropPartitioner.active_view_hide_optional_ports(workspace)
        graph_label_pixel_size, graph_node_icon_pixel_size = self._presentation_sizes(
            graph_label_pixel_size,
            graph_node_icon_pixel_size,
        )
        graph_theme = self.active_graph_theme(graph_theme_bridge)
        data_type_projection = build_data_type_ui_projection(registry.data_types)
        payloads: dict[str, dict[str, Any]] = {}
        for node_id in sorted(str(value).strip() for value in node_ids):
            if not node_id or node_id not in visible_node_ids:
                continue
            node = workspace.nodes.get(node_id)
            if node is None:
                continue
            spec, provenance = self._spec_and_provenance(
                registry, node.type_id, node.properties
            )
            if spec is None:
                continue
            payload_node = self._node_payload_factory.payload_node(node, spec)
            workspace_nodes[node_id] = payload_node
            full_payload = self._node_payload_factory.build_node_payload(
                node=payload_node,
                spec=spec,
                provenance=provenance,
                workspace=workspace,
                workspace_nodes=workspace_nodes,
                port_connection_counts=port_connection_counts,
                graph_theme=graph_theme,
                graph_theme_bridge=graph_theme_bridge,
                hide_optional_ports=hide_optional_ports,
                show_port_labels=show_port_labels,
                graph_label_pixel_size=graph_label_pixel_size,
                graph_node_icon_pixel_size=graph_node_icon_pixel_size,
                lightweight_canvas=lightweight_canvas,
                data_type_projection=data_type_projection,
            )
            payloads[node_id] = {
                key: copy.deepcopy(full_payload[key])
                for key in (
                    "ports",
                    "inline_properties",
                    "surface_metrics",
                    "width",
                    "height",
                )
            }
            for key in ("port_presentation", "settings_band", "settings_groups"):
                if key in full_payload:
                    payloads[node_id][key] = copy.deepcopy(full_payload[key])
            apply_plot_surface_payload(
                payloads[node_id],
                node=payload_node,
                spec=spec,
                workspace=workspace,
                graph_theme_bridge=graph_theme_bridge,
                lightweight_canvas=lightweight_canvas,
            )
        return payloads

    def build_node_payloads_for_ids(
        self,
        *,
        model: GraphModel | None,
        registry: NodeRegistry | None,
        workspace_id: str,
        scope_path: ScopePath,
        node_ids: set[str],
        graph_theme_bridge: GraphThemeBridge | None,
        show_port_labels: bool = True,
        graph_label_pixel_size: int = DEFAULT_GRAPH_LABEL_PIXEL_SIZE,
        graph_node_icon_pixel_size: int | None = None,
        lightweight_canvas: bool = False,
        port_connection_counts: Mapping[tuple[str, str], int] | None = None,
        previous_payloads_by_id: Mapping[str, Mapping[str, Any]] | None = None,
        changed_fields_by_node_id: Mapping[str, set[str] | frozenset[str] | tuple[str, ...] | None] | None = None,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
        if model is None or registry is None or not workspace_id or not node_ids:
            return [], [], []
        workspace = model.project.workspaces.get(workspace_id)
        if workspace is None:
            return [], [], []

        requested_ids = {
            normalized
            for value in node_ids
            if (normalized := str(value or "").strip())
        }
        if not requested_ids:
            return [], [], []

        visible_node_ids = set(scope_node_ids(workspace, scope_path))
        workspace_edges = scope_edges(workspace, scope_path)
        if port_connection_counts is None:
            port_connection_counts = _GraphSceneBackdropPartitioner.port_connection_counts(workspace_edges)
        else:
            port_connection_counts = dict(port_connection_counts)
        enabled_input_port_keys_by_node = (
            _GraphSceneBackdropPartitioner.enabled_input_port_keys_by_node(
                workspace_edges
            )
        )
        workspace_nodes = dict(workspace.nodes)
        hide_optional_ports = _GraphSceneBackdropPartitioner.active_view_hide_optional_ports(workspace)
        graph_label_pixel_size, graph_node_icon_pixel_size = self._presentation_sizes(
            graph_label_pixel_size,
            graph_node_icon_pixel_size,
        )
        graph_theme = self.active_graph_theme(graph_theme_bridge)
        data_type_projection = build_data_type_ui_projection(registry.data_types)

        nodes_payload: list[dict[str, Any]] = []
        backdrop_nodes_payload: list[dict[str, Any]] = []
        minimap_nodes_payload: list[dict[str, Any]] = []
        presentation_facts_by_node_id: dict[str, _NodePresentationFacts] = {}
        for node_id in sorted(requested_ids):
            if node_id not in visible_node_ids:
                continue
            node = workspace.nodes.get(node_id)
            if node is None:
                continue
            spec, provenance = self._spec_and_provenance(
                registry, node.type_id, node.properties
            )
            if spec is None:
                continue
            presentation_facts = self._node_payload_factory.build_presentation_facts(
                node=node,
                spec=spec,
                provenance=provenance,
                workspace_nodes=workspace_nodes,
                enabled_input_port_keys=enabled_input_port_keys_by_node.get(
                    str(node_id), frozenset()
                ),
                port_connection_counts=port_connection_counts,
                hide_optional_ports=hide_optional_ports,
                show_port_labels=show_port_labels,
                graph_label_pixel_size=graph_label_pixel_size,
                graph_node_icon_pixel_size=graph_node_icon_pixel_size,
            )
            presentation_facts_by_node_id[node_id] = presentation_facts
            node_payload = self._node_payload_factory.build_node_payload(
                node=node,
                spec=spec,
                provenance=provenance,
                workspace=workspace,
                workspace_nodes=workspace_nodes,
                port_connection_counts=port_connection_counts,
                graph_theme=graph_theme,
                graph_theme_bridge=graph_theme_bridge,
                hide_optional_ports=hide_optional_ports,
                show_port_labels=show_port_labels,
                graph_label_pixel_size=graph_label_pixel_size,
                graph_node_icon_pixel_size=graph_node_icon_pixel_size,
                lightweight_canvas=lightweight_canvas,
                previous_payload=(
                    previous_payloads_by_id.get(node_id)
                    if previous_payloads_by_id is not None
                    else None
                ),
                changed_fields=(
                    changed_fields_by_node_id.get(node_id)
                    if changed_fields_by_node_id is not None and node_id in changed_fields_by_node_id
                    else None
                ),
                presentation_facts=presentation_facts,
                data_type_projection=data_type_projection,
            )
            is_group_backdrop = presentation_facts.is_group_backdrop
            _GraphSceneBackdropPartitioner.apply_group_backdrop_membership_payload(
                node_payload,
                None,
                is_group_backdrop=is_group_backdrop,
            )
            if is_group_backdrop:
                backdrop_nodes_payload.append(node_payload)
            else:
                nodes_payload.append(node_payload)
            minimap_nodes_payload.append(
                self._node_payload_factory.build_minimap_node_payload(
                    node=node,
                    spec=spec,
                    workspace=workspace,
                    workspace_nodes=workspace_nodes,
                    show_port_labels=show_port_labels,
                    port_connection_counts=port_connection_counts,
                    hide_optional_ports=hide_optional_ports,
                    graph_label_pixel_size=graph_label_pixel_size,
                    graph_node_icon_pixel_size=graph_node_icon_pixel_size,
                    presentation_facts=presentation_facts,
                )
            )
        return nodes_payload, backdrop_nodes_payload, minimap_nodes_payload

    def build_edge_payloads_for_ids(
        self,
        *,
        model: GraphModel | None,
        registry: NodeRegistry | None,
        workspace_id: str,
        scope_path: ScopePath,
        edge_ids: set[str],
        graph_theme_bridge: GraphThemeBridge | None,
        comment_peek_node_id: str = "",
        show_port_labels: bool = True,
        graph_label_pixel_size: int = DEFAULT_GRAPH_LABEL_PIXEL_SIZE,
        graph_node_icon_pixel_size: int | None = None,
        lightweight_canvas: bool = False,
    ) -> list[dict[str, Any]]:
        return self._build_edge_payloads_for_ids(
            model=model,
            registry=registry,
            workspace_id=workspace_id,
            scope_path=scope_path,
            edge_ids=edge_ids,
            graph_theme_bridge=graph_theme_bridge,
            comment_peek_node_id=comment_peek_node_id,
            show_port_labels=show_port_labels,
            graph_label_pixel_size=graph_label_pixel_size,
            graph_node_icon_pixel_size=graph_node_icon_pixel_size,
            lightweight_canvas=lightweight_canvas,
            assume_unobscured=False,
        )

    def build_unobscured_edge_payloads_for_ids(
        self,
        *,
        model: GraphModel | None,
        registry: NodeRegistry | None,
        workspace_id: str,
        scope_path: ScopePath,
        edge_ids: set[str],
        graph_theme_bridge: GraphThemeBridge | None,
        show_port_labels: bool = True,
        graph_label_pixel_size: int = DEFAULT_GRAPH_LABEL_PIXEL_SIZE,
        graph_node_icon_pixel_size: int | None = None,
        lightweight_canvas: bool = False,
    ) -> list[dict[str, Any]]:
        return self._build_edge_payloads_for_ids(
            model=model,
            registry=registry,
            workspace_id=workspace_id,
            scope_path=scope_path,
            edge_ids=edge_ids,
            graph_theme_bridge=graph_theme_bridge,
            show_port_labels=show_port_labels,
            graph_label_pixel_size=graph_label_pixel_size,
            graph_node_icon_pixel_size=graph_node_icon_pixel_size,
            lightweight_canvas=lightweight_canvas,
            assume_unobscured=True,
        )

    def _build_edge_payloads_for_ids(
        self,
        *,
        model: GraphModel | None,
        registry: NodeRegistry | None,
        workspace_id: str,
        scope_path: ScopePath,
        edge_ids: set[str],
        graph_theme_bridge: GraphThemeBridge | None,
        comment_peek_node_id: str = "",
        show_port_labels: bool = True,
        graph_label_pixel_size: int = DEFAULT_GRAPH_LABEL_PIXEL_SIZE,
        graph_node_icon_pixel_size: int | None = None,
        lightweight_canvas: bool = False,
        assume_unobscured: bool,
    ) -> list[dict[str, Any]]:
        requested_edge_ids = {str(edge_id).strip() for edge_id in edge_ids if str(edge_id).strip()}
        if model is None or registry is None or not workspace_id or not requested_edge_ids:
            return []
        workspace = model.project.workspaces.get(workspace_id)
        if workspace is None:
            return []

        graph_label_pixel_size, graph_node_icon_pixel_size = self._presentation_sizes(
            graph_label_pixel_size,
            graph_node_icon_pixel_size,
        )
        workspace_edges = scope_edges(workspace, scope_path)
        if assume_unobscured:
            visible_node_ids = {
                node_id
                for edge in workspace_edges
                if edge.edge_id in requested_edge_ids
                for node_id in (edge.source_node_id, edge.target_node_id)
            }
        else:
            visible_node_ids = scope_node_ids(workspace, scope_path)
        port_connection_counts = _GraphSceneBackdropPartitioner.port_connection_counts(workspace_edges)
        enabled_input_port_keys_by_node = (
            _GraphSceneBackdropPartitioner.enabled_input_port_keys_by_node(
                workspace_edges
            )
        )
        hide_optional_ports = _GraphSceneBackdropPartitioner.active_view_hide_optional_ports(workspace)
        workspace_nodes = dict(workspace.nodes)
        node_specs: dict[str, NodeTypeSpec] = {}
        presentation_facts_by_node_id: dict[str, _NodePresentationFacts] = {}
        group_backdrop_ids: set[str] = set()
        membership_candidates: list[GroupBackdropCandidate] = []

        for node_id in visible_node_ids:
            node = workspace.nodes.get(node_id)
            if node is None:
                continue
            spec, provenance = self._spec_and_provenance(
                registry, node.type_id, node.properties
            )
            if spec is None:
                continue
            node_specs[node_id] = spec
            presentation_facts = self._node_payload_factory.build_presentation_facts(
                node=node,
                spec=spec,
                provenance=provenance,
                workspace_nodes=workspace_nodes,
                enabled_input_port_keys=enabled_input_port_keys_by_node.get(
                    str(node_id), frozenset()
                ),
                port_connection_counts=port_connection_counts,
                hide_optional_ports=hide_optional_ports,
                show_port_labels=show_port_labels,
                graph_label_pixel_size=graph_label_pixel_size,
                graph_node_icon_pixel_size=graph_node_icon_pixel_size,
            )
            presentation_facts_by_node_id[node_id] = presentation_facts
            is_group_backdrop = presentation_facts.is_group_backdrop
            if is_group_backdrop:
                group_backdrop_ids.add(node_id)
            membership_width, membership_height = self._node_payload_factory.membership_candidate_size(
                node=node,
                spec=spec,
                workspace=workspace,
                workspace_nodes=workspace_nodes,
                is_group_backdrop=is_group_backdrop,
                show_port_labels=show_port_labels,
                graph_label_pixel_size=graph_label_pixel_size,
                graph_node_icon_pixel_size=graph_node_icon_pixel_size,
                port_connection_counts=port_connection_counts,
                hide_optional_ports=hide_optional_ports,
                presentation_facts=presentation_facts,
            )
            membership_candidates.append(
                GroupBackdropCandidate(
                    node_id=node_id,
                    scope_path=node_scope_path(workspace, node_id),
                    is_backdrop=is_group_backdrop,
                    x=float(presentation_facts.bounds.x),
                    y=float(presentation_facts.bounds.y),
                    width=float(membership_width),
                    height=float(membership_height),
                )
            )

        if assume_unobscured:
            collapsed_proxy_backdrop_by_node_id = {}
            render_workspace_edges = workspace_edges
        else:
            membership_by_node_id = compute_group_backdrop_membership(membership_candidates)
            comment_peek_visible_node_ids = _GraphSceneBackdropPartitioner.comment_peek_visible_node_ids(
                comment_peek_node_id=str(comment_peek_node_id or "").strip(),
                visible_node_ids=visible_node_ids,
                membership_by_node_id=membership_by_node_id,
                workspace=workspace,
                group_backdrop_ids=group_backdrop_ids,
            )
            render_node_ids = (
                set(comment_peek_visible_node_ids) if comment_peek_visible_node_ids else set(visible_node_ids)
            )
            collapsed_proxy_backdrop_by_node_id = _GraphSceneBackdropPartitioner.collapsed_proxy_backdrop_by_node_id(
                visible_node_ids=visible_node_ids,
                membership_by_node_id=membership_by_node_id,
                workspace=workspace,
                group_backdrop_ids=group_backdrop_ids,
                comment_peek_node_id=comment_peek_node_id if comment_peek_visible_node_ids else "",
            )
            render_workspace_edges = [
                edge
                for edge in workspace_edges
                if edge.source_node_id in render_node_ids and edge.target_node_id in render_node_ids
            ]
        lane_offsets = _edge_payload_lane_offsets(render_workspace_edges)
        graph_theme = self.active_graph_theme(graph_theme_bridge)

        edges_payload: list[dict[str, Any]] = []
        for edge in render_workspace_edges:
            if edge.edge_id not in requested_edge_ids:
                continue
            payload_item = _build_edge_payload_item(
                edge=edge,
                graph_theme=graph_theme,
                workspace_nodes=workspace_nodes,
                node_specs=node_specs,
                data_types=registry.data_types,
                collapsed_proxy_backdrop_by_node_id=collapsed_proxy_backdrop_by_node_id,
                lane_offsets=lane_offsets,
                show_port_labels=show_port_labels,
                graph_label_pixel_size=graph_label_pixel_size,
                graph_node_icon_pixel_size=graph_node_icon_pixel_size,
                presentation_facts_by_node_id=presentation_facts_by_node_id,
            )
            if payload_item is not None:
                _annotate_edge_payload_availability(
                    payload_item,
                    workspace=workspace,
                    edge=edge,
                    workspace_nodes=workspace_nodes,
                    node_specs=node_specs,
                )
                edges_payload.append(payload_item)
        return edges_payload

    def edge_item(
        self,
        *,
        workspace: WorkspaceData,
        scope_path: ScopePath,
        edge_id: str,
    ) -> dict[str, Any] | None:
        edge = workspace.edges.get(edge_id)
        if edge is None:
            return None
        if not is_node_in_scope(workspace, edge.source_node_id, scope_path):
            return None
        if not is_node_in_scope(workspace, edge.target_node_id, scope_path):
            return None
        return {
            "edge_id": edge.edge_id,
            "source_node_id": edge.source_node_id,
            "source_port_key": edge.source_port_key,
            "target_node_id": edge.target_node_id,
            "target_port_key": edge.target_port_key,
            "enabled": bool(edge.enabled),
            "input_order": int(edge.input_order),
            "label": str(edge.label),
            "visual_style": copy.deepcopy(edge.visual_style),
        }

    def rebuild_models(
        self,
        *,
        model: GraphModel | None,
        registry: NodeRegistry | None,
        workspace_id: str,
        scope_path: ScopePath,
        graph_theme_bridge: GraphThemeBridge | None,
        comment_peek_node_id: str = "",
        show_port_labels: bool = True,
        graph_label_pixel_size: int = DEFAULT_GRAPH_LABEL_PIXEL_SIZE,
        graph_node_icon_pixel_size: int | None = None,
        lightweight_canvas: bool = False,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
        nodes_payload, _backdrop_nodes_payload, minimap_nodes_payload, edges_payload = self.rebuild_partitioned_models(
            model=model,
            registry=registry,
            workspace_id=workspace_id,
            scope_path=scope_path,
            comment_peek_node_id=comment_peek_node_id,
            graph_theme_bridge=graph_theme_bridge,
            show_port_labels=show_port_labels,
            graph_label_pixel_size=graph_label_pixel_size,
            graph_node_icon_pixel_size=graph_node_icon_pixel_size,
            lightweight_canvas=lightweight_canvas,
        )
        return nodes_payload, minimap_nodes_payload, edges_payload

    def rebuild_partitioned_models(
        self,
        *,
        model: GraphModel | None,
        registry: NodeRegistry | None,
        workspace_id: str,
        scope_path: ScopePath,
        graph_theme_bridge: GraphThemeBridge | None,
        comment_peek_node_id: str = "",
        show_port_labels: bool = True,
        graph_label_pixel_size: int = DEFAULT_GRAPH_LABEL_PIXEL_SIZE,
        graph_node_icon_pixel_size: int | None = None,
        lightweight_canvas: bool = False,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
        self._last_mutation_phase_timings_ms = {}
        if model is None or registry is None or not workspace_id:
            return [], [], [], []

        workspace = model.project.workspaces[workspace_id]
        graph_label_pixel_size, graph_node_icon_pixel_size = self._presentation_sizes(
            graph_label_pixel_size,
            graph_node_icon_pixel_size,
        )
        payloads = self._backdrop_partitioner.build_payload_models(
            workspace=workspace,
            registry=registry,
            scope_path=scope_path,
            comment_peek_node_id=comment_peek_node_id,
            graph_theme=self.active_graph_theme(graph_theme_bridge),
            graph_theme_bridge=graph_theme_bridge,
            graph_label_pixel_size=graph_label_pixel_size,
            graph_node_icon_pixel_size=graph_node_icon_pixel_size,
            lightweight_canvas=lightweight_canvas,
            show_port_labels=show_port_labels,
        )
        self._last_mutation_phase_timings_ms = self._backdrop_partitioner.mutation_phase_timings_ms()
        return payloads

    def active_graph_theme(self, graph_theme_bridge: GraphThemeBridge | None) -> GraphThemeDefinition:
        return self._theme_resolver.active_graph_theme(graph_theme_bridge)

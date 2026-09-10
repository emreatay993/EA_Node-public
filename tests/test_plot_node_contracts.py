from __future__ import annotations

import inspect
import tempfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from ea_node_editor.addons.tabular_data.input_node import (
    TABULAR_DATA_ARRAY_OUTPUT_KEY,
    TABULAR_DATA_TABLE_OUTPUT_KEY,
    TABULAR_SELECTED_COLUMNS_PROPERTY,
    execute_tabular_input,
)
from ea_node_editor.addons.tabular_data.extraction_nodes import (
    TABULAR_ARRAY_SLICE_2D_OUTPUT_KEY,
    TABULAR_WINDOW_OUTPUT_KEY,
    execute_array_slice_2d,
    execute_table_filter,
)
from ea_node_editor.execution.plot_backend import (
    AUTO_PLOT_BACKEND_ID,
    GENERIC_PLOT_SERIES_RUNTIME_SHAPES,
    PlotRenderRequest,
    plot_render_request_from_payload,
    plot_render_request_to_payload,
)
from ea_node_editor.execution import plot_backend
from ea_node_editor.execution.plot_backend_matplotlib import MATPLOTLIB_PLOT_BACKEND_ID
from ea_node_editor.execution.plot_backend_pyqtgraph import PYQTGRAPH_PLOT_BACKEND_ID
from ea_node_editor.execution.plot_backend_pyvista import PYVISTA_PLOT_BACKEND_ID
from ea_node_editor.execution.runtime_snapshot import RuntimeSnapshot, RuntimeSnapshotContext
from ea_node_editor.graph.model import GraphModel
from ea_node_editor.nodes import output_artifacts
from ea_node_editor.nodes.bootstrap import build_default_registry
from ea_node_editor.nodes.builtins.plot import generic as generic_plot
from ea_node_editor.runtime_contracts import (
    ARRAY_DATA_REF_TYPE_ID,
    ARRAY_SLICE_2D_REF_TYPE_ID,
    DOUBLE_DATA_TYPE_ID,
    GRAPH_ARRAY_DATA_TYPE_ID,
    GRAPH_DICTIONARY_DATA_TYPE_ID,
    INTEGER_DATA_TYPE_ID,
    PATH_DATA_TYPE_ID,
    PLOT_EXPORT_BUNDLE_DATA_TYPE_ID,
    TABULAR_DATA_REF_TYPE_ID,
    TABULAR_WINDOW_REF_TYPE_ID,
)
from ea_node_editor.nodes.builtins.plot import PLOT_NODE_CATEGORY_PATH, PLOT_NODE_TYPE_IDS
from ea_node_editor.nodes.builtins.plot.generic import build_generic_plot_render_request
from ea_node_editor.nodes.execution_context import ExecutionContext
from ea_node_editor.runtime_contracts.value_refs import RuntimeArtifactRef
from ea_node_editor.persistence.artifact_resolution import ProjectArtifactResolver
from ea_node_editor.persistence.artifact_store import ProjectArtifactStore
from ea_node_editor.ui_qml.graph_scene_payload import GraphScenePayloadBuilder

EXPECTED_PLOT_TYPE_IDS = (
    "plot.scatter",
    "plot.bar",
    "plot.histogram",
    "plot.heatmap",
    "plot.contour",
    "plot.surface",
    "plot.point_cloud",
    "plot.streamlines",
)
EXPECTED_DISPLAY_NAMES = {
    "plot.scatter": "Scatter Plot",
    "plot.bar": "Bar Plot",
    "plot.histogram": "Histogram Plot",
    "plot.heatmap": "Heatmap Plot",
    "plot.contour": "Contour Plot",
    "plot.surface": "Surface Plot",
    "plot.point_cloud": "Point Cloud Plot",
    "plot.streamlines": "Streamlines Plot",
}
EXPECTED_GENERIC_PLOT_TYPE_IDS = EXPECTED_PLOT_TYPE_IDS
STANDARD_PROPERTY_KEYS = {
    "backend",
    "title",
    "x_label",
    "y_label",
    "z_label",
    "axis_limits",
    "log_scales",
    "grid",
    "legend",
    "render_in_canvas",
    "archive_export_on_run",
    "static_export_format",
    "data_export_format",
    "tabular_mapping",
    "plot_options",
}
COLORMAP_PLOT_TYPES = {
    "plot.heatmap",
    "plot.contour",
    "plot.surface",
    "plot.point_cloud",
    "plot.streamlines",
}


def _execution_context(
    *,
    inputs: dict[str, object] | None = None,
    properties: dict[str, object] | None = None,
    project_path: Path | None = None,
    runtime_snapshot: RuntimeSnapshot | None = None,
    runtime_snapshot_context: RuntimeSnapshotContext | None = None,
    path_resolver=None,  # noqa: ANN001
    node_type_id: str = "plot.scatter",
) -> ExecutionContext:
    return ExecutionContext(
        run_id="run_plot_contract",
        node_id="node_plot_line",
        workspace_id="ws_plot_contract",
        inputs=dict(inputs or {}),
        properties=dict(properties or {}),
        emit_log=lambda _level, _message: None,
        project_path=str(project_path) if project_path is not None else "",
        runtime_snapshot=runtime_snapshot,
        runtime_snapshot_context=runtime_snapshot_context,
        path_resolver=path_resolver or (lambda _value: None),
        node_type_id=node_type_id,
    )


class _PlotGraphThemeBridge:
    theme = "graph_stitch_dark"

    def __init__(self, *, lightweight_canvas: bool = False) -> None:
        self._parent = SimpleNamespace(graphics_lightweight_canvas=bool(lightweight_canvas))

    def parent(self) -> object:
        return self._parent


def _tabular_input_context(source: Path, **properties: object) -> ExecutionContext:
    payload = {"path": str(source), **properties}
    return ExecutionContext(
        run_id="run_tabular_for_plot",
        node_id="node_tabular_for_plot",
        workspace_id="ws_plot_contract",
        inputs={},
        properties=payload,
        emit_log=lambda _level, _message: None,
    )


def _plot_scene_payload(
    *,
    type_id: str = "plot.scatter",
    properties: dict[str, object] | None = None,
    lightweight_canvas: bool = False,
) -> dict[str, object]:
    model = GraphModel()
    registry = build_default_registry()
    workspace_id = model.active_workspace.workspace_id
    node = model.add_node(
        workspace_id,
        type_id,
        EXPECTED_DISPLAY_NAMES.get(type_id, "Plot"),
        64.0,
        96.0,
        properties=properties,
    )
    nodes_payload, _minimap_payload, _edges_payload = GraphScenePayloadBuilder().rebuild_models(
        model=model,
        registry=registry,
        workspace_id=workspace_id,
        scope_path=(),
        graph_theme_bridge=_PlotGraphThemeBridge(lightweight_canvas=lightweight_canvas),
        lightweight_canvas=lightweight_canvas,
    )
    return next(item for item in nodes_payload if item["node_id"] == node.node_id)


def _connected_tabular_plot_model(tmp_path: Path, *, filename: str = "weather.csv"):
    source = tmp_path / filename
    source.write_text("time,temp\n0,21.5\n1,22.0\n", encoding="utf-8")
    model = GraphModel()
    registry = build_default_registry()
    workspace_id = model.active_workspace.workspace_id
    tabular = model.add_node(
        workspace_id,
        "tabular.input",
        "Tabular",
        32.0,
        64.0,
        properties={"path": str(source)},
    )
    plot = model.add_node(
        workspace_id,
        "plot.scatter",
        "Scatter Plot",
        360.0,
        64.0,
        properties={"tabular_mapping": {"x": "time", "y": ["temp"]}},
    )
    edge = model.add_edge(workspace_id, tabular.node_id, "table_data", plot.node_id, "series")
    return source, model, registry, workspace_id, tabular, plot, edge


def _full_plot_payload(
    model: GraphModel,
    registry,
    workspace_id: str,
    plot_node_id: str,
) -> dict[str, object]:
    nodes_payload, _minimap_payload, _edges_payload = GraphScenePayloadBuilder().rebuild_models(
        model=model,
        registry=registry,
        workspace_id=workspace_id,
        scope_path=(),
        graph_theme_bridge=_PlotGraphThemeBridge(),
    )
    return next(item for item in nodes_payload if item["node_id"] == plot_node_id)


def _targeted_plot_payload(
    model: GraphModel,
    registry,
    workspace_id: str,
    plot_node_id: str,
    *,
    previous_payload: dict[str, object],
    changed_fields: set[str] | None,
) -> dict[str, object]:
    nodes_payload, _backdrop_nodes_payload, _minimap_payload = (
        GraphScenePayloadBuilder().build_node_payloads_for_ids(
            model=model,
            registry=registry,
            workspace_id=workspace_id,
            scope_path=(),
            node_ids={plot_node_id},
            graph_theme_bridge=_PlotGraphThemeBridge(),
            previous_payloads_by_id={plot_node_id: previous_payload},
            changed_fields_by_node_id=(
                {plot_node_id: changed_fields} if changed_fields is not None else None
            ),
        )
    )
    return next(item for item in nodes_payload if item["node_id"] == plot_node_id)


def _generic_render_request(
    *,
    type_id: str = "plot.scatter",
    series_input: object,
    properties: dict[str, object] | None = None,
) -> PlotRenderRequest:
    registry = build_default_registry()
    normalized_properties = registry.normalize_properties(type_id, properties or {})
    render_request, warnings = build_generic_plot_render_request(
        node_type_id=type_id,
        properties=normalized_properties,
        series_input=series_input,
    )
    assert warnings == ()
    assert isinstance(render_request, PlotRenderRequest)
    return render_request


def test_generic_plot_catalog_registers_v1_specs_through_builtin_bootstrap() -> None:
    registry = build_default_registry()
    scalar_series_profile = (
        DOUBLE_DATA_TYPE_ID,
        (
            INTEGER_DATA_TYPE_ID,
            GRAPH_ARRAY_DATA_TYPE_ID,
            GRAPH_DICTIONARY_DATA_TYPE_ID,
            ARRAY_DATA_REF_TYPE_ID,
            ARRAY_SLICE_2D_REF_TYPE_ID,
            TABULAR_DATA_REF_TYPE_ID,
            TABULAR_WINDOW_REF_TYPE_ID,
        ),
    )
    grid_series_profile = (
        GRAPH_ARRAY_DATA_TYPE_ID,
        (
            GRAPH_DICTIONARY_DATA_TYPE_ID,
            ARRAY_DATA_REF_TYPE_ID,
            ARRAY_SLICE_2D_REF_TYPE_ID,
            TABULAR_DATA_REF_TYPE_ID,
            TABULAR_WINDOW_REF_TYPE_ID,
        ),
    )
    point_series_profile = (
        GRAPH_DICTIONARY_DATA_TYPE_ID,
        (
            ARRAY_DATA_REF_TYPE_ID,
            ARRAY_SLICE_2D_REF_TYPE_ID,
            TABULAR_DATA_REF_TYPE_ID,
            TABULAR_WINDOW_REF_TYPE_ID,
        ),
    )
    expected_series_profiles = {
        "plot.scatter": scalar_series_profile,
        "plot.bar": scalar_series_profile,
        "plot.histogram": scalar_series_profile,
        "plot.heatmap": grid_series_profile,
        "plot.contour": grid_series_profile,
        "plot.surface": grid_series_profile,
        "plot.point_cloud": point_series_profile,
        "plot.streamlines": point_series_profile,
    }

    assert PLOT_NODE_TYPE_IDS == EXPECTED_PLOT_TYPE_IDS
    for type_id in EXPECTED_GENERIC_PLOT_TYPE_IDS:
        spec = registry.get_spec(type_id)
        assert spec.type_id == type_id
        assert spec.display_name == EXPECTED_DISPLAY_NAMES[type_id]
        assert spec.category_path == PLOT_NODE_CATEGORY_PATH
        assert spec.category_path == ("Plot",)
        assert spec.runtime_behavior == "active"
        assert spec.surface_family == "standard"
        for shape_name in GENERIC_PLOT_SERIES_RUNTIME_SHAPES:
            assert shape_name in spec.description

        series_port = next(port for port in spec.ports if port.key == "series")
        assert series_port.direction == "in"
        assert series_port.kind == "data"
        assert (
            series_port.data_type,
            series_port.accepted_data_types,
        ) == expected_series_profiles[type_id]
        assert series_port.required
        assert series_port.data_access == "list"
        assert not series_port.allow_multiple_connections
        for source_data_type in (
            series_port.data_type,
            *series_port.accepted_data_types,
        ):
            assert registry.data_types.compatibility(
                source_data_type,
                series_port.data_type,
                series_port.accepted_data_types,
            ).is_compatible
        assert not registry.data_types.compatibility(
            PATH_DATA_TYPE_ID,
            series_port.data_type,
            series_port.accepted_data_types,
        ).is_compatible

        ports = {port.key: port for port in spec.ports}
        assert "render_request" not in ports
        assert ports["static_export"].label == "Image Export"
        assert ports["exports"].data_type == PLOT_EXPORT_BUNDLE_DATA_TYPE_ID


def test_generic_plot_standard_properties_are_stable_and_colormap_is_scoped() -> None:
    registry = build_default_registry()

    for type_id in EXPECTED_GENERIC_PLOT_TYPE_IDS:
        spec = registry.get_spec(type_id)
        property_by_key = {prop.key: prop for prop in spec.properties}
        assert STANDARD_PROPERTY_KEYS.issubset(property_by_key)
        assert property_by_key["backend"].default == AUTO_PLOT_BACKEND_ID
        assert property_by_key["backend"].enum_values == (AUTO_PLOT_BACKEND_ID, MATPLOTLIB_PLOT_BACKEND_ID)
        assert property_by_key["axis_limits"].type == "json"
        assert property_by_key["log_scales"].type == "json"
        assert property_by_key["render_in_canvas"].default is True
        assert property_by_key["archive_export_on_run"].default is False
        assert property_by_key["static_export_format"].label == "Image Export Format"
        assert "frame_selector" not in property_by_key
        assert "animate" not in property_by_key
        assert ("colormap" in property_by_key) is (type_id in COLORMAP_PLOT_TYPES)


def test_generic_plot_scene_payload_reports_node_and_global_sink_mode() -> None:
    default_payload = _plot_scene_payload()
    disabled_payload = _plot_scene_payload(properties={"render_in_canvas": False})
    enabled_payload = _plot_scene_payload(properties={"render_in_canvas": True})
    lightweight_payload = _plot_scene_payload(
        properties={"render_in_canvas": True},
        lightweight_canvas=True,
    )

    assert default_payload["plot_surface"] == {
        "plot_type": "scatter",
        "live_backend_id": PYQTGRAPH_PLOT_BACKEND_ID,
        "render_in_canvas": True,
        "lightweight_canvas": False,
        "embedded_rendering_suppressed": False,
        "embedded_rendering_suppressed_by": [],
    }
    assert default_payload["embedded_rendering_suppressed"] is False
    assert disabled_payload["plot_surface"]["embedded_rendering_suppressed"] is True
    assert disabled_payload["plot_surface"]["embedded_rendering_suppressed_by"] == ["render_in_canvas"]
    assert enabled_payload["plot_surface"]["embedded_rendering_suppressed"] is False
    assert enabled_payload["embedded_rendering_suppressed_by"] == []
    assert lightweight_payload["plot_surface"]["embedded_rendering_suppressed"] is True
    assert lightweight_payload["plot_surface"]["embedded_rendering_suppressed_by"] == [
        "lightweight_canvas"
    ]


def test_generic_plot_scene_payload_reports_resolved_live_backend_id() -> None:
    line_payload = _plot_scene_payload(type_id="plot.scatter")
    surface_payload = _plot_scene_payload(type_id="plot.surface")
    matplotlib_payload = _plot_scene_payload(
        type_id="plot.scatter",
        properties={"backend": MATPLOTLIB_PLOT_BACKEND_ID},
    )

    assert line_payload["plot_surface"]["live_backend_id"] == PYQTGRAPH_PLOT_BACKEND_ID
    assert surface_payload["plot_surface"]["plot_type"] == "surface"
    assert surface_payload["plot_surface"]["live_backend_id"] == PYVISTA_PLOT_BACKEND_ID
    assert matplotlib_payload["plot_surface"]["live_backend_id"] == MATPLOTLIB_PLOT_BACKEND_ID


def test_generic_plot_scene_payload_projects_connected_tabular_auto_preview(tmp_path: Path) -> None:
    source = tmp_path / "weather.csv"
    source.write_text("time,temp\n0,21.5\n1,22.0\n", encoding="utf-8")
    model = GraphModel()
    registry = build_default_registry()
    workspace_id = model.active_workspace.workspace_id
    tabular = model.add_node(
        workspace_id,
        "tabular.input",
        "Tabular",
        32.0,
        64.0,
        properties={"path": str(source)},
    )
    plot = model.add_node(
        workspace_id,
        "plot.scatter",
        "Scatter Plot",
        360.0,
        64.0,
        properties={"tabular_mapping": {"x": "time", "y": ["temp"]}},
    )
    model.add_edge(workspace_id, tabular.node_id, "table_data", plot.node_id, "series")

    nodes_payload, _minimap_payload, _edges_payload = GraphScenePayloadBuilder().rebuild_models(
        model=model,
        registry=registry,
        workspace_id=workspace_id,
        scope_path=(),
        graph_theme_bridge=_PlotGraphThemeBridge(),
    )

    payload = next(item for item in nodes_payload if item["node_id"] == plot.node_id)
    plot_surface = payload["plot_surface"]
    assert plot_surface["auto_preview"] is True
    assert plot_surface["auto_preview_source_node_id"] == tabular.node_id
    # Scene payloads carry only the staleness signature; the render request is
    # built asynchronously and cached outside the payload.
    assert plot_surface["series_signature"]
    assert "render_request" not in plot_surface
    assert plot_surface["auto_preview_pending"] is True
    assert plot_surface["render_revision"] == 0

    from ea_node_editor.ui_qml.graph_scene_payload.kinds.plot import (
        _plot_series_source_descriptor,
    )
    from ea_node_editor.ui_qml.plot_auto_preview_service import (
        build_plot_render_request_payload,
        shared_plot_render_request_cache,
    )

    workspace = model.project.workspaces[workspace_id]
    descriptor = _plot_series_source_descriptor(
        node=workspace.nodes[plot.node_id],
        workspace=workspace,
        graph_theme_bridge=None,
    )
    request_payload, warnings = build_plot_render_request_payload(
        node_type_id="plot.scatter",
        properties={**workspace.nodes[plot.node_id].properties},
        source_descriptor=descriptor,
    )
    assert warnings == ()
    assert request_payload["plot_type"] == "scatter"
    series_payload = [
        {key: value for key, value in item.items() if key not in {"decimation", "source_ref"}}
        for item in request_payload["series"]
    ]
    assert series_payload == [
        {
            "label": "temp",
            "x": [0, 1],
            "y": [21.5, 22],
            "x_column": "time",
            "y_column": "temp",
        }
    ]

    shared_plot_render_request_cache().store(
        workspace_id,
        plot.node_id,
        signature=plot_surface["series_signature"],
        request_payload=request_payload,
    )
    nodes_payload, _minimap_payload, _edges_payload = GraphScenePayloadBuilder().rebuild_models(
        model=model,
        registry=registry,
        workspace_id=workspace_id,
        scope_path=(),
        graph_theme_bridge=_PlotGraphThemeBridge(),
    )
    refreshed = next(item for item in nodes_payload if item["node_id"] == plot.node_id)
    assert refreshed["plot_surface"]["auto_preview_active"] is True
    assert refreshed["plot_surface"]["render_revision"] > 0


def test_shared_plot_render_cache_clear_preserves_service_identity() -> None:
    from ea_node_editor.ui_qml.plot_auto_preview_service import (
        PlotAutoPreviewService,
        shared_plot_render_request_cache,
    )

    cache = shared_plot_render_request_cache()
    service = PlotAutoPreviewService(scene_bridge=None)
    try:
        assert service.cache is cache
        cache.store(
            "workspace-1",
            "plot-1",
            signature="signature-1",
            request_payload={"plot_type": "line", "series": []},
        )

        cache.clear()

        assert shared_plot_render_request_cache() is cache
        assert service.cache is cache
        assert cache.get("workspace-1", "plot-1") is None
    finally:
        service.shutdown()


def test_generic_plot_auto_preview_reuses_surface_for_node_title_rename(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from ea_node_editor.ui_qml.graph_scene_payload.kinds import plot as plot_payload_kind
    from ea_node_editor.ui_qml.plot_auto_preview_service import (
        reset_shared_plot_render_request_cache,
        shared_plot_render_request_cache,
    )

    reset_shared_plot_render_request_cache()
    _source, model, registry, workspace_id, _tabular, plot, _edge = _connected_tabular_plot_model(
        tmp_path
    )
    initial_payload = _full_plot_payload(model, registry, workspace_id, plot.node_id)
    initial_surface = initial_payload["plot_surface"]
    cache_entry = shared_plot_render_request_cache().store(
        workspace_id,
        plot.node_id,
        signature=initial_surface["series_signature"],
        request_payload={"plot_type": "line", "series": []},
    )
    active_payload = _full_plot_payload(model, registry, workspace_id, plot.node_id)
    active_surface = active_payload["plot_surface"]
    assert active_surface["render_revision"] == cache_entry.revision

    descriptor_calls = 0
    original_descriptor = plot_payload_kind._plot_series_source_descriptor

    def counting_descriptor(**kwargs):
        nonlocal descriptor_calls
        descriptor_calls += 1
        return original_descriptor(**kwargs)

    monkeypatch.setattr(plot_payload_kind, "_plot_series_source_descriptor", counting_descriptor)
    stable_payload = _targeted_plot_payload(
        model,
        registry,
        workspace_id,
        plot.node_id,
        previous_payload=active_payload,
        changed_fields=set(),
    )
    assert descriptor_calls == 1
    assert stable_payload["plot_surface"] == active_surface

    descriptor_calls = 0
    model.set_node_title(workspace_id, plot.node_id, "Renamed Plot Node")
    renamed_payload = _targeted_plot_payload(
        model,
        registry,
        workspace_id,
        plot.node_id,
        previous_payload=active_payload,
        changed_fields={"node.title"},
    )

    assert descriptor_calls == 0
    assert renamed_payload["title"] == "Renamed Plot Node"
    assert renamed_payload["plot_surface"] == active_surface
    assert renamed_payload["plot_surface"] is not active_surface


def test_generic_plot_auto_preview_recomputes_for_render_title_source_edge_and_file_stat(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from ea_node_editor.ui_qml.graph_scene_payload.kinds import plot as plot_payload_kind
    from ea_node_editor.ui_qml.plot_auto_preview_service import reset_shared_plot_render_request_cache

    reset_shared_plot_render_request_cache()
    _source, model, registry, workspace_id, _tabular, plot, edge = _connected_tabular_plot_model(
        tmp_path
    )
    initial_payload = _full_plot_payload(model, registry, workspace_id, plot.node_id)
    initial_signature = initial_payload["plot_surface"]["series_signature"]

    descriptor_calls = 0
    original_descriptor = plot_payload_kind._plot_series_source_descriptor

    def counting_descriptor(**kwargs):
        nonlocal descriptor_calls
        descriptor_calls += 1
        return original_descriptor(**kwargs)

    monkeypatch.setattr(plot_payload_kind, "_plot_series_source_descriptor", counting_descriptor)
    model.set_node_property(workspace_id, plot.node_id, "title", "Render Title")
    title_payload = _targeted_plot_payload(
        model,
        registry,
        workspace_id,
        plot.node_id,
        previous_payload=initial_payload,
        changed_fields={"properties.title"},
    )
    title_signature = title_payload["plot_surface"]["series_signature"]
    assert descriptor_calls == 1
    assert title_signature != initial_signature

    second_source = tmp_path / "weather_2.csv"
    second_source.write_text("time,temp\n0,18.0\n1,19.0\n", encoding="utf-8")
    second_tabular = model.add_node(
        workspace_id,
        "tabular.input",
        "Tabular 2",
        32.0,
        220.0,
        properties={"path": str(second_source)},
    )
    model.remove_edge(workspace_id, edge.edge_id)
    model.add_edge(workspace_id, second_tabular.node_id, "table_data", plot.node_id, "series")
    descriptor_calls = 0
    retargeted_payload = _targeted_plot_payload(
        model,
        registry,
        workspace_id,
        plot.node_id,
        previous_payload=title_payload,
        changed_fields=None,
    )
    retargeted_surface = retargeted_payload["plot_surface"]
    assert descriptor_calls == 1
    assert retargeted_surface["series_signature"] != title_signature
    assert retargeted_surface["auto_preview_source_node_id"] == second_tabular.node_id

    second_source.write_text("time,temp\n0,18.0\n1,19.0\n2,20.0\n", encoding="utf-8")
    descriptor_calls = 0
    file_changed_payload = _targeted_plot_payload(
        model,
        registry,
        workspace_id,
        plot.node_id,
        previous_payload=retargeted_payload,
        changed_fields=None,
    )
    assert descriptor_calls == 1
    assert file_changed_payload["plot_surface"]["series_signature"] != retargeted_surface["series_signature"]


def test_generic_plot_scene_payload_projects_connected_table_window_auto_preview(
    tmp_path: Path,
) -> None:
    source = tmp_path / "weather.csv"
    source.write_text("time,temp,pressure\n0,21.5,100.0\n1,22.0,101.5\n", encoding="utf-8")
    model = GraphModel()
    registry = build_default_registry()
    workspace_id = model.active_workspace.workspace_id
    tabular = model.add_node(
        workspace_id,
        "tabular.input",
        "Tabular",
        32.0,
        64.0,
        properties={"path": str(source)},
    )
    table_window = model.add_node(
        workspace_id,
        "tabular.table_filter",
        "Table Filter",
        220.0,
        64.0,
        properties={"columns": "time,temp", "row_limit": 0},
    )
    plot = model.add_node(
        workspace_id,
        "plot.scatter",
        "Scatter Plot",
        420.0,
        64.0,
        properties={"tabular_mapping": {"x": "time", "y": ["temp"]}},
    )
    model.add_edge(workspace_id, tabular.node_id, "table_data", table_window.node_id, "table_data")
    model.add_edge(workspace_id, table_window.node_id, "window", plot.node_id, "series")

    nodes_payload, _minimap_payload, _edges_payload = GraphScenePayloadBuilder().rebuild_models(
        model=model,
        registry=registry,
        workspace_id=workspace_id,
        scope_path=(),
        graph_theme_bridge=_PlotGraphThemeBridge(),
    )

    payload = next(item for item in nodes_payload if item["node_id"] == plot.node_id)
    plot_surface = payload["plot_surface"]
    assert plot_surface["auto_preview"] is True
    assert plot_surface["auto_preview_pending"] is True
    assert plot_surface["auto_preview_source_node_id"] == table_window.node_id
    assert plot_surface["series_signature"]
    assert "render_request" not in plot_surface

    from ea_node_editor.ui_qml.graph_scene_payload.kinds.plot import (
        _plot_series_source_descriptor,
    )
    from ea_node_editor.ui_qml.plot_auto_preview_service import (
        build_plot_render_request_payload,
    )

    workspace = model.project.workspaces[workspace_id]
    descriptor = _plot_series_source_descriptor(
        node=workspace.nodes[plot.node_id],
        workspace=workspace,
        graph_theme_bridge=None,
    )
    assert descriptor["kind"] == "table_filter"
    request_payload, _warnings = build_plot_render_request_payload(
        node_type_id="plot.scatter",
        properties={**workspace.nodes[plot.node_id].properties},
        source_descriptor=descriptor,
    )
    series_payload = [
        {key: value for key, value in item.items() if key not in {"decimation", "source_ref"}}
        for item in request_payload["series"]
    ]
    assert series_payload == [
        {
            "label": "temp",
            "x": [0, 1],
            "y": [21.5, 22],
            "x_column": "time",
            "y_column": "temp",
        }
    ]


def test_generic_plot_request_builder_handles_dict_of_arrays_without_numpy_dependency() -> None:
    registry = build_default_registry()
    plugin = registry.create("plot.scatter")
    properties = registry.normalize_properties(
        "plot.scatter",
        {
            "title": "Packet Line",
            "x_label": "time",
            "y_label": "value",
            "grid": False,
            "legend": True,
        },
    )

    result = plugin.execute(
        _execution_context(
            inputs={"series": {"label": "sample", "x": [0, 1, 2], "y": [1.0, 2.5, 4.0]}},
            properties=properties,
        )
    )

    assert result.outputs == {}
    render_request, warnings = build_generic_plot_render_request(
        node_type_id="plot.scatter",
        properties=properties,
        series_input={"label": "sample", "x": [0, 1, 2], "y": [1.0, 2.5, 4.0]},
    )
    assert warnings == ()
    assert render_request.plot_type == "scatter"
    assert render_request.title == "Packet Line"
    assert render_request.x_label == "time"
    assert render_request.y_label == "value"
    assert render_request.series == ({"label": "sample", "x": [0, 1, 2], "y": [1.0, 2.5, 4.0]},)
    assert render_request.options["grid"] is False
    assert "import numpy" not in inspect.getsource(plot_backend)


def test_generic_plot_request_preserves_live_investigation_options_when_present() -> None:
    render_request = _generic_render_request(
        series_input={"label": "sample", "x": [0, 1], "y": [1.0, 2.0]},
        properties={
            "plot_options": {
                "plot_theme": "dark",
                "hover_readout": True,
                "vertical_guide": True,
                "crosshair": False,
            }
        },
    )

    assert render_request.options["plot_theme"] == "dark"
    assert render_request.options["hover_readout"] is True
    assert render_request.options["vertical_guide"] is True
    assert render_request.options["crosshair"] is False

    legacy_request = _generic_render_request(
        series_input={"label": "sample", "x": [0, 1], "y": [1.0, 2.0]},
    )
    for option_key in ("plot_theme", "hover_readout", "vertical_guide", "crosshair"):
        assert option_key not in legacy_request.options


def test_plot_render_request_payload_helpers_are_json_safe() -> None:
    request = PlotRenderRequest(
        plot_type="line",
        series=({"label": "tuple", "x": (0, 1), "y": (2.0, 3.0)},),
        title="Tuple Series",
        x_label="x",
        y_label="y",
        options={"axis_limits": {"x": (None, 10)}, "markers": ("a", "b")},
    )

    payload = plot_render_request_to_payload(request)

    assert payload == {
        "plot_type": "line",
        "series": [{"label": "tuple", "x": [0, 1], "y": [2.0, 3.0]}],
        "title": "Tuple Series",
        "x_label": "x",
        "y_label": "y",
        "options": {"axis_limits": {"x": [None, 10]}, "markers": ["a", "b"]},
    }
    restored = plot_render_request_from_payload(payload)
    assert restored.series == ({"label": "tuple", "x": [0, 1], "y": [2.0, 3.0]},)
    assert restored.options["axis_limits"] == {"x": [None, 10]}


def _core_series(render_request) -> tuple[dict, ...]:
    """Series payloads minus the decimation/source bookkeeping keys."""
    stripped = []
    for item in render_request.series:
        clean = {key: value for key, value in item.items() if key not in {"decimation", "source_ref"}}
        stripped.append(clean)
    return tuple(stripped)


def test_generic_line_plot_materializes_selected_tabular_columns(tmp_path: Path) -> None:
    source = tmp_path / "weather.csv"
    source.write_text("time,temp,pressure\n0,21.5,100.0\n1,22.0,101.5\n", encoding="utf-8")
    tabular_result = execute_tabular_input(
        _tabular_input_context(source, **{TABULAR_SELECTED_COLUMNS_PROPERTY: ["time", "temp"]})
    )
    ref = tabular_result.outputs[TABULAR_DATA_TABLE_OUTPUT_KEY]

    render_request = _generic_render_request(series_input=ref)
    assert _core_series(render_request) == (
        {
            "label": "temp",
            "x": [0, 1],
            "y": [21.5, 22],
            "x_column": "time",
            "y_column": "temp",
        },
    )
    decimation = render_request.series[0]["decimation"]
    assert decimation == {"method": "none", "original_rows": 2, "points": 2}
    assert render_request.series[0]["source_ref"]["ref"]["ref_id"] == ref.ref_id


def test_generic_line_plot_materializes_table_window_ref(tmp_path: Path) -> None:
    source = tmp_path / "weather.csv"
    source.write_text(
        "Time_s,Accel_g,Pressure\n0,-2.0,100\n0.01,-1.4,101\n0.02,-1.8,102\n",
        encoding="utf-8",
    )
    table_ref = execute_tabular_input(
        _tabular_input_context(source)
    ).outputs[TABULAR_DATA_TABLE_OUTPUT_KEY]
    window_ref = execute_table_filter(
        _execution_context(
            inputs={"table_data": table_ref},
            properties={"row_offset": 1, "row_limit": 2, "columns": "Time_s, Accel_g"},
        )
    ).outputs[TABULAR_WINDOW_OUTPUT_KEY]

    render_request = _generic_render_request(series_input=window_ref)

    assert _core_series(render_request) == (
        {
            "label": "Accel_g",
            "x": [0.01, 0.02],
            "y": [-1.4, -1.8],
            "x_column": "Time_s",
            "y_column": "Accel_g",
        },
    )


def test_generic_histogram_plot_auto_ignores_text_columns(tmp_path: Path) -> None:
    source = tmp_path / "weather.csv"
    source.write_text("station,temp,pressure\nA,21.5,100.0\nB,22.0,101.5\n", encoding="utf-8")
    ref = execute_tabular_input(_tabular_input_context(source)).outputs[TABULAR_DATA_TABLE_OUTPUT_KEY]

    render_request = _generic_render_request(type_id="plot.histogram", series_input=ref)
    assert _core_series(render_request) == (
        {"label": "temp", "values": [21.5, 22], "value_column": "temp"},
        {"label": "pressure", "values": [100, 101.5], "value_column": "pressure"},
    )


def test_generic_scatter_plot_reports_unknown_tabular_mapping_column(tmp_path: Path) -> None:
    source = tmp_path / "weather.csv"
    source.write_text("time,temp\n0,21.5\n1,22.0\n", encoding="utf-8")
    ref = execute_tabular_input(_tabular_input_context(source)).outputs[TABULAR_DATA_TABLE_OUTPUT_KEY]
    registry = build_default_registry()
    plugin = registry.create("plot.scatter")
    properties = registry.normalize_properties(
        "plot.scatter",
        {"tabular_mapping": {"x": "time", "y": ["temperature"]}},
    )

    with pytest.raises(ValueError) as excinfo:
        plugin.execute(_execution_context(inputs={"series": ref}, properties=properties))

    message = str(excinfo.value)
    assert "tabular_mapping.y" in message
    assert "'temperature'" in message
    assert "Loaded columns: 'time', 'temp'." in message
    assert "Header Row" in message


def test_generic_scatter_plot_reports_generated_headers_when_header_row_is_disabled(
    tmp_path: Path,
) -> None:
    source = tmp_path / "weather.csv"
    source.write_text("time,temp\n0,21.5\n1,22.0\n", encoding="utf-8")
    ref = execute_tabular_input(
        _tabular_input_context(source, header_row=None)
    ).outputs[TABULAR_DATA_TABLE_OUTPUT_KEY]
    registry = build_default_registry()
    plugin = registry.create("plot.scatter")

    with pytest.raises(ValueError) as excinfo:
        plugin.execute(_execution_context(inputs={"series": ref}))

    message = str(excinfo.value)
    assert "needs numeric columns" in message
    assert "Loaded columns: 'column_1', 'column_2'." in message
    assert "Header Row" in message


def test_generic_scatter_plot_reports_empty_tabular_input(tmp_path: Path) -> None:
    source = tmp_path / "weather.csv"
    source.write_text("time,temp\n", encoding="utf-8")
    ref = execute_tabular_input(_tabular_input_context(source)).outputs[TABULAR_DATA_TABLE_OUTPUT_KEY]
    registry = build_default_registry()
    plugin = registry.create("plot.scatter")

    with pytest.raises(ValueError) as excinfo:
        plugin.execute(_execution_context(inputs={"series": ref}))

    message = str(excinfo.value)
    assert "has no data rows after parsing" in message
    assert "Loaded columns: 'time', 'temp'." in message
    assert "Skip Rows" in message


def test_generic_heatmap_plot_materializes_numeric_tabular_grid(tmp_path: Path) -> None:
    source = tmp_path / "grid.csv"
    source.write_text("a,b,c\n1,2,3\n4,5,6\n", encoding="utf-8")
    ref = execute_tabular_input(
        _tabular_input_context(source, **{TABULAR_SELECTED_COLUMNS_PROPERTY: ["a", "b", "c"]})
    ).outputs[TABULAR_DATA_TABLE_OUTPUT_KEY]

    render_request = _generic_render_request(type_id="plot.heatmap", series_input=ref)
    assert _core_series(render_request) == (
        {"label": "tabular grid", "values": [[1, 2, 3], [4, 5, 6]], "columns": ["a", "b", "c"]},
    )


def test_generic_point_cloud_plot_infers_named_xyz_tabular_columns(tmp_path: Path) -> None:
    source = tmp_path / "points.csv"
    source.write_text("name,x,y,z\np1,1,2,3\np2,4,5,6\n", encoding="utf-8")
    ref = execute_tabular_input(_tabular_input_context(source)).outputs[TABULAR_DATA_TABLE_OUTPUT_KEY]

    render_request = _generic_render_request(type_id="plot.point_cloud", series_input=ref)
    assert _core_series(render_request) == (
        {"label": "tabular point cloud", "points": [[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]], "columns": ["x", "y", "z"]},
    )


def test_generic_streamlines_plot_reports_missing_xyz_mapping(tmp_path: Path) -> None:
    source = tmp_path / "points.csv"
    source.write_text("x,y\n1,2\n3,4\n", encoding="utf-8")
    ref = execute_tabular_input(_tabular_input_context(source)).outputs[TABULAR_DATA_TABLE_OUTPUT_KEY]
    registry = build_default_registry()
    plugin = registry.create("plot.streamlines")

    with pytest.raises(ValueError, match="Streamline auto tabular plotting requires"):
        plugin.execute(_execution_context(inputs={"series": ref}))


def test_generic_scatter_plot_materializes_array_ref_slice(tmp_path: Path) -> None:
    numpy = pytest.importorskip("numpy")
    source = tmp_path / "points.npy"
    numpy.save(source, numpy.array([[1.0, 2.0], [3.0, 4.0]]))
    ref = execute_tabular_input(_tabular_input_context(source)).outputs[TABULAR_DATA_ARRAY_OUTPUT_KEY]

    render_request = _generic_render_request(type_id="plot.scatter", series_input=ref)
    assert _core_series(render_request) == (
        {"label": "array scatter", "x": [1.0, 3.0], "y": [2.0, 4.0]},
    )
    assert render_request.series[0]["decimation"] == {"method": "none", "original_rows": 2, "points": 2}
    assert render_request.series[0]["source_ref"]["kind"] == "array_ref"
    assert render_request.series[0]["source_ref"]["ref"]["ref_id"] == ref.ref_id


def test_generic_scatter_plot_materializes_array_slice_ref(tmp_path: Path) -> None:
    numpy = pytest.importorskip("numpy")
    source = tmp_path / "points.npy"
    numpy.save(source, numpy.array([[1.0, 2.0, 5.0], [3.0, 4.0, 6.0], [7.0, 8.0, 9.0]]))
    array_ref = execute_tabular_input(
        _tabular_input_context(source)
    ).outputs[TABULAR_DATA_ARRAY_OUTPUT_KEY]
    slice_ref = execute_array_slice_2d(
        _execution_context(
            inputs={"array_data": array_ref},
            properties={"row_limit": 2, "column_limit": 2},
        )
    ).outputs[TABULAR_ARRAY_SLICE_2D_OUTPUT_KEY]

    render_request = _generic_render_request(type_id="plot.scatter", series_input=slice_ref)

    assert _core_series(render_request) == (
        {"label": "array scatter", "x": [1.0, 3.0], "y": [2.0, 4.0]},
    )
    assert render_request.series[0]["decimation"] == {"method": "none", "original_rows": 2, "points": 2}
    assert render_request.series[0]["source_ref"]["kind"] == "array_slice_2d_ref"
    assert render_request.series[0]["source_ref"]["ref"]["ref_id"] == slice_ref.ref_id


def test_generic_plot_node_archive_export_writes_static_and_data_artifacts() -> None:
    registry = build_default_registry()
    plugin = registry.create("plot.scatter")

    with tempfile.TemporaryDirectory() as temp_dir:
        project_path = Path(temp_dir) / "plot_node_contracts.cxproj"
        runtime_snapshot = RuntimeSnapshot(schema_version=1, project_id="project_plot_contract", metadata={})
        artifact_store = ProjectArtifactStore.from_project_metadata(
            project_path=project_path,
            project_metadata=runtime_snapshot.metadata,
        )
        runtime_snapshot_context = RuntimeSnapshotContext.from_snapshot(
            runtime_snapshot,
            project_path=str(project_path),
            artifact_store=artifact_store,
        )
        resolver = ProjectArtifactResolver(project_path=project_path, artifact_store=artifact_store)
        properties = registry.normalize_properties(
            "plot.scatter",
            {
                "title": "Archived Line",
                "archive_export_on_run": True,
                "static_export_format": "png",
                "data_export_format": "csv",
            },
        )

        result = plugin.execute(
            _execution_context(
                inputs={"series": {"label": "sample", "values": [1.0, 2.5, 4.0]}},
                properties=properties,
                project_path=project_path,
                runtime_snapshot=runtime_snapshot,
                runtime_snapshot_context=runtime_snapshot_context,
                path_resolver=resolver.resolve_to_path,
            )
        )

        static_ref = result.outputs["static_export"]
        data_ref = result.outputs["data_export"]
        assert isinstance(static_ref, RuntimeArtifactRef)
        assert isinstance(data_ref, RuntimeArtifactRef)
        assert static_ref.data_type_id == PATH_DATA_TYPE_ID
        assert data_ref.data_type_id == PATH_DATA_TYPE_ID
        assert static_ref.schema_version == 1
        assert data_ref.schema_version == 1
        assert static_ref.format == "png"
        assert data_ref.format == "csv"
        assert static_ref.metadata == {}
        assert data_ref.metadata == {}
        static_path = resolver.resolve_to_path(static_ref.ref)
        data_path = resolver.resolve_to_path(data_ref.ref)
        assert static_path is not None
        assert data_path is not None
        assert static_path.read_bytes().startswith(b"\x89PNG")
        assert "sample" in data_path.read_text(encoding="utf-8")
        assert result.outputs["exports"]["static_metadata"]["backend_id"] == MATPLOTLIB_PLOT_BACKEND_ID
        assert result.outputs["exports"]["data_metadata"]["metadata"]["row_count"] == 3
        registry.data_types.validate_output(PLOT_EXPORT_BUNDLE_DATA_TYPE_ID, result.outputs["exports"])


def test_generic_plot_archive_second_registration_failure_rolls_back_pair(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = ProjectArtifactStore(project_path=None, metadata=None)
    root = store.ensure_staging_root(temporary_root_parent=tmp_path)
    root_hint = store.metadata["staging_root"]
    sentinel = root / "unrelated.keep"
    sentinel.write_text("keep", encoding="utf-8")
    snapshot_context = RuntimeSnapshotContext.from_snapshot(
        None,
        artifact_store=store,
    )
    resolver = ProjectArtifactResolver(project_path=None, artifact_store=store)
    ctx = _execution_context(
        runtime_snapshot_context=snapshot_context,
        path_resolver=resolver.resolve_to_path,
    )

    def export_result(request):  # noqa: ANN001
        request.output_path.write_bytes(request.format.encode("ascii"))
        return SimpleNamespace(
            backend_id="test",
            format=request.format,
            metadata={},
        )

    backend = SimpleNamespace(
        export_static=export_result,
        export_data=export_result,
    )
    monkeypatch.setattr(
        plot_backend,
        "create_plot_backend_registry",
        lambda: SimpleNamespace(resolve=lambda *_args, **_kwargs: backend),
    )
    plugin = build_default_registry().create("plot.scatter")
    request = PlotRenderRequest(
        plot_type="scatter",
        series=({"label": "sample", "x": [0, 1], "y": [1.0, 2.0]},),
    )
    properties = {
        "backend": "auto",
        "static_export_format": "png",
        "data_export_format": "csv",
    }
    seeded = plugin._archive_exports(ctx, request, properties)  # noqa: SLF001
    seeded_refs = (seeded["static_export"], seeded["data_export"])
    seeded_ids = tuple(ref.artifact_id for ref in seeded_refs)
    seeded_paths = tuple(store.resolve_staged_path(artifact_id) for artifact_id in seeded_ids)
    assert all(path is not None and path.is_file() for path in seeded_paths)
    seeded_entries = tuple(store.staged_entry(artifact_id) for artifact_id in seeded_ids)
    assert all(entry is not None for entry in seeded_entries)
    seeded_descriptors = tuple(
        entry.extra["runtime_artifact"]
        for entry in seeded_entries
        if entry is not None
    )

    unrelated_target = output_artifacts.allocate_managed_output(
        ctx,
        output_key="unrelated",
        default_suffix=".bin",
        managed_subdirectory="plots",
    )
    unrelated_target.path.write_bytes(b"unrelated bytes")
    unrelated_ref = output_artifacts.register_staged_path_artifact(
        ctx,
        store=store,
        artifact_id=unrelated_target.artifact_id,
        payload_path=unrelated_target.path,
        relative_path=unrelated_target.relative_path,
        slot=unrelated_target.slot,
        format=unrelated_target.format,
        entry_metadata=unrelated_target.entry_metadata,
    )
    unrelated_descriptor = store.staged_entry(unrelated_ref.artifact_id)
    assert unrelated_descriptor is not None
    unrelated_descriptor = unrelated_descriptor.extra["runtime_artifact"]

    real_register = generic_plot.register_staged_path_artifact
    attempted_ids: list[str] = []
    marker = RuntimeError("generic second registration marker")

    def fail_second_registration(context, **kwargs):  # noqa: ANN001
        runtime_ref = real_register(context, **kwargs)
        artifact_id = kwargs["artifact_id"]
        entry = store.staged_entry(artifact_id)
        assert entry is not None
        assert entry.extra["runtime_artifact"] == runtime_ref.to_descriptor()
        attempted_ids.append(artifact_id)
        if len(attempted_ids) == 2:
            raise marker
        return runtime_ref

    monkeypatch.setattr(
        generic_plot,
        "register_staged_path_artifact",
        fail_second_registration,
    )

    with pytest.raises(RuntimeError) as caught:
        plugin._archive_exports(ctx, request, properties)  # noqa: SLF001

    assert caught.value is marker
    assert tuple(attempted_ids) == seeded_ids
    assert all(store.staged_entry(artifact_id) is None for artifact_id in seeded_ids)
    assert all(path is not None and not path.exists() for path in seeded_paths)
    remaining_staged = store.metadata.get("staged", {})
    assert set(remaining_staged) == {unrelated_ref.artifact_id}
    remaining_descriptors = tuple(
        entry["runtime_artifact"]
        for entry in remaining_staged.values()
    )
    assert all(descriptor not in remaining_descriptors for descriptor in seeded_descriptors)
    assert store.staged_entry(unrelated_ref.artifact_id).extra["runtime_artifact"] == unrelated_descriptor
    assert unrelated_target.path.read_bytes() == b"unrelated bytes"
    assert store.active_staging_root() == root
    assert store.metadata["staging_root"] == root_hint
    assert sentinel.read_text(encoding="utf-8") == "keep"

    monkeypatch.setattr(
        generic_plot,
        "register_staged_path_artifact",
        real_register,
    )
    strict_seeded = plugin._archive_exports(ctx, request, properties)  # noqa: SLF001
    strict_ids = (
        strict_seeded["static_export"].artifact_id,
        strict_seeded["data_export"].artifact_id,
    )
    strict_paths = tuple(store.resolve_staged_path(artifact_id) for artifact_id in strict_ids)
    assert all(path is not None and path.is_file() for path in strict_paths)

    strict_marker = RuntimeError("generic strict cleanup marker")
    strict_attempted_ids: list[str] = []
    strict_relative_paths: list[str] = []
    discard_entry_calls: list[tuple[str, ...]] = []
    discard_path_calls: list[tuple[str, ...]] = []
    raw_unlink_calls: list[Path] = []
    real_discard_paths = store.discard_staged_paths
    cleanup_patch = pytest.MonkeyPatch()

    def reject_registered_entries(artifact_ids):  # noqa: ANN001
        discard_entry_calls.append(tuple(artifact_ids))
        raise ValueError("strict entry cleanup rejection")

    def strict_discard_paths(relative_paths):  # noqa: ANN001
        requested = tuple(relative_paths)
        discard_path_calls.append(requested)
        return real_discard_paths(requested)

    def reject_raw_unlink(path, *_args, **_kwargs):  # noqa: ANN001
        raw_unlink_calls.append(Path(path))
        raise AssertionError("raw unlink bypassed store validation")

    def fail_after_strict_registration(context, **kwargs):  # noqa: ANN001
        runtime_ref = real_register(context, **kwargs)
        artifact_id = kwargs["artifact_id"]
        entry = store.staged_entry(artifact_id)
        assert entry is not None
        assert entry.extra["runtime_artifact"] == runtime_ref.to_descriptor()
        strict_attempted_ids.append(artifact_id)
        strict_relative_paths.append(kwargs["relative_path"])
        if len(strict_attempted_ids) == 2:
            cleanup_patch.setattr(
                store,
                "discard_staged_entries",
                reject_registered_entries,
            )
            cleanup_patch.setattr(
                store,
                "discard_staged_paths",
                strict_discard_paths,
            )
            cleanup_patch.setattr(Path, "unlink", reject_raw_unlink)
            raise strict_marker
        return runtime_ref

    monkeypatch.setattr(
        generic_plot,
        "register_staged_path_artifact",
        fail_after_strict_registration,
    )
    try:
        with pytest.raises(RuntimeError) as strict_caught:
            plugin._archive_exports(ctx, request, properties)  # noqa: SLF001
    finally:
        cleanup_patch.undo()

    assert strict_caught.value is strict_marker
    assert tuple(strict_attempted_ids) == strict_ids
    assert discard_entry_calls == [strict_ids]
    assert discard_path_calls == [tuple(strict_relative_paths)]
    assert raw_unlink_calls == []
    assert all(store.staged_entry(artifact_id) is not None for artifact_id in strict_ids)
    assert all(path is not None and path.is_file() for path in strict_paths)
    assert set(store.metadata.get("staged", {})) == {
        *strict_ids,
        unrelated_ref.artifact_id,
    }
    assert unrelated_target.path.read_bytes() == b"unrelated bytes"
    assert store.active_staging_root() == root
    assert store.metadata["staging_root"] == root_hint
    assert sentinel.read_text(encoding="utf-8") == "keep"


def test_tabular_plot_archive_export_streams_all_source_columns(tmp_path: Path) -> None:
    registry = build_default_registry()
    plugin = registry.create("plot.scatter")
    project_path = tmp_path / "plot_full_source_export.cxproj"
    source = tmp_path / "weather.csv"
    rows = ["time,temp,pressure"]
    rows.extend(f"{index},{20.0 + index * 0.01:.2f},{100.0 + index * 0.1:.1f}" for index in range(4500))
    source.write_text("\n".join(rows) + "\n", encoding="utf-8")
    runtime_snapshot = RuntimeSnapshot(schema_version=1, project_id="project_plot_contract", metadata={})
    artifact_store = ProjectArtifactStore.from_project_metadata(
        project_path=project_path,
        project_metadata=runtime_snapshot.metadata,
    )
    runtime_snapshot_context = RuntimeSnapshotContext.from_snapshot(
        runtime_snapshot,
        project_path=str(project_path),
        artifact_store=artifact_store,
    )
    resolver = ProjectArtifactResolver(project_path=project_path, artifact_store=artifact_store)
    table_ref = execute_tabular_input(
        _tabular_input_context(source)
    ).outputs[TABULAR_DATA_TABLE_OUTPUT_KEY]
    properties = registry.normalize_properties(
        "plot.scatter",
        {
            "archive_export_on_run": True,
            "data_export_format": "csv",
            "tabular_mapping": {"x": "time", "y": ["temp"]},
        },
    )

    result = plugin.execute(
        _execution_context(
            inputs={"series": table_ref},
            properties=properties,
            project_path=project_path,
            runtime_snapshot=runtime_snapshot,
            runtime_snapshot_context=runtime_snapshot_context,
            path_resolver=resolver.resolve_to_path,
        )
    )

    data_path = resolver.resolve_to_path(result.outputs["data_export"].ref)
    assert data_path is not None
    exported_lines = data_path.read_text(encoding="utf-8").splitlines()
    assert exported_lines[0] == '"time","temp","pressure"'
    assert len(exported_lines) == 4501
    metadata = result.outputs["exports"]["data_metadata"]
    assert metadata["backend_id"] == "tabular_full_fidelity"
    assert metadata["metadata"]["row_count"] == 4500
    assert metadata["metadata"]["column_count"] == 3
    assert metadata["metadata"]["columns"] == ["time", "temp", "pressure"]


def test_array_plot_archive_export_streams_all_source_rows(tmp_path: Path) -> None:
    numpy = pytest.importorskip("numpy")
    registry = build_default_registry()
    plugin = registry.create("plot.scatter")
    project_path = tmp_path / "plot_array_full_source_export.cxproj"
    source = tmp_path / "points.npy"
    numpy.save(source, numpy.array([[float(index), float(index * 2)] for index in range(4500)]))
    runtime_snapshot = RuntimeSnapshot(schema_version=1, project_id="project_plot_contract", metadata={})
    artifact_store = ProjectArtifactStore.from_project_metadata(
        project_path=project_path,
        project_metadata=runtime_snapshot.metadata,
    )
    runtime_snapshot_context = RuntimeSnapshotContext.from_snapshot(
        runtime_snapshot,
        project_path=str(project_path),
        artifact_store=artifact_store,
    )
    resolver = ProjectArtifactResolver(project_path=project_path, artifact_store=artifact_store)
    array_ref = execute_tabular_input(
        _tabular_input_context(source, array_slice_2d={"row_limit": 4500, "column_limit": 2})
    ).outputs[TABULAR_DATA_ARRAY_OUTPUT_KEY]
    properties = registry.normalize_properties(
        "plot.scatter",
        {
            "archive_export_on_run": True,
            "data_export_format": "csv",
        },
    )

    result = plugin.execute(
        _execution_context(
            inputs={"series": array_ref},
            properties=properties,
            project_path=project_path,
            runtime_snapshot=runtime_snapshot,
            runtime_snapshot_context=runtime_snapshot_context,
            path_resolver=resolver.resolve_to_path,
            node_type_id="plot.scatter",
        )
    )

    data_path = resolver.resolve_to_path(result.outputs["data_export"].ref)
    assert data_path is not None
    exported_lines = data_path.read_text(encoding="utf-8").splitlines()
    assert exported_lines[0] == "column_1,column_2"
    assert len(exported_lines) == 4501
    metadata = result.outputs["exports"]["data_metadata"]
    assert metadata["backend_id"] == "array_full_fidelity"
    assert metadata["metadata"]["row_count"] == 4500
    assert metadata["metadata"]["column_count"] == 2

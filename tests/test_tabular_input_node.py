from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from ea_node_editor.addons import catalog as addon_catalog
from ea_node_editor.addons.property_edit_adapters import PropertyEditAdapterContext
from ea_node_editor.addons.tabular_data import catalog as tabular_catalog
from ea_node_editor.addons.tabular_data.function_nodes import SOURCE as TABULAR_FUNCTION_SOURCE
from ea_node_editor.addons.tabular_data.input_node import (
    TABULAR_ARRAY_SLICE_2D_PROPERTY,
    TABULAR_DATA_INPUT_CACHE_POLICY_APP_MANAGED_PARQUET,
    TABULAR_DATA_INPUT_DISPLAY_NAME,
    TABULAR_DATA_INPUT_ERROR_LARGE_DATA_GATED,
    TABULAR_DATA_INPUT_ERROR_MISSING_BACKEND,
    TABULAR_DATA_INPUT_ERROR_SELECTOR_REQUIRED,
    TABULAR_DATA_INPUT_NODE_TYPE_ID,
    TABULAR_SELECTED_COLUMNS_PROPERTY,
    TABULAR_TABLE_VIEW_STATE_MAX_COLUMN_WIDTH,
    TABULAR_TABLE_VIEW_STATE_MIN_COLUMN_WIDTH,
    TABULAR_TABLE_VIEW_STATE_PROPERTY,
    execute_tabular_input,
    normalize_tabular_table_view_state,
    normalize_tabular_selected_columns,
    tabular_array_column_label_from_offset,
    tabular_array_slice_2d_summary,
    tabular_load_options_from_node_properties,
)
from ea_node_editor.addons.tabular_data.property_edit_adapter import create_tabular_property_edit_adapters
from ea_node_editor.addons.tabular_data.loader_cache_service import (
    LargeDataMaterializationError,
    MissingTabularDependencyError,
    SelectionRequiredError,
    SourceStats,
    TabularLoaderCacheService,
)
from ea_node_editor.addons.tabular_data.policy import WARNING_LARGE_SOURCE
from ea_node_editor.app_preferences import default_app_preferences_document
from ea_node_editor.graph.model import GraphModel
from ea_node_editor.nodes.bootstrap import build_default_registry
from ea_node_editor.nodes.execution_context import ExecutionContext
from ea_node_editor.nodes.function_plugin import INTERNAL_BUILTIN_FUNCTION_OWNER_ID
from ea_node_editor.nodes.node_specs import property_visible_in_inspector
from ea_node_editor.nodes.plugin_declaration import discover_plugin_declarations
from ea_node_editor.persistence.serializer import JsonProjectSerializer
from ea_node_editor.runtime_contracts import ArrayDataRef, TabularDataRef
from ea_node_editor.ui.shell.controllers.workspace_edit_controller import (
    WorkspaceEditController,
)


def _context(
    *,
    inputs: dict | None = None,
    properties: dict | None = None,
) -> ExecutionContext:
    return ExecutionContext(
        run_id="run_tabular_input",
        node_id="node_tabular_input",
        workspace_id="ws_tabular_input",
        inputs=dict(inputs or {}),
        properties=dict(properties or {}),
        emit_log=lambda _level, _message: None,
        trigger={},
    )


def _spec():
    declarations = discover_plugin_declarations(
        TABULAR_FUNCTION_SOURCE,
        allow_reserved_ids=True,
        owner_id=INTERNAL_BUILTIN_FUNCTION_OWNER_ID,
    )
    return next(
        declaration.spec
        for declaration in declarations
        if declaration.spec.type_id == TABULAR_DATA_INPUT_NODE_TYPE_ID
    )


def test_tabular_data_input_descriptor_publishes_one_ref_only_source_node() -> None:
    spec = _spec()

    assert spec.type_id == TABULAR_DATA_INPUT_NODE_TYPE_ID
    assert spec.display_name == TABULAR_DATA_INPUT_DISPLAY_NAME
    assert spec.category_path == ("Data",)
    assert spec.icon == "integrations/tabular_data.svg"
    assert spec.runtime_behavior == "active"
    assert spec.settings_groups == ()

    ports_by_key = {port.key: port for port in spec.ports}
    assert tuple(ports_by_key) == ("path", "table_data", "array_data")
    assert ports_by_key["path"].direction == "in"
    assert ports_by_key["path"].data_type == "COREX.DataTypes.Path"
    assert ports_by_key["path"].required is True
    assert ports_by_key["path"].uses_property_default is True
    assert ports_by_key["table_data"].data_type == "COREX.Runtime.TabularDataRef"
    assert ports_by_key["array_data"].data_type == "COREX.Runtime.ArrayDataRef"
    assert {"rows", "pandas", "polars", "numpy"}.isdisjoint(ports_by_key)

    properties_by_key = {prop.key: prop for prop in spec.properties}
    assert properties_by_key["path"].type == "path"
    assert properties_by_key["path"].inline_editor == ""
    assert properties_by_key["path"].inspector_editor == "path"
    assert properties_by_key["selected_object"].default == ""
    assert properties_by_key["cache_policy"].default == TABULAR_DATA_INPUT_CACHE_POLICY_APP_MANAGED_PARQUET
    assert properties_by_key["project_managed_source"].default is False
    assert properties_by_key["project_managed_cache"].default is False
    assert properties_by_key[TABULAR_SELECTED_COLUMNS_PROPERTY].default == []
    assert not property_visible_in_inspector(properties_by_key[TABULAR_SELECTED_COLUMNS_PROPERTY])
    assert properties_by_key[TABULAR_TABLE_VIEW_STATE_PROPERTY].default == {}
    assert not property_visible_in_inspector(properties_by_key[TABULAR_TABLE_VIEW_STATE_PROPERTY])
    assert not property_visible_in_inspector(properties_by_key[TABULAR_ARRAY_SLICE_2D_PROPERTY])
    assert properties_by_key[TABULAR_ARRAY_SLICE_2D_PROPERTY].default == {
        "row_offset": 0,
        "column_offset": 0,
        "row_limit": 50,
        "column_limit": 50,
    }


def test_tabular_data_input_function_entry_has_isolated_mutable_defaults() -> None:
    registry = build_default_registry()
    assert registry.get_spec(TABULAR_DATA_INPUT_NODE_TYPE_ID).display_name == TABULAR_DATA_INPUT_DISPLAY_NAME
    first_defaults = registry.default_properties(TABULAR_DATA_INPUT_NODE_TYPE_ID)
    second_defaults = registry.default_properties(TABULAR_DATA_INPUT_NODE_TYPE_ID)
    first_defaults["schema_hints"]["temperature"] = "float64"
    first_defaults["array_slice_2d"]["row_limit"] = 10
    first_defaults[TABULAR_SELECTED_COLUMNS_PROPERTY].append("temperature")
    first_defaults[TABULAR_TABLE_VIEW_STATE_PROPERTY]["column_widths"] = {"table:station": 120}
    assert second_defaults["schema_hints"] == {}
    assert second_defaults["array_slice_2d"]["row_limit"] == 50
    assert second_defaults[TABULAR_SELECTED_COLUMNS_PROPERTY] == []
    assert second_defaults[TABULAR_TABLE_VIEW_STATE_PROPERTY] == {}


def test_tabular_load_options_round_trip_semantic_node_properties() -> None:
    options = tabular_load_options_from_node_properties(
        {
            "delimiter": "|",
            "encoding": "cp1252",
            "header_row": None,
            "skip_rows": "2",
            "schema_hints": {"count": "int64"},
            "selected_object": "Sheet 2",
            "allow_npz_archive_preview": True,
            TABULAR_TABLE_VIEW_STATE_PROPERTY: {
                "version": 1,
                "column_widths": {"table:count": 140},
            },
        }
    )

    assert options.delimiter == "|"
    assert options.encoding == "cp1252"
    assert options.header_row is None
    assert options.skip_rows == 2
    assert options.schema_hints == {"count": "int64"}
    assert options.selected_object == "Sheet 2"
    assert options.allow_npz_archive_preview is True


def test_normalize_tabular_table_view_state_clamps_column_widths() -> None:
    assert normalize_tabular_table_view_state(
        {
            "version": 99,
            "column_widths": {
                "table:station": 128.4,
                "array:3": 9999,
                "too_small": 1,
                "bad": "wide",
                "": 120,
            },
        }
    ) == {
        "version": 1,
        "column_widths": {
            "table:station": 128,
            "array:3": TABULAR_TABLE_VIEW_STATE_MAX_COLUMN_WIDTH,
            "too_small": TABULAR_TABLE_VIEW_STATE_MIN_COLUMN_WIDTH,
        },
    }


def test_normalize_tabular_selected_columns_deduplicates_non_empty_names() -> None:
    assert normalize_tabular_selected_columns(["temp", " pressure ", "", "temp", None]) == [
        "temp",
        "pressure",
    ]
    assert normalize_tabular_selected_columns("time") == ["time"]


def test_tabular_property_edit_adapter_rewrites_friendly_selection_fields_to_stored_slice() -> None:
    [adapter] = create_tabular_property_edit_adapters()
    node = SimpleNamespace(
        type_id=TABULAR_DATA_INPUT_NODE_TYPE_ID,
        properties={
            TABULAR_ARRAY_SLICE_2D_PROPERTY: {
                "row_offset": 0,
                "column_offset": 0,
                "row_limit": 50,
                "column_limit": 50,
            },
        },
    )
    context = PropertyEditAdapterContext(node=node)

    rewrite = adapter.rewrite_property_edit(context, key="array_slice_2d_row_start", value="3")
    assert rewrite is not None
    assert rewrite.key == TABULAR_ARRAY_SLICE_2D_PROPERTY
    assert rewrite.value == {"row_offset": 2, "column_offset": 0, "row_limit": 50, "column_limit": 50}
    node.properties[TABULAR_ARRAY_SLICE_2D_PROPERTY] = rewrite.value

    rewrite = adapter.rewrite_property_edit(context, key="array_slice_2d_column_start", value="AA")
    assert rewrite is not None
    assert rewrite.value == {"row_offset": 2, "column_offset": 26, "row_limit": 50, "column_limit": 50}
    node.properties[TABULAR_ARRAY_SLICE_2D_PROPERTY] = rewrite.value

    rewrite = adapter.rewrite_property_edit(context, key="array_slice_2d_row_count", value="8")
    assert rewrite is not None
    assert rewrite.value == {"row_offset": 2, "column_offset": 26, "row_limit": 8, "column_limit": 50}
    node.properties[TABULAR_ARRAY_SLICE_2D_PROPERTY] = rewrite.value

    rewrite = adapter.rewrite_property_edit(context, key="array_slice_2d_column_count", value="4")
    assert rewrite is not None
    assert rewrite.value == {"row_offset": 2, "column_offset": 26, "row_limit": 8, "column_limit": 4}
    assert tabular_array_column_label_from_offset(27) == "AB"
    assert tabular_array_slice_2d_summary(rewrite.value) == "Rows 3-10, Columns AA-AD"


def test_selected_property_edit_uses_tabular_adapter_for_array_slice_fields() -> None:
    spec = _spec()
    node = SimpleNamespace(
        node_id="node-tabular-input",
        type_id=TABULAR_DATA_INPUT_NODE_TYPE_ID,
        properties={
            TABULAR_ARRAY_SLICE_2D_PROPERTY: {
                "row_offset": 0,
                "column_offset": 0,
                "row_limit": 50,
                "column_limit": 50,
            },
        },
    )
    changed: list[tuple[str, str, object]] = []

    class _Controller:
        def selected_node_context(self):
            return node, spec

        def active_workspace(self):
            return SimpleNamespace(nodes={node.node_id: node}, edges={})

    host = SimpleNamespace(
        project_path="",
        model=SimpleNamespace(project=SimpleNamespace(metadata={})),
        app_preferences_controller=SimpleNamespace(document=default_app_preferences_document),
        scene=SimpleNamespace(
            set_node_property=lambda node_id, key, value: changed.append(
                (node_id, key, value)
            )
        ),
    )

    WorkspaceEditController(
        host,  # type: ignore[arg-type]
        selection_context=_Controller(),  # type: ignore[arg-type]
        effects=SimpleNamespace(
            after_selected_node_property_changed=lambda *_args, **_kwargs: None
        ),  # type: ignore[arg-type]
    ).set_selected_node_property("array_slice_2d_column_start", "C")

    assert changed == [
        (
            "node-tabular-input",
            TABULAR_ARRAY_SLICE_2D_PROPERTY,
            {"row_offset": 0, "column_offset": 2, "row_limit": 50, "column_limit": 50},
        )
    ]


def test_tabular_data_input_executes_csv_as_table_data_only(tmp_path: Path) -> None:
    source = tmp_path / "weather.csv"
    source.write_text("station,temp\nA,21.5\nB,22.0\n", encoding="utf-8")

    result = execute_tabular_input(_context(properties={"path": str(source)}))

    assert result.warnings == ()
    assert "exec_out" not in result.outputs
    assert "array_data" not in result.outputs
    ref = result.outputs["table_data"]
    assert isinstance(ref, TabularDataRef)
    assert ref.resolver_id == "tabular.cache"
    assert ref.backend_id == "python_text_stream"
    assert ref.object_id == "table"
    # Row counts backfill from the managed parquet cache after the first
    # read; open never scans the source.
    assert ref.row_count is None
    assert ref.column_count == 2
    assert ref.metadata["format_id"] == "csv"
    assert ref.metadata["load_options"]["selected_object"] == "table"
    assert ref.metadata["node_options"]["cache_policy"] == TABULAR_DATA_INPUT_CACHE_POLICY_APP_MANAGED_PARQUET
    assert ref.metadata["node_options"]["selected_columns"] == []
    assert "cache_path" not in ref.metadata["node_options"]
    assert ref.metadata["column_schema"] == [{"name": "station", "dtype": ""}, {"name": "temp", "dtype": ""}]


def test_column_schema_omitted_when_final_input_metadata_would_exceed_budget(tmp_path: Path) -> None:
    from ea_node_editor.addons.tabular_data.loader_cache_service import TabularLoaderCacheService
    name = "n" * 33_000
    source = tmp_path / "wide.csv"
    source.write_text(name + "\n1\n", encoding="utf-8")
    service = TabularLoaderCacheService(cache_dir=tmp_path / "cache")
    assert "column_schema" in service.open_source(source).metadata
    result = execute_tabular_input(_context(properties={"path": str(source), TABULAR_SELECTED_COLUMNS_PROPERTY: [name]}))
    metadata = result.outputs["table_data"].metadata
    assert "column_schema" not in metadata
    assert metadata["node_options"]["selected_columns"] == [name]
    source = tmp_path / "wider.csv"
    source.write_text("n" * 66_000 + "\n1\n", encoding="utf-8")
    metadata = service.open_source(source).metadata
    assert "column_schema" not in metadata
    assert metadata["format_id"] == "csv"


def test_tabular_data_input_embeds_selected_columns_in_ref_metadata(tmp_path: Path) -> None:
    source = tmp_path / "weather.csv"
    source.write_text("station,temp,pressure\nA,21.5,100.0\nB,22.0,101.0\n", encoding="utf-8")

    result = execute_tabular_input(
        _context(
            properties={
                "path": str(source),
                TABULAR_SELECTED_COLUMNS_PROPERTY: ["station", "temp", "station"],
            }
        )
    )

    ref = result.outputs["table_data"]
    assert isinstance(ref, TabularDataRef)
    assert ref.metadata["node_options"]["selected_columns"] == ["station", "temp"]


def test_tabular_data_input_executes_npy_as_array_data_only(tmp_path: Path) -> None:
    numpy = pytest.importorskip("numpy")
    source = tmp_path / "array.npy"
    numpy.save(source, numpy.arange(6).reshape(3, 2))

    result = execute_tabular_input(_context(properties={"path": str(source)}))

    assert "exec_out" not in result.outputs
    assert "table_data" not in result.outputs
    ref = result.outputs["array_data"]
    assert isinstance(ref, ArrayDataRef)
    assert ref.backend_id == "npy_mmap"
    assert ref.shape == (3, 2)
    assert ref.metadata["format_id"] == "npy"


def test_tabular_data_input_requires_persisted_selection_for_multi_object_npz(tmp_path: Path) -> None:
    numpy = pytest.importorskip("numpy")
    source = tmp_path / "archive.npz"
    numpy.savez(source, first=numpy.arange(4).reshape(2, 2), second=numpy.arange(6).reshape(3, 2))
    execute = execute_tabular_input

    with pytest.raises(SelectionRequiredError) as exc_info:
        execute(_context(properties={"path": str(source)}))

    assert exc_info.value.structured_error["code"] == TABULAR_DATA_INPUT_ERROR_SELECTOR_REQUIRED
    assert [choice["object_id"] for choice in exc_info.value.structured_error["choices"]] == ["first", "second"]

    result = execute(_context(properties={"path": str(source), "selected_object": "second"}))
    ref = result.outputs["array_data"]
    assert isinstance(ref, ArrayDataRef)
    assert ref.object_id == "second"
    assert ref.shape == (3, 2)


def test_tabular_data_input_reports_missing_backend_as_structured_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "table.parquet"
    source.write_bytes(b"not parquet")

    class _MissingBackendService:
        def open_source(self, _source_path, _options):  # noqa: ANN001
            raise MissingTabularDependencyError(
                format_id="parquet",
                dependency="pyarrow",
                purpose="Parquet schema",
            )

    monkeypatch.setattr(
        "ea_node_editor.addons.tabular_data.input_node.shared_tabular_loader_cache_service",
        _MissingBackendService,
    )

    with pytest.raises(MissingTabularDependencyError) as exc_info:
        execute_tabular_input(_context(properties={"path": str(source)}))

    assert exc_info.value.structured_error["code"] == TABULAR_DATA_INPUT_ERROR_MISSING_BACKEND
    assert exc_info.value.structured_error["format_id"] == "parquet"
    assert exc_info.value.structured_error["dependency"] == "pyarrow"
    assert exc_info.value.structured_error["recoverable"] is True


def test_tabular_data_input_promotes_large_source_warnings_to_ref_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "large.csv"
    source.write_text("station,temp\nA,21.5\n", encoding="utf-8")

    class _LargeCsvService(TabularLoaderCacheService):
        def __init__(self) -> None:
            super().__init__(cache_dir=tmp_path / "cache")

        def _source_stats(self, _path: Path) -> SourceStats:
            return SourceStats(size_bytes=2 * 1024 * 1024 * 1024, mtime_ns=1)

    monkeypatch.setattr(
        "ea_node_editor.addons.tabular_data.input_node.shared_tabular_loader_cache_service",
        _LargeCsvService,
    )

    result = execute_tabular_input(_context(properties={"path": str(source)}))
    ref = result.outputs["table_data"]

    assert result.warnings == (WARNING_LARGE_SOURCE,)
    assert ref.metadata["warnings"] == [WARNING_LARGE_SOURCE]
    assert ref.metadata["warning_facts"][0]["code"] == WARNING_LARGE_SOURCE
    assert ref.metadata["warning_facts"][0]["severity"] == "warning"
    assert ref.metadata["warning_facts"][0]["source_name"] == "large.csv"
    assert "source_path" not in ref.metadata["warning_facts"][0]


def test_tabular_data_input_reports_large_npz_preview_gate_as_structured_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    numpy = pytest.importorskip("numpy")
    source = tmp_path / "archive.npz"
    numpy.savez(source, array=numpy.arange(4).reshape(2, 2))

    class _LargeNpzService(TabularLoaderCacheService):
        def __init__(self) -> None:
            super().__init__(cache_dir=tmp_path / "cache")

        def _source_stats(self, _path: Path) -> SourceStats:
            return SourceStats(size_bytes=2 * 1024 * 1024 * 1024, mtime_ns=1)

    monkeypatch.setattr(
        "ea_node_editor.addons.tabular_data.input_node.shared_tabular_loader_cache_service",
        _LargeNpzService,
    )

    with pytest.raises(LargeDataMaterializationError) as exc_info:
        execute_tabular_input(_context(properties={"path": str(source)}))

    assert exc_info.value.structured_error["code"] == TABULAR_DATA_INPUT_ERROR_LARGE_DATA_GATED
    assert exc_info.value.structured_error["size_bytes"] == 2 * 1024 * 1024 * 1024


def test_tabular_data_input_addon_record_and_default_registry_are_availability_gated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(tabular_catalog, "_find_spec", lambda _module_name: None)
    unavailable_record = addon_catalog.addon_record_by_id(
        "ea_node_editor.builtins.tabular_data",
        preferences_document=default_app_preferences_document(),
    )
    assert unavailable_record is not None
    assert unavailable_record.status == "unavailable"
    assert unavailable_record.provided_node_type_ids == ()
    assert build_default_registry().spec_or_none(TABULAR_DATA_INPUT_NODE_TYPE_ID) is None

    monkeypatch.setattr(tabular_catalog, "_find_spec", lambda _module_name: object())
    available_record = addon_catalog.addon_record_by_id(
        "ea_node_editor.builtins.tabular_data",
        preferences_document=default_app_preferences_document(),
    )
    assert available_record is not None
    assert available_record.status == "installed"
    assert available_record.provided_node_type_ids == tabular_catalog.TABULAR_DATA_FUNCTION_TYPE_IDS
    registry = build_default_registry()
    assert registry.spec_or_none(TABULAR_DATA_INPUT_NODE_TYPE_ID) is not None
    assert registry.spec_or_none("tabular.table_filter") is not None
    assert registry.spec_or_none("tabular.write_table_filter") is not None


def test_tabular_data_input_properties_round_trip_as_semantic_project_data() -> None:
    registry = build_default_registry()
    model = GraphModel()
    workspace = model.active_workspace
    properties = {
        "path": "relative/data.csv",
        "delimiter": "|",
        "encoding": "utf-8",
        "header_row": 0,
        "skip_rows": 1,
        "schema_hints": {"count": "int64"},
        "selected_object": "Sheet1",
        TABULAR_SELECTED_COLUMNS_PROPERTY: ["time", "temp"],
        "array_slice_2d": {"row_offset": 1, "column_offset": 2, "row_limit": 3, "column_limit": 4},
        "cache_policy": TABULAR_DATA_INPUT_CACHE_POLICY_APP_MANAGED_PARQUET,
        "project_managed_source": True,
        "project_managed_cache": False,
        "allow_npz_archive_preview": True,
        TABULAR_TABLE_VIEW_STATE_PROPERTY: {
            "version": 1,
            "column_widths": {"table:temp": 144, "array:2": 96},
        },
    }
    model.add_node(
        workspace.workspace_id,
        TABULAR_DATA_INPUT_NODE_TYPE_ID,
        TABULAR_DATA_INPUT_DISPLAY_NAME,
        10.0,
        20.0,
        properties=properties,
    )

    serializer = JsonProjectSerializer(registry)
    document = serializer.to_document(model.project)
    loaded = serializer.from_document(document)
    loaded_node = next(iter(loaded.workspaces[workspace.workspace_id].nodes.values()))

    assert loaded_node.properties == properties
    assert "cache_path" not in str(document)
    assert "parquet_cache" not in str(document)


def _assert_current_dataflow_document(document: dict[str, object]) -> None:
    retired_type_ids = {
        "core.start",
        "core.end",
        "core.branch",
        "core.on_failure",
        "hpc.on_status",
    }
    retired_port_keys = {
        "exec",
        "exec_in",
        "exec_out",
        "completed",
        "completed_in",
        "completed_out",
        "failed",
        "failed_in",
        "failed_out",
        "on_failed",
    }

    assert document["schema_version"] == 5
    for workspace_doc in document["workspaces"]:
        input_orders: dict[tuple[str, str], list[int]] = {}
        for node_doc in workspace_doc["nodes"]:
            assert node_doc["type_id"] not in retired_type_ids
            for metadata_key in ("exposed_ports", "port_labels"):
                assert retired_port_keys.isdisjoint(node_doc.get(metadata_key, {}))
        for edge_doc in workspace_doc["edges"]:
            assert edge_doc["source_port_key"] not in retired_port_keys
            assert edge_doc["target_port_key"] not in retired_port_keys
            assert edge_doc["enabled"] is True
            input_key = (edge_doc["target_node_id"], edge_doc["target_port_key"])
            input_orders.setdefault(input_key, []).append(edge_doc["input_order"])
        for orders in input_orders.values():
            assert sorted(orders) == list(range(len(orders)))


@pytest.mark.parametrize(
    "filename",
    ("tabular_plot_showcase.cxproj", "tabular_plot_showcase_direct.cxproj"),
)
def test_committed_tabular_showcases_use_current_dataflow_format(filename: str) -> None:
    project_path = Path(__file__).resolve().parents[1] / "examples" / filename
    document = json.loads(project_path.read_text(encoding="utf-8"))

    _assert_current_dataflow_document(document)
    JsonProjectSerializer(build_default_registry()).load(str(project_path))


@pytest.mark.parametrize("with_filter", (False, True))
def test_large_tabular_generator_emits_current_dataflow_projects(
    tmp_path: Path,
    with_filter: bool,
) -> None:
    from scripts.generate_large_tabular_csv import emit_project

    project_path = tmp_path / ("filtered.cxproj" if with_filter else "direct.cxproj")
    emit_project(project_path, tmp_path / "fixture.csv", with_filter=with_filter)
    document = json.loads(project_path.read_text(encoding="utf-8"))

    _assert_current_dataflow_document(document)
    project = JsonProjectSerializer(build_default_registry()).load(str(project_path))
    workspace = project.workspaces[project.active_workspace_id]
    assert len(workspace.edges) == (2 if with_filter else 1)

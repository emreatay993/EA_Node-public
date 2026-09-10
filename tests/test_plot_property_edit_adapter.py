from __future__ import annotations

from types import SimpleNamespace

from ea_node_editor.addons.property_edit_adapters import PropertyEditAdapterContext
from ea_node_editor.nodes.bootstrap import build_default_registry
from ea_node_editor.nodes.builtins.plot.property_edit_adapter import PlotPropertyEditAdapter
from ea_node_editor.ui.shell.inspector_projection import build_selected_node_property_items


def test_signal_schema_is_metadata_only_exact_and_separate_from_generic_controls(monkeypatch) -> None:
    import pandas as pd
    from ea_node_editor.runtime_contracts import DataTree
    from ea_node_editor.runtime_contracts.scientific_values import TableValue, snapshot_scientific_value

    frame = pd.DataFrame([[1., 2., 3., 4., 5., True, "text"]], columns=["", "Column 1", "same", "same", " Case ", "flag", "text"])
    table = snapshot_scientific_value(frame)
    monkeypatch.setattr(TableValue, "column_values", lambda *args: (_ for _ in ()).throw(AssertionError("UI materialized data")))
    node = SimpleNamespace(node_id="signal", type_id="plot.signal", properties={"x_column": 0, "y_columns": [" Case ", 2]}, exposed_ports={}, port_labels={}, parent_node_id=None)
    edge = SimpleNamespace(target_node_id="signal", target_port_key="values", source_node_id="python", source_port_key="custom_result", enabled=True)
    calls = []

    def current(node_id, port_key):
        calls.append((node_id, port_key))
        return DataTree.from_item(table)

    items = build_selected_node_property_items(node=node, spec=build_default_registry().get_spec("plot.signal"), subnode_pin_type_ids=set(), workspace_edges=[edge], current_output_provider=current)
    by_key = {item["key"]: item for item in items}
    assert calls == [("python", "custom_result")]
    assert by_key["x_column"]["enum_codes"] == [0, "Column 1", 2, 3, " Case "]
    assert len(set(by_key["x_column"]["enum_values"])) == 5
    assert by_key["y_columns"]["value"] == [" Case ", 2]
    assert not any(key.startswith(("plot_axis_", "plot_option_", "tabular_mapping_")) for key in by_key)
    edge.enabled = False
    empty = build_selected_node_property_items(node=node, spec=build_default_registry().get_spec("plot.signal"), subnode_pin_type_ids=set(), workspace_edges=[edge], current_output_provider=current)
    assert next(item for item in empty if item["key"] == "x_column")["enum_codes"] == []
    assert calls == [("python", "custom_result")]


def test_signal_cached_ref_schema_matches_explicit_window_and_slice_selections() -> None:
    from ea_node_editor.runtime_contracts import ArrayDataRef, ArraySlice2DRef, TabularDataRef, TabularWindowRef
    from ea_node_editor.nodes.builtins.plot.signal_schema import enrich_signal_property_items

    base = TabularDataRef(ref_id="table", resolver_id="cached", source_uri="missing.csv", metadata={"column_schema": [{"name": "time", "dtype": "timestamp[us]"}, {"name": "a", "dtype": "float64"}, {"name": "b", "dtype": "float64"}], "node_options": {"selected_columns": ["a"]}})
    items = [{"key": "x_column"}, {"key": "y_columns"}]
    assert enrich_signal_property_items(items, base)[0]["enum_codes"] == ["a"]
    window = TabularWindowRef(ref_id="window", table_data=base, columns=("time", "b"))
    assert enrich_signal_property_items(items, window)[0]["enum_codes"] == ["time", "b"]
    assert enrich_signal_property_items(items, window)[1]["enum_codes"] == ["b"]
    array = ArrayDataRef(ref_id="array", resolver_id="cached", source_uri="missing.npy", shape=(10, 4), dtype="float64", metadata={"array_slice_2d": {"column_offset": 2, "column_limit": 1}})
    sliced = ArraySlice2DRef(ref_id="slice", array_data=array, column_offset=0, column_limit=3)
    assert enrich_signal_property_items(items, array)[0]["enum_codes"] == [0]
    assert enrich_signal_property_items(items, sliced)[0]["enum_codes"] == [0, 1, 2]


def _items_by_key(type_id: str, properties: dict[str, object] | None = None) -> dict[str, dict[str, object]]:
    registry = build_default_registry()
    spec = registry.get_spec(type_id)
    node = SimpleNamespace(
        node_id="node_plot",
        type_id=type_id,
        title="Plot",
        properties=dict(properties or {}),
        exposed_ports={},
        port_labels={},
        parent_node_id=None,
    )
    items = build_selected_node_property_items(
        node=node,
        spec=spec,
        subnode_pin_type_ids=set(),
        workspace_nodes={node.node_id: node},
        workspace_edges={},
    )
    return {str(item["key"]): item for item in items}


def _fields_by_role(item: dict[str, object]) -> dict[str, dict[str, object]]:
    fields = item.get("fields")
    assert isinstance(fields, list)
    return {str(field["role"]): field for field in fields if isinstance(field, dict)}


def test_generic_plot_json_properties_project_to_structured_inspector_rows() -> None:
    items = _items_by_key(
        "plot.scatter",
        {
            "axis_limits": {"x": [0, 10]},
            "log_scales": {"y": True},
            "tabular_mapping": {"x": "time", "y": ["temperature"]},
            "plot_options": {
                "plot_theme": "light",
                "hover_readout": True,
                "vertical_guide": True,
                "crosshair": False,
                "custom_backend_flag": True,
            },
        },
    )

    for raw_key in ("axis_limits", "log_scales", "tabular_mapping", "plot_options"):
        assert raw_key not in items
    assert "axis_limit_x_min" not in items
    assert "log_scale_y" not in items
    assert items["plot_axis_x"]["editor_mode"] == "axis_compact"
    assert items["plot_axis_x"]["dirty"] is True
    assert items["plot_axis_x"]["help_text"] == "Auto range unless Min or Max is set."
    x_fields = _fields_by_role(items["plot_axis_x"])
    assert x_fields["min"]["key"] == "axis_limit_x_min"
    assert x_fields["min"]["value"] == 0
    assert x_fields["min"]["placeholder_text"] == "Auto"
    assert x_fields["min"]["reset_value"] == ""
    assert x_fields["max"]["key"] == "axis_limit_x_max"
    assert x_fields["max"]["value"] == 10
    assert x_fields["log"]["key"] == "log_scale_x"
    assert x_fields["log"]["value"] is False
    assert x_fields["log"]["reset_value"] is False
    y_fields = _fields_by_role(items["plot_axis_y"])
    assert y_fields["min"]["value"] == ""
    assert y_fields["max"]["value"] == ""
    assert y_fields["log"]["value"] is True
    assert "plot_axis_z" not in items
    assert items["tabular_mapping_x"]["editor_mode"] == "editable_combo"
    assert items["tabular_mapping_y"]["editor_mode"] == "chip_list"
    assert items["tabular_mapping_y"]["value"] == ["temperature"]
    assert items["plot_option_plot_theme"]["editor_mode"] == "editable_combo"
    assert items["plot_option_plot_theme"]["enum_values"] == ["system", "dark", "light"]
    assert items["plot_option_plot_theme"]["value"] == "light"
    assert items["plot_option_hover_readout"]["editor_mode"] == "toggle"
    assert items["plot_option_hover_readout"]["value"] is True
    assert items["plot_option_vertical_guide"]["value"] is True
    assert items["plot_option_crosshair"]["value"] is False
    assert items["plot_options_unsupported_summary"]["editor_mode"] == "summary"


def test_plot_axis_controls_show_z_only_for_3d_plot_types() -> None:
    line_items = _items_by_key("plot.scatter")
    surface_items = _items_by_key("plot.surface")

    assert {"plot_axis_x", "plot_axis_y"}.issubset(line_items)
    assert "plot_axis_z" not in line_items
    assert {"plot_axis_x", "plot_axis_y", "plot_axis_z"}.issubset(surface_items)
    assert "plot_option_hover_readout" in line_items
    assert "plot_option_hover_readout" not in surface_items


def test_histogram_plot_options_project_to_typed_controls() -> None:
    items = _items_by_key("plot.histogram", {"plot_options": {"bins": 24}})

    assert "plot_options" not in items
    assert items["plot_option_bins"]["editor_mode"] == "text"
    assert items["plot_option_bins"]["value"] == 24


def test_plot_adapter_rewrites_structured_axis_log_mapping_and_options() -> None:
    node = SimpleNamespace(
        type_id="plot.scatter",
        properties={
            "axis_limits": {"x": [None, None], "y": [None, None], "z": [None, None]},
            "log_scales": {"x": False, "y": False, "z": False},
            "tabular_mapping": {},
            "plot_options": {"custom": True, "bins": 10},
        },
    )
    context = PropertyEditAdapterContext(node=node)
    adapter = PlotPropertyEditAdapter()

    axis = adapter.rewrite_property_edit(context, key="axis_limit_x_min", value="5")
    log = adapter.rewrite_property_edit(context, key="log_scale_y", value=True)
    mapping = adapter.rewrite_property_edit(context, key="tabular_mapping_y", value=["a", "b"])
    options = adapter.rewrite_property_edit(context, key="plot_options_reset_unsupported", value=True)
    theme = adapter.rewrite_property_edit(context, key="plot_option_plot_theme", value="dark")
    hover = adapter.rewrite_property_edit(context, key="plot_option_hover_readout", value="true")
    guide = adapter.rewrite_property_edit(context, key="plot_option_vertical_guide", value=True)
    crosshair = adapter.rewrite_property_edit(context, key="plot_option_crosshair", value=False)

    assert axis is not None and axis.key == "axis_limits"
    assert axis.value["x"] == [5, None]
    assert log is not None and log.key == "log_scales"
    assert log.value["y"] is True
    assert mapping is not None and mapping.key == "tabular_mapping"
    assert mapping.value == {"y": ["a", "b"]}
    assert options is not None and options.key == "plot_options"
    assert options.value == {"bins": 10}
    assert theme is not None and theme.key == "plot_options"
    assert theme.value["plot_theme"] == "dark"
    assert hover is not None and hover.value["hover_readout"] is True
    assert guide is not None and guide.value["vertical_guide"] is True
    assert crosshair is not None and crosshair.value["crosshair"] is False

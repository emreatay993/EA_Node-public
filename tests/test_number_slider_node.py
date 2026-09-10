from __future__ import annotations

import math

import pytest

from ea_node_editor.common.number_slider_query import (
    number_slider_query_payload,
    parse_number_slider_query,
)
from ea_node_editor.graph.records import NodeInstance
from ea_node_editor.nodes.bootstrap import build_builtin_registry
from ea_node_editor.nodes.builtins.data_control import (
    NUMBER_SLIDER_PILL_HEIGHT,
    NUMBER_SLIDER_TYPE_ID,
    execute_number_slider,
    normalize_number_slider_properties,
    number_slider_settings,
    number_slider_step,
)
from ea_node_editor.runtime_contracts import DOUBLE_DATA_TYPE_ID
from ea_node_editor.ui_qml.graph_surface_metrics import (
    node_surface_metrics,
    resolved_node_surface_size,
)
from ea_node_editor.ui_qml.surface_contracts import surface_spec_for_node_type


@pytest.fixture(scope="module")
def registry():
    return build_builtin_registry()


def _node(registry, **property_overrides) -> NodeInstance:
    properties = registry.default_properties(NUMBER_SLIDER_TYPE_ID)
    properties.update(property_overrides)
    return NodeInstance(
        node_id="slider-1",
        type_id=NUMBER_SLIDER_TYPE_ID,
        title="Number Slider",
        x=0.0,
        y=0.0,
        properties=properties,
    )


class _Ctx:
    def __init__(self, properties):
        self.properties = properties


class TestNumberSliderSpec:
    def test_spec_shape(self, registry) -> None:
        spec = registry.get_spec(NUMBER_SLIDER_TYPE_ID)
        assert spec.display_name == "Number Slider"
        assert spec.category_path == ("Data", "Control")
        assert spec.collapsible is False
        assert spec.surface_family == "standard"
        assert spec.surface_variant == "number_slider"
        assert "number" in spec.keywords and "slider" in spec.keywords
        assert [port.direction for port in spec.ports] == ["out"]
        out = spec.ports[0]
        assert (out.key, out.kind, out.data_type, out.data_access) == (
            "value",
            "data",
            DOUBLE_DATA_TYPE_ID,
            "item",
        )

    def test_default_properties(self, registry) -> None:
        assert registry.default_properties(NUMBER_SLIDER_TYPE_ID) == {
            "value": 5.0,
            "minimum": 0.0,
            "maximum": 10.0,
            "rounding": "decimal",
            "decimals": 2,
        }

    def test_surface_spec_resolves_to_pill_component(self, registry) -> None:
        spec = registry.get_spec(NUMBER_SLIDER_TYPE_ID)
        surface = surface_spec_for_node_type(type_id=NUMBER_SLIDER_TYPE_ID, spec=spec)
        assert surface.qml_component == "passive/GraphNumberSliderSurface.qml"
        assert (surface.family, surface.variant) == ("standard", "number_slider")

class TestNumberSliderNormalization:
    def test_full_pass_clamps_value_into_range(self, registry) -> None:
        normalized = registry.normalize_properties(
            NUMBER_SLIDER_TYPE_ID,
            {"value": 99.0, "minimum": 0.0, "maximum": 10.0, "rounding": "decimal", "decimals": 2},
        )
        assert normalized["value"] == 10.0

    def test_integer_mode_snaps_bounds_and_value(self, registry) -> None:
        normalized = registry.normalize_properties(
            NUMBER_SLIDER_TYPE_ID,
            {"value": 3.4, "minimum": 0.2, "maximum": 9.7, "rounding": "integer", "decimals": 2},
        )
        assert normalized == {
            "value": 3.0,
            "minimum": 0.0,
            "maximum": 10.0,
            "rounding": "integer",
            "decimals": 2,
        }

    def test_degenerate_range_is_repaired_with_derived_step(self, registry) -> None:
        normalized = registry.normalize_properties(
            NUMBER_SLIDER_TYPE_ID,
            {"value": 5.0, "minimum": 10.0, "maximum": 10.0, "rounding": "decimal", "decimals": 1},
        )
        assert normalized["maximum"] == pytest.approx(10.1)
        assert normalized["value"] == pytest.approx(10.0)

    def test_single_key_normalization_rejects_non_finite(self, registry) -> None:
        assert registry.normalize_property_value(NUMBER_SLIDER_TYPE_ID, "value", float("nan")) == 5.0
        assert registry.normalize_property_value(NUMBER_SLIDER_TYPE_ID, "minimum", float("inf")) == 0.0

    def test_decimals_clamped_to_supported_range(self, registry) -> None:
        assert registry.normalize_property_value(NUMBER_SLIDER_TYPE_ID, "decimals", 99) == 6
        assert registry.normalize_property_value(NUMBER_SLIDER_TYPE_ID, "decimals", -3) == 0

    def test_partial_dict_is_not_clamped_against_defaults(self) -> None:
        # A node may have a custom range; a lone value update must not be
        # clamped against the spec defaults.
        normalized = normalize_number_slider_properties({"value": 250.0})
        assert normalized == {"value": 250.0}

    def test_contextual_update_reclamps_value_when_maximum_drops(self, registry) -> None:
        from ea_node_editor.ui_qml.graph_scene_mutation.selection_and_scope_ops import (
            _contextual_property_updates,
        )

        node = _node(registry, value=8.0)
        updates = _contextual_property_updates(registry, node, {"maximum": 6.0})
        assert updates["maximum"] == 6.0
        assert updates["value"] == 6.0

    def test_step_derivation(self) -> None:
        assert number_slider_step("integer", 4) == 1.0
        assert number_slider_step("decimal", 2) == pytest.approx(0.01)
        assert number_slider_step("decimal", 0) == pytest.approx(1.0)


class TestNumberSliderExecute:
    def test_decimal_mode_outputs_rounded_float(self) -> None:
        result = execute_number_slider(
            _Ctx({"value": 5.678, "minimum": 0.0, "maximum": 10.0, "rounding": "decimal", "decimals": 2})
        )
        assert result.outputs == {"value": 5.68}
        assert isinstance(result.outputs["value"], float)

    def test_integer_mode_outputs_whole_number(self) -> None:
        result = execute_number_slider(
            _Ctx({"value": 5.678, "minimum": 0.0, "maximum": 10.0, "rounding": "integer", "decimals": 2})
        )
        assert result.outputs == {"value": 6}
        assert isinstance(result.outputs["value"], int)

    def test_missing_properties_fall_back_to_defaults(self) -> None:
        result = execute_number_slider(_Ctx({}))
        assert result.outputs == {"value": 5.0}

    def test_settings_resolution_repairs_hostile_input(self) -> None:
        settings = number_slider_settings(
            {"value": float("nan"), "minimum": "abc", "maximum": None, "rounding": "bogus", "decimals": "x"}
        )
        assert settings["rounding"] == "decimal"
        assert settings["minimum"] < settings["maximum"]
        assert settings["minimum"] <= settings["value"] <= settings["maximum"]
        assert math.isfinite(settings["value"])


class TestNumberSliderMetrics:
    def test_pill_metrics_payload(self, registry) -> None:
        spec = registry.get_spec(NUMBER_SLIDER_TYPE_ID)
        payload = node_surface_metrics(_node(registry), spec).to_payload()
        assert payload["default_height"] == NUMBER_SLIDER_PILL_HEIGHT
        assert payload["min_height"] == NUMBER_SLIDER_PILL_HEIGHT
        assert payload["header_height"] == 0.0
        assert payload["title_height"] == 0.0
        assert payload["body_top"] == 0.0
        assert payload["port_top"] == 0.0
        assert payload["port_height"] == NUMBER_SLIDER_PILL_HEIGHT
        assert payload["port_center_offset"] == NUMBER_SLIDER_PILL_HEIGHT / 2
        # Chrome owns the pill body: shared shadow, state-aware border, and
        # port notches all require host chrome to stay enabled.
        assert payload["use_host_chrome"] is True
        assert payload["use_host_shadow"] is True

    def test_height_is_locked_against_custom_resize(self, registry) -> None:
        spec = registry.get_spec(NUMBER_SLIDER_TYPE_ID)
        node = _node(registry)
        node.custom_width = 400.0
        node.custom_height = 300.0
        width, height = resolved_node_surface_size(node, spec)
        assert width == 400.0
        assert height == NUMBER_SLIDER_PILL_HEIGHT


class TestNumberSliderQueryParser:
    @pytest.mark.parametrize(
        ("query", "expected"),
        [
            ("0<10", {"minimum": 0.0, "value": 5.0, "maximum": 10.0, "rounding": "integer", "decimals": 0}),
            ("0<5<10", {"minimum": 0.0, "value": 5.0, "maximum": 10.0, "rounding": "integer", "decimals": 0}),
            (" 0 < 5 < 10 ", {"minimum": 0.0, "value": 5.0, "maximum": 10.0, "rounding": "integer", "decimals": 0}),
            ("-2.5<0<2.5", {"minimum": -2.5, "value": 0.0, "maximum": 2.5, "rounding": "decimal", "decimals": 1}),
            ("0<0.25<1", {"minimum": 0.0, "value": 0.25, "maximum": 1.0, "rounding": "decimal", "decimals": 2}),
            ("0.0<1", {"minimum": 0.0, "value": 0.5, "maximum": 1.0, "rounding": "decimal", "decimals": 1}),
        ],
    )
    def test_valid_expressions(self, query, expected) -> None:
        parsed = parse_number_slider_query(query)
        assert parsed is not None
        for key, value in expected.items():
            assert getattr(parsed, key) == value, key

    @pytest.mark.parametrize(
        "query",
        ["10<0", "0<11<10", "abc", "0<", "<10", "0<10<", "number", "5", "", "0<abc<10", "1<1"],
    )
    def test_invalid_expressions(self, query) -> None:
        assert parse_number_slider_query(query) is None

    def test_two_term_integer_midpoint_rounds(self) -> None:
        parsed = parse_number_slider_query("0<5")
        assert parsed is not None
        assert parsed.value == 3.0

    def test_payload_shape(self) -> None:
        assert number_slider_query_payload(None) == {}
        payload = number_slider_query_payload(parse_number_slider_query("0<5<10"))
        assert payload["valid"] is True
        assert payload["summary"] == "0 < 5 < 10"

    def test_bridge_slot_round_trip(self, registry) -> None:
        from ea_node_editor.ui_qml.shell_library_bridge import ShellLibraryBridge

        class _Signal:
            def connect(self, *_args):  # noqa: ANN002
                return None

        class _Source:
            node_library_changed = _Signal()
            library_pane_reset_requested = _Signal()
            graph_search_changed = _Signal()
            connection_quick_insert_changed = _Signal()
            graph_hint_changed = _Signal()

        bridge = ShellLibraryBridge(library_source=_Source())
        payload = bridge.parse_number_slider_query("1<2<3")
        assert payload["valid"] is True
        assert bridge.parse_number_slider_query("not a slider") == {}


class TestNumberSliderInsertChain:
    def test_drop_ops_insert_with_properties_routes_to_canonical_creator(self, registry) -> None:
        from ea_node_editor.ui.shell.controllers.workspace_drop_connect_controller import (
            WorkspaceDropConnectController,
        )

        calls = {}

        class _Scene:
            active_scope_path = []

            def create_node_from_type(self, **kwargs):
                calls.update(kwargs)
                return "node-77"

        class _Host:
            scene = _Scene()
            app_preferences_controller = None

        ops = WorkspaceDropConnectController(
            _Host(),
            active_workspace=lambda: None,
            resolve_custom_workflow_definition=lambda _workflow_id: None,
            prompt_connection_candidate=lambda **_kwargs: None,
            effects=object(),  # type: ignore[arg-type]
        )
        node_id = ops.insert_library_node_with_properties(
            NUMBER_SLIDER_TYPE_ID,
            {"minimum": 0.0, "value": 5.0, "maximum": 10.0},
            120.0,
            240.0,
        )
        assert node_id == "node-77"
        assert calls["type_id"] == NUMBER_SLIDER_TYPE_ID
        assert calls["x"] == 120.0 and calls["y"] == 240.0
        assert calls["select_node"] is False
        assert calls["property_overrides"] == {"minimum": 0.0, "value": 5.0, "maximum": 10.0}

    def test_drop_ops_rejects_custom_workflow_type_ids(self) -> None:
        from ea_node_editor.ui.shell.controllers.workspace_drop_connect_controller import (
            WorkspaceDropConnectController,
        )

        class _Host:
            scene = None

        ops = WorkspaceDropConnectController(
            _Host(),
            active_workspace=lambda: None,
            resolve_custom_workflow_definition=lambda _workflow_id: None,
            prompt_connection_candidate=lambda **_kwargs: None,
            effects=object(),  # type: ignore[arg-type]
        )
        assert ops.insert_library_node_with_properties("", {}, 0.0, 0.0) == ""

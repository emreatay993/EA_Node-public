from __future__ import annotations

import json

import pytest

from ea_node_editor.execution.run_messages import (
    NodeSettledEvent,
)
from ea_node_editor.execution.protocol_codec import (
    dict_to_event,
    event_to_dict,
)
from ea_node_editor.runtime_contracts.settled_results import SettledPortResult
from ea_node_editor.nodes.builtins.units import (
    IQUANTITY_DATA_TYPE_ID,
    LENGTH_DATA_TYPE_ID,
    LENGTH_UNIT_NAMES,
    PLANE_ANGLE_DATA_TYPE_ID,
    PLANE_ANGLE_UNIT_NAMES,
    QUANTIFIABLE_INTERVAL_LENGTH_DATA_TYPE_ID,
    COREX_UNITS_CONTRACT_MANIFEST,
    COREX_UNITS_DATA_TYPES,
    COREX_UNITS_OWNER_ID,
    COREX_UNITS_OWNER_VERSION,
    TIME_DATA_TYPE_ID,
    TIME_UNIT_NAMES,
    UNIT_SYSTEM_DATA_TYPE_ID,
    UNIT_SYSTEM_DERIVED_UNIT_ENUMS,
    UNIT_SYSTEM_IDENTIFIERS,
    is_length_payload,
    is_plane_angle_payload,
    is_quantifiable_interval_length_payload,
    is_time_payload,
    is_unit_system_payload,
)
from ea_node_editor.nodes.core_data_types import GRAPH_DATA_TYPE_ID
from ea_node_editor.nodes.registry import NodeRegistry
from ea_node_editor.runtime_contracts import (
    DataTree,
    DataTypeCatalogError,
    TypedInlineValue,
)


class _FloatSubclass(float):
    pass


class _StringSubclass(str):
    pass


class _DictSubclass(dict):
    pass


class _StatefulStringKey(str):
    def __new__(cls, value: str) -> _StatefulStringKey:
        instance = super().__new__(cls, value)
        instance.equality_calls = 0
        instance.hash_calls = 0
        return instance

    def __eq__(self, other: object) -> bool:
        self.equality_calls += 1
        raise RuntimeError("hostile-key-secret")

    def __hash__(self) -> int:
        self.hash_calls += 1
        return str.__hash__(self)


def _registry() -> NodeRegistry:
    registry = NodeRegistry()
    registry.register_plugin_bundle(
        COREX_UNITS_CONTRACT_MANIFEST,
        (),
        owner_id=COREX_UNITS_OWNER_ID,
        owner_version=COREX_UNITS_OWNER_VERSION,
    )
    return registry


def _default_derived_units() -> dict[str, str]:
    return {
        property_name: sorted(enum_names)[0]
        for property_name, enum_names in UNIT_SYSTEM_DERIVED_UNIT_ENUMS.items()
    }


def _unit_system_payload() -> dict[str, object]:
    return {
        "identifier": "MKgS",
        "derived_units": _default_derived_units(),
    }




def test_exact_parent_carrier_abstract_and_persistence_facts() -> None:
    specs = {spec.type_id: spec for spec in COREX_UNITS_DATA_TYPES}
    assert specs[IQUANTITY_DATA_TYPE_ID].parents == (GRAPH_DATA_TYPE_ID,)
    assert specs[IQUANTITY_DATA_TYPE_ID].abstract is True
    assert specs[IQUANTITY_DATA_TYPE_ID].carriers == frozenset({"inline"})
    assert specs[IQUANTITY_DATA_TYPE_ID].persistence == "never"
    assert not specs[IQUANTITY_DATA_TYPE_ID].validate_item(
        {"value": 1.0, "unit": "Meter"}
    )

    for type_id in (
        LENGTH_DATA_TYPE_ID,
        PLANE_ANGLE_DATA_TYPE_ID,
        TIME_DATA_TYPE_ID,
    ):
        assert specs[type_id].parents == (IQUANTITY_DATA_TYPE_ID,)
        assert specs[type_id].abstract is False
        assert specs[type_id].carriers == frozenset({"inline"})
        assert specs[type_id].persistence == "inline"

    for type_id in (
        QUANTIFIABLE_INTERVAL_LENGTH_DATA_TYPE_ID,
        UNIT_SYSTEM_DATA_TYPE_ID,
    ):
        assert specs[type_id].parents == (GRAPH_DATA_TYPE_ID,)
        assert specs[type_id].abstract is False
        assert specs[type_id].carriers == frozenset({"inline"})
        assert specs[type_id].persistence == "inline"


def test_quantity_children_validate_at_abstract_but_other_units_do_not() -> None:
    catalog = _registry().data_types
    quantity_values = (
        TypedInlineValue(
            LENGTH_DATA_TYPE_ID,
            1,
            {"value": 1.0, "unit": "Meter"},
        ),
        TypedInlineValue(
            PLANE_ANGLE_DATA_TYPE_ID,
            1,
            {"value": 90.0, "unit": "Degree"},
        ),
        TypedInlineValue(
            TIME_DATA_TYPE_ID,
            1,
            {"value": 2.0, "unit": "Second"},
        ),
    )
    for value in quantity_values:
        catalog.validate_carrier(IQUANTITY_DATA_TYPE_ID, value)

    assert catalog.is_assignable(LENGTH_DATA_TYPE_ID, IQUANTITY_DATA_TYPE_ID)
    assert catalog.is_assignable(PLANE_ANGLE_DATA_TYPE_ID, IQUANTITY_DATA_TYPE_ID)
    assert catalog.is_assignable(TIME_DATA_TYPE_ID, IQUANTITY_DATA_TYPE_ID)
    assert not catalog.is_assignable(
        QUANTIFIABLE_INTERVAL_LENGTH_DATA_TYPE_ID,
        IQUANTITY_DATA_TYPE_ID,
    )
    assert not catalog.is_assignable(
        UNIT_SYSTEM_DATA_TYPE_ID,
        IQUANTITY_DATA_TYPE_ID,
    )
    with pytest.raises(DataTypeCatalogError):
        catalog.validate_carrier(
            IQUANTITY_DATA_TYPE_ID,
            TypedInlineValue(
                QUANTIFIABLE_INTERVAL_LENGTH_DATA_TYPE_ID,
                1,
                {"data": {"start": 0.0, "end": 1.0}, "unit": "Meter"},
            ),
        )
    with pytest.raises(DataTypeCatalogError):
        catalog.validate_carrier(
            IQUANTITY_DATA_TYPE_ID,
            TypedInlineValue(UNIT_SYSTEM_DATA_TYPE_ID, 1, _unit_system_payload()),
        )


@pytest.mark.parametrize(
    ("validator", "unit_names"),
    (
        (is_length_payload, LENGTH_UNIT_NAMES),
        (is_plane_angle_payload, PLANE_ANGLE_UNIT_NAMES),
        (is_time_payload, TIME_UNIT_NAMES),
    ),
)
def test_every_reviewed_quantity_enum_name_is_accepted(
    validator,
    unit_names: frozenset[str],
) -> None:
    for unit_name in unit_names:
        assert validator({"value": -12.5, "unit": unit_name})


@pytest.mark.parametrize(
    ("validator", "invalid"),
    (
        (is_length_payload, {"value": 1.0, "unit": "Second"}),
        (is_plane_angle_payload, {"value": 1.0, "unit": "Meter"}),
        (is_time_payload, {"value": 1.0, "unit": "Degree"}),
        (is_length_payload, {"Value": 1.0, "unit": "Meter"}),
        (is_length_payload, {"value": 1.0, "Unit": "Meter"}),
        (is_length_payload, {"value": 1.0}),
        (is_length_payload, {"value": 1.0, "unit": "Meter", "extra": None}),
        (is_length_payload, {"value": 1, "unit": "Meter"}),
        (is_length_payload, {"value": True, "unit": "Meter"}),
        (is_length_payload, {"value": float("inf"), "unit": "Meter"}),
        (is_length_payload, {"value": float("nan"), "unit": "Meter"}),
        (is_length_payload, {"value": _FloatSubclass(1.0), "unit": "Meter"}),
        (is_length_payload, {"value": 1.0, "unit": _StringSubclass("Meter")}),
        (
            is_length_payload,
            _DictSubclass({"value": 1.0, "unit": "Meter"}),
        ),
    ),
)
def test_quantity_payloads_reject_hostile_or_inexact_shapes(
    validator,
    invalid: object,
) -> None:
    assert not validator(invalid)


def test_quantifiable_interval_requires_exact_payload_and_preserves_order() -> None:
    for unit_name in LENGTH_UNIT_NAMES:
        assert is_quantifiable_interval_length_payload(
            {
                "data": {"start": 10.0, "end": -10.0},
                "unit": unit_name,
            }
        )
    invalid = (
        {"data": {"start": 0.0, "end": 1.0}, "unit": "Second"},
        {"data": {"Start": 0.0, "end": 1.0}, "unit": "Meter"},
        {"data": {"start": 0.0}, "unit": "Meter"},
        {"data": {"start": 0.0, "end": 1.0, "extra": 2.0}, "unit": "Meter"},
        {"data": {"start": 0, "end": 1.0}, "unit": "Meter"},
        {"data": {"start": False, "end": 1.0}, "unit": "Meter"},
        {"data": {"start": 0.0, "end": float("nan")}, "unit": "Meter"},
        {
            "data": _DictSubclass({"start": 0.0, "end": 1.0}),
            "unit": "Meter",
        },
        _DictSubclass({"data": {"start": 0.0, "end": 1.0}, "unit": "Meter"}),
    )
    for value in invalid:
        assert not is_quantifiable_interval_length_payload(value)


def test_every_reviewed_unit_system_identifier_and_property_enum_is_accepted() -> None:
    assert len(UNIT_SYSTEM_IDENTIFIERS) == 8
    assert len(UNIT_SYSTEM_DERIVED_UNIT_ENUMS) == 16
    for identifier in UNIT_SYSTEM_IDENTIFIERS:
        assert is_unit_system_payload(
            {
                "identifier": identifier,
                "derived_units": _default_derived_units(),
            }
        )
    for property_name, enum_names in UNIT_SYSTEM_DERIVED_UNIT_ENUMS.items():
        for enum_name in enum_names:
            derived_units = _default_derived_units()
            derived_units[property_name] = enum_name
            assert is_unit_system_payload(
                {
                    "identifier": "MKgS",
                    "derived_units": derived_units,
                }
            )


def test_unit_system_rejects_incomplete_unknown_and_inexact_payloads() -> None:
    valid = _unit_system_payload()
    missing_derived = _default_derived_units()
    missing_derived.pop("Area")
    extra_derived = _default_derived_units()
    extra_derived["Length"] = "Meter"
    wrong_case = _default_derived_units()
    wrong_case["area"] = wrong_case.pop("Area")
    wrong_family = _default_derived_units()
    wrong_family["Area"] = "Meter"
    subclass_value = _default_derived_units()
    subclass_value["Area"] = _StringSubclass(subclass_value["Area"])
    invalid = (
        {"identifier": "Unknown", "derived_units": _default_derived_units()},
        {"Identifier": "MKgS", "derived_units": _default_derived_units()},
        {"identifier": "MKgS", "DerivedUnits": _default_derived_units()},
        {
            "identifier": "MKgS",
            "derived_units": _default_derived_units(),
            "Length": "Meter",
        },
        {"identifier": "MKgS", "derived_units": missing_derived},
        {"identifier": "MKgS", "derived_units": extra_derived},
        {"identifier": "MKgS", "derived_units": wrong_case},
        {"identifier": "MKgS", "derived_units": wrong_family},
        {"identifier": "MKgS", "derived_units": subclass_value},
        {
            "identifier": _StringSubclass("MKgS"),
            "derived_units": _default_derived_units(),
        },
        {
            "identifier": "MKgS",
            "derived_units": _DictSubclass(_default_derived_units()),
        },
        _DictSubclass(valid),
    )
    for value in invalid:
        assert not is_unit_system_payload(value)


def test_hostile_string_keys_never_run_user_equality_or_hash_or_leak_errors() -> None:
    quantity_key = _StatefulStringKey("value")
    quantity = {quantity_key: 1.0, "unit": "Meter"}

    quantifiable_root_key = _StatefulStringKey("data")
    quantifiable_root = {
        quantifiable_root_key: {"start": 0.0, "end": 1.0},
        "unit": "Meter",
    }

    interval_key = _StatefulStringKey("start")
    quantifiable_nested = {
        "data": {interval_key: 0.0, "end": 1.0},
        "unit": "Meter",
    }

    unit_system_root_key = _StatefulStringKey("identifier")
    unit_system_root = {
        unit_system_root_key: "MKgS",
        "derived_units": _default_derived_units(),
    }

    derived_key = _StatefulStringKey("Area")
    hostile_derived = _default_derived_units()
    hostile_derived.pop("Area")
    hostile_derived[derived_key] = sorted(UNIT_SYSTEM_DERIVED_UNIT_ENUMS["Area"])[0]
    unit_system_nested = {
        "identifier": "MKgS",
        "derived_units": hostile_derived,
    }

    cases = (
        (
            is_length_payload,
            LENGTH_DATA_TYPE_ID,
            quantity,
            quantity_key,
        ),
        (
            is_quantifiable_interval_length_payload,
            QUANTIFIABLE_INTERVAL_LENGTH_DATA_TYPE_ID,
            quantifiable_root,
            quantifiable_root_key,
        ),
        (
            is_quantifiable_interval_length_payload,
            QUANTIFIABLE_INTERVAL_LENGTH_DATA_TYPE_ID,
            quantifiable_nested,
            interval_key,
        ),
        (
            is_unit_system_payload,
            UNIT_SYSTEM_DATA_TYPE_ID,
            unit_system_root,
            unit_system_root_key,
        ),
        (
            is_unit_system_payload,
            UNIT_SYSTEM_DATA_TYPE_ID,
            unit_system_nested,
            derived_key,
        ),
    )
    catalog = _registry().data_types
    for validator, type_id, payload, key in cases:
        calls_before = (key.equality_calls, key.hash_calls)
        assert not validator(payload)
        with pytest.raises(DataTypeCatalogError) as exc_info:
            catalog.validate_output(type_id, payload)
        assert "hostile-key-secret" not in str(exc_info.value)
        assert (key.equality_calls, key.hash_calls) == calls_before


def test_units_round_trip_through_stdio_with_nested_data_tree_paths() -> None:
    registry = _registry()
    tree = DataTree(
        (
            (
                (0,),
                (
                    TypedInlineValue(
                        LENGTH_DATA_TYPE_ID,
                        1,
                        {"value": 1.25, "unit": "Meter"},
                    ),
                    TypedInlineValue(
                        PLANE_ANGLE_DATA_TYPE_ID,
                        1,
                        {"value": 180.0, "unit": "Degree"},
                    ),
                ),
            ),
            (
                (1, 2),
                (
                    TypedInlineValue(
                        TIME_DATA_TYPE_ID,
                        1,
                        {"value": 3.5, "unit": "Second"},
                    ),
                    TypedInlineValue(
                        QUANTIFIABLE_INTERVAL_LENGTH_DATA_TYPE_ID,
                        1,
                        {
                            "data": {"start": 2.0, "end": -2.0},
                            "unit": "Millimeter",
                        },
                    ),
                    TypedInlineValue(
                        UNIT_SYSTEM_DATA_TYPE_ID,
                        1,
                        _unit_system_payload(),
                    ),
                ),
            ),
        )
    )
    event = NodeSettledEvent(
        outputs={"units": SettledPortResult(status="value", value=tree)}
    )
    wire = json.loads(json.dumps(event_to_dict(event, catalog=registry.data_types)))
    restored = dict_to_event(wire, catalog=registry.data_types)
    assert restored.outputs["units"].value == tree

    quantity_tree = DataTree(
        (tree.branches[0], (tree.branches[1][0], tree.branches[1][1][:1]))
    )
    registry.data_types.validate_carrier(IQUANTITY_DATA_TYPE_ID, quantity_tree)

from __future__ import annotations

import pytest

from ea_node_editor.nodes.node_specs import NodeTypeSpec, PortSpec, PropertySpec
from ea_node_editor.nodes.registry import NodeRegistry
from ea_node_editor.nodes.spec_validation import validate_node_spec


def test_invalid_enum_default_raises_exact_value_error() -> None:
    spec = NodeTypeSpec(
        type_id="tests.bad_enum",
        display_name="Bad Enum",
        category_path=("Tests",),
        icon="",
        ports=(PortSpec("value", "out", "data", "COREX.DataTypes.Any"),),
        properties=(
            PropertySpec(
                "level",
                "enum",
                "fatal",
                "Level",
                enum_values=("info", "warning", "error"),
            ),
        ),
    )

    with pytest.raises(
        ValueError,
        match=r"^Invalid default for property level \(enum\): 'fatal'$",
    ):
        validate_node_spec(spec, data_types=NodeRegistry().data_types)


def test_non_serializable_json_default_raises_exact_value_error() -> None:
    spec = NodeTypeSpec(
        type_id="tests.bad_json_default",
        display_name="Bad Json Default",
        category_path=("Tests",),
        icon="",
        ports=(PortSpec("value", "out", "data", "COREX.DataTypes.Any"),),
        properties=(PropertySpec("payload", "json", {"obj": object()}, "Payload"),),
    )

    with pytest.raises(
        ValueError,
        match=r"^Invalid default for property payload \(json\): ",
    ):
        validate_node_spec(spec, data_types=NodeRegistry().data_types)

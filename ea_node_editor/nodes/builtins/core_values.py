# Purpose: Declare strict COREX Complex, Color, and Image value contracts.
# Map: subsystems/nodes_registry_builtins.md
# Tests: tests/test_core_value_types.py

from __future__ import annotations

import math

from ea_node_editor.nodes.core_data_types import GRAPH_DATA_TYPE_ID
from ea_node_editor.nodes.plugin_contracts import (
    PluginContractManifest,
)
from ea_node_editor.runtime_contracts import (
    DataTypeSpec,
    ImageValue,
)

COREX_CORE_VALUE_OWNER_ID = "corex.core_values"
COREX_CORE_VALUE_OWNER_VERSION = "1"

COMPLEX_DATA_TYPE_ID = "COREX.DataTypes.Complex"
COLOR_DATA_TYPE_ID = "COREX.DataTypes.Color"
IMAGE_DATA_TYPE_ID = "COREX.DataTypes.Image"




def _is_finite_float(value: object) -> bool:
    return type(value) is float and math.isfinite(value)


def is_complex_payload(value: object) -> bool:
    return (
        type(value) is dict
        and set(value) == {"real", "imag"}
        and _is_finite_float(value["real"])
        and _is_finite_float(value["imag"])
    )


def is_color_payload(value: object) -> bool:
    return (
        type(value) is dict
        and set(value) == {"R", "G", "B", "A", "IsValid"}
        and all(_is_finite_float(value[channel]) for channel in ("R", "G", "B", "A"))
        and type(value["IsValid"]) is bool
    )


def is_image_value(value: object) -> bool:
    return type(value) is ImageValue


COREX_CORE_VALUE_DATA_TYPES = (
    DataTypeSpec(
        COMPLEX_DATA_TYPE_ID,
        "Complex",
        "scalar",
        is_complex_payload,
        parents=(GRAPH_DATA_TYPE_ID,),
        carriers=frozenset({"inline"}),
        persistence="inline",
    ),
    DataTypeSpec(
        COLOR_DATA_TYPE_ID,
        "Color",
        "viewer",
        is_color_payload,
        parents=(GRAPH_DATA_TYPE_ID,),
        carriers=frozenset({"inline"}),
        persistence="inline",
    ),
    DataTypeSpec(
        IMAGE_DATA_TYPE_ID,
        "Image",
        "viewer",
        is_image_value,
        parents=(GRAPH_DATA_TYPE_ID,),
        carriers=frozenset({"inline"}),
        persistence="inline",
    ),
)

















COREX_CORE_VALUE_CONTRACT_MANIFEST = PluginContractManifest(
    data_types=COREX_CORE_VALUE_DATA_TYPES,
)

__all__ = [
    "COLOR_DATA_TYPE_ID",
    "COMPLEX_DATA_TYPE_ID",
    "IMAGE_DATA_TYPE_ID",
    "COREX_CORE_VALUE_CONTRACT_MANIFEST",
    "COREX_CORE_VALUE_DATA_TYPES",
    "COREX_CORE_VALUE_OWNER_ID",
    "COREX_CORE_VALUE_OWNER_VERSION",
    "is_color_payload",
    "is_complex_payload",
    "is_image_value",
]

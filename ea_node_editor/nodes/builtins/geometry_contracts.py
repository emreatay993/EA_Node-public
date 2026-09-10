# Purpose: Declare strict COREX geometry interface contracts.
# Map: subsystems/nodes_registry_builtins.md
# Tests: tests/test_geometry_contracts.py

from __future__ import annotations

from dataclasses import replace

from ea_node_editor.nodes.core_data_types import (
    CLIPPABLE_GRAPH_DATA_TYPE_ID,
    GRAPH_DATA_TYPE_ID,
)
from ea_node_editor.nodes.plugin_contracts import PluginContractManifest
from ea_node_editor.runtime_contracts import DataTypeSpec

COREX_GEOMETRY_CONTRACTS_OWNER_ID = "corex.geometry_contracts"
COREX_GEOMETRY_CONTRACTS_OWNER_VERSION = "1"

SPATIAL_OBJECT_DATA_TYPE_ID = "COREX.Common.ISpatialObject"
MEASURABLE_DATA_TYPE_ID = "COREX.Common.IMeasurable"
MORPHABLE_DATA_TYPE_ID = "COREX.Common.IMorphable"
PART_DATA_TYPE_ID = "COREX.Geometry.IPart"
ASSEMBLY_DATA_TYPE_ID = "COREX.Geometry.IAssembly"
BODY_DATA_TYPE_ID = "COREX.Geometry.IBody"
BOX_BODY_DATA_TYPE_ID = "COREX.Geometry.IBoxBody"
DEFORMED_BOX_BODY_DATA_TYPE_ID = "COREX.Geometry.IDeformedBoxBody"
SURFACE_DATA_TYPE_ID = "COREX.Geometry.ISurface"
CURVE_DATA_TYPE_ID = "COREX.Geometry.ICurve"
ARC_DATA_TYPE_ID = "COREX.Geometry.IArc"
B_SPLINE_DATA_TYPE_ID = "COREX.Geometry.IBSpline"
CIRCLE_DATA_TYPE_ID = "COREX.Geometry.ICircle"
COORDINATE_SYSTEM_DATA_TYPE_ID = "COREX.DataTypes.ICoordinateSystem"
ELLIPSE_DATA_TYPE_ID = "COREX.Geometry.IEllipse"
FACET_CURVE_DATA_TYPE_ID = "COREX.Geometry.IFacetCurve"
FACET_SURFACE_DATA_TYPE_ID = "COREX.Geometry.IFacetSurface"
FINITE_LINE_DATA_TYPE_ID = "COREX.Geometry.IFiniteLine"
INFINITE_LINE_DATA_TYPE_ID = "COREX.Geometry.IInfiniteLine"
PIPE_CURVE_DATA_TYPE_ID = "COREX.Geometry.IPipeCurve"
POLY_CURVE_DATA_TYPE_ID = "COREX.Geometry.IPolyCurve"
POLYLINE_DATA_TYPE_ID = "COREX.Geometry.IPolyline"
RECTANGLE_DATA_TYPE_ID = "COREX.Geometry.IRectangle"
SIMPLE_TREE_CONNECTOR_DATA_TYPE_ID = "COREX.Geometry.ISimpleTreeConnector"
SUBD_DATA_TYPE_ID = "COREX.Subdiv.ISubD"
TRIMMED_SURFACE_DATA_TYPE_ID = "COREX.Geometry.ITrimmedSurface"
UNTRIMMED_SURFACE_DATA_TYPE_ID = "COREX.Geometry.IUntrimmedSurface"

_HANDLE_CARRIER = frozenset({"handle"})

COREX_GEOMETRY_DATA_TYPES = (
    DataTypeSpec(
        SPATIAL_OBJECT_DATA_TYPE_ID,
        "Spatial Object",
        "engineering",
        lambda _value: False,
        parents=(GRAPH_DATA_TYPE_ID,),
        abstract=True,
        carriers=_HANDLE_CARRIER,
        persistence="never",
        sensitivity="normal",
        payload_schema_version=1,
        implementation_version="1",
    ),
    DataTypeSpec(
        MEASURABLE_DATA_TYPE_ID,
        "Measurable",
        "engineering",
        lambda _value: False,
        parents=(GRAPH_DATA_TYPE_ID,),
        abstract=True,
        carriers=_HANDLE_CARRIER,
        persistence="never",
        sensitivity="normal",
        payload_schema_version=1,
        implementation_version="1",
    ),
    DataTypeSpec(
        MORPHABLE_DATA_TYPE_ID,
        "Morphable",
        "engineering",
        lambda _value: False,
        parents=(SPATIAL_OBJECT_DATA_TYPE_ID,),
        abstract=True,
        carriers=_HANDLE_CARRIER,
        persistence="never",
        sensitivity="normal",
        payload_schema_version=1,
        implementation_version="1",
    ),
    DataTypeSpec(
        PART_DATA_TYPE_ID,
        "Part",
        "engineering",
        lambda _value: False,
        parents=(
            SPATIAL_OBJECT_DATA_TYPE_ID,
            MEASURABLE_DATA_TYPE_ID,
            CLIPPABLE_GRAPH_DATA_TYPE_ID,
        ),
        abstract=True,
        carriers=_HANDLE_CARRIER,
        persistence="never",
        sensitivity="normal",
        payload_schema_version=1,
        implementation_version="1",
    ),
    DataTypeSpec(
        BODY_DATA_TYPE_ID,
        "Body",
        "engineering",
        lambda _value: False,
        parents=(PART_DATA_TYPE_ID, MORPHABLE_DATA_TYPE_ID),
        abstract=True,
        carriers=_HANDLE_CARRIER,
        persistence="never",
        sensitivity="normal",
        payload_schema_version=1,
        implementation_version="1",
    ),
    DataTypeSpec(
        SURFACE_DATA_TYPE_ID,
        "Surface",
        "engineering",
        lambda _value: False,
        parents=(
            SPATIAL_OBJECT_DATA_TYPE_ID,
            MEASURABLE_DATA_TYPE_ID,
            CLIPPABLE_GRAPH_DATA_TYPE_ID,
        ),
        abstract=True,
        carriers=_HANDLE_CARRIER,
        persistence="never",
        sensitivity="normal",
        payload_schema_version=1,
        implementation_version="1",
    ),
    DataTypeSpec(
        CURVE_DATA_TYPE_ID,
        "Curve",
        "engineering",
        lambda _value: False,
        parents=(
            MEASURABLE_DATA_TYPE_ID,
            CLIPPABLE_GRAPH_DATA_TYPE_ID,
            MORPHABLE_DATA_TYPE_ID,
        ),
        abstract=True,
        carriers=_HANDLE_CARRIER,
        persistence="never",
        sensitivity="normal",
        payload_schema_version=1,
        implementation_version="1",
    ),
)

COREX_GEOMETRY_CONTRACT_MANIFEST = PluginContractManifest(
    data_types=COREX_GEOMETRY_DATA_TYPES,
)

COREX_GEOMETRY_ASSEMBLY_CANDIDATE_DATA_TYPES = (
    *COREX_GEOMETRY_DATA_TYPES,
    DataTypeSpec(
        ASSEMBLY_DATA_TYPE_ID,
        "Assembly",
        "engineering",
        lambda _value: False,
        parents=(PART_DATA_TYPE_ID,),
        abstract=True,
        carriers=_HANDLE_CARRIER,
        persistence="never",
        sensitivity="normal",
        payload_schema_version=1,
        implementation_version="1",
    ),
)

COREX_GEOMETRY_ASSEMBLY_CANDIDATE_CONTRACT_MANIFEST = PluginContractManifest(
    data_types=COREX_GEOMETRY_ASSEMBLY_CANDIDATE_DATA_TYPES,
)

COREX_GEOMETRY_CURVE_SUBTYPES_CANDIDATE_DATA_TYPES = (
    *COREX_GEOMETRY_ASSEMBLY_CANDIDATE_DATA_TYPES,
    DataTypeSpec(
        ARC_DATA_TYPE_ID,
        "Arc",
        "engineering",
        lambda _value: False,
        parents=(CURVE_DATA_TYPE_ID,),
        abstract=True,
        carriers=_HANDLE_CARRIER,
        persistence="never",
        sensitivity="normal",
        payload_schema_version=1,
        implementation_version="1",
    ),
    DataTypeSpec(
        CIRCLE_DATA_TYPE_ID,
        "Circle",
        "engineering",
        lambda _value: False,
        parents=(CURVE_DATA_TYPE_ID,),
        abstract=True,
        carriers=_HANDLE_CARRIER,
        persistence="never",
        sensitivity="normal",
        payload_schema_version=1,
        implementation_version="1",
    ),
    DataTypeSpec(
        ELLIPSE_DATA_TYPE_ID,
        "Ellipse",
        "engineering",
        lambda _value: False,
        parents=(CURVE_DATA_TYPE_ID,),
        abstract=True,
        carriers=_HANDLE_CARRIER,
        persistence="never",
        sensitivity="normal",
        payload_schema_version=1,
        implementation_version="1",
    ),
    DataTypeSpec(
        FINITE_LINE_DATA_TYPE_ID,
        "Finite Line",
        "engineering",
        lambda _value: False,
        parents=(CURVE_DATA_TYPE_ID,),
        abstract=True,
        carriers=_HANDLE_CARRIER,
        persistence="never",
        sensitivity="normal",
        payload_schema_version=1,
        implementation_version="1",
    ),
)

COREX_GEOMETRY_CURVE_SUBTYPES_CANDIDATE_CONTRACT_MANIFEST = PluginContractManifest(
    data_types=COREX_GEOMETRY_CURVE_SUBTYPES_CANDIDATE_DATA_TYPES,
)

COREX_GEOMETRY_BODY_SUBTYPES_CANDIDATE_DATA_TYPES = (
    *COREX_GEOMETRY_CURVE_SUBTYPES_CANDIDATE_DATA_TYPES,
    DataTypeSpec(
        BOX_BODY_DATA_TYPE_ID,
        "Box Body",
        "engineering",
        lambda _value: False,
        parents=(BODY_DATA_TYPE_ID,),
        abstract=True,
        carriers=_HANDLE_CARRIER,
        persistence="never",
        sensitivity="normal",
        payload_schema_version=1,
        implementation_version="1",
    ),
    DataTypeSpec(
        DEFORMED_BOX_BODY_DATA_TYPE_ID,
        "Deformed Box Body",
        "engineering",
        lambda _value: False,
        parents=(BODY_DATA_TYPE_ID,),
        abstract=True,
        carriers=_HANDLE_CARRIER,
        persistence="never",
        sensitivity="normal",
        payload_schema_version=1,
        implementation_version="1",
    ),
)

COREX_GEOMETRY_BODY_SUBTYPES_CANDIDATE_CONTRACT_MANIFEST = PluginContractManifest(
    data_types=COREX_GEOMETRY_BODY_SUBTYPES_CANDIDATE_DATA_TYPES,
)

_GEOMETRY_CLOSURE_SUFFIX_FACTS = (
    (B_SPLINE_DATA_TYPE_ID, "B-Spline", (CURVE_DATA_TYPE_ID,)),
    (FACET_CURVE_DATA_TYPE_ID, "Facet Curve", (CURVE_DATA_TYPE_ID,)),
    (INFINITE_LINE_DATA_TYPE_ID, "Infinite Line", (CURVE_DATA_TYPE_ID,)),
    (PIPE_CURVE_DATA_TYPE_ID, "Pipe Curve", (CURVE_DATA_TYPE_ID,)),
    (POLY_CURVE_DATA_TYPE_ID, "Poly Curve", (CURVE_DATA_TYPE_ID,)),
    (POLYLINE_DATA_TYPE_ID, "Polyline", (CURVE_DATA_TYPE_ID,)),
    (RECTANGLE_DATA_TYPE_ID, "Rectangle", (POLYLINE_DATA_TYPE_ID,)),
    (TRIMMED_SURFACE_DATA_TYPE_ID, "Trimmed Surface", (SURFACE_DATA_TYPE_ID,)),
    (
        UNTRIMMED_SURFACE_DATA_TYPE_ID,
        "Untrimmed Surface",
        (SURFACE_DATA_TYPE_ID,),
    ),
    (
        FACET_SURFACE_DATA_TYPE_ID,
        "Facet Surface",
        (UNTRIMMED_SURFACE_DATA_TYPE_ID,),
    ),
    (
        SIMPLE_TREE_CONNECTOR_DATA_TYPE_ID,
        "Simple Tree Connector",
        (SPATIAL_OBJECT_DATA_TYPE_ID,),
    ),
    (
        SUBD_DATA_TYPE_ID,
        "SubD",
        (MEASURABLE_DATA_TYPE_ID, MORPHABLE_DATA_TYPE_ID),
    ),
)

COREX_GEOMETRY_CLOSURE_CANDIDATE_DATA_TYPES = (
    *COREX_GEOMETRY_BODY_SUBTYPES_CANDIDATE_DATA_TYPES,
    *(
        DataTypeSpec(
            type_id,
            display_name,
            "engineering",
            lambda _value: False,
            parents=parents,
            abstract=True,
            carriers=_HANDLE_CARRIER,
            persistence="never",
            sensitivity="normal",
            payload_schema_version=1,
            implementation_version="1",
        )
        for type_id, display_name, parents in _GEOMETRY_CLOSURE_SUFFIX_FACTS
    ),
)

COREX_GEOMETRY_CLOSURE_CANDIDATE_CONTRACT_MANIFEST = PluginContractManifest(
    data_types=COREX_GEOMETRY_CLOSURE_CANDIDATE_DATA_TYPES,
)

COREX_GEOMETRY_COORDINATE_SYSTEM_CANDIDATE_DATA_TYPES = (
    *COREX_GEOMETRY_CLOSURE_CANDIDATE_DATA_TYPES,
    DataTypeSpec(
        COORDINATE_SYSTEM_DATA_TYPE_ID,
        "Coordinate System",
        "engineering",
        lambda _value: False,
        parents=(SPATIAL_OBJECT_DATA_TYPE_ID,),
        abstract=True,
        carriers=_HANDLE_CARRIER,
        persistence="never",
        sensitivity="normal",
        payload_schema_version=1,
        implementation_version="1",
    ),
)

COREX_GEOMETRY_COORDINATE_SYSTEM_CANDIDATE_CONTRACT_MANIFEST = PluginContractManifest(
    data_types=COREX_GEOMETRY_COORDINATE_SYSTEM_CANDIDATE_DATA_TYPES,
)

COREX_GEOMETRY_COORDINATE_SYSTEM_VALUE_CANDIDATE_DATA_TYPES = tuple(
    replace(spec, carriers=frozenset({"handle", "inline"}))
    if spec.type_id
    in (
        SPATIAL_OBJECT_DATA_TYPE_ID,
        COORDINATE_SYSTEM_DATA_TYPE_ID,
    )
    else spec
    for spec in COREX_GEOMETRY_COORDINATE_SYSTEM_CANDIDATE_DATA_TYPES
)

COREX_GEOMETRY_COORDINATE_SYSTEM_VALUE_CANDIDATE_CONTRACT_MANIFEST = (
    PluginContractManifest(
        data_types=COREX_GEOMETRY_COORDINATE_SYSTEM_VALUE_CANDIDATE_DATA_TYPES,
    )
)

__all__ = [
    "ARC_DATA_TYPE_ID",
    "ASSEMBLY_DATA_TYPE_ID",
    "B_SPLINE_DATA_TYPE_ID",
    "BODY_DATA_TYPE_ID",
    "BOX_BODY_DATA_TYPE_ID",
    "CIRCLE_DATA_TYPE_ID",
    "COORDINATE_SYSTEM_DATA_TYPE_ID",
    "CURVE_DATA_TYPE_ID",
    "DEFORMED_BOX_BODY_DATA_TYPE_ID",
    "ELLIPSE_DATA_TYPE_ID",
    "FACET_CURVE_DATA_TYPE_ID",
    "FACET_SURFACE_DATA_TYPE_ID",
    "FINITE_LINE_DATA_TYPE_ID",
    "INFINITE_LINE_DATA_TYPE_ID",
    "MEASURABLE_DATA_TYPE_ID",
    "MORPHABLE_DATA_TYPE_ID",
    "PART_DATA_TYPE_ID",
    "PIPE_CURVE_DATA_TYPE_ID",
    "POLY_CURVE_DATA_TYPE_ID",
    "POLYLINE_DATA_TYPE_ID",
    "RECTANGLE_DATA_TYPE_ID",
    "SIMPLE_TREE_CONNECTOR_DATA_TYPE_ID",
    "SPATIAL_OBJECT_DATA_TYPE_ID",
    "SUBD_DATA_TYPE_ID",
    "SURFACE_DATA_TYPE_ID",
    "COREX_GEOMETRY_ASSEMBLY_CANDIDATE_CONTRACT_MANIFEST",
    "COREX_GEOMETRY_ASSEMBLY_CANDIDATE_DATA_TYPES",
    "COREX_GEOMETRY_BODY_SUBTYPES_CANDIDATE_CONTRACT_MANIFEST",
    "COREX_GEOMETRY_BODY_SUBTYPES_CANDIDATE_DATA_TYPES",
    "COREX_GEOMETRY_CLOSURE_CANDIDATE_CONTRACT_MANIFEST",
    "COREX_GEOMETRY_CLOSURE_CANDIDATE_DATA_TYPES",
    "COREX_GEOMETRY_COORDINATE_SYSTEM_CANDIDATE_CONTRACT_MANIFEST",
    "COREX_GEOMETRY_COORDINATE_SYSTEM_CANDIDATE_DATA_TYPES",
    "COREX_GEOMETRY_COORDINATE_SYSTEM_VALUE_CANDIDATE_CONTRACT_MANIFEST",
    "COREX_GEOMETRY_COORDINATE_SYSTEM_VALUE_CANDIDATE_DATA_TYPES",
    "COREX_GEOMETRY_CONTRACT_MANIFEST",
    "COREX_GEOMETRY_CONTRACTS_OWNER_ID",
    "COREX_GEOMETRY_CONTRACTS_OWNER_VERSION",
    "COREX_GEOMETRY_CURVE_SUBTYPES_CANDIDATE_CONTRACT_MANIFEST",
    "COREX_GEOMETRY_CURVE_SUBTYPES_CANDIDATE_DATA_TYPES",
    "COREX_GEOMETRY_DATA_TYPES",
    "TRIMMED_SURFACE_DATA_TYPE_ID",
    "UNTRIMMED_SURFACE_DATA_TYPE_ID",
]

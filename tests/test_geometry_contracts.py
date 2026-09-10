from __future__ import annotations

from dataclasses import replace

import pytest

from ea_node_editor.nodes.builtins.ai_ml_contracts import (
    COREX_AI_ML_CONTRACT_MANIFEST,
    COREX_AI_ML_CONTRACTS_OWNER_ID,
    COREX_AI_ML_CONTRACTS_OWNER_VERSION,
)
from ea_node_editor.nodes.builtins.geometry_contracts import (
    ARC_DATA_TYPE_ID,
    ASSEMBLY_DATA_TYPE_ID,
    B_SPLINE_DATA_TYPE_ID,
    BODY_DATA_TYPE_ID,
    BOX_BODY_DATA_TYPE_ID,
    CIRCLE_DATA_TYPE_ID,
    COORDINATE_SYSTEM_DATA_TYPE_ID,
    CURVE_DATA_TYPE_ID,
    DEFORMED_BOX_BODY_DATA_TYPE_ID,
    ELLIPSE_DATA_TYPE_ID,
    FACET_CURVE_DATA_TYPE_ID,
    FACET_SURFACE_DATA_TYPE_ID,
    FINITE_LINE_DATA_TYPE_ID,
    INFINITE_LINE_DATA_TYPE_ID,
    MEASURABLE_DATA_TYPE_ID,
    MORPHABLE_DATA_TYPE_ID,
    PART_DATA_TYPE_ID,
    PIPE_CURVE_DATA_TYPE_ID,
    POLY_CURVE_DATA_TYPE_ID,
    POLYLINE_DATA_TYPE_ID,
    RECTANGLE_DATA_TYPE_ID,
    SIMPLE_TREE_CONNECTOR_DATA_TYPE_ID,
    SPATIAL_OBJECT_DATA_TYPE_ID,
    SUBD_DATA_TYPE_ID,
    SURFACE_DATA_TYPE_ID,
    COREX_GEOMETRY_ASSEMBLY_CANDIDATE_CONTRACT_MANIFEST,
    COREX_GEOMETRY_ASSEMBLY_CANDIDATE_DATA_TYPES,
    COREX_GEOMETRY_BODY_SUBTYPES_CANDIDATE_CONTRACT_MANIFEST,
    COREX_GEOMETRY_BODY_SUBTYPES_CANDIDATE_DATA_TYPES,
    COREX_GEOMETRY_CLOSURE_CANDIDATE_CONTRACT_MANIFEST,
    COREX_GEOMETRY_CLOSURE_CANDIDATE_DATA_TYPES,
    COREX_GEOMETRY_COORDINATE_SYSTEM_CANDIDATE_CONTRACT_MANIFEST,
    COREX_GEOMETRY_COORDINATE_SYSTEM_CANDIDATE_DATA_TYPES,
    COREX_GEOMETRY_COORDINATE_SYSTEM_VALUE_CANDIDATE_CONTRACT_MANIFEST,
    COREX_GEOMETRY_COORDINATE_SYSTEM_VALUE_CANDIDATE_DATA_TYPES,
    COREX_GEOMETRY_CONTRACT_MANIFEST,
    COREX_GEOMETRY_CONTRACTS_OWNER_ID,
    COREX_GEOMETRY_CONTRACTS_OWNER_VERSION,
    COREX_GEOMETRY_CURVE_SUBTYPES_CANDIDATE_CONTRACT_MANIFEST,
    COREX_GEOMETRY_CURVE_SUBTYPES_CANDIDATE_DATA_TYPES,
    COREX_GEOMETRY_DATA_TYPES,
    TRIMMED_SURFACE_DATA_TYPE_ID,
    UNTRIMMED_SURFACE_DATA_TYPE_ID,
)
from ea_node_editor.nodes.builtins.mesh_contracts import (
    COREX_DECONSTRUCT_MESH_FACE_CANDIDATE_CONTRACT_MANIFEST,
    COREX_MESH_CONTRACTS_OWNER_ID,
    COREX_MESH_CONTRACTS_OWNER_VERSION,
)
from ea_node_editor.nodes.builtins.spatial_values import (
    COREX_SPATIAL_VALUES_OWNER_ID,
    COREX_SPATIAL_VALUES_OWNER_VERSION,
    COREX_SPATIAL_VALUES_VECTOR_LENGTH_CANDIDATE_CONTRACT_MANIFEST,
)
from ea_node_editor.nodes.core_data_types import (
    CLIPPABLE_GRAPH_DATA_TYPE_ID,
    CORE_DATA_TYPE_OWNER_ID,
    ENGINEERING_SCENE_DATA_TYPE_ID,
    GRAPH_DATA_TYPE_ID,
)
from ea_node_editor.nodes.bootstrap import build_builtin_registry
from ea_node_editor.nodes.plugin_contracts import PluginContractManifest
from ea_node_editor.nodes.registry import NodeRegistry
from ea_node_editor.runtime_contracts import (
    DataTypeCatalogError,
    RuntimeHandleRef,
    TypedInlineValue,
)

_EXPECTED_TYPE_IDS = (
    "COREX.Common.ISpatialObject",
    "COREX.Common.IMeasurable",
    "COREX.Common.IMorphable",
    "COREX.Geometry.IPart",
    "COREX.Geometry.IBody",
    "COREX.Geometry.ISurface",
    "COREX.Geometry.ICurve",
)

_EXPECTED_ASSEMBLY_CANDIDATE_TYPE_IDS = (
    *_EXPECTED_TYPE_IDS,
    "COREX.Geometry.IAssembly",
)

_EXPECTED_CURVE_SUBTYPE_TYPE_IDS = (
    "COREX.Geometry.IArc",
    "COREX.Geometry.ICircle",
    "COREX.Geometry.IEllipse",
    "COREX.Geometry.IFiniteLine",
)

_EXPECTED_CURVE_SUBTYPES_CANDIDATE_TYPE_IDS = (
    *_EXPECTED_ASSEMBLY_CANDIDATE_TYPE_IDS,
    *_EXPECTED_CURVE_SUBTYPE_TYPE_IDS,
)

_EXPECTED_BODY_SUBTYPE_TYPE_IDS = (
    "COREX.Geometry.IBoxBody",
    "COREX.Geometry.IDeformedBoxBody",
)

_EXPECTED_BODY_SUBTYPES_CANDIDATE_TYPE_IDS = (
    *_EXPECTED_CURVE_SUBTYPES_CANDIDATE_TYPE_IDS,
    *_EXPECTED_BODY_SUBTYPE_TYPE_IDS,
)

_EXPECTED_GEOMETRY_CLOSURE_SUFFIX = (
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

_EXPECTED_GEOMETRY_CLOSURE_CANDIDATE_TYPE_IDS = (
    *_EXPECTED_BODY_SUBTYPES_CANDIDATE_TYPE_IDS,
    *(
        type_id
        for type_id, _display_name, _parents in _EXPECTED_GEOMETRY_CLOSURE_SUFFIX
    ),
)

_EXPECTED_COORDINATE_SYSTEM_CANDIDATE_TYPE_IDS = (
    *_EXPECTED_GEOMETRY_CLOSURE_CANDIDATE_TYPE_IDS,
    "COREX.DataTypes.ICoordinateSystem",
)


def _registry(
    manifest: PluginContractManifest = COREX_GEOMETRY_CONTRACT_MANIFEST,
) -> NodeRegistry:
    registry = NodeRegistry()
    registry.register_plugin_bundle(
        manifest,
        (),
        owner_id=COREX_GEOMETRY_CONTRACTS_OWNER_ID,
        owner_version=COREX_GEOMETRY_CONTRACTS_OWNER_VERSION,
    )
    return registry


def _handle(type_id: str) -> RuntimeHandleRef:
    return RuntimeHandleRef(
        data_type_id=type_id,
        schema_version=1,
        handle_id="abstract-geometry-test",
        kind="test.abstract_geometry",
        owner_scope="run:test",
        worker_generation=1,
        metadata={},
    )




def test_exact_abstract_handle_specs_have_the_reduced_direct_parent_dag() -> None:
    expected = (
        (
            SPATIAL_OBJECT_DATA_TYPE_ID,
            "Spatial Object",
            (GRAPH_DATA_TYPE_ID,),
        ),
        (MEASURABLE_DATA_TYPE_ID, "Measurable", (GRAPH_DATA_TYPE_ID,)),
        (
            MORPHABLE_DATA_TYPE_ID,
            "Morphable",
            (SPATIAL_OBJECT_DATA_TYPE_ID,),
        ),
        (
            PART_DATA_TYPE_ID,
            "Part",
            (
                SPATIAL_OBJECT_DATA_TYPE_ID,
                MEASURABLE_DATA_TYPE_ID,
                CLIPPABLE_GRAPH_DATA_TYPE_ID,
            ),
        ),
        (
            BODY_DATA_TYPE_ID,
            "Body",
            (PART_DATA_TYPE_ID, MORPHABLE_DATA_TYPE_ID),
        ),
        (
            SURFACE_DATA_TYPE_ID,
            "Surface",
            (
                SPATIAL_OBJECT_DATA_TYPE_ID,
                MEASURABLE_DATA_TYPE_ID,
                CLIPPABLE_GRAPH_DATA_TYPE_ID,
            ),
        ),
        (
            CURVE_DATA_TYPE_ID,
            "Curve",
            (
                MEASURABLE_DATA_TYPE_ID,
                CLIPPABLE_GRAPH_DATA_TYPE_ID,
                MORPHABLE_DATA_TYPE_ID,
            ),
        ),
    )
    assert [
        (
            spec.type_id,
            spec.display_name,
            spec.parents,
            spec.family_id,
            spec.abstract,
            spec.carriers,
            spec.persistence,
            spec.sensitivity,
            spec.payload_schema_version,
            spec.implementation_version,
            spec.description,
            spec.capabilities,
            spec.coerce_untyped_input,
        )
        for spec in COREX_GEOMETRY_DATA_TYPES
    ] == [
        (
            type_id,
            display_name,
            parents,
            "engineering",
            True,
            frozenset({"handle"}),
            "never",
            "normal",
            1,
            "1",
            "",
            frozenset(),
            None,
        )
        for type_id, display_name, parents in expected
    ]

    curve_subtype_specs = (
        (ARC_DATA_TYPE_ID, "Arc"),
        (CIRCLE_DATA_TYPE_ID, "Circle"),
        (ELLIPSE_DATA_TYPE_ID, "Ellipse"),
        (FINITE_LINE_DATA_TYPE_ID, "Finite Line"),
    )
    assert [
        (
            spec.type_id,
            spec.display_name,
            spec.family_id,
            spec.parents,
            spec.abstract,
            spec.carriers,
            spec.persistence,
            spec.sensitivity,
            spec.payload_schema_version,
            spec.implementation_version,
            spec.description,
            spec.capabilities,
            spec.coerce_untyped_input,
        )
        for spec in COREX_GEOMETRY_CURVE_SUBTYPES_CANDIDATE_DATA_TYPES[-4:]
    ] == [
        (
            type_id,
            display_name,
            "engineering",
            (CURVE_DATA_TYPE_ID,),
            True,
            frozenset({"handle"}),
            "never",
            "normal",
            1,
            "1",
            "",
            frozenset(),
            None,
        )
        for type_id, display_name in curve_subtype_specs
    ]

    body_subtype_specs = (
        (BOX_BODY_DATA_TYPE_ID, "Box Body"),
        (DEFORMED_BOX_BODY_DATA_TYPE_ID, "Deformed Box Body"),
    )
    assert [
        (
            spec.type_id,
            spec.display_name,
            spec.family_id,
            spec.parents,
            spec.abstract,
            spec.carriers,
            spec.persistence,
            spec.sensitivity,
            spec.payload_schema_version,
            spec.implementation_version,
            spec.description,
            spec.capabilities,
            spec.coerce_untyped_input,
        )
        for spec in COREX_GEOMETRY_BODY_SUBTYPES_CANDIDATE_DATA_TYPES[-2:]
    ] == [
        (
            type_id,
            display_name,
            "engineering",
            (BODY_DATA_TYPE_ID,),
            True,
            frozenset({"handle"}),
            "never",
            "normal",
            1,
            "1",
            "",
            frozenset(),
            None,
        )
        for type_id, display_name in body_subtype_specs
    ]

    assert [
        (
            spec.type_id,
            spec.display_name,
            spec.family_id,
            spec.parents,
            spec.abstract,
            spec.carriers,
            spec.persistence,
            spec.sensitivity,
            spec.payload_schema_version,
            spec.implementation_version,
            spec.description,
            spec.capabilities,
            spec.coerce_untyped_input,
        )
        for spec in COREX_GEOMETRY_CLOSURE_CANDIDATE_DATA_TYPES[-12:]
    ] == [
        (
            type_id,
            display_name,
            "engineering",
            parents,
            True,
            frozenset({"handle"}),
            "never",
            "normal",
            1,
            "1",
            "",
            frozenset(),
            None,
        )
        for type_id, display_name, parents in _EXPECTED_GEOMETRY_CLOSURE_SUFFIX
    ]

    coordinate_system_spec = COREX_GEOMETRY_COORDINATE_SYSTEM_CANDIDATE_DATA_TYPES[-1]
    assert (
        coordinate_system_spec.type_id,
        coordinate_system_spec.display_name,
        coordinate_system_spec.family_id,
        coordinate_system_spec.parents,
        coordinate_system_spec.abstract,
        coordinate_system_spec.carriers,
        coordinate_system_spec.persistence,
        coordinate_system_spec.sensitivity,
        coordinate_system_spec.payload_schema_version,
        coordinate_system_spec.implementation_version,
        coordinate_system_spec.description,
        coordinate_system_spec.capabilities,
        coordinate_system_spec.coerce_untyped_input,
    ) == (
        COORDINATE_SYSTEM_DATA_TYPE_ID,
        "Coordinate System",
        "engineering",
        (SPATIAL_OBJECT_DATA_TYPE_ID,),
        True,
        frozenset({"handle"}),
        "never",
        "normal",
        1,
        "1",
        "",
        frozenset(),
        None,
    )

    predecessor_by_id = {
        spec.type_id: spec
        for spec in COREX_GEOMETRY_COORDINATE_SYSTEM_CANDIDATE_DATA_TYPES
    }
    successor_by_id = {
        spec.type_id: spec
        for spec in COREX_GEOMETRY_COORDINATE_SYSTEM_VALUE_CANDIDATE_DATA_TYPES
    }
    assert {
        type_id
        for type_id, successor in successor_by_id.items()
        if successor is not predecessor_by_id[type_id]
    } == {
        SPATIAL_OBJECT_DATA_TYPE_ID,
        COORDINATE_SYSTEM_DATA_TYPE_ID,
    }
    assert successor_by_id[SPATIAL_OBJECT_DATA_TYPE_ID].carriers == frozenset(
        {"handle", "inline"}
    )
    assert successor_by_id[COORDINATE_SYSTEM_DATA_TYPE_ID].carriers == frozenset(
        {"handle", "inline"}
    )
    assert all(
        spec.carriers == frozenset({"handle"})
        for type_id, spec in successor_by_id.items()
        if type_id
        not in {
            SPATIAL_OBJECT_DATA_TYPE_ID,
            COORDINATE_SYSTEM_DATA_TYPE_ID,
        }
    )


def test_geometry_dag_assignability_and_clippable_children_are_exact() -> None:
    registry = _registry(COREX_GEOMETRY_CLOSURE_CANDIDATE_CONTRACT_MANIFEST)
    catalog = registry.data_types
    checked_targets = {
        GRAPH_DATA_TYPE_ID,
        CLIPPABLE_GRAPH_DATA_TYPE_ID,
        *_EXPECTED_GEOMETRY_CLOSURE_CANDIDATE_TYPE_IDS,
    }
    expected_assignable_targets = {
        SPATIAL_OBJECT_DATA_TYPE_ID: {
            SPATIAL_OBJECT_DATA_TYPE_ID,
            GRAPH_DATA_TYPE_ID,
        },
        MEASURABLE_DATA_TYPE_ID: {
            MEASURABLE_DATA_TYPE_ID,
            GRAPH_DATA_TYPE_ID,
        },
        MORPHABLE_DATA_TYPE_ID: {
            MORPHABLE_DATA_TYPE_ID,
            SPATIAL_OBJECT_DATA_TYPE_ID,
            GRAPH_DATA_TYPE_ID,
        },
        PART_DATA_TYPE_ID: {
            PART_DATA_TYPE_ID,
            SPATIAL_OBJECT_DATA_TYPE_ID,
            MEASURABLE_DATA_TYPE_ID,
            CLIPPABLE_GRAPH_DATA_TYPE_ID,
            GRAPH_DATA_TYPE_ID,
        },
        BODY_DATA_TYPE_ID: {
            BODY_DATA_TYPE_ID,
            PART_DATA_TYPE_ID,
            MORPHABLE_DATA_TYPE_ID,
            SPATIAL_OBJECT_DATA_TYPE_ID,
            MEASURABLE_DATA_TYPE_ID,
            CLIPPABLE_GRAPH_DATA_TYPE_ID,
            GRAPH_DATA_TYPE_ID,
        },
        BOX_BODY_DATA_TYPE_ID: {
            BOX_BODY_DATA_TYPE_ID,
            BODY_DATA_TYPE_ID,
            PART_DATA_TYPE_ID,
            MORPHABLE_DATA_TYPE_ID,
            SPATIAL_OBJECT_DATA_TYPE_ID,
            MEASURABLE_DATA_TYPE_ID,
            CLIPPABLE_GRAPH_DATA_TYPE_ID,
            GRAPH_DATA_TYPE_ID,
        },
        DEFORMED_BOX_BODY_DATA_TYPE_ID: {
            DEFORMED_BOX_BODY_DATA_TYPE_ID,
            BODY_DATA_TYPE_ID,
            PART_DATA_TYPE_ID,
            MORPHABLE_DATA_TYPE_ID,
            SPATIAL_OBJECT_DATA_TYPE_ID,
            MEASURABLE_DATA_TYPE_ID,
            CLIPPABLE_GRAPH_DATA_TYPE_ID,
            GRAPH_DATA_TYPE_ID,
        },
        SURFACE_DATA_TYPE_ID: {
            SURFACE_DATA_TYPE_ID,
            SPATIAL_OBJECT_DATA_TYPE_ID,
            MEASURABLE_DATA_TYPE_ID,
            CLIPPABLE_GRAPH_DATA_TYPE_ID,
            GRAPH_DATA_TYPE_ID,
        },
        CURVE_DATA_TYPE_ID: {
            CURVE_DATA_TYPE_ID,
            MORPHABLE_DATA_TYPE_ID,
            SPATIAL_OBJECT_DATA_TYPE_ID,
            MEASURABLE_DATA_TYPE_ID,
            CLIPPABLE_GRAPH_DATA_TYPE_ID,
            GRAPH_DATA_TYPE_ID,
        },
        ASSEMBLY_DATA_TYPE_ID: {
            ASSEMBLY_DATA_TYPE_ID,
            PART_DATA_TYPE_ID,
            SPATIAL_OBJECT_DATA_TYPE_ID,
            MEASURABLE_DATA_TYPE_ID,
            CLIPPABLE_GRAPH_DATA_TYPE_ID,
            GRAPH_DATA_TYPE_ID,
        },
        ARC_DATA_TYPE_ID: {
            ARC_DATA_TYPE_ID,
            CURVE_DATA_TYPE_ID,
            MORPHABLE_DATA_TYPE_ID,
            SPATIAL_OBJECT_DATA_TYPE_ID,
            MEASURABLE_DATA_TYPE_ID,
            CLIPPABLE_GRAPH_DATA_TYPE_ID,
            GRAPH_DATA_TYPE_ID,
        },
        CIRCLE_DATA_TYPE_ID: {
            CIRCLE_DATA_TYPE_ID,
            CURVE_DATA_TYPE_ID,
            MORPHABLE_DATA_TYPE_ID,
            SPATIAL_OBJECT_DATA_TYPE_ID,
            MEASURABLE_DATA_TYPE_ID,
            CLIPPABLE_GRAPH_DATA_TYPE_ID,
            GRAPH_DATA_TYPE_ID,
        },
        ELLIPSE_DATA_TYPE_ID: {
            ELLIPSE_DATA_TYPE_ID,
            CURVE_DATA_TYPE_ID,
            MORPHABLE_DATA_TYPE_ID,
            SPATIAL_OBJECT_DATA_TYPE_ID,
            MEASURABLE_DATA_TYPE_ID,
            CLIPPABLE_GRAPH_DATA_TYPE_ID,
            GRAPH_DATA_TYPE_ID,
        },
        FINITE_LINE_DATA_TYPE_ID: {
            FINITE_LINE_DATA_TYPE_ID,
            CURVE_DATA_TYPE_ID,
            MORPHABLE_DATA_TYPE_ID,
            SPATIAL_OBJECT_DATA_TYPE_ID,
            MEASURABLE_DATA_TYPE_ID,
            CLIPPABLE_GRAPH_DATA_TYPE_ID,
            GRAPH_DATA_TYPE_ID,
        },
    }
    curve_closure = {
        CURVE_DATA_TYPE_ID,
        MORPHABLE_DATA_TYPE_ID,
        SPATIAL_OBJECT_DATA_TYPE_ID,
        MEASURABLE_DATA_TYPE_ID,
        CLIPPABLE_GRAPH_DATA_TYPE_ID,
        GRAPH_DATA_TYPE_ID,
    }
    for type_id in (
        B_SPLINE_DATA_TYPE_ID,
        FACET_CURVE_DATA_TYPE_ID,
        INFINITE_LINE_DATA_TYPE_ID,
        PIPE_CURVE_DATA_TYPE_ID,
        POLY_CURVE_DATA_TYPE_ID,
        POLYLINE_DATA_TYPE_ID,
    ):
        expected_assignable_targets[type_id] = {type_id, *curve_closure}
    expected_assignable_targets[RECTANGLE_DATA_TYPE_ID] = {
        RECTANGLE_DATA_TYPE_ID,
        POLYLINE_DATA_TYPE_ID,
        *curve_closure,
    }
    surface_closure = {
        SURFACE_DATA_TYPE_ID,
        SPATIAL_OBJECT_DATA_TYPE_ID,
        MEASURABLE_DATA_TYPE_ID,
        CLIPPABLE_GRAPH_DATA_TYPE_ID,
        GRAPH_DATA_TYPE_ID,
    }
    for type_id in (TRIMMED_SURFACE_DATA_TYPE_ID, UNTRIMMED_SURFACE_DATA_TYPE_ID):
        expected_assignable_targets[type_id] = {type_id, *surface_closure}
    expected_assignable_targets[FACET_SURFACE_DATA_TYPE_ID] = {
        FACET_SURFACE_DATA_TYPE_ID,
        UNTRIMMED_SURFACE_DATA_TYPE_ID,
        *surface_closure,
    }
    expected_assignable_targets[SIMPLE_TREE_CONNECTOR_DATA_TYPE_ID] = {
        SIMPLE_TREE_CONNECTOR_DATA_TYPE_ID,
        SPATIAL_OBJECT_DATA_TYPE_ID,
        GRAPH_DATA_TYPE_ID,
    }
    expected_assignable_targets[SUBD_DATA_TYPE_ID] = {
        SUBD_DATA_TYPE_ID,
        MEASURABLE_DATA_TYPE_ID,
        MORPHABLE_DATA_TYPE_ID,
        SPATIAL_OBJECT_DATA_TYPE_ID,
        GRAPH_DATA_TYPE_ID,
    }
    for source_type_id, expected_targets in expected_assignable_targets.items():
        assert {
            target_type_id
            for target_type_id in checked_targets
            if catalog.is_assignable(source_type_id, target_type_id)
        } == expected_targets

    assert not catalog.is_assignable(ASSEMBLY_DATA_TYPE_ID, BODY_DATA_TYPE_ID)
    assert not catalog.is_assignable(ASSEMBLY_DATA_TYPE_ID, MORPHABLE_DATA_TYPE_ID)
    curve_and_surface_children = {
        ARC_DATA_TYPE_ID,
        B_SPLINE_DATA_TYPE_ID,
        CIRCLE_DATA_TYPE_ID,
        ELLIPSE_DATA_TYPE_ID,
        FACET_CURVE_DATA_TYPE_ID,
        FACET_SURFACE_DATA_TYPE_ID,
        FINITE_LINE_DATA_TYPE_ID,
        INFINITE_LINE_DATA_TYPE_ID,
        PIPE_CURVE_DATA_TYPE_ID,
        POLY_CURVE_DATA_TYPE_ID,
        POLYLINE_DATA_TYPE_ID,
        RECTANGLE_DATA_TYPE_ID,
        TRIMMED_SURFACE_DATA_TYPE_ID,
        UNTRIMMED_SURFACE_DATA_TYPE_ID,
    }
    assert all(
        catalog.require(type_id).abstract for type_id in curve_and_surface_children
    )
    assert all(
        catalog.is_assignable(type_id, CLIPPABLE_GRAPH_DATA_TYPE_ID)
        for type_id in curve_and_surface_children
    )
    assert catalog.is_assignable(RECTANGLE_DATA_TYPE_ID, POLYLINE_DATA_TYPE_ID)
    assert catalog.is_assignable(RECTANGLE_DATA_TYPE_ID, CURVE_DATA_TYPE_ID)
    assert catalog.is_assignable(
        FACET_SURFACE_DATA_TYPE_ID, UNTRIMMED_SURFACE_DATA_TYPE_ID
    )
    assert catalog.is_assignable(FACET_SURFACE_DATA_TYPE_ID, SURFACE_DATA_TYPE_ID)
    assert catalog.is_assignable(
        SIMPLE_TREE_CONNECTOR_DATA_TYPE_ID, SPATIAL_OBJECT_DATA_TYPE_ID
    )
    assert not catalog.is_assignable(
        SIMPLE_TREE_CONNECTOR_DATA_TYPE_ID, CLIPPABLE_GRAPH_DATA_TYPE_ID
    )
    assert not catalog.is_assignable(
        SIMPLE_TREE_CONNECTOR_DATA_TYPE_ID, MEASURABLE_DATA_TYPE_ID
    )
    assert all(
        catalog.is_assignable(SUBD_DATA_TYPE_ID, target_type_id)
        for target_type_id in (
            SPATIAL_OBJECT_DATA_TYPE_ID,
            MEASURABLE_DATA_TYPE_ID,
            MORPHABLE_DATA_TYPE_ID,
        )
    )
    assert not catalog.is_assignable(SUBD_DATA_TYPE_ID, CLIPPABLE_GRAPH_DATA_TYPE_ID)
    assert catalog.owner_of(CLIPPABLE_GRAPH_DATA_TYPE_ID) == CORE_DATA_TYPE_OWNER_ID
    assert catalog.require(ENGINEERING_SCENE_DATA_TYPE_ID).parents == (
        CLIPPABLE_GRAPH_DATA_TYPE_ID,
    )
    assert {
        spec.type_id
        for spec in catalog.all_specs()
        if not spec.abstract
        and catalog.is_assignable(
            spec.type_id,
            CLIPPABLE_GRAPH_DATA_TYPE_ID,
        )
    } == {ENGINEERING_SCENE_DATA_TYPE_ID}


def test_all_abstract_validators_and_exact_handles_reject() -> None:
    catalog = _registry(
        COREX_GEOMETRY_COORDINATE_SYSTEM_VALUE_CANDIDATE_CONTRACT_MANIFEST
    ).data_types
    for spec in COREX_GEOMETRY_COORDINATE_SYSTEM_VALUE_CANDIDATE_DATA_TYPES:
        handle = _handle(spec.type_id)
        inline = TypedInlineValue(spec.type_id, 1, {})
        assert spec.validate_item(object()) is False
        assert spec.validate_item(handle) is False
        assert spec.validate_item(inline) is False
        with pytest.raises(DataTypeCatalogError, match="must be concrete"):
            catalog.validate_carrier(spec.type_id, handle)
        with pytest.raises(DataTypeCatalogError, match="must be concrete"):
            catalog.validate_carrier(spec.type_id, inline)

    assert catalog.is_assignable(
        COORDINATE_SYSTEM_DATA_TYPE_ID,
        SPATIAL_OBJECT_DATA_TYPE_ID,
    )
    assert not catalog.is_assignable(
        COORDINATE_SYSTEM_DATA_TYPE_ID,
        CLIPPABLE_GRAPH_DATA_TYPE_ID,
    )
    assert {
        spec.type_id
        for spec in catalog.all_specs()
        if not spec.abstract
        and catalog.is_assignable(
            spec.type_id,
            CLIPPABLE_GRAPH_DATA_TYPE_ID,
        )
    } == {ENGINEERING_SCENE_DATA_TYPE_ID}


def test_d023_to_d030_geometry_boundaries_stay_exact_under_d032_bootstrap() -> None:
    baseline_type_ids = tuple(spec.type_id for spec in COREX_GEOMETRY_DATA_TYPES)
    assert baseline_type_ids == _EXPECTED_TYPE_IDS
    assert len(baseline_type_ids) == 7
    assert ASSEMBLY_DATA_TYPE_ID not in baseline_type_ids
    assert COREX_GEOMETRY_CONTRACT_MANIFEST == PluginContractManifest(
        data_types=COREX_GEOMETRY_DATA_TYPES
    )

    candidate_type_ids = tuple(
        spec.type_id for spec in COREX_GEOMETRY_ASSEMBLY_CANDIDATE_DATA_TYPES
    )
    assert candidate_type_ids == _EXPECTED_ASSEMBLY_CANDIDATE_TYPE_IDS
    assert len(candidate_type_ids) == 8
    assert (
        COREX_GEOMETRY_ASSEMBLY_CANDIDATE_DATA_TYPES[:-1] == COREX_GEOMETRY_DATA_TYPES
    )
    assert candidate_type_ids[-1:] == (ASSEMBLY_DATA_TYPE_ID,)
    assert (
        COREX_GEOMETRY_ASSEMBLY_CANDIDATE_CONTRACT_MANIFEST
        == PluginContractManifest(
            data_types=COREX_GEOMETRY_ASSEMBLY_CANDIDATE_DATA_TYPES
        )
    )
    curve_subtype_candidate_type_ids = tuple(
        spec.type_id for spec in COREX_GEOMETRY_CURVE_SUBTYPES_CANDIDATE_DATA_TYPES
    )
    assert (
        curve_subtype_candidate_type_ids == _EXPECTED_CURVE_SUBTYPES_CANDIDATE_TYPE_IDS
    )
    assert len(curve_subtype_candidate_type_ids) == 12
    assert curve_subtype_candidate_type_ids[-4:] == _EXPECTED_CURVE_SUBTYPE_TYPE_IDS
    assert (
        COREX_GEOMETRY_CURVE_SUBTYPES_CANDIDATE_DATA_TYPES[:8]
        == COREX_GEOMETRY_ASSEMBLY_CANDIDATE_DATA_TYPES
    )
    assert (
        COREX_GEOMETRY_CURVE_SUBTYPES_CANDIDATE_CONTRACT_MANIFEST
        == PluginContractManifest(
            data_types=COREX_GEOMETRY_CURVE_SUBTYPES_CANDIDATE_DATA_TYPES
        )
    )

    body_subtype_candidate_type_ids = tuple(
        spec.type_id for spec in COREX_GEOMETRY_BODY_SUBTYPES_CANDIDATE_DATA_TYPES
    )
    assert body_subtype_candidate_type_ids == _EXPECTED_BODY_SUBTYPES_CANDIDATE_TYPE_IDS
    assert len(body_subtype_candidate_type_ids) == 14
    assert body_subtype_candidate_type_ids[-2:] == _EXPECTED_BODY_SUBTYPE_TYPE_IDS
    assert (
        COREX_GEOMETRY_BODY_SUBTYPES_CANDIDATE_DATA_TYPES[:12]
        == COREX_GEOMETRY_CURVE_SUBTYPES_CANDIDATE_DATA_TYPES
    )
    assert (
        COREX_GEOMETRY_BODY_SUBTYPES_CANDIDATE_CONTRACT_MANIFEST
        == PluginContractManifest(
            data_types=COREX_GEOMETRY_BODY_SUBTYPES_CANDIDATE_DATA_TYPES
        )
    )
    closure_candidate_type_ids = tuple(
        spec.type_id for spec in COREX_GEOMETRY_CLOSURE_CANDIDATE_DATA_TYPES
    )
    assert closure_candidate_type_ids == _EXPECTED_GEOMETRY_CLOSURE_CANDIDATE_TYPE_IDS
    assert len(closure_candidate_type_ids) == 26
    assert (
        COREX_GEOMETRY_CLOSURE_CANDIDATE_DATA_TYPES[:14]
        == COREX_GEOMETRY_BODY_SUBTYPES_CANDIDATE_DATA_TYPES
    )
    assert closure_candidate_type_ids[-12:] == tuple(
        type_id
        for type_id, _display_name, _parents in _EXPECTED_GEOMETRY_CLOSURE_SUFFIX
    )
    assert (
        COREX_GEOMETRY_CLOSURE_CANDIDATE_CONTRACT_MANIFEST
        == PluginContractManifest(
            data_types=COREX_GEOMETRY_CLOSURE_CANDIDATE_DATA_TYPES
        )
    )
    assert (
        _registry(
            COREX_GEOMETRY_ASSEMBLY_CANDIDATE_CONTRACT_MANIFEST
        ).all_descriptors()
        == []
    )

    registry = build_builtin_registry()
    owner_records = [
        record
        for record in registry.data_types.snapshot()
        if record["kind"] == "type"
        and record["owner_id"] == COREX_GEOMETRY_CONTRACTS_OWNER_ID
    ]

    assert registry.data_types.is_frozen
    assert (
        registry.plugin_contract_manifest(COREX_GEOMETRY_CONTRACTS_OWNER_ID)
        is COREX_GEOMETRY_COORDINATE_SYSTEM_VALUE_CANDIDATE_CONTRACT_MANIFEST
    )
    assert len(owner_records) == 27
    assert {record["type_id"] for record in owner_records} == set(
        _EXPECTED_COORDINATE_SYSTEM_CANDIDATE_TYPE_IDS
    )
    assert {
        ARC_DATA_TYPE_ID,
        CIRCLE_DATA_TYPE_ID,
        ELLIPSE_DATA_TYPE_ID,
        FINITE_LINE_DATA_TYPE_ID,
    } <= {record["type_id"] for record in owner_records}
    assert (
        sum(record["type_id"] == ASSEMBLY_DATA_TYPE_ID for record in owner_records) == 1
    )
    assert all(
        sum(record["type_id"] == type_id for record in owner_records) == 1
        for type_id in _EXPECTED_BODY_SUBTYPE_TYPE_IDS
    )
    assert {
        (record["owner_id"], record["owner_version"]) for record in owner_records
    } == {
        (
            COREX_GEOMETRY_CONTRACTS_OWNER_ID,
            COREX_GEOMETRY_CONTRACTS_OWNER_VERSION,
        )
    }


def test_d030_icoordinate_system_owner_replacement_is_atomic_and_reversible() -> None:
    registry = NodeRegistry()
    registry.freeze()
    source_label = "ea_node_editor.nodes.builtins.geometry_contracts"
    registry.register_plugin_bundle(
        COREX_GEOMETRY_CLOSURE_CANDIDATE_CONTRACT_MANIFEST,
        (),
        owner_id=COREX_GEOMETRY_CONTRACTS_OWNER_ID,
        owner_version=COREX_GEOMETRY_CONTRACTS_OWNER_VERSION,
        source_label=source_label,
        replace_owner=True,
    )
    d029_snapshot = registry.data_types.snapshot()
    d029_type_ids = {spec.type_id for spec in registry.data_types.all_specs()}
    d029_owner_type_ids = {
        record["type_id"]
        for record in d029_snapshot
        if record["kind"] == "type"
        and record["owner_id"] == COREX_GEOMETRY_CONTRACTS_OWNER_ID
    }
    assert registry.data_types.is_frozen
    assert len(d029_owner_type_ids) == 26
    assert d029_owner_type_ids == set(_EXPECTED_GEOMETRY_CLOSURE_CANDIDATE_TYPE_IDS)
    assert (
        registry.plugin_contract_manifest(COREX_GEOMETRY_CONTRACTS_OWNER_ID)
        is COREX_GEOMETRY_CLOSURE_CANDIDATE_CONTRACT_MANIFEST
    )

    with pytest.raises(DataTypeCatalogError, match="references unknown parent"):
        registry.register_plugin_bundle(
            PluginContractManifest(
                data_types=COREX_GEOMETRY_COORDINATE_SYSTEM_CANDIDATE_DATA_TYPES[-1:]
            ),
            (),
            owner_id=COREX_GEOMETRY_CONTRACTS_OWNER_ID,
            owner_version=COREX_GEOMETRY_CONTRACTS_OWNER_VERSION,
            source_label=source_label,
            replace_owner=True,
        )

    assert registry.data_types.snapshot() == d029_snapshot
    assert registry.data_types.is_frozen
    assert (
        registry.plugin_contract_manifest(COREX_GEOMETRY_CONTRACTS_OWNER_ID)
        is COREX_GEOMETRY_CLOSURE_CANDIDATE_CONTRACT_MANIFEST
    )

    registry.register_plugin_bundle(
        COREX_GEOMETRY_COORDINATE_SYSTEM_CANDIDATE_CONTRACT_MANIFEST,
        (),
        owner_id=COREX_GEOMETRY_CONTRACTS_OWNER_ID,
        owner_version=COREX_GEOMETRY_CONTRACTS_OWNER_VERSION,
        source_label=source_label,
        replace_owner=True,
    )
    d030_type_ids = {spec.type_id for spec in registry.data_types.all_specs()}
    d030_owner_type_ids = {
        record["type_id"]
        for record in registry.data_types.snapshot()
        if record["kind"] == "type"
        and record["owner_id"] == COREX_GEOMETRY_CONTRACTS_OWNER_ID
    }
    assert d030_type_ids == d029_type_ids | {COORDINATE_SYSTEM_DATA_TYPE_ID}
    assert len(d030_owner_type_ids) == 27
    assert d030_owner_type_ids == set(_EXPECTED_COORDINATE_SYSTEM_CANDIDATE_TYPE_IDS)
    assert registry.data_types.is_frozen
    assert (
        registry.plugin_contract_manifest(COREX_GEOMETRY_CONTRACTS_OWNER_ID)
        is COREX_GEOMETRY_COORDINATE_SYSTEM_CANDIDATE_CONTRACT_MANIFEST
    )

    registry.register_plugin_bundle(
        COREX_GEOMETRY_CLOSURE_CANDIDATE_CONTRACT_MANIFEST,
        (),
        owner_id=COREX_GEOMETRY_CONTRACTS_OWNER_ID,
        owner_version=COREX_GEOMETRY_CONTRACTS_OWNER_VERSION,
        source_label=source_label,
        replace_owner=True,
    )
    assert registry.data_types.snapshot() == d029_snapshot
    assert registry.data_types.get(COORDINATE_SYSTEM_DATA_TYPE_ID) is None
    assert registry.data_types.is_frozen


def test_failed_d026_body_subtype_candidate_replacement_rolls_back_all_fourteen_types() -> (
    None
):
    registry = NodeRegistry()
    registry.register_plugin_bundle(
        PluginContractManifest(
            data_types=(
                replace(
                    COREX_GEOMETRY_DATA_TYPES[-1],
                    parents=(GRAPH_DATA_TYPE_ID,),
                ),
            )
        ),
        (),
        owner_id="test.geometry_conflict",
        owner_version="1",
    )
    before = registry.data_types.snapshot()

    with pytest.raises(DataTypeCatalogError, match="duplicate data-type ID"):
        registry.register_plugin_bundle(
            COREX_GEOMETRY_BODY_SUBTYPES_CANDIDATE_CONTRACT_MANIFEST,
            (),
            owner_id=COREX_GEOMETRY_CONTRACTS_OWNER_ID,
            owner_version=COREX_GEOMETRY_CONTRACTS_OWNER_VERSION,
        )

    assert registry.data_types.snapshot() == before
    assert registry.plugin_contract_manifest(COREX_GEOMETRY_CONTRACTS_OWNER_ID) is None
    assert registry.all_descriptors() == []


def test_failed_d027_geometry_closure_candidate_replacement_rolls_back_all_twenty_six_types() -> (
    None
):
    registry = NodeRegistry()
    registry.register_plugin_bundle(
        PluginContractManifest(
            data_types=(
                replace(
                    COREX_GEOMETRY_DATA_TYPES[-1],
                    parents=(GRAPH_DATA_TYPE_ID,),
                ),
            )
        ),
        (),
        owner_id="test.geometry_closure_conflict",
        owner_version="1",
    )
    before = registry.data_types.snapshot()

    with pytest.raises(DataTypeCatalogError, match="duplicate data-type ID"):
        registry.register_plugin_bundle(
            COREX_GEOMETRY_CLOSURE_CANDIDATE_CONTRACT_MANIFEST,
            (),
            owner_id=COREX_GEOMETRY_CONTRACTS_OWNER_ID,
            owner_version=COREX_GEOMETRY_CONTRACTS_OWNER_VERSION,
        )

    assert registry.data_types.snapshot() == before
    assert registry.plugin_contract_manifest(COREX_GEOMETRY_CONTRACTS_OWNER_ID) is None
    assert registry.all_descriptors() == []

from __future__ import annotations

import pytest

from ea_node_editor.nodes.builtins import voxel_contracts as voxel_module
from ea_node_editor.nodes.builtins.geometry_contracts import (
    MEASURABLE_DATA_TYPE_ID,
    SPATIAL_OBJECT_DATA_TYPE_ID,
    COREX_GEOMETRY_CLOSURE_CANDIDATE_CONTRACT_MANIFEST,
    COREX_GEOMETRY_CONTRACTS_OWNER_ID,
    COREX_GEOMETRY_CONTRACTS_OWNER_VERSION,
)
from ea_node_editor.nodes.builtins.voxel_contracts import (
    COREX_VOXEL_CONTRACT_MANIFEST,
    COREX_VOXEL_CONTRACTS_OWNER_ID,
    COREX_VOXEL_CONTRACTS_OWNER_VERSION,
    COREX_VOXEL_DATA_TYPES,
    VOXEL_MAP_DATA_TYPE_ID,
    VOXEL_SKELETON_DATA_TYPE_ID,
)
from ea_node_editor.nodes.core_data_types import (
    CLIPPABLE_GRAPH_DATA_TYPE_ID,
    ENGINEERING_SCENE_DATA_TYPE_ID,
    GRAPH_DATA_TYPE_ID,
)
from ea_node_editor.nodes.registry import NodeRegistry
from ea_node_editor.runtime_contracts import DataTypeCatalogError, RuntimeHandleRef

_EXPECTED_TYPE_IDS = (
    "COREX.Voxel.IVoxelMap",
    "COREX.Voxel.IVoxelSkeleton",
)


def _register_voxel(registry: NodeRegistry) -> None:
    registry.register_plugin_bundle(
        COREX_VOXEL_CONTRACT_MANIFEST,
        (),
        owner_id=COREX_VOXEL_CONTRACTS_OWNER_ID,
        owner_version=COREX_VOXEL_CONTRACTS_OWNER_VERSION,
        source_label=voxel_module.__name__,
    )


def _composed_registry() -> NodeRegistry:
    registry = NodeRegistry()
    registry.register_plugin_bundle(
        COREX_GEOMETRY_CLOSURE_CANDIDATE_CONTRACT_MANIFEST,
        (),
        owner_id=COREX_GEOMETRY_CONTRACTS_OWNER_ID,
        owner_version=COREX_GEOMETRY_CONTRACTS_OWNER_VERSION,
        source_label="ea_node_editor.nodes.builtins.geometry_contracts",
    )
    _register_voxel(registry)
    return registry


def _handle(type_id: str) -> RuntimeHandleRef:
    return RuntimeHandleRef(
        data_type_id=type_id,
        schema_version=1,
        handle_id="abstract-voxel-test",
        kind="test.abstract_voxel",
        owner_scope="run:test",
        worker_generation=1,
        metadata={},
    )




def test_exact_abstract_handle_specs_have_the_reduced_direct_parent_dag() -> None:
    expected = (
        (
            VOXEL_MAP_DATA_TYPE_ID,
            "Voxel Map",
            (
                SPATIAL_OBJECT_DATA_TYPE_ID,
                MEASURABLE_DATA_TYPE_ID,
                CLIPPABLE_GRAPH_DATA_TYPE_ID,
            ),
        ),
        (
            VOXEL_SKELETON_DATA_TYPE_ID,
            "Voxel Skeleton",
            (
                SPATIAL_OBJECT_DATA_TYPE_ID,
                MEASURABLE_DATA_TYPE_ID,
            ),
        ),
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
        for spec in COREX_VOXEL_DATA_TYPES
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
        for type_id, display_name, parents in expected
    ]

    catalog = _composed_registry().data_types
    assert {
        target
        for target in (
            VOXEL_MAP_DATA_TYPE_ID,
            VOXEL_SKELETON_DATA_TYPE_ID,
            SPATIAL_OBJECT_DATA_TYPE_ID,
            MEASURABLE_DATA_TYPE_ID,
            CLIPPABLE_GRAPH_DATA_TYPE_ID,
            GRAPH_DATA_TYPE_ID,
        )
        if catalog.is_assignable(VOXEL_MAP_DATA_TYPE_ID, target)
    } == {
        VOXEL_MAP_DATA_TYPE_ID,
        SPATIAL_OBJECT_DATA_TYPE_ID,
        MEASURABLE_DATA_TYPE_ID,
        CLIPPABLE_GRAPH_DATA_TYPE_ID,
        GRAPH_DATA_TYPE_ID,
    }
    assert {
        target
        for target in (
            VOXEL_MAP_DATA_TYPE_ID,
            VOXEL_SKELETON_DATA_TYPE_ID,
            SPATIAL_OBJECT_DATA_TYPE_ID,
            MEASURABLE_DATA_TYPE_ID,
            CLIPPABLE_GRAPH_DATA_TYPE_ID,
            GRAPH_DATA_TYPE_ID,
        )
        if catalog.is_assignable(VOXEL_SKELETON_DATA_TYPE_ID, target)
    } == {
        VOXEL_SKELETON_DATA_TYPE_ID,
        SPATIAL_OBJECT_DATA_TYPE_ID,
        MEASURABLE_DATA_TYPE_ID,
        GRAPH_DATA_TYPE_ID,
    }
    assert catalog.require(VOXEL_MAP_DATA_TYPE_ID).abstract
    assert catalog.is_assignable(
        VOXEL_MAP_DATA_TYPE_ID,
        CLIPPABLE_GRAPH_DATA_TYPE_ID,
    )
    assert catalog.require(VOXEL_SKELETON_DATA_TYPE_ID).abstract
    assert not catalog.is_assignable(
        VOXEL_SKELETON_DATA_TYPE_ID,
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
    catalog = _composed_registry().data_types
    for spec in COREX_VOXEL_DATA_TYPES:
        handle = _handle(spec.type_id)
        assert spec.validate_item(object()) is False
        assert spec.validate_item(handle) is False
        with pytest.raises(DataTypeCatalogError, match="must be concrete"):
            catalog.validate_carrier(spec.type_id, handle)

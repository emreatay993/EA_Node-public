from __future__ import annotations

from ea_node_editor.nodes.bootstrap import build_builtin_registry
from ea_node_editor.nodes.builtins.tree_path import (
    COREX_TREE_PATH_OWNER_ID,
    TREE_PATH_DATA_TYPE_ID,
)
from ea_node_editor.nodes.core_data_types import GRAPH_DATA_TYPE_ID


def test_corex_type_ids_and_owners_are_canonical() -> None:
    registry = build_builtin_registry()

    expected_owners = {
        "COREX.DataTypes.Image": "corex.core_values",
        "COREX.DataTypes.Point3D": "corex.spatial_values",
        "COREX.Geometry.Group": "corex.geometry_primitives",
        "COREX.Geometry.OCPBody": "corex.geometry_primitives",
        "COREX.DataTypes.ViewerViewport": "corex.viewer_viewport",
        TREE_PATH_DATA_TYPE_ID: COREX_TREE_PATH_OWNER_ID,
    }
    for type_id, owner_id in expected_owners.items():
        assert registry.data_types.owner_of(type_id) == owner_id


def test_tree_path_is_one_concrete_corex_carrier() -> None:
    registry = build_builtin_registry()
    spec = registry.data_types.require(TREE_PATH_DATA_TYPE_ID)

    assert spec.abstract is False
    assert spec.carriers == frozenset({"inline"})
    assert spec.persistence == "inline"
    assert spec.parents == (GRAPH_DATA_TYPE_ID,)


def test_public_contract_manifest_contains_only_runtime_contract_fields() -> None:
    from ea_node_editor.nodes.plugin_contracts import PluginContractManifest

    assert set(PluginContractManifest.__dataclass_fields__) == {
        "runtime_backends",
        "toolchains",
        "artifacts",
        "surface_capabilities",
        "data_type_families",
        "data_types",
        "data_conversions",
    }

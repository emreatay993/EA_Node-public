# Purpose: Register the reserved built-in contract table, descriptors, and function bundle.
# Map: subsystems/nodes_registry_builtins.md
# Tests: tests/test_builtin_function_infrastructure.py, tests/test_registry_validation.py

from __future__ import annotations

from pathlib import Path

from ea_node_editor.nodes.builtins import data_control as _data_control  # noqa: F401
from ea_node_editor.nodes.builtins.ai_ml_contracts import (
    COREX_AI_ML_CONTRACTS_OWNER_ID,
    COREX_AI_ML_CONTRACTS_OWNER_VERSION,
    COREX_AI_ML_VECTOR_DATABASE_CANDIDATE_CONTRACT_MANIFEST,
)
from ea_node_editor.nodes.builtins.core import CORE_NODE_DESCRIPTORS
from ea_node_editor.nodes.builtins.core_media import (
    COREX_CORE_MEDIA_CONTRACT_MANIFEST,
    COREX_CORE_MEDIA_OWNER_ID,
    COREX_CORE_MEDIA_OWNER_VERSION,
)
from ea_node_editor.nodes.builtins.core_values import (
    COREX_CORE_VALUE_CONTRACT_MANIFEST,
    COREX_CORE_VALUE_OWNER_ID,
    COREX_CORE_VALUE_OWNER_VERSION,
)
from ea_node_editor.nodes.builtins.excalidraw import EXCALIDRAW_NODE_DESCRIPTORS
from ea_node_editor.nodes.builtins.fem_contracts import (
    COREX_FEM_CONTRACT_MANIFEST,
    COREX_FEM_CONTRACTS_OWNER_ID,
    COREX_FEM_CONTRACTS_OWNER_VERSION,
    COREX_FEM_NODE_DESCRIPTORS,
)
from ea_node_editor.nodes.builtins.geometry_contracts import (
    COREX_GEOMETRY_CONTRACTS_OWNER_ID,
    COREX_GEOMETRY_CONTRACTS_OWNER_VERSION,
    COREX_GEOMETRY_COORDINATE_SYSTEM_VALUE_CANDIDATE_CONTRACT_MANIFEST,
)
from ea_node_editor.nodes.builtins.geometry_primitives import (
    COREX_GEOMETRY_PRIMITIVES_CONTRACT_MANIFEST,
    COREX_GEOMETRY_PRIMITIVES_OWNER_ID,
    COREX_GEOMETRY_PRIMITIVES_OWNER_VERSION,
)
from ea_node_editor.nodes.builtins.integrations_file_io import (
    FILE_IO_NODE_DESCRIPTORS,
)
from ea_node_editor.nodes.builtins.integrations_ssh_sftp import (
    SSH_SFTP_DATA_TYPE_FAMILIES,
    SSH_SFTP_DATA_TYPE_OWNER_ID,
    SSH_SFTP_DATA_TYPES,
)
from ea_node_editor.nodes.builtins.jupyter_notebook import (
    JUPYTER_NOTEBOOK_NODE_DESCRIPTORS,
)
from ea_node_editor.nodes.builtins.media_panel import MEDIA_PANEL_NODE_DESCRIPTORS
from ea_node_editor.nodes.builtins.mesh_contracts import (
    COREX_MESH_CONTRACTS_OWNER_ID,
    COREX_MESH_CONTRACTS_OWNER_VERSION,
    COREX_MESH_PARAMETER_CANDIDATE_CONTRACT_MANIFEST,
)
from ea_node_editor.nodes.builtins.passive_annotation import (
    PASSIVE_ANNOTATION_NODE_DESCRIPTORS,
)
from ea_node_editor.nodes.builtins.passive_flowchart import (
    PASSIVE_FLOWCHART_NODE_DESCRIPTORS,
)
from ea_node_editor.nodes.builtins.passive_mail import PASSIVE_MAIL_NODE_DESCRIPTORS
from ea_node_editor.nodes.builtins.passive_planning import (
    PASSIVE_PLANNING_NODE_DESCRIPTORS,
)
from ea_node_editor.nodes.builtins.plot import PLOT_NODE_DESCRIPTORS
from ea_node_editor.nodes.builtins.reporting import (
    COREX_REPORTING_CONTRACT_MANIFEST,
    COREX_REPORTING_OWNER_ID,
    COREX_REPORTING_OWNER_VERSION,
)
from ea_node_editor.nodes.builtins.rich_value_nodes import (
    COREX_RICH_VALUE_LLM_CANDIDATE_CONTRACT_MANIFEST,
    COREX_RICH_VALUE_OWNER_ID,
    COREX_RICH_VALUE_OWNER_VERSION,
)
from ea_node_editor.nodes.builtins.security_contracts import (
    COREX_SECURITY_CONTRACT_MANIFEST,
    COREX_SECURITY_OWNER_ID,
    COREX_SECURITY_OWNER_VERSION,
)
from ea_node_editor.nodes.builtins.spatial_values import (
    COREX_SPATIAL_VALUES_COORDINATE_SYSTEM_CANDIDATE_CONTRACT_MANIFEST,
    COREX_SPATIAL_VALUES_OWNER_ID,
    COREX_SPATIAL_VALUES_OWNER_VERSION,
)
from ea_node_editor.nodes.builtins.subnode import SUBNODE_NODE_DESCRIPTORS
from ea_node_editor.nodes.builtins.tree_path import (
    COREX_TREE_PATH_CONTRACT_MANIFEST,
    COREX_TREE_PATH_OWNER_ID,
    COREX_TREE_PATH_OWNER_VERSION,
)
from ea_node_editor.nodes.builtins.units import (
    COREX_UNITS_CONTRACT_MANIFEST,
    COREX_UNITS_OWNER_ID,
    COREX_UNITS_OWNER_VERSION,
)
from ea_node_editor.nodes.builtins.viewer_viewport import (
    COREX_VIEWER_VIEWPORT_CONTRACT_MANIFEST,
    COREX_VIEWER_VIEWPORT_OWNER_ID,
    COREX_VIEWER_VIEWPORT_OWNER_VERSION,
)
from ea_node_editor.nodes.builtins.voxel_contracts import (
    COREX_VOXEL_CONTRACT_MANIFEST,
    COREX_VOXEL_CONTRACTS_OWNER_ID,
    COREX_VOXEL_CONTRACTS_OWNER_VERSION,
)
from ea_node_editor.nodes.builtins.web_viewer import WEB_PAGE_VIEWER_NODE_DESCRIPTORS
from ea_node_editor.nodes.core_data_types import (
    CORE_DATA_CONVERSIONS,
    CORE_DATA_TYPE_FAMILIES,
    CORE_DATA_TYPE_OWNER_ID,
    CORE_DATA_TYPE_OWNER_VERSION,
    CORE_DATA_TYPES,
)
from ea_node_editor.nodes.function_bundle import (
    PreparedFunctionBundle,
    build_function_entries,
    materialize_prepared_function_bundle,
    missing_bundle_imports,
    module_declarations,
    node_inventory,
    registry_plugin_fingerprint,
    source_digest,
)
from ea_node_editor.nodes.function_plugin import INTERNAL_BUILTIN_FUNCTION_OWNER_ID
from ea_node_editor.nodes.package_schema import (
    PLUGIN_SOURCE_LIMIT,
    validated_plugin_member_path,
)
from ea_node_editor.nodes.plugin_contracts import PluginContractManifest
from ea_node_editor.nodes.registry import NodeRegistry

_TRUSTED_BUILTIN_DESCRIPTORS = (
    *CORE_NODE_DESCRIPTORS,
    *FILE_IO_NODE_DESCRIPTORS,
    *PLOT_NODE_DESCRIPTORS,
    *SUBNODE_NODE_DESCRIPTORS,
    *PASSIVE_FLOWCHART_NODE_DESCRIPTORS,
    *PASSIVE_PLANNING_NODE_DESCRIPTORS,
    *PASSIVE_ANNOTATION_NODE_DESCRIPTORS,
    *MEDIA_PANEL_NODE_DESCRIPTORS,
    *PASSIVE_MAIL_NODE_DESCRIPTORS,
    *WEB_PAGE_VIEWER_NODE_DESCRIPTORS,
    *JUPYTER_NOTEBOOK_NODE_DESCRIPTORS,
    *EXCALIDRAW_NODE_DESCRIPTORS,
)

_TRUSTED_BUILTIN_TYPE_IDS = frozenset(
    {
        "code.jupyter_notebook",
        "core.python_script",
        "core.stream_gate",
        "core.subnode",
        "core.subnode_input",
        "core.subnode_output",
        "core.trigger",
        "excalidraw.board",
        "io.folder_explorer",
        "io.path_pointer",
        "optimization.parameter_pool",
        "optimization.parameter_setup",
        "optimization.response_pool",
        "passive.annotation.callout",
        "passive.annotation.group_backdrop",
        "passive.annotation.section_header",
        "passive.annotation.sticky_note",
        "passive.annotation.text",
        "passive.flowchart.actor",
        "passive.flowchart.callout",
        "passive.flowchart.card",
        "passive.flowchart.connector",
        "passive.flowchart.cube",
        "passive.flowchart.database",
        "passive.flowchart.decision",
        "passive.flowchart.document",
        "passive.flowchart.end",
        "passive.flowchart.input_output",
        "passive.flowchart.isometric_cube",
        "passive.flowchart.message",
        "passive.flowchart.multi_document",
        "passive.flowchart.predefined_process",
        "passive.flowchart.process",
        "passive.flowchart.star",
        "passive.flowchart.start",
        "passive.flowchart.tick",
        "passive.flowchart.timestamp",
        "passive.flowchart.x",
        "media.panel",
        "passive.media.mail_panel",
        "passive.planning.decision_card",
        "passive.planning.milestone_card",
        "passive.planning.risk_card",
        "passive.planning.task_card",
        "plot.bar",
        "plot.contour",
        "plot.heatmap",
        "plot.histogram",
        "plot.point_cloud",
        "plot.scatter",
        "plot.streamlines",
        "plot.surface",
        "web.page_viewer",
    }
)

BUILTIN_CONTRACT_CONTRIBUTIONS = (
    (
        PluginContractManifest(
            data_type_families=CORE_DATA_TYPE_FAMILIES,
            data_types=CORE_DATA_TYPES,
            data_conversions=CORE_DATA_CONVERSIONS,
        ),
        CORE_DATA_TYPE_OWNER_ID,
        CORE_DATA_TYPE_OWNER_VERSION,
        "ea_node_editor.nodes.core_data_types",
        True,
    ),
    (
        COREX_GEOMETRY_COORDINATE_SYSTEM_VALUE_CANDIDATE_CONTRACT_MANIFEST,
        COREX_GEOMETRY_CONTRACTS_OWNER_ID,
        COREX_GEOMETRY_CONTRACTS_OWNER_VERSION,
        "ea_node_editor.nodes.builtins.geometry_contracts",
        False,
    ),
    (
        COREX_VOXEL_CONTRACT_MANIFEST,
        COREX_VOXEL_CONTRACTS_OWNER_ID,
        COREX_VOXEL_CONTRACTS_OWNER_VERSION,
        "ea_node_editor.nodes.builtins.voxel_contracts",
        False,
    ),
    (
        COREX_MESH_PARAMETER_CANDIDATE_CONTRACT_MANIFEST,
        COREX_MESH_CONTRACTS_OWNER_ID,
        COREX_MESH_CONTRACTS_OWNER_VERSION,
        "ea_node_editor.nodes.builtins.mesh_contracts",
        False,
    ),
    (
        COREX_FEM_CONTRACT_MANIFEST,
        COREX_FEM_CONTRACTS_OWNER_ID,
        COREX_FEM_CONTRACTS_OWNER_VERSION,
        "ea_node_editor.nodes.builtins.fem_contracts",
        False,
    ),
    (
        COREX_AI_ML_VECTOR_DATABASE_CANDIDATE_CONTRACT_MANIFEST,
        COREX_AI_ML_CONTRACTS_OWNER_ID,
        COREX_AI_ML_CONTRACTS_OWNER_VERSION,
        "ea_node_editor.nodes.builtins.ai_ml_contracts",
        False,
    ),
    (
        COREX_RICH_VALUE_LLM_CANDIDATE_CONTRACT_MANIFEST,
        COREX_RICH_VALUE_OWNER_ID,
        COREX_RICH_VALUE_OWNER_VERSION,
        "ea_node_editor.nodes.builtins.rich_value_nodes",
        False,
    ),
    (
        COREX_GEOMETRY_PRIMITIVES_CONTRACT_MANIFEST,
        COREX_GEOMETRY_PRIMITIVES_OWNER_ID,
        COREX_GEOMETRY_PRIMITIVES_OWNER_VERSION,
        "ea_node_editor.nodes.builtins.geometry_primitives",
        True,
    ),
    (
        COREX_CORE_VALUE_CONTRACT_MANIFEST,
        COREX_CORE_VALUE_OWNER_ID,
        COREX_CORE_VALUE_OWNER_VERSION,
        "ea_node_editor.nodes.builtins.core_values",
        False,
    ),
    (
        COREX_TREE_PATH_CONTRACT_MANIFEST,
        COREX_TREE_PATH_OWNER_ID,
        COREX_TREE_PATH_OWNER_VERSION,
        "ea_node_editor.nodes.builtins.tree_path",
        False,
    ),
    (
        COREX_CORE_MEDIA_CONTRACT_MANIFEST,
        COREX_CORE_MEDIA_OWNER_ID,
        COREX_CORE_MEDIA_OWNER_VERSION,
        "ea_node_editor.nodes.builtins.core_media",
        False,
    ),
    (
        COREX_UNITS_CONTRACT_MANIFEST,
        COREX_UNITS_OWNER_ID,
        COREX_UNITS_OWNER_VERSION,
        "ea_node_editor.nodes.builtins.units",
        False,
    ),
    (
        COREX_SPATIAL_VALUES_COORDINATE_SYSTEM_CANDIDATE_CONTRACT_MANIFEST,
        COREX_SPATIAL_VALUES_OWNER_ID,
        COREX_SPATIAL_VALUES_OWNER_VERSION,
        "ea_node_editor.nodes.builtins.spatial_values",
        False,
    ),
    (
        COREX_VIEWER_VIEWPORT_CONTRACT_MANIFEST,
        COREX_VIEWER_VIEWPORT_OWNER_ID,
        COREX_VIEWER_VIEWPORT_OWNER_VERSION,
        "ea_node_editor.nodes.builtins.viewer_viewport",
        False,
    ),
    (
        COREX_REPORTING_CONTRACT_MANIFEST,
        COREX_REPORTING_OWNER_ID,
        COREX_REPORTING_OWNER_VERSION,
        "ea_node_editor.nodes.builtins.reporting",
        False,
    ),
    (
        COREX_SECURITY_CONTRACT_MANIFEST,
        COREX_SECURITY_OWNER_ID,
        COREX_SECURITY_OWNER_VERSION,
        "ea_node_editor.nodes.builtins.security_contracts",
        False,
    ),
    (
        PluginContractManifest(
            data_type_families=SSH_SFTP_DATA_TYPE_FAMILIES,
            data_types=SSH_SFTP_DATA_TYPES,
        ),
        SSH_SFTP_DATA_TYPE_OWNER_ID,
        "",
        "ea_node_editor.nodes.builtins.integrations_ssh_sftp",
        False,
    ),
)


def register_internal_builtin_functions(
    registry: NodeRegistry,
    *,
    generation_root: Path,
) -> tuple[str, ...]:
    """Register packaged inert source as the reserved built-in function bundle."""

    from ea_node_editor.nodes.builtin_functions import source_modules

    source_items = source_modules()
    module_names = [name for name, _source in source_items]
    if len(module_names) != len({name.casefold() for name in module_names}):
        raise ValueError("Internal built-in source module names must be unique")
    members: dict[str, bytes] = {}
    for raw_path, source in source_items:
        path = validated_plugin_member_path(raw_path, root_python=True)
        if not isinstance(source, str):
            raise TypeError("Internal built-in function source must be a string")
        payload = source.encode("utf-8")
        if len(payload) > PLUGIN_SOURCE_LIMIT:
            raise ValueError("Internal built-in function source is too large")
        members[path] = payload
    manifest: dict[str, object] = {
        "schema_version": 2,
        "name": "corex_builtin_functions",
        "version": "1.0.0",
        "author": "COREX",
        "description": "Ordinary built-in nodes implemented with the function SDK.",
        "modules": module_names,
        "sources": [
            {"path": path, "sha256": source_digest(members[path])}
            for path in module_names
        ],
        "assets": [],
        "nodes": [],
    }
    declarations = module_declarations(
        manifest,
        members,
        filename_prefix=INTERNAL_BUILTIN_FUNCTION_OWNER_ID,
        owner_id=INTERNAL_BUILTIN_FUNCTION_OWNER_ID,
        allow_reserved_ids=True,
    )
    manifest["nodes"] = node_inventory(declarations)
    missing = missing_bundle_imports(members, set(module_names))
    prepared = PreparedFunctionBundle(
        owner_id=INTERNAL_BUILTIN_FUNCTION_OWNER_ID,
        version="1.0.0",
        manifest=manifest,
        members=members,
        declarations=declarations,
        unavailable_reason=(
            f"{missing[0]} is not included in this COREX bundle." if missing else ""
        ),
        log_label=INTERNAL_BUILTIN_FUNCTION_OWNER_ID,
        source_root=Path(__file__).parent / "builtin_functions",
    )
    bundle, _generation = materialize_prepared_function_bundle(
        prepared,
        Path(generation_root),
    )
    function_entries = build_function_entries(
        prepared,
        bundle,
        {module_path: None for module_path, _declaration in prepared.declarations},
    )
    for entry in function_entries:
        registry._register_trusted_python_function(  # noqa: SLF001
            entry.spec,
            entry.function_ref,
            provenance=None,
            owner_id=entry.owner_id,
            unavailable_reason=entry.unavailable_reason,
        )
    bundles = (*registry.plugin_bundle_refs(), bundle)
    fingerprint = registry_plugin_fingerprint(registry, bundles)
    registry.set_python_plugin_catalog(bundles, plugin_fingerprint=fingerprint)
    return tuple(entry.spec.type_id for entry in function_entries)


def register_builtin_catalog(
    registry: NodeRegistry,
    *,
    generation_root: Path,
) -> None:
    trusted_descriptors = (
        *_TRUSTED_BUILTIN_DESCRIPTORS,
        *COREX_FEM_NODE_DESCRIPTORS,
    )
    trusted_type_ids = frozenset(
        descriptor.spec.type_id for descriptor in trusted_descriptors
    )
    if (
        len(trusted_descriptors) != len(_TRUSTED_BUILTIN_TYPE_IDS)
        or trusted_type_ids != _TRUSTED_BUILTIN_TYPE_IDS
    ):
        raise RuntimeError("Trusted built-in descriptor allowlist mismatch")

    for (
        manifest,
        owner_id,
        owner_version,
        source_label,
        replace_owner,
    ) in BUILTIN_CONTRACT_CONTRIBUTIONS:
        registry.register_plugin_bundle(
            manifest,
            (),
            owner_id=owner_id,
            owner_version=owner_version,
            source_label=source_label,
            replace_owner=replace_owner,
        )
    registry.register_descriptors(
        COREX_FEM_NODE_DESCRIPTORS,
        owner_id=COREX_FEM_CONTRACTS_OWNER_ID,
    )
    register_internal_builtin_functions(registry, generation_root=generation_root)
    registry.register_descriptors(_TRUSTED_BUILTIN_DESCRIPTORS)


__all__ = [
    "BUILTIN_CONTRACT_CONTRIBUTIONS",
    "register_builtin_catalog",
    "register_internal_builtin_functions",
]

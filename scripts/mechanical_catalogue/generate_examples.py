# Purpose: Generate the three deterministic Mechanical catalogue example projects.
# Map: subsystems/addons.md
# Tests: tests/mechanical_catalogue/test_examples.py
from __future__ import annotations

import argparse
from copy import deepcopy
from pathlib import Path
from typing import Any

from ea_node_editor.graph.invariant_kernel import GraphInvariantKernel
from ea_node_editor.graph.model import GraphModel
from ea_node_editor.nodes.bootstrap import build_default_registry
from ea_node_editor.nodes.instance_resolution import resolve_instance_ports
from ea_node_editor.nodes.registry import NodeRegistry
from ea_node_editor.persistence.serializer import JsonProjectSerializer
from ea_node_editor.settings import SCHEMA_VERSION

INCREMENT_LOAD_CODE = """if analysis is None or str(analysis.Name) != 'COREX structural A':
    raise Exception('Expected exactly COREX structural A')
matches = list(DataModel.GetObjectsByName('COREX constant load'))
if len(matches) != 1:
    raise Exception('Expected exactly one COREX constant load')
output = matches[0].XComponent.Output
if str(output.DefinitionType).split('.')[-1] != 'Discrete':
    raise Exception('Expected a one-value Discrete definition')
samples = list(output.DiscreteValues)
if int(output.DiscreteValueCount) != 1 or len(samples) != 1:
    raise Exception('Expected one scalar load value')
current_n = samples[0].ConvertUnit('N')
if str(current_n.Unit) != 'N':
    raise Exception('Could not read the load in N')
from Ansys.Core.Units import Quantity
output.DiscreteValues = [Quantity(float(current_n.Value) + 100.0, 'N')]
result = analysis.ObjectId
"""

EXAMPLE_FILES = {
    "table": "mechanical_table_to_signal_plot.cxproj",
    "image": "mechanical_camera_image_workflows.cxproj",
    "mutation": "mechanical_mutate_snippet_save.cxproj",
}

EXPECTED_EDGES = {
    "table": (
        ("table_open", "model", "table_search", "model"),
        ("table_open", "model", "table_fea", "model"),
        ("table_search", "objects", "table_fea", "source"),
        ("table_fea", "tables", "table_plot", "values"),
    ),
    "image": (
        ("image_open", "model", "image_camera", "model"),
        ("image_open", "model", "image_batch", "model"),
        ("image_camera", "views", "image_batch", "views"),
        ("image_open", "model", "image_preview", "model"),
        ("image_preview", "images", "image_panel", "source"),
    ),
    "mutation": (
        ("mutation_open", "model", "mutation_script", "source_model"),
        ("mutation_script", "model", "mutation_snippet", "source_model"),
        ("mutation_snippet", "model", "mutation_save", "source_model"),
    ),
}


def _node(
    registry: NodeRegistry,
    node_id: str,
    type_id: str,
    x: float,
    y: float,
    *,
    title: str | None = None,
    properties: dict[str, Any] | None = None,
    custom_width: float | None = None,
    custom_height: float | None = None,
) -> dict[str, Any]:
    spec = registry.get_spec(type_id)
    normalized_properties = registry.default_properties(type_id)
    normalized_properties.update(properties or {})
    normalized_properties = registry.normalize_properties(
        type_id, normalized_properties, include_defaults=True
    )
    ports = resolve_instance_ports(spec, normalized_properties)
    return {
        "node_id": node_id,
        "type_id": type_id,
        "title": title or spec.display_name,
        "x": x,
        "y": y,
        "collapsed": False,
        "expanded_settings_group_ids": list(
            spec.default_expanded_settings_group_ids
        ),
        "locked": False,
        "properties": normalized_properties,
        "exposed_ports": {
            port.key: bool(port.required or port.exposed) for port in ports
        },
        "port_labels": {},
        "port_modifiers": {},
        "principal_input_port_id": None,
        "visual_style": {},
        "links": [],
        "comments": [],
        "parent_node_id": None,
        "custom_width": custom_width,
        "custom_height": custom_height,
    }


def _edge(index: int, edge: tuple[str, str, str, str]) -> dict[str, Any]:
    source_node_id, source_port_key, target_node_id, target_port_key = edge
    return {
        "edge_id": f"edge_{index:02d}_{source_node_id}_{target_node_id}",
        "source_node_id": source_node_id,
        "source_port_key": source_port_key,
        "target_node_id": target_node_id,
        "target_port_key": target_port_key,
        "enabled": True,
        "input_order": 0,
        "label": "",
        "visual_style": {},
    }


def _document(
    registry: NodeRegistry,
    key: str,
    title: str,
    nodes: list[dict[str, Any]],
) -> dict[str, Any]:
    workspace_id = f"ws_mechanical_{key}"
    return {
        "schema_version": SCHEMA_VERSION,
        "project_id": f"proj_mechanical_{key}",
        "name": title,
        "active_workspace_id": workspace_id,
        "workspace_order": [workspace_id],
        "workspaces": [
            {
                "workspace_id": workspace_id,
                "name": title,
                "dirty": False,
                "active_view_id": f"view_mechanical_{key}",
                "views": [
                    {
                        "view_id": f"view_mechanical_{key}",
                        "name": "Workflow",
                        "zoom": 0.85,
                        "pan_x": 80.0,
                        "pan_y": 100.0,
                        "scope_path": [],
                        "hide_optional_ports": False,
                    }
                ],
                "nodes": nodes,
                "edges": [
                    _edge(index, edge)
                    for index, edge in enumerate(EXPECTED_EDGES[key], start=1)
                ],
            }
        ],
        "metadata": {
            "artifact_store": {"artifacts": {}, "staged": {}},
            "workflow_settings": {
                "general": {
                    "project_name": title,
                    "author": "COREX",
                    "description": "Runnable Mechanical catalogue example",
                }
            },
        },
    }


def example_documents(registry: NodeRegistry) -> dict[str, dict[str, Any]]:
    return {
        "table": _document(
            registry,
            "table",
            "Mechanical Table to Signal Plot",
            [
                _node(registry, "table_open", "mechanical.open_model", 0, 80),
                _node(
                    registry,
                    "table_search",
                    "mechanical.search_tree",
                    360,
                    40,
                    properties={
                        "filter": "name",
                        "query": "COREX tabular load",
                        "match": "exact",
                        "case_sensitive": True,
                        "include_hidden_properties": False,
                        "invert": False,
                    },
                ),
                _node(
                    registry,
                    "table_fea",
                    "mechanical.fea_table",
                    720,
                    80,
                    properties={
                        "family": "model_definition",
                        "table": "XComponent",
                        "component": "all",
                        "units": "source",
                        "sets": [],
                    },
                ),
                _node(
                    registry,
                    "table_plot",
                    "plot.signal",
                    1080,
                    80,
                    properties={
                        "title": "COREX tabular load",
                        "x_mode": "auto",
                        "x_column": "",
                        "y_columns": [],
                        "max_points": 4000,
                    },
                    custom_width=480,
                    custom_height=300,
                ),
            ],
        ),
        "image": _document(
            registry,
            "image",
            "Mechanical Camera and Image Workflows",
            [
                _node(registry, "image_open", "mechanical.open_model", 0, 180),
                _node(
                    registry,
                    "image_camera",
                    "mechanical.camera_views",
                    360,
                    20,
                    properties={"include": "saved"},
                ),
                _node(
                    registry,
                    "image_batch",
                    "mechanical.export_image",
                    720,
                    20,
                    title="Two objects by saved views",
                    properties={
                        "objects": ["COREX cylinder", "COREX witness"],
                        "views": [],
                        "width": 640,
                        "height": 400,
                        "background": "white",
                        "fit_view": False,
                        "folder": "",
                        "file_name": "{object}_{view}.png",
                        "overwrite": False,
                    },
                ),
                _node(
                    registry,
                    "image_preview",
                    "mechanical.export_image",
                    360,
                    380,
                    title="Current display preview",
                    properties={
                        "objects": [],
                        "views": [],
                        "width": 320,
                        "height": 200,
                        "background": "model",
                        "fit_view": False,
                        "folder": "",
                    },
                ),
                _node(
                    registry,
                    "image_panel",
                    "media.panel",
                    720,
                    420,
                    title="Current display preview",
                    custom_width=480,
                    custom_height=300,
                ),
            ],
        ),
        "mutation": _document(
            registry,
            "mutation",
            "Mechanical Mutate, Snippet, and Save",
            [
                _node(registry, "mutation_open", "mechanical.open_model", 0, 80),
                _node(
                    registry,
                    "mutation_script",
                    "mechanical.run_script",
                    360,
                    20,
                    properties={
                        "environments": ["COREX structural A"],
                        "scope": "each_environment",
                        "code": INCREMENT_LOAD_CODE,
                        "timeout_s": 600.0,
                        "stop_on_error": True,
                    },
                ),
                _node(
                    registry,
                    "mutation_snippet",
                    "mechanical.apdl_snippet",
                    720,
                    20,
                    properties={
                        "environments": [],
                        "name": "COREX all commands",
                        "commands": "/prep7\n  ! all body v1  \n/COM,all-end\n",
                        "steps": "all",
                        "selected_steps": [1],
                        "issue_solve_command": False,
                    },
                ),
                _node(
                    registry,
                    "mutation_save",
                    "mechanical.save_model",
                    1080,
                    80,
                    properties={
                        "file": "",
                        "format": "auto",
                        "include_results": True,
                        "include_user_files": True,
                        "include_external_imported_files": True,
                        "overwrite": False,
                    },
                ),
            ],
        ),
    }


def edge_signatures(project) -> tuple[tuple[str, str, str, str], ...]:  # noqa: ANN001
    workspace = project.workspaces[project.active_workspace_id]
    return tuple(
        (
            edge.source_node_id,
            edge.source_port_key,
            edge.target_node_id,
            edge.target_port_key,
        )
        for edge in workspace.edges.values()
    )


def assert_example(project, registry: NodeRegistry, key: str) -> None:  # noqa: ANN001
    workspace = project.workspaces[project.active_workspace_id]
    actual_edges = edge_signatures(project)
    assert len(actual_edges) == len(EXPECTED_EDGES[key])
    assert set(actual_edges) == set(EXPECTED_EDGES[key])
    kernel = GraphInvariantKernel(
        registry=registry,
        workspace_nodes=workspace.nodes,
        workspace_edges=workspace.edges.values(),
    )
    for edge in workspace.edges.values():
        assert kernel.validate_registry_edge(
            source_node_id=edge.source_node_id,
            source_port_key=edge.source_port_key,
            target_node_id=edge.target_node_id,
            target_port_key=edge.target_port_key,
            require_source_output=True,
            require_target_input=True,
            require_exposed_ports=True,
            require_compatible_ports=True,
        ) is not None
    for node in workspace.nodes.values():
        assert node.expanded_settings_group_ids == registry.get_spec(
            node.type_id
        ).default_expanded_settings_group_ids


def inject_fixture_paths(
    project,
    registry: NodeRegistry,
    *,
    source_path: str,
    save_path: str | None = None,
) -> None:  # noqa: ANN001
    """Inject run-specific paths without persisting them in the authored examples."""
    model = GraphModel(project)
    mutations = model.validated_mutations(project.active_workspace_id, registry)
    workspace = model.active_workspace
    open_node = next(
        node for node in workspace.nodes.values() if node.type_id == "mechanical.open_model"
    )
    mutations.set_node_property(open_node.node_id, "file", source_path)
    save_nodes = [
        node for node in workspace.nodes.values() if node.type_id == "mechanical.save_model"
    ]
    if save_nodes:
        if save_path is None:
            raise ValueError("The mutation example requires an explicit save_path")
        mutations.set_node_property(save_nodes[0].node_id, "file", save_path)


def generate_examples(output_dir: Path) -> tuple[Path, ...]:
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    registry = build_default_registry(include_public_plugins=False)
    serializer = JsonProjectSerializer(registry)
    written: list[Path] = []
    for key, raw_document in example_documents(registry).items():
        project = serializer.from_document(deepcopy(raw_document))
        assert_example(project, registry, key)
        persistent_document = serializer.to_persistent_document(project)
        destination = output_dir / EXAMPLE_FILES[key]
        serializer.save_document(str(destination), persistent_document)
        assert_example(serializer.load(str(destination)), registry, key)
        written.append(destination)
    return tuple(written)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("examples"))
    args = parser.parse_args()
    for path in generate_examples(args.output_dir):
        print(path)


if __name__ == "__main__":
    main()

# Purpose: Verify deterministic Mechanical examples, registry contracts, and documentation.
# Map: subsystems/addons.md
# Tests: tests/mechanical_catalogue/test_examples.py

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from ea_node_editor.nodes.bootstrap import build_default_registry
from ea_node_editor.persistence.serializer import JsonProjectSerializer
from scripts.mechanical_catalogue.generate_examples import (
    EXAMPLE_FILES,
    EXPECTED_EDGES,
    INCREMENT_LOAD_CODE,
    assert_example,
    generate_examples,
    inject_fixture_paths,
)

ROOT = Path(__file__).resolve().parents[2]
EXAMPLES = ROOT / "examples"
GUIDE = ROOT / "docs" / "MECHANICAL_CATALOGUE.md"

EXPECTED_NODES = {
    "table": {
        "table_open": "mechanical.open_model",
        "table_search": "mechanical.search_tree",
        "table_fea": "mechanical.fea_table",
        "table_plot": "plot.signal",
    },
    "image": {
        "image_open": "mechanical.open_model",
        "image_camera": "mechanical.camera_views",
        "image_batch": "mechanical.export_image",
        "image_preview": "mechanical.export_image",
        "image_panel": "media.panel",
    },
    "mutation": {
        "mutation_open": "mechanical.open_model",
        "mutation_script": "mechanical.run_script",
        "mutation_snippet": "mechanical.apdl_snippet",
        "mutation_save": "mechanical.save_model",
    },
}


@pytest.fixture(scope="module")
def registry():  # noqa: ANN201
    return build_default_registry(include_public_plugins=False)


@pytest.mark.parametrize("key", tuple(EXAMPLE_FILES))
def test_examples_load_normally_with_exact_nodes_edges_and_expansion_state(
    registry, key: str
) -> None:  # noqa: ANN001
    project = JsonProjectSerializer(registry).load(str(EXAMPLES / EXAMPLE_FILES[key]))
    workspace = project.workspaces[project.active_workspace_id]

    assert {node_id: node.type_id for node_id, node in workspace.nodes.items()} == (
        EXPECTED_NODES[key]
    )
    assert_example(project, registry, key)
    assert len(workspace.edges) == len(EXPECTED_EDGES[key])


def test_table_example_matches_the_retained_registered_definition_recipe(registry) -> None:  # noqa: ANN001
    project = JsonProjectSerializer(registry).load(
        str(EXAMPLES / EXAMPLE_FILES["table"])
    )
    nodes = project.workspaces[project.active_workspace_id].nodes

    assert nodes["table_open"].properties["file"] == ""
    assert nodes["table_search"].properties == {
        "filter": "name",
        "query": "COREX tabular load",
        "match": "exact",
        "case_sensitive": True,
        "include_hidden_properties": False,
        "invert": False,
    }
    assert {
        key: nodes["table_fea"].properties[key]
        for key in ("family", "table", "component", "units", "sets")
    } == {
        "family": "model_definition",
        "table": "XComponent",
        "component": "all",
        "units": "source",
        "sets": [],
    }
    assert {
        key: nodes["table_plot"].properties[key]
        for key in ("x_mode", "x_column", "y_columns", "max_points")
    } == {"x_mode": "auto", "x_column": "", "y_columns": [], "max_points": 4000}


def test_image_example_keeps_batch_and_single_item_preview_separate(registry) -> None:  # noqa: ANN001
    project = JsonProjectSerializer(registry).load(
        str(EXAMPLES / EXAMPLE_FILES["image"])
    )
    nodes = project.workspaces[project.active_workspace_id].nodes

    assert nodes["image_open"].properties["file"] == ""
    assert nodes["image_camera"].properties["include"] == "saved"
    assert {
        key: nodes["image_batch"].properties[key]
        for key in (
            "objects",
            "views",
            "width",
            "height",
            "background",
            "fit_view",
            "folder",
            "file_name",
            "overwrite",
        )
    } == {
        "objects": ["COREX cylinder", "COREX witness"],
        "views": [],
        "width": 640,
        "height": 400,
        "background": "white",
        "fit_view": False,
        "folder": "",
        "file_name": "{object}_{view}.png",
        "overwrite": False,
    }
    assert {
        key: nodes["image_preview"].properties[key]
        for key in ("objects", "views", "width", "height", "background", "fit_view", "folder")
    } == {
        "objects": [],
        "views": [],
        "width": 320,
        "height": 200,
        "background": "model",
        "fit_view": False,
        "folder": "",
    }


def test_mutation_example_reads_current_discrete_value_then_adds_100_n(registry) -> None:  # noqa: ANN001
    project = JsonProjectSerializer(registry).load(
        str(EXAMPLES / EXAMPLE_FILES["mutation"])
    )
    nodes = project.workspaces[project.active_workspace_id].nodes
    script = nodes["mutation_script"].properties
    snippet = nodes["mutation_snippet"].properties
    save = nodes["mutation_save"].properties

    assert script == {
        "environments": ["COREX structural A"],
        "scope": "each_environment",
        "code": INCREMENT_LOAD_CODE,
        "timeout_s": 600.0,
        "stop_on_error": True,
    }
    assert "DefinitionType).split('.')[-1] != 'Discrete'" in INCREMENT_LOAD_CODE
    assert "float(current_n.Value) + 100.0" in INCREMENT_LOAD_CODE
    assert "600" not in INCREMENT_LOAD_CODE
    assert "except" not in INCREMENT_LOAD_CODE
    assert snippet == {
        "environments": [],
        "name": "COREX all commands",
        "commands": "/prep7\n  ! all body v1  \n/COM,all-end\n",
        "steps": "all",
        "selected_steps": [1],
        "issue_solve_command": False,
    }
    assert save == {
        "file": "",
        "format": "auto",
        "include_results": True,
        "include_user_files": True,
        "include_external_imported_files": True,
        "overwrite": False,
    }


def test_example_generation_is_deterministic_through_the_normal_serializer(
    registry, tmp_path: Path
) -> None:  # noqa: ANN001
    generated = generate_examples(tmp_path)
    assert {path.name for path in generated} == set(EXAMPLE_FILES.values())
    for path in generated:
        assert path.read_bytes().replace(b"\r\n", b"\n") == (
            EXAMPLES / path.name
        ).read_bytes().replace(b"\r\n", b"\n")
        project = JsonProjectSerializer(registry).load(str(path))
        key = next(key for key, name in EXAMPLE_FILES.items() if name == path.name)
        assert_example(project, registry, key)


@pytest.mark.parametrize("key", tuple(EXAMPLE_FILES))
def test_authored_examples_contain_no_fixture_or_transient_runtime_identity(key: str) -> None:
    path = EXAMPLES / EXAMPLE_FILES[key]
    document = json.loads(path.read_text(encoding="utf-8"))
    text = path.read_text(encoding="utf-8").casefold()
    nodes = document["workspaces"][0]["nodes"]

    assert next(node for node in nodes if node["type_id"] == "mechanical.open_model")[
        "properties"
    ]["file"] == ""
    assert "c:\\users\\" not in text
    assert "artifacts/verification_logs" not in text
    for transient_key in (
        "catalogue_id",
        "document_id",
        "producer_iteration",
        "producer_node_id",
        "producer_path",
        "run_id",
        "selector_code",
        "session_id",
    ):
        assert f'"{transient_key}"' not in text


def test_fixture_paths_are_injected_only_through_validated_mutation(registry) -> None:  # noqa: ANN001
    serializer = JsonProjectSerializer(registry)
    table = serializer.load(str(EXAMPLES / EXAMPLE_FILES["table"]))
    mutation = serializer.load(str(EXAMPLES / EXAMPLE_FILES["mutation"]))

    inject_fixture_paths(table, registry, source_path="fixture/source.mechdb")
    inject_fixture_paths(
        mutation,
        registry,
        source_path="fixture/source.mechdb",
        save_path="fixture/output.mechdb",
    )

    table_nodes = table.workspaces[table.active_workspace_id].nodes
    mutation_nodes = mutation.workspaces[mutation.active_workspace_id].nodes
    assert table_nodes["table_open"].properties["file"] == "fixture/source.mechdb"
    assert mutation_nodes["mutation_open"].properties["file"] == "fixture/source.mechdb"
    assert mutation_nodes["mutation_save"].properties["file"] == "fixture/output.mechdb"
    assert_example(table, registry, "table")
    assert_example(mutation, registry, "mutation")
    assert '"file": ""' in (
        EXAMPLES / EXAMPLE_FILES["mutation"]
    ).read_text(encoding="utf-8")


def _guide_section(guide: str, spec) -> str:  # noqa: ANN001
    heading = f"### {spec.display_name} (`{spec.type_id}`)"
    start = guide.index(heading)
    match = re.search(r"\n#{2,3} ", guide[start + len(heading) :])
    end = len(guide) if match is None else start + len(heading) + match.start()
    return guide[start:end]


def test_guide_advertises_the_exact_final_mechanical_registry_contract(registry) -> None:  # noqa: ANN001
    guide = GUIDE.read_text(encoding="utf-8")
    mechanical_specs = [
        registry.get_spec(type_id)
        for type_id in (
            "mechanical.open_model",
            "mechanical.search_tree",
            "mechanical.fea_table",
            "mechanical.camera_views",
            "mechanical.export_image",
            "mechanical.run_script",
            "mechanical.apdl_snippet",
            "mechanical.save_model",
        )
    ]

    assert sum(len(spec.ports) for spec in mechanical_specs) == 74
    assert sum(1 for spec in mechanical_specs for port in spec.ports if port.direction == "in") == 52
    assert sum(1 for spec in mechanical_specs for port in spec.ports if port.direction == "out") == 22
    for spec in mechanical_specs:
        section = _guide_section(guide, spec)
        documented_keys = re.findall(r"^\| `([^`]+)` \| (?:In|Out) \|", section, re.MULTILINE)
        assert documented_keys == [port.key for port in spec.ports]
        for port in spec.ports:
            direction = "In" if port.direction == "in" else "Out"
            assert (
                f"| `{port.key}` | {direction} | `{port.data_type}` / "
                f"{port.data_access.title()}"
            ) in section
        for group in spec.settings_groups:
            assert f"`{group.group_id}` (**{group.label}**" in section
        for group_id in spec.default_expanded_settings_group_ids:
            assert f"`{group_id}` (**" in section
            assert "expanded" in section.split(f"`{group_id}`", 1)[1].split("\n", 1)[0]

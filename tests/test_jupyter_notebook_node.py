from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from PyQt6.QtCore import QUrl

from ea_node_editor.graph.model import GraphModel
from ea_node_editor.graph.records import NodeInstance
from ea_node_editor.common.artifact_refs import format_managed_artifact_ref
from ea_node_editor.persistence.artifact_store import ProjectArtifactStore
from ea_node_editor.settings import (
    PROJECT_ARTIFACT_STORE_METADATA_KEY,
    PROJECT_NODE_INPUTS_DIRNAME,
)
from ea_node_editor.ui_qml.graph_scene_payload import build_jupyter_notebook_payload
from ea_node_editor.nodes.bootstrap import build_default_registry
from ea_node_editor.nodes.builtins.jupyter_notebook import (
    JUPYTER_NOTEBOOK_FRONTEND_LAB,
    JUPYTER_NOTEBOOK_FRONTEND_NOTEBOOK,
    JUPYTER_NOTEBOOK_NODE_PLUGINS,
    JUPYTER_NOTEBOOK_SURFACE_FAMILY,
    JUPYTER_NOTEBOOK_SURFACE_VARIANT,
    JUPYTER_NOTEBOOK_TYPE_ID,
    normalize_jupyter_notebook_frontend,
    normalize_jupyter_notebook_properties,
    sanitize_jupyter_notebook_server_state,
)
from ea_node_editor.nodes.execution_context import ExecutionContext
from ea_node_editor.ui_qml.graph_scene_payload import GraphScenePayloadBuilder
from ea_node_editor.ui_qml.surface_contracts import surface_spec_payload_for_node_type

_EXPECTED_CARDINAL_PASSIVE_PORTS = ("top", "right", "bottom", "left")


def _context() -> ExecutionContext:
    return ExecutionContext(
        run_id="run",
        node_id="node",
        workspace_id="ws",
        inputs={},
        properties={},
        emit_log=lambda _level, _message: None,
    )


class JupyterNotebookNodeTests(unittest.TestCase):
    def test_descriptor_defaults_register_passive_jupyter_surface_contract(self) -> None:
        registry = build_default_registry()
        spec = registry.get_spec(JUPYTER_NOTEBOOK_TYPE_ID)

        self.assertEqual(spec.type_id, "code.jupyter_notebook")
        self.assertEqual(spec.display_name, "Jupyter Notebook")
        self.assertEqual(spec.category_path, ("Code",))
        self.assertEqual(spec.category, "Code")
        self.assertEqual(spec.runtime_behavior, "passive")
        self.assertFalse(spec.collapsible)
        self.assertEqual(spec.surface_family, JUPYTER_NOTEBOOK_SURFACE_FAMILY)
        self.assertEqual(spec.surface_variant, JUPYTER_NOTEBOOK_SURFACE_VARIANT)
        self.assertEqual(spec.render_quality.supported_quality_tiers, ("full", "proxy"))

        self.assertEqual([port.key for port in spec.ports], list(_EXPECTED_CARDINAL_PASSIVE_PORTS))
        self.assertTrue(all(port.direction == "neutral" for port in spec.ports))
        self.assertTrue(all(port.kind == "flow" and port.data_type == "flow" for port in spec.ports))
        self.assertTrue(all(port.side == port.key for port in spec.ports))
        self.assertTrue(all(port.allow_multiple_connections for port in spec.ports))

        properties = {prop.key: prop for prop in spec.properties}
        self.assertEqual(
            list(properties),
            [
                "notebook_ref",
                "kernel_name",
                "frontend",
                "autostart",
                "server_state",
                "show_title",
                "show_frame",
                "preview_ref",
            ],
        )
        self.assertEqual(properties["notebook_ref"].type, "str")
        self.assertEqual(properties["notebook_ref"].inspector_editor, "path")
        self.assertEqual(properties["notebook_ref"].group, "Source")
        self.assertIn(".ipynb", properties["notebook_ref"].file_filter)
        self.assertEqual(properties["kernel_name"].type, "str")
        self.assertEqual(properties["frontend"].type, "enum")
        self.assertEqual(
            properties["frontend"].enum_values,
            (JUPYTER_NOTEBOOK_FRONTEND_NOTEBOOK, JUPYTER_NOTEBOOK_FRONTEND_LAB),
        )
        self.assertEqual(properties["frontend"].inspector_editor, "enum")
        self.assertEqual(properties["autostart"].type, "bool")
        self.assertTrue(properties["autostart"].default)
        self.assertEqual(properties["server_state"].type, "json")
        self.assertFalse(properties["server_state"].inspector_visible)
        self.assertFalse(properties["show_title"].inspector_visible)
        self.assertFalse(properties["show_frame"].inspector_visible)
        self.assertEqual(properties["preview_ref"].type, "json")
        self.assertFalse(properties["preview_ref"].inspector_visible)

        defaults = registry.default_properties(JUPYTER_NOTEBOOK_TYPE_ID)
        self.assertEqual(defaults["notebook_ref"], "")
        self.assertEqual(defaults["kernel_name"], "")
        self.assertEqual(defaults["frontend"], JUPYTER_NOTEBOOK_FRONTEND_NOTEBOOK)
        self.assertTrue(defaults["autostart"])
        self.assertEqual(defaults["server_state"], {})
        self.assertTrue(defaults["show_title"])
        self.assertTrue(defaults["show_frame"])
        self.assertEqual(defaults["preview_ref"], {})

    def test_plugin_execution_is_passive_noop(self) -> None:
        [plugin_cls] = JUPYTER_NOTEBOOK_NODE_PLUGINS
        plugin = plugin_cls()

        self.assertEqual(plugin.spec().runtime_behavior, "passive")
        self.assertEqual(plugin.execute(_context()).outputs, {})

    def test_frontend_normalization_defaults_invalid_values_to_notebook(self) -> None:
        self.assertEqual(
            normalize_jupyter_notebook_frontend(JUPYTER_NOTEBOOK_FRONTEND_LAB),
            JUPYTER_NOTEBOOK_FRONTEND_LAB,
        )
        self.assertEqual(normalize_jupyter_notebook_frontend("LAB"), JUPYTER_NOTEBOOK_FRONTEND_LAB)
        self.assertEqual(
            normalize_jupyter_notebook_frontend("retro"),
            JUPYTER_NOTEBOOK_FRONTEND_NOTEBOOK,
        )
        self.assertEqual(
            normalize_jupyter_notebook_frontend(None),
            JUPYTER_NOTEBOOK_FRONTEND_NOTEBOOK,
        )

    def test_server_state_sanitization_strips_connection_secrets(self) -> None:
        sanitized = sanitize_jupyter_notebook_server_state(
            {
                "zoom": 1.4,
                "scroll_top": 120,
                "last_frontend": "lab",
                "token": "super-secret-token",
                "url": "http://127.0.0.1:54213/notebooks/x.ipynb",
                "port": 54213,
                "password": "hunter2",
                "Authorization": "Bearer abc",
            }
        )

        self.assertEqual(sanitized, {"zoom": 1.4, "scroll_top": 120, "last_frontend": "lab"})
        serialized = json.dumps(sanitized, sort_keys=True).lower()
        for unsafe in ("token", "127.0.0.1", "password", "bearer", "hunter2"):
            self.assertNotIn(unsafe, serialized)

    def test_server_state_sanitization_rejects_non_mapping(self) -> None:
        self.assertEqual(sanitize_jupyter_notebook_server_state(None), {})
        self.assertEqual(sanitize_jupyter_notebook_server_state("nope"), {})

    def test_property_normalization_filters_unknown_keys_and_sanitizes_state(self) -> None:
        normalized = normalize_jupyter_notebook_properties(
            {
                "notebook_ref": "saved://abc",
                "frontend": "LAB",
                "server_state": {"zoom": 1.1, "token": "secret"},
                "autostart": True,
                "unexpected_key": "drop me",
            }
        )

        self.assertNotIn("unexpected_key", normalized)
        self.assertEqual(normalized["notebook_ref"], "saved://abc")
        self.assertEqual(normalized["frontend"], JUPYTER_NOTEBOOK_FRONTEND_LAB)
        self.assertEqual(normalized["server_state"], {"zoom": 1.1})


class JupyterNotebookSurfaceTests(unittest.TestCase):
    def test_surface_spec_routes_to_generic_web_page_host(self) -> None:
        spec = build_default_registry().get_spec(JUPYTER_NOTEBOOK_TYPE_ID)

        payload = surface_spec_payload_for_node_type(type_id=JUPYTER_NOTEBOOK_TYPE_ID, spec=spec)

        self.assertEqual(payload["family"], "jupyter")
        self.assertEqual(payload["variant"], "notebook")
        self.assertEqual(payload["component_key"], "jupyter_notebook")
        self.assertEqual(payload["qml_component"], "jupyter/GraphJupyterNotebookSurface.qml")
        self.assertEqual(payload["layout"]["content_region"], "body")
        self.assertTrue(payload["fullscreen"]["supported"])
        self.assertEqual(payload["fullscreen"]["content_kind"], "jupyter_notebook")
        self.assertEqual(payload["fullscreen"]["action_kind"], "surface")
        self.assertEqual(payload["metadata"]["web_surface"], "jupyter_notebook")
        self.assertFalse(payload["metadata"]["qwebchannel_allowed"])

    def test_graph_payload_emits_jupyter_payload_with_availability_gates(self) -> None:
        registry = build_default_registry()
        model = GraphModel()
        workspace = model.active_workspace
        properties = registry.default_properties(JUPYTER_NOTEBOOK_TYPE_ID)
        properties.update(
            {
                "notebook_ref": "saved://nb_local",
                "frontend": "LAB",
                "server_state": {
                    "zoom": 1.25,
                    "token": "super-secret",
                    "url": "http://127.0.0.1:50101/notebooks/x.ipynb",
                },
            }
        )
        node = model.add_node(
            workspace.workspace_id,
            JUPYTER_NOTEBOOK_TYPE_ID,
            "Analysis Notebook",
            20.0,
            30.0,
            properties=properties,
        )

        nodes_payload, _backdrops, _minimap_nodes, _edges = (
            GraphScenePayloadBuilder().rebuild_partitioned_models(
                model=model,
                registry=registry,
                workspace_id=workspace.workspace_id,
                scope_path=(),
                graph_theme_bridge=None,
            )
        )

        payload = next(item for item in nodes_payload if item["node_id"] == node.node_id)
        jupyter_payload = payload["jupyter_notebook_payload"]
        self.assertEqual(jupyter_payload["content_kind"], "jupyter_notebook")
        self.assertEqual(jupyter_payload["notebook_ref"], "saved://nb_local")
        self.assertEqual(jupyter_payload["frontend"], JUPYTER_NOTEBOOK_FRONTEND_LAB)
        self.assertTrue(jupyter_payload["autostart"])
        self.assertEqual(jupyter_payload["server_state"], {"zoom": 1.25})
        self.assertIn("jupyter_available", jupyter_payload)
        self.assertIn("webengine_available", jupyter_payload)

        # Connection secrets must never reach the scene payload nor the persisted props.
        self.assertEqual(payload["properties"]["server_state"], {"zoom": 1.25})
        serialized = json.dumps(payload, sort_keys=True).lower()
        for unsafe in ("super-secret", "127.0.0.1", '"token"'):
            self.assertNotIn(unsafe, serialized)

    def test_managed_notebook_ref_resolves_to_on_disk_ipynb(self) -> None:
        registry = build_default_registry()
        spec = registry.get_spec(JUPYTER_NOTEBOOK_TYPE_ID)
        properties = registry.default_properties(JUPYTER_NOTEBOOK_TYPE_ID)
        artifact_id = "jupyter_notebook_local"
        managed_ref = format_managed_artifact_ref(artifact_id)
        properties.update({"notebook_ref": managed_ref})
        node = NodeInstance(
            node_id="node_jupyter_managed",
            type_id=JUPYTER_NOTEBOOK_TYPE_ID,
            title="Managed Notebook",
            x=20.0,
            y=30.0,
            properties=properties,
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            project_path = Path(temp_dir) / "managed_notebook.cxproj"
            store = ProjectArtifactStore(project_path=project_path)
            paths = store.node_artifact_paths(
                artifact_id=artifact_id,
                workspace_id="ws",
                node_id=node.node_id,
                node_title=node.title,
                node_type="Jupyter Notebook",
                io_dir=PROJECT_NODE_INPUTS_DIRNAME,
                subdirectory="jupyter/notebooks",
                filename="analysis.ipynb",
            )
            ipynb_path = store.layout.absolute_path_for_relative(paths.managed_relative_path)
            ipynb_path.parent.mkdir(parents=True, exist_ok=True)
            ipynb_path.write_text('{"cells": [], "nbformat": 4, "nbformat_minor": 5}', encoding="utf-8")
            project_metadata = {
                PROJECT_ARTIFACT_STORE_METADATA_KEY: {
                    "artifacts": {
                        artifact_id: {
                            "relative_path": paths.managed_relative_path,
                            **paths.metadata,
                        }
                    },
                    "staged": {},
                }
            }

            payload = build_jupyter_notebook_payload(
                workspace_id="ws",
                node=node,
                spec=spec,
                project_path=str(project_path),
                project_metadata=project_metadata,
            )

        self.assertEqual(payload["notebook_ref"], managed_ref)
        self.assertEqual(payload["notebook_location"], QUrl.fromLocalFile(str(ipynb_path)).toString())
        self.assertEqual(payload["content_kind"], "jupyter_notebook")


if __name__ == "__main__":
    unittest.main()

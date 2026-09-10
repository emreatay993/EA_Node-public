from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from PyQt6.QtCore import QObject, QUrl

from ea_node_editor.graph.boundary_adapters import build_graph_boundary_adapters
from ea_node_editor.graph.model import GraphModel
from ea_node_editor.graph.records import NodeInstance
from ea_node_editor.nodes.bootstrap import build_default_registry
from ea_node_editor.nodes.builtins.web_viewer import (
    WEB_PAGE_VIEWER_DISPLAY_MODE_FIT_PAGE,
    WEB_PAGE_VIEWER_DISPLAY_MODE_FIT_WIDTH,
    WEB_PAGE_VIEWER_DISPLAY_MODE_RESPONSIVE,
    WEB_PAGE_VIEWER_NODE_PLUGINS,
    WEB_PAGE_VIEWER_SURFACE_FAMILY,
    WEB_PAGE_VIEWER_SURFACE_VARIANT,
    WEB_PAGE_VIEWER_TYPE_ID,
    normalize_web_page_viewer_browser_state,
    normalize_web_page_viewer_display_mode,
)
from ea_node_editor.nodes.execution_context import ExecutionContext
from ea_node_editor.common.artifact_refs import format_managed_artifact_ref
from ea_node_editor.persistence.artifact_store import ProjectArtifactStore
from ea_node_editor.settings import PROJECT_ARTIFACT_STORE_METADATA_KEY, PROJECT_NODE_INPUTS_DIRNAME
from ea_node_editor.ui_qml.graph_scene_payload import (
    GraphScenePayloadBuilder,
    build_content_fullscreen_web_page_payload,
)
from ea_node_editor.ui_qml.graph_theme_bridge import GraphThemeBridge
from ea_node_editor.ui_qml.graph_geometry.standard_metrics import (
    node_surface_metrics,
    resolved_node_surface_size,
)
from ea_node_editor.ui_qml.surface_contracts import (
    fullscreen_content_kind_for_node_type,
    surface_spec_payload_for_node_type,
)

_EXPECTED_CARDINAL_PASSIVE_PORTS = ("top", "right", "bottom", "left")
WEB_PAGE_VIEWER_FIXTURE_INDEX = (
    Path(__file__).resolve().parent / "fixtures" / "web_page_viewer" / "index.html"
)


class _ProjectContextHost(QObject):
    def __init__(self, *, project_path: Path, model: GraphModel) -> None:
        super().__init__()
        self.project_path = str(project_path)
        self.model = model


def _context() -> ExecutionContext:
    return ExecutionContext(
        run_id="run",
        node_id="node",
        workspace_id="ws",
        inputs={},
        properties={},
        emit_log=lambda _level, _message: None,
    )


class WebPageViewerNodeTests(unittest.TestCase):
    def test_descriptor_defaults_register_passive_web_surface_contract(self) -> None:
        registry = build_default_registry()
        spec = registry.get_spec(WEB_PAGE_VIEWER_TYPE_ID)

        self.assertEqual(spec.type_id, "web.page_viewer")
        self.assertEqual(spec.display_name, "Web Page Viewer")
        self.assertEqual(spec.category_path, ("Web",))
        self.assertEqual(spec.category, "Web")
        self.assertEqual(spec.runtime_behavior, "passive")
        self.assertFalse(spec.collapsible)
        self.assertEqual(spec.surface_family, WEB_PAGE_VIEWER_SURFACE_FAMILY)
        self.assertEqual(spec.surface_variant, WEB_PAGE_VIEWER_SURFACE_VARIANT)
        self.assertEqual([port.key for port in spec.ports], list(_EXPECTED_CARDINAL_PASSIVE_PORTS))
        self.assertTrue(all(port.direction == "neutral" for port in spec.ports))
        self.assertTrue(all(port.kind == "flow" and port.data_type == "flow" for port in spec.ports))
        self.assertTrue(all(port.side == port.key for port in spec.ports))
        self.assertTrue(all(port.allow_multiple_connections for port in spec.ports))

        properties = {prop.key: prop for prop in spec.properties}
        self.assertEqual(
            list(properties),
            [
                "start_location",
                "display_mode",
                "show_title",
                "show_frame",
                "persist_browser_state",
                "browser_state",
                "preview_ref",
            ],
        )
        self.assertEqual(properties["start_location"].type, "str")
        self.assertEqual(properties["start_location"].inspector_editor, "path")
        self.assertEqual(properties["start_location"].group, "Source")
        self.assertEqual(properties["display_mode"].type, "enum")
        self.assertEqual(
            properties["display_mode"].enum_values,
            (
                WEB_PAGE_VIEWER_DISPLAY_MODE_RESPONSIVE,
                WEB_PAGE_VIEWER_DISPLAY_MODE_FIT_WIDTH,
                WEB_PAGE_VIEWER_DISPLAY_MODE_FIT_PAGE,
            ),
        )
        self.assertEqual(properties["display_mode"].inspector_editor, "enum")
        self.assertEqual(properties["display_mode"].group, "Display")
        self.assertEqual(properties["show_title"].type, "bool")
        self.assertTrue(properties["show_title"].default)
        self.assertFalse(properties["show_title"].inspector_visible)
        self.assertEqual(properties["show_frame"].type, "bool")
        self.assertTrue(properties["show_frame"].default)
        self.assertFalse(properties["show_frame"].inspector_visible)
        self.assertEqual(properties["persist_browser_state"].type, "bool")
        self.assertEqual(properties["browser_state"].type, "json")
        self.assertEqual(properties["preview_ref"].type, "json")
        self.assertFalse(properties["browser_state"].inspector_visible)
        self.assertFalse(properties["preview_ref"].inspector_visible)

        defaults = registry.default_properties(WEB_PAGE_VIEWER_TYPE_ID)
        self.assertEqual(defaults["start_location"], "")
        self.assertEqual(defaults["display_mode"], WEB_PAGE_VIEWER_DISPLAY_MODE_FIT_WIDTH)
        self.assertTrue(defaults["show_title"])
        self.assertTrue(defaults["show_frame"])
        self.assertTrue(defaults["persist_browser_state"])
        self.assertEqual(defaults["browser_state"], {})
        self.assertEqual(defaults["preview_ref"], {})

    def test_plugin_execution_is_passive_noop(self) -> None:
        [plugin_cls] = WEB_PAGE_VIEWER_NODE_PLUGINS
        plugin = plugin_cls()

        self.assertEqual(plugin.spec().runtime_behavior, "passive")
        self.assertEqual(plugin.execute(_context()).outputs, {})

    def test_display_mode_normalization_defaults_invalid_values_to_fit_width(self) -> None:
        self.assertEqual(
            normalize_web_page_viewer_display_mode(WEB_PAGE_VIEWER_DISPLAY_MODE_FIT_WIDTH),
            WEB_PAGE_VIEWER_DISPLAY_MODE_FIT_WIDTH,
        )
        self.assertEqual(
            normalize_web_page_viewer_display_mode("FIT_PAGE"),
            WEB_PAGE_VIEWER_DISPLAY_MODE_FIT_PAGE,
        )
        self.assertEqual(
            normalize_web_page_viewer_display_mode("image_contain"),
            WEB_PAGE_VIEWER_DISPLAY_MODE_FIT_WIDTH,
        )

    def test_surface_spec_routes_to_generic_web_page_host(self) -> None:
        spec = build_default_registry().get_spec(WEB_PAGE_VIEWER_TYPE_ID)

        payload = surface_spec_payload_for_node_type(type_id=WEB_PAGE_VIEWER_TYPE_ID, spec=spec)

        self.assertEqual(payload["family"], "web")
        self.assertEqual(payload["variant"], "page_viewer")
        self.assertEqual(payload["component_key"], "web_page")
        self.assertEqual(payload["qml_component"], "../web/WebPageHost.qml")
        self.assertEqual(payload["layout"]["content_region"], "body")
        self.assertTrue(payload["fullscreen"]["supported"])
        self.assertEqual(payload["fullscreen"]["content_kind"], "web_page")
        self.assertEqual(payload["fullscreen"]["action_kind"], "web_page")
        self.assertEqual(payload["metadata"]["web_surface"], "page_viewer")
        self.assertFalse(payload["metadata"]["qwebchannel_allowed"])
        self.assertEqual(
            fullscreen_content_kind_for_node_type(type_id=WEB_PAGE_VIEWER_TYPE_ID, spec=spec),
            "web_page",
        )

    def test_empty_graph_payload_reserves_web_page_status_space(self) -> None:
        registry = build_default_registry()
        spec = registry.get_spec(WEB_PAGE_VIEWER_TYPE_ID)
        model = GraphModel()
        workspace = model.active_workspace
        node = model.add_node(
            workspace.workspace_id,
            WEB_PAGE_VIEWER_TYPE_ID,
            "Web Page Viewer",
            20.0,
            30.0,
            properties=registry.default_properties(WEB_PAGE_VIEWER_TYPE_ID),
        )

        metrics = node_surface_metrics(node, spec, {node.node_id: node})
        resolved_width, resolved_height = resolved_node_surface_size(
            node,
            spec,
            {node.node_id: node},
        )
        payload_builder = GraphScenePayloadBuilder(
            boundary_adapters=build_graph_boundary_adapters(
                node_size_resolver=resolved_node_surface_size,
            ),
        )
        nodes_payload, _backdrops, _minimap_nodes, _edges = (
            payload_builder.rebuild_partitioned_models(
                model=model,
                registry=registry,
                workspace_id=workspace.workspace_id,
                scope_path=(),
                graph_theme_bridge=None,
            )
        )
        payload = next(item for item in nodes_payload if item["node_id"] == node.node_id)

        self.assertEqual(metrics.body_height, 260.0)
        self.assertGreater(metrics.default_width, 210.0)
        self.assertGreaterEqual(metrics.default_height, 300.0)
        self.assertEqual(resolved_width, metrics.default_width)
        self.assertEqual(resolved_height, metrics.default_height)
        self.assertEqual(payload["width"], metrics.default_width)
        self.assertEqual(payload["height"], metrics.default_height)
        self.assertEqual(payload["surface_metrics"]["body_height"], 260.0)

    def test_fullscreen_payload_normalizes_and_remains_unprivileged(self) -> None:
        registry = build_default_registry()
        spec = registry.get_spec(WEB_PAGE_VIEWER_TYPE_ID)
        properties = registry.default_properties(WEB_PAGE_VIEWER_TYPE_ID)
        properties.update(
            {
                "start_location": "https://example.com/docs",
                "display_mode": WEB_PAGE_VIEWER_DISPLAY_MODE_FIT_WIDTH,
                "browser_state": {
                    "current_url": "https://example.com/current",
                    "zoom_factor": 1.25,
                },
            }
        )
        node = NodeInstance(
            node_id="node_web_page",
            type_id=WEB_PAGE_VIEWER_TYPE_ID,
            title="Reference Site",
            x=20.0,
            y=30.0,
            properties=properties,
        )

        payload = build_content_fullscreen_web_page_payload(
            workspace_id="ws",
            node=node,
            spec=spec,
        )

        self.assertEqual(payload["workspace_id"], "ws")
        self.assertEqual(payload["node_id"], "node_web_page")
        self.assertEqual(payload["type_id"], WEB_PAGE_VIEWER_TYPE_ID)
        self.assertEqual(payload["content_kind"], "web_page")
        self.assertEqual(payload["title"], "Reference Site")
        self.assertEqual(payload["surface_family"], "web")
        self.assertEqual(payload["surface_variant"], "page_viewer")
        self.assertEqual(payload["surface_spec"]["component_key"], "web_page")
        self.assertEqual(payload["surface_spec"]["fullscreen"]["content_kind"], "web_page")
        self.assertEqual(payload["current_location"], "https://example.com/current")
        self.assertEqual(payload["display_mode"], WEB_PAGE_VIEWER_DISPLAY_MODE_FIT_WIDTH)
        self.assertEqual(
            payload["properties"]["display_mode"],
            WEB_PAGE_VIEWER_DISPLAY_MODE_FIT_WIDTH,
        )
        self.assertEqual(payload["navigation_decision"]["target_url"], "https://example.com/current")
        self.assertTrue(payload["navigation_decision"]["allowed"])
        self.assertFalse(payload["navigation_decision"]["qwebchannel_allowed"])
        self.assertFalse(payload["qwebchannel_allowed"])
        self.assertIsNone(payload.get("web_surface_bridge"))
        self.assertNotIn("access_profile", payload)
        self.assertNotIn("allowed_origins", payload)
        self.assertNotIn("blocked_origins", payload)
        self.assertNotIn("home_location", payload)
        serialized_keys = json.dumps(payload, sort_keys=True).lower()
        self.assertNotIn("excalidraw", serialized_keys)
        self.assertNotIn("qwebchannel", json.dumps(payload["properties"], sort_keys=True).lower())

    def test_remote_start_location_is_normalized_and_allowed(self) -> None:
        registry = build_default_registry()
        spec = registry.get_spec(WEB_PAGE_VIEWER_TYPE_ID)
        properties = registry.default_properties(WEB_PAGE_VIEWER_TYPE_ID)
        properties.update({"start_location": "example.com"})
        node = NodeInstance(
            node_id="node_web_page_remote",
            type_id=WEB_PAGE_VIEWER_TYPE_ID,
            title="Remote Site",
            x=20.0,
            y=30.0,
            properties=properties,
        )

        payload = build_content_fullscreen_web_page_payload(
            workspace_id="ws",
            node=node,
            spec=spec,
        )

        self.assertEqual(payload["content_kind"], "web_page")
        self.assertTrue(payload["navigation_decision"]["allowed"])
        self.assertEqual(
            payload["navigation_decision"]["target_url"], "https://example.com"
        )
        self.assertFalse(payload["navigation_decision"]["is_local"])
        self.assertFalse(payload["qwebchannel_allowed"])

    def test_local_fixture_start_location_is_allowed_and_unprivileged(self) -> None:
        registry = build_default_registry()
        spec = registry.get_spec(WEB_PAGE_VIEWER_TYPE_ID)
        properties = registry.default_properties(WEB_PAGE_VIEWER_TYPE_ID)
        properties.update({"start_location": str(WEB_PAGE_VIEWER_FIXTURE_INDEX)})
        node = NodeInstance(
            node_id="node_web_page_local",
            type_id=WEB_PAGE_VIEWER_TYPE_ID,
            title="Local Fixture",
            x=20.0,
            y=30.0,
            properties=properties,
        )

        payload = build_content_fullscreen_web_page_payload(
            workspace_id="ws",
            node=node,
            spec=spec,
        )

        self.assertEqual(payload["content_kind"], "web_page")
        self.assertNotIn("access_profile", payload)
        self.assertTrue(payload["navigation_decision"]["allowed"])
        self.assertEqual(
            payload["navigation_decision"]["target_url"],
            WEB_PAGE_VIEWER_FIXTURE_INDEX.resolve().as_uri(),
        )
        self.assertEqual(payload["navigation_decision"]["origin"], "file://")
        self.assertTrue(payload["navigation_decision"]["is_local"])
        self.assertFalse(payload["navigation_decision"]["qwebchannel_allowed"])
        self.assertFalse(payload["qwebchannel_allowed"])

    def test_managed_local_html_start_location_resolves_for_navigation(self) -> None:
        registry = build_default_registry()
        spec = registry.get_spec(WEB_PAGE_VIEWER_TYPE_ID)
        properties = registry.default_properties(WEB_PAGE_VIEWER_TYPE_ID)
        artifact_id = "html_source_local"
        managed_ref = format_managed_artifact_ref(artifact_id)
        properties.update(
            {
                "start_location": managed_ref,
                "browser_state": {
                    "current_url": "file:///C:/old/location.html",
                    "zoom_factor": 1.25,
                },
            }
        )
        node = NodeInstance(
            node_id="node_web_page_managed",
            type_id=WEB_PAGE_VIEWER_TYPE_ID,
            title="Managed HTML",
            x=20.0,
            y=30.0,
            properties=properties,
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            project_path = Path(temp_dir) / "managed_html.cxproj"
            store = ProjectArtifactStore(project_path=project_path)
            paths = store.node_artifact_paths(
                artifact_id=artifact_id,
                workspace_id="ws",
                node_id=node.node_id,
                node_title=node.title,
                node_type="Web Page Viewer",
                io_dir=PROJECT_NODE_INPUTS_DIRNAME,
                subdirectory="web/html",
                filename="index.html",
            )
            html_path = store.layout.absolute_path_for_relative(paths.managed_relative_path)
            html_path.parent.mkdir(parents=True, exist_ok=True)
            html_path.write_text("<!doctype html><title>Managed</title>", encoding="utf-8")
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

            payload = build_content_fullscreen_web_page_payload(
                workspace_id="ws",
                node=node,
                spec=spec,
                project_path=str(project_path),
                project_metadata=project_metadata,
            )

        expected_navigation_url = QUrl.fromLocalFile(str(html_path)).toString()
        expected_target_url = html_path.resolve().as_uri()
        self.assertEqual(payload["start_location"], managed_ref)
        self.assertEqual(payload["current_location"], managed_ref)
        self.assertEqual(payload["navigation_location"], expected_navigation_url)
        self.assertTrue(payload["navigation_decision"]["allowed"])
        self.assertEqual(payload["navigation_decision"]["target_url"], expected_target_url)
        self.assertTrue(payload["navigation_decision"]["is_local"])
        self.assertEqual(payload["browser_state"]["current_url"], "file:///C:/old/location.html")

    def test_graph_payload_resolves_staged_local_html_start_location_for_navigation(self) -> None:
        registry = build_default_registry()
        model = GraphModel()
        workspace = model.active_workspace
        artifact_id = "html_source_local"

        with tempfile.TemporaryDirectory() as temp_dir:
            project_path = Path(temp_dir) / "staged_html.cxproj"
            store = ProjectArtifactStore(project_path=project_path)
            properties = registry.default_properties(WEB_PAGE_VIEWER_TYPE_ID)
            properties.update({"start_location": store.staged_ref(artifact_id)})
            node = model.add_node(
                workspace.workspace_id,
                WEB_PAGE_VIEWER_TYPE_ID,
                "Staged HTML",
                20.0,
                30.0,
                properties=properties,
            )
            paths = store.node_artifact_paths(
                artifact_id=artifact_id,
                workspace_id=workspace.workspace_id,
                node_id=node.node_id,
                node_title=node.title,
                node_type="Web Page Viewer",
                io_dir=PROJECT_NODE_INPUTS_DIRNAME,
                subdirectory="web/html",
                filename="index.html",
            )
            staged_path = store.layout.absolute_path_for_relative(paths.staged_relative_path)
            staged_path.parent.mkdir(parents=True, exist_ok=True)
            staged_path.write_text("<!doctype html><title>Staged</title>", encoding="utf-8")
            store.register_staged_entry(
                artifact_id,
                relative_path=paths.staged_relative_path,
                extra=paths.metadata,
            )
            model.project.replace_metadata({PROJECT_ARTIFACT_STORE_METADATA_KEY: store.metadata})
            host = _ProjectContextHost(project_path=project_path, model=model)
            graph_theme_bridge = GraphThemeBridge(host, theme_id="graph_stitch_dark")

            nodes_payload, _backdrops, _minimap_nodes, _edges = (
                GraphScenePayloadBuilder().rebuild_partitioned_models(
                    model=model,
                    registry=registry,
                    workspace_id=workspace.workspace_id,
                    scope_path=(),
                    graph_theme_bridge=graph_theme_bridge,
                )
            )

        web_payload = next(
            item for item in nodes_payload if item["node_id"] == node.node_id
        )["web_page_payload"]
        self.assertEqual(web_payload["start_location"], store.staged_ref(artifact_id))
        self.assertEqual(web_payload["current_location"], store.staged_ref(artifact_id))
        self.assertEqual(web_payload["navigation_location"], QUrl.fromLocalFile(str(staged_path)).toString())
        self.assertTrue(web_payload["navigation_decision"]["allowed"])
        self.assertEqual(web_payload["navigation_decision"]["target_url"], staged_path.resolve().as_uri())
        self.assertTrue(web_payload["navigation_decision"]["is_local"])

    def test_browser_state_accepts_project_managed_html_refs(self) -> None:
        managed_ref = format_managed_artifact_ref("html_source_local")

        state = normalize_web_page_viewer_browser_state(
            {"current_url": managed_ref, "zoom_factor": 1.25, "page_title": "  Offline\nFixture  "},
            require_location=True,
        )

        self.assertEqual(
            state,
            {
                "current_url": managed_ref,
                "zoom_factor": 1.25,
                "page_title": "Offline Fixture",
            },
        )

    def test_graph_payload_projects_persisted_browser_state_for_preview(self) -> None:
        registry = build_default_registry()
        model = GraphModel()
        workspace = model.active_workspace
        properties = registry.default_properties(WEB_PAGE_VIEWER_TYPE_ID)
        properties.update(
            {
                "start_location": "",
                "browser_state": {
                    "current_url": WEB_PAGE_VIEWER_FIXTURE_INDEX.resolve().as_uri(),
                    "zoom_factor": 1.5,
                },
            }
        )
        node = model.add_node(
            workspace.workspace_id,
            WEB_PAGE_VIEWER_TYPE_ID,
            "Offline Fixture",
            20.0,
            30.0,
            properties=properties,
        )

        nodes_payload, _backdrops, _minimap_nodes, _edges = GraphScenePayloadBuilder().rebuild_partitioned_models(
            model=model,
            registry=registry,
            workspace_id=workspace.workspace_id,
            scope_path=(),
            graph_theme_bridge=None,
        )

        payload = next(item for item in nodes_payload if item["node_id"] == node.node_id)
        web_payload = payload["web_page_payload"]
        self.assertEqual(web_payload["current_location"], WEB_PAGE_VIEWER_FIXTURE_INDEX.resolve().as_uri())
        self.assertEqual(web_payload["browser_state"]["zoom_factor"], 1.5)
        self.assertTrue(web_payload["navigation_decision"]["allowed"])
        self.assertEqual(web_payload["navigation_decision"]["origin"], "file://")

    def test_graph_payload_sanitizes_persisted_browser_state(self) -> None:
        registry = build_default_registry()
        model = GraphModel()
        workspace = model.active_workspace
        properties = registry.default_properties(WEB_PAGE_VIEWER_TYPE_ID)
        properties.update(
            {
                "start_location": "https://example.com/start",
                "browser_state": {
                    "current_location": "example.com/current",
                    "zoom": 1.75,
                    "page_title": "  Example\nCurrent  ",
                    "cookies": "secret",
                    "local_storage": {"token": "secret"},
                    "session_storage": {"csrf": "secret"},
                    "credentials": {"password": "secret"},
                    "page_content": "<html>secret</html>",
                },
                "cookies": "top-level secret",
                "credentials": {"password": "top-level secret"},
            }
        )
        node = model.add_node(
            workspace.workspace_id,
            WEB_PAGE_VIEWER_TYPE_ID,
            "Sanitized Fixture",
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
        expected_state = {
            "current_url": "https://example.com/current",
            "zoom_factor": 1.75,
            "page_title": "Example Current",
        }
        self.assertEqual(payload["properties"]["browser_state"], expected_state)
        self.assertEqual(payload["web_page_payload"]["browser_state"], expected_state)
        self.assertEqual(payload["web_page_payload"]["current_location"], "https://example.com/current")
        serialized_payload = json.dumps(payload, sort_keys=True).lower()
        for unsafe_key in (
            "cookie",
            "credential",
            "password",
            "session_storage",
            "local_storage",
            "page_content",
            "html",
        ):
            self.assertNotIn(unsafe_key, serialized_payload)

    def test_graph_payload_ignores_browser_state_when_persistence_disabled(self) -> None:
        registry = build_default_registry()
        model = GraphModel()
        workspace = model.active_workspace
        properties = registry.default_properties(WEB_PAGE_VIEWER_TYPE_ID)
        properties.update(
            {
                "start_location": "https://example.com/start",
                "persist_browser_state": False,
                "browser_state": {
                    "current_url": "https://example.com/private",
                    "zoom_factor": 1.75,
                },
            }
        )
        node = model.add_node(
            workspace.workspace_id,
            WEB_PAGE_VIEWER_TYPE_ID,
            "Start Fixture",
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
        web_payload = payload["web_page_payload"]
        self.assertEqual(payload["properties"]["browser_state"], {})
        self.assertFalse(web_payload["persist_browser_state"])
        self.assertEqual(web_payload["browser_state"], {})
        self.assertEqual(web_payload["current_location"], "https://example.com/start")
        self.assertEqual(web_payload["navigation_decision"]["target_url"], "https://example.com/start")

    def test_canvas_browser_state_persist_projects_into_graph_payload(self) -> None:
        # Mirrors the canvas persistence sink: WebPageHost -> GraphNodeHost
        # webPageBrowserStateSink -> sceneCommandBridge.set_node_property writes
        # the live browser state; the rebuilt graph payload must project the
        # navigated URL/zoom (off-screen reload + project save/reopen path).
        registry = build_default_registry()
        model = GraphModel()
        workspace = model.active_workspace
        properties = registry.default_properties(WEB_PAGE_VIEWER_TYPE_ID)
        properties.update({"start_location": ""})
        node = model.add_node(
            workspace.workspace_id,
            WEB_PAGE_VIEWER_TYPE_ID,
            "Offline Fixture",
            20.0,
            30.0,
            properties=properties,
        )

        fixture_uri = WEB_PAGE_VIEWER_FIXTURE_INDEX.resolve().as_uri()
        model.set_node_property(
            workspace.workspace_id,
            node.node_id,
            "browser_state",
            {"current_url": fixture_uri, "zoom_factor": 1.5},
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

        web_payload = next(
            item for item in nodes_payload if item["node_id"] == node.node_id
        )["web_page_payload"]
        self.assertEqual(web_payload["current_location"], fixture_uri)
        self.assertEqual(web_payload["browser_state"]["current_url"], fixture_uri)
        self.assertEqual(web_payload["browser_state"]["zoom_factor"], 1.5)
        self.assertTrue(web_payload["navigation_decision"]["allowed"])


if __name__ == "__main__":
    unittest.main()

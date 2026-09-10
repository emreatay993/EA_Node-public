from __future__ import annotations

import ast
import importlib.util
import re
import subprocess
import unittest
from pathlib import Path

from scripts import verification_manifest as manifest

_REPO_ROOT = Path(__file__).resolve().parents[1]


def _tracked_repo_files() -> list[str]:
    result = subprocess.run(
        ["git", "ls-files"],
        cwd=_REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.splitlines()


def _top_level_function_names(relative_path: str) -> set[str]:
    module_path = _REPO_ROOT / relative_path
    module_text = module_path.read_text(encoding="utf-8")
    module_ast = ast.parse(module_text, filename=str(module_path))
    return {
        node.name
        for node in module_ast.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def _parse_module(relative_path: str) -> ast.Module:
    module_path = _REPO_ROOT / relative_path
    return ast.parse(module_path.read_text(encoding="utf-8"), filename=str(module_path))


def _top_level_class_names(relative_path: str) -> set[str]:
    module_ast = _parse_module(relative_path)
    return {
        node.name
        for node in module_ast.body
        if isinstance(node, ast.ClassDef)
    }


def _class_method_names(relative_path: str, class_name: str) -> set[str]:
    module_ast = _parse_module(relative_path)
    for node in module_ast.body:
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            return {
                child.name
                for child in node.body
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))
            }
    raise AssertionError(f"Class not found: {class_name}")


def _qualified_name(node: ast.AST | None) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _qualified_name(node.value)
        if parent is None:
            return node.attr
        return f"{parent}.{node.attr}"
    return None


def _assigned_call_names(relative_path: str) -> set[tuple[str, str]]:
    assignments: set[tuple[str, str]] = set()
    module_ast = _parse_module(relative_path)
    for node in ast.walk(module_ast):
        if not isinstance(node, ast.Assign):
            continue
        if not isinstance(node.value, ast.Call):
            continue
        call_name = _qualified_name(node.value.func)
        if call_name is None:
            continue
        for target in node.targets:
            if isinstance(target, ast.Name):
                assignments.add((target.id, call_name))
    return assignments


def _js_function_names(relative_path: str) -> set[str]:
    source = (_REPO_ROOT / relative_path).read_text(encoding="utf-8")
    return set(re.findall(r"(?m)^function\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(", source))


class DeadCodeHygienePythonHelperBoundaryTests(unittest.TestCase):
    def test_generated_packaging_metadata_is_not_tracked(self) -> None:
        tracked_generated_metadata = [
            path
            for path in _tracked_repo_files()
            if ".egg-info/" in path or path.endswith(".egg-info")
        ]

        self.assertEqual([], tracked_generated_metadata)

    def test_corex_no_legacy_guardrail_inventory_matches_final_baseline(self) -> None:
        inventory = manifest.COREX_NO_LEGACY_GUARDRAIL_INVENTORY
        categories = {surface.category for surface in inventory}
        owners_by_category = {surface.category: surface.owner_packet for surface in inventory}

        self.assertEqual(
            categories,
            set(manifest.COREX_NO_LEGACY_REQUIRED_GUARDRAIL_CATEGORIES),
        )
        self.assertEqual(owners_by_category, manifest.COREX_NO_LEGACY_GUARDRAIL_OWNER_PACKETS)
        self.assertEqual(
            len(inventory),
            len({(surface.category, surface.path, surface.names) for surface in inventory}),
        )
        self.assertEqual(
            {surface.expectation for surface in inventory},
            {
                manifest.COREX_NO_LEGACY_GUARDRAIL_PRESENT,
                manifest.COREX_NO_LEGACY_GUARDRAIL_ABSENT,
                manifest.COREX_NO_LEGACY_GUARDRAIL_PATH_ABSENT,
            },
        )
        for surface in inventory:
            with self.subTest(category=surface.category):
                path = _REPO_ROOT / surface.path
                if surface.expectation == manifest.COREX_NO_LEGACY_GUARDRAIL_PATH_ABSENT:
                    self.assertFalse(path.exists(), msg=f"Guardrail target still exists: {surface.path}")
                    continue
                if surface.expectation == manifest.COREX_NO_LEGACY_GUARDRAIL_ABSENT and not path.exists():
                    continue
                self.assertTrue(path.exists(), msg=f"Guardrail target missing: {surface.path}")
                text = path.read_text(encoding="utf-8")
                for name in surface.names:
                    if surface.expectation == manifest.COREX_NO_LEGACY_GUARDRAIL_PRESENT:
                        self.assertIn(name, text)
                    else:
                        self.assertNotIn(name, text)

    def test_removed_internal_helpers_do_not_reappear(self) -> None:
        expectations = {
            "ea_node_editor/execution/protocol_codec.py": {"dict_to_event_type"},
            "ea_node_editor/ui/shell/library_flow.py": {"input_port_is_available"},
            "ea_node_editor/ui_qml/edge_routing.py": {"inline_body_height"},
        }

        for relative_path, absent_names in expectations.items():
            function_names = _top_level_function_names(relative_path)
            for function_name in absent_names:
                with self.subTest(path=relative_path, function_name=function_name):
                    self.assertNotIn(function_name, function_names)

    def test_graph_geometry_modules_keep_extracted_helper_boundaries(self) -> None:
        edge_routing_classes = _top_level_class_names("ea_node_editor/ui_qml/edge_routing.py")
        edge_routing_functions = _top_level_function_names("ea_node_editor/ui_qml/edge_routing.py")
        graph_surface_metric_classes = _top_level_class_names(
            "ea_node_editor/ui_qml/graph_surface_metrics.py"
        )
        graph_surface_metric_functions = _top_level_function_names(
            "ea_node_editor/ui_qml/graph_surface_metrics.py"
        )
        payload_builder_functions = _top_level_function_names(
            "ea_node_editor/ui_qml/graph_scene_payload/normalize.py"
        )
        payload_factory_methods = _class_method_names(
            "ea_node_editor/ui_qml/graph_scene_payload/factory.py",
            "_GraphSceneNodePayloadFactory",
        )
        payload_builder_assignments = _assigned_call_names(
            "ea_node_editor/ui_qml/graph_scene_payload/factory.py"
        )
        self.assertTrue(
            {"_EdgeLaneOffsets", "_ResolvedEdgePayloadContext"}.issubset(edge_routing_classes)
        )
        self.assertTrue(
            {
                "_edge_payload_lane_offsets",
                "_build_edge_payload_item",
                "_resolve_edge_payload_context",
                "_resolve_edge_route",
            }.issubset(edge_routing_functions)
        )
        self.assertTrue({"resolved_node_surface_size", "_resolve_flowchart_metric_layout_state", "_build_panel_surface_metrics"}.issubset(graph_surface_metric_functions))
        self.assertIn("_FlowchartMetricLayoutState", graph_surface_metric_classes)
        self.assertNotIn("membership_candidate_size", payload_builder_functions)
        self.assertIn("membership_candidate_size", payload_factory_methods)
        self.assertIn(("surface_metrics", "self._surface_metrics"), payload_builder_assignments)

    def test_retired_context_sink_support_files_do_not_reappear(self) -> None:
        absent_paths = (
            "ea_node_editor/ui/shell/presenters.py",
            "ea_node_editor/execution/viewer_session_service_support.py",
            "ea_node_editor/ui_qml/viewer_session_bridge_support.py",
            "ea_node_editor/ui_qml/components/graph/viewer/GraphViewerSurfaceContent.qml",
        )

        for relative_path in absent_paths:
            with self.subTest(path=relative_path):
                self.assertFalse((_REPO_ROOT / relative_path).exists())

    def test_launch_and_import_shims_do_not_reappear(self) -> None:
        absent_paths = (
            "main.py",
            "ea_node_editor/telemetry/performance_harness.py",
        )

        for relative_path in absent_paths:
            with self.subTest(path=relative_path):
                self.assertFalse((_REPO_ROOT / relative_path).exists())

        self.assertIsNone(importlib.util.find_spec("ea_node_editor.telemetry.performance_harness"))

        shell_launcher = (_REPO_ROOT / "scripts" / "run.sh").read_text(encoding="utf-8")
        self.assertIn("-m ea_node_editor.bootstrap", shell_launcher)
        self.assertNotIn("main.py", shell_launcher)
        self.assertNotIn("find_worktree_python", shell_launcher)

        spec_text = (_REPO_ROOT / "ea_node_editor.spec").read_text(encoding="utf-8")
        self.assertIn('"ea_node_editor" / "bootstrap.py"', spec_text)
        self.assertNotIn('PROJECT_ROOT / "main.py"', spec_text)

        check_traceability_text = (_REPO_ROOT / "scripts" / "check_traceability.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("ea_node_editor.ui.perf.performance_harness", check_traceability_text)

    def test_package_roots_do_not_publish_lazy_getattr_barrels(self) -> None:
        for relative_path in (
            "ea_node_editor/ui/__init__.py",
            "ea_node_editor/ui/shell/__init__.py",
            "ea_node_editor/persistence/__init__.py",
            "ea_node_editor/ui/dialogs/__init__.py",
        ):
            with self.subTest(path=relative_path):
                module_text = (_REPO_ROOT / relative_path).read_text(encoding="utf-8")
                self.assertNotIn("def __getattr__", module_text)

    def test_plugin_loader_does_not_publish_executable_legacy_discovery(self) -> None:
        plugin_loader_text = (_REPO_ROOT / "ea_node_editor/nodes/plugin_loader.py").read_text(
            encoding="utf-8"
        )

        for legacy_name in (
            "module_from_spec",
            "exec_module",
            "_legacy_plugin_spec",
            "_register_plugin_classes",
            "__node_type_spec__",
            "PLUGIN_DESCRIPTORS",
        ):
            self.assertNotIn(legacy_name, plugin_loader_text)

    def test_runtime_worker_requires_snapshot_payloads(self) -> None:
        runtime_snapshot_text = (
            _REPO_ROOT / "ea_node_editor/execution/runtime_snapshot.py"
        ).read_text(encoding="utf-8")
        worker_runtime_text = (
            _REPO_ROOT / "ea_node_editor/execution/worker_runtime.py"
        ).read_text(encoding="utf-8")

        self.assertNotIn("sanitize_execution_trigger", runtime_snapshot_text)
        self.assertIn('raise ValueError("start_run requires runtime_snapshot.")', worker_runtime_text)
        self.assertNotIn("project_doc", worker_runtime_text)

    def test_qml_startup_side_effects_are_not_hidden_in_presenter_imports(self) -> None:
        presenters_text = (_REPO_ROOT / "ea_node_editor/ui/shell/presenters/__init__.py").read_text(
            encoding="utf-8"
        )
        ui_qml_text = (_REPO_ROOT / "ea_node_editor/ui_qml/__init__.py").read_text(encoding="utf-8")
        bootstrap_text = (_REPO_ROOT / "ea_node_editor/bootstrap.py").read_text(encoding="utf-8")

        self.assertNotIn("register_qml_types", presenters_text)
        self.assertNotIn("QT_QUICK_CONTROLS_STYLE", ui_qml_text)
        self.assertIn("QT_QUICK_CONTROLS_STYLE", bootstrap_text)

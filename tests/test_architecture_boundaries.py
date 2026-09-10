from __future__ import annotations

import ast
import importlib.util
import re
import unittest
from pathlib import Path

import corex
from ea_node_editor.graph import transforms
from ea_node_editor.graph.record_mutation_ops import GraphRecordMutation
from scripts import verification_manifest as manifest

REPO_ROOT = Path(__file__).resolve().parents[1]
_RETIRED_GUARDRAIL_PRESENT_NAMES = {
    (
        "graph_canvas_qml_legacy_view_alias",
        "ea_node_editor/ui_qml/components/GraphCanvas.qml",
    ): {"_legacyCanvasViewBridgeRef"},
    ("old_preference_schema_compatibility", "ea_node_editor/app_preferences.py"): {
        "_APP_PREFERENCES_MIGRATION_VERSION",
    },
    ("runtime_project_doc_trigger_compatibility", "ea_node_editor/execution/runtime_snapshot.py"): {
        "sanitize_execution_trigger",
    },
}
_EXPECTED_RUNTIME_CONTRACT_EXPORTS = frozenset(
    {
        "ArrayValue",
        "TableValue",
        "ColumnValue",
        "ARRAY_VALUE_TYPE_ID",
        "TABLE_VALUE_TYPE_ID",
        "SERIES_VALUE_TYPE_ID",
        "DATA_TREE_MODIFIER_ORDER",
        "ARRAY_DATA_REF_TYPE_ID",
        "ARRAY_SLICE_2D_REF_TYPE_ID",
        "ArrayDataRef",
        "ArrayDataResolver",
        "ArrayMaterializationOptions",
        "ArraySlice2D",
        "ArraySlice2DRef",
        "ArraySlice2DRequest",
        "BOOLEAN_DATA_TYPE_ID",
        "CONNECTION_FALLBACK_CAPABILITY",
        "COREX_VIEWER_SESSION_HANDLE_KIND",
        "DataAccess",
        "DataPath",
        "DataTree",
        "DataTreeModifier",
        "DataConversionSpec",
        "DataTypeCatalog",
        "DataTypeCatalogError",
        "DataTypeCompatibility",
        "DataTypeFamilySpec",
        "DataTypeSpec",
        "DOUBLE_DATA_TYPE_ID",
        "ENGINEERING_SCENE_DATA_TYPE_ID",
        "ENGINEERING_SELECTION_SET_DATA_TYPE_ID",
        "GRAPH_ARRAY_DATA_TYPE_ID",
        "GRAPH_DATA_TYPE_ID",
        "GRAPH_DICTIONARY_DATA_TYPE_ID",
        "INTEGER_DATA_TYPE_ID",
        "INTERVAL_1D_DATA_TYPE",
        "INTERVAL_1D_GRAPH_DATA_TYPE_ID",
        "IMAGE_VALUE_DATA_TYPE_ID",
        "IMAGE_VALUE_MAX_ENCODED_BYTES",
        "IMAGE_VALUE_SCHEMA_VERSION",
        "ImageValue",
        "Interval1D",
        "JSON_DATA_TYPE_ID",
        "JSON_VALUE_DATA_TYPE_ID",
        "PATH_DATA_TYPE_ID",
        "PLOT_EXPORT_BUNDLE_DATA_TYPE_ID",
        "NodeSolutionFact",
        "RootExecutionError",
        "RuntimeArtifactRef",
        "RuntimeArtifactScope",
        "RuntimeHandleRef",
        "RuntimeValueRef",
        "SettledPortResult",
        "SolutionDisposition",
        "SolutionFreshness",
        "SolutionOutputDescriptor",
        "SolutionPayloadLocator",
        "SolutionRecord",
        "SolutionResidency",
        "STRING_DATA_TYPE_ID",
        "STRING_LIST_DATA_TYPE_ID",
        "TABULAR_DATA_REF_TYPE_ID",
        "TABULAR_WINDOW_REF_TYPE_ID",
        "TabularArrowBatchOptions",
        "TabularColumn",
        "TabularDataRef",
        "TabularDataResolver",
        "TabularDataWindow",
        "TabularMaterializationOptions",
        "TabularSchema",
        "TabularWindowRef",
        "TypedInlineValue",
        "TabularWindowRequest",
        "TypeCarrierKind",
        "TypePersistence",
        "TypeSensitivity",
        "VIEWER_SESSION_DATA_TYPE_ID",
        "coerce_array_data_ref",
        "coerce_array_slice_2d_ref",
        "coerce_interval_1d",
        "coerce_runtime_artifact_ref",
        "coerce_runtime_handle_ref",
        "coerce_tabular_data_ref",
        "coerce_tabular_window_ref",
        "default_viewer_session_id",
        "deserialize_runtime_value",
        "serialize_runtime_value",
    }
)


def parse_module(relative_path: str) -> ast.Module:
    return ast.parse((REPO_ROOT / relative_path).read_text(encoding="utf-8-sig"), filename=relative_path)


def qualified_name(node: ast.AST | None) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = qualified_name(node.value)
        if parent is None:
            return node.attr
        return f"{parent}.{node.attr}"
    return None


def imported_names_from(tree: ast.AST, module_name: str) -> set[str]:
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == module_name:
            imported.update(alias.name for alias in node.names)
    return imported


def imported_modules(tree: ast.AST) -> set[str]:
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module is not None:
            modules.add(node.module)
        elif isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
    return modules


def top_level_imported_modules(tree: ast.Module) -> set[str]:
    modules: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.module is not None:
            modules.add(node.module)
        elif isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
    return modules


def call_names(tree: ast.AST) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            name = qualified_name(node.func)
            if name is not None:
                names.add(name)
    return names


def class_node(tree: ast.Module, class_name: str) -> ast.ClassDef:
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            return node
    raise AssertionError(f"Missing class {class_name!r}.")


def method_node(tree: ast.Module, class_name: str, method_name: str) -> ast.FunctionDef:
    owner = class_node(tree, class_name)
    for node in owner.body:
        if isinstance(node, ast.FunctionDef) and node.name == method_name:
            return node
    raise AssertionError(f"Missing method {class_name}.{method_name}.")


def class_ann_assign(tree: ast.Module, class_name: str, field_name: str) -> ast.AnnAssign:
    owner = class_node(tree, class_name)
    for node in owner.body:
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id == field_name:
            return node
    raise AssertionError(f"Missing annotated field {class_name}.{field_name}.")


def assignment_call(method: ast.FunctionDef, target_name: str) -> ast.Call:
    for node in ast.walk(method):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if qualified_name(target) == target_name and isinstance(node.value, ast.Call):
                    return node.value
    raise AssertionError(f"Missing call assignment for {target_name!r}.")


def has_call_with_keyword(tree: ast.AST, call_name: str, keyword_name: str, keyword_value: str) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and qualified_name(node.func) == call_name:
            for keyword in node.keywords:
                if keyword.arg == keyword_name and qualified_name(keyword.value) == keyword_value:
                    return True
    return False


def function_args(method: ast.FunctionDef) -> set[str]:
    return {arg.arg for arg in (*method.args.args, *method.args.kwonlyargs)}


def declared_python_names(tree: ast.AST) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            names.add(node.name)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    names.add(target.id)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.add(node.target.id)
        elif isinstance(node, ast.ImportFrom):
            names.update(alias.asname or alias.name for alias in node.names)
        elif isinstance(node, ast.Import):
            names.update(alias.asname or alias.name.partition(".")[0] for alias in node.names)
    return names


class GraphArchitectureBoundaryTests(unittest.TestCase):
    def test_shell_run_projection_has_one_direct_non_qobject_owner(self) -> None:
        def class_method_names(path: str, class_name: str) -> set[str]:
            tree = ast.parse((REPO_ROOT / path).read_text(encoding="utf-8"))
            owner = next(
                node
                for node in tree.body
                if isinstance(node, ast.ClassDef) and node.name == class_name
            )
            return {
                node.name
                for node in owner.body
                if isinstance(node, ast.FunctionDef)
            }

        projection_methods = class_method_names(
            "ea_node_editor/ui/shell/controllers/run_projection_controller.py",
            "RunProjectionController",
        )
        run_methods = class_method_names(
            "ea_node_editor/ui/shell/controllers/run_controller.py",
            "RunController",
        )
        event_methods = class_method_names(
            "ea_node_editor/ui/shell/controllers/run_event_controller.py",
            "RunEventController",
        )
        shell_methods = class_method_names(
            "ea_node_editor/ui/shell/window_state/run_and_style_state.py",
            "ShellWindowRunAndStyleStateMixin",
        )
        moved = {
            "mark_node_execution_running",
            "mark_node_execution_settled",
            "handle_solution_state_changed",
            "sync_solution_facts",
            "clear_node_execution_visualization_state",
            "set_run_failure_focus",
            "clear_run_failure_focus",
            "update_run_actions",
        }
        self.assertLessEqual(moved, projection_methods)
        self.assertTrue(moved.isdisjoint(run_methods))
        self.assertTrue(moved.isdisjoint(shell_methods))
        self.assertIn("handle_execution_event", event_methods)
        self.assertNotIn("handle_execution_event", run_methods)
        self.assertNotIn("_handle_execution_event", shell_methods)

        projection_source = (
            REPO_ROOT
            / "ea_node_editor/ui/shell/controllers/run_projection_controller.py"
        ).read_text(encoding="utf-8")
        run_source = (
            REPO_ROOT / "ea_node_editor/ui/shell/controllers/run_controller.py"
        ).read_text(encoding="utf-8")
        event_source = (
            REPO_ROOT / "ea_node_editor/ui/shell/controllers/run_event_controller.py"
        ).read_text(encoding="utf-8")
        viewer_session_source = (
            REPO_ROOT / "ea_node_editor/ui_qml/viewer_session_bridge.py"
        ).read_text(encoding="utf-8")
        composition_source = (
            REPO_ROOT / "ea_node_editor/ui/shell/composition/controllers.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn("QObject", projection_source)
        self.assertNotIn("QTimer", projection_source)
        self.assertNotIn("QObject", event_source)
        self.assertNotIn("QTimer", event_source)
        self.assertNotIn("callLater", event_source)
        self.assertNotIn("execution_event.connect", viewer_session_source)
        self.assertIn("def handle_viewer_execution_event", viewer_session_source)
        self.assertEqual(event_source.count('"handle_viewer_execution_event"'), 1)
        self.assertNotIn("cache_accepted_output_record", run_source)
        self.assertIn("run_projection_controller", composition_source)
        self.assertIn("run_event_controller.handle_execution_event", composition_source)
        self.assertNotIn("host._handle_execution_event", composition_source)
        self.assertEqual(
            composition_source.count("host.execution_event.connect("),
            1,
        )
        self.assertEqual(
            sum(
                path.read_text(encoding="utf-8").count("execution_event.connect(")
                for path in (REPO_ROOT / "ea_node_editor").rglob("*.py")
            ),
            1,
        )
        self.assertEqual(
            composition_source.count("execution_client.subscribe(host.execution_event.emit)"),
            1,
        )

    def test_graph_canvas_host_presenter_exclusively_owns_cursor_and_style_actions(self) -> None:
        owner_tree = parse_module(
            "ea_node_editor/ui/shell/presenters/graph_canvas_host_presenter.py"
        )
        shell_host_tree = parse_module("ea_node_editor/ui/shell/host_presenter.py")
        run_style_tree = parse_module(
            "ea_node_editor/ui/shell/window_state/run_and_style_state.py"
        )
        workspace_actions_tree = parse_module(
            "ea_node_editor/ui/shell/window_state/workspace_graph_actions.py"
        )
        contracts_tree = parse_module("ea_node_editor/ui/shell/presenters/contracts.py")
        owned_methods = {
            "_apply_graph_cursor",
            "set_graph_cursor_shape",
            "clear_graph_cursor_shape",
            "_active_workspace_data",
            "_passive_node_context",
            "_flow_edge_context",
            "_project_passive_style_presets",
            "_set_project_passive_style_presets",
            "edit_passive_node_style",
            "edit_flow_edge_style",
            "_write_style_clipboard",
            "_read_style_clipboard",
            "_normalize_style_clipboard_payload",
            "request_edit_passive_node_style",
            "request_reset_passive_node_style",
            "request_copy_passive_node_style",
            "request_paste_passive_node_style",
            "request_propagate_passive_node_style",
            "request_edit_flow_edge_style",
            "request_edit_flow_edge_label",
            "request_reset_flow_edge_style",
            "request_copy_flow_edge_style",
            "request_paste_flow_edge_style",
        }

        def methods(tree: ast.Module, owner: str) -> set[str]:
            return {
                node.name
                for node in class_node(tree, owner).body
                if isinstance(node, ast.FunctionDef)
            }

        graph_host = class_node(owner_tree, "GraphCanvasHostPresenter")
        self.assertTrue(owned_methods <= methods(owner_tree, "GraphCanvasHostPresenter"))
        for tree, owner in (
            (shell_host_tree, "ShellHostPresenter"),
            (run_style_tree, "ShellWindowRunAndStyleStateMixin"),
            (workspace_actions_tree, "ShellWindowWorkspaceGraphActionsMixin"),
        ):
            with self.subTest(retired_owner=owner):
                self.assertFalse(owned_methods & methods(tree, owner))
        self.assertNotIn(
            "shell_host_presenter",
            {
                node.attr
                for node in ast.walk(graph_host)
                if isinstance(node, ast.Attribute)
            },
        )
        protocol_fields = {
            node.target.id
            for node in class_node(
                contracts_tree,
                "_GraphCanvasHostPresenterHostProtocol",
            ).body
            if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name)
        }
        self.assertNotIn("shell_host_presenter", protocol_fields)
        self.assertTrue(
            {
                "model",
                "registry",
                "workspace_manager",
                "scene",
                "project_session_controller",
                "project_meta_changed",
                "quick_widget",
            }
            <= protocol_fields
        )

    def test_corex_no_legacy_guardrail_inventory_matches_current_source_anchors(self) -> None:
        for surface in manifest.COREX_NO_LEGACY_GUARDRAIL_INVENTORY:
            source_path = REPO_ROOT / surface.path
            with self.subTest(category=surface.category, path=surface.path):
                if surface.expectation == manifest.COREX_NO_LEGACY_GUARDRAIL_PATH_ABSENT:
                    self.assertFalse(source_path.exists())
                    continue
                if (
                    surface.expectation == manifest.COREX_NO_LEGACY_GUARDRAIL_ABSENT
                    and not source_path.exists()
                ):
                    continue
                self.assertTrue(source_path.is_file())
                if source_path.suffix == ".py":
                    text_names = declared_python_names(parse_module(surface.path))
                    source_text = ""
                else:
                    text_names = set()
                    source_text = source_path.read_text(encoding="utf-8")

                if surface.expectation == manifest.COREX_NO_LEGACY_GUARDRAIL_PRESENT:
                    expected_names = set(surface.names) - _RETIRED_GUARDRAIL_PRESENT_NAMES.get(
                        (surface.category, surface.path),
                        set(),
                    )
                    if source_path.suffix == ".py":
                        self.assertTrue(expected_names <= text_names)
                    else:
                        for name in expected_names:
                            self.assertIn(name, source_text)
                elif surface.expectation == manifest.COREX_NO_LEGACY_GUARDRAIL_ABSENT:
                    source_text = source_path.read_text(encoding="utf-8")
                    for name in surface.names:
                        self.assertNotIn(name, source_text)
                else:
                    self.fail(f"Unknown no-legacy guardrail expectation: {surface.expectation!r}")

    def test_graph_mutation_operations_use_graph_owned_boundary_adapters(self) -> None:
        self.assertFalse((REPO_ROOT / "ea_node_editor/graph/mutation_service.py").exists())
        validated_tree = parse_module("ea_node_editor/graph/validated_mutation.py")
        comment_tree = parse_module("ea_node_editor/graph/group_backdrop_mutation_ops.py")
        imports = imported_modules(validated_tree) | imported_modules(comment_tree)

        self.assertNotIn("ea_node_editor.ui.pdf_preview_provider", imports)
        self.assertNotIn("ea_node_editor.ui_qml.edge_routing", imports)
        self.assertNotIn("ea_node_editor.graph.transforms", imports)
        self.assertTrue(
            {"GraphBoundaryAdapters", "fallback_graph_boundary_adapters"}
            <= imported_names_from(validated_tree, "ea_node_editor.graph.boundary_adapters")
        )

        boundary_field = class_ann_assign(validated_tree, "ValidatedGraphMutation", "boundary_adapters")
        self.assertIsInstance(boundary_field.value, ast.Call)
        self.assertEqual("field", qualified_name(boundary_field.value.func))
        default_factory = next(
            keyword.value
            for keyword in boundary_field.value.keywords
            if keyword.arg == "default_factory"
        )
        self.assertEqual("fallback_graph_boundary_adapters", qualified_name(default_factory))
        self.assertIn("adapters.node_size", call_names(comment_tree))

    def test_scene_bridge_injects_ui_boundary_implementations_without_global_installation(self) -> None:
        tree = parse_module("ea_node_editor/ui_qml/graph_scene_bridge.py")

        self.assertIn("build_graph_boundary_adapters", imported_names_from(tree, "ea_node_editor.graph.boundary_adapters"))
        self.assertIn("node_size", imported_names_from(tree, "ea_node_editor.ui_qml.edge_routing"))
        self.assertNotIn("set_graph_boundary_adapters", call_names(tree))

        init_method = method_node(tree, "GraphSceneBridge", "__init__")
        boundary_call = assignment_call(init_method, "self._boundary_adapters")
        self.assertEqual("build_graph_boundary_adapters", qualified_name(boundary_call.func))
        payload_call = assignment_call(init_method, "self._payload_builder")
        self.assertEqual("GraphScenePayloadBuilder", qualified_name(payload_call.func))
        self.assertTrue(
            any(
                keyword.arg == "boundary_adapters" and qualified_name(keyword.value) == "self._boundary_adapters"
                for keyword in payload_call.keywords
            )
        )
        self.assertTrue(
            has_call_with_keyword(
                init_method,
                "GraphSceneMutationHistory",
                "boundary_adapters",
                "self._boundary_adapters",
            )
        )

    def test_canvas_bridge_owners_and_effective_port_policy_have_single_authority(self) -> None:
        canvas_text = (REPO_ROOT / "ea_node_editor/ui_qml/components/GraphCanvas.qml").read_text(encoding="utf-8")
        mutation_history_text = (
            REPO_ROOT / "ea_node_editor/ui_qml/graph_scene_mutation_history.py"
        ).read_text(encoding="utf-8")
        mutation_policy_tree = parse_module("ea_node_editor/ui_qml/graph_scene_mutation/policy.py")
        policy_bridge_tree = parse_module("ea_node_editor/ui_qml/graph_scene/policy_bridge.py")

        self.assertIn("readonly property var canvasStateBridgeRef: root.canvasStateBridge || null", canvas_text)
        self.assertIn("readonly property var canvasCommandBridgeRef: root.canvasCommandBridge || null", canvas_text)
        self.assertIn("readonly property var canvasViewBridgeRef: root._canvasViewportBridge", canvas_text)
        self.assertIn("readonly property var sceneCommandBridge: root.canvasCommandBridgeRef", canvas_text)
        self.assertIn("readonly property var sceneBridge: root.canvasStateBridgeRef", canvas_text)
        for retired_name in (
            "graphCanvasFacade",
            "canvasFacadeRef",
            "_facadeService",
            "graphCanvasFacadeAdapter",
            "_canvasStateBridgeRef",
            "_canvasViewStateBridgeRef",
        ):
            with self.subTest(retired_name=retired_name):
                self.assertNotIn(retired_name, canvas_text)
        self.assertNotIn("_viewportBridgeFrom", canvas_text)

        self.assertEqual(
            imported_names_from(policy_bridge_tree, "ea_node_editor.graph.effective_ports"),
            {"are_port_kinds_compatible"},
        )
        self.assertIn("registry.data_types.compatibility(", (
            REPO_ROOT / "ea_node_editor/ui_qml/graph_scene/policy_bridge.py"
        ).read_text(encoding="utf-8"))
        self.assertNotIn("are_port_kinds_compatible", declared_python_names(mutation_policy_tree))
        self.assertNotIn("are_data_types_compatible", declared_python_names(mutation_policy_tree))
        self.assertNotIn("GraphSceneMutationPolicy.are_port_kinds_compatible = staticmethod", mutation_history_text)
        self.assertNotIn("GraphSceneMutationPolicy.are_data_types_compatible = staticmethod", mutation_history_text)

    def test_graph_model_exposes_direct_mutation_operation_factories(self) -> None:
        model_tree = parse_module("ea_node_editor/graph/model.py")
        validated_tree = parse_module("ea_node_editor/graph/validated_mutation.py")
        view_tree = parse_module("ea_node_editor/graph/workspace_view_ops.py")
        helper_tree = parse_module("ea_node_editor/ui_qml/graph_scene_mutation_history.py")
        composition_trees = [
            parse_module(path.relative_to(REPO_ROOT).as_posix())
            for path in sorted((REPO_ROOT / "ea_node_editor/ui/shell/composition").glob("*.py"))
        ]

        self.assertNotIn("WorkspaceMutationService", call_names(model_tree))
        self.assertNotIn("ea_node_editor.graph.mutation_service", imported_modules(model_tree))
        self.assertFalse((REPO_ROOT / "ea_node_editor/graph/mutation_service.py").exists())
        self.assertNotIn("mutation_service_factory", function_args(method_node(model_tree, "GraphModel", "__init__")))
        self.assertIn("boundary_adapters", function_args(method_node(model_tree, "GraphModel", "validated_mutations")))
        self.assertIn("ValidatedGraphMutation", declared_python_names(validated_tree))
        self.assertIn("WorkspaceViewMutation", declared_python_names(view_tree))
        self.assertIn("workspace_view_mutations", declared_python_names(view_tree))
        self.assertIn("model.validated_mutations", call_names(helper_tree))
        self.assertNotIn("model.mutation_service", call_names(helper_tree))
        self.assertIn("GraphRecordMutation", declared_python_names(helper_tree))
        self.assertNotIn("WorkspaceMutationService", call_names(helper_tree))
        for composition_tree in composition_trees:
            self.assertNotIn(
                "create_workspace_mutation_service",
                imported_names_from(composition_tree, "ea_node_editor.graph.mutation_service"),
            )
            self.assertNotIn("mutation_service_factory", call_names(composition_tree))

    def test_graph_file_issue_module_is_a_boundary_adapter_to_persistence(self) -> None:
        tree = parse_module("ea_node_editor/graph/file_issue_state.py")
        imported_names = imported_names_from(tree, "ea_node_editor.persistence.file_issues")
        all_names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}

        self.assertTrue(imported_names)
        self.assertNotIn("ProjectArtifactResolver", all_names)
        self.assertNotIn("_TRACKED_REPAIR_MODES", all_names)

    def test_runtime_snapshot_builder_uses_execution_owned_assembly_seam(self) -> None:
        snapshot_tree = parse_module("ea_node_editor/execution/runtime_snapshot.py")
        assembly_tree = parse_module("ea_node_editor/execution/runtime_snapshot_assembly.py")
        worker_runtime_tree = parse_module("ea_node_editor/execution/worker_runtime.py")

        self.assertIn(
            "RuntimeSnapshotAssembly",
            imported_names_from(snapshot_tree, "ea_node_editor.execution.runtime_snapshot_assembly"),
        )
        self.assertNotIn("ea_node_editor.persistence.migration", imported_modules(snapshot_tree))
        self.assertNotIn("ea_node_editor.persistence.project_codec", imported_modules(snapshot_tree))
        snapshot_names = {node.id for node in ast.walk(snapshot_tree) if isinstance(node, ast.Name)}
        assembly_names = {node.id for node in ast.walk(assembly_tree) if isinstance(node, ast.Name)}
        self.assertNotIn("normalize_artifact_store_metadata", snapshot_names)
        self.assertIn("RuntimeSnapshotAssembly", {node.name for node in assembly_tree.body if isinstance(node, ast.ClassDef)})
        self.assertNotIn("JsonProjectMigration", assembly_names)
        self.assertNotIn("normalize_artifact_store_metadata", assembly_names)
        build_runtime_snapshot = next(
            node
            for node in snapshot_tree.body
            if isinstance(node, ast.FunctionDef) and node.name == "build_runtime_snapshot"
        )
        self.assertNotIn("serializer", {arg.arg for arg in build_runtime_snapshot.args.args})
        self.assertNotIn("sanitize_execution_trigger", snapshot_names)
        self.assertNotIn("ea_node_editor.persistence.serializer", imported_modules(worker_runtime_tree))

    def test_runtime_owners_do_not_import_ui_or_qt(self) -> None:
        forbidden_prefixes = (
            "PyQt6",
            "ea_node_editor.app",
            "ea_node_editor.ui",
            "ea_node_editor.ui_qml",
        )
        for relative_path in (
            "ea_node_editor/execution/runtime_requests.py",
            "ea_node_editor/execution/project_loader.py",
            "ea_node_editor/execution/runtime.py",
            "ea_node_editor/execution/runtime_cli.py",
        ):
            imports = imported_modules(parse_module(relative_path))
            offenders = sorted(
                module
                for module in imports
                if any(
                    module == prefix or module.startswith(f"{prefix}.")
                    for prefix in forbidden_prefixes
                )
            )
            self.assertEqual(offenders, [], relative_path)

    def test_project_loader_is_the_only_runtime_persistence_import(self) -> None:
        self.assertFalse(
            (REPO_ROOT / "ea_node_editor/execution/headless_runtime.py").exists()
        )
        owner_paths = {
            "runtime_requests.py": "test_runtime_requests.py",
            "project_loader.py": "test_project_loader.py",
            "runtime.py": "test_runtime.py",
            "runtime_cli.py": "test_runtime_cli.py",
        }
        for source_name, test_name in owner_paths.items():
            with self.subTest(source_name=source_name):
                source_path = REPO_ROOT / "ea_node_editor/execution" / source_name
                self.assertTrue(source_path.is_file())
                self.assertIn(test_name, source_path.read_text(encoding="utf-8"))

        loader_imports = imported_modules(
            parse_module("ea_node_editor/execution/project_loader.py")
        )
        self.assertIn("ea_node_editor.persistence.serializer", loader_imports)
        for source_name in ("runtime_requests.py", "runtime.py", "runtime_cli.py"):
            self.assertFalse(
                {
                    module
                    for module in imported_modules(
                        parse_module(f"ea_node_editor/execution/{source_name}")
                    )
                    if module.startswith("ea_node_editor.persistence")
                },
                source_name,
            )

    def test_shell_execution_client_uses_runtime_boundary(self) -> None:
        tree = parse_module("ea_node_editor/ui/shell/composition/controllers.py")

        self.assertIn(
            "CorexRuntime",
            imported_names_from(tree, "ea_node_editor.execution.runtime"),
        )
        self.assertNotIn(
            "ProcessExecutionClient",
            imported_names_from(tree, "ea_node_editor.execution.process_client"),
        )

    def test_solution_store_stays_execution_owned_and_persistence_neutral(self) -> None:
        imports = imported_modules(
            parse_module("ea_node_editor/execution/solution_store.py")
        )
        self.assertFalse(
            {
                module
                for module in imports
                if module.startswith("ea_node_editor.persistence")
                or module.startswith("ea_node_editor.ui")
                or module.startswith("ea_node_editor.ui_qml")
            }
        )

    def test_solution_repository_implements_only_the_execution_port_boundary(self) -> None:
        imports = imported_modules(
            parse_module("ea_node_editor/persistence/solution_repository.py")
        )
        self.assertEqual(
            {
                module
                for module in imports
                if module.startswith("ea_node_editor.execution.")
            },
            {
                "ea_node_editor.execution.project_solution",
                "ea_node_editor.execution.solution_backend",
            },
        )
        self.assertNotIn("ea_node_editor.persistence.serializer", imports)
        self.assertNotIn("ea_node_editor.persistence.project_codec", imports)

    def test_solution_contracts_have_direct_cycle_free_owners(self) -> None:
        store_tree = parse_module("ea_node_editor/execution/solution_store.py")
        backend_tree = parse_module("ea_node_editor/execution/solution_backend.py")
        project_tree = parse_module("ea_node_editor/execution/project_solution.py")
        store_classes = {
            node.name for node in store_tree.body if isinstance(node, ast.ClassDef)
        }
        self.assertFalse(
            {
                "DurableSolutionBackend",
                "DurableSolutionBackendFactory",
                "DurableBackendOpenResult",
                "ProjectSolutionSaveSnapshot",
                "ProjectSolutionSaveResult",
            }
            & store_classes
        )
        self.assertTrue(
            {
                "DurableSolutionBackend",
                "DurableSolutionBackendFactory",
                "DurableBackendOpenResult",
            }
            <= {
                node.name
                for node in backend_tree.body
                if isinstance(node, ast.ClassDef)
            }
        )
        self.assertTrue(
            {
                "ProjectSolutionSaveSnapshot",
                "ProjectSolutionSaveResult",
                "ProjectSolutionAdoptionResult",
                "ProjectSolutionCandidateResult",
                "ProjectSolutionGcResult",
            }
            <= {
                node.name
                for node in project_tree.body
                if isinstance(node, ast.ClassDef)
            }
        )
        self.assertNotIn(
            "ea_node_editor.execution.project_solution",
            top_level_imported_modules(backend_tree),
        )

    def test_project_artifact_store_replacement_uses_public_controller_boundary(
        self,
    ) -> None:
        controller_tree = parse_module(
            "ea_node_editor/ui/shell/controllers/project_session_controller.py"
        )
        project_files_tree = parse_module(
            "ea_node_editor/ui/shell/controllers/"
            "project_session_services_support/project_files_service.py"
        )
        controller_methods = {
            node.name
            for node in class_node(
                controller_tree,
                "ProjectSessionController",
            ).body
            if isinstance(node, ast.FunctionDef)
        }
        project_files_methods = {
            node.name
            for node in class_node(project_files_tree, "ProjectFilesService").body
            if isinstance(node, ast.FunctionDef)
        }

        self.assertIn("replace_project_artifact_store", controller_methods)
        self.assertIn("replace_project_artifact_store", project_files_methods)
        staging_methods = {
            "stage_node_artifact_file",
            "stage_node_artifact_bytes",
            "create_blank_notebook_artifact",
        }
        self.assertTrue(staging_methods <= controller_methods)
        self.assertTrue(staging_methods <= project_files_methods)
        self.assertNotIn("_set_project_artifact_store", controller_methods)
        self.assertNotIn("_set_project_artifact_store", project_files_methods)

        for relative_path in (
            "ea_node_editor/ui/shell/controllers/workspace_navigation_controller.py",
            "ea_node_editor/ui_qml/content_fullscreen_bridge.py",
            "ea_node_editor/ui_qml/graph_scene_mutation_history.py",
        ):
            with self.subTest(path=relative_path):
                self.assertNotIn(
                    "_set_project_artifact_store",
                    (REPO_ROOT / relative_path).read_text(encoding="utf-8"),
                )

    def test_project_file_staging_callers_use_the_controller_owned_service(self) -> None:
        host_presenter_path = "ea_node_editor/ui/shell/host_presenter.py"
        host_presenter_tree = parse_module(host_presenter_path)
        host_presenter_source = (REPO_ROOT / host_presenter_path).read_text(
            encoding="utf-8"
        )
        host_presenter_methods = {
            node.name
            for node in class_node(host_presenter_tree, "ShellHostPresenter").body
            if isinstance(node, ast.FunctionDef)
        }
        self.assertFalse(
            {
                "create_blank_managed_notebook",
                "make_project_managed_data",
                "stage_clipboard_paste_bytes",
                "_node_artifact_context",
                "_persist_project_artifact_store",
                "_import_source_as_managed_copy",
            }
            & host_presenter_methods
        )
        for forbidden in (
            "PROJECT_ARTIFACT_STORE_METADATA_KEY",
            "register_staged_entry(",
            "ensure_project_staging_root(",
            "node_artifact_paths(",
            "shutil.copy2(",
            ".write_bytes(",
            "create_blank_notebook(",
        ):
            with self.subTest(host_presenter_forbidden=forbidden):
                self.assertNotIn(forbidden, host_presenter_source)

        canvas_import_tree = parse_module(
            "ea_node_editor/ui/shell/controllers/canvas_import_controller.py"
        )
        clipboard_stage = ast.unparse(
            method_node(
                canvas_import_tree,
                "CanvasImportController",
                "_creation_request",
            )
        )
        self.assertIn("project_session_controller", clipboard_stage)
        self.assertIn("stage_node_artifact_bytes", clipboard_stage)
        self.assertNotIn("shell_host_presenter", clipboard_stage)

        media_action_tree = parse_module(
            "ea_node_editor/ui/shell/media_panel_action_service.py"
        )
        for method_name in (
            "_stage_image_crop",
            "_stage_video_frame_capture",
            "_stage_video_clip",
        ):
            method_source = ast.unparse(
                method_node(
                    media_action_tree,
                    "MediaPanelActionService",
                    method_name,
                )
            )
            with self.subTest(media_action_method=method_name):
                self.assertIn("_stage_node_artifact_bytes", method_source)
                self.assertNotIn("project_session_controller", method_source)
                self.assertNotIn("shell_host_presenter", method_source)

        jupyter_path = "ea_node_editor/ui_qml/jupyter_server_bridge.py"
        jupyter_tree = parse_module(jupyter_path)
        jupyter_init = method_node(jupyter_tree, "JupyterServerBridge", "__init__")
        self.assertIn(
            "create_blank_notebook_artifact",
            function_args(jupyter_init),
        )
        create_blank_source = ast.unparse(
            method_node(
                jupyter_tree,
                "JupyterServerBridge",
                "createBlankNotebook",
            )
        )
        self.assertIn("self._create_blank_notebook_artifact", create_blank_source)
        self.assertNotIn("shell_host_presenter", create_blank_source)
        runtime_source = (
            REPO_ROOT / "ea_node_editor/ui/shell/composition/runtime_services.py"
        ).read_text(encoding="utf-8")
        self.assertIn(
            "create_blank_notebook_artifact="
            "project_session.create_blank_notebook_artifact",
            runtime_source,
        )

    def test_content_fullscreen_uses_only_explicit_owner_dependencies(self) -> None:
        relative_path = "ea_node_editor/ui_qml/content_fullscreen_bridge.py"
        source = (REPO_ROOT / relative_path).read_text(encoding="utf-8")
        bridge = class_node(parse_module(relative_path), "ContentFullscreenBridge")
        web_bridge = class_node(
            parse_module(relative_path), "_FullscreenWebSurfaceBridge"
        )
        init = next(
            node
            for node in bridge.body
            if isinstance(node, ast.FunctionDef) and node.name == "__init__"
        )
        self.assertEqual(
            [argument.arg for argument in init.args.kwonlyargs],
            [
                "model_provider",
                "registry_provider",
                "active_workspace_id_provider",
                "project_context_provider",
                "scene_bridge",
                "viewer_session_bridge",
                "run_state",
                "execution_state_changed_signal",
                "script_editor",
                "save_file_dialog",
                "trim_video_clip_replace",
                "trim_video_clip_copy",
                "create_web_surface_artifact_service",
            ],
        )
        for retired in (
            "ShellWindow",
            "shell_window",
            "_shell_window",
            "_ContentFullscreenPolicyService",
            "_policy_service",
            "_set_selected_node_property",
        ):
            self.assertNotIn(retired, source)

        web_init = next(
            node
            for node in web_bridge.body
            if isinstance(node, ast.FunctionDef) and node.name == "__init__"
        )
        self.assertIsNone(web_init.args.kwarg)
        self.assertEqual(
            [argument.arg for argument in web_init.args.kwonlyargs],
            [
                "preview_persist_callback",
                "artifact_service",
                "artifact_scope",
            ],
        )
        self.assertNotIn("def _workspace_name", source)
        self.assertNotIn("def _web_surface_node_type", source)

        runtime_source = (
            REPO_ROOT / "ea_node_editor/ui/shell/composition/runtime_services.py"
        ).read_text(encoding="utf-8")
        self.assertIn(
            "persist_artifact_store=project_session.replace_project_artifact_store",
            runtime_source,
        )
        self.assertNotIn("persist_project_metadata=", runtime_source)
        self.assertNotIn("def save_file_dialog(", runtime_source)
        artifact_factory = runtime_source.split(
            "def create_web_surface_artifact_service(", 1
        )[1].split("content_fullscreen_bridge =", 1)[0]
        self.assertNotIn("project_path=", artifact_factory)
        self.assertNotIn("project_metadata=", artifact_factory)
        for service_path in (
            "ea_node_editor/ui_qml/viewer_host_service.py",
            "ea_node_editor/ui_qml/plot_host_service.py",
        ):
            service_source = (REPO_ROOT / service_path).read_text(encoding="utf-8")
            self.assertNotIn("_connect_content_fullscreen_bridge", service_source)

    def test_solution_repository_has_no_project_commit_and_t08_owns_prune_call(self) -> None:
        repository_source = (
            REPO_ROOT / "ea_node_editor" / "persistence" / "solution_repository.py"
        ).read_text(encoding="utf-8")
        production_source = "\n".join(
            path.read_text(encoding="utf-8")
            for root in (
                REPO_ROOT / "ea_node_editor" / "execution",
                REPO_ROOT / "ea_node_editor" / "persistence",
                REPO_ROOT / "ea_node_editor" / "ui" / "shell",
            )
            for path in root.rglob("*.py")
        )
        self.assertNotIn("os.replace(", repository_source)
        self.assertNotIn("JsonProjectSerializer", repository_source)
        self.assertEqual(production_source.count(".prune_unreachable_paths("), 1)
        self.assertIn(
            "def collect_project_solution_garbage(",
            repository_source,
        )

    def test_production_save_path_uses_only_copy_on_write_staging(self) -> None:
        artifact_store_source = (
            REPO_ROOT / "ea_node_editor" / "persistence" / "artifact_store.py"
        ).read_text(encoding="utf-8")
        document_io_source = (
            REPO_ROOT
            / "ea_node_editor"
            / "ui"
            / "shell"
            / "controllers"
            / "project_session_services_support"
            / "document_io_service.py"
        ).read_text(encoding="utf-8")
        save_source = document_io_source.split("def _run_project_save(", 1)[1]
        self.assertIn(".stage_project_save(", save_source)
        self.assertIn('"stage_project_solution_save"', save_source)
        self.assertIn(".stage_document(", save_source)
        self.assertNotIn(".migrate_workspace_artifact_folders(", save_source)
        self.assertNotIn(".commit_referenced_artifacts(", save_source)
        self.assertNotIn(".save_document(", save_source)
        self.assertNotIn("project_save_as_dialog", document_io_source)
        self.assertIn("def stage_project_save(", artifact_store_source)
        for retired_symbol in (
            "SavePromotionResult",
            "_move_or_replace_path",
            "_promote_staged_payload",
            "_delete_staged_entry_payload",
            "commit_referenced_artifacts",
        ):
            with self.subTest(symbol=retired_symbol):
                self.assertNotIn(retired_symbol, artifact_store_source)

    def test_runtime_contracts_do_not_import_execution_implementation(self) -> None:
        contract_root = REPO_ROOT / "ea_node_editor" / "runtime_contracts"

        for source_path in contract_root.glob("*.py"):
            relative_path = source_path.relative_to(REPO_ROOT).as_posix()
            imports = imported_modules(parse_module(relative_path))
            with self.subTest(path=relative_path):
                self.assertFalse(
                    {
                        module
                        for module in imports
                        if module == "ea_node_editor.execution"
                        or module.startswith("ea_node_editor.execution.")
                    }
                )

    def test_addon_state_and_registry_publication_have_direct_owners(self) -> None:
        import ea_node_editor.addons as addons
        from ea_node_editor.addons.state_changes import AddOnApplyResult
        from ea_node_editor.ui.shell.registry_replacement import (
            RegistryReplacementCoordinator,
        )

        self.assertFalse((REPO_ROOT / "ea_node_editor/addons/hot_apply.py").exists())
        self.assertFalse(hasattr(addons, "apply_addon_enabled_state"))
        self.assertFalse(hasattr(addons, "AddOnApplyResult"))
        self.assertEqual(
            AddOnApplyResult.__module__,
            "ea_node_editor.addons.state_changes",
        )
        self.assertFalse(
            hasattr(RegistryReplacementCoordinator, "rebuild_after_addon_apply")
        )

        state_tree = parse_module("ea_node_editor/addons/state_changes.py")
        self.assertFalse(
            {
                "ea_node_editor.execution",
                "ea_node_editor.nodes.bootstrap",
                "ea_node_editor.persistence",
                "ea_node_editor.ui",
                "ea_node_editor.ui_qml",
            }
            & top_level_imported_modules(state_tree)
        )
        state_source = (REPO_ROOT / "ea_node_editor/addons/state_changes.py").read_text(
            encoding="utf-8"
        )
        for retired_name in (
            "AddOnRuntimeCoordinator",
            "AddOnRuntimeRebuildCoordinator",
            "rebuild_hot_apply_runtime",
            "runtime_coordinator",
            ".persist_document(",
            ".load_document(",
            "build_default_registry",
            "invalidate_addon_runtime_caches",
        ):
            with self.subTest(retired_name=retired_name):
                self.assertNotIn(retired_name, state_source)

    def test_plugin_registry_contributions_have_direct_owners(self) -> None:
        from ea_node_editor.nodes.builtin_catalog import (
            BUILTIN_CONTRACT_CONTRIBUTIONS,
        )

        loader_tree = parse_module("ea_node_editor/nodes/plugin_loader.py")
        loader_imports = imported_modules(loader_tree)
        self.assertFalse(
            {
                module
                for module in loader_imports
                if module == "ea_node_editor.addons"
                or module.startswith("ea_node_editor.addons.")
            }
        )
        loader_source = (REPO_ROOT / "ea_node_editor/nodes/plugin_loader.py").read_text(
            encoding="utf-8"
        )
        for retired_name in (
            "PluginBackendDescriptor",
            "register_plugin_backends",
            "register_internal_builtin_functions",
            "_discover_configured_static_plugins",
        ):
            with self.subTest(retired_name=retired_name):
                self.assertNotIn(retired_name, loader_source)

        bundle_source = (REPO_ROOT / "ea_node_editor/nodes/function_bundle.py").read_text(
            encoding="utf-8"
        )
        for forbidden_name in (
            "PluginBackendDescriptor",
            "plugins_dir",
            "_root_entries",
            "live_addon",
            "INTERNAL_BUILTIN_FUNCTION_OWNER_ID",
            "_register_trusted_python_function",
        ):
            with self.subTest(forbidden_name=forbidden_name):
                self.assertNotIn(forbidden_name, bundle_source)

        builtin_source = (
            REPO_ROOT / "ea_node_editor/nodes/builtin_catalog.py"
        ).read_text(encoding="utf-8")
        self.assertIn("INTERNAL_BUILTIN_FUNCTION_OWNER_ID", builtin_source)
        self.assertIn("_register_trusted_python_function", builtin_source)

        addon_tree = parse_module("ea_node_editor/addons/registry_contributions.py")
        self.assertNotIn(
            "ea_node_editor.nodes.plugin_loader",
            imported_modules(addon_tree),
        )
        worker_tree = parse_module("ea_node_editor/execution/plugin_worker_runtime.py")
        self.assertIn(
            "ea_node_editor.nodes.function_bundle",
            imported_modules(worker_tree),
        )
        self.assertNotIn(
            "ea_node_editor.nodes.plugin_loader",
            imported_modules(worker_tree),
        )

        self.assertEqual(len(BUILTIN_CONTRACT_CONTRIBUTIONS), 17)
        self.assertEqual(
            [
                owner_id
                for _manifest, owner_id, _version, _source, replace in BUILTIN_CONTRACT_CONTRIBUTIONS
                if replace
            ],
            ["corex.core_data_types", "corex.geometry_primitives"],
        )

        catalog_source = (REPO_ROOT / "ea_node_editor/addons/catalog.py").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("create_plot_property_edit_adapters", catalog_source)
        shell_adapter_source = (
            REPO_ROOT / "ea_node_editor/ui/shell/property_edit_adapters.py"
        ).read_text(encoding="utf-8")
        self.assertIn("create_property_edit_adapters", shell_adapter_source)

    def test_node_spec_validation_and_property_coercion_have_direct_owners(self) -> None:
        coercion_tree = parse_module("ea_node_editor/nodes/property_coercion.py")
        coercion_imports = imported_modules(coercion_tree)
        self.assertFalse(
            {
                module
                for module in coercion_imports
                if module == "ea_node_editor.nodes.registry"
                or module.startswith("ea_node_editor.addons")
                or module.startswith("ea_node_editor.graph")
                or module.startswith("ea_node_editor.ui")
                or module.startswith("ea_node_editor.persistence")
                or module.startswith("ea_node_editor.execution")
            }
        )

        validation_source = (
            REPO_ROOT / "ea_node_editor/nodes/spec_validation.py"
        ).read_text(encoding="utf-8")
        validation_imports = imported_modules(
            parse_module("ea_node_editor/nodes/spec_validation.py")
        )
        self.assertNotIn("ea_node_editor.nodes.registry", validation_imports)
        for mutation_name in (
            "register_many(",
            ".fork(",
            ".freeze(",
            "_entries",
            "_contract_manifests",
            "_plugin_bundle_refs",
        ):
            with self.subTest(mutation_name=mutation_name):
                self.assertNotIn(mutation_name, validation_source)

        resolution_tree = parse_module("ea_node_editor/nodes/instance_resolution.py")
        resolution_imports = imported_modules(resolution_tree)
        self.assertNotIn("ea_node_editor.nodes.registry", resolution_imports)
        self.assertNotIn("ea_node_editor.nodes.spec_validation", resolution_imports)
        resolution_source = (
            REPO_ROOT / "ea_node_editor/nodes/instance_resolution.py"
        ).read_text(encoding="utf-8")
        for policy_name in (
            "_SUPPORTED_DIRECTIONS",
            "_SUPPORTED_PORT_SIDES",
            "_SUPPORTED_KINDS",
            "_SUPPORTED_DATA_ACCESS",
        ):
            with self.subTest(policy_name=policy_name):
                self.assertIn(policy_name, resolution_source)
                self.assertNotIn(policy_name, validation_source)

        registry_source = (
            REPO_ROOT / "ea_node_editor/nodes/registry.py"
        ).read_text(encoding="utf-8")
        for retired_name in (
            "def _validate_spec(",
            "def _validate_property(",
            "def _validate_port(",
            "def _coerce_property_value(",
            "def resolve_instance_ports(",
            "def resolve_instance_spec(",
            "_SUPPORTED_SURFACE_FAMILIES",
        ):
            with self.subTest(retired_name=retired_name):
                self.assertNotIn(retired_name, registry_source)
        self.assertIn("spec_validation.validate_node_spec(", registry_source)
        self.assertIn("instance_resolution.resolve_instance_spec(", registry_source)
        self.assertIn("def normalize_property_value(", registry_source)
        self.assertIn("def normalize_properties(", registry_source)

        annotation_source = (
            REPO_ROOT / "ea_node_editor/nodes/builtins/passive_annotation.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn("NodeRegistry._SUPPORTED_SURFACE_FAMILIES", annotation_source)

        for consumer_path in (
            "ea_node_editor/execution/worker_runner.py",
            "ea_node_editor/graph/effective_ports.py",
            "ea_node_editor/graph/validated_mutation.py",
            "ea_node_editor/ui_qml/graph_scene_mutation/selection_and_scope_ops.py",
        ):
            with self.subTest(consumer_path=consumer_path):
                consumer_tree = parse_module(consumer_path)
                self.assertIn(
                    "resolve_instance_ports",
                    imported_names_from(
                        consumer_tree,
                        "ea_node_editor.nodes.instance_resolution",
                    ),
                )
                self.assertNotIn(
                    "resolve_instance_ports",
                    imported_names_from(
                        consumer_tree,
                        "ea_node_editor.nodes.registry",
                    ),
                )

    def test_property_normalization_has_one_policy_owner(self) -> None:
        normalization_tree = parse_module(
            "ea_node_editor/nodes/property_normalization.py"
        )
        normalization_imports = imported_modules(normalization_tree)
        self.assertNotIn("ea_node_editor.nodes.registry", normalization_imports)
        self.assertIn(
            "ea_node_editor.nodes.property_coercion",
            normalization_imports,
        )
        self.assertIn(
            "ea_node_editor.nodes.instance_resolution",
            normalization_imports,
        )
        normalization_source = (
            REPO_ROOT / "ea_node_editor/nodes/property_normalization.py"
        ).read_text(encoding="utf-8")
        for policy_anchor in (
            'type_id == "data.select"',
            'type_id == "data.number_slider"',
            'type_id != "web.page_viewer"',
            "resolve_dynamic_port_groups(",
            "coerce_property_value(",
        ):
            with self.subTest(policy_anchor=policy_anchor):
                self.assertIn(policy_anchor, normalization_source)
        self.assertNotIn("Protocol", normalization_source)
        self.assertNotIn("Callable", normalization_source)

        registry_source = (
            REPO_ROOT / "ea_node_editor/nodes/registry.py"
        ).read_text(encoding="utf-8")
        for policy_anchor in (
            "ea_node_editor.nodes.builtins",
            '"data.select"',
            '"data.number_slider"',
            '"web.page_viewer"',
            "property_coercion",
            "_normalize_special_property",
        ):
            with self.subTest(registry_policy_anchor=policy_anchor):
                self.assertNotIn(policy_anchor, registry_source)
        for api_name in (
            "def default_properties(",
            "def normalize_property_value(",
            "def normalize_properties(",
            "property_normalization.normalize_property_value(",
            "property_normalization.normalize_properties(",
        ):
            with self.subTest(api_name=api_name):
                self.assertIn(api_name, registry_source)

    def test_runtime_value_contracts_have_direct_owners_and_common_stays_leaf(self) -> None:
        from ea_node_editor.runtime_contracts import (
            ImageValue,
            RuntimeArtifactRef,
            serialize_runtime_value,
        )
        from ea_node_editor.runtime_contracts.durable_values import (
            validate_durable_settled_outputs,
        )

        self.assertFalse(
            (REPO_ROOT / "ea_node_editor/runtime_contracts/runtime_values.py").exists()
        )
        self.assertFalse(
            (REPO_ROOT / "ea_node_editor/persistence/artifact_refs.py").exists()
        )
        self.assertFalse(
            (REPO_ROOT / "ea_node_editor/nodes/runtime_refs.py").exists()
        )
        self.assertFalse(
            (REPO_ROOT / "ea_node_editor/execution/runtime_value_codec.py").exists()
        )
        self.assertEqual(
            ImageValue.__module__,
            "ea_node_editor.runtime_contracts.image_value",
        )
        self.assertEqual(
            RuntimeArtifactRef.__module__,
            "ea_node_editor.runtime_contracts.value_refs",
        )
        self.assertEqual(
            serialize_runtime_value.__module__,
            "ea_node_editor.runtime_contracts.value_codec",
        )
        self.assertEqual(
            validate_durable_settled_outputs.__module__,
            "ea_node_editor.runtime_contracts.durable_values",
        )

        forbidden_prefixes = (
            "ea_node_editor.execution",
            "ea_node_editor.graph",
            "ea_node_editor.nodes",
            "ea_node_editor.persistence",
            "ea_node_editor.runtime_contracts",
            "ea_node_editor.ui",
            "ea_node_editor.ui_qml",
        )
        offenders: dict[str, list[str]] = {}
        for source_path in (REPO_ROOT / "ea_node_editor/common").glob("*.py"):
            relative_path = source_path.relative_to(REPO_ROOT).as_posix()
            forbidden = sorted(
                module
                for module in imported_modules(parse_module(relative_path))
                if any(
                    module == prefix or module.startswith(f"{prefix}.")
                    for prefix in forbidden_prefixes
                )
            )
            if forbidden:
                offenders[relative_path] = forbidden
        self.assertEqual(offenders, {})

    def test_runtime_contract_package_exports_are_exact(self) -> None:
        import ea_node_editor.runtime_contracts as runtime_contracts

        self.assertEqual(
            frozenset(runtime_contracts.__all__),
            _EXPECTED_RUNTIME_CONTRACT_EXPORTS,
        )
        self.assertEqual(
            len(runtime_contracts.__all__),
            len(_EXPECTED_RUNTIME_CONTRACT_EXPORTS),
        )

    def test_runtime_value_ref_union_members_have_direct_defining_modules(self) -> None:
        from typing import get_args

        from ea_node_editor.runtime_contracts import (
            ArrayDataRef,
            ArrayValue,
            ArraySlice2DRef,
            ImageValue,
            RuntimeArtifactRef,
            RuntimeHandleRef,
            RuntimeValueRef,
            TabularDataRef,
            TabularWindowRef,
            TableValue,
            TypedInlineValue,
        )
        from ea_node_editor.runtime_contracts import image_value, value_refs

        expected_modules = {
            ArrayValue: "ea_node_editor.runtime_contracts.scientific_values",
            TableValue: "ea_node_editor.runtime_contracts.scientific_values",
            TypedInlineValue: "ea_node_editor.runtime_contracts.value_refs",
            ImageValue: "ea_node_editor.runtime_contracts.image_value",
            RuntimeArtifactRef: "ea_node_editor.runtime_contracts.value_refs",
            RuntimeHandleRef: "ea_node_editor.runtime_contracts.value_refs",
            TabularDataRef: "ea_node_editor.runtime_contracts.tabular_data",
            ArrayDataRef: "ea_node_editor.runtime_contracts.tabular_data",
            TabularWindowRef: "ea_node_editor.runtime_contracts.tabular_data",
            ArraySlice2DRef: "ea_node_editor.runtime_contracts.tabular_data",
        }
        self.assertEqual(set(get_args(RuntimeValueRef)), set(expected_modules))
        for member, module_name in expected_modules.items():
            with self.subTest(member=member.__name__):
                self.assertEqual(member.__module__, module_name)
        self.assertEqual(
            frozenset(value_refs.__all__),
            frozenset(
                {
                    "RuntimeArtifactRef",
                    "RuntimeArtifactScope",
                    "RuntimeHandleRef",
                    "TypedInlineValue",
                    "coerce_runtime_artifact_ref",
                    "coerce_runtime_handle_ref",
                }
            ),
        )
        self.assertFalse(hasattr(value_refs, "_RUNTIME_IMAGE_MARKER_VALUE"))
        self.assertEqual(image_value._RUNTIME_IMAGE_MARKER_VALUE, "image_value")

    def test_settled_results_have_one_runtime_contract_owner(self) -> None:
        settled_tree = parse_module(
            "ea_node_editor/runtime_contracts/settled_results.py"
        )
        protocol_tree = parse_module("ea_node_editor/execution/protocol_codec.py")
        worker_runtime_tree = parse_module(
            "ea_node_editor/execution/worker_runtime.py"
        )
        settled_classes = {
            node.name for node in settled_tree.body if isinstance(node, ast.ClassDef)
        }
        protocol_classes = {
            node.name for node in protocol_tree.body if isinstance(node, ast.ClassDef)
        }
        worker_runtime_classes = {
            node.name
            for node in worker_runtime_tree.body
            if isinstance(node, ast.ClassDef)
        }

        self.assertTrue(
            {"RootExecutionError", "SettledPortResult"} <= settled_classes
        )
        self.assertFalse(
            {"RootExecutionError", "SettledPortResult"} & protocol_classes
        )
        self.assertNotIn("ExecutionPlan", worker_runtime_classes)

        offenders: dict[str, list[str]] = {}
        protocol_owner_modules = (
            "ea_node_editor.execution.protocol_codec",
            "ea_node_editor.execution.run_messages",
            "ea_node_editor.execution.viewer_messages",
        )
        for root_name in ("ea_node_editor", "tests"):
            for source_path in (REPO_ROOT / root_name).rglob("*.py"):
                relative_path = source_path.relative_to(REPO_ROOT).as_posix()
                old_owner_imports = sorted(
                    {
                        name
                        for module_name in protocol_owner_modules
                        for name in imported_names_from(
                            parse_module(relative_path), module_name
                        )
                    }
                    & {"RootExecutionError", "SettledPortResult"}
                )
                if old_owner_imports:
                    offenders[relative_path] = old_owner_imports
        self.assertEqual(offenders, {})

    def test_typed_execution_protocol_has_direct_owners(self) -> None:
        self.assertFalse((REPO_ROOT / "ea_node_editor/execution/protocol.py").exists())
        owner_paths = {
            "transport_fields.py": "test_protocol_codec.py",
            "registry_agreement.py": "test_registry_agreement.py",
            "run_messages.py": "test_run_messages.py",
            "viewer_messages.py": "test_execution_viewer_protocol.py",
            "protocol_codec.py": "test_protocol_codec.py",
        }
        for source_name, test_name in owner_paths.items():
            with self.subTest(source_name=source_name):
                source_path = REPO_ROOT / "ea_node_editor/execution" / source_name
                self.assertTrue(source_path.is_file())
                self.assertIn(test_name, source_path.read_text(encoding="utf-8"))
        prepared_tree = parse_module("ea_node_editor/execution/prepared_execution.py")
        self.assertNotIn(
            "ea_node_editor.execution.run_messages",
            top_level_imported_modules(prepared_tree),
        )

    def test_execution_clients_have_direct_transport_and_router_owners(self) -> None:
        self.assertFalse((REPO_ROOT / "ea_node_editor/execution/client.py").exists())
        owner_paths = {
            "client_common.py": "test_client_common.py",
            "client_generation.py": "test_backend_client.py",
            "process_client.py": "test_process_client.py",
            "external_python_client.py": "test_external_python_client.py",
            "trusted_client.py": "test_trusted_client.py",
            "backend_client.py": "test_backend_client.py",
        }
        for source_name, test_name in owner_paths.items():
            with self.subTest(source_name=source_name):
                source_path = REPO_ROOT / "ea_node_editor/execution" / source_name
                self.assertTrue(source_path.is_file())
                self.assertIn(test_name, source_path.read_text(encoding="utf-8"))

        backend_imports = imported_modules(
            parse_module("ea_node_editor/execution/backend_client.py")
        )
        self.assertTrue(
            {
                "ea_node_editor.execution.process_client",
                "ea_node_editor.execution.external_python_client",
                "ea_node_editor.execution.trusted_client",
            }
            <= backend_imports
        )
        for transport_name in (
            "process_client.py",
            "external_python_client.py",
            "trusted_client.py",
        ):
            self.assertNotIn(
                "ea_node_editor.execution.backend_client",
                imported_modules(
                    parse_module(f"ea_node_editor/execution/{transport_name}")
                ),
            )

        package_exports = declared_python_names(
            parse_module("ea_node_editor/execution/__init__.py")
        )
        self.assertFalse(
            {
                "ExecutionBackendClient",
                "ProcessExecutionClient",
                "ExternalPythonExecutionClient",
                "TrustedInProcessExecutionClient",
            }
            & package_exports
        )

    def test_nodes_sdk_modules_do_not_import_runtime_or_ui_implementations_at_module_load(self) -> None:
        nodes_root = REPO_ROOT / "ea_node_editor" / "nodes"
        forbidden_prefixes = (
            "ea_node_editor.execution",
            "ea_node_editor.persistence",
            "ea_node_editor.ui",
            "ea_node_editor.ui_qml",
        )

        offenders: dict[str, list[str]] = {}
        for source_path in nodes_root.rglob("*.py"):
            relative_path = source_path.relative_to(REPO_ROOT).as_posix()
            imports = top_level_imported_modules(parse_module(relative_path))
            forbidden_imports = sorted(
                module
                for module in imports
                if any(
                    module == prefix or module.startswith(f"{prefix}.")
                    for prefix in forbidden_prefixes
                )
            )
            if forbidden_imports:
                offenders[relative_path] = forbidden_imports

        self.assertEqual(offenders, {})

    def test_public_corex_sdk_is_dependency_free(self) -> None:
        self.assertEqual(
            corex.__all__,
            [
                "node",
                "input",
                "output",
                "text",
                "text_area",
                "number",
                "switch",
                "dropdown",
                "slider",
                "color",
                "path",
                "interval",
                "list",
                "Any",
                "Image",
                "Color",
                "Interval",
            ],
        )
        offenders: dict[str, list[str]] = {}
        for source_path in (REPO_ROOT / "corex").rglob("*.py"):
            relative_path = source_path.relative_to(REPO_ROOT).as_posix()
            imports = imported_modules(parse_module(relative_path))
            forbidden = sorted(
                module
                for module in imports
                if module == "ea_node_editor"
                or module.startswith("ea_node_editor.")
                or module.startswith("PyQt")
            )
            if forbidden:
                offenders[relative_path] = forbidden

        self.assertEqual(offenders, {})

    def test_function_declaration_modules_stay_inside_nodes_sdk_boundary(self) -> None:
        forbidden_prefixes = (
            "ea_node_editor.execution",
            "ea_node_editor.persistence",
            "ea_node_editor.ui",
            "ea_node_editor.ui_qml",
        )
        offenders: dict[str, list[str]] = {}
        for relative_path in (
            "ea_node_editor/nodes/declaration_engine.py",
            "ea_node_editor/nodes/plugin_declaration.py",
        ):
            imports = top_level_imported_modules(parse_module(relative_path))
            forbidden = sorted(
                module
                for module in imports
                if any(
                    module == prefix or module.startswith(f"{prefix}.")
                    for prefix in forbidden_prefixes
                )
            )
            if forbidden:
                offenders[relative_path] = forbidden

        self.assertEqual(offenders, {})

    def test_package_internal_code_does_not_import_nodes_types_barrel(self) -> None:
        package_root = REPO_ROOT / "ea_node_editor"
        forbidden_module = "ea_node_editor.nodes.types"
        offenders: list[str] = []

        for source_path in package_root.rglob("*.py"):
            relative_path = source_path.relative_to(REPO_ROOT).as_posix()
            for node in ast.walk(parse_module(relative_path)):
                if isinstance(node, ast.ImportFrom) and node.level:
                    package = ".".join(source_path.parent.relative_to(REPO_ROOT).parts)
                    imported_module = importlib.util.resolve_name(
                        f"{'.' * node.level}{node.module or ''}",
                        package,
                    )
                else:
                    imported_module = node.module if isinstance(node, ast.ImportFrom) else None
                imports_barrel = (
                    isinstance(node, ast.ImportFrom)
                    and (
                        imported_module == forbidden_module
                        or (
                            imported_module == "ea_node_editor.nodes"
                            and any(alias.name == "types" for alias in node.names)
                        )
                    )
                ) or (
                    isinstance(node, ast.Import)
                    and any(alias.name == forbidden_module for alias in node.names)
                )
                if imports_barrel:
                    offenders.append(f"{relative_path}:{node.lineno}")

        self.assertEqual(offenders, [])

    def test_transform_surface_reexports_focused_operation_modules(self) -> None:
        self.assertEqual(transforms.collect_layout_node_bounds.__module__, "ea_node_editor.graph.transform_layout_ops")
        self.assertEqual(transforms.build_subtree_fragment_payload_data.__module__, "ea_node_editor.graph.transform_fragment_ops")
        self.assertEqual(transforms.plan_subnode_shell_pin_addition.__module__, "ea_node_editor.graph.transform_subnode_ops")
        self.assertEqual(transforms.group_selection_into_subnode.__module__, "ea_node_editor.graph.transform_grouping_ops")
        self.assertEqual(transforms.ungroup_subnode.__module__, "ea_node_editor.graph.transform_grouping_ops")

    def test_record_mutation_ops_keep_packet_owned_raw_write_helpers_internal(self) -> None:
        self.assertFalse(hasattr(GraphRecordMutation, "add_node_raw"))
        self.assertFalse(hasattr(GraphRecordMutation, "add_edge_raw"))
        self.assertFalse(hasattr(GraphRecordMutation, "remove_node_raw"))
        self.assertFalse(hasattr(GraphRecordMutation, "remove_edge_raw"))
        self.assertFalse(hasattr(GraphRecordMutation, "set_node_parent_raw"))
        self.assertFalse(hasattr(GraphRecordMutation, "set_node_fragment_state"))
        self.assertTrue(hasattr(GraphRecordMutation, "_add_node_record"))
        self.assertTrue(hasattr(GraphRecordMutation, "_add_edge_record"))
        self.assertTrue(hasattr(GraphRecordMutation, "_remove_node_record"))
        self.assertTrue(hasattr(GraphRecordMutation, "_remove_edge_record"))
        self.assertTrue(hasattr(GraphRecordMutation, "_set_node_parent_record"))
        self.assertTrue(hasattr(GraphRecordMutation, "_set_node_fragment_state_record"))

    def test_graph_mutation_authority_uses_private_model_record_writers(self) -> None:
        validated_tree = parse_module("ea_node_editor/graph/validated_mutation.py")
        record_tree = parse_module("ea_node_editor/graph/record_mutation_ops.py")
        fragment_tree = parse_module("ea_node_editor/graph/transform_fragment_ops.py")
        grouping_tree = parse_module("ea_node_editor/graph/transform_grouping_ops.py")
        comment_tree = parse_module("ea_node_editor/graph/group_backdrop_mutation_ops.py")
        validated_methods = {
            node.name
            for node in class_node(validated_tree, "ValidatedGraphMutation").body
            if isinstance(node, ast.FunctionDef)
        }

        for method_name in {
            "remove_edge",
            "remove_node",
            "set_edge_label",
            "set_edge_visual_style",
            "set_node_settings_section_expanded",
            "set_node_collapsed",
            "set_node_geometry",
            "set_node_position",
            "set_node_title",
            "set_node_visual_style",
        }:
            self.assertNotIn(method_name, validated_methods)

        public_model_write_calls = {
            "self.model.add_edge",
            "self.model.add_node",
            "self.model.remove_edge",
            "self.model.remove_node",
            "self.model.set_edge_label",
            "self.model.set_edge_visual_style",
            "self.model.set_exposed_port",
            "self.model.set_node_settings_section_expanded",
            "self.model.set_node_collapsed",
            "self.model.set_node_geometry",
            "self.model.set_node_position",
            "self.model.set_node_property",
            "self.model.set_node_title",
            "self.model.set_node_visual_style",
            "self.model.set_port_label",
        }
        self.assertFalse(public_model_write_calls & call_names(validated_tree))
        for tree in (record_tree, fragment_tree, grouping_tree, comment_tree):
            with self.subTest(module=getattr(tree, "type_ignores", None)):
                self.assertFalse(public_model_write_calls & call_names(tree))

        validated_calls = call_names(validated_tree)
        record_calls = call_names(record_tree)
        fragment_calls = call_names(fragment_tree)
        grouping_calls = call_names(grouping_tree)
        comment_calls = call_names(comment_tree)
        self.assertIn("self.model._add_node_record", validated_calls)
        self.assertIn("self.model._add_edge_record", validated_calls)
        self.assertIn("self.model._set_node_property_record", validated_calls)
        self.assertIn("self.model._add_node_record", record_calls)
        self.assertIn("self.model._set_node_fragment_state_record", record_calls)
        self.assertIn("mutations._add_node_record", fragment_calls)
        self.assertIn("records._add_edge_record", grouping_calls)
        self.assertIn("model._set_node_geometry_record", comment_calls)

    def test_graph_view_mutations_and_dirty_marking_use_workspace_domain_boundary(self) -> None:
        model_tree = parse_module("ea_node_editor/graph/model.py")
        workspace_state_tree = parse_module("ea_node_editor/graph/workspace_state.py")
        view_tree = parse_module("ea_node_editor/graph/workspace_view_ops.py")
        validated_tree = parse_module("ea_node_editor/graph/validated_mutation.py")

        workspace_methods = {
            node.name
            for node in class_node(workspace_state_tree, "WorkspaceData").body
            if isinstance(node, ast.FunctionDef)
        }
        self.assertTrue({"active_view_state", "mark_dirty"} <= workspace_methods)
        self.assertNotIn("workspace.dirty = True", (REPO_ROOT / "ea_node_editor/graph/model.py").read_text(encoding="utf-8"))
        self.assertNotIn(
            "workspace.dirty = True",
            (REPO_ROOT / "ea_node_editor/graph/workspace_state.py").read_text(encoding="utf-8"),
        )
        self.assertNotIn(
            "self.workspace.dirty = True",
            (REPO_ROOT / "ea_node_editor/graph/workspace_view_ops.py").read_text(encoding="utf-8"),
        )
        self.assertNotIn("self.workspace.dirty = True", (REPO_ROOT / "ea_node_editor/graph/validated_mutation.py").read_text(encoding="utf-8"))

        view_to_record_writer = {
            "create_view": "self.model._create_view_record",
            "set_active_view": "self.model._set_active_view_record",
            "close_view": "self.model._close_view_record",
            "rename_view": "self.model._rename_view_record",
            "move_view": "self.model._move_view_record",
        }
        for public_method, private_writer in view_to_record_writer.items():
            with self.subTest(method=public_method):
                model_method_calls = call_names(method_node(model_tree, "GraphModel", public_method))
                view_method_calls = call_names(method_node(view_tree, "WorkspaceViewMutation", public_method))

                self.assertIn("self.workspace_view_mutations", model_method_calls)
                self.assertIn(private_writer, view_method_calls)
                self.assertNotIn(f"self.model.{public_method}", view_method_calls)

        self.assertIn(
            "self.workspace.active_view_state",
            call_names(method_node(validated_tree, "ValidatedGraphMutation", "_active_view_state")),
        )
        self.assertIn(
            "self.workspace.active_view_state",
            call_names(method_node(view_tree, "WorkspaceViewMutation", "active_view_state")),
        )

    def test_workspace_manager_owns_order_not_view_lifecycle_mutation(self) -> None:
        manager_tree = parse_module("ea_node_editor/workspace/manager.py")

        self.assertIn(
            "resolve_workspace_ownership",
            imported_names_from(manager_tree, "ea_node_editor.workspace.ownership"),
        )
        self.assertNotIn(
            "sync_project_workspace_ownership",
            imported_names_from(manager_tree, "ea_node_editor.workspace.ownership"),
        )
        manager_methods = {
            node.name
            for node in class_node(manager_tree, "WorkspaceManager").body
            if isinstance(node, ast.FunctionDef)
        }
        self.assertFalse(
            {
                "create_view",
                "set_active_view",
                "close_view",
                "rename_view",
                "move_view",
            }
            & manager_methods
        )

    def test_workspace_navigation_view_lifecycle_uses_view_mutation_boundary(self) -> None:
        navigation_tree = parse_module("ea_node_editor/ui/shell/controllers/workspace_navigation_controller.py")

        for method_name in {"close_view", "rename_view", "move_view"}:
            with self.subTest(method=method_name):
                method_calls = call_names(method_node(navigation_tree, "WorkspaceNavigationController", method_name))
                self.assertIn("self._host.model.workspace_view_mutations", method_calls)

        navigation_calls = call_names(navigation_tree)
        self.assertNotIn("self._host.workspace_manager.close_view", navigation_calls)
        self.assertNotIn("self._host.workspace_manager.rename_view", navigation_calls)
        self.assertNotIn("self._host.workspace_manager.move_view", navigation_calls)

    def test_workspace_graph_actions_have_direct_concrete_owners(self) -> None:
        controller_dir = REPO_ROOT / "ea_node_editor/ui/shell/controllers"
        self.assertFalse((controller_dir / "workspace_library_controller.py").exists())
        self.assertFalse(
            (controller_dir / "workspace_graph_edit_controller.py").exists()
        )
        self.assertFalse((controller_dir / "workspace_edit_ops.py").exists())
        self.assertFalse((controller_dir / "workspace_drop_connect_ops.py").exists())

        selection_tree = parse_module(
            "ea_node_editor/ui/shell/controllers/workspace_selection_context.py"
        )
        edit_tree = parse_module(
            "ea_node_editor/ui/shell/controllers/workspace_edit_controller.py"
        )
        drop_tree = parse_module(
            "ea_node_editor/ui/shell/controllers/workspace_drop_connect_controller.py"
        )
        self.assertEqual(
            class_node(selection_tree, "WorkspaceSelectionContext").name,
            "WorkspaceSelectionContext",
        )
        self.assertEqual(
            class_node(edit_tree, "WorkspaceEditController").name,
            "WorkspaceEditController",
        )
        self.assertEqual(
            class_node(drop_tree, "WorkspaceDropConnectController").name,
            "WorkspaceDropConnectController",
        )
        for tree in (edit_tree, drop_tree):
            self.assertFalse(
                any(
                    isinstance(node, ast.ClassDef) and node.name.endswith("Protocol")
                    for node in tree.body
                )
            )

        composition_source = (
            REPO_ROOT / "ea_node_editor/ui/shell/composition/library_workspace.py"
        ).read_text(encoding="utf-8")
        self.assertEqual(composition_source.count("MutationUiEffects("), 1)
        self.assertIn("workspace_edit_controller=edit_controller", composition_source)
        self.assertIn(
            "workspace_drop_connect_controller=drop_connect_controller",
            composition_source,
        )
        self.assertNotIn("workspace_library_controller", composition_source)
        self.assertNotIn("workspace_graph_edit_controller", composition_source)

        action_source = (
            REPO_ROOT / "ea_node_editor/ui/shell/controllers/graph_action_controller.py"
        ).read_text(encoding="utf-8")
        for retired_dispatch in (
            "_invoke_bool",
            "_WORKSPACE_ACTION_METHODS",
            "_NODE_HOST_ACTION_METHODS",
            "_EDGE_HOST_ACTION_METHODS",
            "workspace_library_controller",
            "workspace_graph_edit_controller",
            "shell_library_presenter",
        ):
            self.assertNotIn(retired_dispatch, action_source)

        production_source = "\n".join(
            path.read_text(encoding="utf-8")
            for path in (REPO_ROOT / "ea_node_editor").rglob("*.py")
        )
        self.assertNotIn("workspace_library_controller", production_source)
        self.assertNotIn("workspace_graph_edit_controller", production_source)

    def test_viewer_and_plot_owners_use_explicit_dependencies_without_shell_location(
        self,
    ) -> None:
        owner_paths = (
            "ea_node_editor/ui_qml/viewer_session_bridge.py",
            "ea_node_editor/ui_qml/viewer_control_bridge.py",
            "ea_node_editor/ui_qml/viewer_host_service.py",
            "ea_node_editor/ui_qml/plot_host_service.py",
        )
        for relative_path in owner_paths:
            source = (REPO_ROOT / relative_path).read_text(encoding="utf-8")
            with self.subTest(path=relative_path):
                self.assertNotIn("_shell_window", source)
                self.assertNotIn('shell_window: "ShellWindow', source)

        composition = (
            REPO_ROOT / "ea_node_editor/ui/shell/composition/runtime_services.py"
        ).read_text(encoding="utf-8")
        for direct_dependency in (
            "execution_client_provider=execution_client_provider",
            "active_workspace_id_provider=active_workspace_id_provider",
            "workspace_provider=workspace_provider",
            "model_provider=model_provider",
            "registry_provider=registry_provider",
            "app_preferences_controller=preferences.app_preferences_controller",
            "save_file_dialog=presenters.shell_host_presenter.save_file_dialog",
            "viewer_host_service=viewer_host_service",
            "qml_engine_provider=qml_engine_provider",
            "cycle_camera_bookmark=cycle_viewer_camera_bookmark",
        ):
            self.assertIn(direct_dependency, composition)
        self.assertEqual(composition.count("_ref: list["), 2)
        self.assertEqual(composition.count("def capture_overlay_camera_state("), 1)
        self.assertEqual(composition.count("def cycle_viewer_camera_bookmark("), 1)
        for retired_route in (
            "ViewerSessionBridge(\n        host,\n        shell_window=host",
            "ViewerControlBridge(\n        host,\n        shell_window=host",
            "ViewerHostService(\n        host,\n        shell_window=host",
            "PlotHostService(\n        host,\n        shell_window=host",
        ):
            self.assertNotIn(retired_route, composition)

    def test_native_presentation_handoff_owns_only_shared_demotion_state(self) -> None:
        handoff_tree = parse_module(
            "ea_node_editor/ui_qml/native_presentation_handoff.py"
        )
        handoff_class = class_node(handoff_tree, "NativePresentationHandoff")
        self.assertEqual(handoff_class.bases, [])
        handoff_methods = {
            node.name
            for node in handoff_class.body
            if isinstance(node, ast.FunctionDef)
        }
        self.assertTrue(
            {
                "begin",
                "notify_preview_swapped",
                "cancel",
                "flush",
                "shutdown",
                "_expire",
                "_on_render_gate_frame",
            }
            <= handoff_methods
        )

        retired_host_state = (
            "_PendingEmbeddedExitDemotion",
            "_pending_embedded_exit_demotions",
            "_embedded_exit_demotion_serial",
            "_exit_render_gate_window",
            "_connect_exit_render_gate",
            "_disconnect_exit_render_gate",
            "_complete_armed_embedded_exit_demotions",
        )
        for relative_path in (
            "ea_node_editor/ui_qml/viewer_host_service.py",
            "ea_node_editor/ui_qml/plot_host_service.py",
        ):
            source = (REPO_ROOT / relative_path).read_text(encoding="utf-8")
            with self.subTest(path=relative_path):
                self.assertEqual(source.count("NativePresentationHandoff("), 1)
                for retired_name in retired_host_state:
                    self.assertNotIn(retired_name, source)
                self.assertIn("def _complete_embedded_exit_demotion(", source)

        handoff_source = (
            REPO_ROOT / "ea_node_editor/ui_qml/native_presentation_handoff.py"
        ).read_text(encoding="utf-8")
        for rejected_abstraction in (
            "ABC",
            "Protocol",
            "Registry",
            "Pool",
            "singleton",
        ):
            self.assertNotIn(rejected_abstraction, handoff_source)

    def test_media_panel_actions_have_one_direct_qobject_service(self) -> None:
        presenter_dir = REPO_ROOT / "ea_node_editor/ui/shell/presenters"
        self.assertFalse((presenter_dir / "graph_canvas_presenter.py").exists())
        export_tree = parse_module(
            "ea_node_editor/ui/shell/presenters/canvas_export_presenter.py"
        )
        export_class = class_node(export_tree, "CanvasExportPresenter")
        self.assertEqual(export_class.bases, [])
        self.assertIn(
            "capture_canvas_view_pngs",
            {
                node.name
                for node in export_class.body
                if isinstance(node, ast.FunctionDef)
            },
        )

        service_path = "ea_node_editor/ui/shell/media_panel_action_service.py"
        service_tree = parse_module(service_path)
        service_class = class_node(service_tree, "MediaPanelActionService")
        self.assertEqual(
            [base.id for base in service_class.bases if isinstance(base, ast.Name)],
            ["QObject"],
        )
        self.assertFalse(
            any(
                isinstance(node, ast.ClassDef) and node.name.endswith("Protocol")
                for node in service_tree.body
            )
        )
        service_source = (REPO_ROOT / service_path).read_text(encoding="utf-8")
        self.assertEqual(service_source.count("QThread(self)"), 1)
        self.assertEqual(service_source.count("VideoTrimWorker("), 1)

        runtime_source = (
            REPO_ROOT / "ea_node_editor/ui/shell/composition/runtime_services.py"
        ).read_text(encoding="utf-8")
        self.assertEqual(runtime_source.count("MediaPanelActionService("), 1)
        for direct_dependency in (
            "scene_mutation=primitives.scene",
            "workspace_edit_controller=library_workspace.workspace_edit_controller",
            "workspace_drop_connect_controller=(",
            "library_workspace.workspace_drop_connect_controller",
            "stage_node_artifact_bytes=project_session.stage_node_artifact_bytes",
            "trim_video_clip_replace=(\n            media_panel_action_service.request_trim_video_clip_replace",
            "trim_video_clip_copy=media_panel_action_service.request_trim_video_clip_copy",
        ):
            self.assertIn(direct_dependency, runtime_source)

        bridge_source = (
            REPO_ROOT / "ea_node_editor/ui/shell/composition/bridges.py"
        ).read_text(encoding="utf-8")
        self.assertIn(
            "media_action_source=runtime.media_panel_action_service",
            bridge_source,
        )
        for direct_owner in (
            "session_state=state.search_scope_state",
            "app_preferences_source=preferences.app_preferences_controller",
            "run_controller=controllers.run_controller",
            "inspector_source=presenters.shell_inspector_presenter",
            "library_source=presenters.shell_library_presenter",
            "workspace_edit_controller=library_workspace.workspace_edit_controller",
            "library_workspace.workspace_drop_connect_controller",
            "host_source=presenters.graph_canvas_host_presenter",
        ):
            self.assertIn(direct_owner, bridge_source)
        bridge_package_source = "\n".join(
            path.read_text(encoding="utf-8")
            for root in (
                REPO_ROOT / "ea_node_editor/ui_qml/graph_canvas_state",
                REPO_ROOT / "ea_node_editor/ui_qml/graph_canvas_command",
            )
            for path in root.glob("*.py")
        )
        self.assertNotIn("canvas_source", bridge_package_source)
        self.assertNotIn("shell_window", bridge_package_source)
        fallback_sources = "\n".join(
            (REPO_ROOT / path).read_text(encoding="utf-8")
            for path in (
                "ea_node_editor/ui_qml/graph_canvas_command/media_image_ops.py",
                "ea_node_editor/ui_qml/graph_canvas_command/media_video_ops.py",
                "ea_node_editor/ui_qml/content_fullscreen_bridge.py",
            )
        )
        self.assertNotIn("Graph canvas presenter cannot", fallback_sources)
        self.assertEqual(
            fallback_sources.count("Media Panel actions are unavailable."),
            7,
        )

    def test_fragment_payload_helpers_share_model_mapping_parsers(self) -> None:
        fragment_payload_tree = parse_module("ea_node_editor/graph/fragment_payloads.py")
        fragment_tree = parse_module("ea_node_editor/graph/transform_fragment_ops.py")

        self.assertTrue(
            {
                "edge_instance_from_mapping",
                "edge_instance_to_mapping",
                "node_instance_from_mapping",
                "node_instance_to_mapping",
            }
            <= imported_names_from(fragment_payload_tree, "ea_node_editor.graph.record_payloads")
        )
        self.assertTrue(
            {
                "edge_instance_from_mapping",
                "edge_instance_to_mapping",
                "node_instance_to_mapping",
            }
            <= imported_names_from(fragment_tree, "ea_node_editor.graph.record_payloads")
        )
        self.assertTrue(
            {"fragment_node_from_payload", "normalize_graph_fragment_payload"}
            <= imported_names_from(fragment_tree, "ea_node_editor.graph.fragment_payloads")
        )
        self.assertIn(
            "graph_fragment_payload_is_valid",
            imported_names_from(fragment_tree, "ea_node_editor.graph.fragment_payloads"),
        )
        self.assertNotIn("GraphInvariantKernel.fragment_node_from_payload", call_names(fragment_tree))
        self.assertNotIn("GraphInvariantKernel.graph_fragment_payload_is_valid", call_names(fragment_tree))

    def test_graph_normalization_split_has_focused_owner_modules(self) -> None:
        self.assertFalse((REPO_ROOT / "ea_node_editor/graph/normalization.py").exists())

        fragment_payload_tree = parse_module("ea_node_editor/graph/fragment_payloads.py")
        invariant_tree = parse_module("ea_node_editor/graph/invariant_kernel.py")
        registry_tree = parse_module("ea_node_editor/graph/registry_normalization.py")
        validated_tree = parse_module("ea_node_editor/graph/validated_mutation.py")

        self.assertTrue(
            {
                "GRAPH_FRAGMENT_KIND",
                "GRAPH_FRAGMENT_VERSION",
                "build_graph_fragment_payload",
                "fragment_node_from_payload",
                "graph_fragment_payload_is_valid",
                "normalize_edge_label",
                "normalize_graph_fragment_payload",
                "normalize_visual_style_payload",
            }
            <= declared_python_names(fragment_payload_tree)
        )
        self.assertTrue(
            {
                "GraphInvariantKernel",
                "RegistryEdgeResolution",
                "RegistryNodeResolution",
                "accept_registry_edge",
                "resolve_registry_nodes",
                "validate_registry_edge",
            }
            <= declared_python_names(invariant_tree)
        )
        self.assertEqual(
            {"normalize_project_for_registry"} & declared_python_names(registry_tree),
            {"normalize_project_for_registry"},
        )
        self.assertEqual(
            {"ValidatedGraphMutation"} & declared_python_names(validated_tree),
            {"ValidatedGraphMutation"},
        )

    def test_graph_model_split_has_focused_owner_modules(self) -> None:
        model_tree = parse_module("ea_node_editor/graph/model.py")
        records_tree = parse_module("ea_node_editor/graph/records.py")
        payload_tree = parse_module("ea_node_editor/graph/record_payloads.py")
        workspace_state_tree = parse_module("ea_node_editor/graph/workspace_state.py")
        project_state_tree = parse_module("ea_node_editor/graph/project_state.py")
        hierarchy_tree = parse_module("ea_node_editor/graph/hierarchy.py")

        self.assertEqual({"GraphModel"} & declared_python_names(model_tree), {"GraphModel"})
        self.assertTrue({"NodeInstance", "EdgeInstance"} <= declared_python_names(records_tree))
        self.assertTrue(
            {
                "edge_instance_from_mapping",
                "edge_instance_to_mapping",
                "node_instance_from_mapping",
                "node_instance_to_mapping",
            }
            <= declared_python_names(payload_tree)
        )
        self.assertTrue(
            {"ViewState", "WorkspaceData", "WorkspaceSnapshot"}
            <= declared_python_names(workspace_state_tree)
        )
        self.assertIn("ProjectData", declared_python_names(project_state_tree))
        self.assertIn("sanitize_workspace_parent_links", declared_python_names(hierarchy_tree))
        self.assertFalse(
            {
                "ProjectData",
                "WorkspaceData",
                "WorkspaceSnapshot",
                "ViewState",
                "NodeInstance",
                "EdgeInstance",
                "node_instance_from_mapping",
                "edge_instance_from_mapping",
                "sanitize_workspace_parent_links",
            }
            & declared_python_names(model_tree)
        )

    def test_shell_projection_helpers_have_direct_owners(self) -> None:
        self.assertFalse(
            (REPO_ROOT / "ea_node_editor/ui/shell/window_library_inspector.py").exists()
        )

        library_tree = parse_module("ea_node_editor/ui/shell/library_projection.py")
        library_names = declared_python_names(library_tree)
        inspector_names = declared_python_names(
            parse_module("ea_node_editor/ui/shell/inspector_projection.py")
        )
        quick_insert_tree = parse_module(
            "ea_node_editor/ui/shell/quick_insert_projection.py"
        )
        quick_insert_names = declared_python_names(quick_insert_tree)
        self.assertTrue(
            {
                "build_combined_library_items",
                "build_filtered_library_items",
                "build_library_category_options",
                "build_library_category_tree",
                "build_registry_library_items",
                "project_display_library_items",
                "project_grouped_library_items",
                "projected_port_declared_data_types",
                "rank_node_library_usage",
            }
            <= library_names
        )
        self.assertTrue(
            {
                "build_pin_data_type_options",
                "build_selected_node_header_data",
                "build_selected_node_link_items",
                "build_selected_node_port_items",
                "build_selected_node_property_items",
            }
            <= inspector_names
        )
        self.assertTrue(
            {
                "build_canvas_quick_insert_items",
                "build_connection_quick_insert_items",
            }
            <= quick_insert_names
        )
        self.assertFalse(
            any(
                isinstance(node, ast.FunctionDef)
                and node.name == "projected_port_declared_data_types"
                for node in quick_insert_tree.body
            )
        )
        self.assertEqual(
            imported_names_from(
                library_tree,
                "ea_node_editor.ui.shell.quick_insert_projection",
            ),
            set(),
        )
        self.assertIn(
            "projected_port_declared_data_types",
            imported_names_from(
                quick_insert_tree,
                "ea_node_editor.ui.shell.library_projection",
            ),
        )

        self.assertTrue(
            {
                "build_library_category_options",
                "build_library_category_tree",
                "project_display_library_items",
                "project_grouped_library_items",
            }
            <= imported_names_from(
                parse_module("ea_node_editor/ui/shell/presenters/library_presenter.py"),
                "ea_node_editor.ui.shell.library_projection",
            ),
        )
        library_source = (
            REPO_ROOT / "ea_node_editor/ui/shell/library_projection.py"
        ).read_text(encoding="utf-8")
        presenter_source = (
            REPO_ROOT / "ea_node_editor/ui/shell/presenters/library_presenter.py"
        ).read_text(encoding="utf-8")
        registry_source = (
            REPO_ROOT / "ea_node_editor/nodes/registry.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn("registry_categories", library_source)
        self.assertNotIn("_registry_categories_cache", presenter_source)
        self.assertNotIn(".category_paths(", presenter_source)
        for retired_name in (
            "def filter_nodes(",
            "def category_paths(",
            "def categories(",
        ):
            with self.subTest(retired_name=retired_name):
                self.assertNotIn(retired_name, registry_source)
        self.assertFalse((REPO_ROOT / "tests/test_registry_filters.py").exists())
        self.assertIn(
            "build_selected_node_property_items",
            imported_names_from(
                parse_module("ea_node_editor/ui/shell/presenters/inspector_presenter.py"),
                "ea_node_editor.ui.shell.inspector_projection",
            ),
        )
        self.assertIn(
            "build_connection_quick_insert_items",
            imported_names_from(
                parse_module("ea_node_editor/ui/shell/presenters/state.py"),
                "ea_node_editor.ui.shell.quick_insert_projection",
            ),
        )

    def test_graph_canvas_surface_editor_overlay_owner_replaces_root_items_without_growth(self) -> None:
        graph_canvas_dir = REPO_ROOT / "ea_node_editor/ui_qml/components/graph_canvas"
        root_text = (graph_canvas_dir / "GraphCanvasRootLayers.qml").read_text(
            encoding="utf-8"
        )
        owner_text = (graph_canvas_dir / "GraphCanvasSurfaceEditorOverlays.qml").read_text(
            encoding="utf-8"
        )

        def declaration_count(text: str, type_name: str) -> int:
            return sum(line.strip() == f"{type_name} {{" for line in text.splitlines())

        self.assertEqual(
            {
                type_name: declaration_count(root_text, type_name)
                + declaration_count(owner_text, type_name)
                for type_name in ("Item", "QtObject", "Timer", "Loader")
            },
            {"Item": 10, "QtObject": 0, "Timer": 2, "Loader": 0},
        )
        self.assertEqual(
            [
                name
                for name in (
                    "webPageAddressOverlayLayer",
                    "graphNodeTimestampOverlayLayer",
                    "graphNumberSliderOverlayLayer",
                    "graphSelectOverlayLayer",
                    "graphPanelOverlayLayer",
                )
                if f'objectName: "{name}"' in owner_text
            ],
            [
                "webPageAddressOverlayLayer",
                "graphNodeTimestampOverlayLayer",
                "graphNumberSliderOverlayLayer",
                "graphSelectOverlayLayer",
                "graphPanelOverlayLayer",
            ],
        )
        self.assertEqual(
            root_text.count("function openSurfaceActionOverlayForHost(host, actionId, surface)"),
            1,
        )
        self.assertNotIn('String(actionId || "") ===', root_text)
        self.assertNotIn("property Item webPageAddressEditorHost: null", root_text)
        self.assertNotIn("property bool panelOverlayOpen: false", root_text)
        self.assertIn(
            "property alias webPageAddressEditorHost: surfaceEditorOverlays.webPageAddressEditorHost",
            root_text,
        )
        self.assertIn(
            "return surfaceEditorOverlays.openSurfaceActionOverlayForHost(host, actionId, surface);",
            root_text,
        )

    def test_graph_node_port_row_is_the_direct_shared_delegate_without_object_growth(self) -> None:
        graph_dir = REPO_ROOT / "ea_node_editor/ui_qml/components/graph"
        layer_text = (graph_dir / "GraphNodePortsLayer.qml").read_text(encoding="utf-8")
        row_text = (graph_dir / "GraphNodePortRow.qml").read_text(encoding="utf-8")

        def declaration_count(text: str, type_name: str) -> int:
            return sum(line.strip() == f"{type_name} {{" for line in text.splitlines())

        self.assertEqual(layer_text.count("delegate: GraphNodePortRow {"), 2)
        self.assertEqual(
            {
                type_name: declaration_count(layer_text, type_name)
                + declaration_count(row_text, type_name)
                for type_name in (
                    "Item",
                    "Connections",
                    "Binding",
                    "Loader",
                    "Timer",
                    "Canvas",
                    "Repeater",
                )
            },
            {
                "Item": 3,
                "Connections": 2,
                "Binding": 0,
                "Loader": 1,
                "Timer": 0,
                "Canvas": 2,
                "Repeater": 4,
            },
        )
        for forbidden_type in ("Connections {", "Binding {", "Loader {", "Timer {"):
            self.assertNotIn(forbidden_type, row_text)
        for direction_property in (
            "property bool defaultPropertyCapable",
            "property string portPointSide",
            "property bool notchMirrored",
            "property bool outputHoverBehavior",
        ):
            self.assertNotIn(direction_property, row_text)
        self.assertIn('property string direction: "in"', row_text)
        self.assertIn('readonly property bool isInput: direction === "in"', row_text)
        self.assertIn("function paintPadlock(canvas, padlockLocked, placeholderLocked)", row_text)
        self.assertIn("host.localPortPointForPort(direction, rowIndex, portData)", row_text)
        self.assertIn("mirror: !row.isInput", row_text)
        self.assertIn("row.host._isResizeHandlePoint", row_text)

        direction_only_names = (
            "graphNodeInputPortInactiveSlash",
            "graphNodeInputPortPadlock",
            "graphNodeInputDefaultProperty",
            "graphNodeOutputPortPadlock",
        )
        for name in direction_only_names:
            self.assertIn(f'objectName: "{name}"', layer_text)
            self.assertNotIn(name, row_text)
        self.assertEqual(layer_text.count("id: outputLockGlyphLoader"), 1)
        self.assertEqual(layer_text.count("id: portContextMenu"), 1)
        self.assertIn("GraphNodePortContextMenu {", layer_text)

        shared_name_families = (
            "PortRow",
            "PortNotch",
            "PortDot",
            "PortRing",
            "PortMouseArea",
            "PortLabel",
            "PortHelpToolTip",
            "PortLabelEditor",
        )
        for suffix in shared_name_families:
            with self.subTest(suffix=suffix):
                self.assertIn(f'"graphNodeInput{suffix}"', row_text)
                self.assertIn(f'"graphNodeOutput{suffix}"', row_text)

    def test_graph_node_port_context_menu_is_the_direct_menu_owner_without_growth(self) -> None:
        graph_dir = REPO_ROOT / "ea_node_editor/ui_qml/components/graph"
        layer_text = (graph_dir / "GraphNodePortsLayer.qml").read_text(encoding="utf-8")
        row_text = (graph_dir / "GraphNodePortRow.qml").read_text(encoding="utf-8")
        menu_text = (graph_dir / "GraphNodePortContextMenu.qml").read_text(
            encoding="utf-8"
        )

        def declaration_count(text: str, type_name: str) -> int:
            return sum(line.strip() == f"{type_name} {{" for line in text.splitlines())

        self.assertEqual(layer_text.count("GraphNodePortContextMenu {"), 1)
        self.assertEqual(declaration_count(layer_text, "Menu"), 0)
        self.assertEqual(declaration_count(menu_text, "Shell.ShellContextPopup"), 1)
        self.assertEqual(
            {
                type_name: sum(
                    declaration_count(text, type_name)
                    for text in (layer_text, row_text, menu_text)
                )
                for type_name in (
                    "Item",
                    "Connections",
                    "Binding",
                    "Loader",
                    "Timer",
                    "Canvas",
                    "Repeater",
                    "Shell.ShellContextPopup",
                )
            },
            {
                "Item": 3,
                "Connections": 2,
                "Binding": 0,
                "Loader": 1,
                "Timer": 0,
                "Canvas": 2,
                "Repeater": 4,
                "Shell.ShellContextPopup": 1,
            },
        )
        self.assertIn("required property Item portsLayer", menu_text)
        self.assertNotIn("signal ", menu_text)
        for forbidden in (
            "callback",
            "actionRegistry",
            "actionModel",
            "dispatchAction",
            "Connections {",
            "Binding {",
            "Loader {",
            "Timer {",
        ):
            self.assertNotIn(forbidden, menu_text)

        object_names = (
            "graphNodePortContextMenu",
            "graphNodePortAccessMetadata",
            "graphNodePortPrincipal",
            "graphNodeDynamicPortInsertBefore",
            "graphNodeDynamicPortInsertAfter",
            "graphNodeDynamicPortRename",
            "graphNodeDynamicPortRemove",
        )
        for object_name in object_names:
            with self.subTest(object_name=object_name):
                self.assertIn(f'objectName: "{object_name}"', menu_text)
                self.assertNotIn(f'objectName: "{object_name}"', layer_text)
        self.assertIn(
            'var modifiers = ["Graft", "Flatten", "Simplify", "Reverse", "Clean"]',
            menu_text,
        )
        self.assertIn('objectName: "graphNodePortModifier" + modifiers[i]', menu_text)
        self.assertIn("var layer = menu.portsLayer", menu_text)
        for owner_call in (
            "layer._togglePortModifier(actionId)",
            "layer._togglePrincipal()",
            'layer._insertDynamicPort(group.id, ordinal + (actionId === "insert_after" ? 1 : 0))',
            'layer.beginPortLabelEdit(key, String(group.direction || ""))',
            "layer._removeDynamicPort(group.id, key)",
        ):
            self.assertIn(owner_call, menu_text)
        self.assertIn("root.contextPortData = portData;", layer_text)
        self.assertIn("portContextMenu.openAt(sourceItem, localX, localY);", layer_text)

    def test_graph_action_presentation_is_pure_and_dispatch_stays_in_the_router(self) -> None:
        qml_root = REPO_ROOT / "ea_node_editor/ui_qml/components"
        owner_path = qml_root / "graph/GraphActionPresentation.js"
        owner_text = owner_path.read_text(encoding="utf-8")
        consumer_paths = (
            qml_root / "graph_canvas/GraphCanvasActionRouter.qml",
            qml_root / "graph_canvas/GraphCanvasContextMenus.qml",
            qml_root / "graph_canvas/GraphCanvasOptionsMenu.qml",
            qml_root / "graph/overlay/GraphEdgeFloatingToolbar.qml",
            qml_root / "graph/overlay/GraphNodeFloatingToolbar.qml",
            qml_root / "graph/overlay/GraphNodeToolbarPopoverHost.qml",
            qml_root / "graph/GraphNodeHost.qml",
        )
        consumer_texts = {
            path.name: path.read_text(encoding="utf-8") for path in consumer_paths
        }

        self.assertTrue(owner_text.startswith(".pragma library\n"))
        for forbidden in (
            "Item {",
            "QtObject {",
            "Timer {",
            "Loader {",
            "Connections {",
            "Binding {",
            "crop_",
            "trim_",
            "timestamp_",
            "fullscreen",
            "viewer_",
            "plot_",
            "native_",
        ):
            self.assertNotIn(forbidden, owner_text.lower() if forbidden.islower() else owner_text)

        for name, text in consumer_texts.items():
            with self.subTest(consumer=name):
                self.assertIn("GraphActionPresentation.js", text)

        forbidden_helpers = {
            "GraphCanvasActionRouter.qml": (
                "function _descriptorForActionId(",
                "function _normalizedEdgePathMode(",
            ),
            "GraphCanvasContextMenus.qml": (
                "function _edgeActionId(",
                "function _normalizedEdgePathMode(",
                "function _edgePathAction(",
                "function _normalizedEdgeDisplayMode(",
                "function _edgeDisplayModeActions(",
            ),
            "GraphCanvasOptionsMenu.qml": ("function _normalizedEdgeDisplayMode(",),
            "GraphEdgeFloatingToolbar.qml": (
                "function _toolbarActions(",
                "function _normalizedPathMode(",
                "function _normalizedDisplayMode(",
                "function _displayModeLabel(",
                "function _currentPathMode(",
                "function _currentDisplayMode(",
            ),
            "GraphNodeFloatingToolbar.qml": (
                "function _actionChecked(",
                "function _menuActionsFor(",
                "function _popoverActionsFor(",
                "function _toolbarActionById(",
                "function _filteredPopoverActions(",
                "function _checkedPopoverActionIndex(",
                "function _sourceStorageLabels(",
                "function _sourceStorageActionAt(",
                "function _popoverActionById(",
                "function _actionToolbarText(",
                "function _actionTooltipText(",
                "function _actionToolbarIcon(",
                "function _actionIconOnly(",
            ),
        }
        for name, helpers in forbidden_helpers.items():
            for helper in helpers:
                with self.subTest(consumer=name, helper=helper):
                    self.assertNotIn(helper, consumer_texts[name])

        router_text = consumer_texts["GraphCanvasActionRouter.qml"]
        for public_method in (
            "function descriptorActionId(",
            "function edgeContextActionId(",
            "function nodeContextActionId(",
            "function selectionContextActionId(",
            "function folderExplorerActionId(",
            "function triggerGraphAction(",
            "function handleEdgeContextAction(",
            "function handleNodeContextAction(",
            "function handleSelectionContextAction(",
            "function handleNodeDelegateAction(",
        ):
            self.assertIn(public_method, router_text)

        def declaration_count(text: str, type_name: str) -> int:
            return sum(line.strip() == f"{type_name} {{" for line in text.splitlines())

        combined = "\n".join(consumer_texts.values())
        self.assertEqual(
            {
                name: declaration_count(combined, name)
                for name in ("Item", "QtObject", "Timer", "Loader")
            },
            # Includes the port animation clip added to GraphNodeHost.
            {"Item": 15, "QtObject": 2, "Timer": 0, "Loader": 8},
        )

    def test_graph_node_toolbar_popover_host_directly_replaces_inline_owner(self) -> None:
        overlay_root = REPO_ROOT / "ea_node_editor/ui_qml/components/graph/overlay"
        toolbar_text = (overlay_root / "GraphNodeFloatingToolbar.qml").read_text(
            encoding="utf-8"
        )
        owner_text = (overlay_root / "GraphNodeToolbarPopoverHost.qml").read_text(
            encoding="utf-8"
        )

        def declaration_count(text: str, type_name: str) -> int:
            return sum(line.strip() == f"{type_name} {{" for line in text.splitlines())

        self.assertTrue(owner_text.startswith("// Purpose:"))
        self.assertIn("\nimport QtQuick 2.15\n", owner_text[:512])
        self.assertEqual(toolbar_text.count("GraphNodeToolbarPopoverHost {"), 1)
        self.assertNotIn(
            'objectName: "graphNodeFloatingToolbarActionPopoverBridge"', toolbar_text
        )
        self.assertEqual(
            owner_text.count(
                'objectName: "graphNodeFloatingToolbarActionPopoverBridge"'
            ),
            1,
        )
        self.assertIn("property Item toolbar: null", owner_text)
        self.assertIn("toolbar: root", toolbar_text)
        self.assertIn(
            "function openActionPopover(action, anchorItem) {\n"
            "        actionPopoverHost.openActionPopover(action, anchorItem);\n"
            "    }",
            toolbar_text,
        )

        for property_name in (
            "actionPopoverVisible",
            "actionPopoverActions",
            "actionPopoverLayout",
            "actionPopoverFontSizeDirty",
            "actionPopoverFilterText",
        ):
            with self.subTest(property_name=property_name):
                self.assertIn(f"property alias {property_name}: actionPopoverHost.", toolbar_text)
                self.assertRegex(
                    owner_text,
                    rf"property (?:bool|string|var) {property_name}:",
                )

        combined = toolbar_text + "\n" + owner_text
        self.assertEqual(
            {
                name: declaration_count(combined, name)
                for name in (
                    "Item",
                    "QtObject",
                    "Timer",
                    "Loader",
                    "Connections",
                    "Binding",
                    "Repeater",
                )
            },
            {
                "Item": 8,
                "QtObject": 0,
                "Timer": 0,
                "Loader": 0,
                "Connections": 0,
                "Binding": 2,
                "Repeater": 4,
            },
        )
        self.assertNotIn("Loader {", owner_text)
        self.assertNotIn("Timer {", owner_text)
        self.assertNotIn("QtObject {", owner_text)
        self.assertNotIn("Connections {", owner_text)
        self.assertNotIn("Binding {", owner_text)
        self.assertNotIn("factory", owner_text.lower())
        self.assertNotIn("registry", owner_text.lower())

        self.assertEqual(
            re.findall(r'objectName:\s*"([^"\n]+)', owner_text),
            [
                "graphNodeFloatingToolbarActionPopoverBridge",
                "graphNodeFloatingToolbarActionPopover",
                "graphNodeFloatingToolbarPopoverAction_",
                "graphNodeFloatingToolbarSourceStoragePanel",
                "graphNodeFloatingToolbarSourceStorageCombo",
                "graphNodeFloatingToolbarSourceBrowseButton",
                "graphNodeFloatingToolbarVideoBookmarksPanel",
                "graphNodeFloatingToolbarVideoBookmarkScroll",
                "graphNodeFloatingToolbarVideoBookmarkList",
                "graphNodeFloatingToolbarPopoverAction_",
                "graphNodeFloatingToolbarVideoBookmarkLabel_",
                "graphNodeFloatingToolbarVideoBookmarkJump_",
                "graphNodeFloatingToolbarVideoBookmarkDelete_",
                "graphNodeFloatingToolbarFontSizePanel",
                "graphNodeFloatingToolbarFontSizeField",
                "graphNodeFloatingToolbarFontSizeSlider",
                "graphNodeFloatingToolbarFontSizeStepper",
                "graphNodeFloatingToolbarPopoverAction_",
                "graphNodeFloatingToolbarPdfPagePanel",
                "graphNodeFloatingToolbarPopoverAction_pdf_page_previous",
                "graphNodeFloatingToolbarPdfPageField",
                "graphNodeFloatingToolbarPdfPageTotalLabel",
                "graphNodeFloatingToolbarPopoverAction_pdf_page_next",
                "graphNodeFloatingToolbarFontFamilyPanel",
                "graphNodeFloatingToolbarFontFamilyField",
                "graphNodeFloatingToolbarFontFamilyList",
                "graphNodeFloatingToolbarPopoverAction_",
            ],
        )

    def test_closeout_docs_publish_architecture_residual_matrix_from_packet_owned_surfaces(self) -> None:
        spec_index_text = (REPO_ROOT / manifest.SPEC_INDEX_DOC).read_text(encoding="utf-8")
        qa_acceptance_text = (REPO_ROOT / manifest.QA_ACCEPTANCE_DOC).read_text(encoding="utf-8")
        traceability_text = (REPO_ROOT / manifest.TRACEABILITY_MATRIX_DOC).read_text(encoding="utf-8")
        matrix_path = REPO_ROOT / manifest.ARCHITECTURE_RESIDUAL_REFACTOR_QA_MATRIX_DOC
        matrix_text = matrix_path.read_text(encoding="utf-8")

        self.assertIn("ARCHITECTURE_RESIDUAL_REFACTOR_QA_MATRIX.md", spec_index_text)
        self.assertIn("REQ-QA-029", qa_acceptance_text)
        self.assertIn("ARCHITECTURE_RESIDUAL_REFACTOR_QA_MATRIX.md", qa_acceptance_text)
        self.assertIn("REQ-QA-029", traceability_text)
        self.assertIn("AC-REQ-QA-029-01", traceability_text)
        self.assertIn("ARCHITECTURE_RESIDUAL_REFACTOR_QA_MATRIX.md", traceability_text)
        self.assertTrue(matrix_path.is_file())
        self.assertIn(manifest.ARCHITECTURE_RESIDUAL_REFACTOR_TARGETED_REGRESSION_COMMAND, matrix_text)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import sys
from types import SimpleNamespace
import unittest
from unittest import mock

from ea_node_editor.nodes.builtins.core import PYTHON_SCRIPT_DEFAULT_SOURCE
from ea_node_editor.ui_qml.script_editor_model import ScriptEditorModel
from tests.main_window_shell.base import MainWindowShellTestBase
from tests.shell_isolation_runtime import format_child_output
from tests.shell_isolation_runtime import run_shell_isolation_target
from tests.shell_isolation_runtime import ShellIsolationTarget
from tests.shell_isolation_runtime import ShellIsolationTargetTimeout

_SHELL_TEST_RUNNER = (
    "import sys, unittest; "
    "target = sys.argv[1]; "
    "suite = unittest.defaultTestLoader.loadTestsFromName(target); "
    "result = unittest.TextTestRunner(verbosity=2).run(suite); "
    "sys.exit(0 if result.wasSuccessful() else 1)"
)


class ScriptEditorDockTests(MainWindowShellTestBase):
    def test_canvas_port_edits_preserve_dirty_drafts_and_refresh_clean_editor(self) -> None:
        node_id = self.window.scene.add_node_from_type("core.python_script", 40.0, 40.0)
        self.window.scene.focus_node(node_id)
        self.window.set_script_editor_panel_visible(True)
        self.app.processEvents()
        from ea_node_editor.ui_qml.graph_canvas_command import GraphCanvasCommandBridge

        hints = []
        commands = GraphCanvasCommandBridge(
            scene_bridge=self.window.scene,
            workspace_edit_controller=self.window.workspace_edit_controller,
            show_graph_hint=lambda message, duration: hints.append(message),
        )
        node = self.window.model.active_workspace.nodes[node_id]
        source = node.properties["script"]
        draft = source + "\n# unsaved work\n"
        self.window.script_editor.set_script_text(draft)
        self.assertEqual(commands.insert_dynamic_port(node_id, "inputs", 1), "")
        self.assertEqual(commands.remove_dynamic_port(node_id, "outputs", "result"), {})
        self.assertEqual(node.properties["script"], source)
        self.assertEqual(self.window.script_editor.script_text, draft)
        self.assertTrue(self.window.script_editor.dirty)
        self.assertIn("Apply or Revert", hints[-1])
        self.window.script_editor.revert()
        self.assertEqual(commands.insert_dynamic_port(node_id, "inputs", 1), "input1")
        self.app.processEvents()
        self.assertEqual(self.window.script_editor.script_text, node.properties["script"])
        self.assertFalse(self.window.script_editor.dirty)
        self.assertTrue(self.window.script_editor.apply())
        self.assertIn('@corex.input("input1"', node.properties["script"])
        after_add = node.properties["script"]
        self.assertTrue(self.window.workspace_edit_controller.undo())
        self.assertEqual(self.window.script_editor.script_text, source)
        self.assertFalse(self.window.script_editor.dirty)
        self.assertTrue(self.window.workspace_edit_controller.redo())
        self.assertEqual(self.window.script_editor.script_text, after_add)
        dirty_after_add = after_add + "\n# keep my draft during Undo\n"
        self.window.script_editor.set_script_text(dirty_after_add)
        self.assertTrue(self.window.workspace_edit_controller.undo())
        self.assertEqual(self.window.script_editor.script_text, dirty_after_add)
        self.assertTrue(self.window.script_editor.dirty)
        self.window.script_editor.revert()
        self.assertEqual(self.window.script_editor.script_text, source)
        self.assertEqual(self.window.model.active_workspace.nodes[node_id].properties["script"], source)
        self.assertFalse(self.window.script_editor.dirty)
        self.assertTrue(self.window.script_editor.apply())
        self.assertEqual(self.window.model.active_workspace.nodes[node_id].properties["script"], source)

    def test_script_editor_binds_to_selected_python_script_node(self) -> None:
        script_node_id = self.window.scene.add_node_from_type("core.python_script", x=40.0, y=40.0)
        workspace_id = self.window.workspace_manager.active_workspace_id()
        workspace = self.window.model.project.workspaces[workspace_id]
        workspace.nodes[script_node_id].properties["script"] = PYTHON_SCRIPT_DEFAULT_SOURCE

        self.window.scene.focus_node(script_node_id)
        self.app.processEvents()

        self.window.set_script_editor_panel_visible(True)
        self.app.processEvents()
        self.assertEqual(self.window.script_editor.current_node_id, script_node_id)
        self.assertEqual(self.window.script_editor.current_node_label, workspace.nodes[script_node_id].title)
        self.assertNotIn(script_node_id, self.window.script_editor.current_node_label)
        self.assertIn("@corex.node", self.window.script_editor.script_text)

        updated_source = PYTHON_SCRIPT_DEFAULT_SOURCE.replace(
            'return {"result": payload}',
            'return {"result": payload, **({} if ctx is None else {})}',
        )
        self.window.script_editor.set_script_text(updated_source)
        self.assertTrue(self.window.script_editor.apply())
        self.app.processEvents()
        self.assertEqual(workspace.nodes[script_node_id].properties["script"], updated_source)
        self.assertFalse(self.window.script_editor.dirty)

    def test_script_apply_failure_keeps_draft_dirty(self) -> None:
        editor = ScriptEditorModel()
        editor.set_node(
            SimpleNamespace(
                node_id="node_script",
                type_id="core.python_script",
                title="Script",
                properties={"script": "result = payload"},
            )
        )
        editor.set_script_text("result = payload + 1")

        self.assertFalse(editor.apply())
        self.assertTrue(editor.dirty)
        self.assertEqual(editor.script_text, "result = payload + 1")

    def test_numeric_overflow_draft_stays_dirty_and_leaves_graph_unchanged(self) -> None:
        script_node_id = self.window.scene.add_node_from_type(
            "core.python_script", x=40.0, y=40.0
        )
        workspace = self.window.model.active_workspace
        applied_source = workspace.nodes[script_node_id].properties["script"]
        self.window.scene.focus_node(script_node_id)
        self.window.set_script_editor_panel_visible(True)
        self.app.processEvents()

        huge = "9" * 400
        self.window.script_editor.set_script_text(
            f'''@corex.node
@corex.slider("scale", default={huge}, minimum=0.0, maximum=1.0)
def run(ctx, scale):
    return {{}}
'''
        )
        self.assertFalse(self.window.script_editor.apply())
        self.app.processEvents()

        self.assertEqual(
            workspace.nodes[script_node_id].properties["script"], applied_source
        )
        self.assertTrue(self.window.script_editor.dirty)
        self.assertGreaterEqual(self.window.console_panel.error_count, 1)

    def test_script_apply_failure_draft_survives_panel_reopen(self) -> None:
        script_node_id = self.window.scene.add_node_from_type(
            "core.python_script", x=40.0, y=40.0
        )
        workspace = self.window.model.active_workspace
        applied_source = workspace.nodes[script_node_id].properties["script"]
        self.window.scene.focus_node(script_node_id)
        self.window.set_script_editor_panel_visible(True)
        self.app.processEvents()

        draft = applied_source.replace(
            "@corex.node",
            '@corex.node\n@corex.text("title", default="Plot")',
        )
        self.window.script_editor.set_script_text(draft)
        self.assertFalse(self.window.script_editor.apply())
        self.window.set_script_editor_panel_visible(False)
        self.window.set_script_editor_panel_visible(True)
        self.app.processEvents()

        self.assertEqual(
            workspace.nodes[script_node_id].properties["script"], applied_source
        )
        self.assertEqual(self.window.script_editor.script_text, draft)
        self.assertTrue(self.window.script_editor.dirty)

    def test_script_draft_survives_same_node_property_refresh(self) -> None:
        script_node_id = self.window.scene.add_node_from_type(
            "core.python_script",
            x=40.0,
            y=40.0,
        )
        self.window.scene.focus_node(script_node_id)
        self.window.set_script_editor_panel_visible(True)
        self.app.processEvents()
        draft = PYTHON_SCRIPT_DEFAULT_SOURCE.replace("payload}", "payload + 1}")
        self.window.script_editor.set_script_text(draft)

        with mock.patch.object(
            self.window.script_editor,
            "set_node",
            wraps=self.window.script_editor.set_node,
        ) as set_node:
            self.window.scene.set_node_property(script_node_id, "timeout_sec", 1.0)
            self.app.processEvents()

        set_node.assert_not_called()
        self.assertTrue(self.window.script_editor.dirty)
        self.assertEqual(self.window.script_editor.script_text, draft)

    def test_script_editor_state_persists_in_metadata(self) -> None:
        self.assertFalse(self.window.model.project.metadata["ui"]["script_editor"]["visible"])
        self.window.set_script_editor_panel_visible(True)
        self.app.processEvents()
        self.assertTrue(self.window.model.project.metadata["ui"]["script_editor"]["visible"])
        self.window.set_script_editor_panel_visible(False)
        self.app.processEvents()
        self.assertFalse(self.window.model.project.metadata["ui"]["script_editor"]["visible"])

    def test_script_editor_panel_width_persists_in_metadata(self) -> None:
        self.assertEqual(self.window.model.project.metadata["ui"]["script_editor"]["width"], 0.0)
        self.window.script_editor.set_width(640.0)
        self.app.processEvents()
        self.assertEqual(self.window.script_editor.panel_width, 640.0)
        self.assertEqual(self.window.model.project.metadata["ui"]["script_editor"]["width"], 0.0)

        self.window.project_session_controller.persist_script_editor_state()
        self.assertEqual(self.window.model.project.metadata["ui"]["script_editor"]["width"], 640.0)

        # Negative widths fall back to "unset" so the panel uses its responsive default.
        self.window.script_editor.set_width(-25.0)
        self.app.processEvents()
        self.assertEqual(self.window.script_editor.panel_width, 0.0)

        self.window.project_session_controller.persist_script_editor_state()
        self.assertEqual(self.window.model.project.metadata["ui"]["script_editor"]["width"], 0.0)

    def test_script_editor_exposes_cursor_diagnostics_and_dirty_state(self) -> None:
        script_node_id = self.window.scene.add_node_from_type("core.python_script", x=40.0, y=40.0)
        workspace_id = self.window.workspace_manager.active_workspace_id()
        workspace = self.window.model.project.workspaces[workspace_id]
        workspace.nodes[script_node_id].properties["script"] = PYTHON_SCRIPT_DEFAULT_SOURCE

        self.window.scene.focus_node(script_node_id)
        self.window.set_script_editor_panel_visible(True)
        self.app.processEvents()

        self.window.script_editor.set_script_text(
            PYTHON_SCRIPT_DEFAULT_SOURCE.replace("payload}", "payload + 123}")
        )
        self.window.script_editor.set_cursor_metrics(1, 6, 5, 5)
        self.app.processEvents()

        self.assertTrue(self.window.script_editor.dirty)
        self.assertIn("Ln 1, Col 6", self.window.script_editor.cursor_label)
        self.assertIn("Sel 5", self.window.script_editor.cursor_label)
        self.assertIn("Pos 5", self.window.script_editor.cursor_label)

    def test_set_script_editor_panel_visible_focuses_editor_for_script_node(self) -> None:
        script_node_id = self.window.scene.add_node_from_type("core.python_script", x=40.0, y=40.0)
        self.window.scene.focus_node(script_node_id)
        self.app.processEvents()

        self.window.set_script_editor_panel_visible(True)
        self.app.processEvents()

        self.assertTrue(self.window.script_editor.has_focus)


class _SubprocessShellWindowTest(unittest.TestCase):
    __test__ = False

    def __init__(self, target: str) -> None:
        super().__init__(methodName="runTest")
        self._target = target

    def id(self) -> str:
        return self._target

    def __str__(self) -> str:
        return self._target

    def shortDescription(self) -> str:
        return self._target

    def runTest(self) -> None:
        target = ShellIsolationTarget(
            target_id=self._target,
            command=(sys.executable, "-c", _SHELL_TEST_RUNNER, self._target),
        )
        try:
            result = run_shell_isolation_target(target)
        except ShellIsolationTargetTimeout as exc:
            self.fail(str(exc))
        if result.returncode == 0:
            return
        self.fail(
            f"Subprocess shell test failed for {self._target} "
            f"(exit={result.returncode}).\n{format_child_output(result)}"
        )


def load_tests(loader: unittest.TestLoader, _tests, _pattern):  # noqa: ANN001
    suite = unittest.TestSuite()
    for test_name in loader.getTestCaseNames(ScriptEditorDockTests):
        target = f"{ScriptEditorDockTests.__module__}.{ScriptEditorDockTests.__qualname__}.{test_name}"
        suite.addTest(_SubprocessShellWindowTest(target))
    return suite


if __name__ == "__main__":
    unittest.main()

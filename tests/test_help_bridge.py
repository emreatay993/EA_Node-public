from __future__ import annotations

import unittest
from types import SimpleNamespace

from ea_node_editor.help.help_bridge import HelpBridge
from ea_node_editor.runtime_contracts import GRAPH_DATA_TYPE_ID, STRING_DATA_TYPE_ID


class _SceneStub:
    def __init__(self, node_id: str = "") -> None:
        self._node_id = node_id

    def selected_node_id(self) -> str:
        return self._node_id


class _ShellWindowStub:
    def __init__(self, node_id: str = "", spec: object | None = None) -> None:
        self.scene = _SceneStub(node_id)
        self.registry = _RegistryStub(spec) if spec is not None else None
        self.active_workspace_id = "ws"
        self.model = SimpleNamespace(
            project=SimpleNamespace(
                workspaces={
                    "ws": SimpleNamespace(
                        nodes={node_id: SimpleNamespace(type_id=spec.type_id)}
                        if node_id and spec is not None
                        else {}
                    )
                }
            )
        )


class _RegistryStub:
    def __init__(self, spec: object | None = None) -> None:
        self._spec = spec

    def spec_or_none(self, type_id: str) -> object:
        del type_id
        return self._spec


def _logger_spec() -> SimpleNamespace:
    return SimpleNamespace(
        display_name="Logger",
        type_id="core.logger",
        description="Writes values to the execution log.",
        keywords=("log", "debug"),
        ports=(),
    )


class HelpBridgeSelectedNodeTests(unittest.TestCase):
    def test_show_help_for_selected_node_requests_help_tab_without_docs(self) -> None:
        shell_window = _ShellWindowStub("node-1")
        bridge = HelpBridge(shell_window=shell_window)
        requested: list[bool] = []
        bridge.help_tab_requested.connect(lambda: requested.append(True))

        result = bridge.show_help_for_selected_node()

        self.assertFalse(result)
        self.assertEqual(requested, [True])
        self.assertFalse(bridge.visible)

    def test_show_help_for_selected_node_loads_markdown_for_selected_node(self) -> None:
        shell_window = _ShellWindowStub("node-1", _logger_spec())
        bridge = HelpBridge(shell_window=shell_window)
        requested: list[bool] = []
        bridge.help_tab_requested.connect(lambda: requested.append(True))

        result = bridge.show_help_for_selected_node()

        self.assertTrue(result)
        self.assertEqual(requested, [True])
        self.assertTrue(bridge.visible)
        self.assertIn("# Logger", bridge.markdown)
        self.assertEqual(bridge.type_id, "core.logger")
        self.assertEqual(bridge.title, "Logger")

    def test_show_help_for_selected_node_clears_stale_markdown(self) -> None:
        shell_window = _ShellWindowStub("node-1", _logger_spec())
        bridge = HelpBridge(shell_window=shell_window)
        self.assertTrue(bridge.show_help_for_selected_node())
        self.assertIn("# Logger", bridge.markdown)
        self.assertTrue(bridge.has_help)

        shell_window.registry = None
        self.assertFalse(bridge.show_help_for_selected_node())
        self.assertEqual(bridge.markdown, "")
        self.assertFalse(bridge.has_help)
        self.assertEqual(bridge.title, "")
        self.assertEqual(bridge.type_id, "")

    def test_can_show_help_for_selected_node_uses_current_selection(self) -> None:
        shell_window = _ShellWindowStub("node-1", _logger_spec())
        bridge = HelpBridge(shell_window=shell_window)

        self.assertTrue(bridge.can_show_help_for_selected_node())

    def test_show_help_for_type_builds_structured_fallback_for_registered_node(self) -> None:
        spec = SimpleNamespace(
            display_name="Logger",
            type_id="core.logger",
            description="Writes values to the execution log.",
            keywords=("log", "debug"),
            ports=(
                SimpleNamespace(
                    key="message",
                    label="Message",
                    description="Message written to the log.",
                    direction="in",
                    kind="data",
                    data_type=STRING_DATA_TYPE_ID,
                    data_access="tree",
                ),
            ),
        )
        shell_window = _ShellWindowStub()
        shell_window.registry = _RegistryStub(spec)
        bridge = HelpBridge(shell_window=shell_window)
        requested: list[bool] = []
        bridge.help_tab_requested.connect(lambda: requested.append(True))

        result = bridge.show_help_for_type("core.logger")

        self.assertTrue(result)
        self.assertEqual(requested, [True])
        self.assertIn("# Logger", bridge.markdown)
        self.assertIn("**Keywords:** log, debug", bridge.markdown)
        self.assertIn("## Inputs", bridge.markdown)
        self.assertIn("Message written to the log.", bridge.markdown)
        self.assertNotIn("## Outputs", bridge.markdown)

    def test_show_help_for_type_renders_trigger_benchmark_copy(self) -> None:
        from ea_node_editor.nodes.builtins.core import TriggerNodePlugin

        shell_window = _ShellWindowStub()
        shell_window.registry = _RegistryStub(TriggerNodePlugin().spec())
        bridge = HelpBridge(shell_window=shell_window)

        self.assertTrue(bridge.show_help_for_type("core.trigger"))
        self.assertIn("# Trigger", bridge.markdown)
        self.assertIn(
            "Stop downstream nodes from running until you click the button.",
            bridge.markdown,
        )
        self.assertIn(
            "**Keywords:** button, action, run, dam, gate, block", bridge.markdown
        )
        self.assertIn("## Inputs", bridge.markdown)
        self.assertIn(
            f"- **Input** (`input`, `{GRAPH_DATA_TYPE_ID}`) — The data that is blocked until you "
            "click the button.",
            bridge.markdown,
        )
        self.assertIn("## Outputs", bridge.markdown)
        self.assertIn(
            f"- **Output** (`output`, `{GRAPH_DATA_TYPE_ID}`) — The current output. The output is "
            "not updated until you click the button.",
            bridge.markdown,
        )


if __name__ == "__main__":
    unittest.main()

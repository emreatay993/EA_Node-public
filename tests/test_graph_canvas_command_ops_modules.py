"""MRO insurance for the graph_canvas_command mixin package.

Every ``@pyqtSlot`` declared on a per-domain ops mixin must register in the
composed ``GraphCanvasCommandBridge`` QMetaObject, and the composed class
must resolve each mixin method to that mixin's own function (no accidental
shadowing between domains). Guards the P3 decomposition against PyQt
meta-object regressions and against future cross-mixin name collisions.
"""

from __future__ import annotations

import unittest
from types import SimpleNamespace

from PyQt6.QtCore import QMetaMethod

from ea_node_editor.ui_qml.graph_canvas_command import GraphCanvasCommandBridge
from ea_node_editor.ui_qml.graph_canvas_command.annotation_style_ops import AnnotationStyleOps
from ea_node_editor.ui_qml.graph_canvas_command.canvas_host_ops import CanvasHostOps
from ea_node_editor.ui_qml.graph_canvas_command.folder_explorer_ops import FolderExplorerOps
from ea_node_editor.ui_qml.graph_canvas_command.graphics_settings_ops import GraphicsSettingsOps
from ea_node_editor.ui_qml.graph_canvas_command.media_image_ops import MediaImageOps
from ea_node_editor.ui_qml.graph_canvas_command.media_video_ops import MediaVideoOps
from ea_node_editor.ui_qml.graph_canvas_command.node_creation_ops import NodeCreationOps
from ea_node_editor.ui_qml.graph_canvas_command.scene_mutation_ops import SceneMutationOps
from ea_node_editor.ui_qml.graph_canvas_command.viewport_ops import ViewportOps

OPS_MIXINS = (
    AnnotationStyleOps,
    CanvasHostOps,
    FolderExplorerOps,
    GraphicsSettingsOps,
    MediaImageOps,
    MediaVideoOps,
    NodeCreationOps,
    SceneMutationOps,
    ViewportOps,
)


def _meta_slot_names(cls: type) -> set[str]:
    meta = cls.staticMetaObject
    return {
        bytes(meta.method(index).name()).decode("utf-8")
        for index in range(meta.methodCount())
        if meta.method(index).methodType() == QMetaMethod.MethodType.Slot
    }


def _declared_slot_names(mixin: type) -> set[str]:
    return {
        name
        for name, value in vars(mixin).items()
        if callable(value) and hasattr(value, "__pyqtSignature__")
    }


class GraphCanvasCommandOpsModuleTests(unittest.TestCase):
    def test_settings_group_expansion_forwards_result_and_arguments(self) -> None:
        class SceneCommandSource:
            def __init__(self) -> None:
                self.calls: list[tuple[str, str, bool]] = []

            def set_node_settings_group_expanded(
                self,
                node_id: str,
                group_id: str,
                expanded: bool,
            ) -> bool:
                self.calls.append((node_id, group_id, expanded))
                return expanded

        source = SceneCommandSource()
        bridge = GraphCanvasCommandBridge(
            scene_bridge=SimpleNamespace(command_bridge=source),  # type: ignore[arg-type]
        )

        self.assertTrue(
            bridge.set_node_settings_group_expanded(
                "node_signal",
                "general_options",
                True,
            )
        )
        self.assertFalse(
            bridge.set_node_settings_group_expanded(
                "node_signal",
                "general_options",
                False,
            )
        )
        self.assertEqual(
            source.calls,
            [
                ("node_signal", "general_options", True),
                ("node_signal", "general_options", False),
            ],
        )

    def test_every_mixin_slot_registers_on_composed_bridge(self) -> None:
        registered = _meta_slot_names(GraphCanvasCommandBridge)
        for mixin in OPS_MIXINS:
            declared = _declared_slot_names(mixin)
            with self.subTest(mixin=mixin.__name__):
                self.assertTrue(declared, f"{mixin.__name__} declares no slots")
                missing = sorted(declared - registered)
                self.assertEqual(
                    missing,
                    [],
                    f"{mixin.__name__} slots missing from the composed QMetaObject",
                )

    def test_composed_bridge_resolves_methods_to_their_mixin(self) -> None:
        for mixin in OPS_MIXINS:
            for name, value in vars(mixin).items():
                if name.startswith("__"):
                    continue
                if isinstance(value, (staticmethod, classmethod)):
                    value = value.__func__
                elif not callable(value):
                    continue
                with self.subTest(mixin=mixin.__name__, method=name):
                    resolved = getattr(GraphCanvasCommandBridge, name)
                    resolved = getattr(resolved, "__func__", resolved)
                    self.assertIs(
                        resolved,
                        value,
                        f"{name} is shadowed by another class in the MRO",
                    )

    def test_no_slot_name_collisions_between_mixins(self) -> None:
        seen: dict[str, str] = {}
        for mixin in OPS_MIXINS:
            for name in vars(mixin):
                if name.startswith("__"):
                    continue
                if name in seen:
                    self.fail(f"{name} defined in both {seen[name]} and {mixin.__name__}")
                seen[name] = mixin.__name__


if __name__ == "__main__":
    unittest.main()

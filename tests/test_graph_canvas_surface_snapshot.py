"""Frozen QML-visible meta-object surface for the graph-canvas owner family.

Campaign invariant for the graph-canvas pipeline decomposition: every slot
signature, property (name/type/notify), and signal that QML can see on the
bridge classes is frozen. Additions are allowed; removals and renames fail
this test. This is what keeps the Python-side restructuring (payload package,
command/state mixin packages) provably invisible to QML.

The snapshot is committed at tests/fixtures/graph_canvas_surface_snapshot.json.

Maintenance:
- Regenerate after an intentional surface addition:
    .\\venv\\Scripts\\python.exe -m tests.test_graph_canvas_surface_snapshot --write
- Verify the surface is byte-identical to the committed snapshot (used as the
  P3/P4 mixin-phase gate, stricter than the test itself):
    .\\venv\\Scripts\\python.exe -m tests.test_graph_canvas_surface_snapshot --check-exact

Introspection is instantiate-free: it reads ``staticMetaObject`` so no bridge
dependencies, QApplication, or QML engine are required.
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

from PyQt6.QtCore import QMetaMethod, QObject

from ea_node_editor.ui_qml.graph_canvas_command import GraphCanvasCommandBridge
from ea_node_editor.ui_qml.graph_canvas_state import GraphCanvasStateBridge
from ea_node_editor.ui_qml.graph_scene import (
    GraphSceneCommandBridge,
    GraphScenePolicyBridge,
    GraphSceneReadBridge,
)
from ea_node_editor.ui_qml.graph_scene_bridge import GraphSceneBridge
from ea_node_editor.ui_qml.shell_context_bootstrap import ShellContextBundle
from ea_node_editor.ui_qml.viewport_bridge import ViewportBridge

SNAPSHOT_PATH = (
    Path(__file__).resolve().parent / "fixtures" / "graph_canvas_surface_snapshot.json"
)

BRIDGE_CLASSES: dict[str, type[QObject]] = {
    "GraphCanvasCommandBridge": GraphCanvasCommandBridge,
    "GraphCanvasStateBridge": GraphCanvasStateBridge,
    "GraphSceneBridge": GraphSceneBridge,
    "GraphSceneCommandBridge": GraphSceneCommandBridge,
    "GraphScenePolicyBridge": GraphScenePolicyBridge,
    "GraphSceneReadBridge": GraphSceneReadBridge,
    "ShellContextBundle": ShellContextBundle,
    "ViewportBridge": ViewportBridge,
}

_METHOD_CATEGORY = {
    QMetaMethod.MethodType.Signal: "signals",
    QMetaMethod.MethodType.Slot: "slots",
    QMetaMethod.MethodType.Method: "invokables",
}


def _qobject_base_method_signatures() -> set[str]:
    meta = QObject.staticMetaObject
    return {
        bytes(meta.method(index).methodSignature()).decode("utf-8")
        for index in range(meta.methodCount())
    }


def _qobject_base_property_names() -> set[str]:
    meta = QObject.staticMetaObject
    return {meta.property(index).name() for index in range(meta.propertyCount())}


def build_bridge_surface(cls: type[QObject]) -> dict[str, list[str]]:
    """Full QML-visible surface of ``cls`` (own + inherited, minus QObject)."""
    meta = cls.staticMetaObject
    base_methods = _qobject_base_method_signatures()
    base_properties = _qobject_base_property_names()
    surface: dict[str, list[str]] = {
        "signals": [],
        "slots": [],
        "invokables": [],
        "properties": [],
    }
    for index in range(meta.methodCount()):
        method = meta.method(index)
        signature = bytes(method.methodSignature()).decode("utf-8")
        if signature in base_methods:
            continue
        category = _METHOD_CATEGORY.get(method.methodType())
        if category is None:
            continue
        return_type = method.typeName() or "void"
        surface[category].append(f"{return_type} {signature}")
    for index in range(meta.propertyCount()):
        prop = meta.property(index)
        if prop.name() in base_properties:
            continue
        entry = f"{prop.typeName()} {prop.name()}"
        if prop.isConstant():
            entry += " CONSTANT"
        elif prop.hasNotifySignal():
            notify = bytes(prop.notifySignal().methodSignature()).decode("utf-8")
            entry += f" NOTIFY {notify}"
        surface["properties"].append(entry)
    return {category: sorted(entries) for category, entries in surface.items()}


def build_full_snapshot() -> dict[str, dict[str, list[str]]]:
    return {name: build_bridge_surface(cls) for name, cls in sorted(BRIDGE_CLASSES.items())}


def load_committed_snapshot() -> dict[str, dict[str, list[str]]]:
    return json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))


class GraphCanvasSurfaceSnapshotTests(unittest.TestCase):
    """Removals/renames from the QML-visible bridge surface are forbidden."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.committed = load_committed_snapshot()
        cls.current = build_full_snapshot()

    def test_all_snapshot_classes_still_exist(self) -> None:
        missing_classes = sorted(set(self.committed) - set(self.current))
        self.assertEqual(
            missing_classes,
            [],
            "Bridge classes disappeared from the snapshot scope; the QML-visible "
            "surface freeze is violated.",
        )

    def test_no_snapshot_entry_removed_or_renamed(self) -> None:
        problems: list[str] = []
        for class_name, committed_surface in sorted(self.committed.items()):
            current_surface = self.current.get(class_name, {})
            for category, committed_entries in committed_surface.items():
                current_entries = set(current_surface.get(category, []))
                for entry in committed_entries:
                    if entry not in current_entries:
                        problems.append(f"{class_name}.{category}: {entry}")
        self.assertEqual(
            problems,
            [],
            "QML-visible bridge surface entries were removed or renamed (campaign "
            "invariant: additions allowed, removals/renames forbidden). If a removal "
            "is intentional and QML callers were swept, regenerate the snapshot with: "
            "python -m tests.test_graph_canvas_surface_snapshot --write\n"
            + "\n".join(problems),
        )


def _main(argv: list[str]) -> int:
    if "--write" in argv:
        SNAPSHOT_PATH.write_text(
            json.dumps(build_full_snapshot(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(f"Snapshot written: {SNAPSHOT_PATH}")
        return 0
    if "--check-exact" in argv:
        committed = load_committed_snapshot()
        current = build_full_snapshot()
        if committed == current:
            print("Bridge surface is byte-identical to the committed snapshot.")
            return 0
        for class_name in sorted(set(committed) | set(current)):
            for category in ("signals", "slots", "invokables", "properties"):
                before = set(committed.get(class_name, {}).get(category, []))
                after = set(current.get(class_name, {}).get(category, []))
                for entry in sorted(before - after):
                    print(f"- {class_name}.{category}: {entry}")
                for entry in sorted(after - before):
                    print(f"+ {class_name}.{category}: {entry}")
        return 1
    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1:]))

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from PyQt6.QtCore import QRectF, QTimer
from PyQt6.QtWidgets import QApplication

from ea_node_editor.nodes.execution_context import NodeResult
from ea_node_editor.nodes.node_specs import NodeTypeSpec, PortSpec
from ea_node_editor.nodes.registry import NodeRegistry
from ea_node_editor.ui.shell.controllers.app_preferences_controller import AppPreferencesController
from ea_node_editor.ui.shell.window import ShellWindow
from ea_node_editor.ui.theme import DEFAULT_THEME_ID, build_theme_stylesheet, resolve_theme_id


@dataclass(frozen=True, slots=True)
class _PreviewNodeDefinition:
    key: str
    display_name: str
    variant: str
    title: str
    x: float
    y: float
    width: float
    height: float
    ports: tuple[PortSpec, ...]


_PREVIEW_NODE_PREFIX = "preview.p07_flowchart"
_PREVIEW_NODES: tuple[_PreviewNodeDefinition, ...] = (
    _PreviewNodeDefinition(
        key="start",
        display_name="P07 Start",
        variant="start",
        title="Start",
        x=560.0,
        y=40.0,
        width=220.0,
        height=82.0,
        ports=(PortSpec("flow_out", "out", "flow", "any", allow_multiple_connections=True),),
    ),
    _PreviewNodeDefinition(
        key="document",
        display_name="P07 Document",
        variant="document",
        title="Planning Document",
        x=510.0,
        y=180.0,
        width=260.0,
        height=122.0,
        ports=(
            PortSpec("flow_in", "in", "flow", "any"),
            PortSpec("flow_out", "out", "flow", "any", allow_multiple_connections=True),
        ),
    ),
    _PreviewNodeDefinition(
        key="connector",
        display_name="P07 Connector",
        variant="connector",
        title="A",
        x=600.0,
        y=355.0,
        width=96.0,
        height=96.0,
        ports=(
            PortSpec("flow_in", "in", "flow", "any", allow_multiple_connections=True),
            PortSpec("flow_out", "out", "flow", "any", allow_multiple_connections=True),
        ),
    ),
    _PreviewNodeDefinition(
        key="decision",
        display_name="P07 Decision",
        variant="decision",
        title="Good Plugin?",
        x=500.0,
        y=500.0,
        width=250.0,
        height=150.0,
        ports=(
            PortSpec("flow_in", "in", "flow", "any"),
            PortSpec("branch_yes", "out", "flow", "any", allow_multiple_connections=True),
            PortSpec("branch_no", "out", "flow", "any", allow_multiple_connections=True),
        ),
    ),
    _PreviewNodeDefinition(
        key="input_output",
        display_name="P07 Input / Output",
        variant="input_output",
        title="Feedback",
        x=80.0,
        y=680.0,
        width=250.0,
        height=92.0,
        ports=(
            PortSpec("flow_in", "in", "flow", "any"),
            PortSpec("flow_out", "out", "flow", "any", allow_multiple_connections=True),
        ),
    ),
    _PreviewNodeDefinition(
        key="process",
        display_name="P07 Process",
        variant="process",
        title="Improve",
        x=120.0,
        y=830.0,
        width=230.0,
        height=88.0,
        ports=(
            PortSpec("flow_in", "in", "flow", "any"),
            PortSpec("flow_out", "out", "flow", "any", allow_multiple_connections=True),
        ),
    ),
    _PreviewNodeDefinition(
        key="predefined_process",
        display_name="P07 Predefined Process",
        variant="predefined_process",
        title="Obsidian's Review",
        x=520.0,
        y=830.0,
        width=290.0,
        height=92.0,
        ports=(
            PortSpec("flow_in", "in", "flow", "any", allow_multiple_connections=True),
            PortSpec("flow_out", "out", "flow", "any", allow_multiple_connections=True),
        ),
    ),
    _PreviewNodeDefinition(
        key="database",
        display_name="P07 Database",
        variant="database",
        title="Community Plugins DB",
        x=540.0,
        y=980.0,
        width=260.0,
        height=150.0,
        ports=(
            PortSpec("flow_in", "in", "flow", "any"),
            PortSpec("flow_out", "out", "flow", "any", allow_multiple_connections=True),
        ),
    ),
    _PreviewNodeDefinition(
        key="end",
        display_name="P07 End",
        variant="end",
        title="Plugin Available",
        x=560.0,
        y=1180.0,
        width=230.0,
        height=82.0,
        ports=(PortSpec("flow_in", "in", "flow", "any", allow_multiple_connections=True),),
    ),
)


class _PreviewNodePlugin:
    def __init__(self, spec: NodeTypeSpec) -> None:
        self._spec = spec

    def spec(self) -> NodeTypeSpec:
        return self._spec

    def execute(self, _ctx) -> NodeResult:  # noqa: ANN001
        return NodeResult(outputs={})


def _preview_type_id(key: str) -> str:
    return f"{_PREVIEW_NODE_PREFIX}.{key}"


def _register_preview_nodes(registry: NodeRegistry) -> None:
    for definition in _PREVIEW_NODES:
        type_id = _preview_type_id(definition.key)
        try:
            registry.get_spec(type_id)
            continue
        except KeyError:
            pass
        spec = NodeTypeSpec(
            type_id=type_id,
            display_name=definition.display_name,
            category="Preview",
            icon="branch",
            ports=definition.ports,
            properties=(),
            runtime_behavior="passive",
            surface_family="flowchart",
            surface_variant=definition.variant,
            description="Temporary P07 flowchart preview node.",
        )
        registry.register(lambda spec=spec: _PreviewNodePlugin(spec))


def _disable_persistence(window: ShellWindow) -> None:
    window.autosave_timer.stop()
    window._autosave_tick = lambda: None  # type: ignore[method-assign]
    window._persist_session = lambda project_doc=None: None  # type: ignore[method-assign]
    window._process_deferred_autosave_recovery = lambda: None  # type: ignore[method-assign]
    window.project_session_controller.persist_session = lambda project_doc=None: None  # type: ignore[method-assign]
    window.project_session_controller.discard_autosave_snapshot = lambda: None  # type: ignore[method-assign]
    window.project_session_controller.autosave_tick = lambda: None  # type: ignore[method-assign]
    window.project_session_controller.process_deferred_autosave_recovery = lambda: None  # type: ignore[method-assign]


def _seed_preview(window: ShellWindow) -> None:
    _register_preview_nodes(window.registry)
    window.project_session_controller.new_project()
    window.setWindowTitle("COREX Node Editor - P07 Flowchart Surface Preview")

    node_ids: dict[str, str] = {}
    for definition in _PREVIEW_NODES:
        node_id = window.scene.add_node_from_type(_preview_type_id(definition.key), definition.x, definition.y)
        window.scene.set_node_title(node_id, definition.title)
        window.scene.resize_node(node_id, definition.width, definition.height)
        node_ids[definition.key] = node_id

    def connect(source_key: str, source_port: str, target_key: str, target_port: str, label: str = "") -> None:
        edge_id = window.scene.add_edge(node_ids[source_key], source_port, node_ids[target_key], target_port)
        if label:
            window.scene.set_edge_label(edge_id, label)

    connect("start", "flow_out", "document", "flow_in")
    connect("document", "flow_out", "connector", "flow_in")
    connect("connector", "flow_out", "decision", "flow_in")
    connect("decision", "branch_no", "input_output", "flow_in", "No")
    connect("input_output", "flow_out", "process", "flow_in")
    connect("process", "flow_out", "predefined_process", "flow_in")
    connect("decision", "branch_yes", "predefined_process", "flow_in", "Yes")
    connect("predefined_process", "flow_out", "database", "flow_in")
    connect("database", "flow_out", "end", "flow_in")

    window.scene.clearSelection()
    window.node_library_changed.emit()
    window.console_panel.append_log(
        "info",
        "Loaded temporary P07 flowchart preview scene. Session/autosave persistence is disabled for this run.",
    )

    min_left = min(definition.x for definition in _PREVIEW_NODES)
    min_top = min(definition.y for definition in _PREVIEW_NODES)
    max_right = max(definition.x + definition.width for definition in _PREVIEW_NODES)
    max_bottom = max(definition.y + definition.height for definition in _PREVIEW_NODES)
    bounds = QRectF(min_left - 120.0, min_top - 80.0, (max_right - min_left) + 240.0, (max_bottom - min_top) + 160.0)
    window.view.set_viewport_size(float(window.quick_widget.width()), float(window.quick_widget.height()))
    window.view.frame_scene_rect(bounds)


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Launch a temporary UI preview for P07 flowchart surfaces.")
    parser.add_argument(
        "--quit-after-ms",
        type=int,
        default=0,
        help="Automatically close the preview after the given number of milliseconds.",
    )
    return parser.parse_args(argv)


def _startup_theme_id() -> str:
    try:
        graphics = AppPreferencesController().graphics_settings()
    except Exception:  # noqa: BLE001
        return DEFAULT_THEME_ID
    theme = graphics.get("theme", {}) if isinstance(graphics, dict) else {}
    return resolve_theme_id(theme.get("theme_id", DEFAULT_THEME_ID))


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(list(argv or sys.argv[1:]))
    app = QApplication(sys.argv)
    app.setApplicationName("COREX Node Editor - P07 Preview")
    app.setStyleSheet(build_theme_stylesheet(_startup_theme_id()))

    window = ShellWindow()
    _disable_persistence(window)
    window.show()
    QTimer.singleShot(0, lambda: _seed_preview(window))
    if args.quit_after_ms > 0:
        QTimer.singleShot(int(args.quit_after_ms), app.quit)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())

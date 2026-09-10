from __future__ import annotations

import json
import re
from pathlib import Path

from PyQt6.QtCore import QObject, QUrl
from PyQt6.QtGui import QColor
from PyQt6.QtQml import QQmlComponent, QQmlEngine, QQmlProperty

from ea_node_editor.ui.shell.tooltip_policy import TOOLTIP_CATEGORY_NAMES
from ea_node_editor.ui.theme import STITCH_DARK_V1, STITCH_LIGHT_V1
from ea_node_editor.ui.tooltips import (
    TOOLTIP_COPY_FILES,
    TooltipCopyBridge,
    tooltip_category,
    tooltip_text,
)
from ea_node_editor.ui_qml.theme_bridge import ThemeBridge

_REPO_ROOT = Path(__file__).resolve().parents[1]
_TOOLTIP_DIR = _REPO_ROOT / "ea_node_editor" / "ui" / "tooltips"
_COMPONENTS_DIR = _REPO_ROOT / "ea_node_editor" / "ui_qml" / "components"
_QML_DIR = _REPO_ROOT / "ea_node_editor" / "ui_qml"


def _color_name(value: object, *, include_alpha: bool = False) -> str:
    name_format = QColor.NameFormat.HexArgb if include_alpha else QColor.NameFormat.HexRgb
    return QColor(value).name(name_format)


def _alpha_color_name(value: str, alpha: float) -> str:
    color = QColor(value)
    color.setAlphaF(alpha)
    return _color_name(color, include_alpha=True)


def test_tooltip_registry_files_use_valid_shape_and_categories() -> None:
    seen: set[str] = set()
    for filename in TOOLTIP_COPY_FILES:
        data = json.loads((_TOOLTIP_DIR / filename).read_text(encoding="utf-8"))
        assert isinstance(data, dict)
        for key, entry in data.items():
            assert key not in seen
            seen.add(key)
            assert set(entry) == {"text", "category"}
            assert isinstance(entry["text"], str)
            assert entry["category"] in TOOLTIP_CATEGORY_NAMES


def test_python_and_qml_tooltip_copy_read_same_entry(qapp) -> None:  # noqa: ANN001
    assert tooltip_text("settings.graph_theme.use_selected") == "Set this theme as the active graph theme"
    assert tooltip_category("settings.graph_theme.use_selected") == "general"

    engine = QQmlEngine()
    bridge = TooltipCopyBridge()
    engine.rootContext().setContextProperty("tooltipCopyBridge", bridge)
    component = QQmlComponent(engine)
    component.setData(
        b'''
        import QtQml 2.15
        import "common/TooltipCopy.js" as TooltipCopy

        QtObject {
            property string registryText: TooltipCopy.text(tooltipCopyBridge, "settings.graph_theme.use_selected")
            property string registryCategory: TooltipCopy.category(tooltipCopyBridge, "settings.graph_theme.use_selected")
            property string fallbackText: TooltipCopy.text(tooltipCopyBridge, "missing.tooltip.key", "fallback")
        }
        ''',
        QUrl.fromLocalFile(str(_COMPONENTS_DIR / "tooltip_copy_registry_test.qml")),
    )
    assert component.status() == QQmlComponent.Status.Ready, [
        error.toString() for error in component.errors()
    ]
    item = component.create()
    try:
        assert item is not None
        assert item.property("registryText") == "Set this theme as the active graph theme"
        assert item.property("registryCategory") == "general"
        assert item.property("fallbackText") == "fallback"
    finally:
        if item is not None:
            item.deleteLater()


def test_node_library_tooltip_labels_are_registry_owned() -> None:
    assert tooltip_text("nodes.library.tooltip.input") == "Input:"
    assert tooltip_text("nodes.library.tooltip.output") == "Output:"
    assert tooltip_category("nodes.library.tooltip.input") == "general"


def test_viewer_capability_tooltips_are_registry_owned() -> None:
    assert tooltip_text("viewer.render.wireframe_unavailable") == (
        "Wireframe rendering is unavailable for this source."
    )
    assert tooltip_text("viewer.view.orientation_triad_unavailable") == (
        "The orientation triad is unavailable for this source."
    )
    assert tooltip_text("viewer.camera.projection_unavailable") == (
        "Camera projection controls are unavailable for this source."
    )


def test_managed_tooltip_tracks_shell_theme_colors_and_wraps_text(qapp) -> None:  # noqa: ANN001
    engine = QQmlEngine()
    bridge = ThemeBridge()
    engine.rootContext().setContextProperty("themeBridge", bridge)
    component = QQmlComponent(engine)
    component.setData(
        b'''
        import QtQuick 2.15
        import "common" as Common

        Item {
            width: 200
            height: 100

            Common.ManagedToolTip {
                objectName: "managedToolTip"
                parent: parent
                themeBridgeRef: themeBridge
                text: "<b>Elemental Difference</b> transforms a nodal field into an elemental field with a bounded multi-line explanation."
                textFormat: Text.RichText
                maximumTextWidth: 160
                active: false
            }
        }
        ''',
        QUrl.fromLocalFile(str(_COMPONENTS_DIR / "managed_tooltip_theme_test.qml")),
    )
    assert component.status() == QQmlComponent.Status.Ready, [
        error.toString() for error in component.errors()
    ]
    root = component.create()
    try:
        assert root is not None
        tooltip = root.findChild(QObject, "managedToolTip")
        assert tooltip is not None
        content_item = tooltip.property("contentItem")
        panel = tooltip.findChild(QObject, "managedToolTipPanel")
        assert content_item is not None
        assert panel is not None
        qapp.processEvents()

        maximum_width = tooltip.property("maximumTextWidth")
        padded_maximum_width = (
            maximum_width + tooltip.property("leftPadding") + tooltip.property("rightPadding")
        )
        assert tooltip.property("implicitWidth") <= padded_maximum_width
        assert content_item.property("width") <= maximum_width
        assert content_item.property("implicitHeight") > 40

        def assert_colors(tokens) -> None:  # noqa: ANN001
            assert _color_name(content_item.property("color")) == tokens.app_fg
            assert _color_name(panel.property("color")) == tokens.panel_alt_bg
            assert _color_name(QQmlProperty.read(panel, "border.color"), include_alpha=True) == (
                _alpha_color_name(tokens.input_border, 0.92)
            )

        assert_colors(STITCH_DARK_V1)
        bridge.apply_theme("stitch_light")
        qapp.processEvents()
        assert_colors(STITCH_LIGHT_V1)
    finally:
        if root is not None:
            root.deleteLater()


def test_graph_port_help_tooltips_use_semantic_rich_text(qapp) -> None:  # noqa: ANN001
    engine = QQmlEngine()
    component = QQmlComponent(engine)
    component.setData(
        b'''
        import QtQuick 2.15
        import "graph" as Graph

        Item {
            property string formattedText: ""
            property string neutralText: ""

            Graph.GraphNodePortsLayer {
                id: ports
                width: 200
                height: 200
            }

            Component.onCompleted: {
                formattedText = ports._portHelpTooltipText({
                    "label": "A < B",
                    "key": "out",
                    "direction": "out",
                    "kind": "data",
                    "data_type": "path",
                    "data_access": "item",
                    "help_text": "Managed path & result."
                })
                neutralText = ports._portHelpTooltipText({
                    "label": "Top",
                    "direction": "neutral",
                    "kind": "flow",
                    "data_type": "flow",
                    "help_text": "Passive visual connection."
                })
            }
        }
        ''',
        QUrl.fromLocalFile(str(_COMPONENTS_DIR / "graph_port_tooltip_test.qml")),
    )
    assert component.status() == QQmlComponent.Status.Ready, [
        error.toString() for error in component.errors()
    ]
    root = component.create()
    try:
        assert root is not None
        assert root.property("formattedText") == (
            '<b>A &lt; B</b><br><font color="#95a0b8">Output, path, Item</font>'
            '<br>Managed path &amp; result.<hr color="#3a3d45">No current output'
        )
        assert root.property("neutralText") == ""

        source = (_COMPONENTS_DIR / "graph" / "GraphNodePortRow.qml").read_text(encoding="utf-8")
        assert "row.isInput && portMouse.inactiveTooltipVisible" in source
        assert source.count("textFormat: Text.RichText") == 1
    finally:
        if root is not None:
            root.deleteLater()


def test_all_qml_tooltips_route_through_managed_tooltip() -> None:
    managed_tooltip = _COMPONENTS_DIR / "common" / "ManagedToolTip.qml"
    native_tooltip = re.compile(r"\bToolTip\s*(?:\.|\{)")
    violations = []
    for qml_path in _QML_DIR.rglob("*.qml"):
        if qml_path == managed_tooltip:
            continue
        source = qml_path.read_text(encoding="utf-8")
        for match in native_tooltip.finditer(source):
            line_number = source.count("\n", 0, match.start()) + 1
            line = source.splitlines()[line_number - 1].strip()
            violations.append(f"{qml_path.relative_to(_REPO_ROOT)}:{line_number}: {line}")

    assert not violations, "Native ToolTip usage bypasses Common.ManagedToolTip:\n" + "\n".join(violations)

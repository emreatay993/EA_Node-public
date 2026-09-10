# Purpose: Exercise and capture the registered Mechanical controls through the production GraphCanvas route.
# Map: testing/qml_and_graph_surface_tests.md
# Tests: this file

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys


NODE_IDS = (
    "mechanical.open_model",
    "mechanical.search_tree",
    "mechanical.fea_table",
    "mechanical.camera_views",
    "mechanical.export_image",
    "mechanical.run_script",
    "mechanical.apdl_snippet",
    "mechanical.save_model",
)


def _run_visual_cohort(
    evidence_root: Path,
    scale_label: str,
    *,
    display_attached: bool,
    defaults_only: bool = False,
    light_sheets_only: bool = False,
) -> None:
    os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "Basic")
    from PyQt6.QtCore import (
        QObject,
        QPoint,
        QPointF,
        QRectF,
        Qt,
        QUrl,
        pyqtProperty,
        pyqtSignal,
    )
    from PyQt6.QtGui import QColor, QFont, QFontDatabase, QFontInfo, QImage, QPainter
    from PyQt6.QtQml import QQmlComponent, QQmlEngine
    from PyQt6.QtQuick import QQuickItem, QQuickWindow
    from PyQt6.QtSvg import QSvgRenderer
    from PyQt6.QtTest import QTest
    from PyQt6.QtWidgets import QApplication

    from ea_node_editor.addons.mechanical import runtime as mechanical_runtime
    from ea_node_editor.graph.model import GraphModel
    from ea_node_editor.nodes.bootstrap import build_default_registry
    from ea_node_editor.ui.media_preview_provider import (
        LOCAL_MEDIA_PREVIEW_PROVIDER_ID,
        LocalMediaPreviewImageProvider,
    )
    from ea_node_editor.ui_qml.graph_canvas_command import GraphCanvasCommandBridge
    from ea_node_editor.ui_qml.graph_canvas_state import GraphCanvasStateBridge
    from ea_node_editor.ui_qml.graph_scene_bridge import GraphSceneBridge
    from ea_node_editor.ui_qml.graph_theme_bridge import GraphThemeBridge
    from ea_node_editor.ui_qml.theme_bridge import ThemeBridge
    from ea_node_editor.ui_qml.viewport_bridge import ViewportBridge

    repo_root = Path(__file__).resolve().parents[2]
    evidence_root.mkdir(parents=True, exist_ok=True)
    app = QApplication.instance() or QApplication([])
    if display_attached:
        assert app.platformName().casefold() == "windows", app.platformName()

    arial_path = Path("C:/Windows/Fonts/arial.ttf")
    assert arial_path.is_file(), arial_path
    font_id = QFontDatabase.addApplicationFont(str(arial_path))
    assert font_id >= 0
    font_families = QFontDatabase.applicationFontFamilies(font_id)
    assert font_families
    app.setFont(QFont(font_families[0]))
    assert QFontInfo(app.font()).family() == "Arial"

    class TypographyHost(QObject):
        graphics_preferences_changed = pyqtSignal()

        def __init__(self, label_size: int, icon_size: int) -> None:
            super().__init__()
            self.graphics_graph_label_pixel_size = label_size
            self.graphics_node_title_icon_pixel_size = icon_size

    class ShellContext(QObject):
        def __init__(self, theme_bridge: ThemeBridge, graph_theme_bridge: GraphThemeBridge) -> None:
            super().__init__()
            self._theme_bridge = theme_bridge
            self._graph_theme_bridge = graph_theme_bridge

        @pyqtProperty(QObject, constant=True)
        def themeBridge(self):  # noqa: N802
            return self._theme_bridge

        @pyqtProperty(QObject, constant=True)
        def graphThemeBridge(self):  # noqa: N802
            return self._graph_theme_bridge

        @pyqtProperty(QObject, constant=True)
        def addonManagerBridge(self):  # noqa: N802
            return None

    def variant(value):
        return value.toVariant() if hasattr(value, "toVariant") else value

    def walk_items(item):
        if isinstance(item, QQuickItem):
            yield item
            for child in item.childItems():
                yield from walk_items(child)

    def named_items(root, object_name: str):
        return [item for item in walk_items(root) if item.objectName() == object_name]

    def named_item(root, object_name: str, property_key: str | None = None):
        matches = [
            item
            for item in named_items(root, object_name)
            if property_key is None or str(item.property("propertyKey")) == property_key
        ]
        visible_matches = [item for item in matches if item.isVisible()]
        if visible_matches:
            assert len(visible_matches) == 1, (
                object_name,
                property_key,
                len(visible_matches),
            )
            return visible_matches[0]
        if matches:
            assert len(matches) == 1, (object_name, property_key, len(matches))
            return matches[0]
        raise AssertionError(
            f"missing {object_name!r} propertyKey={property_key!r}"
        )

    def item_point(item):
        point = item.mapToScene(QPointF(item.width() * 0.5, item.height() * 0.5))
        return QPoint(round(point.x()), round(point.y()))

    def settle(cycles: int = 4, wait_ms: int = 0) -> None:
        for _ in range(cycles):
            app.processEvents()
        if wait_ms:
            QTest.qWait(wait_ms)
            app.processEvents()

    def type_text(window: QQuickWindow, value: str) -> None:
        for character in value:
            if character == "\n":
                QTest.keyClick(window, Qt.Key.Key_Return)
            elif character == " ":
                QTest.keyClick(window, Qt.Key.Key_Space)
            elif character.isascii() and character.isalnum():
                modifier = (
                    Qt.KeyboardModifier.ShiftModifier
                    if character.isalpha() and character.isupper()
                    else Qt.KeyboardModifier.NoModifier
                )
                QTest.keyClick(window, Qt.Key(ord(character.upper())), modifier)
            else:
                raise AssertionError(f"unsupported test character {character!r}")

    def create_component(engine: QQmlEngine, path: Path, properties: dict[str, object]):
        component = QQmlComponent(engine, QUrl.fromLocalFile(str(path)))
        assert component.status() == QQmlComponent.Status.Ready, "\n".join(
            error.toString() for error in component.errors()
        )
        result = component.createWithInitialProperties(properties)
        assert result is not None, "\n".join(error.toString() for error in component.errors())
        settle()
        return result

    def render_icon_sheet(
        theme_name: str,
        foreground: QColor,
        background: QColor,
    ) -> Path:
        sizes = (16, 24, 32)
        cell_width = 74
        row_height = 48
        sheet = QImage(cell_width * len(sizes), row_height * len(NODE_IDS), QImage.Format.Format_ARGB32)
        sheet.fill(background)
        painter = QPainter(sheet)
        for row, type_id in enumerate(NODE_IDS):
            icon_path = repo_root / "ea_node_editor" / "assets" / "node_title_icons" / {
                "mechanical.open_model": "mechanical/open.svg",
                "mechanical.search_tree": "mechanical/search.svg",
                "mechanical.fea_table": "mechanical/table.svg",
                "mechanical.camera_views": "mechanical/views.svg",
                "mechanical.export_image": "mechanical/image.svg",
                "mechanical.run_script": "mechanical/script.svg",
                "mechanical.apdl_snippet": "mechanical/snippet.svg",
                "mechanical.save_model": "mechanical/save.svg",
            }[type_id]
            renderer = QSvgRenderer(str(icon_path))
            assert renderer.isValid(), icon_path
            for column, size in enumerate(sizes):
                icon = QImage(size, size, QImage.Format.Format_ARGB32)
                icon.fill(Qt.GlobalColor.transparent)
                icon_painter = QPainter(icon)
                renderer.render(icon_painter, QRectF(0, 0, size, size))
                icon_painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
                icon_painter.fillRect(icon.rect(), foreground)
                icon_painter.end()
                opaque = sum(
                    icon.pixelColor(x, y).alpha() > 16
                    for x in range(size)
                    for y in range(size)
                )
                assert opaque >= max(8, size), (type_id, size, opaque)
                x = column * cell_width + (cell_width - size) // 2
                y = row * row_height + (row_height - size) // 2
                painter.drawImage(x, y, icon)
        painter.end()
        output = evidence_root / f"mechanical_icons_{theme_name}_scale{scale_label}.png"
        assert sheet.save(str(output))
        return output

    diagnostics: dict[str, object] = {
        "platform": app.platformName(),
        "requested_scale": scale_label,
        "qt_scale_factor": os.environ.get("QT_SCALE_FACTOR", ""),
        "qsg_rhi_backend": os.environ.get("QSG_RHI_BACKEND", ""),
        "display_attached": display_attached,
        "captures": [],
        "cohorts": [],
    }

    backend_calls: list[str] = []
    resolved_sheet_palettes: dict[str, tuple[QColor, QColor]] = {}

    def forbidden_backend(*_args, **_kwargs):
        backend_calls.append("unexpected")
        raise AssertionError("UI editing invoked a Mechanical backend")

    for name in (
        "execute_open_model",
        "execute_search_tree",
        "execute_fea_table",
        "execute_camera_views",
        "execute_image_export",
        "execute_run_script",
        "execute_apdl_snippet",
        "execute_save_model",
    ):
        setattr(mechanical_runtime, name, forbidden_backend)

    theme_names = (
        ("light",)
        if light_sheets_only
        else ("dark",)
        if defaults_only
        else ("dark", "light")
    )
    font_sizes = (16,) if light_sheets_only else (10,) if defaults_only else (10, 16)
    for theme_name in theme_names:
        for font_size in font_sizes:
            icon_size = 16 if font_size == 10 else 24
            engine = QQmlEngine()
            engine.addImageProvider(
                LOCAL_MEDIA_PREVIEW_PROVIDER_ID,
                LocalMediaPreviewImageProvider(),
            )
            typography = TypographyHost(font_size, icon_size)
            theme_id = f"stitch_{theme_name}"
            theme_bridge = ThemeBridge(theme_id=theme_id)
            graph_theme_bridge = GraphThemeBridge(typography, theme_id=theme_id)
            shell_context = ShellContext(theme_bridge, graph_theme_bridge)
            engine.rootContext().setContextProperty("themeBridge", theme_bridge)
            engine.rootContext().setContextProperty("graphThemeBridge", graph_theme_bridge)
            engine.rootContext().setContextProperty("shellContext", shell_context)

            registry = build_default_registry(
                include_public_plugins=False,
                addon_runtime_config=(("mechanical.corex", True),),
                generation_root=evidence_root
                / "generations"
                / f"{theme_name}_{font_size}_{scale_label}",
            )
            model = GraphModel()
            scene = GraphSceneBridge()
            scene.bind_graph_theme_bridge(graph_theme_bridge)
            scene.bind_graphics_preferences_source(typography)
            scene.set_workspace(model, registry, model.active_workspace.workspace_id)
            view = ViewportBridge()
            window_width, window_height = 1100, 900
            view.set_viewport_size(float(window_width), float(window_height))
            state = GraphCanvasStateBridge(
                scene_bridge=scene,
                view_bridge=view,
                app_preferences_source=typography,
                graphics_source=typography,
            )
            commands = GraphCanvasCommandBridge(
                scene_bridge=scene,
                view_bridge=view,
                app_preferences_source=typography,
            )

            node_ids: dict[str, str] = {}
            for index, type_id in enumerate(NODE_IDS):
                node_ids[type_id] = scene.add_node_from_type(
                    type_id,
                    float(index * 1600),
                    0.0,
                )
            scene.set_node_property(node_ids["mechanical.open_model"], "file", "fixture.mechdb")
            scene.set_node_property(node_ids["mechanical.fea_table"], "family", "model_definition")
            scene.set_node_property(node_ids["mechanical.save_model"], "file", "result.mechdb")
            source_a = scene.add_node_from_type("data.boolean_toggle", 1180.0, -80.0)
            source_b = scene.add_node_from_type("data.boolean_toggle", 1180.0, 180.0)
            open_id = node_ids["mechanical.open_model"]
            search_id = node_ids["mechanical.search_tree"]
            for type_id in NODE_IDS[1:]:
                model_port = (
                    "source_model"
                    if type_id
                    in {
                        "mechanical.run_script",
                        "mechanical.apdl_snippet",
                        "mechanical.save_model",
                    }
                    else "model"
                )
                assert scene.add_edge(
                    open_id,
                    "model",
                    node_ids[type_id],
                    model_port,
                )
            assert scene.add_edge(
                search_id,
                "objects",
                node_ids["mechanical.fea_table"],
                "source",
            )
            edge_a = scene.add_edge(source_a, "boolean", search_id, "case_sensitive")
            edge_b = scene.add_edge(source_b, "boolean", search_id, "invert")
            assert edge_a and edge_b

            canvas = create_component(
                engine,
                repo_root / "ea_node_editor" / "ui_qml" / "components" / "GraphCanvas.qml",
                {
                    "canvasStateBridge": state,
                    "canvasCommandBridge": commands,
                    "width": float(window_width),
                    "height": float(window_height),
                },
            )
            window = QQuickWindow()
            window.resize(window_width, window_height)
            window.setColor(QColor(theme_bridge.palette["canvas_bg"]))
            canvas.setParentItem(window.contentItem())
            window.show()
            settle(8, 80)
            assert window.isVisible()
            assert window.screen() is not None

            def node_payload(node_id: str):
                return next(
                    payload
                    for payload in scene.nodes_model
                    if payload["node_id"] == node_id
                )

            def center_node(node_id: str):
                payload = node_payload(node_id)
                view.set_view_state(
                    1.0,
                    float(payload["x"]) + float(payload["width"]) * 0.5,
                    float(payload["y"]) + float(payload["height"]) * 0.5,
                )
                settle(5, 20)

            def node_host(node_id: str):
                center_node(node_id)
                return next(
                    item
                    for item in named_items(canvas, "graphNodeCard")
                    if variant(item.property("nodeData"))["node_id"] == node_id
                )

            if light_sheets_only:
                production_host = node_host(open_id)
                production_icon = named_item(
                    production_host,
                    "graphNodeTitleIcon",
                )
                assert production_icon.property("visible")
                assert production_icon.property("themeAware")
                foreground = QColor(production_icon.property("themeAwareColor"))
                background = QColor(production_host.property("surfaceColor"))
                assert foreground.isValid() and background.isValid()
                icon_sheet = render_icon_sheet(
                    theme_name,
                    foreground,
                    background,
                )

                def linear_channel(value: int) -> float:
                    normalized = value / 255.0
                    return (
                        normalized / 12.92
                        if normalized <= 0.04045
                        else ((normalized + 0.055) / 1.055) ** 2.4
                    )

                def luminance(color: QColor) -> float:
                    return (
                        0.2126 * linear_channel(color.red())
                        + 0.7152 * linear_channel(color.green())
                        + 0.0722 * linear_channel(color.blue())
                    )

                lighter, darker = sorted(
                    (luminance(foreground), luminance(background)),
                    reverse=True,
                )
                palette_evidence = {
                    "source_node": "mechanical.open_model",
                    "theme": theme_name,
                    "foreground_hex": foreground.name(QColor.NameFormat.HexArgb),
                    "foreground_rgba": list(foreground.getRgb()),
                    "background_hex": background.name(QColor.NameFormat.HexArgb),
                    "background_rgba": list(background.getRgb()),
                    "contrast_ratio": (lighter + 0.05) / (darker + 0.05),
                    "sizes": [16, 24, 32],
                    "sheet": icon_sheet.name,
                    "window_device_pixel_ratio": window.devicePixelRatio(),
                    "screen_device_pixel_ratio": window.screen().devicePixelRatio(),
                    "graphics_api": getattr(
                        window.rendererInterface().graphicsApi(),
                        "name",
                        str(window.rendererInterface().graphicsApi()),
                    ),
                }
                (
                    evidence_root
                    / f"light_icon_sheet_palette_scale{scale_label}.json"
                ).write_text(
                    json.dumps(palette_evidence, indent=2, sort_keys=True),
                    encoding="utf-8",
                )
                window.close()
                canvas.setParentItem(None)
                canvas.deleteLater()
                window.deleteLater()
                scene.deleteLater()
                engine.deleteLater()
                settle(6, 30)
                return

            def group_toggle(node_id: str, group_id: str) -> None:
                host = node_host(node_id)
                header = next(
                    item
                    for item in named_items(host, "graphNodeSettingsGroupHeader")
                    if str(item.property("groupId")) == group_id
                )
                toggles = [
                    item
                    for item in walk_items(header)
                    if item.objectName() == "graphNodeSettingsGroupToggleArea"
                    and item.isVisible()
                ]
                assert len(toggles) == 1, (node_id, group_id, len(toggles))
                point = item_point(toggles[0])
                assert 0 <= point.x() < window.width() and 0 <= point.y() < window.height(), (
                    node_id,
                    group_id,
                    point.x(),
                    point.y(),
                    window.width(),
                    window.height(),
                )
                QTest.mouseMove(window, point)
                settle(2, 10)
                QTest.mouseClick(
                    window,
                    Qt.MouseButton.LeftButton,
                    Qt.KeyboardModifier.NoModifier,
                    point,
                )
                settle(6, 180)

            fresh_default_states = {
                type_id: list(
                    model.active_workspace.nodes[node_id].expanded_settings_group_ids
                )
                for type_id, node_id in node_ids.items()
            }
            if defaults_only:
                center_node(node_ids["mechanical.open_model"])
                default_capture = window.grabWindow()
                assert not default_capture.isNull()
                default_capture_path = (
                    evidence_root / "fresh_defaults_display_attached.png"
                )
                assert default_capture.save(str(default_capture_path))

            full_interactions = defaults_only or (
                theme_name == "dark" and font_size == 10
            )
            edge_ids_before = tuple(model.active_workspace.edges)
            for type_id in NODE_IDS:
                spec = registry.get_spec(type_id)
                node_id = node_ids[type_id]
                node = model.active_workspace.nodes[node_id]
                assert node.expanded_settings_group_ids == (
                    spec.default_expanded_settings_group_ids
                )
                host = node_host(node_id)
                for group in spec.settings_groups:
                    default_expanded = (
                        group.group_id
                        in spec.default_expanded_settings_group_ids
                    )
                    if default_expanded:
                        assert group.group_id in node.expanded_settings_group_ids
                        if full_interactions:
                            group_toggle(node_id, group.group_id)
                            assert (
                                group.group_id
                                not in node.expanded_settings_group_ids
                            )
                    if not default_expanded or full_interactions:
                        host = node_host(node_id)
                        aggregate = next(
                            item
                            for item in named_items(
                                host,
                                "graphNodeSettingsGroupAggregateSocket",
                            )
                            if str(item.property("groupId")) == group.group_id
                        )
                        assert aggregate.property("visible")
                        if (
                            type_id == "mechanical.search_tree"
                            and group.group_id == "match_options"
                        ):
                            assert int(aggregate.property("connectedCount")) == 2
                        group_toggle(node_id, group.group_id)
                        assert group.group_id in node.expanded_settings_group_ids
                    if full_interactions and not default_expanded:
                        group_toggle(node_id, group.group_id)
                        assert group.group_id not in node.expanded_settings_group_ids
                        group_toggle(node_id, group.group_id)
                        assert group.group_id in node.expanded_settings_group_ids
                    host = node_host(node_id)
                assert tuple(model.active_workspace.edges) == edge_ids_before

            if defaults_only:
                graphics_api = window.rendererInterface().graphicsApi()
                default_diagnostics = {
                    "platform": app.platformName(),
                    "window_device_pixel_ratio": window.devicePixelRatio(),
                    "screen_device_pixel_ratio": window.screen().devicePixelRatio(),
                    "graphics_api": getattr(
                        graphics_api,
                        "name",
                        str(graphics_api),
                    ),
                    "fresh_default_states": fresh_default_states,
                    "physical_default_collapse_restore": True,
                    "edge_ids_before_and_after": list(edge_ids_before),
                    "capture": default_capture_path.name,
                }
                (evidence_root / "fresh_default_state_diagnostics.json").write_text(
                    json.dumps(default_diagnostics, indent=2, sort_keys=True),
                    encoding="utf-8",
                )
                window.close()
                canvas.setParentItem(None)
                canvas.deleteLater()
                window.deleteLater()
                scene.deleteLater()
                engine.deleteLater()
                settle(6, 30)
                return

            search_host = node_host(search_id)
            case_editor = named_item(
                search_host,
                "graphNodeInlineToggleEditor",
                "case_sensitive",
            )
            invert_editor = named_item(
                search_host,
                "graphNodeInlineToggleEditor",
                "invert",
            )
            assert not case_editor.property("enabled")
            assert not invert_editor.property("enabled")
            case_dot = named_item(search_host, "graphNodeInputPortDot", "case_sensitive")
            invert_dot = named_item(search_host, "graphNodeInputPortDot", "invert")
            assert case_dot.property("visible") and invert_dot.property("visible")
            assert abs(item_point(case_dot).y() - item_point(invert_dot).y()) > 4

            open_system = named_item(
                node_host(node_ids["mechanical.open_model"]),
                "graphNodeInlineValueEditor",
                "system",
            )
            assert not open_system.property("enabled"), (
                theme_name,
                font_size,
                model.active_workspace.nodes[node_ids["mechanical.open_model"]].properties,
                variant(open_system.parentItem().property("propertyData")),
            )
            assert not named_item(
                node_host(node_ids["mechanical.fea_table"]),
                "graphNodeInlineListEditor",
                "sets",
            ).property("editorEnabled")
            assert not named_item(
                node_host(node_ids["mechanical.apdl_snippet"]),
                "graphNodeInlineListEditor",
                "selected_steps",
            ).property("editorEnabled")
            save_host = node_host(node_ids["mechanical.save_model"])
            archive_editors = [
                named_item(save_host, "graphNodeInlineToggleEditor", key)
                for key in (
                    "include_results",
                    "include_user_files",
                    "include_external_imported_files",
                )
            ]
            assert all(not item.property("enabled") for item in archive_editors)

            if full_interactions:
                open_host = node_host(open_id)
                mode = named_item(open_host, "graphNodeInlineEnumEditor", "mode")
                QTest.mouseClick(window, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, item_point(mode))
                QTest.keyClick(window, Qt.Key.Key_Down)
                QTest.keyClick(window, Qt.Key.Key_Enter)
                settle(6, 30)
                assert model.active_workspace.nodes[open_id].properties["mode"] == "interactive"

                image_id = node_ids["mechanical.export_image"]
                image_host = node_host(image_id)
                objects = named_item(image_host, "graphNodeInlineListEditor", "objects")
                add_button = named_item(objects, "graphSurfaceListAddButton")
                QTest.mouseClick(window, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, item_point(add_button))
                settle(6, 30)
                assert model.active_workspace.nodes[image_id].properties["objects"] == [""]

                script_id = node_ids["mechanical.run_script"]
                script_node = model.active_workspace.nodes[script_id]
                script_host = node_host(script_id)
                code = named_item(script_host, "graphNodeInlineTextareaEditor", "code")
                original_position = (script_node.x, script_node.y)
                start = item_point(code)
                QTest.mousePress(window, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, start)
                QTest.mouseMove(window, start + QPoint(36, 14), delay=20)
                QTest.mouseRelease(window, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, start + QPoint(36, 14))
                settle(3)
                assert (script_node.x, script_node.y) == original_position
                code_point = item_point(code)
                assert 0 <= code_point.x() < window.width() and 0 <= code_point.y() < window.height(), code_point
                QTest.mouseMove(window, code_point)
                QTest.mouseClick(window, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, code_point)
                settle(4, 30)
                assert code.property("activeFocus"), (
                    code_point,
                    code.property("visible"),
                    code.property("enabled"),
                )
                type_text(window, "T16\nanalysis")
                assert "t16\nanalysis" in str(code.property("text")), repr(
                    code.property("text")
                )
                scope_editor = named_item(
                    script_host,
                    "graphNodeInlineEnumEditor",
                    "scope",
                )
                QTest.mouseClick(
                    window,
                    Qt.MouseButton.LeftButton,
                    Qt.KeyboardModifier.NoModifier,
                    item_point(scope_editor),
                )
                settle(6, 40)
                assert "t16\nanalysis" in script_node.properties["code"], repr(
                    script_node.properties["code"]
                )
                group_toggle(script_id, "script")
                group_toggle(script_id, "script")
                assert "t16\nanalysis" in script_node.properties["code"]

                query = named_item(
                    node_host(search_id),
                    "graphNodeInlineSearchableEnumEditor",
                    "query",
                )
                search_node = model.active_workspace.nodes[search_id]
                query_position = (search_node.x, search_node.y)
                QTest.mouseClick(window, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, item_point(query))
                type_text(window, "NoBackend")
                QTest.keyClick(window, Qt.Key.Key_Return)
                settle(8, 40)
                assert search_node.properties["query"] == "nobackend", repr(
                    search_node.properties["query"]
                )
                assert (search_node.x, search_node.y) == query_position
                group_toggle(search_id, "search")
                group_toggle(search_id, "search")
                query = named_item(
                    node_host(search_id),
                    "graphNodeInlineSearchableEnumEditor",
                    "query",
                )
                assert str(query.property("editText")) == "nobackend"
                assert backend_calls == []

            scene.clear_selection()
            settle(4, 30)
            for type_id in NODE_IDS:
                spec = registry.get_spec(type_id)
                node_id = node_ids[type_id]
                host = node_host(node_id)
                shared_typography = host.findChild(QObject, "graphSharedTypography")
                title_item = named_item(host, "graphNodeTitle")
                inline_labels = [
                    item
                    for item in named_items(host, "graphNodeInlinePropertyLabel")
                    if item.isVisible()
                ]
                assert shared_typography is not None
                assert int(host.property("effectiveGraphLabelPixelSize")) == font_size
                assert int(shared_typography.property("graphLabelPixelSize")) == font_size
                assert int(shared_typography.property("inlinePropertyPixelSize")) == font_size
                assert title_item.property("font").pixelSize() == font_size + 2
                assert all(
                    item.property("font").pixelSize() == font_size
                    for item in inline_labels
                )
                assert abs(float(view.zoom_value) - 1.0) < 1e-9
                assert abs(float(canvas.scale()) - 1.0) < 1e-9
                assert abs(float(host.scale()) - 1.0) < 1e-9
                title_icon = named_item(host, "graphNodeTitleIcon")
                assert title_icon.property("visible")
                assert title_icon.property("themeAware")
                assert 0 < int(round(float(title_icon.width()))) <= icon_size
                if type_id == "mechanical.open_model":
                    resolved_sheet_palettes[theme_name] = (
                        QColor(title_icon.property("themeAwareColor")),
                        QColor(host.property("surfaceColor")),
                    )
                for port in spec.ports:
                    if port.direction == "in":
                        dot = named_item(host, "graphNodeInputPortDot", port.key)
                        assert dot.property("visible"), (type_id, port.key)
                for object_name in (
                    "graphNodeTitle",
                    "graphNodeSettingsGroupLabel",
                    "graphNodeInlinePropertyLabel",
                    "graphNodeInputPortLabel",
                    "graphNodeOutputPortLabel",
                ):
                    for item in named_items(host, object_name):
                        if item.property("visible") and item.property("truncated") is not None:
                            assert not item.property("truncated"), (
                                type_id,
                                object_name,
                                item.property("text"),
                            )
                image = window.grabWindow()
                for _attempt in range(3):
                    if not image.isNull():
                        break
                    settle(4, 80)
                    image = window.grabWindow()
                assert not image.isNull(), (type_id, theme_name, font_size)
                output = evidence_root / (
                    f"mechanical_{type_id.rsplit('.', 1)[-1]}_{theme_name}_"
                    f"font{font_size}_scale{scale_label}_expanded.png"
                )
                assert image.save(str(output)), output
                diagnostics["captures"].append(
                    {
                        "file": output.name,
                        "width": image.width(),
                        "height": image.height(),
                        "device_pixel_ratio": image.devicePixelRatio(),
                        "requested_graph_font": font_size,
                        "host_effective_graph_font": int(
                            host.property("effectiveGraphLabelPixelSize")
                        ),
                        "qml_title_font": title_item.property("font").pixelSize(),
                        "qml_inline_fonts": sorted(
                            {
                                item.property("font").pixelSize()
                                for item in inline_labels
                            }
                        ),
                        "graph_zoom": float(view.zoom_value),
                        "canvas_scale": float(canvas.scale()),
                        "host_scale": float(host.scale()),
                        "host_logical_size": [float(host.width()), float(host.height())],
                    }
                )

            graphics_api = window.rendererInterface().graphicsApi()
            diagnostics["cohorts"].append(
                {
                    "theme": theme_name,
                    "font_size": font_size,
                    "icon_size": icon_size,
                    "window_device_pixel_ratio": window.devicePixelRatio(),
                    "screen_device_pixel_ratio": window.screen().devicePixelRatio(),
                    "screen_name": window.screen().name(),
                    "graphics_api": getattr(graphics_api, "name", str(graphics_api)),
                    "edge_ids": list(edge_ids_before),
                }
            )
            window.close()
            canvas.setParentItem(None)
            canvas.deleteLater()
            window.deleteLater()
            scene.deleteLater()
            engine.deleteLater()
            settle(6, 30)

        foreground, background = resolved_sheet_palettes[theme_name]
        icon_sheet = render_icon_sheet(theme_name, foreground, background)
        diagnostics["captures"].append({"file": icon_sheet.name, "kind": "icon_16_24_32"})

    assert backend_calls == []
    expected_node_captures = len(NODE_IDS) * 2 * 2
    assert len([item for item in diagnostics["captures"] if "font" in item["file"]]) == expected_node_captures
    diagnostics_path = evidence_root / f"display_diagnostics_scale{scale_label}.json"
    diagnostics_path.write_text(
        json.dumps(diagnostics, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence-root", type=Path, required=True)
    parser.add_argument("--scale-label", choices=("100", "150"), required=True)
    parser.add_argument("--display-attached", action="store_true")
    parser.add_argument("--defaults-only", action="store_true")
    parser.add_argument("--light-sheets-only", action="store_true")
    args = parser.parse_args(argv)
    _run_visual_cohort(
        args.evidence_root,
        args.scale_label,
        display_attached=args.display_attached,
        defaults_only=args.defaults_only,
        light_sheets_only=args.light_sheets_only,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1:]))


if __name__ != "__main__":
    from tests.graph_surface.environment import GraphSurfaceInputContractTestBase

    class MechanicalCatalogueVisualTests(GraphSurfaceInputContractTestBase):
        def test_registered_mechanical_group_clicks_through_real_canvas_bridge(self) -> None:
            self._run_qml_probe(
                "mechanical-registered-group-click",
                r'''
                from ea_node_editor.graph.model import GraphModel
                from ea_node_editor.nodes.bootstrap import build_default_registry
                from ea_node_editor.ui_qml.graph_scene_bridge import GraphSceneBridge
                from ea_node_editor.ui_qml.viewport_bridge import ViewportBridge

                generation_root = repo_root / "artifacts" / "verification_logs" / "mechanical_catalogue" / "T16" / "generations_offscreen"
                registry = build_default_registry(
                    include_public_plugins=False,
                    addon_runtime_config=(("mechanical.corex", True),),
                    generation_root=generation_root,
                )
                model = GraphModel()
                scene = GraphSceneBridge()
                scene.set_workspace(model, registry, model.active_workspace.workspace_id)
                view = ViewportBridge()
                view.set_viewport_size(980.0, 680.0)
                state, commands = build_canvas_bridges(scene_bridge=scene, view_bridge=view)
                node_id = scene.add_node_from_type("mechanical.open_model", -160.0, -120.0)
                scene.set_node_property(node_id, "file", "fixture.mechdb")
                canvas = create_component(graph_canvas_qml_path, {
                    "canvasStateBridge": state,
                    "canvasCommandBridge": commands,
                    "width": 980.0,
                    "height": 680.0,
                })
                window = attach_host_to_window(canvas, 980, 680)
                settle_events(8)
                node = model.active_workspace.nodes[node_id]
                assert node.expanded_settings_group_ids == ("open_options",)
                fresh_payload = next(
                    item for item in scene.nodes_model if item["node_id"] == node_id
                )
                assert [
                    (group["group_id"], group["expanded"])
                    for group in fresh_payload["settings_groups"]
                ] == [("open_options", True), ("session_options", False)]

                def host():
                    hosts = [
                        item for item in named_child_items(canvas, "graphNodeCard")
                        if variant_value(item.property("nodeData"))["node_id"] == node_id
                    ]
                    assert len(hosts) == 1, (node_id, len(hosts), list(scene.nodes_model))
                    return hosts[0]

                def primary_header():
                    toggles = [
                        item for item in named_child_items(host(), "graphNodeSettingsGroupHeader")
                        if str(item.property("groupId")) == "open_options"
                    ]
                    assert len(toggles) == 1
                    return toggles[0]

                mouse_click(window, item_scene_point(primary_header()))
                settle_events(8)
                assert node.expanded_settings_group_ids == ()
                aggregate = next(
                    item
                    for item in named_child_items(
                        host(),
                        "graphNodeSettingsGroupAggregateSocket",
                    )
                    if str(item.property("groupId")) == "open_options"
                )
                assert aggregate.property("visible")
                mouse_click(window, item_scene_point(primary_header()))
                settle_events(8)
                assert node.expanded_settings_group_ids == ("open_options",)
                system_editors = [
                    item
                    for item in named_child_items(host(), "graphNodeInlineValueEditor")
                    if str(item.property("propertyKey")) == "system" and item.isVisible()
                ]
                assert len(system_editors) == 1
                assert not system_editors[0].property("enabled")
                title_icon = named_item(host(), "graphNodeTitleIcon")
                assert title_icon.property("visible")
                assert title_icon.property("themeAware")
                window.close()
                canvas.deleteLater()
                engine.deleteLater()
                app.processEvents()
                ''',
            )

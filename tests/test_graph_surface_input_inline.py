from __future__ import annotations

import unittest
from pathlib import Path

from tests.graph_surface_pointer_regression import (
    QML_POINTER_REGRESSION_HELPERS,
    run_qml_probe,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


class GraphSurfaceInputInlineTests(unittest.TestCase):
    def _run_qml_probe(self, label: str, body: str) -> None:
        run_qml_probe(
            self,
            label,
            """
            from pathlib import Path
            import textwrap

            from PyQt6.QtCore import QEvent, QObject, Qt, QUrl, pyqtProperty
            from PyQt6.QtGui import QKeyEvent
            from PyQt6.QtQml import QQmlComponent, QQmlEngine
            from PyQt6.QtWidgets import QApplication

            from ea_node_editor.ui.media_preview_provider import (
                LOCAL_MEDIA_PREVIEW_PROVIDER_ID,
                LocalMediaPreviewImageProvider,
            )

            class ThemeBridgeStub(QObject):
                @pyqtProperty("QVariantMap", constant=True)
                def palette(self):
                    return {
                        "accent": "#2F89FF",
                        "border": "#3a4355",
                        "canvas_bg": "#151821",
                        "canvas_major_grid": "#2f3644",
                        "canvas_minor_grid": "#222833",
                        "group_title_fg": "#d5dbea",
                        "hover": "#33405c",
                        "muted_fg": "#95a0b8",
                        "panel_bg": "#1b1f2a",
                        "panel_title_fg": "#eef3ff",
                        "pressed": "#22304a",
                        "toolbar_bg": "#202635",
                    }

            class GraphThemeBridgeStub(QObject):
                @pyqtProperty("QVariantMap", constant=True)
                def node_palette(self):
                    return {
                        "card_bg": "#1f2431",
                        "card_border": "#414a5d",
                        "card_selected_border": "#5da9ff",
                        "header_bg": "#252c3c",
                        "header_fg": "#eef3ff",
                        "inline_driven_fg": "#aeb8ce",
                        "inline_input_bg": "#18202d",
                        "inline_input_border": "#465066",
                        "inline_input_fg": "#eef3ff",
                        "inline_label_fg": "#d5dbea",
                        "inline_row_bg": "#202635",
                        "inline_row_border": "#3a4355",
                        "port_interactive_border": "#8ca0c7",
                        "port_interactive_fill": "#101521",
                        "port_interactive_ring_border": "#7fb2ff",
                        "port_interactive_ring_fill": "#1a2233",
                        "port_label_fg": "#d5dbea",
                        "scope_badge_bg": "#1f3657",
                        "scope_badge_border": "#4c7bc0",
                        "scope_badge_fg": "#eef3ff",
                    }

                @pyqtProperty("QVariantMap", constant=True)
                def port_kind_palette(self):
                    return {
                        "data": "#7AA8FF",
                        "flow": "#67D487",
                    }

                @pyqtProperty("QVariantMap", constant=True)
                def edge_palette(self):
                    return {
                        "invalid_drag_stroke": "#D94F4F",
                        "preview_stroke": "#95a0b8",
                        "selected_stroke": "#5da9ff",
                        "valid_drag_stroke": "#67D487",
                    }

            app = QApplication.instance() or QApplication([])
            engine = QQmlEngine()
            engine.addImageProvider(LOCAL_MEDIA_PREVIEW_PROVIDER_ID, LocalMediaPreviewImageProvider())
            engine.rootContext().setContextProperty("themeBridge", ThemeBridgeStub())
            engine.rootContext().setContextProperty("graphThemeBridge", GraphThemeBridgeStub())

            repo_root = Path.cwd()
            components_dir = repo_root / "ea_node_editor" / "ui_qml" / "components"
            graph_node_host_qml_path = components_dir / "graph" / "GraphNodeHost.qml"

            def create_component(path, initial_properties):
                component = QQmlComponent(engine, QUrl.fromLocalFile(str(path)))
                if component.status() != QQmlComponent.Status.Ready:
                    errors = "\\n".join(error.toString() for error in component.errors())
                    raise AssertionError(f"Failed to load {path.name}:\\n{errors}")
                if hasattr(component, "createWithInitialProperties"):
                    obj = component.createWithInitialProperties(initial_properties)
                else:
                    obj = component.create()
                    for key, value in initial_properties.items():
                        obj.setProperty(key, value)
                if obj is None:
                    errors = "\\n".join(error.toString() for error in component.errors())
                    raise AssertionError(f"Failed to instantiate {path.name}:\\n{errors}")
                app.processEvents()
                return obj

            probe_qml = textwrap.dedent(
                '''
                import QtQuick 2.15
                import QtQuick.Controls 2.15
                import "ea_node_editor/ui_qml/components/graph" as GraphComponents

                Item {
                    id: root
                    width: 480
                    height: 360

                    QtObject {
                        id: sceneBridgeProxy
                        objectName: "sceneBridgeProxy"
                        property var selected_node_lookup: ({
                            "node_inline_test": true
                        })
                    }

                    QtObject {
                        id: toolbarPrefs
                        objectName: "toolbarPrefs"
                        property bool nodeFloatingToolbarOpensOnHover: false
                        property string activeThemeId: ""
                    }

                    QtObject {
                        id: executionFactsProxy
                        objectName: "executionFactsProxy"
                        property var propertyPresentationLookup: ({})
                        property var failedNodeLookup: ({})
                        property var runningNodeLookup: ({})
                        property var completedNodeLookup: ({})
                        property var warningNodeLookup: ({})
                        property var freshRunNodeLookup: ({})
                        property var selectedRunPreviewNodeLookup: ({})
                        property var nodeDiagnosticLookup: ({})
                        property var runningNodeStartedAtMsLookup: ({})
                        property var nodeElapsedMsLookup: ({})
                        property var portFlowStateLookup: ({})
                        property int nodeExecutionRevision: 0
                        property string nodeElapsedTimeUnit: "seconds"
                    }

                    Item {
                        id: canvasProxy
                        objectName: "canvasProxy"
                        property var sceneBridge: sceneBridgeProxy
                        property var prefs: toolbarPrefs
                        property var executionFacts: executionFactsProxy
                        property Item activeToolbarHost: null
                        property string browseResultPath: ""
                        property string colorResult: ""
                        property var lastBrowseCall: ({})
                        property var lastColorPickCall: ({})

                        function browseNodePropertyPath(nodeId, key, currentPath) {
                            lastBrowseCall = {
                                "nodeId": String(nodeId || ""),
                                "key": String(key || ""),
                                "currentPath": String(currentPath || "")
                            };
                            return browseResultPath;
                        }

                        function pickNodePropertyColor(nodeId, key, currentValue) {
                            lastColorPickCall = {
                                "nodeId": String(nodeId || ""),
                                "key": String(key || ""),
                                "currentValue": String(currentValue || "")
                            };
                            return colorResult;
                        }
                    }

                    Item {
                        id: staleToolbarHost
                        objectName: "staleToolbarHost"
                    }

                    TextField {
                        id: focusSink
                        objectName: "probeFocusSink"
                        anchors.left: parent.left
                        anchors.top: parent.top
                        width: 1
                        height: 1
                        opacity: 0
                    }

                    function nodePayload() {
                        return {
                            "node_id": "node_inline_test",
                            "type_id": "core.logger",
                            "title": "Inline Probe",
                            "x": 96.0,
                            "y": 84.0,
                            "width": 236.0,
                            "height": 188.0,
                            "accent": "#2F89FF",
                            "collapsed": false,
                            "selected": false,
                            "runtime_behavior": "active",
                            "surface_family": "standard",
                            "surface_variant": "",
                            "surface_metrics": {
                                "default_width": 236.0,
                                "default_height": 188.0,
                                "min_width": 120.0,
                                "min_height": 50.0,
                                "collapsed_width": 130.0,
                                "collapsed_height": 36.0,
                                "header_height": 24.0,
                                "header_top_margin": 4.0,
                                "body_top": 30.0,
                                "body_height": 124.0,
                                "port_top": 154.0,
                                "port_height": 18.0,
                                "port_center_offset": 6.0,
                                "port_side_margin": 8.0,
                                "port_dot_radius": 3.5,
                                "resize_handle_size": 16.0,
                                "title_top": 4.0,
                                "title_height": 24.0,
                                "title_left_margin": 10.0,
                                "title_right_margin": 10.0,
                                "title_centered": false,
                                "body_left_margin": 8.0,
                                "body_right_margin": 8.0,
                                "body_bottom_margin": 8.0,
                                "use_host_chrome": true
                            },
                            "visual_style": {},
                            "can_enter_scope": false,
                            "ports": [],
                            "properties": {
                                "source_path": "/fixtures/original.txt",
                            },
                            "inline_properties": [
                                {
                                    "key": "source_path",
                                    "label": "Source",
                                    "inline_editor": "path",
                                    "value": "/fixtures/original.txt",
                                    "status_chip_text": "Stored",
                                    "status_chip_variant": "stored",
                                    "overridden_by_input": false,
                                    "input_port_label": "source_path"
                                },
                                {
                                    "key": "caption",
                                    "label": "Caption",
                                    "inline_editor": "textarea",
                                    "value": "Line one",
                                    "overridden_by_input": false,
                                    "input_port_label": "caption"
                                }
                            ]
                        };
                    }

                    GraphComponents.GraphNodeHost {
                        id: host
                        objectName: "probeHost"
                        nodeData: nodePayload()
                        canvasItem: canvasProxy
                    }
                }
                '''
            )
            component = QQmlComponent(engine)
            component.setData(probe_qml.encode("utf-8"), QUrl.fromLocalFile(str(repo_root) + "/"))
            if component.status() != QQmlComponent.Status.Ready:
                errors = "\\n".join(error.toString() for error in component.errors())
                raise AssertionError("Failed to load probe QML:\\n" + errors)
            probe = component.create()
            if probe is None:
                errors = "\\n".join(error.toString() for error in component.errors())
                raise AssertionError("Failed to instantiate probe QML:\\n" + errors)
            app.processEvents()
            """,
            QML_POINTER_REGRESSION_HELPERS,
            body,
        )

    def test_selected_host_reclaims_floating_toolbar_when_hovered(self) -> None:
        self._run_qml_probe(
            "selected-host-toolbar-hover-ownership",
            """
            host = probe.findChild(QObject, "probeHost")
            canvas_proxy = probe.findChild(QObject, "canvasProxy")
            stale_host = probe.findChild(QObject, "staleToolbarHost")

            assert host is not None
            assert canvas_proxy is not None
            assert stale_host is not None
            settle_events(3)

            assert bool(host.property("isSelected"))
            assert bool(host.property("toolbarActive"))
            active_host = canvas_proxy.property("activeToolbarHost")
            assert active_host is not None
            assert active_host.objectName() == "probeHost"

            canvas_proxy.setProperty("activeToolbarHost", stale_host)
            settle_events(1)
            assert canvas_proxy.property("activeToolbarHost").objectName() == "staleToolbarHost"

            window = attach_host_to_window(host, 520, 420)
            try:
                hover_host_local_point(window, host, 16, 16)
                assert bool(host.property("hoverActive"))
                active_host = canvas_proxy.property("activeToolbarHost")
                assert active_host is not None
                assert active_host.objectName() == "probeHost"
            finally:
                dispose_host_window(host, window)
                engine.deleteLater()
                app.processEvents()
            """,
        )

    def test_floating_toolbar_defaults_to_single_selection_and_allows_hover_opt_in(self) -> None:
        self._run_qml_probe(
            "selected-host-toolbar-hover-opt-in",
            """
            host = probe.findChild(QObject, "probeHost")
            canvas_proxy = probe.findChild(QObject, "canvasProxy")
            scene_bridge = probe.findChild(QObject, "sceneBridgeProxy")
            toolbar_prefs = probe.findChild(QObject, "toolbarPrefs")

            assert host is not None
            assert canvas_proxy is not None
            assert scene_bridge is not None
            assert toolbar_prefs is not None
            settle_events(3)

            assert bool(host.property("isSelected"))
            assert bool(host.property("isIndividuallySelected"))
            assert bool(host.property("toolbarActive"))
            assert not bool(host.property("nodeFloatingToolbarOpensOnHover"))

            scene_bridge.setProperty(
                "selected_node_lookup",
                {"node_inline_test": True, "node_second": True},
            )
            settle_events(2)
            assert bool(host.property("isSelected"))
            assert not bool(host.property("isIndividuallySelected"))
            QTest.qWait(160)
            app.processEvents()
            assert not bool(host.property("toolbarActive"))
            assert canvas_proxy.property("activeToolbarHost") is None

            scene_bridge.setProperty("selected_node_lookup", {})
            settle_events(2)

            window = attach_host_to_window(host, 520, 420)
            try:
                hover_host_local_point(window, host, 16, 16)
                assert bool(host.property("hoverActive"))
                assert not bool(host.property("toolbarActive"))

                toolbar_prefs.setProperty("nodeFloatingToolbarOpensOnHover", True)
                settle_events(2)
                assert bool(host.property("nodeFloatingToolbarOpensOnHover"))
                assert bool(host.property("toolbarActive"))
                active_host = canvas_proxy.property("activeToolbarHost")
                assert active_host is not None
                assert active_host.objectName() == "probeHost"
            finally:
                dispose_host_window(host, window)
                engine.deleteLater()
                app.processEvents()
            """,
        )

    def _run_group_backdrop_probe(self, label: str, body: str) -> None:
        run_qml_probe(
            self,
            label,
            """
            from pathlib import Path
            import textwrap

            from PyQt6.QtCore import QEvent, QObject, Qt, QUrl, pyqtProperty
            from PyQt6.QtGui import QKeyEvent
            from PyQt6.QtQml import QQmlComponent, QQmlEngine
            from PyQt6.QtWidgets import QApplication

            from ea_node_editor.ui.media_preview_provider import (
                LOCAL_MEDIA_PREVIEW_PROVIDER_ID,
                LocalMediaPreviewImageProvider,
            )
            from ea_node_editor.ui_qml.surface_contracts import surface_spec_payload_for_values

            class ThemeBridgeStub(QObject):
                @pyqtProperty("QVariantMap", constant=True)
                def palette(self):
                    return {
                        "accent": "#2F89FF",
                        "border": "#3a4355",
                        "canvas_bg": "#151821",
                        "canvas_major_grid": "#2f3644",
                        "canvas_minor_grid": "#222833",
                        "group_title_fg": "#d5dbea",
                        "hover": "#33405c",
                        "muted_fg": "#95a0b8",
                        "panel_bg": "#1b1f2a",
                        "panel_title_fg": "#eef3ff",
                        "pressed": "#22304a",
                        "toolbar_bg": "#202635",
                    }

            class GraphThemeBridgeStub(QObject):
                @pyqtProperty("QVariantMap", constant=True)
                def node_palette(self):
                    return {
                        "card_bg": "#1f2431",
                        "card_border": "#414a5d",
                        "card_selected_border": "#5da9ff",
                        "header_bg": "#252c3c",
                        "header_fg": "#eef3ff",
                        "inline_driven_fg": "#aeb8ce",
                        "inline_input_bg": "#18202d",
                        "inline_input_border": "#465066",
                        "inline_input_fg": "#eef3ff",
                        "inline_label_fg": "#d5dbea",
                        "inline_row_bg": "#202635",
                        "inline_row_border": "#3a4355",
                        "port_interactive_border": "#8ca0c7",
                        "port_interactive_fill": "#101521",
                        "port_interactive_ring_border": "#7fb2ff",
                        "port_interactive_ring_fill": "#1a2233",
                        "port_label_fg": "#d5dbea",
                        "scope_badge_bg": "#1f3657",
                        "scope_badge_border": "#4c7bc0",
                        "scope_badge_fg": "#eef3ff",
                    }

                @pyqtProperty("QVariantMap", constant=True)
                def port_kind_palette(self):
                    return {
                        "data": "#7AA8FF",
                        "flow": "#67D487",
                    }

                @pyqtProperty("QVariantMap", constant=True)
                def edge_palette(self):
                    return {
                        "invalid_drag_stroke": "#D94F4F",
                        "preview_stroke": "#95a0b8",
                        "selected_stroke": "#5da9ff",
                        "valid_drag_stroke": "#67D487",
                    }

            app = QApplication.instance() or QApplication([])
            engine = QQmlEngine()
            engine.addImageProvider(LOCAL_MEDIA_PREVIEW_PROVIDER_ID, LocalMediaPreviewImageProvider())
            engine.rootContext().setContextProperty("themeBridge", ThemeBridgeStub())
            engine.rootContext().setContextProperty("graphThemeBridge", GraphThemeBridgeStub())
            engine.rootContext().setContextProperty(
                "groupBackdropSurfaceSpec",
                surface_spec_payload_for_values(
                    type_id="passive.annotation.group_backdrop",
                    family="group_backdrop",
                    variant="group_backdrop",
                ),
            )

            repo_root = Path.cwd()

            probe_qml = textwrap.dedent(
                '''
                import QtQuick 2.15
                import QtQuick.Controls 2.15
                import "ea_node_editor/ui_qml/components/graph" as GraphComponents

                Item {
                    id: root
                    width: 520
                    height: 400

                    QtObject {
                        id: sceneBridgeProxy
                        property var selected_node_lookup: ({
                            "node_group_backdrop_inline_test": true
                        })
                    }

                    Item {
                        id: canvasProxy
                        objectName: "canvasProxy"
                        property var sceneBridge: sceneBridgeProxy

                        function browseNodePropertyPath(nodeId, key, currentPath) {
                            return currentPath;
                        }
                    }

                    TextField {
                        id: focusSink
                        objectName: "probeFocusSink"
                        anchors.left: parent.left
                        anchors.top: parent.top
                        width: 1
                        height: 1
                        opacity: 0
                    }

                    function nodePayload() {
                        return {
                            "node_id": "node_group_backdrop_inline_test",
                            "type_id": "passive.annotation.group_backdrop",
                            "title": "",
                            "x": 72.0,
                            "y": 64.0,
                            "width": 340.0,
                            "height": 260.0,
                            "accent": "#2F89FF",
                            "collapsed": false,
                            "selected": true,
                            "runtime_behavior": "passive",
                            "surface_family": "group_backdrop",
                            "surface_variant": "group_backdrop",
                            "surface_spec": groupBackdropSurfaceSpec,
                            "surface_metrics": {
                                "default_width": 320.0,
                                "default_height": 260.0,
                                "min_width": 220.0,
                                "min_height": 180.0,
                                "collapsed_width": 180.0,
                                "collapsed_height": 38.0,
                                "header_height": 32.0,
                                "header_top_margin": 8.0,
                                "body_top": 52.0,
                                "body_height": 190.0,
                                "port_top": 242.0,
                                "port_height": 0.0,
                                "port_center_offset": 0.0,
                                "port_side_margin": 0.0,
                                "port_dot_radius": 0.0,
                                "resize_handle_size": 16.0,
                                "title_top": 8.0,
                                "title_height": 24.0,
                                "title_left_margin": 12.0,
                                "title_right_margin": 12.0,
                                "title_centered": false,
                                "body_left_margin": 18.0,
                                "body_right_margin": 18.0,
                                "body_bottom_margin": 18.0,
                                "use_host_chrome": true
                            },
                            "visual_style": {},
                            "can_enter_scope": false,
                            "ports": [],
                            "properties": {"title": ""}
                        };
                    }

                    GraphComponents.GraphNodeHost {
                        id: host
                        objectName: "probeHost"
                        nodeData: nodePayload()
                        canvasItem: canvasProxy
                        surfaceVariantOverride: "group_backdrop_input_overlay"
                    }
                }
                '''
            )
            component = QQmlComponent(engine)
            component.setData(probe_qml.encode("utf-8"), QUrl.fromLocalFile(str(repo_root) + "/"))
            if component.status() != QQmlComponent.Status.Ready:
                errors = "\\n".join(error.toString() for error in component.errors())
                raise AssertionError("Failed to load probe QML:\\n" + errors)
            probe = component.create()
            if probe is None:
                errors = "\\n".join(error.toString() for error in component.errors())
                raise AssertionError("Failed to instantiate probe QML:\\n" + errors)
            app.processEvents()
            """,
            QML_POINTER_REGRESSION_HELPERS,
            body,
        )

    def test_inline_layer_publishes_control_scoped_rects_for_path_and_textarea_editors(self) -> None:
        self._run_qml_probe(
            "inline-rects",
            """
            host = probe.findChild(QObject, "probeHost")
            loader = host.findChild(QObject, "graphNodeSurfaceLoader")
            assert loader is not None

            embedded_rects = variant_list(loader.property("embeddedInteractiveRects"))
            assert len(embedded_rects) == 2, embedded_rects

            widths = [rect_field(rect, "width") for rect in embedded_rects]
            heights = [rect_field(rect, "height") for rect in embedded_rects]
            ys = [rect_field(rect, "y") for rect in embedded_rects]

            assert widths[0] > 60.0, (widths, heights, ys, embedded_rects)
            assert heights[0] >= 18.0, (widths, heights, ys, embedded_rects)
            assert widths[1] > 120.0, (widths, heights, ys, embedded_rects)
            assert heights[1] > 90.0, (widths, heights, ys, embedded_rects)
            assert ys[0] < ys[1], (widths, heights, ys, embedded_rects)
            """,
        )

    def test_graph_typography_inline_edge_inline_labels_and_status_chips_follow_shared_roles(self) -> None:
        self._run_qml_probe(
            "inline-typography",
            """
            host = probe.findChild(QObject, "probeHost")
            typography = host.findChild(QObject, "graphSharedTypography")
            loader = host.findChild(QObject, "graphNodeSurfaceLoader")
            source_label = named_item(probe, "graphNodeInlinePropertyLabel", "source_path")
            status_chip_label = named_item(probe, "graphNodeInlineStatusChipLabel", "source_path")
            path_field = named_item(probe, "graphNodeInlinePathEditor", "source_path")
            textarea = named_item(probe, "graphNodeInlineTextareaEditor", "caption")

            assert typography is not None
            assert loader is not None
            assert float(host.property("_inlineRowHeight")) == float(typography.property("inlineRowHeight"))
            assert float(host.property("_inlineTextareaRowHeight")) == float(typography.property("inlineTextareaRowHeight"))

            rects_before = variant_list(loader.property("embeddedInteractiveRects"))
            assert len(rects_before) == 2, rects_before
            path_y_before = rect_field(rects_before[0], "y")

            assert source_label.property("font").pixelSize() == int(typography.property("inlinePropertyPixelSize"))
            assert source_label.property("font").weight() == int(typography.property("inlinePropertyFontWeight"))
            assert status_chip_label.property("font").pixelSize() == int(typography.property("badgePixelSize"))
            assert status_chip_label.property("font").weight() == int(typography.property("badgeFontWeight"))
            assert path_field.property("font").pixelSize() == int(typography.property("inlinePropertyPixelSize"))
            assert path_field.property("font").weight() == int(typography.property("inlinePropertyFontWeight"))
            assert textarea.property("font").pixelSize() == int(typography.property("inlinePropertyPixelSize"))
            assert textarea.property("font").weight() == int(typography.property("inlinePropertyFontWeight"))

            host.setProperty("graphLabelPixelSize", 16)
            app.processEvents()

            assert int(typography.property("inlinePropertyPixelSize")) == 16
            assert int(typography.property("badgePixelSize")) == 15
            assert int(typography.property("inlineRowHeight")) == 32
            assert int(typography.property("inlineTextareaRowHeight")) == 128
            assert float(host.property("_inlineRowHeight")) == 32.0
            assert float(host.property("_inlineTextareaRowHeight")) == 128.0
            assert source_label.property("font").pixelSize() == 16
            assert source_label.property("font").weight() == int(typography.property("inlinePropertyFontWeight"))
            assert status_chip_label.property("font").pixelSize() == 15
            assert status_chip_label.property("font").weight() == int(typography.property("badgeFontWeight"))
            assert path_field.property("font").pixelSize() == 16
            assert path_field.property("font").weight() == int(typography.property("inlinePropertyFontWeight"))
            assert textarea.property("font").pixelSize() == 16
            assert textarea.property("font").weight() == int(typography.property("inlinePropertyFontWeight"))

            rects_after = variant_list(loader.property("embeddedInteractiveRects"))
            assert len(rects_after) == 2, rects_after
            """,
        )

    def test_inline_textarea_honors_dirty_shortcuts_and_explicit_commit(self) -> None:
        self._run_qml_probe(
            "inline-textarea",
            """
            host = probe.findChild(QObject, "probeHost")
            focus_sink = probe.findChild(QObject, "probeFocusSink")
            textarea = named_item(probe, "graphNodeInlineTextareaEditor", "caption")
            assert focus_sink is not None
            assert probe.findChild(QObject, "graphNodeInlineTextareaApplyButton") is None
            assert probe.findChild(QObject, "graphNodeInlineTextareaResetButton") is None

            commits = []
            host.inlinePropertyCommitted.connect(lambda node_id, key, value: commits.append((node_id, key, value)))

            window = attach_host_to_window(host, 520, 420)

            textarea.forceActiveFocus()
            app.processEvents()
            textarea.setProperty("text", "Line one draft")
            app.processEvents()

            assert str(textarea.property("text")) == "Line one draft"

            app.sendEvent(
                textarea,
                QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier),
            )
            app.sendEvent(
                textarea,
                QKeyEvent(QEvent.Type.KeyRelease, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier),
            )
            app.processEvents()

            assert str(textarea.property("text")) == "Line one"
            assert commits == []

            textarea.forceActiveFocus()
            app.processEvents()
            textarea.setProperty("text", "Line one again")
            app.processEvents()
            app.sendEvent(
                textarea,
                QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Return, Qt.KeyboardModifier.ControlModifier),
            )
            app.sendEvent(
                textarea,
                QKeyEvent(QEvent.Type.KeyRelease, Qt.Key.Key_Return, Qt.KeyboardModifier.ControlModifier),
            )
            app.processEvents()

            assert commits == [("node_inline_test", "caption", "Line one again")]
            dispose_host_window(host, window)
            engine.deleteLater()
            app.processEvents()
            """,
        )

    def test_inline_path_browse_routes_by_node_id_and_commits_selected_path(self) -> None:
        self._run_qml_probe(
            "inline-path-browse",
            """
            host = probe.findChild(QObject, "probeHost")
            canvas_proxy = probe.findChild(QObject, "canvasProxy")
            browse_button = named_item(probe, "graphNodeInlinePathBrowseButton", "source_path")

            interactions = []
            commits = []
            host.surfaceControlInteractionStarted.connect(lambda node_id: interactions.append(node_id))
            host.inlinePropertyCommitted.connect(lambda node_id, key, value: commits.append((node_id, key, value)))
            canvas_proxy.setProperty("browseResultPath", "/tmp/selected-path.png")

            window = attach_host_to_window(host, 520, 420)

            mouse_click(window, item_scene_point(browse_button))

            browse_call = variant_value(canvas_proxy.property("lastBrowseCall"))
            assert browse_call["nodeId"] == "node_inline_test"
            assert browse_call["key"] == "source_path"
            assert browse_call["currentPath"] == "/fixtures/original.txt"
            assert interactions == ["node_inline_test"]
            assert commits == [("node_inline_test", "source_path", "/tmp/selected-path.png")]

            dispose_host_window(host, window)
            engine.deleteLater()
            app.processEvents()
            """,
        )

    def test_path_pointer_inline_path_row_shortens_display_but_keeps_raw_browse_and_commit_values(self) -> None:
        self._run_qml_probe(
            "path-pointer-inline-display",
            """
            host = probe.findChild(QObject, "probeHost")
            canvas_proxy = probe.findChild(QObject, "canvasProxy")
            focus_sink = probe.findChild(QObject, "probeFocusSink")
            payload = variant_value(host.property("nodeData"))
            payload["type_id"] = "io.path_pointer"
            payload["title"] = "Path Pointer"
            payload["runtime_behavior"] = "passive"
            payload["properties"] = {
                "mode": "folder",
                "path": "/fixtures/projects/demo/results/output",
                "show_full_path": False,
            }
            payload["inline_properties"] = [
                {
                    "key": "mode",
                    "label": "Mode",
                    "inline_editor": "enum",
                    "value": "folder",
                    "enum_values": ["file", "folder"],
                    "overridden_by_input": False,
                    "input_port_label": "mode",
                },
                {
                    "key": "path",
                    "label": "Path",
                    "inline_editor": "path",
                    "value": "/fixtures/projects/demo/results/output",
                    "overridden_by_input": False,
                    "input_port_label": "path",
                },
                {
                    "key": "show_full_path",
                    "label": "Show Full Path",
                    "inline_editor": "toggle",
                    "value": False,
                    "overridden_by_input": False,
                    "input_port_label": "show_full_path",
                },
            ]
            host.setProperty("nodeData", payload)
            app.processEvents()

            window = attach_host_to_window(host, 520, 420)
            focus_sink.setParentItem(window.contentItem())
            mode_combo = next(
                child for child in walk_items(host)
                if "ComboBox" in child.metaObject().className()
                and str(child.property("displayText")) == "folder"
            )
            path_field = named_item(host, "graphNodeInlinePathEditor", "path")
            browse_button = named_item(host, "graphNodeInlinePathBrowseButton", "path")

            assert float(mode_combo.width()) + 0.5 >= float(mode_combo.property("implicitWidth")), (
                mode_combo.width(),
                mode_combo.property("implicitWidth"),
                mode_combo.property("displayText"),
            )
            assert host.property("inlineRowColor").name().lower() == host.property("themeInlineRowColor").name().lower(), (
                host.property("inlineRowColor").name(),
                host.property("themeInlineRowColor").name(),
            )
            assert host.property("inlineInputBackgroundColor").name().lower() == host.property("themeInlineInputBackgroundColor").name().lower(), (
                host.property("inlineInputBackgroundColor").name(),
                host.property("themeInlineInputBackgroundColor").name(),
            )
            assert path_field.property("fillColor").name().lower() == host.property("themeInlineInputBackgroundColor").name().lower(), (
                path_field.property("fillColor").name(),
                host.property("themeInlineInputBackgroundColor").name(),
            )
            focus_sink.forceActiveFocus()
            app.processEvents()
            assert str(path_field.property("text")) == "output", str(path_field.property("text"))

            path_field.forceActiveFocus()
            app.processEvents()
            assert str(path_field.property("text")) == "/fixtures/projects/demo/results/output", (
                str(path_field.property("text"))
            )

            focus_sink.forceActiveFocus()
            app.processEvents()
            assert str(path_field.property("text")) == "output", str(path_field.property("text"))

            interactions = []
            commits = []
            host.surfaceControlInteractionStarted.connect(lambda node_id: interactions.append(node_id))
            host.inlinePropertyCommitted.connect(lambda node_id, key, value: commits.append((node_id, key, value)))
            canvas_proxy.setProperty("browseResultPath", "/tmp/selected/deeper/folder")

            mouse_click(window, item_scene_point(browse_button))

            browse_call = variant_value(canvas_proxy.property("lastBrowseCall"))
            assert browse_call["nodeId"] == "node_inline_test", browse_call
            assert browse_call["key"] == "path", browse_call
            assert browse_call["currentPath"] == "/fixtures/projects/demo/results/output", browse_call
            assert interactions == ["node_inline_test"], interactions
            assert commits == [("node_inline_test", "path", "/tmp/selected/deeper/folder")], commits
            assert str(path_field.property("text")) == "folder", str(path_field.property("text"))

            payload = variant_value(host.property("nodeData"))
            payload["properties"]["path"] = "/tmp/selected/deeper/folder"
            payload["properties"]["show_full_path"] = True
            payload["width"] = 760.0
            host.setProperty("graphLabelPixelSize", 18)
            host.setProperty("width", 760.0)
            host.setProperty("nodeData", payload)
            app.processEvents()
            settle_events(5)

            path_field = named_item(host, "graphNodeInlinePathEditor", "path")
            show_full_label = named_item(host, "graphNodeInlinePropertyLabel", "show_full_path")
            show_full_toggle = named_item(host, "graphNodeInlineToggleEditor", "show_full_path")
            assert str(path_field.property("text")) == "/tmp/selected/deeper/folder", str(path_field.property("text"))
            assert float(show_full_label.width()) + 0.5 >= float(show_full_label.property("implicitWidth")), (
                show_full_label.width(),
                show_full_label.property("implicitWidth"),
                show_full_label.property("text"),
            )
            assert not bool(show_full_label.property("truncated")), (
                show_full_label.width(),
                show_full_label.property("implicitWidth"),
                show_full_label.property("text"),
            )
            label_right = show_full_label.mapToScene(QPointF(show_full_label.width(), 0)).x()
            toggle_left = show_full_toggle.mapToScene(QPointF(0, 0)).x()
            toggle_right = show_full_toggle.mapToScene(
                QPointF(show_full_toggle.width(), 0)
            ).x()
            row_right = host.mapToScene(QPointF(host.width(), 0)).x()
            assert toggle_left >= label_right, (
                label_right,
                toggle_left,
                show_full_label.property("text"),
            )
            assert 0.0 <= row_right - toggle_right <= 32.0, (
                row_right,
                toggle_right,
                show_full_label.property("text"),
            )
            assert float(path_field.width()) + 0.5 >= float(path_field.property("contentWidth")), (
                path_field.width(),
                path_field.property("contentWidth"),
                path_field.property("text"),
            )

            dispose_host_window(host, window)
            engine.deleteLater()
            app.processEvents()
            """,
        )

    def test_path_pointer_whole_node_drop_target_tracks_type_and_writability(self) -> None:
        self._run_qml_probe(
            "path-pointer-drop-target",
            """
            host = probe.findChild(QObject, "probeHost")
            payload = variant_value(host.property("nodeData"))
            payload["type_id"] = "io.path_pointer"
            payload["collapsed"] = True
            payload["read_only"] = False
            payload["locked_state"] = {}
            payload["properties"] = {"path": "/fixtures/original.txt", "mode": "file"}
            host.setProperty("nodeData", payload)
            app.processEvents()

            drop_area = probe.findChild(QObject, "graphNodePathPointerDropArea")
            feedback = probe.findChild(QObject, "graphNodePathPointerDropFeedback")
            assert drop_area is not None
            assert feedback is not None
            assert bool(drop_area.property("enabled")) is True
            assert bool(host.property("pathPointerDropWritable")) is True
            assert abs(float(drop_area.property("width")) - float(host.width())) < 0.5
            assert abs(float(drop_area.property("height")) - float(host.height())) < 0.5

            host.setProperty(
                "pathPointerDropData",
                {"path": "/fixtures/replacement.txt", "isFolder": False, "itemCount": 1},
            )
            app.processEvents()
            assert bool(host.property("pathPointerDropValid")) is True

            payload["locked_state"] = {"locked": True}
            host.setProperty("nodeData", payload)
            app.processEvents()
            assert bool(drop_area.property("enabled")) is True
            assert bool(host.property("pathPointerDropWritable")) is False
            assert bool(host.property("pathPointerDropValid")) is False

            payload["locked_state"] = {}
            payload["read_only"] = True
            host.setProperty("nodeData", payload)
            app.processEvents()
            assert bool(drop_area.property("enabled")) is True
            assert bool(host.property("pathPointerDropWritable")) is False

            payload["read_only"] = False
            payload["type_id"] = "core.logger"
            host.setProperty("nodeData", payload)
            app.processEvents()
            assert bool(drop_area.property("enabled")) is False

            engine.deleteLater()
            app.processEvents()
            """,
        )

    def test_inline_color_picker_routes_by_node_id_and_commits_selected_color(self) -> None:
        self._run_qml_probe(
            "inline-color-picker",
            """
            host = probe.findChild(QObject, "probeHost")
            canvas_proxy = probe.findChild(QObject, "canvasProxy")
            payload = variant_value(host.property("nodeData"))
            payload["properties"] = {
                "accent_color": "#336699"
            }
            payload["inline_properties"] = [
                {
                    "key": "accent_color",
                    "label": "Accent",
                    "inline_editor": "color",
                    "value": "#336699",
                    "overridden_by_input": False,
                    "input_port_label": "accent_color"
                }
            ]
            host.setProperty("nodeData", payload)
            app.processEvents()

            color_field = named_item(probe, "graphNodeInlineColorEditor", "accent_color")
            pick_button = named_item(probe, "graphNodeInlineColorPickerButton", "accent_color")

            interactions = []
            commits = []
            host.surfaceControlInteractionStarted.connect(lambda node_id: interactions.append(node_id))
            host.inlinePropertyCommitted.connect(lambda node_id, key, value: commits.append((node_id, key, value)))
            canvas_proxy.setProperty("colorResult", "#80336699")

            window = attach_host_to_window(host, 520, 420)

            mouse_click(window, item_scene_point(pick_button))

            pick_call = variant_value(canvas_proxy.property("lastColorPickCall"))
            assert pick_call["nodeId"] == "node_inline_test"
            assert pick_call["key"] == "accent_color"
            assert pick_call["currentValue"] == "#336699"
            assert str(color_field.property("text")) == "#80336699"
            assert interactions == ["node_inline_test"]
            assert commits == [("node_inline_test", "accent_color", "#80336699")]

            dispose_host_window(host, window)
            engine.deleteLater()
            app.processEvents()
            """,
        )

    def test_group_backdrop_publishes_no_body_editor_or_surface_actions(self) -> None:
        self._run_group_backdrop_probe(
            "group-no-body-editor",
            """
            host = probe.findChild(QObject, "probeHost")
            loader = host.findChild(QObject, "graphNodeSurfaceLoader")
            assert loader is not None
            assert probe.findChild(QObject, "graphNodeGroupBackdropRichTextBlock") is None
            assert probe.findChild(QObject, "graphNodeGroupBackdropBodyText") is None
            assert probe.findChild(QObject, "graphGroupBackdropBodyEditor") is None
            assert probe.findChild(QObject, "graphGroupBackdropBodyEditorField") is None
            assert probe.findChild(QObject, "graphGroupBackdropBodyApplyButton") is None
            assert probe.findChild(QObject, "graphGroupBackdropBodyResetButton") is None
            assert variant_list(loader.property("embeddedInteractiveRects")) == []
            assert variant_list(loader.property("surfaceActions")) == []
            """,
        )

    def test_live_presentation_facts_drive_interval_searchable_and_condition_controls(self) -> None:
        self._run_qml_probe(
            "live-inline-presentation-facts",
            """
            host = probe.findChild(QObject, "probeHost")
            execution_facts = probe.findChild(QObject, "executionFactsProxy")
            payload = variant_value(host.property("nodeData"))
            payload["height"] = 300.0
            payload["surface_metrics"]["body_height"] = 196.0
            payload["inline_properties"] = [
                {
                    "key": "result_bound",
                    "label": "Result bound",
                    "type": "interval_1d",
                    "inline_editor": "interval_slider",
                    "value": {"start": 0.0, "end": 1.0},
                    "display_value": {"start": 0.0, "end": 1.0},
                    "display_value_available": True,
                    "minimum": 0.0,
                    "maximum": 10.0,
                    "step": 1.0,
                    "interval_direction": "increasing",
                    "editor_enabled": True,
                    "overridden_by_input": False,
                },
                {
                    "key": "number_of_sectors",
                    "label": "Number of sectors",
                    "type": "int",
                    "inline_editor": "slider",
                    "value": 2,
                    "display_value": 2,
                    "display_value_available": True,
                    "minimum": 2,
                    "maximum": 360,
                    "step": 1,
                    "editor_enabled": True,
                    "overridden_by_input": False,
                },
                {
                    "key": "color_map",
                    "label": "Color map",
                    "type": "enum",
                    "inline_editor": "enum",
                    "enum_values": ["Rainbow", "Viridis", "Grayscale"],
                    "searchable": True,
                    "value": "Rainbow",
                    "display_value": "Rainbow",
                    "display_value_available": True,
                    "editor_enabled": True,
                    "overridden_by_input": False,
                },
            ]
            host.setProperty("nodeData", payload)
            settle_events(5)

            interval = named_item(host, "graphNodeInlineIntervalSliderEditor", "result_bound")
            sectors = named_item(host, "graphNodeInlineSliderEditor", "number_of_sectors")
            searchable = named_item(host, "graphNodeInlineSearchableEnumEditor", "color_map")
            assert interval is not None
            assert sectors is not None
            assert searchable is not None
            slider_handle = sectors.property("handle")
            slider_background = sectors.property("background")
            assert slider_handle is not None
            assert slider_background is not None
            assert float(slider_handle.property("width")) == 14.0
            handle_center_y = float(slider_handle.property("y")) + float(slider_handle.property("height")) * 0.5
            track_center_y = float(slider_background.property("y")) + float(slider_background.property("height")) * 0.5
            assert abs(handle_center_y - track_center_y) < 0.01, (
                f"slider handle/track center mismatch: handle={handle_center_y}, track={track_center_y}"
            )
            assert bool(interval.property("enabled")) is True
            assert float(interval.property("semanticStart")) == 0.0
            assert float(interval.property("semanticEnd")) == 1.0
            assert str(searchable.property("selectedValue")) == "Rainbow"

            execution_facts.setProperty(
                "propertyPresentationLookup",
                {
                    "node_inline_test": {
                        "result_bound": {
                            **payload["inline_properties"][0],
                            "display_value": {"start": 10.0, "end": 0.0},
                            "overridden_by_input": True,
                            "editor_enabled": False,
                            "editor_disabled_reason": "Value supplied by connected input.",
                        },
                        "number_of_sectors": {
                            **payload["inline_properties"][1],
                            "condition_enabled": False,
                            "editor_enabled": False,
                            "editor_disabled_reason": "Available when Cyclic symmetry mode is Manual.",
                        },
                        "color_map": {
                            **payload["inline_properties"][2],
                            "display_value": "Viridis",
                            "overridden_by_input": True,
                            "editor_enabled": False,
                            "editor_disabled_reason": "Value supplied by connected input.",
                        },
                    }
                },
            )
            settle_events(5)

            assert float(interval.property("semanticStart")) == 10.0
            assert float(interval.property("semanticEnd")) == 0.0
            assert str(interval.property("intervalDirection")) == "increasing"
            assert bool(interval.property("semanticStartOnLeft")) is False
            assert bool(interval.property("enabled")) is False
            assert bool(sectors.property("enabled")) is False
            assert str(searchable.property("selectedValue")) == "Viridis"
            assert bool(searchable.property("enabled")) is False

            inline_layer = host.findChild(QObject, "graphInlinePropertiesLayer")
            assert len(variant_list(inline_layer.property("embeddedInteractiveRects"))) == 0

            execution_facts.setProperty("propertyPresentationLookup", {})
            settle_events(5)
            assert float(interval.property("semanticStart")) == 0.0
            assert float(interval.property("semanticEnd")) == 1.0
            assert bool(interval.property("enabled")) is True
            assert bool(sectors.property("enabled")) is True
            assert str(searchable.property("selectedValue")) == "Rainbow"
            assert bool(searchable.property("enabled")) is True
            """,
        )

    def test_input_rows_show_default_property_editor_until_input_override(self) -> None:
        self._run_qml_probe(
            "input-default-property-editor",
            """
            host = probe.findChild(QObject, "probeHost")
            payload = variant_value(host.property("nodeData"))
            payload["ports"] = [
                {
                    "key": "message",
                    "label": "Message",
                    "direction": "in",
                    "kind": "data",
                    "data_type": "str",
                    "connected": False,
                    "default_property": {
                        "key": "message",
                        "label": "Message",
                        "inline_editor": "text",
                        "value": "Line one",
                        "overridden_by_input": False,
                    },
                    "allow_multiple_connections": False,
                },
                {
                    "key": "result",
                    "label": "Result",
                    "direction": "out",
                    "kind": "data",
                    "data_type": "str",
                    "connected": False,
                    "allow_multiple_connections": False,
                },
            ]
            host.setProperty("nodeData", payload)
            app.processEvents()

            row = named_item(probe, "graphNodeInputPortRow", "message")
            editor = named_item(probe, "graphNodeInputDefaultProperty", "message")
            assert row is not None, "input row missing"
            assert bool(row.property("defaultEditorVisible")) is True, row.property("defaultEditorVisible")
            assert editor is not None, "default-property editor missing"

            payload = {
                **payload,
                "ports": [
                    {
                        **payload["ports"][0],
                        "default_property": {
                            **payload["ports"][0]["default_property"],
                            "overridden_by_input": True,
                        },
                    },
                    *payload["ports"][1:],
                ],
            }
            host.setProperty("nodeData", payload)
            app.processEvents()
            overridden_row = named_item(probe, "graphNodeInputPortRow", "message")
            assert overridden_row is not None, "overridden input row missing"
            overridden_editor = named_item(
                probe,
                "graphNodeInlineValueEditor",
                "message",
            )
            overridden_layer = named_item(
                probe,
                "graphNodeInputDefaultProperty",
                "message",
            )
            assert bool(overridden_row.property("defaultEditorVisible")) is True, overridden_row.property("defaultEditorVisible")
            assert bool(overridden_editor.property("enabled")) is False
            assert str(overridden_editor.property("text")) == "Line one"
            assert len(variant_list(overridden_layer.property("embeddedInteractiveRects"))) == 0

            payload["ports"][0]["connected"] = False
            payload["ports"][0]["default_property"]["overridden_by_input"] = False
            host.setProperty("nodeData", payload)
            app.processEvents()
            restored_row = named_item(probe, "graphNodeInputPortRow", "message")
            assert restored_row is not None, "restored input row missing"
            assert bool(restored_row.property("defaultEditorVisible")) is True, restored_row.property("defaultEditorVisible")
            """,
        )


    def test_shared_list_and_nullable_interval_controls_commit_and_disable(self) -> None:
        self._run_qml_probe(
            "list-and-interval-fields",
            """
            from PyQt6.QtCore import QPointF, Qt
            from PyQt6.QtTest import QTest

            host = probe.findChild(QObject, "probeHost")
            execution_facts = probe.findChild(QObject, "executionFactsProxy")
            payload = variant_value(host.property("nodeData"))
            payload["height"] = 360.0
            payload["surface_metrics"]["body_height"] = 280.0
            payload["inline_properties"] = [
                {
                    "key": "labels",
                    "label": "Labels",
                    "type": "json",
                    "inline_editor": "list",
                    "value": ["A"],
                    "display_value": ["A"],
                    "display_value_available": True,
                    "list_item_type": "str",
                    "list_item_enum_values": [],
                    "list_item_enum_codes": [],
                    "editor_enabled": True,
                    "overridden_by_input": False,
                },
                {
                    "key": "x_axis_interval",
                    "label": "X axis interval",
                    "type": "interval_1d",
                    "inline_editor": "interval_fields",
                    "value": None,
                    "display_value": None,
                    "display_value_available": True,
                    "nullable": True,
                    "editor_enabled": True,
                    "overridden_by_input": False,
                },
            ]
            host.setProperty("nodeData", payload)
            settle_events(5)

            list_editor = named_item(host, "graphNodeInlineListEditor", "labels")
            interval_editor = named_item(host, "graphNodeInlineIntervalFieldsEditor", "x_axis_interval")
            add_button = list_editor.findChild(QObject, "graphSurfaceListAddButton") if list_editor is not None else None
            auto_button = interval_editor.findChild(QObject, "graphSurfaceIntervalAutoButton") if interval_editor is not None else None
            assert list_editor is not None, "list editor missing"
            assert interval_editor is not None, "interval editor missing"
            assert add_button is not None, "list add button missing"
            assert auto_button is not None, "interval auto button missing"
            list_row = named_item(host, "graphNodeInlinePropertyRow", "labels")
            assert list_row is not None, "list property row missing"

            prefs = probe.findChild(QObject, "toolbarPrefs")
            assert prefs is not None, "toolbar preferences missing"
            prefs.setProperty("activeThemeId", "stitch_light")
            settle_events(2)
            for actual_name, expected_color in (
                ("inlineRowColor", "#ffffff"),
                ("inlineRowBorderColor", "#ccd6e0"),
                ("inlineLabelColor", "#5f6b7a"),
                ("inlineInputTextColor", "#17212b"),
                ("inlineInputBackgroundColor", "#ffffff"),
                ("inlineInputBorderColor", "#c2cedb"),
                ("inlineDrivenTextColor", "#4f5e70"),
            ):
                assert host.property(actual_name).name().lower() == expected_color, (
                    actual_name,
                    host.property(actual_name).name(),
                )

            prefs.setProperty("activeThemeId", "stitch_dark")
            settle_events(2)
            for actual_name, expected_name in (
                ("inlineRowColor", "themeInlineRowColor"),
                ("inlineRowBorderColor", "themeInlineRowBorderColor"),
                ("inlineLabelColor", "themeInlineLabelColor"),
                ("inlineInputTextColor", "themeInlineInputTextColor"),
                ("inlineInputBackgroundColor", "themeInlineInputBackgroundColor"),
                ("inlineInputBorderColor", "themeInlineInputBorderColor"),
                ("inlineDrivenTextColor", "themeInlineDrivenTextColor"),
            ):
                assert host.property(actual_name).name().lower() == host.property(expected_name).name().lower(), (
                    actual_name,
                    host.property(actual_name).name(),
                    host.property(expected_name).name(),
                )
            assert list_row.property("color").alpha() == 0
            for button in (add_button, auto_button):
                assert int(button.property("focusPolicy")) == int(Qt.FocusPolicy.TabFocus)
                assert button.property("baseFillColor").name().lower() == host.property("themeInlineInputBackgroundColor").name().lower()
                assert button.property("baseBorderColor").name().lower() == host.property("themeInlineInputBorderColor").name().lower()

            assert variant_list(list_editor.property("values")) == ["A"]
            assert interval_editor.property("value") is None
            base_row_height = float(host.property("_inlineRowHeight"))
            assert abs(base_row_height + float(list_editor.height()) - 142.0) < 0.5, ("list-height", list_editor.height(), base_row_height)
            assert abs(base_row_height + float(interval_editor.height()) - float(host.property("_inlineStackedRowHeight"))) < 0.5, ("interval-height", interval_editor.height(), host.property("_inlineStackedRowHeight"))
            list_bottom = list_editor.mapToItem(host, QPointF(0.0, list_editor.height())).y()
            interval_top = interval_editor.mapToItem(host, QPointF(0.0, 0.0)).y()
            assert interval_top >= list_bottom + 3.0, (interval_top, list_bottom)
            start_field = interval_editor.findChild(QObject, "graphSurfaceIntervalStartField")
            end_field = interval_editor.findChild(QObject, "graphSurfaceIntervalEndField")
            assert start_field is not None and end_field is not None, "interval-fields"
            assert bool(start_field.property("visible")) and float(start_field.height()) > 0.0, ("interval-visible", start_field.property("visible"), start_field.height())
            interval_commits = []
            interval_editor.commitRequested.connect(lambda value: interval_commits.append(variant_value(value)))
            start_field.setProperty("text", "1")
            end_field.setProperty("text", "2")
            start_field.editingFinished.emit()
            settle_events(2)
            assert interval_commits and interval_commits[-1] == {"start": 1.0, "end": 2.0}, ("interval-commit", interval_commits)

            numeric_commits = []
            payload["inline_properties"][0].update({
                "list_item_type": "int",
                "list_item_minimum": 5,
                "list_item_maximum": 10,
                "value": [],
                "display_value": [],
            })
            host.setProperty("nodeData", payload)
            settle_events(2)
            list_editor = named_item(host, "graphNodeInlineListEditor", "labels")
            add_button = list_editor.findChild(QObject, "graphSurfaceListAddButton")
            list_editor.commitRequested.connect(lambda value: numeric_commits.append(variant_list(value)))
            add_button.clicked.emit()
            settle_events(2)
            assert numeric_commits and numeric_commits[-1] == [5], ("numeric-add", numeric_commits)

            execution_facts.setProperty(
                "propertyPresentationLookup",
                {
                    "node_inline_test": {
                        "labels": {
                            **payload["inline_properties"][0],
                            "overridden_by_input": True,
                            "editor_enabled": False,
                            "editor_disabled_reason": "Value supplied by connected input.",
                        },
                        "x_axis_interval": {
                            **payload["inline_properties"][1],
                            "overridden_by_input": True,
                            "editor_enabled": False,
                            "editor_disabled_reason": "Value supplied by connected input.",
                        },
                    }
                },
            )
            settle_events(5)
            list_editor = named_item(host, "graphNodeInlineListEditor", "labels")
            interval_editor = named_item(host, "graphNodeInlineIntervalFieldsEditor", "x_axis_interval")
            assert bool(list_editor.property("editorEnabled")) is False, list_editor.property("editorEnabled")
            assert bool(interval_editor.property("editorEnabled")) is False, interval_editor.property("editorEnabled")
            inline_layer = host.findChild(QObject, "graphInlinePropertiesLayer")
            assert len(variant_list(inline_layer.property("embeddedInteractiveRects"))) == 0
            engine.deleteLater()
            app.processEvents()
            """,
        )

        list_source = (
            REPO_ROOT
            / "ea_node_editor"
            / "ui_qml"
            / "components"
            / "graph"
            / "surface_controls"
            / "GraphSurfaceListEditor.qml"
        ).read_text(encoding="utf-8")
        self.assertIn("commitRequested(snapshot())", list_source)
        self.assertIn('Accessible.name: "Add list item"', list_source)
        self.assertIn('objectName: "graphSurfaceListColorEditor"', list_source)


class GraphSurfaceFolderExplorerInlineBridgeTests(unittest.TestCase):
    def test_folder_explorer_drag_payload_targets_path_pointer_contract(self) -> None:
        surface_bridge = (
            REPO_ROOT
            / "ea_node_editor"
            / "ui_qml"
            / "components"
            / "graph_canvas"
            / "GraphCanvasNodeSurfaceBridge.qml"
        ).read_text(encoding="utf-8")

        self.assertIn("function folderExplorerDragPayload(path, isFolder)", surface_bridge)
        self.assertIn(
            '"action_id": root._folderExplorerActionId("folder_explorer_send_to_corex_path_pointer")',
            surface_bridge,
        )
        self.assertIn('"type_id": "io.path_pointer"', surface_bridge)
        self.assertIn('"mode": Boolean(isFolder) ? "folder" : "file"', surface_bridge)

    def test_folder_explorer_surface_transient_state_stays_out_of_property_commits(self) -> None:
        surface_qml = (
            REPO_ROOT
            / "ea_node_editor"
            / "ui_qml"
            / "components"
            / "graph"
            / "passive"
            / "GraphNativeExplorerSurface.qml"
        ).read_text(encoding="utf-8")

        self.assertIn('objectName: "graphNativeExplorerSurface"', surface_qml)
        self.assertIn('objectName: "graphNodeViewerViewport"', surface_qml)
        self.assertIn("readonly property var embeddedInteractiveRects", surface_qml)
        self.assertIn('"folder_explorer_list"', surface_qml)
        self.assertIn('"folder_explorer_navigate"', surface_qml)
        self.assertNotIn("inlinePropertyCommitted", surface_qml)
        self.assertNotIn("commitNodeSurfaceProperty", surface_qml)
        self.assertNotIn("set_node_property", surface_qml)

    def test_folder_explorer_current_path_changes_are_owned_by_action_bridge(self) -> None:
        surface_qml = (
            REPO_ROOT
            / "ea_node_editor"
            / "ui_qml"
            / "components"
            / "graph"
            / "passive"
            / "GraphNativeExplorerSurface.qml"
        ).read_text(encoding="utf-8")
        command_bridge = (
            REPO_ROOT
            / "ea_node_editor"
            / "ui_qml"
            / "graph_canvas_command"
            / "folder_explorer_ops.py"
        ).read_text(encoding="utf-8")
        composition = (
            REPO_ROOT
            / "ea_node_editor"
            / "ui"
            / "shell"
            / "composition"
            / "runtime_services.py"
        ).read_text(encoding="utf-8")

        self.assertIn('readonly property string currentPath: _propertyString("current_path")', surface_qml)
        self.assertIn("def _folder_explorer_navigate(", command_bridge)
        self.assertIn('callback(node_id, "current_path", current_path)', command_bridge)
        self.assertIn("enabled=False", composition)
        self.assertNotIn(
            "host.inlinePropertyCommitted(String(host.nodeData.node_id || \"\"), \"current_path\"",
            surface_qml,
        )

    def test_graph_canvas_accepts_os_file_drops_as_path_pointer_nodes(self) -> None:
        canvas_qml = (
            REPO_ROOT
            / "ea_node_editor"
            / "ui_qml"
            / "components"
            / "GraphCanvas.qml"
        ).read_text(encoding="utf-8")
        command_bridge = (
            REPO_ROOT
            / "ea_node_editor"
            / "ui_qml"
            / "graph_canvas_command"
            / "node_creation_ops.py"
        ).read_text(encoding="utf-8")
        host_qml = (
            REPO_ROOT
            / "ea_node_editor"
            / "ui_qml"
            / "components"
            / "graph"
            / "GraphNodeHost.qml"
        ).read_text(encoding="utf-8")
        explorer_qml = (
            REPO_ROOT
            / "ea_node_editor"
            / "ui_qml"
            / "components"
            / "graph"
            / "passive"
            / "GraphNativeExplorerSurface.qml"
        ).read_text(encoding="utf-8")

        self.assertIn('objectName: "graphCanvasOsPathDropArea"', canvas_qml)
        self.assertIn('"text/html", "image/*", "video/*"', canvas_qml)
        self.assertIn("function performPathPointerDrop(screenX, screenY, path, isFolder)", canvas_qml)
        self.assertIn("function performPathPointerNodeDrop(nodeId, path, isFolder)", canvas_qml)
        self.assertIn('"itemCount": eventObj.urls.length', canvas_qml)
        self.assertIn("bridge.request_canvas_import_local_path(", canvas_qml)
        self.assertIn("bridge.request_canvas_import_drop(urls, text, html,", canvas_qml)
        self.assertIn("bridge.request_update_path_pointer_node(", canvas_qml)
        self.assertIn("def request_create_path_pointer_node(", command_bridge)
        self.assertIn("def request_update_path_pointer_node(", command_bridge)
        self.assertIn('objectName: "graphNodePathPointerDropArea"', host_qml)
        self.assertIn("eventObj.accept(card.pathPointerDropValid ? Qt.CopyAction : Qt.IgnoreAction)", host_qml)
        self.assertIn('text: "Replace path"', host_qml)
        self.assertNotIn("usesManualPathPointerDrop", explorer_qml)


if __name__ == "__main__":
    unittest.main()

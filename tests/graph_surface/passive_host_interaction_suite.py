from __future__ import annotations

from tests.graph_surface.environment import *  # noqa: F403

class PassiveGraphSurfaceHostTests(PassiveGraphSurfaceHostTestBase):
    def test_collapsible_node_uses_shared_expand_collapse_action(self) -> None:
        self._run_qml_probe(
            "shared-expand-collapse-action",
            """
            from ea_node_editor.ui.icon_registry import UiIconRegistryBridge, UiIconImageProvider, UI_ICON_PROVIDER_ID

            ui_icons = UiIconRegistryBridge()
            engine.rootContext().setContextProperty("uiIcons", ui_icons)
            engine.addImageProvider(UI_ICON_PROVIDER_ID, UiIconImageProvider())
            payload = node_payload()
            payload["collapsible"] = True
            host = create_component(graph_node_host_qml_path, {"nodeData": payload})
            window = attach_host_to_window(host, 640, 480)
            host.setProperty("toolbarActive", True)
            toolbar = create_component(
                components_dir / "graph" / "overlay" / "GraphNodeFloatingToolbar.qml",
                {"host": host, "visibleSceneRectPayload": {"x": 0, "y": 0, "width": 640, "height": 480}},
            )
            toolbar.setParentItem(window.contentItem())
            settle_events(2)

            for button_name, icon_name in (
                ("graphNodeFloatingToolbarAction_run_selected", "node-run"),
                ("graphNodeFloatingToolbarActionMenu_run_selected", "settings"),
                ("graphNodeFloatingToolbarAction_toggle_node_collapsed", "node-collapse"),
            ):
                button = named_item(toolbar, button_name)
                assert button.property("iconName") == icon_name
                assert f"image://ui-icons/{icon_name}?" in button.property("resolvedIconSource")
                assert not button.property("labelVisible")
            options_button = named_item(toolbar, "graphNodeFloatingToolbarActionMenu_run_selected")
            mouse_click(window, item_scene_point(options_button))
            settle_events(2)
            assert toolbar.property("runMenuVisible") is True
            toolbar.setProperty("runMenuVisible", False)

            actions = [variant_value(action) for action in variant_list(host.property("commonNodeActions"))]
            toggle = next(action for action in actions if action["id"] == "toggle_node_collapsed")
            assert toggle["label"] == "Collapse"
            assert toggle["icon"] == "node-collapse"

            requests = []
            host.nodeActionRequested.connect(lambda node_id, action_id, action_payload: requests.append((node_id, action_id)))
            host.dispatchNodeAction("toggle_node_collapsed", None)
            assert requests == [("node_surface_host_test", "toggle_node_collapsed")]

            payload["collapsed"] = True
            host.setProperty("nodeData", payload)
            settle_events(2)
            actions = [variant_value(action) for action in variant_list(host.property("commonNodeActions"))]
            toggle = next(action for action in actions if action["id"] == "toggle_node_collapsed")
            assert toggle["label"] == "Expand"
            assert toggle["icon"] == "node-expand"
            expand_button = named_item(toolbar, "graphNodeFloatingToolbarAction_toggle_node_collapsed")
            assert "image://ui-icons/node-expand?" in expand_button.property("resolvedIconSource")

            toolbar.deleteLater()
            dispose_host_window(host, window)
            engine.deleteLater()
            app.processEvents()
            """,
        )

    def test_passive_lock_action_lowers_and_blocks_host_until_interaction_is_enabled(self) -> None:
        self._run_qml_probe(
            "passive-authored-lock-host",
            """
            canvas_component = QQmlComponent(engine)
            canvas_component.setData(
                b'import QtQuick 2.15; Item { property bool interactWithLockedObjects: false }',
                QUrl("locked_canvas_stub.qml"),
            )
            canvas_stub = canvas_component.create()

            payload = node_payload(surface_family="annotation", surface_variant="text")
            payload.update({
                "type_id": "passive.annotation.text",
                "runtime_behavior": "passive",
                "locked": True,
            })
            host = create_component(graph_node_host_qml_path, {"nodeData": payload, "canvasItem": canvas_stub})
            actions = [variant_value(action) for action in variant_list(host.property("availableActions"))]

            assert bool(host.property("authorLocked")) is True
            assert bool(host.property("surfaceInteractionLocked")) is True
            assert bool(host.property("enabled")) is False
            assert float(host.property("z")) == 10.0
            assert [action["label"] for action in actions] == ["Zoom to node", "Unlock"]
            assert actions[-1]["checked"] is True

            canvas_stub.setProperty("interactWithLockedObjects", True)
            settle_events(2)
            assert bool(host.property("enabled")) is True
            overlay = named_item(host, "graphNodeLockedOverlay")
            assert bool(overlay.property("visible")) is True
            assert bool(overlay.property("enabled")) is True
            events = host_pointer_events(host)
            window = attach_host_to_window(host)
            mouse_click(window, item_scene_point(overlay))
            assert events["clicked"] == [("node_surface_host_test", False)]
            assert events["opened"] == []
            assert events["contexts"] == []

            requests = []
            host.nodeActionRequested.connect(lambda node_id, action_id, payload: requests.append((node_id, action_id)))
            host.dispatchNodeAction("remove_node", None)
            host.dispatchNodeAction("toggle_node_lock", None)
            assert requests == [("node_surface_host_test", "toggle_node_lock")]

            dispose_host_window(host, window)
            canvas_stub.deleteLater()
            engine.deleteLater()
            app.processEvents()
            """,
        )

    def test_node_comment_badge_and_read_only_paths_stay_canvas_owned(self) -> None:
        qml_text = (
            _REPO_ROOT / "ea_node_editor/ui_qml/components/graph/overlay/GraphNodeCommentPopoverLayer.qml"
        ).read_text(encoding="utf-8")
        qml_text += (
            _REPO_ROOT / "ea_node_editor/ui_qml/components/graph/GraphNodeHost.qml"
        ).read_text(encoding="utf-8")

        for snippet in (
            "if (target === \"inspector\" && root.nodeEditable(nodeData))",
            "visible: root.editorOpen && root.activeEditable()",
            "return root.activeEditable() && bridge && bridge.remove_node_comment",
            "return root.activeEditable() && bridge && bridge.resolve_all_node_comments",
        ):
            with self.subTest(snippet=snippet):
                self.assertIn(snippet, qml_text)
        self.assertNotIn("graphNodeCommentGhostBadge", qml_text)

    def test_folder_explorer_surface_loader_renders_controlled_file_list(self) -> None:
        self._run_qml_probe(
            "folder-explorer-controlled-surface-loader",
            """
            def create_folder_explorer_canvas_stub():
                component = QQmlComponent(engine)
                component.setData(
                    b'''
                    import QtQuick 2.15
                    import QtQml 2.15
                    Item {
                        id: canvas
                        objectName: "folderExplorerCanvasStub"
                        property var requests: []
                        function folderExplorerDragPayload(path, isFolder) {
                            return {
                                "action_id": canvas.canvasActionRouter.folderExplorerActionId("folder_explorer_send_to_corex_path_pointer"),
                                "type_id": "io.path_pointer",
                                "properties": {
                                    "path": String(path || ""),
                                    "mode": Boolean(isFolder) ? "folder" : "file"
                                }
                            };
                        }
                        property QtObject canvasActionRouter: QtObject {
                            function folderExplorerActionId(command) {
                                var map = {
                                    "folder_explorer_list": "folder_explorer_list",
                                    "folder_explorer_navigate": "folder_explorer_navigate",
                                    "folder_explorer_refresh": "folder_explorer_refresh",
                                    "folder_explorer_set_sort": "folder_explorer_set_sort",
                                    "folder_explorer_set_search": "folder_explorer_set_search",
                                    "folder_explorer_open": "folder_explorer_open",
                                    "folder_explorer_open_in_new_window": "folder_explorer_open_in_new_window",
                                    "folder_explorer_new_folder": "folder_explorer_new_folder",
                                    "folder_explorer_rename": "folder_explorer_rename",
                                    "folder_explorer_delete": "folder_explorer_delete",
                                    "folder_explorer_cut": "folder_explorer_cut",
                                    "folder_explorer_copy": "folder_explorer_copy",
                                    "folder_explorer_paste": "folder_explorer_paste",
                                    "folder_explorer_copy_path": "folder_explorer_copy_path",
                                    "folder_explorer_properties": "folder_explorer_properties",
                                    "folder_explorer_send_to_corex_path_pointer": "folder_explorer_send_to_corex_path_pointer"
                                };
                                return map[String(command || "")] || String(command || "");
                            }

                            function requestFolderExplorerAction(actionId, payload) {
                                var path = String((payload || {}).path || "C:/Projects/Corex");
                                canvas.requests = canvas.requests.concat([{"action_id": actionId, "payload": payload || ({})}]);
                                return {
                                    "success": true,
                                    "cancelled": false,
                                    "action_id": actionId,
                                    "node_id": String((payload || {}).node_id || ""),
                                    "path": path,
                                    "error": {},
                                    "listing": {
                                        "directory_path": path,
                                        "parent_path": "C:/Projects",
                                        "breadcrumbs": [
                                            {"name": "C:", "absolute_path": "C:"},
                                            {"name": "Projects", "absolute_path": "C:/Projects"},
                                            {"name": "Corex", "absolute_path": "C:/Projects/Corex"}
                                        ],
                                        "entries": [
                                            {
                                                "name": "Assets",
                                                "absolute_path": path + "/Assets",
                                                "kind": "folder",
                                                "is_folder": true,
                                                "modified_timestamp": 1710000000,
                                                "extension": "",
                                                "type_label": "File folder",
                                                "size_bytes": -1,
                                                "display_size": ""
                                            },
                                            {
                                                "name": "report.txt",
                                                "absolute_path": path + "/report.txt",
                                                "kind": "file",
                                                "is_folder": false,
                                                "modified_timestamp": 1710000010,
                                                "extension": ".txt",
                                                "type_label": "TXT File",
                                                "size_bytes": 128,
                                                "display_size": "128 B"
                                            }
                                        ],
                                        "sort_key": String((payload || {}).sort_key || "name"),
                                        "reverse": Boolean((payload || {}).reverse),
                                        "filter_text": String((payload || {}).filter_text || "")
                                    }
                                };
                            }
                        }
                    }
                    ''',
                    QUrl("folder_explorer_canvas_stub.qml"),
                )
                if component.status() != QQmlComponent.Status.Ready:
                    errors = "\\n".join(error.toString() for error in component.errors())
                    raise AssertionError(f"Failed to load folder explorer canvas stub:\\n{errors}")
                obj = component.create()
                if obj is None:
                    errors = "\\n".join(error.toString() for error in component.errors())
                    raise AssertionError(f"Failed to instantiate folder explorer canvas stub:\\n{errors}")
                return obj

            def to_variant(value):
                if hasattr(value, "toVariant"):
                    value = value.toVariant()
                if isinstance(value, list):
                    return [to_variant(item) for item in value]
                if isinstance(value, tuple):
                    return tuple(to_variant(item) for item in value)
                if isinstance(value, dict):
                    return {key: to_variant(item) for key, item in value.items()}
                return value

            canvas_stub = create_folder_explorer_canvas_stub()
            payload = node_payload()
            payload["node_id"] = "folder_explorer_surface_test"
            payload["type_id"] = "io.folder_explorer"
            payload["title"] = "Folder Explorer"
            payload["runtime_behavior"] = "passive"
            payload["surface_spec"] = surface_spec_payload_for_values(
                type_id="io.folder_explorer",
                family="standard",
                variant="",
            )
            payload["properties"] = {"current_path": "C:/Projects/Corex"}
            payload["inline_properties"] = [
                {
                    "key": "current_path",
                    "label": "Current Path",
                    "inline_editor": "path",
                    "value": "C:/Projects/Corex",
                    "overridden_by_input": False,
                    "input_port_label": "current",
                }
            ]
            payload["width"] = 560.0
            payload["height"] = 360.0
            payload["surface_metrics"].update({
                "default_width": 560.0,
                "default_height": 360.0,
                "min_width": 360.0,
                "min_height": 260.0,
                "body_left_margin": 8.0,
                "body_right_margin": 8.0,
                "body_top": 30.0,
                "body_height": 320.0,
                "body_bottom_margin": 8.0,
            })

            host = create_component(
                graph_node_host_qml_path,
                {"nodeData": payload, "canvasItem": canvas_stub},
            )
            window = attach_host_to_window(host, 720, 520)
            settle_events(6)

            surface = host.findChild(QObject, "graphNativeExplorerSurface")
            loader = host.findChild(QObject, "graphNodeSurfaceLoader")
            viewport = named_item(host, "graphNodeViewerViewport")
            path_text = named_item(host, "graphFolderExplorerPathText")
            parent_row = named_item(host, "graphFolderExplorerParentRow")
            entry_row = named_item(host, "graphFolderExplorerEntryRow")

            assert surface is not None
            assert bool(loader.property("surfaceLoaded")) is True
            assert str(loader.property("loadedSurfaceKey")) == "native_explorer"
            assert viewport is not None
            assert path_text is not None
            assert parent_row is not None
            assert entry_row is not None
            assert "C:/Projects/Corex" in str(path_text.property("text"))
            assert abs(float(viewport.property("x")) - 8.0) < 0.5
            assert abs(float(viewport.property("y")) - 30.0) < 0.5
            assert abs(float(viewport.property("width")) - 544.0) < 0.5
            expected_viewport_height = float(host.height()) - 78.0
            assert abs(float(viewport.property("height")) - expected_viewport_height) < 0.5, (
                float(viewport.property("height")),
                expected_viewport_height,
                float(host.height()),
            )
            assert to_variant(loader.property("embeddedInteractiveRects"))[0]["height"] > 0

            requests = to_variant(canvas_stub.property("requests"))
            assert len(requests) == 1
            assert requests[0]["action_id"] == "folder_explorer_list"
            assert requests[0]["payload"]["node_id"] == "folder_explorer_surface_test"
            assert requests[0]["payload"]["path"] == "C:/Projects/Corex"

            dispose_host_window(host, window)
            canvas_stub.deleteLater()
            engine.deleteLater()
            app.processEvents()
            """,
        )

    def test_folder_explorer_columns_resize_and_persist_without_breaking_sort(self) -> None:
        self._run_qml_probe(
            "folder-explorer-resizable-columns",
            """
            def create_folder_explorer_canvas_stub():
                component = QQmlComponent(engine)
                component.setData(
                    b'''
                    import QtQuick 2.15
                    import QtQml 2.15
                    Item {
                        id: canvas
                        objectName: "folderExplorerCanvasStub"
                        property var requests: []
                        property var savedColumnWidths: []
                        property var folderExplorerColumnWidths: {
                            "name": 220,
                            "modified": 160,
                            "type": 120,
                            "size": 70
                        }
                        function setFolderExplorerColumnWidths(widths) {
                            canvas.savedColumnWidths = canvas.savedColumnWidths.concat([widths || ({})]);
                            canvas.folderExplorerColumnWidths = widths || ({});
                            return true;
                        }
                        function folderExplorerDragPayload(path, isFolder) {
                            return {
                                "action_id": "folder_explorer_send_to_corex_path_pointer",
                                "type_id": "io.path_pointer",
                                "properties": {
                                    "path": String(path || ""),
                                    "mode": Boolean(isFolder) ? "folder" : "file"
                                }
                            };
                        }
                        property QtObject canvasActionRouter: QtObject {
                            function folderExplorerActionId(command) {
                                var map = {
                                    "folder_explorer_list": "folder_explorer_list",
                                    "folder_explorer_navigate": "folder_explorer_navigate",
                                    "folder_explorer_refresh": "folder_explorer_refresh",
                                    "folder_explorer_set_sort": "folder_explorer_set_sort",
                                    "folder_explorer_open": "folder_explorer_open",
                                    "folder_explorer_send_to_corex_path_pointer": "folder_explorer_send_to_corex_path_pointer"
                                };
                                return map[String(command || "")] || String(command || "");
                            }

                            function requestFolderExplorerAction(actionId, payload) {
                                var path = String((payload || {}).path || "C:/Projects/Corex");
                                canvas.requests = canvas.requests.concat([{"action_id": actionId, "payload": payload || ({})}]);
                                return {
                                    "success": true,
                                    "cancelled": false,
                                    "action_id": actionId,
                                    "node_id": String((payload || {}).node_id || ""),
                                    "path": path,
                                    "error": {},
                                    "listing": {
                                        "directory_path": path,
                                        "parent_path": "C:/Projects",
                                        "entries": [
                                            {
                                                "name": "Assets",
                                                "absolute_path": path + "/Assets",
                                                "kind": "folder",
                                                "is_folder": true,
                                                "modified_timestamp": 1710000000,
                                                "extension": "",
                                                "type_label": "File folder",
                                                "size_bytes": -1,
                                                "display_size": ""
                                            }
                                        ],
                                        "sort_key": String((payload || {}).sort_key || "name"),
                                        "reverse": Boolean((payload || {}).reverse),
                                        "filter_text": ""
                                    }
                                };
                            }
                        }
                    }
                    ''',
                    QUrl("folder_explorer_resizable_canvas_stub.qml"),
                )
                if component.status() != QQmlComponent.Status.Ready:
                    errors = "\\n".join(error.toString() for error in component.errors())
                    raise AssertionError(f"Failed to load folder explorer canvas stub:\\n{errors}")
                obj = component.create()
                if obj is None:
                    errors = "\\n".join(error.toString() for error in component.errors())
                    raise AssertionError(f"Failed to instantiate folder explorer canvas stub:\\n{errors}")
                return obj

            def to_variant(value):
                if hasattr(value, "toVariant"):
                    value = value.toVariant()
                if isinstance(value, list):
                    return [to_variant(item) for item in value]
                if isinstance(value, tuple):
                    return tuple(to_variant(item) for item in value)
                if isinstance(value, dict):
                    return {key: to_variant(item) for key, item in value.items()}
                return value

            canvas_stub = create_folder_explorer_canvas_stub()
            payload = node_payload()
            payload["node_id"] = "folder_explorer_resize_test"
            payload["type_id"] = "io.folder_explorer"
            payload["title"] = "Folder Explorer"
            payload["runtime_behavior"] = "passive"
            payload["surface_spec"] = surface_spec_payload_for_values(
                type_id="io.folder_explorer",
                family="standard",
                variant="",
            )
            payload["properties"] = {"current_path": "C:/Projects/Corex"}
            payload["width"] = 600.0
            payload["height"] = 360.0
            payload["surface_metrics"].update({
                "default_width": 600.0,
                "default_height": 360.0,
                "min_width": 360.0,
                "min_height": 260.0,
                "body_left_margin": 8.0,
                "body_right_margin": 8.0,
                "body_top": 30.0,
                "body_height": 320.0,
                "body_bottom_margin": 8.0,
            })

            host = create_component(
                graph_node_host_qml_path,
                {"nodeData": payload, "canvasItem": canvas_stub},
            )
            window = attach_host_to_window(host, 760, 520)
            settle_events(8)

            viewport = named_item(host, "graphNodeViewerViewport")
            name_header = named_item(host, "graphFolderExplorerHeaderCell_name")
            modified_header = named_item(host, "graphFolderExplorerHeaderCell_modified")
            type_header = named_item(host, "graphFolderExplorerHeaderCell_type")
            size_header = named_item(host, "graphFolderExplorerHeaderCell_size")
            name_column = named_item(host, "graphFolderExplorerNameColumn")
            modified_column = named_item(host, "graphFolderExplorerModifiedColumn")
            type_column = named_item(host, "graphFolderExplorerTypeColumn")
            size_column = named_item(host, "graphFolderExplorerSizeColumn")

            initial_name_width = float(name_header.width())
            initial_modified_width = float(modified_header.width())
            assert abs(initial_name_width - float(name_column.width())) < 0.5
            assert abs(initial_modified_width - float(modified_column.width())) < 0.5
            assert abs(float(type_header.width()) - float(type_column.width())) < 0.5
            assert abs(float(size_header.width()) - float(size_column.width())) < 0.5
            assert abs(
                initial_name_width
                + initial_modified_width
                + float(type_header.width())
                + float(size_header.width())
                - float(viewport.width())
            ) < 0.75

            start = item_scene_point(name_header, 0.99, 0.5)
            end = QPoint(start.x() + 30, start.y())
            QTest.mousePress(window, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, start)
            settle_events(2)
            QTest.mouseMove(window, end)
            settle_events(2)
            QTest.mouseRelease(window, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, end)
            settle_events(8)

            after_name_width = float(name_header.width())
            after_modified_width = float(modified_header.width())
            assert after_name_width > initial_name_width + 20.0, (after_name_width, initial_name_width)
            assert after_modified_width < initial_modified_width - 20.0, (
                after_modified_width,
                initial_modified_width,
            )
            assert abs(after_name_width - float(name_column.width())) < 0.5
            assert abs(after_modified_width - float(modified_column.width())) < 0.5
            assert len(to_variant(canvas_stub.property("requests"))) == 1

            saved = to_variant(canvas_stub.property("savedColumnWidths"))
            assert len(saved) == 1
            latest_widths = saved[-1]
            assert latest_widths["name"] > initial_name_width + 20.0
            assert latest_widths["modified"] < initial_modified_width - 20.0
            assert latest_widths["type"] == 120
            assert latest_widths["size"] == 70

            QTest.mouseClick(
                window,
                Qt.MouseButton.LeftButton,
                Qt.KeyboardModifier.NoModifier,
                item_scene_point(modified_header, 0.5, 0.5),
            )
            settle_events(8)

            requests = to_variant(canvas_stub.property("requests"))
            assert len(requests) == 2
            assert requests[-1]["action_id"] == "folder_explorer_set_sort"
            assert requests[-1]["payload"]["sort_key"] == "modified"
            assert len(to_variant(canvas_stub.property("savedColumnWidths"))) == 1

            dispose_host_window(host, window)
            canvas_stub.deleteLater()
            engine.deleteLater()
            app.processEvents()
            """,
        )

    def test_folder_explorer_surface_uses_action_state_without_property_commits(self) -> None:
        self._run_qml_probe(
            "folder-explorer-surface-command-and-transient-state",
            """
            def create_folder_explorer_canvas_stub():
                component = QQmlComponent(engine)
                component.setData(
                    b'''
                    import QtQuick 2.15
                    import QtQml 2.15
                    Item {
                        id: canvas
                        objectName: "folderExplorerCanvasStub"
                        width: 720
                        height: 520
                        property var requests: []
                        property var dropPreviews: []
                        property var pathPointerDrops: []
                        property int clearedDropPreviewCount: 0
                        function isPointInCanvas(screenX, screenY) {
                            return Number(screenX) >= 0 && Number(screenY) >= 0;
                        }
                        function clearLibraryDropPreview() {
                            canvas.clearedDropPreviewCount += 1;
                        }
                        function updatePathPointerDropPreview(screenX, screenY, path, isFolder) {
                            canvas.dropPreviews = canvas.dropPreviews.concat([{
                                "screen_x": Number(screenX || 0),
                                "screen_y": Number(screenY || 0),
                                "path": String(path || ""),
                                "is_folder": Boolean(isFolder)
                            }]);
                        }
                        function performPathPointerDrop(screenX, screenY, path, isFolder) {
                            canvas.pathPointerDrops = canvas.pathPointerDrops.concat([{
                                "screen_x": Number(screenX || 0),
                                "screen_y": Number(screenY || 0),
                                "path": String(path || ""),
                                "is_folder": Boolean(isFolder)
                            }]);
                            return true;
                        }
                        property QtObject canvasActionRouter: QtObject {
                            function folderExplorerActionId(command) {
                                var map = {
                                    "folder_explorer_list": "folder_explorer_list",
                                    "folder_explorer_navigate": "folder_explorer_navigate",
                                    "folder_explorer_refresh": "folder_explorer_refresh",
                                    "folder_explorer_set_sort": "folder_explorer_set_sort",
                                    "folder_explorer_set_search": "folder_explorer_set_search",
                                    "folder_explorer_open": "folder_explorer_open",
                                    "folder_explorer_open_in_new_window": "folder_explorer_open_in_new_window",
                                    "folder_explorer_new_folder": "folder_explorer_new_folder",
                                    "folder_explorer_rename": "folder_explorer_rename",
                                    "folder_explorer_delete": "folder_explorer_delete",
                                    "folder_explorer_cut": "folder_explorer_cut",
                                    "folder_explorer_copy": "folder_explorer_copy",
                                    "folder_explorer_paste": "folder_explorer_paste",
                                    "folder_explorer_copy_path": "folder_explorer_copy_path",
                                    "folder_explorer_properties": "folder_explorer_properties",
                                    "folder_explorer_send_to_corex_path_pointer": "folder_explorer_send_to_corex_path_pointer"
                                };
                                return map[String(command || "")] || String(command || "");
                            }

                            function requestFolderExplorerAction(actionId, payload) {
                                var path = String((payload || {}).path || "C:/Projects/Corex");
                                canvas.requests = canvas.requests.concat([{"action_id": actionId, "payload": payload || ({})}]);
                                return {
                                    "success": true,
                                    "cancelled": false,
                                    "action_id": actionId,
                                    "node_id": String((payload || {}).node_id || ""),
                                    "path": path,
                                    "error": {},
                                    "listing": {
                                        "directory_path": path,
                                        "parent_path": "C:/Projects",
                                        "breadcrumbs": [
                                            {"name": "C:", "absolute_path": "C:"},
                                            {"name": "Projects", "absolute_path": "C:/Projects"},
                                            {"name": "Corex", "absolute_path": "C:/Projects/Corex"}
                                        ],
                                        "entries": [
                                            {
                                                "name": "Assets",
                                                "absolute_path": path + "/Assets",
                                                "kind": "folder",
                                                "is_folder": true,
                                                "modified_timestamp": 1710000000,
                                                "extension": "",
                                                "type_label": "File folder",
                                                "size_bytes": -1,
                                                "display_size": ""
                                            },
                                            {
                                                "name": "report.txt",
                                                "absolute_path": path + "/report.txt",
                                                "kind": "file",
                                                "is_folder": false,
                                                "modified_timestamp": 1710000010,
                                                "extension": ".txt",
                                                "type_label": "TXT File",
                                                "size_bytes": 128,
                                                "display_size": "128 B"
                                            }
                                        ],
                                        "sort_key": String((payload || {}).sort_key || "name"),
                                        "reverse": Boolean((payload || {}).reverse),
                                        "filter_text": String((payload || {}).filter_text || "")
                                    }
                                };
                            }
                        }
                    }
                    ''',
                    QUrl("folder_explorer_canvas_stub.qml"),
                )
                if component.status() != QQmlComponent.Status.Ready:
                    errors = "\\n".join(error.toString() for error in component.errors())
                    raise AssertionError(f"Failed to load folder explorer canvas stub:\\n{errors}")
                obj = component.create()
                if obj is None:
                    errors = "\\n".join(error.toString() for error in component.errors())
                    raise AssertionError(f"Failed to instantiate folder explorer canvas stub:\\n{errors}")
                return obj

            def to_variant(value):
                if hasattr(value, "toVariant"):
                    value = value.toVariant()
                if isinstance(value, list):
                    return [to_variant(item) for item in value]
                if isinstance(value, tuple):
                    return tuple(to_variant(item) for item in value)
                if isinstance(value, dict):
                    return {key: to_variant(item) for key, item in value.items()}
                return value

            canvas_stub = create_folder_explorer_canvas_stub()
            payload = node_payload()
            payload["node_id"] = "folder_explorer_surface_test"
            payload["type_id"] = "io.folder_explorer"
            payload["title"] = "Folder Explorer"
            payload["runtime_behavior"] = "passive"
            payload["surface_spec"] = surface_spec_payload_for_values(
                type_id="io.folder_explorer",
                family="standard",
                variant="",
            )
            payload["properties"] = {"current_path": "C:/Projects/Corex"}
            payload["inline_properties"] = []
            payload["width"] = 560.0
            payload["height"] = 360.0
            payload["surface_metrics"].update({
                "default_width": 560.0,
                "default_height": 360.0,
                "min_width": 360.0,
                "min_height": 260.0,
                "body_left_margin": 8.0,
                "body_right_margin": 8.0,
                "body_top": 30.0,
                "body_height": 320.0,
                "body_bottom_margin": 8.0,
            })

            host = create_component(
                graph_node_host_qml_path,
                {"nodeData": payload, "canvasItem": canvas_stub},
            )
            interactions = []
            commits = []
            actions = []
            host.surfaceControlInteractionStarted.connect(lambda node_id: interactions.append(node_id))
            host.inlinePropertyCommitted.connect(lambda node_id, key, value: commits.append((node_id, key, value)))
            host.nodeActionRequested.connect(lambda node_id, action_id, action_payload: actions.append((node_id, action_id, action_payload)))

            window = attach_host_to_window(host, 720, 520)
            settle_events(6)
            surface = host.findChild(QObject, "graphNativeExplorerSurface")
            assert surface is not None
            entry_rows = named_child_items(host, "graphFolderExplorerEntryRow")
            assert len(entry_rows) >= 2

            drag_payloads = [to_variant(row.property("dragPayload")) for row in entry_rows]
            drag_payload = next(
                payload for payload in drag_payloads
                if payload.get("properties", {}).get("mode") == "file"
            )
            assert drag_payload["action_id"] == "folder_explorer_send_to_corex_path_pointer"
            assert drag_payload["type_id"] == "io.path_pointer"
            assert drag_payload["properties"]["path"].endswith("report.txt")
            assert drag_payload["properties"]["mode"] == "file"

            folder_row = next(
                row for row in entry_rows
                if to_variant(row.property("dragPayload")).get("properties", {}).get("mode") == "folder"
            )
            file_row = next(
                row for row in entry_rows
                if to_variant(row.property("dragPayload")).get("properties", {}).get("mode") == "file"
            )
            def drag_row_to_canvas(row, dx, dy):
                start = item_scene_point(row, 0.25, 0.5)
                mid = QPoint(start.x() + 18, start.y() + 6)
                end = QPoint(start.x() + dx, start.y() + dy)
                QTest.mousePress(window, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, start)
                QTest.mouseMove(window, mid)
                QTest.mouseMove(window, end)
                QTest.mouseRelease(window, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, end)
                settle_events(4)

            drag_row_to_canvas(folder_row, 110, 32)
            drag_row_to_canvas(file_row, 120, 44)

            drop_previews = to_variant(canvas_stub.property("dropPreviews"))
            path_pointer_drops = to_variant(canvas_stub.property("pathPointerDrops"))
            assert len(drop_previews) >= 2
            assert len(path_pointer_drops) == 2
            assert path_pointer_drops[0]["path"].endswith("Assets")
            assert path_pointer_drops[0]["is_folder"] is True
            assert path_pointer_drops[1]["path"].endswith("report.txt")
            assert path_pointer_drops[1]["is_folder"] is False

            requests = to_variant(canvas_stub.property("requests"))
            assert len(requests) == 1
            assert requests[0]["action_id"] == "folder_explorer_list"
            assert interactions == []
            assert commits == []
            assert to_variant(host.property("nodeData"))["properties"] == {"current_path": "C:/Projects/Corex"}
            assert to_variant(actions) == []

            dispose_host_window(host, window)
            canvas_stub.deleteLater()
            engine.deleteLater()
            app.processEvents()
            """,
        )

    def test_standard_host_keeps_port_labels_tied_to_port_handles(self) -> None:
        self._run_qml_probe(
            "port-label-geometry-host",
            """
            payload = node_payload()
            payload["width"] = 320.0
            payload["surface_metrics"]["default_width"] = 320.0
            payload["ports"][0]["label"] = "in"
            payload["ports"][1]["label"] = "out"

            host = create_component(graph_node_host_qml_path, {"nodeData": payload})
            input_dot = named_child_items(host, "graphNodeInputPortDot")[0]
            output_dot = named_child_items(host, "graphNodeOutputPortDot")[0]
            input_label = named_child_items(host, "graphNodeInputPortLabel")[0]
            output_label = named_child_items(host, "graphNodeOutputPortLabel")[0]

            gap = float(host.property("_portLabelGap"))
            max_width = float(host.property("_portLabelMaxWidth"))
            output_implicit_width = float(output_label.property("implicitWidth"))
            input_label_left = input_label.mapToItem(host, QPointF(0.0, 0.0)).x()
            output_label_right = output_label.mapToItem(host, QPointF(float(output_label.width()), 0.0)).x()

            assert abs(input_label_left - (input_dot.x() + input_dot.width() + gap)) < 0.5
            assert abs(output_label_right - (output_dot.x() - gap)) < 0.5
            assert output_label.width() < max_width
            assert abs(output_label.width() - output_implicit_width) < 0.5
            """,
        )

    def test_standard_host_renders_named_settings_groups_without_duplicate_port_labels(self) -> None:
        self._run_qml_probe(
            "named-settings-groups-host",
            """
            from PyQt6.QtCore import QPointF
            from PyQt6.QtGui import QColor
            from PyQt6.QtQml import QQmlProperty
            from PyQt6.QtTest import QTest

            def settings_payload(expanded, surface_family="standard"):
                payload = node_payload(surface_family=surface_family)
                if surface_family == "plot":
                    payload["type_id"] = "plot.scatter"
                    payload["surface_spec"] = surface_spec_payload_for_values(
                        type_id="plot.scatter",
                        family="plot",
                        variant="line",
                    )
                    payload["plot_surface"] = {
                        "plot_type": "line",
                        "embedded_rendering_suppressed": True,
                    }
                content_height = 276.0 if surface_family == "plot" else 88.0
                band_height = 44.0 if expanded else 18.0
                payload["height"] = content_height + band_height
                payload["surface_metrics"]["default_height"] = payload["height"]
                payload["surface_metrics"]["min_height"] = payload["height"]
                payload["inline_properties"] = []
                payload["settings_band"] = {"top": content_height, "height": band_height}
                payload["ports"][0].update({
                    "layout_row": -1,
                    "settings_group_id": "options",
                    "settings_property_key": "message",
                    "data_type_color_token": "settings-control",
                    "flow_state": "default",
                    "handle_visible": expanded,
                    "presentation_anchor": {
                        "x": 0.0,
                        "y": content_height + (31.0 if expanded else 9.0),
                    },
                })
                payload["ports"][1]["layout_row"] = 0
                payload["settings_groups"] = [{
                    "group_id": "options",
                    "label": "Options",
                    "expanded": expanded,
                    "header": {"x": 0.0, "y": content_height, "width": 210.0, "height": 18.0},
                    "aggregate_anchor": {
                        "x": 0.0,
                        "y": content_height + 9.0,
                        "connected_count": 0,
                    },
                    "items": [{
                        "kind": "paired",
                        "port_key": "payload",
                        "property_key": "message",
                        "y": content_height + 18.0,
                        "height": 26.0,
                        "visible": expanded,
                        "property": {
                            "key": "message",
                            "label": "Record",
                            "inline_editor": "toggle",
                            "value": True,
                            "overridden_by_input": False,
                            "input_port_label": "payload",
                        },
                    }],
                }]
                return payload

            collapsed_host = create_component(
                graph_node_host_qml_path,
                {"nodeData": settings_payload(False)},
            )
            collapsed_window = attach_host_to_window(collapsed_host, 360, 240)
            settle_events(5)
            collapsed_layer = collapsed_host.findChild(QObject, "graphNodeSettingsGroupsLayer")
            collapsed_loader = collapsed_host.findChild(QObject, "graphNodeSurfaceLoader")
            aggregate_matches = [
                item
                for item in named_child_items(collapsed_host, "graphNodeSettingsGroupAggregateSocket")
                if str(item.property("groupId")) == "options"
            ]
            collapsed_dots = [
                item
                for item in named_child_items(collapsed_host, "graphNodeInputPortDot")
                if str(item.property("propertyKey")) == "payload"
            ]
            aggregate_notch = next(
                item
                for item in named_child_items(
                    collapsed_host,
                    "graphNodeSettingsGroupAggregateNotch",
                )
                if str(item.property("groupId")) == "options"
            )
            collapsed_chevron = named_child_items(
                collapsed_host,
                "graphNodeSettingsGroupChevron",
            )[0]

            assert collapsed_layer is not None
            assert len(aggregate_matches) == 1, {
                "hostGroups": variant_value(collapsed_host.property("settingsGroups")),
                "layerGroups": variant_value(collapsed_layer.property("settingsGroups")),
                "allSockets": [
                    str(item.property("groupId"))
                    for item in named_child_items(collapsed_host, "graphNodeSettingsGroupAggregateSocket")
                ],
            }
            aggregate = aggregate_matches[0]
            assert collapsed_dots == []
            assert aggregate is not None and bool(aggregate.property("visible"))
            valid_green = QColor("#67D487")
            aggregate_center = aggregate.mapToItem(
                collapsed_host,
                QPointF(float(aggregate.width()) * 0.5, float(aggregate.height()) * 0.5),
            )
            notch_center = aggregate_notch.mapToItem(collapsed_host, QPointF(0.0, 9.0))
            assert abs(aggregate_center.x()) < 0.01
            assert abs(notch_center.x()) < 0.01
            assert bool(aggregate_notch.property("visible"))
            assert abs(float(aggregate_notch.width()) - 9.0) < 0.01
            assert abs(float(aggregate_notch.height()) - 18.0) < 0.01
            assert aggregate_notch.property("sourceSize").width() == 54
            assert aggregate_notch.property("sourceSize").height() == 108
            assert abs(float(aggregate.width()) - 10.0) < 0.01
            neutral_surface = QColor(collapsed_host.property("themeSurfaceColor"))
            assert QColor(aggregate.property("color")).rgba() == neutral_surface.rgba(), (
                QColor(aggregate.property("color")).name(),
                neutral_surface.name(),
            )
            assert QColor(QQmlProperty.read(aggregate, "border.color")).rgba() == valid_green.rgba()
            assert abs(float(QQmlProperty.read(aggregate, "border.width")) - 1.6) < 0.01
            collapsed_decoration = QColor(collapsed_host.property("inlineDrivenTextColor"))
            assert str(collapsed_chevron.property("direction")) == "right"
            assert not bool(collapsed_chevron.property("expandedState"))
            assert abs(float(collapsed_chevron.width()) - 12.0) < 0.01
            assert QColor(collapsed_chevron.property("color")).alpha() == 0
            assert QColor(QQmlProperty.read(collapsed_chevron, "border.color")).rgba() == collapsed_decoration.rgba()
            assert abs(float(QQmlProperty.read(collapsed_chevron, "border.width")) - 1.2) < 0.01
            assert abs(float(collapsed_loader.height()) - 88.0) < 0.5
            assert len(variant_list(collapsed_layer.property("embeddedInteractiveRects"))) == 1

            expanded_host = create_component(
                graph_node_host_qml_path,
                {"nodeData": settings_payload(True)},
            )
            expanded_window = attach_host_to_window(expanded_host, 360, 260)
            settle_events(5)
            expanded_layer = expanded_host.findChild(QObject, "graphNodeSettingsGroupsLayer")
            expanded_loader = expanded_host.findChild(QObject, "graphNodeSurfaceLoader")
            expanded_row = named_item(expanded_host, "graphNodeInputPortRow", "payload")
            expanded_dot = named_item(expanded_host, "graphNodeInputPortDot", "payload")
            expanded_notch = named_item(expanded_host, "graphNodeInputPortNotch", "payload")
            port_label = named_item(expanded_host, "graphNodeInputPortLabel", "payload")
            property_labels = named_child_items(expanded_host, "graphNodeInlinePropertyLabel")
            group_divider = named_child_items(expanded_host, "graphNodeSettingsGroupDivider")[0]
            group_chevron = named_child_items(expanded_host, "graphNodeSettingsGroupChevron")[0]

            assert expanded_layer is not None
            assert expanded_row is not None and bool(expanded_row.property("visible"))
            assert expanded_dot is not None and bool(expanded_dot.property("visible"))
            assert expanded_notch is not None and bool(expanded_notch.property("visible"))
            assert QColor(QQmlProperty.read(expanded_dot, "border.color")).rgba() == valid_green.rgba()
            assert QColor(QQmlProperty.read(expanded_dot, "border.color")).name() != QColor("#7AA8FF").name()
            assert port_label is not None and not bool(port_label.property("visible"))
            assert len(property_labels) == 1
            assert str(property_labels[0].property("text")) == "Record"
            assert abs(float(expanded_loader.height()) - 88.0) < 0.5
            assert len(variant_list(expanded_layer.property("embeddedInteractiveRects"))) >= 2
            neutral_decoration = QColor(expanded_host.property("inlineDrivenTextColor"))
            assert QColor(group_divider.property("color")).rgba() == neutral_decoration.rgba()
            assert abs(float(group_divider.property("opacity")) - 0.38) < 0.01
            assert QColor(group_chevron.property("color")).rgba() == neutral_decoration.rgba()
            assert str(group_chevron.property("direction")) == "down"
            assert bool(group_chevron.property("expandedState"))
            assert abs(float(QQmlProperty.read(group_chevron, "border.width"))) < 0.01
            group_chevron_glyph = named_child_items(
                expanded_host,
                "graphNodeSettingsGroupChevronGlyph",
            )[0]
            assert QColor(group_chevron_glyph.property("strokeColor")).name() == "#ffffff"

            requests = []
            expanded_host.settingsGroupExpansionRequested.connect(
                lambda node_id, group_id, value: requests.append((node_id, group_id, value))
            )
            header = next(
                item
                for item in named_child_items(expanded_host, "graphNodeSettingsGroupHeader")
                if str(item.property("groupId")) == "options"
            )
            header_y_before = header.mapToItem(expanded_host, QPointF(0.0, 0.0)).y()
            expanded_row_y_before = expanded_row.mapToItem(expanded_host, QPointF(0.0, 0.0)).y()
            expanded_host.setProperty("_liveHeight", 172.0)
            expanded_host.setProperty("_liveGeometryActive", True)
            settle_events(3)
            header_y_after = header.mapToItem(expanded_host, QPointF(0.0, 0.0)).y()
            expanded_row_y_after = expanded_row.mapToItem(expanded_host, QPointF(0.0, 0.0)).y()
            assert abs(float(expanded_host.height()) - 172.0) < 0.5
            assert abs((header_y_after - header_y_before) - 40.0) < 0.5
            assert abs((expanded_row_y_after - expanded_row_y_before) - 40.0) < 0.5
            assert abs((header_y_after + 44.0) - float(expanded_host.height())) < 0.5
            assert abs(float(expanded_loader.height()) - 128.0) < 0.5

            point = header.mapToScene(QPointF(header.width() * 0.5, header.height() * 0.5))
            QTest.mouseClick(
                expanded_window,
                Qt.MouseButton.LeftButton,
                Qt.KeyboardModifier.NoModifier,
                point.toPoint(),
            )
            settle_events(3)
            assert requests == [("node_surface_host_test", "options", False)], requests

            requests.clear()
            header_toggle = named_child_items(
                expanded_host,
                "graphNodeSettingsGroupToggleArea",
            )[0]
            header_toggle.forceActiveFocus()
            QTest.keyClick(
                expanded_window,
                Qt.Key.Key_Space,
                Qt.KeyboardModifier.NoModifier,
            )
            settle_events(3)
            assert requests == [("node_surface_host_test", "options", False)], requests

            locked_payload = settings_payload(True)
            locked_payload["read_only"] = True
            locked_host = create_component(
                graph_node_host_qml_path,
                {"nodeData": locked_payload},
            )
            locked_window = attach_host_to_window(locked_host, 360, 260)
            settle_events(3)
            locked_layer = locked_host.findChild(QObject, "graphNodeSettingsGroupsLayer")
            locked_property_layer = named_child_items(
                locked_host,
                "graphNodeSettingsGroupInlineProperty",
            )[0]
            assert not bool(locked_property_layer.property("enabled"))
            assert variant_list(locked_layer.property("embeddedInteractiveRects")) == []

            plot_host = create_component(
                graph_node_host_qml_path,
                {"nodeData": settings_payload(True, "plot")},
            )
            plot_window = attach_host_to_window(plot_host, 360, 280)
            settle_events(5)
            plot_loader = plot_host.findChild(QObject, "graphNodeSurfaceLoader")
            plot_surface = plot_host.findChild(QObject, "graphNodePlotSurface")
            plot_header = next(
                item
                for item in named_child_items(plot_host, "graphNodeSettingsGroupHeader")
                if str(item.property("groupId")) == "options"
            )
            plot_output = named_item(plot_host, "graphNodeOutputPortDot", "result")
            assert plot_surface is not None, "plot surface did not load"
            plot_content_height = float(plot_host.height()) - 44.0
            assert abs(float(plot_loader.height()) - plot_content_height) < 0.5
            plot_header_y = plot_header.mapToItem(plot_host, QPointF(0.0, 0.0)).y()
            plot_output_y = plot_output.mapToItem(plot_host, QPointF(0.0, 0.0)).y()
            assert abs(plot_header_y - plot_content_height) < 0.5
            assert plot_output_y < plot_content_height, ("output", plot_output_y)

            dispose_host_window(collapsed_host, collapsed_window)
            dispose_host_window(expanded_host, expanded_window)
            dispose_host_window(locked_host, locked_window)
            dispose_host_window(plot_host, plot_window)
            engine.deleteLater()
            app.processEvents()
            """,
        )

    def test_content_sized_nodes_keep_settings_and_connected_ports_aligned(self) -> None:
        body = '''
            from PyQt6.QtGui import QFont, QFontDatabase
            from PyQt6.QtCore import pyqtSignal
            from PyQt6.QtTest import QTest

            previous_font = app.font()
            font_ids = [QFontDatabase.addApplicationFont("C:/Windows/Fonts/" + filename)
                for filename in ("segoeui.ttf", "segoeuib.ttf")]
            assert all(font_id >= 0 for font_id in font_ids)
            app.setFont(QFont("Segoe UI", 9))
            class GraphicsSource(QObject):
                graphics_preferences_changed = pyqtSignal()
                graphics_graph_label_pixel_size = 17
                graphics_node_title_icon_pixel_size = 31
                graphics_show_port_labels = True

            graphics = GraphicsSource()
            model = GraphModel()
            registry = build_default_registry()
            scene = GraphSceneBridge()
            scene.bind_graphics_preferences_source(graphics)
            workspace = model.active_workspace
            scene.set_workspace(model, registry, workspace.workspace_id)
            signal_id = scene.add_node_from_type("plot.signal", -380, -300)
            media_id = scene.add_node_from_type("media.panel", 100, -300)
            signal = workspace.nodes[signal_id]
            signal.custom_width, signal.custom_height = 980, 1600
            scene.refresh_workspace_from_model(workspace.workspace_id)
            edge_id = scene.add_edge(signal_id, "image", media_id, "source")
            view = ViewportBridge()
            view.set_viewport_size(1000, 1000)
            canvas = create_component(graph_canvas_qml_path, {
                "sceneBridge": scene, "viewBridge": view, "width": 1000, "height": 1000,
                "mainWindowBridge": graphics,
            })
            window = attach_host_to_window(canvas, 1000, 1000)
            try:
                QTest.qWait(80)

                def host(node_id):
                    return next(item for item in named_child_items(canvas, "graphNodeCard")
                        if variant_value(item.property("nodeData"))["node_id"] == node_id)

                def assert_geometry():
                    card = host(signal_id)
                    payload = variant_value(card.property("nodeData"))
                    metrics = variant_value(card.property("surfaceMetrics"))
                    assert metrics and metrics["port_height"] > 0
                    assert abs(card.width() - payload["surface_metrics"]["default_width"]) < 0.1
                    assert abs(card.height() - payload["surface_metrics"]["default_height"]) < 0.1
                    first_group = named_child_items(card, "graphNodeSettingsGroupHeader")[0]
                    group_top = first_group.mapToItem(card, QPointF(0, 0)).y()
                    assert abs(group_top - (metrics["port_top"] + metrics["port_height"]
                        + metrics["body_bottom_margin"])) < 0.1, (group_top, metrics)
                    for label in named_child_items(card, "graphNodeSettingsGroupLabel"):
                        assert label.isVisible()
                        assert label.width() + 40 <= card.width()
                    output = named_item(card, "graphNodeOutputPortDot", "image")
                    center = output.mapToItem(card, QPointF(output.width()/2, output.height()/2))
                    assert abs(center.x() - card.width()) < 0.1
                    edges = {item["edge_id"]: item for item in scene.edges_model}
                    edge = edges[edge_id]
                    assert edge["source_anchor_bounds"]["width"] == card.width()
                    port = next(port for port in payload["ports"] if port["key"] == "image")
                    point = variant_value(canvas._scenePortPoint(payload, port, -1, 0))
                    assert abs(point["x"] - (payload["x"] + center.x())) < 0.1
                    assert abs(point["y"] - (payload["y"] + center.y())) < 0.1
                    target = host(media_id)
                    target_payload = variant_value(target.property("nodeData"))
                    source = named_item(target, "graphNodeInputPortDot", "source")
                    target_center = source.mapToItem(target, QPointF(source.width()/2, source.height()/2))
                    assert abs(edge["ty"] - (target_payload["y"] + target_center.y())) < 0.1
                    edge_layer = canvas.findChild(QObject, "graphCanvasEdgeLayer")
                    rendered = variant_value(edge_layer.edgeEndpointScenePoint(edge_id, "target"))
                    assert abs(rendered["x"] - (target_payload["x"] + target_center.x())) < 0.1
                    assert abs(rendered["y"] - (target_payload["y"] + target_center.y())) < 0.1, (
                        "media-rendered-endpoint", rendered, target_center)
                    return card, first_group

                card, header = assert_geometry()
                collapsed_size = (card.width(), card.height())
                for _ in range(2):
                    mouse_click(window, item_scene_point(header))
                    QTest.qWait(240)
                    card, header = assert_geometry()
                    assert "general_options" in signal.expanded_settings_group_ids, signal.expanded_settings_group_ids
                    assert card.height() > collapsed_size[1], (card.height(), collapsed_size)
                    for label in named_child_items(card, "graphNodeInlinePropertyLabel"):
                        if label.isVisible():
                            assert not label.property("truncated"), label.property("text")
                    for editor in named_child_items(card, "graphNodeInlineColorEditor"):
                        if editor.isVisible() and graphics.graphics_graph_label_pixel_size == 17:
                            assert editor.width() > 60, (editor.objectName(), editor.width())
                    mouse_click(window, item_scene_point(header))
                    QTest.qWait(240)
                    card, header = assert_geometry()
                    assert (card.width(), card.height()) == collapsed_size, ((card.width(), card.height()), collapsed_size)
            finally:
                dispose_host_window(canvas, window)
                app.setFont(previous_font)
                for font_id in font_ids:
                    QFontDatabase.removeApplicationFont(font_id)
            '''
        for pixel_size in (10, 17, 32):
            with self.subTest(graph_label_pixel_size=pixel_size):
                self._run_qml_probe(
                    "content-sized-node-canvas-layout",
                    body.replace("graphics_graph_label_pixel_size = 17",
                                 f"graphics_graph_label_pixel_size = {pixel_size}"),
                )

    def test_graph_canvas_settings_resize_animates_clipped_content_and_connected_edges(self) -> None:
        self._run_qml_probe(
            "graph-canvas-settings-size-animation",
            '''
            from PyQt6.QtGui import QFont, QFontDatabase
            from PyQt6.QtCore import pyqtSignal
            from PyQt6.QtTest import QTest

            font_id = QFontDatabase.addApplicationFont("C:/Windows/Fonts/segoeui.ttf")
            assert font_id >= 0
            previous_font = app.font()
            app.setFont(QFont("Segoe UI", 9))

            class GraphicsSource(QObject):
                graphics_preferences_changed = pyqtSignal()
                graphics_lightweight_canvas = False
                graphics_graph_label_pixel_size = 17
                graphics_show_port_labels = True

            graphics = GraphicsSource()
            model = GraphModel()
            registry = build_default_registry()
            scene = GraphSceneBridge()
            scene.bind_graphics_preferences_source(graphics)
            workspace = model.active_workspace
            scene.set_workspace(model, registry, workspace.workspace_id)
            signal_id = scene.add_node_from_type("plot.signal", -330, -390)
            media_id = scene.add_node_from_type("media.panel", 270, -390)
            source_id = scene.add_node_from_type("core.constant", -560, 350)
            output_edge = scene.add_edge(signal_id, "image", media_id, "source")
            input_edge = scene.add_edge(source_id, "value", signal_id, "show_legend")
            second_input_edge = scene.add_edge(source_id, "value", signal_id, "labels")
            assert output_edge and input_edge and second_input_edge
            node = workspace.nodes[signal_id]
            persisted_size = (node.custom_width, node.custom_height)
            view = ViewportBridge()
            view.set_viewport_size(1400, 1100)
            canvas = create_component(graph_canvas_qml_path, {
                "sceneBridge": scene, "viewBridge": view, "width": 1400, "height": 1100,
                "mainWindowBridge": graphics,
            })
            window = attach_host_to_window(canvas, 1400, 1100)
            try:
                QTest.qWait(80)
                card = next(item for item in named_child_items(canvas, "graphNodeCard")
                    if variant_value(item.property("nodeData"))["node_id"] == signal_id)
                edge_layer = canvas.findChild(QObject, "graphCanvasEdgeLayer")

                def header(group_id="general_options"):
                    return next(item for item in named_child_items(card, "graphNodeSettingsGroupHeader")
                        if item.property("groupId") == group_id)

                def click_header():
                    mouse_click(window, item_scene_point(header()))

                def group_top(group_id="general_options"):
                    return header(group_id).mapToItem(card, QPointF(0, 0)).y()

                def assert_live_geometry(check_pixels=True):
                    # The immutable rendered frame and its item geometry are
                    # sampled together, without advancing the event loop.
                    frame = window.grabWindow() if check_pixels else None
                    overlay_map = variant_value(canvas.property("liveNodeGeometry"))
                    assert signal_id in overlay_map, (
                        "missing-live-overlay", check_pixels, card.property("settingsGroupAnimationRunning"),
                        card.property("_settingsGroupAnimationArmed"), card.property("_settingsGroupGeometryNodeId"),
                        card.width(), card.height(), node.expanded_settings_group_ids, overlay_map)
                    overlay = overlay_map[signal_id]
                    assert overlay["settingsGroupAnimation"]
                    assert abs(overlay["width"] - card.width()) < 0.1
                    assert abs(overlay["height"] - card.height()) < 0.1
                    assert not card.property("_liveGeometryActive")
                    payload = variant_value(card.property("nodeData"))
                    node_map = variant_value(edge_layer._nodeMap())
                    edges = {edge["edge_id"]: edge for edge in scene.edges_model}
                    for edge_id, prefix, port_key in (
                        (output_edge, "s", "image"), (input_edge, "t", "show_legend"),
                        (second_input_edge, "t", "labels"),
                    ):
                        geometry = variant_value(edge_layer._edgeGeometry(edges[edge_id], node_map))
                        port = next((item for item in named_child_items(card,
                            "graphNodeOutputPortDot" if prefix == "s" else "graphNodeInputPortDot")
                            if item.property("propertyKey") == port_key), None)
                        assert port is not None and port.isVisible(), (port_key, node.expanded_settings_group_ids)
                        center = port.mapToItem(card, QPointF(port.width()/2, port.height()/2))
                        rendered = variant_value(edge_layer.edgeEndpointScenePoint(
                            edge_id, "source" if prefix == "s" else "target"))
                        assert abs(rendered["x"] - (payload["x"] + center.x())) < 0.1, (
                            "rendered-x", port_key, rendered, center, edge_layer.property("_activeEdgeRendererKind"))
                        assert abs(rendered["y"] - (payload["y"] + center.y())) < 0.1, (
                            "rendered-y", port_key, rendered, center, edge_layer.property("_activeEdgeRendererKind"))
                        if prefix == "t" and frame is not None:
                            t = 0.94
                            curve_x = ((1-t)**3*geometry["sx"] + 3*(1-t)**2*t*geometry["c1x"]
                                + 3*(1-t)*t*t*geometry["c2x"] + t**3*geometry["tx"])
                            curve_y = ((1-t)**3*geometry["sy"] + 3*(1-t)**2*t*geometry["c1y"]
                                + 3*(1-t)*t*t*geometry["c2y"] + t**3*geometry["ty"])
                            screen = QPointF(edge_layer.sceneToScreenX(curve_x), edge_layer.sceneToScreenY(curve_y))
                            scale = frame.width() / window.width()
                            pixels = [frame.pixelColor(round((screen.x() + dx)*scale),
                                round((screen.y() + dy)*scale))
                                for dx in range(-1, 2) for dy in range(-1, 2)]
                            assert any(min(color.red(), color.green(), color.blue()) > 110
                                and max(color.red(), color.green(), color.blue())
                                    - min(color.red(), color.green(), color.blue()) < 50
                                for color in pixels), ("painted-wire-at-socket", port_key, screen)
                        if edge_layer.property("_activeEdgeRendererKind") == "retained_qml":
                            retained = canvas.findChild(QObject, "graphCanvasEdgeRetainedLayer")
                            entries = []
                            pending = [retained]
                            while pending:
                                item = pending.pop()
                                pending.extend(item.childItems())
                                entries.append(variant_value(item.property("edgeEntry")))
                            entry = next(value for value in entries
                                if isinstance(value, dict) and value.get("edgeId") == edge_id)
                            screen = port.mapToScene(QPointF(port.width()/2, port.height()/2))
                            assert abs(entry[prefix + "x"] - screen.x()) < 0.1
                            assert abs(entry[prefix + "y"] - screen.y()) < 0.1
                        assert 0 <= center.y() <= card.height(), (port_key, center.y(), card.height())
                        assert abs(geometry[prefix + "x"] - (payload["x"] + center.x())) < 0.1
                        assert abs(geometry[prefix + "y"] - (payload["y"] + center.y())) < 0.1, (
                            port_key, geometry, center.y(), overlay)

                def assert_finished():
                    QTest.qWait(220)
                    assert not card.property("settingsGroupAnimationRunning")
                    assert not card.property("_settingsGroupAnimationArmed")
                    assert card.property("_settingsGroupGeometryNodeId") == ""
                    assert signal_id not in variant_value(canvas.property("liveNodeGeometry"))
                    payload = variant_value(card.property("nodeData"))
                    assert abs(card.width() - payload["width"]) < 0.1
                    assert abs(card.height() - payload["height"]) < 0.1
                    assert (node.custom_width, node.custom_height) == persisted_size
                    if not node.expanded_settings_group_ids:
                        assert not any(item.property("propertyKey") in ("show_legend", "labels")
                            for item in named_child_items(card, "graphNodeInputPortDot"))

                collapsed = (card.width(), card.height())
                first_header_top = group_top()
                second_header_top = group_top("signal_plot_options")
                assert not card.property("settingsGroupAnimationRunning")
                click_header()
                target = variant_value(card.property("nodeData"))
                QTest.qWait(60)
                assert collapsed[0] < card.width() < target["width"], (collapsed, card.width(), target["width"])
                assert collapsed[1] < card.height() < target["height"]
                assert abs(group_top() - first_header_top) < 0.1
                final_second_top = next(group["header"]["y"] for group in target["settings_groups"]
                    if group["group_id"] == "signal_plot_options")
                assert second_header_top < group_top("signal_plot_options") < final_second_top
                assert_live_geometry()
                clip = card.findChild(QObject, "graphNodePortsAnimationClip")
                assert clip.property("clip") and abs(clip.height() - card.height()) < 0.1
                default_editor = named_item(card, "graphNodeInputDefaultProperty", "width")
                assert default_editor is not None and not default_editor.isEnabled()
                for editor in named_child_items(card, "graphNodeInputDefaultProperty"):
                    if editor.isVisible() and editor.height() > 0:
                        bottom = editor.mapToItem(card, QPointF(0, editor.height())).y()
                        assert bottom <= group_top("signal_plot_options") + 0.1
                ancestor = default_editor.parentItem()
                while ancestor is not None and ancestor is not clip:
                    ancestor = ancestor.parentItem()
                assert ancestor is clip
                settings_clip = card.findChild(QObject, "graphNodeSettingsGroupsLayer")
                assert settings_clip.property("clip")
                assert_finished()

                expanded = (card.width(), card.height())
                click_header()
                QTest.qWait(60)
                assert collapsed[0] < card.width() < expanded[0]
                assert collapsed[1] < card.height() < expanded[1]
                assert abs(group_top() - first_header_top) < 0.1
                assert second_header_top < group_top("signal_plot_options") < final_second_top
                assert_live_geometry()
                assert_finished()

                click_header()
                QTest.qWait(45)
                click_header()
                assert collapsed[0] < card.width() <= card.property("_settingsGroupStartWidth")
                assert collapsed[1] < card.height() <= card.property("_settingsGroupStartHeight")
                assert_finished()
                assert (card.width(), card.height()) == collapsed

                click_header()
                assert_finished()
                click_header()
                QTest.qWait(45)
                click_header()
                captured_centers = variant_value(card.property("_settingsGroupStartPorts"))
                assert card.property("settingsGroupAnimationRunning")
                for key in ("show_legend", "labels"):
                    port = named_item(card, "graphNodeInputPortDot", key)
                    center = port.mapToItem(card, QPointF(port.width()/2, port.height()/2)).y()
                    assert center >= captured_centers[key]
                assert_live_geometry(check_pixels=False)
                assert_finished()
                click_header()
                QTest.qWait(40)
                card.resizePreviewChanged.emit(signal_id, -330.0, -390.0, 550.0, 850.0, True)
                app.processEvents()
                assert not card.property("settingsGroupAnimationRunning")
                assert card.property("_liveGeometryActive")
                manual = variant_value(canvas.property("liveNodeGeometry"))[signal_id]
                assert "settingsGroupAnimation" not in manual
                assert (card.width(), card.height()) == (550.0, 850.0)
                card.resizePreviewChanged.emit(signal_id, -330.0, -390.0, 550.0, 850.0, False)
                assert_finished()

                click_header()
                QTest.qWait(45)
                graphics.graphics_lightweight_canvas = True
                graphics.graphics_preferences_changed.emit()
                app.processEvents()
                assert not card.property("settingsGroupAnimationRunning"), (
                    card.property("settingsGroupAnimationsEnabled"),
                    card.property("_settingsGroupAnimationArmed"),
                    card.width(), card.height())
                assert_finished()
                click_header()
                assert not card.property("settingsGroupAnimationRunning")
                assert_finished()
                assert (card.width(), card.height()) == collapsed

                graphics.graphics_lightweight_canvas = False
                graphics.graphics_preferences_changed.emit()
                click_header()
                QTest.qWait(40)
                assert_live_geometry()
                card.cancelSettingsGroupAnimation()
                assert_finished()

                graphics.graphics_keep_expanded_node_width = True
                graphics.graphics_preferences_changed.emit()
                app.processEvents()
                assert not card.property("settingsGroupAnimationRunning")
                stable_width = card.width()
                for _ in range(2):
                    click_header()
                    QTest.qWait(60)
                    assert card.property("settingsGroupAnimationRunning")
                    assert abs(card.width() - stable_width) < 0.1
                    assert_live_geometry()
                    assert_finished()

                scene.set_node_property(signal_id, "labels", ["First", "Second"])
                app.processEvents()
                assert not card.property("settingsGroupAnimationRunning")
                assert signal_id not in variant_value(canvas.property("liveNodeGeometry"))

                scene.clear_selection()
                click_header()
                QTest.qWait(60)
                assert_live_geometry()
                assert edge_layer.property("_activeEdgeRendererKind") == "retained_qml"
                assert_finished()
                click_header()
                assert_finished()

                click_header()
                QTest.qWait(40)
                assert signal_id in variant_value(canvas.property("liveNodeGeometry"))
                scene.remove_node(signal_id)
                QTest.qWait(80)
                assert signal_id not in variant_value(canvas.property("liveNodeGeometry"))
            finally:
                dispose_host_window(canvas, window)
                app.setFont(previous_font)
                QFontDatabase.removeApplicationFont(font_id)
            ''',
        )

    def test_signal_plot_title_and_shared_settings_group_animation_are_interactive(self) -> None:
        self._run_qml_probe(
            "signal-plot-shared-settings-animation",
            """
            import copy
            from PyQt6.QtCore import QPointF, Qt
            from PyQt6.QtTest import QTest
            from ea_node_editor.graph.model import GraphModel
            from ea_node_editor.nodes.bootstrap import build_default_registry
            from ea_node_editor.ui_qml.graph_geometry.standard_metrics import standard_inline_property_row_height
            from ea_node_editor.ui_qml.graph_scene_payload.builder import GraphScenePayloadBuilder

            registry = build_default_registry()
            model = GraphModel()
            workspace = model.active_workspace
            node = model.add_node(
                workspace.workspace_id,
                "plot.signal",
                "Signal Plot",
                0.0,
                0.0,
                properties={"colors": ["#11223344"]},
            )
            node.title = ""
            builder = GraphScenePayloadBuilder()

            def signal_payload():
                return builder.rebuild_models(
                    model=model,
                    registry=registry,
                    workspace_id=workspace.workspace_id,
                    scope_path=(),
                    graph_theme_bridge=None,
                )[0][0]

            collapsed_payload = signal_payload()
            host = create_component(
                graph_node_host_qml_path,
                {
                    "nodeData": collapsed_payload,
                    "settingsGroupAnimationsEnabled": True,
                },
            )
            window = attach_host_to_window(host, 1000, 940)
            settle_events(5)

            title = named_child_items(host, "graphNodeTitle")[0]
            assert bool(title.property("visible"))
            assert str(title.property("text")) == "Signal Plot"
            assert float(title.width()) > 0.0 and float(title.height()) > 0.0

            def apply_expansion(_node_id, group_id, expanded):
                host.beginSettingsGroupAnimation()
                current = set(node.expanded_settings_group_ids)
                if expanded:
                    current.add(str(group_id))
                else:
                    current.discard(str(group_id))
                node.expanded_settings_group_ids = tuple(
                    group.group_id
                    for group in registry.get_spec("plot.signal").settings_groups
                    if group.group_id in current
                )
                host.setProperty("nodeData", signal_payload())

            host.settingsGroupExpansionRequested.connect(apply_expansion)

            def group_header(group_id):
                return next(
                    item
                    for item in named_child_items(host, "graphNodeSettingsGroupHeader")
                    if str(item.property("groupId")) == group_id
                )

            def assert_settings_bottom_clearance(target_host):
                candidates = (
                    named_child_items(target_host, "graphNodeSettingsGroupHeader")
                    + named_child_items(target_host, "graphNodeSettingsGroupInlineProperty")
                )
                visible_items = [item for item in candidates if item.isVisible()]
                content_bottom = max(
                    item.mapToItem(target_host, QPointF(0.0, item.height())).y()
                    for item in visible_items
                )
                assert float(target_host.height()) - content_bottom >= 17.5, (
                    "settings-bottom-clearance",
                    target_host.height(),
                    content_bottom,
                )

            def click_item(item):
                point = item.mapToScene(QPointF(item.width() * 0.5, item.height() * 0.5))
                QTest.mouseClick(
                    window,
                    Qt.MouseButton.LeftButton,
                    Qt.KeyboardModifier.NoModifier,
                    point.toPoint(),
                )
                settle_events(1)

            collapsed_height = float(host.height())
            assert_settings_bottom_clearance(host)
            general_header = group_header("general_options")
            click_item(general_header)
            assert node.expanded_settings_group_ids == ("general_options",)
            assert bool(host.property("settingsGroupAnimationRunning"))
            general_target = float(variant_value(host.property("nodeData"))["height"])
            QTest.qWait(60)
            settle_events(2)
            general_mid = float(host.height())
            assert collapsed_height < general_mid < general_target
            moving_header = group_header("general_options")
            moving_header_bottom = moving_header.mapToItem(
                host, QPointF(0.0, moving_header.height())
            ).y()
            assert moving_header_bottom <= float(host.height()) + 0.5
            QTest.qWait(180)
            settle_events(3)
            assert not bool(host.property("settingsGroupAnimationRunning"))
            assert abs(float(host.height()) - general_target) < 0.75
            assert_settings_bottom_clearance(host)
            width_slider = named_item(host, "graphNodeInlineSliderEditor", "width")
            list_candidates = named_child_items(host, "graphNodeInlineListEditor")
            labels_list = next(
                (
                    item for item in list_candidates
                    if str(item.property("propertyKey")) == "labels"
                ),
                None,
            )
            assert width_slider is not None and bool(width_slider.property("visible"))
            assert labels_list is not None and bool(labels_list.property("visible")), [
                (str(item.property("propertyKey")), bool(item.property("visible")))
                for item in list_candidates
            ]
            assert bool(width_slider.property("enabled"))
            expected_labels_height = standard_inline_property_row_height(
                "list", graph_label_pixel_size=10, list_value=[]
            )
            general_payload = next(
                group
                for group in variant_value(host.property("nodeData"))["settings_groups"]
                if group["group_id"] == "general_options"
            )
            labels_payload = next(
                item for item in general_payload["items"] if item["port_key"] == "labels"
            )
            assert abs(float(labels_payload["height"]) - expected_labels_height) < 0.5, (
                "labels-payload-height",
                labels_payload,
            )
            assert abs(float(labels_list.height()) + float(host.property("_inlineRowHeight")) - expected_labels_height) < 0.5, (
                "labels-row-height",
                labels_list.height(),
                host.property("_inlineRowHeight"),
                expected_labels_height,
            )
            labels_view = labels_list.findChild(QObject, "graphSurfaceListView")
            labels_add = labels_list.findChild(QObject, "graphSurfaceListAddButton")
            assert labels_view is not None and labels_add is not None, "labels-list-children"
            assert abs(float(labels_view.height())) < 0.5, ("labels-list-gap", labels_view.height())
            assert abs(float(labels_add.y()) - 4.0) < 0.5, ("labels-add-position", labels_add.y())
            labels_top = labels_list.mapToItem(host, QPointF(0.0, 0.0)).y()
            labels_bottom = labels_list.mapToItem(
                host, QPointF(0.0, labels_list.height())
            ).y()
            show_legend_payload = next(
                item for item in general_payload["items"] if item["port_key"] == "show_legend"
            )
            assert abs(labels_top - (float(labels_payload["y"]) + float(host.property("_inlineRowHeight")))) < 0.5, (
                "labels-editor-top",
                labels_top,
                labels_payload,
            )
            assert abs(labels_bottom - float(show_legend_payload["y"])) < 0.5, (
                "labels-following-gap",
                labels_bottom,
                show_legend_payload,
            )

            click_item(group_header("general_options"))
            assert node.expanded_settings_group_ids == (), ("general-collapse-state", node.expanded_settings_group_ids)
            assert bool(host.property("settingsGroupAnimationRunning")), "general-collapse-animation"
            QTest.qWait(60)
            settle_events(2)
            collapse_mid = float(host.height())
            assert collapsed_height < collapse_mid < general_target, ("general-collapse-mid", collapsed_height, collapse_mid, general_target)
            QTest.qWait(180)
            settle_events(3)
            assert abs(float(host.height()) - collapsed_height) < 0.75, ("general-collapse-final", host.height(), collapsed_height)

            click_item(group_header("signal_plot_options"))
            assert node.expanded_settings_group_ids == ("signal_plot_options",), ("signal-expand-state", node.expanded_settings_group_ids)
            signal_target = float(variant_value(host.property("nodeData"))["height"])
            QTest.qWait(220)
            settle_events(3)
            assert abs(float(host.height()) - signal_target) < 0.75, ("signal-expand-final", host.height(), signal_target)
            assert_settings_bottom_clearance(host)
            interval = named_item(host, "graphNodeInlineIntervalFieldsEditor", "x_axis_interval")
            colors_list = named_item(host, "graphNodeInlineListEditor", "colors")
            auto_button = interval.findChild(QObject, "graphSurfaceIntervalAutoButton")
            assert interval is not None and auto_button is not None, "signal-interval-controls"
            assert bool(interval.property("visible")) and bool(auto_button.property("enabled")), ("signal-interval-usable", interval.property("visible"), auto_button.property("enabled"))
            assert colors_list is not None and bool(colors_list.property("visible")), "signal-colors-list"
            colors_view = colors_list.findChild(QObject, "graphSurfaceListView")
            colors_add = colors_list.findChild(QObject, "graphSurfaceListAddButton")
            assert colors_view is not None and colors_add is not None, "colors-list-children"
            assert abs(float(colors_view.height()) - 28.0) < 0.5, ("colors-list-height", colors_view.height())
            assert abs(float(colors_add.y()) - 32.0) < 0.5, ("colors-add-position", colors_add.y())
            signal_payload_data = next(
                group
                for group in variant_value(host.property("nodeData"))["settings_groups"]
                if group["group_id"] == "signal_plot_options"
            )
            colors_payload = next(
                item for item in signal_payload_data["items"] if item["port_key"] == "colors"
            )
            line_styles_payload = next(
                item for item in signal_payload_data["items"] if item["port_key"] == "line_styles"
            )
            colors_bottom = colors_list.mapToItem(
                host, QPointF(0.0, colors_list.height())
            ).y()
            assert abs(colors_bottom - float(line_styles_payload["y"])) < 0.5, (
                "colors-following-gap",
                colors_bottom,
                colors_payload,
                line_styles_payload,
            )
            color_candidates = named_child_items(host, "graphSurfaceListColorEditor")
            color_editor = next(
                (
                    item for item in color_candidates
                    if str(item.property("propertyKey")) == "colors"
                ),
                None,
            )
            assert color_editor is not None and bool(color_editor.property("visible")), (
                "signal-color-editor",
                colors_list.property("itemType"),
                variant_list(colors_list.property("values")),
                colors_list.property("itemCount"),
                [(str(item.property("propertyKey")), bool(item.property("visible"))) for item in color_candidates],
            )
            commits = []
            host.inlinePropertyCommitted.connect(
                lambda node_id, key, value: commits.append((node_id, key, variant_value(value)))
            )
            click_item(auto_button)
            assert commits and commits[-1][1:] == ("x_axis_interval", None), ("signal-interval-commit", commits)

            click_item(group_header("signal_plot_options"))
            QTest.qWait(220)
            settle_events(3)
            assert node.expanded_settings_group_ids == (), ("signal-collapse-state", node.expanded_settings_group_ids)
            assert abs(float(host.height()) - collapsed_height) < 0.75, ("signal-collapse-final", host.height(), collapsed_height)

            click_item(group_header("general_options"))
            click_item(group_header("general_options"))
            QTest.qWait(220)
            settle_events(3)
            assert node.expanded_settings_group_ids == (), ("rapid-state", node.expanded_settings_group_ids)
            assert abs(float(host.height()) - collapsed_height) < 0.75, ("rapid-final", host.height(), collapsed_height)

            future_collapsed = copy.deepcopy(collapsed_payload)
            future_collapsed["type_id"] = "tests.future_grouped_node"
            future_collapsed["title"] = ""
            future_collapsed["display_name"] = "Future Grouped Node"
            node.expanded_settings_group_ids = ("general_options",)
            future_expanded = signal_payload()
            future_expanded["type_id"] = "tests.future_grouped_node"
            future_expanded["title"] = ""
            future_expanded["display_name"] = "Future Grouped Node"
            node.expanded_settings_group_ids = ()
            future_host = create_component(
                graph_node_host_qml_path,
                {
                    "nodeData": future_collapsed,
                    "settingsGroupAnimationsEnabled": True,
                },
            )
            future_window = attach_host_to_window(future_host, 1000, 940)
            settle_events(4)

            def apply_future(_node_id, _group_id, expanded):
                future_host.beginSettingsGroupAnimation()
                future_host.setProperty(
                    "nodeData",
                    copy.deepcopy(future_expanded if expanded else future_collapsed),
                )

            future_host.settingsGroupExpansionRequested.connect(apply_future)
            future_header = next(
                item
                for item in named_child_items(future_host, "graphNodeSettingsGroupHeader")
                if str(item.property("groupId")) == "general_options"
            )
            future_start = float(future_host.height())
            point = future_header.mapToScene(QPointF(future_header.width() * 0.5, future_header.height() * 0.5))
            QTest.mouseClick(future_window, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, point.toPoint())
            settle_events(1)
            assert bool(future_host.property("settingsGroupAnimationRunning")), "future-animation"
            QTest.qWait(60)
            settle_events(2)
            future_mid = float(future_host.height())
            assert future_start < future_mid < float(future_expanded["height"]), ("future-mid", future_start, future_mid, future_expanded["height"])
            QTest.qWait(180)
            settle_events(3)
            assert abs(float(future_host.height()) - float(future_expanded["height"])) < 0.75, ("future-final", future_host.height(), future_expanded["height"])
            assert_settings_bottom_clearance(future_host)

            future_host.setProperty("settingsGroupAnimationsEnabled", False)
            future_header = next(
                item
                for item in named_child_items(future_host, "graphNodeSettingsGroupHeader")
                if str(item.property("groupId")) == "general_options"
            )
            point = future_header.mapToScene(QPointF(future_header.width() * 0.5, future_header.height() * 0.5))
            QTest.mouseClick(future_window, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, point.toPoint())
            settle_events(2)
            assert not bool(future_host.property("settingsGroupAnimationRunning"))
            assert abs(float(future_host.height()) - float(future_collapsed["height"])) < 0.75
            assert_settings_bottom_clearance(future_host)

            dispose_host_window(future_host, future_window)
            dispose_host_window(host, window)
            """,
        )

    def test_settings_group_endpoints_and_specialized_bodies_follow_the_live_band(self) -> None:
        self._run_qml_probe(
            "settings-group-live-band-metrics",
            """
            metrics_component = QQmlComponent(engine)
            metrics_component.setData(
                b'''
                import QtQml 2.15
                import "GraphNodeSurfaceMetrics.js" as Metrics
                QtObject {
                    property var nodePayload: ({})
                    property var portPayload: ({})
                    readonly property var endpoint: Metrics.portScenePointForPort(
                        nodePayload,
                        portPayload,
                        0,
                        0
                    )
                    readonly property real endpointY: Number(endpoint.y || 0)
                    readonly property var metrics: Metrics.surfaceMetrics(
                        nodePayload,
                        Number(nodePayload.width || 0),
                        Number(nodePayload.height || 0),
                        12
                    )
                    readonly property real bodyBottom: Number(metrics.body_top || 0)
                        + Number(metrics.body_height || 0)
                    readonly property real portTop: Number(metrics.port_top || 0)
                }
                ''',
                QUrl.fromLocalFile(str(components_dir / "graph" / "SettingsGroupMetricsProbe.qml")),
            )
            if metrics_component.status() == QQmlComponent.Status.Error:
                errors = "\\n".join(error.toString() for error in metrics_component.errors())
                raise AssertionError("Failed to load settings metrics probe:\\n" + errors)
            probe = metrics_component.create()
            if probe is None:
                errors = "\\n".join(error.toString() for error in metrics_component.errors())
                raise AssertionError("Failed to create settings metrics probe:\\n" + errors)

            collapsed_payload = node_payload()
            collapsed_payload["height"] = 106.0
            collapsed_payload["settings_band"] = {"top": 88.0, "height": 18.0}
            collapsed_port = collapsed_payload["ports"][0]
            collapsed_port.update({
                "layout_row": -1,
                "settings_group_id": "options",
                "handle_visible": False,
                "presentation_anchor": {"x": 0.0, "y": 97.0},
            })
            probe.setProperty("nodePayload", collapsed_payload)
            probe.setProperty("portPayload", collapsed_port)
            settle_events(2)
            endpoint_before = float(probe.property("endpointY"))

            live_payload = dict(collapsed_payload)
            live_payload["height"] = 146.0
            probe.setProperty("nodePayload", live_payload)
            settle_events(2)
            assert abs((float(probe.property("endpointY")) - endpoint_before) - 40.0) < 0.5

            family_variants = {
                "standard": "",
                "plot": "line",
                "viewer": "",
                "flowchart": "process",
                "planning": "",
                "annotation": "text",
                "group_backdrop": "",
                "media": "image",
                "web": "",
                "jupyter": "",
            }
            for family, variant in family_variants.items():
                payload = node_payload(surface_family=family, surface_variant=variant)
                payload["height"] = 400.0
                payload["settings_band"] = {"top": 360.0, "height": 40.0}
                payload["surface_metrics"] = {}
                probe.setProperty("nodePayload", payload)
                settle_events(1)
                assert float(probe.property("bodyBottom")) <= 360.5, family
                assert float(probe.property("portTop")) <= 360.5, family

            cardinal_payload = node_payload(
                surface_family="flowchart",
                surface_variant="process",
            )
            cardinal_payload["height"] = 400.0
            cardinal_payload["settings_band"] = {"top": 360.0, "height": 40.0}
            cardinal_payload["surface_metrics"] = {}
            cardinal_port = {
                "key": "bottom",
                "direction": "out",
                "kind": "flow",
                "side": "bottom",
            }
            probe.setProperty("nodePayload", cardinal_payload)
            probe.setProperty("portPayload", cardinal_port)
            settle_events(1)
            cardinal_local_y = (
                float(probe.property("endpointY"))
                - float(cardinal_payload["y"])
            )
            assert 359.0 <= cardinal_local_y <= 360.5, cardinal_local_y

            probe.deleteLater()
            engine.deleteLater()
            app.processEvents()
            """,
        )

    def test_standard_host_uses_valid_green_for_data_grip_states(self) -> None:
        self._run_qml_probe(
            "standard-host-valid-green-grips",
            """
            from PyQt6.QtGui import QColor
            from PyQt6.QtQml import QQmlProperty

            payload = node_payload()
            payload["ports"][0].update({"kind": "data", "flow_state": "default"})
            payload["ports"][1].update({"kind": "data", "flow_state": "flowing"})

            host = create_component(graph_node_host_qml_path, {"nodeData": payload})
            input_dot = named_child_items(host, "graphNodeInputPortDot")[0]
            output_dot = named_child_items(host, "graphNodeOutputPortDot")[0]

            valid_green = QColor("#67D487").name()
            data_blue = QColor("#7AA8FF").name()
            assert QColor(QQmlProperty.read(input_dot, "border.color")).name() == valid_green
            assert QColor(output_dot.property("color")).name() == valid_green
            assert QColor(QQmlProperty.read(output_dot, "border.color")).name() == valid_green
            assert QColor(output_dot.property("color")).name() != data_blue

            passive_payload = node_payload()
            passive_payload["runtime_behavior"] = "passive"
            passive_payload["visual_style"] = {"fill_color": "#5B4A39"}
            passive_payload["ports"][0].update({"kind": "data", "flow_state": "default"})
            passive_host = create_component(graph_node_host_qml_path, {"nodeData": passive_payload})
            passive_input_dot = named_child_items(passive_host, "graphNodeInputPortDot")[0]
            assert QColor(passive_input_dot.property("color")).name() == QColor("#5B4A39").name()
            """,
        )

    def test_standard_host_uses_only_declared_data_ports(self) -> None:
        self._run_qml_probe(
            "declared-data-ports-only-host",
            """
            payload = node_payload()
            payload["width"] = 320.0
            payload["surface_metrics"]["default_width"] = 320.0

            host = create_component(graph_node_host_qml_path, {"nodeData": payload})
            assert named_item(host, "graphNodeInputPortDot", "payload") is not None
            assert named_item(host, "graphNodeOutputPortDot", "result") is not None
            assert host.findChild(QObject, "graphNodeSettingsSectionLabel") is None
            assert host.findChild(QObject, "graphNodeSettingsSectionChevron") is None
            assert named_child_items(host, "graphNodeCompactControlEndpoint") == []
            """,
        )

    def test_standard_host_notches_follow_canvas_background_and_inset_shadow(self) -> None:
        self._run_qml_probe(
            "standard-host-notched-port-rendering",
            """
            from urllib.parse import unquote

            from PyQt6.QtCore import QPointF
            from PyQt6.QtGui import QColor
            from tests.qt_wait import wait_for_condition_or_raise

            def create_canvas_stub():
                component = QQmlComponent(engine)
                component.setData(
                    b'''
                    import QtQuick 2.15
                    Item {
                        property QtObject prefs: QtObject {
                            property bool notchedPortsEnabled: true
                            property string canvasBackgroundVariant: "theme"
                        }
                        property var executionFacts: null
                        property QtObject sceneBridge: QtObject {
                            property var selected_node_lookup: ({})
                        }
                        property var sceneCommandBridge: null
                        property var canvasStateBridgeRef: null
                        property var activeToolbarHost: null
                        property var frameSceneRectPayload: null
                    }
                    ''',
                    QUrl(),
                )
                assert component.status() == QQmlComponent.Status.Ready, [error.toString() for error in component.errors()]
                stub = component.create()
                assert stub is not None
                stub._component_ref = component
                return stub

            payload = node_payload()
            payload["ports"][1].update({"inactive": True})
            canvas_stub = create_canvas_stub()
            host = create_component(
                graph_node_host_qml_path,
                {"nodeData": payload, "canvasItem": canvas_stub, "showShadow": True},
            )
            window = attach_host_to_window(host)
            try:
                input_notch = named_item(host, "graphNodeInputPortNotch", "payload")
                output_notch = named_item(host, "graphNodeOutputPortNotch", "result")
                input_dot = named_item(host, "graphNodeInputPortDot", "payload")
                output_dot = named_item(host, "graphNodeOutputPortDot", "result")
                notches = [input_notch, output_notch]
                shadow = host.findChild(QObject, "graphNodeShadow")
                background_layer = host.findChild(QObject, "graphNodeChromeBackgroundLayer")
                selected_halo = host.findChild(QObject, "graphNodeSelectedHalo")
                removed_halos = [
                    host.findChild(QObject, "graphNodeFailureHalo"),
                    host.findChild(QObject, "graphNodeFailurePulseHalo"),
                    host.findChild(QObject, "graphNodeRunningHalo"),
                    host.findChild(QObject, "graphNodeRunningPulseHalo"),
                    host.findChild(QObject, "graphNodeCompletedFlashHalo"),
                    host.findChild(QObject, "graphNodeSelectedRunPreviewHalo"),
                    host.findChild(QObject, "graphNodeRunFreshHalo"),
                ]
                prefs = canvas_stub.property("prefs")

                assert bool(host.property("_notchedPortsEffective"))
                assert all(notch is not None and bool(notch.property("visible")) for notch in notches)
                assert all(abs(float(notch.width()) - 9.0) < 0.01 for notch in notches)
                assert all(abs(float(notch.height()) - 18.0) < 0.01 for notch in notches)
                assert all(abs(float(notch.opacity()) - 1.0) < 0.01 for notch in notches)
                assert input_notch.parentItem() is not input_dot
                assert output_notch.parentItem() is not output_dot
                assert all(not bool(notch.property("clip")) for notch in notches)
                assert all(bool(notch.property("cache")) for notch in notches)
                assert all(not bool(notch.property("asynchronous")) for notch in notches)
                assert all(bool(notch.property("smooth")) for notch in notches)
                assert all(not bool(notch.property("mipmap")) for notch in notches)
                assert not bool(input_notch.property("mirror"))
                assert bool(output_notch.property("mirror"))
                for notch in notches:
                    source_size = notch.property("sourceSize")
                    assert int(source_size.width()) == 54
                    assert int(source_size.height()) == 108
                wait_for_condition_or_raise(
                    lambda: all(float(notch.property("progress")) >= 0.999 for notch in notches),
                    timeout_ms=1000,
                    app=app,
                    timeout_message="Timed out waiting for cached notch SVG images.",
                )

                def encoded_source(notch):
                    return bytes(notch.property("source").toEncoded()).decode("ascii")

                sources = [encoded_source(notch) for notch in notches]
                assert len(set(sources)) == 1
                # Zoom must reuse the sharp cached image, not rerasterize it.
                for zoom in (0.1, 1.0, 3.0):
                    host.setScale(zoom)
                    app.processEvents()
                    assert [encoded_source(notch) for notch in notches] == sources
                    for notch in notches:
                        assert notch.property("sourceSize").width() == 54
                        assert notch.property("sourceSize").height() == 108
                host.setScale(1.0)
                svg = unquote(sources[0].split(",", 1)[1])
                assert svg.startswith("<svg ")
                assert svg.count("<path ") == 2
                assert 'M0 0 A9 9 0 0 1 0 18 Z' in svg
                assert 'fill="none"' in svg
                assert 'stroke-linecap="round"' in svg
                assert " Z" not in svg.split("<path ", 2)[2]
                assert all(QColor(notch.property("notchFillColor")).name().lower() == "#151821" for notch in notches)
                assert not named_child_items(host, "graphNodePortNotchOuterHalfCover")
                assert not named_child_items(host, "graphNodePortNotchDiameterCover")

                input_center = input_notch.mapToItem(host, QPointF(0.0, 9.0))
                output_center = output_notch.mapToItem(host, QPointF(9.0, 9.0))
                assert abs(input_center.x()) < 0.01
                assert abs(output_center.x() - float(host.width())) < 0.01
                input_notch_left = input_notch.mapToItem(host, QPointF(0.0, 0.0)).x()
                input_notch_right = input_notch.mapToItem(
                    host,
                    QPointF(float(input_notch.width()), 0.0),
                ).x()
                assert input_notch_left >= -0.01
                assert input_notch_right <= float(host.width()) + 0.01
                output_notch_left = output_notch.mapToItem(host, QPointF(0.0, 0.0)).x()
                output_notch_right = output_notch.mapToItem(
                    host,
                    QPointF(float(output_notch.width()), 0.0),
                ).x()
                assert output_notch_left >= -0.01
                assert abs(output_notch_right - float(host.width())) < 0.01

                assert shadow is not None
                assert background_layer is not None
                assert selected_halo is not None
                assert all(halo is None for halo in removed_halos)
                assert bool(background_layer.property("suppressHorizontalGlowSpill"))
                assert not bool(selected_halo.property("autoPaddingEnabled"))
                padding = selected_halo.property("paddingRect")
                assert abs(float(padding.x())) < 0.01
                assert abs(float(padding.width())) < 0.01
                assert abs(float(padding.y()) + 40.0) < 0.01
                assert abs(float(padding.height()) - 80.0) < 0.01
                expected_outline = QColor(background_layer.property("effectiveOutlineColor"))
                expected_width = float(background_layer.property("effectiveBorderWidth"))
                assert all(
                    QColor(notch.property("notchStrokeColor")).rgba() == expected_outline.rgba()
                    for notch in notches
                )
                assert all(
                    abs(float(notch.property("notchStrokeWidth")) - expected_width) < 0.01
                    for notch in notches
                )
                expected_blur = float(shadow.property("effectiveBlur"))
                assert abs(float(shadow.property("horizontalInset")) - expected_blur) < 0.01
                assert abs(float(shadow.x()) - expected_blur) < 0.01
                assert abs(float(shadow.width()) - (float(host.width()) - expected_blur * 2.0)) < 0.01

                host.setProperty("showShadow", False)
                app.processEvents()
                assert not bool(shadow.property("visible"))
                assert all(bool(notch.property("visible")) for notch in notches)
                host.setProperty("showShadow", True)

                expected_colors = {
                    "dark": "#1d1f24",
                    "light": "#f3f5f8",
                    "white": "#ffffff",
                }
                variant_sources = set()
                for variant, expected_color in expected_colors.items():
                    previous_source = encoded_source(input_notch)
                    prefs.setProperty("canvasBackgroundVariant", variant)
                    wait_for_condition_or_raise(
                        lambda: float(input_notch.property("progress")) >= 0.999
                        and encoded_source(input_notch) != previous_source,
                        timeout_ms=1000,
                        app=app,
                        timeout_message=f"Timed out waiting for {variant} notch SVG.",
                    )
                    assert QColor(input_notch.property("notchFillColor")).name().lower() == expected_color
                    variant_sources.add(encoded_source(input_notch))
                assert len(variant_sources) == len(expected_colors)

                idle_outline = QColor(background_layer.property("effectiveOutlineColor"))
                idle_source = encoded_source(input_notch)
                scene_bridge = canvas_stub.property("sceneBridge")
                scene_bridge.setProperty(
                    "selected_node_lookup",
                    {str(payload["node_id"]): True},
                )
                app.processEvents()
                assert bool(host.property("isSelected"))
                selected_outline = QColor(background_layer.property("effectiveOutlineColor"))
                assert selected_outline.rgba() != idle_outline.rgba()
                assert all(
                    QColor(notch.property("notchStrokeColor")).rgba() == selected_outline.rgba()
                    for notch in notches
                )
                wait_for_condition_or_raise(
                    lambda: float(input_notch.property("progress")) >= 0.999
                    and encoded_source(input_notch) != idle_source,
                    timeout_ms=1000,
                    app=app,
                    timeout_message="Timed out waiting for selected-outline notch SVG.",
                )

                host.setProperty("shadowSoftness", 1000)
                app.processEvents()
                assert float(shadow.width()) > float(host.property("resolvedCornerRadius")) * 2.0
                host.setProperty("shadowSoftness", 50)

                enabled_cache_key = str(background_layer.property("cacheKey"))
                prefs.setProperty("notchedPortsEnabled", False)
                app.processEvents()
                assert not bool(host.property("_notchedPortsEffective"))
                assert all(not bool(notch.property("visible")) for notch in notches)
                assert not bool(background_layer.property("suppressHorizontalGlowSpill"))
                assert bool(selected_halo.property("autoPaddingEnabled"))
                assert abs(float(shadow.property("horizontalInset"))) < 0.01
                assert abs(float(shadow.x())) < 0.01
                assert abs(float(shadow.width()) - float(host.width())) < 0.01
                assert str(background_layer.property("cacheKey")) != enabled_cache_key
            finally:
                dispose_host_window(host, window)
                canvas_stub.deleteLater()
                engine.deleteLater()
                app.processEvents()
            """,
        )

    def test_notched_ports_exclude_collapsed_chrome_free_portless_and_flowchart_hosts(self) -> None:
        self._run_qml_probe(
            "notched-port-host-exclusions",
            """
            def assert_notched_state(payload, expected):
                host = create_component(graph_node_host_qml_path, {"nodeData": payload})
                try:
                    assert bool(host.property("_notchedPortsEffective")) is expected
                    for object_name in (
                        "graphNodeInputPortNotch",
                        "graphNodeOutputPortNotch",
                    ):
                        assert all(bool(item.property("visible")) is expected for item in named_child_items(host, object_name))
                finally:
                    host.deleteLater()
                    app.processEvents()

            assert_notched_state(node_payload(), True)

            collapsed = node_payload()
            collapsed["collapsed"] = True
            assert_notched_state(collapsed, False)

            chrome_free = node_payload()
            chrome_free["runtime_behavior"] = "passive"
            chrome_free["surface_metrics"]["use_host_chrome"] = False
            assert_notched_state(chrome_free, False)

            portless = node_payload()
            portless["ports"] = []
            assert_notched_state(portless, False)

            assert_notched_state(flowchart_payload("process"), False)
            """,
        )

    def test_standard_host_port_label_editor_uses_inline_text_treatment(self) -> None:
        self._run_qml_probe(
            "port-label-inline-editor-host",
            """
            from PyQt6.QtGui import QColor

            def assert_inline_editor(editor, label, expected_text):
                assert editor is not None
                assert label is not None
                assert bool(editor.property("visible"))
                assert str(editor.property("text") or "") == expected_text
                assert str(editor.property("selectedText") or "") == ""
                assert int(editor.property("cursorPosition")) == len(expected_text)
                assert QColor(editor.property("fillColor")).alpha() == 0
                assert QColor(editor.property("borderColor")).alpha() == 0
                assert QColor(editor.property("focusBorderColor")).alpha() == 0
                assert int(editor.property("topPadding")) == 0
                assert int(editor.property("bottomPadding")) == 0
                assert int(editor.property("leftPadding")) == 0
                assert int(editor.property("rightPadding")) == 0
                assert editor.property("font").pixelSize() == label.property("font").pixelSize()
                assert editor.property("font").weight() == label.property("font").weight()
                assert QColor(editor.property("textColor")).name().lower() == QColor(label.property("color")).name().lower()

            payload = node_payload()
            payload["width"] = 320.0
            payload["surface_metrics"]["default_width"] = 320.0
            payload["ports"] = [
                {
                    "key": "message",
                    "label": "trigger",
                    "direction": "in",
                    "kind": "data",
                    "data_type": "str",
                    "connected": False,
                },
                {
                    "key": "result",
                    "label": "result",
                    "direction": "out",
                    "kind": "data",
                    "data_type": "str",
                    "connected": False,
                },
            ]
            payload["inline_properties"] = []

            host = create_component(graph_node_host_qml_path, {"nodeData": payload})
            window = attach_host_to_window(host, width=520, height=360)
            try:
                input_label = named_item(host, "graphNodeInputPortLabel", "message")
                output_label = named_item(host, "graphNodeOutputPortLabel", "result")
                input_editor = named_item(host, "graphNodeInputPortLabelEditor", "message")
                output_editor = named_item(host, "graphNodeOutputPortLabelEditor", "result")

                mouse_click(window, item_scene_point(input_label))
                settle_events(5)
                assert_inline_editor(input_editor, input_label, "trigger")

                app.sendEvent(
                    input_editor,
                    QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier),
                )
                app.sendEvent(
                    input_editor,
                    QKeyEvent(QEvent.Type.KeyRelease, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier),
                )
                settle_events(5)

                mouse_click(window, item_scene_point(output_label))
                settle_events(5)
                assert_inline_editor(output_editor, output_label, "result")
            finally:
                dispose_host_window(host, window)
            """,
        )

    def test_standard_host_shows_plain_data_labels_without_access_suffix(self) -> None:
        self._run_qml_probe(
            "data-port-access-labels-host",
            """
            host = create_component(graph_node_host_qml_path, {"nodeData": node_payload()})
            input_label = named_child_items(host, "graphNodeInputPortLabel")[0]
            output_label = named_child_items(host, "graphNodeOutputPortLabel")[0]
            input_mouse = named_child_items(host, "graphNodeInputPortMouseArea")[0]
            output_mouse = named_child_items(host, "graphNodeOutputPortMouseArea")[0]

            assert input_label.property("text") == "Payload"
            assert output_label.property("text") == "Result"
            assert input_mouse.property("portLabelTooltipText") == "Payload"
            assert output_mouse.property("portLabelTooltipText") == "Result"
            """,
        )

    def test_graph_typography_host_chrome_shared_roles_apply_to_passive_titles(self) -> None:
        self._run_qml_probe(
            "graph-typography-host-chrome-passive-title-shared",
            """
            def configured_payload(*, passive=False, font_size=None, font_weight=None):
                payload = node_payload()
                payload["can_enter_scope"] = True
                payload["ports"] = [
                    {
                        "key": "message",
                        "label": "Message",
                        "direction": "in",
                        "kind": "data",
                        "data_type": "str",
                        "connected": False,
                    },
                    {
                        "key": "result",
                        "label": "Result",
                        "direction": "out",
                        "kind": "data",
                        "data_type": "str",
                        "connected": False,
                    },
                ]
                if passive:
                    payload["runtime_behavior"] = "passive"
                    payload["visual_style"] = {}
                    if font_size is not None:
                        payload["visual_style"]["font_size"] = font_size
                    if font_weight is not None:
                        payload["visual_style"]["font_weight"] = font_weight
                return payload

            active_host = create_component(
                graph_node_host_qml_path,
                {
                    "nodeData": configured_payload(),
                    "graphLabelPixelSize": 16,
                },
            )
            active_typography = active_host.findChild(QObject, "graphSharedTypography")
            active_title = active_host.findChild(QObject, "graphNodeTitle")
            active_open_badge = active_host.findChild(QObject, "graphNodeOpenBadgeText")
            active_input_labels = named_child_items(active_host, "graphNodeInputPortLabel")
            active_output_labels = named_child_items(active_host, "graphNodeOutputPortLabel")
            active_data_label = [item for item in active_input_labels if item.property("text") == "Message"][0]
            active_output_label = [item for item in active_output_labels if item.property("text") == "Result"][0]

            assert active_typography is not None
            assert active_title is not None
            assert active_open_badge is None
            assert active_title.property("font").pixelSize() == int(active_typography.property("nodeTitlePixelSize"))
            assert active_title.property("font").weight() == int(active_typography.property("nodeTitleFontWeight"))
            assert active_data_label.property("font").pixelSize() == int(active_typography.property("portLabelPixelSize"))
            assert active_data_label.property("font").weight() == int(active_typography.property("portLabelFontWeight"))
            assert active_output_label.property("font").pixelSize() == int(active_typography.property("portLabelPixelSize"))
            assert active_output_label.property("font").weight() == int(active_typography.property("portLabelFontWeight"))

            passive_host = create_component(
                graph_node_host_qml_path,
                {
                    "nodeData": configured_payload(passive=True, font_size=17, font_weight="normal"),
                    "graphLabelPixelSize": 16,
                },
            )
            passive_typography = passive_host.findChild(QObject, "graphSharedTypography")
            passive_title = passive_host.findChild(QObject, "graphNodeTitle")
            passive_open_badge = passive_host.findChild(QObject, "graphNodeOpenBadgeText")
            passive_input_labels = named_child_items(passive_host, "graphNodeInputPortLabel")
            passive_data_label = [item for item in passive_input_labels if item.property("text") == "Message"][0]

            assert passive_typography is not None
            assert passive_title is not None
            assert passive_open_badge is None
            assert passive_title.property("font").pixelSize() == int(passive_typography.property("nodeTitlePixelSize"))
            assert passive_title.property("font").weight() == int(passive_typography.property("nodeTitleFontWeight"))
            assert passive_title.property("font").pixelSize() != 17
            assert passive_data_label.property("font").pixelSize() == int(passive_typography.property("portLabelPixelSize"))
            assert passive_data_label.property("font").weight() == int(passive_typography.property("portLabelFontWeight"))
            """,
        )

    def test_graph_typography_inline_edge_inline_roles_apply_to_passive_titles(self) -> None:
        self._run_qml_probe(
            "graph-typography-inline-edge-passive-title-shared",
            """
            def configured_payload(*, passive=False):
                payload = node_payload()
                payload["inline_properties"] = [
                    {
                        "key": "source_path",
                        "label": "Source",
                        "inline_editor": "text",
                        "value": "/fixtures/original.txt",
                        "status_chip_text": "Stored",
                        "status_chip_variant": "stored",
                        "overridden_by_input": False,
                        "input_port_label": "source_path",
                    },
                    {
                        "key": "show_full_path",
                        "label": "Show full path",
                        "inline_editor": "toggle",
                        "value": True,
                        "overridden_by_input": False,
                        "input_port_label": "show_full_path",
                    },
                    {
                        "key": "encoding",
                        "label": "Encoding",
                        "inline_editor": "text",
                        "value": "utf-8",
                        "overridden_by_input": True,
                        "input_port_label": "format",
                    }
                ]
                if passive:
                    payload["runtime_behavior"] = "passive"
                    payload["visual_style"] = {
                        "font_size": 17,
                        "font_weight": "normal",
                    }
                return payload

            def inline_item(host, object_name, property_key):
                return next(
                    item for item in named_child_items(host, object_name)
                    if str(item.property("propertyKey") or "") == property_key
                )

            active_host = create_component(
                graph_node_host_qml_path,
                {
                    "nodeData": configured_payload(),
                    "graphLabelPixelSize": 16,
                },
            )
            active_typography = active_host.findChild(QObject, "graphSharedTypography")
            active_inline_label = inline_item(active_host, "graphNodeInlinePropertyLabel", "source_path")
            active_toggle_label = inline_item(active_host, "graphNodeInlinePropertyLabel", "show_full_path")
            active_driven_label = inline_item(active_host, "graphNodeInlinePropertyLabel", "encoding")
            active_status_chip = inline_item(active_host, "graphNodeInlineStatusChipLabel", "source_path")

            assert active_typography is not None
            assert active_inline_label.property("font").pixelSize() == int(active_typography.property("inlinePropertyPixelSize"))
            assert active_inline_label.property("font").weight() == int(active_typography.property("inlinePropertyFontWeight"))
            assert active_toggle_label.property("font").pixelSize() == int(active_typography.property("inlinePropertyPixelSize"))
            assert active_toggle_label.property("font").weight() == int(active_typography.property("inlinePropertyFontWeight"))
            assert active_driven_label.property("font").pixelSize() == int(active_typography.property("inlinePropertyPixelSize")), (
                active_driven_label.property("font").pixelSize(),
                active_typography.property("inlinePropertyPixelSize"),
            )
            assert active_driven_label.property("font").weight() == int(active_typography.property("inlinePropertyFontWeight")), (
                active_driven_label.property("font").weight(),
                active_typography.property("inlinePropertyFontWeight"),
            )
            assert (
                active_driven_label.property("color").name()
                == active_host.property("inlineDrivenTextColor").name()
            )
            assert active_status_chip.property("font").pixelSize() == int(active_typography.property("badgePixelSize"))
            assert active_status_chip.property("font").weight() == int(active_typography.property("badgeFontWeight"))

            passive_host = create_component(
                graph_node_host_qml_path,
                {
                    "nodeData": configured_payload(passive=True),
                    "graphLabelPixelSize": 16,
                },
            )
            passive_typography = passive_host.findChild(QObject, "graphSharedTypography")
            passive_title = passive_host.findChild(QObject, "graphNodeTitle")
            passive_inline_label = inline_item(passive_host, "graphNodeInlinePropertyLabel", "source_path")
            passive_toggle_label = inline_item(passive_host, "graphNodeInlinePropertyLabel", "show_full_path")
            passive_driven_label = inline_item(passive_host, "graphNodeInlinePropertyLabel", "encoding")
            passive_status_chip = inline_item(passive_host, "graphNodeInlineStatusChipLabel", "source_path")

            assert passive_typography is not None
            assert passive_title is not None
            assert passive_title.property("font").pixelSize() == int(passive_typography.property("nodeTitlePixelSize"))
            assert passive_title.property("font").weight() == int(passive_typography.property("nodeTitleFontWeight"))
            assert passive_title.property("font").pixelSize() != 17
            assert passive_inline_label.property("font").pixelSize() == int(passive_typography.property("inlinePropertyPixelSize"))
            assert passive_inline_label.property("font").weight() == int(passive_typography.property("inlinePropertyFontWeight"))
            assert passive_toggle_label.property("font").pixelSize() == int(passive_typography.property("inlinePropertyPixelSize"))
            assert passive_toggle_label.property("font").weight() == int(passive_typography.property("inlinePropertyFontWeight"))
            assert passive_driven_label.property("font").pixelSize() == int(passive_typography.property("inlinePropertyPixelSize")), (
                passive_driven_label.property("font").pixelSize(),
                passive_typography.property("inlinePropertyPixelSize"),
            )
            assert passive_driven_label.property("font").weight() == int(passive_typography.property("inlinePropertyFontWeight")), (
                passive_driven_label.property("font").weight(),
                passive_typography.property("inlinePropertyFontWeight"),
            )
            assert (
                passive_driven_label.property("color").name()
                == passive_host.property("inlineDrivenTextColor").name()
            )
            assert passive_status_chip.property("font").pixelSize() == int(passive_typography.property("badgePixelSize"))
            assert passive_status_chip.property("font").weight() == int(passive_typography.property("badgeFontWeight"))
            """,
        )

    def test_title_icon_renders_for_non_passive_titles_and_uses_centered_reserve(self) -> None:
        self._run_qml_probe(
            "title-icon-non-passive-host",
            """
            from pathlib import Path

            def normalized_source(value):
                if hasattr(value, "toString"):
                    return str(value.toString())
                return str(value or "")

            icon_source = (Path.cwd() / "ea_node_editor" / "assets" / "app_icon" / "corex_app_minimal.svg").as_uri()

            active_canvas = create_component(
                graph_canvas_qml_path,
                {
                    "mainWindowBridge": {
                        "graphics_graph_label_pixel_size": 16,
                        "graphics_graph_node_icon_pixel_size_override": 12,
                        "graphics_node_title_icon_pixel_size": 12,
                    },
                },
            )

            active_payload = node_payload()
            active_payload["title"] = "Archive Session"
            active_payload["surface_metrics"]["title_centered"] = True
            active_payload["icon_source"] = icon_source

            active_host = create_component(
                graph_node_host_qml_path,
                {
                    "nodeData": active_payload,
                    "canvasItem": active_canvas,
                },
            )
            active_typography = active_host.findChild(QObject, "graphSharedTypography")
            active_display = active_host.findChild(QObject, "graphNodeTitleDisplay")
            active_title = active_host.findChild(QObject, "graphNodeTitle")
            active_icon = active_host.findChild(QObject, "graphNodeTitleIcon")
            active_group_icon = active_host.findChild(QObject, "graphNodeGroupTitleIcon")

            assert active_typography is not None
            assert active_display is not None
            assert active_title is not None
            assert active_icon is not None
            assert active_group_icon is not None
            assert int(active_host.property("effectiveNodeTitleIconPixelSize")) == 12
            assert int(active_typography.property("nodeTitleIconPixelSize")) == 12
            assert bool(active_icon.property("visible"))
            assert not bool(active_group_icon.property("visible"))
            assert normalized_source(active_icon.property("source")) == icon_source
            assert not bool(active_icon.property("themeAware"))
            assert int(active_icon.property("width")) == 12
            assert int(active_icon.property("height")) == 12
            assert bool(active_icon.property("smooth"))
            assert bool(active_icon.property("mipmap"))
            assert float(active_title.x()) > 0.0
            assert float(active_title.width()) < float(active_display.width())

            passive_canvas = create_component(
                graph_canvas_qml_path,
                {
                    "mainWindowBridge": {
                        "graphics_graph_label_pixel_size": 16,
                        "graphics_graph_node_icon_pixel_size_override": 12,
                        "graphics_node_title_icon_pixel_size": 12,
                    },
                },
            )

            passive_payload = node_payload()
            passive_payload["runtime_behavior"] = "passive"
            passive_payload["surface_metrics"]["title_centered"] = True
            passive_payload["icon_source"] = icon_source

            passive_host = create_component(
                graph_node_host_qml_path,
                {
                    "nodeData": passive_payload,
                    "canvasItem": passive_canvas,
                },
            )
            passive_title = passive_host.findChild(QObject, "graphNodeTitle")
            passive_icon = passive_host.findChild(QObject, "graphNodeTitleIcon")

            assert passive_title is not None
            assert passive_icon is not None
            assert not bool(passive_icon.property("visible"))
            assert abs(float(passive_title.x()) - 0.0) < 0.5
            """,
        )

    def test_title_icon_theme_aware_flag_tints_with_header_text_color(self) -> None:
        self._run_qml_probe(
            "title-icon-theme-aware-header-color",
            """
            from pathlib import Path

            from PyQt6.QtGui import QColor

            def normalized_source(value):
                if hasattr(value, "toString"):
                    return str(value.toString())
                return str(value or "")

            def color_name(value):
                if hasattr(value, "name"):
                    return str(value.name()).lower()
                return QColor(str(value or "")).name().lower()

            icon_source = (Path.cwd() / "ea_node_editor" / "assets" / "app_icon" / "corex_app_minimal.svg").as_uri()

            payload = node_payload()
            payload["icon_source"] = icon_source
            payload["icon_theme_aware"] = True

            host = create_component(
                graph_node_host_qml_path,
                {
                    "nodeData": payload,
                },
            )
            title_icon = host.findChild(QObject, "graphNodeTitleIcon")

            assert title_icon is not None
            assert bool(title_icon.property("visible"))
            assert normalized_source(title_icon.property("source")) == icon_source
            assert bool(title_icon.property("themeAware"))
            assert color_name(title_icon.property("themeAwareColor")) == color_name(host.property("headerTextColor"))
            """,
        )

    def test_title_icon_filtering_follows_canvas_render_quality(self) -> None:
        self._run_qml_probe(
            "title-icon-filtering-follows-canvas-render-quality",
            """
            from pathlib import Path

            def normalized_source(value):
                if hasattr(value, "toString"):
                    return str(value.toString())
                return str(value or "")

            icon_source = (Path.cwd() / "ea_node_editor" / "assets" / "app_icon" / "corex_app_minimal.svg").as_uri()

            canvas = create_component(
                graph_canvas_qml_path,
                {
                    "mainWindowBridge": {
                        "graphics_graph_label_pixel_size": 16,
                        "graphics_graph_node_icon_pixel_size_override": 12,
                        "graphics_node_title_icon_pixel_size": 12,
                    },
                    "width": 1280.0,
                    "height": 720.0,
                },
            )
            payload = node_payload()
            payload["title"] = "Archive Session"
            payload["surface_metrics"]["title_centered"] = True
            payload["icon_source"] = icon_source

            host = create_component(
                graph_node_host_qml_path,
                {
                    "nodeData": payload,
                    "canvasItem": canvas,
                },
            )
            title_icon = host.findChild(QObject, "graphNodeTitleIcon")

            assert title_icon is not None
            assert normalized_source(title_icon.property("source")) == icon_source
            assert bool(title_icon.property("smooth"))
            assert bool(title_icon.property("mipmap"))

            canvas.beginViewportInteraction()
            canvas.finishViewportInteractionSoon()
            app.processEvents()

            assert bool(canvas.property("interactionActive"))
            assert bool(title_icon.property("smooth"))
            assert bool(title_icon.property("mipmap"))
            """,
        )

    def test_title_icon_large_override_expands_title_row_and_stays_within_bounds(self) -> None:
        self._run_qml_probe(
            "title-icon-large-override-header-bounds",
            """
            from pathlib import Path

            icon_source = (Path.cwd() / "ea_node_editor" / "assets" / "app_icon" / "corex_app_minimal.svg").as_uri()

            canvas_item = create_component(
                graph_canvas_qml_path,
                {
                    "mainWindowBridge": {
                        "graphics_graph_label_pixel_size": 16,
                        "graphics_graph_node_icon_pixel_size_override": 50,
                        "graphics_node_title_icon_pixel_size": 50,
                    },
                },
            )

            payload = node_payload()
            payload["title"] = "Archive Session"
            payload["height"] = 80.0
            payload["surface_metrics"]["default_height"] = 80.0
            payload["surface_metrics"]["header_height"] = 54.0
            payload["surface_metrics"]["title_height"] = 54.0
            payload["surface_metrics"]["body_top"] = 60.0
            payload["surface_metrics"]["port_top"] = 60.0
            payload["surface_metrics"]["title_centered"] = True
            payload["icon_source"] = icon_source

            host = create_component(
                graph_node_host_qml_path,
                {
                    "nodeData": payload,
                    "canvasItem": canvas_item,
                },
            )
            title_display = host.findChild(QObject, "graphNodeTitleDisplay")
            title_icon = host.findChild(QObject, "graphNodeTitleIcon")

            assert title_display is not None
            assert title_icon is not None
            assert int(host.property("effectiveNodeTitleIconPixelSize")) == 50
            assert bool(title_icon.property("visible"))
            assert float(title_display.property("height")) > 24.0
            assert float(host.property("height")) > 50.0
            assert float(title_icon.property("width")) == 50.0
            assert float(title_icon.property("height")) <= float(title_display.property("height"))
            assert float(title_icon.property("y")) >= 0.0
            assert float(title_icon.property("y")) + float(title_icon.property("height")) <= float(title_display.property("height")) + 0.5
            assert float(title_icon.property("height")) == float(host.property("effectiveNodeTitleIconPixelSize"))
            """,
        )

    def test_standard_host_consumes_metric_backed_label_columns_without_overlap(self) -> None:
        self._run_qml_probe(
            "port-label-width-contract-host",
            """
            payload = node_payload()
            payload["ports"][0]["label"] = "Primary Input Payload"
            payload["ports"][1]["label"] = "Dispatch Result Token"
            payload["width"] = 360.0
            payload["surface_metrics"]["default_width"] = 360.0

            measurement_host = create_component(graph_node_host_qml_path, {"nodeData": payload})
            measurement_input = named_child_items(measurement_host, "graphNodeInputPortLabel")[0]
            measurement_output = named_child_items(measurement_host, "graphNodeOutputPortLabel")[0]
            left_width = float(measurement_input.property("implicitWidth"))
            right_width = float(measurement_output.property("implicitWidth"))
            measurement_host.deleteLater()
            app.processEvents()

            port_gutter = 21.5
            center_gap = 24.0
            min_width = left_width + right_width + (port_gutter * 2.0) + center_gap
            payload["width"] = min_width
            payload["surface_metrics"]["default_width"] = min_width
            payload["surface_metrics"]["min_width"] = min_width
            payload["surface_metrics"]["standard_left_label_width"] = left_width
            payload["surface_metrics"]["standard_right_label_width"] = right_width
            payload["surface_metrics"]["standard_port_gutter"] = port_gutter
            payload["surface_metrics"]["standard_center_gap"] = center_gap
            payload["surface_metrics"]["standard_port_label_min_width"] = min_width

            host = create_component(graph_node_host_qml_path, {"nodeData": payload})
            input_dot = named_child_items(host, "graphNodeInputPortDot")[0]
            output_dot = named_child_items(host, "graphNodeOutputPortDot")[0]
            input_label = named_child_items(host, "graphNodeInputPortLabel")[0]
            output_label = named_child_items(host, "graphNodeOutputPortLabel")[0]

            assert bool(host.property("_usesStandardPortLabelColumns"))
            assert abs(float(input_label.width()) - left_width) < 0.75
            assert abs(float(output_label.width()) - right_width) < 0.75

            gap = float(host.property("_portLabelGap"))
            input_left = input_label.mapToItem(host, QPointF(0.0, 0.0)).x()
            input_right = input_label.mapToItem(host, QPointF(float(input_label.width()), 0.0)).x()
            output_left = output_label.mapToItem(host, QPointF(0.0, 0.0)).x()
            output_right = output_label.mapToItem(host, QPointF(float(output_label.width()), 0.0)).x()

            assert abs(input_left - (input_dot.x() + input_dot.width() + gap)) < 0.5
            assert abs(output_right - (output_dot.x() - gap)) < 0.5
            assert output_left - input_right >= center_gap - 0.5
            """,
        )

    def test_body_region_surface_loader_clamps_content_before_port_rows(self) -> None:
        self._run_qml_probe(
            "body-region-surface-loader-clamp",
            """
            payload = node_payload()
            payload["type_id"] = "tabular.input"
            payload["surface_spec"] = {
                "family": "standard",
                "variant": "",
                "component_key": "tabular",
                "qml_component": "tabular/GraphTabularPreviewSurface.qml",
                "fullscreen": {
                    "supported": True,
                    "content_kind": "tabular",
                    "action_id": "fullscreen",
                    "action_label": "Fullscreen",
                    "action_icon": "fullscreen",
                    "action_kind": "tabular",
                    "requires_bridge": True,
                },
                "input_capabilities": {
                    "devices": ["mouse", "touch"],
                    "events": ["press", "release", "move", "wheel", "key"],
                    "hover": True,
                    "pressure": False,
                    "gestures": ["tap", "drag", "wheel"],
                    "plugin_gestures": [],
                },
                "native_overlay": {"required": False, "target": "", "owner": ""},
                "layout": {
                    "content_region": "body",
                    "min_body_width": 320.0,
                    "min_body_height": 154.0,
                    "preferred_body_height": 164.0,
                },
                "metadata": {"tabular_preview": True},
            }
            payload["width"] = 210.0
            payload["height"] = 100.0
            payload["properties"] = {"path": ""}
            payload["surface_metrics"]["default_width"] = 210.0
            payload["surface_metrics"]["min_width"] = 120.0
            payload["surface_metrics"]["body_height"] = 154.0
            payload["surface_metrics"]["port_top"] = 184.0
            payload["surface_metrics"]["default_height"] = 228.0
            payload["surface_metrics"]["min_height"] = 228.0

            host = create_component(graph_node_host_qml_path, {"nodeData": payload})
            app.processEvents()
            loader = host.findChild(QObject, "graphNodeSurfaceLoader")
            surface = host.findChild(QObject, "graphNodeTabularSurface")

            assert loader is not None
            assert surface is not None
            assert str(loader.property("contentRegion")) == "body", str(loader.property("contentRegion"))
            assert float(loader.property("minimumBodyWidth")) >= 320.0, float(loader.property("minimumBodyWidth"))
            assert float(loader.property("minimumBodyHeight")) >= 154.0, float(loader.property("minimumBodyHeight"))
            assert float(host.width()) >= 336.0, float(host.width())
            assert float(host.height()) >= 228.0, float(host.height())

            metrics = variant_value(host.property("surfaceMetrics"))
            surface_top_left = surface.mapToItem(host, QPointF(0.0, 0.0))
            surface_bottom = float(surface_top_left.y()) + float(surface.height())
            assert abs(float(surface_top_left.x()) - float(metrics["body_left_margin"])) < 0.5, (float(surface_top_left.x()), metrics)
            assert abs(float(surface_top_left.y()) - float(metrics["body_top"])) < 0.5, (float(surface_top_left.y()), metrics)
            assert float(surface.width()) >= 320.0, float(surface.width())
            assert float(surface.height()) >= 154.0, float(surface.height())
            assert surface_bottom <= float(metrics["port_top"]) + 0.5, (surface_bottom, metrics)
            """,
        )

    def test_selection_required_tabular_surface_shows_picker_and_commits_selected_object(self) -> None:
        self._run_qml_probe(
            "tabular-selection-required-picker",
            """
            payload = node_payload()
            payload["node_id"] = "node_tabular_selector"
            payload["type_id"] = "tabular.input"
            payload["title"] = "Tabular Data Input"
            payload["surface_spec"] = surface_spec_payload_for_values(type_id="tabular.input")
            payload["width"] = 440.0
            payload["height"] = 230.0
            payload["properties"] = {
                "path": "C:/tmp/workbook.xlsx",
                "cache_policy": "app_managed_parquet",
                "selected_object": "",
            }
            payload["inline_properties"] = []
            payload["ports"] = [
                {
                    "key": "path",
                    "label": "Path",
                    "direction": "in",
                    "kind": "data",
                    "data_type": "path",
                    "connected": False,
                },
                {
                    "key": "table_data",
                    "label": "Table Data",
                    "direction": "out",
                    "kind": "data",
                    "data_type": "tabular_data_ref",
                    "connected": False,
                },
            ]
            payload["surface_metrics"]["default_width"] = 440.0
            payload["surface_metrics"]["min_width"] = 336.0
            payload["surface_metrics"]["body_height"] = 154.0
            payload["surface_metrics"]["port_top"] = 184.0
            payload["surface_metrics"]["default_height"] = 230.0
            payload["surface_metrics"]["min_height"] = 228.0
            payload["preview"] = {
                "state": "selection_required",
                "message": "Select a sheet, key, or dataset before previewing this source.",
                "content_kind": "tabular",
                "preview_kind": "",
                "source": {
                    "path": "C:/tmp/workbook.xlsx",
                    "resolved_path": "C:/tmp/workbook.xlsx",
                    "format_id": "xlsx",
                    "size_class": "small",
                },
                "selector": {
                    "selected_object": "",
                    "requires_selection": True,
                    "objects": [
                        {"object_id": "First", "display_name": "First", "kind": "table"},
                        {"object_id": "Second Sheet", "display_name": "Second Sheet", "kind": "table"},
                    ],
                },
                "error": {
                    "code": "selector_required",
                    "message": "Select a sheet, key, or dataset before previewing this source.",
                    "recoverable": True,
                },
            }
            canvas_item = create_surface_canvas_item()

            host = create_component(
                graph_node_host_qml_path,
                {"nodeData": payload, "canvasItem": canvas_item},
            )
            window = attach_host_to_window(host, width=720, height=520)
            try:
                loader = host.findChild(QObject, "graphNodeSurfaceLoader")
                grid = host.findChild(QObject, "graphNodeTabularPreviewGrid")
                combo = host.findChild(QObject, "graphNodeTabularSelectorCombo")
                assert loader is not None
                assert grid is not None
                assert combo is not None
                settle_events(8)

                assert not bool(grid.property("visible"))
                assert bool(combo.property("visible"))
                assert variant_list(combo.property("model")) == ["First", "Second Sheet"]
                assert 24.0 <= float(combo.property("popupRowHeight")) <= 30.0
                assert abs(float(combo.property("popupWidth")) - float(combo.width())) < 0.75
                rects = variant_list(loader.property("embeddedInteractiveRects"))
                assert len(rects) == 1, rects
                assert abs(rect_field(rects[0], "height") - 28.0) < 0.75
                actions = variant_list(loader.property("surfaceActions"))
                export_actions = [action for action in actions if action["id"] == "exportVisibleRows"]
                assert len(export_actions) == 1, actions
                assert not bool(export_actions[0]["enabled"])

                QTest.mouseClick(
                    window,
                    Qt.MouseButton.LeftButton,
                    Qt.KeyboardModifier.NoModifier,
                    item_scene_point(combo, 0.2, 0.5),
                )
                settle_events(2)
                combo.setProperty("editText", "Second Sheet")
                settle_events(2)
                QTest.keyClick(window, Qt.Key.Key_Return)
                settle_events(4)

                assert canvas_item.last_committed_node_id == "node_tabular_selector"
                assert canvas_item.last_committed_properties == {"selected_object": "Second Sheet"}
            finally:
                dispose_host_window(host, window)
                canvas_item.deleteLater()
                app.processEvents()
            """,
        )

    def test_resized_tabular_preview_keeps_visible_ports_below_content(self) -> None:
        self._run_qml_probe(
            "resized-tabular-preview-port-separation",
            """
            payload = node_payload()
            payload["node_id"] = "node_resized_tabular_ports"
            payload["type_id"] = "tabular.input"
            payload["title"] = "Tabular Data Input"
            payload["surface_spec"] = surface_spec_payload_for_values(type_id="tabular.input")
            payload["width"] = 620.0
            payload["height"] = 420.0
            payload["properties"] = {
                "path": "C:/tmp/plastic_strain.csv",
                "cache_policy": "app_managed_parquet",
                "selected_object": "",
            }
            payload["inline_properties"] = []
            payload["ports"] = [
                {
                    "key": "path",
                    "label": "Path",
                    "direction": "in",
                    "kind": "data",
                    "data_type": "path",
                    "connected": False,
                },
                {
                    "key": "table_data",
                    "label": "Table Data",
                    "direction": "out",
                    "kind": "data",
                    "data_type": "tabular_data_ref",
                    "connected": False,
                },
                {
                    "key": "array_data",
                    "label": "Array Data",
                    "direction": "out",
                    "kind": "data",
                    "data_type": "array_data_ref",
                    "connected": False,
                },
            ]
            payload["preview"] = {
                "state": "ready",
                "message": "Tabular data preview is ready.",
                "content_kind": "tabular",
                "preview_kind": "table",
                "source": {
                    "path": "C:/tmp/plastic_strain.csv",
                    "resolved_path": "C:/tmp/plastic_strain.csv",
                    "format_id": "csv",
                    "size_class": "small",
                },
                "selector": {"selected_object": "", "requires_selection": False, "objects": []},
                "metadata": {"backend": "fixture"},
                "ref": {"resolver_id": "tabular.cache", "object_id": "table"},
                "window": {
                    "columns": ["Plastic Strain", "True Stress [MPa]"],
                    "rows": [
                        {"Plastic Strain": "0.0", "True Stress [MPa]": "616.3"},
                        {"Plastic Strain": "0.01", "True Stress [MPa]": "637.3"},
                        {"Plastic Strain": "0.02", "True Stress [MPa]": "652.9"},
                        {"Plastic Strain": "0.03", "True Stress [MPa]": "665.0"},
                        {"Plastic Strain": "0.04", "True Stress [MPa]": "674.9"},
                    ],
                    "row_offset": 0,
                    "column_offset": 0,
                    "total_rows": 10,
                    "total_columns": 2,
                    "bounded": True,
                    "client_side_full_scan": False,
                    "request": {"row_limit": 50, "column_limit": 50},
                },
            }

            host = create_component(graph_node_host_qml_path, {"nodeData": payload})
            window = attach_host_to_window(host, width=860, height=680)
            try:
                loader = host.findChild(QObject, "graphNodeSurfaceLoader")
                grid = host.findChild(QObject, "graphNodeTabularPreviewGrid")
                input_dot = named_child_items(host, "graphNodeInputPortDot")[0]
                output_dots = named_child_items(host, "graphNodeOutputPortDot")

                assert loader is not None
                assert grid is not None
                assert len(output_dots) == 2
                settle_events(6)

                metrics = variant_value(host.property("surfaceMetrics"))
                grid_top_left = grid.mapToItem(host, QPointF(0.0, 0.0))
                grid_bottom = float(grid_top_left.y()) + float(grid.height())
                input_dot_top = input_dot.mapToItem(host, QPointF(0.0, 0.0)).y()
                first_output_dot_top = output_dots[0].mapToItem(host, QPointF(0.0, 0.0)).y()

                assert bool(grid.property("visible"))
                assert float(host.height()) >= 420.0
                assert float(metrics["body_height"]) > 300.0, metrics
                assert grid_bottom <= float(metrics["port_top"]) + 0.5, (grid_bottom, metrics)
                assert grid_bottom <= float(input_dot_top) + 0.5, (grid_bottom, input_dot_top, metrics)
                assert grid_bottom <= float(first_output_dot_top) + 0.5, (grid_bottom, first_output_dot_top, metrics)
            finally:
                dispose_host_window(host, window)
                app.processEvents()
            """,
        )

    def test_standard_host_uses_extra_width_to_expand_metric_backed_label_columns(self) -> None:
        self._run_qml_probe(
            "port-label-extra-width-host",
            """
            payload = node_payload()
            payload["ports"][0]["label"] = "Primary Input Payload"
            payload["ports"][1]["label"] = "Dispatch Result Token"
            payload["width"] = 360.0
            payload["surface_metrics"]["default_width"] = 360.0

            measurement_host = create_component(graph_node_host_qml_path, {"nodeData": payload})
            measurement_input = named_child_items(measurement_host, "graphNodeInputPortLabel")[0]
            measurement_output = named_child_items(measurement_host, "graphNodeOutputPortLabel")[0]
            left_width = float(measurement_input.property("implicitWidth"))
            right_width = float(measurement_output.property("implicitWidth"))
            measurement_host.deleteLater()
            app.processEvents()

            metric_left_width = max(20.0, left_width - 12.0)
            metric_right_width = max(20.0, right_width - 12.0)
            port_gutter = 21.5
            center_gap = 24.0
            min_width = metric_left_width + metric_right_width + (port_gutter * 2.0) + center_gap
            payload["width"] = min_width + 24.0
            payload["surface_metrics"]["default_width"] = payload["width"]
            payload["surface_metrics"]["min_width"] = min_width
            payload["surface_metrics"]["standard_left_label_width"] = metric_left_width
            payload["surface_metrics"]["standard_right_label_width"] = metric_right_width
            payload["surface_metrics"]["standard_port_gutter"] = port_gutter
            payload["surface_metrics"]["standard_center_gap"] = center_gap
            payload["surface_metrics"]["standard_port_label_min_width"] = min_width

            host = create_component(graph_node_host_qml_path, {"nodeData": payload})
            input_label = named_child_items(host, "graphNodeInputPortLabel")[0]
            output_label = named_child_items(host, "graphNodeOutputPortLabel")[0]

            assert bool(host.property("_usesStandardPortLabelColumns"))
            assert float(input_label.width()) > metric_left_width + 10.0
            assert float(output_label.width()) > metric_right_width + 10.0
            assert abs(float(input_label.width()) - left_width) < 0.75
            assert abs(float(output_label.width()) - right_width) < 0.75
            """,
        )

    def test_standard_host_uses_tooltip_only_port_labels_when_preference_disabled(self) -> None:
        self._run_qml_probe(
            "tooltip-only-port-labels-host",
            """
            payload = {
                **node_payload(),
                "display_name": "Transform",
                "category_path": ["Data", "Control"],
                "help_text": "Runs the selected transformation.",
                "keywords": ["convert", "transform"],
            }
            payload["ports"][0] = {
                **payload["ports"][0],
                "label": "Primary Input Payload",
                "kind": "data",
                "data_type": "payload",
                "help_text": "Payload consumed by the transformation.",
                "flow_state": "waiting",
            }
            payload["ports"][1] = {
                **payload["ports"][1],
                "label": "Dispatch Result Token",
                "kind": "data",
                "data_type": "payload",
                "help_text": "Result emitted by the transformation.",
                "flow_state": "idle",
            }

            host = create_component(
                graph_node_host_qml_path,
                {
                    "nodeData": payload,
                    "showPortLabelsPreference": False,
                },
            )
            assert payload["ports"][0]["help_text"] == "Payload consumed by the transformation."
            projected_input_ports = variant_list(host.property("inputPorts"))
            assert projected_input_ports[0].get("help_text") == "Payload consumed by the transformation.", projected_input_ports
            input_label = named_child_items(host, "graphNodeInputPortLabel")[0]
            output_label = named_child_items(host, "graphNodeOutputPortLabel")[0]
            input_mouse = named_child_items(host, "graphNodeInputPortMouseArea")[0]
            output_mouse = named_child_items(host, "graphNodeOutputPortMouseArea")[0]
            node_title = named_child_items(host, "graphNodeTitle")[0]
            node_help_tooltip = host.findChild(QObject, "graphNodeHelpToolTip")

            assert bool(host.property("_tooltipOnlyPortLabelsActive"))
            assert not bool(host.property("_portLabelsVisible"))
            assert not bool(input_label.property("visible"))
            assert not bool(output_label.property("visible"))
            assert bool(input_mouse.property("tooltipOnlyPortLabelActive"))
            assert bool(output_mouse.property("tooltipOnlyPortLabelActive"))
            assert input_mouse.property("portLabelTooltipText") == "Primary Input Payload"
            assert output_mouse.property("portLabelTooltipText") == "Dispatch Result Token"
            assert "Payload consumed by the transformation." in input_mouse.property("portHelpTooltipText"), input_mouse.property("portHelpTooltipText")
            assert "Input, payload, Item" in input_mouse.property("portHelpTooltipText"), input_mouse.property("portHelpTooltipText")
            assert input_mouse.property("portHelpTooltipText").endswith("Empty"), input_mouse.property("portHelpTooltipText")
            assert "Result emitted by the transformation." in output_mouse.property("portHelpTooltipText"), output_mouse.property("portHelpTooltipText")
            assert "Output, payload, Item" in output_mouse.property("portHelpTooltipText"), output_mouse.property("portHelpTooltipText")
            assert output_mouse.property("portHelpTooltipText").endswith("No current output"), output_mouse.property("portHelpTooltipText")
            assert node_help_tooltip is not None, "missing graphNodeHelpToolTip"
            assert node_help_tooltip.property("category") == "general", node_help_tooltip.property("category")
            assert int(node_help_tooltip.property("textFormat")) == 1, node_help_tooltip.property("textFormat")
            assert node_help_tooltip.property("text") == (
                '<b>Transform</b><br><font color="#95a0b8">Data, Control</font>'
                '<br>Runs the selected transformation.<br><br>Keywords: convert, transform.'
            ), node_help_tooltip.property("text")
            assert input_label.property("helpTooltipCategory") == "general"
            assert output_label.property("helpTooltipCategory") == "general"
            assert input_label.property("helpTooltipText") == input_mouse.property("portHelpTooltipText")
            assert output_label.property("helpTooltipText") == output_mouse.property("portHelpTooltipText")

            window = attach_host_to_window(host)
            try:
                QTest.mouseMove(window, item_scene_point(node_title))
                QTest.qWait(50)
                settle_events(5)
                assert bool(node_help_tooltip.property("managedVisible"))
                QTest.mouseMove(window, item_scene_point(input_mouse))
                settle_events(5)
                assert bool(input_mouse.property("containsMouse"))
                assert bool(input_mouse.property("tooltipVisible"))
                host.setProperty("showPortLabelsPreference", True)
                settle_events(5)
                assert bool(input_label.property("visible"))
                QTest.mouseMove(window, item_scene_point(host))
                QTest.qWait(50)
                QTest.mouseMove(window, item_scene_point(input_label))
                QTest.qWait(50)
                settle_events(5)
                assert bool(input_label.property("helpTooltipHovered")), (
                    input_label.property("visible"),
                    input_label.property("width"),
                    input_label.property("height"),
                )
            finally:
                dispose_host_window(host, window)
            """,
        )

    def test_standard_host_marks_inactive_input_ports_with_muted_label_and_reason_tooltip(self) -> None:
        self._run_qml_probe(
            "inactive-input-port-ux-host",
            """
            payload = node_payload()
            payload["ports"][0]["key"] = "path"
            payload["ports"][0]["label"] = "path"
            payload["ports"][0]["kind"] = "data"
            payload["ports"][0]["data_type"] = "path"
            payload["ports"][0]["help_text"] = "Path supplied by the upstream result file."
            payload["ports"][0]["inactive"] = True
            payload["ports"][0]["inactive_reason"] = "Driven by result_file"

            host = create_component(graph_node_host_qml_path, {"nodeData": payload})
            input_dot = named_child_items(host, "graphNodeInputPortDot")[0]
            inactive_slash = named_child_items(host, "graphNodeInputPortInactiveSlash")[0]
            input_label = named_child_items(host, "graphNodeInputPortLabel")[0]
            input_mouse = named_child_items(host, "graphNodeInputPortMouseArea")[0]

            assert abs(float(input_dot.property("opacity")) - 0.46) < 0.01
            assert abs(float(input_label.property("opacity")) - 0.52) < 0.01
            assert bool(inactive_slash.property("visible"))
            assert input_label.property("helpTooltipCategory") == "general"
            assert "Path supplied by the upstream result file." in input_label.property("helpTooltipText")
            assert input_mouse.property("inactiveTooltipText") == "Driven by result_file"
            assert input_mouse.property("cursorShape") == Qt.CursorShape.ForbiddenCursor

            window = attach_host_to_window(host)
            try:
                QTest.mouseMove(window, item_scene_point(input_mouse))
                QTest.qWait(50)
                settle_events(5)
                assert bool(input_mouse.property("inactiveTooltipVisible"))
                assert input_mouse.property("activeTooltipCategory") == "inactive"

                QTest.mouseMove(window, item_scene_point(host))
                QTest.qWait(50)
                QTest.mouseMove(window, item_scene_point(input_label))
                QTest.qWait(50)
                settle_events(5)
                assert bool(input_label.property("helpTooltipHovered"))
                assert input_label.property("helpTooltipCategory") == "general"
            finally:
                dispose_host_window(host, window)
            """,
        )

    def test_flowchart_host_does_not_replace_surface_suppressed_labels_with_tooltips(self) -> None:
        self._run_qml_probe(
            "flowchart-no-tooltip-port-labels-host",
            """
            host = create_component(
                graph_node_host_qml_path,
                {
                    "nodeData": flowchart_payload("decision"),
                    "showPortLabelsPreference": False,
                },
            )

            assert not bool(host.property("_portLabelsVisible"))
            assert not bool(host.property("_tooltipOnlyPortLabelsActive"))
            assert not bool(host.property("_usesStandardPortLabelColumns"))
            """,
        )

    def test_graph_node_host_node_execution_visualization_states_drive_timer_priority_and_cache_keys(self) -> None:
        self._run_qml_probe(
            "host-node-execution-visualization",
            """
            from PyQt6.QtCore import pyqtProperty, pyqtSignal
            from PyQt6.QtGui import QColor
            from PyQt6.QtTest import QTest
            import time

            class ExecutionSceneBridge(QObject):
                selected_node_lookup_changed = pyqtSignal()

                def __init__(self):
                    super().__init__()
                    self._selected_node_lookup = {}

                @pyqtProperty("QVariantMap", notify=selected_node_lookup_changed)
                def selected_node_lookup(self):
                    return dict(self._selected_node_lookup)

            class ExecutionCanvasItem(QQuickItem):
                failed_node_lookup_changed = pyqtSignal()
                running_node_lookup_changed = pyqtSignal()
                completed_node_lookup_changed = pyqtSignal()
                warning_node_lookup_changed = pyqtSignal()
                running_node_started_at_ms_lookup_changed = pyqtSignal()
                node_elapsed_ms_lookup_changed = pyqtSignal()
                node_execution_revision_changed = pyqtSignal()

                def __init__(self):
                    super().__init__()
                    self._scene_bridge = ExecutionSceneBridge()
                    self._failed_node_lookup = {}
                    self._running_node_lookup = {}
                    self._completed_node_lookup = {}
                    self._warning_node_lookup = {}
                    self._running_node_started_at_ms_lookup = {}
                    self._node_elapsed_ms_lookup = {}
                    self._node_execution_revision = 0

                @pyqtProperty(QObject, constant=True)
                def sceneBridge(self):
                    return self._scene_bridge

                # The host reads execution facts through the shared
                # executionFacts object; this stub exposes the same fact
                # property names directly, so it doubles as its own facts ref.
                @pyqtProperty(QObject, constant=True)
                def executionFacts(self):
                    return self

                @pyqtProperty("QVariantMap", constant=True)
                def freshRunNodeLookup(self):
                    return {}

                @pyqtProperty("QVariantMap", constant=True)
                def selectedRunPreviewNodeLookup(self):
                    return {}

                @pyqtProperty(str, constant=True)
                def nodeElapsedTimeUnit(self):
                    return "seconds"

                @pyqtProperty("QVariantMap", notify=failed_node_lookup_changed)
                def failedNodeLookup(self):
                    return dict(self._failed_node_lookup)

                @pyqtProperty("QVariantMap", notify=running_node_lookup_changed)
                def runningNodeLookup(self):
                    return dict(self._running_node_lookup)

                @pyqtProperty("QVariantMap", notify=completed_node_lookup_changed)
                def completedNodeLookup(self):
                    return dict(self._completed_node_lookup)

                @pyqtProperty("QVariantMap", notify=warning_node_lookup_changed)
                def warningNodeLookup(self):
                    return dict(self._warning_node_lookup)

                @pyqtProperty("QVariantMap", notify=running_node_started_at_ms_lookup_changed)
                def runningNodeStartedAtMsLookup(self):
                    return dict(self._running_node_started_at_ms_lookup)

                @pyqtProperty("QVariantMap", notify=node_elapsed_ms_lookup_changed)
                def nodeElapsedMsLookup(self):
                    return dict(self._node_elapsed_ms_lookup)

                @pyqtProperty(int, notify=node_execution_revision_changed)
                def nodeExecutionRevision(self):
                    return int(self._node_execution_revision)

                def set_running(self, node_id, started_at_ms):
                    self._running_node_lookup = {str(node_id): True}
                    self._completed_node_lookup = {}
                    self._warning_node_lookup = {}
                    self._running_node_started_at_ms_lookup = {str(node_id): float(started_at_ms)}
                    self._node_execution_revision += 1
                    self.running_node_lookup_changed.emit()
                    self.completed_node_lookup_changed.emit()
                    self.warning_node_lookup_changed.emit()
                    self.running_node_started_at_ms_lookup_changed.emit()
                    self.node_execution_revision_changed.emit()

                def set_completed(self, node_id, elapsed_ms):
                    self._running_node_lookup = {}
                    self._completed_node_lookup = {str(node_id): True}
                    self._warning_node_lookup = {}
                    self._running_node_started_at_ms_lookup = {}
                    self._node_elapsed_ms_lookup = {str(node_id): float(elapsed_ms)}
                    self._node_execution_revision += 1
                    self.running_node_lookup_changed.emit()
                    self.completed_node_lookup_changed.emit()
                    self.warning_node_lookup_changed.emit()
                    self.running_node_started_at_ms_lookup_changed.emit()
                    self.node_elapsed_ms_lookup_changed.emit()
                    self.node_execution_revision_changed.emit()

                def set_warning_completed(self, node_id, elapsed_ms):
                    self._running_node_lookup = {}
                    self._completed_node_lookup = {str(node_id): True}
                    self._warning_node_lookup = {str(node_id): True}
                    self._running_node_started_at_ms_lookup = {}
                    self._node_elapsed_ms_lookup = {str(node_id): float(elapsed_ms)}
                    self._node_execution_revision += 1
                    self.running_node_lookup_changed.emit()
                    self.completed_node_lookup_changed.emit()
                    self.warning_node_lookup_changed.emit()
                    self.running_node_started_at_ms_lookup_changed.emit()
                    self.node_elapsed_ms_lookup_changed.emit()
                    self.node_execution_revision_changed.emit()

                def clear_cached_elapsed(self):
                    self._node_elapsed_ms_lookup = {}
                    self._node_execution_revision += 1
                    self.node_elapsed_ms_lookup_changed.emit()
                    self.node_execution_revision_changed.emit()

                def set_failed(self, node_id):
                    self._failed_node_lookup = {str(node_id): True}
                    self.failed_node_lookup_changed.emit()

            canvas_item = ExecutionCanvasItem()
            host = create_component(
                graph_node_host_qml_path,
                {
                    "nodeData": node_payload(),
                    "canvasItem": canvas_item,
                    "showShadow": True,
                },
            )
            background_layer = host.findChild(QObject, "graphNodeChromeBackgroundLayer")
            elapsed_timer = host.findChild(QObject, "graphNodeElapsedTimer")

            assert background_layer is not None
            assert elapsed_timer is not None
            for removed_name in (
                "graphNodeFailureHalo",
                "graphNodeFailurePulseHalo",
                "graphNodeRunningHalo",
                "graphNodeRunningPulseHalo",
                "graphNodeCompletedFlashHalo",
                "graphNodeSelectedRunPreviewHalo",
                "graphNodeRunFreshHalo",
            ):
                assert host.findChild(QObject, removed_name) is None

            started_at_ms = (time.time() * 1000.0) - 1800.0
            completed_elapsed_ms = 3487.0
            idle_key = str(background_layer.property("cacheKey") or "")
            canvas_item.set_running("node_surface_host_test", started_at_ms)
            app.processEvents()
            assert bool(host.property("isRunningNode"))
            assert not bool(host.property("isCompletedNode"))
            assert bool(host.property("renderActive"))
            assert int(host.property("z")) == 31
            assert str(background_layer.property("effectiveBorderState")) == "idle"
            assert QColor(host.property("surfaceColor")).name().lower() == "#403c2d"
            assert QColor(background_layer.property("effectiveOutlineColor")).name().lower() == "#81795c"
            assert bool(elapsed_timer.property("visible"))
            assert bool(elapsed_timer.property("liveElapsedActive"))
            assert abs(float(elapsed_timer.property("startedAtMs")) - started_at_ms) < 16.0
            running_key = str(background_layer.property("cacheKey") or "")
            assert running_key == idle_key

            QTest.qWait(80)
            app.processEvents()
            assert float(elapsed_timer.property("elapsedMilliseconds")) >= 1400.0

            canvas_item.set_completed("node_surface_host_test", completed_elapsed_ms)
            app.processEvents()
            QTest.qWait(80)
            app.processEvents()

            assert not bool(host.property("isRunningNode"))
            assert bool(host.property("isCompletedNode"))
            assert bool(host.property("renderActive"))
            assert int(host.property("z")) == 30
            assert str(background_layer.property("effectiveBorderState")) == "idle"
            assert bool(elapsed_timer.property("visible"))
            assert not bool(elapsed_timer.property("liveElapsedActive"))
            assert bool(elapsed_timer.property("cachedElapsedActive"))
            assert abs(float(elapsed_timer.property("cachedElapsedMilliseconds")) - completed_elapsed_ms) < 0.01
            assert str(elapsed_timer.property("text") or "") == "3.5s"
            assert float(elapsed_timer.property("opacity")) == float(host.property("completedElapsedFooterOpacity"))
            completed_key = str(background_layer.property("cacheKey") or "")
            assert completed_key == running_key

            canvas_item.set_warning_completed("node_surface_host_test", completed_elapsed_ms)
            app.processEvents()
            QTest.qWait(80)
            app.processEvents()

            assert bool(host.property("isWarningNode"))
            assert bool(host.property("isCompletedNode"))
            assert str(background_layer.property("effectiveBorderState")) == "warning"
            assert QColor(host.property("surfaceColor")).name().lower() == "#5a4a28"
            assert QColor(host.property("bodyGradientEndColor")).name().lower() == "#4e4024"
            assert QColor(background_layer.property("effectiveOutlineColor")).name().lower() == "#d9a93c"
            assert bool(elapsed_timer.property("cachedElapsedActive"))
            assert float(elapsed_timer.property("opacity")) == float(host.property("warningElapsedFooterOpacity"))
            warning_key = str(background_layer.property("cacheKey") or "")
            assert warning_key != completed_key
            assert "|warning|" in warning_key

            canvas_item.clear_cached_elapsed()
            app.processEvents()

            assert not bool(elapsed_timer.property("visible"))
            assert not bool(elapsed_timer.property("cachedElapsedActive"))

            canvas_item.set_failed("node_surface_host_test")
            app.processEvents()

            assert bool(host.property("isFailedNode"))
            assert str(background_layer.property("effectiveBorderState")) == "failed"
            assert QColor(host.property("surfaceColor")).name().lower() == "#5d2f30"
            assert QColor(host.property("bodyGradientEndColor")).name().lower() == "#51292a"
            assert QColor(background_layer.property("effectiveOutlineColor")).name().lower() == "#e36155"
            assert "|error|" in str(background_layer.property("cacheKey") or "")
            """,
        )

    def test_graph_node_host_persistent_diagnostic_uses_warning_badge_and_execution_precedence(self) -> None:
        self._run_qml_probe(
            "persistent-node-diagnostic-warning-badge",
            """
            from PyQt6.QtCore import pyqtProperty, pyqtSignal

            class DiagnosticSceneBridge(QObject):
                @pyqtProperty("QVariantMap", constant=True)
                def selected_node_lookup(self):
                    return {}

            class DiagnosticCanvasItem(QQuickItem):
                state_changed = pyqtSignal()

                def __init__(self):
                    super().__init__()
                    self._scene_bridge = DiagnosticSceneBridge()
                    self.failed = False
                    self.running = False
                    self.diagnostic = False

                @pyqtProperty(QObject, constant=True)
                def sceneBridge(self):
                    return self._scene_bridge

                @pyqtProperty(QObject, constant=True)
                def executionFacts(self):
                    return self

                def lookup(self, active):
                    return {"node_surface_host_test": True} if active else {}

                @pyqtProperty("QVariantMap", notify=state_changed)
                def failedNodeLookup(self):
                    return self.lookup(self.failed)

                @pyqtProperty("QVariantMap", notify=state_changed)
                def runningNodeLookup(self):
                    return self.lookup(self.running)

                @pyqtProperty("QVariantMap", notify=state_changed)
                def completedNodeLookup(self):
                    return {}

                @pyqtProperty("QVariantMap", notify=state_changed)
                def warningNodeLookup(self):
                    return {}

                @pyqtProperty("QVariantMap", notify=state_changed)
                def nodeDiagnosticLookup(self):
                    if not self.diagnostic:
                        return {}
                    return {
                        "node_surface_host_test": {
                            "severity": "warning",
                            "kind": "runtime_warning",
                            "tooltip_text": "2 warnings\\n- Mesh quality was reduced.\\n- Result path is missing.",
                            "rows": [
                                {"message": "Mesh quality was reduced."},
                                {"message": "Result path is missing."},
                            ],
                        }
                    }

                @pyqtProperty("QVariantMap", constant=True)
                def freshRunNodeLookup(self):
                    return {}

                @pyqtProperty("QVariantMap", constant=True)
                def selectedRunPreviewNodeLookup(self):
                    return {}

                @pyqtProperty("QVariantMap", constant=True)
                def runningNodeStartedAtMsLookup(self):
                    return {}

                @pyqtProperty("QVariantMap", constant=True)
                def nodeElapsedMsLookup(self):
                    return {}

                @pyqtProperty(str, constant=True)
                def nodeElapsedTimeUnit(self):
                    return "seconds"

                @pyqtProperty(int, notify=state_changed)
                def nodeExecutionRevision(self):
                    return int(self.failed) + int(self.running) + int(self.diagnostic)

                def set_state(self, *, diagnostic, running, failed):
                    self.diagnostic = bool(diagnostic)
                    self.running = bool(running)
                    self.failed = bool(failed)
                    self.state_changed.emit()

            canvas_item = DiagnosticCanvasItem()
            from ea_node_editor.graph.records import NodeInstance
            from ea_node_editor.nodes.bootstrap import build_default_registry
            from ea_node_editor.ui_qml.graph_geometry.standard_metrics import node_surface_metrics

            spec = build_default_registry().get_spec("ssh_sftp.run_command")
            node = NodeInstance(node_id="node_surface_host_test", type_id=spec.type_id,
                title=spec.display_name, x=120, y=120)
            metrics = node_surface_metrics(node, spec, graph_label_pixel_size=16,
                graph_node_icon_pixel_size=16)
            payload = node_payload()
            payload.update(title=node.title, type_id=node.type_id,
                width=metrics.default_width, height=metrics.default_height,
                surface_metrics=metrics.to_payload(),
                inline_properties=[],
                ports=[{"key": port.key, "label": port.label or port.key,
                    "direction": port.direction, "kind": port.kind,
                    "data_type": port.data_type, "connected": False} for port in spec.ports],
                icon_source=QUrl.fromLocalFile(str(repo_root / "ea_node_editor/assets/node_title_icons/ssh_sftp/terminal.svg")).toString())
            host = create_component(
                graph_node_host_qml_path,
                {"nodeData": payload, "canvasItem": canvas_item, "graphLabelPixelSize": 16},
            )
            title = host.findChild(QObject, "graphNodeTitle")
            failure_badge = host.findChild(QObject, "graphNodeFailureBadge")
            original_width = host.width()
            original_title_width = title.width()

            def assert_external_badge(indicator):
                assert indicator.y() < 0
                assert abs(indicator.y() + indicator.height() * 0.5) < 0.1
                assert indicator.width() == indicator.height()
                assert abs(host.width() - original_width) < 0.1
                assert abs(title.width() - original_title_width) < 0.1
                assert not title.property("truncated"), title.property("text")

            background = host.findChild(QObject, "graphNodeChromeBackgroundLayer")
            badge = host.findChild(QObject, "graphNodeWarningBadge")
            tooltip = host.findChild(QObject, "graphNodeWarningToolTip")
            tooltip_table = host.findChild(QObject, "graphNodeWarningToolTipTable")
            tooltip_header = host.findChild(QObject, "graphNodeWarningToolTipHeader")
            assert background is not None
            assert badge is not None
            assert tooltip is not None
            assert tooltip_table is not None
            assert tooltip_header is not None

            canvas_item.set_state(diagnostic=True, running=False, failed=False)
            app.processEvents()
            tooltip_rows = sorted(
                (
                    child
                    for child in tooltip_table.childItems()
                    if str(child.property("objectName") or "").startswith(
                        "graphNodeWarningToolTipRow"
                    )
                ),
                key=lambda child: str(child.property("objectName") or ""),
            )
            assert len(tooltip_rows) == 2
            row_zero_children = tooltip_rows[0].childItems()
            row_one_children = tooltip_rows[1].childItems()
            tooltip_index_zero = next(
                child
                for child in row_zero_children
                if child.property("objectName") == "graphNodeWarningToolTipIndex0"
            )
            tooltip_index_one = next(
                child
                for child in row_one_children
                if child.property("objectName") == "graphNodeWarningToolTipIndex1"
            )
            tooltip_message_one = next(
                child
                for child in row_one_children
                if child.property("objectName") == "graphNodeWarningToolTipMessage1"
            )
            assert bool(host.property("isDiagnosticWarningNode"))
            assert str(background.property("effectiveBorderState")) == "warning"
            assert bool(badge.property("visible"))
            assert_external_badge(badge)
            assert tooltip.property("category") == "warning"
            assert "Mesh quality was reduced." in tooltip.property("text")
            assert tooltip_header.property("text") == "2 warnings", tooltip_header.property("text")
            assert tooltip_index_zero.property("text") == "0", tooltip_index_zero.property("text")
            assert tooltip_index_one.property("text") == "1", tooltip_index_one.property("text")
            assert tooltip_message_one.property("text") == "Result path is missing.", tooltip_message_one.property("text")

            window = attach_host_to_window(host, 800, 480)
            try:
                QTest.mouseMove(window, item_scene_point(badge, y_factor=0.25))
                QTest.qWait(50)
                settle_events(5)
                assert bool(tooltip.property("managedVisible")), (item_scene_point(badge),
                    host.width(), window.width(), tooltip.property("active"))
                assert int(tooltip_table.property("width")) == 360, tooltip_table.property("width")

                canvas_item.set_state(diagnostic=True, running=True, failed=False)
                app.processEvents()
                assert str(background.property("effectiveBorderState")) == "warning"
                assert bool(badge.property("visible"))

                canvas_item.set_state(diagnostic=True, running=True, failed=True)
                app.processEvents()
                assert str(background.property("effectiveBorderState")) == "failed"
                assert not bool(badge.property("visible"))
                assert bool(failure_badge.property("visible"))
                assert_external_badge(failure_badge)
                for pixel_size in (8, 30, 50):
                    metrics = node_surface_metrics(node, spec, graph_label_pixel_size=pixel_size,
                        graph_node_icon_pixel_size=pixel_size)
                    payload.update(surface_metrics=metrics.to_payload(), width=1,
                        height=metrics.default_height)
                    host.setProperty("graphLabelPixelSize", pixel_size)
                    host.setProperty("nodeData", payload)
                    settle_events(3)
                    assert host.width() >= metrics.min_width
                    original_width = host.width()
                    original_title_width = title.width()
                    assert_external_badge(failure_badge)
                    canvas_item.set_state(diagnostic=True, running=False, failed=False)
                    settle_events(3)
                    assert_external_badge(badge)
                    canvas_item.set_state(diagnostic=True, running=False, failed=True)
                    settle_events(3)
            finally:
                dispose_host_window(host, window)
            """,
        )

    def test_persistent_node_elapsed_footer_graph_node_host_reuses_canvas_timing_and_clears_on_invalidation(self) -> None:
        self.test_graph_node_host_node_execution_visualization_states_drive_timer_priority_and_cache_keys()

    def test_flowchart_host_shadow_visibility_follows_global_shadow_preference(self) -> None:
        self._run_qml_probe(
            "flowchart-host-shadow-visibility",
            """
            host = create_component(
                graph_node_host_qml_path,
                {
                    "nodeData": flowchart_payload("decision"),
                    "showShadow": True,
                },
            )
            background_layer = host.findChild(QObject, "graphNodeChromeBackgroundLayer")
            shadow_item = host.findChild(QObject, "graphNodeShadow")
            flowchart_shadow = host.findChild(QObject, "graphNodeFlowchartShadow")
            chrome_item = host.findChild(QObject, "graphNodeChrome")
            flowchart_surface = host.findChild(QObject, "graphNodeFlowchartSurface")

            assert bool(host.property("isFlowchartSurface"))
            assert not bool(host.property("_useHostChrome"))
            assert background_layer is not None
            assert shadow_item is not None
            assert flowchart_shadow is not None
            assert chrome_item is not None
            assert flowchart_surface is not None
            assert not bool(background_layer.property("cacheActive"))
            assert not bool(background_layer.property("chromeCacheActive"))
            assert not bool(background_layer.property("shadowCacheActive"))
            assert not bool(chrome_item.property("visible"))
            assert not bool(shadow_item.property("visible"))
            assert bool(flowchart_surface.property("shapeShadowVisible"))
            assert bool(flowchart_surface.property("shapeShadowCacheActive"))
            assert bool(flowchart_shadow.property("visible"))
            assert bool(flowchart_shadow.property("cacheActive"))

            host.setProperty("showShadow", False)
            app.processEvents()

            assert not bool(background_layer.property("cacheActive"))
            assert not bool(background_layer.property("shadowCacheActive"))
            assert not bool(shadow_item.property("visible"))
            assert not bool(flowchart_surface.property("shapeShadowVisible"))
            assert not bool(flowchart_surface.property("shapeShadowCacheActive"))
            assert not bool(flowchart_shadow.property("visible"))
            """,
        )

    def test_flowchart_host_shadow_cache_key_tracks_shadow_preferences_without_host_chrome(self) -> None:
        self._run_qml_probe(
            "flowchart-host-shadow-cache-key",
            """
            host = create_component(
                graph_node_host_qml_path,
                {
                    "nodeData": flowchart_payload("decision"),
                    "showShadow": True,
                },
            )
            background_layer = host.findChild(QObject, "graphNodeChromeBackgroundLayer")
            shadow_item = host.findChild(QObject, "graphNodeShadow")
            flowchart_shadow = host.findChild(QObject, "graphNodeFlowchartShadow")
            chrome_item = host.findChild(QObject, "graphNodeChrome")
            flowchart_surface = host.findChild(QObject, "graphNodeFlowchartSurface")

            assert background_layer is not None
            assert shadow_item is not None
            assert flowchart_shadow is not None
            assert chrome_item is not None
            assert flowchart_surface is not None
            assert not bool(background_layer.property("cacheActive"))
            assert not bool(background_layer.property("chromeCacheActive"))
            assert not bool(background_layer.property("shadowCacheActive"))
            assert not bool(chrome_item.property("visible"))
            assert not bool(shadow_item.property("visible"))
            assert bool(flowchart_shadow.property("cacheActive"))

            baseline_key = str(flowchart_shadow.property("cacheKey") or "")
            assert baseline_key

            host.setProperty("viewportInteractionCacheActive", True)
            app.processEvents()
            assert str(flowchart_shadow.property("cacheKey") or "") == baseline_key

            host.setProperty("snapshotReuseActive", True)
            app.processEvents()
            assert str(flowchart_shadow.property("cacheKey") or "") == baseline_key

            host.setProperty("_liveWidth", 248.0)
            host.setProperty("_liveHeight", 132.0)
            host.setProperty("_liveGeometryActive", True)
            app.processEvents()
            geometry_key = str(flowchart_shadow.property("cacheKey") or "")
            assert geometry_key != baseline_key

            host.setProperty("_liveGeometryActive", False)
            host.setProperty("shadowSoftness", 41)
            app.processEvents()
            shadow_preference_key = str(flowchart_shadow.property("cacheKey") or "")
            assert shadow_preference_key != baseline_key
            assert shadow_preference_key != geometry_key

            host.setProperty("showShadow", False)
            app.processEvents()
            disabled_shadow_key = str(flowchart_shadow.property("cacheKey") or "")
            assert disabled_shadow_key != shadow_preference_key
            assert not bool(background_layer.property("cacheActive"))
            assert not bool(flowchart_shadow.property("cacheActive"))
            """,
        )

    def test_passive_graph_node_host_top_left_resize_handle_previews_anchored_geometry(self) -> None:
        self._run_qml_probe(
            "passive-host-top-left-resize-preview",
            """
            from PyQt6.QtCore import QPoint
            from PyQt6.QtTest import QTest

            payload = node_payload()
            payload["type_id"] = "tests.passive.resize"
            payload["runtime_behavior"] = "passive"
            host = create_component(graph_node_host_qml_path, {"nodeData": payload})
            preview_events = []
            finish_events = []
            host.resizePreviewChanged.connect(
                lambda node_id, x, y, width, height, active: preview_events.append(
                    (node_id, x, y, width, height, active)
                )
            )
            host.resizeFinished.connect(
                lambda node_id, x, y, width, height: finish_events.append((node_id, x, y, width, height))
            )

            window = attach_host_to_window(host)
            hover_host_local_point(window, host, 40.0, 24.0)

            top_left_handle = [
                handle
                for handle in named_child_items(host, "graphNodeResizeHandle")
                if str(handle.property("cornerRole")) == "topLeft"
            ][0]
            start_point = item_scene_point(top_left_handle, 0.25, 0.25)
            end_point = QPoint(start_point.x() - 30, start_point.y() - 20)

            mouse_click(window, start_point)
            settle_events(2)
            assert finish_events == []
            assert not bool(host.property("_liveGeometryActive"))

            QTest.mousePress(window, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, start_point)
            settle_events(2)
            QTest.mouseMove(window, end_point)
            settle_events(2)

            assert bool(host.property("_liveGeometryActive"))
            assert abs(float(host.x()) - 90.0) < 0.75
            assert abs(float(host.y()) - 100.0) < 0.75
            assert abs(float(host.width()) - 240.0) < 0.75
            assert abs(float(host.height()) - 108.0) < 0.75
            assert any(
                entry[0] == "node_surface_host_test"
                and abs(float(entry[1]) - 90.0) < 0.75
                and abs(float(entry[2]) - 100.0) < 0.75
                and abs(float(entry[3]) - 240.0) < 0.75
                and abs(float(entry[4]) - 108.0) < 0.75
                and bool(entry[5])
                for entry in preview_events
            )

            QTest.mouseRelease(window, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, end_point)
            settle_events(2)

            assert finish_events == [("node_surface_host_test", 90.0, 100.0, 240.0, 108.0)]
            assert not bool(host.property("_liveGeometryActive"))

            dispose_host_window(host, window)
            engine.deleteLater()
            app.processEvents()
            """,
        )

    def test_bare_text_resize_handle_ignores_vertical_pointer_delta(self) -> None:
        self._run_qml_probe(
            "bare-text-horizontal-only-resize",
            """
            from PyQt6.QtCore import QPoint
            from PyQt6.QtTest import QTest

            payload = node_payload(surface_family="annotation", surface_variant="text")
            payload.update({
                "type_id": "passive.annotation.text",
                "runtime_behavior": "passive",
                "surface_spec": surface_spec_payload_for_values(
                    type_id="passive.annotation.text",
                    family="annotation",
                    variant="text",
                ),
                "properties": {"text": "Text", "format": "markdown"},
            })
            host = create_component(graph_node_host_qml_path, {"nodeData": payload})
            finish_events = []
            host.resizeFinished.connect(
                lambda node_id, x, y, width, height: finish_events.append((node_id, x, y, width, height))
            )
            window = attach_host_to_window(host)
            settle_events(5)
            try:
                hover_host_local_point(window, host, 40.0, 24.0)
                handle = [
                    item
                    for item in named_child_items(host, "graphNodeResizeHandle")
                    if str(item.property("cornerRole")) == "topLeft"
                ][0]
                drag_area = handle.findChild(QObject, "graphNodeResizeDragArea")
                surface = host.findChild(QObject, "graphBareTextSurface")
                rendered = host.findChild(QObject, "graphBareTextRenderedText")
                editor = host.findChild(QObject, "graphBareTextEditor")
                assert drag_area is not None
                assert surface is not None
                assert rendered is not None
                assert editor is not None

                mouse_double_click(window, item_scene_point(rendered))
                settle_events(5)
                assert bool(editor.property("visible"))
                editor.setProperty("text", "\\n".join(f"Line {index}" for index in range(12)))
                settle_events(5)
                assert bool(host.property("_liveGeometryActive"))
                assert abs(float(host.height()) - float(surface.property("requiredHeight"))) < 0.5
                assert float(host.height()) > 88.0
                QTest.keyClick(window, Qt.Key.Key_Escape)
                settle_events(5)
                assert not bool(editor.property("visible"))
                assert not bool(host.property("_liveGeometryActive"))
                finish_events.clear()

                start = item_scene_point(handle, 0.25, 0.25)
                end = QPoint(start.x() - 30, start.y() - 20)
                QTest.mouseMove(window, start)
                settle_events(2)
                assert drag_area.property("cursorShape") == Qt.CursorShape.SizeHorCursor

                QTest.mousePress(window, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, start)
                QTest.mouseMove(window, end)
                settle_events(5)

                assert abs(float(host.x()) - 90.0) < 0.75
                assert abs(float(host.y()) - 120.0) < 0.75
                assert abs(float(host.width()) - 240.0) < 0.75
                assert abs(float(host.height()) - float(surface.property("requiredHeight"))) < 0.5

                QTest.mouseRelease(window, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, end)
                settle_events(5)
                assert any(
                    abs(float(event[2]) - 120.0) < 0.75
                    and abs(float(event[3]) - 240.0) < 0.75
                    and abs(float(event[4]) - float(surface.property("requiredHeight"))) < 0.5
                    for event in finish_events
                ), finish_events
            finally:
                dispose_host_window(host, window)
                engine.deleteLater()
                app.processEvents()
            """,
        )

    def test_graph_node_host_right_handle_double_click_fits_displayed_path_text(self) -> None:
        self._run_qml_probe(
            "host-right-handle-double-click-path-fit",
            """
            from ea_node_editor.ui.shell.runtime_history import RuntimeGraphHistory

            registry = build_default_registry()

            def run_fit_case(corner_role, path_text, mode, show_full_path):
                model = GraphModel()
                workspace_id = model.active_workspace.workspace_id
                workspace = model.project.workspaces[workspace_id]
                scene = GraphSceneBridge()
                scene.set_workspace(model, registry, workspace_id)
                node_id = scene.add_node_from_type("io.path_pointer", 120.0, 120.0)
                scene.set_node_property(node_id, "path", path_text)
                scene.set_node_property(node_id, "mode", mode)
                scene.set_node_property(node_id, "show_full_path", show_full_path)

                history = RuntimeGraphHistory()
                scene.bind_runtime_history(history)
                history.clear_workspace(workspace_id)

                view = ViewportBridge()
                view.set_viewport_size(4200.0, 900.0)
                canvas = create_component(
                    graph_canvas_qml_path,
                    {
                        "sceneBridge": scene,
                        "viewBridge": view,
                        "width": 4200.0,
                        "height": 900.0,
                    },
                )
                window = attach_host_to_window(canvas, width=4200, height=900)
                settle_events(4)

                card = [
                    item
                    for item in named_child_items(canvas, "graphNodeCard")
                    if item.property("nodeData")["node_id"] == node_id
                ][0]
                path_field = named_item(card, "graphNodeInlinePathEditor", "path")
                handle = [
                    item
                    for item in named_child_items(card, "graphNodeResizeHandle")
                    if str(item.property("cornerRole")) == corner_role
                ][0]
                left_corner_role = "topLeft" if corner_role == "topRight" else "bottomLeft"
                left_handle = [
                    item
                    for item in named_child_items(card, "graphNodeResizeHandle")
                    if str(item.property("cornerRole")) == left_corner_role
                ][0]
                before = next(item for item in scene.nodes_model if item["node_id"] == node_id)
                before_geometry = (before["x"], before["y"], before["width"], before["height"])
                expected_text = path_text if show_full_path else path_text.replace("\\\\", "/").rstrip("/").split("/")[-1]
                assert str(path_field.property("text")) == expected_text

                finish_events = []
                card.resizeFinished.connect(
                    lambda emitted_id, x, y, width, height: finish_events.append(
                        (emitted_id, x, y, width, height)
                    )
                )
                left_point = item_scene_point(
                    left_handle,
                    0.25,
                    0.25 if left_corner_role == "topLeft" else 0.75,
                )
                QTest.mouseMove(window, left_point)
                settle_events(3)
                mouse_double_click(window, left_point)
                settle_events(3)
                after_left = next(item for item in scene.nodes_model if item["node_id"] == node_id)
                assert (
                    after_left["x"],
                    after_left["y"],
                    after_left["width"],
                    after_left["height"],
                ) == before_geometry
                assert finish_events == []
                assert history.undo_depth(workspace_id) == 0

                point = item_scene_point(
                    handle,
                    0.75,
                    0.25 if corner_role == "topRight" else 0.75,
                )
                QTest.mouseMove(window, point)
                settle_events(3)
                mouse_double_click(window, point)
                settle_events(6)

                after = next(item for item in scene.nodes_model if item["node_id"] == node_id)
                after_geometry = (after["x"], after["y"], after["width"], after["height"])
                assert len(finish_events) == 1, (corner_role, finish_events)
                assert after_geometry[2] > before_geometry[2], (corner_role, before_geometry, after_geometry)
                assert after_geometry[0] == before_geometry[0], (corner_role, before_geometry, after_geometry)
                assert after_geometry[1] == before_geometry[1], (corner_role, before_geometry, after_geometry)
                assert after_geometry[3] == before_geometry[3], (corner_role, before_geometry, after_geometry)
                assert bool(after["properties"]["show_full_path"]) is show_full_path, after["properties"]
                assert after["properties"]["mode"] == mode, after["properties"]
                assert after["properties"]["path"] == path_text, after["properties"]
                assert str(path_field.property("text")) == expected_text, (
                    corner_role,
                    path_field.property("text"),
                    expected_text,
                )
                available_text_width = (
                    float(path_field.width())
                    - float(path_field.property("leftPadding"))
                    - float(path_field.property("rightPadding"))
                )
                assert available_text_width + 1.0 >= float(path_field.property("contentWidth")), (
                    corner_role,
                    available_text_width,
                    path_field.property("contentWidth"),
                    after_geometry,
                )
                assert history.undo_depth(workspace_id) == 1, history.undo_depth(workspace_id)
                assert abs(float(workspace.nodes[node_id].custom_width) - after_geometry[2]) < 0.01
                if show_full_path:
                    assert after_geometry[2] > 1400.0, after_geometry

                already_fit_point = item_scene_point(
                    handle,
                    0.75,
                    0.25 if corner_role == "topRight" else 0.75,
                )
                QTest.mouseMove(window, already_fit_point)
                settle_events(3)
                mouse_double_click(window, already_fit_point)
                settle_events(4)
                already_fit = next(item for item in scene.nodes_model if item["node_id"] == node_id)
                assert (
                    already_fit["x"],
                    already_fit["y"],
                    already_fit["width"],
                    already_fit["height"],
                ) == after_geometry
                assert len(finish_events) == 1, finish_events
                assert history.undo_depth(workspace_id) == 1

                assert history.undo_workspace(workspace_id, workspace) is not None
                scene.refresh_workspace_from_model(workspace_id)
                assert workspace.nodes[node_id].custom_width is None
                assert history.redo_workspace(workspace_id, workspace) is not None
                scene.refresh_workspace_from_model(workspace_id)
                assert abs(float(workspace.nodes[node_id].custom_width) - after_geometry[2]) < 0.01

                dispose_host_window(canvas, window)
                app.processEvents()

            long_filename = "result_" + ("very_long_segment_" * 14) + ".rst"
            run_fit_case(
                "topRight",
                "C:/projects/corex/results/" + long_filename,
                "file",
                False,
            )
            run_fit_case(
                "bottomRight",
                "C:/" + ("deep_directory/" * 90) + "result.rst",
                "folder",
                True,
            )
            engine.deleteLater()
            app.processEvents()
            """,
        )

    def test_graph_node_host_routes_body_click_open_and_context_from_below_surface_layer(self) -> None:
        self._run_qml_probe(
            "host-body-interactions-below-surface",
            """
            from PyQt6.QtQml import QQmlProperty

            payload = node_payload()
            payload["inline_properties"] = []
            host = create_component(graph_node_host_qml_path, {"nodeData": payload})
            loader = host.findChild(QObject, "graphNodeSurfaceLoader")
            gesture_layer = host.findChild(QObject, "graphNodeHostGestureLayer")
            drag_area = host.findChild(QObject, "graphNodeDragArea")

            assert loader is not None
            assert gesture_layer is not None
            assert drag_area is not None
            assert drag_area.parentItem().objectName() == "graphNodeHostGestureLayer"

            surface_layer = loader.parentItem()
            assert surface_layer is not None
            assert float(surface_layer.property("z")) > float(drag_area.property("z"))
            assert abs(float(drag_area.property("width")) - float(host.property("width"))) < 0.5
            assert abs(float(drag_area.property("height")) - float(host.property("height"))) < 0.5

            drag_target = QQmlProperty.read(drag_area, "drag.target")
            assert drag_target is None
            assert not bool(drag_area.property("manualDragActive"))

            window = attach_host_to_window(host)
            body_point = host_scene_point(host, 105.0, 44.0)
            events = host_pointer_events(host)

            mouse_click(window, body_point)
            assert events["clicked"] == [("node_surface_host_test", False)]

            mouse_double_click(window, body_point)
            assert events["opened"] == ["node_surface_host_test"]

            mouse_click(window, body_point, Qt.MouseButton.RightButton)
            assert len(events["contexts"]) == 1
            assert events["contexts"][0][0] == "node_surface_host_test"
            assert abs(float(events["contexts"][0][1]) - 105.0) < 0.5
            assert abs(float(events["contexts"][0][2]) - 44.0) < 0.5

            dispose_host_window(host, window)
            engine.deleteLater()
            app.processEvents()
            """,
        )

    def test_graph_node_host_render_activation_reloads_offscreen_surface_for_hover_drag_and_resize(self) -> None:
        self._run_qml_probe(
            "host-render-activation-force-active-states",
            """
            host = create_component(
                graph_node_host_qml_path,
                {
                    "nodeData": node_payload(),
                    "renderActivationSceneRectPayload": {
                        "x": -400.0,
                        "y": -300.0,
                        "width": 60.0,
                        "height": 40.0,
                    },
                },
            )
            loader = host.findChild(QObject, "graphNodeSurfaceLoader")
            assert loader is not None

            settle_events(2)
            assert not bool(host.property("renderActive"))
            assert not bool(loader.property("renderActive"))
            assert not bool(loader.property("surfaceLoaded"))

            host.setProperty("liveDragDx", 18.0)
            settle_events(2)

            assert bool(host.property("renderActive"))
            assert bool(loader.property("renderActive"))
            assert bool(loader.property("surfaceLoaded"))

            host.setProperty("liveDragDx", 0.0)
            settle_events(2)

            assert not bool(host.property("renderActive"))
            assert not bool(loader.property("renderActive"))
            assert not bool(loader.property("surfaceLoaded"))

            host.setProperty("_liveX", 90.0)
            host.setProperty("_liveY", 100.0)
            host.setProperty("_liveWidth", 240.0)
            host.setProperty("_liveHeight", 108.0)
            host.setProperty("_liveGeometryActive", True)
            settle_events(2)

            assert bool(host.property("renderActive"))
            assert bool(loader.property("renderActive"))
            assert bool(loader.property("surfaceLoaded"))

            host.setProperty("_liveGeometryActive", False)
            settle_events(2)

            assert not bool(host.property("renderActive"))
            assert not bool(loader.property("renderActive"))
            assert not bool(loader.property("surfaceLoaded"))

            window = attach_host_to_window(host)
            hover_host_local_point(window, host, 84.0, 40.0)

            assert bool(host.property("hoverActive"))
            assert bool(host.property("renderActive"))
            assert bool(loader.property("renderActive"))
            assert bool(loader.property("surfaceLoaded"))

            dispose_host_window(host, window)
            engine.deleteLater()
            app.processEvents()
            """,
        )

    def test_graph_node_host_exposes_exact_viewport_fact_during_live_geometry(self) -> None:
        self._run_qml_probe(
            "host-exact-visible-viewport-fact",
            """
            host = create_component(
                graph_node_host_qml_path,
                {
                    "nodeData": node_payload(),
                    "visibleSceneRectPayload": {
                        "x": 330.0,
                        "y": 100.0,
                        "width": 100.0,
                        "height": 150.0,
                    },
                    "renderActivationSceneRectPayload": {
                        "x": -1000.0,
                        "y": -1000.0,
                        "width": 3000.0,
                        "height": 3000.0,
                    },
                },
            )
            loader = host.findChild(QObject, "graphNodeSurfaceLoader")
            assert loader is not None
            assert not bool(host.property("inVisibleViewport"))
            assert bool(loader.property("_asynchronousLoadInProgress")) or bool(loader.property("surfaceLoaded"))

            host.setProperty(
                "visibleSceneRectPayload",
                {"x": 329.0, "y": 100.0, "width": 100.0, "height": 150.0},
            )
            settle_events(1)
            assert bool(host.property("inVisibleViewport"))
            if not bool(loader.property("surfaceLoaded")):
                assert bool(loader.property("_asynchronousLoadInProgress"))

            for _index in range(150):
                settle_events(1)
                if bool(loader.property("surfaceLoaded")):
                    break
                QTest.qWait(10)
            surface = host.findChild(QObject, "graphNodeStandardSurface")
            assert surface is not None
            assert bool(loader.property("surfaceLoaded"))
            assert not bool(loader.property("_asynchronousLoadInProgress"))

            host.setProperty(
                "visibleSceneRectPayload",
                {"x": 350.0, "y": 220.0, "width": 100.0, "height": 100.0},
            )
            settle_events(2)
            assert not bool(host.property("inVisibleViewport"))

            moved_payload = node_payload()
            moved_payload["x"] = 360.0
            moved_payload["y"] = 230.0
            host.setProperty("nodeData", moved_payload)
            settle_events(2)
            assert bool(host.property("inVisibleViewport"))

            host.setProperty("nodeData", node_payload())
            host.setProperty("liveDragDx", 30.0)
            host.setProperty("liveDragDy", 20.0)
            settle_events(2)
            assert bool(host.property("inVisibleViewport"))

            host.setProperty("liveDragDx", 0.0)
            host.setProperty("liveDragDy", 0.0)
            settle_events(2)
            assert not bool(host.property("inVisibleViewport"))

            host.setProperty("_liveX", 340.0)
            host.setProperty("_liveY", 210.0)
            host.setProperty("_liveWidth", 40.0)
            host.setProperty("_liveHeight", 40.0)
            host.setProperty("_liveGeometryActive", True)
            settle_events(2)
            assert bool(host.property("inVisibleViewport"))

            host.setProperty("_liveWidth", 10.0)
            settle_events(2)
            assert not bool(host.property("inVisibleViewport"))

            host.setProperty("visibleSceneRectPayload", {})
            settle_events(2)
            assert bool(host.property("inVisibleViewport"))
            assert host.findChild(QObject, "graphNodeStandardSurface") is surface
            assert bool(loader.property("surfaceLoaded"))

            engine.deleteLater()
            app.processEvents()
            """,
        )

    def test_graph_canvas_keeps_live_drag_preview_continuous_when_snap_to_grid_is_enabled(self) -> None:
        self._run_qml_probe(
            "graph-canvas-snap-live-preview",
            """
            from PyQt6.QtCore import pyqtProperty, pyqtSignal

            class MainWindowBridge(QObject):
                snap_to_grid_changed = pyqtSignal()
                graphics_preferences_changed = pyqtSignal()

                @pyqtProperty(bool, notify=snap_to_grid_changed)
                def snap_to_grid_enabled(self):
                    return True

                @pyqtProperty(float, constant=True)
                def snap_grid_size(self):
                    return 20.0

                @pyqtProperty(bool, notify=graphics_preferences_changed)
                def graphics_show_grid(self):
                    return True

                @pyqtProperty(bool, notify=graphics_preferences_changed)
                def graphics_show_minimap(self):
                    return True

                @pyqtProperty(bool, notify=graphics_preferences_changed)
                def graphics_node_shadow(self):
                    return True

                @pyqtProperty(int, notify=graphics_preferences_changed)
                def graphics_shadow_strength(self):
                    return 70

                @pyqtProperty(int, notify=graphics_preferences_changed)
                def graphics_shadow_softness(self):
                    return 50

                @pyqtProperty(int, notify=graphics_preferences_changed)
                def graphics_shadow_offset(self):
                    return 4

                @pyqtProperty(bool, notify=graphics_preferences_changed)
                def graphics_minimap_expanded(self):
                    return True

            model = GraphModel()
            registry = build_default_registry()
            workspace_id = model.active_workspace.workspace_id
            scene = GraphSceneBridge()
            scene.set_workspace(model, registry, workspace_id)
            scene.add_node_from_type("core.logger", 120.0, 140.0)
            scene.clear_selection()
            node_id = scene.nodes_model[0]["node_id"]

            view = ViewportBridge()
            view.set_viewport_size(1280.0, 720.0)
            main_window_bridge = MainWindowBridge()

            canvas = create_component(
                graph_canvas_qml_path,
                {
                    "mainWindowBridge": main_window_bridge,
                    "sceneBridge": scene,
                    "viewBridge": view,
                    "width": 1280.0,
                    "height": 720.0,
                },
            )
            node_cards = named_child_items(canvas, "graphNodeCard")
            assert len(node_cards) == 1
            node_card = node_cards[0]

            assert canvas.snapToGridEnabled() is True
            node_card.dragOffsetChanged.emit(node_id, 11.0, 9.0)
            canvas.property("frameSchedulerRef").flushPendingRedraws()
            assert canvas.property("liveDragDx") == 11.0
            assert canvas.property("liveDragDy") == 9.0

            node_card.dragFinished.emit(node_id, 131.0, 149.0, True)
            app.processEvents()
            assert canvas.property("liveDragDx") == 0.0
            assert canvas.property("liveDragDy") == 0.0
            assert scene.nodes_model[0]["x"] == 140.0
            assert scene.nodes_model[0]["y"] == 140.0

            canvas.deleteLater()
            app.processEvents()
            engine.deleteLater()
            app.processEvents()
            """,
        )

    def test_graph_canvas_routes_live_resize_geometry_through_edge_layer_and_scene_commit(self) -> None:
        self._run_qml_probe(
            "graph-canvas-live-resize-geometry",
            """
            model = GraphModel()
            registry = build_default_registry()
            workspace_id = model.active_workspace.workspace_id
            scene = GraphSceneBridge()
            scene.set_workspace(model, registry, workspace_id)
            source_node_id = scene.add_node_from_type("core.constant", 40.0, 140.0)
            target_node_id = scene.add_node_from_type("data.panel", 220.0, 140.0)
            scene.set_node_property(target_node_id, "auto_resize", False)
            scene.add_edge(source_node_id, "value", target_node_id, "input")

            view = ViewportBridge()
            view.set_viewport_size(1280.0, 720.0)

            canvas = create_component(
                graph_canvas_qml_path,
                {
                    "sceneBridge": scene,
                    "viewBridge": view,
                    "width": 1280.0,
                    "height": 720.0,
                },
            )
            node_cards = named_child_items(canvas, "graphNodeCard")
            target_card = [
                card
                for card in node_cards
                if card.property("nodeData")["node_id"] == target_node_id
            ][0]
            edge_layer = canvas.findChild(QObject, "graphCanvasEdgeLayer")
            assert edge_layer is not None

            target_card.resizePreviewChanged.emit(target_node_id, 190.0, 120.0, 260.0, 160.0, True)
            app.processEvents()

            canvas_live_geometry = variant_value(canvas.property("liveNodeGeometry"))
            edge_live_geometry = variant_value(edge_layer.property("liveNodeGeometry"))
            assert canvas_live_geometry[target_node_id] == {
                "x": 190.0,
                "y": 120.0,
                "width": 260.0,
                "height": 160.0,
            }
            assert edge_live_geometry[target_node_id] == canvas_live_geometry[target_node_id]

            target_card.resizeFinished.emit(target_node_id, 190.0, 120.0, 260.0, 160.0)
            app.processEvents()

            assert variant_value(canvas.property("liveNodeGeometry")) == {}
            updated_target = [node for node in scene.nodes_model if node["node_id"] == target_node_id][0]
            assert updated_target["x"] == 190.0
            assert updated_target["y"] == 120.0
            assert updated_target["width"] == 260.0
            assert updated_target["height"] == 160.0

            canvas.deleteLater()
            app.processEvents()
            engine.deleteLater()
            app.processEvents()
            """,
        )

    def test_graph_canvas_drag_moves_all_selected_nodes_together(self) -> None:
        self._run_qml_probe(
            "graph-canvas-multi-drag-selection",
            """
            model = GraphModel()
            registry = build_default_registry()
            workspace_id = model.active_workspace.workspace_id
            scene = GraphSceneBridge()
            scene.set_workspace(model, registry, workspace_id)
            first_node_id = scene.add_node_from_type("core.logger", 120.0, 140.0)
            second_node_id = scene.add_node_from_type("core.constant", 320.0, 180.0)
            scene.select_node(first_node_id, False)
            scene.select_node(second_node_id, True)

            view = ViewportBridge()
            view.set_viewport_size(1280.0, 720.0)

            canvas = create_component(
                graph_canvas_qml_path,
                {
                    "sceneBridge": scene,
                    "viewBridge": view,
                    "width": 1280.0,
                    "height": 720.0,
                },
            )
            node_cards = {
                card.property("nodeData")["node_id"]: card
                for card in named_child_items(canvas, "graphNodeCard")
            }
            assert set(scene.selected_node_lookup) == {first_node_id, second_node_id}
            drag_node_ids = canvas.dragNodeIdsForAnchor(second_node_id)
            if hasattr(drag_node_ids, "toVariant"):
                drag_node_ids = drag_node_ids.toVariant()
            assert list(drag_node_ids) == [second_node_id, first_node_id]

            before = {item["node_id"]: (item["x"], item["y"]) for item in scene.nodes_model}
            node_cards[second_node_id].dragOffsetChanged.emit(second_node_id, 25.0, 15.0)
            canvas.property("frameSchedulerRef").flushPendingRedraws()
            drag_lookup = canvas.property("liveDragNodeLookup")
            if hasattr(drag_lookup, "toVariant"):
                drag_lookup = drag_lookup.toVariant()
            assert set(drag_lookup) == {first_node_id, second_node_id}
            assert canvas.property("liveDragDx") == 25.0
            assert canvas.property("liveDragDy") == 15.0

            node_cards[second_node_id].dragFinished.emit(second_node_id, 345.0, 195.0, True)
            app.processEvents()
            after = {item["node_id"]: (item["x"], item["y"]) for item in scene.nodes_model}

            assert canvas.property("liveDragDx") == 0.0
            assert canvas.property("liveDragDy") == 0.0
            assert after[first_node_id] == (before[first_node_id][0] + 25.0, before[first_node_id][1] + 15.0)
            assert after[second_node_id] == (before[second_node_id][0] + 25.0, before[second_node_id][1] + 15.0)

            canvas.deleteLater()
            app.processEvents()
            engine.deleteLater()
            app.processEvents()
            """,
        )

    def test_graph_canvas_keeps_node_shadow_visible_during_direct_viewport_interaction(self) -> None:
        self._run_qml_probe_with_retry(
            "graph-canvas-shadow-direct-viewport-cache",
            """
            from tests.qt_wait import wait_for_condition_or_raise

            model = GraphModel()
            registry = build_default_registry()
            workspace_id = model.active_workspace.workspace_id
            scene = GraphSceneBridge()
            scene.set_workspace(model, registry, workspace_id)
            scene.add_node_from_type("core.logger", 120.0, 140.0)
            scene.clear_selection()

            view = ViewportBridge()
            view.set_viewport_size(1280.0, 720.0)

            canvas = create_component(
                graph_canvas_qml_path,
                {
                    "sceneBridge": scene,
                    "viewBridge": view,
                    "width": 1280.0,
                    "height": 720.0,
                },
            )
            node_cards = named_child_items(canvas, "graphNodeCard")
            assert len(node_cards) == 1
            node_card = node_cards[0]
            shadow_item = node_card.findChild(QObject, "graphNodeShadow")
            assert shadow_item is not None
            assert not bool(canvas.property("viewportInteractionWorldCacheActive"))
            assert not bool(node_card.property("viewportInteractionCacheActive"))
            assert bool(shadow_item.property("visible"))
            assert not bool(canvas.property("interactionActive"))

            canvas.beginViewportInteraction()
            app.processEvents()
            assert bool(canvas.property("interactionActive"))
            assert bool(canvas.property("viewportInteractionWorldCacheActive"))
            assert bool(node_card.property("viewportInteractionCacheActive"))
            assert bool(shadow_item.property("visible"))

            canvas.finishViewportInteractionSoon()
            wait_for_condition_or_raise(
                lambda: (
                    not bool(canvas.property("interactionActive"))
                    and bool(shadow_item.property("visible"))
                ),
                timeout_ms=190,
                app=app,
                timeout_message="Timed out waiting for wheel-zoom interaction state to recover.",
            )
            assert not bool(canvas.property("interactionActive"))
            assert not bool(canvas.property("viewportInteractionWorldCacheActive"))
            assert not bool(node_card.property("viewportInteractionCacheActive"))
            assert bool(shadow_item.property("visible"))

            canvas.deleteLater()
            app.processEvents()
            engine.deleteLater()
            app.processEvents()
            """,
        )


    def test_graph_canvas_minimap_keeps_node_geometry_static_when_center_changes(self) -> None:
        self._run_qml_probe(
            "graph-canvas-minimap-center-stability",
            """
            from tests.qt_wait import wait_for_condition_or_raise

            model = GraphModel()
            registry = build_default_registry()
            workspace_id = model.active_workspace.workspace_id
            scene = GraphSceneBridge()
            scene.set_workspace(model, registry, workspace_id)
            scene.add_node_from_type("core.logger", 120.0, 140.0)
            scene.add_node_from_type("core.logger", 460.0, 280.0)

            view = ViewportBridge()
            view.set_viewport_size(1280.0, 720.0)

            canvas = create_component(
                graph_canvas_qml_path,
                {
                    "mainWindowBridge": {
                        "graphics_show_grid": True,
                        "graphics_show_minimap": True,
                        "graphics_minimap_expanded": True,
                        "graphics_node_shadow": True,
                        "graphics_shadow_strength": 70,
                        "graphics_shadow_softness": 50,
                        "graphics_shadow_offset": 4,
                        "snap_to_grid_enabled": False,
                        "snap_grid_size": 20.0,
                    },
                    "sceneBridge": scene,
                    "viewBridge": view,
                    "width": 1280.0,
                    "height": 720.0,
                },
            )
            minimap_viewport = canvas.findChild(QObject, "graphCanvasMinimapViewport")
            minimap_viewport_rect = canvas.findChild(QObject, "graphCanvasMinimapViewportRect")
            minimap_node_content = canvas.findChild(QObject, "graphCanvasMinimapNodeContent")
            assert minimap_viewport is not None
            assert minimap_viewport_rect is not None
            assert minimap_node_content is not None

            wait_for_condition_or_raise(
                lambda: int(minimap_viewport.property("_nodeDelegateCreationCount")) == 2,
                timeout_ms=120,
                app=app,
                timeout_message="Timed out waiting for minimap node delegates to settle.",
            )

            baseline_node_key = str(minimap_viewport.property("nodeGeometryCacheKey"))
            baseline_creation_count = int(minimap_viewport.property("_nodeDelegateCreationCount"))
            baseline_node_x = float(minimap_node_content.property("x"))
            baseline_node_y = float(minimap_node_content.property("y"))
            baseline_node_scale = float(minimap_node_content.property("scale"))
            baseline_rect_key = str(minimap_viewport_rect.property("geometryKey"))
            baseline_rect_updates = int(minimap_viewport_rect.property("_geometryUpdateCount"))

            view.centerOn(160.0, 80.0)
            app.processEvents()
            view.centerOn(260.0, 210.0)
            app.processEvents()

            assert str(minimap_viewport.property("nodeGeometryCacheKey")) == baseline_node_key
            assert int(minimap_viewport.property("_nodeDelegateCreationCount")) == baseline_creation_count
            assert abs(float(minimap_node_content.property("x")) - baseline_node_x) < 0.001
            assert abs(float(minimap_node_content.property("y")) - baseline_node_y) < 0.001
            assert abs(float(minimap_node_content.property("scale")) - baseline_node_scale) < 1e-6
            assert str(minimap_viewport_rect.property("geometryKey")) != baseline_rect_key
            assert int(minimap_viewport_rect.property("_geometryUpdateCount")) > baseline_rect_updates

            canvas.deleteLater()
            app.processEvents()
            engine.deleteLater()
            app.processEvents()
            """,
        )

    def test_graph_canvas_minimap_rectangle_resizes_with_pane_width_changes(self) -> None:
        self._run_qml_probe(
            "graph-canvas-minimap-pane-resize-viewport-rect",
            """
            from tests.qt_wait import wait_for_condition_or_raise

            model = GraphModel()
            registry = build_default_registry()
            workspace_id = model.active_workspace.workspace_id
            scene = GraphSceneBridge()
            scene.set_workspace(model, registry, workspace_id)
            scene.add_node_from_type("core.logger", 120.0, 140.0)
            scene.add_node_from_type("core.logger", 460.0, 280.0)

            class DeferredViewportBridge(ViewportBridge):
                def __init__(self):
                    super().__init__()
                    self.ignored_size_updates = 0

                @pyqtSlot(float, float)
                def set_viewport_size(self, width, height):
                    if self.ignored_size_updates > 0:
                        self.ignored_size_updates -= 1
                        return
                    super().set_viewport_size(width, height)

            view = DeferredViewportBridge()

            canvas = create_component(
                graph_canvas_qml_path,
                {
                    "mainWindowBridge": {
                        "graphics_show_grid": True,
                        "graphics_show_minimap": True,
                        "graphics_minimap_expanded": True,
                        "graphics_node_shadow": True,
                        "graphics_shadow_strength": 70,
                        "graphics_shadow_softness": 50,
                        "graphics_shadow_offset": 4,
                        "snap_to_grid_enabled": False,
                        "snap_grid_size": 20.0,
                    },
                    "sceneBridge": scene,
                    "viewBridge": view,
                    "width": 1280.0,
                    "height": 720.0,
                },
            )
            minimap_viewport = canvas.findChild(QObject, "graphCanvasMinimapViewport")
            minimap_viewport_rect = canvas.findChild(QObject, "graphCanvasMinimapViewportRect")
            assert minimap_viewport is not None
            assert minimap_viewport_rect is not None

            def payload_dimension(key):
                return float(view.visible_scene_rect_payload[key])

            wait_for_condition_or_raise(
                lambda: (
                    int(minimap_viewport.property("_nodeDelegateCreationCount")) == 2
                    and abs(payload_dimension("width") - 1280.0) < 0.001
                    and abs(payload_dimension("height") - 720.0) < 0.001
                ),
                timeout_ms=200,
                app=app,
                timeout_message="Timed out waiting for minimap initial viewport size.",
            )

            baseline_node_key = str(minimap_viewport.property("nodeGeometryCacheKey"))
            baseline_creation_count = int(minimap_viewport.property("_nodeDelegateCreationCount"))
            baseline_rect_key = str(minimap_viewport_rect.property("geometryKey"))
            baseline_rect_width = float(minimap_viewport_rect.property("width"))
            baseline_rect_height = float(minimap_viewport_rect.property("height"))
            baseline_rect_updates = int(minimap_viewport_rect.property("_geometryUpdateCount"))

            view.ignored_size_updates = 2
            canvas.setProperty("width", 920.0)
            canvas.setProperty("height", 520.0)
            app.processEvents()

            wait_for_condition_or_raise(
                lambda: (
                    abs(payload_dimension("width") - 920.0) < 0.001
                    and abs(payload_dimension("height") - 520.0) < 0.001
                    and str(minimap_viewport_rect.property("geometryKey")) != baseline_rect_key
                ),
                timeout_ms=250,
                app=app,
                timeout_message="Timed out waiting for minimap rectangle to follow shrunken canvas size.",
            )

            resized_rect_width = float(minimap_viewport_rect.property("width"))
            resized_rect_height = float(minimap_viewport_rect.property("height"))
            assert resized_rect_width < baseline_rect_width
            assert resized_rect_height < baseline_rect_height
            assert str(minimap_viewport.property("nodeGeometryCacheKey")) == baseline_node_key
            assert int(minimap_viewport.property("_nodeDelegateCreationCount")) == baseline_creation_count
            assert int(minimap_viewport_rect.property("_geometryUpdateCount")) > baseline_rect_updates

            view.ignored_size_updates = 2
            canvas.setProperty("width", 1280.0)
            canvas.setProperty("height", 720.0)
            app.processEvents()

            wait_for_condition_or_raise(
                lambda: (
                    abs(payload_dimension("width") - 1280.0) < 0.001
                    and abs(payload_dimension("height") - 720.0) < 0.001
                    and str(minimap_viewport_rect.property("geometryKey")) == baseline_rect_key
                ),
                timeout_ms=250,
                app=app,
                timeout_message="Timed out waiting for minimap rectangle to restore with expanded canvas size.",
            )

            assert str(minimap_viewport.property("nodeGeometryCacheKey")) == baseline_node_key
            assert int(minimap_viewport.property("_nodeDelegateCreationCount")) == baseline_creation_count

            canvas.deleteLater()
            app.processEvents()
            engine.deleteLater()
            app.processEvents()
            """,
        )

    def test_graph_canvas_minimap_toggle_retains_node_delegates(self) -> None:
        self._run_qml_probe(
            "graph-canvas-minimap-toggle-retains-delegates",
            """
            from tests.qt_wait import wait_for_condition_or_raise

            model = GraphModel()
            registry = build_default_registry()
            workspace_id = model.active_workspace.workspace_id
            scene = GraphSceneBridge()
            scene.set_workspace(model, registry, workspace_id)
            for index in range(8):
                scene.add_node_from_type("core.logger", 120.0 + index * 75.0, 140.0 + index * 18.0)

            view = ViewportBridge()
            view.set_viewport_size(1280.0, 720.0)

            canvas = create_component(
                graph_canvas_qml_path,
                {
                    "mainWindowBridge": {
                        "graphics_show_grid": True,
                        "graphics_show_minimap": True,
                        "graphics_minimap_expanded": True,
                        "graphics_node_shadow": True,
                        "graphics_shadow_strength": 70,
                        "graphics_shadow_softness": 50,
                        "graphics_shadow_offset": 4,
                        "snap_to_grid_enabled": False,
                        "snap_grid_size": 20.0,
                    },
                    "sceneBridge": scene,
                    "viewBridge": view,
                    "width": 1280.0,
                    "height": 720.0,
                },
            )
            minimap_overlay = canvas.findChild(QObject, "graphCanvasMinimapOverlay")
            minimap_viewport = canvas.findChild(QObject, "graphCanvasMinimapViewport")
            assert minimap_overlay is not None
            assert minimap_viewport is not None

            wait_for_condition_or_raise(
                lambda: int(minimap_viewport.property("_nodeDelegateCreationCount")) == 8,
                timeout_ms=200,
                app=app,
                timeout_message="Timed out waiting for minimap delegates to initialize.",
            )
            baseline_creation_count = int(minimap_viewport.property("_nodeDelegateCreationCount"))
            baseline_static_updates = int(minimap_overlay.property("profileMinimapStaticUpdateCount"))

            canvas.setProperty("minimapExpanded", False)
            app.processEvents()
            assert not bool(minimap_overlay.property("minimapContentVisible"))
            assert not bool(minimap_viewport.property("visible"))
            assert int(minimap_viewport.property("_nodeDelegateCreationCount")) == baseline_creation_count

            canvas.setProperty("minimapExpanded", True)
            wait_for_condition_or_raise(
                lambda: bool(minimap_overlay.property("minimapContentVisible")),
                timeout_ms=200,
                app=app,
                timeout_message="Timed out waiting for minimap content to reopen.",
            )
            assert bool(minimap_viewport.property("visible"))
            assert int(minimap_viewport.property("_nodeDelegateCreationCount")) == baseline_creation_count
            assert int(minimap_overlay.property("profileMinimapStaticUpdateCount")) == baseline_static_updates

            canvas.deleteLater()
            app.processEvents()
            engine.deleteLater()
            app.processEvents()
            """,
        )





    def test_graph_canvas_viewport_interaction_cache_remains_viewport_only_not_port_drag(self) -> None:
        self._run_qml_probe(
            "graph-canvas-cache-scope",
            """
            from PyQt6.QtCore import QPointF

            model = GraphModel()
            registry = build_default_registry()
            workspace_id = model.active_workspace.workspace_id
            scene = GraphSceneBridge()
            scene.set_workspace(model, registry, workspace_id)
            node_id = scene.add_node_from_type("core.constant", 120.0, 140.0)

            view = ViewportBridge()
            view.set_viewport_size(1280.0, 720.0)

            canvas = create_component(
                graph_canvas_qml_path,
                {
                    "sceneBridge": scene,
                    "viewBridge": view,
                    "width": 1280.0,
                    "height": 720.0,
                },
            )
            node_cards = named_child_items(canvas, "graphNodeCard")
            assert len(node_cards) == 1
            node_card = node_cards[0]
            node_payload = node_card.property("nodeData")
            output_dot = named_item(node_card, "graphNodeOutputPortDot", "as_text")
            dot_center = output_dot.mapToItem(
                canvas,
                QPointF(output_dot.width() * 0.5, output_dot.height() * 0.5),
            )
            scene_x = canvas.screenToSceneX(dot_center.x())
            scene_y = canvas.screenToSceneY(dot_center.y())

            assert not bool(canvas.property("interactionActive"))
            assert not bool(canvas.property("viewportInteractionWorldCacheActive"))
            assert not bool(node_card.property("viewportInteractionCacheActive"))

            canvas.beginPortWireDrag(
                str(node_payload["node_id"]),
                "as_text",
                "out",
                scene_x,
                scene_y,
                dot_center.x(),
                dot_center.y(),
                0,
            )
            app.processEvents()

            assert canvas.property("wireDragState") is not None
            assert not bool(canvas.property("interactionActive"))
            assert not bool(canvas.property("viewportInteractionWorldCacheActive"))
            assert not bool(node_card.property("viewportInteractionCacheActive"))

            assert canvas.cancelWireDrag() is True
            app.processEvents()
            assert canvas.property("wireDragState") is None

            canvas.deleteLater()
            app.processEvents()
            engine.deleteLater()
            app.processEvents()
            """,
        )

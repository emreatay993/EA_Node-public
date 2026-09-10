from __future__ import annotations

import base64
import copy
import hashlib
import importlib
import json
from pathlib import Path
import sys
from typing import Any

import pytest
from PyQt6.QtCore import Q_ARG, QMetaObject, QObject, QUrl, pyqtSlot
from PyQt6.QtGui import QColor
from PyQt6.QtQml import QQmlComponent, QQmlEngine

from ea_node_editor.ui.icon_registry import (
    UI_ICON_PROVIDER_ID,
    UiIconImageProvider,
    UiIconRegistryBridge,
)
from ea_node_editor.persistence.artifact_store import ProjectArtifactStore

_REPO_ROOT = Path(__file__).resolve().parents[1]


def _bridge_module() -> Any:
    return importlib.import_module("ea_node_editor.web_host.bridge")


def _bridge(**kwargs: Any) -> QObject:
    return _bridge_module().WebSurfaceBridge(**kwargs)


def _data_url(mime_type: str, payload: bytes) -> str:
    encoded = base64.b64encode(payload).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def _qml_value(value: Any) -> Any:
    to_variant = getattr(value, "toVariant", None)
    return to_variant() if callable(to_variant) else value


def _artifact_service(tmp_path: Path) -> tuple[Any, ProjectArtifactStore, list[dict[str, Any]]]:
    module = _bridge_module()
    metadata_updates: list[dict[str, Any]] = []
    store = ProjectArtifactStore(project_path=tmp_path / "board.cxproj", metadata=None)
    service = module.WebSurfaceArtifactService(
        artifact_store=store,
        persist_artifact_store_metadata=metadata_updates.append,
        temporary_root_parent=tmp_path / "session-artifacts",
    )
    return service, store, metadata_updates


def test_bridge_import_does_not_import_webengine_modules() -> None:
    sys.modules.pop("ea_node_editor.web_host.bridge", None)
    before = {name for name in sys.modules if name.startswith("PyQt6.QtWebEngine")}

    importlib.import_module("ea_node_editor.web_host.bridge")

    after = {name for name in sys.modules if name.startswith("PyQt6.QtWebEngine")}
    assert after == before


def test_web_surface_bridge_is_qobject_with_webchannel_method_names() -> None:
    bridge = _bridge()

    assert isinstance(bridge, QObject)
    assert bridge.objectName() == "webSurfaceBridge"
    meta_object = bridge.metaObject()
    method_names = {
        bytes(meta_object.method(index).name()).decode("utf-8")
        for index in range(meta_object.methodOffset(), meta_object.methodCount())
    }
    assert {"load_state", "save_state", "asset_request", "export_preview"}.issubset(
        method_names
    )


def test_round_trip_accepts_plain_json_object_scene_state() -> None:
    bridge = _bridge()
    signal_count = 0

    def _record_state_change() -> None:
        nonlocal signal_count
        signal_count += 1

    bridge.state_changed.connect(_record_state_change)
    state = {
        "type": "excalidraw",
        "elements": [
            {
                "id": "element-1",
                "type": "rectangle",
                "x": 24.5,
                "y": 48,
                "isDeleted": False,
            }
        ],
        "appState": {"theme": "light", "zoom": {"value": 1.0}},
        "files": {},
    }

    assert bridge.save_state(state) is True

    assert signal_count == 1
    assert bridge.last_error == ""
    assert bridge.has_error is False
    assert bridge.load_state() == state

    loaded = bridge.load_state()
    loaded["elements"].append({"id": "local-mutation"})
    assert bridge.load_state() == state


def test_save_state_accepts_json_string_payload() -> None:
    bridge = _bridge()
    state = {
        "elements": [{"id": "element-2", "type": "text", "text": "hello"}],
        "appState": {},
        "files": {},
    }

    assert bridge.save_state(json.dumps(state)) is True

    assert bridge.load_state() == state
    assert bridge.last_error == ""


def test_invalid_json_payload_sets_visible_error_without_mutating_state() -> None:
    bridge = _bridge()
    original_state = {"elements": [], "appState": {"theme": "dark"}, "files": {}}
    assert bridge.save_state(original_state) is True

    assert bridge.save_state("{not-json") is False

    assert bridge.load_state() == original_state
    assert bridge.has_error is True
    assert "valid JSON" in bridge.last_error


def test_wrong_type_payload_sets_visible_error_without_mutating_state() -> None:
    bridge = _bridge()
    original_state = {"elements": [{"id": "element-3"}], "appState": {}, "files": {}}
    assert bridge.save_state(original_state) is True

    assert bridge.save_state([{"id": "array-is-not-a-scene-object"}]) is False

    assert bridge.load_state() == original_state
    assert bridge.has_error is True
    assert "JSON object" in bridge.last_error


def test_non_json_payload_data_sets_error_without_mutating_state() -> None:
    bridge = _bridge()
    original_state = {"elements": [], "appState": {}, "files": {}}
    assert bridge.save_state(original_state) is True

    assert bridge.save_state({"elements": [{"id": "bad", "data": object()}]}) is False

    assert bridge.load_state() == original_state
    assert bridge.has_error is True
    assert "non-JSON" in bridge.last_error


def test_valid_save_clears_previous_visible_error_state() -> None:
    bridge = _bridge()
    assert bridge.save_state("not-json") is False
    assert bridge.has_error is True

    assert bridge.save_state({"elements": [], "appState": {}, "files": {}}) is True

    assert bridge.has_error is False
    assert bridge.last_error == ""


def test_named_payload_limit_rejects_oversized_payload_without_mutating_state() -> None:
    module = _bridge_module()
    assert module.MAX_SCENE_STATE_PAYLOAD_BYTES > 0
    bridge = module.WebSurfaceBridge(max_payload_bytes=96)
    original_state = {"elements": [], "appState": {}, "files": {}}
    oversized_state = {"elements": [{"id": "x" * 120}], "appState": {}, "files": {}}
    assert bridge.max_payload_bytes == 96
    assert bridge.save_state(original_state) is True

    assert bridge.save_state(oversized_state) is False

    assert bridge.load_state() == original_state
    assert bridge.has_error is True
    assert "96 bytes" in bridge.last_error


def test_web_editor_bridge_oversized_payload_rejected_without_mutating_state() -> None:
    module = _bridge_module()
    bridge = module.WebSurfaceBridge(max_payload_bytes=96)
    original_state = {"elements": [], "appState": {"name": "Original"}, "files": {}}
    oversized_state = {"elements": [{"id": "x" * 120}], "appState": {}, "files": {}}
    assert bridge.save_state(original_state) is True

    assert bridge.save_state(oversized_state) is False

    assert bridge.load_state() == original_state
    assert bridge.has_error is True
    assert "96 bytes" in bridge.last_error


def test_web_editor_host_loads_without_webengine_and_surfaces_bridge_errors(qapp) -> None:  # noqa: ANN001
    bridge = _bridge(initial_state={"elements": [], "appState": {}, "files": {}})
    engine = QQmlEngine()
    qml_path = _REPO_ROOT / "ea_node_editor" / "ui_qml" / "components" / "web" / "WebEditorHost.qml"
    component = QQmlComponent(engine, QUrl.fromLocalFile(str(qml_path)))
    assert component.status() == QQmlComponent.Status.Ready, [
        error.toString() for error in component.errors()
    ]
    payload = {
        "title": "Board editor",
        "asset_url": "file:///tmp/excalidraw-host/index.html",
        "asset_error": "",
        "webengine_available": False,
        "webengine_reason": "test unavailable",
    }
    properties = {
        "payload": payload,
        "webSurfaceBridge": bridge,
        "themePalette": {
            "input_bg": "#151821",
            "input_border": "#3a4355",
            "panel_bg": "#1f2431",
            "panel_title_fg": "#eef3ff",
            "muted_fg": "#95a0b8",
            "error": "#d94f4f",
        },
    }
    if hasattr(component, "createWithInitialProperties"):
        host = component.createWithInitialProperties(properties)
    else:
        host = component.create()
        for key, value in properties.items():
            host.setProperty(key, value)
    assert host is not None
    host.setWidth(640)
    host.setHeight(360)
    qapp.processEvents()

    fallback = host.findChild(QObject, "contentFullscreenWebEditorFallback")
    error_text = host.findChild(QObject, "contentFullscreenWebEditorErrorText")
    assert fallback is not None
    assert error_text is not None
    assert bool(fallback.property("visible")) is True
    assert "Qt WebEngine is unavailable" in str(error_text.property("text"))

    assert bridge.save_state("{not-json") is False
    qapp.processEvents()
    assert "valid JSON" in str(error_text.property("text"))

    host.deleteLater()
    engine.deleteLater()
    qapp.processEvents()


def test_web_editor_dynamic_qml_source_uses_real_line_breaks() -> None:
    qml_path = _REPO_ROOT / "ea_node_editor" / "ui_qml" / "components" / "web" / "WebEditorHost.qml"
    source = qml_path.read_text(encoding="utf-8")

    assert '].join("\\\\n");' not in source
    assert '].join("\\n");' in source


def test_web_editor_host_wires_close_preview_export_lifecycle_to_js_host() -> None:
    qml_path = _REPO_ROOT / "ea_node_editor" / "ui_qml" / "components" / "web" / "WebEditorHost.qml"
    source = qml_path.read_text(encoding="utf-8")

    assert "function requestClosePreviewExport()" in source
    assert "host.flushSave" in source
    assert "host.requestPreviewExport || host.exportPreview || window.corexExcalidrawExportPreview" in source
    assert "editorView.runJavaScript(script);" in source
    assert "signal closePreviewExportResult(var result)" in source
    assert "__corex_pending_close_preview__" in source
    assert "window.corexClosePreviewResult" in source


def test_web_editor_host_waits_for_web_channel_bridge_before_loading_page() -> None:
    qml_path = _REPO_ROOT / "ea_node_editor" / "ui_qml" / "components" / "web" / "WebEditorHost.qml"
    source = qml_path.read_text(encoding="utf-8")

    assert "&& root.webSurfaceBridge !== null" in source
    assert "&& root.webSurfaceBridge !== undefined" in source
    assert "function syncBridgeRegistration()" in source
    assert 'editorChannel.registerObjects({\\"webSurfaceBridge\\": bridgeObject});' in source
    assert "editorChannel.registeredObjects = bridgeObject ? [bridgeObject] : [];" not in source
    assert "Component.onCompleted: syncBridgeRegistration()" in source
    assert '"        url: \\"\\""' in source
    assert "if (bridgeObject && pageUrl.length > 0" in source


def test_web_page_host_loads_without_webengine_and_surfaces_invalid_location_denial(qapp) -> None:  # noqa: ANN001
    engine = QQmlEngine()
    qml_path = _REPO_ROOT / "ea_node_editor" / "ui_qml" / "components" / "web" / "WebPageHost.qml"
    component = QQmlComponent(engine, QUrl.fromLocalFile(str(qml_path)))
    assert component.status() == QQmlComponent.Status.Ready, [
        error.toString() for error in component.errors()
    ]
    payload = {
        "title": "Blocked web page",
        "content_kind": "web_page",
        "start_location": "javascript:alert(1)",
        "current_location": "javascript:alert(1)",
        "navigation_decision": {
            "allowed": False,
            "target_url": "",
            "reason": "Unsupported web navigation scheme: javascript",
            "original_location": "javascript:alert(1)",
            "scheme": "",
            "origin": "",
            "is_local": False,
            "qwebchannel_allowed": False,
        },
        "webengine_available": False,
        "webengine_reason": "Qt WebEngine is disabled for the offscreen Qt platform.",
    }
    properties = {
        "payload": payload,
        "surfaceMode": "fullscreen",
        "themePalette": {
            "input_bg": "#151821",
            "input_border": "#3a4355",
            "panel_bg": "#1f2431",
            "panel_title_fg": "#eef3ff",
            "muted_fg": "#95a0b8",
            "error": "#d94f4f",
            "toolbar_bg": "#202635",
            "border": "#3a4355",
        },
    }
    if hasattr(component, "createWithInitialProperties"):
        host = component.createWithInitialProperties(properties)
    else:
        host = component.create()
        for key, value in properties.items():
            host.setProperty(key, value)
    assert host is not None
    host.setWidth(820)
    host.setHeight(480)
    qapp.processEvents()

    status = host.findChild(QObject, "contentFullscreenWebPageStatusPane")
    message = host.findChild(QObject, "webPageStatusMessage")
    assert status is not None
    assert message is not None
    assert bool(status.property("visible")) is True
    assert "Unsupported web navigation scheme" in str(message.property("text"))
    assert host.findChild(QObject, "webPageHostWebEngineView") is None

    host.deleteLater()
    engine.deleteLater()
    qapp.processEvents()


def test_web_page_host_normalizes_local_navigation_to_file_url_and_flushes_state(qapp) -> None:  # noqa: ANN001
    class BrowserStateBridgeStub(QObject):
        def __init__(self) -> None:
            super().__init__()
            self.states: list[dict[str, Any]] = []

        @pyqtSlot("QVariantMap", result=bool)
        def save_web_page_browser_state(self, state: dict[str, Any]) -> bool:
            self.states.append(dict(state or {}))
            return True

    fixture = _REPO_ROOT / "tests" / "fixtures" / "web_page_viewer" / "index.html"
    state_bridge = BrowserStateBridgeStub()
    engine = QQmlEngine()
    qml_path = _REPO_ROOT / "ea_node_editor" / "ui_qml" / "components" / "web" / "WebPageHost.qml"
    component = QQmlComponent(engine, QUrl.fromLocalFile(str(qml_path)))
    assert component.status() == QQmlComponent.Status.Ready, [
        error.toString() for error in component.errors()
    ]
    payload = {
        "title": "Offline web page",
        "content_kind": "web_page",
        "start_location": "",
        "current_location": "",
        "persist_browser_state": True,
        "navigation_decision": {
            "allowed": False,
            "target_url": "",
            "reason": "",
            "original_location": "",
            "scheme": "",
            "origin": "",
            "is_local": False,
            "qwebchannel_allowed": False,
        },
        "webengine_available": False,
        "webengine_reason": "Qt WebEngine is disabled for the offscreen Qt platform.",
    }
    properties = {
        "payload": payload,
        "surfaceMode": "fullscreen",
        "browserStateBridge": state_bridge,
        "themePalette": {
            "input_bg": "#ffffff",
            "input_border": "#96a6ba",
            "panel_bg": "#f5f7fa",
            "panel_title_fg": "#1b2733",
            "muted_fg": "#5f6b7a",
            "error": "#98434c",
            "toolbar_bg": "#e5ebf2",
            "border": "#b7c2ce",
        },
    }
    if hasattr(component, "createWithInitialProperties"):
        host = component.createWithInitialProperties(properties)
    else:
        host = component.create()
        for key, value in properties.items():
            host.setProperty(key, value)
    assert host is not None
    host.setWidth(820)
    host.setHeight(480)
    qapp.processEvents()

    QMetaObject.invokeMethod(host, "navigateTo", Q_ARG("QVariant", str(fixture)))
    QMetaObject.invokeMethod(host, "flushBrowserState")
    qapp.processEvents()

    assert str(host.property("currentUrl")) == fixture.resolve().as_uri()
    assert state_bridge.states[-1] == {
        "current_url": fixture.resolve().as_uri(),
        "zoom_factor": 1.0,
    }

    host.deleteLater()
    engine.deleteLater()
    qapp.processEvents()


def _web_page_node_data(url: str, *, display_mode: str = "fit_width") -> dict[str, Any]:
    return {
        "node_id": "node-web",
        "properties": {
            "display_mode": display_mode,
        },
        "web_page_payload": {
            "title": "Web Page Viewer",
            "content_kind": "web_page",
            "start_location": url,
            "current_location": url,
            "display_mode": display_mode,
            "navigation_decision": {
                "allowed": True,
                "target_url": url,
                "reason": "",
                "original_location": url,
                "scheme": "https",
                "origin": url,
                "is_local": False,
                "qwebchannel_allowed": False,
            },
            "webengine_available": False,
            "webengine_reason": "Qt WebEngine is disabled for the offscreen Qt platform.",
            "qwebchannel_allowed": False,
        }
    }


def test_web_page_host_reapplies_payload_when_graph_node_data_updates(qapp) -> None:  # noqa: ANN001
    engine = QQmlEngine()
    host_component = QQmlComponent(engine)
    host_component.setData(
        b"import QtQuick 2.15\n"
        b"Item {\n"
        b"    property var nodeData: ({})\n"
        b"    property string lastCommit: \"\"\n"
        b"    property bool surfaceFullscreenAvailable: true\n"
        b"    signal inlinePropertyCommitted(string nodeId, string key, var value)\n"
        b"    onInlinePropertyCommitted: lastCommit = String(nodeId || \"\") + \"|\" + String(key || \"\") + \"|\" + String(value)\n"
        b"    function surfaceFullscreenAction(enabled, primary) {\n"
        b"        return {\"id\": \"fullscreen\", \"label\": \"Fullscreen\", \"icon\": \"fullscreen\", \"kind\": \"web_page\", \"enabled\": Boolean(enabled), \"primary\": Boolean(primary)};\n"
        b"    }\n"
        b"}",
        QUrl(),
    )
    assert host_component.status() == QQmlComponent.Status.Ready, [
        error.toString() for error in host_component.errors()
    ]
    host_stub = host_component.create()
    assert host_stub is not None
    host_stub.setProperty("nodeData", _web_page_node_data("https://example.com/a"))

    qml_path = _REPO_ROOT / "ea_node_editor" / "ui_qml" / "components" / "web" / "WebPageHost.qml"
    component = QQmlComponent(engine, QUrl.fromLocalFile(str(qml_path)))
    assert component.status() == QQmlComponent.Status.Ready, [
        error.toString() for error in component.errors()
    ]
    properties = {
        "host": host_stub,
        "themePalette": {
            "input_bg": "#151821",
            "input_border": "#3a4355",
            "panel_bg": "#1f2431",
            "panel_title_fg": "#eef3ff",
            "muted_fg": "#95a0b8",
            "error": "#d94f4f",
            "toolbar_bg": "#202635",
            "border": "#3a4355",
        },
    }
    host = component.createWithInitialProperties(properties)
    assert host is not None
    host.setWidth(820)
    host.setHeight(480)
    qapp.processEvents()
    qapp.processEvents()

    assert str(host.property("surfaceMode")) == "graph"
    assert str(host.property("currentUrl")) == "https://example.com/a"
    title_label = host.findChild(QObject, "webPageDocumentTitleLabel")
    assert title_label is not None
    assert not bool(title_label.property("visible"))
    QMetaObject.invokeMethod(
        host,
        "_handleWebEngineTitleChanged",
        Q_ARG("QVariant", "  Example\nDomain  "),
    )
    qapp.processEvents()
    assert str(host.property("documentTitle")) == "Example Domain"
    assert str(title_label.property("text")) == "Example Domain"
    assert bool(title_label.property("visible"))
    assert QColor(title_label.property("color")).name().lower() == "#95a0b8"
    title_parent = title_label.parent()
    assert title_parent is not None
    assert str(title_parent.property("objectName")) != "webPageViewportFrame"
    toolbar = host.findChild(QObject, "webPageToolbar")
    address_field = host.findChild(QObject, "webPageAddressField")
    if toolbar is not None:
        assert not bool(toolbar.property("visible"))
    if address_field is not None:
        assert not bool(address_field.property("visible"))
    assert host.findChild(QObject, "webPageAddressPopover") is None
    actions = _qml_value(host.property("surfaceActions"))
    assert [action["id"] for action in actions] == [
        "web_page_back",
        "web_page_forward",
        "web_page_reload_stop",
        "web_page_edit_address",
        "web_page_local_html",
        "web_page_display_mode",
        "toggle_content_only",
        "toggle_title",
        "toggle_frame",
        "fullscreen",
        "web_page_detach",
    ]
    local_html_action = next(action for action in actions if action["id"] == "web_page_local_html")
    assert local_html_action["popover_layout"] == "source_storage"
    assert [action["source_mode"] for action in local_html_action["popoverActions"]] == [
        "external_link",
        "managed_copy",
    ]
    assert local_html_action["popoverActions"][0]["checked"] is True
    assert local_html_action["popoverActions"][1].get("checked", False) is False
    display_action = next(action for action in actions if action["id"] == "web_page_display_mode")
    assert [action["id"] for action in display_action["popoverActions"]] == [
        "web_page_display_responsive",
        "web_page_display_fit_width",
        "web_page_display_fit_page",
    ]
    assert display_action["popoverActions"][1]["checked"] is True
    assert next(action for action in actions if action["id"] == "toggle_content_only")["icon"] == "content-only"
    assert next(action for action in actions if action["id"] == "toggle_title")["icon"] == "title-heading"
    assert next(action for action in actions if action["id"] == "toggle_frame")["icon"] == "frame-corners"
    assert _qml_value(host.property("embeddedInteractiveRects")) == []

    managed_html_data = _web_page_node_data("temp://managed_html")
    host_stub.setProperty("nodeData", managed_html_data)
    qapp.processEvents()
    managed_actions = _qml_value(host.property("surfaceActions"))
    managed_local_html_action = next(action for action in managed_actions if action["id"] == "web_page_local_html")
    assert managed_local_html_action["popoverActions"][0].get("checked", False) is False
    assert managed_local_html_action["popoverActions"][1]["checked"] is True

    QMetaObject.invokeMethod(host, "dispatchSurfaceAction", Q_ARG("QVariant", "web_page_display_fit_width"))
    qapp.processEvents()
    assert str(host.property("displayMode")) == "fit_width"
    assert str(host_stub.property("lastCommit")) == "node-web|display_mode|fit_width"
    QMetaObject.invokeMethod(host, "dispatchSurfaceAction", Q_ARG("QVariant", "toggle_content_only"))
    qapp.processEvents()
    assert str(host_stub.property("lastCommit")) == "node-web|show_frame|false"
    content_only_data = _web_page_node_data("https://example.com/a")
    content_only_data["properties"].update({"show_title": False, "show_frame": False})
    host_stub.setProperty("nodeData", content_only_data)
    qapp.processEvents()
    assert bool(host.property("chromeContentOnlyActive"))
    assert not bool(host.property("chromeTitleVisible"))
    assert not bool(host.property("chromeFrameVisible"))
    actions = _qml_value(host.property("surfaceActions"))
    display_action = next(action for action in actions if action["id"] == "web_page_display_mode")
    assert display_action["popoverActions"][1]["checked"] is True
    viewport = host.findChild(QObject, "webPageViewport")
    assert viewport is not None
    viewport_width = float(viewport.property("width"))
    assert viewport_width > 0.0
    QMetaObject.invokeMethod(
        host,
        "_applyFitZoomForMetrics",
        Q_ARG("QVariant", viewport_width * 2.0),
        Q_ARG("QVariant", 100.0),
    )
    assert float(host.property("zoomFactor")) == pytest.approx(1.0, abs=0.01)

    QMetaObject.invokeMethod(host, "dispatchSurfaceAction", Q_ARG("QVariant", "web_page_display_fit_page"))
    qapp.processEvents()
    assert str(host.property("displayMode")) == "fit_page"
    QMetaObject.invokeMethod(
        host,
        "_applyFitZoomForMetrics",
        Q_ARG("QVariant", viewport_width * 2.0),
        Q_ARG("QVariant", 100.0),
    )
    assert float(host.property("zoomFactor")) == pytest.approx(0.5, abs=0.01)

    QMetaObject.invokeMethod(host, "dispatchSurfaceAction", Q_ARG("QVariant", "web_page_edit_address"))
    qapp.processEvents()
    assert bool(host.property("addressEditorOpen"))
    assert str(host.property("addressEditorText")) == "https://example.com/a"
    assert _qml_value(host.property("embeddedInteractiveRects")) == []
    QMetaObject.invokeMethod(host, "acceptAddressEdit", Q_ARG("QVariant", "example.com/c"))
    qapp.processEvents()
    assert str(host.property("currentUrl")) == "https://example.com/c"
    assert not bool(host.property("addressEditorOpen"))

    host_stub.setProperty("nodeData", _web_page_node_data("https://example.com/b"))
    qapp.processEvents()
    qapp.processEvents()

    assert str(host.property("currentUrl")) == "https://example.com/b"
    assert [action["id"] for action in _qml_value(host.property("surfaceActions"))] == [
        "web_page_back",
        "web_page_forward",
        "web_page_reload_stop",
        "web_page_edit_address",
        "web_page_local_html",
        "web_page_display_mode",
        "toggle_content_only",
        "toggle_title",
        "toggle_frame",
        "fullscreen",
        "web_page_detach",
    ]

    host.deleteLater()
    host_stub.deleteLater()
    engine.deleteLater()
    qapp.processEvents()


def test_web_page_host_parks_and_reclaims_retained_graph_web_item(qapp) -> None:  # noqa: ANN001
    engine = QQmlEngine()
    components_dir = _REPO_ROOT / "ea_node_editor" / "ui_qml" / "components"
    component = QQmlComponent(engine)
    component.setData(
        b'''
        import QtQuick 2.15
        import "web" as WebComponents

        Item {
            id: root
            width: 820
            height: 480
            property bool parkClaimPassed: false

            Item {
                id: canvasStub
                property alias webPageRetentionStore: retentionStore
            }

            WebComponents.WebPageRetentionStore {
                id: retentionStore
                maxRetainedPages: 8
            }

            Item {
                id: graphHostStub
                property var canvasItem: canvasStub
                property bool surfaceFullscreenAvailable: true
                property string lastCommit: ""
                property var nodeData: ({
                    "node_id": "node-web-retained",
                    "workspace_id": "workspace-a",
                    "properties": {"display_mode": "fit_width"},
                    "web_page_payload": {
                        "workspace_id": "workspace-a",
                        "node_id": "node-web-retained",
                        "title": "Web Page Viewer",
                        "content_kind": "web_page",
                        "start_location": "https://example.com/a",
                        "current_location": "https://example.com/a",
                        "display_mode": "fit_width",
                        "navigation_decision": {
                            "allowed": true,
                            "target_url": "https://example.com/a",
                            "reason": "",
                            "original_location": "https://example.com/a",
                            "scheme": "https",
                            "origin": "https://example.com",
                            "is_local": false,
                            "qwebchannel_allowed": false
                        },
                        "webengine_available": false,
                        "webengine_reason": "test fake page",
                        "qwebchannel_allowed": false
                    }
                })
                signal inlinePropertyCommitted(string nodeId, string key, var value)
                onInlinePropertyCommitted: lastCommit = String(nodeId || "") + "|" + String(key || "") + "|" + String(value)
                function surfaceFullscreenAction(enabled, primary) {
                    return {"id": "fullscreen", "label": "Fullscreen", "icon": "fullscreen", "kind": "web_page", "enabled": Boolean(enabled), "primary": Boolean(primary)};
                }
            }

            Item {
                id: fakePage
                objectName: "fakeRetainedWebEngineItem"
                property string pageUrl: "https://example.com/a"
                property real pageZoom: 1.0
                property color pageBackgroundColor: "#ffffff"
                property bool navigationAllowed: true
                property string documentTitle: "Retained title"
                property bool pageCanGoBack: true
                property bool pageCanGoForward: false
                property bool retainedPaused: false
                signal loadStatusChanged(int status, string errorText, string url, int progress, bool loading)
                signal documentTitleReported(string title)
                signal navigationRequestedByPage(string url)
                signal webEngineDiagnostic(string category, string message, string url)
                signal pageFullscreenRequested(bool toggleOn, string origin)
                signal contentMetricsReady(real contentWidth, real contentHeight)
                function setPageRetained(retained) {
                    retainedPaused = Boolean(retained);
                    visible = !retainedPaused;
                }
            }

            WebComponents.WebPageHost {
                id: firstHost
                host: graphHostStub
                width: 400
                height: 300
            }

            WebComponents.WebPageHost {
                id: secondHost
                host: graphHostStub
                width: 400
                height: 300
                x: 410
            }

            function runParkClaim() {
                retentionStore.beginWorkspaceSwitch("workspace-b");
                firstHost.webEngineItem = fakePage;
                fakePage.pageUrl = "https://example.com/live";
                firstHost.currentUrl = "https://example.com/live";
                var parked = firstHost._parkWebEngineItemForWorkspaceSwitch();
                var parkedParentName = fakePage.parent ? String(fakePage.parent.objectName || "") : "";
                secondHost.currentUrl = "https://example.com/stale-persisted";
                var claimed = secondHost._claimRetainedWebEngineItem();
                var restoredParentName = fakePage.parent ? String(fakePage.parent.objectName || "") : "";
                parkClaimPassed = parked
                    && firstHost.webEngineItem === null
                    && parkedParentName === "webPageRetentionParkingLot"
                    && fakePage.retainedPaused === false
                    && claimed
                    && secondHost.webEngineItem === fakePage
                    && secondHost.currentUrl === "https://example.com/live"
                    && restoredParentName === "webPageViewport"
                    && retentionStore.retainedCount() === 0;
            }
        }
        ''',
        QUrl.fromLocalFile(str(components_dir / "web_page_host_retention_test.qml")),
    )
    assert component.status() == QQmlComponent.Status.Ready, [
        error.toString() for error in component.errors()
    ]
    harness = component.create()
    assert harness is not None

    QMetaObject.invokeMethod(harness, "runParkClaim")
    qapp.processEvents()

    assert bool(harness.property("parkClaimPassed"))

    harness.deleteLater()
    engine.deleteLater()
    qapp.processEvents()


def test_web_page_host_reclaims_retained_item_after_same_url_payload_change(qapp) -> None:  # noqa: ANN001
    engine = QQmlEngine()
    components_dir = _REPO_ROOT / "ea_node_editor" / "ui_qml" / "components"
    component = QQmlComponent(engine)
    component.setData(
        b'''
        import QtQuick 2.15
        import "web" as WebComponents

        Item {
            id: root
            width: 420
            height: 320
            property bool resyncPassed: false
            property string debugState: ""
            property string sameUrl: "https://example.com/shared"

            Item {
                id: canvasStub
                property alias webPageRetentionStore: retentionStore
            }

            WebComponents.WebPageRetentionStore {
                id: retentionStore
                maxRetainedPages: 8
            }

            function webNodeData(workspaceId, nodeId, webEngineAvailable) {
                return {
                    "node_id": nodeId,
                    "workspace_id": workspaceId,
                    "properties": {"display_mode": "fit_width"},
                    "web_page_payload": {
                        "workspace_id": workspaceId,
                        "node_id": nodeId,
                        "title": "Web Page Viewer",
                        "content_kind": "web_page",
                        "start_location": root.sameUrl,
                        "current_location": root.sameUrl,
                        "display_mode": "fit_width",
                        "navigation_decision": {
                            "allowed": true,
                            "target_url": root.sameUrl,
                            "reason": "",
                            "original_location": root.sameUrl,
                            "scheme": "https",
                            "origin": "https://example.com",
                            "is_local": false,
                            "qwebchannel_allowed": false
                        },
                        "webengine_available": Boolean(webEngineAvailable),
                        "webengine_reason": "",
                        "qwebchannel_allowed": false
                    }
                };
            }

            Item {
                id: graphHostStub
                property var canvasItem: canvasStub
                property bool surfaceFullscreenAvailable: true
                property var nodeData: root.webNodeData("workspace-b", "node-b", false)
                signal inlinePropertyCommitted(string nodeId, string key, var value)
                function surfaceFullscreenAction(enabled, primary) {
                    return {"id": "fullscreen", "label": "Fullscreen", "icon": "fullscreen", "kind": "web_page", "enabled": Boolean(enabled), "primary": Boolean(primary)};
                }
            }

            Item {
                id: fakePage
                objectName: "fakeRetainedWebEngineItem"
                property string pageUrl: root.sameUrl
                property real pageZoom: 1.0
                property color pageBackgroundColor: "#ffffff"
                property bool navigationAllowed: true
                property string documentTitle: "Retained title"
                property bool pageCanGoBack: false
                property bool pageCanGoForward: false
                property bool retainedPaused: false
                signal loadStatusChanged(int status, string errorText, string url, int progress, bool loading)
                signal documentTitleReported(string title)
                signal navigationRequestedByPage(string url)
                signal webEngineDiagnostic(string category, string message, string url)
                signal pageFullscreenRequested(bool toggleOn, string origin)
                signal contentMetricsReady(real contentWidth, real contentHeight)
                function setPageRetained(retained) {
                    retainedPaused = Boolean(retained);
                    visible = !retainedPaused;
                }
            }

            WebComponents.WebPageHost {
                id: webHost
                host: graphHostStub
                width: 400
                height: 300
            }

            function runPayloadChangeResync() {
                webHost._applyPayload();
                webHost.currentUrl = root.sameUrl;
                webHost.webEngineItem = null;
                var key = retentionStore.keyFor("workspace-a", "node-a");
                retentionStore.parkPage(key, fakePage, {
                    "workspace_id": "workspace-a",
                    "node_id": "node-a",
                    "current_url": root.sameUrl
                });
                graphHostStub.nodeData = root.webNodeData("workspace-a", "node-a", true);
            }

            function checkPayloadChangeResync() {
                var parentName = fakePage.parent ? String(fakePage.parent.objectName || "") : "";
                debugState = "node=" + webHost.nodeId
                    + " currentUrl=" + webHost.currentUrl
                    + " item=" + (webHost.webEngineItem === fakePage)
                    + " retained=" + retentionStore.retainedCount()
                    + " parent=" + parentName
                    + " creationError=" + webHost.webEngineCreationError;
                resyncPassed = webHost.webEngineItem === fakePage
                    && webHost.nodeId === "node-a"
                    && webHost.currentUrl === root.sameUrl
                    && retentionStore.retainedCount() === 0
                    && parentName === "webPageViewport"
                    && webHost.webEngineCreationError === "";
            }
        }
        ''',
        QUrl.fromLocalFile(str(components_dir / "web_page_host_same_url_resync_test.qml")),
    )
    assert component.status() == QQmlComponent.Status.Ready, [
        error.toString() for error in component.errors()
    ]
    harness = component.create()
    assert harness is not None
    qapp.processEvents()
    qapp.processEvents()

    QMetaObject.invokeMethod(harness, "runPayloadChangeResync")
    for _ in range(8):
        qapp.processEvents()
    QMetaObject.invokeMethod(harness, "checkPayloadChangeResync")
    qapp.processEvents()

    assert bool(harness.property("resyncPassed")), str(harness.property("debugState"))

    harness.deleteLater()
    engine.deleteLater()
    qapp.processEvents()


def test_web_page_host_detach_borrows_live_graph_web_item_and_restores(qapp) -> None:  # noqa: ANN001
    engine = QQmlEngine()
    components_dir = _REPO_ROOT / "ea_node_editor" / "ui_qml" / "components"
    component = QQmlComponent(engine)
    component.setData(
        b'''
        import QtQuick 2.15
        import "web" as WebComponents

        Item {
            id: root
            width: 820
            height: 480
            property bool detachPassed: false
            property string debugState: ""
            property string pageUrl: "https://example.com/detached"

            Item {
                id: canvasStub
                property alias webPageRetentionStore: retentionStore
            }

            WebComponents.WebPageRetentionStore {
                id: retentionStore
                maxRetainedPages: 8
            }

            Item {
                id: graphHostStub
                property var canvasItem: canvasStub
                property bool surfaceFullscreenAvailable: true
                property var nodeData: ({
                    "node_id": "node-web-detach",
                    "workspace_id": "workspace-a",
                    "properties": {"display_mode": "fit_width"},
                    "web_page_payload": {
                        "workspace_id": "workspace-a",
                        "node_id": "node-web-detach",
                        "title": "Web Page Viewer",
                        "content_kind": "web_page",
                        "start_location": root.pageUrl,
                        "current_location": root.pageUrl,
                        "display_mode": "fit_width",
                        "navigation_decision": {
                            "allowed": true,
                            "target_url": root.pageUrl,
                            "reason": "",
                            "original_location": root.pageUrl,
                            "scheme": "https",
                            "origin": "https://example.com",
                            "is_local": false,
                            "qwebchannel_allowed": false
                        },
                        "webengine_available": true,
                        "webengine_reason": "",
                        "qwebchannel_allowed": false
                    }
                })
                signal inlinePropertyCommitted(string nodeId, string key, var value)
                function surfaceFullscreenAction(enabled, primary) {
                    return {"id": "fullscreen", "label": "Fullscreen", "icon": "fullscreen", "kind": "web_page", "enabled": Boolean(enabled), "primary": Boolean(primary)};
                }
            }

            Item {
                id: fakePage
                objectName: "fakeDetachedWebEngineItem"
                property string pageUrl: root.pageUrl
                property real pageZoom: 1.0
                property color pageBackgroundColor: "#ffffff"
                property bool navigationAllowed: true
                property string documentTitle: "Detached title"
                property bool pageCanGoBack: false
                property bool pageCanGoForward: true
                property bool retainedPaused: false
                signal loadStatusChanged(int status, string errorText, string url, int progress, bool loading)
                signal documentTitleReported(string title)
                signal navigationRequestedByPage(string url)
                signal webEngineDiagnostic(string category, string message, string url)
                signal pageFullscreenRequested(bool toggleOn, string origin)
                signal contentMetricsReady(real contentWidth, real contentHeight)
                function setPageRetained(retained) {
                    retainedPaused = Boolean(retained);
                    visible = !retainedPaused;
                }
            }

            WebComponents.WebPageHost {
                id: webHost
                host: graphHostStub
                width: 400
                height: 300
            }

            function _parentName(item) {
                return item && item.parent ? String(item.parent.objectName || "") : "";
            }

            function runDetachBorrowRelease() {
                webHost._applyPayload();
                webHost.currentUrl = root.pageUrl;
                var key = retentionStore.keyFor("workspace-a", "node-web-detach");
                retentionStore.parkPage(key, fakePage, {
                    "workspace_id": "workspace-a",
                    "node_id": "node-web-detach",
                    "current_url": root.pageUrl
                });
                var claimed = webHost._claimRetainedWebEngineItem();
                var beforeParent = root._parentName(fakePage);
                var borrowable = webHost.hasBorrowableWebEngineForDetached("node-web-detach");
                var wrongBorrowable = webHost.hasBorrowableWebEngineForDetached("wrong-node");

                var requested = webHost._requestDetached();
                var detachedWindow = webHost.detachedWindow;
                var detachedParent = root._parentName(fakePage);
                var detachedState = String(webHost.statusState || "");
                var detachedStatusVisible = Boolean(webHost.statusVisible);
                var borrowed = detachedWindow ? Boolean(detachedWindow.borrowedActive) : false;
                var standalone = detachedWindow ? Boolean(detachedWindow.standaloneHostActive) : false;
                var fullscreenBorrowed = Boolean(webHost.webEngineBorrowedForFullscreen);
                var detachedBorrowed = Boolean(webHost.webEngineBorrowedForDetached);

                var released = detachedWindow ? detachedWindow._releaseBorrowedHost() : false;
                var restoredParent = root._parentName(fakePage);
                var restoredState = String(webHost.statusState || "");
                var standaloneAfterRelease = detachedWindow ? Boolean(detachedWindow.standaloneHostActive) : true;

                detachPassed = claimed
                    && beforeParent === "webPageViewport"
                    && borrowable
                    && !wrongBorrowable
                    && requested
                    && borrowed
                    && !standalone
                    && detachedParent === "webPageDetachedBorrowedViewport"
                    && detachedState === "detached"
                    && detachedStatusVisible
                    && detachedBorrowed
                    && !fullscreenBorrowed
                    && released
                    && restoredParent === "webPageViewport"
                    && restoredState === ""
                    && !standaloneAfterRelease
                    && !webHost.webEngineBorrowedForDetached
                    && webHost.webEngineItem === fakePage;
                debugState = "claimed=" + claimed
                    + " before=" + beforeParent
                    + " borrowable=" + borrowable
                    + " wrongBorrowable=" + wrongBorrowable
                    + " requested=" + requested
                    + " borrowed=" + borrowed
                    + " standalone=" + standalone
                    + " detachedParent=" + detachedParent
                    + " detachedState=" + detachedState
                    + " detachedStatusVisible=" + detachedStatusVisible
                    + " detachedBorrowed=" + detachedBorrowed
                    + " fullscreenBorrowed=" + fullscreenBorrowed
                    + " released=" + released
                    + " restoredParent=" + restoredParent
                    + " restoredState=" + restoredState
                    + " standaloneAfterRelease=" + standaloneAfterRelease
                    + " creationError=" + webHost.webEngineCreationError;
                if (detachedWindow)
                    detachedWindow.destroy();
            }
        }
        ''',
        QUrl.fromLocalFile(str(components_dir / "web_page_host_detach_borrow_test.qml")),
    )
    assert component.status() == QQmlComponent.Status.Ready, [
        error.toString() for error in component.errors()
    ]
    harness = component.create()
    assert harness is not None

    QMetaObject.invokeMethod(harness, "runDetachBorrowRelease")
    qapp.processEvents()

    assert bool(harness.property("detachPassed")), str(harness.property("debugState"))

    harness.deleteLater()
    engine.deleteLater()
    qapp.processEvents()


def test_web_page_host_canvas_export_uses_preview_ref_fallback(qapp) -> None:  # noqa: ANN001
    engine = QQmlEngine()
    components_dir = _REPO_ROOT / "ea_node_editor" / "ui_qml" / "components"
    component = QQmlComponent(engine)
    component.setData(
        b'''
        import QtQuick 2.15
        import "web" as WebComponents

        Item {
            id: root
            property bool fallbackPassed: false
            property bool cleanupPassed: false

            Item {
                id: graphHostStub
                property var canvasItem: ({})
                property bool surfaceFullscreenAvailable: true
                property var nodeData: ({
                    "node_id": "node-web-preview",
                    "workspace_id": "workspace-a",
                    "properties": {
                        "display_mode": "fit_width",
                        "preview_ref": {"artifact_ref": "temp://web-preview"}
                    },
                    "web_page_payload": {
                        "workspace_id": "workspace-a",
                        "node_id": "node-web-preview",
                        "title": "Web Page Viewer",
                        "content_kind": "web_page",
                        "start_location": "https://example.com",
                        "current_location": "https://example.com",
                        "display_mode": "fit_width",
                        "properties": {
                            "display_mode": "fit_width",
                            "preview_ref": {"artifact_ref": "temp://web-preview"}
                        },
                        "navigation_decision": {
                            "allowed": true,
                            "target_url": "https://example.com",
                            "reason": "",
                            "original_location": "https://example.com",
                            "scheme": "https",
                            "origin": "https://example.com",
                            "is_local": false,
                            "qwebchannel_allowed": false
                        },
                        "webengine_available": false,
                        "webengine_reason": "test fake unavailable",
                        "qwebchannel_allowed": false
                    }
                })
                function surfaceFullscreenAction(enabled, primary) {
                    return {"id": "fullscreen", "label": "Fullscreen", "icon": "fullscreen", "kind": "web_page", "enabled": Boolean(enabled), "primary": Boolean(primary)};
                }
            }

            WebComponents.WebPageHost {
                id: webHost
                host: graphHostStub
                width: 400
                height: 300
            }

            function runFallback() {
                var result = webHost.prepareForCanvasExport();
                fallbackPassed = webHost.canvasExportFallbackActive
                    && Boolean(result.fallback_active)
                    && String(webHost.previewImageSource || "").indexOf("image://local-media-preview/preview?source=temp%3A%2F%2Fweb-preview") === 0;
                webHost.finishCanvasExport();
                cleanupPassed = !webHost.canvasExportFallbackActive;
            }
        }
        ''',
        QUrl.fromLocalFile(str(components_dir / "web_page_host_export_fallback_test.qml")),
    )
    assert component.status() == QQmlComponent.Status.Ready, [
        error.toString() for error in component.errors()
    ]
    harness = component.create()
    assert harness is not None

    QMetaObject.invokeMethod(harness, "runFallback")
    qapp.processEvents()

    assert bool(harness.property("fallbackPassed"))
    assert bool(harness.property("cleanupPassed"))

    harness.deleteLater()
    engine.deleteLater()
    qapp.processEvents()


def test_web_page_toolbar_uses_registered_browser_icons(qapp) -> None:  # noqa: ANN001
    engine = QQmlEngine()
    engine.addImageProvider(UI_ICON_PROVIDER_ID, UiIconImageProvider())
    icon_bridge = UiIconRegistryBridge()
    engine.rootContext().setContextProperty("uiIcons", icon_bridge)
    qml_path = _REPO_ROOT / "ea_node_editor" / "ui_qml" / "components" / "web" / "WebPageToolbar.qml"
    component = QQmlComponent(engine, QUrl.fromLocalFile(str(qml_path)))
    assert component.status() == QQmlComponent.Status.Ready, [
        error.toString() for error in component.errors()
    ]
    properties = {
        "themePalette": {
            "input_bg": "#ffffff",
            "input_fg": "#18202a",
            "input_border": "#96a6ba",
            "panel_bg": "#f5f7fa",
            "panel_title_fg": "#1b2733",
            "muted_fg": "#5f6b7a",
            "toolbar_bg": "#e5ebf2",
            "border": "#b7c2ce",
            "accent": "#eef4fb",
            "hover": "#dbe4ee",
            "pressed": "#cfd9e6",
        },
        "canGoBack": True,
        "canGoForward": True,
        "loading": False,
    }
    if hasattr(component, "createWithInitialProperties"):
        toolbar = component.createWithInitialProperties(properties)
    else:
        toolbar = component.create()
        for key, value in properties.items():
            toolbar.setProperty(key, value)
    assert toolbar is not None
    toolbar.setWidth(820)
    toolbar.setHeight(40)
    qapp.processEvents()

    icon_buttons = {
        "webPageBackButton": "browser-back",
        "webPageForwardButton": "browser-forward",
        "webPageReloadStopButton": "browser-reload",
        "webPageHomeButton": "browser-home",
        "webPageZoomOutButton": "zoom-out",
        "webPageZoomInButton": "zoom-in",
        "webPageFullscreenButton": "fullscreen",
        "webPageDetachedButton": "browser-detach",
    }
    for object_name, icon_name in icon_buttons.items():
        button = toolbar.findChild(QObject, object_name)
        assert button is not None, object_name
        assert str(button.property("iconSource")).startswith(f"image://ui-icons/{icon_name}?")

    reload_button = toolbar.findChild(QObject, "webPageReloadStopButton")
    toolbar.setProperty("loading", True)
    qapp.processEvents()
    assert str(reload_button.property("iconSource")).startswith("image://ui-icons/browser-stop?")

    address_field = toolbar.findChild(QObject, "webPageAddressField")
    assert address_field is not None
    assert QColor(address_field.property("color")).name().lower() == "#18202a"
    assert QColor(address_field.property("selectionColor")).name().lower() == "#eef4fb"
    assert QColor(address_field.property("selectedTextColor")).name().lower() == "#18202a"

    toolbar.deleteLater()
    engine.deleteLater()
    qapp.processEvents()


def test_web_page_address_popover_uses_contrast_safe_light_theme_text(qapp) -> None:  # noqa: ANN001
    engine = QQmlEngine()
    qml_path = _REPO_ROOT / "ea_node_editor" / "ui_qml" / "components" / "web" / "WebPageAddressPopover.qml"
    qml_source = qml_path.read_text(encoding="utf-8")
    assert 'import "../common" as Common' in qml_source
    assert "Common.DialogSurface {" in qml_source
    assert "Common.DialogTextField {" in qml_source
    assert "Common.DialogButton {" in qml_source
    assert "onCloseRequested: root.cancelEdit()" in qml_source
    assert "RectangularShadow" not in qml_source
    component = QQmlComponent(engine, QUrl.fromLocalFile(str(qml_path)))
    assert component.status() == QQmlComponent.Status.Ready, [
        error.toString() for error in component.errors()
    ]
    properties = {
        "themePalette": {
            "input_bg": "#f4eee8",
            "input_fg": "#1d2430",
            "input_border": "#f4c7ad",
            "panel_bg": "#fff7f1",
            "panel_title_fg": "#21160f",
            "muted_fg": "#65584f",
            "toolbar_bg": "#f6e7da",
            "border": "#d9bda9",
            "accent": "#ffe1d1",
        },
        "addressText": "https://www.youtube.com/watch?v=yfavTh4we5c",
        "width": 820.0,
        "height": 180.0,
    }
    if hasattr(component, "createWithInitialProperties"):
        popover = component.createWithInitialProperties(properties)
    else:
        popover = component.create()
        for key, value in properties.items():
            popover.setProperty(key, value)
    assert popover is not None
    qapp.processEvents()

    field = popover.findChild(QObject, "webPageAddressPopoverField")
    assert field is not None
    assert QColor(field.property("color")).name().lower() == "#1d2430"
    assert QColor(field.property("selectionColor")).name().lower() == "#ffe1d1"
    assert QColor(field.property("selectedTextColor")).name().lower() == "#1d2430"
    assert float(field.property("controlHeight")) == 36.0
    assert popover.findChild(QObject, "dialogSurfaceCloseButton") is not None

    popover.deleteLater()
    engine.deleteLater()
    qapp.processEvents()


def test_web_page_host_is_unprivileged_and_uses_dynamic_webengine_import() -> None:
    qml_path = _REPO_ROOT / "ea_node_editor" / "ui_qml" / "components" / "web" / "WebPageHost.qml"
    source = qml_path.read_text(encoding="utf-8")

    assert "import QtWebEngine" not in "\n".join(
        line for line in source.splitlines() if not line.strip().startswith('"')
    )
    assert "QtWebChannel" not in source
    assert "registerObjects" not in source
    assert "webSurfaceBridge" not in source
    assert "navigation_decision" in source
    assert '].join("\\n");' in source
    assert "WebEngineProfile" in source
    assert "function _chromeLikeUserAgent(defaultUserAgent)" in source
    assert "function _applyChromeLikeClientHints(profile)" in source
    assert 'token.indexOf(\\"QtWebEngine/\\") !== 0' in source
    assert "Chrome/" in source
    assert "Safari/537.36" in source
    assert '\\"Google Chrome\\": version' in source
    assert "profile.clientHints.fullVersionList" in source
    assert 'objectName: \\"webPageHostWebEngineProfile\\"' in source
    assert 'storageName: \\"corex_web_page_viewer\\"' in source
    assert "persistentCookiesPolicy: WebEngineProfile.ForcePersistentCookies" in source
    assert "httpUserAgent = webRoot._chromeLikeUserAgent(httpUserAgent);" in source
    assert "webRoot._applyChromeLikeClientHints(pageViewerProfile);" in source
    assert "profile: pageViewerProfile" in source
    assert "backgroundColor: webRoot.pageBackgroundColor" in source
    assert "readonly property string documentTitle: pageView.title" in source
    assert "signal documentTitleReported(string title)" in source
    assert 'function reportDocumentTitle() { webRoot.documentTitleReported(String(pageView.title || \\"\\")); }' in source
    assert "onTitleChanged: webRoot.reportDocumentTitle()" in source
    assert "settings.fullScreenSupportEnabled: true" in source
    assert "settings.playbackRequiresUserGesture: false" in source
    assert "settings.localStorageEnabled: true" in source
    assert "settings.webGLEnabled: true" in source
    assert "onFullScreenRequested" in source
    assert "onNewWindowRequested" in source
    assert "onPermissionRequested" in source
    assert "onJavaScriptConsoleMessage" in source
    assert "onRenderProcessTerminated" in source
    assert "if (!request.isMainFrame)" in source


def test_web_page_host_autofit_restarts_after_payload_and_layout_changes() -> None:
    qml_path = _REPO_ROOT / "ea_node_editor" / "ui_qml" / "components" / "web" / "WebPageHost.qml"
    source = qml_path.read_text(encoding="utf-8")

    assert "function _finishApplyPayload()" in source
    assert "objectName: \"webPageDocumentTitleLabel\"" in source
    assert "root._documentTitleFromPayload(nextPayload)" in source
    assert 'state["page_title"] = root.documentTitle;' in source
    assert "Qt.callLater(root._scheduleFitZoomReset);" in source
    assert "root._scheduleFitZoom(true);" in source
    assert "function _graphResizeActive()" in source
    assert "function _scheduleFitZoomAfterResize()" in source
    assert "id: fitZoomAfterResizeTimer" in source
    assert "root._scheduleFitZoomAfterResize();" in source
    assert "function _retryFitZoom()" in source
    assert "root._fitZoomRetryCount += 1;" in source
    assert "onWidthChanged: root._scheduleFitZoom(true, true)" in source
    assert "onHeightChanged: root._scheduleFitZoom(true, true)" in source
    assert "window.visualViewport" in source


def test_web_page_host_webengine_settings_match_packaged_qmltypes() -> None:
    pyqt6_module = importlib.import_module("PyQt6")
    qmltypes_path = Path(pyqt6_module.__file__).parent / "Qt6" / "qml" / "QtWebEngine" / "plugins.qmltypes"
    qml_path = _REPO_ROOT / "ea_node_editor" / "ui_qml" / "components" / "web" / "WebPageHost.qml"

    if not qmltypes_path.exists():
        pytest.skip("PyQt6 QtWebEngine QML metadata is not installed in this environment.")

    qmltypes_source = qmltypes_path.read_text(encoding="utf-8")
    host_source = qml_path.read_text(encoding="utf-8")

    for setting_name in [
        "fullScreenSupportEnabled",
        "playbackRequiresUserGesture",
        "localStorageEnabled",
        "webGLEnabled",
    ]:
        assert f'name: "{setting_name}"' in qmltypes_source
        assert f"settings.{setting_name}: " in host_source

    for profile_property in [
        "storageName",
        "persistentCookiesPolicy",
    ]:
        assert f'name: "{profile_property}"' in qmltypes_source
        assert f"{profile_property}: " in host_source

    assert 'name: "httpUserAgent"' in qmltypes_source
    assert 'name: "clientHints"' in qmltypes_source
    for client_hint_property in [
        "arch",
        "platform",
        "model",
        "mobile",
        "fullVersion",
        "bitness",
        "fullVersionList",
        "isAllClientHintsEnabled",
    ]:
        assert f'name: "{client_hint_property}"' in qmltypes_source
        assert f"profile.clientHints.{client_hint_property}" in host_source

    assert "httpUserAgent = webRoot._chromeLikeUserAgent(httpUserAgent);" in host_source
    assert "webRoot._applyChromeLikeClientHints(pageViewerProfile);" in host_source
    assert "ForcePersistentCookies" in qmltypes_source
    assert "WebEngineProfile.ForcePersistentCookies" in host_source
    assert "function setPageRetained(retained)" in host_source
    assert "pageView.audioMuted = retainedPaused;" in host_source
    assert "pageView.lifecycleState = retainedPaused ? WebEngineView.Frozen : WebEngineView.Active;" in host_source


def test_graph_web_browser_state_sink_does_not_retry_deleted_node_write() -> None:
    host_source = (
        _REPO_ROOT
        / "ea_node_editor"
        / "ui_qml"
        / "components"
        / "graph"
        / "GraphNodeHost.qml"
    ).read_text(encoding="utf-8")

    assert (
        'return Boolean(bridge.set_node_properties(nodeId, {"browser_state": browserState}));'
        in host_source
    )
    assert 'if (bridge.set_node_properties(nodeId, {"browser_state": browserState}))' not in host_source


def test_graph_web_browser_state_sink_respects_persistence_toggle() -> None:
    host_source = (
        _REPO_ROOT
        / "ea_node_editor"
        / "ui_qml"
        / "components"
        / "graph"
        / "GraphNodeHost.qml"
    ).read_text(encoding="utf-8")

    assert "function browserStatePersistenceEnabled()" in host_source
    assert "card.nodeData.properties.persist_browser_state" in host_source
    assert "card.nodeData.web_page_payload.persist_browser_state" in host_source
    assert "if (!browserStatePersistenceEnabled())" in host_source


def test_content_fullscreen_overlay_wires_web_page_browser_state_flush() -> None:
    source = (_REPO_ROOT / "ea_node_editor" / "ui_qml" / "ContentFullscreenOverlay.qml").read_text(
        encoding="utf-8"
    )

    assert "var activeWebPageHost = root._activeWebPageHost();" in source
    assert "activeWebPageHost.flushBrowserState()" in source
    assert "browserStateBridge: root.bridgeRef" in source


def test_asset_and_preview_methods_return_deterministic_placeholder_shapes() -> None:
    bridge = _bridge()

    assert bridge.asset_request("asset-1") == {
        "ok": False,
        "asset_id": "asset-1",
        "artifact_ref": "",
        "mime_type": "",
        "data_url": "",
        "dataURL": "",
        "error": "Asset lookup is not connected.",
    }
    assert bridge.asset_request() == {
        "ok": False,
        "asset_id": "",
        "artifact_ref": "",
        "mime_type": "",
        "data_url": "",
        "dataURL": "",
        "error": "Asset lookup is not connected.",
    }
    assert bridge.export_preview({"mime_type": "image/png"}) == {
        "ok": False,
        "preview_ref": "",
        "artifact_ref": "",
        "mime_type": "",
        "width": 0,
        "height": 0,
        "size": 0,
        "sha256": "",
        "error": "Preview export is not connected.",
    }
    assert bridge.export_preview() == {
        "ok": False,
        "preview_ref": "",
        "artifact_ref": "",
        "mime_type": "",
        "width": 0,
        "height": 0,
        "size": 0,
        "sha256": "",
        "error": "Preview export is not connected.",
    }


def test_save_state_externalizes_supported_image_dataurl_to_staged_artifact(tmp_path: Path) -> None:
    service, store, metadata_updates = _artifact_service(tmp_path)
    bridge = _bridge(artifact_service=service)
    image_payload = b"\x89PNG\r\n\x1a\nweb-surface-image"
    image_hash = hashlib.sha256(image_payload).hexdigest()
    scene_state = {
        "type": "excalidraw",
        "elements": [],
        "appState": {},
        "files": {
            "file-1": {
                "mimeType": "image/png",
                "dataURL": _data_url("image/png", image_payload),
                "created": 101,
                "lastRetrieved": 202,
                "name": "diagram.png",
            }
        },
    }

    assert bridge.save_state(scene_state) is True

    saved_file = bridge.load_state()["files"]["file-1"]
    assert "dataURL" not in saved_file
    assert saved_file["artifact_ref"].startswith("temp://")
    assert saved_file == {
        "artifact_ref": saved_file["artifact_ref"],
        "mimeType": "image/png",
        "created": 101,
        "lastRetrieved": 202,
        "size": len(image_payload),
        "sha256": image_hash,
        "name": "diagram.png",
    }
    staged_path = store.resolve_staged_path(saved_file["artifact_ref"])
    assert staged_path is not None
    assert staged_path.read_bytes() == image_payload
    assert metadata_updates
    assert saved_file["artifact_ref"][len("temp://") :] in metadata_updates[-1]["staged"]


def test_save_state_rolls_back_unsaved_batch_when_second_registration_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _bridge_module()
    metadata_updates: list[dict[str, Any]] = []
    store = ProjectArtifactStore(project_path=None, metadata=None)
    temporary_root_parent = tmp_path / "session-artifacts"
    service = module.WebSurfaceArtifactService(
        artifact_store=store,
        persist_artifact_store_metadata=metadata_updates.append,
        temporary_root_parent=temporary_root_parent,
    )
    bridge = _bridge(artifact_service=service)
    original_payloads = {
        "file-1": b"first-original-payload",
        "file-2": b"second-original-payload",
    }
    assert bridge.save_state(
        {
            "elements": [],
            "appState": {"theme": "dark"},
            "files": {
                file_id: {
                    "mimeType": "image/png",
                    "dataURL": _data_url("image/png", payload),
                    "name": f"{file_id}-original.png",
                }
                for file_id, payload in original_payloads.items()
            },
        }
    ) is True

    original_scene = bridge.load_state()
    original_metadata = copy.deepcopy(store.metadata)
    staging_root = store.active_staging_root()
    assert staging_root is not None
    staging_hint = store.staging_root_hint
    sentinel = staging_root / "unrelated.txt"
    sentinel.write_bytes(b"keep")
    original_file_map = {
        path.relative_to(staging_root).as_posix(): path.read_bytes()
        for path in staging_root.rglob("*")
        if path.is_file()
    }
    original_assets: dict[str, tuple[str, Path, bytes, str]] = {}
    for file_id, payload in original_payloads.items():
        artifact_ref = original_scene["files"][file_id]["artifact_ref"]
        artifact_path = store.resolve_staged_path(artifact_ref)
        assert artifact_path is not None
        original_assets[file_id] = (
            artifact_ref,
            artifact_path,
            payload,
            hashlib.sha256(payload).hexdigest(),
        )

    replacement_scene = {
        "elements": [],
        "appState": {"theme": "light"},
        "files": {
            "file-1": {
                "mimeType": "image/png",
                "dataURL": _data_url("image/png", b"first-replacement-payload"),
                "name": "file-1-replacement.png",
            },
            "file-2": {
                "mimeType": "image/png",
                "dataURL": _data_url("image/png", original_payloads["file-2"]),
                "name": "file-2-changed-metadata.png",
            },
        },
    }
    prepared_replacement = service.prepare_scene_state(
        replacement_scene,
        max_payload_bytes=module.MAX_SCENE_STATE_PAYLOAD_BYTES,
    )
    replacement_ids = {
        pending_write.artifact_id
        for pending_write in prepared_replacement.pending_writes
    }
    original_ids = {
        file_id: artifact_ref.removeprefix("temp://")
        for file_id, (artifact_ref, *_rest) in original_assets.items()
    }
    replacement_writes = {
        pending_write.slot: pending_write
        for pending_write in prepared_replacement.pending_writes
    }
    original_entries = {
        file_id: store.staged_entry(artifact_id)
        for file_id, artifact_id in original_ids.items()
    }
    assert all(entry is not None for entry in original_entries.values())
    file_1_entry = original_entries["file-1"]
    file_2_entry = original_entries["file-2"]
    assert file_1_entry is not None
    assert file_2_entry is not None
    assert replacement_writes[file_1_entry.slot].artifact_id != original_ids["file-1"]
    assert replacement_writes[file_2_entry.slot].artifact_id == original_ids["file-2"]
    new_replacement_ids = replacement_ids - set(original_metadata["staged"])
    assert len(new_replacement_ids) == 1
    replacement_id = new_replacement_ids.pop()

    original_register = store.register_staged_entry
    registration_count = 0

    def _fail_second_registration(*args: Any, **kwargs: Any) -> Any:
        nonlocal registration_count
        registration_count += 1
        result = original_register(*args, **kwargs)
        if registration_count == 2:
            raise module.WebSurfaceArtifactError("second-registration-marker")
        return result

    monkeypatch.setattr(store, "register_staged_entry", _fail_second_registration)

    assert bridge.save_state(replacement_scene) is False

    assert bridge.last_error == "second-registration-marker"
    assert bridge.load_state() == original_scene
    assert store.metadata == original_metadata
    assert replacement_id not in store.metadata["staged"]
    assert store.active_staging_root() == staging_root
    assert store.staging_root_hint == staging_hint
    assert sentinel.read_bytes() == b"keep"
    assert {
        path.relative_to(staging_root).as_posix(): path.read_bytes()
        for path in staging_root.rglob("*")
        if path.is_file()
    } == original_file_map
    for file_id, (
        artifact_ref,
        artifact_path,
        payload,
        payload_hash,
    ) in original_assets.items():
        assert store.resolve_staged_path(artifact_ref) == artifact_path
        assert artifact_path.read_bytes() == payload
        response = bridge.asset_request({"asset_id": file_id})
        assert response["ok"] is True
        assert response["artifact_ref"] == artifact_ref
        assert response["size"] == len(payload)
        assert response["sha256"] == payload_hash
        assert response["data_url"] == _data_url("image/png", payload)
    assert metadata_updates[-1] == original_metadata


def test_asset_request_hydrates_staged_artifact_ref_to_runtime_dataurl(tmp_path: Path) -> None:
    service, _store, _metadata_updates = _artifact_service(tmp_path)
    bridge = _bridge(artifact_service=service)
    image_payload = b"\x89PNG\r\n\x1a\nhydrated-image"
    scene_state = {
        "elements": [],
        "appState": {},
        "files": {
            "file-1": {
                "mimeType": "image/png",
                "dataURL": _data_url("image/png", image_payload),
                "created": 1,
                "lastRetrieved": 2,
            }
        },
    }
    assert bridge.save_state(scene_state) is True

    response = bridge.asset_request({"asset_id": "file-1"})

    assert response["ok"] is True
    assert response["asset_id"] == "file-1"
    assert response["artifact_ref"] == bridge.load_state()["files"]["file-1"]["artifact_ref"]
    assert response["mime_type"] == "image/png"
    assert response["size"] == len(image_payload)
    assert response["sha256"] == hashlib.sha256(image_payload).hexdigest()
    assert response["data_url"] == _data_url("image/png", image_payload)
    assert response["dataURL"] == response["data_url"]
    assert response["error"] == ""


def test_bridge_can_build_artifact_service_from_project_metadata_callbacks(tmp_path: Path) -> None:
    project_path = tmp_path / "callback-board.cxproj"
    project_metadata: dict[str, Any] = {"title": "Callback board"}
    persisted_metadata: list[dict[str, Any]] = []
    image_payload = b"\x89PNG\r\n\x1a\ncallback-image"

    bridge = _bridge(
        project_path=lambda: project_path,
        project_metadata=lambda: project_metadata,
        persist_project_metadata=persisted_metadata.append,
        temporary_root_parent=tmp_path / "unused-for-saved-project",
    )

    assert bridge.save_state(
        {
            "elements": [],
            "appState": {},
            "files": {
                "file-1": {
                    "mimeType": "image/png",
                    "dataURL": _data_url("image/png", image_payload),
                    "created": 1,
                    "lastRetrieved": 2,
                }
            },
        }
    ) is True

    assert persisted_metadata
    assert persisted_metadata[-1]["title"] == "Callback board"
    artifact_metadata = persisted_metadata[-1]["artifact_store"]
    staged_ref = bridge.load_state()["files"]["file-1"]["artifact_ref"]
    assert staged_ref[len("temp://") :] in artifact_metadata["staged"]
    hydrated = bridge.asset_request({"artifact_ref": staged_ref})
    assert hydrated["ok"] is True
    assert hydrated["data_url"] == _data_url("image/png", image_payload)


def test_save_state_rejects_unsupported_image_dataurl_without_mutating_state(tmp_path: Path) -> None:
    service, store, metadata_updates = _artifact_service(tmp_path)
    bridge = _bridge(artifact_service=service)
    original_state = {"elements": [], "appState": {"theme": "light"}, "files": {}}
    assert bridge.save_state(original_state) is True

    result = bridge.save_state(
        {
            "elements": [],
            "appState": {},
            "files": {
                "file-1": {
                    "mimeType": "image/svg+xml",
                    "dataURL": _data_url("image/svg+xml", b"<svg/>"),
                    "created": 1,
                    "lastRetrieved": 2,
                }
            },
        }
    )

    assert result is False
    assert bridge.load_state() == original_state
    assert bridge.has_error is True
    assert "Unsupported image MIME type" in bridge.last_error
    assert store.metadata["staged"] == {}
    assert metadata_updates == []


def test_save_state_rejects_oversized_image_dataurl_without_mutating_state(tmp_path: Path) -> None:
    service, store, metadata_updates = _artifact_service(tmp_path)
    bridge = _bridge(artifact_service=service, max_payload_bytes=128)
    original_state = {"elements": [], "appState": {"name": "Original"}, "files": {}}
    assert bridge.save_state(original_state) is True

    result = bridge.save_state(
        {
            "elements": [],
            "appState": {},
            "files": {
                "file-1": {
                    "mimeType": "image/png",
                    "dataURL": _data_url("image/png", b"x" * 256),
                    "created": 1,
                    "lastRetrieved": 2,
                }
            },
        }
    )

    assert result is False
    assert bridge.load_state() == original_state
    assert "Image payload exceeds 128 bytes" in bridge.last_error
    assert store.metadata["staged"] == {}
    assert metadata_updates == []


def test_export_preview_writes_png_preview_artifact_and_returns_metadata(tmp_path: Path) -> None:
    service, store, metadata_updates = _artifact_service(tmp_path)
    bridge = _bridge(artifact_service=service)
    preview_payload = b"\x89PNG\r\n\x1a\npreview"
    preview_hash = hashlib.sha256(preview_payload).hexdigest()

    result = bridge.export_preview(
        {
            "dataURL": _data_url("image/png", preview_payload),
            "width": 640,
            "height": 360,
            "name": "preview.png",
        }
    )

    assert result == {
        "ok": True,
        "preview_ref": result["preview_ref"],
        "artifact_ref": result["preview_ref"],
        "mime_type": "image/png",
        "width": 640,
        "height": 360,
        "size": len(preview_payload),
        "sha256": preview_hash,
        "error": "",
    }
    assert result["preview_ref"].startswith("temp://")
    preview_path = store.resolve_staged_path(result["preview_ref"])
    assert preview_path is not None
    assert preview_path.read_bytes() == preview_payload
    assert metadata_updates

    hydrated = bridge.asset_request(result["preview_ref"])
    assert hydrated["ok"] is True
    assert hydrated["artifact_ref"] == result["preview_ref"]
    assert hydrated["data_url"] == _data_url("image/png", preview_payload)


def test_export_preview_scopes_staged_payloads_per_surface(tmp_path: Path) -> None:
    service, store, _metadata_updates = _artifact_service(tmp_path)
    first_bridge = _bridge(artifact_service=service, artifact_scope="workspace-main:board-a")
    second_bridge = _bridge(artifact_service=service, artifact_scope="workspace-main:board-b")
    first_payload = b"\x89PNG\r\n\x1a\nfirst-board-preview"
    second_payload = b"\x89PNG\r\n\x1a\nsecond-board-preview"

    first_result = first_bridge.export_preview(
        {
            "dataURL": _data_url("image/png", first_payload),
            "width": 640,
            "height": 360,
            "name": "first-preview.png",
        }
    )
    second_result = second_bridge.export_preview(
        {
            "dataURL": _data_url("image/png", second_payload),
            "width": 640,
            "height": 360,
            "name": "second-preview.png",
        }
    )

    assert first_result["ok"] is True
    assert second_result["ok"] is True
    assert first_result["preview_ref"] != second_result["preview_ref"]
    first_path = store.resolve_staged_path(first_result["preview_ref"])
    second_path = store.resolve_staged_path(second_result["preview_ref"])
    assert first_path is not None
    assert second_path is not None
    assert first_path.read_bytes() == first_payload
    assert second_path.read_bytes() == second_payload
    first_id = first_result["preview_ref"][len("temp://") :]
    second_id = second_result["preview_ref"][len("temp://") :]
    staged_metadata = store.metadata["staged"]
    assert staged_metadata[first_id]["slot"] != staged_metadata[second_id]["slot"]


def test_export_preview_rejects_non_png_preview_payload(tmp_path: Path) -> None:
    service, store, metadata_updates = _artifact_service(tmp_path)
    bridge = _bridge(artifact_service=service)

    result = bridge.export_preview({"dataURL": _data_url("image/jpeg", b"jpeg")})

    assert result["ok"] is False
    assert result["preview_ref"] == ""
    assert "Unsupported image MIME type" in result["error"]
    assert store.metadata["staged"] == {}
    assert metadata_updates == []

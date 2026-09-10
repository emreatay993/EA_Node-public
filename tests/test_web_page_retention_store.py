from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QMetaObject, QUrl
from PyQt6.QtQml import QQmlComponent, QQmlEngine

_REPO_ROOT = Path(__file__).resolve().parents[1]
_COMPONENTS_DIR = _REPO_ROOT / "ea_node_editor" / "ui_qml" / "components"


def _create_harness(engine: QQmlEngine, source: bytes):
    component = QQmlComponent(engine)
    component.setData(
        source,
        QUrl.fromLocalFile(str(_COMPONENTS_DIR / "web_page_retention_test.qml")),
    )
    assert component.status() == QQmlComponent.Status.Ready, [
        error.toString() for error in component.errors()
    ]
    item = component.create()
    assert item is not None
    return item


def test_web_page_retention_store_parks_claims_and_protects_target_workspace(qapp) -> None:  # noqa: ANN001
    engine = QQmlEngine()
    harness = _create_harness(
        engine,
        b'''
        import QtQuick 2.15
        import "web" as WebComponents

        Item {
            id: root
            property bool basicPassed: false
            property bool mismatchPassed: false
            property bool lruPassed: false
            property bool gracePassed: false

            WebComponents.WebPageRetentionStore {
                id: store
                maxRetainedPages: 2
            }

            Item { id: claimTarget; objectName: "claimTarget" }
            Item {
                id: pageA
                objectName: "pageA"
                property bool retainedPaused: false
                function setPageRetained(paused) {
                    retainedPaused = Boolean(paused);
                    visible = !retainedPaused;
                }
            }
            Item {
                id: pageB
                objectName: "pageB"
                property bool retainedPaused: false
                function setPageRetained(paused) {
                    retainedPaused = Boolean(paused);
                    visible = !retainedPaused;
                }
            }
            Item {
                id: pageC
                objectName: "pageC"
                property bool retainedPaused: false
                function setPageRetained(paused) {
                    retainedPaused = Boolean(paused);
                    visible = !retainedPaused;
                }
            }
            Item {
                id: pageD
                objectName: "pageD"
                property bool retainedPaused: false
                function setPageRetained(paused) {
                    retainedPaused = Boolean(paused);
                    visible = !retainedPaused;
                }
            }

            function runBasic() {
                var key = store.keyFor("ws_a", "node_a");
                store.beginWorkspaceSwitch("ws_b");
                var parked = store.parkPage(
                    key,
                    pageA,
                    {"workspace_id": "ws_a", "node_id": "node_a", "current_url": "https://example.com/a"}
                );
                var parkedParentName = pageA.parent ? String(pageA.parent.objectName || "") : "";
                var claimed = store.claimPage(key, "https://example.com/a", claimTarget);
                basicPassed = parked
                    && parkedParentName === "webPageRetentionParkingLot"
                    && claimed === pageA
                    && pageA.parent === claimTarget
                    && pageA.visible
                    && !pageA.retainedPaused
                    && store.retainedCount() === 0;
            }

            function runGraceWindow() {
                store.workspaceSwitchParkingGraceMs = 500;
                store.beginWorkspaceSwitch("ws_b");
                gracePassed = store.shouldParkForWorkspaceSwitch();
                store.finishWorkspaceSwitch();
            }

            function runMismatch() {
                var key = store.keyFor("ws_a", "node_b");
                store.parkPage(
                    key,
                    pageB,
                    {"workspace_id": "ws_a", "node_id": "node_b", "current_url": "https://example.com/old"}
                );
                var claimed = store.claimPage(key, "https://example.com/new", claimTarget);
                mismatchPassed = claimed === null && !store.containsKey(key);
            }

            function runLru() {
                var keyA = store.keyFor("ws_a", "node_lru_a");
                var keyC = store.keyFor("ws_c", "node_lru_c");
                var keyD = store.keyFor("ws_c", "node_lru_d");
                store.beginWorkspaceSwitch("ws_a");
                store.parkPage(
                    keyA,
                    pageA,
                    {"workspace_id": "ws_a", "node_id": "node_lru_a", "current_url": "https://example.com/a"}
                );
                store.parkPage(
                    keyC,
                    pageC,
                    {"workspace_id": "ws_c", "node_id": "node_lru_c", "current_url": "https://example.com/c"}
                );
                store.parkPage(
                    keyD,
                    pageD,
                    {"workspace_id": "ws_c", "node_id": "node_lru_d", "current_url": "https://example.com/d"}
                );
                lruPassed = store.retainedCount() === 2
                    && store.containsKey(keyA)
                    && !store.containsKey(keyC)
                    && store.containsKey(keyD);
            }
        }
        ''',
    )

    QMetaObject.invokeMethod(harness, "runBasic")
    QMetaObject.invokeMethod(harness, "runGraceWindow")
    QMetaObject.invokeMethod(harness, "runMismatch")
    QMetaObject.invokeMethod(harness, "runLru")
    qapp.processEvents()

    assert bool(harness.property("basicPassed"))
    assert bool(harness.property("gracePassed"))
    assert bool(harness.property("mismatchPassed"))
    assert bool(harness.property("lruPassed"))

    harness.deleteLater()
    engine.deleteLater()
    qapp.processEvents()


def test_graph_canvas_layers_own_web_page_retention_store_above_node_delegates() -> None:
    root_layers_source = (
        _REPO_ROOT
        / "ea_node_editor"
        / "ui_qml"
        / "components"
        / "graph_canvas"
        / "GraphCanvasRootLayers.qml"
    ).read_text(encoding="utf-8")
    graph_canvas_source = (
        _REPO_ROOT / "ea_node_editor" / "ui_qml" / "components" / "GraphCanvas.qml"
    ).read_text(encoding="utf-8")

    assert "WebComponents.WebPageRetentionStore" in root_layers_source
    assert 'objectName: "graphCanvasWebPageRetentionStore"' in root_layers_source
    assert "function onScene_workspace_changing(workspaceId)" in root_layers_source
    assert "function onWorkspace_changed(workspaceId)" in root_layers_source
    assert "function onScene_workspace_changed(workspaceId)" in root_layers_source
    assert "webPageRetentionStore.beginWorkspaceSwitch" in root_layers_source
    assert "workspaceSwitchParkingGraceMs" in (
        _REPO_ROOT
        / "ea_node_editor"
        / "ui_qml"
        / "components"
        / "web"
        / "WebPageRetentionStore.qml"
    ).read_text(encoding="utf-8")
    assert "readonly property var webPageRetentionStore: rootLayers.webPageRetentionStore" in graph_canvas_source
    assert "rootLayers.clearRetainedWebPages();" in graph_canvas_source

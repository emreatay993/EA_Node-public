from __future__ import annotations

from pathlib import Path
from typing import Any

from PyQt6.QtCore import QObject, QUrl
from PyQt6.QtQml import QQmlComponent, QQmlEngine

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SURFACE_QML = (
    _REPO_ROOT
    / "ea_node_editor"
    / "ui_qml"
    / "components"
    / "graph"
    / "jupyter"
    / "GraphJupyterNotebookSurface.qml"
)
_OVERLAY_QML = _REPO_ROOT / "ea_node_editor" / "ui_qml" / "ContentFullscreenOverlay.qml"


def _payload(*, jupyter: bool, webengine: bool, notebook_ref: str = "") -> dict[str, Any]:
    return {
        "node_id": "node-jupyter",
        "content_kind": "jupyter_notebook",
        "notebook_ref": notebook_ref,
        "notebook_location": "",
        "frontend": "notebook",
        "jupyter_available": jupyter,
        "webengine_available": webengine,
    }


def _make_surface(qapp, payload: dict[str, Any]):  # noqa: ANN001
    engine = QQmlEngine()
    component = QQmlComponent(engine, QUrl.fromLocalFile(str(_SURFACE_QML)))
    assert component.status() == QQmlComponent.Status.Ready, [
        error.toString() for error in component.errors()
    ]
    host_component = QQmlComponent(engine)
    host_component.setData(b"import QtQuick 2.15\nItem { property var nodeData: ({}) }", QUrl())
    host = host_component.create()
    host.setProperty("nodeData", {"node_id": "node-jupyter", "jupyter_notebook_payload": payload})
    surface = component.createWithInitialProperties({"host": host})
    assert surface is not None
    surface.setWidth(420)
    surface.setHeight(320)
    qapp.processEvents()
    return engine, host, surface


def test_surface_reports_jupyter_unavailable_without_webengine_view(qapp) -> None:  # noqa: ANN001
    engine, host, surface = _make_surface(qapp, _payload(jupyter=False, webengine=False))
    try:
        assert str(surface.property("statusState")) == "jupyter_unavailable"
        pane = surface.findChild(QObject, "jupyterNotebookStatusPane")
        message = surface.findChild(QObject, "jupyterNotebookStatusMessage")
        assert pane is not None and bool(pane.property("visible"))
        assert "pip install" in str(message.property("text"))
        assert surface.findChild(QObject, "jupyterNotebookWebEngineView") is None
    finally:
        surface.deleteLater()
        host.deleteLater()
        engine.deleteLater()
        qapp.processEvents()


def test_surface_reports_webengine_unavailable_when_jupyter_present(qapp) -> None:  # noqa: ANN001
    engine, host, surface = _make_surface(qapp, _payload(jupyter=True, webengine=False))
    try:
        assert str(surface.property("statusState")) == "webengine_unavailable"
        assert surface.findChild(QObject, "jupyterNotebookWebEngineView") is None
    finally:
        surface.deleteLater()
        host.deleteLater()
        engine.deleteLater()
        qapp.processEvents()


def test_surface_prompts_for_notebook_when_none_selected(qapp) -> None:  # noqa: ANN001
    engine, host, surface = _make_surface(
        qapp, _payload(jupyter=True, webengine=True, notebook_ref="")
    )
    try:
        assert str(surface.property("statusState")) == "no_notebook"
        message = surface.findChild(QObject, "jupyterNotebookStatusMessage")
        assert "notebook" in str(message.property("text")).lower()
        assert surface.findChild(QObject, "jupyterNotebookWebEngineView") is None
    finally:
        surface.deleteLater()
        host.deleteLater()
        engine.deleteLater()
        qapp.processEvents()


def test_surface_source_uses_real_newline_join_for_dynamic_webengine() -> None:
    source = _SURFACE_QML.read_text(encoding="utf-8")
    assert '].join("\\n");' in source
    assert "import QtWebEngine" in source
    assert 'storageName: \\"corex_jupyter\\"' in source


def test_surface_source_exposes_live_fullscreen_handoff() -> None:
    source = _SURFACE_QML.read_text(encoding="utf-8")

    assert "readonly property var surfaceActions" in source
    assert 'String(actionId || "") === "fullscreen"' in source
    assert "function hasBorrowableWebEngineForFullscreen(nodeId)" in source
    assert "function attachWebEngineToFullscreen(target, nodeId)" in source
    assert "function releaseFullscreenWebEngine()" in source
    assert "root._externalWebEngineBorrowMode" in source
    assert "host.requestSurfaceContentFullscreen()" in source


def test_fullscreen_overlay_accepts_jupyter_borrowed_webengine() -> None:
    source = _OVERLAY_QML.read_text(encoding="utf-8")

    assert 'root.contentKind === "jupyter_notebook"' in source
    assert 'objectName === "graphJupyterNotebookSurface"' in source
    assert "contentFullscreenJupyterPlaceholder" in source
    assert "candidate.attachWebEngineToFullscreen" in source

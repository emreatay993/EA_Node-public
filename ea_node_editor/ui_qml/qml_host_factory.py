from __future__ import annotations

import logging
import os
from typing import Any, Protocol

from PyQt6.QtCore import QObject, QUrl, Qt
from PyQt6.QtQml import QQmlContext, QQmlEngine
from PyQt6.QtQuick import QQuickItem, QQuickView, QQuickWindow
from PyQt6.QtQuickWidgets import QQuickWidget
from PyQt6.QtWidgets import QWidget

from ea_node_editor.telemetry.startup_profile import phase

LOGGER = logging.getLogger(__name__)

QML_HOST_ENV = "EA_NODE_EDITOR_QML_HOST"
QML_HOST_QQUICKWIDGET = "qquickwidget"
QML_HOST_QQUICKVIEW_CONTAINER = "qquickview_container"
QML_HOST_SELECTION_REASON_ENV = "env_override"
QML_HOST_SELECTION_REASON_INVALID_ENV = "invalid_env_default"
QML_HOST_SELECTION_REASON_COMPATIBILITY_DEFAULT = "compatibility_default"
_SUPPORTED_QML_HOSTS = {
    QML_HOST_QQUICKWIDGET,
    QML_HOST_QQUICKVIEW_CONTAINER,
}


class ShellQmlHost(Protocol):
    host_kind: str
    container_widget: QWidget
    overlay_parent_widget: QWidget
    event_filter_widget: QObject

    def engine(self) -> QQmlEngine: ...

    def root_context(self) -> QQmlContext: ...

    def root_object(self) -> QQuickItem | QObject | None: ...

    def set_resize_mode_to_root_object(self) -> None: ...

    def set_source(self, url: QUrl) -> None: ...

    def source(self) -> QUrl: ...

    def status(self) -> Any: ...

    def errors(self) -> list[Any]: ...

    def quick_window(self) -> QQuickWindow | None: ...

    def teardown(self) -> None: ...


def normalize_qml_host_kind(value: Any) -> str:
    normalized = str(value or "").strip().lower().replace("-", "_")
    if normalized in _SUPPORTED_QML_HOSTS:
        return normalized
    return ""


def default_qml_host_kind() -> str:
    return QML_HOST_QQUICKWIDGET


def qml_host_selection_reason(value: Any | None = None) -> str:
    requested = os.environ.get(QML_HOST_ENV, "").strip() if value is None else str(value or "").strip()
    if requested and normalize_qml_host_kind(requested):
        return QML_HOST_SELECTION_REASON_ENV
    if requested:
        return QML_HOST_SELECTION_REASON_INVALID_ENV
    return QML_HOST_SELECTION_REASON_COMPATIBILITY_DEFAULT


def select_qml_host_kind_from_environment() -> str:
    requested = os.environ.get(QML_HOST_ENV, "").strip()
    normalized = normalize_qml_host_kind(requested)
    if not requested:
        return default_qml_host_kind()
    if normalized:
        return normalized
    default_host = default_qml_host_kind()
    LOGGER.warning(
        "Unsupported %s=%r; supported values are %s and %s. Using %s.",
        QML_HOST_ENV,
        requested,
        QML_HOST_QQUICKWIDGET,
        QML_HOST_QQUICKVIEW_CONTAINER,
        default_host,
    )
    return default_host


def qml_host_environment_snapshot() -> dict[str, str]:
    requested = os.environ.get(QML_HOST_ENV, "").strip()
    return {
        "qml_host_env": requested,
        "qml_host_kind_selected": select_qml_host_kind_from_environment(),
        "qml_host_default_kind": default_qml_host_kind(),
        "qml_host_selection_reason": qml_host_selection_reason(requested),
    }


class QQuickWidgetHost:
    host_kind = QML_HOST_QQUICKWIDGET

    def __init__(self, parent: QWidget) -> None:
        self.widget = QQuickWidget(parent)
        self.container_widget = self.widget
        self.overlay_parent_widget = self.widget
        self.event_filter_widget = self.widget

    def engine(self) -> QQmlEngine:
        return self.widget.engine()

    def root_context(self) -> QQmlContext:
        return self.widget.rootContext()

    def root_object(self) -> QQuickItem | QObject | None:
        return self.widget.rootObject()

    def rootObject(self) -> QQuickItem | QObject | None:  # noqa: N802
        return self.root_object()

    def rootContext(self) -> QQmlContext:  # noqa: N802
        return self.root_context()

    def set_resize_mode_to_root_object(self) -> None:
        self.widget.setResizeMode(QQuickWidget.ResizeMode.SizeRootObjectToView)

    def setResizeMode(self, mode: QQuickWidget.ResizeMode) -> None:  # noqa: N802
        self.widget.setResizeMode(mode)

    def set_source(self, url: QUrl) -> None:
        with phase("qml.set_source"):
            self.widget.setSource(url)

    def setSource(self, url: QUrl) -> None:  # noqa: N802
        self.set_source(url)

    def source(self) -> QUrl:
        return self.widget.source()

    def status(self) -> Any:
        return self.widget.status()

    def errors(self) -> list[Any]:
        return list(self.widget.errors())

    def quick_window(self) -> QQuickWindow | None:
        return self.widget.quickWindow()

    def quickWindow(self) -> QQuickWindow | None:  # noqa: N802
        return self.quick_window()

    def teardown(self) -> None:
        try:
            self.widget.setUpdatesEnabled(False)
        except Exception:  # noqa: BLE001
            pass
        self.widget.setSource(QUrl())


class QQuickViewContainerHost:
    host_kind = QML_HOST_QQUICKVIEW_CONTAINER

    def __init__(self, parent: QWidget) -> None:
        self.view = QQuickView()
        self.view.setObjectName("mainShellQQuickView")
        self.container_widget = QWidget.createWindowContainer(self.view, parent)
        self.container_widget.setObjectName("mainShellQQuickViewContainer")
        self.container_widget.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.overlay_parent_widget = self.container_widget
        self.event_filter_widget = self.container_widget

    def engine(self) -> QQmlEngine:
        return self.view.engine()

    def root_context(self) -> QQmlContext:
        return self.view.rootContext()

    def root_object(self) -> QQuickItem | QObject | None:
        return self.view.rootObject()

    def rootObject(self) -> QQuickItem | QObject | None:  # noqa: N802
        return self.root_object()

    def rootContext(self) -> QQmlContext:  # noqa: N802
        return self.root_context()

    def set_resize_mode_to_root_object(self) -> None:
        self.view.setResizeMode(QQuickView.ResizeMode.SizeRootObjectToView)

    def setResizeMode(self, mode: QQuickView.ResizeMode) -> None:  # noqa: N802
        self.view.setResizeMode(mode)

    def set_source(self, url: QUrl) -> None:
        with phase("qml.set_source"):
            self.view.setSource(url)

    def setSource(self, url: QUrl) -> None:  # noqa: N802
        self.set_source(url)

    def source(self) -> QUrl:
        return self.view.source()

    def status(self) -> Any:
        return self.view.status()

    def errors(self) -> list[Any]:
        return list(self.view.errors())

    def quick_window(self) -> QQuickWindow | None:
        return self.view

    def quickWindow(self) -> QQuickWindow | None:  # noqa: N802
        return self.quick_window()

    def setCursor(self, cursor) -> None:  # noqa: ANN001, N802
        self.container_widget.setCursor(cursor)
        self.view.setCursor(cursor)

    def unsetCursor(self) -> None:  # noqa: N802
        self.container_widget.unsetCursor()
        self.view.unsetCursor()

    def setFocus(self) -> None:  # noqa: N802
        self.container_widget.setFocus()

    def rect(self):
        return self.container_widget.rect()

    def isVisible(self) -> bool:  # noqa: N802
        return self.container_widget.isVisible()

    def teardown(self) -> None:
        try:
            self.container_widget.setUpdatesEnabled(False)
        except Exception:  # noqa: BLE001
            pass
        self.view.setSource(QUrl())
        self.view.close()


def create_shell_qml_host(parent: QWidget, *, host_kind: str | None = None) -> ShellQmlHost:
    resolved_kind = (
        normalize_qml_host_kind(host_kind)
        if host_kind is not None
        else select_qml_host_kind_from_environment()
    )
    if resolved_kind == QML_HOST_QQUICKVIEW_CONTAINER:
        return QQuickViewContainerHost(parent)
    return QQuickWidgetHost(parent)


__all__ = [
    "QML_HOST_ENV",
    "QML_HOST_QQUICKVIEW_CONTAINER",
    "QML_HOST_QQUICKWIDGET",
    "ShellQmlHost",
    "create_shell_qml_host",
    "default_qml_host_kind",
    "normalize_qml_host_kind",
    "qml_host_environment_snapshot",
    "qml_host_selection_reason",
    "select_qml_host_kind_from_environment",
]

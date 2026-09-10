# Purpose: Bridge Add-On Manager state, hot apply, and asynchronous managed installation to QML.
# Map: feature_routes/addon_manager.md
# Tests: tests/test_addon_manager_install.py

from __future__ import annotations

import logging
from collections.abc import Callable

from PyQt6.QtCore import QObject, QThread, pyqtProperty, pyqtSignal, pyqtSlot
from PyQt6.QtQml import qmlRegisterType

from ea_node_editor.execution.managed_runtime import (
    ManagedRuntimeInstallResult,
    prepare_addon_runtime,
)
from ea_node_editor.ui.shell.presenters.addon_manager_presenter import AddOnManagerPresenter

_QML_IMPORT_NAME = "EA.NodeEditor"
_QML_IMPORT_MAJOR_VERSION = 1
_QML_IMPORT_MINOR_VERSION = 0
_QML_TYPE_NAME = "ShellAddOnManagerBridge"
_QML_REGISTERED = False
logger = logging.getLogger(__name__)


class _AddOnInstallWorker(QObject):
    progress = pyqtSignal(str, str)
    finished = pyqtSignal(str, object)

    def __init__(
        self,
        addon_id: str,
        package_ids: tuple[str, ...],
        prepare: Callable[
            [tuple[str, ...], Callable[[str], None]],
            ManagedRuntimeInstallResult,
        ],
    ) -> None:
        super().__init__()
        self._addon_id = addon_id
        self._package_ids = package_ids
        self._prepare = prepare

    @pyqtSlot()
    def run(self) -> None:
        try:
            result = self._prepare(
                self._package_ids,
                lambda message: self.progress.emit(self._addon_id, message),
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("Managed add-on installation failed")
            result = ManagedRuntimeInstallResult(
                success=False,
                error=f"Managed add-on installation failed: {exc}",
            )
        self.finished.emit(self._addon_id, result)


class ShellAddOnManagerBridge(QObject):
    request_bridge_changed = pyqtSignal()
    workspace_bridge_changed = pyqtSignal()
    viewer_host_service_changed = pyqtSignal()
    state_changed = pyqtSignal()

    def __init__(
        self,
        parent: QObject | None = None,
        *,
        managed_runtime_prepare: Callable[
            [tuple[str, ...], Callable[[str], None]],
            ManagedRuntimeInstallResult,
        ]
        | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("shellAddOnManagerBridge")
        self._presenter = AddOnManagerPresenter()
        self._request_bridge = None
        self._workspace_bridge = None
        self._viewer_host_service = None
        self._managed_runtime_prepare = managed_runtime_prepare or (
            lambda package_ids, progress_callback: prepare_addon_runtime(
                package_ids=package_ids,
                progress_callback=progress_callback,
            )
        )
        self._install_thread: QThread | None = None
        self._install_worker: _AddOnInstallWorker | None = None
        self._installing_addon_id = ""
        self._install_progress_text = ""

    @pyqtProperty(QObject, notify=request_bridge_changed)
    def requestBridge(self) -> QObject | None:  # noqa: N802
        return self._request_bridge

    @requestBridge.setter
    def requestBridge(self, bridge: QObject | None) -> None:  # noqa: N802
        if self._request_bridge is bridge:
            return
        previous = self._request_bridge
        if previous is not None:
            try:
                previous.state_changed.disconnect(self._on_request_state_changed)
            except (AttributeError, TypeError):
                pass
        self._request_bridge = bridge
        if bridge is not None:
            try:
                bridge.state_changed.connect(self._on_request_state_changed)
            except AttributeError:
                pass
        self._sync_presenter_bindings()
        self.request_bridge_changed.emit()
        self._refresh_from_request()

    @pyqtProperty(QObject, notify=workspace_bridge_changed)
    def workspaceBridge(self) -> QObject | None:  # noqa: N802
        return self._workspace_bridge

    @workspaceBridge.setter
    def workspaceBridge(self, bridge: QObject | None) -> None:  # noqa: N802
        if self._workspace_bridge is bridge:
            return
        self._workspace_bridge = bridge
        self._sync_presenter_bindings()
        self.workspace_bridge_changed.emit()
        self._refresh_from_request()

    @pyqtProperty(QObject, notify=viewer_host_service_changed)
    def viewerHostServiceRef(self) -> QObject | None:  # noqa: N802
        return self._viewer_host_service

    @viewerHostServiceRef.setter
    def viewerHostServiceRef(self, service: QObject | None) -> None:  # noqa: N802
        if self._viewer_host_service is service:
            return
        self._viewer_host_service = service
        self._sync_presenter_bindings()
        self.viewer_host_service_changed.emit()
        self.state_changed.emit()

    @pyqtProperty(bool, notify=state_changed)
    def hasSelection(self) -> bool:  # noqa: N802
        return self._presenter.has_selection

    @pyqtProperty(str, notify=state_changed)
    def selectedAddonId(self) -> str:  # noqa: N802
        return self._presenter.selected_addon_id

    @pyqtProperty(int, notify=state_changed)
    def requestSerial(self) -> int:  # noqa: N802
        return self._presenter.request_serial

    @pyqtProperty(str, notify=state_changed)
    def activeTab(self) -> str:  # noqa: N802
        return self._presenter.active_tab

    @pyqtProperty(str, notify=state_changed)
    def statusFilter(self) -> str:  # noqa: N802
        return self._presenter.status_filter

    @pyqtProperty(int, notify=state_changed)
    def rowCount(self) -> int:  # noqa: N802
        return self._presenter.row_count

    @pyqtProperty(int, notify=state_changed)
    def pendingRestartCount(self) -> int:  # noqa: N802
        return self._presenter.pending_restart_count

    @pyqtProperty(str, notify=state_changed)
    def summaryText(self) -> str:  # noqa: N802
        return self._presenter.summary_text

    @pyqtProperty(str, notify=state_changed)
    def lastError(self) -> str:  # noqa: N802
        return self._presenter.last_error

    @pyqtProperty(bool, notify=state_changed)
    def installing(self) -> bool:
        return self._install_thread is not None

    @pyqtProperty(str, notify=state_changed)
    def installingAddonId(self) -> str:  # noqa: N802
        return self._installing_addon_id

    @pyqtProperty(str, notify=state_changed)
    def installProgressText(self) -> str:  # noqa: N802
        return self._install_progress_text

    @pyqtProperty("QVariantList", notify=state_changed)
    def filteredRows(self) -> list[dict]:  # noqa: N802
        return self._presenter.filtered_rows()

    @pyqtProperty("QVariantMap", notify=state_changed)
    def selectedAddon(self) -> dict:  # noqa: N802
        return self._presenter.selected_payload()

    @pyqtSlot()
    def refresh(self) -> None:
        self._refresh_from_request()

    @pyqtSlot(str)
    def setActiveTab(self, tab_id: str) -> None:  # noqa: N802
        self._presenter.set_active_tab(tab_id)
        self.state_changed.emit()

    @pyqtSlot(str)
    def setStatusFilter(self, filter_id: str) -> None:  # noqa: N802
        self._presenter.set_status_filter(filter_id)
        self.state_changed.emit()

    @pyqtSlot(str)
    def selectAddon(self, addon_id: str) -> None:  # noqa: N802
        self._presenter.select_addon(addon_id)
        self.state_changed.emit()

    @pyqtSlot(str, bool, result=bool)
    def setAddonEnabled(self, addon_id: str, enabled: bool) -> bool:  # noqa: N802
        if self.installing:
            return False
        applied = self._presenter.set_addon_enabled(addon_id, enabled)
        self.state_changed.emit()
        return applied

    @pyqtSlot(result=bool)
    def toggleSelectedAddon(self) -> bool:  # noqa: N802
        selected = self._presenter.selected_payload()
        addon_id = str(selected.get("addonId", "")).strip()
        if not addon_id:
            return False
        enabled = bool(selected.get("enabled"))
        return self.setAddonEnabled(addon_id, not enabled)

    @pyqtSlot(result=bool)
    def installSelectedAddon(self) -> bool:  # noqa: N802
        if self.installing:
            return False
        selected = self._presenter.selected_payload()
        addon_id = str(selected.get("addonId", "")).strip()
        package_ids = tuple(
            str(value).strip()
            for value in selected.get("managedRuntimePackageIds", ())
            if str(value).strip()
        )
        if not addon_id or not package_ids or not bool(selected.get("installable")):
            return False
        shell_window = self._shell_window()
        run_state = getattr(shell_window, "run_state", None)
        if str(getattr(run_state, "active_run_id", "") or "").strip():
            self._presenter.set_error(
                "Stop the active workflow before installing or updating an add-on."
            )
            self.state_changed.emit()
            return False

        self._presenter.clear_error()
        thread = QThread(self)
        worker = _AddOnInstallWorker(
            addon_id,
            package_ids,
            self._managed_runtime_prepare,
        )
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.progress.connect(self._on_install_progress)
        worker.finished.connect(self._on_install_finished)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._on_install_thread_finished)
        self._install_thread = thread
        self._install_worker = worker
        self._installing_addon_id = addon_id
        self._install_progress_text = "Preparing the COREX Python environment..."
        self.state_changed.emit()
        thread.start()
        return True

    @pyqtSlot()
    def requestOpenWorkflowSettings(self) -> None:  # noqa: N802
        self._presenter.open_workflow_settings()
        self.state_changed.emit()

    @pyqtSlot()
    def requestClose(self) -> None:  # noqa: N802
        if self.installing:
            self._presenter.set_error(
                "Wait for add-on installation to finish before closing the manager."
            )
            self.state_changed.emit()
            return
        bridge = self._request_bridge
        if bridge is not None and hasattr(bridge, "requestClose"):
            bridge.requestClose()

    def _shell_window(self):
        bridge = self._workspace_bridge
        if bridge is not None:
            shell_window = getattr(bridge, "shell_window", None)
            if shell_window is not None:
                return shell_window
        return None

    def _sync_presenter_bindings(self) -> None:
        self._presenter.bind(
            shell_window=self._shell_window(),
        )

    def _refresh_from_request(self) -> None:
        bridge = self._request_bridge
        if bridge is None:
            self._presenter.refresh()
            self.state_changed.emit()
            return
        self._presenter.sync_request(
            open_=bool(getattr(bridge, "open", False)),
            focus_addon_id=str(getattr(bridge, "focusAddonId", "") or ""),
            request_serial=int(getattr(bridge, "requestSerial", 0) or 0),
        )
        self.state_changed.emit()

    @pyqtSlot(str, str)
    def _on_install_progress(self, addon_id: str, message: str) -> None:
        if addon_id != self._installing_addon_id:
            return
        normalized = str(message or "").strip().replace("\r", "")
        if not normalized:
            return
        self._install_progress_text = normalized[-1000:]
        self.state_changed.emit()

    @pyqtSlot(str, object)
    def _on_install_finished(
        self,
        addon_id: str,
        result: ManagedRuntimeInstallResult,
    ) -> None:
        if result.success:
            self._presenter.refresh(focus_addon_id=addon_id)
            selected = self._presenter.selected_payload()
            if not bool(selected.get("available")):
                self._presenter.set_error(
                    "MARS installed, but MARSBatch verification did not succeed."
                )
            elif not self._presenter.set_addon_enabled(addon_id, True):
                self._presenter.set_error(
                    "MARS installed, but COREX could not enable the add-on."
                )
        else:
            status = getattr(result, "status", None)
            message = str(
                result.error
                or getattr(status, "error", "")
                or "Add-on installation failed."
            )
            logger.error("Add-on installation failed for %s: %s", addon_id, message)
            self._presenter.set_error(message[:1000])
        self.state_changed.emit()

    @pyqtSlot()
    def _on_install_thread_finished(self) -> None:
        self._install_thread = None
        self._install_worker = None
        self._installing_addon_id = ""
        self._install_progress_text = ""
        self.state_changed.emit()

    @pyqtSlot()
    def _on_request_state_changed(self) -> None:
        self._refresh_from_request()


def register_qml_types() -> None:
    global _QML_REGISTERED
    if _QML_REGISTERED:
        return
    qmlRegisterType(
        ShellAddOnManagerBridge,
        _QML_IMPORT_NAME,
        _QML_IMPORT_MAJOR_VERSION,
        _QML_IMPORT_MINOR_VERSION,
        _QML_TYPE_NAME,
    )
    _QML_REGISTERED = True


__all__ = ["ShellAddOnManagerBridge", "register_qml_types"]

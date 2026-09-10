"""Async managed-package installation through the Add-On Manager bridge."""

from types import SimpleNamespace
from threading import Event

from PyQt6.QtCore import QCoreApplication, QEventLoop, QTimer

from ea_node_editor.addons.catalog import registered_addon_registrations
from ea_node_editor.execution.managed_runtime import ManagedRuntimeInstallResult
from ea_node_editor.ui_qml.shell_addon_manager_bridge import ShellAddOnManagerBridge


class _Presenter:
    def __init__(self) -> None:
        self.available = False
        self.enabled = False
        self.last_error = ""

    def selected_payload(self):
        return {
            "addonId": "mars.corex",
            "available": self.available,
            "unavailable": not self.available,
            "installable": True,
            "managedRuntimePackageIds": ["mars"],
        }

    def clear_error(self):
        self.last_error = ""

    def set_error(self, message):
        self.last_error = str(message)

    def refresh(self, **_kwargs):
        self.available = True

    def set_addon_enabled(self, addon_id, enabled):
        assert addon_id == "mars.corex"
        self.enabled = bool(enabled)
        return True


def test_registered_addon_ids_are_exact() -> None:
    assert tuple(
        registration.manifest.addon_id
        for registration in registered_addon_registrations()
    ) == (
        "ea_node_editor.builtins.tabular_data",
        "mars.corex",
        "mechanical.corex",
    )


def test_install_runs_off_thread_then_auto_enables():
    app = QCoreApplication.instance() or QCoreApplication([])
    calls = []

    def prepare(package_ids, _progress_callback):
        calls.append(package_ids)
        return ManagedRuntimeInstallResult(success=True, python_executable="managed-python")

    bridge = ShellAddOnManagerBridge(managed_runtime_prepare=prepare)
    presenter = _Presenter()
    bridge._presenter = presenter
    loop = QEventLoop()
    started = False

    def changed():
        nonlocal started
        started = started or bridge.installing
        if started and not bridge.installing:
            loop.quit()

    bridge.state_changed.connect(changed)
    assert bridge.installSelectedAddon() is True
    assert bridge.installSelectedAddon() is False
    QTimer.singleShot(5000, loop.quit)
    loop.exec()

    assert app is not None
    assert started is True
    assert calls == [("mars",)]
    assert presenter.enabled is True
    assert presenter.last_error == ""


def test_install_progress_is_visible_before_worker_finishes():
    QCoreApplication.instance() or QCoreApplication([])
    worker_started = Event()
    release_progress = Event()
    release_worker = Event()
    saw_progress = False

    def prepare(_package_ids, progress_callback):
        worker_started.set()
        assert release_progress.wait(5)
        progress_callback("Downloading vtk-9.5.2...")
        assert release_worker.wait(5)
        return ManagedRuntimeInstallResult(success=True, python_executable="managed-python")

    bridge = ShellAddOnManagerBridge(managed_runtime_prepare=prepare)
    presenter = _Presenter()
    bridge._presenter = presenter
    loop = QEventLoop()

    def changed():
        nonlocal saw_progress
        if bridge.installProgressText == "Downloading vtk-9.5.2...":
            saw_progress = True
            release_worker.set()
        if saw_progress and not bridge.installing:
            loop.quit()

    bridge.state_changed.connect(changed)
    assert bridge.installSelectedAddon() is True
    assert worker_started.wait(5)
    assert bridge.installProgressText == "Preparing the COREX Python environment..."
    release_progress.set()
    QTimer.singleShot(5000, loop.quit)
    loop.exec()

    release_worker.set()
    assert saw_progress is True
    assert bridge.installProgressText == ""
    assert presenter.enabled is True


def test_install_is_rejected_during_active_workflow():
    bridge = ShellAddOnManagerBridge(
        managed_runtime_prepare=lambda _ids, _progress: ManagedRuntimeInstallResult(success=True)
    )
    presenter = _Presenter()
    bridge._presenter = presenter
    bridge._workspace_bridge = SimpleNamespace(
        shell_window=SimpleNamespace(
            run_state=SimpleNamespace(active_run_id="run-1"),
        )
    )

    assert bridge.installSelectedAddon() is False
    assert "Stop the active workflow" in presenter.last_error


def test_failed_install_keeps_addon_disabled_and_allows_retry():
    QCoreApplication.instance() or QCoreApplication([])
    attempts = 0

    def prepare(_package_ids, _progress_callback):
        nonlocal attempts
        attempts += 1
        return ManagedRuntimeInstallResult(success=False, error="wheel verification failed")

    bridge = ShellAddOnManagerBridge(managed_runtime_prepare=prepare)
    presenter = _Presenter()
    bridge._presenter = presenter
    loop = QEventLoop()
    started = False

    def changed():
        nonlocal started
        started = started or bridge.installing
        if started and not bridge.installing:
            loop.quit()

    bridge.state_changed.connect(changed)
    assert bridge.installSelectedAddon() is True
    QTimer.singleShot(5000, loop.quit)
    loop.exec()

    assert attempts == 1
    assert presenter.enabled is False
    assert presenter.last_error == "wheel verification failed"
    assert bridge.installSelectedAddon() is True
    while bridge.installing:
        QCoreApplication.processEvents()
    assert attempts == 2

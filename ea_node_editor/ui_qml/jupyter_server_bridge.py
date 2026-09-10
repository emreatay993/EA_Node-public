# Purpose: QML<->Python bridge for the Jupyter Notebook node — resolves a node's
#          .ipynb artifact ref, starts the project-scoped Jupyter server OFF the
#          UI thread, and hands the tokened single-document URL back to the
#          surface via signals. The URL/token are never persisted.
# Map: feature_routes/qml_bridge_wiring
# Tests: tests/test_jupyter_server_bridge.py
# Landmarks: JupyterServerBridge, _JupyterStartRunnable
from __future__ import annotations

import copy
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

from PyQt6.QtCore import (
    QObject,
    QRunnable,
    Qt,
    QThreadPool,
    QUrl,
    pyqtSignal,
    pyqtSlot,
)

from ea_node_editor.jupyter_host.notebook_files import relative_to_server_root
from ea_node_editor.jupyter_host.server_manager import JupyterServerRegistry
from ea_node_editor.persistence.artifact_resolution import ProjectArtifactResolver

if TYPE_CHECKING:
    from ea_node_editor.ui.shell.window import ShellWindow


class _JupyterStartSignals(QObject):
    # node_id, url, error
    finished = pyqtSignal(str, str, str)


class _JupyterStartRunnable(QRunnable):
    """Starts (or reuses) the project server off the UI thread and builds the URL."""

    def __init__(
        self,
        *,
        signals: _JupyterStartSignals,
        node_id: str,
        server_root: str,
        relative_path: str,
        frontend: str,
        python_executable: str,
    ) -> None:
        super().__init__()
        self._signals = signals
        self._node_id = node_id
        self._server_root = server_root
        self._relative_path = relative_path
        self._frontend = frontend
        self._python_executable = python_executable

    def run(self) -> None:
        try:
            manager = JupyterServerRegistry.instance().manager_for(
                self._server_root,
                python_executable=self._python_executable,
            )
            handle = manager.ensure_running()
            url = handle.notebook_url(relative_path=self._relative_path, frontend=self._frontend)
            self._signals.finished.emit(self._node_id, url, "")
        except Exception as exc:  # noqa: BLE001 - report to the surface, never crash the pool
            self._signals.finished.emit(self._node_id, "", str(exc))


class JupyterServerBridge(QObject):
    """Bridges a Jupyter notebook surface to the embedded server lifecycle."""

    serverReady = pyqtSignal(str, str)         # node_id, url
    serverFailed = pyqtSignal(str, str)        # node_id, reason
    notebookRefAssigned = pyqtSignal(str, str)  # node_id, staged_ref (surface commits it)

    def __init__(
        self,
        parent: QObject | None = None,
        *,
        shell_window: "ShellWindow | None" = None,
        python_executable: str = "",
        create_blank_notebook_artifact: Callable[..., str] | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("jupyterServerBridge")
        self._shell_window = shell_window
        self._python_executable = str(python_executable or "")
        self._create_blank_notebook_artifact = create_blank_notebook_artifact
        self._thread_pool: QThreadPool | None = None
        self._max_threads = 2
        self._shutdown = False
        self._signals = _JupyterStartSignals(self)
        self._signals.finished.connect(
            self._on_start_finished,
            Qt.ConnectionType.QueuedConnection,
        )

    def _ensure_thread_pool(self) -> QThreadPool | None:
        if self._shutdown:
            return None
        pool = self._thread_pool
        if pool is None:
            pool = QThreadPool(self)
            pool.setMaxThreadCount(self._max_threads)
            self._thread_pool = pool
        return pool

    @pyqtSlot(str, str, str)
    def ensureServer(self, node_id: str, notebook_ref: str, frontend: str) -> None:
        node = str(node_id or "")
        server_root = self._server_root()
        if server_root is None:
            self.serverFailed.emit(node, "Open or save a project to run notebooks.")
            return
        abs_path = self._resolve_notebook_path(notebook_ref)
        if abs_path is None:
            self.serverFailed.emit(
                node,
                "No notebook selected. Choose or create a .ipynb in the inspector.",
            )
            return
        relative_path = relative_to_server_root(abs_path, server_root)
        if not relative_path:
            self.serverFailed.emit(
                node,
                "The notebook must live inside the project to run. Copy it into the project first.",
            )
            return
        pool = self._ensure_thread_pool()
        if pool is None:
            return
        runnable = _JupyterStartRunnable(
            signals=self._signals,
            node_id=node,
            server_root=str(server_root),
            relative_path=relative_path,
            frontend=str(frontend or "notebook"),
            python_executable=self._python_executable,
        )
        pool.start(runnable)

    @pyqtSlot(str, str)
    def createBlankNotebook(self, node_id: str, kernel_name: str) -> None:
        node = str(node_id or "")
        creator = self._create_blank_notebook_artifact
        if not callable(creator):
            self.serverFailed.emit(node, "Open or save a project before creating a notebook.")
            return
        try:
            ref = str(creator(node, kernel_name=str(kernel_name or "")) or "")
        except Exception as exc:  # noqa: BLE001 - surface the failure to the UI
            self.serverFailed.emit(node, "Failed to create a notebook: " + str(exc))
            return
        if not ref:
            self.serverFailed.emit(node, "Failed to create a notebook.")
            return
        self.notebookRefAssigned.emit(node, ref)

    def _on_start_finished(self, node_id: str, url: str, error: str) -> None:
        if self._shutdown:
            return
        if error or not url:
            self.serverFailed.emit(node_id, error or "Failed to start the Jupyter server.")
            return
        self.serverReady.emit(node_id, url)

    @pyqtSlot()
    def shutdown(self) -> None:
        if self._shutdown:
            return
        self._shutdown = True
        pool = self._thread_pool
        if pool is None:
            return
        pool.clear()
        pool.waitForDone(2000)
        try:
            JupyterServerRegistry.instance().shutdown_all()
        except Exception:  # noqa: BLE001 - teardown must never raise
            pass

    # --- project context (UI thread only) -----------------------------------

    def _server_root(self) -> Path | None:
        controller = getattr(self._shell_window, "project_session_controller", None)
        ensure = getattr(controller, "ensure_project_staging_root", None)
        if not callable(ensure):
            return None
        try:
            return Path(ensure())
        except Exception:  # noqa: BLE001
            return None

    def _resolve_notebook_path(self, notebook_ref: str) -> Path | None:
        ref = str(notebook_ref or "").strip()
        if not ref:
            return None
        project_path, project_metadata = self._project_context()
        try:
            resolved = ProjectArtifactResolver(
                project_path=project_path,
                project_metadata=project_metadata,
            ).resolve_to_path(ref)
        except Exception:  # noqa: BLE001
            resolved = None
        if resolved is not None:
            return Path(resolved)
        # Fall back to a plain local path / file URL (unmanaged reference).
        if ref.lower().startswith("file:"):
            local = QUrl(ref).toLocalFile()
            return Path(local) if local else None
        candidate = Path(ref)
        return candidate if candidate.is_absolute() else None

    def _project_context(self) -> tuple[str | None, dict[str, Any] | None]:
        shell_window = self._shell_window
        project_path = str(getattr(shell_window, "project_path", "") or "").strip() or None
        model = getattr(shell_window, "model", None)
        project = getattr(model, "project", None)
        metadata = getattr(project, "metadata", None)
        project_metadata = copy.deepcopy(dict(metadata)) if isinstance(metadata, dict) else None
        return project_path, project_metadata


__all__ = [
    "JupyterServerBridge",
]

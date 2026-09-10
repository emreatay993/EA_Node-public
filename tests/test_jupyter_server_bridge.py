from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from ea_node_editor.jupyter_host import is_jupyter_available
from ea_node_editor.jupyter_host.notebook_files import create_blank_notebook
from ea_node_editor.ui_qml import jupyter_server_bridge as bridge_module
from ea_node_editor.ui_qml.jupyter_server_bridge import JupyterServerBridge


class _FakeController:
    def __init__(self, staging_root: Path) -> None:
        self._staging_root = staging_root

    def ensure_project_staging_root(self) -> Path:
        return self._staging_root


class _FakeProject:
    def __init__(self) -> None:
        self.metadata: dict = {}


class _FakeModel:
    def __init__(self) -> None:
        self.project = _FakeProject()


class _FakeShellWindow:
    def __init__(self, staging_root: Path) -> None:
        self.project_session_controller = _FakeController(staging_root)
        self.project_path = ""
        self.model = _FakeModel()


def _capture_failures(bridge: JupyterServerBridge) -> list[tuple[str, str]]:
    captured: list[tuple[str, str]] = []
    bridge.serverFailed.connect(lambda node, reason: captured.append((node, reason)))
    return captured


def test_ensure_server_without_project_reports_failure(qapp) -> None:  # noqa: ANN001
    bridge = JupyterServerBridge(shell_window=None)
    failures = _capture_failures(bridge)

    bridge.ensureServer("node-1", "saved://x", "notebook")

    assert failures and failures[-1][0] == "node-1"
    assert "project" in failures[-1][1].lower()


def test_ensure_server_with_empty_ref_reports_no_notebook(qapp, tmp_path) -> None:  # noqa: ANN001
    bridge = JupyterServerBridge(shell_window=_FakeShellWindow(tmp_path))
    failures = _capture_failures(bridge)

    bridge.ensureServer("node-2", "", "notebook")

    assert failures and "notebook" in failures[-1][1].lower()


def test_ensure_server_for_notebook_outside_project_is_rejected(qapp, tmp_path) -> None:  # noqa: ANN001
    staging = tmp_path / "staging"
    staging.mkdir(parents=True)
    outside = tmp_path / "outside" / "x.ipynb"
    outside.parent.mkdir(parents=True)
    outside.write_text("{}", encoding="utf-8")
    bridge = JupyterServerBridge(shell_window=_FakeShellWindow(staging))
    failures = _capture_failures(bridge)

    bridge.ensureServer("node-3", str(outside), "notebook")

    assert failures and "inside the project" in failures[-1][1].lower()


def test_thread_pool_is_lazy_reused_and_preserves_max_threads(qapp, tmp_path) -> None:  # noqa: ANN001
    staging = tmp_path / "staging"
    notebook = staging / "jupyter" / "notebooks" / "analysis.ipynb"
    create_blank_notebook(notebook)
    pool = Mock()

    with (
        patch.object(bridge_module, "QThreadPool", return_value=pool) as pool_factory,
        patch.object(bridge_module.JupyterServerRegistry, "instance") as registry_instance,
    ):
        bridge = JupyterServerBridge(shell_window=_FakeShellWindow(staging))
        assert bridge._thread_pool is None  # noqa: SLF001

        bridge.ensureServer("invalid", "", "notebook")
        pool_factory.assert_not_called()

        bridge.ensureServer("node-1", str(notebook), "notebook")
        bridge.ensureServer("node-2", str(notebook), "lab")

        pool_factory.assert_called_once_with(bridge)
        pool.setMaxThreadCount.assert_called_once_with(2)
        assert pool.start.call_count == 2

        bridge.shutdown()
        pool.clear.assert_called_once_with()
        pool.waitForDone.assert_called_once_with(2000)
        registry_instance.assert_called_once_with()


def test_shutdown_before_thread_pool_initialization_allocates_nothing(qapp) -> None:  # noqa: ANN001
    with (
        patch.object(bridge_module, "QThreadPool") as pool_factory,
        patch.object(bridge_module.JupyterServerRegistry, "instance") as registry_instance,
    ):
        bridge = JupyterServerBridge(shell_window=None)
        bridge.shutdown()
        bridge.shutdown()

    pool_factory.assert_not_called()
    registry_instance.assert_not_called()


@pytest.mark.skipif(not is_jupyter_available(), reason="embedded Jupyter stack not installed")
def test_ensure_server_resolves_starts_and_emits_tokened_url(qapp, tmp_path) -> None:  # noqa: ANN001
    staging = tmp_path / "staging"
    notebook = staging / "jupyter" / "notebooks" / "analysis.ipynb"
    create_blank_notebook(notebook)
    bridge = JupyterServerBridge(shell_window=_FakeShellWindow(staging))
    ready: list[tuple[str, str]] = []
    failed: list[tuple[str, str]] = []
    bridge.serverReady.connect(lambda node, url: ready.append((node, url)))
    bridge.serverFailed.connect(lambda node, reason: failed.append((node, reason)))

    try:
        bridge.ensureServer("node-live", str(notebook), "notebook")
        deadline = time.monotonic() + 30.0
        while time.monotonic() < deadline and not ready and not failed:
            qapp.processEvents()
            time.sleep(0.05)

        assert not failed, failed
        assert ready, "serverReady was not emitted within the deadline"
        node_id, url = ready[-1]
        assert node_id == "node-live"
        assert "/notebooks/jupyter/notebooks/analysis.ipynb" in url
        assert "token=" in url
    finally:
        bridge.shutdown()

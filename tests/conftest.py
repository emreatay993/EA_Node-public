"""Shared pytest fixtures for the COREX Node Editor test suite."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

# Must be set before any Qt import.
os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "Basic")

import pytest  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

from ea_node_editor.app import prepare_qt_application_attributes  # noqa: E402
from ea_node_editor.ui.theme.styles import build_theme_stylesheet  # noqa: E402
from scripts.verification_manifest import (  # noqa: E402
    pytest_marker_path_sets as _manifest_marker_path_sets,
)


# ---------------------------------------------------------------------------
# Centralized pytest selection markers
# ---------------------------------------------------------------------------

_MARKER_TEST_PATHS_BY_NAME = _manifest_marker_path_sets()
_GUI_TEST_PATHS = _MARKER_TEST_PATHS_BY_NAME["gui"]
_SLOW_TEST_PATHS = _MARKER_TEST_PATHS_BY_NAME["slow"]


def _nodeid_test_path(nodeid: str) -> str:
    return nodeid.split("::", 1)[0].replace("\\", "/")


def _add_marker_if_missing(item: pytest.Item, marker_name: str) -> None:
    if item.get_closest_marker(marker_name) is None:
        item.add_marker(getattr(pytest.mark, marker_name))


@pytest.hookimpl(tryfirst=True)
def pytest_ignore_collect(collection_path, path=None, config=None):  # type: ignore[no-untyped-def]
    _ = path, config
    if Path(str(collection_path)).name == "venv":
        return True
    return None


@pytest.hookimpl(tryfirst=True)
def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    _ = config
    for item in items:
        test_path = _nodeid_test_path(item.nodeid)
        for marker_name, marker_paths in _MARKER_TEST_PATHS_BY_NAME.items():
            if test_path in marker_paths:
                _add_marker_if_missing(item, marker_name)


# ---------------------------------------------------------------------------
# Session-scoped QApplication
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session", autouse=True)
def qapp():
    """Create (or reuse) a single QApplication for the entire test session."""
    prepare_qt_application_attributes()
    app = QApplication.instance() or QApplication([])
    app.setStyleSheet(build_theme_stylesheet())
    yield app


# ---------------------------------------------------------------------------
# Shared execution runtime cache isolation
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _isolated_runtime_preparation_cache():
    """Prevent one test's prepared registry from leaking into the next test."""
    from ea_node_editor.execution.worker_runtime import DEFAULT_RUNTIME_PREPARATION_CACHE

    DEFAULT_RUNTIME_PREPARATION_CACHE.clear()
    yield
    DEFAULT_RUNTIME_PREPARATION_CACHE.clear()


# ---------------------------------------------------------------------------
# Shared tabular loader service isolation
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _isolated_shared_tabular_service(tmp_path_factory: pytest.TempPathFactory):
    """Point the process-wide tabular loader service at a per-test cache dir.

    The shared service otherwise writes managed parquet caches into the real
    user data directory; tests must never touch it.
    """
    from ea_node_editor.addons.tabular_data import loader_cache_service as _lcs
    from ea_node_editor.ui_qml import plot_auto_preview_service as _paps

    _lcs.reset_shared_tabular_loader_cache_service()
    _paps.shared_plot_render_request_cache().clear()
    cache_dir = tmp_path_factory.getbasetemp() / f"tabular_cache_{uuid4().hex}"
    with patch.object(_lcs, "tabular_data_cache_dir", return_value=cache_dir):
        yield
    _lcs.reset_shared_tabular_loader_cache_service()
    _paps.shared_plot_render_request_cache().clear()


# ---------------------------------------------------------------------------
# Shell window test environment
# ---------------------------------------------------------------------------

class ShellTestEnvironment:
    """Reusable helper that manages the temp dir + four path patches
    required by every test that creates a ``ShellWindow``.

    Usage in unittest-style tests::

        class MyTests(unittest.TestCase):
            def setUp(self):
                self._env = ShellTestEnvironment()
                self._env.start()
                ...

            def tearDown(self):
                self._env.stop()
    """

    _PATCH_TARGETS = (
        "ea_node_editor.ui.shell.window.recent_session_path",
        "ea_node_editor.ui.shell.window.autosave_project_path",
        "ea_node_editor.ui.shell.controllers.app_preferences_controller.app_preferences_path",
        "ea_node_editor.custom_workflows.global_store.global_custom_workflows_path",
    )
    _FILE_NAMES = (
        "last_session.json",
        "autosave.cxproj",
        "app_preferences.json",
        "custom_workflows_global.json",
    )

    def __init__(self) -> None:
        self._temp_dir: tempfile.TemporaryDirectory | None = None
        self._patches: list[patch] = []

    def start(self) -> Path:
        """Create the temp directory, start all patches, return the temp path."""
        self._temp_dir = tempfile.TemporaryDirectory()
        temp = Path(self._temp_dir.name)
        self._patches = [
            patch(target, return_value=temp / fname)
            for target, fname in zip(self._PATCH_TARGETS, self._FILE_NAMES)
        ]
        for p in self._patches:
            p.start()
        return temp

    def stop(self) -> None:
        """Stop all patches and clean up the temp directory."""
        for p in self._patches:
            p.stop()
        self._patches.clear()
        if self._temp_dir is not None:
            self._temp_dir.cleanup()
            self._temp_dir = None

    @property
    def temp_path(self) -> Path:
        assert self._temp_dir is not None
        return Path(self._temp_dir.name)

    @property
    def session_path(self) -> Path:
        return self.temp_path / "last_session.json"

    @property
    def autosave_path(self) -> Path:
        return self.temp_path / "autosave.cxproj"

    @property
    def app_preferences_path(self) -> Path:
        return self.temp_path / "app_preferences.json"

    @property
    def global_custom_workflows_path(self) -> Path:
        return self.temp_path / "custom_workflows_global.json"

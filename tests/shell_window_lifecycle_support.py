# Purpose: Shared real-window fixtures and scenarios for shell-isolated lifecycle tests.
# Map: testing/shell_isolation_tests
# Tests: tests/test_shell_window_lifecycle_isolated.py
# Landmarks: _shell_lifecycle_context, _create_window, mounted fullscreen scenarios
from __future__ import annotations

import gc
import logging
import tempfile
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

from PyQt6.QtCore import (
    QEvent,
    QMarginsF,
    QMetaObject,
    QObject,
    QRectF,
    Qt,
    QUrl,
)
from PyQt6.QtGui import QImage, QPageLayout, QPageSize, QPainter, QPdfWriter
from PyQt6.QtTest import QTest
from PyQt6.QtQuickWidgets import QQuickWidget
from PyQt6.QtWidgets import QApplication, QWidget
import pytest

from ea_node_editor.execution.prepared_execution import InvalidationResult
from ea_node_editor.graph.model import GraphModel
from ea_node_editor.nodes.builtins.media_panel import MEDIA_PANEL_TYPE_ID
from ea_node_editor.ui.shell import composition as shell_composition
from ea_node_editor.ui.shell.controllers.graph_action_controller import (
    GraphActionController,
)
from ea_node_editor.ui.shell.composition import create_shell_window
from ea_node_editor.ui.shell.window import ShellWindow
from ea_node_editor.ui_qml import qml_host_factory, qtquick_backend
from ea_node_editor.ui_qml.qml_host_factory import (
    QML_HOST_ENV,
    QML_HOST_QQUICKVIEW_CONTAINER,
    QML_HOST_QQUICKWIDGET,
    select_qml_host_kind_from_environment,
)
from ea_node_editor.ui_qml.qtquick_backend import (
    BACKEND_OVERRIDE_ENV,
    FORCE_SOFTWARE_ENV,
    normalize_qsg_rhi_backend_override,
    select_qtquick_backend_from_environment,
)
from ea_node_editor.ui.shell.workspace_flow import ShellWorkspaceManagerAdapter
from ea_node_editor.workspace.manager import WorkspaceManager
from tests.conftest import ShellTestEnvironment
from tests.qt_wait import wait_for_condition_or_raise


class _ShellTestExecutionClient:
    def __init__(self, _registry: object | None = None) -> None:
        self._callbacks: list[object] = []
        self._solution_revision = 0

    def subscribe(self, callback) -> None:  # noqa: ANN001
        self._callbacks.append(callback)

    def start_run(  # noqa: ANN001
        self,
        project_path: str,
        workspace_id: str,
        trigger=None,
        *,
        execution_backend=None,
        target_node_ids=(),
        trigger_publications=None,
        trigger_captures=None,
        clicked_trigger_node_id: str = "",
    ) -> str:
        return ""

    def invalidate_solution(
        self,
        project_id: str,
        workspace_id: str,
        _runtime_snapshot,
        changed_root_node_ids,
        reason_code: str,
    ) -> InvalidationResult:
        changed_node_ids = tuple(changed_root_node_ids)
        self._solution_revision += 1
        return InvalidationResult(
            project_id=project_id,
            workspace_id=workspace_id,
            solution_revision=self._solution_revision,
            changed_root_node_ids=changed_node_ids,
            expired_node_ids=changed_node_ids,
            removed_node_ids=(),
            reason_code=reason_code,
        )

    def shutdown(self) -> None:
        self._callbacks.clear()


def _flush_shell_qt_events(app: QApplication) -> None:
    app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    app.processEvents()
    app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    app.processEvents()


@contextmanager
def _shell_lifecycle_context() -> Iterator[QApplication]:
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    env = ShellTestEnvironment()
    env.start()
    execution_client_patch = patch(
        "ea_node_editor.ui.shell.composition.controllers._create_shell_execution_client",
        _ShellTestExecutionClient,
    )
    execution_client_patch.start()
    try:
        yield app
    finally:
        _flush_shell_qt_events(app)
        execution_client_patch.stop()
        env.stop()
        gc.collect()


def _build_window_via_constructor() -> ShellWindow:
    return ShellWindow()


def _build_window_via_factory() -> ShellWindow:
    return create_shell_window()


def _create_window(
    app: QApplication, factory: Callable[[], ShellWindow]
) -> ShellWindow:
    window = factory()
    window.resize(1200, 800)
    window.show()
    _flush_shell_qt_events(app)
    return window


def _delete_window(window: ShellWindow, app: QApplication) -> None:
    window.deleteLater()
    _flush_shell_qt_events(app)
    gc.collect()


def _shell_runtime(window: ShellWindow) -> shell_composition.ShellRuntimeDependencies:
    return window.shell_services.runtime


def _find_child(root: QObject, object_name: str) -> QObject:
    child = root.findChild(QObject, object_name)
    if child is None:
        raise AssertionError(f"Expected QML object {object_name!r}")
    return child


def _qurl_text(value: object) -> str:
    to_string = getattr(value, "toString", None)
    if callable(to_string):
        return str(to_string())
    return str(value)


def _write_test_image(path: Path, color: int = 0xFF4C7BC0) -> None:
    image = QImage(48, 30, QImage.Format.Format_ARGB32)
    image.fill(color)
    assert image.save(str(path))


def _add_browse_media_panel(window: ShellWindow) -> str:
    return window.scene.create_node_from_type(
        type_id=MEDIA_PANEL_TYPE_ID,
        x=120.0,
        y=80.0,
        parent_node_id=None,
        select_node=False,
        exposed_port_overrides={"source": False},
    )


def _write_test_pdf(path: Path, *, page_count: int = 1) -> None:
    writer = QPdfWriter(str(path))
    writer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
    writer.setPageMargins(QMarginsF(12, 12, 12, 12), QPageLayout.Unit.Millimeter)
    painter = QPainter(writer)
    for page_index in range(page_count):
        if page_index > 0:
            writer.newPage()
        painter.drawText(
            QRectF(80.0, 120.0, 420.0, 120.0), f"PDF page {page_index + 1}"
        )
    painter.end()
    del painter
    del writer
    gc.collect()


def test_shell_composition_uses_explicit_feature_owned_bundles() -> None:
    composition_fields = shell_composition.ShellWindowComposition.__dataclass_fields__
    service_fields = shell_composition.ShellServices.__dataclass_fields__

    assert not hasattr(shell_composition, "_ShellWindowAdapterBase")
    assert not hasattr(GraphActionController, "bind_sources")
    assert tuple(composition_fields) == ("services",)
    assert "preferences_theme_status" in service_fields
    assert "library_workspace" in service_fields
    assert "graph_actions" in service_fields
    assert "qml_context" in service_fields
    assert hasattr(
        shell_composition.ShellWindowDependencyFactory,
        "create_preferences_theme_status_dependencies",
    )
    assert hasattr(
        shell_composition.ShellWindowDependencyFactory,
        "create_library_workspace_dependencies",
    )
    assert hasattr(
        shell_composition.ShellWindowDependencyFactory,
        "create_graph_action_dependencies",
    )
    assert hasattr(
        shell_composition.ShellWindowDependencyFactory,
        "create_viewer_service_dependencies",
    )
    assert hasattr(
        shell_composition.ShellWindowDependencyFactory,
        "create_qml_context_dependencies",
    )
    assert hasattr(
        shell_composition.ShellWindowDependencyFactory, "create_services_bundle"
    )


def test_empty_shell_configures_tabular_policy_without_allocating_shared_service() -> (
    None
):
    from ea_node_editor.addons.tabular_data import loader_cache_service

    loader_cache_service.reset_shared_tabular_loader_cache_service()
    cache_dir = loader_cache_service.tabular_data_cache_dir()
    assert not cache_dir.exists()
    assert loader_cache_service._shared_service is None  # noqa: SLF001

    with _shell_lifecycle_context() as app:
        window = _create_window(app, _build_window_via_constructor)

        assert loader_cache_service._shared_service is None  # noqa: SLF001
        service = loader_cache_service.shared_tabular_loader_cache_service()
        assert service.ui_thread_conversion_allowed is False
        assert not cache_dir.exists()

        window.close()
        _flush_shell_qt_events(app)
        _delete_window(window, app)


def test_shared_shell_reset_reapplies_tabular_policy_after_service_reset() -> None:
    from ea_node_editor.addons.tabular_data import loader_cache_service
    from tests.main_window_shell.base import SharedMainWindowShellTestBase

    class _SharedShellPolicyProbe(SharedMainWindowShellTestBase):
        def runTest(self) -> None:
            return None

    _SharedShellPolicyProbe.setUpClass()
    case = _SharedShellPolicyProbe()
    case_setup = False
    try:
        loader_cache_service.reset_shared_tabular_loader_cache_service()
        case.setUp()
        case_setup = True

        service = loader_cache_service.shared_tabular_loader_cache_service()

        assert service.ui_thread_conversion_allowed is False
    finally:
        if case_setup:
            case.tearDown()
        _SharedShellPolicyProbe.tearDownClass()


def test_shell_workspace_manager_adapter_exposes_only_workspace_and_view_surface() -> (
    None
):
    model = GraphModel()
    adapter = ShellWorkspaceManagerAdapter(WorkspaceManager(model), model)

    workspace_id = adapter.active_workspace_id()
    view_id = adapter.create_view(workspace_id, name="Secondary")
    adapter.set_active_view(workspace_id, view_id)

    assert model.project.workspaces[workspace_id].active_view_id == view_id
    with pytest.raises(AttributeError):
        getattr(adapter, "_project_metadata")


def test_qtquick_backend_override_selection_preserves_offscreen_software(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.delenv(FORCE_SOFTWARE_ENV, raising=False)
    monkeypatch.setenv(BACKEND_OVERRIDE_ENV, "d3d11")

    selection = select_qtquick_backend_from_environment()

    assert selection.selected_backend == "software"
    assert selection.reason == "software_qpa_platform"
    assert selection.forced_software is True
    assert selection.normalized_override == "d3d11"


def test_windows_desktop_keeps_qquickwidget_default_and_d3d11_backend(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(qtquick_backend.sys, "platform", "win32")
    monkeypatch.setenv("QT_QPA_PLATFORM", "windows")
    monkeypatch.delenv(QML_HOST_ENV, raising=False)
    monkeypatch.delenv(BACKEND_OVERRIDE_ENV, raising=False)
    monkeypatch.delenv(FORCE_SOFTWARE_ENV, raising=False)

    assert select_qml_host_kind_from_environment() == QML_HOST_QQUICKWIDGET
    qml_snapshot = qml_host_factory.qml_host_environment_snapshot()
    assert qml_snapshot["qml_host_kind_selected"] == QML_HOST_QQUICKWIDGET
    assert qml_snapshot["qml_host_default_kind"] == QML_HOST_QQUICKWIDGET
    assert qml_snapshot["qml_host_selection_reason"] == "compatibility_default"

    selection = select_qtquick_backend_from_environment()
    assert selection.selected_backend == "d3d11"
    assert selection.reason == "windows_desktop_default"
    assert selection.forced_software is False


def test_qtquick_backend_override_accepts_auto_and_rejects_unknown(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setattr(qtquick_backend.sys, "platform", "win32")
    monkeypatch.delenv("QT_QPA_PLATFORM", raising=False)
    monkeypatch.delenv(FORCE_SOFTWARE_ENV, raising=False)
    monkeypatch.setenv(BACKEND_OVERRIDE_ENV, "AUTO")

    assert normalize_qsg_rhi_backend_override("D3D12") == "d3d12"
    assert normalize_qsg_rhi_backend_override("bogus") == ""
    auto_selection = select_qtquick_backend_from_environment()
    assert auto_selection.selected_backend == ""
    assert auto_selection.reason == "qt_default"
    assert auto_selection.normalized_override == "auto"

    caplog.set_level(logging.WARNING, logger="ea_node_editor.ui_qml.qtquick_backend")
    monkeypatch.setenv(BACKEND_OVERRIDE_ENV, "not-a-backend")
    invalid_selection = select_qtquick_backend_from_environment()

    assert invalid_selection.selected_backend == ""
    assert invalid_selection.reason == "qt_default"
    assert invalid_selection.invalid_override is True
    assert "Unsupported EA_NODE_EDITOR_QSG_RHI_BACKEND" in caplog.text


def test_shell_window_close_allows_repeated_in_process_cycles() -> None:
    with _shell_lifecycle_context() as app:
        for factory in (_build_window_via_constructor, _build_window_via_factory):
            for _cycle in range(3):
                window = _create_window(app, factory)
                quick_widget = getattr(window, "quick_widget", None)

                assert isinstance(quick_widget, QQuickWidget)
                assert quick_widget.rootObject() is not None
                assert not quick_widget.source().isEmpty()

                window.close()
                _flush_shell_qt_events(app)

                assert quick_widget.source() == QUrl()
                assert (
                    _shell_runtime(window).viewer_host_service.overlay_manager is None
                )
                assert (
                    _shell_runtime(window).viewer_host_service.active_overlay_count == 0
                )

                _delete_window(window, app)


def test_shell_window_exposes_qtquick_backend_debug_payload() -> None:
    with _shell_lifecycle_context() as app:
        window = _create_window(app, _build_window_via_constructor)

        payload = window.qtquick_backend_debug_payload()

        assert payload["qml_host_kind"] == QML_HOST_QQUICKWIDGET
        assert "qml_host_env" in payload
        assert payload["qml_host_kind_selected"] == QML_HOST_QQUICKWIDGET
        assert "graphics_api" in payload
        assert "graphics_api_label" in payload
        assert "qsg_rhi_backend" in payload
        assert "qsg_rhi_backend_override" in payload
        assert "qtquick_backend_selection_reason" in payload
        assert "qtquick_backend_forced_software" in payload
        assert "qsg_info_capture_enabled" in payload
        assert "software_fallback_active" in payload
        assert "software_fallback_reason" in payload

        window.close()
        _flush_shell_qt_events(app)
        _delete_window(window, app)


def test_shell_window_can_use_opt_in_qquickview_container_host(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(QML_HOST_ENV, QML_HOST_QQUICKVIEW_CONTAINER)
    monkeypatch.setenv(BACKEND_OVERRIDE_ENV, "d3d11")
    with _shell_lifecycle_context() as app:
        window = _create_window(app, _build_window_via_constructor)
        qml_host = getattr(window, "qml_host", None)

        assert qml_host is not None
        assert qml_host.host_kind == QML_HOST_QQUICKVIEW_CONTAINER
        assert window.centralWidget() is qml_host.container_widget
        assert qml_host.root_object() is not None
        assert window.quick_widget.rootObject() is qml_host.root_object()
        assert window.quick_widget.quickWindow() is qml_host.quick_window()
        assert not qml_host.source().isEmpty()
        payload = window.qtquick_backend_debug_payload()
        assert payload["qml_host_kind"] == QML_HOST_QQUICKVIEW_CONTAINER
        assert payload["qml_host_env"] == QML_HOST_QQUICKVIEW_CONTAINER
        assert payload["qml_host_kind_selected"] == QML_HOST_QQUICKVIEW_CONTAINER
        assert payload["qsg_rhi_backend_override"] == "d3d11"
        assert (
            _shell_runtime(window).viewer_host_service.overlay_manager
            is window.embedded_viewer_overlay_manager
        )
        assert (
            window.embedded_viewer_overlay_manager.overlay_parent_widget
            is qml_host.container_widget
        )

        window.close()
        _flush_shell_qt_events(app)

        assert qml_host.source() == QUrl()
        assert _shell_runtime(window).viewer_host_service.overlay_manager is None
        assert _shell_runtime(window).viewer_host_service.active_overlay_count == 0

        _delete_window(window, app)


def test_create_shell_window_factory_tracks_application_state_signal_for_teardown() -> (
    None
):
    with _shell_lifecycle_context() as app:
        window = _create_window(app, _build_window_via_factory)

        assert window._application_state_signal_connected is True

        window.close()
        _flush_shell_qt_events(app)

        assert window._application_state_signal_connected is False
        _delete_window(window, app)


def test_close_skips_deferred_autosave_recovery_after_teardown_starts() -> None:
    with _shell_lifecycle_context() as app:
        window = ShellWindow()
        window.resize(1200, 800)

        with patch.object(
            window, "_process_deferred_autosave_recovery"
        ) as recovery_mock:
            window._autosave_recovery_deferred = True
            window.show()
            window.close()
            _flush_shell_qt_events(app)

        recovery_mock.assert_not_called()
        _delete_window(window, app)


def test_close_releases_viewer_host_service_overlay_manager() -> None:
    with _shell_lifecycle_context() as app:
        window = _create_window(app, _build_window_via_constructor)
        host_service = _shell_runtime(window).viewer_host_service

        assert host_service.overlay_manager is window.embedded_viewer_overlay_manager

        window.close()
        _flush_shell_qt_events(app)

        assert host_service.overlay_manager is None
        assert host_service.active_overlay_count == 0
        _delete_window(window, app)


def test_window_deactivate_coalesces_duplicate_events_and_clears_unowned_focus() -> None:
    with _shell_lifecycle_context() as app:
        window = _create_window(app, _build_window_via_constructor)
        host_service = _shell_runtime(window).viewer_host_service
        bridge = _shell_runtime(window).viewer_session_bridge
        unowned = QWidget()

        with (
            patch.object(bridge, "clear_viewer_focus", wraps=bridge.clear_viewer_focus) as clear_focus,
            patch.object(host_service, "owns_detached_viewer_window", return_value=False),
            patch.object(
                QApplication,
                "applicationState",
                return_value=Qt.ApplicationState.ApplicationActive,
            ),
            patch.object(QApplication, "activeWindow", return_value=unowned),
        ):
            window._viewer_window_active = True
            window._queue_window_deactivate_decision()
            window._queue_window_deactivate_decision()
            assert window._viewer_deactivate_decision_queued is True
            _flush_shell_qt_events(app)
            clear_focus.assert_called_once_with()
            assert window._viewer_window_active is False
            assert window._viewer_deactivate_decision_queued is False

        unowned.deleteLater()
        window.close()
        _flush_shell_qt_events(app)
        _delete_window(window, app)


def test_application_inactive_clears_immediately_and_cancels_queued_deactivation() -> None:
    with _shell_lifecycle_context() as app:
        window = _create_window(app, _build_window_via_constructor)
        bridge = _shell_runtime(window).viewer_session_bridge

        with patch.object(
            bridge,
            "clear_viewer_focus",
            wraps=bridge.clear_viewer_focus,
        ) as clear_focus:
            window._viewer_window_active = True
            window._queue_window_deactivate_decision()
            assert window._viewer_deactivate_decision_queued is True

            window._handle_application_state_changed(
                Qt.ApplicationState.ApplicationInactive
            )

            clear_focus.assert_called_once_with()
            assert window._viewer_window_active is False
            assert window._viewer_deactivate_decision_queued is False
            _flush_shell_qt_events(app)
            clear_focus.assert_called_once_with()

        window.close()
        _flush_shell_qt_events(app)
        _delete_window(window, app)


def test_content_fullscreen_bridge_closes_during_project_reset_lifecycle() -> None:
    with _shell_lifecycle_context() as app:
        window = _create_window(app, _build_window_via_constructor)
        with tempfile.TemporaryDirectory() as temp_dir:
            image_path = Path(temp_dir) / "content-fullscreen-lifecycle.png"
            image = QImage(24, 18, QImage.Format.Format_ARGB32)
            image.fill(0xFF4C7BC0)
            assert image.save(str(image_path))

            node_id = _add_browse_media_panel(window)
            window.scene.set_node_property(node_id, "source", str(image_path))
            _flush_shell_qt_events(app)

            bridge = _shell_runtime(window).content_fullscreen_bridge
            assert bridge.request_open_node(node_id)
            assert bridge.open

            for workspace in window.model.project.workspaces.values():
                workspace.dirty = False
            window._new_project()
            _flush_shell_qt_events(app)

            assert not bridge.open
            assert bridge.node_id == ""
            assert bridge.media_payload == {}

        window.close()
        _flush_shell_qt_events(app)
        _delete_window(window, app)


def test_content_fullscreen_overlay_renders_image_media_and_keeps_node_state_read_only() -> (
    None
):
    with _shell_lifecycle_context() as app:
        window = _create_window(app, _build_window_via_constructor)
        with tempfile.TemporaryDirectory() as temp_dir:
            image_path = Path(temp_dir) / "content-fullscreen-overlay.png"
            _write_test_image(image_path)

            node_id = _add_browse_media_panel(window)
            window.scene.set_node_properties(
                node_id,
                {
                    "source": str(image_path),
                    "fit_mode": "cover",
                    "crop_x": 0.2,
                    "crop_y": 0.1,
                    "crop_w": 0.5,
                    "crop_h": 0.6,
                },
            )
            _flush_shell_qt_events(app)

            workspace = window.model.project.workspaces[
                window.workspace_manager.active_workspace_id()
            ]
            before_state = workspace.nodes[node_id].properties.copy()
            bridge = _shell_runtime(window).content_fullscreen_bridge
            assert bridge.request_open_node(node_id)
            _flush_shell_qt_events(app)

            root = window.quick_widget.rootObject()
            assert root is not None
            overlay = _find_child(root, "contentFullscreenOverlay")
            media_image = _find_child(root, "contentFullscreenMediaImage")
            fit_button = _find_child(root, "contentFullscreenDisplayModeFitButton")
            fill_button = _find_child(root, "contentFullscreenDisplayModeFillButton")
            actual_button = _find_child(
                root, "contentFullscreenDisplayModeActualButton"
            )

            assert bool(overlay.property("visible"))
            assert str(overlay.property("contentKind")) == "media"
            assert bridge.media_payload["media_kind"] == "image"
            assert str(overlay.property("effectiveDisplayMode")) == "fill"
            assert "local-media-preview" in _qurl_text(media_image.property("source"))
            assert bool(fill_button.property("selectedStyle"))
            assert not bool(fit_button.property("selectedStyle"))

            QMetaObject.invokeMethod(actual_button, "click")
            _flush_shell_qt_events(app)

            assert str(overlay.property("effectiveDisplayMode")) == "actual"
            assert bool(actual_button.property("selectedStyle"))
            after_state = workspace.nodes[node_id].properties.copy()
            assert after_state == before_state

        window.close()
        _flush_shell_qt_events(app)
        _delete_window(window, app)


def test_content_fullscreen_overlay_owns_animated_image_playback() -> None:
    with _shell_lifecycle_context() as app:
        window = _create_window(app, _build_window_via_constructor)
        image_path = (
            Path(__file__).resolve().parent
            / "fixtures"
            / "media"
            / "animated-small.gif"
        )
        node_id = _add_browse_media_panel(window)
        window.scene.set_node_properties(
            node_id,
            {
                "source": str(image_path),
                "fit_mode": "contain",
                "animation_playback_mode": "play",
            },
        )
        window.scene.focus_node(node_id)
        _flush_shell_qt_events(app)

        root = window.quick_widget.rootObject()
        assert root is not None

        def find_quick_item(item: QObject, object_name: str) -> QObject | None:
            if item.objectName() == object_name:
                return item
            child_items = item.childItems() if hasattr(item, "childItems") else []
            for child in child_items:
                match = find_quick_item(child, object_name)
                if match is not None:
                    return match
            return None

        wait_for_condition_or_raise(
            lambda: find_quick_item(root, "graphNodeMediaImageRenderer") is not None,
            app=app,
            timeout_ms=2500,
            timeout_message="Timed out waiting for the inline image surface.",
        )
        inline_surface = find_quick_item(root, "graphNodeMediaImageRenderer")
        assert inline_surface is not None
        bridge = _shell_runtime(window).content_fullscreen_bridge
        wait_for_condition_or_raise(
            lambda: bool(inline_surface.property("animationPlaying")),
            app=app,
            timeout_ms=2500,
            timeout_message="Timed out waiting for selected inline GIF playback.",
        )

        assert bridge.request_open_node(node_id)
        _flush_shell_qt_events(app)
        animated_image = _find_child(root, "contentFullscreenMediaAnimatedImage")
        static_image = _find_child(root, "contentFullscreenMediaImage")
        wait_for_condition_or_raise(
            lambda: bool(animated_image.property("playing")),
            app=app,
            timeout_ms=2500,
            timeout_message="Timed out waiting for fullscreen GIF playback.",
        )
        assert _qurl_text(animated_image.property("source")).startswith("file:///")
        assert _qurl_text(static_image.property("source")) == ""
        assert not bool(inline_surface.property("animationPlaying"))
        assert int(inline_surface.property("animationCurrentFrame")) == 0

        bridge.request_close()
        wait_for_condition_or_raise(
            lambda: bool(inline_surface.property("animationPlaying")),
            app=app,
            timeout_ms=2500,
            timeout_message="Timed out waiting for inline GIF playback to resume.",
        )

        window.scene.set_node_property(node_id, "animation_playback_mode", "pause")
        wait_for_condition_or_raise(
            lambda: not bool(inline_surface.property("animationPlaying")),
            app=app,
            timeout_ms=2500,
            timeout_message="Timed out waiting for saved pause mode.",
        )
        assert bridge.request_open_node(node_id)
        wait_for_condition_or_raise(
            lambda: bool(animated_image.property("playing")),
            app=app,
            timeout_ms=2500,
            timeout_message="Saved pause mode incorrectly blocked fullscreen GIF playback.",
        )
        bridge.request_close()
        _flush_shell_qt_events(app)
        assert not bool(inline_surface.property("animationPlaying"))

        window.close()
        _flush_shell_qt_events(app)
        _delete_window(window, app)


def test_content_fullscreen_overlay_preserves_cropped_image_source_aspect() -> None:
    with _shell_lifecycle_context() as app:
        window = _create_window(app, _build_window_via_constructor)
        with tempfile.TemporaryDirectory() as temp_dir:
            image_path = Path(temp_dir) / "content-fullscreen-crop-aspect.png"
            _write_test_image(image_path)

            node_id = _add_browse_media_panel(window)
            window.scene.set_node_properties(
                node_id,
                {
                    "source": str(image_path),
                    "fit_mode": "contain",
                    "crop_x": 0.0,
                    "crop_y": 0.25,
                    "crop_w": 1.0,
                    "crop_h": 0.5,
                },
            )
            _flush_shell_qt_events(app)

            bridge = _shell_runtime(window).content_fullscreen_bridge
            assert bridge.request_open_node(node_id)
            _flush_shell_qt_events(app)

            root = window.quick_widget.rootObject()
            assert root is not None
            overlay = _find_child(root, "contentFullscreenOverlay")
            viewport = _find_child(root, "contentFullscreenMediaImageViewport")
            transform_frame = _find_child(
                root, "contentFullscreenMediaImageTransformFrame"
            )
            media_image = _find_child(root, "contentFullscreenMediaImage")

            assert bool(overlay.property("visible"))
            assert str(overlay.property("contentKind")) == "media"
            assert bridge.media_payload["media_kind"] == "image"
            assert float(viewport.property("width")) > 0.0
            assert float(viewport.property("height")) > 0.0

            frame_width = float(transform_frame.property("width"))
            frame_height = float(transform_frame.property("height"))
            image_width = float(media_image.property("width"))
            image_height = float(media_image.property("height"))
            image_y = float(media_image.property("y"))

            assert frame_width > 0.0
            assert frame_height > 0.0
            assert image_width > 0.0
            assert image_height > 0.0
            assert frame_width / frame_height == pytest.approx(48.0 / 15.0, rel=0.01)
            assert image_width / image_height == pytest.approx(48.0 / 30.0, rel=0.01)
            assert image_height > frame_height
            assert image_y < 0.0

        window.close()
        _flush_shell_qt_events(app)
        _delete_window(window, app)


def test_content_fullscreen_overlay_renders_pdf_media_blocks_background_and_close_button() -> (
    None
):
    with _shell_lifecycle_context() as app:
        window = _create_window(app, _build_window_via_constructor)
        with tempfile.TemporaryDirectory() as temp_dir:
            pdf_path = Path(temp_dir) / "content-fullscreen-pages.pdf"
            _write_test_pdf(pdf_path, page_count=3)

            node_id = _add_browse_media_panel(window)
            window.scene.set_node_properties(
                node_id,
                {
                    "source": str(pdf_path),
                    "page_number": 1,
                },
            )
            _flush_shell_qt_events(app)

            bridge = _shell_runtime(window).content_fullscreen_bridge
            assert bridge.request_open_node(node_id)
            _flush_shell_qt_events(app)

            root = window.quick_widget.rootObject()
            assert root is not None
            overlay = _find_child(root, "contentFullscreenOverlay")
            blocker = _find_child(root, "contentFullscreenInteractionBlocker")
            media_summary = _find_child(root, "contentFullscreenMediaSummary")
            pdf_document = _find_child(root, "contentFullscreenPdfDocument")
            pdf_view = _find_child(root, "contentFullscreenPdfMultiPageView")
            previous_button = _find_child(root, "contentFullscreenPdfPreviousButton")
            next_button = _find_child(root, "contentFullscreenPdfNextButton")
            search_button = _find_child(root, "contentFullscreenPdfSearchButton")
            search_field = _find_child(root, "contentFullscreenPdfSearchField")
            zoom_out_button = _find_child(root, "contentFullscreenPdfZoomOutButton")
            zoom_in_button = _find_child(root, "contentFullscreenPdfZoomInButton")
            fit_width_button = _find_child(root, "contentFullscreenPdfFitWidthButton")
            actual_size_button = _find_child(
                root, "contentFullscreenPdfActualSizeButton"
            )
            rotate_button = _find_child(
                root, "contentFullscreenPdfRotateClockwiseButton"
            )
            close_button = _find_child(root, "contentFullscreenCloseButton")

            assert bool(overlay.property("visible"))
            assert str(overlay.property("contentKind")) == "media"
            assert bridge.media_payload["media_kind"] == "pdf"
            assert bool(blocker.property("visible"))
            assert bool(blocker.property("preventStealing"))
            assert _qurl_text(pdf_document.property("source")).startswith("file:")

            def pdf_current_page() -> int:
                value = pdf_view.property("currentPage")
                return int(value) if value is not None else -1

            def pdf_page_count() -> int:
                value = pdf_document.property("pageCount")
                return int(value) if value is not None else 0

            def pdf_render_scale() -> float:
                value = pdf_view.property("renderScale")
                return float(value) if value is not None else 0.0

            def pdf_page_rotation() -> float:
                value = pdf_view.property("pageRotation")
                return float(value) if value is not None else 0.0

            wait_for_condition_or_raise(
                lambda: (
                    bool(pdf_view.property("visible"))
                    and pdf_page_count() == 3
                    and pdf_current_page() == 0
                ),
                app=app,
                timeout_ms=2500,
                timeout_message="Timed out waiting for fullscreen PdfMultiPageView to load.",
            )
            assert str(media_summary.property("text")) == "PDF page 1 / 3"
            assert not bool(previous_button.property("enabled"))
            assert bool(next_button.property("enabled"))

            QTest.mouseClick(
                window.quick_widget,
                Qt.MouseButton.LeftButton,
                pos=window.quick_widget.rect().topLeft(),
            )
            _flush_shell_qt_events(app)
            assert bridge.open

            QMetaObject.invokeMethod(next_button, "click")
            wait_for_condition_or_raise(
                lambda: (
                    pdf_current_page() == 1
                    and str(media_summary.property("text")) == "PDF page 2 / 3"
                ),
                app=app,
                timeout_ms=1000,
                timeout_message="Timed out waiting for PdfMultiPageView page navigation.",
            )

            QMetaObject.invokeMethod(previous_button, "click")
            wait_for_condition_or_raise(
                lambda: (
                    pdf_current_page() == 0
                    and str(media_summary.property("text")) == "PDF page 1 / 3"
                ),
                app=app,
                timeout_ms=1000,
                timeout_message="Timed out waiting for PdfMultiPageView previous-page navigation.",
            )

            window.quick_widget.setFocus()
            QMetaObject.invokeMethod(overlay, "forceActiveFocus")
            QTest.keyClick(window.quick_widget, Qt.Key.Key_PageDown)
            wait_for_condition_or_raise(
                lambda: pdf_current_page() == 1,
                app=app,
                timeout_ms=1000,
                timeout_message="Timed out waiting for fullscreen PDF Page Down navigation.",
            )

            QMetaObject.invokeMethod(overlay, "forceActiveFocus")
            QTest.keyClick(window.quick_widget, Qt.Key.Key_End)
            wait_for_condition_or_raise(
                lambda: pdf_current_page() == 2,
                app=app,
                timeout_ms=1000,
                timeout_message="Timed out waiting for fullscreen PDF End navigation.",
            )

            QMetaObject.invokeMethod(overlay, "forceActiveFocus")
            QTest.keyClick(window.quick_widget, Qt.Key.Key_Home)
            wait_for_condition_or_raise(
                lambda: pdf_current_page() == 0,
                app=app,
                timeout_ms=1000,
                timeout_message="Timed out waiting for fullscreen PDF Home navigation.",
            )

            initial_scale = pdf_render_scale()
            QMetaObject.invokeMethod(zoom_in_button, "click")
            wait_for_condition_or_raise(
                lambda: pdf_render_scale() > initial_scale,
                app=app,
                timeout_ms=1000,
                timeout_message="Timed out waiting for fullscreen PDF zoom-in.",
            )

            QMetaObject.invokeMethod(zoom_out_button, "click")
            wait_for_condition_or_raise(
                lambda: pdf_render_scale() <= initial_scale * 1.02,
                app=app,
                timeout_ms=1000,
                timeout_message="Timed out waiting for fullscreen PDF zoom-out.",
            )

            QMetaObject.invokeMethod(fit_width_button, "click")
            wait_for_condition_or_raise(
                lambda: (
                    str(overlay.property("pdfFitMode")) == "width"
                    and bool(fit_width_button.property("selectedStyle"))
                ),
                app=app,
                timeout_ms=1000,
                timeout_message="Timed out waiting for fullscreen PDF fit-width mode.",
            )

            QMetaObject.invokeMethod(actual_size_button, "click")
            wait_for_condition_or_raise(
                lambda: (
                    str(overlay.property("pdfFitMode")) == "actual"
                    and abs(pdf_render_scale() - 1.0) < 0.02
                ),
                app=app,
                timeout_ms=1000,
                timeout_message="Timed out waiting for fullscreen PDF actual-size mode.",
            )

            QMetaObject.invokeMethod(rotate_button, "click")
            wait_for_condition_or_raise(
                lambda: abs(pdf_page_rotation() - 90.0) < 0.01,
                app=app,
                timeout_ms=1000,
                timeout_message="Timed out waiting for fullscreen PDF rotate button.",
            )

            QMetaObject.invokeMethod(overlay, "forceActiveFocus")
            QTest.keyClick(
                window.quick_widget, Qt.Key.Key_R, Qt.KeyboardModifier.ShiftModifier
            )
            wait_for_condition_or_raise(
                lambda: abs(pdf_page_rotation()) < 0.01,
                app=app,
                timeout_ms=1000,
                timeout_message="Timed out waiting for fullscreen PDF reverse rotate shortcut.",
            )

            QMetaObject.invokeMethod(overlay, "forceActiveFocus")
            QTest.keyClick(
                window.quick_widget, Qt.Key.Key_F, Qt.KeyboardModifier.ControlModifier
            )
            wait_for_condition_or_raise(
                lambda: (
                    bool(overlay.property("pdfSearchOpen"))
                    and bool(search_field.property("activeFocus"))
                ),
                app=app,
                timeout_ms=1000,
                timeout_message="Timed out waiting for fullscreen PDF Ctrl+F search focus.",
            )

            overlay.setProperty("pdfSearchText", "PDF page 2")
            wait_for_condition_or_raise(
                lambda: (
                    str(pdf_view.property("searchString")) == "PDF page 2"
                    and str(search_field.property("text")) == "PDF page 2"
                ),
                app=app,
                timeout_ms=1000,
                timeout_message="Timed out waiting for fullscreen PDF search binding.",
            )

            QMetaObject.invokeMethod(search_button, "click")
            wait_for_condition_or_raise(
                lambda: not bool(overlay.property("pdfSearchOpen")),
                app=app,
                timeout_ms=1000,
                timeout_message="Timed out waiting for fullscreen PDF search toggle.",
            )

            QMetaObject.invokeMethod(close_button, "click")
            _flush_shell_qt_events(app)
            assert not bridge.open

        window.close()
        _flush_shell_qt_events(app)
        _delete_window(window, app)


def test_content_fullscreen_overlay_renders_video_media_and_persists_close_state() -> (
    None
):
    with _shell_lifecycle_context() as app:
        window = _create_window(app, _build_window_via_constructor)
        with tempfile.TemporaryDirectory() as temp_dir:
            video_path = Path(temp_dir) / "content-fullscreen-overlay.mp4"
            video_path.write_bytes(b"not a decoded fixture")

            node_id = _add_browse_media_panel(window)
            window.scene.set_node_properties(
                node_id,
                {
                    "source": str(video_path),
                    "fit_mode": "cover",
                    "auto_play": False,
                    "loop": False,
                    "muted": False,
                    "volume": 1.0,
                    "playback_rate": 1.0,
                    "position_ms": 0,
                },
            )
            _flush_shell_qt_events(app)

            bridge = _shell_runtime(window).content_fullscreen_bridge
            assert bridge.request_open_node_with_state(
                node_id,
                {
                    "position_ms": 2500,
                    "playing": False,
                    "muted": True,
                    "volume": 0.5,
                    "playback_rate": 1.25,
                    "loop": True,
                    "fit_mode": "contain",
                },
            )
            _flush_shell_qt_events(app)

            root = window.quick_widget.rootObject()
            assert root is not None
            overlay = _find_child(root, "contentFullscreenOverlay")
            video_surface = _find_child(root, "contentFullscreenVideoSurface")
            video_output = _find_child(root, "contentFullscreenVideoOutput")

            assert bool(overlay.property("visible"))
            assert str(overlay.property("contentKind")) == "media"
            assert bridge.media_payload["media_kind"] == "video"
            assert video_surface is not None
            assert video_output is not None

            QMetaObject.invokeMethod(video_surface, "requestCloseWithState")
            _flush_shell_qt_events(app)

            assert not bridge.open
            workspace = window.model.project.workspaces[
                window.workspace_manager.active_workspace_id()
            ]
            node = workspace.nodes[node_id]
            assert node.properties["muted"] is True
            assert node.properties["volume"] == 0.5
            assert node.properties["playback_rate"] == 1.25
            assert node.properties["loop"] is True
            assert node.properties["fit_mode"] == "contain"

        window.close()
        _flush_shell_qt_events(app)
        _delete_window(window, app)


def test_content_fullscreen_overlay_closes_open_state_with_escape_and_f11() -> None:
    with _shell_lifecycle_context() as app:
        window = _create_window(app, _build_window_via_constructor)
        with tempfile.TemporaryDirectory() as temp_dir:
            image_path = Path(temp_dir) / "content-fullscreen-shortcuts.png"
            _write_test_image(image_path, color=0xFF669933)

            node_id = _add_browse_media_panel(window)
            window.scene.set_node_property(node_id, "source", str(image_path))
            _flush_shell_qt_events(app)

            bridge = _shell_runtime(window).content_fullscreen_bridge
            root = window.quick_widget.rootObject()
            assert root is not None
            assert root.findChild(QObject, "contentFullscreenOverlay") is None
            assert root.findChild(QObject, "contentFullscreenOverlayLoader") is not None

            assert bridge.request_open_node(node_id)
            _flush_shell_qt_events(app)
            overlay = _find_child(root, "contentFullscreenOverlay")
            assert bool(overlay.property("activeFocus"))
            window.quick_widget.setFocus()
            QMetaObject.invokeMethod(overlay, "forceActiveFocus")
            QTest.keyClick(window.quick_widget, Qt.Key.Key_Escape)
            _flush_shell_qt_events(app)
            assert not bridge.open

            assert bridge.request_open_node(node_id)
            _flush_shell_qt_events(app)
            assert _find_child(root, "contentFullscreenOverlay") is overlay
            assert bool(overlay.property("activeFocus"))
            window.quick_widget.setFocus()
            QMetaObject.invokeMethod(overlay, "forceActiveFocus")
            QTest.keyClick(window.quick_widget, Qt.Key.Key_F11)
            _flush_shell_qt_events(app)
            assert not bridge.open

        window.close()
        _flush_shell_qt_events(app)
        _delete_window(window, app)


def test_content_fullscreen_overlay_exposes_viewer_viewport_placeholder_contract() -> (
    None
):
    with _shell_lifecycle_context() as app:
        window = _create_window(app, _build_window_via_constructor)

        node_id = window.scene.add_node_from_type("model.viewer", x=120.0, y=80.0)
        _flush_shell_qt_events(app)

        bridge = _shell_runtime(window).content_fullscreen_bridge
        assert bridge.request_open_node(node_id)
        _flush_shell_qt_events(app)

        root = window.quick_widget.rootObject()
        assert root is not None
        overlay = _find_child(root, "contentFullscreenOverlay")
        viewer_viewport = _find_child(root, "contentFullscreenViewerViewport")
        viewer_status = _find_child(root, "contentFullscreenViewerStatusText")
        controls = _find_child(root, "viewerQuickControls")

        assert bool(overlay.property("visible"))
        assert str(overlay.property("contentKind")) == "viewer"
        assert bool(viewer_viewport.property("visible"))
        assert "Session" in str(viewer_status.property("text"))

        assert bool(controls.property("visible"))

        window.close()
        _flush_shell_qt_events(app)
        _delete_window(window, app)

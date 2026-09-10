from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QObject, QUrl, pyqtSignal  # noqa: E402
from PyQt6.QtWidgets import QApplication, QWidget  # noqa: E402

from ea_node_editor.ui.folder_explorer.native_widget import NativeFolderExplorerWidget  # noqa: E402
from ea_node_editor.ui_qml import native_folder_explorer_host_service as host_module  # noqa: E402


def _resolved(path: Path) -> str:
    return str(path.resolve(strict=False))


class _FakeBrowser(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("nativeFolderExplorerBrowser")
        self.calls: list[tuple[str, tuple[Any, ...]]] = []
        self.location_url = ""

    def dynamicCall(self, signature: str, *args: Any) -> str:  # noqa: N802
        self.calls.append((signature, args))
        if signature.startswith("LocationURL"):
            return self.location_url
        if signature.startswith("Navigate") and args:
            self.location_url = str(args[0])
        return ""


class _FakeNativeFolderExplorerWidget(NativeFolderExplorerWidget):
    fake_browser: _FakeBrowser

    def _create_windows_shell_browser(self) -> QWidget | None:
        self.fake_browser = _FakeBrowser(self)
        return self.fake_browser


class _FakeExplorerWidget(QWidget):
    path_changed = pyqtSignal(str)

    def __init__(self, path: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.initial_path = str(path)
        self.current_path = str(path)
        self.navigate_calls: list[str] = []

    def navigate_to(self, path: str) -> bool:
        self.current_path = str(path)
        self.navigate_calls.append(str(path))
        return True


class _FakeCommandBridge:
    def __init__(self) -> None:
        self.set_calls: list[tuple[str, str, str]] = []

    def set_node_property(self, node_id: str, property_name: str, value: str) -> None:
        self.set_calls.append((node_id, property_name, value))


class _FakeSceneBridge(QObject):
    nodes_changed = pyqtSignal()
    workspace_changed = pyqtSignal()
    scope_changed = pyqtSignal()

    def __init__(self, *, workspace_id: str, nodes_model: list[dict[str, Any]]) -> None:
        super().__init__()
        self.workspace_id = workspace_id
        self.nodes_model = nodes_model
        self.command_bridge = _FakeCommandBridge()


class _FakeOverlayManager:
    def __init__(self) -> None:
        self.last_error = ""
        self.set_active_calls: list[tuple[str, tuple[Any, ...]]] = []
        self.attach_calls: list[tuple[str, str, QWidget]] = []
        self.widgets: dict[tuple[str, str], QWidget] = {}
        self.containers: dict[tuple[str, str], QWidget] = {}

    def set_active_overlays_for_owner(self, owner: str, overlays) -> None:  # noqa: ANN001
        self.set_active_calls.append((owner, tuple(overlays)))

    def overlay_widget(self, node_id: str, *, workspace_id: str = "") -> QWidget | None:
        return self.widgets.get((workspace_id, node_id))

    def overlay_container(self, node_id: str, *, workspace_id: str = "") -> QWidget:
        key = (workspace_id, node_id)
        container = self.containers.get(key)
        if container is None:
            container = QWidget()
            container.resize(320, 180)
            self.containers[key] = container
        return container

    def attach_overlay_widget(self, node_id: str, widget: QWidget, *, workspace_id: str = "") -> bool:
        self.attach_calls.append((workspace_id, node_id, widget))
        self.widgets[(workspace_id, node_id)] = widget
        return True


class _ManualSyncNativeFolderExplorerHostService(host_module.NativeFolderExplorerHostService):
    def _schedule_sync(self, *args: object) -> None:
        del args
        self._sync_queued = False


def _folder_node(node_id: str, path: Path) -> dict[str, Any]:
    return {
        "type_id": "io.folder_explorer",
        "node_id": node_id,
        "properties": {
            "current_path": str(path),
        },
    }


class NativeFolderExplorerWidgetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self._widgets: list[QWidget] = []

    def tearDown(self) -> None:
        for widget in reversed(self._widgets):
            widget.close()
            widget.deleteLater()
        self.app.processEvents()

    def _track(self, widget: QWidget) -> QWidget:
        self._widgets.append(widget)
        return widget

    def test_poll_timer_starts_only_when_visible_and_stops_when_hidden_or_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            widget = self._track(_FakeNativeFolderExplorerWidget(temp_dir))
            widget.resize(240, 160)

            timer = widget._poll_timer
            self.assertIsNotNone(timer)
            self.assertFalse(timer.isActive())
            self.assertTrue(widget.property("ea.nativeWindowOverlay"))

            widget.show()
            self.app.processEvents()
            self.assertTrue(timer.isActive())

            widget.hide()
            self.app.processEvents()
            self.assertFalse(timer.isActive())

            widget.show()
            self.app.processEvents()
            self.assertTrue(timer.isActive())

            widget.close()
            self.app.processEvents()
            self.assertFalse(timer.isActive())

    def test_poll_location_does_not_call_com_while_hidden_or_outside_parent(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            first = root / "first"
            second = root / "second"
            first.mkdir()
            second.mkdir()

            parent = self._track(QWidget())
            parent.resize(100, 100)
            widget = self._track(_FakeNativeFolderExplorerWidget(str(first), parent=parent))
            widget.setGeometry(140, 140, 40, 40)
            parent.show()
            widget.show()
            self.app.processEvents()

            timer = widget._poll_timer
            self.assertIsNotNone(timer)
            self.assertFalse(timer.isActive())
            widget.fake_browser.calls.clear()
            widget.fake_browser.location_url = QUrl.fromLocalFile(str(second)).toString()

            widget._poll_location()

            self.assertEqual(widget.fake_browser.calls, [])
            self.assertEqual(widget.current_path, _resolved(first))

            widget.move(10, 10)
            self.app.processEvents()
            self.assertTrue(timer.isActive())
            widget.fake_browser.calls.clear()

            widget._poll_location()

            self.assertTrue(
                any(signature.startswith("LocationURL") for signature, _args in widget.fake_browser.calls)
            )

    def test_poll_location_emits_path_changed_when_visible_location_changes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            first = root / "first"
            second = root / "second"
            first.mkdir()
            second.mkdir()

            widget = self._track(_FakeNativeFolderExplorerWidget(str(first)))
            widget.resize(240, 160)
            seen: list[str] = []
            widget.path_changed.connect(seen.append)
            widget.show()
            self.app.processEvents()

            widget.fake_browser.calls.clear()
            widget.fake_browser.location_url = QUrl.fromLocalFile(str(second)).toString()
            widget._poll_location()

            self.assertEqual(seen, [_resolved(second)])
            self.assertEqual(widget.current_path, _resolved(second))


class NativeFolderExplorerHostServiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_disabled_service_connects_no_scene_signals_and_queues_no_sync(self) -> None:
        bridge = _FakeSceneBridge(workspace_id="workspace_a", nodes_model=[])
        overlay_manager = _FakeOverlayManager()
        service_type = host_module.NativeFolderExplorerHostService

        with (
            patch.object(service_type, "_connect_signals", autospec=True) as connect_signals,
            patch.object(service_type, "_schedule_sync", autospec=True) as schedule_sync,
        ):
            service = service_type(
                scene_bridge=bridge,
                overlay_manager=overlay_manager,  # type: ignore[arg-type]
                enabled=False,
            )

        connect_signals.assert_not_called()
        schedule_sync.assert_not_called()
        service.sync()
        self.assertEqual(overlay_manager.set_active_calls, [])

        with patch.object(host_module.QTimer, "singleShot") as single_shot:
            service._schedule_sync()  # noqa: SLF001
        single_shot.assert_not_called()
        service.shutdown()

    def test_repeated_sync_with_unchanged_specs_does_not_resubmit_reattach_or_navigate(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            first = root / "first"
            second = root / "second"
            first.mkdir()
            second.mkdir()
            bridge = _FakeSceneBridge(
                workspace_id="workspace_a",
                nodes_model=[_folder_node("folder_node", first)],
            )
            overlay_manager = _FakeOverlayManager()

            with patch.object(host_module, "NativeFolderExplorerWidget", _FakeExplorerWidget):
                service = _ManualSyncNativeFolderExplorerHostService(
                    scene_bridge=bridge,
                    overlay_manager=overlay_manager,  # type: ignore[arg-type]
                )

                service.sync()

                self.assertEqual(len(overlay_manager.set_active_calls), 1)
                self.assertEqual(len(overlay_manager.attach_calls), 1)
                widget = overlay_manager.widgets[("workspace_a", "folder_node")]
                self.assertIsInstance(widget, _FakeExplorerWidget)
                self.assertEqual(widget.initial_path, _resolved(first))
                self.assertEqual(widget.navigate_calls, [])

                service.sync()

                self.assertEqual(len(overlay_manager.set_active_calls), 1)
                self.assertEqual(len(overlay_manager.attach_calls), 1)
                self.assertEqual(widget.navigate_calls, [])

                bridge.nodes_model[0]["properties"]["current_path"] = str(second)
                service.sync()

                self.assertEqual(len(overlay_manager.set_active_calls), 2)
                self.assertEqual(len(overlay_manager.attach_calls), 1)
                self.assertEqual(widget.navigate_calls, [_resolved(second)])

                service.sync()

                self.assertEqual(len(overlay_manager.set_active_calls), 2)
                self.assertEqual(len(overlay_manager.attach_calls), 1)
                self.assertEqual(widget.navigate_calls, [_resolved(second)])

    def test_widget_path_changed_commits_current_path_to_scene_bridge(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            first = root / "first"
            second = root / "second"
            first.mkdir()
            second.mkdir()
            bridge = _FakeSceneBridge(
                workspace_id="workspace_a",
                nodes_model=[_folder_node("folder_node", first)],
            )
            overlay_manager = _FakeOverlayManager()

            with patch.object(host_module, "NativeFolderExplorerWidget", _FakeExplorerWidget):
                service = _ManualSyncNativeFolderExplorerHostService(
                    scene_bridge=bridge,
                    overlay_manager=overlay_manager,  # type: ignore[arg-type]
                )
                service.sync()

                widget = overlay_manager.widgets[("workspace_a", "folder_node")]
                self.assertIsInstance(widget, _FakeExplorerWidget)
                widget.path_changed.emit(_resolved(second))

                self.assertEqual(
                    bridge.command_bridge.set_calls,
                    [("folder_node", "current_path", _resolved(second))],
                )
                self.assertEqual(
                    service._bound_paths[("workspace_a", "folder_node")],
                    _resolved(second),
                )


if __name__ == "__main__":
    unittest.main()

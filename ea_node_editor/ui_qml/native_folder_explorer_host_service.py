from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from PyQt6.QtCore import QObject, QTimer, pyqtProperty, pyqtSignal, pyqtSlot
from PyQt6.QtWidgets import QWidget

from ea_node_editor.platform_paths import default_user_desktop_path
from ea_node_editor.ui.folder_explorer import NativeFolderExplorerWidget
from ea_node_editor.ui_qml.embedded_viewer_overlay_manager import (
    EmbeddedViewerOverlayManager,
    EmbeddedViewerOverlaySpec,
)

if TYPE_CHECKING:
    from ea_node_editor.ui.shell.window import ShellWindow
    from ea_node_editor.ui_qml.graph_scene_bridge import GraphSceneBridge

_FOLDER_EXPLORER_OVERLAY_OWNER = "folder_explorer"
_OverlayKey = tuple[str, str]
_OverlaySignature = tuple[tuple[str, str, str], ...]


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _string(value: Any) -> str:
    return str(value or "").strip()


def _folder_path_from_node_payload(payload: Mapping[str, Any]) -> str:
    properties = _mapping(payload.get("properties"))
    path = _string(properties.get("current_path") or payload.get("current_path"))
    if path:
        candidate = Path(path).expanduser()
        if candidate.exists() and candidate.is_file():
            candidate = candidate.parent
        return str(candidate.resolve(strict=False))
    return default_user_desktop_path()


@dataclass(slots=True, frozen=True)
class _NativeFolderExplorerSnapshot:
    workspace_id: str
    node_id: str
    current_path: str

    def overlay_spec(self) -> EmbeddedViewerOverlaySpec:
        return EmbeddedViewerOverlaySpec(
            workspace_id=self.workspace_id,
            node_id=self.node_id,
            session_id=self.current_path,
        )


class NativeFolderExplorerHostService(QObject):
    state_changed = pyqtSignal()
    last_error_changed = pyqtSignal()

    def __init__(
        self,
        parent: QObject | None = None,
        *,
        shell_window: "ShellWindow | None" = None,
        scene_bridge: "GraphSceneBridge | None" = None,
        overlay_manager: EmbeddedViewerOverlayManager | None = None,
        enabled: bool = True,
    ) -> None:
        super().__init__(parent)
        self._shell_window = shell_window
        self._scene_bridge = scene_bridge
        self._overlay_manager = overlay_manager
        self._enabled = bool(enabled)
        self._bound_paths: dict[_OverlayKey, str] = {}
        self._active_overlay_signature: _OverlaySignature | None = None
        self._last_error = ""
        self._sync_queued = False
        self._shutdown = False
        if self._enabled:
            self._connect_signals()
            self._schedule_sync()

    @property
    def overlay_manager(self) -> EmbeddedViewerOverlayManager | None:
        return self._overlay_manager

    @pyqtProperty(int, notify=state_changed)
    def active_overlay_count(self) -> int:
        return len(self._bound_paths)

    @pyqtProperty(str, notify=last_error_changed)
    def last_error(self) -> str:
        return self._last_error

    def set_overlay_manager(self, overlay_manager: EmbeddedViewerOverlayManager | None) -> None:
        if self._shutdown or self._overlay_manager is overlay_manager:
            return
        previous = self._overlay_manager
        self._overlay_manager = overlay_manager
        self._bound_paths.clear()
        self._active_overlay_signature = None
        if previous is not None:
            previous.set_active_overlays_for_owner(_FOLDER_EXPLORER_OVERLAY_OWNER, ())
        self._schedule_sync()

    def reset(self, *, reason: str = "") -> None:
        del reason
        self._bound_paths.clear()
        self._active_overlay_signature = None
        if self._overlay_manager is not None:
            self._overlay_manager.set_active_overlays_for_owner(_FOLDER_EXPLORER_OVERLAY_OWNER, ())
            self._active_overlay_signature = ()
        self._set_last_error("")
        self.state_changed.emit()

    def shutdown(self, *, reason: str = "") -> None:
        if self._shutdown:
            return
        self._shutdown = True
        self.reset(reason=reason or "shutdown")
        self._overlay_manager = None

    def _connect_signals(self) -> None:
        self._connect_signal(self._scene_bridge, "nodes_changed", self._schedule_sync)
        self._connect_signal(self._scene_bridge, "workspace_changed", self._schedule_sync)
        self._connect_signal(self._scene_bridge, "scope_changed", self._schedule_sync)

    @staticmethod
    def _connect_signal(source: object | None, name: str, slot) -> None:  # noqa: ANN001
        signal = getattr(source, name, None) if source is not None else None
        if signal is not None and hasattr(signal, "connect"):
            signal.connect(slot)

    def _schedule_sync(self, *args: object) -> None:
        del args
        if self._shutdown or not self._enabled or self._sync_queued:
            return
        self._sync_queued = True
        QTimer.singleShot(0, self._run_queued_sync)

    @pyqtSlot()
    def _run_queued_sync(self) -> None:
        self._sync_queued = False
        self.sync()

    @pyqtSlot()
    def sync(self) -> None:
        if self._shutdown or not self._enabled:
            return
        overlay_manager = self._overlay_manager
        if overlay_manager is None:
            self._bound_paths.clear()
            self._active_overlay_signature = None
            return

        snapshots = self._desired_snapshots()
        desired_signature = self._snapshot_signature(snapshots)
        desired_keys = {(snapshot.workspace_id, snapshot.node_id) for snapshot in snapshots}
        changed = desired_signature != self._active_overlay_signature
        for key in list(self._bound_paths):
            if key not in desired_keys:
                self._bound_paths.pop(key, None)
                changed = True

        if desired_signature != self._active_overlay_signature:
            overlay_manager.set_active_overlays_for_owner(
                _FOLDER_EXPLORER_OVERLAY_OWNER,
                (snapshot.overlay_spec() for snapshot in snapshots),
            )
            self._active_overlay_signature = desired_signature
        for snapshot in snapshots:
            if self._bound_paths.get((snapshot.workspace_id, snapshot.node_id)) != snapshot.current_path:
                if self._ensure_bound_widget(snapshot):
                    changed = True
        if changed:
            self.state_changed.emit()

    def _desired_snapshots(self) -> list[_NativeFolderExplorerSnapshot]:
        if not self._enabled:
            return []
        scene_bridge = self._scene_bridge
        if scene_bridge is None:
            return []
        workspace_id = _string(getattr(scene_bridge, "workspace_id", ""))
        if not workspace_id:
            return []
        nodes_model = getattr(scene_bridge, "nodes_model", [])
        snapshots: list[_NativeFolderExplorerSnapshot] = []
        for item in nodes_model if isinstance(nodes_model, list) else []:
            payload = _mapping(item)
            if _string(payload.get("type_id")) != "io.folder_explorer":
                continue
            node_id = _string(payload.get("node_id"))
            if not node_id:
                continue
            snapshots.append(
                _NativeFolderExplorerSnapshot(
                    workspace_id=workspace_id,
                    node_id=node_id,
                    current_path=_folder_path_from_node_payload(payload),
                )
            )
        return snapshots

    @staticmethod
    def _snapshot_signature(snapshots: list[_NativeFolderExplorerSnapshot]) -> _OverlaySignature:
        return tuple(
            sorted(
                (snapshot.workspace_id, snapshot.node_id, snapshot.current_path)
                for snapshot in snapshots
            )
        )

    def _ensure_bound_widget(self, snapshot: _NativeFolderExplorerSnapshot) -> bool:
        overlay_manager = self._overlay_manager
        if overlay_manager is None:
            return False
        key = (snapshot.workspace_id, snapshot.node_id)
        widget = overlay_manager.overlay_widget(snapshot.node_id, workspace_id=snapshot.workspace_id)
        if isinstance(widget, NativeFolderExplorerWidget):
            if self._bound_paths.get(key) != snapshot.current_path:
                widget.navigate_to(snapshot.current_path)
                self._bound_paths[key] = snapshot.current_path
                return True
            return False

        container = overlay_manager.overlay_container(snapshot.node_id, workspace_id=snapshot.workspace_id)
        parent = container if isinstance(container, QWidget) else None
        explorer = NativeFolderExplorerWidget(snapshot.current_path, parent=parent)
        explorer.path_changed.connect(
            lambda path, workspace_id=snapshot.workspace_id, node_id=snapshot.node_id: self._commit_current_path(
                workspace_id,
                node_id,
                path,
            )
        )
        if overlay_manager.attach_overlay_widget(
            snapshot.node_id,
            explorer,
            workspace_id=snapshot.workspace_id,
        ):
            self._bound_paths[key] = snapshot.current_path
            self._set_last_error("")
            return True
        else:
            self._set_last_error(overlay_manager.last_error)
            return False

    def _commit_current_path(self, workspace_id: str, node_id: str, path: str) -> None:
        if not _string(workspace_id) or not _string(node_id) or not _string(path):
            return
        scene_bridge = self._scene_bridge
        if scene_bridge is None or _string(getattr(scene_bridge, "workspace_id", "")) != workspace_id:
            return
        command_bridge = getattr(scene_bridge, "command_bridge", None)
        setter = getattr(command_bridge, "set_node_property", None)
        if not callable(setter):
            return
        setter(node_id, "current_path", _string(path))
        self._bound_paths[(workspace_id, node_id)] = _string(path)

    def _set_last_error(self, message: str) -> None:
        normalized = _string(message)
        if self._last_error == normalized:
            return
        self._last_error = normalized
        self.last_error_changed.emit()


__all__ = ["NativeFolderExplorerHostService"]

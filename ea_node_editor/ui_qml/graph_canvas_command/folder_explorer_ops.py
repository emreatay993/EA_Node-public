from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol, cast

from PyQt6.QtCore import QUrl, pyqtSlot
from PyQt6.QtGui import QGuiApplication
from PyQt6.QtWidgets import QMessageBox

from ea_node_editor.platform_open import (
    open_path_with_app_chooser,
    open_path_with_default_handler,
)
from ea_node_editor.platform_paths import default_user_desktop_path
from ea_node_editor.ui.folder_explorer import (
    FolderExplorerClipboard,
    FolderExplorerDirectoryEntry,
    FolderExplorerDirectoryListing,
    FolderExplorerServiceError,
)
from ea_node_editor.ui.shell.graph_action_contracts import (
    GraphActionId,
    normalize_graph_action_payload,
)
from ea_node_editor.ui_qml.bridge_runtime import (
    first_payload_str as _first_payload_str,
    payload_bool as _payload_bool,
    payload_float as _payload_float,
    payload_str as _payload_str,
)

if TYPE_CHECKING:
    pass

class _FolderExplorerConfirmationSource(Protocol):
    def confirm_folder_explorer_operation(
        self,
        operation: str,
        path: str,
        target_path: str = "",
    ) -> bool: ...


class _FolderExplorerClipboardSource(Protocol):
    def setText(self, text: str) -> None: ...  # noqa: N802


class _FolderExplorerOpenSource(Protocol):
    def open_folder_explorer_path(self, path: str) -> bool: ...


_FOLDER_EXPLORER_ACTION_IDS: frozenset[GraphActionId] = frozenset(
    {
        GraphActionId.FOLDER_EXPLORER_LIST,
        GraphActionId.FOLDER_EXPLORER_NAVIGATE,
        GraphActionId.FOLDER_EXPLORER_REFRESH,
        GraphActionId.FOLDER_EXPLORER_SET_SORT,
        GraphActionId.FOLDER_EXPLORER_SET_SEARCH,
        GraphActionId.FOLDER_EXPLORER_OPEN,
        GraphActionId.FOLDER_EXPLORER_OPEN_WITH,
        GraphActionId.FOLDER_EXPLORER_OPEN_IN_NEW_WINDOW,
        GraphActionId.FOLDER_EXPLORER_NEW_FOLDER,
        GraphActionId.FOLDER_EXPLORER_RENAME,
        GraphActionId.FOLDER_EXPLORER_DELETE,
        GraphActionId.FOLDER_EXPLORER_CUT,
        GraphActionId.FOLDER_EXPLORER_COPY,
        GraphActionId.FOLDER_EXPLORER_PASTE,
        GraphActionId.FOLDER_EXPLORER_COPY_PATH,
        GraphActionId.FOLDER_EXPLORER_PROPERTIES,
        GraphActionId.FOLDER_EXPLORER_SEND_TO_COREX_PATH_POINTER,
    }
)


_FOLDER_EXPLORER_DEFAULTABLE_PATH_ACTION_IDS: frozenset[GraphActionId] = frozenset(
    {
        GraphActionId.FOLDER_EXPLORER_LIST,
        GraphActionId.FOLDER_EXPLORER_REFRESH,
        GraphActionId.FOLDER_EXPLORER_SET_SORT,
        GraphActionId.FOLDER_EXPLORER_SET_SEARCH,
    }
)


_FOLDER_EXPLORER_CONFIRMATION_OPERATIONS: dict[GraphActionId, str] = {
    GraphActionId.FOLDER_EXPLORER_NEW_FOLDER: "new_folder",
    GraphActionId.FOLDER_EXPLORER_RENAME: "rename",
    GraphActionId.FOLDER_EXPLORER_DELETE: "delete",
    GraphActionId.FOLDER_EXPLORER_CUT: "cut",
    GraphActionId.FOLDER_EXPLORER_COPY: "copy",
    GraphActionId.FOLDER_EXPLORER_PASTE: "paste",
}


class FolderExplorerOps:
    """The folder-explorer feature: action dispatch, filesystem ops, payload shaping, and its source protocols."""

    @pyqtSlot(str, "QVariantMap", result="QVariantMap")
    def request_folder_explorer_action(self, action_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(payload, Mapping):
            return self._folder_explorer_error_payload(
                action_id=str(action_id or ""),
                code="invalid_payload",
                message="Folder explorer action payload must be an object.",
            )
        action_literal = str(action_id or "").strip()
        try:
            canonical_action_id = GraphActionId(action_literal)
        except ValueError:
            canonical_action_id = None
        if canonical_action_id not in _FOLDER_EXPLORER_ACTION_IDS:
            return self._folder_explorer_error_payload(
                action_id=str(action_id or ""),
                payload=payload,
                code="unknown_action",
                message=f"Unsupported folder explorer action: {action_id!r}",
            )
        payload_for_normalization = dict(payload)
        if (
            canonical_action_id in _FOLDER_EXPLORER_DEFAULTABLE_PATH_ACTION_IDS
            and not _payload_str(payload_for_normalization, "path")
        ):
            payload_for_normalization["path"] = default_user_desktop_path()
            payload_for_normalization["_defaulted_path"] = True
        normalized_payload = normalize_graph_action_payload(canonical_action_id, payload_for_normalization)
        if normalized_payload is None:
            return self._folder_explorer_error_payload(
                action_id=canonical_action_id.value,
                payload=payload_for_normalization,
                code="invalid_payload",
                message=f"Invalid payload for folder explorer action: {canonical_action_id.value}",
            )
        try:
            return self._dispatch_folder_explorer_action(canonical_action_id, normalized_payload)
        except FolderExplorerServiceError as exc:
            return self._folder_explorer_service_error_payload(canonical_action_id, normalized_payload, exc)

    def _dispatch_folder_explorer_action(
        self,
        action_id: GraphActionId,
        payload: Mapping[str, object],
    ) -> dict[str, Any]:
        if action_id in {
            GraphActionId.FOLDER_EXPLORER_LIST,
            GraphActionId.FOLDER_EXPLORER_REFRESH,
            GraphActionId.FOLDER_EXPLORER_SET_SORT,
            GraphActionId.FOLDER_EXPLORER_SET_SEARCH,
        }:
            return self._folder_explorer_listing_payload(action_id, payload)
        if action_id is GraphActionId.FOLDER_EXPLORER_NAVIGATE:
            return self._folder_explorer_navigate(action_id, payload)
        if action_id is GraphActionId.FOLDER_EXPLORER_OPEN:
            return self._folder_explorer_open(action_id, payload)
        if action_id is GraphActionId.FOLDER_EXPLORER_OPEN_WITH:
            return self._folder_explorer_open_with(action_id, payload)
        if action_id is GraphActionId.FOLDER_EXPLORER_OPEN_IN_NEW_WINDOW:
            return self._folder_explorer_open_in_new_window(action_id, payload)
        if action_id is GraphActionId.FOLDER_EXPLORER_NEW_FOLDER:
            return self._folder_explorer_new_folder(action_id, payload)
        if action_id is GraphActionId.FOLDER_EXPLORER_RENAME:
            return self._folder_explorer_rename(action_id, payload)
        if action_id is GraphActionId.FOLDER_EXPLORER_DELETE:
            return self._folder_explorer_delete(action_id, payload)
        if action_id is GraphActionId.FOLDER_EXPLORER_CUT:
            return self._folder_explorer_clipboard_action(action_id, payload, mode="cut")
        if action_id is GraphActionId.FOLDER_EXPLORER_COPY:
            return self._folder_explorer_clipboard_action(action_id, payload, mode="copy")
        if action_id is GraphActionId.FOLDER_EXPLORER_PASTE:
            return self._folder_explorer_paste(action_id, payload)
        if action_id is GraphActionId.FOLDER_EXPLORER_COPY_PATH:
            return self._folder_explorer_copy_path(action_id, payload)
        if action_id is GraphActionId.FOLDER_EXPLORER_PROPERTIES:
            return self._folder_explorer_properties(action_id, payload)
        if action_id is GraphActionId.FOLDER_EXPLORER_SEND_TO_COREX_PATH_POINTER:
            return self._folder_explorer_send_to_corex_path_pointer(action_id, payload)
        return self._folder_explorer_error_payload(
            action_id=action_id.value,
            payload=payload,
            code="unknown_action",
            message=f"Unsupported folder explorer action: {action_id.value}",
        )

    def _folder_explorer_listing_payload(
        self,
        action_id: GraphActionId,
        payload: Mapping[str, object],
        *,
        path: str | None = None,
    ) -> dict[str, Any]:
        listing = self._folder_explorer_service.list_directory(
            path or _payload_str(payload, "path"),
            sort_key=cast(Any, _first_payload_str(payload, "sort_key", "sortKey", default="name")),
            reverse=_payload_bool(payload, "reverse", False),
            filter_text=str(payload.get("filter_text", payload.get("filterText", "")) or ""),
        )
        if _payload_bool(payload, "_defaulted_path", False):
            self._set_folder_explorer_current_path(_payload_str(payload, "node_id"), listing.directory_path)
        return self._folder_explorer_success_payload(
            action_id,
            payload,
            path=listing.directory_path,
            listing=self._folder_explorer_listing_to_payload(listing),
        )

    def _folder_explorer_navigate(
        self,
        action_id: GraphActionId,
        payload: Mapping[str, object],
    ) -> dict[str, Any]:
        listing_result = self._folder_explorer_listing_payload(action_id, payload)
        if not listing_result.get("success"):
            return listing_result
        directory_path = _payload_str(cast(Mapping[str, object], listing_result), "path")
        if not self._set_folder_explorer_current_path(_payload_str(payload, "node_id"), directory_path):
            return self._folder_explorer_error_payload(
                action_id=action_id.value,
                payload=payload,
                path=directory_path,
                code="mutation_unavailable",
                message="Graph scene command bridge cannot update folder explorer current_path.",
            )
        return listing_result

    def _folder_explorer_open(
        self,
        action_id: GraphActionId,
        payload: Mapping[str, object],
    ) -> dict[str, Any]:
        path = self._folder_explorer_service.copy_path(_payload_str(payload, "path"))
        if not self._open_folder_explorer_path(path):
            return self._folder_explorer_error_payload(
                action_id=action_id.value,
                payload=payload,
                path=path,
                code="open_failed",
                message=f"Could not open path: {path}",
            )
        return self._folder_explorer_success_payload(action_id, payload, path=path)

    def _folder_explorer_open_with(
        self,
        action_id: GraphActionId,
        payload: Mapping[str, object],
    ) -> dict[str, Any]:
        path = self._folder_explorer_service.copy_path(_payload_str(payload, "path"))
        if not open_path_with_app_chooser(path):
            return self._folder_explorer_error_payload(
                action_id=action_id.value,
                payload=payload,
                path=path,
                code="open_failed",
                message=f"Could not open path with chooser: {path}",
            )
        return self._folder_explorer_success_payload(action_id, payload, path=path)

    def _folder_explorer_open_in_new_window(
        self,
        action_id: GraphActionId,
        payload: Mapping[str, object],
    ) -> dict[str, Any]:
        listing = self._folder_explorer_service.list_directory(_payload_str(payload, "path"))
        node_id = self._add_folder_explorer_node(
            listing.directory_path,
            _payload_float(payload, "scene_x"),
            _payload_float(payload, "scene_y"),
        )
        if not node_id:
            return self._folder_explorer_error_payload(
                action_id=action_id.value,
                payload=payload,
                path=listing.directory_path,
                code="mutation_unavailable",
                message="Graph scene command bridge cannot create an io.folder_explorer node.",
            )
        return self._folder_explorer_success_payload(
            action_id,
            payload,
            path=listing.directory_path,
            created_node_id=node_id,
            created_type_id="io.folder_explorer",
        )

    def _folder_explorer_new_folder(
        self,
        action_id: GraphActionId,
        payload: Mapping[str, object],
    ) -> dict[str, Any]:
        parent_path = _payload_str(payload, "path")
        name = _payload_str(payload, "name")
        target_path = str(Path(parent_path) / name) if name else ""
        cancelled = self._cancelled_confirmation_payload(action_id, payload, target_path=target_path)
        if cancelled is not None:
            return cancelled
        entry = self._folder_explorer_service.new_folder(parent_path, name, confirmed=True)
        return self._folder_explorer_entry_mutation_payload(action_id, payload, entry, listing_path=parent_path)

    def _folder_explorer_rename(
        self,
        action_id: GraphActionId,
        payload: Mapping[str, object],
    ) -> dict[str, Any]:
        path = _payload_str(payload, "path")
        new_name = _payload_str(payload, "new_name")
        parent_path = self._folder_explorer_refresh_path(payload, fallback_path=path)
        target_path = str(Path(path).parent / new_name) if new_name else ""
        cancelled = self._cancelled_confirmation_payload(action_id, payload, target_path=target_path)
        if cancelled is not None:
            return cancelled
        entry = self._folder_explorer_service.rename(path, new_name, confirmed=True)
        return self._folder_explorer_entry_mutation_payload(action_id, payload, entry, listing_path=parent_path)

    def _folder_explorer_delete(
        self,
        action_id: GraphActionId,
        payload: Mapping[str, object],
    ) -> dict[str, Any]:
        path = _payload_str(payload, "path")
        listing_path = self._folder_explorer_refresh_path(payload, fallback_path=path)
        cancelled = self._cancelled_confirmation_payload(action_id, payload)
        if cancelled is not None:
            return cancelled
        self._folder_explorer_service.delete(path, confirmed=True)
        return self._folder_explorer_success_payload(
            action_id,
            payload,
            path=path,
            listing=self._folder_explorer_listing_to_payload(
                self._folder_explorer_service.list_directory(listing_path)
            ),
        )

    def _folder_explorer_clipboard_action(
        self,
        action_id: GraphActionId,
        payload: Mapping[str, object],
        *,
        mode: str,
    ) -> dict[str, Any]:
        cancelled = self._cancelled_confirmation_payload(action_id, payload)
        if cancelled is not None:
            return cancelled
        path = _payload_str(payload, "path")
        clipboard = (
            self._folder_explorer_service.cut(path, confirmed=True)
            if mode == "cut"
            else self._folder_explorer_service.copy(path, confirmed=True)
        )
        return self._folder_explorer_success_payload(
            action_id,
            payload,
            path=clipboard.source_path,
            clipboard=self._folder_explorer_clipboard_to_payload(clipboard),
        )

    def _folder_explorer_paste(
        self,
        action_id: GraphActionId,
        payload: Mapping[str, object],
    ) -> dict[str, Any]:
        destination = _payload_str(payload, "path")
        cancelled = self._cancelled_confirmation_payload(action_id, payload)
        if cancelled is not None:
            return cancelled
        entry = self._folder_explorer_service.paste(destination, confirmed=True)
        return self._folder_explorer_entry_mutation_payload(action_id, payload, entry, listing_path=destination)

    def _folder_explorer_copy_path(
        self,
        action_id: GraphActionId,
        payload: Mapping[str, object],
    ) -> dict[str, Any]:
        copied_path = self._folder_explorer_service.copy_path(
            _payload_str(payload, "path"),
            quote=_payload_bool(payload, "quote", False),
        )
        if not self._copy_to_system_clipboard(copied_path):
            return self._folder_explorer_error_payload(
                action_id=action_id.value,
                payload=payload,
                path=copied_path,
                code="clipboard_unavailable",
                message="System clipboard is not available.",
            )
        return self._folder_explorer_success_payload(action_id, payload, path=copied_path, copied_path=copied_path)

    def _folder_explorer_properties(
        self,
        action_id: GraphActionId,
        payload: Mapping[str, object],
    ) -> dict[str, Any]:
        path = self._folder_explorer_service.copy_path(_payload_str(payload, "path"))
        return self._folder_explorer_success_payload(
            action_id,
            payload,
            path=path,
            entry=self._folder_explorer_entry_properties_payload(path),
        )

    def _folder_explorer_send_to_corex_path_pointer(
        self,
        action_id: GraphActionId,
        payload: Mapping[str, object],
    ) -> dict[str, Any]:
        path = self._folder_explorer_service.copy_path(_payload_str(payload, "path"))
        mode = "folder" if Path(path).is_dir() else "file"
        node_id = self._add_path_pointer_node(
            path,
            mode,
            _payload_float(payload, "scene_x"),
            _payload_float(payload, "scene_y"),
        )
        if not node_id:
            return self._folder_explorer_error_payload(
                action_id=action_id.value,
                payload=payload,
                path=path,
                code="mutation_unavailable",
                message="Graph scene command bridge cannot create an io.path_pointer node.",
            )
        return self._folder_explorer_success_payload(
            action_id,
            payload,
            path=path,
            created_node_id=node_id,
            created_type_id="io.path_pointer",
            mode=mode,
        )

    def _folder_explorer_entry_mutation_payload(
        self,
        action_id: GraphActionId,
        payload: Mapping[str, object],
        entry: FolderExplorerDirectoryEntry,
        *,
        listing_path: str,
    ) -> dict[str, Any]:
        return self._folder_explorer_success_payload(
            action_id,
            payload,
            path=entry.absolute_path,
            entry=self._folder_explorer_entry_to_payload(entry),
            listing=self._folder_explorer_listing_to_payload(
                self._folder_explorer_service.list_directory(listing_path)
            ),
        )

    def _set_folder_explorer_current_path(self, node_id: str, current_path: str) -> bool:
        command_source = self._scene_command_source
        if command_source is None:
            return False
        callback = getattr(command_source, "set_node_property", None)
        if not callable(callback):
            return False
        callback(node_id, "current_path", current_path)
        return True

    def _cancelled_confirmation_payload(
        self,
        action_id: GraphActionId,
        payload: Mapping[str, object],
        *,
        target_path: str = "",
    ) -> dict[str, Any] | None:
        operation = _FOLDER_EXPLORER_CONFIRMATION_OPERATIONS[action_id]
        path = _payload_str(payload, "path")
        if self._confirm_folder_explorer_operation(operation, path, target_path=target_path):
            return None
        return self._folder_explorer_error_payload(
            action_id=action_id.value,
            payload=payload,
            path=path,
            target_path=target_path,
            code="cancelled",
            message=f"Folder explorer operation was cancelled: {operation}",
            cancelled=True,
        )

    def _confirm_folder_explorer_operation(self, operation: str, path: str, *, target_path: str = "") -> bool:
        source = self._folder_explorer_confirmation_source
        callback = getattr(source, "confirm_folder_explorer_operation", None) if source is not None else None
        if callable(callback):
            return bool(callback(operation, path, target_path))

        message = f"Apply folder explorer operation '{operation}' to:\n{path}"
        if target_path:
            message += f"\n\nTarget:\n{target_path}"
        choice = QMessageBox.question(
            self._dialog_parent,
            "Confirm Folder Explorer Operation",
            message,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return choice == QMessageBox.StandardButton.Yes

    def _copy_to_system_clipboard(self, text: str) -> bool:
        source = self._folder_explorer_clipboard_source
        setter = getattr(source, "setText", None) if source is not None else None
        if callable(setter):
            setter(text)
            return True
        app = QGuiApplication.instance()
        if app is None:
            return False
        clipboard = app.clipboard()
        if clipboard is None:
            return False
        clipboard.setText(text)
        return True

    def _open_folder_explorer_path(self, path: str) -> bool:
        source = self._folder_explorer_open_source
        opener = getattr(source, "open_folder_explorer_path", None) if source is not None else None
        if callable(opener):
            return bool(opener(path))
        return open_path_with_default_handler(path)

    @staticmethod
    def _path_from_url_or_path(path_or_url: str) -> str:
        text = str(path_or_url or "").strip()
        if not text:
            return ""
        url = QUrl(text)
        if url.isLocalFile():
            return str(Path(url.toLocalFile()).resolve(strict=False))
        return str(Path(text).expanduser().resolve(strict=False))

    def _folder_explorer_refresh_path(self, payload: Mapping[str, object], *, fallback_path: str) -> str:
        explicit = _first_payload_str(payload, "current_path", "directory_path", "currentPath", "directoryPath")
        if explicit:
            return explicit
        parent = self._folder_explorer_service.parent_path(fallback_path)
        return parent or fallback_path

    def _folder_explorer_success_payload(
        self,
        action_id: GraphActionId,
        payload: Mapping[str, object],
        *,
        path: str = "",
        **values: Any,
    ) -> dict[str, Any]:
        result: dict[str, Any] = {
            "success": True,
            "cancelled": False,
            "action_id": action_id.value,
            "node_id": _payload_str(payload, "node_id"),
            "path": path or _payload_str(payload, "path"),
            "error": {},
        }
        result.update(values)
        return result

    def _folder_explorer_service_error_payload(
        self,
        action_id: GraphActionId,
        payload: Mapping[str, object],
        exc: FolderExplorerServiceError,
    ) -> dict[str, Any]:
        return self._folder_explorer_error_payload(
            action_id=action_id.value,
            payload=payload,
            path=exc.path,
            target_path=exc.target_path,
            code=exc.code,
            message=exc.message,
            error=exc.to_dict(),
        )

    def _folder_explorer_error_payload(
        self,
        *,
        action_id: str,
        payload: Mapping[str, object] | None = None,
        path: str = "",
        target_path: str = "",
        code: str,
        message: str,
        cancelled: bool = False,
        error: Mapping[str, object] | None = None,
    ) -> dict[str, Any]:
        normalized_payload = payload or {}
        return {
            "success": False,
            "cancelled": bool(cancelled),
            "action_id": action_id,
            "node_id": _payload_str(normalized_payload, "node_id"),
            "path": path or _payload_str(normalized_payload, "path"),
            "error": dict(
                error
                or {
                    "code": code,
                    "message": message,
                    "operation": action_id,
                    "path": path or _payload_str(normalized_payload, "path"),
                    "target_path": target_path,
                }
            ),
        }

    @staticmethod
    def _folder_explorer_listing_to_payload(listing: FolderExplorerDirectoryListing) -> dict[str, Any]:
        return {
            "directory_path": listing.directory_path,
            "parent_path": listing.parent_path or "",
            "breadcrumbs": [
                {
                    "name": breadcrumb.name,
                    "absolute_path": breadcrumb.absolute_path,
                }
                for breadcrumb in listing.breadcrumbs
            ],
            "entries": [
                FolderExplorerOps._folder_explorer_entry_to_payload(entry)
                for entry in listing.entries
            ],
            "sort_key": listing.sort_key,
            "reverse": listing.reverse,
            "filter_text": listing.filter_text,
        }

    @staticmethod
    def _folder_explorer_entry_to_payload(entry: FolderExplorerDirectoryEntry) -> dict[str, Any]:
        return {
            "name": entry.name,
            "absolute_path": entry.absolute_path,
            "kind": entry.kind,
            "is_folder": entry.is_folder,
            "modified_timestamp": entry.modified_timestamp,
            "extension": entry.extension,
            "type_label": entry.type_label,
            "size_bytes": entry.size_bytes if entry.size_bytes is not None else -1,
            "display_size": entry.display_size,
        }

    @staticmethod
    def _folder_explorer_clipboard_to_payload(clipboard: FolderExplorerClipboard) -> dict[str, str]:
        return {
            "source_path": clipboard.source_path,
            "mode": clipboard.mode,
        }

    @staticmethod
    def _folder_explorer_entry_properties_payload(path: str) -> dict[str, Any]:
        target = Path(path)
        stats = target.stat()
        is_folder = target.is_dir()
        return {
            "name": target.name or path,
            "absolute_path": path,
            "kind": "folder" if is_folder else "file",
            "is_folder": is_folder,
            "modified_timestamp": float(stats.st_mtime),
            "extension": "" if is_folder else target.suffix.lower(),
            "size_bytes": -1 if is_folder else int(stats.st_size),
        }

from __future__ import annotations

from typing import Any

from ea_node_editor.addons.catalog import discover_addon_records
from ea_node_editor.addons.contracts import AddOnRecord
from ._addon_manager_payloads import canonical_token
from ._addon_manager_payloads import detail_payload
from ._addon_manager_payloads import normalized_filter
from ._addon_manager_payloads import normalized_tab
from ._addon_manager_payloads import row_payload


class AddOnManagerPresenter:
    def __init__(self) -> None:
        self._shell_window = None
        self._records: tuple[AddOnRecord, ...] = ()
        self._selected_addon_id = ""
        self._active_tab = "about"
        self._status_filter = "all"
        self._last_error = ""
        self._request_serial = 0
        self._filtered_rows_cache: list[dict[str, Any]] = []
        self._selected_payload_cache: dict[str, Any] = {}

    def bind(self, *, shell_window=None) -> None:  # noqa: ANN001
        self._shell_window = shell_window

    @property
    def active_tab(self) -> str:
        return self._active_tab

    @property
    def status_filter(self) -> str:
        return self._status_filter

    @property
    def last_error(self) -> str:
        return self._last_error

    @property
    def selected_addon_id(self) -> str:
        return self._selected_addon_id

    @property
    def request_serial(self) -> int:
        return self._request_serial

    @property
    def row_count(self) -> int:
        return len(self._filtered_rows_cache)

    @property
    def pending_restart_count(self) -> int:
        return sum(1 for record in self._records if record.status == "pending_restart")

    @property
    def summary_text(self) -> str:
        loaded_count = sum(
            1 for record in self._records if record.state.enabled and record.availability.is_available
        )
        return f"{loaded_count} loaded / {len(self._records)} installed"

    @property
    def has_selection(self) -> bool:
        return self.selected_record() is not None

    def selected_record(self) -> AddOnRecord | None:
        for record in self._records:
            if record.addon_id == self._selected_addon_id:
                return record
        return None

    def filtered_rows(self) -> list[dict[str, Any]]:
        return list(self._filtered_rows_cache)

    def selected_payload(self) -> dict[str, Any]:
        return dict(self._selected_payload_cache)

    def set_error(self, message: str) -> None:
        self._last_error = str(message or "").strip()

    def clear_error(self) -> None:
        self._last_error = ""

    def sync_request(self, *, open_: bool, focus_addon_id: str, request_serial: int) -> None:
        self._request_serial = int(request_serial)
        self.refresh(focus_addon_id=focus_addon_id if open_ else "")

    def refresh(
        self,
        *,
        focus_addon_id: str = "",
        preferences_document: Any = None,
    ) -> None:
        shell_window = self._shell_window
        if shell_window is None:
            self._records = ()
            self._selected_addon_id = ""
            self._rebuild_payload_caches()
            return
        document = (
            shell_window.app_preferences_controller.document()
            if preferences_document is None
            else preferences_document
        )
        self._records = tuple(
            sorted(
                discover_addon_records(preferences_document=document),
                key=lambda record: (record.display_name.casefold(), record.addon_id.casefold()),
            )
        )
        normalized_focus = self._resolve_focus_addon_id(focus_addon_id)
        if normalized_focus:
            self._selected_addon_id = normalized_focus
            self._active_tab = "about"
        self._realign_selection()
        self._rebuild_payload_caches()
        if self._last_error:
            self._last_error = ""

    def set_status_filter(self, filter_id: str) -> None:
        normalized = normalized_filter(filter_id)
        if normalized == self._status_filter:
            return
        self._status_filter = normalized
        self._realign_selection()
        self._rebuild_payload_caches()

    def set_active_tab(self, tab_id: str) -> None:
        self._active_tab = normalized_tab(tab_id)

    def select_addon(self, addon_id: str) -> None:
        normalized = self._resolve_focus_addon_id(addon_id)
        if normalized:
            self._selected_addon_id = normalized
            self._rebuild_payload_caches()
            return
        if any(record.addon_id == addon_id for record in self._records):
            self._selected_addon_id = str(addon_id)
            self._rebuild_payload_caches()
            return
        self._realign_selection()
        self._rebuild_payload_caches()

    def set_addon_enabled(self, addon_id: str, enabled: bool) -> bool:
        shell_window = self._shell_window
        if shell_window is None:
            return False
        normalized_addon_id = self._resolve_focus_addon_id(addon_id)
        if not normalized_addon_id:
            return False
        selected = next((record for record in self._records if record.addon_id == normalized_addon_id), None)
        if selected is None or not selected.availability.is_available:
            return False
        app_preferences_controller = shell_window.app_preferences_controller
        try:
            result = shell_window.registry_replacement_coordinator.apply_addon_enabled_state(
                normalized_addon_id,
                enabled=bool(enabled),
                app_preferences_controller=app_preferences_controller,
                preferences_document=app_preferences_controller.document(),
            )
        except Exception as exc:  # noqa: BLE001
            self._last_error = str(exc)
            return False
        if result.restart_required:
            shell_window.workspace_state_changed.emit()
        self.refresh(
            focus_addon_id=normalized_addon_id,
            preferences_document=result.preferences_document,
        )
        return True

    def open_workflow_settings(self) -> None:
        shell_window = self._shell_window
        if shell_window is None:
            return
        shell_window.project_session_controller.show_workflow_settings_dialog()

    def _filtered_records(self) -> list[AddOnRecord]:
        if self._status_filter == "enabled":
            return [record for record in self._records if record.state.enabled]
        if self._status_filter == "disabled":
            return [record for record in self._records if not record.state.enabled]
        return list(self._records)

    def _realign_selection(self) -> None:
        if not self._records:
            self._selected_addon_id = ""
            return
        visible_records = self._filtered_records()
        if any(record.addon_id == self._selected_addon_id for record in visible_records):
            return
        if visible_records:
            self._selected_addon_id = visible_records[0].addon_id
            return
        if any(record.addon_id == self._selected_addon_id for record in self._records):
            return
        self._selected_addon_id = self._records[0].addon_id

    def _rebuild_payload_caches(self) -> None:
        registry = getattr(self._shell_window, "registry", None) if self._shell_window is not None else None
        self._filtered_rows_cache = [
            row_payload(record, selected_addon_id=self._selected_addon_id, registry=registry)
            for record in self._filtered_records()
        ]
        record = self.selected_record()
        self._selected_payload_cache = (
            {}
            if record is None
            else detail_payload(record, selected_addon_id=self._selected_addon_id, registry=registry)
        )

    def _resolve_focus_addon_id(self, addon_id: str) -> str:
        normalized = str(addon_id or "").strip()
        if not normalized:
            return ""
        for record in self._records:
            if record.addon_id == normalized:
                return record.addon_id
        requested_token = canonical_token(normalized)
        if not requested_token:
            return ""
        for record in self._records:
            record_token = canonical_token(record.addon_id)
            if record_token.endswith(requested_token) or requested_token.endswith(record_token):
                return record.addon_id
        return ""

__all__ = ["AddOnManagerPresenter"]

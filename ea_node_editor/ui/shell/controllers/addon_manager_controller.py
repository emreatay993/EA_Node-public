from __future__ import annotations

from typing import Any, Protocol


class _AddonManagerHostProtocol(Protocol):
    addon_manager_request_changed: Any


class AddonManagerController:
    def __init__(self, host: _AddonManagerHostProtocol) -> None:
        self._host = host
        self._open = False
        self._focus_addon_id = ""
        self._request_serial = 0

    @property
    def open(self) -> bool:
        return bool(self._open)

    @property
    def focus_addon_id(self) -> str:
        return str(self._focus_addon_id)

    @property
    def request_serial(self) -> int:
        return int(self._request_serial)

    def snapshot(self) -> dict[str, Any]:
        return {
            "open": self.open,
            "focus_addon_id": self.focus_addon_id,
            "request_serial": self.request_serial,
        }

    def request_open(self, focus_addon_id: str | None = None) -> None:
        self._open = True
        self._focus_addon_id = str(focus_addon_id or "").strip()
        self._request_serial += 1
        self._host.addon_manager_request_changed.emit()

    def request_close(self) -> None:
        if not self._open and not self._focus_addon_id and self._request_serial == 0:
            return
        self._open = False
        self._focus_addon_id = ""
        self._host.addon_manager_request_changed.emit()


__all__ = ["AddonManagerController"]

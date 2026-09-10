from __future__ import annotations

import sys
from pathlib import Path

from PyQt6.QtCore import QTimer, QUrl, pyqtSignal
from PyQt6.QtWidgets import QLabel, QVBoxLayout, QWidget

from ea_node_editor.platform_paths import default_user_desktop_path


def _normalized_folder_path(path: str) -> str:
    text = str(path or "").strip()
    if not text:
        text = default_user_desktop_path()
    candidate = Path(text).expanduser()
    if candidate.exists() and candidate.is_file():
        candidate = candidate.parent
    return str(candidate.resolve(strict=False))


class NativeFolderExplorerWidget(QWidget):
    """Windows shell Explorer host used by the Folder Explorer graph node."""

    path_changed = pyqtSignal(str)

    def __init__(self, path: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("nativeFolderExplorerWidget")
        self.setAcceptDrops(False)
        self.setProperty("ea.nativeWindowOverlay", False)
        self._current_path = _normalized_folder_path(path)
        self._browser: QWidget | None = None
        self._last_location_url = ""
        self._poll_timer: QTimer | None = None
        self._closing = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        browser = self._create_windows_shell_browser()
        if browser is None:
            fallback = QLabel(
                "Native Windows Explorer embedding is unavailable in this runtime.",
                self,
            )
            fallback.setObjectName("nativeFolderExplorerFallback")
            fallback.setWordWrap(True)
            fallback.setStyleSheet("QLabel { padding: 8px; color: #c8d3e3; background: #101318; }")
            layout.addWidget(fallback)
            self._browser = fallback
            return

        layout.addWidget(browser)
        self._browser = browser
        self.setFocusProxy(browser)
        self.setProperty("ea.nativeWindowOverlay", True)

        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(500)
        self._poll_timer.timeout.connect(self._poll_location)
        self._update_poll_timer()
        self.navigate_to(self._current_path)

    @property
    def current_path(self) -> str:
        return self._current_path

    @property
    def native_available(self) -> bool:
        return self._browser is not None and self._browser.objectName() == "nativeFolderExplorerBrowser"

    def navigate_to(self, path: str) -> bool:
        target_path = _normalized_folder_path(path)
        if target_path == self._current_path and self._last_location_url:
            return True
        self._current_path = target_path
        browser = self._browser
        dynamic_call = getattr(browser, "dynamicCall", None)
        if not callable(dynamic_call):
            return False
        url = QUrl.fromLocalFile(target_path).toString()
        for signature in (
            "Navigate(const QString&)",
            "Navigate(QString)",
            "Navigate2(QString)",
            "Navigate2(const QString&)",
        ):
            try:
                dynamic_call(signature, url)
            except Exception:  # noqa: BLE001
                continue
            self._last_location_url = url
            return True
        return False

    def _create_windows_shell_browser(self) -> QWidget | None:
        if sys.platform != "win32":
            return None
        try:
            from PyQt6.QAxContainer import QAxWidget
        except Exception:  # noqa: BLE001
            return None

        browser = QAxWidget(self)
        browser.setObjectName("nativeFolderExplorerBrowser")
        for control in ("Shell.Explorer.2", "Shell.Explorer"):
            try:
                browser.setControl(control)
                if str(browser.control() or "").strip():
                    return browser
            except Exception:  # noqa: BLE001
                continue
        browser.deleteLater()
        return None

    def showEvent(self, event) -> None:  # noqa: ANN001, N802
        super().showEvent(event)
        self._update_poll_timer()

    def hideEvent(self, event) -> None:  # noqa: ANN001, N802
        self._update_poll_timer(active=False)
        super().hideEvent(event)

    def closeEvent(self, event) -> None:  # noqa: ANN001, N802
        self._closing = True
        self._update_poll_timer(active=False)
        super().closeEvent(event)

    def moveEvent(self, event) -> None:  # noqa: ANN001, N802
        super().moveEvent(event)
        self._update_poll_timer()

    def resizeEvent(self, event) -> None:  # noqa: ANN001, N802
        super().resizeEvent(event)
        self._update_poll_timer()

    def _is_effectively_visible(self) -> bool:
        if self._closing or not self.isVisible() or self.width() <= 0 or self.height() <= 0:
            return False
        widget: QWidget | None = self
        while widget is not None:
            if not widget.isVisible():
                return False
            parent = widget.parentWidget()
            if parent is not None:
                geometry = widget.geometry()
                if geometry.isEmpty() or not geometry.intersects(parent.rect()):
                    return False
            widget = parent
        return True

    def _should_poll_location(self) -> bool:
        return self.native_available and self._is_effectively_visible()

    def _update_poll_timer(self, *, active: bool | None = None) -> None:
        timer = self._poll_timer
        if timer is None:
            return
        should_run = self._should_poll_location() if active is None else bool(active)
        if should_run:
            if not timer.isActive():
                timer.start()
            return
        if timer.isActive():
            timer.stop()

    def _poll_location(self) -> None:
        if not self._should_poll_location():
            self._update_poll_timer(active=False)
            return
        browser = self._browser
        dynamic_call = getattr(browser, "dynamicCall", None)
        if not callable(dynamic_call):
            return
        location_url = ""
        for signature in ("LocationURL()", "LocationURL"):
            try:
                value = dynamic_call(signature)
            except Exception:  # noqa: BLE001
                continue
            location_url = str(value or "").strip()
            if location_url:
                break
        if not location_url or location_url == self._last_location_url:
            return
        self._last_location_url = location_url
        local_path = QUrl(location_url).toLocalFile()
        if not local_path:
            return
        normalized = _normalized_folder_path(local_path)
        if normalized == self._current_path:
            return
        self._current_path = normalized
        self.path_changed.emit(normalized)


__all__ = ["NativeFolderExplorerWidget"]

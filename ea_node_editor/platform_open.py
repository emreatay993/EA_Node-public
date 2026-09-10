from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from PyQt6.QtCore import QUrl
from PyQt6.QtGui import QDesktopServices


def _normalized_existing_path(path: object) -> Path | None:
    """Return an expanded ``Path`` for an existing target, else ``None``.

    Empty, malformed, or non-existent paths resolve to ``None`` so callers can
    surface a user-facing error instead of launching nothing.
    """
    text = str(path or "").strip()
    if not text:
        return None
    try:
        candidate = Path(text).expanduser()
    except (OSError, ValueError):
        return None
    try:
        if not candidate.exists():
            return None
    except OSError:
        return None
    return candidate


def _open_with_desktop_services(candidate: Path) -> bool:
    return bool(QDesktopServices.openUrl(QUrl.fromLocalFile(str(candidate))))


def open_path_with_default_handler(path: object) -> bool:
    """Open a file/folder with the OS default handler (Explorer-style "Open").

    Returns ``True`` on a successful launch, ``False`` for missing/invalid paths
    or when no handler could be invoked. Never raises.
    """
    candidate = _normalized_existing_path(path)
    if candidate is None:
        return False
    target = str(candidate)
    if sys.platform == "win32" and hasattr(os, "startfile"):
        try:
            os.startfile(target)  # type: ignore[attr-defined]  # Windows-only
            return True
        except OSError:
            return _open_with_desktop_services(candidate)
    if sys.platform == "darwin":
        try:
            if subprocess.run(["open", target], check=False).returncode == 0:
                return True
        except OSError:
            pass
        return _open_with_desktop_services(candidate)
    # Linux / other: prefer xdg-open, fall back to Qt's handler.
    try:
        if subprocess.run(["xdg-open", target], check=False).returncode == 0:
            return True
    except OSError:
        pass
    return _open_with_desktop_services(candidate)


def open_path_with_app_chooser(path: object) -> bool:
    """Open the OS "Open with..." app picker for a path.

    Windows shows the native "Open with" dialog. macOS/Linux have no portable
    app-picker, so they fall back to a platform-native equivalent (reveal in
    Finder / default handler). Returns ``False`` for missing/invalid paths.
    Never raises.
    """
    candidate = _normalized_existing_path(path)
    if candidate is None:
        return False
    target = str(candidate)
    if sys.platform == "win32":
        try:
            completed = subprocess.run(
                ["rundll32.exe", "shell32.dll,OpenAs_RunDLL", target],
                check=False,
            )
            return completed.returncode == 0
        except OSError:
            return False
    if sys.platform == "darwin":
        # No native "always choose an app" picker; reveal in Finder instead.
        try:
            return subprocess.run(["open", "-R", target], check=False).returncode == 0
        except OSError:
            return False
    # Linux / other: no portable chooser; fall back to the default handler.
    return open_path_with_default_handler(candidate)


__all__ = ["open_path_with_default_handler", "open_path_with_app_chooser"]

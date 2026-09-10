from __future__ import annotations

import logging
import os
import sys
from dataclasses import dataclass
from typing import Any

from PyQt6.QtCore import QT_VERSION_STR
from PyQt6.QtQuick import QQuickWindow, QSGRendererInterface

from ea_node_editor.ui_qml.qml_host_factory import qml_host_environment_snapshot

LOGGER = logging.getLogger(__name__)

BACKEND_OVERRIDE_ENV = "EA_NODE_EDITOR_QSG_RHI_BACKEND"
FORCE_SOFTWARE_ENV = "EA_NODE_EDITOR_FORCE_SOFTWARE_QML"
WINDOWS_DESKTOP_DEFAULT_BACKEND = "d3d11"
_SOFTWARE_QPA_PLATFORMS = {"offscreen", "minimal"}
_TRUE_VALUES = {"1", "true", "yes", "on"}
_SUPPORTED_BACKEND_OVERRIDES = {
    "auto",
    "d3d11",
    "d3d12",
    "opengl",
    "vulkan",
    "metal",
    "software",
}
_GRAPHICS_API_BY_BACKEND = {
    "d3d11": QSGRendererInterface.GraphicsApi.Direct3D11Rhi,
    "d3d12": QSGRendererInterface.GraphicsApi.Direct3D12,
    "opengl": QSGRendererInterface.GraphicsApi.OpenGL,
    "vulkan": QSGRendererInterface.GraphicsApi.VulkanRhi,
    "metal": QSGRendererInterface.GraphicsApi.MetalRhi,
    "software": QSGRendererInterface.GraphicsApi.Software,
}
_GRAPHICS_API_LABELS = {
    QSGRendererInterface.GraphicsApi.Direct3D11Rhi: "Direct3D 11",
    QSGRendererInterface.GraphicsApi.Direct3D12: "Direct3D 12",
    QSGRendererInterface.GraphicsApi.MetalRhi: "Metal",
    QSGRendererInterface.GraphicsApi.NullRhi: "Null",
    QSGRendererInterface.GraphicsApi.OpenGL: "OpenGL",
    QSGRendererInterface.GraphicsApi.OpenVG: "OpenVG",
    QSGRendererInterface.GraphicsApi.Software: "Software",
    QSGRendererInterface.GraphicsApi.VulkanRhi: "Vulkan",
}


@dataclass(frozen=True, slots=True)
class QtQuickBackendSelection:
    requested_override: str
    normalized_override: str
    selected_backend: str
    reason: str
    forced_software: bool
    invalid_override: bool

    def to_payload(self) -> dict[str, Any]:
        return {
            "requested_override": self.requested_override,
            "normalized_override": self.normalized_override,
            "selected_backend": self.selected_backend,
            "reason": self.reason,
            "forced_software": self.forced_software,
            "invalid_override": self.invalid_override,
        }


def normalize_qsg_rhi_backend_override(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in _SUPPORTED_BACKEND_OVERRIDES:
        return normalized
    return ""


def _qt_qpa_platform_name() -> str:
    return os.environ.get("QT_QPA_PLATFORM", "").split(";", 1)[0].strip().lower()


def _is_windows_desktop_qpa_platform(platform_name: str) -> bool:
    return sys.platform.startswith("win") and platform_name not in _SOFTWARE_QPA_PLATFORMS


def select_qtquick_backend_from_environment() -> QtQuickBackendSelection:
    requested_override = os.environ.get(BACKEND_OVERRIDE_ENV, "").strip()
    normalized_override = normalize_qsg_rhi_backend_override(requested_override)
    force_value = os.environ.get(FORCE_SOFTWARE_ENV, "").strip().lower()
    platform_name = _qt_qpa_platform_name()
    invalid_override = bool(requested_override) and not normalized_override

    if invalid_override:
        LOGGER.warning(
            "Unsupported %s=%r; supported values are auto, d3d11, d3d12, "
            "opengl, vulkan, metal, and software. Leaving Qt Quick backend "
            "at the Qt default unless a software-only platform requires it.",
            BACKEND_OVERRIDE_ENV,
            requested_override,
        )

    if force_value in _TRUE_VALUES:
        return QtQuickBackendSelection(
            requested_override=requested_override,
            normalized_override=normalized_override,
            selected_backend="software",
            reason="forced_software_env",
            forced_software=True,
            invalid_override=invalid_override,
        )

    if platform_name in _SOFTWARE_QPA_PLATFORMS:
        return QtQuickBackendSelection(
            requested_override=requested_override,
            normalized_override=normalized_override,
            selected_backend="software",
            reason="software_qpa_platform",
            forced_software=True,
            invalid_override=invalid_override,
        )

    if normalized_override and normalized_override != "auto":
        return QtQuickBackendSelection(
            requested_override=requested_override,
            normalized_override=normalized_override,
            selected_backend=normalized_override,
            reason="env_override",
            forced_software=normalized_override == "software",
            invalid_override=False,
        )

    if not requested_override and _is_windows_desktop_qpa_platform(platform_name):
        return QtQuickBackendSelection(
            requested_override=requested_override,
            normalized_override=normalized_override,
            selected_backend=WINDOWS_DESKTOP_DEFAULT_BACKEND,
            reason="windows_desktop_default",
            forced_software=False,
            invalid_override=False,
        )

    return QtQuickBackendSelection(
        requested_override=requested_override,
        normalized_override=normalized_override,
        selected_backend="",
        reason="qt_default",
        forced_software=False,
        invalid_override=invalid_override,
    )


def configure_qtquick_backend() -> QtQuickBackendSelection:
    selection = select_qtquick_backend_from_environment()
    if selection.selected_backend == "software":
        os.environ["QT_QUICK_BACKEND"] = "software"
        os.environ["QSG_RHI_BACKEND"] = "software"
        os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "Basic")
        QQuickWindow.setGraphicsApi(QSGRendererInterface.GraphicsApi.Software)
        return selection

    if selection.selected_backend:
        os.environ["QSG_RHI_BACKEND"] = selection.selected_backend
        graphics_api = _GRAPHICS_API_BY_BACKEND.get(selection.selected_backend)
        if graphics_api is not None:
            QQuickWindow.setGraphicsApi(graphics_api)
    return selection


def enum_name(value: Any) -> str:
    name = getattr(value, "name", None)
    if name:
        return str(name)
    return str(value)


def graphics_api_name(window: QQuickWindow | None = None) -> str:
    if window is not None:
        try:
            renderer_interface = window.rendererInterface()
            if renderer_interface is not None:
                return enum_name(renderer_interface.graphicsApi())
        except Exception:  # noqa: BLE001
            pass
    try:
        return enum_name(QQuickWindow.graphicsApi())
    except Exception:  # noqa: BLE001
        return "unknown"


def graphics_api_label(window: QQuickWindow | None = None) -> str:
    api = QSGRendererInterface.GraphicsApi.Unknown
    if window is not None:
        try:
            renderer_interface = window.rendererInterface()
            if renderer_interface is not None:
                api = renderer_interface.graphicsApi()
        except Exception:  # noqa: BLE001
            api = QSGRendererInterface.GraphicsApi.Unknown
    if api == QSGRendererInterface.GraphicsApi.Unknown:
        try:
            api = QQuickWindow.graphicsApi()
        except Exception:  # noqa: BLE001
            api = QSGRendererInterface.GraphicsApi.Unknown
    return _GRAPHICS_API_LABELS.get(api, "Unavailable")


def qtquick_environment_snapshot() -> dict[str, Any]:
    selection = select_qtquick_backend_from_environment()
    qsg_info_value = os.environ.get("QSG_INFO", "").strip()
    return {
        "qt_version": QT_VERSION_STR,
        **qml_host_environment_snapshot(),
        "qt_qpa_platform": os.environ.get("QT_QPA_PLATFORM", ""),
        "qt_quick_backend": os.environ.get("QT_QUICK_BACKEND", ""),
        "qsg_rhi_backend": os.environ.get("QSG_RHI_BACKEND", ""),
        "qsg_info": qsg_info_value,
        "qsg_info_capture_enabled": qsg_info_value.lower() in _TRUE_VALUES,
        "qsg_render_loop": os.environ.get("QSG_RENDER_LOOP", ""),
        "qsg_rhi_backend_override": selection.requested_override,
        "qsg_rhi_backend_override_normalized": selection.normalized_override,
        "qtquick_backend_selected": selection.selected_backend,
        "qtquick_backend_selection_reason": selection.reason,
        "qtquick_backend_forced_software": selection.forced_software,
        "qtquick_backend_invalid_override": selection.invalid_override,
    }


def qtquick_backend_diagnostics(
    window: QQuickWindow | None = None,
    *,
    qml_host_kind: str = "",
    grab_window_readback_included: bool = False,
) -> dict[str, Any]:
    screen = window.screen() if window is not None else None
    screen_dpr = float(screen.devicePixelRatio()) if screen is not None else 1.0
    window_dpr = float(window.effectiveDevicePixelRatio()) if window is not None else 1.0
    selection = select_qtquick_backend_from_environment()
    api_name = graphics_api_name(window)
    api_label = graphics_api_label(window)
    software_fallback_active = (
        selection.selected_backend == "software"
        or selection.forced_software
        or api_name == "Software"
        or api_label == "Software"
    )
    return {
        **qtquick_environment_snapshot(),
        "graphics_api": api_name,
        "graphics_api_label": api_label,
        "qml_host_kind": qml_host_kind,
        "screen_device_pixel_ratio": screen_dpr,
        "window_effective_device_pixel_ratio": window_dpr,
        "grab_window_readback_included": bool(grab_window_readback_included),
        "software_fallback_active": software_fallback_active,
        "software_fallback_reason": selection.reason if software_fallback_active else "",
    }


__all__ = [
    "BACKEND_OVERRIDE_ENV",
    "FORCE_SOFTWARE_ENV",
    "QtQuickBackendSelection",
    "WINDOWS_DESKTOP_DEFAULT_BACKEND",
    "configure_qtquick_backend",
    "enum_name",
    "graphics_api_label",
    "graphics_api_name",
    "normalize_qsg_rhi_backend_override",
    "qtquick_backend_diagnostics",
    "qtquick_environment_snapshot",
    "select_qtquick_backend_from_environment",
]

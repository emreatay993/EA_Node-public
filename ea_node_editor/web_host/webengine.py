"""Lazy Qt WebEngine availability checks."""

from __future__ import annotations

from dataclasses import dataclass
import importlib
import os

_WEBENGINE_MODULES = ("PyQt6.QtWebEngineCore", "PyQt6.QtWebEngineQuick", "PyQt6.QtWebEngineWidgets")
_OFFSCREEN_QT_PLATFORMS = {"offscreen"}
_OFFSCREEN_OVERRIDE_ENV = "COREX_ENABLE_OFFSCREEN_WEBENGINE"


@dataclass(frozen=True)
class WebEngineAvailability:
    """Result of probing optional PyQt6 WebEngine support."""

    available: bool
    reason: str = ""
    module_name: str = ""
    exception_type: str = ""

    def __bool__(self) -> bool:
        return self.available

    def as_payload(self) -> dict[str, bool | str]:
        """Return a UI-safe payload without importing Qt WebEngine."""

        return {
            "webengine_available": bool(self.available),
            "webengine_reason": str(self.reason or ""),
            "webengine_module_name": str(self.module_name or ""),
            "webengine_exception_type": str(self.exception_type or ""),
        }


def is_webengine_disabled_for_offscreen_platform() -> bool:
    """Return whether live WebEngine should stay disabled for the current Qt platform."""

    qt_platform = os.environ.get("QT_QPA_PLATFORM", "").split(";", 1)[0].strip().lower()
    override = os.environ.get(_OFFSCREEN_OVERRIDE_ENV, "").lower()
    return qt_platform in _OFFSCREEN_QT_PLATFORMS and override not in {"1", "true", "yes", "on"}


def check_webengine_available() -> WebEngineAvailability:
    """Import WebEngine lazily and report failures without raising."""

    if is_webengine_disabled_for_offscreen_platform():
        return WebEngineAvailability(
            available=False,
            reason="Qt WebEngine is disabled for the offscreen Qt platform.",
            module_name="QtWebEngine",
            exception_type="RuntimeError",
        )

    for module_name in _WEBENGINE_MODULES:
        try:
            importlib.import_module(module_name)
        except Exception as exc:
            return WebEngineAvailability(
                available=False,
                reason=str(exc),
                module_name=module_name,
                exception_type=type(exc).__name__,
            )
    return WebEngineAvailability(available=True)


def is_webengine_available() -> bool:
    """Return whether optional PyQt6 WebEngine modules can be imported."""

    return check_webengine_available().available

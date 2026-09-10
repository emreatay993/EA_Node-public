from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Literal

from PyQt6.QtCore import QSize
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication, QWidget

AppIconVariant = Literal["opaque", "transparent", "minimal"]

APP_ICON_SIZES = (16, 24, 32, 48, 64, 128, 256, 512, 1024)


@dataclass(frozen=True, slots=True)
class AppIconAssetSet:
    variant: AppIconVariant
    svg_path: Path
    png_paths: tuple[Path, ...]
    ico_path: Path | None = None


_APP_ICON_ROOT = Path(__file__).resolve().parents[1] / "assets" / "app_icon"
_APP_ICON_PREFIXES: dict[AppIconVariant, str] = {
    "opaque": "corex_app",
    "transparent": "corex_app_transparent",
    "minimal": "corex_app_minimal",
}


def _normalize_variant(variant: str) -> AppIconVariant:
    normalized = str(variant or "opaque").strip().lower()
    if normalized not in _APP_ICON_PREFIXES:
        raise KeyError(f"Unknown app icon variant: {variant}")
    return normalized  # type: ignore[return-value]


def app_icon_root() -> Path:
    return _APP_ICON_ROOT


def app_icon_svg_path(variant: AppIconVariant = "opaque") -> Path:
    normalized = _normalize_variant(variant)
    return _APP_ICON_ROOT / f"{_APP_ICON_PREFIXES[normalized]}.svg"


def app_icon_png_path(size: int, variant: AppIconVariant = "opaque") -> Path:
    normalized = _normalize_variant(variant)
    normalized_size = max(1, int(size))
    return _APP_ICON_ROOT / f"{_APP_ICON_PREFIXES[normalized]}_{normalized_size}.png"


def app_icon_ico_path() -> Path:
    return _APP_ICON_ROOT / "corex_app.ico"


def app_icon_assets(variant: AppIconVariant = "opaque") -> AppIconAssetSet:
    normalized = _normalize_variant(variant)
    ico_path = app_icon_ico_path() if normalized == "opaque" else None
    return AppIconAssetSet(
        variant=normalized,
        svg_path=app_icon_svg_path(normalized),
        png_paths=tuple(app_icon_png_path(size, normalized) for size in APP_ICON_SIZES),
        ico_path=ico_path,
    )


@lru_cache(maxsize=3)
def app_icon(variant: AppIconVariant = "opaque") -> QIcon:
    assets = app_icon_assets(variant)
    icon = QIcon(str(assets.svg_path))
    for size, png_path in zip(APP_ICON_SIZES, assets.png_paths):
        if png_path.is_file():
            icon.addFile(str(png_path), QSize(size, size))
    if assets.ico_path is not None and assets.ico_path.is_file():
        icon.addFile(str(assets.ico_path))
    return icon


def apply_application_icon(app: QApplication, variant: AppIconVariant = "opaque") -> QIcon:
    icon = app_icon(variant)
    app.setWindowIcon(icon)
    return icon


def apply_window_icon(window: QWidget, variant: AppIconVariant = "opaque") -> QIcon:
    icon = app_icon(variant)
    window.setWindowIcon(icon)
    return icon


__all__ = [
    "APP_ICON_SIZES",
    "AppIconAssetSet",
    "AppIconVariant",
    "app_icon",
    "app_icon_assets",
    "app_icon_ico_path",
    "app_icon_png_path",
    "app_icon_root",
    "app_icon_svg_path",
    "apply_application_icon",
    "apply_window_icon",
]

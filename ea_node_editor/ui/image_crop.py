from __future__ import annotations

from dataclasses import dataclass
from math import ceil, floor, isfinite
from pathlib import Path
from typing import Any

from PyQt6.QtCore import QByteArray, QBuffer, QIODevice, QRect
from PyQt6.QtGui import QImageReader


@dataclass(frozen=True, slots=True)
class ImageCropResult:
    data: bytes
    width: int
    height: int


class ImageCropError(ValueError):
    pass


def crop_image_file_to_png_bytes(
    source_path: Path,
    crop_rect: dict[str, Any],
) -> ImageCropResult:
    image = _read_image(source_path)
    width = image.width()
    height = image.height()
    if width <= 0 or height <= 0:
        raise ImageCropError("The image source has no readable dimensions.")

    rect = _source_pixel_rect(crop_rect, width, height)
    cropped = image.copy(rect)
    if cropped.isNull():
        raise ImageCropError("The selected crop could not be read from the image.")

    data = _encode_png(cropped)
    if not data:
        raise ImageCropError("The cropped image could not be encoded as PNG.")
    return ImageCropResult(data=data, width=cropped.width(), height=cropped.height())


def crop_rect_is_effective(crop_rect: dict[str, Any]) -> bool:
    x, y, width, height = _normalized_rect_values(crop_rect)
    return (
        abs(x) > 1e-6
        or abs(y) > 1e-6
        or abs(width - 1.0) > 1e-6
        or abs(height - 1.0) > 1e-6
    )


def _read_image(path: Path):
    reader = QImageReader(str(path))
    reader.setAutoTransform(True)
    reader.setDecideFormatFromContent(True)
    image = reader.read()
    if image.isNull():
        raise ImageCropError("The image source could not be loaded.")
    return image


def _source_pixel_rect(crop_rect: dict[str, Any], source_width: int, source_height: int) -> QRect:
    x, y, width, height = _normalized_rect_values(crop_rect)
    left = max(0, min(source_width - 1, floor(x * source_width)))
    top = max(0, min(source_height - 1, floor(y * source_height)))
    right = max(left + 1, min(source_width, ceil((x + width) * source_width)))
    bottom = max(top + 1, min(source_height, ceil((y + height) * source_height)))
    return QRect(left, top, right - left, bottom - top)


def _normalized_rect_values(crop_rect: dict[str, Any]) -> tuple[float, float, float, float]:
    x = _finite_float(crop_rect.get("x"), 0.0)
    y = _finite_float(crop_rect.get("y"), 0.0)
    width = _finite_float(crop_rect.get("width"), 1.0)
    height = _finite_float(crop_rect.get("height"), 1.0)

    x = max(0.0, min(1.0, x))
    y = max(0.0, min(1.0, y))
    width = max(0.0, min(1.0 - x, width))
    height = max(0.0, min(1.0 - y, height))
    if width <= 0.0 or height <= 0.0:
        raise ImageCropError("The selected crop is empty.")
    return x, y, width, height


def _finite_float(value: Any, default: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if isfinite(number) else default


def _encode_png(image) -> bytes:
    payload = QByteArray()
    buffer = QBuffer(payload)
    if not buffer.open(QIODevice.OpenModeFlag.WriteOnly):
        return b""
    try:
        if not image.save(buffer, "PNG"):
            return b""
        return bytes(payload)
    finally:
        buffer.close()


__all__ = [
    "ImageCropError",
    "ImageCropResult",
    "crop_image_file_to_png_bytes",
    "crop_rect_is_effective",
]

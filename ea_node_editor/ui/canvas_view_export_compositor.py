from __future__ import annotations

from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

from PyQt6.QtCore import QRect, QRectF
from PyQt6.QtGui import QImage, QPainter


class CanvasViewExportCompositeError(RuntimeError):
    """Raised when a visible overlay cannot be included in the final PNG."""


def _snapshot_rect(snapshot: Any) -> QRectF:
    rect = getattr(snapshot, "rect", None)
    if rect is None:
        rect = getattr(snapshot, "canvas_rect", None)
    if isinstance(rect, QRectF):
        return QRectF(rect)
    if hasattr(rect, "x") and hasattr(rect, "y") and hasattr(rect, "width") and hasattr(rect, "height"):
        return QRectF(float(rect.x()), float(rect.y()), float(rect.width()), float(rect.height()))
    if isinstance(rect, dict):
        return QRectF(
            float(rect.get("x", 0.0) or 0.0),
            float(rect.get("y", 0.0) or 0.0),
            float(rect.get("width", 0.0) or 0.0),
            float(rect.get("height", 0.0) or 0.0),
        )
    raise CanvasViewExportCompositeError("Overlay snapshot is missing a canvas-relative rect.")


def _crop_rect(value: Any, image_width: int, image_height: int) -> QRect | None:
    if value is None:
        return None
    if isinstance(value, QRect):
        rect = QRect(value)
    elif isinstance(value, dict):
        rect = QRect(
            int(value.get("x", 0) or 0),
            int(value.get("y", 0) or 0),
            int(value.get("width", 0) or 0),
            int(value.get("height", 0) or 0),
        )
    elif all(hasattr(value, name) for name in ("x", "y", "width", "height")):
        rect = QRect(
            int(getattr(value, "x")),
            int(getattr(value, "y")),
            int(getattr(value, "width")),
            int(getattr(value, "height")),
        )
    else:
        return None
    normalized = rect.normalized()
    if normalized.width() <= 0 or normalized.height() <= 0:
        return None
    left = max(0, min(int(image_width), int(normalized.x())))
    top = max(0, min(int(image_height), int(normalized.y())))
    right = max(0, min(int(image_width), int(normalized.x() + normalized.width())))
    bottom = max(0, min(int(image_height), int(normalized.y() + normalized.height())))
    if right <= left or bottom <= top:
        return None
    if left == 0 and top == 0 and right == image_width and bottom == image_height:
        return None
    return QRect(left, top, right - left, bottom - top)


def composite_canvas_view_png(
    *,
    base_png_path: Path | str,
    output_png_path: Path | str,
    canvas_logical_width: float,
    canvas_logical_height: float,
    overlay_snapshots: Iterable[Any],
    capture_overlay_image: Callable[[Any], QImage],
    crop_rect_px: Any | None = None,
) -> Path:
    base_path = Path(base_png_path)
    output_path = Path(output_png_path)
    base_image = QImage(str(base_path))
    if base_image.isNull():
        raise CanvasViewExportCompositeError(f"Could not load canvas base PNG: {base_path}")
    logical_width = float(canvas_logical_width)
    logical_height = float(canvas_logical_height)
    if logical_width <= 0.0 or logical_height <= 0.0:
        raise CanvasViewExportCompositeError("Canvas logical size must be positive.")

    scale_x = float(base_image.width()) / logical_width
    scale_y = float(base_image.height()) / logical_height
    painter = QPainter(base_image)
    try:
        painter.setClipRect(0, 0, base_image.width(), base_image.height())
        for snapshot in overlay_snapshots:
            rect = _snapshot_rect(snapshot)
            if rect.width() <= 0.0 or rect.height() <= 0.0:
                continue
            overlay_image = capture_overlay_image(snapshot)
            if not isinstance(overlay_image, QImage) or overlay_image.isNull():
                owner = str(getattr(snapshot, "owner", "") or "native overlay")
                node_id = str(getattr(snapshot, "node_id", "") or "")
                suffix = f" for node {node_id}" if node_id else ""
                raise CanvasViewExportCompositeError(f"Could not capture {owner} overlay{suffix}.")
            destination = QRectF(
                rect.x() * scale_x,
                rect.y() * scale_y,
                rect.width() * scale_x,
                rect.height() * scale_y,
            )
            painter.drawImage(
                destination,
                overlay_image,
                QRectF(0.0, 0.0, float(overlay_image.width()), float(overlay_image.height())),
            )
    finally:
        painter.end()

    output_image = base_image
    crop = _crop_rect(crop_rect_px, base_image.width(), base_image.height())
    if crop is not None:
        output_image = base_image.copy(crop)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    if not output_image.save(str(output_path), "PNG"):
        raise CanvasViewExportCompositeError(f"Could not save canvas PNG: {output_path}")
    return output_path


__all__ = ["CanvasViewExportCompositeError", "composite_canvas_view_png"]

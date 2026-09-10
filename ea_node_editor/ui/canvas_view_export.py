from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
import math
import re
from pathlib import Path

MAX_EXPORT_SCALE = 4
MAX_EXPORT_SIDE_PX = 16384
MAX_EXPORT_TOTAL_PIXELS = 67108864
DEFAULT_CANVAS_EXPORT_CROP_PADDING_PX = 48.0

_INVALID_FILENAME_CHARS_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]+')
_WHITESPACE_RE = re.compile(r"\s+")
_WINDOWS_RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{index}" for index in range(1, 10)),
    *(f"LPT{index}" for index in range(1, 10)),
}


class CanvasViewExportError(ValueError):
    """Raised when canvas view export inputs cannot produce a valid file."""


@dataclass(frozen=True, slots=True)
class CanvasExportCropRect:
    x: int
    y: int
    width: int
    height: int


def _numeric_value(value: object) -> float | None:
    raw = value() if callable(value) else value
    try:
        resolved = float(raw)
    except (TypeError, ValueError):
        return None
    return resolved if math.isfinite(resolved) else None


def _rect_value(rect: object, name: str) -> float | None:
    if isinstance(rect, Mapping):
        return _numeric_value(rect.get(name))
    attr = getattr(rect, name, None)
    if attr is not None:
        return _numeric_value(attr)
    return None


def canvas_export_crop_rect_for_scene_bounds(
    *,
    scene_bounds: object,
    center_x: object,
    center_y: object,
    zoom: object,
    canvas_logical_width: float,
    canvas_logical_height: float,
    output_pixel_width: int,
    output_pixel_height: int,
    padding_px: float = DEFAULT_CANVAS_EXPORT_CROP_PADDING_PX,
) -> CanvasExportCropRect | None:
    scene_x = _rect_value(scene_bounds, "x")
    scene_y = _rect_value(scene_bounds, "y")
    scene_width = _rect_value(scene_bounds, "width")
    scene_height = _rect_value(scene_bounds, "height")
    view_center_x = _numeric_value(center_x)
    view_center_y = _numeric_value(center_y)
    view_zoom = _numeric_value(zoom)
    logical_width = _numeric_value(canvas_logical_width)
    logical_height = _numeric_value(canvas_logical_height)
    if (
        scene_x is None
        or scene_y is None
        or scene_width is None
        or scene_height is None
        or view_center_x is None
        or view_center_y is None
        or view_zoom is None
        or logical_width is None
        or logical_height is None
    ):
        return None
    if scene_width < 0.0:
        scene_x += scene_width
        scene_width = abs(scene_width)
    if scene_height < 0.0:
        scene_y += scene_height
        scene_height = abs(scene_height)
    if scene_width <= 0.0 or scene_height <= 0.0 or view_zoom <= 0.0:
        return None
    if logical_width <= 0.0 or logical_height <= 0.0:
        return None
    if output_pixel_width <= 0 or output_pixel_height <= 0:
        return None

    half_width = logical_width * 0.5
    half_height = logical_height * 0.5
    left = ((scene_x - view_center_x) * view_zoom) + half_width
    top = ((scene_y - view_center_y) * view_zoom) + half_height
    right = (((scene_x + scene_width) - view_center_x) * view_zoom) + half_width
    bottom = (((scene_y + scene_height) - view_center_y) * view_zoom) + half_height
    if right < left:
        left, right = right, left
    if bottom < top:
        top, bottom = bottom, top

    padding = max(0.0, _numeric_value(padding_px) or 0.0)
    scale_x = float(output_pixel_width) / logical_width
    scale_y = float(output_pixel_height) / logical_height
    left_px = math.floor((left - padding) * scale_x)
    top_px = math.floor((top - padding) * scale_y)
    right_px = math.ceil((right + padding) * scale_x)
    bottom_px = math.ceil((bottom + padding) * scale_y)

    clamped_left = max(0, min(int(output_pixel_width), int(left_px)))
    clamped_top = max(0, min(int(output_pixel_height), int(top_px)))
    clamped_right = max(0, min(int(output_pixel_width), int(right_px)))
    clamped_bottom = max(0, min(int(output_pixel_height), int(bottom_px)))
    width = clamped_right - clamped_left
    height = clamped_bottom - clamped_top
    if width <= 0 or height <= 0:
        return None
    if clamped_left == 0 and clamped_top == 0 and width == output_pixel_width and height == output_pixel_height:
        return None
    return CanvasExportCropRect(clamped_left, clamped_top, width, height)


def _canvas_rect_value(rect: object, name: str) -> float | None:
    value = _rect_value(rect, name)
    if value is not None:
        return value
    attr = getattr(rect, name, None)
    if callable(attr):
        return _numeric_value(attr)
    return None


def _snapshot_canvas_rect(snapshot: object) -> object | None:
    rect = getattr(snapshot, "rect", None)
    if rect is not None:
        return rect
    return getattr(snapshot, "canvas_rect", None)


def canvas_export_crop_rect_with_overlay_snapshots(
    *,
    base_crop_rect: CanvasExportCropRect | None,
    overlay_snapshots: Iterable[object],
    canvas_logical_width: float,
    canvas_logical_height: float,
    output_pixel_width: int,
    output_pixel_height: int,
) -> CanvasExportCropRect | None:
    if base_crop_rect is None:
        return None
    logical_width = _numeric_value(canvas_logical_width)
    logical_height = _numeric_value(canvas_logical_height)
    if (
        logical_width is None
        or logical_height is None
        or logical_width <= 0.0
        or logical_height <= 0.0
        or output_pixel_width <= 0
        or output_pixel_height <= 0
    ):
        return base_crop_rect

    left = int(base_crop_rect.x)
    top = int(base_crop_rect.y)
    right = int(base_crop_rect.x + base_crop_rect.width)
    bottom = int(base_crop_rect.y + base_crop_rect.height)
    scale_x = float(output_pixel_width) / logical_width
    scale_y = float(output_pixel_height) / logical_height
    for snapshot in overlay_snapshots:
        rect = _snapshot_canvas_rect(snapshot)
        if rect is None:
            continue
        x = _canvas_rect_value(rect, "x")
        y = _canvas_rect_value(rect, "y")
        width = _canvas_rect_value(rect, "width")
        height = _canvas_rect_value(rect, "height")
        if x is None or y is None or width is None or height is None:
            continue
        if width < 0.0:
            x += width
            width = abs(width)
        if height < 0.0:
            y += height
            height = abs(height)
        if width <= 0.0 or height <= 0.0:
            continue
        overlay_left = math.floor(x * scale_x)
        overlay_top = math.floor(y * scale_y)
        overlay_right = math.ceil((x + width) * scale_x)
        overlay_bottom = math.ceil((y + height) * scale_y)
        clamped_left = max(0, min(int(output_pixel_width), int(overlay_left)))
        clamped_top = max(0, min(int(output_pixel_height), int(overlay_top)))
        clamped_right = max(0, min(int(output_pixel_width), int(overlay_right)))
        clamped_bottom = max(0, min(int(output_pixel_height), int(overlay_bottom)))
        if clamped_right <= clamped_left or clamped_bottom <= clamped_top:
            continue
        left = min(left, clamped_left)
        top = min(top, clamped_top)
        right = max(right, clamped_right)
        bottom = max(bottom, clamped_bottom)

    left = max(0, min(int(output_pixel_width), int(left)))
    top = max(0, min(int(output_pixel_height), int(top)))
    right = max(0, min(int(output_pixel_width), int(right)))
    bottom = max(0, min(int(output_pixel_height), int(bottom)))
    width = right - left
    height = bottom - top
    if width <= 0 or height <= 0:
        return None
    if left == 0 and top == 0 and width == output_pixel_width and height == output_pixel_height:
        return None
    return CanvasExportCropRect(left, top, width, height)


def normalize_export_scale(scale: object) -> int:
    try:
        normalized = int(scale)
    except (TypeError, ValueError) as exc:
        raise CanvasViewExportError("Export scale must be between 1x and 4x.") from exc
    if normalized < 1 or normalized > MAX_EXPORT_SCALE:
        raise CanvasViewExportError("Export scale must be between 1x and 4x.")
    return normalized


def rounded_export_pixels(value: float) -> int:
    if not math.isfinite(float(value)):
        return 0
    return int(math.floor(max(0.0, float(value)) + 0.5))


def final_export_pixel_size(
    *,
    canvas_logical_width: float,
    canvas_logical_height: float,
    device_pixel_ratio: float,
    scale: int,
) -> tuple[int, int]:
    normalized_scale = normalize_export_scale(scale)
    try:
        dpr = float(device_pixel_ratio)
    except (TypeError, ValueError) as exc:
        raise CanvasViewExportError("Canvas device pixel ratio must be positive.") from exc
    if not math.isfinite(dpr) or dpr <= 0.0:
        raise CanvasViewExportError("Canvas device pixel ratio must be positive.")
    width = rounded_export_pixels(float(canvas_logical_width) * dpr * normalized_scale)
    height = rounded_export_pixels(float(canvas_logical_height) * dpr * normalized_scale)
    validate_export_pixel_size(width, height)
    return width, height


def validate_export_pixel_size(width: int, height: int) -> None:
    if width <= 0 or height <= 0:
        raise CanvasViewExportError("Canvas export size must be positive.")
    if width > MAX_EXPORT_SIDE_PX or height > MAX_EXPORT_SIDE_PX:
        raise CanvasViewExportError(
            f"Canvas export sides must not exceed {MAX_EXPORT_SIDE_PX} px."
        )
    if width * height > MAX_EXPORT_TOTAL_PIXELS:
        raise CanvasViewExportError(
            f"Canvas export must not exceed {MAX_EXPORT_TOTAL_PIXELS} total pixels."
        )


def safe_filename_component(value: object, *, fallback: str = "view", max_length: int = 96) -> str:
    text = _INVALID_FILENAME_CHARS_RE.sub("-", str(value or "").strip())
    text = _WHITESPACE_RE.sub(" ", text).strip(" .")
    text = re.sub(r"-{2,}", "-", text).strip("- ")
    if not text:
        text = fallback
    if text.upper() in _WINDOWS_RESERVED_NAMES:
        text = f"{text}-export"
    if len(text) > max_length:
        text = text[:max_length].rstrip(" .-") or fallback
    return text


def canvas_view_png_stem(workspace_name: object, view_name: object) -> str:
    workspace = safe_filename_component(workspace_name, fallback="workspace")
    view = safe_filename_component(view_name, fallback="view")
    return safe_filename_component(f"{workspace}-{view}", fallback="canvas-view", max_length=140)


def collision_safe_path(
    directory: Path | str,
    stem: str,
    suffix: str,
    *,
    reserved: set[Path] | None = None,
) -> Path:
    output_dir = Path(directory)
    clean_stem = safe_filename_component(stem, fallback="canvas-view", max_length=140)
    normalized_suffix = str(suffix or "").strip() or ".png"
    if not normalized_suffix.startswith("."):
        normalized_suffix = f".{normalized_suffix}"
    reserved_paths = reserved if reserved is not None else set()
    candidate = output_dir / f"{clean_stem}{normalized_suffix}"
    index = 2
    while candidate.exists() or candidate in reserved_paths:
        candidate = output_dir / f"{clean_stem} ({index}){normalized_suffix}"
        index += 1
    reserved_paths.add(candidate)
    return candidate


def canvas_view_png_output_paths(
    *,
    output_dir: Path | str,
    workspace_name: object,
    view_names_by_id: dict[str, object],
) -> dict[str, Path]:
    reserved: set[Path] = set()
    paths: dict[str, Path] = {}
    for view_id, view_name in view_names_by_id.items():
        paths[str(view_id)] = collision_safe_path(
            output_dir,
            canvas_view_png_stem(workspace_name, view_name),
            ".png",
            reserved=reserved,
        )
    return paths


__all__ = [
    "CanvasExportCropRect",
    "CanvasViewExportError",
    "DEFAULT_CANVAS_EXPORT_CROP_PADDING_PX",
    "MAX_EXPORT_SCALE",
    "MAX_EXPORT_SIDE_PX",
    "MAX_EXPORT_TOTAL_PIXELS",
    "canvas_export_crop_rect_for_scene_bounds",
    "canvas_export_crop_rect_with_overlay_snapshots",
    "canvas_view_png_output_paths",
    "canvas_view_png_stem",
    "collision_safe_path",
    "final_export_pixel_size",
    "normalize_export_scale",
    "rounded_export_pixels",
    "safe_filename_component",
    "validate_export_pixel_size",
]

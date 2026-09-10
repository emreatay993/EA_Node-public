# Purpose: Adapt immutable ImageValue previews into the existing viewer preview cache.
# Map: feature_routes/node_execution_visualization
# Tests: tests/test_image_value.py
from __future__ import annotations

import weakref

from PyQt6.QtGui import QImage

from ea_node_editor.runtime_contracts import ImageValue
from ea_node_editor.ui.plot_preview_cache_provider import ViewerPreviewCacheImageProvider

IMAGE_VALUE_PREVIEW_WORKSPACE_ID = "image-value"
_active_provider_ref: weakref.ReferenceType[ViewerPreviewCacheImageProvider] | None = None
_cached_digests: set[str] = set()


def set_active_image_value_preview_provider(
    provider: ViewerPreviewCacheImageProvider | None,
) -> None:
    global _active_provider_ref
    _active_provider_ref = weakref.ref(provider) if provider is not None else None


def image_value_preview_source(value: ImageValue) -> str:
    provider = _active_provider_ref() if _active_provider_ref is not None else None
    if provider is None or type(value) is not ImageValue:
        return ""
    image = QImage.fromData(value.encoded_bytes, "PNG")
    if image.isNull() or image.width() != value.width or image.height() != value.height:
        return ""
    provider.set_preview(
        IMAGE_VALUE_PREVIEW_WORKSPACE_ID,
        value.sha256,
        image,
        signature=value.sha256,
    )
    _cached_digests.add(value.sha256)
    return provider.preview_source(IMAGE_VALUE_PREVIEW_WORKSPACE_ID, value.sha256)


def clear_image_value_previews() -> None:
    provider = _active_provider_ref() if _active_provider_ref is not None else None
    if provider is not None:
        for digest in tuple(_cached_digests):
            provider.clear_preview(IMAGE_VALUE_PREVIEW_WORKSPACE_ID, digest)
    _cached_digests.clear()


__all__ = [
    "IMAGE_VALUE_PREVIEW_WORKSPACE_ID",
    "clear_image_value_previews",
    "image_value_preview_source",
    "set_active_image_value_preview_provider",
]

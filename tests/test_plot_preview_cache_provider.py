from __future__ import annotations

from PyQt6.QtCore import QSize
from PyQt6.QtGui import QColor, QImage

from ea_node_editor.ui.plot_preview_cache_provider import PlotPreviewCacheImageProvider


def _image(color: str) -> QImage:
    image = QImage(5, 3, QImage.Format.Format_ARGB32)
    image.fill(QColor(color))
    return image


def test_plot_preview_cache_provider_serves_revisioned_qimages(qapp) -> None:  # noqa: ANN001
    provider = PlotPreviewCacheImageProvider()

    assert provider.preview_source("workspace one", "node/a") == ""

    original = _image("#3366ff")
    assert provider.set_preview(
        "workspace one",
        "node/a",
        original,
        signature=("line", 1),
    )
    source_v1 = provider.preview_source("workspace one", "node/a")
    assert source_v1.startswith("image://plot-preview-cache/preview?")
    assert "revision=1" in source_v1

    original.fill(QColor("#ff0000"))
    cached_v1, size_v1 = provider.requestImage(source_v1.split("image://plot-preview-cache/", 1)[1], QSize())
    assert size_v1 == QSize(5, 3)
    assert cached_v1.pixelColor(0, 0) == QColor("#3366ff")
    assert provider.preview_signature("workspace one", "node/a") == ("line", 1)

    assert provider.set_preview(
        "workspace one",
        "node/a",
        _image("#33aa55"),
        signature=("line", 2),
    )
    source_v2 = provider.preview_source("workspace one", "node/a")
    assert source_v2 != source_v1
    assert "revision=2" in source_v2
    cached_v2, _size_v2 = provider.requestImage(source_v2.split("image://plot-preview-cache/", 1)[1], QSize())
    assert cached_v2.pixelColor(0, 0) == QColor("#33aa55")

    assert provider.clear_preview("workspace one", "node/a")
    assert provider.preview_source("workspace one", "node/a") == ""


def test_plot_preview_cache_provider_does_not_double_decode_node_ids(qapp) -> None:  # noqa: ANN001
    provider = PlotPreviewCacheImageProvider()

    assert provider.set_preview(
        "workspace one",
        "node/a",
        _image("#ff3333"),
        signature=("line", "slash"),
    )
    assert provider.set_preview(
        "workspace one",
        "node%2Fa",
        _image("#3366ff"),
        signature=("line", "percent"),
    )

    source = provider.preview_source("workspace one", "node%2Fa")
    cached, cached_size = provider.requestImage(source.split("image://plot-preview-cache/", 1)[1], QSize())

    assert cached_size == QSize(5, 3)
    assert cached.pixelColor(0, 0) == QColor("#3366ff")

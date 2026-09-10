from __future__ import annotations

from contextlib import contextmanager
import gc
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import quote

from PyQt6.QtCore import QMarginsF, QRectF, QSize, QUrl
from PyQt6.QtGui import QPainter, QPageLayout, QPageSize, QPdfWriter
from PyQt6.QtWidgets import QApplication

from ea_node_editor.common.artifact_refs import format_managed_artifact_ref
from ea_node_editor.common.artifact_refs import format_staged_artifact_ref
from ea_node_editor.ui import pdf_preview_provider as pdf_preview_provider_module
from ea_node_editor.ui.pdf_preview_provider import (
    LOCAL_PDF_PREVIEW_PROVIDER_ID,
    LocalPdfPreviewImageProvider,
    clamp_pdf_page_number,
    describe_pdf_preview,
    set_pdf_preview_project_context_provider,
)


def _write_pdf(path: Path, *, page_count: int = 1) -> None:
    writer = QPdfWriter(str(path))
    writer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
    writer.setPageMargins(QMarginsF(12, 12, 12, 12), QPageLayout.Unit.Millimeter)
    painter = QPainter(writer)
    for page_index in range(page_count):
        if page_index > 0:
            writer.newPage()
        painter.drawText(
            QRectF(80.0, 120.0, 420.0, 120.0),
            f"PDF page {page_index + 1}",
        )
    painter.end()
    del painter
    del writer
    gc.collect()


@contextmanager
def _pdf_preview_project_context(
    *,
    project_path: Path | None,
    project_metadata: dict[str, object] | None,
):
    set_pdf_preview_project_context_provider(lambda: (project_path, project_metadata))
    try:
        yield
    finally:
        set_pdf_preview_project_context_provider(None)


class PdfPreviewProviderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.app = QApplication.instance() or QApplication([])

    def test_describe_preview_reads_only_requested_page_size_for_large_pdf(self) -> None:
        class _FakePageSize:
            def width(self) -> float:
                return 612.0

            def height(self) -> float:
                return 792.0

        page_size_calls: list[int] = []

        class _FakePdfDocument:
            class Error:
                None_ = "none"

            def __init__(self, _parent) -> None:  # noqa: ANN001
                pass

            def load(self, _path_text: str) -> str:
                return self.Error.None_

            def pageCount(self) -> int:
                return 400

            def pagePointSize(self, page_index: int) -> _FakePageSize:
                page_size_calls.append(page_index)
                return _FakePageSize()

            def close(self) -> None:
                pass

        with tempfile.TemporaryDirectory() as temp_dir:
            pdf_path = Path(temp_dir) / "large.pdf"
            pdf_path.write_bytes(b"%PDF fake")
            pdf_preview_provider_module._cached_pdf_page_count.cache_clear()
            pdf_preview_provider_module._cached_pdf_page_point_size.cache_clear()
            try:
                with patch.object(
                    pdf_preview_provider_module,
                    "QPdfDocument",
                    _FakePdfDocument,
                ):
                    info = pdf_preview_provider_module.describe_pdf_preview(
                        str(pdf_path), 399
                    )
            finally:
                pdf_preview_provider_module._cached_pdf_page_count.cache_clear()
                pdf_preview_provider_module._cached_pdf_page_point_size.cache_clear()

        self.assertEqual(info["state"], "ready")
        self.assertEqual(info["page_count"], 400)
        self.assertEqual(info["resolved_page_number"], 399)
        self.assertEqual(page_size_calls, [398])

    def test_describe_preview_and_provider_render_single_page_preview(self) -> None:
        provider = LocalPdfPreviewImageProvider()
        with tempfile.TemporaryDirectory() as temp_dir:
            pdf_path = Path(temp_dir) / "preview.pdf"
            _write_pdf(pdf_path, page_count=2)

            info = describe_pdf_preview(str(pdf_path), 9)
            self.assertEqual(info["state"], "ready")
            self.assertEqual(info["page_count"], 2)
            self.assertEqual(info["requested_page_number"], 9)
            self.assertEqual(info["resolved_page_number"], 2)
            self.assertTrue(
                str(info["preview_url"]).startswith(
                    f"image://{LOCAL_PDF_PREVIEW_PROVIDER_ID}/"
                )
            )
            self.assertEqual(clamp_pdf_page_number(str(pdf_path), 9), 2)

            image, size = provider.requestImage(
                f"preview?source={quote(str(pdf_path), safe='')}&page=9",
                QSize(220, 220),
            )

        self.assertFalse(image.isNull())
        self.assertGreater(size.width(), 0)
        self.assertGreater(size.height(), 0)
        self.assertLessEqual(size.width(), 220)
        self.assertLessEqual(size.height(), 220)
        paper_pixel = image.pixelColor(0, 0)
        self.assertEqual(paper_pixel.alpha(), 255)
        self.assertGreaterEqual(paper_pixel.red(), 250)
        self.assertGreaterEqual(paper_pixel.green(), 250)
        self.assertGreaterEqual(paper_pixel.blue(), 250)

    def test_provider_uses_default_render_size_when_request_is_unspecified(self) -> None:
        provider = LocalPdfPreviewImageProvider()
        with tempfile.TemporaryDirectory() as temp_dir:
            pdf_path = Path(temp_dir) / "preview.pdf"
            _write_pdf(pdf_path)
            image, size = provider.requestImage(
                f"preview?source={quote(str(pdf_path), safe='')}&page=1",
                QSize(),
            )

        self.assertEqual(image.size(), size)
        self.assertGreater(size.width(), 100)
        self.assertGreater(size.height(), 100)

    def test_describe_preview_and_provider_render_managed_pdf_ref(self) -> None:
        provider = LocalPdfPreviewImageProvider()
        with tempfile.TemporaryDirectory() as temp_dir:
            project_path = Path(temp_dir) / "artifact_demo.cxproj"
            managed_pdf_path = (
                project_path.with_name("artifact_demo.data")
                / "nodes"
                / "Media Panel [11111111]"
                / "in"
                / "media"
                / "preview.pdf"
            )
            managed_pdf_path.parent.mkdir(parents=True, exist_ok=True)
            _write_pdf(managed_pdf_path, page_count=2)
            managed_ref = format_managed_artifact_ref("preview_pdf")

            with _pdf_preview_project_context(
                project_path=project_path,
                project_metadata={
                    "artifact_store": {
                        "artifacts": {
                            "preview_pdf": {
                                "relative_path": (
                                    "nodes/Media Panel [11111111]/in/media/preview.pdf"
                                )
                            },
                        }
                    }
                },
            ):
                info = describe_pdf_preview(managed_ref, 9)
                image, size = provider.requestImage(
                    f"preview?source={quote(managed_ref, safe='')}&page=9",
                    QSize(220, 220),
                )

        self.assertEqual(info["state"], "ready")
        self.assertEqual(info["page_count"], 2)
        self.assertEqual(info["resolved_page_number"], 2)
        self.assertEqual(
            Path(QUrl(info["resolved_source_url"]).toLocalFile()),
            managed_pdf_path,
        )
        self.assertFalse(image.isNull())
        self.assertGreater(size.width(), 0)
        self.assertGreater(size.height(), 0)
        self.assertLessEqual(size.width(), 220)
        self.assertLessEqual(size.height(), 220)

    def test_describe_preview_and_provider_render_staged_pdf_ref(self) -> None:
        provider = LocalPdfPreviewImageProvider()
        with tempfile.TemporaryDirectory() as temp_dir:
            project_path = Path(temp_dir) / "artifact_demo.cxproj"
            staged_pdf_path = (
                project_path.with_name("artifact_demo.data")
                / "nodes"
                / "Media Panel [11111111]"
                / "tmp"
                / "in"
                / "media"
                / "preview.pdf"
            )
            staged_pdf_path.parent.mkdir(parents=True, exist_ok=True)
            _write_pdf(staged_pdf_path, page_count=2)
            staged_ref = format_staged_artifact_ref("preview_pdf")

            with _pdf_preview_project_context(
                project_path=project_path,
                project_metadata={
                    "artifact_store": {
                        "staged": {
                            "preview_pdf": {
                                "relative_path": (
                                    "nodes/Media Panel [11111111]/tmp/in/media/preview.pdf"
                                )
                            },
                        }
                    }
                },
            ):
                info = describe_pdf_preview(staged_ref, 9)
                image, size = provider.requestImage(
                    f"preview?source={quote(staged_ref, safe='')}&page=9",
                    QSize(220, 220),
                )

        self.assertEqual(info["state"], "ready")
        self.assertEqual(info["page_count"], 2)
        self.assertEqual(info["resolved_page_number"], 2)
        self.assertEqual(
            Path(QUrl(info["resolved_source_url"]).toLocalFile()),
            staged_pdf_path,
        )
        self.assertFalse(image.isNull())
        self.assertGreater(size.width(), 0)
        self.assertGreater(size.height(), 0)
        self.assertLessEqual(size.width(), 220)
        self.assertLessEqual(size.height(), 220)

    def test_missing_invalid_and_non_local_sources_return_error_imagery(self) -> None:
        provider = LocalPdfPreviewImageProvider()
        with tempfile.TemporaryDirectory() as temp_dir:
            invalid_path = Path(temp_dir) / "invalid.pdf"
            invalid_path.write_text("not a pdf", encoding="utf-8")
            missing_path = Path(temp_dir) / "missing.pdf"

            for source in (
                str(missing_path),
                str(invalid_path),
                "https://example.com/manual.pdf",
                "docs/manual.pdf",
            ):
                self.assertEqual(describe_pdf_preview(source, 1)["state"], "error")
                image, size = provider.requestImage(
                    f"preview?source={quote(source, safe='')}&page=1",
                    QSize(180, 240),
                )
                self.assertFalse(image.isNull())
                self.assertEqual(size.width(), 180)
                self.assertEqual(size.height(), 240)

    def test_provider_releases_file_handle_after_render(self) -> None:
        provider = LocalPdfPreviewImageProvider()
        with tempfile.TemporaryDirectory() as temp_dir:
            pdf_path = Path(temp_dir) / "handle.pdf"
            renamed_path = Path(temp_dir) / "handle-renamed.pdf"
            _write_pdf(pdf_path)

            image, _size = provider.requestImage(
                f"preview?source={quote(str(pdf_path), safe='')}&page=1",
                QSize(200, 280),
            )
            self.assertFalse(image.isNull())
            pdf_path.rename(renamed_path)
            renamed_path.unlink()


if __name__ == "__main__":
    unittest.main()

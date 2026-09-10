from __future__ import annotations

import json
from pathlib import Path
import re
import shutil
import tempfile
import unittest
from unittest.mock import patch

from PyQt6.QtCore import QSize
from ea_node_editor.ui.media_preview_provider import (
    LocalMediaPreviewImageProvider,
    describe_local_image,
    set_media_preview_project_context_provider,
)


class MediaPanelRendererContractTests(unittest.TestCase):
    def test_generated_js_surface_metric_contract_matches_authoritative_json(
        self,
    ) -> None:
        graph_dir = (
            Path(__file__).resolve().parents[1]
            / "ea_node_editor"
            / "ui_qml"
            / "components"
            / "graph"
        )
        json_payload = json.loads(
            (graph_dir / "GraphNodeSurfaceMetricContract.json").read_text(
                encoding="utf-8"
            )
        )
        js_text = (graph_dir / "GraphNodeSurfaceMetricContract.js").read_text(
            encoding="utf-8"
        )
        match = re.search(
            r"var SURFACE_METRIC_CONTRACT = (\{.*\});\s*function contract",
            js_text,
            re.DOTALL,
        )

        self.assertIsNotNone(match)
        assert match is not None
        self.assertEqual(json.loads(match.group(1)), json_payload)

    def test_unified_renderers_keep_media_specific_lifecycle_guards(self) -> None:
        passive_root = (
            Path(__file__).resolve().parents[1]
            / "ea_node_editor"
            / "ui_qml"
            / "components"
            / "graph"
            / "passive"
        )
        image_source = (passive_root / "GraphMediaImageRenderer.qml").read_text(
            encoding="utf-8"
        )
        image_viewport_source = (
            passive_root / "GraphMediaImageViewport.qml"
        ).read_text(encoding="utf-8")
        video_source = (passive_root / "GraphMediaVideoRenderer.qml").read_text(
            encoding="utf-8"
        )
        fullscreen_video_source = (
            passive_root / "GraphMediaVideoFullscreenRenderer.qml"
        ).read_text(encoding="utf-8")
        video_playback_core_source = (
            passive_root / "GraphMediaVideoPlaybackCore.qml"
        ).read_text(encoding="utf-8")

        self.assertIn("sourceInputExposed || !cropToolAvailable", image_source)
        self.assertIn("root.surface.animationShouldPlay", image_viewport_source)
        self.assertIn("property bool rendererReleased", video_source)
        self.assertIn("sourceInputExposed || !localSourceActive", video_source)
        self.assertIn("request_create_video_frame_image_node", video_source)
        self.assertIn("function rewindToStart()", fullscreen_video_source)
        self.assertIn("sourceInputExposed", fullscreen_video_source)
        self.assertNotIn("MediaPlayer {", video_source)
        self.assertNotIn("MediaPlayer {", fullscreen_video_source)
        self.assertEqual(video_playback_core_source.count("MediaPlayer {"), 1)


class LocalMediaPreviewProviderTests(unittest.TestCase):
    def test_describe_local_image_classifies_static_animated_and_corrupt_fixtures(
        self,
    ) -> None:
        fixture_root = Path(__file__).resolve().parent / "fixtures" / "media"

        animated_gif = describe_local_image(str(fixture_root / "animated-small.gif"))
        large_gif = describe_local_image(str(fixture_root / "animated-large.gif"))
        single_frame = describe_local_image(str(fixture_root / "single-frame.gif"))
        animated_webp = describe_local_image(str(fixture_root / "animated.webp"))
        corrupt = describe_local_image(str(fixture_root / "corrupt.gif"))
        missing = describe_local_image(str(fixture_root / "missing.gif"))
        placeholder = describe_local_image("")

        self.assertEqual(animated_gif["state"], "ready")
        self.assertEqual(animated_gif["format"], "gif")
        self.assertEqual(animated_gif["frame_count"], 3)
        self.assertTrue(animated_gif["animation_supported"])
        self.assertTrue(animated_gif["is_animated"])
        self.assertTrue(animated_gif["resolved_source_url"].startswith("file:///"))
        self.assertEqual(
            (animated_gif["source_pixel_width"], animated_gif["source_pixel_height"]),
            (24, 18),
        )
        self.assertEqual(large_gif["frame_count"], 4)
        self.assertEqual(
            (large_gif["source_pixel_width"], large_gif["source_pixel_height"]),
            (1600, 1200),
        )
        self.assertEqual(single_frame["state"], "ready")
        self.assertEqual(single_frame["format"], "gif")
        self.assertEqual(single_frame["frame_count"], 1)
        self.assertFalse(single_frame["is_animated"])
        self.assertEqual(animated_webp["state"], "ready")
        self.assertEqual(animated_webp["format"], "webp")
        self.assertEqual(animated_webp["frame_count"], 3)
        self.assertTrue(animated_webp["animation_supported"])
        self.assertTrue(animated_webp["is_animated"])
        self.assertEqual(corrupt["state"], "error")
        self.assertFalse(corrupt["is_animated"])
        self.assertTrue(corrupt["message"])
        self.assertEqual(missing["state"], "error")
        self.assertEqual(placeholder["state"], "placeholder")

    def test_describe_local_image_resolves_managed_animated_media_to_file_url(
        self,
    ) -> None:
        fixture = (
            Path(__file__).resolve().parent
            / "fixtures"
            / "media"
            / "animated-small.gif"
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            project_path = Path(temp_dir) / "animated-project.cxproj"
            managed_path = (
                project_path.with_name("animated-project.data")
                / "nodes"
                / "Media Panel [11111111]"
                / "in"
                / "media"
                / "managed.gif"
            )
            managed_path.parent.mkdir(parents=True)
            shutil.copyfile(fixture, managed_path)
            set_media_preview_project_context_provider(
                lambda: (
                    project_path,
                    {
                        "artifact_store": {
                            "artifacts": {
                                "managed_animation": {
                                    "relative_path": (
                                        "nodes/Media Panel [11111111]/in/media/managed.gif"
                                    )
                                },
                            }
                        }
                    },
                )
            )
            try:
                description = describe_local_image("saved://managed_animation")
            finally:
                set_media_preview_project_context_provider(None)

        self.assertEqual(description["state"], "ready")
        self.assertTrue(description["is_animated"])
        self.assertEqual(description["frame_count"], 3)
        self.assertTrue(description["resolved_source_url"].startswith("file:///"))
        self.assertIn("animated-project.data/nodes/", description["resolved_source_url"])

    def test_provider_enables_auto_transform_for_local_images(self) -> None:
        calls: list[tuple[str, object]] = []

        class FakeReader:
            def __init__(self, filename: str) -> None:
                calls.append(("init", filename))

            def setAutoTransform(self, value: bool) -> None:
                calls.append(("setAutoTransform", value))

            def setDecideFormatFromContent(self, value: bool) -> None:
                calls.append(("setDecideFormatFromContent", value))

            def read(self):
                calls.append(("read", None))
                from PyQt6.QtGui import QColor, QImage

                image = QImage(8, 6, QImage.Format.Format_ARGB32)
                image.fill(QColor("#2c85bf"))
                return image

        provider = LocalMediaPreviewImageProvider()
        with (
            patch("ea_node_editor.ui.media_preview_provider.QImageReader", FakeReader),
            patch(
                "ea_node_editor.ui.media_preview_provider.Path.exists",
                return_value=True,
            ),
            patch(
                "ea_node_editor.ui.media_preview_provider.Path.is_file",
                return_value=True,
            ),
        ):
            image, size = provider.requestImage(
                "preview?source=file%3A%2F%2F%2FC%3A%2Ftmp%2Forientation-test.jpg",
                QSize(),
            )

        self.assertFalse(image.isNull())
        self.assertEqual(size.width(), 8)
        self.assertEqual(size.height(), 6)
        self.assertIn(("setAutoTransform", True), calls)
        self.assertIn(("setDecideFormatFromContent", True), calls)
        self.assertIn(("read", None), calls)


if __name__ == "__main__":
    unittest.main()

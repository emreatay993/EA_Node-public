from __future__ import annotations

import subprocess
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

from ea_node_editor.ui.video_trim import trim_video_clip


class VideoTrimTests(TestCase):
    def _source(self) -> Path:
        path = Path(self._testMethodName).with_suffix(".mp4")
        path.write_bytes(b"source video")
        self.addCleanup(lambda: path.unlink(missing_ok=True))
        return path

    def test_trim_video_clip_uses_fast_copy_first(self) -> None:
        source_path = self._source()
        calls: list[list[str]] = []

        def fake_run(command: list[str], *, timeout_seconds: int) -> subprocess.CompletedProcess[str]:
            del timeout_seconds
            calls.append(command)
            Path(command[-1]).write_bytes(b"trimmed")
            return subprocess.CompletedProcess(command, 0, "", "")

        with (
            patch("ea_node_editor.ui.video_trim._ffmpeg_executable", return_value="ffmpeg"),
            patch("ea_node_editor.ui.video_trim._run_ffmpeg", side_effect=fake_run),
        ):
            result = trim_video_clip(source_path=source_path, start_ms=1000, end_ms=4500)

        self.assertTrue(result.success)
        self.assertEqual(result.mode_used, "fast_copy")
        self.assertEqual(result.data, b"trimmed")
        self.assertEqual(len(calls), 1)
        self.assertIn("-c", calls[0])
        self.assertIn("copy", calls[0])
        self.assertIn("+faststart", calls[0])

    def test_trim_video_clip_falls_back_to_precise_encode(self) -> None:
        source_path = self._source()
        calls: list[list[str]] = []

        def fake_run(command: list[str], *, timeout_seconds: int) -> subprocess.CompletedProcess[str]:
            del timeout_seconds
            calls.append(command)
            if len(calls) == 1:
                return subprocess.CompletedProcess(command, 1, "", "cannot copy")
            Path(command[-1]).write_bytes(b"precise")
            return subprocess.CompletedProcess(command, 0, "", "")

        with (
            patch("ea_node_editor.ui.video_trim._ffmpeg_executable", return_value="ffmpeg"),
            patch("ea_node_editor.ui.video_trim._run_ffmpeg", side_effect=fake_run),
        ):
            result = trim_video_clip(source_path=source_path, start_ms=2500, end_ms=5750)

        self.assertTrue(result.success)
        self.assertEqual(result.mode_used, "precise")
        self.assertEqual(result.data, b"precise")
        self.assertEqual(len(calls), 2)
        self.assertIn("-c:v", calls[1])
        self.assertIn("libx264", calls[1])
        self.assertIn("-c:a", calls[1])
        self.assertIn("aac", calls[1])

    def test_trim_video_clip_rejects_invalid_range(self) -> None:
        source_path = self._source()

        result = trim_video_clip(source_path=source_path, start_ms=3000, end_ms=3000)

        self.assertFalse(result.success)
        self.assertEqual(result.error_code, "invalid_clip_range")

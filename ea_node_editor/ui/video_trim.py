from __future__ import annotations

import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot


@dataclass(frozen=True, slots=True)
class VideoTrimResult:
    success: bool
    data: bytes = b""
    mode_used: str = ""
    error_code: str = ""
    message: str = ""
    diagnostics: str = ""


class VideoTrimWorker(QObject):
    finished = pyqtSignal(str, object)

    def __init__(
        self,
        *,
        request_id: str,
        source_path: Path,
        start_ms: int,
        end_ms: int,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._request_id = str(request_id or "")
        self._source_path = Path(source_path)
        self._start_ms = max(0, int(start_ms or 0))
        self._end_ms = max(0, int(end_ms or 0))

    @pyqtSlot()
    def run(self) -> None:
        self.finished.emit(
            self._request_id,
            trim_video_clip(
                source_path=self._source_path,
                start_ms=self._start_ms,
                end_ms=self._end_ms,
            ),
        )


def trim_video_clip(*, source_path: Path, start_ms: int, end_ms: int) -> VideoTrimResult:
    path = Path(source_path)
    if not path.exists() or not path.is_file():
        return _failure("source_unavailable", "The source video file could not be found.")
    start = max(0, int(start_ms or 0))
    end = max(0, int(end_ms or 0))
    if end <= start:
        return _failure("invalid_clip_range", "Set a clip out point after the clip in point.")

    ffmpeg_path = _ffmpeg_executable()
    if not ffmpeg_path:
        return _failure("ffmpeg_unavailable", "Bundled ffmpeg is not available.")

    duration_seconds = max(0.001, (end - start) / 1000.0)
    attempts = (
        ("fast_copy", _fast_copy_args(ffmpeg_path, path, start / 1000.0, duration_seconds)),
        ("precise", _precise_args(ffmpeg_path, path, start / 1000.0, duration_seconds)),
    )
    diagnostics: list[str] = []
    for mode, args in attempts:
        output_path = Path(tempfile.gettempdir()) / f"corex-video-trim-{uuid4().hex}.mp4"
        command = [*args, str(output_path)]
        result = _run_ffmpeg(command, timeout_seconds=_timeout_seconds(duration_seconds))
        if result.returncode == 0 and output_path.exists() and output_path.stat().st_size > 0:
            try:
                return VideoTrimResult(
                    success=True,
                    data=output_path.read_bytes(),
                    mode_used=mode,
                )
            except OSError as exc:
                return _failure("output_unwritable", str(exc) or "The trimmed video could not be read.")
            finally:
                _unlink_quietly(output_path)
        diagnostics.append(f"{mode}: {_stderr_tail(result.stderr)}")
        _unlink_quietly(output_path)

    return _failure(
        "ffmpeg_failed",
        "The selected video range could not be trimmed.",
        diagnostics="\n".join(item for item in diagnostics if item.strip()),
    )


def _ffmpeg_executable() -> str:
    try:
        import imageio_ffmpeg  # type: ignore[import-not-found]

        return str(imageio_ffmpeg.get_ffmpeg_exe() or "")
    except Exception:
        return ""


def _fast_copy_args(ffmpeg_path: str, source_path: Path, start_seconds: float, duration_seconds: float) -> list[str]:
    return [
        ffmpeg_path,
        "-hide_banner",
        "-nostdin",
        "-y",
        "-ss",
        _seconds_arg(start_seconds),
        "-i",
        str(source_path),
        "-t",
        _seconds_arg(duration_seconds),
        "-map",
        "0:v:0",
        "-map",
        "0:a?",
        "-c",
        "copy",
        "-avoid_negative_ts",
        "make_zero",
        "-movflags",
        "+faststart",
    ]


def _precise_args(ffmpeg_path: str, source_path: Path, start_seconds: float, duration_seconds: float) -> list[str]:
    return [
        ffmpeg_path,
        "-hide_banner",
        "-nostdin",
        "-y",
        "-ss",
        _seconds_arg(start_seconds),
        "-i",
        str(source_path),
        "-t",
        _seconds_arg(duration_seconds),
        "-map",
        "0:v:0",
        "-map",
        "0:a?",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "18",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-movflags",
        "+faststart",
    ]


def _run_ffmpeg(command: list[str], *, timeout_seconds: int) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=max(5, int(timeout_seconds)),
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        return subprocess.CompletedProcess(
            args=command,
            returncode=124,
            stdout=str(exc.stdout or ""),
            stderr=str(exc.stderr or "ffmpeg timed out."),
        )
    except OSError as exc:
        return subprocess.CompletedProcess(
            args=command,
            returncode=127,
            stdout="",
            stderr=str(exc),
        )


def _seconds_arg(value: float) -> str:
    return f"{max(0.0, float(value)):.3f}"


def _timeout_seconds(duration_seconds: float) -> int:
    return int(max(30.0, min(3600.0, duration_seconds * 6.0 + 30.0)))


def _stderr_tail(value: object, *, limit: int = 1200) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return text[-limit:]


def _failure(code: str, message: str, *, diagnostics: str = "") -> VideoTrimResult:
    return VideoTrimResult(
        success=False,
        error_code=str(code or "failed"),
        message=str(message or "Video trim failed."),
        diagnostics=_stderr_tail(diagnostics),
    )


def _unlink_quietly(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


__all__ = ["VideoTrimResult", "VideoTrimWorker", "trim_video_clip"]

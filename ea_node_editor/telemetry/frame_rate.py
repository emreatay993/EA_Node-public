from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass


@dataclass(slots=True, frozen=True)
class FrameRateSample:
    fps: float
    sample_count: int
    frame_interval_ms_without_readback: float = 0.0


class FrameRateSampler:
    def __init__(self, window_seconds: float = 1.0) -> None:
        self._window_seconds = max(0.1, float(window_seconds))
        self._frame_times: deque[float] = deque()

    def record_frame(self, timestamp: float | None = None) -> None:
        now = time.monotonic() if timestamp is None else float(timestamp)
        self._frame_times.append(now)
        self._prune(now)

    def snapshot(self, timestamp: float | None = None) -> FrameRateSample:
        now = time.monotonic() if timestamp is None else float(timestamp)
        self._prune(now)
        if len(self._frame_times) < 2:
            return FrameRateSample(fps=0.0, sample_count=len(self._frame_times))
        span = self._frame_times[-1] - self._frame_times[0]
        if span <= 1e-9:
            return FrameRateSample(fps=0.0, sample_count=len(self._frame_times))
        frame_interval_ms = (span / float(len(self._frame_times) - 1)) * 1000.0
        return FrameRateSample(
            fps=float((len(self._frame_times) - 1) / span),
            sample_count=len(self._frame_times),
            frame_interval_ms_without_readback=float(frame_interval_ms),
        )

    def _prune(self, now: float) -> None:
        cutoff = float(now) - self._window_seconds
        while self._frame_times and self._frame_times[0] < cutoff:
            self._frame_times.popleft()

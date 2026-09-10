"""Worker pool for tabular preview resolution off the UI thread.

Cold tabular previews need the managed parquet cache built first — too slow
for the UI thread, which instead receives a ``loading`` payload (see
``TabularCacheNotReadyError``). Callers schedule the same provider call here;
the provider's session/inline caches absorb the result, and ``job_finished``
tells the surface to re-describe (now a warm cache hit).

Jobs are deduplicated by key and run on a single worker thread so concurrent
conversions of the same gigabyte source never race.
"""
from __future__ import annotations

from typing import Any, Callable

from PyQt6.QtCore import QObject, QRunnable, QThreadPool, pyqtSignal


class _JobSignals(QObject):
    finished = pyqtSignal(str, str)
    """(job_key, error_text)"""


class _JobRunnable(QRunnable):
    def __init__(self, signals: _JobSignals, job_key: str, fn: Callable[[], Any]) -> None:
        super().__init__()
        self._signals = signals
        self._job_key = job_key
        self._fn = fn

    def run(self) -> None:  # noqa: D102 - QRunnable contract
        try:
            self._fn()
            error = ""
        except Exception as exc:  # noqa: BLE001 - reported via the signal
            error = str(exc)
        self._signals.finished.emit(self._job_key, error)


class TabularPreviewWorkerPool(QObject):
    """Deduplicated single-worker job pool with queued completion signals."""

    job_finished = pyqtSignal(str, str)
    """(job_key, error_text) — emitted on the pool's thread affinity (UI)."""

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._thread_pool = QThreadPool(self)
        self._thread_pool.setMaxThreadCount(1)
        self._signals = _JobSignals(self)
        self._signals.finished.connect(self._on_job_finished)
        self._in_flight: set[str] = set()
        self._shutdown = False

    def schedule(self, job_key: str, fn: Callable[[], Any]) -> bool:
        """Run ``fn`` on the worker unless an identical job is in flight."""

        normalized = str(job_key)
        if self._shutdown or not normalized or normalized in self._in_flight:
            return False
        self._in_flight.add(normalized)
        self._thread_pool.start(_JobRunnable(self._signals, normalized, fn))
        return True

    def in_flight(self, job_key: str) -> bool:
        return str(job_key) in self._in_flight

    def shutdown(self) -> None:
        self._shutdown = True
        self._thread_pool.clear()
        self._thread_pool.waitForDone(2000)

    def _on_job_finished(self, job_key: str, error: str) -> None:
        self._in_flight.discard(job_key)
        if not self._shutdown:
            self.job_finished.emit(job_key, error)


__all__ = ["TabularPreviewWorkerPool"]

from __future__ import annotations

import time
from pathlib import Path

import pytest
from PyQt6.QtWidgets import QApplication

import ea_node_editor.addons.tabular_data.loader_cache_service as loader_module
from ea_node_editor.ui.tabular_preview_async import TabularPreviewWorkerPool
from ea_node_editor.ui.tabular_preview_provider import TabularPreviewProvider


def _wait_for(condition, *, timeout_s: float = 20.0) -> bool:  # noqa: ANN001
    app = QApplication.instance()
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        app.processEvents()
        if condition():
            return True
        time.sleep(0.01)
    return False


def test_worker_pool_dedupes_in_flight_jobs() -> None:
    pool = TabularPreviewWorkerPool()
    finished: list[tuple[str, str]] = []
    pool.job_finished.connect(lambda key, error: finished.append((key, error)))
    started = []

    def slow_job() -> None:
        started.append(time.monotonic())
        time.sleep(0.2)

    try:
        assert pool.schedule("job", slow_job) is True
        assert pool.schedule("job", slow_job) is False  # dedup while in flight
        assert pool.in_flight("job") is True
        assert _wait_for(lambda: finished and not pool.in_flight("job"))
        assert len(started) == 1
        assert finished == [("job", "")]

        # After completion the same key schedules again.
        assert pool.schedule("job", lambda: None) is True
        assert _wait_for(lambda: len(finished) == 2)
    finally:
        pool.shutdown()


def test_worker_pool_reports_job_errors() -> None:
    pool = TabularPreviewWorkerPool()
    finished: list[tuple[str, str]] = []
    pool.job_finished.connect(lambda key, error: finished.append((key, error)))

    def failing_job() -> None:
        raise RuntimeError("boom")

    try:
        assert pool.schedule("bad", failing_job) is True
        assert _wait_for(lambda: bool(finished))
        assert finished[0][0] == "bad"
        assert "boom" in finished[0][1]
    finally:
        pool.shutdown()


def test_cold_describe_returns_loading_then_warm_ready(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """UI-thread describes of large cold sources go async end-to-end."""

    source = tmp_path / "big.csv"
    lines = ["time,value"]
    lines.extend(f"{index},{index * 0.5}" for index in range(2000))
    source.write_text("\n".join(lines) + "\n", encoding="utf-8")

    # Force the "large file" policy: nothing converts inline on the UI thread.
    monkeypatch.setattr(loader_module, "TABULAR_DATA_INLINE_CONVERSION_BYTES", 0)
    service = loader_module.shared_tabular_loader_cache_service()
    monkeypatch.setattr(service, "ui_thread_conversion_allowed", False)

    provider = TabularPreviewProvider()
    properties = {"path": str(source)}

    cold = provider.describe_preview(properties, {"row_limit": 5}, mode="inline")
    assert cold["state"] == "loading"

    pool = TabularPreviewWorkerPool()
    finished: list[str] = []
    pool.job_finished.connect(lambda key, error: finished.append(error))
    try:
        assert pool.schedule(
            "warm",
            lambda: provider.describe_preview(properties, {"row_limit": 5}, mode="inline"),
        )
        assert _wait_for(lambda: bool(finished))
        assert finished == [""]
    finally:
        pool.shutdown()

    warm = provider.describe_preview(properties, {"row_limit": 5}, mode="inline")
    assert warm["state"] == "ready"
    assert len(warm["window"]["rows"]) == 5
    assert warm["window"]["total_rows"] == 2000

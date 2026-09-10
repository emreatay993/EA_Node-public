from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from ea_node_editor.ui.perf.engineering_viewer_benchmark import (
    _write_reports,
    evaluate_metrics,
)


def _passing_metrics() -> dict[str, object]:
    return {
        "interaction_frame_p95_ms": 20.0,
        "detail_restore_ms": 180.0,
        "warm_coarse_frame_ms": 900.0,
        "ui_thread_stall_max_ms": 10.0,
        "released_on_close": True,
    }


def test_acceptance_requires_display_attached_windows_d3d11() -> None:
    with patch("platform.system", return_value="Windows"):
        accepted = evaluate_metrics(
            _passing_metrics(),
            display_attached=True,
            graphics_api="Direct3D11Rhi",
        )
        offscreen = evaluate_metrics(
            _passing_metrics(),
            display_attached=False,
            graphics_api="Direct3D11Rhi",
        )

    assert accepted["status"] == "PASS"
    assert accepted["acceptance_allowed"] is True
    assert offscreen["status"] == "FAIL"
    assert offscreen["acceptance_allowed"] is False


def test_report_writes_json_and_markdown(tmp_path: Path) -> None:
    report = {
        "environment": {"qt_platform": "windows", "graphics_api": "Direct3D11Rhi"},
        "fixtures": {"primary_cells": 10, "overlay_cells": 5},
        "acceptance": evaluate_metrics(
            _passing_metrics(),
            display_attached=False,
            graphics_api="Direct3D11Rhi",
        ),
    }

    json_path, markdown_path = _write_reports(report, tmp_path)

    assert json_path.is_file()
    assert markdown_path.is_file()
    assert "Regression evidence only" in markdown_path.read_text(encoding="utf-8")

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
RUNNER = REPO_ROOT / "mockups" / "docx_rendering_comparison" / "run.py"


pytestmark = pytest.mark.gui


def test_docx_rendering_comparison_single_renderer_smoke(tmp_path: Path) -> None:
    pytest.importorskip("docx")
    pytest.importorskip("PIL")
    pytest.importorskip("fitz")
    pytest.importorskip("PyQt6.QtWebEngineCore")

    output_dir = tmp_path / "docx_rendering"
    env = os.environ.copy()
    env["QT_QPA_PLATFORM"] = "offscreen"
    env.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", "--disable-gpu --no-sandbox")

    result = subprocess.run(
        [
            sys.executable,
            str(RUNNER),
            "--only",
            "python_docx_html_qt",
            "--output-dir",
            str(output_dir),
            "--timeout",
            "60",
        ],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        timeout=90,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads((output_dir / "report.json").read_text(encoding="utf-8"))
    assert [item["name"] for item in report["results"]] == ["python_docx_html_qt"]
    renderer = report["results"][0]
    assert renderer["status"] == "ok"
    assert (output_dir / "comparison.html").exists()

    for relative_path in list(renderer["artifacts"].values()) + renderer["pages"]:
        assert (output_dir / relative_path).exists(), relative_path

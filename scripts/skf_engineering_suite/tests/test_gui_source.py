from __future__ import annotations

import ast
from pathlib import Path


def test_gui_source_is_valid_and_contains_expected_workspaces() -> None:
    path = Path(__file__).parents[1] / "skfcalc" / "gui.py"
    source = path.read_text(encoding="utf-8")
    ast.parse(source)
    assert "class MainWindow" in source
    assert "Batch operating map" in source
    assert "Calibration and validation" in source
    assert "Four-node conductances" in source
    assert "PyQt6" in source

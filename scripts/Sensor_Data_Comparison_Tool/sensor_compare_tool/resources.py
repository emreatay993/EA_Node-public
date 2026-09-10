from __future__ import annotations

from pathlib import Path


PACKAGE_ROOT = Path(__file__).resolve().parent
TOOL_ROOT = PACKAGE_ROOT.parent
HELP_PDF = TOOL_ROOT / "Help_Doc_Statistical_Metrics.pdf"
MOCK_INPUTS = TOOL_ROOT / "mock_inputs"


def help_pdf_path() -> Path:
    return HELP_PDF


def mock_input_path(filename: str) -> Path:
    return MOCK_INPUTS / filename

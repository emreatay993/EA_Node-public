"""Dependency-aware GUI launcher."""

from __future__ import annotations

import multiprocessing
import sys


def _load_main():
    try:
        from skfcalc.gui import main
    except ModuleNotFoundError as exc:
        missing = exc.name or "a required package"
        if missing.startswith("PyQt6"):
            print(
                "PyQt6 is not installed in this Python environment.\n"
                "Run setup_windows.bat, or activate the virtual environment and run:\n"
                "    python -m pip install -e .\n",
                file=sys.stderr,
            )
        else:
            print(f"Missing dependency: {missing}. Run setup_windows.bat.", file=sys.stderr)
        raise SystemExit(2) from exc
    return main


if __name__ == "__main__":
    multiprocessing.freeze_support()
    _load_main()()

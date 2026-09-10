#!/usr/bin/env python3
r"""Print environment details for comparing Model Viewer failures across machines.

Run with the interpreter used to launch COREX, for example::

    .\venv\Scripts\python.exe .\scripts\diagnose_viewer_environment.py

Uses only the standard library. Does not import COREX or native viewer modules,
install packages, launch a GUI, or modify configuration.
"""

from __future__ import annotations

from importlib import metadata
from pathlib import Path
import platform
import subprocess
import sys
import sysconfig


REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_NAMES = (
    "corex-node-editor",
    "numpy",
    "scipy",
    "pyvista",
    "pyvistaqt",
    "vtk",
    "PyQt6",
    "PyQt6-Qt6",
    "PyQt6-sip",
    "cadquery-ocp-novtk",
    "cadquery-ocp",
)


def run_check(command: list[str]) -> tuple[int | None, str]:
    """Capture a read-only command without losing the rest of the report."""
    try:
        result = subprocess.run(
            command,
            cwd=REPO_ROOT,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return None, "Unavailable: command timed out after 30 seconds."
    except OSError as exc:
        return None, f"Unavailable: {exc}"
    return result.returncode, result.stdout.strip()


def main() -> int:
    print("COREX Model Viewer environment report")
    print(f"Python executable: {sys.executable}")
    print(f"Python version: {sys.version.replace(chr(10), ' ')}")
    print(f"Platform: {platform.platform()}")
    print(f"Architecture: {platform.machine()} ({64 if sys.maxsize > 2**32 else 32}-bit)")
    print(f"Free-threaded build: {bool(sysconfig.get_config_var('Py_GIL_DISABLED'))}")

    print("\nInstalled package versions:")
    for name in PACKAGE_NAMES:
        try:
            version = metadata.version(name)
        except metadata.PackageNotFoundError:
            version = "not installed"
        print(f"  {name}: {version}")
    print("  cadquery-ocp may be absent when cadquery-ocp-novtk is installed.")

    print("\nRepository revision:")
    git_code, git_output = run_check(["git", "rev-parse", "--short", "HEAD"])
    print(git_output or "No Git output.")
    print(f"Git exit code: {git_code if git_code is not None else 'unavailable'}")

    print("\npip check (using the Python executable above):", flush=True)
    pip_code, pip_output = run_check([sys.executable, "-m", "pip", "check"])
    print(pip_output or "No pip output.")
    print(f"pip check exit code: {pip_code if pip_code is not None else 'unavailable'}")
    print("\nThis report collects environment details; it does not test rendering.")
    return 0 if pip_code == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())

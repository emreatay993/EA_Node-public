# Verification Runner

## Purpose
Use this for verification modes, pytest defaults, xdist behavior, summarized output, and choosing focused tests.

## Start Here
- `scripts/run_verification.py`
- `scripts/verification_manifest.py`
- `ea_node_editor/pytest_defaults.py`
- `tests/test_run_verification.py`
- `tests/conftest.py`

## Common Changes
- Update the manifest and tests together when verification mode facts change.
- Prefer `--summarize-output` for broad agent-run verification.
- Use narrow route-owned tests before full verification.
- Keep xdist-sensitive fast targets in the manifest-owned `fast.serial.pytest`
  phase instead of letting them run in the `fast.pytest` xdist phase.
- Real scientific process/external transport lives in `tests/test_scientific_worker_transport.py`
  and runs in the same `fast.serial.pytest` phase as the existing ProcessClientTests;
  it remains part of fast/full coverage, with unchanged success and timeout assertions.
- Keep the outer shell-isolation phase capped by its manifest-owned `worker_cap`
  (currently four); each isolated child remains serial.
- Keep native/backend benchmark workbenches such as `tests/test_tabular_benchmark_workbench.py` in slow or direct serial proof lanes rather than the fast xdist slice.
- Keep `gui.qml_quick` first in both `gui` and `full`; it runs the authoritative
  pure-QML `tests/qml_quick` directory before parallel Python GUI pytest and
  `gui.serial.pytest`. Keep only the proven Windows Qt/xdist-contention targets
  in that serial phase: one DOCX selector and `tests/test_viewer_surface_contract.py`;
  graph-surface and Media Panel lock coverage remains in the parallel GUI/QML
  lanes. All other GUI tests remain parallel.
  `fast` and `slow` must not resolve or require the external Qt SDK.
- Discover `qmltestrunner` from explicit `QT_ROOT/bin` first, otherwise from
  `PATH`. Validate the sibling `qtpaths6`/`qtpaths` Qt major/minor against the
  project PyQt runtime, allow patch drift, and fail real `gui`/`full` runs on
  missing or mismatched tooling. Keep `--dry-run` usable through its placeholder
  command and setup notice.
- The repository has no tracked CI workflow. External jobs that run `gui` or
  `full` must provision the matching Qt Quick Test SDK; do not add a Python
  package, wrapper, CMake target, or custom C++ harness for this phase.

## Focused Verification
```powershell
.\venv\Scripts\python.exe -m pytest tests/test_run_verification.py --ignore=venv -q
.\venv\Scripts\python.exe .\scripts\run_verification.py --mode fast --dry-run
.\venv\Scripts\python.exe .\scripts\run_verification.py --mode gui --dry-run
.\venv\Scripts\python.exe .\scripts\run_verification.py --mode full --dry-run
```

## Update Triggers
Update when verification commands, mode composition, pytest default behavior, or runner output policy changes.

# Build and verification status

Release: **1.0.0**  
Build date: **2026-08-19**

Automated verification in the build environment:

- `43 passed` with `pytest`.
- All 10 bearing-family solvers converged in smoke tests.
- Original deep-groove one-node regression case reproduced to the stored tolerance.
- Four-node energy balance, seal, drag, life, JSON round-trip, batch, calibration recovery, HTML report and Numba parity checks passed.
- The 100,000-point warm Numba DGBB one-node benchmark completed at approximately 1.04 million cases/s in this build environment; the full solver benchmark was approximately 1,020 cases/s.
- PyQt6 source parsed and byte-compiled; the GUI was not launched in the build container because a Qt binding/runtime was not installed there.

The GUI should be runtime-smoke-tested on the target Windows computer after `setup_windows.bat` installs PyQt6 and Qt6.

No prebuilt wheel is shipped. Build one on demand from the project root with
`python -m build`, or install the package directly with `python -m pip install -e .`.

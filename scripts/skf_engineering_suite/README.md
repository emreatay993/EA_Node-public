# SKF Engineering Bearing Suite

A modular Python calculation package and PyQt6 desktop application for rolling-bearing friction, oil drag, thermal equilibrium, rating life, batch operating maps and calibration.

## Implemented model coverage

### Published SKF / ISO equation layer

- SKF rolling and sliding friction torque for every radial/thrust family represented in the referenced SKF table set:
  - deep-groove ball bearings;
  - angular-contact and four-point-contact ball bearings;
  - self-aligning ball bearings;
  - cylindrical roller bearings;
  - tapered roller bearings;
  - spherical roller bearings;
  - CARB toroidal roller bearings;
  - thrust ball bearings;
  - cylindrical roller thrust bearings;
  - spherical roller thrust bearings.
- SKF inlet shear-heating factor, lubricant replenishment/starvation factor and mixed-lubrication sliding coefficient.
- SKF contact-seal torque tables for RSL, RSH, RS1, LS, CS, CS2 and CS5 where published ranges apply.
- SKF oil-bath and oil-jet drag equations, including ball/roller forms, oil-jet multiplier and vertical-shaft submerged-width correction.
- Two-point Walther/ASTM D341 viscosity-temperature interpolation.
- Basic rating life `L10` / `L10h`, reliability factor `a1`, rated viscosity `nu1`, viscosity ratio `kappa`, contamination factor `eC`, and the ISO 281 algebraic life-modification factor used as the standard `aSKF` baseline.

### Explicit engineering extension layer

These features are intentionally identified in the GUI, reports and warnings because they require installation-specific calibration rather than SKF table constants:

- clearance/preload and misalignment friction corrections;
- generic Hertz-like rolling-element load-zone distribution;
- four-node inner-ring / rolling-element / outer-ring / oil thermal network;
- oil bypass and friction-heat partitioning;
- local inner/outer contact temperature rise through user-entered thermal resistances;
- SKF Explorer diagram-axis approximation with configurable scale;
- least-squares calibration factors for rolling, sliding, seal, drag, heat transfer and installation corrections.
- a visibly flagged full-complement CARB proxy because the referenced SKF document publishes its Kz/KL drag constants but no matching Grr/Gsl table row.

## GUI workflow

The PyQt6 interface has nine workspaces:

1. Bearing definition and SKF table-series selection
2. Operating point and lubricant
3. Lubrication, drag and contact seals
4. Clearance, preload, misalignment and element-load distribution
5. One-node or four-node thermal model
6. Rating life
7. Results, convergence and engineering plots
8. Batch speed/load maps from CSV
9. Calibration against measured data or manually exported SKF Bearing Select reference points

The application supports JSON case save/load, CSV batch templates, CSV convergence export, calibration-profile JSON and a self-contained HTML engineering report. Numerical work runs on worker threads so the desktop interface remains responsive.

## Installation on Windows

Recommended Python: 3.11 or 3.12, 64-bit.

```bat
setup_windows.bat
run_gui.bat
```

Manual installation:

```powershell
py -3 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
python -m pytest -q
python launch_gui.py
```

## Command line

```powershell
# Demonstration case, templates and HTML report
python -m skfcalc.cli demo --output-dir results

# One saved case
python -m skfcalc.cli run examples\example_case.json --report results\report.html --history results\history.csv

# Full-model operating map
python -m skfcalc.cli batch examples\example_case.json examples\batch_template.csv results\batch_results.csv --workers 1

# Backend benchmark
python -m skfcalc.benchmark --output results\benchmark.csv
```

## Numba backend

The full engineering solver supports all families and both thermal models. A separate Numba fast path is included for very large deep-groove-ball-bearing maps using the one-node thermal model. It includes rolling/sliding friction, seal torque and oil drag, but deliberately omits four-node temperatures, installation corrections and rating-life output.

The first Numba call compiles the kernel. Benchmark only warm calls for repeated engineering studies.

The current build benchmark reached approximately 1.04 million warm Numba cases/s for a 100,000-point DGBB map on the build computer. The full object-oriented solver ran at approximately 1,020 cases/s for the same one-node benchmark configuration. These are machine-specific measurements, not an assumed Excel comparison; see `docs/performance_and_excel.md` and `results/benchmark.csv`.

## Batch CSV columns

Recognized override columns for the full solver include:

```text
case_id
speed_rpm
radial_load_n
axial_load_n
equivalent_dynamic_load_n
inlet_temp_c
ambient_temp_c
shaft_boundary_temp_c
housing_boundary_temp_c
oil_flow_l_min
oil_level_h_mm
operating_clearance_um
radial_preload_n
axial_preload_n
misalignment_mrad
```

The Numba path additionally recognizes `housing_conductance_w_k`.

## Calibration CSV

At least one measured output is required:

```text
measured_torque_nmm
measured_temperature_c
```

Operating-condition columns use the same names as the batch file. SKF Bearing Select values can be entered into the same template after manual export or transcription. No undocumented SKF web service is called.

## Verification status

The packaged regression suite contains 43 tests covering all ten bearing families, the original DGBB reference case, thermal energy balance, seal/drag behavior, life factors, serialization, batch execution, calibration recovery, report generation, Numba parity, double-row drag and fast-path input validation. See `BUILD_STATUS.md` and `docs/release_validation_checklist.md`.

## Verification and release use

This project is an auditable engineering implementation, not an SKF-certified selector. Before design release:

- verify the selected table series and all product dimensions/ratings;
- enter the bearing-specific equivalent dynamic load `P` rather than relying on the program's reported default;
- calibrate thermal conductances, contact resistances and installation corrections;
- compare representative points with SKF Bearing Select and/or test data;
- review model validity for oil level, viscosity, shaft orientation, internal clearance and alignment;
- retain a validation record with software version, case JSON and calibration profile.

## Primary references

- SKF, *The SKF model for calculating the frictional moment*:
  `https://cdn.skfmediahub.skf.com/api/public/0901d1968065e9e7/pdf_preview_medium/0901d1968065e9e7_pdf_preview_medium.pdf`
- SKF rolling-bearing selection principles and rating-life documentation:
  `https://www.skf.com/group/products/rolling-bearings/principles-of-rolling-bearing-selection`
- ISO 281:2007, *Rolling bearings — Dynamic load ratings and rating life*.
- ASTM D341, *Standard Practice for Viscosity-Temperature Equations and Charts for Liquid Petroleum or Hydrocarbon Products*.

The ISO standard text is not included in this package. See `NOTICES.md` for trademark, scope and PyQt6 licensing notes.

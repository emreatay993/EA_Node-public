# GUI workflow

## Start

```powershell
setup_windows.bat
run_gui.bat
```

Press **F5** at any time to solve the current case.

## Recommended order

1. **Bearing** — choose family/table series and enter catalogue data.
2. **Operating & Oil** — enter `n`, `Fr`, `Fa`, `P`, `nu40`, `nu100`, density and `cp`.
3. **Lubrication & Seals** — select replenishment mode, drag inputs and contact seals.
4. **Installation** — normally leave disabled until coefficients are justified.
5. **Thermal Network** — start with one-node for screening; move to four-node after conductance calibration.
6. **Rating Life** — set reliability and contamination; review the reported source of `P`.
7. **Results** — inspect convergence, torque split, temperatures, element load zone and warnings.
8. **Batch Map** — create/import a CSV operating map. Use the full backend for complete output or the Numba DGBB backend for large one-node maps.
9. **Calibration** — import reference data, fit selected parameters and save the profile.

## File outputs

- `.json`: complete bearing case and calibration state
- `.csv`: batch results, calibration input, convergence history
- `.html`: self-contained engineering report with embedded plots

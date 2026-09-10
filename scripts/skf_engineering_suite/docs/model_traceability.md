# Model traceability

This document separates published bearing equations from engineering extensions. The separation is also repeated in GUI notes, calculation warnings and HTML reports.

## A. Published SKF friction layer

Implemented in `skfcalc/friction.py`, `skfcalc/constants.py`, `skfcalc/seals.py` and `skfcalc/drag.py`.

### Total frictional moment

\[
M = M_{rr}+M_{sl}+M_{seal}+M_{drag}
\]

### Rolling friction

\[
M_{rr}=\phi_{ish}\,\phi_{rs}\,G_{rr}(\nu n)^{0.6}
\]

\[
\phi_{ish}=\frac{1}{1+1.84\times10^{-9}(nd_m)^{1.28}\nu^{0.64}}
\]

\[
\phi_{rs}=\exp\left[-K_{rs}\nu n(d+D)
\sqrt{\frac{K_z}{2(D-d)}}\right]
\]

`Grr` is selected from the family/series table in `constants.py`. Every published row in the referenced table set is transcribed. The optional full-complement CARB entry is explicitly marked as a calibration proxy because the document gives its drag constants but no matching `Grr/Gsl` row.

### Sliding friction

\[
M_{sl}=G_{sl}\mu_{sl}
\]

\[
\mu_{sl}=\phi_{bl}\mu_{bl}+(1-\phi_{bl})\mu_{EHL}
\]

\[
\phi_{bl}=\exp[-2.6\times10^{-8}(n\nu)^{1.4}d_m]
\]

The family-dependent `Gsl` equations and constants are auditable in `friction.load_factors()` and `constants.REGISTRY`.

### Seal torque

For applicable SKF contact seals:

\[
M_{seal}=K_{s1}d_s^{\beta}+K_{s2}
\]

The published relation represents two seals. One-seal handling and the RSL exception are implemented in `seals.seal_torque_nmm()`.

### Oil drag

Ball-bearing and roller-bearing forms are implemented in `drag.drag_torque_nmm()`. They include:

- geometry factors `Kball` / `Kroll`;
- `Cw`, `lD`, `ft`, `Rs` and oil immersion angle;
- graph-derived `VM` interpolation;
- oil-jet factor of two;
- vertical-shaft submerged-width correction.

`VM` is published as a diagram. The source arrays are therefore explicitly described as a digitization and may be overridden by the user.

## B. Viscosity

Implemented in `skfcalc/viscosity.py` using the two-point Walther form fitted to lubricant `nu40` and `nu100`.

## C. Rating life

Implemented in `skfcalc/life.py`.

### Basic life

\[
L_{10}=\left(\frac{C}{P}\right)^p
\]

with `p=3` for ball bearings and `p=10/3` for roller bearings.

\[
L_{10h}=\frac{10^6L_{10}}{60n}
\]

### Modified life

\[
L_{nm}=a_1a_{SKF}L_{10}
\]

The standard `aSKF` baseline is evaluated with the ISO 281 algebraic life-modification equations using viscosity ratio `kappa`, contamination factor `eC`, fatigue load limit `Cu` and equivalent dynamic load `P`.

SKF Explorer performance is exposed as a configurable diagram-axis scale because the SKF publication does not define one universal multiplier valid for all bearing classes.

## D. Engineering extensions

The following are not represented as SKF catalogue equations:

| Extension | Module | Required validation |
|---|---|---|
| Clearance/preload torque multiplier | `installation.py` | Internal load model or test |
| Misalignment torque multiplier | `installation.py` | Bearing-specific analysis/test |
| Generic element load-zone plot | `installation.py` | ISO/TS 16281 or detailed contact model |
| Four-node temperatures | `thermal.py` | Thermal network or test calibration |
| Local contact temperature rise | `thermal.py` | Contact thermal resistance calibration |
| Oil bypass / heat partition | `thermal.py` | Flow/thermal test or CFD |
| Full-complement CARB G-factor proxy | `constants.py` | Supplier calculation or test |
| Calibration scales | `calibration.py` | Independent validation set |

## E. Source references

- SKF, *The SKF model for calculating the frictional moment*.
- SKF rolling-bearing selection principles and rating-life documentation.
- ISO 281:2007, *Rolling bearings — Dynamic load ratings and rating life*.
- ASTM D341, viscosity-temperature equations.

The ISO standard itself is not bundled with the software.

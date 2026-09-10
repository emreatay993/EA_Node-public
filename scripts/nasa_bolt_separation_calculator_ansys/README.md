# NASA-STD-5020B Bolt Separation Calculator

Standalone PyQt utility for calculating bolt separation margins with
NASA-STD-5020B Eq. 19:

```text
MSsep = Pp_min / (FF * FSsep * PtL) - 1
```

Run from the repository root:

```powershell
.\venv\Scripts\python.exe .\scripts\nasa_bolt_separation_calculator_ansys\run.py
```

The GUI uses PyQt6 first and falls back to PyQt5 when PyQt6 is not available.

## What The Tool Does

- Calculates final minimum preload, `Pp_min`, from preload scatter and losses.
- Calculates NASA-STD-5020B separation margin for each bolt/load row.
- Supports direct per-bolt `PtL` input.
- Supports derived `PtL` from imported Ansys Mechanical-style load rows.
- Adds optional advanced screens for combined fastener loading, joint slip,
  seal/pressure residual compression, and nonlinear Ansys contact evidence.
- Imports and exports project JSON, bolt table CSV, and Ansys load CSV.
- Generates a plain-text or HTML report with inputs, margins, controlling bolt, warnings, and source links.

Official source links used by the report:

- [NASA-STD-5020 standard page](https://standards.nasa.gov/standard/nasa/nasa-std-5020)
- [NASA-STD-5020B revalidated PDF](https://standards.nasa.gov/system/files/tmp/2025%20-01-05%20NASA-STD-5020B%20Final%20-Revalidated.pdf)

The GUI also includes toolbar actions for **Method help**, **Open NASA PDF**,
and **NASA online**. The local bundled copy is stored at
`resources/NASA-STD-5020B-Revalidated.pdf` so users can open the standard from
the calculator even when they do not remember the web link.

The **Nomenclature** tab renders a formula and symbol reference inside the GUI.
It covers Eq. 19, preload equations, `FF`, `FSsep`, `PtL`, preload parameters,
Ansys force/moment columns, derived `PtL` modes, NASA combined-load equations,
Appendix A.10 slip equations, seal/pressure residual compression equations,
and nonlinear evidence fields.

## Step-By-Step Guide

### Step 1 - Project

Enter the project name, analyst, force/moment unit labels, fitting factor `FF`,
and separation factor `FSsep`.

For `FF`, check NASA-STD-5020B Section 4.2.2. Use the program/project levied
value or a substantiated value. A common minimum default for
separation-critical work is `1.15`; the GUI keeps this as the starting value
but does not certify that it is correct for a specific program.

For `FSsep`, check NASA-STD-5020B Section 4.2.3 and Figure 1. Choose the factor
from the consequence of credible separation and any proof, acceptance, or
qualification test level that must be enveloped. Critical cases use at least
`max(1.2, FSy)`; catastrophic cases use the program-levied `FSu`.

The **Joint classification** field now drives a read-only recommended `FSsep`:

- `catastrophic`: recommends `FSu`, the program-levied ultimate factor of safety from Figure 1.
- `critical`: recommends `max(1.2, FSy)`, where `FSy` is the program-levied yield factor of safety from Figure 1.
- `non-separation-critical`: recommends `max(1.0, program-levied test factor)` from Figure 1.
- `user-defined`: does not recommend a numeric value; document the basis notes.

The three factor-basis fields are Figure 1 load factors, not material allowables:

- **Program yield factor `FSy`**: use the yield factor of safety levied
  by the program, project, certification basis, or verification plan. It is
  used only for the `critical` `FSsep` recommendation.
- **Program ultimate factor `FSu`**: use the ultimate factor of safety
  levied by the program or verification plan. It is used for the
  `catastrophic` `FSsep` recommendation.
- **Program/test envelope factor**: use the program-levied test factor from
  Figure 1. In practice, this should envelope the largest proof, acceptance,
  qualification, or other planned test load multiplier relative to the same
  limit-load basis used for `PtL`. Use `1.0` if no over-limit test must be
  enveloped.

The calculator does not overwrite the editable `FSsep` automatically. Use
**Apply recommended FSsep** when you want to copy the recommendation into the
calculation field. If the entered `FSsep` is below the recommendation, the GUI
and report show a warning.

Use the checkboxes to flag cases where Eq. 19 is not enough by itself:

- seal or gasket function,
- pressure or fluid containment,
- combined shear, bending, eccentricity, or moment.

These flags add report warnings and sync to Step 4 - Advanced:

- seal or gasket function enables the Seal / Pressure residual compression check,
- pressure or fluid containment enables the Seal / Pressure residual compression check,
- combined shear, bending, eccentricity, or moment enables the Combined Load screen.

After checking one of these boxes, fill the corresponding Step 4 inputs before
using the result as substantiation. Unchecking the Step 1 flag also turns off
the linked Step 4 check.

### Step 2 - Default Preload

Enter the default preload basis:

- `Ppi_nom`: nominal initial preload,
- `Gamma`: preload variation as a decimal, such as `0.25`,
- `cmin`: minimum preload coefficient,
- `nf`: number of fasteners in the pattern,
- relaxation, creep, and thermal preload losses.

Use NASA-STD-5020B Sections 4.3.1 through 4.3.3 as the source for these values.
`Ppi_nom` should come from test-substantiated installation data, `Gamma` should
come from the required preload variation basis, `cmin` should come from the
preload/installation basis, and the losses should capture expected relaxation,
creep, and thermal preload decreases. The GUI `?` buttons beside these fields
open the same guidance and NASA source links.

For separation-critical checks, keep **Use separation-critical preload Eq. 4**
checked. For non-separation-critical multi-bolt joint checks, uncheck it to use
Eq. 5 with the `Gamma / sqrt(nf)` term.

If Step 1 is classified as `catastrophic` or `critical` while this checkbox is
unchecked, the calculator warns that the classification and preload basis look
inconsistent. Keeping Eq. 4 checked for a `non-separation-critical` case is
allowed because it is conservative.

Step 2 is a default profile, not a forced value for every bolt. When a flange
has different fastener sizes, installation torques, preload scatter, or loss
bases, fill the matching `preload_*` override cells in Step 3 for those bolt
rows. Blank preload override cells inherit the Step 2 default.

The final minimum preload used by Eq. 19 is resolved per bolt:

```text
Pp_min = Ppi_min - relaxation_loss - creep_loss - thermal_loss
```

The same equations and parameter definitions are also available in the GUI
**Nomenclature** tab.

### Step 3 - Bolts

Use one row per bolt and load set. The table is spreadsheet-like: paste rows
directly from Excel or CSV with `Ctrl+V`, copy selected cells with `Ctrl+C`, and
clear selected cells with Delete/Backspace. If the pasted first row contains
column names, values are mapped by header; otherwise they paste positionally
from the selected cell.

The Step 3 table can override project defaults per row:

- `fitting_factor` and `separation_factor` override Step 1 `FF` and `FSsep`.
- `preload_ppi_nom`, `preload_gamma`, `preload_cmin`, `preload_nf`,
  `preload_separation_critical`, `preload_relaxation_loss`,
  `preload_creep_loss`, and `preload_thermal_loss` override Step 2 preload.
- `geometry_*` columns override Step 4 combined-load geometry for that bolt.
- `material_*` columns override Step 4 combined-load material allowables for
  that bolt.

Leave an override cell blank when the bolt should inherit the default value
from Step 1, Step 2, or Step 4. Use **Export Bolt CSV** to create the current
template. **Import Bolt CSV** expects that same full table header.

`ptl_mode` choices:

- `direct`: use the `direct_ptl` cell directly.
- `axial`: use `abs(axial)` from an imported Ansys row.
- `fz`: use `abs(fz)` from an imported Ansys row.
- `force_magnitude`: use `sqrt(fx^2 + fy^2 + fz^2)`.
- `axial_plus_bending`: use `abs(axial) + sqrt(mx^2 + my^2) / moment_arm`.

NASA-STD-5020B Eq. 19 is axial-only. The derived modes are convenience paths
for screening and documented engineering review, not a replacement for a
combined-load method.

### Step 4 - Advanced

Enable only the checks that apply to the joint. Eq. 19 remains the primary
axial separation margin; the advanced checks appear as separate report
sections.

#### Combined Load

Use this when the bolt row contains axial tension plus shear and/or bending.
The NASA ultimate option uses NASA-STD-5020B Section 4.4.4 combined fastener
interaction equations:

- Eq. 20/21 for full-diameter bolt body in the shear plane.
- Eq. 22/23 for threads in the shear plane.
- Eq. 21/23 are selected when plastic bending is credited.

The von Mises and Tresca options are yield stress screens. They are useful for
engineering review, but the report labels them as screens rather than NASA
separation margin equations.

Required inputs include tensile area, shear area, diameter or minor-diameter
area, section modulus for bending, tensile/shear allowables, and the selected
factor of safety.

#### Joint Slip

Use NASA Appendix A.10 when friction slip matters:

```text
Eq. 84: MSslip = mu * nf * Pp_min / (FS * (PsL_joint + mu * PtL_joint)) - 1
Eq. 85: MSslip = mu * nf * Pp_min / (FS * PsL_joint) - 1
Eq. 86: MSslip_i = mu * Pp_min_i / (FF * FS * (PsL_i + mu * PtL_i)) - 1
```

Eq. 84/85 assume concentric load through the pattern centroid, equal nominal
preload, same fastener type, and equivalent fastener sizes. Use Eq. 86
per-fastener mode when those assumptions do not hold or when per-bolt Ansys
loads are available.

Without test/substantiation, the GUI caps friction at `0.20` for clean,
uncoated, non-lubricated metal surfaces and `0.10` otherwise.

#### Seal / Pressure

Use this for pressure or gasket/seal cases where residual compression matters.
The calculator evaluates:

```text
pressure_load = pressure * effective_pressure_area
residual_clamp = nf * Pp_min - pressure_load
residual_contact_pressure = residual_clamp / gasket_contact_area
```

It compares those results against user-entered minimum contact pressure and/or
minimum residual clamp load. The tool does not invent seal compression,
leak-rate, or gasket acceptance limits.

#### Nonlinear Evidence

Use this when nonlinear contact opening, contact pressure loss, partial
separation, or load redistribution needs Ansys evidence. Import a CSV with
contact/gap/contact-pressure/load-redistribution rows, then set acceptance
limits such as max gap, minimum residual contact pressure, max separated-area
fraction, and max redistributed `PtL`.

### Step 5 - Results

Press **Calculate margins**. The table shows:

- final minimum preload,
- selected/derived `PtL`,
- factored demand `FF * FSsep * PtL`,
- `MSsep`,
- pass/fail state,
- warnings.

The lower summary pane lists enabled advanced-check results separately from the
Eq. 19 axial separation table.

### Step 6 - Report

Review the report and export it to `.txt` or `.html`.

## Ansys Mechanical Import Workflow

The current workflow is CSV/script assisted. It does not connect to a live Mechanical
session.

Recommended Mechanical-side sources:

- Force Reaction,
- Moment Reaction,
- Beam Probe,
- Bolt Pretension Probe,
- remote point or connector result tables,
- manually exported APDL/Mechanical tables.

Use a bolt-local coordinate system before exporting. For circular flanges, use
axial/radial/tangential directions. For horizontal split-line flanges, use
axial/across-split/along-split directions.

Required Ansys CSV header:

```text
case_id,set_id,bolt_id,fx,fy,fz,mx,my,mz,axial,shear_mag,units,source_type,source_name,quality_flags
```

Required nonlinear evidence CSV header:

```text
case_id,set_id,bolt_id,region,max_gap,min_contact_pressure,separated_area_fraction,redistributed_ptl,quality_flags
```

Generate a template guide and sample CSV:

```powershell
.\venv\Scripts\python.exe .\scripts\nasa_bolt_separation_calculator_ansys\ansys_export.py
```

## Verification

Run the focused tests:

```powershell
.\venv\Scripts\python.exe -m pytest tests/test_nasa_bolt_separation_calculator_ansys.py --ignore=venv -q
```

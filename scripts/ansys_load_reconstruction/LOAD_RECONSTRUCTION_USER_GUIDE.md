# Load Reconstruction User Guide

This guide covers the upgraded load reconstruction workflow in `SG_Calc`.
It explains how to generate the strain sensitivity matrix, run load
reconstruction, read the outputs, and understand the theory behind the method.

## What the tool does

The tool estimates applied load components from strain-gauge channel strain
data:

```text
S = A L + error
```

where:

- `S` is the measured strain history, one row per time point and one column per
  strain-gauge channel.
- `A` is the strain sensitivity matrix from unit-load FE cases, one row per
  strain-gauge channel and one column per load component.
- `L` is the estimated load vector at each time point.

The upgraded point estimate uses direct least squares:

```python
np.linalg.lstsq(A, S.T, rcond=None)
```

It does not form `A.T @ A`, `A.T @ W @ A`, or any normal-equation inverse.
This avoids squaring the condition number of `A` and gives a stable SVD-backed
least-squares solution, including for rank-deficient or nearly collinear load
bases.

## Main scripts

Use these scripts for the normal workflow:

1. `get_strain_sensitivity_matrix_from_unit_load_cases_in_mechanical_v0.py`
   generates `strain_sensitivity_matrix.csv` and sidecar metadata.
2. `get_local_strains_and_SG_geo_data_around_each_SG_grid_dpf.py` exports local
   strain fields, SG local coordinate systems, and SG grid geometry for
   placement sensitivity without creating temporary Mechanical result contours.
3. `calculate_placement_sensitivity_from_local_strains.py` launches the
   placement calculator. Use this file for a Mechanical user button or from
   PowerShell. It is a single button script that embeds its CPython worker.
4. `load_reconstruction_function_with_errors_weighting_function_v1.py`
   estimates loads from `SG_FEA_strain_data.csv` and the sensitivity matrix.

Recommended Mechanical button order:

1. Select the solution environment with your `sol_selected_environment` helper.
2. Run the strain sensitivity matrix extraction.
3. Run the DPF local SG strain extraction in the selected solution environment.
4. Run the placement sensitivity calculation. If
   `strain_sensitivity_metadata.json` is not in the selected solution
   `WorkingDir`, the button asks you to select that JSON file with a standard
   Windows file dialog. If the selected JSON file's folder already contains
   `StrainX_around_each_SG`, that folder is used for placement fields.

Optional placement visualization helper:

- `get_local_strains_and_SG_geo_data_around_each_SG_grid.py` is the legacy
  contour-based local strain exporter. Keep it only for reference or manual
  comparison against Mechanical contour export behavior.
- `get_position_error_contour_v0.3.py` exports local position-error evidence
  from a selected Mechanical result. Use it for inspection only. It is not the
  source of reconstruction placement sensitivity because it does not shift each
  finite SG grid in that channel's local coordinate system.

## Required ANSYS model setup

The sensitivity matrix and measured strain file must represent the same strain
quantity in the same channel order.

For this model, each SG channel is represented by a finite shell/sheet grid body
named like:

```text
SG_Grid_Body_1_1
SG_Grid_Body_1_2
...
```

Each matching result object should be named like:

```text
StrainX_SG1_1
StrainX_SG1_2
...
```

and should be scoped to the matching `SG_Grid_Body_*` body.

The sensitivity generator reads:

```text
NormalElasticStrain.Average.Value
```

That means the matrix row is already the average strain over the finite shell
channel grid. It is not a point strain. Do not apply another finite-grid
averaging correction during reconstruction.

## Step 1: Generate the sensitivity matrix

In Mechanical, create one analysis environment per unit load case. Each unit
load analysis name must contain:

```text
Unit_Load_Study_LC
```

The script uses the order of these analyses in the tree as the load-column
order in `A`.

For each unit load analysis:

1. Create the same unsuppressed `StrainX_SG*` normal elastic strain result
   objects.
2. Scope each `StrainX_SG*` result to the matching `SG_Grid_Body_*` shell/sheet
   channel body.
3. Keep the result object order identical in every unit load analysis.
4. Run `get_strain_sensitivity_matrix_from_unit_load_cases_in_mechanical_v0.py`.
5. Pick the unit-load step in the dialog.

The script writes these files to the selected project folder:

```text
strain_sensitivity_matrix.csv
strain_sensitivity_metadata.json
strain_sensitivity_placement_sensitivity.csv
```

### `strain_sensitivity_matrix.csv`

This is the matrix `A`.

Shape:

```text
number_of_SG_channels x number_of_unit_load_cases
```

For the benchmark model, the real matrix is:

```text
42 x 3
```

### `strain_sensitivity_metadata.json`

This file records:

- channel order
- unit-load analysis names
- selected step times
- result object names
- expected SG grid body names
- shell/sheet body evidence
- body bounds and dimensions where available
- `Average.Value` source evidence
- matrix rank
- singular values
- condition number
- warnings when Mechanical object evidence cannot confirm scoping or body type

The reconstruction script can run without metadata, but then it warns that
finite shell-channel averaging and scoping could not be fully verified.

### `strain_sensitivity_placement_sensitivity.csv`

This file is for placement uncertainty propagation, not finite-grid averaging.

Expected columns:

```text
Channel
Load Case
d_epsilon_d_x_per_mm
d_epsilon_d_y_per_mm
gradient_norm_per_mm
Method
Warning
```

For the Mechanical button workflow, placement sensitivity uses the local
`StrainX_around_each_SG` field exports from the currently selected solution
environment. To create those exports, run
`get_local_strains_and_SG_geo_data_around_each_SG_grid_dpf.py` after selecting
the solution environment that should supply the placement local strain fields.
Suggested button name: `Extract Local SG Strains - DPF`.

The DPF exporter uses `NS_of_faces_of_SG_test_parts`, `CS_SG_Ch_*`, and
`SG_Grid_Body_*`, then writes the folder under that solution's solver folder:

```text
sol_selected_environment.WorkingDir\StrainX_around_each_SG
```

It also writes `local_sg_strain_dpf_diagnostics.json` with the selected result
file, radius/time inputs, channel row counts, and midside-node handling. The
DPF path reads direct nodal tensors where available and uses DPF's unscoped
`extend_to_mid_nodes_fc` nodal extension for high-order midside nodes so it
matches Mechanical contour export numerically. Use the legacy contour exporter
only if you specifically need Mechanical contour-object export behavior.

Then run:

```powershell
.\venv\Scripts\python.exe .\scripts\ansys_load_reconstruction\calculate_placement_sensitivity_from_local_strains.py `
  --metadata C:\path\to\strain_sensitivity_metadata.json `
  --output C:\path\to\strain_sensitivity_placement_sensitivity.csv `
  --local-strain-root C:\path\to\selected\SYS-n\MECH
```

If you add a Mechanical user button, associate it with
`calculate_placement_sensitivity_from_local_strains.py`. Mechanical runs user
buttons with IronPython; the script writes its embedded CPython worker to a
temporary file and starts external CPython for the NumPy/Pandas work. If
Mechanical cannot find `python`, set `SG_PLACEMENT_PYTHON` to the full
`python.exe` path.

The calculator reads:

```text
StrainX_around_each_SG/*.csv
SG_coordinate_matrix.csv
SG_grid_body_vertices_in_local_CS.csv
```

It rotates exported node positions into each `CS_SG_Ch_*` frame, shifts the
finite `SG_Grid_Body_*` footprint by `+/-0.1 mm` in local X and Y by default,
interpolates local `Normal Elastic Strain (mm/mm)`, and central-differences the
average strain. The output derivatives are strain per mm.

Use `--step-mm`, `--samples-x`, and `--samples-y` to change the finite
difference step or footprint sampling density. The default `--step-mm 0.1` is a
derivative step, not the placement uncertainty itself.

If the selected solution environment local field exports do not exist, the file
is still written, but rows are marked `not_computed`. In that case positioning
uncertainty is not propagated and the popup names the missing selected
environment export folder.

Do not select equivalent stress, equivalent strain, or a generic global contour
for placement sensitivity. The correct result is the same local-x normal elastic
strain component used by each SG channel.

## Step 2: Generate or provide measured strain data

The reconstruction script expects this file in the selected analysis solver
folder:

```text
SG_FEA_strain_data.csv
```

Format:

```text
Time [s],SG1_1,SG1_2,...,SG14_3
0.0,...
...
```

The first column is time. All remaining columns are strain channels in strain
units, not microstrain. The channel order must match `strain_sensitivity_matrix.csv`.

## Step 3: Run load reconstruction

Run:

```text
load_reconstruction_function_with_errors_weighting_function_v1.py
```

The GUI asks for:

```text
Overall Signal Noise (microstrains)
Gage Factor Error (%)
Positioning Std. Uncertainty [mm]
```

Defaults:

```text
20 microstrain
1 percent gage-factor standard uncertainty
0.5 mm positioning standard uncertainty
```

These values do not change the point estimate. They are used only for
uncertainty propagation in Monte Carlo output.

## Batch and non-interactive use

Set these environment variables before running the script in Mechanical batch:

| Variable | Default | Meaning |
|---|---:|---|
| `SG_LOAD_RECON_NO_GUI` | unset | Use env/default inputs and do not show the WinForms prompt. |
| `SG_LOAD_RECON_SIGNAL_NOISE_MICROSTRAINS` | `20` | Additive strain noise standard deviation in microstrain. |
| `SG_LOAD_RECON_GAGE_FACTOR_ERROR_PERCENT` | `1` | Multiplicative per-channel gage-factor standard uncertainty. |
| `SG_LOAD_RECON_POSITION_STD_MM` | `0.5` | Placement standard uncertainty in mm. |
| `SG_LOAD_RECON_MONTE_CARLO_SAMPLES` | `1000` | Number of uncertainty samples. |
| `SG_LOAD_RECON_SEED` | `20260628` | Monte Carlo random seed. |
| `SG_LOAD_RECON_THERMAL_FILE` | unset | Optional path to thermal/apparent strain compensation CSV. |
| `SG_LOAD_RECON_KNOWN_LOADS_FILE` | unset | Optional path to known loads CSV for validation. |
| `SG_LOAD_RECON_NO_PLOT` | unset | Skip Plotly HTML opening. |
| `SG_LOAD_RECON_WAIT` | unset | Wait for the spawned CPython process to finish. |

For batch verification, a typical setup is:

```powershell
$env:SG_LOAD_RECON_NO_GUI = "1"
$env:SG_LOAD_RECON_NO_PLOT = "1"
$env:SG_LOAD_RECON_WAIT = "1"
$env:SG_LOAD_RECON_SIGNAL_NOISE_MICROSTRAINS = "20"
$env:SG_LOAD_RECON_GAGE_FACTOR_ERROR_PERCENT = "1"
$env:SG_LOAD_RECON_POSITION_STD_MM = "0.5"
$env:SG_LOAD_RECON_MONTE_CARLO_SAMPLES = "1000"
$env:SG_LOAD_RECON_SEED = "20260628"
```

## Optional input files

### `SG_thermal_apparent_strain_data.csv`

Use this when the analysis or test includes thermal/apparent strain that should
not be reconstructed as mechanical load.

Supported forms:

- same channel columns as `SG_FEA_strain_data.csv`
- with or without a time column
- one row, repeated across all time points
- one row per measured time point

The values are subtracted from `SG_FEA_strain_data.csv` before solving.

If the Workbench project mentions `Isothermal Heating` and this file is absent,
the diagnostics warn:

```text
thermal/apparent strain can reconstruct as fake mechanical load
```

### `known_loads.csv`

Use this for validation against known applied loads.

Expected columns:

```text
Load 1,Load 2,Load 3,...
```

with the same row count as `SG_FEA_strain_data.csv`.

If present and valid, the script writes:

```text
load_reconstruction_validation.csv
```

## Output files

### `estimated_loads_with_errors_per_gauge_RMS.csv`

Kept for compatibility with the old workflow.

Despite the old name, this is now the plain direct least-squares point estimate.
The error inputs do not alter this file.

### `estimated_loads_uncertainty.csv`

Monte Carlo uncertainty summary.

For each load component it writes:

```text
Load N Mean
Load N Std
Load N P2.5
Load N P97.5
```

### `load_reconstruction_diagnostics.json`

This is the first file to check when something looks wrong.

It records:

- input paths
- uncertainty parameters
- matrix shape
- rank
- singular values
- condition number
- residual RMS
- finite-channel averaging statement
- output paths
- warnings

### `load_reconstruction_validation.csv`

Written only when `known_loads.csv` is supplied and matches the output shape.

## Theory summary

### Linear forward model

The model assumes linear elastic superposition:

```text
S = A L
```

This is valid when:

- material behavior is linear elastic
- deformations are small enough for linear strain-displacement behavior
- contacts, supports, preload effects, and load paths do not change with load
- the real loading lies in the span of the chosen unit-load cases

If these assumptions fail, least squares can still return numbers, but they are
not guaranteed to be physically meaningful.

### Least squares point estimate

For each time point, the tool solves:

```text
minimize ||A L - S||_2
```

The implementation calls:

```python
np.linalg.lstsq(A, S.T, rcond=None)
```

This uses a direct least-squares method instead of the normal equations.

The old weighted form:

```text
inv(A.T W A) A.T W S
```

was removed because:

- forming `A.T A` squares the condition number
- `inv` can return unstable results for ill-conditioned or rank-deficient cases
- the previous weights mixed systematic effects with random noise

### Conditioning

The diagnostics report singular values and condition number:

```text
condition_number = largest_singular_value / smallest_singular_value
```

Large condition numbers mean small strain errors can become large load errors.
Plain least squares is still the correct baseline estimator. Add regularization
only when real validation/noise behavior shows it is needed.

### Gage-factor uncertainty

Gage-factor error is modeled as a multiplicative systematic uncertainty:

```text
epsilon_sample = epsilon * (1 + delta_gage)
```

where `delta_gage` is sampled once per channel per Monte Carlo sample and held
fixed over the whole time record for that sample.

It is not used as a diagonal weight for the point estimate.

### Additive strain noise

Signal noise is modeled as independent additive strain noise:

```text
epsilon_sample = epsilon + noise
```

The GUI value is in microstrain. Internally it is converted to strain:

```text
20 microstrain = 20e-6 strain
```

### Positioning uncertainty

Positioning uncertainty is gradient-driven:

```text
delta_epsilon = (d_epsilon/dx) dx + (d_epsilon/dy) dy
```

It is not modeled as a percentage of strain magnitude.

This is why `strain_sensitivity_placement_sensitivity.csv` needs spatial
derivatives. If the derivatives are missing, positioning uncertainty is skipped
and the diagnostics warn.

### Thermal/apparent strain

Thermal strain can look like mechanical load because the solver only knows:

```text
S = A L
```

If a load-independent thermal strain vector is present in `S`, least squares
will project it onto the load basis and report fake load. Supply
`SG_thermal_apparent_strain_data.csv` when thermal/apparent strain is present.

### Finite gauge-channel averaging

The benchmark model uses shell/sheet SG grid bodies with finite size. Since the
sensitivity generator reads `NormalElasticStrain.Average.Value` on each
`StrainX_SG*` result, each matrix row is already the average strain over that
finite SG channel grid.

Therefore:

- do verify that each result is scoped to the matching SG grid body
- do keep measured and sensitivity channels in the same order
- do not add a second finite-grid averaging correction

## Benchmark evidence

For the benchmark project:

```text
C:\Users\user\Documents\ANSYS\Benchmark\load_reconstruction_v0.wbpj
```

the target system is:

```text
SYS-6
Arbitrary Loads with Isothermal Heating
```

The solver folder is:

```text
C:\Users\user\Documents\ANSYS\Benchmark\load_reconstruction_v0_files\dp0\SYS-6\MECH
```

Observed evidence:

- `ds.dat` lists 42 `SG_Grid_Body_*` bodies.
- `CAERep.xml` records `SG_Grid_Body_1_1` as `GeometryType=Sheet`,
  `ModelType=Shell`.
- `SG_Grid_Body_1_1` has bounding-box diagonal about `4.7 mm`.
- `strain_sensitivity_matrix.csv` is `42 x 3`.
- The matrix is full rank, rank `3`.
- The condition number is about `1.11e5`.
- The upgraded OLS point estimate matches the old output to roundoff on the
  benchmark files.

## Practical checks before trusting results

Check these before using reconstructed loads for decisions:

1. `load_reconstruction_diagnostics.json` exists.
2. `normal_equations_used` is `false`.
3. `rank` equals the number of load columns.
4. `condition_number` is not unexpectedly large for your application.
5. `metadata_confirms_shell_channel_average` is `true` when metadata is present.
6. No channel-order warning appears.
7. If thermal loading exists, a thermal compensation file is supplied.
8. If positioning uncertainty matters, placement derivatives are numeric.
9. If possible, `known_loads.csv` validation error is acceptable.

## Common warnings

### Missing metadata

```text
strain_sensitivity_metadata.json was not found
```

The solve can still run, but Mechanical scoping and shell/sheet evidence were
not verified for this matrix. Regenerate the sensitivity matrix with the
upgraded generator.

### Missing placement sensitivity

```text
Placement Std. Uncertainty [mm] is nonzero, but placement sensitivity was not found
```

The point estimate is still valid. The uncertainty output does not include
placement uncertainty.

### Thermal warning

```text
Isothermal Heating appears to exist, but no SG_thermal_apparent_strain_data.csv was supplied
```

Do not ignore this for thermally loaded cases. Add a thermal/apparent strain
compensation file or validate that thermal strain is negligible.

## Limitations

The tool does not automatically solve these problems:

- nonlinear material, geometry, or contact behavior
- load paths outside the unit-load basis
- FE model error in `A`
- transverse sensitivity correction
- physical calibration against known loads
- regularization parameter selection
- missing or incorrect strain-gauge scoping

For production use, validate with known applied loads whenever possible.

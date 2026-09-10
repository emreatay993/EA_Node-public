# Strain‑Gauge Thermal Correction

Removes the temperature‑induced **thermal output** (apparent strain) from measured
strain‑gauge channels so the recovered **mechanical** strain can be validated against
an FE model's **elastic** strain (projected onto the gauge axis).

This is the *front‑end* that the rest of the strain‑gauge toolchain was missing: it
turns a manufacturer thermal‑output curve plus measured temperatures into a
per‑channel apparent‑strain correction, and emits CSVs that drop straight into the
[Sensor Comparison Tool](../Sensor_Data_Comparison_Tool) (FE‑vs‑test overlay) and the
[load‑reconstruction tool](../ansys_load_reconstruction) (which subtracts
`SG_thermal_apparent_strain_data.csv`).

## Correction model

```
eps_mech(t)   = ( eps_measured(t) − eps_apparent(T(t)) ) · F_ref / F(T(t))
eps_apparent  = curve_fit(T)  +  (alpha_part − alpha_curve) · (T − T_ref)
F(T)          = F_ref · (1 + dF(T)/100)        →   scale = 1 / (1 + dF(T)/100)
```

- `curve_fit(T)` — polynomial fit (default degree 1) of the manufacturer curve, with R² reported.
- `(alpha_part − alpha_curve)·(T − T_ref)` — **substrate α‑mismatch** term. See the caveat below; it can be the *dominant* correction (~1000 µε over a 150 °C rise).
- `F_ref/F(T)` — **gauge‑factor‑vs‑temperature** term (needs `dF(T)` from the datasheet; identity if absent).

## ⚠️ The substrate caveat (read this)

The gauge here is `BAB350‑…(16)…` — self‑temperature‑compensated (STC) for **α ≈ 16 ppm/°C
(copper)** — but the part is **titanium (α ≈ 9 ppm/°C)**. A curve that comes from the *gauge
manufacturer* is the standard **STC‑reference (copper) curve**, **not** measured on your
titanium part. So on titanium the gauge has a large extra thermal output and you **must add**
`(α_Ti − 16)·(T − T_ref)`. That is why `mismatch_enabled` defaults to **True**.

If, instead, the curve was measured on your *actual titanium hardware*, run with `--no-mismatch`.

Because the mismatch term is large, confirm with the gauge maker: the **exact reference α**, the
curve's **reference temperature** (apparent‑strain zero), and use **α(T) for the specific Ti
alloy** (e.g. Ti‑6Al‑4V), not a single constant, over a wide span.

## CLI

```bash
# from the repo root, using the project venv:
.\venv\Scripts\python.exe scripts\strain_gauge_thermal_correction\examples\generate_examples.py

.\venv\Scripts\python.exe -m scripts.strain_gauge_thermal_correction.run \
    --strain      scripts\strain_gauge_thermal_correction\examples\synthetic_strain.csv \
    --temperature scripts\strain_gauge_thermal_correction\examples\synthetic_temperature.csv \
    --curve       scripts\strain_gauge_thermal_correction\examples\copper_reference_curve.csv \
    --mismatch --alpha-part 9 --alpha-curve 16 --t-ref 20 \
    --gauge-factor-delta 0.008 \
    --out-dir out
```

`--alpha-part` and `--gauge-factor-delta` accept either a scalar or a path to a 2‑column CSV
`(T, value)` for temperature‑dependent tables.

## Outputs (in `--out-dir`)

| File | Consumer | Schema |
|------|----------|--------|
| `corrected_strain.csv` | Sensor Comparison Tool | `Time` + per‑channel mechanical strain |
| `SG_thermal_apparent_strain_data.csv` | load‑reconstruction tool | channel‑named columns (selected by name) |
| `thermal_correction_diagnostics.json` | you | fit R²/coeffs, α's, units, per‑channel max\|apparent\|, warnings, trust checklist |

## Units

Internal math is in **microstrain**. `--measured-unit` / `--curve-unit` / `--output-unit` are
`microstrain` (default) or dimensionless `strain`. **Set `--output-unit strain` if your
`SG_FEA_strain_data.csv` is dimensionless** so the apparent‑strain CSV matches it before the
load‑reconstruction subtraction. Units are stamped in every output and the diagnostics JSON.

## Theory & validation

`methodology_docs/` holds a runnable methodology notebook (theory + a ground‑truth round‑trip on
synthetic data, including a panel showing the ~1000 µε error if the mismatch term is wrongly
omitted) and a theory deck. No ANSYS dependency.

## Tests

```bash
.\venv\Scripts\python.exe -m pytest tests\test_strain_gauge_thermal_correction.py -n auto
```

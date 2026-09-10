# Purpose: CLI for the strain-gauge thermal-output correction tool.
# Map: subsystems/supporting_runtime_assets
# Tests: tests/test_strain_gauge_thermal_correction.py
"""Command-line front-end.

Example (the resolved BAB350 / titanium case — manufacturer copper-reference
curve, so the substrate mismatch term is ON)::

    python -m scripts.strain_gauge_thermal_correction.run \
        --strain examples/synthetic_strain.csv \
        --temperature examples/synthetic_temperature.csv \
        --curve examples/copper_reference_curve.csv \
        --mismatch --alpha-part 9 --alpha-curve 16 --t-ref 20 \
        --out-dir out

Writes three files into ``--out-dir``:
  * ``corrected_strain.csv``                  (Time + per-channel mechanical strain)
  * ``SG_thermal_apparent_strain_data.csv``   (for the load-reconstruction tool)
  * ``thermal_correction_diagnostics.json``
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence

import numpy as np
import pandas as pd

try:  # package execution: python -m scripts.strain_gauge_thermal_correction.run
    from .config import CorrectionConfig
    from .core import (
        correct_dataset,
        load_curve,
        load_curve_from_coeffs,
        read_timeseries_csv,
        write_corrected_strain_csv,
        write_diagnostics_json,
        write_thermal_apparent_csv,
    )
except ImportError:  # pragma: no cover - direct-script execution fallback
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from config import CorrectionConfig  # type: ignore
    from core import (  # type: ignore
        correct_dataset,
        load_curve,
        load_curve_from_coeffs,
        read_timeseries_csv,
        write_corrected_strain_csv,
        write_diagnostics_json,
        write_thermal_apparent_csv,
    )


def _parse_scalar_or_table(value: str):
    """Return a float, or an (N, 2) numpy table read from a 2-column CSV path."""
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        pass
    path = Path(value)
    if not path.exists():
        raise SystemExit(f"value {value!r} is neither a number nor an existing CSV path")
    frame = pd.read_csv(path)
    if frame.shape[1] < 2:
        raise SystemExit(f"{path}: expected at least two columns [T, value]")
    return frame.iloc[:, :2].astype(float).to_numpy()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Apply thermal-output (apparent-strain) correction to strain-gauge time series.",
    )
    parser.add_argument("--strain", required=True, help="Measured strain CSV (Time + per-channel columns).")
    parser.add_argument("--temperature", help="Temperature CSV (Time + per-channel columns, same names).")

    curve = parser.add_mutually_exclusive_group(required=True)
    curve.add_argument("--curve", help="Manufacturer thermal-output curve (.xlsx/.csv): T vs apparent strain.")
    curve.add_argument("--curve-coeffs", help="Comma-separated polynomial coeffs (highest power first).")
    parser.add_argument("--curve-degree", type=int, default=1, help="Polynomial fit degree (default 1).")
    parser.add_argument("--curve-unit", default="microstrain", choices=["microstrain", "strain"])
    parser.add_argument("--curve-t-col", help="Temperature column name in the curve file.")
    parser.add_argument("--curve-strain-col", help="Apparent-strain column name in the curve file.")

    parser.add_argument("--t-ref", type=float, default=20.0, help="Reference temperature [degC] (default 20).")
    mismatch = parser.add_mutually_exclusive_group()
    mismatch.add_argument("--mismatch", dest="mismatch", action="store_true", help="Apply substrate alpha-mismatch (default).")
    mismatch.add_argument("--no-mismatch", dest="mismatch", action="store_false", help="Curve already on the real part.")
    parser.set_defaults(mismatch=True)
    parser.add_argument("--alpha-part", default="9.0", help="Part alpha [ppm/degC]: scalar or 2-col CSV (T, alpha).")
    parser.add_argument("--alpha-curve", type=float, default=16.0, help="Curve substrate alpha [ppm/degC] (default 16).")

    parser.add_argument("--gauge-factor-delta", help="dF [%]: scalar (per-degC slope) or 2-col CSV (T, dF%).")
    parser.add_argument("--gauge-factor-delta-flat", action="store_true", help="Treat scalar dF as a flat %% offset.")
    parser.add_argument("--gauge-factor-ref", type=float, help="Reference gauge factor F_ref (reporting only).")

    parser.add_argument("--measured-unit", default="microstrain", choices=["microstrain", "strain"])
    parser.add_argument("--output-unit", default="microstrain", choices=["microstrain", "strain"],
                        help="Units of both output CSVs; set 'strain' to match dimensionless FEA strain.")
    parser.add_argument("--extrapolation", default="warn", choices=["warn", "error", "clamp", "ignore"])
    parser.add_argument("--single-row-thermal", action="store_true",
                        help="Emit a single broadcastable row in the thermal apparent-strain CSV.")
    parser.add_argument("--out-dir", default="out", help="Output directory (default ./out).")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.curve:
        fit = load_curve(
            args.curve,
            degree=args.curve_degree,
            t_col=args.curve_t_col,
            strain_col=args.curve_strain_col,
            curve_unit=args.curve_unit,
        )
    else:
        coeffs = [float(x) for x in args.curve_coeffs.split(",") if x.strip()]
        fit = load_curve_from_coeffs(coeffs, curve_unit=args.curve_unit)

    cfg = CorrectionConfig(
        t_ref_celsius=args.t_ref,
        degree=args.curve_degree,
        mismatch_enabled=args.mismatch,
        alpha_part_ppm=_parse_scalar_or_table(args.alpha_part),
        alpha_curve_substrate_ppm=args.alpha_curve,
        gauge_factor_ref=args.gauge_factor_ref,
        gauge_factor_delta_pct=_parse_scalar_or_table(args.gauge_factor_delta) if args.gauge_factor_delta else None,
        gauge_factor_delta_is_slope=not args.gauge_factor_delta_flat,
        measured_unit=args.measured_unit,
        curve_unit=args.curve_unit,
        output_unit=args.output_unit,
        extrapolation=args.extrapolation,
    )
    cfg.validate()

    strain_frame = read_timeseries_csv(args.strain)
    temp_frame = read_timeseries_csv(args.temperature) if args.temperature else None
    if temp_frame is None:
        print("WARNING: no --temperature supplied; channels will be left uncorrected.", file=sys.stderr)

    corrected_frame, apparent_frame, diagnostics = correct_dataset(strain_frame, temp_frame, fit, cfg)

    out_dir = Path(args.out_dir)
    corrected_path = write_corrected_strain_csv(out_dir / "corrected_strain.csv", corrected_frame)
    thermal_path = write_thermal_apparent_csv(
        out_dir / "SG_thermal_apparent_strain_data.csv",
        apparent_frame,
        single_row=args.single_row_thermal,
    )
    diag_path = write_diagnostics_json(out_dir / "thermal_correction_diagnostics.json", diagnostics)

    max_app = max((c["max_apparent_strain_microstrain"] for c in diagnostics["channels"]), default=0.0)
    print(f"curve fit: degree={fit.degree} R^2={fit.r_squared:.5f} rmse={fit.rmse:.2f} ue "
          f"(range {fit.t_min:.0f}..{fit.t_max:.0f} C)")
    print(f"mismatch term: {'ON' if cfg.mismatch_enabled else 'OFF'} "
          f"(alpha_curve={cfg.alpha_curve_substrate_ppm} ppm/C)")
    print(f"max |apparent strain| across channels: {max_app:.1f} ue")
    if diagnostics["warnings"]:
        print(f"{len(diagnostics['warnings'])} channel warning(s) — see diagnostics JSON.", file=sys.stderr)
    print(f"wrote:\n  {corrected_path}\n  {thermal_path}\n  {diag_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

try:
    from .io_formats import ANSYS_LOAD_COLUMNS, NONLINEAR_EVIDENCE_COLUMNS
except ImportError:  # pragma: no cover - direct script execution fallback.
    from io_formats import ANSYS_LOAD_COLUMNS, NONLINEAR_EVIDENCE_COLUMNS  # type: ignore


MECHANICAL_EXPORT_GUIDE = """# Ansys Mechanical Bolt Load Export Guide

This calculator imports bolt loads from CSV/JSON instead of connecting to a live
Mechanical session. The recommended workflow is:

1. In Mechanical, create or evaluate one result object per bolt and result set:
   Force Reaction, Moment Reaction, Beam Probe, Bolt Pretension Probe, or a
   user table based on the connector abstraction used in your model.
2. Report loads in a bolt-local coordinate system. For circular flanges, use
   axial/radial/tangential directions. For horizontal split-line flanges, use
   axial/across-split/along-split directions.
3. Export one row per bolt per load set using the CSV header below.
4. Import the CSV in the calculator and choose the PtL derivation mode.

For solid/contact bolts, a later DPF fallback can sum named-selection
under-head element nodal forces and moments. For now, use an analyst-created
Mechanical/APDL table when probe exports are not available.

For nonlinear contact evidence, export or assemble one row per checked
bolt/contact region with maximum gap, minimum contact pressure, separated area
fraction, and redistributed bolt tensile load. Import that CSV in Step 4 -
Advanced > Nonlinear Evidence.
"""


def ansys_load_csv_header() -> str:
    return ",".join(ANSYS_LOAD_COLUMNS)


def sample_ansys_load_csv() -> str:
    return "\n".join(
        [
            ansys_load_csv_header(),
            "LC1,1,B1,0,250,4200,1000,0,50,4200,250,N|N-mm,beam_probe,B1_BEAM,check local axis",
            "LC1,1,B2,0,175,3900,800,0,25,3900,175,N|N-mm,force_reaction,B2_FORCE,",
        ]
    )


def nonlinear_evidence_csv_header() -> str:
    return ",".join(NONLINEAR_EVIDENCE_COLUMNS)


def sample_nonlinear_evidence_csv() -> str:
    return "\n".join(
        [
            nonlinear_evidence_csv_header(),
            "LC1,1,B1,under_head_contact,0.01,2.5,0.02,4300,sample nonlinear contact row",
            "LC1,1,B2,gasket_land,0.02,2.1,0.04,4200,",
        ]
    )


def write_template_files(output_dir: str | Path) -> list[Path]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    guide = output_path / "ANSYS_MECHANICAL_EXPORT_GUIDE.md"
    csv_template = output_path / "ansys_bolt_loads_template.csv"
    evidence_template = output_path / "nonlinear_contact_evidence_template.csv"
    guide.write_text(MECHANICAL_EXPORT_GUIDE, encoding="utf-8")
    csv_template.write_text(sample_ansys_load_csv() + "\n", encoding="utf-8")
    evidence_template.write_text(sample_nonlinear_evidence_csv() + "\n", encoding="utf-8")
    return [guide, csv_template, evidence_template]


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Write NASA bolt separation Ansys CSV templates.")
    parser.add_argument(
        "--output-dir",
        default=str(Path(__file__).resolve().parent / "examples"),
        help="Directory where the guide and CSV template will be written.",
    )
    args = parser.parse_args(argv)
    for path in write_template_files(args.output_dir):
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

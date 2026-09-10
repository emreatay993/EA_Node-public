"""Command-line interface for the SKF Engineering Bearing Suite."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .batch import run_batch_csv
from .io import create_batch_template, create_calibration_template, load_case, save_case, write_history_csv
from .models import BearingCase
from .report import generate_html_report
from .solver import solve_case


def _demo(output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    case = BearingCase()
    result = solve_case(case)
    save_case(case, output_dir / "example_case.json")
    write_history_csv(result.history, output_dir / "example_convergence.csv")
    generate_html_report(case, result, output_dir / "example_report.html")
    create_batch_template(output_dir / "batch_template.csv")
    create_calibration_template(output_dir / "calibration_template.csv")
    print(json.dumps(result.summary_dict(), indent=2))
    print(f"Artifacts written to {output_dir.resolve()}")


def main() -> None:
    parser = argparse.ArgumentParser(prog="skf-bearing", description=__doc__)
    sub = parser.add_subparsers(dest="command")

    p_demo = sub.add_parser("demo", help="Run the built-in engineering example.")
    p_demo.add_argument("--output-dir", type=Path, default=Path("skf_results"))

    p_run = sub.add_parser("run", help="Run one saved JSON case.")
    p_run.add_argument("case", type=Path)
    p_run.add_argument("--report", type=Path)
    p_run.add_argument("--history", type=Path)

    p_batch = sub.add_parser("batch", help="Run a CSV operating map from a base JSON case.")
    p_batch.add_argument("case", type=Path)
    p_batch.add_argument("input_csv", type=Path)
    p_batch.add_argument("output_csv", type=Path)
    p_batch.add_argument("--workers", type=int, default=1)

    args = parser.parse_args()
    if args.command in (None, "demo"):
        _demo(args.output_dir if args.command else Path("skf_results"))
        return
    if args.command == "run":
        case = load_case(args.case)
        result = solve_case(case)
        print(json.dumps(result.summary_dict(), indent=2))
        if args.report:
            generate_html_report(case, result, args.report)
        if args.history:
            write_history_csv(result.history, args.history)
        return
    if args.command == "batch":
        case = load_case(args.case)
        run = run_batch_csv(case, args.input_csv, args.output_csv, workers=max(args.workers, 1))
        print(f"Wrote {len(run.dataframe)} rows to {args.output_csv}; failures={run.failed_cases}")


if __name__ == "__main__":
    main()

"""Command-line interface (and GUI launcher when run without a subcommand).

Exit codes: 0 ok, 2 input/config error, 3 solve infeasible, 4 verification not
accepted — scriptable in batch chains (house convention).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from scripts.equivalent_static_load.config import ConfigError, load_config
from scripts.equivalent_static_load.core import EslError, InputError, SolveError


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="equivalent_static_load",
        description=(
            "Derive equivalent static rig loads from an MSUP transient "
            "(blade-out secondary vibrations). Run without a subcommand to "
            "launch the GUI."
        ),
    )
    sub = parser.add_subparsers(dest="command")

    p = sub.add_parser("make-synthetic", help="Generate the offline demo dataset")
    p.add_argument("--out", required=True)
    p.add_argument("--nodes", type=int, default=500)
    p.add_argument("--modes", type=int, default=8)
    p.add_argument("--channels", type=int, default=4)
    p.add_argument("--times", type=int, default=1000)
    p.add_argument("--seed", type=int, default=0)

    p = sub.add_parser("check", help="Pre-flight: load inputs, mode counts, mapping dry-run")
    p.add_argument("--config", required=True)

    p = sub.add_parser("suggest-instants", help="Evidence-driven candidate instants")
    p.add_argument("--config", required=True)
    p.add_argument("--out", default=None, help="Optional CSV output path")

    p = sub.add_parser("resultants", help="Route A: interface resultants at an instant")
    p.add_argument("--config", required=True)
    p.add_argument("--t", type=float, required=True, help="Instant [s] (snapped to grid)")
    p.add_argument("--out", default=None, help="Optional CSV output path")

    p = sub.add_parser("derive", help="Derive ESL load sets (writes the full output folder)")
    p.add_argument("--config", required=True)
    p.add_argument("--instants", default=None, help="Comma-separated times [s], overrides config")
    p.add_argument("--tier", choices=("1", "2", "both"), default=None)
    p.add_argument("--pattern-csv", default=None, help="Tier-1 pattern (channel,value CSV)")
    p.add_argument("--out", default=None, help="Output directory override")

    p = sub.add_parser("verify", help="Compare a combined-solve field vs a case target")
    p.add_argument("--config", required=True)
    p.add_argument("--case", required=True, help="Case id, e.g. t0p012300")
    group = p.add_mutually_exclusive_group(required=True)
    group.add_argument("--solved-field", default=None, help="Solved tensor CSV")
    group.add_argument("--solved-rst", default=None, help="Solved .rst (needs DPF)")
    p.add_argument("--set", type=int, default=None, help="Result set in --solved-rst")

    return parser


def _cmd_make_synthetic(args: argparse.Namespace) -> int:
    from scripts.equivalent_static_load.synthetic import make_synthetic

    truth = make_synthetic(
        args.out, n_nodes=args.nodes, n_modes=args.modes,
        n_channels=args.channels, n_times=args.times, seed=args.seed,
    )
    print(f"Synthetic dataset written to {args.out}")
    print(f"  t* = {truth['t_star']:.6g}s, lambda_true = {truth['lambda_true']}")
    print(f"  config: {Path(args.out) / 'config.json'}  truth: {Path(args.out) / 'truth.json'}")
    return 0


def _cmd_check(args: argparse.Namespace) -> int:
    from scripts.equivalent_static_load.workflow import load_inputs

    cfg = load_config(args.config)
    inputs = load_inputs(cfg, log=print)
    print("\nChannel table:")
    header = f"{'name':<16} {'case_label':<12} {'unit_load':>10} {'bounds':<24} {'iface_channel':<18}"
    print(header)
    print("-" * len(header))
    for c in cfg.channels:
        print(
            f"{c.name:<16} {c.case_label:<12} {c.unit_load:>10.4g} "
            f"{str(list(c.bounds)):<24} {str(c.interface_channel):<18}"
        )
    for w in inputs.warnings:
        print(f"WARNING: {w}")
    print("\ncheck OK")
    return 0


def _cmd_suggest_instants(args: argparse.Namespace) -> int:
    import pandas as pd

    from scripts.equivalent_static_load.workflow import choose_instants, load_inputs

    cfg = load_config(args.config)
    inputs = load_inputs(cfg, log=print)
    suggestions = choose_instants(cfg, inputs, log=print)
    frame = pd.DataFrame(
        {
            "time_s": [s.time for s in suggestions],
            "reason": [s.reason for s in suggestions],
            "driver_node": [s.driver_node for s in suggestions],
            "vm_at_driver": [s.vm_at_driver for s in suggestions],
            "cluster_size": [s.cluster_size for s in suggestions],
        }
    )
    print("\n" + frame.to_string(index=False))
    if args.out:
        frame.to_csv(args.out, index=False)
        print(f"written: {args.out}")
    return 0


def _cmd_resultants(args: argparse.Namespace) -> int:
    import pandas as pd

    from scripts.equivalent_static_load.io_fields import load_node_list
    from scripts.equivalent_static_load.io_modal import (
        check_mode_consistency,
        load_modal_coordinates,
        load_modal_field,
    )
    from scripts.equivalent_static_load.reconstruct import interface_resultants, snap_to_grid

    cfg = load_config(args.config)
    if cfg.msup.modal_forces_csv is None:
        raise InputError("resultants needs msup.modal_forces_csv in the config")
    if not cfg.interfaces:
        raise InputError("resultants needs at least one entry in 'interfaces'")
    forces = load_modal_field(cfg.msup.modal_forces_csv, kind="force")
    coords = load_modal_coordinates(cfg.msup.modal_coordinates)
    check_mode_consistency(forces, coords, "modal forces CSV")
    instant = snap_to_grid(coords, args.t)
    print(f"Instant snapped to t={instant.time:.6g}s (index {instant.index})")

    rows = []
    for iface in cfg.interfaces:
        node_ids = load_node_list(iface.node_list_csv)
        f, m = interface_resultants(forces, coords, instant, node_ids, iface.ref_point)
        rows.append(
            {
                "interface": iface.name, "time_s": instant.time,
                "fx": f[0], "fy": f[1], "fz": f[2],
                "mx_about_ref": m[0], "my_about_ref": m[1], "mz_about_ref": m[2],
                "ref_x": iface.ref_point[0], "ref_y": iface.ref_point[1], "ref_z": iface.ref_point[2],
                "n_nodes": len(node_ids),
            }
        )
    frame = pd.DataFrame(rows)
    print(frame.to_string(index=False))
    if args.out:
        frame.to_csv(args.out, index=False)
        print(f"written: {args.out}")
    print(
        "\nNote: for resultants straight from a modal .rst over the whole time "
        "history, use the sibling tool scripts/mcf_dpf_section_resultants."
    )
    return 0


def _cmd_derive(args: argparse.Namespace) -> int:
    from scripts.equivalent_static_load.workflow import derive_run

    cfg = load_config(args.config)
    override = (
        [float(t) for t in str(args.instants).split(",")] if args.instants else None
    )
    result = derive_run(
        cfg,
        override_times=override,
        tier=args.tier,
        pattern_csv=Path(args.pattern_csv) if args.pattern_csv else None,
        out_dir=Path(args.out) if args.out else None,
        log=print,
    )
    print(f"\nOutputs: {result.out_dir}")
    for case in result.cases:
        for tier_key in sorted(case.tiers):
            tier = case.tiers[tier_key]
            lam = f" lambda={tier.solution.lam:.4g}" if tier.solution.lam is not None else ""
            print(
                f"  {case.case_id} tier {tier_key}:{lam} "
                f"peak_ratio={tier.metrics.peak_ratio_at_critical:.3f} "
                f"under_test={tier.metrics.n_under_test}"
            )
    for w in result.warnings:
        print(f"WARNING: {w}")
    return 0


def _cmd_verify(args: argparse.Namespace) -> int:
    from scripts.equivalent_static_load.verify import verify_case

    cfg = load_config(args.config)
    case_dir = cfg.outputs.directory / f"case_{args.case}"
    if args.solved_rst:
        from scripts.equivalent_static_load.io_dpf import read_solved_field_from_rst

        solved = read_solved_field_from_rst(args.solved_rst, set_id=args.set)
    else:
        solved = Path(args.solved_field)
    result = verify_case(cfg, case_dir, solved, log=print)
    print(json.dumps({"accepted": result.accepted, "lambda_corr": result.lambda_corr}, indent=2))
    return 0 if result.accepted else 4


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        from scripts.equivalent_static_load.gui import run_gui

        return run_gui()
    handlers = {
        "make-synthetic": _cmd_make_synthetic,
        "check": _cmd_check,
        "suggest-instants": _cmd_suggest_instants,
        "resultants": _cmd_resultants,
        "derive": _cmd_derive,
        "verify": _cmd_verify,
    }
    try:
        return handlers[args.command](args)
    except (ConfigError, InputError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    except SolveError as exc:
        print(f"SOLVE ERROR: {exc}", file=sys.stderr)
        return 3
    except EslError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    if __package__ in (None, ""):
        sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    raise SystemExit(main())

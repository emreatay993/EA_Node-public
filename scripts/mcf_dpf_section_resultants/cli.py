# Purpose: Command-line interface for the MCF DPF section resultants tool.
# Map: subsystems/packaging_generated_assets
# Tests: tests/test_mcf_dpf_section_resultants_gui.py
"""Standalone DPF section resultant extractor.

This tool extracts section forces and moments from either:

- a modal ``file.rst`` containing modal nodal force output, and
- a transient MSUP ``file.mcf`` containing modal coordinates, or
- one result set in a Static Structural ``file.rst``.

It mirrors the Mechanical construction-surface probe convention verified for
this example project, while staying usable as a standalone Slurm post job.
Run without ``--cli`` to open the PyQt GUI, or run with ``--cli`` for batch use.
"""

from __future__ import annotations

import argparse
import csv
import errno
import json
import math
import os
import re
import sys
import tempfile
import traceback
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from time import perf_counter
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

from scripts.mcf_dpf_section_resultants.core import *
from scripts.mcf_dpf_section_resultants.extraction import *

def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=SCRIPT_DESCRIPTION)
    parser.add_argument("--cli", action="store_true", help="Run extraction without opening the GUI.")
    parser.add_argument("--config", help="JSON config path.")
    parser.add_argument("--write-default-config", help="Write a default JSON config and exit.")
    parser.add_argument(
        "--rst",
        "--modal-rst",
        dest="modal_rst",
        help="RST path override.",
    )
    parser.add_argument(
        "--analysis-mode",
        choices=["modal", "static"],
        help="Extraction mode. Defaults to modal unless supplied by the config.",
    )
    parser.add_argument(
        "--result-set-id",
        type=int,
        help="Cumulative DPF result-set ID required for Static Structural mode.",
    )
    parser.add_argument(
        "--static-set-scope",
        choices=["single", "range", "all"],
        help="Static cumulative-set selection mode.",
    )
    parser.add_argument("--result-set-start", type=int, help="First cumulative set in Range mode.")
    parser.add_argument("--result-set-end", type=int, help="Last cumulative set in Range mode.")
    parser.add_argument("--result-set-stride", type=int, help="Cumulative-set stride in Range mode.")
    parser.add_argument("--mcf", help="Transient MCF path override.")
    parser.add_argument("--out-csv", help="Output CSV path override.")
    parser.add_argument("--element-named-selection", help="Element named selection override.")
    parser.add_argument(
        "--origin",
        nargs=3,
        type=float,
        metavar=("X_MM", "Y_MM", "Z_MM"),
        help="Coordinate-system origin in millimeters.",
    )
    parser.add_argument(
        "--reference-frame-motion",
        choices=["fixed", "follow-geometry"],
        help="Keep the initial frame global or transport it with the selected geometry.",
    )
    parser.add_argument(
        "--reference-frame-attachment",
        help=(
            "Optional NODE/ELEMENT named-selection attachment override. Empty uses "
            "the initial local section-cut neighborhood."
        ),
    )
    parser.add_argument(
        "--frame-fit-warning-ratio",
        type=float,
        help="Warn-and-continue RMS rigid-fit residual divided by tracking span.",
    )
    parser.add_argument("--normal-axis", choices=["x", "y", "z"], help="Local section normal axis.")
    parser.add_argument("--side", choices=["positive", "negative", "both"], help="Extraction side.")
    parser.add_argument(
        "--modal-summation-batch-size",
        type=int,
        help=(
            "Maximum modal sets per DPF force_summation batch. "
            f"Default: {DEFAULT_MODAL_SUMMATION_BATCH_SIZE}."
        ),
    )
    parser.add_argument(
        "--skip-first-modes",
        type=int,
        help="Drop the first N MCF modal coordinate columns and RST modal set IDs before summation.",
    )
    return parser


def config_from_args(args: argparse.Namespace) -> SectionConfig:
    cfg = load_config(args.config) if args.config else SectionConfig()
    if args.analysis_mode:
        cfg.analysis_mode = args.analysis_mode
    if args.result_set_id is not None:
        cfg.result_set_id = args.result_set_id
    if args.static_set_scope:
        cfg.static_set_scope = args.static_set_scope
    if args.result_set_start is not None:
        cfg.result_set_range_start = args.result_set_start
    if args.result_set_end is not None:
        cfg.result_set_range_end = args.result_set_end
    if args.result_set_stride is not None:
        cfg.result_set_range_stride = args.result_set_stride
    if args.modal_rst:
        cfg.modal_rst = args.modal_rst
    if args.mcf:
        cfg.mcf = args.mcf
    if args.out_csv:
        cfg.out_csv = args.out_csv
    if args.element_named_selection:
        cfg.element_named_selection = args.element_named_selection
    if args.origin:
        cfg.coordinate_system_origin = [float(value) for value in args.origin]
    if args.reference_frame_motion:
        cfg.reference_frame_motion = args.reference_frame_motion
    if args.reference_frame_attachment is not None:
        cfg.reference_frame_attachment_selection = args.reference_frame_attachment
    if args.frame_fit_warning_ratio is not None:
        cfg.reference_frame_fit_warning_ratio = args.frame_fit_warning_ratio
    if args.normal_axis:
        cfg.section_normal_axis = args.normal_axis
    if args.side:
        cfg.extraction_side = args.side
    if args.modal_summation_batch_size is not None:
        cfg.modal_summation_batch_size = args.modal_summation_batch_size
    if args.skip_first_modes is not None:
        cfg.skip_first_modes = args.skip_first_modes
    return config_from_mapping(asdict(cfg))


def print_summary_for_cli(summary: Dict[str, Any]) -> None:
    print(f"CSV: {summary['out_csv']}")
    print(f"Summary: {summary['summary_json']}")
    print(f"Result rows: {summary['time_point_count']}")
    if summary.get("analysis_mode") == "static":
        selected_sets = summary.get("selected_result_sets") or []
        print("Result sets: " + ", ".join(str(item.get("id")) for item in selected_sets))
    else:
        print(f"Modes used: {summary['modes_used']}")
    local = summary.get("max_abs_resultant_local", {})
    print(
        "Max abs local: "
        f"Fx={local.get('fx', 0.0):.6g}, "
        f"Fy={local.get('fy', 0.0):.6g}, "
        f"Fz={local.get('fz', 0.0):.6g}, "
        f"Mx={local.get('mx', 0.0):.6g}, "
        f"My={local.get('my', 0.0):.6g}, "
        f"Mz={local.get('mz', 0.0):.6g}"
    )


def run_cli(args: argparse.Namespace) -> int:
    if args.write_default_config:
        save_config(args.write_default_config, SectionConfig())
        print(f"Wrote default config: {args.write_default_config}")
        return 0
    cfg = config_from_args(args)
    summary = extract_section_resultants(cfg, lambda message: print(message, flush=True))
    print_summary_for_cli(summary)
    return 0

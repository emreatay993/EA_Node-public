# Purpose: Standalone MAPDL/DPF helper for creating reduced Ansys .rst files.
# Map: subsystems/supporting_runtime_assets
# Tests: tests/test_rst_subset_tool.py

from __future__ import annotations

import argparse
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Sequence

from PyQt6.QtCore import Qt, QThread, QUrl, pyqtSignal
from PyQt6.QtGui import QAction, QColor, QDesktopServices, QPalette
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSizePolicy,
    QStyle,
    QToolButton,
    QVBoxLayout,
    QWidget,
)


DEFAULT_RESULT_ITEMS = ("ALL",)
RSPLIT_OUTPUT_COMPONENT = "RSTSUBSET"
INRES_ITEM_DESCRIPTIONS = {
    "ALL": "all stored result items",
    "BASIC": "basic nodal/element results",
    "NSOL": "nodal solution items",
    "RSOL": "reaction solution items",
    "ESOL": "element solution items",
    "NLOAD": "element nodal loads",
    "STRS": "stresses",
    "EPEL": "elastic strains",
    "EPPL": "plastic strains",
    "EPCR": "creep strains",
    "EPTH": "thermal strains",
    "MISC": "miscellaneous element items",
}
INRES_ITEM_ORDER = tuple(INRES_ITEM_DESCRIPTIONS)
RESULT_NAME_TO_INRES = (
    ("RSOL", ("reaction_force", "reaction_moment", "reaction")),
    ("NLOAD", ("elemental_nodal_force", "elemental_nodal_forces", "nodal_force", "nodal_forces")),
    ("STRS", ("stress",)),
    ("EPEL", ("elastic_strain",)),
    ("EPPL", ("plastic_strain",)),
    ("EPCR", ("creep_strain",)),
    ("EPTH", ("thermal_strain",)),
    ("NSOL", ("displacement", "structural_temperature", "temperature", "electric_potential", "voltage")),
    ("MISC", ("energy", "elemental_volume", "element_volume", "mass")),
)
LogFn = Callable[[str], None] | None
CancelFn = Callable[[], bool] | None


@dataclass(frozen=True)
class RstMetadata:
    set_ids: tuple[int, ...]
    times: tuple[float, ...]
    named_selections: tuple[str, ...]
    available_results: tuple[str, ...] = ()
    result_items: tuple[str, ...] = DEFAULT_RESULT_ITEMS
    unmapped_results: tuple[str, ...] = ()
    result_item_sources: tuple[tuple[str, tuple[str, ...]], ...] = ()


@dataclass(frozen=True)
class GuiRunConfig:
    rst: str
    out: str
    named_selection: str = ""
    time_mode: str = "all"
    set_ids: str = ""
    times: str = ""
    result_items: str = "ALL"
    mapdl_exe: str = ""
    deck_out: str = ""
    dry_run: bool = False
    overwrite: bool = False


def gui_config_to_namespace(config: GuiRunConfig) -> argparse.Namespace:
    return argparse.Namespace(
        rst=Path(config.rst),
        out=Path(config.out) if config.out else None,
        list=False,
        named_selection=config.named_selection.strip() or None,
        all_time_sets=config.time_mode == "all",
        set_ids=config.set_ids.strip() if config.time_mode == "sets" else None,
        times=config.times.strip() if config.time_mode == "times" else None,
        time_tolerance=1.0e-8,
        result_items=config.result_items.strip() or "ALL",
        mapdl_exe=Path(config.mapdl_exe) if config.mapdl_exe else None,
        dry_run=config.dry_run,
        deck_out=Path(config.deck_out) if config.deck_out else None,
        overwrite=config.overwrite,
    )


def parse_int_csv(text: str) -> tuple[int, ...]:
    values = tuple(int(part.strip()) for part in text.split(",") if part.strip())
    if not values:
        raise ValueError("Expected at least one set id.")
    if any(value < 1 for value in values):
        raise ValueError("Set ids are 1-based and must be positive.")
    return values


def parse_float_csv(text: str) -> tuple[float, ...]:
    values = tuple(float(part.strip()) for part in text.split(",") if part.strip())
    if not values:
        raise ValueError("Expected at least one time value.")
    return values


def parse_result_items(text: str | None) -> tuple[str, ...]:
    if not text:
        return DEFAULT_RESULT_ITEMS
    values = tuple(part.strip().upper() for part in text.split(",") if part.strip())
    if not values:
        raise ValueError("Expected at least one result item.")
    if len(values) > 8:
        raise ValueError("INRES accepts at most 8 result item labels.")
    for value in values:
        if not re.fullmatch(r"[A-Z0-9_]+", value):
            raise ValueError(f"Invalid INRES result item: {value!r}")
    return values


def delete_ranges(total_sets: int, keep_set_ids: Sequence[int]) -> list[tuple[int, int]]:
    keep = sorted(set(keep_set_ids))
    if total_sets < 1:
        raise ValueError("The result file has no result sets.")
    if not keep:
        raise ValueError("Refusing to delete every result set.")
    if keep[0] < 1 or keep[-1] > total_sets:
        raise ValueError(f"Requested set ids must be between 1 and {total_sets}.")

    ranges: list[tuple[int, int]] = []
    next_delete = 1
    for set_id in keep:
        if next_delete < set_id:
            ranges.append((next_delete, set_id - 1))
        next_delete = set_id + 1
    if next_delete <= total_sets:
        ranges.append((next_delete, total_sets))
    return ranges


def match_time_set_ids(
    stored_times: Sequence[float],
    requested_times: Sequence[float],
    tolerance: float,
) -> tuple[int, ...]:
    if not stored_times:
        raise ValueError("No time/frequency values were found in the result file.")
    matched: list[int] = []
    for requested in requested_times:
        best_index, best_time = min(
            enumerate(stored_times),
            key=lambda item: abs(float(item[1]) - requested),
        )
        best_delta = abs(float(best_time) - requested)
        limit = max(1.0, abs(requested)) * tolerance
        if best_delta > limit:
            raise ValueError(
                f"No stored result set matches time {requested:g} within tolerance {tolerance:g}; "
                f"nearest is set {best_index + 1} at {stored_times[best_index]:g}."
            )
        matched.append(best_index + 1)
    return tuple(sorted(set(matched)))


def _call_or_value(value: object) -> object:
    return value() if callable(value) else value


def _sequence(value: object) -> tuple[object, ...]:
    value = _call_or_value(value)
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    try:
        return tuple(value)  # type: ignore[arg-type]
    except TypeError:
        return (value,)


def _time_values(time_freq_support: object) -> tuple[float, ...]:
    holder = _call_or_value(getattr(time_freq_support, "time_frequencies", None))
    values: tuple[object, ...] = ()
    if holder is not None:
        data = _call_or_value(getattr(holder, "data", None))
        values = _sequence(data if data is not None else holder)
    return tuple(float(value) for value in values)


def _set_count(time_freq_support: object, times: Sequence[float]) -> int:
    for name in ("n_sets", "number_sets", "NumberSets"):
        value = _call_or_value(getattr(time_freq_support, name, None))
        if value:
            return int(value)
    return len(times)


def _named_selections(metadata: object) -> tuple[str, ...]:
    names: list[str] = []
    for owner in (metadata, getattr(metadata, "meshed_region", None)):
        if owner is None:
            continue
        names.extend(str(name) for name in _sequence(getattr(owner, "available_named_selections", None)))
    return tuple(dict.fromkeys(name for name in names if name))


def _result_name(value: object) -> str:
    for attr_name in ("name", "operator_name", "result_name"):
        attr_value = _call_or_value(getattr(value, attr_name, None))
        if attr_value:
            return str(attr_value)
    return str(value)


def _available_result_names(metadata: object) -> tuple[str, ...]:
    result_info = _call_or_value(getattr(metadata, "result_info", None))
    values = _sequence(getattr(result_info, "available_results", None))
    names = (_result_name(value).strip() for value in values)
    return tuple(dict.fromkeys(name for name in names if name and not name.startswith("<")))


def _normalized_result_name(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def map_available_results_to_inres(
    result_names: Sequence[str],
) -> tuple[tuple[str, ...], tuple[str, ...], tuple[tuple[str, tuple[str, ...]], ...]]:
    labels = ["ALL", "BASIC"]
    sources: dict[str, list[str]] = {}
    unmapped: list[str] = []
    for result_name in result_names:
        normalized = _normalized_result_name(result_name)
        matched = False
        for label, needles in RESULT_NAME_TO_INRES:
            if any(needle in normalized for needle in needles):
                if label not in labels:
                    labels.append(label)
                sources.setdefault(label, []).append(result_name)
                matched = True
        if not matched:
            unmapped.append(result_name)
    ordered = tuple(label for label in INRES_ITEM_ORDER if label in labels)
    ordered += tuple(label for label in labels if label not in ordered)
    return ordered, tuple(unmapped), tuple((label, tuple(values)) for label, values in sources.items())


def read_rst_metadata(rst_path: Path) -> RstMetadata:
    try:
        from ansys.dpf import core as dpf
    except ImportError as exc:  # pragma: no cover - depends on user Ansys environment
        raise RuntimeError("ansys-dpf-core is required for --list, --times, and --set-ids.") from exc

    model = dpf.Model(str(rst_path))
    support = model.metadata.time_freq_support
    times = _time_values(support)
    total_sets = _set_count(support, times)
    set_ids = tuple(range(1, total_sets + 1))
    if not times and total_sets:
        times = tuple(float("nan") for _ in set_ids)
    available_results = _available_result_names(model.metadata)
    result_items, unmapped_results, result_item_sources = map_available_results_to_inres(available_results)
    return RstMetadata(
        set_ids=set_ids,
        times=times,
        named_selections=_named_selections(model.metadata),
        available_results=available_results,
        result_items=result_items,
        unmapped_results=unmapped_results,
        result_item_sources=result_item_sources,
    )


def _apdl_token(value: str, label: str) -> str:
    token = value.strip()
    if not token or any(char in token for char in ",\r\n"):
        raise ValueError(f"{label} cannot be empty or contain commas/newlines.")
    return token


def build_apdl_deck(
    *,
    total_sets: int | None,
    keep_set_ids: Sequence[int] | None,
    named_selection: str | None,
    result_items: Sequence[str] = DEFAULT_RESULT_ITEMS,
    input_stem: str = "source",
    output_stem: str = RSPLIT_OUTPUT_COMPONENT,
) -> str:
    lines = [
        "/BATCH",
        "/COM, Generated by scripts/rst_subset_tool.py",
    ]

    if keep_set_ids is not None:
        if total_sets is None:
            raise ValueError("total_sets is required when trimming result sets.")
        ranges = delete_ranges(total_sets, keep_set_ids)
        if ranges:
            lines.extend(["/AUX3", f"FILEAUX3,{input_stem},rst"])
            for start, end in ranges:
                lines.append(f"DELETE,SET,{start},{end}")
            lines.extend(["COMPRESS", "FINISH"])

    if named_selection:
        component = _apdl_token(named_selection, "named selection")
        items = ",".join(result_items)
        lines.extend(
            [
                "/POST1",
                f"FILE,{input_stem},rst",
                "SET,LAST",
                "ALLSEL,ALL",
                "ESEL,NONE",
                "NSEL,NONE",
                f"CMSEL,S,{component}",
                "*GET,_RST_ECOUNT,ELEM,0,COUNT",
                "*GET,_RST_NCOUNT,NODE,0,COUNT",
                "*IF,_RST_ECOUNT,LE,0,THEN",
                "  *IF,_RST_NCOUNT,GT,0,THEN",
                "    ESLN,S,0,ALL",
                "    *GET,_RST_ECOUNT,ELEM,0,COUNT",
                "  *ENDIF",
                "*ENDIF",
                "*IF,_RST_ECOUNT,LE,0,THEN",
                "  *MSG,FATAL",
                "  Named selection did not resolve to any elements.",
                "*ENDIF",
                "NSLE,S,ALL",
                f"INRES,{items}",
                f"RSPLIT,ALL,ESEL,{output_stem}",
                "FINISH",
            ]
        )

    lines.append("/EXIT,NOSAVE")
    return "\n".join(lines) + "\n"


def find_mapdl_exe() -> Path | None:
    for env_name in ("ANSYS_MAPDL_EXE", "MAPDL_EXE"):
        value = os.environ.get(env_name)
        if value and Path(value).is_file():
            return Path(value)

    for env_name, value in sorted(os.environ.items(), reverse=True):
        if not env_name.startswith("AWP_ROOT"):
            continue
        version = env_name.removeprefix("AWP_ROOT")
        candidate = Path(value) / "ansys" / "bin" / "winx64" / f"ansys{version}.exe"
        if candidate.is_file():
            return candidate

    roots = [Path(value) for value in {os.environ.get("ProgramFiles"), r"C:\Program Files"} if value]
    candidates: list[Path] = []
    for root in roots:
        candidates.extend(root.glob(r"ANSYS Inc\v*\ansys\bin\winx64\ansys*.exe"))
    candidates = [path for path in candidates if re.fullmatch(r"ansys\d+\.exe", path.name, re.IGNORECASE)]
    return sorted(candidates, reverse=True)[0] if candidates else None


def _tail(path: Path, line_count: int = 80) -> str:
    if not path.exists():
        return ""
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    return "\n".join(lines[-line_count:])


def _log(log_fn: LogFn, text: str) -> None:
    if log_fn is not None:
        log_fn(text)
    else:
        print(text)


def run_mapdl(
    deck_path: Path,
    work_dir: Path,
    mapdl_exe: Path,
    *,
    force_smp: bool = False,
    log_fn: LogFn = None,
    cancel_check: CancelFn = None,
) -> None:
    log_path = work_dir / "mapdl.out"
    command = [
        str(mapdl_exe),
        "-b",
        "-i",
        str(deck_path),
        "-o",
        str(log_path),
        "-j",
        "rstsubset",
    ]
    if force_smp:
        command[1:1] = ["-smp", "-np", "1"]
    _log(log_fn, f"Running MAPDL: {mapdl_exe}")
    process = subprocess.Popen(
        command,
        cwd=work_dir,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    while process.poll() is None:
        if cancel_check and cancel_check():
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
            raise RuntimeError("Cancelled.")
        try:
            process.wait(timeout=0.2)
        except subprocess.TimeoutExpired:
            pass
    stdout_text = process.stdout.read() if process.stdout else ""
    if process.returncode:
        details = _tail(log_path) or stdout_text
        raise RuntimeError(f"MAPDL failed with exit code {process.returncode}.\n{details}")


def print_metadata(metadata: RstMetadata) -> None:
    print("Result sets:")
    for set_id, time_value in zip(metadata.set_ids, metadata.times):
        time_text = "unknown" if math.isnan(time_value) else f"{time_value:g}"
        print(f"  {set_id}: time/frequency={time_text}")
    print("Named selections:")
    if metadata.named_selections:
        for name in metadata.named_selections:
            print(f"  {name}")
    else:
        print("  <none reported by DPF>")
    print("Result items:")
    for label in metadata.result_items:
        print(f"  {label} - {INRES_ITEM_DESCRIPTIONS.get(label, 'available INRES group')}")
    if metadata.unmapped_results:
        print("Unmapped DPF results:")
        for name in metadata.unmapped_results:
            print(f"  {name}")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create smaller MAPDL-readable .rst files with /AUX3 and RSPLIT.",
    )
    parser.add_argument("--gui", action="store_true", help="Open the PyQt6 GUI.")
    parser.add_argument("--self-test", action="store_true", help="Run a no-GUI smoke test and exit.")
    parser.add_argument("--rst", type=Path, help="Source .rst file.")
    parser.add_argument("--out", type=Path, help="Output .rst file for extraction modes.")
    parser.add_argument("--list", action="store_true", help="List result sets and named selections with DPF.")
    parser.add_argument("--named-selection", help="APDL/Mechanical named selection or component to keep.")
    time_group = parser.add_mutually_exclusive_group()
    time_group.add_argument("--all-time-sets", action="store_true", help="Keep every stored result set.")
    time_group.add_argument("--set-ids", help="Comma-separated 1-based result set ids to keep.")
    time_group.add_argument("--times", help="Comma-separated stored time/frequency values to keep.")
    parser.add_argument(
        "--time-tolerance",
        type=float,
        default=1.0e-8,
        help="Relative-ish tolerance used when matching --times to stored sets.",
    )
    parser.add_argument(
        "--result-items",
        default="ALL",
        help="Comma-separated INRES labels for RSPLIT output, for example ALL or BASIC,NLOAD.",
    )
    parser.add_argument("--mapdl-exe", type=Path, help="MAPDL executable. Defaults to env/ANSYS install search.")
    parser.add_argument("--dry-run", action="store_true", help="Write the generated APDL deck without running MAPDL.")
    parser.add_argument("--deck-out", type=Path, help="Optional path for the generated APDL input deck.")
    parser.add_argument("--overwrite", action="store_true", help="Allow replacing an existing --out file.")
    return parser


def _validated_paths(args: argparse.Namespace) -> tuple[Path, Path | None]:
    if args.rst is None:
        raise ValueError("--rst is required unless --gui is used.")
    rst_path = args.rst.resolve()
    if not rst_path.is_file():
        raise ValueError(f"Source .rst does not exist: {rst_path}")
    if rst_path.suffix.lower() != ".rst":
        raise ValueError(f"Source file must have .rst extension: {rst_path}")

    out_path = args.out.resolve() if args.out else None
    if out_path is not None:
        if out_path.suffix.lower() != ".rst":
            raise ValueError(f"Output file must have .rst extension: {out_path}")
        if out_path.exists() and not args.overwrite:
            raise ValueError(f"Output already exists; pass --overwrite to replace it: {out_path}")
    return rst_path, out_path


def _selected_sets(args: argparse.Namespace, metadata: RstMetadata | None) -> tuple[int, ...] | None:
    if args.all_time_sets:
        return None
    if args.set_ids:
        if metadata is None:
            raise ValueError("DPF metadata is required for --set-ids.")
        set_ids = parse_int_csv(args.set_ids)
        delete_ranges(len(metadata.set_ids), set_ids)
        return tuple(sorted(set(set_ids)))
    if args.times:
        if metadata is None:
            raise ValueError("DPF metadata is required for --times.")
        return match_time_set_ids(metadata.times, parse_float_csv(args.times), args.time_tolerance)
    raise ValueError("Choose one of --all-time-sets, --set-ids, or --times.")


def run_cli(args: argparse.Namespace, *, log_fn: LogFn = None, cancel_check: CancelFn = None) -> int:
    rst_path, out_path = _validated_paths(args)

    if args.list:
        print_metadata(read_rst_metadata(rst_path))
        return 0
    if out_path is None:
        raise ValueError("--out is required unless --list is used.")
    if args.all_time_sets and not args.named_selection:
        raise ValueError("--all-time-sets without --named-selection would not reduce the result file.")

    needs_metadata = bool(args.set_ids or args.times)
    metadata = read_rst_metadata(rst_path) if needs_metadata else None
    keep_set_ids = _selected_sets(args, metadata)
    result_items = parse_result_items(args.result_items)
    if result_items != DEFAULT_RESULT_ITEMS and not args.named_selection:
        raise ValueError("--result-items only applies when RSPLIT is used with --named-selection.")

    total_sets = len(metadata.set_ids) if metadata else None
    deck = build_apdl_deck(
        total_sets=total_sets,
        keep_set_ids=keep_set_ids,
        named_selection=args.named_selection,
        result_items=result_items,
    )

    deck_out = args.deck_out.resolve() if args.deck_out else None
    if args.dry_run:
        deck_path = deck_out or out_path.with_suffix(".inp")
        deck_path.parent.mkdir(parents=True, exist_ok=True)
        deck_path.write_text(deck, encoding="utf-8")
        _log(log_fn, f"Wrote APDL deck: {deck_path}")
        return 0

    mapdl_exe = args.mapdl_exe or find_mapdl_exe()
    if mapdl_exe is None or not mapdl_exe.is_file():
        raise ValueError("MAPDL executable not found. Pass --mapdl-exe or set ANSYS_MAPDL_EXE.")

    with tempfile.TemporaryDirectory(prefix="rst_subset_") as temp_name:
        work_dir = Path(temp_name)
        source_copy = work_dir / "source.rst"
        _log(log_fn, f"Copying source RST to scratch folder: {source_copy}")
        shutil.copy2(rst_path, source_copy)
        deck_path = work_dir / "rst_subset.inp"
        deck_path.write_text(deck, encoding="utf-8")
        if deck_out:
            deck_out.parent.mkdir(parents=True, exist_ok=True)
            deck_out.write_text(deck, encoding="utf-8")
            _log(log_fn, f"Wrote APDL deck: {deck_out}")

        run_mapdl(
            deck_path,
            work_dir,
            mapdl_exe.resolve(),
            force_smp=bool(args.named_selection),
            log_fn=log_fn,
            cancel_check=cancel_check,
        )
        produced = work_dir / (f"{RSPLIT_OUTPUT_COMPONENT}.rst" if args.named_selection else "source.rst")
        if not produced.is_file():
            raise RuntimeError(f"MAPDL completed but did not produce expected result file: {produced}")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(produced, out_path)

    _log(log_fn, f"Wrote reduced RST: {out_path}")
    return 0


def engineering_palette() -> QPalette:
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor("#eef2f6"))
    palette.setColor(QPalette.ColorRole.WindowText, QColor("#1e2a36"))
    palette.setColor(QPalette.ColorRole.Base, QColor("#ffffff"))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor("#f6f8fb"))
    palette.setColor(QPalette.ColorRole.Text, QColor("#1e2a36"))
    palette.setColor(QPalette.ColorRole.Button, QColor("#ffffff"))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor("#1e2a36"))
    palette.setColor(QPalette.ColorRole.Highlight, QColor("#2d74c4"))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor("#203040"))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor("#ffffff"))
    palette.setColor(QPalette.ColorRole.PlaceholderText, QColor("#7d8a98"))
    return palette


def application_stylesheet() -> str:
    return """
    QWidget {
        background: #eef2f6;
        color: #1e2a36;
        font-family: "Segoe UI", Arial, sans-serif;
        font-size: 10pt;
        selection-background-color: #2d74c4;
        selection-color: #ffffff;
    }
    QLabel { background: transparent; }
    QLabel#TitleLabel {
        font-size: 20pt;
        font-weight: 700;
        color: #16212c;
    }
    QLabel#MutedLabel { color: #647386; }
    QLabel#StatusLabel {
        background: #eaf3ff;
        border: 1px solid #bad5f4;
        border-radius: 6px;
        padding: 8px 10px;
        color: #214c77;
        font-weight: 600;
    }
    QFrame#Panel, QGroupBox {
        background: #ffffff;
        border: 1px solid #d3dce7;
        border-radius: 6px;
    }
    QGroupBox {
        margin-top: 10px;
        padding: 12px 10px 10px 10px;
        font-weight: 650;
    }
    QGroupBox::title {
        subcontrol-origin: margin;
        left: 12px;
        padding: 0 4px;
    }
    QLineEdit, QComboBox, QListWidget {
        background: #ffffff;
        border: 1px solid #b9c5d0;
        border-radius: 5px;
        padding: 6px 8px;
    }
    QLineEdit, QComboBox {
        min-height: 22px;
    }
    QCheckBox, QRadioButton {
        min-height: 22px;
        background: transparent;
    }
    QPushButton, QToolButton {
        min-height: 24px;
    }
    QPlainTextEdit#RunLog {
        background: #101b24;
        color: #d7e7f3;
        border: 1px solid #223646;
        border-radius: 6px;
        font-family: Consolas, "Cascadia Mono", monospace;
        font-size: 9pt;
    }
    QPushButton, QToolButton {
        background: #f8fbfd;
        border: 1px solid #b8c7d4;
        border-radius: 5px;
        padding: 8px 12px;
        min-width: 92px;
    }
    QPushButton:hover, QToolButton:hover {
        background: #eaf4fb;
        border-color: #5f9cc7;
    }
    QPushButton:disabled, QToolButton:disabled {
        color: #8a98a3;
        background: #eef2f5;
        border-color: #d5dde4;
    }
    QPushButton#PrimaryButton {
        background: #2d74c4;
        color: #ffffff;
        border-color: #2362aa;
        font-weight: 650;
    }
    QPushButton#PrimaryButton:hover { background: #3584db; }
    QProgressBar {
        background: #e3ebf1;
        border: 1px solid #bac8d3;
        border-radius: 6px;
        min-height: 24px;
        text-align: center;
        color: #173041;
        font-weight: 650;
    }
    QProgressBar::chunk {
        background: #24a3c7;
        border-radius: 5px;
    }
    """


class MetadataWorker(QThread):
    completed = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, rst_path: Path) -> None:
        super().__init__()
        self.rst_path = rst_path

    def run(self) -> None:  # type: ignore[override]
        try:
            self.completed.emit(read_rst_metadata(self.rst_path))
        except Exception as exc:  # pragma: no cover - Qt thread boundary
            self.failed.emit(str(exc))


class RstSubsetWorker(QThread):
    log = pyqtSignal(str)
    completed = pyqtSignal(int)
    failed = pyqtSignal(str)

    def __init__(self, args: argparse.Namespace) -> None:
        super().__init__()
        self.args = args
        self._cancel_requested = False

    def request_cancel(self) -> None:
        self._cancel_requested = True

    def run(self) -> None:  # type: ignore[override]
        try:
            self.completed.emit(run_cli(self.args, log_fn=self.log.emit, cancel_check=lambda: self._cancel_requested))
        except Exception as exc:  # pragma: no cover - Qt thread boundary
            self.failed.emit(str(exc))


class RstSubsetWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.metadata_worker: MetadataWorker | None = None
        self.run_worker: RstSubsetWorker | None = None
        self._result_items_updating = False
        self.setWindowTitle("RST Subset Tool")
        self.resize(1120, 760)
        self.setMinimumSize(880, 620)
        self._build_ui()

    def _build_ui(self) -> None:
        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(22, 18, 22, 18)
        root.setSpacing(12)

        title_row = QHBoxLayout()
        title_col = QVBoxLayout()
        title = QLabel("RST Subset Tool")
        title.setObjectName("TitleLabel")
        subtitle = QLabel("Create MAPDL-readable reduced .rst files with APDL/DPF")
        subtitle.setObjectName("MutedLabel")
        title_col.addWidget(title)
        title_col.addWidget(subtitle)
        title_row.addLayout(title_col, 1)
        self.open_output_button = QPushButton("Open Output")
        self.open_output_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_DirOpenIcon))
        self.open_output_button.clicked.connect(self._open_output)
        title_row.addWidget(self.open_output_button)
        root.addLayout(title_row)

        form_content = QWidget()
        form_layout = QVBoxLayout(form_content)
        form_layout.setContentsMargins(0, 0, 0, 0)
        form_layout.setSpacing(12)

        files_panel = QFrame()
        files_panel.setObjectName("Panel")
        files_layout = QGridLayout(files_panel)
        files_layout.setContentsMargins(14, 14, 14, 14)
        files_layout.setHorizontalSpacing(10)
        files_layout.setVerticalSpacing(10)
        self.rst_edit = QLineEdit()
        self.rst_edit.setPlaceholderText("Source file.rst")
        self.out_edit = QLineEdit()
        self.out_edit.setPlaceholderText("Output reduced .rst")
        self.mapdl_edit = QLineEdit()
        self.mapdl_edit.setPlaceholderText("Optional MAPDL executable")
        found_mapdl = find_mapdl_exe()
        if found_mapdl:
            self.mapdl_edit.setText(os.fspath(found_mapdl))
        self.deck_edit = QLineEdit()
        self.deck_edit.setPlaceholderText("Optional APDL deck output path")
        self._add_file_row(files_layout, 0, "Source RST", self.rst_edit, self._choose_rst)
        self._add_file_row(files_layout, 1, "Output RST", self.out_edit, self._choose_out)
        self._add_file_row(files_layout, 2, "MAPDL", self.mapdl_edit, self._choose_mapdl)
        self._add_file_row(files_layout, 3, "APDL deck", self.deck_edit, self._choose_deck)
        files_layout.setColumnStretch(1, 1)
        form_layout.addWidget(files_panel)

        middle = QHBoxLayout()
        controls_box = QGroupBox("Extraction")
        controls_box.setMinimumHeight(250)
        controls_layout = QGridLayout(controls_box)
        controls_layout.setHorizontalSpacing(10)
        controls_layout.setVerticalSpacing(8)
        self.named_selection_combo = QComboBox()
        self.named_selection_combo.setEditable(True)
        self.named_selection_combo.setToolTip("Choose the named selection/component used for RSPLIT or later Mechanical scoping.")
        self.named_selection_combo.currentIndexChanged.connect(lambda _index: self._sync_result_items_enabled())
        self.named_selection_combo.currentTextChanged.connect(lambda _text: self._sync_result_items_enabled())
        self.spatial_subset_checkbox = QCheckBox("Create split RST with RSPLIT")
        self.spatial_subset_checkbox.setToolTip(
            "Off: full-mesh RST for normal Mechanical result objects, reduced only by selected result sets/times. "
            "On: smaller RST created with MAPDL RSPLIT. For Mechanical read-back use the v2024 R1+ beta Result "
            "File workflow: dummy analysis, Mesh Source = Result File, and Result File Item scoping."
        )
        self.spatial_subset_checkbox.toggled.connect(self._spatial_subset_toggled)
        self.all_sets_radio = QRadioButton("All stored result sets")
        self.set_ids_radio = QRadioButton("Selected set IDs")
        self.times_radio = QRadioButton("Selected stored times")
        self.all_sets_radio.setChecked(True)
        self.set_ids_edit = QLineEdit()
        self.set_ids_edit.setPlaceholderText("Example: 3,7,11")
        self.times_edit = QLineEdit()
        self.times_edit.setPlaceholderText("Example: 0.1,0.25,0.5")
        self.result_items_button = QToolButton()
        self.result_items_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.result_items_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        self.result_items_button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.result_items_menu = QMenu(self.result_items_button)
        self.result_items_button.setMenu(self.result_items_menu)
        self.result_item_actions: dict[str, QAction] = {}
        self.advanced_result_items_checkbox = QCheckBox("Advanced INRES labels")
        self.result_items_edit = QLineEdit("ALL")
        self.result_items_edit.setPlaceholderText("Manual INRES labels, for example ALL or BASIC,NLOAD")
        self.result_items_edit.setVisible(False)
        self.advanced_result_items_checkbox.toggled.connect(self.result_items_edit.setVisible)
        self.advanced_result_items_checkbox.toggled.connect(lambda _checked: self._sync_result_items_enabled())
        self.dry_run_checkbox = QCheckBox("Dry run: write APDL deck only")
        self.overwrite_checkbox = QCheckBox("Overwrite existing output")
        self._populate_result_items(("NSOL",))
        self._sync_result_items_enabled()
        controls_layout.addWidget(QLabel("Mechanical scope"), 0, 0)
        controls_layout.addWidget(self.named_selection_combo, 0, 1)
        controls_layout.addWidget(self.spatial_subset_checkbox, 1, 0, 1, 2)
        controls_layout.addWidget(self.all_sets_radio, 2, 0, 1, 2)
        controls_layout.addWidget(self.set_ids_radio, 3, 0)
        controls_layout.addWidget(self.set_ids_edit, 3, 1)
        controls_layout.addWidget(self.times_radio, 4, 0)
        controls_layout.addWidget(self.times_edit, 4, 1)
        result_items_label = QLabel("RSPLIT result items")
        controls_layout.addWidget(result_items_label, 5, 0)
        controls_layout.addWidget(self.result_items_button, 5, 1)
        controls_layout.addWidget(self.advanced_result_items_checkbox, 6, 1)
        controls_layout.addWidget(self.result_items_edit, 7, 1)
        controls_layout.addWidget(self.dry_run_checkbox, 8, 0, 1, 2)
        controls_layout.addWidget(self.overwrite_checkbox, 9, 0, 1, 2)
        controls_layout.setColumnStretch(1, 1)
        middle.addWidget(controls_box, 2)

        metadata_box = QGroupBox("RST Metadata")
        metadata_box.setMinimumHeight(250)
        metadata_layout = QVBoxLayout(metadata_box)
        self.scan_button = QPushButton("Scan RST")
        self.scan_button.clicked.connect(self._scan_rst)
        self.metadata_list = QListWidget()
        self.metadata_list.setMinimumHeight(132)
        self.metadata_list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self.metadata_list.itemSelectionChanged.connect(self._sync_selected_sets)
        self._sync_mode_controls()
        metadata_layout.addWidget(self.scan_button)
        metadata_layout.addWidget(self.metadata_list, 1)
        middle.addWidget(metadata_box, 1)
        form_layout.addLayout(middle)

        form_scroll = QScrollArea()
        form_scroll.setObjectName("FormScroll")
        form_scroll.setWidgetResizable(True)
        form_scroll.setFrameShape(QFrame.Shape.NoFrame)
        form_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        form_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        form_scroll.setWidget(form_content)
        root.addWidget(form_scroll, 3)

        action_row = QHBoxLayout()
        self.run_button = QPushButton("Run")
        self.run_button.setObjectName("PrimaryButton")
        self.run_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay))
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_BrowserStop))
        self.cancel_button.setEnabled(False)
        self.run_button.clicked.connect(self._run)
        self.cancel_button.clicked.connect(self._cancel)
        action_row.addWidget(self.run_button)
        action_row.addWidget(self.cancel_button)
        action_row.addStretch(1)
        root.addLayout(action_row)

        self.status_label = QLabel("Ready")
        self.status_label.setObjectName("StatusLabel")
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 1)
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("Ready")
        self.log_edit = QPlainTextEdit()
        self.log_edit.setObjectName("RunLog")
        self.log_edit.setReadOnly(True)
        self.log_edit.setMaximumBlockCount(5000)
        self.log_edit.setMinimumHeight(82)
        self.log_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        root.addWidget(self.status_label)
        root.addWidget(self.progress_bar)
        root.addWidget(self.log_edit, 1)
        self.setCentralWidget(central)

    def _add_file_row(self, layout: QGridLayout, row: int, label: str, edit: QLineEdit, slot: Callable[[], None]) -> None:
        button = QPushButton("Browse")
        button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_DirOpenIcon))
        button.clicked.connect(slot)
        layout.addWidget(QLabel(label), row, 0)
        layout.addWidget(edit, row, 1)
        layout.addWidget(button, row, 2)

    def _populate_result_items(
        self,
        result_items: Sequence[str],
        sources: dict[str, Sequence[str]] | None = None,
    ) -> None:
        sources = sources or {}
        labels = tuple(dict.fromkeys(("ALL", "BASIC", "NSOL", *result_items)))
        ordered = tuple(label for label in INRES_ITEM_ORDER if label in labels)
        ordered += tuple(label for label in labels if label not in ordered)
        self._result_items_updating = True
        self.result_items_menu.clear()
        self.result_item_actions.clear()
        for label in ordered:
            description = INRES_ITEM_DESCRIPTIONS.get(label, "available INRES group")
            action = self.result_items_menu.addAction(f"{label} - {description}")
            action.setCheckable(True)
            action.setChecked(label == "ALL")
            action.setData(label)
            source_names = sources.get(label, ())
            if source_names:
                action.setToolTip("Detected from DPF results: " + ", ".join(source_names))
            action.toggled.connect(lambda checked, item_label=label: self._result_item_toggled(item_label, checked))
            self.result_item_actions[label] = action
        self._result_items_updating = False
        self._refresh_result_items_button()

    def _result_item_toggled(self, changed_label: str, checked: bool) -> None:
        if self._result_items_updating:
            return
        if not checked:
            if not any(action.isChecked() for action in self.result_item_actions.values()):
                self._result_items_updating = True
                self.result_item_actions["ALL"].setChecked(True)
                self._result_items_updating = False
            self._refresh_result_items_button()
            return
        self._result_items_updating = True
        for label, action in self.result_item_actions.items():
            if changed_label == "ALL" and label != "ALL":
                action.setChecked(False)
            elif changed_label != "ALL" and label == "ALL":
                action.setChecked(False)
        self._result_items_updating = False
        self._refresh_result_items_button()

    def _check_only_result_item(self, selected_label: str) -> None:
        action = self.result_item_actions.get(selected_label)
        if action is None:
            return
        self._result_items_updating = True
        for label, item_action in self.result_item_actions.items():
            item_action.setChecked(label == selected_label)
        self._result_items_updating = False
        self._refresh_result_items_button()

    def _spatial_subset_toggled(self, checked: bool) -> None:
        if checked:
            self._check_only_result_item("NSOL")
        self._sync_mode_controls()

    def _sync_mode_controls(self) -> None:
        split_mode = self.spatial_subset_checkbox.isChecked()
        if split_mode:
            self.all_sets_radio.setChecked(True)
            self.metadata_list.clearSelection()
        for widget in (self.set_ids_radio, self.times_radio, self.set_ids_edit, self.times_edit):
            widget.setEnabled(not split_mode)
        self.metadata_list.setSelectionMode(
            QListWidget.SelectionMode.NoSelection if split_mode else QListWidget.SelectionMode.ExtendedSelection
        )
        self._sync_result_items_enabled()

    def _refresh_result_items_button(self) -> None:
        selected = [
            label
            for label, action in self.result_item_actions.items()
            if action.isChecked()
        ]
        text = "ALL" if not selected or "ALL" in selected else ", ".join(selected)
        self.result_items_button.setText(text)
        self.result_items_button.setToolTip("Select INRES result groups from the scanned RST metadata.")

    def _selected_result_items_text(self) -> str:
        if not (self.spatial_subset_checkbox.isChecked() and self._selected_named_selection()):
            return "ALL"
        manual = self.result_items_edit.text().strip()
        if self.advanced_result_items_checkbox.isChecked() and manual:
            return manual
        checked = [label for label, action in self.result_item_actions.items() if action.isChecked()]
        return "ALL" if not checked or "ALL" in checked else ",".join(checked)

    def _sync_result_items_enabled(self) -> None:
        enabled = self.spatial_subset_checkbox.isChecked() and bool(self._selected_named_selection())
        self.result_items_button.setEnabled(enabled)
        self.advanced_result_items_checkbox.setEnabled(enabled)
        self.result_items_edit.setEnabled(enabled and self.advanced_result_items_checkbox.isChecked())

    def _selected_named_selection(self) -> str:
        text = self.named_selection_combo.currentText().strip()
        if text != self.named_selection_combo.itemText(self.named_selection_combo.currentIndex()).strip():
            return text
        data = self.named_selection_combo.currentData()
        if data is not None:
            return str(data).strip()
        return "" if text == "Whole model (no spatial subset)" else text

    def _choose_rst(self) -> None:
        path, _filter = QFileDialog.getOpenFileName(self, "Select RST file", "", "Ansys RST (*.rst);;All Files (*)")
        if path:
            self.rst_edit.setText(path)
            if not self.out_edit.text().strip():
                rst_path = Path(path)
                self.out_edit.setText(os.fspath(rst_path.with_name(f"{rst_path.stem}_subset.rst")))

    def _choose_out(self) -> None:
        path, _filter = QFileDialog.getSaveFileName(self, "Select output RST", "", "Ansys RST (*.rst);;All Files (*)")
        if path:
            self.out_edit.setText(path)

    def _choose_mapdl(self) -> None:
        path, _filter = QFileDialog.getOpenFileName(self, "Select MAPDL executable", "", "Executable (*.exe);;All Files (*)")
        if path:
            self.mapdl_edit.setText(path)

    def _choose_deck(self) -> None:
        path, _filter = QFileDialog.getSaveFileName(self, "Select APDL deck path", "", "APDL input (*.inp);;All Files (*)")
        if path:
            self.deck_edit.setText(path)

    def _config(self) -> GuiRunConfig:
        time_mode = "all"
        if self.set_ids_radio.isChecked():
            time_mode = "sets"
        elif self.times_radio.isChecked():
            time_mode = "times"
        named_selection = self._selected_named_selection() if self.spatial_subset_checkbox.isChecked() else ""
        return GuiRunConfig(
            rst=self.rst_edit.text().strip(),
            out=self.out_edit.text().strip(),
            named_selection=named_selection,
            time_mode=time_mode,
            set_ids=self.set_ids_edit.text().strip(),
            times=self.times_edit.text().strip(),
            result_items=self._selected_result_items_text(),
            mapdl_exe=self.mapdl_edit.text().strip(),
            deck_out=self.deck_edit.text().strip(),
            dry_run=self.dry_run_checkbox.isChecked(),
            overwrite=self.overwrite_checkbox.isChecked(),
        )

    def _scan_rst(self) -> None:
        try:
            rst_path, _out = _validated_paths(argparse.Namespace(rst=Path(self.rst_edit.text().strip()), out=None, overwrite=True))
        except ValueError as exc:
            QMessageBox.warning(self, "Scan RST", str(exc))
            return
        self._set_busy(True, "Scanning RST metadata...")
        self.metadata_worker = MetadataWorker(rst_path)
        self.metadata_worker.completed.connect(self._metadata_loaded)
        self.metadata_worker.failed.connect(self._metadata_failed)
        self.metadata_worker.start()

    def _metadata_loaded(self, metadata: RstMetadata) -> None:
        self._set_busy(False, "RST metadata loaded.")
        self.named_selection_combo.clear()
        self.named_selection_combo.addItem("Whole model (no spatial subset)", "")
        for name in metadata.named_selections:
            self.named_selection_combo.addItem(name, name)
        self.named_selection_combo.setCurrentIndex(0)
        self._sync_result_items_enabled()
        self._populate_result_items(metadata.result_items, dict(metadata.result_item_sources))
        if self.spatial_subset_checkbox.isChecked():
            self._check_only_result_item("NSOL")
        self.metadata_list.clear()
        for set_id, time_value in zip(metadata.set_ids, metadata.times):
            time_text = "unknown" if math.isnan(time_value) else f"{time_value:g}"
            item = QListWidgetItem(f"{set_id}: time/frequency={time_text}")
            item.setData(Qt.ItemDataRole.UserRole, (set_id, time_text))
            self.metadata_list.addItem(item)
        self._append_log(
            f"Loaded {len(metadata.set_ids)} result sets, {len(metadata.named_selections)} named selections, "
            f"and {len(metadata.result_items)} result item groups."
        )
        if metadata.unmapped_results:
            self._append_log("Detected DPF results not mapped to INRES: " + ", ".join(metadata.unmapped_results))

    def _metadata_failed(self, details: str) -> None:
        self._set_busy(False, "RST metadata scan failed.")
        self._append_log(details)
        QMessageBox.critical(self, "Scan failed", details)

    def _sync_selected_sets(self) -> None:
        selected_ids: list[str] = []
        selected_times: list[str] = []
        if self.spatial_subset_checkbox.isChecked():
            return
        for item in self.metadata_list.selectedItems():
            set_id, time_text = item.data(Qt.ItemDataRole.UserRole)
            selected_ids.append(str(set_id))
            if time_text != "unknown":
                selected_times.append(str(time_text))
        if selected_ids:
            self.set_ids_edit.setText(",".join(selected_ids))
            self.set_ids_radio.setChecked(True)
        if selected_times:
            self.times_edit.setText(",".join(selected_times))

    def _run(self) -> None:
        try:
            scope_hint = self._selected_named_selection()
            if self.spatial_subset_checkbox.isChecked() and not self.all_sets_radio.isChecked():
                raise ValueError("RSPLIT mode writes all stored result sets. Turn RSPLIT off to trim by set or time.")
            if scope_hint and not self.spatial_subset_checkbox.isChecked() and self.all_sets_radio.isChecked():
                raise ValueError(
                    "Full-mesh mode keeps all elements. Choose selected set IDs/times, "
                    "or enable RSPLIT for a smaller element-only split result file."
                )
            args = gui_config_to_namespace(self._config())
            _validated_paths(args)
        except ValueError as exc:
            QMessageBox.warning(self, "Run extraction", str(exc))
            return
        self.run_worker = RstSubsetWorker(args)
        self.run_worker.log.connect(self._append_log)
        self.run_worker.completed.connect(self._run_completed)
        self.run_worker.failed.connect(self._run_failed)
        self._set_busy(True, "Running extraction...")
        self.run_worker.start()

    def _cancel(self) -> None:
        if self.run_worker and self.run_worker.isRunning():
            self.run_worker.request_cancel()
            self._append_log("Cancel requested.")
            self.cancel_button.setEnabled(False)

    def _run_completed(self, _code: int) -> None:
        self._set_busy(False, "Done.")
        self.run_worker = None
        QMessageBox.information(self, "RST subset complete", "RST subset operation completed.")

    def _run_failed(self, details: str) -> None:
        self._set_busy(False, "Failed.")
        self.run_worker = None
        self._append_log(details)
        QMessageBox.critical(self, "RST subset failed", details)

    def _set_busy(self, busy: bool, status: str) -> None:
        self.status_label.setText(status)
        self.progress_bar.setRange(0, 0 if busy else 1)
        self.progress_bar.setFormat(status)
        for widget in (
            self.scan_button,
            self.run_button,
            self.rst_edit,
            self.out_edit,
            self.mapdl_edit,
            self.deck_edit,
            self.spatial_subset_checkbox,
            self.all_sets_radio,
            self.set_ids_radio,
            self.times_radio,
            self.set_ids_edit,
            self.times_edit,
            self.metadata_list,
            self.result_items_button,
            self.advanced_result_items_checkbox,
            self.result_items_edit,
        ):
            widget.setEnabled(not busy)
        if not busy:
            self._sync_mode_controls()
        self.cancel_button.setEnabled(busy and self.run_worker is not None)

    def _append_log(self, text: str) -> None:
        self.log_edit.appendPlainText(text)

    def _open_output(self) -> None:
        path = Path(self.out_edit.text().strip())
        folder = path.parent if path.suffix else path
        if folder.exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(os.fspath(folder)))

    def closeEvent(self, event) -> None:  # type: ignore[override]
        if self.run_worker and self.run_worker.isRunning():
            self.run_worker.request_cancel()
            self.run_worker.wait(3000)
        if self.metadata_worker and self.metadata_worker.isRunning():
            self.metadata_worker.wait(3000)
        super().closeEvent(event)


def run_app(argv: Sequence[str] | None = None) -> int:
    app = QApplication.instance() or QApplication(list(argv or sys.argv[:1]))
    app.setApplicationName("RST Subset Tool")
    app.setStyle("Fusion")
    app.setPalette(engineering_palette())
    app.setStyleSheet(application_stylesheet())
    window = RstSubsetWindow()
    window.show()
    return app.exec()


def self_test() -> int:
    with tempfile.TemporaryDirectory(prefix="rst_subset_self_test_") as temp_name:
        root = Path(temp_name)
        rst = root / "file.rst"
        out = root / "subset.rst"
        deck = root / "subset.inp"
        rst.write_bytes(b"fake rst")
        args = gui_config_to_namespace(
            GuiRunConfig(
                rst=os.fspath(rst),
                out=os.fspath(out),
                named_selection="MY_NS",
                time_mode="all",
                dry_run=True,
                deck_out=os.fspath(deck),
            )
        )
        run_cli(args)
        deck_text = deck.read_text(encoding="utf-8")
        assert "CMSEL,S,MY_NS" in deck_text, deck_text
        assert "RSPLIT,ALL,ESEL,RSTSUBSET" in deck_text, deck_text
    print("RST Subset Tool self-test passed.")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        return run_app(sys.argv[:1])
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    if args.gui:
        return run_app(sys.argv[:1])
    if args.self_test:
        return self_test()
    try:
        return run_cli(args)
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

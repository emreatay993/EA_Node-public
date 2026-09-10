"""Single-file Mechanical button for placement-sensitivity calculation.

Mechanical user buttons execute IronPython, while the calculator needs CPython
with NumPy/Pandas/SciPy. This file embeds the CPython calculator as a string,
writes it to a temporary file when needed, and launches external CPython.
"""

import os
import sys
import tempfile


CORE_CODE = r'''"""Calculate SG placement sensitivity from local StrainX_around exports.

The Mechanical extraction script writes global node coordinates, local-x strain
components, SG coordinate systems, and SG grid body vertices. This script
rotates node positions into each SG local coordinate system, shifts the finite
grid footprint in local X/Y, and central-differences the averaged strain.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd


DEFAULT_STEP_MM = float(os.environ.get("SG_PLACEMENT_FINITE_DIFF_MM", "0.1"))
DEFAULT_SAMPLES_X = int(os.environ.get("SG_PLACEMENT_SAMPLES_X", "11"))
DEFAULT_SAMPLES_Y = int(os.environ.get("SG_PLACEMENT_SAMPLES_Y", "5"))


def channel_numbers(channel: str) -> tuple[str, str]:
    numbers = re.findall(r"\d+", str(channel))
    if len(numbers) < 2:
        raise ValueError(f"Cannot derive SG body name from channel {channel!r}.")
    return numbers[-2], numbers[-1]


def channel_key(name: str) -> str:
    first, second = channel_numbers(name)
    return f"{first}_{second}"


def channel_tokens(channel: str) -> list[str]:
    first, second = channel_numbers(channel)
    raw = str(channel)
    tokens = [
        raw,
        f"SG_Ch_{first}_{second}",
        f"SG{first}_{second}",
        f"Ch_{first}_{second}",
    ]
    return list(dict.fromkeys(tokens))


def body_name(channel: str) -> str:
    first, second = channel_numbers(channel)
    return f"SG_Grid_Body_{first}_{second}"


def cs_name(channel: str) -> str:
    first, second = channel_numbers(channel)
    return f"CS_SG_Ch_{first}_{second}"


def add_channel_alias(mapping: dict, name: str, value) -> None:
    mapping[str(name)] = value
    try:
        mapping.setdefault(channel_key(name), value)
    except ValueError:
        pass


def channel_lookup(mapping: dict, name: str):
    if name in mapping:
        return mapping[name]
    key = channel_key(name)
    if key in mapping:
        return mapping[key]
    raise KeyError(name)


def read_csv_flexible(path: Path) -> pd.DataFrame:
    try:
        df = pd.read_csv(path, sep="\t")
        if len(df.columns) > 1:
            return df
    except Exception:
        pass
    return pd.read_csv(path)


def find_column(columns: list[str], required: list[str], fallback: list[str] | None = None) -> str | None:
    fallback = fallback or []
    lowered = {column: column.lower().strip() for column in columns}
    for column, lower in lowered.items():
        if all(part in lower for part in required):
            return column
    for name in fallback:
        for column, lower in lowered.items():
            if lower == name.lower():
                return column
    return None


def load_coordinate_systems(folder: Path) -> dict[str, dict[str, np.ndarray]]:
    df = pd.read_csv(folder / "SG_coordinate_matrix.csv")
    systems = {}
    for _, row in df.iterrows():
        name = str(row["CS Name"])
        system = {
            "origin": np.array([row["Origin_X"], row["Origin_Y"], row["Origin_Z"]], dtype=float),
            "x": np.array([row["X_dir_i"], row["X_dir_j"], row["X_dir_k"]], dtype=float),
            "y": np.array([row["Y_dir_i"], row["Y_dir_j"], row["Y_dir_k"]], dtype=float),
            "z": np.array([row["Z_dir_i"], row["Z_dir_j"], row["Z_dir_k"]], dtype=float),
        }
        add_channel_alias(systems, name, system)
    return systems


def load_footprints(folder: Path) -> dict[str, tuple[float, float, float, float]]:
    df = pd.read_csv(folder / "SG_grid_body_vertices_in_local_CS.csv")
    footprints = {}
    for name, group in df.groupby("Body_Name"):
        x = pd.to_numeric(group["X_local [mm]"], errors="coerce")
        y = pd.to_numeric(group["Y_local [mm]"], errors="coerce")
        add_channel_alias(footprints, str(name), (float(x.min()), float(x.max()), float(y.min()), float(y.max())))
    return footprints


def load_global_vertices(folder: Path) -> dict[str, np.ndarray]:
    path = folder / "SG_grid_body_vertices.csv"
    if not path.exists():
        return {}
    df = pd.read_csv(path)
    vertices = {}
    for name, group in df.groupby("Body_Name"):
        xyz = group[["X [mm]", "Y [mm]", "Z [mm]"]].apply(pd.to_numeric, errors="coerce").dropna().to_numpy(dtype=float)
        if len(xyz):
            add_channel_alias(vertices, str(name), xyz)
    return vertices


def footprint_from_global_vertices(vertices: np.ndarray, system: dict[str, np.ndarray]) -> tuple[float, float, float, float]:
    axes = np.column_stack([system["x"], system["y"], system["z"]])
    local_xy = (vertices - system["origin"]).dot(axes)[:, :2]
    return (
        float(local_xy[:, 0].min()),
        float(local_xy[:, 0].max()),
        float(local_xy[:, 1].min()),
        float(local_xy[:, 1].max()),
    )


def export_folder(working_dir: str | Path | None) -> Path | None:
    if not working_dir:
        return None
    folder = Path(working_dir)
    if folder.name != "StrainX_around_each_SG":
        folder = folder / "StrainX_around_each_SG"
    return folder


def find_channel_file(folder: Path, channel: str) -> Path | None:
    candidates = []
    for token in channel_tokens(channel):
        candidates.extend([
            folder / f"StrainX_around_{token}_zeroed.csv",
            folder / f"StrainX_around_{token}.csv",
        ])
    for path in candidates:
        if path.exists():
            return path
    lowered_tokens = [token.lower() for token in channel_tokens(channel)]
    for path in sorted(folder.glob("StrainX_around_*.csv")):
        if path.name.startswith("Preload_"):
            continue
        lower = path.name.lower()
        if any(token in lower for token in lowered_tokens):
            return path
    return None


def load_local_field(path: Path, system: dict[str, np.ndarray]) -> tuple[np.ndarray, np.ndarray]:
    df = read_csv_flexible(path)
    columns = list(df.columns)
    x_col = find_column(columns, ["x", "location"], ["x [mm]", "x"])
    y_col = find_column(columns, ["y", "location"], ["y [mm]", "y"])
    z_col = find_column(columns, ["z", "location"], ["z [mm]", "z"])
    strain_col = find_column(columns, ["normal", "elastic", "strain"])
    if strain_col is None:
        strain_col = columns[-1]
    if x_col is None or y_col is None:
        raise ValueError(f"{path} does not contain X/Y location columns.")

    values = df[[x_col, y_col, strain_col] + ([z_col] if z_col else [])].apply(pd.to_numeric, errors="coerce").dropna()
    if z_col:
        global_xyz = values[[x_col, y_col, z_col]].to_numpy(dtype=float)
        axes = np.column_stack([system["x"], system["y"], system["z"]])
        local_xyz = (global_xyz - system["origin"]).dot(axes)
        local_xy = local_xyz[:, :2]
    else:
        local_xy = values[[x_col, y_col]].to_numpy(dtype=float)
    strain = values[strain_col].to_numpy(dtype=float)
    if len(strain) < 3:
        raise ValueError(f"{path} does not contain enough numeric strain points.")
    return local_xy, strain


def interpolate(local_xy: np.ndarray, strain: np.ndarray, sample_xy: np.ndarray) -> tuple[np.ndarray, str, str]:
    try:
        from scipy.interpolate import griddata  # type: ignore

        values = griddata(local_xy, strain, sample_xy, method="linear")
        warning = ""
        if np.any(~np.isfinite(values)):
            nearest = griddata(local_xy, strain, sample_xy, method="nearest")
            mask = ~np.isfinite(values)
            values[mask] = nearest[mask]
            warning = "Linear interpolation reached outside the exported strain cloud; nearest-neighbor fill was used."
        if not np.all(np.isfinite(values)):
            raise ValueError("Interpolation produced non-finite values.")
        return values, "griddata_linear_with_nearest_fill", warning
    except Exception as exc:
        x = local_xy[:, 0]
        y = local_xy[:, 1]
        design = np.column_stack([np.ones_like(x), x, y])
        coeffs, _, rank, _ = np.linalg.lstsq(design, strain, rcond=None)
        if rank < 3:
            raise ValueError("Local strain points are rank deficient; cannot interpolate placement sensitivity.") from exc
        values = np.column_stack([np.ones(len(sample_xy)), sample_xy[:, 0], sample_xy[:, 1]]).dot(coeffs)
        return values, "least_squares_plane_fallback", "SciPy interpolation was unavailable or failed; used a local plane fallback."


def sample_points(bounds: tuple[float, float, float, float], dx: float, dy: float, nx: int, ny: int) -> np.ndarray:
    xmin, xmax, ymin, ymax = bounds
    xs = np.linspace(xmin + dx, xmax + dx, max(2, nx))
    ys = np.linspace(ymin + dy, ymax + dy, max(2, ny))
    grid_x, grid_y = np.meshgrid(xs, ys)
    return np.column_stack([grid_x.ravel(), grid_y.ravel()])


def averaged_strain(
    local_xy: np.ndarray,
    strain: np.ndarray,
    bounds: tuple[float, float, float, float],
    dx: float,
    dy: float,
    nx: int,
    ny: int,
) -> tuple[float, str, str]:
    values, method, warning = interpolate(local_xy, strain, sample_points(bounds, dx, dy, nx, ny))
    return float(np.mean(values)), method, warning


def derivatives_for_channel(
    local_xy: np.ndarray,
    strain: np.ndarray,
    bounds: tuple[float, float, float, float],
    step_mm: float,
    nx: int,
    ny: int,
) -> tuple[float, float, str, str]:
    px, method_xp, warning_xp = averaged_strain(local_xy, strain, bounds, step_mm, 0.0, nx, ny)
    mx, method_xm, warning_xm = averaged_strain(local_xy, strain, bounds, -step_mm, 0.0, nx, ny)
    py, method_yp, warning_yp = averaged_strain(local_xy, strain, bounds, 0.0, step_mm, nx, ny)
    my, method_ym, warning_ym = averaged_strain(local_xy, strain, bounds, 0.0, -step_mm, nx, ny)
    gx = (px - mx) / (2.0 * step_mm)
    gy = (py - my) / (2.0 * step_mm)
    methods = {method_xp, method_xm, method_yp, method_ym}
    warnings = [text for text in [warning_xp, warning_xm, warning_yp, warning_ym] if text]
    return gx, gy, "+".join(sorted(methods)), " ".join(dict.fromkeys(warnings))


def blank_rows(metadata: dict) -> pd.DataFrame:
    rows = []
    for channel in metadata.get("channel_order", []):
        for unit_load in metadata.get("unit_load_systems", []):
            rows.append({
                "Channel": str(channel),
                "Load Case": str(unit_load.get("analysis_name", "")),
                "d_epsilon_d_x_per_mm": "",
                "d_epsilon_d_y_per_mm": "",
                "gradient_norm_per_mm": "",
                "Method": "not_computed",
                "Warning": "Placement sensitivity requires local StrainX_around_each_SG field exports.",
            })
    return pd.DataFrame(rows)


def missing_folder_warning(folder: Path | None, source: str) -> str:
    if folder is None:
        return "No local StrainX_around_each_SG export folder was provided."
    if source == "selected_solution_environment":
        return (
            f"Missing local export folder {folder}. Run "
            "get_local_strains_and_SG_geo_data_around_each_SG_grid.py in the "
            "currently selected solution environment before calculating placement sensitivity."
        )
    return f"Missing {folder}."


def missing_required_files(folder: Path) -> list[str]:
    missing = [
        str(folder / name)
        for name in ["SG_coordinate_matrix.csv", "SG_grid_body_vertices_in_local_CS.csv"]
        if not (folder / name).exists()
    ]
    if not any(path.name.startswith("StrainX_around_") for path in folder.glob("*.csv")):
        missing.append(str(folder / "StrainX_around_*.csv"))
    return missing


def default_local_strain_root(metadata_path: Path, local_strain_root: Path | None) -> tuple[Path | None, str]:
    if local_strain_root is not None:
        return local_strain_root, "selected_solution_environment"
    metadata_folder = export_folder(metadata_path.parent)
    if metadata_folder is not None and metadata_folder.is_dir():
        return metadata_path.parent, "metadata_folder"
    return None, "metadata_working_dir_fallback"


def calculate(metadata_path: Path, output_path: Path, step_mm: float, nx: int, ny: int, local_strain_root: Path | None = None) -> int:
    with metadata_path.open("r", encoding="utf-8-sig") as stream:
        metadata = json.load(stream)
    output = pd.read_csv(output_path) if output_path.exists() else blank_rows(metadata)
    for column in ["Channel", "Load Case", "d_epsilon_d_x_per_mm", "d_epsilon_d_y_per_mm", "gradient_norm_per_mm", "Method", "Warning"]:
        if column not in output.columns:
            output[column] = ""

    filled = 0
    local_strain_root, folder_source = default_local_strain_root(metadata_path, local_strain_root)
    selected_folder = export_folder(local_strain_root)
    folder_resolution = []
    for unit_load in metadata.get("unit_load_systems", []):
        load_name = str(unit_load.get("analysis_name", ""))
        folder = selected_folder or export_folder(str(unit_load.get("working_dir", "")))
        folder_resolution.append({
            "load_case": load_name,
            "source": folder_source,
            "folder": str(folder) if folder is not None else "",
        })
        if folder is None or not folder.is_dir():
            output.loc[output["Load Case"].astype(str) == load_name, "Warning"] = missing_folder_warning(folder, folder_source)
            continue
        missing_files = missing_required_files(folder)
        if missing_files:
            output.loc[output["Load Case"].astype(str) == load_name, "Warning"] = "Missing required local export file(s): " + "; ".join(missing_files)
            continue
        try:
            systems = load_coordinate_systems(folder)
            footprints = load_footprints(folder)
            global_vertices = load_global_vertices(folder)
        except Exception as exc:
            output.loc[output["Load Case"].astype(str) == load_name, "Warning"] = str(exc)
            continue
        for channel in [str(item) for item in metadata.get("channel_order", [])]:
            mask = (output["Channel"].astype(str) == channel) & (output["Load Case"].astype(str) == load_name)
            if not mask.any():
                output = pd.concat([output, pd.DataFrame([{"Channel": channel, "Load Case": load_name}])], ignore_index=True)
                mask = (output["Channel"].astype(str) == channel) & (output["Load Case"].astype(str) == load_name)
            try:
                system = channel_lookup(systems, cs_name(channel))
                try:
                    bounds = channel_lookup(footprints, body_name(channel))
                    footprint_warning = ""
                except KeyError:
                    bounds = footprint_from_global_vertices(channel_lookup(global_vertices, body_name(channel)), system)
                    footprint_warning = "Local footprint row was missing; computed footprint from SG_grid_body_vertices.csv."
                field_path = find_channel_file(folder, channel)
                if field_path is None:
                    raise FileNotFoundError(f"Missing StrainX_around export for {channel}.")
                local_xy, strain = load_local_field(field_path, system)
                gx, gy, method, warning = derivatives_for_channel(local_xy, strain, bounds, step_mm, nx, ny)
                output.loc[mask, "d_epsilon_d_x_per_mm"] = gx
                output.loc[mask, "d_epsilon_d_y_per_mm"] = gy
                output.loc[mask, "gradient_norm_per_mm"] = math.sqrt(gx * gx + gy * gy)
                output.loc[mask, "Method"] = f"finite_footprint_central_difference_{method}"
                output.loc[mask, "Warning"] = " ".join(text for text in [warning, footprint_warning] if text)
                filled += int(mask.sum())
            except Exception as exc:
                output.loc[mask, "Method"] = "not_computed"
                output.loc[mask, "Warning"] = str(exc)

    metadata.setdefault("placement_sensitivity", {})
    metadata["placement_sensitivity"].update({
        "file": str(output_path),
        "numeric_rows_filled": int(filled),
        "method": "finite_footprint_central_difference_local_xy",
        "selected_solution_working_dir": str(local_strain_root) if folder_source == "selected_solution_environment" and local_strain_root else "",
        "local_export_folder_source": folder_source,
        "local_export_folder_used": str(selected_folder) if selected_folder else "",
        "folder_resolution": folder_resolution,
        "finite_difference_step_mm": float(step_mm),
        "samples_x": int(nx),
        "samples_y": int(ny),
    })
    output.to_csv(output_path, index=False)
    with metadata_path.open("w", encoding="utf-8") as stream:
        json.dump(metadata, stream, indent=2)
    return filled


def write_field(path: Path, system: dict[str, np.ndarray], slope_x: float, slope_y: float, constant: float) -> None:
    rows = []
    local_x = np.linspace(-3.0, 3.0, 9)
    local_y = np.linspace(-3.0, 3.0, 9)
    for x in local_x:
        for y in local_y:
            global_xyz = system["origin"] + x * system["x"] + y * system["y"]
            rows.append({
                "Node Number": len(rows) + 1,
                "X Location (mm)": global_xyz[0],
                "Y Location (mm)": global_xyz[1],
                "Z Location (mm)": global_xyz[2],
                "Normal Elastic Strain (mm/mm)": constant + slope_x * x + slope_y * y,
            })
    pd.DataFrame(rows).to_csv(path, sep="\t", index=False)


def self_test() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        folder = root / "Selected_Solution" / "StrainX_around_each_SG"
        folder.mkdir(parents=True)
        rot = math.sqrt(0.5)
        systems = {
            "CS_SG_Ch_1_1": {
                "origin": np.array([0.0, 0.0, 0.0]),
                "x": np.array([1.0, 0.0, 0.0]),
                "y": np.array([0.0, 1.0, 0.0]),
                "z": np.array([0.0, 0.0, 1.0]),
            },
            "CS_SG_Ch_2_1": {
                "origin": np.array([10.0, -5.0, 2.0]),
                "x": np.array([rot, rot, 0.0]),
                "y": np.array([-rot, rot, 0.0]),
                "z": np.array([0.0, 0.0, 1.0]),
            },
        }
        pd.DataFrame([
            {"CS Name": name + ("(" if name == "CS_SG_Ch_2_1" else ""), "Origin_X": data["origin"][0], "Origin_Y": data["origin"][1], "Origin_Z": data["origin"][2],
             "X_dir_i": data["x"][0], "X_dir_j": data["x"][1], "X_dir_k": data["x"][2],
             "Y_dir_i": data["y"][0], "Y_dir_j": data["y"][1], "Y_dir_k": data["y"][2],
             "Z_dir_i": data["z"][0], "Z_dir_j": data["z"][1], "Z_dir_k": data["z"][2]}
            for name, data in systems.items()
        ]).to_csv(folder / "SG_coordinate_matrix.csv", index=False)
        local_vertices = []
        global_vertices = []
        for body, system_name in [("SG_Grid_Body_1_1", "CS_SG_Ch_1_1"), ("SG_Grid_Body_2_1", "CS_SG_Ch_2_1")]:
            for index, (x, y) in enumerate([(-1.0, -0.5), (1.0, -0.5), (1.0, 0.5), (-1.0, 0.5)], start=1):
                if body == "SG_Grid_Body_1_1":
                    local_vertices.append({"Body_Name": body, "Vertex_No": index, "X_local [mm]": x, "Y_local [mm]": y, "Z_local [mm]": 0.0})
                system = systems[system_name]
                global_xyz = system["origin"] + x * system["x"] + y * system["y"]
                global_vertices.append({"Body_Name": body, "Vertex_No": index, "X [mm]": global_xyz[0], "Y [mm]": global_xyz[1], "Z [mm]": global_xyz[2]})
        pd.DataFrame(local_vertices).to_csv(folder / "SG_grid_body_vertices_in_local_CS.csv", index=False)
        pd.DataFrame(global_vertices).to_csv(folder / "SG_grid_body_vertices.csv", index=False)
        write_field(folder / "StrainX_around_SG_Ch_1_1_zeroed.csv", systems["CS_SG_Ch_1_1"], 0.0, 0.0, 7.0)
        write_field(folder / "StrainX_around_SG_Ch_2_1(.csv", systems["CS_SG_Ch_2_1"], 4.0, 1.5, 2.0)
        metadata = {
            "channel_order": ["SG1_1", "SG2_1"],
            "unit_load_systems": [{"analysis_name": "Unit_Load_Study_LC_1", "working_dir": str(root / "Missing_Metadata_WorkingDir")}],
        }
        metadata_path = folder.parent / "strain_sensitivity_metadata.json"
        output_path = folder.parent / "strain_sensitivity_placement_sensitivity.csv"
        metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
        calculate(metadata_path, output_path, 0.1, 11, 5)
        result = pd.read_csv(output_path)
        sg1 = result[result["Channel"] == "SG1_1"].iloc[0]
        sg2 = result[result["Channel"] == "SG2_1"].iloc[0]
        assert abs(float(sg1["d_epsilon_d_x_per_mm"])) < 1e-10
        assert abs(float(sg1["d_epsilon_d_y_per_mm"])) < 1e-10
        assert abs(float(sg2["d_epsilon_d_x_per_mm"]) - 4.0) < 1e-10
        assert abs(float(sg2["d_epsilon_d_y_per_mm"]) - 1.5) < 1e-10


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--metadata", default="strain_sensitivity_metadata.json")
    parser.add_argument("--output", default="strain_sensitivity_placement_sensitivity.csv")
    parser.add_argument("--step-mm", type=float, default=DEFAULT_STEP_MM)
    parser.add_argument("--samples-x", type=int, default=DEFAULT_SAMPLES_X)
    parser.add_argument("--samples-y", type=int, default=DEFAULT_SAMPLES_Y)
    parser.add_argument("--local-strain-root", default="")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        print("self-test passed")
        return 0
    if args.step_mm <= 0:
        raise SystemExit("--step-mm must be positive")
    local_strain_root = Path(args.local_strain_root) if args.local_strain_root else None
    filled = calculate(Path(args.metadata), Path(args.output), args.step_mm, args.samples_x, args.samples_y, local_strain_root)
    message = f"wrote {args.output} with {filled} numeric placement-sensitivity rows"
    try:
        with Path(args.metadata).open("r", encoding="utf-8-sig") as stream:
            placement = json.load(stream).get("placement_sensitivity", {})
        if placement.get("local_export_folder_used"):
            message += f"\n\nLocal export folder source:\n{placement.get('local_export_folder_source', '')}"
            message += f"\n\nLocal export folder used:\n{placement.get('local_export_folder_used', '')}"
    except Exception:
        pass
    if filled == 0:
        try:
            warnings = pd.read_csv(args.output)["Warning"].dropna().astype(str)
            unique = [text for text in dict.fromkeys(warnings) if text.strip()]
            if unique:
                message += "\n\nFirst warnings:\n- " + "\n- ".join(unique[:5])
        except Exception:
            pass
    print(message)
    return 0


_exit_code = main()
if _exit_code:
    raise SystemExit(_exit_code)
'''


TITLE = "Calculate Placement Sensitivity from Local SG"


def is_ironpython():
    return sys.platform == "cli" or sys.version.lower().find("ironpython") >= 0


def quote_arg(value):
    text = str(value)
    if not text:
        return '""'
    if " " not in text and "\t" not in text and '"' not in text:
        return text
    result = '"'
    backslashes = 0
    for char in text:
        if char == "\\":
            backslashes += 1
        elif char == '"':
            result += "\\" * (backslashes * 2 + 1)
            result += char
            backslashes = 0
        else:
            result += "\\" * backslashes
            backslashes = 0
            result += char
    result += "\\" * (backslashes * 2)
    result += '"'
    return result


def candidate_project_folder():
    for name in ["project_path", "PROJECT_PATH"]:
        if name in globals() and globals()[name]:
            return str(globals()[name])
    return ""


def ask_project_folder():
    try:
        from System.Windows.Forms import OpenFileDialog, DialogResult

        dialog = OpenFileDialog()
        dialog.Title = "Select strain_sensitivity_metadata.json"
        dialog.Filter = "strain_sensitivity_metadata.json|strain_sensitivity_metadata.json|JSON files (*.json)|*.json|All files (*.*)|*.*"
        dialog.CheckFileExists = True
        dialog.Multiselect = False
        if dialog.ShowDialog() == DialogResult.OK:
            return os.path.dirname(str(dialog.FileName))
    except Exception:
        pass
    try:
        from System.Windows.Forms import FolderBrowserDialog, DialogResult

        dialog = FolderBrowserDialog()
        dialog.Description = "Select the folder containing strain_sensitivity_metadata.json"
        if dialog.ShowDialog() == DialogResult.OK:
            return str(dialog.SelectedPath)
    except Exception:
        pass
    return ""


def candidate_solution_working_dir():
    try:
        if "sol_selected_environment" in globals() and globals()["sol_selected_environment"]:
            working_dir = globals()["sol_selected_environment"].WorkingDir
            if working_dir:
                return str(working_dir)
    except Exception:
        pass
    return ""


def has_metadata(folder):
    return bool(folder) and os.path.exists(os.path.join(folder, "strain_sensitivity_metadata.json"))


def default_mechanical_args():
    if len(sys.argv) > 1:
        return sys.argv[1:]
    solution_working_dir = candidate_solution_working_dir()
    folder = solution_working_dir if has_metadata(solution_working_dir) else candidate_project_folder()
    if not has_metadata(folder):
        folder = ask_project_folder()
    if not folder:
        return []
    args = [
        "--metadata", os.path.join(folder, "strain_sensitivity_metadata.json"),
        "--output", os.path.join(folder, "strain_sensitivity_placement_sensitivity.csv"),
    ]
    if solution_working_dir:
        args.extend(["--local-strain-root", solution_working_dir])
    return args


def show_message(text, title):
    try:
        from System.Windows.Forms import MessageBox

        MessageBox.Show(str(text), str(title))
    except Exception:
        print(str(title) + ": " + str(text))


def runtime_core_path():
    return os.path.join(tempfile.gettempdir(), "placement_sensitivity_calculator_core_runtime.py")


def write_runtime_core():
    path = runtime_core_path()
    stream = open(path, "w")
    try:
        stream.write(CORE_CODE)
    finally:
        stream.close()
    return path


def run_external_python(script_path, args):
    from System.Diagnostics import Process, ProcessWindowStyle

    python_exe = (
        os.environ.get("SG_PLACEMENT_PYTHON")
        or os.environ.get("SG_LOAD_RECON_PYTHON")
        or "python"
    )
    process = Process()
    process.StartInfo.FileName = python_exe
    process.StartInfo.Arguments = " ".join([quote_arg(script_path)] + [quote_arg(arg) for arg in args])
    process.StartInfo.UseShellExecute = False
    process.StartInfo.RedirectStandardOutput = True
    process.StartInfo.RedirectStandardError = True
    process.StartInfo.CreateNoWindow = True
    process.StartInfo.WindowStyle = ProcessWindowStyle.Hidden
    process.Start()
    stdout = process.StandardOutput.ReadToEnd()
    stderr = process.StandardError.ReadToEnd()
    process.WaitForExit()
    message = (stdout or "") + ("\n" + stderr if stderr else "")
    return process.ExitCode, message.strip()


def run_embedded_core_in_cpython():
    namespace = {"__name__": "__main__", "__file__": os.path.abspath(sys.argv[0])}
    exec(compile(CORE_CODE, "<placement_sensitivity_calculator_core>", "exec"), namespace, namespace)
    return 0


def main():
    if not is_ironpython():
        return run_embedded_core_in_cpython()

    args = default_mechanical_args()
    if not args:
        show_message("No metadata folder was selected.", TITLE)
        return 1

    runtime_path = write_runtime_core()
    try:
        code, output = run_external_python(runtime_path, args)
    except Exception as exc:
        show_message("Could not start CPython. Set SG_PLACEMENT_PYTHON to your python.exe path.\n\n" + str(exc), TITLE)
        return 1
    finally:
        if os.environ.get("SG_PLACEMENT_KEEP_TEMP", "").lower() not in ["1", "true", "yes"]:
            try:
                os.remove(runtime_path)
            except Exception:
                pass

    if code == 0:
        show_message(output or "Placement sensitivity calculation finished.", TITLE)
    else:
        show_message(output or "CPython calculator failed.", TITLE)
    return int(code)


main()

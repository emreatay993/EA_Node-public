"""Configuration schema, JSON loader, and validation for the ESL tool.

The config is plain JSON (stdlib-parseable on any intranet Python). JSON has
no comments, so free-text rationale belongs in the ``notes`` fields; the
resolved config is echoed verbatim into ``run_manifest.json`` for traceability.

All relative paths in the config are resolved relative to the config file's
own directory, so a dataset folder can be copied between machines as a unit.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


class ConfigError(ValueError):
    """Raised for malformed or inconsistent configuration input."""


@dataclass(frozen=True)
class Channel:
    """One rig load channel (piston/actuator direction at a point).

    ``unit_load`` is the load magnitude the unit static solve was run at;
    the tool divides the supplied field by it to normalize to +1 force unit.
    A positive solved load means force ``P * direction`` applied at ``point``.
    """

    name: str
    case_label: str
    unit_load: float = 1.0
    point: tuple[float, float, float] | None = None
    direction: tuple[float, float, float] | None = None
    cs: str = "global"
    bounds: tuple[float, float] = (0.0, math.inf)
    interface_channel: str | None = None
    apdl_node: int | None = None
    gang: str | None = None
    gang_ratio: float = 1.0
    notes: str = ""


@dataclass(frozen=True)
class Interface:
    """A casing interface cut for Route-A resultants.

    ``ref_point`` must be the same reference the whole-engine team reduces
    interface loads to, so resultants stay traceable to their load set.
    """

    name: str
    node_list_csv: Path
    ref_point: tuple[float, float, float]


@dataclass(frozen=True)
class MsupConfig:
    modal_stress_csv: Path
    modal_coordinates: Path
    modal_forces_csv: Path | None = None
    modes_used: int | None = None
    steady_state_csv: Path | None = None
    include_steady_bias: bool = False


@dataclass(frozen=True)
class TargetConfig:
    mode: str = "reconstruct"          # "reconstruct" | "tensor_csv"
    tensor_csv: Path | None = None
    subtract_steady_csv: Path | None = None


@dataclass(frozen=True)
class UnitFieldsConfig:
    layout: str = "wide"               # "wide" | "per_case" | "rst"
    csv: Path | None = None
    per_case_files: dict[str, Path] | None = None
    rst: Path | None = None


@dataclass(frozen=True)
class MappingConfig:
    coord_tol: float = 0.1
    kdtree_max_dist: float = 1.0
    min_id_match_fraction: float = 0.9


@dataclass(frozen=True)
class MarsEnvelopeConfig:
    max_vm_csv: Path | None = None
    time_of_max_vm_csv: Path | None = None


@dataclass(frozen=True)
class InstantsConfig:
    mode: str = "auto"                 # "auto" | "explicit"
    explicit_times: tuple[float, ...] | None = None
    n_suggestions: int = 4
    quadrature: bool = True
    hotspot_top_percent: float = 2.0
    cluster_dt: float = 0.002
    mars_envelope: MarsEnvelopeConfig = field(default_factory=MarsEnvelopeConfig)


@dataclass(frozen=True)
class RegionConfig:
    mode: str = "top_vm_percent"       # "top_vm_percent" | "node_list_csv" | "bbox" | "all"
    value: float = 5.0
    node_list_csv: Path | None = None
    bbox: tuple[float, float, float, float, float, float] | None = None


@dataclass(frozen=True)
class SolveConfig:
    tier: str = "both"                 # "1" (pattern/Route B) | "2" (free/Route C) | "both"
    weighting: str = "vm"              # "uniform" | "vm"
    vm_weight_exponent: float = 1.0
    region: RegionConfig = field(default_factory=RegionConfig)
    tikhonov_alpha: float = 0.0
    cond_warn_threshold: float = 1e8


@dataclass(frozen=True)
class AcceptanceConfig:
    under_test_tol: float = 0.05
    vm_floor_frac: float = 0.10
    min_peak_ratio: float = 1.0


@dataclass(frozen=True)
class ScalingConfig:
    rt_factor: float = 1.0
    basis_note: str = ""


@dataclass(frozen=True)
class OutputsConfig:
    directory: Path = Path("esl_out")
    apdl_snippet: bool = True
    top_n_hotspots: int = 25


@dataclass(frozen=True)
class EslConfig:
    """Fully resolved, validated configuration."""

    config_path: Path
    title: str
    notes: str
    units: dict[str, str]
    msup: MsupConfig
    target: TargetConfig
    interface_loads_csv: Path | None
    unit_fields: UnitFieldsConfig
    channels: tuple[Channel, ...]
    interfaces: tuple[Interface, ...]
    mapping: MappingConfig
    instants: InstantsConfig
    solve: SolveConfig
    acceptance: AcceptanceConfig
    scaling: ScalingConfig
    outputs: OutputsConfig
    raw: dict[str, Any] = field(repr=False, default_factory=dict)


def _as_path(base: Path, value: Any, key: str) -> Path:
    if not isinstance(value, str) or not value:
        raise ConfigError(f"'{key}' must be a non-empty path string, got {value!r}")
    p = Path(value)
    return p if p.is_absolute() else (base / p).resolve()


def _opt_path(base: Path, value: Any, key: str) -> Path | None:
    return None if value is None else _as_path(base, value, key)


def _vec3(value: Any, key: str) -> tuple[float, float, float]:
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        raise ConfigError(f"'{key}' must be a 3-element [x, y, z] list, got {value!r}")
    return (float(value[0]), float(value[1]), float(value[2]))


def _bounds(value: Any, key: str) -> tuple[float, float]:
    if value is None:
        return (0.0, math.inf)
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise ConfigError(f"'{key}' must be a 2-element [lower, upper] list, got {value!r}")
    lo = -math.inf if value[0] is None else float(value[0])
    hi = math.inf if value[1] is None else float(value[1])
    if not lo < hi:
        raise ConfigError(f"'{key}': lower bound {lo} must be < upper bound {hi}")
    return (lo, hi)


def _parse_channel(base: Path, d: dict[str, Any], idx: int) -> Channel:
    key = f"rig.channels[{idx}]"
    if "name" not in d or "case_label" not in d:
        raise ConfigError(f"{key}: 'name' and 'case_label' are required")
    direction = d.get("direction")
    if direction is not None:
        direction = _vec3(direction, f"{key}.direction")
        norm = math.sqrt(sum(c * c for c in direction))
        if not math.isclose(norm, 1.0, rel_tol=1e-3):
            raise ConfigError(
                f"{key}.direction must be a unit vector (|d|={norm:.4f}); "
                "scale magnitudes via loads, not direction"
            )
    point = d.get("point")
    return Channel(
        name=str(d["name"]),
        case_label=str(d["case_label"]),
        unit_load=float(d.get("unit_load", 1.0)),
        point=None if point is None else _vec3(point, f"{key}.point"),
        direction=direction,
        cs=str(d.get("cs", "global")),
        bounds=_bounds(d.get("bounds"), f"{key}.bounds"),
        interface_channel=d.get("interface_channel"),
        apdl_node=None if d.get("apdl_node") is None else int(d["apdl_node"]),
        gang=d.get("gang"),
        gang_ratio=float(d.get("gang_ratio", 1.0)),
        notes=str(d.get("notes", "")),
    )


def _parse_interface(base: Path, d: dict[str, Any], idx: int) -> Interface:
    key = f"interfaces[{idx}]"
    if "name" not in d or "node_list_csv" not in d or "ref_point" not in d:
        raise ConfigError(f"{key}: 'name', 'node_list_csv' and 'ref_point' are required")
    return Interface(
        name=str(d["name"]),
        node_list_csv=_as_path(base, d["node_list_csv"], f"{key}.node_list_csv"),
        ref_point=_vec3(d["ref_point"], f"{key}.ref_point"),
    )


def load_config(path: str | Path) -> EslConfig:
    """Load, resolve, and validate a JSON config file.

    Raises:
        ConfigError: On malformed JSON, missing required keys, or
            inconsistent settings.
    """
    cfg_path = Path(path).resolve()
    if not cfg_path.is_file():
        raise ConfigError(f"Config file not found: {cfg_path}")
    try:
        raw = json.loads(cfg_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ConfigError(f"Config is not valid JSON ({cfg_path}): {exc}") from exc

    base = cfg_path.parent
    version = raw.get("schema_version")
    if version != 1:
        raise ConfigError(f"Unsupported schema_version {version!r} (expected 1)")

    msup_raw = raw.get("msup")
    if not isinstance(msup_raw, dict):
        raise ConfigError("'msup' block is required")
    msup = MsupConfig(
        modal_stress_csv=_as_path(base, msup_raw.get("modal_stress_csv"), "msup.modal_stress_csv"),
        modal_coordinates=_as_path(base, msup_raw.get("modal_coordinates"), "msup.modal_coordinates"),
        modal_forces_csv=_opt_path(base, msup_raw.get("modal_forces_csv"), "msup.modal_forces_csv"),
        modes_used=None if msup_raw.get("modes_used") is None else int(msup_raw["modes_used"]),
        steady_state_csv=_opt_path(base, msup_raw.get("steady_state_csv"), "msup.steady_state_csv"),
        include_steady_bias=bool(msup_raw.get("include_steady_bias", False)),
    )

    tgt_raw = raw.get("target", {})
    target = TargetConfig(
        mode=str(tgt_raw.get("mode", "reconstruct")),
        tensor_csv=_opt_path(base, tgt_raw.get("tensor_csv"), "target.tensor_csv"),
        subtract_steady_csv=_opt_path(base, tgt_raw.get("subtract_steady_csv"), "target.subtract_steady_csv"),
    )
    if target.mode not in ("reconstruct", "tensor_csv"):
        raise ConfigError(f"target.mode must be 'reconstruct' or 'tensor_csv', got {target.mode!r}")
    if target.mode == "tensor_csv" and target.tensor_csv is None:
        raise ConfigError("target.mode='tensor_csv' requires target.tensor_csv")

    rig_raw = raw.get("rig")
    if not isinstance(rig_raw, dict):
        raise ConfigError("'rig' block is required")
    uf_raw = rig_raw.get("unit_fields", {})
    per_case_raw = uf_raw.get("per_case_files")
    per_case = None
    if per_case_raw is not None:
        per_case = {
            str(k): _as_path(base, v, f"rig.unit_fields.per_case_files[{k}]")
            for k, v in per_case_raw.items()
        }
    unit_fields = UnitFieldsConfig(
        layout=str(uf_raw.get("layout", "wide")),
        csv=_opt_path(base, uf_raw.get("csv"), "rig.unit_fields.csv"),
        per_case_files=per_case,
        rst=_opt_path(base, uf_raw.get("rst"), "rig.unit_fields.rst"),
    )
    if unit_fields.layout not in ("wide", "per_case", "rst"):
        raise ConfigError(f"rig.unit_fields.layout must be wide|per_case|rst, got {unit_fields.layout!r}")
    if unit_fields.layout == "wide" and unit_fields.csv is None:
        raise ConfigError("rig.unit_fields.layout='wide' requires rig.unit_fields.csv")
    if unit_fields.layout == "per_case" and not unit_fields.per_case_files:
        raise ConfigError("rig.unit_fields.layout='per_case' requires rig.unit_fields.per_case_files")
    if unit_fields.layout == "rst" and unit_fields.rst is None:
        raise ConfigError("rig.unit_fields.layout='rst' requires rig.unit_fields.rst")

    channels_raw = rig_raw.get("channels")
    if not isinstance(channels_raw, list) or not channels_raw:
        raise ConfigError("rig.channels must be a non-empty list")
    channels = tuple(_parse_channel(base, c, i) for i, c in enumerate(channels_raw))
    names = [c.name for c in channels]
    if len(set(names)) != len(names):
        raise ConfigError(f"rig.channels names must be unique, got {names}")
    labels = [c.case_label for c in channels]
    if len(set(labels)) != len(labels):
        raise ConfigError(f"rig.channels case_labels must be unique, got {labels}")

    interfaces = tuple(
        _parse_interface(base, d, i) for i, d in enumerate(raw.get("interfaces", []) or [])
    )

    map_raw = raw.get("mapping", {})
    mapping = MappingConfig(
        coord_tol=float(map_raw.get("coord_tol", 0.1)),
        kdtree_max_dist=float(map_raw.get("kdtree_max_dist", 1.0)),
        min_id_match_fraction=float(map_raw.get("min_id_match_fraction", 0.9)),
    )

    inst_raw = raw.get("instants", {})
    env_raw = inst_raw.get("mars_envelope", {}) or {}
    explicit = inst_raw.get("explicit_times")
    instants = InstantsConfig(
        mode=str(inst_raw.get("mode", "auto")),
        explicit_times=None if explicit is None else tuple(float(t) for t in explicit),
        n_suggestions=int(inst_raw.get("n_suggestions", 4)),
        quadrature=bool(inst_raw.get("quadrature", True)),
        hotspot_top_percent=float(inst_raw.get("hotspot_top_percent", 2.0)),
        cluster_dt=float(inst_raw.get("cluster_dt", 0.002)),
        mars_envelope=MarsEnvelopeConfig(
            max_vm_csv=_opt_path(base, env_raw.get("max_vm_csv"), "instants.mars_envelope.max_vm_csv"),
            time_of_max_vm_csv=_opt_path(
                base, env_raw.get("time_of_max_vm_csv"), "instants.mars_envelope.time_of_max_vm_csv"
            ),
        ),
    )
    if instants.mode not in ("auto", "explicit"):
        raise ConfigError(f"instants.mode must be 'auto' or 'explicit', got {instants.mode!r}")
    if instants.mode == "explicit" and not instants.explicit_times:
        raise ConfigError("instants.mode='explicit' requires instants.explicit_times")

    solve_raw = raw.get("solve", {})
    region_raw = solve_raw.get("region", {}) or {}
    region = RegionConfig(
        mode=str(region_raw.get("mode", "top_vm_percent")),
        value=float(region_raw.get("value", 5.0)),
        node_list_csv=_opt_path(base, region_raw.get("node_list_csv"), "solve.region.node_list_csv"),
        bbox=None
        if region_raw.get("bbox") is None
        else tuple(float(v) for v in region_raw["bbox"]),
    )
    if region.mode not in ("top_vm_percent", "node_list_csv", "bbox", "all"):
        raise ConfigError(f"solve.region.mode invalid: {region.mode!r}")
    if region.mode == "node_list_csv" and region.node_list_csv is None:
        raise ConfigError("solve.region.mode='node_list_csv' requires solve.region.node_list_csv")
    if region.mode == "bbox" and (region.bbox is None or len(region.bbox) != 6):
        raise ConfigError("solve.region.mode='bbox' requires a 6-element solve.region.bbox")
    solve = SolveConfig(
        tier=str(solve_raw.get("tier", "both")),
        weighting=str(solve_raw.get("weighting", "vm")),
        vm_weight_exponent=float(solve_raw.get("vm_weight_exponent", 1.0)),
        region=region,
        tikhonov_alpha=float(solve_raw.get("tikhonov_alpha", 0.0)),
        cond_warn_threshold=float(solve_raw.get("cond_warn_threshold", 1e8)),
    )
    if solve.tier not in ("1", "2", "both"):
        raise ConfigError(f"solve.tier must be '1', '2' or 'both', got {solve.tier!r}")
    if solve.weighting not in ("uniform", "vm"):
        raise ConfigError(f"solve.weighting must be 'uniform' or 'vm', got {solve.weighting!r}")

    acc_raw = raw.get("acceptance", {})
    acceptance = AcceptanceConfig(
        under_test_tol=float(acc_raw.get("under_test_tol", 0.05)),
        vm_floor_frac=float(acc_raw.get("vm_floor_frac", 0.10)),
        min_peak_ratio=float(acc_raw.get("min_peak_ratio", 1.0)),
    )

    scal_raw = raw.get("scaling", {})
    scaling = ScalingConfig(
        rt_factor=float(scal_raw.get("rt_factor", 1.0)),
        basis_note=str(scal_raw.get("basis_note", "")),
    )

    out_raw = raw.get("outputs", {})
    out_dir = out_raw.get("directory", "esl_out")
    outputs = OutputsConfig(
        directory=_as_path(base, out_dir, "outputs.directory"),
        apdl_snippet=bool(out_raw.get("apdl_snippet", True)),
        top_n_hotspots=int(out_raw.get("top_n_hotspots", 25)),
    )

    return EslConfig(
        config_path=cfg_path,
        title=str(raw.get("title", "")),
        notes=str(raw.get("notes", "")),
        units=dict(raw.get("units", {})),
        msup=msup,
        target=target,
        interface_loads_csv=_opt_path(base, raw.get("interface_loads_csv"), "interface_loads_csv"),
        unit_fields=unit_fields,
        channels=channels,
        interfaces=interfaces,
        mapping=mapping,
        instants=instants,
        solve=solve,
        acceptance=acceptance,
        scaling=scaling,
        outputs=outputs,
        raw=raw,
    )


def input_files(cfg: EslConfig) -> dict[str, Path]:
    """All input files referenced by the config, for manifest hashing."""
    files: dict[str, Path] = {
        "config": cfg.config_path,
        "modal_stress_csv": cfg.msup.modal_stress_csv,
        "modal_coordinates": cfg.msup.modal_coordinates,
    }
    optional = {
        "modal_forces_csv": cfg.msup.modal_forces_csv,
        "steady_state_csv": cfg.msup.steady_state_csv,
        "target_tensor_csv": cfg.target.tensor_csv,
        "subtract_steady_csv": cfg.target.subtract_steady_csv,
        "interface_loads_csv": cfg.interface_loads_csv,
        "unit_fields_csv": cfg.unit_fields.csv,
        "unit_fields_rst": cfg.unit_fields.rst,
        "region_node_list_csv": cfg.solve.region.node_list_csv,
        "mars_max_vm_csv": cfg.instants.mars_envelope.max_vm_csv,
        "mars_time_of_max_vm_csv": cfg.instants.mars_envelope.time_of_max_vm_csv,
    }
    files.update({k: v for k, v in optional.items() if v is not None})
    if cfg.unit_fields.per_case_files:
        for label, p in cfg.unit_fields.per_case_files.items():
            files[f"unit_field[{label}]"] = p
    for iface in cfg.interfaces:
        files[f"interface_nodes[{iface.name}]"] = iface.node_list_csv
    return files

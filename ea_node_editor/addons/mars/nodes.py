# Purpose: Define guided batch, time-history, and advanced MARS job nodes.
# Map: feature_routes/mars_solver_addon.md
# Tests: tests/test_mars_nodes.py

from __future__ import annotations

import json
import math
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from ea_node_editor.addons.mars.runtime import publish_mars_artifacts, run_mars_batch
from ea_node_editor.nodes.builtins.integrations_common import (
    pick_optional_path,
    pick_path,
    require_existing_file,
)
from ea_node_editor.nodes.execution_context import ExecutionContext, NodeResult
from ea_node_editor.runtime_contracts.data_tree import resolve_single_run_inputs

MARS_BATCH_SOLVE_NODE_TYPE_ID = "mars.batch_solve"
MARS_TIME_HISTORY_NODE_TYPE_ID = "mars.time_history"
MARS_RUN_JOB_NODE_TYPE_ID = "mars.run_job"

_PREPARED_INPUT_KEYS = (
    "modal_coordinates",
    "modal_stress",
    "modal_deformation",
    "modal_force_moment",
    "steady_state_stress",
    "temperature_field",
    "material_profile",
)
_BATCH_OUTPUTS = (
    ("von_mises", "Von Mises", True),
    ("max_principal", "Maximum Principal", False),
    ("min_principal", "Minimum Principal", False),
    ("deformation", "Deformation", False),
    ("velocity", "Velocity", False),
    ("acceleration", "Acceleration", False),
    ("force_moment", "Force / Moment", False),
    ("damage", "Fatigue Damage", False),
)
_TIME_HISTORY_OUTPUTS = tuple(
    key for key, _label, _default in _BATCH_OUTPUTS if key != "damage"
)
_PRIMARY_OUTPUT_PORTS = {
    key: key
    for key in (
        "von_mises",
        "max_principal",
        "min_principal",
        "deformation",
        "velocity",
        "acceleration",
        "damage",
        "force",
        "moment",
    )
}
def _number_property(ctx: ExecutionContext, key: str) -> float:
    value = ctx.properties.get(key)
    if isinstance(value, bool):
        raise ValueError(f"{key} must be a number.")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{key} must be a number.") from exc
    if not math.isfinite(number):
        raise ValueError(f"{key} must be a finite number.")
    return number


def _optional_number_property(ctx: ExecutionContext, key: str) -> float | None:
    value = ctx.properties.get(key)
    if value in (None, ""):
        return None
    return _number_property(ctx, key)


def _resolve_guided_inputs(ctx: ExecutionContext, *, node_name: str) -> dict[str, Any]:
    inputs: dict[str, Any] = {}
    for key in _PREPARED_INPUT_KEYS:
        path = pick_optional_path(ctx, input_key=key, property_key=key)
        if path is None:
            continue
        require_existing_file(path, node_name=f"{node_name} {key}")
        inputs[key] = str(path.resolve())

    rst_path = pick_optional_path(ctx, input_key="modal_rst", property_key="modal_rst")
    if rst_path is not None:
        require_existing_file(rst_path, node_name=f"{node_name} modal_rst")
        scope_name = str(ctx.properties.get("rst_scope_name", "")).strip()
        shell_layer = str(ctx.properties.get("rst_shell_layer", "top")).strip().lower()
        inputs["modal_rst"] = {
            "path": str(rst_path.resolve()),
            "scope_name": scope_name or "All result-support nodes",
            "shell_layer": shell_layer or None,
        }

    return inputs


def _guided_settings(ctx: ExecutionContext, outputs: tuple[str, ...]) -> dict[str, Any]:
    skip_first = ctx.properties.get("skip_first_modes", 0)
    skip_last = ctx.properties.get("skip_last_modes", 0)
    if (
        isinstance(skip_first, bool)
        or not isinstance(skip_first, int)
        or skip_first < 0
    ):
        raise ValueError("Skip First Modes must be a non-negative integer.")
    if isinstance(skip_last, bool) or not isinstance(skip_last, int) or skip_last < 0:
        raise ValueError("Skip Last Modes must be a non-negative integer.")
    settings: dict[str, Any] = {
        "skip_first_modes": skip_first,
        "skip_last_modes": skip_last,
        "include_steady_state": bool(ctx.properties.get("include_steady_state", False)),
    }
    if "damage" in outputs:
        fatigue_A = _optional_number_property(ctx, "fatigue_A")
        fatigue_m = _optional_number_property(ctx, "fatigue_m")
        settings["fatigue"] = {"A": fatigue_A, "m": fatigue_m}
    if bool(ctx.properties.get("plasticity_enabled", False)):
        max_iterations = ctx.properties.get("plasticity_max_iterations", 60)
        if isinstance(max_iterations, bool) or not isinstance(max_iterations, int) or max_iterations <= 0:
            raise ValueError("Plasticity Maximum Iterations must be a positive integer.")
        settings["plasticity"] = {
            "enabled": True,
            "method": str(ctx.properties.get("plasticity_method", "neuber")),
            "max_iterations": max_iterations,
            "tolerance": _number_property(ctx, "plasticity_tolerance"),
            "default_temperature": _optional_number_property(
                ctx, "plasticity_default_temperature"
            ),
            "temperature_column": str(
                ctx.properties.get("plasticity_temperature_column", "")
            ).strip()
            or None,
            "poisson_ratio": _optional_number_property(
                ctx, "plasticity_poisson_ratio"
            ),
            "extrapolation_mode": str(
                ctx.properties.get("plasticity_extrapolation_mode", "linear")
            ),
        }
    return settings


def _write_guided_job(
    path: Path,
    *,
    mode: str,
    inputs: Mapping[str, Any],
    outputs: tuple[str, ...],
    settings: Mapping[str, Any],
    output_directory: Path,
    node_id: int | None = None,
) -> None:
    payload: dict[str, Any] = {
        "schema_version": 1,
        "mode": mode,
        "inputs": dict(inputs),
        "outputs": list(outputs),
        "settings": dict(settings),
        "output_directory": str(output_directory.resolve()),
    }
    if node_id is not None:
        payload["node_id"] = node_id
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _run_and_publish(
    ctx: ExecutionContext,
    *,
    job_path: Path,
    output_directory: Path,
):
    outcome = run_mars_batch(
        ctx,
        job_path=job_path,
        output_directory=output_directory,
        timeout_seconds=_number_property(ctx, "timeout_seconds"),
        termination_grace_seconds=_number_property(ctx, "termination_grace_seconds"),
    )
    published = publish_mars_artifacts(
        ctx,
        output_directory=output_directory,
        outcome=outcome,
        include_results_directory=False,
    )
    return outcome, published


def execute_mars_batch_solve(ctx: ExecutionContext) -> NodeResult:
    ctx.inputs = resolve_single_run_inputs(ctx.inputs, node_name="MARS Batch Solve")
    outputs = tuple(
        key
        for key, _label, _default in _BATCH_OUTPUTS
        if bool(ctx.properties.get(f"output_{key}", False))
    )
    if not outputs:
        raise ValueError("MARS Batch Solve requires at least one selected output.")
    if "force_moment" in outputs and len(outputs) != 1:
        raise ValueError("Force / Moment cannot be combined with other MARS outputs.")
    inputs = _resolve_guided_inputs(ctx, node_name="MARS Batch Solve")
    settings = _guided_settings(ctx, outputs)

    with tempfile.TemporaryDirectory(prefix="corex-mars-batch-") as scratch:
        scratch_path = Path(scratch)
        output_directory = scratch_path / "results"
        job_path = scratch_path / "mars_job.json"
        _write_guided_job(
            job_path,
            mode="batch",
            inputs=inputs,
            outputs=outputs,
            settings=settings,
            output_directory=output_directory,
        )
        outcome, published = _run_and_publish(
            ctx,
            job_path=job_path,
            output_directory=output_directory,
        )

    node_outputs: dict[str, Any] = {
        "manifest": published.manifest,
        "files": published.files,
    }
    for primary_key, ref in published.primary_files.items():
        port = _PRIMARY_OUTPUT_PORTS.get(primary_key)
        if port:
            node_outputs[port] = ref
    return NodeResult(outputs=node_outputs, warnings=outcome.warnings)


def execute_mars_time_history(ctx: ExecutionContext) -> NodeResult:
    ctx.inputs = resolve_single_run_inputs(ctx.inputs, node_name="MARS Time History")
    node_id = ctx.properties.get("node_id")
    if isinstance(node_id, bool) or not isinstance(node_id, int):
        raise ValueError("MARS Time History requires an integer Node ID.")
    output = str(ctx.properties.get("output", "")).strip()
    if output not in _TIME_HISTORY_OUTPUTS:
        raise ValueError(f"Unsupported MARS time-history output: {output!r}.")
    outputs = (output,)
    inputs = _resolve_guided_inputs(ctx, node_name="MARS Time History")
    settings = _guided_settings(ctx, outputs)

    with tempfile.TemporaryDirectory(prefix="corex-mars-history-") as scratch:
        scratch_path = Path(scratch)
        output_directory = scratch_path / "results"
        job_path = scratch_path / "mars_job.json"
        _write_guided_job(
            job_path,
            mode="time_history",
            inputs=inputs,
            outputs=outputs,
            settings=settings,
            output_directory=output_directory,
            node_id=node_id,
        )
        outcome, published = _run_and_publish(
            ctx,
            job_path=job_path,
            output_directory=output_directory,
        )

    history_csv = published.primary_files.get("history_csv")
    if history_csv is None:
        raise RuntimeError("MARSBatch did not identify the time-history CSV.")
    return NodeResult(
        outputs={
            "history_csv": history_csv,
            "manifest": published.manifest,
            "files": published.files,
        },
        warnings=outcome.warnings,
    )


def execute_mars_run_job(ctx: ExecutionContext) -> NodeResult:
    ctx.inputs = resolve_single_run_inputs(ctx.inputs, node_name="MARS Run Job")
    job_path = pick_path(
        ctx,
        input_key="job",
        property_key="job",
        node_name="MARS Run Job",
    )
    require_existing_file(job_path, node_name="MARS Run Job")
    with tempfile.TemporaryDirectory(prefix="corex-mars-job-") as scratch:
        output_directory = Path(scratch) / "results"
        outcome, published = _run_and_publish(
            ctx,
            job_path=job_path.resolve(),
            output_directory=output_directory,
        )
    node_outputs: dict[str, Any] = {
        "manifest": published.manifest,
        "files": published.files,
    }
    for primary_key, ref in published.primary_files.items():
        port = _PRIMARY_OUTPUT_PORTS.get(primary_key)
        if port:
            node_outputs[port] = ref
    return NodeResult(outputs=node_outputs, warnings=outcome.warnings)


__all__ = [
    "MARS_BATCH_SOLVE_NODE_TYPE_ID",
    "MARS_RUN_JOB_NODE_TYPE_ID",
    "MARS_TIME_HISTORY_NODE_TYPE_ID",
    "execute_mars_batch_solve",
    "execute_mars_run_job",
    "execute_mars_time_history",
]

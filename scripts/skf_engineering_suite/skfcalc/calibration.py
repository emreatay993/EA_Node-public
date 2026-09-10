"""Calibration against measured or SKF Bearing Select reference data."""

from __future__ import annotations

import copy
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import numpy as np
import pandas as pd
from scipy.optimize import least_squares

from .batch import _apply_row
from .models import BearingCase, CalibrationProfile
from .solver import solve_case


@dataclass(slots=True)
class CalibrationFitResult:
    profile: CalibrationProfile
    success: bool
    message: str
    cost: float
    evaluations: int
    rms_normalized_residual: float
    predictions: pd.DataFrame = field(default_factory=pd.DataFrame)


_PARAMETERS = {
    "rolling_scale": (0.20, 5.0),
    "sliding_scale": (0.20, 5.0),
    "seal_scale": (0.20, 5.0),
    "drag_scale": (0.20, 5.0),
    "heat_transfer_scale": (0.20, 5.0),
    "installation_scale": (0.20, 5.0),
}


def fit_calibration(
    base_case: BearingCase,
    data: pd.DataFrame,
    fit_parameters: list[str] | None = None,
    progress: Callable[[int], None] | None = None,
) -> CalibrationFitResult:
    if fit_parameters is None:
        fit_parameters = ["rolling_scale", "sliding_scale", "drag_scale", "heat_transfer_scale"]
    invalid = set(fit_parameters) - set(_PARAMETERS)
    if invalid:
        raise ValueError(f"Unknown calibration parameters: {sorted(invalid)}")
    if not fit_parameters:
        raise ValueError("Select at least one calibration parameter.")
    if data.empty:
        raise ValueError("Calibration data is empty.")
    if not ({"measured_torque_nmm", "measured_temperature_c"} & set(data.columns)):
        raise ValueError("Calibration CSV needs measured_torque_nmm and/or measured_temperature_c.")

    rows = data.to_dict(orient="records")
    base_profile = copy.deepcopy(base_case.calibration)
    lower = np.log([_PARAMETERS[name][0] for name in fit_parameters])
    upper = np.log([_PARAMETERS[name][1] for name in fit_parameters])
    x0 = np.log([getattr(base_profile, name) for name in fit_parameters])
    evaluation_counter = 0

    def profile_from(x: np.ndarray) -> CalibrationProfile:
        profile = copy.deepcopy(base_profile)
        for name, value in zip(fit_parameters, np.exp(x)):
            setattr(profile, name, float(value))
        return profile

    def residuals(x: np.ndarray, capture: bool = False) -> tuple[np.ndarray, list[dict]] | np.ndarray:
        nonlocal evaluation_counter
        evaluation_counter += 1
        profile = profile_from(x)
        residual: list[float] = []
        predictions: list[dict] = []
        for row in rows:
            case = _apply_row(base_case, row)
            case.calibration = copy.deepcopy(profile)
            result = solve_case(case)
            prediction = {
                "case_id": row.get("case_id", case.case_name),
                "predicted_torque_nmm": result.friction.total_torque_nmm,
                "predicted_temperature_c": result.thermal.contact_temperature_c,
            }
            measured_torque = row.get("measured_torque_nmm")
            if measured_torque is not None and not pd.isna(measured_torque):
                scale = max(abs(float(measured_torque)), 10.0)
                error = (result.friction.total_torque_nmm - float(measured_torque)) / scale
                residual.append(error)
                prediction["measured_torque_nmm"] = float(measured_torque)
                prediction["torque_error_percent"] = 100.0 * (
                    result.friction.total_torque_nmm - float(measured_torque)
                ) / scale
            measured_temp = row.get("measured_temperature_c")
            if measured_temp is not None and not pd.isna(measured_temp):
                scale = max(abs(float(measured_temp) - case.thermal.inlet_temp_c), 10.0)
                error = (result.thermal.contact_temperature_c - float(measured_temp)) / scale
                residual.append(error)
                prediction["measured_temperature_c"] = float(measured_temp)
                prediction["temperature_error_c"] = result.thermal.contact_temperature_c - float(measured_temp)
            predictions.append(prediction)
        if progress:
            progress(evaluation_counter)
        arr = np.asarray(residual, dtype=float)
        return (arr, predictions) if capture else arr

    solution = least_squares(
        residuals,
        x0,
        bounds=(lower, upper),
        method="trf",
        loss="soft_l1",
        f_scale=1.0,
        max_nfev=200,
    )
    final_profile = profile_from(solution.x)
    final_profile.name = "Fitted calibration"
    final_profile.notes = (
        "Least-squares fit against imported torque/temperature data. "
        "Review residuals and validation cases before design use."
    )
    final_residual, predictions = residuals(solution.x, capture=True)
    rms = float(math.sqrt(float(np.mean(final_residual**2)))) if final_residual.size else 0.0
    return CalibrationFitResult(
        profile=final_profile,
        success=bool(solution.success),
        message=str(solution.message),
        cost=float(solution.cost),
        evaluations=int(solution.nfev),
        rms_normalized_residual=rms,
        predictions=pd.DataFrame(predictions),
    )


def fit_calibration_csv(
    base_case: BearingCase,
    path: str | Path,
    fit_parameters: list[str] | None = None,
    progress: Callable[[int], None] | None = None,
) -> CalibrationFitResult:
    return fit_calibration(base_case, pd.read_csv(path), fit_parameters, progress)

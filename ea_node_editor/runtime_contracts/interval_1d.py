# Purpose: Define COREX's ordered, finite Interval 1D runtime value.
# Map: docs/agent_maps/subsystems/supporting_runtime_assets.md
# Tests: tests/test_interval_1d.py

from __future__ import annotations

import math
from dataclasses import dataclass
from numbers import Real
from typing import Final

INTERVAL_1D_DATA_TYPE: Final[str] = "interval_1d"


def _normalize_endpoint(name: str, value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise TypeError(f"Interval1D {name} must be a finite numeric value")
    endpoint = float(value)
    if not math.isfinite(endpoint):
        raise ValueError(f"Interval1D {name} must be finite")
    return endpoint


@dataclass(frozen=True, slots=True)
class Interval1D:
    start: float
    end: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "start", _normalize_endpoint("start", self.start))
        object.__setattr__(self, "end", _normalize_endpoint("end", self.end))


def coerce_interval_1d(value: object) -> Interval1D:
    if isinstance(value, Interval1D):
        return value
    raise TypeError("Interval 1D values must be Interval1D instances")


__all__ = ["INTERVAL_1D_DATA_TYPE", "Interval1D", "coerce_interval_1d"]

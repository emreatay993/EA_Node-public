"""Shared constants for the ESL tool.

Component order follows the MARS modal-stress CSV convention and is fixed
everywhere in this package: (sx, sy, sz, sxy, syz, sxz).
"""

from __future__ import annotations

import numpy as np

#: Stress tensor component names, in canonical order.
STRESS_COMPONENTS: tuple[str, ...] = ("sx", "sy", "sz", "sxy", "syz", "sxz")

#: Column prefixes used to detect per-mode / per-case stress columns
#: (contains-match, case-insensitive — MARS loader parity).
STRESS_PREFIXES: tuple[str, ...] = tuple(f"{c}_" for c in STRESS_COMPONENTS)

#: Element-nodal force/moment component names (Route A resultants).
FORCE_COMPONENTS: tuple[str, ...] = ("enfox", "enfoy", "enfoz", "enmox", "enmoy", "enmoz")

#: Column prefixes for modal element-nodal force/moment CSVs.
FORCE_PREFIXES: tuple[str, ...] = tuple(f"{c}_" for c in FORCE_COMPONENTS)

#: dtype used for all solver math. Inputs may be written from float32 sources;
#: the solve itself is always float64 (conditioning of correlated unit fields).
SOLVE_DTYPE = np.float64

#: Default condition-number warning threshold for the reduced design matrix.
DEFAULT_COND_WARN = 1e8

#: Relative tolerance used to flag a channel load as sitting at a bound.
AT_BOUND_RTOL = 1e-6

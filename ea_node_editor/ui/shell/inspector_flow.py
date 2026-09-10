from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from ea_node_editor.runtime_contracts import Interval1D, coerce_interval_1d


def coerce_editor_input_value(prop_type: str, value: Any, default: Any) -> Any:
    if prop_type == "bool":
        return bool(value)
    if prop_type == "int":
        try:
            return int(value)
        except (TypeError, ValueError):
            return default
    if prop_type == "float":
        try:
            return float(value)
        except (TypeError, ValueError):
            return default
    if prop_type == "json":
        if isinstance(value, str):
            text = value.strip()
            if not text:
                return default
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                return default
        return value
    if prop_type == "interval_1d":
        if isinstance(value, Mapping):
            try:
                return Interval1D(start=value["start"], end=value["end"])
            except (KeyError, TypeError, ValueError):
                return default
        try:
            return coerce_interval_1d(value)
        except TypeError:
            return default
    return str(value)

"""Parse node-browser quick-insert expressions for the Number Slider node.

Grammar (COREX/Grasshopper style):
    ``min < max``          e.g. ``0<10``     -> value defaults to the midpoint
    ``min < value < max``  e.g. ``0<5<10``

Any token containing a decimal point selects decimal rounding with the decimal
places inferred from the longest fractional part; all-integer tokens select
integer rounding.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

_NUMBER_PATTERN = r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)"
_EXPRESSION_PATTERN = re.compile(
    rf"^\s*(?P<first>{_NUMBER_PATTERN})\s*<\s*(?P<second>{_NUMBER_PATTERN})"
    rf"(?:\s*<\s*(?P<third>{_NUMBER_PATTERN}))?\s*$"
)
_MAX_DECIMALS = 6


@dataclass(frozen=True)
class NumberSliderQuery:
    minimum: float
    value: float
    maximum: float
    rounding: str
    decimals: int

    @property
    def summary(self) -> str:
        return (
            f"{self._format(self.minimum)} < {self._format(self.value)} "
            f"< {self._format(self.maximum)}"
        )

    def _format(self, number: float) -> str:
        if self.rounding == "integer":
            return str(int(round(number)))
        return f"{number:.{max(1, self.decimals)}f}".rstrip("0").rstrip(".") or "0"


def _fraction_digits(token: str) -> int:
    if "." not in token:
        return 0
    return len(token.split(".", 1)[1].rstrip())


def parse_number_slider_query(text: str) -> NumberSliderQuery | None:
    match = _EXPRESSION_PATTERN.match(str(text or ""))
    if match is None:
        return None
    tokens = [match.group("first"), match.group("second")]
    third = match.group("third")
    if third is not None:
        tokens.append(third)
    try:
        numbers = [float(token) for token in tokens]
    except ValueError:
        return None
    if not all(math.isfinite(number) for number in numbers):
        return None

    decimals = min(_MAX_DECIMALS, max(_fraction_digits(token) for token in tokens))
    rounding = "decimal" if any("." in token for token in tokens) else "integer"
    if rounding == "decimal":
        decimals = max(1, decimals)

    if third is None:
        minimum, maximum = numbers
        if minimum >= maximum:
            return None
        value = (minimum + maximum) / 2.0
        if rounding == "integer":
            value = float(math.floor(value + 0.5))
    else:
        minimum, value, maximum = numbers
        if minimum >= maximum or not (minimum <= value <= maximum):
            return None

    return NumberSliderQuery(
        minimum=minimum,
        value=value,
        maximum=maximum,
        rounding=rounding,
        decimals=decimals if rounding == "decimal" else 0,
    )


def number_slider_query_payload(query: NumberSliderQuery | None) -> dict[str, object]:
    """QML-friendly payload; empty dict when the query is not a slider expression."""
    if query is None:
        return {}
    return {
        "valid": True,
        "minimum": query.minimum,
        "value": query.value,
        "maximum": query.maximum,
        "rounding": query.rounding,
        "decimals": query.decimals,
        "summary": query.summary,
    }

from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, TypeVar

T = TypeVar("T")


@dataclass(slots=True)
class ControllerResult(Generic[T]):
    ok: bool
    message: str = ""
    payload: T | None = None

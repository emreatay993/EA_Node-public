"""Shared structural protocols used across subsystems."""

from __future__ import annotations

from typing import Protocol


class SignalLike(Protocol):
    """Anything exposing a Qt-style ``connect`` slot, e.g. a ``pyqtSignal``.

    Used for structural typing of bridge/presenter signal attributes without
    importing concrete Qt signal types.
    """

    def connect(self, slot) -> object: ...  # noqa: ANN001

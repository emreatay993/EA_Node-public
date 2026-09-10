from __future__ import annotations

import time
from collections.abc import Callable
from typing import TypeAlias

from PyQt6.QtCore import QCoreApplication
from PyQt6.QtTest import QTest

TimeoutMessage: TypeAlias = str | Callable[[], str]


def wait_for_condition(
    predicate: Callable[[], bool],
    *,
    timeout_ms: int = 1000,
    poll_interval_ms: int = 20,
    app: QCoreApplication | None = None,
) -> bool:
    if predicate():
        return True

    qt_app = app or QCoreApplication.instance()
    deadline = time.monotonic() + timeout_ms / 1000.0
    poll_interval_ms = max(1, int(poll_interval_ms))

    while True:
        if qt_app is not None:
            qt_app.processEvents()
        if predicate():
            return True

        remaining_ms = int((deadline - time.monotonic()) * 1000)
        if remaining_ms <= 0:
            return False
        QTest.qWait(min(poll_interval_ms, remaining_ms))


def wait_for_condition_or_raise(
    predicate: Callable[[], bool],
    *,
    timeout_ms: int = 1000,
    poll_interval_ms: int = 20,
    app: QCoreApplication | None = None,
    timeout_message: TimeoutMessage = "Timed out waiting for GUI condition.",
) -> None:
    if wait_for_condition(
        predicate,
        timeout_ms=timeout_ms,
        poll_interval_ms=poll_interval_ms,
        app=app,
    ):
        return
    raise AssertionError(timeout_message() if callable(timeout_message) else timeout_message)

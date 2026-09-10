from __future__ import annotations

import os
import sys
import time
from contextlib import contextmanager
from typing import Iterator


"""
Env-gated startup profiler.

Set ``EA_PROFILE_STARTUP=1`` to record and emit phase timings; unset, every
``phase()`` / ``summary()`` call is a no-op. Timings stream to stderr as each
phase closes (so long phases are visible even if the app hangs later), and a
sorted summary can be flushed with ``summary()`` once startup is done.

Set ``EA_PROFILE_AUTOQUIT=1`` in addition to get app.py to quit the process
shortly after the shell is shown — useful for scripted timing runs.
"""

_ENABLED = os.environ.get("EA_PROFILE_STARTUP") == "1"
_AUTOQUIT = os.environ.get("EA_PROFILE_AUTOQUIT") == "1"
_EVENTS: list[tuple[str, float]] = []


def _write_stderr(message: str) -> None:
    """Emit optional diagnostics without making startup depend on stderr."""

    stream = sys.stderr
    if stream is None:
        return
    try:
        stream.write(message)
        stream.flush()
    except (OSError, ValueError):
        # Windowed/frozen launches may have no valid stderr, or a diagnostic
        # launcher may close its redirected pipe before the GUI exits.
        pass


def is_enabled() -> bool:
    return _ENABLED


def is_autoquit() -> bool:
    return _AUTOQUIT


@contextmanager
def phase(name: str) -> Iterator[None]:
    if not _ENABLED:
        yield
        return
    t0 = time.perf_counter()
    try:
        yield
    finally:
        elapsed = time.perf_counter() - t0
        _EVENTS.append((name, elapsed))
        _write_stderr(f"[startup] {name}: {elapsed * 1000:.1f} ms\n")


def summary() -> None:
    if not _ENABLED or not _EVENTS:
        return
    total = sum(e for _, e in _EVENTS)
    lines = ["\n[startup] phase summary (slowest first)\n"]
    for name, elapsed in sorted(_EVENTS, key=lambda x: -x[1]):
        pct = (elapsed / total * 100) if total else 0.0
        lines.append(
            f"  {name:42s} {elapsed * 1000:>9.1f} ms   {pct:>5.1f}%\n"
        )
    lines.append(
        f"  {'TOTAL (sum of instrumented phases)':42s} {total * 1000:>9.1f} ms\n"
    )
    _write_stderr("".join(lines))


__all__ = ["is_enabled", "is_autoquit", "phase", "summary"]

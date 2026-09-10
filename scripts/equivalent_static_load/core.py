"""Shared helpers: logging, hashing, atomic CSV writes, small vector math.

Logging and file-replacement patterns follow
``scripts/mcf_dpf_section_resultants/core.py`` (same repo) so the two tools
behave identically in GUIs and batch runs.
"""

from __future__ import annotations

import hashlib
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

LogFn = Optional[Callable[[str], None]]


class EslError(Exception):
    """Base error for the ESL tool."""


class InputError(EslError):
    """Malformed or inconsistent input data (CLI exit code 2)."""


class SolveError(EslError):
    """The load solve is infeasible or failed (CLI exit code 3)."""


def timestamp() -> str:
    return datetime.now().strftime("%H:%M:%S")


def emit(log: LogFn, message: str) -> None:
    """Timestamped progress logging (house pattern from mcf_dpf_section_resultants)."""
    if log:
        log(f"[{timestamp()}] {message}")


def sha256_of_file(path: Path, chunk_bytes: int = 4 * 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while True:
            chunk = handle.read(chunk_bytes)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def ensure_parent_dir(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def atomic_write_text(path: Path, text: str) -> None:
    """Write via temp file + replace so a locked/partial file never survives."""
    ensure_parent_dir(path)
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)
        os.replace(tmp_name, str(path))
    except BaseException:
        try:
            os.remove(tmp_name)
        except OSError:
            pass
        raise


def normalize3(values: tuple[float, float, float]) -> tuple[float, float, float]:
    x, y, z = (float(v) for v in values)
    norm = (x * x + y * y + z * z) ** 0.5
    if norm == 0.0:
        raise InputError("Zero-length direction vector")
    return (x / norm, y / norm, z / norm)


def cross3(a: tuple[float, float, float], b: tuple[float, float, float]) -> tuple[float, float, float]:
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )

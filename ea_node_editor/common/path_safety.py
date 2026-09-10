# Purpose: Detect symbolic links and Windows reparse points without layer imports.
# Map: subsystems/nodes_registry_builtins.md
# Tests: tests/test_plugin_loader.py

"""Dependency-light filesystem alias detection shared across COREX layers."""

from __future__ import annotations

import os
import stat
from pathlib import Path


def is_reparse_point(path: Path) -> bool:
    try:
        file_status = os.lstat(path)
    except OSError:
        return False
    attributes = getattr(file_status, "st_file_attributes", 0)
    return stat.S_ISLNK(file_status.st_mode) or bool(
        attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    )


__all__ = ["is_reparse_point"]

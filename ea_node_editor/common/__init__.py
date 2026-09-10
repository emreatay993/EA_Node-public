# Purpose: Canonical home for dependency-light helpers shared by 2+ subsystems
#          (protocols, value coercions, JSON/payload tools), so there is one
#          copy to find and edit instead of subsystem-local duplicates.
# Tests: covered indirectly by the suites of the subsystems that import these.
"""Shared, dependency-light helpers used across COREX subsystems.

Keep this package a leaf layer: it must not import from ``graph``, ``ui``,
``ui_qml``, ``execution``, ``persistence``, or ``nodes``. A utility used by two
or more subsystems belongs here rather than as a subsystem-local copy; check
here before adding a new helper (see AGENTS.md duplicate-abstraction rule).
"""

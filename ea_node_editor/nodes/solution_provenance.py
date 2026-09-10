# Purpose: Own trusted shipped-node declarations for external solution provenance.
# Map: subsystems/nodes_registry_builtins.md
# Tests: tests/test_registry_validation.py

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

SolutionProvenanceKind = Literal["file", "directory"]

_BUILTIN_FUNCTION_OWNER_ID = "corex:builtin:functions"
_TABULAR_DATA_OWNER_ID = "ea_node_editor.builtins.tabular_data"


@dataclass(frozen=True, slots=True)
class SolutionProvenanceInputSpec:
    property_key: str
    kind: SolutionProvenanceKind
    policy_revision: int = 1

    def __post_init__(self) -> None:
        if not isinstance(self.property_key, str) or not self.property_key.strip():
            raise ValueError("solution provenance property_key must be non-empty")
        if self.property_key != self.property_key.strip():
            raise ValueError("solution provenance property_key must be trimmed")
        if self.kind not in {"file", "directory"}:
            raise ValueError("solution provenance kind must be file or directory")
        if isinstance(self.policy_revision, bool) or not isinstance(
            self.policy_revision, int
        ):
            raise TypeError("solution provenance policy_revision must be an integer")
        if self.policy_revision <= 0:
            raise ValueError("solution provenance policy_revision must be positive")


_FILE_PATH = (SolutionProvenanceInputSpec("path", "file"),)
_TRUSTED_OVERLAY = {
    (_BUILTIN_FUNCTION_OWNER_ID, "engineering.cad_import"): _FILE_PATH,
    (_BUILTIN_FUNCTION_OWNER_ID, "engineering.fe_import"): _FILE_PATH,
    (_BUILTIN_FUNCTION_OWNER_ID, "io.file_read"): _FILE_PATH,
    (_BUILTIN_FUNCTION_OWNER_ID, "io.image_import"): _FILE_PATH,
    (_BUILTIN_FUNCTION_OWNER_ID, "io.excel_read"): _FILE_PATH,
    (_TABULAR_DATA_OWNER_ID, "tabular.input"): _FILE_PATH,
}


def trusted_solution_provenance_inputs(
    owner_id: str,
    type_id: str,
) -> tuple[SolutionProvenanceInputSpec, ...]:
    return _TRUSTED_OVERLAY.get((str(owner_id).strip(), str(type_id).strip()), ())


__all__ = [
    "SolutionProvenanceInputSpec",
    "SolutionProvenanceKind",
    "trusted_solution_provenance_inputs",
]

# Purpose: Define the shared saved:// and temp:// artifact-reference grammar.
# Map: feature_routes/managed_artifacts_project_data.md
# Tests: tests/test_project_artifact_store.py

from __future__ import annotations

import re
from dataclasses import dataclass

ARTIFACT_REF_SCHEME = "saved"
STAGED_ARTIFACT_REF_SCHEME = "temp"
_ARTIFACT_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def normalize_artifact_id(value: object) -> str:
    text = str(value).strip() if value is not None else ""
    return text if _ARTIFACT_ID_PATTERN.fullmatch(text) else ""


@dataclass(frozen=True, slots=True)
class ManagedArtifactRef:
    artifact_id: str

    def __post_init__(self) -> None:
        normalized = normalize_artifact_id(self.artifact_id)
        if not normalized:
            raise ValueError(f"Invalid managed artifact id: {self.artifact_id!r}")
        object.__setattr__(self, "artifact_id", normalized)

    def as_string(self) -> str:
        return format_managed_artifact_ref(self.artifact_id)


@dataclass(frozen=True, slots=True)
class StagedArtifactRef:
    artifact_id: str

    def __post_init__(self) -> None:
        normalized = normalize_artifact_id(self.artifact_id)
        if not normalized:
            raise ValueError(f"Invalid staged artifact id: {self.artifact_id!r}")
        object.__setattr__(self, "artifact_id", normalized)

    def as_string(self) -> str:
        return format_staged_artifact_ref(self.artifact_id)


ArtifactRef = ManagedArtifactRef | StagedArtifactRef


def format_managed_artifact_ref(artifact_id: str) -> str:
    normalized = normalize_artifact_id(artifact_id)
    if not normalized:
        raise ValueError(f"Invalid managed artifact id: {artifact_id!r}")
    return f"{ARTIFACT_REF_SCHEME}://{normalized}"


def format_staged_artifact_ref(artifact_id: str) -> str:
    normalized = normalize_artifact_id(artifact_id)
    if not normalized:
        raise ValueError(f"Invalid staged artifact id: {artifact_id!r}")
    return f"{STAGED_ARTIFACT_REF_SCHEME}://{normalized}"


def is_managed_artifact_ref(value: object) -> bool:
    parsed = parse_artifact_ref(value)
    return isinstance(parsed, ManagedArtifactRef)


def is_staged_artifact_ref(value: object) -> bool:
    parsed = parse_artifact_ref(value)
    return isinstance(parsed, StagedArtifactRef)


def coerce_managed_artifact_id(value: object) -> str:
    if isinstance(value, ManagedArtifactRef):
        return value.artifact_id
    parsed = parse_artifact_ref(value)
    if isinstance(parsed, ManagedArtifactRef):
        return parsed.artifact_id
    return normalize_artifact_id(value)


def coerce_staged_artifact_id(value: object) -> str:
    if isinstance(value, StagedArtifactRef):
        return value.artifact_id
    parsed = parse_artifact_ref(value)
    if isinstance(parsed, StagedArtifactRef):
        return parsed.artifact_id
    return normalize_artifact_id(value)


def parse_artifact_ref(value: object) -> ArtifactRef | None:
    text = str(value).strip() if value is not None else ""
    if not text:
        return None
    if text.startswith(f"{ARTIFACT_REF_SCHEME}://"):
        artifact_id = normalize_artifact_id(text[len(f"{ARTIFACT_REF_SCHEME}://") :])
        return ManagedArtifactRef(artifact_id) if artifact_id else None
    if text.startswith(f"{STAGED_ARTIFACT_REF_SCHEME}://"):
        artifact_id = normalize_artifact_id(
            text[len(f"{STAGED_ARTIFACT_REF_SCHEME}://") :]
        )
        return StagedArtifactRef(artifact_id) if artifact_id else None
    return None

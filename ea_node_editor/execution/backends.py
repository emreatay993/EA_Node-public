from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal

ExecutionBackendId = Literal[
    "process_isolated",
    "trusted_in_process",
    "external_subprocess",
]

AUTO_BACKEND = "auto"
PROCESS_ISOLATED_BACKEND = "process_isolated"
TRUSTED_IN_PROCESS_BACKEND = "trusted_in_process"
EXTERNAL_SUBPROCESS_BACKEND = "external_subprocess"
_SUPPORTED_BACKENDS = {
    AUTO_BACKEND,
    PROCESS_ISOLATED_BACKEND,
    TRUSTED_IN_PROCESS_BACKEND,
    EXTERNAL_SUBPROCESS_BACKEND,
}
_EXTERNAL_RUNTIME_KINDS = {"external_process", "rust", "cpp", "foreign"}


def _normalize_token(field_name: str, value: object, *, allow_auto: bool = False) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        normalized = AUTO_BACKEND if allow_auto else PROCESS_ISOLATED_BACKEND
    allowed = _SUPPORTED_BACKENDS if allow_auto else _SUPPORTED_BACKENDS - {AUTO_BACKEND}
    if normalized not in allowed:
        allowed_text = ", ".join(sorted(allowed))
        raise ValueError(f"{field_name} must be one of: {allowed_text}.")
    return normalized


def _string_tuple(value: object) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value.strip(),) if value.strip() else ()
    if not isinstance(value, Sequence):
        return ()
    return tuple(str(item).strip() for item in value if str(item).strip())


@dataclass(frozen=True, slots=True)
class RuntimeBackendContract:
    backend_id: str
    kind: str
    runtime_behaviors: tuple[str, ...] = ("active",)

    def __post_init__(self) -> None:
        object.__setattr__(self, "backend_id", str(self.backend_id).strip())
        object.__setattr__(self, "kind", str(self.kind).strip())
        object.__setattr__(
            self,
            "runtime_behaviors",
            _string_tuple(self.runtime_behaviors) or ("active",),
        )
        if not self.backend_id:
            raise ValueError("runtime backend contract requires backend_id.")
        if not self.kind:
            raise ValueError("runtime backend contract requires kind.")

    @property
    def requires_external_subprocess(self) -> bool:
        return self.kind in _EXTERNAL_RUNTIME_KINDS

    @classmethod
    def from_value(cls, value: object) -> "RuntimeBackendContract":
        if isinstance(value, cls):
            return value
        if isinstance(value, Mapping):
            return cls(
                backend_id=str(value.get("backend_id", "")),
                kind=str(value.get("kind", "")),
                runtime_behaviors=_string_tuple(value.get("runtime_behaviors")),
            )
        return cls(
            backend_id=str(getattr(value, "backend_id", "")),
            kind=str(getattr(value, "kind", "")),
            runtime_behaviors=_string_tuple(getattr(value, "runtime_behaviors", ())),
        )

    def to_payload(self) -> dict[str, Any]:
        return {
            "backend_id": self.backend_id,
            "kind": self.kind,
            "runtime_behaviors": list(self.runtime_behaviors),
        }


@dataclass(frozen=True, slots=True)
class ExecutionBackendPolicy:
    requested_backend: str = AUTO_BACKEND
    allow_trusted_in_process: bool = False
    allow_external_subprocess: bool = False
    runtime_backends: tuple[RuntimeBackendContract, ...] = field(default_factory=tuple)
    python_executable: str = ""
    reason: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "requested_backend",
            _normalize_token(
                "execution_backend.requested_backend",
                self.requested_backend,
                allow_auto=True,
            ),
        )
        object.__setattr__(
            self,
            "runtime_backends",
            tuple(RuntimeBackendContract.from_value(item) for item in self.runtime_backends),
        )
        object.__setattr__(self, "reason", str(self.reason).strip())

    @classmethod
    def from_value(cls, value: object) -> "ExecutionBackendPolicy":
        if isinstance(value, cls):
            return value
        if value is None:
            return cls()
        if isinstance(value, str):
            return cls(requested_backend=value)
        if not isinstance(value, Mapping):
            raise TypeError("execution_backend must be a policy mapping, backend id string, or None.")
        runtime_backends = value.get("runtime_backends", ())
        if runtime_backends is None:
            runtime_backends = ()
        return cls(
            requested_backend=str(value.get("requested_backend", AUTO_BACKEND)),
            allow_trusted_in_process=bool(value.get("allow_trusted_in_process", False)),
            allow_external_subprocess=bool(value.get("allow_external_subprocess", False)),
            runtime_backends=tuple(
                RuntimeBackendContract.from_value(item)
                for item in runtime_backends
                if item is not None
            ),
            python_executable=str(value.get("python_executable", "")),
            reason=str(value.get("reason", "")),
        )

    def to_payload(self) -> dict[str, Any]:
        return {
            "requested_backend": self.requested_backend,
            "allow_trusted_in_process": self.allow_trusted_in_process,
            "allow_external_subprocess": self.allow_external_subprocess,
            "runtime_backends": [backend.to_payload() for backend in self.runtime_backends],
            "python_executable": self.python_executable,
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class ExecutionBackendSelection:
    backend_id: ExecutionBackendId = PROCESS_ISOLATED_BACKEND
    isolation: str = "process"
    reason: str = "process_isolation_default"
    trusted_in_process: bool = False
    external_subprocess: bool = False
    python_executable: str = ""
    runtime_backend_ids: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        backend_id = _normalize_token("execution_backend.backend_id", self.backend_id)
        object.__setattr__(self, "backend_id", backend_id)
        object.__setattr__(self, "isolation", str(self.isolation).strip() or "process")
        object.__setattr__(self, "reason", str(self.reason).strip())
        object.__setattr__(self, "python_executable", str(self.python_executable).strip())
        object.__setattr__(
            self,
            "runtime_backend_ids",
            _string_tuple(self.runtime_backend_ids),
        )

    @classmethod
    def from_value(cls, value: object) -> "ExecutionBackendSelection":
        if isinstance(value, cls):
            return value
        if value is None:
            return cls()
        if isinstance(value, str):
            return cls(backend_id=value)  # type: ignore[arg-type]
        if not isinstance(value, Mapping):
            raise TypeError("execution backend selection must be a mapping, backend id string, or None.")
        return cls(
            backend_id=str(value.get("backend_id", PROCESS_ISOLATED_BACKEND)),  # type: ignore[arg-type]
            isolation=str(value.get("isolation", "process")),
            reason=str(value.get("reason", "")),
            trusted_in_process=bool(value.get("trusted_in_process", False)),
            external_subprocess=bool(value.get("external_subprocess", False)),
            python_executable=str(value.get("python_executable", "")),
            runtime_backend_ids=_string_tuple(value.get("runtime_backend_ids")),
        )

    def to_payload(self) -> dict[str, Any]:
        return {
            "backend_id": self.backend_id,
            "isolation": self.isolation,
            "reason": self.reason,
            "trusted_in_process": self.trusted_in_process,
            "external_subprocess": self.external_subprocess,
            "python_executable": self.python_executable,
            "runtime_backend_ids": list(self.runtime_backend_ids),
        }


class ExecutionBackendOrchestrator:
    def select(self, policy: ExecutionBackendPolicy | Mapping[str, Any] | str | None = None) -> ExecutionBackendSelection:
        backend_policy = coerce_execution_backend_policy(policy)
        runtime_backend_ids = tuple(backend.backend_id for backend in backend_policy.runtime_backends)
        requested_backend = backend_policy.requested_backend

        if requested_backend in {"", AUTO_BACKEND, PROCESS_ISOLATED_BACKEND}:
            reason = "process_isolation_default"
            if any(backend.requires_external_subprocess for backend in backend_policy.runtime_backends):
                reason = "process_isolation_for_external_runtime_contracts"
            return ExecutionBackendSelection(
                backend_id=PROCESS_ISOLATED_BACKEND,
                isolation="process",
                reason=reason,
                runtime_backend_ids=runtime_backend_ids,
            )

        if requested_backend == TRUSTED_IN_PROCESS_BACKEND:
            if not backend_policy.allow_trusted_in_process:
                raise ValueError(
                    "Trusted in-process execution requires allow_trusted_in_process=True."
                )
            if any(backend.requires_external_subprocess for backend in backend_policy.runtime_backends):
                raise ValueError(
                    "Trusted in-process execution cannot run external-process runtime backend contracts."
                )
            return ExecutionBackendSelection(
                backend_id=TRUSTED_IN_PROCESS_BACKEND,
                isolation="in_process",
                reason=backend_policy.reason or "trusted_in_process_opt_in",
                trusted_in_process=True,
                runtime_backend_ids=runtime_backend_ids,
            )

        if requested_backend == EXTERNAL_SUBPROCESS_BACKEND:
            has_external_contract = any(
                backend.requires_external_subprocess
                for backend in backend_policy.runtime_backends
            )
            has_python_executable = bool(str(backend_policy.python_executable).strip())
            if (
                not backend_policy.allow_external_subprocess
                and not has_external_contract
                and not has_python_executable
            ):
                raise ValueError(
                    "External subprocess execution requires allow_external_subprocess=True "
                    "or an external runtime backend contract or python_executable."
                )
            return ExecutionBackendSelection(
                backend_id=EXTERNAL_SUBPROCESS_BACKEND,
                isolation="external_subprocess",
                reason=backend_policy.reason or "external_runtime_contract",
                external_subprocess=True,
                python_executable=backend_policy.python_executable,
                runtime_backend_ids=runtime_backend_ids,
            )

        raise ValueError(f"Unsupported execution backend: {requested_backend!r}")


def coerce_execution_backend_policy(value: object) -> ExecutionBackendPolicy:
    return ExecutionBackendPolicy.from_value(value)


def coerce_execution_backend_selection(value: object) -> ExecutionBackendSelection:
    return ExecutionBackendSelection.from_value(value)


__all__ = [
    "AUTO_BACKEND",
    "EXTERNAL_SUBPROCESS_BACKEND",
    "ExecutionBackendId",
    "ExecutionBackendOrchestrator",
    "ExecutionBackendPolicy",
    "ExecutionBackendSelection",
    "PROCESS_ISOLATED_BACKEND",
    "RuntimeBackendContract",
    "TRUSTED_IN_PROCESS_BACKEND",
    "coerce_execution_backend_policy",
    "coerce_execution_backend_selection",
]

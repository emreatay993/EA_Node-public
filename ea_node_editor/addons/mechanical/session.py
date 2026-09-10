# Purpose: Own Mechanical sessions by execution run, Open item, path, and workspace.
# Map: subsystems/addons.md
# Tests: tests/mechanical_catalogue/test_session_lifecycle.py, tests/mechanical_catalogue/test_scripts.py, tests/mechanical_catalogue/test_workbench_save.py

from __future__ import annotations

import shutil
import tempfile
import threading
import time
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ea_node_editor.addons.mechanical.contracts import (
    MODEL_HANDLE_KIND,
    MODEL_TYPE_ID,
    validate_model,
)
from ea_node_editor.addons.mechanical.owner_process import MechanicalOwnerProcess
from ea_node_editor.runtime_contracts import DataPath, RuntimeHandleRef

SESSION_CLEANUP_TIMEOUT_SEC = 6.0


class MechanicalSessionError(RuntimeError):
    pass


class StaleMechanicalModelError(MechanicalSessionError):
    pass


@dataclass(frozen=True, slots=True)
class MechanicalSessionKey:
    run_id: str
    open_node_id: str
    target_path: DataPath
    target_iteration: int


@dataclass(slots=True)
class _Session:
    key: MechanicalSessionKey
    workspace_id: str
    session_id: str
    source_path: Path
    work_root: Path
    work_path: Path
    backend_mode: str
    owner: Any
    revision: int = 0
    connection_generation: int = 0
    terminal: bool = False
    closed: bool = False
    operation_lock: threading.Lock = field(default_factory=threading.Lock)

    def close(self) -> None:
        if self.closed:
            return
        self.terminal = True
        self.owner.close()
        deadline = time.monotonic() + 2.0
        while self.work_root.exists():
            shutil.rmtree(self.work_root, ignore_errors=True)
            if not self.work_root.exists() or time.monotonic() >= deadline:
                break
            time.sleep(0.05)
        if self.work_root.exists():
            raise MechanicalSessionError(
                f"Mechanical working directory cleanup failed: {self.work_root}"
            )
        self.closed = True


@dataclass(frozen=True, slots=True)
class _ModelState:
    session: _Session
    revision: int
    connection_generation: int


class MechanicalSessionService:
    def __init__(
        self,
        worker_services: Any,
        *,
        owner_factory: Callable[[], Any] = MechanicalOwnerProcess,
    ) -> None:
        self._worker_services = worker_services
        self._owner_factory = owner_factory
        self._sessions: dict[MechanicalSessionKey, _Session] = {}
        self._retained: dict[str, list[_Session]] = {}
        self._pending_close: dict[str, _Session] = {}
        self._closed_workspaces: set[str] = set()
        self._lock = threading.RLock()

    def begin_run(self, run_id: str, workspace_id: str) -> int:
        run_id, workspace_id = (
            _identity(run_id, "run_id"),
            _identity(workspace_id, "workspace_id"),
        )
        with self._lock:
            self._closed_workspaces.discard(workspace_id)
            return self._retire_workspace_locked(workspace_id)

    def open_session(
        self,
        *,
        run_id: str,
        workspace_id: str,
        open_node_id: str,
        source_path: Path | str,
        target_path: DataPath = (0,),
        target_iteration: int = 0,
        backend_mode: str = "background",
        working_folder: Path | str | None = None,
        register_cancel: Callable[[Callable[[], None]], None] | None = None,
    ) -> _Session:
        run_id = _identity(run_id, "run_id")
        workspace_id = _identity(workspace_id, "workspace_id")
        open_node_id = _identity(open_node_id, "open_node_id")
        normalized_path = tuple(int(item) for item in target_path)
        if not normalized_path or any(item < 0 for item in normalized_path):
            raise ValueError("target_path must contain non-negative integers")
        if isinstance(target_iteration, bool) or int(target_iteration) < 0:
            raise ValueError("target_iteration must be a non-negative integer")
        if backend_mode not in {"background", "interactive"}:
            raise ValueError("backend_mode must be background or interactive")
        source = Path(source_path).resolve(strict=True)
        key = MechanicalSessionKey(
            run_id, open_node_id, normalized_path, int(target_iteration)
        )
        with self._lock:
            if workspace_id in self._closed_workspaces:
                raise MechanicalSessionError("workspace has been retired")
            existing = self._sessions.get(key)
            if existing is not None:
                if (
                    existing.workspace_id != workspace_id
                    or existing.source_path != source
                    or existing.backend_mode != backend_mode
                ):
                    raise MechanicalSessionError(
                        "session key was reused with different ownership metadata"
                    )
                return existing
            if working_folder:
                work_root = Path(working_folder).resolve()
                if work_root.exists() and any(work_root.iterdir()):
                    raise ValueError("Mechanical working folder must be empty")
                work_root.mkdir(parents=True, exist_ok=True)
            else:
                work_root = Path(tempfile.mkdtemp(prefix="corex-mechanical-"))
            work_suffix = {".mechpz": ".mechdb", ".wbpz": ".wbpj"}.get(
                source.suffix.casefold(), source.suffix
            )
            work_path = work_root / f"{source.stem}{work_suffix}"
            try:
                if self._owner_factory is MechanicalOwnerProcess:
                    owner = self._owner_factory(work_root=work_root)
                else:
                    # Existing deterministic lifecycle fakes do not implement native Open.
                    shutil.copy2(source, work_path)
                    owner = self._owner_factory()
            except BaseException:
                shutil.rmtree(work_root, ignore_errors=True)
                raise
            session = _Session(
                key,
                workspace_id,
                uuid.uuid4().hex,
                source,
                work_root,
                work_path,
                backend_mode,
                owner,
            )
            self._sessions[key] = session
            if register_cancel is not None:
                try:
                    register_cancel(session.close)
                except BaseException:
                    self._sessions.pop(key, None)
                    session.close()
                    raise
            return session

    def register_model(
        self,
        session: _Session,
        *,
        document_id: str,
        source_key: str,
        system_key: str,
        release_code: int,
        catalogue_id: str,
        producer_node_id: str | None = None,
        producer_port: str = "info",
        producer_path: DataPath | None = None,
        producer_iteration: int | None = None,
    ) -> RuntimeHandleRef:
        with self._lock:
            self._require_live_session(session)
            metadata = {
                "workspace_id": session.workspace_id,
                "run_id": session.key.run_id,
                "session_id": session.session_id,
                "document_id": _identity(document_id, "document_id"),
                "source_key": _identity(source_key, "source_key"),
                "system_key": _identity(system_key, "system_key"),
                "model_revision": session.revision,
                "connection_generation": session.connection_generation,
                "release_code": int(release_code),
                "backend_mode": session.backend_mode,
                "catalogue_id": catalogue_id,
                "producer_node_id": _identity(
                    producer_node_id or session.key.open_node_id,
                    "producer_node_id",
                ),
                "producer_port": producer_port,
                "producer_path": list(producer_path or session.key.target_path),
                "producer_iteration": (
                    session.key.target_iteration
                    if producer_iteration is None
                    else int(producer_iteration)
                ),
            }
            return self._worker_services.register_handle(
                _ModelState(session, session.revision, session.connection_generation),
                data_type_id=MODEL_TYPE_ID,
                kind=MODEL_HANDLE_KIND,
                run_id=session.key.run_id,
                metadata=metadata,
            )

    def admit_model(self, value: object, *, run_id: str, workspace_id: str) -> _Session:
        if not validate_model(value):
            raise TypeError("value is not a Mechanical Model handle")
        assert isinstance(value, RuntimeHandleRef)
        state = self._worker_services.resolve_handle(
            value, expected_data_type=MODEL_TYPE_ID, expected_kind=MODEL_HANDLE_KIND
        )
        if not isinstance(state, _ModelState):
            raise StaleMechanicalModelError(
                "Mechanical Model handle has no live session"
            )
        session = state.session
        with self._lock:
            self._require_live_session(session)
            metadata = value.metadata
            if (
                metadata["run_id"] != _identity(run_id, "run_id")
                or metadata["workspace_id"] != _identity(workspace_id, "workspace_id")
                or metadata["session_id"] != session.session_id
                or metadata["model_revision"] != state.revision
                or metadata["model_revision"] != session.revision
                or metadata["connection_generation"] != state.connection_generation
                or metadata["connection_generation"] != session.connection_generation
            ):
                raise StaleMechanicalModelError(
                    "Mechanical Model handle is stale or belongs to another run/session"
                )
            return session

    def operate(
        self,
        session: _Session,
        *,
        expected_revision: int,
        operation: str,
        args: Mapping[str, Any] | None = None,
        mutation: bool = False,
        connection_change: bool = False,
        timeout_sec: float = 600.0,
    ) -> dict[str, Any]:
        with session.operation_lock:
            with self._lock:
                self._require_live_session(session)
                if expected_revision != session.revision:
                    raise StaleMechanicalModelError(
                        "Mechanical Model revision is stale"
                    )
            succeeded = False
            try:
                response = session.owner.request(
                    run_id=session.key.run_id,
                    session_id=session.session_id,
                    workspace_id=session.workspace_id,
                    expected_revision=expected_revision,
                    operation=operation,
                    args=args,
                    timeout_sec=timeout_sec,
                )
                succeeded = True
                return response
            finally:
                if mutation or connection_change and succeeded:
                    with self._lock:
                        if mutation:
                            session.revision += 1
                        if connection_change and succeeded:
                            session.connection_generation += 1

    def cleanup_run(
        self,
        run_id: str,
        *,
        succeeded: bool = False,
        warn: Callable[[str], None] | None = None,
    ) -> int:
        normalized = _identity(run_id, "run_id")
        with self._lock:
            owned = [
                session
                for key, session in self._sessions.items()
                if key.run_id == normalized
            ]
            owned.extend(
                session
                for session in self._pending_close.values()
                if session.key.run_id == normalized and session not in owned
            )
            for session in owned:
                self._sessions.pop(session.key, None)
                if (
                    succeeded
                    and session.backend_mode == "interactive"
                    and session.workspace_id not in self._closed_workspaces
                ):
                    session.terminal = True
                    self._retained.setdefault(session.workspace_id, []).append(session)
            self._close_many(
                [
                    session
                    for session in owned
                    if not (
                        succeeded
                        and session.backend_mode == "interactive"
                        and session.workspace_id not in self._closed_workspaces
                    )
                ],
                warn,
            )
            return len(owned)

    def retire_session(self, session: _Session) -> None:
        with self._lock:
            if self._sessions.get(session.key) is session:
                self._sessions.pop(session.key)
            session.terminal = True
        session.close()

    def retire_workspace(
        self, workspace_id: str, *, warn: Callable[[str], None] | None = None
    ) -> int:
        workspace_id = _identity(workspace_id, "workspace_id")
        with self._lock:
            self._closed_workspaces.add(workspace_id)
            count = self._retire_workspace_locked(workspace_id, warn=warn)
            active = []
            for key, session in tuple(self._sessions.items()):
                if session.workspace_id == workspace_id:
                    self._sessions.pop(key, None)
                    active.append(session)
                    count += 1
            self._close_many(active, warn)
            return count

    def reset(self, *, warn: Callable[[str], None] | None = None) -> int:
        with self._lock:
            sessions = (
                list(self._sessions.values())
                + [item for values in self._retained.values() for item in values]
                + list(self._pending_close.values())
            )
            self._sessions.clear()
            self._retained.clear()
            self._closed_workspaces.clear()
            self._close_many(sessions, warn)
            return len(sessions)

    def _retire_workspace_locked(
        self, workspace_id: str, *, warn: Callable[[str], None] | None = None
    ) -> int:
        sessions = self._retained.pop(workspace_id, [])
        sessions.extend(
            session
            for session in self._pending_close.values()
            if session.workspace_id == workspace_id and session not in sessions
        )
        self._close_many(sessions, warn)
        return len(sessions)

    def _close_many(
        self, sessions: list[_Session], warn: Callable[[str], None] | None
    ) -> None:
        sessions = list({session.session_id: session for session in sessions}.values())
        failures: list[_Session] = []
        failure_lock = threading.Lock()

        def close(session: _Session) -> None:
            try:
                session.close()
            except Exception as exc:  # noqa: BLE001
                with failure_lock:
                    failures.append(session)
                if warn is not None:
                    warn(f"Mechanical session cleanup failed: {exc}")

        threads = [
            threading.Thread(target=close, args=(session,), daemon=True)
            for session in sessions
        ]
        for thread in threads:
            thread.start()
        deadline = time.monotonic() + SESSION_CLEANUP_TIMEOUT_SEC
        for thread in threads:
            thread.join(timeout=max(0.0, deadline - time.monotonic()))
        if warn is not None and any(thread.is_alive() for thread in threads):
            warn("Mechanical session cleanup exceeded the shared six-second bound")
        failures.extend(
            session
            for session, thread in zip(sessions, threads, strict=True)
            if thread.is_alive() and session not in failures
        )
        for session in sessions:
            self._pending_close.pop(session.session_id, None)
        self._pending_close.update(
            (session.session_id, session) for session in failures
        )

    def _require_live_session(self, session: _Session) -> None:
        if session.terminal or self._sessions.get(session.key) is not session:
            raise StaleMechanicalModelError("Mechanical session is no longer live")


def _identity(value: object, name: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise ValueError(f"{name} is required")
    return normalized


__all__ = [
    "MechanicalSessionError",
    "MechanicalSessionKey",
    "MechanicalSessionService",
    "SESSION_CLEANUP_TIMEOUT_SEC",
    "StaleMechanicalModelError",
]

# Purpose: Run MARSBatch losslessly and publish contained results as managed artifacts.
# Map: feature_routes/mars_solver_addon.md
# Tests: tests/test_mars_nodes.py

from __future__ import annotations

import hashlib
import json
import os
import queue
import shutil
import subprocess
import threading
import time
from collections import deque
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ea_node_editor.nodes.execution_context import ExecutionContext
from ea_node_editor.nodes.output_artifacts import (
    artifact_store_for_context,
    default_staging_workspace_root,
    persist_artifact_store,
    register_staged_path_artifact,
)
from ea_node_editor.runtime_contracts import RuntimeArtifactRef


@dataclass(frozen=True, slots=True)
class MarsBatchOutcome:
    terminal_result: dict[str, Any]
    files: tuple[Path, ...]
    primary_files: dict[str, Path]
    warnings: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PublishedMarsArtifacts:
    results_directory: RuntimeArtifactRef | None
    manifest: RuntimeArtifactRef
    files: dict[str, RuntimeArtifactRef]
    primary_files: dict[str, RuntimeArtifactRef]


def managed_mars_batch_executable() -> Path:
    """Return the fixed console entry point in COREX's selected Python environment."""

    from ea_node_editor.execution.managed_runtime import (
        resolve_addon_runtime_paths,
        resolve_managed_console_script,
    )

    return resolve_managed_console_script(
        "MARSBatch",
        paths=resolve_addon_runtime_paths(),
    ).resolve()


def _build_mars_command(
    executable: Path, job_path: Path, output_directory: Path
) -> list[str]:
    return [
        str(executable.resolve()),
        "run",
        str(job_path.resolve()),
        "--format",
        "json",
        "--output-directory",
        str(output_directory.resolve()),
    ]


def _mars_subprocess_environment() -> dict[str, str]:
    environment = dict(os.environ)
    for key in tuple(environment):
        if key.upper().startswith("PYTHON"):
            environment.pop(key)
    return environment


def _terminate_process(process: subprocess.Popen[str], grace_seconds: float) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=grace_seconds)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()


def _validated_record(line: str, *, result_seen: bool) -> tuple[str, dict[str, Any]]:
    text = line.strip()
    if not text:
        raise RuntimeError("MARSBatch emitted a blank line on JSON stdout.")
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"MARSBatch emitted invalid JSONL at column {exc.colno}: {exc.msg}."
        ) from exc
    if not isinstance(payload, Mapping):
        raise RuntimeError("Every MARSBatch JSONL record must be an object.")
    record = payload.get("record")
    if record not in {"event", "result"}:
        raise RuntimeError(
            f"MARSBatch emitted an unsupported JSONL record: {record!r}."
        )
    body = payload.get(record)
    if not isinstance(body, Mapping):
        raise RuntimeError(f"MARSBatch {record!r} record payload must be an object.")
    if result_seen:
        raise RuntimeError(
            "MARSBatch emitted JSONL data after its terminal result record."
        )
    return str(record), dict(body)


def _emit_mars_event(ctx: ExecutionContext, event: Mapping[str, Any]) -> None:
    kind = str(event.get("kind", "event")).strip() or "event"
    message = str(event.get("message", "")).strip()
    if kind == "progress" and event.get("percent") is not None:
        ctx.log_info(f"MARS progress: {event['percent']}%")
        return
    if not message:
        return
    level = str(event.get("level", "info")).strip().lower()
    ctx.emit_log(
        level if level in {"debug", "info", "warning", "error"} else "info", message
    )


def _contained_file(path_value: Any, output_directory: Path, *, label: str) -> Path:
    if not isinstance(path_value, str) or not path_value.strip():
        raise RuntimeError(f"MARSBatch {label} must be a non-empty path string.")
    candidate = Path(path_value).expanduser().resolve()
    root = output_directory.resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise RuntimeError(
            f"MARSBatch reported a file outside its scratch output directory: {candidate}"
        ) from exc
    if not candidate.is_file():
        raise RuntimeError(f"MARSBatch reported a missing output file: {candidate}")
    return candidate


def run_mars_batch(
    ctx: ExecutionContext,
    *,
    job_path: Path,
    output_directory: Path,
    timeout_seconds: float,
    termination_grace_seconds: float,
) -> MarsBatchOutcome:
    """Run one MARS JSON job and validate every stdout JSONL record."""

    executable = managed_mars_batch_executable()
    if not executable.is_file():
        raise FileNotFoundError(
            f"MARSBatch is not installed beside COREX's Python executable: {executable}"
        )
    if not job_path.is_file():
        raise FileNotFoundError(f"MARS job file does not exist: {job_path}")
    if timeout_seconds <= 0:
        raise ValueError("MARS timeout must be greater than zero seconds.")
    if termination_grace_seconds <= 0:
        raise ValueError("MARS termination grace must be greater than zero seconds.")

    output_directory.mkdir(parents=True, exist_ok=True)
    process = subprocess.Popen(
        _build_mars_command(executable, job_path, output_directory),
        env=_mars_subprocess_environment(),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        shell=False,
    )
    cancel_requested = threading.Event()
    cancel_lock = threading.Lock()

    def cancel() -> None:
        cancel_requested.set()
        with cancel_lock:
            _terminate_process(process, termination_grace_seconds)

    ctx.register_cancel(cancel)

    stream_queue: queue.Queue[tuple[str, str | None]] = queue.Queue()

    def read_stream(name: str, stream: Any) -> None:
        try:
            for line in iter(stream.readline, ""):
                stream_queue.put((name, line))
        except OSError:
            pass
        finally:
            stream_queue.put((name, None))

    readers = [
        threading.Thread(
            target=read_stream,
            args=("stdout", process.stdout),
            daemon=True,
            name="mars-batch-stdout",
        ),
        threading.Thread(
            target=read_stream,
            args=("stderr", process.stderr),
            daemon=True,
            name="mars-batch-stderr",
        ),
    ]
    for reader in readers:
        reader.start()

    started = time.monotonic()
    finished_streams: set[str] = set()
    terminal_result: dict[str, Any] | None = None
    stderr_tail: deque[str] = deque(maxlen=40)
    try:
        while len(finished_streams) < 2:
            if cancel_requested.is_set() or ctx.should_stop():
                cancel()
                raise InterruptedError("MARSBatch execution was cancelled.")
            if time.monotonic() - started > timeout_seconds:
                with cancel_lock:
                    _terminate_process(process, termination_grace_seconds)
                raise TimeoutError(
                    f"MARSBatch timed out after {timeout_seconds:.2f} seconds."
                )
            try:
                stream_name, line = stream_queue.get(timeout=0.05)
            except queue.Empty:
                continue
            if line is None:
                finished_streams.add(stream_name)
                continue
            if stream_name == "stderr":
                message = line.rstrip("\r\n")
                if message:
                    stderr_tail.append(message)
                    ctx.log_warning(f"[MARS stderr] {message}")
                continue

            record, body = _validated_record(
                line, result_seen=terminal_result is not None
            )
            if record == "event":
                _emit_mars_event(ctx, body)
            else:
                terminal_result = body

        for reader in readers:
            reader.join(timeout=0.2)
        exit_code = process.wait()
    except BaseException:
        with cancel_lock:
            _terminate_process(process, termination_grace_seconds)
        for reader in readers:
            reader.join(timeout=0.2)
        raise
    finally:
        for stream in (process.stdout, process.stderr):
            try:
                if stream is not None:
                    stream.close()
            except OSError:
                pass

    if terminal_result is None:
        tail = " | ".join(stderr_tail)
        suffix = f" stderr={tail}" if tail else ""
        raise RuntimeError(f"MARSBatch emitted no terminal result record.{suffix}")

    status = str(terminal_result.get("status", "")).strip()
    if exit_code == 130 or status == "interrupted":
        raise InterruptedError(
            str(terminal_result.get("error") or "MARSBatch was interrupted.")
        )
    if exit_code != 0 or status != "completed":
        error = str(
            terminal_result.get("error") or "MARSBatch failed without an error message."
        )
        raise RuntimeError(f"MARSBatch failed with exit code {exit_code}: {error}")

    raw_files = terminal_result.get("files")
    if not isinstance(raw_files, list):
        raise RuntimeError("MARSBatch terminal result field 'files' must be a list.")
    files = tuple(
        _contained_file(value, output_directory, label="result.files entry")
        for value in raw_files
    )
    if len(set(files)) != len(files):
        raise RuntimeError("MARSBatch terminal result contains duplicate file paths.")

    raw_primary = terminal_result.get("primary_files", {})
    if not isinstance(raw_primary, Mapping):
        raise RuntimeError(
            "MARSBatch terminal result field 'primary_files' must be an object."
        )
    primary_files = {
        str(key): _contained_file(value, output_directory, label=f"primary_files.{key}")
        for key, value in raw_primary.items()
        if str(key).strip()
    }
    file_set = set(files)
    if any(path not in file_set for path in primary_files.values()):
        raise RuntimeError(
            "MARSBatch primary_files must refer to entries in result.files."
        )
    manifest = output_directory.resolve() / "mars_result.json"
    if not manifest.is_file():
        raise RuntimeError(
            "MARSBatch did not persist mars_result.json in its output directory."
        )

    raw_warnings = terminal_result.get("warnings", [])
    if not isinstance(raw_warnings, list):
        raise RuntimeError("MARSBatch terminal result field 'warnings' must be a list.")
    warnings = tuple(str(value) for value in raw_warnings if str(value).strip())
    return MarsBatchOutcome(
        terminal_result=terminal_result,
        files=files,
        primary_files=primary_files,
        warnings=warnings,
    )


def _safe_token(value: Any, fallback: str) -> str:
    cleaned = "".join(
        char if char.isalnum() or char in "._-" else "_" for char in str(value).strip()
    )
    return cleaned.strip("._-") or fallback


def _artifact_id(ctx: ExecutionContext, suffix: str) -> str:
    return ".".join(
        (
            "mars",
            _safe_token(ctx.workspace_id, "workspace"),
            _safe_token(ctx.node_id, "node"),
            _safe_token(suffix, "output"),
        )
    )


def _portable_terminal_result(
    outcome: MarsBatchOutcome, output_directory: Path
) -> dict[str, Any]:
    payload = dict(outcome.terminal_result)
    payload["output_directory"] = "."
    payload["files"] = [
        path.relative_to(output_directory.resolve()).as_posix()
        for path in outcome.files
    ]
    payload["primary_files"] = {
        key: path.relative_to(output_directory.resolve()).as_posix()
        for key, path in outcome.primary_files.items()
    }
    return payload


def publish_mars_artifacts(
    ctx: ExecutionContext,
    *,
    output_directory: Path,
    outcome: MarsBatchOutcome,
    include_results_directory: bool,
) -> PublishedMarsArtifacts:
    """Copy scratch results into COREX-managed artifacts before scratch cleanup."""

    output_root = output_directory.resolve()
    store = artifact_store_for_context(ctx)
    store.ensure_staging_root(
        temporary_root_parent=default_staging_workspace_root(),
    )
    attempted_ids: list[str] = []
    attempted_paths: list[str] = []

    def prepare_destination(artifact_id: str, relative_path: str) -> Path:
        attempted_ids.append(artifact_id)
        attempted_paths.append(relative_path)
        store.discard_staged_entries((artifact_id,))
        store.discard_staged_paths((relative_path,))
        return store.staged_target_path(relative_path)

    def paths_for(artifact_id: str, *, subdirectory: str, filename: str):
        return store.node_artifact_paths(
            artifact_id=artifact_id,
            workspace_id=ctx.workspace_id,
            workspace_name=ctx.workspace_name,
            node_id=ctx.node_id,
            node_title=ctx.node_title,
            node_type=ctx.node_type_display_name or ctx.node_type_id or "MARS",
            io_dir="out",
            subdirectory=subdirectory,
            filename=filename,
        )

    def register(
        artifact_id: str,
        artifact_paths: Any,
        payload_path: Path,
        *,
        slot: str,
        format: str,
        extra: Mapping[str, Any],
        metadata: Mapping[str, Any] | None = None,
    ) -> RuntimeArtifactRef:
        entry_metadata = {
            **artifact_paths.metadata,
            **dict(extra),
        }
        runtime_ref = register_staged_path_artifact(
            ctx,
            store=store,
            artifact_id=artifact_id,
            payload_path=payload_path,
            relative_path=artifact_paths.staged_relative_path,
            slot=f"{ctx.workspace_id}:{ctx.node_id}:mars:{slot}",
            format=format,
            entry_metadata=entry_metadata,
            metadata=dict(metadata or {}),
        )
        return runtime_ref

    portable_result = _portable_terminal_result(outcome, output_root)
    results_ref: RuntimeArtifactRef | None = None
    file_refs: dict[str, RuntimeArtifactRef] = {}
    primary_refs: dict[str, RuntimeArtifactRef] = {}
    try:
        if include_results_directory:
            bundle_id = _artifact_id(ctx, "results")
            bundle_paths = paths_for(
                bundle_id,
                subdirectory="mars",
                filename="mars_results",
            )
            bundle_path = prepare_destination(
                bundle_id, bundle_paths.staged_relative_path
            )
            bundle_path.mkdir(parents=True)
            relative_files: list[str] = []
            for source in outcome.files:
                relative = source.relative_to(output_root)
                destination = bundle_path / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, destination)
                relative_files.append(relative.as_posix())
            (bundle_path / "mars_result.json").write_text(
                json.dumps(portable_result, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            relative_files.append("mars_result.json")
            results_ref = register(
                bundle_id,
                bundle_paths,
                bundle_path,
                slot="results_directory",
                format="mars_results",
                extra={"file_count": len(relative_files)},
                metadata={"file_count": len(relative_files)},
            )

        manifest_id = _artifact_id(ctx, "manifest")
        manifest_paths = paths_for(
            manifest_id,
            subdirectory="mars/manifest",
            filename="mars_result.json",
        )
        manifest_path = prepare_destination(
            manifest_id, manifest_paths.staged_relative_path
        )
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(
            json.dumps(portable_result, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        manifest_ref = register(
            manifest_id,
            manifest_paths,
            manifest_path,
            slot="manifest",
            format="json",
            extra={"entry_file": "mars_result.json"},
            metadata={"entry_file": "mars_result.json"},
        )

        refs_by_source: dict[Path, RuntimeArtifactRef] = {}
        for source in outcome.files:
            relative = source.relative_to(output_root)
            relative_text = relative.as_posix()
            digest = hashlib.sha1(relative_text.encode("utf-8")).hexdigest()[:12]
            file_id = _artifact_id(ctx, f"file.{digest}")
            parent_text = relative.parent.as_posix()
            subdirectory = (
                "mars/files" if parent_text == "." else f"mars/files/{parent_text}"
            )
            file_paths = paths_for(
                file_id,
                subdirectory=subdirectory,
                filename=relative.name,
            )
            destination = prepare_destination(file_id, file_paths.staged_relative_path)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
            ref = register(
                file_id,
                file_paths,
                destination,
                slot=f"file:{relative_text}",
                format=source.suffix or "file",
                extra={
                    "entry_file": relative.name,
                },
                metadata={"entry_file": relative.name},
            )
            file_refs[relative_text] = ref
            refs_by_source[source] = ref

        primary_refs = {
            key: refs_by_source[source] for key, source in outcome.primary_files.items()
        }
        persist_artifact_store(ctx, store)
        return PublishedMarsArtifacts(
            results_directory=results_ref,
            manifest=manifest_ref,
            files=file_refs,
            primary_files=primary_refs,
        )
    except BaseException:
        try:
            store.discard_staged_entries(tuple(attempted_ids))
        except BaseException:
            pass
        try:
            store.discard_staged_paths(tuple(attempted_paths))
        except BaseException:
            pass
        try:
            persist_artifact_store(ctx, store)
        except BaseException:
            pass
        raise


__all__ = [
    "MarsBatchOutcome",
    "PublishedMarsArtifacts",
    "managed_mars_batch_executable",
    "publish_mars_artifacts",
    "run_mars_batch",
]

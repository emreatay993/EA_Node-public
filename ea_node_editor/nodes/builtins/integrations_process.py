from __future__ import annotations

import queue
import subprocess
import sys
import threading
import time
from collections import deque
from typing import Any

from ea_node_editor.nodes.builtins.process_subprocess_policy import (
    ExternalSubprocessPolicy,
    PROCESS_OUTPUT_MODE_STORED,
    PROCESS_STREAM_CAPTURE_CHAR_LIMIT,
    PROCESS_TRANSCRIPT_SUBDIRECTORY,
    PROCESS_TRANSCRIPT_SUFFIX,
)
from ea_node_editor.nodes.output_artifacts import (
    ManagedOutputTarget,
    allocate_managed_output,
    artifact_store_for_context,
    persist_artifact_store,
    register_staged_path_artifact,
)
from ea_node_editor.nodes.execution_context import NodeResult
from ea_node_editor.runtime_contracts.data_tree import resolve_single_run_inputs


def _discard_stored_transcripts(
    ctx,  # noqa: ANN001
    targets: tuple[ManagedOutputTarget, ...],
) -> None:
    if not targets:
        return
    store = artifact_store_for_context(ctx)
    cleanup_error: BaseException | None = None
    try:
        store.discard_staged_entries(tuple(target.artifact_id for target in targets))
    except BaseException as error:
        cleanup_error = error
    try:
        store.discard_staged_paths(tuple(target.relative_path for target in targets))
    except BaseException as error:
        if cleanup_error is None:
            cleanup_error = error
    if cleanup_error is not None:
        raise cleanup_error


def execute_process_run(ctx) -> NodeResult:  # noqa: ANN001
    inputs = resolve_single_run_inputs(ctx.inputs, node_name="Process Run")
    policy = ExternalSubprocessPolicy.from_process_run_inputs(
        inputs=inputs,
        properties=ctx.properties,
    )
    output_mode = policy.output_mode
    encoding = policy.encoding
    stored_stdout: ManagedOutputTarget | None = None
    stored_stderr: ManagedOutputTarget | None = None
    stdout_stream = None
    stderr_stream = None
    reader_threads: list[threading.Thread] = []
    keep_stored_outputs = False
    stored_targets: tuple[ManagedOutputTarget, ...] = ()
    stderr_error_tail: deque[str] = deque()
    stderr_error_tail_chars = 0
    stream_queue: queue.Queue[tuple[str, str]] = queue.Queue(
        maxsize=policy.stream_policy.queue_size
    )
    dropped_chunks: dict[str, int] = {
        "stdout": 0,
        "stderr": 0,
    }
    dropped_lock = threading.Lock()
    stdout_chunks: deque[str] = deque()
    stderr_chunks: deque[str] = deque()
    stdout_chars = 0
    stderr_chars = 0
    stdout_truncated = False
    stderr_truncated = False

    process = subprocess.Popen(
        policy.popen_args,
        cwd=policy.popen_cwd,
        env=policy.build_environment(),
        shell=policy.shell,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding=encoding,
        errors="replace",
    )

    def _cancel() -> None:
        if process.poll() is not None:
            return
        process.terminate()
        try:
            process.wait(timeout=policy.termination_grace_sec)
        except subprocess.TimeoutExpired:
            process.kill()
        finally:
            for stream in (process.stdin, process.stdout, process.stderr):
                try:
                    if stream:
                        stream.close()
                except OSError:
                    continue

    def _cleanup_started_resources(
        *,
        suppress_errors: bool = False,
    ) -> None:
        cleanup_error: BaseException | None = None
        try:
            _cancel()
        except BaseException as error:
            cleanup_error = error
        for thread in reader_threads:
            try:
                if thread.is_alive():
                    thread.join(timeout=0.1)
            except BaseException as error:
                if cleanup_error is None:
                    cleanup_error = error
        for stream in (process.stdin, process.stdout, process.stderr):
            try:
                if stream:
                    stream.close()
            except BaseException as error:
                if cleanup_error is None:
                    cleanup_error = error
        for transcript_stream in (stdout_stream, stderr_stream):
            if transcript_stream is None:
                continue
            try:
                transcript_stream.close()
            except BaseException as error:
                if cleanup_error is None:
                    cleanup_error = error
        if not keep_stored_outputs:
            try:
                _discard_stored_transcripts(ctx, stored_targets)
            except BaseException as error:
                if cleanup_error is None:
                    cleanup_error = error
        if cleanup_error is not None and not suppress_errors:
            raise cleanup_error

    try:
        ctx.register_cancel(_cancel)
    except BaseException:
        _cleanup_started_resources(suppress_errors=True)
        raise

    if process.stdin:
        try:
            if policy.stdin_text:
                process.stdin.write(policy.stdin_text)
            process.stdin.close()
        except OSError:
            pass
        except BaseException:
            _cleanup_started_resources(suppress_errors=True)
            raise

    def _append_bounded(
        chunks: deque[str],
        total_chars: int,
        text: str,
        *,
        limit: int = PROCESS_STREAM_CAPTURE_CHAR_LIMIT,
    ) -> tuple[int, bool]:
        if not text:
            return total_chars, False
        chunks.append(text)
        total_chars += len(text)
        truncated = False
        while total_chars > limit and chunks:
            total_chars -= len(chunks.popleft())
            truncated = True
        return total_chars, truncated

    def _create_stored_transcript(output_key: str):
        return allocate_managed_output(
            ctx,
            output_key=output_key,
            default_suffix=PROCESS_TRANSCRIPT_SUFFIX,
            managed_subdirectory=PROCESS_TRANSCRIPT_SUBDIRECTORY,
        )

    if output_mode == PROCESS_OUTPUT_MODE_STORED:
        try:
            stored_stdout = _create_stored_transcript("stdout")
            stored_targets = (stored_stdout,)
            stored_stderr = _create_stored_transcript("stderr")
            stored_targets = (stored_stdout, stored_stderr)
            stdout_stream = stored_stdout.path.open(
                "w",
                encoding=encoding,
            )
            stderr_stream = stored_stderr.path.open(
                "w",
                encoding=encoding,
            )
        except BaseException:
            _cleanup_started_resources(suppress_errors=True)
            raise

    def _stream_reader(stream_name: str, stream: Any) -> None:
        try:
            for chunk in iter(stream.readline, ""):
                if not chunk:
                    break
                try:
                    stream_queue.put_nowait((stream_name, chunk))
                except queue.Full:
                    with dropped_lock:
                        dropped_chunks[stream_name] = (
                            dropped_chunks.get(stream_name, 0) + 1
                        )
        except OSError:
            return

    try:
        if process.stdout is not None:
            stdout_reader = threading.Thread(
                target=_stream_reader,
                args=("stdout", process.stdout),
                daemon=True,
                name="process-run-stdout-reader",
            )
            stdout_reader.start()
            reader_threads.append(stdout_reader)
        if process.stderr is not None:
            stderr_reader = threading.Thread(
                target=_stream_reader,
                args=("stderr", process.stderr),
                daemon=True,
                name="process-run-stderr-reader",
            )
            stderr_reader.start()
            reader_threads.append(stderr_reader)
    except BaseException:
        _cleanup_started_resources(suppress_errors=True)
        raise

    try:
        started_at = time.monotonic()
        while True:
            if ctx.should_stop():
                _cancel()
                raise InterruptedError("run_stop_requested")
            elapsed = time.monotonic() - started_at
            if elapsed > policy.timeout_sec:
                _cancel()
                raise TimeoutError(
                    f"Process Run timed out after {policy.timeout_sec:.2f} seconds."
                )

            drained_any = False
            try:
                while True:
                    stream_name, chunk = stream_queue.get_nowait()
                    drained_any = True
                    message = chunk.rstrip("\r\n")
                    for line in message.splitlines():
                        if line:
                            ctx.emit_log("info", f"[{stream_name}] {line}")
                    if (
                        output_mode == PROCESS_OUTPUT_MODE_STORED
                        and stream_name == "stdout"
                        and stdout_stream is not None
                    ):
                        stdout_stream.write(chunk)
                        stdout_stream.flush()
                    elif (
                        output_mode == PROCESS_OUTPUT_MODE_STORED
                        and stream_name == "stderr"
                        and stderr_stream is not None
                    ):
                        stderr_stream.write(chunk)
                        stderr_stream.flush()
                        stderr_error_tail_chars, _was_truncated = _append_bounded(
                            stderr_error_tail,
                            stderr_error_tail_chars,
                            chunk,
                            limit=policy.stream_policy.stderr_error_tail_char_limit,
                        )
                    elif stream_name == "stdout":
                        stdout_chars, was_truncated = _append_bounded(
                            stdout_chunks,
                            stdout_chars,
                            chunk,
                            limit=policy.stream_policy.capture_char_limit,
                        )
                        stdout_truncated = stdout_truncated or was_truncated
                    elif stream_name == "stderr":
                        stderr_chars, was_truncated = _append_bounded(
                            stderr_chunks,
                            stderr_chars,
                            chunk,
                            limit=policy.stream_policy.capture_char_limit,
                        )
                        stderr_truncated = stderr_truncated or was_truncated
            except queue.Empty:
                pass

            if process.poll() is not None and all(
                not thread.is_alive() for thread in reader_threads
            ):
                if stream_queue.empty():
                    break
                continue
            if not drained_any:
                time.sleep(0.02)

        for thread in reader_threads:
            thread.join(timeout=0.1)

        try:
            while True:
                stream_name, chunk = stream_queue.get_nowait()
                message = chunk.rstrip("\r\n")
                for line in message.splitlines():
                    if line:
                        ctx.emit_log("info", f"[{stream_name}] {line}")
                if (
                    output_mode == PROCESS_OUTPUT_MODE_STORED
                    and stream_name == "stdout"
                    and stdout_stream is not None
                ):
                    stdout_stream.write(chunk)
                    stdout_stream.flush()
                elif (
                    output_mode == PROCESS_OUTPUT_MODE_STORED
                    and stream_name == "stderr"
                    and stderr_stream is not None
                ):
                    stderr_stream.write(chunk)
                    stderr_stream.flush()
                    stderr_error_tail_chars, _was_truncated = _append_bounded(
                        stderr_error_tail,
                        stderr_error_tail_chars,
                        chunk,
                        limit=policy.stream_policy.stderr_error_tail_char_limit,
                    )
                elif stream_name == "stdout":
                    stdout_chars, was_truncated = _append_bounded(
                        stdout_chunks,
                        stdout_chars,
                        chunk,
                        limit=policy.stream_policy.capture_char_limit,
                    )
                    stdout_truncated = stdout_truncated or was_truncated
                elif stream_name == "stderr":
                    stderr_chars, was_truncated = _append_bounded(
                        stderr_chunks,
                        stderr_chars,
                        chunk,
                        limit=policy.stream_policy.capture_char_limit,
                    )
                    stderr_truncated = stderr_truncated or was_truncated
        except queue.Empty:
            pass

        exit_code = int(process.returncode or 0)
        stdout_text = "".join(stdout_chunks)
        stderr_text = "".join(stderr_chunks)

        if stdout_truncated:
            ctx.emit_log(
                "warning",
                (
                    "Process Run stdout capture exceeded limit and was truncated to the most recent "
                    f"{policy.stream_policy.capture_char_limit} characters."
                ),
            )
        if stderr_truncated:
            ctx.emit_log(
                "warning",
                (
                    "Process Run stderr capture exceeded limit and was truncated to the most recent "
                    f"{policy.stream_policy.capture_char_limit} characters."
                ),
            )
        with dropped_lock:
            dropped_stdout = int(dropped_chunks.get("stdout", 0))
            dropped_stderr = int(dropped_chunks.get("stderr", 0))
        if dropped_stdout > 0 or dropped_stderr > 0:
            ctx.emit_log(
                "warning",
                (
                    "Process Run dropped streamed chunks due to output backpressure "
                    f"(stdout={dropped_stdout}, stderr={dropped_stderr})."
                ),
            )

        if policy.fail_on_nonzero and exit_code != 0:
            if output_mode == PROCESS_OUTPUT_MODE_STORED:
                stderr_tail = "".join(stderr_error_tail).strip()
                transcript_hint = f" stderr_tail={stderr_tail!r}" if stderr_tail else ""
                raise RuntimeError(
                    "Process Run returned non-zero exit code "
                    f"{exit_code}. stored_transcripts_discarded=True.{transcript_hint}"
                )
            raise RuntimeError(
                f"Process Run returned non-zero exit code {exit_code}. stderr={stderr_text.strip()}"
            )
        if (
            output_mode == PROCESS_OUTPUT_MODE_STORED
            and stored_stdout is not None
            and stored_stderr is not None
        ):
            for transcript_stream in (stdout_stream, stderr_stream):
                if transcript_stream is not None:
                    transcript_stream.close()
            stdout_stream = None
            stderr_stream = None
            store = artifact_store_for_context(ctx)
            stdout_ref = register_staged_path_artifact(
                ctx,
                store=store,
                artifact_id=stored_stdout.artifact_id,
                payload_path=stored_stdout.path,
                relative_path=stored_stdout.relative_path,
                slot=stored_stdout.slot,
                format=stored_stdout.format,
                entry_metadata=stored_stdout.entry_metadata,
            )
            stderr_ref = register_staged_path_artifact(
                ctx,
                store=store,
                artifact_id=stored_stderr.artifact_id,
                payload_path=stored_stderr.path,
                relative_path=stored_stderr.relative_path,
                slot=stored_stderr.slot,
                format=stored_stderr.format,
                entry_metadata=stored_stderr.entry_metadata,
            )
            persist_artifact_store(ctx, store)
            keep_stored_outputs = True
            return NodeResult(
                outputs={
                    "stdout": stdout_ref,
                    "stderr": stderr_ref,
                    "exit_code": exit_code,
                }
            )
        return NodeResult(
            outputs={
                "stdout": stdout_text,
                "stderr": stderr_text,
                "exit_code": exit_code,
            }
        )
    finally:
        _cleanup_started_resources(
            suppress_errors=sys.exc_info()[0] is not None,
        )

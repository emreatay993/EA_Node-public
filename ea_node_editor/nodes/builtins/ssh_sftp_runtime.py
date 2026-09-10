# Purpose: Execute the built-in SSH command, script, upload, and download nodes.
# Map: feature_routes/ssh_sftp_nodes.md
# Tests: tests/test_ssh_sftp_runtime.py

from __future__ import annotations

import errno
import os
import posixpath
import shlex
import stat
import sys
import time
import uuid
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import paramiko

from ea_node_editor.common.protected_values import (
    unprotect_secret,
)
from ea_node_editor.nodes.execution_context import (
    ExecutionContext,
    NodeResult,
)
from ea_node_editor.nodes.builtins.ssh_sftp_values import (
    HOST_RUNTIME_TYPE,
    RUNTIME_VALUE_REVISION,
    RUNTIME_VALUE_TAG,
    SECRET_RUNTIME_TYPE,
    _coerce_host,
    _coerce_secret,
    _secret_envelope,
)


SSH_TIMEOUT_SECONDS = 30.0
STREAM_CAPTURE_LIMIT = 16 * 1024 * 1024
SCRIPT_SOURCE_LIMIT = 4 * 1024 * 1024
TRANSFER_CHUNK_SIZE = 64 * 1024


def _reveal_credential(value: Mapping[str, Any] | None, *, label: str) -> str | None:
    if value is None:
        return None
    try:
        return unprotect_secret(_secret_envelope(value))
    except Exception as exc:  # noqa: BLE001 - DPAPI errors vary by Windows security context.
        raise RuntimeError(
            f"{label} could not be decrypted in the current Windows user/machine context."
        ) from exc


class _SelectedAgent:
    def __init__(self, agents: Sequence[Any]) -> None:
        self._agents = tuple(agents)

    def get_keys(self) -> tuple[Any, ...]:
        return tuple(key for agent in self._agents for key in agent.get_keys())

    def close(self) -> None:
        for agent in self._agents:
            try:
                agent.close()
            except Exception:
                pass


def _selected_agent(*, use_openssh: bool, use_pageant: bool) -> Any | None:
    if not use_openssh and not use_pageant:
        return None
    if sys.platform != "win32":
        if use_pageant:
            raise RuntimeError("PuTTY Pageant authentication is only available on Windows.")
        return paramiko.Agent()

    from paramiko import win_openssh, win_pageant
    from paramiko.agent import Agent, AgentSSH

    agents = []
    candidates = (
        (use_openssh, win_openssh.can_talk_to_agent, win_openssh.OpenSSHAgentConnection),
        (use_pageant, win_pageant.can_talk_to_agent, win_pageant.PageantConnection),
    )
    for enabled, available, connection_factory in candidates:
        if not enabled:
            continue
        agent = None
        try:
            if not available():
                continue
            agent = Agent.__new__(Agent)
            AgentSSH.__init__(agent)
            # ponytail: Paramiko has no public per-agent selector; replace when its API gains one.
            agent._connect(connection_factory())  # noqa: SLF001
        except Exception:
            if agent is not None:
                try:
                    agent.close()
                except Exception:
                    pass
            _SelectedAgent(agents).close()
            raise
        agents.append(agent)
    if len(agents) == 1:
        return agents[0]
    return _SelectedAgent(agents)


def _connect(host_value: Any, ctx: ExecutionContext) -> paramiko.SSHClient:
    host = _coerce_host(host_value)
    key_path = host["private_key_path"]
    connection_error = (
        "SSH connection failed. "
        "Check the SSH/SFTP Host address, port, credentials, and host key."
    )
    key_is_file = True
    key_probe_failed = False
    if key_path:
        try:
            probe_result = Path(key_path).is_file()
        except Exception:
            key_probe_failed = True
        else:
            if type(probe_result) is bool:
                key_is_file = probe_result
            else:
                key_probe_failed = True

    if key_probe_failed:
        raise RuntimeError(connection_error)
    if not key_is_file:
        raise FileNotFoundError(
            "SSH private key file does not exist. Check the configured private key."
        )

    client = None
    selected_agent = None
    failed = False
    try:
        password = _reveal_credential(host["password"], label="SSH password")
        passphrase = _reveal_credential(
            host["private_key_passphrase"],
            label="Private key passphrase",
        )
        client = paramiko.SSHClient()
        client.load_system_host_keys()
        client.set_missing_host_key_policy(paramiko.RejectPolicy())
        ctx.register_cancel(client.close)
        selected_agent = _selected_agent(
            use_openssh=bool(host["use_openssh_agent"]),
            use_pageant=bool(host["use_pageant"]),
        )
        if selected_agent is not None:
            # Paramiko's single public allow_agent switch cannot distinguish Pageant from OpenSSH.
            client._agent = selected_agent  # noqa: SLF001
        client.connect(
            hostname=host["address"],
            port=host["port"],
            username=host["username"],
            password=password,
            key_filename=key_path or None,
            passphrase=passphrase,
            allow_agent=selected_agent is not None,
            look_for_keys=False,
            timeout=SSH_TIMEOUT_SECONDS,
            banner_timeout=SSH_TIMEOUT_SECONDS,
            auth_timeout=SSH_TIMEOUT_SECONDS,
        )
        transport = client.get_transport()
        if transport is None or not transport.is_active():
            raise RuntimeError("SSH transport did not become active.")
        transport.set_keepalive(int(SSH_TIMEOUT_SECONDS))
    except Exception:
        failed = True
        _close_quietly(client)
        _close_quietly(selected_agent)

    if failed:
        raise RuntimeError(connection_error)
    assert client is not None
    return client


def _append_bounded(target: bytearray, chunk: bytes) -> bool:
    remaining = STREAM_CAPTURE_LIMIT - len(target)
    if remaining > 0:
        target.extend(chunk[:remaining])
    return len(chunk) > remaining


def _execute_command(
    client: paramiko.SSHClient,
    command: str,
    ctx: ExecutionContext,
) -> tuple[int, str, str]:
    stdin, stdout, _stderr = client.exec_command(
        command,
        get_pty=False,
        timeout=SSH_TIMEOUT_SECONDS,
    )
    stdin.close()
    channel = stdout.channel
    channel.settimeout(SSH_TIMEOUT_SECONDS)
    ctx.register_cancel(channel.close)
    stdout_bytes = bytearray()
    stderr_bytes = bytearray()
    stdout_truncated = False
    stderr_truncated = False
    try:
        while True:
            if ctx.should_stop():
                channel.close()
                raise InterruptedError("run_stop_requested")
            drained = False
            if channel.recv_ready():
                drained = True
                stdout_truncated = (
                    _append_bounded(stdout_bytes, channel.recv(TRANSFER_CHUNK_SIZE))
                    or stdout_truncated
                )
            if ctx.should_stop():
                channel.close()
                raise InterruptedError("run_stop_requested")
            if channel.recv_stderr_ready():
                drained = True
                stderr_truncated = (
                    _append_bounded(stderr_bytes, channel.recv_stderr(TRANSFER_CHUNK_SIZE))
                    or stderr_truncated
                )
            if channel.exit_status_ready() and not channel.recv_ready() and not channel.recv_stderr_ready():
                break
            if not drained:
                time.sleep(0.02)
        exit_code = int(channel.recv_exit_status())
    finally:
        channel.close()

    if stdout_truncated:
        ctx.emit_log("warning", "SSH stdout exceeded 16 MiB and was truncated.")
    if stderr_truncated:
        ctx.emit_log("warning", "SSH stderr exceeded 16 MiB and was truncated.")
    return (
        exit_code,
        bytes(stdout_bytes).decode("utf-8", errors="replace"),
        bytes(stderr_bytes).decode("utf-8", errors="replace"),
    )


def _command_result(exit_code: int, output: str, error: str, ctx: ExecutionContext) -> NodeResult:
    successful = exit_code == 0
    if not successful:
        ctx.emit_log("warning", f"SSH command exited with code {exit_code}.")
    return NodeResult(
        outputs={
            "successful": successful,
            "exit_code": exit_code,
            "output": output,
            "error": error,
        }
    )


def run_ssh_command(ctx: ExecutionContext) -> NodeResult:
    command = str(ctx.inputs.get("command", ""))
    if not command.strip():
        raise ValueError("Run SSH Command requires a Command.")
    client = _connect(ctx.inputs.get("target_host"), ctx)
    try:
        return _command_result(*_execute_command(client, command, ctx), ctx)
    finally:
        client.close()


def _script_source(ctx: ExecutionContext) -> bytes:
    value = ctx.inputs.get("script", "")
    if not isinstance(value, (str, os.PathLike)):
        raise TypeError("Run SSH Script requires script text or a local file path.")
    text = os.fspath(value)
    resolved = ctx.resolve_input_path("script")
    path = resolved if resolved is not None and resolved.is_file() else None
    if path is None and "\n" not in text and "\r" not in text:
        try:
            candidate = Path(text)
            if candidate.is_file():
                path = candidate
        except OSError:
            path = None
    if path is not None:
        size = path.stat().st_size
        if size > SCRIPT_SOURCE_LIMIT:
            raise ValueError("Run SSH Script local source exceeds 4 MiB.")
        source = path.read_bytes()
    else:
        source = text.encode("utf-8")
    if len(source) > SCRIPT_SOURCE_LIMIT:
        raise ValueError("Run SSH Script source exceeds 4 MiB.")
    if not source:
        raise ValueError("Run SSH Script requires a non-empty Script.")
    return source.replace(b"\r\n", b"\n").replace(b"\r", b"\n")


def _open_sftp(client: paramiko.SSHClient, ctx: ExecutionContext) -> paramiko.SFTPClient:
    sftp = client.open_sftp()
    sftp.get_channel().settimeout(SSH_TIMEOUT_SECONDS)
    ctx.register_cancel(sftp.close)
    return sftp


def _close_quietly(resource: Any | None) -> None:
    if resource is None:
        return
    try:
        resource.close()
    except Exception:
        pass


def _remove_remote_quietly(sftp: paramiko.SFTPClient, path: str) -> None:
    try:
        sftp.remove(path)
    except Exception:
        pass


def _write_remote_script(
    sftp: paramiko.SFTPClient,
    remote_path: str,
    source: bytes,
    ctx: ExecutionContext,
) -> None:
    remote_file = sftp.file(remote_path, "wb")
    try:
        sftp.chmod(remote_path, 0o700)
        for offset in range(0, len(source), TRANSFER_CHUNK_SIZE):
            if ctx.should_stop():
                raise InterruptedError("run_stop_requested")
            remote_file.write(source[offset : offset + TRANSFER_CHUNK_SIZE])
        remote_file.flush()
    finally:
        _close_quietly(remote_file)


def run_ssh_script(ctx: ExecutionContext) -> NodeResult:
    source = _script_source(ctx)
    interpreter = str(ctx.properties.get("interpreter", "Bash")).strip()
    executables = {
        "Bash": "bash",
        "sh": "sh",
        "Python 3": "python3",
        "Python 2": "python2",
        "Perl": "perl",
    }
    if interpreter == "Custom":
        if not source.startswith(b"#!"):
            raise ValueError("Custom SSH scripts require a shebang on the first line.")
        executable = ""
    elif interpreter in executables:
        executable = executables[interpreter]
    else:
        raise ValueError(f"Unsupported SSH script interpreter: {interpreter}")

    client = _connect(ctx.inputs.get("target_host"), ctx)
    sftp = None
    stage_dir = f"/tmp/.corex-run-ssh-script-{uuid.uuid4().hex}"
    remote_path = posixpath.join(stage_dir, "script")
    stage_created = False
    try:
        sftp = _open_sftp(client, ctx)
        sftp.mkdir(stage_dir, mode=0o700)
        stage_created = True
        sftp.chmod(stage_dir, 0o700)
        _write_remote_script(sftp, remote_path, source, ctx)
        quoted_path = shlex.quote(remote_path)
        command = quoted_path if interpreter == "Custom" else f"{executable} {quoted_path}"
        result = _execute_command(client, command, ctx)
        if result[0] == 127:
            ctx.emit_log("warning", f"SSH script interpreter is unavailable: {interpreter}.")
        return _command_result(*result, ctx)
    finally:
        if sftp is not None and stage_created:
            _remove_remote_quietly(sftp, remote_path)
            try:
                sftp.rmdir(stage_dir)
            except Exception:
                ctx.emit_log("warning", "Could not remove the staged remote SSH script.")
        _close_quietly(sftp)
        _close_quietly(client)


def _check_cancelled(ctx: ExecutionContext) -> None:
    if ctx.should_stop():
        raise InterruptedError("run_stop_requested")


def _sources(value: Any) -> list[str]:
    if isinstance(value, (str, os.PathLike)):
        values = [os.fspath(value)]
    elif isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        values = [os.fspath(item) for item in value]
    else:
        raise TypeError("Sources must be a path or a list of paths.")
    sources = [item for item in values if item]
    if not sources:
        raise ValueError("At least one Source is required.")
    return sources


def _remote_path(value: Any, *, label: str) -> str:
    path = str(value or "").strip()
    if not path:
        raise ValueError(f"{label} is required.")
    if "\x00" in path:
        raise ValueError(f"{label} contains an invalid null character.")
    return posixpath.normpath(path)


def _remote_join(base: str, relative: str) -> str:
    relative = relative.replace("\\", "/")
    normalized_relative = posixpath.normpath(relative)
    if (
        posixpath.isabs(normalized_relative)
        or normalized_relative == ".."
        or normalized_relative.startswith("../")
    ):
        raise ValueError("Transfer path escapes its destination.")
    base = posixpath.normpath(base)
    candidate = posixpath.normpath(posixpath.join(base, normalized_relative))
    if (
        base not in (".", "/")
        and candidate != base
        and not candidate.startswith(base.rstrip("/") + "/")
    ):
        raise ValueError("Transfer path escapes its destination.")
    return candidate


def _remote_lstat(sftp: paramiko.SFTPClient, path: str) -> Any | None:
    try:
        return sftp.lstat(path)
    except OSError as exc:
        if isinstance(exc, FileNotFoundError) or exc.errno == errno.ENOENT:
            return None
        raise


def _ensure_remote_dir(sftp: paramiko.SFTPClient, path: str) -> None:
    path = posixpath.normpath(path)
    if path in ("", ".", "/"):
        return
    attrs = _remote_lstat(sftp, path)
    if attrs is not None:
        if not stat.S_ISDIR(attrs.st_mode):
            raise NotADirectoryError(f"Remote path is not a directory: {path}")
        return
    parent = posixpath.dirname(path)
    if parent != path:
        _ensure_remote_dir(sftp, parent)
    sftp.mkdir(path)


def _warn_symlink(ctx: ExecutionContext, path: str) -> None:
    ctx.emit_log("warning", f"Skipping symbolic link: {path}")


def _plan_upload(
    sources: list[str],
    destination: str,
    *,
    destination_is_directory: bool,
    ctx: ExecutionContext,
) -> tuple[list[str], list[tuple[Path, str]]]:
    directories = [
        destination
        if destination_is_directory
        else posixpath.dirname(destination)
    ]
    files: list[tuple[Path, str]] = []

    def visit(path: Path, relative: str) -> None:
        _check_cancelled(ctx)
        if path.is_symlink():
            _warn_symlink(ctx, str(path))
            return
        if path.is_dir():
            target_dir = _remote_join(destination, relative) if relative else destination
            directories.append(target_dir)
            for child in sorted(path.iterdir(), key=lambda item: item.name):
                visit(child, posixpath.join(relative, child.name) if relative else child.name)
            return
        if not path.is_file():
            ctx.emit_log("warning", f"Skipping non-regular local path: {path}")
            return
        files.append((path, _remote_join(destination, relative)))

    for source_text in sources:
        source = Path(source_text)
        if not source.exists() and not source.is_symlink():
            raise FileNotFoundError(f"SFTP Upload source does not exist: {source}")
        if source.is_dir() and not source.is_symlink():
            for child in sorted(source.iterdir(), key=lambda item: item.name):
                visit(child, child.name)
        else:
            visit(source, source.name if destination_is_directory else "")
    return list(dict.fromkeys(directories)), files


def _atomic_remote_upload(
    sftp: paramiko.SFTPClient,
    source: Path,
    destination: str,
    overwrite: bool,
    ctx: ExecutionContext,
) -> int:
    source_size = source.stat().st_size
    temporary = posixpath.join(
        posixpath.dirname(destination),
        f".{posixpath.basename(destination)}.corex-tmp-{uuid.uuid4().hex}",
    )

    def progress(_transferred: int, _total: int) -> None:
        _check_cancelled(ctx)

    try:
        uploaded = sftp.put(str(source), temporary, callback=progress, confirm=True)
        _check_cancelled(ctx)
        if overwrite:
            try:
                sftp.posix_rename(temporary, destination)
            except (AttributeError, OSError) as exc:
                raise RuntimeError(
                    "The SSH server does not support atomic replacement of existing files."
                ) from exc
        else:
            sftp.rename(temporary, destination)
        return int(getattr(uploaded, "st_size", source_size))
    finally:
        try:
            if _remote_lstat(sftp, temporary) is not None:
                sftp.remove(temporary)
        except Exception:
            pass


def sftp_upload(ctx: ExecutionContext) -> NodeResult:
    sources = _sources(ctx.inputs.get("sources"))
    destination_text = str(ctx.inputs.get("destination", "") or "").strip()
    destination = _remote_path(destination_text, label="Destination")
    overwrite = bool(ctx.inputs.get("overwrite", False))

    client = _connect(ctx.inputs.get("target_host"), ctx)
    sftp = None
    try:
        sftp = _open_sftp(client, ctx)
        destination_attrs = _remote_lstat(sftp, destination)
        requires_directory = len(sources) > 1 or any(
            Path(source).is_dir() and not Path(source).is_symlink()
            for source in sources
        )
        destination_is_directory = (
            requires_directory
            or destination_text.endswith("/")
            or destination in (".", "/")
            or (
                destination_attrs is not None
                and stat.S_ISDIR(destination_attrs.st_mode)
            )
        )
        if (
            requires_directory
            and destination_attrs is not None
            and not stat.S_ISDIR(destination_attrs.st_mode)
        ):
            raise NotADirectoryError(
                "Multiple sources and directory uploads require a destination directory."
            )
        directories, files = _plan_upload(
            sources,
            destination,
            destination_is_directory=destination_is_directory,
            ctx=ctx,
        )
        if not overwrite:
            targets = [remote for _local, remote in files]
            if len(targets) != len(set(targets)):
                raise FileExistsError(
                    "SFTP Upload sources map to the same destination path."
                )
        for directory in sorted(directories, key=lambda item: (item.count("/"), item)):
            _ensure_remote_dir(sftp, directory)
        if not overwrite:
            conflicts = [remote for _local, remote in files if _remote_lstat(sftp, remote) is not None]
            if conflicts:
                raise FileExistsError(f"SFTP Upload destination already exists: {conflicts[0]}")
        uploaded_bytes = 0
        uploaded_files = 0
        for local_path, remote_path in files:
            _check_cancelled(ctx)
            _ensure_remote_dir(sftp, posixpath.dirname(remote_path))
            uploaded_bytes += _atomic_remote_upload(
                sftp,
                local_path,
                remote_path,
                overwrite,
                ctx,
            )
            uploaded_files += 1
        return NodeResult(
            outputs={
                "successful": True,
                "uploaded_bytes": uploaded_bytes,
                "uploaded_files": uploaded_files,
            }
        )
    finally:
        _close_quietly(sftp)
        _close_quietly(client)


def _safe_local_target(base: Path, relative: str) -> Path:
    if "\x00" in relative:
        raise ValueError("Download path contains an invalid null character.")
    normalized = Path(relative.replace("\\", "/"))
    if normalized.is_absolute() or ".." in normalized.parts:
        raise ValueError("Download path escapes its destination.")
    base = base.resolve()
    target = (base / normalized).resolve()
    if target != base and base not in target.parents:
        raise ValueError("Download path escapes its destination.")
    return target


def _plan_download(
    sftp: paramiko.SFTPClient,
    sources: list[str],
    destination: Path,
    *,
    destination_is_directory: bool,
    ctx: ExecutionContext,
) -> tuple[list[Path], list[tuple[str, Path, int]]]:
    directories = [destination if destination_is_directory else destination.parent]
    files: list[tuple[str, Path, int]] = []

    def visit(remote: str, relative: str) -> None:
        _check_cancelled(ctx)
        attrs = sftp.lstat(remote)
        if stat.S_ISLNK(attrs.st_mode):
            _warn_symlink(ctx, remote)
            return
        if stat.S_ISDIR(attrs.st_mode):
            target_dir = _safe_local_target(destination, relative) if relative else destination
            directories.append(target_dir)
            for child in sorted(sftp.listdir_attr(remote), key=lambda item: item.filename):
                name = str(child.filename)
                if name in ("", ".", "..") or "/" in name or "\x00" in name:
                    raise ValueError("Remote directory contains an unsafe entry name.")
                visit(
                    posixpath.join(remote, name),
                    posixpath.join(relative, name) if relative else name,
                )
            return
        if not stat.S_ISREG(attrs.st_mode):
            ctx.emit_log("warning", f"Skipping non-regular remote path: {remote}")
            return
        local_target = (
            _safe_local_target(destination, relative)
            if destination_is_directory
            else destination.resolve()
        )
        files.append((remote, local_target, int(attrs.st_size)))

    for source_text in sources:
        remote = _remote_path(source_text, label="Source")
        attrs = sftp.lstat(remote)
        if stat.S_ISDIR(attrs.st_mode) and not stat.S_ISLNK(attrs.st_mode):
            for child in sorted(sftp.listdir_attr(remote), key=lambda item: item.filename):
                name = str(child.filename)
                if name in ("", ".", "..") or "/" in name or "\x00" in name:
                    raise ValueError("Remote directory contains an unsafe entry name.")
                visit(posixpath.join(remote, name), name)
        else:
            visit(
                remote,
                posixpath.basename(remote) if destination_is_directory else "",
            )
    return list(dict.fromkeys(directories)), files


def _atomic_local_download(
    sftp: paramiko.SFTPClient,
    source: str,
    destination: Path,
    overwrite: bool,
    ctx: ExecutionContext,
) -> int:
    temporary = destination.with_name(f".{destination.name}.corex-tmp-{uuid.uuid4().hex}")

    def progress(_transferred: int, _total: int) -> None:
        _check_cancelled(ctx)

    try:
        sftp.get(source, str(temporary), callback=progress)
        _check_cancelled(ctx)
        downloaded_size = temporary.stat().st_size
        if overwrite:
            os.replace(temporary, destination)
        else:
            os.link(temporary, destination)
            temporary.unlink()
        return downloaded_size
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass


def sftp_download(ctx: ExecutionContext) -> NodeResult:
    sources = _sources(ctx.inputs.get("sources"))
    destination_text = str(ctx.inputs.get("destination", "") or "").strip()
    if not destination_text:
        raise ValueError("Destination is required.")
    destination = Path(destination_text)
    overwrite = bool(ctx.inputs.get("overwrite", False))

    client = _connect(ctx.inputs.get("target_host"), ctx)
    sftp = None
    try:
        sftp = _open_sftp(client, ctx)
        remote_sources = [
            _remote_path(source, label="Source")
            for source in sources
        ]
        requires_directory = len(remote_sources) > 1 or any(
            stat.S_ISDIR(sftp.lstat(source).st_mode)
            and not stat.S_ISLNK(sftp.lstat(source).st_mode)
            for source in remote_sources
        )
        destination_is_directory = (
            requires_directory
            or destination_text.endswith(("/", "\\"))
            or destination.is_dir()
        )
        if requires_directory and destination.exists() and not destination.is_dir():
            raise NotADirectoryError(
                "Multiple sources and directory downloads require a destination directory."
            )
        destination = destination.resolve()
        directories, files = _plan_download(
            sftp,
            remote_sources,
            destination,
            destination_is_directory=destination_is_directory,
            ctx=ctx,
        )
        if not overwrite:
            targets = [local for _remote, local, _size in files]
            if len(targets) != len(set(targets)):
                raise FileExistsError("SFTP Download sources map to the same destination path.")
            conflicts = [local for _remote, local, _size in files if local.exists()]
            if conflicts:
                raise FileExistsError(f"SFTP Download destination already exists: {conflicts[0]}")
        for directory in sorted(directories, key=lambda item: (len(item.parts), str(item))):
            directory.mkdir(parents=True, exist_ok=True)
        downloaded_bytes = 0
        downloaded_files = 0
        for remote_path, local_path, _remote_size in files:
            _check_cancelled(ctx)
            local_path.parent.mkdir(parents=True, exist_ok=True)
            downloaded_bytes += _atomic_local_download(
                sftp,
                remote_path,
                local_path,
                overwrite,
                ctx,
            )
            downloaded_files += 1
        return NodeResult(
            outputs={
                "successful": True,
                "downloaded_bytes": downloaded_bytes,
                "downloaded_files": downloaded_files,
            }
        )
    finally:
        _close_quietly(sftp)
        _close_quietly(client)


__all__ = [
    "run_ssh_command",
    "run_ssh_script",
    "sftp_download",
    "sftp_upload",
]

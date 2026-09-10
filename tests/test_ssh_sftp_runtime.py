from __future__ import annotations

import json
import os
import posixpath
import queue
import stat
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from ea_node_editor.common.protected_values import protect_secret
from ea_node_editor.execution.worker_runner import NodeExecutor, RunEventPublisher
from ea_node_editor.nodes.builtins import ssh_sftp_runtime as runtime
from ea_node_editor.nodes.builtins import ssh_sftp_values as values
from ea_node_editor.nodes.execution_context import (
    ExecutionContext,
    NodeInputNotReadyError,
)
from ea_node_editor.runtime_contracts import (
    deserialize_runtime_value,
    serialize_runtime_value,
)


def _ctx(
    *,
    inputs: dict[str, Any] | None = None,
    properties: dict[str, Any] | None = None,
    logs: list[tuple[str, str]] | None = None,
    should_stop=lambda: False,
) -> ExecutionContext:
    captured_logs = logs if logs is not None else []
    return ExecutionContext(
        run_id="run",
        node_id="node",
        workspace_id="workspace",
        inputs=inputs or {},
        properties=properties or {},
        emit_log=lambda level, message: captured_logs.append((level, message)),
        should_stop=should_stop,
    )


def _host(**updates: Any) -> dict[str, Any]:
    value = {
        runtime.RUNTIME_VALUE_TAG: runtime.HOST_RUNTIME_TYPE,
        "revision": 1,
        "address": "example.test",
        "port": 22,
        "username": "worker",
        "password": None,
        "private_key_path": "",
        "private_key_passphrase": None,
        "use_openssh_agent": False,
        "use_pageant": False,
    }
    value.update(updates)
    return value


class _Transport:
    def __init__(self) -> None:
        self.keepalive = 0

    def is_active(self) -> bool:
        return True

    def set_keepalive(self, seconds: int) -> None:
        self.keepalive = seconds


class _Channel:
    def __init__(
        self,
        *,
        stdout: list[bytes] | None = None,
        stderr: list[bytes] | None = None,
        exit_code: int = 0,
    ) -> None:
        self.stdout = list(stdout or [])
        self.stderr = list(stderr or [])
        self.exit_code = exit_code
        self.closed = False
        self.timeout = 0.0

    def settimeout(self, timeout: float) -> None:
        self.timeout = timeout

    def recv_ready(self) -> bool:
        return bool(self.stdout)

    def recv(self, _size: int) -> bytes:
        return self.stdout.pop(0)

    def recv_stderr_ready(self) -> bool:
        return bool(self.stderr)

    def recv_stderr(self, _size: int) -> bytes:
        return self.stderr.pop(0)

    def exit_status_ready(self) -> bool:
        return True

    def recv_exit_status(self) -> int:
        return self.exit_code

    def close(self) -> None:
        self.closed = True


class _Stream:
    def __init__(self, channel: _Channel) -> None:
        self.channel = channel
        self.closed = False

    def close(self) -> None:
        self.closed = True


class _CommandClient:
    def __init__(self, channel: _Channel) -> None:
        self.channel = channel
        self.commands: list[tuple[str, bool, float]] = []
        self.closed = False

    def exec_command(self, command: str, *, get_pty: bool, timeout: float):
        self.commands.append((command, get_pty, timeout))
        return _Stream(self.channel), _Stream(self.channel), _Stream(self.channel)

    def close(self) -> None:
        self.closed = True


class _RemoteWriter:
    def __init__(self, sftp: "_MemorySftp", path: str) -> None:
        self.sftp = sftp
        self.path = path
        self.payload = bytearray()

    def write(self, payload: bytes) -> None:
        self.payload.extend(payload)

    def flush(self) -> None:
        pass

    def close(self) -> None:
        self.sftp.files[self.path] = bytes(self.payload)


class _MemorySftp:
    def __init__(self) -> None:
        self.directories = {"/"}
        self.files: dict[str, bytes] = {}
        self.symlinks: set[str] = set()
        self.modes: dict[str, int] = {}
        self.closed = False

    def close(self) -> None:
        self.closed = True

    def file(self, path: str, _mode: str) -> _RemoteWriter:
        return _RemoteWriter(self, path)

    def chmod(self, path: str, mode: int) -> None:
        self.modes[path] = mode

    def remove(self, path: str) -> None:
        if path not in self.files and path not in self.symlinks:
            raise FileNotFoundError(path)
        self.files.pop(path, None)
        self.symlinks.discard(path)

    def lstat(self, path: str):
        if path in self.symlinks:
            return SimpleNamespace(st_mode=stat.S_IFLNK | 0o777, st_size=0)
        if path in self.directories:
            return SimpleNamespace(st_mode=stat.S_IFDIR | 0o755, st_size=0)
        if path in self.files:
            return SimpleNamespace(
                st_mode=stat.S_IFREG | 0o644, st_size=len(self.files[path])
            )
        raise FileNotFoundError(path)

    stat = lstat

    def mkdir(self, path: str, mode: int = 0o777) -> None:
        self.directories.add(path)
        self.modes[path] = mode

    def rmdir(self, path: str) -> None:
        prefix = path.rstrip("/") + "/"
        if any(candidate.startswith(prefix) for candidate in self.files):
            raise OSError("directory is not empty")
        self.directories.remove(path)

    def listdir_attr(self, path: str):
        prefix = path.rstrip("/") + "/"
        names: dict[str, Any] = {}
        for candidate in self.directories | set(self.files) | self.symlinks:
            if not candidate.startswith(prefix):
                continue
            remainder = candidate[len(prefix) :]
            if not remainder or "/" in remainder:
                continue
            attrs = self.lstat(candidate)
            attrs.filename = remainder
            names[remainder] = attrs
        return list(names.values())

    def put(self, source: str, destination: str, *, callback, confirm: bool):
        payload = Path(source).read_bytes()
        callback(len(payload), len(payload))
        self.files[destination] = payload
        return SimpleNamespace(st_size=len(payload))

    def get(self, source: str, destination: str, *, callback) -> None:
        payload = self.files[source]
        Path(destination).write_bytes(payload)
        callback(len(payload), len(payload))

    def rename(self, source: str, destination: str) -> None:
        if destination in self.files:
            raise FileExistsError(destination)
        self.files[destination] = self.files.pop(source)

    def posix_rename(self, source: str, destination: str) -> None:
        self.files[destination] = self.files.pop(source)


@pytest.mark.skipif(os.name != "nt", reason="Windows DPAPI is required")
def test_secret_and_host_values_are_tagged_and_process_safe() -> None:
    envelope = protect_secret("password", "Current user")
    secret = values.compute_secret(
        _ctx(
            properties={
                "protected_value": envelope,
                "data_protection_scope": "Current user",
            }
        )
    ).outputs["secret_value"]

    assert secret == {
        runtime.RUNTIME_VALUE_TAG: "secret_data",
        "revision": 1,
        "provider": "windows_dpapi",
        "scope": "CurrentUser",
        "ciphertext_b64": envelope["ciphertext_b64"],
    }
    host = values.compute_host(
        _ctx(
            inputs={
                "address": "host",
                "port": 2222,
                "username": "user",
                "password": secret,
                "use_pageant": True,
            }
        )
    ).outputs["host"]
    assert host[runtime.RUNTIME_VALUE_TAG] == "ssh_sftp_host_data"
    assert host["password"] == secret
    assert host["use_pageant"] is True
    assert deserialize_runtime_value(serialize_runtime_value(host)) == host


def test_host_requires_a_coherent_authentication_source() -> None:
    with pytest.raises(NodeInputNotReadyError, match="password, private key"):
        values.compute_host(
            _ctx(inputs={"address": "host", "username": "user", "port": 22})
        )

    with pytest.raises(ValueError, match="requires a Private key path"):
        values.compute_host(
            _ctx(
                inputs={
                    "address": "host",
                    "username": "user",
                    "port": 22,
                    "private_key_passphrase": {
                        runtime.RUNTIME_VALUE_TAG: runtime.SECRET_RUNTIME_TYPE,
                        "revision": 1,
                        "provider": "windows_dpapi",
                        "scope": "CurrentUser",
                        "ciphertext_b64": "opaque",
                    },
                }
            )
        )


def test_connection_uses_strict_known_hosts_and_locked_timeouts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Client:
        def __init__(self) -> None:
            self.loaded = False
            self.policy = None
            self.connect_kwargs: dict[str, Any] = {}
            self.transport = _Transport()

        def load_system_host_keys(self) -> None:
            self.loaded = True

        def set_missing_host_key_policy(self, policy: Any) -> None:
            self.policy = policy

        def connect(self, **kwargs: Any) -> None:
            self.connect_kwargs = kwargs

        def get_transport(self) -> _Transport:
            return self.transport

        def close(self) -> None:
            pass

    client = Client()
    selected_agent = SimpleNamespace(get_keys=lambda: (), close=lambda: None)
    selected_args = []
    monkeypatch.setattr(runtime.paramiko, "SSHClient", lambda: client)
    monkeypatch.setattr(
        runtime,
        "_selected_agent",
        lambda **kwargs: selected_args.append(kwargs) or selected_agent,
    )
    result = runtime._connect(_host(use_openssh_agent=True), _ctx())

    assert result is client
    assert client.loaded is True
    assert isinstance(client.policy, runtime.paramiko.RejectPolicy)
    assert client._agent is selected_agent
    assert selected_args == [{"use_openssh": True, "use_pageant": False}]
    assert client.connect_kwargs["allow_agent"] is True
    assert client.connect_kwargs["look_for_keys"] is False
    assert client.connect_kwargs["timeout"] == 30.0
    assert client.connect_kwargs["banner_timeout"] == 30.0
    assert client.connect_kwargs["auth_timeout"] == 30.0
    assert client.transport.keepalive == 30


@pytest.mark.parametrize(
    ("failure_site", "expected_closes"),
    (
        ("path_not_file", ()),
        ("path_probe", ()),
        ("password_reveal", ()),
        ("passphrase_reveal", ()),
        ("client", ()),
        ("known_hosts", ("client",)),
        ("host_key_policy", ("client",)),
        ("cancel_registration", ("client",)),
        ("agent_selection", ("client",)),
        ("agent_assignment", ("client", "agent")),
        ("connect", ("client", "agent")),
        ("get_transport", ("client", "agent")),
        ("transport_none", ("client", "agent")),
        ("is_active", ("client", "agent")),
        ("inactive", ("client", "agent")),
        ("keepalive", ("client", "agent")),
        ("cleanup", ("client", "agent")),
    ),
)
def test_connection_failure_error_is_fixed_and_sensitive_text_free(
    monkeypatch: pytest.MonkeyPatch,
    failure_site: str,
    expected_closes: tuple[str, ...],
) -> None:
    address = "LOUD_ADDRESS_SENTINEL.invalid"
    username = "LOUD_USERNAME_SENTINEL"
    passphrase = "LOUD_PASSPHRASE_SENTINEL"
    ciphertext = "LOUD_CIPHERTEXT_SENTINEL"
    key_path = "C:/LOUD_PRIVATE_KEY_SENTINEL.pem"
    logs: list[tuple[str, str]] = []
    close_attempts: list[str] = []
    injected_message = (
        "LOUD_INJECTED_MESSAGE_SENTINEL "
        f"{address} 6553 {username} {key_path} {passphrase} {ciphertext}"
    )
    injected_error = type(
        "LOUD_EXCEPTION_CLASS_SENTINEL",
        (RuntimeError,),
        {},
    )

    def fail() -> None:
        raise injected_error(injected_message)

    class Transport:
        def is_active(self) -> bool:
            if failure_site == "is_active":
                fail()
            return failure_site != "inactive"

        def set_keepalive(self, _seconds: int) -> None:
            if failure_site == "keepalive":
                fail()

    class Client:
        def __setattr__(self, name: str, value: object) -> None:
            if name == "_agent" and failure_site == "agent_assignment":
                fail()
            object.__setattr__(self, name, value)

        def load_system_host_keys(self) -> None:
            if failure_site == "known_hosts":
                fail()

        def set_missing_host_key_policy(self, _policy: Any) -> None:
            if failure_site == "host_key_policy":
                fail()

        def connect(self, **_kwargs: Any) -> None:
            if failure_site in {"connect", "cleanup"}:
                fail()

        def get_transport(self) -> Transport | None:
            if failure_site == "get_transport":
                fail()
            if failure_site == "transport_none":
                return None
            return Transport()

        def close(self) -> None:
            close_attempts.append("client")
            if failure_site == "cleanup":
                raise injected_error("LOUD_CLIENT_CLEANUP_SENTINEL")

    class Agent:
        def close(self) -> None:
            close_attempts.append("agent")
            if failure_site == "cleanup":
                raise injected_error("LOUD_AGENT_CLEANUP_SENTINEL")

    def reveal(_value: object, *, label: str) -> str:
        if failure_site == "password_reveal" and label == "SSH password":
            fail()
        if failure_site == "passphrase_reveal" and label == "Private key passphrase":
            fail()
        return passphrase

    def client_factory() -> Client:
        if failure_site == "client":
            fail()
        return Client()

    def selected_agent(**_kwargs: object) -> Agent:
        if failure_site == "agent_selection":
            fail()
        return Agent()

    def path_is_file(_path: Path) -> bool:
        if failure_site == "path_probe":
            fail()
        return failure_site != "path_not_file"

    secret = {
        runtime.RUNTIME_VALUE_TAG: runtime.SECRET_RUNTIME_TYPE,
        "revision": 1,
        "provider": "windows_dpapi",
        "scope": "CurrentUser",
        "ciphertext_b64": ciphertext,
    }
    monkeypatch.setattr(runtime.Path, "is_file", path_is_file)
    monkeypatch.setattr(runtime, "_reveal_credential", reveal)
    monkeypatch.setattr(runtime.paramiko, "SSHClient", client_factory)
    monkeypatch.setattr(runtime, "_selected_agent", selected_agent)

    context = _ctx(logs=logs)
    context.register_cancel = (
        (lambda _callback: fail())
        if failure_site == "cancel_registration"
        else (lambda _callback: None)
    )
    event_queue: queue.Queue[dict[str, Any]] = queue.Queue()
    executor = object.__new__(NodeExecutor)
    object.__setattr__(
        executor,
        "_publisher",
        RunEventPublisher(
            event_queue,
            run_id="run",
            workspace_id="workspace",
        ),
    )
    object.__setattr__(
        executor,
        "_plan",
        SimpleNamespace(output_ports=lambda _node_id: ()),
    )
    object.__setattr__(executor, "_developer_mode", False)
    object.__setattr__(executor, "_node_decisions", {})
    executor.node_outputs = {}
    executor.executed = set()

    expected_error_type = (
        FileNotFoundError if failure_site == "path_not_file" else RuntimeError
    )
    expected_message = (
        "SSH private key file does not exist. Check the configured private key."
        if failure_site == "path_not_file"
        else (
            "SSH connection failed. "
            "Check the SSH/SFTP Host address, port, credentials, and host key."
        )
    )
    try:
        runtime._connect(
            _host(
                address=address,
                port=6553,
                username=username,
                password=secret,
                private_key_path=key_path,
                private_key_passphrase=secret,
            ),
            context,
        )
    except expected_error_type as error:
        caught_error = error
        NodeExecutor._fail_node(  # noqa: SLF001
            executor,
            "node",
            error,
            started_at_epoch_ms=0.0,
        )
    else:
        pytest.fail("connection failure must raise")

    events = [event_queue.get_nowait(), event_queue.get_nowait()]
    settled_event = next(event for event in events if event["type"] == "node_settled")
    serialized_events = json.dumps(events, sort_keys=True)
    assert str(caught_error) == expected_message
    assert caught_error.__cause__ is None
    assert caught_error.__context__ is None
    assert settled_event["errors"][0]["error"] == expected_message
    assert expected_message in serialized_events
    for forbidden in (
        address,
        "6553",
        username,
        key_path,
        passphrase,
        ciphertext,
        "LOUD_EXCEPTION_CLASS_SENTINEL",
        "LOUD_INJECTED_MESSAGE_SENTINEL",
        "LOUD_CLIENT_CLEANUP_SENTINEL",
        "LOUD_AGENT_CLEANUP_SENTINEL",
    ):
        assert forbidden not in repr(caught_error)
        assert forbidden not in serialized_events
        assert all(forbidden not in message for _level, message in logs)
    assert close_attempts == list(expected_closes)


def test_pageant_selection_fails_closed_off_windows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(runtime.sys, "platform", "linux")
    with pytest.raises(RuntimeError, match="only available on Windows"):
        runtime._selected_agent(use_openssh=False, use_pageant=True)


@pytest.mark.skipif(os.name != "nt", reason="Windows agent backends are required")
def test_windows_agent_flags_select_only_the_named_backends(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from paramiko import win_openssh, win_pageant
    from paramiko.agent import AgentSSH

    connections = []

    class Connection:
        def __init__(self, name: str) -> None:
            self.name = name
            self.closed = False

        def close(self) -> None:
            self.closed = True

    openssh = Connection("openssh")
    pageant = Connection("pageant")
    monkeypatch.setattr(win_openssh, "can_talk_to_agent", lambda: True)
    monkeypatch.setattr(win_openssh, "OpenSSHAgentConnection", lambda: openssh)
    monkeypatch.setattr(win_pageant, "can_talk_to_agent", lambda: True)
    monkeypatch.setattr(win_pageant, "PageantConnection", lambda: pageant)

    def connect(agent, connection) -> None:  # noqa: ANN001
        agent._conn = connection
        agent._keys = (connection.name,)
        connections.append(connection.name)

    monkeypatch.setattr(AgentSSH, "_connect", connect)

    selected = runtime._selected_agent(use_openssh=True, use_pageant=False)
    assert selected.get_keys() == ("openssh",)
    assert connections == ["openssh"]
    selected.close()
    assert openssh.closed is True
    assert pageant.closed is False


@pytest.mark.skipif(os.name != "nt", reason="Windows agent backends are required")
def test_agent_probe_failure_closes_previously_connected_agent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from paramiko import win_openssh, win_pageant
    from paramiko.agent import AgentSSH

    class Connection:
        def __init__(self) -> None:
            self.closed = False

        def close(self) -> None:
            self.closed = True

    openssh = Connection()
    monkeypatch.setattr(win_openssh, "can_talk_to_agent", lambda: True)
    monkeypatch.setattr(win_openssh, "OpenSSHAgentConnection", lambda: openssh)
    monkeypatch.setattr(
        win_pageant,
        "can_talk_to_agent",
        lambda: (_ for _ in ()).throw(RuntimeError("agent probe failed")),
    )

    def connect(agent, connection) -> None:  # noqa: ANN001
        agent._conn = connection
        agent._keys = ()

    monkeypatch.setattr(AgentSSH, "_connect", connect)

    with pytest.raises(RuntimeError, match="agent probe failed"):
        runtime._selected_agent(use_openssh=True, use_pageant=True)

    assert openssh.closed is True


def test_command_maps_nonzero_result_and_cancellation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    logs: list[tuple[str, str]] = []
    client = _CommandClient(_Channel(stdout=[b"out\xff"], stderr=[b"err"], exit_code=9))
    monkeypatch.setattr(runtime, "_connect", lambda _host, _ctx: client)
    result = runtime.run_ssh_command(
        _ctx(
            inputs={"target_host": _host(), "command": "false"},
            logs=logs,
        )
    )

    assert result.outputs == {
        "successful": False,
        "exit_code": 9,
        "output": "out\ufffd",
        "error": "err",
    }
    assert ("warning", "SSH command exited with code 9.") in logs
    assert client.commands == [("false", False, 30.0)]
    assert client.closed is True

    stopped_channel = _Channel(stdout=[b"unused"])
    stopped_client = _CommandClient(stopped_channel)
    monkeypatch.setattr(runtime, "_connect", lambda _host, _ctx: stopped_client)
    with pytest.raises(InterruptedError, match="run_stop_requested"):
        runtime.run_ssh_command(
            _ctx(
                inputs={"target_host": _host(), "command": "sleep"},
                should_stop=lambda: True,
            )
        )
    assert stopped_channel.closed is True


def test_continuous_stdout_cannot_starve_cancellation() -> None:
    class BusyChannel(_Channel):
        def recv_ready(self) -> bool:
            return True

        def recv(self, _size: int) -> bytes:
            return b"x"

        def exit_status_ready(self) -> bool:
            return False

    calls = 0

    def should_stop() -> bool:
        nonlocal calls
        calls += 1
        return calls >= 2

    channel = BusyChannel()
    client = _CommandClient(channel)
    with pytest.raises(InterruptedError, match="run_stop_requested"):
        runtime._execute_command(client, "busy", _ctx(should_stop=should_stop))
    assert channel.closed is True


def test_stream_capture_is_hard_capped() -> None:
    payload = bytearray()
    assert (
        runtime._append_bounded(payload, b"x" * (runtime.STREAM_CAPTURE_LIMIT + 1))
        is True
    )
    assert len(payload) == runtime.STREAM_CAPTURE_LIMIT


def test_script_stages_normalized_source_and_cleans_up(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sftp = _MemorySftp()
    client = _CommandClient(_Channel(stdout=[b"done"], exit_code=0))
    monkeypatch.setattr(runtime, "_connect", lambda _host, _ctx: client)
    monkeypatch.setattr(runtime, "_open_sftp", lambda _client, _ctx: sftp)

    result = runtime.run_ssh_script(
        _ctx(
            inputs={"target_host": _host(), "script": "#!/bin/sh\r\necho ok\r\n"},
            properties={"interpreter": "Custom"},
        )
    )

    command = client.commands[0][0]
    remote_path = command
    assert remote_path.startswith("/tmp/.corex-run-ssh-script-")
    assert remote_path.endswith("/script")
    assert sftp.modes[remote_path] == 0o700
    assert remote_path not in sftp.files
    assert posixpath.dirname(remote_path) not in sftp.directories
    assert result.outputs["successful"] is True
    assert result.outputs["output"] == "done"
    assert sftp.closed is True
    assert client.closed is True


def test_open_sftp_failure_still_closes_connected_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = SimpleNamespace(closed=False)

    def close() -> None:
        client.closed = True

    client.close = close
    monkeypatch.setattr(runtime, "_connect", lambda _host, _ctx: client)
    monkeypatch.setattr(
        runtime,
        "_open_sftp",
        lambda _client, _ctx: (_ for _ in ()).throw(RuntimeError("open failed")),
    )

    with pytest.raises(RuntimeError, match="open failed"):
        runtime.run_ssh_script(
            _ctx(
                inputs={"target_host": _host(), "script": "echo ok"},
                properties={"interpreter": "Bash"},
            )
        )
    assert client.closed is True


def test_custom_script_requires_shebang(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        runtime, "_connect", lambda _host, _ctx: pytest.fail("must not connect")
    )
    with pytest.raises(ValueError, match="require a shebang"):
        runtime.run_ssh_script(
            _ctx(
                inputs={"target_host": _host(), "script": "echo no"},
                properties={"interpreter": "Custom"},
            )
        )


def test_upload_recurses_contents_skips_symlinks_and_commits_atomically(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "a.txt").write_bytes(b"abc")
    (source / "nested").mkdir()
    (source / "nested" / "b.bin").write_bytes(b"12345")
    symlink_created = False
    try:
        (source / "link").symlink_to(source / "a.txt")
        symlink_created = True
    except OSError:
        pass

    logs: list[tuple[str, str]] = []
    sftp = _MemorySftp()
    client = SimpleNamespace(close=lambda: None)
    monkeypatch.setattr(runtime, "_connect", lambda _host, _ctx: client)
    monkeypatch.setattr(runtime, "_open_sftp", lambda _client, _ctx: sftp)
    result = runtime.sftp_upload(
        _ctx(
            inputs={
                "target_host": _host(),
                "sources": [str(source)],
                "destination": "/dest",
                "overwrite": False,
            },
            logs=logs,
        )
    )

    assert sftp.files["/dest/a.txt"] == b"abc"
    assert sftp.files["/dest/nested/b.bin"] == b"12345"
    assert all(".corex-tmp-" not in path for path in sftp.files)
    assert result.outputs == {
        "successful": True,
        "uploaded_bytes": 8,
        "uploaded_files": 2,
    }
    if symlink_created:
        assert any("Skipping symbolic link" in message for _level, message in logs)


def test_upload_overwrite_false_preflights_before_copy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "a.txt").write_text("new", encoding="utf-8")
    (source / "b.txt").write_text("other", encoding="utf-8")
    sftp = _MemorySftp()
    sftp.directories.add("/dest")
    sftp.files["/dest/a.txt"] = b"old"
    monkeypatch.setattr(
        runtime, "_connect", lambda _host, _ctx: SimpleNamespace(close=lambda: None)
    )
    monkeypatch.setattr(runtime, "_open_sftp", lambda _client, _ctx: sftp)

    with pytest.raises(FileExistsError, match="already exists"):
        runtime.sftp_upload(
            _ctx(
                inputs={
                    "target_host": _host(),
                    "sources": [str(source)],
                    "destination": "/dest",
                    "overwrite": False,
                }
            )
        )

    assert sftp.files == {"/dest/a.txt": b"old"}


def test_upload_single_file_can_target_an_exact_remote_filename(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source.txt"
    source.write_bytes(b"payload")
    sftp = _MemorySftp()
    monkeypatch.setattr(
        runtime, "_connect", lambda _host, _ctx: SimpleNamespace(close=lambda: None)
    )
    monkeypatch.setattr(runtime, "_open_sftp", lambda _client, _ctx: sftp)

    result = runtime.sftp_upload(
        _ctx(
            inputs={
                "target_host": _host(),
                "sources": [str(source)],
                "destination": "/renamed.txt",
                "overwrite": False,
            }
        )
    )

    assert sftp.files["/renamed.txt"] == b"payload"
    assert result.outputs["uploaded_bytes"] == 7


def test_download_recurses_contents_contains_paths_and_skips_symlinks(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sftp = _MemorySftp()
    sftp.directories.update({"/source", "/source/nested"})
    sftp.files["/source/a.txt"] = b"abc"
    sftp.files["/source/nested/b.bin"] = b"12345"
    sftp.symlinks.add("/source/link")
    logs: list[tuple[str, str]] = []
    monkeypatch.setattr(
        runtime, "_connect", lambda _host, _ctx: SimpleNamespace(close=lambda: None)
    )
    monkeypatch.setattr(runtime, "_open_sftp", lambda _client, _ctx: sftp)
    destination = tmp_path / "download"

    result = runtime.sftp_download(
        _ctx(
            inputs={
                "target_host": _host(),
                "sources": ["/source"],
                "destination": str(destination),
                "overwrite": False,
            },
            logs=logs,
        )
    )

    assert (destination / "a.txt").read_bytes() == b"abc"
    assert (destination / "nested" / "b.bin").read_bytes() == b"12345"
    assert not (destination / "source").exists()
    assert all(".corex-tmp-" not in path.name for path in destination.rglob("*"))
    assert result.outputs == {
        "successful": True,
        "downloaded_bytes": 8,
        "downloaded_files": 2,
    }
    assert any("Skipping symbolic link" in message for _level, message in logs)

    with pytest.raises(ValueError, match="escapes"):
        runtime._safe_local_target(destination, "../outside.txt")


def test_download_single_file_exact_target_and_no_overwrite_race(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sftp = _MemorySftp()
    sftp.files["/source.txt"] = b"payload"
    monkeypatch.setattr(
        runtime, "_connect", lambda _host, _ctx: SimpleNamespace(close=lambda: None)
    )
    monkeypatch.setattr(runtime, "_open_sftp", lambda _client, _ctx: sftp)
    destination = tmp_path / "renamed.txt"

    result = runtime.sftp_download(
        _ctx(
            inputs={
                "target_host": _host(),
                "sources": ["/source.txt"],
                "destination": str(destination),
                "overwrite": False,
            }
        )
    )
    assert destination.read_bytes() == b"payload"
    assert result.outputs["downloaded_bytes"] == 7

    class RacingSftp(_MemorySftp):
        def get(self, source: str, temporary: str, *, callback) -> None:
            super().get(source, temporary, callback=callback)
            destination.write_bytes(b"concurrent")

    racing = RacingSftp()
    racing.files["/source.txt"] = b"new"
    destination.unlink()
    monkeypatch.setattr(runtime, "_open_sftp", lambda _client, _ctx: racing)
    with pytest.raises(FileExistsError):
        runtime.sftp_download(
            _ctx(
                inputs={
                    "target_host": _host(),
                    "sources": ["/source.txt"],
                    "destination": str(destination),
                    "overwrite": False,
                }
            )
        )
    assert destination.read_bytes() == b"concurrent"
    assert not any(".corex-tmp-" in path.name for path in tmp_path.iterdir())

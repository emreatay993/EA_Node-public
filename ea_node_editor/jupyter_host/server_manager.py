"""Project-scoped embedded Jupyter server lifecycle.

The manager launches Jupyter as a *separate subprocess* (``python -m
jupyter_server``) and only ever talks to it over loopback HTTP -- it never
imports ``jupyter_server``/``notebook`` into the GUI process. That keeps the
heavy Jupyter stack (and its native deps) out of the Qt process, mirrors the
existing external-subprocess execution backend's lifecycle discipline
(terminate -> wait -> kill escalation, bounded stderr tail), and keeps this
module import-cheap + Qt-free so it is safe in headless/test contexts.

One ``JupyterServerManager`` is shared per project root (server root = the
project staging/data area) via ``JupyterServerRegistry``; N notebook nodes =>
1 server process + N lazily-spawned kernels. The tokened localhost URL is built
on demand and is NEVER persisted -- it is rebuilt for each session.
"""

from __future__ import annotations

import atexit
import os
import secrets
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

_HEALTH_CHECK_TIMEOUT_SEC = 30.0
_HEALTH_POLL_INTERVAL_SEC = 0.25
_STDERR_TAIL_MAXLEN = 60
_GRACEFUL_SHUTDOWN_WAIT_SEC = 3.0


class JupyterServerStartError(RuntimeError):
    """Raised when the embedded Jupyter server fails to become healthy."""


@dataclass(frozen=True)
class JupyterServerHandle:
    """A live server's loopback address + session token (never persisted)."""

    base_url: str
    token: str
    port: int

    def notebook_url(self, *, relative_path: str, frontend: str = "notebook") -> str:
        rel = quote(str(relative_path or "").strip().lstrip("/"))
        token_query = quote(self.token)
        if str(frontend or "").strip().lower() == "lab":
            return f"{self.base_url}/doc/tree/{rel}?token={token_query}"
        return f"{self.base_url}/notebooks/{rel}?token={token_query}"


def _free_loopback_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _normalized_root_key(server_root: str | os.PathLike[str]) -> str:
    path = Path(server_root)
    try:
        resolved = path.resolve()
    except OSError:
        resolved = path
    return os.path.normcase(str(resolved))


class JupyterServerManager:
    """Owns a single ``jupyter_server`` subprocess rooted at ``server_root``."""

    def __init__(self, *, server_root: str | os.PathLike[str], python_executable: str = "") -> None:
        # In a frozen build ``sys.executable`` is the bundled GUI exe (not a real
        # interpreter); callers should pass the configured Workflow Python there.
        # In dev, ``sys.executable`` is the project venv -- exactly what we want.
        self._server_root = Path(server_root)
        self._python_executable = str(python_executable or "").strip() or sys.executable
        self._lock = threading.RLock()
        self._process: subprocess.Popen[str] | None = None
        self._handle: JupyterServerHandle | None = None
        self._stderr_tail: deque[str] = deque(maxlen=_STDERR_TAIL_MAXLEN)
        self._stderr_thread: threading.Thread | None = None

    @property
    def server_root(self) -> Path:
        return self._server_root

    def is_running(self) -> bool:
        with self._lock:
            return self._process is not None and self._process.poll() is None

    def ensure_running(self) -> JupyterServerHandle:
        """Start the server if needed and return a live handle (idempotent)."""

        with self._lock:
            if self._handle is not None and self.is_running():
                return self._handle
            return self._start_locked()

    def notebook_url(self, *, relative_path: str, frontend: str = "notebook") -> str:
        return self.ensure_running().notebook_url(relative_path=relative_path, frontend=frontend)

    def stderr_tail(self) -> str:
        with self._lock:
            return "\n".join(self._stderr_tail)[-2000:]

    def _start_locked(self) -> JupyterServerHandle:
        self._server_root.mkdir(parents=True, exist_ok=True)
        port = _free_loopback_port()
        token = secrets.token_urlsafe(32)
        argv = [
            self._python_executable,
            "-m",
            "jupyter_server",
            "--ServerApp.ip=127.0.0.1",
            f"--ServerApp.port={port}",
            "--ServerApp.port_retries=0",
            f"--ServerApp.token={token}",
            f"--ServerApp.root_dir={self._server_root}",
            "--ServerApp.open_browser=False",
            "--ServerApp.password=",
            "--ServerApp.allow_origin=",
            "--ServerApp.quit_button=False",
        ]
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
        process = subprocess.Popen(  # noqa: S603 - fixed argv, loopback-only, token-gated
            argv,
            cwd=str(self._server_root),
            env=os.environ.copy(),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            creationflags=creationflags,
        )
        self._process = process
        self._stderr_tail.clear()
        self._stderr_thread = threading.Thread(
            target=self._drain_stderr,
            args=(process,),
            name="jupyter-server-stderr",
            daemon=True,
        )
        self._stderr_thread.start()

        base_url = f"http://127.0.0.1:{port}"
        if not self._wait_until_healthy(base_url=base_url, token=token, process=process):
            tail = self.stderr_tail()
            self._terminate_process_locked()
            reason = "process exited" if process.poll() is not None else "timed out"
            raise JupyterServerStartError(
                f"Jupyter server {reason} before becoming healthy at {base_url}.\n{tail}"
            )

        handle = JupyterServerHandle(base_url=base_url, token=token, port=port)
        self._handle = handle
        return handle

    def _drain_stderr(self, process: subprocess.Popen[str]) -> None:
        stderr = process.stderr
        if stderr is None:
            return
        while True:
            try:
                line = stderr.readline()
            except (OSError, ValueError):
                return
            if line == "":
                return
            text = line.strip()
            if text:
                self._stderr_tail.append(text)

    def _wait_until_healthy(
        self,
        *,
        base_url: str,
        token: str,
        process: subprocess.Popen[str],
    ) -> bool:
        deadline = time.monotonic() + _HEALTH_CHECK_TIMEOUT_SEC
        status_url = f"{base_url}/api/status?token={quote(token)}"
        while time.monotonic() < deadline:
            if process.poll() is not None:
                return False
            if self._probe_status(status_url, token):
                return True
            time.sleep(_HEALTH_POLL_INTERVAL_SEC)
        return False

    @staticmethod
    def _probe_status(status_url: str, token: str) -> bool:
        request = urllib.request.Request(
            status_url,
            headers={"Authorization": f"token {token}"},
        )
        try:
            with urllib.request.urlopen(request, timeout=2.0) as response:  # noqa: S310 - loopback only
                return 200 <= int(response.status) < 300
        except (urllib.error.URLError, OSError, ValueError):
            return False

    def _post_api(self, path: str) -> bool:
        with self._lock:
            handle = self._handle
        if handle is None:
            return False
        separator = "&" if "?" in path else "?"
        url = f"{handle.base_url}{path}{separator}token={quote(handle.token)}"
        request = urllib.request.Request(
            url,
            data=b"",
            method="POST",
            headers={"Authorization": f"token {handle.token}"},
        )
        try:
            with urllib.request.urlopen(request, timeout=5.0) as response:  # noqa: S310 - loopback only
                return 200 <= int(response.status) < 300
        except (urllib.error.URLError, OSError, ValueError):
            return False

    def restart_kernel(self, kernel_id: str) -> bool:
        kernel = quote(str(kernel_id or "").strip())
        return bool(kernel) and self._post_api(f"/api/kernels/{kernel}/restart")

    def interrupt_kernel(self, kernel_id: str) -> bool:
        kernel = quote(str(kernel_id or "").strip())
        return bool(kernel) and self._post_api(f"/api/kernels/{kernel}/interrupt")

    def shutdown(self) -> None:
        with self._lock:
            process = self._process
            handle = self._handle
            if process is not None and process.poll() is None:
                if handle is not None:
                    # Best-effort graceful shutdown so kernels flush + autosave.
                    self._post_api("/api/shutdown")
                    try:
                        process.wait(timeout=_GRACEFUL_SHUTDOWN_WAIT_SEC)
                    except subprocess.TimeoutExpired:
                        pass
            self._terminate_process_locked()
            self._handle = None
        thread = self._stderr_thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=1.0)

    def _terminate_process_locked(self) -> None:
        process = self._process
        if process is None:
            return
        try:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=2.0)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=1.0)
        except Exception:  # noqa: BLE001 - teardown must never raise
            pass
        self._process = None


class JupyterServerRegistry:
    """Process-wide registry of one server manager per project root."""

    _instance: "JupyterServerRegistry | None" = None
    _instance_lock = threading.Lock()

    def __init__(self) -> None:
        self._managers: dict[str, JupyterServerManager] = {}
        self._lock = threading.RLock()

    @classmethod
    def instance(cls) -> "JupyterServerRegistry":
        with cls._instance_lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def manager_for(
        self,
        server_root: str | os.PathLike[str],
        *,
        python_executable: str = "",
    ) -> JupyterServerManager:
        key = _normalized_root_key(server_root)
        with self._lock:
            manager = self._managers.get(key)
            if manager is None:
                manager = JupyterServerManager(
                    server_root=server_root,
                    python_executable=python_executable,
                )
                self._managers[key] = manager
            return manager

    def shutdown_for(self, server_root: str | os.PathLike[str]) -> None:
        key = _normalized_root_key(server_root)
        with self._lock:
            manager = self._managers.pop(key, None)
        if manager is not None:
            manager.shutdown()

    def shutdown_all(self) -> None:
        with self._lock:
            managers = list(self._managers.values())
            self._managers.clear()
        for manager in managers:
            manager.shutdown()


@atexit.register
def _shutdown_all_servers_on_exit() -> None:
    JupyterServerRegistry.instance().shutdown_all()


__all__ = [
    "JupyterServerHandle",
    "JupyterServerManager",
    "JupyterServerRegistry",
    "JupyterServerStartError",
]

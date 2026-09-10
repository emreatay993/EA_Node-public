from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


_BOOTSTRAP_SENTINEL = "EA_NODE_EDITOR_BOOTSTRAPPED"
_QT_QUICK_CONTROLS_STYLE = "Basic"


def _path_key(path: Path) -> str:
    return os.path.normcase(str(path.resolve()))


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _find_worktree_python(repo_root: Path) -> Path | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_root), "worktree", "list", "--porcelain"],
            capture_output=True,
            check=False,
            text=True,
        )
    except OSError:
        return None

    repo_root_key = _path_key(repo_root)
    for line in result.stdout.splitlines():
        if not line.startswith("worktree "):
            continue
        worktree_path = Path(line[len("worktree ") :].strip())
        if _path_key(worktree_path) == repo_root_key:
            continue
        candidate = worktree_path / "venv" / "Scripts" / "python.exe"
        if candidate.is_file():
            return candidate
    return None


def _preferred_python(repo_root: Path) -> Path | None:
    local_python = repo_root / "venv" / "Scripts" / "python.exe"
    if local_python.is_file():
        return local_python
    return _find_worktree_python(repo_root)


def _bootstrap_python(module_name: str = "ea_node_editor.bootstrap") -> None:
    if getattr(sys, "frozen", False):
        return

    if os.environ.get(_BOOTSTRAP_SENTINEL) == "1":
        return

    repo_root = _repo_root()
    preferred_python = _preferred_python(repo_root)
    if preferred_python is None:
        return

    if _path_key(Path(sys.executable)) == _path_key(preferred_python):
        return

    env = os.environ.copy()
    env[_BOOTSTRAP_SENTINEL] = "1"
    os.chdir(repo_root)
    os.execvpe(
        str(preferred_python),
        [str(preferred_python), "-m", module_name, *sys.argv[1:]],
        env,
    )


def configure_qquick_controls_runtime() -> None:
    if sys.platform != "win32":
        return
    if os.environ.get("QT_QUICK_CONTROLS_STYLE"):
        return
    # PyQt6 6.11 on Windows can miss the Windows Quick Controls style runtime DLL.
    os.environ["QT_QUICK_CONTROLS_STYLE"] = _QT_QUICK_CONTROLS_STYLE


def main() -> int:
    if len(sys.argv) == 6 and sys.argv[1] == "--private-mechanical-owner" and sys.argv[2] == "--owner-child":
        from ea_node_editor.addons.mechanical.owner_process import _child
        return _child(int(sys.argv[3]), sys.argv[4], sys.argv[5])
    _bootstrap_python()
    configure_qquick_controls_runtime()
    from ea_node_editor.telemetry.startup_profile import phase

    with phase("bootstrap.import app"):
        from ea_node_editor.app import run

    return run()


def headless_main() -> int:
    _bootstrap_python("ea_node_editor.execution.runtime_cli")
    from ea_node_editor.execution.runtime_cli import main as run_headless_runtime

    return run_headless_runtime(sys.argv[1:])


if __name__ == "__main__":
    raise SystemExit(main())

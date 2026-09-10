"""Prepare an isolated worktree, run a packet, and optionally wrap it into main."""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from devtools.work_packet_runner import (
    PacketDefinition,
    PacketRunnerError,
    PacketSet,
    discover_packet_set_dir,
    ensure_codex_available,
    execute_packet,
    git_status_short,
    load_packet_set,
)


WORKTREE_BRANCH_RE = re.compile(r"^branch refs/heads/(?P<branch>.+)$")
WORKTREE_PATH_RE = re.compile(r"^worktree (?P<path>.+)$")
SAFE_PATH_RE = re.compile(r"[^A-Za-z0-9._-]+")


class PacketThreadError(RuntimeError):
    """Raised when packet-thread orchestration cannot proceed safely."""


@dataclass(frozen=True)
class PacketThreadResult:
    packet_commit_sha: str
    merge_commit_sha: str
    branch_deleted: bool
    worktree_removed: bool
    merge_workspace: Path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Create an isolated worktree for a packet, run it, and optionally wrap it into main."
        )
    )
    parser.add_argument("packet_set", help="Packet set slug or path.")
    parser.add_argument("--packet", required=True, help="Packet code to run, for example P05.")
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parent.parent,
        help="Repository root.",
    )
    parser.add_argument(
        "--base-branch",
        default="main",
        help="Base branch for new packet worktrees. Default: main.",
    )
    parser.add_argument(
        "--codex-bin",
        default="codex",
        help="Codex executable to invoke. Default: codex.",
    )
    parser.add_argument(
        "--artifacts-dir",
        type=Path,
        default=Path("artifacts") / "work_packet_runs",
        help="Artifacts directory, relative to --root by default.",
    )
    parser.add_argument(
        "--worktrees-dir",
        type=Path,
        default=Path("artifacts") / "work_packet_worktrees",
        help="Worktree directory, relative to --root by default.",
    )
    parser.add_argument(
        "--no-wrap-up",
        action="store_true",
        help="Run the packet but skip packet wrap-up.",
    )
    return parser


def resolve_dir(root: Path, value: Path) -> Path:
    if value.is_absolute():
        return value
    return root / value


def run_git(args: list[str], *, cwd: Path) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        message = result.stderr.strip() or result.stdout.strip() or "git command failed"
        raise PacketThreadError(f"git {' '.join(args)} failed in {cwd}: {message}")
    return result.stdout.strip()


def local_branch_exists(repo_root: Path, branch: str) -> bool:
    result = subprocess.run(
        ["git", "show-ref", "--verify", "--quiet", f"refs/heads/{branch}"],
        cwd=repo_root,
        check=False,
    )
    return result.returncode == 0


def worktree_listing(repo_root: Path) -> list[tuple[Path, str | None]]:
    output = run_git(["worktree", "list", "--porcelain"], cwd=repo_root)
    entries: list[tuple[Path, str | None]] = []
    path: Path | None = None
    branch: str | None = None
    for line in output.splitlines():
        path_match = WORKTREE_PATH_RE.match(line)
        if path_match:
            if path is not None:
                entries.append((path, branch))
            path = Path(path_match.group("path")).resolve()
            branch = None
            continue
        branch_match = WORKTREE_BRANCH_RE.match(line)
        if branch_match:
            branch = branch_match.group("branch")
            continue
        if not line.strip() and path is not None:
            entries.append((path, branch))
            path = None
            branch = None
    if path is not None:
        entries.append((path, branch))
    return entries


def branch_worktrees(repo_root: Path, branch: str) -> list[Path]:
    return [path for path, listed_branch in worktree_listing(repo_root) if listed_branch == branch]


def safe_worktree_leaf(branch_label: str) -> str:
    cleaned = SAFE_PATH_RE.sub("-", branch_label).strip("-")
    return cleaned or "packet"


def create_packet_worktree(
    *,
    repo_root: Path,
    worktrees_root: Path,
    base_branch: str,
    branch_label: str,
) -> Path:
    worktrees_root.mkdir(parents=True, exist_ok=True)
    branch_paths = branch_worktrees(repo_root, branch_label)
    if branch_paths:
        raise PacketThreadError(
            f"Branch {branch_label} is already checked out in worktree(s): "
            + ", ".join(str(path) for path in branch_paths)
        )

    worktree_path = worktrees_root / safe_worktree_leaf(branch_label)
    if worktree_path.exists():
        raise PacketThreadError(
            f"Worktree path already exists for {branch_label}: {worktree_path}"
        )

    if local_branch_exists(repo_root, branch_label):
        run_git(["worktree", "add", str(worktree_path), branch_label], cwd=repo_root)
    else:
        run_git(
            ["worktree", "add", str(worktree_path), "-b", branch_label, base_branch],
            cwd=repo_root,
        )
    return worktree_path


def packet_set_relative_path(repo_root: Path, packet_set_dir: Path) -> Path:
    try:
        return packet_set_dir.resolve().relative_to(repo_root.resolve())
    except ValueError as exc:
        raise PacketThreadError(
            f"Packet set {packet_set_dir} is not inside repository root {repo_root}."
        ) from exc


def packet_commit_message(packet_set: PacketSet, packet: PacketDefinition) -> str:
    return f"Complete {packet_set.slug.upper()} {packet.code} packet"


def short_head_sha(cwd: Path) -> str:
    return run_git(["rev-parse", "--short", "HEAD"], cwd=cwd)


def maybe_commit_packet_changes(
    *,
    worktree_path: Path,
    packet_set: PacketSet,
    packet: PacketDefinition,
) -> str:
    status = git_status_short(worktree_path)
    if status:
        run_git(["add", "-A"], cwd=worktree_path)
        run_git(["commit", "-m", packet_commit_message(packet_set, packet)], cwd=worktree_path)
    return short_head_sha(worktree_path)


def ensure_packet_passed(packet_set: PacketSet, packet: PacketDefinition) -> None:
    refreshed = load_packet_set(packet_set.directory)
    refreshed_packet = refreshed.packet_by_code(packet.code)
    if refreshed_packet.status != "PASS":
        raise PacketThreadError(
            f"{packet.code} did not end in PASS in {refreshed.status_path}; "
            f"current status is {refreshed_packet.status}."
        )


def main_worktree_candidates(repo_root: Path, base_branch: str) -> list[Path]:
    return branch_worktrees(repo_root, base_branch)


def choose_merge_workspace(
    *,
    repo_root: Path,
    packet_worktree: Path,
    base_branch: str,
) -> Path:
    main_paths = [path for path in main_worktree_candidates(repo_root, base_branch) if path != packet_worktree]
    for path in main_paths:
        if not git_status_short(path):
            return path
    if main_paths:
        raise PacketThreadError(
            f"Cannot auto-wrap because {base_branch} is checked out in a dirty worktree: "
            + ", ".join(str(path) for path in main_paths)
        )

    if git_status_short(packet_worktree):
        raise PacketThreadError(
            f"Cannot switch packet worktree to {base_branch}; worktree is dirty: {packet_worktree}"
        )
    run_git(["switch", base_branch], cwd=packet_worktree)
    return packet_worktree


def remove_worktree(repo_root: Path, worktree_path: Path) -> bool:
    if not worktree_path.exists():
        return False
    run_git(["worktree", "remove", str(worktree_path)], cwd=repo_root)
    return True


def delete_local_branch(cwd: Path, branch_label: str) -> bool:
    run_git(["branch", "-d", branch_label], cwd=cwd)
    return True


def wrap_packet_branch(
    *,
    repo_root: Path,
    packet_worktree: Path,
    packet_set: PacketSet,
    packet: PacketDefinition,
    base_branch: str,
) -> PacketThreadResult:
    if load_packet_set(packet_set.directory).packet_by_code(packet.code).status != "PASS":
        raise PacketThreadError(
            f"Refusing to wrap {packet.code}; status ledger does not show PASS."
        )

    packet_sha = maybe_commit_packet_changes(
        worktree_path=packet_worktree,
        packet_set=packet_set,
        packet=packet,
    )

    merge_workspace = choose_merge_workspace(
        repo_root=repo_root,
        packet_worktree=packet_worktree,
        base_branch=base_branch,
    )
    if git_status_short(merge_workspace):
        raise PacketThreadError(
            f"Merge workspace is dirty, cannot continue packet wrap-up: {merge_workspace}"
        )

    run_git(["merge", "--no-ff", "--no-edit", packet.branch_label], cwd=merge_workspace)
    merge_sha = short_head_sha(merge_workspace)

    worktree_removed = False
    if merge_workspace != packet_worktree:
        worktree_removed = remove_worktree(repo_root, packet_worktree)
    branch_deleted = delete_local_branch(merge_workspace, packet.branch_label)
    if merge_workspace == packet_worktree and packet_worktree != repo_root:
        worktree_removed = remove_worktree(repo_root, packet_worktree)

    return PacketThreadResult(
        packet_commit_sha=packet_sha,
        merge_commit_sha=merge_sha,
        branch_deleted=branch_deleted,
        worktree_removed=worktree_removed,
        merge_workspace=merge_workspace,
    )


def run(args: argparse.Namespace) -> int:
    repo_root = args.root.resolve()
    packet_set_dir = discover_packet_set_dir(repo_root, args.packet_set)
    packet_set = load_packet_set(packet_set_dir)
    packet = packet_set.packet_by_code(args.packet)
    worktrees_root = resolve_dir(repo_root, args.worktrees_dir)
    artifacts_root = resolve_dir(repo_root, args.artifacts_dir)
    codex_bin = ensure_codex_available(args.codex_bin)
    relative_packet_set = packet_set_relative_path(repo_root, packet_set.directory)

    print("[packet-thread] phase=preparing")
    worktree_path = create_packet_worktree(
        repo_root=repo_root,
        worktrees_root=worktrees_root,
        base_branch=args.base_branch,
        branch_label=packet.branch_label,
    )
    print(f"Worktree: {worktree_path}")
    print(f"Branch: {packet.branch_label}")

    worktree_packet_set = load_packet_set(worktree_path / relative_packet_set)
    worktree_packet = worktree_packet_set.packet_by_code(packet.code)

    print("[packet-thread] phase=running")
    exit_code = execute_packet(
        repo_root=worktree_path,
        packet_set=worktree_packet_set,
        packet=worktree_packet,
        codex_bin=codex_bin,
        artifacts_root=artifacts_root,
        dry_run=False,
        prompt_preamble=(
            f"Execution context note: this worktree is already on target branch "
            f"`{packet.branch_label}` at `{worktree_path}`. Reuse the existing branch; do not create another one. "
            f"Treat `{worktree_path}` as the only editable root. `apply_patch` can resolve relative paths "
            f"against the original workspace, so use absolute paths under `{worktree_path}` for all patches "
            f"and verify `git rev-parse --show-toplevel` before editing."
        ),
    )
    if exit_code != 0:
        print(f"[packet-thread] phase=failed exit_code={exit_code}")
        return exit_code

    ensure_packet_passed(worktree_packet_set, worktree_packet)
    if args.no_wrap_up:
        print("[packet-thread] phase=passed wrap_up=skipped")
        return 0

    print("[packet-thread] phase=wrapping")
    result = wrap_packet_branch(
        repo_root=repo_root,
        packet_worktree=worktree_path,
        packet_set=worktree_packet_set,
        packet=worktree_packet,
        base_branch=args.base_branch,
    )
    print(f"Packet commit: {result.packet_commit_sha}")
    print(f"Merge commit: {result.merge_commit_sha}")
    print(f"Merge workspace: {result.merge_workspace}")
    print(f"Branch deleted: {'yes' if result.branch_deleted else 'no'}")
    print(f"Worktree removed: {'yes' if result.worktree_removed else 'no'}")
    print("[packet-thread] phase=passed wrap_up=completed")
    return 0


def main(argv: Iterable[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    try:
        return run(args)
    except (PacketThreadError, PacketRunnerError) as exc:
        parser.exit(1, f"Error: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())

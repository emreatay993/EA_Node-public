"""Run Codex packet prompts using the repo's work-packet conventions."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable


PACKET_CODE_RE = re.compile(r"\b(P\d+[A-Z]?)\b")
PACKET_FILE_RE = re.compile(
    r"^(?P<prefix>[A-Z0-9_]+)_(?P<code>P\d+[A-Z]?)_(?P<slug>.+)\.md$"
)
MANIFEST_ORDER_RE = re.compile(
    r"^\d+\.\s+`?(?P<filename>[A-Z0-9_]+_P\d+[A-Z]?_[^`]+\.md)`?\s*$",
    re.MULTILINE,
)
BRANCH_ROW_RE = re.compile(
    r"^\|\s*(?P<label>P\d+[A-Z]?\b[^|]*)\|\s*`(?P<branch>[^`]+)`\s*\|",
    re.MULTILINE,
)


class PacketRunnerError(RuntimeError):
    """Raised when packet automation cannot proceed safely."""


@dataclass(frozen=True)
class PacketDefinition:
    """Resolved metadata for one packet in a packet set."""

    code: str
    spec_filename: str
    prompt_filename: str
    branch_label: str
    status: str


@dataclass(frozen=True)
class PacketSet:
    """Manifest + status view for one packet set directory."""

    slug: str
    directory: Path
    manifest_path: Path
    status_path: Path
    packets: tuple[PacketDefinition, ...]

    def packet_by_code(self, code: str) -> PacketDefinition:
        for packet in self.packets:
            if packet.code == code:
                return packet
        raise PacketRunnerError(f"Packet {code} is not defined in {self.directory}.")


def repo_root_from_here() -> Path:
    return Path(__file__).resolve().parent.parent


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run Codex packet prompts using manifest order and status-ledger PASS gating."
        )
    )
    parser.add_argument(
        "packet_set",
        help=(
            "Packet set slug under docs/specs/work_packets/ or an absolute/relative path "
            "to the packet-set directory."
        ),
    )
    parser.add_argument(
        "--packet",
        help="Specific packet code to run, for example P05 or P11A. Defaults to the next ready packet.",
    )
    parser.add_argument(
        "--count",
        type=int,
        default=1,
        help="Maximum number of packets to run sequentially in this invocation. Default: 1.",
    )
    parser.add_argument(
        "--codex-bin",
        default="codex",
        help="Codex executable to invoke. Default: codex.",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=repo_root_from_here(),
        help="Repository root. Default: current repo root.",
    )
    parser.add_argument(
        "--artifacts-dir",
        type=Path,
        default=Path("artifacts") / "work_packet_runs",
        help="Directory for per-run logs and output summaries, relative to --root by default.",
    )
    parser.add_argument(
        "--allow-dirty",
        action="store_true",
        help="Allow starting when git status is dirty. By default the runner stops before crossing packet boundaries on a dirty worktree.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Resolve the next ready packet and print the planned execution without launching Codex.",
    )
    return parser


def normalize_packet_code(value: str) -> str:
    code = value.strip().upper()
    match = PACKET_CODE_RE.fullmatch(code)
    if not match:
        raise PacketRunnerError(f"Invalid packet code: {value!r}")
    return code


def resolve_artifacts_dir(root: Path, artifacts_dir: Path) -> Path:
    if artifacts_dir.is_absolute():
        return artifacts_dir
    return root / artifacts_dir


def discover_packet_set_dir(root: Path, packet_set_arg: str) -> Path:
    candidate = Path(packet_set_arg)
    if candidate.exists():
        return candidate.resolve()
    by_slug = root / "docs" / "specs" / "work_packets" / packet_set_arg
    if by_slug.exists():
        return by_slug.resolve()
    raise PacketRunnerError(
        f"Packet set {packet_set_arg!r} was not found as a path or under "
        f"{root / 'docs/specs/work_packets'}."
    )


def find_single_packet_file(packet_set_dir: Path, suffix: str) -> Path:
    matches = sorted(packet_set_dir.glob(f"*{suffix}"))
    if len(matches) != 1:
        raise PacketRunnerError(
            f"Expected exactly one *{suffix} file in {packet_set_dir}, found {len(matches)}."
        )
    return matches[0]


def is_packet_set_dir(candidate: Path) -> bool:
    if not candidate.is_dir():
        return False
    manifest_matches = list(candidate.glob("*_MANIFEST.md"))
    status_matches = list(candidate.glob("*_STATUS.md"))
    return len(manifest_matches) == 1 and len(status_matches) == 1


def discover_packet_set_dirs(packet_root: Path) -> list[Path]:
    resolved_root = packet_root.resolve()
    if is_packet_set_dir(resolved_root):
        return [resolved_root]
    packet_set_dirs = [path.resolve() for path in sorted(resolved_root.iterdir()) if is_packet_set_dir(path)]
    if not packet_set_dirs:
        raise PacketRunnerError(
            f"No packet sets were found in {resolved_root}. "
            "Select a packet-set directory or a folder that contains packet-set subdirectories."
        )
    return packet_set_dirs


def parse_manifest(manifest_path: Path) -> tuple[list[str], dict[str, str]]:
    text = manifest_path.read_text(encoding="utf-8")
    ordered_specs = [match.group("filename") for match in MANIFEST_ORDER_RE.finditer(text)]
    if not ordered_specs:
        raise PacketRunnerError(f"No packet order entries were found in {manifest_path}.")

    branch_labels: dict[str, str] = {}
    for match in BRANCH_ROW_RE.finditer(text):
        code_match = PACKET_CODE_RE.search(match.group("label"))
        if not code_match:
            continue
        branch_labels[code_match.group(1)] = match.group("branch").strip()

    if not branch_labels:
        raise PacketRunnerError(f"No branch-label table rows were found in {manifest_path}.")
    return ordered_specs, branch_labels


def parse_status_ledger(status_path: Path) -> dict[str, str]:
    rows: dict[str, str] = {}
    for raw_line in status_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line.startswith("|"):
            continue
        columns = [column.strip() for column in line.strip("|").split("|")]
        if len(columns) < 3:
            continue
        if columns[0] == "Packet" or set(columns[0]) == {"-"}:
            continue
        match = PACKET_CODE_RE.match(columns[0])
        if not match:
            continue
        rows[match.group(1)] = columns[2].upper()
    if not rows:
        raise PacketRunnerError(f"No packet status rows were found in {status_path}.")
    return rows


def spec_to_packet_code(spec_filename: str) -> str:
    match = PACKET_FILE_RE.match(spec_filename)
    if not match:
        raise PacketRunnerError(f"Malformed packet spec filename: {spec_filename}")
    return match.group("code")


def prompt_filename_for(spec_filename: str) -> str:
    if not spec_filename.endswith(".md"):
        raise PacketRunnerError(f"Packet spec filename must end with .md: {spec_filename}")
    return spec_filename[:-3] + "_PROMPT.md"


def load_packet_set(packet_set_dir: Path) -> PacketSet:
    manifest_path = find_single_packet_file(packet_set_dir, "_MANIFEST.md")
    status_path = find_single_packet_file(packet_set_dir, "_STATUS.md")
    ordered_specs, branch_labels = parse_manifest(manifest_path)
    statuses = parse_status_ledger(status_path)

    packets: list[PacketDefinition] = []
    for spec_filename in ordered_specs:
        code = spec_to_packet_code(spec_filename)
        prompt_filename = prompt_filename_for(spec_filename)
        prompt_path = packet_set_dir / prompt_filename
        spec_path = packet_set_dir / spec_filename
        if not spec_path.exists():
            raise PacketRunnerError(f"Packet spec is missing: {spec_path}")
        if not prompt_path.exists():
            raise PacketRunnerError(f"Packet prompt is missing: {prompt_path}")
        if code not in branch_labels:
            raise PacketRunnerError(f"Branch label for {code} is missing in {manifest_path}.")
        if code not in statuses:
            raise PacketRunnerError(f"Status row for {code} is missing in {status_path}.")
        packets.append(
            PacketDefinition(
                code=code,
                spec_filename=spec_filename,
                prompt_filename=prompt_filename,
                branch_label=branch_labels[code],
                status=statuses[code],
            )
        )

    return PacketSet(
        slug=packet_set_dir.name,
        directory=packet_set_dir,
        manifest_path=manifest_path,
        status_path=status_path,
        packets=tuple(packets),
    )


def select_next_ready_packet(
    packet_set: PacketSet,
    requested_code: str | None = None,
) -> PacketDefinition | None:
    if requested_code is not None:
        requested_code = normalize_packet_code(requested_code)
        requested_packet = packet_set.packet_by_code(requested_code)
        blocking = [
            packet.code
            for packet in packet_set.packets
            if packet.code != requested_packet.code
            and packet_set.packets.index(packet) < packet_set.packets.index(requested_packet)
            and packet.status != "PASS"
        ]
        if blocking:
            raise PacketRunnerError(
                f"{requested_packet.code} is blocked until earlier packets are PASS: "
                + ", ".join(blocking)
            )
        if requested_packet.status == "PASS":
            return None
        return requested_packet

    for packet in packet_set.packets:
        if packet.status != "PASS":
            return packet
    return None


def git_status_short(root: Path) -> str:
    result = subprocess.run(
        ["git", "status", "--short"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise PacketRunnerError(
            f"git status --short failed in {root}: {result.stderr.strip() or result.stdout.strip()}"
        )
    return result.stdout.strip()


def ensure_clean_worktree(root: Path) -> None:
    status = git_status_short(root)
    if status:
        raise PacketRunnerError(
            "Refusing to start a packet on a dirty worktree.\n"
            "Run with --allow-dirty if you intentionally want to override this guard.\n"
            f"git status --short:\n{status}"
        )


def ensure_codex_available(codex_bin: str) -> str:
    resolved = shutil.which(codex_bin)
    if resolved:
        return resolved
    if codex_bin == "codex":
        home = Path.home()
        fallback = home / ".codex" / "bin" / "wsl" / "codex"
        if fallback.exists():
            return str(fallback)
    candidate = Path(codex_bin)
    if candidate.exists():
        return str(candidate)
    raise PacketRunnerError(
        f"Codex executable {codex_bin!r} was not found on PATH and does not exist as a file."
    )


def packet_artifact_dir(base_dir: Path, packet_set: PacketSet, packet: PacketDefinition) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return base_dir / packet_set.slug / f"{timestamp}-{packet.code.lower()}"


def write_metadata(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def run_codex_exec(
    codex_bin: str,
    repo_root: Path,
    prompt_text: str,
    last_message_path: Path,
    log_path: Path,
) -> int:
    command = [
        codex_bin,
        "exec",
        "-C",
        str(repo_root),
        "--skip-git-repo-check",
        "-o",
        str(last_message_path),
        "-",
    ]
    process = subprocess.Popen(
        command,
        cwd=repo_root,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
    )

    assert process.stdin is not None
    process.stdin.write(prompt_text)
    process.stdin.close()

    assert process.stdout is not None
    with log_path.open("w", encoding="utf-8") as log_file:
        for line in process.stdout:
            sys.stdout.write(line)
            log_file.write(line)
    return process.wait()


def format_packet_summary(packet_set: PacketSet, packet: PacketDefinition, artifact_dir: Path) -> str:
    lines = [
        f"Packet set: {packet_set.slug}",
        f"Manifest: {packet_set.manifest_path}",
        f"Status ledger: {packet_set.status_path}",
        f"Packet: {packet.code}",
        f"Spec: {packet_set.directory / packet.spec_filename}",
        f"Prompt: {packet_set.directory / packet.prompt_filename}",
        f"Branch label: {packet.branch_label}",
        f"Current status: {packet.status}",
        f"Artifacts: {artifact_dir}",
    ]
    return "\n".join(lines)


def execute_packet(
    repo_root: Path,
    packet_set: PacketSet,
    packet: PacketDefinition,
    codex_bin: str,
    artifacts_root: Path,
    dry_run: bool,
    prompt_preamble: str = "",
) -> int:
    resolved_repo_root = repo_root.resolve()
    artifact_dir = packet_artifact_dir(artifacts_root, packet_set, packet)
    summary = format_packet_summary(packet_set, packet, artifact_dir)
    if dry_run:
        print(summary)
        return 0

    artifact_dir.mkdir(parents=True, exist_ok=True)
    prompt_path = packet_set.directory / packet.prompt_filename
    prompt_text = prompt_path.read_text(encoding="utf-8")
    worktree_guard = (
        f"Execution context note: the assigned repository root is `{resolved_repo_root}`. "
        f"Treat `{resolved_repo_root}` as the only editable root. `apply_patch` can resolve relative paths "
        f"against the original workspace, so use absolute paths under `{resolved_repo_root}` for all patches "
        f"and verify `git rev-parse --show-toplevel` before editing."
    )
    prompt_text = worktree_guard + "\n\n" + prompt_text
    if prompt_preamble:
        prompt_text = prompt_preamble.rstrip() + "\n\n" + prompt_text
    prompt_copy_path = artifact_dir / prompt_path.name
    prompt_copy_path.write_text(prompt_text, encoding="utf-8")

    last_message_path = artifact_dir / "codex_last_message.txt"
    log_path = artifact_dir / "codex_stdout.log"
    metadata_path = artifact_dir / "run_metadata.json"
    write_metadata(
        metadata_path,
        {
            "packet_set": packet_set.slug,
            "packet": packet.code,
            "spec_path": str(packet_set.directory / packet.spec_filename),
            "prompt_path": str(prompt_path),
            "branch_label": packet.branch_label,
            "status_path": str(packet_set.status_path),
            "manifest_path": str(packet_set.manifest_path),
        },
    )

    print(summary)
    print("Launching Codex packet run...")
    return_code = run_codex_exec(
        codex_bin=codex_bin,
        repo_root=repo_root,
        prompt_text=prompt_text,
        last_message_path=last_message_path,
        log_path=log_path,
    )
    print(f"Codex exit code: {return_code}")
    return return_code


def run(args: argparse.Namespace) -> int:
    repo_root = args.root.resolve()
    packet_set_dir = discover_packet_set_dir(repo_root, args.packet_set)
    artifacts_root = resolve_artifacts_dir(repo_root, args.artifacts_dir)
    codex_bin = args.codex_bin if args.dry_run else ensure_codex_available(args.codex_bin)

    if args.count < 1:
        raise PacketRunnerError("--count must be at least 1.")
    if not args.allow_dirty and not args.dry_run:
        ensure_clean_worktree(repo_root)

    requested_code = args.packet
    executed_packets: list[str] = []
    for _ in range(args.count):
        packet_set = load_packet_set(packet_set_dir)
        packet = select_next_ready_packet(packet_set, requested_code=requested_code)
        if packet is None:
            if not executed_packets:
                if requested_code:
                    print(f"{normalize_packet_code(requested_code)} is already PASS. Nothing to run.")
                else:
                    print(f"All packets are PASS for {packet_set.slug}. Nothing to run.")
            break

        exit_code = execute_packet(
            repo_root=repo_root,
            packet_set=packet_set,
            packet=packet,
            codex_bin=codex_bin,
            artifacts_root=artifacts_root,
            dry_run=args.dry_run,
        )
        if args.dry_run:
            break
        if exit_code != 0:
            raise PacketRunnerError(
                f"Codex exited with code {exit_code} while running {packet.code}."
            )

        refreshed_packet_set = load_packet_set(packet_set_dir)
        refreshed_packet = refreshed_packet_set.packet_by_code(packet.code)
        if refreshed_packet.status != "PASS":
            raise PacketRunnerError(
                f"{packet.code} completed with exit code 0, but {refreshed_packet_set.status_path} "
                f"still shows status {refreshed_packet.status!r} instead of PASS."
            )

        executed_packets.append(packet.code)
        requested_code = None

    return 0


def main(argv: Iterable[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    try:
        return run(args)
    except PacketRunnerError as exc:
        parser.exit(1, f"Error: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())

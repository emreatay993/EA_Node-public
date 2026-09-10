import tempfile
import unittest
from pathlib import Path

from devtools.work_packet_runner import (
    PacketRunnerError,
    discover_packet_set_dirs,
    load_packet_set,
    select_next_ready_packet,
)
from devtools.work_packet_thread import (
    PacketThreadError,
    packet_set_relative_path,
    safe_worktree_leaf,
)


class WorkPacketRunnerTests(unittest.TestCase):
    def make_packet_set(self, root: Path, slug: str = "demo_packets") -> Path:
        packet_dir = root / slug
        packet_dir.mkdir(parents=True)

        (packet_dir / "DEMO_MANIFEST.md").write_text(
            """# Demo Manifest

## Packet Order (Strict)

1. `DEMO_P00_bootstrap.md`
2. `DEMO_P01_alpha.md`
3. `DEMO_P02_beta.md`

## Branch Labels

| Packet | Branch Label | Intent |
|---|---|---|
| P00 Bootstrap | `codex/demo/p00-bootstrap` | Bootstrap |
| P01 Alpha | `codex/demo/p01-alpha` | Alpha |
| P02 Beta | `codex/demo/p02-beta` | Beta |
""",
            encoding="utf-8",
        )

        (packet_dir / "DEMO_STATUS.md").write_text(
            """# Demo Status

| Packet | Branch Label | Status | Commit SHA | Commands | Tests | Artifacts | Residual Risks |
|---|---|---|---|---|---|---|---|
| P00 Bootstrap | `codex/demo/p00-bootstrap` | PASS | `n/a` | done | pass | files | none |
| P01 Alpha | `codex/demo/p01-alpha` | PASS | `abc1234` | done | pass | files | none |
| P02 Beta | `codex/demo/p02-beta` | PENDING | `n/a` | pending | pending | pending | pending |
""",
            encoding="utf-8",
        )

        for filename in (
            "DEMO_P00_bootstrap.md",
            "DEMO_P00_bootstrap_PROMPT.md",
            "DEMO_P01_alpha.md",
            "DEMO_P01_alpha_PROMPT.md",
            "DEMO_P02_beta.md",
            "DEMO_P02_beta_PROMPT.md",
        ):
            (packet_dir / filename).write_text(filename, encoding="utf-8")

        return packet_dir

    def test_load_packet_set_reads_manifest_status_and_prompts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            packet_dir = self.make_packet_set(Path(temp_dir))
            packet_set = load_packet_set(packet_dir)

        self.assertEqual("demo_packets", packet_set.slug)
        self.assertEqual(["P00", "P01", "P02"], [packet.code for packet in packet_set.packets])
        self.assertEqual("PASS", packet_set.packet_by_code("P01").status)
        self.assertEqual(
            "codex/demo/p02-beta",
            packet_set.packet_by_code("P02").branch_label,
        )

    def test_select_next_ready_packet_uses_first_non_pass(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            packet_dir = self.make_packet_set(Path(temp_dir))
            packet_set = load_packet_set(packet_dir)

        packet = select_next_ready_packet(packet_set)
        self.assertIsNotNone(packet)
        assert packet is not None
        self.assertEqual("P02", packet.code)

    def test_select_specific_packet_requires_prior_pass_packets(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            packet_dir = self.make_packet_set(Path(temp_dir))
            status_path = packet_dir / "DEMO_STATUS.md"
            status_path.write_text(
                status_path.read_text(encoding="utf-8").replace(
                    "| P01 Alpha | `codex/demo/p01-alpha` | PASS |",
                    "| P01 Alpha | `codex/demo/p01-alpha` | PENDING |",
                ),
                encoding="utf-8",
            )
            packet_set = load_packet_set(packet_dir)

        with self.assertRaises(PacketRunnerError):
            select_next_ready_packet(packet_set, requested_code="P02")

    def test_discover_packet_set_dirs_accepts_packet_set_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            packet_dir = self.make_packet_set(Path(temp_dir))

            discovered = discover_packet_set_dirs(packet_dir)

        self.assertEqual([packet_dir.resolve()], discovered)

    def test_discover_packet_set_dirs_finds_packet_set_children(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            first_dir = self.make_packet_set(root, slug="first")
            second_dir = self.make_packet_set(root, slug="second")

            discovered = discover_packet_set_dirs(root)

        self.assertEqual([first_dir.resolve(), second_dir.resolve()], discovered)

    def test_safe_worktree_leaf_sanitizes_branch_names(self) -> None:
        self.assertEqual(
            "codex-graph-surface-input-p09-docs-traceability",
            safe_worktree_leaf("codex/graph-surface-input/p09-docs-traceability"),
        )

    def test_packet_set_relative_path_requires_repo_containment(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir, tempfile.TemporaryDirectory() as other_dir:
            repo_root = Path(temp_dir)
            packet_dir = self.make_packet_set(repo_root)

            self.assertEqual(
                packet_dir.relative_to(repo_root),
                packet_set_relative_path(repo_root, packet_dir),
            )

            with self.assertRaises(PacketThreadError):
                packet_set_relative_path(repo_root, Path(other_dir))


if __name__ == "__main__":
    unittest.main()

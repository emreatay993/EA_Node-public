#!/usr/bin/env python3
"""Run one packet in an isolated worktree and auto-wrap it into main."""

from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from devtools.work_packet_thread import main


if __name__ == "__main__":
    raise SystemExit(main())

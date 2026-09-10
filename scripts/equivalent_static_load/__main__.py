"""``python -m scripts.equivalent_static_load`` entry point."""

from __future__ import annotations

import sys

from scripts.equivalent_static_load.cli import main

if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

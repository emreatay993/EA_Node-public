from __future__ import annotations

import argparse
from typing import Sequence

try:
    from .gui import run_app
except ImportError:  # pragma: no cover - direct script execution fallback.
    from gui import run_app  # type: ignore


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="NASA-STD-5020B bolt separation calculator GUI.")
    parser.add_argument(
        "--version",
        action="store_true",
        help="Print a short version string and exit.",
    )
    args, remaining = parser.parse_known_args(argv)
    if args.version:
        print("NASA-STD-5020B bolt separation calculator")
        return 0
    return run_app(remaining)


if __name__ == "__main__":
    raise SystemExit(main())

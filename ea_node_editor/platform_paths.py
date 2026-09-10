from __future__ import annotations

from pathlib import Path


def default_user_desktop_path() -> str:
    """Return the user's Desktop directory, falling back to home if needed."""
    home = Path.home().expanduser()
    candidates = (home / "Desktop", home)
    for candidate in candidates:
        try:
            if candidate.exists() and candidate.is_dir():
                return str(candidate.resolve(strict=False))
        except OSError:
            continue
    try:
        return str(home.resolve(strict=False))
    except OSError:
        return str(home)


__all__ = ["default_user_desktop_path"]

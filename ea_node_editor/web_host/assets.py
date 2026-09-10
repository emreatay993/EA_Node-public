"""Package-resource resolvers for local web host assets."""

from __future__ import annotations

import atexit
from contextlib import ExitStack
from functools import lru_cache
from importlib import resources
from pathlib import Path, PurePosixPath

_PACKAGE_ROOT = "ea_node_editor"
_EXCALIDRAW_HOST_ROOT = ("web_assets", "excalidraw_host")

EXCALIDRAW_HOST_ENTRYPOINT = "index.html"

_RESOURCE_CONTEXTS = ExitStack()
atexit.register(_RESOURCE_CONTEXTS.close)


class WebHostAssetNotFoundError(FileNotFoundError):
    """Raised when a packaged web-host asset cannot be resolved."""


def resolve_excalidraw_host_index_path() -> Path:
    """Return a stable local path to the Excalidraw host entry point."""

    return resolve_excalidraw_host_asset_path(EXCALIDRAW_HOST_ENTRYPOINT)


def resolve_excalidraw_host_index_url() -> str:
    """Return a file URL for the Excalidraw host entry point."""

    return resolve_excalidraw_host_index_path().as_uri()


def resolve_excalidraw_host_asset_path(relative_path: str = EXCALIDRAW_HOST_ENTRYPOINT) -> Path:
    """Return a stable local path for an asset in the Excalidraw host bundle."""

    asset_path = _normalize_asset_path(relative_path)
    return _resolve_excalidraw_host_asset_path(asset_path.as_posix())


def resolve_excalidraw_host_asset_url(relative_path: str = EXCALIDRAW_HOST_ENTRYPOINT) -> str:
    """Return a file URL for an asset in the Excalidraw host bundle."""

    return resolve_excalidraw_host_asset_path(relative_path).as_uri()


@lru_cache(maxsize=None)
def _resolve_excalidraw_host_asset_path(relative_path: str) -> Path:
    resource = resources.files(_PACKAGE_ROOT)
    for path_part in (*_EXCALIDRAW_HOST_ROOT, *PurePosixPath(relative_path).parts):
        resource = resource.joinpath(path_part)

    if not resource.is_file():
        raise WebHostAssetNotFoundError(f"Missing Excalidraw host asset: {relative_path}")

    return _RESOURCE_CONTEXTS.enter_context(resources.as_file(resource)).resolve()


def _normalize_asset_path(relative_path: str) -> PurePosixPath:
    normalized = PurePosixPath(str(relative_path).replace("\\", "/"))
    if str(normalized) in {"", "."}:
        raise ValueError("Excalidraw host asset path must not be empty.")
    if normalized.is_absolute() or any(part in {".."} or ":" in part for part in normalized.parts):
        raise ValueError(f"Excalidraw host asset path must be relative: {relative_path!r}")
    return normalized

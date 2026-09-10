"""Helpers for COREX-owned local web host surfaces."""

from __future__ import annotations

from .assets import (
    EXCALIDRAW_HOST_ENTRYPOINT,
    WebHostAssetNotFoundError,
    resolve_excalidraw_host_asset_path,
    resolve_excalidraw_host_asset_url,
    resolve_excalidraw_host_index_path,
    resolve_excalidraw_host_index_url,
)
from .navigation_policy import (
    WebNavigationDecision,
    decide_web_navigation,
    normalize_web_page_browser_state,
    normalize_web_location,
)
from .webengine import WebEngineAvailability, check_webengine_available, is_webengine_available

__all__ = [
    "EXCALIDRAW_HOST_ENTRYPOINT",
    "WebEngineAvailability",
    "WebHostAssetNotFoundError",
    "WebNavigationDecision",
    "check_webengine_available",
    "decide_web_navigation",
    "is_webengine_available",
    "normalize_web_page_browser_state",
    "normalize_web_location",
    "resolve_excalidraw_host_asset_path",
    "resolve_excalidraw_host_asset_url",
    "resolve_excalidraw_host_index_path",
    "resolve_excalidraw_host_index_url",
]

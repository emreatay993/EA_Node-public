"""Navigation normalization helpers for generic WebEngine-backed pages."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import math
import os
from pathlib import Path
import re
from typing import Any
from urllib.parse import SplitResult, quote, unquote, urlsplit, urlunsplit

_ALLOWED_SCHEMES = {"file", "http", "https"}
_DEFAULT_REMOTE_SCHEME = "https"
_HOST_PORT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.-]*:\d+(?:[/#?].*)?$")
_SCHEME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")
_WINDOWS_DRIVE_RE = re.compile(r"^[A-Za-z]:[\\/]")
_WINDOWS_FILE_URL_PATH_RE = re.compile(r"^/[A-Za-z]:/")
_PROJECT_ARTIFACT_REF_RE = re.compile(r"^(?:saved|temp)://[A-Za-z0-9][A-Za-z0-9._-]*$")


@dataclass(frozen=True)
class _NavigationTarget:
    url: str
    scheme: str
    origin: str
    is_local: bool


@dataclass(frozen=True)
class WebNavigationDecision:
    """A deterministic decision for one requested web navigation."""

    allowed: bool
    target_url: str = ""
    reason: str = ""
    original_location: str = ""
    scheme: str = ""
    origin: str = ""
    is_local: bool = False
    qwebchannel_allowed: bool = False

    def as_payload(self) -> dict[str, bool | str]:
        """Return a UI-safe payload without importing Qt WebEngine."""

        return {
            "allowed": bool(self.allowed),
            "target_url": self.target_url,
            "reason": self.reason,
            "original_location": self.original_location,
            "scheme": self.scheme,
            "origin": self.origin,
            "is_local": bool(self.is_local),
            "qwebchannel_allowed": bool(self.qwebchannel_allowed),
        }


def normalize_web_location(location: str | os.PathLike[str]) -> str:
    """Normalize a user-entered file, HTTP, or HTTPS location to a load URL."""

    return _normalize_target(location).url


def normalize_web_page_browser_state(
    state: Mapping[str, Any] | None,
    *,
    fallback_location: str | os.PathLike[str] | None = None,
    require_location: bool = False,
) -> dict[str, Any]:
    """Return the project-safe browser state subset for generic web pages."""

    source = state if isinstance(state, Mapping) else {}
    normalized: dict[str, Any] = {}
    current_location = str(
        source.get("current_url")
        or source.get("current_location")
        or source.get("url")
        or fallback_location
        or ""
    ).strip()
    if current_location:
        if is_project_artifact_location(current_location):
            normalized["current_url"] = current_location
        else:
            decision = decide_web_navigation(current_location)
            if decision.allowed and decision.target_url.strip():
                normalized["current_url"] = decision.target_url.strip()

    zoom_factor = _normalized_web_page_zoom(
        source.get("zoom_factor") if "zoom_factor" in source else source.get("zoom")
    )
    if zoom_factor is not None:
        normalized["zoom_factor"] = zoom_factor

    page_title = _normalized_web_page_title(source.get("page_title"))
    if page_title is not None:
        normalized["page_title"] = page_title

    if require_location and "current_url" not in normalized:
        return {}
    return normalized


def is_project_artifact_location(location: str | os.PathLike[str]) -> bool:
    """Return whether a web-page location is a project-managed file reference."""

    return bool(_PROJECT_ARTIFACT_REF_RE.match(os.fspath(location).strip()))


def _normalized_web_page_zoom(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number) or number <= 0.0:
        return None
    return max(0.25, min(3.0, number))


def _normalized_web_page_title(value: Any) -> str | None:
    if value is None or isinstance(value, bool):
        return None
    text = " ".join(str(value).split())
    if not text:
        return None
    return text[:256]


def decide_web_navigation(location: str | os.PathLike[str]) -> WebNavigationDecision:
    """Normalize a requested location and decide whether it may load.

    A target is allowed when it normalizes to a safe ``file``, ``http``, or
    ``https`` URL. Generic pages never receive a privileged page bridge, so
    ``qwebchannel_allowed`` is always ``False``.
    """

    original_location = os.fspath(location)
    try:
        target = _normalize_target(location)
    except ValueError as exc:
        return WebNavigationDecision(
            allowed=False,
            original_location=original_location,
            reason=str(exc),
        )

    return WebNavigationDecision(
        allowed=True,
        target_url=target.url,
        original_location=original_location,
        scheme=target.scheme,
        origin=target.origin,
        is_local=target.is_local,
        qwebchannel_allowed=False,
    )


def _normalize_target(location: str | os.PathLike[str]) -> _NavigationTarget:
    text = os.fspath(location).strip()
    if not text:
        raise ValueError("Web navigation location must not be empty.")

    if isinstance(location, os.PathLike) or _looks_like_local_path(text):
        return _target_from_file_path(text)

    if "://" in text:
        return _target_from_url(text)

    if _HOST_PORT_RE.match(text):
        return _target_from_url(f"{_DEFAULT_REMOTE_SCHEME}://{text}")

    if _SCHEME_RE.match(text):
        scheme = text.split(":", 1)[0].lower()
        raise ValueError(f"Unsupported web navigation scheme: {scheme}")

    if any(character.isspace() for character in text):
        raise ValueError("Web navigation location must be a URL or filesystem path.")

    return _target_from_url(f"{_DEFAULT_REMOTE_SCHEME}://{text}")


def _target_from_file_path(path_text: str) -> _NavigationTarget:
    path = Path(path_text).expanduser().resolve(strict=False)
    return _NavigationTarget(
        url=path.as_uri(),
        scheme="file",
        origin="file://",
        is_local=True,
    )


def _target_from_url(url_text: str) -> _NavigationTarget:
    split = urlsplit(url_text)
    scheme = split.scheme.lower()
    if scheme not in _ALLOWED_SCHEMES:
        raise ValueError(f"Unsupported web navigation scheme: {scheme or '<missing>'}")
    if split.username or split.password:
        raise ValueError("Web navigation URLs must not include embedded credentials.")

    if scheme == "file":
        return _target_from_file_url(split)

    if not split.netloc or not split.hostname:
        raise ValueError(f"{scheme.upper()} navigation requires a host.")

    try:
        port = split.port
    except ValueError as exc:
        raise ValueError(f"{scheme.upper()} navigation has an invalid port.") from exc

    hostname = split.hostname.lower()
    netloc = hostname if port is None else f"{hostname}:{port}"
    normalized = urlunsplit(
        (
            scheme,
            netloc,
            _quote_path(unquote(split.path)),
            split.query,
            split.fragment,
        )
    )
    return _NavigationTarget(
        url=normalized,
        scheme=scheme,
        origin=f"{scheme}://{netloc}",
        is_local=False,
    )


def _target_from_file_url(split: SplitResult) -> _NavigationTarget:
    if split.netloc and split.netloc.lower() != "localhost":
        path = _quote_path(unquote(split.path))
        return _NavigationTarget(
            url=urlunsplit(("file", split.netloc.lower(), path, "", "")),
            scheme="file",
            origin="file://",
            is_local=True,
        )

    path_text = unquote(split.path)
    if os.name == "nt" and _WINDOWS_FILE_URL_PATH_RE.match(path_text):
        path_text = path_text[1:]
    return _target_from_file_path(path_text)


def _quote_path(path: str) -> str:
    return quote(path, safe="/:@!$&'()*+,;=")


def _looks_like_local_path(text: str) -> bool:
    if _WINDOWS_DRIVE_RE.match(text) or text.startswith(("~", ".", "/", "\\")):
        return True
    if "\\" in text or _looks_like_unc_path(text):
        return True
    try:
        return Path(text).expanduser().exists()
    except OSError:
        return False


def _looks_like_unc_path(text: str) -> bool:
    return text.startswith("\\\\") or text.startswith("//")

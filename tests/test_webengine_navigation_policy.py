from __future__ import annotations

import re
from pathlib import Path

import pytest

from ea_node_editor.web_host import decide_web_navigation, normalize_web_location

WEB_PAGE_VIEWER_FIXTURE_INDEX = (
    Path(__file__).resolve().parent / "fixtures" / "web_page_viewer" / "index.html"
)
_RELATIVE_ASSET_RE = re.compile(r"""(?:src|href)=["']\./([^"']+)["']""")


def test_filesystem_paths_and_file_urls_are_normalized_and_allowed(tmp_path: Path) -> None:
    html_path = tmp_path / "local page.html"
    html_path.write_text("<html></html>", encoding="utf-8")

    path_decision = decide_web_navigation(str(html_path))
    file_url_decision = decide_web_navigation(html_path.as_uri())

    assert path_decision.allowed is True
    assert path_decision.target_url == html_path.resolve().as_uri()
    assert path_decision.scheme == "file"
    assert path_decision.origin == "file://"
    assert path_decision.is_local is True
    assert path_decision.qwebchannel_allowed is False
    assert file_url_decision.allowed is True
    assert file_url_decision.target_url == html_path.resolve().as_uri()
    assert file_url_decision.scheme == "file"
    assert file_url_decision.origin == "file://"
    assert file_url_decision.is_local is True
    assert file_url_decision.qwebchannel_allowed is False
    assert normalize_web_location(html_path) == html_path.resolve().as_uri()


def test_local_html_fixture_and_relative_assets_are_allowed() -> None:
    html_text = WEB_PAGE_VIEWER_FIXTURE_INDEX.read_text(encoding="utf-8")
    asset_names = _RELATIVE_ASSET_RE.findall(html_text)

    assert asset_names == [
        "assets/style.css",
        "assets/local-pixel.svg",
        "assets/viewer-fixture.js",
    ]

    path_decision = decide_web_navigation(WEB_PAGE_VIEWER_FIXTURE_INDEX)
    file_url_decision = decide_web_navigation(WEB_PAGE_VIEWER_FIXTURE_INDEX.as_uri())

    assert path_decision.allowed is True
    assert path_decision.target_url == WEB_PAGE_VIEWER_FIXTURE_INDEX.resolve().as_uri()
    assert path_decision.origin == "file://"
    assert path_decision.is_local is True
    assert file_url_decision.allowed is True
    assert file_url_decision.target_url == WEB_PAGE_VIEWER_FIXTURE_INDEX.resolve().as_uri()

    for asset_name in asset_names:
        asset_path = WEB_PAGE_VIEWER_FIXTURE_INDEX.parent / asset_name
        asset_decision = decide_web_navigation(asset_path)
        assert asset_path.is_file(), asset_path
        assert asset_decision.allowed is True
        assert asset_decision.origin == "file://"
        assert asset_decision.is_local is True


@pytest.mark.skipif(
    not str(WEB_PAGE_VIEWER_FIXTURE_INDEX.drive),
    reason="Windows drive path proof needs a drive root",
)
def test_windows_style_local_fixture_paths_are_normalized() -> None:
    windows_path_text = str(WEB_PAGE_VIEWER_FIXTURE_INDEX).replace("/", "\\")

    decision = decide_web_navigation(windows_path_text)

    assert decision.allowed is True
    assert decision.target_url == WEB_PAGE_VIEWER_FIXTURE_INDEX.resolve().as_uri()
    assert decision.scheme == "file"
    assert decision.origin == "file://"
    assert decision.is_local is True


@pytest.mark.parametrize(
    ("raw_location", "expected_url", "expected_origin"),
    (
        (
            "https://tenant.sharepoint.com/sites/corex",
            "https://tenant.sharepoint.com/sites/corex",
            "https://tenant.sharepoint.com",
        ),
        ("http://intranet.local/wiki", "http://intranet.local/wiki", "http://intranet.local"),
        ("intranet/sites/wiki", "https://intranet/sites/wiki", "https://intranet"),
        ("portal:8443/app", "https://portal:8443/app", "https://portal:8443"),
        ("example.com", "https://example.com", "https://example.com"),
    ),
)
def test_http_https_and_bare_host_locations_are_normalized(
    raw_location: str,
    expected_url: str,
    expected_origin: str,
) -> None:
    decision = decide_web_navigation(raw_location)

    assert decision.allowed is True
    assert decision.target_url == expected_url
    assert decision.origin == expected_origin
    assert decision.is_local is False
    assert decision.qwebchannel_allowed is False


@pytest.mark.parametrize(
    "raw_location",
    (
        "javascript:alert(1)",
        "data:text/html,<h1>Unsafe</h1>",
        "shell:AppsFolder",
        "ftp://example.test/file.txt",
        "cmd.exe /c calc.exe",
        "https://user:secret@example.test/",
    ),
)
def test_unsafe_and_unsupported_navigation_targets_are_denied(raw_location: str) -> None:
    decision = decide_web_navigation(raw_location)

    assert decision.allowed is False
    assert decision.target_url == ""
    assert decision.qwebchannel_allowed is False
    assert decision.reason


def test_empty_location_is_denied_with_reason() -> None:
    decision = decide_web_navigation("   ")

    assert decision.allowed is False
    assert decision.target_url == ""
    assert "must not be empty" in decision.reason


def test_navigation_decision_payload_is_ui_safe() -> None:
    decision = decide_web_navigation("https://example.test/docs")

    assert decision.as_payload() == {
        "allowed": True,
        "target_url": "https://example.test/docs",
        "reason": "",
        "original_location": "https://example.test/docs",
        "scheme": "https",
        "origin": "https://example.test",
        "is_local": False,
        "qwebchannel_allowed": False,
    }

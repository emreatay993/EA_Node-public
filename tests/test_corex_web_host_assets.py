from __future__ import annotations

import fnmatch
from importlib import resources
from pathlib import Path
import re

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10 project venv
    import tomli as tomllib

import pytest

from ea_node_editor.web_host import webengine
from ea_node_editor.web_host.assets import (
    EXCALIDRAW_HOST_ENTRYPOINT,
    WebHostAssetNotFoundError,
    resolve_excalidraw_host_asset_path,
    resolve_excalidraw_host_asset_url,
    resolve_excalidraw_host_index_path,
    resolve_excalidraw_host_index_url,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PYPROJECT_PATH = PROJECT_ROOT / "pyproject.toml"
WEBENGINE_REQUIREMENT = "PyQt6-WebEngine>=6.10"
WEB_ASSET_PACKAGE_DATA_GLOBS = {
    "web_assets/**/*.html",
    "web_assets/**/*.css",
    "web_assets/**/*.js",
    "web_assets/**/*.mjs",
    "web_assets/**/*.cjs",
    "web_assets/**/*.chunk.js",
    "web_assets/**/*.chunk.css",
    "web_assets/**/*.json",
    "web_assets/**/*.webmanifest",
    "web_assets/**/asset-manifest.*",
    "web_assets/**/*.wasm",
    "web_assets/**/*.svg",
    "web_assets/**/*.png",
    "web_assets/**/*.jpg",
    "web_assets/**/*.jpeg",
    "web_assets/**/*.gif",
    "web_assets/**/*.webp",
    "web_assets/**/*.ico",
    "web_assets/**/*.woff",
    "web_assets/**/*.woff2",
    "web_assets/**/*.ttf",
    "web_assets/**/*.otf",
    "web_assets/**/*.eot",
    "web_assets/excalidraw_host/*",
    "web_assets/excalidraw_host/**/*",
}
TEXT_WEB_ASSET_SUFFIXES = {
    ".cjs",
    ".css",
    ".html",
    ".js",
    ".json",
    ".mjs",
    ".svg",
    ".webmanifest",
}
EXCALIDRAW_RUNTIME_FONT_ASSETS = (
    Path("fonts/Virgil/Virgil-Regular.woff2"),
    Path("fonts/Cascadia/CascadiaCode-Regular.woff2"),
)
WEB_PAGE_VIEWER_FIXTURE_ROOT = PROJECT_ROOT / "tests" / "fixtures" / "web_page_viewer"
WEB_PAGE_VIEWER_FIXTURE_ASSETS = {
    "assets/style.css",
    "assets/local-pixel.svg",
    "assets/viewer-fixture.js",
}


def test_webengine_dependency_metadata_includes_runtime_web_support() -> None:
    pyproject = tomllib.loads(PYPROJECT_PATH.read_text(encoding="utf-8"))
    dependencies = pyproject["project"]["dependencies"]
    optional_dependencies = pyproject["project"]["optional-dependencies"]

    assert WEBENGINE_REQUIREMENT in dependencies
    assert "web" not in optional_dependencies
    assert WEBENGINE_REQUIREMENT not in optional_dependencies["all"]
    assert WEBENGINE_REQUIREMENT not in optional_dependencies["dev"]


def test_webengine_availability_reports_missing_dependency_without_raising(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_import_module(module_name: str) -> object:
        raise ModuleNotFoundError(f"No module named {module_name!r}")

    monkeypatch.delenv("QT_QPA_PLATFORM", raising=False)
    monkeypatch.setattr(webengine.importlib, "import_module", fake_import_module)

    availability = webengine.check_webengine_available()

    assert not availability
    assert availability.available is False
    assert availability.module_name == "PyQt6.QtWebEngineCore"
    assert availability.exception_type == "ModuleNotFoundError"
    assert "PyQt6.QtWebEngineCore" in availability.reason
    assert availability.as_payload() == {
        "webengine_available": False,
        "webengine_reason": availability.reason,
        "webengine_module_name": "PyQt6.QtWebEngineCore",
        "webengine_exception_type": "ModuleNotFoundError",
    }


def test_webengine_availability_requires_qml_quick_module(monkeypatch: pytest.MonkeyPatch) -> None:
    imported_modules: list[str] = []

    def fake_import_module(module_name: str) -> object:
        imported_modules.append(module_name)
        if module_name == "PyQt6.QtWebEngineQuick":
            raise ModuleNotFoundError(f"No module named {module_name!r}")
        return object()

    monkeypatch.delenv("QT_QPA_PLATFORM", raising=False)
    monkeypatch.setattr(webengine.importlib, "import_module", fake_import_module)

    availability = webengine.check_webengine_available()

    assert not availability
    assert availability.module_name == "PyQt6.QtWebEngineQuick"
    assert availability.exception_type == "ModuleNotFoundError"
    assert imported_modules == ["PyQt6.QtWebEngineCore", "PyQt6.QtWebEngineQuick"]


def test_webengine_availability_disables_real_webengine_under_offscreen_qt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    imported_modules: list[str] = []

    def fake_import_module(module_name: str) -> object:
        imported_modules.append(module_name)
        return object()

    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.delenv("COREX_ENABLE_OFFSCREEN_WEBENGINE", raising=False)
    monkeypatch.setattr(webengine.importlib, "import_module", fake_import_module)

    availability = webengine.check_webengine_available()

    assert not availability
    assert availability.module_name == "QtWebEngine"
    assert availability.exception_type == "RuntimeError"
    assert "offscreen" in availability.reason
    assert imported_modules == []


def _excalidraw_host_asset_root() -> Path:
    return PROJECT_ROOT / "ea_node_editor" / "web_assets" / "excalidraw_host"


def _linked_asset_names(html_text: str, *, extension: str) -> list[str]:
    pattern = rf"""(?:src|href)=["']\./([^"']+{re.escape(extension)})["']"""
    return re.findall(pattern, html_text)


def test_asset_resolver_returns_local_excalidraw_host_entrypoint_and_generated_bundle() -> None:
    expected_root = PROJECT_ROOT / "ea_node_editor" / "web_assets" / "excalidraw_host"

    index_path = resolve_excalidraw_host_index_path()

    assert index_path == expected_root / EXCALIDRAW_HOST_ENTRYPOINT
    assert index_path.is_file()
    assert resolve_excalidraw_host_index_url() == index_path.as_uri()

    html_text = index_path.read_text(encoding="utf-8")
    script_names = _linked_asset_names(html_text, extension=".js")
    stylesheet_names = _linked_asset_names(html_text, extension=".css")
    entry_script_names = [name for name in script_names if name != "excalidraw-assets.js"]

    assert "COREX Excalidraw Editor" in html_text
    assert "Excalidraw host placeholder" not in html_text
    assert "connect-src 'none'" in html_text
    assert 'src="./qwebchannel.js"' in html_text
    assert script_names
    assert "qwebchannel.js" in script_names
    assert "excalidraw-assets.js" in script_names
    entry_script_names = [name for name in entry_script_names if name != "qwebchannel.js"]
    assert entry_script_names
    assert stylesheet_names
    assert html_text.index("qwebchannel.js") < html_text.index(entry_script_names[0])
    assert html_text.index("excalidraw-assets.js") < html_text.index(entry_script_names[0])

    asset_setup_path = resolve_excalidraw_host_asset_path("excalidraw-assets.js")
    qwebchannel_script_path = resolve_excalidraw_host_asset_path("qwebchannel.js")
    entry_script_path = resolve_excalidraw_host_asset_path(entry_script_names[0])
    stylesheet_path = resolve_excalidraw_host_asset_path(stylesheet_names[0])
    assert asset_setup_path.is_file()
    assert qwebchannel_script_path.is_file()
    assert entry_script_path.is_file()
    assert stylesheet_path.is_file()
    assert resolve_excalidraw_host_asset_url(entry_script_names[0]) == entry_script_path.as_uri()

    asset_setup_text = asset_setup_path.read_text(encoding="utf-8")
    script_text = entry_script_path.read_text(encoding="utf-8")
    assert "EXCALIDRAW_ASSET_PATH" in asset_setup_text
    assert "webSurfaceBridge" in script_text
    assert "load_state" in script_text
    assert "save_scene" in script_text
    assert "asset_request" in script_text
    assert "commit_snapshot" in script_text
    assert "corexExcalidrawHost" in script_text
    assert "gridModeEnabled" in script_text
    assert "scrollToContent" in script_text
    assert "Preview export timed out" in script_text
    assert "fallback_reason" not in script_text
    qwebchannel_script_text = qwebchannel_script_path.read_text(encoding="utf-8")
    assert "var QWebChannel" in qwebchannel_script_text
    assert "qwebchannel.js" in script_text

    host_source_text = (PROJECT_ROOT / "web" / "excalidraw_host" / "src" / "main.tsx").read_text(encoding="utf-8")
    assert "WEBCHANNEL_BRIDGE_TIMEOUT_MS" in host_source_text
    assert "BRIDGE_CALL_TIMEOUT_MS" in host_source_text
    assert "bridgeFromChannel(channel)" in host_source_text


def test_excalidraw_host_text_assets_are_local_only() -> None:
    asset_root = _excalidraw_host_asset_root()
    text_assets = [
        path
        for path in asset_root.rglob("*")
        if path.is_file() and path.suffix.lower() in TEXT_WEB_ASSET_SUFFIXES
    ]

    assert text_assets
    for path in text_assets:
        text = path.read_text(encoding="utf-8")
        assert "http://" not in text, path
        assert "https://" not in text, path


def test_web_page_viewer_fixture_uses_relative_local_assets_only() -> None:
    index_path = WEB_PAGE_VIEWER_FIXTURE_ROOT / "index.html"
    html_text = index_path.read_text(encoding="utf-8")
    asset_names = set(_linked_asset_names(html_text, extension=".css"))
    asset_names.update(_linked_asset_names(html_text, extension=".js"))
    asset_names.update(_linked_asset_names(html_text, extension=".svg"))

    assert asset_names == WEB_PAGE_VIEWER_FIXTURE_ASSETS
    assert "http://" not in html_text
    assert "https://" not in html_text
    for asset_name in WEB_PAGE_VIEWER_FIXTURE_ASSETS:
        asset_path = WEB_PAGE_VIEWER_FIXTURE_ROOT / asset_name
        assert asset_path.is_file(), asset_path
        if asset_path.suffix in {".css", ".html", ".js"}:
            text = asset_path.read_text(encoding="utf-8")
            assert "http://" not in text, asset_path
            assert "https://" not in text, asset_path


def test_excalidraw_host_runtime_fonts_are_packaged_for_local_loading() -> None:
    asset_root = _excalidraw_host_asset_root()

    for font_asset in EXCALIDRAW_RUNTIME_FONT_ASSETS:
        assert (asset_root / font_asset).is_file()

    excalifont_assets = list((asset_root / "fonts" / "Excalifont").glob("Excalifont-Regular-*.woff2"))
    assert excalifont_assets

    entry_script_text = next(asset_root.glob("index-*.js")).read_text(encoding="utf-8")
    for font_asset in EXCALIDRAW_RUNTIME_FONT_ASSETS:
        assert f"./{font_asset.as_posix()}" in entry_script_text


def test_excalidraw_host_sanitizes_runtime_app_state_before_reopening() -> None:
    host_source_text = (PROJECT_ROOT / "web" / "excalidraw_host" / "src" / "main.tsx").read_text(encoding="utf-8")
    allowlist_start = host_source_text.index("const DOCUMENT_APP_STATE_KEYS")
    allowlist_end = host_source_text.index("] as const;", allowlist_start)
    allowlist_block = host_source_text[allowlist_start:allowlist_end]

    assert "serializeAsJSON" in host_source_text
    assert "documentSceneState(coerceSceneState(value))" in host_source_text
    for key in ("gridModeEnabled", "gridSize", "gridStep", "viewBackgroundColor"):
        assert key in allowlist_block
    for runtime_key in (
        "collaborators",
        "showWelcomeScreen",
        "scrollX",
        "scrollY",
        "width",
        "height",
        "offsetLeft",
        "offsetTop",
    ):
        assert runtime_key not in allowlist_block


def test_excalidraw_host_frames_initial_content_after_webengine_mount() -> None:
    host_source_text = (PROJECT_ROOT / "web" / "excalidraw_host" / "src" / "main.tsx").read_text(encoding="utf-8")

    assert "INITIAL_CONTENT_FRAME_ATTEMPTS" in host_source_text
    assert "scheduleInitialContentFrame(api)" in host_source_text
    assert "api.refresh?.()" in host_source_text
    assert "api.scrollToContent?.(undefined, { animate: false })" in host_source_text


def test_excalidraw_host_uses_only_bounded_library_snapshot_exports() -> None:
    host_source_text = (PROJECT_ROOT / "web" / "excalidraw_host" / "src" / "main.tsx").read_text(encoding="utf-8")

    assert "maxWidthOrHeight: PREVIEW_MAX_EDGE" in host_source_text
    assert "const PREVIEW_MAX_EDGE = 2048" in host_source_text
    assert "createCanvasPreviewPayload" not in host_source_text
    assert "fallback_reason" not in host_source_text
    assert "SnapshotController" in host_source_text


def test_packaged_web_asset_globs_cover_current_excalidraw_host_bundle() -> None:
    pyproject = tomllib.loads(PYPROJECT_PATH.read_text(encoding="utf-8"))
    package_data = set(pyproject["tool"]["setuptools"]["package-data"]["ea_node_editor"])
    web_asset_globs = package_data.intersection(WEB_ASSET_PACKAGE_DATA_GLOBS)
    asset_root = PROJECT_ROOT / "ea_node_editor" / "web_assets"
    asset_paths = [path.relative_to(PROJECT_ROOT / "ea_node_editor").as_posix() for path in asset_root.rglob("*") if path.is_file()]

    assert web_asset_globs == WEB_ASSET_PACKAGE_DATA_GLOBS
    assert asset_paths
    for asset_path in asset_paths:
        assert any(fnmatch.fnmatchcase(asset_path, pattern) for pattern in web_asset_globs), asset_path


def test_excalidraw_host_assets_are_importlib_resource_visible_for_frozen_resolution() -> None:
    resource_root = resources.files("ea_node_editor").joinpath("web_assets", "excalidraw_host")
    resource_names = {
        resource.name
        for resource in resource_root.iterdir()
        if resource.is_file()
    }

    assert resource_root.joinpath("index.html").is_file()
    assert any(name.endswith(".js") for name in resource_names)
    assert any(name.endswith(".css") for name in resource_names)
    assert any(name.endswith(".woff2") for name in resource_names)
    assert (
        resource_root.joinpath("fonts").joinpath("Virgil").joinpath("Virgil-Regular.woff2").is_file()
    )
    assert any(
        resource.name.startswith("Excalifont-Regular-") and resource.name.endswith(".woff2")
        for resource in resource_root.joinpath("fonts").joinpath("Excalifont").iterdir()
        if resource.is_file()
    )


def test_asset_resolver_raises_for_missing_excalidraw_host_asset() -> None:
    with pytest.raises(WebHostAssetNotFoundError, match="missing.js"):
        resolve_excalidraw_host_asset_path("missing.js")

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys

import pytest
from PyQt6.QtCore import QUrl
from PyQt6.QtQml import QQmlComponent, QQmlEngine

from ea_node_editor.mockups.status_bar.__main__ import GALLERY_QML_PATH, MOCKUP_ROOT
from ea_node_editor.ui.icon_registry import (
    UI_ICON_PROVIDER_ID,
    UiIconImageProvider,
    UiIconRegistryBridge,
)


pytestmark = pytest.mark.gui

REPO_ROOT = Path(__file__).resolve().parents[1]
VARIANT_PATHS = [
    MOCKUP_ROOT / "variants" / f"StatusBarVariant0{variant_id}.qml"
    for variant_id in range(1, 6)
]


def _new_engine() -> QQmlEngine:
    engine = QQmlEngine()
    engine.addImageProvider(UI_ICON_PROVIDER_ID, UiIconImageProvider())
    engine.rootContext().setContextProperty("uiIcons", UiIconRegistryBridge())
    return engine


def _component_errors(component: QQmlComponent) -> list[str]:
    return [error.toString() for error in component.errors()]


def _create_component(engine: QQmlEngine, qml_path: Path, properties: dict[str, object]) -> object:
    component = QQmlComponent(engine, QUrl.fromLocalFile(str(qml_path)))
    assert component.status() == QQmlComponent.Status.Ready, _component_errors(component)
    if hasattr(component, "createWithInitialProperties"):
        item = component.createWithInitialProperties(properties)
    else:
        item = component.create()
        for key, value in properties.items():
            item.setProperty(key, value)
    assert item is not None, _component_errors(component)
    item.setWidth(960)
    item.setHeight(300)
    return item


def test_status_bar_gallery_and_variants_compile(qapp) -> None:  # noqa: ANN001
    engine = _new_engine()
    context = engine.rootContext()
    context.setContextProperty("mockupVariantFilter", "1")
    context.setContextProperty("mockupThemeFilter", "dark")
    context.setContextProperty("mockupScreenshotMode", False)

    created_items = [
        _create_component(engine, GALLERY_QML_PATH, {}),
    ]
    # Variants instantiate without a telemetry model (null-guarded) so a QML
    # binding error would surface here as a failed create / component error.
    for qml_path in VARIANT_PATHS:
        for theme_name in ("dark", "light"):
            created_items.append(
                _create_component(
                    engine,
                    qml_path,
                    {"themeName": theme_name},
                )
            )
            qapp.processEvents()

    for item in created_items:
        item.deleteLater()
    engine.deleteLater()
    qapp.processEvents()


def test_status_bar_runner_smoke() -> None:
    env = os.environ.copy()
    env["QT_QPA_PLATFORM"] = "offscreen"
    env.setdefault("QT_QUICK_CONTROLS_STYLE", "Basic")

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "ea_node_editor.mockups.status_bar",
            "--quit-after-ms",
            "500",
        ],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        timeout=20,
        check=False,
    )

    assert result.returncode == 0, result.stderr


def test_status_bar_runner_writes_theme_variant_screenshots(tmp_path: Path) -> None:
    env = os.environ.copy()
    env["QT_QPA_PLATFORM"] = "offscreen"
    env.setdefault("QT_QUICK_CONTROLS_STYLE", "Basic")
    screenshot_dir = tmp_path / "status_bar"

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "ea_node_editor.mockups.status_bar",
            "--screenshot-dir",
            str(screenshot_dir),
        ],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        timeout=90,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    screenshots = sorted(screenshot_dir.glob("status_bar_variant_*.png"))
    assert len(screenshots) == 10
    assert {path.stem.rsplit("_", 1)[-1] for path in screenshots} == {"dark", "light"}
    assert all(path.stat().st_size > 0 for path in screenshots)

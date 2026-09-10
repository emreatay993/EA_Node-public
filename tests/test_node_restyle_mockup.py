from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
GALLERY_QML = REPO_ROOT / "ea_node_editor" / "mockups" / "node_restyle" / "NodeRestyleGallery.qml"


def _mockup_env() -> dict[str, str]:
    env = os.environ.copy()
    env["QT_QPA_PLATFORM"] = "offscreen"
    env.setdefault("QT_QUICK_CONTROLS_STYLE", "Basic")
    return env


def test_node_restyle_runner_smoke() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "ea_node_editor.mockups.node_restyle",
            "--quit-after-ms",
            "500",
        ],
        cwd=REPO_ROOT,
        env=_mockup_env(),
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
    )

    assert result.returncode == 0, result.stderr


def test_node_restyle_gallery_covers_fixed_semantic_states() -> None:
    gallery_text = GALLERY_QML.read_text(encoding="utf-8")

    assert "Graph.GraphNodeHostTheme" in gallery_text
    assert 'text: "Fixed active-node semantic colors"' in gallery_text
    for state in ("default", "running", "warning", "error", "disabled"):
        assert f'{{ state: "{state}"' in gallery_text
    assert 'text: semanticStateRow.selectedRow ? "Selected" : "Unselected"' in gallery_text


def test_node_restyle_gallery_resolves_reserved_disabled_palette() -> None:
    probe = r'''
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QApplication
from ea_node_editor.mockups.node_restyle.__main__ import _create_view

app = QApplication([])
view = _create_view(theme="both", screenshot_mode=True)
view.show()
for _ in range(8):
    app.processEvents()
root = view.rootObject()

def find_item(item, object_name):
    if str(item.objectName()) == object_name:
        return item
    for child in item.childItems():
        match = find_item(child, object_name)
        if match is not None:
            return match
    return None

expected = {
    "semanticNodeCard_dark_disabled_unselected": ("disabled", "#404244", "#393b3d", "#5d6164", "#b3b7bc", "#9ea3a8"),
    "semanticNodeCard_dark_disabled_selected": ("selected", "#1f5369", "#1a485b", "#00a5e4", "#b3b7bc", "#9ea3a8"),
    "semanticNodeCard_light_disabled_unselected": ("disabled", "#cdd0d1", "#cfd2d3", "#bdc3c7", "#9697a8", "#a2a4b2"),
    "semanticNodeCard_light_disabled_selected": ("selected", "#acdcf0", "#adddf1", "#009ee0", "#9697a8", "#a2a4b2"),
}
for object_name, values in expected.items():
    card = find_item(root, object_name)
    assert card is not None, object_name
    assert str(card.property("resolvedState")) == values[0]
    for property_name, expected_color in zip(
        ("resolvedStartColor", "resolvedEndColor", "resolvedOutlineColor", "resolvedTitleColor", "resolvedPortColor"),
        values[1:],
    ):
        assert QColor(card.property(property_name)).name().lower() == expected_color
'''
    result = subprocess.run(
        [sys.executable, "-c", probe],
        cwd=REPO_ROOT,
        env=_mockup_env(),
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
    )

    assert result.returncode == 0, result.stderr


def test_node_restyle_runner_writes_theme_screenshots(tmp_path: Path) -> None:
    screenshot_dir = tmp_path / "node_restyle"

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "ea_node_editor.mockups.node_restyle",
            "--screenshot-dir",
            str(screenshot_dir),
        ],
        cwd=REPO_ROOT,
        env=_mockup_env(),
        text=True,
        capture_output=True,
        timeout=90,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    screenshots = sorted(screenshot_dir.glob("node_restyle_*.png"))
    assert {path.stem.rsplit("_", 1)[-1] for path in screenshots} == {"dark", "light"}
    assert all(path.stat().st_size > 0 for path in screenshots)

from __future__ import annotations

import os
import unittest
from pathlib import Path

from PyQt6.QtQml import QJSEngine
from PyQt6.QtWidgets import QApplication


_REPO_ROOT = Path(__file__).resolve().parents[1]
_TOOLBAR_POSITIONING_PATH = (
    _REPO_ROOT
    / "ea_node_editor"
    / "ui_qml"
    / "components"
    / "graph"
    / "overlay"
    / "toolbar_positioning.js"
)
_TOOLBAR_QML_PATH = (
    _REPO_ROOT
    / "ea_node_editor"
    / "ui_qml"
    / "components"
    / "graph"
    / "overlay"
    / "GraphNodeFloatingToolbar.qml"
)
_POPOVER_HOST_QML_PATH = _TOOLBAR_QML_PATH.with_name(
    "GraphNodeToolbarPopoverHost.qml"
)


def _load_positioning_engine() -> QJSEngine:
    source = _TOOLBAR_POSITIONING_PATH.read_text(encoding="utf-8")
    # `.pragma library` is a QML script loader directive; strip it so the source
    # can be evaluated directly inside a QJSEngine context.
    stripped = "\n".join(
        line for line in source.splitlines() if not line.strip().startswith(".pragma")
    )
    engine = QJSEngine()
    result = engine.evaluate(stripped)
    if result.isError():
        raise RuntimeError(f"toolbar_positioning.js failed to load: {result.toString()}")
    return engine


def _js_literal(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return repr(float(value))
    if isinstance(value, dict):
        parts = [f"{key!r}: {_js_literal(sub)}" for key, sub in value.items()]
        return "({" + ", ".join(parts) + "})"
    raise TypeError(f"unsupported literal: {type(value)!r}")


def _invoke_compute_anchor(
    engine: QJSEngine,
    node_rect: dict[str, float],
    toolbar_size: dict[str, float],
    viewport_rect: dict[str, float],
    metrics: dict[str, float],
    previous_flipped: bool,
) -> dict[str, object]:
    expression = (
        "computeAnchor("
        f"{_js_literal(node_rect)},"
        f"{_js_literal(toolbar_size)},"
        f"{_js_literal(viewport_rect)},"
        f"{_js_literal(metrics)},"
        f"{_js_literal(previous_flipped)}"
        ")"
    )
    result = engine.evaluate(expression)
    if result.isError():
        raise RuntimeError(f"computeAnchor failed: {result.toString()}")
    return dict(result.toVariant())


class FloatingToolbarPositioningTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        cls._app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self._engine = _load_positioning_engine()
        self._viewport = {"x": 0.0, "y": 0.0, "width": 640.0, "height": 480.0}
        self._toolbar = {"width": 120.0, "height": 32.0}
        self._metrics = {
            "gap_from_node": 6.0,
            "safety_margin": 8.0,
            "hysteresis": 8.0,
        }

    def _compute(
        self,
        *,
        node: dict[str, float],
        previous_flipped: bool = False,
    ) -> dict[str, object]:
        return _invoke_compute_anchor(
            self._engine,
            node,
            self._toolbar,
            self._viewport,
            self._metrics,
            previous_flipped,
        )

    def test_anchor_sits_above_when_node_is_mid_canvas(self) -> None:
        node = {"x": 200.0, "y": 200.0, "width": 200.0, "height": 80.0}

        anchor = self._compute(node=node)

        # topY = 200 - 32 - 6 = 162; centerX = 300 - 60 = 240
        self.assertFalse(bool(anchor["flipped"]))
        self.assertAlmostEqual(float(anchor["y"]), 162.0, places=4)
        self.assertAlmostEqual(float(anchor["x"]), 240.0, places=4)

    def test_anchor_flips_below_when_node_is_near_viewport_top(self) -> None:
        node = {"x": 200.0, "y": 10.0, "width": 200.0, "height": 80.0}

        anchor = self._compute(node=node)

        # topY = -28, viewport_safety = 8 -> flip; bottomY = 10 + 80 + 6 = 96
        self.assertTrue(bool(anchor["flipped"]))
        self.assertAlmostEqual(float(anchor["y"]), 96.0, places=4)

    def test_anchor_tracks_node_past_left_viewport_edge(self) -> None:
        # The toolbar follows its owner off-screen instead of pinning to the
        # viewport's left edge, so it stays visually glued to the node.
        node = {"x": -100.0, "y": 200.0, "width": 200.0, "height": 80.0}

        anchor = self._compute(node=node)

        # centerX = -100 + 100 - 60 = -60
        self.assertAlmostEqual(float(anchor["x"]), -60.0, places=4)

    def test_anchor_tracks_node_past_right_viewport_edge(self) -> None:
        node = {"x": 600.0, "y": 200.0, "width": 200.0, "height": 80.0}

        anchor = self._compute(node=node)

        # centerX = 600 + 100 - 60 = 640 (no clamp; toolbar follows node off-screen)
        self.assertAlmostEqual(float(anchor["x"]), 640.0, places=4)

    def test_anchor_uses_hysteresis_to_prevent_flip_jitter(self) -> None:
        # node.y chosen so topY = 50 - 32 - 6 = 12, which sits between the
        # non-flipped threshold (minTop = 8) and the flipped-back threshold
        # (minTop + hysteresis = 16). A node parked in this gap must retain
        # whatever flip state it was already in.
        node = {"x": 200.0, "y": 50.0, "width": 200.0, "height": 80.0}

        from_unflipped = self._compute(node=node, previous_flipped=False)
        from_flipped = self._compute(node=node, previous_flipped=True)

        self.assertFalse(bool(from_unflipped["flipped"]))
        self.assertTrue(bool(from_flipped["flipped"]))

    def test_anchor_releases_flip_after_node_clears_hysteresis_band(self) -> None:
        # topY = 60 - 32 - 6 = 22 > minTop + hysteresis (16) -> flip releases
        node = {"x": 200.0, "y": 60.0, "width": 200.0, "height": 80.0}

        from_flipped = self._compute(node=node, previous_flipped=True)

        self.assertFalse(bool(from_flipped["flipped"]))
        # Anchors above the node at topY = 22
        self.assertAlmostEqual(float(from_flipped["y"]), 22.0, places=4)

    def test_action_popover_reposition_is_thresholded(self) -> None:
        qml = _POPOVER_HOST_QML_PATH.read_text(encoding="utf-8")

        self.assertIn("function _positionActionPopoverIfSizeMoved()", qml)
        self.assertIn(">= 0.5", qml)
        self.assertIn("onImplicitWidthChanged", qml)
        self.assertIn("onImplicitHeightChanged", qml)


if __name__ == "__main__":
    unittest.main()

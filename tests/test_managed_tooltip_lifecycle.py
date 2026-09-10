# Purpose: Guard ManagedToolTip's popup-window dismissal lifecycle.
# Map: docs/agent_maps/feature_routes/tooltips_and_tiers.md
# Tests: tests/test_managed_tooltip_lifecycle.py

"""Behavioral guards for `ManagedToolTip`'s dismissal lifecycle.

`ManagedToolTip` uses `popupType: Popup.Window`, so an open tooltip is a real
top-level OS window. Qt does not withdraw one when the host loses focus, is
minimized, or when a hover-exit event is never delivered, so the control has to
close itself. These tests cover the guards that are observable offscreen; the
`Qt.application.active` guard needs a foreign window taking the foreground and
is pinned by source contract in `tests/main_window_shell/bridge_qml_boundaries.py`.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "Basic")

from PyQt6.QtCore import QMetaObject, QUrl, QVariant, Q_RETURN_ARG
from PyQt6.QtQuickWidgets import QQuickWidget
from PyQt6.QtWidgets import QVBoxLayout, QWidget

pytestmark = pytest.mark.xdist_group("managed_tooltip_lifecycle")

_REPO_ROOT = Path(__file__).resolve().parents[1]
_COMMON_DIR = _REPO_ROOT / "ea_node_editor" / "ui_qml" / "components" / "common"

# `pane` stands in for the panning/zooming canvas content item: moving it slides
# the anchor out from under a stationary cursor, which is the one hover-exit case
# Qt never reports.
_PROBE_QML = """
import QtQuick 2.15
import "file:///__COMMON__" as Common

Rectangle {
    width: 400
    height: 200
    property bool hovering: false

    Item {
        id: pane
        width: parent.width
        height: parent.height

        Rectangle {
            id: anchorItem
            x: 40
            y: 40
            width: 120
            height: 24

            Common.ManagedToolTip {
                id: tip
                objectName: "lifecycleProbeToolTip"
                policyBridge: null
                category: "general"
                active: hovering
                text: "port help"
                delay: 0
                anchorWatchInterval: 25
            }
        }
    }

    function tipVisible() { return tip.visible }
    function anchorMoved() { return tip._anchorMoved }
    function panCanvas() { pane.x = -300 }
    function hideAnchor() { anchorItem.visible = false }
    function showAnchor() { anchorItem.visible = true }
}
"""


class _Probe:
    def __init__(self, app, root) -> None:  # noqa: ANN001
        self._app = app
        self._root = root

    def call(self, name: str):
        return QMetaObject.invokeMethod(self._root, name, Q_RETURN_ARG(QVariant))

    def set_hovering(self, hovering: bool) -> None:
        self._root.setProperty("hovering", hovering)
        self.pump()

    def pump(self, seconds: float = 0.05) -> None:
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            self._app.processEvents()
            time.sleep(0.005)

    def wait_for_visible(self, expected: bool, timeout: float = 3.0) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if bool(self.call("tipVisible")) == expected:
                return True
            self.pump(0.02)
        return bool(self.call("tipVisible")) == expected


@pytest.fixture()
def probe(qapp, tmp_path):  # noqa: ANN001
    source = tmp_path / "managed_tooltip_probe.qml"
    source.write_text(
        _PROBE_QML.replace("__COMMON__", _COMMON_DIR.as_posix()), encoding="utf-8"
    )

    host = QWidget()
    layout = QVBoxLayout(host)
    layout.setContentsMargins(0, 0, 0, 0)
    widget = QQuickWidget()
    widget.setResizeMode(QQuickWidget.ResizeMode.SizeRootObjectToView)
    layout.addWidget(widget)
    host.resize(420, 220)
    host.show()
    widget.setSource(QUrl.fromLocalFile(str(source)))

    errors = [error.toString() for error in widget.errors()]
    assert not errors, errors
    root = widget.rootObject()
    assert root is not None

    try:
        yield _Probe(qapp, root)
    finally:
        widget.setSource(QUrl())
        host.close()
        widget.deleteLater()
        host.deleteLater()
        qapp.processEvents()


def test_tooltip_opens_while_the_anchor_is_hovered(probe) -> None:  # noqa: ANN001
    probe.set_hovering(True)
    assert probe.wait_for_visible(True)


def test_tooltip_closes_when_the_anchor_item_hides(probe) -> None:  # noqa: ANN001
    probe.set_hovering(True)
    assert probe.wait_for_visible(True)

    probe.call("hideAnchor")
    assert probe.wait_for_visible(False)

    probe.call("showAnchor")
    assert probe.wait_for_visible(True)


def test_tooltip_closes_when_the_anchor_travels_under_a_stuck_hover(probe) -> None:  # noqa: ANN001
    probe.set_hovering(True)
    assert probe.wait_for_visible(True)

    # `hovering` stays true for the rest of this test: that is exactly the stuck
    # hover state Qt leaves behind when an item moves out from under a stationary
    # cursor, and the tooltip must still take itself down.
    probe.call("panCanvas")
    assert probe.wait_for_visible(False)
    assert bool(probe.call("anchorMoved")) is True


def test_tooltip_stays_closed_until_the_hover_rearms(probe) -> None:  # noqa: ANN001
    probe.set_hovering(True)
    assert probe.wait_for_visible(True)
    probe.call("panCanvas")
    assert probe.wait_for_visible(False)

    # Releasing the hover clears the latch so the next genuine hover reopens.
    probe.set_hovering(False)
    probe.pump(0.1)
    assert bool(probe.call("anchorMoved")) is False

    probe.set_hovering(True)
    assert probe.wait_for_visible(True)

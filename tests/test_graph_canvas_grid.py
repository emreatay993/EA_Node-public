"""Grid alignment, bounded scene size, and rendered pixels on the selected Qt backend.

Native check: QT_QPA_PLATFORM=windows QSG_RHI_BACKEND=d3d11 python -m unittest
tests.test_graph_canvas_grid. Pytest also exercises the offscreen/software path.
"""
from pathlib import Path
import unittest

from PyQt6.QtCore import QObject, QUrl
from PyQt6.QtQuick import QQuickItem, QQuickView, QSGRendererInterface
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from ea_node_editor.ui_qml.theme_bridge import ThemeBridge
from ea_node_editor.ui_qml.viewport_bridge import ViewportBridge


class GraphCanvasGridTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.window = QQuickView()
        self.window.setResizeMode(QQuickView.ResizeMode.SizeRootObjectToView)
        self.window.resize(400, 300)
        self.theme = ThemeBridge(self.window)
        self.view = ViewportBridge(self.window)
        self.window.rootContext().setContextProperty("themeBridge", self.theme)
        self.window.setInitialProperties({
            "viewBridge": self.view,
            "canvasBackgroundVariant": "white",
        })
        path = Path(__file__).resolve().parents[1] / (
            "ea_node_editor/ui_qml/components/graph_canvas/GraphCanvasBackground.qml"
        )
        self.window.setSource(QUrl.fromLocalFile(str(path)))
        self.background = self.window.rootObject()
        self.assertIsNotNone(self.background, str(self.window.errors()))
        self.shader = self.background.findChild(QObject, "graphCanvasGridShaderRenderer")
        self.window.show()
        QTest.qWait(80)

    def tearDown(self):
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()

    def test_grid_follows_live_view_without_waiting_for_scheduled_redraw(self):
        for zoom, x, y in ((1.375, -123.25, 83.75), (0.1, 1e9, -1e9), (3.0, 0.125, -0.25)):
            with self.subTest(zoom=zoom):
                redraws = self.background.property("_redrawRequestCount")
                self.view.set_view_state(zoom, x, y)
                # No processEvents, requestGridRedraw or timer flush here.
                self.assertEqual(self.background.property("_redrawRequestCount"), redraws)
                step = float(self.shader.property("minorStep"))
                offset = self.shader.property("minorOffset")
                self.assertAlmostEqual(offset.x(), (200 - x * zoom) % step, places=4)
                self.assertAlmostEqual(offset.y(), (150 - y * zoom) % step, places=4)

    def test_grid_scene_size_stays_constant_across_density_pan_style_and_resize(self):
        children = self.background.findChildren(QQuickItem)
        for style, zoom, size in (("points", 0.1, 1200), ("points", 1.1, 500), ("lines", 3.0, 800)):
            self.background.setProperty("gridStyle", style)
            self.window.resize(size, 400)
            self.view.set_view_state(zoom, -331.25, 71.875)
            self.app.processEvents()
            self.assertEqual(self.background.findChildren(QQuickItem), children)
            self.assertEqual(self.shader.childItems(), [])
            self.assertEqual(self.background.property("profileGridItemCount"), 1)
        self.background.setProperty("showGrid", False)
        self.assertEqual(self.background.property("profileGridItemCount"), 0)
        self.assertFalse(self.shader.isVisible())

    def test_lines_points_and_software_fallback_render_and_hide(self):
        software = self.window.rendererInterface().graphicsApi() == QSGRendererInterface.GraphicsApi.Software
        self.assertEqual(self.background.property("activeGridRendererKind"), "canvas" if software else "shader")
        self.assertFalse(self.window.grabWindow().isNull())
        for renderer in ("shader", "canvas"):
            self.background.setProperty("gridRendererPreference", renderer)
            for style in ("lines", "points"):
                self.background.setProperty("gridStyle", style)
                QTest.qWait(50)
                image = self.window.grabWindow()
                self.assertFalse(image.isNull())
                dpr = image.width() / self.background.width()
                # A major mark at world origin, and empty space between marks.
                center = image.pixelColor(round(200 * dpr), round(150 * dpr))
                empty = image.pixelColor(round(207 * dpr), round(157 * dpr))
                self.assertLess(center.red(), 250, (renderer, style, center.name()))
                self.assertEqual(empty.name(), "#ffffff")
                between_points = image.pixelColor(round(200 * dpr), round(157 * dpr))
                if style == "points":
                    self.assertEqual(between_points.name(), "#ffffff")
                else:
                    self.assertLess(between_points.red(), 250)
        self.background.setProperty("showGrid", False)
        QTest.qWait(50)
        image = self.window.grabWindow()
        self.assertEqual(image.pixelColor(image.width() // 2, image.height() // 2).name(), "#ffffff")

    def test_gpu_dot_coverage_stays_constant_during_fractional_pan(self):
        if self.background.property("activeGridRendererKind") != "shader":
            self.skipTest("Physical-pixel shader coverage requires a GPU backend")
        self.background.setProperty("gridStyle", "points")
        self.shader.setProperty("minorGridColor", "#000000")
        for delta in (0.0, 0.125, 0.25, 0.375, 0.5):
            self.view.set_view_state(1.0, delta, delta)
            QTest.qWait(20)
            image = self.window.grabWindow()
            dpr = image.width() / self.background.width()
            x, y = round(220 * dpr), round(150 * dpr)
            radius = round(3 * dpr)
            coverage = sum(
                (255 - image.pixelColor(px, py).red()) / 255.0
                for px in range(x - radius, x + radius + 1)
                for py in range(y - radius, y + radius + 1)
            )
            self.assertAlmostEqual(coverage, (1.25 * dpr) ** 2, delta=0.08)

    def test_point_grid_is_legible_on_light_and_dark_backgrounds(self):
        self.background.setProperty("gridStyle", "points")
        for renderer in ("shader", "canvas"):
            self.background.setProperty("gridRendererPreference", renderer)
            for variant in ("white", "dark"):
                with self.subTest(renderer=renderer, variant=variant):
                    self.background.setProperty("canvasBackgroundVariant", variant)
                    QTest.qWait(50)
                    image = self.window.grabWindow()
                    dpr = image.width() / self.background.width()
                    # A minor point must itself be visible, not only the major marks.
                    empty = image.pixelColor(round(227 * dpr), round(157 * dpr))
                    x, y, radius = round(220 * dpr), round(150 * dpr), round(2 * dpr)
                    # Smaller dots spread across adjacent pixels at fractional
                    # positions. Measure contrast over their intended footprint.
                    contrast = sum(
                        abs(image.pixelColor(px, py).red() - empty.red())
                        for px in range(x - radius, x + radius + 1)
                        for py in range(y - radius, y + radius + 1)
                    ) / (1.25 * dpr) ** 2
                    self.assertGreaterEqual(contrast, 50)


if __name__ == "__main__":
    unittest.main()

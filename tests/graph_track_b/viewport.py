from __future__ import annotations

import unittest

from PyQt6.QtCore import QPointF

from tests.graph_track_b.scene_and_model import QRectF, ViewportBridge


class ViewportBridgeTrackBTests(unittest.TestCase):
    def test_viewport_applies_zoom_and_center_updates(self) -> None:
        view = ViewportBridge()
        view.set_zoom(2.5)
        self.assertAlmostEqual(view.zoom, 2.5, places=6)

        view.centerOn(12.0, 18.0)
        self.assertAlmostEqual(view.center_x, 12.0, places=6)
        self.assertAlmostEqual(view.center_y, 18.0, places=6)

        view.pan_by(5.0, -3.0)
        self.assertAlmostEqual(view.center_x, 17.0, places=6)
        self.assertAlmostEqual(view.center_y, 15.0, places=6)

    def test_visible_scene_rect_reflects_viewport_center_and_zoom(self) -> None:
        view = ViewportBridge()
        view.set_viewport_size(1000.0, 500.0)
        view.set_zoom(2.0)
        view.centerOn(10.0, 20.0)

        rect = view.visible_scene_rect()
        self.assertAlmostEqual(rect.x(), -240.0, places=6)
        self.assertAlmostEqual(rect.y(), -105.0, places=6)
        self.assertAlmostEqual(rect.width(), 500.0, places=6)
        self.assertAlmostEqual(rect.height(), 250.0, places=6)

    def test_frame_scene_rect_applies_padding_and_respects_zoom_clamp(self) -> None:
        view = ViewportBridge()
        view.set_viewport_size(1280.0, 720.0)

        self.assertTrue(view.frame_scene_rect(QRectF(100.0, 50.0, 400.0, 200.0)))
        self.assertAlmostEqual(view.zoom, 2.8, places=6)
        self.assertAlmostEqual(view.center_x, 300.0, places=6)
        self.assertAlmostEqual(view.center_y, 150.0, places=6)

        self.assertTrue(view.frame_scene_rect(QRectF(-10.0, -10.0, 20.0, 20.0)))
        self.assertAlmostEqual(view.zoom, 3.0, places=6)

    def test_frame_scene_rect_rejects_empty_bounds(self) -> None:
        view = ViewportBridge()
        view.set_viewport_size(1280.0, 720.0)
        view.set_zoom(1.5)
        view.centerOn(11.0, -9.0)

        self.assertFalse(view.frame_scene_rect(QRectF()))
        self.assertAlmostEqual(view.zoom, 1.5, places=6)
        self.assertAlmostEqual(view.center_x, 11.0, places=6)
        self.assertAlmostEqual(view.center_y, -9.0, places=6)

    def test_visible_scene_rect_payload_and_center_helper(self) -> None:
        view = ViewportBridge()
        view.set_viewport_size(800.0, 600.0)
        view.set_zoom(2.0)
        view.centerOn(100.0, -50.0)

        payload = view.visible_scene_rect_payload
        self.assertAlmostEqual(payload["x"], -100.0, places=6)
        self.assertAlmostEqual(payload["y"], -200.0, places=6)
        self.assertAlmostEqual(payload["width"], 400.0, places=6)
        self.assertAlmostEqual(payload["height"], 300.0, places=6)

        payload_from_slot = view.visible_scene_rect_map()
        self.assertEqual(payload_from_slot, payload)

        view.center_on_scene_point(240.0, 120.0)
        self.assertAlmostEqual(view.center_x, 240.0, places=6)
        self.assertAlmostEqual(view.center_y, 120.0, places=6)

    def test_adjust_zoom_at_viewport_point_keeps_cursor_anchor_with_one_view_commit(self) -> None:
        view = ViewportBridge()
        view.set_viewport_size(800.0, 600.0)
        view.centerOn(100.0, -50.0)

        zoom_commits = 0
        center_commits = 0
        commits = 0

        def _count_zoom(_zoom: float) -> None:
            nonlocal zoom_commits
            zoom_commits += 1

        def _count_center(_center_x: float, _center_y: float) -> None:
            nonlocal center_commits
            center_commits += 1

        def _count_commit() -> None:
            nonlocal commits
            commits += 1

        view.zoom_changed.connect(_count_zoom)
        view.center_changed.connect(_count_center)
        view.view_state_changed.connect(_count_commit)

        anchor_viewport_point = QPointF(560.0, 380.0)
        scene_before = view.mapToScene(anchor_viewport_point)

        changed = view.adjust_zoom_at_viewport_point(1.15, anchor_viewport_point.x(), anchor_viewport_point.y())

        scene_after = view.mapToScene(anchor_viewport_point)
        self.assertTrue(changed)
        self.assertEqual(zoom_commits, 1)
        self.assertEqual(center_commits, 1)
        self.assertEqual(commits, 1)
        self.assertAlmostEqual(view.zoom, 1.15, places=6)
        self.assertAlmostEqual(scene_before.x(), scene_after.x(), places=6)
        self.assertAlmostEqual(scene_before.y(), scene_after.y(), places=6)
        self.assertEqual(view.visible_scene_rect_payload_cached, view.visible_scene_rect_payload)

    def test_frame_scene_rect_payload_slot_normalizes_negative_dimensions(self) -> None:
        view = ViewportBridge()
        view.set_viewport_size(1280.0, 720.0)

        changed = view.frame_scene_rect_payload(600.0, 300.0, -500.0, -250.0, 40.0)

        self.assertTrue(changed)
        self.assertAlmostEqual(view.zoom, 2.4, places=6)
        self.assertAlmostEqual(view.center_x, 350.0, places=6)
        self.assertAlmostEqual(view.center_y, 175.0, places=6)


__all__ = ["ViewportBridgeTrackBTests"]

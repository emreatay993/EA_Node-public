from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import textwrap
import unittest

_REPO_ROOT = Path(__file__).resolve().parents[1]


class EdgeSnapshotSpatialIndexTests(unittest.TestCase):
    def _run_edge_layer_probe(self, label: str, body: str) -> None:
        script = textwrap.dedent(
            """
            from pathlib import Path

            from PyQt6.QtCore import QObject, QUrl
            from PyQt6.QtQml import QQmlComponent, QQmlEngine
            from PyQt6.QtWidgets import QApplication

            from ea_node_editor.ui_qml.viewport_bridge import ViewportBridge

            def to_variant(value):
                return value.toVariant() if hasattr(value, "toVariant") else value

            def refresh(edge_layer):
                edge_layer.requestRedraw()
                app.processEvents()
                app.processEvents()
                return to_variant(edge_layer.property("_visibleEdgeSnapshots"))

            def snapshot(edge_layer, edge_id):
                result = to_variant(edge_layer._visibleEdgeSnapshot(edge_id))
                assert result is not None, edge_id
                return result

            def named_child_items(root, object_name):
                matches = []

                def visit(item):
                    if item is None:
                        return
                    if item.objectName() == object_name:
                        matches.append(item)
                    for child in item.childItems():
                        visit(child)

                visit(root)
                return matches

            def bezier_edge(edge_id, sx, sy, tx, ty, **overrides):
                payload = {
                    "edge_id": edge_id,
                    "source_node_id": "",
                    "source_port_key": "",
                    "target_node_id": "",
                    "target_port_key": "",
                    "source_port_kind": "data",
                    "target_port_kind": "data",
                    "edge_family": "standard",
                    "label": "",
                    "visual_style": {},
                    "flow_style": {},
                    "source_port_side": "right",
                    "target_port_side": "left",
                    "source_anchor_side": "right",
                    "target_anchor_side": "left",
                    "source_anchor_kind": "scene",
                    "target_anchor_kind": "scene",
                    "source_anchor_node_id": "",
                    "target_anchor_node_id": "",
                    "source_hidden_by_backdrop_id": "",
                    "target_hidden_by_backdrop_id": "",
                    "source_anchor_bounds": None,
                    "target_anchor_bounds": None,
                    "lane_bias": 0.0,
                    "sx": sx,
                    "sy": sy,
                    "tx": tx,
                    "ty": ty,
                    "c1x": sx + 72.0,
                    "c1y": sy,
                    "c2x": tx - 72.0,
                    "c2y": ty,
                    "route": "bezier",
                    "pipe_points": [],
                    "color": "#7AA8FF",
                    "data_type_warning": False,
                }
                payload.update(overrides)
                return payload

            app = QApplication.instance() or QApplication([])
            engine = QQmlEngine()
            component = QQmlComponent(
                engine,
                QUrl.fromLocalFile(
                    str(Path.cwd() / "ea_node_editor" / "ui_qml" / "components" / "graph" / "EdgeLayer.qml")
                ),
            )
            if component.status() != QQmlComponent.Status.Ready:
                errors = "\\n".join(error.toString() for error in component.errors())
                raise AssertionError(f"Failed to load EdgeLayer.qml:\\n{errors}")

            view = ViewportBridge()
            view.set_viewport_size(400.0, 300.0)
            view.centerOn(150.0, 100.0)
            edge_layer = component.createWithInitialProperties(
                {
                    "width": 400.0,
                    "height": 300.0,
                    "viewBridge": view,
                }
            ) if hasattr(component, "createWithInitialProperties") else component.create()
            if edge_layer is None:
                errors = "\\n".join(error.toString() for error in component.errors())
                raise AssertionError(f"Failed to instantiate EdgeLayer.qml:\\n{errors}")
            if not hasattr(component, "createWithInitialProperties"):
                edge_layer.setProperty("width", 400.0)
                edge_layer.setProperty("height", 300.0)
                edge_layer.setProperty("viewBridge", view)
            app.processEvents()
            """
        ) + "\n" + textwrap.dedent(body) + "\napp.processEvents()\nimport os\nos._exit(0)\n"
        env = os.environ.copy()
        env["QT_QPA_PLATFORM"] = "offscreen"
        env.setdefault("QT_QUICK_CONTROLS_STYLE", "Basic")
        result = subprocess.run(
            [sys.executable, "-c", script],
            cwd=_REPO_ROOT,
            env=env,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            details = "\n".join(part for part in (result.stdout.strip(), result.stderr.strip()) if part)
            self.fail(f"{label} probe failed with exit code {result.returncode}\n{details}")

    def test_viewport_only_refresh_uses_spatial_candidates_and_skips_offscreen_edges(self) -> None:
        self._run_edge_layer_probe(
            "viewport-only-spatial-candidates",
            """
            edge_layer.setProperty(
                "edges",
                [
                    bezier_edge("near", 80.0, 100.0, 220.0, 100.0),
                    bezier_edge("far", 5080.0, 5100.0, 5220.0, 5100.0),
                    bezier_edge("other_far", -4200.0, -4100.0, -4040.0, -4100.0),
                ],
            )
            refresh(edge_layer)
            draw_snapshots = to_variant(edge_layer.property("_visibleEdgeSnapshots"))
            warm_rebuild_count = int(edge_layer.property("profileSpatialIndexRebuildCount"))

            assert int(edge_layer.property("profileTotalEdgeCount")) == 3
            assert int(edge_layer.property("profileLastCandidateEdgeCount")) < 3
            assert int(edge_layer.property("profileLastSkippedEdgeCount")) > 0
            assert warm_rebuild_count >= 1
            assert int(edge_layer.property("profileSpatialIndexQueryCount")) >= 1 or int(edge_layer.property("profileSpatialIndexQueryCacheHitCount")) >= 1, (
                int(edge_layer.property("profileSpatialIndexQueryCount")),
                int(edge_layer.property("profileSpatialIndexQueryCacheHitCount")),
                int(edge_layer.property("profileSpatialIndexQueryCacheMissCount")),
            )
            assert int(edge_layer.property("profileSpatialIndexCandidateCount")) < 3, int(edge_layer.property("profileSpatialIndexCandidateCount"))
            assert [snapshot["edgeId"] for snapshot in draw_snapshots] == ["near"]
            assert snapshot(edge_layer, "near")["culled"] is False
            assert snapshot(edge_layer, "far")["culled"] is True

            view.pan_by(1.0, 0.0)
            edge_layer.markViewStateRedrawDirty()
            assert edge_layer.flushViewStateRedraw(), "small pan flush failed"
            app.processEvents()
            draw_snapshots = to_variant(edge_layer.property("_visibleEdgeSnapshots"))

            assert int(edge_layer.property("profileSpatialIndexQueryCacheHitCount")) == 1, (
                int(edge_layer.property("profileSpatialIndexQueryCacheHitCount")),
                int(edge_layer.property("profileSpatialIndexQueryCacheMissCount")),
                int(edge_layer.property("profileSpatialIndexQueryCount")),
            )
            assert int(edge_layer.property("profileSpatialIndexQueryCount")) == 0, int(edge_layer.property("profileSpatialIndexQueryCount"))
            assert [snapshot["edgeId"] for snapshot in draw_snapshots] == ["near"], draw_snapshots

            updated_near = bezier_edge("near", 80.0, 100.0, 240.0, 100.0)
            edge_layer.replaceEdgePayload(
                [
                    updated_near,
                    bezier_edge("far", 5080.0, 5100.0, 5220.0, 5100.0),
                    bezier_edge("other_far", -4200.0, -4100.0, -4040.0, -4100.0),
                ],
            )
            app.processEvents()
            app.processEvents()
            draw_snapshots = to_variant(edge_layer.property("_visibleEdgeSnapshots"))
            updated_rebuild_count = int(edge_layer.property("profileSpatialIndexRebuildCount"))

            assert int(edge_layer.property("profileSpatialIndexQueryCacheHitCount")) == 0
            assert int(edge_layer.property("profileSpatialIndexQueryCacheMissCount")) == 1, (
                int(edge_layer.property("profileSpatialIndexQueryCacheHitCount")),
                int(edge_layer.property("profileSpatialIndexQueryCacheMissCount")),
                int(edge_layer.property("profileSpatialIndexQueryCount")),
            )
            assert [snapshot["edgeId"] for snapshot in draw_snapshots] == ["near"], draw_snapshots
            assert abs(float(snapshot(edge_layer, "near")["geometry"]["tx"]) - 240.0) < 0.001

            view.centerOn(5150.0, 5100.0)
            edge_layer.markViewStateRedrawDirty()
            assert edge_layer.flushViewStateRedraw(), "large pan flush failed"
            app.processEvents()
            draw_snapshots = to_variant(edge_layer.property("_visibleEdgeSnapshots"))

            assert int(edge_layer.property("profileTotalEdgeCount")) == 3
            assert int(edge_layer.property("profileLastCandidateEdgeCount")) < 3
            assert int(edge_layer.property("profileLastSkippedEdgeCount")) > 0
            assert int(edge_layer.property("profileGeometryCacheMissCount")) == 0
            assert int(edge_layer.property("profileSpatialIndexRebuildCount")) == updated_rebuild_count
            assert float(edge_layer.property("profileSpatialIndexBuildMs")) == 0.0
            assert int(edge_layer.property("profileSpatialIndexDirtyUpdateCount")) == 0
            assert int(edge_layer.property("profileSpatialIndexQueryCacheMissCount")) == 1, (
                int(edge_layer.property("profileSpatialIndexQueryCacheHitCount")),
                int(edge_layer.property("profileSpatialIndexQueryCacheMissCount")),
                int(edge_layer.property("profileSpatialIndexQueryCount")),
            )
            assert int(edge_layer.property("profileSpatialIndexQueryCount")) >= 1, int(edge_layer.property("profileSpatialIndexQueryCount"))
            assert [snapshot["edgeId"] for snapshot in draw_snapshots] == ["far"], draw_snapshots
            assert snapshot(edge_layer, "near")["culled"] is True
            assert snapshot(edge_layer, "far")["culled"] is False
            assert int(edge_layer.property("profileLastVisibleEdgeSnapshotCount")) == 1
            """,
        )

    def test_hit_testing_uses_visible_index_candidates_without_returning_culled_edges(self) -> None:
        self._run_edge_layer_probe(
            "spatial-hit-testing",
            """
            edge_layer.setProperty(
                "edges",
                [
                    bezier_edge("near", 80.0, 100.0, 220.0, 100.0),
                    bezier_edge("far", 5080.0, 5100.0, 5220.0, 5100.0),
                ],
            )
            refresh(edge_layer)

            assert edge_layer.edgeAtScreen(edge_layer.sceneToScreenX(150.0), edge_layer.sceneToScreenY(100.0)) == "near"
            assert edge_layer.edgeAtScreen(edge_layer.sceneToScreenX(5150.0), edge_layer.sceneToScreenY(5100.0)) == ""
            edge_layer.setProperty("_edgeSpatialIndex", {})
            edge_layer.setProperty("_edgeSpatialIndexDirty", True)
            edge_layer.setProperty("profileSpatialIndexQueryCount", 0)
            edge_layer.setProperty("profileSpatialIndexCandidateCount", 0)
            assert edge_layer.edgeAtScreen(edge_layer.sceneToScreenX(150.0), edge_layer.sceneToScreenY(100.0)) == "near"
            assert bool(edge_layer.property("_edgeSpatialIndexDirty")) is False
            assert int(edge_layer.property("profileSpatialIndexCandidateCount")) < 2

            view.centerOn(5150.0, 5100.0)
            edge_layer.markViewStateRedrawDirty()
            assert edge_layer.flushViewStateRedraw()
            app.processEvents()

            assert edge_layer.edgeAtScreen(edge_layer.sceneToScreenX(150.0), edge_layer.sceneToScreenY(100.0)) == ""
            assert edge_layer.edgeAtScreen(edge_layer.sceneToScreenX(5150.0), edge_layer.sceneToScreenY(5100.0)) == "far"
            """,
        )

    def test_node_geometry_dirty_rebuilds_attached_edge_geometry_and_spatial_index(self) -> None:
        self._run_edge_layer_probe(
            "node-geometry-dirty",
            """
            attached = bezier_edge(
                "attached",
                100.0,
                100.0,
                320.0,
                100.0,
                source_anchor_kind="bounds",
                target_anchor_kind="bounds",
                source_anchor_node_id="source",
                target_anchor_node_id="target",
                source_anchor_bounds={"x": 80.0, "y": 70.0, "width": 80.0, "height": 60.0},
                target_anchor_bounds={"x": 300.0, "y": 70.0, "width": 80.0, "height": 60.0},
            )
            visible_unrelated = bezier_edge("visible_unrelated", 90.0, 180.0, 230.0, 180.0)
            offscreen_unrelated = bezier_edge("offscreen_unrelated", 5080.0, 5100.0, 5220.0, 5100.0)
            edge_layer.setProperty("edges", [attached, visible_unrelated, offscreen_unrelated])
            refresh(edge_layer)
            baseline = snapshot(edge_layer, "attached")["geometry"]
            visible_unrelated_baseline = snapshot(edge_layer, "visible_unrelated")
            offscreen_unrelated_baseline = snapshot(edge_layer, "offscreen_unrelated")
            warm_rebuild_count = int(edge_layer.property("profileSpatialIndexRebuildCount"))
            assert abs(float(baseline["sx"]) - 160.0) < 0.001

            edge_layer.setProperty("dragNodeLookup", {"source": True})
            edge_layer.setProperty("dragDx", 40.0)
            edge_layer.setProperty("dragDy", 0.0)
            edge_layer.setProperty("dragRevision", 1)
            app.processEvents()
            app.processEvents()

            moved = snapshot(edge_layer, "attached")["geometry"]
            assert abs(float(moved["sx"]) - 200.0) < 0.001
            assert int(edge_layer.property("profileTotalEdgeCount")) == 3
            assert int(edge_layer.property("profileLastCandidateEdgeCount")) == 2
            assert int(edge_layer.property("profileLastSkippedEdgeCount")) == 1
            assert int(edge_layer.property("profileGeometryCacheMissCount")) == 1
            assert int(edge_layer.property("profileLastRefreshEdgeCount")) == 1
            assert int(edge_layer.property("profileLastIncidentEdgeRefreshCount")) == 1
            assert int(edge_layer.property("profileIncidentEdgeRefreshCount")) >= 1
            assert int(edge_layer.property("profileSpatialIndexRebuildCount")) == warm_rebuild_count
            assert int(edge_layer.property("profileSpatialIndexDirtyUpdateCount")) == 1
            assert snapshot(edge_layer, "visible_unrelated")["revision"] == visible_unrelated_baseline["revision"]
            assert snapshot(edge_layer, "offscreen_unrelated")["revision"] == offscreen_unrelated_baseline["revision"]
            assert bool(edge_layer.property("_nodeGeometryDirty")) is False
            assert bool(edge_layer.property("_edgeSpatialIndexDirty")) is False

            edge_layer.setProperty("dragNodeLookup", {})
            edge_layer.setProperty("dragDx", 0.0)
            edge_layer.setProperty("dragRevision", 2)
            app.processEvents()
            app.processEvents()

            restored = snapshot(edge_layer, "attached")["geometry"]
            assert abs(float(restored["sx"]) - 160.0) < 0.001
            assert int(edge_layer.property("profileGeometryCacheMissCount")) == 1
            assert int(edge_layer.property("profileLastRefreshEdgeCount")) == 1
            assert int(edge_layer.property("profileLastIncidentEdgeRefreshCount")) == 1
            assert int(edge_layer.property("profileSpatialIndexRebuildCount")) == warm_rebuild_count
            assert int(edge_layer.property("profileSpatialIndexDirtyUpdateCount")) == 1
            assert bool(edge_layer.property("_edgeSpatialIndexDirty")) is False
            """,
        )

    def test_edge_topology_delta_refreshes_only_dirty_edges_and_spatial_index_entries(self) -> None:
        self._run_edge_layer_probe(
            "edge-topology-delta",
            """
            stable = bezier_edge("stable", 80.0, 100.0, 220.0, 100.0, source_node_id="source", target_node_id="target")
            stable_other = bezier_edge("stable_other", 70.0, 140.0, 210.0, 140.0, source_node_id="other_source", target_node_id="other_target")
            removed = bezier_edge("removed", 90.0, 180.0, 230.0, 180.0, source_node_id="removed_source", target_node_id="removed_target")
            added = bezier_edge("added", 110.0, 240.0, 250.0, 240.0, source_node_id="added_source", target_node_id="added_target")
            edge_layer.setProperty("edges", [stable, stable_other, removed])
            refresh(edge_layer)
            stable_baseline = snapshot(edge_layer, "stable")
            stable_other_baseline = snapshot(edge_layer, "stable_other")
            removed_baseline = snapshot(edge_layer, "removed")
            warm_topology_rebuild_count = int(edge_layer.property("profileEdgeTopologyRebuildCount"))
            warm_topology_entry_update_count = int(edge_layer.property("profileEdgeTopologyEntryUpdateCount"))
            warm_rebuild_count = int(edge_layer.property("profileSpatialIndexRebuildCount"))
            assert stable_baseline is not None
            assert stable_other_baseline is not None
            assert removed_baseline is not None

            edge_layer.applyStructuralEdgePayloadDelta(
                [stable, stable_other, added],
                {
                    "added_edge_ids": ["added"],
                    "updated_edge_ids": [],
                    "removed_edge_ids": ["removed"],
                    "dirty_edge_ids": ["added", "removed"],
                },
            )
            app.processEvents()
            app.processEvents()

            draw_snapshots = to_variant(edge_layer.property("_visibleEdgeSnapshots"))
            assert [snapshot["edgeId"] for snapshot in draw_snapshots] == ["stable", "stable_other", "added"], draw_snapshots
            assert to_variant(edge_layer.property("_edgeIds")) == ["stable", "stable_other", "added"], to_variant(edge_layer.property("_edgeIds"))
            edge_by_id = to_variant(edge_layer.property("_edgeById"))
            assert "added" in edge_by_id, edge_by_id
            assert "removed" not in edge_by_id, edge_by_id
            edge_ids_by_node = to_variant(edge_layer.property("_edgeIdsByNodeId"))
            assert "added" in edge_ids_by_node["added_source"], edge_ids_by_node
            assert "removed" not in edge_ids_by_node.get("removed_source", []), edge_ids_by_node
            dependency_by_id = to_variant(edge_layer.property("_edgeDependencyNodeIdsById"))
            assert dependency_by_id["added"] == ["added_source", "added_target"], dependency_by_id
            assert "removed" not in dependency_by_id, dependency_by_id
            assert snapshot(edge_layer, "stable")["revision"] == stable_baseline["revision"], snapshot(edge_layer, "stable")
            assert snapshot(edge_layer, "stable_other")["revision"] == stable_other_baseline["revision"], snapshot(edge_layer, "stable_other")
            assert to_variant(edge_layer._visibleEdgeSnapshot("removed")) is None, to_variant(edge_layer._visibleEdgeSnapshot("removed"))
            assert snapshot(edge_layer, "added")["revision"] > stable_baseline["revision"], snapshot(edge_layer, "added")
            assert int(edge_layer.property("profileTotalEdgeCount")) == 3, int(edge_layer.property("profileTotalEdgeCount"))
            assert int(edge_layer.property("profileLastRefreshEdgeCount")) == 2, int(edge_layer.property("profileLastRefreshEdgeCount"))
            assert int(edge_layer.property("profileGeometryCacheMissCount")) == 1, int(edge_layer.property("profileGeometryCacheMissCount"))
            assert int(edge_layer.property("profileEdgeTopologyRebuildCount")) == warm_topology_rebuild_count, (
                int(edge_layer.property("profileEdgeTopologyRebuildCount")),
                warm_topology_rebuild_count,
            )
            assert int(edge_layer.property("profileEdgeTopologyEntryUpdateCount")) - warm_topology_entry_update_count == 2, (
                int(edge_layer.property("profileEdgeTopologyEntryUpdateCount")),
                warm_topology_entry_update_count,
            )
            assert int(edge_layer.property("profileSpatialIndexRebuildCount")) == warm_rebuild_count, (
                int(edge_layer.property("profileSpatialIndexRebuildCount")),
                warm_rebuild_count,
            )
            assert int(edge_layer.property("profileSpatialIndexDirtyUpdateCount")) == 1, int(edge_layer.property("profileSpatialIndexDirtyUpdateCount"))
            spatial_index = to_variant(edge_layer.property("_edgeSpatialIndex"))
            assert "added" in spatial_index["entriesById"], spatial_index
            assert "removed" not in spatial_index["entriesById"], spatial_index
            assert bool(edge_layer.property("_edgeTopologyDirty")) is False, bool(edge_layer.property("_edgeTopologyDirty"))
            assert bool(edge_layer.property("_edgeTopologyDeltaDirty")) is False, bool(edge_layer.property("_edgeTopologyDeltaDirty"))
            assert bool(edge_layer.property("_edgeSpatialIndexDirty")) is False, bool(edge_layer.property("_edgeSpatialIndexDirty"))
            """,
        )

    def test_retained_edges_and_flow_labels_keep_delegates_for_targeted_updates(self) -> None:
        self._run_edge_layer_probe(
            "qml-delegate-stability",
            """
            standard = bezier_edge("standard", 80.0, 100.0, 220.0, 100.0)
            edge_layer.setProperty("edges", [standard])
            refresh(edge_layer)
            retained_layer = edge_layer.findChild(QObject, "graphCanvasEdgeRetainedLayer")
            assert retained_layer is not None
            assert int(retained_layer.property("retainedEdgeCount")) == 1
            retained_creates = int(retained_layer.property("profileRetainedDelegateCreateCount"))
            retained_destroys = int(retained_layer.property("profileRetainedDelegateDestroyCount"))
            assert retained_creates == 1, retained_creates
            assert retained_destroys == 0, retained_destroys
            retained_skips = int(retained_layer.property("profileRetainedModelEntrySkipCount"))
            retained_updates = int(retained_layer.property("profileRetainedModelEntryUpdateCount"))
            retained_layer.requestRetainedPaint()
            app.processEvents()
            assert int(retained_layer.property("profileRetainedModelEntrySkipCount")) == retained_skips + 1
            assert int(retained_layer.property("profileRetainedModelEntryUpdateCount")) == retained_updates

            moved_standard = dict(standard)
            moved_standard["tx"] = 240.0
            moved_standard["c2x"] = 168.0
            edge_layer.applyStructuralEdgePayloadDelta(
                [moved_standard],
                {
                    "added_edge_ids": [],
                    "updated_edge_ids": ["standard"],
                    "removed_edge_ids": [],
                    "dirty_edge_ids": ["standard"],
                },
            )
            app.processEvents()
            app.processEvents()

            assert int(retained_layer.property("retainedEdgeCount")) == 1
            assert int(retained_layer.property("profileRetainedDelegateCreateCount")) == retained_creates
            assert int(retained_layer.property("profileRetainedDelegateDestroyCount")) == retained_destroys
            assert int(retained_layer.property("profileRetainedModelEntryUpdateCount")) == retained_updates + 1
            assert abs(float(snapshot(edge_layer, "standard")["geometry"]["tx"]) - 240.0) < 0.001

            flow = bezier_edge(
                "flow",
                80.0,
                150.0,
                220.0,
                150.0,
                edge_family="flow",
                source_port_kind="flow",
                target_port_kind="flow",
                label="Primary path",
            )
            edge_layer.setProperty("edgeTopologyDelta", {})
            edge_layer.setProperty("edges", [flow])
            refresh(edge_layer)
            label_layer = edge_layer.findChild(QObject, "graphEdgeFlowLabelLayer")
            assert label_layer is not None
            labels = named_child_items(edge_layer, "graphEdgeFlowLabelItem")
            assert len(labels) == 1, len(labels)
            label_creates = int(label_layer.property("profileLabelDelegateCreateCount"))
            label_destroys = int(label_layer.property("profileLabelDelegateDestroyCount"))
            assert label_creates == 1, label_creates
            assert label_destroys == 0, label_destroys
            label_skips = int(label_layer.property("profileFlowLabelModelSyncSkipCount"))
            label_layer._syncFlowLabelModel()
            app.processEvents()
            assert int(label_layer.property("profileFlowLabelModelSyncSkipCount")) == label_skips + 1

            renamed_flow = dict(flow)
            renamed_flow["label"] = "Renamed path"
            edge_layer.applyStructuralEdgePayloadDelta(
                [renamed_flow],
                {
                    "added_edge_ids": [],
                    "updated_edge_ids": ["flow"],
                    "removed_edge_ids": [],
                    "dirty_edge_ids": ["flow"],
                },
            )
            app.processEvents()
            app.processEvents()

            labels = named_child_items(edge_layer, "graphEdgeFlowLabelItem")
            assert len(labels) == 1, len(labels)
            assert labels[0].property("labelText") == "Renamed path", labels[0].property("labelText")
            assert int(label_layer.property("profileLabelDelegateCreateCount")) == label_creates
            assert int(label_layer.property("profileLabelDelegateDestroyCount")) == label_destroys

            added_flow = bezier_edge(
                "flow_added",
                80.0,
                205.0,
                220.0,
                205.0,
                edge_family="flow",
                source_port_kind="flow",
                target_port_kind="flow",
                label="Secondary path",
            )
            edge_layer.applyStructuralEdgePayloadDelta(
                [renamed_flow, added_flow],
                {
                    "added_edge_ids": ["flow_added"],
                    "updated_edge_ids": [],
                    "removed_edge_ids": [],
                    "dirty_edge_ids": ["flow_added"],
                    "added_edges": [{"edge_id": "flow_added", "index": 1, "payload": added_flow}],
                    "edge_count_after": 2,
                },
            )
            app.processEvents()
            app.processEvents()

            labels = named_child_items(edge_layer, "graphEdgeFlowLabelItem")
            label_texts = sorted([label.property("labelText") for label in labels])
            assert label_texts == ["Renamed path", "Secondary path"], label_texts
            assert int(label_layer.property("profileLabelDelegateCreateCount")) == label_creates + 1
            assert int(label_layer.property("profileLabelDelegateDestroyCount")) == label_destroys

            edge_layer.applyStructuralEdgePayloadDelta(
                [added_flow],
                {
                    "added_edge_ids": [],
                    "updated_edge_ids": [],
                    "removed_edge_ids": ["flow"],
                    "dirty_edge_ids": ["flow"],
                    "edge_count_after": 1,
                },
            )
            app.processEvents()
            app.processEvents()

            labels = named_child_items(edge_layer, "graphEdgeFlowLabelItem")
            assert len(labels) == 1, len(labels)
            assert labels[0].property("labelText") == "Secondary path", labels[0].property("labelText")
            assert int(label_layer.property("profileLabelDelegateCreateCount")) == label_creates + 1
            assert int(label_layer.property("profileLabelDelegateDestroyCount")) == label_destroys + 1
            """,
        )

    def test_packet_exposes_dirty_flags_spatial_metrics_and_harness_counts(self) -> None:
        graph_dir = _REPO_ROOT / "ea_node_editor" / "ui_qml" / "components" / "graph"
        edge_layer_text = (graph_dir / "EdgeLayer.qml").read_text(encoding="utf-8")
        cache_text = (graph_dir / "EdgeSnapshotCache.js").read_text(encoding="utf-8")
        retained_text = (graph_dir / "EdgeRetainedLayer.qml").read_text(encoding="utf-8")
        flow_label_text = (graph_dir / "EdgeFlowLabelLayer.qml").read_text(encoding="utf-8")
        harness_text = (_REPO_ROOT / "ea_node_editor" / "ui" / "perf" / "performance_harness.py").read_text(
            encoding="utf-8"
        )

        for dirty_flag in (
            "_edgeTopologyDirty",
            "_nodeGeometryDirty",
            "_viewportDirty",
            "_selectionDirty",
            "_crossingStyleDirty",
            "_themeDirty",
        ):
            self.assertIn(dirty_flag, edge_layer_text)
        for snippet in (
            "ensureSpatialIndex",
            "_querySpatialIndex",
            "profileLastCandidateEdgeCount",
            "profileLastSkippedEdgeCount",
            "profileGeometryCacheHitCount",
            "profileGeometryCacheMissCount",
            "profileEdgeTopologyRebuildCount",
            "profileEdgeTopologyEntryUpdateCount",
            "profileSpatialIndexRebuildCount",
            "profileSpatialIndexDirtyUpdateCount",
            "profileSpatialIndexQueryCount",
            "profileSpatialIndexQueryCacheHitCount",
            "profileSpatialIndexCandidateCount",
            "_visibleEdgeSnapshots",
            "_visibleEdgeSnapshotById",
            "_activeNodeGeometryDirty",
            "profileLastRefreshEdgeCount",
            "profileIncidentEdgeRefreshCount",
            "profileLastIncidentEdgeRefreshCount",
            "edgeRendererKind",
            "edgeRendererCanvasFallbackActive",
            "_edgeById",
            "_edgeIdsByNodeId",
            "_edgeDrawOrderById",
            "_edgeTopologyRevision",
            "_activeNodeGeometryRevision",
            "_replaceEdgeTopologyEntries",
            "_applyStructuralEdgeTopologyEntries",
        ):
            self.assertIn(snippet, cache_text + edge_layer_text)
        for snippet in (
            "retainedEdgeModel",
            "profileRetainedDelegateCreateCount",
            "profileRetainedDelegateDestroyCount",
            "profileRetainedModelEntrySkipCount",
            "flowLabelModel",
            "profileLabelDelegateCreateCount",
            "profileLabelDelegateDestroyCount",
            "profileFlowLabelModelSyncSkipCount",
        ):
            self.assertIn(snippet, retained_text + flow_label_text)
        for stale_snippet in (
            "JSON.stringify",
            "_stableKey",
            "_stableClone",
            "_incidentEdgeLookup(edgesList",
            "fallbackEdgesList",
            "unboundedEdgeIds",
            "model: root.edgeLayer ? (root.edgeLayer.edges || []) : []",
            "structuralDelta || !_replaceEdgeTopologyEntries",
        ):
            self.assertNotIn(stale_snippet, cache_text + flow_label_text)
        for metric_key in (
            "candidate_edge_count",
            "visible_edge_snapshot_count",
            "skipped_edge_count",
            "geometry_cache_hit_count",
            "geometry_cache_miss_count",
            "edge_spatial_index_build_ms",
            "edge_renderer_kind",
            "edge_renderer_ab",
        ):
            self.assertIn(metric_key, harness_text)


if __name__ == "__main__":
    unittest.main()

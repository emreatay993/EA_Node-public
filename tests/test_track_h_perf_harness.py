from __future__ import annotations

import copy
import importlib.util
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from ea_node_editor.nodes.bootstrap import build_default_registry
from ea_node_editor.persistence.serializer import JsonProjectSerializer
from ea_node_editor.ui.perf.performance_harness import (
    BenchmarkConfig,
    SyntheticGraphConfig,
    _resolve_baseline_mode,
    generate_synthetic_project,
    run_benchmark,
)
from ea_node_editor.ui.perf import performance_harness


class TrackHPerformanceHarnessTests(unittest.TestCase):
    def test_benchmark_bridge_enables_notched_ports_by_default(self) -> None:
        bridge = performance_harness._BenchmarkMainWindowBridge()

        self.assertTrue(bridge.graphics_notched_ports)
        self.assertTrue(bridge.property("graphics_notched_ports"))

    def test_node_insertion_cli_defaults_and_stress_scenario_routing(self) -> None:
        args = performance_harness._parse_args(["--scenario", "node_insertions"])

        self.assertEqual(args.node_insertion_samples, 40)
        self.assertEqual(args.node_insertion_warmup_samples, 3)
        self.assertEqual(
            performance_harness._scenario_label_for_config(
                BenchmarkConfig(
                    scenario="node_insertions",
                    stress_fixture="real",
                )
            ),
            "node_insertions",
        )

    def test_mutation_scenario_cli_is_repeatable_with_full_set_default(self) -> None:
        default_args = performance_harness._parse_args(
            ["--scenario", "graph_mutations"]
        )
        selected_args = performance_harness._parse_args(
            [
                "--scenario",
                "graph_mutations",
                "--mutation-scenario",
                "create_edge",
                "--mutation-scenario",
                "undo_redo",
            ]
        )

        self.assertEqual(default_args.mutation_scenario, [])
        self.assertEqual(
            performance_harness._resolve_mutation_benchmark_scenarios(
                default_args.mutation_scenario
            ),
            performance_harness._MUTATION_BENCHMARK_SCENARIOS,
        )
        self.assertEqual(
            selected_args.mutation_scenario,
            ["create_edge", "undo_redo"],
        )

    def test_interaction_zoom_cli_defaults_and_overrides(self) -> None:
        default_args = performance_harness._parse_args([])
        custom_args = performance_harness._parse_args(
            [
                "--interaction-zoom-min",
                "0.75",
                "--interaction-zoom-max",
                "1.25",
            ]
        )

        self.assertEqual(default_args.interaction_zoom_min, 0.5)
        self.assertEqual(default_args.interaction_zoom_max, 2.0)
        self.assertEqual(custom_args.interaction_zoom_min, 0.75)
        self.assertEqual(custom_args.interaction_zoom_max, 1.25)

    def test_node_insertion_report_applies_strict_display_attached_d3d11_p95_gate(
        self,
    ) -> None:
        samples = []
        for profile in performance_harness._NODE_INSERTION_PROFILES:
            for sample_index, presented_ms in enumerate((50.0, 60.0)):
                samples.append(
                    {
                        "profile": profile,
                        "sample_index": sample_index,
                        "dispatch_to_model_commit_ms": 5.0 + sample_index,
                        "all_primary_delegates_presented_ms": presented_ms,
                        "inserted_node_count": 2 if "workflow" in profile else 1,
                        "inserted_edge_count": 1
                        if profile == "small_custom_workflow"
                        else 0,
                        "expected_primary_delegate_count": (
                            2 if profile == "small_custom_workflow" else 1
                        ),
                        "undo_entry_count": 1,
                        "comment_input_helper_present_at_completion": (
                            profile == "group_backdrop"
                        ),
                    }
                )
        renderer = {
            "qt_qpa_platform": "windows",
            "graphics_api": "Direct3D11Rhi",
            "graphics_api_label": "Direct3D 11",
            "qsg_rhi_backend": "d3d11",
            "software_fallback_active": False,
        }
        report = performance_harness._node_insertion_report_payload(
            samples=samples,
            sample_budget=8,
            warmup_samples_per_profile=3,
            renderer_diagnostics=renderer,
            environment={"qt_qpa_platform": "windows"},
        )

        self.assertEqual(report["acceptance_result"]["status"], "PASS")
        self.assertFalse(
            report["measurement_contract"]["grab_window_readback_included"]
        )
        self.assertFalse(
            report["measurement_contract"]["heavy_content_readiness_included"]
        )
        self.assertTrue(
            report["measurement_contract"]["undo_history_included_in_dispatch_timing"]
        )
        self.assertEqual(report["sample_budget"], 8)
        self.assertEqual(
            {
                summary["expected_sample_count"]
                for summary in report["profile_summaries"].values()
            },
            {2},
        )
        self.assertEqual(
            report["profile_summaries"]["ordinary_node"][
                "all_primary_delegates_presented_ms"
            ]["summary"]["p50"],
            55.0,
        )
        self.assertEqual(
            report["profile_summaries"]["ordinary_node"][
                "all_primary_delegates_presented_ms"
            ]["summary"]["p95"],
            59.5,
        )

        threshold_samples = [dict(sample) for sample in samples]
        for sample in threshold_samples:
            if sample["profile"] == "ordinary_node":
                sample["all_primary_delegates_presented_ms"] = 100.0
        threshold_report = performance_harness._node_insertion_report_payload(
            samples=threshold_samples,
            sample_budget=8,
            warmup_samples_per_profile=3,
            renderer_diagnostics=renderer,
            environment={"qt_qpa_platform": "windows"},
        )
        self.assertEqual(
            threshold_report["profile_summaries"]["ordinary_node"]["acceptance"][
                "status"
            ],
            "FAIL",
        )
        self.assertEqual(threshold_report["acceptance_result"]["status"], "FAIL")

        invalid_report = performance_harness._node_insertion_report_payload(
            samples=samples,
            sample_budget=8,
            warmup_samples_per_profile=3,
            renderer_diagnostics={
                "qt_qpa_platform": "offscreen",
                "graphics_api": "Software",
                "qsg_rhi_backend": "software",
                "software_fallback_active": True,
            },
            environment={"qt_qpa_platform": "offscreen"},
        )
        self.assertEqual(invalid_report["acceptance_result"]["status"], "INVALID")

    def test_node_insertion_completion_waits_for_frame_after_delegate_observation(
        self,
    ) -> None:
        class _FakeCard:
            def property(self, name: str):
                return {
                    "nodeData": {"node_id": "inserted-node"},
                    "visible": True,
                    "width": 120.0,
                    "height": 80.0,
                }.get(name)

            def isVisible(self) -> bool:
                return True

            def width(self) -> float:
                return 120.0

            def height(self) -> float:
                return 80.0

        host = SimpleNamespace(frame_index=5)

        class _FakeApp:
            calls = 0

            def processEvents(self) -> None:
                self.calls += 1
                if self.calls >= 2:
                    host.frame_index = 6

        class _FakeWindow:
            updates = 0

            def update(self) -> None:
                self.updates += 1

        host.app = _FakeApp()
        host.window = _FakeWindow()
        host.node_cards = lambda: [_FakeCard()]
        host.group_backdrop_input_cards = lambda: []
        host.frame_render_timestamp_index = lambda: host.frame_index

        result = performance_harness._wait_for_node_insertion_presented_frame(
            host,
            primary_node_ids=["inserted-node"],
            frame_start_index=5,
            timeout_ms=100,
        )

        self.assertGreaterEqual(host.app.calls, 2)
        self.assertGreaterEqual(host.window.updates, 1)
        self.assertEqual(result["completion_frame_count"], 1)
        self.assertEqual(result["presented_primary_delegate_count"], 1)

    def test_first_frame_attribution_treats_command_dispatch_as_inclusive_envelope(
        self,
    ) -> None:
        sample = {
            "first_frame_after_mutation_ms": 100.0,
            "phase_timings_ms": {
                "command_dispatch_ms": 80.0,
                "graph_model_mutation_ms": 10.0,
                "history_apply_ms": 5.0,
                "payload_rebuild_ms": 20.0,
                "edge_payload_update_ms": 0.0,
                "scene_publish_ms": 15.0,
                "visible_node_model_update_ms": 10.0,
                "harness_force_exact_refresh_ms": 3.0,
                "qt_event_drain_ms": 2.0,
                "render_callback_wait_ms": 5.0,
                "readback_grab_ms": 1.0,
                "post_readback_event_drain_ms": 4.0,
            },
        }

        attribution = performance_harness._first_frame_phase_attribution_ms(sample)

        self.assertNotIn("command_dispatch_ms", attribution)
        self.assertEqual(attribution["python_scene_payload_rebuild_ms"], 20.0)
        self.assertEqual(attribution["python_scene_publish_ms"], 5.0)
        self.assertEqual(attribution["visible_model_sync_ms"], 10.0)
        self.assertEqual(attribution["harness_force_exact_refresh_ms"], 3.0)
        self.assertEqual(attribution["qt_event_drain_ms"], 2.0)
        self.assertEqual(attribution["graph_mutation_or_history_apply_ms"], 45.0)
        self.assertEqual(attribution["unattributed_first_frame_ms"], 5.0)
        self.assertEqual(sum(attribution.values()), 100.0)

    def test_drag_gesture_feature_detects_membership_freeze_counter(self) -> None:
        class Canvas:
            def __init__(self, freeze_count: int | None) -> None:
                self.freeze_count = freeze_count

            def property(self, name: str):
                if name == "profileLiveDragMembershipFreezeCount":
                    return self.freeze_count
                if name == "liveDragAnchorNodeId":
                    return ""
                return None

        def host(*, freeze_increment: int | None):
            canvas = Canvas(None if freeze_increment is None else 10)
            frozen = False

            def emit_offset(*_args) -> None:
                nonlocal frozen
                if freeze_increment is not None and not frozen:
                    canvas.freeze_count += freeze_increment
                    frozen = True

            node_card = SimpleNamespace(
                property=lambda _name: {"node_id": "node-1"},
                dragOffsetChanged=SimpleNamespace(emit=emit_offset),
                dragCanceled=SimpleNamespace(emit=lambda *_args: None),
            )
            return SimpleNamespace(
                canvas=canvas,
                app=SimpleNamespace(processEvents=lambda: None),
                control_node_card=lambda: node_card,
                render_frame=lambda: None,
            )

        unsupported = performance_harness._measure_node_drag_gesture(
            host(freeze_increment=None), sample_index=0
        )
        self.assertFalse(unsupported.membership_freeze_supported)
        self.assertIsNone(unsupported.membership_freeze_count)

        supported = performance_harness._measure_node_drag_gesture(
            host(freeze_increment=1), sample_index=0
        )
        self.assertTrue(supported.membership_freeze_supported)
        self.assertEqual(supported.membership_freeze_count, 1)

        with self.assertRaisesRegex(RuntimeError, "observed 2 freezes"):
            performance_harness._measure_node_drag_gesture(
                host(freeze_increment=2), sample_index=0
            )

    def test_selected_drag_payload_keeps_absent_baseline_features_explicit(
        self,
    ) -> None:
        measurement = performance_harness._SelectedNodeDragGestureMeasurement(
            first_offset_ms=1.0,
            steady_offset_ms=(0.5,),
            full_gesture_ms=4.0,
            end_clear_ms=2.0,
            membership_freeze_supported=False,
            membership_freeze_count=None,
            membership_size_supported=False,
            membership_size=None,
            raw_input_count=None,
            flushed_update_count=None,
            incident_edge_count=None,
            render_timings_ms={},
            clear_render_timings_ms={},
            drag_frame_timestamp_range=(0, 1),
            clear_frame_timestamp_range=(1, 2),
        )

        payload = performance_harness._supplemental_selected_drag_payload(
            selected_node_ids=("node-1", "node-2", "node-3"),
            measurements=[measurement],
            frame_interval_samples_ms=[],
        )

        self.assertFalse(payload["membership_size"]["supported"])
        self.assertEqual(payload["membership_size"]["samples"], [None])
        self.assertIsNone(payload["membership_size"]["verified"])
        self.assertFalse(payload["membership_freeze"]["supported"])
        self.assertEqual(payload["membership_freeze"]["samples"], [None])
        self.assertIsNone(payload["membership_freeze"]["verified"])

    def _mock_single_run_report(self) -> dict:
        return {
            "generated_at_utc": "2026-03-21T00:00:00+00:00",
            "config": {
                "scenario": "synthetic_exec",
            },
            "environment": {
                "hostname": "test-host",
                "machine": "x86_64",
                "qt_version": "6.0.0",
                "qt_qpa_platform": "windows",
                "qml_host_env": "qquickwidget",
                "qml_host_kind_selected": "qquickwidget",
                "qt_quick_backend": "",
                "qsg_rhi_backend": "",
                "qsg_rhi_backend_override": "",
                "qtquick_backend_selected": "",
                "qtquick_backend_selection_reason": "qt_default",
                "qsg_info": "",
                "qsg_info_capture_enabled": False,
                "qsg_render_loop": "",
            },
            "display_diagnostics": {
                "qt_platform": "windows",
                "display_attached": True,
                "active_graphics_api": "Direct3D11Rhi",
                "active_graphics_api_label": "Direct3D 11",
                "rhi_backend": "d3d11",
                "render_loop": "threaded",
                "host_kind": "qquickview_container",
                "screen_device_pixel_ratio": 2.0,
                "window_effective_device_pixel_ratio": 2.0,
                "software_fallback_active": False,
                "software_fallback_reason": "",
                "readback_included": True,
                "qsg_info_capture_enabled": True,
                "acceptance_allowed": True,
                "acceptance_blockers": [],
            },
            "packet_verification_result": {"status": "PASS", "pass": True},
            "performance_acceptance_result": {"status": "FAIL", "pass": False},
            "metrics": {
                "project_graph_load_ms": {"summary": {"p95": 10.0}},
                "pan_interaction_ms": {"summary": {"p95": 20.0}},
                "zoom_interaction_ms": {"summary": {"p95": 30.0}},
                "pan_zoom_combined_ms": {"summary": {"p95": 40.0}},
                "node_drag_control_ms": {"summary": {"p95": 50.0}},
                "node_drag_first_offset_ms": {"summary": {"p95": 12.0}},
                "node_drag_steady_offset_ms": {"summary": {"p95": 8.0}},
                "node_drag_full_gesture_ms": {"summary": {"p95": 80.0}},
                "node_drag_end_clear_ms": {"summary": {"p95": 10.0}},
                "frame_interval_ms_without_readback": {"summary": {"p95": 16.0}},
            },
        }

    def _mock_interaction_samples(
        self, *, membership_freeze_supported: bool = True
    ) -> dict:
        renderer_diagnostics = {
            "qt_qpa_platform": "offscreen",
            "qt_quick_backend": "software",
            "qsg_rhi_backend": "software",
            "qsg_info": "1",
            "qsg_info_capture_enabled": True,
            "qsg_render_loop": "",
            "qtquick_backend_selected": "software",
            "qtquick_backend_selection_reason": "software_qpa_platform",
            "qtquick_backend_forced_software": True,
            "graphics_api": "Software",
            "graphics_api_label": "Software",
            "qml_host_env": "qquickwidget",
            "qml_host_kind": "qquickwidget",
            "qml_host_kind_selected": "qquickwidget",
            "screen_device_pixel_ratio": 1.25,
            "window_effective_device_pixel_ratio": 1.25,
            "grab_window_readback_included": True,
            "software_fallback_active": True,
            "software_fallback_reason": "software_qpa_platform",
        }
        return {
            "pan_ms": [2.0],
            "zoom_ms": [3.0],
            "combined_ms": [5.0],
            "node_drag_control_ms": [4.0],
            "node_drag_first_offset_ms": [1.0],
            "node_drag_steady_offset_ms": [0.5] * 11,
            "node_drag_full_gesture_ms": [9.0],
            "node_drag_end_clear_ms": [2.0],
            "membership_freeze_supported": membership_freeze_supported,
            "node_drag_membership_freeze_count": [
                1 if membership_freeze_supported else None
            ],
            "frame_interval_ms_without_readback": [16.0],
            "phase_timings_ms": {
                "canvas_setup_ms": {"samples": [1.0], "summary": {"p95": 1.0}},
                **{
                    phase_key: {"samples": [0.1], "summary": {"p95": 0.1}}
                    for phase_key in performance_harness._CANVAS_SETUP_PHASE_KEYS
                },
                "canvas_warmup_ms": {"samples": [], "summary": {"p95": 0.0}},
                "pan_interaction_ms": {"samples": [2.0], "summary": {"p95": 2.0}},
                "zoom_interaction_ms": {"samples": [3.0], "summary": {"p95": 3.0}},
                "node_drag_control_ms": {"samples": [4.0], "summary": {"p95": 4.0}},
                "node_drag_first_offset_ms": {
                    "samples": [1.0],
                    "summary": {"p95": 1.0},
                },
                "node_drag_steady_offset_ms": {
                    "samples": [0.5] * 11,
                    "summary": {"p95": 0.5},
                },
                "node_drag_full_gesture_ms": {
                    "samples": [9.0],
                    "summary": {"p95": 9.0},
                },
                "node_drag_end_clear_ms": {"samples": [2.0], "summary": {"p95": 2.0}},
                "frame_interval_ms_without_readback": {
                    "samples": [16.0],
                    "summary": {"p95": 16.0},
                },
            },
            "profiling_counts": {
                "pan_frame_scheduler_coalesced_redraw_request_count": {
                    "samples": [1.0],
                    "summary": {"p95": 1.0},
                }
            },
            "benchmark": {
                "grab_window_readback_included": True,
                "frame_interval_metric": "frame_interval_ms_without_readback",
                "node_drag_gesture_offset_count": 12,
                "membership_freeze_supported": membership_freeze_supported,
                "node_drag_membership_freezes_per_gesture": (
                    1 if membership_freeze_supported else None
                ),
                "node_drag_membership_freeze_counts": [
                    1 if membership_freeze_supported else None
                ],
                "node_drag_membership_freeze_verified": (
                    True if membership_freeze_supported else None
                ),
                "node_drag_steady_state_gate_metric": "node_drag_steady_offset_ms",
                "node_drag_legacy_continuity_metric": "node_drag_control_ms",
            },
            "renderer_diagnostics": renderer_diagnostics,
            "feature_parity": {"pass": True, "failures": []},
        }

    def _mock_graph_mutation_benchmark(
        self, *, fixture_checksum_sha256: str = ""
    ) -> dict:
        samples = []
        for index, scenario in enumerate(
            performance_harness._MUTATION_BENCHMARK_SCENARIOS
        ):
            samples.append(
                {
                    "scenario": scenario,
                    "operation_iteration": index,
                    "mutation_wall_clock_samples_ms": [1.0 + index],
                    "phase_timings_ms": {
                        "command_dispatch_ms": 0.1 + index,
                        "history_capture_ms": 0.2 + index,
                        "history_apply_ms": 0.3 + index,
                        "graph_model_mutation_ms": 0.4 + index,
                        "payload_rebuild_ms": 0.5 + index,
                        "scene_publish_ms": 0.6 + index,
                        "visible_node_model_update_ms": 0.7 + index,
                        "harness_force_exact_refresh_ms": 0.75 + index,
                        "qt_event_drain_ms": 0.8 + index,
                        "edge_payload_update_ms": 0.8 + index,
                        "render_callback_wait_ms": 0.85 + index,
                        "readback_grab_ms": 0.86 + index,
                        "post_readback_event_drain_ms": 0.87 + index,
                        "first_frame_after_mutation_ms": 0.9 + index,
                    },
                    "setup_excluded_from_mutation_timing": True,
                    "setup_wall_clock_samples_ms": [0.05 + index]
                    if scenario
                    in {
                        "create_edge",
                        "remove_edge",
                        "delete_node_with_incident_edges",
                        "undo_redo",
                    }
                    else [],
                    "setup_phase_timings_ms": {
                        "command_dispatch_ms": 0.01 + index,
                        "graph_model_mutation_ms": 0.02 + index,
                        "payload_rebuild_ms": 0.03 + index,
                        "scene_publish_ms": 0.04 + index,
                    }
                    if scenario
                    in {
                        "create_edge",
                        "remove_edge",
                        "delete_node_with_incident_edges",
                        "undo_redo",
                    }
                    else {},
                    "setup_dirty_node_count": 2
                    if scenario
                    in {
                        "create_edge",
                        "remove_edge",
                        "delete_node_with_incident_edges",
                    }
                    else (1 if scenario == "undo_redo" else 0),
                    "setup_dirty_edge_count": 1
                    if scenario
                    in {
                        "remove_edge",
                        "delete_node_with_incident_edges",
                    }
                    else 0,
                    "fixture_checksum_sha256": fixture_checksum_sha256,
                    "graph_size": {"nodes": 12, "edges": 20},
                    "dirty_node_count": 1,
                    "dirty_edge_count": 1,
                    "model_delta_dirty_node_count": 1,
                    "model_delta_dirty_edge_count": 1,
                    "scene_publication_dirty_node_count": 1,
                    "scene_publication_dirty_edge_count": 1,
                    "scene_publication_paths": ["targeted_node_payload"],
                    "mutation_counters": {
                        "payload_cache_rebuild_indexes": 1,
                        "visible_model_delta_fallback": 1,
                    },
                    "mutation_counter_reasons": {
                        "visible_model_delta_fallback": {
                            "visibility_may_change": 1,
                        },
                    },
                    "command_payload_bytes": 32,
                    "graph_delta_payload_bytes": 64,
                    "scene_payload_bytes": 128,
                    "first_frame_after_mutation_ms": 0.9 + index,
                }
            )
        samples = [
            performance_harness._annotate_graph_mutation_phase_attribution(sample)
            for sample in samples
        ]
        return {
            "kind": "graph_canvas_mutation_latency",
            "status": "measured_baseline",
            "threshold_policy": "baseline_evidence_only_no_pass_fail_thresholds",
            "scenario": "graph_mutations",
            "render_path": "ea_node_editor/ui_qml/components/GraphCanvas.qml",
            "uses_actual_canvas_render_path": True,
            "samples_per_scenario": 1,
            "sample_count": len(samples),
            "scenarios": list(performance_harness._MUTATION_BENCHMARK_SCENARIOS),
            "fixture_checksum_sha256": fixture_checksum_sha256,
            "fixture_graph_size": {"nodes": 12, "edges": 20},
            "first_frame_phase_attribution_schema": {
                "version": 1,
                "first_frame_includes_readback": True,
                "completion_semantics": performance_harness._FIRST_FRAME_COMPLETION_SEMANTICS,
                "phase_bucket_semantics": dict(
                    performance_harness._FIRST_FRAME_PHASE_BUCKET_DESCRIPTIONS
                ),
            },
            "samples": samples,
            "scenario_summaries": performance_harness._graph_mutation_scenario_summaries(
                samples
            ),
            "residual_mutation_dirty_blockers": [],
        }

    def _mock_load_benchmark(
        self,
    ) -> performance_harness._ProjectGraphLoadBenchmarkSamples:
        return performance_harness._ProjectGraphLoadBenchmarkSamples(
            phase_samples_ms={
                "project_graph_load_ms": [1.0],
                **{
                    phase_key: [0.1]
                    for phase_key in performance_harness._PROJECT_LOAD_PHASE_KEYS
                },
            }
        )

    def test_graph_mutation_runner_filters_to_create_edge_and_flushes_progress(
        self,
    ) -> None:
        recorded_scenarios: list[str] = []
        fake_scene = SimpleNamespace(
            bind_runtime_history=lambda _history: None,
            clear_mutation_timing_samples=lambda: None,
            set_mutation_timing_enabled=lambda _enabled: None,
        )
        fake_host = SimpleNamespace(scene=fake_scene, close=lambda: None)

        def record_sample(**kwargs) -> dict:
            recorded_scenarios.append(kwargs["scenario"])
            return {"scenario": kwargs["scenario"]}

        with patch.object(performance_harness, "QApplication") as application:
            application.instance.return_value = object()
            with patch.object(
                performance_harness,
                "_GraphCanvasBenchmarkHost",
                return_value=fake_host,
            ):
                with patch.object(
                    performance_harness,
                    "_record_graph_mutation_sample",
                    side_effect=record_sample,
                ):
                    with patch.object(
                        performance_harness,
                        "_graph_mutation_scenario_summaries",
                        return_value={"create_edge": {}},
                    ):
                        with patch.object(
                            performance_harness,
                            "_graph_mutation_dirty_blockers",
                            return_value=[],
                        ):
                            with patch("builtins.print") as print_mock:
                                report = performance_harness.benchmark_graph_mutations_ms(
                                    doc={},
                                    workspace_id="ws_main",
                                    samples=2,
                                    fixture_metadata={"node_count": 12, "edge_count": 20},
                                    scenarios=("create_edge",),
                                )

        self.assertEqual(recorded_scenarios, ["create_edge", "create_edge"])
        self.assertEqual(report["scenarios"], ["create_edge"])
        self.assertEqual(report["sample_count"], 2)
        self.assertIn(
            performance_harness._CREATE_EDGE_MEASUREMENT_LIMITATION,
            report["measurement_limitations"],
        )
        print_mock.assert_called_once_with(
            "progress mutation_scenario=create_edge completed=1/1 samples=2",
            flush=True,
        )

    def test_create_edge_setup_dirties_are_excluded_from_mutation_sample(self) -> None:
        workspace = SimpleNamespace(
            nodes={"seed": SimpleNamespace(node_id="seed", x=0.0, y=0.0)},
            edges={},
        )

        class _FakeTimingScope:
            def __init__(self, scene, scenario):
                self._scene = scene
                self._scenario = scenario

            def __enter__(self):
                self._scene.active_record = {
                    "scenario": self._scenario,
                    "operation_iteration": len(self._scene.records),
                    "mutation_wall_clock_samples_ms": [1.0],
                    "phase_timings_ms": {"command_dispatch_ms": 0.1},
                    "fixture_checksum_sha256": "",
                    "graph_size": {
                        "nodes": len(workspace.nodes),
                        "edges": len(workspace.edges),
                    },
                    "dirty_node_count": 0,
                    "dirty_edge_count": 0,
                    "model_delta_dirty_node_count": 0,
                    "model_delta_dirty_edge_count": 0,
                    "scene_publication_dirty_node_count": 0,
                    "scene_publication_dirty_edge_count": 0,
                    "scene_publication_paths": [],
                    "mutation_counters": {},
                    "mutation_counter_reasons": {},
                    "command_payload_bytes": 1,
                    "graph_delta_payload_bytes": 0,
                    "scene_payload_bytes": 0,
                    "first_frame_after_mutation_ms": 0.1,
                }
                return self

            def __exit__(self, exc_type, exc, tb):
                record = dict(self._scene.active_record)
                record["graph_size"] = {
                    "nodes": len(workspace.nodes),
                    "edges": len(workspace.edges),
                }
                self._scene.records.append(record)
                self._scene.active_record = None
                return False

        class _FakeScene:
            def __init__(self):
                self.records = []
                self.active_record = None
                self.events = []
                self._next_node_index = 0
                self._next_edge_index = 0

            def mutation_timing_samples(self):
                return [dict(record) for record in self.records]

            def mutation_timing_scope(self, scenario, **_kwargs):
                return _FakeTimingScope(self, scenario)

            def add_node_from_type(self, _node_type, x, y):
                scenario = self.active_record["scenario"] if self.active_record else ""
                self.events.append(("add_node", scenario))
                node_id = f"setup_node_{self._next_node_index}"
                self._next_node_index += 1
                workspace.nodes[node_id] = SimpleNamespace(node_id=node_id, x=x, y=y)
                if self.active_record is not None:
                    self.active_record["dirty_node_count"] += 1
                return node_id

            def add_edge(self, source_id, _source_port, target_id, _target_port):
                scenario = self.active_record["scenario"] if self.active_record else ""
                self.events.append(("add_edge", scenario))
                edge_id = f"edge_{self._next_edge_index}"
                self._next_edge_index += 1
                workspace.edges[edge_id] = SimpleNamespace(
                    edge_id=edge_id,
                    source_node_id=source_id,
                    target_node_id=target_id,
                )
                if self.active_record is not None:
                    self.active_record["dirty_node_count"] += len(
                        {source_id, target_id}
                    )
                    self.active_record["dirty_edge_count"] += 1
                return edge_id

            def record_mutation_payload_metrics(self, **metrics):
                if (
                    self.active_record is not None
                    and metrics.get("graph_delta_payload") is not None
                ):
                    self.active_record["graph_delta_payload_bytes"] = 1

        host = SimpleNamespace(
            scene=_FakeScene(),
            model=SimpleNamespace(
                project=SimpleNamespace(workspaces={"ws": workspace})
            ),
            canvas_state_bridge=SimpleNamespace(
                force_visible_scene_models_exact=lambda: None
            ),
            app=SimpleNamespace(processEvents=lambda: None),
            render_frame=lambda: None,
        )

        sample = performance_harness._record_graph_mutation_sample(
            canvas_host=host,
            history=SimpleNamespace(),
            workspace_id="ws",
            scenario="create_edge",
            sample_index=0,
            operation_iteration=0,
            fixture_checksum_sha256="",
        )

        self.assertEqual(
            host.scene.events,
            [
                ("add_node", "create_edge_setup"),
                ("add_node", "create_edge_setup"),
                ("add_edge", "create_edge"),
            ],
        )
        self.assertTrue(sample["setup_excluded_from_mutation_timing"])
        self.assertEqual(sample["setup_dirty_node_count"], 2)
        self.assertEqual(sample["setup_dirty_edge_count"], 0)
        self.assertEqual(sample["dirty_node_count"], 2)
        self.assertEqual(sample["dirty_edge_count"], 1)

    def test_undo_redo_operation_uses_production_refresh_path(self) -> None:
        before_node = SimpleNamespace(node_id="node_a", x=0.0, y=0.0, title="Before")
        after_node = SimpleNamespace(node_id="node_a", x=0.0, y=0.0, title="After")
        workspace = SimpleNamespace(nodes={"node_a": after_node}, edges={})
        entry = SimpleNamespace(
            action_type="rename-node",
            before=SimpleNamespace(nodes={"node_a": before_node}, edges={}),
            after=SimpleNamespace(nodes={"node_a": after_node}, edges={}),
        )

        class _FakeScene:
            def __init__(self):
                self.refresh_calls: list[str] = []
                self.phase_calls: list[tuple[str, float]] = []
                self.payload_metrics: list[dict] = []

            def record_mutation_timing_phase(
                self, phase_name: str, elapsed_ms: float
            ) -> None:
                self.phase_calls.append((phase_name, elapsed_ms))

            def record_mutation_payload_metrics(self, **metrics) -> None:
                self.payload_metrics.append(dict(metrics))

            def refresh_workspace_from_model(self, workspace_id: str) -> None:
                self.refresh_calls.append(workspace_id)

        class _FakeHistory:
            def undo_workspace(self, workspace_id: str, target_workspace) -> object:
                target_workspace.nodes = dict(entry.before.nodes)
                return entry

            def redo_workspace(self, workspace_id: str, target_workspace) -> object:
                target_workspace.nodes = dict(entry.after.nodes)
                return entry

        scene = _FakeScene()
        host = SimpleNamespace(
            scene=scene,
            canvas_state_bridge=SimpleNamespace(
                force_visible_scene_models_exact=lambda: None
            ),
            app=SimpleNamespace(processEvents=lambda: None),
            render_frame=lambda: None,
        )

        payload = performance_harness._run_graph_mutation_operation(
            canvas_host=host,
            history=_FakeHistory(),
            workspace_id="ws",
            scenario="undo_redo",
            sample_index=0,
            setup_context={
                "workspace": workspace,
                "selected_ids": ["node_a"],
                "primary_id": "node_a",
                "prepared_title": "After",
            },
        )

        self.assertEqual(scene.refresh_calls, ["ws", "ws"])
        self.assertEqual(payload["undo_applied"], True)
        self.assertEqual(payload["redo_applied"], True)
        self.assertEqual(
            [
                metrics["model_delta_dirty_node_count"]
                for metrics in scene.payload_metrics
            ],
            [1, 1],
        )
        self.assertEqual(
            [
                metrics["model_delta_dirty_edge_count"]
                for metrics in scene.payload_metrics
            ],
            [0, 0],
        )

    def _assert_heavy_media_scenario(self) -> None:
        with patch.object(
            performance_harness._GraphCanvasBenchmarkHost,
            "wait_for_media_surfaces_ready",
            return_value=None,
        ):
            report = run_benchmark(
                BenchmarkConfig(
                    synthetic_graph=SyntheticGraphConfig(
                        node_count=18, edge_count=30, seed=17
                    ),
                    load_iterations=1,
                    interaction_samples=1,
                    interaction_warmup_samples=0,
                    scenario="heavy_media",
                )
            )

        config = report["config"]
        interaction_benchmark = report["interaction_benchmark"]
        feature_parity = report["feature_parity"]
        scenario_details = config["scenario_details"]
        node_mix = scenario_details["node_mix"]

        self.assertEqual(config["scenario"], "heavy_media")
        self.assertEqual(
            scenario_details["fixture_strategy"], "generated_local_media_reuse"
        )
        self.assertGreater(node_mix["image_source_nodes"], 0)
        self.assertGreater(node_mix["pdf_source_nodes"], 0)
        self.assertEqual(
            node_mix["execution_nodes"]
            + node_mix["media_panel_nodes"],
            18,
        )
        self.assertEqual(
            scenario_details["expected_media_surface_count"],
            node_mix["media_panel_nodes"],
        )
        self.assertEqual(interaction_benchmark["scenario"], "heavy_media")
        self.assertEqual(
            interaction_benchmark["media_surface_count"],
            scenario_details["expected_media_surface_count"],
        )
        self.assertEqual(
            feature_parity["embedded_media_count"],
            scenario_details["expected_media_surface_count"],
        )
        self.assertEqual(
            feature_parity["expected_embedded_media_count"],
            scenario_details["expected_media_surface_count"],
        )
        self.assertTrue(interaction_benchmark["uses_actual_canvas_render_path"])
        self.assertTrue(feature_parity["pass"])
        self.assertTrue(feature_parity["zero_loss_enforced"])

    def test_ui_perf_harness_is_the_canonical_import_path(self) -> None:
        self.assertIs(run_benchmark, performance_harness.run_benchmark)
        self.assertEqual(
            run_benchmark.__module__,
            "ea_node_editor.ui.perf.performance_harness",
        )
        self.assertIsNone(
            importlib.util.find_spec("ea_node_editor.telemetry.performance_harness")
        )
        harness_text = Path(performance_harness.__file__).read_text(encoding="utf-8")
        self.assertNotIn("ea_node_editor.telemetry.performance_harness", harness_text)

    def test_perf_harness_and_stress_fixture_use_only_dataflow_control(self) -> None:
        harness_text = Path(performance_harness.__file__).read_text(encoding="utf-8")
        fixture_path = (
            Path(__file__).resolve().parents[1]
            / "examples"
            / "stress_1200_nodes.cxproj"
        )
        fixture_text = fixture_path.read_text(encoding="utf-8")
        retired_tokens = (
            "core.start",
            "core.end",
            "core.branch",
            "core.on_failure",
            "hpc.on_status",
            '"exec_in"',
            '"exec_out"',
            '"failed_in"',
            '"failed_out"',
            '"completed_in"',
            '"completed_out"',
            "execution_flash_scoped_refresh_count",
            "execution_visualization_active",
            "_executionVisualizationActive",
            "profileExecutionFlashScopedRefreshCount",
        )

        for token in retired_tokens:
            self.assertNotIn(token, harness_text)
            self.assertNotIn(token, fixture_text)

        fixture_doc = json.loads(fixture_text)
        self.assertEqual(fixture_doc["schema_version"], 5)
        fixture_edges = fixture_doc["workspaces"][0]["edges"]
        self.assertTrue(all(edge["enabled"] is True for edge in fixture_edges))
        self.assertTrue(all(edge["input_order"] == 0 for edge in fixture_edges))

    def test_ui_perf_harness_keeps_extracted_interaction_and_baseline_helpers(
        self,
    ) -> None:
        harness_text = Path(performance_harness.__file__).read_text(encoding="utf-8")

        self.assertIn("class _InteractionBenchmarkSamples:", harness_text)
        self.assertIn("def _baseline_series_run(", harness_text)
        self.assertIn("def _baseline_metric_series(", harness_text)
        self.assertIn("def _baseline_series_payload(", harness_text)

    def test_canonical_perf_module_has_direct_module_entrypoint(self) -> None:
        harness_text = Path(performance_harness.__file__).read_text(encoding="utf-8")

        self.assertIn('if __name__ == "__main__":', harness_text)
        self.assertIn("def _run_cli() -> None:", harness_text)
        self.assertIn("os._exit(exit_code)", harness_text)
        self.assertIn("_run_cli()", harness_text)

    def test_generate_synthetic_project_hits_target_scale(self) -> None:
        project = generate_synthetic_project(
            SyntheticGraphConfig(node_count=1000, edge_count=5000, seed=42)
        )
        workspace = project.workspaces[project.active_workspace_id]

        self.assertEqual(len(workspace.nodes), 1000)
        self.assertEqual(len(workspace.edges), 5000)
        self.assertEqual(
            {node.type_id for node in workspace.nodes.values()},
            {"core.python_script"},
        )

        node_indexes = {node_id: index for index, node_id in enumerate(workspace.nodes)}
        input_orders: dict[tuple[str, str], list[int]] = {}
        for edge in workspace.edges.values():
            self.assertEqual(edge.source_port_key, "result")
            self.assertEqual(edge.target_port_key, "payload")
            self.assertTrue(edge.enabled)
            self.assertLess(
                node_indexes[edge.source_node_id],
                node_indexes[edge.target_node_id],
            )
            input_key = (edge.target_node_id, edge.target_port_key)
            input_orders.setdefault(input_key, []).append(edge.input_order)
        for orders in input_orders.values():
            self.assertEqual(orders, list(range(len(orders))))

    def test_benchmark_runner_reports_expected_metric_shapes(self) -> None:
        report = run_benchmark(
            BenchmarkConfig(
                synthetic_graph=SyntheticGraphConfig(
                    node_count=80, edge_count=220, seed=7
                ),
                load_iterations=2,
                interaction_samples=8,
                interaction_warmup_samples=1,
            )
        )

        load_samples = report["metrics"]["project_graph_load_ms"]["samples"]
        pan_samples = report["metrics"]["pan_interaction_ms"]["samples"]
        zoom_samples = report["metrics"]["zoom_interaction_ms"]["samples"]
        combined_samples = report["metrics"]["pan_zoom_combined_ms"]["samples"]
        node_drag_control_samples = report["metrics"]["node_drag_control_ms"]["samples"]
        node_drag_first_offset_samples = report["metrics"]["node_drag_first_offset_ms"][
            "samples"
        ]
        node_drag_steady_offset_samples = report["metrics"][
            "node_drag_steady_offset_ms"
        ]["samples"]
        node_drag_full_gesture_samples = report["metrics"]["node_drag_full_gesture_ms"][
            "samples"
        ]
        node_drag_end_clear_samples = report["metrics"]["node_drag_end_clear_ms"][
            "samples"
        ]
        frame_interval_samples = report["metrics"][
            "frame_interval_ms_without_readback"
        ]["samples"]
        interaction_benchmark = report["interaction_benchmark"]
        supplemental_selected_drag = report["supplemental_selected_drag"]
        renderer_diagnostics = report["renderer_diagnostics"]
        display_diagnostics = report["display_diagnostics"]
        packet_verification_result = report["packet_verification_result"]
        performance_acceptance_result = report["performance_acceptance_result"]
        feature_parity = report["feature_parity"]
        phase_timings = report["phase_timings_ms"]
        stress_breakdown = report["stress_1200_bottleneck_breakdown"]
        mutation_contract = report["mutation_benchmark_contract"]
        mutation_instrumentation = report["mutation_phase_instrumentation"]

        self.assertEqual(len(load_samples), 2)
        self.assertEqual(len(pan_samples), 8)
        self.assertEqual(len(zoom_samples), 8)
        self.assertEqual(len(combined_samples), 8)
        self.assertEqual(len(node_drag_control_samples), 8)
        self.assertEqual(len(node_drag_first_offset_samples), 8)
        self.assertEqual(len(node_drag_steady_offset_samples), 8 * 11)
        self.assertEqual(len(node_drag_full_gesture_samples), 8)
        self.assertEqual(len(node_drag_end_clear_samples), 8)
        self.assertEqual(
            report["interaction_benchmark"]["node_drag_gesture_offset_count"], 12
        )
        self.assertTrue(report["interaction_benchmark"]["membership_freeze_supported"])
        self.assertEqual(
            report["interaction_benchmark"]["node_drag_membership_freezes_per_gesture"],
            1,
        )
        self.assertEqual(
            report["interaction_benchmark"]["node_drag_membership_freeze_counts"],
            [1] * 8,
        )
        self.assertTrue(
            report["interaction_benchmark"]["node_drag_membership_freeze_verified"]
        )
        self.assertEqual(
            report["interaction_benchmark"]["node_drag_steady_state_gate_metric"],
            "node_drag_steady_offset_ms",
        )
        self.assertEqual(
            report["interaction_benchmark"]["node_drag_legacy_continuity_metric"],
            "node_drag_control_ms",
        )
        self.assertTrue(supplemental_selected_drag["supported"])
        self.assertTrue(supplemental_selected_drag["supplemental_only"])
        self.assertTrue(supplemental_selected_drag["formal_gate_metrics_unchanged"])
        self.assertEqual(len(supplemental_selected_drag["selected_node_ids"]), 3)
        self.assertEqual(supplemental_selected_drag["expected_membership_size"], 3)
        self.assertEqual(
            supplemental_selected_drag["membership_size"]["samples"], [3] * 8
        )
        self.assertTrue(supplemental_selected_drag["membership_size"]["verified"])
        self.assertEqual(
            supplemental_selected_drag["membership_freeze"]["samples"], [1] * 8
        )
        self.assertTrue(supplemental_selected_drag["membership_freeze"]["verified"])
        self.assertEqual(
            supplemental_selected_drag["raw_input_count"]["samples"], [12] * 8
        )
        self.assertTrue(supplemental_selected_drag["flushed_update_count"]["supported"])
        self.assertTrue(supplemental_selected_drag["incident_edge_count"]["supported"])
        self.assertEqual(
            len(supplemental_selected_drag["metrics"]["first_offset_ms"]["samples"]),
            8,
        )
        self.assertEqual(
            len(supplemental_selected_drag["metrics"]["steady_offset_ms"]["samples"]),
            8 * 11,
        )
        self.assertEqual(
            len(
                supplemental_selected_drag["render_phase_timings_ms"][
                    "selected_drag_readback_grab_ms"
                ]["samples"]
            ),
            8,
        )
        self.assertEqual(
            len(supplemental_selected_drag["frame_timestamp_ranges"]["selected_drag"]),
            8,
        )
        self.assertEqual(
            len(interaction_benchmark["frame_timestamp_ranges"]["single_drag"]), 8
        )
        self.assertEqual(
            len(interaction_benchmark["frame_timestamp_ranges"]["single_clear"]), 8
        )
        self.assertEqual(len(interaction_benchmark["frame_timestamp_ranges"]["pan"]), 8)
        self.assertEqual(
            len(interaction_benchmark["frame_timestamp_ranges"]["zoom"]), 8
        )
        self.assertIsInstance(frame_interval_samples, list)
        self.assertEqual(report["config"]["interaction_warmup_samples"], 1)
        self.assertEqual(len(phase_timings["project_graph_load_ms"]["samples"]), 2)
        for phase_key in performance_harness._PROJECT_LOAD_PHASE_KEYS:
            self.assertEqual(len(phase_timings[phase_key]["samples"]), 2)
        self.assertEqual(len(phase_timings["canvas_setup_ms"]["samples"]), 1)
        for phase_key in performance_harness._CANVAS_SETUP_PHASE_KEYS:
            self.assertEqual(len(phase_timings[phase_key]["samples"]), 1)
        self.assertEqual(len(phase_timings["canvas_warmup_ms"]["samples"]), 1)
        self.assertEqual(len(phase_timings["pan_interaction_ms"]["samples"]), 8)
        self.assertEqual(len(phase_timings["zoom_interaction_ms"]["samples"]), 8)
        self.assertEqual(len(phase_timings["node_drag_control_ms"]["samples"]), 8)
        self.assertEqual(len(phase_timings["node_drag_first_offset_ms"]["samples"]), 8)
        self.assertEqual(
            len(phase_timings["node_drag_steady_offset_ms"]["samples"]), 8 * 11
        )
        self.assertEqual(len(phase_timings["node_drag_full_gesture_ms"]["samples"]), 8)
        self.assertEqual(len(phase_timings["node_drag_end_clear_ms"]["samples"]), 8)
        self.assertEqual(
            phase_timings["frame_interval_ms_without_readback"]["samples"],
            frame_interval_samples,
        )
        self.assertIn("pan_grid_paint_ms", phase_timings)
        self.assertIn("zoom_overlay_sync_ms", phase_timings)
        self.assertIn("pan_visible_model_query_ms", phase_timings)
        self.assertIn("zoom_edge_paint_ms", phase_timings)
        self.assertIn(
            "pan_frame_scheduler_coalesced_redraw_request_count",
            report["profiling_counts"],
        )
        self.assertIn(
            "pan_edge_spatial_index_query_cache_hit_count", report["profiling_counts"]
        )
        self.assertIn("pan_retained_model_entry_skip_count", report["profiling_counts"])
        self.assertIn(
            "pan_flow_label_model_sync_skip_count", report["profiling_counts"]
        )
        self.assertIn("pan_delegate_create_count", report["profiling_counts"])
        self.assertIn("zoom_live_drag_offset_update_count", report["profiling_counts"])
        self.assertEqual(
            mutation_contract["scenarios"],
            list(performance_harness._MUTATION_BENCHMARK_SCENARIOS),
        )
        self.assertEqual(mutation_contract["kind"], "graph_canvas_mutation_latency")
        self.assertEqual(mutation_contract["status"], "contract_only")
        self.assertEqual(
            mutation_contract["threshold_policy"],
            "baseline_evidence_only_no_pass_fail_thresholds",
        )
        self.assertNotIn("thresholds", mutation_contract)
        mutation_fields = set(mutation_contract["required_report_fields"])
        self.assertTrue(
            {
                "scenario",
                "mutation_wall_clock_samples_ms",
                "phase_timings_ms",
                "first_frame_phase_attribution_ms",
                "first_frame_phase_attribution_ratio",
                "first_frame_includes_readback",
                "first_frame_completion_semantics",
                "setup_excluded_from_mutation_timing",
                "setup_wall_clock_samples_ms",
                "setup_phase_timings_ms",
                "setup_dirty_node_count",
                "setup_dirty_edge_count",
                "fixture_checksum_sha256",
                "graph_size",
                "dirty_node_count",
                "dirty_edge_count",
                "model_delta_dirty_node_count",
                "model_delta_dirty_edge_count",
                "scene_publication_dirty_node_count",
                "scene_publication_dirty_edge_count",
                "scene_publication_paths",
                "mutation_counters",
                "mutation_counter_reasons",
                "command_payload_bytes",
                "graph_delta_payload_bytes",
                "scene_payload_bytes",
                "first_frame_after_mutation_ms",
            }.issubset(mutation_fields)
        )
        self.assertEqual(
            mutation_instrumentation["kind"], "graph_canvas_mutation_latency"
        )
        self.assertEqual(
            mutation_instrumentation["status"], "instrumentation_hooks_available"
        )
        self.assertEqual(mutation_instrumentation["sample_count"], 1)
        self.assertEqual(
            mutation_instrumentation["samples"][0]["scenario"], "rename_node"
        )
        sample = mutation_instrumentation["samples"][0]
        self.assertGreaterEqual(sample["dirty_node_count"], 0)
        self.assertGreaterEqual(sample["dirty_edge_count"], 0)
        self.assertGreaterEqual(sample["model_delta_dirty_node_count"], 0)
        self.assertGreaterEqual(sample["model_delta_dirty_edge_count"], 0)
        self.assertGreaterEqual(sample["scene_publication_dirty_node_count"], 0)
        self.assertGreaterEqual(sample["scene_publication_dirty_edge_count"], 0)
        self.assertIsInstance(sample["scene_publication_paths"], list)
        self.assertIsInstance(sample["mutation_counters"], dict)
        self.assertIsInstance(sample["mutation_counter_reasons"], dict)
        self.assertTrue(sample["setup_excluded_from_mutation_timing"])
        self.assertIsInstance(sample["setup_wall_clock_samples_ms"], list)
        self.assertIsInstance(sample["setup_phase_timings_ms"], dict)
        self.assertGreaterEqual(sample["setup_dirty_node_count"], 0)
        self.assertGreaterEqual(sample["setup_dirty_edge_count"], 0)
        self.assertGreaterEqual(sample["command_payload_bytes"], 0)
        self.assertGreaterEqual(sample["graph_delta_payload_bytes"], 0)
        self.assertGreaterEqual(sample["scene_payload_bytes"], 0)
        self.assertGreaterEqual(sample["first_frame_after_mutation_ms"], 0.0)
        self.assertTrue(sample["first_frame_includes_readback"])
        self.assertIsInstance(sample["first_frame_completion_semantics"], str)
        self.assertIn("readback", sample["first_frame_completion_semantics"])
        self.assertIn("readback_grab_ms", sample["first_frame_phase_attribution_ms"])
        self.assertIn("readback_grab_ms", sample["first_frame_phase_attribution_ratio"])
        for ratio in sample["first_frame_phase_attribution_ratio"].values():
            self.assertGreaterEqual(ratio, 0.0)
            self.assertLessEqual(ratio, 1.0)
        self.assertGreaterEqual(sample["graph_size"]["nodes"], 0)
        self.assertGreaterEqual(sample["graph_size"]["edges"], 0)
        for phase_key in (
            "command_dispatch_ms",
            "history_capture_ms",
            "history_apply_ms",
            "graph_model_mutation_ms",
            "payload_rebuild_ms",
            "scene_publish_ms",
            "visible_node_model_update_ms",
            "harness_force_exact_refresh_ms",
            "qt_event_drain_ms",
            "edge_payload_update_ms",
            "render_callback_wait_ms",
            "readback_grab_ms",
            "post_readback_event_drain_ms",
            "first_frame_after_mutation_ms",
        ):
            self.assertIn(phase_key, sample["phase_timings_ms"])
            self.assertGreaterEqual(sample["phase_timings_ms"][phase_key], 0.0)
        self.assertEqual(
            stress_breakdown["section_name"],
            "Stress 1200 Bottleneck Breakdown",
        )
        self.assertIn("backend_state", stress_breakdown)
        self.assertIn("qml_host_kind", stress_breakdown["backend_state"])
        self.assertIn("qml_host_env", stress_breakdown["backend_state"])
        self.assertIn("qsg_rhi_backend_override", stress_breakdown["backend_state"])
        self.assertIn("next_measured_bottleneck", stress_breakdown)
        breakdown_metrics = {
            metric["metric_key"]: metric
            for group in stress_breakdown["groups"]
            for metric in group["metrics"]
        }
        for metric_key in (
            "pan_visible_model_query_ms",
            "zoom_edge_paint_ms",
            "pan_grid_update_ms",
            "zoom_grid_paint_ms",
            "pan_frame_scheduler_view_state_redraw_request_count",
            "zoom_frame_scheduler_edge_redraw_request_count",
            "pan_delegate_create_count",
            "zoom_delegate_destroy_count",
            "pan_live_drag_offset_update_count",
        ):
            self.assertIn(metric_key, breakdown_metrics)
            metric = breakdown_metrics[metric_key]
            if metric["available"]:
                self.assertIsInstance(metric["value"], float)
            else:
                self.assertTrue(metric["unavailable_reason"])

        self.assertGreaterEqual(
            report["metrics"]["project_graph_load_ms"]["summary"]["p95"], 0.0
        )
        self.assertGreaterEqual(
            report["metrics"]["pan_zoom_combined_ms"]["summary"]["p95"], 0.0
        )
        self.assertGreaterEqual(
            report["metrics"]["node_drag_control_ms"]["summary"]["p95"], 0.0
        )
        self.assertGreaterEqual(
            report["metrics"]["node_drag_first_offset_ms"]["summary"]["p95"], 0.0
        )
        self.assertGreaterEqual(
            report["metrics"]["node_drag_steady_offset_ms"]["summary"]["p95"], 0.0
        )
        self.assertGreaterEqual(
            report["metrics"]["node_drag_full_gesture_ms"]["summary"]["p95"], 0.0
        )
        self.assertGreaterEqual(
            report["metrics"]["node_drag_end_clear_ms"]["summary"]["p95"], 0.0
        )
        self.assertGreaterEqual(
            report["metrics"]["frame_interval_ms_without_readback"]["summary"]["p95"],
            0.0,
        )
        self.assertEqual(report["config"]["scenario"], "synthetic_exec")
        self.assertEqual(
            report["config"]["scenario_details"]["node_mix"]["media_panel_nodes"], 0
        )
        self.assertEqual(
            report["config"]["scenario_details"]["node_mix"]["pdf_source_nodes"], 0
        )
        self.assertEqual(interaction_benchmark["kind"], "graph_canvas_qml")
        self.assertEqual(
            interaction_benchmark["render_path"],
            "ea_node_editor/ui_qml/components/GraphCanvas.qml",
        )
        self.assertEqual(
            interaction_benchmark["viewport"], {"width": 1280, "height": 720}
        )
        self.assertTrue(interaction_benchmark["uses_actual_canvas_render_path"])
        self.assertTrue(interaction_benchmark["steady_state_canvas_host_reused"])
        self.assertEqual(interaction_benchmark["warmup_samples"], 1)
        self.assertEqual(interaction_benchmark["scenario"], "synthetic_exec")
        self.assertEqual(interaction_benchmark["media_surface_count"], 0)
        self.assertIn("frame readback", interaction_benchmark["measurement_driver"])
        self.assertTrue(interaction_benchmark["grab_window_readback_included"])
        self.assertEqual(
            interaction_benchmark["frame_interval_metric"],
            "frame_interval_ms_without_readback",
        )
        self.assertEqual(renderer_diagnostics["qml_host_kind"], "qquickwidget")
        self.assertIn("qml_host_env", renderer_diagnostics)
        self.assertIn("qml_host_kind_selected", renderer_diagnostics)
        self.assertIn("graphics_api", renderer_diagnostics)
        self.assertIn("graphics_api_label", renderer_diagnostics)
        self.assertIn("qt_version", renderer_diagnostics)
        self.assertIn("qsg_render_loop", renderer_diagnostics)
        self.assertIn("qsg_rhi_backend_override", renderer_diagnostics)
        self.assertIn("qtquick_backend_selected", renderer_diagnostics)
        self.assertIn("qtquick_backend_selection_reason", renderer_diagnostics)
        self.assertIn("qtquick_backend_forced_software", renderer_diagnostics)
        self.assertIn("screen_device_pixel_ratio", renderer_diagnostics)
        self.assertIn("window_effective_device_pixel_ratio", renderer_diagnostics)
        self.assertTrue(renderer_diagnostics["grab_window_readback_included"])
        self.assertIn("qsg_rhi_backend_override", report["environment"])
        self.assertIn("qml_host_env", report["environment"])
        self.assertIn("qml_host_kind_selected", report["environment"])
        self.assertIn("qtquick_backend_selection_reason", report["environment"])
        self.assertEqual(display_diagnostics["qt_platform"], "offscreen")
        self.assertFalse(display_diagnostics["display_attached"])
        self.assertIn("active_graphics_api", display_diagnostics)
        self.assertIn("rhi_backend", display_diagnostics)
        self.assertIn("render_loop", display_diagnostics)
        self.assertEqual(
            display_diagnostics["host_kind"], renderer_diagnostics["qml_host_kind"]
        )
        self.assertIn("screen_device_pixel_ratio", display_diagnostics)
        self.assertIn("window_effective_device_pixel_ratio", display_diagnostics)
        self.assertIn("software_fallback_active", display_diagnostics)
        self.assertTrue(display_diagnostics["readback_included"])
        self.assertFalse(display_diagnostics["acceptance_allowed"])
        self.assertEqual(packet_verification_result["status"], "PASS")
        self.assertEqual(performance_acceptance_result["status"], "FAIL")
        self.assertIn("GRAPH-CANVAS-DISPLAY-ATTACHED", report["requirements_eval"])
        self.assertFalse(
            report["requirements_eval"]["GRAPH-CANVAS-DISPLAY-ATTACHED"]["pass"]
        )
        self.assertTrue(feature_parity["pass"])
        self.assertTrue(feature_parity["zero_loss_enforced"])
        self.assertTrue(feature_parity["show_grid"])
        self.assertTrue(feature_parity["minimap_visible"])
        self.assertTrue(feature_parity["node_shadows_enabled"])
        self.assertTrue(feature_parity["notched_ports_enabled"])
        self.assertTrue(feature_parity["port_labels_visible"])
        self.assertIn("edge_crossing_style", feature_parity)
        self.assertEqual(feature_parity["expected_embedded_media_count"], 0)

    def test_project_fixture_loads_serializer_project_and_reports_fixture_metadata(
        self,
    ) -> None:
        project = generate_synthetic_project(
            SyntheticGraphConfig(node_count=12, edge_count=20, seed=23)
        )
        serializer = JsonProjectSerializer(build_default_registry())

        with tempfile.TemporaryDirectory() as temp_dir:
            fixture_path = Path(temp_dir) / "small_fixture.cxproj"
            serializer.save(str(fixture_path), project)
            loaded_workspace = serializer.load(str(fixture_path)).workspaces[
                "ws_perf_h"
            ]

            with patch.object(
                performance_harness,
                "benchmark_project_graph_load_ms",
                return_value=self._mock_load_benchmark(),
            ) as load_benchmark:
                with patch.object(
                    performance_harness,
                    "benchmark_pan_zoom_ms",
                    return_value=self._mock_interaction_samples(),
                ):
                    report = performance_harness._run_single_benchmark(
                        BenchmarkConfig(
                            synthetic_graph=SyntheticGraphConfig(
                                node_count=3, edge_count=2
                            ),
                            load_iterations=1,
                            interaction_samples=1,
                            interaction_warmup_samples=0,
                            project_path=str(fixture_path),
                            workspace_id="ws_perf_h",
                        )
                    )

        load_benchmark.assert_called_once()
        self.assertEqual(load_benchmark.call_args.kwargs["workspace_id"], "ws_perf_h")
        self.assertEqual(report["config"]["scenario"], "project_fixture")
        self.assertEqual(report["config"]["workspace_id"], "ws_perf_h")
        fixture = report["fixture_metadata"]
        self.assertEqual(fixture["fixture_source_kind"], "project")
        self.assertEqual(
            fixture["fixture_acceptance_scope"], "project_fixture_regression"
        )
        self.assertFalse(fixture["display_acceptance_eligible"])
        self.assertTrue(fixture["project_path_exists"])
        self.assertRegex(fixture["fixture_checksum_sha256"], r"^[0-9a-f]{64}$")
        self.assertEqual(fixture["workspace_id"], "ws_perf_h")
        self.assertEqual(fixture["node_count"], 12)
        self.assertEqual(fixture["edge_count"], len(loaded_workspace.edges))
        self.assertEqual(fixture["node_type_histogram"]["core.python_script"], 12)
        self.assertEqual(fixture["active_graphics_api"], "Software")
        self.assertEqual(fixture["qml_host_kind"], "qquickwidget")
        self.assertIn("qml_host_env", fixture["qt_scenegraph_environment"])
        self.assertIn("qml_host_kind_selected", fixture["qt_scenegraph_environment"])
        self.assertTrue(fixture["grab_window_readback_included"])
        self.assertEqual(report["display_diagnostics"]["qt_platform"], "offscreen")
        self.assertFalse(report["display_diagnostics"]["acceptance_allowed"])
        self.assertEqual(report["packet_verification_result"]["status"], "PASS")
        self.assertEqual(report["performance_acceptance_result"]["status"], "FAIL")

    def test_real_stress_fixture_mode_targets_default_path_and_workspace(self) -> None:
        with performance_harness._build_scenario_project(
            BenchmarkConfig(stress_fixture="real")
        ) as scenario_project:
            fixture = scenario_project.scenario_details["fixture_metadata"]
            workspace = scenario_project.project.workspaces[
                scenario_project.workspace_id
            ]

        self.assertEqual(scenario_project.workspace_id, "ws_perf_h")
        self.assertEqual(fixture["fixture_source_kind"], "real")
        self.assertEqual(fixture["fixture_acceptance_scope"], "real_fixture_baseline")
        self.assertTrue(fixture["display_acceptance_eligible"])
        self.assertEqual(fixture["project_path"], "examples/stress_1200_nodes.cxproj")
        self.assertEqual(fixture["workspace_id"], "ws_perf_h")
        self.assertEqual(fixture["fixture_strategy"], "serializer_project_load")
        self.assertTrue(fixture["project_path_exists"])
        self.assertRegex(fixture["project_sha256"], r"^[0-9a-f]{64}$")
        self.assertEqual(fixture["fixture_checksum_sha256"], fixture["project_sha256"])
        self.assertTrue(
            str(fixture["effective_project_path"]).endswith("stress_1200_nodes.cxproj")
        )
        self.assertEqual(fixture["node_count"], 1200)
        self.assertEqual(fixture["edge_count"], 1199)
        self.assertEqual(
            {node.type_id for node in workspace.nodes.values()},
            {"core.python_script"},
        )
        self.assertTrue(
            all(
                edge.source_port_key == "result"
                and edge.target_port_key == "payload"
                and edge.enabled
                and edge.input_order == 0
                for edge in workspace.edges.values()
            )
        )

    def test_real_stress_fixture_mode_fails_when_canonical_fixture_is_absent(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            missing_path = Path(temp_dir) / "missing_stress_1200_nodes.cxproj"
            with patch.object(
                performance_harness,
                "_default_stress_fixture_path",
                return_value=missing_path,
            ):
                with self.assertRaisesRegex(
                    FileNotFoundError, "Real stress fixture not found"
                ):
                    performance_harness._build_scenario_project(
                        BenchmarkConfig(stress_fixture="real")
                    )

    def test_stress_fixture_cli_requires_explicit_real_mode(self) -> None:
        args = performance_harness._parse_args(["--stress-fixture", "real"])
        self.assertEqual(args.stress_fixture, "real")

        graph_mutation_args = performance_harness._parse_args(
            ["--scenario", "graph_mutations", "--stress-fixture", "real"]
        )
        self.assertEqual(graph_mutation_args.scenario, "graph_mutations")
        self.assertEqual(graph_mutation_args.stress_fixture, "real")

        with self.assertRaises(SystemExit):
            performance_harness._parse_args(["--stress-fixture"])
        with self.assertRaises(SystemExit):
            performance_harness._parse_args(["--stress-fixture", "generated"])

    def test_graph_mutations_scenario_reports_measured_baseline_contract(self) -> None:
        project = generate_synthetic_project(
            SyntheticGraphConfig(node_count=12, edge_count=20, seed=23)
        )
        serializer = JsonProjectSerializer(build_default_registry())

        with tempfile.TemporaryDirectory() as temp_dir:
            fixture_path = Path(temp_dir) / "small_fixture.cxproj"
            serializer.save(str(fixture_path), project)

            def graph_mutation_payload(**kwargs) -> dict:
                fixture_metadata = kwargs["fixture_metadata"]
                return self._mock_graph_mutation_benchmark(
                    fixture_checksum_sha256=fixture_metadata["fixture_checksum_sha256"]
                )

            with patch.object(
                performance_harness,
                "benchmark_project_graph_load_ms",
                return_value=self._mock_load_benchmark(),
            ):
                with patch.object(
                    performance_harness,
                    "benchmark_pan_zoom_ms",
                    return_value=self._mock_interaction_samples(
                        membership_freeze_supported=False
                    ),
                ):
                    with patch.object(
                        performance_harness,
                        "_mutation_phase_instrumentation_payload",
                        return_value={"status": "instrumentation_hooks_available"},
                    ):
                        with patch.object(
                            performance_harness,
                            "benchmark_graph_mutations_ms",
                            side_effect=graph_mutation_payload,
                        ) as mutation_runner:
                            report = performance_harness._run_single_benchmark(
                                BenchmarkConfig(
                                    synthetic_graph=SyntheticGraphConfig(
                                        node_count=3, edge_count=2
                                    ),
                                    load_iterations=1,
                                    interaction_samples=2,
                                    interaction_warmup_samples=0,
                                    scenario="graph_mutations",
                                    project_path=str(fixture_path),
                                    workspace_id="ws_perf_h",
                                )
                            )

            markdown_path = Path(temp_dir) / "TRACK_H_BENCHMARK_REPORT.md"
            performance_harness._write_markdown_report(report, markdown_path)
            markdown = markdown_path.read_text(encoding="utf-8")

        mutation_runner.assert_called_once()
        self.assertEqual(mutation_runner.call_args.kwargs["samples"], 2)
        self.assertEqual(mutation_runner.call_args.kwargs["scenarios"], ())
        self.assertEqual(report["config"]["scenario"], "graph_mutations")
        self.assertEqual(report["fixture_metadata"]["fixture_source_kind"], "project")
        self.assertRegex(
            report["fixture_metadata"]["fixture_checksum_sha256"], r"^[0-9a-f]{64}$"
        )
        self.assertFalse(report["interaction_benchmark"]["membership_freeze_supported"])
        self.assertIsNone(
            report["interaction_benchmark"]["node_drag_membership_freezes_per_gesture"]
        )
        self.assertEqual(
            report["interaction_benchmark"]["node_drag_membership_freeze_counts"],
            [None],
        )
        self.assertIsNone(
            report["interaction_benchmark"]["node_drag_membership_freeze_verified"]
        )
        self.assertEqual(
            mutation_runner.call_args.kwargs["fixture_metadata"][
                "fixture_checksum_sha256"
            ],
            report["fixture_metadata"]["fixture_checksum_sha256"],
        )
        mutation_benchmark = report["graph_mutation_benchmark"]
        self.assertEqual(mutation_benchmark["status"], "measured_baseline")
        self.assertTrue(mutation_benchmark["uses_actual_canvas_render_path"])
        self.assertIn("residual_mutation_dirty_blockers", mutation_benchmark)
        self.assertEqual(
            mutation_benchmark["fixture_checksum_sha256"],
            report["fixture_metadata"]["fixture_checksum_sha256"],
        )
        for scenario in performance_harness._MUTATION_BENCHMARK_SCENARIOS:
            self.assertIn(scenario, mutation_benchmark["scenario_summaries"])
            self.assertIn(
                "command_dispatch_ms",
                mutation_benchmark["scenario_summaries"][scenario]["phase_timings_ms"],
            )
            self.assertIn(
                "setup_dirty_node_count",
                mutation_benchmark["scenario_summaries"][scenario],
            )
            self.assertIn(
                "dirty_node_count", mutation_benchmark["scenario_summaries"][scenario]
            )
            self.assertIn(
                "model_delta_dirty_node_count",
                mutation_benchmark["scenario_summaries"][scenario],
            )
            self.assertIn(
                "scene_publication_dirty_node_count",
                mutation_benchmark["scenario_summaries"][scenario],
            )
            self.assertIn(
                "scene_publication_paths",
                mutation_benchmark["scenario_summaries"][scenario],
            )
            self.assertIn(
                "mutation_counters", mutation_benchmark["scenario_summaries"][scenario]
            )
            self.assertIn(
                "mutation_counter_reasons",
                mutation_benchmark["scenario_summaries"][scenario],
            )
            self.assertIn(
                "first_frame_phase_attribution_ms",
                mutation_benchmark["scenario_summaries"][scenario],
            )
            self.assertIn(
                "readback_grab_ms",
                mutation_benchmark["scenario_summaries"][scenario][
                    "first_frame_phase_attribution_ms"
                ],
            )
            self.assertTrue(
                mutation_benchmark["scenario_summaries"][scenario][
                    "first_frame_includes_readback"
                ]
            )
        self.assertIn("## Graph Mutation Baseline", markdown)
        self.assertIn("Notched ports enabled:", markdown)
        self.assertIn(
            "Setup dirty counts are captured in a separate setup scope", markdown
        )
        self.assertIn("Scene publish dirty nodes p95", markdown)
        self.assertIn("Mutation Churn Counters", markdown)
        self.assertIn(
            "First-frame phase attribution keeps state-side visible-model publication",
            markdown,
        )
        self.assertIn(
            "Node-drag membership-freeze counter supported: `false`", markdown
        )
        self.assertIn("Node-drag membership-freeze counts: `unsupported`", markdown)
        self.assertIn(
            "Node-drag membership-freeze verification: `unsupported`", markdown
        )
        self.assertIn("First-Frame Phase Attribution", markdown)
        self.assertIn("### `rename_node` Mutation Phase Timings", markdown)
        self.assertIn("baseline_evidence_only_no_pass_fail_thresholds", markdown)
        self.assertIn(
            performance_harness._CREATE_EDGE_MEASUREMENT_LIMITATION,
            report["limitations"],
        )
        self.assertIn(
            performance_harness._CREATE_EDGE_MEASUREMENT_LIMITATION,
            markdown,
        )

    def test_p08_final_mutation_latency_artifact_records_thresholds(self) -> None:
        artifact_path = Path(
            "artifacts/graph_canvas_mutation_latency_final/track_h_benchmark_report.json"
        )
        self.assertTrue(
            artifact_path.exists(), f"Missing P08 final artifact: {artifact_path}"
        )

        report = json.loads(artifact_path.read_text(encoding="utf-8"))
        closeout = report["mutation_closeout_thresholds"]
        graph_mutation_benchmark = report["graph_mutation_benchmark"]

        self.assertEqual(closeout["status"], "PASS")
        self.assertEqual(
            closeout["threshold_policy"],
            "p08_empirical_offscreen_regression_guardrails",
        )
        self.assertEqual(
            set(closeout["scenario_thresholds"]),
            set(performance_harness._MUTATION_BENCHMARK_SCENARIOS),
        )
        self.assertEqual(
            graph_mutation_benchmark["threshold_policy"],
            closeout["threshold_policy"],
        )
        self.assertEqual(
            report["packet_verification_result"]["status"],
            "PASS",
        )
        self.assertEqual(
            report["performance_acceptance_result"]["status"],
            "FAIL",
        )
        self.assertFalse(report["display_diagnostics"]["display_attached"])

        for scenario in performance_harness._MUTATION_BENCHMARK_SCENARIOS:
            result = closeout["scenario_thresholds"][scenario]
            wall_threshold = result["wall_p95_ms_max"]
            first_frame_threshold = result["first_frame_p95_ms_max"]

            self.assertEqual(result["result"], "PASS")
            self.assertGreater(wall_threshold, 0.0)
            self.assertGreater(first_frame_threshold, 0.0)
            self.assertLessEqual(result["observed_wall_p95_ms"], wall_threshold)
            self.assertLessEqual(
                result["observed_first_frame_p95_ms"], first_frame_threshold
            )
            self.assertLess(wall_threshold, result["baseline_wall_p95_ms"])
            self.assertLess(first_frame_threshold, result["baseline_wall_p95_ms"])
            self.assertGreater(result["wall_p95_improvement_vs_p03_baseline_pct"], 0.0)
            self.assertEqual(
                graph_mutation_benchmark["thresholds"][scenario]["wall_p95_ms_max"],
                wall_threshold,
            )
            self.assertEqual(
                graph_mutation_benchmark["thresholds"][scenario][
                    "first_frame_p95_ms_max"
                ],
                first_frame_threshold,
            )
            self.assertGreaterEqual(len(closeout["phase_bottlenecks"][scenario]), 1)

    def test_p05_final_structural_edge_delta_artifact_records_thresholds(self) -> None:
        artifact_path = Path(
            "artifacts/graph_canvas_structural_edge_delta_final/track_h_benchmark_report.json"
        )
        self.assertTrue(
            artifact_path.exists(), f"Missing P05 final artifact: {artifact_path}"
        )

        report = json.loads(artifact_path.read_text(encoding="utf-8"))
        graph_mutation_benchmark = report["graph_mutation_benchmark"]
        scenario_summaries = graph_mutation_benchmark["scenario_summaries"]
        structural_thresholds = {
            "create_edge": 7000.0,
            "remove_edge": 8000.0,
            "delete_node_with_incident_edges": 13000.0,
            "undo_redo": 34000.0,
        }

        self.assertEqual(report["packet_verification_result"]["status"], "PASS")
        self.assertEqual(report["performance_acceptance_result"]["status"], "FAIL")
        self.assertEqual(report["fixture_metadata"]["fixture_source_kind"], "real")
        self.assertFalse(report["display_diagnostics"]["display_attached"])
        self.assertEqual(report["baseline_series"]["run_count"], 3)
        self.assertEqual(graph_mutation_benchmark["sample_count"], 70)

        for scenario, wall_threshold in structural_thresholds.items():
            summary = scenario_summaries[scenario]
            observed_wall = summary["mutation_wall_clock_samples_ms"]["summary"]["p95"]
            observed_first_frame = summary["first_frame_after_mutation_ms"]["summary"][
                "p95"
            ]

            self.assertLessEqual(observed_wall, wall_threshold)
            self.assertLessEqual(observed_first_frame, wall_threshold)
            if scenario == "undo_redo":
                self.assertGreater(
                    summary["dirty_node_count"]["summary"]["p95"], 1000.0
                )
                self.assertGreater(
                    summary["dirty_edge_count"]["summary"]["p95"], 1000.0
                )
            else:
                self.assertLessEqual(summary["dirty_node_count"]["summary"]["p95"], 2.0)
                self.assertLessEqual(summary["dirty_edge_count"]["summary"]["p95"], 1.0)

    def test_p02_final_undo_redo_delta_publication_artifact_records_thresholds(
        self,
    ) -> None:
        artifact_path = Path(
            "artifacts/graph_canvas_undo_redo_delta_publication_final/track_h_benchmark_report.json"
        )
        baseline_path = Path(
            "artifacts/graph_canvas_structural_edge_delta_topology/track_h_benchmark_report.json"
        )
        self.assertTrue(
            artifact_path.exists(), f"Missing P02 final artifact: {artifact_path}"
        )
        self.assertTrue(
            baseline_path.exists(), f"Missing P04 comparison artifact: {baseline_path}"
        )

        report = json.loads(artifact_path.read_text(encoding="utf-8"))
        baseline_report = json.loads(baseline_path.read_text(encoding="utf-8"))
        graph_mutation_benchmark = report["graph_mutation_benchmark"]
        undo_redo = graph_mutation_benchmark["scenario_summaries"]["undo_redo"]
        baseline_undo_redo = baseline_report["graph_mutation_benchmark"][
            "scenario_summaries"
        ]["undo_redo"]

        def p95(summary: dict, field: str) -> float:
            return summary[field]["summary"]["p95"]

        self.assertEqual(report["packet_verification_result"]["status"], "PASS")
        self.assertEqual(report["performance_acceptance_result"]["status"], "FAIL")
        self.assertEqual(report["fixture_metadata"]["fixture_source_kind"], "real")
        self.assertFalse(report["display_diagnostics"]["display_attached"])
        self.assertEqual(report["baseline_series"]["run_count"], 3)
        self.assertEqual(graph_mutation_benchmark["sample_count"], 70)
        self.assertEqual(graph_mutation_benchmark["samples_per_scenario"], 10)
        self.assertEqual(
            graph_mutation_benchmark["residual_mutation_dirty_blockers"], []
        )

        self.assertEqual(
            undo_redo["scene_publication_paths"], ["history_targeted_node_payload"]
        )
        self.assertLessEqual(p95(undo_redo, "model_delta_dirty_node_count"), 5.0)
        self.assertLessEqual(p95(undo_redo, "model_delta_dirty_edge_count"), 5.0)
        self.assertLessEqual(p95(undo_redo, "scene_publication_dirty_node_count"), 5.0)
        self.assertLessEqual(p95(undo_redo, "scene_publication_dirty_edge_count"), 5.0)
        self.assertLessEqual(
            undo_redo["phase_timings_ms"]["payload_rebuild_ms"]["summary"]["p95"],
            5.0,
        )
        self.assertLessEqual(p95(undo_redo, "mutation_wall_clock_samples_ms"), 8000.0)
        self.assertLessEqual(p95(undo_redo, "first_frame_after_mutation_ms"), 8000.0)
        self.assertLessEqual(
            undo_redo["phase_timings_ms"]["scene_publish_ms"]["summary"]["p95"],
            6500.0,
        )

        self.assertGreater(p95(baseline_undo_redo, "dirty_node_count"), 1000.0)
        self.assertGreater(p95(baseline_undo_redo, "dirty_edge_count"), 1000.0)
        self.assertLess(
            p95(undo_redo, "scene_publication_dirty_node_count"),
            p95(baseline_undo_redo, "dirty_node_count"),
        )
        self.assertLess(
            p95(undo_redo, "scene_publication_dirty_edge_count"),
            p95(baseline_undo_redo, "dirty_edge_count"),
        )

    def test_canvas_lag_profiler_exposes_project_fixture_mode(self) -> None:
        from scripts import profile_canvas_lag

        profiler_text = Path("scripts/profile_canvas_lag.py").read_text(
            encoding="utf-8"
        )
        harness_text = Path(performance_harness.__file__).read_text(encoding="utf-8")

        self.assertIn("--stress-fixture", profiler_text)
        self.assertIn('choices=("real",)', profiler_text)
        self.assertIn("--project-path", profiler_text)
        self.assertIn("project_path=args.project_path", profiler_text)
        self.assertIn("stress_fixture=args.stress_fixture", profiler_text)
        self.assertIn(
            'cmd.extend(["--stress-fixture", args.stress_fixture])', profiler_text
        )
        self.assertIn("_build_scenario_project(cfg)", profiler_text)
        self.assertIn("pan_samples_ms.append(pan_step.elapsed_ms)", profiler_text)
        self.assertIn("zoom_samples_ms.append(zoom_step.elapsed_ms)", profiler_text)
        self.assertIn("--capture-qsg-info", profiler_text)
        self.assertIn("QSG_INFO", profiler_text)
        self.assertIn("qsg_info_capture_enabled", profiler_text)
        self.assertIn("--qml-host", profiler_text)
        self.assertIn("--qsg-rhi-backend", profiler_text)
        self.assertIn("EA_NODE_EDITOR_QML_HOST", profiler_text)
        self.assertIn("EA_NODE_EDITOR_QSG_RHI_BACKEND", profiler_text)
        self.assertIn("--engineering-step", profiler_text)
        self.assertIn("root_context_setup=_setup_viewer_context", profiler_text)
        self.assertIn("root_context_setup(self, root_context)", harness_text)
        self.assertIn(
            'renderer_diagnostics["grab_window_readback_included"] = False',
            profiler_text,
        )
        for operation_name in (
            "startup_proxy",
            "proxy_pan_control",
            "proxy_zoom_control",
            "selection_without_activation",
            "hover_without_activation",
            "single_click_without_activation",
            "proxy_double_click_activation",
            "live_wheel_zoom",
            "live_box_zoom",
            "active_viewer_drag",
            "active_viewer_resize",
            "canvas_click_demotion",
            "retained_proxy_pan",
            "retained_proxy_zoom",
            "double_click_reactivation",
            "active_wire_drag",
            "unrelated_property_edit",
            "unrelated_node_add",
            "unrelated_node_delete",
            "unrelated_wire_create",
            "unrelated_wire_reroute",
            "unrelated_wire_delete",
            "viewer_deletion",
        ):
            self.assertIn(f'"{operation_name}"', profiler_text)
        for report_field in (
            "widget_identity",
            "native_overlay_visible",
            "binder_bind",
            "binder_release",
            "binder_render",
            "dataset_load",
            "widget_create",
            "overlay_full_sync",
            "viewer_host_sync",
            "overlay_transform_sync",
            "native_move_calls",
            "native_resize_calls",
            "native_set_geometry_calls",
            "overlay_skipped_delta",
            "cached_preview_available",
            "cached_preview_source",
            "preview_cache_revision",
            "transport_revision",
            "native_updates_enabled",
            "retained_inline_node_id",
            "presentation_hold_count",
            "explicit_inline_active",
            "camera_capture",
            "preview_capture",
            "execution_update",
            "transition_lifecycle_deltas",
            "continuous_lifecycle_deltas",
            "restoration_lifecycle_deltas",
            "engineering_acceptance",
            "release_ready",
            "release_status",
            "coefficients_of_variation",
            "operation_gaps",
            "driver_limitations",
            "warmup_samples_applied",
        ):
            self.assertIn(f'"{report_field}"', profiler_text)
        parsed = profile_canvas_lag._parse_args(
            ["--engineering-step", "part.stp"]
        )
        self.assertEqual(parsed.engineering_step, "part.stp")
        self.assertFalse(hasattr(parsed, "engineering_condition"))
        registry = build_default_registry()
        engineering_project = profile_canvas_lag._build_engineering_project(
            Path("part.stp"), registry
        )
        engineering_workspace = engineering_project.workspaces[
            engineering_project.active_workspace_id
        ]
        self.assertEqual(
            [node.type_id for node in engineering_workspace.nodes.values()],
            [
                "data.panel",
                "engineering.cad_import",
                "model.viewer",
                "data.boolean_toggle",
                "core.constant",
                "core.python_script",
                "core.python_script",
            ],
        )
        self.assertEqual(
            {
                (
                    edge.source_node_id,
                    edge.source_port_key,
                    edge.target_node_id,
                    edge.target_port_key,
                )
                for edge in engineering_workspace.edges.values()
            },
            {
                ("node_canvas_panel", "output", "node_canvas_cad_import", "path"),
                (
                    "node_canvas_cad_import",
                    "scene",
                    "node_canvas_model_viewer",
                    "scene_1",
                ),
            },
        )
        self.assertIn("--capture-qsg-info", harness_text)
        self.assertIn("QSG_INFO", harness_text)

    def _passing_engineering_canvas_report(self) -> dict:
        from scripts import profile_canvas_lag

        zero = {
            "binder_bind": 0,
            "binder_release": 0,
            "binder_render": 0,
            "dataset_load": 0,
            "widget_create": 0,
            "native_move_calls": 0,
            "native_resize_calls": 0,
            "native_set_geometry_calls": 0,
            "overlay_skipped_delta": 0,
            "overlay_full_sync": 0,
            "viewer_host_sync": 0,
        }

        def viewer(
            *,
            live="proxy",
            widget="",
            explicit=False,
            retained="",
            visible=False,
            transport=1,
        ):
            return {
                "live_mode": live,
                "widget_identity": widget,
                "explicit_inline_active": explicit,
                "retained_inline_node_id": retained,
                "transport_revision": transport,
                "native_overlay_visible": visible,
                "native_overlay_geometry_ready": visible,
                "native_updates_enabled": visible,
            }

        operations = []
        for name in profile_canvas_lag._ENGINEERING_OPERATION_ORDER:
            before = viewer()
            after = viewer()
            during = {}
            delta = dict(zero)
            continuous = dict(zero)
            if name == "proxy_double_click_activation":
                after = viewer(live="full", widget="widget-1", explicit=True, visible=True)
                delta.update(
                    binder_bind=1,
                    binder_render=1,
                    dataset_load=1,
                    widget_create=1,
                )
            elif name in {
                "live_wheel_zoom",
                "live_box_zoom",
                "active_viewer_drag",
                "active_viewer_resize",
                "active_wire_drag",
            }:
                before = viewer(live="full", widget="widget-1", explicit=True, visible=True)
                after = dict(before)
                during = viewer(live="full", widget="widget-1", explicit=True)
            elif name == "canvas_click_demotion":
                before = viewer(live="full", widget="widget-1", explicit=True, visible=True)
                after = viewer(
                    widget="widget-1",
                    retained=profile_canvas_lag._ENGINEERING_VIEWER_NODE_ID,
                )
            elif name in {"retained_proxy_pan", "retained_proxy_zoom"}:
                before = viewer(
                    widget="widget-1",
                    retained=profile_canvas_lag._ENGINEERING_VIEWER_NODE_ID,
                )
                after = dict(before)
            elif name == "double_click_reactivation":
                before = viewer(
                    widget="widget-1",
                    retained=profile_canvas_lag._ENGINEERING_VIEWER_NODE_ID,
                )
                after = viewer(live="full", widget="widget-1", explicit=True, visible=True)
            elif name == "unrelated_property_edit":
                before = viewer(live="full", widget="widget-1", explicit=True, visible=True)
                after = dict(before)
                delta["overlay_skipped_delta"] = 1
            elif name == "unrelated_node_add":
                before = viewer(live="full", widget="widget-1", explicit=True, visible=True)
                after = viewer(
                    widget="widget-1",
                    retained=profile_canvas_lag._ENGINEERING_VIEWER_NODE_ID,
                )
                delta["overlay_skipped_delta"] = 1
            elif name in {
                "unrelated_node_delete",
                "unrelated_wire_create",
                "unrelated_wire_reroute",
                "unrelated_wire_delete",
            }:
                before = viewer(
                    widget="widget-1",
                    retained=profile_canvas_lag._ENGINEERING_VIEWER_NODE_ID,
                )
                after = dict(before)
                delta["overlay_skipped_delta"] = 1
            elif name == "viewer_deletion":
                before = viewer(
                    widget="widget-1",
                    retained=profile_canvas_lag._ENGINEERING_VIEWER_NODE_ID,
                )
                after = viewer(transport=0)
                delta["binder_release"] = 1
            operations.append(
                {
                    "operation": name,
                    "status": "measured",
                    "timing_p95_ms": 10.0,
                    "frame_interval_p95_ms": 10.0,
                    "viewer_before": before,
                    "viewer_during": during,
                    "viewer_after": after,
                    "lifecycle_deltas": delta,
                    "continuous_lifecycle_deltas": continuous,
                }
            )

        return {
            "operations": operations,
            "qt_platform": "windows",
            "renderer_diagnostics": {
                "graphics_api": "Direct3D11Rhi",
                "qml_host_kind": "qquickwidget",
                "grab_window_readback_included": False,
            },
            "feature_parity": {"pass": True},
            "grab_window_readback_included": False,
        }

    def test_engineering_canvas_acceptance_accepts_contract_payload(self) -> None:
        from scripts import profile_canvas_lag

        result = profile_canvas_lag._evaluate_engineering_acceptance(
            self._passing_engineering_canvas_report()
        )

        self.assertEqual(result["status"], "PASS", result["failures"])
        self.assertEqual(result["operation_count"], 23)
        self.assertFalse(result["three_run_cv_evaluated"])
        self.assertFalse(result["release_ready"])
        self.assertEqual(result["release_status"], "DIAGNOSTIC_ONLY")

    def test_engineering_canvas_acceptance_rejects_churn_and_missing_phases(self) -> None:
        from scripts import profile_canvas_lag

        result = profile_canvas_lag._evaluate_engineering_acceptance(
            {
                "operations": [
                    {
                        "operation": "startup_proxy",
                        "status": "measured",
                        "viewer_after": {
                            "live_mode": "full",
                            "widget_identity": "unexpected-widget",
                            "explicit_inline_active": True,
                        },
                        "lifecycle_deltas": {
                            "binder_bind": 1,
                            "widget_create": 1,
                        },
                    }
                ]
            }
        )

        self.assertEqual(result["status"], "FAIL")
        self.assertTrue(
            any("operation order mismatch" in failure for failure in result["failures"])
        )
        self.assertTrue(
            any("native widget exists before activation" in failure for failure in result["failures"])
        )

    def test_engineering_canvas_acceptance_collapses_blocked_phase_cascade(self) -> None:
        from scripts import profile_canvas_lag

        operations = []
        for name in profile_canvas_lag._ENGINEERING_OPERATION_ORDER:
            operations.append(
                {
                    "operation": name,
                    "status": "failed" if name == "live_box_zoom" else "blocked",
                    "unavailable_reason": (
                        "root box failure"
                        if name == "live_box_zoom"
                        else "Blocked by prerequisite phase live_box_zoom"
                    ),
                    "derived_from": "" if name == "live_box_zoom" else "live_box_zoom",
                }
            )

        result = profile_canvas_lag._evaluate_engineering_acceptance(
            {"operations": operations}
        )

        self.assertEqual(result["status"], "FAIL")
        self.assertEqual(result["failures"], ["live_box_zoom: root box failure"])

    def test_engineering_canvas_acceptance_rejects_wire_host_or_full_sync(self) -> None:
        from scripts import profile_canvas_lag

        operations = []
        for name in profile_canvas_lag._ENGINEERING_OPERATION_ORDER:
            item = {
                "operation": name,
                "status": "blocked",
                "unavailable_reason": "not part of this synthetic wire check",
            }
            if name == "active_wire_drag":
                live = {
                    "live_mode": "full",
                    "explicit_inline_active": True,
                    "widget_identity": "widget-1",
                    "transport_revision": 1,
                    "native_overlay_visible": True,
                    "native_overlay_geometry_ready": True,
                    "native_updates_enabled": True,
                }
                during = {
                    **live,
                    "native_overlay_visible": False,
                    "native_overlay_geometry_ready": False,
                    "native_updates_enabled": False,
                }
                item = {
                    "operation": name,
                    "status": "measured",
                    "timing_p95_ms": 10.0,
                    "frame_interval_p95_ms": 10.0,
                    "viewer_before": live,
                    "viewer_during": during,
                    "viewer_after": live,
                    "lifecycle_deltas": {},
                    "continuous_lifecycle_deltas": {
                        "binder_bind": 0,
                        "binder_release": 0,
                        "binder_render": 0,
                        "dataset_load": 0,
                        "widget_create": 0,
                        "native_move_calls": 0,
                        "native_resize_calls": 0,
                        "native_set_geometry_calls": 0,
                        "viewer_host_sync": 1,
                        "overlay_full_sync": 1,
                    },
                }
            operations.append(item)

        result = profile_canvas_lag._evaluate_engineering_acceptance(
            {"operations": operations}
        )

        self.assertEqual(result["status"], "FAIL")
        self.assertEqual(
            result["failures"],
            [
                "active_wire_drag: unexpected native work "
                "{'viewer_host_sync': 1, 'overlay_full_sync': 1}"
            ],
        )

    def test_engineering_canvas_acceptance_rejects_passive_counter_changes(self) -> None:
        from scripts import profile_canvas_lag

        report = self._passing_engineering_canvas_report()
        selection = next(
            item
            for item in report["operations"]
            if item["operation"] == "selection_without_activation"
        )
        selection["lifecycle_deltas"].update(
            viewer_host_sync=1,
            embedded_interaction_sync=1,
            camera_capture=1,
            preview_capture=1,
            execution_update=1,
            overlay_full_sync=1,
            overlay_transform_sync=1,
            overlay_skipped_delta=1,
        )

        result = profile_canvas_lag._evaluate_engineering_acceptance(report)

        self.assertEqual(result["status"], "FAIL")
        passive_failure = next(
            failure
            for failure in result["failures"]
            if failure.startswith("selection_without_activation: unexpected native work")
        )
        for counter in (
            "viewer_host_sync",
            "embedded_interaction_sync",
            "camera_capture",
            "preview_capture",
            "execution_update",
            "overlay_full_sync",
            "overlay_transform_sync",
            "overlay_skipped_delta",
        ):
            self.assertIn(counter, passive_failure)

    def test_engineering_canvas_acceptance_rejects_transient_update_and_activation_loss(
        self,
    ) -> None:
        from scripts import profile_canvas_lag

        report = self._passing_engineering_canvas_report()
        box_zoom = next(
            item
            for item in report["operations"]
            if item["operation"] == "live_box_zoom"
        )
        box_zoom["viewer_after"]["explicit_inline_active"] = False
        box_zoom["lifecycle_deltas"]["execution_update"] = 1

        result = profile_canvas_lag._evaluate_engineering_acceptance(report)

        self.assertEqual(result["status"], "FAIL")
        self.assertIn(
            "live_box_zoom: execution live-mode update occurred during transient gesture",
            result["failures"],
        )
        self.assertIn(
            "live_box_zoom: explicit inline activation did not restore",
            result["failures"],
        )

    def test_engineering_canvas_acceptance_rejects_incomplete_deletion_cleanup(
        self,
    ) -> None:
        from scripts import profile_canvas_lag

        report = self._passing_engineering_canvas_report()
        deletion = next(
            item
            for item in report["operations"]
            if item["operation"] == "viewer_deletion"
        )
        deletion["viewer_after"].update(
            phase="open",
            session_id="session-still-present",
            explicit_inline_active=True,
            retained_inline_node_id=profile_canvas_lag._ENGINEERING_VIEWER_NODE_ID,
            widget_identity="widget-still-present",
            transport_revision=1,
        )

        result = profile_canvas_lag._evaluate_engineering_acceptance(report)

        self.assertEqual(result["status"], "FAIL")
        for expected in (
            "viewer_deletion: widget remains resident",
            "viewer_deletion: retained key remains",
            "viewer_deletion: session projection remains",
            "viewer_deletion: explicit inline activation remains",
            "viewer_deletion: transport revision remains",
        ):
            self.assertIn(expected, result["failures"])

    def test_engineering_release_acceptance_passes_three_stable_reports(self) -> None:
        from scripts import profile_canvas_lag

        reports = [
            copy.deepcopy(self._passing_engineering_canvas_report())
            for _ in range(3)
        ]
        for report, value in zip(reports, (9.0, 10.0, 11.0)):
            operation = next(
                item
                for item in report["operations"]
                if item["operation"] == "live_box_zoom"
            )
            operation["timing_p95_ms"] = value

        result = profile_canvas_lag._evaluate_engineering_release_acceptance(
            reports
        )

        self.assertEqual(result["status"], "PASS", result["failures"])
        self.assertTrue(result["release_ready"])
        self.assertEqual(result["release_status"], "READY")
        self.assertTrue(result["three_run_cv_evaluated"])
        self.assertLessEqual(
            result["coefficients_of_variation"]["live_box_zoom"]["timing_p95_cv"],
            0.20,
        )

    def test_engineering_release_acceptance_rejects_invalid_environment_or_parity(
        self,
    ) -> None:
        from scripts import profile_canvas_lag

        cases = (
            (
                "qt_platform",
                lambda report: report.__setitem__("qt_platform", "offscreen"),
                "run 1: qt_platform must be windows",
            ),
            (
                "graphics_api",
                lambda report: report["renderer_diagnostics"].__setitem__(
                    "graphics_api", "Software"
                ),
                "run 1: graphics_api must be Direct3D11Rhi",
            ),
            (
                "qml_host_kind",
                lambda report: report["renderer_diagnostics"].__setitem__(
                    "qml_host_kind", "qquickview_container"
                ),
                "run 1: qml_host_kind must be qquickwidget",
            ),
            (
                "feature_parity",
                lambda report: report["feature_parity"].__setitem__("pass", False),
                "run 1: feature parity must pass",
            ),
            (
                "renderer_grab_window_readback_included",
                lambda report: report["renderer_diagnostics"].__setitem__(
                    "grab_window_readback_included", True
                ),
                "run 1: renderer grab_window_readback_included must be false",
            ),
            (
                "grab_window_readback_included",
                lambda report: report.__setitem__(
                    "grab_window_readback_included", True
                ),
                "run 1: grab_window_readback_included must be false",
            ),
        )
        for label, mutate, expected_failure in cases:
            with self.subTest(label=label):
                reports = [
                    copy.deepcopy(self._passing_engineering_canvas_report())
                    for _ in range(3)
                ]
                mutate(reports[0])

                result = profile_canvas_lag._evaluate_engineering_release_acceptance(
                    reports
                )

                self.assertEqual(result["status"], "FAIL")
                self.assertFalse(result["release_ready"])
                self.assertIn(expected_failure, result["failures"])

    def test_engineering_release_acceptance_rejects_unstable_cv(self) -> None:
        from scripts import profile_canvas_lag

        reports = [
            copy.deepcopy(self._passing_engineering_canvas_report())
            for _ in range(3)
        ]
        for report, value in zip(reports, (1.0, 1.0, 30.0)):
            operation = next(
                item
                for item in report["operations"]
                if item["operation"] == "live_box_zoom"
            )
            operation["timing_p95_ms"] = value

        result = profile_canvas_lag._evaluate_engineering_release_acceptance(
            reports
        )

        self.assertEqual(result["status"], "FAIL")
        self.assertFalse(result["release_ready"])
        self.assertEqual(result["release_status"], "NOT_READY")
        self.assertIn(
            "live_box_zoom: timing p95 CV exceeds 0.20",
            result["failures"],
        )

    def test_benchmark_runner_emits_baseline_series_with_machine_metadata(self) -> None:
        report = run_benchmark(
            BenchmarkConfig(
                synthetic_graph=SyntheticGraphConfig(
                    node_count=60, edge_count=160, seed=11
                ),
                load_iterations=1,
                interaction_samples=4,
                interaction_warmup_samples=1,
            ),
            baseline_runs=2,
            baseline_mode="interactive",
            baseline_tag="unit_test",
        )

        baseline_series = report["baseline_series"]
        self.assertEqual(baseline_series["mode"], "interactive")
        self.assertEqual(baseline_series["tag"], "unit_test")
        self.assertEqual(baseline_series["scenario"], "synthetic_exec")
        self.assertEqual(baseline_series["run_count"], 2)
        self.assertEqual(len(baseline_series["runs"]), 2)
        self.assertEqual(baseline_series["status"], "complete")
        self.assertEqual(baseline_series["completed_run_count"], 2)
        self.assertEqual(baseline_series["failed_run_count"], 0)
        self.assertEqual(baseline_series["failed_runs"], [])

        first_run = baseline_series["runs"][0]
        mutation_contract = baseline_series["mutation_benchmark_contract"]
        self.assertIn("run_id", first_run)
        self.assertIn("generated_at_utc", first_run)
        self.assertEqual(first_run["scenario"], "synthetic_exec")
        self.assertIn("environment", first_run)
        self.assertIn("metrics", first_run)
        self.assertIn("hostname", first_run["environment"])
        self.assertIn("machine", first_run["environment"])
        self.assertIn("qt_quick_backend", first_run["environment"])
        self.assertIn("qsg_rhi_backend", first_run["environment"])
        self.assertIn("qsg_rhi_backend_override", first_run["environment"])
        self.assertIn("qml_host_env", first_run["environment"])
        self.assertIn("qml_host_kind_selected", first_run["environment"])
        self.assertIn("qtquick_backend_selection_reason", first_run["environment"])
        self.assertIn("display_diagnostics", first_run)
        self.assertIn("packet_verification_result", first_run)
        self.assertIn("performance_acceptance_result", first_run)
        self.assertIn("qt_platform", first_run["display_diagnostics"])
        self.assertIn("load_p95_ms", first_run["metrics"])
        self.assertIn("pan_p95_ms", first_run["metrics"])
        self.assertIn("zoom_p95_ms", first_run["metrics"])
        self.assertIn("pan_zoom_p95_ms", first_run["metrics"])
        self.assertIn("node_drag_control_p95_ms", first_run["metrics"])
        self.assertIn("node_drag_first_offset_p95_ms", first_run["metrics"])
        self.assertIn("node_drag_steady_offset_p95_ms", first_run["metrics"])
        self.assertIn("node_drag_full_gesture_p95_ms", first_run["metrics"])
        self.assertIn("node_drag_end_clear_p95_ms", first_run["metrics"])
        self.assertIn("frame_interval_without_readback_p95_ms", first_run["metrics"])
        self.assertEqual(
            mutation_contract["scenarios"],
            list(performance_harness._MUTATION_BENCHMARK_SCENARIOS),
        )
        self.assertEqual(
            mutation_contract["report_field_groups"]["payload_sizes"],
            [
                "command_payload_bytes",
                "graph_delta_payload_bytes",
                "scene_payload_bytes",
            ],
        )
        self.assertEqual(
            mutation_contract["report_field_groups"]["setup_evidence"],
            [
                "setup_excluded_from_mutation_timing",
                "setup_wall_clock_samples_ms",
                "setup_phase_timings_ms",
                "setup_dirty_node_count",
                "setup_dirty_edge_count",
            ],
        )
        self.assertEqual(
            baseline_series["mutation_phase_instrumentation"]["status"],
            "instrumentation_hooks_available",
        )

        metric_series = baseline_series["metric_series"]
        self.assertEqual(len(metric_series["load_p95_ms"]), 2)
        self.assertEqual(len(metric_series["pan_p95_ms"]), 2)
        self.assertEqual(len(metric_series["zoom_p95_ms"]), 2)
        self.assertEqual(len(metric_series["pan_zoom_p95_ms"]), 2)
        self.assertEqual(len(metric_series["node_drag_control_p95_ms"]), 2)
        self.assertEqual(len(metric_series["node_drag_first_offset_p95_ms"]), 2)
        self.assertEqual(len(metric_series["node_drag_steady_offset_p95_ms"]), 2)
        self.assertEqual(len(metric_series["node_drag_full_gesture_p95_ms"]), 2)
        self.assertEqual(len(metric_series["node_drag_end_clear_p95_ms"]), 2)
        self.assertEqual(
            len(metric_series["frame_interval_without_readback_p95_ms"]), 2
        )

        variance_eval = baseline_series["variance_eval"]
        self.assertIn("load_p95_ms", variance_eval)
        self.assertIn("pan_p95_ms", variance_eval)
        self.assertIn("zoom_p95_ms", variance_eval)
        self.assertIn("pan_zoom_p95_ms", variance_eval)
        self.assertIn("node_drag_control_p95_ms", variance_eval)
        self.assertIn("node_drag_first_offset_p95_ms", variance_eval)
        self.assertIn("node_drag_steady_offset_p95_ms", variance_eval)
        self.assertIn("node_drag_full_gesture_p95_ms", variance_eval)
        self.assertIn("node_drag_end_clear_p95_ms", variance_eval)
        self.assertIn("frame_interval_without_readback_p95_ms", variance_eval)
        self.assertIn("pass", variance_eval["load_p95_ms"])
        self.assertIn("details", variance_eval["pan_zoom_p95_ms"])

    def test_windows_baseline_series_uses_subprocess_runner(self) -> None:
        sample_report = self._mock_single_run_report()
        with patch.dict(
            performance_harness.os.environ, {"QT_QPA_PLATFORM": "windows"}, clear=False
        ):
            with patch.object(
                performance_harness,
                "_run_single_benchmark_subprocess",
                side_effect=[sample_report, sample_report],
            ) as subprocess_runner:
                with patch.object(
                    performance_harness, "_run_single_benchmark"
                ) as in_process_runner:
                    report = run_benchmark(
                        BenchmarkConfig(
                            synthetic_graph=SyntheticGraphConfig(
                                node_count=60, edge_count=160, seed=11
                            ),
                            load_iterations=1,
                            interaction_samples=4,
                            interaction_warmup_samples=1,
                            qml_host="qquickview_container",
                            qsg_rhi_backend="d3d11",
                        ),
                        baseline_runs=2,
                        baseline_mode="interactive",
                        baseline_tag="unit_test",
                    )

        self.assertEqual(subprocess_runner.call_count, 2)
        forwarded_config = subprocess_runner.call_args.args[0]
        self.assertEqual(forwarded_config.qml_host, "qquickview_container")
        self.assertEqual(forwarded_config.qsg_rhi_backend, "d3d11")
        in_process_runner.assert_not_called()
        self.assertEqual(report["baseline_series"]["run_count"], 2)
        self.assertEqual(len(report["baseline_series"]["runs"]), 2)

    def test_repeated_baseline_retains_completed_runs_and_failed_run_record(
        self,
    ) -> None:
        first_report = self._mock_single_run_report()
        third_report = json.loads(json.dumps(first_report))
        child_failure = subprocess.CalledProcessError(
            -1073741819,
            ["performance_harness"],
            output="native Qt crash tail",
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            report_dir = Path(temp_dir)
            with patch.object(
                performance_harness,
                "_run_single_benchmark_subprocess",
                side_effect=[first_report, child_failure, third_report],
            ) as subprocess_runner:
                with patch("builtins.print"):
                    report = run_benchmark(
                        BenchmarkConfig(),
                        baseline_runs=3,
                        baseline_mode="offscreen",
                        baseline_tag="partial_failure_test",
                        report_dir=report_dir,
                    )

            first_path = report_dir / "baseline_run_01.json"
            failed_path = report_dir / "baseline_run_02.failed.json"
            third_path = report_dir / "baseline_run_03.json"
            self.assertEqual(subprocess_runner.call_count, 3)
            self.assertEqual(
                json.loads(first_path.read_text(encoding="utf-8"))["generated_at_utc"],
                first_report["generated_at_utc"],
            )
            self.assertEqual(
                json.loads(third_path.read_text(encoding="utf-8"))["generated_at_utc"],
                third_report["generated_at_utc"],
            )
            failed_record = json.loads(failed_path.read_text(encoding="utf-8"))

        baseline = report["baseline_series"]
        self.assertEqual(baseline["status"], "partial_failure")
        self.assertEqual(baseline["run_count"], 3)
        self.assertEqual(baseline["completed_run_count"], 2)
        self.assertEqual(baseline["failed_run_count"], 1)
        self.assertEqual([run["run_id"] for run in baseline["runs"]], ["run_01", "run_03"])
        self.assertEqual(failed_record["run_id"], "run_02")
        self.assertEqual(failed_record["returncode"], -1073741819)
        self.assertIn("native Qt crash tail", failed_record["output_tail"])
        self.assertEqual(len(baseline["run_report_paths"]), 2)

    def test_isolated_child_preserves_custom_interaction_zoom_range(self) -> None:
        sample_report = self._mock_single_run_report()
        captured_command: list[str] = []

        def popen(command, **_kwargs):
            captured_command.extend(command)
            report_dir = Path(command[command.index("--report-dir") + 1])
            (report_dir / "track_h_benchmark_report.json").write_text(
                json.dumps(sample_report),
                encoding="utf-8",
            )
            return SimpleNamespace(stdout=(), wait=lambda: 0)

        with patch.object(performance_harness.subprocess, "Popen", side_effect=popen):
            report = performance_harness._run_single_benchmark_subprocess(
                BenchmarkConfig(
                    interaction_zoom_min=0.75,
                    interaction_zoom_max=1.25,
                ),
                baseline_mode="offscreen",
                baseline_tag="zoom_forwarding",
            )

        self.assertEqual(report["generated_at_utc"], sample_report["generated_at_utc"])
        self.assertEqual(
            captured_command[captured_command.index("--interaction-zoom-min") + 1],
            "0.75",
        )
        self.assertEqual(
            captured_command[captured_command.index("--interaction-zoom-max") + 1],
            "1.25",
        )
        self.assertEqual(
            captured_command[captured_command.index("--baseline-runs") + 1],
            "1",
        )

    def test_new_isolated_series_clears_only_stale_baseline_artifacts(self) -> None:
        first_report = self._mock_single_run_report()
        second_report = json.loads(json.dumps(first_report))
        with tempfile.TemporaryDirectory() as temp_dir:
            report_dir = Path(temp_dir)
            stale_paths = (
                report_dir / "baseline_run_01.failed.json",
                report_dir / "baseline_run_04.json",
                report_dir / "baseline_series_failure.json",
            )
            for path in stale_paths:
                path.write_text("{}", encoding="utf-8")
            unrelated_path = report_dir / "keep_me.json"
            aggregate_path = report_dir / "track_h_benchmark_report.json"
            unrelated_path.write_text("{}", encoding="utf-8")
            aggregate_path.write_text("{}", encoding="utf-8")

            with patch.object(
                performance_harness,
                "_run_single_benchmark_subprocess",
                side_effect=[first_report, second_report],
            ):
                with patch("builtins.print"):
                    run_benchmark(
                        BenchmarkConfig(),
                        baseline_runs=2,
                        report_dir=report_dir,
                    )

            self.assertTrue((report_dir / "baseline_run_01.json").is_file())
            self.assertTrue((report_dir / "baseline_run_02.json").is_file())
            self.assertTrue(all(not path.exists() for path in stale_paths))
            self.assertTrue(unrelated_path.is_file())
            self.assertTrue(aggregate_path.is_file())

    def test_repeated_baseline_in_process_opt_out_avoids_child_runner(self) -> None:
        sample_report = self._mock_single_run_report()
        with patch.object(
            performance_harness,
            "_run_single_benchmark",
            side_effect=[sample_report, json.loads(json.dumps(sample_report))],
        ) as in_process_runner:
            with patch.object(
                performance_harness,
                "_run_single_benchmark_subprocess",
            ) as subprocess_runner:
                with patch("builtins.print"):
                    report = run_benchmark(
                        BenchmarkConfig(),
                        baseline_runs=2,
                        isolate_baseline_runs=False,
                    )

        self.assertEqual(in_process_runner.call_count, 2)
        subprocess_runner.assert_not_called()
        self.assertEqual(report["baseline_series"]["execution_mode"], "in_process")

    def test_comparison_output_is_bounded_and_excludes_raw_report_arrays(self) -> None:
        reference_report = self._mock_single_run_report()
        current_report = json.loads(json.dumps(reference_report))
        reference_report["process_resources"] = {"rss_end_bytes": 64 * 1024 * 1024}
        current_report["process_resources"] = {"rss_end_bytes": 80 * 1024 * 1024}
        reference_report["graph_mutation_benchmark"] = self._mock_graph_mutation_benchmark()
        current_report["graph_mutation_benchmark"] = self._mock_graph_mutation_benchmark()
        reference_report["baseline_series"] = {
            "samples": ["RAW_SAMPLE_SENTINEL"] * 1000
        }
        current_report["baseline_series"] = {
            "samples": ["RAW_SAMPLE_SENTINEL"] * 1000
        }

        output = performance_harness._format_report_comparison(
            current_report,
            reference_report,
        )

        self.assertLess(len(output.encode("utf-8")), 4096)
        self.assertIn("load_p95_ms", output)
        self.assertIn("pan_zoom_p95_ms", output)
        self.assertIn("node_drag_steady_offset_p95_ms", output)
        self.assertIn("mutation.create_edge.wall_p95_ms", output)
        self.assertIn("process_rss_end_mib", output)
        self.assertNotIn("baseline_series", output)
        self.assertNotIn("samples", output)
        self.assertNotIn("RAW_SAMPLE_SENTINEL", output)

    def test_heavy_media_records_all_media_surfaces(self) -> None:
        self._assert_heavy_media_scenario()

    def test_resolve_baseline_mode_auto(self) -> None:
        self.assertEqual(_resolve_baseline_mode("auto", "offscreen"), "offscreen")
        self.assertEqual(_resolve_baseline_mode("auto", "windows"), "interactive")
        self.assertEqual(
            _resolve_baseline_mode("interactive", "offscreen"), "interactive"
        )
        self.assertEqual(_resolve_baseline_mode("offscreen", "windows"), "offscreen")


if __name__ == "__main__":
    unittest.main()

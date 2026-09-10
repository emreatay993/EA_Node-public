from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path
from unittest import mock

from ea_node_editor.execution.handle_registry import StaleHandleError
from ea_node_editor.execution.viewer_messages import (
    CloseViewerSessionCommand,
    MaterializeViewerDataCommand,
    OpenViewerSessionCommand,
    QueryViewerSessionCommand,
    UpdateViewerSessionCommand,
    ViewerDataMaterializedEvent,
    ViewerSessionClosedEvent,
    ViewerSessionFailedEvent,
    ViewerSessionOpenedEvent,
    ViewerQueryResultEvent,
    ViewerSessionUpdatedEvent,
    viewer_epoch_snapshot_digest,
)
from ea_node_editor.execution.protocol_codec import (
    event_to_dict,
)
from ea_node_editor.execution.viewer_backend import (
    ViewerBackendMaterializationResult,
    ViewerBackendQueryResult,
)
from ea_node_editor.execution.viewer_backend_engineering import (
    COREX_SCENE_HANDLE_KIND,
    ENGINEERING_VIEWER_BACKEND_ID,
)
from ea_node_editor.execution.viewer_session_service import (
    build_run_required_viewer_session_model,
    coerce_viewer_session_model,
)
from ea_node_editor.runtime_contracts import (
    COREX_VIEWER_SESSION_HANDLE_KIND,
    ENGINEERING_SCENE_DATA_TYPE_ID,
    PATH_DATA_TYPE_ID,
    RuntimeArtifactRef,
    VIEWER_SESSION_DATA_TYPE_ID,
)
from tests.typed_handle_support import core_worker_services


class _FakeViewerObject:
    def __init__(self, label: str) -> None:
        self.label = label

    def __repr__(self) -> str:
        return f"RAW<{self.label}>"


class ViewerSessionServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.services = core_worker_services()
        self.service = self.services.viewer_session_service

    def test_engineering_open_replaces_scene_snapshot_after_acquiring_all_new_leases(
        self,
    ) -> None:
        disposed = []
        new_lease_counts = []
        session_scope = []

        def register(label, run_id):
            def dispose():
                disposed.append(label)
                if label == "removed":
                    new_lease_counts.append(
                        self.services.handle_registry.lease_count(
                            new_ref, owner_scope=session_scope[0]
                        )
                    )

            return self.services.register_handle(
                {"label": label},
                data_type_id=ENGINEERING_SCENE_DATA_TYPE_ID,
                kind=COREX_SCENE_HANDLE_KIND,
                run_id=run_id,
                dispose=dispose,
            )

        removed_ref = register("removed", "old")
        retained_ref = register("retained", "old")
        native_ref = register("native", "old")
        new_ref = register("new", "new")
        identity = {
            "workspace_id": "ws_main",
            "node_id": "model_viewer",
            "session_id": "scene_snapshot",
            "backend_id": ENGINEERING_VIEWER_BACKEND_ID,
        }
        first_refs = {
            "scene_order": ["a", "b", "c"],
            "scene_labels": {"a": "First"},
            "scene:a": removed_ref,
            "scene:b": retained_ref,
            "scene:c": retained_ref,
            "native_source:a": native_ref,
        }
        self.service.open_session(
            OpenViewerSessionCommand(
                **identity,
                data_refs=first_refs,
                transport={"kind": "engineering_scene_bundle", "layers": []},
            )
        )
        record = self.service._sessions[("ws_main", "scene_snapshot")]
        session_scope.append(record.owner_scope)
        moved_ref = record.source_refs["scene:b"]
        self.services.cleanup_run("old")
        replacement_refs = {
            "scene_order": ["x", "d", "e"],
            "scene_labels": {"x": "Renamed"},
            "scene:x": moved_ref,
            "scene:d": new_ref,
            "scene:e": new_ref,
        }
        self.service.open_session(
            OpenViewerSessionCommand(**identity, data_refs=replacement_refs)
        )
        self.assertEqual(new_lease_counts, [2])
        self.assertEqual(set(disposed), {"removed", "native"})
        self.assertEqual(set(record.source_refs), set(replacement_refs))
        self.assertEqual(record.source_refs["scene_order"], ["x", "d", "e"])
        self.assertEqual(record.transport, {})
        self.assertEqual(
            self.services.handle_registry.lease_count(
                moved_ref, owner_scope=record.owner_scope
            ),
            1,
        )
        self.service.open_session(
            OpenViewerSessionCommand(**identity, data_refs=replacement_refs)
        )
        self.service.open_session(OpenViewerSessionCommand(**identity))
        self.service.update_session(
            UpdateViewerSessionCommand(**identity, options={"active_scene_id": "e"})
        )
        self.assertEqual(set(record.source_refs), set(replacement_refs))
        self.assertEqual(
            self.services.handle_registry.lease_count(
                new_ref, owner_scope=record.owner_scope
            ),
            2,
        )
        self.services.cleanup_run("new")
        self.service.close_session(
            CloseViewerSessionCommand(
                workspace_id="ws_main",
                node_id="model_viewer",
                session_id="scene_snapshot",
            )
        )
        self.assertCountEqual(disposed, ["removed", "native", "retained", "new"])

    def test_viewer_session_service_facade_stays_within_packet_budget(self) -> None:
        execution_dir = (
            Path(__file__).resolve().parents[1] / "ea_node_editor" / "execution"
        )
        facade_path = execution_dir / "viewer_session_service.py"
        support_path = execution_dir / "viewer_session_service_support.py"
        facade_text = facade_path.read_text(encoding="utf-8")

        self.assertFalse(support_path.exists())
        self.assertNotIn("base64.b85decode", facade_text)
        self.assertNotIn("zlib.decompress", facade_text)
        self.assertIn("class ViewerSessionService", facade_text)

    def test_empty_filter_baseline_adopts_only_on_a_fresh_recycled_service(
        self,
    ) -> None:
        digest = viewer_epoch_snapshot_digest(
            workspace_id="ws_fresh",
            node_ids=(),
            workspace_epoch=3,
            node_epochs=(),
        )
        self.assertEqual(
            self.service.adopt_invalidation_snapshot(
                workspace_id="ws_fresh",
                node_ids=(),
                workspace_epoch=3,
                node_epochs=(),
                snapshot_digest=digest,
                reason="workspace_rerun",
            ),
            0,
        )
        self.assertEqual(
            self.service._workspace_invalidation_epochs,  # noqa: SLF001
            {"ws_fresh": 3},
        )
        equal_before = dict(
            self.service._workspace_invalidation_epochs  # noqa: SLF001
        )
        self.assertEqual(
            self.service.adopt_invalidation_snapshot(
                workspace_id="ws_fresh",
                node_ids=(),
                workspace_epoch=3,
                node_epochs=(),
                snapshot_digest=digest,
                reason="workspace_rerun",
            ),
            0,
        )
        self.assertEqual(
            self.service._workspace_invalidation_epochs,  # noqa: SLF001
            equal_before,
        )

        for stale_kind in ("context", "node_epoch", "session", "lease", "buffer"):
            with self.subTest(stale_kind=stale_kind):
                services = core_worker_services()
                service = services.viewer_session_service
                buffered = stale_kind == "buffer"
                if stale_kind == "context":
                    service.install_workspace_context(workspace_id="ws_fresh")
                elif stale_kind == "node_epoch":
                    service._node_invalidation_epochs[("ws_fresh", "viewer")] = 1  # noqa: SLF001
                elif stale_kind == "session":
                    service.open_session(
                        OpenViewerSessionCommand(
                            workspace_id="ws_fresh",
                            node_id="viewer",
                            session_id="session_stale",
                            transport={"kind": "mock_live"},
                        )
                    )
                elif stale_kind == "lease":
                    services.register_handle(
                        _FakeViewerObject("stale_lease"),
                        data_type_id=ENGINEERING_SCENE_DATA_TYPE_ID,
                        kind=COREX_SCENE_HANDLE_KIND,
                        owner_scope="cache:viewer_session:stale",
                    )
                with self.assertRaisesRegex(ValueError, "fresh service"):
                    service.adopt_invalidation_snapshot(
                        workspace_id="ws_fresh",
                        node_ids=(),
                        workspace_epoch=3,
                        node_epochs=(),
                        snapshot_digest=digest,
                        reason="workspace_rerun",
                        buffered_viewer_commands=buffered,
                    )
                self.assertNotIn(
                    "ws_fresh",
                    service._workspace_invalidation_epochs,  # noqa: SLF001
                )

    def test_scoped_snapshot_baselines_only_a_fresh_selected_service(self) -> None:
        digest = viewer_epoch_snapshot_digest(
            workspace_id="ws_scoped_fresh",
            node_ids=("viewer",),
            workspace_epoch=5,
            node_epochs=(("viewer", 4),),
        )
        self.assertEqual(
            self.service.adopt_invalidation_snapshot(
                workspace_id="ws_scoped_fresh",
                node_ids=("viewer",),
                workspace_epoch=5,
                node_epochs=(("viewer", 4),),
                snapshot_digest=digest,
                reason="workspace_rerun",
            ),
            0,
        )
        self.assertEqual(
            self.service._workspace_invalidation_epochs["ws_scoped_fresh"],  # noqa: SLF001
            5,
        )
        self.assertEqual(
            self.service._node_invalidation_epochs[  # noqa: SLF001
                ("ws_scoped_fresh", "viewer")
            ],
            4,
        )

        services = core_worker_services()
        service = services.viewer_session_service
        service.install_workspace_context(workspace_id="ws_scoped_fresh")
        before = (
            dict(service._workspace_invalidation_epochs),  # noqa: SLF001
            dict(service._node_invalidation_epochs),  # noqa: SLF001
            dict(service._workspace_contexts),  # noqa: SLF001
        )
        with self.assertRaisesRegex(ValueError, "fresh service"):
            service.adopt_invalidation_snapshot(
                workspace_id="ws_scoped_fresh",
                node_ids=("viewer",),
                workspace_epoch=5,
                node_epochs=(("viewer", 4),),
                snapshot_digest=digest,
                reason="workspace_rerun",
            )
        self.assertEqual(
            (
                dict(service._workspace_invalidation_epochs),  # noqa: SLF001
                dict(service._node_invalidation_epochs),  # noqa: SLF001
                dict(service._workspace_contexts),  # noqa: SLF001
            ),
            before,
        )

    def test_session_handle_exposes_identity_only_and_resolves_current_projection(
        self,
    ) -> None:
        session_id = "viewer_session_contract"
        self.service.open_session(
            OpenViewerSessionCommand(
                workspace_id="ws_main",
                node_id="node_viewer",
                session_id=session_id,
                backend_id=ENGINEERING_VIEWER_BACKEND_ID,
                summary={"result_name": "displacement"},
                options={"live_mode": "proxy"},
            )
        )

        handle = self.service.session_handle("ws_main", session_id)
        projection = self.services.resolve_handle(
            handle,
            expected_data_type=VIEWER_SESSION_DATA_TYPE_ID,
            expected_kind=COREX_VIEWER_SESSION_HANDLE_KIND,
        )

        self.assertEqual(handle.data_type_id, VIEWER_SESSION_DATA_TYPE_ID)
        self.assertEqual(handle.kind, COREX_VIEWER_SESSION_HANDLE_KIND)
        self.assertEqual(
            handle.metadata,
            {
                "workspace_id": "ws_main",
                "node_id": "node_viewer",
                "session_id": session_id,
                "backend_id": ENGINEERING_VIEWER_BACKEND_ID,
            },
        )
        self.assertEqual(projection["session_id"], session_id)
        self.assertEqual(projection["summary"]["result_name"], "displacement")

    def test_viewer_lease_survives_run_cleanup_without_duplicate_updates(
        self,
    ) -> None:
        disposed: list[str] = []
        fields_value = _FakeViewerObject("leased_fields")
        fields_ref = self.services.register_handle(
            fields_value,
            data_type_id=ENGINEERING_SCENE_DATA_TYPE_ID,
            kind=COREX_SCENE_HANDLE_KIND,
            run_id="run_viewer_lease",
            dispose=lambda: disposed.append("fields"),
        )
        model_ref = self.services.register_handle(
            _FakeViewerObject("leased_model"),
            data_type_id=ENGINEERING_SCENE_DATA_TYPE_ID,
            kind=COREX_SCENE_HANDLE_KIND,
            run_id="run_viewer_lease",
        )
        command = OpenViewerSessionCommand(
            workspace_id="ws_main",
            node_id="node_viewer",
            session_id="session_lease",
            backend_id=ENGINEERING_VIEWER_BACKEND_ID,
            data_refs={"fields": fields_ref, "model": model_ref},
        )

        self.service.open_session(command)
        record = self.service._sessions[("ws_main", "session_lease")]  # noqa: SLF001
        viewer_fields_ref = record.source_refs["fields"]
        viewer_scope = record.owner_scope

        self.assertEqual(viewer_fields_ref.handle_id, fields_ref.handle_id)
        self.assertEqual(viewer_fields_ref.owner_scope, viewer_scope)
        self.assertEqual(
            self.services.handle_registry.lease_count(
                fields_ref,
                owner_scope=viewer_scope,
            ),
            1,
        )
        self.assertIs(self.services.resolve_handle(fields_ref), fields_value)

        self.service.update_session(
            UpdateViewerSessionCommand(
                workspace_id="ws_main",
                node_id="node_viewer",
                session_id="session_lease",
                data_refs={"fields": fields_ref, "model": model_ref},
            )
        )
        self.assertEqual(
            self.services.handle_registry.lease_count(
                fields_ref,
                owner_scope=viewer_scope,
            ),
            1,
        )

        session_projection_ref = self.service.session_handle(
            "ws_main",
            "session_lease",
        )
        self.services.cleanup_run("run_viewer_lease")
        with self.assertRaisesRegex(StaleHandleError, "owner_scope is stale"):
            self.services.resolve_handle(fields_ref)
        self.assertIs(
            self.services.resolve_handle(viewer_fields_ref),
            fields_value,
        )

        closed = self.service.close_session(
            CloseViewerSessionCommand(
                workspace_id="ws_main",
                node_id="node_viewer",
                session_id="session_lease",
            )
        )
        closed_again = self.service.close_session(
            CloseViewerSessionCommand(
                workspace_id="ws_main",
                node_id="node_viewer",
                session_id="session_lease",
            )
        )

        self.assertEqual(closed.options["session_state"], "closed")
        self.assertEqual(closed_again.options["session_state"], "closed")
        self.assertEqual(disposed, ["fields"])
        with self.assertRaisesRegex(StaleHandleError, "stale or unknown"):
            self.services.resolve_handle(viewer_fields_ref)
        with self.assertRaisesRegex(StaleHandleError, "stale or unknown"):
            self.services.resolve_handle(session_projection_ref)

    def test_viewer_ref_replacement_acquires_new_lease_before_releasing_old(
        self,
    ) -> None:
        session_scope: list[str] = []
        replacement_ref = self.services.register_handle(
            _FakeViewerObject("replacement"),
            data_type_id=ENGINEERING_SCENE_DATA_TYPE_ID,
            kind=COREX_SCENE_HANDLE_KIND,
            run_id="run_replace_new",
        )
        observed_new_lease_counts: list[int] = []

        def dispose_previous() -> None:
            observed_new_lease_counts.append(
                self.services.handle_registry.lease_count(
                    replacement_ref,
                    owner_scope=session_scope[0],
                )
            )

        previous_ref = self.services.register_handle(
            _FakeViewerObject("previous"),
            data_type_id=ENGINEERING_SCENE_DATA_TYPE_ID,
            kind=COREX_SCENE_HANDLE_KIND,
            run_id="run_replace_old",
            dispose=dispose_previous,
        )
        self.service.open_session(
            OpenViewerSessionCommand(
                workspace_id="ws_main",
                node_id="node_viewer",
                session_id="session_replace",
                backend_id=ENGINEERING_VIEWER_BACKEND_ID,
                data_refs={"fields": previous_ref},
            )
        )
        record = self.service._sessions[("ws_main", "session_replace")]  # noqa: SLF001
        session_scope.append(record.owner_scope)
        self.services.cleanup_run("run_replace_old")

        updated = self.service.update_session(
            UpdateViewerSessionCommand(
                workspace_id="ws_main",
                node_id="node_viewer",
                session_id="session_replace",
                data_refs={"fields": replacement_ref},
            )
        )

        record = self.service._sessions[("ws_main", "session_replace")]  # noqa: SLF001
        self.assertIsInstance(updated, ViewerSessionUpdatedEvent)
        self.assertEqual(observed_new_lease_counts, [1])
        self.assertEqual(
            record.source_refs["fields"].handle_id,
            replacement_ref.handle_id,
        )

    def test_colliding_external_session_keys_have_distinct_owner_scopes(
        self,
    ) -> None:
        first_ref = self.services.register_handle(
            _FakeViewerObject("first"),
            data_type_id=ENGINEERING_SCENE_DATA_TYPE_ID,
            kind=COREX_SCENE_HANDLE_KIND,
            run_id="run_collision_first",
        )
        second_ref = self.services.register_handle(
            _FakeViewerObject("second"),
            data_type_id=ENGINEERING_SCENE_DATA_TYPE_ID,
            kind=COREX_SCENE_HANDLE_KIND,
            run_id="run_collision_second",
        )
        for workspace_id, session_id, data_ref in (
            ("a:b", "c", first_ref),
            ("a", "b:c", second_ref),
        ):
            self.service.open_session(
                OpenViewerSessionCommand(
                    workspace_id=workspace_id,
                    node_id="node_viewer",
                    session_id=session_id,
                    backend_id=ENGINEERING_VIEWER_BACKEND_ID,
                    data_refs={"fields": data_ref},
                )
            )

        first_record = self.service._sessions[("a:b", "c")]  # noqa: SLF001
        second_record = self.service._sessions[("a", "b:c")]  # noqa: SLF001
        first_viewer_ref = first_record.source_refs["fields"]
        second_viewer_ref = second_record.source_refs["fields"]
        self.assertNotEqual(first_record.owner_scope, second_record.owner_scope)

        self.services.cleanup_run("run_collision_first")
        self.services.cleanup_run("run_collision_second")
        self.service.close_session(
            CloseViewerSessionCommand(
                workspace_id="a:b",
                node_id="node_viewer",
                session_id="c",
            )
        )

        with self.assertRaisesRegex(StaleHandleError, "stale or unknown"):
            self.services.resolve_handle(first_viewer_ref)
        self.assertEqual(
            self.services.resolve_handle(second_viewer_ref).label,
            "second",
        )
        self.service.close_session(
            CloseViewerSessionCommand(
                workspace_id="a",
                node_id="node_viewer",
                session_id="b:c",
            )
        )

    def test_explicit_close_reports_disposal_failure_after_complete_cleanup(
        self,
    ) -> None:
        disposed: list[str] = []

        def fail_disposal() -> None:
            disposed.append("failed")
            raise RuntimeError("private disposal detail")

        failing_ref = self.services.register_handle(
            _FakeViewerObject("failing"),
            data_type_id=ENGINEERING_SCENE_DATA_TYPE_ID,
            kind=COREX_SCENE_HANDLE_KIND,
            run_id="run_close_failure",
            dispose=fail_disposal,
        )
        successful_ref = self.services.register_handle(
            _FakeViewerObject("successful"),
            data_type_id=ENGINEERING_SCENE_DATA_TYPE_ID,
            kind=COREX_SCENE_HANDLE_KIND,
            run_id="run_close_failure",
            dispose=lambda: disposed.append("successful"),
        )
        artifact_ref = RuntimeArtifactRef.staged(
            "viewer_close_artifact",
            data_type_id=PATH_DATA_TYPE_ID,
            schema_version=1,
            format="png",
            size_bytes=0,
            sha256="0" * 64,
            provenance="corex.test.fixture",
        )
        other_workspace_ref = self.services.register_handle(
            _FakeViewerObject("other_workspace"),
            data_type_id=ENGINEERING_SCENE_DATA_TYPE_ID,
            kind=COREX_SCENE_HANDLE_KIND,
            owner_scope="cache:tests:other_workspace",
        )
        for workspace_id, session_id, refs in (
            (
                "ws_main",
                "session_close_failure",
                {
                    "fields": failing_ref,
                    "model": successful_ref,
                    "png": artifact_ref,
                },
            ),
            (
                "ws_other",
                "session_other",
                {"fields": other_workspace_ref},
            ),
        ):
            self.service.open_session(
                OpenViewerSessionCommand(
                    workspace_id=workspace_id,
                    node_id="node_viewer",
                    session_id=session_id,
                    backend_id=ENGINEERING_VIEWER_BACKEND_ID,
                    data_refs=refs,
                )
            )
        other_record = self.service._sessions[  # noqa: SLF001
            ("ws_other", "session_other")
        ]
        other_viewer_ref = other_record.source_refs["fields"]
        self.services.cleanup_run("run_close_failure")

        failed = self.service.close_session(
            CloseViewerSessionCommand(
                workspace_id="ws_main",
                node_id="node_viewer",
                session_id="session_close_failure",
            )
        )
        closed_again = self.service.close_session(
            CloseViewerSessionCommand(
                workspace_id="ws_main",
                node_id="node_viewer",
                session_id="session_close_failure",
            )
        )

        self.assertCountEqual(disposed, ["failed", "successful"])
        self.assertIsInstance(failed, ViewerSessionFailedEvent)
        self.assertEqual(
            failed.error,
            "Viewer session cleanup failed.",
        )
        self.assertNotIn("private disposal detail", failed.error)
        self.assertIsInstance(closed_again, ViewerSessionClosedEvent)
        self.assertEqual(
            closed_again.options["session_state"],
            "closed",
        )
        closed_record = self.service._sessions[  # noqa: SLF001
            ("ws_main", "session_close_failure")
        ]
        self.assertEqual(closed_record.session_state, "closed")
        self.assertEqual(
            closed_record.summary["cleanup_error"],
            "Runtime handle disposal failed.",
        )
        self.assertEqual(closed_record.materialized_refs["png"], artifact_ref)
        self.assertIs(
            self.services.resolve_handle(other_viewer_ref),
            self.services.resolve_handle(other_workspace_ref),
        )

    def test_invalidation_and_reset_warn_and_continue_across_sessions(self) -> None:
        disposed: list[str] = []

        def failing_dispose() -> None:
            disposed.append("failed")
            raise RuntimeError("automatic cleanup failed")

        refs = (
            self.services.register_handle(
                _FakeViewerObject("failed"),
                data_type_id=ENGINEERING_SCENE_DATA_TYPE_ID,
                kind=COREX_SCENE_HANDLE_KIND,
                run_id="run_auto_cleanup",
                dispose=failing_dispose,
            ),
            self.services.register_handle(
                _FakeViewerObject("successful"),
                data_type_id=ENGINEERING_SCENE_DATA_TYPE_ID,
                kind=COREX_SCENE_HANDLE_KIND,
                run_id="run_auto_cleanup",
                dispose=lambda: disposed.append("successful"),
            ),
        )
        for index, runtime_ref in enumerate(refs):
            self.service.open_session(
                OpenViewerSessionCommand(
                    workspace_id="ws_main",
                    node_id=f"node_{index}",
                    session_id=f"session_{index}",
                    backend_id=ENGINEERING_VIEWER_BACKEND_ID,
                    data_refs={"fields": runtime_ref},
                )
            )
        viewer_refs = tuple(
            self.service._sessions[("ws_main", f"session_{index}")].source_refs[  # noqa: SLF001
                "fields"
            ]
            for index in range(2)
        )
        self.services.cleanup_run("run_auto_cleanup")

        with self.assertLogs(
            "ea_node_editor.execution.handle_registry",
            level="WARNING",
        ):
            self.service.invalidate_workspace(
                "ws_main",
                reason="workspace_rerun",
            )

        self.assertCountEqual(disposed, ["failed", "successful"])
        for runtime_ref in viewer_refs:
            with self.assertRaisesRegex(StaleHandleError, "stale or unknown"):
                self.services.resolve_handle(runtime_ref)

        reset_disposed: list[str] = []

        def failing_reset_dispose() -> None:
            reset_disposed.append("failed")
            raise RuntimeError("reset failure")

        reset_ref = self.services.register_handle(
            _FakeViewerObject("reset_failed"),
            data_type_id=ENGINEERING_SCENE_DATA_TYPE_ID,
            kind=COREX_SCENE_HANDLE_KIND,
            owner_scope="cache:tests:reset_failure",
            dispose=failing_reset_dispose,
        )
        self.services.register_handle(
            _FakeViewerObject("reset_successful"),
            data_type_id=ENGINEERING_SCENE_DATA_TYPE_ID,
            kind=COREX_SCENE_HANDLE_KIND,
            owner_scope="cache:tests:reset_success",
            dispose=lambda: reset_disposed.append("successful"),
        )
        reset_warnings: list[str] = []
        previous_generation = self.services.worker_generation
        self.services.reset(warn=reset_warnings.append)
        self.assertEqual(self.services.worker_generation, previous_generation + 1)
        self.assertCountEqual(reset_disposed, ["failed", "successful"])
        self.assertEqual(
            reset_warnings,
            ["Runtime handle automatic disposal failed."],
        )
        with self.assertRaisesRegex(StaleHandleError, "worker_generation is stale"):
            self.services.resolve_handle(reset_ref)

    def test_query_command_returns_serializable_backend_result_with_session_context(
        self,
    ) -> None:
        self.service.open_session(
            OpenViewerSessionCommand(
                workspace_id="ws_main",
                node_id="node_viewer",
                session_id="session_query",
                backend_id=ENGINEERING_VIEWER_BACKEND_ID,
                summary={"result_name": "displacement"},
                options={"representation": "surface"},
            )
        )
        backend = self.services.viewer_backend_registry.resolve(
            ENGINEERING_VIEWER_BACKEND_ID
        )
        with mock.patch.object(
            backend,
            "query",
            create=True,
            return_value=ViewerBackendQueryResult(
                supported=True,
                value={"distance": 5.0, "length_unit": "mm"},
            ),
        ) as query:
            event = self.service.handle_command(
                QueryViewerSessionCommand(
                    request_id="viewer_req_query",
                    workspace_id="ws_main",
                    node_id="node_viewer",
                    session_id="session_query",
                    backend_id=ENGINEERING_VIEWER_BACKEND_ID,
                    query_type="distance",
                    payload={"point_a": [0, 0, 0], "point_b": [3, 4, 0]},
                )
            )

        self.assertIsInstance(event, ViewerQueryResultEvent)
        self.assertTrue(event.supported)
        self.assertEqual(event.value["distance"], 5.0)
        request = query.call_args.args[0]
        self.assertEqual(request.query_type, "distance")
        self.assertEqual(request.session_summary["result_name"], "displacement")
        self.assertEqual(request.session_options["representation"], "surface")

    def test_open_session_demotes_stale_materialized_handles_to_proxy_state(
        self,
    ) -> None:
        dataset_ref = self.services.register_handle(
            _FakeViewerObject("materialized_scene"),
            data_type_id=ENGINEERING_SCENE_DATA_TYPE_ID,
            kind=COREX_SCENE_HANDLE_KIND,
            owner_scope="cache:tests:materialized_scene",
        )
        identity = {
            "workspace_id": "ws_main",
            "node_id": "node_engineering_viewer",
            "session_id": "session_stale",
            "backend_id": ENGINEERING_VIEWER_BACKEND_ID,
        }
        opened = self.service.open_session(
            OpenViewerSessionCommand(
                **identity,
                data_refs={"dataset": dataset_ref},
                transport={"kind": "engineering_scene_bundle"},
                live_open_status="ready",
                options={"live_mode": "full"},
            )
        )
        self.assertIsInstance(opened, ViewerSessionOpenedEvent)
        record = self.service._sessions[("ws_main", "session_stale")]  # noqa: SLF001
        session_dataset_ref = record.materialized_refs["dataset"]
        self.assertFalse(self.services.release_handle(session_dataset_ref))

        reopened = self.service.open_session(OpenViewerSessionCommand(**identity))

        self.assertIsInstance(reopened, ViewerSessionOpenedEvent)
        self.assertNotIn("dataset", reopened.data_refs)
        self.assertEqual(reopened.transport, {})
        self.assertEqual(reopened.options["live_mode"], "proxy")
        self.assertIn("dataset", reopened.summary["stale_ref_keys"])

    def test_options_update_preserves_engineering_live_transport_without_materialized_refs(
        self,
    ) -> None:
        transport = {
            "kind": "engineering_scene_bundle",
            "backend_id": ENGINEERING_VIEWER_BACKEND_ID,
        }
        opened = self.service.open_session(
            OpenViewerSessionCommand(
                request_id="viewer_req_open_engineering",
                workspace_id="ws_main",
                node_id="node_engineering_viewer",
                session_id="session_engineering",
                backend_id=ENGINEERING_VIEWER_BACKEND_ID,
                transport=transport,
                transport_revision=1,
                live_open_status="ready",
                options={"live_mode": "proxy"},
            )
        )

        self.assertIsInstance(opened, ViewerSessionOpenedEvent)
        updated = self.service.update_session(
            UpdateViewerSessionCommand(
                request_id="viewer_req_focus_engineering",
                workspace_id="ws_main",
                node_id="node_engineering_viewer",
                session_id="session_engineering",
                options={"live_mode": "full"},
            )
        )

        self.assertIsInstance(updated, ViewerSessionUpdatedEvent)
        self.assertEqual(updated.transport, transport)
        self.assertEqual(updated.live_open_status, "ready")
        self.assertEqual(updated.summary["cache_state"], "live_ready")
        self.assertFalse(updated.summary["has_materialized_data"])
        self.assertFalse(updated.options["rerun_required"])
        self.assertEqual(updated.options["live_mode"], "full")

    def test_materialize_fails_after_workspace_invalidation(self) -> None:
        fields_ref = self.services.register_handle(
            _FakeViewerObject("fields_cached"),
            data_type_id=ENGINEERING_SCENE_DATA_TYPE_ID,
            kind=COREX_SCENE_HANDLE_KIND,
            owner_scope="cache:tests:viewer_fields",
        )
        model_ref = self.services.register_handle(
            _FakeViewerObject("model_cached"),
            data_type_id=ENGINEERING_SCENE_DATA_TYPE_ID,
            kind=COREX_SCENE_HANDLE_KIND,
            owner_scope="cache:tests:viewer_model",
        )

        self.service.open_session(
            OpenViewerSessionCommand(
                request_id="viewer_req_open",
                workspace_id="ws_main",
                node_id="node_viewer",
                session_id="session_invalidated",
                backend_id=ENGINEERING_VIEWER_BACKEND_ID,
                data_refs={"fields": fields_ref, "model": model_ref},
            )
        )
        self.service.invalidate_workspace(
            "ws_main",
            reason="workspace_rerun",
            node_ids=None,
        )
        self.service.install_workspace_context(
            workspace_id="ws_main",
        )

        failed = self.service.materialize_data(
            MaterializeViewerDataCommand(
                request_id="viewer_req_materialize",
                workspace_id="ws_main",
                node_id="node_viewer",
                session_id="session_invalidated",
                workspace_invalidation_epoch=1,
            )
        )

        self.assertIsInstance(failed, ViewerSessionFailedEvent)
        self.assertIn("invalidated", failed.error)

    def test_scoped_and_empty_invalidation_preserve_unaffected_viewer_state(
        self,
    ) -> None:
        for node_id in ("viewer_a", "viewer_b"):
            self.service.open_session(
                OpenViewerSessionCommand(
                    request_id=f"open_{node_id}",
                    workspace_id="ws_main",
                    node_id=node_id,
                    session_id=f"session_{node_id}",
                    data_refs={"source": node_id},
                    transport={"kind": "mock_live", "node_id": node_id},
                )
            )
        unaffected_before = copy.deepcopy(
            self.service._sessions[("ws_main", "session_viewer_b")].public_projection()  # noqa: SLF001
        )

        self.assertEqual(
            self.service.invalidate_workspace(
                "ws_main",
                reason="workspace_rerun",
                node_ids=("viewer_a", "viewer_a"),
            ),
            1,
        )
        self.assertEqual(
            self.service._sessions[("ws_main", "session_viewer_b")].public_projection(),  # noqa: SLF001
            unaffected_before,
        )
        self.assertEqual(
            self.service._node_invalidation_epochs[("ws_main", "viewer_a")],  # noqa: SLF001
            1,
        )

        context_marker = object()
        self.service.install_workspace_context(
            workspace_id="ws_main",
            project_path="updated.cxproj",
            runtime_snapshot_context=context_marker,
        )
        self.assertIs(
            self.service._workspace_contexts["ws_main"].runtime_snapshot_context,  # noqa: SLF001
            context_marker,
        )
        self.assertEqual(
            self.service._sessions[("ws_main", "session_viewer_b")].public_projection(),  # noqa: SLF001
            unaffected_before,
        )

        stale = self.service.close_session(
            CloseViewerSessionCommand(
                request_id="late_close",
                workspace_id="ws_main",
                node_id="viewer_a",
                session_id="session_viewer_a",
            )
        )
        self.assertIsInstance(stale, ViewerSessionFailedEvent)
        self.assertIn("newer epoch", stale.error)

        reopened = self.service.open_session(
            OpenViewerSessionCommand(
                request_id="",
                workspace_id="ws_main",
                node_id="viewer_a",
                session_id="session_viewer_a",
                data_refs={"source": "viewer_a_recomputed"},
                transport={"kind": "mock_live", "revision": 2},
            )
        )
        self.assertIsInstance(reopened, ViewerSessionOpenedEvent)
        self.assertEqual(reopened.node_invalidation_epoch, 1)
        self.assertEqual(reopened.live_open_status, "ready")
        self.service.reset()
        self.assertEqual(
            self.service._workspace_invalidation_epochs["ws_main"],  # noqa: SLF001
            1,
        )
        self.assertNotIn(
            ("ws_main", "viewer_a"),
            self.service._node_invalidation_epochs,  # noqa: SLF001
        )

    def test_coerce_viewer_session_model_normalizes_current_typed_projection(
        self,
    ) -> None:
        payload = {
            "request_id": "viewer_req_open",
            "workspace_id": "ws_main",
            "node_id": "node_viewer",
            "session_id": "session_authoritative",
            "phase": "open",
            "request_id": "viewer_req_open",
            "playback_state": "paused",
            "step_index": 2,
            "playback": {"state": "paused", "step_index": 2},
            "cache_state": "live_ready",
            "backend_id": ENGINEERING_VIEWER_BACKEND_ID,
            "transport_revision": 4,
            "live_mode": "full",
            "live_open_status": "ready",
            "live_open_blocker": {},
            "data_refs": {"dataset": {"kind": "tests.dataset"}},
            "transport": {
                "kind": "scene_transport",
                "backend_id": ENGINEERING_VIEWER_BACKEND_ID,
            },
            "camera_state": {"zoom": 1.25},
            "summary": {"result_name": "displacement", "cache_state": "live_ready"},
            "options": {"live_mode": "proxy", "playback_state": "playing"},
        }

        session = coerce_viewer_session_model(payload)

        self.assertEqual(session["phase"], "open")
        self.assertEqual(session["backend_id"], ENGINEERING_VIEWER_BACKEND_ID)
        self.assertEqual(session["transport_revision"], 4)
        self.assertEqual(session["live_mode"], "full")
        self.assertEqual(session["playback"]["state"], "paused")
        self.assertEqual(session["summary"]["result_name"], "displacement")
        self.assertEqual(session["data_refs"], {"dataset": {"kind": "tests.dataset"}})

    def test_build_run_required_viewer_session_model_clears_live_transport_but_keeps_projection_summary(
        self,
    ) -> None:
        session_model = build_run_required_viewer_session_model(
            {
                "workspace_id": "ws_main",
                "node_id": "node_viewer",
                "session_id": "session_blocked",
                "phase": "open",
                "playback_state": "paused",
                "step_index": 5,
                "cache_state": "live_ready",
                "backend_id": ENGINEERING_VIEWER_BACKEND_ID,
                "transport_revision": 8,
                "live_open_status": "ready",
                "data_refs": {"dataset": {"kind": "tests.dataset"}},
                "transport": {
                    "kind": "scene_transport",
                    "backend_id": ENGINEERING_VIEWER_BACKEND_ID,
                    "manifest_path": "C:/temp/viewer/manifest.json",
                    "entry_path": "C:/temp/viewer/entry.vtm",
                },
                "camera_state": {"zoom": 1.1},
                "summary": {"result_name": "displacement", "set_label": "Set 4"},
                "options": {
                    "live_mode": "full",
                    "playback_state": "paused",
                    "step_index": 5,
                },
            },
            reason="workspace_rerun",
            run_id="run_live",
        )

        self.assertEqual(session_model["phase"], "blocked")
        self.assertEqual(session_model["live_open_status"], "blocked")
        self.assertTrue(session_model["live_open_blocker"]["rerun_required"])
        self.assertEqual(session_model["summary"]["result_name"], "displacement")
        self.assertEqual(
            session_model["summary"]["live_transport_release_reason"], "workspace_rerun"
        )
        self.assertEqual(session_model["summary"]["run_id"], "run_live")
        self.assertEqual(
            session_model["transport"],
            {
                "kind": "scene_transport",
                "backend_id": ENGINEERING_VIEWER_BACKEND_ID,
            },
        )
        self.assertEqual(session_model["data_refs"], {})
        self.assertEqual(session_model["options"]["live_mode"], "proxy")


if __name__ == "__main__":
    unittest.main()

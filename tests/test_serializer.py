from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
import ea_node_editor.persistence.serializer as serializer_module

from ea_node_editor.common.payload_tools import document_fingerprint
from ea_node_editor.graph.model import GraphModel
from ea_node_editor.graph.records import NodeLinkRecord
from ea_node_editor.nodes.bootstrap import build_default_registry
from ea_node_editor.nodes.builtins.web_viewer import (
    WEB_PAGE_VIEWER_DISPLAY_MODE_FIT_WIDTH,
    WEB_PAGE_VIEWER_TYPE_ID,
)
from ea_node_editor.nodes.registry import NodeRegistry
from ea_node_editor.nodes.node_specs import NodeTypeSpec, PortSpec, PropertySpec
from ea_node_editor.runtime_contracts import (
    GRAPH_DATA_TYPE_ID,
    ArrayDataRef,
    DataTree,
    DataTypeFamilySpec,
    DataTypeSpec,
    RuntimeArtifactRef,
    RuntimeHandleRef,
    TabularDataRef,
    TypedInlineValue,
)
from ea_node_editor.common.artifact_refs import (
    format_managed_artifact_ref,
    format_staged_artifact_ref,
)
from ea_node_editor.persistence.artifact_store import ProjectArtifactStore
from ea_node_editor.persistence.project_codec import (
    JsonProjectCodec,
    rewrite_project_artifact_refs,
)
from ea_node_editor.persistence.serializer import ProjectDocumentSnapshot, JsonProjectSerializer, ProjectSessionMetadata
from ea_node_editor.persistence.session_store import SessionAutosaveStore
from ea_node_editor.settings import SCHEMA_VERSION
from tests.serializer.round_trip_cases import SerializerRoundTripMixin
from tests.serializer.schema_cases import SerializerSchemaMixin
from tests.serializer.workflow_cases import SerializerWorkflowMixin
from ea_node_editor.ui_qml.graph_scene_bridge import GraphSceneBridge

_PERSISTENCE_NODE_TYPE_ID = "tests.persistence_values"
_INLINE_TYPE_ID = "Tests.Persistence.Inline"
_NEVER_INLINE_TYPE_ID = "Tests.Persistence.NeverInline"
_ARTIFACT_TYPE_ID = "Tests.Persistence.Artifact"
_OTHER_ARTIFACT_TYPE_ID = "Tests.Persistence.OtherArtifact"
_NEVER_ARTIFACT_TYPE_ID = "Tests.Persistence.NeverArtifact"


def _persistence_registry() -> NodeRegistry:
    registry = NodeRegistry()
    family = DataTypeFamilySpec(
        "tests.persistence",
        "Test Persistence",
        "data.test",
        "test",
    )
    registry.data_types.register_many(
        families=(family,),
        types=(
            DataTypeSpec(
                _INLINE_TYPE_ID,
                "Inline",
                family.family_id,
                lambda value: isinstance(value, dict),
                parents=(GRAPH_DATA_TYPE_ID,),
                carriers=frozenset({"inline"}),
                persistence="inline",
            ),
            DataTypeSpec(
                _NEVER_INLINE_TYPE_ID,
                "Never Inline",
                family.family_id,
                lambda value: isinstance(value, dict),
                parents=(_INLINE_TYPE_ID,),
                carriers=frozenset({"inline"}),
            ),
            DataTypeSpec(
                _ARTIFACT_TYPE_ID,
                "Artifact",
                family.family_id,
                lambda value: isinstance(value, RuntimeArtifactRef),
                parents=(GRAPH_DATA_TYPE_ID,),
                carriers=frozenset({"artifact"}),
                persistence="saved_artifact",
            ),
            DataTypeSpec(
                _OTHER_ARTIFACT_TYPE_ID,
                "Other Artifact",
                family.family_id,
                lambda value: isinstance(value, RuntimeArtifactRef),
                parents=(GRAPH_DATA_TYPE_ID,),
                carriers=frozenset({"artifact"}),
                persistence="saved_artifact",
            ),
            DataTypeSpec(
                _NEVER_ARTIFACT_TYPE_ID,
                "Never Artifact",
                family.family_id,
                lambda value: isinstance(value, RuntimeArtifactRef),
                parents=(_ARTIFACT_TYPE_ID,),
                carriers=frozenset({"artifact"}),
            ),
        ),
        owner_id="tests.persistence",
    )
    spec = NodeTypeSpec(
        _PERSISTENCE_NODE_TYPE_ID,
        "Persistence Values",
        ("Tests",),
        "",
        (PortSpec("result", "out", "data", GRAPH_DATA_TYPE_ID),),
        (
            PropertySpec("ordinary", "json", {}, "Ordinary"),
            PropertySpec(
                "inline",
                "json",
                {},
                "Inline",
                persistence_data_type_id=_INLINE_TYPE_ID,
            ),
            PropertySpec(
                "artifact",
                "path",
                "",
                "Artifact",
                persistence_data_type_id=_ARTIFACT_TYPE_ID,
            ),
        ),
    )
    registry.register_descriptor(spec, lambda: None)  # type: ignore[arg-type]
    return registry


def _persistence_model(**properties: object) -> GraphModel:
    model = GraphModel()
    workspace = model.active_workspace
    model.add_node(
        workspace.workspace_id,
        _PERSISTENCE_NODE_TYPE_ID,
        "Persistence Values",
        0.0,
        0.0,
        properties=dict(properties),
    )
    return model


def _managed_artifact_metadata(
    artifact_id: str,
    runtime_ref: RuntimeArtifactRef | None = None,
) -> dict[str, object]:
    entry: dict[str, object] = {
        "relative_path": f"nodes/Persistence [11111111]/in/{artifact_id}.bin",
    }
    if runtime_ref is not None:
        entry["runtime_artifact"] = runtime_ref.to_descriptor()
    return {
        "artifacts": {artifact_id: entry},
        "staged": {},
    }


def _staged_artifact_metadata(
    runtime_ref: RuntimeArtifactRef,
) -> dict[str, object]:
    return {
        "artifacts": {},
        "staged": {
            runtime_ref.artifact_id: {
                "relative_path": (
                    f"nodes/Persistence [11111111]/tmp/in/"
                    f"{runtime_ref.artifact_id}.bin"
                ),
                "runtime_artifact": runtime_ref.to_descriptor(),
            },
        },
    }


class SerializerTests(SerializerRoundTripMixin, SerializerWorkflowMixin, SerializerSchemaMixin, unittest.TestCase):
    def test_project_properties_reject_live_handles_datatrees_bytes_and_native_objects(self) -> None:
        serializer = JsonProjectSerializer(_persistence_registry())
        invalid_values = (
            RuntimeHandleRef(
                data_type_id=GRAPH_DATA_TYPE_ID,
                schema_version=1,
                handle_id="handle",
                kind="test",
                owner_scope="run",
                worker_generation=1,
            ),
            {"nested": [TabularDataRef("table", "resolver")]},
            {"nested": [ArrayDataRef("array", "resolver")]},
            DataTree.from_item("value"),
            {"nested": [b"bytes"]},
            {"nested": [object()]},
        )

        for value in invalid_values:
            with self.subTest(value_type=type(value).__name__):
                model = _persistence_model(ordinary=value)
                with self.assertRaises((TypeError, ValueError)):
                    serializer.to_persistent_document(model.project)

    def test_typed_inline_property_requires_opt_in_and_persistent_concrete_type(self) -> None:
        serializer = JsonProjectSerializer(_persistence_registry())
        allowed = TypedInlineValue(
            _INLINE_TYPE_ID,
            1,
            {"value": 3},
        )
        model = _persistence_model(inline=allowed)

        document = serializer.to_persistent_document(model.project)
        node_doc = document["workspaces"][0]["nodes"][0]
        self.assertEqual(
            node_doc["properties"]["inline"]["__ea_runtime_value__"],
            "typed_inline",
        )
        loaded = serializer.from_document(document)
        loaded_node = next(iter(loaded.workspaces.values())).nodes[
            node_doc["node_id"]
        ]
        self.assertEqual(loaded_node.properties["inline"], allowed)

        unauthorized = _persistence_model(ordinary=allowed)
        with self.assertRaisesRegex(ValueError, "does not permit typed persistence"):
            serializer.to_persistent_document(unauthorized.project)

        never = _persistence_model(
            inline=TypedInlineValue(
                _NEVER_INLINE_TYPE_ID,
                1,
                {"value": 3},
            )
        )
        with self.assertRaisesRegex(ValueError, "does not permit inline persistence"):
            serializer.to_persistent_document(never.project)

    def test_transient_temp_ref_is_allowed_but_final_project_write_rejects_it(self) -> None:
        registry = _persistence_registry()
        serializer = JsonProjectSerializer(registry)
        staged_ref = RuntimeArtifactRef.staged(
            "pending",
            data_type_id=_ARTIFACT_TYPE_ID,
            schema_version=1,
            format="bin",
            size_bytes=4,
            sha256="d" * 64,
            provenance="test",
        )
        self.assertEqual(
            registry.normalize_property_value(
                _PERSISTENCE_NODE_TYPE_ID,
                "artifact",
                staged_ref,
            ),
            staged_ref,
        )
        model = _persistence_model(artifact=staged_ref)
        model.project.metadata["artifact_store"] = _staged_artifact_metadata(
            staged_ref
        )
        document = serializer.to_persistent_document(model.project)
        self.assertEqual(
            document["workspaces"][0]["nodes"][0]["properties"]["artifact"],
            "temp://pending",
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            with self.assertRaisesRegex(ValueError, "temp://"):
                serializer.save_document(
                    str(Path(temp_dir) / "invalid.cxproj"),
                    document,
                )

        unowned = _persistence_model(artifact=staged_ref)
        with self.assertRaisesRegex(ValueError, "unowned staged artifact"):
            serializer.to_persistent_document(unowned.project)

        mismatched = _persistence_model(artifact=staged_ref)
        mismatched_ref = RuntimeArtifactRef.staged(
            "pending",
            data_type_id=_ARTIFACT_TYPE_ID,
            schema_version=2,
            format="other",
            size_bytes=5,
            sha256="e" * 64,
            provenance="other",
        )
        mismatched.project.metadata["artifact_store"] = (
            _staged_artifact_metadata(mismatched_ref)
        )
        with self.assertRaisesRegex(ValueError, "descriptor is invalid"):
            serializer.to_persistent_document(mismatched.project)

        invalid_descriptor = _persistence_model(artifact=staged_ref)
        invalid_descriptor.project.metadata["artifact_store"] = (
            _staged_artifact_metadata(staged_ref)
        )
        descriptor = invalid_descriptor.project.metadata["artifact_store"][
            "staged"
        ]["pending"]["runtime_artifact"]
        descriptor["schema_version"] = True
        with self.assertRaisesRegex(ValueError, "descriptor is invalid"):
            serializer.to_persistent_document(invalid_descriptor.project)

    def test_typed_literal_artifact_refs_require_owned_compatible_exact_descriptors(
        self,
    ) -> None:
        serializer = JsonProjectSerializer(_persistence_registry())
        for scope in ("managed", "staged"):
            factory = (
                RuntimeArtifactRef.managed
                if scope == "managed"
                else RuntimeArtifactRef.staged
            )
            runtime_ref = factory(
                f"{scope}_literal",
                data_type_id=_ARTIFACT_TYPE_ID,
                schema_version=1,
                format="bin",
                size_bytes=4,
                sha256="1" * 64,
                provenance="literal-test",
            )
            metadata_factory = (
                _managed_artifact_metadata
                if scope == "managed"
                else lambda _artifact_id, ref: _staged_artifact_metadata(ref)
            )

            valid = _persistence_model(artifact=runtime_ref.ref)
            valid.project.metadata["artifact_store"] = metadata_factory(
                runtime_ref.artifact_id,
                runtime_ref,
            )
            document = serializer.to_persistent_document(valid.project)
            self.assertEqual(
                document["workspaces"][0]["nodes"][0]["properties"]["artifact"],
                runtime_ref.ref,
            )

            unowned = _persistence_model(artifact=runtime_ref.ref)
            with self.subTest(scope=scope, case="unowned"):
                with self.assertRaisesRegex(
                    ValueError,
                    f"unowned {scope} artifact",
                ):
                    serializer.to_persistent_document(unowned.project)

            other_ref = factory(
                runtime_ref.artifact_id,
                data_type_id=_OTHER_ARTIFACT_TYPE_ID,
                schema_version=1,
                format="bin",
                size_bytes=4,
                sha256="1" * 64,
                provenance="literal-test",
            )
            mismatched = _persistence_model(artifact=runtime_ref.ref)
            mismatched.project.metadata["artifact_store"] = metadata_factory(
                runtime_ref.artifact_id,
                other_ref,
            )
            with self.subTest(scope=scope, case="mismatched"):
                with self.assertRaisesRegex(ValueError, "descriptor is invalid"):
                    serializer.to_persistent_document(mismatched.project)

            malformed = _persistence_model(artifact=runtime_ref.ref)
            malformed.project.metadata["artifact_store"] = metadata_factory(
                runtime_ref.artifact_id,
                runtime_ref,
            )
            section = "artifacts" if scope == "managed" else "staged"
            descriptor = malformed.project.metadata["artifact_store"][section][
                runtime_ref.artifact_id
            ]["runtime_artifact"]
            descriptor["schema_version"] = True
            with self.subTest(scope=scope, case="malformed"):
                with self.assertRaisesRegex(ValueError, "descriptor is invalid"):
                    serializer.to_persistent_document(malformed.project)

    def test_saved_typed_literal_load_and_reserialize_preserves_owned_descriptor(
        self,
    ) -> None:
        serializer = JsonProjectSerializer(_persistence_registry())
        runtime_ref = RuntimeArtifactRef.managed(
            "saved_literal_round_trip",
            data_type_id=_ARTIFACT_TYPE_ID,
            schema_version=1,
            format="bin",
            size_bytes=4,
            sha256="2" * 64,
            provenance="round-trip",
        )
        model = _persistence_model(artifact=runtime_ref.ref)
        model.project.metadata["artifact_store"] = _managed_artifact_metadata(
            runtime_ref.artifact_id,
            runtime_ref,
        )
        document = serializer.to_persistent_document(model.project)
        node_doc = document["workspaces"][0]["nodes"][0]
        self.assertEqual(document["schema_version"], SCHEMA_VERSION)
        self.assertEqual(node_doc["properties"]["artifact"], runtime_ref.ref)

        loaded = serializer.from_document(copy.deepcopy(document))
        loaded_node = loaded.workspaces[document["active_workspace_id"]].nodes[
            node_doc["node_id"]
        ]
        self.assertEqual(loaded_node.properties["artifact"], runtime_ref.ref)
        self.assertEqual(
            loaded.metadata["artifact_store"]["artifacts"][
                runtime_ref.artifact_id
            ]["runtime_artifact"],
            runtime_ref.to_descriptor(),
        )

        reserialized = serializer.to_persistent_document(loaded)
        reserialized_node = reserialized["workspaces"][0]["nodes"][0]
        self.assertEqual(reserialized["schema_version"], SCHEMA_VERSION)
        self.assertEqual(
            reserialized_node["properties"]["artifact"],
            runtime_ref.ref,
        )
        self.assertEqual(
            reserialized["metadata"]["artifact_store"]["artifacts"][
                runtime_ref.artifact_id
            ]["runtime_artifact"],
            runtime_ref.to_descriptor(),
        )

    def test_final_project_write_requires_canonical_owned_refs_in_properties_and_metadata(self) -> None:
        serializer = JsonProjectSerializer(_persistence_registry())
        document = serializer.to_persistent_document(
            _persistence_model(ordinary="saved://source").project
        )
        document["metadata"]["future_import"] = {
            "source_ref": "saved://source",
            "report_ref": "saved://report",
        }
        document["metadata"]["artifact_store"] = {
            "artifacts": {
                "source": {
                    "relative_path": "nodes/Import [11111111]/in/source.bin",
                },
                "report": {
                    "relative_path": "nodes/Import [11111111]/out/report.json",
                },
            },
            "staged": {},
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "owned.cxproj"
            serializer.save_document(str(target), document)
            saved = json.loads(target.read_text(encoding="utf-8"))
        self.assertEqual(saved["schema_version"], SCHEMA_VERSION)
        self.assertEqual(
            saved["metadata"]["future_import"]["source_ref"],
            "saved://source",
        )

        unowned = copy.deepcopy(document)
        unowned["metadata"]["future_import"]["report_ref"] = "saved://missing"
        with tempfile.TemporaryDirectory() as temp_dir:
            with self.assertRaisesRegex(ValueError, "unowned managed artifact"):
                serializer.save_document(
                    str(Path(temp_dir) / "unowned.cxproj"),
                    unowned,
                )

        for malformed in (
            "SAVED://source",
            "saved://bad/id",
            " saved://source",
        ):
            invalid = copy.deepcopy(document)
            invalid["metadata"]["future_import"]["source_ref"] = malformed
            with self.subTest(malformed=malformed), tempfile.TemporaryDirectory() as temp_dir:
                with self.assertRaisesRegex(ValueError, "malformed artifact ref"):
                    serializer.save_document(
                        str(Path(temp_dir) / "malformed.cxproj"),
                        invalid,
                    )

    def test_final_project_write_rejects_forbidden_values_outside_node_properties(
        self,
    ) -> None:
        serializer = JsonProjectSerializer(_persistence_registry())
        document = serializer.to_persistent_document(
            _persistence_model(ordinary={}).project
        )
        invalid_payloads = (
            (
                "runtime_marker",
                {"__ea_runtime_value__": "runtime_handle"},
                ValueError,
                "unauthorized runtime marker",
            ),
            (
                "temp_key",
                {"temp://pending": "value"},
                ValueError,
                "temp://",
            ),
            (
                "managed_key",
                {"saved://missing": "value"},
                ValueError,
                "unowned managed artifact",
            ),
            (
                "malformed_key",
                {"SAVED://source": "value"},
                ValueError,
                "malformed artifact ref",
            ),
            (
                "native_object",
                {"value": object()},
                TypeError,
                "strict JSON values",
            ),
        )

        for name, payload, error_type, message in invalid_payloads:
            invalid = copy.deepcopy(document)
            invalid["metadata"]["future_payload"] = payload
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temp_dir:
                with self.assertRaisesRegex(error_type, message):
                    serializer.save_document(
                        str(Path(temp_dir) / f"{name}.cxproj"),
                        invalid,
                    )

    def test_final_project_write_does_not_exempt_property_containers_or_aliases(
        self,
    ) -> None:
        serializer = JsonProjectSerializer(_persistence_registry())
        root_marker = serializer.to_persistent_document(
            _persistence_model(ordinary={}).project
        )
        root_marker["workspaces"][0]["nodes"][0]["properties"] = {
            "__ea_runtime_value__": "runtime_handle",
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            with self.assertRaisesRegex(ValueError, "unauthorized runtime marker"):
                serializer.save_document(
                    str(Path(temp_dir) / "root_marker.cxproj"),
                    root_marker,
                )

        aliased = serializer.to_persistent_document(
            _persistence_model(
                inline=TypedInlineValue(
                    _INLINE_TYPE_ID,
                    1,
                    {"value": 3},
                )
            ).project
        )
        properties = aliased["workspaces"][0]["nodes"][0]["properties"]
        aliased["metadata"]["property_alias"] = properties
        with tempfile.TemporaryDirectory() as temp_dir:
            with self.assertRaisesRegex(ValueError, "unauthorized runtime marker"):
                serializer.save_document(
                    str(Path(temp_dir) / "aliased_properties.cxproj"),
                    aliased,
                )

    def test_typed_managed_artifact_requires_catalog_policy_and_exact_descriptor(self) -> None:
        serializer = JsonProjectSerializer(_persistence_registry())
        runtime_ref = RuntimeArtifactRef.managed(
            "typed",
            data_type_id=_ARTIFACT_TYPE_ID,
            schema_version=1,
            format="bin",
            size_bytes=4,
            sha256="a" * 64,
            provenance="test",
        )
        model = _persistence_model(artifact=runtime_ref)
        model.project.metadata["artifact_store"] = _managed_artifact_metadata(
            runtime_ref.artifact_id,
            runtime_ref,
        )
        document = serializer.to_persistent_document(model.project)
        self.assertEqual(
            document["workspaces"][0]["nodes"][0]["properties"]["artifact"],
            runtime_ref.ref,
        )

        with (
            patch.object(
                ProjectArtifactStore,
                "resolve_managed_path",
                side_effect=AssertionError("validation must not resolve artifact paths"),
            ),
            tempfile.TemporaryDirectory() as temp_dir,
        ):
            serializer.save_document(str(Path(temp_dir) / "typed.cxproj"), document)

        mismatched_ref = RuntimeArtifactRef.managed(
            "typed",
            data_type_id=_ARTIFACT_TYPE_ID,
            schema_version=2,
            format="other",
            size_bytes=5,
            sha256="c" * 64,
            provenance="other",
        )
        mismatched_model = _persistence_model(artifact=runtime_ref)
        mismatched_model.project.metadata["artifact_store"] = (
            _managed_artifact_metadata(
                runtime_ref.artifact_id,
                mismatched_ref,
            )
        )
        with self.assertRaisesRegex(ValueError, "descriptor is invalid"):
            serializer.to_persistent_document(mismatched_model.project)

        wrong_type = copy.deepcopy(document)
        descriptor = wrong_type["metadata"]["artifact_store"]["artifacts"]["typed"][
            "runtime_artifact"
        ]
        descriptor["schema_version"] = True
        with tempfile.TemporaryDirectory() as temp_dir:
            with self.assertRaisesRegex(ValueError, "descriptor is invalid"):
                serializer.save_document(
                    str(Path(temp_dir) / "wrong_descriptor.cxproj"),
                    wrong_type,
                )

        never_ref = RuntimeArtifactRef.managed(
            "never",
            data_type_id=_NEVER_ARTIFACT_TYPE_ID,
            schema_version=1,
            format="bin",
            size_bytes=4,
            sha256="b" * 64,
            provenance="test",
        )
        with self.assertRaisesRegex(ValueError, "does not permit saved_artifact"):
            serializer.to_persistent_document(
                _persistence_model(artifact=never_ref).project
            )

    def test_document_fingerprint_is_deterministic_lowercase_sha256(self) -> None:
        first = {"z": [1, {"name": "caf\u00e9"}], "a": {"enabled": True}}
        reordered = {"a": {"enabled": True}, "z": [1, {"name": "caf\u00e9"}]}
        before = copy.deepcopy(first)

        fingerprint = document_fingerprint(first)

        self.assertRegex(fingerprint, r"^[0-9a-f]{64}$")
        self.assertEqual(
            document_fingerprint({}),
            "44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a",
        )
        self.assertEqual(fingerprint, document_fingerprint(reordered))
        self.assertNotEqual(fingerprint, document_fingerprint({**reordered, "changed": True}))
        self.assertEqual(first, before)

    def test_save_document_preserves_input_and_emits_the_same_bytes(self) -> None:
        serializer = JsonProjectSerializer(NodeRegistry())
        document = {
            "schema_version": SCHEMA_VERSION,
            "project_id": "non_mutating_save",
            "name": "Non-mutating Save",
            "workspaces": [],
            "metadata": {"nested": {"values": [3, 2, 1]}},
        }
        before = copy.deepcopy(document)

        with tempfile.TemporaryDirectory() as temp_dir:
            saved_path = Path(temp_dir) / "saved.cxproj"
            previous_bytes_path = Path(temp_dir) / "previous.cxproj"
            previous_bytes_path.write_text(
                json.dumps(copy.deepcopy(dict(document)), indent=2, sort_keys=True, ensure_ascii=True),
                encoding="utf-8",
            )

            serializer.save_document(str(saved_path), document)

            self.assertEqual(saved_path.read_bytes(), previous_bytes_path.read_bytes())
        self.assertEqual(document, before)

    def test_old_fingerprint_mismatches_once_then_autosave_skips_unchanged_document(self) -> None:
        serializer = JsonProjectSerializer(NodeRegistry())
        document = {
            "schema_version": SCHEMA_VERSION,
            "project_id": "old_fingerprint",
            "name": "Old Fingerprint",
            "workspaces": [],
            "metadata": {},
        }
        old_fingerprint = json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=True)

        with tempfile.TemporaryDirectory() as temp_dir:
            autosave_path = Path(temp_dir) / "autosave.cxproj"
            store = SessionAutosaveStore(
                serializer=serializer,
                session_path_provider=lambda: Path(temp_dir) / "session.json",
                autosave_path_provider=lambda: autosave_path,
            )

            with patch(
                "ea_node_editor.common.payload_tools.json.dumps",
                wraps=json.dumps,
            ) as encode_json:
                snapshot = ProjectDocumentSnapshot.from_owned_document(document)
                rewritten_fingerprint = store.autosave_if_changed(
                    last_fingerprint=old_fingerprint,
                    project_snapshot=snapshot,
                )

            self.assertNotEqual(rewritten_fingerprint, old_fingerprint)
            self.assertRegex(rewritten_fingerprint, r"^[0-9a-f]{64}$")
            self.assertEqual(encode_json.call_count, 1)
            self.assertEqual(autosave_path.read_text(encoding="utf-8"), snapshot.encoded_payload)
            self.assertEqual(json.loads(autosave_path.read_text(encoding="utf-8")), document)
            with patch("ea_node_editor.persistence.session_store.write_json_atomic") as atomic_write:
                repeated_fingerprint = store.autosave_if_changed(
                    last_fingerprint=rewritten_fingerprint,
                    project_snapshot=snapshot,
                )
            self.assertEqual(repeated_fingerprint, rewritten_fingerprint)
            atomic_write.assert_not_called()

    def test_autosave_atomic_replace_failure_keeps_existing_document(self) -> None:
        serializer = JsonProjectSerializer(NodeRegistry())
        snapshot = ProjectDocumentSnapshot.from_owned_document(
            {
                "schema_version": SCHEMA_VERSION,
                "project_id": "atomic_failure",
                "name": "Atomic Failure",
                "workspaces": [],
                "metadata": {},
            }
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            autosave_path = Path(temp_dir) / "autosave.cxproj"
            autosave_path.write_text("previous autosave", encoding="utf-8")
            store = SessionAutosaveStore(
                serializer=serializer,
                session_path_provider=lambda: Path(temp_dir) / "session.json",
                autosave_path_provider=lambda: autosave_path,
            )

            with patch.object(Path, "replace", side_effect=OSError("replace failed")):
                with self.assertRaisesRegex(OSError, "replace failed"):
                    store.autosave_if_changed(
                        last_fingerprint="previous-fingerprint",
                        project_snapshot=snapshot,
                    )

            self.assertEqual(autosave_path.read_text(encoding="utf-8"), "previous autosave")

    def test_project_document_snapshot_from_owned_document_keeps_document_identity(self) -> None:
        document = {
            "schema_version": SCHEMA_VERSION,
            "project_id": "owned_doc",
            "name": "Owned",
            "workspaces": [],
            "metadata": {},
        }

        snapshot = ProjectDocumentSnapshot.from_owned_document(document)

        self.assertIs(snapshot.document, document)
        self.assertEqual(snapshot.fingerprint, JsonProjectSerializer.snapshot_from_mapping(document).fingerprint)

    def test_owned_node_normalization_matches_defensive_external_copy(self) -> None:
        codec = JsonProjectCodec(NodeRegistry())
        cases = (
            {
                "node_id": "web",
                "type_id": WEB_PAGE_VIEWER_TYPE_ID,
                "properties": {"start_location": "https://example.com"},
                "owner_backdrop_id": "runtime-owner",
            },
            {
                "node_id": "plot",
                "type_id": "plot.scatter",
                "properties": {"preview_series": [1, 2, 3], "title": "Series"},
                "member_node_ids": ["runtime-member"],
            },
        )

        for payload in cases:
            with self.subTest(type_id=payload["type_id"]):
                before = copy.deepcopy(payload)
                owned = copy.deepcopy(payload)
                defensive = codec._copy_node_mapping(payload)  # noqa: SLF001

                normalized = codec._normalize_owned_node_mapping(owned)  # noqa: SLF001

                self.assertIs(normalized, owned)
                self.assertEqual(normalized, defensive)
                self.assertEqual(payload, before)

    def test_runtime_document_skips_second_copy_but_stays_independent_from_graph(self) -> None:
        model = GraphModel()
        workspace = model.active_workspace
        node = model.add_node(
            workspace.workspace_id,
            "core.logger",
            "Logger",
            20.0,
            40.0,
            properties={"nested": {"values": [1, 2, 3]}},
            visual_style={"fill": "#123456"},
        )
        serializer = JsonProjectSerializer(NodeRegistry())

        with patch.object(
            JsonProjectCodec,
            "_copy_mapping",
            wraps=JsonProjectCodec._copy_mapping,  # noqa: SLF001
        ) as copy_mapping:
            document = serializer.to_document(model.project)

        copy_mapping.assert_not_called()
        workspace_doc = next(
            item for item in document["workspaces"] if item["workspace_id"] == workspace.workspace_id
        )
        node_doc = next(
            item for item in workspace_doc["nodes"] if item["node_id"] == node.node_id
        )
        node_doc["properties"]["nested"]["values"].append(4)
        node_doc["visual_style"]["fill"] = "#abcdef"

        self.assertEqual(node.properties, {"nested": {"values": [1, 2, 3]}})
        self.assertEqual(node.visual_style, {"fill": "#123456"})

    def test_rewrite_project_artifact_refs_returns_original_payload_without_replacements(self) -> None:
        payload = {
            "source_path": format_staged_artifact_ref("pending_output"),
            "nested": [format_managed_artifact_ref("existing_asset")],
        }

        self.assertIs(rewrite_project_artifact_refs(payload, {}), payload)
        self.assertIs(
            rewrite_project_artifact_refs(
                payload,
                {
                    "": format_managed_artifact_ref("ignored"),
                    format_staged_artifact_ref("pending_output"): "",
                },
            ),
            payload,
        )

    def test_rewrite_project_artifact_refs_normalizes_promoted_typed_carrier(
        self,
    ) -> None:
        staged_ref = RuntimeArtifactRef.staged(
            "pending_output",
            data_type_id=_ARTIFACT_TYPE_ID,
            schema_version=1,
            format="bin",
            size_bytes=4,
            sha256="f" * 64,
            provenance="test",
        )

        rewritten = rewrite_project_artifact_refs(
            {"artifact": staged_ref},
            {staged_ref.ref: format_managed_artifact_ref(staged_ref.artifact_id)},
        )

        self.assertEqual(
            rewritten["artifact"],
            format_managed_artifact_ref(staged_ref.artifact_id),
        )

    def test_project_session_metadata_exposes_typed_substructures_and_preserves_extra_namespaces(self) -> None:
        metadata = ProjectSessionMetadata.from_mapping(
            {
                "ui": {
                    "script_editor": {
                        "visible": True,
                    },
                    "panel_state": {
                        "inspector": "expanded",
                    },
                },
                "workflow_settings": {
                    "solver_config": {
                        "thread_count": 16,
                    },
                },
                "artifact_store": {
                    "staged": {
                        "pending_output": {
                            "relative_path": "outputs/run.txt",
                            "slot": "process_run.stdout",
                        }
                    }
                },
                "solution_store": {
                    "schema_version": 1,
                    "solution_namespace_id": "namespace",
                    "active_generation_id": "a" * 32,
                    "active_manifest_set_digest": "b" * 64,
                },
            }
        )

        self.assertTrue(metadata.ui.script_editor.visible)
        self.assertFalse(metadata.ui.script_editor.floating)
        self.assertEqual(metadata.ui.extra["panel_state"], {"inspector": "expanded"})
        self.assertEqual(metadata.workflow_settings["solver_config"]["thread_count"], 16)
        self.assertIn("memory_limit_gb", metadata.workflow_settings["solver_config"])
        self.assertEqual(metadata.extra["artifact_store"]["staged"]["pending_output"]["slot"], "process_run.stdout")

        round_tripped = metadata.to_mapping()
        self.assertEqual(
            round_tripped["ui"]["script_editor"],
            {
                "visible": True,
                "floating": False,
                "width": 0.0,
            },
        )
        self.assertEqual(round_tripped["ui"]["panel_state"], {"inspector": "expanded"})
        self.assertEqual(
            round_tripped["artifact_store"],
            copy.deepcopy(metadata.extra["artifact_store"]),
        )
        self.assertEqual(
            round_tripped["solution_store"],
            metadata.extra["solution_store"],
        )

    def test_project_codec_preserves_solution_store_metadata_without_migration(self) -> None:
        registry = build_default_registry()
        serializer = JsonProjectSerializer(registry)
        model = GraphModel()
        pointer = {
            "schema_version": 99,
            "solution_namespace_id": "original-namespace",
            "active_generation_id": "not-interpreted-by-codec",
            "active_manifest_set_digest": "original-metadata",
            "unknown": {"preserved": True},
        }
        model.project.replace_metadata(
            {**model.project.metadata, "solution_store": pointer}
        )

        loaded = serializer.from_document(serializer.to_document(model.project))

        self.assertEqual(loaded.metadata["solution_store"], pointer)

    def test_script_editor_session_metadata_normalizes_panel_width(self) -> None:
        def width_for(value: object) -> float:
            metadata = ProjectSessionMetadata.from_mapping(
                {"ui": {"script_editor": {"visible": True, "width": value}}}
            )
            return metadata.ui.script_editor.width

        self.assertEqual(width_for(640), 640.0)
        self.assertEqual(width_for(512.5), 512.5)
        self.assertEqual(width_for("720"), 720.0)
        self.assertEqual(width_for(0), 0.0)
        self.assertEqual(width_for(-40), 0.0)
        self.assertEqual(width_for("nonsense"), 0.0)
        self.assertEqual(width_for(None), 0.0)
        self.assertEqual(width_for(10_000), 4000.0)

        defaulted = ProjectSessionMetadata.from_mapping({"ui": {"script_editor": {"visible": True}}})
        self.assertEqual(defaulted.ui.script_editor.width, 0.0)

        round_tripped = ProjectSessionMetadata.from_mapping(
            {"ui": {"script_editor": {"visible": True, "width": 512.0}}}
        ).to_mapping()
        self.assertEqual(round_tripped["ui"]["script_editor"]["width"], 512.0)

    def test_group_backdrop_load_recomputes_membership_and_drops_persisted_membership_fields(self) -> None:
        registry = build_default_registry()
        model = GraphModel()
        workspace = model.active_workspace
        backdrop = model.add_node(
            workspace.workspace_id,
            "passive.annotation.group_backdrop",
            "Group",
            80.0,
            80.0,
        )
        model.set_node_size(workspace.workspace_id, backdrop.node_id, 360.0, 240.0)
        logger = model.add_node(workspace.workspace_id, "core.logger", "Logger", 140.0, 140.0)

        serializer = JsonProjectSerializer(registry)
        document = serializer.to_document(model.project)
        workspace_doc = next(ws for ws in document["workspaces"] if ws["workspace_id"] == workspace.workspace_id)
        backdrop_doc = next(node for node in workspace_doc["nodes"] if node["node_id"] == backdrop.node_id)
        logger_doc = next(node for node in workspace_doc["nodes"] if node["node_id"] == logger.node_id)
        backdrop_doc.update(
            {
                "owner_backdrop_id": "stale-owner",
                "backdrop_depth": 99,
                "member_node_ids": ["stale-node"],
                "member_backdrop_ids": ["stale-backdrop"],
                "contained_node_ids": ["stale-node"],
                "contained_backdrop_ids": ["stale-backdrop"],
            }
        )
        logger_doc.update(
            {
                "owner_backdrop_id": "wrong-backdrop",
                "backdrop_depth": 42,
            }
        )

        loaded_project = serializer.from_document(document)
        reserialized = serializer.to_document(loaded_project)
        reserialized_workspace_doc = next(
            ws for ws in reserialized["workspaces"] if ws["workspace_id"] == workspace.workspace_id
        )
        serialized_nodes = {
            node["node_id"]: node
            for node in reserialized_workspace_doc["nodes"]
        }
        for node_id in (backdrop.node_id, logger.node_id):
            for key in (
                "owner_backdrop_id",
                "backdrop_depth",
                "member_node_ids",
                "member_backdrop_ids",
                "contained_node_ids",
                "contained_backdrop_ids",
            ):
                self.assertNotIn(key, serialized_nodes[node_id])

        loaded_model = GraphModel(loaded_project)
        scene = GraphSceneBridge()
        scene.set_workspace(loaded_model, registry, workspace.workspace_id)
        payloads = {
            payload["node_id"]: payload
            for payload in [*scene.nodes_model, *scene.backdrop_nodes_model]
        }
        self.assertEqual(payloads[logger.node_id]["owner_backdrop_id"], backdrop.node_id)
        self.assertEqual(payloads[logger.node_id]["backdrop_depth"], 1)
        self.assertEqual(payloads[backdrop.node_id]["member_node_ids"], [logger.node_id])

    def test_folder_explorer_persistence_keeps_only_semantic_current_path_state(self) -> None:
        registry = build_default_registry()
        model = GraphModel()
        workspace = model.active_workspace
        folder_node = model.add_node(
            workspace.workspace_id,
            "io.folder_explorer",
            "Folder Explorer",
            80.0,
            120.0,
            properties={"current_path": "C:/Projects/Input"},
        )

        serializer = JsonProjectSerializer(registry)
        document = serializer.to_persistent_document(model.project)
        workspace_doc = next(ws for ws in document["workspaces"] if ws["workspace_id"] == workspace.workspace_id)
        node_doc = next(node for node in workspace_doc["nodes"] if node["node_id"] == folder_node.node_id)

        self.assertEqual(node_doc["type_id"], "io.folder_explorer")
        self.assertEqual(node_doc["properties"], {"current_path": "C:/Projects/Input"})
        serialized_node_doc = json.dumps(node_doc, sort_keys=True)
        for transient_key in (
            "navigationHistory",
            "navigation_history",
            "searchText",
            "search_text",
            "sortKey",
            "sort_key",
            "sortReverse",
            "sort_reverse",
            "selectedIndex",
            "selected_row",
            "contextEntryIndex",
            "context_menu_position",
            "maximized",
        ):
            self.assertNotIn(transient_key, serialized_node_doc)

    def test_folder_explorer_load_discards_surface_transients_before_reserialize(self) -> None:
        registry = build_default_registry()
        serializer = JsonProjectSerializer(registry)
        model = GraphModel()
        workspace = model.active_workspace
        folder_node = model.add_node(
            workspace.workspace_id,
            "io.folder_explorer",
            "Folder Explorer",
            80.0,
            120.0,
            properties={"current_path": "C:/Projects/Input"},
        )
        document = serializer.to_document(model.project)
        workspace_doc = next(ws for ws in document["workspaces"] if ws["workspace_id"] == workspace.workspace_id)
        node_doc = next(node for node in workspace_doc["nodes"] if node["node_id"] == folder_node.node_id)
        node_doc["properties"].update(
            {
                "navigation_history": ["C:/Projects", "C:/Projects/Input"],
                "search_text": "report",
                "sort_key": "modified",
                "selected_row": 2,
            }
        )
        node_doc["context_menu_position"] = {"x": 12, "y": 20}
        node_doc["maximized"] = True

        loaded_project = serializer.from_document(document)
        reserialized = serializer.to_persistent_document(loaded_project)
        reserialized_workspace_doc = next(
            ws for ws in reserialized["workspaces"] if ws["workspace_id"] == workspace.workspace_id
        )
        reserialized_node_doc = next(
            node for node in reserialized_workspace_doc["nodes"] if node["node_id"] == folder_node.node_id
        )

        self.assertEqual(reserialized_node_doc["properties"], {"current_path": "C:/Projects/Input"})
        serialized_node_doc = json.dumps(reserialized_node_doc, sort_keys=True)
        for transient_key in (
            "navigation_history",
            "search_text",
            "sort_key",
            "selected_row",
            "context_menu_position",
            "maximized",
        ):
            self.assertNotIn(transient_key, serialized_node_doc)

    def test_web_page_viewer_round_trip_persists_safe_browser_state_only(self) -> None:
        registry = build_default_registry()
        model = GraphModel()
        workspace = model.active_workspace
        properties = registry.default_properties(WEB_PAGE_VIEWER_TYPE_ID)
        properties.update(
            {
                "start_location": "https://example.com/docs",
                "persist_browser_state": True,
                "browser_state": {
                    "current_url": "https://example.com/docs",
                    "zoom_factor": 1.25,
                },
            }
        )
        node = model.add_node(
            workspace.workspace_id,
            WEB_PAGE_VIEWER_TYPE_ID,
            "Web Page Viewer",
            80.0,
            120.0,
            properties=properties,
        )

        serializer = JsonProjectSerializer(registry)
        document = serializer.to_persistent_document(model.project)
        loaded_project = serializer.from_document(document)
        reserialized = serializer.to_persistent_document(loaded_project)
        workspace_doc = next(ws for ws in reserialized["workspaces"] if ws["workspace_id"] == workspace.workspace_id)
        node_doc = next(item for item in workspace_doc["nodes"] if item["node_id"] == node.node_id)

        self.assertEqual(node_doc["type_id"], WEB_PAGE_VIEWER_TYPE_ID)
        self.assertEqual(
            node_doc["properties"],
            {
                "start_location": "https://example.com/docs",
                "display_mode": WEB_PAGE_VIEWER_DISPLAY_MODE_FIT_WIDTH,
                "show_title": True,
                "show_frame": True,
                "persist_browser_state": True,
                "browser_state": {
                    "current_url": "https://example.com/docs",
                    "zoom_factor": 1.25,
                },
                "preview_ref": {},
            },
        )
        serialized_node_doc = json.dumps(node_doc, sort_keys=True).lower()
        for unsafe_key in (
            "cookie",
            "cache",
            "credential",
            "session_storage",
            "local_storage",
            "page_content",
            "html",
        ):
            self.assertNotIn(unsafe_key, serialized_node_doc)

    def test_web_page_viewer_save_sanitizes_injected_browser_state(self) -> None:
        registry = build_default_registry()
        model = GraphModel()
        workspace = model.active_workspace
        properties = registry.default_properties(WEB_PAGE_VIEWER_TYPE_ID)
        properties.update(
            {
                "start_location": "https://example.com/docs",
                "persist_browser_state": True,
                "browser_state": {
                    "current_location": "example.com/current",
                    "zoom": 2.25,
                    "cookies": [{"name": "sid", "value": "secret"}],
                    "local_storage": {"token": "secret"},
                    "session_storage": {"csrf": "secret"},
                    "cache": {"entry": "secret"},
                    "credentials": {"username": "user", "password": "secret"},
                    "page_content": "<html>secret</html>",
                },
                "cookies": "top-level secret",
                "credentials": {"password": "top-level secret"},
            }
        )
        node = model.add_node(
            workspace.workspace_id,
            WEB_PAGE_VIEWER_TYPE_ID,
            "Web Page Viewer",
            80.0,
            120.0,
            properties=properties,
        )

        serializer = JsonProjectSerializer(registry)
        document = serializer.to_persistent_document(model.project)
        workspace_doc = next(ws for ws in document["workspaces"] if ws["workspace_id"] == workspace.workspace_id)
        node_doc = next(item for item in workspace_doc["nodes"] if item["node_id"] == node.node_id)

        self.assertEqual(
            node_doc["properties"]["browser_state"],
            {
                "current_url": "https://example.com/current",
                "zoom_factor": 2.25,
            },
        )
        serialized_browser_state = json.dumps(node_doc["properties"]["browser_state"], sort_keys=True).lower()
        serialized_node_doc = json.dumps(node_doc, sort_keys=True).lower()
        for unsafe_key in (
            "cookie",
            "cache",
            "credential",
            "password",
            "session_storage",
            "local_storage",
            "page_content",
            "html",
        ):
            self.assertNotIn(unsafe_key, serialized_browser_state)
            self.assertNotIn(unsafe_key, serialized_node_doc)

    def test_web_page_viewer_load_and_disabled_persistence_drop_browser_state(self) -> None:
        registry = build_default_registry()
        serializer = JsonProjectSerializer(registry)
        payload = {
            "schema_version": SCHEMA_VERSION,
            "project_id": "proj_web_page_state",
            "name": "Web Page State",
            "active_workspace_id": "ws_web",
            "workspace_order": ["ws_web"],
            "workspaces": [
                {
                    "workspace_id": "ws_web",
                    "name": "Workspace Web",
                    "active_view_id": "view_web",
                    "views": [
                        {
                            "view_id": "view_web",
                            "name": "V1",
                            "zoom": 1.0,
                            "pan_x": 0.0,
                            "pan_y": 0.0,
                        }
                    ],
                    "nodes": [
                        {
                            "node_id": "node_checked",
                            "type_id": WEB_PAGE_VIEWER_TYPE_ID,
                            "title": "Checked",
                            "x": 80.0,
                            "y": 120.0,
                            "properties": {
                                "start_location": "https://example.com/docs",
                                "persist_browser_state": True,
                                "browser_state": {
                                    "current_url": "https://example.com/current",
                                    "zoom_factor": 1.75,
                                    "cookies": "secret",
                                    "local_storage": {"token": "secret"},
                                    "session_storage": {"csrf": "secret"},
                                    "credentials": {"password": "secret"},
                                    "page_content": "<html>secret</html>",
                                },
                            },
                        },
                        {
                            "node_id": "node_unchecked",
                            "type_id": WEB_PAGE_VIEWER_TYPE_ID,
                            "title": "Unchecked",
                            "x": 180.0,
                            "y": 120.0,
                            "properties": {
                                "start_location": "https://example.org/start",
                                "persist_browser_state": False,
                                "browser_state": {
                                    "current_url": "https://example.org/private",
                                    "zoom_factor": 2.0,
                                    "cookies": "secret",
                                },
                            },
                        },
                    ],
                    "edges": [],
                }
            ],
            "metadata": {},
        }

        project = serializer.from_document(payload)
        reserialized = serializer.to_persistent_document(project)
        workspace_doc = next(ws for ws in reserialized["workspaces"] if ws["workspace_id"] == "ws_web")
        nodes = {item["node_id"]: item for item in workspace_doc["nodes"]}

        self.assertEqual(
            nodes["node_checked"]["properties"]["browser_state"],
            {
                "current_url": "https://example.com/current",
                "zoom_factor": 1.75,
            },
        )
        self.assertEqual(nodes["node_unchecked"]["properties"]["browser_state"], {})
        serialized_nodes = json.dumps(nodes, sort_keys=True).lower()
        for unsafe_key in (
            "cookie",
            "cache",
            "credential",
            "password",
            "session_storage",
            "local_storage",
            "page_content",
            "html",
        ):
            self.assertNotIn(unsafe_key, serialized_nodes)


class SerializerDefaultPortTests(unittest.TestCase):
    def test_persistent_document_drops_obsolete_locks_and_preserves_optional_filter(self) -> None:
        serializer = JsonProjectSerializer(build_default_registry())
        model = GraphModel()
        workspace = model.active_workspace
        node = model.add_node(
            workspace.workspace_id,
            "core.logger",
            "Logger",
            120.0,
            80.0,
            properties={"message": "inline"},
        )
        view = workspace.views[workspace.active_view_id]
        view.hide_optional_ports = True

        document = serializer.to_persistent_document(model.project)
        workspace_doc = next(ws for ws in document["workspaces"] if ws["workspace_id"] == workspace.workspace_id)
        node_doc = next(item for item in workspace_doc["nodes"] if item["node_id"] == node.node_id)
        view_doc = next(item for item in workspace_doc["views"] if item["view_id"] == view.view_id)

        self.assertNotIn("locked_ports", node_doc)
        self.assertNotIn("hide_locked_ports", view_doc)
        self.assertTrue(view_doc["hide_optional_ports"])

        node_doc["locked_ports"] = {"message": True}
        view_doc["hide_locked_ports"] = True
        document["metadata"]["port_locking_view_state"] = {
            workspace.workspace_id: {view.view_id: {"hide_locked_ports": True}}
        }

        loaded = serializer.from_document(document)
        loaded_workspace = loaded.workspaces[workspace.workspace_id]
        loaded_node = loaded_workspace.nodes[node.node_id]
        loaded_view = loaded_workspace.views[view.view_id]

        self.assertFalse(hasattr(loaded_node, "locked_ports"))
        self.assertFalse(hasattr(loaded_view, "hide_locked_ports"))
        self.assertTrue(loaded_view.hide_optional_ports)
        reserialized = serializer.to_persistent_document(loaded)
        reserialized_workspace = next(
            ws for ws in reserialized["workspaces"] if ws["workspace_id"] == workspace.workspace_id
        )
        self.assertNotIn("locked_ports", reserialized_workspace["nodes"][0])
        self.assertNotIn("hide_locked_ports", reserialized_workspace["views"][0])
        self.assertNotIn("port_locking_view_state", reserialized["metadata"])

    def test_persistent_document_round_trip_preserves_node_links(self) -> None:
        serializer = JsonProjectSerializer(build_default_registry())
        model = GraphModel()
        workspace = model.active_workspace
        node = model.add_node(
            workspace.workspace_id,
            "core.logger",
            "Logger",
            120.0,
            80.0,
            properties={"message": "inline"},
        )
        node.links = [
            NodeLinkRecord(
                link_id="link-docs",
                kind="url",
                title="Project docs",
                target="https://example.com/docs",
                subtitle="Reference",
            ),
            NodeLinkRecord(
                link_id="link-node",
                kind="node",
                title="Start",
                target="node-start",
            ),
        ]

        document = serializer.to_persistent_document(model.project)
        workspace_doc = next(ws for ws in document["workspaces"] if ws["workspace_id"] == workspace.workspace_id)
        node_doc = next(item for item in workspace_doc["nodes"] if item["node_id"] == node.node_id)

        self.assertEqual(
            node_doc["links"],
            [
                {
                    "id": "link-docs",
                    "kind": "url",
                    "title": "Project docs",
                    "target": "https://example.com/docs",
                    "subtitle": "Reference",
                },
                {
                    "id": "link-node",
                    "kind": "node",
                    "title": "Start",
                    "target": "node-start",
                    "target_node_id": "node-start",
                    "target_workspace_id": workspace.workspace_id,
                    "subtitle": "",
                },
            ],
        )

        loaded = serializer.from_document(document)
        loaded_workspace = loaded.workspaces[workspace.workspace_id]
        loaded_node = loaded_workspace.nodes[node.node_id]
        self.assertEqual(
            [
                (
                    link.link_id,
                    link.kind,
                    link.title,
                    link.target,
                    link.subtitle,
                    link.target_workspace_id,
                    link.target_node_id,
                )
                for link in loaded_node.links
            ],
            [
                ("link-docs", "url", "Project docs", "https://example.com/docs", "Reference", "", ""),
                ("link-node", "node", "Start", "node-start", "", workspace.workspace_id, "node-start"),
            ],
        )

        reserialized = serializer.to_persistent_document(loaded)
        reserialized_workspace = next(
            ws for ws in reserialized["workspaces"] if ws["workspace_id"] == workspace.workspace_id
        )
        reserialized_node = next(
            item for item in reserialized_workspace["nodes"] if item["node_id"] == node.node_id
        )
        self.assertEqual(reserialized_node["links"], node_doc["links"])

    def test_persistent_document_round_trip_preserves_cross_workspace_node_link_targets(self) -> None:
        serializer = JsonProjectSerializer(build_default_registry())
        model = GraphModel()
        workspace = model.active_workspace
        node = model.add_node(
            workspace.workspace_id,
            "core.logger",
            "Logger",
            120.0,
            80.0,
            properties={"message": "inline"},
        )
        node.links = [
            NodeLinkRecord(
                link_id="link-cross-node",
                kind="node",
                title="Target node",
                target="node-target",
                subtitle="Target Workspace - Media - ID 2",
                target_workspace_id="workspace-target",
                target_node_id="node-target",
            )
        ]

        document = serializer.to_persistent_document(model.project)
        workspace_doc = next(ws for ws in document["workspaces"] if ws["workspace_id"] == workspace.workspace_id)
        node_doc = next(item for item in workspace_doc["nodes"] if item["node_id"] == node.node_id)

        self.assertEqual(
            node_doc["links"],
            [
                {
                    "id": "link-cross-node",
                    "kind": "node",
                    "title": "Target node",
                    "target": "node-target",
                    "target_node_id": "node-target",
                    "target_workspace_id": "workspace-target",
                    "subtitle": "Target Workspace - Media - ID 2",
                }
            ],
        )

        loaded = serializer.from_document(document)
        loaded_link = loaded.workspaces[workspace.workspace_id].nodes[node.node_id].links[0]
        self.assertEqual(loaded_link.target, "node-target")
        self.assertEqual(loaded_link.target_node_id, "node-target")
        self.assertEqual(loaded_link.target_workspace_id, "workspace-target")

    def test_load_legacy_node_link_defaults_target_workspace_to_owning_workspace(self) -> None:
        serializer = JsonProjectSerializer(build_default_registry())
        model = GraphModel()
        workspace = model.active_workspace
        node = model.add_node(
            workspace.workspace_id,
            "core.logger",
            "Logger",
            120.0,
            80.0,
        )
        document = serializer.to_persistent_document(model.project)
        workspace_doc = next(ws for ws in document["workspaces"] if ws["workspace_id"] == workspace.workspace_id)
        node_doc = next(item for item in workspace_doc["nodes"] if item["node_id"] == node.node_id)
        node_doc["links"] = [
            {
                "id": "link-legacy-node",
                "kind": "node",
                "title": "Legacy node",
                "target": "node-target",
                "subtitle": "",
            }
        ]

        loaded = serializer.from_document(document)
        loaded_link = loaded.workspaces[workspace.workspace_id].nodes[node.node_id].links[0]
        self.assertEqual(loaded_link.target, "node-target")
        self.assertEqual(loaded_link.target_node_id, "node-target")
        self.assertEqual(loaded_link.target_workspace_id, workspace.workspace_id)

        reserialized = serializer.to_persistent_document(loaded)
        reserialized_workspace = next(
            ws for ws in reserialized["workspaces"] if ws["workspace_id"] == workspace.workspace_id
        )
        reserialized_node = next(
            item for item in reserialized_workspace["nodes"] if item["node_id"] == node.node_id
        )
        self.assertEqual(
            reserialized_node["links"][0],
            {
                "id": "link-legacy-node",
                "kind": "node",
                "title": "Legacy node",
                "target": "node-target",
                "target_node_id": "node-target",
                "target_workspace_id": workspace.workspace_id,
                "subtitle": "",
            },
        )

    def test_load_defaults_optional_filter_when_field_is_missing(self) -> None:
        serializer = JsonProjectSerializer(build_default_registry())
        model = GraphModel()
        workspace = model.active_workspace
        node = model.add_node(
            workspace.workspace_id,
            "core.logger",
            "Logger",
            40.0,
            60.0,
        )

        document = serializer.to_persistent_document(model.project)
        workspace_doc = next(ws for ws in document["workspaces"] if ws["workspace_id"] == workspace.workspace_id)
        node_doc = next(item for item in workspace_doc["nodes"] if item["node_id"] == node.node_id)
        view_doc = next(item for item in workspace_doc["views"] if item["view_id"] == workspace.active_view_id)
        node_doc.pop("links", None)
        view_doc.pop("hide_optional_ports", None)

        loaded = serializer.from_document(document)
        loaded_workspace = loaded.workspaces[workspace.workspace_id]
        loaded_node = loaded_workspace.nodes[node.node_id]
        loaded_view = loaded_workspace.views[workspace.active_view_id]

        self.assertEqual(loaded_node.links, [])
        self.assertFalse(loaded_view.hide_optional_ports)


class SerializerLegacyPlotSessionLayoutTests(unittest.TestCase):
    def test_persistent_document_omits_plot_session_layout(self) -> None:
        serializer = JsonProjectSerializer(build_default_registry())
        document = serializer.to_persistent_document(GraphModel().project)

        self.assertNotIn("plot_session_layout", document)

    def test_legacy_plot_session_layout_is_ignored_on_load_and_save(self) -> None:
        serializer = JsonProjectSerializer(build_default_registry())
        model = GraphModel()
        document = serializer.to_persistent_document(model.project)
        document["plot_session_layout"] = {
            "version": 1,
            "workspaces": {
                model.active_workspace.workspace_id: {
                    "window": {"open": True},
                    "panels": [{"panel_id": "plot::legacy", "node_id": "legacy"}],
                }
            },
        }

        loaded_project = serializer.from_document(document)
        round_tripped = serializer.to_persistent_document(loaded_project)

        self.assertNotIn("plot_session_layout", round_tripped)


def test_staged_create_new_commit_never_clobbers_a_racing_project() -> None:
    serializer = JsonProjectSerializer(build_default_registry())
    document = serializer.to_persistent_document(GraphModel().project)
    with tempfile.TemporaryDirectory() as temp_dir:
        target = Path(temp_dir) / "race.cxproj"
        stage = serializer.stage_document(target, document, "create_new")
        target.write_bytes(b"racing project")
        try:
            publication = serializer.commit_staged_document(stage)
        finally:
            serializer.discard_staged_document(stage)
        assert publication.state == "not_published"
        assert not publication.committed
        assert target.read_bytes() == b"racing project"


def test_create_new_target_appearing_during_atomic_attempt_is_published_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    serializer = JsonProjectSerializer(build_default_registry())
    target = tmp_path / "attempt-race.cxproj"
    stage = serializer.stage_document(
        target,
        serializer.to_persistent_document(GraphModel().project),
        "create_new",
    )

    def race_during_attempt(_source, destination) -> None:  # noqa: ANN001
        Path(destination).write_bytes(b"racing project")
        raise FileExistsError

    monkeypatch.setattr(serializer_module.os, "link", race_during_attempt)
    try:
        publication = serializer.commit_staged_document(stage)
    finally:
        serializer.discard_staged_document(stage)

    assert publication.state == "published"
    assert publication.committed
    assert target.read_bytes() == b"racing project"


def test_publication_result_rejects_cross_state_reason_pairs() -> None:
    with pytest.raises(ValueError, match="state/reason"):
        serializer_module.ProjectDocumentPublicationResult(
            "published",
            "project_document_not_published",
        )


@pytest.mark.parametrize("commit_mode", ["create_new", "replace_current"])
def test_atomic_helper_publish_then_raise_is_still_published(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    commit_mode: str,
) -> None:
    serializer = JsonProjectSerializer(build_default_registry())
    target = tmp_path / f"{commit_mode}.cxproj"
    if commit_mode == "replace_current":
        target.write_bytes(b"previous")
    stage = serializer.stage_document(
        target,
        serializer.to_persistent_document(GraphModel().project),
        commit_mode,
    )
    helper_name = "replace" if commit_mode == "replace_current" else "link"
    real_helper = (
        serializer_module.os.replace
        if commit_mode == "replace_current"
        else serializer_module.os.link
    )

    def publish_then_raise(source, destination) -> None:  # noqa: ANN001
        real_helper(source, destination)
        raise OSError("raised after publication")

    monkeypatch.setattr(serializer_module.os, helper_name, publish_then_raise)
    try:
        publication = serializer.commit_staged_document(stage)
        assert publication.state == "published"
        assert publication.committed
        serializer.verify_committed_document(stage)
    finally:
        serializer.discard_staged_document(stage)


@pytest.mark.parametrize("commit_mode", ["create_new", "replace_current"])
def test_atomic_helper_failure_before_attempt_is_not_published(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    commit_mode: str,
) -> None:
    serializer = JsonProjectSerializer(build_default_registry())
    target = tmp_path / f"before-{commit_mode}.cxproj"
    previous = b"previous"
    if commit_mode == "replace_current":
        target.write_bytes(previous)
    stage = serializer.stage_document(
        target,
        serializer.to_persistent_document(GraphModel().project),
        commit_mode,
    )
    helper_name = "replace" if commit_mode == "replace_current" else "link"
    monkeypatch.setattr(
        serializer_module.os,
        helper_name,
        lambda *_args: (_ for _ in ()).throw(OSError("before attempt")),
    )
    try:
        publication = serializer.commit_staged_document(stage)
    finally:
        serializer.discard_staged_document(stage)
    assert publication.state == "not_published"
    assert not publication.committed
    if target.exists():
        assert target.read_bytes() == previous
    else:
        assert commit_mode == "create_new"


def test_unreadable_postattempt_probe_is_publication_uncertain(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    serializer = JsonProjectSerializer(build_default_registry())
    target = tmp_path / "uncertain.cxproj"
    stage = serializer.stage_document(
        target,
        serializer.to_persistent_document(GraphModel().project),
        "create_new",
    )
    real_link = serializer_module.os.link
    real_fact = serializer_module._publication_target_fact  # noqa: SLF001
    probe_count = 0

    def publish_then_raise(source, destination) -> None:  # noqa: ANN001
        real_link(source, destination)
        raise OSError("raised after publication")

    def unreadable_after_attempt(path):  # noqa: ANN001, ANN202
        nonlocal probe_count
        probe_count += 1
        if probe_count > 1:
            raise OSError("unreadable")
        return real_fact(path)

    monkeypatch.setattr(serializer_module.os, "link", publish_then_raise)
    monkeypatch.setattr(serializer_module, "_publication_target_fact", unreadable_after_attempt)
    try:
        publication = serializer.commit_staged_document(stage)
    finally:
        serializer.discard_staged_document(stage)
    assert publication.state == "publication_uncertain"
    assert publication.committed


def test_save_document_skips_cleanup_after_committed_verification_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    serializer = JsonProjectSerializer(build_default_registry())
    target = tmp_path / "verify-failure.cxproj"
    target.write_bytes(b"previous")
    real_replace = serializer_module.os.replace

    def publish_corrupt_then_raise(source, destination) -> None:  # noqa: ANN001
        real_replace(source, destination)
        Path(destination).write_bytes(b"corrupt")
        raise OSError("raised after publication")

    cleanup = Mock()
    monkeypatch.setattr(serializer_module.os, "replace", publish_corrupt_then_raise)
    monkeypatch.setattr(serializer_module, "collect_project_image_garbage", cleanup)
    with pytest.raises(OSError, match="verification failed"):
        serializer.save_document(
            str(target),
            serializer.to_persistent_document(GraphModel().project),
        )
    cleanup.assert_not_called()


if __name__ == "__main__":
    unittest.main()

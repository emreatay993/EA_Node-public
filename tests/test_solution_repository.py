from __future__ import annotations

from dataclasses import replace
import hashlib
import json
import os
import shutil
from pathlib import Path

import pytest

import ea_node_editor.persistence.solution_repository as solution_repository_module

from ea_node_editor.execution.solution_backend import DurableBackendOpenResult
from ea_node_editor.execution.project_solution import (
    ProjectSolutionSaveRecordExport,
    ProjectSolutionSaveSnapshot,
)
from ea_node_editor.execution.solution_store import SolutionStore
from ea_node_editor.nodes.bootstrap import build_default_registry
from ea_node_editor.persistence.artifact_store import ProjectArtifactStore
from ea_node_editor.persistence.solution_repository import (
    DurableGenerationResult,
    MAX_DURABLE_MANIFEST_SET_BYTES,
    SolutionRepository,
    SolutionRepositoryFactory,
    node_path_key,
    workspace_path_key,
)
from ea_node_editor.runtime_contracts import (
    DataTree,
    DataTypeCatalog,
    DataTypeFamilySpec,
    DataTypeSpec,
    STRING_DATA_TYPE_ID,
    RuntimeArtifactRef,
    TypedInlineValue,
)
from ea_node_editor.runtime_contracts.settled_results import (
    SettledPortResult,
    settled_outputs_to_payload,
)
from ea_node_editor.runtime_contracts.solution_records import (
    SolutionOutputDescriptor,
    SolutionPayloadLocator,
    SolutionRecord,
    SolutionResidency,
)


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _deep_json_bytes(depth: int = 1_500) -> bytes:
    return b'{"nested":' + (b"[" * depth) + b"0" + (b"]" * depth) + b"}"


def _fixture(tmp_path: Path):  # noqa: ANN202
    registry = build_default_registry()
    catalog = registry.data_types
    outputs = {
        "result": SettledPortResult(
            status="value",
            value=DataTree.from_item("portable"),
        )
    }
    output_payload = settled_outputs_to_payload(outputs, catalog=catalog)
    canonical = _canonical(output_payload)
    descriptor_digest = hashlib.sha256(
        _canonical({"result": output_payload["result"]})
    ).hexdigest()
    record = SolutionRecord(
        record_id="record-1",
        project_id="project-1",
        workspace_id="workspace-1",
        node_id="node-1",
        solution_key="a" * 64,
        node_interface_revision=1,
        node_interface_digest="b" * 64,
        node_contract_digest="c" * 64,
        dependency_solution_keys=(),
        input_provenance_digest="d" * 64,
        execution_policy_digest="e" * 64,
        implementation_digest="f" * 64,
        execution_environment_digest="1" * 64,
        settlement_status="completed",
        result_digest=hashlib.sha256(canonical).hexdigest(),
        reuse_eligible=True,
        output_descriptors=(
            SolutionOutputDescriptor(
                port_key="result",
                status="value",
                data_type_id=STRING_DATA_TYPE_ID,
                concrete_data_type_ids=(STRING_DATA_TYPE_ID,),
                data_access="item",
                item_count=1,
                payload_kinds=("inline",),
                payload_digest=descriptor_digest,
                payload_schema_version=1,
            ),
        ),
        payload_locator=SolutionPayloadLocator(
            kind=SolutionResidency.SESSION,
            reference_id="payload-1",
        ),
        residency=SolutionResidency.SESSION,
        runtime_generation=1,
        created_at_epoch_ms=1,
    )
    project_path = tmp_path / "sample.cxproj"
    return catalog, outputs, canonical, record, project_path


def _built_repository(tmp_path: Path):  # noqa: ANN202
    catalog, outputs, canonical, record, project_path = _fixture(tmp_path)
    repository = SolutionRepository.create_empty(
        project_id=record.project_id,
        project_path=project_path,
        solution_namespace_id="namespace-1",
        catalog=catalog,
    )
    staged = repository.stage_record(record, canonical, catalog)
    assert staged.reason_code == "durable_stage_published"
    assert staged.record is not None
    generation = repository.build_candidate_generation((staged.record,))
    assert generation.reason_code == "durable_generation_built"
    metadata = generation.metadata_solution_store
    return catalog, outputs, record, project_path, repository, staged.record, metadata


def test_project_solution_save_stages_opens_and_filters_removed_owners(
    tmp_path: Path,
) -> None:
    catalog, _outputs, canonical, record, _source_path = _fixture(tmp_path)
    with pytest.raises(ValueError, match="must be current"):
        ProjectSolutionSaveRecordExport(
            record=record,
            canonical_payload=canonical,
            maximum_reuse_scope="durable",
            is_current=False,
        )
    factory = SolutionRepositoryFactory()
    destination = tmp_path / "destination.cxproj"
    snapshot = factory.export_project_solution_save(
        record.project_id,
        "",
        "save-namespace",
        "",
        "",
        ((record.workspace_id, record.node_id),),
        (
            ProjectSolutionSaveRecordExport(
                record=record,
                canonical_payload=canonical,
                maximum_reuse_scope="durable",
                is_current=True,
            ),
        ),
        0,
        "a" * 64,
        "b" * 64,
        catalog,
        None,
    )

    result = factory.stage_project_solution_save(
        snapshot,
        str(destination),
        catalog,
        None,
    )
    assert result.reason_code == "project_solution_save_staged"
    assert result.omitted_record_count == 0
    solution_root = destination.with_name("destination.data") / "solutions" / "v1"
    published_bytes = sum(
        path.stat().st_size for path in solution_root.rglob("*") if path.is_file()
    )
    assert result.estimated_copy_bytes == snapshot.estimated_copy_bytes
    assert result.staged_new_bytes == published_bytes
    assert result.estimated_copy_bytes >= result.staged_new_bytes
    candidate = factory.open_project_solution_save_candidate(
        record.project_id,
        str(destination),
        result.metadata_solution_store,
        snapshot.solution_namespace_id,
        catalog,
        None,
    )
    assert candidate.status_code == "durable_bound_active"
    assert candidate.active_generation_id == result.candidate_generation_id
    assert candidate.active_manifest_set_digest == result.candidate_manifest_set_digest
    assert candidate.backend is not None
    hit = candidate.backend.lookup_record(
        record.workspace_id,
        record.node_id,
        record.solution_key,
        catalog,
    )
    assert hit.record is not None
    candidate.backend.close()
    gc_result = factory.collect_project_solution_garbage(
        record.project_id,
        str(destination),
        result.candidate_generation_id,
        result.candidate_manifest_set_digest,
        (),
        result.orphan_candidate_relative_paths,
        result.orphan_scan_complete,
        10_000,
        catalog,
    )
    assert gc_result.removed_relative_paths == ()
    assert gc_result.reason_code == "project_solution_gc_completed"

    with pytest.raises(ValueError, match="binding"):
        replace(
            snapshot,
            retained_owner_ids=((record.workspace_id, "removed-node"),),
        )


def test_save_as_managed_artifact_solution_survives_source_deletion(
    tmp_path: Path,
) -> None:
    registry = build_default_registry()
    catalog = registry.data_types
    project_id = "artifact-project"
    workspace_id = "workspace"
    node_id = "artifact-node"
    source_project = tmp_path / "source" / "source.cxproj"
    destination_project = tmp_path / "destination" / "copy.cxproj"
    destination_project.parent.mkdir(parents=True)
    relative = "workspaces/Workspace [11111111]/nodes/Node [22222222]/out/payload.bin"
    source_store = ProjectArtifactStore(
        project_path=source_project,
        metadata=None,
    )
    source_path = source_store.layout.absolute_path_for_relative(relative)
    source_path.parent.mkdir(parents=True, exist_ok=True)
    source_path.write_bytes(b"portable managed solution")
    artifact_digest = hashlib.sha256(source_path.read_bytes()).hexdigest()
    artifact_ref = RuntimeArtifactRef.managed(
        "managed-solution",
        data_type_id="COREX.DataTypes.Animation",
        schema_version=1,
        format="gif",
        size_bytes=source_path.stat().st_size,
        sha256=artifact_digest,
        provenance="corex.test",
    )
    source_store = ProjectArtifactStore(
        project_path=source_project,
        metadata={
            "artifacts": {
                artifact_ref.artifact_id: {
                    "relative_path": relative,
                    "runtime_artifact": artifact_ref.to_descriptor(),
                }
            },
            "staged": {},
        },
    )
    outputs = {
        "result": SettledPortResult(
            status="value",
            value=DataTree.from_item(artifact_ref),
        )
    }
    payload = settled_outputs_to_payload(outputs, catalog=catalog)
    canonical = _canonical(payload)
    record = SolutionRecord(
        record_id="managed-artifact-record",
        project_id=project_id,
        workspace_id=workspace_id,
        node_id=node_id,
        solution_key="9" * 64,
        node_interface_revision=1,
        node_interface_digest="1" * 64,
        node_contract_digest="2" * 64,
        dependency_solution_keys=(),
        input_provenance_digest="3" * 64,
        execution_policy_digest="4" * 64,
        implementation_digest="5" * 64,
        execution_environment_digest="6" * 64,
        settlement_status="completed",
        result_digest=hashlib.sha256(canonical).hexdigest(),
        reuse_eligible=True,
        output_descriptors=(
            SolutionOutputDescriptor(
                port_key="result",
                status="value",
                data_type_id="COREX.DataTypes.Animation",
                concrete_data_type_ids=("COREX.DataTypes.Animation",),
                data_access="item",
                item_count=1,
                payload_kinds=("artifact_ref",),
                payload_digest=hashlib.sha256(
                    _canonical({"result": payload["result"]})
                ).hexdigest(),
                payload_schema_version=1,
            ),
        ),
        payload_locator=SolutionPayloadLocator(
            kind=SolutionResidency.SESSION,
            reference_id="managed-session-payload",
        ),
        residency=SolutionResidency.SESSION,
        runtime_generation=1,
        created_at_epoch_ms=1,
        catalog=catalog,
    )
    source_repository = SolutionRepository.create_empty(
        project_id=project_id,
        project_path=source_project,
        solution_namespace_id="managed-namespace",
        catalog=catalog,
    )
    staged = source_repository.stage_record(record, canonical, catalog)
    assert staged.record is not None
    generation = source_repository.build_candidate_generation((staged.record,))
    assert generation.reason_code == "durable_generation_built"
    source_repository.close()
    factory = SolutionRepositoryFactory()
    snapshot = factory.export_project_solution_save(
        project_id,
        os.path.normcase(os.path.abspath(source_project)),
        "managed-namespace",
        generation.generation_id,
        generation.manifest_set_digest,
        ((workspace_id, node_id),),
        (),
        0,
        "a" * 64,
        source_store.project_save_context_digest(),
        catalog,
        source_store,
    )
    assert snapshot.required_managed_artifact_ids == (artifact_ref.artifact_id,)
    artifact_stage = source_store.stage_project_save(
        destination_project_path=destination_project,
        workspaces={},
        required_managed_artifact_ids=snapshot.required_managed_artifact_ids,
    )
    save_result = factory.stage_project_solution_save(
        snapshot,
        str(destination_project),
        catalog,
        artifact_stage.destination_store,
    )
    assert save_result.reason_code == "project_solution_save_staged"

    shutil.rmtree(source_project.with_name("source.data"))
    reopened = factory.open_project_solution_save_candidate(
        project_id,
        str(destination_project),
        save_result.metadata_solution_store,
        "managed-namespace",
        catalog,
        artifact_stage.destination_store,
    )
    assert reopened.backend is not None
    hit = reopened.backend.lookup_record(
        workspace_id,
        node_id,
        record.solution_key,
        catalog,
    )
    assert hit.record is not None
    loaded = reopened.backend.load_payload(hit.record, catalog)
    assert loaded.reason_code == "durable_hit"
    copied = artifact_stage.destination_store.resolve_managed_path(
        artifact_ref.artifact_id
    )
    assert copied is not None and copied.read_bytes() == b"portable managed solution"
    reopened.backend.close()


def test_solution_gc_incomplete_scan_rescans_and_partial_retry_completes(
    tmp_path: Path,
) -> None:
    catalog, _outputs, canonical, record, _source_path = _fixture(tmp_path)
    factory = SolutionRepositoryFactory()
    snapshot = factory.export_project_solution_save(
        record.project_id,
        "",
        "gc-namespace",
        "",
        "",
        ((record.workspace_id, record.node_id),),
        (ProjectSolutionSaveRecordExport(record, canonical, "durable", True),),
        0,
        "a" * 64,
        "b" * 64,
        catalog,
        None,
    )
    destination = tmp_path / "gc.cxproj"
    result = factory.stage_project_solution_save(snapshot, str(destination), catalog, None)
    root = destination.with_name("gc.data") / "solutions" / "v1"
    orphan_paths = (
        f"records/sha256/cc/{'c' * 64}.json",
        f"records/sha256/dd/{'d' * 64}.json",
    )
    for relative in orphan_paths:
        path = root / Path(relative)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"orphan")

    first = factory.collect_project_solution_garbage(
        record.project_id,
        str(destination),
        result.candidate_generation_id,
        result.candidate_manifest_set_digest,
        (),
        (),
        False,
        1,
        catalog,
    )
    assert first.reason_code == "project_solution_gc_partial"
    assert first.has_more
    remaining = tuple(
        sorted(set(first.candidate_relative_paths).difference(first.removed_relative_paths))
    )
    second = factory.collect_project_solution_garbage(
        record.project_id,
        str(destination),
        result.candidate_generation_id,
        result.candidate_manifest_set_digest,
        (),
        remaining,
        True,
        10_000,
        catalog,
    )
    assert second.reason_code == "project_solution_gc_completed"
    assert not second.has_more
    assert all(not (root / Path(relative)).exists() for relative in orphan_paths)


def test_solution_stage_fails_when_new_publications_exceed_snapshot_estimate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    catalog, _outputs, canonical, record, _source_path = _fixture(tmp_path)
    monkeypatch.setattr(
        solution_repository_module,
        "_projected_supplemental_bytes",
        lambda *_args, **_kwargs: 1,
    )
    factory = SolutionRepositoryFactory()
    snapshot = factory.export_project_solution_save(
        record.project_id,
        "",
        "estimate-namespace",
        "",
        "",
        ((record.workspace_id, record.node_id),),
        (ProjectSolutionSaveRecordExport(record, canonical, "durable", True),),
        0,
        "a" * 64,
        "b" * 64,
        catalog,
        None,
    )
    result = factory.stage_project_solution_save(
        snapshot,
        str(tmp_path / "estimate.cxproj"),
        catalog,
        None,
    )
    assert result.reason_code == "project_solution_save_capacity_exceeded"
    assert result.staged_new_bytes == 0
    assert result.estimated_copy_bytes == 0


def test_normal_save_merges_active_generation_with_current_supplemental_record(
    tmp_path: Path,
) -> None:
    catalog, outputs, record, source_path, repository, _durable, metadata = (
        _built_repository(tmp_path)
    )
    repository.close()
    canonical = _canonical(settled_outputs_to_payload(outputs, catalog=catalog))
    supplemental = replace(
        record,
        record_id="record-2",
        node_id="node-2",
        solution_key="2" * 64,
        created_at_epoch_ms=2,
        catalog=catalog,
    )
    factory = SolutionRepositoryFactory()
    snapshot = factory.export_project_solution_save(
        record.project_id,
        os.path.normcase(os.path.abspath(source_path)),
        metadata["solution_namespace_id"],
        metadata["active_generation_id"],
        metadata["active_manifest_set_digest"],
        (
            (record.workspace_id, record.node_id),
            (supplemental.workspace_id, supplemental.node_id),
        ),
        (
            ProjectSolutionSaveRecordExport(
                supplemental,
                canonical,
                "durable",
                True,
            ),
        ),
        0,
        "a" * 64,
        "b" * 64,
        catalog,
        None,
    )
    destination = tmp_path / "normal-copy.cxproj"
    result = factory.stage_project_solution_save(
        snapshot,
        str(destination),
        catalog,
        None,
    )
    assert result.reason_code == "project_solution_save_staged"
    candidate = factory.open_project_solution_save_candidate(
        record.project_id,
        str(destination),
        result.metadata_solution_store,
        snapshot.solution_namespace_id,
        catalog,
        None,
    )
    assert candidate.backend is not None
    for expected in (record, supplemental):
        hit = candidate.backend.lookup_record(
            expected.workspace_id,
            expected.node_id,
            expected.solution_key,
            catalog,
        )
        assert hit.record is not None
    candidate.backend.close()


def test_path_keys_are_full_tagged_sha256_digests() -> None:
    assert workspace_path_key("same") != node_path_key("same")
    assert len(workspace_path_key("workspace")) == 64
    assert len(node_path_key("node")) == 64
    assert workspace_path_key("a/b") != workspace_path_key("a\\b")


def test_every_generation_reason_has_one_strict_result_shape() -> None:
    for reason in solution_repository_module._GENERATION_REASONS:  # noqa: SLF001
        succeeded = reason in {
            "durable_generation_built",
            "durable_generation_valid",
        }
        result = DurableGenerationResult(
            "a" * 32 if succeeded else "",
            "b" * 64 if succeeded else "",
            reason,
            "namespace" if succeeded else "",
        )
        assert bool(result.metadata_solution_store) is succeeded


@pytest.mark.parametrize(
    ("metadata", "reason"),
    [
        (None, "durable_session_only_metadata_absent"),
        ({}, "durable_session_only_metadata_invalid"),
        (
            {
                "schema_version": 2,
                "solution_namespace_id": "namespace",
                "active_generation_id": "a" * 32,
                "active_manifest_set_digest": "b" * 64,
            },
            "durable_session_only_schema_unsupported",
        ),
        (
            {
                "schema_version": 1,
                "solution_namespace_id": "namespace",
                "active_generation_id": "../bad",
                "active_manifest_set_digest": "b" * 64,
            },
            "durable_session_only_pointer_invalid",
        ),
    ],
)
def test_factory_metadata_fails_closed_session_only(
    tmp_path: Path,
    metadata: object,
    reason: str,
) -> None:
    catalog = build_default_registry().data_types
    result = SolutionRepositoryFactory().open_backend(
        "project",
        str(tmp_path / "project.cxproj"),
        metadata,
        catalog,
    )
    assert result.backend is None
    assert result.status_code == reason
    assert 0 < len(result.diagnostic.encode("utf-8")) <= 512


def test_stage_build_bind_lookup_and_lazy_payload_restart(tmp_path: Path) -> None:
    catalog, outputs, record, project_path, repository, durable, metadata = (
        _built_repository(tmp_path)
    )
    repository.close()

    opened = SolutionRepositoryFactory().open_backend(
        record.project_id,
        str(project_path),
        metadata,
        catalog,
    )
    assert opened.status_code == "durable_bound_active"
    assert opened.backend is not None
    looked_up = opened.backend.lookup_record(
        record.workspace_id,
        record.node_id,
        record.solution_key,
        catalog,
    )
    assert looked_up.reason_code == "durable_hit"
    assert looked_up.record == durable
    loaded = opened.backend.load_payload(looked_up.record, catalog)
    assert loaded.reason_code == "durable_hit"
    assert dict(loaded.outputs or ()) == outputs


def test_durable_load_and_restart_invoke_zero_catalog_callbacks(tmp_path: Path) -> None:
    calls = 0

    def hostile_validator(_value: object) -> bool:
        nonlocal calls
        calls += 1
        return True

    catalog = DataTypeCatalog()
    catalog.register_many(
        families=(DataTypeFamilySpec("hostile", "Hostile", "type.test", "test"),),
        types=(
            DataTypeSpec(
                "Test.Hostile.Inline",
                "Hostile Inline",
                "hostile",
                hostile_validator,
                carriers=frozenset({"inline"}),
                persistence="inline",
            ),
        ),
        owner_id="tests",
    )
    catalog.freeze()
    outputs = {
        "result": SettledPortResult(
            status="value",
            value=DataTree.from_item(
                TypedInlineValue("Test.Hostile.Inline", 1, {"value": 1})
            ),
        )
    }
    output_payload = settled_outputs_to_payload(outputs, catalog=catalog)
    canonical = _canonical(output_payload)
    record = SolutionRecord(
        record_id="hostile-record",
        project_id="project",
        workspace_id="workspace",
        node_id="node",
        solution_key="1" * 64,
        node_interface_revision=1,
        node_interface_digest="2" * 64,
        node_contract_digest="3" * 64,
        dependency_solution_keys=(),
        input_provenance_digest="4" * 64,
        execution_policy_digest="5" * 64,
        implementation_digest="6" * 64,
        execution_environment_digest="7" * 64,
        settlement_status="completed",
        result_digest=hashlib.sha256(canonical).hexdigest(),
        reuse_eligible=True,
        output_descriptors=(
            SolutionOutputDescriptor(
                port_key="result",
                status="value",
                data_type_id="Test.Hostile.Inline",
                concrete_data_type_ids=("Test.Hostile.Inline",),
                data_access="item",
                item_count=1,
                payload_kinds=("inline",),
                payload_digest=hashlib.sha256(
                    _canonical({"result": output_payload["result"]})
                ).hexdigest(),
                payload_schema_version=1,
            ),
        ),
        payload_locator=SolutionPayloadLocator(
            kind=SolutionResidency.SESSION,
            reference_id="session-payload",
        ),
        residency=SolutionResidency.SESSION,
        runtime_generation=1,
        created_at_epoch_ms=1,
        catalog=catalog,
    )
    calls = 0
    project_path = tmp_path / "hostile.cxproj"
    repository = SolutionRepository.create_empty(
        project_id="project",
        project_path=project_path,
        solution_namespace_id="namespace",
        catalog=catalog,
    )
    staged = repository.stage_record(record, canonical, catalog)
    assert staged.record is not None
    generation = repository.build_candidate_generation((staged.record,))
    assert calls == 0
    repository.close()
    opened = SolutionRepositoryFactory().open_backend(
        "project",
        str(project_path),
        generation.metadata_solution_store,
        catalog,
    )
    assert opened.backend is not None
    looked_up = opened.backend.lookup_record(
        "workspace",
        "node",
        record.solution_key,
        catalog,
    )
    assert looked_up.record == staged.record
    loaded = opened.backend.load_payload(staged.record, catalog)
    assert loaded.reason_code == "durable_hit"
    assert calls == 0

    store = SolutionStore()
    store.reset_project_session("project", str(project_path))
    store.install_durable_backend(
        "project",
        DurableBackendOpenResult(
            opened.backend,
            "namespace",
            "durable_bound_active",
            active_generation_id=opened.active_generation_id,
            active_manifest_set_digest=opened.active_manifest_set_digest,
        ),
    )
    selected = store.select_record(
        solution_key=record.solution_key,
        project_id="project",
        workspace_id="workspace",
        node_id="node",
        runtime_generation=1,
        catalog=catalog,
    )
    assert selected == staged.record
    accepted = store.accepted_outputs(
        selected,
        catalog=catalog,
        runtime_generation=1,
    )
    assert accepted.residency is SolutionResidency.DURABLE
    assert store.facts("project", "workspace")[0].retained_record_id == (
        staged.record.record_id
    )
    assert calls == 0


def test_bind_lookup_and_payload_reads_are_lazy_and_ordered(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    catalog, _outputs, record, project_path, repository, _durable, metadata = (
        _built_repository(tmp_path)
    )
    repository.close()
    original_read = solution_repository_module._read_file  # noqa: SLF001
    reads: list[str] = []

    def recording_read(root, relative_path, **kwargs):  # noqa: ANN001, ANN202
        reads.append(str(relative_path))
        return original_read(root, relative_path, **kwargs)

    monkeypatch.setattr(solution_repository_module, "_read_file", recording_read)
    opened = SolutionRepositoryFactory().open_backend(
        record.project_id,
        str(project_path),
        metadata,
        catalog,
    )
    assert reads == [
        f"generations/{metadata['active_generation_id']}/manifest-set.json"
    ]
    assert opened.backend is not None
    looked_up = opened.backend.lookup_record(
        record.workspace_id,
        record.node_id,
        record.solution_key,
        catalog,
    )
    assert [Path(item).name for item in reads[1:]] == [
        f"{node_path_key(record.node_id)}.json",
        next(item for item in reads if item.startswith("records/")).split("/")[-1],
    ]
    before_load = len(reads)
    assert looked_up.record is not None
    loaded = opened.backend.load_payload(looked_up.record, catalog)
    assert loaded.reason_code == "durable_hit"
    assert len(reads) == before_load + 1
    assert reads[-1].startswith("blobs/sha256/")


def test_same_key_same_result_is_identical_and_difference_conflicts(tmp_path: Path) -> None:
    catalog, _outputs, canonical, record, project_path = _fixture(tmp_path)
    repository = SolutionRepository.create_empty(
        project_id=record.project_id,
        project_path=project_path,
        solution_namespace_id="namespace",
        catalog=catalog,
    )
    first = repository.stage_record(record, canonical, catalog)
    second = repository.stage_record(record, canonical, catalog)
    assert first.record == second.record
    assert second.reason_code == "durable_stage_existing_identical"
    divergent_outputs = {
        "result": SettledPortResult(
            status="value",
            value=DataTree.from_item("different"),
        )
    }
    divergent_payload = settled_outputs_to_payload(divergent_outputs, catalog=catalog)
    divergent_canonical = _canonical(divergent_payload)
    divergent_descriptor = replace(
        record.output_descriptors[0],
        payload_digest=hashlib.sha256(
            _canonical({"result": divergent_payload["result"]})
        ).hexdigest(),
    )
    conflict_record = replace(
        record,
        result_digest=hashlib.sha256(divergent_canonical).hexdigest(),
        record_id="record-2",
        output_descriptors=(divergent_descriptor,),
    )
    conflict = repository.stage_record(
        conflict_record,
        divergent_canonical,
        catalog,
    )
    assert conflict.reason_code == "durable_nondeterminism_conflict"


def test_corrupt_manifest_preserves_session_only_fallback(tmp_path: Path) -> None:
    catalog, _outputs, record, project_path, repository, _durable, metadata = (
        _built_repository(tmp_path)
    )
    repository.close()
    manifest = (
        project_path.with_name(f"{project_path.stem}.data")
        / "solutions"
        / "v1"
        / "generations"
        / metadata["active_generation_id"]
        / "manifest-set.json"
    )
    manifest.write_bytes(b"{}")
    opened = SolutionRepositoryFactory().open_backend(
        record.project_id,
        str(project_path),
        metadata,
        catalog,
    )
    assert opened.backend is None
    assert opened.status_code == "durable_session_only_manifest_digest_mismatch"


def test_manifest_size_n_plus_one_is_rejected_before_decode(tmp_path: Path) -> None:
    catalog = build_default_registry().data_types
    project_path = tmp_path / "project.cxproj"
    generation = "a" * 32
    manifest = (
        project_path.with_name(f"{project_path.stem}.data")
        / "solutions"
        / "v1"
        / "generations"
        / generation
        / "manifest-set.json"
    )
    manifest.parent.mkdir(parents=True)
    manifest.write_bytes(b"x" * (MAX_DURABLE_MANIFEST_SET_BYTES + 1))
    result = SolutionRepositoryFactory().open_backend(
        "project",
        str(project_path),
        {
            "schema_version": 1,
            "solution_namespace_id": "namespace",
            "active_generation_id": generation,
            "active_manifest_set_digest": "b" * 64,
        },
        catalog,
    )
    assert result.status_code == "durable_session_only_manifest_oversized"


def test_deep_manifest_is_contained_as_session_only_invalid(tmp_path: Path) -> None:
    catalog = build_default_registry().data_types
    project_path = tmp_path / "deep.cxproj"
    generation = "a" * 32
    raw = _deep_json_bytes()
    manifest = (
        project_path.with_name(f"{project_path.stem}.data")
        / "solutions"
        / "v1"
        / "generations"
        / generation
        / "manifest-set.json"
    )
    manifest.parent.mkdir(parents=True)
    manifest.write_bytes(raw)
    result = SolutionRepositoryFactory().open_backend(
        "project",
        str(project_path),
        {
            "schema_version": 1,
            "solution_namespace_id": "namespace",
            "active_generation_id": generation,
            "active_manifest_set_digest": hashlib.sha256(raw).hexdigest(),
        },
        catalog,
    )
    assert result.backend is None
    assert result.status_code == "durable_session_only_manifest_invalid"


def test_deep_node_record_and_blob_are_contained_by_backend_ports(
    tmp_path: Path,
) -> None:
    deep = _deep_json_bytes()
    deep_digest = hashlib.sha256(deep).hexdigest()

    catalog, _outputs, record, project_path, repository, durable, metadata = (
        _built_repository(tmp_path / "node")
    )
    repository.close()
    opened = SolutionRepositoryFactory().open_backend(
        record.project_id,
        str(project_path),
        metadata,
        catalog,
    )
    assert isinstance(opened.backend, SolutionRepository)
    manifest_entry = next(iter(opened.backend._manifest_entries.values()))  # noqa: SLF001
    node_path = (
        opened.backend._root  # noqa: SLF001
        / "generations"
        / metadata["active_generation_id"]
        / manifest_entry["relative_path"]
    )
    node_path.write_bytes(deep)
    manifest_entry["node_manifest_digest"] = deep_digest
    assert opened.backend.lookup_record(
        record.workspace_id,
        record.node_id,
        record.solution_key,
        catalog,
    ).reason_code == "durable_node_manifest_invalid"

    catalog, _outputs, record, project_path, repository, durable, metadata = (
        _built_repository(tmp_path / "record")
    )
    repository.close()
    opened = SolutionRepositoryFactory().open_backend(
        record.project_id,
        str(project_path),
        metadata,
        catalog,
    )
    assert isinstance(opened.backend, SolutionRepository)
    manifest_entry = next(iter(opened.backend._manifest_entries.values()))  # noqa: SLF001
    node_path = (
        opened.backend._root  # noqa: SLF001
        / "generations"
        / metadata["active_generation_id"]
        / manifest_entry["relative_path"]
    )
    node_payload = json.loads(node_path.read_text(encoding="utf-8"))
    node_payload["records"][0]["record_digest"] = deep_digest
    node_raw = _canonical(node_payload)
    node_path.write_bytes(node_raw)
    manifest_entry["node_manifest_digest"] = hashlib.sha256(node_raw).hexdigest()
    record_path = (
        opened.backend._root  # noqa: SLF001
        / "records"
        / "sha256"
        / deep_digest[:2]
        / f"{deep_digest}.json"
    )
    record_path.parent.mkdir(parents=True, exist_ok=True)
    record_path.write_bytes(deep)
    assert opened.backend.lookup_record(
        record.workspace_id,
        record.node_id,
        record.solution_key,
        catalog,
    ).reason_code == "durable_record_invalid"

    catalog, _outputs, _record, _project_path, repository, durable, _metadata = (
        _built_repository(tmp_path / "blob")
    )
    blob_path = (
        repository._root  # noqa: SLF001
        / "blobs"
        / "sha256"
        / deep_digest[:2]
        / deep_digest
    )
    blob_path.parent.mkdir(parents=True, exist_ok=True)
    blob_path.write_bytes(deep)
    deep_record = replace(
        durable,
        payload_locator=SolutionPayloadLocator(
            kind=SolutionResidency.DURABLE,
            reference_id=deep_digest,
            blob_digests=(deep_digest,),
        ),
        catalog=catalog,
    )
    assert repository.load_payload(
        deep_record,
        catalog,
    ).reason_code == "durable_payload_invalid"


def test_candidate_validation_reachability_and_isolated_prune(tmp_path: Path) -> None:
    _catalog, _outputs, _record, _project_path, repository, _durable, metadata = (
        _built_repository(tmp_path)
    )
    validation = repository.validate_generation(
        metadata["active_generation_id"],
        metadata["active_manifest_set_digest"],
    )
    assert validation.reason_code == "durable_generation_valid"
    reachable = repository.enumerate_reachable_paths(
        (metadata["active_generation_id"],)
    )
    assert reachable
    extra = repository._root / "blobs" / "sha256" / "ff" / ("f" * 64)  # noqa: SLF001
    extra.parent.mkdir(parents=True, exist_ok=True)
    extra.write_bytes(b"garbage")
    removed = repository.prune_unreachable_paths(
        (f"blobs/sha256/ff/{'f' * 64}",),
        reachable_paths=reachable,
    )
    assert removed == (f"blobs/sha256/ff/{'f' * 64}",)
    assert not extra.exists()
    assert all(path.exists() for path in reachable)


def test_close_is_idempotent_and_never_deletes_content(tmp_path: Path) -> None:
    _catalog, _outputs, _record, _project_path, repository, _durable, _metadata = (
        _built_repository(tmp_path)
    )
    files = tuple(path for path in repository._root.rglob("*") if path.is_file())  # noqa: SLF001
    repository.close()
    repository.close()
    assert files and all(path.exists() for path in files)


def test_stage_blob_and_record_byte_limits_accept_n_reject_n_plus_one(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    catalog, _outputs, canonical, record, project_path = _fixture(tmp_path)
    probe = SolutionRepository.create_empty(
        project_id=record.project_id,
        project_path=project_path,
        solution_namespace_id="namespace",
        catalog=catalog,
    )
    staged = probe.stage_record(record, canonical, catalog)
    assert staged.record is not None and staged.record.payload_locator is not None
    blob_digest = staged.record.payload_locator.reference_id
    blob_size = (
        probe._root / "blobs" / "sha256" / blob_digest[:2] / blob_digest  # noqa: SLF001
    ).stat().st_size
    record_digest = probe._record_digests[staged.record.record_id]  # noqa: SLF001
    record_size = (
        probe._root / "records" / "sha256" / record_digest[:2] / f"{record_digest}.json"  # noqa: SLF001
    ).stat().st_size

    exact_blob_repo = SolutionRepository.create_empty(
        project_id=record.project_id,
        project_path=tmp_path / "exact-blob.cxproj",
        solution_namespace_id="namespace",
        catalog=catalog,
    )
    monkeypatch.setattr(solution_repository_module, "MAX_DURABLE_RESULT_BLOB_BYTES", blob_size)
    assert exact_blob_repo.stage_record(record, canonical, catalog).record is not None
    small_blob_repo = SolutionRepository.create_empty(
        project_id=record.project_id,
        project_path=tmp_path / "small-blob.cxproj",
        solution_namespace_id="namespace",
        catalog=catalog,
    )
    monkeypatch.setattr(solution_repository_module, "MAX_DURABLE_RESULT_BLOB_BYTES", blob_size - 1)
    assert small_blob_repo.stage_record(record, canonical, catalog).reason_code == "durable_stage_capacity_exceeded"

    monkeypatch.setattr(solution_repository_module, "MAX_DURABLE_RESULT_BLOB_BYTES", 67_108_864)
    exact_record_repo = SolutionRepository.create_empty(
        project_id=record.project_id,
        project_path=tmp_path / "exact-record.cxproj",
        solution_namespace_id="namespace",
        catalog=catalog,
    )
    monkeypatch.setattr(solution_repository_module, "MAX_DURABLE_RECORD_JSON_BYTES", record_size)
    assert exact_record_repo.stage_record(record, canonical, catalog).record is not None
    small_record_repo = SolutionRepository.create_empty(
        project_id=record.project_id,
        project_path=tmp_path / "small-record.cxproj",
        solution_namespace_id="namespace",
        catalog=catalog,
    )
    monkeypatch.setattr(solution_repository_module, "MAX_DURABLE_RECORD_JSON_BYTES", record_size - 1)
    assert small_record_repo.stage_record(record, canonical, catalog).reason_code == "durable_stage_capacity_exceeded"


def test_generation_count_and_aggregate_limits_accept_n_reject_n_plus_one(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _catalog, _outputs, _record, _project_path, repository, durable, metadata = (
        _built_repository(tmp_path)
    )
    generation_root = repository._root / "generations" / metadata["active_generation_id"]  # noqa: SLF001
    node_manifest = next((generation_root / "nodes").rglob("*.json"))
    node_size = node_manifest.stat().st_size
    manifest_size = (generation_root / "manifest-set.json").stat().st_size
    record_digest = repository._record_digests[durable.record_id]  # noqa: SLF001
    record_path = repository._root / "records" / "sha256" / record_digest[:2] / f"{record_digest}.json"  # noqa: SLF001
    blob_digest = durable.payload_locator.reference_id if durable.payload_locator else ""
    blob_path = repository._root / "blobs" / "sha256" / blob_digest[:2] / blob_digest  # noqa: SLF001
    referenced_size = record_path.stat().st_size + blob_path.stat().st_size

    limits = (
        ("MAX_DURABLE_NODE_MANIFESTS_PER_GENERATION", 1),
        ("MAX_DURABLE_RECORDS_PER_NODE", 1),
        ("MAX_DURABLE_RECORDS_PER_GENERATION", 1),
        ("MAX_DURABLE_NODE_MANIFEST_BYTES", node_size),
        ("MAX_DURABLE_NODE_MANIFEST_BYTES_PER_GENERATION", node_size),
        ("MAX_DURABLE_REFERENCED_BYTES_PER_GENERATION", referenced_size),
        ("MAX_DURABLE_MANIFEST_SET_BYTES", manifest_size),
    )
    originals = {name: getattr(solution_repository_module, name) for name, _value in limits}
    for index, (name, exact) in enumerate(limits):
        for restore_name, original in originals.items():
            monkeypatch.setattr(solution_repository_module, restore_name, original)
        monkeypatch.setattr(solution_repository_module, name, exact)
        accepted = repository.build_candidate_generation(
            (durable,),
            generation_id=f"{index + 10:032x}",
        )
        assert accepted.reason_code == "durable_generation_built", name
        monkeypatch.setattr(solution_repository_module, name, exact - 1)
        rejected = repository.build_candidate_generation(
            (durable,),
            generation_id=f"{index + 100:032x}",
        )
        assert rejected.reason_code == "durable_generation_capacity_exceeded", name


def test_validate_enumerate_and_active_prune_share_generation_aggregate_limits(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    catalog, _outputs, record, project_path, repository, durable, metadata = (
        _built_repository(tmp_path)
    )
    repository.close()
    opened = SolutionRepositoryFactory().open_backend(
        record.project_id,
        str(project_path),
        metadata,
        catalog,
    )
    assert isinstance(opened.backend, SolutionRepository)
    root = opened.backend._root  # noqa: SLF001
    generation_root = root / "generations" / metadata["active_generation_id"]
    node_size = next((generation_root / "nodes").rglob("*.json")).stat().st_size
    looked_up_record = opened.backend.lookup_record(
        durable.workspace_id,
        durable.node_id,
        durable.solution_key,
        catalog,
    ).record
    assert looked_up_record is not None
    stored_record_digest = opened.backend._record_digests[durable.record_id]  # noqa: SLF001
    record_path = (
        root
        / "records"
        / "sha256"
        / stored_record_digest[:2]
        / f"{stored_record_digest}.json"
    )
    assert durable.payload_locator is not None
    blob_digest = durable.payload_locator.reference_id
    blob_path = root / "blobs" / "sha256" / blob_digest[:2] / blob_digest
    referenced_size = record_path.stat().st_size + blob_path.stat().st_size
    limits = (
        ("MAX_DURABLE_RECORDS_PER_GENERATION", 1),
        ("MAX_DURABLE_NODE_MANIFEST_BYTES_PER_GENERATION", node_size),
        ("MAX_DURABLE_REFERENCED_BYTES_PER_GENERATION", referenced_size),
    )
    originals = {
        name: getattr(solution_repository_module, name)
        for name, _exact in limits
    }
    for name, exact in limits:
        for restore_name, original in originals.items():
            monkeypatch.setattr(solution_repository_module, restore_name, original)
        monkeypatch.setattr(solution_repository_module, name, exact)
        assert opened.backend.validate_generation(
            metadata["active_generation_id"],
            metadata["active_manifest_set_digest"],
        ).reason_code == "durable_generation_valid"
        assert len(
            opened.backend.enumerate_reachable_paths(
                (metadata["active_generation_id"],)
            )
        ) == 4

        monkeypatch.setattr(solution_repository_module, name, exact - 1)
        assert opened.backend.validate_generation(
            metadata["active_generation_id"],
            metadata["active_manifest_set_digest"],
        ).reason_code == "durable_generation_capacity_exceeded"
        with pytest.raises(ValueError, match="reachability"):
            opened.backend.enumerate_reachable_paths(
                (metadata["active_generation_id"],)
            )
        with pytest.raises(ValueError, match="reachability"):
            opened.backend.prune_unreachable_paths((), reachable_paths=())


def test_durable_json_depth_accepts_n_rejects_n_plus_one() -> None:
    def nested(depth: int) -> dict[str, object]:
        value: object = "leaf"
        for _index in range(depth):
            value = {"nested": value}
        assert isinstance(value, dict)
        return value

    accepted = nested(solution_repository_module.MAX_DURABLE_JSON_DEPTH)
    assert solution_repository_module._strict_json_bytes(  # noqa: SLF001
        _canonical(accepted),
        maximum=len(_canonical(accepted)),
    ) == accepted
    rejected = nested(solution_repository_module.MAX_DURABLE_JSON_DEPTH + 1)
    with pytest.raises(ValueError, match="depth"):
        solution_repository_module._strict_json_bytes(  # noqa: SLF001
            _canonical(rejected),
            maximum=len(_canonical(rejected)),
        )


def test_immutable_publish_never_replaces_racing_winner(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "root"
    original_link = solution_repository_module.os.link

    def racing_link(source: object, target: object) -> None:
        Path(target).write_bytes(b"winner")
        raise FileExistsError

    monkeypatch.setattr(solution_repository_module.os, "link", racing_link)
    with pytest.raises(
        solution_repository_module._RepositoryError,  # noqa: SLF001
        match="durable_nondeterminism_conflict",
    ):
        solution_repository_module._publish_immutable(  # noqa: SLF001
            root,
            "records/value.json",
            b"candidate",
        )
    assert (root / "records" / "value.json").read_bytes() == b"winner"
    monkeypatch.setattr(solution_repository_module.os, "link", original_link)


def test_all_four_schema_one_documents_reject_unknown_fields(tmp_path: Path) -> None:
    manifest = {
        "schema_version": 1,
        "generation_id": "a" * 32,
        "solution_namespace_id": "namespace",
        "node_manifests": [],
        "unknown": True,
    }
    with pytest.raises(ValueError):
        SolutionRepository._manifest_set(_canonical(manifest))  # noqa: SLF001

    node = {
        "schema_version": 1,
        "solution_namespace_id": "namespace",
        "workspace_id": "workspace",
        "node_id": "node",
        "workspace_key": workspace_path_key("workspace"),
        "node_key": node_path_key("node"),
        "records": [],
        "unknown": True,
    }
    with pytest.raises(ValueError):
        solution_repository_module._exact_fields(  # noqa: SLF001
            node,
            solution_repository_module._NODE_MANIFEST_FIELDS,  # noqa: SLF001
        )

    catalog, _outputs, _canonical_payload, record, _project_path = _fixture(tmp_path)
    record_payload = record.to_payload(catalog=catalog)
    record_payload["unknown"] = True
    with pytest.raises(ValueError):
        SolutionRecord.from_payload(record_payload, catalog=catalog)

    result_blob = solution_repository_module._result_blob_payload(  # noqa: SLF001
        record,
        {},
    )
    result_blob["unknown"] = True
    with pytest.raises(ValueError):
        solution_repository_module._exact_fields(  # noqa: SLF001
            result_blob,
            solution_repository_module._RESULT_BLOB_FIELDS,  # noqa: SLF001
        )


def test_lookup_and_payload_fail_closed_on_truncation_without_partial_decode(
    tmp_path: Path,
) -> None:
    catalog, _outputs, record, project_path, repository, durable, metadata = (
        _built_repository(tmp_path)
    )
    repository.close()
    opened = SolutionRepositoryFactory().open_backend(
        record.project_id,
        str(project_path),
        metadata,
        catalog,
    )
    assert opened.backend is not None
    root = project_path.with_name(f"{project_path.stem}.data") / "solutions" / "v1"
    node_manifest = next(
        (root / "generations" / metadata["active_generation_id"] / "nodes").rglob(
            "*.json"
        )
    )
    original_node = node_manifest.read_bytes()
    node_manifest.write_bytes(original_node[:-1])
    assert opened.backend.lookup_record(
        record.workspace_id,
        record.node_id,
        record.solution_key,
        catalog,
    ).reason_code == "durable_node_manifest_digest_mismatch"
    node_manifest.write_bytes(original_node)

    looked_up = opened.backend.lookup_record(
        record.workspace_id,
        record.node_id,
        record.solution_key,
        catalog,
    )
    assert looked_up.record == durable
    assert durable.payload_locator is not None
    blob = (
        root
        / "blobs"
        / "sha256"
        / durable.payload_locator.reference_id[:2]
        / durable.payload_locator.reference_id
    )
    blob.write_bytes(blob.read_bytes()[:-1])
    assert opened.backend.load_payload(
        durable,
        catalog,
    ).reason_code == "durable_payload_digest_mismatch"


def test_lookup_rejects_replace_scan_restore_record_bytes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    catalog, _outputs, record, project_path, repository, _durable, metadata = (
        _built_repository(tmp_path)
    )
    repository.close()
    opened = SolutionRepositoryFactory().open_backend(
        record.project_id,
        str(project_path),
        metadata,
        catalog,
    )
    assert opened.backend is not None
    original_read = solution_repository_module._read_file  # noqa: SLF001

    def replacing_read(root, relative_path, **kwargs):  # noqa: ANN001, ANN202
        relative = str(relative_path)
        if relative.startswith("records/sha256/"):
            target = Path(root).joinpath(*relative.split("/"))
            original = target.read_bytes()
            target.write_bytes(b"x" * len(original))
            try:
                return original_read(root, relative_path, **kwargs)
            finally:
                target.write_bytes(original)
        return original_read(root, relative_path, **kwargs)

    monkeypatch.setattr(solution_repository_module, "_read_file", replacing_read)
    result = opened.backend.lookup_record(
        record.workspace_id,
        record.node_id,
        record.solution_key,
        catalog,
    )
    assert result.reason_code == "durable_record_digest_mismatch"


def test_lookup_rejects_link_or_reparse_components(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    catalog, _outputs, record, project_path, repository, _durable, metadata = (
        _built_repository(tmp_path)
    )
    repository.close()
    opened = SolutionRepositoryFactory().open_backend(
        record.project_id,
        str(project_path),
        metadata,
        catalog,
    )
    assert opened.backend is not None
    generation_nodes = (
        project_path.with_name(f"{project_path.stem}.data")
        / "solutions"
        / "v1"
        / "generations"
        / metadata["active_generation_id"]
        / "nodes"
    )
    workspace_directory = next(path for path in generation_nodes.iterdir() if path.is_dir())
    moved = tmp_path / "moved-node-manifest"
    workspace_directory.rename(moved)
    try:
        workspace_directory.symlink_to(moved, target_is_directory=True)
    except OSError:
        moved.rename(workspace_directory)
        original_validate = solution_repository_module.validate_owned_artifact_path

        def reject_node_manifest(root, relative_path, **kwargs):  # noqa: ANN001, ANN202
            if str(relative_path).startswith("nodes/"):
                raise ValueError("simulated reparse component")
            return original_validate(root, relative_path, **kwargs)

        monkeypatch.setattr(
            solution_repository_module,
            "validate_owned_artifact_path",
            reject_node_manifest,
        )
        monkeypatch.setattr(
            solution_repository_module,
            "_contains_reparse_component",
            lambda _root, _relative: True,
        )
    result = opened.backend.lookup_record(
        record.workspace_id,
        record.node_id,
        record.solution_key,
        catalog,
    )
    assert result.reason_code == "durable_reparse_rejected"


def test_candidate_rejects_full_path_key_collision_before_manifest_publication(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    catalog, _outputs, canonical, record, project_path = _fixture(tmp_path)
    repository = SolutionRepository.create_empty(
        project_id=record.project_id,
        project_path=project_path,
        solution_namespace_id="namespace",
        catalog=catalog,
    )
    first = repository.stage_record(record, canonical, catalog)
    second_record = replace(
        record,
        record_id="record-2",
        workspace_id="workspace-2",
        solution_key="2" * 64,
    )
    second = repository.stage_record(second_record, canonical, catalog)
    assert first.record is not None and second.record is not None
    monkeypatch.setattr(
        solution_repository_module,
        "workspace_path_key",
        lambda _value: "0" * 64,
    )
    result = repository.build_candidate_generation(
        (first.record, second.record),
        generation_id="3" * 32,
    )
    assert result.reason_code == "durable_generation_invalid"
    assert not (
        repository._root  # noqa: SLF001
        / "generations"
        / ("3" * 32)
        / "manifest-set.json"
    ).exists()


def test_prune_prevalidates_the_complete_batch_before_deleting(tmp_path: Path) -> None:
    _catalog, _outputs, _record, _project_path, repository, _durable, _metadata = (
        _built_repository(tmp_path)
    )
    relative = f"blobs/sha256/ff/{'f' * 64}"
    extra = repository._root / relative  # noqa: SLF001
    extra.parent.mkdir(parents=True, exist_ok=True)
    extra.write_bytes(b"garbage")
    with pytest.raises(ValueError, match="candidate"):
        repository.prune_unreachable_paths(
            (relative, "../../outside"),
            reachable_paths=(),
        )
    assert extra.read_bytes() == b"garbage"


def test_reachability_rejects_corruption_instead_of_returning_a_partial_set(
    tmp_path: Path,
) -> None:
    _catalog, _outputs, _record, _project_path, repository, _durable, metadata = (
        _built_repository(tmp_path)
    )
    node_manifest = next(
        (
            repository._root  # noqa: SLF001
            / "generations"
            / metadata["active_generation_id"]
            / "nodes"
        ).rglob("*.json")
    )
    node_manifest.write_bytes(b"{}")
    with pytest.raises(ValueError, match="reachability"):
        repository.enumerate_reachable_paths((metadata["active_generation_id"],))


def test_immutable_publish_reuses_identical_bytes_and_conflicts_on_difference(
    tmp_path: Path,
) -> None:
    root = tmp_path / "root"
    relative = f"records/sha256/aa/{'a' * 64}.json"
    assert solution_repository_module._publish_immutable(  # noqa: SLF001
        root,
        relative,
        b"first",
    )
    assert not solution_repository_module._publish_immutable(  # noqa: SLF001
        root,
        relative,
        b"first",
    )
    with pytest.raises(
        solution_repository_module._RepositoryError,  # noqa: SLF001
        match="durable_nondeterminism_conflict",
    ):
        solution_repository_module._publish_immutable(  # noqa: SLF001
            root,
            relative,
            b"second and longer",
        )
    assert (root / relative).read_bytes() == b"first"

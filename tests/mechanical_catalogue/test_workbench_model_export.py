# Purpose: Verify selected Workbench Model.Export conversion through a separate standalone owner.
# Map: subsystems/addons.md
# Tests: tests/mechanical_catalogue/test_workbench_model_export.py
# Landmarks: _snapshot; test_snapshot_comparison_covers_tree_geometry_loads_selections_snippets_and_views; test_runtime_uses_short_lived_separate_owner_and_keeps_archive_flags_inactive; test_source_owner_flushes_exports_reconnects_and_preserves_workbench; test_conversion_operation_uses_embedded_app_only_in_its_fresh_backend

from __future__ import annotations

import hashlib
import json
import threading
from pathlib import Path
from types import MappingProxyType, MethodType, SimpleNamespace

import pytest

from ea_node_editor.addons.mechanical.backend import MechanicalOwnerBackend
from ea_node_editor.addons.mechanical.contracts import catalogue_table, model_handle
from ea_node_editor.addons.mechanical.runtime import execute_save_model
from ea_node_editor.addons.mechanical.owner_process import OwnerProtocolError
from ea_node_editor.addons.mechanical.saving import (
    compare_model_export_snapshot,
    companion_path,
    create_save_staging,
    model_export_native_owner_map,
    validate_model_export_snapshot,
)
from ea_node_editor.addons.mechanical.session import StaleMechanicalModelError
from ea_node_editor.addons.mechanical.workbench import (
    WORKBENCH_MODEL_EXPORT_BODY,
    validate_workbench_model_export_snapshots,
)
from ea_node_editor.nodes.execution_context import ExecutionContext
from ea_node_editor.runtime_contracts.scientific_values import snapshot_scientific_value
from tests.mechanical_catalogue.test_contracts import _model_metadata, _row
from tests.mechanical_catalogue.test_search_tree import Native, remote_objects
from tests.mechanical_catalogue.test_workbench_save import SAVE_DATA_TYPES, _Workbench, _project


def _definition_fingerprint(
    *, sample: float = 300.0, unit: str = "Pa", formula: str = "",
) -> str:
    owner = {
        "owner_index": 3,
        "owner_parent_index": 1,
        "object_path": "tree:0/1/3",
    }
    return json.dumps({
        "sources": [{
            "kind": "property",
            **owner,
            "property_key": "Magnitude",
        }],
        "tables": [{
            "columns": [f"Pressure [{unit}]"],
            "index": [0],
            "data": [[sample]],
        }],
        "definitions": {
            "columns": ["object_path", "property_key", "unit", "formula"],
            "index": [0],
            "data": [[owner["object_path"], "Magnitude", unit, formula]],
        },
    }, sort_keys=True, separators=(",", ":"))


def _snapshot() -> dict[str, object]:
    base = {"name": "Static Structural", "api_type": "Analysis", "parent_index": 0}
    return {
        "schema_version": 1,
        "tree": [
            {"name": "Model", "api_type": "Model", "parent_index": None},
            base,
            {"name": "Body", "api_type": "Body", "parent_index": 0},
            {"name": "Pressure", "api_type": "Pressure", "parent_index": 1},
            {"name": "COREX selection", "api_type": "NamedSelection", "parent_index": 0},
            {"name": "COREX snippet", "api_type": "CommandSnippet", "parent_index": 1},
        ],
        "analyses": [base],
        "bodies": [
            {
                "name": "Body", "api_type": "Body", "parent_index": 0,
                "suppressed": False,
                "geometry": {
                    "geometry_type": "Solid",
                    "topology": {"face_count": 6, "edge_count": 12, "vertex_count": 8},
                    "quantities": {
                        key: {"value": value, "unit": unit}
                        for key, value, unit in (
                            ("Volume", 1.0, "mm^3"), ("SurfaceArea", 6.0, "mm^2"),
                            ("LengthX", 1.0, "mm"), ("LengthY", 1.0, "mm"),
                            ("LengthZ", 1.0, "mm"), ("CentroidX", 0.5, "mm"),
                            ("CentroidY", 0.5, "mm"), ("CentroidZ", 0.5, "mm"),
                        )
                    },
                },
            }
        ],
        "scopes": [{
            "owner_index": 3,
            "role": "Location",
            "selection_type": "GeometryEntities",
            "identities": [{"body_index": 0, "kind": "face", "index": 2}],
        }],
        "snippets": [{
            "name": "COREX snippet",
            "api_type": "CommandSnippet",
            "parent_index": 1,
            "input": "/COM,COREX",
            "step_selection_mode": "All",
            "step_number": 1,
            "issue_solve_command": False,
        }],
        "settings": [{
            "owner_index": 3,
            "owner_parent_index": 1,
            "object_path": "tree:0/1/3",
            "property_key": "Magnitude",
            "caption": "Magnitude",
            "display_value": "300 Pa",
            "definition_kind": "scalar",
            "scalar_value": 300.0,
            "unit": "Pa",
            "quantity_name": "Pressure",
            "formula": "",
            "has_tabular_data": False,
            "tables": [],
        }],
        "definitions": [_definition_fingerprint()],
        "cameras": [{
            "kind": "saved", "name": "COREX view", "index": 0,
            "focal_point": [0.0, 0.0, 0.0],
            "view_vector": [1.0, 0.0, 0.0],
            "up_vector": [0.0, 1.0, 0.0],
            "scene_width": 10.0, "scene_height": 8.0,
            "length_unit": "mm", "availability_notes": {},
        }],
        "unreadable_display_diagnostics": [{
            "owner_index": 3,
            "owner_parent_index": 1,
            "object_path": "tree:0/1/3",
            "property_key": "Location",
            "reason": "unreadable",
        }],
    }


def _write_snapshot(
    path: Path, value: dict[str, object] | None = None,
) -> dict[str, object]:
    encoded = json.dumps(
        value or _snapshot(), ensure_ascii=False, separators=(",", ":")
    ).encode()
    path.write_bytes(encoded)
    return {"byte_length": len(encoded), "sha256": hashlib.sha256(encoded).hexdigest()}


def test_snapshot_comparison_covers_tree_geometry_loads_selections_snippets_and_views() -> None:
    proof = compare_model_export_snapshot(_snapshot(), _snapshot())
    assert proof == {
        "tree_object_count": 6,
        "analysis_count": 1,
        "body_count": 1,
        "definition_count": 1,
        "setting_count": 1,
        "scope_count": 1,
        "snippet_count": 1,
        "camera_count": 1,
    }
    changed = _snapshot()
    changed["bodies"][0]["geometry"]["quantities"]["Volume"]["value"] = 2.0
    with pytest.raises(RuntimeError, match="changed bodies"):
        compare_model_export_snapshot(_snapshot(), changed)
    for field, mutate in (
        ("settings", lambda value: value["settings"][0].update(display_value="301 Pa")),
        ("cameras", lambda value: value["cameras"][0].update(view_vector=[0.0, 0.0, 1.0])),
        ("scopes", lambda value: value["scopes"][0]["identities"][0].update(index=3)),
    ):
        changed = _snapshot()
        mutate(changed)
        with pytest.raises(RuntimeError, match=f"changed {field}"):
            compare_model_export_snapshot(_snapshot(), changed)
    diagnostic_only = _snapshot()
    diagnostic_only["unreadable_display_diagnostics"][0]["reason"] = "still unreadable"
    compare_model_export_snapshot(_snapshot(), diagnostic_only)
    for fingerprint in (
        _definition_fingerprint(sample=301.0),
        _definition_fingerprint(formula="2*t"),
        _definition_fingerprint(unit="kPa"),
    ):
        changed = _snapshot()
        changed["definitions"] = [fingerprint]
        with pytest.raises(RuntimeError, match="changed definitions"):
            compare_model_export_snapshot(_snapshot(), changed)
    unrelated_path = _snapshot()
    unrelated_path["settings"][0].update(
        property_key="UserPath", display_value=r"C:\different\model.input"
    )
    with pytest.raises(RuntimeError, match="changed settings"):
        compare_model_export_snapshot(_snapshot(), unrelated_path)
    for owner_change, error in (
        ({"owner_parent_index": 0}, "settings fingerprint is invalid"),
        (
            {"owner_index": 99, "owner_parent_index": None, "object_path": "tree:99"},
            "owner index is invalid",
        ),
    ):
        changed = _snapshot()
        changed["settings"][0].update(owner_change)
        with pytest.raises(RuntimeError, match=error):
            validate_model_export_snapshot(changed)


def _base_snapshot() -> dict[str, object]:
    return {
        "native_owner_ids": [100, 101, 102, 103, 104, 105],
        **{
            key: value
            for key, value in _snapshot().items()
            if key
            in {"schema_version", "tree", "analyses", "bodies", "scopes", "snippets"}
        },
    }


def _semantics() -> dict[str, object]:
    return {
        key: value
        for key, value in _snapshot().items()
        if key in {"settings", "definitions", "cameras", "unreadable_display_diagnostics"}
    }


def test_invalid_bounded_candidate_is_retained_before_validation(tmp_path: Path) -> None:
    semantics = _semantics()
    semantics["settings"][0]["owner_parent_index"] = 0
    path = tmp_path / "bridge-model.json"
    with pytest.raises(RuntimeError, match="settings fingerprint is invalid"):
        MechanicalOwnerBackend._write_model_export_snapshot(
            path, _base_snapshot(), semantics
        )
    assert path.is_file()
    retained = json.loads(path.read_text(encoding="utf-8"))
    assert retained["settings"][0]["owner_parent_index"] == 0


def test_native_workbench_route_uses_export_without_archive_or_internal_copy() -> None:
    assert "container.Exit(SaveDatabase=True)" in WORKBENCH_MODEL_EXPORT_BODY
    assert "container.Export(FilePath=bridge)" in WORKBENCH_MODEL_EXPORT_BODY
    assert "Save()" in WORKBENCH_MODEL_EXPORT_BODY
    assert "Archive(" not in WORKBENCH_MODEL_EXPORT_BODY
    assert "Unarchive(" not in WORKBENCH_MODEL_EXPORT_BODY
    assert "copy" not in WORKBENCH_MODEL_EXPORT_BODY.casefold()


def test_model_export_report_omits_archive_only_workbench_proof(
    tmp_path: Path, monkeypatch,
) -> None:
    monkeypatch.setattr(
        "ea_node_editor.addons.mechanical.workbench.validate_workbench_semantic_snapshots",
        lambda *_args, **_kwargs: {
            "system_count": 3,
            "results_authority": "native IncludeSkippedFiles",
            "state_file_logical_comparison": None,
        },
    )
    assert validate_workbench_model_export_snapshots(
        tmp_path / "w.json",
        receipt={},
        work_path=tmp_path / "work.wbpj",
    ) == {"system_count": 3, "source_workbench_preserved": True}


def test_field_discovery_uses_exact_object_field_when_internal_value_is_scalar(
    tmp_path: Path, monkeypatch
) -> None:
    prop = SimpleNamespace(
        APIName="XComponent",
        Name="X Component",
        InternalValue=99.0,
    )
    field = SimpleNamespace(Inputs=[], Output=SimpleNamespace(sample=5.0))
    project = Native(
        ObjectId=10, Name="Project", Parent=None,
        api_type="Ansys.ACT.Automation.Mechanical.Project",
        DataModelObjectCategory="Project", VisibleProperties=[], Properties=[],
    )
    model = Native(
        ObjectId=11, Name="Model", Parent=project,
        api_type="Ansys.ACT.Automation.Mechanical.Model",
        DataModelObjectCategory="Model", VisibleProperties=[], Properties=[],
    )
    analysis = Native(
        ObjectId=1, Name="Analysis", Parent=model,
        api_type="Ansys.ACT.Automation.Mechanical.Analysis",
        DataModelObjectCategory="Analysis", VisibleProperties=[], Properties=[],
    )
    load = Native(
        ObjectId=2,
        Name="Load",
        Parent=analysis,
        api_type="Ansys.ACT.Automation.Mechanical.BoundaryConditions.Displacement",
        DataModelObjectCategory="Displacement",
        VisibleProperties=[prop],
        Properties=[prop],
        XComponent=field,
    )
    backend = MechanicalOwnerBackend()
    backend.tree = SimpleNamespace(
        AllObjects=remote_objects([project, model, analysis, load])
    )
    backend.model = object()
    backend.work_root = tmp_path
    backend.app = SimpleNamespace(
        execute_script=lambda _script: json.dumps({"views": []})
    )
    project_payload = {
        "object_id": 10,
        "parent_id": None,
        "display_name": "Project",
        "object_path": "Project",
        "api_type": "Ansys.ACT.Automation.Mechanical.Project",
        "analysis_id": None,
    }
    model_payload = {
        "object_id": 11,
        "parent_id": 10,
        "display_name": "Model",
        "object_path": "Project/Model",
        "api_type": "Ansys.ACT.Automation.Mechanical.Model",
        "analysis_id": None,
    }
    analysis_payload = {
        "object_id": 1,
        # Reproduces the direct proxy boundary observed in raw native evidence:
        # the analysis omits its Project/Model parent chain.
        "parent_id": None,
        "display_name": "Analysis",
        "object_path": "Project/Model/Analysis",
        "api_type": "Ansys.ACT.Automation.Mechanical.Analysis",
        "analysis_id": 1,
    }
    object_payload = {
        "object_id": 2,
        "parent_id": 1,
        "display_name": "Load",
        "object_path": "Project/Model/Analysis/Load",
        "api_type": "Ansys.ACT.Automation.Mechanical.BoundaryConditions.Displacement",
        "analysis_id": 1,
    }
    property_payload = {
        "object_id": 2,
        "object_path": "Project/Model/Analysis/Load",
        "property_key": "XComponent",
        "caption": "X Component",
        "display_value": "same tabular shape",
        "definition_kind": "tabular",
        "scalar_value": None,
        "unit": "N",
        "quantity_name": "Force",
        "formula": "",
        "has_tabular_data": True,
        "tables": [{
            "table_family": "field_definition",
            "definition_kind": "Field",
            "row_count": 1,
            "column_count": 1,
        }],
        "value_status": "available",
    }
    monkeypatch.setattr(
        "ea_node_editor.addons.mechanical.backend.search_tree",
        lambda **_kwargs: {
            "objects": [
                SimpleNamespace(payload=project_payload),
                SimpleNamespace(payload=model_payload),
                SimpleNamespace(payload=analysis_payload),
                SimpleNamespace(payload=object_payload),
            ],
            "properties": [SimpleNamespace(payload=property_payload)],
        },
    )
    captured = []

    def definitions(args):
        captured.append(args["sources"])
        import pandas as pd

        sample = field.Output.sample
        return {"definition_tables": {
            "tables": [snapshot_scientific_value(pd.DataFrame({"X [N]": [sample]}))],
            "definitions": snapshot_scientific_value(pd.DataFrame({
                "object_path": [args["sources"][0]["object_path"]],
                "property_key": ["XComponent"],
                "sample": [sample],
            })),
        }}

    monkeypatch.setattr(backend, "definition_tables", definitions)
    identity = {
        key: value
        for key, value in _row().items()
        if key in {
            "schema_version", "model_revision", "producer_iteration", "catalogue_id",
            "producer_node_id", "producer_port", "producer_path", "run_id", "session_id",
            "document_id", "source_key", "system_key",
        }
    }
    base = {
        "schema_version": 1,
        "native_owner_ids": [10, 11, 1, 2],
        "tree": [
            {"name": "Project", "api_type": project.api_type, "parent_index": None},
            {"name": "Model", "api_type": model.api_type, "parent_index": 0},
            {"name": "Analysis", "api_type": analysis.api_type, "parent_index": 1},
            {"name": "Load", "api_type": load.api_type, "parent_index": 2},
        ],
        "analyses": [
            {"name": "Analysis", "api_type": analysis.api_type, "parent_index": 1}
        ],
        "bodies": [],
        "scopes": [],
        "snippets": [],
    }
    first = backend._write_model_export_snapshot(
        tmp_path / "first.json",
        base,
        backend._model_export_semantics(
            identity,
            owner_tree=base["tree"],
            native_owner_ids=base["native_owner_ids"],
            label="test",
        ),
    )
    field.Output = SimpleNamespace(sample=6.0)
    second = backend._write_model_export_snapshot(
        tmp_path / "second.json",
        base,
        backend._model_export_semantics(
            identity,
            owner_tree=base["tree"],
            native_owner_ids=base["native_owner_ids"],
            label="test",
        ),
    )
    assert prop.InternalValue == 99.0
    assert captured == [
        [{
            "kind": "property", "object_id": 2,
            "object_path": "Project/Model/Analysis/Load", "property_key": "XComponent",
        }],
        [{
            "kind": "property", "object_id": 2,
            "object_path": "Project/Model/Analysis/Load", "property_key": "XComponent",
        }],
    ]
    with pytest.raises(RuntimeError, match="changed definitions"):
        compare_model_export_snapshot(first, second)


@pytest.mark.parametrize(
    (
        "display_value", "native_working_dir", "analysis_id", "owner_api_type",
        "owner_parent_id", "error",
    ),
    [
        (
            r"C:\run\solver", r"C:\run\solver", 1,
            "Ansys.ACT.Automation.Mechanical.AnalysisSettings.ANSYSAnalysisSettings", 1, "",
        ),
        (
            r"C:\wrong\solver", r"C:\run\solver", 1,
            "Ansys.ACT.Automation.Mechanical.AnalysisSettings.ANSYSAnalysisSettings", 1,
            "does not match",
        ),
        (
            r"C:\run\solver", None, 1,
            "Ansys.ACT.Automation.Mechanical.AnalysisSettings.ANSYSAnalysisSettings", 1,
            "WorkingDir is unavailable",
        ),
        (
            r"C:\run\solver", r"C:\run\solver", 99,
            "Ansys.ACT.Automation.Mechanical.AnalysisSettings.ANSYSAnalysisSettings", 99,
            "tree-owner parent mapping is misaligned",
        ),
        (
            r"C:\run\solver", r"C:\run\solver", 1,
            "Ansys.ACT.Automation.Mechanical.BoundaryConditions.FixedSupport", 1,
            "requires an exact direct Analysis Settings owner",
        ),
        (
            r"C:\run\solver", r"C:\run\solver", 1,
            "Ansys.ACT.Automation.Mechanical.AnalysisSettings.ANSYSAnalysisSettings", None,
            "requires an exact direct Analysis Settings owner",
        ),
        (
            r"C:\run\solver", r"C:\run\solver", 1,
            "Ansys.ACT.Automation.Mechanical.AnalysisSettings", 1,
            "requires an exact direct Analysis Settings owner",
        ),
    ],
)
def test_solver_files_directory_requires_exact_native_analysis_working_dir(
    tmp_path: Path,
    monkeypatch,
    display_value: str,
    native_working_dir: str | None,
    analysis_id: int,
    owner_api_type: str,
    owner_parent_id: int | None,
    error: str,
) -> None:
    property_value = SimpleNamespace(
        APIName="SolverFilesDirectory",
        Name="Solver Files Directory",
        InternalValue=display_value,
    )
    analysis = SimpleNamespace(ObjectId=1, VisibleProperties=[])
    if native_working_dir is not None:
        analysis.WorkingDir = native_working_dir
    settings = SimpleNamespace(ObjectId=2, VisibleProperties=[property_value])
    backend = MechanicalOwnerBackend()
    backend.tree = SimpleNamespace(AllObjects=[analysis, settings])
    backend.model = object()
    backend.work_root = tmp_path
    backend.app = SimpleNamespace(
        execute_script=lambda _script: json.dumps({"views": []})
    )
    objects = [
        SimpleNamespace(payload={
            "object_id": 1,
            "parent_id": None,
            "display_name": "Analysis",
            "object_path": "Project/Model/Analysis",
            "api_type": "Ansys.ACT.Automation.Mechanical.Analysis",
            "analysis_id": 1,
        }),
        SimpleNamespace(payload={
            "object_id": 2,
            "parent_id": owner_parent_id,
            "display_name": "Analysis Settings",
            "object_path": "Project/Model/Analysis/Analysis Settings",
            "api_type": owner_api_type,
            "analysis_id": analysis_id,
        }),
    ]
    prop = SimpleNamespace(payload={
        "object_id": 2,
        "object_path": "Project/Model/Analysis/Analysis Settings",
        "property_key": "SolverFilesDirectory",
        "caption": "Solver Files Directory",
        "display_value": display_value,
        "definition_kind": "scalar",
        "scalar_value": None,
        "unit": "",
        "quantity_name": "",
        "formula": "",
        "has_tabular_data": False,
        "tables": [],
        "value_status": "available",
    })
    monkeypatch.setattr(
        "ea_node_editor.addons.mechanical.backend.search_tree",
        lambda **_kwargs: {"objects": objects, "properties": [prop]},
    )
    identity = {key: value for key, value in _row().items() if key in {
        "run_id", "session_id", "document_id", "source_key", "system_key",
        "model_revision",
    }}
    owner_tree = [
        {
            "name": "Analysis",
            "api_type": "Ansys.ACT.Automation.Mechanical.Analysis",
            "parent_index": None,
        },
        {
            "name": "Analysis Settings",
            "api_type": owner_api_type,
            "parent_index": 0,
        },
    ]
    if error:
        with pytest.raises(RuntimeError, match=error):
            backend._model_export_semantics(
                identity,
                owner_tree=owner_tree,
                native_owner_ids=[1, 2],
                label="test",
            )
    else:
        result = backend._model_export_semantics(
            identity,
            owner_tree=owner_tree,
            native_owner_ids=[1, 2],
            label="test",
        )
        assert result["settings"] == []
        assert result["unreadable_display_diagnostics"] == [{
            "owner_index": 1,
            "owner_parent_index": 0,
            "object_path": "tree:0/1",
            "property_key": "SolverFilesDirectory",
            "reason": "runtime_location:SolverFilesDirectory",
        }]


def test_model_export_rejects_ambiguous_tree_owner_ids(tmp_path: Path, monkeypatch) -> None:
    backend = MechanicalOwnerBackend()
    backend.tree = SimpleNamespace(AllObjects=[])
    backend.model = object()
    backend.work_root = tmp_path
    duplicate = {
        "object_id": 1,
        "parent_id": None,
        "display_name": "Analysis",
        "object_path": "Analysis",
        "api_type": "Ansys.ACT.Automation.Mechanical.Analysis",
        "analysis_id": 1,
    }
    monkeypatch.setattr(
        "ea_node_editor.addons.mechanical.backend.search_tree",
        lambda **_kwargs: {
            "objects": [
                SimpleNamespace(payload=duplicate),
                SimpleNamespace(payload=dict(duplicate)),
            ],
            "properties": [],
        },
    )
    with pytest.raises(RuntimeError, match="tree-owner identity is ambiguous"):
        backend._model_export_semantics(
            {},
            owner_tree=[
                {"name": "Analysis", "api_type": duplicate["api_type"], "parent_index": None},
                {"name": "Other", "api_type": duplicate["api_type"], "parent_index": None},
            ],
            native_owner_ids=[1, 2],
            label="test",
        )


def test_native_owner_map_rejects_duplicate_missing_misaligned_and_cyclic_rows(
    tmp_path: Path, monkeypatch
) -> None:
    tree = [
        {"name": "Project", "api_type": "Project", "parent_index": None},
        {"name": "Model", "api_type": "Model", "parent_index": 0},
    ]
    with pytest.raises(RuntimeError, match="native owner mapping is invalid"):
        model_export_native_owner_map(tree, [10])
    with pytest.raises(RuntimeError, match="native owner mapping is invalid"):
        model_export_native_owner_map(tree, [10, 10])
    cyclic = [
        {"name": "Project", "api_type": "Project", "parent_index": 1},
        {"name": "Model", "api_type": "Model", "parent_index": 0},
    ]
    with pytest.raises(RuntimeError, match="owner ancestry is invalid"):
        model_export_native_owner_map(cyclic, [10, 11])

    backend = MechanicalOwnerBackend()
    backend.tree = SimpleNamespace(AllObjects=[])
    backend.model = object()
    backend.work_root = tmp_path
    only_project = SimpleNamespace(payload={
        "object_id": 10,
        "parent_id": None,
        "display_name": "Project",
        "object_path": "Project",
        "api_type": "Project",
        "analysis_id": None,
    })
    monkeypatch.setattr(
        "ea_node_editor.addons.mechanical.backend.search_tree",
        lambda **_kwargs: {"objects": [only_project], "properties": []},
    )
    with pytest.raises(RuntimeError, match="tree-owner mapping is incomplete"):
        backend._model_export_semantics(
            {}, owner_tree=tree, native_owner_ids=[10, 11], label="test"
        )


class _Sessions:
    def __init__(self, root: Path, source: Path):
        self.session = SimpleNamespace(
            revision=2,
            connection_generation=4,
            work_root=root / "run",
            work_path=_project(root / "run" / "work.wbpj"),
            source_path=source,
            terminal=False,
        )
        self.calls: list[dict[str, object]] = []

    def admit_model(self, model, **_kwargs):
        if (
            model.metadata["model_revision"] != self.session.revision
            or model.metadata["connection_generation"] != self.session.connection_generation
        ):
            raise StaleMechanicalModelError("stale")
        return self.session

    def operate(self, _session, **kwargs):
        self.calls.append(kwargs)
        self.session.revision += 1
        self.session.connection_generation += 1
        args = kwargs["args"]
        bridge = Path(args["bridge_path"])
        bridge.parent.mkdir()
        bridge.write_bytes(b"native-dsdb")
        snapshot = Path(args["model_snapshot_path"])
        receipt = _write_snapshot(snapshot)
        Path(args["snapshot_path"]).write_text("{}", encoding="utf-8")
        row = _row(
            model_revision=3,
            catalogue_id=args["catalogue_identity"]["catalogue_id"],
            producer_node_id="save-1",
            producer_port="report",
            producer_path="[3,1]",
            producer_iteration=4,
            system_key="SYS",
        )
        return {
            "status": "exported",
            "native_export": {
                "bridge_bytes": bridge.stat().st_size,
                "bridge_sha256": hashlib.sha256(bridge.read_bytes()).hexdigest(),
                "snapshot_bytes": receipt["byte_length"],
                "snapshot_sha256": receipt["sha256"],
            },
            "connection_changed": True,
            "connection_generation": self.session.connection_generation,
            "catalogue": catalogue_table([row]),
        }

    @staticmethod
    def register_model(_session, **kwargs):
        return kwargs


def _context(root: Path, sessions: _Sessions, destination: Path, **properties):
    invalidations = []
    values = {
        "file": str(destination),
        "format": "auto",
        "include_results": "inactive",
        "include_user_files": "inactive",
        "include_external_imported_files": "inactive",
        "overwrite": False,
        **properties,
    }
    return ExecutionContext(
        run_id="run-1",
        node_id="save-1",
        workspace_id="workspace-1",
        inputs={},
        properties=values,
        emit_log=lambda *_: None,
        path_resolver=lambda value: Path(value),
        worker_services=SimpleNamespace(
            mechanical_session_service=sessions,
            data_types=SAVE_DATA_TYPES,
        ),
        target_path=(3, 1),
        target_iteration=4,
        workspace_node_types=MappingProxyType(
            {"open-1": "mechanical.open_model", "save-1": "mechanical.save_model"}
        ),
        _request_observation_invalidation=lambda root_id, reason: invalidations.append(
            (root_id, reason)
        ),
    ), invalidations


def _model():
    return model_handle(
        handle_id="model",
        owner_scope="run-1",
        worker_generation=1,
        metadata=_model_metadata(
            model_revision=2,
            connection_generation=4,
            system_key="SYS",
        ),
    )


@pytest.mark.parametrize("format_code", ["mechdb", "mechdat"])
def test_runtime_uses_short_lived_separate_owner_and_keeps_archive_flags_inactive(
    tmp_path: Path, monkeypatch, format_code: str
) -> None:
    source = _project(tmp_path / "source.wbpj")
    sessions = _Sessions(tmp_path, source)
    destination = tmp_path / f"selected.{format_code}"
    owners = []

    class ConversionOwner:
        def __init__(self, *, work_root):
            self.work_root = Path(work_root)
            self.closed = False
            self.calls = []
            owners.append(self)

        def request(self, **kwargs):
            self.calls.append(kwargs)
            args = kwargs["args"]
            stage = Path(args["stage_path"])
            stage.write_bytes(b"standalone")
            Path(args["stage_companion"]).mkdir()
            return {
                "status": "converted",
                "native_save": {
                    "schema_version": 1,
                    "marker": "corex-workbench-model-export-v1",
                    "format": format_code,
                    "reopen_verified": True,
                    "source_workbench_preserved": True,
                    "bridge_bytes": args["bridge_bytes"],
                    "stage_bytes": stage.stat().st_size,
                    "tree_object_count": 6,
                    "analysis_count": 1,
                    "body_count": 1,
                    "definition_count": 1,
                    "setting_count": 1,
                    "scope_count": 1,
                    "snippet_count": 1,
                    "camera_count": 1,
                },
            }

        def close(self):
            self.closed = True

    monkeypatch.setattr(
        "ea_node_editor.addons.mechanical.runtime.MechanicalOwnerProcess",
        ConversionOwner,
    )
    ctx, invalidations = _context(tmp_path, sessions, destination)
    result = execute_save_model(ctx, _model(), SimpleNamespace(**ctx.properties))
    source_call = sessions.calls[0]
    assert source_call["operation"] == "workbench_model_export"
    assert source_call["mutation"] is True and source_call["connection_change"] is True
    assert not {
        "include_results", "include_user_files", "include_external_imported_files"
    } & source_call["args"].keys()
    assert len(owners) == 1 and owners[0].closed is True
    assert owners[0].calls[0]["operation"] == "convert_workbench_model"
    assert owners[0].calls[0]["args"]["bridge_path"].endswith("b.dsdb")
    assert result["files"] == [str(destination), str(companion_path(destination, format_code))]
    assert result["model"]["producer_node_id"] == "save-1"
    assert invalidations == [("open-1", "mechanical_model_mutated")]
    with pytest.raises(ValueError, match="stale_reference"):
        execute_save_model(ctx, _model(), SimpleNamespace(**ctx.properties))


def test_runtime_reuses_publication_rollback_after_conversion(tmp_path: Path, monkeypatch) -> None:
    source = _project(tmp_path / "source.wbpj")
    sessions = _Sessions(tmp_path, source)
    destination = tmp_path / "selected.mechdb"
    destination.write_bytes(b"old-primary")
    old_companion = companion_path(destination, "mechdb")
    assert old_companion is not None
    old_companion.mkdir()
    (old_companion / "old.txt").write_bytes(b"old-companion")

    class ConversionOwner:
        def __init__(self, **_kwargs): pass
        def request(self, **kwargs):
            args = kwargs["args"]
            stage = Path(args["stage_path"])
            stage.write_bytes(b"new-primary")
            companion = Path(args["stage_companion"])
            companion.mkdir()
            (companion / "new.txt").write_bytes(b"new-companion")
            return {"status": "converted", "native_save": {
                "schema_version": 1, "marker": "corex-workbench-model-export-v1",
                "format": "mechdb", "reopen_verified": True,
                "source_workbench_preserved": True,
                "bridge_bytes": args["bridge_bytes"], "stage_bytes": stage.stat().st_size,
                "tree_object_count": 6, "analysis_count": 1, "body_count": 1,
                "definition_count": 1, "setting_count": 1, "scope_count": 1,
                "snippet_count": 1, "camera_count": 1,
            }}
        def close(self): pass

    monkeypatch.setattr(
        "ea_node_editor.addons.mechanical.runtime.MechanicalOwnerProcess",
        ConversionOwner,
    )
    monkeypatch.setattr(
        "ea_node_editor.addons.mechanical.runtime.serialize_runtime_value",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("serialize failed")),
    )
    ctx, _ = _context(tmp_path, sessions, destination, overwrite=True)
    with pytest.raises(RuntimeError, match="serialize failed"):
        execute_save_model(ctx, _model(), SimpleNamespace(**ctx.properties))
    assert destination.read_bytes() == b"old-primary"
    assert (old_companion / "old.txt").read_bytes() == b"old-companion"
    assert not (old_companion / "new.txt").exists()


def test_runtime_cancellation_closes_conversion_owner_before_publication(
    tmp_path: Path, monkeypatch
) -> None:
    source = _project(tmp_path / "source.wbpj")
    sessions = _Sessions(tmp_path, source)
    destination = tmp_path / "cancelled.mechdb"
    started = threading.Event()
    closed = threading.Event()
    callbacks = []

    class BlockingOwner:
        def __init__(self, **_kwargs): pass
        def request(self, **_kwargs):
            started.set()
            if not closed.wait(5):
                raise AssertionError("cancel callback did not close the conversion owner")
            raise OwnerProtocolError("conversion owner closed")
        def close(self):
            closed.set()

    monkeypatch.setattr(
        "ea_node_editor.addons.mechanical.runtime.MechanicalOwnerProcess",
        BlockingOwner,
    )
    ctx, _ = _context(tmp_path, sessions, destination)
    cancelled = threading.Event()
    ctx.should_stop = cancelled.is_set
    ctx.register_cancel = callbacks.append
    outcome = []

    def execute():
        try:
            outcome.append(
                execute_save_model(ctx, _model(), SimpleNamespace(**ctx.properties))
            )
        except BaseException as exc:
            outcome.append(exc)

    worker = threading.Thread(target=execute)
    worker.start()
    assert started.wait(5) and len(callbacks) == 1
    cancelled.set()
    callbacks[0]()
    worker.join(timeout=5)
    assert not worker.is_alive()
    assert len(outcome) == 1 and isinstance(outcome[0], RuntimeError)
    assert closed.is_set()
    assert not destination.exists()
    companion = companion_path(destination, "mechdb")
    assert companion is not None and not companion.exists()


def test_source_owner_flushes_exports_reconnects_and_preserves_workbench(tmp_path: Path, monkeypatch) -> None:
    source = _project(tmp_path / "source.wbpj").resolve()
    work = _project(tmp_path / "work.wbpj").resolve()
    staging = create_save_staging(tmp_path / "selected.mechdb", "mechdb")
    workbench = _Workbench(work)
    for container in {system.container for system in workbench.systems if hasattr(system, "container")}:
        def export(self, *, FilePath):
            self.calls.append(("Export", self.Name, FilePath))
            Path(FilePath).write_bytes(b"native-dsdb")
        container.Export = MethodType(export, container)
    backend = MechanicalOwnerBackend()
    backend.workbench = workbench
    backend.mechanical = SimpleNamespace()
    backend.mechanical_server_started = True
    backend.system_name = "SYS"
    backend.source_path = source
    backend.work_path = work
    backend.work_root = tmp_path.resolve()
    backend.systems = [
        {"key": "SYS", "label": "Primary", "model_key": "Model", "system_keys": ["SYS", "SYS 1"]},
        {"key": "SYS 2", "label": "Independent", "model_key": "Model 2", "system_keys": ["SYS 2"]},
    ]
    snapshot_path = staging.root / "m.json"

    def execute_source_snapshot(_script):
        return _write_snapshot(snapshot_path, _base_snapshot())

    monkeypatch.setattr(backend, "_execute_native_script", execute_source_snapshot)
    monkeypatch.setattr(backend, "_execute_native_json", lambda *_args, **_kwargs: _base_snapshot())
    monkeypatch.setattr(backend, "_model_export_semantics", lambda *_args, **_kwargs: _semantics())

    def reconnect():
        workbench.calls.append(("reconnect", backend.system_name))
        backend.mechanical = SimpleNamespace()
        backend.tree = backend.model = backend.graphics = SimpleNamespace()

    monkeypatch.setattr(backend, "_connect_workbench_model", reconnect)
    monkeypatch.setattr(
        "ea_node_editor.addons.mechanical.backend.collect_catalogue_rows",
        lambda **kwargs: [_row(
            model_revision=3,
            catalogue_id=kwargs["identity"]["catalogue_id"],
            producer_node_id="save-1",
            producer_port="report",
            producer_path="[0]",
            producer_iteration=0,
            system_key="SYS",
        )],
    )
    args = {
        "format": "mechdb",
        "source_path": str(source),
        "destination_path": str(tmp_path / "selected.mechdb"),
        "work_path": str(work),
        "bridge_path": str(staging.root / "b" / "b.dsdb"),
        "snapshot_path": str(staging.root / "w.json"),
        "model_snapshot_path": str(snapshot_path),
        "stage_path": str(staging.primary),
        "stage_companion": str(staging.companion),
        "verify_path": str(staging.verify_project),
        "files": [str(tmp_path / "selected.mechdb")],
        "overwrite": False,
        "catalogue_identity": {
            key: value for key, value in _row(
                model_revision=3,
                catalogue_id="00000000-0000-0000-0000-000000000001",
                producer_node_id="save-1",
                producer_port="report",
                producer_path="[0]",
                producer_iteration=0,
                system_key="SYS",
            ).items() if key in {
                "schema_version", "model_revision", "producer_iteration", "catalogue_id",
                "producer_node_id", "producer_port", "producer_path", "run_id", "session_id",
                "document_id", "source_key", "system_key",
            }
        },
        "view_export_path": str(tmp_path / "views.xml"),
    }
    result = backend.workbench_model_export(args)
    names = [call[0] for call in workbench.calls]
    assert names.index("stop") < names.index("Exit") < names.index("Save") < names.index("Export") < names.index("reconnect")
    assert all(name not in {"Archive", "Unarchive"} for name in names)
    assert result["status"] == "exported"
    assert result["connection_changed"] is True and result["connection_generation"] == 1
    assert backend.systems[0]["system_keys"] == ["SYS", "SYS 1"]


def test_conversion_operation_uses_embedded_app_only_in_its_fresh_backend(
    tmp_path: Path, monkeypatch
) -> None:
    staging = create_save_staging(tmp_path / "selected.mechdat", "mechdat")
    bridge = staging.root / "b" / "b.dsdb"
    bridge.parent.mkdir()
    bridge.write_bytes(b"native-dsdb")
    snapshot_path = staging.root / "m.json"
    snapshot_receipt = _write_snapshot(snapshot_path)
    calls = []

    class App:
        def __init__(self, *, version):
            calls.append(("App", version))
        def open(self, path):
            calls.append(("Open", Path(path).suffix))
        def save_as(self, path, *, overwrite):
            calls.append(("SaveAs", Path(path).suffix, overwrite))
            Path(path).write_bytes(b"standalone")
            companion = companion_path(Path(path), "mechdat")
            assert companion is not None
            companion.mkdir()
        def close(self):
            calls.append(("Close",))

    import ansys.mechanical.core

    monkeypatch.setattr(ansys.mechanical.core, "App", App)
    monkeypatch.setattr(
        ansys.mechanical.core,
        "global_variables",
        lambda _app: {key: object() for key in ("Tree", "Model", "DataModel", "Graphics")},
    )
    backend = MechanicalOwnerBackend()
    monkeypatch.setattr(backend, "_execute_native_json", lambda *_args, **_kwargs: _base_snapshot())
    monkeypatch.setattr(backend, "_model_export_semantics", lambda *_args, **_kwargs: _semantics())
    result = backend.convert_workbench_model({
        "format": "mechdat",
        "release_code": 261,
        "bridge_path": str(bridge),
        "bridge_bytes": bridge.stat().st_size,
        "bridge_sha256": hashlib.sha256(bridge.read_bytes()).hexdigest(),
        "stage_path": str(staging.primary),
        "stage_companion": str(staging.companion),
        "verify_path": str(staging.verify_project),
        "model_snapshot_path": str(snapshot_path),
        "model_snapshot_bytes": snapshot_receipt["byte_length"],
        "model_snapshot_sha256": snapshot_receipt["sha256"],
    })
    assert result["status"] == "converted"
    assert calls == [
        ("App", 261),
        ("Open", ".dsdb"),
        ("SaveAs", ".mechdat", False),
        ("Open", ".mechdat"),
        ("Close",),
    ]
    assert backend.app is None

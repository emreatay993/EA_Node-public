# Purpose: Verify Mechanical saved/current camera extraction and exact restoration.
# Map: subsystems/addons.md
# Tests: this file

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from xml.sax.saxutils import quoteattr

import pytest

from ea_node_editor.addons.mechanical.backend import (
    MechanicalOwnerBackend,
    _data_script,
)
from ea_node_editor.addons.mechanical.catalog import MECHANICAL_ADDON_ID
from ea_node_editor.addons.mechanical.contracts import (
    CAMERA_VIEW_TYPE_ID,
    MECHANICAL_DATA_TYPE_FAMILY,
    MECHANICAL_DATA_TYPES,
    model_handle,
)
from ea_node_editor.addons.mechanical.function_nodes import SOURCE
from ea_node_editor.addons.mechanical.graphics import (
    CAMERA_DETAILS_COLUMNS,
    CAMERA_SCRIPT_BODY,
    build_camera_views,
)
from ea_node_editor.addons.mechanical.owner_process import (
    _read_camera_bulk,
    _write_camera_bulk,
)
from ea_node_editor.addons.mechanical.property_edit import MechanicalPropertyEditAdapter
from ea_node_editor.addons.mechanical.runtime import execute_camera_views
from ea_node_editor.addons.mechanical.session import StaleMechanicalModelError
from ea_node_editor.addons.property_edit_adapters import PropertyEditAdapterContext
from ea_node_editor.execution.plugin_worker_runtime import WorkerPluginRuntime
from ea_node_editor.execution.registry_agreement import (
    catalog_agreement,
    runtime_registry_fingerprint,
)
from ea_node_editor.execution.run_messages import StartRunCommand
from ea_node_editor.nodes.bootstrap import build_default_registry
from ea_node_editor.nodes.execution_context import ExecutionContext
from ea_node_editor.nodes.function_plugin import PythonFunctionAdapter
from ea_node_editor.nodes.plugin_declaration import discover_plugin_declarations
from ea_node_editor.runtime_contracts import DataTypeCatalog, TableValue
from ea_node_editor.ui_qml.graph_canvas_state.execution_state_props import (
    _bounded_sample,
)


IDENTITY = {
    "run_id": "run",
    "session_id": "session",
    "document_id": "document",
    "source_key": "sha256:source",
    "system_key": "standalone",
    "model_revision": 0,
}


def _raw_camera(**changes):
    return {
        "kind": "current",
        "name": "Current view",
        "index": None,
        "focal_point": [1.0, 2.0, 3.0],
        "view_vector": [0.0, 0.0, 1.0],
        "up_vector": [0.0, 1.0, 0.0],
        "scene_width": 40.0,
        "scene_height": 30.0,
        "length_unit": "mm",
        "availability_notes": {},
        **changes,
    }


def _model(**metadata_changes):
    metadata = {
        "workspace_id": "workspace",
        **IDENTITY,
        "connection_generation": 0,
        "release_code": 261,
        "backend_mode": "background",
        "catalogue_id": "35ac84bc-7cd6-4b7c-8c4e-43db19709f51",
        "producer_node_id": "open",
        "producer_port": "info",
        "producer_path": [0],
        "producer_iteration": 0,
        **metadata_changes,
    }
    return model_handle(
        handle_id="model",
        owner_scope="run",
        worker_generation=1,
        metadata=metadata,
    )


class _Quantity:
    def __init__(self, value, unit="mm"):
        self.Value, self.Unit = value, unit

    def ConvertUnit(self, unit):
        if unit != self.Unit:
            raise ValueError("unsupported conversion")
        return _Quantity(self.Value, unit)

    def __str__(self):
        return f"{self.Value} [{self.Unit}]"


class _Point:
    def __init__(self, location, unit="mm"):
        self.Location, self.Unit = list(location), unit

    def __str__(self):
        return f"Point({self.Location!r}, {self.Unit!r})"


class _Camera:
    def __init__(self, state):
        self.set_state(state)

    def set_state(self, state):
        focal, view, up, width, height = state
        self.FocalPoint = _Point(focal)
        self.ViewVector = list(view)
        self.UpVector = list(up)
        self.SceneWidth = _Quantity(width)
        self.SceneHeight = _Quantity(height)

    def state(self):
        return (
            tuple(self.FocalPoint.Location),
            tuple(self.ViewVector),
            tuple(self.UpVector),
            self.SceneWidth.Value,
            self.SceneHeight.Value,
        )


class _Object:
    def __init__(self, object_id):
        self.ObjectId = object_id


class _Tree:
    def __init__(self, objects, *, fail_activate=False):
        self.ActiveObjects = [objects[0]]
        self.fail_activate = fail_activate

    def Activate(self, objects):
        if self.fail_activate:
            raise RuntimeError("activation failed")
        self.ActiveObjects = list(objects)


class _DataModel:
    def __init__(self, objects):
        self.objects = {value.ObjectId: value for value in objects}

    def GetObjectById(self, object_id):
        return self.objects[object_id]


class _Manager:
    def __init__(self, camera, tree, views, *, malformed="", apply_error=None):
        self.camera, self.tree = camera, tree
        self.views = [dict(name=name, state=state) for name, state in views]
        self.malformed = malformed
        self.apply_error = apply_error
        self.created = self.deleted = 0

    @property
    def NumberOfViews(self):
        return len(self.views)

    def ExportModelViews(self, path):
        if self.malformed == "root":
            text = "<Unexpected/>"
        elif self.malformed == "nested":
            text = "<ModelViewsManager><Group><ModelView Name='nested'/></Group></ModelViewsManager>"
        elif self.malformed == "unknown_sibling":
            text = "<ModelViewsManager>" + "".join(
                f"<ModelView Name={quoteattr(item['name'])}/>" for item in self.views
            ) + "<Unknown/></ModelViewsManager>"
        else:
            text = "<ModelViewsManager>" + "".join(
                f"<ModelView Name={quoteattr(item['name'])}/>" for item in self.views
            ) + "</ModelViewsManager>"
        Path(path).write_text(text, encoding="utf-8")

    def CreateView(self, name):
        self.views.append({"name": name, "state": self.camera.state()})
        self.created += 1

    def ApplyModelView(self, value):
        item = self.views[value] if type(value) is int else next(
            item for item in self.views if item["name"] == value
        )
        self.camera.set_state(item["state"])
        if type(value) is int:
            self.tree.ActiveObjects = [_Object(2)]
            if self.apply_error is not None:
                error, self.apply_error = self.apply_error, None
                raise error

    def DeleteView(self, name):
        self.views = [item for item in self.views if item["name"] != name]
        self.deleted += 1


def _run_native_script(
    tmp_path,
    views,
    *,
    include="saved_and_current",
    malformed="",
    fail_activate=False,
    apply_error=None,
    empty_focal_unit=False,
    empty_scene_units=False,
    capture_error=False,
):
    initial = ((1.0, 2.0, 3.0), (0.0, 0.0, 1.0), (0.0, 1.0, 0.0), 40.0, 30.0)
    objects = [_Object(1), _Object(2)]
    tree = _Tree(objects, fail_activate=fail_activate)
    camera = _Camera(initial)
    if empty_focal_unit:
        camera.FocalPoint.Unit = ""
    if empty_scene_units:
        camera.SceneWidth.Unit = camera.SceneHeight.Unit = ""
    manager = _Manager(
        camera, tree, views, malformed=malformed, apply_error=apply_error
    )
    namespace = {
        "Graphics": SimpleNamespace(Camera=camera, ModelViewManager=manager),
        "Tree": tree,
        "DataModel": _DataModel(objects),
    }
    script = _data_script(
        {
            "include": include,
            "identity": IDENTITY,
            "export_path": str(tmp_path / "camera-views-test.xml"),
            "restore_name": "COREX restore test",
        },
        CAMERA_SCRIPT_BODY,
    )
    error = None
    try:
        exec(script, namespace)
    except BaseException as exc:
        if not capture_error:
            raise
        error = exc
    payload = (
        json.loads(namespace["_corex_receipt"])
        if "_corex_receipt" in namespace
        else None
    )
    return payload, camera, tree, manager, initial, error


def test_generated_script_preserves_duplicate_unicode_names_and_restores_state(tmp_path):
    payload, camera, tree, manager, initial, error = _run_native_script(
        tmp_path,
        [
            ("Vue, α", ((4, 5, 6), (1, 0, 0), (0, 0, 1), 20, 10)),
            ("Vue, α", ((7, 8, 9), (0, 1, 0), (1, 0, 0), 25, 15)),
        ],
    )
    assert error is None
    assert [(row["name"], row["index"]) for row in payload["views"]] == [
        ("Vue, α", 0),
        ("Vue, α", 1),
        ("Current view", None),
    ]
    assert camera.state() == initial
    assert [value.ObjectId for value in tree.ActiveObjects] == [1]
    assert manager.NumberOfViews == 2
    assert (manager.created, manager.deleted) == (1, 1)


def test_zero_saved_views_returns_current_without_creating_a_restore_view(tmp_path):
    payload, camera, tree, manager, initial, error = _run_native_script(tmp_path, [])
    assert error is None
    assert [(row["kind"], row["name"]) for row in payload["views"]] == [
        ("current", "Current view")
    ]
    assert camera.state() == initial
    assert [value.ObjectId for value in tree.ActiveObjects] == [1]
    assert manager.NumberOfViews == 0
    assert (manager.created, manager.deleted) == (0, 0)


@pytest.mark.parametrize("malformed", ("root", "nested", "unknown_sibling"))
def test_generated_script_rejects_malformed_exported_schema(tmp_path, malformed):
    with pytest.raises(ValueError, match="mechanical.camera_schema_invalid"):
        _run_native_script(
            tmp_path,
            [("View", ((4, 5, 6), (1, 0, 0), (0, 1, 0), 20, 10))],
            malformed=malformed,
        )


def test_generated_script_reports_restore_failure(tmp_path):
    with pytest.raises(ValueError, match="mechanical.restore_failed"):
        _run_native_script(
            tmp_path,
            [("View", ((4, 5, 6), (1, 0, 0), (0, 1, 0), 20, 10))],
            fail_activate=True,
        )


@pytest.mark.parametrize("error", (RuntimeError("apply failed"), KeyboardInterrupt("cancelled")))
def test_operation_error_or_cancel_restores_before_propagating(tmp_path, error):
    payload, camera, tree, manager, initial, raised = _run_native_script(
        tmp_path,
        [("View", ((4, 5, 6), (1, 0, 0), (0, 1, 0), 20, 10))],
        apply_error=error,
        capture_error=True,
    )
    assert payload is None
    assert type(raised) is type(error)
    assert str(raised) == str(error)
    assert camera.state() == initial
    assert [value.ObjectId for value in tree.ActiveObjects] == [1]
    assert manager.NumberOfViews == 1
    assert (manager.created, manager.deleted) == (1, 1)


def test_current_focal_point_without_its_unit_is_nullable_not_relabeled(tmp_path):
    payload, _camera, _tree, manager, _initial, error = _run_native_script(
        tmp_path,
        [],
        include="current",
        empty_focal_unit=True,
    )
    assert error is None
    current = payload["views"][0]
    assert current["focal_point"] is None
    assert current["length_unit"] == "mm"
    assert current["availability_notes"]["focal_point"] == (
        "focal-point unit is unavailable"
    )
    assert manager.NumberOfViews == 0


def test_scene_dimensions_without_units_are_nullable(tmp_path):
    payload, _camera, _tree, _manager, _initial, error = _run_native_script(
        tmp_path,
        [],
        include="current",
        empty_focal_unit=True,
        empty_scene_units=True,
    )
    assert error is None
    current = payload["views"][0]
    assert current["focal_point"] is None
    assert current["scene_width"] is None
    assert current["scene_height"] is None
    assert current["length_unit"] is None
    assert set(current["availability_notes"]) == {
        "focal_point",
        "scene_width",
        "scene_height",
        "length_unit",
    }


def test_generated_camera_script_stays_ironpython_math_compatible():
    assert "math.isfinite" not in CAMERA_SCRIPT_BODY


def test_build_camera_views_keeps_nullable_fields_and_meaningful_details():
    result = build_camera_views(
        {
            "views": [
                _raw_camera(
                    focal_point=None,
                    availability_notes={"focal_point": "Location unavailable"},
                ),
                _raw_camera(kind="saved", name="Front, α", index=0),
            ]
        },
        identity=IDENTITY,
    )
    assert result["names"] == ["Current view", "Front, α"]
    assert [value.data_type_id for value in result["views"]] == [
        CAMERA_VIEW_TYPE_ID,
        CAMERA_VIEW_TYPE_ID,
    ]
    frame = result["details"].to_pandas()
    assert tuple(frame.columns) == CAMERA_DETAILS_COLUMNS
    assert frame.loc[0, "availability_notes"] == '{"focal_point":"Location unavailable"}'
    assert frame.loc[1, "saved_index"] == 0
    assert frame.loc[1, "focal_x"] == 1.0


def test_camera_result_uses_the_existing_typed_value_spool(tmp_path):
    result = build_camera_views(
        {"views": [_raw_camera()]}, identity=IDENTITY
    )
    descriptor = _write_camera_bulk(tmp_path, result, IDENTITY)
    restored = _read_camera_bulk(tmp_path, descriptor, IDENTITY)
    assert restored["names"] == ["Current view"]
    assert restored["details"].column_names == CAMERA_DETAILS_COLUMNS
    assert not list(tmp_path.glob("camera-views-result-*.json"))


def test_restore_failure_retires_the_native_backend(tmp_path):
    backend = MechanicalOwnerBackend()
    backend.work_root = tmp_path

    class App:
        def execute_script(self, _script):
            raise RuntimeError("mechanical.restore_failed: injected verification failure")

    backend.app = App()
    retired = []
    backend.close = lambda: retired.append(True)
    with pytest.raises(RuntimeError, match="mechanical.restore_failed"):
        backend.execute(
            "camera_views",
            {
                "include": "saved",
                "identity": IDENTITY,
                "export_path": str(tmp_path / "camera-views-test.xml"),
                "restore_name": "COREX restore test",
            },
        )
    assert retired == [True]


class _Sessions:
    def __init__(self, *, response_identity=IDENTITY, stale=False):
        self.response_identity = response_identity
        self.stale = stale
        self.operated = None

    def admit_model(self, _value, **_kwargs):
        if self.stale:
            raise StaleMechanicalModelError("expired")
        return SimpleNamespace(work_root=Path.cwd())

    def operate(self, _session, **kwargs):
        self.operated = kwargs
        return {
            "camera_views": build_camera_views(
                {"views": [_raw_camera()]}, identity=self.response_identity
            )
        }


def test_runtime_rejects_stale_and_cross_session_camera_results():
    context = SimpleNamespace(
        run_id="run",
        workspace_id="workspace",
        inputs={},
        properties={"include": "current"},
        mechanical_sessions=_Sessions(stale=True),
    )
    with pytest.raises(ValueError, match="mechanical.stale_reference"):
        execute_camera_views(context, _model())
    context.mechanical_sessions = _Sessions(
        response_identity={**IDENTITY, "session_id": "other"}
    )
    with pytest.raises(ValueError, match="mechanical.cross_session_reference"):
        execute_camera_views(context, _model())


def test_registered_declaration_forwards_connected_include_and_loads_in_worker(tmp_path):
    declarations = discover_plugin_declarations(
        SOURCE,
        filename="mechanical_nodes.py",
        allow_reserved_ids=True,
        owner_id=MECHANICAL_ADDON_ID,
        allow_internal_metadata=True,
    )
    declaration = next(
        item for item in declarations if item.spec.type_id == "mechanical.camera_views"
    )
    assert declaration.spec.solution_reuse_scope == "never"
    assert [(port.key, port.data_type, port.data_access) for port in declaration.spec.ports] == [
        ("model", "COREX.Mechanical.Model", "item"),
        ("include", "COREX.DataTypes.String", "item"),
        ("views", "COREX.Mechanical.CameraView", "list"),
        ("names", "COREX.DataTypes.String", "list"),
        ("details", "COREX.DataTypes.TableValue", "item"),
    ]
    namespace = {}
    exec(SOURCE, namespace)
    sessions = _Sessions()
    context = ExecutionContext(
        run_id="run",
        node_id="camera",
        workspace_id="workspace",
        inputs={"model": _model(), "include": "current"},
        properties={"include": "saved"},
        emit_log=lambda *_: None,
        worker_services=SimpleNamespace(mechanical_session_service=sessions),
    )
    outputs = PythonFunctionAdapter(
        declaration.spec, namespace["mechanical_camera_views"]
    ).execute(context).outputs
    assert outputs["names"] == ["Current view"]
    assert sessions.operated["args"]["include"] == "current"

    registry = build_default_registry(
        include_public_plugins=False,
        addon_runtime_config=((MECHANICAL_ADDON_ID, True),),
        generation_root=tmp_path / "generations",
    )
    fingerprint, revisions = catalog_agreement(registry.data_types)
    plugin_digest = registry.plugin_fingerprint()
    command = StartRunCommand(
        run_id="run",
        workspace_id="workspace",
        runtime_snapshot=None,
        catalog_fingerprint=fingerprint,
        catalog_revisions=revisions,
        plugin_bundles=registry.plugin_bundle_refs(),
        plugin_fingerprint=plugin_digest,
        runtime_registry_fingerprint=runtime_registry_fingerprint(
            fingerprint, plugin_digest
        ),
        registry_contract_fingerprint=registry.contract_fingerprint(),
        addon_runtime_config=registry.addon_runtime_config(),
    )
    runtime = WorkerPluginRuntime()
    prepared = runtime.prepare_registry(command, registry)
    ref = prepared.python_function_ref_or_none("mechanical.camera_views")
    assert ref is not None
    assert runtime.create_adapter(ref, prepared.get_spec("mechanical.camera_views"))
    runtime.clear()


def test_include_labels_and_panel_use_shared_presentation_paths():
    items = MechanicalPropertyEditAdapter().build_property_items(
        PropertyEditAdapterContext(
            node=SimpleNamespace(
                node_id="camera", type_id="mechanical.camera_views", properties={}
            )
        ),
        [{"key": "include"}],
    )
    assert items[0]["enum_values"] == [
        "Saved views + current view",
        "Saved views",
        "Current view",
    ]
    value = build_camera_views(
        {"views": [_raw_camera(kind="saved", name="Front, α", index=3)]},
        identity=IDENTITY,
    )["views"][0]
    catalog = DataTypeCatalog()
    catalog.register_many(
        families=(MECHANICAL_DATA_TYPE_FAMILY,),
        types=MECHANICAL_DATA_TYPES,
        owner_id="mechanical.corex",
        owner_version="1",
        source_label="test",
    )
    assert _bounded_sample(value, data_types=catalog) == (
        "Mechanical Camera View: Front, α (saved index 3)"
    )

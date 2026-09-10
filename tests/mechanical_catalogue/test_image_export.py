# Purpose: Verify deterministic Mechanical viewport image batches and safe publication.
# Map: subsystems/addons.md
# Tests: this file

from __future__ import annotations

import os
import hashlib
import struct
import zlib
from pathlib import Path
from types import SimpleNamespace

import pytest

from ea_node_editor.addons.mechanical.backend import MechanicalOwnerBackend
from ea_node_editor.addons.mechanical.catalog import MECHANICAL_ADDON_ID
from ea_node_editor.addons.mechanical.contracts import (
    camera_view_value,
    encode_selector,
    model_handle,
    object_value,
)
from ea_node_editor.addons.mechanical.function_nodes import SOURCE
from ea_node_editor.addons.mechanical.graphics import (
    IMAGE_DETAILS_COLUMNS,
    preflight_image_destinations,
    publish_image_batch,
    render_image_filenames,
)
from ea_node_editor.addons.mechanical.owner_process import _read_image_export
from ea_node_editor.addons.mechanical.runtime import execute_image_export
from ea_node_editor.execution.plugin_worker_runtime import WorkerPluginRuntime
from ea_node_editor.execution.registry_agreement import (
    catalog_agreement,
    runtime_registry_fingerprint,
)
from ea_node_editor.execution.run_messages import StartRunCommand
from ea_node_editor.graph.effective_ports import ports_compatible
from ea_node_editor.nodes.bootstrap import build_default_registry
from ea_node_editor.nodes.execution_context import ExecutionContext
from ea_node_editor.nodes.function_plugin import PythonFunctionAdapter
from ea_node_editor.nodes.plugin_declaration import discover_plugin_declarations
from ea_node_editor.runtime_contracts import DataTree, ImageValue
from tests.mechanical_catalogue.test_contracts import (
    _camera_payload,
    _model_metadata,
    _object_payload,
)


def _chunk(kind: bytes, payload: bytes) -> bytes:
    return (
        struct.pack(">I", len(payload))
        + kind
        + payload
        + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)
    )


def _png(width: int = 64, height: int = 64) -> bytes:
    raster = b"".join(b"\0" + b"\xff\xff\xff\xff" * width for _ in range(height))
    return (
        b"\x89PNG\r\n\x1a\n"
        + _chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
        + _chunk(b"IDAT", zlib.compress(raster))
        + _chunk(b"IEND", b"")
    )


def _model():
    return model_handle(
        handle_id="model",
        owner_scope="run-1",
        worker_generation=1,
        metadata=_model_metadata(),
    )


def _object(object_id: int, name: str):
    return object_value(
        _object_payload(
            object_id=object_id,
            object_path=f"Model/{name}",
            display_name=name,
            selector_code=encode_selector(
                "object",
                document_id="document-1",
                system_key="system-1",
                object_path=f"Model/{name}",
                native_id=object_id,
            ),
        )
    )


def _view(index: int, name: str):
    return camera_view_value(
        _camera_payload(
            index=index,
            name=name,
            selector_code=encode_selector(
                "camera_view",
                document_id="document-1",
                system_key="system-1",
                object_path="",
                native_id=index,
            ),
        )
    )


class _Sessions:
    def __init__(self, work_root: Path):
        self.work_root = work_root
        self.calls = []

    def admit_model(self, _model, **_kwargs):
        return SimpleNamespace(work_root=self.work_root)

    def operate(self, _session, **kwargs):
        self.calls.append(kwargs)
        args = kwargs["args"]
        image = ImageValue.from_png(_png(args["width"], args["height"]))
        records = []
        for object_index, obj in enumerate(args["objects"]):
            for view_ordinal, view in enumerate(args["views"]):
                records.append(
                    {
                        "object_index": object_index,
                        "object_name": "Current display" if obj["kind"] == "current" else f"Object {object_index}",
                        "object_path": "" if obj["kind"] == "current" else obj.get("object_path", ""),
                        "object_id": None if obj["kind"] == "current" else obj.get("object_id"),
                        "view_ordinal": view_ordinal,
                        "view_name": "Current view" if view["kind"] == "current" else (view.get("name") or f"View {view['index']}"),
                        "view_kind": "current" if view["kind"] == "current" else "saved",
                        "view_index": None if view["kind"] == "current" else view["index"],
                        **({} if args["preflight_only"] else {"image": image}),
                    }
                )
        if args["preflight_only"]:
            return {"status": "validated", "image_preflight": {"images": records}}
        return {"status": "captured", "image_export": {"images": records}}


def _context(tmp_path: Path, sessions: _Sessions, **changes):
    values = dict(
        run_id="run-1",
        node_id="image",
        workspace_id="workspace-1",
        inputs={},
        properties={
            "objects": [],
            "views": [],
            "width": 64,
            "height": 64,
            "background": "white",
            "fit_view": False,
            "folder": "",
            "file_name": "{object}_{view}.png",
            "overwrite": False,
        },
        emit_log=lambda *_: None,
        path_resolver=lambda value: Path(value),
        worker_services=SimpleNamespace(mechanical_session_service=sessions),
        target_path=(4, 2),
        target_iteration=3,
    )
    values.update(changes)
    return ExecutionContext(**values)


def test_registered_declaration_is_typed_and_loads_in_worker(tmp_path):
    declarations = discover_plugin_declarations(
        SOURCE,
        filename="mechanical_nodes.py",
        allow_reserved_ids=True,
        owner_id=MECHANICAL_ADDON_ID,
        allow_internal_metadata=True,
    )
    declaration = next(item for item in declarations if item.spec.type_id == "mechanical.export_image")
    ports = {port.key: port for port in declaration.spec.ports}
    assert declaration.spec.solution_reuse_scope == "never"
    assert (ports["model"].data_access, ports["objects"].data_access, ports["views"].data_access) == ("list", "list", "list")
    assert ports["objects"].accepted_data_types == ("COREX.DataTypes.String",)
    assert ports["views"].accepted_data_types == ("COREX.DataTypes.String",)
    assert ports["images"].data_access == "tree"
    assert all(port.exposed for port in ports.values())

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
        runtime_registry_fingerprint=runtime_registry_fingerprint(fingerprint, plugin_digest),
        registry_contract_fingerprint=registry.contract_fingerprint(),
        addon_runtime_config=registry.addon_runtime_config(),
    )
    runtime = WorkerPluginRuntime()
    prepared = runtime.prepare_registry(command, registry)
    ref = prepared.python_function_ref_or_none("mechanical.export_image")
    assert ref is not None
    assert runtime.create_adapter(ref, prepared.get_spec("mechanical.export_image"))
    runtime.clear()


def test_registered_images_and_files_connect_to_media_panel_and_path_tools(tmp_path):
    registry = build_default_registry(
        include_public_plugins=False,
        addon_runtime_config=((MECHANICAL_ADDON_ID, True),),
        generation_root=tmp_path / "generations",
    )
    image = registry.get_spec("mechanical.export_image")
    media = registry.get_spec("media.panel")
    path_tool = registry.get_spec("io.deconstruct_file_path")
    by_key = lambda spec, key: next(port for port in spec.ports if port.key == key)
    assert ports_compatible(
        by_key(image, "images"), by_key(media, "source"), data_types=registry.data_types
    )
    assert ports_compatible(
        by_key(image, "files"), by_key(path_tool, "file_path"), data_types=registry.data_types
    )


def test_runtime_two_by_three_preserves_branch_and_invocation(tmp_path):
    sessions = _Sessions(tmp_path)
    context = _context(tmp_path, sessions)
    result = execute_image_export(
        context,
        [_model()],
        [_object(10, "Part, A"), _object(11, "Part B")],
        [_view(0, "Front"), _view(1, "Side, detail"), _view(2, "Iso")],
        SimpleNamespace(**context.properties),
    )
    assert result["images"].paths == ((4, 2, 3, 0), (4, 2, 3, 1))
    assert [len(items) for _path, items in result["images"].branches] == [3, 3]
    assert result["files"] == []
    frame = result["details"].to_pandas()
    assert tuple(frame.columns) == IMAGE_DETAILS_COLUMNS
    assert frame["data_path"].tolist() == ["[4,2,3,0]"] * 3 + ["[4,2,3,1]"] * 3
    assert frame["image_ordinal"].tolist() == list(range(6))
    assert sessions.calls[-1]["args"]["fit_view"] is False


def test_separate_grafted_model_invocations_cannot_merge_equal_paths(tmp_path):
    sessions = _Sessions(tmp_path)
    settings = SimpleNamespace(**_context(tmp_path, sessions).properties)
    first = execute_image_export(
        _context(tmp_path, sessions, target_path=(7,), target_iteration=0),
        [_model()],
        [],
        [],
        settings,
    )["images"]
    second = execute_image_export(
        _context(tmp_path, sessions, target_path=(7,), target_iteration=1),
        [_model()],
        [],
        [],
        settings,
    )["images"]
    assert first.merge(second).paths == ((7, 0, 0), (7, 1, 0))


def test_registered_function_passes_connected_list_settings(tmp_path):
    declaration = next(
        item
        for item in discover_plugin_declarations(
            SOURCE,
            filename="mechanical_nodes.py",
            allow_reserved_ids=True,
            owner_id=MECHANICAL_ADDON_ID,
            allow_internal_metadata=True,
        )
        if item.spec.type_id == "mechanical.export_image"
    )
    namespace = {}
    exec(SOURCE, namespace)
    sessions = _Sessions(tmp_path)
    context = _context(
        tmp_path,
        sessions,
        inputs={"model": [_model()], "objects": ["Model/Load"], "views": ["Current view"], "width": 65},
    )
    outputs = PythonFunctionAdapter(declaration.spec, namespace["export_mechanical_image"]).execute(context).outputs
    assert outputs["images"].item_count == 1
    assert sessions.calls[-1]["args"]["width"] == 65
    assert sessions.calls[-1]["args"]["objects"] == [{"kind": "text", "text": "Model/Load"}]


def test_current_picker_identity_and_blank_folder_ignore_disk_controls(tmp_path):
    sessions = _Sessions(tmp_path)
    current_selector = encode_selector(
        "view",
        document_id="document-1",
        system_key="system-1",
        object_path="",
        native_id="current",
    )
    context = _context(tmp_path, sessions)
    settings = SimpleNamespace(
        **{
            **context.properties,
            "file_name": "{unsupported}.jpg",
            "overwrite": "inactive invalid value",
        }
    )
    result = execute_image_export(context, [_model()], [], [current_selector], settings)
    assert result["images"].item_count == 1
    assert result["files"] == []
    assert sessions.calls[-1]["args"]["views"] == [{"kind": "current"}]


def test_multiple_models_and_limits_fail_before_native_capture(tmp_path):
    sessions = _Sessions(tmp_path)
    context = _context(tmp_path, sessions)
    with pytest.raises(ValueError, match="exactly one Model.*Graft"):
        execute_image_export(context, [_model(), _model()], [], [], SimpleNamespace(**context.properties))
    assert sessions.calls == []
    with pytest.raises(ValueError, match="requested 272 image captures"):
        execute_image_export(context, [_model()], ["x"] * 17, ["y"] * 16, SimpleNamespace(**context.properties))
    with pytest.raises(ValueError, match="maximum is 33554432"):
        execute_image_export(context, [_model()], [], [], SimpleNamespace(**{**context.properties, "width": 8192, "height": 8192}))
    assert sessions.calls == []


def test_filename_tokens_are_sanitized_and_collisions_or_escape_fail(tmp_path):
    assert render_image_filenames("{object}_{view}.png", [("A/B", "V:1")], view_count=1) == ["A_B_V_1.png"]
    with pytest.raises(ValueError, match="duplicate destinations"):
        render_image_filenames("same.png", [("A", "V1"), ("A", "V2")], view_count=2)
    with pytest.raises(ValueError, match="local .png"):
        render_image_filenames("../{object}.png", [("A", "V")], view_count=1)
    with pytest.raises(ValueError, match="supports only"):
        render_image_filenames("{object.__class__}.png", [("A", "V")], view_count=1)
    with pytest.raises(ValueError, match="local .png"):
        render_image_filenames("CON.png", [("A", "V")], view_count=1)

    outside = tmp_path / "outside"
    outside.mkdir()
    folder = tmp_path / "output"
    destinations = preflight_image_destinations(folder, ["a.png"], overwrite=False)
    assert destinations == [folder / "a.png"]
    (folder).mkdir()
    (folder / "a.png").write_bytes(b"old")
    with pytest.raises(FileExistsError):
        preflight_image_destinations(folder, ["a.png"], overwrite=False)


def test_publication_is_all_or_rollback(monkeypatch, tmp_path):
    folder = tmp_path / "output"
    folder.mkdir()
    destinations = [folder / "a.png", folder / "b.png"]
    destinations[0].write_bytes(b"old-a")
    destinations[1].write_bytes(b"old-b")
    images = [ImageValue.from_png(_png()), ImageValue.from_png(_png())]
    real_link = os.link

    def fail_second_publish(source, destination):
        if Path(destination) == destinations[1] and Path(source).parent.name == "staged":
            raise OSError("injected publish failure")
        return real_link(source, destination)

    monkeypatch.setattr(os, "link", fail_second_publish)
    with pytest.raises(OSError, match="injected publish failure"):
        publish_image_batch(images, destinations, overwrite=True)
    assert destinations[0].read_bytes() == b"old-a"
    assert destinations[1].read_bytes() == b"old-b"
    assert not list(folder.glob(".corex-image-batch-*"))


def test_publication_preserves_concurrent_replacement_and_backup(monkeypatch, tmp_path):
    folder = tmp_path / "output"
    folder.mkdir()
    destinations = [folder / "a.png", folder / "b.png"]
    destinations[0].write_bytes(b"old-a")
    destinations[1].write_bytes(b"old-b")
    images = [ImageValue.from_png(_png()), ImageValue.from_png(_png())]
    real_link = os.link

    def link_then_race(source, destination):
        source_path, destination_path = Path(source), Path(destination)
        if destination_path == destinations[1] and source_path.parent.name == "staged":
            raise OSError("injected later failure")
        result = real_link(source, destination)
        if destination_path == destinations[0] and source_path.parent.name == "staged":
            destination_path.write_bytes(b"new-user-data")
        return result

    monkeypatch.setattr(os, "link", link_then_race)
    with pytest.raises(RuntimeError, match="publication_recovery_required") as raised:
        publish_image_batch(images, destinations, overwrite=True)
    assert destinations[0].read_bytes() == b"new-user-data"
    recovery = Path(str(raised.value).split(": ", 1)[1].split(";", 1)[0])
    assert recovery.is_dir()
    assert [path.read_bytes() for path in (recovery / "backups").glob("*.png")] == [b"old-a"]


class _NativeObject:
    def __init__(self, object_id, name, parent=None, events=None, result=False, api_type=None):
        self.ObjectId, self.Name, self.Parent = object_id, name, parent
        self.Hidden = False
        self.events = events if events is not None else []
        self.api_type = api_type
        if result:
            self.RetrieveResult = lambda: self.events.append(("evaluate", self.Name))

    def GetType(self):
        return SimpleNamespace(FullName=self.api_type or ("Ansys.Mechanical.ProbeResults.ForceReaction" if hasattr(self, "RetrieveResult") else "Ansys.Mechanical.Body"))


class _Camera:
    def __init__(self, events):
        self.events = events
        self.FocalPoint, self.ViewVector, self.UpVector = "focal", "view", "up"
        self.SceneWidth, self.SceneHeight = "width", "height"

    def SetFit(self):
        self.events.append(("fit",))


class _Tree:
    def __init__(self, objects, events):
        self.AllObjects = list(objects)
        self.ActiveObjects = [objects[0]]
        self.events = events

    def Activate(self, objects):
        self.ActiveObjects = list(objects)
        self.events.append(("activate", objects[0].Name if objects else ""))


class _ViewManager:
    def __init__(self, camera, tree, events):
        self.camera, self.tree, self.events = camera, tree, events
        self.views = ["Front", "Side", "Iso"]

    @property
    def NumberOfViews(self):
        return len(self.views)

    def ExportModelViews(self, path):
        Path(path).write_text("<ModelViewsManager>" + "".join(f'<ModelView Name="{name}"/>' for name in self.views) + "</ModelViewsManager>", encoding="utf-8")

    def CreateView(self, name):
        self.views.append(name)

    def ApplyModelView(self, value):
        name = self.views[value] if type(value) is int else value
        self.events.append(("view", name))

    def DeleteView(self, name):
        self.views.remove(name)


def test_native_script_captures_object_major_after_activation_and_restores(tmp_path):
    events = []
    root = _NativeObject(1, "Model", events=events)
    first = _NativeObject(10, "Result, A", root, events, result=True)
    first.By = "Time"
    first.DisplayTime = "1 [s]"
    second = _NativeObject(11, "Body B", root, events)
    objects = [root, first, second]
    camera = _Camera(events)
    tree = _Tree(objects, events)
    manager = _ViewManager(camera, tree, events)

    class Settings:
        pass

    class Graphics:
        Camera = camera
        ModelViewManager = manager

        @staticmethod
        def ExportImage(path, _format, settings):
            events.append(("export", tree.ActiveObjects[0].Name, manager.events[-1][1], settings.Width, settings.Height, settings.Background))
            Path(path).write_bytes(_png(settings.Width, settings.Height))

    backend = MechanicalOwnerBackend()
    backend.work_root = tmp_path.resolve()
    backend.app = SimpleNamespace()
    backend.app.execute_script = lambda script: _exec_native(script, Graphics, tree, objects, Settings)
    paths = [tmp_path / f"viewport-{index}.png" for index in range(6)]
    result = backend.image_export(
        {
            "objects": [
                {"kind": "typed", "object_id": 10, "object_path": "Model/Result, A"},
                {"kind": "typed", "object_id": 11, "object_path": "Model/Body B"},
            ],
            "views": [
                {"kind": "text", "text": "Front"},
                {"kind": "text", "text": "Side"},
                {"kind": "text", "text": "Iso"},
            ],
            "width": 64,
            "height": 64,
            "background": "white",
            "fit_view": False,
            "output_paths": [str(path) for path in paths],
            "view_export_path": str(tmp_path / "image-views-test.xml"),
            "restore_name": "COREX restore test",
            "preflight_only": False,
        }
    )
    restored = _read_image_export(tmp_path, result["image_export"])
    assert len(restored["images"]) == 6
    assert all(type(record["image"]) is ImageValue for record in restored["images"])
    exports = [event for event in events if event[0] == "export"]
    assert [(event[1], event[2]) for event in exports] == [
        ("Result, A", "Front"), ("Result, A", "Side"), ("Result, A", "Iso"),
        ("Body B", "Front"), ("Body B", "Side"), ("Body B", "Iso"),
    ]
    first_activation = events.index(("activate", "Result, A"))
    assert first_activation < events.index(("evaluate", "Result, A")) < events.index(("view", "Front"))
    assert not any(event[0] == "fit" for event in events)
    assert [item.ObjectId for item in tree.ActiveObjects] == [1]
    assert manager.views == ["Front", "Side", "Iso"]
    assert not list(tmp_path.glob("viewport-*.png"))


def _exec_native(script, graphics, tree, objects, settings_type):
    namespace = {
        "Graphics": graphics,
        "Tree": tree,
        "DataModel": SimpleNamespace(GetObjectById=lambda object_id: next(item for item in objects if item.ObjectId == object_id)),
        "Ansys": SimpleNamespace(
            Mechanical=SimpleNamespace(
                Graphics=SimpleNamespace(GraphicsImageExportSettings=settings_type),
                DataModel=SimpleNamespace(
                    Enums=SimpleNamespace(
                        GraphicsBackgroundType=SimpleNamespace(White="white", GraphicsAppearanceSetting="model"),
                        GraphicsCaptureType=SimpleNamespace(ImageOnly="image_only"),
                        GraphicsImageExportFormat=SimpleNamespace(PNG="png"),
                    )
                ),
            )
        ),
    }
    exec(compile(script, "<mechanical-image-script>", "exec"), namespace)
    return namespace["_corex_receipt"]


def test_missing_or_ambiguous_native_selector_fails_before_export(tmp_path):
    events = []
    root = _NativeObject(1, "Model", events=events)
    duplicate_a = _NativeObject(10, "Duplicate", root, events)
    duplicate_b = _NativeObject(11, "Duplicate", root, events)
    objects = [root, duplicate_a, duplicate_b]
    camera = _Camera(events)
    tree = _Tree(objects, events)
    manager = _ViewManager(camera, tree, events)

    class Settings:
        pass

    class Graphics:
        Camera = camera
        ModelViewManager = manager

        @staticmethod
        def ExportImage(*_args):
            events.append(("export",))

    backend = MechanicalOwnerBackend()
    backend.work_root = tmp_path.resolve()
    backend.app = SimpleNamespace(execute_script=lambda script: _exec_native(script, Graphics, tree, objects, Settings))
    args = {
        "objects": [{"kind": "text", "text": "Duplicate"}],
        "views": [{"kind": "text", "text": "Front"}],
        "width": 64,
        "height": 64,
        "background": "white",
        "fit_view": False,
        "output_paths": [str(tmp_path / "viewport-one.png")],
        "view_export_path": str(tmp_path / "image-views-one.xml"),
        "restore_name": "COREX restore test",
        "preflight_only": False,
    }
    with pytest.raises(ValueError, match="mechanical.selector_ambiguous"):
        backend.image_export(args)
    assert not any(event[0] == "export" for event in events)


def test_unreadable_visibility_fails_before_capture(tmp_path):
    events = []

    class UnreadableHidden(_NativeObject):
        @property
        def Hidden(self):
            raise RuntimeError("hidden getter failed")

        @Hidden.setter
        def Hidden(self, _value):
            pass

    root = _NativeObject(1, "Model", events=events)
    broken = UnreadableHidden(10, "Broken", root, events)
    objects = [root, broken]
    camera = _Camera(events)
    tree = _Tree(objects, events)
    manager = _ViewManager(camera, tree, events)

    class Settings:
        pass

    class Graphics:
        Camera = camera
        ModelViewManager = manager

        @staticmethod
        def ExportImage(*_args):
            events.append(("export",))

    backend = MechanicalOwnerBackend()
    backend.work_root = tmp_path.resolve()
    backend.app = SimpleNamespace(execute_script=lambda script: _exec_native(script, Graphics, tree, objects, Settings))
    with pytest.raises(ValueError, match="mechanical.capability_unproved: object visibility is unreadable"):
        backend.image_export(
            {
                "objects": [{"kind": "current"}],
                "views": [{"kind": "current"}],
                "width": 64,
                "height": 64,
                "background": "white",
                "fit_view": False,
                "output_paths": [str(tmp_path / "viewport-one.png")],
                "view_export_path": str(tmp_path / "image-views-one.xml"),
                "restore_name": "COREX restore test",
                "preflight_only": False,
            }
        )
    assert not any(event[0] == "export" for event in events)


def test_capture_failure_removes_temporary_images_and_restore_failure_retires(tmp_path):
    backend = MechanicalOwnerBackend()
    backend.work_root = tmp_path.resolve()
    paths = [tmp_path / "viewport-a.png", tmp_path / "viewport-b.png"]

    def fail_after_first(_script):
        paths[0].write_bytes(_png())
        raise RuntimeError("capture failed")

    backend.app = SimpleNamespace(execute_script=fail_after_first)
    args = {
        "objects": [{"kind": "current"}],
        "views": [{"kind": "current"}, {"kind": "current"}],
        "width": 64,
        "height": 64,
        "background": "white",
        "fit_view": False,
        "output_paths": [str(path) for path in paths],
        "view_export_path": str(tmp_path / "image-views-failure.xml"),
        "restore_name": "COREX restore test",
        "preflight_only": False,
    }
    with pytest.raises(RuntimeError, match="capture failed"):
        backend.image_export(args)
    assert not any(path.exists() for path in paths)

    retired = []
    backend.app = SimpleNamespace(execute_script=lambda _script: (_ for _ in ()).throw(RuntimeError("mechanical.restore_failed: injected")))
    backend.close = lambda: retired.append(True)
    with pytest.raises(RuntimeError, match="mechanical.restore_failed"):
        backend.image_export(args)
    assert retired == [True]


def test_configured_result_keeps_the_approved_inactive_zero_restore_exception(tmp_path):
    events = []

    class Reader:
        ListTimeFreq = [1.0, 2.0, 3.0]

        def Dispose(self):
            pass

    class Analysis(_NativeObject):
        def GetResultsData(self):
            return Reader()

    class ConfiguredResult(_NativeObject):
        def __init__(self, parent):
            super().__init__(
                10,
                "Configured result",
                parent,
                events,
                api_type="Ansys.Mechanical.Results.DeformationResults.TotalDeformation",
            )
            self.By = "Time"
            self.DisplayTime = "0 [s]"
            self.CalculateTimeHistory = True
            self._set_number = 0
            self.RetrieveResult = self.retrieve

        @property
        def SetNumber(self):
            return self._set_number

        @SetNumber.setter
        def SetNumber(self, value):
            if value == 0:
                raise ValueError("zero is inactive")
            self._set_number = int(value)

        def retrieve(self):
            events.append(("evaluate", self.Name))
            self._set_number = 3

    analysis = Analysis(1, "Analysis", events=events)
    result_object = ConfiguredResult(analysis)
    objects = [analysis, result_object]
    camera = _Camera(events)
    tree = _Tree(objects, events)
    manager = _ViewManager(camera, tree, events)

    class Settings:
        pass

    class Graphics:
        Camera = camera
        ModelViewManager = manager

        @staticmethod
        def ExportImage(path, _format, settings):
            Path(path).write_bytes(_png(settings.Width, settings.Height))

    backend = MechanicalOwnerBackend()
    backend.work_root = tmp_path.resolve()
    backend.app = SimpleNamespace(execute_script=lambda script: _exec_native(script, Graphics, tree, objects, Settings))
    path = tmp_path / "viewport-configured.png"
    response = backend.image_export(
        {
            "objects": [{"kind": "typed", "object_id": 10, "object_path": "Analysis/Configured result"}],
            "views": [{"kind": "current"}],
            "width": 64,
            "height": 64,
            "background": "model",
            "fit_view": False,
            "output_paths": [str(path)],
            "view_export_path": str(tmp_path / "image-views-configured.xml"),
            "restore_name": "COREX restore configured",
            "preflight_only": False,
        }
    )
    _read_image_export(tmp_path, response["image_export"], (64, 64))
    assert response["warnings"] and "before=0; after=3" in response["warnings"][0]
    assert (result_object.By, result_object.DisplayTime, result_object.CalculateTimeHistory, result_object.SetNumber) == ("Time", "0 [s]", True, 3)


def test_force_reaction_requires_already_time_before_export(tmp_path):
    events = []
    root = _NativeObject(1, "Model", events=events)
    force = _NativeObject(10, "Reaction", root, events, result=True)
    force.By = "ResultSet"
    force.DisplayTime = "1 [s]"
    objects = [root, force]
    camera = _Camera(events)
    tree = _Tree(objects, events)
    manager = _ViewManager(camera, tree, events)

    class Settings:
        pass

    class Graphics:
        Camera = camera
        ModelViewManager = manager

        @staticmethod
        def ExportImage(*_args):
            events.append(("export",))

    backend = MechanicalOwnerBackend()
    backend.work_root = tmp_path.resolve()
    backend.app = SimpleNamespace(execute_script=lambda script: _exec_native(script, Graphics, tree, objects, Settings))
    with pytest.raises(ValueError, match="ForceReaction image capture requires By=Time"):
        backend.image_export(
            {
                "objects": [{"kind": "typed", "object_id": 10, "object_path": "Model/Reaction"}],
                "views": [{"kind": "current"}],
                "width": 64,
                "height": 64,
                "background": "white",
                "fit_view": False,
                "output_paths": [str(tmp_path / "viewport-force.png")],
                "view_export_path": str(tmp_path / "image-views-force.xml"),
                "restore_name": "COREX restore force",
                "preflight_only": False,
            }
        )
    assert not any(event[0] == "export" for event in events)


@pytest.mark.parametrize(
    "change",
    (
        {"width": 63},
        {"height": True},
        {"width": 8192, "height": 8192},
        {"background": "transparent"},
        {"fit_view": 1},
        {"objects": [{"kind": "text", "text": "x"}] * 17, "views": [{"kind": "text", "text": "v"}] * 16, "output_paths": ["unused"] * 272},
    ),
)
def test_owner_boundary_rejects_runtime_cap_bypass_before_export(tmp_path, change):
    backend = MechanicalOwnerBackend()
    backend.work_root = tmp_path.resolve()
    backend.app = SimpleNamespace(execute_script=lambda _script: (_ for _ in ()).throw(AssertionError("must not execute")))
    args = {
        "objects": [{"kind": "current"}],
        "views": [{"kind": "current"}],
        "width": 64,
        "height": 64,
        "background": "white",
        "fit_view": False,
        "output_paths": [str(tmp_path / "viewport-one.png")],
        "view_export_path": str(tmp_path / "image-views-one.xml"),
        "restore_name": "COREX restore test",
        "preflight_only": False,
    }
    args.update(change)
    with pytest.raises(ValueError, match="invalid"):
        backend.image_export(args)


def test_folder_alias_is_rejected_before_resolution(monkeypatch, tmp_path):
    folder = tmp_path / "alias" / "output"
    monkeypatch.setattr(
        "ea_node_editor.addons.mechanical.graphics._unsafe_existing_path",
        lambda path: Path(path) == tmp_path,
    )
    with pytest.raises(ValueError, match="links or reparse"):
        preflight_image_destinations(folder, ["a.png"], overwrite=False)


def test_dangling_folder_alias_is_rejected_even_when_exists_is_false(monkeypatch, tmp_path):
    folder = tmp_path / "dangling"
    monkeypatch.setattr(
        "ea_node_editor.addons.mechanical.graphics._unsafe_existing_path",
        lambda path: Path(path) == folder,
    )
    with pytest.raises(ValueError, match="links or reparse"):
        preflight_image_destinations(folder, ["a.png"], overwrite=False)


def test_picker_saved_view_uses_native_visible_name_for_default_file(tmp_path):
    class NamedViewSessions(_Sessions):
        def operate(self, session, **kwargs):
            response = super().operate(session, **kwargs)
            key = "image_preflight" if kwargs["args"]["preflight_only"] else "image_export"
            response[key]["images"][0]["view_name"] = "Native, Front"
            return response

    sessions = NamedViewSessions(tmp_path)
    folder = tmp_path / "published"
    selector = encode_selector(
        "view",
        document_id="document-1",
        system_key="system-1",
        object_path="",
        native_id=0,
    )
    context = _context(tmp_path, sessions)
    settings = SimpleNamespace(**{**context.properties, "folder": str(folder)})
    result = execute_image_export(context, [_model()], [], [selector], settings)
    assert result["files"] == [str(folder / "Current display_Native, Front.png")]
    assert ImageValue.from_png(Path(result["files"][0]).read_bytes()).width == 64


def test_image_descriptor_requires_order_and_requested_dimensions(tmp_path):
    images = []
    for index in range(2):
        path = tmp_path / f"viewport-{index}.png"
        payload = _png()
        path.write_bytes(payload)
        images.append(
            {
                "object_index": 0,
                "object_name": "Object",
                "object_path": "Model/Object",
                "object_id": 10,
                "view_ordinal": index,
                "view_name": f"View {index}",
                "view_kind": "saved",
                "view_index": index,
                "relative_name": path.name,
                "byte_length": len(payload),
                "sha256": hashlib.sha256(payload).hexdigest(),
                "width": 64,
                "height": 64,
            }
        )
    with pytest.raises(Exception, match="ordered Cartesian"):
        _read_image_export(tmp_path, {"images": list(reversed(images))}, (64, 64))
    for index in range(2):
        (tmp_path / f"viewport-{index}.png").write_bytes(_png())
    with pytest.raises(Exception, match="descriptor is invalid"):
        _read_image_export(tmp_path, {"images": images}, (65, 64))

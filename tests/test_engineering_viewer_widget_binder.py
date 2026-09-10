from __future__ import annotations

import hashlib
import tempfile
import threading
import time
import unittest
import weakref
import gc
import copy
from dataclasses import replace
from multiprocessing.shared_memory import SharedMemory
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import PropertyMock, patch

from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtGui import QImage
from PyQt6.QtWidgets import QApplication, QWidget

from ea_node_editor.execution.viewer_backend_engineering import (
    ENGINEERING_VIEWER_BACKEND_ID,
    ENGINEERING_VIEWER_SHARED_MEMORY_ASSET_SCHEMA,
    ENGINEERING_VIEWER_TRANSPORT_KIND,
    ENGINEERING_VIEWER_TRANSPORT_SCHEMA,
    EngineeringViewerBackend,
)
from ea_node_editor.ui_qml.engineering_viewer_widget_binder import EngineeringViewerWidgetBinder
from ea_node_editor.ui_qml.viewer_host_service import ViewerHostService
from ea_node_editor.ui_qml.viewer_widget_binder import (
    ViewerWidgetBindRequest,
    ViewerWidgetNoBind,
    ViewerWidgetReleaseRequest,
)


class _FakeContentFullscreenBridge(QObject):
    content_fullscreen_changed = pyqtSignal()
    open = False
    content_kind = ""
    workspace_id = ""
    node_id = ""
    viewer_payload: dict[str, object] = {}


class _FakeCamera:
    def __init__(self) -> None:
        self.position = None
        self.focal_point = None
        self.up = None
        self.azimuth_calls: list[float] = []
        self.elevation_calls: list[float] = []
        self.orthogonalize_calls = 0

    def Azimuth(self, value: float) -> None:  # noqa: N802
        self.azimuth_calls.append(value)

    def Elevation(self, value: float) -> None:  # noqa: N802
        self.elevation_calls.append(value)

    def OrthogonalizeViewUp(self) -> None:  # noqa: N802
        self.orthogonalize_calls += 1


class _FakeActor:
    def __init__(self, dataset=None) -> None:  # noqa: ANN001
        self.visible = True
        self.mapper = _FakeMapper(dataset)
        self.property = _FakeActorProperty()
        self.pickable = True

    def SetVisibility(self, value: int) -> None:
        self.visible = bool(value)

    def GetVisibility(self) -> bool:
        return self.visible

    def GetMapper(self):  # noqa: ANN201
        return self.mapper

    def GetProperty(self):  # noqa: ANN201, N802
        return self.property

    def PickableOff(self) -> None:  # noqa: N802
        self.pickable = False


class _FakeActorProperty:
    def __init__(self) -> None:
        self.opacity = 1.0
        self.edge_visibility = False
        self.representation = "surface"
        self.lighting = False
        self.interpolation = "flat"
        self.ambient = 0.0
        self.diffuse = 0.0
        self.specular = 0.0
        self.specular_power = 0.0
        self.line_width = 1.0
        self.point_size = 1.0

    def SetOpacity(self, value: float) -> None:  # noqa: N802
        self.opacity = value

    def SetEdgeVisibility(self, value: int) -> None:  # noqa: N802
        self.edge_visibility = bool(value)

    def SetRepresentationToWireframe(self) -> None:  # noqa: N802
        self.representation = "wireframe"

    def SetRepresentationToPoints(self) -> None:  # noqa: N802
        self.representation = "points"

    def SetRepresentationToSurface(self) -> None:  # noqa: N802
        self.representation = "surface"

    def SetLighting(self, value: int) -> None:  # noqa: N802
        self.lighting = bool(value)

    def SetInterpolationToPhong(self) -> None:  # noqa: N802
        self.interpolation = "phong"

    def SetInterpolationToFlat(self) -> None:  # noqa: N802
        self.interpolation = "flat"

    def SetAmbient(self, value: float) -> None:  # noqa: N802
        self.ambient = value

    def SetDiffuse(self, value: float) -> None:  # noqa: N802
        self.diffuse = value

    def SetSpecular(self, value: float) -> None:  # noqa: N802
        self.specular = value

    def SetSpecularPower(self, value: float) -> None:  # noqa: N802
        self.specular_power = value

    def SetLineWidth(self, value: float) -> None:  # noqa: N802
        self.line_width = value

    def SetPointSize(self, value: float) -> None:  # noqa: N802
        self.point_size = value


class _FakeMapper:
    def __init__(self, dataset=None) -> None:  # noqa: ANN001
        self.dataset = dataset
        self.clipping_planes = []

    def SetInputData(self, dataset) -> None:  # noqa: ANN001, N802
        self.dataset = dataset

    def RemoveAllClippingPlanes(self) -> None:  # noqa: N802
        self.clipping_planes.clear()

    def AddClippingPlane(self, plane) -> None:  # noqa: ANN001, N802
        self.clipping_planes.append(plane)


class _FakeDataset:
    def __init__(
        self,
        name: str,
        cell_ids: list[int] | None = None,
        *,
        bounds: tuple[float, float, float, float, float, float] | None = None,
        cell_data: dict[str, object] | None = None,
        point_data: dict[str, object] | None = None,
    ) -> None:
        self.name = name
        identifiers = list(cell_ids or [])
        self.cell_data = dict(
            cell_data
            or {
                "engineering_id": identifiers,
                "corex_block_index": [0] * len(identifiers),
                "corex_element_index": identifiers,
            }
        )
        self.point_data = dict(point_data or {})
        self.bounds = bounds

    def extract_cells(self, indices: list[int]):
        selected_cell_data = {
            key: [values[index] for index in indices]
            for key, values in self.cell_data.items()
        }
        return _FakeDataset(
            f"{self.name}:selection",
            bounds=self.bounds,
            cell_data=selected_cell_data,
            point_data=self.point_data,
        )

    def extract_points(self, indices: list[int], **_kwargs):
        selected_point_data = {
            key: [values[index] for index in indices]
            for key, values in self.point_data.items()
        }
        return _FakeDataset(
            f"{self.name}:point-selection",
            bounds=self.bounds,
            cell_data=self.cell_data,
            point_data=selected_point_data,
        )


class _FakeOrientationRepresentation:
    def __init__(self) -> None:
        self.lower_left = False

    def AnchorToLowerLeft(self) -> None:  # noqa: N802
        self.lower_left = True


class _FakeOrientationWidget:
    def __init__(self, interactor=None) -> None:  # noqa: ANN001
        self.representation = _FakeOrientationRepresentation()
        self.disabled = False
        self.interactor = interactor

    def GetRepresentation(self):  # noqa: ANN201, N802
        return self.representation

    def Off(self) -> None:  # noqa: N802
        self.disabled = True

    def EnabledOff(self) -> None:  # noqa: N802
        self.disabled = True

    def GetInteractor(self):  # noqa: ANN201, N802
        return self.interactor

    def SetInteractor(self, value) -> None:  # noqa: ANN001, N802
        self.interactor = value


class _FakeRenderer:
    def __init__(self) -> None:
        self.axes_widget = None
        self.axes_actor = None


class _FakePicker:
    def __init__(self, index: int = 0) -> None:
        self.index = index
        self.actors: list[_FakeActor] = []

    def PickFromListOn(self) -> None:  # noqa: N802
        return None

    def AddPickList(self, actor: _FakeActor) -> None:  # noqa: N802
        self.actors.append(actor)

    def Pick(self, *_args) -> int:  # noqa: ANN002, N802
        return int(bool(self.actors))

    def GetActor(self):  # noqa: ANN201, N802
        return self.actors[0] if self.actors else None

    def GetCellId(self) -> int:  # noqa: N802
        return self.index

    def GetPointId(self) -> int:  # noqa: N802
        return self.index


class _FakeInteractorStyle:
    def __init__(self) -> None:
        self.enabled = True

    def GetEnabled(self) -> bool:  # noqa: N802
        return self.enabled

    def SetEnabled(self, value: int) -> None:  # noqa: N802
        self.enabled = bool(value)


class _FakeInteractor(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.clear_calls = 0
        self.enable_lightkit_calls = 0
        self.add_mesh_calls: list[dict[str, object]] = []
        self.background_calls: list[dict[str, object]] = []
        self.render_calls = 0
        self.reset_camera_calls = 0
        self.reset_camera_bounds = None
        self.camera_position = None
        self.camera = _FakeCamera()
        self.preview = QImage(20, 12, QImage.Format.Format_ARGB32)
        self.preview.fill(0xFF2484FF)
        self.iren = self
        self._observers: dict[int, tuple[str, object]] = {}
        self._next_observer_id = 1
        self.picking_kwargs: dict[str, object] = {}
        self.picking_callback = None
        self.hidden_line_enabled = False
        self.hidden_line_calls: list[bool] = []
        self.camera_widgets: list[_FakeOrientationWidget] = []
        self.renderer = _FakeRenderer()
        self.axes_calls: list[dict[str, object]] = []
        self.interactor_style = _FakeInteractorStyle()
        self.event_position = (0, 0)
        self.render_size = (1000, 500)
        self.reset_clipping_calls = 0
        self.control_key = False
        self.device_pixel_ratio = 1.0
        self.native_ready = True
        self.close_calls = 0

    def closeEvent(self, event) -> None:  # noqa: ANN001, N802
        self.close_calls += 1
        super().closeEvent(event)

    def clear(self) -> None:
        self.clear_calls += 1
        self.add_mesh_calls.clear()

    def enable_lightkit(self) -> None:
        self.enable_lightkit_calls += 1

    def add_mesh(self, dataset, **kwargs):  # noqa: ANN001
        actor = _FakeActor(dataset)
        self.add_mesh_calls.append({"dataset": dataset, "actor": actor, **kwargs})
        return actor

    def set_background(self, color, **kwargs):  # noqa: ANN001
        self.background_calls.append({"color": color, **kwargs})

    def render(self) -> None:
        self.render_calls += 1

    def reset_camera(self, *, bounds=None, render=True) -> None:  # noqa: ANN001, FBT002
        self.reset_camera_calls += 1
        self.reset_camera_bounds = bounds

    def screenshot(self, **_kwargs):  # noqa: ANN001
        return self.preview.copy()

    def enable_cell_picking(self, callback, **kwargs) -> None:  # noqa: ANN001
        self.picking_callback = callback
        self.picking_kwargs = dict(kwargs)

    def disable_picking(self) -> None:
        self.picking_callback = None

    def remove_actor(self, actor, **_kwargs) -> None:  # noqa: ANN001
        self.add_mesh_calls = [call for call in self.add_mesh_calls if call.get("actor") is not actor]

    def enable_hidden_line_removal(self) -> None:
        self.hidden_line_enabled = True
        self.hidden_line_calls.append(True)

    def disable_hidden_line_removal(self) -> None:
        self.hidden_line_enabled = False
        self.hidden_line_calls.append(False)

    def add_camera_orientation_widget(self):  # noqa: ANN201
        widget = _FakeOrientationWidget(self)
        self.camera_widgets.append(widget)
        return widget

    def add_axes(self, **kwargs) -> object:
        widget = _FakeOrientationWidget(self)
        self.renderer.axes_widget = widget
        self.renderer.axes_actor = _FakeActor()
        self.axes_calls.append(dict(kwargs))
        return self.renderer.axes_actor

    def get_event_position(self) -> tuple[int, int]:
        return self.event_position

    def get_interactor_style(self) -> _FakeInteractorStyle:
        return self.interactor_style

    def GetRenderWindow(self):  # noqa: ANN201, N802
        return self if self.native_ready else None

    def GetSize(self) -> tuple[int, int]:  # noqa: N802
        return self.render_size

    def GetControlKey(self) -> int:  # noqa: N802
        return int(self.control_key)

    def devicePixelRatioF(self) -> float:  # noqa: N802
        return self.device_pixel_ratio

    def reset_camera_clipping_range(self) -> None:
        self.reset_clipping_calls += 1

    def add_observer(self, event_name: str, callback):  # noqa: ANN001, ANN201
        observer_id = self._next_observer_id
        self._next_observer_id += 1
        self._observers[observer_id] = (event_name, callback)
        return observer_id

    def remove_observer(self, observer_id: int) -> None:
        self._observers.pop(observer_id, None)

    def trigger(self, event_name: str, *, position: tuple[int, int] | None = None) -> None:
        if position is not None:
            self.event_position = position
        for registered_name, callback in list(self._observers.values()):
            if registered_name == event_name:
                callback(self, event_name)


def _request(
    primary: Path,
    overlay: Path | None = None,
    *,
    current_widget: QWidget | None = None,
    camera_state: dict[str, object] | None = None,
    transport_revision: int = 4,
    interaction_path: Path | None = None,
    topology_path: Path | None = None,
    options: dict[str, object] | None = None,
    attribute_colors: dict[str, object] | None = None,
    topology_attribute_colors: dict[str, object] | None = None,
    source_kind: str = "fe",
    selection_topology_path: Path | None = None,
    container: QWidget | None = None,
) -> ViewerWidgetBindRequest:
    overlays = []
    if overlay is not None:
        overlays.append(
            {
                "id": "scene_2",
                "name": "Selected faces",
                "display_path": str(overlay),
                "visible": True,
                "style": {},
            }
        )
    return ViewerWidgetBindRequest(
        workspace_id="workspace-engineering",
        node_id="node-engineering",
        session_id="session-engineering",
        backend_id=ENGINEERING_VIEWER_BACKEND_ID,
        transport_revision=transport_revision,
        live_mode="embedded",
        cache_state="live_ready",
        live_open_status="ready",
        transport={
            "kind": ENGINEERING_VIEWER_TRANSPORT_KIND,
            "schema": ENGINEERING_VIEWER_TRANSPORT_SCHEMA,
            "status": "ready",
            "layers": [{
                "id": "scene_1",
                "name": "FE mesh",
                "display_path": str(primary),
                "visible": True,
                "source_kind": source_kind,
                "source": {"sha256": "a" * 64},
                "style": {"representation": "surface_with_edges", "scalars": "stress"},
                "interaction_display_path": str(interaction_path) if interaction_path is not None else "",
                "topological_edge_path": str(topology_path) if topology_path is not None else "",
                "geometry_assets": [
                    {
                        "role": "full",
                        "content": "surface" if source_kind == "cad" else "mesh",
                        "path": str(primary),
                        "attribute_colors": dict(attribute_colors or {}),
                        "entity_arrays": (
                            {
                                "part_index": "corex_part_index",
                                "face_index": "corex_face_index",
                                "body_index": "corex_body_index",
                            }
                            if source_kind == "cad"
                            else {}
                        ),
                    },
                    *(
                        [
                            {
                                "role": "selection_identity",
                                "content": "mesh",
                                "path": str(primary),
                            }
                        ]
                        if source_kind == "fe"
                        else []
                    ),
                    *(
                        [
                            {
                                "role": "topology",
                                "content": "topological_edges",
                                "path": str(topology_path),
                                "attribute_colors": dict(topology_attribute_colors or {}),
                            }
                        ]
                        if topology_path is not None
                        else []
                    ),
                    *(
                        [
                            {
                                "role": "selection_topology",
                                "content": "selection_topology",
                                "path": str(selection_topology_path),
                            }
                        ]
                        if selection_topology_path is not None
                        else []
                    ),
                ],
                "attribute_colors": dict(attribute_colors or {}),
            }, *overlays],
        },
        camera_state=camera_state or {},
        options={"viewer_background": "#20252c", **dict(options or {})},
        summary={
            "scene_fingerprint": "b" * 64,
            "default_selection_filter": "cad_body" if source_kind == "cad" else "fe_element",
        },
        container=container,
        current_widget=current_widget,
    )


class EngineeringViewerWidgetBinderTests(unittest.TestCase):
    def test_three_same_source_scenes_keep_independent_identity_and_appearance(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            surface = Path(directory) / "surface.vtp"
            edges = Path(directory) / "edges.vtp"
            surface.touch()
            edges.touch()
            binder = EngineeringViewerWidgetBinder(
                interactor_factory=lambda parent: _FakeInteractor(parent),
                dataset_loader=lambda path: _FakeDataset(path, [1, 2]),
                background_loading=False,
            )
            request = _request(surface, topology_path=edges, source_kind="cad")
            layer = request.transport["layers"][0]
            request.transport["layers"] = [
                {**copy.deepcopy(layer), "id": f"scene_{index}", "name": "Same name"}
                for index in range(1, 4)
            ]
            widget = binder.bind_widget(request)
            state = binder._widget_state[widget]
            self.assertEqual(list(state.actors), ["scene_1", "scene_2", "scene_3"])
            self.assertEqual(len(state.topology_actors), 3)
            self.assertEqual(
                {source["layer_id"] for source in state.selection_source_actors.values()},
                {"scene_1", "scene_2", "scene_3"},
            )
            self.assertTrue(binder.set_layer_visibility(widget, "scene_1", False))
            original_actors = dict(state.actors)
            styled = replace(request, current_widget=widget, options={
                **request.options,
                "scene_styles": {"scene_2": {"opacity": 0.25, "color": "#112233"}},
            })
            self.assertIs(binder.bind_widget(styled), widget)
            self.assertIs(state.actors["scene_1"], original_actors["scene_1"])
            self.assertIs(state.actors["scene_3"], original_actors["scene_3"])
            self.assertIsNot(state.actors["scene_2"], original_actors["scene_2"])
            self.assertFalse(state.actors["scene_1"].visible)
            self.assertEqual(state.actors["scene_2"].property.opacity, 0.25)
            self.assertEqual(state.topology_actors["scene_2"].property.opacity, 0.25)
            calls = {call["name"]: call for call in widget.add_mesh_calls}
            self.assertEqual(calls["scene_2"]["color"], "#112233")
            self.assertNotIn("scalars", calls["scene_2"])
            self.assertEqual(calls["scene_2::topological_edges"]["color"], "#112233")
            self.assertEqual(calls["scene_3"]["scalars"], "stress")

            automatic = replace(styled, options={
                **styled.options, "scene_styles": {"scene_2": {"opacity": 0.6, "color": ""}},
            })
            binder.bind_widget(automatic)
            calls = {call["name"]: call for call in widget.add_mesh_calls}
            self.assertEqual(calls["scene_2"]["scalars"], "stress")
            self.assertEqual(state.topology_actors["scene_2"].property.opacity, 0.6)
            self.assertTrue(binder.isolate_layer(widget, "scene_3"))
            stats = binder.render_stats(widget)
            self.assertEqual([entry["visible"] for entry in stats["layers"]], [False, False, True])
            self.assertEqual([entry["id"] for entry in stats["layers"]], ["scene_1", "scene_2", "scene_3"])
            self.assertEqual(stats["display_state"]["layer_visibility"], state.layer_visibility)

            reduced = replace(automatic, transport_revision=5, transport={
                **automatic.transport, "layers": automatic.transport["layers"][1:],
            })
            binder.bind_widget(reduced)
            state = binder._widget_state[widget]
            self.assertEqual(set(state.actors), {"scene_2", "scene_3"})
            self.assertFalse(state.actors["scene_2"].visible)
            self.assertTrue(state.actors["scene_3"].visible)
            binder.shutdown()

    def test_scene_transport_requires_unique_stable_ids(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "mesh.vtu"
            path.touch()
            binder = EngineeringViewerWidgetBinder(background_loading=False)
            request = _request(path)
            request.transport["layers"].append(dict(request.transport["layers"][0]))
            with self.assertRaisesRegex(ValueError, "IDs must be nonempty and unique"):
                binder._layer_descriptors(request)
            request.transport["layers"] = [{**request.transport["layers"][0], "id": ""}]
            with self.assertRaisesRegex(ValueError, "IDs must be nonempty and unique"):
                binder._layer_descriptors(request)
            binder.shutdown()

    def test_mesh_kwargs_does_not_turn_missing_scalars_into_a_name(self) -> None:
        kwargs = EngineeringViewerWidgetBinder._mesh_kwargs(
            {"id": "scene_1", "name": "Geometry", "style": {}},
            options={},
        )

        self.assertNotIn("scalars", kwargs)

    def test_direct_attribute_colors_require_the_declared_array(self) -> None:
        with self.assertRaisesRegex(ValueError, "attribute-color array is missing"):
            EngineeringViewerWidgetBinder._mesh_kwargs(
                {
                    "id": "scene_1",
                    "name": "Geometry",
                    "style": {},
                    "dataset": _FakeDataset("surface", [1]),
                    "attribute_colors": {
                        "available": True,
                        "array_name": "corex_source_rgba",
                        "association": "cell",
                        "component_count": 4,
                    },
                },
                options={"show_attribute_colors": True},
            )

    def test_direct_attribute_colors_accept_consistent_multiblock_leaves(self) -> None:
        import pyvista

        first = pyvista.Cube().triangulate()
        second = pyvista.Cube(center=(2.0, 0.0, 0.0)).triangulate()
        for block in (first, second):
            block.cell_data["RGBA"] = [(10, 20, 30, 255)] * block.n_cells
        kwargs = EngineeringViewerWidgetBinder._mesh_kwargs(
            {
                "id": "scene_1",
                "name": "Colored blocks",
                "style": {},
                "dataset": pyvista.MultiBlock([first, second]),
                "attribute_colors": {
                    "available": True,
                    "array_name": "RGBA",
                    "association": "cell",
                    "component_count": 4,
                },
            },
            options={"show_attribute_colors": True},
        )

        self.assertEqual(kwargs["scalars"], "RGBA")
        self.assertTrue(kwargs["rgb"])
        self.assertEqual(kwargs["preference"], "cell")

    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_shared_memory_geometry_round_trips_into_existing_render_path(self) -> None:
        import pyvista

        surface = pyvista.PolyData(
            [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)],
            faces=[3, 0, 1, 2],
        )
        surface.cell_data["corex_source_rgba"] = [(10, 20, 30, 255)]
        surface.cell_data["corex_part_index"] = [1]
        surface.cell_data["corex_body_index"] = [1]
        surface.cell_data["corex_face_index"] = [1]
        payload = EngineeringViewerBackend._vtk_polydata_payload(surface)
        segment = SharedMemory(create=True, size=len(payload))
        segment.buf[: len(payload)] = payload
        descriptor = {
            "schema": ENGINEERING_VIEWER_SHARED_MEMORY_ASSET_SCHEMA,
            "version": 1,
            "storage": "shared_memory",
            "name": segment.name,
            "byte_length": len(payload),
            "sha256": hashlib.sha256(payload).hexdigest(),
            "format": "vtkxml-polydata",
            "role": "full",
            "content": "surface",
            "attribute_colors": {
                "available": True,
                "array_name": "corex_source_rgba",
                "association": "cell",
                "component_count": 4,
            },
            "entity_arrays": {
                "part_index": "corex_part_index",
                "body_index": "corex_body_index",
                "face_index": "corex_face_index",
            },
        }
        missing = Path(tempfile.gettempdir()) / "corex_unused_shared_surface.vtp"
        missing.unlink(missing_ok=True)
        request = _request(
            missing,
            source_kind="cad",
            options={"show_attribute_colors": True},
        )
        request.transport["layers"][0]["display_asset"] = descriptor
        binder = EngineeringViewerWidgetBinder(
            interactor_factory=lambda parent: _FakeInteractor(parent),
            dataset_loader=lambda _path: self.fail(
                "file loader must not run for shared-memory geometry"
            ),
            background_loading=False,
        )
        try:
            widget = binder.bind_widget(request)
            display_call = next(
                call
                for call in widget.add_mesh_calls
                if not str(call.get("name", "")).startswith(
                    "__engineering_pick_source__"
                )
            )
            dataset = display_call["dataset"]
            self.assertEqual(dataset.n_points, surface.n_points)
            self.assertIn("Normals", dataset.point_data)
            self.assertIn("corex_source_rgba", dataset.cell_data)
            self.assertIn("corex_face_index", dataset.cell_data)
            self.assertEqual(display_call["scalars"], "corex_source_rgba")
            self.assertTrue(display_call["rgb"])

            unknown = dict(descriptor)
            unknown["unexpected"] = True
            unknown_request = _request(
                missing,
                source_kind="cad",
                transport_revision=5,
            )
            unknown_request.transport["layers"][0]["display_asset"] = unknown
            with self.assertRaisesRegex(ValueError, "descriptor is invalid") as raised:
                binder.bind_widget(unknown_request)
            self.assertNotIn(segment.name, str(raised.exception))

            corrupt = dict(descriptor)
            corrupt["sha256"] = "0" * 64
            corrupt_request = _request(
                missing,
                source_kind="cad",
                transport_revision=6,
            )
            corrupt_request.transport["layers"][0]["display_asset"] = corrupt
            with self.assertRaisesRegex(ValueError, "geometry is unavailable") as raised:
                binder.bind_widget(corrupt_request)
            self.assertNotIn(segment.name, str(raised.exception))
        finally:
            binder.shutdown()
            segment.unlink()
            segment.close()

    def test_bind_loads_primary_and_overlay_into_one_reusable_interactor(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            primary = root / "mesh.vtu"
            overlay = root / "selection.vtp"
            primary.write_text("primary", encoding="utf-8")
            overlay.write_text("overlay", encoding="utf-8")
            loaded_paths: list[str] = []
            created: list[_FakeInteractor] = []

            def create(parent: QWidget | None) -> QWidget:
                widget = _FakeInteractor(parent)
                created.append(widget)
                return widget

            def load(path: str) -> str:
                loaded_paths.append(path)
                return f"dataset:{Path(path).name}"

            binder = EngineeringViewerWidgetBinder(
                interactor_factory=create,
                dataset_loader=load,
                background_loading=False,
            )
            widget = binder.bind_widget(_request(primary, overlay))

            self.assertIs(widget, created[0])
            self.assertEqual(loaded_paths, [str(primary), str(overlay)])
            display_calls = [
                call
                for call in created[0].add_mesh_calls
                if not str(call.get("name", "")).startswith("__engineering_pick_source__")
            ]
            self.assertEqual(len(display_calls), 2)
            self.assertEqual(created[0].enable_lightkit_calls, 1)
            self.assertEqual(created[0].reset_camera_calls, 1)
            primary_call, overlay_call = display_calls
            self.assertEqual(primary_call["dataset"], "dataset:mesh.vtu")
            self.assertEqual(primary_call["style"], "surface")
            self.assertFalse(primary_call["show_edges"])
            self.assertEqual(primary_call["scalars"], "stress")
            self.assertEqual(overlay_call["dataset"], "dataset:selection.vtp")
            self.assertNotIn("color", overlay_call)
            self.assertEqual(overlay_call["opacity"], 1.0)
            self.assertTrue(overlay_call["pickable"])
            self.assertTrue(widget.property("ea.nativeWindowOverlay"))
            self.assertEqual(binder.render_stats(widget)["layer_count"], 2)
            self.assertTrue(binder.set_layer_visibility(widget, "scene_2", False))
            self.assertFalse(binder.render_stats(widget)["layers"][1]["visible"])
            self.assertTrue(binder.isolate_layer(widget, "scene_1"))

            created[0].camera_position = (
                (9.0, 8.0, 7.0),
                (0.0, 0.0, 0.0),
                (0.0, 1.0, 0.0),
            )
            rebound = binder.bind_widget(
                _request(
                    primary,
                    overlay,
                    current_widget=widget,
                    camera_state={"position": [1.0, 1.0, 1.0]},
                )
            )
            self.assertIs(rebound, widget)
            self.assertEqual(len(created), 1)
            self.assertEqual(loaded_paths, [str(primary), str(overlay)])
            self.assertEqual(
                len(
                    [
                        call
                        for call in created[0].add_mesh_calls
                        if not str(call.get("name", "")).startswith(
                            "__engineering_pick_source__"
                        )
                    ]
                ),
                2,
            )
            self.assertEqual(created[0].clear_calls, 1)
            self.assertEqual(tuple(rebound.camera_position[0]), (9.0, 8.0, 7.0))

            preview = binder.capture_preview_image(widget)
            self.assertIsInstance(preview, QImage)
            self.assertFalse(preview.isNull())

            binder.release_widget(
                ViewerWidgetReleaseRequest(
                    workspace_id="workspace-engineering",
                    node_id="node-engineering",
                    session_id="session-engineering",
                    backend_id=ENGINEERING_VIEWER_BACKEND_ID,
                    transport_revision=4,
                    widget=widget,
                )
            )
            self.assertEqual(binder.render_stats(widget)["layer_count"], 0)
            self.assertEqual(binder.render_stats(widget)["dataset_count"], 0)
            binder.shutdown()

    def test_missing_layer_file_declines_live_binding(self) -> None:
        missing = Path(tempfile.gettempdir()) / "corex_missing_binder_scene.vtk"
        missing.unlink(missing_ok=True)
        binder = EngineeringViewerWidgetBinder(
            interactor_factory=lambda parent: _FakeInteractor(parent),
            dataset_loader=lambda path: path,
            background_loading=False,
        )

        with self.assertRaises(ViewerWidgetNoBind):
            binder.bind_widget(_request(missing))
        binder.shutdown()

    def test_background_loader_discards_stale_revision_and_retries_ready_revision(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            old_path = root / "old.vtu"
            new_path = root / "new.vtu"
            old_path.write_text("old", encoding="utf-8")
            new_path.write_text("new", encoding="utf-8")
            old_started = threading.Event()
            release_old = threading.Event()
            ready_revisions: list[int] = []

            def load(path: str) -> str:
                if Path(path) == old_path:
                    old_started.set()
                    release_old.wait(2.0)
                return f"dataset:{Path(path).name}"

            binder = EngineeringViewerWidgetBinder(
                interactor_factory=lambda parent: _FakeInteractor(parent),
                dataset_loader=load,
            )
            binder.load_ready.connect(lambda _ws, _node, _session, revision: ready_revisions.append(revision))
            try:
                with self.assertRaises(ViewerWidgetNoBind) as old_pending:
                    binder.bind_widget(_request(old_path, transport_revision=4))
                self.assertTrue(getattr(old_pending.exception, "retry_when_ready", False))
                self.assertTrue(old_started.wait(1.0))

                with self.assertRaises(ViewerWidgetNoBind):
                    binder.bind_widget(_request(new_path, transport_revision=5))
                deadline = time.monotonic() + 2.0
                while 5 not in ready_revisions and time.monotonic() < deadline:
                    self.app.processEvents()
                    time.sleep(0.01)
                self.assertIn(5, ready_revisions)
                widget = binder.bind_widget(_request(new_path, transport_revision=5))
                self.assertEqual(widget.add_mesh_calls[0]["dataset"], "dataset:new.vtu")

                release_old.set()
                deadline = time.monotonic() + 1.0
                while time.monotonic() < deadline:
                    self.app.processEvents()
                    time.sleep(0.01)
                self.assertNotIn(4, ready_revisions)
            finally:
                release_old.set()
                binder.shutdown()

    def test_interaction_lod_selection_activation_and_release_drop_datasets(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            full_path = root / "full.vtu"
            interaction_path = root / "coarse.vtu"
            full_path.write_text("full", encoding="utf-8")
            interaction_path.write_text("coarse", encoding="utf-8")
            full_dataset = _FakeDataset("full", [10, 20, 30])
            coarse_dataset = _FakeDataset("coarse", [10, 20, 30])
            loaded = {str(full_path): full_dataset, str(interaction_path): coarse_dataset}
            full_ref = weakref.ref(full_dataset)
            binder = EngineeringViewerWidgetBinder(
                interactor_factory=lambda parent: _FakeInteractor(parent),
                dataset_loader=lambda path: loaded.pop(path),
                background_loading=False,
            )
            widget = binder.bind_widget(_request(full_path, interaction_path=interaction_path))
            actor = binder._widget_state[widget].actors["scene_1"]
            self.assertIs(actor.mapper.dataset, full_dataset)
            widget.trigger("StartInteractionEvent")
            self.assertIs(actor.mapper.dataset, coarse_dataset)
            widget.trigger("EndInteractionEvent")
            deadline = time.monotonic() + 0.5
            while actor.mapper.dataset is coarse_dataset and time.monotonic() < deadline:
                self.app.processEvents()
                time.sleep(0.01)
            self.assertIs(actor.mapper.dataset, full_dataset)

            self.assertTrue(
                binder.activate_selection(
                    widget,
                    [
                        {
                            "layer_id": "scene_1",
                            "source_fingerprint": "a" * 64,
                            "entity_kind": "fe_element",
                            "entity_id": "block:0/element:20",
                        }
                    ],
                )
            )
            self.assertEqual(
                binder.selection_snapshot(widget)["entities"][0]["entity_id"],
                "block:0/element:20",
            )
            self.assertTrue(
                binder.activate_selection(
                    widget,
                    [
                        {
                            "layer_id": "scene_1",
                            "source_fingerprint": "a" * 64,
                            "entity_kind": "fe_element",
                            "entity_id": f"block:0/element:{value}",
                        }
                        for value in (30, 10)
                    ],
                )
            )
            self.assertEqual(binder.render_stats(widget)["selected_entity_count"], 2)

            del actor
            del full_dataset
            binder.release_widget(
                ViewerWidgetReleaseRequest(
                    workspace_id="workspace-engineering",
                    node_id="node-engineering",
                    session_id="session-engineering",
                    backend_id=ENGINEERING_VIEWER_BACKEND_ID,
                    transport_revision=4,
                    widget=widget,
                )
            )
            gc.collect()
            self.assertIsNone(full_ref())
            binder.shutdown()

    def test_exact_topology_edges_and_visible_edge_wireframe_are_independent(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            surface_path = root / "surface.vtp"
            topology_path = root / "topology_edges.vtp"
            surface_path.write_text("surface", encoding="utf-8")
            topology_path.write_text("topology", encoding="utf-8")
            surface = _FakeDataset("surface", [1, 2])
            topology = _FakeDataset("topology", [10, 11])
            datasets = {str(surface_path): surface, str(topology_path): topology}
            binder = EngineeringViewerWidgetBinder(
                interactor_factory=lambda parent: _FakeInteractor(parent),
                dataset_loader=datasets.__getitem__,
                background_loading=False,
            )
            widget = binder.bind_widget(
                _request(
                    surface_path,
                    topology_path=topology_path,
                    source_kind="cad",
                    options={"representation": "surface_with_edges", "show_mesh_edges": False},
                )
            )
            state = binder._widget_state[widget]
            display_calls = [
                call
                for call in widget.add_mesh_calls
                if not str(call.get("name", "")).startswith("__engineering_pick_source__")
            ]
            self.assertEqual(len(display_calls), 2)
            self.assertFalse(widget.add_mesh_calls[0]["show_edges"])
            self.assertTrue(state.topology_actors["scene_1"].visible)
            self.assertTrue(binder.set_selection_filter(widget, "cad_edge"))
            self.assertAlmostEqual(
                state.selection_source_actors["scene_1:cad_edge"]["actor"].property.opacity,
                0.18,
            )

            widget.camera_position = ((7.0, 6.0, 5.0), (0.0, 0.0, 0.0), (0.0, 1.0, 0.0))
            binder.bind_widget(
                _request(
                    surface_path,
                    topology_path=topology_path,
                    source_kind="cad",
                    current_widget=widget,
                    options={"representation": "wireframe_visible_edges"},
                )
            )
            self.assertTrue(widget.hidden_line_enabled)
            occluder_call = next(
                call for call in widget.add_mesh_calls if call.get("name") == "scene_1"
            )
            self.assertEqual(occluder_call["style"], "surface")
            self.assertEqual(occluder_call["opacity"], 1.0)
            self.assertFalse(occluder_call["lighting"])
            self.assertFalse(occluder_call["show_edges"])
            self.assertNotIn("scalars", occluder_call)
            self.assertEqual(
                widget.background_calls[-1]["color"],
                widget.background_calls[-1]["top"],
            )
            self.assertTrue(state.actors["scene_1"].visible)
            self.assertTrue(state.topology_actors["scene_1"].visible)
            self.assertEqual(tuple(widget.camera_position[0]), (7.0, 6.0, 5.0))

            binder.bind_widget(
                _request(
                    surface_path,
                    topology_path=topology_path,
                    source_kind="cad",
                    current_widget=widget,
                    options={"representation": "wireframe"},
                )
            )
            self.assertFalse(widget.hidden_line_enabled)
            self.assertNotEqual(
                widget.background_calls[-1]["color"],
                widget.background_calls[-1]["top"],
            )
            self.assertFalse(state.actors["scene_1"].visible)
            self.assertTrue(state.topology_actors["scene_1"].visible)

            binder.bind_widget(
                _request(
                    surface_path,
                    topology_path=topology_path,
                    source_kind="cad",
                    current_widget=widget,
                    options={"representation": "surface"},
                )
            )
            self.assertTrue(state.actors["scene_1"].visible)
            self.assertFalse(state.topology_actors["scene_1"].visible)
            self.assertEqual(widget.hidden_line_calls, [True, False])
            binder.shutdown()

    def test_declared_missing_topology_edges_declines_live_binding(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            surface_path = root / "surface.vtp"
            surface_path.write_text("surface", encoding="utf-8")
            missing = root / "missing_edges.vtp"
            binder = EngineeringViewerWidgetBinder(
                interactor_factory=lambda parent: _FakeInteractor(parent),
                dataset_loader=lambda path: path,
                background_loading=False,
            )
            with self.assertRaisesRegex(ViewerWidgetNoBind, "topological-edge file is missing"):
                binder.bind_widget(_request(surface_path, topology_path=missing))
            binder.shutdown()

    def test_direct_attribute_colors_replace_only_affected_actors(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            surface_path = root / "surface.vtp"
            topology_path = root / "topology_edges.vtp"
            surface_path.write_text("surface", encoding="utf-8")
            topology_path.write_text("topology", encoding="utf-8")
            surface = _FakeDataset(
                "surface",
                cell_data={"engineering_id": [1], "corex_source_rgba": [(1, 2, 3, 255)]},
            )
            topology = _FakeDataset(
                "topology",
                cell_data={"engineering_id": [10], "corex_source_rgba": [(4, 5, 6, 255)]},
            )
            datasets = {str(surface_path): surface, str(topology_path): topology}
            metadata = {
                "available": True,
                "array_name": "corex_source_rgba",
                "association": "cell",
                "component_count": 4,
            }
            binder = EngineeringViewerWidgetBinder(
                interactor_factory=lambda parent: _FakeInteractor(parent),
                dataset_loader=datasets.__getitem__,
                background_loading=False,
            )
            widget = binder.bind_widget(
                _request(
                    surface_path,
                    topology_path=topology_path,
                    attribute_colors=metadata,
                    topology_attribute_colors=metadata,
                    options={"show_attribute_colors": False},
                )
            )
            state = binder._widget_state[widget]
            old_surface_actor = state.actors["scene_1"]
            old_topology_actor = state.topology_actors["scene_1"]

            binder.bind_widget(
                _request(
                    surface_path,
                    topology_path=topology_path,
                    current_widget=widget,
                    attribute_colors=metadata,
                    topology_attribute_colors=metadata,
                    options={"show_attribute_colors": True},
                )
            )
            self.assertIsNot(state.actors["scene_1"], old_surface_actor)
            self.assertIsNot(state.topology_actors["scene_1"], old_topology_actor)
            color_calls = [call for call in widget.add_mesh_calls if call.get("rgb")]
            self.assertEqual(len(color_calls), 2)
            self.assertTrue(all(call["scalars"] == "corex_source_rgba" for call in color_calls))
            self.assertTrue(all(call["preference"] == "cell" for call in color_calls))
            self.assertTrue(all(call["show_scalar_bar"] is False for call in color_calls))
            binder.shutdown()

    def test_view_cube_cleanup_uses_widget_component(self) -> None:
        interactor = _FakeInteractor()
        cube = interactor.add_camera_orientation_widget()
        other_cube = interactor.add_camera_orientation_widget()
        interactor.widgets = SimpleNamespace(camera_widgets=interactor.camera_widgets)
        state = SimpleNamespace(view_cube_widget=cube)

        with patch.object(
            _FakeInteractor, "camera_widgets", new_callable=PropertyMock, create=True
        ) as deprecated_camera_widgets:
            deprecated_camera_widgets.side_effect = AssertionError(
                "Deprecated Plotter.camera_widgets accessed"
            )
            EngineeringViewerWidgetBinder._remove_view_cube(interactor, state)

        self.assertEqual(interactor.widgets.camera_widgets, [other_cube])
        self.assertTrue(cube.disabled)
        self.assertIsNone(cube.GetInteractor())
        self.assertIsNone(state.view_cube_widget)

    def test_orientation_aids_world_axes_and_release_cleanup(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            surface_path = Path(temporary_directory) / "surface.vtp"
            surface_path.write_text("surface", encoding="utf-8")
            surface = _FakeDataset("surface", [1], bounds=(-2.0, 2.0, -1.0, 1.0, -3.0, 3.0))
            binder = EngineeringViewerWidgetBinder(
                interactor_factory=lambda parent: _FakeInteractor(parent),
                dataset_loader=lambda _path: surface,
                background_loading=False,
            )
            widget = binder.bind_widget(
                _request(
                    surface_path,
                    options={
                        "show_view_cube": True,
                        "show_orientation_triad": True,
                        "show_world_axes": True,
                    },
                )
            )
            state = binder._widget_state[widget]
            cube = state.view_cube_widget
            triad = state.orientation_triad_widget
            self.assertTrue(cube.representation.lower_left)
            self.assertEqual(
                widget.axes_calls,
                [
                    {
                        "interactive": False,
                        "viewport": (0.82, 0.0, 1.0, 0.18),
                        "x_color": "#ef4444",
                        "y_color": "#22c55e",
                        "z_color": "#3b82f6",
                    }
                ],
            )
            self.assertFalse(state.orientation_triad_actor.pickable)
            self.assertEqual(len(state.triad_drag_observers), 4)
            self.assertEqual(len(state.world_axes_actors), 3)
            world_calls = [
                call
                for call in widget.add_mesh_calls
                if str(call.get("name", "")).startswith("__engineering_world_axis__")
            ]
            self.assertEqual(len(world_calls), 3)
            self.assertTrue(all(call["pickable"] is False for call in world_calls))
            self.assertEqual(
                {call["color"] for call in world_calls},
                {"#ef4444", "#22c55e", "#3b82f6"},
            )

            render_calls = widget.render_calls
            widget.trigger("LeftButtonPressEvent", position=(900, 50))
            self.assertTrue(state.triad_drag_active)
            self.assertFalse(widget.interactor_style.enabled)
            widget.trigger("MouseMoveEvent", position=(920, 70))
            self.assertEqual(widget.camera.azimuth_calls, [-8.0])
            self.assertEqual(widget.camera.elevation_calls, [8.0])
            self.assertEqual(widget.camera.orthogonalize_calls, 1)
            self.assertEqual(widget.reset_clipping_calls, 1)
            self.assertGreater(widget.render_calls, render_calls)
            widget.trigger("LeftButtonReleaseEvent", position=(920, 70))
            self.assertFalse(state.triad_drag_active)
            self.assertTrue(widget.interactor_style.enabled)

            binder.bind_widget(
                _request(
                    surface_path,
                    current_widget=widget,
                    options={
                        "show_view_cube": True,
                        "show_orientation_triad": False,
                        "show_world_axes": True,
                    },
                )
            )
            self.assertIsNone(state.orientation_triad_widget)
            self.assertEqual(state.triad_drag_observers, [])
            self.assertTrue(state.selection_observers)
            self.assertEqual(state.interaction_observers, [])

            binder.bind_widget(
                _request(
                    surface_path,
                    current_widget=widget,
                    options={
                        "show_view_cube": True,
                        "show_orientation_triad": True,
                        "show_world_axes": True,
                    },
                )
            )
            self.assertIsNotNone(state.orientation_triad_widget)
            self.assertEqual(len(state.triad_drag_observers), 4)
            self.assertEqual(len(widget.axes_calls), 2)

            binder.release_widget(
                ViewerWidgetReleaseRequest(
                    workspace_id="workspace-engineering",
                    node_id="node-engineering",
                    session_id="session-engineering",
                    backend_id=ENGINEERING_VIEWER_BACKEND_ID,
                    transport_revision=4,
                    widget=widget,
                )
            )
            self.assertTrue(cube.disabled)
            self.assertTrue(triad.disabled)
            self.assertEqual(widget.camera_widgets, [])
            self.assertEqual(state.world_axes_actors, [])
            self.assertEqual(state.triad_drag_observers, [])
            self.assertEqual(widget._observers, {})
            binder.shutdown()

    def test_fit_and_selection_isolate_update_restore(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            surface_path = Path(temporary_directory) / "surface.vtp"
            surface_path.write_text("surface", encoding="utf-8")
            surface = _FakeDataset(
                "surface",
                [10, 20, 30],
                bounds=(-4.0, 4.0, -2.0, 2.0, -1.0, 1.0),
            )
            binder = EngineeringViewerWidgetBinder(
                interactor_factory=lambda parent: _FakeInteractor(parent),
                dataset_loader=lambda _path: surface,
                background_loading=False,
            )
            widget = binder.bind_widget(
                _request(
                    surface_path,
                    options={"show_view_cube": False, "show_orientation_triad": False},
                )
            )
            selection_events: list[tuple[str, str]] = []
            binder.selection_changed.connect(
                lambda workspace_id, node_id: selection_events.append((workspace_id, node_id))
            )
            entity = {
                "layer_id": "scene_1",
                "source_fingerprint": "a" * 64,
                "entity_kind": "fe_element",
                "entity_id": "block:0/element:20",
            }
            self.assertTrue(binder.activate_selection(widget, [entity]))
            self.assertEqual(
                selection_events,
                [("workspace-engineering", "node-engineering")],
            )
            self.assertTrue(binder.fit_selection(widget))
            self.assertEqual(widget.reset_camera_bounds, surface.bounds)

            state = binder._widget_state[widget]
            base_actor = state.actors["scene_1"]
            self.assertTrue(binder.toggle_selection_isolate(widget))
            self.assertTrue(state.selection_isolated)
            self.assertFalse(base_actor.visible)
            self.assertTrue(state.selection_isolate_actor.visible)

            self.assertTrue(
                binder.activate_selection(
                    widget,
                    [{**entity, "entity_id": "block:0/element:10"}],
                )
            )
            self.assertTrue(binder.toggle_selection_isolate(widget, update=True))
            isolated_dataset = state.selection_isolate_actor.mapper.dataset
            self.assertEqual(isolated_dataset.cell_data["engineering_id"], [10])

            self.assertTrue(binder.toggle_selection_isolate(widget))
            self.assertFalse(state.selection_isolated)
            self.assertTrue(base_actor.visible)
            self.assertIsNone(state.selection_isolate_actor)
            binder.shutdown()

    def test_cad_part_face_ids_are_stable_composites(self) -> None:
        dataset = _FakeDataset(
            "cad",
            cell_data={"corex_part_index": [2, 2], "corex_face_index": [5, 9]},
        )
        self.assertEqual(
            EngineeringViewerWidgetBinder._stable_entity_ids(
                dataset,
                entity_kind="cad_face",
                association="cell",
            ),
            ["part:2/face:5", "part:2/face:9"],
        )

    def test_click_selection_ignores_drag_and_camera_interaction(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            surface_path = Path(temporary_directory) / "mesh.vtu"
            interaction_path = Path(temporary_directory) / "mesh.coarse.vtu"
            surface_path.write_text("mesh", encoding="utf-8")
            interaction_path.write_text("mesh", encoding="utf-8")
            surface = _FakeDataset("mesh", [10, 20])
            binder = EngineeringViewerWidgetBinder(
                interactor_factory=lambda parent: _FakeInteractor(parent),
                dataset_loader=lambda _path: surface,
                picker_factory=lambda _association: _FakePicker(index=1),
                background_loading=False,
            )
            widget = binder.bind_widget(
                _request(
                    surface_path,
                    interaction_path=interaction_path,
                    options={"show_view_cube": False, "show_orientation_triad": False},
                )
            )
            state = binder._widget_state[widget]

            widget.trigger("LeftButtonPressEvent", position=(300, 200))
            widget.trigger("LeftButtonReleaseEvent", position=(300, 200))
            self.assertEqual(
                [value["entity_id"] for value in state.selected_entities],
                ["block:0/element:20"],
            )

            binder._set_selected_entities(widget, state, [])
            threshold = binder._selection_click_threshold(widget)
            widget.trigger("LeftButtonPressEvent", position=(500, 300))
            widget.trigger("MouseMoveEvent", position=(501, 300))
            widget.trigger("LeftButtonReleaseEvent", position=(501, 300))
            self.assertEqual(
                [value["entity_id"] for value in state.selected_entities],
                ["block:0/element:20"],
            )

            binder._set_selected_entities(widget, state, [])
            widget.trigger("LeftButtonPressEvent", position=(300, 200))
            widget.trigger("MouseMoveEvent", position=(300 + threshold + 1, 200))
            widget.trigger("LeftButtonReleaseEvent", position=(300 + threshold + 1, 200))
            self.assertEqual(state.selected_entities, [])

            widget.trigger("LeftButtonPressEvent", position=(300, 200))
            widget.trigger("StartInteractionEvent")
            widget.trigger("MouseMoveEvent", position=(301, 200))
            widget.trigger("EndInteractionEvent")
            widget.trigger("LeftButtonReleaseEvent", position=(301, 200))
            self.assertEqual(state.selected_entities, [])
            binder.shutdown()

    def test_double_click_tangent_selection_and_control_toggle(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            surface_path = root / "surface.vtp"
            topology_path = root / "selection_topology.json"
            surface_path.write_text("surface", encoding="utf-8")
            topology_path.write_text(
                """
                {
                  "face_continuity": [
                    {
                      "face_a": "part:2/face:5",
                      "face_b": "part:2/face:9",
                      "supported": true,
                      "angular_deviation_degrees": 3.0
                    }
                  ]
                }
                """,
                encoding="utf-8",
            )
            surface = _FakeDataset(
                "cad",
                cell_data={
                    "corex_part_index": [2, 2],
                    "corex_face_index": [5, 9],
                    "corex_body_index": [1, 1],
                },
            )
            binder = EngineeringViewerWidgetBinder(
                interactor_factory=lambda parent: _FakeInteractor(parent),
                dataset_loader=lambda _path: surface,
                picker_factory=lambda _association: _FakePicker(index=0),
                tangent_selection_angle_provider=lambda: 5.0,
                background_loading=False,
            )
            widget = binder.bind_widget(
                _request(
                    surface_path,
                    source_kind="cad",
                    selection_topology_path=topology_path,
                    options={"show_view_cube": False, "show_orientation_triad": False},
                )
            )
            state = binder._widget_state[widget]
            self.assertTrue(binder.set_selection_filter(widget, "cad_face"))

            widget.trigger("LeftButtonPressEvent", position=(300, 200))
            widget.trigger("LeftButtonReleaseEvent", position=(300, 200))
            self.assertEqual(
                [value["entity_id"] for value in state.selected_entities],
                ["part:2/face:5"],
            )
            widget.trigger("LeftButtonPressEvent", position=(300, 200))
            widget.trigger("LeftButtonReleaseEvent", position=(300, 200))
            self.assertEqual(
                {value["entity_id"] for value in state.selected_entities},
                {"part:2/face:5", "part:2/face:9"},
            )

            binder._set_selected_entities(widget, state, [])
            widget.control_key = True
            widget.trigger("LeftButtonPressEvent", position=(300, 200))
            widget.trigger("LeftButtonReleaseEvent", position=(300, 200))
            self.assertEqual(
                [value["entity_id"] for value in state.selected_entities],
                ["part:2/face:5"],
            )
            widget.trigger("LeftButtonPressEvent", position=(300, 200))
            widget.trigger("LeftButtonReleaseEvent", position=(300, 200))
            self.assertEqual(
                {value["entity_id"] for value in state.selected_entities},
                {"part:2/face:5", "part:2/face:9"},
            )
            binder.shutdown()

    def test_reparent_refresh_recreates_aids_and_observers_once(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            surface_path = Path(temporary_directory) / "mesh.vtu"
            interaction_path = Path(temporary_directory) / "mesh.coarse.vtu"
            surface_path.write_text("mesh", encoding="utf-8")
            interaction_path.write_text("mesh", encoding="utf-8")
            surface = _FakeDataset("mesh", [10])
            binder = EngineeringViewerWidgetBinder(
                interactor_factory=lambda parent: _FakeInteractor(parent),
                dataset_loader=lambda _path: surface,
                background_loading=False,
            )
            widget = binder.bind_widget(
                _request(
                    surface_path,
                    interaction_path=interaction_path,
                    options={"show_view_cube": True, "show_orientation_triad": True},
                )
            )
            state = binder._widget_state[widget]
            old_cube = state.view_cube_widget
            old_triad = state.orientation_triad_widget

            binder.prepare_for_reparent(widget)
            self.assertEqual(state.selection_observers, [])
            self.assertEqual(state.interaction_observers, [])
            self.assertEqual(state.triad_drag_observers, [])
            self.assertIsNone(old_cube.GetInteractor())
            self.assertIsNone(old_triad.GetInteractor())
            axes_call_count = len(widget.axes_calls)

            binder.bind_widget(
                _request(
                    surface_path,
                    interaction_path=interaction_path,
                    current_widget=widget,
                    options={"show_view_cube": True, "show_orientation_triad": True},
                )
            )
            self.assertIsNone(state.view_cube_widget)
            self.assertIsNone(state.orientation_triad_widget)
            self.assertEqual(len(widget.axes_calls), axes_call_count)

            binder.refresh_after_attach(widget)
            counts = (
                len(state.selection_observers),
                len(state.interaction_observers),
                len(state.triad_drag_observers),
            )
            self.assertEqual(counts, (6, 2, 4))
            self.assertIsNot(state.view_cube_widget, old_cube)
            self.assertIsNot(state.orientation_triad_widget, old_triad)

            binder.refresh_after_attach(widget)
            self.assertEqual(
                (
                    len(state.selection_observers),
                    len(state.interaction_observers),
                    len(state.triad_drag_observers),
                ),
                counts,
            )
            binder.shutdown()

    def test_default_interactor_is_constructed_parentless_then_assigned_requested_parent(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            surface_path = Path(temporary_directory) / "mesh.vtu"
            surface_path.write_text("mesh", encoding="utf-8")
            container = QWidget()
            widget = _FakeInteractor()
            binder = EngineeringViewerWidgetBinder(
                dataset_loader=lambda _path: _FakeDataset("mesh", [10]),
                background_loading=False,
            )

            with patch("pyvistaqt.QtInteractor", return_value=widget) as constructor:
                bound = binder.bind_widget(_request(surface_path, container=container))

            self.assertIs(bound, widget)
            self.assertIsNone(constructor.call_args.kwargs["parent"])
            self.assertIs(widget.parent(), container)

            binder.release_widget(
                ViewerWidgetReleaseRequest(
                    workspace_id="workspace-engineering",
                    node_id="node-engineering",
                    session_id="session-engineering",
                    backend_id=ENGINEERING_VIEWER_BACKEND_ID,
                    transport_revision=4,
                    container=container,
                    widget=widget,
                    reason="test_release",
                )
            )
            widget.close()
            binder.shutdown()

    def test_reparent_refresh_defers_once_and_reports_readiness(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            surface_path = Path(temporary_directory) / "mesh.vtu"
            surface_path.write_text("mesh", encoding="utf-8")
            surface = _FakeDataset("mesh", [10])
            binder = EngineeringViewerWidgetBinder(
                interactor_factory=lambda parent: _FakeInteractor(parent),
                dataset_loader=lambda _path: surface,
                background_loading=False,
            )
            widget = binder.bind_widget(
                _request(
                    surface_path,
                    options={"show_view_cube": False, "show_orientation_triad": False},
                )
            )
            ready_revisions: list[int] = []
            binder.load_ready.connect(
                lambda _workspace, _node, _session, revision: ready_revisions.append(revision)
            )
            widget.native_ready = False
            binder.prepare_for_reparent(widget)

            with self.assertRaises(ViewerWidgetNoBind) as first_pending:
                binder.refresh_after_attach(widget)
            self.assertTrue(getattr(first_pending.exception, "retry_when_ready", False))
            with self.assertRaises(ViewerWidgetNoBind):
                binder.refresh_after_attach(widget)
            self.app.processEvents()
            self.assertEqual(ready_revisions, [4])
            with self.assertRaisesRegex(RuntimeError, "not ready after attachment"):
                binder.refresh_after_attach(widget)

            widget.native_ready = True
            self.assertTrue(binder.refresh_after_attach(widget))
            binder.shutdown()

    def test_restore_view_state_resets_clipping_before_render(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            surface_path = Path(temporary_directory) / "mesh.vtu"
            surface_path.write_text("mesh", encoding="utf-8")
            binder = EngineeringViewerWidgetBinder(
                interactor_factory=lambda parent: _FakeInteractor(parent),
                dataset_loader=lambda _path: _FakeDataset("mesh", [10]),
                background_loading=False,
            )
            widget = binder.bind_widget(_request(surface_path))
            clipping_calls = widget.reset_clipping_calls
            render_calls = widget.render_calls

            self.assertTrue(
                binder.restore_view_state(
                    widget,
                    {
                        "position": [2.0, 2.0, 2.0],
                        "focal_point": [0.0, 0.0, 0.0],
                        "viewup": [0.0, 1.0, 0.0],
                    },
                )
            )
            self.assertEqual(widget.reset_clipping_calls, clipping_calls + 1)
            self.assertEqual(widget.render_calls, render_calls + 1)
            binder.shutdown()

    def test_cad_render_matrix_and_fe_flat_shading(self) -> None:
        import pyvista

        prepared = pyvista.Cube().triangulate()
        prepared.cell_data["corex_part_index"] = list(range(prepared.n_cells))
        self.assertEqual(prepared.active_scalars_name, "corex_part_index")

        prepared = EngineeringViewerWidgetBinder._prepare_shaded_dataset(
            prepared,
            source_kind="cad",
        )

        self.assertIsNone(prepared.active_scalars_name)
        self.assertIn("corex_part_index", prepared.cell_data)
        self.assertEqual(prepared.point_data.active_normals_name, "Normals")
        cad_dataset = _FakeDataset("cad", [1])
        cad_layer = {
            "source_kind": "cad",
            "id": "scene_1",
            "name": "CAD",
            "dataset": cad_dataset,
            "style": {},
        }
        fe_layer = {
            "source_kind": "fe",
            "id": "scene_1",
            "name": "FE",
            "dataset": _FakeDataset("fe", [1]),
            "style": {},
        }
        cad_kwargs = EngineeringViewerWidgetBinder._mesh_kwargs(
            cad_layer,
            options={"representation": "wireframe", "show_mesh_edges": True},
        )
        self.assertEqual(cad_kwargs["style"], "surface")
        self.assertFalse(cad_kwargs["show_edges"])
        self.assertTrue(cad_kwargs["smooth_shading"])

        fe_kwargs = EngineeringViewerWidgetBinder._mesh_kwargs(
            fe_layer,
            options={"representation": "surface", "show_mesh_edges": False},
        )
        self.assertFalse(fe_kwargs["show_edges"])
        self.assertFalse(fe_kwargs["smooth_shading"])
        fe_edges = EngineeringViewerWidgetBinder._mesh_kwargs(
            fe_layer,
            options={"representation": "surface", "show_mesh_edges": True},
        )
        self.assertTrue(fe_edges["show_edges"])

        actor = _FakeActor(cad_dataset)
        EngineeringViewerWidgetBinder._apply_actor_material(actor.property, cad_kwargs)
        self.assertTrue(actor.property.lighting)
        self.assertEqual(actor.property.interpolation, "phong")
        self.assertAlmostEqual(actor.property.specular, 0.22)

    def test_viewer_host_registers_engineering_binder(self) -> None:
        host = ViewerHostService(
            qml_engine_provider=lambda: None,
            save_file_dialog=lambda **_kwargs: "",
            cycle_camera_bookmark=lambda _node_id, _direction: False,
            content_fullscreen_bridge=_FakeContentFullscreenBridge(),  # type: ignore[arg-type]
        )
        try:
            binder = host.binder_registry.lookup(ENGINEERING_VIEWER_BACKEND_ID)
            self.assertIsInstance(binder, EngineeringViewerWidgetBinder)
        finally:
            host.shutdown()


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import copy
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol
from weakref import WeakKeyDictionary

from PyQt6.QtGui import QImage
from PyQt6.QtWidgets import QWidget

from ea_node_editor.execution.plot_backend import PlotRenderRequest
from ea_node_editor.execution.plot_backend_matplotlib import (
    MATPLOTLIB_PLOT_BACKEND_ID,
    MatplotlibLive2DPlotBackend,
)
from ea_node_editor.execution.plot_backend_pyqtgraph import (
    PYQTGRAPH_PLOT_BACKEND_ID,
    PyQtGraphLive2DPlotBackend,
)
from ea_node_editor.execution.plot_backend_pyvista import (
    PYVISTA_PLOT_BACKEND_ID,
    PyVistaLive3DPlotBackend,
)


class PlotWidgetNoBind(RuntimeError):
    """Signal that the plot host should leave the overlay container unbound."""


@dataclass(slots=True, frozen=True)
class PlotWidgetBindRequest:
    workspace_id: str
    node_id: str
    plot_type: str
    backend_id: str
    render_request: PlotRenderRequest
    render_revision: int = 0
    properties: Mapping[str, Any] = field(default_factory=dict)
    plot_surface: Mapping[str, Any] = field(default_factory=dict)
    container: QWidget | None = None
    current_widget: QWidget | None = None


@dataclass(slots=True, frozen=True)
class PlotWidgetReleaseRequest:
    workspace_id: str
    node_id: str
    plot_type: str
    backend_id: str
    render_revision: int = 0
    properties: Mapping[str, Any] = field(default_factory=dict)
    plot_surface: Mapping[str, Any] = field(default_factory=dict)
    container: QWidget | None = None
    widget: QWidget | None = None
    reason: str = ""


class PlotWidgetBinder(Protocol):
    def bind_widget(self, request: PlotWidgetBindRequest) -> QWidget | None:
        ...

    def release_widget(self, request: PlotWidgetReleaseRequest) -> None:
        ...


class PlotWidgetPreviewCapture(Protocol):
    def capture_preview_image(self, widget: QWidget | None) -> QImage | None:
        ...


class PlotWidgetViewState(Protocol):
    def capture_view_state(self, widget: QWidget | None) -> object | None:
        ...

    def restore_view_state(self, widget: QWidget | None, state: object) -> bool:
        ...


class PlotWidgetPresentationRefresh(Protocol):
    def refresh_after_attach(self, widget: QWidget | None) -> None:
        ...


class PlotWidgetBinderRegistry:
    def __init__(self) -> None:
        self._binders: dict[str, PlotWidgetBinder] = {}

    def register(self, backend_id: str, binder: PlotWidgetBinder) -> None:
        normalized_backend_id = str(backend_id).strip()
        if not normalized_backend_id:
            raise ValueError("plot widget binder backend_id is required")
        self._binders[normalized_backend_id] = binder

    def lookup(self, backend_id: str) -> PlotWidgetBinder | None:
        normalized_backend_id = str(backend_id).strip()
        if not normalized_backend_id:
            return None
        return self._binders.get(normalized_backend_id)

    def resolve(self, backend_id: str) -> PlotWidgetBinder:
        normalized_backend_id = str(backend_id).strip()
        if not normalized_backend_id:
            raise LookupError("plot widget binder backend_id is required")
        binder = self.lookup(normalized_backend_id)
        if binder is None:
            raise LookupError(f"Unknown plot widget binder backend: {normalized_backend_id!r}.")
        return binder


@dataclass(slots=True)
class _MatplotlibWidgetState:
    backend_id: str
    node_id: str = ""
    plot_type: str = ""
    render_revision: int = 0


class MatplotlibPlotWidgetBinder:
    backend_id = MATPLOTLIB_PLOT_BACKEND_ID

    def __init__(
        self,
        *,
        backend_factory: Callable[[], MatplotlibLive2DPlotBackend] | None = None,
        widget_factory: Callable[[QWidget | None], QWidget] | None = None,
    ) -> None:
        self._backend_factory = backend_factory or MatplotlibLive2DPlotBackend
        self._widget_factory = widget_factory
        self._widget_state: WeakKeyDictionary[QWidget, _MatplotlibWidgetState] = WeakKeyDictionary()

    def bind_widget(self, request: PlotWidgetBindRequest) -> QWidget:
        backend = self._backend_factory()
        widget = self._resolve_widget(request, backend=backend)
        try:
            backend.render_widget(widget, request.render_request)
        except RuntimeError as exc:
            raise PlotWidgetNoBind(str(exc)) from exc
        self._widget_state[widget] = _MatplotlibWidgetState(
            backend_id=self.backend_id,
            node_id=request.node_id,
            plot_type=request.plot_type,
            render_revision=int(request.render_revision),
        )
        return widget

    def release_widget(self, request: PlotWidgetReleaseRequest) -> None:
        widget = request.widget
        if not self._is_reusable_canvas(widget):
            return
        self._clear_canvas(widget)
        widget.setProperty("ea.plotLiveOverlay", False)
        self._widget_state[widget] = _MatplotlibWidgetState(backend_id=self.backend_id)

    def capture_preview_image(self, widget: QWidget | None) -> QImage:
        if not isinstance(widget, QWidget):
            return QImage()
        try:
            pixmap = widget.grab()
        except Exception:  # noqa: BLE001
            return QImage()
        if pixmap.isNull():
            return QImage()
        image = pixmap.toImage()
        return image.copy() if not image.isNull() else QImage()

    def refresh_after_attach(self, widget: QWidget | None) -> None:
        if not self._is_reusable_canvas(widget):
            return
        draw_idle = getattr(widget, "draw_idle", None)
        if callable(draw_idle):
            try:
                draw_idle()
            except Exception:  # noqa: BLE001
                pass

    def _resolve_widget(self, request: PlotWidgetBindRequest, *, backend: MatplotlibLive2DPlotBackend) -> QWidget:
        current_widget = request.current_widget
        if self._is_reusable_canvas(current_widget):
            if request.container is not None and current_widget.parent() is not request.container:
                current_widget.setParent(request.container)
            self._mark_live_overlay(current_widget)
            return current_widget
        if self._widget_factory is not None:
            widget = self._widget_factory(request.container)
        else:
            widget = backend.create_widget(request.container)
        if not isinstance(widget, QWidget):
            raise TypeError("matplotlib plot widget factory must return a QWidget instance.")
        if request.container is not None and widget.parent() is not request.container:
            widget.setParent(request.container)
        self._mark_live_overlay(widget)
        self._widget_state[widget] = _MatplotlibWidgetState(backend_id=self.backend_id)
        return widget

    def _is_reusable_canvas(self, widget: QWidget | None) -> bool:
        if not isinstance(widget, QWidget):
            return False
        state = self._widget_state.get(widget)
        return state is not None and state.backend_id == self.backend_id

    @staticmethod
    def _clear_canvas(widget: QWidget) -> None:
        figure = getattr(widget, "figure", None)
        clear = getattr(figure, "clear", None)
        if callable(clear):
            try:
                clear()
            except Exception:  # noqa: BLE001
                pass
        draw_idle = getattr(widget, "draw_idle", None)
        if callable(draw_idle):
            try:
                draw_idle()
            except Exception:  # noqa: BLE001
                pass

    @staticmethod
    def _mark_live_overlay(widget: QWidget) -> None:
        widget.setProperty("ea.plotLiveOverlay", True)


@dataclass(slots=True)
class _PyQtGraphWidgetState:
    backend_id: str
    node_id: str = ""
    plot_type: str = ""
    render_revision: int = 0


class PyQtGraphPlotWidgetBinder:
    backend_id = PYQTGRAPH_PLOT_BACKEND_ID

    def __init__(
        self,
        *,
        backend_factory: Callable[[], PyQtGraphLive2DPlotBackend] | None = None,
        widget_factory: Callable[[QWidget | None], QWidget] | None = None,
    ) -> None:
        self._backend_factory = backend_factory or PyQtGraphLive2DPlotBackend
        self._widget_factory = widget_factory
        self._widget_state: WeakKeyDictionary[QWidget, _PyQtGraphWidgetState] = WeakKeyDictionary()

    def bind_widget(self, request: PlotWidgetBindRequest) -> QWidget:
        backend = self._backend_factory()
        widget = self._resolve_widget(request, backend=backend)
        try:
            backend.render_widget(widget, request.render_request)
        except RuntimeError as exc:
            raise PlotWidgetNoBind(str(exc)) from exc
        self._widget_state[widget] = _PyQtGraphWidgetState(
            backend_id=self.backend_id,
            node_id=request.node_id,
            plot_type=request.plot_type,
            render_revision=int(request.render_revision),
        )
        return widget

    def release_widget(self, request: PlotWidgetReleaseRequest) -> None:
        widget = request.widget
        if not self._is_reusable_plot_widget(widget):
            return
        clear = getattr(widget, "clear", None)
        if callable(clear):
            clear()
        widget.setProperty("ea.plotLiveOverlay", False)
        self._widget_state[widget] = _PyQtGraphWidgetState(backend_id=self.backend_id)

    def capture_preview_image(self, widget: QWidget | None) -> QImage:
        if not isinstance(widget, QWidget):
            return QImage()
        try:
            pixmap = widget.grab()
        except Exception:  # noqa: BLE001
            return QImage()
        if pixmap.isNull():
            return QImage()
        image = pixmap.toImage()
        return image.copy() if not image.isNull() else QImage()

    def capture_view_state(self, widget: QWidget | None) -> object | None:
        view_box = self._view_box(widget)
        if view_box is None:
            return None
        get_state = getattr(view_box, "getState", None)
        if callable(get_state):
            try:
                try:
                    state = get_state(copy=True)
                except TypeError:
                    state = get_state()
            except Exception:  # noqa: BLE001
                return None
            return {"kind": "pyqtgraph_viewbox", "state": copy.deepcopy(state)}
        view_range = getattr(view_box, "viewRange", None)
        if callable(view_range):
            try:
                ranges = view_range()
            except Exception:  # noqa: BLE001
                return None
            return {"kind": "pyqtgraph_ranges", "ranges": copy.deepcopy(ranges)}
        return None

    def restore_view_state(self, widget: QWidget | None, state: object) -> bool:
        view_box = self._view_box(widget)
        if view_box is None or not isinstance(state, Mapping):
            return False
        if state.get("kind") == "pyqtgraph_viewbox":
            set_state = getattr(view_box, "setState", None)
            if callable(set_state):
                try:
                    set_state(copy.deepcopy(state.get("state")))
                except Exception:  # noqa: BLE001
                    return False
                return True
        ranges = state.get("ranges")
        stored_state = state.get("state")
        if ranges is None and isinstance(stored_state, Mapping):
            ranges = stored_state.get("viewRange")
        if not isinstance(ranges, (list, tuple)) or len(ranges) < 2:
            return False
        set_range = getattr(view_box, "setRange", None)
        if not callable(set_range):
            return False
        try:
            set_range(xRange=tuple(ranges[0]), yRange=tuple(ranges[1]), padding=0.0)
        except Exception:  # noqa: BLE001
            return False
        return True

    def _resolve_widget(self, request: PlotWidgetBindRequest, *, backend: PyQtGraphLive2DPlotBackend) -> QWidget:
        current_widget = request.current_widget
        if self._is_reusable_plot_widget(current_widget):
            if request.container is not None and current_widget.parent() is not request.container:
                current_widget.setParent(request.container)
            self._mark_live_overlay(current_widget)
            return current_widget
        if self._widget_factory is not None:
            widget = self._widget_factory(request.container)
        else:
            widget = backend.create_widget(request.container)
        if not isinstance(widget, QWidget):
            raise TypeError("plot widget factory must return a QWidget instance.")
        if request.container is not None and widget.parent() is not request.container:
            widget.setParent(request.container)
        self._mark_live_overlay(widget)
        self._widget_state[widget] = _PyQtGraphWidgetState(backend_id=self.backend_id)
        return widget

    def _is_reusable_plot_widget(self, widget: QWidget | None) -> bool:
        if not isinstance(widget, QWidget):
            return False
        state = self._widget_state.get(widget)
        return state is not None and state.backend_id == self.backend_id

    @staticmethod
    def _mark_live_overlay(widget: QWidget) -> None:
        widget.setProperty("ea.plotLiveOverlay", True)

    @staticmethod
    def _view_box(widget: QWidget | None) -> object | None:
        if not isinstance(widget, QWidget):
            return None
        get_plot_item = getattr(widget, "getPlotItem", None)
        plot_item = get_plot_item() if callable(get_plot_item) else None
        get_view_box = getattr(plot_item, "getViewBox", None) if plot_item is not None else None
        if callable(get_view_box):
            return get_view_box()
        get_view_box = getattr(widget, "getViewBox", None)
        return get_view_box() if callable(get_view_box) else None


@dataclass(slots=True)
class _PyVistaWidgetState:
    backend_id: str
    node_id: str = ""
    plot_type: str = ""
    render_revision: int = 0


class PyVistaPlotWidgetBinder:
    backend_id = PYVISTA_PLOT_BACKEND_ID

    def __init__(
        self,
        *,
        backend_factory: Callable[[], PyVistaLive3DPlotBackend] | None = None,
        interactor_factory: Callable[[QWidget | None], QWidget] | None = None,
    ) -> None:
        self._backend_factory = backend_factory or PyVistaLive3DPlotBackend
        self._interactor_factory = interactor_factory
        self._widget_state: WeakKeyDictionary[QWidget, _PyVistaWidgetState] = WeakKeyDictionary()

    def bind_widget(self, request: PlotWidgetBindRequest) -> QWidget:
        backend = self._backend_factory()
        widget = self._resolve_widget(request, backend=backend)
        try:
            backend.render_widget(widget, request.render_request)
        except RuntimeError as exc:
            raise PlotWidgetNoBind(str(exc)) from exc
        self._widget_state[widget] = _PyVistaWidgetState(
            backend_id=self.backend_id,
            node_id=request.node_id,
            plot_type=request.plot_type,
            render_revision=int(request.render_revision),
        )
        return widget

    def release_widget(self, request: PlotWidgetReleaseRequest) -> None:
        widget = request.widget
        if not self._is_reusable_interactor(widget):
            return
        self._finalize_interactor(widget)
        widget.setProperty("ea.plotLiveOverlay", False)
        self._widget_state[widget] = _PyVistaWidgetState(backend_id="")

    def capture_preview_image(self, widget: QWidget | None) -> QImage:
        if not self._is_reusable_interactor(widget):
            return QImage()
        render = getattr(widget, "render", None)
        if callable(render):
            try:
                render()
            except Exception:  # noqa: BLE001
                return QImage()
        screenshot = getattr(widget, "screenshot", None)
        if not callable(screenshot):
            return QImage()
        try:
            captured = screenshot(return_img=True)
        except Exception:  # noqa: BLE001
            return QImage()
        return self._qimage_from_screenshot(captured)

    def refresh_after_attach(self, widget: QWidget | None) -> None:
        if not self._is_reusable_interactor(widget):
            return
        render = getattr(widget, "render", None)
        if callable(render):
            try:
                render()
            except Exception:  # noqa: BLE001
                pass
        update = getattr(widget, "update", None)
        if callable(update):
            try:
                update()
            except Exception:  # noqa: BLE001
                pass

    def capture_view_state(self, widget: QWidget | None) -> object | None:
        if not self._is_reusable_interactor(widget):
            return None
        state: dict[str, Any] = {}
        try:
            camera_position = getattr(widget, "camera_position")
        except Exception:  # noqa: BLE001
            camera_position = None
        if camera_position is not None:
            state["camera_position"] = copy.deepcopy(camera_position)
        camera = getattr(widget, "camera", None)
        if camera is not None:
            camera_state = {
                "position": self._camera_value(camera, "position", "GetPosition"),
                "focal_point": self._camera_value(camera, "focal_point", "GetFocalPoint"),
                "view_up": self._camera_value(camera, "view_up", "GetViewUp"),
                "clipping_range": self._camera_value(camera, "clipping_range", "GetClippingRange"),
                "parallel_scale": self._camera_value(camera, "parallel_scale", "GetParallelScale"),
                "parallel_projection": self._camera_value(camera, "parallel_projection", "GetParallelProjection"),
            }
            state["camera"] = {
                key: copy.deepcopy(value)
                for key, value in camera_state.items()
                if value is not None
            }
        return {"kind": "pyvista_camera", "state": state} if state else None

    def restore_view_state(self, widget: QWidget | None, state: object) -> bool:
        if not self._is_reusable_interactor(widget) or not isinstance(state, Mapping):
            return False
        if state.get("kind") != "pyvista_camera" or not isinstance(state.get("state"), Mapping):
            return False
        restored = False
        saved_state = state["state"]
        if "camera_position" in saved_state:
            try:
                setattr(widget, "camera_position", copy.deepcopy(saved_state["camera_position"]))
            except Exception:  # noqa: BLE001
                pass
            else:
                restored = True
        camera_state = saved_state.get("camera")
        camera = getattr(widget, "camera", None)
        if camera is not None and isinstance(camera_state, Mapping):
            restored = self._restore_camera_values(camera, camera_state) or restored
        if restored:
            render = getattr(widget, "render", None)
            if callable(render):
                try:
                    render()
                except Exception:  # noqa: BLE001
                    pass
        return restored

    def _resolve_widget(self, request: PlotWidgetBindRequest, *, backend: PyVistaLive3DPlotBackend) -> QWidget:
        current_widget = request.current_widget
        if self._is_reusable_interactor(current_widget):
            if request.container is not None and current_widget.parent() is not request.container:
                current_widget.setParent(request.container)
            self._mark_live_overlay(current_widget)
            return current_widget
        if self._interactor_factory is not None:
            widget = self._interactor_factory(request.container)
        else:
            widget = backend.create_widget(request.container)
        if not isinstance(widget, QWidget):
            raise TypeError("PyVista plot interactor factory must return a QWidget instance.")
        if request.container is not None and widget.parent() is not request.container:
            widget.setParent(request.container)
        self._mark_live_overlay(widget)
        self._widget_state[widget] = _PyVistaWidgetState(backend_id=self.backend_id)
        return widget

    def _is_reusable_interactor(self, widget: QWidget | None) -> bool:
        if not isinstance(widget, QWidget):
            return False
        state = self._widget_state.get(widget)
        return state is not None and state.backend_id == self.backend_id

    @staticmethod
    def _mark_live_overlay(widget: QWidget) -> None:
        widget.setProperty("ea.plotLiveOverlay", True)

    @staticmethod
    def _finalize_interactor(widget: QWidget) -> None:
        finalize = getattr(widget, "Finalize", None)
        if callable(finalize):
            try:
                finalize()
            except Exception:  # noqa: BLE001
                pass
        close = getattr(widget, "close", None)
        if callable(close):
            try:
                close()
            except Exception:  # noqa: BLE001
                pass

    @staticmethod
    def _qimage_from_screenshot(captured: Any) -> QImage:
        if isinstance(captured, QImage):
            return captured.copy()
        if captured is None:
            return QImage()
        shape = getattr(captured, "shape", None)
        if not shape or len(shape) < 2:
            return QImage()
        try:
            height = int(shape[0])
            width = int(shape[1])
            channels = int(shape[2]) if len(shape) >= 3 else 1
        except (TypeError, ValueError):
            return QImage()
        if width <= 0 or height <= 0:
            return QImage()

        dtype = getattr(captured, "dtype", None)
        itemsize = getattr(dtype, "itemsize", 1)
        try:
            if int(itemsize) != 1:
                return QImage()
        except (TypeError, ValueError):
            return QImage()

        tobytes = getattr(captured, "tobytes", None)
        if not callable(tobytes):
            return QImage()
        try:
            payload = tobytes()
        except Exception:  # noqa: BLE001
            return QImage()

        if channels == 4:
            image_format = QImage.Format.Format_RGBA8888
            bytes_per_line = width * 4
        elif channels == 3:
            image_format = QImage.Format.Format_RGB888
            bytes_per_line = width * 3
        elif channels == 1:
            image_format = QImage.Format.Format_Grayscale8
            bytes_per_line = width
        else:
            return QImage()

        if len(payload) < bytes_per_line * height:
            return QImage()
        image = QImage(payload, width, height, bytes_per_line, image_format)
        if image.isNull():
            return QImage()
        return image.copy()

    @staticmethod
    def _camera_value(camera: object, attribute_name: str, getter_name: str) -> object | None:
        try:
            value = getattr(camera, attribute_name)
        except Exception:  # noqa: BLE001
            value = None
        if value is not None:
            return value
        getter = getattr(camera, getter_name, None)
        if not callable(getter):
            return None
        try:
            return getter()
        except Exception:  # noqa: BLE001
            return None

    @classmethod
    def _restore_camera_values(cls, camera: object, camera_state: Mapping[str, object]) -> bool:
        restored = False
        restored = cls._set_camera_value(camera, "position", "SetPosition", camera_state.get("position")) or restored
        restored = cls._set_camera_value(
            camera,
            "focal_point",
            "SetFocalPoint",
            camera_state.get("focal_point"),
        ) or restored
        restored = cls._set_camera_value(camera, "view_up", "SetViewUp", camera_state.get("view_up")) or restored
        restored = cls._set_camera_value(
            camera,
            "clipping_range",
            "SetClippingRange",
            camera_state.get("clipping_range"),
        ) or restored
        restored = cls._set_camera_value(
            camera,
            "parallel_scale",
            "SetParallelScale",
            camera_state.get("parallel_scale"),
        ) or restored
        return cls._set_camera_value(
            camera,
            "parallel_projection",
            "SetParallelProjection",
            camera_state.get("parallel_projection"),
        ) or restored

    @staticmethod
    def _set_camera_value(camera: object, attribute_name: str, setter_name: str, value: object | None) -> bool:
        if value is None:
            return False
        try:
            setattr(camera, attribute_name, copy.deepcopy(value))
        except Exception:  # noqa: BLE001
            pass
        else:
            return True
        setter = getattr(camera, setter_name, None)
        if not callable(setter):
            return False
        try:
            if isinstance(value, (list, tuple)):
                setter(*value)
            else:
                setter(value)
        except Exception:  # noqa: BLE001
            return False
        return True


__all__ = [
    "MatplotlibPlotWidgetBinder",
    "PlotWidgetBindRequest",
    "PlotWidgetBinder",
    "PlotWidgetBinderRegistry",
    "PlotWidgetNoBind",
    "PlotWidgetPreviewCapture",
    "PlotWidgetReleaseRequest",
    "PlotWidgetViewState",
    "PyQtGraphPlotWidgetBinder",
    "PyVistaPlotWidgetBinder",
]

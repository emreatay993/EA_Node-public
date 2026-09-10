from __future__ import annotations

import copy
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from ea_node_editor.nodes.builtins.data_control import PANEL_TYPE_ID
from ea_node_editor.nodes.builtins.excalidraw import (
    EXCALIDRAW_BOARD_SURFACE_FAMILY,
    EXCALIDRAW_BOARD_SURFACE_VARIANT,
    EXCALIDRAW_BOARD_TYPE_ID,
)
from ea_node_editor.nodes.builtins.media_panel import MEDIA_PANEL_TYPE_ID
from ea_node_editor.nodes.builtins.passive_mail import PASSIVE_MEDIA_MAIL_PANEL_TYPE_ID
from ea_node_editor.nodes.builtins.jupyter_notebook import (
    JUPYTER_NOTEBOOK_SURFACE_FAMILY,
    JUPYTER_NOTEBOOK_SURFACE_VARIANT,
    JUPYTER_NOTEBOOK_TYPE_ID,
)
from ea_node_editor.nodes.builtins.web_viewer import (
    WEB_PAGE_VIEWER_SURFACE_FAMILY,
    WEB_PAGE_VIEWER_SURFACE_VARIANT,
    WEB_PAGE_VIEWER_TYPE_ID,
)
from ea_node_editor.execution.plot_backend import V1_PLOT_TYPES
from ea_node_editor.ui_qml.native_overlay_owners import (
    PLOT_HOST_OVERLAY_OWNER,
    VIEWER_SESSION_OVERLAY_OWNER,
)

if TYPE_CHECKING:
    from ea_node_editor.nodes.node_specs import NodeTypeSpec


@dataclass(frozen=True, slots=True)
class CanvasInputCapabilities:
    devices: tuple[str, ...] = ("mouse",)
    events: tuple[str, ...] = ("press", "release", "move", "wheel")
    hover: bool = True
    pressure: bool = False
    gestures: tuple[str, ...] = ()
    plugin_gestures: tuple[str, ...] = ()

    def to_payload(self) -> dict[str, Any]:
        return {
            "devices": list(self.devices),
            "events": list(self.events),
            "hover": bool(self.hover),
            "pressure": bool(self.pressure),
            "gestures": list(self.gestures),
            "plugin_gestures": list(self.plugin_gestures),
        }


@dataclass(frozen=True, slots=True)
class SurfaceFullscreenPolicy:
    supported: bool = False
    content_kind: str = ""
    action_id: str = "fullscreen"
    action_label: str = "Fullscreen"
    action_icon: str = "fullscreen"
    action_kind: str = "surface"
    requires_bridge: bool = True

    def to_payload(self) -> dict[str, Any]:
        return {
            "supported": bool(self.supported),
            "content_kind": self.content_kind,
            "action_id": self.action_id,
            "action_label": self.action_label,
            "action_icon": self.action_icon,
            "action_kind": self.action_kind,
            "requires_bridge": bool(self.requires_bridge),
        }


@dataclass(frozen=True, slots=True)
class NativeOverlayPolicy:
    required: bool = False
    target: str = ""
    owner: str = ""

    def to_payload(self) -> dict[str, Any]:
        return {
            "required": bool(self.required),
            "target": self.target,
            "owner": self.owner,
        }


@dataclass(frozen=True, slots=True)
class SurfaceLayoutMetrics:
    content_region: str = "host"
    min_body_width: float = 0.0
    min_body_height: float = 0.0
    preferred_body_height: float = 0.0

    def to_payload(self) -> dict[str, Any]:
        return {
            "content_region": self.content_region,
            "min_body_width": float(self.min_body_width),
            "min_body_height": float(self.min_body_height),
            "preferred_body_height": float(self.preferred_body_height),
        }


@dataclass(frozen=True, slots=True)
class SurfaceSpec:
    family: str
    variant: str = ""
    component_key: str = "standard"
    qml_component: str = "GraphStandardNodeSurface.qml"
    fullscreen: SurfaceFullscreenPolicy = field(default_factory=SurfaceFullscreenPolicy)
    input_capabilities: CanvasInputCapabilities = field(default_factory=CanvasInputCapabilities)
    native_overlay: NativeOverlayPolicy = field(default_factory=NativeOverlayPolicy)
    layout: SurfaceLayoutMetrics = field(default_factory=SurfaceLayoutMetrics)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        return {
            "family": self.family,
            "variant": self.variant,
            "component_key": self.component_key,
            "qml_component": self.qml_component,
            "fullscreen": self.fullscreen.to_payload(),
            "input_capabilities": self.input_capabilities.to_payload(),
            "native_overlay": self.native_overlay.to_payload(),
            "layout": self.layout.to_payload(),
            "metadata": copy.deepcopy(dict(self.metadata)),
        }


_BASIC_CANVAS_INPUT = CanvasInputCapabilities(
    devices=("mouse", "touch"),
    events=("press", "release", "move", "wheel"),
    hover=True,
    gestures=("tap", "drag", "wheel"),
)
_RICH_CANVAS_INPUT = CanvasInputCapabilities(
    devices=("mouse", "touch", "stylus"),
    events=("press", "release", "move", "wheel", "hover"),
    hover=True,
    pressure=False,
    gestures=("tap", "drag", "wheel", "pinch"),
)
_VIEWER_CANVAS_INPUT = CanvasInputCapabilities(
    devices=("mouse", "touch", "stylus"),
    events=("press", "release", "move", "wheel", "hover"),
    hover=True,
    pressure=False,
    gestures=("orbit", "pan", "zoom", "select"),
    plugin_gestures=("viewer.pluginGesture",),
)
_PLOT_CANVAS_INPUT = CanvasInputCapabilities(
    devices=("mouse", "touch", "stylus"),
    events=("press", "release", "move", "wheel", "hover"),
    hover=True,
    pressure=False,
    gestures=("pan", "zoom", "select", "hover"),
    plugin_gestures=("plot.pluginGesture",),
)
_WEB_CANVAS_INPUT = CanvasInputCapabilities(
    devices=("mouse", "touch", "stylus"),
    events=("press", "release", "move", "wheel", "hover"),
    hover=True,
    pressure=True,
    gestures=("draw", "pan", "zoom"),
    plugin_gestures=("webSurface.pluginGesture", "stylusPlugin.pressureStroke"),
)
_TABULAR_CANVAS_INPUT = CanvasInputCapabilities(
    devices=("mouse", "touch"),
    events=("press", "release", "move", "wheel", "key"),
    hover=True,
    gestures=("tap", "drag", "wheel"),
)
_WEB_PAGE_CANVAS_INPUT = CanvasInputCapabilities(
    devices=("mouse", "touch"),
    events=("press", "release", "move", "wheel", "key"),
    hover=True,
    gestures=("tap", "drag", "wheel"),
)
_TABULAR_BODY_LAYOUT = SurfaceLayoutMetrics(
    content_region="body",
    min_body_width=320.0,
    min_body_height=154.0,
    preferred_body_height=164.0,
)
_WEB_PAGE_BODY_LAYOUT = SurfaceLayoutMetrics(
    content_region="body",
    min_body_width=260.0,
    min_body_height=150.0,
    preferred_body_height=260.0,
)
_JUPYTER_BODY_LAYOUT = SurfaceLayoutMetrics(
    content_region="body",
    min_body_width=320.0,
    min_body_height=240.0,
    preferred_body_height=420.0,
)
_PLOT_BODY_LAYOUT = SurfaceLayoutMetrics(
    content_region="host",
    min_body_width=300.0,
    min_body_height=180.0,
    preferred_body_height=220.0,
)
def _plot_surface_spec(plot_type: str) -> SurfaceSpec:
    return SurfaceSpec(
        family="plot",
        variant=str(plot_type or "").strip(),
        component_key="plot",
        qml_component="plot/GraphPlotSurface.qml",
        fullscreen=SurfaceFullscreenPolicy(
            supported=True,
            content_kind="plot",
            action_kind="plot",
        ),
        input_capabilities=_PLOT_CANVAS_INPUT,
        native_overlay=NativeOverlayPolicy(required=True, target="body", owner=PLOT_HOST_OVERLAY_OWNER),
        layout=_PLOT_BODY_LAYOUT,
        metadata={"live_2d_backend": "pyqtgraph"},
    )


_STANDARD_SURFACE = SurfaceSpec(
    family="standard",
    component_key="standard",
    qml_component="GraphStandardNodeSurface.qml",
    input_capabilities=_BASIC_CANVAS_INPUT,
)
_MEDIA_PANEL_SURFACE = SurfaceSpec(
    family="media",
    variant="media_panel",
    component_key="media",
    qml_component="passive/GraphMediaPanelSurface.qml",
    fullscreen=SurfaceFullscreenPolicy(
        supported=True,
        content_kind="media",
        action_kind="media",
    ),
    input_capabilities=_RICH_CANVAS_INPUT,
    metadata={"panel_like": True, "suppress_run_action": True},
)
_SURFACE_SPECS_BY_FAMILY: dict[str, SurfaceSpec] = {
    "standard": _STANDARD_SURFACE,
    "flowchart": SurfaceSpec(
        family="flowchart",
        component_key="flowchart",
        qml_component="passive/GraphFlowchartNodeSurface.qml",
        input_capabilities=_BASIC_CANVAS_INPUT,
    ),
    "planning": SurfaceSpec(
        family="planning",
        component_key="planning",
        qml_component="passive/GraphPlanningCardSurface.qml",
        input_capabilities=_BASIC_CANVAS_INPUT,
    ),
    "annotation": SurfaceSpec(
        family="annotation",
        component_key="annotation",
        qml_component="passive/GraphAnnotationNoteSurface.qml",
        input_capabilities=_BASIC_CANVAS_INPUT,
    ),
    "group_backdrop": SurfaceSpec(
        family="group_backdrop",
        variant="group_backdrop",
        component_key="group_backdrop",
        qml_component="passive/GraphGroupBackdropSurface.qml",
        input_capabilities=_BASIC_CANVAS_INPUT,
    ),
    "media": _MEDIA_PANEL_SURFACE,
    "viewer": SurfaceSpec(
        family="viewer",
        component_key="viewer",
        qml_component="viewer/GraphViewerSurface.qml",
        fullscreen=SurfaceFullscreenPolicy(
            supported=True,
            content_kind="viewer",
            action_kind="viewer",
        ),
        input_capabilities=_VIEWER_CANVAS_INPUT,
        native_overlay=NativeOverlayPolicy(required=True, target="body", owner=VIEWER_SESSION_OVERLAY_OWNER),
    ),
    "plot": _plot_surface_spec("line"),
}
_PLOT_SURFACE_SPECS_BY_VARIANT = {
    ("plot", plot_type): _plot_surface_spec(plot_type)
    for plot_type in V1_PLOT_TYPES
}
_SURFACE_SPECS_BY_FAMILY_VARIANT: dict[tuple[str, str], SurfaceSpec] = {
    **_PLOT_SURFACE_SPECS_BY_VARIANT,
    ("annotation", "text"): SurfaceSpec(
        family="annotation",
        variant="text",
        component_key="annotation_text",
        qml_component="passive/GraphBareTextSurface.qml",
        input_capabilities=_BASIC_CANVAS_INPUT,
        metadata={"bare_text": True},
    ),
    ("media", "media_panel"): _MEDIA_PANEL_SURFACE,
    ("media", "mail_panel"): SurfaceSpec(
        family="media",
        variant="mail_panel",
        component_key="media_mail",
        qml_component="passive/GraphMailPanelSurface.qml",
        fullscreen=SurfaceFullscreenPolicy(
            supported=True,
            content_kind="mail",
            action_kind="media",
        ),
        input_capabilities=_RICH_CANVAS_INPUT,
        metadata={"media_kind": "mail"},
    ),
    (EXCALIDRAW_BOARD_SURFACE_FAMILY, EXCALIDRAW_BOARD_SURFACE_VARIANT): SurfaceSpec(
        family=EXCALIDRAW_BOARD_SURFACE_FAMILY,
        variant=EXCALIDRAW_BOARD_SURFACE_VARIANT,
        component_key="web_excalidraw_board",
        qml_component="passive/GraphWebBoardSurface.qml",
        fullscreen=SurfaceFullscreenPolicy(
            supported=True,
            content_kind="web_editor",
            action_kind="web_board",
        ),
        input_capabilities=_WEB_CANVAS_INPUT,
        metadata={"web_surface": "excalidraw"},
    ),
    (WEB_PAGE_VIEWER_SURFACE_FAMILY, WEB_PAGE_VIEWER_SURFACE_VARIANT): SurfaceSpec(
        family=WEB_PAGE_VIEWER_SURFACE_FAMILY,
        variant=WEB_PAGE_VIEWER_SURFACE_VARIANT,
        component_key="web_page",
        qml_component="../web/WebPageHost.qml",
        fullscreen=SurfaceFullscreenPolicy(
            supported=True,
            content_kind="web_page",
            action_kind="web_page",
        ),
        input_capabilities=_WEB_PAGE_CANVAS_INPUT,
        layout=_WEB_PAGE_BODY_LAYOUT,
        metadata={
            "web_surface": WEB_PAGE_VIEWER_SURFACE_VARIANT,
            "qwebchannel_allowed": False,
        },
    ),
    (JUPYTER_NOTEBOOK_SURFACE_FAMILY, JUPYTER_NOTEBOOK_SURFACE_VARIANT): SurfaceSpec(
        family=JUPYTER_NOTEBOOK_SURFACE_FAMILY,
        variant=JUPYTER_NOTEBOOK_SURFACE_VARIANT,
        component_key="jupyter_notebook",
        qml_component="jupyter/GraphJupyterNotebookSurface.qml",
        fullscreen=SurfaceFullscreenPolicy(
            supported=True,
            content_kind="jupyter_notebook",
            action_kind="surface",
        ),
        input_capabilities=_WEB_PAGE_CANVAS_INPUT,
        layout=_JUPYTER_BODY_LAYOUT,
        metadata={
            "web_surface": "jupyter_notebook",
            "qwebchannel_allowed": False,
        },
    ),
}
_SURFACE_SPECS_BY_TYPE_ID: dict[str, SurfaceSpec] = {
    **{
        f"plot.{plot_type}": spec
        for (_family, plot_type), spec in _PLOT_SURFACE_SPECS_BY_VARIANT.items()
    },
    MEDIA_PANEL_TYPE_ID: _SURFACE_SPECS_BY_FAMILY_VARIANT[("media", "media_panel")],
    PASSIVE_MEDIA_MAIL_PANEL_TYPE_ID: _SURFACE_SPECS_BY_FAMILY_VARIANT[("media", "mail_panel")],
    EXCALIDRAW_BOARD_TYPE_ID: _SURFACE_SPECS_BY_FAMILY_VARIANT[
        (EXCALIDRAW_BOARD_SURFACE_FAMILY, EXCALIDRAW_BOARD_SURFACE_VARIANT)
    ],
    WEB_PAGE_VIEWER_TYPE_ID: _SURFACE_SPECS_BY_FAMILY_VARIANT[
        (WEB_PAGE_VIEWER_SURFACE_FAMILY, WEB_PAGE_VIEWER_SURFACE_VARIANT)
    ],
    JUPYTER_NOTEBOOK_TYPE_ID: _SURFACE_SPECS_BY_FAMILY_VARIANT[
        (JUPYTER_NOTEBOOK_SURFACE_FAMILY, JUPYTER_NOTEBOOK_SURFACE_VARIANT)
    ],
    PANEL_TYPE_ID: SurfaceSpec(
        family="standard",
        variant="panel",
        component_key="panel",
        qml_component="passive/GraphPanelSurface.qml",
        input_capabilities=_BASIC_CANVAS_INPUT,
        layout=SurfaceLayoutMetrics(
            content_region="host",
            min_body_width=120.0,
            min_body_height=40.0,
            preferred_body_height=180.0,
        ),
    ),
    "core.python_script": SurfaceSpec(
        family="standard",
        component_key="standard",
        qml_component="GraphStandardNodeSurface.qml",
        fullscreen=SurfaceFullscreenPolicy(
            supported=True,
            content_kind="script_editor",
            action_label="Open script",
            action_icon="code",
            action_kind="surface",
        ),
        input_capabilities=_BASIC_CANVAS_INPUT,
    ),
    "io.folder_explorer": SurfaceSpec(
        family="standard",
        component_key="native_explorer",
        qml_component="passive/GraphNativeExplorerSurface.qml",
        input_capabilities=_RICH_CANVAS_INPUT,
        metadata={"native_surface": "folder_explorer"},
    ),
    "data.number_slider": SurfaceSpec(
        family="standard",
        variant="number_slider",
        component_key="number_slider",
        qml_component="passive/GraphNumberSliderSurface.qml",
        input_capabilities=_BASIC_CANVAS_INPUT,
    ),
    "data.select": SurfaceSpec(
        family="standard",
        variant="select",
        component_key="select",
        qml_component="passive/GraphSelectSurface.qml",
        input_capabilities=_BASIC_CANVAS_INPUT,
    ),
    "data.boolean_toggle": SurfaceSpec(
        family="standard",
        variant="boolean_toggle",
        component_key="boolean_toggle",
        qml_component="passive/GraphBooleanToggleSurface.qml",
        input_capabilities=_BASIC_CANVAS_INPUT,
    ),
    "core.trigger": SurfaceSpec(
        family="standard",
        variant="trigger",
        component_key="trigger",
        qml_component="passive/GraphTriggerSurface.qml",
        input_capabilities=_BASIC_CANVAS_INPUT,
    ),
    "tabular.input": SurfaceSpec(
        family="standard",
        component_key="tabular",
        qml_component="tabular/GraphTabularPreviewSurface.qml",
        fullscreen=SurfaceFullscreenPolicy(
            supported=True,
            content_kind="tabular",
            action_kind="tabular",
        ),
        input_capabilities=_TABULAR_CANVAS_INPUT,
        layout=_TABULAR_BODY_LAYOUT,
        metadata={"tabular_preview": True},
    ),
}


def surface_spec_for_values(
    *,
    type_id: object = "",
    family: object = "standard",
    variant: object = "",
) -> SurfaceSpec:
    normalized_type_id = str(type_id or "").strip()
    if normalized_type_id in _SURFACE_SPECS_BY_TYPE_ID:
        return _SURFACE_SPECS_BY_TYPE_ID[normalized_type_id]

    normalized_family = str(family or "standard").strip() or "standard"
    normalized_variant = str(variant or "").strip()
    variant_spec = _SURFACE_SPECS_BY_FAMILY_VARIANT.get((normalized_family, normalized_variant))
    if variant_spec is not None:
        return variant_spec
    return _SURFACE_SPECS_BY_FAMILY.get(normalized_family, _STANDARD_SURFACE)


def surface_spec_for_node_type(
    *,
    type_id: object,
    spec: "NodeTypeSpec",
) -> SurfaceSpec:
    return surface_spec_for_values(
        type_id=type_id,
        family=getattr(spec, "surface_family", "standard"),
        variant=getattr(spec, "surface_variant", ""),
    )


def surface_spec_payload_for_values(
    *,
    type_id: object = "",
    family: object = "standard",
    variant: object = "",
) -> dict[str, Any]:
    return surface_spec_for_values(type_id=type_id, family=family, variant=variant).to_payload()


def surface_spec_payload_for_node_type(
    *,
    type_id: object,
    spec: "NodeTypeSpec",
) -> dict[str, Any]:
    return surface_spec_for_node_type(type_id=type_id, spec=spec).to_payload()


def fullscreen_content_kind_for_node_type(
    *,
    type_id: object,
    spec: "NodeTypeSpec",
) -> str:
    return surface_spec_for_node_type(type_id=type_id, spec=spec).fullscreen.content_kind


__all__ = [
    "CanvasInputCapabilities",
    "NativeOverlayPolicy",
    "SurfaceFullscreenPolicy",
    "SurfaceLayoutMetrics",
    "SurfaceSpec",
    "fullscreen_content_kind_for_node_type",
    "surface_spec_for_node_type",
    "surface_spec_for_values",
    "surface_spec_payload_for_node_type",
    "surface_spec_payload_for_values",
]

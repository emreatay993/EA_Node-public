from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from urllib.parse import parse_qs, urlencode

from PyQt6.QtCore import QObject, QRectF, QSize, Qt, pyqtSlot
from PyQt6.QtGui import QColor, QIcon, QImage, QPainter, QPixmap
from PyQt6.QtQuick import QQuickImageProvider
from PyQt6.QtSvg import QSvgRenderer

UI_ICON_PROVIDER_ID = "ui-icons"
DEFAULT_ICON_COLOR = "#D8DEEA"
DEFAULT_ICON_SIZE = 16


@dataclass(frozen=True, slots=True)
class IconSpec:
    name: str
    label: str
    relative_path: str
    default_size: int = DEFAULT_ICON_SIZE
    tintable: bool = True


_ICON_ROOT = Path(__file__).resolve().parents[1] / "ui_qml" / "components" / "shell" / "icons"
_ICON_SPECS: dict[str, IconSpec] = {
    "comment": IconSpec(name="comment", label="Comment", relative_path="comment.svg"),
    "code": IconSpec(name="code", label="Code", relative_path="code.svg"),
    "crop": IconSpec(name="crop", label="Crop", relative_path="crop.svg"),
    "delete": IconSpec(name="delete", label="Delete", relative_path="delete.svg"),
    "duplicate": IconSpec(name="duplicate", label="Duplicate", relative_path="duplicate.svg"),
    "copy": IconSpec(name="copy", label="Copy", relative_path="duplicate.svg"),
    "edit": IconSpec(name="edit", label="Edit", relative_path="edit.svg"),
    "filter": IconSpec(name="filter", label="Filter", relative_path="filter.svg"),
    "palette": IconSpec(name="palette", label="Palette", relative_path="palette.svg"),
    "text-decrease": IconSpec(name="text-decrease", label="Decrease Text Size", relative_path="text-decrease.svg"),
    "text-increase": IconSpec(name="text-increase", label="Increase Text Size", relative_path="text-increase.svg"),
    "fit-width": IconSpec(name="fit-width", label="Fit Width", relative_path="fit-width.svg"),
    "fit-height": IconSpec(name="fit-height", label="Fit Height", relative_path="fit-height.svg"),
    "format-bold-italic": IconSpec(
        name="format-bold-italic",
        label="Bold Italic",
        relative_path="format-bold-italic.svg",
    ),
    "format-bold": IconSpec(name="format-bold", label="Bold", relative_path="format-bold.svg"),
    "format-italic": IconSpec(name="format-italic", label="Italic", relative_path="format-italic.svg"),
    "format-underline": IconSpec(name="format-underline", label="Underline", relative_path="format-underline.svg"),
    "format-strikethrough": IconSpec(
        name="format-strikethrough",
        label="Strikethrough",
        relative_path="format-strikethrough.svg",
    ),
    "format-align-left": IconSpec(name="format-align-left", label="Align Left", relative_path="format-align-left.svg"),
    "format-align-center": IconSpec(name="format-align-center", label="Align Center", relative_path="format-align-center.svg"),
    "format-align-right": IconSpec(name="format-align-right", label="Align Right", relative_path="format-align-right.svg"),
    "format-align-justify": IconSpec(name="format-align-justify", label="Justify", relative_path="format-align-justify.svg"),
    "format-list-bulleted": IconSpec(
        name="format-list-bulleted",
        label="Bulleted List",
        relative_path="format-list-bulleted.svg",
    ),
    "format-list-numbered": IconSpec(
        name="format-list-numbered",
        label="Numbered List",
        relative_path="format-list-numbered.svg",
    ),
    "text-wrap": IconSpec(name="text-wrap", label="Wrap Text", relative_path="text-wrap.svg"),
    "text-color": IconSpec(name="text-color", label="Text Color", relative_path="text-color.svg"),
    "color-picker": IconSpec(name="color-picker", label="Pick Color", relative_path="color-picker.svg"),
    "circle-filled": IconSpec(name="circle-filled", label="Color Swatch", relative_path="circle-filled.svg"),
    "copy-text-style": IconSpec(
        name="copy-text-style",
        label="Copy Text Style",
        relative_path="copy-text-style.svg",
    ),
    "paste-text-style": IconSpec(
        name="paste-text-style",
        label="Paste Text Style",
        relative_path="paste-text-style.svg",
    ),
    "arrow-right": IconSpec(name="arrow-right", label="Arrow Right", relative_path="arrow-right.svg"),
    "navigate": IconSpec(name="navigate", label="Navigate", relative_path="navigate.svg"),
    "navigate-previous": IconSpec(
        name="navigate-previous",
        label="Previous Page",
        relative_path="navigate-previous.svg",
    ),
    "navigate-next": IconSpec(name="navigate-next", label="Next Page", relative_path="navigate-next.svg"),
    "path-style": IconSpec(name="path-style", label="Path Style", relative_path="path-style.svg"),
    "edge-path-solid": IconSpec(name="edge-path-solid", label="Solid Path", relative_path="edge-path-solid.svg"),
    "edge-path-dashed": IconSpec(name="edge-path-dashed", label="Dashed Path", relative_path="edge-path-dashed.svg"),
    "edge-path-dotted": IconSpec(name="edge-path-dotted", label="Dotted Path", relative_path="edge-path-dotted.svg"),
    "edge-arrow-filled": IconSpec(name="edge-arrow-filled", label="Filled Arrow", relative_path="edge-arrow-filled.svg"),
    "edge-arrow-open": IconSpec(name="edge-arrow-open", label="Open Arrow", relative_path="edge-arrow-open.svg"),
    "edge-arrow-none": IconSpec(name="edge-arrow-none", label="No Arrow", relative_path="edge-arrow-none.svg"),
    "label-off": IconSpec(name="label-off", label="Remove Label", relative_path="label-off.svg"),
    "fullscreen": IconSpec(name="fullscreen", label="Fullscreen", relative_path="fullscreen.svg"),
    "content-only": IconSpec(name="content-only", label="Content Only", relative_path="content-only.svg"),
    "node-chrome": IconSpec(name="node-chrome", label="Node Chrome", relative_path="node-chrome.svg"),
    "title-heading": IconSpec(name="title-heading", label="Title", relative_path="title-heading.svg"),
    "frame-corners": IconSpec(name="frame-corners", label="Frame", relative_path="frame-corners.svg"),
    "frame": IconSpec(name="frame", label="Frame", relative_path="frame.svg"),
    "door-enter": IconSpec(name="door-enter", label="Enter Subnode", relative_path="door-enter.svg"),
    "open-session": IconSpec(name="open-session", label="Open Session", relative_path="open-session.svg"),
    "link": IconSpec(name="link", label="Link", relative_path="link.svg"),
    "external-link": IconSpec(name="external-link", label="Open", relative_path="external-link.svg"),
    "internalize-source": IconSpec(
        name="internalize-source",
        label="Copy Into Project",
        relative_path="internalize-source.svg",
    ),
    "file-text": IconSpec(name="file-text", label="File", relative_path="file-text.svg"),
    "file-type-html": IconSpec(name="file-type-html", label="HTML File", relative_path="file-type-html.svg"),
    "folder": IconSpec(name="folder", label="Folder", relative_path="folder.svg"),
    "folder-open": IconSpec(name="folder-open", label="Browse Files", relative_path="folder-open.svg"),
    "layout-dashboard": IconSpec(name="layout-dashboard", label="Workspace", relative_path="layout-dashboard.svg"),
    "hierarchy-2": IconSpec(name="hierarchy-2", label="Node", relative_path="hierarchy-2.svg"),
    "world-www": IconSpec(name="world-www", label="Web Address", relative_path="world-www.svg"),
    "plus": IconSpec(name="plus", label="Add", relative_path="plus.svg"),
    "x": IconSpec(name="x", label="Remove", relative_path="x.svg"),
    "run": IconSpec(name="run", label="Run", relative_path="player-play.svg"),
    "node-run": IconSpec(name="node-run", label="Run", relative_path="node-run.svg"),
    "node-expand": IconSpec(name="node-expand", label="Expand", relative_path="node-expand.svg"),
    "node-collapse": IconSpec(name="node-collapse", label="Collapse", relative_path="node-collapse.svg"),
    "pause": IconSpec(name="pause", label="Pause", relative_path="player-pause.svg"),
    "resume": IconSpec(name="resume", label="Resume", relative_path="player-play.svg"),
    "stop": IconSpec(name="stop", label="Stop", relative_path="player-stop.svg"),
    "step": IconSpec(name="step", label="Step", relative_path="step.svg"),
    "focus": IconSpec(name="focus", label="Focus", relative_path="focus.svg"),
    "zoom-fit": IconSpec(name="zoom-fit", label="Zoom to Fit", relative_path="zoom-fit.svg"),
    "viewer-wireframe": IconSpec(
        name="viewer-wireframe",
        label="Wireframe",
        relative_path="viewer-wireframe.svg",
    ),
    "viewer-visible-edges": IconSpec(
        name="viewer-visible-edges",
        label="Visible Edges",
        relative_path="viewer-visible-edges.svg",
    ),
    "viewer-shaded": IconSpec(
        name="viewer-shaded",
        label="Shaded",
        relative_path="viewer-shaded.svg",
    ),
    "viewer-body-edges": IconSpec(
        name="viewer-body-edges",
        label="Shaded with Body Edges",
        relative_path="viewer-body-edges.svg",
    ),
    "viewer-mesh-edges": IconSpec(
        name="viewer-mesh-edges",
        label="Mesh or Facet Edges",
        relative_path="viewer-mesh-edges.svg",
    ),
    "viewer-attribute-colors": IconSpec(
        name="viewer-attribute-colors",
        label="Attribute Colors",
        relative_path="viewer-attribute-colors.svg",
        tintable=False,
    ),
    "viewer-perspective": IconSpec(
        name="viewer-perspective",
        label="Perspective Projection",
        relative_path="viewer-perspective.svg",
    ),
    "viewer-orthographic": IconSpec(
        name="viewer-orthographic",
        label="Orthographic Projection",
        relative_path="viewer-orthographic.svg",
    ),
    "viewer-fit-all": IconSpec(name="viewer-fit-all", label="Fit All", relative_path="viewer-fit-all.svg"),
    "viewer-fit-selection": IconSpec(
        name="viewer-fit-selection",
        label="Fit Selection",
        relative_path="viewer-fit-selection.svg",
    ),
    "viewer-isolate": IconSpec(name="viewer-isolate", label="Isolate Selection", relative_path="viewer-isolate.svg"),
    "viewer-ui-controls": IconSpec(
        name="viewer-ui-controls",
        label="Viewer UI Controls",
        relative_path="viewer-ui-controls.svg",
    ),
    "viewer-saved-views": IconSpec(
        name="viewer-saved-views",
        label="Saved Views",
        relative_path="viewer-saved-views.svg",
    ),
    "viewer-detach": IconSpec(name="viewer-detach", label="Detach Viewer", relative_path="viewer-detach.svg"),
    "viewer-dock": IconSpec(name="viewer-dock", label="Dock Viewer", relative_path="viewer-dock.svg"),
    "viewer-fullscreen": IconSpec(
        name="viewer-fullscreen",
        label="Fullscreen Viewer",
        relative_path="viewer-fullscreen.svg",
    ),
    "viewer-select-vertex": IconSpec(
        name="viewer-select-vertex",
        label="Select CAD Vertex",
        relative_path="viewer-select-vertex.svg",
    ),
    "viewer-select-edge": IconSpec(
        name="viewer-select-edge",
        label="Select CAD Edge",
        relative_path="viewer-select-edge.svg",
    ),
    "viewer-select-face": IconSpec(
        name="viewer-select-face",
        label="Select CAD Face",
        relative_path="viewer-select-face.svg",
    ),
    "viewer-select-body": IconSpec(
        name="viewer-select-body",
        label="Select CAD Body",
        relative_path="viewer-select-body.svg",
    ),
    "viewer-select-node": IconSpec(
        name="viewer-select-node",
        label="Select FE Node",
        relative_path="viewer-select-node.svg",
    ),
    "viewer-select-element-face": IconSpec(
        name="viewer-select-element-face",
        label="Select FE Element Face",
        relative_path="viewer-select-element-face.svg",
    ),
    "viewer-select-element": IconSpec(
        name="viewer-select-element",
        label="Select FE Element",
        relative_path="viewer-select-element.svg",
    ),
    "viewer-select-tangent": IconSpec(
        name="viewer-select-tangent",
        label="Tangent Selection Angle",
        relative_path="viewer-select-tangent.svg",
    ),
    "keep-live": IconSpec(name="keep-live", label="Keep Live", relative_path="keep-live.svg"),
    "clock-update": IconSpec(name="clock-update", label="Update Time", relative_path="clock-update.svg"),
    "calendar": IconSpec(name="calendar", label="Calendar", relative_path="calendar.svg"),
    "lock": IconSpec(name="lock", label="Lock", relative_path="lock.svg"),
    "pin": IconSpec(name="pin", label="Pin", relative_path="pin.svg"),
    "pin-off": IconSpec(name="pin-off", label="Unpin", relative_path="pinned-off.svg"),
    "reply": IconSpec(name="reply", label="Reply", relative_path="arrow-back-up.svg"),
    "check": IconSpec(name="check", label="Check", relative_path="check.svg"),
    "send": IconSpec(name="send", label="Send", relative_path="send.svg"),
    "plug": IconSpec(name="plug", label="Plug", relative_path="plug.svg"),
    "search": IconSpec(name="search", label="Search", relative_path="search.svg"),
    "settings": IconSpec(name="settings", label="Settings", relative_path="settings.svg"),
    "title": IconSpec(name="title", label="Title", relative_path="title.svg"),
    "volume": IconSpec(name="volume", label="Volume", relative_path="volume.svg"),
    "volume-muted": IconSpec(name="volume-muted", label="Muted", relative_path="volume-muted.svg"),
    "video-bookmarks": IconSpec(
        name="video-bookmarks",
        label="Video Bookmarks",
        relative_path="video-bookmarks.svg",
    ),
    "video-bookmark-add": IconSpec(
        name="video-bookmark-add",
        label="Add Video Bookmark",
        relative_path="video-bookmark-add.svg",
    ),
    "video-bookmark-jump": IconSpec(
        name="video-bookmark-jump",
        label="Jump To Video Bookmark",
        relative_path="video-bookmark-jump.svg",
    ),
    "video-capture-frame": IconSpec(
        name="video-capture-frame",
        label="Capture Video Frame",
        relative_path="video-capture-frame.svg",
    ),
    "export": IconSpec(name="export", label="Export", relative_path="video-capture-frame.svg"),
    "video-timestamp-note": IconSpec(
        name="video-timestamp-note",
        label="Timestamp Note",
        relative_path="video-timestamp-note.svg",
    ),
    "video-clip-range": IconSpec(
        name="video-clip-range",
        label="Video Clip Range",
        relative_path="video-clip-range.svg",
    ),
    "video-clip-in": IconSpec(
        name="video-clip-in",
        label="Set Clip In",
        relative_path="video-clip-in.svg",
    ),
    "video-clip-out": IconSpec(
        name="video-clip-out",
        label="Set Clip Out",
        relative_path="video-clip-out.svg",
    ),
    "video-trim-save": IconSpec(
        name="video-trim-save",
        label="Save Trimmed Video",
        relative_path="video-trim-save.svg",
    ),
    "video-seek-back-10": IconSpec(
        name="video-seek-back-10",
        label="Seek Back 10 Seconds",
        relative_path="video-seek-back-10.svg",
    ),
    "video-seek-forward-10": IconSpec(
        name="video-seek-forward-10",
        label="Seek Forward 10 Seconds",
        relative_path="video-seek-forward-10.svg",
    ),
    "video-rewind": IconSpec(name="video-rewind", label="Rewind Video", relative_path="video-rewind.svg"),
    "video-fit": IconSpec(name="video-fit", label="Fit Video", relative_path="video-fit.svg"),
    "video-fill": IconSpec(name="video-fill", label="Fill Video", relative_path="video-fill.svg"),
    "video-loop": IconSpec(name="video-loop", label="Loop Video", relative_path="video-loop.svg"),
    "more": IconSpec(name="more", label="More", relative_path="more.svg"),
    "chevrons-left": IconSpec(name="chevrons-left", label="Collapse", relative_path="chevrons-left.svg"),
    "chevrons-right": IconSpec(name="chevrons-right", label="Collapse", relative_path="chevrons-right.svg"),
    "chevron-up": IconSpec(name="chevron-up", label="Expand", relative_path="chevron-up.svg"),
    "chevron-down": IconSpec(name="chevron-down", label="Collapse", relative_path="chevron-down.svg"),
    "browser-back": IconSpec(name="browser-back", label="Back", relative_path="browser-back.svg"),
    "browser-forward": IconSpec(name="browser-forward", label="Forward", relative_path="browser-forward.svg"),
    "browser-reload": IconSpec(name="browser-reload", label="Reload", relative_path="browser-reload.svg"),
    "browser-stop": IconSpec(name="browser-stop", label="Stop", relative_path="browser-stop.svg"),
    "browser-home": IconSpec(name="browser-home", label="Home", relative_path="browser-home.svg"),
    "browser-detach": IconSpec(name="browser-detach", label="Detach", relative_path="browser-detach.svg"),
    "zoom-in": IconSpec(name="zoom-in", label="Zoom In", relative_path="zoom-in.svg"),
    "zoom-out": IconSpec(name="zoom-out", label="Zoom Out", relative_path="zoom-out.svg"),
    "rotate-clockwise": IconSpec(name="rotate-clockwise", label="Rotate Clockwise", relative_path="rotate-clockwise.svg"),
    "flip-horizontal": IconSpec(name="flip-horizontal", label="Flip Horizontal", relative_path="flip-horizontal.svg"),
    "flip-vertical": IconSpec(name="flip-vertical", label="Flip Vertical", relative_path="flip-vertical.svg"),
}


def _normalize_name(name: str) -> str:
    return str(name or "").strip().lower()


def has_icon(name: str) -> bool:
    return _normalize_name(name) in _ICON_SPECS


def icon_names() -> tuple[str, ...]:
    return tuple(sorted(_ICON_SPECS))


def icon_spec(name: str) -> IconSpec:
    normalized = _normalize_name(name)
    if normalized not in _ICON_SPECS:
        raise KeyError(f"Unknown icon: {name}")
    return _ICON_SPECS[normalized]


def icon_path(name: str) -> Path:
    return _ICON_ROOT / icon_spec(name).relative_path


def icon_source_url(name: str, size: int = DEFAULT_ICON_SIZE, color: str = DEFAULT_ICON_COLOR) -> str:
    spec = icon_spec(name)
    params = urlencode({"size": max(1, int(size)), "color": color or DEFAULT_ICON_COLOR})
    return f"image://{UI_ICON_PROVIDER_ID}/{spec.name}?{params}"


def _normalize_color(color: str) -> QColor:
    qcolor = QColor(color or DEFAULT_ICON_COLOR)
    if not qcolor.isValid():
        qcolor = QColor(DEFAULT_ICON_COLOR)
    return qcolor


@lru_cache(maxsize=256)
def _render_icon_image(name: str, size: int, color: str) -> QImage:
    spec = icon_spec(name)
    renderer = QSvgRenderer(str(_ICON_ROOT / spec.relative_path))
    image = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    if not renderer.isValid():
        return image

    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
    renderer.render(painter, QRectF(0, 0, size, size))
    if spec.tintable:
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
        painter.fillRect(image.rect(), _normalize_color(color))
    painter.end()
    return image


def icon_pixmap(name: str, size: int = DEFAULT_ICON_SIZE, color: str = DEFAULT_ICON_COLOR) -> QPixmap:
    normalized_size = max(1, int(size))
    return QPixmap.fromImage(_render_icon_image(name, normalized_size, color))


def qicon(name: str, size: int = DEFAULT_ICON_SIZE, color: str = DEFAULT_ICON_COLOR) -> QIcon:
    return QIcon(icon_pixmap(name, size=size, color=color))


class UiIconRegistryBridge(QObject):
    @pyqtSlot(str, result=bool)
    def has(self, name: str) -> bool:
        return has_icon(name)

    @pyqtSlot(str, result=str)
    def label(self, name: str) -> str:
        try:
            return icon_spec(name).label
        except KeyError:
            return str(name or "")

    @pyqtSlot(str, result=int)
    def defaultSize(self, name: str) -> int:
        try:
            return icon_spec(name).default_size
        except KeyError:
            return DEFAULT_ICON_SIZE

    @pyqtSlot(str, result=str)
    def source(self, name: str) -> str:
        return self.sourceSized(name, DEFAULT_ICON_SIZE, DEFAULT_ICON_COLOR)

    @pyqtSlot(str, int, str, result=str)
    def sourceSized(self, name: str, size: int, color: str) -> str:
        try:
            return icon_source_url(name, size=size, color=color)
        except KeyError:
            return ""


class UiIconImageProvider(QQuickImageProvider):
    def __init__(self) -> None:
        super().__init__(QQuickImageProvider.ImageType.Pixmap)

    def requestPixmap(self, icon_id: str, requested_size: QSize) -> tuple[QPixmap, QSize]:  # type: ignore[override]
        icon_name, _, query = icon_id.partition("?")
        parsed_params = parse_qs(query, keep_blank_values=False)
        params = {key: values[-1] for key, values in parsed_params.items() if values}

        requested = max(requested_size.width(), requested_size.height(), 0)
        resolved_size = max(1, requested or int(params.get("size", DEFAULT_ICON_SIZE)))
        color = params.get("color", DEFAULT_ICON_COLOR)

        try:
            pixmap = icon_pixmap(icon_name, size=resolved_size, color=color)
        except KeyError:
            pixmap = QPixmap(resolved_size, resolved_size)
            pixmap.fill(Qt.GlobalColor.transparent)

        return pixmap, pixmap.size()

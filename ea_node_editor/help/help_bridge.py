"""QObject bridge exposing node help to QML.

Modeled on [ShellInspectorBridge](../ui_qml/shell_inspector_bridge.py). The
bridge holds the currently-displayed Markdown and title and exposes a slot to
resolve a node id through the catalog's shared spec lookup into the
corresponding Help page.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import QObject, pyqtProperty, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QTextCursor
from PyQt6.QtQuick import QQuickTextDocument

from ea_node_editor.runtime_contracts import GRAPH_DATA_TYPE_ID

_PARAGRAPH_TOP_MARGIN = 10.0
_PARAGRAPH_BOTTOM_MARGIN = 10.0

if TYPE_CHECKING:
    from ea_node_editor.ui.shell.window import ShellWindow


def _single_line(value: object) -> str:
    return " ".join(str(value or "").split())


def _structured_markdown_for_spec(spec: object) -> str:
    type_id = _single_line(getattr(spec, "type_id", ""))
    title = _single_line(getattr(spec, "display_name", "")) or type_id or "Node Help"
    description = str(getattr(spec, "description", "") or "").strip()
    keywords = [
        _single_line(keyword)
        for keyword in (getattr(spec, "keywords", ()) or ())
        if _single_line(keyword)
    ]
    ports = list(getattr(spec, "ports", ()) or ())

    lines = [f"# {title}"]
    if type_id:
        lines.extend(("", f"`{type_id}`"))
    if description:
        lines.extend(("", description))
    if keywords:
        lines.extend(("", f"**Keywords:** {', '.join(keywords)}"))

    for heading, direction in (("Inputs", "in"), ("Outputs", "out"), ("Ports", "neutral")):
        matching = [port for port in ports if str(getattr(port, "direction", "")) == direction]
        if not matching:
            continue
        lines.extend(("", f"## {heading}"))
        for port in matching:
            key = _single_line(getattr(port, "key", ""))
            label = _single_line(getattr(port, "label", "")) or key
            data_type = (
                _single_line(getattr(port, "data_type", "")) or GRAPH_DATA_TYPE_ID
            )
            description_text = _single_line(getattr(port, "description", "")) or "No description provided."
            lines.append(f"- **{label}** (`{key}`, `{data_type}`) — {description_text}")
    return "\n".join(lines).strip()


def _spec_for_node(shell_window: object, node_id: str) -> object | None:
    registry = getattr(shell_window, "registry", None)
    lookup = getattr(registry, "spec_or_none", None)
    if not callable(lookup):
        return None
    workspace_id = str(
        getattr(shell_window, "active_workspace_id", "")
        or (
            shell_window.workspace_manager.active_workspace_id()
            if hasattr(shell_window, "workspace_manager")
            else ""
        )
        or ""
    ).strip()
    project = getattr(getattr(shell_window, "model", None), "project", None)
    workspace = project.workspaces.get(workspace_id) if project is not None and workspace_id else None
    node = workspace.nodes.get(str(node_id)) if workspace is not None else None
    return lookup(node.type_id) if node is not None else None


class HelpBridge(QObject):
    help_changed = pyqtSignal()
    help_visible_changed = pyqtSignal()
    help_tab_requested = pyqtSignal()

    def __init__(
        self,
        parent: QObject | None = None,
        *,
        shell_window: "ShellWindow | None" = None,
    ) -> None:
        super().__init__(parent)
        self._shell_window = shell_window
        self._markdown: str = ""
        self._title: str = ""
        self._type_id: str = ""
        self._visible: bool = False

    @property
    def shell_window(self) -> "ShellWindow | None":
        return self._shell_window

    @pyqtProperty(str, notify=help_changed)
    def markdown(self) -> str:
        return self._markdown

    @pyqtProperty(str, notify=help_changed)
    def title(self) -> str:
        return self._title

    @pyqtProperty(str, notify=help_changed)
    def type_id(self) -> str:
        return self._type_id

    @pyqtProperty(bool, notify=help_changed)
    def has_help(self) -> bool:
        return bool(self._markdown)

    @pyqtProperty(bool, notify=help_visible_changed)
    def visible(self) -> bool:
        return self._visible

    @pyqtSlot(str, result=bool)
    def show_help_for_node(self, node_id: str) -> bool:
        if self._shell_window is None or not node_id:
            return False
        spec = _spec_for_node(self._shell_window, str(node_id))
        if spec is None:
            return False
        type_id = str(getattr(spec, "type_id", "") or "")
        display_name = str(getattr(spec, "display_name", "") or type_id)
        markdown = _structured_markdown_for_spec(spec)
        self._apply(markdown=markdown, type_id=type_id, title=display_name)
        self._set_visible(True)
        return True

    @pyqtSlot(result=bool)
    def show_help_for_selected_node(self) -> bool:
        self.help_tab_requested.emit()
        node_id = self._selected_node_id()
        if node_id and self.can_show_help_for_node(node_id):
            return self.show_help_for_node(node_id)
        # An unresolved node must not leave help from a prior selection visible.
        self._apply(markdown="", type_id="", title="")
        return False

    @pyqtSlot(result=bool)
    def can_show_help_for_selected_node(self) -> bool:
        return self.can_show_help_for_node(self._selected_node_id())

    @pyqtSlot(str, result=bool)
    def show_help_for_type(self, type_id: str) -> bool:
        if self._shell_window is None:
            return False
        registry = getattr(self._shell_window, "registry", None)
        if registry is None:
            return False
        normalized_type_id = str(type_id).strip()
        spec = registry.spec_or_none(normalized_type_id)
        if spec is None:
            return False
        markdown = _structured_markdown_for_spec(spec)
        display_name = str(getattr(spec, "display_name", "") or normalized_type_id)
        self.help_tab_requested.emit()
        self._apply(markdown=markdown, type_id=normalized_type_id, title=display_name)
        self._set_visible(True)
        return True

    @pyqtSlot(str, result=bool)
    def can_show_help_for_node(self, node_id: str) -> bool:
        if self._shell_window is None or not node_id:
            return False
        return _spec_for_node(self._shell_window, str(node_id)) is not None

    @pyqtSlot()
    def close_help(self) -> None:
        self._set_visible(False)

    @pyqtSlot(QQuickTextDocument)
    def apply_document_spacing(self, quick_doc: QQuickTextDocument | None) -> None:
        """Loosen paragraph margins on the help TextArea's document.

        Qt's built-in Markdown renderer uses very tight default block margins,
        which collapses the blank lines between short paragraphs (e.g. each
        entry in the Scripting section) visually. Walking the blocks and
        setting top/bottom margin restores the spacing implied by the source.
        """
        if quick_doc is None:
            return
        doc = quick_doc.textDocument()
        if doc is None:
            return
        cursor = QTextCursor(doc)
        cursor.beginEditBlock()
        block = doc.begin()
        while block.isValid():
            fmt = block.blockFormat()
            fmt.setTopMargin(_PARAGRAPH_TOP_MARGIN)
            fmt.setBottomMargin(_PARAGRAPH_BOTTOM_MARGIN)
            cursor.setPosition(block.position())
            cursor.setBlockFormat(fmt)
            block = block.next()
        cursor.endEditBlock()

    def _selected_node_id(self) -> str:
        scene = getattr(self._shell_window, "scene", None)
        selector = getattr(scene, "selected_node_id", None)
        if not callable(selector):
            return ""
        return str(selector() or "")

    def _apply(self, *, markdown: str, type_id: str, title: str) -> None:
        changed = (
            markdown != self._markdown
            or type_id != self._type_id
            or title != self._title
        )
        self._markdown = markdown
        self._type_id = type_id
        self._title = title
        if changed:
            self.help_changed.emit()

    def _set_visible(self, visible: bool) -> None:
        if self._visible == visible:
            return
        self._visible = visible
        self.help_visible_changed.emit()


__all__ = ["HelpBridge"]

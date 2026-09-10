from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QComboBox,
    QCompleter,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)


@dataclass(frozen=True)
class InputReferenceEntry:
    context: str
    input: str
    action: str


@dataclass(frozen=True)
class InputReferenceSection:
    title: str
    entries: tuple[InputReferenceEntry, ...]


INPUT_REFERENCE_SECTIONS: tuple[InputReferenceSection, ...] = (
    InputReferenceSection(
        "Project, Workspaces, And Shell",
        (
            InputReferenceEntry("Project", "Ctrl+N", "Create a new project."),
            InputReferenceEntry("Project", "Ctrl+O", "Open an existing project."),
            InputReferenceEntry("Project", "Ctrl+S", "Save the current project."),
            InputReferenceEntry("Project", "Ctrl+Shift+S", "Save the project under a new path."),
            InputReferenceEntry("Workspace", "Ctrl+F4", "Close the active workspace."),
            InputReferenceEntry("Workspace", "Ctrl+Shift+N", "Create a new workspace."),
            InputReferenceEntry("Workspace", "Ctrl+Shift+V", "Create a new view."),
            InputReferenceEntry("Workspace", "Ctrl+Shift+D", "Duplicate the active workspace."),
            InputReferenceEntry("Workspace", "F2", "Rename the active workspace."),
            InputReferenceEntry("Workspace", "Ctrl+Tab or Ctrl+PgDown", "Switch to the next workspace."),
            InputReferenceEntry("Workspace", "Ctrl+Shift+Tab or Ctrl+PgUp", "Switch to the previous workspace."),
            InputReferenceEntry("Views", "File menu or view-tab context menu", "Export one or more canvas views as PNG files or a PowerPoint deck."),
            InputReferenceEntry("Settings", "Ctrl+,", "Open workflow settings."),
            InputReferenceEntry("Shell", "Ctrl+Shift+E", "Show or hide the script editor panel."),
            InputReferenceEntry("Run", "F5", "Run the active workflow."),
            InputReferenceEntry("Run", "Shift+F5", "Stop the active workflow."),
            InputReferenceEntry("Run", "F6", "Pause or resume the active workflow."),
            InputReferenceEntry("Add-On Manager", "Esc", "Close the Add-On Manager pane when it has focus."),
        ),
    ),
    InputReferenceSection(
        "Graph Actions And Navigation",
        (
            InputReferenceEntry("History", "Ctrl+Z", "Undo the last graph or project edit."),
            InputReferenceEntry("History", "Ctrl+Shift+Z or Ctrl+Y", "Redo the last undone edit."),
            InputReferenceEntry("Selection", "Ctrl+C", "Copy selected graph items."),
            InputReferenceEntry("Selection", "Ctrl+X", "Cut selected graph items."),
            InputReferenceEntry("Canvas", "Ctrl+V", "Paste graph items or import clipboard content using Automatic or Ask every time."),
            InputReferenceEntry("Canvas", "Drop files, folders, URLs, or content", "Import every item at the drop position; Ask every time offers per-item choices and Set all to."),
            InputReferenceEntry("Canvas options / Graphics Settings", "Paste and drop", "Choose app-wide Automatic or Ask every time behaviour; the choice persists across restarts."),
            InputReferenceEntry("Selection", "Ctrl+D", "Duplicate selected graph items."),
            InputReferenceEntry("Selection", "Delete", "Delete selected graph items."),
            InputReferenceEntry("Connections", "Ctrl+Shift+L", "Connect the currently selected connectable items."),
            InputReferenceEntry("Locked objects", "Ctrl+L", "Temporarily allow selecting locked canvas objects."),
            InputReferenceEntry("Group", "C", "Wrap the current selection in a Group."),
            InputReferenceEntry("Subnodes", "Ctrl+Alt+G", "Group the current selection into a subnode."),
            InputReferenceEntry("Subnodes", "Ctrl+Shift+G", "Ungroup the selected subnode."),
            InputReferenceEntry("Viewport", "A", "Frame all graph items."),
            InputReferenceEntry("Viewport", "F", "Frame the current selection."),
            InputReferenceEntry("Viewport", "Shift+F", "Center the current selection."),
            InputReferenceEntry("Search", "Ctrl+K", "Open graph search."),
            InputReferenceEntry("Node Browser", "Ctrl+B", "Open the node browser."),
            InputReferenceEntry("Scope", "Alt+Left", "Navigate to the parent scope."),
            InputReferenceEntry("Scope", "Alt+Home", "Navigate to the root scope."),
            InputReferenceEntry(
                "Selected edge",
                "Ctrl+Left or Ctrl+Right",
                "Center the view on the edge start or end.",
            ),
            InputReferenceEntry(
                "Media Panel (PDF mode)",
                "Left or Right",
                "Move the selected PDF-mode Media Panel to the previous or next page.",
            ),
            InputReferenceEntry("Help", "F1", "Show help for the selected node."),
            InputReferenceEntry("Fullscreen", "F11", "Open eligible selected content in fullscreen."),
            InputReferenceEntry("Graph", "Esc", "Cancel active wire drags, menus, overlays, or comment peek."),
        ),
    ),
    InputReferenceSection(
        "Canvas And Viewport Gestures",
        (
            InputReferenceEntry(
                "Empty canvas",
                "Left-drag",
                "Drag left-to-right for enclosed nodes or right-to-left for crossing nodes.",
            ),
            InputReferenceEntry(
                "Empty canvas",
                "Ctrl+left-drag or Shift+left-drag",
                "Add with the same enclosed or crossing marquee rules.",
            ),
            InputReferenceEntry("Empty canvas", "W+left-drag", "Select wires crossed by the marquee."),
            InputReferenceEntry(
                "Empty canvas",
                "W+Shift+left-drag",
                "Add crossed wires to the current selection.",
            ),
            InputReferenceEntry("Empty canvas", "Right-drag", "Zoom to the dragged rectangle."),
            InputReferenceEntry("Empty canvas", "Right-click", "Open the graph or selection context menu."),
            InputReferenceEntry("Empty canvas", "Double-click", "Open quick insert at the pointer."),
            InputReferenceEntry(
                "Model Viewer proxy viewport",
                "Double-click",
                "Activate the inline 3D viewer.",
            ),
            InputReferenceEntry("Viewport", "Mouse wheel", "Zoom the graph canvas."),
            InputReferenceEntry("Viewport", "Middle-drag", "Pan the graph canvas."),
            InputReferenceEntry(
                "Viewport",
                "Middle+right click",
                "Toggle unused optional data ports for the active view.",
            ),
            InputReferenceEntry("Minimap", "Click minimap toggle", "Expand or collapse the minimap."),
            InputReferenceEntry("Minimap", "Click minimap", "Center the graph view on that minimap position."),
            InputReferenceEntry("Minimap", "Drag viewport rectangle", "Pan the graph view through the minimap."),
        ),
    ),
    InputReferenceSection(
        "Nodes, Edges, Ports, And Context Menus",
        (
            InputReferenceEntry("Node body", "Left-click", "Select the node."),
            InputReferenceEntry("Node body", "Ctrl+left-click or Shift+left-click", "Add or remove the node from selection."),
            InputReferenceEntry("Node body", "Left-drag", "Move the node or selected node group."),
            InputReferenceEntry("Embedded node control", "Click, type, drag, or choose", "Use the control without changing graph selection."),
            InputReferenceEntry(
                "Node body",
                "Right-click",
                "Open the node context menu, including Add Link and Add Comment for editable nodes.",
            ),
            InputReferenceEntry("Node body", "Double-click", "Open the node default action or an inline edit target."),
            InputReferenceEntry("Panel", "Double-click", "Open the Panel Text/Data editor."),
            InputReferenceEntry("Panel", "Right-click", "Open Edit values and interpretation..., Copy, and Copy as tree actions."),
            InputReferenceEntry("Node title edit", "Enter or focus loss", "Commit the edited node title."),
            InputReferenceEntry("Node title edit", "Esc", "Cancel the edited node title."),
            InputReferenceEntry("Floating node toolbar", "Enter Subnode", "Enter the subnode scope."),
            InputReferenceEntry("Locked add-on node", "Left-click", "Select the locked placeholder or manager affordance."),
            InputReferenceEntry("Locked add-on node", "Right-click", "Open the locked placeholder context menu."),
            InputReferenceEntry("Locked add-on node", "Double-click", "Open the Add-On Manager recovery affordance."),
            InputReferenceEntry("Node resize handle", "Left-drag", "Resize the node."),
            InputReferenceEntry("Edge", "Left-click", "Select the edge."),
            InputReferenceEntry("Edge", "Ctrl+left-click or Shift+left-click", "Add or remove the edge from selection."),
            InputReferenceEntry("Edge", "Double-click", "Edit the flow-edge label inline."),
            InputReferenceEntry("Edge", "Right-click", "Open the edge context menu."),
            InputReferenceEntry("Port", "Click or drag", "Start, preview, or complete a connection."),
            InputReferenceEntry("Port drag", "Release on empty canvas", "Open connection quick insert for compatible nodes."),
            InputReferenceEntry("Connected port", "Ctrl+drag", "Reconnect the incident wire endpoints as one operation."),
            InputReferenceEntry("Connected port", "Ctrl+drag to empty canvas", "Disconnect the incident wires as one operation."),
            InputReferenceEntry(
                "Connected port",
                "Ctrl+Shift+drag",
                "Copy the sole or selected incident wire to a compatible endpoint.",
            ),
            InputReferenceEntry("Port label", "Click", "Start editing the port label."),
            InputReferenceEntry("Port label edit", "Enter or focus loss", "Commit the edited port label."),
            InputReferenceEntry("Port label edit", "Esc", "Cancel the edited port label."),
            InputReferenceEntry("Node context menu", "Left-click command", "Run the selected node command."),
            InputReferenceEntry("Edge context menu", "Left-click command", "Run the selected edge command."),
            InputReferenceEntry("Selection context menu", "Left-click command", "Run the selected selection command."),
        ),
    ),
    InputReferenceSection(
        "Search, Quick Insert, And Inline Editors",
        (
            InputReferenceEntry("Graph search", "Up or Down", "Move the highlighted search result."),
            InputReferenceEntry("Graph search", "Enter or Return", "Activate the highlighted search result."),
            InputReferenceEntry("Graph search", "Esc", "Close graph search."),
            InputReferenceEntry("Graph search", "Left-click result", "Activate that search result."),
            InputReferenceEntry("Connection quick insert", "Up or Down", "Move the highlighted compatible node result."),
            InputReferenceEntry("Connection quick insert", "Enter or Return", "Insert the highlighted compatible node."),
            InputReferenceEntry("Connection quick insert", "Esc", "Close quick insert."),
            InputReferenceEntry("Connection quick insert", "Left-click result", "Insert that compatible node."),
            InputReferenceEntry("Inline text editor", "Ctrl+Enter", "Commit inline text or textarea edits."),
            InputReferenceEntry("Inline text editor", "Esc", "Cancel or reset inline text edits."),
            InputReferenceEntry("Inspector text field", "Enter or focus loss", "Commit the edited property value."),
            InputReferenceEntry("Inspector textarea", "Ctrl+Enter", "Apply the edited multiline property value."),
            InputReferenceEntry("Inspector textarea", "Esc", "Revert the edited multiline property value."),
            InputReferenceEntry("Inspector port label", "Click label", "Begin editing the selected node port label."),
            InputReferenceEntry("Inspector port label", "Enter or focus loss", "Commit the edited port label."),
            InputReferenceEntry("Inspector port label", "Esc", "Cancel the edited port label."),
            InputReferenceEntry("Floating node toolbar", "Enter or Return", "Activate the focused toolbar action."),
            InputReferenceEntry("Floating node toolbar", "Left-click action", "Run the clicked node action."),
            InputReferenceEntry("Floating edge toolbar", "Left-click action", "Run the clicked edge action or quick style control."),
            InputReferenceEntry("Edge label edit", "Enter or focus loss", "Commit the edited edge label."),
            InputReferenceEntry("Edge label edit", "Esc", "Cancel the edited edge label."),
        ),
    ),
    InputReferenceSection(
        "Library, Inspector, And Tabs",
        (
            InputReferenceEntry("Node library category", "Left-click", "Expand or collapse the category."),
            InputReferenceEntry("Node library node", "Left-click", "Add the node to the active graph."),
            InputReferenceEntry("Node library node", "Left-drag to canvas", "Drop the node at the canvas position."),
            InputReferenceEntry("Custom workflow row", "Right-click", "Open the custom workflow context menu."),
            InputReferenceEntry("Inspector palette", "Up or Down", "Move the active property row."),
            InputReferenceEntry("Inspector palette", "Esc", "Clear the current property search query."),
            InputReferenceEntry("Inspector palette row", "Hover or left-click", "Make that property row active."),
            InputReferenceEntry("Inspector editable combo", "Down", "Open the filtered option list."),
            InputReferenceEntry("Inspector editable combo", "Enter or Return", "Commit the current text or option."),
            InputReferenceEntry("Inspector editable combo", "Esc", "Close the option list."),
            InputReferenceEntry("Inspector editable combo", "Click dropdown affordance", "Open or close the option list."),
            InputReferenceEntry("Workspace and view tabs", "Left-click", "Activate the tab."),
            InputReferenceEntry("Workspace and view tabs", "Left-drag", "Reorder the tab."),
            InputReferenceEntry("Workspace and view tabs", "Right-click", "Open the tab context menu."),
            InputReferenceEntry("Workspace and view tabs", "Horizontal wheel or Shift+wheel", "Scroll overflowing tabs."),
        ),
    ),
    InputReferenceSection(
        "Fullscreen, Media, Tables, And Folder Explorer",
        (
            InputReferenceEntry("Fullscreen overlay", "Esc or F11", "Close fullscreen content."),
            InputReferenceEntry("PDF fullscreen", "Left or Right", "Move to the previous or next PDF page."),
            InputReferenceEntry("PDF fullscreen", "Page Up or Page Down", "Move to the previous or next PDF page."),
            InputReferenceEntry("PDF fullscreen", "Home or End", "Move to the first or last PDF page."),
            InputReferenceEntry("PDF fullscreen", "Mouse wheel", "Move to the previous or next PDF page."),
            InputReferenceEntry("PDF fullscreen", "Ctrl+F", "Open PDF text search."),
            InputReferenceEntry("PDF fullscreen search", "Enter or Shift+Enter", "Move to the next or previous PDF search match."),
            InputReferenceEntry("PDF fullscreen", "Ctrl+Plus or Ctrl+Minus", "Zoom the PDF in or out."),
            InputReferenceEntry("PDF fullscreen", "Ctrl+0", "Reset the PDF to actual size."),
            InputReferenceEntry("PDF fullscreen", "R or Shift+R", "Rotate the PDF clockwise or counter-clockwise."),
            InputReferenceEntry("Viewer fullscreen", "Space", "Play or pause result-step animation when available."),
            InputReferenceEntry("Viewer fullscreen", "Left or Right", "Move to the previous or next result step when available."),
            InputReferenceEntry("Viewer fullscreen", "Home", "Fit the camera to the model."),
            InputReferenceEntry("Viewer fullscreen", "R", "Reset the camera to the isometric view."),
            InputReferenceEntry(
                "Viewer fullscreen or detached",
                "Page Up or Page Down",
                "Restore the previous or next saved view, wrapping at the ends.",
            ),
            InputReferenceEntry("Video fullscreen", "Space", "Play or pause the video."),
            InputReferenceEntry("Video fullscreen", "Left or Right", "Seek backward or forward ten seconds."),
            InputReferenceEntry("Video fullscreen", "M", "Mute or unmute the video."),
            InputReferenceEntry("Video fullscreen", "Esc or F11", "Close video fullscreen."),
            InputReferenceEntry("Video clip range", "Replace / Copy", "Save the selected clip range internally."),
            InputReferenceEntry("Video source popover", "Esc", "Cancel the source edit."),
            InputReferenceEntry("Media crop mode", "Left-drag crop handle", "Adjust the crop rectangle."),
            InputReferenceEntry("Media crop mode", "Apply button", "Commit the crop rectangle."),
            InputReferenceEntry("Media crop mode", "Cancel button", "Discard the crop rectangle."),
            InputReferenceEntry("Tabular preview", "Tap cell", "Select the table cell."),
            InputReferenceEntry("Tabular preview", "Drag column divider", "Resize the column."),
            InputReferenceEntry("Tabular preview", "Double-click column divider", "Autofit the column."),
            InputReferenceEntry("Folder explorer row", "Left-click", "Select the row."),
            InputReferenceEntry("Folder explorer row", "Right-click", "Open the row menu: Open, Open with..., Copy Path, Open in New Classic Explorer, Send to COREX as Path Pointer, Properties."),
            InputReferenceEntry("Folder explorer row", "Left-drag", "Import the file or folder using Automatic or Ask every time; dropping on an existing Path Pointer replaces its path."),
            InputReferenceEntry("Folder explorer row", "Double-click", "Navigate into folders or open files."),
            InputReferenceEntry("Folder explorer header", "Left-click", "Sort by the clicked column."),
            InputReferenceEntry("Path Pointer toolbar", "Open button", "Expand the Open / Open with... sub-toolbar to launch the pointed path with the OS."),
        ),
    ),
)


def iter_input_reference_entries() -> Iterator[InputReferenceEntry]:
    for section in INPUT_REFERENCE_SECTIONS:
        yield from section.entries


def _unique_sorted_entry_values(column_name: str) -> list[str]:
    values = {
        str(getattr(entry, column_name)).strip()
        for entry in iter_input_reference_entries()
        if str(getattr(entry, column_name)).strip()
    }
    return sorted(values, key=str.casefold)


class InputReferenceDialog(QDialog):
    def __init__(self, *, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Keyboard and Mouse Reference")
        self.setModal(True)
        self.resize(940, 680)

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(10)

        self.summary_label = QLabel(
            "Current keyboard shortcuts, mouse gestures, context-menu gestures, and focused editor controls.",
            self,
        )
        self.summary_label.setObjectName("inputReferenceSummaryLabel")
        self.summary_label.setWordWrap(True)
        root.addWidget(self.summary_label)

        filter_layout = QHBoxLayout()
        filter_layout.setContentsMargins(0, 0, 0, 0)
        filter_layout.setSpacing(8)
        filter_layout.addWidget(QLabel("Context", self))
        self.context_filter_combo = self._build_filter_combo(
            object_name="inputReferenceContextFilter",
            values=_unique_sorted_entry_values("context"),
            placeholder="Filter context",
        )
        filter_layout.addWidget(self.context_filter_combo, stretch=1)
        filter_layout.addWidget(QLabel("Action", self))
        self.action_filter_combo = self._build_filter_combo(
            object_name="inputReferenceActionFilter",
            values=_unique_sorted_entry_values("action"),
            placeholder="Filter action",
        )
        filter_layout.addWidget(self.action_filter_combo, stretch=2)
        self.clear_filters_button = QPushButton("Clear", self)
        self.clear_filters_button.setObjectName("inputReferenceClearFiltersButton")
        self.clear_filters_button.clicked.connect(self.clear_filters)
        filter_layout.addWidget(self.clear_filters_button)
        root.addLayout(filter_layout)

        self.reference_tree = QTreeWidget(self)
        self.reference_tree.setObjectName("inputReferenceTree")
        self.reference_tree.setColumnCount(3)
        self.reference_tree.setHeaderLabels(["Context", "Input", "Action"])
        self.reference_tree.setAlternatingRowColors(True)
        self.reference_tree.setRootIsDecorated(True)
        self.reference_tree.setUniformRowHeights(False)
        self.reference_tree.setWordWrap(True)
        self._populate_reference_tree()
        root.addWidget(self.reference_tree, stretch=1)

        self.context_filter_combo.currentTextChanged.connect(self._apply_filters)
        self.action_filter_combo.currentTextChanged.connect(self._apply_filters)
        self._apply_filters()

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, parent=self)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def clear_filters(self) -> None:
        self.context_filter_combo.setEditText("")
        self.action_filter_combo.setEditText("")
        self._apply_filters()

    def _build_filter_combo(self, *, object_name: str, values: list[str], placeholder: str) -> QComboBox:
        combo = QComboBox(self)
        combo.setObjectName(object_name)
        combo.setEditable(True)
        combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        combo.addItems(values)
        combo.setCurrentIndex(-1)
        line_edit = combo.lineEdit()
        if line_edit is not None:
            line_edit.setPlaceholderText(placeholder)
        completer = QCompleter(values, combo)
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completer.setFilterMode(Qt.MatchFlag.MatchContains)
        combo.setCompleter(completer)
        return combo

    def _populate_reference_tree(self) -> None:
        section_font = QFont()
        section_font.setBold(True)

        for section in INPUT_REFERENCE_SECTIONS:
            section_item = QTreeWidgetItem([section.title, "", ""])
            section_item.setFirstColumnSpanned(True)
            section_item.setFont(0, section_font)
            self.reference_tree.addTopLevelItem(section_item)
            for entry in section.entries:
                section_item.addChild(QTreeWidgetItem([entry.context, entry.input, entry.action]))

        self.reference_tree.expandAll()
        self.reference_tree.resizeColumnToContents(0)
        self.reference_tree.resizeColumnToContents(1)

    def _apply_filters(self) -> None:
        context_filter = self.context_filter_combo.currentText().strip().casefold()
        action_filter = self.action_filter_combo.currentText().strip().casefold()
        for section_index in range(self.reference_tree.topLevelItemCount()):
            section_item = self.reference_tree.topLevelItem(section_index)
            visible_children = 0
            for child_index in range(section_item.childCount()):
                child = section_item.child(child_index)
                context_matches = not context_filter or context_filter in child.text(0).casefold()
                action_matches = not action_filter or action_filter in child.text(2).casefold()
                child_visible = context_matches and action_matches
                child.setHidden(not child_visible)
                if child_visible:
                    visible_children += 1
            section_item.setHidden(visible_children == 0)
            if visible_children:
                section_item.setExpanded(True)

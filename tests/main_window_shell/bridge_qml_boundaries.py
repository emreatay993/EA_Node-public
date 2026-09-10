from __future__ import annotations

import re
import unittest

import pytest
from PyQt6.QtCore import QPoint, QPointF, Qt, QUrl, pyqtSlot
from PyQt6.QtQml import QQmlComponent, QQmlEngine
from PyQt6.QtQuick import QQuickItem, QQuickWindow
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from ea_node_editor.ui_qml.script_editor_model import ScriptEditorModel
from ea_node_editor.ui_qml.theme_bridge import ThemeBridge

from tests.main_window_shell.bridge_contracts import _REPO_ROOT

pytestmark = pytest.mark.xdist_group("p03_bridge_contracts")

_TOOLTIP_QML_SCOPE_DIRS = (
    "ea_node_editor/ui_qml/components/graph",
    "ea_node_editor/ui_qml/components/graph_canvas",
    "ea_node_editor/ui_qml/components/shell",
)
_TOOLTIP_HELPER_BLOCK_RE = re.compile(
    r"^\s*("
    r"ShellButton|ShellControls\.ShellButton|ShellCreateButton|InspectorButton|"
    r"InspectorColorField|ShellCollapsibleSidePane|GraphSurfaceButton|"
    r"GraphSurfaceControls\.GraphSurfaceButton|GraphCanvasMinimapOverlay"
    r")\s*\{"
)
_RICH_TOOLTIP_FORMAT_SNIPPETS = (
    "tooltipTextFormat: Text.RichText",
    "tooltipTextFormat: Text.StyledText",
)
_STYLED_TOOLTIP_ALLOWLIST: frozenset[tuple[str, int]] = frozenset()


class _SlotCountingScriptEditorModel(ScriptEditorModel):
    def __init__(self) -> None:
        super().__init__()
        self.width_calls: list[float] = []

    @pyqtSlot(float)
    def set_width(self, width: float) -> None:
        self.width_calls.append(float(width))
        super().set_width(width)


def _qml_tooltip_scope_files() -> list[tuple[str, object]]:
    files: list[tuple[str, object]] = []
    for relative_root in _TOOLTIP_QML_SCOPE_DIRS:
        scope_root = _REPO_ROOT / relative_root
        files.extend(
            (path.relative_to(_REPO_ROOT).as_posix(), path)
            for path in sorted(scope_root.rglob("*.qml"))
        )
    return files


def _qml_block_from_line(lines: list[str], start_index: int) -> str:
    block_lines: list[str] = []
    depth = 0
    for line in lines[start_index:]:
        block_lines.append(line)
        depth += line.count("{") - line.count("}")
        if depth <= 0 and len(block_lines) > 1:
            break
    return "\n".join(block_lines)


def _helper_block_exposes_tooltip(helper_type: str, block: str) -> bool:
    if helper_type in {
        "ShellCreateButton",
        "InspectorColorField",
        "ShellCollapsibleSidePane",
        "GraphCanvasMinimapOverlay",
    }:
        return True
    if helper_type in {"ShellButton", "ShellControls.ShellButton"}:
        return "tooltipText:" in block or "iconName:" in block
    if helper_type == "InspectorButton":
        return "tooltipText:" in block
    if helper_type in {"GraphSurfaceButton", "GraphSurfaceControls.GraphSurfaceButton"}:
        return (
            "tooltipText:" in block
            or "iconName:" in block
            or re.search(r"^\s*text\s*:", block, flags=re.MULTILINE) is not None
        )
    return False


class TooltipManagerTierCatalogQmlBoundaryTests(unittest.TestCase):
    def test_p05_tooltip_catalog_rollout_marks_tutorial_warning_inactive_and_advanced_paths(
        self,
    ) -> None:
        expectations = {
            "ea_node_editor/ui_qml/components/shell/GraphSearchOverlay.qml": (
                "tooltipText: root.graphSearchFilterTooltip()",
                'tooltipCategory: "tutorial"',
            ),
            "ea_node_editor/ui_qml/components/graph_canvas/GraphCanvasRootLayers.qml": (
                "GraphCanvasMinimapOverlay {",
                'tooltipCategory: TooltipCopy.category(tooltipCopyBridge, "graph.minimap.expand")',
            ),
            "ea_node_editor/ui_qml/components/shell/ShellLabeledTabStrip.qml": (
                "ShellCreateButton {",
                'tooltipCategory: "tutorial"',
            ),
            "ea_node_editor/ui_qml/components/shell/InspectorPortManagementSection.qml": (
                'objectName: "inspectorDeletePortButton"',
                'tooltipText: TooltipCopy.text(tooltipCopyBridge, "inspector.ports.delete_selected")',
                'tooltipCategory: TooltipCopy.category(tooltipCopyBridge, "inspector.ports.delete_selected")',
                'objectName: "inspectorAddPortButton"',
                'tooltipCategory: "tutorial"',
            ),
            "ea_node_editor/ui_qml/components/shell/InspectorNodeDefinitionSection.qml": (
                'objectName: "inspectorUngroupButton"',
                'tooltipText: TooltipCopy.text(tooltipCopyBridge, "inspector.node_definition.ungroup")',
                'tooltipCategory: TooltipCopy.category(tooltipCopyBridge, "inspector.node_definition.ungroup")',
            ),
            "ea_node_editor/ui_qml/components/graph/passive/GraphWebBoardSurface.qml": (
                'TooltipCopy.text(tooltipCopyBridge, "fullscreen.web_board.editor_unavailable")',
                'TooltipCopy.category(tooltipCopyBridge, "fullscreen.web_board.editor_unavailable")',
            ),
            "ea_node_editor/ui_qml/components/shell/ShellStatusStrip.qml": (
                "graphics_status_bar_layout",
                "readonly property bool telemetryHudLayout",
                "Layout.preferredHeight: root.telemetryHudLayout ? 46 : 32",
            ),
            "ea_node_editor/ui/tooltips/graph.json": (
                '"graph.minimap.expand"',
                '"category": "tutorial"',
            ),
            "ea_node_editor/ui/tooltips/inspector.json": (
                "affected connections may be removed",
                '"category": "warning"',
                "child nodes move to the parent scope",
            ),
            "ea_node_editor/ui/tooltips/fullscreen.json": (
                '"Fullscreen editor unavailable"',
                '"category": "inactive"',
            ),
        }

        for relative_path, snippets in expectations.items():
            qml_text = (_REPO_ROOT / relative_path).read_text(encoding="utf-8")
            for snippet in snippets:
                with self.subTest(path=relative_path, snippet=snippet):
                    self.assertIn(snippet, qml_text)

    def test_tooltip_qml_scope_records_accepted_missing_categories(
        self,
    ) -> None:
        missing_categories: list[str] = []
        raw_tooltips: list[str] = []

        for relative_path, qml_path in _qml_tooltip_scope_files():
            qml_text = qml_path.read_text(encoding="utf-8")
            if re.search(r"\bToolTip\b", qml_text):
                raw_tooltips.append(relative_path)

            lines = qml_text.splitlines()
            for index, line in enumerate(lines):
                match = _TOOLTIP_HELPER_BLOCK_RE.match(line)
                if match is None:
                    continue
                helper_type = match.group(1)
                block = _qml_block_from_line(lines, index)
                if (
                    _helper_block_exposes_tooltip(helper_type, block)
                    and "tooltipCategory:" not in block
                ):
                    missing_categories.append(
                        f"{relative_path}:{index + 1} {helper_type}"
                    )

        self.assertEqual(raw_tooltips, [])
        self.assertEqual(
            [re.sub(r":\d+ ", ": ", value) for value in missing_categories],
            [
                "ea_node_editor/ui_qml/components/graph/surface_controls/GraphSurfaceIntervalFields.qml: GraphSurfaceButton",
                "ea_node_editor/ui_qml/components/graph/surface_controls/GraphSurfaceListEditor.qml: GraphSurfaceButton",
                "ea_node_editor/ui_qml/components/graph/surface_controls/GraphSurfaceListEditor.qml: GraphSurfaceButton",
                "ea_node_editor/ui_qml/components/shell/PythonScriptGuidePane.qml: ShellButton",
                "ea_node_editor/ui_qml/components/shell/ScriptCodeEditorPane.qml: ShellButton",
            ],
        )

    def test_tooltip_qml_scope_keeps_ordinary_tooltips_plain_text_without_unreviewed_rich_opt_in(
        self,
    ) -> None:
        unreviewed_rich_tooltips: list[str] = []
        markup_without_format: list[str] = []
        markup_pattern = re.compile(r'tooltipText:\s*"[^"\n]*<[^"\n]+>')

        for relative_path, qml_path in _qml_tooltip_scope_files():
            lines = qml_path.read_text(encoding="utf-8").splitlines()
            for index, line in enumerate(lines):
                match = _TOOLTIP_HELPER_BLOCK_RE.match(line)
                if match is None:
                    continue
                block = _qml_block_from_line(lines, index)
                location = (relative_path, index + 1)
                if (
                    any(snippet in block for snippet in _RICH_TOOLTIP_FORMAT_SNIPPETS)
                    and location not in _STYLED_TOOLTIP_ALLOWLIST
                ):
                    unreviewed_rich_tooltips.append(f"{relative_path}:{index + 1}")
                if markup_pattern.search(block) and not any(
                    snippet in block for snippet in _RICH_TOOLTIP_FORMAT_SNIPPETS
                ):
                    markup_without_format.append(f"{relative_path}:{index + 1}")

        self.assertEqual(unreviewed_rich_tooltips, [])
        self.assertEqual(markup_without_format, [])

    def test_general_help_tooltips_action_remains_bound_to_general_category(
        self,
    ) -> None:
        source_text = (
            _REPO_ROOT / "ea_node_editor/ui/shell/window_actions.py"
        ).read_text(encoding="utf-8")
        for snippet in (
            'QAction("General Help Tooltips", window)',
            "window.set_graphics_tooltip_category_enabled(",
            "TOOLTIP_CATEGORY_GENERAL",
            "refresh_recent_projects_menu(window)",
        ):
            with self.subTest(snippet=snippet):
                self.assertIn(snippet, source_text)


class ShellLibraryBridgeQmlBoundaryTests(unittest.TestCase):
    def test_owned_qml_components_route_migrated_concerns_through_shell_library_bridge(
        self,
    ) -> None:
        expectations = {
            "ea_node_editor/ui_qml/components/shell/NodeLibraryPane.qml": (
                (
                    "property var mainWindowRef",
                    "mainWindowRef.set_library_query",
                    "mainWindowRef.grouped_node_library_items",
                    "mainWindowRef.request_add_node_from_library",
                    "target: root.mainWindowRef",
                ),
                ("shellLibraryBridgeRef",),
            ),
            "ea_node_editor/ui_qml/components/shell/LibraryWorkflowContextPopup.qml": (
                (
                    "property var mainWindowRef",
                    "mainWindowRef.request_rename_custom_workflow_from_library",
                    "mainWindowRef.request_set_custom_workflow_scope",
                    "mainWindowRef.request_delete_custom_workflow_from_library",
                ),
                ("shellLibraryBridgeRef",),
            ),
            "ea_node_editor/ui_qml/components/shell/GraphSearchOverlay.qml": (
                (
                    "property var mainWindowRef",
                    "mainWindowRef.graph_search_",
                    "mainWindowRef.set_graph_search_query",
                    "mainWindowRef.request_graph_search_",
                    "target: root.mainWindowRef",
                ),
                ("shellLibraryBridgeRef",),
            ),
            "ea_node_editor/ui_qml/components/shell/ConnectionQuickInsertOverlay.qml": (
                (
                    "property var mainWindowRef",
                    "mainWindowRef.connection_quick_insert_",
                    "mainWindowRef.set_connection_quick_insert_query",
                    "mainWindowRef.request_close_connection_quick_insert",
                    "mainWindowRef.request_connection_quick_insert_",
                    "target: root.mainWindowRef",
                ),
                ("shellLibraryBridgeRef",),
            ),
            "ea_node_editor/ui_qml/components/shell/GraphHintOverlay.qml": (
                (
                    "property var mainWindowRef",
                    "mainWindowRef.graph_hint_",
                ),
                ("shellLibraryBridgeRef",),
            ),
        }

        for relative_path, (absent_snippets, present_snippets) in expectations.items():
            qml_path = _REPO_ROOT / relative_path
            qml_text = qml_path.read_text(encoding="utf-8")

            for snippet in absent_snippets:
                with self.subTest(
                    path=relative_path, snippet=snippet, expectation="absent"
                ):
                    self.assertNotIn(snippet, qml_text)

            for snippet in present_snippets:
                with self.subTest(
                    path=relative_path, snippet=snippet, expectation="present"
                ):
                    self.assertIn(snippet, qml_text)

    def test_nested_category_qml_library_pane_uses_flattened_row_metadata(self) -> None:
        qml_path = (
            _REPO_ROOT / "ea_node_editor/ui_qml/components/shell/NodeLibraryPane.qml"
        )
        qml_text = qml_path.read_text(encoding="utf-8")

        present_snippets = (
            "ListView {",
            "function categoryKeyForRow(row) {",
            'return String(row.category_key || "")',
            "function depthForRow(row) {",
            "function ancestorsExpanded(ancestorCategoryKeys) {",
            "row.ancestor_category_keys || []",
            'objectName: "nodeLibraryRow"',
            "model: root.shellLibraryBridgeRef.display_node_library_items",
            'property bool isIconGrid: modelData.kind === "passive_icon_grid"',
            "property string rowCategoryKey: root.categoryKeyForRow(modelData)",
            "property int rowDepth: root.depthForRow(modelData)",
            "property real rowIndent: root.rowIndentForRow(modelData)",
            "property bool hiddenByAncestors: root.isRowHiddenByAncestors(modelData)",
            "anchors.leftMargin: libraryRow.rowIndent",
            'objectName: "nodeLibraryGridTile"',
            "LibraryNodeVisual {",
            "root.isCategoryCollapsed(libraryRow.rowCategoryKey)",
            "root.setCategoryCollapsed(",
            "libraryRow.rowCategoryKey,",
            "Drag.active: !libraryRow.isCategory && !libraryRow.isIconGrid && mouseArea.drag.active",
            "root.graphCanvasRef.updateLibraryDropPreview",
            "root.graphCanvasRef.performLibraryDrop",
            "root.shellLibraryBridgeRef.request_add_node_from_library(modelData.type_id)",
        )
        absent_snippets = (
            "TreeView",
            "modelData.category",
            'split("',
            "split('",
            "collapsedCategories[normalizedCategory]",
        )

        for snippet in present_snippets:
            with self.subTest(snippet=snippet, expectation="present"):
                self.assertIn(snippet, qml_text)

        for snippet in absent_snippets:
            with self.subTest(snippet=snippet, expectation="absent"):
                self.assertNotIn(snippet, qml_text)

    def test_node_library_rows_use_compact_metadata_tooltips(self) -> None:
        qml_path = (
            _REPO_ROOT / "ea_node_editor/ui_qml/components/shell/NodeLibraryPane.qml"
        )
        qml_text = qml_path.read_text(encoding="utf-8")

        for snippet in (
            "function primaryDataPort(item, direction) {",
            'String(port.kind || "") === "data"',
            "function compactDescription(description) {",
            'replace(/\\s+/g, " ").trim()',
            "if (compact.length > 200)",
            'compact.slice(0, 197).trim() + "..."',
            "function libraryItemTooltip(item) {",
            "root.compactDescription(item.description)",
            '"nodes.library.tooltip.input"',
            '"nodes.library.tooltip.output"',
            "active: mouseArea.containsMouse && !libraryRow.isCategory",
            "maximumTextWidth: 320",
        ):
            with self.subTest(snippet=snippet):
                self.assertIn(snippet, qml_text)
        self.assertEqual(qml_text.count("text: root.libraryItemTooltip(modelData)"), 2)


class ShellInspectorBridgeQmlBoundaryTests(unittest.TestCase):
    def test_inspector_pane_routes_owned_concerns_through_shell_inspector_bridge(
        self,
    ) -> None:
        expectations = {
            "ea_node_editor/ui_qml/components/shell/InspectorPane.qml": (
                (
                    "property var mainWindowRef",
                    "mainWindowRef.has_selected_node",
                    "mainWindowRef.selected_node_is_subnode_pin",
                    "mainWindowRef.selected_node_is_subnode_shell",
                    "mainWindowRef.selected_node_port_items",
                    "mainWindowRef.selected_node_title",
                    "mainWindowRef.selected_node_subtitle",
                    "mainWindowRef.selected_node_collapsible",
                    "mainWindowRef.selected_node_collapsed",
                    "mainWindowRef.selected_node_header_items",
                    "mainWindowRef.selected_node_property_items",
                    "mainWindowRef.selected_node_link_items",
                    "mainWindowRef.selected_node_comment_items",
                    "mainWindowRef.pin_data_type_options",
                    "mainWindowRef.request_add_selected_subnode_pin",
                    "mainWindowRef.set_selected_port_label",
                    "mainWindowRef.request_remove_selected_port",
                    "mainWindowRef.set_selected_node_collapsed",
                    "mainWindowRef.request_ungroup_selected_nodes",
                    "mainWindowRef.set_selected_node_property",
                    "mainWindowRef.browse_selected_node_property_path",
                    "mainWindowRef.set_selected_port_exposed",
                    "mainWindowRef.upsert_selected_node_link",
                    "mainWindowRef.remove_selected_node_link",
                    "mainWindowRef.move_selected_node_link",
                    "mainWindowRef.open_selected_node_link",
                    "mainWindowRef.upsert_selected_node_comment",
                    "mainWindowRef.remove_selected_node_comment",
                    "mainWindowRef.set_selected_node_comment_resolved",
                    "mainWindowRef.set_selected_node_comment_pinned",
                    "mainWindowRef.resolve_all_selected_node_comments",
                    "mainWindowRef.mark_selected_node_comments_read",
                    "target: root.mainWindowRef",
                ),
                (
                    "property var inspectorBridgeRef:",
                    "root.inspectorBridgeRef.has_selected_node",
                    "bridge.selected_node_is_subnode_pin",
                    "bridge.selected_node_is_subnode_shell",
                    "bridge.selected_node_port_items",
                    "bridge.selected_node_title",
                    "bridge.selected_node_subtitle",
                    "bridge.selected_node_collapsible",
                    "bridge.selected_node_collapsed",
                    "bridge.selected_node_header_items",
                    "bridge.selected_node_property_items",
                    "bridge.selected_node_link_items",
                    "bridge.selected_node_comment_items",
                    "bridge.pin_data_type_options",
                    "root.inspectorBridgeRef.request_add_selected_subnode_pin",
                    "root.inspectorBridgeRef.set_selected_port_label",
                    "root.inspectorBridgeRef.request_remove_selected_port",
                    "InspectorNodeLinksSection {",
                    "InspectorNodeCommentsSection {",
                    "target: root.inspectorBridgeRef",
                ),
            ),
            "ea_node_editor/ui_qml/components/shell/InspectorNodeLinksSection.qml": (
                (
                    "mainWindowRef.selected_node_link_items",
                    "mainWindowRef.upsert_selected_node_link",
                    "mainWindowRef.remove_selected_node_link",
                    "mainWindowRef.move_selected_node_link",
                    "mainWindowRef.open_selected_node_link",
                ),
                (
                    "section.pane.selectedNodeLinkItems",
                    "pane.inspectorBridgeRef.upsert_selected_node_link",
                    "section.pane.inspectorBridgeRef.remove_selected_node_link",
                    "section.pane.inspectorBridgeRef.move_selected_node_link",
                    "section.pane.inspectorBridgeRef.open_selected_node_link",
                ),
            ),
            "ea_node_editor/ui_qml/components/shell/InspectorNodeCommentsSection.qml": (
                (
                    "mainWindowRef.selected_node_comment_items",
                    "mainWindowRef.upsert_selected_node_comment",
                    "mainWindowRef.remove_selected_node_comment",
                    "property var pane",
                ),
                (
                    "pane.selectedNodeCommentItems",
                    "pane.inspectorBridgeRef.upsert_selected_node_comment",
                    "section.pane.inspectorBridgeRef.remove_selected_node_comment",
                    "section.pane.inspectorBridgeRef.set_selected_node_comment_resolved",
                    "section.pane.inspectorBridgeRef.set_selected_node_comment_pinned",
                    "section.pane.inspectorBridgeRef.resolve_all_selected_node_comments",
                    "pane.inspectorBridgeRef.mark_selected_node_comments_read",
                    "property string editingNodeId",
                    'editingNodeId !== String(pane.selectedNodeId || "")',
                ),
            ),
            "ea_node_editor/ui_qml/components/shell/InspectorNodeDefinitionSection.qml": (
                (
                    "mainWindowRef.set_selected_node_collapsed",
                    "mainWindowRef.request_ungroup_selected_nodes",
                ),
                (
                    "definitionSection.pane.inspectorBridgeRef.set_selected_node_collapsed",
                    "definitionSection.pane.inspectorBridgeRef.request_ungroup_selected_nodes",
                ),
            ),
            "ea_node_editor/ui_qml/components/shell/InspectorPropertyEditor.qml": (
                (
                    "mainWindowRef.set_selected_node_property",
                    "mainWindowRef.browse_selected_node_property_path",
                ),
                (
                    "propertyEditor.pane.inspectorBridgeRef.set_selected_node_property",
                    "propertyEditor.canCommit()",
                ),
            ),
            "ea_node_editor/ui_qml/components/shell/InspectorPathPropertyEditor.qml": (
                ("mainWindowRef.browse_selected_node_property_path",),
                ("editorContext.pane.inspectorBridgeRef.browse_selected_node_property_path",
                 "editorContext.commitValue("),
            ),
            "ea_node_editor/ui_qml/components/shell/InspectorColorField.qml": (
                ("mainWindowRef.pick_selected_node_property_color",),
                ("root.pane.inspectorBridgeRef.pick_selected_node_property_color",),
            ),
            "ea_node_editor/ui_qml/components/shell/InspectorPortRow.qml": (
                ("mainWindowRef.set_selected_port_exposed",),
                ("portRow.pane.inspectorBridgeRef.set_selected_port_exposed",),
            ),
        }

        for relative_path, (absent_snippets, present_snippets) in expectations.items():
            qml_path = _REPO_ROOT / relative_path
            qml_text = qml_path.read_text(encoding="utf-8")

            for snippet in absent_snippets:
                with self.subTest(
                    path=relative_path, snippet=snippet, expectation="absent"
                ):
                    self.assertNotIn(snippet, qml_text)

            for snippet in present_snippets:
                with self.subTest(
                    path=relative_path, snippet=snippet, expectation="present"
                ):
                    self.assertIn(snippet, qml_text)


class ShellAddOnManagerQmlBoundaryTests(unittest.TestCase):
    def test_addon_manager_surface_routes_variant4_concerns_through_packet_owned_bridge(
        self,
    ) -> None:
        expectations = {
            "ea_node_editor/ui_qml/MainShell.qml": (
                (
                    "AddOnManagerPane {",
                    "sourceComponent:",
                    'objectName: "addonManagerPlaceholderOverlay"',
                    'objectName: "addonManagerPlaceholderMessage"',
                    'objectName: "addonManagerPlaceholderRevision"',
                ),
                (
                    'objectName: "shellWorkspaceRow"',
                    'objectName: "addonManagerScrim"',
                    'objectName: "addonManagerPaneLoader"',
                    "visible: root.addonManagerBridgeRef.open",
                    "property bool addonManagerLoaderActivated:",
                    "function onStateChanged()",
                    "active: root.addonManagerLoaderActivated",
                    'source: Qt.resolvedUrl("components/shell/AddOnManagerPane.qml")',
                    "item.requestBridge = root.addonManagerBridgeRef",
                    "item.workspaceBridge = root.shellWorkspaceBridgeRef",
                    "item.viewerHostServiceRef = root.viewerHostServiceRef",
                    "item.themeBridgeRef = root.themeBridgeRef",
                    "item.graphThemeBridgeRef = root.graphThemeBridgeRef",
                ),
            ),
            "ea_node_editor/ui_qml/components/shell/AddOnManagerPane.qml": (
                (
                    "category_accent_palette",
                    "graphCategoryPalette",
                    "nodeHeaderBg",
                    "categoryAccent(",
                ),
                (
                    "import EA.NodeEditor 1.0",
                    "ShellAddOnManagerBridge {",
                    'objectName: "shellAddOnManagerBridge"',
                    "requestBridge: root.requestBridge",
                    "workspaceBridge: root.workspaceBridge",
                    "viewerHostServiceRef: root.viewerHostServiceRef",
                    'objectName: "addonManagerToolbar"',
                    'objectName: "addonManagerPendingBadge"',
                    'objectName: "addonManagerRestartRuntimeButton"',
                    'objectName: "addonManagerFallbackWorkflowSettingsButton"',
                    'objectName: "addonManagerPrimaryToggleButton"',
                    "controller.installSelectedAddon()",
                    '"Installing..."',
                    'objectName: "addonManagerInstallProgressText"',
                    "visible: controller.installing && controller.installProgressText.length > 0",
                    "text: controller.installProgressText",
                    'objectName: "addonManagerPendingBanner"',
                    'objectName: "addonManagerTab" + modelData.label',
                    "nodeCardBg: graphNodePalette.card_bg",
                    "return themePalette.accent",
                ),
            ),
        }

        for relative_path, (absent_snippets, present_snippets) in expectations.items():
            qml_text = (_REPO_ROOT / relative_path).read_text(encoding="utf-8")
            for snippet in absent_snippets:
                with self.subTest(
                    path=relative_path, snippet=snippet, expectation="absent"
                ):
                    self.assertNotIn(snippet, qml_text)
            for snippet in present_snippets:
                with self.subTest(
                    path=relative_path, snippet=snippet, expectation="present"
                ):
                    self.assertIn(snippet, qml_text)


class ShellWorkspaceBridgeQmlBoundaryTests(unittest.TestCase):
    def test_node_link_pick_mode_intercepts_canvas_and_workspace_tabs(self) -> None:
        expectations = {
            "ea_node_editor/ui_qml/MainShell.qml": (
                ("function startLinkTargetPick(kind)",),
                (
                    "property string linkTargetPickMode",
                    'property string linkTargetPickOwner: ""',
                    "function startLinkTargetPick(owner, kind, sourceWorkspaceId, sourceNodeId)",
                    "function finishLinkTargetPick(kind, workspaceId, nodeId, label, subtitle)",
                    'if (owner === "canvas") {',
                    "workspaceCenterPane.graphCanvasRef.applyNodeLinkTargetPick(",
                    "workspaceCenterPane.graphCanvasRef.resumeNodeLinkEditorAfterPickCancel();",
                    "workspaceCenterPane.graphCanvasRef.abortNodeLinkEditorAfterSourceLoss();",
                    "workspaceCenterPane.selectNodeForLinkSource(sourceWorkspaceId, sourceNodeId",
                    "inspectorPane.applyLinkTargetPick(",
                    'root.startLinkTargetPick("canvas", kind, sourceWorkspaceId, sourceNodeId)',
                    'root.startLinkTargetPick("inspector", kind, "", "")',
                    "onLinkTargetPicked: function(kind, workspaceId, nodeId, label, subtitle)",
                    "onSelectedNodeIdChanged: root.cancelLinkTargetPickIfSourceSelectionLost()",
                ),
            ),
            "ea_node_editor/ui_qml/components/shell/InspectorPane.qml": (
                (),
                (
                    "signal linkTargetPickRequested(string kind)",
                    "signal linkTargetPickCancelled()",
                    "function applyLinkTargetPick(kind, workspaceId, nodeId, label, subtitle)",
                    "function cancelLinkTargetPick()",
                    "readonly property var selectedNodeLinkNodeOptions:",
                    "readonly property var selectedNodeLinkWorkspaceOptions:",
                    "root.inspectorBridgeRef.selected_node_link_node_options",
                    "root.inspectorBridgeRef.selected_node_link_workspace_options",
                    "onPickTargetRequested: function(kind)",
                    'root.linkTargetPickRequested(String(kind || ""))',
                ),
            ),
            "ea_node_editor/ui_qml/components/shell/InspectorNodeLinksSection.qml": (
                (
                    'objectName: "inspectorNodeLinkPickTargetButton"',
                    "pickTargetRequested(editingKind)",
                ),
                (
                    "Common.NodeLinkEditorForm {",
                    'objectNamePrefix: "inspectorNodeLink"',
                    "function applyPickedTarget(kind, workspaceId, nodeId, label, subtitle)",
                    "linkEditorForm.applyPickedTarget(kind, workspaceId, nodeId, label, subtitle)",
                    "section.pane.inspectorBridgeRef.upsert_selected_node_link(",
                    'String(draft.target_workspace_id || "")',
                    'String(draft.target_node_id || "")',
                    "linkEditorForm.completeSave(storedId);",
                ),
            ),
            "ea_node_editor/ui_qml/components/shell/WorkspaceCenterPane.qml": (
                (),
                (
                    "property string linkTargetPickMode",
                    "signal linkTargetPickRequested(string kind, string sourceWorkspaceId, string sourceNodeId)",
                    "signal linkTargetPicked(string kind, string workspaceId, string nodeId, string label, string subtitle)",
                    'nodeLinkTargetPickActive: root.linkTargetPickMode === "node"',
                    "nodeLinkTargetPickCancelActive: root.linkTargetPickMode.length > 0",
                    "onNodeLinkTargetPickRequested: function(kind, sourceWorkspaceId, sourceNodeId)",
                    'if (root.linkTargetPickMode === "workspace")',
                    'root.linkTargetPicked("workspace", pickedWorkspaceId, "", pickedLabel, "Workspace")',
                    'if (root.linkTargetPickMode === "node")',
                    "root.workspaceBridgeRef.activate_workspace(itemData.workspace_id)",
                ),
            ),
            "ea_node_editor/ui_qml/components/GraphCanvas.qml": (
                (),
                (
                    "property bool nodeLinkTargetPickActive: false",
                    "property bool nodeLinkTargetPickCancelActive: nodeLinkTargetPickActive",
                    "signal nodeLinkTargetPickRequested(string kind, string sourceWorkspaceId, string sourceNodeId)",
                    "signal nodeLinkTargetPicked(string workspaceId, string nodeId, string label, string subtitle)",
                    "function requestNodeLinkTargetPick(kind, sourceWorkspaceId, sourceNodeId)",
                    "function applyNodeLinkTargetPick(kind, workspaceId, nodeId, label, subtitle)",
                    "function resumeNodeLinkEditorAfterPickCancel()",
                    "function abortNodeLinkEditorAfterSourceLoss()",
                    "function completeNodeLinkTargetPick(nodeId)",
                    "if (!root.nodeLinkTargetPickActive)",
                    "root.nodeLinkTargetPicked(",
                    "normalizedNodeId,",
                    'subtitleParts.join(" - ")',
                    "function cancelNodeLinkTargetPick()",
                    "if (!root.nodeLinkTargetPickCancelActive)",
                ),
            ),
            "ea_node_editor/ui_qml/components/graph_canvas/GraphCanvasNodeDelegate.qml": (
                (),
                (
                    "if (canvasItem.completeNodeLinkTargetPick && canvasItem.completeNodeLinkTargetPick(nodeId))",
                    "return;",
                ),
            ),
            "ea_node_editor/ui_qml/components/graph_canvas/GraphCanvasInputLayers.qml": (
                (),
                (
                    "Keys.onEscapePressed: function(event)",
                    "canvasItem.cancelNodeLinkTargetPick()",
                ),
            ),
        }

        for relative_path, (absent_snippets, present_snippets) in expectations.items():
            qml_path = _REPO_ROOT / relative_path
            qml_text = qml_path.read_text(encoding="utf-8")

            for snippet in absent_snippets:
                with self.subTest(path=relative_path, snippet=snippet, expectation="absent"):
                    self.assertNotIn(snippet, qml_text)
            for snippet in present_snippets:
                with self.subTest(path=relative_path, snippet=snippet, expectation="present"):
                    self.assertIn(snippet, qml_text)

    def test_workspace_run_toolbar_and_console_qml_routes_owned_concerns_through_shell_workspace_bridge(
        self,
    ) -> None:
        expectations = {
            "ea_node_editor/ui_qml/components/shell/ShellRunToolbar.qml": (
                (
                    "property var mainWindowRef",
                    "mainWindowRef.project_file_name",
                    "mainWindowRef.active_scope_breadcrumb_items",
                    "mainWindowRef.request_run_workflow",
                    "mainWindowRef.request_toggle_run_pause",
                    "mainWindowRef.request_stop_workflow",
                    "mainWindowRef.request_open_scope_breadcrumb",
                    "mainWindowRef.set_script_editor_panel_visible",
                    'objectName: "shellRunToolbarRunButton"',
                    'objectName: "shellRunToolbarPauseButton"',
                ),
                (
                    "property var viewBridgeRef",
                    "property var scriptEditorBridgeRef",
                    "property var workspaceBridgeRef:",
                    "property var themeBridgeRef:",
                    'objectName: "shellRunToolbarProjectFileName"',
                    'objectName: "shellRunToolbarScopeBreadcrumb"',
                    'objectName: "shellRunToolbarRunPauseResumeButton"',
                    'objectName: "shellRunToolbarStopButton"',
                    'objectName: "shellRunToolbarAutoButton"',
                    "root.workspaceBridgeRef.project_file_name",
                    "root.workspaceBridgeRef.active_scope_breadcrumb_items",
                    "root.workspaceBridgeRef.active_workspace_run_control_mode",
                    "enabled: root.workspaceBridgeRef.active_workspace_can_run",
                    "|| root.workspaceBridgeRef.active_workspace_can_pause",
                    "enabled: root.workspaceBridgeRef.active_workspace_can_stop",
                    'if (runControlMode === "run")',
                    "root.workspaceBridgeRef.request_run_workflow",
                    "root.workspaceBridgeRef.request_toggle_run_pause",
                    "root.workspaceBridgeRef.request_stop_workflow",
                    "selectedStyle: root.workspaceBridgeRef.auto_run_enabled",
                    "root.workspaceBridgeRef.request_toggle_auto_run",
                    "root.workspaceBridgeRef.request_open_scope_breadcrumb",
                    "root.workspaceBridgeRef.set_script_editor_panel_visible",
                ),
            ),
            "ea_node_editor/ui_qml/components/shell/WorkspaceCenterPane.qml": (
                (
                    "mainWindowRef.graphics_tab_strip_density",
                    "mainWindowRef.active_scope_breadcrumb_items",
                    "mainWindowRef.active_view_items",
                    "mainWindowRef.active_workspace_id",
                    "mainWindowRef.request_open_scope_breadcrumb",
                    "mainWindowRef.request_switch_view",
                    "mainWindowRef.request_move_view_tab",
                    "mainWindowRef.request_rename_view",
                    "mainWindowRef.request_close_view",
                    "mainWindowRef.request_create_view",
                    "mainWindowRef.request_move_workspace_tab",
                    "mainWindowRef.request_rename_workspace_by_id",
                    "mainWindowRef.request_close_workspace_by_id",
                    "mainWindowRef.request_create_workspace",
                    "property var workspaceTabsBridgeRef",
                    "property var consoleBridgeRef",
                    "workspaceTabsBridgeRef.tabs",
                    "workspaceTabsBridgeRef.activate_workspace",
                    "consoleBridgeRef.error_count_value",
                    "consoleBridgeRef.warning_count_value",
                    "consoleBridgeRef.clear_all",
                    "consoleBridgeRef.output_text",
                    "consoleBridgeRef.errors_text",
                    "consoleBridgeRef.warnings_text",
                    "property var mainWindowRef",
                    "property var sceneBridgeRef",
                    "property var viewBridgeRef",
                    "property var graphCanvasBridgeRef",
                    "canvasBridge: root.graphCanvasBridgeRef",
                ),
                (
                    "property var graphCanvasStateBridgeRef",
                    "property var graphCanvasCommandBridgeRef",
                    "property var overlayHostItem",
                    "property var workspaceBridgeRef",
                    "property var themeBridgeRef",
                    "property var uiIconsRef:",
                    "root.workspaceBridgeRef.graphics_tab_strip_density",
                    "root.workspaceBridgeRef.active_view_items",
                    "root.workspaceBridgeRef.active_workspace_id",
                    "root.workspaceBridgeRef.request_switch_view",
                    "root.workspaceBridgeRef.request_move_view_tab",
                    "root.workspaceBridgeRef.request_rename_view",
                    "root.workspaceBridgeRef.request_close_view",
                    "root.workspaceBridgeRef.request_create_view",
                    "root.workspaceBridgeRef.request_move_workspace_tab",
                    "root.workspaceBridgeRef.request_rename_workspace_by_id",
                    "root.workspaceBridgeRef.request_close_workspace_by_id",
                    "root.workspaceBridgeRef.request_create_workspace",
                    "root.workspaceBridgeRef.workspace_tabs",
                    "root.workspaceBridgeRef.activate_workspace",
                    "root.workspaceBridgeRef.error_count_value",
                    "root.workspaceBridgeRef.warning_count_value",
                    "root.workspaceBridgeRef.clear_all",
                    "root.workspaceBridgeRef.output_text",
                    "root.workspaceBridgeRef.errors_text",
                    "root.workspaceBridgeRef.warnings_text",
                    'objectName: "workspaceConsoleSeverityTabs"',
                    '"workspaceConsoleOutputTab"',
                    '"workspaceConsoleErrorsTab"',
                    '"workspaceConsoleWarningsTab"',
                    '"workspaceConsoleErrorsBadge"',
                    '"workspaceConsoleWarningsBadge"',
                    'objectName: "workspaceConsoleClearButton"',
                    'objectName: "workspaceConsoleResizeHandle"',
                    'objectName: "workspaceConsoleOutputScrollView"',
                    'objectName: "workspaceConsoleOutputTextArea"',
                    "ScrollBar.vertical.policy: ScrollBar.AsNeeded",
                    "cursorShape: Qt.SplitVCursor",
                    "function scrollToBottom()",
                    "badgeValue: consolePane.consoleChannelCount(channelIndex)",
                    "canvasStateBridge: root.graphCanvasStateBridgeRef",
                    "canvasCommandBridge: root.graphCanvasCommandBridgeRef",
                ),
            ),
            "ea_node_editor/ui_qml/components/shell/ScriptEditorOverlay.qml": (
                (
                    "property var mainWindowRef",
                    "mainWindowRef.set_script_editor_panel_visible(false)",
                    "root.workspaceBridgeRef.set_script_editor_panel_width(root.panelWidth)",
                ),
                (
                    "property var scriptEditorBridgeRef",
                    "property var scriptHighlighterBridgeRef",
                    "property var workspaceBridgeRef:",
                    "property var themeBridgeRef:",
                    "root.workspaceBridgeRef.set_script_editor_panel_visible(false)",
                    "root.scriptEditorBridgeRef.set_width(root.panelWidth)",
                    'objectName: "scriptEditorResizeHandle"',
                    "cursorShape: Qt.SplitHCursor",
                ),
            ),
        }

        for relative_path, (absent_snippets, present_snippets) in expectations.items():
            qml_path = _REPO_ROOT / relative_path
            qml_text = qml_path.read_text(encoding="utf-8")

            for snippet in absent_snippets:
                with self.subTest(
                    path=relative_path, snippet=snippet, expectation="absent"
                ):
                    self.assertNotIn(snippet, qml_text)

            for snippet in present_snippets:
                with self.subTest(
                    path=relative_path, snippet=snippet, expectation="present"
                ):
                    self.assertIn(snippet, qml_text)

    def test_script_editor_width_has_no_shell_forwarding_chain(self) -> None:
        forwarding_paths = (
            "ea_node_editor/ui_qml/shell_workspace_bridge.py",
            "ea_node_editor/ui/shell/presenters/workspace_presenter.py",
            "ea_node_editor/ui/shell/controllers/project_session_controller.py",
            "ea_node_editor/ui/shell/controllers/project_session_services_support/document_io_service.py",
        )

        for relative_path in forwarding_paths:
            with self.subTest(path=relative_path):
                source_text = (_REPO_ROOT / relative_path).read_text(encoding="utf-8")
                self.assertNotIn("set_script_editor_panel_width", source_text)

    def test_script_editor_resize_commits_model_width_only_on_release(self) -> None:
        qml_path = (
            _REPO_ROOT
            / "ea_node_editor/ui_qml/components/shell/ScriptEditorOverlay.qml"
        )
        qml_text = qml_path.read_text(encoding="utf-8")
        position_start = qml_text.index("onPositionChanged: function(mouse) {")
        release_start = qml_text.index("onReleased: {", position_start)
        cancel_start = qml_text.index("onCanceled:", release_start)
        position_handler = qml_text[position_start:release_start]
        release_handler = qml_text[release_start:cancel_start]

        self.assertNotIn("set_width(", position_handler)
        self.assertEqual(
            release_handler.count(
                "root.scriptEditorBridgeRef.set_width(root.panelWidth)"
            ),
            1,
        )

    def test_script_editor_resize_calls_model_once_on_release_and_never_on_cancel(
        self,
    ) -> None:
        app = QApplication.instance() or QApplication([])
        engine = QQmlEngine()
        theme_bridge = ThemeBridge(theme_id="stitch_dark")
        component = QQmlComponent(
            engine,
            QUrl.fromLocalFile(
                str(
                    _REPO_ROOT
                    / "ea_node_editor/ui_qml/components/shell/ScriptEditorOverlay.qml"
                )
            ),
        )
        if component.status() != QQmlComponent.Status.Ready:
            errors = "\n".join(error.toString() for error in component.errors())
            self.fail(f"Failed to load ScriptEditorOverlay.qml:\n{errors}")

        model = _SlotCountingScriptEditorModel()
        model.set_visible(True)
        overlay = component.createWithInitialProperties(
            {
                "scriptEditorBridgeRef": model,
                "themeBridgeRef": theme_bridge,
            }
        )
        if not isinstance(overlay, QQuickItem):
            errors = "\n".join(error.toString() for error in component.errors())
            self.fail(f"Failed to instantiate ScriptEditorOverlay.qml:\n{errors}")

        window = QQuickWindow()
        window.resize(800, 600)
        overlay.setParentItem(window.contentItem())
        window.show()
        app.processEvents()
        QTest.qWait(20)

        handle = overlay.findChild(QQuickItem, "scriptEditorResizeHandle")
        self.assertIsNotNone(handle)
        mouse_area = next(
            (
                child
                for child in handle.childItems()
                if child.property("dragMoved") is not None
            ),
            None,
        )
        self.assertIsNotNone(mouse_area)

        def drag_points() -> tuple[QPoint, QPoint]:
            center = handle.mapToScene(
                QPointF(float(handle.width()) * 0.5, float(handle.height()) * 0.5)
            )
            press = QPoint(round(center.x()), round(center.y()))
            return press, QPoint(press.x() - 60, press.y())

        try:
            cancel_press, cancel_move = drag_points()
            QTest.mousePress(
                window,
                Qt.MouseButton.LeftButton,
                Qt.KeyboardModifier.NoModifier,
                cancel_press,
            )
            QTest.mouseMove(window, cancel_move)
            app.processEvents()
            self.assertTrue(bool(mouse_area.property("dragMoved")))
            self.assertEqual(model.width_calls, [])

            mouse_area.ungrabMouse()
            QTest.mouseRelease(
                window,
                Qt.MouseButton.LeftButton,
                Qt.KeyboardModifier.NoModifier,
                cancel_move,
            )
            app.processEvents()
            self.assertFalse(bool(overlay.property("resizeDragActive")))
            self.assertEqual(model.width_calls, [])

            release_press, release_move = drag_points()
            QTest.mousePress(
                window,
                Qt.MouseButton.LeftButton,
                Qt.KeyboardModifier.NoModifier,
                release_press,
            )
            QTest.mouseMove(
                window,
                QPoint(release_press.x() - 30, release_press.y()),
            )
            QTest.mouseMove(window, release_move)
            app.processEvents()
            self.assertGreater(float(overlay.property("panelWidth")), 0.0)
            self.assertEqual(model.width_calls, [])

            QTest.mouseRelease(
                window,
                Qt.MouseButton.LeftButton,
                Qt.KeyboardModifier.NoModifier,
                release_move,
            )
            app.processEvents()
            self.assertEqual(len(model.width_calls), 1)
            self.assertAlmostEqual(
                model.width_calls[0],
                float(overlay.property("panelWidth")),
                places=6,
            )
        finally:
            window.close()
            overlay.setParentItem(None)
            overlay.deleteLater()
            window.deleteLater()
            engine.deleteLater()
            app.processEvents()

    def test_shell_button_qml_mutes_disabled_visual_states(self) -> None:
        qml_path = _REPO_ROOT / "ea_node_editor/ui_qml/components/shell/ShellButton.qml"
        qml_text = qml_path.read_text(encoding="utf-8")

        present_snippets = (
            "readonly property color foregroundColor: !control.enabled",
            "Qt.alpha(control.themePalette.muted_fg, 0.55)",
            "readonly property color chromeBorderColor: !control.enabled",
            "readonly property color chromeFillColor: !control.enabled",
            "readonly property real contentOpacity: control.enabled ? 1.0 : 0.72",
            "property color iconColor: control.foregroundColor",
            "hoverEnabled: control.enabled",
            'property string tooltipCategory: "general"',
            "property int tooltipTextFormat: Text.PlainText",
            "readonly property bool tooltipVisible: control.enabled",
            "Common.ManagedToolTip {",
            "policyBridge: control.graphCanvasStateBridgeRef",
            "active: control.tooltipVisible",
            "opacity: control.contentOpacity",
            "color: control.foregroundColor",
            "(control.enabled && control.down)",
            "(control.enabled && control.hovered)",
        )

        for snippet in present_snippets:
            with self.subTest(snippet=snippet):
                self.assertIn(snippet, qml_text)

    def test_shell_tooltip_qml_surfaces_gate_informational_tooltips_through_canvas_state_bridge(
        self,
    ) -> None:
        expectations = {
            "ea_node_editor/ui_qml/components/shell/ShellButton.qml": (
                (
                    "function _tooltipBridge() {",
                    "graphics_show_tooltips",
                    "ToolTip.visible:",
                ),
                (
                    'import "../common" as Common',
                    'property string tooltipCategory: "general"',
                    "readonly property bool tooltipVisible: control.enabled",
                    "Common.ManagedToolTip {",
                    "policyBridge: control.graphCanvasStateBridgeRef",
                    "category: control.tooltipCategory",
                    "active: control.tooltipVisible",
                ),
            ),
            "ea_node_editor/ui_qml/components/shell/ShellCreateButton.qml": (
                (
                    "function _tooltipBridge() {",
                    "graphics_show_tooltips",
                    "ToolTip.visible:",
                ),
                (
                    'property string tooltipCategory: "general"',
                    "readonly property bool tooltipVisible: hovered",
                    "Common.ManagedToolTip {",
                    "policyBridge: control.graphCanvasStateBridgeRef",
                    "category: control.tooltipCategory",
                    "active: control.tooltipVisible",
                ),
            ),
            "ea_node_editor/ui_qml/components/shell/InspectorButton.qml": (
                (
                    "function _tooltipBridge() {",
                    "graphics_show_tooltips",
                    "ToolTip.visible:",
                ),
                (
                    "readonly property var tooltipPolicyBridge: control.pane ? control.pane.graphCanvasStateBridgeRef : null",
                    'property string tooltipCategory: "general"',
                    "Common.ManagedToolTip {",
                    "policyBridge: control.tooltipPolicyBridge",
                    "category: control.tooltipCategory",
                    "active: control.tooltipVisible",
                ),
            ),
            "ea_node_editor/ui_qml/components/shell/InspectorColorField.qml": (
                (
                    "function _tooltipBridge() {",
                    "graphics_show_tooltips",
                    "ToolTip.visible:",
                ),
                (
                    "readonly property var tooltipPolicyBridge: root.pane ? root.pane.graphCanvasStateBridgeRef : null",
                    "Common.ManagedToolTip {",
                    "policyBridge: root.tooltipPolicyBridge",
                    "category: root.tooltipCategory",
                    "active: pickButton.hovered",
                ),
            ),
            "ea_node_editor/ui_qml/components/shell/ShellCollapsibleSidePane.qml": (
                (
                    "function _tooltipBridge() {",
                    "graphics_show_tooltips",
                    "ToolTip.visible:",
                ),
                (
                    'property string tooltipCategory: "general"',
                    "Common.ManagedToolTip {",
                    "policyBridge: root.graphCanvasStateBridgeRef",
                    "category: root.tooltipCategory",
                    "active: collapsedHandleHover.hovered",
                    "text: root.expandHandleTooltip",
                ),
            ),
            "ea_node_editor/ui_qml/components/shell/ShellContextMenu.qml": (
                (
                    "function _tooltipBridge() {",
                    "graphics_show_tooltips",
                    "ToolTip.visible:",
                ),
                (
                    'import "../common" as Common',
                    "property var tooltipPolicyBridge:",
                    "readonly property string actionTooltipText:",
                    "readonly property string actionTooltipCategory:",
                    "Common.ManagedToolTip {",
                    "policyBridge: root.tooltipPolicyBridge",
                    "category: parent.actionTooltipCategory",
                    "active: actionEnabled && actionMouseArea.containsMouse",
                ),
            ),
        }

        for relative_path, (absent_snippets, present_snippets) in expectations.items():
            qml_text = (_REPO_ROOT / relative_path).read_text(encoding="utf-8")
            for snippet in absent_snippets:
                with self.subTest(
                    path=relative_path, snippet=snippet, expectation="absent"
                ):
                    self.assertNotIn(snippet, qml_text)
            for snippet in present_snippets:
                with self.subTest(
                    path=relative_path, snippet=snippet, expectation="present"
                ):
                    self.assertIn(snippet, qml_text)

    def test_main_shell_keeps_only_the_remaining_live_shell_plumbing_assignments(
        self,
    ) -> None:
        qml_path = _REPO_ROOT / "ea_node_editor/ui_qml/MainShell.qml"
        qml_text = qml_path.read_text(encoding="utf-8")

        absent_snippets = (
            "typeof graphCanvasBridge",
            "typeof mainWindow",
            "typeof sceneBridge",
            "typeof viewBridge",
            "workspaceTabsBridgeRef: workspaceTabsBridge",
            "consoleBridgeRef: consoleBridge",
            "mainWindowRef: mainWindow",
            "sceneBridgeRef: root.sceneBridgeRef",
            "viewBridgeRef: root.viewBridgeRef",
            "viewBridgeRef: viewBridge",
            "readonly property var canvasShellBridgeRef",
            "readonly property var canvasSceneBridgeRef",
            "readonly property var canvasBridgeRef: graphCanvasBridge",
            "canvasBridgeRef: root.canvasBridgeRef",
            "ShellTitleBar {",
        )
        present_snippets = (
            "readonly property var shellContextRef: shellContext",
            "readonly property var shellLibraryBridgeRef: root.shellContextRef.shellLibraryBridge",
            "readonly property var shellWorkspaceBridgeRef: root.shellContextRef.shellWorkspaceBridge",
            "readonly property var themeBridgeRef: root.shellContextRef.themeBridge",
            "readonly property var graphThemeBridgeRef: root.shellContextRef.graphThemeBridge",
            "readonly property var contentFullscreenBridgeRef: root.shellContextRef.contentFullscreenBridge",
            "readonly property var viewerHostServiceRef: root.shellContextRef.viewerHostService",
            "readonly property var canvasStateBridgeRef: root.shellContextRef.graphCanvasStateBridge",
            "readonly property var canvasCommandBridgeRef: root.shellContextRef.graphCanvasCommandBridge",
            "readonly property var canvasViewBridgeRef: root.shellContextRef.graphCanvasViewBridge",
            "WorkspaceCenterPane {",
            "graphCanvasStateBridgeRef: root.canvasStateBridgeRef",
            "graphCanvasCommandBridgeRef: root.canvasCommandBridgeRef",
            "workspaceBridgeRef: root.shellWorkspaceBridgeRef",
            "themeBridgeRef: root.themeBridgeRef",
            "overlayHostItem: root",
            "viewBridgeRef: root.canvasViewBridgeRef",
            "ShellStatusStrip {",
            "canvasStateBridgeRef: root.canvasStateBridgeRef",
            "scriptEditorBridgeRef: root.scriptEditorBridgeRef",
            "scriptHighlighterBridgeRef: root.scriptHighlighterBridgeRef",
        )

        for snippet in absent_snippets:
            with self.subTest(snippet=snippet, expectation="absent"):
                self.assertNotIn(snippet, qml_text)

        for snippet in present_snippets:
            with self.subTest(snippet=snippet, expectation="present"):
                self.assertIn(snippet, qml_text)

    def test_migrated_shell_components_do_not_reach_shell_context_directly(
        self,
    ) -> None:
        shell_component_root = _REPO_ROOT / "ea_node_editor/ui_qml/components/shell"
        for qml_path in shell_component_root.glob("*.qml"):
            qml_text = qml_path.read_text(encoding="utf-8")
            with self.subTest(path=qml_path.relative_to(_REPO_ROOT).as_posix()):
                self.assertNotIn("shellContext", qml_text)

    def test_graph_canvas_descendants_use_context_bundle_instead_of_raw_service_globals(
        self,
    ) -> None:
        expectations = {
            "ea_node_editor/ui_qml/components/graph_canvas/GraphCanvasContextMenus.qml": (
                (
                    "typeof addonManagerBridge",
                    "typeof helpBridge",
                    "themeBridge.palette",
                    "addonManagerBridge.",
                    "helpBridge.",
                ),
                (
                    "readonly property var shellContextRef",
                    "root.shellContextRef.addonManagerBridge",
                    "root.shellContextRef.helpBridge",
                    "root.themeBridgeRef ? root.themeBridgeRef.palette : ({})",
                ),
            ),
            "ea_node_editor/ui_qml/components/graph_canvas/GraphCanvasInputLayers.qml": (
                (
                    "typeof contentFullscreenBridge",
                    "typeof viewerSessionBridge",
                    "typeof shellLibraryBridge",
                    "themeBridge.palette",
                    "contentFullscreenBridge.",
                    "viewerSessionBridge.",
                    "shellLibraryBridge.show_graph_hint",
                ),
                (
                    "readonly property var shellContextRef",
                    "root.shellContextRef.contentFullscreenBridge",
                    "root.shellContextRef.viewerSessionBridge",
                    "root.shellContextRef.shellLibraryBridge",
                ),
            ),
            "ea_node_editor/ui_qml/components/graph/GraphNodeHost.qml": (
                (
                    "typeof graphThemeBridge",
                    "typeof addonManagerBridge",
                    "graphThemeBridge.node_palette",
                    "addonManagerBridge.requestOpen",
                ),
                (
                    "readonly property var shellContextRef",
                    "shellContextRef.graphThemeBridge",
                    "shellContextRef.addonManagerBridge",
                    "card.addonManagerBridgeRef.requestOpen",
                ),
            ),
        }

        for relative_path, (absent_snippets, present_snippets) in expectations.items():
            qml_text = (_REPO_ROOT / relative_path).read_text(encoding="utf-8")
            for snippet in absent_snippets:
                with self.subTest(
                    path=relative_path, snippet=snippet, expectation="absent"
                ):
                    self.assertNotIn(snippet, qml_text)
            for snippet in present_snippets:
                with self.subTest(
                    path=relative_path, snippet=snippet, expectation="present"
                ):
                    self.assertIn(snippet, qml_text)


class ShellStatusStripQmlBoundaryTests(unittest.TestCase):
    def test_status_strip_omits_removed_graphics_mode_controls(self) -> None:
        qml_path = (
            _REPO_ROOT / "ea_node_editor/ui_qml/components/shell/ShellStatusStrip.qml"
        )
        qml_text = qml_path.read_text(encoding="utf-8")

        absent_snippets = (
            "property var mainWindowRef",
            "property var canvasCommandBridgeRef",
        )
        present_snippets = (
            'objectName: "shellStatusStrip"',
            "property var canvasStateBridgeRef",
            "readonly property string statusBarLayout",
            "graphics_status_bar_layout",
            "readonly property bool telemetryHudLayout",
            "Layout.preferredHeight: root.telemetryHudLayout ? 46 : 32",
            'objectName: "shellStatusStripOption2TelemetryHud"',
        )

        for snippet in absent_snippets:
            with self.subTest(snippet=snippet, expectation="absent"):
                self.assertNotIn(snippet, qml_text)

        for snippet in present_snippets:
            with self.subTest(snippet=snippet, expectation="present"):
                self.assertIn(snippet, qml_text)


class GraphCanvasQmlBoundaryTests(unittest.TestCase):
    def test_graph_canvas_routes_owned_concerns_through_bridge_first_refs(self) -> None:
        qml_path = _REPO_ROOT / "ea_node_editor/ui_qml/components/GraphCanvas.qml"
        qml_text = qml_path.read_text(encoding="utf-8")

        absent_snippets = (
            "property var canvasBridge: null",
            "readonly property var canvasBridgeRef",
            "property var mainWindowBridge",
            "property var viewBridge: root.canvasStateBridgeRef",
            "readonly property var _canvasViewStateBridgeRef: root.canvasStateBridgeRef",
            "readonly property var _canvasViewCommandBridgeRef: root.canvasCommandBridgeRef",
            "mainWindowBridge.graphics_minimap_expanded",
            "mainWindowBridge.graphics_show_grid",
            "mainWindowBridge.graphics_show_minimap",
            "mainWindowBridge.graphics_node_shadow",
            "mainWindowBridge.graphics_shadow_strength",
            "mainWindowBridge.graphics_shadow_softness",
            "mainWindowBridge.graphics_shadow_offset",
            "mainWindowBridge.snap_to_grid_enabled",
            "mainWindowBridge.snap_grid_size",
            "mainWindowBridge.request_open_subnode_scope",
            "mainWindowBridge.browse_node_property_path",
            "mainWindowBridge.request_drop_node_from_library",
            "mainWindowBridge.request_connect_ports",
            "mainWindowBridge.request_open_connection_quick_insert",
            "sceneBridge.nodes_model",
            "sceneBridge.selected_node_lookup",
            "sceneBridge.select_node",
            "sceneBridge.set_node_property",
            "sceneBridge.are_port_kinds_compatible",
            "sceneBridge.are_data_types_compatible",
            "sceneBridge.move_nodes_by_delta",
            "sceneBridge.move_node",
            "sceneBridge.resize_node",
            "viewBridge.adjust_zoom",
            "viewBridge.pan_by",
            "viewBridge.set_viewport_size",
            "viewBridge.zoom_value",
            "viewBridge.center_x",
            "viewBridge.center_y",
            "property var hoveredPort: null",
            "property var pendingConnectionPort: null",
            "property var wireDragState: null",
            "property bool edgeContextVisible: false",
            "property bool interactionActive: false",
            "readonly property var _canvasCommandBridgeRef",
            "readonly property var _canvasShellBridgeRef",
            "readonly property var _canvasSceneBridgeRef",
            "readonly property var _canvasViewBridgeRef",
            "typeof graphCanvasViewBridge",
            "readonly property var _canvasShellCompatRef",
            "readonly property var _canvasSceneCompatRef",
            "readonly property var _canvasViewCompatRef",
            "readonly property var _canvasCompatBridgeRef",
            "readonly property var _legacyCanvasViewBridgeRef",
            "readonly property var _canvasSceneStateBridgeRef",
            "readonly property var _canvasShellCommandBridgeRef",
            "readonly property var _canvasSceneCommandBridgeRef",
            "readonly property var _canvasViewCommandBridgeRef",
            "shellCommandBridge: root._canvasShellCommandBridgeRef",
            "graphCanvasFacade",
            "canvasFacadeRef",
            "_facadeService",
            "graphCanvasFacadeAdapter",
            "_canvasStateBridgeRef",
            "_canvasViewStateBridgeRef",
        )
        present_snippets = (
            "property var canvasStateBridge: null",
            "property var canvasCommandBridge: null",
            "property var canvasViewBridge: null",
            "readonly property var _canvasViewportBridge: root.canvasViewBridge",
            "root.canvasStateBridge.viewport_bridge",
            "root.canvasCommandBridge.viewport_bridge",
            "readonly property var canvasStateBridgeRef: root.canvasStateBridge || null",
            "readonly property var canvasCommandBridgeRef: root.canvasCommandBridge || null",
            "readonly property var canvasViewBridgeRef: root._canvasViewportBridge",
            "readonly property var sceneStateBridge: root.canvasStateBridgeRef",
            "readonly property var sceneCommandBridge: root.canvasCommandBridgeRef",
            "readonly property var sceneBridge: root.canvasStateBridgeRef",
            "readonly property var viewBridge: root.canvasViewBridgeRef",
            "readonly property bool showGrid: preferenceFactsObject.showGrid",
            "GraphCanvasComponents.GraphCanvasInteractionState {",
            "GraphCanvasComponents.GraphCanvasSceneState {",
            "GraphCanvasComponents.GraphCanvasNodeSurfaceBridge {",
            "GraphCanvasComponents.GraphCanvasViewportController {",
            "GraphCanvasComponents.GraphCanvasSceneLifecycle {",
            "GraphCanvasComponents.GraphCanvasRootLayers {",
            "readonly property var canvasViewportController: viewportController",
            "readonly property var canvasSceneLifecycle: sceneLifecycle",
            "property alias hoveredPort: interactionState.hoveredPort",
            "property alias pendingConnectionPort: interactionState.pendingConnectionPort",
            "property alias interactionActive: interactionState.interactionActive",
            'GraphCanvasRootApi.invoke(interactionState, "updateLibraryDropPreview", [screenX, screenY, payload]);',
            'GraphCanvasRootApi.invoke(interactionState, "beginPortWireDrag", [nodeId, portKey, direction, sceneX, sceneY, screenX, screenY, modifiers]);',
            'GraphCanvasRootApi.invoke(viewportController, "applyWheelZoom", [eventObj], false);',
            'GraphCanvasRootApi.invoke(sceneLifecycle, "requestEdgeRedraw");',
            "sceneBridge: root.sceneStateBridge",
            "shellBridge: root.canvasCommandBridgeRef",
            "canvasCommandBridge: root.canvasCommandBridgeRef",
            "sceneCommandBridge: root.sceneCommandBridge",
            "sceneStateBridge: root.sceneStateBridge",
            "viewStateBridge: root.viewBridge",
            "viewCommandBridge: root.viewBridge",
        )

        for snippet in absent_snippets:
            with self.subTest(snippet=snippet, expectation="absent"):
                self.assertNotIn(snippet, qml_text)

        for snippet in present_snippets:
            with self.subTest(snippet=snippet, expectation="present"):
                self.assertIn(snippet, qml_text)

    def test_graph_canvas_root_layers_mount_node_link_hover_layer(self) -> None:
        qml_path = (
            _REPO_ROOT
            / "ea_node_editor/ui_qml/components/graph_canvas/GraphCanvasRootLayers.qml"
        )
        qml_text = qml_path.read_text(encoding="utf-8")

        for snippet in (
            "GraphOverlay.GraphNodeLinkHoverLayer {",
            'objectName: "graphNodeLinkHoverLayer"',
            "sceneStateBridge: root.sceneStateBridge",
            "sceneModel: root.visibleNodesModel",
            "hostResolver: root.hostForNodeId",
            "visibleSceneRectPayload: root.canvasItem ? root.canvasItem.visibleSceneRectPayload : ({})",
            "property var themePalette: ({})",
            "property var graphNodePalette: ({})",
            "readonly property var nodeLinkHoverPalette: ({",
            '"panel_bg": root._graphNodeToken("card_bg", root._shellToken("panel_bg", "#1b1d22"))',
            '"panel_title_fg": root._graphNodeToken("header_fg", root._shellToken("panel_title_fg", "#f0f4fb"))',
            '"accent": root._graphNodeToken("card_selected_border", root._shellToken("accent", "#60CDFF"))',
            "themePalette: root.nodeLinkHoverPalette",
        ):
            with self.subTest(snippet=snippet):
                self.assertIn(snippet, qml_text)

        node_link_block = qml_text.split("GraphOverlay.GraphNodeLinkHoverLayer {", 1)[
            1
        ].split("GraphOverlay.GraphEdgeFloatingToolbar {", 1)[0]
        self.assertNotIn("themePalette: root.themePalette", node_link_block)

    def test_graph_canvas_root_layers_mount_node_comment_count_pill_layer(self) -> None:
        qml_path = (
            _REPO_ROOT
            / "ea_node_editor/ui_qml/components/graph_canvas/GraphCanvasRootLayers.qml"
        )
        qml_text = qml_path.read_text(encoding="utf-8")
        popover_layer = (
            _REPO_ROOT
            / "ea_node_editor/ui_qml/components/graph/overlay/GraphNodeCommentPopoverLayer.qml"
        ).read_text(encoding="utf-8")

        for snippet in (
            "readonly property var nodeCommentPalette: ({",
            '"comment": root.nodeCommentPaletteDark ? "#F2B84B" : "#D58E1E"',
            '"success": root.nodeCommentPaletteDark ? "#64C88A" : "#247B4F"',
            "GraphOverlay.GraphNodeCommentPopoverLayer {",
            'objectName: "graphNodeCommentPopoverLayer"',
            "sceneModel: root.visibleNodesModel",
            "hostResolver: root.hostForNodeId",
            "themePalette: root.nodeCommentPalette",
        ):
            with self.subTest(file="root_layers", snippet=snippet):
                self.assertIn(snippet, qml_text)

        for snippet in (
            "height: 18",
            "radius: 9",
            "width: pillRow.implicitWidth + 16",
            "spacing: 4",
            "readonly property real badgeGap: 6",
            "readonly property real groupWidth: hasLinkBadge ? linkBadgeWidth + root.badgeGap + ownBadgeWidth : ownBadgeWidth",
            "GraphNodeSurfaceMetrics.nodeHasBottomNeutralFlowHandle(modelData)",
            "root.nodeX(modelData) + (root.nodeWidth(modelData) - groupWidth) / 2",
            "root.nodeY(modelData) + root.nodeHeight(modelData) - height / 2",
            "z: root.activeNodeData || root.editorOpen ? 38 : 34",
            'objectName: "graphNodeCommentPopoverCloseButton"',
            "RectangularShadow {",
            'iconName: "reply"',
            "onClicked: root.forceClearCard()",
            'var target = prefs ? String(prefs.nodeCommentEditorDefault || "canvas_popover") : "canvas_popover";',
            "canvasItem.requestNodeCommentEditorForNode",
        ):
            with self.subTest(file="comment_popover", snippet=snippet):
                self.assertIn(snippet, popover_layer)

    def test_graph_node_link_hover_card_routes_mockup_actions_and_type_colors(
        self,
    ) -> None:
        hover_layer = (
            _REPO_ROOT
            / "ea_node_editor/ui_qml/components/graph/overlay/GraphNodeLinkHoverLayer.qml"
        ).read_text(encoding="utf-8")
        graph_canvas = (
            _REPO_ROOT / "ea_node_editor/ui_qml/components/GraphCanvas.qml"
        ).read_text(encoding="utf-8")
        root_layers = (
            _REPO_ROOT
            / "ea_node_editor/ui_qml/components/graph_canvas/GraphCanvasRootLayers.qml"
        ).read_text(encoding="utf-8")
        context_menus = (
            _REPO_ROOT
            / "ea_node_editor/ui_qml/components/graph_canvas/GraphCanvasContextMenus.qml"
        ).read_text(encoding="utf-8")
        editor_form = (
            _REPO_ROOT
            / "ea_node_editor/ui_qml/components/common/NodeLinkEditorForm.qml"
        ).read_text(encoding="utf-8")
        inspector_links = (
            _REPO_ROOT
            / "ea_node_editor/ui_qml/components/shell/InspectorNodeLinksSection.qml"
        ).read_text(encoding="utf-8")
        workspace_center = (
            _REPO_ROOT
            / "ea_node_editor/ui_qml/components/shell/WorkspaceCenterPane.qml"
        ).read_text(encoding="utf-8")
        main_shell = (_REPO_ROOT / "ea_node_editor/ui_qml/MainShell.qml").read_text(
            encoding="utf-8"
        )

        for snippet in (
            "function linkTypeColor(kind)",
            'return "#3BA9F5"',
            'return "#8B7CF6"',
            'return "#F2B84B"',
            'return "#64C88A"',
            "function forceClearCard()",
            "if (removed)\n            forceClearCard();",
            "function linkGoesToGraphTarget(kind)",
            'normalized === "node" || normalized === "workspace"',
            "function linkPrimaryActionLabel(kind)",
            'linkGoesToGraphTarget(kind) ? "Go To" : "Open"',
            "function linkPrimaryActionIcon(kind)",
            'linkGoesToGraphTarget(kind) ? "navigate" : "external-link"',
            "function requestAddLink()",
            "canvasItem.requestAddNodeLinkForNode",
            "onClicked: root.requestAddLink()",
            "function openEditor(nodeData, workspaceId)",
            "readonly property bool editorSuspended: editorOpen && linkEditorForm.pickModeActive",
            "if (root.editorSuspended || root.editorRestoreInProgress)",
            "if (!root.editorSuspended && !root.editorRestoreInProgress)",
            "function editorSourceNodeData()",
            "canvasItem._sceneNodePayload(root.activeNodeId)",
            "Common.NodeLinkEditorForm {",
            'objectNamePrefix: "graphNodeLinkPopover"',
            "hideWhilePicking: true",
            "onSaveRequested: function(draft) { root.saveEditorDraft(draft); }",
            "onPickTargetRequested: function(kind) { root.requestEditorTargetPick(kind); }",
            "readonly property color typeColor: root.linkTypeColor",
            "root.linkIcon(root.editorOpen ? linkEditorForm.editingKind : (root.activeLink ? root.activeLink.kind : \"url\"))",
            "parent.typeColor",
            'text: root.linkPrimaryActionLabel(root.activeLink ? root.activeLink.kind : "url")',
            'iconName: root.linkPrimaryActionIcon(root.activeLink ? root.activeLink.kind : "url")',
        ):
            with self.subTest(file="hover_layer", snippet=snippet):
                self.assertIn(snippet, hover_layer)

        for qml_text, snippet in (
            (context_menus, 'if (normalized === "node_context::add_link") {'),
            (context_menus, "accepted = Boolean(root.canvasItem.requestAddNodeLinkForNode(nodeId));"),
            (graph_canvas, "function requestAddNodeLinkForNode(nodeId)"),
            (graph_canvas, "root.sceneCommandBridge.select_node(normalizedNodeId, false);"),
            (graph_canvas, "var nodeData = root._sceneNodePayload(normalizedNodeId);"),
            (graph_canvas, "return root.openNodeLinkEditor(nodeData, workspaceId);"),
            (graph_canvas, "function openNodeLinkEditor(nodeData, workspaceId)"),
            (root_layers, "function openNodeLinkEditor(nodeData, workspaceId)"),
            (root_layers, "return nodeLinkHoverLayer.openEditor(nodeData, workspaceId);"),
        ):
            with self.subTest(snippet=snippet):
                self.assertIn(snippet, qml_text)

        for qml_text in (graph_canvas, workspace_center, main_shell, inspector_links):
            with self.subTest(file="removed_inspector_redirect"):
                self.assertNotIn("nodeLinkAddRequested", qml_text)

        for snippet in (
            '{ label: "Web", value: "url" }',
            '{ label: "File", value: "file" }',
            '{ label: "Folder", value: "folder" }',
            '{ label: "Workspace", value: "workspace" }',
            '{ label: "Node", value: "node" }',
            "option ? option.label : \"\"",
            "option ? option.title : \"\"",
            "option ? option.subtitle : \"\"",
            "option ? option.workspace_name : \"\"",
            "option ? option.display_name : \"\"",
            "option ? option.instance_label : \"\"",
            "return results.slice(0, 8);",
            "editingTargetNodeId = String(option.target_node_id || option.target || \"\").trim();",
            "editingTargetWorkspaceId = String(option.target_workspace_id || \"\").trim();",
            "if (!target.length)",
            "enabled: form.currentTarget().length > 0",
            "if (!String(storedId || \"\").length)",
            "_resetEditor();",
            "visible: editorOpen && (!pickModeActive || !hideWhilePicking)",
        ):
            with self.subTest(file="shared_editor_form", snippet=snippet):
                self.assertIn(snippet, editor_form)

        upsert_call = hover_layer.split("var storedId = bridge.upsert_node_link(", 1)[1].split(
            ");", 1
        )[0]
        arguments = [
            line.strip().removesuffix(",")
            for line in upsert_call.splitlines()
            if line.strip()
        ]
        self.assertEqual(
            arguments,
            [
                "root.activeNodeId",
                '""',
                'String(draft.kind || "url")',
                'String(draft.title || "")',
                'String(draft.target || "")',
                'String(draft.subtitle || "")',
                'String(draft.target_workspace_id || "")',
                'String(draft.target_node_id || "")',
            ],
        )
        self.assertIn("return linkEditorForm.completeSave(storedId);", hover_layer)

    def test_graph_node_comment_badge_routes_to_canvas_or_inspector_editor(
        self,
    ) -> None:
        graph_canvas = (
            _REPO_ROOT / "ea_node_editor/ui_qml/components/GraphCanvas.qml"
        ).read_text(encoding="utf-8")
        workspace_center = (
            _REPO_ROOT
            / "ea_node_editor/ui_qml/components/shell/WorkspaceCenterPane.qml"
        ).read_text(encoding="utf-8")
        inspector_pane = (
            _REPO_ROOT / "ea_node_editor/ui_qml/components/shell/InspectorPane.qml"
        ).read_text(encoding="utf-8")
        main_shell = (_REPO_ROOT / "ea_node_editor/ui_qml/MainShell.qml").read_text(
            encoding="utf-8"
        )
        options_menu = (
            _REPO_ROOT
            / "ea_node_editor/ui_qml/components/graph_canvas/GraphCanvasOptionsMenu.qml"
        ).read_text(encoding="utf-8")

        for qml_text, snippet in (
            (
                graph_canvas,
                "signal nodeCommentEditorRequested(string nodeId, bool compose)",
            ),
            (graph_canvas, "function requestNodeCommentEditorForNode(nodeId, compose)"),
            (
                graph_canvas,
                "root.nodeCommentEditorRequested(normalizedNodeId, Boolean(compose));",
            ),
            (
                workspace_center,
                "signal nodeCommentEditorRequested(string nodeId, bool compose)",
            ),
            (
                workspace_center,
                "onNodeCommentEditorRequested: function(nodeId, compose)",
            ),
            (main_shell, "onNodeCommentEditorRequested: function(_nodeId, compose)"),
            (main_shell, "inspectorPane.beginAddCommentForSelectedNode()"),
            (main_shell, "inspectorPane.openCommentsForSelectedNode()"),
            (inspector_pane, "function openCommentsForSelectedNode()"),
            (inspector_pane, "function beginAddCommentForSelectedNode()"),
            (inspector_pane, "root.activeTabIndex = 0"),
            (inspector_pane, "nodeCommentsSection.markRead()"),
            (inspector_pane, 'nodeCommentsSection.beginNewComment("")'),
            (options_menu, "readonly property string nodeCommentEditorDefaultValue"),
            (options_menu, "function setNodeCommentEditorDefault(value)"),
            (options_menu, "set_graphics_node_comment_editor_default"),
            (options_menu, 'label: "Comments"'),
        ):
            with self.subTest(snippet=snippet):
                self.assertIn(snippet, qml_text)

    def test_graph_canvas_tooltip_qml_surfaces_bind_to_bridge_first_policy_and_preserve_inactive_explanations(
        self,
    ) -> None:
        expectations = {
            "ea_node_editor/ui_qml/components/graph_canvas/GraphCanvasPreferenceFacts.qml": (
                ("graphics_show_tooltips",),
                (
                    'import "../common/TooltipPolicy.js" as TooltipPolicy',
                    "readonly property var tooltipCategoryVisibility: TooltipPolicy.categoryVisibility(facts.stateBridge)",
                    'readonly property bool showTooltips: facts.tooltipCategoryEnabled("general")',
                    "function tooltipCategoryEnabled(category)",
                ),
            ),
            "ea_node_editor/ui_qml/components/graph/surface_controls/GraphSurfaceButton.qml": (
                (
                    "function _tooltipBridge() {",
                    "graphics_show_tooltips",
                    "ToolTip.visible:",
                ),
                (
                    'import "../../common" as Common',
                    'property string tooltipCategory: "general"',
                    "readonly property var tooltipPolicyBridge:",
                    "Common.ManagedToolTip {",
                    "policyBridge: control.tooltipPolicyBridge",
                    "active: control.tooltipVisible",
                ),
            ),
            "ea_node_editor/ui_qml/components/graph_canvas/GraphCanvasMinimapOverlay.qml": (
                (
                    "function _tooltipBridge() {",
                    "graphics_show_tooltips",
                    "ToolTip.visible:",
                ),
                (
                    'import "../common" as Common',
                    'import "../common/TooltipCopy.js" as TooltipCopy',
                    "readonly property string toggleTooltipKey:",
                    "property string tooltipCategory: TooltipCopy.category(tooltipCopyBridge, root.toggleTooltipKey)",
                    "readonly property var tooltipPolicyBridge:",
                    "Common.ManagedToolTip {",
                    "policyBridge: root.tooltipPolicyBridge",
                    "category: root.tooltipCategory",
                    "active: minimapToggleMouse.containsMouse",
                    "text: TooltipCopy.text(tooltipCopyBridge, root.toggleTooltipKey)",
                ),
            ),
            "ea_node_editor/ui_qml/components/graph_canvas/GraphCanvasOptionsMenu.qml": (
                (
                    "function _tooltipBridge() {",
                    "graphics_show_tooltips",
                    "ToolTip.visible:",
                ),
                (
                    'import "../common" as Common',
                    "readonly property var tooltipPolicyBridge:",
                    "Common.ManagedToolTip {",
                    "policyBridge: root.tooltipPolicyBridge",
                    "category: parent.tooltipCategory",
                    "active: toggleMouseArea.containsMouse && !parent.dim",
                ),
            ),
            "ea_node_editor/ui_qml/components/graph_canvas/GraphCanvasContextMenus.qml": (
                (
                    "function _tooltipBridge() {",
                    "graphics_show_tooltips",
                    "ToolTip.visible:",
                    '"tooltipText": TooltipCopy.text(tooltipCopyBridge, "graph.node_context.toggle_settings")',
                    '"tooltipCategory": TooltipCopy.category(tooltipCopyBridge, "graph.node_context.toggle_settings")',
                ),
                (
                    'import "../common/TooltipCopy.js" as TooltipCopy',
                    "tooltipPolicyBridge: root.canvasItem ? root.canvasItem.canvasStateBridgeRef : null",
                ),
            ),
            "ea_node_editor/ui_qml/components/graph/GraphNodePortsLayer.qml": (
                (
                    "function _tooltipBridge() {",
                    "graphics_show_tooltips",
                    "ToolTip.visible:",
                ),
                (
                    'import "../common" as Common',
                    'import "../common/TooltipPolicy.js" as TooltipPolicy',
                    "readonly property var tooltipPolicyBridge:",
                    "Common.ManagedToolTip {",
                ),
            ),
            "ea_node_editor/ui_qml/components/graph/GraphNodePortRow.qml": (
                (
                    "function _tooltipBridge() {",
                    "graphics_show_tooltips",
                    "ToolTip.visible:",
                ),
                (
                    'import "../common" as Common',
                    'import "../common/TooltipPolicy.js" as TooltipPolicy',
                    'property bool infoTooltipsEnabled: TooltipPolicy.categoryEnabled(',
                    'property bool inactiveTooltipsEnabled: TooltipPolicy.categoryEnabled(',
                    "property bool tooltipVisible: TooltipPolicy.tooltipVisible(",
                    "property bool inactiveTooltipVisible: TooltipPolicy.tooltipVisible(",
                    "category: row.isInput ? portMouse.activeTooltipCategory : \"general\"",
                    "Common.ManagedToolTip {",
                ),
            ),
        }

        for relative_path, (absent_snippets, present_snippets) in expectations.items():
            qml_text = (_REPO_ROOT / relative_path).read_text(encoding="utf-8")
            for snippet in absent_snippets:
                with self.subTest(
                    path=relative_path, snippet=snippet, expectation="absent"
                ):
                    self.assertNotIn(snippet, qml_text)
            for snippet in present_snippets:
                with self.subTest(
                    path=relative_path, snippet=snippet, expectation="present"
                ):
                    self.assertIn(snippet, qml_text)

    def test_graph_canvas_state_sources_expose_tooltip_category_policy_contract(
        self,
    ) -> None:
        expectations = {
            "ea_node_editor/ui_qml/graph_canvas_state/graphics_preferences_props.py": (
                "def graphics_tooltip_categories(self) -> dict[str, bool]:",
                "def graphics_tooltip_category_visibility(self) -> dict[str, bool]:",
                "def tooltip_category_enabled(self, category: str) -> bool:",
                "TOOLTIP_CATEGORY_NAMES",
            ),
            "ea_node_editor/ui/shell/window.py": (
                "graphics_tooltip_categories = pyqtProperty(",
                "graphics_tooltip_category_visibility = pyqtProperty(",
            ),
        }

        for relative_path, present_snippets in expectations.items():
            source_text = (_REPO_ROOT / relative_path).read_text(encoding="utf-8")
            for snippet in present_snippets:
                with self.subTest(path=relative_path, snippet=snippet):
                    self.assertIn(snippet, source_text)

    def test_managed_tooltip_qml_contract_defaults_plain_text_and_requires_explicit_format_opt_in(
        self,
    ) -> None:
        managed_tooltip = (
            _REPO_ROOT / "ea_node_editor/ui_qml/components/common/ManagedToolTip.qml"
        ).read_text(encoding="utf-8")
        tooltip_policy = (
            _REPO_ROOT / "ea_node_editor/ui_qml/components/common/TooltipPolicy.js"
        ).read_text(encoding="utf-8")

        present_snippets = (
            "property int textFormat: Text.PlainText",
            "textFormat: control.textFormat",
            "property int maximumTextWidth: 360",
            "wrapMode: Text.WordWrap",
            "implicitWidth: Math.min(implicitContentWidth, maximumTextWidth)",
            "readonly property bool managedVisible: TooltipPolicy.tooltipVisible(",
            "popupType: Popup.Window",
        )
        for snippet in present_snippets:
            with self.subTest(source="ManagedToolTip.qml", snippet=snippet):
                self.assertIn(snippet, managed_tooltip)

        absent_snippets = (
            "Text.AutoText",
            "Text.RichText",
            "Text.StyledText",
            'indexOf("<"',
            'search("<"',
        )
        for snippet in absent_snippets:
            with self.subTest(source="ManagedToolTip.qml", snippet=snippet):
                self.assertNotIn(snippet, managed_tooltip)

        policy_snippets = (
            "function categoryEnabled(bridge, category)",
            "var visibleValue = mapCategoryValue(bridge.graphics_tooltip_category_visibility, normalized);",
            "var categoryValue = mapCategoryValue(bridge.graphics_tooltip_categories, normalized);",
            "if (normalized === CRITICAL)",
            "if (normalized === GENERAL && bridge.graphics_show_tooltips !== undefined)",
        )
        for snippet in policy_snippets:
            with self.subTest(source="TooltipPolicy.js", snippet=snippet):
                self.assertIn(snippet, tooltip_policy)

    def test_managed_tooltip_qml_contract_guards_popup_window_dismissal_lifecycle(
        self,
    ) -> None:
        managed_tooltip = (
            _REPO_ROOT / "ea_node_editor/ui_qml/components/common/ManagedToolTip.qml"
        ).read_text(encoding="utf-8")

        # popupType: Popup.Window makes an open tooltip a real top-level OS
        # window. Qt does not withdraw one when the app loses focus, when the
        # host is minimized, or when a hover-exit event is never delivered, so
        # these guards are what stop a tooltip floating over the desktop.
        present_snippets = (
            "popupType: Popup.Window",
            "readonly property bool _lifecycleAllowsTooltip: Qt.application.active",
            "&& control._hostWindowShown",
            "&& control._anchorPresentable",
            "&& !control._anchorMoved",
            "active && text.length > 0 && control._lifecycleAllowsTooltip",
            "visibility !== Window.Hidden",
            "readonly property bool _anchorPresentable: !!control.parent && control.parent.visible",
            "running: control.visible && !!control.parent",
            "control._anchorMoved = true;",
        )
        for snippet in present_snippets:
            with self.subTest(source="ManagedToolTip.qml", snippet=snippet):
                self.assertIn(snippet, managed_tooltip)

        timeout_lines = [
            line.strip()
            for line in managed_tooltip.splitlines()
            if line.strip().startswith("timeout:")
        ]
        self.assertEqual(len(timeout_lines), 1, timeout_lines)
        timeout_ms = int(timeout_lines[0].split(":", 1)[1].strip())
        self.assertGreaterEqual(timeout_ms, 1000)

        # Window.active is permanently false under QQuickWidget: the QML scene
        # lives in a QQuickWidgetOffscreenWindow the window manager never
        # activates, so guarding on it suppresses every tooltip in the app.
        # Qt.application.active is the signal that tracks foreign-app focus.
        absent_snippets = (
            "Window.window.active",
            "window.active &&",
        )
        for snippet in absent_snippets:
            with self.subTest(source="ManagedToolTip.qml", snippet=snippet):
                self.assertNotIn(snippet, managed_tooltip)

    def test_graph_typography_qml_contract_exposes_canvas_binding_and_shared_role_names(
        self,
    ) -> None:
        expectations = {
            "ea_node_editor/ui_qml/components/graph_canvas/GraphCanvasPreferenceFacts.qml": (
                "readonly property int graphLabelPixelSize",
                "graphics_graph_label_pixel_size",
            ),
            "ea_node_editor/ui_qml/components/graph/GraphSharedTypography.qml": (
                'objectName: "graphSharedTypography"',
                "property int graphLabelPixelSize",
                "readonly property int nodeTitlePixelSize",
                "readonly property int portLabelPixelSize",
                "readonly property int elapsedFooterPixelSize",
                "readonly property int inlinePropertyPixelSize",
                "readonly property int badgePixelSize",
                "readonly property int badgeIconPixelSize",
                "readonly property int edgeLabelPixelSize",
                "readonly property int edgePillPixelSize",
                "readonly property int nodeTitleFontWeight",
                "readonly property int portLabelFontWeight",
                "readonly property int inlinePropertyFontWeight",
                "readonly property int badgeFontWeight",
                "readonly property int edgeLabelFontWeight",
                "readonly property int edgePillFontWeight",
            ),
        }

        for relative_path, present_snippets in expectations.items():
            qml_text = (_REPO_ROOT / relative_path).read_text(encoding="utf-8")
            for snippet in present_snippets:
                with self.subTest(path=relative_path, snippet=snippet):
                    self.assertIn(snippet, qml_text)

    def test_graph_node_icon_size_qml_contract_exposes_canvas_binding_and_shared_role_name(
        self,
    ) -> None:
        expectations = {
            "ea_node_editor/ui_qml/components/graph_canvas/GraphCanvasPreferenceFacts.qml": (
                "readonly property var graphNodeIconPixelSizeOverride",
                "readonly property int nodeTitleIconPixelSize",
                "graphics_graph_node_icon_pixel_size_override",
                "graphics_node_title_icon_pixel_size",
            ),
            "ea_node_editor/ui_qml/components/graph/GraphSharedTypography.qml": (
                "property int graphNodeIconPixelSize",
                "readonly property int nodeTitleIconPixelSize",
            ),
        }

        for relative_path, present_snippets in expectations.items():
            qml_text = (_REPO_ROOT / relative_path).read_text(encoding="utf-8")
            for snippet in present_snippets:
                with self.subTest(path=relative_path, snippet=snippet):
                    self.assertIn(snippet, qml_text)

    def test_persistent_node_elapsed_canvas_qml_properties_bind_only_to_state_bridge_execution_contract(
        self,
    ) -> None:
        expectations = {
            "ea_node_editor/ui_qml/components/GraphCanvas.qml": (
                "readonly property var runningNodeStartedAtMsLookup: executionFactsObject.runningNodeStartedAtMsLookup",
                "readonly property var nodeElapsedMsLookup: executionFactsObject.nodeElapsedMsLookup",
                "readonly property string nodeElapsedTimeUnit: executionFactsObject.nodeElapsedTimeUnit",
                "readonly property var warningNodeLookup: executionFactsObject.warningNodeLookup",
            ),
            "ea_node_editor/ui_qml/components/graph_canvas/GraphCanvasExecutionFacts.qml": (
                "readonly property var warningNodeLookup: facts.stateBridge",
                "facts.stateBridge.warning_node_lookup",
                "readonly property var runningNodeStartedAtMsLookup: facts.stateBridge",
                "facts.stateBridge.running_node_started_at_ms_lookup",
                "readonly property var nodeElapsedMsLookup: facts.stateBridge",
                "facts.stateBridge.node_elapsed_ms_lookup",
                "readonly property string nodeElapsedTimeUnit: facts.stateBridge",
                "facts.stateBridge.graphics_node_elapsed_time_unit",
            ),
            "ea_node_editor/ui_qml/components/graph_canvas/GraphCanvasPreferenceFacts.qml": (
                "readonly property string nodeElapsedTimeVisibility: facts.stateBridge",
                "facts.stateBridge.graphics_node_elapsed_time_visibility",
            ),
            "ea_node_editor/ui_qml/components/graph/GraphNodeHost.qml": (
                "[\"data.boolean_toggle\", \"data.number_slider\", \"data.select\", \"core.trigger\", \"core.constant\"]",
            ),
        }

        for relative_path, present_snippets in expectations.items():
            qml_text = (_REPO_ROOT / relative_path).read_text(encoding="utf-8")

            for snippet in present_snippets:
                with self.subTest(path=relative_path, snippet=snippet):
                    self.assertIn(snippet, qml_text)

    def test_solution_freshness_qml_transport_has_no_styling_consumer(self) -> None:
        facts = (
            _REPO_ROOT
            / "ea_node_editor/ui_qml/components/graph_canvas/GraphCanvasExecutionFacts.qml"
        ).read_text(encoding="utf-8")
        host = (
            _REPO_ROOT / "ea_node_editor/ui_qml/components/graph/GraphNodeHost.qml"
        ).read_text(encoding="utf-8")
        self.assertIn("readonly property var nodeSolutionFreshnessLookup", facts)
        self.assertIn("facts.stateBridge.node_solution_freshness_lookup", facts)
        self.assertNotIn("nodeSolutionFreshnessLookup", host)

    def test_graph_canvas_interaction_state_helper_owns_extracted_canvas_state(
        self,
    ) -> None:
        helper_path = (
            _REPO_ROOT
            / "ea_node_editor/ui_qml/components/graph_canvas/GraphCanvasInteractionState.qml"
        )
        helper_text = helper_path.read_text(encoding="utf-8")

        present_snippets = (
            "property var pendingConnectionPort: null",
            "property var wireDragState: null",
            "property bool edgeContextVisible: false",
            "property bool interactionActive: false",
            "property var interactionIdleTimer: null",
            "function updateLibraryDropPreview(screenX, screenY, payload) {",
            "function finishPortWireDrag(nodeId, portKey, direction, _sceneX, _sceneY, screenX, screenY, dragActive, modifiers) {",
            "function _openNodeContext(nodeId, x, y) {",
            "function resetSceneBridgeState() {",
        )

        for snippet in present_snippets:
            with self.subTest(snippet=snippet):
                self.assertIn(snippet, helper_text)

    def test_graph_canvas_helper_components_hold_scene_surface_and_delegate_logic(
        self,
    ) -> None:
        expectations = {
            "ea_node_editor/ui_qml/components/graph_canvas/GraphCanvasSceneState.qml": (
                "property var selectedEdgeIds: []",
                "function sceneNodePayload(nodeId) {",
                "function syncEdgePayload() {",
                'bridge && typeof bridge.selected_node_lookup !== "undefined"',
                'bridge && typeof bridge.selected_node_ids !== "undefined"',
            ),
            "ea_node_editor/ui_qml/components/graph_canvas/GraphCanvasNodeSurfaceBridge.qml": (
                "GraphCanvasSurfaceInteractionHost {",
                "function requestOpenSubnodeScope(nodeId) {",
                "function commitNodeSurfaceProperties(nodeId, properties) {",
                "function browseNodePropertyPath(nodeId, key, currentPath) {",
                "function pickNodePropertyColor(nodeId, key, currentValue) {",
                "bridge.pick_node_property_color",
                "return hostInteraction.sceneSelectionBridge();",
                "hostInteraction.resetSurfaceInteractionState();",
            ),
            "ea_node_editor/ui_qml/components/graph_canvas/GraphCanvasViewportController.qml": (
                "function applyWheelZoom(eventObj) {",
                "function requestViewStateRedraw() {",
                "function updateViewportSize() {",
            ),
            "ea_node_editor/ui_qml/components/graph_canvas/GraphCanvasSceneLifecycle.qml": (
                "function handleSceneMutation() {",
                "function resetCanvasSceneState() {",
                "target: root.sceneStateBridge",
            ),
            "ea_node_editor/ui_qml/components/graph_canvas/GraphCanvasNodeDelegate.qml": (
                "GraphComponents.GraphNodeHost {",
                "property bool backdropInputOverlay: false",
                "canvasItem.requestEdgeRedraw",
            ),
            "ea_node_editor/ui_qml/components/graph_canvas/GraphCanvasWorldLayer.qml": (
                "property bool backdropInputOverlay: false",
                "delegate: GraphCanvasNodeDelegate {",
                "scale: viewBridge ? viewBridge.zoom_value : 1.0",
            ),
        }

        for relative_path, present_snippets in expectations.items():
            qml_text = (_REPO_ROOT / relative_path).read_text(encoding="utf-8")
            for snippet in present_snippets:
                with self.subTest(path=relative_path, snippet=snippet):
                    self.assertIn(snippet, qml_text)

    def test_graph_canvas_root_exposes_color_picker_helper_through_node_surface_bridge(
        self,
    ) -> None:
        qml_text = (
            _REPO_ROOT / "ea_node_editor/ui_qml/components/GraphCanvas.qml"
        ).read_text(encoding="utf-8")

        present_snippets = (
            "function pickNodePropertyColor(nodeId, key, currentValue) {",
            'GraphCanvasRootApi.invoke(nodeSurfaceBridge, "pickNodePropertyColor", [nodeId, key, currentValue], "")',
        )

        for snippet in present_snippets:
            with self.subTest(snippet=snippet):
                self.assertIn(snippet, qml_text)

    def test_graph_canvas_root_exposes_tabular_preview_helper_through_node_surface_bridge(
        self,
    ) -> None:
        qml_text = (
            _REPO_ROOT / "ea_node_editor/ui_qml/components/GraphCanvas.qml"
        ).read_text(encoding="utf-8")

        present_snippets = (
            "function describeNodeSurfaceTabularPreview(properties, request) {",
            'GraphCanvasRootApi.invoke(nodeSurfaceBridge, "describeNodeSurfaceTabularPreview", [properties, request], ({}))',
        )

        for snippet in present_snippets:
            with self.subTest(snippet=snippet):
                self.assertIn(snippet, qml_text)

    def test_overlay_host_item_plumbing_remains_live_for_canvas_overlay_paths(
        self,
    ) -> None:
        expectations = {
            "ea_node_editor/ui_qml/MainShell.qml": (
                "WorkspaceCenterPane {",
                "overlayHostItem: root",
            ),
            "ea_node_editor/ui_qml/components/shell/WorkspaceCenterPane.qml": (
                "property var overlayHostItem",
                "overlayHostItem: root.overlayHostItem",
            ),
            "ea_node_editor/ui_qml/components/GraphCanvas.qml": (
                "property var overlayHostItem: null",
            ),
            "ea_node_editor/ui_qml/components/graph_canvas/GraphCanvasInputLayers.qml": (
                "var overlayHost = root.canvasItem.overlayHostItem || root.canvasItem;",
            ),
            "ea_node_editor/ui_qml/components/graph_canvas/GraphCanvasInteractionState.qml": (
                "root.canvasItem.overlayHostItem ? root.canvasItem.overlayHostItem : root.canvasItem",
            ),
        }

        for relative_path, present_snippets in expectations.items():
            qml_text = (_REPO_ROOT / relative_path).read_text(encoding="utf-8")
            for snippet in present_snippets:
                with self.subTest(path=relative_path, snippet=snippet):
                    self.assertIn(snippet, qml_text)


__all__ = [
    "ShellLibraryBridgeQmlBoundaryTests",
    "ShellInspectorBridgeQmlBoundaryTests",
    "ShellWorkspaceBridgeQmlBoundaryTests",
    "GraphCanvasQmlBoundaryTests",
]

from __future__ import annotations

import copy
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from PyQt6.QtCore import QObject, Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QLabel, QScrollArea

from ea_node_editor.settings import DEFAULT_GRAPHICS_SETTINGS
from ea_node_editor.ui.dialogs.graphics_settings_dialog import GraphicsSettingsDialog
from ea_node_editor.ui.dialogs.sectioned_settings_dialog import SectionedSettingsDialog
from ea_node_editor.ui.graph_theme.registry import graph_theme_choices, resolve_graph_theme
from ea_node_editor.ui.shell.tooltip_policy import default_tooltip_category_preferences


_EXPAND_COLLISION_TOOLTIP_CASES = (
    (
        "expand_collision_enabled_check",
        "Pushes newly expanded items away from nearby content to reduce overlap.",
    ),
    (
        "expand_collision_strategy_combo",
        "Chooses how the first items are picked when overlap resolution begins.",
    ),
    (
        "expand_collision_animate_check",
        "Animates the repositioning pass so the settled layout stays readable.",
    ),
    (
        "expand_collision_scope_combo",
        "Limits which nearby items can move when the expanded area needs room.",
    ),
    (
        "expand_collision_gap_preset_combo",
        "Sets the target spacing kept between the expanded area and moved items.",
    ),
    (
        "expand_collision_radius_mode_combo",
        "Controls whether overlap checks stay local or search across the full canvas.",
    ),
    (
        "expand_collision_local_radius_preset_combo",
        "Sets how far the local search reaches when reach mode stays nearby.",
    ),
)


def _set_next_combo_index(combo) -> None:  # noqa: ANN001
    if combo.count() > 1:
        combo.setCurrentIndex((combo.currentIndex() + 1) % combo.count())


def _apply_roundtrip_mutations(dialog: GraphicsSettingsDialog) -> None:
    dialog.show_grid_check.setChecked(False)
    dialog.show_port_labels_check.setChecked(False)
    dialog.expand_collision_enabled_check.setChecked(True)
    _set_next_combo_index(dialog.expand_collision_strategy_combo)
    _set_next_combo_index(dialog.expand_collision_scope_combo)
    _set_next_combo_index(dialog.expand_collision_gap_preset_combo)
    _set_next_combo_index(dialog.expand_collision_radius_mode_combo)
    _set_next_combo_index(dialog.expand_collision_local_radius_preset_combo)
    dialog.expand_collision_animate_check.setChecked(False)


class _RecordingGraphicsSettingsController:
    def __init__(self) -> None:
        self.applied_graphics: list[tuple[dict[str, object], object]] = []

    def graphics_settings(self) -> dict[str, object]:
        return copy.deepcopy(DEFAULT_GRAPHICS_SETTINGS)

    def graph_theme_choices(self) -> list[tuple[str, str]]:
        return list(graph_theme_choices())

    def set_graphics_settings(self, graphics: dict[str, object], *, host: object) -> None:
        self.applied_graphics.append((copy.deepcopy(graphics), host))


class _TooltipPolicyHost(QObject):
    def __init__(self, *, general_tooltips: bool) -> None:
        super().__init__()
        self.graphics_show_tooltips = bool(general_tooltips)
        self.project_path = ""
        self.model = SimpleNamespace(project=SimpleNamespace(metadata={}))
        self.app_preferences_controller = _RecordingGraphicsSettingsController()


class GraphicsSettingsDialogTests(unittest.TestCase):

    def test_action_buttons_stay_reachable_when_settings_pages_scroll(self) -> None:
        dialog = GraphicsSettingsDialog()
        try:
            scroll_area = dialog.findChild(QScrollArea, "sectionedSettingsPageScrollArea")
            self.assertIsNotNone(scroll_area)
            self.assertEqual(scroll_area.widget(), dialog.page_stack)
            self.assertFalse(scroll_area.isAncestorOf(dialog.cancel_button))
            self.assertFalse(scroll_area.isAncestorOf(dialog.ok_button))
            self.assertLessEqual(dialog.minimumSizeHint().height(), 620)

            dialog.resize(760, 520)
            dialog.show()
            QApplication.instance().processEvents()

            for section_label in ("Canvas", "Theme", "Layout"):
                with self.subTest(section=section_label):
                    matches = dialog.section_list.findItems(
                        section_label,
                        Qt.MatchFlag.MatchExactly,
                    )
                    self.assertEqual(len(matches), 1)
                    dialog.section_list.setCurrentItem(matches[0])
                    QApplication.instance().processEvents()

                    self.assertLessEqual(dialog.height(), 620)
                    for button in (dialog.cancel_button, dialog.ok_button):
                        geometry = button.geometry()
                        self.assertGreaterEqual(geometry.top(), dialog.rect().top())
                        self.assertLessEqual(geometry.bottom(), dialog.rect().bottom())
        finally:
            dialog.close()

    def test_dialog_defaults_and_values_roundtrip(self) -> None:
        dialog = GraphicsSettingsDialog()
        try:
            self.assertIsInstance(dialog, SectionedSettingsDialog)
            self.assertEqual(
                [dialog.section_list.item(index).text() for index in range(dialog.section_list.count())],
                ["Canvas", "Interaction", "Performance", "Theme", "Layout"],
            )
            self.assertEqual(dialog.values(), DEFAULT_GRAPHICS_SETTINGS)
            self.assertFalse(dialog.keep_expanded_node_width_check.isChecked())
            self.assertEqual(dialog.show_port_labels_check.objectName(), "graphicsSettingsShowPortLabelsCheck")
            self.assertEqual(
                dialog.notched_ports_check.objectName(),
                "graphicsSettingsNotchedPortsCheck",
            )
            self.assertEqual(
                dialog.show_canvas_options_button_check.objectName(),
                "graphicsSettingsShowCanvasOptionsButtonCheck",
            )
            self.assertEqual(
                dialog.media_panel_show_title_check.objectName(),
                "graphicsSettingsMediaPanelShowTitleCheck",
            )
            self.assertEqual(
                dialog.media_panel_show_frame_check.objectName(),
                "graphicsSettingsMediaPanelShowFrameCheck",
            )
            self.assertEqual(
                dialog.media_panel_autoplay_animations_check.objectName(),
                "graphicsSettingsMediaPanelAutoplayAnimationsCheck",
            )
            self.assertEqual(
                dialog.media_panel_source_input_exposed_check.objectName(),
                "graphicsSettingsMediaPanelSourceInputExposedCheck",
            )
            self.assertEqual(
                dialog.media_panel_source_input_exposed_check.text(),
                "Expose Source input on blank Media Panels",
            )
            helper = dialog.findChild(QLabel, "graphicsSettingsMediaPanelDefaultsHelper")
            self.assertIsNotNone(helper)
            self.assertIn("future blank Media Panels only", helper.text())
            self.assertEqual(
                dialog.edge_crossing_style_combo.objectName(),
                "graphicsSettingsEdgeCrossingStyleCombo",
            )
            self.assertEqual(
                dialog.node_elapsed_time_unit_combo.objectName(),
                "graphicsSettingsNodeElapsedTimeUnitCombo",
            )
            self.assertEqual(
                dialog.node_elapsed_time_visibility_combo.objectName(),
                "graphicsSettingsNodeElapsedTimeVisibilityCombo",
            )
            self.assertEqual(
                dialog.node_comment_editor_default_combo.objectName(),
                "graphicsSettingsNodeCommentEditorDefaultCombo",
            )
            self.assertEqual(
                dialog.plot_lightweight_canvas_check.objectName(),
                "graphicsSettingsPlotLightweightCanvasCheck",
            )
            self.assertEqual(
                dialog.node_toolbar_opens_on_hover_check.objectName(),
                "graphicsSettingsNodeToolbarOpensOnHoverCheck",
            )
            self.assertTrue(dialog.show_canvas_options_button_check.isChecked())
            self.assertTrue(dialog.show_port_labels_check.isChecked())
            self.assertTrue(dialog.notched_ports_check.isChecked())
            self.assertFalse(dialog.node_toolbar_opens_on_hover_check.isChecked())
            self.assertTrue(dialog.media_panel_show_title_check.isChecked())
            self.assertTrue(dialog.media_panel_show_frame_check.isChecked())
            self.assertTrue(dialog.media_panel_autoplay_animations_check.isChecked())
            self.assertTrue(dialog.media_panel_source_input_exposed_check.isChecked())
            self.assertFalse(dialog.plot_lightweight_canvas_check.isChecked())
            self.assertEqual(
                {
                    category: check.isChecked()
                    for category, check in dialog.tooltip_category_checks.items()
                },
                default_tooltip_category_preferences(),
            )
            self.assertEqual(dialog.edge_crossing_style_combo.currentData(), "none")
            self.assertEqual(dialog.node_elapsed_time_visibility_combo.currentData(), "always")
            self.assertEqual(dialog.node_elapsed_time_unit_combo.currentData(), "seconds")
            self.assertEqual(dialog.node_comment_editor_default_combo.currentData(), "canvas_popover")
            self.assertEqual(
                dialog.status_bar_layout_option_1_button.objectName(),
                "graphicsSettingsStatusBarLayoutOption1Radio",
            )
            self.assertEqual(
                dialog.status_bar_layout_option_2_button.objectName(),
                "graphicsSettingsStatusBarLayoutOption2Radio",
            )
            self.assertTrue(dialog.status_bar_layout_option_1_button.isChecked())
            self.assertFalse(dialog.status_bar_layout_option_2_button.isChecked())
            self.assertEqual(
                dialog.show_fps_telemetry_check.objectName(),
                "graphicsSettingsShowFpsTelemetryCheck",
            )
            self.assertTrue(dialog.show_fps_telemetry_check.isChecked())
            self.assertTrue(dialog.expand_collision_enabled_check.isChecked())
            self.assertEqual(
                dialog.expand_collision_enabled_check.objectName(),
                "graphicsSettingsExpandCollisionAvoidanceEnabledCheck",
            )
            self.assertEqual(
                dialog.expand_collision_strategy_combo.objectName(),
                "graphicsSettingsExpandCollisionAvoidanceStrategyCombo",
            )
            self.assertEqual(dialog.expand_collision_strategy_combo.currentData(), "nearest")
            self.assertEqual(dialog.expand_collision_scope_combo.currentData(), "all_movable")
            self.assertEqual(dialog.expand_collision_radius_mode_combo.currentData(), "local")
            self.assertEqual(dialog.expand_collision_local_radius_preset_combo.currentData(), "medium")
            self.assertEqual(dialog.expand_collision_gap_preset_combo.currentData(), "normal")
            self.assertTrue(dialog.expand_collision_animate_check.isChecked())
            self.assertTrue(dialog.follow_shell_theme_check.isChecked())
            self.assertFalse(dialog.graph_theme_combo.isEnabled())
            self.assertEqual(
                dialog.passive_node_library_display_mode_combo.objectName(),
                "graphicsSettingsPassiveNodeLibraryDisplayModeCombo",
            )
            self.assertEqual(dialog.passive_node_library_display_mode_combo.currentData(), "text")

            dialog.show_grid_check.setChecked(False)
            dialog.grid_style_combo.setCurrentIndex(dialog.grid_style_combo.findData("points"))
            dialog.edge_crossing_style_combo.setCurrentIndex(dialog.edge_crossing_style_combo.findData("gap_break"))
            dialog.show_canvas_options_button_check.setChecked(False)
            dialog.show_minimap_check.setChecked(False)
            dialog.show_port_labels_check.setChecked(False)
            dialog.notched_ports_check.setChecked(False)
            dialog.node_elapsed_time_visibility_combo.setCurrentIndex(
                dialog.node_elapsed_time_visibility_combo.findData("off")
            )
            dialog.node_elapsed_time_unit_combo.setCurrentIndex(
                dialog.node_elapsed_time_unit_combo.findData("milliseconds")
            )
            dialog.node_comment_editor_default_combo.setCurrentIndex(
                dialog.node_comment_editor_default_combo.findData("inspector")
            )
            dialog.node_toolbar_opens_on_hover_check.setChecked(True)
            dialog.minimap_expanded_check.setChecked(False)
            dialog.media_panel_show_title_check.setChecked(False)
            dialog.media_panel_show_frame_check.setChecked(False)
            dialog.media_panel_autoplay_animations_check.setChecked(False)
            dialog.media_panel_source_input_exposed_check.setChecked(False)
            dialog.snap_to_grid_check.setChecked(True)
            dialog.expand_collision_enabled_check.setChecked(False)
            dialog.expand_collision_radius_mode_combo.setCurrentIndex(
                dialog.expand_collision_radius_mode_combo.findData("unbounded")
            )
            dialog.expand_collision_local_radius_preset_combo.setCurrentIndex(
                dialog.expand_collision_local_radius_preset_combo.findData("large")
            )
            dialog.expand_collision_gap_preset_combo.setCurrentIndex(
                dialog.expand_collision_gap_preset_combo.findData("tight")
            )
            dialog.expand_collision_animate_check.setChecked(False)
            dialog.tab_strip_density_combo.setCurrentIndex(dialog.tab_strip_density_combo.findData("regular"))
            dialog.passive_node_library_display_mode_combo.setCurrentIndex(
                dialog.passive_node_library_display_mode_combo.findData("icon")
            )
            dialog.property_pane_variant_combo.setCurrentIndex(
                dialog.property_pane_variant_combo.findData("accordion_cards")
            )
            dialog.theme_combo.setCurrentIndex(dialog.theme_combo.findData("stitch_light"))
            dialog.follow_shell_theme_check.setChecked(False)
            dialog.graph_theme_combo.setCurrentIndex(dialog.graph_theme_combo.findData("graph_stitch_light"))

            expected = copy.deepcopy(DEFAULT_GRAPHICS_SETTINGS)
            expected["canvas"]["show_grid"] = False
            expected["canvas"]["grid_style"] = "points"
            expected["canvas"]["edge_crossing_style"] = "gap_break"
            expected["canvas"]["show_canvas_options_button"] = False
            expected["canvas"]["show_minimap"] = False
            expected["canvas"]["show_port_labels"] = False
            expected["canvas"]["notched_ports"] = False
            expected["canvas"]["node_elapsed_time_visibility"] = "off"
            expected["canvas"]["node_elapsed_time_unit"] = "milliseconds"
            expected["canvas"]["node_comment_editor_default"] = "inspector"
            expected["canvas"]["node_floating_toolbar_opens_on_hover"] = True
            expected["canvas"]["minimap_expanded"] = False
            expected["media_panel"]["show_title"] = False
            expected["media_panel"]["show_frame"] = False
            expected["media_panel"]["autoplay_animations"] = False
            expected["media_panel"]["source_input_exposed"] = False
            expected["interaction"]["snap_to_grid"] = True
            expected["interaction"]["expand_collision_avoidance"] = {
                "enabled": False,
                "strategy": "nearest",
                "scope": "all_movable",
                "radius_mode": "unbounded",
                "local_radius_preset": "large",
                "gap_preset": "tight",
                "animate": False,
            }
            expected["shell"]["tab_strip_density"] = "regular"
            expected["shell"]["passive_node_library_display_mode"] = "icon"
            expected["shell"]["property_pane_variant"] = "accordion_cards"
            expected["theme"]["theme_id"] = "stitch_light"
            expected["graph_theme"]["follow_shell_theme"] = False
            expected["graph_theme"]["selected_theme_id"] = "graph_stitch_light"
            self.assertEqual(
                dialog.values(),
                expected,
            )
        finally:
            dialog.close()

    def test_dialog_roundtrips_custom_graph_theme_library_without_manager_ui(self) -> None:
        custom_theme = copy.deepcopy(resolve_graph_theme("graph_stitch_light").as_dict())
        custom_theme["theme_id"] = "custom_graph_theme_deadbeef"
        custom_theme["label"] = "Ocean Wire"
        available_graph_themes = graph_theme_choices([custom_theme])
        initial_settings = copy.deepcopy(DEFAULT_GRAPHICS_SETTINGS)
        initial_settings["graph_theme"] = {
            "follow_shell_theme": False,
            "selected_theme_id": custom_theme["theme_id"],
            "custom_themes": [custom_theme],
        }

        dialog = GraphicsSettingsDialog(
            initial_settings=initial_settings,
            available_graph_themes=available_graph_themes,
        )
        try:
            self.assertEqual(dialog.graph_theme_combo.count(), len(available_graph_themes))
            self.assertEqual(dialog.graph_theme_combo.currentData(), custom_theme["theme_id"])
            self.assertTrue(dialog.graph_theme_combo.isEnabled())

            values = dialog.values()
            self.assertEqual(values["graph_theme"]["selected_theme_id"], custom_theme["theme_id"])
            self.assertEqual(values["graph_theme"]["custom_themes"][0]["theme_id"], custom_theme["theme_id"])
            self.assertEqual(values["graph_theme"]["custom_themes"][0]["label"], "Ocean Wire")
        finally:
            dialog.close()

    def test_keep_expanded_node_width_checkbox_roundtrips(self) -> None:
        dialog = GraphicsSettingsDialog(initial_settings={"canvas": {"keep_expanded_node_width": True}})
        try:
            self.assertTrue(dialog.keep_expanded_node_width_check.isChecked())
            self.assertIn("fully expanded settings", dialog.keep_expanded_node_width_check.toolTip())
            self.assertTrue(dialog.values()["canvas"]["keep_expanded_node_width"])
            dialog.keep_expanded_node_width_check.setChecked(False)
            self.assertFalse(dialog.values()["canvas"]["keep_expanded_node_width"])
        finally:
            dialog.close()

    def test_dialog_normalizes_invalid_initial_settings(self) -> None:
        dialog = GraphicsSettingsDialog(
            initial_settings={
                "canvas": {
                    "show_grid": False,
                    "edge_crossing_style": "arc-weld",
                    "show_canvas_options_button": "no",
                    "show_minimap": "no",
                    "show_port_labels": False,
                    "notched_ports": "false",
                    "keep_expanded_node_width": "true",
                    "node_elapsed_time_unit": "ticks",
                    "node_floating_toolbar_opens_on_hover": "false",
                    "minimap_expanded": False,
                },
                "interaction": {
                    "snap_to_grid": True,
                    "expand_collision_avoidance": {
                        "enabled": "yes",
                        "strategy": "farthest",
                        "scope": "selection",
                        "radius_mode": "global",
                        "local_radius_preset": "tiny",
                        "gap_preset": "huge",
                        "animate": "yes",
                    },
                },
                "performance": {
                    "mode": "warp_speed",
                },
                "shell": {
                    "tab_strip_density": "huge",
                    "passive_node_library_display_mode": "tiles",
                },
                "theme": {
                    "theme_id": "unknown_theme",
                },
                "media_panel": {
                    "show_title": "false",
                    "show_frame": None,
                    "autoplay_animations": "yes",
                    "source_input_exposed": "no",
                },
                "graph_theme": {
                    "follow_shell_theme": "no",
                    "selected_theme_id": "unknown_graph_theme",
                },
            }
        )
        try:
            self.assertEqual(dialog.section_list.count(), 5)
            self.assertEqual(dialog.theme_combo.count(), 2)
            self.assertEqual(dialog.graph_theme_combo.count(), len(graph_theme_choices()))
            self.assertNotIn("performance", dialog.values())
            self.assertFalse(dialog.values()["canvas"]["keep_expanded_node_width"])
            self.assertTrue(dialog.follow_shell_theme_check.isChecked())
            self.assertFalse(dialog.graph_theme_combo.isEnabled())
            self.assertTrue(dialog.expand_collision_enabled_check.isChecked())
            self.assertEqual(dialog.expand_collision_strategy_combo.currentData(), "nearest")
            self.assertEqual(dialog.expand_collision_scope_combo.currentData(), "all_movable")
            self.assertEqual(dialog.expand_collision_radius_mode_combo.currentData(), "local")
            self.assertEqual(dialog.expand_collision_local_radius_preset_combo.currentData(), "medium")
            self.assertEqual(dialog.expand_collision_gap_preset_combo.currentData(), "normal")
            self.assertTrue(dialog.expand_collision_animate_check.isChecked())
            self.assertTrue(dialog.show_canvas_options_button_check.isChecked())
            self.assertFalse(dialog.show_port_labels_check.isChecked())
            self.assertTrue(dialog.notched_ports_check.isChecked())
            self.assertTrue(dialog.media_panel_show_title_check.isChecked())
            self.assertTrue(dialog.media_panel_show_frame_check.isChecked())
            self.assertTrue(dialog.media_panel_autoplay_animations_check.isChecked())
            self.assertTrue(dialog.media_panel_source_input_exposed_check.isChecked())
            self.assertEqual(dialog.grid_style_combo.currentData(), "lines")
            self.assertEqual(dialog.edge_crossing_style_combo.currentData(), "none")
            self.assertEqual(dialog.node_elapsed_time_unit_combo.currentData(), "seconds")
            self.assertFalse(dialog.node_toolbar_opens_on_hover_check.isChecked())
            self.assertEqual(dialog.passive_node_library_display_mode_combo.currentData(), "text")
            expected = copy.deepcopy(DEFAULT_GRAPHICS_SETTINGS)
            expected["canvas"]["show_grid"] = False
            expected["canvas"]["show_port_labels"] = False
            expected["canvas"]["minimap_expanded"] = False
            expected["interaction"]["snap_to_grid"] = True
            self.assertEqual(
                dialog.values(),
                expected,
            )
        finally:
            dialog.close()

    def test_follow_shell_toggle_enables_explicit_graph_theme_selection(self) -> None:
        dialog = GraphicsSettingsDialog()
        try:
            self.assertFalse(dialog.graph_theme_combo.isEnabled())
            self.assertEqual(dialog.graph_theme_combo.currentData(), "graph_stitch_dark")

            dialog.follow_shell_theme_check.setChecked(False)
            self.assertTrue(dialog.graph_theme_combo.isEnabled())
            dialog.graph_theme_combo.setCurrentIndex(dialog.graph_theme_combo.findData("graph_stitch_light"))
            self.assertEqual(dialog.graph_theme_combo.currentData(), "graph_stitch_light")

            dialog.follow_shell_theme_check.setChecked(True)
            self.assertFalse(dialog.graph_theme_combo.isEnabled())
            self.assertEqual(dialog.graph_theme_combo.currentData(), "graph_stitch_dark")

            dialog.theme_combo.setCurrentIndex(dialog.theme_combo.findData("stitch_light"))
            self.assertEqual(dialog.graph_theme_combo.currentData(), "graph_stitch_light")

            dialog.follow_shell_theme_check.setChecked(False)
            self.assertTrue(dialog.graph_theme_combo.isEnabled())
            self.assertEqual(dialog.graph_theme_combo.currentData(), "graph_stitch_light")
        finally:
            dialog.close()

    def test_follow_shell_preserves_previous_explicit_graph_theme_in_values(self) -> None:
        custom_theme = copy.deepcopy(resolve_graph_theme("graph_stitch_light").as_dict())
        custom_theme["theme_id"] = "custom_graph_theme_deadbeef"
        custom_theme["label"] = "Ocean Wire"
        dialog = GraphicsSettingsDialog(
            initial_settings={
                "theme": {"theme_id": "stitch_dark"},
                "graph_theme": {
                    "follow_shell_theme": False,
                    "selected_theme_id": custom_theme["theme_id"],
                    "custom_themes": [custom_theme],
                },
            },
            available_graph_themes=graph_theme_choices([custom_theme]),
        )
        try:
            self.assertEqual(dialog.graph_theme_combo.currentData(), custom_theme["theme_id"])

            dialog.follow_shell_theme_check.setChecked(True)
            self.assertEqual(dialog.graph_theme_combo.currentData(), "graph_stitch_dark")

            values = dialog.values()
            self.assertTrue(values["graph_theme"]["follow_shell_theme"])
            self.assertEqual(values["graph_theme"]["selected_theme_id"], custom_theme["theme_id"])

            dialog.follow_shell_theme_check.setChecked(False)
            self.assertEqual(dialog.graph_theme_combo.currentData(), custom_theme["theme_id"])
        finally:
            dialog.close()

    def test_graph_theme_preview_identifies_passive_node_defaults(self) -> None:
        dialog = GraphicsSettingsDialog()
        try:
            preview_label = dialog._graph_theme_preview.findChild(
                QLabel,
                "graphThemePassiveDefaultsPreviewLabel",
            )
            self.assertIsNotNone(preview_label)
            assert preview_label is not None
            self.assertEqual(preview_label.text(), "Passive node defaults")
        finally:
            dialog.close()

    def test_manage_graph_themes_callback_updates_theme_library_and_selection(self) -> None:
        custom_theme = copy.deepcopy(resolve_graph_theme("graph_stitch_light").as_dict())
        custom_theme["theme_id"] = "custom_graph_theme_deadbeef"
        custom_theme["label"] = "Ocean Wire"
        received_settings: list[dict[str, object]] = []

        def manage_graph_themes(graph_theme_settings: dict[str, object]) -> dict[str, object]:
            received_settings.append(copy.deepcopy(graph_theme_settings))
            return {
                "follow_shell_theme": False,
                "selected_theme_id": custom_theme["theme_id"],
                "custom_themes": [custom_theme],
            }

        dialog = GraphicsSettingsDialog(manage_graph_themes_callback=manage_graph_themes)
        try:
            self.assertTrue(dialog.manage_graph_themes_button.isEnabled())

            dialog.manage_graph_themes_button.click()

            self.assertEqual(len(received_settings), 1)
            self.assertTrue(received_settings[0]["follow_shell_theme"])
            self.assertEqual(received_settings[0]["selected_theme_id"], "graph_stitch_dark")
            self.assertEqual(received_settings[0]["custom_themes"], [])
            self.assertEqual(dialog.graph_theme_combo.count(), len(graph_theme_choices([custom_theme])))
            self.assertEqual(dialog.graph_theme_combo.currentData(), custom_theme["theme_id"])
            self.assertTrue(dialog.graph_theme_combo.isEnabled())
            self.assertFalse(dialog.follow_shell_theme_check.isChecked())

            values = dialog.values()
            self.assertFalse(values["graph_theme"]["follow_shell_theme"])
            self.assertEqual(values["graph_theme"]["selected_theme_id"], custom_theme["theme_id"])
            self.assertEqual(values["graph_theme"]["custom_themes"][0]["label"], "Ocean Wire")
        finally:
            dialog.close()

    def test_manage_graph_themes_button_is_disabled_without_callback(self) -> None:
        dialog = GraphicsSettingsDialog()
        try:
            self.assertFalse(dialog.manage_graph_themes_button.isEnabled())
            with patch.object(dialog, "_open_graph_theme_manager") as open_manager:
                dialog.manage_graph_themes_button.click()
            open_manager.assert_not_called()
        finally:
            dialog.close()

    def test_dialog_shows_active_renderer_as_read_only_runtime_info(self) -> None:
        dialog = GraphicsSettingsDialog(active_renderer_label="Direct3D 11")
        try:
            self.assertEqual(dialog.active_renderer_value_label.text(), "Direct3D 11")
            self.assertTrue(
                bool(
                    dialog.active_renderer_value_label.textInteractionFlags()
                    & Qt.TextInteractionFlag.TextSelectableByMouse
                )
            )
            self.assertEqual(dialog.values(), DEFAULT_GRAPHICS_SETTINGS)
        finally:
            dialog.close()

    def test_status_bar_layout_option_cards_update_selection(self) -> None:
        dialog = GraphicsSettingsDialog()
        try:
            dialog.show()
            QApplication.instance().processEvents()

            self.assertTrue(dialog.status_bar_layout_option_1_button.isChecked())
            self.assertEqual(
                dialog.status_bar_layout_option_1_card.property("statusBarLayoutSelected"),
                True,
            )
            self.assertEqual(
                dialog.status_bar_layout_option_2_card.property("statusBarLayoutSelected"),
                False,
            )

            QTest.mouseClick(
                dialog.status_bar_layout_option_2_card,
                Qt.MouseButton.LeftButton,
                Qt.KeyboardModifier.NoModifier,
            )
            QApplication.instance().processEvents()

            self.assertFalse(dialog.status_bar_layout_option_1_button.isChecked())
            self.assertTrue(dialog.status_bar_layout_option_2_button.isChecked())
            self.assertEqual(
                dialog.status_bar_layout_option_1_card.property("statusBarLayoutSelected"),
                False,
            )
            self.assertEqual(
                dialog.status_bar_layout_option_2_card.property("statusBarLayoutSelected"),
                True,
            )
            dialog.show_fps_telemetry_check.setChecked(False)
            self.assertEqual(dialog.values()["shell"]["status_bar_layout"], "option_2")
            self.assertFalse(dialog.values()["shell"]["show_fps_telemetry"])
        finally:
            dialog.close()

    def test_floating_toolbar_style_combo_defaults_and_roundtrips_all_choices(self) -> None:
        dialog = GraphicsSettingsDialog()
        try:
            self.assertEqual(
                dialog.floating_toolbar_style_combo.objectName(),
                "graphicsSettingsFloatingToolbarStyleCombo",
            )
            self.assertEqual(dialog.floating_toolbar_style_combo.count(), 3)
            item_ids = [
                dialog.floating_toolbar_style_combo.itemData(index)
                for index in range(dialog.floating_toolbar_style_combo.count())
            ]
            self.assertEqual(item_ids, ["compact_pill", "segmented_bar", "minimal_ghost"])
            self.assertEqual(dialog.floating_toolbar_style_combo.currentData(), "compact_pill")
            self.assertEqual(
                dialog.values()["canvas"]["floating_toolbar_style"],
                "compact_pill",
            )

            for style_id in ("segmented_bar", "minimal_ghost", "compact_pill"):
                with self.subTest(style=style_id):
                    dialog.floating_toolbar_style_combo.setCurrentIndex(
                        dialog.floating_toolbar_style_combo.findData(style_id)
                    )
                    self.assertEqual(
                        dialog.values()["canvas"]["floating_toolbar_style"],
                        style_id,
                    )
        finally:
            dialog.close()

    def test_floating_toolbar_style_set_values_accepts_initial_settings(self) -> None:
        dialog = GraphicsSettingsDialog(
            initial_settings={
                "canvas": {
                    "floating_toolbar_style": "segmented_bar",
                }
            }
        )
        try:
            self.assertEqual(dialog.floating_toolbar_style_combo.currentData(), "segmented_bar")
            self.assertEqual(
                dialog.values()["canvas"]["floating_toolbar_style"],
                "segmented_bar",
            )
        finally:
            dialog.close()

    def test_floating_toolbar_style_set_values_falls_back_for_unknown_id(self) -> None:
        dialog = GraphicsSettingsDialog(
            initial_settings={
                "canvas": {
                    "floating_toolbar_style": "bubble_row",
                }
            }
        )
        try:
            self.assertEqual(dialog.floating_toolbar_style_combo.currentData(), "compact_pill")
            self.assertEqual(
                dialog.values()["canvas"]["floating_toolbar_style"],
                "compact_pill",
            )
        finally:
            dialog.close()

    def test_node_toolbar_hover_checkbox_accepts_initial_settings_and_roundtrips(self) -> None:
        dialog = GraphicsSettingsDialog(
            initial_settings={
                "canvas": {
                    "node_floating_toolbar_opens_on_hover": True,
                }
            }
        )
        try:
            self.assertTrue(dialog.node_toolbar_opens_on_hover_check.isChecked())
            self.assertTrue(dialog.values()["canvas"]["node_floating_toolbar_opens_on_hover"])

            dialog.node_toolbar_opens_on_hover_check.setChecked(False)
            self.assertFalse(dialog.values()["canvas"]["node_floating_toolbar_opens_on_hover"])
        finally:
            dialog.close()

    def test_selection_toolbar_controls_default_and_roundtrip_choices(self) -> None:
        dialog = GraphicsSettingsDialog()
        try:
            self.assertEqual(
                dialog.selection_toolbar_mode_combo.objectName(),
                "graphicsSettingsSelectionToolbarModeCombo",
            )
            self.assertEqual(
                dialog.selection_toolbar_minimal_menu_trigger_combo.objectName(),
                "graphicsSettingsSelectionToolbarMinimalMenuTriggerCombo",
            )
            self.assertEqual(
                dialog.selection_toolbar_minimal_menu_trigger_label.objectName(),
                "graphicsSettingsSelectionToolbarMinimalMenuTriggerLabel",
            )
            self.assertEqual(dialog.selection_toolbar_mode_combo.count(), 2)
            self.assertEqual(
                [
                    dialog.selection_toolbar_mode_combo.itemData(index)
                    for index in range(dialog.selection_toolbar_mode_combo.count())
                ],
                ["minimal_ghost_menu", "side_rail"],
            )
            self.assertEqual(dialog.selection_toolbar_mode_combo.currentData(), "minimal_ghost_menu")
            self.assertEqual(
                dialog.selection_toolbar_minimal_menu_trigger_combo.currentData(),
                "click_affordance",
            )
            self.assertTrue(dialog.selection_toolbar_minimal_menu_trigger_combo.isEnabled())
            self.assertFalse(dialog.selection_toolbar_minimal_menu_trigger_combo.isHidden())
            self.assertFalse(dialog.selection_toolbar_minimal_menu_trigger_label.isHidden())

            dialog.selection_toolbar_mode_combo.setCurrentIndex(
                dialog.selection_toolbar_mode_combo.findData("side_rail")
            )
            dialog.selection_toolbar_minimal_menu_trigger_combo.setCurrentIndex(
                dialog.selection_toolbar_minimal_menu_trigger_combo.findData("right_click")
            )

            values = dialog.values()["canvas"]
            self.assertEqual(values["selection_toolbar_mode"], "side_rail")
            self.assertEqual(values["selection_toolbar_minimal_menu_trigger"], "right_click")
            self.assertFalse(dialog.selection_toolbar_minimal_menu_trigger_combo.isEnabled())
            self.assertTrue(dialog.selection_toolbar_minimal_menu_trigger_combo.isHidden())
            self.assertTrue(dialog.selection_toolbar_minimal_menu_trigger_label.isHidden())
        finally:
            dialog.close()

    def test_selection_toolbar_controls_accept_initial_settings_and_fallbacks(self) -> None:
        dialog = GraphicsSettingsDialog(
            initial_settings={
                "canvas": {
                    "selection_toolbar_mode": "side_rail",
                    "selection_toolbar_minimal_menu_trigger": "right_click",
                }
            }
        )
        try:
            self.assertEqual(dialog.selection_toolbar_mode_combo.currentData(), "side_rail")
            self.assertEqual(
                dialog.selection_toolbar_minimal_menu_trigger_combo.currentData(),
                "right_click",
            )
            self.assertFalse(dialog.selection_toolbar_minimal_menu_trigger_combo.isEnabled())
            self.assertTrue(dialog.selection_toolbar_minimal_menu_trigger_combo.isHidden())
            self.assertTrue(dialog.selection_toolbar_minimal_menu_trigger_label.isHidden())
        finally:
            dialog.close()

        fallback_dialog = GraphicsSettingsDialog(
            initial_settings={
                "canvas": {
                    "selection_toolbar_mode": "hover_cloud",
                    "selection_toolbar_minimal_menu_trigger": "drag",
                }
            }
        )
        try:
            self.assertEqual(
                fallback_dialog.selection_toolbar_mode_combo.currentData(),
                "minimal_ghost_menu",
            )
            self.assertEqual(
                fallback_dialog.selection_toolbar_minimal_menu_trigger_combo.currentData(),
                "click_affordance",
            )
            self.assertTrue(
                fallback_dialog.selection_toolbar_minimal_menu_trigger_combo.isEnabled()
            )
            self.assertFalse(
                fallback_dialog.selection_toolbar_minimal_menu_trigger_combo.isHidden()
            )
            self.assertFalse(
                fallback_dialog.selection_toolbar_minimal_menu_trigger_label.isHidden()
            )
        finally:
            fallback_dialog.close()

    def test_grid_style_control_tracks_grid_visibility_and_roundtrips_selection(self) -> None:
        dialog = GraphicsSettingsDialog(
            initial_settings={
                "canvas": {
                    "show_grid": True,
                    "grid_style": "points",
                }
            }
        )
        try:
            self.assertTrue(dialog.show_grid_check.isChecked())
            self.assertFalse(dialog._grid_style_container.isHidden())
            self.assertEqual(dialog.grid_style_combo.objectName(), "graphicsSettingsGridStyleCombo")
            self.assertEqual(dialog.grid_style_combo.currentData(), "points")

            dialog.show_grid_check.setChecked(False)
            self.assertTrue(dialog._grid_style_container.isHidden())
            self.assertEqual(dialog.values()["canvas"]["grid_style"], "points")

            dialog.show_grid_check.setChecked(True)
            self.assertFalse(dialog._grid_style_container.isHidden())
        finally:
            dialog.close()

    def test_graph_typography_dialog_theme_page_spinbox_roundtrips_app_global_size(self) -> None:
        dialog = GraphicsSettingsDialog()
        try:
            self.assertEqual(
                dialog.graph_label_pixel_size_spin.objectName(),
                "graphicsSettingsGraphLabelPixelSizeSpin",
            )
            self.assertEqual(dialog.graph_label_pixel_size_spin.minimum(), 8)
            self.assertEqual(dialog.graph_label_pixel_size_spin.maximum(), 50)
            self.assertEqual(dialog.graph_label_pixel_size_spin.value(), 10)
            self.assertEqual(dialog.values()["typography"]["graph_label_pixel_size"], 10)

            dialog.graph_label_pixel_size_spin.setValue(16)

            values = dialog.values()
            self.assertEqual(values["typography"]["graph_label_pixel_size"], 16)
            self.assertEqual(values["theme"], DEFAULT_GRAPHICS_SETTINGS["theme"])
            self.assertEqual(values["graph_theme"], DEFAULT_GRAPHICS_SETTINGS["graph_theme"])
        finally:
            dialog.close()

    def test_graph_node_icon_size_dialog_defaults_to_automatic_graph_label_size(self) -> None:
        dialog = GraphicsSettingsDialog()
        try:
            self.assertEqual(
                dialog.graph_node_icon_size_override_check.objectName(),
                "graphicsSettingsGraphNodeIconSizeOverrideCheck",
            )
            self.assertEqual(
                dialog.graph_node_icon_pixel_size_spin.objectName(),
                "graphicsSettingsGraphNodeIconPixelSizeOverrideSpin",
            )
            self.assertFalse(dialog.graph_node_icon_size_override_check.isChecked())
            self.assertFalse(dialog.graph_node_icon_pixel_size_spin.isEnabled())
            self.assertEqual(dialog.graph_node_icon_pixel_size_spin.minimum(), 8)
            self.assertEqual(dialog.graph_node_icon_pixel_size_spin.maximum(), 50)
            self.assertEqual(dialog.graph_node_icon_pixel_size_spin.value(), 10)
            self.assertIsNone(dialog.values()["typography"]["graph_node_icon_pixel_size_override"])
        finally:
            dialog.close()

    def test_graph_node_icon_size_dialog_roundtrips_explicit_override(self) -> None:
        dialog = GraphicsSettingsDialog(
            initial_settings={
                "typography": {
                    "graph_label_pixel_size": 14,
                    "graph_node_icon_pixel_size_override": 17,
                }
            }
        )
        try:
            self.assertTrue(dialog.graph_node_icon_size_override_check.isChecked())
            self.assertTrue(dialog.graph_node_icon_pixel_size_spin.isEnabled())
            self.assertEqual(dialog.graph_label_pixel_size_spin.value(), 14)
            self.assertEqual(dialog.graph_node_icon_pixel_size_spin.value(), 17)

            dialog.graph_node_icon_pixel_size_spin.setValue(15)

            values = dialog.values()
            self.assertEqual(values["typography"]["graph_label_pixel_size"], 14)
            self.assertEqual(values["typography"]["graph_node_icon_pixel_size_override"], 15)
        finally:
            dialog.close()

    def test_graph_node_icon_size_dialog_can_disable_override_without_changing_label_size(self) -> None:
        dialog = GraphicsSettingsDialog(
            initial_settings={
                "typography": {
                    "graph_label_pixel_size": 16,
                    "graph_node_icon_pixel_size_override": 12,
                }
            }
        )
        try:
            dialog.graph_node_icon_size_override_check.setChecked(False)

            values = dialog.values()
            self.assertFalse(dialog.graph_node_icon_pixel_size_spin.isEnabled())
            self.assertEqual(values["typography"]["graph_label_pixel_size"], 16)
            self.assertIsNone(values["typography"]["graph_node_icon_pixel_size_override"])
        finally:
            dialog.close()

    def test_graph_node_icon_size_dialog_normalizes_invalid_and_clamped_initial_settings(self) -> None:
        cases = (
            ("boolean", True, False, 13, None),
            ("low", 2, True, 8, 8),
            ("high", 84, True, 50, 50),
        )

        for label, override, checked, spin_value, expected_override in cases:
            with self.subTest(case=label):
                dialog = GraphicsSettingsDialog(
                    initial_settings={
                        "typography": {
                            "graph_label_pixel_size": 13,
                            "graph_node_icon_pixel_size_override": override,
                        }
                    }
                )
                try:
                    self.assertEqual(dialog.graph_node_icon_size_override_check.isChecked(), checked)
                    self.assertEqual(dialog.graph_node_icon_pixel_size_spin.value(), spin_value)
                    self.assertEqual(
                        dialog.values()["typography"]["graph_node_icon_pixel_size_override"],
                        expected_override,
                    )
                finally:
                    dialog.close()

    def test_graph_typography_dialog_normalizes_missing_and_invalid_payloads(self) -> None:
        cases = (
            ("missing-block", {}, 10),
            ("invalid-block", {"typography": "large"}, 10),
            ("non-integer", {"typography": {"graph_label_pixel_size": "11"}}, 10),
            ("low", {"typography": {"graph_label_pixel_size": 4}}, 8),
            ("high", {"typography": {"graph_label_pixel_size": 64}}, 50),
        )

        for label, initial_settings, expected in cases:
            with self.subTest(case=label):
                dialog = GraphicsSettingsDialog(initial_settings=initial_settings)
                try:
                    self.assertEqual(dialog.graph_label_pixel_size_spin.value(), expected)
                    self.assertEqual(dialog.values()["typography"]["graph_label_pixel_size"], expected)
                finally:
                    dialog.close()

    def test_tooltip_expand_collision_controls_are_present_by_default(self) -> None:
        dialog = GraphicsSettingsDialog()
        try:
            for control_name, tooltip_text in _EXPAND_COLLISION_TOOLTIP_CASES:
                with self.subTest(control=control_name):
                    self.assertEqual(getattr(dialog, control_name).toolTip(), tooltip_text)
        finally:
            dialog.close()

    def test_plot_lightweight_canvas_control_roundtrips_without_overwriting_backend_defaults(self) -> None:
        initial_settings = copy.deepcopy(DEFAULT_GRAPHICS_SETTINGS)
        initial_settings["plot"] = {
            "lightweight_canvas": True,
            "plot_default_backend_per_type": {
                "line": "matplotlib",
            },
        }
        dialog = GraphicsSettingsDialog(initial_settings=initial_settings)
        try:
            self.assertTrue(dialog.plot_lightweight_canvas_check.isChecked())
            self.assertEqual(
                dialog.values()["plot"],
                {
                    "lightweight_canvas": True,
                    "plot_default_backend_per_type": DEFAULT_GRAPHICS_SETTINGS["plot"][
                        "plot_default_backend_per_type"
                    ],
                },
            )

            dialog.plot_lightweight_canvas_check.setChecked(False)

            self.assertEqual(
                dialog.values()["plot"],
                {
                    "lightweight_canvas": False,
                    "plot_default_backend_per_type": DEFAULT_GRAPHICS_SETTINGS["plot"][
                        "plot_default_backend_per_type"
                    ],
                },
            )
        finally:
            dialog.close()

    def test_tooltip_expand_collision_controls_are_suppressed_when_disabled(self) -> None:
        dialog = GraphicsSettingsDialog(tooltips_enabled=False)
        try:
            for control_name, _tooltip_text in _EXPAND_COLLISION_TOOLTIP_CASES:
                with self.subTest(control=control_name):
                    self.assertEqual(getattr(dialog, control_name).toolTip(), "")
        finally:
            dialog.close()

    def test_tooltip_policy_does_not_change_settings_roundtrip_behavior(self) -> None:
        dialog_with_tooltips = GraphicsSettingsDialog()
        dialog_without_tooltips = GraphicsSettingsDialog(tooltips_enabled=False)
        try:
            _apply_roundtrip_mutations(dialog_with_tooltips)
            _apply_roundtrip_mutations(dialog_without_tooltips)

            self.assertEqual(dialog_without_tooltips.values(), dialog_with_tooltips.values())
        finally:
            dialog_with_tooltips.close()
            dialog_without_tooltips.close()

    def test_tooltip_category_controls_default_and_roundtrip_shell_preferences(self) -> None:
        dialog = GraphicsSettingsDialog()
        try:
            self.assertEqual(
                dialog.tooltip_category_checks["general"].objectName(),
                "graphicsSettingsTooltipCategoryGeneralCheck",
            )
            self.assertEqual(set(dialog.tooltip_category_checks), set(default_tooltip_category_preferences()))
            self.assertNotIn("critical", dialog.tooltip_category_checks)
            self.assertEqual(
                dialog.findChild(QObject, "graphicsSettingsCriticalTooltipNotice").text(),
                "Critical blocker messaging remains visible and cannot be disabled.",
            )

            dialog.tooltip_category_checks["general"].setChecked(False)
            dialog.tooltip_category_checks["tutorial"].setChecked(False)
            dialog.tooltip_category_checks["advanced"].setChecked(True)
            dialog.tooltip_category_checks["warning"].setChecked(False)
            dialog.tooltip_category_checks["inactive"].setChecked(False)

            shell = dialog.values()["shell"]
            self.assertNotIn("show_tooltips", shell)
            self.assertEqual(
                shell["tooltip_categories"],
                {
                    "general": False,
                    "tutorial": False,
                    "advanced": True,
                    "warning": False,
                    "inactive": False,
                },
            )
        finally:
            dialog.close()

    def test_tooltip_category_controls_normalize_initial_settings_and_exclude_critical(self) -> None:
        dialog = GraphicsSettingsDialog(
            initial_settings={
                "shell": {
                    "tooltip_categories": {
                        "general": False,
                        "tutorial": False,
                        "advanced": True,
                        "warning": False,
                        "inactive": False,
                        "critical": False,
                        "future": True,
                    },
                }
            }
        )
        try:
            self.assertEqual(
                {
                    category: check.isChecked()
                    for category, check in dialog.tooltip_category_checks.items()
                },
                {
                    "general": False,
                    "tutorial": False,
                    "advanced": True,
                    "warning": False,
                    "inactive": False,
                },
            )
            shell = dialog.values()["shell"]
            self.assertNotIn("critical", shell["tooltip_categories"])
            self.assertNotIn("future", shell["tooltip_categories"])
        finally:
            dialog.close()

    def test_tooltip_category_controls_preserve_values_during_unrelated_edits(self) -> None:
        initial_settings = copy.deepcopy(DEFAULT_GRAPHICS_SETTINGS)
        expected_categories = {
            "general": False,
            "tutorial": True,
            "advanced": True,
            "warning": False,
            "inactive": True,
        }
        initial_settings["shell"]["tooltip_categories"] = copy.deepcopy(expected_categories)
        dialog = GraphicsSettingsDialog(initial_settings=initial_settings)
        try:
            dialog.show_grid_check.setChecked(False)

            shell = dialog.values()["shell"]
            self.assertNotIn("show_tooltips", shell)
            self.assertEqual(shell["tooltip_categories"], expected_categories)
        finally:
            dialog.close()

    def test_property_pane_variant_combo_defaults_and_roundtrips_all_choices(self) -> None:
        dialog = GraphicsSettingsDialog()
        try:
            self.assertEqual(
                dialog.property_pane_variant_combo.objectName(),
                "graphicsSettingsPropertyPaneVariantCombo",
            )
            self.assertEqual(dialog.property_pane_variant_combo.count(), 3)
            item_ids = [
                dialog.property_pane_variant_combo.itemData(index)
                for index in range(dialog.property_pane_variant_combo.count())
            ]
            self.assertEqual(item_ids, ["smart_groups", "accordion_cards", "palette"])
            self.assertEqual(dialog.property_pane_variant_combo.currentData(), "smart_groups")
            self.assertEqual(
                dialog.values()["shell"]["property_pane_variant"],
                "smart_groups",
            )

            for variant_id in ("accordion_cards", "palette", "smart_groups"):
                with self.subTest(variant=variant_id):
                    dialog.property_pane_variant_combo.setCurrentIndex(
                        dialog.property_pane_variant_combo.findData(variant_id)
                    )
                    self.assertEqual(
                        dialog.values()["shell"]["property_pane_variant"],
                        variant_id,
                    )
        finally:
            dialog.close()

    def test_property_pane_variant_combo_set_values_accepts_initial_settings(self) -> None:
        dialog = GraphicsSettingsDialog(
            initial_settings={
                "shell": {
                    "property_pane_variant": "accordion_cards",
                }
            }
        )
        try:
            self.assertEqual(dialog.property_pane_variant_combo.currentData(), "accordion_cards")
            self.assertEqual(
                dialog.values()["shell"]["property_pane_variant"],
                "accordion_cards",
            )
        finally:
            dialog.close()

    def test_property_pane_variant_combo_set_values_falls_back_for_unknown_id(self) -> None:
        dialog = GraphicsSettingsDialog(
            initial_settings={
                "shell": {
                    "property_pane_variant": "hologram",
                }
            }
        )
        try:
            self.assertEqual(dialog.property_pane_variant_combo.currentData(), "smart_groups")
            self.assertEqual(
                dialog.values()["shell"]["property_pane_variant"],
                "smart_groups",
            )
        finally:
            dialog.close()

    def test_shell_panel_collapsed_state_roundtrips_through_values(self) -> None:
        initial_settings = copy.deepcopy(DEFAULT_GRAPHICS_SETTINGS)
        initial_settings["shell"]["panel_collapsed"] = {
            "node_library": True,
            "property_pane": True,
            "output_panel": False,
        }
        dialog = GraphicsSettingsDialog(initial_settings=initial_settings)
        try:
            dialog.show_grid_check.setChecked(not initial_settings["canvas"]["show_grid"])

            self.assertEqual(
                dialog.values()["shell"]["panel_collapsed"],
                initial_settings["shell"]["panel_collapsed"],
            )
        finally:
            dialog.close()

    def test_tooltip_host_presenter_passes_current_general_policy_to_graphics_dialog(self) -> None:
        from ea_node_editor.ui.shell.host_presenter import ShellHostPresenter

        host = _TooltipPolicyHost(general_tooltips=False)
        presenter = ShellHostPresenter(host)
        expected_settings = copy.deepcopy(DEFAULT_GRAPHICS_SETTINGS)
        expected_settings["canvas"]["show_grid"] = False
        expected_settings["shell"]["tooltip_categories"]["warning"] = False

        with patch("ea_node_editor.ui.dialogs.GraphicsSettingsDialog") as dialog_cls:
            dialog = dialog_cls.return_value
            dialog.DialogCode.Accepted = 1
            dialog.exec.return_value = 1
            dialog.values.return_value = expected_settings

            presenter.show_graphics_settings_dialog()

        self.assertEqual(dialog_cls.call_count, 1)
        self.assertEqual(dialog_cls.call_args.kwargs["tooltips_enabled"], False)
        self.assertEqual(
            host.app_preferences_controller.applied_graphics,
            [(expected_settings, host)],
        )


if __name__ == "__main__":
    unittest.main()

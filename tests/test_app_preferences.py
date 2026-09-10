from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from ea_node_editor.app_preferences import (
    AppPreferencesStore,
    default_app_preferences_document,
    engineering_viewer_tangent_selection_angle,
    normalize_app_preferences_document,
    normalize_folder_explorer_column_widths,
    normalize_floating_toolbar_style,
    normalize_graphics_settings,
    normalize_engineering_viewer_settings,
    normalize_node_comment_editor_default,
    normalize_status_bar_layout,
    normalize_media_panel_settings,
    normalize_node_library_usage,
    normalize_property_pane_variant,
    normalize_python_runtime_settings,
    normalize_selection_toolbar_minimal_menu_trigger,
    normalize_selection_toolbar_mode,
    normalize_shell_panel_collapsed,
)
from ea_node_editor.settings import (
    APP_PREFERENCES_KIND,
    APP_PREFERENCES_VERSION,
    DEFAULT_FLOATING_TOOLBAR_STYLE,
    DEFAULT_FOLDER_EXPLORER_COLUMN_WIDTHS,
    DEFAULT_GRAPHICS_SETTINGS,
    DEFAULT_MEDIA_PANEL_SETTINGS,
    DEFAULT_PROPERTY_PANE_VARIANT,
    DEFAULT_PYTHON_RUNTIME_SETTINGS,
    DEFAULT_SELECTION_TOOLBAR_MINIMAL_MENU_TRIGGER,
    DEFAULT_SELECTION_TOOLBAR_MODE,
    DEFAULT_SHELL_PANEL_COLLAPSED,
    SCHEMA_VERSION,
)


class AppPreferencesTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temp_dir = tempfile.TemporaryDirectory()
        self._preferences_path = Path(self._temp_dir.name) / "app_preferences.json"
        self._store = AppPreferencesStore(path_provider=lambda: self._preferences_path)

    def tearDown(self) -> None:
        self._temp_dir.cleanup()

    def test_engineering_viewer_tangent_angle_is_app_wide_and_clamped(self) -> None:
        self.assertEqual(
            normalize_engineering_viewer_settings({})["tangent_selection_angle_degrees"],
            5.0,
        )
        self.assertEqual(
            normalize_engineering_viewer_settings(
                {"tangent_selection_angle_degrees": 120}
            )["tangent_selection_angle_degrees"],
            90.0,
        )
        document = default_app_preferences_document()
        document["graphics"]["engineering_viewer"][
            "tangent_selection_angle_degrees"
        ] = 12.5
        self.assertEqual(engineering_viewer_tangent_selection_angle(document), 12.5)

    def test_missing_document_uses_current_defaults(self) -> None:
        document = self._store.load_document()

        self.assertEqual(document["kind"], APP_PREFERENCES_KIND)
        self.assertEqual(APP_PREFERENCES_VERSION, 8)
        self.assertEqual(document["version"], APP_PREFERENCES_VERSION)
        self.assertEqual(document["python_runtime"], DEFAULT_PYTHON_RUNTIME_SETTINGS)
        self.assertEqual(document["plugins"], {})

    def test_pre_v5_documents_load_locked_current_defaults(self) -> None:
        for old_version in (1, 2, 3, 4):
            with self.subTest(version=old_version):
                self._preferences_path.write_text(
                    json.dumps(
                        {
                            "kind": APP_PREFERENCES_KIND,
                            "version": old_version,
                            "plugins": {"obsolete": {"version": "0.1.0"}},
                        }
                    ),
                    encoding="utf-8",
                )

                document = self._store.load_document()

                self.assertEqual(document, default_app_preferences_document())

    def test_python_runtime_normalizes_only_path_strings(self) -> None:
        for payload in (None, [], "python.exe"):
            with self.subTest(payload=payload):
                self.assertEqual(
                    normalize_python_runtime_settings(payload),
                    DEFAULT_PYTHON_RUNTIME_SETTINGS,
                )
        self.assertEqual(
            normalize_python_runtime_settings(
                {"default_executable": '  " C:\\Python\\python.exe "  '}
            ),
            {"default_executable": "C:\\Python\\python.exe"},
        )
        self.assertEqual(
            normalize_python_runtime_settings(
                {"default_executable": "  'python.exe'  "}
            ),
            {"default_executable": "python.exe"},
        )
        self.assertEqual(
            normalize_python_runtime_settings(
                {"default_executable": " 'python.exe\" "}
            ),
            {"default_executable": "'python.exe\""},
        )
        for value in (None, True, 1, 1.5, [], {}, object()):
            with self.subTest(value=value):
                self.assertEqual(
                    normalize_python_runtime_settings({"default_executable": value}),
                    DEFAULT_PYTHON_RUNTIME_SETTINGS,
                )

    def test_v5_and_v6_migration_discard_python_runtime_and_preserve_siblings(self) -> None:
        for old_version in (5, 6):
            with self.subTest(version=old_version):
                legacy = default_app_preferences_document()
                legacy["version"] = old_version
                legacy["graphics"]["canvas"]["show_canvas_options_button"] = False
                legacy["source_import"]["default_mode"] = "managed_copy"
                legacy["authoring"] = {
                    "canvas_mode": "advanced",
                    "guided_connected_control_policy": "auto_expand",
                }
                legacy["selected_run"]["preview_before_run"] = False
                legacy["plugins"] = {"obsolete": {"version": "0.2.0"}}
                legacy["addons"]["states"] = {
                    "example": {"enabled": False, "pending_restart": True}
                }
                legacy["python_runtime"] = {
                    "default_executable": "C:\\forged\\python.exe"
                }
                self._preferences_path.write_text(json.dumps(legacy), encoding="utf-8")

                document = self._store.load_document()

                self.assertEqual(document["version"], APP_PREFERENCES_VERSION)
                self.assertNotIn("authoring", document)
                self.assertEqual(document["solution"], {"default_mode": "auto"})
                self.assertFalse(document["graphics"]["canvas"]["show_canvas_options_button"])
                self.assertEqual(document["source_import"]["default_mode"], "managed_copy")
                self.assertFalse(document["selected_run"]["preview_before_run"])
                self.assertEqual(document["plugins"], {})
                self.assertEqual(
                    document["addons"]["states"]["example"],
                    {"enabled": False, "pending_restart": True},
                )
                self.assertEqual(document["python_runtime"], DEFAULT_PYTHON_RUNTIME_SETTINGS)

    def test_v5_and_v6_migration_persist_v8_document_on_load(self) -> None:
        for old_version in (5, 6):
            with self.subTest(version=old_version):
                legacy = default_app_preferences_document()
                legacy["version"] = old_version
                legacy["graphics"]["canvas"]["show_canvas_options_button"] = False
                legacy["authoring"] = {"canvas_mode": "advanced"}
                legacy["selected_run"]["preview_before_run"] = False
                legacy["python_runtime"] = {"default_executable": "forged-python"}
                self._preferences_path.write_text(json.dumps(legacy), encoding="utf-8")

                self._store.load_document()

                persisted = json.loads(self._preferences_path.read_text(encoding="utf-8"))
                self.assertEqual(persisted["version"], APP_PREFERENCES_VERSION)
                self.assertNotIn("authoring", persisted)
                self.assertEqual(persisted["solution"], {"default_mode": "auto"})
                self.assertFalse(persisted["graphics"]["canvas"]["show_canvas_options_button"])
                self.assertFalse(persisted["selected_run"]["preview_before_run"])
                self.assertEqual(persisted["python_runtime"], DEFAULT_PYTHON_RUNTIME_SETTINGS)

    def test_v7_migration_renames_image_node_settings_without_legacy_key(self) -> None:
        legacy = default_app_preferences_document()
        legacy["version"] = 7
        legacy["graphics"].pop("media_panel")
        legacy["graphics"]["image_nodes"] = {
            "show_title": False,
            "show_frame": False,
            "autoplay_animations": False,
        }
        self._preferences_path.write_text(json.dumps(legacy), encoding="utf-8")

        document = self._store.load_document()
        persisted = json.loads(self._preferences_path.read_text(encoding="utf-8"))

        self.assertEqual(document["version"], 8)
        self.assertNotIn("image_nodes", document["graphics"])
        self.assertEqual(
            document["graphics"]["media_panel"],
            {
                "show_title": False,
                "show_frame": False,
                "autoplay_animations": False,
                "source_input_exposed": True,
            },
        )
        self.assertEqual(persisted, document)

    def test_invalid_or_future_documents_still_load_current_defaults(self) -> None:
        for payload in (
            {"kind": "wrong-kind", "version": APP_PREFERENCES_VERSION},
            {"kind": APP_PREFERENCES_KIND, "version": "not-a-version"},
            {"kind": APP_PREFERENCES_KIND, "version": APP_PREFERENCES_VERSION + 1},
        ):
            with self.subTest(payload=payload):
                self.assertEqual(
                    normalize_app_preferences_document(payload),
                    default_app_preferences_document(),
                )

    def test_python_runtime_preferences_remain_app_only(self) -> None:
        document = default_app_preferences_document()
        document["python_runtime"] = normalize_python_runtime_settings(
            {"default_executable": "C:\\Python\\python.exe"}
        )

        persisted = self._store.persist_document(document)

        self.assertEqual(SCHEMA_VERSION, 5)
        self.assertNotIn("workflow_settings", persisted)
        self.assertEqual(
            persisted["python_runtime"]["default_executable"],
            "C:\\Python\\python.exe",
        )

class FloatingToolbarStyleNormalizationTests(unittest.TestCase):
    def test_known_values_pass_through_case_insensitive(self) -> None:
        self.assertEqual(normalize_floating_toolbar_style("compact_pill"), "compact_pill")
        self.assertEqual(normalize_floating_toolbar_style(" SEGMENTED_BAR "), "segmented_bar")
        self.assertEqual(normalize_floating_toolbar_style("Minimal_Ghost"), "minimal_ghost")

    def test_unknown_value_falls_back_to_default(self) -> None:
        self.assertEqual(
            normalize_floating_toolbar_style("bubble_row"),
            DEFAULT_FLOATING_TOOLBAR_STYLE,
        )
        self.assertEqual(
            normalize_floating_toolbar_style(None),
            DEFAULT_FLOATING_TOOLBAR_STYLE,
        )

    def test_unknown_value_with_valid_override_default_uses_override(self) -> None:
        self.assertEqual(
            normalize_floating_toolbar_style("bogus", "segmented_bar"),
            "segmented_bar",
        )


class SelectionToolbarPreferenceNormalizationTests(unittest.TestCase):
    def test_mode_known_values_pass_through_case_insensitive(self) -> None:
        self.assertEqual(
            normalize_selection_toolbar_mode("minimal_ghost_menu"),
            "minimal_ghost_menu",
        )
        self.assertEqual(normalize_selection_toolbar_mode(" SIDE_RAIL "), "side_rail")

    def test_mode_unknown_value_falls_back_to_default(self) -> None:
        self.assertEqual(
            normalize_selection_toolbar_mode("segmented_bar"),
            DEFAULT_SELECTION_TOOLBAR_MODE,
        )
        self.assertEqual(
            normalize_selection_toolbar_mode(None),
            DEFAULT_SELECTION_TOOLBAR_MODE,
        )

    def test_mode_unknown_value_with_valid_override_default_uses_override(self) -> None:
        self.assertEqual(
            normalize_selection_toolbar_mode("bogus", "side_rail"),
            "side_rail",
        )

    def test_minimal_menu_trigger_known_values_pass_through_case_insensitive(self) -> None:
        self.assertEqual(
            normalize_selection_toolbar_minimal_menu_trigger("click_affordance"),
            "click_affordance",
        )
        self.assertEqual(
            normalize_selection_toolbar_minimal_menu_trigger(" RIGHT_CLICK "),
            "right_click",
        )

    def test_minimal_menu_trigger_unknown_value_falls_back_to_default(self) -> None:
        self.assertEqual(
            normalize_selection_toolbar_minimal_menu_trigger("hover"),
            DEFAULT_SELECTION_TOOLBAR_MINIMAL_MENU_TRIGGER,
        )
        self.assertEqual(
            normalize_selection_toolbar_minimal_menu_trigger(None),
            DEFAULT_SELECTION_TOOLBAR_MINIMAL_MENU_TRIGGER,
        )

    def test_minimal_menu_trigger_unknown_value_with_valid_override_uses_override(self) -> None:
        self.assertEqual(
            normalize_selection_toolbar_minimal_menu_trigger("bogus", "right_click"),
            "right_click",
        )


class RecentTextColorPreferenceNormalizationTests(unittest.TestCase):
    def test_graphics_settings_normalizes_recent_text_colors(self) -> None:
        normalized = normalize_graphics_settings(
            {
                "typography": {
                    "recent_text_colors": [
                        "#112233",
                        "bad",
                        "#AABBCC",
                        "#112233",
                    ]
                }
            }
        )

        self.assertEqual(
            normalized["typography"]["recent_text_colors"],
            ["#112233", "#AABBCC"],
        )

    def test_default_document_includes_empty_recent_text_colors(self) -> None:
        document = default_app_preferences_document()

        self.assertEqual(
            document["graphics"]["typography"]["recent_text_colors"],
            [],
        )


class NodeLibraryUsagePreferenceTests(unittest.TestCase):
    def test_normalizes_to_last_64_nonempty_type_ids_with_repeats(self) -> None:
        source = ["", " core.constant ", *[f"core.node_{index}" for index in range(70)], "core.constant"]

        normalized = normalize_node_library_usage(source)

        self.assertEqual(len(normalized), 64)
        self.assertEqual(normalized[-1], "core.constant")
        self.assertNotIn("", normalized)

    def test_default_document_includes_empty_node_library_usage(self) -> None:
        document = default_app_preferences_document()

        self.assertEqual(document["graphics"]["shell"]["node_library_usage"], [])


class NotchedPortsPreferenceNormalizationTests(unittest.TestCase):
    def test_missing_or_invalid_values_default_true_and_false_roundtrips(self) -> None:
        self.assertTrue(DEFAULT_GRAPHICS_SETTINGS["canvas"]["notched_ports"])
        self.assertTrue(normalize_graphics_settings({})["canvas"]["notched_ports"])
        self.assertTrue(
            normalize_graphics_settings(
                {"canvas": {"notched_ports": "false"}}
            )["canvas"]["notched_ports"]
        )
        self.assertFalse(
            normalize_graphics_settings(
                {"canvas": {"notched_ports": False}}
            )["canvas"]["notched_ports"]
        )


class CanvasOptionsButtonPreferenceNormalizationTests(unittest.TestCase):
    def test_defaults_when_missing_or_invalid(self) -> None:
        self.assertTrue(DEFAULT_GRAPHICS_SETTINGS["canvas"]["show_canvas_options_button"])
        self.assertTrue(
            normalize_graphics_settings({})["canvas"]["show_canvas_options_button"]
        )
        self.assertTrue(
            normalize_graphics_settings(
                {"canvas": {"show_canvas_options_button": "no"}}
            )["canvas"]["show_canvas_options_button"]
        )

    def test_bool_value_roundtrips(self) -> None:
        self.assertFalse(
            normalize_graphics_settings(
                {"canvas": {"show_canvas_options_button": False}}
            )["canvas"]["show_canvas_options_button"]
        )


class NodeFloatingToolbarHoverPreferenceNormalizationTests(unittest.TestCase):
    def test_defaults_when_missing_or_invalid(self) -> None:
        self.assertFalse(
            DEFAULT_GRAPHICS_SETTINGS["canvas"][
                "node_floating_toolbar_opens_on_hover"
            ]
        )
        self.assertFalse(
            normalize_graphics_settings({})["canvas"][
                "node_floating_toolbar_opens_on_hover"
            ]
        )
        self.assertFalse(
            normalize_graphics_settings(
                {
                    "canvas": {
                        "node_floating_toolbar_opens_on_hover": "true",
                    }
                }
            )["canvas"]["node_floating_toolbar_opens_on_hover"]
        )

    def test_bool_value_roundtrips(self) -> None:
        self.assertTrue(
            normalize_graphics_settings(
                {
                    "canvas": {
                        "node_floating_toolbar_opens_on_hover": True,
                    }
                }
            )["canvas"]["node_floating_toolbar_opens_on_hover"]
        )


class NodeElapsedTimeUnitPreferenceNormalizationTests(unittest.TestCase):
    def test_defaults_when_missing_or_invalid(self) -> None:
        self.assertEqual(DEFAULT_GRAPHICS_SETTINGS["canvas"]["node_elapsed_time_unit"], "seconds")
        self.assertEqual(
            normalize_graphics_settings({})["canvas"]["node_elapsed_time_unit"],
            "seconds",
        )
        self.assertEqual(
            normalize_graphics_settings(
                {"canvas": {"node_elapsed_time_unit": "frames"}}
            )["canvas"]["node_elapsed_time_unit"],
            "seconds",
        )

    def test_known_values_and_aliases_roundtrip(self) -> None:
        self.assertEqual(
            normalize_graphics_settings(
                {"canvas": {"node_elapsed_time_unit": " milliseconds "}}
            )["canvas"]["node_elapsed_time_unit"],
            "milliseconds",
        )
        self.assertEqual(
            normalize_graphics_settings(
                {"canvas": {"node_elapsed_time_unit": "MS"}}
            )["canvas"]["node_elapsed_time_unit"],
            "milliseconds",
        )
        self.assertEqual(
            normalize_graphics_settings(
                {"canvas": {"node_elapsed_time_unit": "sec"}}
            )["canvas"]["node_elapsed_time_unit"],
            "seconds",
        )


class NodeElapsedTimeVisibilityPreferenceNormalizationTests(unittest.TestCase):
    def test_defaults_and_invalid_values_fall_back_to_always(self) -> None:
        self.assertEqual(
            DEFAULT_GRAPHICS_SETTINGS["canvas"]["node_elapsed_time_visibility"],
            "always",
        )
        self.assertEqual(
            normalize_graphics_settings({})["canvas"]["node_elapsed_time_visibility"],
            "always",
        )
        self.assertEqual(
            normalize_graphics_settings(
                {"canvas": {"node_elapsed_time_visibility": "frames"}}
            )["canvas"]["node_elapsed_time_visibility"],
            "always",
        )

    def test_known_values_round_trip(self) -> None:
        for value in ("off", "during_run", "always"):
            with self.subTest(value=value):
                self.assertEqual(
                    normalize_graphics_settings(
                        {"canvas": {"node_elapsed_time_visibility": f" {value} "}}
                    )["canvas"]["node_elapsed_time_visibility"],
                    value,
                )


class NodeCommentEditorDefaultPreferenceNormalizationTests(unittest.TestCase):
    def test_defaults_when_missing_or_invalid(self) -> None:
        self.assertEqual(DEFAULT_GRAPHICS_SETTINGS["canvas"]["node_comment_editor_default"], "canvas_popover")
        self.assertEqual(
            normalize_graphics_settings({})["canvas"]["node_comment_editor_default"],
            "canvas_popover",
        )
        self.assertEqual(
            normalize_graphics_settings(
                {"canvas": {"node_comment_editor_default": "sidebar"}}
            )["canvas"]["node_comment_editor_default"],
            "canvas_popover",
        )

    def test_known_values_and_aliases_roundtrip(self) -> None:
        self.assertEqual(normalize_node_comment_editor_default(" Inspector "), "inspector")
        self.assertEqual(normalize_node_comment_editor_default("canvas-popover"), "canvas_popover")
        self.assertEqual(
            normalize_graphics_settings(
                {"canvas": {"node_comment_editor_default": "canvas"}}
            )["canvas"]["node_comment_editor_default"],
            "canvas_popover",
        )


class PropertyPaneVariantNormalizationTests(unittest.TestCase):
    def test_known_values_pass_through_case_insensitive(self) -> None:
        self.assertEqual(normalize_property_pane_variant("smart_groups"), "smart_groups")
        self.assertEqual(normalize_property_pane_variant(" ACCORDION_CARDS "), "accordion_cards")
        self.assertEqual(normalize_property_pane_variant("Palette"), "palette")

    def test_unknown_value_falls_back_to_default(self) -> None:
        self.assertEqual(
            normalize_property_pane_variant("bogus_layout"),
            DEFAULT_PROPERTY_PANE_VARIANT,
        )
        self.assertEqual(
            normalize_property_pane_variant(None),
            DEFAULT_PROPERTY_PANE_VARIANT,
        )

    def test_graphics_settings_fills_default_when_absent(self) -> None:
        normalized = normalize_graphics_settings({"shell": {}})
        self.assertEqual(
            normalized["shell"]["property_pane_variant"],
            DEFAULT_PROPERTY_PANE_VARIANT,
        )

    def test_graphics_settings_rejects_unknown_variant(self) -> None:
        normalized = normalize_graphics_settings(
            {"shell": {"property_pane_variant": "floating_bubbles"}}
        )
        self.assertEqual(
            normalized["shell"]["property_pane_variant"],
            DEFAULT_PROPERTY_PANE_VARIANT,
        )

    def test_graphics_settings_preserves_known_variant(self) -> None:
        normalized = normalize_graphics_settings(
            {"shell": {"property_pane_variant": "palette"}}
        )
        self.assertEqual(normalized["shell"]["property_pane_variant"], "palette")

    def test_status_bar_layout_defaults_and_normalizes(self) -> None:
        self.assertEqual(DEFAULT_GRAPHICS_SETTINGS["shell"]["status_bar_layout"], "option_1")
        self.assertTrue(DEFAULT_GRAPHICS_SETTINGS["shell"]["show_fps_telemetry"])
        self.assertEqual(normalize_status_bar_layout(None), "option_1")
        self.assertEqual(
            normalize_graphics_settings({})["shell"]["status_bar_layout"],
            "option_1",
        )
        self.assertTrue(
            normalize_graphics_settings({})["shell"]["show_fps_telemetry"]
        )
        self.assertEqual(
            normalize_graphics_settings(
                {"shell": {"status_bar_layout": "option_2"}}
            )["shell"]["status_bar_layout"],
            "option_2",
        )
        self.assertFalse(
            normalize_graphics_settings(
                {"shell": {"show_fps_telemetry": False}}
            )["shell"]["show_fps_telemetry"]
        )
        self.assertEqual(
            normalize_graphics_settings(
                {"shell": {"status_bar_layout": "floating_hud"}}
            )["shell"]["status_bar_layout"],
            "option_1",
        )

    def test_shell_panel_collapsed_defaults_and_normalizes(self) -> None:
        self.assertEqual(
            DEFAULT_GRAPHICS_SETTINGS["shell"]["panel_collapsed"],
            DEFAULT_SHELL_PANEL_COLLAPSED,
        )
        self.assertEqual(
            normalize_shell_panel_collapsed(None),
            DEFAULT_SHELL_PANEL_COLLAPSED,
        )
        self.assertEqual(
            normalize_graphics_settings({})["shell"]["panel_collapsed"],
            DEFAULT_SHELL_PANEL_COLLAPSED,
        )

        normalized = normalize_graphics_settings(
            {
                "shell": {
                    "panel_collapsed": {
                        "node_library": True,
                        "property_pane": False,
                        "output_panel": True,
                        "unknown": True,
                    }
                }
            }
        )["shell"]["panel_collapsed"]

        self.assertEqual(
            normalized,
            {
                "node_library": True,
                "property_pane": False,
                "output_panel": True,
            },
        )

        partial = normalize_graphics_settings(
            {"shell": {"panel_collapsed": {"property_pane": True, "output_panel": "yes"}}}
        )["shell"]["panel_collapsed"]
        self.assertEqual(
            partial,
            {
                "node_library": False,
                "property_pane": True,
                "output_panel": False,
            },
        )


class MediaPanelSettingsNormalizationTests(unittest.TestCase):
    def test_defaults_when_missing_or_invalid(self) -> None:
        self.assertEqual(
            normalize_media_panel_settings(None),
            DEFAULT_MEDIA_PANEL_SETTINGS,
        )
        normalized = normalize_graphics_settings(
            {
                "media_panel": {
                    "show_title": "false",
                    "show_frame": None,
                    "source_input_exposed": "false",
                }
            }
        )
        self.assertEqual(normalized["media_panel"], DEFAULT_MEDIA_PANEL_SETTINGS)
        self.assertNotIn("image_nodes", normalized)

    def test_bool_values_roundtrip(self) -> None:
        normalized = normalize_graphics_settings(
            {
                "media_panel": {
                    "show_title": False,
                    "show_frame": False,
                    "autoplay_animations": False,
                    "source_input_exposed": False,
                }
            }
        )
        self.assertEqual(
            normalized["media_panel"],
            {
                "show_title": False,
                "show_frame": False,
                "autoplay_animations": False,
                "source_input_exposed": False,
            },
        )


class FolderExplorerColumnWidthNormalizationTests(unittest.TestCase):
    def test_defaults_when_missing_or_invalid(self) -> None:
        self.assertEqual(DEFAULT_FOLDER_EXPLORER_COLUMN_WIDTHS, {})
        self.assertEqual(normalize_folder_explorer_column_widths(None), {})
        self.assertEqual(normalize_graphics_settings({})["folder_explorer"]["column_widths"], {})
        self.assertEqual(
            normalize_graphics_settings({"folder_explorer": "bad"})["folder_explorer"]["column_widths"],
            {},
        )

    def test_valid_full_and_partial_maps_pass_through(self) -> None:
        self.assertEqual(
            normalize_folder_explorer_column_widths(
                {"name": 240, "modified": 180, "type": 126, "size": 88}
            ),
            {"name": 240, "modified": 180, "type": 126, "size": 88},
        )
        self.assertEqual(
            normalize_graphics_settings(
                {"folder_explorer": {"column_widths": {"modified": 220}}}
            )["folder_explorer"]["column_widths"],
            {"modified": 220},
        )

    def test_invalid_values_are_ignored(self) -> None:
        self.assertEqual(
            normalize_folder_explorer_column_widths(
                {
                    "name": "240",
                    "modified": True,
                    "type": None,
                    "size": [88],
                    "unknown": 300,
                }
            ),
            {},
        )

    def test_valid_values_are_clamped(self) -> None:
        self.assertEqual(
            normalize_folder_explorer_column_widths(
                {"name": 12, "modified": 1201, "type": 70.4, "size": 70.6}
            ),
            {"name": 48, "modified": 1200, "type": 70, "size": 71},
        )


if __name__ == "__main__":
    unittest.main()

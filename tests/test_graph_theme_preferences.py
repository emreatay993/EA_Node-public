from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path

from ea_node_editor.graph_theme_defaults import DEFAULT_GRAPH_THEME_ID
from ea_node_editor.settings import DEFAULT_GRAPHICS_SETTINGS
from ea_node_editor.ui.graph_theme.service import GraphThemeService
from ea_node_editor.ui.graph_theme import is_custom_graph_theme_id
from ea_node_editor.ui.graph_theme.registry import normalize_graph_theme_definition
from ea_node_editor.ui.shell.controllers.app_preferences_controller import (
    AppPreferencesController,
    AppPreferencesStore,
    normalize_graph_theme_settings,
)


class GraphThemePreferencesTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temp_dir = tempfile.TemporaryDirectory()
        self._preferences_path = Path(self._temp_dir.name) / "app_preferences.json"
        self._store = AppPreferencesStore(path_provider=lambda: self._preferences_path)
        self._controller = AppPreferencesController(store=self._store)

    def tearDown(self) -> None:
        self._temp_dir.cleanup()

    def test_normalize_graph_theme_settings_rekeys_custom_theme_ids_and_falls_back_to_default_selection(self) -> None:
        normalized = normalize_graph_theme_settings(
            {
                "follow_shell_theme": False,
                "selected_theme_id": "missing-theme",
                "custom_themes": [
                    {
                        "theme_id": "graph_stitch_light",
                        "label": "Custom Light",
                    }
                ],
            }
        )

        self.assertFalse(normalized["follow_shell_theme"])
        self.assertEqual(normalized["selected_theme_id"], DEFAULT_GRAPH_THEME_ID)
        self.assertEqual(len(normalized["custom_themes"]), 1)
        self.assertEqual(normalized["custom_themes"][0]["label"], "Custom Light")
        self.assertTrue(is_custom_graph_theme_id(normalized["custom_themes"][0]["theme_id"]))

    def test_graph_theme_service_resolves_follow_shell_and_explicit_settings(self) -> None:
        service = GraphThemeService(theme_id="graph_stitch_dark")

        self.assertFalse(
            service.apply_settings(
                shell_theme_id="stitch_dark",
                graph_theme_settings={"follow_shell_theme": True},
            )
        )
        self.assertEqual(service.theme_id, "graph_stitch_dark")

        self.assertTrue(
            service.apply_settings(
                shell_theme_id="stitch_dark",
                graph_theme_settings={
                    "follow_shell_theme": False,
                    "selected_theme_id": "graph_ocean_light",
                },
            )
        )
        self.assertEqual(service.theme_id, "graph_ocean_light")

    def test_graph_theme_normalization_preserves_body_gradient_and_drops_retired_tokens(self) -> None:
        normalized = normalize_graph_theme_definition(
            {
                "theme_id": "graph_stitch_dark",
                "label": "Gradient Test",
                "node_tokens": {
                    "card_gradient_enabled": True,
                    "card_gradient_color": "#445566",
                    "card_gradient_direction": "radial",
                    "header_bg": "#223344",
                    "header_gradient_enabled": "true",
                    "header_gradient_color": "#112233",
                    "header_gradient_direction": "diagonal",
                },
                "category_accent_tokens": {"core": "#44AAFF"},
            }
        )

        self.assertTrue(normalized.node_tokens.card_gradient_enabled)
        self.assertEqual(normalized.node_tokens.card_gradient_color, "#445566")
        self.assertEqual(normalized.node_tokens.card_gradient_direction, "radial")
        serialized = normalized.as_dict()
        self.assertIn("header_fg", serialized["node_tokens"])
        self.assertNotIn("header_bg", serialized["node_tokens"])
        self.assertNotIn("header_gradient_enabled", serialized["node_tokens"])
        self.assertNotIn("header_gradient_color", serialized["node_tokens"])
        self.assertNotIn("header_gradient_direction", serialized["node_tokens"])
        self.assertNotIn("category_accent_tokens", serialized)

    def test_controller_can_create_duplicate_rename_and_delete_custom_graph_themes(self) -> None:
        created = self._controller.create_blank_custom_graph_theme(label="My Theme")
        duplicate = self._controller.duplicate_graph_theme("graph_stitch_light", label="Light Copy")

        self.assertTrue(is_custom_graph_theme_id(created["theme_id"]))
        self.assertIsNotNone(duplicate)
        assert duplicate is not None
        self.assertTrue(is_custom_graph_theme_id(duplicate["theme_id"]))

        renamed = self._controller.rename_custom_graph_theme(created["theme_id"], "Renamed Theme")
        self.assertIsNotNone(renamed)
        assert renamed is not None
        self.assertEqual(renamed["label"], "Renamed Theme")

        labels = [label for _theme_id, label in self._controller.graph_theme_choices()]
        self.assertIn("Renamed Theme", labels)
        self.assertIn("Light Copy", labels)

        graphics = copy.deepcopy(DEFAULT_GRAPHICS_SETTINGS)
        graphics["graph_theme"] = {
            "follow_shell_theme": False,
            "selected_theme_id": renamed["theme_id"],
            "custom_themes": self._controller.custom_graph_themes(),
        }
        self._controller.set_graphics_settings(graphics)

        self.assertTrue(self._controller.delete_custom_graph_theme(renamed["theme_id"]))
        self.assertEqual(self._controller.graph_theme_settings()["selected_theme_id"], DEFAULT_GRAPH_THEME_ID)

    def test_save_custom_graph_theme_coerces_builtin_theme_id_to_custom_identity(self) -> None:
        saved = self._controller.save_custom_graph_theme(
            {
                "theme_id": "graph_stitch_light",
                "label": "Saved Custom Light",
            }
        )

        self.assertTrue(is_custom_graph_theme_id(saved["theme_id"]))
        reloaded_controller = AppPreferencesController(store=self._store)
        persisted_themes = reloaded_controller.load()["graphics"]["graph_theme"]["custom_themes"]
        self.assertTrue(any(theme["theme_id"] == saved["theme_id"] for theme in persisted_themes))


if __name__ == "__main__":
    unittest.main()

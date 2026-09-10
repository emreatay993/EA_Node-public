from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from ea_node_editor.settings import (
    APP_PREFERENCES_KIND,
    APP_PREFERENCES_VERSION,
    DEFAULT_SELECTED_RUN_SETTINGS,
    DEFAULT_SOLUTION_SETTINGS,
    DEFAULT_SOURCE_IMPORT_MODE,
    DEFAULT_SOURCE_IMPORT_SETTINGS,
)
from ea_node_editor.ui.shell.controllers.app_preferences_controller import (
    AppPreferencesController,
    AppPreferencesStore,
)


class SourceImportPreferencesTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temp_dir = tempfile.TemporaryDirectory()
        self._preferences_path = Path(self._temp_dir.name) / "app_preferences.json"
        self._store = AppPreferencesStore(path_provider=lambda: self._preferences_path)
        self._controller = AppPreferencesController(store=self._store)

    def tearDown(self) -> None:
        self._temp_dir.cleanup()

    def test_missing_document_defaults_source_import_mode_to_external_link(self) -> None:
        document = self._controller.load()

        self.assertEqual(document["kind"], APP_PREFERENCES_KIND)
        self.assertEqual(document["version"], APP_PREFERENCES_VERSION)
        self.assertEqual(document["source_import"], DEFAULT_SOURCE_IMPORT_SETTINGS)
        self.assertEqual(document["selected_run"], DEFAULT_SELECTED_RUN_SETTINGS)
        self.assertEqual(document["solution"], DEFAULT_SOLUTION_SETTINGS)
        self.assertEqual(self._controller.source_import_mode(), DEFAULT_SOURCE_IMPORT_MODE)
        self.assertEqual(self._controller.solution_default_mode(), "auto")
        self.assertTrue(self._controller.selected_run_preview_before_run())

    def test_invalid_source_import_mode_normalizes_to_external_link(self) -> None:
        self._preferences_path.write_text(
            json.dumps(
                {
                    "kind": APP_PREFERENCES_KIND,
                    "version": APP_PREFERENCES_VERSION,
                    "source_import": {
                        "default_mode": "archive_everything",
                    },
                }
            ),
            encoding="utf-8",
        )

        document = self._controller.load()

        self.assertEqual(document["source_import"], DEFAULT_SOURCE_IMPORT_SETTINGS)
        self.assertEqual(document["selected_run"], DEFAULT_SELECTED_RUN_SETTINGS)
        self.assertEqual(document["solution"], DEFAULT_SOLUTION_SETTINGS)
        self.assertEqual(self._controller.source_import_mode(), DEFAULT_SOURCE_IMPORT_MODE)

    def test_set_source_import_mode_persists_managed_copy_and_round_trips(self) -> None:
        mode = self._controller.set_source_import_mode(" MANAGED_COPY ")

        self.assertEqual(mode, "managed_copy")
        persisted = json.loads(self._preferences_path.read_text(encoding="utf-8"))
        self.assertEqual(
            persisted["source_import"],
            {
                "default_mode": "managed_copy",
            },
        )
        reloaded_controller = AppPreferencesController(store=self._store)
        self.assertEqual(reloaded_controller.source_import_mode(), "managed_copy")
        self.assertEqual(
            reloaded_controller.load()["source_import"],
            {
                "default_mode": "managed_copy",
            },
        )

    def test_solution_mode_write_preserves_sibling_settings_and_round_trips(self) -> None:
        solution_mode = self._controller.set_solution_default_mode(" MANUAL ")
        preview_enabled = self._controller.set_selected_run_preview_before_run(False)

        self.assertEqual(solution_mode, "manual")
        self.assertFalse(preview_enabled)
        persisted = json.loads(self._preferences_path.read_text(encoding="utf-8"))
        self.assertEqual(persisted["solution"], {"default_mode": "manual"})
        self.assertEqual(persisted["selected_run"], {"preview_before_run": False})

        reloaded_controller = AppPreferencesController(store=self._store)
        self.assertEqual(reloaded_controller.solution_default_mode(), "manual")
        self.assertFalse(reloaded_controller.selected_run_preview_before_run())

    def test_default_python_executable_round_trips_normalized_text(self) -> None:
        self.assertEqual(self._controller.python_runtime_settings(), {"default_executable": ""})
        self.assertEqual(self._controller.default_python_executable(), "")

        stored = self._controller.set_default_python_executable(
            '  " C:\\Python\\python.exe "  '
        )

        self.assertEqual(stored, "C:\\Python\\python.exe")
        self.assertEqual(
            AppPreferencesController(store=self._store).default_python_executable(),
            "C:\\Python\\python.exe",
        )
        persisted = json.loads(self._preferences_path.read_text(encoding="utf-8"))
        self.assertEqual(
            persisted["python_runtime"],
            {"default_executable": "C:\\Python\\python.exe"},
        )

    def test_failed_default_python_write_leaves_cached_document_unchanged(self) -> None:
        before = self._controller.load()

        with (
            mock.patch.object(
                self._store,
                "persist_document",
                side_effect=OSError("write failed"),
            ),
            self.assertRaisesRegex(OSError, "write failed"),
        ):
            self._controller.set_default_python_executable("C:\\Python\\python.exe")

        self.assertEqual(self._controller.document(), before)
        self.assertEqual(self._controller.default_python_executable(), "")

    def test_node_library_usage_keeps_the_last_64_choices_and_round_trips(self) -> None:
        for index in range(66):
            self._controller.record_node_library_usage(f"core.node_{index}")

        self.assertEqual(
            self._controller.node_library_usage(),
            [f"core.node_{index}" for index in range(2, 66)],
        )
        reloaded_controller = AppPreferencesController(store=self._store)
        self.assertEqual(
            reloaded_controller.node_library_usage(),
            [f"core.node_{index}" for index in range(2, 66)],
        )

    def test_explicit_store_and_document_replacement_apis_keep_cache_in_sync(self) -> None:
        initial = self._controller.load()
        replacement = dict(initial)
        replacement["source_import"] = {"default_mode": "managed_copy"}

        self.assertIs(self._controller.store(), self._store)
        replaced = self._controller.replace_document(replacement)
        self.assertEqual(replaced["source_import"]["default_mode"], "managed_copy")
        self.assertFalse(self._preferences_path.exists())

        persisted = self._controller.persist_document(replaced)
        self.assertEqual(persisted, self._controller.document())
        self.assertEqual(
            json.loads(self._preferences_path.read_text(encoding="utf-8")),
            persisted,
        )

    def test_failed_explicit_persist_leaves_cached_document_unchanged(self) -> None:
        before = self._controller.load()
        replacement = dict(before)
        replacement["source_import"] = {"default_mode": "managed_copy"}

        with (
            mock.patch.object(
                self._store,
                "persist_document",
                side_effect=OSError("write failed"),
            ),
            self.assertRaisesRegex(OSError, "write failed"),
        ):
            self._controller.persist_document(replacement)

        self.assertEqual(self._controller.document(), before)


if __name__ == "__main__":
    unittest.main()

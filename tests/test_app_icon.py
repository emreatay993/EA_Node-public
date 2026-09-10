from __future__ import annotations

import unittest

from PyQt6.QtWidgets import QApplication, QWidget

from ea_node_editor.ui.app_icon import (
    APP_ICON_SIZES,
    app_icon,
    app_icon_assets,
    app_icon_ico_path,
    app_icon_png_path,
    app_icon_root,
    app_icon_svg_path,
    apply_application_icon,
    apply_window_icon,
)


class AppIconTests(unittest.TestCase):
    def setUp(self) -> None:
        self.app = QApplication.instance() or QApplication([])

    def test_asset_set_resolves_generated_files_for_all_variants(self) -> None:
        self.assertTrue(app_icon_root().is_dir())
        self.assertTrue(app_icon_ico_path().is_file())

        for variant in ("opaque", "transparent", "minimal"):
            with self.subTest(variant=variant):
                assets = app_icon_assets(variant)
                self.assertTrue(assets.svg_path.is_file())
                self.assertEqual(len(assets.png_paths), len(APP_ICON_SIZES))
                for png_path in assets.png_paths:
                    self.assertTrue(png_path.is_file(), png_path.name)

    def test_path_helpers_resolve_expected_file_names(self) -> None:
        self.assertEqual(app_icon_svg_path().name, "corex_app.svg")
        self.assertEqual(app_icon_svg_path("transparent").name, "corex_app_transparent.svg")
        self.assertEqual(app_icon_png_path(64).name, "corex_app_64.png")
        self.assertEqual(app_icon_png_path(128, "minimal").name, "corex_app_minimal_128.png")

    def test_app_icon_renders_to_pixmap(self) -> None:
        pixmap = app_icon().pixmap(64, 64)
        self.assertFalse(pixmap.isNull())

    def test_application_and_window_helpers_apply_icon(self) -> None:
        window = QWidget()
        try:
            app_icon_value = apply_application_icon(self.app)
            window_icon_value = apply_window_icon(window)
            self.assertFalse(app_icon_value.isNull())
            self.assertFalse(window_icon_value.isNull())
            self.assertFalse(self.app.windowIcon().isNull())
            self.assertFalse(window.windowIcon().isNull())
        finally:
            window.close()
            window.deleteLater()

    def test_unknown_variant_raises_key_error(self) -> None:
        with self.assertRaises(KeyError):
            app_icon_svg_path("missing")  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()

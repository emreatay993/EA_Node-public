from __future__ import annotations

import unittest

from ea_node_editor.ui.passive_style_presets import (
    PassiveStylePresetCatalog,
    built_in_style_presets,
)


class PassiveStylePresetCatalogTests(unittest.TestCase):
    def test_flowchart_classic_preset_matches_polished_defaults(self) -> None:
        built_ins = built_in_style_presets("node")
        flowchart_classic = next(entry for entry in built_ins if entry["preset_id"] == "builtin_node_flowchart_classic")

        self.assertTrue(flowchart_classic["read_only"])
        self.assertEqual(
            flowchart_classic["style"],
            {
                "fill_color": "#F5FAFD",
                "border_color": "#61798B",
                "text_color": "#173247",
                "border_width": 2.0,
                "font_weight": "bold",
            },
        )

    def test_catalog_exposes_read_only_starters_without_serializing_them(self) -> None:
        catalog = PassiveStylePresetCatalog("node", [])

        built_ins = built_in_style_presets("node")
        edge_built_ins = built_in_style_presets("edge")
        retired_keys = {
            "accent_color",
            "header_color",
            "header_gradient_enabled",
            "header_gradient_color",
            "header_gradient_direction",
        }

        self.assertTrue(built_ins)
        self.assertTrue(edge_built_ins)
        self.assertTrue(all(retired_keys.isdisjoint(entry["style"]) for entry in built_ins))
        self.assertEqual(catalog.user_presets(), [])
        self.assertEqual(catalog.entries()[: len(built_ins)], built_ins)
        self.assertTrue(all(entry.get("read_only") for entry in built_ins))

        saved = catalog.save_new(
            "Project Accent",
            {
                "fill_color": "#112233",
                "border_width": "2.5",
                "gradient_enabled": True,
                "gradient_color": "#334455",
                "gradient_direction": "west",
                "header_gradient_enabled": False,
                "header_gradient_color": "#556677",
                "header_gradient_direction": "east",
                "accent_color": "#778899",
                "header_color": "#AABBCC",
            },
        )
        assert saved is not None

        self.assertFalse(saved.get("read_only"))
        self.assertRegex(saved["preset_id"], r"^node_preset_[0-9a-f]{8}$")
        self.assertEqual(
            catalog.user_presets(),
            [
                {
                    "preset_id": saved["preset_id"],
                    "name": "Project Accent",
                    "style": {
                        "fill_color": "#112233",
                        "border_width": 2.5,
                        "gradient_enabled": True,
                        "gradient_color": "#334455",
                        "gradient_direction": "west",
                    },
                }
            ],
        )

if __name__ == "__main__":
    unittest.main()

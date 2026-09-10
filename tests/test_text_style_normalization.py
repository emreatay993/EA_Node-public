from __future__ import annotations

import unittest

from ea_node_editor.text_style import (
    DEFAULT_INHERITED_RICH_TEXT_STYLE_PROPERTIES,
    RICH_TEXT_SLOT_STYLE_KEYS,
    TEXT_ANNOTATION_STYLE_KEYS,
    normalize_text_annotation_style_payload,
    normalize_recent_text_colors,
    normalize_text_style_color,
    normalize_text_style_properties,
    record_recent_text_color,
    rich_text_format_property_key,
    rich_text_slot_property_keys,
    rich_text_style_property_key,
)


class TextStyleNormalizationTests(unittest.TestCase):
    def test_text_style_properties_normalize_defaults_and_invalid_values(self) -> None:
        defaults = normalize_text_style_properties({})
        self.assertEqual(defaults["font_family"], "Caveat")
        self.assertEqual(normalize_text_style_properties({"font_family": ""})["font_family"], "")
        self.assertEqual(defaults["text_color"], "")
        self.assertEqual(defaults["horizontal_alignment"], "center")
        self.assertEqual(defaults["vertical_alignment"], "middle")

        normalized = normalize_text_style_properties(
            {
                "text": "# Heading",
                "format": "HTML",
                "font_family": "  Segoe UI  ",
                "font_size": 999,
                "font_weight": "BOLD",
                "italic": "yes",
                "underline": "0",
                "strikeout": "no",
                "text_color": "#aabbcc",
                "background_color": "bad",
                "horizontal_alignment": "RIGHT",
                "vertical_alignment": "bogus",
                "wrap_mode": "ANYWHERE",
                "line_height": 8,
                "letter_spacing": -20,
                "padding": -5,
                "opacity": 140,
            }
        )

        self.assertEqual(normalized["text"], "# Heading")
        self.assertEqual(normalized["format"], "markdown")
        self.assertEqual(normalized["font_family"], "Segoe UI")
        self.assertEqual(normalized["font_size"], 144)
        self.assertEqual(normalized["font_weight"], "bold")
        self.assertTrue(normalized["italic"])
        self.assertFalse(normalized["underline"])
        self.assertFalse(normalized["strikeout"])
        self.assertEqual(normalized["text_color"], "#AABBCC")
        self.assertEqual(normalized["background_color"], "")
        self.assertEqual(normalized["horizontal_alignment"], "right")
        self.assertEqual(normalized["vertical_alignment"], "middle")
        self.assertEqual(normalized["wrap_mode"], "anywhere")
        self.assertEqual(normalized["line_height"], 4.0)
        self.assertEqual(normalized["letter_spacing"], -10.0)
        self.assertEqual(normalized["padding"], 0)
        self.assertEqual(normalized["opacity"], 100)

    def test_recent_text_colors_are_valid_deduped_and_newest_first(self) -> None:
        self.assertEqual(
            normalize_recent_text_colors(["#112233", "bad", "#112233", "#aabbcc"]),
            ["#112233", "#AABBCC"],
        )
        self.assertEqual(
            record_recent_text_color(["#112233", "#AABBCC"], "#112233"),
            ["#112233", "#AABBCC"],
        )
        self.assertEqual(
            record_recent_text_color(["#112233", "#AABBCC"], "#445566"),
            ["#445566", "#112233", "#AABBCC"],
        )
        self.assertEqual(
            normalize_text_style_color("transparent", "#F0F4FB"),
            "#F0F4FB",
        )

    def test_text_annotation_style_payload_keeps_visual_style_only(self) -> None:
        normalized = normalize_text_annotation_style_payload(
            {
                "text": "Do not copy content",
                "format": "plain",
                "font_family": "  Segoe UI  ",
                "font_size": 999,
                "font_weight": "bold",
                "italic": "yes",
                "underline": "1",
                "strikeout": False,
                "text_color": "#aabbcc",
                "background_color": "bad",
                "horizontal_alignment": "right",
                "vertical_alignment": "bottom",
                "wrap_mode": "none",
                "line_height": 9,
                "letter_spacing": -12,
                "padding": 999,
                "opacity": -20,
            }
        )

        self.assertEqual(tuple(normalized), TEXT_ANNOTATION_STYLE_KEYS)
        self.assertNotIn("text", normalized)
        self.assertNotIn("format", normalized)
        self.assertEqual(normalized["font_family"], "Segoe UI")
        self.assertEqual(normalized["font_size"], 144)
        self.assertEqual(normalized["text_color"], "#AABBCC")
        self.assertEqual(normalized["background_color"], "")
        self.assertEqual(normalized["line_height"], 4.0)
        self.assertEqual(normalized["letter_spacing"], -10.0)
        self.assertEqual(normalized["padding"], 64)
        self.assertEqual(normalized["opacity"], 0)

    def test_rich_text_slot_keys_preserve_bare_text_and_prefix_other_fields(self) -> None:
        self.assertEqual(rich_text_format_property_key("text"), "format")
        self.assertEqual(rich_text_style_property_key("text", "font_size"), "font_size")
        self.assertEqual(rich_text_format_property_key("body"), "body_format")
        self.assertEqual(rich_text_style_property_key("body", "font_size"), "body_font_size")
        self.assertEqual(rich_text_style_property_key("body_top", "text_color"), "body_top_text_color")

        body_keys = rich_text_slot_property_keys("body")
        self.assertEqual(body_keys[0], "body")
        self.assertEqual(body_keys[1], "body_format")
        self.assertEqual(body_keys[2:], tuple(f"body_{key}" for key in RICH_TEXT_SLOT_STYLE_KEYS))
        self.assertEqual(DEFAULT_INHERITED_RICH_TEXT_STYLE_PROPERTIES["format"], "plain")
        self.assertEqual(DEFAULT_INHERITED_RICH_TEXT_STYLE_PROPERTIES["font_size"], 0)


if __name__ == "__main__":
    unittest.main()

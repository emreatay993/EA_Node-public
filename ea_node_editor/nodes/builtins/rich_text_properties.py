from __future__ import annotations

from collections.abc import Iterable

from ea_node_editor.nodes.node_specs import PropertySpec
from ea_node_editor.text_style import (
    DEFAULT_INHERITED_RICH_TEXT_STYLE_PROPERTIES,
    DEFAULT_TEXT_STYLE_PROPERTIES,
    RICH_TEXT_SLOT_STYLE_KEYS,
    TEXT_STYLE_FONT_WEIGHTS,
    TEXT_STYLE_FORMATS,
    TEXT_STYLE_HORIZONTAL_ALIGNMENTS,
    TEXT_STYLE_VERTICAL_ALIGNMENTS,
    TEXT_STYLE_WRAP_MODES,
    rich_text_format_property_key,
    rich_text_style_property_key,
)


def rich_text_slot_property_specs(
    content_key: str,
    *,
    content_default: str | None = None,
    content_label: str = "",
    content_inspector_editor: str = "textarea",
    default_format: str = "plain",
    inherited_style_defaults: bool = True,
) -> tuple[PropertySpec, ...]:
    specs: list[PropertySpec] = []
    normalized_content_key = str(content_key or "").strip()
    if content_default is not None:
        specs.append(
            PropertySpec(
                normalized_content_key,
                "str",
                str(content_default),
                content_label or normalized_content_key.replace("_", " ").title(),
                inspector_editor=content_inspector_editor,
            )
        )
    specs.append(
        PropertySpec(
            rich_text_format_property_key(normalized_content_key),
            "enum",
            _normalized_format_default(default_format),
            "Format",
            enum_values=TEXT_STYLE_FORMATS,
            inspector_visible=not inherited_style_defaults,
            inspector_editor="enum" if not inherited_style_defaults else "",
        )
    )
    defaults = (
        DEFAULT_INHERITED_RICH_TEXT_STYLE_PROPERTIES
        if inherited_style_defaults
        else DEFAULT_TEXT_STYLE_PROPERTIES
    )
    for style_key in RICH_TEXT_SLOT_STYLE_KEYS:
        specs.append(_style_property_spec(normalized_content_key, style_key, defaults, inherited_style_defaults))
    return tuple(specs)


def rich_text_extra_slot_property_specs(
    *content_keys: str,
    default_format: str = "plain",
) -> tuple[PropertySpec, ...]:
    specs: list[PropertySpec] = []
    for content_key in content_keys:
        specs.extend(
            rich_text_slot_property_specs(
                content_key,
                default_format=default_format,
                inherited_style_defaults=True,
            )
        )
    return tuple(specs)


def _normalized_format_default(value: str) -> str:
    normalized = str(value or "").strip().lower()
    return normalized if normalized in TEXT_STYLE_FORMATS else "plain"


def _style_property_spec(
    content_key: str,
    style_key: str,
    defaults: dict[str, object],
    inherited_style_defaults: bool,
) -> PropertySpec:
    key = rich_text_style_property_key(content_key, style_key)
    label = style_key.replace("_", " ").title()
    inspector_visible = not inherited_style_defaults
    if style_key in {"font_family", "text_color", "background_color"}:
        inspector_editor = (
            "font_family"
            if style_key == "font_family"
            else "color"
        ) if inspector_visible else ""
        inline_editor = "color" if inspector_visible and style_key in {"text_color", "background_color"} else ""
        return PropertySpec(
            key,
            "str",
            str(defaults[style_key]),
            label,
            inline_editor=inline_editor,
            inspector_editor=inspector_editor,
            inspector_visible=inspector_visible,
        )
    if style_key == "font_weight":
        if inherited_style_defaults:
            return PropertySpec(key, "str", str(defaults[style_key]), label, inspector_visible=False)
        return PropertySpec(
            key,
            "enum",
            str(defaults[style_key]),
            label,
            enum_values=TEXT_STYLE_FONT_WEIGHTS,
            inspector_editor="enum",
        )
    if style_key in {"horizontal_alignment", "vertical_alignment", "wrap_mode"}:
        values: Iterable[str]
        if style_key == "horizontal_alignment":
            values = TEXT_STYLE_HORIZONTAL_ALIGNMENTS
        elif style_key == "vertical_alignment":
            values = TEXT_STYLE_VERTICAL_ALIGNMENTS
        else:
            values = TEXT_STYLE_WRAP_MODES
        if inherited_style_defaults:
            return PropertySpec(key, "str", str(defaults[style_key]), label, inspector_visible=False)
        return PropertySpec(
            key,
            "enum",
            str(defaults[style_key]),
            label,
            enum_values=tuple(values),
            inspector_editor="enum",
        )
    if style_key in {"italic", "underline", "strikeout"}:
        return PropertySpec(
            key,
            "bool",
            bool(defaults[style_key]),
            label,
            inspector_visible=inspector_visible,
        )
    if style_key in {"font_size", "padding", "opacity"}:
        return PropertySpec(
            key,
            "int",
            int(defaults[style_key]),
            label,
            inspector_visible=inspector_visible,
        )
    return PropertySpec(
        key,
        "float",
        float(defaults[style_key]),
        label,
        inspector_visible=inspector_visible,
    )


__all__ = [
    "rich_text_extra_slot_property_specs",
    "rich_text_slot_property_specs",
]

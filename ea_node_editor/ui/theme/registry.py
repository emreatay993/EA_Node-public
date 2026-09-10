from __future__ import annotations

from dataclasses import dataclass

from ea_node_editor.ui.theme.tokens import STITCH_DARK_V1, STITCH_LIGHT_V1, ThemeTokens

DEFAULT_THEME_ID = "stitch_dark"


@dataclass(frozen=True, slots=True)
class ThemeDefinition:
    theme_id: str
    label: str
    tokens: ThemeTokens


THEME_REGISTRY: dict[str, ThemeDefinition] = {
    "stitch_dark": ThemeDefinition(
        theme_id="stitch_dark",
        label="Stitch Dark",
        tokens=STITCH_DARK_V1,
    ),
    "stitch_light": ThemeDefinition(
        theme_id="stitch_light",
        label="Stitch Light",
        tokens=STITCH_LIGHT_V1,
    ),
}


def theme_choices() -> tuple[tuple[str, str], ...]:
    return tuple((theme.theme_id, theme.label) for theme in THEME_REGISTRY.values())


def is_known_theme_id(theme_id: object) -> bool:
    return str(theme_id).strip() in THEME_REGISTRY


def resolve_theme(theme_id: object) -> ThemeDefinition:
    normalized = str(theme_id).strip()
    return THEME_REGISTRY.get(normalized, THEME_REGISTRY[DEFAULT_THEME_ID])


def resolve_theme_id(theme_id: object) -> str:
    return resolve_theme(theme_id).theme_id


def resolve_theme_tokens(theme_id: object) -> ThemeTokens:
    return resolve_theme(theme_id).tokens


__all__ = [
    "DEFAULT_THEME_ID",
    "THEME_REGISTRY",
    "ThemeDefinition",
    "is_known_theme_id",
    "resolve_theme",
    "resolve_theme_id",
    "resolve_theme_tokens",
    "theme_choices",
]

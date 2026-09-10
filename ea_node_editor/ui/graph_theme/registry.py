from __future__ import annotations

import secrets
from collections.abc import Collection, Mapping, Sequence
from dataclasses import asdict, dataclass, fields
from typing import Any

from ea_node_editor.graph_theme_defaults import DEFAULT_GRAPH_THEME_ID
from ea_node_editor.ui.graph_theme.palettes import (
    AMETHYST_DARK_EDGE_TOKENS,
    AMETHYST_DARK_NODE_TOKENS,
    AMETHYST_LIGHT_EDGE_TOKENS,
    AMETHYST_LIGHT_NODE_TOKENS,
    AMETHYST_PORT_KIND_TOKENS,
    EMBER_DARK_EDGE_TOKENS,
    EMBER_DARK_NODE_TOKENS,
    EMBER_LIGHT_EDGE_TOKENS,
    EMBER_LIGHT_NODE_TOKENS,
    EMBER_PORT_KIND_TOKENS,
    NORD_DARK_EDGE_TOKENS,
    NORD_DARK_NODE_TOKENS,
    NORD_LIGHT_EDGE_TOKENS,
    NORD_LIGHT_NODE_TOKENS,
    NORD_PORT_KIND_TOKENS,
    OCEAN_DARK_EDGE_TOKENS,
    OCEAN_DARK_NODE_TOKENS,
    OCEAN_LIGHT_EDGE_TOKENS,
    OCEAN_LIGHT_NODE_TOKENS,
    OCEAN_PORT_KIND_TOKENS,
    VERDANT_DARK_EDGE_TOKENS,
    VERDANT_DARK_NODE_TOKENS,
    VERDANT_LIGHT_EDGE_TOKENS,
    VERDANT_LIGHT_NODE_TOKENS,
    VERDANT_PORT_KIND_TOKENS,
)
from ea_node_editor.ui.graph_theme.tokens import (
    GRAPH_NODE_GRADIENT_DIRECTIONS,
    GRAPH_PORT_KIND_TOKENS_V1,
    GRAPH_STITCH_DARK_EDGE_TOKENS_V1,
    GRAPH_STITCH_DARK_NODE_TOKENS_V1,
    GRAPH_STITCH_DARK_PORT_STATE_TOKENS_V1,
    GRAPH_STITCH_LIGHT_EDGE_TOKENS_V1,
    GRAPH_STITCH_LIGHT_NODE_TOKENS_V1,
    GRAPH_STITCH_LIGHT_PORT_STATE_TOKENS_V1,
    GraphEdgeTokens,
    GraphNodeTokens,
    GraphPortKindTokens,
    GraphPortStateTokens,
)
from ea_node_editor.ui.theme.registry import resolve_theme_id

CUSTOM_GRAPH_THEME_ID_PREFIX = "custom_graph_theme_"
DEFAULT_CUSTOM_GRAPH_THEME_LABEL = "Custom Graph Theme"


@dataclass(frozen=True, slots=True)
class GraphThemeDefinition:
    theme_id: str
    label: str
    node_tokens: GraphNodeTokens
    edge_tokens: GraphEdgeTokens
    port_kind_tokens: GraphPortKindTokens
    # Grip flow-state colors are shared per brightness rather than authored
    # per palette family: warning/error/neutral must read as alerts in every
    # theme, so hue-family variation would only dilute them.
    port_state_tokens: GraphPortStateTokens = GRAPH_STITCH_DARK_PORT_STATE_TOKENS_V1

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


SHELL_THEME_TO_GRAPH_THEME = {
    "stitch_dark": "graph_stitch_dark",
    "stitch_light": "graph_stitch_light",
}


GRAPH_THEME_REGISTRY: dict[str, GraphThemeDefinition] = {
    "graph_stitch_dark": GraphThemeDefinition(
        theme_id="graph_stitch_dark",
        label="Graph Stitch Dark",
        node_tokens=GRAPH_STITCH_DARK_NODE_TOKENS_V1,
        edge_tokens=GRAPH_STITCH_DARK_EDGE_TOKENS_V1,
        port_kind_tokens=GRAPH_PORT_KIND_TOKENS_V1,
        port_state_tokens=GRAPH_STITCH_DARK_PORT_STATE_TOKENS_V1,
    ),
    "graph_stitch_light": GraphThemeDefinition(
        theme_id="graph_stitch_light",
        label="Graph Stitch Light",
        node_tokens=GRAPH_STITCH_LIGHT_NODE_TOKENS_V1,
        edge_tokens=GRAPH_STITCH_LIGHT_EDGE_TOKENS_V1,
        port_kind_tokens=GRAPH_PORT_KIND_TOKENS_V1,
        port_state_tokens=GRAPH_STITCH_LIGHT_PORT_STATE_TOKENS_V1,
    ),
    "graph_ocean_dark": GraphThemeDefinition(
        theme_id="graph_ocean_dark",
        label="Graph Ocean Dark",
        node_tokens=OCEAN_DARK_NODE_TOKENS,
        edge_tokens=OCEAN_DARK_EDGE_TOKENS,
        port_kind_tokens=OCEAN_PORT_KIND_TOKENS,
        port_state_tokens=GRAPH_STITCH_DARK_PORT_STATE_TOKENS_V1,
    ),
    "graph_ocean_light": GraphThemeDefinition(
        theme_id="graph_ocean_light",
        label="Graph Ocean Light",
        node_tokens=OCEAN_LIGHT_NODE_TOKENS,
        edge_tokens=OCEAN_LIGHT_EDGE_TOKENS,
        port_kind_tokens=OCEAN_PORT_KIND_TOKENS,
        port_state_tokens=GRAPH_STITCH_LIGHT_PORT_STATE_TOKENS_V1,
    ),
    "graph_ember_dark": GraphThemeDefinition(
        theme_id="graph_ember_dark",
        label="Graph Ember Dark",
        node_tokens=EMBER_DARK_NODE_TOKENS,
        edge_tokens=EMBER_DARK_EDGE_TOKENS,
        port_kind_tokens=EMBER_PORT_KIND_TOKENS,
        port_state_tokens=GRAPH_STITCH_DARK_PORT_STATE_TOKENS_V1,
    ),
    "graph_ember_light": GraphThemeDefinition(
        theme_id="graph_ember_light",
        label="Graph Ember Light",
        node_tokens=EMBER_LIGHT_NODE_TOKENS,
        edge_tokens=EMBER_LIGHT_EDGE_TOKENS,
        port_kind_tokens=EMBER_PORT_KIND_TOKENS,
        port_state_tokens=GRAPH_STITCH_LIGHT_PORT_STATE_TOKENS_V1,
    ),
    "graph_verdant_dark": GraphThemeDefinition(
        theme_id="graph_verdant_dark",
        label="Graph Verdant Dark",
        node_tokens=VERDANT_DARK_NODE_TOKENS,
        edge_tokens=VERDANT_DARK_EDGE_TOKENS,
        port_kind_tokens=VERDANT_PORT_KIND_TOKENS,
        port_state_tokens=GRAPH_STITCH_DARK_PORT_STATE_TOKENS_V1,
    ),
    "graph_verdant_light": GraphThemeDefinition(
        theme_id="graph_verdant_light",
        label="Graph Verdant Light",
        node_tokens=VERDANT_LIGHT_NODE_TOKENS,
        edge_tokens=VERDANT_LIGHT_EDGE_TOKENS,
        port_kind_tokens=VERDANT_PORT_KIND_TOKENS,
        port_state_tokens=GRAPH_STITCH_LIGHT_PORT_STATE_TOKENS_V1,
    ),
    "graph_amethyst_dark": GraphThemeDefinition(
        theme_id="graph_amethyst_dark",
        label="Graph Amethyst Dark",
        node_tokens=AMETHYST_DARK_NODE_TOKENS,
        edge_tokens=AMETHYST_DARK_EDGE_TOKENS,
        port_kind_tokens=AMETHYST_PORT_KIND_TOKENS,
        port_state_tokens=GRAPH_STITCH_DARK_PORT_STATE_TOKENS_V1,
    ),
    "graph_amethyst_light": GraphThemeDefinition(
        theme_id="graph_amethyst_light",
        label="Graph Amethyst Light",
        node_tokens=AMETHYST_LIGHT_NODE_TOKENS,
        edge_tokens=AMETHYST_LIGHT_EDGE_TOKENS,
        port_kind_tokens=AMETHYST_PORT_KIND_TOKENS,
        port_state_tokens=GRAPH_STITCH_LIGHT_PORT_STATE_TOKENS_V1,
    ),
    "graph_nord_dark": GraphThemeDefinition(
        theme_id="graph_nord_dark",
        label="Graph Nord Dark",
        node_tokens=NORD_DARK_NODE_TOKENS,
        edge_tokens=NORD_DARK_EDGE_TOKENS,
        port_kind_tokens=NORD_PORT_KIND_TOKENS,
        port_state_tokens=GRAPH_STITCH_DARK_PORT_STATE_TOKENS_V1,
    ),
    "graph_nord_light": GraphThemeDefinition(
        theme_id="graph_nord_light",
        label="Graph Nord Light",
        node_tokens=NORD_LIGHT_NODE_TOKENS,
        edge_tokens=NORD_LIGHT_EDGE_TOKENS,
        port_kind_tokens=NORD_PORT_KIND_TOKENS,
        port_state_tokens=GRAPH_STITCH_LIGHT_PORT_STATE_TOKENS_V1,
    ),
}


def graph_theme_choices(custom_themes: Any = None) -> tuple[tuple[str, str], ...]:
    choices = [(theme.theme_id, theme.label) for theme in GRAPH_THEME_REGISTRY.values()]
    choices.extend((theme.theme_id, theme.label) for theme in normalize_custom_graph_themes(custom_themes))
    return tuple(choices)


def graph_theme_registry(custom_themes: Any = None) -> dict[str, GraphThemeDefinition]:
    registry = dict(GRAPH_THEME_REGISTRY)
    registry.update({theme.theme_id: theme for theme in normalize_custom_graph_themes(custom_themes)})
    return registry


def is_known_graph_theme_id(theme_id: object, *, custom_themes: Any = None) -> bool:
    return str(theme_id).strip() in graph_theme_registry(custom_themes)


def resolve_graph_theme(theme_id: object, *, custom_themes: Any = None) -> GraphThemeDefinition:
    if isinstance(theme_id, GraphThemeDefinition):
        return theme_id
    if isinstance(theme_id, Mapping):
        return normalize_graph_theme_definition(theme_id)
    normalized = str(theme_id).strip()
    return graph_theme_registry(custom_themes).get(normalized, GRAPH_THEME_REGISTRY[DEFAULT_GRAPH_THEME_ID])


def resolve_graph_theme_id(theme_id: object, *, custom_themes: Any = None) -> str:
    return resolve_graph_theme(theme_id, custom_themes=custom_themes).theme_id


def normalize_graph_theme_definition(
    payload: Any,
    *,
    fallback_theme_id: object = DEFAULT_GRAPH_THEME_ID,
    default_theme_id: object | None = None,
    default_label: object | None = None,
) -> GraphThemeDefinition:
    source = _graph_theme_mapping(payload)
    fallback_theme = _fallback_graph_theme(source.get("theme_id"), fallback_theme_id)
    theme_id = _normalize_graph_theme_identity(
        source.get("theme_id"),
        default=default_theme_id if default_theme_id is not None else fallback_theme.theme_id,
    )
    label = _normalize_theme_label(
        source.get("label"),
        default=default_label if default_label is not None else fallback_theme.label,
    )
    return GraphThemeDefinition(
        theme_id=theme_id,
        label=label,
        node_tokens=_normalize_tokens(source.get("node_tokens"), fallback_theme.node_tokens),
        edge_tokens=_normalize_tokens(source.get("edge_tokens"), fallback_theme.edge_tokens),
        port_kind_tokens=_normalize_tokens(source.get("port_kind_tokens"), fallback_theme.port_kind_tokens),
        port_state_tokens=_normalize_tokens(source.get("port_state_tokens"), fallback_theme.port_state_tokens),
    )


def normalize_custom_graph_theme_definition(
    payload: Any,
    *,
    reserved_theme_ids: Collection[str] = (),
) -> GraphThemeDefinition:
    reserved = set(str(theme_id).strip() for theme_id in reserved_theme_ids if str(theme_id).strip())
    theme = normalize_graph_theme_definition(
        payload,
        fallback_theme_id=DEFAULT_GRAPH_THEME_ID,
        default_theme_id=_generate_custom_graph_theme_id(reserved),
        default_label=DEFAULT_CUSTOM_GRAPH_THEME_LABEL,
    )
    theme_id = theme.theme_id
    if not is_custom_graph_theme_id(theme_id) or theme_id in GRAPH_THEME_REGISTRY or theme_id in reserved:
        theme_id = _generate_custom_graph_theme_id(reserved)
    return _clone_graph_theme(theme, theme_id=theme_id)


def normalize_custom_graph_themes(payload: Any) -> tuple[GraphThemeDefinition, ...]:
    if not isinstance(payload, Sequence) or isinstance(payload, (str, bytes, bytearray)):
        return ()

    themes: list[GraphThemeDefinition] = []
    reserved = set(GRAPH_THEME_REGISTRY)
    for item in payload:
        if not isinstance(item, (GraphThemeDefinition, Mapping)):
            continue
        theme = normalize_custom_graph_theme_definition(item, reserved_theme_ids=reserved)
        reserved.add(theme.theme_id)
        themes.append(theme)
    return tuple(themes)


def serialize_custom_graph_themes(payload: Any) -> list[dict[str, object]]:
    return [theme.as_dict() for theme in normalize_custom_graph_themes(payload)]


def create_blank_custom_graph_theme(*, custom_themes: Any = None, label: object | None = None) -> GraphThemeDefinition:
    theme = resolve_graph_theme(DEFAULT_GRAPH_THEME_ID)
    return _clone_graph_theme(
        theme,
        theme_id=_generate_custom_graph_theme_id(graph_theme_registry(custom_themes)),
        label=_normalize_theme_label(label, default=DEFAULT_CUSTOM_GRAPH_THEME_LABEL),
    )


def duplicate_graph_theme_as_custom(
    theme: object,
    *,
    custom_themes: Any = None,
    label: object | None = None,
) -> GraphThemeDefinition:
    source = resolve_graph_theme(theme, custom_themes=custom_themes)
    return _clone_graph_theme(
        source,
        theme_id=_generate_custom_graph_theme_id(graph_theme_registry(custom_themes)),
        label=_normalize_theme_label(label, default=f"{source.label} Copy"),
    )


def is_custom_graph_theme_id(theme_id: object) -> bool:
    normalized = str(theme_id).strip().lower()
    if not normalized.startswith(CUSTOM_GRAPH_THEME_ID_PREFIX):
        return False
    suffix = normalized.removeprefix(CUSTOM_GRAPH_THEME_ID_PREFIX)
    return len(suffix) == 8 and all(character in "0123456789abcdef" for character in suffix)


def default_graph_theme_id_for_shell_theme(theme_id: object) -> str:
    resolved_shell_theme_id = resolve_theme_id(theme_id)
    return SHELL_THEME_TO_GRAPH_THEME.get(resolved_shell_theme_id, DEFAULT_GRAPH_THEME_ID)


def _graph_theme_mapping(payload: Any) -> Mapping[str, Any]:
    if isinstance(payload, GraphThemeDefinition):
        return payload.as_dict()
    if isinstance(payload, Mapping):
        return payload
    return {}


def _fallback_graph_theme(theme_id: object, fallback_theme_id: object) -> GraphThemeDefinition:
    normalized_theme_id = str(theme_id).strip()
    if normalized_theme_id in GRAPH_THEME_REGISTRY:
        return GRAPH_THEME_REGISTRY[normalized_theme_id]
    normalized_fallback_id = str(fallback_theme_id).strip()
    return GRAPH_THEME_REGISTRY.get(normalized_fallback_id, GRAPH_THEME_REGISTRY[DEFAULT_GRAPH_THEME_ID])


def _normalize_graph_theme_identity(value: object, *, default: object) -> str:
    normalized = str(value).strip()
    if normalized in GRAPH_THEME_REGISTRY:
        return normalized
    custom_theme_id = _normalized_custom_graph_theme_id(normalized)
    if custom_theme_id is not None:
        return custom_theme_id

    normalized_default = str(default).strip()
    if normalized_default in GRAPH_THEME_REGISTRY:
        return normalized_default
    custom_default = _normalized_custom_graph_theme_id(normalized_default)
    if custom_default is not None:
        return custom_default
    return DEFAULT_GRAPH_THEME_ID


def _normalized_custom_graph_theme_id(value: object) -> str | None:
    normalized = str(value).strip().lower()
    if is_custom_graph_theme_id(normalized):
        return normalized
    return None


def _normalize_theme_label(value: object, *, default: object) -> str:
    if value is not None:
        normalized = str(value).strip()
        if normalized:
            return normalized
    fallback = str(default).strip()
    return fallback or DEFAULT_CUSTOM_GRAPH_THEME_LABEL


def _normalize_tokens(payload: Any, fallback: Any) -> Any:
    source = payload if isinstance(payload, Mapping) else {}
    values = {}
    for token_field in fields(type(fallback)):
        fallback_value = getattr(fallback, token_field.name)
        if isinstance(fallback_value, bool):
            values[token_field.name] = _normalize_bool_value(source.get(token_field.name), fallback_value)
        elif token_field.name.endswith("_gradient_direction"):
            values[token_field.name] = _normalize_gradient_direction(source.get(token_field.name), fallback_value)
        else:
            values[token_field.name] = _normalize_color_value(source.get(token_field.name), fallback_value)
    return type(fallback)(**values)


def _normalize_color_value(value: object, default: str) -> str:
    if value is None:
        return default
    normalized = str(value).strip()
    return normalized or default


def _normalize_bool_value(value: object, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "on"}:
            return True
        if normalized in {"false", "0", "no", "off"}:
            return False
    if isinstance(value, (int, float)) and value in (0, 1):
        return bool(value)
    return default


def _normalize_gradient_direction(value: object, default: str) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in GRAPH_NODE_GRADIENT_DIRECTIONS:
        return normalized
    return default


def _generate_custom_graph_theme_id(reserved_theme_ids: Collection[str] | Mapping[str, object]) -> str:
    if isinstance(reserved_theme_ids, Mapping):
        reserved = {str(theme_id).strip() for theme_id in reserved_theme_ids}
    else:
        reserved = {str(theme_id).strip() for theme_id in reserved_theme_ids}
    while True:
        candidate = f"{CUSTOM_GRAPH_THEME_ID_PREFIX}{secrets.token_hex(4)}"
        if candidate not in GRAPH_THEME_REGISTRY and candidate not in reserved:
            return candidate


def _clone_graph_theme(
    theme: GraphThemeDefinition,
    *,
    theme_id: str | None = None,
    label: str | None = None,
) -> GraphThemeDefinition:
    return GraphThemeDefinition(
        theme_id=theme_id or theme.theme_id,
        label=label or theme.label,
        node_tokens=theme.node_tokens,
        edge_tokens=theme.edge_tokens,
        port_kind_tokens=theme.port_kind_tokens,
        port_state_tokens=theme.port_state_tokens,
    )


__all__ = [
    "CUSTOM_GRAPH_THEME_ID_PREFIX",
    "DEFAULT_GRAPH_THEME_ID",
    "DEFAULT_CUSTOM_GRAPH_THEME_LABEL",
    "GRAPH_THEME_REGISTRY",
    "SHELL_THEME_TO_GRAPH_THEME",
    "GraphThemeDefinition",
    "create_blank_custom_graph_theme",
    "default_graph_theme_id_for_shell_theme",
    "duplicate_graph_theme_as_custom",
    "graph_theme_registry",
    "graph_theme_choices",
    "is_custom_graph_theme_id",
    "is_known_graph_theme_id",
    "normalize_custom_graph_theme_definition",
    "normalize_custom_graph_themes",
    "normalize_graph_theme_definition",
    "resolve_graph_theme",
    "resolve_graph_theme_id",
    "serialize_custom_graph_themes",
]

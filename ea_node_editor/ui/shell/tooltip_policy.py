from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any


TOOLTIP_CATEGORY_GENERAL = "general"
TOOLTIP_CATEGORY_TUTORIAL = "tutorial"
TOOLTIP_CATEGORY_ADVANCED = "advanced"
TOOLTIP_CATEGORY_WARNING = "warning"
TOOLTIP_CATEGORY_INACTIVE = "inactive"
TOOLTIP_CATEGORY_CRITICAL = "critical"


@dataclass(frozen=True)
class TooltipCategoryPolicy:
    name: str
    default_enabled: bool
    configurable: bool


_TOOLTIP_CATEGORY_REGISTRY: dict[str, TooltipCategoryPolicy] = {
    TOOLTIP_CATEGORY_GENERAL: TooltipCategoryPolicy(
        name=TOOLTIP_CATEGORY_GENERAL,
        default_enabled=True,
        configurable=True,
    ),
    TOOLTIP_CATEGORY_TUTORIAL: TooltipCategoryPolicy(
        name=TOOLTIP_CATEGORY_TUTORIAL,
        default_enabled=True,
        configurable=True,
    ),
    TOOLTIP_CATEGORY_ADVANCED: TooltipCategoryPolicy(
        name=TOOLTIP_CATEGORY_ADVANCED,
        default_enabled=False,
        configurable=True,
    ),
    TOOLTIP_CATEGORY_WARNING: TooltipCategoryPolicy(
        name=TOOLTIP_CATEGORY_WARNING,
        default_enabled=True,
        configurable=True,
    ),
    TOOLTIP_CATEGORY_INACTIVE: TooltipCategoryPolicy(
        name=TOOLTIP_CATEGORY_INACTIVE,
        default_enabled=True,
        configurable=True,
    ),
    TOOLTIP_CATEGORY_CRITICAL: TooltipCategoryPolicy(
        name=TOOLTIP_CATEGORY_CRITICAL,
        default_enabled=True,
        configurable=False,
    ),
}

TOOLTIP_CATEGORY_NAMES = tuple(_TOOLTIP_CATEGORY_REGISTRY)
TOOLTIP_CONFIGURABLE_CATEGORY_NAMES = tuple(
    category
    for category, policy in _TOOLTIP_CATEGORY_REGISTRY.items()
    if policy.configurable
)


def default_tooltip_category_preferences() -> dict[str, bool]:
    return {
        category: _TOOLTIP_CATEGORY_REGISTRY[category].default_enabled
        for category in TOOLTIP_CONFIGURABLE_CATEGORY_NAMES
    }


def tooltip_category_registry() -> dict[str, TooltipCategoryPolicy]:
    return dict(_TOOLTIP_CATEGORY_REGISTRY)


def normalize_tooltip_category_name(category: Any) -> str:
    if category is None:
        return ""
    return str(category).strip().lower()


def tooltip_category_policy(category: Any) -> TooltipCategoryPolicy | None:
    return _TOOLTIP_CATEGORY_REGISTRY.get(normalize_tooltip_category_name(category))


def is_registered_tooltip_category(category: Any) -> bool:
    return tooltip_category_policy(category) is not None


def is_configurable_tooltip_category(category: Any) -> bool:
    policy = tooltip_category_policy(category)
    return bool(policy and policy.configurable)


def normalize_tooltip_category_preferences(payload: Any) -> dict[str, bool]:
    normalized = default_tooltip_category_preferences()
    if not isinstance(payload, Mapping):
        return normalized

    for raw_category, raw_enabled in payload.items():
        category = normalize_tooltip_category_name(raw_category)
        if not is_configurable_tooltip_category(category):
            continue
        policy = _TOOLTIP_CATEGORY_REGISTRY[category]
        normalized[category] = raw_enabled if isinstance(raw_enabled, bool) else policy.default_enabled
    return normalized


def tooltip_category_user_enabled(
    category: Any,
    *,
    tooltip_categories: Any = None,
) -> bool:
    policy = tooltip_category_policy(category)
    if policy is None:
        return False
    if not policy.configurable:
        return policy.default_enabled
    normalized = normalize_tooltip_category_preferences(tooltip_categories)
    return normalized.get(policy.name, policy.default_enabled)


def tooltip_category_effectively_visible(
    category: Any,
    *,
    tooltip_categories: Any = None,
) -> bool:
    policy = tooltip_category_policy(category)
    if policy is None:
        return False
    if not tooltip_category_user_enabled(policy.name, tooltip_categories=tooltip_categories):
        return False
    return True


__all__ = [
    "TOOLTIP_CATEGORY_ADVANCED",
    "TOOLTIP_CATEGORY_CRITICAL",
    "TOOLTIP_CATEGORY_GENERAL",
    "TOOLTIP_CATEGORY_INACTIVE",
    "TOOLTIP_CATEGORY_NAMES",
    "TOOLTIP_CATEGORY_TUTORIAL",
    "TOOLTIP_CATEGORY_WARNING",
    "TOOLTIP_CONFIGURABLE_CATEGORY_NAMES",
    "TooltipCategoryPolicy",
    "default_tooltip_category_preferences",
    "is_configurable_tooltip_category",
    "is_registered_tooltip_category",
    "normalize_tooltip_category_name",
    "normalize_tooltip_category_preferences",
    "tooltip_category_effectively_visible",
    "tooltip_category_policy",
    "tooltip_category_registry",
    "tooltip_category_user_enabled",
]

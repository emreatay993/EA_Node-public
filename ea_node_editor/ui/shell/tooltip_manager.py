from __future__ import annotations

from collections.abc import Mapping

from ea_node_editor.ui.shell.tooltip_policy import (
    TOOLTIP_CATEGORY_GENERAL,
    TOOLTIP_CATEGORY_INACTIVE,
    TOOLTIP_CATEGORY_WARNING,
    is_configurable_tooltip_category,
    normalize_tooltip_category_name,
    normalize_tooltip_category_preferences,
    tooltip_category_effectively_visible,
)


def _has_tooltip_text(text: object) -> bool:
    return bool(str(text or "").strip())


class TooltipManager:
    def __init__(
        self,
        *,
        tooltip_categories: Mapping[object, object] | None = None,
    ) -> None:
        self._tooltip_categories = normalize_tooltip_category_preferences(tooltip_categories)

    @property
    def tooltip_categories(self) -> dict[str, bool]:
        return dict(self._tooltip_categories)

    def set_tooltip_categories(self, categories: Mapping[object, object] | None) -> bool:
        normalized = normalize_tooltip_category_preferences(categories)
        changed = normalized != self._tooltip_categories
        self._tooltip_categories = normalized
        return changed

    def set_tooltip_category_enabled(self, category: object, enabled: bool) -> bool:
        normalized_category = normalize_tooltip_category_name(category)
        if not is_configurable_tooltip_category(normalized_category):
            return False
        normalized_enabled = bool(enabled)
        changed = self._tooltip_categories.get(normalized_category) != normalized_enabled
        self._tooltip_categories[normalized_category] = normalized_enabled
        return changed

    def category_tooltips_enabled(self, category: object) -> bool:
        return tooltip_category_effectively_visible(
            category,
            tooltip_categories=self._tooltip_categories,
        )

    def should_show_category_tooltip(self, category: object, text: object) -> bool:
        return self.category_tooltips_enabled(category) and _has_tooltip_text(text)

    def should_show_tooltip(self, text: object, *, category: object = TOOLTIP_CATEGORY_GENERAL) -> bool:
        return self.should_show_category_tooltip(category, text)

    def should_show_info_tooltip(self, text: object) -> bool:
        return self.should_show_category_tooltip(TOOLTIP_CATEGORY_GENERAL, text)

    def should_show_warning_tooltip(self, text: object) -> bool:
        return self.should_show_category_tooltip(TOOLTIP_CATEGORY_WARNING, text)

    def should_show_inactive_tooltip(self, text: object) -> bool:
        return self.should_show_category_tooltip(TOOLTIP_CATEGORY_INACTIVE, text)


__all__ = ["TooltipManager"]

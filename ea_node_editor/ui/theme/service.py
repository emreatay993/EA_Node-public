from __future__ import annotations

from ea_node_editor.ui.theme.registry import DEFAULT_THEME_ID, ThemeDefinition, resolve_theme


class ShellThemeService:
    def __init__(self, *, theme_id: object = DEFAULT_THEME_ID) -> None:
        self._theme = resolve_theme(theme_id)
        self._palette_cache: dict[str, str] | None = None

    @property
    def theme(self) -> ThemeDefinition:
        return self._theme

    @property
    def theme_id(self) -> str:
        return self._theme.theme_id

    @property
    def label(self) -> str:
        return self._theme.label

    def palette(self) -> dict[str, str]:
        if self._palette_cache is None:
            self._palette_cache = self._theme.tokens.as_dict()
        return dict(self._palette_cache)

    def token(self, name: object) -> str:
        if self._palette_cache is None:
            self._palette_cache = self._theme.tokens.as_dict()
        return str(self._palette_cache.get(str(name).strip(), ""))

    def apply_theme(self, theme_id: object) -> bool:
        resolved = resolve_theme(theme_id)
        if resolved == self._theme:
            return False
        self._theme = resolved
        self._palette_cache = None
        return True


__all__ = ["ShellThemeService"]

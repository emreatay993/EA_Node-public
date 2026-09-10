# Purpose: Compose built-in, trusted add-on, and public plugin registry contributions.
# Map: subsystems/nodes_registry_builtins.md
# Tests: tests/test_plugin_loader.py, tests/test_corex_contract_catalog.py

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Any

from ea_node_editor.nodes.registry import NodeRegistry
from ea_node_editor.settings import plugin_generations_dir, plugins_dir


def build_builtin_registry(*, generation_root: Path | None = None) -> NodeRegistry:
    from ea_node_editor.nodes.builtin_catalog import register_builtin_catalog

    registry = NodeRegistry()
    register_builtin_catalog(
        registry,
        generation_root=generation_root or plugin_generations_dir(),
    )
    registry.freeze()
    return registry


def _build_trusted_registry(
    *,
    app_preferences_store: Any = None,
    preferences_document: Any = None,
    addon_runtime_config: Iterable[tuple[str, bool]] | None = None,
    generation_root: Path | None = None,
) -> NodeRegistry:
    from ea_node_editor.addons.catalog import (
        addon_registration_is_live_enabled,
        registered_addon_registrations,
    )
    from ea_node_editor.addons.registry_contributions import (
        register_live_addon_contributions,
    )

    resolved_generation_root = generation_root or plugin_generations_dir()
    registry = build_builtin_registry(generation_root=resolved_generation_root)
    registrations = registered_addon_registrations()
    if addon_runtime_config is None:
        from ea_node_editor.app_preferences import (
            default_app_preferences_document,
            normalize_app_preferences_document,
        )

        source_preferences = (
            preferences_document
            if preferences_document is not None
            else (
                app_preferences_store.load_document()
                if app_preferences_store is not None
                else default_app_preferences_document()
            )
        )
        runtime_preferences = normalize_app_preferences_document(source_preferences)
        accepted_config = tuple(
            sorted(
                (
                    registration.manifest.addon_id,
                    addon_registration_is_live_enabled(
                        registration,
                        preferences_document=runtime_preferences,
                    ),
                )
                for registration in registrations
            )
        )
        runtime_store = app_preferences_store
    else:
        from ea_node_editor.app_preferences import default_app_preferences_document

        requested_config = dict(addon_runtime_config)
        known_ids = {registration.manifest.addon_id for registration in registrations}
        unknown_ids = set(requested_config) - known_ids
        if unknown_ids:
            raise ValueError("add-on runtime configuration contains unknown ids")
        accepted_config = tuple(
            sorted(
                (
                    registration.manifest.addon_id,
                    True
                    if registration.manifest.apply_policy != "hot_apply"
                    else bool(
                        requested_config.get(registration.manifest.addon_id, False)
                    ),
                )
                for registration in registrations
                if registration.manifest.addon_id in requested_config
                or registration.manifest.apply_policy != "hot_apply"
            )
        )
        accepted_by_id = dict(accepted_config)
        runtime_preferences = default_app_preferences_document()
        runtime_preferences["addons"]["states"] = {
            registration.manifest.addon_id: {
                "enabled": accepted_by_id.get(
                    registration.manifest.addon_id,
                    False,
                )
            }
            for registration in registrations
        }
        runtime_store = None
    registry.set_addon_runtime_config(accepted_config)
    register_live_addon_contributions(
        registry,
        preferences_document=runtime_preferences,
        store=runtime_store,
        generation_root=resolved_generation_root,
    )
    return registry


def build_default_registry(
    extra_plugin_dirs: list[Path] | None = None,
    *,
    app_preferences_store: Any = None,
    preferences_document: Any = None,
    include_public_plugins: bool = True,
    addon_runtime_config: Iterable[tuple[str, bool]] | None = None,
    generation_root: Path | None = None,
) -> NodeRegistry:
    registry = _build_trusted_registry(
        app_preferences_store=app_preferences_store,
        preferences_document=preferences_document,
        addon_runtime_config=addon_runtime_config,
        generation_root=generation_root,
    )
    if include_public_plugins:
        from ea_node_editor.nodes.plugin_loader import (
            discover_configured_static_plugins,
        )

        discover_configured_static_plugins(
            registry,
            extra_dirs=extra_plugin_dirs,
            generation_root=generation_root,
        )
    registry.freeze()
    return registry


def build_plugin_candidate_registry(
    extra_plugin_dirs: list[Path] | None = None,
    *,
    generation_root: Path,
    staged_package_root: Path | None = None,
    app_preferences_store: Any = None,
    preferences_document: Any = None,
) -> NodeRegistry:
    """Build a fresh fail-closed registry from static public-plugin sources."""

    registry = _build_trusted_registry(
        app_preferences_store=app_preferences_store,
        preferences_document=preferences_document,
        generation_root=Path(generation_root),
    )
    from ea_node_editor.nodes.plugin_loader import discover_static_plugin_candidate

    discover_static_plugin_candidate(
        registry,
        roots=(plugins_dir(), *(extra_plugin_dirs or ())),
        generation_root=Path(generation_root),
        staged_package_root=staged_package_root,
    )
    registry.freeze()
    return registry


__all__ = [
    "build_builtin_registry",
    "build_default_registry",
    "build_plugin_candidate_registry",
]

from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from ea_node_editor.graph.model import GraphModel
from ea_node_editor.nodes.bootstrap import build_default_registry
from ea_node_editor.app_preferences import (
    effective_graph_node_icon_pixel_size,
    normalize_plot_default_backend_per_type,
    resolve_startup_theme_id,
)
from ea_node_editor.settings import (
    APP_PREFERENCES_KIND,
    APP_PREFERENCES_VERSION,
    DEFAULT_GRAPHICS_SETTINGS,
)
from ea_node_editor.ui.shell.controllers.app_preferences_controller import (
    AppPreferencesController,
    AppPreferencesStore,
)
from ea_node_editor.ui.shell.host_presenter import ShellHostPresenter
from ea_node_editor.ui.shell.presenters import workspace_presenter as workspace_presenter_module
from ea_node_editor.ui.shell.presenters.state import build_default_shell_workspace_ui_state
from ea_node_editor.ui.shell.presenters.workspace_presenter import ShellWorkspacePresenter
from ea_node_editor.ui.shell.tooltip_manager import TooltipManager
from ea_node_editor.ui.shell.tooltip_policy import (
    TOOLTIP_CATEGORY_ADVANCED,
    TOOLTIP_CATEGORY_CRITICAL,
    TOOLTIP_CATEGORY_GENERAL,
    TOOLTIP_CATEGORY_INACTIVE,
    TOOLTIP_CATEGORY_NAMES,
    TOOLTIP_CATEGORY_TUTORIAL,
    TOOLTIP_CATEGORY_WARNING,
    default_tooltip_category_preferences,
    normalize_tooltip_category_preferences,
)
from ea_node_editor.ui.shell.window_state import context_properties as shell_context_properties
from ea_node_editor.ui.shell.window_state import run_and_style_state as shell_run_and_style_state
from ea_node_editor.ui_qml.graph_scene_bridge import GraphSceneBridge
from ea_node_editor.ui_qml.graph_canvas_state import GraphCanvasStateBridge
from ea_node_editor.ui_qml.graph_canvas_command import GraphCanvasCommandBridge
from ea_node_editor.ui_qml.graph_theme_bridge import GraphThemeBridge


class _RecordingHost:
    def __init__(self) -> None:
        self.applied_graphics: list[dict[str, object]] = []

    def apply_graphics_preferences(self, graphics: dict[str, object]) -> None:
        self.applied_graphics.append(graphics)


class _Signal:
    def __init__(self) -> None:
        self._slots: list[object] = []

    def connect(self, slot) -> None:  # noqa: ANN001
        self._slots.append(slot)

    def emit(self) -> None:
        for slot in tuple(self._slots):
            slot()


class _SearchScopeController:
    def __init__(self, state: SimpleNamespace, host: object) -> None:
        self._state = state
        self._host = host

    def set_snap_to_grid_enabled(self, enabled: bool, *, persist: bool = True) -> None:  # noqa: ARG002
        normalized = bool(enabled)
        if self._state.snap_to_grid_enabled == normalized:
            return
        self._state.snap_to_grid_enabled = normalized
        self._host.snap_to_grid_changed.emit()

    def set_graphics_minimap_expanded(
        self,
        expanded: bool,
        *,
        persist: bool = True,  # noqa: ARG002
    ) -> None:
        normalized = bool(expanded)
        if self._state.graphics_minimap_expanded == normalized:
            return
        self._state.graphics_minimap_expanded = normalized
        self._host.graphics_preferences_changed.emit()


class _ShellHostPresenter:
    def __init__(self, host: object | None = None) -> None:
        self._host = host
        self.active_theme_id = str(DEFAULT_GRAPHICS_SETTINGS["theme"]["theme_id"])
        self.applied_graphics: list[dict[str, object]] = []

    def apply_theme(self, theme_id: object) -> str:
        normalized = str(theme_id or "").strip()
        self.active_theme_id = normalized or str(DEFAULT_GRAPHICS_SETTINGS["theme"]["theme_id"])
        return self.active_theme_id

    def apply_graphics_preferences(self, graphics: dict[str, object]) -> dict[str, object]:
        self.applied_graphics.append(graphics)
        host = self._host
        if host is None:
            return graphics
        resolved = host.shell_workspace_presenter.apply_graphics_preferences(graphics)
        shell = resolved.get("shell", {}) if isinstance(resolved, dict) else {}
        categories = normalize_tooltip_category_preferences(shell.get("tooltip_categories"))
        host._sync_general_help_tooltips_action(categories[TOOLTIP_CATEGORY_GENERAL])
        return resolved


class _GraphThemeBridge:
    def __init__(self) -> None:
        self.theme_id = str(DEFAULT_GRAPHICS_SETTINGS["graph_theme"]["selected_theme_id"])
        self.last_settings: dict[str, object] | None = None

    def apply_settings(self, *, shell_theme_id: str, graph_theme_settings: dict[str, object]) -> None:
        self.last_settings = {
            "shell_theme_id": str(shell_theme_id),
            "graph_theme_settings": copy.deepcopy(graph_theme_settings),
        }
        self.theme_id = str(
            graph_theme_settings.get(
                "selected_theme_id",
                DEFAULT_GRAPHICS_SETTINGS["graph_theme"]["selected_theme_id"],
            )
        )


class _RuntimeTooltipHost:
    def __init__(self, controller: AppPreferencesController | None = None) -> None:
        self.project_meta_changed = _Signal()
        self.workspace_state_changed = _Signal()
        self.graphics_preferences_changed = _Signal()
        self.snap_to_grid_changed = _Signal()
        self.run_controls_changed = _Signal()
        self.project_path = ""
        self.workspace_ui_state = build_default_shell_workspace_ui_state(copy.deepcopy(DEFAULT_GRAPHICS_SETTINGS))
        self.search_scope_state = SimpleNamespace(
            graphics_minimap_expanded=bool(DEFAULT_GRAPHICS_SETTINGS["canvas"]["minimap_expanded"]),
            snap_to_grid_enabled=bool(DEFAULT_GRAPHICS_SETTINGS["interaction"]["snap_to_grid"]),
        )
        self.search_scope_controller = _SearchScopeController(
            self.search_scope_state,
            self,
        )
        self.shell_host_presenter = _ShellHostPresenter(self)
        self.shell_inspector_presenter = SimpleNamespace(
            set_property_pane_variant=lambda variant: None,
        )
        self.graph_theme_bridge = _GraphThemeBridge()
        self.workspace_manager = SimpleNamespace()
        self.model = SimpleNamespace()
        self.scene = SimpleNamespace()
        self.run_state = SimpleNamespace()
        self.run_controller = SimpleNamespace()
        self.project_session_controller = SimpleNamespace()
        self.workspace_navigation_controller = SimpleNamespace()
        self._SNAP_GRID_SIZE = 20.0
        self.tooltip_manager = TooltipManager(
            tooltip_categories=self.workspace_ui_state.graphics_tooltip_categories,
        )
        self._synced_show_port_labels: list[bool] = []
        self._synced_general_help_tooltips: list[bool] = []
        self._scene_refresh_count = 0
        self.app_preferences_controller = controller
        self.shell_workspace_presenter = ShellWorkspacePresenter(self, ui_state=self.workspace_ui_state)

    def _sync_graphics_show_port_labels_action(self, show_port_labels: bool) -> None:
        self._synced_show_port_labels.append(bool(show_port_labels))

    def _sync_general_help_tooltips_action(self, enabled: bool) -> None:
        self._synced_general_help_tooltips.append(bool(enabled))

    def _refresh_active_workspace_scene_payload(self) -> None:
        self._scene_refresh_count += 1

    def apply_graphics_preferences(self, graphics: dict[str, object]) -> dict[str, object]:
        return shell_run_and_style_state.ShellWindowRunAndStyleStateMixin.apply_graphics_preferences(self, graphics)

    def set_graphics_selection_toolbar_mode(self, mode: str) -> None:
        assert self.app_preferences_controller is not None
        self.app_preferences_controller.set_graphics_selection_toolbar_mode(mode, host=self)

    def set_graphics_selection_toolbar_minimal_menu_trigger(self, trigger: str) -> None:
        assert self.app_preferences_controller is not None
        self.app_preferences_controller.set_graphics_selection_toolbar_minimal_menu_trigger(
            trigger,
            host=self,
        )


class GraphicsSettingsPreferencesTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temp_dir = tempfile.TemporaryDirectory()
        self._preferences_path = Path(self._temp_dir.name) / "app_preferences.json"
        self._store = AppPreferencesStore(path_provider=lambda: self._preferences_path)
        self._controller = AppPreferencesController(store=self._store)

    def tearDown(self) -> None:
        self._temp_dir.cleanup()

    def test_graph_typography_bridge_workspace_presenter_snapshots_graph_label_pixel_size(self) -> None:
        host = _RuntimeTooltipHost()
        presenter = host.shell_workspace_presenter
        seen = {"graphics_preferences_changed": 0}
        presenter.graphics_preferences_changed.connect(
            lambda: seen.__setitem__(
                "graphics_preferences_changed",
                seen["graphics_preferences_changed"] + 1,
            )
        )

        resolved = presenter.apply_graphics_preferences(
            {"typography": {"graph_label_pixel_size": 17}},
        )

        self.assertEqual(
            resolved["typography"]["graph_label_pixel_size"],
            17,
        )
        self.assertEqual(host.workspace_ui_state.graph_label_pixel_size, 17)
        self.assertEqual(presenter.graphics_graph_label_pixel_size, 17)
        self.assertEqual(seen["graphics_preferences_changed"], 1)

    def test_tooltip_category_bridge_workspace_presenter_projects_effective_visibility(self) -> None:
        host = _RuntimeTooltipHost()
        presenter = host.shell_workspace_presenter
        seen = {"graphics_preferences_changed": 0}
        presenter.graphics_preferences_changed.connect(
            lambda: seen.__setitem__(
                "graphics_preferences_changed",
                seen["graphics_preferences_changed"] + 1,
            )
        )

        resolved = presenter.apply_graphics_preferences(
            {
                "shell": {
                    "tooltip_categories": {
                        "general": False,
                        "advanced": True,
                        "warning": False,
                        "critical": False,
                        "unknown": True,
                    },
                }
            },
        )

        self.assertEqual(
            resolved["shell"]["tooltip_categories"],
            {
                "general": False,
                "tutorial": True,
                "advanced": True,
                "warning": False,
                "inactive": True,
            },
        )
        self.assertFalse(presenter.graphics_show_tooltips)
        self.assertTrue(presenter.graphics_tooltip_categories[TOOLTIP_CATEGORY_ADVANCED])
        self.assertTrue(presenter.tooltip_category_enabled(TOOLTIP_CATEGORY_ADVANCED))
        self.assertFalse(presenter.tooltip_category_enabled(TOOLTIP_CATEGORY_WARNING))
        self.assertTrue(presenter.tooltip_category_enabled("critical"))
        self.assertEqual(
            presenter.graphics_tooltip_category_visibility,
            {
                "general": False,
                "tutorial": True,
                "advanced": True,
                "warning": False,
                "inactive": True,
                "critical": True,
            },
        )
        self.assertEqual(seen["graphics_preferences_changed"], 1)

    def test_shell_graphics_apply_writes_tooltip_manager_once(self) -> None:
        host = _RuntimeTooltipHost()
        shell_presenter = SimpleNamespace(
            _host=host,
            sync_graphics_show_port_labels_action=lambda _enabled: None,
            sync_general_help_tooltips_action=lambda _enabled: None,
        )
        categories = {
            **default_tooltip_category_preferences(),
            TOOLTIP_CATEGORY_GENERAL: False,
        }

        with mock.patch.object(
            host.tooltip_manager,
            "set_tooltip_categories",
            wraps=host.tooltip_manager.set_tooltip_categories,
        ) as set_categories:
            ShellHostPresenter.apply_graphics_preferences(
                shell_presenter,
                {"shell": {"tooltip_categories": categories}},
            )

        self.assertEqual(set_categories.call_count, 1)
        self.assertFalse(
            host.tooltip_manager.category_tooltips_enabled(
                TOOLTIP_CATEGORY_GENERAL
            )
        )

    def test_combined_theme_and_payload_preferences_rebuild_once_with_final_facts(
        self,
    ) -> None:
        host = _RuntimeTooltipHost()
        host.graph_theme_bridge = GraphThemeBridge()
        model = GraphModel()
        registry = build_default_registry()
        workspace_id = model.active_workspace.workspace_id
        scene = GraphSceneBridge()
        host.model = model
        host.scene = scene
        scene.set_workspace(model, registry, workspace_id)
        scene.bind_graphics_preferences_source(host.shell_workspace_presenter)
        scene.bind_graph_theme_bridge(host.graph_theme_bridge)
        plot_node_id = scene.add_node_from_type("plot.scatter", 40.0, 60.0)
        state_bridge = GraphCanvasStateBridge(
            graphics_source=host.shell_workspace_presenter,
            scene_bridge=scene,
        )
        notifications = {"host": 0, "workspace": 0, "state": 0}
        host.graphics_preferences_changed.connect(
            lambda: notifications.__setitem__("host", notifications["host"] + 1)
        )
        host.shell_workspace_presenter.graphics_preferences_changed.connect(
            lambda: notifications.__setitem__(
                "workspace", notifications["workspace"] + 1
            )
        )
        state_bridge.graphics_preferences_changed.connect(
            lambda: notifications.__setitem__("state", notifications["state"] + 1)
        )
        nodes_changed: list[str] = []
        edges_changed: list[str] = []
        scene.nodes_changed.connect(lambda: nodes_changed.append("nodes"))
        scene.edges_changed.connect(lambda: edges_changed.append("edges"))
        graphics = copy.deepcopy(DEFAULT_GRAPHICS_SETTINGS)
        graphics["canvas"]["show_port_labels"] = False
        graphics["typography"]["graph_label_pixel_size"] = 16
        graphics["typography"]["graph_node_icon_pixel_size_override"] = 12
        graphics["plot"]["lightweight_canvas"] = True
        graphics["graph_theme"] = {
            "follow_shell_theme": False,
            "selected_theme_id": "graph_stitch_light",
            "custom_themes": [],
        }

        host.shell_workspace_presenter.apply_graphics_preferences(graphics)

        self.assertEqual(
            notifications,
            {"host": 1, "workspace": 1, "state": 1},
        )
        self.assertEqual(nodes_changed, ["nodes"])
        self.assertEqual(edges_changed, ["edges"])
        self.assertEqual(
            scene._scene_payload_graphics_preferences,
            (False, 16, 12, True, False),
        )
        self.assertEqual(host.graph_theme_bridge.theme_id, "graph_stitch_light")
        plot_payload = next(
            payload
            for payload in scene.nodes_model
            if payload["node_id"] == plot_node_id
        )
        self.assertTrue(plot_payload["plot_surface"]["lightweight_canvas"])
        self.assertEqual(
            plot_payload["plot_surface"]["embedded_rendering_suppressed_by"],
            ["lightweight_canvas"],
        )

    def test_graphics_preference_fanout_matrix(self) -> None:
        count_names = (
            "host_graphics",
            "workspace_graphics",
            "state_graphics",
            "host_snap",
            "state_snap",
            "scene_nodes",
            "scene_edges",
        )

        def build_harness(case_name: str) -> SimpleNamespace:
            preferences_path = self._preferences_path.with_name(f"{case_name}.json")
            controller = AppPreferencesController(
                store=AppPreferencesStore(
                    path_provider=lambda path=preferences_path: path
                )
            )
            host = _RuntimeTooltipHost(controller)
            model = GraphModel()
            registry = build_default_registry()
            workspace_id = model.active_workspace.workspace_id
            scene = GraphSceneBridge()
            host.model = model
            host.scene = scene
            scene.bind_graphics_preferences_source(host.shell_workspace_presenter)
            scene.set_workspace(model, registry, workspace_id)
            scene.add_node_from_type("core.logger", 40.0, 60.0)
            canvas = GraphCanvasCommandBridge(
                search_scope_controller=host.search_scope_controller,
                app_preferences_source=host.app_preferences_controller,
                graphics_preferences_changed_signal=host.graphics_preferences_changed,
            )
            state = GraphCanvasStateBridge(
                session_state=host.search_scope_state,
                snap_to_grid_changed_signal=host.snap_to_grid_changed,
                snap_grid_size=20.0,
                app_preferences_source=host.app_preferences_controller,
                graphics_source=host.shell_workspace_presenter,
                scene_bridge=scene,
            )
            counts = dict.fromkeys(count_names, 0)
            for name, signal in (
                ("host_graphics", host.graphics_preferences_changed),
                (
                    "workspace_graphics",
                    host.shell_workspace_presenter.graphics_preferences_changed,
                ),
                ("state_graphics", state.graphics_preferences_changed),
                ("host_snap", host.snap_to_grid_changed),
                ("state_snap", state.snap_to_grid_changed),
                ("scene_nodes", scene.nodes_changed),
                ("scene_edges", scene.edges_changed),
            ):
                signal.connect(
                    lambda name=name: counts.__setitem__(name, counts[name] + 1)
                )
            return SimpleNamespace(
                controller=controller,
                host=host,
                presenter=host.shell_workspace_presenter,
                canvas=canvas,
                state=state,
                scene=scene,
                counts=counts,
            )

        cases = (
            (
                "identical_reapply",
                lambda harness: None,
                lambda harness: harness.presenter.apply_graphics_preferences(
                    copy.deepcopy(DEFAULT_GRAPHICS_SETTINGS)
                ),
                (0, 0, 0, 0, 0, 0, 0),
            ),
            (
                "ordinary_persisted",
                lambda harness: None,
                lambda harness: harness.presenter.apply_graphics_preferences(
                    {"canvas": {"show_grid": False}}
                ),
                (1, 1, 1, 0, 0, 0, 0),
            ),
            (
                "tooltip_category",
                lambda harness: None,
                lambda harness: harness.presenter.apply_graphics_preferences(
                    {"shell": {"tooltip_categories": {"general": False}}}
                ),
                (1, 1, 1, 0, 0, 0, 0),
            ),
            (
                "effective_icon_change",
                lambda harness: None,
                lambda harness: harness.presenter.apply_graphics_preferences(
                    {"typography": {"graph_node_icon_pixel_size_override": 12}}
                ),
                (1, 1, 1, 0, 0, 1, 1),
            ),
            (
                "unchanged_effective_icon",
                lambda harness: None,
                lambda harness: harness.presenter.apply_graphics_preferences(
                    {"typography": {"graph_node_icon_pixel_size_override": 10}}
                ),
                (1, 1, 1, 0, 0, 0, 0),
            ),
            (
                "lightweight_canvas",
                lambda harness: None,
                lambda harness: harness.presenter.apply_graphics_preferences(
                    {"plot": {"lightweight_canvas": True}}
                ),
                (1, 1, 1, 0, 0, 1, 1),
            ),
            (
                "backend_default_only",
                lambda harness: setattr(
                    harness.host.workspace_ui_state,
                    "plot_default_backend_per_type",
                    {"line": "different"},
                ),
                lambda harness: harness.presenter.apply_graphics_preferences(
                    copy.deepcopy(DEFAULT_GRAPHICS_SETTINGS)
                ),
                (1, 1, 1, 0, 0, 0, 0),
            ),
            (
                "media_default",
                lambda harness: None,
                lambda harness: harness.presenter.apply_graphics_preferences(
                    {"media_panel": {"show_title": False}}
                ),
                (1, 1, 1, 0, 0, 0, 0),
            ),
            (
                "minimap_expanded",
                lambda harness: None,
                lambda harness: harness.canvas.set_graphics_minimap_expanded(False),
                (1, 1, 1, 0, 0, 0, 0),
            ),
            (
                "selected_run_preview",
                lambda harness: None,
                lambda harness: harness.canvas.set_selected_run_preview_before_run(False),
                (1, 1, 1, 0, 0, 0, 0),
            ),
            (
                "snap_to_grid",
                lambda harness: None,
                lambda harness: harness.canvas.set_snap_to_grid_enabled(True),
                (0, 0, 0, 1, 1, 0, 0),
            ),
        )

        for case_name, prepare, mutate, expected in cases:
            with self.subTest(case=case_name):
                harness = build_harness(case_name)
                prepare(harness)
                mutate(harness)
                self.assertEqual(
                    tuple(harness.counts[name] for name in count_names),
                    expected,
                )

        class _RejectedGraphicsSettingsDialog:
            DialogCode = SimpleNamespace(Accepted=1)

            def __init__(self, **_kwargs) -> None:
                pass

            def exec(self) -> int:
                return 0

        harness = build_harness("graphics_dialog_cancel")
        harness.host.graphics_show_tooltips = (
            harness.presenter.graphics_show_tooltips
        )
        shell_presenter = SimpleNamespace(
            _host=harness.host,
            active_renderer_label=lambda: "Unavailable",
            edit_graph_theme_settings=lambda _settings: None,
        )
        with (
            mock.patch(
                "ea_node_editor.ui.dialogs.GraphicsSettingsDialog",
                _RejectedGraphicsSettingsDialog,
            ),
            mock.patch.object(
                harness.controller,
                "set_graphics_settings",
                wraps=harness.controller.set_graphics_settings,
            ) as set_graphics_settings,
        ):
            ShellHostPresenter.show_graphics_settings_dialog(shell_presenter)
        self.assertEqual(set_graphics_settings.call_count, 0)
        self.assertEqual(
            tuple(harness.counts[name] for name in count_names),
            (0, 0, 0, 0, 0, 0, 0),
        )

    def test_workspace_tooltip_projections_are_computed_once_per_preferences_revision(self) -> None:
        host = _RuntimeTooltipHost()
        presenter = host.shell_workspace_presenter
        original_policy = workspace_presenter_module.tooltip_category_effectively_visible

        with mock.patch.object(
            workspace_presenter_module,
            "tooltip_category_effectively_visible",
            wraps=original_policy,
        ) as project_visibility:
            categories = presenter.graphics_tooltip_categories
            categories["general"] = False
            self.assertTrue(presenter.graphics_tooltip_categories["general"])
            _ = presenter.graphics_tooltip_category_visibility
            _ = presenter.graphics_tooltip_category_visibility
            self.assertTrue(presenter.tooltip_category_enabled("general"))
            self.assertEqual(project_visibility.call_count, len(TOOLTIP_CATEGORY_NAMES))

            host.workspace_ui_state.graphics_tooltip_categories["general"] = False
            host.graphics_preferences_changed.emit()

            self.assertFalse(presenter.tooltip_category_enabled("general"))
            self.assertEqual(project_visibility.call_count, 2 * len(TOOLTIP_CATEGORY_NAMES))

    def test_graph_node_icon_size_bridge_workspace_presenter_projects_nullable_override_and_effective_size(self) -> None:
        host = _RuntimeTooltipHost()
        presenter = host.shell_workspace_presenter
        seen = {"graphics_preferences_changed": 0}
        presenter.graphics_preferences_changed.connect(
            lambda: seen.__setitem__(
                "graphics_preferences_changed",
                seen["graphics_preferences_changed"] + 1,
            )
        )

        resolved = presenter.apply_graphics_preferences(
            {
                "typography": {
                    "graph_label_pixel_size": 16,
                    "graph_node_icon_pixel_size_override": None,
                }
            },
        )

        self.assertEqual(resolved["typography"]["graph_label_pixel_size"], 16)
        self.assertIsNone(resolved["typography"]["graph_node_icon_pixel_size_override"])
        self.assertEqual(host.workspace_ui_state.node_title_icon_pixel_size, 16)
        self.assertEqual(presenter.graphics_node_title_icon_pixel_size, 16)
        self.assertEqual(seen["graphics_preferences_changed"], 1)

        resolved = presenter.apply_graphics_preferences(
            {
                "typography": {
                    "graph_label_pixel_size": 16,
                    "graph_node_icon_pixel_size_override": 3,
                }
            },
        )

        self.assertEqual(resolved["typography"]["graph_node_icon_pixel_size_override"], 8)
        self.assertEqual(host.workspace_ui_state.node_title_icon_pixel_size, 8)
        self.assertEqual(presenter.graphics_graph_node_icon_pixel_size_override, 8)
        self.assertEqual(presenter.graphics_node_title_icon_pixel_size, 8)
        self.assertEqual(seen["graphics_preferences_changed"], 2)

    def test_missing_file_loads_locked_defaults(self) -> None:
        document = self._controller.load()

        self.assertEqual(document["kind"], APP_PREFERENCES_KIND)
        self.assertEqual(document["version"], APP_PREFERENCES_VERSION)
        self.assertEqual(document["graphics"], DEFAULT_GRAPHICS_SETTINGS)
        self.assertFalse(self._preferences_path.exists())

    def test_unsupported_document_metadata_loads_locked_defaults(self) -> None:
        self._preferences_path.write_text(
            json.dumps(
                {
                    "kind": "unexpected",
                    "version": 99,
                    "graphics": {
                        "canvas": {"show_grid": False},
                        "theme": {"theme_id": "stitch_light"},
                    },
                }
            ),
            encoding="utf-8",
        )

        document = self._controller.load()

        self.assertEqual(document["kind"], APP_PREFERENCES_KIND)
        self.assertEqual(document["version"], APP_PREFERENCES_VERSION)
        self.assertEqual(document["graphics"], DEFAULT_GRAPHICS_SETTINGS)

    def test_load_normalizes_invalid_graphics_values(self) -> None:
        self._preferences_path.write_text(
            json.dumps(
                {
                    "kind": APP_PREFERENCES_KIND,
                    "version": APP_PREFERENCES_VERSION,
                    "graphics": {
                        "canvas": {
                            "background_variant": "neon",
                            "show_grid": "yes",
                            "grid_style": "dots",
                            "edge_crossing_style": "crossing-bridges",
                            "show_canvas_options_button": "no",
                            "show_minimap": False,
                            "show_port_labels": "no",
                            "notched_ports": "false",
                            "minimap_expanded": None,
                            "node_shadow": "no",
                            "shadow_strength": 101,
                            "shadow_softness": 25,
                            "shadow_offset": -1,
                            "floating_toolbar_style": "bubble_row",
                            "node_floating_toolbar_opens_on_hover": "false",
                            "selection_toolbar_mode": "toolbar_cloud",
                            "selection_toolbar_minimal_menu_trigger": "hover",
                        },
                        "interaction": {
                            "snap_to_grid": True,
                            "expand_collision_avoidance": {
                                "enabled": "yes",
                                "strategy": "farthest",
                                "scope": "selected_only",
                                "radius_mode": "global",
                                "local_radius_preset": "tiny",
                                "gap_preset": "huge",
                                "animate": "true",
                            },
                        },
                        "performance": {
                            "mode": "warp_speed",
                        },
                        "shell": {
                            "tab_strip_density": "dense",
                            "passive_node_library_display_mode": "tiles",
                        },
                        "theme": {
                            "theme_id": "invalid-theme",
                        },
                        "media_panel": {
                            "show_title": "no",
                            "show_frame": None,
                            "source_input_exposed": "no",
                        },
                        "graph_theme": {
                            "follow_shell_theme": False,
                            "selected_theme_id": "missing-theme",
                            "custom_themes": "bad",
                        },
                        "folder_explorer": {
                            "column_widths": {
                                "name": "260",
                                "modified": True,
                                "type": None,
                                "size": [88],
                            },
                        },
                    },
                }
            ),
            encoding="utf-8",
        )

        graphics = self._controller.load()["graphics"]

        self.assertEqual(graphics["canvas"]["show_grid"], True)
        self.assertEqual(
            graphics["canvas"]["background_variant"],
            DEFAULT_GRAPHICS_SETTINGS["canvas"]["background_variant"],
        )
        self.assertEqual(graphics["canvas"]["grid_style"], "lines")
        self.assertEqual(
            graphics["canvas"]["edge_crossing_style"],
            DEFAULT_GRAPHICS_SETTINGS["canvas"]["edge_crossing_style"],
        )
        self.assertTrue(graphics["canvas"]["show_canvas_options_button"])
        self.assertEqual(graphics["canvas"]["show_minimap"], False)
        self.assertEqual(graphics["canvas"]["show_port_labels"], True)
        self.assertEqual(graphics["canvas"]["notched_ports"], True)
        self.assertEqual(graphics["canvas"]["minimap_expanded"], True)
        self.assertEqual(graphics["canvas"]["node_shadow"], True)
        self.assertEqual(graphics["canvas"]["shadow_strength"], DEFAULT_GRAPHICS_SETTINGS["canvas"]["shadow_strength"])
        self.assertEqual(graphics["canvas"]["shadow_softness"], 25)
        self.assertEqual(graphics["canvas"]["shadow_offset"], DEFAULT_GRAPHICS_SETTINGS["canvas"]["shadow_offset"])
        self.assertEqual(
            graphics["canvas"]["floating_toolbar_style"],
            DEFAULT_GRAPHICS_SETTINGS["canvas"]["floating_toolbar_style"],
        )
        self.assertEqual(
            graphics["canvas"]["node_floating_toolbar_opens_on_hover"],
            DEFAULT_GRAPHICS_SETTINGS["canvas"]["node_floating_toolbar_opens_on_hover"],
        )
        self.assertEqual(
            graphics["canvas"]["selection_toolbar_mode"],
            DEFAULT_GRAPHICS_SETTINGS["canvas"]["selection_toolbar_mode"],
        )
        self.assertEqual(
            graphics["canvas"]["selection_toolbar_minimal_menu_trigger"],
            DEFAULT_GRAPHICS_SETTINGS["canvas"]["selection_toolbar_minimal_menu_trigger"],
        )
        self.assertEqual(graphics["interaction"]["snap_to_grid"], True)
        self.assertEqual(
            graphics["interaction"]["expand_collision_avoidance"],
            DEFAULT_GRAPHICS_SETTINGS["interaction"]["expand_collision_avoidance"],
        )
        self.assertNotIn("performance", graphics)
        self.assertEqual(graphics["shell"]["tab_strip_density"], DEFAULT_GRAPHICS_SETTINGS["shell"]["tab_strip_density"])
        self.assertEqual(
            graphics["shell"]["passive_node_library_display_mode"],
            DEFAULT_GRAPHICS_SETTINGS["shell"]["passive_node_library_display_mode"],
        )
        self.assertEqual(graphics["theme"]["theme_id"], DEFAULT_GRAPHICS_SETTINGS["theme"]["theme_id"])
        self.assertEqual(graphics["media_panel"], DEFAULT_GRAPHICS_SETTINGS["media_panel"])
        self.assertEqual(graphics["plot"], DEFAULT_GRAPHICS_SETTINGS["plot"])
        self.assertEqual(graphics["folder_explorer"]["column_widths"], {})
        self.assertFalse(graphics["graph_theme"]["follow_shell_theme"])
        self.assertEqual(
            graphics["graph_theme"]["selected_theme_id"],
            DEFAULT_GRAPHICS_SETTINGS["graph_theme"]["selected_theme_id"],
        )
        self.assertEqual(graphics["graph_theme"]["custom_themes"], [])

    def test_set_graphics_settings_persists_and_applies_values_to_host(self) -> None:
        host = _RecordingHost()

        graphics = self._controller.set_graphics_settings(
            {
                "canvas": {
                    "background_variant": " WHITE ",
                    "show_grid": False,
                    "grid_style": "POINTS",
                    "edge_crossing_style": " GAP_BREAK ",
                    "show_canvas_options_button": False,
                    "show_minimap": False,
                    "show_port_labels": False,
                    "notched_ports": False,
                    "node_elapsed_time_unit": " MS ",
                    "node_elapsed_time_visibility": " DURING_RUN ",
                    "node_comment_editor_default": " inspector ",
                    "minimap_expanded": False,
                    "node_shadow": False,
                    "shadow_strength": 15,
                    "shadow_softness": 25,
                    "shadow_offset": 3,
                    "floating_toolbar_style": " SEGMENTED_BAR ",
                    "node_floating_toolbar_opens_on_hover": True,
                    "selection_toolbar_mode": " SIDE_RAIL ",
                    "selection_toolbar_minimal_menu_trigger": " RIGHT_CLICK ",
                },
                "interaction": {
                    "snap_to_grid": True,
                    "expand_collision_avoidance": {
                        "enabled": False,
                        "strategy": " NEAREST ",
                        "scope": " ALL_MOVABLE ",
                        "radius_mode": " UNBOUNDED ",
                        "local_radius_preset": " LARGE ",
                        "gap_preset": " TIGHT ",
                        "animate": False,
                    },
                },
                "performance": {
                    "mode": "retired",
                },
                "shell": {
                    "tab_strip_density": "regular",
                    "passive_node_library_display_mode": " TEXT_ICON ",
                },
                "theme": {
                    "theme_id": "stitch_light",
                },
                "media_panel": {
                    "show_title": False,
                    "show_frame": False,
                    "autoplay_animations": False,
                    "source_input_exposed": False,
                },
                "graph_theme": {
                    "follow_shell_theme": False,
                    "selected_theme_id": "graph_stitch_light",
                    "custom_themes": [],
                },
            },
            host=host,
        )

        self.assertEqual(host.applied_graphics, [graphics])
        self.assertEqual(graphics["canvas"]["background_variant"], "white")
        self.assertEqual(graphics["canvas"]["grid_style"], "points")
        self.assertEqual(graphics["canvas"]["edge_crossing_style"], "gap_break")
        self.assertEqual(graphics["canvas"]["floating_toolbar_style"], "segmented_bar")
        self.assertTrue(graphics["canvas"]["node_floating_toolbar_opens_on_hover"])
        self.assertEqual(graphics["canvas"]["selection_toolbar_mode"], "side_rail")
        self.assertEqual(
            graphics["canvas"]["selection_toolbar_minimal_menu_trigger"],
            "right_click",
        )
        self.assertEqual(graphics["canvas"]["node_elapsed_time_unit"], "milliseconds")
        self.assertEqual(graphics["canvas"]["node_elapsed_time_visibility"], "during_run")
        self.assertEqual(graphics["canvas"]["node_comment_editor_default"], "inspector")
        self.assertFalse(graphics["canvas"]["show_canvas_options_button"])
        self.assertFalse(graphics["canvas"]["show_port_labels"])
        self.assertFalse(graphics["canvas"]["notched_ports"])
        self.assertEqual(
            graphics["media_panel"],
            {
                "show_title": False,
                "show_frame": False,
                "autoplay_animations": False,
                "source_input_exposed": False,
            },
        )
        self.assertNotIn("performance", graphics)
        self.assertEqual(graphics["shell"]["passive_node_library_display_mode"], "text_icon")
        self.assertEqual(graphics["plot"], DEFAULT_GRAPHICS_SETTINGS["plot"])
        self.assertEqual(
            graphics["interaction"]["expand_collision_avoidance"],
            {
                "enabled": False,
                "strategy": "nearest",
                "scope": "all_movable",
                "radius_mode": "unbounded",
                "local_radius_preset": "large",
                "gap_preset": "tight",
                "animate": False,
            },
        )
        persisted = json.loads(self._preferences_path.read_text(encoding="utf-8"))
        self.assertEqual(persisted["kind"], APP_PREFERENCES_KIND)
        self.assertEqual(persisted["version"], APP_PREFERENCES_VERSION)
        self.assertEqual(persisted["graphics"], graphics)
        reloaded = AppPreferencesController(store=self._store).load()
        self.assertEqual(reloaded, persisted)

    def test_media_panel_preferences_reach_workspace_presenter(self) -> None:
        host = _RuntimeTooltipHost(self._controller)

        self._controller.set_graphics_settings(
            {
                "media_panel": {
                    "show_title": False,
                    "show_frame": False,
                    "autoplay_animations": False,
                    "source_input_exposed": False,
                }
            },
            host=host,
        )

        self.assertEqual(
            host.shell_workspace_presenter.graphics_media_panel_defaults,
            {
                "show_title": False,
                "show_frame": False,
                "autoplay_animations": False,
                "source_input_exposed": False,
            },
        )
    def test_folder_explorer_column_widths_persist_through_workspace_presenter(self) -> None:
        host = _RuntimeTooltipHost(self._controller)

        host.shell_workspace_presenter.set_folder_explorer_column_widths(
            {"name": 260, "modified": 180, "type": "bad", "size": 1400}
        )

        expected = {"name": 260, "modified": 180, "size": 1200}
        self.assertEqual(host.workspace_ui_state.folder_explorer_column_widths, expected)
        self.assertEqual(host.shell_workspace_presenter.graphics_folder_explorer_column_widths, expected)
        self.assertEqual(
            shell_context_properties._qt_graphics_folder_explorer_column_widths(host),
            expected,
        )
        persisted = json.loads(self._preferences_path.read_text(encoding="utf-8"))
        self.assertEqual(persisted["graphics"]["folder_explorer"]["column_widths"], expected)

    def test_shell_panel_collapsed_persists_through_workspace_presenter(self) -> None:
        host = _RuntimeTooltipHost(self._controller)

        host.shell_workspace_presenter.set_shell_panel_collapsed("node_library", True)
        host.shell_workspace_presenter.set_shell_panel_collapsed("property_pane", True)
        host.shell_workspace_presenter.set_shell_panel_collapsed("unknown_panel", True)

        expected = {
            "node_library": True,
            "property_pane": True,
            "output_panel": False,
        }
        self.assertEqual(host.workspace_ui_state.shell_panel_collapsed, expected)
        self.assertEqual(host.shell_workspace_presenter.shell_panel_collapsed, expected)
        persisted = json.loads(self._preferences_path.read_text(encoding="utf-8"))
        self.assertEqual(persisted["graphics"]["shell"]["panel_collapsed"], expected)

    def test_recent_text_colors_persist_through_workspace_presenter(self) -> None:
        host = _RuntimeTooltipHost(self._controller)

        host.shell_workspace_presenter.record_recent_text_color("#112233")
        host.shell_workspace_presenter.record_recent_text_color("bad")
        host.shell_workspace_presenter.record_recent_text_color("#aabbcc")
        host.shell_workspace_presenter.record_recent_text_color("#112233")

        expected = ["#112233", "#AABBCC"]
        self.assertEqual(host.workspace_ui_state.recent_text_colors, expected)
        self.assertEqual(host.shell_workspace_presenter.graphics_recent_text_colors, expected)
        persisted = json.loads(self._preferences_path.read_text(encoding="utf-8"))
        self.assertEqual(persisted["graphics"]["typography"]["recent_text_colors"], expected)

    def test_selection_toolbar_preferences_persist_through_workspace_presenter(self) -> None:
        host = _RuntimeTooltipHost(self._controller)

        host.shell_workspace_presenter.set_graphics_selection_toolbar_mode(" SIDE_RAIL ")
        host.shell_workspace_presenter.set_graphics_selection_toolbar_minimal_menu_trigger(" RIGHT_CLICK ")

        self.assertEqual(host.workspace_ui_state.selection_toolbar_mode, "side_rail")
        self.assertEqual(
            host.workspace_ui_state.selection_toolbar_minimal_menu_trigger,
            "right_click",
        )
        self.assertEqual(host.shell_workspace_presenter.graphics_selection_toolbar_mode, "side_rail")
        self.assertEqual(
            host.shell_workspace_presenter.graphics_selection_toolbar_minimal_menu_trigger,
            "right_click",
        )
        self.assertEqual(
            shell_context_properties._qt_graphics_selection_toolbar_mode(host),
            "side_rail",
        )
        self.assertEqual(
            shell_context_properties._qt_graphics_selection_toolbar_minimal_menu_trigger(host),
            "right_click",
        )
        persisted = json.loads(self._preferences_path.read_text(encoding="utf-8"))
        self.assertEqual(persisted["graphics"]["canvas"]["selection_toolbar_mode"], "side_rail")
        self.assertEqual(
            persisted["graphics"]["canvas"]["selection_toolbar_minimal_menu_trigger"],
            "right_click",
        )

    def test_node_floating_toolbar_hover_preference_reaches_workspace_presenter(self) -> None:
        host = _RuntimeTooltipHost(self._controller)

        self._controller.set_graphics_settings(
            {"canvas": {"node_floating_toolbar_opens_on_hover": True}},
            host=host,
        )

        self.assertTrue(host.workspace_ui_state.node_floating_toolbar_opens_on_hover)
        self.assertTrue(
            host.shell_workspace_presenter.graphics_node_floating_toolbar_opens_on_hover
        )
        persisted = json.loads(self._preferences_path.read_text(encoding="utf-8"))
        self.assertTrue(persisted["graphics"]["canvas"]["node_floating_toolbar_opens_on_hover"])

    def test_notched_ports_preference_reaches_shell_and_graph_canvas_state(self) -> None:
        host = _RuntimeTooltipHost(self._controller)

        self.assertTrue(host.workspace_ui_state.notched_ports)
        self._controller.set_graphics_settings(
            {"canvas": {"notched_ports": False}},
            host=host,
        )

        self.assertFalse(host.workspace_ui_state.notched_ports)
        self.assertFalse(host.shell_workspace_presenter.graphics_notched_ports)
        self.assertFalse(shell_context_properties._qt_graphics_notched_ports(host))
        persisted = json.loads(self._preferences_path.read_text(encoding="utf-8"))
        self.assertFalse(persisted["graphics"]["canvas"]["notched_ports"])

    def test_keep_expanded_node_width_persists_and_updates_existing_scene(self) -> None:
        host = _RuntimeTooltipHost(self._controller)
        self.assertFalse(self._controller.load()["graphics"]["canvas"]["keep_expanded_node_width"])
        registry = build_default_registry()
        model = GraphModel()
        workspace = model.active_workspace
        node = model.add_node(workspace.workspace_id, "plot.signal", "Signal Plot", 40, 60)
        scene = GraphSceneBridge()
        scene.bind_graphics_preferences_source(host.shell_workspace_presenter)
        scene.set_workspace(model, registry, workspace.workspace_id)
        fitted = scene.nodes_model[0]
        notifications = []
        scene.nodes_changed.connect(lambda: notifications.append(True))

        self._controller.set_graphics_settings({"canvas": {"keep_expanded_node_width": True}}, host=host)

        self.assertTrue(host.workspace_ui_state.keep_expanded_node_width)
        self.assertTrue(host.shell_workspace_presenter.graphics_keep_expanded_node_width)
        self.assertTrue(scene.graphics_keep_expanded_node_width)
        self.assertEqual(notifications, [True])
        self.assertGreater(scene.nodes_model[0]["width"], fitted["width"])
        self.assertEqual(scene.nodes_model[0]["height"], fitted["height"])
        self.assertIsNone(node.custom_width)
        reloaded = AppPreferencesController(store=self._store).load()["graphics"]
        self.assertTrue(reloaded["canvas"]["keep_expanded_node_width"])

        self._controller.set_graphics_settings({"canvas": {"keep_expanded_node_width": False}}, host=host)
        self.assertEqual(scene.nodes_model[0]["width"], fitted["width"])

    def test_tooltip_preferences_missing_key_defaults_true(self) -> None:
        self._preferences_path.write_text(
            json.dumps(
                {
                    "kind": APP_PREFERENCES_KIND,
                    "version": APP_PREFERENCES_VERSION,
                    "graphics": {
                        "canvas": {
                            "show_grid": False,
                        },
                        "shell": {
                            "tab_strip_density": "regular",
                        },
                    },
                }
            ),
            encoding="utf-8",
        )

        graphics = self._controller.load()["graphics"]

        self.assertFalse(graphics["canvas"]["show_grid"])
        self.assertEqual(graphics["shell"]["tab_strip_density"], "regular")
        self.assertNotIn("show_tooltips", graphics["shell"])
        self.assertEqual(
            graphics["shell"]["tooltip_categories"],
            default_tooltip_category_preferences(),
        )

    def test_tooltip_preferences_missing_category_payload_defaults_true(self) -> None:
        self._preferences_path.write_text(
            json.dumps(
                {
                    "kind": APP_PREFERENCES_KIND,
                    "version": APP_PREFERENCES_VERSION,
                    "graphics": {
                        "shell": {
                            "tab_strip_density": "regular",
                        },
                    },
                }
            ),
            encoding="utf-8",
        )

        graphics = self._controller.load()["graphics"]

        self.assertEqual(graphics["shell"]["tab_strip_density"], "regular")
        self.assertNotIn("show_tooltips", graphics["shell"])
        self.assertEqual(
            graphics["shell"]["tooltip_categories"],
            default_tooltip_category_preferences(),
        )

    def test_tooltip_category_preferences_invalid_payload_preserves_unrelated_graphics(self) -> None:
        self._preferences_path.write_text(
            json.dumps(
                {
                    "kind": APP_PREFERENCES_KIND,
                    "version": APP_PREFERENCES_VERSION,
                    "graphics": {
                        "canvas": {
                            "show_grid": False,
                        },
                        "shell": {
                            "tooltip_categories": {
                                "general": "false",
                                "tutorial": None,
                                "advanced": True,
                                "warning": False,
                                "inactive": "yes",
                                "critical": False,
                                "unknown": True,
                            },
                        },
                    },
                }
            ),
            encoding="utf-8",
        )

        graphics = self._controller.load()["graphics"]

        self.assertFalse(graphics["canvas"]["show_grid"])
        self.assertNotIn("show_tooltips", graphics["shell"])
        self.assertEqual(
            graphics["shell"]["tooltip_categories"],
            {
                "general": True,
                "tutorial": True,
                "advanced": True,
                "warning": False,
                "inactive": True,
            },
        )

    def test_tooltip_category_preferences_persist_roundtrip_without_unknown_or_critical(self) -> None:
        graphics = self._controller.set_graphics_settings(
            {
                "shell": {
                    "tooltip_categories": {
                        "general": False,
                        "tutorial": False,
                        "advanced": True,
                        "warning": False,
                        "inactive": False,
                        "critical": False,
                        "experimental": True,
                    },
                },
            }
        )

        expected_categories = {
            "general": False,
            "tutorial": False,
            "advanced": True,
            "warning": False,
            "inactive": False,
        }
        persisted = json.loads(self._preferences_path.read_text(encoding="utf-8"))
        reloaded = AppPreferencesController(store=self._store).load()["graphics"]

        self.assertNotIn("show_tooltips", graphics["shell"])
        self.assertNotIn("show_tooltips", persisted["graphics"]["shell"])
        self.assertNotIn("show_tooltips", reloaded["shell"])
        self.assertEqual(graphics["shell"]["tooltip_categories"], expected_categories)
        self.assertEqual(persisted["graphics"]["shell"]["tooltip_categories"], expected_categories)
        self.assertEqual(reloaded["shell"]["tooltip_categories"], expected_categories)
        self.assertNotIn("critical", persisted["graphics"]["shell"]["tooltip_categories"])
        self.assertNotIn("experimental", persisted["graphics"]["shell"]["tooltip_categories"])

    def test_tooltip_category_controller_methods_update_store_and_preserve_unrelated_saves(self) -> None:
        graphics = self._controller.set_graphics_tooltip_category_enabled(
            TOOLTIP_CATEGORY_ADVANCED,
            True,
        )
        self.assertTrue(graphics["shell"]["tooltip_categories"]["advanced"])

        graphics = self._controller.set_graphics_tooltip_categories(
            {
                "general": False,
                "warning": False,
                "critical": False,
                "unknown": True,
            }
        )
        expected_categories = {
            "general": False,
            "tutorial": True,
            "advanced": False,
            "warning": False,
            "inactive": True,
        }
        self.assertEqual(graphics["shell"]["tooltip_categories"], expected_categories)

        graphics = self._controller.set_graphics_settings(
            {
                "canvas": {
                    "show_grid": False,
                }
            }
        )
        persisted = json.loads(self._preferences_path.read_text(encoding="utf-8"))
        self.assertFalse(graphics["canvas"]["show_grid"])
        self.assertEqual(graphics["shell"]["tooltip_categories"], expected_categories)
        self.assertEqual(persisted["graphics"]["shell"]["tooltip_categories"], expected_categories)

        unchanged = self._controller.set_graphics_tooltip_category_enabled(
            TOOLTIP_CATEGORY_CRITICAL,
            False,
        )
        self.assertEqual(unchanged["shell"]["tooltip_categories"], expected_categories)

    def test_tooltip_category_settings_dialog_payload_persists_and_updates_runtime_host(self) -> None:
        host = _RuntimeTooltipHost(self._controller)
        dialog_payload = copy.deepcopy(DEFAULT_GRAPHICS_SETTINGS)
        expected_categories = {
            "general": False,
            "tutorial": True,
            "advanced": True,
            "warning": False,
            "inactive": True,
        }
        dialog_payload["shell"]["tooltip_categories"] = copy.deepcopy(expected_categories)

        graphics = self._controller.set_graphics_settings(dialog_payload, host=host)
        persisted = json.loads(self._preferences_path.read_text(encoding="utf-8"))

        self.assertNotIn("show_tooltips", graphics["shell"])
        self.assertEqual(graphics["shell"]["tooltip_categories"], expected_categories)
        self.assertNotIn("show_tooltips", persisted["graphics"]["shell"])
        self.assertEqual(persisted["graphics"]["shell"]["tooltip_categories"], expected_categories)
        self.assertFalse(host.shell_workspace_presenter.graphics_show_tooltips)
        self.assertEqual(host.workspace_ui_state.graphics_tooltip_categories, expected_categories)
        self.assertTrue(host.tooltip_manager.tooltip_categories["advanced"])
        self.assertFalse(host.tooltip_manager.category_tooltips_enabled(TOOLTIP_CATEGORY_GENERAL))
        self.assertFalse(host.tooltip_manager.category_tooltips_enabled(TOOLTIP_CATEGORY_WARNING))
        self.assertTrue(host.tooltip_manager.category_tooltips_enabled(TOOLTIP_CATEGORY_INACTIVE))
        self.assertTrue(host.tooltip_manager.category_tooltips_enabled(TOOLTIP_CATEGORY_CRITICAL))
        self.assertEqual(host._synced_general_help_tooltips, [False])

    def test_tooltip_preferences_load_into_runtime_host_updates_shell_state(self) -> None:
        host = _RuntimeTooltipHost()
        self._preferences_path.write_text(
            json.dumps(
                {
                    "kind": APP_PREFERENCES_KIND,
                    "version": APP_PREFERENCES_VERSION,
                    "graphics": {
                        "shell": {
                            "tooltip_categories": {
                                "general": False,
                                "advanced": True,
                                "warning": False,
                                "critical": False,
                            },
                        },
                    },
                }
            ),
            encoding="utf-8",
        )

        resolved = self._controller.load_into_host(host)

        self.assertNotIn("show_tooltips", resolved["shell"])
        self.assertEqual(
            resolved["shell"]["tooltip_categories"],
            {
                "general": False,
                "tutorial": True,
                "advanced": True,
                "warning": False,
                "inactive": True,
            },
        )
        self.assertFalse(host.shell_workspace_presenter.graphics_show_tooltips)
        self.assertEqual(host.workspace_ui_state.graphics_tooltip_categories, resolved["shell"]["tooltip_categories"])
        self.assertTrue(host.tooltip_manager.tooltip_categories["advanced"])
        self.assertTrue(host.tooltip_manager.category_tooltips_enabled(TOOLTIP_CATEGORY_ADVANCED))
        self.assertFalse(host.tooltip_manager.category_tooltips_enabled(TOOLTIP_CATEGORY_WARNING))
        self.assertTrue(host.tooltip_manager.category_tooltips_enabled(TOOLTIP_CATEGORY_CRITICAL))
        self.assertEqual(host._synced_general_help_tooltips, [False])
        self.assertFalse(shell_context_properties._qt_graphics_show_tooltips(host))
        self.assertTrue(shell_context_properties._qt_graphics_tooltip_category_visibility(host)["advanced"])

    def test_tooltip_preferences_shell_entry_point_updates_runtime_and_store(self) -> None:
        host = _RuntimeTooltipHost(controller=self._controller)

        shell_run_and_style_state.ShellWindowRunAndStyleStateMixin.set_graphics_tooltip_category_enabled(
            host,
            TOOLTIP_CATEGORY_GENERAL,
            False,
        )
        shell_run_and_style_state.ShellWindowRunAndStyleStateMixin.set_graphics_tooltip_category_enabled(
            host,
            TOOLTIP_CATEGORY_WARNING,
            False,
        )

        persisted = json.loads(self._preferences_path.read_text(encoding="utf-8"))

        self.assertFalse(host.shell_workspace_presenter.graphics_show_tooltips)
        self.assertFalse(host.tooltip_manager.category_tooltips_enabled(TOOLTIP_CATEGORY_GENERAL))
        self.assertFalse(host.workspace_ui_state.graphics_tooltip_categories["warning"])
        self.assertFalse(host.tooltip_manager.category_tooltips_enabled(TOOLTIP_CATEGORY_WARNING))
        self.assertTrue(host.tooltip_manager.category_tooltips_enabled(TOOLTIP_CATEGORY_CRITICAL))
        self.assertEqual(host._synced_general_help_tooltips, [False, False])
        self.assertNotIn("show_tooltips", persisted["graphics"]["shell"])
        self.assertFalse(persisted["graphics"]["shell"]["tooltip_categories"]["general"])
        self.assertFalse(persisted["graphics"]["shell"]["tooltip_categories"]["warning"])

    def test_tooltip_manager_general_category_keeps_warning_and_inactive_visibility_independent(self) -> None:
        manager = TooltipManager(tooltip_categories={TOOLTIP_CATEGORY_GENERAL: False})

        self.assertFalse(manager.should_show_info_tooltip("Show grid"))
        self.assertTrue(manager.should_show_warning_tooltip("Disabled while running"))
        self.assertTrue(manager.should_show_inactive_tooltip("Unavailable for passive nodes"))
        self.assertFalse(manager.should_show_warning_tooltip(""))
        self.assertFalse(manager.should_show_inactive_tooltip(""))

    def test_tooltip_category_manager_effective_visibility_contract(self) -> None:
        manager = TooltipManager(
            tooltip_categories={
                TOOLTIP_CATEGORY_GENERAL: False,
                TOOLTIP_CATEGORY_TUTORIAL: False,
                TOOLTIP_CATEGORY_ADVANCED: True,
            }
        )

        self.assertFalse(manager.should_show_category_tooltip(TOOLTIP_CATEGORY_GENERAL, "General help"))
        self.assertFalse(manager.should_show_category_tooltip(TOOLTIP_CATEGORY_TUTORIAL, "Try this"))
        self.assertTrue(manager.should_show_category_tooltip(TOOLTIP_CATEGORY_ADVANCED, "Power tip"))
        self.assertTrue(manager.should_show_category_tooltip(TOOLTIP_CATEGORY_WARNING, "Risk"))
        self.assertTrue(manager.should_show_category_tooltip(TOOLTIP_CATEGORY_INACTIVE, "Disabled"))
        self.assertTrue(manager.should_show_category_tooltip(TOOLTIP_CATEGORY_CRITICAL, "Blocked"))
        self.assertFalse(manager.should_show_category_tooltip("future", "Unknown"))

        self.assertTrue(manager.set_tooltip_category_enabled(TOOLTIP_CATEGORY_GENERAL, True))
        self.assertTrue(manager.set_tooltip_category_enabled(TOOLTIP_CATEGORY_TUTORIAL, True))
        self.assertTrue(manager.should_show_category_tooltip(TOOLTIP_CATEGORY_GENERAL, "General help"))
        self.assertTrue(manager.should_show_category_tooltip(TOOLTIP_CATEGORY_TUTORIAL, "Try this"))

    def test_tooltip_category_manager_normalizes_unknown_and_keeps_critical_enabled(self) -> None:
        manager = TooltipManager(
            tooltip_categories={
                " general ": False,
                "warning": False,
                "critical": False,
                "unknown": True,
            },
        )

        self.assertEqual(
            manager.tooltip_categories,
            {
                "general": False,
                "tutorial": True,
                "advanced": False,
                "warning": False,
                "inactive": True,
            },
        )
        self.assertFalse(manager.should_show_info_tooltip("General help"))
        self.assertFalse(manager.should_show_warning_tooltip("Risk"))
        self.assertTrue(manager.should_show_category_tooltip(TOOLTIP_CATEGORY_CRITICAL, "Blocked"))
        self.assertFalse(manager.set_tooltip_category_enabled(TOOLTIP_CATEGORY_CRITICAL, False))
        self.assertTrue(manager.should_show_category_tooltip(TOOLTIP_CATEGORY_CRITICAL, "Blocked"))

    def test_expand_collision_avoidance_preferences_default_and_partial_payloads(self) -> None:
        defaults = self._controller.load()["graphics"]["interaction"]["expand_collision_avoidance"]

        self.assertEqual(defaults, DEFAULT_GRAPHICS_SETTINGS["interaction"]["expand_collision_avoidance"])

        current_graphics = copy.deepcopy(DEFAULT_GRAPHICS_SETTINGS)
        current_graphics["interaction"]["expand_collision_avoidance"] = {
            "enabled": False,
        }

        graphics = self._controller.set_graphics_settings(current_graphics)

        self.assertEqual(
            graphics["interaction"]["expand_collision_avoidance"],
            {
                **DEFAULT_GRAPHICS_SETTINGS["interaction"]["expand_collision_avoidance"],
                "enabled": False,
            },
        )

    def test_plot_preferences_default_partial_payloads_and_controller_updates(self) -> None:
        defaults = self._controller.load()["graphics"]["plot"]

        self.assertEqual(defaults, DEFAULT_GRAPHICS_SETTINGS["plot"])
        self.assertFalse(defaults["lightweight_canvas"])

        graphics = self._controller.set_graphics_settings(
            {
                "plot": {
                    "lightweight_canvas": True,
                    "plot_default_backend_per_type": {
                        " line ": "matplotlib",
                        "surface": "matplotlib",
                        "unknown": "matplotlib",
                        "scatter": "auto",
                        "bar": "third_party",
                    },
                }
            }
        )
        persisted = json.loads(self._preferences_path.read_text(encoding="utf-8"))

        self.assertTrue(graphics["plot"]["lightweight_canvas"])
        self.assertEqual(
            graphics["plot"]["plot_default_backend_per_type"],
            DEFAULT_GRAPHICS_SETTINGS["plot"]["plot_default_backend_per_type"],
        )
        self.assertNotIn("surface", graphics["plot"]["plot_default_backend_per_type"])
        self.assertNotIn("unknown", graphics["plot"]["plot_default_backend_per_type"])
        self.assertEqual(persisted["graphics"]["plot"], graphics["plot"])

        host = _RuntimeTooltipHost(self._controller)
        self._controller.load_into_host(host)
        seen = {"graphics": 0}
        host.graphics_preferences_changed.connect(
            lambda: seen.__setitem__("graphics", seen["graphics"] + 1)
        )

        updated = self._controller.set_plot_lightweight_canvas(False, host=host)

        self.assertFalse(updated["plot"]["lightweight_canvas"])
        self.assertEqual(seen["graphics"], 1)
        self.assertEqual(host._scene_refresh_count, 0)

    def test_plot_default_backend_normalizer_uses_registry_capabilities(self) -> None:
        normalized = normalize_plot_default_backend_per_type(
            {
                "line": "matplotlib",
                "point_cloud": "matplotlib",
                "scatter": "auto",
                "future": "matplotlib",
            }
        )

        self.assertEqual(
            normalized,
            DEFAULT_GRAPHICS_SETTINGS["plot"]["plot_default_backend_per_type"],
        )
        self.assertNotIn("point_cloud", normalized)
        self.assertNotIn("future", normalized)

    def test_graph_typography_preferences_default_schema_and_partial_current_payload(self) -> None:
        defaults = self._controller.load()["graphics"]

        self.assertEqual(defaults["typography"]["graph_label_pixel_size"], 10)
        self.assertIsNone(defaults["typography"]["graph_node_icon_pixel_size_override"])

        self._preferences_path.write_text(
            json.dumps(
                {
                    "kind": APP_PREFERENCES_KIND,
                    "version": APP_PREFERENCES_VERSION,
                    "graphics": {
                        "canvas": {
                            "show_grid": False,
                        },
                        "theme": {
                            "theme_id": "stitch_light",
                        },
                    },
                }
            ),
            encoding="utf-8",
        )

        graphics = AppPreferencesController(store=self._store).load()["graphics"]

        self.assertFalse(graphics["canvas"]["show_grid"])
        self.assertEqual(graphics["theme"]["theme_id"], "stitch_light")
        self.assertEqual(graphics["typography"]["graph_label_pixel_size"], 10)
        self.assertIsNone(graphics["typography"]["graph_node_icon_pixel_size_override"])

    def test_graph_typography_preferences_clamp_invalid_values_without_disturbing_other_graphics(self) -> None:
        cases = (
            ("missing", {}, 10),
            ("non-integer", {"graph_label_pixel_size": "11"}, 10),
            ("low", {"graph_label_pixel_size": 3}, 8),
            ("high", {"graph_label_pixel_size": 64}, 50),
        )

        for _label, typography_payload, expected in cases:
            with self.subTest(case=_label):
                self._preferences_path.write_text(
                    json.dumps(
                        {
                            "kind": APP_PREFERENCES_KIND,
                            "version": APP_PREFERENCES_VERSION,
                            "graphics": {
                                "canvas": {
                                    "show_grid": False,
                                },
                                "typography": typography_payload,
                            },
                        }
                    ),
                    encoding="utf-8",
                )

                graphics = AppPreferencesController(store=self._store).load()["graphics"]

                self.assertFalse(graphics["canvas"]["show_grid"])
                self.assertEqual(
                    graphics["typography"]["graph_label_pixel_size"],
                    expected,
                )

    def test_graph_node_icon_size_preferences_default_missing_and_invalid_values_normalize_to_null(self) -> None:
        cases = (
            ("missing", {}, None),
            ("null", {"graph_node_icon_pixel_size_override": None}, None),
            ("string", {"graph_node_icon_pixel_size_override": "12"}, None),
            ("boolean", {"graph_node_icon_pixel_size_override": True}, None),
            ("float", {"graph_node_icon_pixel_size_override": 12.5}, None),
        )

        for label, typography_payload, expected in cases:
            with self.subTest(case=label):
                self._preferences_path.write_text(
                    json.dumps(
                        {
                            "kind": APP_PREFERENCES_KIND,
                            "version": APP_PREFERENCES_VERSION,
                            "graphics": {
                                "typography": typography_payload,
                            },
                        }
                    ),
                    encoding="utf-8",
                )

                typography = AppPreferencesController(store=self._store).load()["graphics"]["typography"]

                self.assertEqual(typography["graph_node_icon_pixel_size_override"], expected)
                self.assertEqual(
                    effective_graph_node_icon_pixel_size(
                        typography["graph_label_pixel_size"],
                        typography["graph_node_icon_pixel_size_override"],
                    ),
                    typography["graph_label_pixel_size"],
                )

    def test_graph_node_icon_size_preferences_clamp_persist_and_roundtrip_override(self) -> None:
        graphics = self._controller.set_graphics_settings(
            {
                "typography": {
                    "graph_label_pixel_size": 12,
                    "graph_node_icon_pixel_size_override": 27,
                },
            }
        )

        persisted = json.loads(self._preferences_path.read_text(encoding="utf-8"))

        self.assertEqual(graphics["typography"]["graph_label_pixel_size"], 12)
        self.assertEqual(graphics["typography"]["graph_node_icon_pixel_size_override"], 27)
        self.assertEqual(effective_graph_node_icon_pixel_size(12, 27), 27)
        self.assertEqual(
            persisted["graphics"]["typography"],
            {
                "graph_label_pixel_size": 12,
                "graph_node_icon_pixel_size_override": 27,
                "recent_text_colors": [],
            },
        )
        self.assertEqual(
            AppPreferencesController(store=self._store).load()["graphics"]["typography"],
            {
                "graph_label_pixel_size": 12,
                "graph_node_icon_pixel_size_override": 27,
                "recent_text_colors": [],
            },
        )

    def test_graph_node_icon_size_preferences_clamp_high_values_to_fifty(self) -> None:
        graphics = self._controller.set_graphics_settings(
            {
                "typography": {
                    "graph_label_pixel_size": 12,
                    "graph_node_icon_pixel_size_override": 72,
                },
            }
        )

        self.assertEqual(graphics["typography"]["graph_label_pixel_size"], 12)
        self.assertEqual(graphics["typography"]["graph_node_icon_pixel_size_override"], 50)
        self.assertEqual(effective_graph_node_icon_pixel_size(12, 72), 50)

    def test_graph_node_icon_size_preferences_automatic_effective_size_follows_graph_label_size(self) -> None:
        graphics = self._controller.set_graphics_settings(
            {
                "typography": {
                    "graph_label_pixel_size": 16,
                    "graph_node_icon_pixel_size_override": None,
                },
            }
        )

        self.assertIsNone(graphics["typography"]["graph_node_icon_pixel_size_override"])
        self.assertEqual(
            effective_graph_node_icon_pixel_size(
                graphics["typography"]["graph_label_pixel_size"],
                graphics["typography"]["graph_node_icon_pixel_size_override"],
            ),
            16,
        )

    def test_graph_typography_preferences_persist_nested_block_on_save(self) -> None:
        graphics = self._controller.set_graphics_settings(
            {
                "canvas": {
                    "show_grid": False,
                },
                "typography": {
                    "graph_label_pixel_size": 17,
                },
            }
        )

        persisted = json.loads(self._preferences_path.read_text(encoding="utf-8"))

        self.assertEqual(graphics["typography"]["graph_label_pixel_size"], 17)
        self.assertEqual(
            persisted["graphics"]["typography"],
            {
                "graph_label_pixel_size": 17,
                "graph_node_icon_pixel_size_override": None,
                "recent_text_colors": [],
            },
        )
        self.assertEqual(
            AppPreferencesController(store=self._store).load()["graphics"]["typography"],
            {
                "graph_label_pixel_size": 17,
                "graph_node_icon_pixel_size_override": None,
                "recent_text_colors": [],
            },
        )

    def test_graph_typography_preferences_load_into_host_applies_normalized_size(self) -> None:
        host = _RecordingHost()
        self._preferences_path.write_text(
            json.dumps(
                {
                    "kind": APP_PREFERENCES_KIND,
                    "version": APP_PREFERENCES_VERSION,
                    "graphics": {
                        "typography": {
                            "graph_label_pixel_size": 22,
                        },
                    },
                }
            ),
            encoding="utf-8",
        )

        resolved = self._controller.load_into_host(host)

        self.assertEqual(host.applied_graphics, [resolved])
        self.assertEqual(resolved["typography"]["graph_label_pixel_size"], 22)

    def test_graph_typography_dialog_preferences_persist_app_global_graph_label_size(self) -> None:
        self._preferences_path.write_text(
            json.dumps(
                {
                    "kind": APP_PREFERENCES_KIND,
                    "version": APP_PREFERENCES_VERSION,
                    "graphics": {
                        "canvas": {
                            "show_grid": False,
                        },
                        "typography": "invalid",
                    },
                }
            ),
            encoding="utf-8",
        )

        loaded = self._controller.load()["graphics"]
        self.assertFalse(loaded["canvas"]["show_grid"])
        self.assertEqual(loaded["typography"]["graph_label_pixel_size"], 10)
        self.assertIsNone(loaded["typography"]["graph_node_icon_pixel_size_override"])

        host = _RecordingHost()
        resolved = self._controller.set_graphics_settings(
            {
                "canvas": {
                    "show_grid": False,
                },
                "typography": {
                    "graph_label_pixel_size": 17,
                },
            },
            host=host,
        )

        persisted = json.loads(self._preferences_path.read_text(encoding="utf-8"))

        self.assertEqual(host.applied_graphics, [resolved])
        self.assertFalse(resolved["canvas"]["show_grid"])
        self.assertEqual(resolved["typography"]["graph_label_pixel_size"], 17)
        self.assertEqual(
            persisted["graphics"]["typography"],
            {
                "graph_label_pixel_size": 17,
                "graph_node_icon_pixel_size_override": None,
                "recent_text_colors": [],
            },
        )
        self.assertEqual(
            AppPreferencesController(store=self._store).load()["graphics"]["typography"]["graph_label_pixel_size"],
            17,
        )

    def test_startup_theme_resolution_reads_preferences_store_without_controller(self) -> None:
        self._preferences_path.write_text(
            json.dumps(
                {
                    "kind": APP_PREFERENCES_KIND,
                    "version": APP_PREFERENCES_VERSION,
                    "graphics": {
                        "theme": {
                            "theme_id": "stitch_light",
                        },
                    },
                }
            ),
            encoding="utf-8",
        )

        self.assertEqual(resolve_startup_theme_id(store=self._store), "stitch_light")


if __name__ == "__main__":
    unittest.main()

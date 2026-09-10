from pathlib import Path
import sys
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

pv = pytest.importorskip("pyvista")
pytest.importorskip("PyQt6")
pytest.importorskip("pyvistaqt")
from PyQt6.QtWidgets import QApplication  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
SG_ROOT = REPO_ROOT / "scripts" / "Strain_Gage_Positioning" / "modular_version"
if str(SG_ROOT) not in sys.path:
    sys.path.insert(0, str(SG_ROOT))

from app import dpf_loader  # noqa: E402
from app import ansys_overlay  # noqa: E402
from app import main_window  # noqa: E402
from app.analysis_engine import AnalysisEngine  # noqa: E402
from app.dpf_dialog import DpfImportDialog  # noqa: E402
from app.ui_tools import (  # noqa: E402
    ContourHoverUI,
    PLACEMENT_COLUMNS,
    build_gage_placements,
    project_to_tangent,
    surface_angle_from_axis,
    surface_axes_from_angle,
)


BENCHMARK_RST = Path(
    r"C:\Users\user\Documents\ANSYS\Benchmark"
    r"\ENFO_conversion\enfo_conversion_example_files\dp0\SYS-6\MECH\file.rst"
)
LOAD_RECONSTRUCTION_RST = Path(
    r"C:\Users\user\Documents\ANSYS\Benchmark"
    r"\load_reconstruction_v0_files\dp0\SYS-15\MECH\file.rst"
)


def _plane_surface():
    surface = pv.Plane(
        center=(0.0, 0.0, 0.0),
        direction=(0.0, 0.0, 1.0),
        i_size=2.0,
        j_size=2.0,
    )
    return surface.compute_normals(point_normals=True, cell_normals=True, inplace=False)


def _triangle_surface(node_ids=(30, 10, 20)):
    surface = pv.PolyData(
        np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]),
        np.array([3, 0, 1, 2]),
    )
    surface.point_data["DPFNodeId"] = np.asarray(node_ids, dtype=int)
    return surface


def _candidate_df():
    return pd.DataFrame({
        "Node": [10, 11],
        "X": [0.0, 0.5],
        "Y": [0.0, 0.0],
        "Z": [0.0, 0.0],
        "Best_Strain": [120.0, 80.0],
        "Best_Angle": [0.0, 90.0],
        "Local_Std": [1.0, 2.0],
        "Quality": [10.0, 9.0],
    })


def test_rst_set_summary_does_not_dump_many_sets():
    assert main_window._format_rst_set_summary(range(1, 74)) == "sets 1-73 (73 sets)"
    assert main_window._format_rst_set_summary([1, 2, 5, 9, 12, 20, 30]) == "sets 1,2,5,...30 (7 sets)"


def test_contour_set_parser_supports_single_ranges_and_loaded_subsets():
    available = [1, 2, 3, 5]

    assert main_window._parse_contour_set_ids("all", available) == available
    assert main_window._parse_contour_set_ids("last", available) == [5]
    assert main_window._parse_contour_set_ids("3", available) == [3]
    assert main_window._parse_contour_set_ids("1-3,5", available) == available
    with pytest.raises(ValueError, match="not loaded"):
        main_window._parse_contour_set_ids("2-5", available)


def test_analysis_keeps_each_case_scalar_for_contour_selection():
    params = {
        "measurement_mode": "Rosette",
        "quality_mode": "Default: |ε|/(1+σ)",
        "uniformity_radius": 2.0,
        "agg_method": "Max",
        "strain_threshold_enabled": False,
    }
    engine = AnalysisEngine(None, params, False)
    nodes = np.array([1, 2])
    coords = np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]])
    tensors = {
        0: np.array([[1.0, 0.0, 0.0], [2.0, 0.0, 0.0]]),
        1: np.array([[3.0, 0.0, 0.0], [0.5, 0.0, 0.0]]),
    }

    _quality, aggregate, cases = engine._compute_quality(nodes, coords, tensors)

    np.testing.assert_allclose(cases[0], [1.0, 2.0])
    np.testing.assert_allclose(cases[1], [3.0, 0.5])
    np.testing.assert_allclose(aggregate, [3.0, 2.0])


def test_dpf_dialog_can_ignore_evaluation_only_shell_results():
    app = QApplication.instance() or QApplication([])
    dialog = DpfImportDialog(
        "file.rst",
        {
            "n_sets": 3,
            "n_nodes": 100,
            "stress_evaluation_shell_count": 1,
        },
    )

    assert dialog.chk_ignore_evaluation_shells.isEnabled()
    assert not dialog.get_selection()[3]
    dialog.chk_ignore_evaluation_shells.setChecked(True)
    assert dialog.get_selection()[3]
    dialog.close()
    assert app is not None


class _FakeLookupTable:
    def __init__(self, n_values=9):
        self.values = np.tile(
            np.array([[10, 20, 30, 255]], dtype=np.uint8), (max(n_values, 1), 1)
        )

    def GetUseBelowRangeColor(self):
        return True

    def GetBelowRangeColor(self):
        return (0.5, 0.5, 0.5, 1.0)

    def GetUseAboveRangeColor(self):
        return True

    def GetAboveRangeColor(self):
        return (0.5, 0.0, 0.5, 1.0)


class _FakeActor(str):
    """Compares equal to its name, but carries a mapper like a real actor."""

    def __new__(cls, name, lookup_table=None):
        actor = super().__new__(cls, name)
        actor.mapper = SimpleNamespace(lookup_table=lookup_table)
        return actor


class _StubRenderWindow:
    def GetSize(self):
        return (1000, 800)


class _StubPlotter:
    """Enough plotter for the overlay geometry, with no render window."""

    def __init__(self):
        self.render_window = _StubRenderWindow()
        self.actors = {}

    def add_actor(self, actor, name=None, **_kwargs):
        self.actors[name] = actor
        return actor, None

    def remove_actor(self, actor, **_kwargs):
        for key, value in list(self.actors.items()):
            if value is actor:
                del self.actors[key]


class _FakeCamera:
    def __init__(self, generation=0):
        self.generation = generation

    def copy(self):
        # Returns another camera, so repeated preserve_camera redraws work
        # the way they do against a real plotter.
        return _FakeCamera(self.generation + 1)


class _FakePlotter:
    def __init__(self):
        self.camera = _FakeCamera()
        self.add_mesh_calls = []
        self.add_actor_calls = []
        self.removed_actors = []
        self.clear_count = 0
        self.reset_count = 0
        self.render_count = 0

    def add_mesh(self, *args, **kwargs):
        self.add_mesh_calls.append((args, kwargs))
        return _FakeActor(
            "actor-{0}".format(len(self.add_mesh_calls)),
            _FakeLookupTable(int(kwargs.get("n_colors", 256))),
        )

    def add_actor(self, actor, **kwargs):
        # Overlay actors must never land in add_mesh_calls, so the contour
        # assertions can keep indexing that list positionally.
        self.add_actor_calls.append((actor, kwargs))
        return actor, None

    def remove_actor(self, actor, **_kwargs):
        self.removed_actors.append(actor)

    def clear(self):
        self.clear_count += 1

    def reset_camera(self):
        self.reset_count += 1

    def render(self):
        self.render_count += 1


class _FakeVisualizationPanel:
    def __init__(self, plotter):
        self.vtk_widget = plotter
        self.enabled_values = []
        self.contour_entries = []
        self.contour_text = "all"
        self.contour_aggregation = "Max"
        self._settings = {
            "cloud_point_size": 8.0,
            "candidate_point_size": 12.0,
            "label_font_size": 11,
            "n_bands": 9,
            "clim_min": 1.0,
            "clim_max": 3.0,
            "below_color": "gray",
            "above_color": "purple",
            "show_surface_edges": True,
            "surface_mesh_opacity": 0.42,
            "show_surface_normals": True,
            "show_gage_axes": True,
        }

    def get_settings(self):
        return dict(self._settings)

    def set_surface_placement_enabled(self, value):
        self.enabled_values.append(bool(value))

    def configure_contour_sets(self, entries, default_aggregation="Max", reset=False):
        self.contour_entries = list(entries or [])
        if reset:
            self.contour_text = "all"
            self.contour_aggregation = default_aggregation

    def get_contour_selection(self):
        return self.contour_text, self.contour_aggregation, list(self.contour_entries)


class _FakeInputPanel:
    def __init__(self):
        self.labels = []

    def set_file_label(self, label):
        self.labels.append(label)


class _FakeGagePlacementTool:
    def __init__(self):
        self.contexts = []
        self.visibility = []

    def set_context(self, surface_info, candidates_df, named_selection=None):
        self.contexts.append((surface_info, candidates_df, named_selection))

    def set_visibility(self, show_normals=True, show_axes=True):
        self.visibility.append((show_normals, show_axes))


class _FakeResultHeader:
    def __init__(self):
        self.infos = []
        self.clear_count = 0

    def set_info(self, title, lines):
        self.infos.append((title, list(lines)))

    def bottom_y(self):
        return 0.9

    def clear(self):
        self.clear_count += 1


class _FakeResultLegend:
    def __init__(self):
        self.contexts = []
        self.clear_count = 0

    def set_context(self, colors, clim, n_bands, **kwargs):
        self.contexts.append((colors, clim, n_bands, kwargs))

    def clear(self):
        self.clear_count += 1


class _FakeResultAnnotations:
    def __init__(self):
        self.point_sets = []
        self.clear_count = 0

    def set_points(self, points, texts, font_size=None):
        self.point_sets.append((points, list(texts), font_size))

    def clear(self):
        self.clear_count += 1


class _FakeContourHoverTool:
    def __init__(self):
        self.contexts = []
        self.clear_count = 0

    def set_context(self, *context):
        self.contexts.append(context)

    def clear_context(self):
        self.clear_count += 1


class _FakeTextProperty:
    def __init__(self):
        self.font_size = None
        self.framed = False

    def SetBackgroundColor(self, *_):
        pass

    def SetBackgroundOpacity(self, *_):
        pass

    def SetFontSize(self, size):
        self.font_size = size

    def SetFontFamilyToArial(self):
        pass

    def SetBold(self, *_):
        pass

    def SetShadow(self, *_):
        pass

    def FrameOn(self):
        self.framed = True

    def SetFrameColor(self, *_):
        pass

    def SetFrameWidth(self, *_):
        pass


class _FakeTextActor:
    def __init__(self):
        self.text = ""
        self.visible = False
        self.position = (0, 0)
        self.text_property = _FakeTextProperty()

    def GetTextProperty(self):
        return self.text_property

    def SetInput(self, text):
        self.text = text

    def SetPickable(self, *_):
        pass

    def SetVisibility(self, visible):
        self.visible = bool(visible)

    def GetSize(self, _renderer, size):
        size[:] = [120.0, 40.0]

    def SetDisplayPosition(self, x, y):
        self.position = (x, y)


class _FakeObserverInteractor:
    def __init__(self):
        self.added = []
        self.removed = []

    def add_observer(self, event, callback):
        self.added.append((event, callback))
        return 17

    def remove_observer(self, observer_id):
        self.removed.append(observer_id)


class _FakeHoverPlotter:
    def __init__(self):
        self.iren = _FakeObserverInteractor()
        self.renderer = object()
        self.text_actors = []
        self.removed = []

    def add_text(self, *_args, **_kwargs):
        actor = _FakeTextActor()
        self.text_actors.append(actor)
        return actor

    def remove_actor(self, actor, **_kwargs):
        self.removed.append(actor)


class _FakeCellPicker:
    def __init__(self):
        self.pick_result = True
        self.cell_id = 0
        self.point = (1.0 / 3.0, 1.0 / 3.0, 0.0)
        self.pick_list = []

    def InitializePickList(self):
        self.pick_list.clear()

    def AddPickList(self, actor):
        self.pick_list.append(actor)

    def Pick(self, *_):
        return self.pick_result

    def GetCellId(self):
        return self.cell_id

    def GetPickPosition(self):
        return self.point


class _FakeRenderWindow:
    def __init__(self):
        self.render_count = 0

    def GetSize(self):
        return (200, 100)

    def Render(self):
        self.render_count += 1


class _FakeMouseInteractor:
    def __init__(self):
        self.render_window = _FakeRenderWindow()

    def GetEventPosition(self):
        return (190, 90)

    def GetRenderWindow(self):
        return self.render_window


def _preview_window(surface=None):
    plotter = _FakePlotter()
    surface = surface if surface is not None else _plane_surface()
    window = SimpleNamespace(
        rst_surface_mesh={"surface": surface},
        visualization_panel=_FakeVisualizationPanel(plotter),
        gage_placement_tool=_FakeGagePlacementTool(),
        contour_hover_tool=_FakeContourHoverTool(),
        result_header=_FakeResultHeader(),
        result_legend=_FakeResultLegend(),
        result_annotations=_FakeResultAnnotations(),
        last_results={},
        preloaded_dataset=("old",),
        input_file=None,
        rst_named_selection="NS",
        input_panel=_FakeInputPanel(),
        project_dir=str(REPO_ROOT),
        display_in_strain=False,
        control_panel=SimpleNamespace(
            get_parameters=lambda: {
                "strategy": "Max Quality (Greedy Search)",
                "measurement_mode": "Rosette",
                "quality_mode": "Signal-Noise Ratio: |e|/(s+1e-12)",
            }
        ),
    )
    window.clear_visualization = (
        lambda preserve_camera=False: main_window.MainWindow.clear_visualization(
            window, preserve_camera=preserve_camera
        )
    )
    window.display_rst_surface_preview = (
        lambda preserve_camera=False: main_window.MainWindow.display_rst_surface_preview(
            window, preserve_camera=preserve_camera
        )
    )
    window._result_header_info = (
        lambda contour_label: main_window.MainWindow._result_header_info(
            window, contour_label
        )
    )
    window.update_result_overlay = (
        lambda actor, scalars, viz_settings, contour_label: main_window.MainWindow.update_result_overlay(
            window, actor, scalars, viz_settings, contour_label
        )
    )
    window._add_rst_surface_mesh = (
        lambda plotter: main_window.MainWindow._add_rst_surface_mesh(window, plotter)
    )
    return window


def test_contour_selection_is_independent_from_positioning_aggregate():
    window = _preview_window()
    window.visualization_panel.configure_contour_sets([
        (1, "Set 1 — time/frequency 0.1"),
        (2, "Set 2 — time/frequency 0.2"),
        (3, "Set 3 — time/frequency 0.3"),
    ])
    window.last_results = {
        "scalars": np.array([30.0, 30.0]),
        "case_scalars": {
            0: np.array([1.0, 2.0]),
            1: np.array([10.0, 20.0]),
            2: np.array([100.0, 200.0]),
        },
    }

    window.visualization_panel.contour_text = "2"
    scalars, label = main_window.MainWindow._selected_contour_data(window)
    np.testing.assert_allclose(scalars, [10.0, 20.0])
    assert label == "Set 2 — time/frequency 0.2"

    window.visualization_panel.contour_text = "1-2"
    window.visualization_panel.contour_aggregation = "Average"
    scalars, label = main_window.MainWindow._selected_contour_data(window)
    np.testing.assert_allclose(scalars, [5.5, 11.0])
    assert label == "Average of sets 1,2"


def test_rst_surface_result_indices_follow_solver_node_ids():
    surface = _triangle_surface()

    indices = main_window._rst_surface_result_indices(
        np.array([10, 20, 30]), surface
    )

    assert indices.tolist() == [2, 0, 1]
    with pytest.raises(ValueError, match="no strain result"):
        main_window._rst_surface_result_indices(np.array([10, 20]), surface)


def test_contour_hover_interpolates_inside_surface_cells():
    surface = _triangle_surface()
    surface.point_data["Scalars"] = np.array([0.0, 3.0, 6.0])

    assert ContourHoverUI.interpolate_scalar(
        surface, 0, (0.0, 0.0, 0.0), "Scalars"
    ) == pytest.approx(0.0)
    assert ContourHoverUI.interpolate_scalar(
        surface, 0, (1.0 / 3.0, 1.0 / 3.0, 0.0), "Scalars"
    ) == pytest.approx(3.0)

    surface.point_data["Scalars"] = np.array([0.0, np.nan, 6.0])
    assert ContourHoverUI.interpolate_scalar(
        surface, 0, (1.0 / 3.0, 1.0 / 3.0, 0.0), "Scalars"
    ) is None


def test_contour_hover_reuses_observer_and_clears_on_miss():
    plotter = _FakeHoverPlotter()
    tool = ContourHoverUI(plotter)
    tool.picker = _FakeCellPicker()
    surface = _triangle_surface()
    surface.point_data["Scalars"] = np.array([0.0, 3.0, 6.0])
    interactor = _FakeMouseInteractor()

    tool.set_context("contour-actor", surface, "Scalars", "Microstrain (με)")
    tool._on_mouse_move(interactor, None)

    tooltip = tool.tooltip_actor
    assert plotter.iren.added[0][0] == "MouseMoveEvent"
    assert len(plotter.iren.added) == 1
    assert tool.picker.pick_list == ["contour-actor"]
    assert tooltip.visible
    assert "Microstrain (με): 3" in tooltip.text
    assert "X/Y/Z [mm]: 0.333333, 0.333333, 0" in tooltip.text
    assert tooltip.position[0] < 190
    assert tooltip.position[1] < 90

    tool.picker.pick_result = False
    tool._last_hover_time = 0.0
    tool._on_mouse_move(interactor, None)
    assert not tooltip.visible
    assert tooltip.text == ""

    tool.set_context("new-actor", surface, "Scalars", "Strain (mm/mm)")
    assert len(plotter.iren.added) == 1
    tool.close()
    assert plotter.iren.removed == [17]


def test_surface_axes_are_orthonormal_and_angle_wraps():
    axis_x, axis_y, normal = surface_axes_from_angle((0.0, 0.0, 1.0), 195.0)

    assert np.isclose(np.linalg.norm(axis_x), 1.0)
    assert np.isclose(np.linalg.norm(axis_y), 1.0)
    assert np.isclose(np.linalg.norm(normal), 1.0)
    assert np.isclose(np.dot(axis_x, normal), 0.0, atol=1.0e-12)
    assert np.isclose(np.dot(axis_y, normal), 0.0, atol=1.0e-12)
    assert np.isclose(np.dot(axis_x, axis_y), 0.0, atol=1.0e-12)
    assert np.isclose(surface_angle_from_axis(normal, axis_x), 15.0)


def test_manual_direction_projects_to_tangent_plane():
    normal = np.asarray((0.0, 0.0, 1.0))
    projected = project_to_tangent((1.0, 1.0, 5.0), normal)

    assert np.allclose(projected, (1.0, 1.0, 0.0))
    assert np.isclose(surface_angle_from_axis(normal, projected), 45.0)


def test_build_gage_placements_csv_shape_and_override_axes():
    candidates = _candidate_df()
    original_columns = list(candidates.columns)
    records = build_gage_placements(
        candidates,
        _plane_surface(),
        named_selection="NS_FACES_FANDUCT",
        overrides={0: {
            "origin": np.asarray((0.0, 0.0, 0.0)),
            "direction_pick": np.asarray((1.0, 1.0, 5.0)),
        }},
    )
    df = pd.DataFrame(records, columns=PLACEMENT_COLUMNS)

    assert list(candidates.columns) == original_columns
    assert list(df.columns) == PLACEMENT_COLUMNS
    assert len(df) == 2
    assert bool(df.loc[0, "Manual_Override"])
    assert not bool(df.loc[1, "Manual_Override"])
    assert np.isclose(df.loc[0, "Surface_Angle_Deg"], 45.0)
    axis_x = df.loc[0, ["Axis_X_X", "Axis_X_Y", "Axis_X_Z"]].to_numpy(float)
    axis_y = df.loc[0, ["Axis_Y_X", "Axis_Y_Y", "Axis_Y_Z"]].to_numpy(float)
    normal = df.loc[0, ["Normal_X", "Normal_Y", "Normal_Z"]].to_numpy(float)
    assert np.isclose(np.linalg.norm(axis_x), 1.0)
    assert np.isclose(np.linalg.norm(axis_y), 1.0)
    assert np.isclose(np.linalg.norm(normal), 1.0)
    assert np.isclose(np.dot(axis_x, normal), 0.0, atol=1.0e-12)
    assert np.isclose(np.dot(axis_y, normal), 0.0, atol=1.0e-12)


def test_rst_surface_preview_draws_mesh_without_analysis_results():
    window = _preview_window()
    plotter = window.visualization_panel.vtk_widget

    main_window.MainWindow.display_rst_surface_preview(window, preserve_camera=False)

    assert plotter.clear_count == 1
    assert plotter.reset_count == 1
    assert plotter.render_count == 1
    assert len(plotter.add_mesh_calls) == 1
    _, kwargs = plotter.add_mesh_calls[0]
    assert kwargs["color"] == "lightgray"
    assert kwargs["opacity"] == 0.42
    assert kwargs["show_edges"] is True


def test_refresh_visualization_redraws_preview_before_analysis():
    window = _preview_window()
    plotter = window.visualization_panel.vtk_widget

    main_window.MainWindow.refresh_visualization(window)

    assert plotter.clear_count == 1
    assert plotter.reset_count == 0
    assert plotter.render_count == 1
    assert len(plotter.add_mesh_calls) == 1


def test_rst_results_render_one_interpolated_surface_contour():
    surface = _triangle_surface()
    window = _preview_window(surface)
    window.rst_surface_mesh["result_indices"] = np.array([2, 0, 1])
    plotter = window.visualization_panel.vtk_widget

    main_window.MainWindow.display_strain_with_candidates(
        window,
        surface.points,
        np.array([1.0, 2.0, 3.0]),
        pd.DataFrame(),
        preserve_camera=False,
        contour_label="Set 2 — time/frequency 0.2",
    )

    assert len(plotter.add_mesh_calls) == 1
    args, kwargs = plotter.add_mesh_calls[0]
    assert args[0] is surface
    assert surface.point_data["Scalars"].tolist() == [3.0, 1.0, 2.0]
    assert kwargs["scalars"] == "Scalars"
    assert kwargs["cmap"].name == "ansys_rainbow"
    # Saturated blue to saturated red, without the dark ends jet has.
    assert ansys_overlay.ANSYS_RAINBOW_COLORS[0] == "#0000FF"
    assert ansys_overlay.ANSYS_RAINBOW_COLORS[-1] == "#FF0000"
    assert kwargs["n_colors"] == 9
    assert kwargs["show_scalar_bar"] is False
    assert "scalar_bar_args" not in kwargs
    assert kwargs["clim"] == (1.0, 3.0)
    assert kwargs["below_color"] == "gray"
    assert kwargs["above_color"] == "purple"
    assert kwargs["opacity"] == 0.42
    assert kwargs["show_edges"] is True
    assert kwargs["interpolate_before_map"] is True
    assert "render_points_as_spheres" not in kwargs
    assert window.contour_hover_tool.contexts[-1] == (
        "actor-1", surface, "Scalars",
        "Microstrain — Set 2 — time/frequency 0.2"
    )

    window.visualization_panel._settings["show_surface_edges"] = False
    main_window.MainWindow.display_strain_with_candidates(
        window,
        surface.points,
        np.array([1.0, 2.0, 3.0]),
        pd.DataFrame(),
        preserve_camera=True,
    )
    assert len(plotter.add_mesh_calls) == 2
    assert plotter.add_mesh_calls[-1][1]["show_edges"] is False


def test_text_results_remain_a_point_cloud():
    window = _preview_window()
    window.rst_surface_mesh = None
    window.preloaded_dataset = None
    plotter = window.visualization_panel.vtk_widget

    main_window.MainWindow.display_strain_with_candidates(
        window,
        np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]]),
        np.array([1.0, 2.0]),
        pd.DataFrame(),
        preserve_camera=False,
    )

    assert len(plotter.add_mesh_calls) == 1
    args, kwargs = plotter.add_mesh_calls[0]
    assert isinstance(args[0], pv.PolyData)
    assert kwargs["render_points_as_spheres"] is True
    assert kwargs["point_size"] == 8.0
    assert window.contour_hover_tool.contexts == []


def test_text_input_resets_rst_preview_state(monkeypatch, tmp_path):
    input_file = tmp_path / "strain.txt"
    input_file.write_text("dummy", encoding="utf-8")
    window = _preview_window()
    clear_calls = []
    window.clear_visualization = lambda preserve_camera=False: clear_calls.append(preserve_camera)

    monkeypatch.setattr(
        main_window.QFileDialog,
        "getOpenFileNames",
        lambda *args, **kwargs: ([str(input_file)], ""),
    )

    main_window.MainWindow.load_strain_data(window)

    assert window.input_file == str(input_file)
    assert window.preloaded_dataset is None
    assert window.rst_surface_mesh is None
    assert window.rst_named_selection is None
    assert window.visualization_panel.enabled_values == [False]
    assert window.gage_placement_tool.contexts[-1] == (None, None, None)
    assert clear_calls == [False]


@pytest.mark.skipif(not BENCHMARK_RST.exists(), reason="benchmark .rst is not available")
@pytest.mark.skipif(not dpf_loader.dpf_available(), reason="ansys-dpf-core is not available")
def test_benchmark_named_selection_surface_has_normals():
    nodes, _coords, _strain_tensors = dpf_loader.load_rst_strain(
        BENCHMARK_RST,
        [1],
        named_selection="NS_FACES_FANDUCT",
    )
    info = dpf_loader.load_rst_surface_mesh(
        BENCHMARK_RST,
        named_selection="NS_FACES_FANDUCT",
    )
    surface = info["surface"]
    normals = np.asarray(surface.point_data["Normals"], dtype=float)
    norms = np.linalg.norm(normals, axis=1)

    assert info["n_points"] > 0
    assert info["n_cells"] > 0
    assert normals.shape[0] == surface.n_points
    assert np.allclose(norms, 1.0, atol=1.0e-6)
    assert np.unique(surface.point_data["DPFNodeId"]).size == surface.n_points
    assert main_window._rst_surface_result_indices(nodes, surface).size == surface.n_points


@pytest.mark.skipif(
    not LOAD_RECONSTRUCTION_RST.exists(), reason="load-reconstruction .rst is not available"
)
@pytest.mark.skipif(not dpf_loader.dpf_available(), reason="ansys-dpf-core is not available")
def test_load_reconstruction_merges_shell_elshape_strain():
    assert dpf_loader.inspect_rst(LOAD_RECONSTRUCTION_RST)[
        "stress_evaluation_shell_count"
    ] == 1
    nodes, _coords, strain_tensors = dpf_loader.load_rst_strain(
        LOAD_RECONSTRUCTION_RST, [1]
    )
    shell_node_ids = np.array([12620, 12621, 12622, 12623])
    shell_rows = dpf_loader._indices_for_ids(nodes, shell_node_ids)

    assert shell_rows.size == shell_node_ids.size
    np.testing.assert_allclose(
        strain_tensors[0][shell_rows, 0], -333.33332976326346, rtol=1.0e-12
    )
    np.testing.assert_allclose(
        strain_tensors[0][shell_rows, 1], 343.4343379922212, rtol=1.0e-12
    )

    surface_info = dpf_loader.load_rst_surface_mesh(LOAD_RECONSTRUCTION_RST)
    assert main_window._rst_surface_result_indices(
        nodes, surface_info["surface"]
    ).size == surface_info["surface"].n_points

    ignored_nodes, _ignored_coords, _ignored_tensors = dpf_loader.load_rst_strain(
        LOAD_RECONSTRUCTION_RST,
        [1],
        ignore_stress_evaluation_shells=True,
    )
    assert np.intersect1d(ignored_nodes, shell_node_ids).size == 0
    ignored_surface_info = dpf_loader.load_rst_surface_mesh(
        LOAD_RECONSTRUCTION_RST,
        ignore_stress_evaluation_shells=True,
        result_node_ids=ignored_nodes,
    )
    assert ignored_surface_info[
        "ignored_stress_evaluation_shell_element_ids"
    ].tolist() == [4123]
    assert 4123 not in np.asarray(
        ignored_surface_info["surface"].cell_data["DPFElementId"], dtype=int
    )
    assert main_window._rst_surface_result_indices(
        ignored_nodes, ignored_surface_info["surface"]
    ).size == ignored_surface_info["surface"].n_points


def test_ansys_number_format_strips_exponent_padding():
    fmt = ansys_overlay.format_ansys_number
    # Mechanical prints 1.3006e-5, not the zero-padded 1.3006e-05 Python emits.
    assert fmt(1.3006e-05) == "1.3006e-5"
    assert fmt(0.0) == "0"
    assert fmt(0.01701) == "0.01701"
    assert fmt(0.0094497) == "0.0094497"
    assert fmt(-2.5e-12) == "-2.5e-12"
    assert fmt(float("nan")) == "nan"


def test_band_boundaries_label_edges_not_centres():
    values = ansys_overlay.band_boundaries(0.0, 0.01701, 9)
    # Nine colour bands carry ten numbers, stepping by max/9 exactly as the
    # Mechanical legend does.
    assert len(values) == 10
    assert values[0] == 0.0
    assert values[-1] == 0.01701
    assert np.allclose(np.diff(values), 0.01701 / 9.0)


def test_band_boundaries_survive_degenerate_limits():
    assert ansys_overlay.band_boundaries(2.0, 2.0, 9)[-1] > 2.0
    assert len(ansys_overlay.band_boundaries(float("nan"), 1.0, 4)) == 5


def test_legend_labels_boundaries_and_hit_tests_max_and_min():
    plotter = _StubPlotter()
    legend = ansys_overlay.AnsysLegend(plotter)
    colors = np.tile(np.array([[0, 0, 255]], dtype=np.uint8), (9, 1))
    legend.set_context(colors, (0.0, 0.01701), 9, top_y=0.9)

    labels = [
        plotter.actors[name].GetInput()
        for name in plotter.actors
        if name.startswith("ansys_legend_label")
    ]
    assert len(labels) == 10
    assert any(text.endswith(" Max") for text in labels)
    assert any(text.endswith(" Min") for text in labels)
    assert "ansys_legend_bands" in plotter.actors
    assert "ansys_legend_outline" in plotter.actors

    # The top label sits at the top of the bar. hit_test works in VTK
    # bottom-left-origin render-window pixels, not Qt coordinates.
    y_top = (0.9 - ansys_overlay.LEGEND_GAP_BELOW_HEADER) * 800
    x_label = (
        ansys_overlay.LEGEND_X
        + ansys_overlay.LEGEND_BAR_WIDTH
        + ansys_overlay.LEGEND_LABEL_GAP
    ) * 1000 + 5
    assert legend.hit_test(x_label, y_top) == "max"
    assert legend.hit_test(x_label, y_top - ansys_overlay.LEGEND_HEIGHT * 800) == "min"
    assert legend.hit_test(900, 400) is None

    legend.clear()
    assert plotter.actors == {}
    assert legend.hit_test(x_label, y_top) is None


def test_legend_thins_labels_when_bands_get_shorter_than_the_text():
    plotter = _StubPlotter()
    legend = ansys_overlay.AnsysLegend(plotter)
    colors = np.tile(np.array([[0, 0, 255]], dtype=np.uint8), (24, 1))
    legend.set_context(colors, (0.0, 1.0), 24, top_y=0.9)

    texts = [
        plotter.actors[name].GetInput()
        for name in plotter.actors
        if name.startswith("ansys_legend_label")
    ]
    assert len(texts) < 25
    # Whatever gets thinned out, the extremes always stay labelled.
    assert any(text.endswith(" Max") for text in texts)
    assert any(text.endswith(" Min") for text in texts)


def test_result_overlay_feeds_header_legend_and_compact_callouts():
    surface = _triangle_surface()
    window = _preview_window(surface)
    window.rst_surface_mesh["result_indices"] = np.array([2, 0, 1])
    candidates = pd.DataFrame(
        {
            "X": [0.0, 1.0],
            "Y": [0.0, 0.0],
            "Z": [0.0, 0.0],
            "Quality": [4.0, 2.0],
        }
    )

    main_window.MainWindow.display_strain_with_candidates(
        window,
        surface.points,
        np.array([0.5, 2.0, 5.0]),
        candidates,
        preserve_camera=False,
        contour_label="Set 2",
    )

    title, lines = window.result_header.infos[-1]
    assert title == "A: NS"
    assert lines[0] == "Equivalent (von Mises) Elastic Strain"
    assert lines[1] == "Type: Rosette - Signal-Noise Ratio"
    assert lines[2] == "Unit: microstrain"
    assert "Set 2" in lines

    colors, clim, n_bands, kwargs = window.result_legend.contexts[-1]
    assert n_bands == 9
    assert colors.shape == (9, 3)
    assert clim == (1.0, 3.0)
    # Data runs 0.5 to 5.0 against limits of 1.0 to 3.0, so both out-of-range
    # swatches belong on the legend.
    assert kwargs["clipped_below"] is True
    assert kwargs["clipped_above"] is True
    assert kwargs["below_color"] == (128, 128, 128)
    assert kwargs["above_color"] == (128, 0, 128)

    points, labels, font_size = window.result_annotations.point_sets[-1]
    assert labels == ["P1  Q 100%", "P2  Q 50%"]
    assert font_size == 11
    assert points.shape == (2, 3)


def test_display_clears_overlay_before_each_redraw():
    surface = _triangle_surface()
    window = _preview_window(surface)
    window.rst_surface_mesh["result_indices"] = np.array([2, 0, 1])
    for _ in range(3):
        main_window.MainWindow.display_strain_with_candidates(
            window,
            surface.points,
            np.array([1.0, 2.0, 3.0]),
            pd.DataFrame(),
            preserve_camera=True,
        )
    # Every redraw tears the overlay down first, so nothing accumulates.
    assert window.result_header.clear_count == 3
    assert window.result_annotations.clear_count == 3
    assert len(window.result_legend.contexts) == 3

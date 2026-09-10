# File: app/ui_tools.py
"""
Contains reusable UI tool classes that can be attached to a PyVista plotter.
"""
import time

import numpy as np
import pyvista as pv
import vtk

from .ansys_overlay import (
    ANNOTATION_BORDER, ANNOTATION_FILL, DEFAULT_ANNOTATION_FONT_SIZE,
)


PLACEMENT_COLUMNS = [
    "Gage", "Source", "Named_Selection", "Node",
    "Origin_X_mm", "Origin_Y_mm", "Origin_Z_mm",
    "Best_Strain", "Best_Angle_Deg", "Surface_Angle_Deg", "Manual_Override",
    "Normal_X", "Normal_Y", "Normal_Z",
    "Axis_X_X", "Axis_X_Y", "Axis_X_Z",
    "Axis_Y_X", "Axis_Y_Y", "Axis_Y_Z",
    "Direction_Pick_X_mm", "Direction_Pick_Y_mm", "Direction_Pick_Z_mm",
]


def _normalize_vector(vector, fallback=None):
    v = np.asarray(vector, dtype=float).reshape(3)
    norm = float(np.linalg.norm(v))
    if norm > 1.0e-12:
        return v / norm
    if fallback is None:
        fallback = (1.0, 0.0, 0.0)
    return np.asarray(fallback, dtype=float).reshape(3)


def project_to_tangent(vector, normal):
    normal = _normalize_vector(normal, (0.0, 0.0, 1.0))
    vector = np.asarray(vector, dtype=float).reshape(3)
    return vector - float(np.dot(vector, normal)) * normal


def tangent_reference_axis(normal):
    normal = _normalize_vector(normal, (0.0, 0.0, 1.0))
    ref = project_to_tangent((1.0, 0.0, 0.0), normal)
    if np.linalg.norm(ref) <= 1.0e-12:
        ref = project_to_tangent((0.0, 1.0, 0.0), normal)
    return _normalize_vector(ref, (1.0, 0.0, 0.0))


def surface_axes_from_angle(normal, angle_deg):
    normal = _normalize_vector(normal, (0.0, 0.0, 1.0))
    ref = tangent_reference_axis(normal)
    tangent_y = _normalize_vector(np.cross(normal, ref), (0.0, 1.0, 0.0))
    try:
        angle = float(angle_deg)
    except Exception:
        angle = 0.0
    if not np.isfinite(angle):
        angle = 0.0
    theta = np.radians(angle % 180.0)
    axis_x = _normalize_vector(np.cos(theta) * ref + np.sin(theta) * tangent_y, ref)
    axis_y = _normalize_vector(np.cross(normal, axis_x), tangent_y)
    return axis_x, axis_y, normal


def surface_angle_from_axis(normal, axis_x):
    normal = _normalize_vector(normal, (0.0, 0.0, 1.0))
    ref = tangent_reference_axis(normal)
    tangent_y = _normalize_vector(np.cross(normal, ref), (0.0, 1.0, 0.0))
    axis = _normalize_vector(project_to_tangent(axis_x, normal), ref)
    return float(np.degrees(np.arctan2(np.dot(axis, tangent_y), np.dot(axis, ref))) % 180.0)


def nearest_surface_normal(surface, point):
    if surface is None or int(getattr(surface, "n_points", 0)) == 0:
        return np.asarray((0.0, 0.0, 1.0), dtype=float)
    try:
        idx = int(surface.find_closest_point(np.asarray(point, dtype=float).reshape(3)))
    except Exception:
        idx = 0
    normals = surface.point_data.get("Normals")
    if normals is None or len(normals) == 0:
        return np.asarray((0.0, 0.0, 1.0), dtype=float)
    idx = max(0, min(idx, len(normals) - 1))
    return _normalize_vector(normals[idx], (0.0, 0.0, 1.0))


def _row_value(row, key, default=np.nan):
    try:
        value = row[key]
    except Exception:
        return default
    try:
        return float(value)
    except Exception:
        return default


def build_gage_placements(candidates_df, surface, named_selection=None, overrides=None):
    overrides = overrides or {}
    if candidates_df is None or getattr(candidates_df, "empty", True) or surface is None:
        return []

    records = []
    for idx, row in candidates_df.reset_index(drop=True).iterrows():
        origin = np.asarray([
            _row_value(row, "X", 0.0),
            _row_value(row, "Y", 0.0),
            _row_value(row, "Z", 0.0),
        ], dtype=float)
        best_angle = _row_value(row, "Best_Angle", 0.0)
        override = overrides.get(int(idx))
        direction_pick = np.asarray((np.nan, np.nan, np.nan), dtype=float)
        manual = False

        normal = nearest_surface_normal(surface, origin)
        axis_x, axis_y, normal = surface_axes_from_angle(normal, best_angle)
        surface_angle = best_angle % 180.0 if np.isfinite(best_angle) else 0.0

        if override:
            manual = True
            origin = np.asarray(override.get("origin", origin), dtype=float).reshape(3)
            direction_pick = np.asarray(
                override.get("direction_pick", direction_pick), dtype=float
            ).reshape(3)
            normal = nearest_surface_normal(surface, origin)
            projected = project_to_tangent(direction_pick - origin, normal)
            axis_x = _normalize_vector(projected, axis_x)
            axis_y = _normalize_vector(np.cross(normal, axis_x), axis_y)
            surface_angle = surface_angle_from_axis(normal, axis_x)

        try:
            node = int(row["Node"])
        except Exception:
            node = ""

        record = {
            "Gage": "P{0}".format(idx + 1),
            "Source": "candidate",
            "Named_Selection": named_selection or "",
            "Node": node,
            "Origin_X_mm": float(origin[0]),
            "Origin_Y_mm": float(origin[1]),
            "Origin_Z_mm": float(origin[2]),
            "Best_Strain": _row_value(row, "Best_Strain"),
            "Best_Angle_Deg": best_angle,
            "Surface_Angle_Deg": surface_angle,
            "Manual_Override": bool(manual),
            "Normal_X": float(normal[0]),
            "Normal_Y": float(normal[1]),
            "Normal_Z": float(normal[2]),
            "Axis_X_X": float(axis_x[0]),
            "Axis_X_Y": float(axis_x[1]),
            "Axis_X_Z": float(axis_x[2]),
            "Axis_Y_X": float(axis_y[0]),
            "Axis_Y_Y": float(axis_y[1]),
            "Axis_Y_Z": float(axis_y[2]),
            "Direction_Pick_X_mm": float(direction_pick[0]),
            "Direction_Pick_Y_mm": float(direction_pick[1]),
            "Direction_Pick_Z_mm": float(direction_pick[2]),
        }
        records.append(record)
    return records


class ContourHoverUI:
    """Cursor tooltip for interpolated values on one active contour actor."""

    def __init__(self, plotter: pv.Plotter):
        self.pl = plotter
        self.surface = None
        self.actor = None
        self.scalar_name = ""
        self.scalar_label = ""
        self.tooltip_actor = None
        self._tooltip_visible = False
        self._last_hover_time = 0.0
        self.picker = vtk.vtkCellPicker()
        self.picker.SetTolerance(0.005)
        self.picker.PickFromListOn()
        self.observer_id = self.pl.iren.add_observer(
            "MouseMoveEvent", self._on_mouse_move
        )

    def set_context(self, actor, surface, scalar_name, scalar_label):
        self.clear_context()
        if surface is None or scalar_name not in surface.point_data:
            raise ValueError("The active contour does not contain the requested point scalar.")
        self.actor = actor
        self.surface = surface
        self.scalar_name = str(scalar_name)
        self.scalar_label = str(scalar_label)
        self.picker.AddPickList(actor)
        self.tooltip_actor = self.pl.add_text(
            "",
            position=(0, 0),
            font_size=DEFAULT_ANNOTATION_FONT_SIZE,
            color="black",
            name="contour_hover_tooltip",
            render=False,
        )
        text_property = self.tooltip_actor.GetTextProperty()
        # PyVista doubles font_size when `position` is a tuple, so the real
        # size has to be set back afterwards -- otherwise this box renders at
        # twice the size of the callouts sitting next to it.
        text_property.SetFontSize(DEFAULT_ANNOTATION_FONT_SIZE)
        text_property.SetFontFamilyToArial()
        text_property.SetBold(False)
        text_property.SetShadow(False)
        text_property.SetBackgroundColor(*ANNOTATION_FILL)
        text_property.SetBackgroundOpacity(1.0)
        text_property.FrameOn()
        text_property.SetFrameColor(*ANNOTATION_BORDER)
        text_property.SetFrameWidth(1)
        self.tooltip_actor.SetPickable(False)
        self.tooltip_actor.SetVisibility(False)

    def clear_context(self):
        self.picker.InitializePickList()
        self.surface = None
        self.actor = None
        self.scalar_name = ""
        self.scalar_label = ""
        self._tooltip_visible = False
        if self.tooltip_actor is not None:
            try:
                self.pl.remove_actor(self.tooltip_actor, render=False)
            except Exception:
                pass
        self.tooltip_actor = None

    def close(self):
        self.clear_context()
        if self.observer_id is not None:
            try:
                self.pl.iren.remove_observer(self.observer_id)
            except Exception:
                pass
            self.observer_id = None

    @staticmethod
    def interpolate_scalar(surface, cell_id, point, scalar_name):
        if surface is None or scalar_name not in surface.point_data:
            return None
        if cell_id < 0 or cell_id >= int(surface.n_cells):
            return None

        cell = surface.GetCell(int(cell_id))
        point_count = int(cell.GetNumberOfPoints())
        if point_count == 0:
            return None

        closest_point = [0.0, 0.0, 0.0]
        sub_id = vtk.mutable(0)
        parametric_coords = [0.0, 0.0, 0.0]
        distance_squared = vtk.mutable(0.0)
        weights = [0.0] * point_count
        status = cell.EvaluatePosition(
            np.asarray(point, dtype=float).reshape(3),
            closest_point,
            sub_id,
            parametric_coords,
            distance_squared,
            weights,
        )
        if status < 0:
            return None

        point_ids = [cell.GetPointId(i) for i in range(point_count)]
        point_values = np.asarray(surface.point_data[scalar_name], dtype=float)
        value = float(np.dot(weights, point_values[point_ids]))
        return value if np.isfinite(value) else None

    def _on_mouse_move(self, interactor, _event):
        if self.surface is None or self.actor is None or self.tooltip_actor is None:
            return
        now = time.monotonic()
        if now - self._last_hover_time < 1.0 / 30.0:
            return
        self._last_hover_time = now

        try:
            x, y = interactor.GetEventPosition()
            picked = self.picker.Pick(x, y, 0, self.pl.renderer)
            cell_id = self.picker.GetCellId()
            point = np.asarray(self.picker.GetPickPosition(), dtype=float)
            value = (
                self.interpolate_scalar(
                    self.surface, cell_id, point, self.scalar_name
                )
                if picked
                else None
            )
            if value is None:
                if self._hide_tooltip():
                    interactor.GetRenderWindow().Render()
                return

            self.tooltip_actor.SetInput(
                "{0}: {1:.6g}\nX/Y/Z [mm]: {2:.6g}, {3:.6g}, {4:.6g}".format(
                    self.scalar_label, value, point[0], point[1], point[2]
                )
            )
            self.tooltip_actor.SetVisibility(True)
            self._tooltip_visible = True
            render_window = interactor.GetRenderWindow()
            width, height = render_window.GetSize()
            text_size = [0.0, 0.0]
            self.tooltip_actor.GetSize(self.pl.renderer, text_size)
            tooltip_x = x + 12
            tooltip_y = y + 12
            if tooltip_x + text_size[0] > width:
                tooltip_x = x - text_size[0] - 12
            if tooltip_y + text_size[1] > height:
                tooltip_y = y - text_size[1] - 12
            self.tooltip_actor.SetDisplayPosition(
                max(0, int(tooltip_x)), max(0, int(tooltip_y))
            )
            render_window.Render()
        except Exception:
            if self._hide_tooltip():
                try:
                    interactor.GetRenderWindow().Render()
                except Exception:
                    pass

    def _hide_tooltip(self):
        if self.tooltip_actor is None or not self._tooltip_visible:
            return False
        self.tooltip_actor.SetInput("")
        self.tooltip_actor.SetVisibility(False)
        self._tooltip_visible = False
        return True


class DistanceMeasureUI:
    """
    Click two surface points to measure distance.
    Toggle with checkbox or press 'm'. Clear with 'c'.
    """

    def __init__(self, plotter: pv.Plotter, units: str = ""):
        self.pl = plotter
        self.units = units
        self.enabled = False

        # State
        self.picks = []
        self.actors_points = []
        self.actor_line = None
        self.actor_labels = []
        self.actor_text = None

        # Hotkeys (zero-arg callbacks required)
        self.pl.add_key_event("m", lambda: self._on_key_toggle())
        self.pl.add_key_event("c", lambda: self.clear())

        # Helper hint
        self._hint = self.pl.add_text(
            "Distance Measurement: off  [M=toggle, C=clear]\nWhen on: click two points on the surface.",
            position="lower_left",
            font_size=6,
        )

    # ---- Public helpers -------------------------------------------------

    def set_units(self, units: str):
        self.units = units
        if len(self.picks) == 2:
            self._update_overlays()

    def enable(self):
        if self.enabled:
            return
        self.enabled = True
        # New API (PyVista >= 0.43): use_picker replaces use_mesh
        try:
            self.pl.enable_point_picking(
                callback=self._on_pick,    # will accept (point, picker)
                use_picker=True,           # snaps using VTK picker
                picker="point",             # snap to surface/cells; try "point" for vertex snap
                show_message=True,
                left_clicking=True,
            )
        except TypeError:
            # Old API fallback
            self.pl.enable_point_picking(
                callback=self._on_pick,    # will accept (point)
                use_mesh=True,             # deprecated, but kept for older versions
                show_message=True,
                left_clicking=True,
            )
        self._update_hint()

    def disable(self):
        if not self.enabled:
            return
        self.enabled = False
        self.pl.disable_picking()
        self._update_hint()

    def clear(self):
        for a in self.actors_points:
            try:
                self.pl.remove_actor(a)
            except Exception:
                pass
        self.actors_points.clear()

        if self.actor_line is not None:
            try:
                self.pl.remove_actor(self.actor_line)
            except Exception:
                pass
            self.actor_line = None

        for a in self.actor_labels:
            try:
                self.pl.remove_actor(a)
            except Exception:
                pass
        self.actor_labels.clear()

        if self.actor_text is not None:
            try:
                self.pl.remove_actor(self.actor_text)
            except Exception:
                pass
            self.actor_text = None

        self.picks.clear()
        self.pl.render()

    # ---- Internal callbacks --------------------------------------------

    def _on_pick(self, point, *_) -> None:
        """Accepts (point) or (point, picker) from PyVista."""
        if not self.enabled:
            return
        if point is None:
            return
        p = np.asarray(point, dtype=float).reshape(3)
        self.picks.append(p)
        if len(self.picks) > 2:
            self.picks = self.picks[-2:]
        self._update_overlays()

    def _on_key_toggle(self):
        new_state = not self.enabled
        if new_state:
            self.enable()
        else:
            self.disable()

    # ---- Drawing / overlays --------------------------------------------

    def _update_overlays(self):
        old = list(self.picks)
        self.clear()
        self.picks = old

        balls, labels = [], []
        color_a = 'cyan'
        color_b = 'magenta'
        if len(self.picks) >= 1:
            balls.append(self._add_point_sphere(self.picks[0]))
            labels.append(self._add_point_label(self.picks[0], "A"))
        if len(self.picks) == 2:
            balls.append(self._add_point_sphere(self.picks[1]))
            labels.append(self._add_point_label(self.picks[1], "B"))
            self._add_line_and_text(self.picks[0], self.picks[1])

        self.actors_points = balls
        self.actor_labels = labels
        self.pl.render()

    def _scene_diag(self):
        try:
            b = self.pl.bounds
            if b is None:
                return None
            return np.linalg.norm([b[1]-b[0], b[3]-b[2], b[5]-b[4]])
        except Exception:
            return None

    def _add_point_sphere(self, p, radius=0.02):
        diag = self._scene_diag()
        if diag is not None:
            radius = max(diag, 1e-9) * 0.01  # 1% scene diagonal
        sph = pv.Sphere(radius=radius, center=p, theta_resolution=24, phi_resolution=24)
        return self.pl.add_mesh(sph, style="surface", opacity=0.8, pickable=False, color='red')

    def _add_point_label(self, p, text):
        return self.pl.add_point_labels(
            [p], [text], point_size=0, font_size=DEFAULT_ANNOTATION_FONT_SIZE,
            shape=None, show_points=False, pickable=False, bold=False)

    def _add_line_and_text(self, p1, p2):
        line = pv.Line(p1, p2, resolution=1)
        self.actor_line = self.pl.add_mesh(line, line_width=3, pickable=False, color='red')

        d = float(np.linalg.norm(np.asarray(p2) - np.asarray(p1)))
        mid = 0.5 * (np.asarray(p1) + np.asarray(p2))
        label = f"{d:.6g} {self.units}".strip()
        self.actor_text = self.pl.add_point_labels(
            points=[mid],
            labels=[label],
            font_size=DEFAULT_ANNOTATION_FONT_SIZE + 1,
            shape='rect',
            shape_color=ANNOTATION_FILL,
            shape_opacity=1.0,
            point_size=0,
            show_points=False,
            pickable=False,
            bold=False,
            shadow=False,
            margin=2,
            always_visible=True
        )

    def _update_hint(self):
        txt = (
            "Distance Measurement: off  [M=toggle, C=clear]\nWhen on: click two points on the surface."
            if self.enabled
            else "Distance Measurement: on  [M=toggle, C=clear]\nWhen on: click two points on the surface."
        )
        if self._hint is not None:
            try:
                self.pl.remove_actor(self._hint)
            except Exception:
                pass
        self._hint = self.pl.add_text(txt, position="lower_left", font_size=6)


class GagePlacementUI:
    """Candidate-first surface gage placement overlays and two-click overrides."""

    def __init__(self, plotter: pv.Plotter, on_changed=None):
        self.pl = plotter
        self.on_changed = on_changed
        self.surface = None
        self.candidates_df = None
        self.named_selection = ""
        self.overrides = {}
        self.active_index = 0
        self.override_enabled = False
        self.show_normals = True
        self.show_axes = True
        self._pending_origin = None
        self._actors = []

    def set_context(self, surface_info, candidates_df, named_selection=None):
        self.surface = (surface_info or {}).get("surface") if surface_info else None
        self.candidates_df = candidates_df.copy() if candidates_df is not None else None
        self.named_selection = named_selection or ""
        self.active_index = 0
        self._pending_origin = None
        self.overrides.clear()
        self.draw()

    def set_active_index(self, index):
        try:
            self.active_index = max(0, int(index))
        except Exception:
            self.active_index = 0

    def set_visibility(self, show_normals=True, show_axes=True):
        self.show_normals = bool(show_normals)
        self.show_axes = bool(show_axes)
        self.draw()

    def set_override_enabled(self, enabled):
        enabled = bool(enabled)
        if enabled == self.override_enabled:
            return
        self.override_enabled = enabled
        self._pending_origin = None
        if enabled:
            try:
                self.pl.enable_point_picking(
                    callback=self._on_pick,
                    use_picker=True,
                    picker="point",
                    show_message=True,
                    left_clicking=True,
                )
            except TypeError:
                self.pl.enable_point_picking(
                    callback=self._on_pick,
                    use_mesh=True,
                    show_message=True,
                    left_clicking=True,
                )
        else:
            self.pl.disable_picking()

    def clear_overrides(self):
        self.overrides.clear()
        self._pending_origin = None
        self.draw()
        self._notify_changed()

    def placement_records(self):
        return build_gage_placements(
            self.candidates_df, self.surface, self.named_selection, self.overrides
        )

    def clear_actors(self):
        for actor in self._actors:
            try:
                self.pl.remove_actor(actor)
            except Exception:
                pass
        self._actors.clear()

    def draw(self):
        self.clear_actors()
        records = self.placement_records()
        if not records:
            try:
                self.pl.render()
            except Exception:
                pass
            return
        diag = self._scene_diag()
        scale = max(diag, 1.0e-9) * 0.045
        for i, record in enumerate(records):
            origin = np.asarray([
                record["Origin_X_mm"], record["Origin_Y_mm"], record["Origin_Z_mm"]
            ], dtype=float)
            normal = np.asarray([
                record["Normal_X"], record["Normal_Y"], record["Normal_Z"]
            ], dtype=float)
            axis_x = np.asarray([
                record["Axis_X_X"], record["Axis_X_Y"], record["Axis_X_Z"]
            ], dtype=float)
            axis_y = np.asarray([
                record["Axis_Y_X"], record["Axis_Y_Y"], record["Axis_Y_Z"]
            ], dtype=float)
            if self.show_normals:
                self._add_arrow(origin, normal, scale, "dodgerblue")
            if self.show_axes:
                width_scale = 1.35 if i == self.active_index else 1.0
                self._add_arrow(origin, axis_x, scale * width_scale, "red")
                self._add_arrow(origin, axis_y, scale * 0.75 * width_scale, "limegreen")
            if record["Manual_Override"] and np.isfinite(record["Direction_Pick_X_mm"]):
                pick = np.asarray([
                    record["Direction_Pick_X_mm"],
                    record["Direction_Pick_Y_mm"],
                    record["Direction_Pick_Z_mm"],
                ], dtype=float)
                try:
                    self._actors.append(
                        self.pl.add_mesh(
                            pv.Line(origin, pick, resolution=1),
                            color="orange",
                            line_width=3,
                            pickable=False,
                        )
                    )
                except Exception:
                    pass
        try:
            self.pl.render()
        except Exception:
            pass

    def _on_pick(self, point, *_):
        if not self.override_enabled or self.candidates_df is None:
            return
        if point is None:
            return
        p = np.asarray(point, dtype=float).reshape(3)
        if self._pending_origin is None:
            self._pending_origin = p
            self.active_index = self._nearest_candidate_index(p)
            return
        self.overrides[int(self.active_index)] = {
            "origin": self._pending_origin,
            "direction_pick": p,
        }
        self._pending_origin = None
        self.draw()
        self._notify_changed()

    def _nearest_candidate_index(self, point):
        if self.candidates_df is None or getattr(self.candidates_df, "empty", True):
            return 0
        try:
            coords = self.candidates_df[["X", "Y", "Z"]].to_numpy(dtype=float)
            distances = np.linalg.norm(coords - np.asarray(point, dtype=float).reshape(1, 3), axis=1)
            return int(np.argmin(distances))
        except Exception:
            return int(self.active_index)

    def _scene_diag(self):
        try:
            bounds = self.pl.bounds
            if bounds is None:
                return 1.0
            return float(np.linalg.norm([
                bounds[1] - bounds[0],
                bounds[3] - bounds[2],
                bounds[5] - bounds[4],
            ]))
        except Exception:
            return 1.0

    def _add_arrow(self, origin, direction, scale, color):
        try:
            arrow = pv.Arrow(
                start=np.asarray(origin, dtype=float),
                direction=_normalize_vector(direction, (1.0, 0.0, 0.0)),
                scale=float(scale),
            )
            self._actors.append(
                self.pl.add_mesh(arrow, color=color, pickable=False)
            )
        except Exception:
            pass

    def _notify_changed(self):
        if self.on_changed is not None:
            try:
                self.on_changed()
            except Exception:
                pass

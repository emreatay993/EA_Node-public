"""ANSYS-Mechanical-style overlay actors for the strain-gage viewport.

Mechanical draws its results with a fixed vocabulary that engineers read at a
glance: an information block in the top-left corner, a vertical banded colour
legend directly beneath it whose extreme labels are suffixed ``Max`` / ``Min``,
and small pale callouts joined to the geometry by thin leader lines. PyVista's
stock scalar bar cannot reproduce any of that -- ``vtkScalarBarActor`` applies a
single printf format to every label, so ``1.3006e-5 Max`` on top and ``0 Min``
on the bottom is impossible -- so the legend here is built from plain VTK 2D
actors instead.

Four cooperating pieces, each attached to one PyVista plotter:

``AnsysResultHeader``        the top-left information block
``AnsysLegend``             vertical banded legend with boundary labels
``AnsysLegendInteractor``   double-click a value to edit it, right-click for a menu
``AnsysAnnotations``        draggable pale callouts with leader lines

The controller rebuilds all of them on every redraw, because
``MainWindow.clear_visualization`` calls ``plotter.clear()`` between frames.

Design note: the legend renders the *mesh's own* lookup table (read back from
``actor.mapper.lookup_table``) rather than re-deriving colours from a colormap
name. VTK's discretisation and PyVista's ``n_colors`` resampling have their own
sampling convention, so a recomputed legend can sit half a band away from what
the surface actually shows -- an invisible bug that would quietly misreport
strain. Reading the table back makes disagreement structurally impossible.
"""

import math
import time

import numpy as np
import vtk

from PyQt6.QtCore import QTimer
from PyQt6.QtGui import QCursor
from PyQt6.QtWidgets import QInputDialog, QMenu

# --- Appearance -------------------------------------------------------------
HEADER_FONT_SIZE = 13
LEGEND_FONT_SIZE = 12
DEFAULT_ANNOTATION_FONT_SIZE = 11
DEFAULT_BANDS = 9
MIN_BANDS = 2
MAX_BANDS = 24

TEXT_COLOR = (0.0, 0.0, 0.0)
OUTLINE_COLOR = (0.0, 0.0, 0.0)
ANNOTATION_FILL = (0.72, 0.89, 0.96)
ANNOTATION_BORDER = (0.10, 0.15, 0.35)
LEADER_COLOR = (0.85, 0.0, 0.65)

# Mechanical's default contour ramp: saturated blue at the bottom through to
# saturated red at the top. Matplotlib's `jet` bottoms and tops out in dark
# navy and dark maroon, which reads visibly different from a Mechanical plot.
ANSYS_RAINBOW_COLORS = (
    "#0000FF", "#0080FF", "#00FFFF", "#00FF80", "#00FF00",
    "#80FF00", "#FFFF00", "#FF8000", "#FF0000",
)
_RAINBOW_CMAP = None

# --- Normalised-viewport geometry of the top-left block ---------------------
HEADER_X = 0.012
HEADER_TOP_Y = 0.985
LEGEND_X = 0.015
LEGEND_BAR_WIDTH = 0.026
LEGEND_LABEL_GAP = 0.006
LEGEND_HEIGHT = 0.42
LEGEND_GAP_BELOW_HEADER = 0.025
LEGEND_SWATCH_GAP = 0.012
LEGEND_SWATCH_HEIGHT = 0.020

# --- Interaction ------------------------------------------------------------
DOUBLE_CLICK_SECONDS = 0.4
DOUBLE_CLICK_RADIUS_PX = 5
LEGEND_OBSERVER_PRIORITY = 10.0
ANNOTATION_OBSERVER_PRIORITY = 9.0
BAND_MENU_CHOICES = (3, 5, 9, 12, 18, 24)

# Cycled so neighbouring callouts do not stack on top of each other.
ANNOTATION_OFFSETS = ((40, 28), (40, -34), (-104, 28), (-104, -34))
ANNOTATION_PADDING = 3

# Rough Arial advance/line metrics, used to size the caption box that the
# leader line terminates on. Deliberately a slight under-estimate so the leader
# always ends *inside* the opaque text background rather than short of it,
# which would show as a visible gap.
_CHAR_ADVANCE = 0.58
_LINE_HEIGHT = 1.35
_BOX_SHRINK = 0.95


def ansys_rainbow_colormap():
    """Colormap matching the default Mechanical contour ramp.

    Built with ``from_list`` rather than a ``ListedColormap`` so any band
    count interpolates smoothly through the ramp -- a listed map resampled
    above nine colours would duplicate entries and pair the bands up.
    """
    global _RAINBOW_CMAP
    if _RAINBOW_CMAP is None:
        from matplotlib.colors import LinearSegmentedColormap

        _RAINBOW_CMAP = LinearSegmentedColormap.from_list(
            "ansys_rainbow", list(ANSYS_RAINBOW_COLORS), N=256
        )
    return _RAINBOW_CMAP


def format_ansys_number(value, precision=5):
    """Format ``value`` the way the Mechanical legend does.

    Five significant digits, and the exponent's leading zero stripped so VTK
    renders ``1.3006e-5`` rather than Python's ``1.3006e-05``. Exact zero is
    rendered as a bare ``0``, matching the ``0 Min`` label.
    """
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    if not np.isfinite(number):
        return str(number)
    if number == 0.0:
        return "0"
    text = "{0:.{1}g}".format(number, int(precision))
    if "e" in text:
        mantissa, _, exponent = text.partition("e")
        sign = "-" if exponent.startswith("-") else ""
        digits = exponent.lstrip("+-").lstrip("0") or "0"
        text = "{0}e{1}{2}".format(mantissa, sign, digits)
    return text


def band_boundaries(vmin, vmax, n_bands):
    """Return the ``n_bands + 1`` values printed against the legend bands.

    Mechanical labels band *boundaries*, not band centres: nine bands carry ten
    numbers whose step is ``(max - min) / 9``. The endpoints are forced to the
    requested limits so the ``Max``/``Min`` labels are exact.
    """
    count = max(1, int(n_bands))
    low = float(vmin)
    high = float(vmax)
    if not np.isfinite(low) or not np.isfinite(high):
        low, high = 0.0, 1.0
    if high <= low:
        high = low + 1.0
    values = [low + (high - low) * index / count for index in range(count + 1)]
    values[0] = low
    values[-1] = high
    return values


def lookup_table_band_colors(lookup_table, n_bands):
    """Sample ``n_bands`` RGB triplets from a rendered lookup table."""
    count = max(1, int(n_bands))
    values = None
    try:
        values = np.asarray(lookup_table.values, dtype=np.uint8)
    except Exception:
        values = None
    if values is None or values.ndim != 2 or values.shape[0] == 0:
        try:
            size = int(lookup_table.GetNumberOfTableValues())
            raw = [lookup_table.GetTableValue(index) for index in range(size)]
            values = (np.asarray(raw, dtype=float) * 255.0).astype(np.uint8)
        except Exception:
            values = None
    if values is None or values.ndim != 2 or values.shape[0] == 0:
        return np.full((count, 3), 128, dtype=np.uint8)
    if values.shape[0] == count:
        rgb = values[:, :3]
    else:
        positions = (np.arange(count) + 0.5) / count * values.shape[0]
        index = np.clip(positions.astype(int), 0, values.shape[0] - 1)
        rgb = values[index, :3]
    return np.ascontiguousarray(rgb, dtype=np.uint8)


def lookup_table_range_colors(lookup_table):
    """Return the ``(below, above)`` out-of-range RGB triplets, or ``None`` each."""

    def _read(use_getter, color_getter):
        try:
            if not bool(use_getter()):
                return None
            color = color_getter()
        except Exception:
            return None
        return tuple(int(round(float(channel) * 255.0)) for channel in color[:3])

    below = _read(lookup_table.GetUseBelowRangeColor, lookup_table.GetBelowRangeColor)
    above = _read(lookup_table.GetUseAboveRangeColor, lookup_table.GetAboveRangeColor)
    return below, above


def _text_extent_px(text, font_size):
    """Estimate the pixel footprint of ``text`` without needing a render pass."""
    lines = str(text).split("\n") or [""]
    columns = max((len(line) for line in lines), default=0)
    return columns * font_size * _CHAR_ADVANCE, len(lines) * font_size * _LINE_HEIGHT


def _make_text_actor(text, font_size, bold=False, vertical="centered"):
    actor = vtk.vtkTextActor()
    actor.SetInput(str(text))
    actor.SetTextScaleModeToNone()
    prop = actor.GetTextProperty()
    prop.SetFontFamilyToArial()
    prop.SetFontSize(int(font_size))
    prop.SetColor(*TEXT_COLOR)
    prop.SetBold(bool(bold))
    prop.SetItalic(False)
    prop.SetShadow(False)
    prop.SetJustificationToLeft()
    if vertical == "top":
        prop.SetVerticalJustificationToTop()
    else:
        prop.SetVerticalJustificationToCentered()
    actor.GetPositionCoordinate().SetCoordinateSystemToNormalizedViewport()
    return actor


class _PlotterOverlay:
    """Shared plumbing: named 2D actors that survive ``plotter.clear()`` cleanly."""

    def __init__(self, plotter):
        self.pl = plotter
        self._actors = []

    def _add(self, actor, name):
        if actor is None:
            return None
        try:
            self.pl.add_actor(
                actor, name=name, render=False, reset_camera=False, pickable=False
            )
        except Exception:
            return None
        self._actors.append((name, actor))
        return actor

    def clear(self):
        for name, actor in self._actors:
            try:
                self.pl.remove_actor(actor, render=False)
            except Exception:
                try:
                    self.pl.remove_actor(name, render=False)
                except Exception:
                    pass
        self._actors = []

    def _window_size(self):
        try:
            size = self.pl.render_window.GetSize()
            width, height = int(size[0]), int(size[1])
        except Exception:
            width = height = 0
        return (width or 1200, height or 800)


class AnsysResultHeader(_PlotterOverlay):
    """The bold analysis line plus the ``Type:`` / ``Unit:`` / ``Time:`` block.

    Each line is its own ``vtkTextActor`` so line spacing is exact and does not
    depend on measuring a rendered multi-line string. ``SetTextScaleModeToNone``
    keeps the block at a fixed pixel size -- ``plotter.add_text('upper_left')``
    would instead build a ``CornerAnnotation`` that rescales with the window.
    """

    def __init__(self, plotter, font_size=HEADER_FONT_SIZE):
        super().__init__(plotter)
        self.font_size = int(font_size)
        self._line_count = 0

    def set_info(self, title, lines):
        self.clear()
        self._line_count = 0
        title = str(title or "").strip()
        body = [str(line).strip() for line in (lines or []) if str(line).strip()]
        if not title and not body:
            return
        step = self._line_height()
        y = HEADER_TOP_Y
        if title:
            actor = _make_text_actor(title, self.font_size, bold=True, vertical="top")
            actor.SetPosition(HEADER_X, y)
            self._add(actor, "ansys_header_title")
            y -= step
        for index, line in enumerate(body):
            actor = _make_text_actor(line, self.font_size, vertical="top")
            actor.SetPosition(HEADER_X, y)
            self._add(actor, "ansys_header_line_{0}".format(index))
            y -= step
        self._line_count = (1 if title else 0) + len(body)

    def bottom_y(self):
        """Normalised y of the lower edge, so the legend can dock underneath."""
        return HEADER_TOP_Y - self._line_count * self._line_height()

    def _line_height(self):
        return (self.font_size * 1.45) / float(self._window_size()[1])


class AnsysLegend(_PlotterOverlay):
    """Vertical banded colour legend with ``Max`` / ``Min`` boundary labels."""

    def __init__(self, plotter, font_size=LEGEND_FONT_SIZE):
        super().__init__(plotter)
        self.font_size = int(font_size)
        self._legend_rect = None
        self._max_rect = None
        self._min_rect = None

    def clear(self):
        super().clear()
        self._legend_rect = self._max_rect = self._min_rect = None

    def set_context(
        self,
        colors,
        clim,
        n_bands,
        top_y=None,
        below_color=None,
        above_color=None,
        clipped_below=False,
        clipped_above=False,
    ):
        self.clear()
        colors = np.asarray(colors, dtype=np.uint8).reshape(-1, 3)
        count = max(1, int(n_bands))
        if colors.shape[0] < count:
            pad = np.repeat(colors[-1:], count - colors.shape[0], axis=0)
            colors = np.vstack([colors, pad])
        colors = colors[:count]

        y_top = (HEADER_TOP_Y if top_y is None else float(top_y)) - LEGEND_GAP_BELOW_HEADER
        y_bottom = y_top - LEGEND_HEIGHT
        band_height = (y_top - y_bottom) / count
        x0 = LEGEND_X
        x1 = LEGEND_X + LEGEND_BAR_WIDTH

        quads = []
        for index in range(count):
            low = y_bottom + index * band_height
            quads.append(((x0, low, x1, low + band_height), tuple(colors[index])))
        if clipped_above and above_color is not None:
            low = y_top + LEGEND_SWATCH_GAP
            quads.append(((x0, low, x1, low + LEGEND_SWATCH_HEIGHT), tuple(above_color)))
        if clipped_below and below_color is not None:
            high = y_bottom - LEGEND_SWATCH_GAP
            quads.append(((x0, high - LEGEND_SWATCH_HEIGHT, x1, high), tuple(below_color)))

        self._add(self._build_band_actor(quads), "ansys_legend_bands")
        self._add(self._build_outline_actor(quads), "ansys_legend_outline")

        values = band_boundaries(clim[0], clim[1], count)
        label_x = x1 + LEGEND_LABEL_GAP
        width_px, height_px = self._window_size()
        indices = self._label_indices(count, band_height * height_px)
        for order, index in enumerate(indices):
            text = format_ansys_number(values[index])
            if index == count:
                text += " Max"
            elif index == 0:
                text += " Min"
            y = y_bottom + index * band_height
            actor = _make_text_actor(text, self.font_size)
            actor.SetPosition(label_x, y)
            self._add(actor, "ansys_legend_label_{0}".format(order))
            rect = self._label_rect(label_x, y, text, width_px, height_px)
            if index == count:
                self._max_rect = rect
            elif index == 0:
                self._min_rect = rect

        block_bottom = min(quad[0][1] for quad in quads)
        block_top = max(quad[0][3] for quad in quads)
        label_width = max(0.09, 12 * self.font_size * _CHAR_ADVANCE / width_px)
        self._legend_rect = (x0, block_bottom, label_x + label_width, block_top)

    def hit_test(self, x_px, y_px):
        """Classify a render-window pixel as ``max`` / ``min`` / ``legend`` / ``None``.

        Rects are stored normalised and converted on demand, so a window resize
        needs no observer to keep them correct.
        """
        if self._legend_rect is None:
            return None
        width, height = self._window_size()
        point = (float(x_px) / width, float(y_px) / height)
        if self._inside(self._max_rect, point):
            return "max"
        if self._inside(self._min_rect, point):
            return "min"
        if self._inside(self._legend_rect, point):
            return "legend"
        return None

    @staticmethod
    def _inside(rect, point):
        if rect is None:
            return False
        return rect[0] <= point[0] <= rect[2] and rect[1] <= point[1] <= rect[3]

    def _label_indices(self, count, band_px):
        """Thin the boundary labels out when bands get shorter than the text."""
        needed = self.font_size * 1.5
        if band_px >= needed:
            step = 1
        else:
            step = max(1, int(math.ceil(needed / max(band_px, 1.0))))
        indices = list(range(count, -1, -step))
        if indices[-1] != 0:
            if indices[-1] < step:
                indices[-1] = 0
            else:
                indices.append(0)
        return sorted(set(indices))

    def _label_rect(self, x, y, text, width_px, height_px):
        text_width, text_height = _text_extent_px(text, self.font_size)
        half_height = max(text_height, self.font_size) / 2.0 / height_px
        return (x, y - half_height, x + max(text_width / width_px, 0.05), y + half_height)

    @staticmethod
    def _build_band_actor(quads):
        points = vtk.vtkPoints()
        polys = vtk.vtkCellArray()
        colors = vtk.vtkUnsignedCharArray()
        colors.SetNumberOfComponents(3)
        colors.SetName("BandColors")
        for (x0, y0, x1, y1), rgb in quads:
            base = points.GetNumberOfPoints()
            points.InsertNextPoint(x0, y0, 0.0)
            points.InsertNextPoint(x1, y0, 0.0)
            points.InsertNextPoint(x1, y1, 0.0)
            points.InsertNextPoint(x0, y1, 0.0)
            polys.InsertNextCell(4)
            for offset in range(4):
                polys.InsertCellPoint(base + offset)
            colors.InsertNextTuple3(int(rgb[0]), int(rgb[1]), int(rgb[2]))
        poly_data = vtk.vtkPolyData()
        poly_data.SetPoints(points)
        poly_data.SetPolys(polys)
        poly_data.GetCellData().SetScalars(colors)

        coordinate = vtk.vtkCoordinate()
        coordinate.SetCoordinateSystemToNormalizedViewport()
        mapper = vtk.vtkPolyDataMapper2D()
        mapper.SetInputData(poly_data)
        mapper.SetTransformCoordinate(coordinate)
        mapper.SetScalarModeToUseCellData()
        mapper.SetColorModeToDirectScalars()
        mapper.ScalarVisibilityOn()
        actor = vtk.vtkActor2D()
        actor.SetMapper(mapper)
        return actor

    @staticmethod
    def _build_outline_actor(quads):
        points = vtk.vtkPoints()
        lines = vtk.vtkCellArray()
        for (x0, y0, x1, y1), _rgb in quads:
            base = points.GetNumberOfPoints()
            points.InsertNextPoint(x0, y0, 0.0)
            points.InsertNextPoint(x1, y0, 0.0)
            points.InsertNextPoint(x1, y1, 0.0)
            points.InsertNextPoint(x0, y1, 0.0)
            lines.InsertNextCell(5)
            for offset in (0, 1, 2, 3, 0):
                lines.InsertCellPoint(base + offset)
        poly_data = vtk.vtkPolyData()
        poly_data.SetPoints(points)
        poly_data.SetLines(lines)

        coordinate = vtk.vtkCoordinate()
        coordinate.SetCoordinateSystemToNormalizedViewport()
        mapper = vtk.vtkPolyDataMapper2D()
        mapper.SetInputData(poly_data)
        mapper.SetTransformCoordinate(coordinate)
        mapper.ScalarVisibilityOff()
        actor = vtk.vtkActor2D()
        actor.SetMapper(mapper)
        actor.GetProperty().SetColor(*OUTLINE_COLOR)
        actor.GetProperty().SetLineWidth(1.0)
        return actor


class AnsysLegendInteractor:
    """Mechanical-style legend behaviour: edit a value, or open a context menu.

    Two constraints shaped this. First, ``pyvistaqt``'s vendored interactor has
    no ``mouseDoubleClickEvent``, so VTK never emits ``LeftButtonDoubleClickEvent``
    and the double click has to be reconstructed from press timestamps. Second,
    ``plotter.iren.add_observer`` takes no priority argument, so the observers
    are registered on the raw ``vtkRenderWindowInteractor`` with an explicit
    priority and abort the event when the click lands on the legend -- otherwise
    the click would also rotate the camera or fire the gage-direction picker.

    The VTK event position is used rather than Qt's: Qt is top-left origin and
    device-pixel scaled, VTK is bottom-left render-window pixels, which is the
    space the legend rects already live in.
    """

    def __init__(
        self,
        plotter,
        legend,
        on_get_limits=None,
        on_set_limits=None,
        on_set_bands=None,
        on_reset_range=None,
    ):
        self.pl = plotter
        self.legend = legend
        self.on_get_limits = on_get_limits
        self.on_set_limits = on_set_limits
        self.on_set_bands = on_set_bands
        self.on_reset_range = on_reset_range
        self._last_click = None
        self._left_observer = None
        self._right_observer = None
        self._interactor = None
        try:
            self._interactor = plotter.iren.interactor
        except Exception:
            self._interactor = None
        if self._interactor is None:
            return
        self._left_observer = self._interactor.AddObserver(
            "LeftButtonPressEvent", self._on_left_press, LEGEND_OBSERVER_PRIORITY
        )
        self._right_observer = self._interactor.AddObserver(
            "RightButtonPressEvent", self._on_right_press, LEGEND_OBSERVER_PRIORITY
        )

    def close(self):
        if self._interactor is None:
            return
        for observer in (self._left_observer, self._right_observer):
            if observer is not None:
                try:
                    self._interactor.RemoveObserver(observer)
                except Exception:
                    pass
        self._left_observer = self._right_observer = None

    def _abort(self, caller, observer):
        try:
            command = caller.GetCommand(observer)
            if command is not None:
                command.SetAbortFlag(1)
        except Exception:
            pass

    def _on_left_press(self, caller, _event):
        try:
            x, y = caller.GetEventPosition()
        except Exception:
            return
        now = time.monotonic()
        previous = self._last_click
        self._last_click = (now, x, y)

        target = self.legend.hit_test(x, y)
        if target is None:
            return
        # Swallow every click on the legend so it never rotates the camera or
        # reaches the point pickers used by the distance / override tools.
        self._abort(caller, self._left_observer)

        if previous is None or now - previous[0] > DOUBLE_CLICK_SECONDS:
            return
        if (
            abs(x - previous[1]) > DOUBLE_CLICK_RADIUS_PX
            or abs(y - previous[2]) > DOUBLE_CLICK_RADIUS_PX
        ):
            return
        self._last_click = None
        if target in ("max", "min"):
            # Deferred: a modal dialog opened inside a VTK callback re-enters
            # the interactor while it is still dispatching the press.
            QTimer.singleShot(0, lambda bound=target: self._prompt_limit(bound))

    def _on_right_press(self, caller, _event):
        try:
            x, y = caller.GetEventPosition()
        except Exception:
            return
        if self.legend.hit_test(x, y) is None:
            return
        self._abort(caller, self._right_observer)
        QTimer.singleShot(0, self._show_menu)

    def _prompt_limit(self, bound):
        if self.on_set_limits is None or self.on_get_limits is None:
            return
        current = self.on_get_limits()
        if current is None:
            return
        low, high = float(current[0]), float(current[1])
        title = "Upper Limit" if bound == "max" else "Lower Limit"
        value, accepted = QInputDialog.getDouble(
            self._parent_widget(),
            "Legend " + title,
            title + ":",
            float(high if bound == "max" else low),
            -1.0e30,
            1.0e30,
            6,
        )
        if not accepted:
            return
        if bound == "max":
            self.on_set_limits(low, float(value))
        else:
            self.on_set_limits(float(value), high)

    def _show_menu(self):
        menu = QMenu(self._parent_widget())
        bands_menu = menu.addMenu("Number of bands")
        for count in BAND_MENU_CHOICES:
            action = bands_menu.addAction(str(count))
            action.triggered.connect(
                lambda _checked=False, value=count: self._apply_bands(value)
            )
        menu.addSeparator()
        reset_action = menu.addAction("Reset to data range")
        reset_action.triggered.connect(lambda _checked=False: self._apply_reset())
        upper_action = menu.addAction("Set upper limit...")
        upper_action.triggered.connect(lambda _checked=False: self._prompt_limit("max"))
        lower_action = menu.addAction("Set lower limit...")
        lower_action.triggered.connect(lambda _checked=False: self._prompt_limit("min"))
        menu.exec(QCursor.pos())

    def _apply_bands(self, count):
        if self.on_set_bands is not None:
            self.on_set_bands(int(count))

    def _apply_reset(self):
        if self.on_reset_range is not None:
            self.on_reset_range()

    def _parent_widget(self):
        widget = getattr(self.pl, "interactor", None)
        return widget if widget is not None else None


class AnsysAnnotations:
    """Small pale callouts joined to their candidate point by a leader line.

    ``vtkCaptionActor2D`` is Mechanical's callout in VTK form: a text box held
    at a fixed *display-space* offset from a 3D attachment point, with a leader
    line between the two. Because the offset is relative to the attachment
    point, the box tracks the geometry as the camera moves, which is what
    Mechanical does.

    Dragging is implemented directly rather than with ``vtkCaptionWidget``.
    The widget re-anchors the caption to a fixed *normalised viewport* position
    and clears the reference coordinate, so a dragged label would stop following
    its point on rotation. Editing the display offset instead keeps the label
    point-anchored and draggable at the same time -- and avoids the widget
    lifecycle entirely, since widgets are owned by the interactor and would
    survive the ``plotter.clear()`` that happens on every redraw.
    """

    def __init__(self, plotter, font_size=DEFAULT_ANNOTATION_FONT_SIZE, draggable=True):
        self.pl = plotter
        self.font_size = int(font_size)
        self.draggable = bool(draggable)
        self._entries = []
        self._offsets = {}
        self._points_key = None
        self._drag_index = None
        self._drag_origin = None
        self._observers = []
        self._interactor = None
        if not self.draggable:
            return
        try:
            self._interactor = plotter.iren.interactor
        except Exception:
            self._interactor = None
        if self._interactor is None:
            return
        for event, handler in (
            ("LeftButtonPressEvent", self._on_press),
            ("MouseMoveEvent", self._on_move),
            ("LeftButtonReleaseEvent", self._on_release),
        ):
            self._observers.append(
                self._interactor.AddObserver(event, handler, ANNOTATION_OBSERVER_PRIORITY)
            )

    # -- lifecycle ----------------------------------------------------------
    def set_points(self, points, texts, font_size=None):
        """Rebuild the callouts for ``points``, preserving any dragged offsets."""
        self.clear()
        if font_size is not None:
            self.font_size = int(font_size)
        points = np.asarray(points, dtype=float).reshape(-1, 3)
        texts = list(texts)
        if points.shape[0] == 0 or len(texts) != points.shape[0]:
            return

        key = (points.shape[0], float(np.sum(points)))
        if key != self._points_key:
            self._offsets = {}
            self._points_key = key

        for index, (point, text) in enumerate(zip(points, texts)):
            offset = self._offsets.get(
                index, ANNOTATION_OFFSETS[index % len(ANNOTATION_OFFSETS)]
            )
            caption = self._build_caption(point, str(text), offset)
            try:
                self.pl.add_actor(
                    caption,
                    name="ansys_annotation_{0}".format(index),
                    render=False,
                    reset_camera=False,
                    pickable=False,
                )
            except Exception:
                continue
            self._entries.append(
                {
                    "actor": caption,
                    "name": "ansys_annotation_{0}".format(index),
                    "index": index,
                    "point": point,
                    "text": str(text),
                }
            )

    def clear(self):
        for entry in self._entries:
            try:
                self.pl.remove_actor(entry["actor"], render=False)
            except Exception:
                try:
                    self.pl.remove_actor(entry["name"], render=False)
                except Exception:
                    pass
        self._entries = []
        self._drag_index = None
        self._drag_origin = None

    def reset_offsets(self):
        self._offsets = {}

    def close(self):
        self.clear()
        if self._interactor is None:
            return
        for observer in self._observers:
            try:
                self._interactor.RemoveObserver(observer)
            except Exception:
                pass
        self._observers = []

    # -- construction -------------------------------------------------------
    def _build_caption(self, point, text, offset):
        caption = vtk.vtkCaptionActor2D()
        caption.SetCaption(text)
        caption.SetAttachmentPoint(float(point[0]), float(point[1]), float(point[2]))
        caption.GetTextActor().SetTextScaleModeToNone()

        prop = caption.GetCaptionTextProperty()
        prop.SetFontFamilyToArial()
        prop.SetFontSize(self.font_size)
        prop.SetColor(*TEXT_COLOR)
        prop.SetBold(False)
        prop.SetItalic(False)
        prop.SetShadow(False)
        prop.SetJustificationToLeft()
        prop.SetVerticalJustificationToBottom()
        prop.SetBackgroundColor(*ANNOTATION_FILL)
        prop.SetBackgroundOpacity(1.0)
        # The frame hugs the rendered text exactly at any window size, unlike
        # the caption border, which is sized from Width/Height in normalised
        # viewport units and would drift as the window resizes.
        prop.FrameOn()
        prop.SetFrameColor(*ANNOTATION_BORDER)
        prop.SetFrameWidth(1)

        caption.BorderOff()
        caption.LeaderOn()
        caption.ThreeDimensionalLeaderOff()
        caption.SetLeaderGlyphSize(0.0)
        caption.SetPadding(ANNOTATION_PADDING)
        caption.GetProperty().SetColor(*LEADER_COLOR)
        caption.GetProperty().SetLineWidth(1.0)
        caption.SetPosition(float(offset[0]), float(offset[1]))
        self._size_caption(caption, text)
        return caption

    def _size_caption(self, caption, text):
        """Size the invisible caption box so the leader terminates on the text."""
        width, height = self._window_size()
        text_width, text_height = _text_extent_px(text, self.font_size)
        box_width = max(text_width + 2 * ANNOTATION_PADDING, 1.0) * _BOX_SHRINK
        box_height = max(text_height + 2 * ANNOTATION_PADDING, 1.0) * _BOX_SHRINK
        caption.SetWidth(box_width / width)
        caption.SetHeight(box_height / height)

    def refresh_geometry(self):
        for entry in self._entries:
            self._size_caption(entry["actor"], entry["text"])

    # -- dragging -----------------------------------------------------------
    def _on_press(self, caller, _event):
        if not self._entries:
            return
        try:
            x, y = caller.GetEventPosition()
        except Exception:
            return
        index = self._caption_at(x, y)
        if index is None:
            return
        entry = self._entries[index]
        offset = entry["actor"].GetPosition()
        self._drag_index = index
        self._drag_origin = (x, y, float(offset[0]), float(offset[1]))
        self._abort(caller, self._observers[0])

    def _on_move(self, caller, _event):
        if self._drag_index is None:
            return
        try:
            x, y = caller.GetEventPosition()
        except Exception:
            return
        start_x, start_y, offset_x, offset_y = self._drag_origin
        entry = self._entries[self._drag_index]
        entry["actor"].SetPosition(
            offset_x + (x - start_x), offset_y + (y - start_y)
        )
        self._offsets[entry["index"]] = (
            offset_x + (x - start_x),
            offset_y + (y - start_y),
        )
        self._abort(caller, self._observers[1])
        try:
            caller.GetRenderWindow().Render()
        except Exception:
            pass

    def _on_release(self, caller, _event):
        if self._drag_index is None:
            return
        self._drag_index = None
        self._drag_origin = None
        self._abort(caller, self._observers[2])

    def _caption_at(self, x, y):
        width, height = self._window_size()
        for position, entry in enumerate(self._entries):
            display = self._display_position(entry["point"])
            if display is None:
                continue
            offset = entry["actor"].GetPosition()
            text_width, text_height = _text_extent_px(entry["text"], self.font_size)
            left = display[0] + float(offset[0])
            bottom = display[1] + float(offset[1])
            right = left + text_width + 2 * ANNOTATION_PADDING
            top = bottom + text_height + 2 * ANNOTATION_PADDING
            if left <= x <= right and bottom <= y <= top:
                return position
        return None

    def _display_position(self, point):
        try:
            renderer = self.pl.renderer
            renderer.SetWorldPoint(
                float(point[0]), float(point[1]), float(point[2]), 1.0
            )
            renderer.WorldToDisplay()
            display = renderer.GetDisplayPoint()
        except Exception:
            return None
        return float(display[0]), float(display[1])

    def _abort(self, caller, observer):
        try:
            command = caller.GetCommand(observer)
            if command is not None:
                command.SetAbortFlag(1)
        except Exception:
            pass

    def _window_size(self):
        try:
            size = self.pl.render_window.GetSize()
            width, height = int(size[0]), int(size[1])
        except Exception:
            width = height = 0
        return (width or 1200, height or 800)

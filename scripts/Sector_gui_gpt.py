#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
PyQt6 + PyVistaQt GUI for sector-duplicating point-cloud .dat files and visualizing them.

Requirements:
    pip install pyqt6 pyvista pyvistaqt pandas numpy

Assumptions:
    - Each .dat file has at least 4 whitespace-separated numeric columns.
    - First 3 columns: X, Y, Z (Cartesian coordinates).
    - 4th column: scalar Data to be visualized and duplicated.
    - Sector duplication is rotation around the global Z-axis.
"""

import math
import os
from dataclasses import dataclass
from typing import List, Optional

os.environ.setdefault("QT_API", "pyqt6")

import numpy as np
import pandas as pd
import pyvista as pv
from pyvistaqt import QtInteractor
from vtkmodules.vtkRenderingCore import vtkPointPicker

from PyQt6.QtCore import (
    Qt,
    QAbstractTableModel,
    QModelIndex,
    pyqtSignal,
)
from PyQt6.QtGui import QPalette, QColor, QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QTableView,
    QSplitter,
    QFileDialog,
    QMessageBox,
    QPlainTextEdit,
    QHeaderView,
    QCheckBox,
    QMenu,
)


HOVER_TEXT_EMPTY = "Hover point: none"
HOVER_TEXT_NAME = "hover_point_info"


# -----------------------------
# Data structures and utilities
# -----------------------------


@dataclass
class FileEntry:
    """Stores data and visualization info for a single .dat file."""

    path: str
    base_df: pd.DataFrame  # columns: X, Y, Z, Data
    n_sectors: int = 1
    total_angle_deg: float = 360.0
    expanded_df: Optional[pd.DataFrame] = None
    polydata: Optional[pv.PolyData] = None
    scalar_min: float = 0.0
    scalar_max: float = 0.0


def expand_sectors(
    base_df: pd.DataFrame,
    n_sectors: int,
    total_angle_deg: float,
) -> pd.DataFrame:
    """
    Duplicate a base point cloud into sectors by rotating around Z-axis.

    base_df: DataFrame with columns ["X", "Y", "Z", "Data"].
    n_sectors: number of sectors to create.
    total_angle_deg: total angle span (e.g. 360 degrees).

    Returns:
        DataFrame with columns ["X", "Y", "Z", "Data"] of size (N * n_sectors, 4).
    """
    if n_sectors < 1:
        raise ValueError("Number of sectors must be >= 1")
    if total_angle_deg <= 0.0:
        raise ValueError("Total angle must be > 0")

    # Ensure correct columns and dtypes
    coords = base_df[["X", "Y", "Z"]].to_numpy(dtype=float)
    data = base_df["Data"].to_numpy(dtype=float)

    x = coords[:, 0]
    y = coords[:, 1]
    z = coords[:, 2]

    all_points = []
    all_data = []

    delta_angle = float(total_angle_deg) / float(n_sectors)

    for k in range(n_sectors):
        angle_deg = k * delta_angle
        angle_rad = math.radians(angle_deg)

        cos_t = math.cos(angle_rad)
        sin_t = math.sin(angle_rad)

        x_rot = x * cos_t - y * sin_t
        y_rot = x * sin_t + y * cos_t
        z_rot = z  # unchanged

        pts_k = np.column_stack((x_rot, y_rot, z_rot))
        all_points.append(pts_k)
        all_data.append(data)  # same scalar field

    points = np.vstack(all_points)
    values = np.hstack(all_data)

    expanded_df = pd.DataFrame(points, columns=["X", "Y", "Z"])
    expanded_df["Data"] = values

    return expanded_df


def make_polydata(df: pd.DataFrame) -> pv.PolyData:
    """
    Convert a DataFrame with columns ["X", "Y", "Z", "Data"] into a PyVista PolyData.
    """
    points = df[["X", "Y", "Z"]].to_numpy(dtype=float)
    values = df["Data"].to_numpy(dtype=float)

    poly = pv.PolyData(points)
    poly["Data"] = values
    poly["NodeId"] = np.arange(poly.n_points, dtype=np.int64)
    return poly


def _hover_text_for_polydata(polydata: pv.PolyData, point_id: int) -> str:
    """
    Build the upper-left hover label for a picked point.
    """
    if point_id < 0 or point_id >= polydata.n_points:
        return HOVER_TEXT_EMPTY

    node_ids = polydata.point_data.get("NodeId")
    values = polydata.point_data.get("Data")
    if node_ids is None or values is None:
        return HOVER_TEXT_EMPTY

    return f"Node ID: {int(node_ids[point_id])}\nValue: {float(values[point_id]):.6g}"


def _read_numeric_dat_file(path: str) -> tuple[pd.DataFrame, int]:
    """
    Read numeric .dat rows and skip rows containing any nonnumeric token.
    """
    rows = []
    skipped_rows = 0

    with open(path, "r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            tokens = line.split()
            if len(tokens) < 4:
                skipped_rows += 1
                continue

            try:
                values = [float(token) for token in tokens]
            except ValueError:
                skipped_rows += 1
                continue

            rows.append(values[:4])

    return pd.DataFrame(rows, columns=["X", "Y", "Z", "Data"]), skipped_rows


# -----------------------
# Table model for the GUI
# -----------------------


class FileTableModel(QAbstractTableModel):
    """
    Table model backing the file list.

    Columns:
        0: File path (read-only)
        1: Number of sectors (editable int)
        2: Total angle [deg] (editable float)
    """

    parametersChanged = pyqtSignal(int, int)  # row, column

    def __init__(self, parent=None):
        super().__init__(parent)
        self._entries: List[FileEntry] = []
        self._dirty_rows: set = set()  # Track rows that need geometry recomputation

    @property
    def entries(self) -> List[FileEntry]:
        return self._entries

    def rowCount(self, parent=QModelIndex()) -> int:
        return len(self._entries)

    def columnCount(self, parent=QModelIndex()) -> int:
        return 3

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role != Qt.ItemDataRole.DisplayRole:
            return None

        if orientation == Qt.Orientation.Horizontal:
            if section == 0:
                return "File"
            elif section == 1:
                return "Sectors"
            elif section == 2:
                return "Angle [deg]"
        return None

    def data(self, index: QModelIndex, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None

        row = index.row()
        col = index.column()

        if row < 0 or row >= len(self._entries):
            return None

        entry = self._entries[row]

        if role == Qt.ItemDataRole.DisplayRole or role == Qt.ItemDataRole.EditRole:
            if col == 0:
                return entry.path
            elif col == 1:
                return str(entry.n_sectors)
            elif col == 2:
                return str(entry.total_angle_deg)

        if role == Qt.ItemDataRole.ToolTipRole:
            if col == 0:
                return entry.path

        return None

    def flags(self, index: QModelIndex):
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags

        col = index.column()
        base_flags = Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled

        if col in (1, 2):  # sectors and angle editable
            return base_flags | Qt.ItemFlag.ItemIsEditable
        else:
            return base_flags

    def mark_row_dirty(self, row: int):
        """Mark a row as needing geometry recomputation."""
        if 0 <= row < len(self._entries):
            self._dirty_rows.add(row)

    def clear_dirty_rows(self):
        """Clear all dirty row markers."""
        self._dirty_rows.clear()

    def get_dirty_rows(self) -> set:
        """Get all rows marked as dirty."""
        return self._dirty_rows.copy()

    def setData(self, index: QModelIndex, value, role=Qt.ItemDataRole.EditRole):
        if role != Qt.ItemDataRole.EditRole or not index.isValid():
            return False

        row = index.row()
        col = index.column()

        if row < 0 or row >= len(self._entries):
            return False

        entry = self._entries[row]
        text = str(value).strip()

        if col == 1:
            # Number of sectors
            try:
                n = int(text)
                if n < 1:
                    return False
            except ValueError:
                return False
            if n == entry.n_sectors:
                return False
            entry.n_sectors = n

        elif col == 2:
            # Total angle
            try:
                angle = float(text)
                if angle <= 0.0:
                    return False
            except ValueError:
                return False
            if math.isclose(angle, entry.total_angle_deg):
                return False
            entry.total_angle_deg = angle

        else:
            return False

        self.dataChanged.emit(index, index, [Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.EditRole])
        self.parametersChanged.emit(row, col)
        return True

    def add_entries(self, new_entries: List[FileEntry]) -> int:
        """
        Append a list of FileEntry objects to the model.

        Returns:
            start_row of inserted items.
        """
        if not new_entries:
            return len(self._entries)

        start_row = len(self._entries)
        end_row = start_row + len(new_entries) - 1

        self.beginInsertRows(QModelIndex(), start_row, end_row)
        self._entries.extend(new_entries)
        self.endInsertRows()
        return start_row

    def remove_rows(self, rows: List[int]):
        """
        Remove rows by index (expects sorted in ascending order or any order;
        will handle in descending internally).
        """
        if not rows:
            return

        # Remove in descending order to keep indices valid
        for row in sorted(rows, reverse=True):
            if 0 <= row < len(self._entries):
                self.beginRemoveRows(QModelIndex(), row, row)
                del self._entries[row]
                self.endRemoveRows()
                # Clean up dirty rows tracking
                self._dirty_rows.discard(row)
                # Adjust other dirty row indices
                self._dirty_rows = {r - 1 if r > row else r for r in self._dirty_rows}


# -----------------------
# PyVista viewer widget
# -----------------------


class Viewer(QtInteractor):
    """
    PyVistaQt viewer with a context menu and simple modes:
        - global: all files visible, global scalar bar
        - focus: one file colored by scalar, others grey
    """

    requestGlobalView = pyqtSignal()
    requestResetCamera = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_mode: str = "global"  # "global" or "focus"
        self.focus_index: Optional[int] = None
        self._has_camera: bool = False
        self.point_size: float = 4.0  # Default point size
        self.focus_point_size: float = 5.0  # Default focused point size
        self._hover_picker = vtkPointPicker()
        self._hover_picker.SetTolerance(0.01)
        self._hover_text_value = HOVER_TEXT_EMPTY
        self.iren.add_observer("MouseMoveEvent", self._on_mouse_move, interactor_style_fallback=False)

        # Visual tweaks
        self.set_background("black")  # change to taste
        self.show_axes()
        self._set_hover_text(HOVER_TEXT_EMPTY, render=False, force=True)

    def contextMenuEvent(self, event):
        menu = QMenu(self)

        action_global = menu.addAction("Show all files (global view)")
        action_reset = menu.addAction("Reset camera")

        action = menu.exec(event.globalPos())
        if action == action_global:
            self.requestGlobalView.emit()
        elif action == action_reset:
            self.requestResetCamera.emit()

    def _store_camera_if_any(self):
        """
        Return camera position if a camera was set before; otherwise None.
        """
        if self._has_camera:
            return self.camera_position
        return None

    def _restore_or_reset_camera(self, camera_position):
        """
        Restore camera if camera_position is not None, otherwise reset.
        """
        if camera_position is None:
            self.reset_camera()
            self._has_camera = True
        else:
            self.camera_position = camera_position
            self._has_camera = True

    def _set_hover_text(self, text: str, render: bool = True, force: bool = False):
        if not force and text == self._hover_text_value:
            return
        self._hover_text_value = text
        self.add_text(
            text,
            position="upper_left",
            font_size=10,
            color="white",
            shadow=True,
            name=HOVER_TEXT_NAME,
            render=render,
        )

    def _on_mouse_move(self, *_args):
        x, y = self.iren.get_event_position()
        if not self._hover_picker.Pick(x, y, 0, self.renderer):
            self._set_hover_text(HOVER_TEXT_EMPTY)
            return

        dataset = self._hover_picker.GetDataSet()
        point_id = self._hover_picker.GetPointId()
        if dataset is None or point_id < 0:
            self._set_hover_text(HOVER_TEXT_EMPTY)
            return

        self._set_hover_text(_hover_text_for_polydata(pv.wrap(dataset), point_id))

    def show_global(self, entries: List[FileEntry]):
        """
        Show all files with a global scalar bar range.
        """
        self.current_mode = "global"
        self.focus_index = None

        camera = self._store_camera_if_any()
        self.clear()
        self._set_hover_text(HOVER_TEXT_EMPTY, render=False, force=True)

        if not entries:
            self.render()
            return

        # Determine global scalar range
        scalar_mins = [e.scalar_min for e in entries]
        scalar_maxs = [e.scalar_max for e in entries]
        global_min = float(min(scalar_mins))
        global_max = float(max(scalar_maxs))

        # Draw all meshes
        mesh_actor = None
        for entry in entries:
            if entry.polydata is None:
                continue
            actor = self.add_mesh(
                entry.polydata,
                scalars="Data",
                cmap="jet",
                clim=(global_min, global_max),
                show_scalar_bar=False,
                render_points_as_spheres=True,
                point_size=self.point_size,
            )
            # Store the first mesh actor for scalar bar reference
            if mesh_actor is None:
                mesh_actor = actor

        # Add a single scalar bar using the mesh actor
        if mesh_actor is not None:
            self.add_scalar_bar(title="Data", mapper=mesh_actor.GetMapper())

        self._restore_or_reset_camera(camera)
        self.render()

    def show_focus(self, entries: List[FileEntry], focus_index: int):
        """
        Show a focused view on a single file, with other files in grey.
        """
        if not entries:
            self.clear()
            self._set_hover_text(HOVER_TEXT_EMPTY, render=False, force=True)
            self.render()
            return

        if focus_index < 0 or focus_index >= len(entries):
            # Fallback to global view if index is invalid
            self.show_global(entries)
            return

        self.current_mode = "focus"
        self.focus_index = focus_index

        camera = self._store_camera_if_any()
        self.clear()
        self._set_hover_text(HOVER_TEXT_EMPTY, render=False, force=True)

        focus_entry = entries[focus_index]
        local_min = float(focus_entry.scalar_min)
        local_max = float(focus_entry.scalar_max)

        # Draw meshes: focus file colored, others grey/transparent
        focus_actor = None
        for idx, entry in enumerate(entries):
            if entry.polydata is None:
                continue

            if idx == focus_index:
                focus_actor = self.add_mesh(
                    entry.polydata,
                    scalars="Data",
                    cmap="jet",
                    clim=(local_min, local_max),
                    show_scalar_bar=False,
                    render_points_as_spheres=True,
                    point_size=self.focus_point_size,
                )
            else:
                self.add_mesh(
                    entry.polydata,
                    color="lightgray",
                    opacity=0.15,
                    render_points_as_spheres=True,
                    point_size=self.point_size * 0.75,  # Slightly smaller for background
                    show_scalar_bar=False,
                )

        # Add scalar bar for the focused file using its mapper
        if focus_actor is not None:
            self.add_scalar_bar(title="Data", mapper=focus_actor.GetMapper())

        self._restore_or_reset_camera(camera)
        self.render()

    def reset_camera_view(self):
        self.reset_camera()
        self._has_camera = True
        self.render()

    def increase_point_size(self):
        """Increase point size by 1 unit."""
        self.point_size += 1.0
        self.focus_point_size += 1.0
        return self.point_size

    def decrease_point_size(self):
        """Decrease point size by 1 unit (minimum 1.0)."""
        self.point_size = max(1.0, self.point_size - 1.0)
        self.focus_point_size = max(1.0, self.focus_point_size - 1.0)
        return self.point_size


# ---------------
# Main window GUI
# ---------------


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Sector Duplicator & Point Cloud Viewer")
        self.resize(1400, 800)

        self.model = FileTableModel(self)

        # State tracking for manual update controls
        self._auto_update_enabled = True
        self._needs_update = False
        self._last_selected_column = None  # Track which column was last selected

        self._build_ui()
        self._connect_signals()

    # ---- UI setup ----

    def _build_ui(self):
        splitter = QSplitter(Qt.Orientation.Horizontal, self)
        self.setCentralWidget(splitter)

        # Left panel: controls + table
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(6, 6, 6, 6)
        left_layout.setSpacing(6)

        button_layout = QHBoxLayout()
        self.btn_add_files = QPushButton("Add Files…")
        self.btn_remove_selected = QPushButton("Remove Selected")
        self.btn_export_csv = QPushButton("Export Expanded CSV")

        button_layout.addWidget(self.btn_add_files)
        button_layout.addWidget(self.btn_remove_selected)
        button_layout.addWidget(self.btn_export_csv)
        button_layout.addStretch(1)

        # Add manual update controls
        update_controls_layout = QHBoxLayout()
        self.chk_auto_update = QCheckBox("Auto-Update PyVista")
        self.chk_auto_update.setChecked(True)
        self.btn_update_screen = QPushButton("Update Screen")
        self.btn_update_screen.setMinimumWidth(120)

        update_controls_layout.addWidget(self.chk_auto_update)
        update_controls_layout.addWidget(self.btn_update_screen)
        update_controls_layout.addStretch(1)

        self.table_view = QTableView()
        self.table_view.setModel(self.model)
        self.table_view.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.table_view.setSelectionMode(QTableView.SelectionMode.ExtendedSelection)
        self.table_view.setAlternatingRowColors(True)
        self.table_view.setSortingEnabled(False)

        header = self.table_view.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)

        left_layout.addLayout(button_layout)
        left_layout.addLayout(update_controls_layout)
        left_layout.addWidget(self.table_view)

        # Right panel: viewer + log
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(6, 6, 6, 6)
        right_layout.setSpacing(6)

        self.viewer = Viewer(right_widget)

        self.log_widget = QPlainTextEdit()
        self.log_widget.setReadOnly(True)
        self.log_widget.setMaximumHeight(120)

        right_layout.addWidget(self.viewer, stretch=1)
        right_layout.addWidget(self.log_widget, stretch=0)

        splitter.addWidget(left_widget)
        splitter.addWidget(right_widget)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)

    def _connect_signals(self):
        self.btn_add_files.clicked.connect(self.on_add_files)
        self.btn_remove_selected.clicked.connect(self.on_remove_selected)
        self.btn_export_csv.clicked.connect(self.on_export_csv)

        # Manual update controls
        self.chk_auto_update.toggled.connect(self.on_auto_update_toggled)
        self.btn_update_screen.clicked.connect(self.on_manual_update)

        self.model.parametersChanged.connect(self.on_parameters_changed)

        # table selection -> viewer focus
        self.table_view.selectionModel().selectionChanged.connect(
            self.on_selection_changed
        )

        # viewer context menu actions
        self.viewer.requestGlobalView.connect(self.on_request_global_view)
        self.viewer.requestResetCamera.connect(self.on_request_reset_camera)

        # Keyboard shortcuts for point size control
        self.shortcut_increase_size = QShortcut(QKeySequence("Ctrl++"), self)
        self.shortcut_increase_size.activated.connect(self.on_increase_point_size)

        self.shortcut_decrease_size = QShortcut(QKeySequence("Ctrl+-"), self)
        self.shortcut_decrease_size.activated.connect(self.on_decrease_point_size)

    # ---- Logging ----

    def log(self, text: str):
        self.log_widget.appendPlainText(text)

    # ---- Model / data helpers ----

    def _validate_and_load_file(self, path: str) -> (Optional[FileEntry], Optional[str]):
        """
        Try to read and validate a single .dat file.

        Returns:
            (entry, None) if successful
            (None, reason) if failed
        """
        try:
            # Strict .dat extension check can be relaxed if needed
            if not path.lower().endswith(".dat"):
                return None, "File does not have .dat extension."

            base_df, skipped_rows = _read_numeric_dat_file(path)
            if base_df.empty:
                return None, "No usable numeric rows with at least 4 columns."
            if skipped_rows:
                self.log(f"Skipped {skipped_rows} nonnumeric or short line(s): {path}")

            scalar_min = float(base_df["Data"].min())
            scalar_max = float(base_df["Data"].max())

            entry = FileEntry(
                path=path,
                base_df=base_df,
                n_sectors=1,
                total_angle_deg=360.0,
                expanded_df=None,
                polydata=None,
                scalar_min=scalar_min,
                scalar_max=scalar_max,
            )
            return entry, None

        except Exception as exc:
            return None, f"Error reading file: {exc}"

    def _recompute_entry_geometry(self, row: int):
        """
        Recompute the expanded DataFrame and PolyData for a given row.
        """
        if row < 0 or row >= len(self.model.entries):
            return

        entry = self.model.entries[row]
        try:
            expanded_df = expand_sectors(
                entry.base_df,
                entry.n_sectors,
                entry.total_angle_deg,
            )
            entry.expanded_df = expanded_df
            entry.polydata = make_polydata(expanded_df)
        except Exception as exc:
            self.log(f"Error expanding sectors for row {row}: {exc}")
            entry.expanded_df = None
            entry.polydata = None

    def _refresh_view(self):
        """
        Redraw the viewer according to current mode and data state.
        """
        entries = self.model.entries
        if not entries:
            self.viewer.clear()
            self.viewer.render()
            return

        if self.viewer.current_mode == "focus":
            idx = self.viewer.focus_index
            if idx is not None and 0 <= idx < len(entries):
                self.viewer.show_focus(entries, idx)
            else:
                self.viewer.show_global(entries)
        else:
            self.viewer.show_global(entries)

    # ---- Slots / event handlers ----

    def on_add_files(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Select DAT files",
            "",
            "DAT files (*.dat);;All Files (*)",
        )
        if not paths:
            return

        valid_entries: List[FileEntry] = []
        invalid_messages: List[str] = []

        existing_paths = {e.path for e in self.model.entries}

        for path in paths:
            if path in existing_paths:
                invalid_messages.append(f"{path}: already loaded, skipped.")
                continue

            entry, reason = self._validate_and_load_file(path)
            if entry is not None:
                valid_entries.append(entry)
            else:
                invalid_messages.append(f"{path}: {reason}")

        if invalid_messages:
            msg = "Some files were skipped:\n\n" + "\n".join(invalid_messages)
            QMessageBox.warning(self, "File validation", msg)
            for line in invalid_messages:
                self.log(line)

        if not valid_entries:
            return

        start_row = self.model.add_entries(valid_entries)
        # Recompute geometry for newly added entries
        for i in range(len(valid_entries)):
            row = start_row + i
            self._recompute_entry_geometry(row)

        # Mark as needing update
        self._mark_needs_update()

        # Show all in global view if auto-update is enabled
        if self._auto_update_enabled:
            self._apply_updates()

        self.log(f"Added {len(valid_entries)} file(s).")

    def on_remove_selected(self):
        selection_model = self.table_view.selectionModel()
        # Get selected rows from either row selection or cell selection
        selected_indexes = selection_model.selectedIndexes()
        selected_rows = sorted(set(idx.row() for idx in selected_indexes))

        if not selected_rows:
            QMessageBox.information(self, "Remove Files", "No rows selected.")
            return

        # Just for logging
        removed_paths = [self.model.entries[r].path for r in selected_rows]

        self.model.remove_rows(selected_rows)

        # Mark as needing update
        self._mark_needs_update()

        # Apply update if auto-update is enabled
        if self._auto_update_enabled:
            self._apply_updates()

        # Clear selection
        self.table_view.clearSelection()

        for p in removed_paths:
            self.log(f"Removed file: {p}")

    def on_export_csv(self):
        entries = self.model.entries
        if not entries:
            QMessageBox.information(self, "Export CSV", "No data to export.")
            return

        # Ensure all expanded data is up to date
        for row in range(len(entries)):
            self._recompute_entry_geometry(row)

        frames = []
        for entry in entries:
            if entry.expanded_df is not None:
                frames.append(entry.expanded_df)

        if not frames:
            QMessageBox.warning(
                self, "Export CSV", "No expanded data available to export."
            )
            return

        df_all = pd.concat(frames, ignore_index=True)
        df_all = df_all[["X", "Y", "Z", "Data"]]  # ensure correct order

        out_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save expanded data as CSV",
            "",
            "CSV files (*.csv);;All Files (*)",
        )
        if not out_path:
            return

        try:
            df_all.to_csv(out_path, index=False)
            self.log(f"Exported expanded data to: {out_path}")
            QMessageBox.information(
                self, "Export CSV", f"Expanded data saved to:\n{out_path}"
            )
        except Exception as exc:
            QMessageBox.critical(self, "Export CSV", f"Failed to save CSV:\n{exc}")
            self.log(f"Error exporting CSV: {exc}")

    def on_parameters_changed(self, row: int, column: int):
        """
        Triggered when sectors or total angle is edited in the table.
        """
        if self._auto_update_enabled:
            # Immediately recompute and update view
            self._recompute_entry_geometry(row)
            self._refresh_view()
            self.log(
                f"Updated parameters for row {row}: "
                f"sectors={self.model.entries[row].n_sectors}, "
                f"angle={self.model.entries[row].total_angle_deg}"
            )
        else:
            # Mark as dirty and defer update
            self.model.mark_row_dirty(row)
            self._mark_needs_update()
            self.log(
                f"Parameters changed for row {row} (pending update): "
                f"sectors={self.model.entries[row].n_sectors}, "
                f"angle={self.model.entries[row].total_angle_deg}"
            )

    def on_selection_changed(self, selected, deselected):
        """
        When the user selects filepath cells, focus the view on that file.
        Selecting sector/angle cells alone does NOT trigger replot.
        """
        selection_model = self.table_view.selectionModel()
        selected_indexes = selection_model.selectedIndexes()

        # Check if any selected index is in column 0 (filepath)
        has_filepath_selection = any(idx.column() == 0 for idx in selected_indexes)

        # Only update view if filepath cells are selected
        if not has_filepath_selection:
            return

        # Get selected rows
        rows = sorted(set(idx.row() for idx in selected_indexes if idx.column() == 0))

        entries = self.model.entries

        if not entries:
            self.viewer.clear()
            self.viewer.render()
            return

        if not rows:
            # No filepath selection -> global view
            self.viewer.show_global(entries)
            return

        focus_row = rows[0]
        self.viewer.show_focus(entries, focus_row)

    def on_request_global_view(self):
        """
        Right-click context menu: show all files.
        """
        # Clear selection so that global state is consistent
        self.table_view.clearSelection()
        self.viewer.show_global(self.model.entries)

    def on_request_reset_camera(self):
        """
        Right-click context menu: reset camera.
        """
        self.viewer.reset_camera_view()

    # ---- Keyboard shortcuts ----

    def on_increase_point_size(self):
        """
        Handle Ctrl + (Plus) shortcut to increase point size.
        """
        new_size = self.viewer.increase_point_size()
        self._refresh_view()
        self.log(f"Point size increased to {new_size:.1f}")

    def on_decrease_point_size(self):
        """
        Handle Ctrl + (Minus) shortcut to decrease point size.
        """
        new_size = self.viewer.decrease_point_size()
        self._refresh_view()
        self.log(f"Point size decreased to {new_size:.1f}")

    # ---- Manual update controls ----

    def on_auto_update_toggled(self, checked: bool):
        """
        Handle auto-update checkbox toggle.
        """
        self._auto_update_enabled = checked
        if checked and self._needs_update:
            # If re-enabling auto-update and there are pending changes, apply them
            self._apply_updates()
        self.log(f"Auto-update {'enabled' if checked else 'disabled'}.")

    def on_manual_update(self):
        """
        Handle manual update button click.
        """
        if not self._needs_update:
            self.log("Screen is already up-to-date.")
            return

        self._apply_updates()
        self.log("Screen updated manually.")

    def _mark_needs_update(self):
        """
        Mark that PyVista screen needs updating and style the update button.
        """
        if not self._needs_update:
            self._needs_update = True
            # Set button style to reddish to indicate update needed
            self.btn_update_screen.setStyleSheet(
                "background-color: #8B4513; font-weight: bold; color: white;"
            )

    def _clear_needs_update(self):
        """
        Clear the needs update flag and restore button style.
        """
        self._needs_update = False
        self.btn_update_screen.setStyleSheet("")  # Reset to default style

    def _apply_updates(self):
        """
        Apply all pending geometry recomputations and refresh the view.
        """
        dirty_rows = self.model.get_dirty_rows()

        # Recompute geometry for all dirty rows
        for row in dirty_rows:
            self._recompute_entry_geometry(row)

        # Clear dirty rows
        self.model.clear_dirty_rows()

        # Refresh view
        self._refresh_view()

        # Clear update needed flag
        self._clear_needs_update()


# ---------------
# Application main
# ---------------


def _set_modern_palette(app: QApplication):
    """
    Set a simple modern darkish Fusion palette.
    """
    app.setStyle("Fusion")
    palette = QPalette()

    base_color = QColor(53, 53, 53)
    text_color = QColor(220, 220, 220)
    highlight_color = QColor(42, 130, 218)

    palette.setColor(QPalette.ColorRole.Window, base_color)
    palette.setColor(QPalette.ColorRole.WindowText, text_color)
    palette.setColor(QPalette.ColorRole.Base, QColor(35, 35, 35))
    palette.setColor(QPalette.ColorRole.AlternateBase, base_color)
    palette.setColor(QPalette.ColorRole.ToolTipBase, text_color)
    palette.setColor(QPalette.ColorRole.ToolTipText, text_color)
    palette.setColor(QPalette.ColorRole.Text, text_color)
    palette.setColor(QPalette.ColorRole.Button, base_color)
    palette.setColor(QPalette.ColorRole.ButtonText, text_color)
    palette.setColor(QPalette.ColorRole.BrightText, QColor(255, 0, 0))
    palette.setColor(QPalette.ColorRole.Highlight, highlight_color)
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor(0, 0, 0))

    app.setPalette(palette)


def main():
    import sys

    pv.set_plot_theme("dark")  # optional, keeps things consistent

    app = QApplication(sys.argv)
    _set_modern_palette(app)

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()

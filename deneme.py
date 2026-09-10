# mos_app.py : MoS% Calculator with Strength Type (YTS/UTS) dropdown + configurable preview cap
# Default: MoS% = [1 - sigma_max / (Strength(T)/FS)] * 100
# Strength applies to allowable (allowable = Strength/FS). Preview table is capped for speed.

import sys, os, re, time
import numpy as np
import pandas as pd
from PyQt6 import QtCore, QtGui, QtWidgets

APP_NAME, VERSION = "MoS Calculator", "0.5.1"

# ---------- utilities ----------
def c_to_k(c): return c + 273.15
def k_to_c(k): return k - 273.15

# --- FIX ---: Replaced the buggy custom interpolation function with NumPy's robust np.interp.
def interp_with_extrap(x, xp, fp, extrap='clamp'):
    """
    Interpolates data using NumPy's interp and handles extrapolation policies.
    """
    x = np.asarray(x, dtype=float)
    xp = np.asarray(xp, dtype=float)
    fp = np.asarray(fp, dtype=float)

    if xp.ndim != 1 or fp.ndim != 1 or xp.size != fp.size:
        raise ValueError("xp and fp must be 1D and the same length")
    if np.any(np.diff(xp) <= 0):
        raise ValueError("Material temperature column must be strictly increasing")

    if extrap == 'error':
        if np.any((x < xp[0]) | (x > xp[-1])):
            raise ValueError("Extrapolation outside material temperature range")
    y = np.interp(x, xp, fp)

    if extrap == 'linear':
        if xp.size < 2:
            raise ValueError("Need at least two material points for linear extrapolation")
        # Linear extrapolation on both ends
        x0, x1 = xp[0], xp[1]
        y0, y1 = fp[0], fp[1]
        xn1, xn2 = xp[-2], xp[-1]
        yn1, yn2 = fp[-2], fp[-1]
        m_low = (y1 - y0) / (x1 - x0)
        m_high = (yn2 - yn1) / (xn2 - xn1)
        low_mask = x < x0
        high_mask = x > xn2
        if np.any(low_mask):
            y[low_mask] = y0 + m_low * (x[low_mask] - x0)
        if np.any(high_mask):
            y[high_mask] = yn2 + m_high * (x[high_mask] - xn2)

    return y


def guess_col(df, patterns):
    pats = [re.compile(p, re.I) for p in patterns]
    for col in df.columns:
        name = str(col)
        if any(p.search(name) for p in pats): return col
    return None


# --- NEW ---: strength-type-aware guess patterns
def strength_patterns(strength_type: str):
    st = str(strength_type).upper().strip()
    if st == "UTS":
        # Common naming: UTS, ultimate, tensile strength, Rm
        return [r"\buts\b", r"ultimate", r"tensile", r"\brm\b", r"su\b", r"sig.*u", r"f_u"]
    # Default to YTS
    return [r"yield", r"\byts\b", r"proof", r"rp0[.,]2", r"r0[.,]2", r"sy\b", r"sig.*y", r"f_y"]

def temp_patterns():
    # Common naming: Temp, T(C/K), BFE
    return [
        r"temp",
        r"t(c|k)",
        r"tref",
        r"temp[_\s]*c",
        r"t\s*\(\s*Â°?c\s*\)",
        r"temp\s*\(\s*Â°?c\s*\)",
        r"\bbfe\b",
        r"bfe\s*\(\s*\)",
    ]


# ---------- Qt model ----------
class PandasModel(QtCore.QAbstractTableModel):
    def __init__(self, df=pd.DataFrame(), parent=None):
        super().__init__(parent)
        self._df = df
        self._float_decimals = 4

    def setDataFrame(self, df):
        self.beginResetModel()
        self._df = df.copy()
        self.endResetModel()

    def rowCount(self, parent=None):
        return 0 if parent and parent.isValid() else len(self._df.index)

    def columnCount(self, parent=None):
        return 0 if parent and parent.isValid() else len(self._df.columns)

    def data(self, index, role=QtCore.Qt.ItemDataRole.DisplayRole):
        if not index.isValid(): return None
        if role in (QtCore.Qt.ItemDataRole.DisplayRole, QtCore.Qt.ItemDataRole.EditRole):
            val = self._df.iat[index.row(), index.column()]
            if pd.isna(val):
                return ""
            if isinstance(val, (np.floating, float)):
                if np.isfinite(val):
                    s = f"{float(val):.{self._float_decimals}f}"
                    s = s.rstrip("0").rstrip(".")
                    return "0" if s == "-0" else s
                return str(val)
            if isinstance(val, (np.integer, int)):
                return str(int(val))
            return str(val)
        return None

    def headerData(self, section, orientation, role):
        if role != QtCore.Qt.ItemDataRole.DisplayRole: return None
        if orientation == QtCore.Qt.Orientation.Horizontal:
            return str(self._df.columns[section])
        return str(self._df.index[section])


# ---------- file drop helper ----------
class FileDropWidget(QtWidgets.QWidget):
    def __init__(self, on_drop, parent=None, on_drag_hint=None, on_drag_leave=None):
        super().__init__(parent)
        self._on_drop = on_drop
        self._on_drag_hint = on_drag_hint
        self._on_drag_leave = on_drag_leave
        self.setAcceptDrops(True)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            if callable(self._on_drag_hint):
                self._on_drag_hint()
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            if callable(self._on_drag_hint):
                self._on_drag_hint()
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragLeaveEvent(self, event):
        if callable(self._on_drag_leave):
            self._on_drag_leave()
        event.accept()

    def dropEvent(self, event):
        urls = event.mimeData().urls()
        if not urls:
            event.ignore()
            return
        path = urls[0].toLocalFile()
        if path:
            self._on_drop(path)
            event.acceptProposedAction()
        else:
            event.ignore()
        if callable(self._on_drag_leave):
            self._on_drag_leave()


# ---------- table copy helper ----------
class TableCopyHelper(QtCore.QObject):
    def __init__(self, table):
        super().__init__(table)
        self.table = table
        self.table.installEventFilter(self)
        self.table.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectItems)
        self.table.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.ActionsContextMenu)
        act_copy = QtGui.QAction("Copy", self.table)
        act_copy.setShortcut(QtGui.QKeySequence.StandardKey.Copy)
        act_copy.triggered.connect(self.copy_selection)
        self.table.addAction(act_copy)

    def eventFilter(self, obj, event):
        if obj is self.table and event.type() == QtCore.QEvent.Type.KeyPress:
            if event.matches(QtGui.QKeySequence.StandardKey.Copy):
                self.copy_selection()
                return True
        return super().eventFilter(obj, event)

    def copy_selection(self):
        sel = self.table.selectionModel()
        if sel is None:
            return
        indexes = sel.selectedIndexes()
        if not indexes:
            return
        indexes = sorted(indexes, key=lambda i: (i.row(), i.column()))
        cols = sorted({i.column() for i in indexes})
        rows = {}
        for idx in indexes:
            rows.setdefault(idx.row(), {})[idx.column()] = idx.data()

        lines = []
        for r in sorted(rows.keys()):
            line = []
            for c in cols:
                val = rows[r].get(c, "")
                line.append("" if val is None else str(val))
            lines.append("\t".join(line))
        QtWidgets.QApplication.clipboard().setText("\n".join(lines))


# ---------- worker ----------
class ComputeWorker(QtCore.QObject):
    finished = QtCore.pyqtSignal(pd.DataFrame, dict, str)  # df, stats, err

    # --- CHANGED ---: yts -> strength, plus strength_type
    def __init__(self, material, ansys, map_mat, map_ans, units, fs, extrap, strength_type, percent=True,
                 use_const_temp=False, const_temp=None):
        super().__init__()
        self.material, self.ansys = material, ansys
        self.map_mat, self.map_ans = map_mat, map_ans
        self.units, self.fs, self.extrap, self.percent = units, fs, extrap, percent
        self.strength_type = str(strength_type).upper().strip()  # "YTS" or "UTS"
        self.use_const_temp = bool(use_const_temp)
        self.const_temp = const_temp

    @QtCore.pyqtSlot()
    def run(self):
        try:
            t0 = time.perf_counter()

            # material
            Tm = self.material[self.map_mat['temp']].to_numpy(dtype=float)

            # --- CHANGED ---: generic "Strength" column selection
            Scol = self.map_mat['strength']
            Strength = self.material[Scol].to_numpy(dtype=float)

            if self.units['mat_T'] == 'K':
                Tm = k_to_c(Tm)
            mat_strength_units = self.units.get('mat_strength', 'MPa')
            if mat_strength_units == 'Pa':
                Strength = Strength / 1e6
            elif mat_strength_units == 'GPa':
                Strength = Strength * 1000.0

            # Ensure material properties are sorted by temperature
            order = np.argsort(Tm)
            Tm, Strength = Tm[order], Strength[order]

            # ansys
            node = self.ansys[self.map_ans['node']].to_numpy()
            stress = self.ansys[self.map_ans['stress']].to_numpy(dtype=float)
            if self.use_const_temp:
                if self.const_temp is None:
                    raise ValueError("Constant temperature is enabled but no value was provided")
                Ta = np.full(stress.shape, float(self.const_temp), dtype=float)
            else:
                Ta = self.ansys[self.map_ans['temp']].to_numpy(dtype=float)
            if self.units['ans_T'] == 'K':
                Ta = k_to_c(Ta)
            if self.units.get('ans_stress', 'MPa') == 'Pa':
                stress = stress / 1e6

            # compute
            strength_at_T = interp_with_extrap(Ta, Tm, Strength, extrap=self.extrap)
            allowable = strength_at_T / max(self.fs, 1e-12)

            with np.errstate(divide='ignore', invalid='ignore'):
                mos_ratio = 1.0 - (stress / allowable)

            mos = 100.0 * mos_ratio if self.percent else mos_ratio

            # output
            st = self.strength_type  # label for columns
            df_out = pd.DataFrame({
                "NodeID": node,
                "Stress_MPa": stress,
                "Temp_C": Ta,
                f"{st}_at_T_MPa": strength_at_T,
                f"Allowable_{st}_MPa": allowable,
            })
            df_out["MoS_%" if self.percent else "MoS"] = mos

            worst_idx = int(np.nanargmin(mos))
            stats = {
                "rows": int(df_out.shape[0]),
                "num_negative": int(np.sum(mos < 0)),
                "worst_node": str(df_out.iloc[worst_idx]["NodeID"]),
                "worst_mos_percent": float(mos[worst_idx] if self.percent else mos_ratio[worst_idx] * 100.0),
                "t_compute_s": float(time.perf_counter() - t0),
                "strength_type": st,
            }
            self.finished.emit(df_out, stats, "")
        except Exception as e:
            self.finished.emit(pd.DataFrame(), {}, str(e))


# ---------- main window ----------
class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} v{VERSION}")
        self.resize(1280, 800)
        self.material_df = pd.DataFrame()
        self.ansys_df = pd.DataFrame()
        self.results_df = pd.DataFrame()
        self.dark_mode = True
        self.const_temp_col = None
        self.merged_temp_col = None
        self.has_real_temp = False
        self.node_filter_id = None
        self._copy_helpers = []
        self._build_ui()
        self._apply_style()

    # UI build
    def _build_ui(self):
        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        layout = QtWidgets.QVBoxLayout(central)

        tb = QtWidgets.QToolBar()
        tb.setMovable(False)
        self.addToolBar(tb)
        act_theme = QtGui.QAction("Toggle Theme", self)
        act_theme.setToolTip("Switch between dark and light theme")
        act_theme.triggered.connect(self._toggle_theme)
        tb.addAction(act_theme)

        self.tabs = QtWidgets.QTabWidget()
        self.tabs.setTabPosition(QtWidgets.QTabWidget.TabPosition.West)
        layout.addWidget(self.tabs)
        self._build_tab_material()
        self._build_tab_ansys()
        self._build_tab_compute()
        self._build_tab_results()

        self.status = QtWidgets.QStatusBar()
        self.setStatusBar(self.status)

    def _build_tab_material(self):
        w = FileDropWidget(
            self._handle_material_drop,
            on_drag_hint=lambda: self._show_drop_hint("material file"),
            on_drag_leave=self._clear_drop_hint,
        )
        v = QtWidgets.QVBoxLayout(w)
        top = QtWidgets.QHBoxLayout()
        self.btn_mat = QtWidgets.QPushButton("Load Material CSV/XLSX")
        self.btn_mat.setToolTip(
            "Load material properties table (CSV/XLSX/TXT)\n"
            "Expected columns (example): Temp_C, YTS_MPa or UTS_MPa\n"
            "Accepted separators: comma or tab (auto-detected)"
        )
        self.btn_mat.clicked.connect(self.load_material)
        top.addWidget(self.btn_mat)
        top.addStretch()

        top.addWidget(QtWidgets.QLabel("Material T units:"))
        self.combo_mat_units = QtWidgets.QComboBox()
        self.combo_mat_units.addItems(["C", "K"])
        self.combo_mat_units.setCurrentText("C")
        self.combo_mat_units.setMinimumWidth(140)
        self.combo_mat_units.setSizeAdjustPolicy(QtWidgets.QComboBox.SizeAdjustPolicy.AdjustToContents)
        self.combo_mat_units.setToolTip(
            "Units of the material temperature column:\n"
            "- C: values are in degrees Celsius\n"
            "- K: values are in Kelvin (will be converted to C)"
        )
        top.addWidget(self.combo_mat_units)

        # --- NEW ---: Strength type dropdown (YTS/UTS)
        top.addSpacing(16)
        top.addWidget(QtWidgets.QLabel("Strength type:"))
        self.combo_strength_type = QtWidgets.QComboBox()
        self.combo_strength_type.addItems(["YTS", "UTS"])
        self.combo_strength_type.setCurrentText("YTS")
        self.combo_strength_type.setMinimumWidth(120)
        self.combo_strength_type.setToolTip(
            "Strength type used for allowables:\n"
            "- YTS: yield tensile strength\n"
            "- UTS: ultimate tensile strength\n"
            "Allowable = Strength / FS"
        )
        self.combo_strength_type.currentTextChanged.connect(self._on_strength_type_changed)
        top.addWidget(self.combo_strength_type)
        top.addSpacing(16)
        top.addWidget(QtWidgets.QLabel("Strength units:"))
        self.combo_mat_strength_units = QtWidgets.QComboBox()
        self.combo_mat_strength_units.addItems(["MPa", "Pa", "GPa"])
        self.combo_mat_strength_units.setCurrentText("MPa")
        self.combo_mat_strength_units.setMinimumWidth(140)
        self.combo_mat_strength_units.setSizeAdjustPolicy(QtWidgets.QComboBox.SizeAdjustPolicy.AdjustToContents)
        self.combo_mat_strength_units.setToolTip(
            "Units of the material strength column:\n"
            "- MPa: no conversion\n"
            "- Pa: converted to MPa (divide by 1e6)\n"
            "- GPa: converted to MPa (multiply by 1000)"
        )
        top.addWidget(self.combo_mat_strength_units)

        v.addLayout(top)

        form = QtWidgets.QFormLayout()
        self.cb_mat_temp = QtWidgets.QComboBox()
        self.cb_mat_strength = QtWidgets.QComboBox()
        self.cb_mat_temp.setToolTip("Select the material temperature column")
        self.cb_mat_strength.setToolTip("Select the material strength column")

        form.addRow("Temperature column", self.cb_mat_temp)

        # --- NEW/CHANGED ---: label that updates when strength type changes
        self.lbl_mat_strength = QtWidgets.QLabel("Strength column (YTS)")
        form.addRow(self.lbl_mat_strength, self.cb_mat_strength)

        v.addLayout(form)

        self.tbl_mat = QtWidgets.QTableView()
        if hasattr(self.tbl_mat, "setUniformRowHeights"):
            self.tbl_mat.setUniformRowHeights(True)
        self.tbl_mat.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.Stretch)
        self.tbl_mat.setToolTip("Preview of material data (sortable)")
        self._enable_table_copy(self.tbl_mat)
        self.model_mat = PandasModel()
        self.proxy_model_mat = QtCore.QSortFilterProxyModel()
        self.proxy_model_mat.setSourceModel(self.model_mat)
        self.tbl_mat.setModel(self.proxy_model_mat)
        self.tbl_mat.setSortingEnabled(True)
        v.addWidget(self.tbl_mat)
        self.tabs.addTab(w, "Material DB")

    def _build_tab_ansys(self):
        w = FileDropWidget(
            self._handle_ansys_drop,
            on_drag_hint=lambda: self._show_drop_hint("ANSYS stress file or Node Temp file"),
            on_drag_leave=self._clear_drop_hint,
        )
        v = QtWidgets.QVBoxLayout(w)
        top = QtWidgets.QHBoxLayout()
        self.btn_ans = QtWidgets.QPushButton("Load ANSYS CSV/XLSX")
        self.btn_ans.setToolTip(
            "Load ANSYS results table (CSV/XLSX/TXT)\n"
            "Expected columns (example): NodeID, Stress_MPa, Temp_C / TEMP_C / T(Â°C) / TEMP(Â°C) / TREF / BFE()\n"
            "Accepted separators: comma or tab (auto-detected)\n"
            "Stress columns labeled (Pa) are auto-converted to (MPa)"
        )
        self.btn_ans.clicked.connect(self.load_ansys)
        top.addWidget(self.btn_ans)
        self.btn_ans_temp = QtWidgets.QPushButton("Load Node Temp File")
        self.btn_ans_temp.setToolTip(
            "Load a separate NodeID vs Temperature file and merge by NodeID.\n"
            "Use this when your ANSYS stress file has no temperature column.\n"
            "The temperature values must use the selected ANSYS T units.\n"
            "Expected columns (example): NodeID, Temp_C / TEMP_C / T(Â°C) / TEMP(Â°C) / TREF / BFE()\n"
            "Accepted separators: comma or tab\n"
            "If duplicate NodeIDs exist, the first occurrence is kept"
        )
        self.btn_ans_temp.clicked.connect(self.load_ansys_temp)
        self.btn_ans_temp.setVisible(False)
        top.addWidget(self.btn_ans_temp)
        top.addStretch()
        top.addWidget(QtWidgets.QLabel("ANSYS T units:"))
        self.combo_ans_units = QtWidgets.QComboBox()
        self.combo_ans_units.addItems(["C", "K"])
        self.combo_ans_units.setCurrentText("C")
        self.combo_ans_units.setMinimumWidth(140)
        self.combo_ans_units.setSizeAdjustPolicy(QtWidgets.QComboBox.SizeAdjustPolicy.AdjustToContents)
        self.combo_ans_units.setToolTip(
            "Units of the ANSYS temperature column:\n"
            "- C: values are in degrees Celsius\n"
            "- K: values are in Kelvin (will be converted to C)"
        )
        top.addWidget(self.combo_ans_units)
        top.addSpacing(16)
        top.addWidget(QtWidgets.QLabel("Stress units:"))
        self.combo_ans_stress_units = QtWidgets.QComboBox()
        self.combo_ans_stress_units.addItems(["MPa", "Pa"])
        self.combo_ans_stress_units.setCurrentText("MPa")
        self.combo_ans_stress_units.setMinimumWidth(140)
        self.combo_ans_stress_units.setSizeAdjustPolicy(QtWidgets.QComboBox.SizeAdjustPolicy.AdjustToContents)
        self.combo_ans_stress_units.setToolTip(
            "Units of the ANSYS stress column:\n"
            "- MPa: no conversion\n"
            "- Pa: converted to MPa (divide by 1e6)\n"
            "If the stress column name includes (Pa) or (MPa),\n"
            "the app will auto-convert and rename to MPa on load."
        )
        top.addWidget(self.combo_ans_stress_units)
        top.addSpacing(16)
        top.addWidget(QtWidgets.QLabel("Max preview rows:"))
        self.spin_ans_cap = QtWidgets.QSpinBox()
        self.spin_ans_cap.setRange(1000, 2000000)
        self.spin_ans_cap.setSingleStep(1000)
        self.spin_ans_cap.setValue(5000)
        self.spin_ans_cap.setToolTip("Limit ANSYS preview rows for performance (does not affect compute)")
        self.spin_ans_cap.valueChanged.connect(self._apply_ansys_preview)
        top.addWidget(self.spin_ans_cap)
        v.addLayout(top)

        form = QtWidgets.QFormLayout()
        self.cb_ans_node, self.cb_ans_stress, self.cb_ans_temp = QtWidgets.QComboBox(), QtWidgets.QComboBox(), QtWidgets.QComboBox()
        self.cb_ans_node.setToolTip("Select the node ID column")
        self.cb_ans_stress.setToolTip("Select the von Mises stress column")
        self.cb_ans_temp.setToolTip("Select the temperature column")
        form.addRow("Node ID column", self.cb_ans_node)
        form.addRow("Von Mises Stress column", self.cb_ans_stress)
        form.addRow("Temperature column", self.cb_ans_temp)

        self.chk_const_temp = QtWidgets.QCheckBox("Use constant temperature")
        self.chk_const_temp.setToolTip(
            "Use a single temperature for all nodes.\n"
            "Useful if the ANSYS file has no temperature column.\n"
            "Value is interpreted in the selected ANSYS T units."
        )
        self.txt_const_temp = QtWidgets.QLineEdit()
        self.txt_const_temp.setPlaceholderText("e.g. 25.0")
        self.txt_const_temp.setValidator(QtGui.QDoubleValidator(bottom=-1e9, top=1e9, decimals=6))
        self.txt_const_temp.setEnabled(False)
        self.txt_const_temp.setText("25.0")
        self.txt_const_temp.setToolTip(
            "Constant temperature applied to every node.\n"
            "Units follow the ANSYS T units setting (C or K)."
        )
        self.lbl_const_temp = QtWidgets.QLabel("Constant temperature value")
        self.chk_const_temp.toggled.connect(self._on_const_temp_toggled)
        self.chk_const_temp.toggled.connect(lambda: self._update_const_temp_column())
        self.txt_const_temp.textChanged.connect(lambda: self._update_const_temp_column())
        form.addRow(self.chk_const_temp)
        form.addRow(self.lbl_const_temp, self.txt_const_temp)
        v.addLayout(form)

        self.tbl_ans = QtWidgets.QTableView()
        if hasattr(self.tbl_ans, "setUniformRowHeights"):
            self.tbl_ans.setUniformRowHeights(True)
        self.tbl_ans.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.Stretch)
        self.tbl_ans.setToolTip("Preview of ANSYS results (sortable)")
        self._enable_table_copy(self.tbl_ans)
        self.model_ans = PandasModel()
        self.proxy_model_ans = QtCore.QSortFilterProxyModel()
        self.proxy_model_ans.setSourceModel(self.model_ans)
        self.tbl_ans.setModel(self.proxy_model_ans)
        self.tbl_ans.setSortingEnabled(True)
        v.addWidget(self.tbl_ans)
        self.tabs.addTab(w, "ANSYS Import")

    def _build_tab_compute(self):
        w = QtWidgets.QWidget()
        v = QtWidgets.QVBoxLayout(w)
        form = QtWidgets.QFormLayout()
        self.fs_spin = QtWidgets.QDoubleSpinBox()
        self.fs_spin.setRange(0.01, 1000.0)
        self.fs_spin.setDecimals(3)
        self.fs_spin.setValue(1.0)
        self.fs_spin.setToolTip("Factor of safety applied to strength: allowable = strength / FS")
        form.addRow("Factor of Safety (applied to Strength):", self.fs_spin)
        self.combo_extrap = QtWidgets.QComboBox()
        self.combo_extrap.addItems(["clamp", "linear", "error"])
        self.combo_extrap.setCurrentText("error")
        self.combo_extrap.setToolTip(
            "How to handle temperatures outside the material range:\n"
            "- clamp: use end values (flat)\n"
            "- linear: extend using end slopes\n"
            "- error: stop if any temp is out of range"
        )
        form.addRow("Extrapolation policy:", self.combo_extrap)
        v.addLayout(form)

        self.chk_percent = QtWidgets.QCheckBox("Output MoS in percent")
        self.chk_percent.setChecked(True)
        self.chk_percent.setToolTip(
            "If checked, MoS is reported as percent:\n"
            "MoS% = (1 - stress/allowable) Ã— 100\n"
            "Unchecked: MoS ratio = 1 - stress/allowable"
        )
        v.addWidget(self.chk_percent)

        v.addStretch()

        self.btn_compute = QtWidgets.QPushButton("Compute MoS")
        self.btn_compute.setToolTip("Run MoS calculation with current settings")
        self.btn_compute.clicked.connect(self.compute)
        v.addWidget(self.btn_compute)
        self.lbl_summary = QtWidgets.QLabel("Summary: N/A")
        self.lbl_summary.setToolTip(
            "Summary fields:\n"
            "- Rows: number of result rows\n"
            "- MoS < 0: count of negative margins\n"
            "- Worst Node: node with minimum MoS\n"
            "- Worst MoS: minimum MoS value\n"
            "- Strength: strength type used\n"
            "- Time: compute time"
        )
        v.addWidget(self.lbl_summary)

        v.addStretch()
        self.tabs.addTab(w, "Compute")

    def _build_tab_results(self):
        w = QtWidgets.QWidget()
        v = QtWidgets.QVBoxLayout(w)
        top = QtWidgets.QHBoxLayout()
        self.btn_export = QtWidgets.QPushButton("Export CSV")
        self.btn_export.setToolTip("Export full results to CSV")
        self.btn_export.clicked.connect(self.export_csv)
        top.addWidget(self.btn_export)
        self.chk_only_neg = QtWidgets.QCheckBox("Show MoS < 0 only")
        self.chk_only_neg.setToolTip("Filter the preview to only negative MoS values")
        self.chk_only_neg.toggled.connect(self._apply_filter)
        top.addWidget(self.chk_only_neg)
        top.addSpacing(12)
        top.addWidget(QtWidgets.QLabel("Go to node:"))
        self.txt_node_filter = QtWidgets.QLineEdit()
        self.txt_node_filter.setPlaceholderText("Node ID")
        self.txt_node_filter.setValidator(QtGui.QIntValidator())
        self.txt_node_filter.setMaximumWidth(140)
        self.txt_node_filter.setToolTip("Filter results to a specific NodeID")
        top.addWidget(self.txt_node_filter)
        self.btn_node_filter = QtWidgets.QPushButton("Go")
        self.btn_node_filter.setToolTip("Filter the results table to the specified NodeID")
        self.btn_node_filter.clicked.connect(self._apply_node_filter)
        top.addWidget(self.btn_node_filter)
        self.btn_node_clear = QtWidgets.QPushButton("Clear")
        self.btn_node_clear.setToolTip("Clear NodeID filter")
        self.btn_node_clear.clicked.connect(self._clear_node_filter)
        top.addWidget(self.btn_node_clear)
        self.btn_node_explain = QtWidgets.QPushButton("Explain")
        self.btn_node_explain.setToolTip(
            "Show step-by-step MoS calculation for the NodeID.\n"
            "Uses: Allowable = Strength / FS, MoS = 1 - Stress/Allowable\n"
            "If MoS% output is enabled: MoS% = MoS Ã— 100"
        )
        self.btn_node_explain.clicked.connect(self._explain_mos)
        top.addWidget(self.btn_node_explain)

        top.addStretch()
        top.addWidget(QtWidgets.QLabel("Max preview rows:"))
        self.spin_cap = QtWidgets.QSpinBox()
        self.spin_cap.setRange(1000, 2000000)
        self.spin_cap.setSingleStep(1000)
        self.spin_cap.setValue(5000)
        self.spin_cap.setToolTip("Limit preview rows for performance (does not affect export)")
        self.spin_cap.valueChanged.connect(self._apply_filter)
        top.addWidget(self.spin_cap)
        v.addLayout(top)

        self.tbl_out = QtWidgets.QTableView()
        if hasattr(self.tbl_out, "setUniformRowHeights"):
            self.tbl_out.setUniformRowHeights(True)
        self.tbl_out.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.Stretch)
        self.tbl_out.setToolTip("Preview of computed results (sortable)")
        self._enable_table_copy(self.tbl_out)
        self.model_out = PandasModel()
        self.proxy_model_out = QtCore.QSortFilterProxyModel()
        self.proxy_model_out.setSourceModel(self.model_out)
        self.tbl_out.setModel(self.proxy_model_out)
        self.tbl_out.setSortingEnabled(True)
        v.addWidget(self.tbl_out)
        self.tabs.addTab(w, "Results")

    def _enable_table_copy(self, table):
        self._copy_helpers.append(TableCopyHelper(table))

    def _on_const_temp_toggled(self, checked):
        self.txt_const_temp.setEnabled(bool(checked))
        self.lbl_const_temp.setEnabled(bool(checked))

    def _set_const_temp_controls_visible(self, visible):
        self.chk_const_temp.setVisible(bool(visible))
        self.lbl_const_temp.setVisible(bool(visible))
        self.txt_const_temp.setVisible(bool(visible))
        if not visible:
            self.chk_const_temp.setChecked(False)
            self._on_const_temp_toggled(False)
        else:
            self._on_const_temp_toggled(self.chk_const_temp.isChecked())

    def _apply_ansys_preview(self):
        if self.ansys_df.empty:
            self.model_ans.setDataFrame(pd.DataFrame())
            return
        view_df = self.ansys_df
        cap = self.spin_ans_cap.value()
        if len(view_df) > cap:
            view_df = view_df.head(cap)
        self.tbl_ans.setUpdatesEnabled(False)
        self.model_ans.setDataFrame(view_df.reset_index(drop=True))
        self.tbl_ans.setUpdatesEnabled(True)

    def _convert_location_units(self, df):
        # Convert X/Y/Z Location columns from meters to millimeters if labeled with "(m)"
        for axis in ("x", "y", "z"):
            for col in list(df.columns):
                name = str(col)
                lname = name.lower()
                if f"{axis} location" in lname and "(m)" in lname and "(mm)" not in lname:
                    new_name = re.sub(r"\(\s*m\s*\)", "(mm)", name, flags=re.I)
                    vals = pd.to_numeric(df[col], errors="coerce")
                    df[new_name] = vals * 1000.0
                    df.drop(columns=[col], inplace=True)
        return df

    def _update_const_temp_column(self):
        if self.has_real_temp:
            return
        if not self.chk_const_temp.isChecked():
            return
        if self.ansys_df.empty or not self.const_temp_col:
            return
        text = self.txt_const_temp.text().strip()
        if not text:
            return
        try:
            value = float(text)
        except ValueError:
            return
        self.ansys_df[self.const_temp_col] = value
        self._apply_ansys_preview()

    def _show_drop_hint(self, text):
        self.status.showMessage(f"Drop {text} here to load", 0)

    def _clear_drop_hint(self):
        self.status.clearMessage()

    # theme
    def _toggle_theme(self):
        self.dark_mode = not self.dark_mode
        self._apply_style()

    def _apply_style(self):
        dark_style = """
            QMainWindow, QWidget { background: #101012; color: #e5e5e5; }
            QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QTableView, QTextEdit {
                background: #1a1a1f; color: #e5e5e5; border: 1px solid #2a2a2f; padding: 4px;
            }
            QPushButton { background: #2a2a35; border: 1px solid #3a3a45; padding: 6px 10px; border-radius: 8px; }
            QPushButton:hover { background: #343444; }
            QHeaderView::section { background: #22222a; padding: 4px; border: none; border-bottom: 1px solid #3a3a45; }
            QTabWidget::pane { border: 1px solid #2a2a2f; }
            QTabBar::tab { padding: 8px 12px; }
        """
        light_style = """
            QMainWindow, QWidget { background: #fafafa; color: #111; }
            QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QTableView, QTextEdit {
                background: #ffffff; color: #111; border: 1px solid #cfcfcf; padding: 4px;
            }
            QPushButton { background: #f3f3f3; border: 1px solid #cfcfcf; padding: 6px 10px; border-radius: 8px; }
            QPushButton:hover { background: #e9e9e9; }
            QHeaderView::section { background: #f0f0f0; padding: 4px; border: 1px solid #dcdcdc; }
            QTabWidget::pane { border: 1px solid #dcdcdc; }
            QTabBar::tab { padding: 8px 12px; }
        """
        self.setStyleSheet(dark_style if self.dark_mode else light_style)

    # ---------- NEW ---: strength dropdown handler + auto-guess
    def _on_strength_type_changed(self):
        st = self.combo_strength_type.currentText().upper().strip()
        self.lbl_mat_strength.setText(f"Strength column ({st})")

        # If material already loaded, try to auto-guess a suitable column for the chosen type.
        if not self.material_df.empty:
            s_guess = guess_col(self.material_df, strength_patterns(st))
            if s_guess is not None:
                self.cb_mat_strength.setCurrentText(str(s_guess))

    # ---------- IO ----------
    def _read_any(self, path, autodetect_sep=False):
        ext = os.path.splitext(path)[1].lower()
        if ext in (".csv", ".txt"):
            if autodetect_sep:
                # Auto-detect tab/comma for ANSYS exports (no whitespace delimiter)
                looks_space_delimited = False
                try:
                    with open(path, "r", encoding="utf-8", errors="ignore") as f:
                        first_line = f.readline()
                    if first_line and ("\t" not in first_line) and ("," not in first_line):
                        if re.search(r"\S\s{2,}\S", first_line):
                            looks_space_delimited = True
                except Exception:
                    pass

                if not looks_space_delimited:
                    try:
                        return pd.read_csv(path, sep=None, engine="python")
                    except Exception:
                        pass
                for opts in ({"sep": "\t"}, {"sep": ","}):
                    try:
                        return pd.read_csv(path, **opts)
                    except Exception:
                        pass
                if looks_space_delimited:
                    QtWidgets.QMessageBox.warning(
                        self,
                        "Unsupported Separator",
                        "This file appears to be space-delimited.\n"
                        "Only comma or tab separators are supported."
                    )
            try:
                return pd.read_csv(path, engine="pyarrow")
            except Exception:
                return pd.read_csv(path)
        if ext in (".xlsx", ".xls"):
            return pd.read_excel(path)
        raise ValueError("Unsupported file type. Please use CSV or XLSX.")

    def load_material(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Open Material File", "", "Data Files (*.csv *.xlsx *.txt)")
        if not path: return
        self._load_material_path(path)

    def _load_material_path(self, path):
        t0 = time.perf_counter()
        try:
            df = self._read_any(path, autodetect_sep=True)
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Error", f"Failed to load material file:\n{e}")
            return

        self.material_df = df
        self.model_mat.setDataFrame(df)

        self.cb_mat_temp.clear()
        self.cb_mat_strength.clear()

        cols = [str(c) for c in df.columns]
        self.cb_mat_temp.addItems(cols)
        self.cb_mat_strength.addItems(cols)

        t_guess = guess_col(df, [r"temp"])
        if t_guess: self.cb_mat_temp.setCurrentText(str(t_guess))

        # --- CHANGED ---: strength guess depends on dropdown (YTS vs UTS)
        st = self.combo_strength_type.currentText().upper().strip()
        s_guess = guess_col(df, strength_patterns(st))
        if s_guess: self.cb_mat_strength.setCurrentText(str(s_guess))
        if s_guess:
            name = str(s_guess).lower()
            if "gpa" in name:
                self.combo_mat_strength_units.setCurrentText("GPa")
            elif "mpa" in name:
                self.combo_mat_strength_units.setCurrentText("MPa")
            elif "pa" in name:
                self.combo_mat_strength_units.setCurrentText("Pa")

        self.status.showMessage(f"Material loaded in {time.perf_counter()-t0:.2f}s: {os.path.basename(path)}", 5000)

    def _handle_material_drop(self, path):
        if not path:
            return
        if not self.material_df.empty:
            reply = QtWidgets.QMessageBox.question(
                self,
                "Replace Material Data?",
                "Dropping this file will replace the currently loaded material data.\n"
                "Do you want to continue?",
                QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No,
                QtWidgets.QMessageBox.StandardButton.No
            )
            if reply != QtWidgets.QMessageBox.StandardButton.Yes:
                return
        self._load_material_path(path)

    def load_ansys(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Open ANSYS File", "", "Data Files (*.csv *.xlsx *.txt)")
        if not path: return
        self._load_ansys_path(path)

    def _load_ansys_path(self, path):
        t0 = time.perf_counter()
        try:
            df = self._read_any(path, autodetect_sep=True)
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Error", f"Failed to load ANSYS file:\n{e}")
            return

        df = self._convert_location_units(df)

        node_g = guess_col(df, [r"node", r"nid", r"\bid\b"])
        stress_g = guess_col(df, [r"vm", r"von", r"mises", r"stress"])
        temp_g = guess_col(df, temp_patterns())
        stress_converted = False
        if stress_g:
            name = str(stress_g)
            lname = name.lower()
            if "mpa" in lname:
                self.combo_ans_stress_units.setCurrentText("MPa")
            elif ("pa" in lname) and ("kpa" not in lname) and ("gpa" not in lname):
                # Auto-convert Pa to MPa and rename column
                df[name] = pd.to_numeric(df[name], errors="coerce") / 1e6
                new_name = re.sub(r"\(\s*pa\s*\)", "(MPa)", name, flags=re.I)
                if new_name == name:
                    new_name = re.sub(r"\bpa\b", "MPa", name, flags=re.I)
                if new_name in df.columns:
                    i = 1
                    base = new_name
                    while f"{base}_{i}" in df.columns:
                        i += 1
                    new_name = f"{base}_{i}"
                df = df.rename(columns={name: new_name})
                stress_g = new_name
                self.combo_ans_stress_units.setCurrentText("MPa")
                stress_converted = True
        missing_temp = temp_g is None
        self.has_real_temp = not missing_temp
        self.const_temp_col = None
        if missing_temp:
            # Add a constant temperature column for visibility/selection
            const_name = "Temp_Const"
            if const_name in df.columns:
                i = 1
                while f"{const_name}_{i}" in df.columns:
                    i += 1
                const_name = f"{const_name}_{i}"
            text = self.txt_const_temp.text().strip()
            try:
                const_val = float(text) if text else 25.0
            except ValueError:
                const_val = 25.0
            df[const_name] = const_val
            temp_g = const_name
            self.const_temp_col = const_name

        self.ansys_df = df
        self.merged_temp_col = None

        self.cb_ans_node.clear()
        self.cb_ans_stress.clear()
        self.cb_ans_temp.clear()

        cols = [str(c) for c in df.columns]
        self.cb_ans_node.addItems(cols)
        self.cb_ans_stress.addItems(cols)
        self.cb_ans_temp.addItems(cols)
        if node_g: self.cb_ans_node.setCurrentText(str(node_g))
        if stress_g: self.cb_ans_stress.setCurrentText(str(stress_g))
        if temp_g: self.cb_ans_temp.setCurrentText(str(temp_g))
        if missing_temp:
            self._set_const_temp_controls_visible(True)
            self.chk_const_temp.setChecked(True)
            if not self.txt_const_temp.text().strip():
                self.txt_const_temp.setText("25.0")
            QtWidgets.QMessageBox.warning(
                self,
                "Temperature Column Not Found",
                "No temperature-like column was detected in the ANSYS file.\n"
                "Constant temperature mode was enabled automatically.\n"
                "You can also use the 'Load Node Temp File' button to merge a separate\n"
                "NodeID vs Temperature file if you have one.\n"
                f"Reminder: temperatures use the selected ANSYS T units ({self.combo_ans_units.currentText()})."
            )
        else:
            self.chk_const_temp.setChecked(False)
        # Hide constant-temp controls when a real temperature column exists
        self._set_const_temp_controls_visible(not self.has_real_temp)
        self.btn_ans_temp.setVisible(missing_temp)
        if stress_g and not stress_converted:
            name = str(stress_g).lower()
            if "mpa" in name:
                self.combo_ans_stress_units.setCurrentText("MPa")
            elif "pa" in name:
                self.combo_ans_stress_units.setCurrentText("Pa")

        self._apply_ansys_preview()
        self.status.showMessage(f"ANSYS loaded in {time.perf_counter()-t0:.2f}s: {os.path.basename(path)}", 5000)

    def load_ansys_temp(self):
        if self.ansys_df.empty:
            QtWidgets.QMessageBox.warning(self, "Missing Data", "Load the ANSYS stress file first.")
            return
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Open Node Temperature File", "", "Data Files (*.csv *.xlsx *.txt)")
        if not path: return
        self._load_ansys_temp_path(path)

    def _load_ansys_temp_path(self, path):
        t0 = time.perf_counter()
        try:
            df = self._read_any(path, autodetect_sep=True)
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Error", f"Failed to load temperature file:\n{e}")
            return

        node_g = guess_col(df, [r"node", r"nid", r"\bid\b"])
        temp_g = guess_col(df, temp_patterns())
        if node_g is None or temp_g is None:
            QtWidgets.QMessageBox.critical(
                self,
                "Missing Columns",
                "Could not detect Node ID and Temperature columns in the temperature file.\n"
                f"Columns found: {', '.join([str(c) for c in df.columns])}"
            )
            return

        node_col_main = self.cb_ans_node.currentText()
        if not node_col_main:
            QtWidgets.QMessageBox.warning(self, "Missing Node Column", "Select a Node ID column in ANSYS input.")
            return

        # Drop constant temperature column when merging real temperature data
        if self.const_temp_col and self.const_temp_col in self.ansys_df.columns:
            self.ansys_df = self.ansys_df.drop(columns=[self.const_temp_col])
            self.const_temp_col = None

        temp_sub = df[[node_g, temp_g]].copy()
        # Validate NodeID set match
        try:
            main_nodes = set(pd.to_numeric(self.ansys_df[node_col_main], errors="coerce").dropna().astype(float))
            temp_nodes = set(pd.to_numeric(temp_sub[node_g], errors="coerce").dropna().astype(float))
        except Exception:
            main_nodes = set(self.ansys_df[node_col_main].dropna().astype(str))
            temp_nodes = set(temp_sub[node_g].dropna().astype(str))
        if main_nodes != temp_nodes:
            only_main = len(main_nodes - temp_nodes)
            only_temp = len(temp_nodes - main_nodes)
            QtWidgets.QMessageBox.critical(
                self,
                "NodeID Mismatch",
                "The NodeID set in the temperature file does not match the ANSYS stress file.\n"
                f"Only in stress file: {only_main}\n"
                f"Only in temp file: {only_temp}\n"
                "Temperature merge was cancelled."
            )
            return
        if temp_sub[node_g].duplicated().any():
            temp_sub = temp_sub.drop_duplicates(subset=[node_g], keep="first")
            QtWidgets.QMessageBox.warning(
                self,
                "Duplicate Nodes",
                "Duplicate Node IDs were found in the temperature file.\n"
                "Keeping the first occurrence for each NodeID."
            )

        # Try to align types for merge
        try:
            self.ansys_df[node_col_main] = pd.to_numeric(self.ansys_df[node_col_main])
        except Exception:
            pass
        try:
            temp_sub[node_g] = pd.to_numeric(temp_sub[node_g])
        except Exception:
            pass

        # If a previous temp merge exists, drop it to replace cleanly
        if self.merged_temp_col and self.merged_temp_col in self.ansys_df.columns:
            self.ansys_df = self.ansys_df.drop(columns=[self.merged_temp_col])

        new_temp_col = str(temp_g)
        if new_temp_col in self.ansys_df.columns:
            new_temp_col = f"{new_temp_col}_from_file"
        temp_sub = temp_sub.rename(columns={temp_g: new_temp_col})

        merged = self.ansys_df.merge(temp_sub, how="left", left_on=node_col_main, right_on=node_g)
        if node_g != node_col_main:
            merged = merged.drop(columns=[node_g])

        missing = int(merged[new_temp_col].isna().sum())
        if missing > 0:
            QtWidgets.QMessageBox.warning(
                self,
                "Missing Temperatures",
                f"{missing} nodes did not find a matching temperature value."
            )

        self.ansys_df = merged
        self.const_temp_col = None
        self.merged_temp_col = new_temp_col

        # Refresh combo boxes and keep selections
        cur_node = self.cb_ans_node.currentText()
        cur_stress = self.cb_ans_stress.currentText()
        cols = [str(c) for c in merged.columns]
        self.cb_ans_node.clear()
        self.cb_ans_stress.clear()
        self.cb_ans_temp.clear()
        self.cb_ans_node.addItems(cols)
        self.cb_ans_stress.addItems(cols)
        self.cb_ans_temp.addItems(cols)
        if cur_node in cols: self.cb_ans_node.setCurrentText(cur_node)
        if cur_stress in cols: self.cb_ans_stress.setCurrentText(cur_stress)
        self.cb_ans_temp.setCurrentText(str(new_temp_col))

        self.chk_const_temp.setChecked(False)
        self.has_real_temp = True
        self._set_const_temp_controls_visible(False)
        self.btn_ans_temp.setVisible(False)
        self._apply_ansys_preview()
        self.status.showMessage(f"Temperature file merged in {time.perf_counter()-t0:.2f}s: {os.path.basename(path)}", 5000)

    def _handle_ansys_drop(self, path):
        if not path:
            return
        if self.ansys_df.empty:
            # If it looks like a temp-only file, warn and bail
            try:
                df = self._read_any(path, autodetect_sep=True)
            except Exception:
                self._load_ansys_path(path)
                return
            node_g = guess_col(df, [r"node", r"nid", r"\bid\b"])
            stress_g = guess_col(df, [r"vm", r"von", r"mises", r"stress"])
            temp_g = guess_col(df, [r"temp", r"t(c|k)"])
            if node_g is not None and temp_g is not None and stress_g is None:
                QtWidgets.QMessageBox.warning(
                    self,
                    "Temperature File Detected",
                    "This file looks like a NodeID vs Temperature file.\n"
                    "Load the ANSYS stress file first, then drop this file to merge temperatures."
                )
                return
            self._load_ansys_path(path)
            return

        # ANSYS already loaded: decide whether to merge temps or replace
        try:
            df = self._read_any(path, autodetect_sep=True)
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Error", f"Failed to read dropped file:\n{e}")
            return
        node_g = guess_col(df, [r"node", r"nid", r"\bid\b"])
        stress_g = guess_col(df, [r"vm", r"von", r"mises", r"stress"])
        temp_g = guess_col(df, temp_patterns())

        if node_g is not None and temp_g is not None and stress_g is None:
            self._load_ansys_temp_path(path)
        else:
            reply = QtWidgets.QMessageBox.question(
                self,
                "Replace ANSYS Data?",
                "Dropping this file will replace the currently loaded ANSYS stress data.\n"
                "Do you want to continue?",
                QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No,
                QtWidgets.QMessageBox.StandardButton.No
            )
            if reply == QtWidgets.QMessageBox.StandardButton.Yes:
                self._load_ansys_path(path)

    # ---------- compute ----------
    def compute(self):
        if self.material_df.empty or self.ansys_df.empty:
            QtWidgets.QMessageBox.warning(self, "Missing Data", "Please load both material and ANSYS files first.")
            return

        # --- CHANGED ---: map_mat uses 'strength' key now
        map_mat = {
            "temp": self.cb_mat_temp.currentText(),
            "strength": self.cb_mat_strength.currentText(),
        }
        map_ans = {
            "node": self.cb_ans_node.currentText(),
            "stress": self.cb_ans_stress.currentText(),
            "temp": self.cb_ans_temp.currentText(),
        }
        units = {
            "mat_T": self.combo_mat_units.currentText(),
            "ans_T": self.combo_ans_units.currentText(),
            "ans_stress": self.combo_ans_stress_units.currentText(),
            "mat_strength": self.combo_mat_strength_units.currentText(),
        }

        fs = self.fs_spin.value()
        extrap = self.combo_extrap.currentText()
        percent = self.chk_percent.isChecked()
        use_const_temp = self.chk_const_temp.isChecked()
        const_temp = None
        if use_const_temp:
            text = self.txt_const_temp.text().strip()
            if not text:
                QtWidgets.QMessageBox.warning(self, "Missing Constant Temperature",
                                              "Enter a constant temperature value.")
                return
            try:
                const_temp = float(text)
            except ValueError:
                QtWidgets.QMessageBox.warning(self, "Invalid Constant Temperature",
                                              "Constant temperature must be a number.")
                return

        # --- NEW ---: pass strength type to worker for output labeling
        strength_type = self.combo_strength_type.currentText().upper().strip()

        self.btn_compute.setEnabled(False)
        self.status.showMessage("Computingâ€¦")

        self.thread = QtCore.QThread()
        self.worker = ComputeWorker(
            self.material_df, self.ansys_df,
            map_mat, map_ans,
            units, fs, extrap,
            strength_type,
            percent,
            use_const_temp=use_const_temp,
            const_temp=const_temp
        )
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.finished.connect(self._on_compute_done)
        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        self.thread.start()

    @QtCore.pyqtSlot(pd.DataFrame, dict, str)
    def _on_compute_done(self, df, stats, err):
        self.btn_compute.setEnabled(True)
        if err:
            QtWidgets.QMessageBox.critical(self, "Compute Error", err)
            self.status.showMessage("Error", 5000)
            return

        self.results_df = df
        self.node_filter_id = None
        self.txt_node_filter.clear()
        self._apply_filter()

        st = stats.get("strength_type", "YTS")
        s = (f"Rows: {stats['rows']} | "
             f"MoS < 0: {stats['num_negative']} | "
             f"Worst Node: {stats['worst_node']} | "
             f"Worst MoS: {stats['worst_mos_percent']:.2f}% | "
             f"Strength: {st} | "
             f"Time: {stats['t_compute_s']:.2f}s")
        self.lbl_summary.setText(f"Summary: {s}")
        self.status.showMessage("Computation finished", 3000)
        self.tabs.setCurrentIndex(3)

    # ---------- preview filter ----------
    def _apply_filter(self):
        if self.results_df.empty:
            self.model_out.setDataFrame(pd.DataFrame())
            return

        col = "MoS_%" if "MoS_%" in self.results_df.columns else "MoS"
        view_df = self.results_df

        if self.node_filter_id is not None:
            if "NodeID" in view_df.columns:
                try:
                    series_num = pd.to_numeric(view_df["NodeID"], errors="coerce")
                    if series_num.notna().any():
                        view_df = view_df[series_num == self.node_filter_id]
                    else:
                        view_df = view_df[view_df["NodeID"].astype(str) == str(self.node_filter_id)]
                except Exception:
                    view_df = view_df[view_df["NodeID"].astype(str) == str(self.node_filter_id)]

        if self.chk_only_neg.isChecked():
            view_df = view_df[view_df[col] < 0]

        cap = self.spin_cap.value()
        if len(view_df) > cap:
            vals = view_df[col].to_numpy()
            k = min(cap, len(view_df))
            idx = np.argpartition(vals, k - 1)[:k]
            view_df = view_df.iloc[idx].sort_values(col)

        self.tbl_out.setUpdatesEnabled(False)
        self.model_out.setDataFrame(view_df.reset_index(drop=True))
        self.tbl_out.setUpdatesEnabled(True)

    def _apply_node_filter(self):
        if self.results_df.empty:
            QtWidgets.QMessageBox.information(self, "No Data", "Run a computation first.")
            return
        text = self.txt_node_filter.text().strip()
        if not text:
            self._clear_node_filter()
            return
        try:
            node_id = int(text)
        except ValueError:
            QtWidgets.QMessageBox.warning(self, "Invalid Node ID", "Node ID must be an integer.")
            return
        if "NodeID" not in self.results_df.columns:
            QtWidgets.QMessageBox.warning(self, "Missing NodeID", "Results do not contain a NodeID column.")
            return
        try:
            series_num = pd.to_numeric(self.results_df["NodeID"], errors="coerce")
            if series_num.notna().any():
                exists = (series_num == node_id).any()
            else:
                exists = (self.results_df["NodeID"].astype(str) == str(node_id)).any()
        except Exception:
            exists = (self.results_df["NodeID"].astype(str) == str(node_id)).any()
        if not exists:
            QtWidgets.QMessageBox.warning(self, "Node Not Found", f"Node ID {node_id} does not exist in results.")
            return
        self.node_filter_id = node_id
        self._apply_filter()

    def _clear_node_filter(self):
        self.node_filter_id = None
        self.txt_node_filter.clear()
        self._apply_filter()

    def _get_selected_result_row(self):
        sel = self.tbl_out.selectionModel()
        if sel is None:
            return None

        idx = self.tbl_out.currentIndex()
        if not idx.isValid():
            rows = sel.selectedRows()
            if rows:
                idx = rows[0]
            else:
                idxs = sel.selectedIndexes()
                if not idxs:
                    return None
                idx = idxs[0]

        source_idx = self.proxy_model_out.mapToSource(idx)
        row = source_idx.row()
        df_view = self.model_out._df
        if row < 0 or row >= len(df_view):
            return None
        return df_view.iloc[row].copy()

    def _get_selected_node_id(self):
        row = self._get_selected_result_row()
        if row is None or "NodeID" not in row.index:
            return None
        try:
            return int(float(row["NodeID"]))
        except Exception:
            return None

    def _find_result_row_by_node_id(self, node_id):
        if "NodeID" not in self.results_df.columns:
            return None
        try:
            series_num = pd.to_numeric(self.results_df["NodeID"], errors="coerce")
            if series_num.notna().any():
                row = self.results_df.loc[series_num == node_id]
            else:
                row = self.results_df.loc[self.results_df["NodeID"].astype(str) == str(node_id)]
        except Exception:
            row = self.results_df.loc[self.results_df["NodeID"].astype(str) == str(node_id)]
        if row.empty:
            return None
        return row.iloc[0].copy()

    def _get_explain_target_row(self):
        selected_row = self._get_selected_result_row()
        if selected_row is not None:
            return selected_row, None

        text = self.txt_node_filter.text().strip()
        if not text:
            return None, "No Node Selected"
        try:
            node_id = int(text)
        except ValueError:
            return None, "Invalid Node ID"

        row = self._find_result_row_by_node_id(node_id)
        if row is None:
            return None, "Node Not Found"
        return row, None

    def _explain_mos(self):
        if self.results_df.empty:
            QtWidgets.QMessageBox.information(self, "No Data", "Run a computation first.")
            return

        if "NodeID" not in self.results_df.columns:
            QtWidgets.QMessageBox.warning(self, "Missing NodeID", "Results do not contain a NodeID column.")
            return

        r, err = self._get_explain_target_row()
        if err == "No Node Selected":
            QtWidgets.QMessageBox.warning(self, "No Node Selected", "Enter a NodeID or select a row.")
            return
        if err == "Invalid Node ID":
            QtWidgets.QMessageBox.warning(self, "Invalid Node ID", "Node ID must be an integer.")
            return
        if err == "Node Not Found":
            QtWidgets.QMessageBox.warning(self, "Node Not Found", f"Node ID {self.txt_node_filter.text().strip()} does not exist in results.")
            return
        if r is None:
            QtWidgets.QMessageBox.warning(self, "No Node Selected", "Enter a NodeID or select a row.")
            return

        try:
            node_id = int(float(r.get("NodeID")))
        except Exception:
            node_id = str(r.get("NodeID", "N/A"))

        stress = r.get("Stress_MPa", np.nan)
        temp = r.get("Temp_C", np.nan)
        strength_col = None
        for c in self.results_df.columns:
            if str(c).endswith("_at_T_MPa"):
                strength_col = c
                break
        allowable_col = None
        for c in self.results_df.columns:
            if str(c).startswith("Allowable_") and str(c).endswith("_MPa"):
                allowable_col = c
                break

        strength = r.get(strength_col, np.nan) if strength_col else np.nan
        allowable = r.get(allowable_col, np.nan) if allowable_col else np.nan
        fs = None
        try:
            if allowable and np.isfinite(allowable):
                fs = float(strength) / float(allowable)
        except Exception:
            fs = None

        mos_col = "MoS_%" if "MoS_%" in self.results_df.columns else "MoS"
        mos_val = r.get(mos_col, np.nan)

        def fmt(v):
            try:
                if v is None or (isinstance(v, float) and np.isnan(v)):
                    return "N/A"
                return f"{float(v):.4f}"
            except Exception:
                return "N/A"

        ratio = None
        mos_ratio = None
        mos_percent = None
        try:
            if np.isfinite(stress) and np.isfinite(allowable) and float(allowable) != 0.0:
                ratio = float(stress) / float(allowable)
                mos_ratio = 1.0 - ratio
                mos_percent = mos_ratio * 100.0
        except Exception:
            ratio = mos_ratio = mos_percent = None

        lines = [
            f"NodeID: {node_id}",
            f"Stress = {fmt(stress)} MPa",
            f"Temp = {fmt(temp)} C",
        ]
        if strength_col:
            lines.append(f"Strength at T ({strength_col}) = {fmt(strength)} MPa")
        if allowable_col:
            lines.append(f"Allowable ({allowable_col}) = {fmt(allowable)} MPa")
        if fs is not None and np.isfinite(fs):
            lines.append(f"Factor of Safety = Strength / Allowable = {fs:.4f}")

        lines.append("")
        lines.append("Formula:")
        lines.append("Allowable = Strength / FS")
        lines.append("MoS = 1 - (Stress / Allowable)")
        if ratio is not None:
            lines.append(f"Stress / Allowable = {fmt(stress)} / {fmt(allowable)} = {fmt(ratio)}")
            lines.append(f"MoS = 1 - {fmt(ratio)} = {fmt(mos_ratio)}")
        if mos_col == "MoS_%":
            lines.append("MoS% = MoS * 100")
            if mos_percent is not None:
                lines.append(f"MoS% = {fmt(mos_ratio)} * 100 = {fmt(mos_percent)}")
            lines.append(f"Reported MoS% = {fmt(mos_val)}")
        else:
            lines.append(f"Reported MoS = {fmt(mos_val)}")

        QtWidgets.QMessageBox.information(self, "MoS Calculation", "\n".join(lines))

    # ---------- export ----------
    def export_csv(self):
        if self.results_df.empty:
            QtWidgets.QMessageBox.information(self, "No Data", "There is nothing to export.")
            return
        path, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Save Results CSV", "mos_results.csv", "CSV Files (*.csv)")
        if not path: return
        try:
            self.results_df.to_csv(path, index=False)
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Error", f"Failed to save file:\n{e}")
            return
        self.status.showMessage(f"Results saved to: {os.path.basename(path)}", 5000)


# ---------- main ----------
def main():
    app = QtWidgets.QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()

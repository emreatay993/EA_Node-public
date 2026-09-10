# File: app/dpf_dialog.py
"""
Qt dialog for importing strain directly from an Ansys ``.rst`` file via DPF.

The dialog only presents choices and validates them; the actual extraction is
done by :mod:`app.dpf_loader` (headless model layer). Keeping the two apart means
the loader stays unit-testable and this view stays free of analysis logic.
"""
import os
os.environ.setdefault("QT_API", "pyqt6")

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QComboBox, QLineEdit, QCheckBox,
    QLabel, QDialogButtonBox, QGroupBox,
)


class DpfImportDialog(QDialog):
    """Collects named selection / result sets / rotation options for a .rst import.

    Build it with the dict returned by :func:`app.dpf_loader.inspect_rst`. After
    ``exec()`` returns ``Accepted``, read the user's choices via
    :meth:`get_selection`.
    """

    WHOLE_MODEL = "(whole model)"

    def __init__(self, rst_path, meta, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Import Strain from .rst (DPF)")
        self.setMinimumWidth(460)
        self._meta = meta or {}

        layout = QVBoxLayout(self)

        # --- summary of the opened result file ---
        n_sets = int(self._meta.get("n_sets", 0) or 0)
        times = self._meta.get("times", []) or []
        unit = self._meta.get("unit", "") or "?"
        n_nodes = int(self._meta.get("n_nodes", 0) or 0)
        evaluation_shell_count = int(
            self._meta.get("stress_evaluation_shell_count", 0) or 0
        )
        names = list(self._meta.get("named_selections", []) or [])

        info = QGroupBox("Result File")
        info_layout = QVBoxLayout(info)
        lbl_file = QLabel(os.path.basename(str(rst_path)))
        lbl_file.setStyleSheet("font-weight: bold;")
        lbl_file.setToolTip(str(rst_path))
        times_str = ", ".join(f"{t:g}" for t in times[:12])
        if len(times) > 12:
            times_str += ", …"
        lbl_summary = QLabel(
            f"{n_nodes:,} nodes · {n_sets} result set(s) · mesh unit: {unit}"
            + (f"\nset times/freqs: {times_str}" if times_str else "")
        )
        lbl_summary.setWordWrap(True)
        info_layout.addWidget(lbl_file)
        info_layout.addWidget(lbl_summary)
        layout.addWidget(info)

        # --- selection controls ---
        form = QFormLayout()

        self.combo_ns = QComboBox()
        self.combo_ns.addItem(self.WHOLE_MODEL)
        self.combo_ns.addItems(names)
        self.combo_ns.setToolTip(
            "Scope extraction to a named selection (component) from the result\n"
            "file, or use the whole model. Strain gages sit on the free surface,\n"
            "so a surface/skin named selection usually gives the most relevant\n"
            "candidate points and a much faster analysis."
        )
        form.addRow("Named selection:", self.combo_ns)

        self.edit_sets = QLineEdit("all" if n_sets > 1 else "last")
        self.edit_sets.setToolTip(
            "Which result sets to treat as load cases. Each set becomes one load\n"
            "case, aggregated by the Aggregation control in the main window.\n"
            "Examples:  all   ·   last   ·   1,3,5   ·   1-4   ·   2-last"
        )
        form.addRow(f"Result sets (1–{max(n_sets, 1)}):", self.edit_sets)

        self.chk_rotate = QCheckBox("Rotate strains to global coordinate system")
        self.chk_rotate.setChecked(True)
        self.chk_rotate.setToolTip(
            "Rotate the strain tensors into the global Cartesian frame before\n"
            "analysis. Keep this on unless your gage angles are defined in the\n"
            "solver/elemental frame. The uniaxial angle sweep is performed in the\n"
            "global X–Y plane."
        )
        form.addRow("", self.chk_rotate)

        self.chk_ignore_evaluation_shells = QCheckBox(
            "Ignore stress/strain-evaluation-only SHELL181 results"
        )
        self.chk_ignore_evaluation_shells.setChecked(False)
        self.chk_ignore_evaluation_shells.setEnabled(evaluation_shell_count > 0)
        self.chk_ignore_evaluation_shells.setToolTip(
            "Exclude strain from SHELL181 elements whose KEYOPT(1)=2, and remove "
            "their unsupported faces from the contour. The RST contains {0} such "
            "element(s).".format(evaluation_shell_count)
        )
        form.addRow("", self.chk_ignore_evaluation_shells)

        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def get_selection(self):
        """Return named selection, set text, rotation, and shell-ignore choice."""
        ns = self.combo_ns.currentText()
        if ns == self.WHOLE_MODEL:
            ns = None
        return (
            ns,
            self.edit_sets.text().strip(),
            self.chk_rotate.isChecked(),
            self.chk_ignore_evaluation_shells.isChecked(),
        )

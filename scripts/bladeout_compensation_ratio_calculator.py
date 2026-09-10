# Purpose: Guided PyQt6 calculator for room/hot blade-out compensation ratios.
# Map: subsystems/supporting_runtime_assets
# Tests: tests/test_bladeout_compensation_ratio_calculator.py

from __future__ import annotations

import argparse
import math
import sys
from datetime import datetime
from typing import Sequence

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)


VALIDATION_MODE = "External-load stress validation"
UTILIZATION_MODE = "Strength / utilization screening"


def parse_number(text: str, label: str, *, positive: bool = True) -> float:
    """Parse a finite engineering input, accepting decimal comma or point."""
    normalized = text.strip().replace(" ", "").replace(",", ".")
    try:
        value = float(normalized)
    except ValueError as exc:
        raise ValueError(f"{label} must be a number.") from exc
    if not math.isfinite(value):
        raise ValueError(f"{label} must be finite.")
    if positive and value <= 0:
        raise ValueError(f"{label} must be greater than zero.")
    return value


def calculate_ratios(
    e_room: float,
    e_hot: float,
    strength_room: float | None = None,
    strength_hot: float | None = None,
) -> dict[str, float]:
    """Calculate modulus ratios and, when supplied, utilization-screening ratios."""
    for label, value in (("Room-temperature modulus", e_room), ("Hot modulus", e_hot)):
        if not math.isfinite(value) or value <= 0:
            raise ValueError(f"{label} must be finite and greater than zero.")

    results = {
        "stiffness_retention": e_hot / e_room,
        "strain_equivalence_multiplier": e_room / e_hot,
        "modulus_change_percent": (e_hot / e_room - 1.0) * 100.0,
    }

    if (strength_room is None) != (strength_hot is None):
        raise ValueError("Provide both room and hot strength values, or neither.")
    if strength_room is not None and strength_hot is not None:
        for label, value in (
            ("Room-temperature strength", strength_room),
            ("Hot strength", strength_hot),
        ):
            if not math.isfinite(value) or value <= 0:
                raise ValueError(f"{label} must be finite and greater than zero.")
        strength_retention = strength_hot / strength_room
        strength_ratio = strength_room / strength_hot
        results.update(
            strength_retention=strength_retention,
            strength_ratio=strength_ratio,
            strength_change_percent=(strength_retention - 1.0) * 100.0,
            utilization_screening_factor=strength_ratio * results["stiffness_retention"],
        )
    return results


def guidance_for_mode(mode: str) -> str:
    if mode == VALIDATION_MODE:
        return (
            "<b>Use for model-response validation.</b> Apply the traceable external blade-out "
            "interface-load snapshot, then compare the incremental room-temperature test response "
            "with the matching room-temperature FE response. <b>Do not apply a material strength "
            "ratio.</b> Use the modulus ratios only to interpret strain/displacement equivalence, "
            "or replace them with a separately justified paired-FE stress-response factor."
        )
    return (
        "<b>Use only as an elastic utilization screen.</b> The combined factor preserves a simple "
        "strength-utilization relationship under the entered material ratios. It is not a general "
        "stress-equivalence factor and does not replace paired room/hot FE response checks."
    )


def format_ratio(value: float) -> str:
    return f"{value:.4f}"


def build_summary(
    *,
    mode: str,
    material: str,
    assessment_point: str,
    room_temperature: float,
    hot_temperature: float,
    e_room: float,
    e_hot: float,
    results: dict[str, float],
    strength_basis: str = "",
    strength_room: float | None = None,
    strength_hot: float | None = None,
) -> str:
    lines = [
        "BLADE-OUT COMPENSATION RATIO CALCULATION",
        f"Generated: {datetime.now().astimezone().isoformat(timespec='minutes')}",
        f"Mode: {mode}",
        f"Material / specification: {material or '[not entered]'}",
        f"Assessment point: {assessment_point or '[not entered]'}",
        f"Temperatures: RT = {room_temperature:g} °C; hot = {hot_temperature:g} °C",
        f"Young's modulus: E_RT = {e_room:g} GPa; E_hot = {e_hot:g} GPa",
        "",
        f"Stiffness retention E_hot / E_RT = {format_ratio(results['stiffness_retention'])}",
        "Strain-equivalence multiplier E_RT / E_hot = "
        f"{format_ratio(results['strain_equivalence_multiplier'])}",
        f"Modulus change = {results['modulus_change_percent']:+.2f} %",
    ]
    if strength_room is not None and strength_hot is not None:
        lines.extend(
            [
                "",
                f"Strength basis: {strength_basis}",
                f"Strengths: S_RT = {strength_room:g} MPa; S_hot = {strength_hot:g} MPa",
                f"Strength retention S_hot / S_RT = {format_ratio(results['strength_retention'])}",
                f"Strength ratio S_RT / S_hot = {format_ratio(results['strength_ratio'])}",
                f"Strength change = {results['strength_change_percent']:+.2f} %",
                "Utilization screening factor (S_RT / S_hot) × (E_hot / E_RT) = "
                f"{format_ratio(results['utilization_screening_factor'])}",
                "",
                "Interpretation: screening only; not a general stress-equivalence factor.",
            ]
        )
    else:
        lines.extend(
            [
                "",
                "Strength ratio applied: NO",
                "Interpretation: validate the isolated external-load response against matching RT FE.",
            ]
        )
    return "\n".join(lines)


APP_STYLESHEET = """
QWidget { color: #17212b; font-family: "Segoe UI"; font-size: 10pt; }
QMainWindow, QWidget#page { background: #f3f6f9; }
QFrame#header { background: #17324d; border-radius: 10px; }
QLabel#title { color: white; font-size: 20pt; font-weight: 700; }
QLabel#subtitle { color: #d8e5f0; font-size: 10pt; }
QFrame.card { background: white; border: 1px solid #d6dee6; border-radius: 9px; }
QFrame.resultRow { background: #f7f9fb; border-radius: 5px; }
QLabel.sectionTitle { color: #17324d; font-size: 12pt; font-weight: 700; }
QLabel.fieldNote { color: #607080; font-size: 9pt; }
QLineEdit, QComboBox {
    background: white; border: 1px solid #aebdca; border-radius: 5px; padding: 7px; min-height: 22px;
}
QLineEdit:focus, QComboBox:focus { border: 2px solid #1b6ca8; padding: 6px; }
QLineEdit[invalid="true"] { border: 2px solid #b42318; background: #fff7f6; padding: 6px; }
QPushButton { border: 1px solid #9fb0bf; border-radius: 5px; padding: 8px 16px; background: #eef3f7; }
QPushButton:hover { background: #e2eaf1; }
QPushButton#primary { color: white; background: #1b6ca8; border-color: #1b6ca8; font-weight: 700; }
QPushButton#primary:hover { background: #155b8f; }
QPushButton:disabled { color: #8c99a5; background: #edf0f2; }
QLabel#guidance { background: #eef6fb; border-left: 4px solid #1b6ca8; padding: 12px; }
QLabel#status[status="error"] { color: #8a1c14; background: #fff0ee; border: 1px solid #f3b8b3; }
QLabel#status[status="ok"] { color: #17633a; background: #edf8f1; border: 1px solid #a8d8b9; }
QLabel#status[status="warning"] { color: #805400; background: #fff8e6; border: 1px solid #ecd38c; }
QLabel#status { border-radius: 5px; padding: 8px; }
QLabel.resultValue { color: #17324d; font-size: 15pt; font-weight: 700; }
QLabel.resultFormula { color: #607080; font-size: 9pt; }
"""


class BladeoutRatioWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Blade-Out Compensation Ratio Calculator")
        self.resize(1080, 760)
        self.setMinimumSize(820, 620)
        self._summary = ""
        self._result_widgets: dict[str, tuple[QWidget, QLabel]] = {}
        self._build_ui()
        self._update_mode()

    def _build_ui(self) -> None:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        central = QWidget(objectName="page")
        scroll.setWidget(central)
        self.setCentralWidget(scroll)

        root = QVBoxLayout(central)
        root.setContentsMargins(22, 22, 22, 22)
        root.setSpacing(14)

        header = QFrame(objectName="header")
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(20, 16, 20, 16)
        title = QLabel("Blade-Out Compensation Ratio Calculator", objectName="title")
        subtitle = QLabel(
            "Guided room-temperature / operating-temperature material ratios for external-load validation and utilization screening.",
            objectName="subtitle",
        )
        subtitle.setWordWrap(True)
        header_layout.addWidget(title)
        header_layout.addWidget(subtitle)
        root.addWidget(header)

        mode_card = self._card("1  Choose the engineering claim")
        mode_layout = mode_card.layout()
        self.mode_combo = QComboBox()
        self.mode_combo.addItems([VALIDATION_MODE, UTILIZATION_MODE])
        self.mode_combo.setToolTip(
            "Choose validation when comparing isolated external-load response. Choose utilization only when a strength-margin screen is intended."
        )
        self.mode_combo.setAccessibleName("Calculation mode")
        self.mode_combo.currentTextChanged.connect(self._update_mode)
        mode_layout.addWidget(self.mode_combo)
        self.guidance = QLabel(objectName="guidance")
        self.guidance.setWordWrap(True)
        self.guidance.setTextFormat(Qt.TextFormat.RichText)
        mode_layout.addWidget(self.guidance)
        root.addWidget(mode_card)

        columns = QGridLayout()
        columns.setHorizontalSpacing(14)
        columns.setVerticalSpacing(14)
        columns.setColumnStretch(0, 1)
        columns.setColumnStretch(1, 1)
        root.addLayout(columns)

        input_card = self._card("2  Enter approved material values")
        input_form = QFormLayout()
        input_form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        input_form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        input_card.layout().addLayout(input_form)

        self.material_edit = self._edit(
            "e.g. Ti6242 TMS01-030887",
            "Optional traceability field. Use the exact material specification and condition shared by both property values.",
            "Material or specification",
        )
        self.point_edit = self._edit(
            "e.g. HPC1 hot spot / node 123456",
            "Optional case, region, node, element, gauge, or assessed-section identifier.",
            "Assessment point",
        )
        self.room_temperature_edit = self._edit(
            "25",
            "Actual room/test temperature in °C. Temperature is recorded only; properties are entered directly.",
            "Room temperature",
        )
        self.hot_temperature_edit = self._edit(
            "350",
            "Operating temperature at the assessed location in °C. Temperature is recorded only; no interpolation is performed.",
            "Operating temperature",
        )
        self.e_room_edit = self._edit(
            "100",
            "Approved Young's modulus at the room/test temperature, in GPa.",
            "Room-temperature Young's modulus",
        )
        self.e_hot_edit = self._edit(
            "90",
            "Approved Young's modulus at the operating temperature, in GPa.",
            "Operating-temperature Young's modulus",
        )
        input_form.addRow("Material / specification", self.material_edit)
        input_form.addRow("Assessment point", self.point_edit)
        input_form.addRow("Room temperature [°C]", self.room_temperature_edit)
        input_form.addRow("Operating temperature [°C]", self.hot_temperature_edit)
        input_form.addRow("E at room temperature [GPa]", self.e_room_edit)
        input_form.addRow("E at operating temperature [GPa]", self.e_hot_edit)

        note = QLabel("Use values from the same approved material source, condition, and statistical basis.")
        note.setObjectName("fieldNote")
        note.setWordWrap(True)
        input_card.layout().addWidget(note)

        self.strength_frame = QFrame()
        strength_layout = QFormLayout(self.strength_frame)
        strength_layout.setContentsMargins(0, 10, 0, 0)
        strength_layout.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self.strength_basis_combo = QComboBox()
        self.strength_basis_combo.addItems(["Yield strength", "Tensile strength", "Custom allowable"])
        self.strength_basis_combo.setToolTip(
            "Select the same allowable basis for the room and operating strength values."
        )
        self.strength_basis_combo.setAccessibleName("Strength basis")
        self.strength_room_edit = self._edit(
            "900",
            "Approved room-temperature strength or allowable in MPa, using the selected basis.",
            "Room-temperature strength",
        )
        self.strength_hot_edit = self._edit(
            "600",
            "Approved operating-temperature strength or allowable in MPa, using the same basis.",
            "Operating-temperature strength",
        )
        strength_layout.addRow("Allowable basis", self.strength_basis_combo)
        strength_layout.addRow("Strength at room temperature [MPa]", self.strength_room_edit)
        strength_layout.addRow("Strength at operating temperature [MPa]", self.strength_hot_edit)
        input_card.layout().addWidget(self.strength_frame)
        columns.addWidget(input_card, 0, 0)

        result_card = self._card("3  Read the ratios and their meaning")
        self._add_result(
            result_card,
            "stiffness_retention",
            "Stiffness retention",
            "E_hot / E_RT",
            "Fraction of room-temperature stiffness retained at the operating temperature.",
        )
        self._add_result(
            result_card,
            "strain_equivalence_multiplier",
            "Strain-equivalence multiplier",
            "E_RT / E_hot",
            "A simple elastic strain/displacement equivalence ratio; not a general stress-equivalence factor.",
        )
        self._add_result(
            result_card,
            "strength_retention",
            "Strength retention",
            "S_hot / S_RT",
            "Fraction of the selected room-temperature strength retained at operating temperature.",
            strength_only=True,
        )
        self._add_result(
            result_card,
            "strength_ratio",
            "Strength ratio",
            "S_RT / S_hot",
            "Room-to-hot strength ratio. Do not apply this ratio in external-load stress-validation mode.",
            strength_only=True,
        )
        self._add_result(
            result_card,
            "utilization_screening_factor",
            "Utilization screening factor",
            "(S_RT / S_hot) × (E_hot / E_RT)",
            "Simple elastic utilization screen only; it does not prove stress-response equivalence.",
            strength_only=True,
        )
        columns.addWidget(result_card, 0, 1)

        guide_card = self._card("4  Process guide")
        guide = QLabel(
            "<b>1.</b> Define the claim before choosing a ratio.<br>"
            "<b>2.</b> Use approved properties for the same material, condition, direction, and basis.<br>"
            "<b>3.</b> For external-load validation, compare incremental test response with matching RT FE; do not add a strength ratio.<br>"
            "<b>4.</b> For utilization screening, retain the formula and source values with the result.<br>"
            "<b>5.</b> Check proportional response, unchanged contact state, and no unintended yielding before scaling results."
        )
        guide.setWordWrap(True)
        guide.setTextFormat(Qt.TextFormat.RichText)
        guide.setToolTip("A short workflow for using the ratios without changing the engineering claim.")
        guide_card.layout().addWidget(guide)
        columns.addWidget(guide_card, 1, 0, 1, 2)

        self.status = QLabel("Enter values, then select Calculate.", objectName="status")
        self.status.setWordWrap(True)
        self.status.setAccessibleName("Calculation status")
        root.addWidget(self.status)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        reset_button = QPushButton("Reset")
        reset_button.setToolTip("Clear all inputs and results.")
        reset_button.clicked.connect(self._reset)
        self.copy_button = QPushButton("Copy summary")
        self.copy_button.setToolTip("Copy the traceable inputs, formulas, ratios, and interpretation to the clipboard.")
        self.copy_button.setEnabled(False)
        self.copy_button.clicked.connect(self._copy_summary)
        calculate_button = QPushButton("Calculate", objectName="primary")
        calculate_button.setToolTip("Validate the inputs and calculate the ratios for the selected engineering claim.")
        calculate_button.setDefault(True)
        calculate_button.clicked.connect(self._calculate)
        buttons.addWidget(reset_button)
        buttons.addWidget(self.copy_button)
        buttons.addWidget(calculate_button)
        root.addLayout(buttons)

    @staticmethod
    def _card(title: str) -> QFrame:
        card = QFrame()
        card.setProperty("class", "card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)
        heading = QLabel(title)
        heading.setProperty("class", "sectionTitle")
        layout.addWidget(heading)
        return card

    @staticmethod
    def _edit(placeholder: str, tooltip: str, accessible_name: str) -> QLineEdit:
        edit = QLineEdit()
        edit.setPlaceholderText(placeholder)
        edit.setToolTip(tooltip)
        edit.setAccessibleName(accessible_name)
        edit.textChanged.connect(lambda: BladeoutRatioWindow._mark_invalid(edit, False))
        return edit

    def _add_result(
        self,
        card: QFrame,
        key: str,
        title: str,
        formula: str,
        tooltip: str,
        *,
        strength_only: bool = False,
    ) -> None:
        row = QFrame()
        row.setProperty("class", "resultRow")
        layout = QGridLayout(row)
        layout.setContentsMargins(0, 5, 0, 5)
        name = QLabel(title)
        value = QLabel("—")
        value.setProperty("class", "resultValue")
        value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        detail = QLabel(formula)
        detail.setProperty("class", "resultFormula")
        layout.addWidget(name, 0, 0)
        layout.addWidget(value, 0, 1)
        layout.addWidget(detail, 1, 0, 1, 2)
        row.setToolTip(tooltip)
        row.setAccessibleName(f"{title}: {formula}")
        row.setProperty("strengthOnly", strength_only)
        card.layout().addWidget(row)
        self._result_widgets[key] = (row, value)

    @staticmethod
    def _mark_invalid(edit: QLineEdit, invalid: bool) -> None:
        edit.setProperty("invalid", invalid)
        edit.style().unpolish(edit)
        edit.style().polish(edit)

    def _update_mode(self) -> None:
        utilization = self.mode_combo.currentText() == UTILIZATION_MODE
        self.strength_frame.setVisible(utilization)
        for row, _value in self._result_widgets.values():
            if row.property("strengthOnly"):
                row.setVisible(utilization)
        self.guidance.setText(guidance_for_mode(self.mode_combo.currentText()))
        self._clear_results()

    def _read(self, edit: QLineEdit, label: str, *, positive: bool = True) -> float:
        try:
            value = parse_number(edit.text(), label, positive=positive)
            if not positive and value <= -273.15:
                raise ValueError(f"{label} must be above absolute zero.")
        except ValueError:
            self._mark_invalid(edit, True)
            edit.setFocus()
            raise
        self._mark_invalid(edit, False)
        return value

    def _calculate(self) -> None:
        for edit in (
            self.room_temperature_edit,
            self.hot_temperature_edit,
            self.e_room_edit,
            self.e_hot_edit,
            self.strength_room_edit,
            self.strength_hot_edit,
        ):
            self._mark_invalid(edit, False)
        try:
            room_temperature = self._read(
                self.room_temperature_edit, "Room temperature", positive=False
            )
            hot_temperature = self._read(
                self.hot_temperature_edit, "Operating temperature", positive=False
            )
            e_room = self._read(self.e_room_edit, "Room-temperature Young's modulus")
            e_hot = self._read(self.e_hot_edit, "Operating-temperature Young's modulus")
            strength_room = strength_hot = None
            if self.mode_combo.currentText() == UTILIZATION_MODE:
                strength_room = self._read(
                    self.strength_room_edit, "Room-temperature strength"
                )
                strength_hot = self._read(
                    self.strength_hot_edit, "Operating-temperature strength"
                )
            results = calculate_ratios(e_room, e_hot, strength_room, strength_hot)
        except ValueError as exc:
            self._set_status(str(exc), "error")
            self._clear_results()
            return

        for key, (_row, value) in self._result_widgets.items():
            value.setText(format_ratio(results[key]) if key in results else "—")

        self._summary = build_summary(
            mode=self.mode_combo.currentText(),
            material=self.material_edit.text().strip(),
            assessment_point=self.point_edit.text().strip(),
            room_temperature=room_temperature,
            hot_temperature=hot_temperature,
            e_room=e_room,
            e_hot=e_hot,
            results=results,
            strength_basis=self.strength_basis_combo.currentText(),
            strength_room=strength_room,
            strength_hot=strength_hot,
        )
        self.copy_button.setEnabled(True)
        if hot_temperature <= room_temperature:
            self._set_status(
                "Calculated. Check the temperatures: the operating value is not above the room/test value.",
                "warning",
            )
        elif self.mode_combo.currentText() == VALIDATION_MODE:
            self._set_status(
                "Calculated. No material strength ratio is applied in external-load stress-validation mode.",
                "ok",
            )
        else:
            self._set_status(
                "Calculated. Treat the combined factor as an elastic utilization screen, not stress equivalence.",
                "warning",
            )

    def _clear_results(self) -> None:
        for _row, value in self._result_widgets.values():
            value.setText("—")
        self._summary = ""
        if hasattr(self, "copy_button"):
            self.copy_button.setEnabled(False)

    def _reset(self) -> None:
        self.mode_combo.setCurrentIndex(0)
        for edit in (
            self.material_edit,
            self.point_edit,
            self.room_temperature_edit,
            self.hot_temperature_edit,
            self.e_room_edit,
            self.e_hot_edit,
            self.strength_room_edit,
            self.strength_hot_edit,
        ):
            edit.clear()
            self._mark_invalid(edit, False)
        self.strength_basis_combo.setCurrentIndex(0)
        self._clear_results()
        self._set_status("Enter values, then select Calculate.", "")

    def _copy_summary(self) -> None:
        if self._summary:
            QApplication.clipboard().setText(self._summary)
            self._set_status("Calculation summary copied to the clipboard.", "ok")

    def _set_status(self, text: str, status: str) -> None:
        self.status.setText(text)
        self.status.setProperty("status", status)
        self.status.style().unpolish(self.status)
        self.status.style().polish(self.status)


def self_test() -> int:
    results = calculate_ratios(100.0, 90.0, 900.0, 600.0)
    assert math.isclose(results["stiffness_retention"], 0.9)
    assert math.isclose(results["strain_equivalence_multiplier"], 1.0 / 0.9)
    assert math.isclose(results["strength_ratio"], 1.5)
    assert math.isclose(results["utilization_screening_factor"], 1.35)
    assert math.isclose(parse_number("100,5", "value"), 100.5)
    assert "Do not apply a material strength ratio" in guidance_for_mode(VALIDATION_MODE)
    try:
        calculate_ratios(0.0, 90.0)
    except ValueError:
        pass
    else:  # pragma: no cover - defensive self-test failure branch
        raise AssertionError("Zero modulus must be rejected.")
    print("bladeout compensation ratio calculator self-test: PASS")
    return 0


def run_gui(*, smoke: bool = False) -> int:
    app = QApplication.instance() or QApplication([sys.argv[0]])
    app.setApplicationName("Blade-Out Compensation Ratio Calculator")
    app.setStyle("Fusion")
    app.setStyleSheet(APP_STYLESHEET)
    window = BladeoutRatioWindow()
    window.show()
    if smoke:
        app.processEvents()
        assert window.isVisible()
        assert window.mode_combo.count() == 2
        window.close()
        print("bladeout compensation ratio calculator GUI smoke: PASS")
        return 0
    return app.exec()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true", help="Run pure calculation checks and exit.")
    parser.add_argument("--smoke", action="store_true", help="Construct the GUI, process events, and exit.")
    args = parser.parse_args(argv)
    if args.self_test:
        return self_test()
    return run_gui(smoke=args.smoke)


if __name__ == "__main__":
    raise SystemExit(main())

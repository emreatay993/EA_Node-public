"""GUI smoke tests for scripts/equivalent_static_load (offscreen Qt)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.gui


@pytest.fixture()
def esl_window(qt_app=None):
    from PyQt6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication(["test"])
    from scripts.equivalent_static_load.gui import MainWindow

    window = MainWindow()
    yield window
    window.close()


def test_window_builds_all_steps(esl_window) -> None:
    assert esl_window.rail.count() == 7
    assert esl_window.pages.count() == 7


def test_config_round_trip_through_widgets(esl_window, tmp_path: Path) -> None:
    from scripts.equivalent_static_load.synthetic import make_synthetic

    make_synthetic(tmp_path, n_nodes=50, n_modes=3, n_channels=2, n_times=100)
    raw = json.loads((tmp_path / "config.json").read_text())
    esl_window.apply_raw_config(raw, tmp_path)
    collected = esl_window.collect_raw_config()

    assert collected["rig"]["channels"][0]["name"] == raw["rig"]["channels"][0]["name"]
    assert collected["rig"]["channels"][1]["case_label"] == "Case2"
    assert collected["msup"]["modal_stress_csv"].endswith("modal_stress.csv")
    assert Path(collected["msup"]["modal_stress_csv"]).is_absolute()
    assert collected["instants"]["n_suggestions"] == raw["instants"]["n_suggestions"]
    assert collected["solve"]["region"]["mode"] == raw["solve"]["region"]["mode"]
    # Loaded relative paths must be absolutized against the config dir.
    assert str(tmp_path) in collected["msup"]["modal_coordinates"]


def test_every_interactive_widget_has_rich_tooltip(esl_window) -> None:
    """No ambiguity rule: every input/action widget carries an HTML tooltip."""
    from PyQt6 import QtWidgets

    widgets = [
        # page 1
        esl_window.title_edit, esl_window.unit_force, esl_window.unit_moment,
        esl_window.unit_stress, esl_window.unit_length,
        esl_window.modal_stress_row, esl_window.mcf_row, esl_window.modal_forces_row,
        esl_window.steady_row, esl_window.include_bias_cb,
        esl_window.unit_layout_combo, esl_window.unit_csv_row, esl_window.unit_rst_row,
        esl_window.history_row, esl_window.mars_max_row, esl_window.mars_time_row,
        # page 2
        esl_window.channel_table,
        # page 3
        esl_window.coord_tol, esl_window.kdtree_dist, esl_window.min_id_frac,
        esl_window.check_button, esl_window.mapping_label,
        esl_window.region_mode, esl_window.region_value, esl_window.region_nodes_row,
        esl_window.bbox_edit, esl_window.weighting_combo, esl_window.vm_exponent,
        esl_window.tikhonov, esl_window.under_test_tol, esl_window.vm_floor,
        esl_window.min_peak_ratio, esl_window.rt_factor, esl_window.rt_note,
        # page 4
        esl_window.instants_mode, esl_window.explicit_times, esl_window.n_suggestions,
        esl_window.quadrature_cb, esl_window.hotspot_pct, esl_window.cluster_dt,
        esl_window.suggest_button, esl_window.instants_table,
        # page 5
        esl_window.tier_combo, esl_window.pattern_row, esl_window.outdir_row,
        esl_window.derive_button,
        # page 6
        esl_window.case_combo, esl_window.result_tier_combo,
        esl_window.metrics_label, esl_window.loads_table, esl_window.hotspots_table,
        # page 7
        esl_window.verify_case_combo, esl_window.solved_row, esl_window.verify_button,
        # chrome
        esl_window.status_label, esl_window.log_view, esl_window.progress,
        esl_window.rail,
    ]
    missing = [
        w.__class__.__name__ + ":" + (w.objectName() or repr(w))
        for w in widgets
        if not w.toolTip().startswith("<html>")
    ]
    assert not missing, f"widgets without rich tooltips: {missing}"

    # QLabel form labels must carry tooltips too (hover targets).
    unlabeled = [
        label.text()
        for label in esl_window.findChildren(QtWidgets.QLabel)
        if label.text() and not label.toolTip()
        and label.objectName() not in ("TitleLabel",)
        and label.parent() is not None
        and not label.text().startswith(("Checked rows", "bounds:", "Apply the derived",
                                         "Runs:", "Run a derivation"))
        and label.objectName() != "SectionTitle"
    ]
    assert not unlabeled, f"form labels without tooltips: {unlabeled}"


def test_table_headers_and_steps_have_tooltips(esl_window) -> None:
    for table, n_expected in (
        (esl_window.channel_table, 16),
        (esl_window.instants_table, 6),
        (esl_window.loads_table, 6),
        (esl_window.hotspots_table, 6),
    ):
        with_tips = sum(
            1
            for col in range(table.columnCount())
            if (item := table.horizontalHeaderItem(col)) is not None and item.toolTip()
        )
        assert with_tips == n_expected, table

    for row in range(esl_window.rail.count()):
        assert esl_window.rail.item(row).toolTip().startswith("<html>")


def test_tooltip_formulas_present(esl_window) -> None:
    """Spot-check that the key formulas render as HTML in the tooltips."""
    derive_tip = esl_window.derive_button.toolTip()
    assert "&sigma;<sub>c</sub>(t*)" in derive_tip          # reconstruction formula
    tier_tip = None
    # tier combo tooltip holds both route formulas + the exact-ESL anchor
    tier_tip = esl_window.tier_combo.toolTip()
    assert "f<sub>ESL</sub>" in tier_tip
    assert "&lambda;" in tier_tip
    verify_tip = esl_window.verify_button.toolTip()
    assert "&lambda;<sub>corr</sub>" in verify_tip
    quad_tip = esl_window.quadrature_cb.toolTip()
    assert "1 / (4&middot;f&#8320;)" in quad_tip


def test_filerow_missing_path_highlight(esl_window, tmp_path: Path) -> None:
    row = esl_window.modal_stress_row
    row.set_path(str(tmp_path / "does_not_exist.csv"))
    assert row.is_missing()
    real = tmp_path / "exists.csv"
    real.write_text("NodeID\n1\n")
    row.set_path(str(real))
    assert not row.is_missing()
    row.set_path("")
    assert not row.is_missing()


def test_missing_inputs_listed_for_template_config(esl_window, tmp_path: Path) -> None:
    template = Path(__file__).resolve().parents[1] / (
        "scripts/equivalent_static_load/example_config.json"
    )
    raw = json.loads(template.read_text(encoding="utf-8"))
    esl_window.apply_raw_config(raw, template.parent)
    missing = esl_window._missing_inputs()
    assert any("Modal stress CSV" in entry for entry in missing)
    assert any("modal_stress_w_coords.csv" in entry for entry in missing)


def test_example_config_loads_with_no_missing_files(esl_window) -> None:
    example = esl_window._example_config_path()
    assert example.is_file(), "mockup example missing from the repo"
    raw = json.loads(example.read_text(encoding="utf-8"))
    esl_window.apply_raw_config(raw, example.parent)
    assert esl_window._missing_inputs() == []


def test_friendly_error_strips_exception_prefix() -> None:
    from scripts.equivalent_static_load.gui import _friendly_error

    trace = (
        "Traceback (most recent call last):\n"
        "  ...\n"
        "scripts.equivalent_static_load.core.InputError: Modal stress CSV not "
        "found: C:\\some\\missing.csv"
    )
    message = _friendly_error(trace)
    assert message.startswith("Modal stress CSV not found: C:\\some\\missing.csv")
    assert "scripts.equivalent_static_load.core" not in message
    assert "Load Example" in message  # missing-file hint appended


def test_checked_instants_extraction(esl_window) -> None:
    from PyQt6 import QtCore, QtWidgets

    table = esl_window.instants_table
    table.setRowCount(2)
    for row, (checked, time) in enumerate(((True, "0.0123"), (False, "0.0456"))):
        use = QtWidgets.QTableWidgetItem()
        use.setFlags(QtCore.Qt.ItemFlag.ItemIsUserCheckable | QtCore.Qt.ItemFlag.ItemIsEnabled)
        use.setCheckState(
            QtCore.Qt.CheckState.Checked if checked else QtCore.Qt.CheckState.Unchecked
        )
        table.setItem(row, 0, use)
        table.setItem(row, 1, QtWidgets.QTableWidgetItem(time))
    assert esl_window._checked_instants() == [0.0123]

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "rst_subset_tool.py"


def load_tool_module():
    spec = importlib.util.spec_from_file_location("rst_subset_tool", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_delete_ranges_keep_requested_sets_only() -> None:
    tool = load_tool_module()

    assert tool.delete_ranges(6, (2, 5)) == [(1, 1), (3, 4), (6, 6)]
    assert tool.delete_ranges(3, (1, 2, 3)) == []


def test_match_time_set_ids_uses_existing_sets_only() -> None:
    tool = load_tool_module()

    assert tool.match_time_set_ids((0.0, 0.1, 0.2), (0.1, 0.2), 1.0e-8) == (2, 3)

    try:
        tool.match_time_set_ids((0.0, 0.1, 0.2), (0.15,), 1.0e-8)
    except ValueError as exc:
        assert "No stored result set matches time" in str(exc)
    else:  # pragma: no cover - defensive assertion
        raise AssertionError("Expected non-stored time to fail.")


def test_build_hybrid_apdl_deck_trims_time_and_splits_named_selection() -> None:
    tool = load_tool_module()

    deck = tool.build_apdl_deck(
        total_sets=6,
        keep_set_ids=(2, 5),
        named_selection="MY_NS",
        result_items=("BASIC", "NLOAD"),
    )

    assert "FILEAUX3,source,rst" in deck
    assert "DELETE,SET,1,1" in deck
    assert "DELETE,SET,3,4" in deck
    assert "DELETE,SET,6,6" in deck
    assert "SET,LAST" in deck
    assert "INRES,BASIC,NLOAD" in deck
    assert "CMSEL,S,MY_NS" in deck
    assert "ESLN,S,0,ALL" in deck
    assert "NSLE,S,ALL" in deck
    assert "RSPLIT,ALL,ESEL,RSTSUBSET" in deck
    assert "*MSG,FATAL" in deck


def test_result_item_mapper_uses_conservative_inres_groups() -> None:
    tool = load_tool_module()

    labels, unmapped, sources = tool.map_available_results_to_inres(
        ("displacement", "stress", "elastic_strain", "reaction_force", "custom_result")
    )

    assert labels == ("ALL", "BASIC", "NSOL", "RSOL", "STRS", "EPEL")
    assert unmapped == ("custom_result",)
    assert dict(sources)["STRS"] == ("stress",)


def test_dry_run_writes_deck_without_dpf_or_mapdl(tmp_path: Path) -> None:
    tool = load_tool_module()
    rst = tmp_path / "file.rst"
    out = tmp_path / "subset.rst"
    deck = tmp_path / "subset.inp"
    rst.write_bytes(b"fake rst")

    rc = tool.main(
        [
            "--rst",
            str(rst),
            "--out",
            str(out),
            "--named-selection",
            "MY_NS",
            "--all-time-sets",
            "--dry-run",
            "--deck-out",
            str(deck),
        ]
    )

    assert rc == 0
    assert deck.exists()
    assert "CMSEL,S,MY_NS" in deck.read_text(encoding="utf-8")
    assert not out.exists()


def test_gui_config_builds_cli_namespace(tmp_path: Path) -> None:
    tool = load_tool_module()
    rst = tmp_path / "file.rst"
    out = tmp_path / "subset.rst"
    deck = tmp_path / "subset.inp"

    args = tool.gui_config_to_namespace(
        tool.GuiRunConfig(
            rst=str(rst),
            out=str(out),
            named_selection="MY_NS",
            time_mode="sets",
            set_ids="2,5",
            result_items="BASIC,NLOAD",
            deck_out=str(deck),
            dry_run=True,
            overwrite=True,
        )
    )

    assert args.rst == rst
    assert args.out == out
    assert args.named_selection == "MY_NS"
    assert args.all_time_sets is False
    assert args.set_ids == "2,5"
    assert args.times is None
    assert args.result_items == "BASIC,NLOAD"
    assert args.deck_out == deck
    assert args.dry_run is True
    assert args.overwrite is True


def test_gui_result_item_selector_uses_scanned_metadata(monkeypatch) -> None:
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    tool = load_tool_module()
    from PyQt6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication(["rst-subset-test"])
    app.setStyle("Fusion")
    app.setPalette(tool.engineering_palette())
    app.setStyleSheet(tool.application_stylesheet())
    window = tool.RstSubsetWindow()
    window._metadata_loaded(
        tool.RstMetadata(
            set_ids=(1,),
            times=(0.0,),
            named_selections=("MY_NS",),
            available_results=("stress", "elemental_nodal_forces"),
            result_items=("ALL", "BASIC", "NLOAD", "STRS"),
            unmapped_results=("custom_result",),
            result_item_sources=(("NLOAD", ("elemental_nodal_forces",)), ("STRS", ("stress",))),
        )
    )

    assert window._config().named_selection == ""
    assert window._config().result_items == "ALL"
    window.named_selection_combo.setCurrentIndex(1)
    assert window._config().named_selection == ""

    labels = list(window.result_item_actions)
    assert labels == ["ALL", "BASIC", "NSOL", "NLOAD", "STRS"]
    assert window._config().result_items == "ALL"

    window.result_item_actions["NLOAD"].setChecked(True)
    window.result_item_actions["STRS"].setChecked(True)

    assert window._config().result_items == "ALL"
    window.spatial_subset_checkbox.setChecked(True)
    assert window._config().named_selection == "MY_NS"
    assert window._config().result_items == "NSOL"
    window.result_item_actions["NLOAD"].setChecked(True)
    window.result_item_actions["STRS"].setChecked(True)
    assert window._config().result_items == "NSOL,NLOAD,STRS"
    window.advanced_result_items_checkbox.setChecked(True)
    window.result_items_edit.setText("BASIC,NLOAD")
    assert window._config().result_items == "BASIC,NLOAD"
    window.spatial_subset_checkbox.setChecked(False)
    assert window._config().named_selection == ""
    assert window._config().result_items == "ALL"
    window.spatial_subset_checkbox.setChecked(True)
    window.named_selection_combo.setCurrentIndex(0)
    assert window._config().result_items == "ALL"
    window.named_selection_combo.setEditText("MY_TYPED_COMPONENT")
    assert window._config().named_selection == "MY_TYPED_COMPONENT"
    window.spatial_subset_checkbox.setChecked(False)
    window.metadata_list.item(0).setSelected(True)
    assert window.set_ids_radio.isChecked()
    assert window.set_ids_edit.text() == "1"
    window.close()


def test_no_args_dispatches_to_gui_without_opening_window(monkeypatch) -> None:
    tool = load_tool_module()
    called: list[object] = []

    def fake_run_app(argv=None):  # noqa: ANN001
        called.append(argv)
        return 17

    monkeypatch.setattr(tool, "run_app", fake_run_app)

    assert tool.main([]) == 17
    assert called


def test_self_test_smoke_path() -> None:
    tool = load_tool_module()

    assert tool.main(["--self-test"]) == 0


def test_short_window_keeps_extraction_controls_readable(monkeypatch) -> None:
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    tool = load_tool_module()
    from PyQt6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication(["rst-subset-test"])
    app.setStyle("Fusion")
    app.setPalette(tool.engineering_palette())
    app.setStyleSheet(tool.application_stylesheet())
    window = tool.RstSubsetWindow()
    window.resize(1120, 520)
    window.show()
    app.processEvents()

    assert window.named_selection_combo.height() >= 28
    assert window.set_ids_edit.height() >= 28
    assert window.times_edit.height() >= 28
    assert window.result_items_button.height() >= 28
    assert window.metadata_list.height() >= 90
    window.close()


def test_gui_mechanical_safe_scope_requires_time_reduction(monkeypatch) -> None:
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    tool = load_tool_module()
    from PyQt6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication(["rst-subset-test"])
    app.setStyle("Fusion")
    app.setPalette(tool.engineering_palette())
    app.setStyleSheet(tool.application_stylesheet())
    window = tool.RstSubsetWindow()
    window._metadata_loaded(tool.RstMetadata(set_ids=(1,), times=(1.0,), named_selections=("MY_NS",)))
    window.named_selection_combo.setCurrentIndex(1)
    warnings: list[str] = []
    monkeypatch.setattr(tool.QMessageBox, "warning", lambda *_args: warnings.append(str(_args[-1])))

    window._run()

    assert "Full-mesh mode keeps all elements" in warnings[0]
    assert window.run_worker is None
    window.close()


def test_gui_rsplit_mode_disables_time_selection(monkeypatch) -> None:
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    tool = load_tool_module()
    from PyQt6.QtWidgets import QApplication, QListWidget

    app = QApplication.instance() or QApplication(["rst-subset-test"])
    app.setStyle("Fusion")
    app.setPalette(tool.engineering_palette())
    app.setStyleSheet(tool.application_stylesheet())
    window = tool.RstSubsetWindow()
    window._metadata_loaded(tool.RstMetadata(set_ids=(1, 2), times=(1.0, 2.0), named_selections=("MY_NS",)))
    window.metadata_list.item(1).setSelected(True)
    assert window.set_ids_radio.isChecked()

    window.spatial_subset_checkbox.setChecked(True)

    assert window.all_sets_radio.isChecked()
    assert not window.set_ids_radio.isEnabled()
    assert not window.times_radio.isEnabled()
    assert not window.set_ids_edit.isEnabled()
    assert not window.times_edit.isEnabled()
    assert window.metadata_list.selectionMode() == QListWidget.SelectionMode.NoSelection
    assert window._config().time_mode == "all"

    window.spatial_subset_checkbox.setChecked(False)
    assert window.set_ids_radio.isEnabled()
    assert window.times_radio.isEnabled()
    assert window.metadata_list.selectionMode() == QListWidget.SelectionMode.ExtendedSelection
    window.close()

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import pytest
from PyQt6.QtCore import QPoint, QRect, Qt
from PyQt6.QtGui import QColor, QGuiApplication, QPainter, QPen
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QFrame, QHeaderView, QPushButton, QSizePolicy, QWidget
from scripts.Sensor_Data_Comparison_Tool.mock_inputs.plotly_html.generate_mock_plotly_html_inputs import (
    generate_mock_plotly_html_inputs,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
TOOL_ROOT = REPO_ROOT / "scripts" / "Sensor_Data_Comparison_Tool"
if str(TOOL_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOL_ROOT))

import sensor_compare_tool.wizard as wizard_module  # noqa: E402
from sensor_compare_tool.analysis_tables import AnalysisTable, AnalysisTableBundle  # noqa: E402
from sensor_compare_tool.logic import ColumnMatch, DatasetSpec, PreparedComparison  # noqa: E402
from sensor_compare_tool.plots import SignAgreementPlotData  # noqa: E402
from sensor_compare_tool.sign_agreement_view import SignAgreementView  # noqa: E402
from sensor_compare_tool.wizard import ResultsPage, SensorComparisonWindow, WebPlotView  # noqa: E402


REFERENCE_CSV = TOOL_ROOT / "mock_inputs" / "mock_sensor_dataset_reference.csv"
CANDIDATE_CSV = TOOL_ROOT / "mock_inputs" / "mock_sensor_dataset_candidate.csv"


@pytest.fixture(scope="module")
def plotly_html_paths(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    return generate_mock_plotly_html_inputs(
        tmp_path_factory.mktemp("sensor_plotly_html_gui"),
        include_plotlyjs=False,
    )


@pytest.fixture(autouse=True)
def fail_on_unexpected_modal_message(monkeypatch) -> None:
    def fail(_parent, title, message, *_args, **_kwargs) -> None:
        pytest.fail(f"Unexpected modal message '{title}': {message}", pytrace=False)

    monkeypatch.setattr(wizard_module.QMessageBox, "warning", fail)
    monkeypatch.setattr(wizard_module.QMessageBox, "critical", fail)


class DummyPlotView(QWidget):
    def __init__(self):
        super().__init__()
        self.figure = None
        self.refresh_count = 0
        self.force_refresh_count = 0
        self.visibility_masks: list[tuple[bool, ...]] = []

    def set_figure(self, figure):
        self.figure = figure

    def apply_trace_visibility_mask(self, mask):
        self.visibility_masks.append(tuple(bool(value) for value in mask))
        if self.figure is not None:
            for trace, visible in zip(self.figure.data, mask):
                trace.visible = bool(visible)
        self.refresh_plot()

    def refresh_plot(self):
        self.refresh_count += 1

    def force_refresh_plot(self):
        self.force_refresh_count += 1
        self.refresh_plot()


class ScreenshotPlotView(DummyPlotView):
    def __init__(self):
        super().__init__()
        self.setMinimumSize(520, 360)

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#ffffff"))
        if self.figure is None:
            painter.setPen(QColor("#7d8a98"))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "No plot")
            return

        margin = 44
        plot_rect = self.rect().adjusted(margin, margin, -margin, -margin)
        painter.setPen(QPen(QColor("#cbd6e2"), 2))
        painter.drawRect(plot_rect)
        painter.setPen(QPen(QColor("#2f6fbb"), 4))
        points = [
            QPoint(plot_rect.left(), plot_rect.bottom() - 12),
            QPoint(plot_rect.center().x(), plot_rect.center().y()),
            QPoint(plot_rect.right(), plot_rect.top() + 12),
        ]
        for left, right in zip(points, points[1:]):
            painter.drawLine(left, right)
        painter.setPen(QPen(QColor("#b64a4a"), 3))
        painter.setBrush(QColor("#b64a4a"))
        for point in points:
            painter.drawEllipse(point, 6, 6)
        painter.setPen(QColor("#263545"))
        painter.drawText(plot_rect.adjusted(8, 8, -8, -8), Qt.AlignmentFlag.AlignTop, "Detached plot screenshot test")


def _open_mock_results(window: SensorComparisonWindow, qapp) -> None:
    window.load_page.set_input_mode(window.load_page.SEPARATE_MODE)
    window.load_page.path1_edit.setText(str(REFERENCE_CSV))
    window.load_page.path2_edit.setText(str(CANDIDATE_CSV))
    window.load_page.name1_edit.setText("Reference")
    window.load_page.name2_edit.setText("Candidate")
    for _step in range(4):
        window.go_next()
    qapp.processEvents()
    assert window.stack.currentIndex() == 4


def _apply_pending_results_update(window: SensorComparisonWindow, qapp) -> None:
    assert window.results_page.update_button.isEnabled()
    window.results_page.update_button.click()
    qapp.processEvents()
    assert not window.results_page.update_button.isEnabled()


def _count_wizard_calls(monkeypatch, names: list[str]) -> dict[str, int]:
    calls = dict.fromkeys(names, 0)
    for name in names:
        original = getattr(wizard_module, name)

        def wrapper(*args, _original=original, _name=name, **kwargs):
            calls[_name] += 1
            return _original(*args, **kwargs)

        monkeypatch.setattr(wizard_module, name, wrapper)
    return calls


def _visible_overlay_channels(figure) -> list[str]:
    channels = []
    for trace in figure.data:
        if trace.visible is False:
            continue
        channel = trace.meta.get("overlay_channel") if isinstance(trace.meta, dict) else None
        if channel is not None and channel not in channels:
            channels.append(channel)
    return channels


class FakeWebView:
    def __init__(self):
        self.urls: list[str] = []
        self.page_object = FakePage()

    def setUrl(self, url):
        self.urls.append(url.toString())

    def setHtml(self, _html):
        pass

    def page(self):
        return self.page_object


class FakePage:
    def __init__(self):
        self.scripts: list[str] = []

    def runJavaScript(self, script):
        self.scripts.append(script)


def test_web_plot_view_force_refresh_reloads_existing_render(qapp, monkeypatch) -> None:
    monkeypatch.setattr(wizard_module, "write_offline_plot_html", lambda _figure: "C:/tmp/detached-plot.html")
    view = WebPlotView()
    fake_web_view = FakeWebView()
    view.web_view = fake_web_view
    view._ensure_web_view = lambda: None  # type: ignore[method-assign]
    view._figure = object()
    view._needs_render = False

    view.refresh_plot()
    assert fake_web_view.urls == []

    view.force_refresh_plot()
    assert fake_web_view.urls == ["file:///C:/tmp/detached-plot.html"]
    assert view._needs_render is False


def test_web_plot_view_applies_trace_visibility_without_reloading(qapp) -> None:
    view = WebPlotView()
    fake_web_view = FakeWebView()
    view.web_view = fake_web_view
    view._figure = go.Figure(data=[go.Scatter(y=[1.0]), go.Scatter(y=[2.0])])
    view._needs_render = False

    view.apply_trace_visibility_mask((True, False))

    assert [trace.visible for trace in view._figure.data] == [True, False]
    assert fake_web_view.urls == []
    assert "Plotly.restyle" in fake_web_view.page_object.scripts[-1]


def test_sign_agreement_view_keeps_time_on_x_axis(qapp) -> None:
    view = SignAgreementView()
    try:
        view.set_figure(
            SignAgreementPlotData(
                status_frame=pd.DataFrame(
                    {
                        "Time": [0.0, 1.0, 2.0, 3.0],
                        "A": [1, -1, 1, 1],
                        "B": [1, -1, 1, 1],
                        "C": [1, -1, 1, 1],
                    }
                ),
                metrics=[],
                reference_name="Reference",
                target_name="Target",
                deadband=0.0,
            )
        )
        view.refresh_plot()

        image = view.image_item.image
        assert image.shape == (4, 3)
        assert image[1, :].tolist() == [0, 0, 0]
        assert image[:, 0].tolist() == [2, 0, 2, 2]
    finally:
        view.close()


def test_sign_agreement_view_filters_summary_and_heatmap(qapp) -> None:
    view = SignAgreementView()
    try:
        view.set_figure(
            SignAgreementPlotData(
                status_frame=pd.DataFrame(
                    {
                        "Time": [0.0, 1.0, 2.0, 3.0],
                        "A": [1, 1, 1, 1],
                        "B": [1, -1, 1, 1],
                        "C": [-1, -1, -1, 1],
                    }
                ),
                metrics=[
                    {
                        "Channel": "A",
                        "Sign Agreement (%)": 100.0,
                        "Sign Mismatch (%)": 0.0,
                        "Sign Deadband (%)": 50.0,
                        "Longest Sign Mismatch (s)": 0.0,
                    },
                    {
                        "Channel": "B",
                        "Sign Agreement (%)": 75.0,
                        "Sign Mismatch (%)": 25.0,
                        "Sign Deadband (%)": 10.0,
                        "Longest Sign Mismatch (s)": 1.0,
                    },
                    {
                        "Channel": "C",
                        "Sign Agreement (%)": 25.0,
                        "Sign Mismatch (%)": 75.0,
                        "Sign Deadband (%)": 50.0,
                        "Longest Sign Mismatch (s)": 3.0,
                    },
                ],
                reference_name="Reference",
                target_name="Target",
                deadband=0.125,
            )
        )
        view.refresh_plot()

        header = view.summary_table.horizontalHeader()
        assert header.sectionsMovable()
        assert all(header.sectionResizeMode(column) == QHeaderView.ResizeMode.Interactive for column in range(5))
        assert not view.opposite_threshold_spin.keyboardTracking()
        assert not view.sign_deadband_spin.keyboardTracking()
        assert view.summary_table.rowCount() == 3
        assert view.image_item.image.shape == (4, 3)
        assert view.sign_deadband_spin.value() == pytest.approx(0.125)
        assert view.filtered_channels() == ["A", "B", "C"]
        assert view.summary_table.item(0, 1).text() == "100.0%"
        assert view.summary_table.item(2, 4).text() == "3s"
        assert view.summary_table.item(0, 1).textAlignment() == (
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        assert view.summary_table.item(0, 1).background().color() == QColor("#ecf7f0")
        assert view.summary_table.item(0, 2).background().color() == QColor("#faeeee")
        assert view.summary_table.item(0, 3).background().color() == QColor("#f1f4f8")
        summary_filter_changes = []
        view.summary_filter_changed.connect(lambda: summary_filter_changes.append(view.filtered_channels()))

        view.opposite_threshold_spin.setValue(30.0)
        qapp.processEvents()
        assert view.summary_table.rowCount() == 1
        assert view.summary_table.item(0, 0).text() == "C"
        assert view.image_item.image.shape == (4, 1)
        assert view._channels == ["C"]
        assert view.filtered_channels() == ["C"]
        assert summary_filter_changes == [["C"]]

        view.opposite_threshold_spin.setValue(90.0)
        qapp.processEvents()
        assert view.summary_table.rowCount() == 0
        assert view._channels == []
        assert view.filtered_channels() == []
        assert summary_filter_changes == [["C"], []]
        assert "opposite > 90%" in view.hover_label.text()
    finally:
        view.close()


def test_sign_agreement_summary_spinbox_commit_and_collapse(qapp) -> None:
    view = SignAgreementView()
    try:
        opposite_changes = []
        sign_deadband_changes = []
        view.opposite_threshold_spin.valueChanged.connect(opposite_changes.append)
        view.sign_deadband_spin.valueChanged.connect(sign_deadband_changes.append)
        view.show()
        qapp.processEvents()

        view.opposite_threshold_spin.setFocus()
        view.opposite_threshold_spin.selectAll()
        QTest.keyClicks(view.opposite_threshold_spin, "12.5")
        qapp.processEvents()
        assert opposite_changes == []

        QTest.keyClick(view.opposite_threshold_spin, Qt.Key.Key_Return)
        qapp.processEvents()
        assert len(opposite_changes) == 1
        assert opposite_changes[0] == pytest.approx(12.5)

        view.sign_deadband_spin.setFocus()
        view.sign_deadband_spin.selectAll()
        QTest.keyClicks(view.sign_deadband_spin, "33.5")
        qapp.processEvents()
        assert sign_deadband_changes == []

        QTest.keyClick(view.sign_deadband_spin, Qt.Key.Key_Return)
        qapp.processEvents()
        assert len(sign_deadband_changes) == 1
        assert sign_deadband_changes[0] == pytest.approx(33.5)

        view.summary_splitter.setSizes([620, 380])
        qapp.processEvents()
        view.collapse_summary_panel()
        qapp.processEvents()
        assert view.summary_panel_collapsed is True
        assert view.summary_sidebar.isHidden()
        assert not view.summary_restore_rail.isHidden()
        assert view.summary_shell.minimumWidth() == view.COLLAPSED_RAIL_WIDTH
        assert view.summary_shell.maximumWidth() == view.COLLAPSED_RAIL_WIDTH

        view.expand_summary_panel()
        qapp.processEvents()
        assert view.summary_panel_collapsed is False
        assert not view.summary_sidebar.isHidden()
        assert view.summary_restore_rail.isHidden()
        assert view.summary_shell.minimumWidth() == view.SUMMARY_EXPANDED_MIN_WIDTH
        assert view.summary_splitter.sizes()[1] >= view.SUMMARY_EXPANDED_MIN_WIDTH
    finally:
        view.close()
        qapp.processEvents()


def test_results_page_sign_agreement_deadband_controls_stay_synced(qapp) -> None:
    page = ResultsPage(DummyPlotView)
    try:
        changes = []
        page.changed.connect(lambda: changes.append(page.sign_deadband_spin.value()))

        page.sign_deadband_spin.setValue(0.25)
        qapp.processEvents()
        assert page.sign_plot.sign_deadband_spin.value() == pytest.approx(0.25)

        change_count = len(changes)
        page.sign_plot.sign_deadband_spin.setValue(0.5)
        qapp.processEvents()
        assert page.sign_deadband_spin.value() == pytest.approx(0.5)
        assert page.sign_plot.sign_deadband_spin.value() == pytest.approx(0.5)
        assert len(changes) == change_count + 1

        change_count = len(changes)
        page.sign_plot.set_figure(
            SignAgreementPlotData(
                status_frame=pd.DataFrame({"Time": [0.0, 1.0], "A": [1, -1]}),
                metrics=[],
                reference_name="Reference",
                target_name="Target",
                deadband=0.75,
            )
        )
        page.sign_plot.refresh_plot()
        qapp.processEvents()
        assert page.sign_plot.sign_deadband_spin.value() == pytest.approx(0.75)
        assert page.sign_deadband_spin.value() == pytest.approx(0.5)
        assert len(changes) == change_count
    finally:
        page.close()
        qapp.processEvents()


def test_results_page_channel_search_and_certification_quick_filters(qapp) -> None:
    page = ResultsPage(DummyPlotView)
    try:
        frame = pd.DataFrame({"Time": [0.0, 1.0], "A": [1.0, 2.0], "B": [3.0, 4.0], "C": [5.0, 6.0]})
        prepared = PreparedComparison(
            dataset1=DatasetSpec(Path("reference.csv"), "Reference", frame),
            dataset2=DatasetSpec(Path("candidate.csv"), "Candidate", frame),
            matches=tuple(ColumnMatch(channel, channel, channel) for channel in ["A", "B", "C"]),
            dataset1_prepared=frame,
            dataset2_prepared=frame,
            dataset1_aligned=frame,
            dataset2_aligned=frame,
        )
        page.set_ready(prepared, 0, 0.0, 1.0)
        bundle = AnalysisTableBundle(
            scope="test",
            summary={},
            tables=(
                AnalysisTable(
                    "certification_ranking",
                    "Certification Ranking",
                    pd.DataFrame(
                        [
                            {
                                "Channel": "A",
                                "Evidence Grade": "A",
                                "Certification Eligible": "Yes",
                                "Data Quality Warnings": 0.0,
                            },
                            {
                                "Channel": "B",
                                "Evidence Grade": "Reject",
                                "Certification Eligible": "No",
                                "Data Quality Warnings": 0.0,
                            },
                            {
                                "Channel": "C",
                                "Evidence Grade": "B",
                                "Certification Eligible": "Yes",
                                "Data Quality Warnings": 1.0,
                            },
                        ]
                    ),
                ),
            ),
        )
        page.set_table_bundle(bundle)

        assert page.channel_completion_model.stringList() == ["A", "B", "C"]
        assert page.channel_completer.filterMode() == Qt.MatchFlag.MatchContains
        assert page.channel_completer.caseSensitivity() == Qt.CaseSensitivity.CaseInsensitive
        assert page.select_reject_channels_button.isEnabled()
        page.select_reject_channels_button.click()
        assert page.selected_columns() == ["B"]

        page.select_warning_channels_button.click()
        assert page.selected_columns() == ["C"]

        page.channel_search_edit.setText("B")
        qapp.processEvents()
        assert [page.channel_list.item(index).isHidden() for index in range(3)] == [True, False, True]
        assert "1 matches" in page.channel_count.text()
        assert page.selected_columns() == ["C"]
        page.channel_search_edit.clear()
        qapp.processEvents()
        assert [page.channel_list.item(index).isHidden() for index in range(3)] == [False, False, False]
        assert page.selected_columns() == ["C"]
    finally:
        page.close()
        qapp.processEvents()


def test_results_page_detached_table_refresh_and_button_state(qapp) -> None:
    page = ResultsPage(DummyPlotView)
    try:
        first_table = AnalysisTable("metrics", "Statistical Metrics", pd.DataFrame({"Channel": ["A"], "RMSE": [1.0]}))
        page.set_table_bundle(AnalysisTableBundle(scope="test", summary={}, tables=(first_table,)))

        assert page.detach_table_button.isEnabled()
        assert page.detach_table_button.accessibleName() == "Detach Table"
        page.detach_current_table()
        qapp.processEvents()
        assert set(page._detached_tables) == {"metrics"}
        state = page._detached_tables["metrics"]
        assert state.table_view.table.title == "Statistical Metrics"
        assert state.table_view.model().rowCount() == 1
        assert page.detach_table_button.accessibleName() == "Close Detached Table"

        refreshed_table = AnalysisTable(
            "metrics",
            "Statistical Metrics",
            pd.DataFrame({"Channel": ["A", "B"], "RMSE": [1.0, 2.0]}),
        )
        page.set_table_bundle(AnalysisTableBundle(scope="test", summary={}, tables=(refreshed_table,)))
        qapp.processEvents()
        assert state.table_view.model().rowCount() == 2
        assert page.current_table().frame["Channel"].tolist() == ["A", "B"]

        page.detach_current_plot()
        qapp.processEvents()
        assert page.current_table().title == "Statistical Metrics"
        page.restore_detached_plot(0)
        qapp.processEvents()

        page.toggle_current_table_detached()
        qapp.processEvents()
        assert page._detached_tables == {}
        assert page.detach_table_button.accessibleName() == "Detach Table"

        page.tabs.setCurrentIndex(4)
        qapp.processEvents()
        assert page.current_table() is None
        assert not page.detach_table_button.isEnabled()
    finally:
        page.close()
        qapp.processEvents()


def test_sensor_comparison_window_smoke(qapp, monkeypatch) -> None:
    window = SensorComparisonWindow(plot_view_factory=DummyPlotView)
    try:
        assert window.windowTitle() == "Sensor Data Comparison Tool"
        assert window.stack.count() == 5
        assert window.stack.currentIndex() == 0
        assert window.step_labels[0].text() == "1. Choose Input"
        assert window.next_button.text() == "Review Matched Channels"
        assert window.results_page.tabs.count() == 13
        assert window.results_page.tabs.tabText(1) == "Certification Ranking"
        assert window.results_page.tabs.tabToolTip(2)
        assert window.workflow_panel_collapsed is False
        assert not window.workflow_sidebar.isHidden()
        assert window.workflow_restore_rail.isHidden()
        assert window.workflow_shell.minimumWidth() == window.WORKFLOW_EXPANDED_WIDTH
        assert window.workflow_collapse_button.accessibleName() == "Collapse Workflow"
        assert window.workflow_collapse_button.property("paneHandle") == "true"
        assert window.workflow_collapse_button.property("paneTheme") == "sidebar"
        assert window.workflow_restore_handle.objectName() == "CollapsedPaneHandle"
        assert isinstance(window.workflow_restore_handle, QFrame)
        assert not isinstance(window.workflow_restore_handle, QPushButton)
        assert window.workflow_restore_handle.height() > window.workflow_restore_handle.width()
        assert window.workflow_restore_handle.accessibleName() == "Show Workflow"
        assert window.workflow_restore_rail.property("railTheme") == "sidebar"
        window.collapse_workflow_panel()
        assert window.workflow_panel_collapsed is True
        assert window.workflow_sidebar.isHidden()
        assert not window.workflow_restore_rail.isHidden()
        assert window.workflow_restore_handle.isHidden()
        assert window.workflow_shell.minimumWidth() == window.COLLAPSED_RAIL_WIDTH
        assert window.workflow_shell.maximumWidth() == window.COLLAPSED_RAIL_WIDTH
        window.workflow_restore_rail.set_revealed(True)
        assert not window.workflow_restore_handle.isHidden()
        assert window.workflow_restore_handle.width() == window.COLLAPSED_HANDLE_WIDTH
        assert window.workflow_shell.minimumWidth() == window.COLLAPSED_RAIL_WIDTH
        window.workflow_restore_rail.conceal()
        assert window.workflow_restore_handle.isHidden()
        assert window.workflow_shell.minimumWidth() == window.COLLAPSED_RAIL_WIDTH
        window.expand_workflow_panel()
        assert window.workflow_panel_collapsed is False
        assert not window.workflow_sidebar.isHidden()
        assert window.workflow_restore_rail.isHidden()
        assert window.workflow_shell.minimumWidth() == window.WORKFLOW_EXPANDED_WIDTH
        assert window.results_page.metric_button.menu() is not None
        assert window.results_page.export_button.menu() is not None
        assert window.results_page.export_button.text() == ""
        assert window.results_page.export_button.property("iconButton") == "true"
        assert not window.results_page.export_button.icon().isNull()
        assert window.results_page.export_button.accessibleName() == "Export Excel"
        assert [action.text() for action in window.results_page.export_button.menu().actions()] == [
            "Export Current Table...",
            "Export Master Workbook...",
        ]
        assert window.results_page.detach_table_button.property("iconButton") == "true"
        assert window.results_page.detach_table_button.accessibleName() == "Detach Table"
        assert window.results_page.help_button.text() == "Metrics Help"
        assert window.results_page.hide_transforms_checkbox.isChecked()
        assert window.results_page.abs_tolerance() == pytest.approx(0.0)
        assert window.results_page.rel_tolerance_percent() == pytest.approx(0.0)
        assert "RMSE" in window.results_page.selected_metric_keys()
        assert "Robust NMAE (%)" in window.results_page.selected_metric_keys()
        assert "Within Tolerance Abs (%)" in window.results_page.metric_actions
        assert "Within Tolerance Rel (%)" in window.results_page.metric_actions
        assert not window.results_page.metric_actions["Within Tolerance Abs (%)"].isChecked()
        assert not window.results_page.metric_actions["Within Tolerance Rel (%)"].isChecked()
        rmse_action = window.results_page.metric_actions["RMSE"]
        assert rmse_action.toolTip()
        window.results_page._show_metric_help("RMSE")
        qapp.processEvents()
        assert window.results_page.metric_help_popover.isVisible()
        rmse_html = window.results_page.metric_help_popover.current_html()
        assert "Root Mean Squared Error" in rmse_html
        assert "<h3>Formula</h3>" in rmse_html
        assert "<h3>Example Problem</h3>" in rmse_html
        popover = window.results_page.metric_help_popover
        assert popover.windowType() == Qt.WindowType.Tool
        assert not popover.windowFlags() & Qt.WindowType.WindowDoesNotAcceptFocus
        assert popover.pin_button.accessibleName() == "Pin Metric Help"
        assert not popover.pin_button.isChecked()
        assert popover.browser.verticalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAsNeeded
        assert popover.browser.horizontalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        cursor_position = popover.frameGeometry().bottomRight() + QPoint(1000, 1000)
        scheduled_hides = []
        with monkeypatch.context() as popover_patch:
            popover_patch.setattr(
                wizard_module.QCursor,
                "pos",
                staticmethod(lambda: QPoint(cursor_position)),
            )
            popover_patch.setattr(
                wizard_module.QTimer,
                "singleShot",
                staticmethod(lambda delay, callback: scheduled_hides.append((delay, callback))),
            )

            window.results_page.metric_menu.aboutToHide.emit()
            delay, hide_callback = scheduled_hides.pop()
            assert delay == 180
            hide_callback()
            assert not popover.isVisible()

            window.results_page._show_metric_help("RMSE")
            qapp.processEvents()
            assert popover.isVisible()
            popover_rect = popover.frameGeometry()
            menu_rect = QRect(
                popover_rect.left() - 120,
                popover_rect.top(),
                96,
                popover_rect.height(),
            )
            bridge_pos = QPoint(
                (menu_rect.right() + popover_rect.left()) // 2,
                popover_rect.center().y(),
            )
            assert not menu_rect.contains(bridge_pos)
            assert not popover_rect.adjusted(-4, -4, 4, 4).contains(bridge_pos)
            assert menu_rect.united(popover_rect).contains(bridge_pos)
            window.results_page._last_metric_menu_rect = menu_rect
            cursor_position = bridge_pos

            window.results_page.metric_action_menus["RMSE"].aboutToHide.emit()
            delay, hide_callback = scheduled_hides.pop()
            assert delay == 180
            hide_callback()
            assert popover.isVisible()
            assert scheduled_hides[-1][0] == 180

            cursor_position = popover_rect.bottomRight() + QPoint(1000, 1000)
            _delay, hide_callback = scheduled_hides.pop()
            hide_callback()
            assert not popover.isVisible()

        window.results_page._show_metric_help("RMSE")
        qapp.processEvents()
        assert popover.isVisible()
        window.results_page.tabs.setCurrentIndex(5)
        qapp.processEvents()
        assert not popover.isVisible()

        window.results_page._show_metric_help("RMSE")
        qapp.processEvents()
        popover.pin_button.click()
        qapp.processEvents()
        assert popover.is_pinned()
        assert popover.pin_button.accessibleName() == "Unpin Metric Help"
        window.results_page.metric_menu.aboutToHide.emit()
        qapp.processEvents()
        assert popover.isVisible()
        window.results_page.tabs.setCurrentIndex(6)
        qapp.processEvents()
        assert popover.isVisible()
        popover.pin_button.click()
        qapp.processEvents()
        assert not popover.is_pinned()
        assert not popover.isVisible()

        screen = QGuiApplication.primaryScreen()
        assert screen is not None
        bounds = screen.availableGeometry()
        menu_rect = QRect(bounds.left() + 20, bounds.top() + 20, 260, 220)
        if bounds.width() >= popover.width() + menu_rect.width() + 80:
            popover.show_metric("RMSE", menu_rect, menu_rect.top() + 30)
            qapp.processEvents()
            assert not popover.frameGeometry().intersects(menu_rect)
        window.results_page._hide_metric_help()
        assert window.step_labels[0].property("state") == "current"
        assert window.step_labels[1].property("state") == "upcoming"
    finally:
        window.close()
        qapp.processEvents()


def test_results_toolbar_time_spinboxes_emit_typed_edits(qapp) -> None:
    page = ResultsPage(DummyPlotView)
    try:
        assert page.start_spin.keyboardTracking()
        assert page.end_spin.keyboardTracking()
        assert not page.sign_deadband_spin.keyboardTracking()
        assert not page.abs_tolerance_spin.keyboardTracking()
        assert not page.rel_tolerance_spin.keyboardTracking()

        changes = []
        page.changed.connect(lambda: changes.append(page.start_spin.value()))
        page.show()
        qapp.processEvents()

        page.start_spin.setFocus()
        page.start_spin.selectAll()
        QTest.keyClicks(page.start_spin, "12.5")
        qapp.processEvents()
        assert changes
        assert changes[-1] == pytest.approx(12.5)

        QTest.keyClick(page.start_spin, Qt.Key.Key_Return)
        qapp.processEvents()
        assert page.start_spin.value() == pytest.approx(12.5)
        first_change_count = len(changes)

        page.start_spin.selectAll()
        QTest.keyClicks(page.start_spin, "18.75")
        qapp.processEvents()
        assert len(changes) > first_change_count
        assert changes[-1] == pytest.approx(18.75)

        page.reference_combo.setFocus()
        qapp.processEvents()
        assert page.start_spin.value() == pytest.approx(18.75)
        second_change_count = len(changes)

        page.start_spin.stepUp()
        qapp.processEvents()
        assert len(changes) > second_change_count

        page.start_spin.setValue(20.0)
        qapp.processEvents()
        assert changes[-1] == pytest.approx(20.0)
    finally:
        page.close()
        qapp.processEvents()


def test_results_page_changes_wait_for_update_button(qapp, monkeypatch) -> None:
    calls = []

    def fake_render(self, *, verbose_progress=False):
        calls.append(verbose_progress)
        self._set_results_dirty(False)
        return True

    monkeypatch.setattr(SensorComparisonWindow, "render_results", fake_render)
    window = SensorComparisonWindow(plot_view_factory=DummyPlotView)
    try:
        _open_mock_results(window, qapp)
        assert calls == [True]
        calls.clear()
        assert not window.results_page.update_button.isEnabled()

        window.results_page.changed.emit()
        window.results_page.changed.emit()
        window.results_page.changed.emit()
        qapp.processEvents()
        assert calls == []
        assert window.results_page.update_button.isEnabled()
        assert "Click Update Data & Plots" in window.results_page.status_label.text()

        QTest.qWait(160)
        qapp.processEvents()
        assert calls == []

        window.results_page.update_button.click()
        qapp.processEvents()
        assert calls == [False]
        assert not window.results_page.update_button.isEnabled()
    finally:
        window.close()
        qapp.processEvents()


def test_tolerance_changes_reuse_analysis_cache(qapp, monkeypatch) -> None:
    counted = [
        "calculate_residual_diagnostics",
        "calculate_rolling_diagnostics",
        "calculate_lag_diagnostics",
        "calculate_event_timing_diagnostics",
        "calculate_data_quality",
        "calculate_calibration_diagnostics",
        "calculate_frequency_diagnostics",
        "calculate_scale_offset",
        "build_overlay_transforms",
        "calculate_statistical_metrics",
        "build_metrics_figure",
        "build_residual_figure",
    ]
    calls = _count_wizard_calls(monkeypatch, counted)
    window = SensorComparisonWindow(plot_view_factory=DummyPlotView)
    try:
        _open_mock_results(window, qapp)
        before = calls.copy()
        table_bundle_before = window.results_page.table_bundle()
        metrics_figure_before = window.results_page.metrics_plot.figure
        residual_figure_before = window.results_page.residual_plot.figure

        window.results_page.abs_tolerance_spin.setValue(999999.0)
        window.results_page.rel_tolerance_spin.setValue(5.0)
        qapp.processEvents()

        assert window.results_page.update_button.isEnabled()
        assert calls == before
        assert window.results_page.metrics_plot.figure is metrics_figure_before
        assert window.results_page.residual_plot.figure is residual_figure_before
        assert window.results_page.table_bundle() is table_bundle_before

        _apply_pending_results_update(window, qapp)

        for name in counted:
            expected = before[name] + 1 if name == "build_residual_figure" else before[name]
            assert calls[name] == expected
        assert window.results_page.metrics_plot.figure is metrics_figure_before
        assert window.results_page.residual_plot.figure is not residual_figure_before
        table_bundle_after = window.results_page.table_bundle()
        assert table_bundle_after is not table_bundle_before
        assert table_bundle_after.table("overlay_reference") is table_bundle_before.table("overlay_reference")
        metrics_frame = table_bundle_after.table("metrics").frame
        # The large absolute tolerance places every sample inside the absolute band.
        assert metrics_frame["Within Tolerance Abs (%)"].tolist() == pytest.approx([100.0] * len(metrics_frame))
    finally:
        window.close()
        qapp.processEvents()


def test_metric_selection_rebuilds_only_metrics_plot(qapp, monkeypatch) -> None:
    calls = _count_wizard_calls(
        monkeypatch,
        [
            "calculate_residual_diagnostics",
            "calculate_statistical_metrics",
            "build_metrics_figure",
            "build_overlay_figure",
        ],
    )
    window = SensorComparisonWindow(plot_view_factory=DummyPlotView)
    try:
        _open_mock_results(window, qapp)
        before = calls.copy()
        table_bundle_before = window.results_page.table_bundle()
        overlay_figure_before = window.results_page.overlay_plot.figure

        window.results_page.metric_actions["MSE"].setChecked(True)
        qapp.processEvents()

        assert window.results_page.update_button.isEnabled()
        assert calls == before
        assert window.results_page.table_bundle() is table_bundle_before
        assert window.results_page.overlay_plot.figure is overlay_figure_before

        _apply_pending_results_update(window, qapp)

        assert calls["build_metrics_figure"] == before["build_metrics_figure"] + 1
        assert calls["calculate_residual_diagnostics"] == before["calculate_residual_diagnostics"]
        assert calls["calculate_statistical_metrics"] == before["calculate_statistical_metrics"]
        assert calls["build_overlay_figure"] == before["build_overlay_figure"]
        assert window.results_page.table_bundle() is table_bundle_before
        assert window.results_page.overlay_plot.figure is overlay_figure_before
    finally:
        window.close()
        qapp.processEvents()


def test_hide_transforms_rebuilds_only_overlay_plot(qapp, monkeypatch) -> None:
    calls = _count_wizard_calls(
        monkeypatch,
        [
            "build_overlay_figure",
            "build_overlay_transforms",
            "build_metrics_figure",
            "calculate_statistical_metrics",
        ],
    )
    window = SensorComparisonWindow(plot_view_factory=DummyPlotView)
    try:
        _open_mock_results(window, qapp)
        before = calls.copy()
        table_bundle_before = window.results_page.table_bundle()
        metrics_figure_before = window.results_page.metrics_plot.figure
        overlay_figure_before = window.results_page.overlay_plot.figure
        assert window.results_page.hide_transforms_checkbox.isChecked()

        window.results_page.hide_transforms_checkbox.setChecked(False)
        qapp.processEvents()

        assert window.results_page.update_button.isEnabled()
        assert calls == before
        assert window.results_page.table_bundle() is table_bundle_before
        assert window.results_page.metrics_plot.figure is metrics_figure_before
        assert window.results_page.overlay_plot.figure is overlay_figure_before

        _apply_pending_results_update(window, qapp)

        assert calls["build_overlay_figure"] == before["build_overlay_figure"] + 1
        assert calls["build_overlay_transforms"] == before["build_overlay_transforms"]
        assert calls["build_metrics_figure"] == before["build_metrics_figure"]
        assert calls["calculate_statistical_metrics"] == before["calculate_statistical_metrics"]
        assert window.results_page.table_bundle() is table_bundle_before
        assert window.results_page.metrics_plot.figure is metrics_figure_before
        assert len(window.results_page.overlay_plot.figure.data) > len(overlay_figure_before.data)
    finally:
        window.close()
        qapp.processEvents()


def test_overlay_metric_filter_threshold_rank_updates_plot_tables_and_exports(qapp, monkeypatch, tmp_path) -> None:
    calls = _count_wizard_calls(
        monkeypatch,
        [
            "build_overlay_figure",
            "build_overlay_transforms",
            "calculate_statistical_metrics",
        ],
    )
    window = SensorComparisonWindow(plot_view_factory=DummyPlotView)
    try:
        _open_mock_results(window, qapp)
        before = calls.copy()
        table_bundle_before = window.results_page.table_bundle()
        overlay_figure_before = window.results_page.overlay_plot.figure
        overlay_refresh_before = window.results_page.overlay_plot.refresh_count

        window.results_page.set_overlay_metric_filter_state(
            wizard_module.OverlayMetricFilterState(
                thresholds=(wizard_module.OverlayMetricThresholdRule("MAE", "<=", 0.05),),
                rank_metric_keys=("Robust NMAE (%)",),
                rank_count=2,
                rank_direction="Worst",
            )
        )
        qapp.processEvents()

        assert window.results_page.update_button.isEnabled()
        assert window.results_page.overlay_filter_button.text() == "Overlay Filter: On"
        assert calls == before
        assert window.results_page.table_bundle() is table_bundle_before
        assert window.results_page.overlay_plot.figure is overlay_figure_before

        _apply_pending_results_update(window, qapp)

        filtered_channels = ["SG_Rear_Right", "SG_Rear_Left"]
        filtered_plot_channels = ["SG_Rear_Left", "SG_Rear_Right"]
        assert calls["build_overlay_figure"] == before["build_overlay_figure"] + 1
        assert calls["build_overlay_transforms"] == before["build_overlay_transforms"]
        assert calls["calculate_statistical_metrics"] == before["calculate_statistical_metrics"]
        assert window.results_page.overlay_plot.figure is not overlay_figure_before
        assert _visible_overlay_channels(window.results_page.overlay_plot.figure) == filtered_plot_channels
        assert len(window.results_page.overlay_plot.figure.data) == len(filtered_channels) * 2
        assert sum(trace.visible is not False for trace in window.results_page.overlay_plot.figure.data) == len(filtered_channels) * 2
        assert window.results_page.overlay_plot.refresh_count > overlay_refresh_before
        filtered_bundle = window.results_page.table_bundle()
        assert filtered_bundle.summary["Overlay Filter"] == "Metric Filter"
        assert list(filtered_bundle.table("overlay_reference").frame.columns) == ["Time", *filtered_channels]

        exported_bundles = []
        monkeypatch.setattr(
            wizard_module.QFileDialog,
            "getSaveFileName",
            lambda *_args, **_kwargs: (str(tmp_path / "overlay_metric_table.xlsx"), "Excel Workbook (*.xlsx)"),
        )
        monkeypatch.setattr(
            wizard_module,
            "write_analysis_workbook",
            lambda path, bundle: exported_bundles.append((path, bundle)) or Path(path),
        )
        monkeypatch.setattr(wizard_module.QMessageBox, "exec", lambda _self: 0)
        window.results_page.tabs.setCurrentWidget(window.results_page.overlay_view)
        qapp.processEvents()
        window.export_current_table()
        assert list(exported_bundles[-1][1].tables[0].frame.columns) == ["Time", *filtered_channels]

        before_sign_intersection = calls.copy()
        filtered_figure_before = window.results_page.overlay_plot.figure
        window.results_page.sign_plot.opposite_threshold_spin.setValue(8.0)
        window.results_page.filter_overlay_to_sign_summary_checkbox.setChecked(True)
        qapp.processEvents()
        _apply_pending_results_update(window, qapp)

        intersected_bundle = window.results_page.table_bundle()
        assert calls["build_overlay_figure"] == before_sign_intersection["build_overlay_figure"] + 1
        assert calls["build_overlay_transforms"] == before_sign_intersection["build_overlay_transforms"]
        assert calls["calculate_statistical_metrics"] == before_sign_intersection["calculate_statistical_metrics"]
        assert window.results_page.overlay_plot.figure is not filtered_figure_before
        assert _visible_overlay_channels(window.results_page.overlay_plot.figure) == ["SG_Rear_Right"]
        assert len(window.results_page.overlay_plot.figure.data) == 2
        assert intersected_bundle.summary["Overlay Filter"] == "Sign Summary + Metric Filter"
        assert list(intersected_bundle.table("overlay_reference").frame.columns) == ["Time", "SG_Rear_Right"]
    finally:
        window.close()
        qapp.processEvents()


def test_overlay_filter_to_sign_summary_updates_plot_tables_and_exports(qapp, monkeypatch, tmp_path) -> None:
    calls = _count_wizard_calls(
        monkeypatch,
        [
            "build_overlay_figure",
            "build_overlay_transforms",
            "calculate_statistical_metrics",
        ],
    )
    window = SensorComparisonWindow(plot_view_factory=DummyPlotView)
    try:
        _open_mock_results(window, qapp)
        full_overlay_columns = list(window.results_page.table_bundle().table("overlay_reference").frame.columns)
        assert "SG_Front_Right" in full_overlay_columns
        assert "SG_Rear_Right" in full_overlay_columns
        before = calls.copy()
        overlay_figure_before = window.results_page.overlay_plot.figure
        table_bundle_before = window.results_page.table_bundle()

        window.results_page.sign_plot.opposite_threshold_spin.setValue(8.0)
        qapp.processEvents()
        assert calls == before
        assert window.results_page.overlay_plot.figure is overlay_figure_before
        assert window.results_page.table_bundle() is table_bundle_before
        assert not window.results_page.update_button.isEnabled()

        window.results_page.filter_overlay_to_sign_summary_checkbox.setChecked(True)
        qapp.processEvents()
        assert window.results_page.update_button.isEnabled()
        assert calls == before
        assert window.results_page.overlay_plot.figure is overlay_figure_before
        assert window.results_page.table_bundle() is table_bundle_before

        _apply_pending_results_update(window, qapp)

        filtered_channels = ["SG_Front_Right", "SG_Rear_Right"]
        assert calls["build_overlay_figure"] == before["build_overlay_figure"] + 1
        assert calls["build_overlay_transforms"] == before["build_overlay_transforms"]
        assert calls["calculate_statistical_metrics"] == before["calculate_statistical_metrics"]
        assert window.results_page.overlay_plot.figure is not overlay_figure_before
        assert _visible_overlay_channels(window.results_page.overlay_plot.figure) == filtered_channels
        assert len(window.results_page.overlay_plot.figure.data) == len(filtered_channels) * 2
        assert sum(trace.visible is not False for trace in window.results_page.overlay_plot.figure.data) == len(filtered_channels) * 2
        filtered_bundle = window.results_page.table_bundle()
        assert filtered_bundle is not table_bundle_before
        assert filtered_bundle.summary["Overlay Filter"] == "Sign Summary"
        assert filtered_bundle.summary["Overlay Channel Count"] == len(filtered_channels)
        assert list(filtered_bundle.table("overlay_reference").frame.columns) == ["Time", *filtered_channels]
        assert list(window.results_page.overlay_table.table.frame.columns) == ["Time", *filtered_channels]
        overlay_table_index = window.results_page.data_tables_view.combo.findData("overlay_reference")
        window.results_page.data_tables_view.combo.setCurrentIndex(overlay_table_index)
        assert list(window.results_page.data_tables_view.current_table().frame.columns) == ["Time", *filtered_channels]

        exported_bundles = []
        monkeypatch.setattr(
            wizard_module.QFileDialog,
            "getSaveFileName",
            lambda *_args, **_kwargs: (str(tmp_path / "overlay_table.xlsx"), "Excel Workbook (*.xlsx)"),
        )
        monkeypatch.setattr(
            wizard_module,
            "write_analysis_workbook",
            lambda path, bundle: exported_bundles.append((path, bundle)) or Path(path),
        )
        monkeypatch.setattr(wizard_module.QMessageBox, "exec", lambda _self: 0)
        window.results_page.tabs.setCurrentWidget(window.results_page.overlay_view)
        qapp.processEvents()
        window.export_current_table()
        assert list(exported_bundles[-1][1].tables[0].frame.columns) == ["Time", *filtered_channels]

        before_empty_filter = calls.copy()
        filtered_bundle_before = window.results_page.table_bundle()
        filtered_figure_before = window.results_page.overlay_plot.figure
        window.results_page.sign_plot.opposite_threshold_spin.setValue(95.0)
        qapp.processEvents()
        assert window.results_page.update_button.isEnabled()
        assert calls == before_empty_filter
        assert window.results_page.overlay_plot.figure is filtered_figure_before
        assert window.results_page.table_bundle() is filtered_bundle_before

        _apply_pending_results_update(window, qapp)
        empty_bundle = window.results_page.table_bundle()
        assert calls["build_overlay_figure"] == before_empty_filter["build_overlay_figure"] + 1
        assert window.results_page.overlay_plot.figure is not filtered_figure_before
        assert len(window.results_page.overlay_plot.figure.data) == 0
        assert _visible_overlay_channels(window.results_page.overlay_plot.figure) == []
        assert all(trace.visible is False for trace in window.results_page.overlay_plot.figure.data)
        assert list(empty_bundle.table("overlay_reference").frame.columns) == []
        assert empty_bundle.summary["Overlay Channel Count"] == 0
    finally:
        window.close()
        qapp.processEvents()


def test_hover_style_rebuilds_plotly_figures_from_cache(qapp, monkeypatch) -> None:
    calls = _count_wizard_calls(
        monkeypatch,
        [
            "calculate_residual_diagnostics",
            "calculate_rolling_diagnostics",
            "calculate_statistical_metrics",
            "build_metrics_figure",
            "build_residual_figure",
            "build_sign_agreement_plot_data",
        ],
    )
    window = SensorComparisonWindow(plot_view_factory=DummyPlotView)
    try:
        _open_mock_results(window, qapp)
        before = calls.copy()
        sign_figure_before = window.results_page.sign_plot.figure
        table_bundle_before = window.results_page.table_bundle()

        window.cycle_hover_annotation_style()
        qapp.processEvents()

        assert window.results_page.update_button.isEnabled()
        assert calls == before
        assert window.results_page.sign_plot.figure is sign_figure_before
        assert window.results_page.table_bundle() is table_bundle_before

        _apply_pending_results_update(window, qapp)

        assert calls["build_metrics_figure"] == before["build_metrics_figure"] + 1
        assert calls["build_residual_figure"] == before["build_residual_figure"] + 1
        assert calls["build_sign_agreement_plot_data"] == before["build_sign_agreement_plot_data"]
        assert calls["calculate_residual_diagnostics"] == before["calculate_residual_diagnostics"]
        assert calls["calculate_rolling_diagnostics"] == before["calculate_rolling_diagnostics"]
        assert calls["calculate_statistical_metrics"] == before["calculate_statistical_metrics"]
        assert window.results_page.sign_plot.figure is sign_figure_before
        assert window.results_page.table_bundle() is table_bundle_before
    finally:
        window.close()
        qapp.processEvents()


def test_detached_plot_window_screenshot_contains_plot_content(qapp, tmp_path) -> None:
    window = SensorComparisonWindow(plot_view_factory=ScreenshotPlotView)
    try:
        window.load_page.set_input_mode(window.load_page.SEPARATE_MODE)
        window.load_page.path1_edit.setText(str(REFERENCE_CSV))
        window.load_page.path2_edit.setText(str(CANDIDATE_CSV))
        window.load_page.name1_edit.setText("Reference")
        window.load_page.name2_edit.setText("Candidate")
        for _step in range(4):
            window.go_next()
        assert window.stack.currentIndex() == 4
        assert window.results_page.metrics_plot.figure is not None

        window.results_page.detach_current_plot()
        qapp.processEvents()
        assert 0 in window.results_page._detached_plots
        detached_state = window.results_page._detached_plots[0]
        assert detached_state.window.isVisible()
        assert isinstance(detached_state.detached_widget, ScreenshotPlotView)

        pixmap = detached_state.window.grab()
        screenshot_path = tmp_path / "detached_metrics_plot.png"
        assert pixmap.save(str(screenshot_path))
        assert screenshot_path.stat().st_size > 0

        image = pixmap.toImage()
        colored_pixels = 0
        for y in range(0, image.height(), 3):
            for x in range(0, image.width(), 3):
                color = QColor(image.pixel(x, y))
                blue_plot = color.blue() > 130 and color.red() < 120
                red_marker = color.red() > 140 and color.blue() < 120
                if blue_plot or red_marker:
                    colored_pixels += 1
        assert colored_pixels > 120
    finally:
        window.close()
        qapp.processEvents()


def test_sensor_comparison_load_page_accepts_plotly_html_preview(qapp, plotly_html_paths: dict[str, Path]) -> None:
    window = SensorComparisonWindow(plot_view_factory=DummyPlotView)
    try:
        assert window.load_page.input_mode() == window.load_page.OVERLAY_MODE
        assert window.load_page.input_stack.currentWidget() is window.load_page.overlay_panel
        assert window.load_page.input_stack.sizePolicy().verticalPolicy() == QSizePolicy.Policy.Maximum
        assert window.load_page.overlay_panel.sizePolicy().verticalPolicy() == QSizePolicy.Policy.Maximum
        assert window.load_page.separate_panel.sizePolicy().verticalPolicy() == QSizePolicy.Policy.Maximum
        assert window.load_page.input_stack.sizeHint().height() <= window.load_page.overlay_panel.sizeHint().height() + 12
        assert window.load_page.input_stack.maximumHeight() <= window.load_page.overlay_panel.sizeHint().height() + 12
        assert window.next_button.text() == "Review Matched Channels"
        assert window.load_page.overlay_mode_button.isChecked()
        assert not window.load_page.separate_mode_button.isChecked()

        window.load_page.overlay_path_edit.setText(str(plotly_html_paths["mixed"]))
        qapp.processEvents()

        assert window.dataset1 is not None
        assert window.dataset2 is not None
        assert window.dataset1.display_name == "Main"
        assert window.dataset2.display_name == "Comp"
        assert "Main: Accel_X [g]" in window.dataset1.channels
        assert "Comp: LVDT_Stroke [mm]" in window.dataset1.channels
        assert window.load_page.summary1.text().startswith("Reference: Main traces\n")
        assert window.load_page.summary2.text().startswith("Candidate: Comp traces\n")
        assert "49 rows | 7 matched pairs" in window.load_page.summary1.text()
        assert window.load_page.input_stack.currentWidget() is window.load_page.overlay_panel
        assert window.load_page.overlay_clear_button.isEnabled()
    finally:
        window.close()
        qapp.processEvents()


def test_sensor_comparison_load_page_switches_modes_without_clearing_paths(
    qapp,
    plotly_html_paths: dict[str, Path],
) -> None:
    window = SensorComparisonWindow(plot_view_factory=DummyPlotView)
    try:
        window.load_page.set_input_mode(window.load_page.SEPARATE_MODE)
        qapp.processEvents()

        assert window.load_page.input_mode() == window.load_page.SEPARATE_MODE
        assert window.load_page.input_stack.currentWidget() is window.load_page.separate_panel
        assert window.next_button.text() == "Next"

        window.load_page.path1_edit.setText(str(REFERENCE_CSV))
        window.load_page.path2_edit.setText(str(CANDIDATE_CSV))
        window.load_page.name1_edit.setText("Reference")
        window.load_page.name2_edit.setText("Candidate")
        qapp.processEvents()
        assert window.dataset1 is not None
        assert window.dataset2 is not None
        assert window.load_page.summary1.text().startswith("Reference\n")

        window.load_page.set_input_mode(window.load_page.OVERLAY_MODE)
        qapp.processEvents()
        assert window.load_page.input_stack.currentWidget() is window.load_page.overlay_panel
        assert window.load_page.path1_edit.text() == str(REFERENCE_CSV)
        assert window.load_page.path2_edit.text() == str(CANDIDATE_CSV)
        assert window.dataset1 is None
        assert "Select one SG Plotly HTML overlay file." in window.load_page.summary1.text()

        window.load_page.overlay_path_edit.setText(str(plotly_html_paths["mixed"]))
        qapp.processEvents()
        assert window.dataset1 is not None
        assert window.dataset1.display_name == "Main"

        window.load_page.set_input_mode(window.load_page.SEPARATE_MODE)
        qapp.processEvents()
        assert window.load_page.input_stack.currentWidget() is window.load_page.separate_panel
        assert window.load_page.overlay_path_edit.text() == str(plotly_html_paths["mixed"])
        assert window.load_page.path1_edit.text() == str(REFERENCE_CSV)
        assert window.load_page.path2_edit.text() == str(CANDIDATE_CSV)
        assert window.dataset1 is not None
        assert window.dataset1.display_name == "Reference"
        assert window.dataset2 is not None
        assert window.dataset2.display_name == "Candidate"
    finally:
        window.close()
        qapp.processEvents()


def test_sensor_comparison_wizard_auto_pairs_single_overlay_html(qapp, plotly_html_paths: dict[str, Path]) -> None:
    window = SensorComparisonWindow(plot_view_factory=DummyPlotView)
    try:
        window.load_page.overlay_path_edit.setText(str(plotly_html_paths["mixed"]))
        qapp.processEvents()

        window.go_next()
        assert window.stack.currentIndex() == 1
        left = [window.match_page.left_list.item(index).text() for index in range(window.match_page.left_list.count())]
        right = [window.match_page.right_list.item(index).text() for index in range(window.match_page.right_list.count())]
        assert left[:3] == ["Main: Accel_X [g]", "Main: Accel_Z [g]", "Main: LVDT_Stroke [mm]"]
        assert right[:3] == ["Comp: Accel_X [g]", "Comp: Accel_Z [g]", "Comp: LVDT_Stroke [mm]"]

        window.go_next()
        assert window.stack.currentIndex() == 2
        assert window.name_page.table.rowCount() == len(left)
        assert window.name_page.table.item(0, 2).text() == "Accel_X [g]"
        assert window.name_page.table.item(2, 2).text() == "LVDT_Stroke [mm]"
        assert window.name_page.table.item(6, 2).text() == "SG57_von_Mises [MPa]"

        window.go_next()
        assert window.stack.currentIndex() == 3
        assert [window.config_page.reference_combo.itemText(index) for index in range(2)] == ["Main", "Comp"]

        window.go_next()
        assert window.stack.currentIndex() == 4
        assert [window.results_page.reference_combo.itemText(index) for index in range(2)] == ["Main", "Comp"]
        overlay_figure = window.results_page.overlay_plot.figure
        assert overlay_figure is not None
        assert overlay_figure.data[0].name == "Main - Accel_X [g]"
        assert overlay_figure.data[1].name == "Comp - Accel_X [g]"
        assert "SG_Calculations" not in str(overlay_figure.layout.title.text)
    finally:
        window.close()
        qapp.processEvents()


def test_sensor_comparison_wizard_progresses_with_mock_inputs(qapp, monkeypatch, tmp_path) -> None:
    window = SensorComparisonWindow(plot_view_factory=DummyPlotView)
    try:
        window.load_page.set_input_mode(window.load_page.SEPARATE_MODE)
        window.load_page.path1_edit.setText(str(REFERENCE_CSV))
        assert "Not loaded" not in window.load_page.summary1.text()
        assert "rows |" in window.load_page.summary1.text()

        window.load_page.path2_edit.setText(str(CANDIDATE_CSV))
        window.load_page.name1_edit.setText("Reference")
        window.load_page.name2_edit.setText("Candidate")
        assert window.load_page.summary1.text().startswith("Reference\n")
        assert window.load_page.summary2.text().startswith("Candidate\n")
        assert window.match_page.left_list.count() > 0
        assert window.match_page.right_list.count() > 0

        window.go_next()
        assert window.stack.currentIndex() == 1
        assert window.match_page.left_list.count() > 0
        assert window.step_labels[0].property("state") == "completed"
        assert window.step_labels[1].property("state") == "current"
        icon_buttons = [
            button
            for button in window.match_page.findChildren(QWidget)
            if button.property("iconButton") == "true"
        ]
        assert len(icon_buttons) == 6
        assert all(not button.text() for button in icon_buttons)
        assert all(button.toolTip() for button in icon_buttons)

        window.go_next()
        assert window.stack.currentIndex() == 2
        assert window.name_page.table.rowCount() == window.match_page.left_list.count()

        window.go_next()
        assert window.stack.currentIndex() == 3
        assert window.config_page.reference_combo.count() == 2

        progress_messages = []
        original_set_status = window.config_page.set_status

        def record_config_status(message: str) -> None:
            progress_messages.append((window.stack.currentIndex(), message))
            original_set_status(message)

        monkeypatch.setattr(window.config_page, "set_status", record_config_status)
        window.go_next()
        assert window.stack.currentIndex() == 4
        messages_before_advance = [
            message for page_index, message in progress_messages if page_index == 3
        ]
        quality_messages = []
        for dataset_name in ("Reference", "Target"):
            quality_messages.append(f"Checking {dataset_name} timestamps...")
            for channel_index, channel in enumerate(window.results_page.selected_columns(), start=1):
                label = f"{dataset_name} channel {channel_index}/{window.results_page.channel_list.count()}: {channel}"
                quality_messages.extend(
                    [
                        f"Checking {label} - NaN/Inf...",
                        f"Checking {label} - flatlines...",
                        f"Checking {label} - clipping...",
                        f"Checking {label} - spikes...",
                    ]
                )
        assert "Calculating diagnostics..." not in messages_before_advance
        assert "Checking data quality..." not in messages_before_advance
        assert messages_before_advance == [
            "Preparing analysis settings...",
            "Filtering 6 channels from 0 to 10...",
            "Calculating scale and offset transforms...",
            "Building overlay transforms...",
            "Calculating residual diagnostics...",
            "Calculating lag diagnostics...",
            "Calculating event timing diagnostics...",
            *quality_messages,
            "Calculating calibration diagnostics...",
            "Calculating frequency diagnostics...",
            "Calculating sign agreement...",
            "Calculating rolling diagnostics...",
            "Calculating statistical metrics...",
            "Building analysis tables...",
            "Building metrics figure...",
            "Building certification ranking figure...",
            "Building scale and offset figure...",
            "Building sign agreement figure...",
            "Building residual figure...",
            "Building rolling diagnostics figure...",
            "Building lag figure...",
            "Building calibration figure...",
            "Building frequency figure...",
            "Building overlay figure...",
            "Rendering result plots...",
            "Opening Analyze Results...",
        ]
        assert window.results_page.metrics_plot.figure is not None
        assert window.results_page.certification_plot.figure is not None
        assert window.results_page.scale_plot.figure is not None
        assert window.results_page.sign_plot.figure is not None
        assert window.results_page.residual_plot.figure is not None
        assert window.results_page.rolling_plot.figure is not None
        assert window.results_page.lag_plot.figure is not None
        assert window.results_page.calibration_plot.figure is not None
        assert window.results_page.frequency_plot.figure is not None
        assert window.results_page.overlay_plot.figure is not None
        assert window.results_page.table_bundle() is not None
        assert window.results_page.metrics_table.table.title == "Statistical Metrics"
        assert window.results_page.metrics_table.model().rowCount() == window.results_page.channel_list.count()
        assert window.results_page.metrics_table.model().headerData(0, Qt.Orientation.Horizontal) == "Channel"
        assert window.results_page.update_button.text() == "Update Data & Plots"
        assert window.results_page.update_button.accessibleName() == "Update Data and Plots"
        assert not window.results_page.update_button.isEnabled()
        metrics_frame = window.results_page.table_bundle().table("metrics").frame
        assert "Within Tolerance Abs (%)" in metrics_frame.columns
        assert "Within Tolerance Rel (%)" in metrics_frame.columns
        assert "Robust NMAE (%)" in metrics_frame.columns
        assert "Certification Score" in metrics_frame.columns
        assert "Evidence Grade" in metrics_frame.columns
        assert metrics_frame["Within Tolerance Abs (%)"].isna().all()
        assert metrics_frame["Within Tolerance Rel (%)"].isna().all()
        certification_table = window.results_page.table_bundle().table("certification_ranking")
        assert certification_table.title == "Certification Ranking"
        assert certification_table.frame["Channel"].tolist()
        assert window.results_page.certification_table.table.title == "Certification Ranking"
        certification_channel = str(certification_table.frame["Channel"].iloc[0])
        metrics_cache_before_certification_selection = window._metrics_cache
        certification_figure_before_selection = window.results_page.certification_plot.figure
        # Labels default to hover-only ("none"): selecting a row rebuilds the figure and
        # spotlights the marker, but no longer pins a permanent text label.
        assert window.results_page.certification_label_combo.currentData() == "none"
        window.results_page.certification_table.selectRow(0)
        qapp.processEvents()
        certification_figure_after_selection = window.results_page.certification_plot.figure
        certification_peak_trace = next(
            trace for trace in certification_figure_after_selection.data if trace.name == "Peak parity"
        )
        assert window._metrics_cache is metrics_cache_before_certification_selection
        assert certification_figure_after_selection is not certification_figure_before_selection
        assert not window.results_page.update_button.isEnabled()
        assert certification_peak_trace.mode == "markers"
        assert not any(certification_peak_trace.text)

        # Picking a labeling mode pins the selected channel's label back onto the plot.
        selected_label_index = window.results_page.certification_label_combo.findData("selected")
        assert selected_label_index >= 0
        window.results_page.certification_label_combo.setCurrentIndex(selected_label_index)
        qapp.processEvents()
        labeled_peak_trace = next(
            trace for trace in window.results_page.certification_plot.figure.data if trace.name == "Peak parity"
        )
        assert window._metrics_cache is metrics_cache_before_certification_selection
        assert certification_channel in labeled_peak_trace.text
        assert not window.results_page.update_button.isEnabled()
        refresh_count_before_tolerance = window.results_page.metrics_plot.refresh_count
        residual_figure_before_tolerance = window.results_page.residual_plot.figure
        window.results_page.abs_tolerance_spin.setValue(999999.0)
        window.results_page.rel_tolerance_spin.setValue(5.0)
        qapp.processEvents()
        assert window.results_page.update_button.isEnabled()
        assert "Click Update Data & Plots" in window.results_page.status_label.text()
        metrics_frame = window.results_page.table_bundle().table("metrics").frame
        assert metrics_frame["Within Tolerance Abs (%)"].isna().all()
        assert metrics_frame["Within Tolerance Rel (%)"].isna().all()
        assert window.results_page.residual_plot.figure is residual_figure_before_tolerance

        _apply_pending_results_update(window, qapp)
        metrics_frame = window.results_page.table_bundle().table("metrics").frame
        # The large absolute tolerance places every sample inside the absolute band.
        assert metrics_frame["Within Tolerance Abs (%)"].tolist() == pytest.approx([100.0] * len(metrics_frame))
        assert window.results_page.metrics_plot.refresh_count == refresh_count_before_tolerance
        assert window.results_page.residual_plot.figure is not residual_figure_before_tolerance
        refresh_count_after_tolerance = window.results_page.metrics_plot.refresh_count
        assert "abs tol 999999" in window.results_page.status_label.text()
        assert "rel tol 5%" in window.results_page.status_label.text()
        assert window.results_page.scale_table.table.title == "Scale and Offset"
        assert window.results_page.calibration_table.model().rowCount() == window.results_page.channel_list.count()
        assert window.results_page.calibration_table.model().headerData(1, Qt.Orientation.Horizontal) == "Calibration Slope"
        assert window.results_page.events_table.model().rowCount() > 0
        assert window.results_page.quality_table.model().rowCount() > 0
        assert window.results_page.overlay_table.table.title == "Overlay Reference"
        assert window.results_page.overlay_view.table_selector.count() == 5
        assert window.results_page.data_tables_view.combo.count() >= 20
        assert window.results_page.current_table().title == "Statistical Metrics"
        assert window.results_page.metrics_panel.splitter.orientation() == Qt.Orientation.Vertical
        assert not window.results_page.metrics_panel.splitter.childrenCollapsible()
        assert window.results_page.metrics_table.maximumHeight() > 1000
        assert window.results_page.overlay_view.splitter.orientation() == Qt.Orientation.Vertical
        assert not window.results_page.metrics_panel.table_collapsed
        assert window.results_page.metrics_panel.table_section.collapsed_handle.objectName() == "CollapsedTableHandle"
        assert window.results_page.metrics_panel.table_section.collapse_button.property("tableHandle") == "true"
        window.results_page.metrics_panel.splitter.setSizes([420, 260])
        assert len(window.results_page.metrics_panel.splitter.sizes()) == 2
        window.results_page.metrics_panel.collapse_table()
        assert window.results_page.metrics_panel.table_collapsed
        assert window.results_page.metrics_panel.table_section.table_panel.isHidden()
        assert not window.results_page.metrics_panel.table_section.collapsed_handle.isHidden()
        assert window.results_page.current_table().title == "Statistical Metrics"
        window.results_page.metrics_panel.expand_table()
        assert not window.results_page.metrics_panel.table_collapsed
        assert not window.results_page.metrics_panel.table_section.table_panel.isHidden()
        assert window.results_page.metrics_panel.table_section.collapsed_handle.isHidden()
        window.results_page.events_view.collapse_table()
        assert window.results_page.events_view.table_collapsed
        assert not window.results_page.events_view.table_section.collapsed_handle.isHidden()
        window.results_page.events_view.expand_table()
        window.results_page.overlay_view.collapse_table()
        assert window.results_page.overlay_view.table_collapsed
        window.results_page.overlay_view.expand_table()
        window.results_page.data_tables_view.collapse_table()
        assert window.results_page.data_tables_view.table_collapsed
        window.results_page.data_tables_view.expand_table()
        assert window.results_page.channels_panel_collapsed is False
        assert not window.results_page.channels_sidebar.isHidden()
        assert window.results_page.channels_restore_rail.isHidden()
        assert window.results_page.channels_collapse_button.accessibleName() == "Collapse Channels"
        assert window.results_page.channels_collapse_button.property("paneHandle") == "true"
        assert window.results_page.channels_collapse_button.property("paneTheme") == "panel"
        assert window.results_page.channels_restore_handle.objectName() == "CollapsedPaneHandle"
        assert isinstance(window.results_page.channels_restore_handle, QFrame)
        assert not isinstance(window.results_page.channels_restore_handle, QPushButton)
        assert window.results_page.channels_restore_handle.height() > window.results_page.channels_restore_handle.width()
        assert window.results_page.channels_restore_handle.accessibleName() == "Show Channels"
        assert window.results_page.channels_restore_rail.property("railTheme") == "panel"
        window.results_page.collapse_channels_panel()
        assert window.results_page.channels_panel_collapsed is True
        assert window.results_page.channels_sidebar.isHidden()
        assert not window.results_page.channels_restore_rail.isHidden()
        assert window.results_page.channels_restore_handle.isHidden()
        assert window.results_page.channels_shell.minimumWidth() == window.results_page.COLLAPSED_RAIL_WIDTH
        assert window.results_page.channels_shell.maximumWidth() == window.results_page.COLLAPSED_RAIL_WIDTH
        window.results_page.channels_restore_rail.set_revealed(True)
        assert not window.results_page.channels_restore_handle.isHidden()
        assert window.results_page.channels_restore_handle.width() == window.results_page.COLLAPSED_HANDLE_WIDTH
        assert window.results_page.channels_shell.minimumWidth() == window.results_page.COLLAPSED_RAIL_WIDTH
        window.results_page.channels_restore_rail.conceal()
        assert window.results_page.channels_restore_handle.isHidden()
        assert window.results_page.channels_shell.minimumWidth() == window.results_page.COLLAPSED_RAIL_WIDTH
        assert window.results_page.channel_list.count() > 0
        window.results_page.expand_channels_panel()
        assert window.results_page.channels_panel_collapsed is False
        assert not window.results_page.channels_sidebar.isHidden()
        assert window.results_page.channels_restore_rail.isHidden()
        assert window.results_page.channels_shell.minimumWidth() == window.results_page.CHANNELS_EXPANDED_MIN_WIDTH
        window.results_page.metrics_table.selectAll()
        copied = window.results_page.metrics_table.copy_selection(include_headers=True)
        assert "Channel" in copied
        assert "SG_Front_Left" in copied
        assert window.results_page.metrics_plot.refresh_count == refresh_count_after_tolerance
        exported_bundles = []
        monkeypatch.setattr(
            wizard_module.QFileDialog,
            "getSaveFileName",
            lambda *_args, **_kwargs: (str(tmp_path / "current_table.xlsx"), "Excel Workbook (*.xlsx)"),
        )
        monkeypatch.setattr(
            wizard_module,
            "write_analysis_workbook",
            lambda path, bundle: exported_bundles.append((path, bundle)) or Path(path),
        )
        monkeypatch.setattr(wizard_module.QMessageBox, "exec", lambda _self: 0)
        window.export_current_table()
        assert exported_bundles[0][1].tables[0].title == "Statistical Metrics"
        assert exported_bundles[0][1].summary["Abs tol"] == pytest.approx(999999.0)
        assert exported_bundles[0][1].summary["Rel tol %"] == pytest.approx(5.0)
        assert exported_bundles[0][1].summary["Noise floor"] == pytest.approx(0.0)
        full_scope = wizard_module.MasterExportDialog.FULL_SCOPE

        class FakeMasterExportDialog:
            FULL_SCOPE = full_scope

            def __init__(self, _parent=None):
                pass

            def exec(self):
                return wizard_module.QDialog.DialogCode.Accepted

            def selected_scope(self):
                return full_scope

        monkeypatch.setattr(wizard_module, "MasterExportDialog", FakeMasterExportDialog)
        window.export_master_workbook()
        assert exported_bundles[-1][1].scope == "Full aligned data"
        assert exported_bundles[-1][1].table("metrics").frame.shape[0] == window.results_page.channel_list.count()
        assert exported_bundles[-1][1].table("metrics").frame["Within Tolerance Abs (%)"].tolist() == pytest.approx(
            [100.0] * window.results_page.channel_list.count()
        )
        assert window.results_page.sign_plot.refresh_count == 0
        assert window.hover_annotation_shortcut.key().toString() == "H"
        assert window.results_page.metrics_plot.figure.layout.hovermode == "x unified"
        assert window.results_page.metrics_plot.figure.layout.hoverlabel.bgcolor == "rgba(255, 255, 255, 0.78)"
        assert window.results_page.metrics_plot.figure.data[0].hovertemplate is None
        assert "hover annotations: Sensor" in window.results_page.status_label.text()

        window.cycle_hover_annotation_style()
        qapp.processEvents()
        assert window.results_page.update_button.isEnabled()
        assert window.results_page.metrics_plot.figure.layout.hovermode == "x unified"
        _apply_pending_results_update(window, qapp)
        assert window.results_page.metrics_plot.figure.layout.hovermode == "closest"
        assert window.results_page.metrics_plot.figure.layout.hoverlabel.bgcolor == "rgba(240, 240, 240, 0.9)"
        assert window.results_page.metrics_plot.figure.layout.hoverlabel.font.size == 15
        assert (
            window.results_page.metrics_plot.figure.data[0].hovertemplate
            == "%{fullData.name}<br>Channel: %{x}<br>Metric Value: %{y:.3f}<extra></extra>"
        )
        assert "hover annotations: WE-DAVIS" in window.results_page.status_label.text()

        window.cycle_hover_annotation_style()
        qapp.processEvents()
        assert window.results_page.update_button.isEnabled()
        assert window.results_page.metrics_plot.figure.layout.hovermode == "closest"
        _apply_pending_results_update(window, qapp)
        assert window.results_page.metrics_plot.figure.layout.hovermode == "x unified"
        assert window.results_page.metrics_plot.figure.layout.hoverlabel.bgcolor == "rgba(255, 255, 255, 0.78)"
        assert window.results_page.metrics_plot.figure.data[0].hovertemplate is None
        assert "hover annotations: Sensor" in window.results_page.status_label.text()

        assert window.results_page.detach_button.text() == ""
        assert window.results_page.detach_button.property("iconButton") == "true"
        assert not window.results_page.detach_button.icon().isNull()
        assert window.results_page.detach_button.accessibleName() == "Detach Plot"

        refresh_count_before_detach = window.results_page.metrics_plot.refresh_count
        window.results_page.detach_button.click()
        qapp.processEvents()
        assert 0 in window.results_page._detached_plots
        detached_state = window.results_page._detached_plots[0]
        assert window.results_page.tabs.widget(0) is detached_state.placeholder
        assert detached_state.window.isVisible()
        assert detached_state.tab_widget is window.results_page.metrics_panel
        assert detached_state.detached_widget is not window.results_page.metrics_panel
        assert detached_state.window.centralWidget() is detached_state.detached_widget
        assert getattr(detached_state.detached_widget, "figure", None) is window.results_page.metrics_plot.figure
        assert getattr(detached_state.detached_widget, "force_refresh_count", 0) >= 1
        assert window.results_page.metrics_plot.force_refresh_count == 0
        assert window.results_page.metrics_plot.refresh_count == refresh_count_before_detach
        refresh_count_after_detach = window.results_page.metrics_plot.refresh_count
        assert window.results_page.detach_button.text() == ""
        assert window.results_page.detach_button.accessibleName() == "Restore Plot"
        assert window.results_page.current_table().title == "Statistical Metrics"
        window.export_current_table()
        assert exported_bundles[-1][1].tables[0].title == "Statistical Metrics"

        detached_state.window.close()
        qapp.processEvents()
        assert 0 not in window.results_page._detached_plots
        assert window.results_page.tabs.widget(0) is window.results_page.metrics_panel
        assert window.results_page.metrics_plot.force_refresh_count == 1
        assert window.results_page.metrics_plot.refresh_count >= refresh_count_after_detach + 1
        assert window.results_page.detach_button.accessibleName() == "Detach Plot"

        window.results_page.tabs.setCurrentWidget(window.results_page.sign_plot)
        qapp.processEvents()
        assert window.results_page.sign_plot.refresh_count == 1
        assert window.results_page.metrics_plot.figure.layout.legend.x == pytest.approx(1.02)
        assert window.results_page.sign_plot.plot_data is not None
        assert window.results_page.sign_plot.figure.status_frame.shape[0] > 0
        assert window.results_page.sign_plot.summary_table.rowCount() == len(window.results_page.sign_plot._channels)

        window.cycle_legend_position()
        assert window.legend_position == "top left"
        assert window.results_page.update_button.isEnabled()
        assert window.results_page.metrics_plot.figure.layout.legend.x == pytest.approx(1.02)
        _apply_pending_results_update(window, qapp)
        assert window.results_page.metrics_plot.figure.layout.legend.x == pytest.approx(0.01)

        window.results_page._set_all_metrics(False)
        assert window.results_page.selected_metric_keys() == []
        window.results_page._reset_default_metrics()
        assert "RMSE" in window.results_page.selected_metric_keys()
    finally:
        window.close()
        qapp.processEvents()

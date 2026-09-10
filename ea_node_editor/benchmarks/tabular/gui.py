from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from ea_node_editor.benchmarks.tabular.adapters import available_format_adapters
from ea_node_editor.benchmarks.tabular.contracts import (
    DEFAULT_FORMATS,
    DEFAULT_OPERATIONS,
    DEFAULT_PROFILES,
    SUPPORTED_BACKENDS,
    BenchmarkConfig,
)
from ea_node_editor.benchmarks.tabular.runner import run_benchmark_matrix

_QT_QUICK_CONTROLS_STYLE = "Basic"


def run_gui(
    args: Any,
    *,
    start_event_loop: bool = True,
    screenshot_path: Path | None = None,
    auto_run: bool = False,
    quit_on_complete: bool = False,
    quit_timeout_ms: int = 30_000,
) -> int:
    os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", _QT_QUICK_CONTROLS_STYLE)
    if os.environ.get("QT_QPA_PLATFORM", "").strip().lower() in {"offscreen", "minimal"}:
        os.environ.setdefault("QT_QUICK_BACKEND", "software")
        os.environ.setdefault("QSG_RHI_BACKEND", "software")

    from PyQt6.QtCore import (
        QAbstractTableModel,
        QModelIndex,
        QObject,
        QThread,
        QTimer,
        Qt,
        QUrl,
        pyqtProperty,
        pyqtSignal,
        pyqtSlot,
    )
    from PyQt6.QtGui import QGuiApplication
    from PyQt6.QtQml import QQmlApplicationEngine
    from PyQt6.QtQuick import QQuickWindow, QSGRendererInterface

    if os.environ.get("QT_QPA_PLATFORM", "").strip().lower() in {"offscreen", "minimal"}:
        QQuickWindow.setGraphicsApi(QSGRendererInterface.GraphicsApi.Software)

    class ResultsTableModel(QAbstractTableModel):
        columns = (
            "profile",
            "size",
            "format",
            "backend",
            "operation",
            "status",
            "time_ms",
            "throughput",
            "peak_rss_mb",
            "rss_delta_mb",
            "file_gib",
            "error",
        )

        def __init__(self) -> None:
            super().__init__()
            self._rows: list[dict[str, Any]] = []

        def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
            return 0 if parent.isValid() else len(self._rows)

        def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
            return 0 if parent.isValid() else len(self.columns)

        def data(self, index: QModelIndex, role: int = int(Qt.ItemDataRole.DisplayRole)) -> Any:
            if not index.isValid() or role != int(Qt.ItemDataRole.DisplayRole):
                return None
            row = self._rows[index.row()]
            return row.get(self.columns[index.column()], "")

        def headerData(  # noqa: N802
            self,
            section: int,
            orientation: Qt.Orientation,
            role: int = int(Qt.ItemDataRole.DisplayRole),
        ) -> Any:
            if role != int(Qt.ItemDataRole.DisplayRole):
                return None
            if orientation == Qt.Orientation.Horizontal:
                return self.columns[section]
            return section + 1

        def replace(self, rows: list[dict[str, Any]]) -> None:
            self.beginResetModel()
            self._rows = rows
            self.endResetModel()

    class PreviewTableModel(QAbstractTableModel):
        def __init__(self) -> None:
            super().__init__()
            self._columns: list[str] = []
            self._rows: list[list[str]] = []

        def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
            return 0 if parent.isValid() else len(self._rows)

        def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
            return 0 if parent.isValid() else len(self._columns)

        def data(self, index: QModelIndex, role: int = int(Qt.ItemDataRole.DisplayRole)) -> Any:
            if not index.isValid() or role != int(Qt.ItemDataRole.DisplayRole):
                return None
            return self._rows[index.row()][index.column()]

        def headerData(  # noqa: N802
            self,
            section: int,
            orientation: Qt.Orientation,
            role: int = int(Qt.ItemDataRole.DisplayRole),
        ) -> Any:
            if role != int(Qt.ItemDataRole.DisplayRole):
                return None
            if orientation == Qt.Orientation.Horizontal and section < len(self._columns):
                return self._columns[section]
            return section + 1

        def replace(self, columns: list[str], rows: list[list[str]]) -> None:
            self.beginResetModel()
            self._columns = columns
            self._rows = rows
            self.endResetModel()

    class BenchmarkWorker(QObject):
        finished = pyqtSignal(object, object)
        failed = pyqtSignal(str)

        def __init__(self, config: BenchmarkConfig) -> None:
            super().__init__()
            self._config = config

        @pyqtSlot()
        def run(self) -> None:
            try:
                results, paths = run_benchmark_matrix(self._config)
            except Exception as exc:  # noqa: BLE001
                self.failed.emit(f"{type(exc).__name__}: {exc}")
                return
            self.finished.emit(results, paths)

    class WorkbenchController(QObject):
        statusChanged = pyqtSignal()
        reportsChanged = pyqtSignal()
        runningChanged = pyqtSignal()
        summaryChanged = pyqtSignal()
        resultFilterChanged = pyqtSignal()
        visibleResultCountChanged = pyqtSignal()
        previewRowCountChanged = pyqtSignal()

        def __init__(self) -> None:
            super().__init__()
            self._status = "Ready"
            self._reports = ""
            self._running = False
            self._result_count = 0
            self._success_count = 0
            self._skipped_count = 0
            self._failure_count = 0
            self._visible_result_count = 0
            self._preview_row_count = 0
            self._result_filter = "all"
            self._all_result_rows: list[dict[str, Any]] = []
            self._thread: QThread | None = None
            self._worker: BenchmarkWorker | None = None
            self.results_model = ResultsTableModel()
            self.preview_model = PreviewTableModel()
            self.output_dir = str(Path(getattr(args, "out", "artifacts/tabular_bench")))
            self.sizes = getattr(args, "sizes", "small")
            self.profiles = getattr(args, "profiles", "mixed_table")
            self.formats = getattr(args, "formats", "csv,parquet")
            self.backends = getattr(args, "backends", "pandas,polars,duckdb,arrow")
            self.operations = getattr(args, "operations", "write,read,schema,preview,filter,groupby,compute")

        @pyqtProperty(str, notify=statusChanged)
        def status(self) -> str:
            return self._status

        @pyqtProperty(str, notify=reportsChanged)
        def reports(self) -> str:
            return self._reports

        @pyqtProperty(bool, notify=runningChanged)
        def running(self) -> bool:
            return self._running

        @pyqtProperty(int, notify=summaryChanged)
        def resultCount(self) -> int:
            return self._result_count

        @pyqtProperty(int, notify=summaryChanged)
        def successCount(self) -> int:
            return self._success_count

        @pyqtProperty(int, notify=summaryChanged)
        def skippedCount(self) -> int:
            return self._skipped_count

        @pyqtProperty(int, notify=summaryChanged)
        def failureCount(self) -> int:
            return self._failure_count

        @pyqtProperty(int, notify=visibleResultCountChanged)
        def visibleResultCount(self) -> int:
            return self._visible_result_count

        @pyqtProperty(int, notify=previewRowCountChanged)
        def previewRowCount(self) -> int:
            return self._preview_row_count

        @pyqtProperty(str, notify=resultFilterChanged)
        def resultFilter(self) -> str:
            return self._result_filter

        @pyqtProperty(QObject, constant=True)
        def resultsModel(self) -> QObject:
            return self.results_model

        @pyqtProperty(QObject, constant=True)
        def previewModel(self) -> QObject:
            return self.preview_model

        @pyqtProperty(str, constant=True)
        def defaultOutputDir(self) -> str:
            return self.output_dir

        @pyqtProperty(str, constant=True)
        def defaultSizes(self) -> str:
            return self.sizes

        @pyqtProperty(str, constant=True)
        def defaultProfiles(self) -> str:
            return self.profiles

        @pyqtProperty(str, constant=True)
        def defaultFormats(self) -> str:
            return self.formats

        @pyqtProperty(str, constant=True)
        def defaultBackends(self) -> str:
            return self.backends

        @pyqtProperty(str, constant=True)
        def defaultOperations(self) -> str:
            return self.operations

        @pyqtSlot(str, str, str, str, str, str)
        def runBenchmark(
            self,
            output_dir: str,
            sizes: str,
            profiles: str,
            formats: str,
            backends: str,
            operations: str,
        ) -> None:
            try:
                config = BenchmarkConfig(
                    output_dir=Path(output_dir),
                    sizes=_split(sizes, all_values=("small", "medium", "large")),
                    profiles=_split(profiles, all_values=DEFAULT_PROFILES),
                    formats=_split(formats, all_values=DEFAULT_FORMATS),
                    backends=_split(backends, all_values=SUPPORTED_BACKENDS),
                    operations=_split(operations, all_values=DEFAULT_OPERATIONS),
                    headless=False,
                )
            except Exception as exc:  # noqa: BLE001
                self._status = f"Failed: {type(exc).__name__}: {exc}"
                self.statusChanged.emit()
                return
            if self._running:
                return
            self._set_running(True)
            self._set_summary([])
            self._replace_result_rows([])
            self.preview_model.replace([], [])
            self._set_preview_row_count(0)
            self._reports = ""
            self.reportsChanged.emit()
            self._status = "Running benchmark matrix"
            self.statusChanged.emit()

            thread = QThread(self)
            worker = BenchmarkWorker(config)
            worker.moveToThread(thread)
            thread.started.connect(worker.run)
            worker.finished.connect(lambda results, paths, config=config: self._handle_finished(config, results, paths))
            worker.failed.connect(self._handle_failed)
            worker.finished.connect(worker.deleteLater)
            worker.failed.connect(worker.deleteLater)
            worker.finished.connect(thread.quit)
            worker.failed.connect(thread.quit)
            thread.finished.connect(thread.deleteLater)
            thread.finished.connect(self._clear_worker)
            self._thread = thread
            self._worker = worker
            thread.start()

        def _handle_finished(self, config: BenchmarkConfig, results: Any, paths: Any) -> None:
            self._replace_result_rows([_result_row(result.to_payload()) for result in results])
            self._load_first_preview(config, results)
            self._reports = " | ".join(str(path) for path in paths.values())
            self._set_summary(results)
            self._set_running(False)
            self._status = f"Complete: {self._success_count} ok, {self._skipped_count} skipped, {self._failure_count} failed"
            self.reportsChanged.emit()
            self.statusChanged.emit()

        @pyqtSlot(str)
        def setResultFilter(self, value: str) -> None:
            normalized = value.strip().lower()
            if normalized not in {"all", "ok", "skipped", "failed"}:
                return
            if self._result_filter == normalized:
                return
            self._result_filter = normalized
            self.resultFilterChanged.emit()
            self._apply_result_filter()

        def _handle_failed(self, message: str) -> None:
            self._set_running(False)
            self._status = f"Failed: {message}"
            self.statusChanged.emit()

        def _clear_worker(self) -> None:
            self._thread = None
            self._worker = None

        def _set_running(self, value: bool) -> None:
            if self._running == value:
                return
            self._running = value
            self.runningChanged.emit()

        def _set_summary(self, results: Any) -> None:
            self._result_count = len(results)
            self._success_count = sum(1 for result in results if result.success and not result.skipped)
            self._skipped_count = sum(1 for result in results if result.skipped)
            self._failure_count = sum(1 for result in results if not result.success and not result.skipped)
            self.summaryChanged.emit()

        def _replace_result_rows(self, rows: list[dict[str, Any]]) -> None:
            self._all_result_rows = rows
            self._apply_result_filter()

        def _apply_result_filter(self) -> None:
            if self._result_filter == "all":
                rows = self._all_result_rows
            else:
                rows = [row for row in self._all_result_rows if row["status"] == self._result_filter]
            self.results_model.replace(rows)
            self._visible_result_count = len(rows)
            self.visibleResultCountChanged.emit()

        def _set_preview_row_count(self, value: int) -> None:
            if self._preview_row_count == value:
                return
            self._preview_row_count = value
            self.previewRowCountChanged.emit()

        def _load_first_preview(self, config: BenchmarkConfig, results: Any) -> None:
            adapters = available_format_adapters()
            datasets_dir = config.output_dir / "datasets"
            for result in results:
                if not result.success or result.operation != "write":
                    continue
                adapter = adapters[result.format_id]
                path = adapter.path_for(datasets_dir, result.dataset)
                try:
                    preview = adapter.preview(path, rows=50, backend_id="pandas")
                except Exception:  # noqa: BLE001
                    continue
                columns, rows = _preview_payload(preview)
                self.preview_model.replace(columns, rows)
                self._set_preview_row_count(len(rows))
                return
            self.preview_model.replace([], [])
            self._set_preview_row_count(0)

    app = QGuiApplication.instance() or QGuiApplication([])
    controller = WorkbenchController()
    engine = QQmlApplicationEngine()
    engine.rootContext().setContextProperty("tabularController", controller)
    engine.loadData(_QML.encode("utf-8"), QUrl("qrc:/TabularBenchmarkWorkbench.qml"))
    if not engine.rootObjects():
        return 1
    if auto_run:
        if quit_on_complete:
            def maybe_quit() -> None:
                if not controller.running and (controller.resultCount > 0 or controller.status.startswith("Failed")):
                    app.quit()

            controller.statusChanged.connect(maybe_quit)
        controller.runBenchmark(
            controller.defaultOutputDir,
            controller.defaultSizes,
            controller.defaultProfiles,
            controller.defaultFormats,
            controller.defaultBackends,
            controller.defaultOperations,
        )
    if not start_event_loop:
        app.processEvents()
        if screenshot_path is not None:
            screenshot_path.parent.mkdir(parents=True, exist_ok=True)
            window = engine.rootObjects()[0]
            screen = app.primaryScreen()
            if screen is not None:
                screen.grabWindow(int(window.winId())).save(str(screenshot_path))
        return 0
    if quit_on_complete:
        QTimer.singleShot(quit_timeout_ms, app.quit)
    exit_code = int(app.exec())
    if auto_run and (controller.running or controller.resultCount == 0 or controller.failureCount > 0):
        return 2
    return exit_code


def _split(value: str, *, all_values: tuple[str, ...]) -> tuple[str, ...]:
    normalized = value.strip().lower()
    if normalized == "all":
        return all_values
    values = tuple(part.strip() for part in value.split(",") if part.strip())
    if not values:
        raise ValueError("Expected at least one comma-separated value.")
    return values


def _result_row(payload: dict[str, Any]) -> dict[str, Any]:
    dataset = payload["dataset"]
    rss_peak_delta = payload.get("rss_peak_delta_bytes", payload.get("rss_delta_bytes", 0))
    rss_delta = payload.get("rss_delta_bytes", 0)
    file_size = payload.get("file_size_bytes", 0)
    return {
        "profile": dataset["profile"],
        "size": dataset["size"],
        "format": payload["format_id"],
        "backend": payload["backend_id"],
        "operation": payload["operation"],
        "status": "skipped" if payload.get("skipped") else ("ok" if payload["success"] else "failed"),
        "time_ms": f"{payload['elapsed_ms']:.2f}",
        "throughput": f"{payload['throughput_mb_s']:.2f}",
        "peak_rss_mb": f"{rss_peak_delta / 1024 / 1024:.1f}",
        "rss_delta_mb": f"{rss_delta / 1024 / 1024:.1f}",
        "file_gib": f"{file_size / 1024 / 1024 / 1024:.3f}",
        "error": payload["error"],
    }


_QML = """
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

    ApplicationWindow {
    id: root
    width: 1320
    height: 820
    visible: true
    title: "Tabular Benchmark Workbench"
    color: "#f4f6f8"
    font.family: "Segoe UI"

    readonly property color panelColor: "#ffffff"
    readonly property color borderColor: "#d7dee6"
    readonly property color textColor: "#17212b"
    readonly property color mutedColor: "#637083"
    readonly property color accentColor: "#1264a3"
    readonly property color successColor: "#1f8a5b"
    readonly property color warningColor: "#9f6b00"
    readonly property color dangerColor: "#b42318"
    readonly property string uiFontFamily: "Segoe UI"

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 18
        spacing: 12

        Rectangle {
            Layout.fillWidth: true
            implicitHeight: 72
            color: root.panelColor
            border.color: root.borderColor
            radius: 8

            RowLayout {
                anchors.fill: parent
                anchors.margins: 14
                spacing: 14

                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 4
                    Label {
                        text: "Tabular Benchmark Workbench"
                        color: root.textColor
                        font.pixelSize: 20
                        font.bold: true
                    }
                    Label {
                        text: tabularController.status
                        color: tabularController.failureCount > 0 ? root.dangerColor : root.mutedColor
                        elide: Text.ElideRight
                        Layout.fillWidth: true
                    }
                }

                BusyIndicator {
                    running: tabularController.running
                    visible: tabularController.running
                    implicitWidth: 30
                    implicitHeight: 30
                }

                Button {
                    id: runButton
                    text: tabularController.running ? "Running" : "Run"
                    enabled: !tabularController.running
                    Layout.preferredWidth: 118
                    Layout.preferredHeight: 42
                    contentItem: Text {
                        text: runButton.text
                        color: "#ffffff"
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignVCenter
                        font.pixelSize: 14
                        font.bold: true
                    }
                    background: Rectangle {
                        color: runButton.enabled ? root.accentColor : "#b7c0ca"
                        radius: 6
                    }
                    onClicked: tabularController.runBenchmark(
                        outputDir.text,
                        sizes.text,
                        profiles.text,
                        formats.text,
                        backends.text,
                        operations.text
                    )
                }
            }
        }

        Rectangle {
            Layout.fillWidth: true
            implicitHeight: 190
            color: root.panelColor
            border.color: root.borderColor
            radius: 8

            GridLayout {
                anchors.fill: parent
                anchors.margins: 14
                columns: 8
                columnSpacing: 10
                rowSpacing: 8

                Label { text: "Preset"; color: root.mutedColor }
                RowLayout {
                    Layout.columnSpan: 7
                    Layout.fillWidth: true
                    spacing: 8
                    BenchPresetButton {
                        text: "Backend Decision"
                        onClicked: {
                            sizes.text = "small"
                            profiles.text = "mixed_table"
                            formats.text = "csv,parquet"
                            backends.text = "pandas,polars,duckdb,arrow"
                            operations.text = "write,read,schema,preview,filter,groupby,compute"
                        }
                    }
                    BenchPresetButton {
                        text: "Array Paths"
                        onClicked: {
                            sizes.text = "small"
                            profiles.text = "dense_numeric"
                            formats.text = "npy,npz,hdf5"
                            backends.text = "numpy,pandas,polars,duckdb,arrow"
                            operations.text = "write,read,schema,preview,filter,groupby,compute"
                        }
                    }
                    BenchPresetButton {
                        text: "Format Smoke"
                        onClicked: {
                            sizes.text = "small"
                            profiles.text = "mixed_table,dense_numeric,excel_like"
                            formats.text = "all"
                            backends.text = "all"
                            operations.text = "write,read,schema,preview"
                        }
                    }
                    BenchPresetButton {
                        text: "Medium Scale"
                        onClicked: {
                            sizes.text = "medium"
                            profiles.text = "mixed_table"
                            formats.text = "csv,parquet"
                            backends.text = "pandas,polars,duckdb,arrow"
                            operations.text = "write,read,schema,preview,filter,groupby,compute"
                        }
                    }
                    Item { Layout.fillWidth: true }
                }

                Label { text: "Output"; color: root.mutedColor }
                BenchTextField {
                    id: outputDir
                    Layout.columnSpan: 7
                    Layout.fillWidth: true
                    text: tabularController.defaultOutputDir
                }

                Label { text: "Sizes"; color: root.mutedColor }
                BenchTextField { id: sizes; Layout.fillWidth: true; text: tabularController.defaultSizes }
                Label { text: "Profiles"; color: root.mutedColor }
                BenchTextField { id: profiles; Layout.fillWidth: true; text: tabularController.defaultProfiles }
                Label { text: "Formats"; color: root.mutedColor }
                BenchTextField { id: formats; Layout.fillWidth: true; text: tabularController.defaultFormats }
                Label { text: "Backends"; color: root.mutedColor }
                BenchTextField { id: backends; Layout.fillWidth: true; text: tabularController.defaultBackends }

                Label { text: "Operations"; color: root.mutedColor }
                BenchTextField {
                    id: operations
                    Layout.columnSpan: 7
                    Layout.fillWidth: true
                    text: tabularController.defaultOperations
                }
            }
        }

        RowLayout {
            Layout.fillWidth: true
            spacing: 10
            MetricChip { label: "Cases"; value: tabularController.resultCount; colorValue: root.accentColor }
            MetricChip { label: "Ok"; value: tabularController.successCount; colorValue: root.successColor }
            MetricChip { label: "Skipped"; value: tabularController.skippedCount; colorValue: root.warningColor }
            MetricChip { label: "Failed"; value: tabularController.failureCount; colorValue: root.dangerColor }
            Item { Layout.fillWidth: true }
        }

        RowLayout {
            Layout.fillWidth: true
            spacing: 8
            Label {
                text: "Filter"
                color: root.mutedColor
                Layout.preferredWidth: 48
            }
            FilterButton { text: "All"; filterValue: "all"; countValue: tabularController.resultCount }
            FilterButton { text: "Ok"; filterValue: "ok"; countValue: tabularController.successCount }
            FilterButton { text: "Skipped"; filterValue: "skipped"; countValue: tabularController.skippedCount }
            FilterButton { text: "Failed"; filterValue: "failed"; countValue: tabularController.failureCount }
            Label {
                Layout.fillWidth: true
                text: tabularController.visibleResultCount + " visible"
                color: root.mutedColor
                horizontalAlignment: Text.AlignRight
            }
        }

        TabBar {
            id: tabs
            Layout.fillWidth: true
            background: Rectangle { color: "transparent" }
            BenchTabButton { text: "Results" }
            BenchTabButton { text: "Preview" }
        }

        StackLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            currentIndex: tabs.currentIndex

            Rectangle {
                color: root.panelColor
                border.color: root.borderColor
                radius: 8
                clip: true

                ColumnLayout {
                    anchors.fill: parent
                    spacing: 0

                    HorizontalHeaderView {
                        id: resultHeader
                        Layout.fillWidth: true
                        syncView: resultTable
                        clip: true
                        delegate: Rectangle {
                            implicitHeight: 34
                            color: "#e8edf2"
                            border.color: root.borderColor
                            Text {
                                anchors.fill: parent
                                anchors.margins: 8
                                text: display
                                color: root.textColor
                                font.bold: true
                                elide: Text.ElideRight
                                verticalAlignment: Text.AlignVCenter
                            }
                        }
                    }

                    Item {
                        Layout.fillWidth: true
                        Layout.fillHeight: true

                        TableView {
                            id: resultTable
                            anchors.fill: parent
                            clip: true
                            model: tabularController.resultsModel
                            reuseItems: true
                            columnSpacing: 1
                            rowSpacing: 1
                            rowHeightProvider: function(row) { return 32 }
                            columnWidthProvider: function(column) {
                                const widths = [120, 78, 92, 96, 110, 82, 92, 112, 360]
                                return widths[column] || 120
                            }

                            delegate: Rectangle {
                                implicitWidth: resultTable.columnWidthProvider(column)
                                implicitHeight: 32
                                color: row % 2 === 0 ? "#ffffff" : "#f5f7fa"
                                border.color: "#e1e6ec"
                                Text {
                                    id: resultText
                                    anchors.fill: parent
                                    anchors.margins: 7
                                    text: display
                                    color: column === 5 && display === "failed" ? root.dangerColor
                                        : column === 5 && display === "skipped" ? root.warningColor
                                        : column === 5 ? root.successColor
                                        : root.textColor
                                    font.bold: column === 5
                                    elide: Text.ElideRight
                                    verticalAlignment: Text.AlignVCenter
                                }
                            }
                        }

                        Label {
                            anchors.centerIn: parent
                            visible: tabularController.visibleResultCount === 0
                            text: tabularController.running ? "Running..." : (tabularController.resultCount === 0 ? "No results yet" : "No matching results")
                            color: root.mutedColor
                            font.pixelSize: 16
                        }
                    }
                }
            }

            Rectangle {
                color: root.panelColor
                border.color: root.borderColor
                radius: 8
                clip: true

                ColumnLayout {
                    anchors.fill: parent
                    spacing: 0

                    HorizontalHeaderView {
                        Layout.fillWidth: true
                        syncView: previewTable
                        clip: true
                        delegate: Rectangle {
                            implicitHeight: 34
                            color: "#e8edf2"
                            border.color: root.borderColor
                            Text {
                                anchors.fill: parent
                                anchors.margins: 8
                                text: display
                                color: root.textColor
                                font.bold: true
                                elide: Text.ElideRight
                                verticalAlignment: Text.AlignVCenter
                            }
                        }
                    }

                    Item {
                        Layout.fillWidth: true
                        Layout.fillHeight: true

                        TableView {
                            id: previewTable
                            anchors.fill: parent
                            clip: true
                            model: tabularController.previewModel
                            reuseItems: true
                            columnSpacing: 1
                            rowSpacing: 1
                            rowHeightProvider: function(row) { return 30 }
                            columnWidthProvider: function(column) { return 140 }

                            delegate: Rectangle {
                                implicitWidth: previewTable.columnWidthProvider(column)
                                implicitHeight: 30
                                color: row % 2 === 0 ? "#ffffff" : "#f5f7fa"
                                border.color: "#e1e6ec"
                                Text {
                                    id: previewText
                                    anchors.fill: parent
                                    anchors.margins: 7
                                    text: display
                                    color: root.textColor
                                    elide: Text.ElideRight
                                    verticalAlignment: Text.AlignVCenter
                                }
                            }
                        }

                        Label {
                            anchors.centerIn: parent
                            visible: tabularController.previewRowCount === 0
                            text: tabularController.running ? "Preview will load after the run" : "No preview loaded"
                            color: root.mutedColor
                            font.pixelSize: 16
                        }
                    }
                }
            }
        }

        Rectangle {
            Layout.fillWidth: true
            implicitHeight: 34
            color: "transparent"
            Label {
                anchors.fill: parent
                text: tabularController.reports
                elide: Text.ElideMiddle
                color: root.mutedColor
                verticalAlignment: Text.AlignVCenter
            }
        }
    }

    component MetricChip: Rectangle {
        property string label: ""
        property int value: 0
        property color colorValue: root.accentColor
        implicitWidth: 132
        implicitHeight: 42
        color: root.panelColor
        border.color: root.borderColor
        radius: 8

        RowLayout {
            anchors.fill: parent
            anchors.margins: 10
            spacing: 8
            Label {
                text: label
                color: root.mutedColor
                Layout.fillWidth: true
            }
            Label {
                text: value
                color: colorValue
                font.bold: true
                font.pixelSize: 16
            }
        }
    }

    component BenchPresetButton: Button {
        id: presetButton
        implicitHeight: 32
        implicitWidth: Math.max(118, presetText.implicitWidth + 22)
        contentItem: Text {
            id: presetText
            text: presetButton.text
            color: presetButton.hovered ? root.accentColor : root.textColor
            horizontalAlignment: Text.AlignHCenter
            verticalAlignment: Text.AlignVCenter
            font.pixelSize: 13
            font.bold: presetButton.hovered
        }
        background: Rectangle {
            color: presetButton.down ? "#d6e7f4" : "#edf3f8"
            border.color: presetButton.hovered ? root.accentColor : root.borderColor
            radius: 16
        }
    }

    component FilterButton: Button {
        id: filterButton
        property string filterValue: "all"
        property int countValue: 0
        checked: tabularController.resultFilter === filterValue
        implicitHeight: 32
        implicitWidth: Math.max(92, filterText.implicitWidth + 22)
        onClicked: tabularController.setResultFilter(filterValue)
        contentItem: Text {
            id: filterText
            text: filterButton.text + " " + filterButton.countValue
            color: filterButton.checked ? "#ffffff" : root.textColor
            horizontalAlignment: Text.AlignHCenter
            verticalAlignment: Text.AlignVCenter
            font.pixelSize: 13
            font.bold: filterButton.checked
        }
        background: Rectangle {
            color: filterButton.checked ? root.accentColor : root.panelColor
            border.color: filterButton.checked ? root.accentColor : root.borderColor
            radius: 16
        }
    }

    component BenchTextField: TextField {
        id: benchTextField
        selectByMouse: true
        color: root.textColor
        selectedTextColor: "#ffffff"
        selectionColor: root.accentColor
        font.pixelSize: 14
        verticalAlignment: TextInput.AlignVCenter
        background: Rectangle {
            color: "#ffffff"
            border.color: benchTextField.activeFocus ? root.accentColor : "#b7c2ce"
            border.width: benchTextField.activeFocus ? 2 : 1
            radius: 5
        }
    }

    component BenchTabButton: TabButton {
        id: benchTabButton
        implicitHeight: 42
        contentItem: Text {
            text: benchTabButton.text
            color: benchTabButton.checked ? "#ffffff" : root.textColor
            horizontalAlignment: Text.AlignHCenter
            verticalAlignment: Text.AlignVCenter
            font.bold: benchTabButton.checked
        }
        background: Rectangle {
            color: benchTabButton.checked ? root.accentColor : "#e5ebf1"
            border.color: root.borderColor
        }
    }
}
"""


def _preview_payload(data: Any) -> tuple[list[str], list[list[str]]]:
    if hasattr(data, "to_pandas"):
        data = data.to_pandas()
    if data.__class__.__module__.startswith("polars"):
        data = data.to_pandas()
    if hasattr(data, "columns") and hasattr(data, "itertuples"):
        columns = [str(column) for column in data.columns]
        rows = [
            ["" if value is None else str(value) for value in row]
            for row in data.itertuples(index=False, name=None)
        ]
        return columns, rows
    if hasattr(data, "shape"):
        columns = [str(index) for index in range(data.shape[1] if len(data.shape) > 1 else 1)]
        rows = [[str(value) for value in row] for row in data.tolist()]
        return columns, rows
    return [], []

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import QProcess, Qt, QTimer, QUrl
from PyQt6.QtGui import QColor, QDesktopServices, QFont, QTextCursor
from PyQt6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QStatusBar,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from devtools.work_packet_runner import (
    PACKET_FILE_RE,
    PacketDefinition,
    PacketRunnerError,
    PacketSet,
    discover_packet_set_dirs,
    load_packet_set,
)


def _preferred_project_python(repo_root: Path) -> str:
    preferred = repo_root / "venv" / "Scripts" / "python.exe"
    if preferred.exists():
        return str(preferred)
    return sys.executable


def _packet_title(packet: PacketDefinition) -> str:
    match = PACKET_FILE_RE.match(packet.spec_filename)
    if not match:
        return packet.spec_filename
    return match.group("slug").replace("_", " ").title()


def _powershell_stylesheet() -> str:
    return """
QMainWindow, QWidget {
    background: #012456;
    color: #f1f6ff;
    font-family: "Consolas";
    font-size: 12px;
}
QLabel {
    background: transparent;
    color: #f1f6ff;
}
QLineEdit, QListWidget, QTableWidget, QPlainTextEdit {
    background: #071a35;
    color: #d7f7c0;
    border: 1px solid #2f5d8f;
    selection-background-color: #124078;
    selection-color: #ffffff;
    gridline-color: #23476f;
}
QHeaderView::section {
    background: #0d315f;
    color: #d6e8ff;
    border: 1px solid #2f5d8f;
    padding: 4px 6px;
    font-weight: 600;
}
QPushButton {
    background: #0d315f;
    color: #f1f6ff;
    border: 1px solid #3e75ad;
    border-radius: 3px;
    padding: 5px 10px;
}
QPushButton:hover {
    background: #114280;
}
QPushButton:pressed {
    background: #0a284f;
}
QPushButton:disabled {
    background: #173055;
    color: #8aa4c6;
    border-color: #2a4567;
}
QStatusBar {
    background: #08284f;
    color: #d6e8ff;
    border-top: 1px solid #2f5d8f;
}
QTableWidget::item {
    padding: 3px;
}
QSplitter::handle {
    background: #0b2c55;
}
QSplitter::handle:hover {
    background: #124078;
}
"""


@dataclass
class PacketJob:
    job_id: int
    packet_set_slug: str
    packet_set_dir: Path
    packet_code: str
    packet_title: str
    branch_label: str
    ledger_status: str
    run_state: str = "Queued"
    start_time: datetime | None = None
    end_time: datetime | None = None
    exit_code: int | None = None
    artifact_dir: Path | None = None
    worktree_path: Path | None = None
    merge_workspace: Path | None = None
    output_lines: list[str] = field(default_factory=list)

    @property
    def thread_label(self) -> str:
        return f"T{self.job_id:02d}"

    def start_text(self) -> str:
        return self.start_time.strftime("%Y-%m-%d %H:%M:%S") if self.start_time else "-"

    def end_text(self) -> str:
        return self.end_time.strftime("%Y-%m-%d %H:%M:%S") if self.end_time else "-"

    def duration_text(self) -> str:
        if not self.start_time:
            return "-"
        end_time = self.end_time or datetime.now()
        total_seconds = int((end_time - self.start_time).total_seconds())
        hours, remainder = divmod(max(total_seconds, 0), 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

    def artifact_text(self) -> str:
        return str(self.artifact_dir) if self.artifact_dir else "-"

    def worktree_text(self) -> str:
        return str(self.worktree_path) if self.worktree_path else "-"

    def append_output(self, text: str) -> None:
        if not text:
            return
        self.output_lines.extend(text.splitlines(keepends=True))
        for line in text.splitlines():
            if line.startswith("[packet-thread] phase="):
                phase = line.split("phase=", 1)[1].split()[0].strip().lower()
                phase_map = {
                    "preparing": "Preparing",
                    "running": "Running",
                    "wrapping": "Wrapping",
                    "passed": "Passed",
                    "failed": "Failed",
                }
                self.run_state = phase_map.get(phase, self.run_state)
            if line.startswith("Worktree: "):
                worktree_text = line.split(":", 1)[1].strip()
                if worktree_text:
                    self.worktree_path = Path(worktree_text)
            if line.startswith("Merge workspace: "):
                workspace_text = line.split(":", 1)[1].strip()
                if workspace_text:
                    self.merge_workspace = Path(workspace_text)
            if line.startswith("Artifacts: "):
                artifact_text = line.split(":", 1)[1].strip()
                if artifact_text:
                    self.artifact_dir = Path(artifact_text)


class WorkPacketMonitorWindow(QMainWindow):
    def __init__(
        self,
        *,
        repo_root: Path | None = None,
        packet_root: Path | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.repo_root = (repo_root or Path(__file__).resolve().parents[1]).resolve()
        self.packet_root = (
            packet_root or self.repo_root / "docs" / "specs" / "work_packets"
        ).resolve()
        self.python_executable = _preferred_project_python(self.repo_root)
        self.thread_script = self.repo_root / "scripts" / "run_work_packet_thread.py"

        self.packet_sets: list[PacketSet] = []
        self.jobs: list[PacketJob] = []
        self._packet_set_by_path: dict[str, PacketSet] = {}
        self._processes_by_job_id: dict[int, QProcess] = {}
        self._job_counter = 1
        self._terminating_job_ids: set[int] = set()

        self.setWindowTitle("Work Packet Console")
        self.resize(1460, 900)
        self._build_ui()
        self._duration_timer = QTimer(self)
        self._duration_timer.setInterval(1000)
        self._duration_timer.timeout.connect(self._refresh_job_table)
        self._duration_timer.start()
        self._refresh_packet_sets()

    def _build_ui(self) -> None:
        central = QWidget(self)
        root = QVBoxLayout(central)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(10)

        controls = QHBoxLayout()
        controls.setSpacing(8)
        folder_label = QLabel("Packet Folder", central)
        self.folder_edit = QLineEdit(str(self.packet_root), central)
        self.browse_button = QPushButton("Browse...", central)
        self.refresh_button = QPushButton("Refresh", central)
        parallel_label = QLabel("Parallel", central)
        self.parallel_spin = QSpinBox(central)
        self.parallel_spin.setRange(1, 8)
        self.parallel_spin.setValue(2)
        controls.addWidget(folder_label)
        controls.addWidget(self.folder_edit, stretch=1)
        controls.addWidget(self.browse_button)
        controls.addWidget(self.refresh_button)
        controls.addWidget(parallel_label)
        controls.addWidget(self.parallel_spin)
        root.addLayout(controls)

        body_splitter = QSplitter(Qt.Orientation.Horizontal, central)
        body_splitter.setChildrenCollapsible(False)
        root.addWidget(body_splitter, stretch=1)

        selector_panel = QWidget(body_splitter)
        selector_layout = QVBoxLayout(selector_panel)
        selector_layout.setContentsMargins(0, 0, 0, 0)
        selector_layout.setSpacing(8)

        set_label = QLabel("Packet Sets", selector_panel)
        selector_layout.addWidget(set_label)
        self.packet_set_list = QListWidget(selector_panel)
        self.packet_set_list.setMinimumWidth(280)
        selector_layout.addWidget(self.packet_set_list, stretch=1)

        packet_label = QLabel("Packets In Selected Set", selector_panel)
        selector_layout.addWidget(packet_label)
        self.packet_table = QTableWidget(0, 6, selector_panel)
        self.packet_table.setHorizontalHeaderLabels(
            ["Run", "Packet", "Name", "Ledger", "Ready", "Branch"]
        )
        self.packet_table.verticalHeader().setVisible(False)
        self.packet_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.packet_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.packet_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.packet_table.horizontalHeader().setStretchLastSection(True)
        self.packet_table.setColumnWidth(0, 46)
        self.packet_table.setColumnWidth(1, 72)
        self.packet_table.setColumnWidth(2, 240)
        self.packet_table.setColumnWidth(3, 80)
        self.packet_table.setColumnWidth(4, 120)
        self.packet_table.setMinimumHeight(300)
        selector_layout.addWidget(self.packet_table, stretch=2)

        packet_actions = QHBoxLayout()
        packet_actions.setSpacing(8)
        self.select_pending_button = QPushButton("Select Pending", selector_panel)
        self.clear_selection_button = QPushButton("Clear Selection", selector_panel)
        self.queue_selected_button = QPushButton("Queue Selected", selector_panel)
        packet_actions.addWidget(self.select_pending_button)
        packet_actions.addWidget(self.clear_selection_button)
        packet_actions.addStretch(1)
        packet_actions.addWidget(self.queue_selected_button)
        selector_layout.addLayout(packet_actions)

        monitor_splitter = QSplitter(Qt.Orientation.Vertical, body_splitter)
        monitor_splitter.setChildrenCollapsible(False)

        jobs_panel = QWidget(monitor_splitter)
        jobs_layout = QVBoxLayout(jobs_panel)
        jobs_layout.setContentsMargins(0, 0, 0, 0)
        jobs_layout.setSpacing(8)

        jobs_label = QLabel("Thread Monitor", jobs_panel)
        jobs_layout.addWidget(jobs_label)
        self.jobs_table = QTableWidget(0, 9, jobs_panel)
        self.jobs_table.setHorizontalHeaderLabels(
            [
                "Thread",
                "Packet Set",
                "Packet",
                "State",
                "Start",
                "End",
                "Duration",
                "Branch",
                "Worktree",
            ]
        )
        self.jobs_table.verticalHeader().setVisible(False)
        self.jobs_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.jobs_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.jobs_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.jobs_table.horizontalHeader().setStretchLastSection(True)
        self.jobs_table.setColumnWidth(0, 64)
        self.jobs_table.setColumnWidth(1, 150)
        self.jobs_table.setColumnWidth(2, 180)
        self.jobs_table.setColumnWidth(3, 88)
        self.jobs_table.setColumnWidth(4, 152)
        self.jobs_table.setColumnWidth(5, 152)
        self.jobs_table.setColumnWidth(6, 90)
        self.jobs_table.setColumnWidth(7, 220)
        jobs_layout.addWidget(self.jobs_table, stretch=1)

        job_actions = QHBoxLayout()
        job_actions.setSpacing(8)
        self.stop_active_button = QPushButton("Stop Selected", jobs_panel)
        self.open_artifacts_button = QPushButton("Open Artifacts", jobs_panel)
        self.open_worktree_button = QPushButton("Open Worktree", jobs_panel)
        job_actions.addWidget(self.stop_active_button)
        job_actions.addWidget(self.open_worktree_button)
        job_actions.addWidget(self.open_artifacts_button)
        job_actions.addStretch(1)
        jobs_layout.addLayout(job_actions)

        log_panel = QWidget(monitor_splitter)
        log_layout = QVBoxLayout(log_panel)
        log_layout.setContentsMargins(0, 0, 0, 0)
        log_layout.setSpacing(8)

        log_label = QLabel("Live Output", log_panel)
        log_layout.addWidget(log_label)
        self.log_output = QPlainTextEdit(log_panel)
        self.log_output.setReadOnly(True)
        self.log_output.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        monospace = QFont("Consolas", 10)
        self.packet_set_list.setFont(monospace)
        self.packet_table.setFont(monospace)
        self.jobs_table.setFont(monospace)
        self.log_output.setFont(monospace)
        log_layout.addWidget(self.log_output, stretch=1)

        body_splitter.addWidget(selector_panel)
        body_splitter.addWidget(monitor_splitter)
        body_splitter.setSizes([560, 900])
        monitor_splitter.setSizes([430, 370])

        status_bar = QStatusBar(self)
        self.setStatusBar(status_bar)
        self._status_label = QLabel("Ready.", self)
        status_bar.addPermanentWidget(self._status_label, 1)

        self.setCentralWidget(central)

        self.browse_button.clicked.connect(self._browse_packet_folder)
        self.refresh_button.clicked.connect(self._refresh_packet_sets)
        self.packet_set_list.currentItemChanged.connect(self._on_packet_set_changed)
        self.select_pending_button.clicked.connect(self._select_pending_packets)
        self.clear_selection_button.clicked.connect(self._clear_packet_selection)
        self.queue_selected_button.clicked.connect(self._queue_selected_packets)
        self.jobs_table.itemSelectionChanged.connect(self._sync_log_viewer)
        self.stop_active_button.clicked.connect(self._stop_active_job)
        self.open_worktree_button.clicked.connect(self._open_selected_worktree)
        self.open_artifacts_button.clicked.connect(self._open_selected_artifacts)
        self.folder_edit.returnPressed.connect(self._refresh_packet_sets)
        self.parallel_spin.valueChanged.connect(lambda _value: self._start_pending_jobs())

    def _browse_packet_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self,
            "Select Work Packet Folder",
            str(self._selected_packet_folder()),
        )
        if not folder:
            return
        self.folder_edit.setText(folder)
        self._refresh_packet_sets()

    def _selected_packet_folder(self) -> Path:
        return Path(self.folder_edit.text()).expanduser()

    def _refresh_packet_sets(self) -> None:
        folder = self._selected_packet_folder()
        try:
            packet_dirs = discover_packet_set_dirs(folder)
            packet_sets = [load_packet_set(path) for path in packet_dirs]
        except (PacketRunnerError, FileNotFoundError) as exc:
            self.packet_sets = []
            self._packet_set_by_path = {}
            self.packet_set_list.clear()
            self.packet_table.setRowCount(0)
            self._status_label.setText(str(exc))
            return

        current_path = self._current_packet_set_path()
        self.packet_sets = packet_sets
        self._packet_set_by_path = {str(packet_set.directory): packet_set for packet_set in packet_sets}
        self.packet_set_list.blockSignals(True)
        self.packet_set_list.clear()
        selected_row = 0
        for row, packet_set in enumerate(packet_sets):
            item = QListWidgetItem(packet_set.slug)
            item.setData(Qt.ItemDataRole.UserRole, str(packet_set.directory))
            self.packet_set_list.addItem(item)
            if current_path and current_path == str(packet_set.directory):
                selected_row = row
        self.packet_set_list.blockSignals(False)
        if packet_sets:
            self.packet_set_list.setCurrentRow(selected_row)
            self._status_label.setText(
                f"Loaded {len(packet_sets)} packet set(s) from {folder.resolve()}."
            )
        else:
            self.packet_table.setRowCount(0)
            self._status_label.setText(f"No packet sets found in {folder.resolve()}.")
        self._refresh_job_table()

    def _current_packet_set_path(self) -> str | None:
        item = self.packet_set_list.currentItem()
        if item is None:
            return None
        return item.data(Qt.ItemDataRole.UserRole)

    def _on_packet_set_changed(
        self,
        current: QListWidgetItem | None,
        _previous: QListWidgetItem | None,
    ) -> None:
        if current is None:
            self.packet_table.setRowCount(0)
            return
        packet_set = self._packet_set_by_path.get(current.data(Qt.ItemDataRole.UserRole))
        if packet_set is None:
            self.packet_table.setRowCount(0)
            return
        self._populate_packet_table(packet_set)

    def _packet_readiness_map(self, packet_set: PacketSet) -> dict[str, str]:
        readiness: dict[str, str] = {}
        blocker: str | None = None
        for packet in packet_set.packets:
            if packet.status == "PASS":
                readiness[packet.code] = "Done"
                continue
            if blocker is None:
                readiness[packet.code] = "Ready"
                blocker = packet.code
            else:
                readiness[packet.code] = f"Blocked by {blocker}"
        return readiness

    def _populate_packet_table(self, packet_set: PacketSet) -> None:
        readiness = self._packet_readiness_map(packet_set)
        self.packet_table.blockSignals(True)
        self.packet_table.setRowCount(len(packet_set.packets))
        for row, packet in enumerate(packet_set.packets):
            check_item = QTableWidgetItem()
            check_item.setFlags(
                Qt.ItemFlag.ItemIsEnabled
                | Qt.ItemFlag.ItemIsUserCheckable
                | Qt.ItemFlag.ItemIsSelectable
            )
            check_item.setCheckState(Qt.CheckState.Unchecked)
            check_item.setData(Qt.ItemDataRole.UserRole, packet.code)
            self.packet_table.setItem(row, 0, check_item)

            code_item = QTableWidgetItem(packet.code)
            name_item = QTableWidgetItem(_packet_title(packet))
            ledger_item = QTableWidgetItem(packet.status)
            ready_item = QTableWidgetItem(readiness.get(packet.code, "-"))
            branch_item = QTableWidgetItem(packet.branch_label)
            for col, item in enumerate(
                (code_item, name_item, ledger_item, ready_item, branch_item),
                start=1,
            ):
                item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
                self.packet_table.setItem(row, col, item)

            if packet.status == "PASS":
                ledger_item.setForeground(QColor("#5bd37b"))
            elif readiness.get(packet.code) == "Ready":
                ready_item.setForeground(QColor("#7fd6ff"))
            else:
                ready_item.setForeground(QColor("#ffcf66"))
        self.packet_table.blockSignals(False)
        self.packet_table.resizeRowsToContents()

    def _selected_packets(self) -> list[PacketDefinition]:
        current_path = self._current_packet_set_path()
        if current_path is None:
            return []
        packet_set = self._packet_set_by_path[current_path]
        selected_codes: set[str] = set()
        for row in range(self.packet_table.rowCount()):
            item = self.packet_table.item(row, 0)
            if item is None:
                continue
            if item.checkState() == Qt.CheckState.Checked:
                selected_codes.add(str(item.data(Qt.ItemDataRole.UserRole)))
        return [packet for packet in packet_set.packets if packet.code in selected_codes]

    def _select_pending_packets(self) -> None:
        current_path = self._current_packet_set_path()
        if current_path is None:
            return
        packet_set = self._packet_set_by_path[current_path]
        readiness = self._packet_readiness_map(packet_set)
        for row in range(self.packet_table.rowCount()):
            code_item = self.packet_table.item(row, 1)
            if code_item is None:
                continue
            check_item = self.packet_table.item(row, 0)
            if check_item is None:
                continue
            code = code_item.text()
            check_item.setCheckState(
                Qt.CheckState.Checked if readiness.get(code) == "Ready" else Qt.CheckState.Unchecked
            )

    def _clear_packet_selection(self) -> None:
        for row in range(self.packet_table.rowCount()):
            item = self.packet_table.item(row, 0)
            if item is not None:
                item.setCheckState(Qt.CheckState.Unchecked)

    def _queue_selected_packets(self) -> None:
        current_path = self._current_packet_set_path()
        if current_path is None:
            return
        packet_set = self._packet_set_by_path[current_path]
        packets = self._selected_packets()
        if not packets:
            self._status_label.setText("No packets selected.")
            return

        readiness = self._packet_readiness_map(packet_set)
        queued = 0
        skipped = 0
        existing_keys = {
            (str(job.packet_set_dir), job.packet_code)
            for job in self.jobs
            if job.run_state in {"Queued", "Preparing", "Running", "Wrapping"}
        }
        for packet in packets:
            key = (str(packet_set.directory), packet.code)
            if key in existing_keys or readiness.get(packet.code) != "Ready":
                skipped += 1
                continue
            job = PacketJob(
                job_id=self._job_counter,
                packet_set_slug=packet_set.slug,
                packet_set_dir=packet_set.directory,
                packet_code=packet.code,
                packet_title=_packet_title(packet),
                branch_label=packet.branch_label,
                ledger_status=packet.status,
            )
            self._job_counter += 1
            self.jobs.append(job)
            queued += 1
        self._refresh_job_table()
        self._sync_log_viewer()
        if queued:
            if skipped:
                self._status_label.setText(
                    f"Queued {queued} packet thread(s); skipped {skipped} blocked/already-active packet(s)."
                )
            else:
                self._status_label.setText(f"Queued {queued} packet thread(s).")
            self._start_pending_jobs()
        else:
            self._status_label.setText("No selected packets were ready to queue.")

    def _job_state_color(self, state: str) -> QColor:
        colors = {
            "Queued": QColor("#ffcf66"),
            "Preparing": QColor("#ffd67c"),
            "Running": QColor("#7fd6ff"),
            "Wrapping": QColor("#8ce2ff"),
            "Passed": QColor("#5bd37b"),
            "Failed": QColor("#ff7a7a"),
            "Cancelled": QColor("#d7a7ff"),
        }
        return colors.get(state, QColor("#f1f6ff"))

    def _refresh_job_table(self) -> None:
        current_job_id = self._selected_job_id()
        self.jobs_table.setRowCount(len(self.jobs))
        for row, job in enumerate(self.jobs):
            values = [
                job.thread_label,
                job.packet_set_slug,
                f"{job.packet_code} {job.packet_title}",
                job.run_state,
                job.start_text(),
                job.end_text(),
                job.duration_text(),
                job.branch_label,
                job.worktree_text(),
            ]
            for col, value in enumerate(values):
                item = self.jobs_table.item(row, col)
                if item is None:
                    item = QTableWidgetItem()
                    item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
                    item.setData(Qt.ItemDataRole.UserRole, job.job_id if col == 0 else None)
                    self.jobs_table.setItem(row, col, item)
                item.setText(value)
                if col == 3:
                    item.setForeground(self._job_state_color(job.run_state))
            if current_job_id is not None and current_job_id == job.job_id:
                self.jobs_table.setCurrentCell(row, 0)
        self.open_artifacts_button.setEnabled(self._selected_job_with_artifacts() is not None)
        self.open_worktree_button.setEnabled(self._selected_job_with_worktree() is not None)
        self.stop_active_button.setEnabled(self._selected_running_job() is not None)
        self.jobs_table.resizeRowsToContents()

    def _selected_job_id(self) -> int | None:
        row = self.jobs_table.currentRow()
        if row < 0:
            return None
        item = self.jobs_table.item(row, 0)
        if item is None:
            return None
        return item.data(Qt.ItemDataRole.UserRole)

    def _selected_job(self) -> PacketJob | None:
        job_id = self._selected_job_id()
        if job_id is None:
            return None
        for job in self.jobs:
            if job.job_id == job_id:
                return job
        return None

    def _selected_job_with_artifacts(self) -> PacketJob | None:
        job = self._selected_job()
        if job is None or job.artifact_dir is None:
            return None
        return job

    def _selected_job_with_worktree(self) -> PacketJob | None:
        job = self._selected_job()
        if job is None or job.worktree_path is None:
            return None
        return job

    def _selected_running_job(self) -> PacketJob | None:
        job = self._selected_job()
        if job is None:
            return None
        if job.job_id not in self._processes_by_job_id:
            return None
        return job

    def _sync_log_viewer(self) -> None:
        job = self._selected_job()
        if job is None:
            self.log_output.clear()
            self.open_artifacts_button.setEnabled(False)
            self.open_worktree_button.setEnabled(False)
            self.stop_active_button.setEnabled(False)
            return
        self.log_output.setPlainText("".join(job.output_lines))
        self.log_output.verticalScrollBar().setValue(self.log_output.verticalScrollBar().maximum())
        self.open_artifacts_button.setEnabled(job.artifact_dir is not None)
        self.open_worktree_button.setEnabled(job.worktree_path is not None)
        self.stop_active_button.setEnabled(job.job_id in self._processes_by_job_id)

    def _next_queued_job(self) -> PacketJob | None:
        for job in self.jobs:
            if job.run_state == "Queued":
                return job
        return None

    def _active_job_count(self) -> int:
        return len(self._processes_by_job_id)

    def _start_job(self, next_job: PacketJob) -> None:
        process = QProcess(self)
        process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        process.readyReadStandardOutput.connect(
            lambda job_id=next_job.job_id: self._handle_process_output(job_id)
        )
        process.finished.connect(
            lambda exit_code, exit_status, job_id=next_job.job_id: self._handle_process_finished(
                job_id, exit_code, exit_status
            )
        )
        self._processes_by_job_id[next_job.job_id] = process
        next_job.run_state = "Preparing"
        next_job.start_time = datetime.now()
        self._refresh_job_table()
        self._status_label.setText(
            f"Launching {next_job.packet_set_slug} {next_job.packet_code} on {next_job.thread_label}."
        )

        arguments = [
            str(self.thread_script),
            str(next_job.packet_set_dir),
            "--packet",
            next_job.packet_code,
            "--root",
            str(self.repo_root),
        ]
        process.start(self.python_executable, arguments)
        if not process.waitForStarted(5000):
            next_job.run_state = "Failed"
            next_job.end_time = datetime.now()
            next_job.exit_code = -1
            next_job.append_output("Failed to start packet thread process.\n")
            self._processes_by_job_id.pop(next_job.job_id, None)
            self._refresh_job_table()
            self._sync_log_viewer()
            self._status_label.setText(
                f"Failed to start {next_job.packet_set_slug} {next_job.packet_code} on {next_job.thread_label}."
            )
            self._start_pending_jobs()

    def _start_pending_jobs(self) -> None:
        while self._active_job_count() < self.parallel_spin.value():
            next_job = self._next_queued_job()
            if next_job is None:
                return
            self._start_job(next_job)

    def _handle_process_output(self, job_id: int) -> None:
        process = self._processes_by_job_id.get(job_id)
        job = self._job_by_id(job_id)
        if process is None or job is None:
            return
        payload = bytes(process.readAllStandardOutput()).decode("utf-8", errors="replace")
        job.append_output(payload)
        if self._selected_job_id() == job.job_id:
            self.log_output.moveCursor(QTextCursor.MoveOperation.End)
            self.log_output.insertPlainText(payload)
            self.log_output.verticalScrollBar().setValue(self.log_output.verticalScrollBar().maximum())
        self._refresh_job_table()

    def _handle_process_finished(
        self,
        job_id: int,
        exit_code: int,
        _exit_status: QProcess.ExitStatus,
    ) -> None:
        job = self._job_by_id(job_id)
        if job is None:
            return
        self._handle_process_output(job_id)
        job.end_time = datetime.now()
        job.exit_code = exit_code
        if job.job_id in self._terminating_job_ids:
            job.run_state = "Cancelled"
        else:
            job.run_state = "Passed" if exit_code == 0 else "Failed"
        self._processes_by_job_id.pop(job_id, None)
        self._terminating_job_ids.discard(job_id)
        self._refresh_packet_sets()
        self._refresh_job_table()
        self._sync_log_viewer()
        self._status_label.setText(
            f"{job.thread_label} finished {job.packet_set_slug} {job.packet_code} with state {job.run_state}."
        )
        self._start_pending_jobs()

    def _job_by_id(self, job_id: int) -> PacketJob | None:
        for job in self.jobs:
            if job.job_id == job_id:
                return job
        return None

    def _stop_active_job(self) -> None:
        job = self._selected_running_job()
        if job is None:
            return
        process = self._processes_by_job_id.get(job.job_id)
        if process is None:
            return
        self._terminating_job_ids.add(job.job_id)
        self._status_label.setText(
            f"Stopping {job.thread_label} ({job.packet_set_slug} {job.packet_code})..."
        )
        process.terminate()
        QTimer.singleShot(3000, lambda job_id=job.job_id: self._kill_active_if_needed(job_id))

    def _kill_active_if_needed(self, job_id: int) -> None:
        process = self._processes_by_job_id.get(job_id)
        if process is None:
            return
        if process.state() != QProcess.ProcessState.NotRunning:
            process.kill()

    def _open_selected_artifacts(self) -> None:
        job = self._selected_job_with_artifacts()
        if job is None:
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(job.artifact_dir)))

    def _open_selected_worktree(self) -> None:
        job = self._selected_job_with_worktree()
        if job is None:
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(job.worktree_path)))

    def closeEvent(self, event) -> None:  # type: ignore[override]
        if self._processes_by_job_id:
            response = QMessageBox.question(
                self,
                "Stop Running Packet Threads?",
                "One or more packet threads are still running. Stop them and close the monitor?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if response != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
            for job_id, process in list(self._processes_by_job_id.items()):
                self._terminating_job_ids.add(job_id)
                process.terminate()
            for process in list(self._processes_by_job_id.values()):
                process.waitForFinished(5000)
        super().closeEvent(event)


def run(argv: list[str] | None = None) -> int:
    app = QApplication.instance() or QApplication(argv or sys.argv)
    app.setApplicationName("Work Packet Console")
    app.setStyleSheet(_powershell_stylesheet())
    window = WorkPacketMonitorWindow()
    window.show()
    return app.exec()


__all__ = ["WorkPacketMonitorWindow", "run"]

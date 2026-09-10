from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ea_node_editor.graph.file_issue_state import encode_file_repair_request


@dataclass(frozen=True, slots=True)
class ProjectFilesManagedEntry:
    artifact_id: str
    relative_path: str
    absolute_path: str
    exists: bool

    @property
    def status_label(self) -> str:
        return "Available" if self.exists else "Missing"


@dataclass(frozen=True, slots=True)
class ProjectFilesStagedEntry:
    artifact_id: str
    relative_path: str
    absolute_path: str
    slot: str
    exists: bool

    @property
    def status_label(self) -> str:
        return "Ready" if self.exists else "Missing"


@dataclass(frozen=True, slots=True)
class ProjectFilesBrokenEntry:
    workspace_id: str
    workspace_name: str
    node_id: str
    node_title: str
    property_key: str
    property_label: str
    current_value: str
    issue_kind: str
    source_kind: str
    source_mode: str
    message: str

    @property
    def repair_request(self) -> str:
        return encode_file_repair_request(self.current_value)

    @property
    def location_label(self) -> str:
        workspace = self.workspace_name or self.workspace_id
        node = self.node_title or self.node_id
        if workspace and node:
            return f"{workspace} / {node}"
        return workspace or node


@dataclass(frozen=True, slots=True)
class ProjectFilesSnapshot:
    project_path: str
    data_root_path: str
    staging_root_path: str
    managed_entries: tuple[ProjectFilesManagedEntry, ...]
    staged_entries: tuple[ProjectFilesStagedEntry, ...]
    broken_entries: tuple[ProjectFilesBrokenEntry, ...]

    @property
    def managed_count(self) -> int:
        return len(self.managed_entries)

    @property
    def staged_count(self) -> int:
        return len(self.staged_entries)

    @property
    def broken_count(self) -> int:
        return len(self.broken_entries)

    @property
    def has_prompt_context(self) -> bool:
        return bool(self.staged_entries or self.broken_entries)

    @property
    def project_label(self) -> str:
        return self.project_path or "Unsaved project"

    @property
    def summary_text(self) -> str:
        fragments = [
            self._count_text(self.managed_count, "saved file"),
            self._count_text(self.staged_count, "temporary file"),
            self._count_text(self.broken_count, "broken file entry"),
        ]
        return ", ".join(fragments)

    @staticmethod
    def _count_text(count: int, noun: str) -> str:
        suffix = "" if count == 1 else "s"
        return f"{count} {noun}{suffix}"


class ProjectFilesDialog(QDialog):
    def __init__(
        self,
        *,
        snapshot: ProjectFilesSnapshot,
        repair_callback: Callable[[ProjectFilesBrokenEntry], bool] | None = None,
        refresh_snapshot_callback: Callable[[], ProjectFilesSnapshot] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Project Files")
        self.setModal(True)
        self.resize(860, 680)

        self._snapshot = snapshot
        self._repair_callback = repair_callback
        self._refresh_snapshot_callback = refresh_snapshot_callback

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        self.project_label = QLabel(self)
        self.project_label.setObjectName("projectFilesDialogProjectLabel")
        self.project_label.setWordWrap(True)
        layout.addWidget(self.project_label)

        self.location_label = QLabel(self)
        self.location_label.setObjectName("projectFilesDialogLocationLabel")
        self.location_label.setWordWrap(True)
        layout.addWidget(self.location_label)

        self.summary_label = QLabel(self)
        self.summary_label.setObjectName("projectFilesDialogSummaryLabel")
        self.summary_label.setWordWrap(True)
        layout.addWidget(self.summary_label)

        self.managed_summary_label = QLabel(self)
        self.managed_summary_label.setObjectName("projectFilesDialogManagedSummaryLabel")
        layout.addWidget(self.managed_summary_label)

        self.managed_tree = self._build_tree(
            object_name="projectFilesDialogManagedTree",
            headers=("Artifact", "Relative Path", "Status"),
        )
        layout.addWidget(self.managed_tree)

        self.staged_summary_label = QLabel(self)
        self.staged_summary_label.setObjectName("projectFilesDialogStagedSummaryLabel")
        layout.addWidget(self.staged_summary_label)

        self.staged_tree = self._build_tree(
            object_name="projectFilesDialogStagedTree",
            headers=("Artifact", "Relative Path", "Status"),
        )
        layout.addWidget(self.staged_tree)

        self.broken_summary_label = QLabel(self)
        self.broken_summary_label.setObjectName("projectFilesDialogBrokenSummaryLabel")
        layout.addWidget(self.broken_summary_label)

        self.broken_tree = self._build_tree(
            object_name="projectFilesDialogBrokenTree",
            headers=("Location", "Property", "Issue"),
        )
        self.broken_tree.itemSelectionChanged.connect(self._sync_repair_button)
        layout.addWidget(self.broken_tree)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, parent=self)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        self.repair_button = QPushButton("Repair file...", self)
        self.repair_button.setObjectName("projectFilesDialogRepairButton")
        self.repair_button.clicked.connect(self._repair_selected_broken_entry)
        buttons.addButton(self.repair_button, QDialogButtonBox.ButtonRole.ActionRole)
        layout.addWidget(buttons)

        self._apply_snapshot(snapshot)

    @staticmethod
    def _build_tree(*, object_name: str, headers: Iterable[str]) -> QTreeWidget:
        tree = QTreeWidget()
        tree.setObjectName(object_name)
        tree.setColumnCount(len(tuple(headers)))
        tree.setHeaderLabels(list(headers))
        tree.setRootIsDecorated(False)
        tree.setUniformRowHeights(True)
        tree.setAlternatingRowColors(True)
        tree.setSelectionBehavior(QTreeWidget.SelectionBehavior.SelectRows)
        tree.setSelectionMode(QTreeWidget.SelectionMode.SingleSelection)
        tree.setMinimumHeight(132)
        return tree

    def _apply_snapshot(self, snapshot: ProjectFilesSnapshot) -> None:
        self._snapshot = snapshot
        self.project_label.setText(f"Project: {snapshot.project_label}")
        location_lines = [
            f"Project files folder: {snapshot.data_root_path or 'Not available until the project is saved.'}",
        ]
        if snapshot.staging_root_path:
            location_lines.append(f"Node files root: {snapshot.staging_root_path}")
        self.location_label.setText("\n".join(location_lines))
        self.summary_label.setText(snapshot.summary_text)

        self.managed_summary_label.setText(
            f"Saved files ({snapshot.managed_count})"
        )
        self._populate_tree(
            self.managed_tree,
            entries=snapshot.managed_entries,
            placeholder=("No managed project files are currently recorded.", "", ""),
            item_builder=lambda entry: (entry.artifact_id, entry.relative_path, entry.status_label),
        )

        self.staged_summary_label.setText(
            f"Temporary files ({snapshot.staged_count})"
        )
        self._populate_tree(
            self.staged_tree,
            entries=snapshot.staged_entries,
            placeholder=("No staged scratch items are currently recorded.", "", ""),
            item_builder=lambda entry: (
                entry.artifact_id,
                entry.relative_path or entry.absolute_path or entry.slot,
                entry.status_label,
            ),
        )

        self.broken_summary_label.setText(
            f"Broken file entries ({snapshot.broken_count})"
        )
        self._populate_tree(
            self.broken_tree,
            entries=snapshot.broken_entries,
            placeholder=("No broken file entries are currently recorded.", "", ""),
            item_builder=lambda entry: (entry.location_label, entry.property_label, entry.message),
            store_entry=True,
        )
        if snapshot.broken_entries:
            self.broken_tree.setCurrentItem(self.broken_tree.topLevelItem(0))
        self._sync_repair_button()

    def _populate_tree(
        self,
        tree: QTreeWidget,
        *,
        entries: Iterable[object],
        placeholder: tuple[str, str, str],
        item_builder: Callable[[object], tuple[str, str, str]],
        store_entry: bool = False,
    ) -> None:
        tree.clear()
        rendered = False
        for entry in entries:
            item = QTreeWidgetItem(list(item_builder(entry)))
            if store_entry:
                item.setData(0, Qt.ItemDataRole.UserRole, entry)
            tree.addTopLevelItem(item)
            rendered = True
        if rendered:
            tree.resizeColumnToContents(0)
            tree.resizeColumnToContents(1)
            return
        placeholder_item = QTreeWidgetItem(list(placeholder))
        placeholder_item.setFlags(placeholder_item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
        tree.addTopLevelItem(placeholder_item)
        tree.resizeColumnToContents(0)

    def _selected_broken_entry(self) -> ProjectFilesBrokenEntry | None:
        item = self.broken_tree.currentItem()
        if item is None:
            return None
        entry = item.data(0, Qt.ItemDataRole.UserRole)
        return entry if isinstance(entry, ProjectFilesBrokenEntry) else None

    def _sync_repair_button(self) -> None:
        entry = self._selected_broken_entry()
        self.repair_button.setEnabled(self._repair_callback is not None and entry is not None)

    def _repair_selected_broken_entry(self) -> None:
        entry = self._selected_broken_entry()
        if entry is None or self._repair_callback is None:
            return
        if not self._repair_callback(entry):
            return
        if self._refresh_snapshot_callback is None:
            return
        self._apply_snapshot(self._refresh_snapshot_callback())

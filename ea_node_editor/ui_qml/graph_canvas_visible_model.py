from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator, Mapping
from typing import Any

from PyQt6.QtCore import QAbstractListModel, QByteArray, QModelIndex, QObject, Qt, pyqtProperty, pyqtSignal

_MODEL_DATA_ROLE = int(Qt.ItemDataRole.UserRole.value) + 1
_NODE_ID_ROLE = _MODEL_DATA_ROLE + 1
_MODEL_ROLES = [_MODEL_DATA_ROLE, _NODE_ID_ROLE]


def _payload_node_id(payload: Any) -> str:
    if not isinstance(payload, Mapping):
        return ""
    return str(payload.get("node_id", "") or "").strip()


def _can_diff_by_node_id(node_ids: list[str]) -> bool:
    return all(node_ids) and len(set(node_ids)) == len(node_ids)


def _dedupe_rows_by_node_id(rows: list[Any]) -> tuple[list[Any], list[str]]:
    """Drop payloads whose non-empty node_id already appeared earlier.

    Duplicate ids in a visible-model feed are always upstream corruption
    (one graph node must never render twice); keep the first occurrence so
    the model stays sane and report the ids so the owner can resync.
    Payloads without a node_id are passed through untouched.
    """
    seen: set[str] = set()
    deduped: list[Any] = []
    duplicate_ids: list[str] = []
    for payload in rows:
        node_id = _payload_node_id(payload)
        if node_id and node_id in seen:
            if node_id not in duplicate_ids:
                duplicate_ids.append(node_id)
            continue
        if node_id:
            seen.add(node_id)
        deduped.append(payload)
    return deduped, duplicate_ids


class GraphCanvasVisibleModel(QAbstractListModel):
    count_changed = pyqtSignal()
    duplicate_node_ids_detected = pyqtSignal(list)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._rows: list[Any] = []
        self._duplicate_sync_count = 0
        self._last_duplicate_node_ids: tuple[str, ...] = ()
        self._sync_in_progress = False
        self._active_publication_rows: list[Any] | None = None
        self._pending_sync_rows: list[Any] | None = None
        self._pending_duplicate_node_ids: tuple[str, ...] = ()

    @property
    def duplicate_payload_sync_count(self) -> int:
        return self._duplicate_sync_count

    @property
    def last_duplicate_node_ids(self) -> tuple[str, ...]:
        return self._last_duplicate_node_ids

    @pyqtProperty(int, notify=count_changed)
    def count(self) -> int:
        return len(self._rows)

    @pyqtProperty(int, notify=count_changed)
    def length(self) -> int:
        return len(self._rows)

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self._rows)

    def data(self, index: QModelIndex, role: int = _MODEL_DATA_ROLE) -> Any:
        if not index.isValid() or not (0 <= index.row() < len(self._rows)):
            return None
        payload = self._rows[index.row()]
        if role == _MODEL_DATA_ROLE:
            return payload
        if role == _NODE_ID_ROLE:
            return _payload_node_id(payload)
        return None

    def roleNames(self) -> dict[int, QByteArray]:  # noqa: N802
        return {
            _MODEL_DATA_ROLE: QByteArray(b"modelData"),
            _NODE_ID_ROLE: QByteArray(b"node_id"),
        }

    def __len__(self) -> int:
        return len(self._rows)

    def __iter__(self) -> Iterator[Any]:
        return iter(self.payloads())

    def __getitem__(self, index: int) -> Any:
        return self._rows[index]

    def payloads(self) -> list[Any]:
        return list(self._rows)

    def sync_payloads(self, payloads: Iterable[Any]) -> None:
        next_rows, duplicate_ids = _dedupe_rows_by_node_id(list(payloads))
        if duplicate_ids:
            self._duplicate_sync_count += 1
            self._last_duplicate_node_ids = tuple(duplicate_ids)
        if self._sync_in_progress:
            self._queue_sync(next_rows, duplicate_ids)
            return

        self._run_publication(
            lambda: self._sync_payload_rows(next_rows),
            target_rows=next_rows,
            duplicate_ids=tuple(duplicate_ids),
        )

    def replace_existing_payloads(self, payloads: Iterable[Any]) -> int | None:
        replacements: dict[str, Any] = {}
        for payload in payloads:
            node_id = _payload_node_id(payload)
            if not node_id or node_id in replacements:
                return None
            replacements[node_id] = payload
        if not replacements:
            return 0

        source_rows = self._rows
        if self._sync_in_progress:
            if self._pending_sync_rows is not None:
                source_rows = self._pending_sync_rows
            elif self._active_publication_rows is not None:
                source_rows = self._active_publication_rows
        next_rows = list(source_rows)
        missing_ids = set(replacements)
        changed_rows: list[int] = []
        for row, current_payload in enumerate(source_rows):
            node_id = _payload_node_id(current_payload)
            replacement = replacements.get(node_id)
            if replacement is None:
                continue
            missing_ids.discard(node_id)
            if current_payload == replacement:
                continue
            next_rows[row] = replacement
            changed_rows.append(row)
        if missing_ids:
            return None
        if not changed_rows:
            return 0
        if self._sync_in_progress:
            self._queue_sync(next_rows, ())
            return len(changed_rows)

        self._run_publication(
            lambda: self._replace_prepared_rows(next_rows, changed_rows),
            target_rows=next_rows,
            duplicate_ids=(),
        )
        return len(changed_rows)

    def append_new_payloads(self, payloads: Iterable[Any]) -> int | None:
        additions, duplicate_ids = _dedupe_rows_by_node_id(list(payloads))
        if duplicate_ids:
            self._duplicate_sync_count += 1
            self._last_duplicate_node_ids = tuple(duplicate_ids)
        if not additions:
            return 0

        addition_ids = [_payload_node_id(payload) for payload in additions]
        if not _can_diff_by_node_id(addition_ids):
            return None
        source_rows = self._rows
        if self._sync_in_progress:
            if self._pending_sync_rows is not None:
                source_rows = self._pending_sync_rows
            elif self._active_publication_rows is not None:
                source_rows = self._active_publication_rows
        source_ids = [_payload_node_id(payload) for payload in source_rows]
        if not _can_diff_by_node_id(source_ids) or set(addition_ids).intersection(source_ids):
            return None

        next_rows = [*source_rows, *additions]
        if self._sync_in_progress:
            self._queue_sync(next_rows, duplicate_ids)
            return len(additions)
        self._run_publication(
            lambda: self._append_prepared_rows(additions),
            target_rows=next_rows,
            duplicate_ids=tuple(duplicate_ids),
        )
        return len(additions)

    def _queue_sync(self, rows: list[Any], duplicate_ids: Iterable[str]) -> None:
        self._pending_sync_rows = rows
        duplicate_ids_tuple = tuple(duplicate_ids)
        if duplicate_ids_tuple:
            self._pending_duplicate_node_ids = duplicate_ids_tuple

    def _run_publication(
        self,
        publication: Callable[[], None],
        *,
        target_rows: list[Any],
        duplicate_ids: tuple[str, ...],
    ) -> None:
        duplicate_ids_to_emit = duplicate_ids
        while True:
            self._sync_in_progress = True
            self._active_publication_rows = target_rows
            try:
                publication()
            finally:
                self._active_publication_rows = None
                self._sync_in_progress = False
            # Emit after the row transactions complete so handlers never run
            # inside a model update window.
            if duplicate_ids_to_emit:
                self.duplicate_node_ids_detected.emit(list(duplicate_ids_to_emit))
            if self._pending_sync_rows is None:
                break
            target_rows = self._pending_sync_rows
            duplicate_ids_to_emit = self._pending_duplicate_node_ids
            self._pending_sync_rows = None
            self._pending_duplicate_node_ids = ()
            publication = lambda rows=target_rows: self._sync_payload_rows(rows)

    def _replace_prepared_rows(self, payloads: list[Any], changed_rows: list[int]) -> None:
        range_start = changed_rows[0]
        range_end = range_start
        for row in (*changed_rows[1:], None):
            if row is not None and row == range_end + 1:
                range_end = row
                continue
            self._rows[range_start : range_end + 1] = payloads[range_start : range_end + 1]
            self.dataChanged.emit(
                self.index(range_start, 0),
                self.index(range_end, 0),
                _MODEL_ROLES,
            )
            if row is None:
                break
            range_start = range_end = row

    def _append_prepared_rows(self, payloads: list[Any]) -> None:
        if not payloads:
            return
        start_row = len(self._rows)
        self.beginInsertRows(QModelIndex(), start_row, start_row + len(payloads) - 1)
        self._rows.extend(payloads)
        self.endInsertRows()
        self.count_changed.emit()

    def _sync_payload_rows(self, next_rows: list[Any]) -> None:
        if not self._rows and not next_rows:
            return
        if not self._rows:
            next_node_ids = [_payload_node_id(payload) for payload in next_rows]
            if not _can_diff_by_node_id(next_node_ids):
                self._reset_payloads(next_rows)
                return
            self.beginInsertRows(QModelIndex(), 0, len(next_rows) - 1)
            self._rows = next_rows
            self.endInsertRows()
            self.count_changed.emit()
            return
        if not next_rows:
            self.beginRemoveRows(QModelIndex(), 0, len(self._rows) - 1)
            self._rows = []
            self.endRemoveRows()
            self.count_changed.emit()
            return
        old_node_ids = [_payload_node_id(payload) for payload in self._rows]
        next_node_ids = [_payload_node_id(payload) for payload in next_rows]
        if not _can_diff_by_node_id(old_node_ids) or not _can_diff_by_node_id(next_node_ids):
            self._reset_payloads(next_rows)
            return
        if old_node_ids == next_node_ids:
            self._replace_matching_rows(next_rows)
            return

        next_id_set = set(next_node_ids)
        count_changed = False
        for row in range(len(self._rows) - 1, -1, -1):
            if old_node_ids[row] in next_id_set:
                continue
            self.beginRemoveRows(QModelIndex(), row, row)
            self._rows.pop(row)
            self.endRemoveRows()
            count_changed = True

        for target_row, payload in enumerate(next_rows):
            node_id = next_node_ids[target_row]
            if target_row < len(self._rows) and _payload_node_id(self._rows[target_row]) == node_id:
                self._replace_row(target_row, payload)
                continue
            existing_row = self._find_node_row(node_id, start=target_row + 1)
            if existing_row >= 0:
                self.beginMoveRows(QModelIndex(), existing_row, existing_row, QModelIndex(), target_row)
                moved_payload = self._rows.pop(existing_row)
                self._rows.insert(target_row, moved_payload)
                self.endMoveRows()
                self._replace_row(target_row, payload)
                continue
            self.beginInsertRows(QModelIndex(), target_row, target_row)
            self._rows.insert(target_row, payload)
            self.endInsertRows()
            count_changed = True

        if len(self._rows) > len(next_rows):
            for row in range(len(self._rows) - 1, len(next_rows) - 1, -1):
                self.beginRemoveRows(QModelIndex(), row, row)
                self._rows.pop(row)
                self.endRemoveRows()
                count_changed = True
        if count_changed:
            self.count_changed.emit()

    def _reset_payloads(self, payloads: list[Any]) -> None:
        if self._rows == payloads:
            return
        count_changed = len(self._rows) != len(payloads)
        self.beginResetModel()
        self._rows = list(payloads)
        self.endResetModel()
        if count_changed:
            self.count_changed.emit()

    def _replace_matching_rows(self, payloads: list[Any]) -> None:
        for row, payload in enumerate(payloads):
            self._replace_row(row, payload)

    def _replace_row(self, row: int, payload: Any) -> None:
        if self._rows[row] == payload:
            return
        self._rows[row] = payload
        model_index = self.index(row, 0)
        self.dataChanged.emit(model_index, model_index, _MODEL_ROLES)

    def _find_node_row(self, node_id: str, *, start: int) -> int:
        for row in range(max(0, start), len(self._rows)):
            if _payload_node_id(self._rows[row]) == node_id:
                return row
        return -1


__all__ = ["GraphCanvasVisibleModel"]

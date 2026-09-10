from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

FolderExplorerEntryKind = Literal["file", "folder"]
FolderExplorerClipboardMode = Literal["copy", "cut"]
FolderExplorerSortKey = Literal["name", "type", "size", "modified"]

_VALID_SORT_KEYS: set[str] = {"name", "type", "size", "modified"}


class FolderExplorerServiceError(RuntimeError):
    def __init__(
        self,
        *,
        code: str,
        message: str,
        operation: str,
        path: str = "",
        target_path: str = "",
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.operation = operation
        self.path = path
        self.target_path = target_path

    def to_dict(self) -> dict[str, str]:
        return {
            "code": self.code,
            "message": self.message,
            "operation": self.operation,
            "path": self.path,
            "target_path": self.target_path,
        }


@dataclass(frozen=True, slots=True)
class FolderExplorerBreadcrumb:
    name: str
    absolute_path: str


@dataclass(frozen=True, slots=True)
class FolderExplorerDirectoryEntry:
    name: str
    absolute_path: str
    kind: FolderExplorerEntryKind
    modified_timestamp: float
    extension: str
    type_label: str
    size_bytes: int | None
    display_size: str

    @property
    def is_folder(self) -> bool:
        return self.kind == "folder"


@dataclass(frozen=True, slots=True)
class FolderExplorerDirectoryListing:
    directory_path: str
    parent_path: str | None
    breadcrumbs: tuple[FolderExplorerBreadcrumb, ...]
    entries: tuple[FolderExplorerDirectoryEntry, ...]
    sort_key: FolderExplorerSortKey
    reverse: bool
    filter_text: str


@dataclass(frozen=True, slots=True)
class FolderExplorerClipboard:
    source_path: str
    mode: FolderExplorerClipboardMode


class FolderExplorerFilesystemService:
    def __init__(self) -> None:
        self._clipboard: FolderExplorerClipboard | None = None

    @property
    def clipboard(self) -> FolderExplorerClipboard | None:
        return self._clipboard

    @staticmethod
    def normalize_path(path: str | os.PathLike[str], *, operation: str = "normalize") -> str:
        try:
            candidate = Path(os.fspath(path)).expanduser()
            return str(candidate.resolve(strict=False))
        except (OSError, RuntimeError, TypeError, ValueError) as exc:
            raise FolderExplorerServiceError(
                code="invalid_path",
                message=f"Could not normalize path: {path!r}",
                operation=operation,
                path=str(path),
            ) from exc

    def list_directory(
        self,
        path: str | os.PathLike[str],
        *,
        sort_key: FolderExplorerSortKey = "name",
        reverse: bool = False,
        filter_text: str = "",
    ) -> FolderExplorerDirectoryListing:
        directory = self._require_directory(path, operation="list")
        entries = []
        try:
            for child in directory.iterdir():
                entry = self._entry_for_path(child, operation="list")
                if self._matches_filter(entry, filter_text):
                    entries.append(entry)
        except OSError as exc:
            raise self._error_from_os_error(exc, operation="list", path=directory) from exc

        sorted_entries = self._sort_entries(entries, sort_key=sort_key, reverse=reverse)
        normalized_directory = str(directory)
        return FolderExplorerDirectoryListing(
            directory_path=normalized_directory,
            parent_path=self.parent_path(directory),
            breadcrumbs=self.breadcrumbs(directory),
            entries=tuple(sorted_entries),
            sort_key=sort_key,
            reverse=reverse,
            filter_text=filter_text,
        )

    def parent_path(self, path: str | os.PathLike[str]) -> str | None:
        normalized = Path(self.normalize_path(path, operation="parent"))
        parent = normalized.parent
        if parent == normalized:
            return None
        return str(parent)

    def breadcrumbs(self, path: str | os.PathLike[str]) -> tuple[FolderExplorerBreadcrumb, ...]:
        normalized = Path(self.normalize_path(path, operation="breadcrumbs"))
        parts = normalized.parts
        if not parts:
            return ()

        crumbs: list[FolderExplorerBreadcrumb] = []
        current = Path(parts[0])
        crumbs.append(FolderExplorerBreadcrumb(name=self._breadcrumb_label(parts[0]), absolute_path=str(current)))
        for part in parts[1:]:
            current = current / part
            crumbs.append(FolderExplorerBreadcrumb(name=part, absolute_path=str(current)))
        return tuple(crumbs)

    def new_folder(
        self,
        parent_path: str | os.PathLike[str],
        name: str,
        *,
        confirmed: bool = False,
    ) -> FolderExplorerDirectoryEntry:
        self._require_confirmation(confirmed, operation="new_folder", path=parent_path)
        parent = self._require_directory(parent_path, operation="new_folder")
        target = parent / self._validate_child_name(name, operation="new_folder", path=parent)
        if target.exists():
            raise self._already_exists_error(operation="new_folder", path=parent, target_path=target)
        try:
            target.mkdir()
        except OSError as exc:
            raise self._error_from_os_error(exc, operation="new_folder", path=parent, target_path=target) from exc
        return self._entry_for_path(target, operation="new_folder")

    def rename(
        self,
        path: str | os.PathLike[str],
        new_name: str,
        *,
        confirmed: bool = False,
    ) -> FolderExplorerDirectoryEntry:
        self._require_confirmation(confirmed, operation="rename", path=path)
        source = self._require_existing_path(path, operation="rename")
        target = source.parent / self._validate_child_name(new_name, operation="rename", path=source)
        if target == source:
            return self._entry_for_path(source, operation="rename")
        if target.exists():
            raise self._already_exists_error(operation="rename", path=source, target_path=target)
        try:
            source.rename(target)
        except OSError as exc:
            raise self._error_from_os_error(exc, operation="rename", path=source, target_path=target) from exc
        return self._entry_for_path(target, operation="rename")

    def delete(self, path: str | os.PathLike[str], *, confirmed: bool = False) -> None:
        self._require_confirmation(confirmed, operation="delete", path=path)
        target = self._require_existing_path(path, operation="delete")
        try:
            if target.is_dir() and not target.is_symlink():
                shutil.rmtree(target)
            else:
                target.unlink()
        except OSError as exc:
            raise self._error_from_os_error(exc, operation="delete", path=target) from exc

    def copy(self, path: str | os.PathLike[str], *, confirmed: bool = False) -> FolderExplorerClipboard:
        self._require_confirmation(confirmed, operation="copy", path=path)
        source = self._require_existing_path(path, operation="copy")
        self._clipboard = FolderExplorerClipboard(source_path=str(source), mode="copy")
        return self._clipboard

    def cut(self, path: str | os.PathLike[str], *, confirmed: bool = False) -> FolderExplorerClipboard:
        self._require_confirmation(confirmed, operation="cut", path=path)
        source = self._require_existing_path(path, operation="cut")
        self._clipboard = FolderExplorerClipboard(source_path=str(source), mode="cut")
        return self._clipboard

    def paste(
        self,
        destination_directory: str | os.PathLike[str],
        *,
        clipboard: FolderExplorerClipboard | None = None,
        confirmed: bool = False,
    ) -> FolderExplorerDirectoryEntry:
        selected_clipboard = clipboard if clipboard is not None else self._clipboard
        if selected_clipboard is None:
            raise FolderExplorerServiceError(
                code="empty_clipboard",
                message="No folder explorer clipboard item is available to paste.",
                operation="paste",
            )
        self._require_confirmation(confirmed, operation="paste", path=selected_clipboard.source_path)

        destination = self._require_directory(destination_directory, operation="paste")
        source = self._require_existing_path(selected_clipboard.source_path, operation="paste")
        target = destination / source.name
        if target.exists():
            raise self._already_exists_error(operation="paste", path=source, target_path=target)

        try:
            if selected_clipboard.mode == "copy":
                self._copy_path(source, target)
            elif selected_clipboard.mode == "cut":
                shutil.move(str(source), str(target))
                if selected_clipboard == self._clipboard:
                    self._clipboard = None
            else:
                raise FolderExplorerServiceError(
                    code="invalid_clipboard",
                    message=f"Unsupported folder explorer clipboard mode: {selected_clipboard.mode!r}",
                    operation="paste",
                    path=selected_clipboard.source_path,
                    target_path=str(target),
                )
        except FolderExplorerServiceError:
            raise
        except OSError as exc:
            raise self._error_from_os_error(exc, operation="paste", path=source, target_path=target) from exc
        return self._entry_for_path(target, operation="paste")

    def copy_path(self, path: str | os.PathLike[str], *, quote: bool = False) -> str:
        target = self._require_existing_path(path, operation="copy_path")
        formatted = str(target)
        if quote:
            return f'"{formatted}"'
        return formatted

    @staticmethod
    def _breadcrumb_label(part: str) -> str:
        stripped = part.rstrip("\\/")
        return stripped or part

    @staticmethod
    def _matches_filter(entry: FolderExplorerDirectoryEntry, filter_text: str) -> bool:
        needle = filter_text.strip().casefold()
        if not needle:
            return True
        return needle in entry.name.casefold()

    @classmethod
    def _sort_entries(
        cls,
        entries: list[FolderExplorerDirectoryEntry],
        *,
        sort_key: FolderExplorerSortKey,
        reverse: bool,
    ) -> list[FolderExplorerDirectoryEntry]:
        if sort_key not in _VALID_SORT_KEYS:
            raise FolderExplorerServiceError(
                code="invalid_sort_key",
                message=f"Unsupported folder explorer sort key: {sort_key!r}",
                operation="sort",
            )

        if sort_key == "name":
            folders = [entry for entry in entries if entry.kind == "folder"]
            files = [entry for entry in entries if entry.kind == "file"]
            folders.sort(key=cls._name_sort_key, reverse=reverse)
            files.sort(key=cls._name_sort_key, reverse=reverse)
            return folders + files

        if sort_key == "type":
            return sorted(
                entries,
                key=lambda entry: (
                    entry.type_label.casefold(),
                    entry.extension.casefold(),
                    entry.name.casefold(),
                ),
                reverse=reverse,
            )
        if sort_key == "size":
            return sorted(
                entries,
                key=lambda entry: (
                    -1 if entry.size_bytes is None else entry.size_bytes,
                    entry.name.casefold(),
                ),
                reverse=reverse,
            )
        return sorted(
            entries,
            key=lambda entry: (
                entry.modified_timestamp,
                entry.name.casefold(),
            ),
            reverse=reverse,
        )

    @staticmethod
    def _name_sort_key(entry: FolderExplorerDirectoryEntry) -> tuple[str, str]:
        return (entry.name.casefold(), entry.name)

    def _require_confirmation(
        self,
        confirmed: bool,
        *,
        operation: str,
        path: str | os.PathLike[str],
    ) -> None:
        if confirmed:
            return
        raise FolderExplorerServiceError(
            code="confirmation_required",
            message=f"Folder explorer operation requires confirmation: {operation}",
            operation=operation,
            path=str(path),
        )

    def _require_existing_path(self, path: str | os.PathLike[str], *, operation: str) -> Path:
        normalized = Path(self.normalize_path(path, operation=operation))
        if not normalized.exists():
            raise FolderExplorerServiceError(
                code="not_found",
                message=f"Path does not exist: {normalized}",
                operation=operation,
                path=str(normalized),
            )
        return normalized

    def _require_directory(self, path: str | os.PathLike[str], *, operation: str) -> Path:
        normalized = self._require_existing_path(path, operation=operation)
        if not normalized.is_dir():
            raise FolderExplorerServiceError(
                code="not_directory",
                message=f"Path is not a directory: {normalized}",
                operation=operation,
                path=str(normalized),
            )
        return normalized

    def _validate_child_name(self, name: str, *, operation: str, path: Path) -> str:
        normalized_name = str(name).strip()
        if not normalized_name:
            raise FolderExplorerServiceError(
                code="invalid_name",
                message="Folder explorer item name cannot be empty.",
                operation=operation,
                path=str(path),
            )
        if normalized_name in {".", ".."} or Path(normalized_name).name != normalized_name:
            raise FolderExplorerServiceError(
                code="invalid_name",
                message=f"Folder explorer item name cannot include path separators: {name!r}",
                operation=operation,
                path=str(path),
            )
        if any(separator in normalized_name for separator in ("\\", "/")):
            raise FolderExplorerServiceError(
                code="invalid_name",
                message=f"Folder explorer item name cannot include path separators: {name!r}",
                operation=operation,
                path=str(path),
            )
        return normalized_name

    @classmethod
    def _entry_for_path(cls, path: Path, *, operation: str) -> FolderExplorerDirectoryEntry:
        try:
            stats = path.stat()
            is_folder = path.is_dir()
        except OSError as exc:
            raise cls._error_from_os_error(exc, operation=operation, path=path) from exc

        kind: FolderExplorerEntryKind = "folder" if is_folder else "file"
        size_bytes = None if is_folder else int(stats.st_size)
        extension = "" if is_folder else path.suffix.lower()
        return FolderExplorerDirectoryEntry(
            name=path.name,
            absolute_path=str(path.resolve(strict=False)),
            kind=kind,
            modified_timestamp=float(stats.st_mtime),
            extension=extension,
            type_label=cls._type_label(path, is_folder=is_folder),
            size_bytes=size_bytes,
            display_size=cls._display_size(size_bytes),
        )

    @staticmethod
    def _type_label(path: Path, *, is_folder: bool) -> str:
        if is_folder:
            return "File folder"
        extension = path.suffix.lower().lstrip(".")
        if not extension:
            return "File"
        return f"{extension.upper()} File"

    @staticmethod
    def _display_size(size_bytes: int | None) -> str:
        if size_bytes is None:
            return ""
        if size_bytes == 1:
            return "1 byte"
        if size_bytes < 1024:
            return f"{size_bytes} bytes"

        value = float(size_bytes)
        for unit in ("KB", "MB", "GB", "TB"):
            value /= 1024.0
            if value < 1024.0 or unit == "TB":
                return f"{value:.1f} {unit}"
        return f"{size_bytes} bytes"

    @staticmethod
    def _copy_path(source: Path, target: Path) -> None:
        if source.is_dir() and not source.is_symlink():
            shutil.copytree(source, target)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)

    @staticmethod
    def _already_exists_error(*, operation: str, path: Path, target_path: Path) -> FolderExplorerServiceError:
        return FolderExplorerServiceError(
            code="already_exists",
            message=f"Target already exists: {target_path}",
            operation=operation,
            path=str(path),
            target_path=str(target_path),
        )

    @staticmethod
    def _error_from_os_error(
        exc: OSError,
        *,
        operation: str,
        path: Path,
        target_path: Path | None = None,
    ) -> FolderExplorerServiceError:
        if isinstance(exc, FileNotFoundError):
            code = "not_found"
        elif isinstance(exc, FileExistsError):
            code = "already_exists"
        elif isinstance(exc, PermissionError):
            code = "permission_denied"
        elif isinstance(exc, NotADirectoryError):
            code = "not_directory"
        elif isinstance(exc, IsADirectoryError):
            code = "is_directory"
        else:
            code = "operation_failed"
        return FolderExplorerServiceError(
            code=code,
            message=str(exc),
            operation=operation,
            path=str(path),
            target_path=str(target_path) if target_path is not None else "",
        )


__all__ = [
    "FolderExplorerBreadcrumb",
    "FolderExplorerClipboard",
    "FolderExplorerClipboardMode",
    "FolderExplorerDirectoryEntry",
    "FolderExplorerDirectoryListing",
    "FolderExplorerEntryKind",
    "FolderExplorerFilesystemService",
    "FolderExplorerServiceError",
    "FolderExplorerSortKey",
]

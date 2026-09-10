# Purpose: Standalone PyQt6 GUI for collecting Office files by modified date.
# Map: subsystems/supporting_runtime_assets
# Tests: tests/test_office_date_collector_gui.py

from __future__ import annotations

import argparse
import contextlib
import csv
import html as html_module
import os
import re
import shutil
import sys
import tempfile
import traceback
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import date, datetime, time as day_time, timedelta
from pathlib import Path
from typing import Callable, Iterable, Sequence
from xml.etree import ElementTree

from PyQt6.QtCore import QDate, QThread, Qt, QUrl, pyqtSignal
from PyQt6.QtGui import QAction, QDesktopServices, QIcon
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QStyle,
    QTextEdit,
    QVBoxLayout,
    QWidget,
    QDateEdit,
)


FILE_TYPE_EXTENSIONS = {
    "PowerPoint": frozenset({".ppt", ".pptx", ".pptm", ".pps", ".ppsx", ".ppsm"}),
    "Excel": frozenset({".xlsx", ".xlsm"}),
    "Word": frozenset({".docx"}),
    "HTML": frozenset({".html", ".htm"}),
    "CSV": frozenset({".csv"}),
    "PDF": frozenset({".pdf"}),
}
DEFAULT_FILE_TYPES = tuple(FILE_TYPE_EXTENSIONS)
OPEN_XML_EXTENSIONS = frozenset({".docx", ".pptx", ".pptm", ".ppsx", ".ppsm", ".xlsx", ".xlsm"})
HTML_EXTENSIONS = frozenset({".html", ".htm"})
# Flat text formats (no markup) whose raw bytes are searched directly.
PLAINTEXT_EXTENSIONS = frozenset({".csv"})
# Formats whose text content can be searched (OOXML zips + flat HTML + flat text). Legacy
# binary Office formats (.ppt/.xls/...) are not here -> counted as skipped_unsupported_search.
SEARCHABLE_EXTENSIONS = OPEN_XML_EXTENSIONS | HTML_EXTENSIONS | PLAINTEXT_EXTENSIONS
COPY_BUFFER_SIZE = 8 * 1024 * 1024
PROGRESS_SCALE = 10_000
# Name of the CSV index written into the output folder listing every collected file.
MANIFEST_FILENAME = "collected_files.csv"

# Fast content search: tag-strip + substring skips DOM tree construction + itertext.
# End-to-end the per-file cost is dominated by zip-open + inflate, so the realistic win
# vs ElementTree is ~1.4-1.8x (the raw-parse speedup is ~30x but diluted by I/O). See
# scripts/bench_office_search.py for the full matrix. Compiled once.
_TAG_RE = re.compile(rb"<[^>]*>")
# Env override for both the content-search pool and the (UNC-gated) parallel walk.
_WORKERS_ENV = "OFFICE_COLLECTOR_WORKERS"

# Opportunistic faster inflate (Intel ISA-L). Used only if the package is importable;
# the packaged exe does not bundle it by default (keeps the binary lean and avoids the
# native-DLL-after-Qt hazard), so this is a no-op there. Set OFFICE_COLLECTOR_NO_ISAL=1
# to force the stdlib path even when isal is installed.
try:
    from isal import isal_zlib as _isal_zlib  # type: ignore
    _HAVE_ISAL = True
except Exception:  # pragma: no cover - depends on environment
    _isal_zlib = None
    _HAVE_ISAL = False


@contextlib.contextmanager
def _fast_inflate():
    """Route zipfile inflate through isal for the duration, if available and enabled.

    Safe to wrap a parallel content-search phase: each zip member gets its own
    decompressor object, and the global is restored on exit. Only the content search
    reads zips, so nothing else observes the swap.
    """
    if not _HAVE_ISAL or os.environ.get("OFFICE_COLLECTOR_NO_ISAL") == "1":
        yield
        return
    saved = zipfile.zlib
    zipfile.zlib = _isal_zlib
    try:
        yield
    finally:
        zipfile.zlib = saved


@dataclass(frozen=True)
class JobConfig:
    source_dir: Path
    output_dir: Path
    start_date: date
    end_date: date
    file_types: tuple[str, ...] = DEFAULT_FILE_TYPES
    search_text: str = ""
    case_sensitive: bool = False


@dataclass(frozen=True)
class FileMatch:
    source_path: Path
    size: int
    modified_at: float


@dataclass
class ScanStats:
    folders: int = 0
    files: int = 0
    matched: int = 0
    skipped_outside_date: int = 0
    skipped_text: int = 0
    skipped_unsupported_search: int = 0
    errors: int = 0


@dataclass
class JobSummary:
    scanned_folders: int = 0
    scanned_files: int = 0
    matched_files: int = 0
    skipped_outside_date: int = 0
    skipped_text: int = 0
    skipped_unsupported_search: int = 0
    copied_files: int = 0
    error_count: int = 0
    total_bytes: int = 0
    copied_bytes: int = 0
    cancelled: bool = False
    output_dir: Path | None = None
    manifest_path: Path | None = None


class Cancelled(RuntimeError):
    pass


def _norm_path(path: Path) -> str:
    return os.path.normcase(os.path.abspath(os.fspath(path)))


def same_or_child(path: Path, parent: Path) -> bool:
    child_norm = _norm_path(path)
    parent_norm = _norm_path(parent)
    return child_norm == parent_norm or child_norm.startswith(parent_norm + os.sep)


def date_bounds(start: date, end: date) -> tuple[float, float]:
    start_dt = datetime.combine(start, day_time.min)
    end_dt = datetime.combine(end, day_time.max)
    return start_dt.timestamp(), end_dt.timestamp()


def active_extensions(file_types: Sequence[str]) -> frozenset[str]:
    extensions: set[str] = set()
    for file_type in file_types:
        extensions.update(FILE_TYPE_EXTENSIONS[file_type])
    return frozenset(extensions)


def is_office_file(path: Path, extensions: frozenset[str]) -> bool:
    return not path.name.startswith("~$") and path.suffix.casefold() in extensions


def _office_xml_parts(extension: str, names: Sequence[str]) -> list[str]:
    if extension == ".docx":
        return [
            name
            for name in names
            if name == "word/document.xml"
            or name.startswith("word/header")
            or name.startswith("word/footer")
            or name in {"word/footnotes.xml", "word/endnotes.xml", "word/comments.xml"}
        ]
    if extension in {".pptx", ".pptm", ".ppsx", ".ppsm"}:
        return [
            name
            for name in names
            if (name.startswith("ppt/slides/slide") or name.startswith("ppt/notesSlides/notesSlide"))
            and name.endswith(".xml")
        ]
    if extension in {".xlsx", ".xlsm"}:
        return [
            name
            for name in names
            if name == "xl/sharedStrings.xml"
            or (name.startswith("xl/worksheets/sheet") and name.endswith(".xml"))
        ]
    return []


def _iter_xml_text(payload: bytes) -> Iterable[str]:
    try:
        root = ElementTree.fromstring(payload)
    except ElementTree.ParseError:
        return
    for text in root.itertext():
        if text:
            yield text


def open_xml_contains(path: Path, needle: str, case_sensitive: bool) -> bool:
    suffix = path.suffix.casefold()
    if suffix not in OPEN_XML_EXTENSIONS:
        return False
    target = needle if case_sensitive else needle.casefold()
    try:
        with zipfile.ZipFile(path) as package:
            for name in _office_xml_parts(suffix, package.namelist()):
                haystack = "\n".join(_iter_xml_text(package.read(name)))
                if not case_sensitive:
                    haystack = haystack.casefold()
                if target in haystack:
                    return True
    except (OSError, zipfile.BadZipFile, KeyError, RuntimeError):
        return False
    return False


def _needle_is_prefilter_safe(needle: str) -> bool:
    """True when a raw tag-stripped byte search is exact vs. the ElementTree path.

    Safe requires pure ASCII (so non-ASCII stored as numeric char references cannot
    be missed) and none of the XML-significant chars ``& < >`` (which are entity
    encoded in the payload, e.g. ``R&D`` -> ``R&amp;D``). Anything else routes to the
    exact ElementTree path in :func:`open_xml_contains`.
    """
    return needle.isascii() and not any(ch in needle for ch in "&<>")


def open_xml_contains_fast(path: Path, needle: str, case_sensitive: bool) -> bool:
    """Fast equivalent of :func:`open_xml_contains` for the common case.

    For ASCII needles without ``& < >`` it strips XML tags in C (``_TAG_RE``) and does
    a direct substring search on the decoded text -- ~30x faster than DOM parsing while
    producing identical matches (tag-strip keeps the same separator-between-runs
    behavior as ``"\\n".join(itertext())``). Other needles fall back to the exact path.
    """
    suffix = path.suffix.casefold()
    if suffix not in OPEN_XML_EXTENSIONS:
        return False
    if not _needle_is_prefilter_safe(needle):
        return open_xml_contains(path, needle, case_sensitive)
    target = needle if case_sensitive else needle.casefold()
    try:
        with zipfile.ZipFile(path) as package:
            for name in _office_xml_parts(suffix, package.namelist()):
                haystack = _TAG_RE.sub(b" ", package.read(name)).decode("utf-8", "replace")
                if not case_sensitive:
                    haystack = haystack.casefold()
                if target in haystack:
                    return True
    except (OSError, zipfile.BadZipFile, KeyError, RuntimeError):
        return False
    return False


def html_contains(path: Path, needle: str, case_sensitive: bool) -> bool:
    """Whether a flat HTML file's visible text contains ``needle``.

    HTML is not a zip: read the file, strip tags (so markup/attributes are not matched,
    matching the Office "search visible text" behavior), and search. For needles that may
    be entity-encoded (non-ASCII, or ``& < >``) the text is HTML-unescaped first so e.g.
    ``R&D`` matches ``R&amp;D`` and ``café`` matches ``caf&#233;``. UTF-8 is assumed
    (ASCII needles match regardless of the file's encoding since ASCII bytes are stable).
    """
    if path.suffix.casefold() not in HTML_EXTENSIONS:
        return False
    try:
        data = path.read_bytes()
    except OSError:
        return False
    haystack = _TAG_RE.sub(b" ", data).decode("utf-8", "replace")
    if not _needle_is_prefilter_safe(needle):
        haystack = html_module.unescape(haystack)
    target = needle if case_sensitive else needle.casefold()
    if not case_sensitive:
        haystack = haystack.casefold()
    return target in haystack


def plain_text_contains(path: Path, needle: str, case_sensitive: bool) -> bool:
    """Whether a flat text file (e.g. CSV) contains ``needle``.

    CSV has no markup, so the raw decoded bytes are searched directly -- no tag stripping
    or entity unescaping. UTF-8 is assumed (ASCII needles match regardless of encoding
    since ASCII bytes are stable).
    """
    if path.suffix.casefold() not in PLAINTEXT_EXTENSIONS:
        return False
    try:
        data = path.read_bytes()
    except OSError:
        return False
    haystack = data.decode("utf-8", "replace")
    target = needle if case_sensitive else needle.casefold()
    if not case_sensitive:
        haystack = haystack.casefold()
    return target in haystack


def file_contains(path: Path, needle: str, case_sensitive: bool) -> bool:
    """Dispatch a content search to the matcher for the file's format."""
    suffix = path.suffix.casefold()
    if suffix in OPEN_XML_EXTENSIONS:
        return open_xml_contains_fast(path, needle, case_sensitive)
    if suffix in HTML_EXTENSIONS:
        return html_contains(path, needle, case_sensitive)
    if suffix in PLAINTEXT_EXTENSIONS:
        return plain_text_contains(path, needle, case_sensitive)
    return False


def unique_destination(source_path: Path, output_dir: Path, used_names: set[str]) -> Path:
    stem = source_path.stem
    suffix = source_path.suffix
    candidate = source_path.name
    index = 0
    while candidate.casefold() in used_names:
        index += 1
        candidate = f"{stem}_{index}{suffix}"
    used_names.add(candidate.casefold())
    return output_dir / candidate


def existing_output_names(output_dir: Path) -> set[str]:
    if not output_dir.exists():
        return set()
    return {path.name.casefold() for path in output_dir.iterdir()}


def write_manifest(
    output_dir: Path,
    source_dir: Path,
    rows: Sequence[tuple[Path, Path]],
) -> Path:
    """Write the CSV index of collected files into ``output_dir``.

    ``rows`` is ``(source_path, destination_path)`` per successfully copied file. The
    CSV lists the original file name, its absolute source path, its path relative to the
    scanned ``source_dir``, and the (possibly collision-renamed) name it was copied to.
    Uses ``utf-8-sig`` so Excel detects UTF-8 on open. Returns the manifest path.
    """
    manifest_path = output_dir / MANIFEST_FILENAME
    with manifest_path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow(["File Name", "Absolute Path", "Relative Path", "Copied As"])
        for source_path, destination in rows:
            writer.writerow([
                source_path.name,
                os.path.abspath(source_path),
                os.path.relpath(source_path, source_dir),
                destination.name,
            ])
    return manifest_path


def _env_workers() -> int | None:
    raw = os.environ.get(_WORKERS_ENV, "").strip()
    if raw.isdigit() and int(raw) > 0:
        return int(raw)
    return None


def _is_network_source(source: Path) -> bool:
    # UNC paths (\\server\share) are the reliable "this is a slow share" signal on
    # Windows; mapped network drives are not distinguishable here, so power users get
    # the env override instead. Local fixed drives keep the byte-identical serial walk.
    return os.fspath(source).startswith("\\\\")


def _content_search_workers(source: Path, n_candidates: int) -> int:
    if n_candidates <= 1:
        return 1
    override = _env_workers()
    if override is not None:
        return min(override, n_candidates)
    # Benchmarking (scripts/bench_office_search.py) shows that on local warm-cache disk a
    # thread pool LOSES to serial here: the per-file work is short and the pool dispatch +
    # GIL-bound orchestration outweigh the (absent) I/O latency to hide. Parallelism only
    # pays when there is real I/O latency, i.e. on network/UNC shares -- so gate on that.
    if _is_network_source(source):
        return min(32, max(1, (os.cpu_count() or 4) * 5), n_candidates)
    return 1


def _scan_directory(
    folder: Path,
    output_norm: str,
    extensions: frozenset[str],
    cancel_requested: Callable[[], bool] | None = None,
) -> tuple[list[Path], list[FileMatch], int, Path | None, list[str], str | None]:
    """Scan one directory into plain data (no stats mutation, no callbacks).

    Returns ``(child_dirs, office_files, total_files, sample_path, entry_errors,
    scan_error)``. Pure and thread-safe so it can be fanned out across a pool; the
    caller (single consumer thread) applies counting, classification and callbacks.

    Hot-path note: at full-drive scale the dominant cost is per-entry Python work, so we
    do a string-level extension test on ``entry.name`` and only build a ``Path`` for the
    rare actual office files (and for child directories) -- not for every file. The
    output-folder skip compares the already-absolute ``entry.path`` against a precomputed
    ``output_norm`` to avoid an ``abspath`` per directory.
    """
    child_dirs: list[Path] = []
    office_files: list[FileMatch] = []
    total_files = 0
    sample_path: Path | None = None
    entry_errors: list[str] = []
    sep = os.sep
    normcase = os.path.normcase
    try:
        with os.scandir(folder) as entries:
            for entry in entries:
                if cancel_requested and cancel_requested():
                    raise Cancelled()
                try:
                    if entry.is_dir(follow_symlinks=False):
                        child_norm = normcase(entry.path)
                        if child_norm != output_norm and not child_norm.startswith(output_norm + sep):
                            child_dirs.append(Path(entry.path))
                        continue
                    if not entry.is_file(follow_symlinks=False):
                        continue
                    total_files += 1
                    name = entry.name
                    dot = name.rfind(".")
                    # Fast reject 99.99% of files without constructing a Path object.
                    if dot <= 0 or name[dot:].casefold() not in extensions or name.startswith("~$"):
                        continue
                    entry_path = Path(entry.path)
                    if not is_office_file(entry_path, extensions):  # exact-semantics confirm (rare)
                        continue
                    info = entry.stat(follow_symlinks=False)
                    office_files.append(FileMatch(entry_path, info.st_size, info.st_mtime))
                    sample_path = entry_path
                except OSError as exc:
                    entry_errors.append(f"Skipped unreadable entry: {entry.path} ({exc})")
    except Cancelled:
        raise
    except OSError as exc:
        return [], [], 0, None, [], f"Skipped unreadable folder: {folder} ({exc})"
    return child_dirs, office_files, total_files, sample_path, entry_errors, None


def _classify_office_file(
    match: FileMatch,
    start_ts: float,
    end_ts: float,
    search_text: str,
    matches: list[FileMatch],
    candidates: list[FileMatch],
    stats: ScanStats,
    log: Callable[[str], None] | None,
) -> None:
    """Apply the date/search routing for one office file (consumer thread only)."""
    if start_ts <= match.modified_at <= end_ts:
        if search_text:
            if match.source_path.suffix.casefold() not in SEARCHABLE_EXTENSIONS:
                stats.skipped_unsupported_search += 1
                if log:
                    log(f"Skipped content search for unsupported legacy format: {match.source_path}")
            else:
                candidates.append(match)
        else:
            matches.append(match)
            stats.matched += 1
    else:
        stats.skipped_outside_date += 1


def _consume_directory_result(
    folder: Path,
    result: tuple[list[Path], list[FileMatch], int, Path | None, list[str], str | None],
    *,
    start_ts: float,
    end_ts: float,
    search_text: str,
    matches: list[FileMatch],
    candidates: list[FileMatch],
    stats: ScanStats,
    file_seen: Callable[[Path, ScanStats], None] | None,
    log: Callable[[str], None] | None,
) -> list[Path]:
    child_dirs, office_files, total_files, sample_path, entry_errors, scan_error = result
    if scan_error:
        stats.errors += 1
        if log:
            log(scan_error)
        return []
    prev_files = stats.files
    stats.files += total_files
    if file_seen and sample_path is not None and prev_files // 25 != stats.files // 25:
        file_seen(sample_path, stats)
    for message in entry_errors:
        stats.errors += 1
        if log:
            log(message)
    for match in office_files:
        _classify_office_file(match, start_ts, end_ts, search_text, matches, candidates, stats, log)
    return child_dirs


def _walk_serial(
    config: JobConfig,
    extensions: frozenset[str],
    start_ts: float,
    end_ts: float,
    search_text: str,
    matches: list[FileMatch],
    candidates: list[FileMatch],
    stats: ScanStats,
    cancel_requested: Callable[[], bool] | None,
    folder_seen: Callable[[Path, ScanStats], None] | None,
    file_seen: Callable[[Path, ScanStats], None] | None,
    log: Callable[[str], None] | None,
) -> None:
    output_dir = config.output_dir
    output_norm = _norm_path(output_dir)
    stack = [config.source_dir]
    while stack:
        if cancel_requested and cancel_requested():
            raise Cancelled()
        folder = stack.pop()
        if same_or_child(folder, output_dir):
            continue
        stats.folders += 1
        if folder_seen:
            folder_seen(folder, stats)
        result = _scan_directory(folder, output_norm, extensions, cancel_requested)
        child_dirs = _consume_directory_result(
            folder,
            result,
            start_ts=start_ts,
            end_ts=end_ts,
            search_text=search_text,
            matches=matches,
            candidates=candidates,
            stats=stats,
            file_seen=file_seen,
            log=log,
        )
        stack.extend(child_dirs)


def _search_candidates(
    config: JobConfig,
    candidates: list[FileMatch],
    matches: list[FileMatch],
    stats: ScanStats,
    search_text: str,
    cancel_requested: Callable[[], bool] | None,
    search_started: Callable[[Path, ScanStats], None] | None,
    log: Callable[[str], None] | None,
) -> None:
    if not candidates:
        return
    case_sensitive = config.case_sensitive
    if search_started:
        search_started(candidates[0].source_path, stats)
    workers = _content_search_workers(config.source_dir, len(candidates))

    def record(match: FileMatch, hit: bool) -> None:
        if hit:
            matches.append(match)
            stats.matched += 1
        else:
            stats.skipped_text += 1

    # _fast_inflate() opportunistically routes inflate through isal for this whole phase.
    with _fast_inflate():
        if workers <= 1:
            for index, match in enumerate(candidates):
                if cancel_requested and cancel_requested():
                    raise Cancelled()
                if search_started and index % 25 == 0:
                    search_started(match.source_path, stats)
                try:
                    hit = file_contains(match.source_path, search_text, case_sensitive)
                except Exception as exc:  # defensive: the fast path already swallows OSError
                    stats.errors += 1
                    hit = False
                    if log:
                        log(f"Search failed: {match.source_path} ({exc})")
                record(match, hit)
            return

        pool = ThreadPoolExecutor(max_workers=workers)
        try:
            future_to_match = {
                pool.submit(file_contains, match.source_path, search_text, case_sensitive): match
                for match in candidates
            }
            completed = 0
            for future in as_completed(future_to_match):
                if cancel_requested and cancel_requested():
                    pool.shutdown(wait=False, cancel_futures=True)
                    raise Cancelled()
                match = future_to_match[future]
                completed += 1
                if search_started and completed % 25 == 0:
                    search_started(match.source_path, stats)
                try:
                    hit = future.result()
                except Exception as exc:  # defensive: the fast path already swallows OSError
                    stats.errors += 1
                    hit = False
                    if log:
                        log(f"Search failed: {match.source_path} ({exc})")
                record(match, hit)
        finally:
            pool.shutdown(wait=False)


def scan_office_files(
    config: JobConfig,
    cancel_requested: Callable[[], bool] | None = None,
    folder_seen: Callable[[Path, ScanStats], None] | None = None,
    file_seen: Callable[[Path, ScanStats], None] | None = None,
    search_started: Callable[[Path, ScanStats], None] | None = None,
    log: Callable[[str], None] | None = None,
) -> tuple[list[FileMatch], ScanStats]:
    start_ts, end_ts = date_bounds(config.start_date, config.end_date)
    extensions = active_extensions(config.file_types)
    search_text = config.search_text.strip()
    matches: list[FileMatch] = []
    candidates: list[FileMatch] = []
    stats = ScanStats()

    # Phase 1: walk the tree and collect matches (no-search) or content-search
    # candidates. The walk is serial: with the per-entry Path() elimination in
    # _scan_directory it beats native multithreaded robocopy /MT on a full-drive scan
    # (scripts/bench_vs_windows.py), and a thread-per-directory walk does not help on a
    # GIL-bound enumeration -- it only adds overhead.
    _walk_serial(
        config, extensions, start_ts, end_ts, search_text,
        matches, candidates, stats,
        cancel_requested, folder_seen, file_seen, log,
    )

    # Phase 2: content search across candidates, parallelized over a thread pool.
    if search_text:
        _search_candidates(
            config, candidates, matches, stats, search_text,
            cancel_requested, search_started, log,
        )

    matches.sort(key=lambda item: (item.source_path.name.casefold(), _norm_path(item.source_path)))
    return matches, stats


def copy_file_with_progress(
    source: Path,
    destination: Path,
    cancel_requested: Callable[[], bool] | None = None,
    progress: Callable[[int], None] | None = None,
) -> int:
    copied = 0
    destination.parent.mkdir(parents=True, exist_ok=True)
    buffer = bytearray(COPY_BUFFER_SIZE)
    try:
        with source.open("rb", buffering=0) as src, destination.open("wb", buffering=0) as dst:
            while True:
                if cancel_requested and cancel_requested():
                    raise Cancelled()
                count = src.readinto(buffer)
                if not count:
                    break
                dst.write(memoryview(buffer)[:count])
                copied += count
                if progress:
                    progress(copied)
        shutil.copystat(source, destination)
    except BaseException:
        destination.unlink(missing_ok=True)
        raise
    return copied


def collect_office_files(
    config: JobConfig,
    cancel_requested: Callable[[], bool] | None = None,
    folder_seen: Callable[[Path, ScanStats], None] | None = None,
    file_seen: Callable[[Path, ScanStats], None] | None = None,
    search_started: Callable[[Path, ScanStats], None] | None = None,
    copy_started: Callable[[FileMatch, Path, int, int], None] | None = None,
    copy_progress: Callable[[int, int, FileMatch, Path], None] | None = None,
    log: Callable[[str], None] | None = None,
) -> JobSummary:
    if config.start_date > config.end_date:
        raise ValueError("Start date must be on or before end date.")
    if not config.file_types:
        raise ValueError("Select at least one file type.")
    if not config.source_dir.is_dir():
        raise ValueError(f"Source folder does not exist: {config.source_dir}")
    if _norm_path(config.source_dir) == _norm_path(config.output_dir):
        raise ValueError("Source and output folders must be different.")

    config.output_dir.mkdir(parents=True, exist_ok=True)
    matches, stats = scan_office_files(config, cancel_requested, folder_seen, file_seen, search_started, log)
    summary = JobSummary(
        scanned_folders=stats.folders,
        scanned_files=stats.files,
        matched_files=stats.matched,
        skipped_outside_date=stats.skipped_outside_date,
        skipped_text=stats.skipped_text,
        skipped_unsupported_search=stats.skipped_unsupported_search,
        error_count=stats.errors,
        total_bytes=sum(item.size for item in matches),
        output_dir=config.output_dir,
    )

    used_names = existing_output_names(config.output_dir)
    manifest_rows: list[tuple[Path, Path]] = []
    for index, match in enumerate(matches, start=1):
        if cancel_requested and cancel_requested():
            summary.cancelled = True
            break
        destination = unique_destination(match.source_path, config.output_dir, used_names)
        if copy_started:
            copy_started(match, destination, index, len(matches))
        try:
            last_file_bytes = 0

            def on_file_progress(file_bytes: int) -> None:
                nonlocal last_file_bytes
                delta = file_bytes - last_file_bytes
                last_file_bytes = file_bytes
                summary.copied_bytes += delta
                if copy_progress:
                    copy_progress(summary.copied_bytes, summary.total_bytes, match, destination)

            copied = copy_file_with_progress(match.source_path, destination, cancel_requested, on_file_progress)
            if copied != match.size and log:
                log(f"Copied with size change: {match.source_path} ({match.size} -> {copied} bytes)")
            summary.copied_files += 1
            manifest_rows.append((match.source_path, destination))
            if log:
                log(f"Copied: {match.source_path} -> {destination.name}")
        except Cancelled:
            summary.cancelled = True
            break
        except OSError as exc:
            summary.error_count += 1
            if log:
                log(f"Copy failed: {match.source_path} ({exc})")

    if manifest_rows:
        try:
            summary.manifest_path = write_manifest(config.output_dir, config.source_dir, manifest_rows)
            if log:
                log(f"Wrote index of {len(manifest_rows)} files: {summary.manifest_path}")
        except OSError as exc:
            summary.error_count += 1
            if log:
                log(f"Failed to write {MANIFEST_FILENAME}: {exc}")
    return summary


def _fmt_bytes(value: int) -> str:
    units = ("B", "KB", "MB", "GB", "TB")
    amount = float(value)
    for unit in units:
        if amount < 1024 or unit == units[-1]:
            if unit == "B":
                return f"{value} B"
            return f"{amount:.1f} {unit}"
        amount /= 1024
    return f"{value} B"


class CopyWorker(QThread):
    phase_changed = pyqtSignal(str)
    folder_changed = pyqtSignal(str)
    file_changed = pyqtSignal(str)
    progress_changed = pyqtSignal(int, int, str)
    counts_changed = pyqtSignal(int, int, int, int, int)
    log_message = pyqtSignal(str)
    completed = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, config: JobConfig) -> None:
        super().__init__()
        self.config = config
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def is_cancelled(self) -> bool:
        return self._cancelled

    def run(self) -> None:
        try:
            self.phase_changed.emit("Scanning")
            self.progress_changed.emit(0, 0, "Scanning folders...")

            def folder_seen(path: Path, stats: ScanStats) -> None:
                self.folder_changed.emit(os.fspath(path))
                self.counts_changed.emit(stats.folders, stats.files, stats.matched, 0, stats.errors)

            def file_seen(path: Path, stats: ScanStats) -> None:
                # Throttling is handled upstream (per ~25-file boundary) since the scan
                # now advances stats.files in per-directory batches.
                self.file_changed.emit(os.fspath(path))
                self.counts_changed.emit(stats.folders, stats.files, stats.matched, 0, stats.errors)

            def search_started(path: Path, stats: ScanStats) -> None:
                self.phase_changed.emit("Searching")
                self.file_changed.emit(os.fspath(path))
                self.counts_changed.emit(stats.folders, stats.files, stats.matched, 0, stats.errors)

            def copy_started(match: FileMatch, destination: Path, index: int, total: int) -> None:
                self.phase_changed.emit("Copying")
                self.file_changed.emit(os.fspath(match.source_path))
                self.log_message.emit(f"Copying {index}/{total}: {match.source_path.name} -> {destination.name}")

            def copy_progress(copied: int, total: int, match: FileMatch, destination: Path) -> None:
                if total <= 0:
                    self.progress_changed.emit(0, 1, "Copying...")
                    return
                value = min(PROGRESS_SCALE, int(copied * PROGRESS_SCALE / total))
                label = f"{_fmt_bytes(copied)} / {_fmt_bytes(total)} - {match.source_path.name}"
                self.progress_changed.emit(value, PROGRESS_SCALE, label)

            summary = collect_office_files(
                self.config,
                cancel_requested=self.is_cancelled,
                folder_seen=folder_seen,
                file_seen=file_seen,
                search_started=search_started,
                copy_started=copy_started,
                copy_progress=copy_progress,
                log=self.log_message.emit,
            )
            self.counts_changed.emit(
                summary.scanned_folders,
                summary.scanned_files,
                summary.matched_files,
                summary.copied_files,
                summary.error_count,
            )
            if summary.cancelled:
                self.phase_changed.emit("Cancelled")
                self.progress_changed.emit(0, 1, "Cancelled")
            else:
                self.phase_changed.emit("Complete")
                self.progress_changed.emit(PROGRESS_SCALE, PROGRESS_SCALE, "Complete")
            self.completed.emit(summary)
        except Cancelled:
            self.completed.emit(JobSummary(cancelled=True, output_dir=self.config.output_dir))
        except Exception:
            self.failed.emit(traceback.format_exc())


class OfficeDateCollectorWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.worker: CopyWorker | None = None
        self.setWindowTitle("Office Date Collector")
        self.resize(1120, 720)
        self.setMinimumSize(860, 580)
        self._build_ui()
        self._apply_style()
        self._set_default_dates()

    def _build_ui(self) -> None:
        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(22, 18, 22, 18)
        root.setSpacing(14)

        title_row = QHBoxLayout()
        title = QLabel("Office Date Collector")
        title.setObjectName("TitleLabel")
        subtitle = QLabel("Fast folder scan and collision-safe Office file copy")
        subtitle.setObjectName("MutedLabel")
        title_col = QVBoxLayout()
        title_col.addWidget(title)
        title_col.addWidget(subtitle)
        title_row.addLayout(title_col, 1)
        self.open_output_button = QPushButton("Open Output")
        self.open_output_button.setIcon(self._icon(QStyle.StandardPixmap.SP_DirOpenIcon))
        self.open_output_button.setEnabled(False)
        self.open_output_button.clicked.connect(self._open_output)
        title_row.addWidget(self.open_output_button)
        root.addLayout(title_row)

        picker_panel = QFrame()
        picker_panel.setObjectName("Panel")
        picker_layout = QGridLayout(picker_panel)
        picker_layout.setContentsMargins(16, 14, 16, 14)
        picker_layout.setHorizontalSpacing(10)
        picker_layout.setVerticalSpacing(10)

        self.source_edit = QLineEdit()
        self.source_edit.setPlaceholderText("Select folder to scan")
        self.output_edit = QLineEdit()
        self.output_edit.setPlaceholderText("Select output folder")
        self.source_button = QPushButton("Browse")
        self.source_button.setIcon(self._icon(QStyle.StandardPixmap.SP_DirOpenIcon))
        self.output_button = QPushButton("Browse")
        self.output_button.setIcon(self._icon(QStyle.StandardPixmap.SP_DialogSaveButton))
        self.source_button.clicked.connect(self._choose_source)
        self.output_button.clicked.connect(self._choose_output)

        self.start_date_edit = QDateEdit()
        self.end_date_edit = QDateEdit()
        for date_edit in (self.start_date_edit, self.end_date_edit):
            date_edit.setCalendarPopup(True)
            date_edit.setDisplayFormat("yyyy-MM-dd")

        self.powerpoint_checkbox = QCheckBox("PowerPoint")
        self.excel_checkbox = QCheckBox("Excel")
        self.word_checkbox = QCheckBox("Word")
        self.html_checkbox = QCheckBox("HTML")
        self.csv_checkbox = QCheckBox("CSV")
        self.pdf_checkbox = QCheckBox("PDF")
        for checkbox in (
            self.powerpoint_checkbox,
            self.excel_checkbox,
            self.word_checkbox,
            self.html_checkbox,
            self.csv_checkbox,
            self.pdf_checkbox,
        ):
            checkbox.setChecked(True)

        file_type_row = QHBoxLayout()
        file_type_row.addWidget(self.powerpoint_checkbox)
        file_type_row.addWidget(self.excel_checkbox)
        file_type_row.addWidget(self.word_checkbox)
        file_type_row.addWidget(self.html_checkbox)
        file_type_row.addWidget(self.csv_checkbox)
        file_type_row.addWidget(self.pdf_checkbox)
        file_type_row.addStretch(1)

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Optional text to find inside selected files")
        self.case_sensitive_checkbox = QCheckBox("Case sensitive")

        search_row = QHBoxLayout()
        search_row.addWidget(self.search_edit, 1)
        search_row.addWidget(self.case_sensitive_checkbox)

        picker_layout.addWidget(QLabel("Source"), 0, 0)
        picker_layout.addWidget(self.source_edit, 0, 1)
        picker_layout.addWidget(self.source_button, 0, 2)
        picker_layout.addWidget(QLabel("Output"), 1, 0)
        picker_layout.addWidget(self.output_edit, 1, 1)
        picker_layout.addWidget(self.output_button, 1, 2)
        picker_layout.addWidget(QLabel("Modified From"), 2, 0)
        picker_layout.addWidget(self.start_date_edit, 2, 1)
        picker_layout.addWidget(QLabel("Modified To"), 3, 0)
        picker_layout.addWidget(self.end_date_edit, 3, 1)
        picker_layout.addWidget(QLabel("File Types"), 4, 0)
        picker_layout.addLayout(file_type_row, 4, 1)
        picker_layout.addWidget(QLabel("Text Contains"), 5, 0)
        picker_layout.addLayout(search_row, 5, 1)
        picker_layout.setColumnStretch(1, 1)
        root.addWidget(picker_panel)

        action_row = QHBoxLayout()
        self.start_button = QPushButton("Start")
        self.start_button.setObjectName("PrimaryButton")
        self.start_button.setIcon(self._icon(QStyle.StandardPixmap.SP_MediaPlay))
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setIcon(self._icon(QStyle.StandardPixmap.SP_BrowserStop))
        self.cancel_button.setEnabled(False)
        self.start_button.clicked.connect(self._start)
        self.cancel_button.clicked.connect(self._cancel)
        action_row.addWidget(self.start_button)
        action_row.addWidget(self.cancel_button)
        action_row.addStretch(1)
        root.addLayout(action_row)

        status_panel = QFrame()
        status_panel.setObjectName("Panel")
        status_layout = QVBoxLayout(status_panel)
        status_layout.setContentsMargins(16, 14, 16, 14)
        status_layout.setSpacing(10)

        self.phase_label = QLabel("Ready")
        self.phase_label.setObjectName("SectionTitle")
        self.current_folder_label = QLabel("Folder: -")
        self.current_folder_label.setObjectName("PathLabel")
        self.current_file_label = QLabel("File: -")
        self.current_file_label.setObjectName("PathLabel")
        self.progress_bar = QProgressBar()
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setRange(0, 1)
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("Ready")

        counts_layout = QHBoxLayout()
        self.folders_count = self._metric_label("Folders", "0")
        self.files_count = self._metric_label("Files", "0")
        self.matched_count = self._metric_label("Matched", "0")
        self.copied_count = self._metric_label("Copied", "0")
        self.errors_count = self._metric_label("Errors", "0")
        for widget in (
            self.folders_count,
            self.files_count,
            self.matched_count,
            self.copied_count,
            self.errors_count,
        ):
            counts_layout.addWidget(widget)

        self.log_edit = QTextEdit()
        self.log_edit.setObjectName("LogEdit")
        self.log_edit.setReadOnly(True)
        self.log_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        status_layout.addWidget(self.phase_label)
        status_layout.addWidget(self.current_folder_label)
        status_layout.addWidget(self.current_file_label)
        status_layout.addWidget(self.progress_bar)
        status_layout.addLayout(counts_layout)
        status_layout.addWidget(self.log_edit, 1)
        root.addWidget(status_panel, 1)

        exit_action = QAction("Exit", self)
        exit_action.triggered.connect(self.close)
        self.addAction(exit_action)
        self.setCentralWidget(central)

    def _apply_style(self) -> None:
        self.setStyleSheet(
            """
            QWidget {
                background: #edf2f6;
                color: #1a2a35;
                font-family: "Segoe UI", Arial, sans-serif;
                font-size: 10pt;
            }
            QLabel#TitleLabel {
                font-size: 22pt;
                font-weight: 700;
                color: #102433;
            }
            QLabel#SectionTitle {
                font-size: 13pt;
                font-weight: 650;
                color: #163449;
            }
            QLabel#MutedLabel {
                color: #5f6f7c;
            }
            QLabel#PathLabel {
                background: transparent;
                color: #405565;
            }
            QFrame#Panel {
                background: #ffffff;
                border: 1px solid #cfd9e2;
                border-radius: 7px;
            }
            QLineEdit, QDateEdit, QTextEdit {
                background: #f9fbfd;
                border: 1px solid #bdc9d4;
                border-radius: 5px;
                padding: 7px 9px;
                selection-background-color: #2f7dc1;
            }
            QTextEdit#LogEdit {
                background: #101b24;
                color: #d7e7f3;
                border-color: #223646;
                font-family: Consolas, "Cascadia Mono", monospace;
                font-size: 9pt;
            }
            QPushButton {
                background: #f8fbfd;
                border: 1px solid #b8c7d4;
                border-radius: 5px;
                padding: 8px 14px;
                min-width: 94px;
            }
            QPushButton:hover {
                background: #eaf4fb;
                border-color: #5f9cc7;
            }
            QPushButton:pressed {
                background: #d7eaf6;
            }
            QPushButton:disabled {
                color: #8a98a3;
                background: #eef2f5;
                border-color: #d5dde4;
            }
            QPushButton#PrimaryButton {
                background: #1976a3;
                color: #ffffff;
                border-color: #166b94;
                font-weight: 650;
            }
            QPushButton#PrimaryButton:hover {
                background: #2189ba;
            }
            QProgressBar {
                background: #e3ebf1;
                border: 1px solid #bac8d3;
                border-radius: 6px;
                min-height: 26px;
                text-align: center;
                color: #173041;
                font-weight: 650;
            }
            QProgressBar::chunk {
                background: #24a3c7;
                border-radius: 5px;
            }
            """
        )

    def _set_default_dates(self) -> None:
        today = QDate.currentDate()
        self.end_date_edit.setDate(today)
        self.start_date_edit.setDate(today.addDays(-30))

    def _metric_label(self, title: str, value: str) -> QLabel:
        label = QLabel(f"{title}: {value}")
        label.setObjectName("MetricLabel")
        label.setMinimumWidth(126)
        return label

    def _icon(self, pixmap: QStyle.StandardPixmap) -> QIcon:
        return self.style().standardIcon(pixmap)

    def _choose_source(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Select source folder", self.source_edit.text())
        if folder:
            self.source_edit.setText(folder)

    def _choose_output(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Select output folder", self.output_edit.text())
        if folder:
            self.output_edit.setText(folder)

    def _selected_file_types(self) -> tuple[str, ...]:
        selected: list[str] = []
        if self.powerpoint_checkbox.isChecked():
            selected.append("PowerPoint")
        if self.excel_checkbox.isChecked():
            selected.append("Excel")
        if self.word_checkbox.isChecked():
            selected.append("Word")
        if self.html_checkbox.isChecked():
            selected.append("HTML")
        if self.csv_checkbox.isChecked():
            selected.append("CSV")
        if self.pdf_checkbox.isChecked():
            selected.append("PDF")
        return tuple(selected)

    def _config_from_ui(self) -> JobConfig | None:
        source_text = self.source_edit.text().strip()
        output_text = self.output_edit.text().strip()
        if not source_text:
            QMessageBox.warning(self, "Missing source", "Select a source folder that exists.")
            return None
        if not output_text:
            QMessageBox.warning(self, "Missing output", "Select an output folder.")
            return None
        source = Path(source_text)
        output = Path(output_text)
        start = self.start_date_edit.date().toPyDate()
        end = self.end_date_edit.date().toPyDate()
        file_types = self._selected_file_types()
        search_text = self.search_edit.text().strip()
        case_sensitive = self.case_sensitive_checkbox.isChecked()
        if not source.is_dir():
            QMessageBox.warning(self, "Missing source", "Select a source folder that exists.")
            return None
        if not file_types:
            QMessageBox.warning(self, "Missing file type", "Select at least one file type.")
            return None
        if start > end:
            QMessageBox.warning(self, "Invalid date range", "Start date must be on or before end date.")
            return None
        if _norm_path(source) == _norm_path(output):
            QMessageBox.warning(self, "Invalid output", "Source and output folders must be different.")
            return None
        return JobConfig(source, output, start, end, file_types, search_text, case_sensitive)

    def _start(self) -> None:
        config = self._config_from_ui()
        if config is None:
            return
        self.log_edit.clear()
        self._append_log(f"Source: {config.source_dir}")
        self._append_log(f"Output: {config.output_dir}")
        self._append_log(f"Modified date range: {config.start_date.isoformat()} to {config.end_date.isoformat()}")
        self._append_log(f"File types: {', '.join(config.file_types)}")
        if config.search_text:
            mode = "case-sensitive" if config.case_sensitive else "case-insensitive"
            self._append_log(f"Text filter: {config.search_text!r} ({mode})")
        self.worker = CopyWorker(config)
        self.worker.phase_changed.connect(self._set_phase)
        self.worker.folder_changed.connect(self._set_folder)
        self.worker.file_changed.connect(self._set_file)
        self.worker.progress_changed.connect(self._set_progress)
        self.worker.counts_changed.connect(self._set_counts)
        self.worker.log_message.connect(self._append_log)
        self.worker.completed.connect(self._completed)
        self.worker.failed.connect(self._failed)
        self._set_busy(True)
        self.worker.start()

    def _cancel(self) -> None:
        if self.worker:
            self.worker.cancel()
            self.cancel_button.setEnabled(False)
            self._append_log("Cancel requested. Finishing the current safe step.")

    def _set_busy(self, busy: bool) -> None:
        self.start_button.setEnabled(not busy)
        self.cancel_button.setEnabled(busy)
        self.source_button.setEnabled(not busy)
        self.output_button.setEnabled(not busy)
        self.start_date_edit.setEnabled(not busy)
        self.end_date_edit.setEnabled(not busy)
        self.source_edit.setEnabled(not busy)
        self.output_edit.setEnabled(not busy)
        self.powerpoint_checkbox.setEnabled(not busy)
        self.excel_checkbox.setEnabled(not busy)
        self.word_checkbox.setEnabled(not busy)
        self.html_checkbox.setEnabled(not busy)
        self.csv_checkbox.setEnabled(not busy)
        self.search_edit.setEnabled(not busy)
        self.case_sensitive_checkbox.setEnabled(not busy)

    def _set_phase(self, value: str) -> None:
        self.phase_label.setText(value)

    def _set_folder(self, value: str) -> None:
        self.current_folder_label.setText(f"Folder: {value}")

    def _set_file(self, value: str) -> None:
        self.current_file_label.setText(f"File: {value}")

    def _set_progress(self, value: int, maximum: int, label: str) -> None:
        self.progress_bar.setRange(0, maximum)
        if maximum > 0:
            self.progress_bar.setValue(value)
        self.progress_bar.setFormat(label)

    def _set_counts(self, folders: int, files: int, matched: int, copied: int, errors: int) -> None:
        self.folders_count.setText(f"Folders: {folders}")
        self.files_count.setText(f"Files: {files}")
        self.matched_count.setText(f"Matched: {matched}")
        self.copied_count.setText(f"Copied: {copied}")
        self.errors_count.setText(f"Errors: {errors}")

    def _append_log(self, text: str) -> None:
        stamp = datetime.now().strftime("%H:%M:%S")
        self.log_edit.append(f"[{stamp}] {text}")

    def _completed(self, summary: JobSummary) -> None:
        self._set_busy(False)
        self.open_output_button.setEnabled(bool(summary.output_dir and summary.output_dir.exists()))
        if summary.cancelled:
            self._append_log("Cancelled.")
            return
        self._append_log(
            "Done: "
            f"{summary.copied_files}/{summary.matched_files} copied, "
            f"{summary.skipped_text} text misses, "
            f"{summary.skipped_unsupported_search} unsupported, "
            f"{summary.error_count} errors, {_fmt_bytes(summary.copied_bytes)} copied."
        )
        manifest_line = f"\nIndex: {summary.manifest_path.name}" if summary.manifest_path else ""
        QMessageBox.information(
            self,
            "Collection complete",
            (
                f"Copied {summary.copied_files} Office files.\n"
                f"Matched: {summary.matched_files}\n"
                f"Errors: {summary.error_count}\n"
                f"Output: {summary.output_dir}"
                f"{manifest_line}"
            ),
        )

    def _failed(self, details: str) -> None:
        self._set_busy(False)
        self._append_log(details)
        QMessageBox.critical(self, "Collection failed", details)

    def _open_output(self) -> None:
        output = Path(self.output_edit.text().strip())
        if output.exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(os.fspath(output)))

    def closeEvent(self, event) -> None:  # type: ignore[override]
        if self.worker and self.worker.isRunning():
            self.worker.cancel()
            self.worker.wait(3000)
        super().closeEvent(event)


def run_app(argv: Sequence[str] | None = None) -> int:
    app = QApplication(list(argv or sys.argv[:1]))
    window = OfficeDateCollectorWindow()
    window.show()
    return app.exec()


def _touch(path: Path, when: datetime) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"office")
    ts = when.timestamp()
    os.utime(path, (ts, ts))


def self_test() -> int:
    now = datetime.now()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        source = root / "source"
        output = root / "output"
        _touch(source / "a" / "deck.pptx", now)
        _touch(source / "b" / "deck.pptx", now)
        _touch(source / "book.xlsx", now)
        _touch(source / "macro.xlsm", now)
        _touch(source / "doc.docx", now)
        _touch(source / "~$lock.docx", now)
        _touch(source / "old" / "old.pptx", now - timedelta(days=30))
        _touch(source / "template.potx", now)
        config = JobConfig(source, output, (now - timedelta(days=1)).date(), now.date())
        summary = collect_office_files(config)
        assert summary.matched_files == 5, summary
        assert summary.copied_files == 5, summary
        copied = sorted(path.name for path in output.iterdir())
        assert copied == ["book.xlsx", MANIFEST_FILENAME, "deck.pptx", "deck_1.pptx", "doc.docx", "macro.xlsm"], copied
        assert summary.manifest_path == output / MANIFEST_FILENAME, summary
    print("Office Date Collector self-test passed.")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Collect Office files by modified date.")
    parser.add_argument("--self-test", action="store_true", help="Run a no-GUI smoke test and exit.")
    parser.add_argument("--version", action="store_true", help="Print version text and exit.")
    args, remaining = parser.parse_known_args(argv)
    if args.version:
        print("Office Date Collector")
        return 0
    if args.self_test:
        return self_test()
    return run_app(remaining)


if __name__ == "__main__":
    raise SystemExit(main())

# Purpose: Capture external canvas input and classify shared paste/drop insertion choices.
# Map: feature_routes/clipboard_undo_redo_mutation_history.md
# Tests: tests/test_canvas_import_inputs.py
from __future__ import annotations

import csv
import hashlib
import html
import json
import re
from collections.abc import Iterable
from dataclasses import dataclass, replace
from html.parser import HTMLParser
from io import StringIO
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from PyQt6.QtCore import QBuffer, QByteArray, QIODevice, QMimeData, QUrl
from PyQt6.QtGui import QImage

from ea_node_editor.nodes.builtins.passive_annotation import PASSIVE_ANNOTATION_TEXT_TYPE_ID
from ea_node_editor.nodes.builtins.media_panel import MEDIA_PANEL_TYPE_ID
from ea_node_editor.nodes.builtins.data_control import PANEL_MODE_TEXT
from ea_node_editor.nodes.builtins.passive_mail import (
    PASSIVE_MEDIA_MAIL_PANEL_TYPE_ID,
)
from ea_node_editor.nodes.file_dialog_filters import (
    MAIL_FILE_SUFFIXES,
    media_kind_from_source,
)
from ea_node_editor.nodes.builtins.web_viewer import (
    WEB_PAGE_VIEWER_START_LOCATION_PROPERTY,
    WEB_PAGE_VIEWER_TYPE_ID,
)
from ea_node_editor.ui.shell.runtime_clipboard import GRAPH_FRAGMENT_MIME_TYPE, parse_graph_fragment_payload

_MEDIA_SOURCE_PROPERTY = "source"
_SOURCE_PATH_PROPERTY = "source_path"
_TEXT_PROPERTY = "text"
_TEXT_FORMAT_PROPERTY = "format"
_TABULAR_INPUT_NODE_TYPE_ID = "tabular.input"
_TABULAR_INPUT_PATH_PROPERTY = "path"

_MAIL_SUFFIXES = frozenset(MAIL_FILE_SUFFIXES)
_HTML_SUFFIXES = frozenset({".html", ".htm", ".xhtml"})

_IMAGE_MIME_SUFFIXES = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/bmp": ".bmp",
    "image/gif": ".gif",
    "image/webp": ".webp",
    "image/svg+xml": ".svg",
    "image/tiff": ".tiff",
}
_VIDEO_MIME_SUFFIXES = {
    "video/mp4": ".mp4",
    "video/x-m4v": ".m4v",
    "video/quicktime": ".mov",
    "video/x-msvideo": ".avi",
    "video/x-matroska": ".mkv",
    "video/webm": ".webm",
    "video/x-ms-wmv": ".wmv",
}


@dataclass(frozen=True, slots=True)
class ClipboardBytePayload:
    property_key: str
    data: bytes
    filename: str
    mime_type: str
    artifact_prefix: str
    subdirectory: str
    artifact_kind: str

    def signature_payload(self) -> dict[str, Any]:
        return {
            "property_key": self.property_key,
            "filename": self.filename,
            "mime_type": self.mime_type,
            "artifact_prefix": self.artifact_prefix,
            "subdirectory": self.subdirectory,
            "artifact_kind": self.artifact_kind,
            "size": len(self.data),
            "sha256": hashlib.sha256(self.data).hexdigest(),
        }


@dataclass(frozen=True, slots=True)
class ClipboardPasteItem:
    type_id: str
    properties: dict[str, Any]
    artifact: ClipboardBytePayload | None = None

    def signature_payload(self) -> dict[str, Any]:
        return {
            "type_id": self.type_id,
            "properties": self.properties,
            "artifact": None if self.artifact is None else self.artifact.signature_payload(),
        }


@dataclass(frozen=True, slots=True)
class ClipboardTablePasteItems:
    tabular: ClipboardPasteItem
    markdown: ClipboardPasteItem


@dataclass(frozen=True, slots=True)
class CanvasImportLocation:
    """A copied location with URL spelling and filesystem identity kept separate."""

    value: str
    local_path: str = ""
    is_folder: bool = False


@dataclass(frozen=True, slots=True)
class CanvasImportSnapshot:
    """Owned values only: no clipboard, QMimeData, QImage, or staging lifetime."""

    locations: tuple[CanvasImportLocation, ...] = ()
    text: str = ""
    html: str = ""
    media: tuple[ClipboardBytePayload, ...] = ()
    graph_fragment: bytes | None = None


@dataclass(frozen=True, slots=True)
class CanvasImportChoice:
    key: str
    label: str
    item: ClipboardPasteItem | None
    explanation: str = ""


@dataclass(frozen=True, slots=True)
class CanvasImportSource:
    label: str
    detected_choice: str
    choices: tuple[CanvasImportChoice, ...]

    def choice(self, key: str) -> CanvasImportChoice:
        for choice in self.choices:
            if choice.key == key:
                return choice
        raise KeyError(key)


def capture_canvas_mime_data(mime_data: QMimeData | None) -> CanvasImportSnapshot:
    """Snapshot every useful MIME representation before a modal chooser can open."""
    if mime_data is None:
        return CanvasImportSnapshot()
    image_item = _image_item_from_qimage(mime_data)
    media = list(_byte_payloads_from_mime_data(mime_data))
    if image_item is not None and image_item.artifact is not None:
        media.insert(0, image_item.artifact)
    # Qt synthesizes decoded text for URI lists even without a plain-text MIME
    # representation. Keep the captured URL for those cases, not this fallback.
    has_plain_text = any(
        str(mime_type).split(";", 1)[0].lower() == "text/plain"
        for mime_type in mime_data.formats()
    )
    locations = tuple(_capture_location(url) for url in mime_data.urls())
    if not locations and mime_data.hasFormat("application/x-corex-path-pointer"):
        try:
            payload = json.loads(bytes(mime_data.data("application/x-corex-path-pointer")))
            properties = payload.get("properties") if isinstance(payload, dict) else None
            if (payload.get("type_id") == "io.path_pointer" and isinstance(properties, dict)
                    and isinstance(properties.get("path"), str)):
                locations = (_capture_location(properties["path"], is_folder=properties.get("mode") == "folder"),)
        except (ValueError, TypeError, AttributeError):
            pass
    return CanvasImportSnapshot(
        locations=locations,
        text=(
            str(mime_data.text() or "")
            if mime_data.hasText() and (has_plain_text or not mime_data.hasUrls()) else ""
        ),
        html=str(mime_data.html() or "") if mime_data.hasHtml() else "",
        media=tuple(media),
        graph_fragment=(
            bytes(mime_data.data(GRAPH_FRAGMENT_MIME_TYPE))
            if mime_data.hasFormat(GRAPH_FRAGMENT_MIME_TYPE) else None
        ),
    )


def capture_canvas_drop(
    urls: Iterable[str | QUrl] = (),
    *,
    text: str = "",
    html: str = "",
    folder_hints: Iterable[bool] = (),
) -> CanvasImportSnapshot:
    """Capture a QML drop's full URL/path list without converting HTTP to paths.

    ``folder_hints`` aligns with ``urls`` for Folder Explorer entries; real local
    directories are also detected. Native MIME drops use capture_canvas_mime_data.
    """
    hints = tuple(folder_hints)
    return CanvasImportSnapshot(
        locations=tuple(
            _capture_location(value, is_folder=hints[index] if index < len(hints) else False)
            for index, value in enumerate(urls)
        ),
        text=str(text),
        html=str(html),
    )


def classify_canvas_import(snapshot: CanvasImportSnapshot) -> tuple[CanvasImportSource, ...]:
    """Apply one automatic mapping and keep chooser alternatives on each source."""
    if snapshot.graph_fragment is not None or parse_graph_fragment_payload(snapshot.text) is not None:
        return ()
    locations = tuple(location for location in snapshot.locations if location.value)
    if any(location.local_path for location in locations):
        return tuple(_source_from_location(location) for location in locations)

    rows = _table_rows_from_content(snapshot.text, snapshot.html)
    if rows:
        table = _table_paste_items(rows)
        literal = snapshot.text or _rows_to_tsv_bytes(rows).decode("utf-8")
        source = _source_with_text_choices(
            "Copied table", "tabular", [
                CanvasImportChoice("tabular", "Tabular Data Input", table.tabular),
                CanvasImportChoice("markdown_table", "Markdown Table", table.markdown),
            ], literal,
        )
        return (_with_location_choices(source, locations),)

    # A browser source URL can accompany selected HTML/image content. Treat that
    # URL as an alternative; direct URL drops and URL batches remain locations.
    if locations and (len(locations) > 1 or not snapshot.html.strip()):
        return tuple(
            _source_from_location(
                location,
                literal=snapshot.text if len(locations) == 1 and snapshot.html and snapshot.text else None,
                raw_html=snapshot.html if len(locations) == 1 else "",
            )
            for location in locations
        )
    if snapshot.media:
        artifact = snapshot.media[0]
        item = ClipboardPasteItem(MEDIA_PANEL_TYPE_ID, {}, artifact)
        choices = [CanvasImportChoice("media", "Media Panel", item)]
        markdown = html_to_markdownish(snapshot.html) if snapshot.html else ""
        if markdown:
            choices.append(_formatted_text_choice(markdown))
        literal = snapshot.text or markdown or (locations[0].value if locations else "")
        source = _source_with_text_choices(
            artifact.filename, "media", choices, literal,
            artifact=None if literal else artifact,
        )
        return (_with_location_choices(source, locations),)

    text_location = _location_from_text(snapshot.text)
    if text_location is not None:
        source = _source_from_location(text_location, literal=snapshot.text, raw_html=snapshot.html)
        return (_with_location_choices(source, locations),)

    if snapshot.html.strip():
        href = _single_remote_href_from_html(snapshot.html)
        if href is not None:
            source = _source_from_location(
                CanvasImportLocation(href),
                literal=snapshot.text or html_to_markdownish(snapshot.html),
                raw_html=snapshot.html,
            )
            return (_with_location_choices(source, locations),)
        markdown = html_to_markdownish(snapshot.html)
        if markdown:
            source = _source_with_text_choices(
                _text_label(snapshot.text or markdown), "formatted_text",
                [_formatted_text_choice(markdown)], snapshot.text or markdown,
            )
            return (_with_location_choices(source, locations),)
    if snapshot.text.strip():
        source = _source_with_text_choices(_text_label(snapshot.text), "text", [], snapshot.text)
        return (_with_location_choices(source, locations),)
    if locations:
        return tuple(_source_from_location(location) for location in locations)
    return ()




def _table_paste_items(rows: tuple[tuple[str, ...], ...]) -> ClipboardTablePasteItems:
    return ClipboardTablePasteItems(
        tabular=ClipboardPasteItem(
            type_id=_TABULAR_INPUT_NODE_TYPE_ID,
            properties={},
            artifact=ClipboardBytePayload(
                property_key=_TABULAR_INPUT_PATH_PROPERTY,
                data=_rows_to_tsv_bytes(rows),
                filename="clipboard-table.tsv",
                mime_type="text/tab-separated-values",
                artifact_prefix="clipboard_table",
                subdirectory="tabular",
                artifact_kind="clipboard_table_source",
            ),
        ),
        markdown=ClipboardPasteItem(
            type_id=PASSIVE_ANNOTATION_TEXT_TYPE_ID,
            properties={
                _TEXT_PROPERTY: _rows_to_markdown_table(rows),
                _TEXT_FORMAT_PROPERTY: "markdown",
            },
        ),
    )


def clipboard_paste_items_signature(items: tuple[ClipboardPasteItem, ...]) -> str:
    if not items:
        return ""
    return json.dumps(
        [item.signature_payload() for item in items],
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def html_to_markdownish(raw_html: str) -> str:
    parser = _MarkdownishHTMLParser()
    try:
        parser.feed(str(raw_html or ""))
        parser.close()
    except Exception:  # noqa: BLE001
        return ""
    return _normalize_markdownish_text(parser.text())


def _table_rows_from_content(text: str, raw_html: str) -> tuple[tuple[str, ...], ...]:
    if "\t" in text:
        normalized_text = text.replace("\r\n", "\n").replace("\r", "\n")
        rows = _normalize_table_rows(csv.reader(StringIO(normalized_text), delimiter="\t"))
        if rows:
            return rows
    if raw_html.strip():
        return _table_rows_from_html(raw_html)
    return ()


def _table_rows_from_html(raw_html: str) -> tuple[tuple[str, ...], ...]:
    parser = _TableHTMLParser()
    try:
        parser.feed(str(raw_html or ""))
        parser.close()
    except Exception:  # noqa: BLE001
        return ()
    for rows in parser.tables:
        normalized = _normalize_table_rows(rows)
        if normalized:
            return normalized
    return ()


def _normalize_table_rows(rows: Any) -> tuple[tuple[str, ...], ...]:
    normalized = [tuple(str(cell) for cell in row) for row in rows if row]
    while normalized and not any(cell.strip() for cell in normalized[-1]):
        normalized.pop()
    if not normalized:
        return ()
    width = max(len(row) for row in normalized)
    if width < 2 and len(normalized) < 2:
        return ()
    return tuple(tuple(row[index] if index < len(row) else "" for index in range(width)) for row in normalized)


def _rows_to_tsv_bytes(rows: tuple[tuple[str, ...], ...]) -> bytes:
    stream = StringIO()
    writer = csv.writer(stream, delimiter="\t", lineterminator="\n")
    writer.writerows(rows)
    return stream.getvalue().encode("utf-8")


def _rows_to_markdown_table(rows: tuple[tuple[str, ...], ...]) -> str:
    header, *body = rows
    lines = [
        _markdown_row(header),
        _markdown_row(["---"] * len(header)),
    ]
    lines.extend(_markdown_row(row) for row in body)
    return "\n".join(lines)


def _markdown_row(row: Any) -> str:
    return "| " + " | ".join(_markdown_cell(cell) for cell in row) + " |"


def _markdown_cell(value: Any) -> str:
    return str(value).replace("|", r"\|").replace("\r\n", "\n").replace("\r", "\n").replace("\n", "<br>")


def _single_remote_href_from_html(raw_html: str) -> str | None:
    parser = _HrefHTMLParser()
    try:
        parser.feed(str(raw_html or ""))
        parser.close()
    except Exception:  # noqa: BLE001
        return None
    urls: list[str] = []
    seen: set[str] = set()
    for href in parser.hrefs:
        normalized = html.unescape(str(href or "")).strip()
        if not _is_remote_url(normalized) or normalized in seen:
            continue
        seen.add(normalized)
        urls.append(normalized)
    return urls[0] if len(urls) == 1 else None


def _capture_location(value: str | QUrl, *, is_folder: bool = False) -> CanvasImportLocation:
    url = value if isinstance(value, QUrl) else QUrl(str(value))
    literal = (
        str(url.toString(QUrl.ComponentFormattingOption.FullyEncoded))
        if isinstance(value, QUrl) else str(value)
    )
    if url.isLocalFile():
        path = str(url.toLocalFile() or "")
        return CanvasImportLocation(literal, path, bool(is_folder) or _is_directory(path))
    # QML Folder Explorer sends raw filesystem paths, including Windows drives.
    if literal and (not url.scheme() or re.match(r"^[A-Za-z]:[\\/]", literal)):
        return CanvasImportLocation(literal, literal, bool(is_folder) or _is_directory(literal))
    return CanvasImportLocation(literal)


def _is_directory(path: str) -> bool:
    try:
        return Path(path).is_dir()
    except (OSError, ValueError):
        return False


def _location_from_text(text: str) -> CanvasImportLocation | None:
    normalized = text.strip()
    if not normalized:
        return None
    url = QUrl(normalized)
    if url.isLocalFile():
        return _capture_location(normalized)
    return CanvasImportLocation(normalized) if _is_remote_url(normalized) else None


def _is_remote_url(value: str) -> bool:
    if any(character.isspace() for character in value):
        return False
    try:
        parsed = urlsplit(value)
        parsed.port
        return parsed.scheme.lower() in {"http", "https"} and bool(parsed.hostname)
    except ValueError:
        return False


def _source_from_location(
    location: CanvasImportLocation, *, literal: str | None = None, raw_html: str = "",
) -> CanvasImportSource:
    value = location.local_path or location.value
    path_choice = CanvasImportChoice(
        "path", "Path Pointer", ClipboardPasteItem(
            "io.path_pointer", {"path": value, "mode": "folder" if location.is_folder else "file"},
        ),
    ) if location.local_path else None
    if location.is_folder:
        detected = path_choice
    elif media_kind_from_source(value):
        detected = CanvasImportChoice("media", "Media Panel", ClipboardPasteItem(
            MEDIA_PANEL_TYPE_ID, {_MEDIA_SOURCE_PROPERTY: value},
        ))
    elif location.local_path and Path(value).suffix.lower() in _MAIL_SUFFIXES:
        detected = CanvasImportChoice("mail", "Mail Panel", ClipboardPasteItem(
            PASSIVE_MEDIA_MAIL_PANEL_TYPE_ID, {_SOURCE_PATH_PROPERTY: value},
        ))
    elif _is_remote_url(value) or (location.local_path and Path(value).suffix.lower() in _HTML_SUFFIXES):
        detected = CanvasImportChoice("web", "Web Viewer", ClipboardPasteItem(
            WEB_PAGE_VIEWER_TYPE_ID, {WEB_PAGE_VIEWER_START_LOCATION_PROPERTY: value},
        ))
    else:
        detected = path_choice
    choices = [detected] if detected is not None else []
    if path_choice is not None and detected is not path_choice:
        choices.append(path_choice)
    markdown = html_to_markdownish(raw_html) if raw_html else ""
    if markdown:
        choices.append(_formatted_text_choice(markdown))
    return _source_with_text_choices(
        value, detected.key if detected is not None else "text", choices,
        value if literal is None else literal,
    )


def _text_label(text: str) -> str:
    preview = " ".join(text.split())
    return preview if len(preview) <= 100 else preview[:97] + "..."


def _with_location_choices(
    source: CanvasImportSource, locations: tuple[CanvasImportLocation, ...],
) -> CanvasImportSource:
    """Keep browser source URLs selectable even when copied content wins."""
    choices = list(source.choices)
    for index, location in enumerate(locations):
        location_source = _source_from_location(location)
        choice = location_source.choice(location_source.detected_choice)
        if any(existing.item == choice.item for existing in choices):
            continue
        if any(existing.key == choice.key for existing in choices):
            choice = replace(
                choice, key=f"source_url_{index}", label=f"{choice.label} (source URL)",
                explanation=location.value,
            )
        choices.insert(-1, choice)
    return replace(source, choices=tuple(choices))


def _formatted_text_choice(markdown: str) -> CanvasImportChoice:
    return CanvasImportChoice("formatted_text", "Text Annotation (formatted)", ClipboardPasteItem(
        PASSIVE_ANNOTATION_TEXT_TYPE_ID, {_TEXT_PROPERTY: markdown, _TEXT_FORMAT_PROPERTY: "markdown"},
    ))


def _source_with_text_choices(
    label: str,
    detected_choice: str,
    choices: list[CanvasImportChoice],
    literal: str,
    *,
    artifact: ClipboardBytePayload | None = None,
) -> CanvasImportSource:
    explanation = (
        "Saves an internal project copy and inserts its managed reference."
        if artifact is not None else ""
    )
    choices.extend((
        CanvasImportChoice("text", "Plain Text Annotation", ClipboardPasteItem(
            PASSIVE_ANNOTATION_TEXT_TYPE_ID,
            {_TEXT_PROPERTY: literal, _TEXT_FORMAT_PROPERTY: "plain"},
            replace(artifact, property_key=_TEXT_PROPERTY) if artifact is not None else None,
        ), explanation),
        CanvasImportChoice("panel", "Panel", ClipboardPasteItem(
            "data.panel", {"value": literal, "mode": PANEL_MODE_TEXT, "interpretation": "text"},
            replace(artifact, property_key="value") if artifact is not None else None,
        ), explanation),
        CanvasImportChoice("skip", "Skip", None),
    ))
    return CanvasImportSource(label, detected_choice, tuple(choices))


def _image_item_from_qimage(mime_data: QMimeData) -> ClipboardPasteItem | None:
    if not mime_data.hasImage():
        return None
    image_data = mime_data.imageData()
    image: QImage | None = None
    if isinstance(image_data, QImage):
        image = image_data
    elif hasattr(image_data, "toImage"):
        candidate = image_data.toImage()
        if isinstance(candidate, QImage):
            image = candidate
    if image is None or image.isNull():
        return None
    data = _qimage_to_png_bytes(image)
    if not data:
        return None
    return ClipboardPasteItem(
        type_id=MEDIA_PANEL_TYPE_ID,
        properties={},
        artifact=ClipboardBytePayload(
            property_key=_MEDIA_SOURCE_PROPERTY,
            data=data,
            filename="clipboard-image.png",
            mime_type="image/png",
            artifact_prefix="clipboard_image",
            subdirectory="media",
            artifact_kind="clipboard_image_source",
        ),
    )


def _qimage_to_png_bytes(image: QImage) -> bytes:
    buffer_data = QByteArray()
    buffer = QBuffer(buffer_data)
    if not buffer.open(QIODevice.OpenModeFlag.WriteOnly):
        return b""
    try:
        if not image.save(buffer, "PNG", 100):
            return b""
        return bytes(buffer_data)
    finally:
        buffer.close()


def _byte_payloads_from_mime_data(mime_data: QMimeData) -> tuple[ClipboardBytePayload, ...]:
    payloads: list[ClipboardBytePayload] = []
    for mime_type in mime_data.formats():
        normalized_mime = str(mime_type or "").strip().lower()
        target = _target_for_mime_type(normalized_mime)
        if target is None:
            continue
        raw_data = bytes(mime_data.data(mime_type))
        if not raw_data:
            continue
        _type_id, property_key, filename, artifact_prefix, subdirectory, artifact_kind = target
        payloads.append(ClipboardBytePayload(
            property_key=property_key,
            data=raw_data,
            filename=filename,
            mime_type=normalized_mime,
            artifact_prefix=artifact_prefix,
            subdirectory=subdirectory,
            artifact_kind=artifact_kind,
        ))
    return tuple(payloads)


def _target_for_mime_type(mime_type: str) -> tuple[str, str, str, str, str, str] | None:
    if mime_type == "application/pdf":
        return (
            MEDIA_PANEL_TYPE_ID,
            _MEDIA_SOURCE_PROPERTY,
            "clipboard-document.pdf",
            "clipboard_pdf",
            "media",
            "clipboard_pdf_source",
        )
    if mime_type in _IMAGE_MIME_SUFFIXES:
        suffix = _IMAGE_MIME_SUFFIXES[mime_type]
        return (
            MEDIA_PANEL_TYPE_ID,
            _MEDIA_SOURCE_PROPERTY,
            f"clipboard-image{suffix}",
            "clipboard_image",
            "media",
            "clipboard_image_source",
        )
    if mime_type in _VIDEO_MIME_SUFFIXES:
        suffix = _VIDEO_MIME_SUFFIXES[mime_type]
        return (
            MEDIA_PANEL_TYPE_ID,
            _MEDIA_SOURCE_PROPERTY,
            f"clipboard-video{suffix}",
            "clipboard_video",
            "media",
            "clipboard_video_source",
        )
    return None


class _MarkdownishHTMLParser(HTMLParser):
    _BLOCK_TAGS = {
        "address",
        "article",
        "aside",
        "blockquote",
        "div",
        "dl",
        "dt",
        "dd",
        "figcaption",
        "figure",
        "footer",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "header",
        "main",
        "ol",
        "p",
        "pre",
        "section",
        "table",
        "tr",
        "ul",
    }
    _SKIP_TAGS = {"script", "style", "noscript"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, _attrs: list[tuple[str, str | None]]) -> None:
        normalized = tag.lower()
        if normalized in self._SKIP_TAGS:
            self._skip_depth += 1
            return
        if self._skip_depth:
            return
        if normalized == "br":
            self._parts.append("\n")
        elif normalized == "li":
            self._parts.append("\n- ")
        elif normalized in self._BLOCK_TAGS:
            self._parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        normalized = tag.lower()
        if normalized in self._SKIP_TAGS:
            self._skip_depth = max(0, self._skip_depth - 1)
            return
        if self._skip_depth:
            return
        if normalized in self._BLOCK_TAGS or normalized == "li":
            self._parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        self._parts.append(html.unescape(data))

    def text(self) -> str:
        return "".join(self._parts)


class _HrefHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.hrefs: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        for key, value in attrs:
            if key.lower() == "href" and value:
                self.hrefs.append(value)
                return


class _TableHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tables: list[list[list[str]]] = []
        self._table_depth = 0
        self._current_table: list[list[str]] | None = None
        self._current_row: list[str] | None = None
        self._current_cell: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        normalized = tag.lower()
        if normalized == "table":
            if self._table_depth == 0:
                self._current_table = []
            self._table_depth += 1
            return
        if self._table_depth != 1:
            return
        if normalized == "tr":
            self._current_row = []
        elif normalized in {"td", "th"} and self._current_row is not None:
            self._current_cell = []
        elif normalized == "br" and self._current_cell is not None:
            self._current_cell.append("\n")

    def handle_endtag(self, tag: str) -> None:
        normalized = tag.lower()
        if normalized in {"td", "th"} and self._current_cell is not None and self._current_row is not None:
            self._current_row.append(_normalize_cell_text("".join(self._current_cell)))
            self._current_cell = None
            return
        if normalized == "tr" and self._current_row is not None and self._current_table is not None:
            self._current_table.append(self._current_row)
            self._current_row = None
            return
        if normalized == "table" and self._table_depth:
            self._table_depth -= 1
            if self._table_depth == 0 and self._current_table is not None:
                self.tables.append(self._current_table)
                self._current_table = None

    def handle_data(self, data: str) -> None:
        if self._current_cell is not None:
            self._current_cell.append(data)


def _normalize_cell_text(text: str) -> str:
    normalized = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
    return re.sub(r"[ \t\f\v]+", " ", normalized).strip()


def _normalize_markdownish_text(text: str) -> str:
    lines = [
        re.sub(r"[ \t\f\v]+", " ", line).strip()
        for line in str(text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    ]
    normalized_lines: list[str] = []
    previous_blank = True
    for line in lines:
        if not line:
            if not previous_blank:
                normalized_lines.append("")
            previous_blank = True
            continue
        normalized_lines.append(line)
        previous_blank = False
    while normalized_lines and not normalized_lines[-1]:
        normalized_lines.pop()
    return "\n".join(normalized_lines).strip()


__all__ = [
    "CanvasImportChoice",
    "CanvasImportLocation",
    "CanvasImportSnapshot",
    "CanvasImportSource",
    "ClipboardBytePayload",
    "ClipboardPasteItem",
    "ClipboardTablePasteItems",
    "capture_canvas_drop",
    "capture_canvas_mime_data",
    "classify_canvas_import",
    "clipboard_paste_items_signature",
    "html_to_markdownish",
]

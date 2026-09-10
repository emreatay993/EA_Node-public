from __future__ import annotations

import os
from pathlib import PurePath
import re
from urllib.parse import unquote, urlsplit

from ea_node_editor.common.scene_protocol import CAD_SCENE_SUFFIXES, FE_SCENE_SUFFIXES

ALL_FILES_FILTER = "All Files (*)"
IMAGE_FILE_SUFFIXES = (
    ".png",
    ".jpg",
    ".jpeg",
    ".bmp",
    ".gif",
    ".webp",
    ".svg",
    ".tif",
    ".tiff",
)
PDF_FILE_SUFFIXES = (".pdf",)
VIDEO_FILE_SUFFIXES = (".mp4", ".m4v", ".mov", ".avi", ".mkv", ".webm", ".wmv")
MEDIA_FILE_SUFFIXES = IMAGE_FILE_SUFFIXES + PDF_FILE_SUFFIXES + VIDEO_FILE_SUFFIXES
_PROJECT_MEDIA_REF = re.compile(r"^(?:saved|temp)://[A-Za-z0-9][A-Za-z0-9._-]*$")
_URI_SCHEME = re.compile(r"^(?P<scheme>[A-Za-z][A-Za-z0-9+.-]*):")
_WINDOWS_DRIVE_PATH = re.compile(r"^[A-Za-z]:")


def media_kind_from_source(source: object) -> str:
    if isinstance(source, os.PathLike):
        try:
            text = os.fspath(source)
        except (OSError, TypeError, ValueError):
            return ""
        if not isinstance(text, str):
            return ""
    elif type(source) is str:
        text = source
    else:
        return ""
    text = text.strip()
    if not text or _PROJECT_MEDIA_REF.fullmatch(text):
        return ""
    scheme_match = None if _WINDOWS_DRIVE_PATH.match(text) else _URI_SCHEME.match(text)
    if scheme_match is not None:
        if not text.startswith(f"{scheme_match['scheme']}://"):
            return ""
        try:
            parsed = urlsplit(text)
        except ValueError:
            return ""
        if parsed.scheme.casefold() not in {"file", "http", "https"}:
            return ""
        if parsed.scheme.casefold() in {"http", "https"}:
            try:
                if not parsed.netloc or parsed.hostname is None:
                    return ""
                parsed.port
            except ValueError:
                return ""
        text = unquote(parsed.path)
    elif "://" in text:
        return ""
    suffix = PurePath(text.replace("\\", "/")).suffix.casefold()
    if suffix in IMAGE_FILE_SUFFIXES:
        return "image"
    if suffix in PDF_FILE_SUFFIXES:
        return "pdf"
    if suffix in VIDEO_FILE_SUFFIXES:
        return "video"
    return ""


def is_supported_media_source_reference(source: object) -> bool:
    if type(source) is str and _PROJECT_MEDIA_REF.fullmatch(source.strip()):
        return True
    return bool(media_kind_from_source(source))


TEXT_FILES_FILTER = (
    "Text/Data Files (*.txt *.md *.csv *.json *.jsonl *.yaml *.yml *.log);;"
    f"{ALL_FILES_FILTER}"
)
SPREADSHEET_FILES_FILTER = f"Spreadsheet Files (*.csv *.xlsx *.xlsm);;{ALL_FILES_FILTER}"
TABULAR_DATA_FILES_FILTER = (
    "Tabular Data (*.csv *.tsv *.txt *.xlsx *.xlsm *.parquet *.h5 *.hdf *.hdf5 *.npy *.npz);;"
    f"{ALL_FILES_FILTER}"
)
TABULAR_TABLE_OUTPUT_FILES_FILTER = (
    "Table Output (*.csv *.tsv *.txt *.jsonl *.xlsx *.xlsm);;"
    f"{ALL_FILES_FILTER}"
)
TABULAR_ARRAY_OUTPUT_FILES_FILTER = (
    "Array Output (*.csv *.tsv *.txt *.xlsx *.xlsm *.npy);;"
    f"{ALL_FILES_FILTER}"
)
IMAGE_FILES_FILTER = (
    f"Image Files (*{' *'.join(IMAGE_FILE_SUFFIXES)});;{ALL_FILES_FILTER}"
)
PDF_FILES_FILTER = f"PDF Files (*{' *'.join(PDF_FILE_SUFFIXES)});;{ALL_FILES_FILTER}"
VIDEO_FILES_FILTER = (
    f"Video Files (*{' *'.join(VIDEO_FILE_SUFFIXES)});;{ALL_FILES_FILTER}"
)
MEDIA_FILES_FILTER = (
    f"Media Files (*{' *'.join(MEDIA_FILE_SUFFIXES)});;{ALL_FILES_FILTER}"
)
MAIL_FILE_SUFFIXES = (".eml", ".msg", ".oft")
MAIL_FILES_FILTER = f"Mail Files (*{' *'.join(MAIL_FILE_SUFFIXES)});;{ALL_FILES_FILTER}"
WEB_PAGE_FILES_FILTER = "Web Page Files (*.html *.htm *.xhtml);;" f"{ALL_FILES_FILTER}"
NOTEBOOK_FILES_FILTER = f"Jupyter Notebook (*.ipynb);;{ALL_FILES_FILTER}"
SCRIPT_FILES_FILTER = (
    "Script Files (*.sh *.bash *.slurm *.pbs *.lsf *.cmd *.bat *.ps1);;"
    f"{ALL_FILES_FILTER}"
)
FE_SCENE_FILES_FILTER = (
    f"Neutral FE Files (*{' *'.join(FE_SCENE_SUFFIXES)});;{ALL_FILES_FILTER}"
)
CAD_SCENE_FILES_FILTER = (
    f"Neutral CAD Files (*{' *'.join(CAD_SCENE_SUFFIXES)});;{ALL_FILES_FILTER}"
)


__all__ = [
    "ALL_FILES_FILTER",
    "CAD_SCENE_FILES_FILTER",
    "FE_SCENE_FILES_FILTER",
    "IMAGE_FILE_SUFFIXES",
    "IMAGE_FILES_FILTER",
    "MAIL_FILE_SUFFIXES",
    "MAIL_FILES_FILTER",
    "MEDIA_FILE_SUFFIXES",
    "MEDIA_FILES_FILTER",
    "NOTEBOOK_FILES_FILTER",
    "PDF_FILE_SUFFIXES",
    "PDF_FILES_FILTER",
    "SCRIPT_FILES_FILTER",
    "SPREADSHEET_FILES_FILTER",
    "TABULAR_ARRAY_OUTPUT_FILES_FILTER",
    "TABULAR_DATA_FILES_FILTER",
    "TABULAR_TABLE_OUTPUT_FILES_FILTER",
    "TEXT_FILES_FILTER",
    "VIDEO_FILE_SUFFIXES",
    "VIDEO_FILES_FILTER",
    "WEB_PAGE_FILES_FILTER",
    "is_supported_media_source_reference",
    "media_kind_from_source",
]

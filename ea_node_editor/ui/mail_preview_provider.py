from __future__ import annotations

from copy import deepcopy
import email
from email.message import EmailMessage, Message
from email import policy
from functools import lru_cache
import hashlib
import html as html_lib
import mimetypes
from pathlib import Path
import re
import sys
from typing import Any, Callable
from urllib.parse import unquote

from PyQt6.QtCore import QUrl

from ea_node_editor.nodes.file_dialog_filters import MAIL_FILE_SUFFIXES
from ea_node_editor.persistence.artifact_resolution import ProjectArtifactResolver
from ea_node_editor.settings import user_data_dir

_PreviewProjectContext = tuple[str | Path | None, dict[str, Any] | None]
_PreviewProjectContextProvider = Callable[[], _PreviewProjectContext | None]
_project_context_provider: _PreviewProjectContextProvider | None = None
_OUTLOOK_HTML_FORMAT = 5
_SCRIPT_BLOCK_RE = re.compile(r"<script\b[^>]*>.*?</script\s*>", re.IGNORECASE | re.DOTALL)
_MAIL_PREVIEW_CACHE_SIZE = 32


class _UncacheableMailPreview(Exception):
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload


def set_mail_preview_project_context_provider(
    provider: _PreviewProjectContextProvider | None,
) -> None:
    global _project_context_provider
    _project_context_provider = provider


def _preview_resolver() -> ProjectArtifactResolver:
    context = _project_context_provider() if callable(_project_context_provider) else None
    project_path: str | Path | None = None
    project_metadata: dict[str, Any] | None = None
    if isinstance(context, tuple) and len(context) >= 2:
        project_path = context[0]
        metadata = context[1]
        if isinstance(metadata, dict):
            project_metadata = metadata
    return ProjectArtifactResolver(
        project_path=project_path,
        project_metadata=project_metadata,
    )


def _mail_preview_cache_dir() -> Path:
    path = user_data_dir() / "mail_preview_cache"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _source_stats(path: Path) -> tuple[int, int] | None:
    try:
        stats = path.stat()
    except OSError:
        return None
    return int(stats.st_mtime_ns), int(stats.st_size)


def _cache_key(path: Path, stamp: str) -> str:
    payload = f"{path.resolve(strict=False)}|{stamp}".encode("utf-8", errors="surrogatepass")
    return hashlib.sha256(payload).hexdigest()[:24]


def _preview_url(path: Path) -> str:
    return QUrl.fromLocalFile(str(path)).toString()


def _blank_payload(message: str) -> dict[str, Any]:
    return {
        "state": "placeholder",
        "message": message,
        "source_path": "",
        "resolved_source_url": "",
        "preview_url": "",
        "metadata": {},
        "attachments": [],
        "attachment_summary": "No attachments",
        "file_stamp_token": "",
    }


def _error_payload(source: str, message: str, *, state: str = "error") -> dict[str, Any]:
    return {
        "state": state,
        "message": message,
        "source_path": str(source or "").strip(),
        "resolved_source_url": "",
        "preview_url": "",
        "metadata": {},
        "attachments": [],
        "attachment_summary": "No attachments",
        "file_stamp_token": "",
    }


def _attachment_summary(attachments: list[dict[str, Any]]) -> str:
    count = len(attachments)
    if count == 0:
        return "No attachments"
    if count == 1:
        return "1 attachment"
    return f"{count} attachments"


def _ready_payload(
    *,
    source: str,
    path: Path,
    preview_path: Path,
    metadata: dict[str, str],
    attachments: list[dict[str, Any]],
    file_stamp_token: str,
    message: str = "",
) -> dict[str, Any]:
    return {
        "state": "ready",
        "message": message or "Mail preview is ready.",
        "source_path": str(source or "").strip(),
        "resolved_source_url": _preview_url(path),
        "preview_url": _preview_url(preview_path),
        "metadata": dict(metadata),
        "attachments": list(attachments),
        "attachment_summary": _attachment_summary(attachments),
        "file_stamp_token": file_stamp_token,
    }


def _local_path_from_source(source: str) -> Path | None:
    normalized = str(source or "").strip()
    if not normalized:
        return None
    return _preview_resolver().resolve_to_path(normalized)


def _part_payload_bytes(part: Message) -> bytes:
    payload = part.get_payload(decode=True)
    if isinstance(payload, bytes):
        return payload
    if isinstance(payload, str):
        return payload.encode(part.get_content_charset() or "utf-8", errors="replace")
    return b""


def _safe_filename(value: str, fallback: str) -> str:
    name = Path(str(value or "").strip()).name
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("._")
    return cleaned or fallback


def _message_headers(message: Message) -> dict[str, str]:
    return {
        "subject": str(message.get("subject", "") or ""),
        "from": str(message.get("from", "") or ""),
        "to": str(message.get("to", "") or ""),
        "cc": str(message.get("cc", "") or ""),
        "date": str(message.get("date", "") or ""),
    }


def _message_body_part(message: EmailMessage) -> tuple[str, str]:
    body = message.get_body(preferencelist=("html", "plain"))
    if body is None and message.is_multipart():
        for part in message.walk():
            if part.is_multipart() or part.get_content_disposition() == "attachment":
                continue
            if part.get_content_type() in {"text/html", "text/plain"}:
                body = part
                break
    if body is None:
        return "", "text/plain"
    content_type = str(body.get_content_type() or "text/plain").lower()
    try:
        return str(body.get_content() or ""), content_type
    except Exception:  # noqa: BLE001
        payload = _part_payload_bytes(body)
        charset = body.get_content_charset() or "utf-8"
        return payload.decode(charset, errors="replace"), content_type


def _inline_resource_map(message: EmailMessage, resources_dir: Path) -> dict[str, str]:
    cid_map: dict[str, str] = {}
    resources_dir.mkdir(parents=True, exist_ok=True)
    counter = 0
    for part in message.walk():
        if part.is_multipart():
            continue
        raw_cid = str(part.get("Content-ID", "") or "").strip()
        if not raw_cid:
            continue
        payload = _part_payload_bytes(part)
        if not payload:
            continue
        counter += 1
        content_type = str(part.get_content_type() or "application/octet-stream")
        filename = part.get_filename() or ""
        suffix = Path(filename).suffix
        if not suffix:
            suffix = mimetypes.guess_extension(content_type) or ".bin"
        resource_name = _safe_filename(filename, f"inline_{counter}{suffix}")
        if not Path(resource_name).suffix:
            resource_name = f"{resource_name}{suffix}"
        resource_path = resources_dir / resource_name
        resource_path.write_bytes(payload)
        cid = raw_cid.strip("<>").strip()
        if cid:
            cid_map[cid.lower()] = f"resources/{resource_path.name}"
    return cid_map


def _rewrite_cid_sources(html_body: str, cid_map: dict[str, str]) -> str:
    if not cid_map:
        return html_body

    def replace(match: re.Match[str]) -> str:
        token = unquote(match.group(1)).strip("<>").strip().lower()
        replacement = cid_map.get(token)
        return f"cid:{match.group(1)}" if replacement is None else replacement

    return re.sub(r"cid:([^\"'>\s)]+)", replace, html_body, flags=re.IGNORECASE)


def _attachments(message: EmailMessage) -> list[dict[str, Any]]:
    attachments: list[dict[str, Any]] = []
    for part in message.walk():
        if part.is_multipart() or part.get_content_disposition() != "attachment":
            continue
        payload = _part_payload_bytes(part)
        attachments.append(
            {
                "filename": part.get_filename() or "attachment",
                "content_type": str(part.get_content_type() or ""),
                "size": len(payload),
            }
        )
    return attachments


def _metadata_html(metadata: dict[str, str], attachment_summary: str) -> str:
    rows = []
    for label, key in (("Subject", "subject"), ("From", "from"), ("To", "to"), ("Date", "date")):
        value = str(metadata.get(key, "") or "").strip()
        if value:
            rows.append(
                "<div class=\"meta-row\"><span>"
                + html_lib.escape(label)
                + "</span><strong>"
                + html_lib.escape(value)
                + "</strong></div>"
            )
    if attachment_summary:
        rows.append(
            "<div class=\"meta-row\"><span>Attachments</span><strong>"
            + html_lib.escape(attachment_summary)
            + "</strong></div>"
        )
    return "".join(rows)


def _build_eml_preview_html(message: EmailMessage, resources_dir: Path) -> tuple[str, dict[str, str], list[dict[str, Any]]]:
    body_text, content_type = _message_body_part(message)
    inline_map = _inline_resource_map(message, resources_dir)
    attachments = _attachments(message)
    metadata = _message_headers(message)
    if content_type == "text/html":
        body_html = _rewrite_cid_sources(_SCRIPT_BLOCK_RE.sub("", body_text), inline_map)
    else:
        body_html = "<pre class=\"plain-body\">" + html_lib.escape(body_text) + "</pre>"
    return (
        "<!doctype html><html><head><meta charset=\"utf-8\">"
        "<style>"
        "html,body{margin:0;background:#f5f7fb;color:#18202b;font-family:Segoe UI,Arial,sans-serif;}"
        "body{padding:18px;}"
        ".meta{border:1px solid #d8dee8;background:#fff;border-radius:8px;padding:12px;margin-bottom:14px;}"
        ".meta-row{display:flex;gap:12px;margin:4px 0;font-size:12px;}"
        ".meta-row span{width:86px;color:#596579;flex:0 0 auto;}"
        ".meta-row strong{font-weight:600;color:#18202b;overflow-wrap:anywhere;}"
        ".body{background:#fff;border:1px solid #d8dee8;border-radius:8px;padding:14px;overflow:auto;}"
        ".plain-body{white-space:pre-wrap;font-family:Consolas,Segoe UI Mono,monospace;margin:0;}"
        "img{max-width:100%;height:auto;}"
        "</style></head><body><section class=\"meta\">"
        + _metadata_html(metadata, _attachment_summary(attachments))
        + "</section><article class=\"body\">"
        + body_html
        + "</article></body></html>",
        metadata,
        attachments,
    )


def _describe_eml(path: Path, raw_source: str, preview_dir: Path, file_stamp_token: str) -> dict[str, Any]:
    try:
        with path.open("rb") as handle:
            message = email.message_from_binary_file(handle, policy=policy.default)
        if not isinstance(message, EmailMessage):
            message = EmailMessage(policy=policy.default)
        if not list(message.items()) and not message.get_payload():
            return _error_payload(raw_source, "Unable to parse the selected mail file: the file is empty.")
    except Exception as exc:  # noqa: BLE001
        return _error_payload(raw_source, f"Unable to parse the selected mail file: {exc}")

    preview_path = preview_dir / "preview.html"
    resources_dir = preview_dir / "resources"
    try:
        html_text, metadata, attachments = _build_eml_preview_html(message, resources_dir)
        preview_path.write_text(html_text, encoding="utf-8")
    except Exception as exc:  # noqa: BLE001
        return _error_payload(raw_source, f"Unable to build the mail preview: {exc}")
    return _ready_payload(
        source=raw_source,
        path=path,
        preview_path=preview_path,
        metadata=metadata,
        attachments=attachments,
        file_stamp_token=file_stamp_token,
    )


def _dispatch_outlook_application() -> Any:
    import win32com.client  # type: ignore[import-not-found]

    return win32com.client.Dispatch("Outlook.Application")


def _outlook_value(item: Any, *names: str) -> str:
    for name in names:
        try:
            value = getattr(item, name)
        except Exception:  # noqa: BLE001
            continue
        if value is not None:
            return str(value)
    return ""


def _outlook_attachments(item: Any) -> list[dict[str, Any]]:
    try:
        attachments = getattr(item, "Attachments", None)
        count = int(getattr(attachments, "Count", 0) or 0)
    except Exception:  # noqa: BLE001
        return []
    result: list[dict[str, Any]] = []
    for index in range(1, count + 1):
        try:
            attachment = attachments.Item(index)
            filename = str(getattr(attachment, "FileName", "") or "attachment")
            size = int(getattr(attachment, "Size", 0) or 0)
        except Exception:  # noqa: BLE001
            continue
        result.append({"filename": filename, "content_type": "", "size": size})
    return result


def _describe_outlook_mail(path: Path, raw_source: str, preview_dir: Path, file_stamp_token: str) -> dict[str, Any]:
    if sys.platform != "win32":
        return _error_payload(
            raw_source,
            "Outlook rich mail preview requires Outlook on Windows.",
            state="unavailable",
        )
    try:
        application = _dispatch_outlook_application()
        item = application.Session.OpenSharedItem(str(path))
    except Exception as exc:  # noqa: BLE001
        return _error_payload(
            raw_source,
            f"Outlook rich mail preview is unavailable: {exc}",
            state="unavailable",
        )

    preview_path = preview_dir / "preview.html"
    try:
        preview_dir.mkdir(parents=True, exist_ok=True)
        item.SaveAs(str(preview_path), _OUTLOOK_HTML_FORMAT)
        metadata = {
            "subject": _outlook_value(item, "Subject"),
            "from": _outlook_value(item, "SenderName", "SenderEmailAddress"),
            "to": _outlook_value(item, "To"),
            "cc": _outlook_value(item, "CC"),
            "date": _outlook_value(item, "ReceivedTime", "SentOn", "CreationTime"),
        }
        attachments = _outlook_attachments(item)
    except Exception as exc:  # noqa: BLE001
        return _error_payload(raw_source, f"Unable to export the Outlook mail preview: {exc}")
    finally:
        close = getattr(item, "Close", None)
        if callable(close):
            try:
                close(0)
            except Exception:  # noqa: BLE001
                pass

    if not preview_path.exists():
        return _error_payload(raw_source, "Outlook did not create a mail preview.")
    return _ready_payload(
        source=raw_source,
        path=path,
        preview_path=preview_path,
        metadata=metadata,
        attachments=attachments,
        file_stamp_token=file_stamp_token,
    )


@lru_cache(maxsize=_MAIL_PREVIEW_CACHE_SIZE)
def _describe_mail_preview_cached(
    path_text: str,
    raw_source: str,
    modified_ns: int,
    file_size: int,
    suffix: str,
    cache_root_text: str,
) -> dict[str, Any]:
    path = Path(path_text)
    file_stamp_token = f"{modified_ns}-{file_size}"
    preview_dir = Path(cache_root_text) / _cache_key(path, file_stamp_token)
    preview_dir.mkdir(parents=True, exist_ok=True)
    if suffix == ".eml":
        payload = _describe_eml(path, raw_source, preview_dir, file_stamp_token)
    else:
        payload = _describe_outlook_mail(path, raw_source, preview_dir, file_stamp_token)
    if payload.get("state") != "ready":
        raise _UncacheableMailPreview(payload)
    return payload


def _clear_mail_preview_memory_cache() -> None:
    _describe_mail_preview_cached.cache_clear()


def describe_mail_preview(source: str) -> dict[str, Any]:
    raw_source = str(source or "").strip()
    if not raw_source:
        return _blank_payload("Choose a local mail file to preview it here.")

    path = _local_path_from_source(raw_source)
    if path is None:
        return _error_payload(raw_source, "Mail previews support only absolute local file paths.")
    if not path.exists() or not path.is_file():
        return _error_payload(raw_source, "Unable to find the selected mail file.")

    suffix = path.suffix.lower()
    if suffix not in MAIL_FILE_SUFFIXES:
        return _error_payload(raw_source, "Mail previews support .eml, .msg, and .oft files.")

    stats = _source_stats(path)
    if stats is None:
        return _error_payload(raw_source, "Unable to inspect the selected mail file.")
    modified_ns, file_size = stats
    try:
        payload = _describe_mail_preview_cached(
            str(path),
            raw_source,
            modified_ns,
            file_size,
            suffix,
            str(_mail_preview_cache_dir().resolve(strict=False)),
        )
    except _UncacheableMailPreview as exc:
        return exc.payload
    return deepcopy(payload)


__all__ = [
    "describe_mail_preview",
    "set_mail_preview_project_context_provider",
]

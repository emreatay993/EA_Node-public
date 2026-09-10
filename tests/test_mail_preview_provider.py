from __future__ import annotations

from contextlib import contextmanager
from email.message import EmailMessage
from pathlib import Path

from PyQt6.QtCore import QUrl

from ea_node_editor.ui import mail_preview_provider as mail_preview_provider_module
from ea_node_editor.ui.mail_preview_provider import (
    describe_mail_preview,
    set_mail_preview_project_context_provider,
)


@contextmanager
def _mail_preview_cache(monkeypatch, cache_dir: Path):  # noqa: ANN001
    monkeypatch.setattr(mail_preview_provider_module, "_mail_preview_cache_dir", lambda: cache_dir)
    mail_preview_provider_module._clear_mail_preview_memory_cache()
    set_mail_preview_project_context_provider(None)
    try:
        yield
    finally:
        mail_preview_provider_module._clear_mail_preview_memory_cache()
        set_mail_preview_project_context_provider(None)


def _preview_path(info: dict[str, object]) -> Path:
    return Path(QUrl(str(info["preview_url"])).toLocalFile())


def _write_message(path: Path, message: EmailMessage) -> None:
    path.write_bytes(message.as_bytes())


def test_eml_preview_prefers_html_body_and_lists_attachments(tmp_path, monkeypatch) -> None:  # noqa: ANN001
    msg = EmailMessage()
    msg["Subject"] = "HTML mail"
    msg["From"] = "sender@example.test"
    msg["To"] = "reader@example.test"
    msg.set_content("plain fallback")
    msg.add_alternative("<p>Hello <strong>HTML</strong></p>", subtype="html")
    msg.add_attachment(b"abc", maintype="text", subtype="plain", filename="note.txt")
    eml_path = tmp_path / "sample.eml"
    _write_message(eml_path, msg)

    with _mail_preview_cache(monkeypatch, tmp_path / "cache"):
        info = describe_mail_preview(str(eml_path))

    html_text = _preview_path(info).read_text(encoding="utf-8")
    assert info["state"] == "ready"
    assert info["attachment_summary"] == "1 attachment"
    assert info["metadata"]["subject"] == "HTML mail"  # type: ignore[index]
    assert "<strong>HTML</strong>" in html_text
    assert "plain fallback" not in html_text


def test_eml_preview_falls_back_to_escaped_plain_text(tmp_path, monkeypatch) -> None:  # noqa: ANN001
    msg = EmailMessage()
    msg["Subject"] = "Plain"
    msg.set_content("2 < 3\nbody")
    eml_path = tmp_path / "plain.eml"
    _write_message(eml_path, msg)

    with _mail_preview_cache(monkeypatch, tmp_path / "cache"):
        info = describe_mail_preview(str(eml_path))

    html_text = _preview_path(info).read_text(encoding="utf-8")
    assert info["state"] == "ready"
    assert "2 &lt; 3" in html_text


def test_mail_preview_reuses_ready_payload_for_the_same_source_stamp(tmp_path, monkeypatch) -> None:  # noqa: ANN001
    msg = EmailMessage()
    msg["Subject"] = "Cached"
    msg.set_content("body")
    eml_path = tmp_path / "cached.eml"
    _write_message(eml_path, msg)
    real_describe = mail_preview_provider_module._describe_eml
    calls = 0

    def counted_describe(*args, **kwargs):  # noqa: ANN002, ANN003, ANN202
        nonlocal calls
        calls += 1
        return real_describe(*args, **kwargs)

    monkeypatch.setattr(mail_preview_provider_module, "_describe_eml", counted_describe)
    with _mail_preview_cache(monkeypatch, tmp_path / "cache"):
        first = describe_mail_preview(str(eml_path))
        second = describe_mail_preview(str(eml_path))

    assert first == second
    assert first is not second
    assert calls == 1


def test_mail_preview_invalidates_when_the_source_stamp_changes(tmp_path, monkeypatch) -> None:  # noqa: ANN001
    msg = EmailMessage()
    msg["Subject"] = "Before"
    msg.set_content("short")
    eml_path = tmp_path / "changing.eml"
    _write_message(eml_path, msg)
    real_describe = mail_preview_provider_module._describe_eml
    calls = 0

    def counted_describe(*args, **kwargs):  # noqa: ANN002, ANN003, ANN202
        nonlocal calls
        calls += 1
        return real_describe(*args, **kwargs)

    monkeypatch.setattr(mail_preview_provider_module, "_describe_eml", counted_describe)
    with _mail_preview_cache(monkeypatch, tmp_path / "cache"):
        before = describe_mail_preview(str(eml_path))
        msg.replace_header("Subject", "After")
        msg.set_content("a longer body changes the source stamp")
        _write_message(eml_path, msg)
        after = describe_mail_preview(str(eml_path))

    assert before["file_stamp_token"] != after["file_stamp_token"]
    assert after["metadata"]["subject"] == "After"  # type: ignore[index]
    assert calls == 2


def test_mail_preview_does_not_cache_failures(tmp_path, monkeypatch) -> None:  # noqa: ANN001
    eml_path = tmp_path / "empty.eml"
    eml_path.write_bytes(b"")
    real_describe = mail_preview_provider_module._describe_eml
    calls = 0

    def counted_describe(*args, **kwargs):  # noqa: ANN002, ANN003, ANN202
        nonlocal calls
        calls += 1
        return real_describe(*args, **kwargs)

    monkeypatch.setattr(mail_preview_provider_module, "_describe_eml", counted_describe)
    with _mail_preview_cache(monkeypatch, tmp_path / "cache"):
        first = describe_mail_preview(str(eml_path))
        second = describe_mail_preview(str(eml_path))

    assert first["state"] == second["state"] == "error"
    assert calls == 2


def test_eml_preview_rewrites_cid_images_and_keeps_remote_images(tmp_path, monkeypatch) -> None:  # noqa: ANN001
    msg = EmailMessage()
    msg["Subject"] = "Images"
    msg.set_content("plain")
    msg.add_alternative(
        '<p><img src="cid:logo1"><img src="https://example.test/remote.png"></p>',
        subtype="html",
    )
    html_part = msg.get_payload()[1]
    html_part.add_related(b"png-bytes", maintype="image", subtype="png", cid="<logo1>", filename="logo.png")
    eml_path = tmp_path / "images.eml"
    _write_message(eml_path, msg)

    with _mail_preview_cache(monkeypatch, tmp_path / "cache"):
        info = describe_mail_preview(str(eml_path))

    preview_path = _preview_path(info)
    html_text = preview_path.read_text(encoding="utf-8")
    assert info["state"] == "ready"
    assert 'src="resources/logo.png"' in html_text
    assert (preview_path.parent / "resources" / "logo.png").read_bytes() == b"png-bytes"
    assert 'src="https://example.test/remote.png"' in html_text


def test_mail_preview_reports_missing_and_unsupported_sources(tmp_path, monkeypatch) -> None:  # noqa: ANN001
    unsupported = tmp_path / "mail.txt"
    unsupported.write_text("hello", encoding="utf-8")
    invalid = tmp_path / "empty.eml"
    invalid.write_text("", encoding="utf-8")

    with _mail_preview_cache(monkeypatch, tmp_path / "cache"):
        missing = describe_mail_preview(str(tmp_path / "missing.eml"))
        bad_suffix = describe_mail_preview(str(unsupported))
        remote = describe_mail_preview("https://example.test/message.eml")
        invalid_result = describe_mail_preview(str(invalid))

    assert missing["state"] == "error"
    assert "find" in str(missing["message"]).lower()
    assert bad_suffix["state"] == "error"
    assert ".eml" in str(bad_suffix["message"])
    assert remote["state"] == "error"
    assert "absolute local" in str(remote["message"])
    assert invalid_result["state"] == "error"
    assert "empty" in str(invalid_result["message"])


def test_msg_preview_uses_fake_outlook_com_export(tmp_path, monkeypatch) -> None:  # noqa: ANN001
    msg_path = tmp_path / "message.msg"
    msg_path.write_bytes(b"fake msg")

    class _Attachment:
        FileName = "agenda.pdf"
        Size = 123

    class _Attachments:
        Count = 1

        def Item(self, _index):  # noqa: N802, ANN001
            return _Attachment()

    class _Item:
        Subject = "Outlook subject"
        SenderName = "Sender"
        To = "Reader"
        ReceivedTime = "2026-07-08"
        Attachments = _Attachments()

        def SaveAs(self, path, _format):  # noqa: N802, ANN001
            Path(path).write_text("<html><body>Outlook HTML</body></html>", encoding="utf-8")

        def Close(self, _mode):  # noqa: N802, ANN001
            return None

    class _Session:
        def OpenSharedItem(self, _path):  # noqa: N802, ANN001
            return _Item()

    class _App:
        Session = _Session()

    monkeypatch.setattr(mail_preview_provider_module.sys, "platform", "win32")
    monkeypatch.setattr(mail_preview_provider_module, "_dispatch_outlook_application", lambda: _App())

    with _mail_preview_cache(monkeypatch, tmp_path / "cache"):
        info = describe_mail_preview(str(msg_path))

    assert info["state"] == "ready"
    assert info["metadata"]["subject"] == "Outlook subject"  # type: ignore[index]
    assert info["attachment_summary"] == "1 attachment"
    assert "Outlook HTML" in _preview_path(info).read_text(encoding="utf-8")

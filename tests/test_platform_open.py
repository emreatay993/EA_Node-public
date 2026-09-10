from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import ea_node_editor.platform_open as platform_open


def _record_all_launchers(monkeypatch) -> list:
    """Patch every launch path to record (and never actually launch)."""
    calls: list = []
    monkeypatch.setattr(
        platform_open.os, "startfile", lambda p: calls.append(("startfile", p)), raising=False
    )
    monkeypatch.setattr(
        platform_open.subprocess, "run", lambda *a, **k: calls.append(("run", a, k)) or SimpleNamespace(returncode=0)
    )
    monkeypatch.setattr(
        platform_open.QDesktopServices, "openUrl", lambda url: calls.append(("openUrl", url)) or True
    )
    return calls


def test_open_rejects_empty_and_blank_paths(monkeypatch) -> None:
    calls = _record_all_launchers(monkeypatch)
    for value in ("", "   ", None):
        assert platform_open.open_path_with_default_handler(value) is False
        assert platform_open.open_path_with_app_chooser(value) is False
    assert calls == []


def test_open_rejects_nonexistent_path(monkeypatch, tmp_path: Path) -> None:
    calls = _record_all_launchers(monkeypatch)
    missing = tmp_path / "does-not-exist.txt"
    assert platform_open.open_path_with_default_handler(str(missing)) is False
    assert platform_open.open_path_with_app_chooser(str(missing)) is False
    assert calls == []


def test_open_default_windows_uses_startfile(monkeypatch, tmp_path: Path) -> None:
    target = tmp_path / "file.txt"
    target.write_text("x", encoding="utf-8")
    monkeypatch.setattr(platform_open.sys, "platform", "win32")
    started: list[str] = []
    monkeypatch.setattr(platform_open.os, "startfile", lambda p: started.append(p), raising=False)
    ran: list = []
    monkeypatch.setattr(platform_open.subprocess, "run", lambda *a, **k: ran.append(a) or SimpleNamespace(returncode=0))

    assert platform_open.open_path_with_default_handler(str(target)) is True
    assert started == [str(target)]
    assert ran == []


def test_open_default_windows_falls_back_to_desktop_services(monkeypatch, tmp_path: Path) -> None:
    target = tmp_path / "file.txt"
    target.write_text("x", encoding="utf-8")
    monkeypatch.setattr(platform_open.sys, "platform", "win32")

    def _boom(_p: str) -> None:
        raise OSError("no handler")

    monkeypatch.setattr(platform_open.os, "startfile", _boom, raising=False)
    fallback: list = []
    monkeypatch.setattr(platform_open.QDesktopServices, "openUrl", lambda url: fallback.append(url) or True)

    assert platform_open.open_path_with_default_handler(str(target)) is True
    assert len(fallback) == 1


def test_open_default_linux_uses_xdg_open(monkeypatch, tmp_path: Path) -> None:
    target = tmp_path / "file.txt"
    target.write_text("x", encoding="utf-8")
    monkeypatch.setattr(platform_open.sys, "platform", "linux")
    recorded: dict = {}

    def _run(args, **kwargs):
        recorded["args"] = args
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(platform_open.subprocess, "run", _run)

    assert platform_open.open_path_with_default_handler(str(target)) is True
    assert recorded["args"] == ["xdg-open", str(target)]


def test_open_chooser_windows_uses_rundll32_open_as(monkeypatch, tmp_path: Path) -> None:
    target = tmp_path / "file.txt"
    target.write_text("x", encoding="utf-8")
    monkeypatch.setattr(platform_open.sys, "platform", "win32")
    recorded: dict = {}

    def _run(args, **kwargs):
        recorded["args"] = args
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(platform_open.subprocess, "run", _run)

    assert platform_open.open_path_with_app_chooser(str(target)) is True
    assert recorded["args"] == ["rundll32.exe", "shell32.dll,OpenAs_RunDLL", str(target)]


def test_open_chooser_windows_reports_failure_on_nonzero_exit(monkeypatch, tmp_path: Path) -> None:
    target = tmp_path / "file.txt"
    target.write_text("x", encoding="utf-8")
    monkeypatch.setattr(platform_open.sys, "platform", "win32")
    monkeypatch.setattr(platform_open.subprocess, "run", lambda args, **k: SimpleNamespace(returncode=1))

    assert platform_open.open_path_with_app_chooser(str(target)) is False

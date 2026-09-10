from __future__ import annotations

from ea_node_editor.telemetry import startup_profile


class _BrokenStderr:
    def write(self, _message: str) -> int:
        raise OSError(22, "Invalid argument")

    def flush(self) -> None:
        raise AssertionError("flush must not follow a failed write")


def test_startup_profile_ignores_unavailable_stderr(monkeypatch) -> None:
    monkeypatch.setattr(startup_profile, "_ENABLED", True)
    monkeypatch.setattr(startup_profile, "_EVENTS", [])
    monkeypatch.setattr(startup_profile.sys, "stderr", _BrokenStderr())

    with startup_profile.phase("diagnostic"):
        pass

    startup_profile.summary()
    assert startup_profile._EVENTS[0][0] == "diagnostic"


def test_startup_profile_ignores_missing_stderr(monkeypatch) -> None:
    monkeypatch.setattr(startup_profile, "_ENABLED", True)
    monkeypatch.setattr(startup_profile, "_EVENTS", [])
    monkeypatch.setattr(startup_profile.sys, "stderr", None)

    with startup_profile.phase("windowed"):
        pass

    startup_profile.summary()
    assert startup_profile._EVENTS[0][0] == "windowed"

from __future__ import annotations

from ea_node_editor.nodes import function_bundle


def test_frozen_import_availability_uses_the_actual_bundle_importer(
    monkeypatch,
) -> None:
    monkeypatch.setattr(function_bundle.sys, "frozen", True, raising=False)
    monkeypatch.setattr(function_bundle.importlib.util, "find_spec", lambda _name: None)

    assert not function_bundle.bundled_module_available("ansys")

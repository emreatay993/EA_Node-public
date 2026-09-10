from __future__ import annotations

import os
from pathlib import Path

import pytest

from ea_node_editor.nodes import plugin_authoring
from ea_node_editor.nodes.plugin_authoring import (
    new_plugin_identity,
    read_saved_plugin_draft,
    render_plugin_template,
    save_plugin_draft,
    suggest_plugin_filename,
    validate_plugin_draft,
)
from ea_node_editor.nodes.plugin_declaration import (
    PluginDeclarationError,
    discover_plugin_declarations,
)
from ea_node_editor.nodes.package_schema import PLUGIN_SOURCE_LIMIT
from ea_node_editor.nodes.registry import NodeRegistry


def _node_source(
    node_id: str,
    function_name: str,
    *,
    import_line: str = "",
) -> str:
    extra_import = f"{import_line}\n" if import_line else ""
    return f'''import corex
{extra_import}
@corex.node(id={node_id!r}, name={function_name!r}, category=("Custom",))
@corex.input("value", value_type=float, required=True)
@corex.output("result", value_type=float)
def {function_name}(ctx, value):
    return {{"result": value}}
'''


def test_identity_normalizes_name_and_uses_randomness_once(monkeypatch) -> None:
    calls: list[int] = []

    def token_hex(size: int) -> str:
        calls.append(size)
        return "a7c31e9b"

    monkeypatch.setattr(plugin_authoring.secrets, "token_hex", token_hex)

    identity = new_plugin_identity("  Résumé / Scale  ")

    assert identity.visible_name == "Résumé / Scale"
    assert identity.slug == "resume_scale"
    assert identity.filename == "resume_scale.py"
    assert identity.function_name == "resume_scale"
    assert identity.node_id == "custom.resume_scale.a7c31e9b"
    assert calls == [4]


@pytest.mark.parametrize(
    ("name", "expected_slug"),
    (("", "new_plugin"), ("节点", "plugin"), ("class", "class_node"), ("../CON", "con_node")),
)
def test_identity_normalizes_empty_unicode_keyword_and_path_hostile_names(
    name: str,
    expected_slug: str,
    monkeypatch,
) -> None:
    monkeypatch.setattr(plugin_authoring.secrets, "token_hex", lambda _size: "1234abcd")

    identity = new_plugin_identity(name)

    assert identity.slug == expected_slug
    assert identity.function_name.isidentifier()
    assert identity.filename == f"{expected_slug}.py"
    assert identity.node_id == f"custom.{expected_slug}.1234abcd"


def test_filename_suggestions_are_safe_and_consume_no_randomness(monkeypatch) -> None:
    def unexpected_randomness(_size: int) -> str:
        pytest.fail("filename suggestions must not generate an ID")

    monkeypatch.setattr(plugin_authoring.secrets, "token_hex", unexpected_randomness)

    assert suggest_plugin_filename("Scale Value") == "scale_value.py"
    assert suggest_plugin_filename("class") == "class_node.py"
    assert suggest_plugin_filename("../CON") == "con_node.py"


def test_template_is_deterministic_valid_and_keeps_id_after_rename(monkeypatch) -> None:
    monkeypatch.setattr(plugin_authoring.secrets, "token_hex", lambda _size: "1234abcd")
    identity = new_plugin_identity("Scale Value")

    original = render_plugin_template(identity)
    renamed = render_plugin_template(identity, visible_name="Renamed Scale")
    original_declaration = discover_plugin_declarations(original, filename=identity.filename)[0]
    renamed_declaration = discover_plugin_declarations(renamed, filename=identity.filename)[0]

    assert original == render_plugin_template(identity)
    assert original_declaration.spec.type_id == renamed_declaration.spec.type_id
    assert renamed_declaration.spec.type_id == identity.node_id
    assert renamed_declaration.spec.display_name == "Renamed Scale"
    assert renamed_declaration.spec.category_path == ("Custom",)
    assert renamed_declaration.input_keys == ("value",)
    assert renamed_declaration.output_keys == ("result",)


def test_validation_never_executes_source_or_mutates_an_installed_root(
    tmp_path: Path,
) -> None:
    marker = tmp_path / "executed.txt"
    installed_root = tmp_path / "plugins"
    installed_root.mkdir()
    existing = installed_root / "existing.py"
    existing.write_text("unchanged", encoding="utf-8")
    source = (
        f"from pathlib import Path\nPath({str(marker)!r}).write_text('bad')\n"
        + _node_source("custom.safe.1234abcd", "safe")
    )

    report = validate_plugin_draft(source, "safe.py", NodeRegistry())

    assert report.success
    assert report.summary.bundle_count == 1
    assert report.summary.node_count == 1
    assert len(report.summary.plugin_digest) == 64
    assert report.diagnostics[0].severity == "info"
    assert report.diagnostics[0].node_id == "custom.safe.1234abcd"
    assert len(report.diagnostics[0].digest) == 64
    assert not marker.exists()
    assert existing.read_text(encoding="utf-8") == "unchanged"


def test_validation_reports_every_node_and_missing_dependency_state() -> None:
    source = _node_source(
        "custom.first.1234abcd",
        "first",
        import_line="import definitely_missing_corex_dependency",
    ) + _node_source("custom.second.89abcdef", "second").removeprefix("import corex\n")

    report = validate_plugin_draft(source, "two_nodes.py", NodeRegistry())

    assert report.success
    assert report.summary == plugin_authoring.PluginAuthoringSummary(
        bundle_count=1,
        node_count=2,
        plugin_digest=report.summary.plugin_digest,
        unavailable_node_count=2,
    )
    assert [row.node_id for row in report.diagnostics] == [
        "custom.first.1234abcd",
        "custom.second.89abcdef",
    ]
    assert {row.severity for row in report.diagnostics} == {"warning"}
    assert all(
        row.unavailable_reason
        == "definitely_missing_corex_dependency is not included in this COREX bundle."
        for row in report.diagnostics
    )


def test_validation_preserves_exact_static_parser_position() -> None:
    source = '''import corex

@corex.node(id="custom.bad.1234abcd", name="Bad", category=("Custom",))
@corex.output("result", value_type=corex.Any)
@corex.number("factor", default=2.0)
def bad(ctx, settings):
    return {"result": settings.fator}
'''
    with pytest.raises(PluginDeclarationError) as caught:
        discover_plugin_declarations(source, filename="bad.py")

    report = validate_plugin_draft(source, "bad.py", NodeRegistry())

    assert not report.success
    assert report.diagnostics[0].filename == caught.value.filename
    assert report.diagnostics[0].line == caught.value.line
    assert report.diagnostics[0].column == caught.value.column
    assert report.diagnostics[0].message == caught.value.message


def test_validation_rejects_zero_declarations_and_oversized_source() -> None:
    empty = validate_plugin_draft("import corex\n", "empty.py", NodeRegistry())
    oversized = validate_plugin_draft(
        "#" * (PLUGIN_SOURCE_LIMIT + 1),
        "large.py",
        NodeRegistry(),
    )

    assert not empty.success
    assert empty.diagnostics[0].message == "Plugin draft must declare at least one node"
    assert not oversized.success
    assert oversized.diagnostics[0].message == "Plugin source is too large"


@pytest.mark.parametrize(
    "filename",
    ("../escape.py", "nested/node.py", "_hidden.py", ".hidden.py", "CON.py", "node.PY"),
)
def test_save_rejects_non_visible_direct_child_python_names(
    tmp_path: Path,
    filename: str,
) -> None:
    with pytest.raises(ValueError, match="direct-child"):
        save_plugin_draft("import corex\n", filename, root=tmp_path)


def test_save_is_atomic_and_redacts_operating_system_failure_paths(
    tmp_path: Path,
    monkeypatch,
) -> None:
    destination = tmp_path / "draft.py"
    destination.write_text("old", encoding="utf-8")

    def fail_replace(_source: object, _destination: object) -> None:
        raise OSError(f"private path: {tmp_path}")

    monkeypatch.setattr(plugin_authoring.os, "replace", fail_replace)

    with pytest.raises(ValueError) as caught:
        save_plugin_draft("new", "draft.py", expected_source="old", root=tmp_path)

    assert str(caught.value) == "Plugin draft could not be saved"
    assert str(tmp_path) not in str(caught.value)
    assert destination.read_text(encoding="utf-8") == "old"
    assert sorted(path.name for path in tmp_path.iterdir()) == ["draft.py"]


def test_first_save_atomically_refuses_existing_and_racing_destinations(
    tmp_path: Path,
    monkeypatch,
) -> None:
    destination = save_plugin_draft("first", "draft.py", root=tmp_path)
    with pytest.raises(ValueError, match="already exists"):
        save_plugin_draft("second", "draft.py", root=tmp_path)
    assert destination.read_text(encoding="utf-8") == "first"

    racing_destination = tmp_path / "racing.py"
    real_link = plugin_authoring.os.link

    def collide(source: object, target: object) -> None:
        Path(target).write_text("external", encoding="utf-8")
        real_link(source, target)

    monkeypatch.setattr(plugin_authoring.os, "link", collide)
    with pytest.raises(ValueError, match="already exists"):
        save_plugin_draft("ours", "racing.py", root=tmp_path)
    assert racing_destination.read_text(encoding="utf-8") == "external"
    assert not any(path.suffix == ".tmp" for path in tmp_path.iterdir())


def test_overwrite_requires_exact_expected_source_and_refuses_mutation_or_deletion(
    tmp_path: Path,
) -> None:
    destination = save_plugin_draft("first", "draft.py", root=tmp_path)

    save_plugin_draft(
        "second",
        "draft.py",
        expected_source="first",
        root=tmp_path,
    )
    assert read_saved_plugin_draft(destination, root=tmp_path) == "second"

    destination.write_text("external", encoding="utf-8")
    with pytest.raises(ValueError, match="changed since it was opened"):
        save_plugin_draft(
            "third",
            "draft.py",
            expected_source="second",
            root=tmp_path,
        )
    assert destination.read_text(encoding="utf-8") == "external"

    destination.unlink()
    with pytest.raises(ValueError, match="changed since it was opened"):
        save_plugin_draft(
            "third",
            "draft.py",
            expected_source="external",
            root=tmp_path,
        )
    assert not destination.exists()


def test_save_rejects_existing_hard_link_and_reparse_target(
    tmp_path: Path,
    monkeypatch,
) -> None:
    destination = tmp_path / "draft.py"
    destination.write_text("old", encoding="utf-8")
    linked = tmp_path / "linked.py"
    try:
        os.link(destination, linked)
    except OSError:
        pytest.skip("hard links are unavailable")

    with pytest.raises(ValueError, match="regular files with exactly one link"):
        save_plugin_draft("new", "draft.py", root=tmp_path)
    assert destination.read_text(encoding="utf-8") == "old"

    linked.unlink()
    monkeypatch.setattr(
        plugin_authoring,
        "is_reparse_point",
        lambda path: path == destination,
    )
    with pytest.raises(ValueError, match="path alias"):
        save_plugin_draft("new", "draft.py", root=tmp_path)


def test_save_writes_bounded_utf8_source_as_one_regular_file(tmp_path: Path) -> None:
    source = _node_source("custom.saved.1234abcd", "saved")

    destination = save_plugin_draft(source, "saved.py", root=tmp_path)

    assert destination == tmp_path / "saved.py"
    assert read_saved_plugin_draft(destination, root=tmp_path) == source
    assert read_saved_plugin_draft("saved.py", root=tmp_path) == source
    assert destination.stat().st_nlink == 1
    with pytest.raises(ValueError, match="too large"):
        save_plugin_draft("#" * (PLUGIN_SOURCE_LIMIT + 1), "large.py", root=tmp_path)


def test_read_saved_draft_rejects_non_direct_hardlinked_reparse_large_and_non_utf8(
    tmp_path: Path,
    monkeypatch,
) -> None:
    destination = save_plugin_draft("valid", "draft.py", root=tmp_path)
    with pytest.raises(ValueError, match="direct installed"):
        read_saved_plugin_draft(tmp_path / "nested" / "draft.py", root=tmp_path)

    linked = tmp_path / "linked.py"
    try:
        os.link(destination, linked)
    except OSError:
        pytest.skip("hard links are unavailable")
    with pytest.raises(ValueError, match="regular files with exactly one link"):
        read_saved_plugin_draft(destination, root=tmp_path)
    linked.unlink()

    monkeypatch.setattr(
        plugin_authoring,
        "is_reparse_point",
        lambda path: path == destination,
    )
    with pytest.raises(ValueError, match="unavailable"):
        read_saved_plugin_draft(destination, root=tmp_path)
    monkeypatch.setattr(plugin_authoring, "is_reparse_point", lambda _path: False)

    destination.write_bytes(b"\xff")
    with pytest.raises(ValueError, match="UTF-8"):
        read_saved_plugin_draft(destination, root=tmp_path)
    destination.write_bytes(b"x" * (PLUGIN_SOURCE_LIMIT + 1))
    with pytest.raises(ValueError, match="too large"):
        read_saved_plugin_draft(destination, root=tmp_path)

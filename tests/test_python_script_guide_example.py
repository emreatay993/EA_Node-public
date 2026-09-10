from pathlib import Path

from ea_node_editor.nodes.bootstrap import build_builtin_registry


_EXAMPLE = (
    Path(__file__).resolve().parents[1]
    / "docs"
    / "examples"
    / "python_script_decorated_signal_plot.py"
)


def test_python_script_guide_example_resolves_without_running_source() -> None:
    source = _EXAMPLE.read_text(encoding="utf-8")
    registry = build_builtin_registry()

    properties = registry.normalize_properties(
        "core.python_script", {"script": source}
    )
    spec = registry.resolve_spec("core.python_script", properties)

    assert [port.key for port in spec.ports] == [
        "series",
        "title_suffix",
        "plot_summary",
        "title",
        "show_legend",
        "legend_position",
        "line_width",
        "series_labels",
    ]
    assert [group.label for group in spec.settings_groups] == [
        "Data",
        "Style",
        "Legend",
        "Axes",
    ]

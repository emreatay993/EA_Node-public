from __future__ import annotations

from ea_node_editor.nodes.execution_context import NodeResult
from ea_node_editor.nodes.node_specs import NodeTypeSpec, PropertySpec

PASSIVE_EDITOR_FIXTURE_TYPE_ID = "tests.passive_editor_fixture"


class PassiveEditorFixturePlugin:
    def spec(self) -> NodeTypeSpec:
        return NodeTypeSpec(
            type_id=PASSIVE_EDITOR_FIXTURE_TYPE_ID,
            display_name="Passive Editor Fixture",
            category_path=("Tests",),
            icon="article",
            description="Test-only node for inspector property editor coverage.",
            runtime_behavior="passive",
            surface_family="annotation",
            ports=(),
            properties=(
                PropertySpec(
                    "notes_blob",
                    "str",
                    "Line one",
                    "Notes",
                    inspector_editor="textarea",
                ),
                PropertySpec("media_ref", "path", "", "Media Reference"),
                PropertySpec(
                    "accent_color",
                    "str",
                    "#336699",
                    "Accent Color",
                    inline_editor="color",
                    inspector_editor="color",
                ),
                PropertySpec("caption", "str", "Short caption", "Caption"),
            ),
        )

    def execute(self, _ctx) -> NodeResult:  # noqa: ANN001
        return NodeResult()


def register_passive_editor_fixture(registry) -> None:  # noqa: ANN001
    try:
        registry.get_spec(PASSIVE_EDITOR_FIXTURE_TYPE_ID)
    except KeyError:
        registry.register(PassiveEditorFixturePlugin)

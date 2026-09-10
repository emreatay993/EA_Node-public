from __future__ import annotations

from collections import UserList
from dataclasses import asdict
from pathlib import Path

import pytest

import corex
from corex import _Settings
from ea_node_editor.nodes.plugin_declaration import (
    PluginDeclarationError,
    discover_plugin_declarations as _discover_plugin_declarations,
)
from ea_node_editor.nodes.function_plugin import INTERNAL_BUILTIN_FUNCTION_OWNER_ID
from ea_node_editor.nodes.node_specs import PropertyConditionSpec
from ea_node_editor.nodes.registry import NodeRegistry
from ea_node_editor.runtime_contracts import DataTypeSpec, Interval1D, TypedInlineValue


PUBLIC_EXPORTS = [
    "node",
    "input",
    "output",
    "text",
    "text_area",
    "number",
    "switch",
    "dropdown",
    "slider",
    "color",
    "path",
    "interval",
    "list",
    "Any",
    "Image",
    "Color",
    "Interval",
]


def discover_plugin_declarations(source: str, **kwargs):
    return _discover_plugin_declarations("import corex\n" + source, **kwargs)


def discover_internal(source: str):
    return discover_plugin_declarations(
        source,
        allow_reserved_ids=True,
        owner_id=INTERNAL_BUILTIN_FUNCTION_OWNER_ID,
    )


def test_corex_public_exports_and_runtime_decorators_are_exact() -> None:
    assert corex.__all__ == PUBLIC_EXPORTS
    assert corex.Any == "COREX.DataTypes.Any"
    assert corex.Image == "COREX.DataTypes.Image"
    assert corex.Color == "COREX.DataTypes.Color"
    assert corex.Interval == "COREX.DataTypes.Interval1D"

    @corex.node(id="custom.identity.a7c31e9b", name="Identity", category=("Core",))
    @corex.input("value", value_type=corex.Any)
    @corex.output("result", value_type=corex.Any)
    def identity(ctx, value):
        return {"result": value}

    assert identity(None, 3) == {"result": 3}


def test_multiple_sync_async_nodes_and_literal_constants_are_discovered() -> None:
    source = '''
CATEGORY = ("Math", "Transforms")
KEYWORDS = ("scale", "multiply")
FACTOR = 2.0

@corex.node(
    id="custom.scale.a7c31e9b",
    name="Scale",
    category=CATEGORY,
    description="Scale a number.",
    keywords=KEYWORDS,
)
@corex.input("value", value_type=float, required=True, section="Data")
@corex.output("scaled", value_type=float)
@corex.slider("factor", default=FACTOR, minimum=0.0, maximum=10.0, section="Settings", port=True)
def scale(ctx, value, settings):
    return {"scaled": value * settings.factor}

@corex.node(id="custom.negate.b8d42f0a", name="Negate", category=("Math",))
@corex.input("value", value_type=float)
@corex.output("negated", value_type=float)
async def negate(ctx, value):
    return {"negated": -value}
'''

    scale, negate = discover_plugin_declarations(source, filename="nodes.py")

    assert scale.function_name == "scale"
    assert scale.input_keys == ("value",)
    assert scale.output_keys == ("scaled",)
    assert scale.control_keys == ("factor",)
    assert scale.spec.category_path == ("Math", "Transforms")
    assert scale.spec.keywords == ("scale", "multiply")
    assert [port.key for port in scale.spec.ports] == ["value", "scaled", "factor"]
    assert scale.spec.properties[0].default == 2.0
    assert [(group.group_id, group.label) for group in scale.spec.settings_groups] == [
        ("data", "Data"),
        ("settings", "Settings"),
    ]
    assert not scale.is_async
    assert negate.function_name == "negate"
    assert negate.is_async
    assert negate.spec.is_async


def test_every_control_uses_shared_metadata_and_one_settings_parameter() -> None:
    source = '''
OPTIONS = ("Mean", "Maximum")

@corex.node(id="custom.controls.1234abcd", name="Controls", category=("Tests",))
@corex.output("result", value_type=str)
@corex.text("title", default="Plot", section="Text")
@corex.text_area("notes", default="", section="Text")
@corex.number("count", default=2)
@corex.switch("enabled", default=True)
@corex.dropdown("mode", default="Mean", options=OPTIONS)
@corex.slider("factor", default=2.0, minimum=0.0, maximum=10.0, port=True)
@corex.color("accent", default="#336699")
@corex.path("folder", default="", file_filter="All files (*)")
@corex.interval("bounds", default=(0.0, 1.0), minimum=0.0, maximum=2.0)
@corex.list("labels", default=["A"], item_type=str)
def controls(ctx, settings):
    values = settings.to_dict()
    return {"result": values["title"]}
'''

    (declaration,) = discover_plugin_declarations(source)

    assert declaration.control_keys == (
        "title",
        "notes",
        "count",
        "enabled",
        "mode",
        "factor",
        "accent",
        "folder",
        "bounds",
        "labels",
    )
    assert [prop.inline_editor for prop in declaration.spec.properties] == [
        "text",
        "textarea",
        "number",
        "toggle",
        "enum",
        "slider",
        "color",
        "path",
        "interval_slider",
        "list",
    ]
    assert declaration.spec.properties[8].default == Interval1D(0.0, 1.0)
    factor = next(port for port in declaration.spec.ports if port.key == "factor")
    assert factor.uses_property_default


def test_labels_derive_only_when_omitted_and_preserve_explicit_blank() -> None:
    source = '''
@corex.node(id="custom.labels.1234abcd", name="Labels", category=("Tests",))
@corex.input("omitted_input", value_type=corex.Any)
@corex.input("blank_input", value_type=corex.Any, label="")
@corex.output("omitted_output", value_type=corex.Any)
@corex.output("blank_output", value_type=corex.Any, label="")
@corex.text("omitted_control")
@corex.text("blank_control", label="")
def labels(ctx, omitted_input, blank_input, settings):
    return {}
'''

    (declaration,) = discover_plugin_declarations(source)
    ports = {port.key: port for port in declaration.spec.ports}
    properties = {prop.key: prop for prop in declaration.spec.properties}

    assert ports["omitted_input"].label == "Omitted Input"
    assert ports["blank_input"].label == ""
    assert ports["omitted_output"].label == "Omitted Output"
    assert ports["blank_output"].label == ""
    assert properties["omitted_control"].label == "Omitted Control"
    assert properties["blank_control"].label == ""


@pytest.mark.parametrize("direction", ("input", "output"))
def test_port_types_must_be_explicit_and_errors_locate_the_decorator(direction: str) -> None:
    parameters = "ctx, value" if direction == "input" else "ctx"
    source = f'''import corex
@corex.node(id="custom.explicit.1234abcd", name="Explicit", category=("Tests",))
@corex.{direction}("value")
def explicit({parameters}): return {{}}
'''
    with pytest.raises(PluginDeclarationError, match="requires explicit value_type=") as caught:
        _discover_plugin_declarations(source, filename="explicit.py")
    assert (caught.value.filename, caught.value.line, caught.value.column) == (
        "explicit.py", 3, 2
    )
    explicit_source = source.replace('(\"value\")', '(\"value\", value_type=corex.Any)')
    (declaration,) = _discover_plugin_declarations(explicit_source)
    assert declaration.spec.ports[0].data_type == "COREX.DataTypes.Any"


def test_hostile_source_is_never_executed_during_discovery(tmp_path: Path) -> None:
    marker = tmp_path / "marker.txt"
    source = f'''
from pathlib import Path
Path({str(marker)!r}).write_text("executed", encoding="utf-8")

@corex.node(id="custom.safe.1234abcd", name="Safe", category=("Tests",))
@corex.output("result", value_type=corex.Any)
def safe(ctx):
    return {{"result": True}}
'''

    assert len(discover_plugin_declarations(source, filename="hostile.py")) == 1
    assert not marker.exists()


@pytest.mark.parametrize(
    ("source", "message"),
    (
        (
            '''
@corex.input("value", value_type=corex.Any)
@corex.node(id="custom.order.1234abcd", name="Order", category=("Tests",))
def order(ctx, value): return {}
''',
            "first decorator",
        ),
        (
            '''
@corex.node(id="plot.signal", name="Reserved", category=("Tests",))
def reserved(ctx): return {}
''',
            "External node ids",
        ),
        (
            '''
@corex.node(id="custom.unknown.1234abcd", name="Unknown", category=("Tests",))
@corex.mystery("value")
def unknown(ctx): return {}
''',
            "Unknown corex decorator",
        ),
        (
            '''
@corex.node(id="custom.field.1234abcd", name="Field", category=("Tests",), extra=True)
def field(ctx): return {}
''',
            "does not accept 'extra'",
        ),
        (
            '''
def outer():
    @corex.node(id="custom.nested.1234abcd", name="Nested", category=("Tests",))
    def nested(ctx): return {}
''',
            "top-level",
        ),
        (
            '''
class Owner:
    @corex.node(id="custom.method.1234abcd", name="Method", category=("Tests",))
    def method(self, ctx): return {}
''',
            "top-level",
        ),
        (
            '''
generated = corex.node(id="custom.lambda.1234abcd", name="Lambda", category=("Tests",))(lambda ctx: {})
''',
            "Dynamically generated",
        ),
        (
            '''
from corex import node
@node(id="custom.alias.1234abcd", name="Alias", category=("Tests",))
def alias(ctx): return {}
''',
            "aliases are unsupported",
        ),
    ),
)
def test_invalid_declaration_locations_are_actionable(
    source: str,
    message: str,
) -> None:
    with pytest.raises(PluginDeclarationError, match=message) as caught:
        discover_plugin_declarations(source, filename="bad.py")

    assert caught.value.filename == "bad.py"
    assert caught.value.line >= 1
    assert caught.value.column >= 1


def test_plugin_source_requires_an_explicit_unaliased_corex_import() -> None:
    source = '''
@corex.node(id="custom.import.1234abcd", name="Import", category=("Tests",))
def imported(ctx): return {}
'''
    with pytest.raises(PluginDeclarationError, match="import corex"):
        _discover_plugin_declarations(source)


@pytest.mark.parametrize(
    ("signature", "decorators"),
    (
        ("ctx, settings", '@corex.input("value", value_type=corex.Any)'),
        ("ctx, value", '@corex.slider("factor", default=1.0, minimum=0.0, maximum=2.0)'),
        ("ctx, second, first", '@corex.input("first", value_type=corex.Any)\n@corex.input("second", value_type=corex.Any)'),
        ("ctx, value=None", '@corex.input("value", value_type=corex.Any)'),
        ("ctx, *, value", '@corex.input("value", value_type=corex.Any)'),
    ),
)
def test_signature_must_match_inputs_and_settings_exactly(
    signature: str,
    decorators: str,
) -> None:
    source = f'''
@corex.node(id="custom.signature.1234abcd", name="Signature", category=("Tests",))
{decorators}
def signature({signature}): return {{}}
'''
    with pytest.raises(PluginDeclarationError, match="plain required|exactly"):
        discover_plugin_declarations(source)


def test_duplicate_ids_names_and_cross_direction_keys_reject() -> None:
    duplicate_id = '''
@corex.node(id="custom.duplicate.1234abcd", name="One", category=("Tests",))
def one(ctx): return {}
@corex.node(id="custom.duplicate.1234abcd", name="Two", category=("Tests",))
def two(ctx): return {}
'''
    with pytest.raises(PluginDeclarationError, match="id .* duplicated"):
        discover_plugin_declarations(duplicate_id)

    duplicate_name = '''
@corex.node(id="custom.one.1234abcd", name="One", category=("Tests",))
def same(ctx): return {}
@corex.node(id="custom.two.1234abcd", name="Two", category=("Tests",))
def same(ctx): return {}
'''
    with pytest.raises(PluginDeclarationError, match="function name .* unique"):
        discover_plugin_declarations(duplicate_name)

    collision = '''
@corex.node(id="custom.collision.1234abcd", name="Collision", category=("Tests",))
@corex.input("value", value_type=corex.Any)
@corex.output("value", value_type=corex.Any)
def collision(ctx, value): return {"value": value}
'''
    with pytest.raises(PluginDeclarationError, match="cross-direction"):
        discover_plugin_declarations(collision)


@pytest.mark.parametrize(
    "shadow",
    (
        "def target(ctx): return {'unsafe': True}",
        "class target: pass",
        "target = lambda ctx: {'unsafe': True}",
        "from math import sin as target",
        "try:\n    raise RuntimeError\nexcept RuntimeError as target:\n    pass",
        "match 1:\n    case target:\n        pass",
        "match {'value': 1}:\n    case {'value': value, **target}:\n        pass",
    ),
)
def test_node_function_symbol_cannot_be_shadowed(shadow: str) -> None:
    source = f'''
@corex.node(id="custom.target.1234abcd", name="Target", category=("Tests",))
def target(ctx): return {{}}
{shadow}
'''
    with pytest.raises(PluginDeclarationError, match="must be unique"):
        discover_plugin_declarations(source)


def test_star_imports_reject_before_they_can_shadow_node_symbols() -> None:
    source = '''
from math import *
@corex.node(id="custom.star.1234abcd", name="Star", category=("Tests",))
def star(ctx): return {}
'''
    with pytest.raises(PluginDeclarationError, match="Star imports"):
        discover_plugin_declarations(source)


def test_nonliteral_constants_calls_and_reserved_names_reject() -> None:
    nonliteral = '''
DEFAULT = make_default()
@corex.node(id="custom.nonliteral.1234abcd", name="Nonliteral", category=("Tests",))
@corex.number("factor", default=DEFAULT)
def nonliteral(ctx, settings): return {}
'''
    with pytest.raises(PluginDeclarationError, match="must be literals"):
        discover_plugin_declarations(nonliteral)

    reserved = '''
@corex.node(id="custom.reserved.1234abcd", name="Reserved", category=("Tests",))
@corex.text("to_dict")
def reserved(ctx, settings): return {}
'''
    with pytest.raises(PluginDeclarationError, match="reserved"):
        discover_plugin_declarations(reserved)


def test_settings_access_is_validated_with_runtime_matching_diagnostics() -> None:
    typo = '''
@corex.node(id="custom.typo.1234abcd", name="Typo", category=("Tests",))
@corex.number("factor", default=2.0)
def typo(ctx, settings):
    return {"value": settings.factro}
'''
    with pytest.raises(PluginDeclarationError) as caught:
        discover_plugin_declarations(typo, filename="typo.py")

    settings = _Settings({"factor": 2.0})
    with pytest.raises(AttributeError) as runtime_error:
        _ = settings.factro
    assert runtime_error.value.args[0] in str(caught.value)
    assert "Did you mean 'factor'?" in str(caught.value)

    introspection = typo.replace("settings.factro", "getattr(settings, 'factor')")
    with pytest.raises(PluginDeclarationError, match="introspection"):
        discover_plugin_declarations(introspection)

    no_controls = '''
@corex.node(id="custom.no_controls.1234abcd", name="No Controls", category=("Tests",))
def no_controls(ctx): return {"value": settings.to_dict()}
'''
    with pytest.raises(PluginDeclarationError, match="only when controls"):
        discover_plugin_declarations(no_controls)


def test_settings_are_deeply_immutable_and_to_dict_is_defensive() -> None:
    authored_sequence = UserList([1, {"value": 2}])
    settings = _Settings(
        {
            "factor": 2.0,
            "nested": {"items": [1, {"value": 2}]},
            "flags": {"a", "b"},
            "sequence": authored_sequence,
        }
    )

    assert settings.factor == 2.0
    assert settings.nested["items"] == (1, {"value": 2})
    assert settings.flags == frozenset({"a", "b"})
    assert settings.sequence == (1, {"value": 2})
    authored_sequence[1]["value"] = 77
    assert settings.sequence[1]["value"] == 2
    with pytest.raises(AttributeError, match="immutable"):
        settings.factor = 3.0
    with pytest.raises(TypeError):
        settings.nested["items"] = ()

    mutable = settings.to_dict()
    mutable["nested"]["items"][1]["value"] = 99
    mutable["flags"].add("c")
    mutable["sequence"][1]["value"] = 88
    assert settings.nested["items"][1]["value"] == 2
    assert settings.flags == frozenset({"a", "b"})
    assert settings.sequence[1]["value"] == 2


def test_builtin_ids_require_explicit_trusted_parser_mode() -> None:
    source = '''
@corex.node(id="plot.signal", name="Signal Plot", category=("Plot",))
def signal(ctx): return {}
'''
    with pytest.raises(PluginDeclarationError, match="External node ids"):
        discover_plugin_declarations(source)

    with pytest.raises(ValueError, match="internal built-in owner"):
        discover_plugin_declarations(source, allow_reserved_ids=True)

    (declaration,) = discover_plugin_declarations(
        source,
        allow_reserved_ids=True,
        owner_id=INTERNAL_BUILTIN_FUNCTION_OWNER_ID,
    )
    assert declaration.spec.type_id == "plot.signal"


def test_trusted_non_builtin_owner_can_parse_property_group_and_visibility() -> None:
    source = '''
@corex.node(id="tabular.input", name="Tabular Input", category=("Tabular",))
@corex.text(
    "table",
    default="",
    _property_group="Internal",
    _inspector_visible=False,
)
def tabular_input(ctx, settings): return {}
'''

    (declaration,) = discover_plugin_declarations(
        source,
        allow_reserved_ids=True,
        owner_id="corex:addon:tabular",
        allow_internal_metadata=True,
    )

    assert declaration.spec.properties[0].group == "Internal"
    assert declaration.spec.properties[0].inspector_visible is False
    assert declaration.spec.settings_groups == ()


@pytest.mark.parametrize(
    "kwargs",
    (
        {"owner_id": "corex:addon:tabular", "allow_internal_metadata": True},
        {"allow_reserved_ids": True, "allow_internal_metadata": True},
        {
            "allow_reserved_ids": True,
            "owner_id": " ",
            "allow_internal_metadata": True,
        },
    ),
)
def test_internal_metadata_flag_requires_reserved_ids_and_non_empty_owner(
    kwargs: dict[str, object],
) -> None:
    with pytest.raises(ValueError, match="reserved node ids.*non-empty owner"):
        discover_plugin_declarations("", **kwargs)


def test_internal_control_fields_preserve_spec_order_and_customize_group_order() -> None:
    source = '''
@corex.node(id="plot.private_fields", name="Private Fields", category=("Plot",))
@corex.slider(
    "width",
    default=600,
    minimum=2,
    maximum=3840,
    description="Property width.",
    section="General",
    port=True,
    _port_description="Port width.",
    _section_order=1,
)
@corex.interval(
    "bounds",
    default=None,
    section="General",
    port=True,
    _section_order=0,
    _persistence_type=None,
)
def private_fields(ctx, settings):
    return {}
'''

    (declaration,) = discover_plugin_declarations(
        source,
        allow_reserved_ids=True,
        owner_id=INTERNAL_BUILTIN_FUNCTION_OWNER_ID,
    )

    assert [prop.key for prop in declaration.spec.properties] == ["width", "bounds"]
    assert [port.key for port in declaration.spec.ports] == ["width", "bounds"]
    assert [
        item.property_key for item in declaration.spec.settings_groups[0].items
    ] == ["bounds", "width"]
    assert declaration.spec.properties[0].description == "Property width."
    assert declaration.spec.ports[0].description == "Port width."
    assert declaration.spec.properties[1].persistence_data_type_id == ""


def test_internal_control_field_omission_preserves_public_defaults() -> None:
    source = '''
@corex.node(id="plot.private_defaults", name="Private Defaults", category=("Plot",))
@corex.interval("first", default=None, description="Shared.", section="General", port=True)
@corex.text("second", description="Second.", section="General", port=True)
def private_defaults(ctx, settings):
    return {}
'''

    (declaration,) = discover_plugin_declarations(
        source,
        allow_reserved_ids=True,
        owner_id=INTERNAL_BUILTIN_FUNCTION_OWNER_ID,
    )

    assert [
        item.property_key for item in declaration.spec.settings_groups[0].items
    ] == ["first", "second"]
    assert declaration.spec.ports[0].description == "Shared."
    assert declaration.spec.collapsible is True
    assert declaration.spec.surface_family == "standard"
    assert declaration.spec.surface_variant == ""
    assert declaration.spec.render_quality.supported_quality_tiers == ("full",)
    assert (
        declaration.spec.properties[0].persistence_data_type_id
        == "COREX.DataTypes.Interval1D"
    )


@pytest.mark.parametrize(
    "persistence_type",
    ("corex.Interval", '"COREX.DataTypes.Interval1D"'),
)
def test_internal_interval_accepts_explicit_interval_persistence_type(
    persistence_type: str,
) -> None:
    source = f'''
@corex.node(id="plot.private_persistence", name="Private", category=("Plot",))
@corex.interval("bounds", default=None, _persistence_type={persistence_type})
def private_persistence(ctx, settings): return {{}}
'''

    (declaration,) = discover_plugin_declarations(
        source,
        allow_reserved_ids=True,
        owner_id=INTERNAL_BUILTIN_FUNCTION_OWNER_ID,
    )
    assert (
        declaration.spec.properties[0].persistence_data_type_id
        == "COREX.DataTypes.Interval1D"
    )


def test_internal_typed_carrier_defaults_materialize_and_normalize() -> None:
    source = '''
PLANE_DEFAULT = {
    "data_type_id": "COREX.DataTypes.Plane",
    "schema_version": 1,
    "payload": {"origin": [0.0, 0.0, 0.0]},
}
POINT_DEFAULT = {
    "data_type_id": "COREX.DataTypes.Point3D",
    "schema_version": 2,
    "payload": {"x": 1.0, "y": 2.0, "z": 3.0},
}

@corex.node(id="reference.plane", name="Plane", category=("Reference",))
@corex.text(
    "value", _property_type="json", _property_default=PLANE_DEFAULT,
    _persistence_type="COREX.DataTypes.Plane",
)
def plane(ctx, settings): return {}

@corex.node(id="reference.point", name="Point", category=("Reference",))
@corex.text(
    "value", _property_type="json", _property_default=POINT_DEFAULT,
    _persistence_type="COREX.DataTypes.Point3D",
)
def point(ctx, settings): return {}

@corex.node(id="reference.json", name="JSON", category=("Reference",))
@corex.text(
    "value", _property_type="json", _property_default=PLANE_DEFAULT,
    _persistence_type=None,
)
def json_value(ctx, settings): return {}
'''

    plane, point, json_value = discover_internal(source)
    expected = (
        {
            "data_type_id": "COREX.DataTypes.Plane",
            "schema_version": 1,
            "payload": {"origin": [0.0, 0.0, 0.0]},
        },
        {
            "data_type_id": "COREX.DataTypes.Point3D",
            "schema_version": 2,
            "payload": {"x": 1.0, "y": 2.0, "z": 3.0},
        },
    )
    for declaration, carrier in zip((plane, point), expected, strict=True):
        default = declaration.spec.properties[0].default
        assert type(default) is TypedInlineValue
        assert asdict(default) == carrier

    assert json_value.spec.properties[0].default == expected[0]
    assert type(json_value.spec.properties[0].default) is dict

    registry = NodeRegistry()
    registry.data_types.register_many(
        types=tuple(
            DataTypeSpec(
                carrier["data_type_id"],
                carrier["data_type_id"],
                "graph",
                lambda payload: isinstance(payload, dict),
                carriers=frozenset({"inline"}),
                persistence="inline",
                payload_schema_version=carrier["schema_version"],
            )
            for carrier in expected
        ),
        owner_id="tests.typed_defaults",
    )
    for declaration in (plane, point):
        registry.register_descriptor(declaration.spec, lambda: None)  # type: ignore[arg-type]
        normalized = registry.default_properties(declaration.spec.type_id)["value"]
        assert type(normalized) is TypedInlineValue
        assert normalized == declaration.spec.properties[0].default
        assert normalized is not declaration.spec.properties[0].default


@pytest.mark.parametrize(
    ("carrier", "message"),
    (
        (
            {"data_type_id": "COREX.DataTypes.Other", "schema_version": 1, "payload": {}},
            "must match _persistence_type",
        ),
        (
            {"data_type_id": "COREX.DataTypes.Plane", "schema_version": 1},
            "must contain only",
        ),
        ({"schema_version": 1}, "must contain only"),
        (
            {
                "data_type_id": "COREX.DataTypes.Plane",
                "schema_version": 1,
                "payload": {},
                "extra": True,
            },
            "must contain only",
        ),
        (
            {"data_type_id": "COREX.DataTypes.Plane", "schema_version": 0, "payload": {}},
            "positive integer",
        ),
        (
            {"data_type_id": "COREX.DataTypes.Plane", "schema_version": True, "payload": {}},
            "positive integer",
        ),
        (
            {"data_type_id": "COREX.DataTypes.Plane", "schema_version": 1, "payload": []},
            "payload must be a mapping",
        ),
    ),
)
def test_internal_typed_carrier_defaults_reject_malformed_values(
    carrier: object,
    message: str,
) -> None:
    source = f'''
@corex.node(id="reference.bad", name="Bad", category=("Reference",))
@corex.text(
    "value", _property_type="json", _property_default={carrier!r},
    _persistence_type="COREX.DataTypes.Plane",
)
def bad(ctx, settings): return {{}}
'''

    with pytest.raises(PluginDeclarationError, match=message):
        discover_internal(source)


@pytest.mark.parametrize(
    ("decorator", "message"),
    (
        (
            '@corex.text("value", _port_description="Private")',
            "Private decorator field '_port_description'",
        ),
        (
            '@corex.text("value", _section_order=0)',
            "Private decorator field '_section_order'",
        ),
        (
            '@corex.interval("value", _persistence_type=None)',
            "Private decorator field '_persistence_type'",
        ),
    ),
)
def test_external_plugins_reject_internal_control_fields(
    decorator: str,
    message: str,
) -> None:
    source = f'''
@corex.node(id="custom.private.1234abcd", name="Private", category=("Tests",))
{decorator}
def private(ctx, settings): return {{}}
'''

    with pytest.raises(PluginDeclarationError, match=message):
        discover_plugin_declarations(source)


@pytest.mark.parametrize(
    ("decorator", "message"),
    (
        ('@corex.text("value", _port_description="Private")', "port=True"),
        ('@corex.text("value", section="General", _section_order=-1)', "non-negative"),
        (
            '@corex.interval("value", _persistence_type=corex.Color)',
            "corex.Interval",
        ),
        (
            '@corex.text("value", _section_order=0)',
            "requires a non-empty section",
        ),
    ),
)
def test_internal_control_fields_validate_their_narrow_contract(
    decorator: str,
    message: str,
) -> None:
    source = f'''
@corex.node(id="plot.private_validation", name="Private", category=("Tests",))
{decorator}
def private_validation(ctx, settings): return {{}}
'''

    with pytest.raises(PluginDeclarationError, match=message):
        discover_plugin_declarations(
            source,
            allow_reserved_ids=True,
            owner_id=INTERNAL_BUILTIN_FUNCTION_OWNER_ID,
        )


def test_internal_section_order_rejects_duplicates_deterministically() -> None:
    source = '''
@corex.node(id="plot.private_order", name="Private", category=("Tests",))
@corex.text("first", section="General", _section_order=0)
@corex.text("second", section="General", _section_order=0)
def private_order(ctx, settings): return {}
'''

    with pytest.raises(PluginDeclarationError, match="Duplicate _section_order 0"):
        discover_plugin_declarations(
            source,
            allow_reserved_ids=True,
            owner_id=INTERNAL_BUILTIN_FUNCTION_OWNER_ID,
        )


def test_runtime_decorators_ignore_internal_control_fields() -> None:
    @corex.node(id="plot.runtime_private", name="Runtime", category=("Tests",))
    @corex.interval("bounds", _persistence_type=None)
    @corex.text(
        "title",
        port=True,
        _port_description="Port title.",
        _section_order=0,
    )
    def runtime_private(ctx, settings):  # noqa: ANN001
        return {"ctx": ctx, "settings": settings}

    assert runtime_private("context", "settings") == {
        "ctx": "context",
        "settings": "settings",
    }


def test_internal_file_and_process_metadata_preserve_exact_specs() -> None:
    source = '''
@corex.node(id="io.file_read", name="File Read", category=("Input / Output",))
@corex.path(
    "path", default="", label="File Path", file_filter="Text files (*.txt)", port=True,
    _port_label="", _port_required=True, _port_description="File path.",
)
@corex.output("text", value_type=str, description="UTF-8 text.")
def file_read(ctx, settings): return {"text": ""}

@corex.node(id="io.process_run", name="Process Run", category=("Input / Output",))
@corex.text(
    "command", label="Command", port=True, _port_required=True,
    _port_structure="tree", _port_description="Command to run.",
)
@corex.text(
    "args", _property_type="json", _property_default=[], _inline_editor="",
    port=True, _port_value_type="COREX.DataTypes.StringList", _port_structure="tree",
)
@corex.text(
    "env", _property_type="json", _property_default={}, _inline_editor="",
)
@corex.output("exit_code", value_type=int)
def process_run(ctx, settings): return {"exit_code": 0}
'''

    file_read, process_run = discover_internal(source)
    assert [port.key for port in file_read.spec.ports] == ["path", "text"]
    assert [prop.key for prop in file_read.spec.properties] == ["path"]
    assert file_read.spec.ports[0].required is True
    assert file_read.spec.ports[0].label == ""
    assert file_read.spec.ports[0].uses_property_default is True

    assert [port.key for port in process_run.spec.ports] == [
        "command",
        "args",
        "exit_code",
    ]
    assert [prop.key for prop in process_run.spec.properties] == [
        "command",
        "args",
        "env",
    ]
    command, args, _exit_code = process_run.spec.ports
    assert (command.required, command.data_access) == (True, "tree")
    assert (args.data_type, args.data_access) == (
        "COREX.DataTypes.StringList",
        "tree",
    )
    assert process_run.spec.properties[1].type == "json"
    assert process_run.spec.properties[1].default == []
    assert process_run.spec.properties[1].inline_editor == ""
    assert process_run.spec.properties[2].default == {}


def test_internal_email_readiness_and_ssh_security_metadata_are_typed() -> None:
    source = '''
@corex.node(
    id="io.email_send", name="Email Send", category=("Input / Output",),
    _readiness_requirements=(
        {"any_of_properties": ("smtp_host",)},
        {"any_of_properties": ("sender",)},
        {"any_of_properties": ("to",)},
        {
            "any_of_properties": ("password",),
            "when_properties": ({"property_key": "username"},),
        },
    ),
)
@corex.text("smtp_host", default="localhost", label="SMTP Host")
@corex.text("sender", label="Sender")
@corex.text("to", label="To")
@corex.text("username", label="Username")
@corex.text("password", label="Password")
@corex.output("sent", value_type=bool)
def email_send(ctx, settings): return {"sent": True}

@corex.node(id="ssh_sftp.secret", name="Secret", category=("Control", "SSH/SFTP"))
@corex.text(
    "protected_value", label="Value", _property_type="json", _property_default={},
    _inline_editor="secret", _inspector_editor="secret", _sensitive=True,
    _sensitive_scope_key="data_protection_scope",
)
@corex.dropdown(
    "data_protection_scope", default="Current user",
    options=("Current user", "All users on this machine"),
    label="Data Protection Scope", _inspector_editor="enum",
)
@corex.output(
    "secret_value", value_type="SSH_SFTP_Connector.Nodes.Control.SSH_SFTP.SecretData",
)
def secret(ctx, settings): return {"secret_value": {}}

@corex.node(id="ssh_sftp.host", name="SSH Host", category=("Control", "SSH/SFTP"))
@corex.input(
    "private_key_path", value_type=str,
    _accepted_data_types=("COREX.DataTypes.String", "COREX.DataTypes.Path"),
)
@corex.output("host", value_type="SSH_SFTP_Connector.Nodes.Control.SSH_SFTP.SshSftpHostData")
def host(ctx, private_key_path): return {"host": {}}
'''

    email, secret, host = discover_internal(source)
    assert [requirement.any_of_properties for requirement in email.spec.readiness_requirements] == [
        ("smtp_host",),
        ("sender",),
        ("to",),
        ("password",),
    ]
    assert email.spec.readiness_requirements[-1].when_properties[0] == (
        PropertyConditionSpec("username")
    )
    protected_value = secret.spec.properties[0]
    assert (
        protected_value.type,
        protected_value.default,
        protected_value.inline_editor,
        protected_value.inspector_editor,
        protected_value.sensitive,
        protected_value.sensitive_scope_key,
    ) == ("json", {}, "secret", "secret", True, "data_protection_scope")
    assert host.spec.ports[0].accepted_data_types == (
        "COREX.DataTypes.String",
        "COREX.DataTypes.Path",
    )


@pytest.mark.parametrize(
    ("private_field", "value"),
    (
        ("_port_required", "True"),
        ("_port_label", '""'),
        ("_port_structure", '"tree"'),
        ("_port_uses_property_default", "False"),
        ("_port_value_type", '"COREX.DataTypes.Any"'),
        ("_port_accepted_data_types", '("COREX.DataTypes.Any",)'),
        ("_property_type", '"json"'),
        ("_property_default", "{}"),
        ("_inline_editor", '"secret"'),
        ("_inspector_editor", '"secret"'),
        ("_inspector_visible", "False"),
        ("_property_group", '"Internal"'),
        ("_sensitive", "True"),
        ("_sensitive_scope_key", '"scope"'),
    ),
)
def test_external_plugins_reject_all_private_control_fields(
    private_field: str,
    value: str,
) -> None:
    source = f'''
@corex.node(id="custom.private_t12.1234abcd", name="Private", category=("Tests",))
@corex.text("value", {private_field}={value})
def private_t12(ctx, settings): return {{}}
'''
    with pytest.raises(PluginDeclarationError, match="reserved for internal built-ins"):
        discover_plugin_declarations(source)


@pytest.mark.parametrize(
    "decorator",
    (
        '@corex.input("value", value_type=corex.Any, _accepted_data_types=("COREX.DataTypes.Any",))',
        '@corex.node(id="custom.private_node.1234abcd", name="Private", category=("Tests",), _readiness_requirements=())',
    ),
)
def test_external_plugins_reject_t12_private_input_and_node_fields(
    decorator: str,
) -> None:
    if decorator.startswith("@corex.node"):
        source = f"{decorator}\ndef private_node(ctx): return {{}}"
    else:
        source = f'''
@corex.node(id="custom.private_input.1234abcd", name="Private", category=("Tests",))
{decorator}
def private_input(ctx, value): return {{}}
'''
    with pytest.raises(PluginDeclarationError, match="reserved for internal built-ins"):
        discover_plugin_declarations(source)


@pytest.mark.parametrize(
    "field",
    (
        "_collapsible=False",
        '_property_output_collisions=("value",)',
        '_surface_family="viewer"',
        '_surface_variant="embedded"',
        '_render_quality_tiers=("full", "proxy")',
        '_solution_reuse_scope="durable"',
    ),
)
def test_external_plugins_reject_internal_node_surface_fields(field: str) -> None:
    source = f'''
@corex.node(
    id="custom.private_surface.1234abcd", name="Private", category=("Tests",),
    {field},
)
def private_surface(ctx): return {{}}
'''

    with pytest.raises(PluginDeclarationError, match="reserved for internal built-ins"):
        discover_plugin_declarations(source)


def test_public_function_declarations_are_hard_locked_to_never_reuse() -> None:
    source = '''
@corex.node(id="custom.reuse_default.1234abcd", name="Reuse", category=("Tests",))
def reuse_default(ctx): return {}
'''

    (declaration,) = discover_plugin_declarations(source)
    assert declaration.spec.solution_reuse_scope == "never"


@pytest.mark.parametrize(
    ("decorator", "message"),
    (
        ('@corex.input("value", value_type=corex.Any, _accepted_data_types="Bad")', "tuple or list"),
        (
            '@corex.input("value", value_type=corex.Any, _accepted_data_types=("Type.One", "Type.One"))',
            "duplicates",
        ),
        (
            '@corex.text("value", port=True, _port_structure="branch")',
            "item.*list.*tree",
        ),
        ('@corex.text("value", _property_type="object")', "_property_type"),
        ('@corex.text("value", _inline_editor="wizard")', "_inline_editor"),
        ('@corex.text("value", _inspector_visible="no")', "_inspector_visible"),
        ('@corex.text("value", _property_group=1)', "_property_group"),
        ('@corex.text("value", _sensitive=True)', "type json.*secret editor"),
        (
            '@corex.text("value", _sensitive_scope_key="scope")',
            "requires _sensitive=True",
        ),
    ),
)
def test_internal_t12_metadata_rejects_bad_values(
    decorator: str,
    message: str,
) -> None:
    source = f'''
@corex.node(id="io.private_validation", name="Private", category=("Tests",))
{decorator}
def private_validation(ctx, value): return {{}}
'''
    if "@corex.text" in decorator:
        source = source.replace("ctx, value", "ctx, settings")
    with pytest.raises(PluginDeclarationError, match=message):
        discover_internal(source)


@pytest.mark.parametrize(
    ("readiness", "message"),
    (
        ('{"any_of_properties": ("missing",)}', "unknown property"),
        ('{"when_properties": ()}', "at least one target"),
        ('{"any_of_properties": ("value",), "unsupported": ()}', "supported fields"),
        (
            '{"any_of_properties": ("value",), "when_properties": '
            '({"property_key": "missing"},)}',
            "unknown property",
        ),
    ),
)
def test_internal_readiness_rejects_unknown_or_malformed_literals(
    readiness: str,
    message: str,
) -> None:
    source = f'''
@corex.node(
    id="io.readiness_validation", name="Private", category=("Tests",),
    _readiness_requirements=({readiness},),
)
@corex.text("value")
def readiness_validation(ctx, settings): return {{}}
'''
    with pytest.raises(PluginDeclarationError, match=message):
        discover_internal(source)


def test_runtime_private_metadata_accepts_known_fields_and_rejects_unknown() -> None:
    @corex.node(
        id="io.runtime_private",
        name="Runtime",
        category=("Tests",),
        _collapsible=False,
        _property_output_collisions=(),
        _readiness_requirements=(),
        _render_quality_tiers=("full", "proxy"),
        _solution_reuse_scope="session",
        _surface_family="viewer",
        _surface_variant="embedded",
    )
    @corex.input("path", value_type=corex.Any, _accepted_data_types=("COREX.DataTypes.Path",))
    @corex.text(
        "value",
        _property_type="json",
        _property_default={},
        _inline_editor="secret",
        _inspector_editor="secret",
        _inspector_visible=False,
        _property_group="Internal",
        _sensitive=True,
        _sensitive_scope_key="scope",
        port=True,
        _port_required=True,
        _port_label="",
        _port_structure="tree",
        _port_uses_property_default=False,
        _port_value_type="COREX.DataTypes.Any",
        _port_accepted_data_types=("COREX.DataTypes.String",),
    )
    def runtime_private(ctx, path, settings):  # noqa: ANN001
        return ctx, path, settings

    assert runtime_private(1, 2, 3) == (1, 2, 3)
    with pytest.raises(TypeError, match="Unsupported private decorator field"):
        corex.text("value", _unknown_private=True)
    with pytest.raises(TypeError, match="Unsupported private decorator field"):
        corex.node(_unknown_private=True)


def test_internal_node_surface_metadata_maps_to_node_type_spec() -> None:
    source = '''
@corex.node(
    id="engineering.viewer", name="Viewer", category=("Engineering",),
    _collapsible=False, _surface_family="viewer", _surface_variant="embedded",
    _render_quality_tiers=("full", "proxy"),
    _solution_reuse_scope="session",
)
@corex.output("session", value_type=corex.Any)
def viewer(ctx): return {"session": None}
'''

    (declaration,) = discover_internal(source)

    assert declaration.spec.collapsible is False
    assert declaration.spec.surface_family == "viewer"
    assert declaration.spec.surface_variant == "embedded"
    assert declaration.spec.render_quality.supported_quality_tiers == (
        "full",
        "proxy",
    )
    assert declaration.spec.solution_reuse_scope == "session"


@pytest.mark.parametrize(
    ("value", "message"),
    (
        ('"full"', "tuple or list"),
        ("()", "one to three"),
        ('("full", "reduced", "proxy", "full")', "one to three"),
        ('("draft",)', "values must be"),
        ('("full", "full")', "duplicates"),
    ),
)
def test_internal_render_quality_tiers_validate_bounds_and_values(
    value: str,
    message: str,
) -> None:
    source = f'''
@corex.node(
    id="engineering.viewer", name="Viewer", category=("Engineering",),
    _render_quality_tiers={value},
)
def viewer(ctx): return {{}}
'''

    with pytest.raises(PluginDeclarationError, match=message):
        discover_internal(source)


@pytest.mark.parametrize(
    ("field", "message"),
    (
        ("_collapsible=0", "true or false"),
        ("_surface_family=1", "non-empty trimmed string"),
        ('_surface_family=" viewer"', "non-empty trimmed string"),
        ("_surface_variant=1", "trimmed string"),
        ('_surface_variant=" embedded"', "trimmed string"),
        ('_solution_reuse_scope="global"', "never.*session.*durable"),
        ("_solution_reuse_scope=[]", "never.*session.*durable"),
    ),
)
def test_internal_node_surface_fields_validate_types(
    field: str,
    message: str,
) -> None:
    source = f'''
@corex.node(id="engineering.viewer", name="Viewer", category=("Engineering",), {field})
def viewer(ctx): return {{}}
'''

    with pytest.raises(PluginDeclarationError, match=message):
        discover_internal(source)


def test_internal_control_port_can_remain_a_normal_function_argument() -> None:
    source = '''
@corex.node(id="reference.plane_container", name="Plane", category=("Reference",))
@corex.text(
    "input", port=True, _property_type="json", _property_default={},
    _port_value_type="COREX.DataTypes.Plane", _port_uses_property_default=False,
)
@corex.output("output", value_type="COREX.DataTypes.Plane")
def plane_container(ctx, input, settings):
    return {"output": input if input is not None else settings.input}
'''

    (declaration,) = discover_internal(source)

    assert declaration.input_keys == ("input",)
    assert declaration.control_keys == ("input",)
    assert declaration.spec.ports[0].uses_property_default is False
    assert declaration.spec.properties[0].key == "input"


@pytest.mark.parametrize(
    ("decorator", "signature", "message"),
    (
        (
            '@corex.text("value", _port_uses_property_default=False)',
            "ctx, settings",
            "port=True",
        ),
        (
            '@corex.text("value", port=True, _port_uses_property_default="no")',
            "ctx, value, settings",
            "true or false",
        ),
    ),
)
def test_internal_port_default_flag_requires_a_boolean_port(
    decorator: str,
    signature: str,
    message: str,
) -> None:
    source = f'''
@corex.node(id="reference.flag", name="Flag", category=("Reference",))
{decorator}
def flag({signature}): return {{}}
'''

    with pytest.raises(PluginDeclarationError, match=message):
        discover_internal(source)


def test_internal_property_output_collision_requires_exact_node_allowlist() -> None:
    source = '''
@corex.node(
    id="core.constant", name="Constant", category=("Core",),
    _property_output_collisions=("value",),
)
@corex.output("value", value_type=corex.Any)
@corex.text("value", default="")
def constant(ctx, settings): return {"value": settings.value}
'''

    (declaration,) = discover_internal(source)
    assert [prop.key for prop in declaration.spec.properties] == ["value"]
    assert [port.key for port in declaration.spec.ports] == ["value"]


@pytest.mark.parametrize(
    ("metadata", "control", "message"),
    (
        (
            '_property_output_collisions=("missing",)',
            '@corex.text("value")',
            "cross-direction",
        ),
        ('_property_output_collisions=("value", "value")', '@corex.text("value")', "duplicates"),
        ('_property_output_collisions="value"', '@corex.text("value")', "tuple or list"),
        ('_property_output_collisions=("value",)', '@corex.text("value", port=True)', "cross-direction"),
    ),
)
def test_internal_property_output_collision_allowlist_is_narrow(
    metadata: str,
    control: str,
    message: str,
) -> None:
    source = f'''
@corex.node(id="core.constant", name="Constant", category=("Core",), {metadata})
@corex.output("value", value_type=corex.Any)
{control}
def constant(ctx, settings): return {{"value": settings.value}}
'''

    with pytest.raises(PluginDeclarationError, match=message):
        discover_internal(source)


def test_internal_property_output_collision_allowlist_rejects_unused_keys() -> None:
    source = '''
@corex.node(
    id="core.constant", name="Constant", category=("Core",),
    _property_output_collisions=("missing",),
)
@corex.output("result", value_type=corex.Any)
@corex.text("value")
def constant(ctx, settings): return {"result": settings.value}
'''

    with pytest.raises(PluginDeclarationError, match="actual property/output"):
        discover_internal(source)


def test_internal_property_output_collision_allowlist_is_bounded() -> None:
    keys = ", ".join(repr(f"key_{index}") for index in range(33))
    source = f'''
@corex.node(
    id="core.constant", name="Constant", category=("Core",),
    _property_output_collisions=({keys},),
)
def constant(ctx): return {{}}
'''

    with pytest.raises(PluginDeclarationError, match="too many keys"):
        discover_internal(source)


def test_source_and_decorator_counts_are_bounded() -> None:
    with pytest.raises(PluginDeclarationError, match="source is too large"):
        discover_plugin_declarations("#" * (256 * 1024 + 1))

    decorators = "\n".join(f'@corex.input("value_{index}", value_type=corex.Any)' for index in range(129))
    parameters = ", ".join(f"value_{index}" for index in range(129))
    source = f'''
@corex.node(id="custom.large.1234abcd", name="Large", category=("Tests",))
{decorators}
def large(ctx, {parameters}): return {{}}
'''
    with pytest.raises(PluginDeclarationError, match="too many decorators"):
        discover_plugin_declarations(source)

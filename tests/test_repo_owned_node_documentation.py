from __future__ import annotations

from ea_node_editor.addons.mars.function_nodes import SOURCE as MARS_SOURCE
from ea_node_editor.addons.mars.metadata import MARS_ADDON_ID
from ea_node_editor.addons.mechanical.catalog import MECHANICAL_ADDON_ID
from ea_node_editor.addons.mechanical.function_nodes import SOURCE as MECHANICAL_SOURCE
from ea_node_editor.addons.tabular_data.catalog import TABULAR_DATA_FUNCTION_TYPE_IDS
from ea_node_editor.nodes.bootstrap import build_builtin_registry, build_default_registry
from ea_node_editor.nodes.plugin_declaration import discover_plugin_declarations
from ea_node_editor.nodes.instance_resolution import resolve_instance_ports
from tests.repo_owned_catalog_fixture import load_current_repo_owned_catalog


_TABULAR_DATA_REGISTRY = build_default_registry(include_public_plugins=False)
_MARS_SPECS = tuple(
    declaration.spec
    for declaration in discover_plugin_declarations(
        MARS_SOURCE,
        filename="mars_nodes.py",
        allow_reserved_ids=True,
        owner_id=MARS_ADDON_ID,
        allow_internal_metadata=True,
    )
)
_MECHANICAL_SPECS = tuple(
    declaration.spec
    for declaration in discover_plugin_declarations(
        MECHANICAL_SOURCE,
        filename="mechanical_nodes.py",
        allow_reserved_ids=True,
        owner_id=MECHANICAL_ADDON_ID,
        allow_internal_metadata=True,
    )
)
REPO_OWNED_NODE_SPECS = (
    *build_builtin_registry().all_specs(),
    *(
        _TABULAR_DATA_REGISTRY.get_spec(type_id)
        for type_id in TABULAR_DATA_FUNCTION_TYPE_IDS
    ),
    *_MARS_SPECS,
    *_MECHANICAL_SPECS,
)


def test_all_repo_owned_nodes_have_authored_documentation() -> None:
    specs = REPO_OWNED_NODE_SPECS
    resolved_ports = tuple((spec, resolve_instance_ports(spec, {})) for spec in specs)

    assert len(specs) == 147
    assert sum(len(ports) for _, ports in resolved_ports) == 616
    assert len({spec.type_id for spec in specs}) == len(specs)

    missing_node_descriptions = [spec.type_id for spec in specs if not spec.description.strip()]
    missing_keywords = [spec.type_id for spec in specs if not spec.keywords]
    missing_port_descriptions = [
        f"{spec.type_id}.{port.key}"
        for spec, ports in resolved_ports
        for port in ports
        if not port.description.strip()
    ]

    assert missing_node_descriptions == []
    assert missing_keywords == []
    assert missing_port_descriptions == []


def test_repo_owned_catalog_fixture_has_exact_scope() -> None:
    assert len(load_current_repo_owned_catalog()) == 147

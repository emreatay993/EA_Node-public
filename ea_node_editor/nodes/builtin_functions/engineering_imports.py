# Purpose: Hold inert decorated source for neutral CAD and FE import built-ins.
# Map: feature_routes/neutral_cad_fe_engineering_viewer.md
# Tests: tests/test_engineering_import_nodes.py

SOURCE = r'''import corex

from ea_node_editor.nodes.builtins.engineering_imports import execute_engineering_import


@corex.node(
    id="engineering.fe_import",
    _solution_reuse_scope="session",
    name="FE Import",
    category=("Engineering", "Import"),
    icon="integrations/download.svg",
    description="Imports a neutral finite-element file as a prepared COREX scene.",
    keywords=("finite element", "mesh", "import"),
)
@corex.path(
    "path",
    default="",
    label="FE File",
    file_filter="Neutral FE Files (*.vtk *.vtu *.vtm *.vtkhdf *.e *.exo *.ex2 *.xdmf *.xmf);;All Files (*)",
    port=True,
    _inline_editor="",
    _inspector_editor="",
    _port_accepted_data_types=(),
    _port_description="Path to the neutral finite-element file to import.",
    _port_label="",
    _port_required=True,
    _port_structure="item",
    _port_value_type="COREX.DataTypes.Path",
)
@corex.output(
    "scene",
    value_type="COREX.Engineering.Scene",
    label="",
    description="Prepared finite-element scene for viewing or downstream processing.",
)
@corex.dropdown(
    "length_unit",
    default="file",
    options=("file", "m", "mm", "cm", "in", "ft"),
    label="Length Unit",
    _inline_editor="",
    _inspector_editor="",
    _property_group="Import",
)
def fe_import(ctx, settings):
    result = execute_engineering_import(ctx, source_kind="fe")
    for warning in result.warnings:
        ctx.warn(warning, code="fe_import")
    return dict(result.outputs)


@corex.node(
    id="engineering.cad_import",
    _solution_reuse_scope="session",
    name="CAD Import",
    category=("Engineering", "Import"),
    icon="integrations/download.svg",
    description="Imports a neutral CAD file as a prepared COREX scene.",
    keywords=("cad", "geometry", "import"),
)
@corex.path(
    "path",
    default="",
    label="CAD File",
    file_filter="Neutral CAD Files (*.stl *.step *.stp *.iges *.igs *.brep);;All Files (*)",
    port=True,
    _inline_editor="",
    _inspector_editor="",
    _port_accepted_data_types=(),
    _port_description="Path to the neutral CAD file to import.",
    _port_label="",
    _port_required=True,
    _port_structure="item",
    _port_value_type="COREX.DataTypes.Path",
)
@corex.output(
    "scene",
    value_type="COREX.Engineering.Scene",
    label="",
    description="Prepared CAD scene for viewing or downstream processing.",
)
@corex.dropdown(
    "length_unit",
    default="file",
    options=("file", "m", "mm", "cm", "in", "ft"),
    label="Length Unit",
    _inline_editor="",
    _inspector_editor="",
    _property_group="Import",
)
def cad_import(ctx, settings):
    result = execute_engineering_import(ctx, source_kind="cad")
    for warning in result.warnings:
        ctx.warn(warning, code="cad_import")
    return dict(result.outputs)
'''

__all__ = ["SOURCE"]

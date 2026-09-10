# Purpose: Hold inert decorated source for SQLite vector database nodes.
# Map: subsystems/nodes_registry_builtins.md
# Tests: tests/test_ai_ml_contracts.py

SOURCE = r"""import corex

from ea_node_editor.nodes.builtins.ai_ml_contracts import (
    execute_create_vector_collection,
    execute_inspect_vector_collection,
    execute_sqlite_vector_database,
)


@corex.node(
    id="ai.sqlite_vector_database",
    name="SQLite Vector Database",
    category=("AI", "Vector Database"),
    icon="database",
    description="Initializes or reopens a local COREX SQLite vector database.",
    keywords=("sqlite", "vector", "database"),
)
@corex.path(
    "file_path",
    default="",
    label="File Path",
    file_filter="SQLite database (*.db *.sqlite *.sqlite3)",
    port=True,
    _inline_editor="",
    _port_accepted_data_types=(),
    _port_description="Absolute local path for the SQLite database.",
    _port_label="File Path",
    _port_required=True,
    _port_structure="item",
    _port_value_type="COREX.DataTypes.String",
)
@corex.output(
    "vector_database",
    value_type="AdvancedAiModule.VectorDb.DataTypes.VectorDbConnection",
    label="Vector Database",
    description="Validated SQLite vector database locator.",
)
def sqlite_vector_database(ctx, settings):
    return dict(execute_sqlite_vector_database(ctx).outputs)


@corex.node(
    id="ai.create_vector_collection",
    name="Create Vector Collection",
    category=("AI", "Vector Database"),
    icon="database",
    description="Creates an idempotent collection entry in a COREX vector database.",
    keywords=("vector", "collection", "create", "sqlite"),
)
@corex.input(
    "vector_database",
    value_type="AdvancedAiModule.VectorDb.DataTypes.VectorDbConnection",
    required=True,
    label="Vector Database",
    description="SQLite vector database locator.",
)
@corex.text(
    "collection_name",
    default="",
    label="Collection Name",
    port=True,
    _inline_editor="",
    _port_description="Unique ASCII collection name.",
    _port_label="Collection Name",
    _port_required=True,
    _port_value_type="COREX.DataTypes.String",
)
@corex.number(
    "vector_dimension",
    default=1,
    minimum=1,
    maximum=65536,
    label="Vector Dimension",
    port=True,
    _inline_editor="",
    _port_description="Number of scalar components in each vector.",
    _port_label="Vector Dimension",
    _port_required=True,
    _port_value_type="COREX.DataTypes.Int",
)
@corex.dropdown(
    "distance_metric",
    default="Cosine",
    options=("Cosine", "Euclidean"),
    label="Distance Metric",
    port=True,
    _port_description="Cosine or Euclidean distance metric.",
    _port_label="Distance Metric",
    _port_required=True,
    _port_value_type="COREX.DataTypes.String",
)
@corex.text(
    "additional_metadata",
    default="",
    label="Additional Metadata",
    port=True,
    _inline_editor="",
    _property_default={},
    _property_type="json",
    _port_description="Bounded non-sensitive JSON metadata.",
    _port_label="Additional Metadata",
    _port_required=False,
    _port_value_type="COREX.DataTypes.GraphDictionary",
)
@corex.output(
    "vector_collection",
    value_type="AdvancedAiModule.VectorDb.DataTypes.VectorCollection",
    label="Vector Collection",
    description="Locator for the created vector collection.",
)
def create_vector_collection(ctx, vector_database, settings):
    return dict(execute_create_vector_collection(ctx).outputs)


@corex.node(
    id="ai.inspect_vector_collection",
    name="Inspect Vector Collection",
    category=("AI", "Vector Database"),
    icon="database",
    description="Reads validated metadata for a COREX vector collection.",
    keywords=("vector", "collection", "inspect", "sqlite"),
)
@corex.input(
    "vector_collection",
    value_type="AdvancedAiModule.VectorDb.DataTypes.VectorCollection",
    required=True,
    label="Vector Collection",
    description="Vector collection locator to inspect.",
)
@corex.output(
    "name",
    value_type="COREX.DataTypes.String",
    label="Name",
    description="Collection name.",
)
@corex.output(
    "record_count",
    value_type="COREX.DataTypes.Int",
    label="Record Count",
    description="Record count, fixed at zero until record storage exists.",
)
@corex.output(
    "vector_dimension",
    value_type="COREX.DataTypes.Int",
    label="Vector Dimension",
    description="Number of scalar components in each vector.",
)
@corex.output(
    "distance_metric",
    value_type="COREX.DataTypes.String",
    label="Distance Metric",
    description="Configured distance metric.",
)
@corex.output(
    "metadata",
    value_type="COREX.DataTypes.GraphDictionary",
    label="Metadata",
    description="Detached collection metadata.",
)
def inspect_vector_collection(ctx, vector_collection):
    return dict(execute_inspect_vector_collection(ctx).outputs)
"""

__all__ = ["SOURCE"]

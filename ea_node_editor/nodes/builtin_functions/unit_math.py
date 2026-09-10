# Purpose: Hold inert decorated source for ordinary unit and math built-ins.
# Map: subsystems/nodes_registry_builtins.md
# Tests: tests/test_core_unit_nodes.py, tests/test_interval_nodes.py

SOURCE = '''import corex

from ea_node_editor.nodes.builtins.core_media import (
    CELL_DATA_TYPE_ID,
    DATETIME_DATA_TYPE_ID,
    INTERVAL_2D_DATA_TYPE_ID,
    TENSOR_DATA_TYPE_ID,
    is_cell_payload,
    is_datetime_payload,
    is_interval_2d_payload,
    is_tensor_payload,
)
from ea_node_editor.nodes.builtins.tree_path import (
    make_tree_path_value,
    tree_path_indices,
)
from ea_node_editor.nodes.builtins.units import (
    LENGTH_DATA_TYPE_ID,
    PLANE_ANGLE_DATA_TYPE_ID,
    TIME_DATA_TYPE_ID,
    UNIT_SYSTEM_DATA_TYPE_ID,
    is_length_payload,
    is_plane_angle_payload,
    is_time_payload,
    is_unit_system_payload,
)
from ea_node_editor.runtime_contracts import (
    Interval1D,
    TypedInlineValue,
    coerce_interval_1d,
)


_INT32_MAX = 2_147_483_647
_QUANTITY_VALIDATORS = (
    (LENGTH_DATA_TYPE_ID, is_length_payload),
    (PLANE_ANGLE_DATA_TYPE_ID, is_plane_angle_payload),
    (TIME_DATA_TYPE_ID, is_time_payload),
)


def _typed_payload(value, data_type_id, validator):
    if (
        type(value) is not TypedInlineValue
        or type(value.data_type_id) is not str
        or value.data_type_id != data_type_id
        or type(value.schema_version) is not int
        or value.schema_version != 1
        or not validator(value.payload)
    ):
        raise ValueError(f"{data_type_id} input is invalid")
    return value.payload


def _normalize_excel_column(value):
    if type(value) is not str or not value:
        raise ValueError("column must be an ASCII column name or positive Int32")
    if all(("A" <= char <= "Z") or ("a" <= char <= "z") for char in value):
        return value.upper()
    if not all("0" <= char <= "9" for char in value):
        raise ValueError("column must be an ASCII column name or positive Int32")
    digits = value.lstrip("0")
    if (
        not digits
        or len(digits) > 10
        or (len(digits) == 10 and digits > str(_INT32_MAX))
    ):
        raise ValueError("column number must be a positive Int32")
    index = int(digits)
    letters = []
    while index:
        index, remainder = divmod(index - 1, 26)
        letters.append(chr(ord("A") + remainder))
    return "".join(reversed(letters))


def _validated_quantity(value):
    if value is None:
        return None
    if type(value) is not TypedInlineValue or type(value.data_type_id) is not str:
        raise ValueError("physical quantity input is invalid")
    for data_type_id, validator in _QUANTITY_VALIDATORS:
        if value.data_type_id == data_type_id:
            _typed_payload(value, data_type_id, validator)
            return value
    raise ValueError("physical quantity input is invalid")


@corex.node(
    id="data.construct_path",
    _solution_reuse_scope="durable",
    name="Construct Path",
    category=("Data Structure", "Tree"),
    icon="account_tree",
    description="Construct a path of a data tree branch using a list of indices.",
    keywords=("data", "tree", "path", "construct"),
)
@corex.input(
    "indices",
    value_type="COREX.DataTypes.Int",
    structure="list",
    label="Indices",
    required=True,
    description="Path indices.",
)
@corex.output(
    "path",
    value_type="COREX.DataTree.Path",
    label="Path",
    description="Path defined by the given indices.",
)
def construct_path(ctx, indices):
    return {"path": make_tree_path_value(indices)}


@corex.node(
    id="data.deconstruct_path",
    _solution_reuse_scope="durable",
    name="Deconstruct Path",
    category=("Data Structure", "Tree"),
    icon="account_tree",
    description="Deconstruct a path of a data tree into a list of integers.",
    keywords=("data", "tree", "path", "deconstruct"),
)
@corex.input(
    "path",
    value_type="COREX.DataTree.Path",
    label="Path",
    required=True,
    description="Path to deconstruct into its indices.",
)
@corex.output(
    "indices",
    value_type="COREX.DataTypes.Int",
    structure="list",
    label="Indices",
    description="Indices of the path.",
)
def deconstruct_path(ctx, path):
    return {"indices": tree_path_indices(path)}


@corex.node(
    id="utilities.deconstruct_date_time",
    _solution_reuse_scope="durable",
    name="Deconstruct Date and Time",
    category=("Utilities", "Time"),
    icon="schedule",
    description="Extracts the integer components of a typed COREX date and time.",
    keywords=("date", "time", "deconstruct"),
)
@corex.input(
    "date_and_time",
    value_type="COREX.DataTypes.DateTime",
    label="Date and time",
    required=True,
    description="The date and time to deconstruct.",
)
@corex.output(
    "year", value_type="COREX.DataTypes.Int", label="Year", description="Year component."
)
@corex.output(
    "month",
    value_type="COREX.DataTypes.Int",
    label="Month",
    description="Month component.",
)
@corex.output(
    "day", value_type="COREX.DataTypes.Int", label="Day", description="Day component."
)
@corex.output(
    "hour", value_type="COREX.DataTypes.Int", label="Hour", description="Hour component."
)
@corex.output(
    "minute",
    value_type="COREX.DataTypes.Int",
    label="Minute",
    description="Minute component.",
)
@corex.output(
    "second",
    value_type="COREX.DataTypes.Int",
    label="Second",
    description="Second component.",
)
@corex.output(
    "millisecond",
    value_type="COREX.DataTypes.Int",
    label="Millisecond",
    description="Millisecond component.",
)
def deconstruct_date_time(ctx, date_and_time):
    payload = _typed_payload(date_and_time, DATETIME_DATA_TYPE_ID, is_datetime_payload)
    return {
        key: payload[key]
        for key in (
            "year",
            "month",
            "day",
            "hour",
            "minute",
            "second",
            "millisecond",
        )
    }


@corex.node(
    id="math.deconstruct_tensor",
    _solution_reuse_scope="durable",
    name="Deconstruct Tensor",
    category=("Math", "Tensor"),
    icon="view_in_ar",
    description="Deconstruct a Tensor to retrieve data and shape.",
    keywords=("tensor", "deconstruct", "dimensions"),
)
@corex.input(
    "tensor",
    value_type="COREX.DataTypes.Tensor",
    label="Tensor",
    required=True,
    description="A Tensor representation of data.",
)
@corex.output(
    "data",
    value_type="COREX.DataTypes.Double",
    structure="list",
    label="Values",
    description="The values in the tensor.",
)
@corex.output(
    "dimensions",
    value_type="COREX.DataTypes.Int",
    structure="list",
    label="Shape",
    description="The shape of the tensor.",
)
def deconstruct_tensor(ctx, tensor):
    payload = _typed_payload(tensor, TENSOR_DATA_TYPE_ID, is_tensor_payload)
    return {
        "data": list(payload["data"]),
        "dimensions": list(payload["dimensions"]),
    }


@corex.node(
    id="data.excel_cell",
    _solution_reuse_scope="session",
    name="Excel Cell",
    category=("Data", "Excel"),
    icon="grid_on",
    description="Define an Excel cell by its column and row.",
    keywords=("excel", "cell", "column", "row"),
)
@corex.input(
    "column",
    value_type="COREX.DataTypes.String",
    label="Column",
    required=True,
    description="Column of the Excel cell starting at A or 1.",
)
@corex.input(
    "row",
    value_type="COREX.DataTypes.Int",
    label="Row",
    required=True,
    description="Row of the Excel cell starting at 1.",
)
@corex.output(
    "cell",
    value_type="COREX.DataTypes.Cell",
    label="Cell",
    description="Excel cell defined by column and row.",
)
def excel_cell(ctx, column, row):
    if type(row) is not int or not 1 <= row <= _INT32_MAX:
        raise ValueError("row must be a positive Int32")
    payload = {"Column": _normalize_excel_column(column), "Row": row}
    if not is_cell_payload(payload):
        raise ValueError("cell payload is invalid")
    return {"cell": TypedInlineValue(CELL_DATA_TYPE_ID, 1, payload)}


@corex.node(
    id="math.deconstruct_interval_2d",
    _solution_reuse_scope="durable",
    name="Deconstruct Interval 2D",
    category=("Math", "Interval"),
    icon="aspect_ratio",
    description="Deconstruct a 2D numeric interval into its u- and v-intervals.",
    keywords=("interval", "2d", "deconstruct"),
)
@corex.input(
    "interval",
    value_type="COREX.DataTypes.Interval2D",
    label="Interval 2D",
    required=True,
    description="Interval to deconstruct into its u- and v-interval.",
)
@corex.output(
    "u",
    value_type="COREX.DataTypes.Interval1D",
    label="U-interval",
    description="Interval in the u-direction of the 2D-interval.",
)
@corex.output(
    "v",
    value_type="COREX.DataTypes.Interval1D",
    label="V-interval",
    description="Interval in the v-direction of the 2D-interval.",
)
def deconstruct_interval_2d(ctx, interval):
    payload = _typed_payload(interval, INTERVAL_2D_DATA_TYPE_ID, is_interval_2d_payload)
    return {
        axis: Interval1D(payload[axis]["start"], payload[axis]["end"])
        for axis in ("u", "v")
    }


@corex.node(
    id="math.physical_quantity_container",
    _solution_reuse_scope="session",
    name="Physical Quantity",
    category=("Math", "Container"),
    icon="straighten",
    description="Passes through an optional typed physical quantity.",
    keywords=("physical", "quantity", "container", "units"),
)
@corex.input(
    "input",
    value_type="COREX.DataTypes.Units.IQuantity",
    label="Input",
    required=False,
    description="Optional physical quantity to pass through.",
)
@corex.output(
    "output",
    value_type="COREX.DataTypes.Units.IQuantity",
    label="Output",
    description="Validated physical quantity, when supplied.",
)
def physical_quantity_container(ctx, input):
    if "input" not in ctx.inputs:
        return {}
    return {"output": _validated_quantity(input)}


@corex.node(
    id="math.unit_system_container",
    _solution_reuse_scope="durable",
    name="Unit System",
    category=("Math", "Container"),
    icon="square_foot",
    description="Passes through an optional typed Unit System.",
    keywords=("unit", "system", "container"),
)
@corex.input(
    "input",
    value_type="COREX.DataTypes.Units.UnitSystem",
    label="Input",
    required=False,
    description="Optional unit system to pass through.",
)
@corex.output(
    "output",
    value_type="COREX.DataTypes.Units.UnitSystem",
    label="Output",
    description="Validated unit system, when supplied.",
)
def unit_system_container(ctx, input):
    if "input" not in ctx.inputs:
        return {}
    if input is not None:
        _typed_payload(input, UNIT_SYSTEM_DATA_TYPE_ID, is_unit_system_payload)
    return {"output": input}


@corex.node(
    id="math.deconstruct_interval",
    _solution_reuse_scope="durable",
    name="Deconstruct Interval",
    category=("Math", "Interval"),
    icon="core/data_object.svg",
    description="Extracts the original ordered Start and End endpoints from an Interval 1D.",
    keywords=("interval", "deconstruct", "range", "start", "end"),
)
@corex.input(
    "interval",
    value_type="COREX.DataTypes.Interval1D",
    label="Interval",
    required=True,
    description="Interval 1D whose original endpoints will be extracted.",
)
@corex.output(
    "start",
    value_type="COREX.DataTypes.Double",
    label="",
    description="Original Interval 1D Start endpoint.",
)
@corex.output(
    "end",
    value_type="COREX.DataTypes.Double",
    label="",
    description="Original Interval 1D End endpoint.",
)
def deconstruct_interval(ctx, interval):
    value = coerce_interval_1d(interval)
    return {"start": value.start, "end": value.end}


@corex.node(
    id="math.construct_interval",
    _solution_reuse_scope="durable",
    name="Construct Interval",
    category=("Math", "Interval"),
    icon="core/data_object.svg",
    description="Constructs an ordered Interval 1D from Start and End values.",
    keywords=("interval", "construct", "range", "start", "end"),
)
@corex.number(
    "start",
    default=0.0,
    label="Start",
    port=True,
    _port_value_type="COREX.DataTypes.Double",
    _port_accepted_data_types=("COREX.DataTypes.Int",),
    _port_description="Interval start value; overrides the configured Start property when connected.",
)
@corex.number(
    "end",
    default=1.0,
    label="End",
    port=True,
    _port_value_type="COREX.DataTypes.Double",
    _port_accepted_data_types=("COREX.DataTypes.Int",),
    _port_description="Interval end value; overrides the configured End property when connected.",
)
@corex.output(
    "interval",
    value_type="COREX.DataTypes.Interval1D",
    label="",
    description="Ordered Interval 1D containing the original Start and End endpoints.",
)
def construct_interval(ctx, settings):
    del ctx
    return {"interval": Interval1D(settings.start, settings.end)}
'''

__all__ = ["SOURCE"]

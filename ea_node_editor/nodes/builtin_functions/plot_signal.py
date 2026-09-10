# Purpose: Hold inert decorated source for the Signal Plot built-in.
# Map: feature_routes/plotter_nodes
# Tests: tests/test_signal_plot_renderer.py

SOURCE = r'''import corex

from ea_node_editor.execution.signal_plot_renderer import render_signal_plot


LEGEND_LABELS = (
    "Upper left",
    "Upper center",
    "Upper right",
    "Middle left",
    "Middle center",
    "Middle right",
    "Lower left",
    "Lower center",
    "Lower right",
)
LEGEND_CODES = (0, 1, 2, 3, 4, 5, 6, 7, 8)
LINE_STYLE_LABELS = ("None", "Solid", "Dash", "Dash Dot", "Dash Dot Dot", "Dot")
LINE_STYLE_CODES = (0, 1, 2, 3, 4, 5)
MARKER_LABELS = (
    "None",
    "Filled circle",
    "Filled square",
    "Open circle",
    "Open square",
    "Filled diamond",
    "Open diamond",
    "Asterisk",
    "Hashtag",
    "Cross",
    "X",
    "Vertical bar",
    "Tri upwards",
    "Tri downwards",
    "Filled triangle upwards",
    "Filled triangle downwards",
    "Open triangle upwards",
    "Open triangle downwards",
)
MARKER_CODES = (0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17)


@corex.node(
    id="plot.signal",
    _solution_reuse_scope="durable",
    name="Signal Plot",
    category=("Plot",),
    icon="show_chart",
    description="Plot numeric signals, arrays and table columns against sample index or explicit numeric/datetime X values.",
    keywords=("signal", "line plot", "chart"),
)
@corex.slider(
    "width",
    default=600,
    minimum=2,
    maximum=3840,
    step=1,
    label="Width",
    section="General options",
    port=True,
    _port_description="Width of the image.",
    _section_order=0,
)
@corex.slider(
    "height",
    default=400,
    minimum=2,
    maximum=2160,
    step=1,
    label="Height",
    section="General options",
    port=True,
    _port_description="Height of the image.",
    _section_order=1,
)
@corex.text(
    "title",
    default="",
    label="Title",
    section="General options",
    port=True,
    _port_description="Title of the plot.",
    _section_order=2,
)
@corex.slider(
    "font_size",
    default=12,
    minimum=1,
    maximum=72,
    step=1,
    label="Font size",
    section="General options",
    port=True,
    _port_description="Specify the font size for your plot.",
    _section_order=3,
)
@corex.list(
    "labels",
    default=[],
    item_type=str,
    label="Labels",
    section="General options",
    port=True,
    _port_description="Label for each plotted trace. Leave empty to use source column names.",
    _section_order=4,
)
@corex.switch(
    "show_legend",
    default=False,
    label="Show legend",
    section="General options",
    port=True,
    _port_description="Input 'True' to show a legend with the given labels. If no labels are defined, nothing is shown.",
    _section_order=5,
)
@corex.dropdown(
    "legend_alignment",
    default=8,
    options=LEGEND_LABELS,
    codes=LEGEND_CODES,
    label="Legend alignment",
    section="General options",
    port=True,
    _port_description="Define the alignment where the legend should be displayed. Possible values are 0 = Upper left, 1 = Upper center, 2 = Upper right, 3 = Middle left, 4 = Middle center, 5 = Middle right, 6 = Lower left, 7 = Lower center, 8 = Lower right.",
    _section_order=6,
)
@corex.input(
    "values",
    value_type=float,
    _accepted_data_types=(
        "COREX.DataTypes.Int", "COREX.DataTypes.GraphArray",
        "COREX.DataTypes.ArrayValue", "COREX.DataTypes.TableValue", "COREX.DataTypes.SeriesValue",
        "COREX.Runtime.TabularDataRef", "COREX.Runtime.TabularWindowRef",
        "COREX.Runtime.ArrayDataRef", "COREX.Runtime.ArraySlice2DRef",
    ),
    structure="tree",
    required=True,
    label="Values",
    description="Numeric tree branches, vectors, matrices, scientific tables or tabular/array references.",
)
@corex.interval(
    "x_axis_interval",
    default=None,
    label="X axis interval",
    section="Signal plot options",
    port=True,
    _port_description="Define a custom interval for the displayed X-axis value range.",
    _section_order=0,
    _persistence_type=None,
)
@corex.interval(
    "y_axis_interval",
    default=None,
    label="Y axis interval",
    section="Signal plot options",
    port=True,
    _port_description="Define a custom interval for the displayed Y-axis value range.",
    _section_order=1,
    _persistence_type=None,
)
@corex.list(
    "colors",
    default=[],
    item_type=corex.Color,
    label="Colors",
    section="Signal plot options",
    port=True,
    _port_description="Input one color per plotted trace for your input data. If the number of colors is less than the number of plotted traces, then the color values are repeated.",
    _section_order=3,
)
@corex.list(
    "line_styles",
    default=[1],
    item_type=int,
    options=LINE_STYLE_LABELS,
    codes=LINE_STYLE_CODES,
    label="Line styles",
    section="Signal plot options",
    port=True,
    _port_description="Choose the line style for the plot. 0 = None, 1 = Solid, 2 = Dash, 3 = Dash Dot, 4 = Dash Dot Dot, 5 = Dot. Please provide one style for all plotted traces or one style for each branch. If the number of styles is less than the number of traces, then the styles are repeated.",
    _section_order=4,
)
@corex.list(
    "line_widths",
    default=[1],
    item_type=int,
    minimum=0,
    maximum=5,
    step=1,
    label="Line widths",
    section="Signal plot options",
    port=True,
    _port_description="Specify the line width connecting the data points. Please provide one width for all plotted traces or one width for each branch. If the number of widths is less than the number of traces, then the widths are repeated.",
    _section_order=5,
)
@corex.list(
    "marker_shapes",
    default=[1],
    item_type=int,
    options=MARKER_LABELS,
    codes=MARKER_CODES,
    label="Marker shapes",
    section="Signal plot options",
    port=True,
    _port_description="Choose the marker shape for the plot. 0 = None, 1 = Filled circle, 2 = Filled square, 3 = Open circle, 4 = Open square, 5 = Filled diamond, 6 = Open diamond, 7 = Asterisk, 8 = Hashtag, 9 = Cross, 10 = X, 11 = Vertical bar, 12 = Tri upwards, 13 = Tri downwards, 14 = Filled triangle upwards, 15 = Filled triangle downwards, 16 = Open triangle upwards, 17 = Open triangle downwards. Please provide one shape for all plotted traces or one shape for each branch. If the number of shapes is less than the number of traces, then the shapes are repeated.",
    _section_order=6,
)
@corex.list(
    "marker_sizes",
    default=[10],
    item_type=int,
    minimum=1,
    maximum=72,
    step=1,
    label="Marker sizes",
    section="Signal plot options",
    port=True,
    _port_description="Specify the size of the markers which point to your given values. Please provide one size for all plotted traces or one size for each branch. If the number of sizes is less than the number of traces, then the sizes are repeated.",
    _section_order=7,
)
@corex.text(
    "x_axis_label",
    default="",
    label="X axis label",
    section="Signal plot options",
    port=True,
    _port_description="Label of the horizontal x-axis.",
    _section_order=8,
)
@corex.text(
    "y_axis_label",
    default="",
    label="Y axis label",
    section="Signal plot options",
    port=True,
    _port_description="Label of the vertical y-axis.",
    _section_order=9,
)
@corex.switch(
    "logarithmic_y_axis",
    default=False,
    label="Logarithmic Y axis",
    section="Signal plot options",
    port=True,
    _port_description="If set to true, the Y axis will use a logarithmic scale with a base of 10.",
    _section_order=2,
)
@corex.color(
    "image_background_color",
    default="#ffffff",
    label="Image background color",
    section="General options",
    port=True,
    _port_description="Specify the background color that is used by the whole image. By default, it's set to white.",
    _section_order=7,
)
@corex.color(
    "data_background_color",
    default="#ffffff",
    label="Data background color",
    section="General options",
    port=True,
    _port_description="Specify the background color that is used by the rectangle that contains the data. By default, it's set to white.",
    _section_order=8,
)
@corex.dropdown(
    "x_mode", default="auto", options=("auto", "index", "column"),
    label="X mode", section="Data", port=True, _section_order=0,
    _port_description="Automatic uses the first numeric/datetime column when multiple usable columns exist. Sample index ignores X columns.",
)
@corex.text(
    "x_column", default="", label="X column", section="Data", port=True, _section_order=1,
    _property_type="json", _inline_editor="enum",
    _port_accepted_data_types=("COREX.DataTypes.Int",),
    _port_description="Exact column name or zero-based position, used in Column X mode. Position choices display one-based labels.",
)
@corex.text(
    "y_columns", default="", label="Y columns", section="Data", port=True, _section_order=2,
    _property_type="json", _property_default=[],
    _port_value_type="COREX.DataTypes.GraphArray",
    _port_description="Ordered exact column names or zero-based positions. Leave empty to select numeric Y columns automatically.",
)
@corex.number(
    "max_points", default=4000, minimum=0, label="Maximum rendered points", section="Data", port=True, _section_order=3,
    _port_description="Maximum points per rendered trace, preserving extrema and gaps. Zero renders full resolution; source data is unchanged.",
)
@corex.text(
    "x_datetime_start", default="", label="Datetime X start", section="Data", port=True, _section_order=4,
    _port_description="Optional ISO-8601 date or timestamp for the displayed X minimum. Naive timestamps use UTC.",
)
@corex.text(
    "x_datetime_end", default="", label="Datetime X end", section="Data", port=True, _section_order=5,
    _port_description="Optional ISO-8601 date or timestamp for the displayed X maximum. Naive timestamps use UTC.",
)
@corex.output(
    "image",
    value_type=corex.Image,
    label="Image",
    description="Image data from your plot.",
)
def signal_plot(ctx, values, settings):
    render_inputs = settings.to_dict()
    render_inputs["values"] = values
    image, warnings = render_signal_plot(render_inputs)
    for warning in warnings:
        ctx.warn(warning, code="signal_plot_render")
    return {"image": image}
'''

__all__ = ["SOURCE"]

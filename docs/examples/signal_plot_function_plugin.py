"""Public Signal Plot-style function-plugin example.

The node creates a backend-neutral plot request so the example stays usable
without a plotting dependency. Connect that request to a renderer available in
your workflow.
"""

import corex


LEGEND_POSITIONS = ("Upper left", "Upper right", "Lower right")


@corex.node(
    id="custom.signal_plot_style.7b9c2d4e",
    name="Signal Plot Style",
    category=("Custom", "Plot"),
    description="Build a styled request for an evenly spaced signal plot.",
    keywords=("signal", "plot", "chart"),
)
@corex.input(
    "values",
    value_type=float,
    structure="tree",
    required=True,
    label="Values",
    description="Signal samples grouped by data-tree branch.",
    section="Data",
)
@corex.text(
    "title",
    default="Signal",
    label="Title",
    section="Style",
    port=True,
)
@corex.slider(
    "line_width",
    default=2.0,
    minimum=0.5,
    maximum=8.0,
    step=0.5,
    label="Line width",
    section="Style",
    port=True,
)
@corex.color(
    "line_color",
    default="#4f8cff",
    label="Line color",
    section="Style",
)
@corex.switch(
    "show_legend",
    default=False,
    label="Show legend",
    section="Style",
    port=True,
)
@corex.dropdown(
    "legend_position",
    default="Upper right",
    options=LEGEND_POSITIONS,
    label="Legend position",
    section="Style",
)
@corex.interval(
    "y_range",
    default=None,
    label="Y range",
    section="Axes",
    port=True,
)
@corex.output(
    "plot_request",
    value_type=corex.Any,
    label="Plot request",
    description="Values and settings for a downstream plot renderer.",
)
def signal_plot_style(ctx, values, settings):
    if not values:
        ctx.warn("Signal Plot received no samples.", code="empty_signal")
    request = settings.to_dict()
    request["values"] = values
    return {"plot_request": request}

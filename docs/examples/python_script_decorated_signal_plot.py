@corex.node
@corex.input(
    "series",
    value_type=corex.Any,
    structure="tree",
    required=True,
    section="Data",
)
@corex.input("title_suffix", value_type=str, section="Data")
@corex.output("plot_summary", value_type=str)
@corex.text("title", default="Signal plot", section="Style", port=True)
@corex.switch("show_legend", default=True, section="Legend", port=True)
@corex.dropdown(
    "legend_position",
    default=1,
    options=("Upper left", "Upper right", "Lower right"),
    codes=(0, 1, 2),
    section="Legend",
    port=True,
)
@corex.slider(
    "line_width",
    default=2.0,
    minimum=0.5,
    maximum=8.0,
    step=0.5,
    section="Style",
    port=True,
)
@corex.color("line_color", default="#4f8cff", section="Style")
@corex.interval(
    "x_range",
    default=(0.0, 10.0),
    minimum=0.0,
    maximum=10.0,
    step=0.1,
    direction="increasing",
    section="Axes",
)
@corex.list(
    "series_labels",
    default=["Signal"],
    item_type=str,
    section="Data",
    port=True,
)
def run(
    ctx,
    series,
    title_suffix,
    title,
    show_legend,
    legend_position,
    line_width,
    line_color,
    x_range,
    series_labels,
):
    del series, show_legend, line_width, line_color, x_range
    ctx.log_info("Preparing signal plot settings")
    return {
        "plot_summary": (
            f"{title}{title_suffix}: {len(series_labels)} series, "
            f"legend position code {legend_position}"
        )
    }

from __future__ import annotations

VIEWER_OVERLAY_FONT_FAMILY = "arial"

# Live viewer canvas styles for both shell themes. The dark palette sits near
# the shell's canvas_bg (#1d1f24) and the light palette near #f3f5f8, so the
# embedded native viewport reads as part of the shell instead of a raw VTK
# window. Report exports (PNG materialization) keep pyvista's default light
# background, so themed styling is opt-in via `themed=True`.
_DARK_CANVAS_STYLE: dict[str, str | bool] = {
    "dark": True,
    "background_bottom": "#151A20",
    "background_top": "#232A33",
    "annotation_color": "#F4F6F8",
    "scalar_bar_color": "#E8ECF1",
    "marker_text_color": "#F4F6F8",
    "marker_chip_color": "#1F2933",
}
_LIGHT_CANVAS_STYLE: dict[str, str | bool] = {
    "dark": False,
    "background_bottom": "#E9EEF4",
    "background_top": "#FBFCFE",
    "annotation_color": "#26303B",
    "scalar_bar_color": "#2A3441",
    "marker_text_color": "#1B2733",
    "marker_chip_color": "#E3EAF1",
}

# Fixed per-node background overrides (the "viewer_background" view option).
# Each carries the full annotation palette so text/markers stay readable.
_BACKGROUND_OVERRIDE_STYLES: dict[str, dict[str, str | bool]] = {
    "white": {
        "dark": False,
        "background_bottom": "#FFFFFF",
        "background_top": "#FFFFFF",
        "annotation_color": "#26303B",
        "scalar_bar_color": "#2A3441",
        "marker_text_color": "#1B2733",
        "marker_chip_color": "#E3EAF1",
    },
    "black": {
        "dark": True,
        "background_bottom": "#000000",
        "background_top": "#000000",
        "annotation_color": "#F4F6F8",
        "scalar_bar_color": "#E8ECF1",
        "marker_text_color": "#F4F6F8",
        "marker_chip_color": "#1F2933",
    },
    "gray": {
        "dark": False,
        "background_bottom": "#AEB8C2",
        "background_top": "#CBD3DB",
        "annotation_color": "#1B2733",
        "scalar_bar_color": "#1B2733",
        "marker_text_color": "#1B2733",
        "marker_chip_color": "#E3EAF1",
    },
}

_canvas_dark = True


def set_viewer_canvas_dark(dark: bool) -> None:
    """Select the live viewer canvas style; called from the shell theme funnel."""
    global _canvas_dark
    _canvas_dark = bool(dark)


def viewer_canvas_style(background: object = "") -> dict[str, str | bool]:
    """Active canvas style; a non-"theme" background override wins over the theme."""
    override = _BACKGROUND_OVERRIDE_STYLES.get(str(background or "").strip().lower())
    if override is not None:
        return dict(override)
    return dict(_DARK_CANVAS_STYLE if _canvas_dark else _LIGHT_CANVAS_STYLE)


def _coerce_dimension(value: object, *, fallback: int) -> int:
    try:
        numeric = int(value)
    except (TypeError, ValueError):
        return fallback
    return numeric if numeric > 0 else fallback


def scalar_bar_args_for_viewport(
    viewport_width: object,
    viewport_height: object,
    *,
    themed: bool = False,
    themed_background: object = "",
) -> dict[str, int | float | bool | str]:
    width = _coerce_dimension(viewport_width, fallback=320)
    height = _coerce_dimension(viewport_height, fallback=240)
    shortest_side = min(width, height)

    # Slim bar: width fractions are of the viewport width, so keep them small
    # enough that a wide fullscreen viewport does not grow a huge legend.
    if shortest_side < 180:
        title_font_size = 9
        label_font_size = 8
        bar_height = 0.40
        bar_width = 0.035
        position_x = 0.90
        position_y = 0.12
    elif shortest_side < 260:
        title_font_size = 10
        label_font_size = 8
        bar_height = 0.46
        bar_width = 0.04
        position_x = 0.90
        position_y = 0.10
    else:
        title_font_size = 11
        label_font_size = 9
        bar_height = 0.52
        bar_width = 0.045
        position_x = 0.90
        position_y = 0.08

    args: dict[str, int | float | bool | str] = {
        "vertical": True,
        "title_font_size": title_font_size,
        "label_font_size": label_font_size,
        "height": bar_height,
        "width": bar_width,
        "position_x": position_x,
        "position_y": position_y,
    }
    if themed:
        style = viewer_canvas_style(themed_background)
        args["color"] = str(style["scalar_bar_color"])
        args["font_family"] = VIEWER_OVERLAY_FONT_FAMILY
    return args


__all__ = [
    "VIEWER_OVERLAY_FONT_FAMILY",
    "scalar_bar_args_for_viewport",
    "set_viewer_canvas_dark",
    "viewer_canvas_style",
]

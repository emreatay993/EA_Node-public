"""Design tokens, palette and stylesheet for the SKF Engineering Bearing Suite GUI.

Why this module exists
----------------------
Qt style sheets do not reset the widget palette; they only override the
properties they explicitly name. On Windows 10/11 with "Apps use dark theme"
enabled, Qt hands the application a dark palette (white ``Text``/``WindowText``,
near-black ``Window``). A style sheet that paints backgrounds but not
foregrounds therefore renders white text on white cards and leaves unstyled
containers filled with the dark window brush.

This module removes that whole class of failure by doing three things:

* pinning the application to an explicit light colour scheme and palette, so the
  OS theme cannot leak in,
* pairing every ``background`` rule with an explicit ``color`` rule, so the
  style sheet is self-sufficient even if the palette is bypassed,
* keeping every colour in one token table instead of scattered literals.
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path

from PyQt6.QtCore import QStandardPaths, Qt
from PyQt6.QtGui import QColor, QFont, QGuiApplication, QImage, QPainter, QPainterPath, QPalette, QPen


# --------------------------------------------------------------------------- tokens


@dataclass(frozen=True)
class Tokens:
    """Named colours for the whole application.

    Slate neutrals plus a single blue accent. Keeping these in one place is what
    stops the "four almost-identical greys" drift that the first style sheet had.
    """

    # Neutrals / surfaces
    canvas: str = "#F1F5F9"
    surface: str = "#FFFFFF"
    surface_alt: str = "#F8FAFC"
    surface_sunken: str = "#EDF2F7"
    border: str = "#E2E8F0"
    border_strong: str = "#CBD5E1"
    border_hover: str = "#94A3B8"

    # Text
    ink: str = "#0F172A"
    text: str = "#1E293B"
    text_muted: str = "#475569"
    text_subtle: str = "#94A3B8"
    text_disabled: str = "#A8B4C4"

    # Accent
    accent: str = "#2563EB"
    accent_hover: str = "#1D4ED8"
    accent_pressed: str = "#1E40AF"
    accent_soft: str = "#EFF6FF"
    accent_border: str = "#BFDBFE"
    accent_text: str = "#1D4ED8"

    # Navigation rail
    rail: str = "#0F172A"
    rail_alt: str = "#1E293B"
    rail_text: str = "#94A3B8"
    rail_subtle: str = "#64748B"

    # Semantic
    ok: str = "#047857"
    ok_soft: str = "#ECFDF5"
    ok_border: str = "#A7F3D0"
    warn: str = "#B45309"
    warn_soft: str = "#FFFBEB"
    warn_border: str = "#FDE68A"
    danger: str = "#DC2626"
    danger_soft: str = "#FEF2F2"

    # Type stacks. Qt picks the first family that exists, so Windows 11 gets the
    # variable Segoe faces and older systems fall back cleanly.
    font_ui: str = '"Segoe UI Variable Text", "Segoe UI", "Noto Sans", sans-serif'
    font_display: str = '"Segoe UI Variable Display", "Segoe UI", "Noto Sans", sans-serif'
    font_mono: str = '"Cascadia Mono", "Consolas", "Courier New", monospace'


T = Tokens()

#: Radii and metrics reused across the style sheet.
RADIUS_CARD = 12
RADIUS_CONTROL = 8
RADIUS_PILL = 8
CONTROL_HEIGHT = 22  # content height; padding brings the widget to ~36 px


# --------------------------------------------------------------------------- icons


def _icon_dir() -> Path:
    """Return a writable directory for the generated indicator images."""
    base = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.CacheLocation)
    candidates = [Path(base) / "ui-icons-v1"] if base else []
    candidates.append(Path(tempfile.gettempdir()) / "skfcalc-ui-icons-v1")
    for candidate in candidates:
        try:
            candidate.mkdir(parents=True, exist_ok=True)
            probe = candidate / ".writable"
            probe.write_bytes(b"")
            probe.unlink()
        except OSError:
            continue
        return candidate
    raise OSError("no writable directory for generated UI icons")


def _draw_chevron(size: int, scale: int, color: str, direction: str) -> QImage:
    """Draw a stroked chevron. Qt discards native arrows once a sub-control is
    styled, so the style sheet supplies its own crisp ones."""
    px = size * scale
    image = QImage(px, px, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    pen = QPen(QColor(color))
    pen.setWidthF(1.6 * scale)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)

    inset = 2.2 * scale
    mid = px / 2.0
    span = (px - 2 * inset) / 2.0
    path = QPainterPath()
    if direction == "down":
        path.moveTo(mid - span, mid - span * 0.55)
        path.lineTo(mid, mid + span * 0.55)
        path.lineTo(mid + span, mid - span * 0.55)
    else:
        path.moveTo(mid - span, mid + span * 0.55)
        path.lineTo(mid, mid - span * 0.55)
        path.lineTo(mid + span, mid + span * 0.55)
    painter.drawPath(path)
    painter.end()
    return image


def _draw_check(size: int, scale: int, color: str) -> QImage:
    px = size * scale
    image = QImage(px, px, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    pen = QPen(QColor(color))
    pen.setWidthF(1.9 * scale)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    path = QPainterPath()
    path.moveTo(px * 0.22, px * 0.52)
    path.lineTo(px * 0.42, px * 0.72)
    path.lineTo(px * 0.79, px * 0.28)
    painter.drawPath(path)
    painter.end()
    return image


def _draw_dash(size: int, scale: int, color: str) -> QImage:
    px = size * scale
    image = QImage(px, px, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    pen = QPen(QColor(color))
    pen.setWidthF(1.9 * scale)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    painter.setPen(pen)
    painter.drawLine(int(px * 0.24), int(px * 0.5), int(px * 0.76), int(px * 0.5))
    painter.end()
    return image


def generate_icons() -> dict[str, str]:
    """Render the indicator images and return QSS-safe ``url()`` paths.

    Each glyph is written at 1x and 2x; Qt loads the ``@2x`` sibling
    automatically on high-DPI screens, so the chevrons stay sharp.
    """
    directory = _icon_dir()
    specs: dict[str, tuple[str, int, str]] = {
        "chevron_down": ("chevron", 12, T.text_muted),
        "chevron_down_muted": ("chevron", 10, T.text_subtle),
        "chevron_up_muted": ("chevron_up", 10, T.text_subtle),
        "chevron_down_accent": ("chevron", 12, T.accent),
        "chevron_up_accent": ("chevron_up", 10, T.accent),
        "chevron_down_disabled": ("chevron", 10, T.text_disabled),
        "chevron_up_disabled": ("chevron_up", 10, T.text_disabled),
        "check_white": ("check", 14, "#FFFFFF"),
        "check_disabled": ("check", 14, T.text_disabled),
        "dash_white": ("dash", 14, "#FFFFFF"),
    }
    paths: dict[str, str] = {}
    for name, (kind, size, color) in specs.items():
        for scale, suffix in ((1, ""), (2, "@2x")):
            if kind == "chevron":
                image = _draw_chevron(size, scale, color, "down")
            elif kind == "chevron_up":
                image = _draw_chevron(size, scale, color, "up")
            elif kind == "check":
                image = _draw_check(size, scale, color)
            else:
                image = _draw_dash(size, scale, color)
            target = directory / f"{name}{suffix}.png"
            image.save(str(target), "PNG")
            if not suffix:
                # Qt style sheets need forward slashes even on Windows.
                paths[name] = target.as_posix()
    return paths


# --------------------------------------------------------------------------- palette


def light_palette() -> QPalette:
    """An explicit light palette.

    This is the first half of the dark-mode fix: every widget that the style
    sheet does not name still resolves readable colours from here, including
    native-ish surfaces such as ``QMessageBox`` and tooltips.
    """
    p = QPalette()
    role = QPalette.ColorRole
    group = QPalette.ColorGroup

    p.setColor(role.Window, QColor(T.canvas))
    p.setColor(role.WindowText, QColor(T.text))
    p.setColor(role.Base, QColor(T.surface))
    p.setColor(role.AlternateBase, QColor(T.surface_alt))
    p.setColor(role.Text, QColor(T.text))
    p.setColor(role.Button, QColor(T.surface))
    p.setColor(role.ButtonText, QColor(T.text))
    p.setColor(role.BrightText, QColor(T.danger))
    p.setColor(role.ToolTipBase, QColor(T.ink))
    p.setColor(role.ToolTipText, QColor("#FFFFFF"))
    p.setColor(role.PlaceholderText, QColor(T.text_subtle))
    p.setColor(role.Highlight, QColor(T.accent))
    p.setColor(role.HighlightedText, QColor("#FFFFFF"))
    p.setColor(role.Link, QColor(T.accent))
    p.setColor(role.LinkVisited, QColor(T.accent_pressed))
    p.setColor(role.Light, QColor(T.surface))
    p.setColor(role.Midlight, QColor(T.surface_alt))
    p.setColor(role.Mid, QColor(T.border))
    p.setColor(role.Dark, QColor(T.border_strong))
    p.setColor(role.Shadow, QColor(T.border_strong))

    for disabled_role, value in (
        (role.WindowText, T.text_disabled),
        (role.Text, T.text_disabled),
        (role.ButtonText, T.text_disabled),
        (role.Base, T.surface_alt),
        (role.Button, T.surface_alt),
        (role.Highlight, T.border),
        (role.HighlightedText, T.text_disabled),
    ):
        p.setColor(group.Disabled, disabled_role, QColor(value))
    return p


# --------------------------------------------------------------------------- stylesheet


def build_stylesheet(icons: dict[str, str] | None = None) -> str:
    """Return the full application style sheet.

    Every rule that sets a ``background`` also sets a ``color``. That is the
    second half of the dark-mode fix and the reason this sheet stays correct even
    if the palette above is never installed.
    """
    icons = icons or {}

    def url(name: str) -> str:
        path = icons.get(name)
        return f"url({path})" if path else "none"

    return f"""
/* ------------------------------------------------------------------ base */
QWidget {{
    font-family: {T.font_ui};
    font-size: 10pt;
    color: {T.text};
}}
QMainWindow, QDialog {{
    background: {T.canvas};
    color: {T.text};
}}
QWidget#pageStack, QWidget#pageRoot, QWidget#scrollContent {{
    background: {T.canvas};
    color: {T.text};
}}
QLabel {{
    background: transparent;
    color: {T.text};
}}
QLabel:disabled {{ color: {T.text_disabled}; }}
/* Tooltips carry multi-line field help with formulas and a source line, so
   they are styled as a light card rather than a dark one-liner. */
QToolTip {{
    background: {T.surface};
    color: {T.text};
    border: 1px solid {T.border_strong};
    border-radius: 8px;
    padding: 9px 11px;
}}

/* --------------------------------------------------------------- menu bar */
QMenuBar {{
    background: {T.surface};
    color: {T.text};
    border-bottom: 1px solid {T.border};
    padding: 2px 6px;
}}
QMenuBar::item {{
    background: transparent;
    color: {T.text_muted};
    padding: 6px 11px;
    border-radius: 6px;
}}
QMenuBar::item:selected {{ background: {T.surface_sunken}; color: {T.ink}; }}
QMenu {{
    background: {T.surface};
    color: {T.text};
    border: 1px solid {T.border};
    border-radius: 10px;
    padding: 6px;
}}
QMenu::item {{
    background: transparent;
    color: {T.text};
    padding: 7px 26px 7px 14px;
    border-radius: 6px;
}}
QMenu::item:selected {{ background: {T.accent_soft}; color: {T.accent_text}; }}
QMenu::item:disabled {{ color: {T.text_disabled}; }}
QMenu::separator {{ height: 1px; background: {T.border}; margin: 5px 8px; }}

/* ---------------------------------------------------------------- toolbar */
QToolBar#mainToolbar {{
    background: {T.surface};
    color: {T.text};
    border: none;
    border-bottom: 1px solid {T.border};
    spacing: 4px;
    padding: 9px 16px;
}}
QToolBar#mainToolbar::separator {{
    background: {T.border};
    width: 1px;
    margin: 4px 9px;
}}
QToolButton {{
    background: transparent;
    color: {T.text_muted};
    border: 1px solid transparent;
    border-radius: {RADIUS_CONTROL}px;
    padding: 7px 13px;
    font-weight: 600;
}}
QToolButton:hover {{ background: {T.surface_sunken}; color: {T.ink}; }}
QToolButton:pressed {{ background: {T.border}; color: {T.ink}; }}
QToolButton:disabled {{ background: transparent; color: {T.text_disabled}; }}
QToolButton#runButton {{
    background: {T.accent};
    color: #FFFFFF;
    border: 1px solid {T.accent};
    padding: 7px 18px;
    font-weight: 700;
}}
QToolButton#runButton:hover {{ background: {T.accent_hover}; border-color: {T.accent_hover}; }}
QToolButton#runButton:pressed {{ background: {T.accent_pressed}; border-color: {T.accent_pressed}; }}
QToolButton#runButton:disabled {{
    background: {T.border};
    color: {T.text_disabled};
    border-color: {T.border};
}}
QLabel#toolbarBadge {{
    background: {T.accent_soft};
    color: {T.accent_text};
    border: 1px solid {T.accent_border};
    border-radius: 11px;
    padding: 4px 12px;
    font-size: 8.5pt;
    font-weight: 600;
}}

/* ------------------------------------------------------------ navigation */
QFrame#sidebar {{
    background: {T.rail};
    color: {T.rail_text};
    border: none;
}}
QLabel#brand {{
    background: transparent;
    color: #FFFFFF;
    font-family: {T.font_display};
    font-size: 15pt;
    font-weight: 700;
    letter-spacing: 1.2px;
}}
QLabel#subbrand {{
    background: transparent;
    color: {T.rail_subtle};
    font-size: 8.5pt;
    font-weight: 600;
    letter-spacing: 1.1px;
}}
QLabel#railSectionLabel {{
    background: transparent;
    color: {T.rail_subtle};
    font-size: 8pt;
    font-weight: 700;
    letter-spacing: 1.3px;
}}
QLabel#versionLabel {{
    background: transparent;
    color: {T.rail_subtle};
    font-size: 8.5pt;
}}
QFrame#railDivider {{ background: {T.rail_alt}; border: none; max-height: 1px; }}
QListWidget#navigation {{
    background: transparent;
    color: {T.rail_text};
    border: none;
    outline: none;
}}
QListWidget#navigation::item {{
    background: transparent;
    color: {T.rail_text};
    padding: 0px 12px;
    border-radius: {RADIUS_PILL}px;
}}
QListWidget#navigation::item:disabled {{
    background: transparent;
    color: {T.rail_subtle};
    font-size: 8pt;
    font-weight: 700;
    letter-spacing: 1.4px;
    padding-top: 10px;
}}
QListWidget#navigation::item:hover {{ background: {T.rail_alt}; color: #FFFFFF; }}
QListWidget#navigation::item:selected {{
    background: {T.accent};
    color: #FFFFFF;
    font-weight: 700;
}}

/* -------------------------------------------------------------- page head */
QLabel#pageTitle {{
    background: transparent;
    color: {T.ink};
    font-family: {T.font_display};
    font-size: 19pt;
    font-weight: 700;
}}
QLabel#pageSubtitle {{
    background: transparent;
    color: {T.text_muted};
    font-size: 10pt;
}}

/* ------------------------------------------------------------------ cards */
QGroupBox#engineeringGroup {{
    background: {T.surface};
    color: {T.text};
    border: 1px solid {T.border};
    border-radius: {RADIUS_CARD}px;
    margin-top: 0px;
    padding: 42px 0px 0px 0px;
    font-weight: 600;
}}
QGroupBox#engineeringGroup::title {{
    subcontrol-origin: border;
    subcontrol-position: top left;
    left: 0px;
    top: 0px;
    padding: 15px 20px 6px 21px;
    background: transparent;
    color: {T.text_muted};
    font-size: 8.5pt;
    font-weight: 700;
    letter-spacing: 1.1px;
}}
QFrame#cardPanel {{
    background: {T.surface};
    color: {T.text};
    border: 1px solid {T.border};
    border-radius: {RADIUS_CARD}px;
}}

/* --------------------------------------------------------------- editors */
QLineEdit, QComboBox, QDoubleSpinBox, QSpinBox, QTextEdit, QPlainTextEdit {{
    background: {T.surface};
    color: {T.text};
    border: 1px solid {T.border_strong};
    border-radius: {RADIUS_CONTROL}px;
    padding: 6px 11px;
    min-height: {CONTROL_HEIGHT}px;
    selection-background-color: {T.accent};
    selection-color: #FFFFFF;
}}
QLineEdit:hover, QComboBox:hover, QDoubleSpinBox:hover, QSpinBox:hover, QTextEdit:hover {{
    border-color: {T.border_hover};
}}
/* 2 px focus ring with 1 px less padding so the row height never jumps. */
QLineEdit:focus, QComboBox:focus, QDoubleSpinBox:focus, QSpinBox:focus, QTextEdit:focus {{
    border: 2px solid {T.accent};
    padding: 5px 10px;
}}
QLineEdit:disabled, QComboBox:disabled, QDoubleSpinBox:disabled,
QSpinBox:disabled, QTextEdit:disabled {{
    background: {T.surface_alt};
    color: {T.text_disabled};
    border-color: {T.border};
}}
QLineEdit[readOnly="true"] {{ background: {T.surface_alt}; color: {T.text_muted}; }}

QComboBox::drop-down {{
    subcontrol-origin: padding;
    subcontrol-position: center right;
    width: 26px;
    border: none;
    background: transparent;
}}
QComboBox::down-arrow {{ image: {url('chevron_down')}; width: 12px; height: 12px; }}
QComboBox::down-arrow:disabled {{ image: {url('chevron_down_disabled')}; }}
QComboBox QAbstractItemView {{
    background: {T.surface};
    color: {T.text};
    border: 1px solid {T.border};
    border-radius: 10px;
    padding: 5px;
    outline: none;
    selection-background-color: {T.accent_soft};
    selection-color: {T.accent_text};
}}
QComboBox QAbstractItemView::item {{
    padding: 7px 10px;
    border-radius: 6px;
    min-height: 22px;
}}

QDoubleSpinBox::up-button, QSpinBox::up-button {{
    subcontrol-origin: border;
    subcontrol-position: top right;
    width: 22px;
    margin: 3px 3px 0px 0px;
    border: none;
    border-top-right-radius: 6px;
    background: transparent;
}}
QDoubleSpinBox::down-button, QSpinBox::down-button {{
    subcontrol-origin: border;
    subcontrol-position: bottom right;
    width: 22px;
    margin: 0px 3px 3px 0px;
    border: none;
    border-bottom-right-radius: 6px;
    background: transparent;
}}
QDoubleSpinBox::up-button:hover, QSpinBox::up-button:hover,
QDoubleSpinBox::down-button:hover, QSpinBox::down-button:hover {{
    background: {T.accent_soft};
}}
QDoubleSpinBox::up-arrow, QSpinBox::up-arrow {{
    image: {url('chevron_up_muted')}; width: 10px; height: 10px;
}}
QDoubleSpinBox::down-arrow, QSpinBox::down-arrow {{
    image: {url('chevron_down_muted')}; width: 10px; height: 10px;
}}
QDoubleSpinBox::up-arrow:hover, QSpinBox::up-arrow:hover {{ image: {url('chevron_up_accent')}; }}
QDoubleSpinBox::down-arrow:hover, QSpinBox::down-arrow:hover {{ image: {url('chevron_down_accent')}; }}
QDoubleSpinBox::up-arrow:disabled, QSpinBox::up-arrow:disabled,
QDoubleSpinBox::up-arrow:off, QSpinBox::up-arrow:off {{ image: {url('chevron_up_disabled')}; }}
QDoubleSpinBox::down-arrow:disabled, QSpinBox::down-arrow:disabled,
QDoubleSpinBox::down-arrow:off, QSpinBox::down-arrow:off {{ image: {url('chevron_down_disabled')}; }}

/* ------------------------------------------------------------- checkboxes */
QCheckBox {{ background: transparent; color: {T.text}; spacing: 9px; padding: 3px 0px; }}
QCheckBox:disabled {{ color: {T.text_disabled}; }}
QCheckBox::indicator {{
    width: 18px;
    height: 18px;
    border: 1px solid {T.border_strong};
    border-radius: 5px;
    background: {T.surface};
}}
QCheckBox::indicator:hover {{ border-color: {T.accent}; }}
QCheckBox::indicator:checked {{
    background: {T.accent};
    border-color: {T.accent};
    image: {url('check_white')};
}}
QCheckBox::indicator:indeterminate {{
    background: {T.accent};
    border-color: {T.accent};
    image: {url('dash_white')};
}}
QCheckBox::indicator:disabled {{ background: {T.surface_alt}; border-color: {T.border}; }}
QCheckBox::indicator:checked:disabled {{
    background: {T.border};
    border-color: {T.border};
    image: {url('check_disabled')};
}}
QCheckBox#primaryCheck {{
    background: {T.accent_soft};
    color: {T.ink};
    border: 1px solid {T.accent_border};
    border-radius: 10px;
    padding: 12px 16px;
    font-weight: 600;
}}

/* ---------------------------------------------------------------- buttons */
QPushButton {{
    background: {T.surface};
    color: {T.text};
    border: 1px solid {T.border_strong};
    border-radius: {RADIUS_CONTROL}px;
    padding: 8px 16px;
    min-height: {CONTROL_HEIGHT}px;
    font-weight: 600;
}}
QPushButton:hover {{ background: {T.surface_alt}; border-color: {T.border_hover}; color: {T.ink}; }}
QPushButton:pressed {{ background: {T.surface_sunken}; border-color: {T.border_hover}; }}
QPushButton:disabled {{
    background: {T.surface_alt};
    color: {T.text_disabled};
    border-color: {T.border};
}}
QPushButton:default {{ border-color: {T.accent_border}; }}
QPushButton#primaryButton {{
    background: {T.accent};
    color: #FFFFFF;
    border-color: {T.accent};
    font-weight: 700;
}}
QPushButton#primaryButton:hover {{ background: {T.accent_hover}; border-color: {T.accent_hover}; }}
QPushButton#primaryButton:pressed {{ background: {T.accent_pressed}; border-color: {T.accent_pressed}; }}
QPushButton#primaryButton:disabled {{
    background: {T.border};
    color: {T.text_disabled};
    border-color: {T.border};
}}
QPushButton#ghostButton {{
    background: transparent;
    color: {T.accent_text};
    border: 1px solid transparent;
    font-weight: 600;
}}
QPushButton#ghostButton:hover {{ background: {T.accent_soft}; border-color: {T.accent_border}; }}

/* ------------------------------------------------------------- callouts */
QLabel#methodNote {{
    background: {T.accent_soft};
    color: {T.text_muted};
    border: 1px solid {T.accent_border};
    border-left: 3px solid {T.accent};
    border-radius: 9px;
    padding: 13px 15px;
}}
QLabel#warningNote {{
    background: {T.warn_soft};
    color: {T.warn};
    border: 1px solid {T.warn_border};
    border-left: 3px solid #D97706;
    border-radius: 9px;
    padding: 13px 15px;
}}

/* ---------------------------------------------------------- metric cards */
QFrame#metricCard {{
    background: {T.surface};
    color: {T.text};
    border: 1px solid {T.border};
    border-radius: {RADIUS_CARD}px;
}}
QLabel#metricTitle {{
    background: transparent;
    color: {T.text_muted};
    font-size: 8.5pt;
    font-weight: 700;
    letter-spacing: 0.9px;
}}
QLabel#metricValue {{
    background: transparent;
    color: {T.ink};
    font-family: {T.font_display};
    font-size: 21pt;
    font-weight: 700;
}}
QLabel#metricValue[empty="true"] {{
    color: {T.text_subtle};
    font-weight: 400;
}}
QLabel#metricUnit {{
    background: transparent;
    color: {T.text_subtle};
    font-size: 9.5pt;
    font-weight: 600;
}}

/* -------------------------------------------------------------------- tabs */
QTabWidget::pane {{
    background: {T.surface};
    border: 1px solid {T.border};
    border-radius: {RADIUS_CARD}px;
    /* Inset the content so an opaque child (a matplotlib canvas) cannot paint
       square corners over the card's rounded border. */
    padding: 8px;
    top: -1px;
}}
QTabBar {{ background: transparent; qproperty-drawBase: 0; }}
QTabBar::tab {{
    background: transparent;
    color: {T.text_muted};
    border: none;
    border-bottom: 2px solid transparent;
    padding: 9px 16px;
    margin-right: 2px;
    font-weight: 600;
}}
QTabBar::tab:hover {{ color: {T.ink}; }}
QTabBar::tab:selected {{ color: {T.accent_text}; border-bottom: 2px solid {T.accent}; }}
QTabBar::tab:disabled {{ color: {T.text_disabled}; }}

/* ------------------------------------------------------------------ tables */
QTableView, QTableWidget {{
    background: {T.surface};
    alternate-background-color: {T.surface_alt};
    color: {T.text};
    border: 1px solid {T.border};
    border-radius: 10px;
    gridline-color: {T.border};
    selection-background-color: {T.accent_soft};
    selection-color: {T.ink};
    outline: none;
}}
QTableView::item, QTableWidget::item {{ padding: 6px 9px; border: none; }}
QTableView::item:selected, QTableWidget::item:selected {{
    background: {T.accent_soft};
    color: {T.ink};
}}
QHeaderView {{ background: transparent; }}
QHeaderView::section {{
    background: {T.surface_alt};
    color: {T.text_muted};
    border: none;
    border-right: 1px solid {T.border};
    border-bottom: 1px solid {T.border};
    padding: 9px 10px;
    font-size: 9pt;
    font-weight: 700;
}}
QHeaderView::section:last {{ border-right: none; }}
QTableCornerButton::section {{ background: {T.surface_alt}; border: none; }}

/* --------------------------------------------------------------- scrolling */
QScrollArea {{ background: transparent; border: none; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
QScrollBar:vertical {{
    background: transparent;
    width: 12px;
    margin: 2px 2px 2px 0px;
    border: none;
}}
QScrollBar::handle:vertical {{
    background: {T.border_strong};
    border-radius: 5px;
    min-height: 34px;
}}
QScrollBar::handle:vertical:hover {{ background: {T.border_hover}; }}
QScrollBar:horizontal {{
    background: transparent;
    height: 12px;
    margin: 0px 2px 2px 2px;
    border: none;
}}
QScrollBar::handle:horizontal {{
    background: {T.border_strong};
    border-radius: 5px;
    min-width: 34px;
}}
QScrollBar::handle:horizontal:hover {{ background: {T.border_hover}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0px; height: 0px; border: none; background: none; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: none; }}

/* --------------------------------------------------------------- splitters */
QSplitter::handle {{ background: transparent; }}
QSplitter::handle:vertical {{ height: 12px; }}
QSplitter::handle:horizontal {{ width: 12px; }}

/* -------------------------------------------------------------- status bar */
QStatusBar {{
    background: {T.surface};
    color: {T.text_muted};
    border-top: 1px solid {T.border};
}}
QStatusBar::item {{ border: none; }}
QLabel#statusText {{ background: transparent; color: {T.text_muted}; padding: 3px 4px; }}
QLabel#statusChip {{
    background: {T.surface_sunken};
    color: {T.text_muted};
    border: 1px solid {T.border};
    border-radius: 10px;
    padding: 3px 12px;
    font-size: 8.5pt;
    font-weight: 700;
    letter-spacing: 0.6px;
}}
QLabel#statusChip[state="running"] {{
    background: {T.accent_soft};
    color: {T.accent_text};
    border-color: {T.accent_border};
}}
QLabel#statusChip[state="ok"] {{
    background: {T.ok_soft};
    color: {T.ok};
    border-color: {T.ok_border};
}}
QLabel#statusChip[state="warn"] {{
    background: {T.warn_soft};
    color: {T.warn};
    border-color: {T.warn_border};
}}
QProgressBar {{
    background: {T.surface_sunken};
    color: {T.text};
    border: none;
    border-radius: 3px;
    max-height: 6px;
    text-align: center;
}}
QProgressBar::chunk {{ background: {T.accent}; border-radius: 3px; }}
"""


# --------------------------------------------------------------------------- entry point


def apply_app_theme(app) -> None:
    """Pin the application to the light design system.

    Order matters: the style must be set before the palette, and the
    organisation/application names must already be set so the icon cache lands
    in a per-app directory.
    """
    # Fusion renders style-sheet rules consistently across Windows versions; the
    # native Windows style ignores several of the rules used above.
    app.setStyle("Fusion")

    # Qt 6.8+ exposes an explicit colour-scheme override. Without it, Windows
    # dark mode reaches in and repaints unstyled widgets.
    hints = QGuiApplication.styleHints()
    if hasattr(hints, "setColorScheme"):
        try:
            hints.setColorScheme(Qt.ColorScheme.Light)
        except (AttributeError, TypeError):  # pragma: no cover - older Qt
            pass

    app.setPalette(light_palette())
    app.setFont(QFont("Segoe UI", 10))

    try:
        icons = generate_icons()
    except OSError:
        icons = {}  # Style sheet degrades to Qt's default indicators.
    app.setStyleSheet(build_stylesheet(icons))
    configure_matplotlib()


# --------------------------------------------------------------------------- matplotlib

#: Ordered colour cycle for plotted series.
PLOT_COLORS = ("#2563EB", "#DB2777", "#059669", "#D97706", "#7C3AED", "#0891B2")



_MATPLOTLIB_CONFIGURED = False


def configure_matplotlib() -> None:
    """Apply the design system to matplotlib's global defaults.

    Idempotent: only the first call touches rcParams.
    """
    global _MATPLOTLIB_CONFIGURED
    if _MATPLOTLIB_CONFIGURED:
        return
    import matplotlib

    matplotlib.rcParams.update(
        {
            "font.family": "sans-serif",
            "font.sans-serif": ["Segoe UI", "Noto Sans", "DejaVu Sans"],
            "font.size": 9.0,
            "axes.titlesize": 10.5,
            "axes.titleweight": "600",
            "axes.labelsize": 9.0,
            "axes.prop_cycle": matplotlib.cycler(color=list(PLOT_COLORS)),
            "legend.frameon": True,
            "legend.framealpha": 0.96,
            "legend.facecolor": T.surface,
            "legend.edgecolor": T.border,
            "legend.fontsize": 8.5,
            "lines.linewidth": 1.9,
            "lines.markersize": 5.0,
            "figure.facecolor": T.surface,
            "savefig.facecolor": T.surface,
        }
    )
    _MATPLOTLIB_CONFIGURED = True


def style_axes(figure, axes, polar: bool = False) -> None:
    """Match a matplotlib figure to the surrounding card."""
    configure_matplotlib()
    figure.patch.set_facecolor(T.surface)
    axes.set_facecolor(T.surface)
    axes.tick_params(colors=T.text_muted, labelsize=8.5, length=3, width=0.8)
    for label in list(axes.get_xticklabels()) + list(axes.get_yticklabels()):
        label.set_color(T.text_muted)
    axes.xaxis.label.set_color(T.text_muted)
    axes.yaxis.label.set_color(T.text_muted)
    axes.title.set_color(T.ink)
    axes.title.set_fontweight("600")
    axes.grid(True, color=T.border, linewidth=0.8, alpha=0.9)
    axes.set_axisbelow(True)
    if polar:
        for spine in axes.spines.values():
            spine.set_color(T.border)
    else:
        for name, spine in axes.spines.items():
            if name in ("top", "right"):
                spine.set_visible(False)
            else:
                spine.set_color(T.border_strong)
                spine.set_linewidth(0.9)


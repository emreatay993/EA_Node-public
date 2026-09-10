from __future__ import annotations

import pathlib

from PyQt6.QtGui import QColor, QPalette

from ea_node_editor.ui.theme.registry import DEFAULT_THEME_ID, resolve_theme_tokens
from ea_node_editor.ui.theme.tokens import ThemeTokens

_ICONS_DIR = pathlib.Path(__file__).resolve().parent / "icons"


def _icon_path(name: str) -> str:
    """Return a forward-slash absolute path suitable for Qt stylesheet url()."""
    return str(_ICONS_DIR / name).replace("\\", "/")


def build_app_stylesheet(tokens: ThemeTokens) -> str:
    # Resolve icon file paths based on the theme's icon variant
    check_icon = _icon_path(f"check-{tokens.icon_variant}.svg")
    chevron_down_icon = _icon_path(f"chevron-down-{tokens.icon_variant}.svg")
    chevron_up_icon = _icon_path(f"chevron-up-{tokens.icon_variant}.svg")

    return f"""
QMainWindow {{
    background: {tokens.app_bg};
    color: {tokens.app_fg};
}}
QWidget {{
    background: {tokens.app_bg};
    color: {tokens.app_fg};
    font-family: 'Segoe UI';
    font-size: 12px;
}}
QMenuBar {{
    background: {tokens.toolbar_bg};
    color: {tokens.app_fg};
    border-bottom: 1px solid {tokens.border};
}}
QMenuBar::item {{
    background: transparent;
    padding: 4px 11px;
}}
QMenuBar::item:selected {{
    background: {tokens.hover};
}}
QMenu {{
    background: {tokens.panel_bg};
    color: {tokens.panel_title_fg};
    border: 1px solid rgba{(*QColor(tokens.input_border).getRgb()[:3], 235)};
    border-radius: 8px;
    padding: 4px;
}}
QMenu::item {{
    padding: 9px 12px 9px 25px;
    border-left: 3px solid transparent;
    border-radius: 6px;
}}
QMenu::item:selected:enabled {{
    background: rgba{(*QColor(tokens.accent).getRgb()[:3], 31)};
    border-left-color: {tokens.accent};
}}
QMenu::item:disabled {{
    color: rgba{(*QColor(tokens.panel_title_fg).getRgb()[:3], 117)};
}}
QMenu::separator {{
    height: 1px;
    background: rgba{(*QColor(tokens.border).getRgb()[:3], 140)};
    margin: 3px 10px;
}}
QMenu::indicator {{
    width: 14px;
    height: 14px;
    margin-left: 8px;
    border-radius: 3px;
}}
QMenu::indicator:checked {{
    background: {tokens.accent};
    image: url({check_icon});
}}
QToolBar#mainToolbar {{
    background: {tokens.toolbar_bg};
    border-bottom: 1px solid {tokens.border};
    spacing: 5px;
    padding: 3px 6px;
}}
QToolButton {{
    background: {tokens.panel_alt_bg};
    border: 1px solid {tokens.border};
    border-radius: 3px;
    padding: 4px 9px;
    color: {tokens.app_fg};
}}
QToolButton:hover {{
    background: {tokens.hover};
}}
QToolButton:pressed {{
    background: {tokens.pressed};
}}
QPushButton {{
    background: {tokens.panel_alt_bg};
    border: 1px solid {tokens.border};
    border-radius: 3px;
    padding: 4px 8px;
    color: {tokens.app_fg};
}}
QPushButton:hover {{
    background: {tokens.hover};
}}
QPushButton:pressed {{
    background: {tokens.pressed};
}}
QPushButton#workspaceAddButton {{
    padding: 0;
    font-weight: 600;
}}
QPushButton#viewButton {{
    padding: 4px 10px;
}}
QLabel#zoomLabel {{
    color: {tokens.muted_fg};
    padding-left: 4px;
}}
QLineEdit,
QComboBox,
QPlainTextEdit,
QListWidget,
QTreeWidget {{
    background: {tokens.input_bg};
    border: 1px solid {tokens.input_border};
    color: {tokens.input_fg};
    padding: 3px;
    selection-background-color: {tokens.accent_strong};
}}
QSpinBox,
QDoubleSpinBox {{
    background: {tokens.input_bg};
    border: 1px solid {tokens.input_border};
    color: {tokens.input_fg};
    padding: 3px 27px 3px 3px;
    selection-background-color: {tokens.accent_strong};
}}
QSpinBox::up-button,
QDoubleSpinBox::up-button {{
    subcontrol-origin: border;
    subcontrol-position: top right;
    width: 24px;
    border-left: 1px solid {tokens.input_border};
    border-bottom: 1px solid {tokens.input_border};
    background: transparent;
}}
QSpinBox::down-button,
QDoubleSpinBox::down-button {{
    subcontrol-origin: border;
    subcontrol-position: bottom right;
    width: 24px;
    border-left: 1px solid {tokens.input_border};
    background: transparent;
}}
QSpinBox::up-button:hover,
QSpinBox::down-button:hover,
QDoubleSpinBox::up-button:hover,
QDoubleSpinBox::down-button:hover {{
    background: {tokens.hover};
}}
QSpinBox::up-button:pressed,
QSpinBox::down-button:pressed,
QDoubleSpinBox::up-button:pressed,
QDoubleSpinBox::down-button:pressed {{
    background: {tokens.pressed};
}}
QSpinBox::up-arrow,
QDoubleSpinBox::up-arrow {{
    image: url({chevron_up_icon});
    width: 12px;
    height: 12px;
}}
QSpinBox::down-arrow,
QDoubleSpinBox::down-arrow {{
    image: url({chevron_down_icon});
    width: 12px;
    height: 12px;
}}
QComboBox::drop-down {{
    subcontrol-origin: padding;
    subcontrol-position: center right;
    width: 24px;
    border-left: 1px solid {tokens.input_border};
    background: transparent;
}}
QComboBox::down-arrow {{
    image: url({chevron_down_icon});
    width: 12px;
    height: 12px;
}}
QCheckBox {{
    spacing: 8px;
    padding: 3px 0;
    background: transparent;
}}
QRadioButton {{
    spacing: 8px;
    padding: 3px 0;
    background: transparent;
}}
QCheckBox::indicator {{
    width: 16px;
    height: 16px;
    border: 2px solid {tokens.input_border};
    border-radius: 4px;
    background: {tokens.input_bg};
}}
QCheckBox::indicator:hover {{
    border-color: {tokens.accent};
    background: {tokens.hover};
}}
QCheckBox::indicator:checked {{
    background: {tokens.accent_strong};
    border-color: {tokens.accent_strong};
    image: url({check_icon});
}}
QCheckBox::indicator:checked:hover {{
    background: {tokens.accent};
    border-color: {tokens.accent};
    image: url({check_icon});
}}
QRadioButton::indicator {{
    width: 16px;
    height: 16px;
    border: 2px solid {tokens.input_border};
    border-radius: 8px;
    background: {tokens.input_bg};
}}
QRadioButton::indicator:hover {{
    border-color: {tokens.accent};
    background: {tokens.hover};
}}
QRadioButton::indicator:checked {{
    border: 5px solid {tokens.accent_strong};
    border-radius: 8px;
    background: {tokens.input_bg};
}}
QRadioButton::indicator:checked:hover {{
    border-color: {tokens.accent};
    background: {tokens.input_bg};
}}
QSlider {{
    background: transparent;
}}
QSlider::groove:horizontal {{
    height: 4px;
    background: {tokens.input_border};
    border-radius: 2px;
}}
QSlider::handle:horizontal {{
    background: {tokens.accent};
    border: none;
    width: 14px;
    height: 14px;
    margin: -5px 0;
    border-radius: 7px;
}}
QSlider::handle:horizontal:hover {{
    background: {tokens.accent_strong};
}}
QSlider::sub-page:horizontal {{
    background: {tokens.accent_strong};
    border-radius: 2px;
}}
QLabel {{
    background: transparent;
    border: none;
}}
QDialog,
QMessageBox,
QInputDialog {{
    background: {tokens.app_bg};
    color: {tokens.app_fg};
}}
QDialog QLabel,
QMessageBox QLabel,
QInputDialog QLabel {{
    color: {tokens.app_fg};
}}
QDialog QLineEdit,
QDialog QTextEdit,
QDialog QPlainTextEdit,
QDialog QComboBox,
QDialog QSpinBox,
QDialog QDoubleSpinBox,
QDialog QListWidget,
QDialog QTreeWidget,
QMessageBox QLineEdit,
QMessageBox QTextEdit,
QMessageBox QPlainTextEdit,
QMessageBox QComboBox,
QMessageBox QSpinBox,
QMessageBox QDoubleSpinBox,
QMessageBox QListWidget,
QMessageBox QTreeWidget,
QInputDialog QLineEdit,
QInputDialog QTextEdit,
QInputDialog QPlainTextEdit,
QInputDialog QComboBox,
QInputDialog QSpinBox,
QInputDialog QDoubleSpinBox,
QInputDialog QListWidget,
QInputDialog QTreeWidget {{
    background: {tokens.input_bg};
    border: 1px solid {tokens.input_border};
    color: {tokens.input_fg};
    selection-background-color: {tokens.accent_strong};
}}
QDialog QLineEdit:focus,
QDialog QTextEdit:focus,
QDialog QPlainTextEdit:focus,
QDialog QComboBox:focus,
QDialog QSpinBox:focus,
QDialog QDoubleSpinBox:focus,
QDialog QListWidget:focus,
QDialog QTreeWidget:focus,
QMessageBox QLineEdit:focus,
QMessageBox QTextEdit:focus,
QMessageBox QPlainTextEdit:focus,
QMessageBox QComboBox:focus,
QMessageBox QSpinBox:focus,
QMessageBox QDoubleSpinBox:focus,
QMessageBox QListWidget:focus,
QMessageBox QTreeWidget:focus,
QInputDialog QLineEdit:focus,
QInputDialog QTextEdit:focus,
QInputDialog QPlainTextEdit:focus,
QInputDialog QComboBox:focus,
QInputDialog QSpinBox:focus,
QInputDialog QDoubleSpinBox:focus,
QInputDialog QListWidget:focus,
QInputDialog QTreeWidget:focus {{
    border-color: {tokens.accent};
}}
QDialog QLineEdit:read-only,
QDialog QTextEdit:read-only,
QDialog QPlainTextEdit:read-only,
QInputDialog QLineEdit:read-only,
QInputDialog QTextEdit:read-only,
QInputDialog QPlainTextEdit:read-only {{
    background: {tokens.panel_bg};
    border-color: {tokens.border};
    color: {tokens.muted_fg};
}}
QDialog QLineEdit:disabled,
QDialog QTextEdit:disabled,
QDialog QPlainTextEdit:disabled,
QDialog QComboBox:disabled,
QDialog QSpinBox:disabled,
QDialog QDoubleSpinBox:disabled,
QDialog QListWidget:disabled,
QDialog QTreeWidget:disabled,
QMessageBox QLineEdit:disabled,
QMessageBox QTextEdit:disabled,
QMessageBox QPlainTextEdit:disabled,
QMessageBox QComboBox:disabled,
QMessageBox QSpinBox:disabled,
QMessageBox QDoubleSpinBox:disabled,
QMessageBox QListWidget:disabled,
QMessageBox QTreeWidget:disabled,
QInputDialog QLineEdit:disabled,
QInputDialog QTextEdit:disabled,
QInputDialog QPlainTextEdit:disabled,
QInputDialog QComboBox:disabled,
QInputDialog QSpinBox:disabled,
QInputDialog QDoubleSpinBox:disabled,
QInputDialog QListWidget:disabled,
QInputDialog QTreeWidget:disabled {{
    background: {tokens.panel_bg};
    border-color: {tokens.border};
    color: {tokens.muted_fg};
}}
QDialog QDialogButtonBox,
QMessageBox QDialogButtonBox,
QInputDialog QDialogButtonBox {{
    background: transparent;
    border: none;
}}
QDialog QPushButton,
QMessageBox QPushButton,
QInputDialog QPushButton {{
    background: {tokens.panel_alt_bg};
    border: 1px solid {tokens.border};
    color: {tokens.app_fg};
}}
QDialog QPushButton:hover,
QMessageBox QPushButton:hover,
QInputDialog QPushButton:hover {{
    background: {tokens.hover};
}}
QDialog QPushButton:pressed,
QMessageBox QPushButton:pressed,
QInputDialog QPushButton:pressed {{
    background: {tokens.pressed};
}}
QDialog QPushButton:disabled,
QMessageBox QPushButton:disabled,
QInputDialog QPushButton:disabled {{
    background: {tokens.panel_bg};
    border-color: {tokens.border};
    color: {tokens.muted_fg};
}}
QDialog QPushButton:default,
QDialog QPushButton#primaryButton,
QMessageBox QPushButton:default,
QInputDialog QPushButton:default {{
    background: {tokens.panel_alt_bg};
    border: 2px solid {tokens.accent};
    color: {tokens.app_fg};
    font-weight: 600;
    padding: 6px 20px;
}}
QDialog QPushButton:default:hover,
QDialog QPushButton#primaryButton:hover,
QMessageBox QPushButton:default:hover,
QInputDialog QPushButton:default:hover {{
    background: {tokens.hover};
    color: {tokens.app_fg};
}}
QDialog QPushButton:default:pressed,
QDialog QPushButton#primaryButton:pressed,
QMessageBox QPushButton:default:pressed,
QInputDialog QPushButton:default:pressed {{
    background: {tokens.accent_strong};
    color: {tokens.app_fg};
}}
QDialog QPushButton:default:disabled,
QDialog QPushButton#primaryButton:disabled,
QMessageBox QPushButton:default:disabled,
QInputDialog QPushButton:default:disabled {{
    background: {tokens.panel_bg};
    border-color: {tokens.border};
    color: {tokens.muted_fg};
}}
QLabel[dialogRole="muted"] {{
    color: {tokens.muted_fg};
}}
QLabel[dialogRole="error"] {{
    color: {tokens.inspector_danger_fg};
}}
QPushButton[dialogRole="danger"] {{
    color: {tokens.inspector_danger_fg};
}}
QPushButton[dialogRole="danger"]:hover {{
    background: {tokens.inspector_danger_bg};
    border-color: {tokens.inspector_danger_border};
}}
QPushButton[dialogRole="danger"]:disabled {{
    background: {tokens.panel_bg};
    border-color: {tokens.border};
    color: {tokens.muted_fg};
}}
QLineEdit[dialogRole="error"],
QTextEdit[dialogRole="error"],
QPlainTextEdit[dialogRole="error"],
QComboBox[dialogRole="error"],
QSpinBox[dialogRole="error"],
QDoubleSpinBox[dialogRole="error"] {{
    border-color: {tokens.inspector_danger_border};
}}
QFrame[dialogSwatch="true"] {{
    border: 1px solid {tokens.input_border};
    border-radius: 4px;
}}
QFrame[dialogSwatch="true"][dialogRole="empty"] {{
    border-style: dashed;
}}
QFrame[dialogSwatch="true"][dialogRole="error"] {{
    border-color: {tokens.inspector_danger_border};
}}
QFrame#dialogSeparator {{
    background: {tokens.border};
    border: none;
}}
QPushButton#collapsibleSectionHeader {{
    background: transparent;
    border: none;
    border-bottom: 1px solid {tokens.border};
    font-weight: 600;
    padding: 4px 8px;
    text-align: left;
}}
QPushButton#collapsibleSectionHeader:hover {{
    background: {tokens.hover};
}}
QWidget[settingsCard="true"] {{
    background: {tokens.panel_alt_bg};
    border: 1px solid {tokens.border};
    border-radius: 8px;
}}
QLabel[settingsSectionTitle="true"] {{
    font-weight: 600;
    font-size: 11px;
    color: {tokens.muted_fg};
    padding: 0 0 2px 2px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    background: transparent;
    border: none;
}}
QGroupBox {{
    border: 1px solid {tokens.border};
    margin-top: 8px;
    padding-top: 10px;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 8px;
    padding: 0 2px;
    color: {tokens.group_title_fg};
}}
QLabel#panelTitle {{
    color: {tokens.panel_title_fg};
    font-weight: 700;
    letter-spacing: 0.4px;
}}
QWidget#nodeLibraryPanel,
QWidget#inspectorPanel {{
    background: {tokens.panel_bg};
}}
QWidget#workspaceTabStrip {{
    background: {tokens.panel_bg};
    border-top: 1px solid {tokens.border};
    border-bottom: 1px solid {tokens.border};
}}
QTabBar::tab {{
    background: {tokens.tab_bg};
    color: {tokens.tab_fg};
    padding: 5px 11px;
    border: 1px solid {tokens.border};
    border-bottom: 0;
    margin-right: 2px;
}}
QTabBar::tab:selected {{
    background: {tokens.tab_selected_bg};
    color: {tokens.tab_selected_fg};
    border-top: 2px solid {tokens.accent};
}}
QTabBar::tab:hover {{
    background: {tokens.hover};
}}
QTabWidget::pane {{
    border-top: 1px solid {tokens.border};
}}
QWidget#consolePanel {{
    background: {tokens.console_bg};
    border-top: 1px solid {tokens.border};
}}
QSplitter::handle {{
    background: {tokens.splitter_handle};
}}
QSplitter::handle:hover {{
    background: {tokens.splitter_handle_hover};
}}
QStatusBar#mainStatusBar {{
    background: {tokens.status_bg};
    color: {tokens.status_fg};
    min-height: 26px;
    border-top: 1px solid {tokens.status_border};
}}
QStatusBar#mainStatusBar QLabel {{
    color: {tokens.status_fg};
}}
QStatusBar#mainStatusBar > QWidget {{
    color: {tokens.status_fg};
}}
QStatusBar#mainStatusBar > QWidget[clickable="true"]:hover {{
    background: {tokens.status_hover_bg};
    border-radius: 3px;
}}
QDockWidget {{
    titlebar-close-icon: none;
    titlebar-normal-icon: none;
}}
QDockWidget::title {{
    background: {tokens.toolbar_bg};
    text-align: left;
    padding-left: 8px;
    border-bottom: 1px solid {tokens.border};
}}
QScrollBar:vertical {{
    background: {tokens.panel_bg};
    width: 10px;
}}
QScrollBar::handle:vertical {{
    background: {tokens.scrollbar_handle};
    min-height: 20px;
    border-radius: 4px;
}}
QScrollBar:horizontal {{
    background: {tokens.panel_bg};
    height: 10px;
}}
QScrollBar::handle:horizontal {{
    background: {tokens.scrollbar_handle};
    min-width: 20px;
    border-radius: 4px;
}}
"""


def build_theme_stylesheet(theme_id: object = DEFAULT_THEME_ID) -> str:
    return build_app_stylesheet(resolve_theme_tokens(theme_id))


def build_theme_palette(theme_id: object = DEFAULT_THEME_ID) -> QPalette:
    """Build the application palette used by uncustomized Qt Quick Controls."""
    tokens = resolve_theme_tokens(theme_id)
    palette = QPalette()
    for role, color in (
        (QPalette.ColorRole.Window, tokens.app_bg),
        (QPalette.ColorRole.WindowText, tokens.app_fg),
        (QPalette.ColorRole.Base, tokens.input_bg),
        (QPalette.ColorRole.AlternateBase, tokens.panel_alt_bg),
        (QPalette.ColorRole.ToolTipBase, tokens.panel_alt_bg),
        (QPalette.ColorRole.ToolTipText, tokens.app_fg),
        (QPalette.ColorRole.Text, tokens.input_fg),
        (QPalette.ColorRole.Button, tokens.panel_alt_bg),
        (QPalette.ColorRole.ButtonText, tokens.app_fg),
        (QPalette.ColorRole.BrightText, tokens.app_fg),
        (QPalette.ColorRole.Highlight, tokens.accent_strong),
        (QPalette.ColorRole.HighlightedText, tokens.app_fg),
        (QPalette.ColorRole.Link, tokens.accent),
        (QPalette.ColorRole.LinkVisited, tokens.accent),
    ):
        palette.setColor(role, QColor(color))
    return palette

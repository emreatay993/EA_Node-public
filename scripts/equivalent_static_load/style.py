"""Engineering Fusion styling for the ESL GUI.

Palette and QSS adapted from
``scripts/Sensor_Data_Comparison_Tool/sensor_compare_tool/style.py`` (the house
"engineering" look: Fusion base style, light #eef2f6 surfaces, #2d74c4 accent)
— trimmed to the widgets this tool uses and with no external asset files.
"""

from __future__ import annotations

from PyQt6.QtGui import QColor, QPalette


def engineering_palette() -> QPalette:
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor("#eef2f6"))
    palette.setColor(QPalette.ColorRole.WindowText, QColor("#1e2a36"))
    palette.setColor(QPalette.ColorRole.Base, QColor("#ffffff"))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor("#f6f8fb"))
    palette.setColor(QPalette.ColorRole.Text, QColor("#1e2a36"))
    palette.setColor(QPalette.ColorRole.Button, QColor("#ffffff"))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor("#1e2a36"))
    palette.setColor(QPalette.ColorRole.Highlight, QColor("#2d74c4"))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor("#203040"))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor("#ffffff"))
    palette.setColor(QPalette.ColorRole.PlaceholderText, QColor("#7d8a98"))
    return palette


def application_stylesheet() -> str:
    return """
    QWidget {
        background: #eef2f6;
        color: #1e2a36;
        font-family: "Segoe UI", Arial, sans-serif;
        font-size: 10pt;
        selection-background-color: #2d74c4;
        selection-color: #ffffff;
    }
    QMainWindow, QDialog { background: #eef2f6; }

    /* Long-form rich tooltips (formulas render on light boxes) — overrides the
       dark palette ToolTipBase so inline HTML styling stays readable. */
    QToolTip {
        background-color: #ffffff;
        color: #1e2a36;
        border: 1px solid #8fa3b8;
        border-radius: 3px;
        padding: 8px 10px;
        font-size: 9.5pt;
    }
    QLabel, QCheckBox, QRadioButton { background: transparent; }

    QLabel#TitleLabel { font-size: 16pt; font-weight: 650; color: #16212c; }
    QLabel#SectionTitle { font-size: 12pt; font-weight: 650; color: #1c2a38; }
    QLabel#MutedLabel { color: #647386; }
    QLabel#StatusLabel {
        background: #eaf3ff; border: 1px solid #bad5f4; border-radius: 4px;
        padding: 4px 8px; color: #1c3a5a;
    }
    QLabel#WarnLabel {
        background: #fff4e5; border: 1px solid #f0c088; border-radius: 4px;
        padding: 4px 8px; color: #7a4a12;
    }

    QFrame#Panel {
        background: #ffffff; border: 1px solid #d5dde6; border-radius: 6px;
    }
    QFrame#Panel QLabel { background: transparent; }

    QPushButton {
        background: #ffffff; border: 1px solid #b9c6d3; border-radius: 4px;
        padding: 5px 14px; min-height: 20px;
    }
    QPushButton:hover { border-color: #2d74c4; background: #f5f9ff; }
    QPushButton:pressed { background: #e5eefb; }
    QPushButton:disabled { color: #9aa7b5; border-color: #d5dde6; }
    QPushButton#PrimaryButton {
        background: #2d74c4; color: #ffffff; border: 1px solid #2362aa;
        font-weight: 600; padding: 7px 18px;
    }
    QPushButton#PrimaryButton:hover { background: #2f7ed6; }
    QPushButton#PrimaryButton:disabled { background: #9db9d6; border-color: #9db9d6; }

    QLineEdit, QDoubleSpinBox, QSpinBox, QComboBox {
        background: #ffffff; border: 1px solid #b9c6d3; border-radius: 4px;
        padding: 3px 6px; min-height: 20px;
    }
    QLineEdit:focus, QDoubleSpinBox:focus, QSpinBox:focus, QComboBox:focus {
        border-color: #2d74c4;
    }
    /* File paths that do not exist on disk (FileRow open mode). */
    QLineEdit[missingPath="true"] {
        border: 1px solid #c0392b;
        background: #fdf1ef;
    }
    QLineEdit[missingPath="true"]:focus { border-color: #c0392b; }
    QComboBox::drop-down { border: none; width: 20px; }

    QTableWidget, QTableView {
        background: #ffffff; border: 1px solid #d5dde6; gridline-color: #e3e9f0;
        alternate-background-color: #f6f8fb;
    }
    QHeaderView::section {
        background: #f0f4f8; border: none; border-right: 1px solid #d5dde6;
        border-bottom: 1px solid #d5dde6; padding: 4px 6px; font-weight: 600;
    }

    QPlainTextEdit#LogView {
        background: #10161d; color: #cfe3f5; border: 1px solid #26303a;
        font-family: Consolas, "Courier New", monospace; font-size: 9pt;
    }

    QListWidget#StepRail {
        background: #e4eaf1; border: none; outline: none; padding: 6px;
    }
    QListWidget#StepRail::item {
        background: #ffffff; border: 1px solid #cdd7e1; border-radius: 6px;
        padding: 10px 12px; margin: 4px 2px; color: #33475b;
    }
    QListWidget#StepRail::item:hover { border-color: #2d74c4; }
    QListWidget#StepRail::item:selected {
        background: #2d74c4; color: #ffffff; border-color: #2362aa; font-weight: 600;
    }

    QProgressBar {
        background: #ffffff; border: 1px solid #b9c6d3; border-radius: 4px;
        text-align: center; min-height: 16px;
    }
    QProgressBar::chunk { background: #2d74c4; border-radius: 3px; }

    QTabWidget::pane { border: 1px solid #d5dde6; background: #ffffff; }
    QTabBar::tab {
        background: #e8edf3; border: 1px solid #d5dde6; border-bottom: none;
        border-top-left-radius: 4px; border-top-right-radius: 4px;
        padding: 5px 12px; margin-right: 2px;
    }
    QTabBar::tab:selected { background: #ffffff; font-weight: 600; }
    """

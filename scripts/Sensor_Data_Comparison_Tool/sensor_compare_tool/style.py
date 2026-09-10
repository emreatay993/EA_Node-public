from __future__ import annotations

from pathlib import Path

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
    assets_dir = Path(__file__).resolve().parent / "assets"
    checkmark_path = (assets_dir / "checkmark.svg").as_posix()
    chevron_down_path = (assets_dir / "chevron-down.svg").as_posix()
    chevron_up_path = (assets_dir / "chevron-up.svg").as_posix()
    return """
    QWidget {
        background: #eef2f6;
        color: #1e2a36;
        font-family: "Segoe UI", Arial, sans-serif;
        font-size: 10pt;
        selection-background-color: #2d74c4;
        selection-color: #ffffff;
    }

    QMainWindow, QDialog {
        background: #eef2f6;
    }

    QLabel,
    QCheckBox,
    QRadioButton {
        background: transparent;
        background-color: transparent;
    }

    QFrame#Panel QLabel,
    QFrame#Panel QCheckBox,
    QFrame#Panel QRadioButton {
        background: transparent;
        background-color: transparent;
    }

    QCheckBox {
        spacing: 7px;
    }

    QCheckBox::indicator {
        width: 15px;
        height: 15px;
        border: 1px solid #8fa3b8;
        border-radius: 3px;
        background: #ffffff;
        image: none;
    }

    QCheckBox::indicator:hover {
        border-color: #2d74c4;
        background: #f5f9ff;
    }

    QCheckBox::indicator:checked {
        border-color: #2d74c4;
        background: #2d74c4;
        image: url("__CHECKMARK_PATH__");
    }

    QCheckBox::indicator:checked:hover {
        border-color: #2362aa;
        background: #2362aa;
    }

    QCheckBox::indicator:disabled {
        border-color: #c7d1dc;
        background: #eef1f5;
    }

    QCheckBox::indicator:checked:disabled {
        border-color: #9aa7b5;
        background: #9aa7b5;
        image: url("__CHECKMARK_PATH__");
    }

    QCheckBox:disabled {
        color: #7d8a98;
    }

    QLabel#TitleLabel {
        font-size: 18pt;
        font-weight: 650;
        color: #16212c;
    }

    QLabel#SectionTitle {
        font-size: 12pt;
        font-weight: 650;
        color: #1c2a38;
    }

    QLabel#MutedLabel {
        color: #647386;
    }

    QLabel#StatusLabel {
        background: #eaf3ff;
        border: 1px solid #bad5f4;
        border-radius: 6px;
        padding: 9px 12px;
        color: #214c77;
    }

    QLabel#SignAgreementTitle {
        background: transparent;
        color: #173f69;
        font-size: 13pt;
        font-weight: 650;
    }

    QFrame#SignSummaryPanel {
        background: #ffffff;
        border: 1px solid #d3dce7;
        border-radius: 6px;
    }

    QLabel#SignHoverLabel {
        background: #f6f9fc;
        border: 1px solid #d1dbe7;
        border-radius: 5px;
        padding: 7px 9px;
        color: #34485c;
    }

    QTableWidget#SignSummaryTable {
        border: 1px solid #cbd6e2;
        border-radius: 5px;
        gridline-color: #e1e8f0;
        alternate-background-color: #f7fafc;
    }

    QFrame#MetricHelpPopover {
        background: #ffffff;
        border: 1px solid #aebdcb;
        border-radius: 6px;
    }

    QTextBrowser#MetricHelpText {
        background: #ffffff;
        border: 0;
        padding: 12px 14px;
        color: #1e2a36;
    }

    QToolButton#MetricHelpPinButton {
        background: #f8fbff;
        border: 1px solid #c5d1de;
        border-radius: 4px;
        padding: 3px;
    }

    QToolButton#MetricHelpPinButton:hover {
        background: #edf5ff;
        border-color: #7fa6d4;
    }

    QToolButton#MetricHelpPinButton:checked {
        background: #d8e9fb;
        border-color: #2d74c4;
    }

    QTextBrowser#MetricHelpText QScrollBar:vertical {
        background: #f6f9fc;
        border: 1px solid #d1dbe7;
        width: 12px;
        margin: 4px 3px 4px 0;
        border-radius: 6px;
    }

    QTextBrowser#MetricHelpText QScrollBar::handle:vertical {
        background: #b8c4d1;
        border-radius: 5px;
        min-height: 34px;
    }

    QTextBrowser#MetricHelpText QScrollBar::handle:vertical:hover {
        background: #7fa6d4;
    }

    QTextBrowser#MetricHelpText QScrollBar::handle:vertical:pressed {
        background: #2d74c4;
    }

    QTextBrowser#MetricHelpText QScrollBar::add-line:vertical,
    QTextBrowser#MetricHelpText QScrollBar::sub-line:vertical,
    QTextBrowser#MetricHelpText QScrollBar::add-page:vertical,
    QTextBrowser#MetricHelpText QScrollBar::sub-page:vertical {
        background: transparent;
        border: 0;
        height: 0;
    }

    QTextBrowser#MetricHelpText QScrollBar:horizontal {
        background: #f6f9fc;
        border: 1px solid #d1dbe7;
        height: 12px;
        margin: 0 4px 3px 4px;
        border-radius: 6px;
    }

    QTextBrowser#MetricHelpText QScrollBar::handle:horizontal {
        background: #b8c4d1;
        border-radius: 5px;
        min-width: 34px;
    }

    QTextBrowser#MetricHelpText QScrollBar::handle:horizontal:hover {
        background: #7fa6d4;
    }

    QTextBrowser#MetricHelpText QScrollBar::handle:horizontal:pressed {
        background: #2d74c4;
    }

    QTextBrowser#MetricHelpText QScrollBar::add-line:horizontal,
    QTextBrowser#MetricHelpText QScrollBar::sub-line:horizontal,
    QTextBrowser#MetricHelpText QScrollBar::add-page:horizontal,
    QTextBrowser#MetricHelpText QScrollBar::sub-page:horizontal {
        background: transparent;
        border: 0;
        width: 0;
    }

    QLabel#SummaryCard, QFrame#Panel {
        background: #ffffff;
        border: 1px solid #d3dce7;
        border-radius: 6px;
    }

    QLabel#SummaryCard {
        padding: 10px 12px;
        color: #263545;
    }

    QWidget#PaneHeader {
        background: transparent;
        background-color: transparent;
    }

    QFrame#Sidebar {
        background: #223141;
        border: 1px solid #182532;
        border-radius: 6px;
    }

    QFrame#Sidebar QLabel#SectionTitle {
        color: #f4f7fb;
        font-size: 12pt;
        font-weight: 700;
    }

    QFrame#StepCard {
        background: #2b3c4f;
        border: 1px solid #405369;
        border-radius: 5px;
    }

    QFrame#StepCard[state="current"] {
        border: 1px solid #60a5fa;
        background: #f5f9ff;
    }

    QFrame#StepCard[state="completed"] {
        border: 1px solid #55718e;
        background: #30455b;
    }

    QFrame#StepCard[state="upcoming"] {
        border: 1px solid #42566d;
        background: #2b3c4f;
    }

    QLabel#StepLabel {
        background: transparent;
        font-size: 10.5pt;
        font-weight: 650;
    }

    QLabel#StepLabel[state="current"] {
        color: #173f69;
    }

    QLabel#StepLabel[state="completed"] {
        color: #f4f8fd;
    }

    QLabel#StepLabel[state="upcoming"] {
        color: #d8e3ef;
    }

    QWidget#CollapsibleColumnShell {
        background: transparent;
    }

    QFrame#CollapsedPaneRail {
        background: transparent;
        border: 0;
    }

    QLineEdit, QComboBox, QDoubleSpinBox {
        background: #ffffff;
        border: 1px solid #b8c4d1;
        border-radius: 5px;
        min-height: 30px;
        padding: 4px 9px;
    }

    QComboBox, QDoubleSpinBox {
        padding-right: 34px;
    }

    QComboBox:hover, QDoubleSpinBox:hover {
        border-color: #7fa6d4;
        background: #fbfdff;
    }

    QLineEdit:focus, QComboBox:focus, QDoubleSpinBox:focus {
        border: 1px solid #2d74c4;
    }

    QLineEdit[readOnly="true"] {
        color: #4f5f70;
        background: #f6f8fb;
    }

    QComboBox::drop-down {
        subcontrol-origin: border;
        subcontrol-position: top right;
        width: 29px;
        border-left: 1px solid #d1dbe7;
        border-top-right-radius: 5px;
        border-bottom-right-radius: 5px;
        background: #f6f9fc;
    }

    QComboBox::drop-down:hover {
        background: #eaf3ff;
        border-left-color: #a9c4e4;
    }

    QComboBox::down-arrow {
        image: url("__CHEVRON_DOWN_PATH__");
        width: 11px;
        height: 11px;
    }

    QComboBox QAbstractItemView {
        background: #ffffff;
        border: 1px solid #aebdcb;
        border-radius: 5px;
        outline: 0;
        selection-background-color: #d9eaff;
        selection-color: #173f69;
        padding: 3px;
    }

    QDoubleSpinBox::up-button {
        subcontrol-origin: border;
        subcontrol-position: top right;
        width: 29px;
        border-left: 1px solid #d1dbe7;
        border-bottom: 1px solid #d1dbe7;
        border-top-right-radius: 5px;
        background: #f6f9fc;
    }

    QDoubleSpinBox::down-button {
        subcontrol-origin: border;
        subcontrol-position: bottom right;
        width: 29px;
        border-left: 1px solid #d1dbe7;
        border-bottom-right-radius: 5px;
        background: #f6f9fc;
    }

    QDoubleSpinBox::up-button:hover,
    QDoubleSpinBox::down-button:hover {
        background: #eaf3ff;
        border-left-color: #a9c4e4;
    }

    QDoubleSpinBox::up-button:pressed,
    QDoubleSpinBox::down-button:pressed {
        background: #dbeafe;
    }

    QDoubleSpinBox::up-arrow {
        image: url("__CHEVRON_UP_PATH__");
        width: 9px;
        height: 9px;
    }

    QDoubleSpinBox::down-arrow {
        image: url("__CHEVRON_DOWN_PATH__");
        width: 9px;
        height: 9px;
    }

    QPushButton {
        background: #f9fbfd;
        color: #1f2d3b;
        border: 1px solid #b8c4d1;
        border-radius: 5px;
        min-height: 30px;
        padding: 5px 13px;
    }

    QPushButton:hover {
        background: #eef5fd;
        border-color: #7fa6d4;
    }

    QPushButton:pressed {
        background: #dfeaf7;
    }

    QPushButton[modeButton="true"] {
        min-width: 210px;
        font-weight: 600;
    }

    QPushButton[modeButton="true"]:checked {
        background: #2d74c4;
        border-color: #2d74c4;
        color: #ffffff;
    }

    QPushButton[modeButton="true"]:checked:hover {
        background: #2362aa;
        border-color: #2362aa;
    }

    QPushButton[variant="primary"] {
        background: #2d74c4;
        border-color: #2d74c4;
        color: #ffffff;
        font-weight: 650;
    }

    QPushButton[variant="primary"]:hover {
        background: #2362aa;
        border-color: #2362aa;
    }

    QPushButton[variant="danger"] {
        color: #9d3030;
        border-color: #e0b7b7;
    }

    QPushButton[iconButton="true"] {
        background: #f7fafc;
        border: 1px solid #bac8d8;
        border-radius: 5px;
        padding: 0;
        min-width: 34px;
        min-height: 30px;
        max-width: 38px;
        max-height: 34px;
    }

    QPushButton[iconButton="true"]:hover {
        background: #e8f2ff;
        border-color: #6ea2da;
    }

    QPushButton[iconButton="true"]:pressed {
        background: #d8e9fb;
        border-color: #2d74c4;
    }

    QPushButton[paneHandle="true"] {
        background: transparent;
        border: 1px solid transparent;
        border-radius: 4px;
        padding: 0;
        min-width: 26px;
        min-height: 24px;
        max-width: 28px;
        max-height: 26px;
    }

    QPushButton[paneHandle="true"]:hover {
        background: #e8f2ff;
        border-color: #bac8d8;
    }

    QPushButton[paneHandle="true"]:pressed {
        background: #d8e9fb;
        border-color: #7fa6d4;
    }

    QPushButton[paneHandle="true"][paneTheme="sidebar"] {
        background: transparent;
        border-color: transparent;
    }

    QPushButton[paneHandle="true"][paneTheme="sidebar"]:hover {
        background: #30455b;
        border-color: #55718e;
    }

    QPushButton[paneHandle="true"][paneTheme="sidebar"]:pressed {
        background: #36506a;
        border-color: #7fa6d4;
    }

    QPushButton:disabled {
        background: #eef1f5;
        color: #9aa7b5;
        border-color: #dbe2ea;
    }

    QListWidget, QTableWidget, QTableView {
        background: #ffffff;
        border: 1px solid #cbd6e2;
        border-radius: 5px;
        alternate-background-color: #f6f8fb;
    }

    QListWidget::item {
        min-height: 25px;
        padding: 4px 7px;
    }

    QListWidget::item:selected {
        background: #d9eaff;
        color: #173f69;
    }

    QHeaderView::section {
        background: #e8eef5;
        border: 0;
        border-right: 1px solid #cbd6e2;
        border-bottom: 1px solid #cbd6e2;
        padding: 6px;
        font-weight: 650;
    }

    QTabWidget::pane {
        background: #ffffff;
        border: 1px solid #cbd6e2;
        border-radius: 6px;
        top: -1px;
    }

    QTabBar::tab {
        background: #e3eaf2;
        border: 1px solid #cbd6e2;
        border-bottom: 0;
        border-top-left-radius: 5px;
        border-top-right-radius: 5px;
        padding: 7px 14px;
        margin-right: 2px;
    }

    QTabBar::tab:selected {
        background: #ffffff;
        color: #173f69;
        font-weight: 650;
    }

    QScrollBar:vertical {
        background: #f6f9fc;
        border: 1px solid #d1dbe7;
        width: 12px;
        margin: 2px;
        border-radius: 6px;
    }

    QScrollBar::handle:vertical {
        background: #b8c4d1;
        border-radius: 5px;
        min-height: 34px;
    }

    QScrollBar::handle:vertical:hover {
        background: #7fa6d4;
    }

    QScrollBar::handle:vertical:pressed {
        background: #2d74c4;
    }

    QScrollBar::add-line:vertical,
    QScrollBar::sub-line:vertical,
    QScrollBar::add-page:vertical,
    QScrollBar::sub-page:vertical {
        background: transparent;
        border: 0;
        height: 0;
    }

    QScrollBar:horizontal {
        background: #f6f9fc;
        border: 1px solid #d1dbe7;
        height: 12px;
        margin: 2px;
        border-radius: 6px;
    }

    QScrollBar::handle:horizontal {
        background: #b8c4d1;
        border-radius: 5px;
        min-width: 34px;
    }

    QScrollBar::handle:horizontal:hover {
        background: #7fa6d4;
    }

    QScrollBar::handle:horizontal:pressed {
        background: #2d74c4;
    }

    QScrollBar::add-line:horizontal,
    QScrollBar::sub-line:horizontal,
    QScrollBar::add-page:horizontal,
    QScrollBar::sub-page:horizontal {
        background: transparent;
        border: 0;
        width: 0;
    }

    QSplitter::handle {
        background: #d7e0ea;
    }

    QSplitter::handle:vertical {
        height: 7px;
        background: #d7e0ea;
    }

    QSplitter::handle:vertical:hover {
        background: #7fa6d4;
    }
    """.replace("__CHECKMARK_PATH__", checkmark_path).replace(
        "__CHEVRON_DOWN_PATH__",
        chevron_down_path,
    ).replace("__CHEVRON_UP_PATH__", chevron_up_path)

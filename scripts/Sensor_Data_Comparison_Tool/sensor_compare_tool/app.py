from __future__ import annotations

import sys

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication

from .style import application_stylesheet, engineering_palette
from .wizard import SensorComparisonWindow


def main(argv: list[str] | None = None) -> int:
    QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts, True)
    app = QApplication(argv or sys.argv)
    app.setApplicationName("Sensor Data Comparison Tool")
    app.setStyle("Fusion")
    app.setPalette(engineering_palette())
    app.setStyleSheet(application_stylesheet())
    window = SensorComparisonWindow()
    window.showMaximized()
    return app.exec()

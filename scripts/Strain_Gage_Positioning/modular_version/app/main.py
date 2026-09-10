"""Launch the Strain Gage Positioning GUI."""

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_API", "pyqt6")

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication

from app.main_window import MainWindow


def main():
    """
    The main entry point for the application.
    Initializes the QApplication and the MainWindow, then starts the event loop.
    """
    # Qt 6 enables high-DPI scaling by default; keep older attributes optional.
    for attr_name in ("AA_EnableHighDpiScaling", "AA_UseHighDpiPixmaps"):
        attr = getattr(Qt.ApplicationAttribute, attr_name, None)
        if attr is not None:
            QApplication.setAttribute(attr, True)

    app = QApplication(sys.argv)

    # Load a global stylesheet (keeps styling separate from code)
    qss_path = Path(__file__).with_name("styles.qss")
    if qss_path.is_file():
        app.setStyleSheet(qss_path.read_text(encoding="utf-8"))

    # Instantiate and show the main window
    win = MainWindow()
    win.show()

    # Start the application's event loop
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

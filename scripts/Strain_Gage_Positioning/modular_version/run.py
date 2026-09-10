"""Run the Strain Gage Positioning GUI from this folder."""

import sys


if __name__ == "__main__":
    if "--smoke" in sys.argv:
        from app.main_window import MainWindow

        assert MainWindow.__name__ == "MainWindow"
        print("smoke ok")
        raise SystemExit(0)

    from app.main import main

    main()

# Purpose: Capture deterministic native splash frames and prove the loading handoff.
# Map: docs/agent_maps/feature_routes/shell_startup_qml_context_splash.md
# Tests: tests/test_main_bootstrap.py
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scale", type=float, choices=(1.0, 1.5, 2.0), default=1.0)
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts/splash_preview"))
    args = parser.parse_args()
    os.environ["QT_QPA_PLATFORM"] = "windows" if sys.platform == "win32" else "offscreen"
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

    from PyQt6.QtCore import Qt
    from PyQt6.QtGui import QImage
    from PyQt6.QtWidgets import QApplication, QWidget

    from ea_node_editor.ui.splash.opening_screen import BOOT_STEPS, OpeningSplash

    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication([])
    output = args.output_dir.resolve() / f"scale-{args.scale:g}"
    output.mkdir(parents=True, exist_ok=True)
    splash = OpeningSplash()
    splash.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
    completed: list[bool] = []
    splash.boot_completed.connect(lambda: completed.append(True))
    splash.show_centered()
    splash._boot_timer.stop()
    splash._animation_timer.stop()
    frames: dict[str, list[int]] = {}

    def capture(name: str, elapsed_ms: int) -> None:
        splash._animation_ms = elapsed_ms
        image = QImage(round(720 * args.scale), round(440 * args.scale), QImage.Format.Format_ARGB32_Premultiplied)
        image.setDevicePixelRatio(args.scale)
        image.fill(Qt.GlobalColor.transparent)
        splash.render(image)
        assert abs(image.devicePixelRatioF() - args.scale) < 0.01
        assert image.width() == round(720 * args.scale)
        assert image.height() == round(440 * args.scale)
        assert image.save(str(output / f"{name}.png"))
        frames[name] = [image.width(), image.height()]

    for elapsed in (0, 300, 1000):
        capture(f"entrance-{elapsed:04}", elapsed)
    for _ in range(len(BOOT_STEPS) - 1):
        splash._advance_step()
    app.processEvents()
    assert completed == [True]
    assert splash._step_index == len(BOOT_STEPS) - 2
    capture("waiting-12000", 12000)
    splash.set_busy_message("Building workspace", "Preparing the main workspace and restoring interface state.")
    capture("building-workspace", 12500)
    splash.mark_ready()
    assert splash.accessibleDescription().startswith("Ready.")
    capture("ready", 13000)

    window = QWidget()
    window.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
    splash.finish(window, min_visible_ms=0)
    assert window.isVisible() and not splash.isVisible()
    assert not splash._animation_timer.isActive() and not splash._boot_timer.isActive()
    window.close()
    app.processEvents()
    result = {"scale": args.scale, "platform": app.platformName(), "window_dpr": window.devicePixelRatioF(), "frames": frames,
              "boot_completed": len(completed), "handoff": "passed"}
    (output / "checks.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result))


if __name__ == "__main__":
    main()

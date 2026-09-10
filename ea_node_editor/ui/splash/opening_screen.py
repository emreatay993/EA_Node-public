# Purpose: Paint the native COREX splash and expose its existing startup handoff.
# Map: docs/agent_maps/feature_routes/shell_startup_qml_context_splash.md
# Tests: tests/test_main_bootstrap.py
from __future__ import annotations

import math

from PyQt6.QtCore import QEasingCurve, QElapsedTimer, QPointF, QRectF, QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import (
    QBrush, QColor, QCloseEvent, QFont, QFontMetricsF, QLinearGradient,
    QPainter, QPainterPath, QPen, QRadialGradient,
)
from PyQt6.QtWidgets import QApplication, QWidget


SPLASH_W = 720
SPLASH_H = 440

# Scale only the emblem around the reference center; text uses the original box.
REFERENCE_MARK_SIZE = 172
MARK_SIZE = REFERENCE_MARK_SIZE * 1.15
MARK_CENTER = QPointF(SPLASH_W / 2, SPLASH_H * 0.08 + REFERENCE_MARK_SIZE / 2)
WORDMARK_TOP = SPLASH_H * 0.08 + REFERENCE_MARK_SIZE + 14
BREATHE_MS = 6912

BOOT_STEPS: tuple[str, ...] = (
    "Initialising runtime…",
    "Loading registry",
    "Scanning plug-ins",
    "Preparing add-ons",
    "Ready",
)
BOOT_STEP_DETAILS: tuple[str, ...] = (
    "Starting application services and preferences.",
    "Building the node catalog in the background.",
    "Discovering plug-ins and add-on descriptors.",
    "Loading optional integrations and node metadata; this can take a moment.",
    "Opening the workspace shell.",
)
STEP_MS = 720


class OpeningSplash(QWidget):
    """Frameless 720 × 440 splash with a layered blue background and COREX mark.

    Entrance and ambient motion are cosmetic. The boot timer and app coordinator
    still determine when registry loading can hand off to the workspace shell.
    """

    boot_completed = pyqtSignal()

    def __init__(
        self,
        *,
        version: str = "v0.9.3",
        mark_size: float = MARK_SIZE,
        breathe_ms: int = BREATHE_MS,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent, Qt.WindowType.SplashScreen | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setFixedSize(QSize(SPLASH_W, SPLASH_H))
        self._version = str(version)
        self._mark_size = float(mark_size)
        self._breathe_ms = max(1, int(breathe_ms))
        self.setAccessibleName(f"COREX Node Editor {self._version}")

        self._shown_timer = QElapsedTimer()
        self._animation_ms = 0
        self._entrance_curve = QEasingCurve(QEasingCurve.Type.OutCubic)
        self._animation_timer = QTimer(self)
        self._animation_timer.setInterval(33)
        self._animation_timer.timeout.connect(self._advance_animation)

        self._step_index = 0
        self._boot_completed_emitted = False
        self._status_label_override: str | None = None
        self._status_detail_override: str | None = None
        self._boot_timer = QTimer(self)
        self._boot_timer.setInterval(STEP_MS)
        self._boot_timer.timeout.connect(self._advance_step)
        self._refresh_status()

    def show_centered(self, screen=None) -> None:
        target = screen or QApplication.primaryScreen()
        if target is not None:
            geometry = target.availableGeometry()
            self.move(geometry.center().x() - SPLASH_W // 2, geometry.center().y() - SPLASH_H // 2)
        self._animation_ms = 0
        self._shown_timer.start()
        self.show()
        self._animation_timer.start()
        self._boot_timer.start()

    def finish(self, next_widget: QWidget | None = None, *, min_visible_ms: int = 1200) -> None:
        """Close the splash and raise the main window, enforcing a minimum visible time."""
        elapsed = self._shown_timer.elapsed() if self._shown_timer.isValid() else 0
        remaining = max(0, min_visible_ms - int(elapsed))

        def _close() -> None:
            self._boot_timer.stop()
            self._animation_timer.stop()
            if next_widget is not None:
                next_widget.show()
                next_widget.raise_()
                next_widget.activateWindow()
            self.close()

        if remaining == 0:
            _close()
        else:
            QTimer.singleShot(remaining, _close)

    def mark_ready(self) -> None:
        """Paint the final handoff state once the shell is ready to show."""
        self._status_label_override = None
        self._status_detail_override = None
        self._step_index = len(BOOT_STEPS) - 1
        self._refresh_status()

    def set_busy_message(self, label: str, detail: str | None = None) -> None:
        """Show a concrete startup task while the main thread does handoff work."""
        self._status_label_override = str(label)
        self._status_detail_override = str(detail) if detail else None
        self._refresh_status()

    def _refresh_status(self) -> None:
        label = self._status_label_override or BOOT_STEPS[self._step_index]
        detail = self._status_detail_override or BOOT_STEP_DETAILS[self._step_index]
        self.setAccessibleDescription(f"{label}. {detail}")
        self.setToolTip(detail)
        self.update()

    def _advance_animation(self) -> None:
        self._animation_ms = self._shown_timer.elapsed()
        self.update()

    def _entrance(self, delay_ms: int, duration_ms: int) -> float:
        progress = max(0.0, min(1.0, (self._animation_ms - delay_ms) / duration_ms))
        return self._entrance_curve.valueForProgress(progress)

    def _advance_step(self) -> None:
        if self._boot_completed_emitted:
            return
        handoff_wait_step_index = max(0, len(BOOT_STEPS) - 2)
        if self._step_index < handoff_wait_step_index:
            self._step_index += 1
            self._refresh_status()
            return
        self._boot_timer.stop()
        self._boot_completed_emitted = True
        QTimer.singleShot(0, self.boot_completed.emit)

    def closeEvent(self, event: QCloseEvent) -> None:
        self._animation_timer.stop()
        self._boot_timer.stop()
        super().closeEvent(event)

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        frame = QPainterPath()
        frame.addRoundedRect(QRectF(0.5, 0.5, SPLASH_W - 1, SPLASH_H - 1), 8, 8)
        p.setClipPath(frame)
        self._paint_background(p)
        self._paint_mark(p)
        self._paint_wordmark(p)
        self._paint_progress(p)
        p.setClipping(False)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QColor("#27456C"), 1))
        p.drawPath(frame)
        p.end()

    def _paint_background(self, p: QPainter) -> None:
        w, h, t = SPLASH_W, SPLASH_H, self._animation_ms
        background = QRadialGradient(QPointF(w * 0.5 + math.sin(t / 2300) * 15, h * 0.28), max(w * 0.7, h))
        background.setColorAt(0, QColor("#0C4769"))
        background.setColorAt(1, QColor("#070F22"))
        p.fillRect(self.rect(), background)
        radiance = QRadialGradient(QPointF(w * 0.5, h * 0.3), h * 0.52)
        radiance.setColorAt(0, QColor(33, 134, 223, 53))
        radiance.setColorAt(1, QColor(33, 134, 223, 0))
        p.fillRect(self.rect(), radiance)

        # Repeating bands wrap seamlessly if registry loading takes a long time.
        drift = (t * 0.002) % (w * 0.25)
        for i in range(-3, 7):
            x = i * w * 0.25 + drift
            band = QPainterPath(QPointF(x, 0))
            band.lineTo(x + w * 0.2, 0)
            band.lineTo(x - w * 0.25, h)
            band.lineTo(x - w * 0.45, h)
            band.closeSubpath()
            p.fillPath(band, QColor(156, 202, 255, 4))
            p.setPen(QPen(QColor(174, 218, 255, 10), 0.8))
            p.drawLine(QPointF(x, 0), QPointF(x - w * 0.45, h))

        p.setBrush(Qt.BrushStyle.NoBrush)
        for side in (-1, 1):
            start, direction = (0 if side < 0 else w), -side
            for i in range(4):
                y = h * (0.15 + i * 0.15)
                inset = w * (0.09 + (i % 2) * 0.085)
                end_y = y + (1 if i % 2 else -1) * h * 0.06
                end_x = start + direction * (inset + w * 0.09)
                trace = QPainterPath(QPointF(start, y))
                trace.lineTo(start + direction * inset, y)
                trace.lineTo(start + direction * (inset + w * 0.045), end_y)
                trace.lineTo(end_x, end_y)
                p.setPen(QPen(QColor(101, 193, 250, 72), 0.9))
                p.drawPath(trace)
                p.setPen(QPen(QColor(100, 189, 237, 136), 1))
                p.drawEllipse(QPointF(end_x, end_y), 3.2, 3.2)

        p.setPen(QPen(QColor(140, 189, 227, 19), 0.7))
        for i in range(11):
            p.drawLine(QPointF(w * 0.5, h * 0.67), QPointF(w * i / 10, h))
        for i in range(6):
            y = h * (0.69 + 0.012 * i * i)
            p.drawLine(QPointF(0, y), QPointF(w, y))
        floor = QLinearGradient(0, h * 0.7, 0, h)
        floor.setColorAt(0, QColor(8, 18, 37, 0))
        floor.setColorAt(1, QColor("#081225"))
        p.fillRect(QRectF(0, h * 0.7, w, h * 0.3), floor)

    def _paint_mark(self, p: QPainter) -> None:
        p.save()
        p.translate(MARK_CENTER)
        scale = self._mark_size / REFERENCE_MARK_SIZE
        p.scale(scale, scale)
        offset = REFERENCE_MARK_SIZE * 0.285
        corners = ((-offset, -offset), (offset, -offset), (-offset, offset), (offset, offset))
        connection = self._entrance(200, 450)
        for x, y in corners:
            end = QPointF(x * connection, y * connection)
            for width, alpha in ((9, 12), (5.5, 26)):
                p.setPen(QPen(QColor(44, 129, 255, alpha), width, cap=Qt.PenCapStyle.FlatCap))
                p.drawLine(QPointF(), end)
            gradient = QLinearGradient(QPointF(), QPointF(x, y))
            gradient.setColorAt(0, QColor("#39DCFF"))
            gradient.setColorAt(1, QColor("#4386FF"))
            p.setPen(QPen(QBrush(gradient), 3, cap=Qt.PenCapStyle.FlatCap))
            p.drawLine(QPointF(), end)

        for i, (x, y) in enumerate(corners):
            entrance = self._entrance(40 + i * 45, 440)
            p.setOpacity(entrance)
            center = QPointF(
                x + math.copysign(10 * (1 - entrance), x),
                y + math.copysign(10 * (1 - entrance), y),
            )
            radius = REFERENCE_MARK_SIZE * 0.105 / 2
            glow = QRadialGradient(center, radius + 10)
            glow.setColorAt(0, QColor(52, 127, 245, 35))
            glow.setColorAt(1, QColor(52, 127, 245, 0))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(glow)
            p.drawEllipse(center, radius + 10, radius + 10)
            p.setBrush(QColor("#112747"))
            p.setPen(QPen(QColor("#5197FF"), 2))
            p.drawEllipse(center, radius - 1, radius - 1)

        p.setOpacity(self._entrance(300, 700))
        breathe = 1 + 0.035 * math.sin(self._animation_ms * 2 * math.pi / self._breathe_ms)
        p.scale(breathe, breathe)
        radius = REFERENCE_MARK_SIZE * 0.08
        p.setPen(Qt.PenStyle.NoPen)
        glow = QRadialGradient(QPointF(), radius + 25)
        glow.setColorAt(0, QColor(71, 180, 255, 102))
        glow.setColorAt(1, QColor(71, 180, 255, 0))
        p.setBrush(glow)
        p.drawEllipse(QPointF(), radius + 25, radius + 25)
        for spread, color in ((18, QColor(69, 144, 255, 12)), (8, QColor(76, 154, 255, 24))):
            p.setBrush(color)
            p.drawEllipse(QPointF(), radius + spread, radius + spread)
        core = QRadialGradient(QPointF(-0.32 * radius, -0.5 * radius), radius * 2)
        core.setColorAt(0, QColor("#B8F7FF"))
        core.setColorAt(0.4, QColor("#1CCCF0"))
        core.setColorAt(0.95, QColor("#3272FF"))
        core.setColorAt(1, QColor("#3272FF"))
        p.setBrush(core)
        p.drawEllipse(QPointF(), radius, radius)
        p.restore()

    def _paint_wordmark(self, p: QPainter) -> None:
        entrance = self._entrance(350, 600)
        p.save()
        p.setOpacity(entrance)
        p.translate(0, (1 - entrance) * 4)
        font = QFont("Segoe UI Variable", -1, QFont.Weight.Medium)
        font.setPixelSize(45)
        font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 45 * 0.09)
        metrics = QFontMetricsF(font)
        left = (SPLASH_W - metrics.horizontalAdvance("COREX")) / 2
        baseline = WORDMARK_TOP + (45 * 1.15 - metrics.height()) / 2 + metrics.ascent()
        p.setFont(font)
        p.setPen(QColor("#F2F6FF"))
        p.drawText(QPointF(left, baseline), "CORE")
        x_left = left + metrics.horizontalAdvance("CORE")
        x_color = QLinearGradient(x_left, WORDMARK_TOP, x_left + metrics.horizontalAdvance("X"), baseline)
        x_color.setColorAt(0, QColor("#6AA4FF"))
        x_color.setColorAt(1, QColor("#58E8FF"))
        p.setPen(QPen(QBrush(x_color), 1))
        p.drawText(QPointF(x_left, baseline), "X")

        subtitle_font = QFont("Segoe UI", -1, QFont.Weight.Normal)
        subtitle_font.setPixelSize(12)
        subtitle_font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 12 * 0.11)
        p.setFont(subtitle_font)
        p.setPen(QColor("#BDD0ED"))
        metrics = QFontMetricsF(subtitle_font)
        top = WORDMARK_TOP + 45 * 1.15 + 8
        p.drawText(
            QPointF((SPLASH_W - metrics.horizontalAdvance("NODE EDITOR")) / 2,
                    top + (18 - metrics.height()) / 2 + metrics.ascent()),
            "NODE EDITOR",
        )
        p.restore()

    def _paint_progress(self, p: QPainter) -> None:
        margin = SPLASH_W * 0.07
        width = SPLASH_W - margin * 2
        bar_y = SPLASH_H * 0.93 - 3
        row_top = bar_y - 13 - 16.5
        p.setPen(QPen(QColor(152, 192, 255, 34), 1))
        p.drawLine(QPointF(margin, row_top - 15), QPointF(SPLASH_W - margin, row_top - 15))

        tag_font = QFont("Cascadia Mono", -1, QFont.Weight.Normal)
        tag_font.setPixelSize(11)
        tag_width = QFontMetricsF(tag_font).horizontalAdvance("COREX")
        label_font = QFont("Segoe UI", -1, QFont.Weight.Normal)
        label_font.setPixelSize(11)
        metrics = QFontMetricsF(label_font)
        label = self._status_label_override or BOOT_STEPS[self._step_index]
        label = metrics.elidedText(label, Qt.TextElideMode.ElideRight, int(width - tag_width - 24))
        baseline = row_top + (16.5 - metrics.height()) / 2 + metrics.ascent()
        p.setFont(label_font)
        p.setPen(QColor("#BDD0ED"))
        p.drawText(QPointF(margin, baseline), label)
        p.setFont(tag_font)
        p.drawText(QPointF(SPLASH_W - margin - tag_width, baseline), "COREX")

        p.fillRect(QRectF(margin, bar_y, width, 3), QColor(168, 205, 255, 34))
        progress = self._step_index / (len(BOOT_STEPS) - 1)
        if progress > 0:
            fill = QRectF(margin, bar_y, width * progress, 3)
            gradient = QLinearGradient(fill.topLeft(), fill.topRight())
            gradient.setColorAt(0, QColor("#3675FF"))
            gradient.setColorAt(1, QColor("#60CEFF"))
            p.fillRect(fill, gradient)


__all__ = ["OpeningSplash", "BOOT_STEPS", "BOOT_STEP_DETAILS"]

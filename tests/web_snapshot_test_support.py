from PyQt6.QtCore import QBuffer, QByteArray, QIODevice
from PyQt6.QtGui import QColor, QImage


def png_bytes(width: int = 640, height: int = 360, color: str = "#2876bd") -> bytes:
    image = QImage(width, height, QImage.Format.Format_ARGB32)
    image.fill(QColor(color))
    data = QByteArray()
    device = QBuffer(data)
    device.open(QIODevice.OpenModeFlag.WriteOnly)
    assert image.save(device, "PNG")
    return bytes(data)

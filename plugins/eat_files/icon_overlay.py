"""给吃文件叠加拖入文件的系统图标"""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QFileInfo, QPointF, Qt
from PyQt6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPixmap, QPolygonF
from PyQt6.QtWidgets import QFileIconProvider

from core.playback.clip import Clip
from core.playback.overlay_clip import PixmapOverlayConfig, clip_with_pixmap_overlay


def clip_with_file_icon(
    clip: Clip,
    path: Path | None,
    *,
    icon_size_ratio: float = 0.15,
    center_x_ratio: float = 0.5,
    center_y_ratio: float = 0.575,
    visible_start_ratio: float = 0.0,
    visible_end_ratio: float = 1.0,
    opacity: float = 1.0,
    layer: str = "behind_front",
) -> Clip:
    return clip_with_pixmap_overlay(
        clip,
        _file_icon(path),
        PixmapOverlayConfig(
            size_ratio=icon_size_ratio,
            center_x_ratio=center_x_ratio,
            center_y_ratio=center_y_ratio,
            visible_start_ratio=visible_start_ratio,
            visible_end_ratio=visible_end_ratio,
            opacity=opacity,
            layer=layer,
            background_enabled=True,
        ),
    )


def _file_icon(path: Path | None) -> QPixmap:
    if path is not None:
        icon = QFileIconProvider().icon(QFileInfo(str(path)))
        pixmap = _pixmap_from_icon(icon)
        if not pixmap.isNull():
            return pixmap
    return _fallback_file_icon()


def _pixmap_from_icon(icon: QIcon) -> QPixmap:
    for size in (256, 128, 64, 32):
        pixmap = icon.pixmap(size, size)
        if not pixmap.isNull():
            return pixmap
    return QPixmap()


def _fallback_file_icon() -> QPixmap:
    pixmap = QPixmap(256, 256)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

    path = QPainterPath()
    path.moveTo(58, 28)
    path.lineTo(158, 28)
    path.lineTo(214, 84)
    path.lineTo(214, 228)
    path.lineTo(58, 228)
    path.closeSubpath()

    painter.setPen(QColor(75, 100, 130))
    painter.setBrush(QColor(245, 249, 255))
    painter.drawPath(path)
    painter.setBrush(QColor(210, 226, 245))
    painter.drawPolygon(QPolygonF([QPointF(158, 28), QPointF(214, 84), QPointF(158, 84)]))
    painter.drawLine(158, 28, 158, 84)
    painter.drawLine(158, 84, 214, 84)
    painter.setPen(QColor(92, 118, 148))
    for y in (124, 154, 184):
        painter.drawLine(88, y, 184, y)
    painter.end()
    return pixmap

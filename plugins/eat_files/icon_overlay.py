"""给吃文件叠加拖入文件的系统图标"""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QFileInfo, QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPixmap, QPolygonF
from PyQt6.QtWidgets import QFileIconProvider

from core.playback.clip import Clip


class IconOverlayClip:
    def __init__(
        self,
        base: Clip,
        icon: QPixmap,
        *,
        icon_size_ratio: float,
        center_x_ratio: float,
        center_y_ratio: float,
        visible_start_ratio: float,
        visible_end_ratio: float,
        opacity: float,
        layer: str,
    ) -> None:
        self._base = base
        self._icon = icon
        self._icon_size_ratio = max(0.01, float(icon_size_ratio))
        self._center_x_ratio = float(center_x_ratio)
        self._center_y_ratio = float(center_y_ratio)
        self._visible_start_ratio = min(1.0, max(0.0, float(visible_start_ratio)))
        self._visible_end_ratio = min(1.0, max(0.0, float(visible_end_ratio)))
        self._opacity = min(1.0, max(0.0, float(opacity)))
        self._layer = str(layer)
        self._frame_cache: dict[int, QPixmap] = {}

        self.frame_paths = base.frame_paths
        self.frame_intervals_ms = base.frame_intervals_ms
        self.action_id = base.action_id
        self.source_state = base.source_state
        self.phase = base.phase
        self.variant = base.variant

    def __len__(self) -> int:
        return len(self._base)

    @property
    def duration_ms(self) -> int:
        return self._base.duration_ms

    @property
    def interval_ms(self) -> int:
        return self._base.interval_ms

    def interval_for(self, index: int) -> int:
        return self._base.interval_for(index)

    def frame(self, index: int) -> QPixmap:
        cached = self._frame_cache.get(index)
        if cached is not None:
            return cached
        if not self._icon_visible_at(index):
            return self._base.frame(index)
        pixmap = self._compose_frame(index)
        self._frame_cache[index] = pixmap
        return pixmap

    def _icon_visible_at(self, index: int) -> bool:
        if self._visible_end_ratio <= self._visible_start_ratio:
            return False
        if len(self._base) <= 1:
            progress = 0.0
        else:
            progress = index / (len(self._base) - 1)
        return self._visible_start_ratio <= progress <= self._visible_end_ratio

    def _compose_frame(self, index: int) -> QPixmap:
        frame_layers = getattr(self._base, "frame_layers", None)
        if not frame_layers:
            pixmap = QPixmap(self._base.frame(index))
            _draw_icon(
                pixmap,
                self._icon,
                self._icon_size_ratio,
                self._center_x_ratio,
                self._center_y_ratio,
                self._opacity,
            )
            return pixmap

        layers = tuple(frame_layers[index])
        pixmaps = [QPixmap(str(path)) for _, path in layers]
        width = max(pixmap.width() for pixmap in pixmaps if not pixmap.isNull())
        height = max(pixmap.height() for pixmap in pixmaps if not pixmap.isNull())
        result = QPixmap(width, height)
        result.fill(Qt.GlobalColor.transparent)
        painter = QPainter(result)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        icon_drawn = False
        for layer, path in layers:
            if self._layer == "behind_front" and layer == "front" and not icon_drawn:
                _draw_icon_with_painter(
                    painter,
                    self._icon,
                    self._icon_size_ratio,
                    self._center_x_ratio,
                    self._center_y_ratio,
                    self._opacity,
                )
                icon_drawn = True
            pixmap = QPixmap(str(path))
            if not pixmap.isNull():
                painter.drawPixmap(0, 0, pixmap)
        if not icon_drawn:
            _draw_icon_with_painter(
                painter,
                self._icon,
                self._icon_size_ratio,
                self._center_x_ratio,
                self._center_y_ratio,
                self._opacity,
            )
        painter.end()
        return result


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
) -> IconOverlayClip:
    return IconOverlayClip(
        clip,
        _file_icon(path),
        icon_size_ratio=icon_size_ratio,
        center_x_ratio=center_x_ratio,
        center_y_ratio=center_y_ratio,
        visible_start_ratio=visible_start_ratio,
        visible_end_ratio=visible_end_ratio,
        opacity=opacity,
        layer=layer,
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


def _draw_icon(
    target: QPixmap,
    icon: QPixmap,
    icon_size_ratio: float,
    center_x_ratio: float,
    center_y_ratio: float,
    opacity: float,
) -> None:
    painter = QPainter(target)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
    _draw_icon_with_painter(
        painter,
        icon,
        icon_size_ratio,
        center_x_ratio,
        center_y_ratio,
        opacity,
    )
    painter.end()


def _draw_icon_with_painter(
    painter: QPainter,
    icon: QPixmap,
    icon_size_ratio: float,
    center_x_ratio: float,
    center_y_ratio: float,
    opacity: float,
) -> None:
    target = painter.device()
    dpr_fn = getattr(target, "devicePixelRatioF", None)
    dpr = max(1.0, float(dpr_fn())) if callable(dpr_fn) else 1.0
    width = target.width()
    height = target.height()
    logical_width = width / dpr
    logical_height = height / dpr
    size = min(
        min(logical_width, logical_height) * icon_size_ratio,
        logical_width * 0.35,
        logical_height * 0.35,
    )
    resolved_center_x = logical_width * center_x_ratio
    resolved_center_y = logical_height * center_y_ratio
    x = resolved_center_x - size / 2
    y = resolved_center_y - size / 2
    rect = QRectF(x, y, size, size)

    painter.save()
    painter.setOpacity(min(1.0, max(0.0, opacity)))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(255, 255, 255, 210))
    painter.drawRoundedRect(rect.adjusted(-8, -8, 8, 8), 18, 18)
    painter.drawPixmap(rect, icon, QRectF(icon.rect()))
    painter.restore()


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

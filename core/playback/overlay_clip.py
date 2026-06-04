"""运行时给动画帧叠加静态 PNG 图层"""

from __future__ import annotations

from dataclasses import dataclass

from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QColor, QPainter, QPixmap

from core.playback.clip import Clip


@dataclass(frozen=True, slots=True)
class PixmapOverlayConfig:
    size_ratio: float = 0.15
    center_x_ratio: float = 0.5
    center_y_ratio: float = 0.575
    visible_start_ratio: float = 0.0
    visible_end_ratio: float = 1.0
    opacity: float = 1.0
    layer: str = "behind_front"
    background_enabled: bool = False


class PixmapOverlayClip:
    def __init__(
        self,
        base: Clip,
        overlay: QPixmap,
        config: PixmapOverlayConfig,
    ) -> None:
        self._base = base
        self._overlay = overlay
        self._config = config
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
        if not self._overlay_visible_at(index):
            return self._base.frame(index)
        pixmap = self._compose_frame(index)
        self._frame_cache[index] = pixmap
        return pixmap

    def _overlay_visible_at(self, index: int) -> bool:
        start_ratio = min(1.0, max(0.0, float(self._config.visible_start_ratio)))
        end_ratio = min(1.0, max(0.0, float(self._config.visible_end_ratio)))
        if end_ratio <= start_ratio:
            return False
        if len(self._base) <= 1:
            progress = 0.0
        else:
            progress = index / (len(self._base) - 1)
        return start_ratio <= progress <= end_ratio

    def _compose_frame(self, index: int) -> QPixmap:
        frame_layers = getattr(self._base, "frame_layers", None)
        if not frame_layers:
            pixmap = QPixmap(self._base.frame(index))
            draw_pixmap_overlay(pixmap, self._overlay, self._config)
            return pixmap

        layers = tuple(frame_layers[index])
        layer_pixmaps = [
            (layer, QPixmap(str(path)))
            for layer, path in layers
        ]
        visible_pixmaps = [pixmap for _, pixmap in layer_pixmaps if not pixmap.isNull()]
        if not visible_pixmaps:
            return self._base.frame(index)

        result = QPixmap(
            max(pixmap.width() for pixmap in visible_pixmaps),
            max(pixmap.height() for pixmap in visible_pixmaps),
        )
        result.fill(Qt.GlobalColor.transparent)
        painter = QPainter(result)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

        overlay_drawn = False
        for layer, pixmap in layer_pixmaps:
            if self._config.layer == "behind_front" and layer == "front" and not overlay_drawn:
                draw_pixmap_overlay_with_painter(painter, self._overlay, self._config)
                overlay_drawn = True
            if not pixmap.isNull():
                painter.drawPixmap(0, 0, pixmap)
        if not overlay_drawn:
            draw_pixmap_overlay_with_painter(painter, self._overlay, self._config)
        painter.end()
        return result


def clip_with_pixmap_overlay(
    clip: Clip,
    overlay: QPixmap,
    config: PixmapOverlayConfig,
) -> Clip | PixmapOverlayClip:
    if overlay.isNull():
        return clip
    return PixmapOverlayClip(clip, overlay, config)


def draw_pixmap_overlay(
    target: QPixmap,
    overlay: QPixmap,
    config: PixmapOverlayConfig,
) -> None:
    painter = QPainter(target)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
    draw_pixmap_overlay_with_painter(painter, overlay, config)
    painter.end()


def draw_pixmap_overlay_with_painter(
    painter: QPainter,
    overlay: QPixmap,
    config: PixmapOverlayConfig,
) -> None:
    target = painter.device()
    dpr_fn = getattr(target, "devicePixelRatioF", None)
    dpr = max(1.0, float(dpr_fn())) if callable(dpr_fn) else 1.0
    width = target.width()
    height = target.height()
    logical_width = width / dpr
    logical_height = height / dpr
    size = min(
        min(logical_width, logical_height) * max(0.01, float(config.size_ratio)),
        logical_width * 0.35,
        logical_height * 0.35,
    )
    resolved_center_x = logical_width * float(config.center_x_ratio)
    resolved_center_y = logical_height * float(config.center_y_ratio)
    rect = QRectF(
        resolved_center_x - size / 2,
        resolved_center_y - size / 2,
        size,
        size,
    )

    painter.save()
    painter.setOpacity(min(1.0, max(0.0, float(config.opacity))))
    if config.background_enabled:
        padding = max(4.0, size * 0.12)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(255, 255, 255, 210))
        painter.drawRoundedRect(
            rect.adjusted(-padding, -padding, padding, padding),
            max(8.0, size * 0.22),
            max(8.0, size * 0.22),
        )
    painter.drawPixmap(rect, overlay, QRectF(overlay.rect()))
    painter.restore()


__all__ = [
    "PixmapOverlayClip",
    "PixmapOverlayConfig",
    "clip_with_pixmap_overlay",
    "draw_pixmap_overlay",
    "draw_pixmap_overlay_with_painter",
]

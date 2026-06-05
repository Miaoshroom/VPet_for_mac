"""聊天头像渲染工具"""

from __future__ import annotations

import math
from collections import OrderedDict
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont, QImage, QImageReader, QPainter, QPainterPath, QPixmap
from PyQt6.QtWidgets import QLabel, QWidget

_CACHE_LIMIT = 64
_AVATAR_CACHE: OrderedDict[tuple[str, int, int], QPixmap] = OrderedDict()


class AvatarLabel(QLabel):
    def __init__(
        self,
        object_name: str,
        path: Path | None,
        logical_size: int,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__("", parent)
        self._avatar_path = path
        self._logical_size = max(1, int(logical_size))
        self._fallback_id = object_name
        self.setObjectName(object_name)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setFixedSize(self._logical_size, self._logical_size)
        self.setScaledContents(False)
        self.refresh_avatar()

    def refresh_avatar(self) -> None:
        self.setPixmap(
            render_avatar_pixmap(
                self._avatar_path,
                self._logical_size,
                device_pixel_ratio=avatar_device_pixel_ratio(self),
                fallback_id=self._fallback_id,
            )
        )

    def showEvent(self, event) -> None:
        self.refresh_avatar()
        super().showEvent(event)


def avatar_device_pixel_ratio(widget: QWidget | None) -> float:
    if widget is None:
        return 1.0
    try:
        ratio = float(widget.devicePixelRatioF())
    except (RuntimeError, TypeError, ValueError):
        return 1.0
    if not math.isfinite(ratio):
        return 1.0
    return max(1.0, ratio)


def render_avatar_pixmap(
    path: Path | None,
    logical_size: int,
    *,
    device_pixel_ratio: float = 1.0,
    fallback_id: str = "avatar",
) -> QPixmap:
    logical_size = max(1, int(logical_size))
    dpr = _normalized_dpr(device_pixel_ratio)
    cache_key = (_source_key(path, fallback_id), logical_size, round(dpr * 100))
    cached = _AVATAR_CACHE.get(cache_key)
    if cached is not None:
        _AVATAR_CACHE.move_to_end(cache_key)
        return cached

    physical_size = _physical_size(logical_size, dpr)
    image = _load_source_image(path)
    if image is None or min(image.width(), image.height()) < physical_size:
        pixmap = _fallback_avatar(logical_size, dpr, physical_size, fallback_id)
    else:
        pixmap = _round_avatar(_center_crop_scaled(image, physical_size), dpr)

    _remember(cache_key, pixmap)
    return pixmap


def clear_avatar_cache() -> None:
    _AVATAR_CACHE.clear()


def _normalized_dpr(value: float) -> float:
    try:
        ratio = float(value)
    except (TypeError, ValueError):
        return 1.0
    if not math.isfinite(ratio):
        return 1.0
    return max(1.0, ratio)


def _physical_size(logical_size: int, dpr: float) -> int:
    return max(1, int(round(logical_size * dpr)))


def _source_key(path: Path | None, fallback_id: str) -> str:
    if path is None:
        return f"fallback:{fallback_id}"
    try:
        resolved = path.expanduser().resolve()
        stat = resolved.stat()
    except OSError:
        return f"missing:{path}:{fallback_id}"
    return f"file:{resolved}:{stat.st_size}:{stat.st_mtime_ns}:{fallback_id}"


def _load_source_image(path: Path | None) -> QImage | None:
    if path is None:
        return None
    try:
        if not path.exists():
            return None
        reader = QImageReader(str(path))
        reader.setAutoTransform(True)
        image = reader.read()
    except RuntimeError:
        return None
    if image.isNull():
        return None
    return image


def _center_crop_scaled(source: QImage, physical_size: int) -> QImage:
    side = min(source.width(), source.height())
    x = max(0, (source.width() - side) // 2)
    y = max(0, (source.height() - side) // 2)
    return source.copy(x, y, side, side).scaled(
        physical_size,
        physical_size,
        Qt.AspectRatioMode.IgnoreAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )


def _round_avatar(source: QImage, dpr: float) -> QPixmap:
    size = source.width()
    canvas = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    canvas.fill(Qt.GlobalColor.transparent)

    painter = QPainter(canvas)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    clip = QPainterPath()
    clip.addEllipse(0, 0, size, size)
    painter.setClipPath(clip)
    painter.drawImage(0, 0, source)
    painter.end()

    pixmap = QPixmap.fromImage(canvas)
    pixmap.setDevicePixelRatio(dpr)
    return pixmap


def _fallback_avatar(
    logical_size: int,
    dpr: float,
    physical_size: int,
    fallback_id: str,
) -> QPixmap:
    canvas = QImage(
        physical_size,
        physical_size,
        QImage.Format.Format_ARGB32_Premultiplied,
    )
    canvas.fill(Qt.GlobalColor.transparent)

    bg, edge, text = _fallback_colors(fallback_id)
    painter = QPainter(canvas)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setBrush(bg)
    painter.setPen(edge)
    inset = max(1, round(physical_size * 0.04))
    diameter = max(1, physical_size - inset * 2)
    painter.drawEllipse(inset, inset, diameter, diameter)

    font = QFont()
    font.setBold(True)
    font.setPixelSize(max(10, round(physical_size * 0.44)))
    painter.setFont(font)
    painter.setPen(text)
    painter.drawText(canvas.rect(), Qt.AlignmentFlag.AlignCenter, _fallback_text(fallback_id))
    painter.end()

    pixmap = QPixmap.fromImage(canvas)
    pixmap.setDevicePixelRatio(dpr)
    return pixmap


def _fallback_colors(fallback_id: str) -> tuple[QColor, QColor, QColor]:
    if "pet" in fallback_id.lower() or "lolith" in fallback_id.lower():
        return QColor(92, 84, 135), QColor(166, 157, 218), QColor(248, 247, 255)
    return QColor(54, 101, 135), QColor(134, 184, 220), QColor(246, 251, 255)


def _fallback_text(fallback_id: str) -> str:
    lower = fallback_id.lower()
    if "pet" in lower or "lolith" in lower:
        return "L"
    if "user" in lower:
        return "U"
    return "?"


def _remember(key: tuple[str, int, int], pixmap: QPixmap) -> None:
    _AVATAR_CACHE[key] = pixmap
    _AVATAR_CACHE.move_to_end(key)
    while len(_AVATAR_CACHE) > _CACHE_LIMIT:
        _AVATAR_CACHE.popitem(last=False)


__all__ = [
    "AvatarLabel",
    "avatar_device_pixel_ratio",
    "clear_avatar_cache",
    "render_avatar_pixmap",
]

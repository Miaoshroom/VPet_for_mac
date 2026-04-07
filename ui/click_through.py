"""切换穿透模式"""

from __future__ import annotations

from collections.abc import Callable

from PyQt6.QtCore import QPoint, Qt
from PyQt6.QtGui import QColor, QMouseEvent, QPaintEvent, QPainter, QPen
from PyQt6.QtWidgets import QWidget

BADGE_SIZE = 26
DRAG_THRESHOLD = 4
BADGE_MARGIN = 15


class ClickThroughBadge(QWidget):
    def __init__(
        self,
        *,
        target_window: QWidget,
        is_enabled: Callable[[], bool],
        set_enabled: Callable[[bool], None],
        initial_pos: QPoint | None = None,
    ) -> None:
        super().__init__(None)
        self._target_window = target_window
        self._is_enabled = is_enabled
        self._set_enabled = set_enabled
        self._drag_offset: QPoint | None = None
        self._press_global: QPoint | None = None
        self._dragged = False

        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFixedSize(BADGE_SIZE, BADGE_SIZE)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("点击切换穿透，拖动可移动位置")
        self.move(initial_pos or self._default_pos())
        target_window.destroyed.connect(self.close)

    def _default_pos(self) -> QPoint:
        geometry = self._target_window.geometry()
        return QPoint(
            geometry.x() + geometry.width() - BADGE_SIZE - BADGE_MARGIN,
            geometry.y() + geometry.height() - BADGE_SIZE - BADGE_MARGIN,
        )

    def _toggle(self) -> None:
        self._set_enabled(not self._is_enabled())
        self.raise_()
        self.update()

    def mousePressEvent(self, e: QMouseEvent) -> None:
        if e.button() == Qt.MouseButton.LeftButton:
            self._drag_offset = e.position().toPoint()
            self._press_global = e.globalPosition().toPoint()
            self._dragged = False
            e.accept()
            return
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e: QMouseEvent) -> None:
        if (
            e.buttons() & Qt.MouseButton.LeftButton
            and self._drag_offset is not None
        ):
            current_global = e.globalPosition().toPoint()
            if self._press_global is not None:
                self._dragged = (
                    current_global - self._press_global
                ).manhattanLength() > DRAG_THRESHOLD
            self.move(current_global - self._drag_offset)
            e.accept()
            return
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e: QMouseEvent) -> None:
        if e.button() == Qt.MouseButton.LeftButton:
            dragged = self._dragged
            self._drag_offset = None
            self._press_global = None
            self._dragged = False
            if not dragged:
                self._toggle()
            e.accept()
            return
        super().mouseReleaseEvent(e)

    def paintEvent(self, event: QPaintEvent) -> None:
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        outer = self.rect().adjusted(2, 2, -2, -2)
        fill = QColor("#76C9FF") if self._is_enabled() else QColor("#AEE6FF")
        border = QColor("#2F8FCE")
        highlight = QColor(255, 255, 255, 150)

        painter.setPen(QPen(border, 1.4))
        painter.setBrush(fill)
        painter.drawEllipse(outer)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(highlight)
        painter.drawEllipse(outer.adjusted(4, 4, -10, -10))

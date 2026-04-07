"""桌宠显示层：负责图片显示与开发模式叠层"""

from __future__ import annotations

from PyQt6.QtCore import QRect, Qt
from PyQt6.QtGui import QColor, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import QLabel

from core.interaction_map import InteractionMap


class PetDisplay(QLabel):
    def __init__(self, interaction_map: InteractionMap, dev_mode: bool) -> None:
        super().__init__()
        self._interaction_map = interaction_map
        self._dev_mode = dev_mode
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setScaledContents(False)
        if self._dev_mode:
            self.setStyleSheet("background: rgba(173, 216, 230, 0.18);")
        else:
            self.setStyleSheet("background: transparent;")

    def set_pet_pixmap(self, pixmap: QPixmap) -> None:
        self.setPixmap(pixmap)

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        if not self._dev_mode:
            return

        width = max(1, self.width())
        height = max(1, self.height())
        cell_w = width / self._interaction_map.cols
        cell_h = height / self._interaction_map.rows

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        painter.setPen(QPen(QColor(40, 120, 180, 180), 1))

        for row in range(1, self._interaction_map.rows):
            y = round(row * cell_h)
            painter.drawLine(0, y, width, y)
        for col in range(1, self._interaction_map.cols):
            x = round(col * cell_w)
            painter.drawLine(x, 0, x, height)

        for row in range(self._interaction_map.rows):
            for col in range(self._interaction_map.cols):
                rect = QRect(
                    round(col * cell_w),
                    round(row * cell_h),
                    round((col + 1) * cell_w) - round(col * cell_w),
                    round((row + 1) * cell_h) - round(row * cell_h),
                )
                self._draw_cell_debug(painter, rect, row, col)

    def _draw_cell_debug(self, painter: QPainter, rect: QRect, row: int, col: int) -> None:
        press = self._interaction_map.resolve_cell("press", row, col)
        drag = self._interaction_map.resolve_cell("drag", row, col)
        lines = [f"{row + 1},{col + 1}"]

        if press.type == "press_mode" and press.mode is not None:
            lines.append(f"P:{press.mode}")
        elif press.type != "none":
            lines.append(f"P:{press.type}")

        if drag.type == "move_window":
            lines.append("D:move")
        elif drag.type != "none":
            lines.append(f"D:{drag.type}")

        painter.setPen(QColor(20, 60, 100, 220))
        painter.drawText(
            rect.adjusted(3, 2, -3, -2),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop,
            "\n".join(lines),
        )

"""番茄钟悬浮计时窗口。"""

from __future__ import annotations

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import QLabel, QVBoxLayout, QWidget

FOLLOW_INTERVAL_MS = 250
WINDOW_OVERLAP_PX = 28


class TomatoClockWindow(QWidget):
    def __init__(self, target_window: QWidget) -> None:
        super().__init__(None)
        self._target_window = target_window
        self._follow_timer = QTimer(self)
        self._follow_timer.timeout.connect(self.update_position)

        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.WindowDoesNotAcceptFocus
            | Qt.WindowType.WindowTransparentForInput
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        self._action_label = QLabel("番茄钟")
        self._time_label = QLabel("00:00")
        self._count_label = QLabel("自律 0 次")
        self._action_label.setObjectName("actionLabel")
        self._time_label.setObjectName("timeLabel")
        self._count_label.setObjectName("countLabel")

        self._action_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._time_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._count_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 9, 14, 9)
        layout.setSpacing(2)
        layout.addWidget(self._action_label)
        layout.addWidget(self._time_label)
        layout.addWidget(self._count_label)

        self.setStyleSheet(
            """
            QWidget {
                background: rgba(34, 43, 52, 205);
                border-radius: 12px;
            }
            QLabel {
                color: #F4FAFF;
                background: transparent;
                font-family: 'PingFang SC';
            }
            QLabel#actionLabel {
                font-size: 12px;
                font-weight: 600;
            }
            QLabel#timeLabel {
                font-size: 24px;
                font-weight: 700;
            }
            QLabel#countLabel {
                font-size: 11px;
                color: #C8D6E5;
            }
            """
        )
        self.setMinimumWidth(136)
        target_window.destroyed.connect(self.close)

    def show_timer(
        self,
        *,
        action_title: str,
        phase_title: str,
        remaining_seconds: int,
        count: int,
    ) -> None:
        self.update_timer(
            action_title=action_title,
            phase_title=phase_title,
            remaining_seconds=remaining_seconds,
            count=count,
        )
        self.show()
        self.update_position()
        self.raise_()
        if not self._follow_timer.isActive():
            self._follow_timer.start(FOLLOW_INTERVAL_MS)

    def update_timer(
        self,
        *,
        action_title: str,
        phase_title: str,
        remaining_seconds: int,
        count: int,
    ) -> None:
        self._action_label.setText(f"{phase_title} · {action_title}")
        self._time_label.setText(_format_seconds(remaining_seconds))
        self._count_label.setText(f"自律 {count} 次")
        self.adjustSize()
        if self.isVisible():
            self.update_position()

    def hide_timer(self) -> None:
        self._follow_timer.stop()
        self.hide()

    def update_position(self) -> None:
        geometry = self._target_window.geometry()
        x = geometry.x() + (geometry.width() - self.width()) // 2
        y = geometry.y() + geometry.height() - self.height() - WINDOW_OVERLAP_PX
        self.move(x, y)
        self.raise_()


def _format_seconds(seconds: int) -> str:
    value = max(0, int(seconds))
    minutes, seconds = divmod(value, 60)
    return f"{minutes:02d}:{seconds:02d}"

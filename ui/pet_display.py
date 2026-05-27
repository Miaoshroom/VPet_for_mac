"""桌宠显示层：负责图片显示与开发模式叠层"""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QRect, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import QButtonGroup, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from core.interaction_map import InteractionMap
from core.playback.director import PlaybackDebugSnapshot


SOURCE_LABELS = {
    "mode": "常驻",
    "interaction": "互动",
    "single": "单次",
}


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


class DevModePanel(QWidget):
    pet_state_requested = pyqtSignal(str)
    replay_requested = pyqtSignal()

    def __init__(self, pet_states: tuple[str, ...]) -> None:
        super().__init__()
        self._state_buttons: dict[str, QPushButton] = {}

        self._summary_label = QLabel("播放: -")
        self._summary_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self._detail_label = QLabel("素材: -")
        self._detail_label.setWordWrap(True)
        self._detail_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )

        self._state_button_group = QButtonGroup(self)
        self._state_button_group.setExclusive(True)

        button_row = QHBoxLayout()
        button_row.setContentsMargins(0, 0, 0, 0)
        button_row.setSpacing(6)
        for state in pet_states:
            button = QPushButton(state)
            button.setCheckable(True)
            button.setMinimumHeight(26)
            button.clicked.connect(
                lambda checked=False, state=state: self.pet_state_requested.emit(state)
            )
            self._state_button_group.addButton(button)
            button_row.addWidget(button)
            self._state_buttons[state] = button
        button_row.addStretch(1)

        replay_button = QPushButton("重播")
        replay_button.setMinimumHeight(26)
        replay_button.clicked.connect(self.replay_requested.emit)
        button_row.addWidget(replay_button)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 5, 8, 6)
        layout.setSpacing(3)
        layout.addWidget(self._summary_label)
        layout.addWidget(self._detail_label)
        layout.addLayout(button_row)

        self.setStyleSheet(
            """
            DevModePanel {
                background: rgba(245, 250, 255, 0.94);
                border-top: 1px solid rgba(40, 120, 180, 0.35);
            }
            DevModePanel QLabel {
                color: #17324d;
                font-size: 11px;
            }
            DevModePanel QPushButton {
                color: #17324d;
                background: rgba(255, 255, 255, 0.9);
                border: 1px solid rgba(40, 120, 180, 0.32);
                border-radius: 4px;
                padding: 2px 8px;
            }
            DevModePanel QPushButton:checked {
                color: white;
                background: #2878b4;
                border-color: #2878b4;
            }
            """
        )

    def set_snapshot(self, snapshot: PlaybackDebugSnapshot | None) -> None:
        if snapshot is None:
            self._summary_label.setText("播放: -")
            self._detail_label.setText("素材: -")
            self._detail_label.setToolTip("")
            return

        source = SOURCE_LABELS.get(snapshot.source, snapshot.source)
        action = self._format_action(snapshot)
        frame = self._format_frame(snapshot)
        variant = snapshot.variant or "-"
        pending = f" | 待切换 {snapshot.pending_mode}" if snapshot.pending_mode else ""
        self._summary_label.setText(
            f"播放: {source} | {action} | {snapshot.phase} | 帧 {frame} | variant {variant}{pending}"
        )

        state_text = snapshot.pet_state
        fallback = ""
        if snapshot.source_state and snapshot.source_state != snapshot.pet_state:
            state_text = f"{snapshot.pet_state} -> {snapshot.source_state}"
            fallback = " | fallback"
        path = _short_path(snapshot.frame_path)
        self._detail_label.setText(f"状态: {state_text}{fallback} | 当前帧: {path}")
        self._detail_label.setToolTip(str(snapshot.frame_path or ""))

        for state, button in self._state_buttons.items():
            button.setChecked(state == snapshot.pet_state)

    def set_error(self, message: str) -> None:
        self._detail_label.setText(f"状态切换失败: {message}")

    def set_notice(self, message: str) -> None:
        self._detail_label.setText(message)

    def _format_action(self, snapshot: PlaybackDebugSnapshot) -> str:
        action_id = snapshot.action_id or "-"
        title = snapshot.action_title or action_id
        if title == action_id:
            return action_id
        return f"{title} ({action_id})"

    def _format_frame(self, snapshot: PlaybackDebugSnapshot) -> str:
        if snapshot.frame_index is None or snapshot.frame_count is None:
            return "-/-"
        return f"{snapshot.frame_index + 1}/{snapshot.frame_count}"


def _short_path(path: Path | None) -> str:
    if path is None:
        return "-"
    parts = path.parts
    if len(parts) <= 6:
        return str(path)
    return "/".join(parts[-6:])

"""聊天加号二级菜单"""

from __future__ import annotations

from dataclasses import dataclass

from PyQt6.QtCore import QPoint, Qt, pyqtSignal
from PyQt6.QtWidgets import QFrame, QToolButton, QVBoxLayout, QWidget


@dataclass(frozen=True, slots=True)
class PlusMenuAction:
    id: str
    label: str
    tooltip: str


class PlusMenu(QFrame):
    sticker_requested = pyqtSignal()
    memory_requested = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(
            parent,
            Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint,
        )
        self.setObjectName("chatPlusMenu")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)
        for action in _ACTIONS:
            button = QToolButton()
            button.setObjectName(f"chatPlusMenuButton_{action.id}")
            button.setText(action.label)
            button.setToolTip(action.tooltip)
            button.setFixedSize(112, 36)
            button.clicked.connect(
                lambda checked=False, action_id=action.id: self._choose(action_id)
            )
            layout.addWidget(button)

    def show_near(self, widget: QWidget) -> None:
        point = widget.mapToGlobal(QPoint(0, -self.sizeHint().height() - 6))
        self.move(point)
        self.show()

    def _choose(self, action_id: str) -> None:
        self.hide()
        if action_id == "stickers":
            self.sticker_requested.emit()
        elif action_id == "memory":
            self.memory_requested.emit()


_ACTIONS = (
    PlusMenuAction("stickers", "表情包", "打开表情包"),
    PlusMenuAction("memory", "记忆", "人工查看和编辑长期记忆"),
)


__all__ = ["PlusMenu", "PlusMenuAction"]

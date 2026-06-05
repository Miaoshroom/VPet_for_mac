"""聊天输入栏"""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtWidgets import QHBoxLayout, QPushButton, QTextEdit, QWidget


class ChatTextEdit(QTextEdit):
    send_requested = pyqtSignal()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        key = event.key()
        shift = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and not shift:
            self.send_requested.emit()
            return
        super().keyPressEvent(event)


class InputBar(QWidget):
    send_requested = pyqtSignal(str)
    plus_clicked = pyqtSignal()
    close_clicked = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("chatInputBar")
        self.setFixedHeight(62)
        self._busy = False

        self._close_button = QPushButton("×")
        self._close_button.setObjectName("chatCloseButton")
        self._close_button.setToolTip("关闭")
        self._close_button.setFixedSize(36, 36)
        self._close_button.clicked.connect(self.close_clicked.emit)

        self._plus_button = QPushButton("+")
        self._plus_button.setObjectName("chatPlusButton")
        self._plus_button.setToolTip("更多")
        self._plus_button.setFixedSize(36, 36)
        self._plus_button.clicked.connect(self.plus_clicked.emit)

        self._editor = ChatTextEdit()
        self._editor.setObjectName("chatInputEdit")
        self._editor.setPlaceholderText("和萝莉斯说点什么")
        self._editor.setFixedHeight(40)
        self._editor.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._editor.send_requested.connect(self.submit)

        self._send_button = QPushButton("➤")
        self._send_button.setObjectName("chatSendButton")
        self._send_button.setToolTip("发送")
        self._send_button.setFixedSize(40, 36)
        self._send_button.clicked.connect(self.submit)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 10)
        layout.setSpacing(8)
        layout.addWidget(self._close_button)
        layout.addWidget(self._plus_button)
        layout.addWidget(self._editor, 1)
        layout.addWidget(self._send_button)

    def set_busy(self, busy: bool) -> None:
        self._busy = bool(busy)
        self._send_button.setEnabled(not self._busy)
        self._plus_button.setEnabled(not self._busy)

    def set_text(self, text: str) -> None:
        self._editor.setPlainText(text)

    def text(self) -> str:
        return self._editor.toPlainText()

    def submit(self) -> None:
        if self._busy:
            return
        text = self.text().strip()
        if not text:
            return
        self._editor.clear()
        self.send_requested.emit(text)


__all__ = ["InputBar"]

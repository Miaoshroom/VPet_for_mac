"""人工长期记忆编辑面板"""

from __future__ import annotations

import json

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from core.chat.config import ChatConfig, load_chat_config
from core.chat.memory_store import MemoryStore


class MemoryEditorDialog(QDialog):
    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        config: ChatConfig | None = None,
        memory_store: MemoryStore | None = None,
    ) -> None:
        super().__init__(parent)
        self.config = config or load_chat_config()
        self.memory_store = memory_store or MemoryStore(self.config.storage)
        self.setObjectName("memoryEditorDialog")
        self.setWindowTitle("长期记忆")
        self.setModal(False)
        self.resize(520, 560)

        self._title = QLabel("长期记忆")
        self._title.setObjectName("memoryEditorTitle")

        self._notice = QLabel("仅人工编辑；AI 只能读取裁剪摘要，不能保存或删除记忆。")
        self._notice.setObjectName("memoryEditorNotice")
        self._notice.setWordWrap(True)

        self._editor = QTextEdit()
        self._editor.setObjectName("memoryEditorText")
        self._editor.setAcceptRichText(False)
        self._editor.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)

        self._status = QLabel("")
        self._status.setObjectName("memoryEditorStatus")

        self._reload_button = QPushButton("重新载入")
        self._reload_button.setObjectName("memoryEditorReloadButton")
        self._reload_button.clicked.connect(self.load_memory)

        self._save_button = QPushButton("保存")
        self._save_button.setObjectName("memoryEditorSaveButton")
        self._save_button.clicked.connect(self.save_memory)

        self._close_button = QPushButton("关闭")
        self._close_button.setObjectName("memoryEditorCloseButton")
        self._close_button.clicked.connect(self.hide)

        buttons = QHBoxLayout()
        buttons.addWidget(self._status, 1)
        buttons.addWidget(self._reload_button)
        buttons.addWidget(self._save_button)
        buttons.addWidget(self._close_button)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)
        layout.addWidget(self._title)
        layout.addWidget(self._notice)
        layout.addWidget(self._editor, 1)
        layout.addLayout(buttons)
        self.setStyleSheet(_STYLE)
        self.load_memory()

    def show_editor(self) -> None:
        self.load_memory()
        self.show()
        self.raise_()
        self.activateWindow()

    def load_memory(self) -> None:
        payload = self.memory_store.load_full()
        self._editor.setPlainText(
            json.dumps(payload, ensure_ascii=False, indent=2)
        )
        self._status.setText("")

    def save_memory(self) -> None:
        try:
            payload = json.loads(self._editor.toPlainText())
            if not isinstance(payload, dict):
                raise ValueError("root_must_be_json_object")
            backup_path = self.memory_store.save_full(payload, actor="user")
        except (OSError, ValueError) as exc:
            self._status.setText("保存失败")
            QMessageBox.warning(self, "保存失败", str(exc))
            return
        self.load_memory()
        self._status.setText(f"已保存，备份：{backup_path.name}")

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.hide()
            return
        super().keyPressEvent(event)


_STYLE = """
QDialog#memoryEditorDialog {
    background: rgba(32, 34, 38, 248);
    color: rgb(242, 244, 247);
}
QLabel#memoryEditorTitle {
    font-size: 16px;
    font-weight: 700;
}
QLabel#memoryEditorNotice,
QLabel#memoryEditorStatus {
    color: rgba(242, 244, 247, 180);
    font-size: 12px;
}
QTextEdit#memoryEditorText {
    background: rgba(24, 26, 30, 242);
    color: rgb(242, 244, 247);
    border: 1px solid rgba(88, 94, 108, 90);
    border-radius: 8px;
    padding: 8px;
    font-family: Menlo, Monaco, Consolas, monospace;
    font-size: 12px;
}
QPushButton {
    background: rgba(42, 45, 52, 232);
    color: rgb(242, 244, 247);
    border: 1px solid rgba(88, 94, 108, 90);
    border-radius: 8px;
    padding: 7px 12px;
}
QPushButton:hover {
    background: rgba(56, 61, 72, 242);
}
"""


__all__ = ["MemoryEditorDialog"]

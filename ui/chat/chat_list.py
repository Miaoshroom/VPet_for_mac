"""聊天消息列表"""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QTimer, Qt, pyqtSignal
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QScrollArea, QVBoxLayout, QWidget

from core.chat.models import ChatMessage, ChatMessageType, ChatSender
from ui.chat.avatar import AvatarLabel
from ui.chat.chat_bubble import ChatBubble
from ui.chat.sticker_resolver import StickerPathResolver

CHAT_AVATAR_SIZE = 28


class ChatList(QScrollArea):
    load_older_requested = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("chatList")
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.viewport().setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.viewport().setAutoFillBackground(False)
        self._content = QWidget()
        self._content.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self._content.setAutoFillBackground(False)
        self._layout = QVBoxLayout(self._content)
        self._layout.setContentsMargins(10, 6, 10, 12)
        self._layout.setSpacing(10)
        self._layout.addStretch(1)
        self.setWidget(self._content)
        self._typing_row: QWidget | None = None
        self._message_rows: dict[str, QWidget] = {}
        self._sticker_resolver: StickerPathResolver | None = None
        self._avatar_paths: dict[ChatSender, Path] = {}
        self.verticalScrollBar().valueChanged.connect(self._on_scroll_changed)

    def set_stickers(
        self,
        resolver: StickerPathResolver | None = None,
    ) -> None:
        self._sticker_resolver = resolver

    def set_avatar_paths(self, paths: dict[ChatSender, Path]) -> None:
        self._avatar_paths = dict(paths)

    def set_messages(self, messages: list[ChatMessage]) -> None:
        self.clear()
        for message in messages:
            self.add_message(message, scroll=False)
        self.scroll_to_bottom()

    def prepend_messages(self, messages: list[ChatMessage]) -> int:
        new_messages = [
            message for message in messages if message.id not in self._message_rows
        ]
        if not new_messages:
            return 0
        bar = self.verticalScrollBar()
        previous_maximum = bar.maximum()
        previous_value = bar.value()
        new_rows: dict[str, QWidget] = {}
        for index, message in enumerate(new_messages):
            row = self._message_row(message)
            new_rows[message.id] = row
            self._layout.insertWidget(index, row)
        self._message_rows = {**new_rows, **self._message_rows}
        QTimer.singleShot(
            0,
            lambda: self._restore_prepend_scroll(previous_value, previous_maximum),
        )
        return len(new_messages)

    def add_message(self, message: ChatMessage, *, scroll: bool = True) -> None:
        if message.id in self._message_rows:
            return
        row = self._message_row(message)
        self._message_rows[message.id] = row
        self._layout.insertWidget(max(0, self._layout.count() - 1), row)
        if scroll:
            self.scroll_to_bottom()

    def add_typing(self) -> None:
        if self._typing_row is not None:
            return
        self._typing_row = self._typing_message_row()
        self._layout.insertWidget(max(0, self._layout.count() - 1), self._typing_row)
        self.scroll_to_bottom()

    def remove_typing(self) -> None:
        if self._typing_row is None:
            return
        row = self._typing_row
        self._typing_row = None
        self._layout.removeWidget(row)
        row.setParent(None)
        row.deleteLater()

    def has_typing(self) -> bool:
        return self._typing_row is not None

    def message_ids(self) -> list[str]:
        return list(self._message_rows)

    def clear(self) -> None:
        self._typing_row = None
        self._message_rows.clear()
        while self._layout.count():
            item = self._layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
        self._layout.addStretch(1)

    def scroll_to_bottom(self) -> None:
        QTimer.singleShot(0, self._scroll_to_bottom_now)

    def _scroll_to_bottom_now(self) -> None:
        bar = self.verticalScrollBar()
        bar.setValue(bar.maximum())

    def _restore_prepend_scroll(
        self,
        previous_value: int,
        previous_maximum: int,
        attempts: int = 0,
    ) -> None:
        bar = self.verticalScrollBar()
        added_range = bar.maximum() - previous_maximum
        if added_range <= 0 and attempts < 3:
            QTimer.singleShot(
                0,
                lambda: self._restore_prepend_scroll(
                    previous_value,
                    previous_maximum,
                    attempts + 1,
                ),
            )
            return
        bar.setValue(previous_value + max(0, added_range))

    def _message_row(self, message: ChatMessage) -> QWidget:
        row = QWidget()
        row.setObjectName("chatMessageRow")
        row.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        row.setAutoFillBackground(False)
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(7)
        bubble = ChatBubble(
            message,
            sticker_resolver=self._sticker_resolver,
        )
        if message.type == ChatMessageType.SYSTEM_NOTICE:
            layout.addStretch(1)
            layout.addWidget(bubble)
            layout.addStretch(1)
        elif message.sender == ChatSender.USER:
            layout.addStretch(1)
            layout.addWidget(_message_stack(message, bubble))
            layout.addWidget(
                _avatar(
                    "chatAvatarUser",
                    self._avatar_paths.get(ChatSender.USER),
                )
            )
        else:
            layout.addWidget(
                _avatar(
                    "chatAvatarPet",
                    self._avatar_paths.get(ChatSender.LOLITH),
                )
            )
            layout.addWidget(_message_stack(message, bubble))
            layout.addStretch(1)
        return row

    def _typing_message_row(self) -> QWidget:
        row = QWidget()
        row.setObjectName("chatTypingRow")
        row.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        row.setAutoFillBackground(False)
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(7)
        layout.addWidget(_avatar("chatAvatarPet", self._avatar_paths.get(ChatSender.LOLITH)))
        layout.addWidget(_typing_stack(ChatBubble(typing=True)))
        layout.addStretch(1)
        return row

    def _on_scroll_changed(self, value: int) -> None:
        if value == self.verticalScrollBar().minimum() and self._message_rows:
            self.load_older_requested.emit()


def _message_stack(message: ChatMessage, bubble: ChatBubble) -> QWidget:
    stack = QWidget()
    is_user = message.sender == ChatSender.USER
    stack.setObjectName("chatMessageStackUser" if is_user else "chatMessageStackPet")
    stack.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
    stack.setAutoFillBackground(False)
    stack.setMaximumWidth(250)
    layout = QVBoxLayout(stack)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(0)
    layout.addWidget(
        bubble,
        0,
        Qt.AlignmentFlag.AlignRight if is_user else Qt.AlignmentFlag.AlignLeft,
    )
    return stack


def _typing_stack(bubble: ChatBubble) -> QWidget:
    stack = QWidget()
    stack.setObjectName("chatMessageStackPet")
    stack.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
    stack.setAutoFillBackground(False)
    stack.setMaximumWidth(250)
    layout = QVBoxLayout(stack)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(0)
    layout.addWidget(bubble, 0, Qt.AlignmentFlag.AlignLeft)
    return stack


def _avatar(object_name: str, path: Path | None) -> AvatarLabel:
    return AvatarLabel(object_name, path, CHAT_AVATAR_SIZE)


__all__ = ["ChatList"]

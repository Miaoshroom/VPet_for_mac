"""无边框聊天窗口"""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QEvent, Qt, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QApplication, QVBoxLayout, QWidget

from core.chat.config import ChatConfig, load_chat_config
from core.chat.models import ChatMessage, ChatSender
from ui.chat.chat_list import ChatList
from ui.chat.input_bar import InputBar
from ui.chat.sticker_resolver import StickerPathResolver


class ChatWindow(QWidget):
    send_requested = pyqtSignal(str)
    plus_requested = pyqtSignal()
    load_older_requested = pyqtSignal()

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        config: ChatConfig | None = None,
    ) -> None:
        super().__init__(
            parent,
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.NoDropShadowWindowHint,
        )
        self.config = config or load_chat_config()
        self.setObjectName("chatWindow")
        self.setWindowTitle("萝莉斯聊天")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAutoFillBackground(False)
        self.resize(324, 648)
        self.setFixedSize(324, 648)
        self._applying_style = False
        self._closed_by_outside = False
        self._registered_popups: list[QWidget] = []

        self.chat_list = ChatList()
        self.sticker_resolver = StickerPathResolver(self.config)
        self.user_stickers = self.sticker_resolver.user_stickers()
        self.chat_list.set_stickers(self.sticker_resolver)
        self.chat_list.set_avatar_paths(_avatar_assets(self.config))
        self.chat_list.load_older_requested.connect(self.load_older_requested.emit)

        self.input_bar = InputBar()
        self.input_bar.send_requested.connect(self.send_requested.emit)
        self.input_bar.plus_clicked.connect(self.plus_requested.emit)
        self.input_bar.close_clicked.connect(self.hide)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(8)
        root.addWidget(self.chat_list, 1)
        root.addWidget(self.input_bar)

        app = QApplication.instance()
        if app is not None:
            app.installEventFilter(self)

        self._apply_window_style()

    def show_window(self) -> None:
        self._closed_by_outside = False
        self.show()
        self.raise_()
        self.activateWindow()

    def set_messages(self, messages: list[ChatMessage]) -> None:
        self.chat_list.set_messages(messages)

    def prepend_messages(self, messages: list[ChatMessage]) -> int:
        return self.chat_list.prepend_messages(messages)

    def append_message(self, message: ChatMessage) -> None:
        self.chat_list.add_message(message)

    def add_typing(self) -> None:
        self.chat_list.add_typing()

    def remove_typing(self) -> None:
        self.chat_list.remove_typing()

    def set_busy(self, busy: bool) -> None:
        self.input_bar.set_busy(busy)

    def register_popup(self, popup: QWidget) -> None:
        if popup not in self._registered_popups:
            self._registered_popups.append(popup)

    def closeEvent(self, event) -> None:
        event.ignore()
        self.hide()

    def hideEvent(self, event) -> None:
        for popup in list(self._registered_popups):
            popup.hide()
        super().hideEvent(event)

    def changeEvent(self, event) -> None:
        super().changeEvent(event)
        if (
            event.type() == QEvent.Type.PaletteChange
            and not getattr(self, "_applying_style", False)
        ):
            self._apply_window_style()

    def eventFilter(self, watched, event) -> bool:
        if (
            self.isVisible()
            and event.type() == QEvent.Type.MouseButtonPress
            and hasattr(event, "button")
            and event.button() != Qt.MouseButton.RightButton
            and isinstance(watched, QWidget)
            and not self._contains_chat_widget(watched)
        ):
            self.close_from_outside()
        return super().eventFilter(watched, event)

    def close_from_outside(self) -> None:
        self._closed_by_outside = True
        self.hide()

    def take_closed_by_outside(self) -> bool:
        was_closed = self._closed_by_outside
        self._closed_by_outside = False
        return was_closed

    def plus_anchor(self) -> QWidget:
        return self.input_bar

    def _contains_chat_widget(self, widget: QWidget) -> bool:
        current: QWidget | None = widget
        while current is not None:
            if current is self or current in self._registered_popups:
                return True
            current = current.parentWidget()
        return False

    def _apply_window_style(self) -> None:
        if self._applying_style:
            return
        self._applying_style = True
        palette = QApplication.palette()
        window = QColor(32, 34, 38)
        base = QColor(28, 30, 34)
        text = QColor(242, 244, 247)
        button = QColor(34, 36, 41)
        highlight = palette.highlight().color()
        highlighted_text = QColor(255, 255, 255)
        mid = QColor(74, 78, 88)
        try:
            self.setStyleSheet(
                _STYLE_TEMPLATE.format(
                    shell_bg=_rgba(window, 0.96),
                    row_bg=_rgba(base, 0.62),
                    text=_hex(text),
                    on_accent=_hex(highlighted_text),
                    soft_text=_rgba(text, 0.74),
                    muted_text=_rgba(text, 0.55),
                    border=_rgba(mid, 0.28),
                    soft_border=_rgba(mid, 0.26),
                    user_bg=_rgba(highlight, 0.90),
                    user_hover=_rgba(highlight, 0.78),
                    pet_bg=_rgba(base, 0.84),
                    notice_bg=_rgba(base, 0.84),
                    field_bg=_rgba(base, 0.92),
                    button_bg=_rgba(button, 0.88),
                    button_hover=_rgba(_blend(button, highlight, 0.12), 0.96),
                    button_pressed=_rgba(_blend(button, highlight, 0.22), 0.96),
                    avatar_bg=_rgba(base, 0.86),
                    avatar_edge=_rgba(mid, 0.32),
                    sticker_bg=_rgba(button, 0.78),
                    sticker_missing_bg=_rgba(base, 0.62),
                    sticker_border=_rgba(mid, 0.28),
                )
            )
        finally:
            self._applying_style = False


def _avatar_assets(config: ChatConfig) -> dict[ChatSender, Path]:
    resources = config.project_root / "resources" / "chat"
    return {
        ChatSender.USER: resources / "user_default_avatar.png",
        ChatSender.LOLITH: resources / "pet_default_avatar.png",
    }

def _hex(color: QColor) -> str:
    return color.name()


def _rgba(color: QColor, alpha: float) -> str:
    alpha_i = max(0, min(255, round(alpha * 255)))
    return f"rgba({color.red()}, {color.green()}, {color.blue()}, {alpha_i})"


def _blend(a: QColor, b: QColor, ratio: float) -> QColor:
    ratio = max(0.0, min(1.0, ratio))
    return QColor(
        round(a.red() * (1.0 - ratio) + b.red() * ratio),
        round(a.green() * (1.0 - ratio) + b.green() * ratio),
        round(a.blue() * (1.0 - ratio) + b.blue() * ratio),
    )


_STYLE_TEMPLATE = """
QWidget#chatWindow {{
    background: transparent;
    color: {text};
    border: none;
}}
QLabel#chatAvatarPet,
QLabel#chatAvatarUser {{
    background: transparent;
    border: none;
    border-radius: 14px;
    color: {soft_text};
    font-size: 12px;
    font-weight: 700;
}}
QPushButton#chatCloseButton,
QPushButton#chatPlusButton {{
    background: {button_bg};
    border: 1px solid {border};
    border-radius: 9px;
    color: {text};
    font-size: 20px;
}}
QPushButton#chatSendButton {{
    background: {user_bg};
    border: 1px solid {border};
    border-radius: 9px;
    color: {on_accent};
    font-size: 15px;
    font-weight: 700;
}}
QPushButton#chatCloseButton:hover,
QPushButton#chatPlusButton:hover {{
    background: {button_hover};
}}
QPushButton#chatSendButton:hover {{
    background: {user_hover};
}}
QPushButton#chatCloseButton:pressed,
QPushButton#chatPlusButton:pressed,
QPushButton#chatSendButton:pressed {{
    background: {button_pressed};
}}
QPushButton#chatPlusButton:disabled,
QPushButton#chatSendButton:disabled {{
    color: {muted_text};
    background: {field_bg};
}}
QScrollArea#chatList {{
    background: transparent;
    border: none;
}}
QScrollArea#chatList::viewport {{
    background: transparent;
    border: none;
}}
QScrollArea#chatList > QWidget > QWidget {{
    background: transparent;
}}
QWidget#chatMessageRow,
QWidget#chatTypingRow,
QWidget#chatMessageStackPet,
QWidget#chatMessageStackUser {{
    background: transparent;
    border: none;
}}
QWidget#chatInputBar {{
    background: {shell_bg};
    border: 1px solid {soft_border};
    border-radius: 13px;
}}
QTextEdit#chatInputEdit {{
    background: {field_bg};
    color: {text};
    border: 1px solid {soft_border};
    border-radius: 10px;
    padding: 7px 9px;
    selection-background-color: {user_bg};
    selection-color: {on_accent};
}}
	QFrame#chatUserBubble {{
	    background: {user_bg};
    border: 1px solid {border};
    border-radius: 8px;
}}
QFrame#chatPetBubble,
QFrame#chatTypingBubble {{
    background: {pet_bg};
    border: 1px solid {border};
    border-radius: 8px;
}}
	QFrame#chatNoticeBubble {{
	    background: {notice_bg};
	    border: 1px solid {soft_border};
	    border-radius: 8px;
	}}
	QFrame#chatStickerBubble {{
	    background: transparent;
	    border: none;
	}}
	QLabel#chatBubbleText {{
	    color: {text};
    font-size: 13px;
    line-height: 18px;
}}
QFrame#chatUserBubble QLabel#chatBubbleText {{
    color: {on_accent};
}}
QFrame#chatStickerTile,
QFrame#chatStickerTileMissing {{
    background: {sticker_bg};
    border: 1px solid {sticker_border};
    border-radius: 8px;
}}
QFrame#chatStickerTileMissing {{
    background: {sticker_missing_bg};
    border-style: dashed;
}}
QLabel#chatStickerImage {{
    background: transparent;
}}
QLabel#chatStickerPlaceholder {{
    background: {row_bg};
    border-radius: 8px;
    color: {soft_text};
    font-weight: 600;
}}
QLabel#chatStickerCaption {{
    color: {soft_text};
    font-size: 11px;
}}
QFrame#chatPlusMenu {{
    background: {shell_bg};
    border: 1px solid {border};
    border-radius: 8px;
}}
QToolButton#chatPlusMenuButton_stickers {{
    background: {button_bg};
    border: 1px solid {border};
    border-radius: 7px;
    color: {text};
    font-size: 13px;
}}
QToolButton#chatPlusMenuButton_stickers:hover {{
    background: {button_hover};
}}
QFrame#stickerPicker {{
    background: {shell_bg};
    border: 1px solid {border};
    border-radius: 8px;
}}
	QToolButton#stickerButton {{
	    background: {button_bg};
	    border: 1px solid {border};
	    border-radius: 7px;
	    color: {text};
	    font-size: 11px;
	}}
	QToolButton#stickerButton:hover {{
	    background: {button_hover};
	}}
"""


__all__ = ["ChatWindow"]

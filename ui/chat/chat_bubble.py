"""聊天气泡组件"""

from __future__ import annotations

import re
from pathlib import Path

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import QFrame, QLabel, QSizePolicy, QVBoxLayout

from core.chat.models import ChatMessage, ChatMessageType, ChatSender
from ui.chat.sticker_resolver import StickerPathResolver

LONG_RUN_RE = re.compile(r"([^\s]{18,})")
STICKER_IMAGE_SIZE = 112


class ChatBubble(QFrame):
    def __init__(
        self,
        message: ChatMessage | None = None,
        *,
        sticker_resolver: StickerPathResolver | None = None,
        typing: bool = False,
    ) -> None:
        super().__init__()
        self.message_id = message.id if message is not None else ""
        self.is_typing = typing
        sticker_only = _is_sticker_only(message, typing=typing)
        self.setObjectName(_bubble_object_name(message, typing=typing))
        self.setMaximumWidth(132 if sticker_only else 236)
        self.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Preferred)

        layout = QVBoxLayout(self)
        if sticker_only:
            layout.setContentsMargins(2, 2, 2, 2)
            layout.setSpacing(0)
        else:
            layout.setContentsMargins(11, 8, 11, 8)
            layout.setSpacing(7)

        sticker_id = _message_sticker_id(message)
        text = _bubble_text(message, typing=typing)
        if text:
            label = QLabel(_break_long_runs(text))
            label.setObjectName("chatBubbleText")
            label.setWordWrap(True)
            label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            label.setMaximumWidth(214)
            layout.addWidget(label)
        if sticker_id is not None:
            layout.addWidget(
                _build_sticker_tile(
                    sticker_id,
                    sticker_resolver,
                    message=message,
                    compact=sticker_only,
                )
            )
        if not text and sticker_id is None:
            label = QLabel("")
            label.setObjectName("chatBubbleText")
            layout.addWidget(label)


def _bubble_object_name(message: ChatMessage | None, *, typing: bool) -> str:
    if typing:
        return "chatTypingBubble"
    if message is None:
        return "chatPetBubble"
    if message.type == ChatMessageType.SYSTEM_NOTICE:
        return "chatNoticeBubble"
    if _is_sticker_only(message, typing=typing):
        return "chatStickerBubble"
    if message.sender == ChatSender.USER:
        return "chatUserBubble"
    return "chatPetBubble"


def _bubble_text(message: ChatMessage | None, *, typing: bool) -> str:
    if typing:
        return "正在输入..."
    if message is None:
        return ""
    if message.type == ChatMessageType.SYSTEM_NOTICE:
        return message.text or "我刚刚卡了一下。"
    if message.type == ChatMessageType.STICKER:
        return ""
    if message.type == ChatMessageType.MIXED:
        return message.text
    if message.type == ChatMessageType.FILE:
        return message.text or "[文件]"
    return message.text or ""


def _message_sticker_id(message: ChatMessage | None) -> str | None:
    if message is None:
        return None
    sticker_id = str(message.sticker_id or "").strip()
    return sticker_id or None


def _is_sticker_only(message: ChatMessage | None, *, typing: bool = False) -> bool:
    return (
        not typing
        and message is not None
        and message.type == ChatMessageType.STICKER
        and _message_sticker_id(message) is not None
    )


def _build_sticker_tile(
    sticker_id: str,
    sticker_resolver: StickerPathResolver | None,
    *,
    message: ChatMessage | None,
    compact: bool = False,
) -> QFrame:
    resolved = None
    if sticker_resolver is not None:
        resolved = sticker_resolver.resolve(
            sticker_id,
            sender=message.sender if message is not None else None,
            metadata=message.metadata if message is not None else None,
        )
    pixmap = _load_sticker_pixmap(resolved.path if resolved is not None else None)
    tile = QFrame()
    tile.setObjectName("chatStickerTile" if pixmap is not None else "chatStickerTileMissing")
    tile.setProperty("stickerId", sticker_id)
    tile.setProperty("stickerPath", str(resolved.path) if resolved is not None else "")
    tile.setProperty("stickerSource", resolved.source if resolved is not None else "missing")
    if compact:
        tile.setFixedSize(124, 136)
        image_size = STICKER_IMAGE_SIZE
        target = QSize(STICKER_IMAGE_SIZE, STICKER_IMAGE_SIZE)
        margins = (5, 5, 5, 4)
        spacing = 3
    else:
        tile.setFixedSize(132, 108)
        image_size = 72
        target = QSize(104, 72)
        margins = (8, 8, 8, 7)
        spacing = 5

    layout = QVBoxLayout(tile)
    layout.setContentsMargins(*margins)
    layout.setSpacing(spacing)

    image = QLabel()
    image.setObjectName("chatStickerImage" if pixmap is not None else "chatStickerPlaceholder")
    image.setProperty("stickerId", sticker_id)
    image.setProperty("stickerPath", str(resolved.path) if resolved is not None else "")
    image.setProperty("stickerSource", resolved.source if resolved is not None else "missing")
    image.setAlignment(Qt.AlignmentFlag.AlignCenter)
    image.setFixedSize(STICKER_IMAGE_SIZE if compact else 116, image_size)
    image.setScaledContents(False)
    if pixmap is None:
        image.setText("贴纸")
    else:
        image.setPixmap(
            pixmap.scaled(
                target,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )
    layout.addWidget(image)

    return tile


def _load_sticker_pixmap(path: Path | None) -> QPixmap | None:
    if path is None or not path.exists():
        return None
    pixmap = QPixmap(str(path))
    if pixmap.isNull():
        return None
    return pixmap


def _break_long_runs(text: str, *, every: int = 18) -> str:
    def break_run(match: re.Match[str]) -> str:
        run = match.group(1)
        return "\u200b".join(run[index : index + every] for index in range(0, len(run), every))

    return LONG_RUN_RE.sub(break_run, text)


__all__ = ["ChatBubble"]

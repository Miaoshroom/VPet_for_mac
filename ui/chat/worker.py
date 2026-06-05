"""聊天后台任务"""

from __future__ import annotations

from typing import Any, Mapping

from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot

from core.chat.models import ChatMessageType
from core.chat.service import ChatService


class ChatWorker(QObject):
    succeeded = pyqtSignal(object)
    failed = pyqtSignal(str)
    finished = pyqtSignal()

    def __init__(
        self,
        service: ChatService,
        text: str,
        *,
        client_message_id: str,
        message_type: ChatMessageType = ChatMessageType.TEXT,
        sticker_id: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__()
        self._service = service
        self._text = text
        self._client_message_id = client_message_id
        self._message_type = message_type
        self._sticker_id = sticker_id
        self._metadata = dict(metadata or {})

    @pyqtSlot()
    def run(self) -> None:
        try:
            if self._message_type == ChatMessageType.STICKER and self._sticker_id:
                result = self._service.send_user_sticker(
                    self._sticker_id,
                    label=self._text,
                    metadata=self._metadata,
                    client_message_id=self._client_message_id,
                )
            else:
                result = self._service.send_user_message(
                    self._text,
                    metadata=self._metadata,
                    client_message_id=self._client_message_id,
                )
        except Exception:
            self.failed.emit("chat_worker_failed")
        else:
            self.succeeded.emit(result)
        finally:
            self.finished.emit()


__all__ = ["ChatWorker"]

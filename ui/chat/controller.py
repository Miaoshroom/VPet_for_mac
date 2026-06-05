"""聊天窗口控制器"""

from __future__ import annotations

from datetime import date
from typing import Any, Mapping

from PyQt6.QtCore import QPoint, QRect, QObject, QThread, pyqtSignal
from PyQt6.QtGui import QGuiApplication
from PyQt6.QtWidgets import QMessageBox

from core.chat.config import ChatConfig, load_chat_config
from core.chat.models import (
    ChatMessage,
    ChatMessageStatus,
    ChatMessageType,
    ChatSender,
    ChatTurnResult,
    EffectRequest,
)
from core.chat.ports import ChatEffectExecutor, ChatPetContextProvider
from core.chat.service import ChatService
from ui.chat.chat_window import ChatWindow
from ui.chat.memory_editor import MemoryEditorDialog
from ui.chat.plus_menu import PlusMenu
from ui.chat.sticker_picker import StickerPicker
from ui.chat.worker import ChatWorker


class ChatController(QObject):
    turn_finished = pyqtSignal(object)
    effects_ready = pyqtSignal(object)
    worker_failed = pyqtSignal(str)

    def __init__(
        self,
        *,
        config: ChatConfig | None = None,
        service: ChatService | None = None,
        window: ChatWindow | None = None,
        rect_provider: Any | None = None,
        effect_executor: ChatEffectExecutor | None = None,
        pet_context_provider: ChatPetContextProvider | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.config = config or (service.config if service is not None else load_chat_config())
        self.service = service or ChatService(
            config=self.config,
            pet_context_provider=pet_context_provider,
        )
        self.window = window or ChatWindow(config=self.config)
        self._rect_provider = rect_provider
        self._effect_executor = effect_executor
        self._busy = False
        self._threads: list[QThread] = []
        self._workers: list[ChatWorker] = []
        self._pending_effects: list[EffectRequest] = []
        self._recent_effect_results: tuple[str, ...] = ()
        self._earliest_loaded_day: date | None = None
        self._loading_older = False
        self._has_older_history = False
        self._pending_memory_delete: dict[str, Any] | None = None
        self._plus_menu = PlusMenu(self.window)
        self._sticker_picker = StickerPicker(
            list(self.window.user_stickers),
            self.window.sticker_resolver,
            self.window,
        )
        self._memory_editor = MemoryEditorDialog(
            self.window,
            config=self.config,
            memory_store=self.service.memory_store,
        )
        self.window.register_popup(self._plus_menu)
        self.window.register_popup(self._sticker_picker)
        self.window.register_popup(self._memory_editor)
        self._connect_window()

    @property
    def is_busy(self) -> bool:
        return self._busy

    @property
    def active_worker_count(self) -> int:
        return len(self._threads)

    @property
    def pending_effects(self) -> tuple[EffectRequest, ...]:
        return tuple(self._pending_effects)

    @property
    def recent_effect_results(self) -> tuple[str, ...]:
        return self._recent_effect_results

    @property
    def pending_memory_delete(self) -> Mapping[str, Any] | None:
        if self._pending_memory_delete is None:
            return None
        return dict(self._pending_memory_delete)

    def show_window(self) -> None:
        self.load_recent_messages()
        self.reposition_window()
        self.window.show_window()

    def focus_window(self) -> None:
        self.reposition_window()
        self.window.show_window()

    def hide_window(self) -> None:
        self._pending_memory_delete = None
        self._plus_menu.hide()
        self._sticker_picker.hide()
        self._memory_editor.hide()
        self.window.hide()

    def reposition_window(self) -> bool:
        rect = self._provided_rect()
        if rect is None or rect.isNull() or not rect.isValid():
            return False
        self.window.move(_chat_position(rect, self.window.size()))
        return True

    def load_recent_messages(self) -> None:
        latest_day = self.service.history_store.latest_day()
        if latest_day is None:
            self._earliest_loaded_day = None
            self._has_older_history = False
            self.window.set_messages([])
            return
        messages = self.service.history_store.load_day(
            latest_day,
            limit=self.config.storage.recent_history_limit,
        )
        self._earliest_loaded_day = latest_day
        self._has_older_history = (
            self.service.history_store.previous_day_before(latest_day) is not None
        )
        self.window.set_messages(messages)

    def send_text(self, text: str) -> bool:
        text = str(text).strip()
        if not text or self._busy:
            return False
        client_id = self.service.id_generator.new_id("user_ui")
        optimistic = ChatMessage(
            id=client_id,
            timestamp=self.service.clock.now().isoformat(),
            sender=ChatSender.USER,
            type=ChatMessageType.TEXT,
            text=text,
            status=ChatMessageStatus.PENDING,
        )
        self.window.append_message(optimistic)
        self._start_worker(text, client_id, metadata={})
        return True

    def send_sticker(self, sticker_id: str) -> bool:
        sticker_id = str(sticker_id).strip()
        if not sticker_id or self._busy:
            return False
        sticker_label = _sticker_label(
            self.config,
            sticker_id,
            self.window.user_stickers,
        )
        client_id = self.service.id_generator.new_id("user_ui")
        optimistic = ChatMessage(
            id=client_id,
            timestamp=self.service.clock.now().isoformat(),
            sender=ChatSender.USER,
            type=ChatMessageType.STICKER,
            text=sticker_label,
            sticker_id=sticker_id,
            status=ChatMessageStatus.PENDING,
            metadata=_sticker_metadata(
                self.config,
                sticker_id,
                sticker_label,
                self.window.user_stickers,
            ),
        )
        self.window.append_message(optimistic)
        self._start_worker(
            sticker_label,
            client_id,
            message_type=ChatMessageType.STICKER,
            sticker_id=sticker_id,
            metadata=_sticker_metadata(
                self.config,
                sticker_id,
                sticker_label,
                self.window.user_stickers,
            ),
        )
        return True

    def _connect_window(self) -> None:
        self.window.send_requested.connect(self.send_text)
        self.window.plus_requested.connect(self._show_plus_menu)
        self.window.load_older_requested.connect(self._request_older_messages)
        self._plus_menu.sticker_requested.connect(self._show_sticker_picker)
        self._plus_menu.memory_requested.connect(self._show_memory_editor)
        self._sticker_picker.sticker_selected.connect(self.send_sticker)

    def _show_plus_menu(self) -> None:
        self._sticker_picker.hide()
        self._plus_menu.show_near(self.window.plus_anchor())

    def _show_sticker_picker(self) -> None:
        self._sticker_picker.show_near(self.window.plus_anchor())

    def _show_memory_editor(self) -> None:
        self._sticker_picker.hide()
        self._memory_editor.show_editor()

    def _start_worker(
        self,
        text: str,
        client_id: str,
        *,
        message_type: ChatMessageType = ChatMessageType.TEXT,
        sticker_id: str | None = None,
        metadata: dict[str, Any],
    ) -> None:
        self._set_busy(True)
        self.window.add_typing()

        thread = QThread(self)
        worker = ChatWorker(
            self.service,
            text,
            client_message_id=client_id,
            message_type=message_type,
            sticker_id=sticker_id,
            metadata=metadata,
        )
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.succeeded.connect(self._on_worker_succeeded)
        worker.failed.connect(self._on_worker_failed)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(lambda t=thread, w=worker: self._forget_worker(t, w))
        self._threads.append(thread)
        self._workers.append(worker)
        thread.start()

    def _on_worker_succeeded(self, result: ChatTurnResult) -> None:
        self.window.remove_typing()
        if result.provider_result.ok:
            self.window.append_message(result.pet_message)
        else:
            self.window.append_message(_failure_notice(result.pet_message.id))
        if result.effects:
            self._pending_effects = list(result.effects)
            self.effects_ready.emit(tuple(result.effects))
            self._execute_effects(result.effects)
            if self._effect_executor is not None:
                self._pending_effects = []
        else:
            self._pending_effects = []
            self._recent_effect_results = ()
        self.turn_finished.emit(result)
        self._set_busy(False)
        self._handle_memory_delete_proposal(result)

    def _on_worker_failed(self, error: str) -> None:
        self.window.remove_typing()
        self.window.append_message(_failure_notice("chat_worker_failed_notice"))
        self.worker_failed.emit(error)
        self._set_busy(False)

    def _forget_worker(self, thread: QThread, worker: ChatWorker) -> None:
        if thread in self._threads:
            self._threads.remove(thread)
        if worker in self._workers:
            self._workers.remove(worker)

    def _set_busy(self, busy: bool) -> None:
        self._busy = bool(busy)
        self.window.set_busy(self._busy)

    def _execute_effects(self, effects: tuple[EffectRequest, ...]) -> None:
        if self._effect_executor is None:
            self._recent_effect_results = ()
            return
        try:
            self._recent_effect_results = tuple(self._effect_executor.execute(effects))
        except Exception:
            self._recent_effect_results = ("execution_failed",)

    def _handle_memory_delete_proposal(self, result: ChatTurnResult) -> None:
        proposal = _memory_delete_proposal(result.metadata)
        if proposal is None or proposal.get("status") != "needs_confirmation":
            return
        candidates = proposal.get("candidates")
        if not isinstance(candidates, list) or len(candidates) != 1:
            return
        candidate = candidates[0]
        if not isinstance(candidate, Mapping):
            return
        self._pending_memory_delete = dict(proposal)
        preview = str(candidate.get("text") or "")
        if self._confirm_memory_delete(preview):
            self.confirm_pending_memory_delete()
        else:
            self.cancel_pending_memory_delete()

    def confirm_pending_memory_delete(self) -> bool:
        proposal = self._pending_memory_delete
        self._pending_memory_delete = None
        if not proposal:
            return False
        candidates = proposal.get("candidates")
        if not isinstance(candidates, list) or len(candidates) != 1:
            return False
        candidate = candidates[0]
        if not isinstance(candidate, Mapping):
            return False
        note_id = str(candidate.get("id") or "").strip()
        if not note_id:
            return False
        try:
            result = self.service.memory_store.delete_manual_notes(
                [note_id],
                actor="user",
            )
        except (OSError, ValueError):
            self._append_local_notice("刚刚没删成。")
            return False
        if result.status == "deleted":
            self._append_local_notice("删掉啦。")
            if self._memory_editor.isVisible():
                self._memory_editor.load_memory()
            return True
        self._append_local_notice("刚刚没删成，可能已经不在记忆里了。")
        return False

    def cancel_pending_memory_delete(self) -> bool:
        if self._pending_memory_delete is None:
            return False
        self._pending_memory_delete = None
        self._append_local_notice("先不删。")
        return True

    def _confirm_memory_delete(self, preview_text: str) -> bool:
        box = QMessageBox(self.window)
        box.setWindowTitle("删除记忆")
        box.setText(f"我找到这条记忆，要删掉吗？\n\n{preview_text}")
        confirm = box.addButton("确认删除", QMessageBox.ButtonRole.AcceptRole)
        cancel = box.addButton("先不删", QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(cancel)
        box.exec()
        return box.clickedButton() is confirm

    def _append_local_notice(self, text: str) -> None:
        message = ChatMessage(
            id=self.service.id_generator.new_id("lolith_ui"),
            timestamp=self.service.clock.now().isoformat(),
            sender=ChatSender.LOLITH,
            type=ChatMessageType.TEXT,
            text=text,
            status=ChatMessageStatus.SENT,
        )
        self.service.history_store.append(message)
        self.window.append_message(message)

    def _request_older_messages(self) -> None:
        if (
            self._loading_older
            or not self._has_older_history
            or self._earliest_loaded_day is None
        ):
            return
        self._loading_older = True
        try:
            previous_day = self.service.history_store.previous_day_before(
                self._earliest_loaded_day
            )
            if previous_day is None:
                self._has_older_history = False
                return
            messages = self.service.history_store.load_day(previous_day)
            self._earliest_loaded_day = previous_day
            self._has_older_history = (
                self.service.history_store.previous_day_before(previous_day) is not None
            )
            if messages:
                self.window.prepend_messages(messages)
        finally:
            self._loading_older = False

    def _provided_rect(self) -> QRect | None:
        if self._rect_provider is None:
            return None
        rect = self._rect_provider()
        if isinstance(rect, QRect):
            return rect
        return None


def _failure_notice(message_id: str) -> ChatMessage:
    return ChatMessage(
        id=f"{message_id}_notice",
        timestamp="",
        sender=ChatSender.SYSTEM,
        type=ChatMessageType.SYSTEM_NOTICE,
        text="我刚刚卡了一下。",
        status=ChatMessageStatus.FAILED,
    )


def _memory_delete_proposal(metadata: Mapping[str, Any]) -> Mapping[str, Any] | None:
    proposal = metadata.get("memory_delete_proposal")
    if isinstance(proposal, Mapping):
        return proposal
    return None


def _sticker_label(
    config: ChatConfig,
    sticker_id: str,
    user_stickers: list[dict[str, object]],
) -> str:
    for sticker in user_stickers:
        if str(sticker.get("id", "")).strip() == sticker_id:
            return str(sticker.get("label", sticker_id)).strip() or sticker_id
    return _configured_sticker_label(config, sticker_id)


def _configured_sticker_label(config: ChatConfig, sticker_id: str) -> str:
    sticker = config.stickers.get(sticker_id)
    if sticker is None:
        return sticker_id
    return sticker.label


def _sticker_metadata(
    config: ChatConfig,
    sticker_id: str,
    label: str,
    user_stickers: list[dict[str, object]] | None = None,
) -> dict[str, Any]:
    metadata: dict[str, Any] = {"label": label}
    if any(
        str(sticker.get("id", "")).strip() == sticker_id
        and str(sticker.get("source", "")).strip() == "user"
        for sticker in (user_stickers or ())
    ):
        metadata["source"] = "user"
        return metadata
    sticker = config.stickers.get(sticker_id)
    if sticker is None:
        return metadata
    tags = sticker.metadata.get("tags")
    if isinstance(tags, list | tuple):
        clean_tags = [str(tag).strip() for tag in tags if str(tag).strip()]
        if clean_tags:
            metadata["tags"] = clean_tags
    source = str(sticker.metadata.get("source") or "").strip()
    if source:
        metadata["source"] = source
    return metadata


def _chat_position(anchor: QRect, size) -> QPoint:
    screen = QGuiApplication.screenAt(anchor.center()) or QGuiApplication.primaryScreen()
    available = screen.availableGeometry() if screen is not None else QRect(0, 0, 1440, 900)
    gap = 12
    width = max(1, int(size.width()))
    height = max(1, int(size.height()))
    right_x = anchor.right() + gap
    left_x = anchor.left() - width - gap
    if right_x + width <= available.right() + 1:
        x = right_x
    elif left_x >= available.left():
        x = left_x
    else:
        x = anchor.center().x() - width // 2
    y = anchor.center().y() - height // 2
    x = min(max(x, available.left()), available.right() - width + 1)
    y = min(max(y, available.top()), available.bottom() - height + 1)
    return QPoint(x, y)


__all__ = ["ChatController"]

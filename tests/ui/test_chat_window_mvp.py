from __future__ import annotations

import json
import os
import sys
import tempfile
import time
import unittest
from datetime import date, datetime, timezone
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = next(path for path in Path(__file__).resolve().parents if (path / "main.py").is_file())
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from PyQt6.QtCore import QPointF, QEvent, Qt
from PyQt6.QtGui import QColor, QImage, QMouseEvent
from PyQt6.QtWidgets import QApplication, QFrame, QLabel, QToolButton, QWidget

from core.chat.config import load_chat_config
from core.chat.context_builder import StaticChatPetContextProvider
from core.chat.history_store import HistoryStore
from core.chat.memory_store import MemoryStore
from core.chat.models import (
    ChatMessage,
    ChatMessageType,
    ChatSender,
    PetContextSnapshot,
    ProviderResult,
)
from core.chat.service import ChatService
from ui.chat.chat_list import ChatList
from ui.chat.controller import ChatController
from ui.chat.chat_window import ChatWindow
from ui.chat.sticker_resolver import StickerPathResolver


class FixedClock:
    def __init__(self) -> None:
        self.count = 0

    def now(self) -> datetime:
        self.count += 1
        return datetime(2026, 6, 4, 9, 0, self.count, tzinfo=timezone.utc)


class SequentialIds:
    def __init__(self) -> None:
        self.count = 0

    def new_id(self, prefix: str = "") -> str:
        self.count += 1
        return f"{prefix}_{self.count}" if prefix else str(self.count)


class SlowFakeProvider:
    def __init__(self, delay_seconds: float = 0.05) -> None:
        self.delay_seconds = delay_seconds
        self.payloads = []

    def complete(self, payload) -> ProviderResult:
        self.payloads.append(payload)
        time.sleep(self.delay_seconds)
        return ProviderResult(
            ok=True,
            content=json.dumps(
                {
                    "schema_version": 1,
                    "text": "我在，这里先走窗口 MVP。",
                    "sticker_id": None,
                    "action_id": None,
                    "intent": "chat",
                    "state_request": None,
                },
                ensure_ascii=False,
            ),
            provider="fake",
        )


class ActionFakeProvider(SlowFakeProvider):
    def complete(self, payload) -> ProviderResult:
        self.payloads.append(payload)
        time.sleep(self.delay_seconds)
        return ProviderResult(
            ok=True,
            content=json.dumps(
                {
                    "schema_version": 1,
                    "text": "我想一下。",
                    "sticker_id": None,
                    "action_id": "say_self",
                    "intent": "action_request",
                    "state_request": None,
                },
                ensure_ascii=False,
            ),
            provider="fake",
        )


class RecordingEffectExecutor:
    def __init__(self, reasons: tuple[str, ...] = ("performed",)) -> None:
        self.reasons = reasons
        self.effects = []

    def execute(self, effects):
        self.effects.extend(effects)
        return self.reasons


class CountingHistoryStore(HistoryStore):
    def __init__(self, storage) -> None:
        super().__init__(storage)
        self.previous_day_queries = 0

    def previous_day_before(self, day) -> date | None:
        self.previous_day_queries += 1
        return super().previous_day_before(day)


def _write_long_term_memory(root: Path, manual_notes: list[object]) -> None:
    memory_file = root / "chat_data" / "memory" / "long_term_memory.json"
    memory_file.parent.mkdir(parents=True)
    memory_file.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "updated_at": None,
                "relationship_summary": "",
                "user_preferences": [],
                "important_facts": [],
                "recurring_topics": [],
                "boundaries": [],
                "manual_notes": manual_notes,
                "daily_summaries": [],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def _app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _wait_until(app: QApplication, condition, timeout_ms: int = 1200) -> bool:
    deadline = time.monotonic() + timeout_ms / 1000
    while time.monotonic() < deadline:
        app.processEvents()
        if condition():
            return True
        time.sleep(0.005)
    app.processEvents()
    return bool(condition())


class ChatWindowMvpTest(unittest.TestCase):
    def test_window_hides_on_left_click_outside_without_worker_shutdown(self) -> None:
        app = _app()
        with tempfile.TemporaryDirectory() as tmp_dir:
            config = load_chat_config(project_root=Path(tmp_dir))
            window = ChatWindow(config=config)
            outside = QWidget()
            window.show()
            app.processEvents()

            event = QMouseEvent(
                QEvent.Type.MouseButtonPress,
                QPointF(1, 1),
                QPointF(1, 1),
                Qt.MouseButton.LeftButton,
                Qt.MouseButton.LeftButton,
                Qt.KeyboardModifier.NoModifier,
            )
            window.eventFilter(outside, event)
            app.processEvents()

            self.assertFalse(window.isVisible())
            outside.deleteLater()

    def test_window_renders_missing_sticker_as_message_without_crashing(self) -> None:
        app = _app()
        with tempfile.TemporaryDirectory() as tmp_dir:
            config = load_chat_config(project_root=Path(tmp_dir))
            window = ChatWindow(config=config)
            message = ChatMessage(
                id="missing_sticker_message",
                timestamp="2026-06-04T09:00:00+00:00",
                sender=ChatSender.LOLITH,
                type=ChatMessageType.STICKER,
                sticker_id="missing_sticker",
            )

            window.set_messages([message])
            app.processEvents()

            self.assertIn("missing_sticker_message", window.chat_list.message_ids())
            self.assertFalse(window.chat_list.has_typing())
            window.hide()

    def test_plus_menu_opens_sticker_picker_with_present_and_missing_images(
        self,
    ) -> None:
        app = _app()
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            _write_sticker_config(root, ["sticker_01", "missing_sticker"])
            _write_sticker_image(root, "sticker_01")
            config = load_chat_config(project_root=root)
            controller = ChatController(config=config)
            app.processEvents()

            controller.window.input_bar._plus_button.click()
            app.processEvents()
            menu_buttons = controller._plus_menu.findChildren(
                QToolButton,
                "chatPlusMenuButton_stickers",
            )
            self.assertEqual([button.text() for button in menu_buttons], ["表情包"])

            menu_buttons[0].click()
            app.processEvents()
            buttons = controller._sticker_picker.findChildren(
                QToolButton,
                "stickerButton",
            )

            self.assertEqual([button.text() for button in buttons], ["贴纸1", "贴纸2"])
            self.assertTrue(all(not button.icon().isNull() for button in buttons))
            controller.hide_window()

    def test_plus_menu_opens_manual_memory_editor(self) -> None:
        app = _app()
        with tempfile.TemporaryDirectory() as tmp_dir:
            controller = ChatController(
                config=load_chat_config(project_root=Path(tmp_dir))
            )
            app.processEvents()

            controller.window.input_bar._plus_button.click()
            app.processEvents()
            memory_buttons = controller._plus_menu.findChildren(
                QToolButton,
                "chatPlusMenuButton_memory",
            )
            self.assertEqual([button.text() for button in memory_buttons], ["记忆"])

            memory_buttons[0].click()
            app.processEvents()

            self.assertTrue(controller._memory_editor.isVisible())
            self.assertIn("relationship_summary", controller._memory_editor._editor.toPlainText())
            controller.hide_window()

    def test_controller_builds_service_with_injected_pet_context_provider(self) -> None:
        app = _app()
        self.assertIsNotNone(app)
        with tempfile.TemporaryDirectory() as tmp_dir:
            provider = StaticChatPetContextProvider(
                PetContextSnapshot(
                    pet_state={"satiety": 7},
                    visual_state="ill",
                )
            )
            controller = ChatController(
                config=load_chat_config(project_root=Path(tmp_dir)),
                pet_context_provider=provider,
            )

            self.assertIs(
                controller.service.context_builder.pet_context_provider,
                provider,
            )
            controller.hide_window()

    def test_controller_confirms_single_memory_delete_candidate(self) -> None:
        app = _app()
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            _write_long_term_memory(
                root,
                [
                    {
                        "id": "note_ice",
                        "created_at": "2026-06-04T10:00:00+00:00",
                        "text": "用户喜欢冰美式",
                        "source": "user_explicit",
                        "source_message_id": "u0",
                        "tags": [],
                    }
                ],
            )
            config = load_chat_config(project_root=root)
            history = HistoryStore(config.storage)
            service = ChatService(
                config=config,
                history_store=history,
                memory_store=MemoryStore(config.storage),
                provider=SlowFakeProvider(delay_seconds=0.01),
                clock=FixedClock(),
                id_generator=SequentialIds(),
            )
            controller = ChatController(config=config, service=service)
            controller._confirm_memory_delete = lambda preview: True

            self.assertTrue(controller.send_text("忘记我喜欢冰美式"))
            self.assertTrue(
                _wait_until(
                    app,
                    lambda: not controller.is_busy and controller.active_worker_count == 0,
                )
            )
            saved = service.memory_store.load_full()
            backups = list((config.storage.memory_dir / "backups").glob("*.json"))
            bubble_texts = [
                label.text()
                for label in controller.window.findChildren(QLabel, "chatBubbleText")
            ]
            controller.hide_window()

        self.assertEqual(saved["manual_notes"], [])
        self.assertEqual(len(backups), 1)
        self.assertIsNone(controller.pending_memory_delete)
        self.assertIn("删掉啦。", bubble_texts)
        self.assertTrue(any("要删掉吗" in text for text in bubble_texts))

    def test_controller_cancel_single_memory_delete_candidate(self) -> None:
        app = _app()
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            _write_long_term_memory(
                root,
                [
                    {
                        "id": "note_ice",
                        "created_at": "2026-06-04T10:00:00+00:00",
                        "text": "用户喜欢冰美式",
                        "source": "user_explicit",
                        "source_message_id": "u0",
                        "tags": [],
                    }
                ],
            )
            config = load_chat_config(project_root=root)
            history = HistoryStore(config.storage)
            service = ChatService(
                config=config,
                history_store=history,
                memory_store=MemoryStore(config.storage),
                provider=SlowFakeProvider(delay_seconds=0.01),
                clock=FixedClock(),
                id_generator=SequentialIds(),
            )
            controller = ChatController(config=config, service=service)
            controller._confirm_memory_delete = lambda preview: False

            self.assertTrue(controller.send_text("忘记我喜欢冰美式"))
            self.assertTrue(
                _wait_until(
                    app,
                    lambda: not controller.is_busy and controller.active_worker_count == 0,
                )
            )
            saved = service.memory_store.load_full()
            backups = list((config.storage.memory_dir / "backups").glob("*.json"))
            bubble_texts = [
                label.text()
                for label in controller.window.findChildren(QLabel, "chatBubbleText")
            ]
            controller.hide_window()

        self.assertEqual(saved["manual_notes"][0]["text"], "用户喜欢冰美式")
        self.assertEqual(backups, [])
        self.assertIsNone(controller.pending_memory_delete)
        self.assertIn("先不删。", bubble_texts)

    def test_sticker_resolver_uses_sender_when_pet_and_user_share_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            _write_sticker_config(
                root,
                ["shared"],
                paths={"shared": "chat_data/pet_stickers/shared.png"},
            )
            pet_path = _write_sticker_image(root, "shared", area="pet")
            user_path = _write_sticker_image(root, "shared", area="user")
            resolver = StickerPathResolver(load_chat_config(project_root=root))

            user_resolved = resolver.resolve("shared", sender=ChatSender.USER)
            pet_resolved = resolver.resolve("shared", sender=ChatSender.LOLITH)

        self.assertIsNotNone(user_resolved)
        self.assertIsNotNone(pet_resolved)
        self.assertEqual(user_resolved.path, user_path)
        self.assertEqual(user_resolved.source, "user")
        self.assertEqual(pet_resolved.path, pet_path)
        self.assertEqual(pet_resolved.source, "configured")

    def test_picker_uses_user_stickers_preview_for_user_send(self) -> None:
        app = _app()
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            _write_sticker_config(
                root,
                ["shared"],
                paths={"shared": "chat_data/pet_stickers/shared.png"},
            )
            _write_sticker_image(root, "shared", area="pet")
            user_path = _write_sticker_image(root, "shared", area="user")
            controller = ChatController(config=load_chat_config(project_root=root))
            app.processEvents()

            controller.window.input_bar._plus_button.click()
            app.processEvents()
            menu_buttons = controller._plus_menu.findChildren(
                QToolButton,
                "chatPlusMenuButton_stickers",
            )
            menu_buttons[0].click()
            app.processEvents()
            buttons = controller._sticker_picker.findChildren(
                QToolButton,
                "stickerButton",
            )

            self.assertEqual([button.text() for button in buttons], ["shared"])
            self.assertEqual(buttons[0].property("stickerSource"), "user")
            self.assertEqual(Path(buttons[0].property("stickerPath")), user_path)
            self.assertFalse(buttons[0].icon().isNull())
            controller.hide_window()

    def test_bubble_resolves_pet_and_user_stickers_by_sender(self) -> None:
        app = _app()
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            _write_sticker_config(
                root,
                ["shared"],
                paths={"shared": "chat_data/pet_stickers/shared.png"},
            )
            pet_path = _write_sticker_image(root, "shared", area="pet")
            user_path = _write_sticker_image(root, "shared", area="user")
            window = ChatWindow(config=load_chat_config(project_root=root))
            window.set_messages(
                [
                    ChatMessage(
                        id="user_shared",
                        timestamp="2026-06-04T09:00:00+00:00",
                        sender=ChatSender.USER,
                        type=ChatMessageType.STICKER,
                        sticker_id="shared",
                    ),
                    ChatMessage(
                        id="pet_shared",
                        timestamp="2026-06-04T09:00:01+00:00",
                        sender=ChatSender.LOLITH,
                        type=ChatMessageType.STICKER,
                        sticker_id="shared",
                    ),
                ]
            )
            app.processEvents()

            sticker_paths = {
                Path(label.property("stickerPath"))
                for label in window.findChildren(QLabel, "chatStickerImage")
            }
            sticker_sources = {
                label.property("stickerSource")
                for label in window.findChildren(QLabel, "chatStickerImage")
            }

            self.assertEqual(sticker_paths, {user_path, pet_path})
            self.assertEqual(sticker_sources, {"user", "configured"})
            window.hide()

    def test_controller_send_sticker_persists_and_reloads_as_sticker_bubble(
        self,
    ) -> None:
        app = _app()
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            _write_sticker_config(root, ["sticker_01"])
            _write_sticker_image(root, "sticker_01")
            config = load_chat_config(project_root=root)
            history = HistoryStore(config.storage)
            service = ChatService(
                config=config,
                history_store=history,
                memory_store=MemoryStore(config.storage),
                provider=SlowFakeProvider(delay_seconds=0.01),
                clock=FixedClock(),
                id_generator=SequentialIds(),
            )
            controller = ChatController(config=config, service=service)

            controller.show_window()
            self.assertTrue(controller.send_sticker("sticker_01"))
            app.processEvents()
            self.assertTrue(controller.is_busy)
            self.assertIn("user_ui_1", controller.window.chat_list.message_ids())
            self.assertTrue(
                _wait_until(
                    app,
                    lambda: not controller.is_busy and controller.active_worker_count == 0,
                )
            )
            messages = history.load_day(date(2026, 6, 4))
            user_messages = [message for message in messages if message.sender == ChatSender.USER]
            controller.window.hide()

            reloaded = ChatWindow(config=config)
            reloaded.set_messages(messages)
            app.processEvents()
            sticker_bubbles = reloaded.findChildren(QFrame, "chatStickerBubble")
            bubble_texts = [
                label.text()
                for label in reloaded.findChildren(QLabel, "chatBubbleText")
            ]

            self.assertEqual(len(user_messages), 1)
            self.assertEqual(user_messages[0].type, ChatMessageType.STICKER)
            self.assertEqual(user_messages[0].sticker_id, "sticker_01")
            self.assertEqual(user_messages[0].text, "贴纸1")
            self.assertFalse(any("[贴纸:" in text for text in bubble_texts))
            self.assertTrue(sticker_bubbles)
            reloaded.hide()

    def test_window_send_typing_history_and_hidden_worker_flow(self) -> None:
        app = _app()
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            config = load_chat_config(project_root=root)
            history = HistoryStore(config.storage)
            service = ChatService(
                config=config,
                history_store=history,
                memory_store=MemoryStore(config.storage),
                provider=SlowFakeProvider(),
                clock=FixedClock(),
                id_generator=SequentialIds(),
            )
            controller = ChatController(config=config, service=service)

            controller.show_window()
            self.assertTrue(controller.window.isVisible())

            controller.window.input_bar.set_text("你好")
            controller.window.input_bar.submit()
            app.processEvents()

            self.assertTrue(controller.is_busy)
            self.assertTrue(controller.window.chat_list.has_typing())
            self.assertIn("user_ui_1", controller.window.chat_list.message_ids())

            controller.window.close()
            app.processEvents()
            self.assertFalse(controller.window.isVisible())
            self.assertGreaterEqual(controller.active_worker_count, 1)

            self.assertTrue(
                _wait_until(
                    app,
                    lambda: not controller.is_busy and controller.active_worker_count == 0,
                )
            )

            messages = history.load_day(date(2026, 6, 4))
            user_messages = [message for message in messages if message.sender.value == "user"]
            self.assertEqual(len(messages), 2)
            self.assertEqual(len(user_messages), 1)
            self.assertEqual(user_messages[0].id, "user_ui_1")
            self.assertFalse(any(message.text == "正在输入..." for message in messages))

            controller.show_window()
            app.processEvents()
            self.assertIn(messages[0].id, controller.window.chat_list.message_ids())
            self.assertIn(messages[1].id, controller.window.chat_list.message_ids())
            self.assertFalse(controller.window.chat_list.has_typing())
            controller.window.hide()

    def test_controller_keeps_effects_pending_without_executor(self) -> None:
        app = _app()
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            config = load_chat_config(project_root=root)
            service = ChatService(
                config=config,
                history_store=HistoryStore(config.storage),
                memory_store=MemoryStore(config.storage),
                provider=ActionFakeProvider(delay_seconds=0.01),
                clock=FixedClock(),
                id_generator=SequentialIds(),
            )
            controller = ChatController(config=config, service=service)

            self.assertTrue(controller.send_text("想一下"))
            self.assertTrue(
                _wait_until(
                    app,
                    lambda: not controller.is_busy and controller.active_worker_count == 0,
                )
            )

            self.assertEqual(
                [effect.action_id for effect in controller.pending_effects],
                ["say_self"],
            )
            self.assertEqual(controller.recent_effect_results, ())
            self.assertTrue(controller.send_text("再想一下"))
            self.assertTrue(
                _wait_until(
                    app,
                    lambda: not controller.is_busy and controller.active_worker_count == 0,
                )
            )
            self.assertEqual(
                [effect.action_id for effect in controller.pending_effects],
                ["say_self"],
            )
            controller.window.hide()

    def test_controller_executes_effects_with_optional_executor(self) -> None:
        app = _app()
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            config = load_chat_config(project_root=root)
            executor = RecordingEffectExecutor(("performed",))
            service = ChatService(
                config=config,
                history_store=HistoryStore(config.storage),
                memory_store=MemoryStore(config.storage),
                provider=ActionFakeProvider(delay_seconds=0.01),
                clock=FixedClock(),
                id_generator=SequentialIds(),
            )
            controller = ChatController(
                config=config,
                service=service,
                effect_executor=executor,
            )

            self.assertTrue(controller.send_text("想一下"))
            self.assertTrue(
                _wait_until(
                    app,
                    lambda: not controller.is_busy and controller.active_worker_count == 0,
                )
            )

            self.assertEqual([effect.action_id for effect in executor.effects], ["say_self"])
            self.assertEqual(controller.pending_effects, ())
            self.assertEqual(controller.recent_effect_results, ("performed",))
            controller.window.hide()

    def test_controller_loads_latest_tail_and_scroll_top_loads_previous_day(
        self,
    ) -> None:
        app = _app()
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            _write_storage_limit(root, 12)
            config = load_chat_config(project_root=root)
            history = HistoryStore(config.storage)
            history.append_many(
                _messages_for_day("oldest", date(2026, 6, 1), 1)
                + _messages_for_day("prev", date(2026, 6, 2), 2)
                + _messages_for_day("latest", date(2026, 6, 4), 15)
            )
            service = ChatService(
                config=config,
                history_store=history,
                memory_store=MemoryStore(config.storage),
                provider=SlowFakeProvider(delay_seconds=0.01),
                clock=FixedClock(),
                id_generator=SequentialIds(),
            )
            controller = ChatController(config=config, service=service)

            controller.show_window()
            self.assertTrue(
                _wait_until(
                    app,
                    lambda: (
                        controller.window.chat_list.verticalScrollBar().maximum() > 0
                        and controller.window.chat_list.verticalScrollBar().value()
                        == controller.window.chat_list.verticalScrollBar().maximum()
                    ),
                )
            )
            loaded_ids = controller.window.chat_list.message_ids()
            self.assertNotIn("prev_0", loaded_ids)
            self.assertNotIn("latest_0", loaded_ids)
            self.assertEqual(loaded_ids[0], "latest_3")

            controller.window.chat_list.verticalScrollBar().setValue(0)
            self.assertTrue(
                _wait_until(
                    app,
                    lambda: "prev_0" in controller.window.chat_list.message_ids(),
                )
            )

            loaded_ids = controller.window.chat_list.message_ids()
            self.assertEqual(loaded_ids[:2], ["prev_0", "prev_1"])

            self.assertTrue(
                _wait_until(
                    app,
                    lambda: controller.window.chat_list.verticalScrollBar().value() > 0,
                )
            )
            controller.window.chat_list.verticalScrollBar().setValue(0)
            self.assertTrue(
                _wait_until(
                    app,
                    lambda: "oldest_0" in controller.window.chat_list.message_ids(),
                )
            )
            loaded_ids = controller.window.chat_list.message_ids()
            self.assertEqual(loaded_ids[0], "oldest_0")
            controller.window.hide()

    def test_chat_list_prepend_preserves_visual_scroll_position(self) -> None:
        app = _app()
        chat_list = ChatList()
        chat_list.resize(300, 220)
        chat_list.set_messages(_messages_for_day("new", date(2026, 6, 4), 16))
        chat_list.show()
        self.assertTrue(
            _wait_until(
                app,
                lambda: chat_list.verticalScrollBar().maximum() > 0
                and chat_list.verticalScrollBar().value()
                == chat_list.verticalScrollBar().maximum(),
            )
        )
        bar = chat_list.verticalScrollBar()
        bar.setValue(0)
        old_maximum = bar.maximum()

        inserted = chat_list.prepend_messages(
            _messages_for_day("old", date(2026, 6, 3), 4)
        )

        self.assertEqual(inserted, 4)
        self.assertTrue(
            _wait_until(
                app,
                lambda: bar.maximum() > old_maximum
                and bar.value() == bar.maximum() - old_maximum,
            )
        )
        chat_list.hide()

    def test_controller_does_not_repeat_older_lookup_when_history_has_no_previous_day(
        self,
    ) -> None:
        app = _app()
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            config = load_chat_config(project_root=root)
            history = CountingHistoryStore(config.storage)
            history.append_many(_messages_for_day("only", date(2026, 6, 4), 3))
            service = ChatService(
                config=config,
                history_store=history,
                memory_store=MemoryStore(config.storage),
                provider=SlowFakeProvider(delay_seconds=0.01),
                clock=FixedClock(),
                id_generator=SequentialIds(),
            )
            controller = ChatController(config=config, service=service)

            controller.show_window()
            app.processEvents()
            first_query_count = history.previous_day_queries
            controller.window.load_older_requested.emit()
            controller.window.load_older_requested.emit()
            controller.window.load_older_requested.emit()
            app.processEvents()

            self.assertEqual(first_query_count, 1)
            self.assertEqual(history.previous_day_queries, first_query_count)
            controller.window.hide()


def _write_sticker_config(
    root: Path,
    sticker_ids: list[str],
    *,
    paths: dict[str, str] | None = None,
) -> None:
    config_dir = root / "config" / "chat"
    config_dir.mkdir(parents=True)
    (config_dir / "pet_stickers.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "stickers": [
                    _sticker_config_item(
                        sticker_id,
                        f"贴纸{index}",
                        paths.get(sticker_id) if paths else None,
                    )
                    for index, sticker_id in enumerate(sticker_ids, start=1)
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def _sticker_config_item(
    sticker_id: str,
    label: str,
    path: str | None,
) -> dict[str, object]:
    item: dict[str, object] = {"id": sticker_id, "label": label}
    if path:
        item["metadata"] = {"path": path}
    return item


def _write_storage_limit(root: Path, limit: int) -> None:
    config_dir = root / "config" / "chat"
    config_dir.mkdir(parents=True)
    (config_dir / "storage.json").write_text(
        json.dumps({"schema_version": 1, "recent_history_limit": limit}),
        encoding="utf-8",
    )


def _messages_for_day(prefix: str, day: date, count: int) -> list[ChatMessage]:
    return [
        ChatMessage(
            id=f"{prefix}_{index}",
            timestamp=f"{day.isoformat()}T10:{index:02d}:00+00:00",
            sender=ChatSender.USER if index % 2 == 0 else ChatSender.LOLITH,
            text=f"{prefix} message {index} " + ("long text " * 24),
        )
        for index in range(count)
    ]


def _write_sticker_image(
    root: Path,
    sticker_id: str,
    *,
    area: str = "legacy",
) -> Path:
    if area == "pet":
        sticker_dir = root / "chat_data" / "pet_stickers"
    elif area == "user":
        sticker_dir = root / "chat_data" / "user_stickers"
    else:
        sticker_dir = root / "assets" / "sticker"
    sticker_dir.mkdir(parents=True)
    image = QImage(64, 64, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(QColor(240, 120, 180))
    path = sticker_dir / f"{sticker_id}.png"
    image.save(str(path))
    return path


if __name__ == "__main__":
    unittest.main()

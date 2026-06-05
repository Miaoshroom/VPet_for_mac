from __future__ import annotations

import json
import os
import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import patch

from core.chat.config import load_chat_config
from core.chat.context_builder import ContextBuilder, StaticChatPetContextProvider
from core.chat.history_store import HistoryStore
from core.chat.memory_commands import parse_explicit_memory_delete_command
from core.chat.memory_store import MemoryStore
from core.chat.models import (
    ChatMessage,
    ChatMessageStatus,
    ChatMessageType,
    ChatSender,
    EffectKind,
    PetContextSnapshot,
    ProviderResult,
)
from core.chat.providers.deepseek import DeepSeekChatProvider, build_deepseek_messages
from core.chat.providers.fake import FakeChatProvider
from core.chat.reply_parser import ReplyParser
from core.chat.service import ChatService


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


class StaticProvider:
    def __init__(self, content: dict[str, object]) -> None:
        self.content = dict(content)

    def complete(self, payload) -> ProviderResult:
        return ProviderResult(
            ok=True,
            content=json.dumps(self.content, ensure_ascii=False),
            provider="static",
        )


class RecordingProvider(StaticProvider):
    def __init__(self, content: dict[str, object]) -> None:
        super().__init__(content)
        self.payloads = []

    def complete(self, payload) -> ProviderResult:
        self.payloads.append(payload)
        return super().complete(payload)


class FailingProvider:
    def __init__(self, error: str = "provider_down") -> None:
        self.error = error

    def complete(self, payload) -> ProviderResult:
        return ProviderResult(
            ok=False,
            content="",
            provider="static",
            error=self.error,
        )


def _write_long_term_memory(root: Path, manual_notes: list[object]) -> None:
    memory_file = root / "chat_data" / "memory" / "long_term_memory.json"
    memory_file.parent.mkdir(parents=True)
    memory_file.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "updated_at": None,
                "relationship_summary": "保留关系摘要",
                "user_preferences": ["保留偏好"],
                "important_facts": ["保留事实"],
                "recurring_topics": [],
                "boundaries": ["保留边界"],
                "manual_notes": manual_notes,
                "daily_summaries": ["保留日总结"],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


class ChatOfflineTest(unittest.TestCase):
    def test_chat_core_does_not_import_pyqt(self) -> None:
        package_root = Path(__file__).resolve().parents[2] / "core" / "chat"
        for path in package_root.rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("import PyQt", text, path)
            self.assertNotIn("from PyQt", text, path)

    def test_chat_config_migrates_legacy_lolith_files_to_pet_names(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            config_dir = root / "config" / "chat"
            config_dir.mkdir(parents=True)
            legacy_persona = config_dir / "lolith_persona.json"
            legacy_stickers = config_dir / "lolith_stickers.json"
            legacy_persona.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "name": "萝莉斯",
                        "summary": "迁移后仍然保留角色名。",
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            legacy_stickers.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "stickers": [{"id": "legacy_smile", "label": "开心"}],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            config = load_chat_config(project_root=root)

            self.assertEqual(config.persona["name"], "萝莉斯")
            self.assertEqual(config.persona["summary"], "迁移后仍然保留角色名。")
            self.assertIn("legacy_smile", config.stickers)
            self.assertFalse(legacy_persona.exists())
            self.assertFalse(legacy_stickers.exists())
            self.assertTrue((config_dir / "pet_persona.json").exists())
            self.assertTrue((config_dir / "pet_stickers.json").exists())

    def test_chat_config_uses_pet_files_without_legacy_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            config_dir = root / "config" / "chat"
            config_dir.mkdir(parents=True)
            (config_dir / "pet_persona.json").write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "name": "萝莉斯",
                        "summary": "新主路径",
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            (config_dir / "pet_stickers.json").write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "stickers": [{"id": "pet_smile", "label": "开心"}],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            (config_dir / "lolith_persona.json").write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "name": "旧名",
                        "summary": "不应读取",
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            (config_dir / "lolith_stickers.json").write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "stickers": [{"id": "legacy_smile", "label": "旧贴纸"}],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            config = load_chat_config(project_root=root)

            self.assertEqual(config.persona["name"], "萝莉斯")
            self.assertEqual(config.persona["summary"], "新主路径")
            self.assertIn("pet_smile", config.stickers)
            self.assertNotIn("legacy_smile", config.stickers)
            self.assertTrue((config_dir / "lolith_persona.json").exists())
            self.assertTrue((config_dir / "lolith_stickers.json").exists())

    def test_default_ai_actions_match_checked_in_say_actions(self) -> None:
        repo_root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as tmp_dir:
            default_config = load_chat_config(project_root=Path(tmp_dir))
        checked_in_config = load_chat_config(project_root=repo_root)

        self.assertEqual(
            default_config.available_actions(),
            checked_in_config.available_actions(),
        )
        self.assertEqual(
            [action["id"] for action in default_config.available_actions()],
            ["say_self", "say_serious", "say_shining", "say_shy"],
        )

    def test_fake_provider_completes_one_turn_and_saves_history(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            config = load_chat_config(project_root=root)
            history = HistoryStore(config.storage)
            memory = MemoryStore(config.storage)
            service = ChatService(
                config=config,
                history_store=history,
                memory_store=memory,
                provider=FakeChatProvider(),
                clock=FixedClock(),
                id_generator=SequentialIds(),
            )

            result = service.send_user_message("你好")
            messages = history.load_day(date(2026, 6, 4))

        self.assertEqual(result.pet_message.sender, ChatSender.LOLITH)
        self.assertEqual(result.pet_message.text, "我在，这里先走离线回应。")
        self.assertEqual(result.effects, ())
        self.assertNotIn(
            result.user_message.id,
            [message["id"] for message in result.request_payload.recent_messages],
        )
        self.assertEqual([message.sender for message in messages], [ChatSender.USER, ChatSender.LOLITH])

    def test_memory_store_missing_file_returns_empty_prompt_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            store = MemoryStore(Path(tmp_dir) / "long_term_memory.json")
            summary = store.load()
            full = store.load_full()

        self.assertTrue(summary["read_only"])
        self.assertEqual(summary["relationship_summary"], "")
        self.assertEqual(summary["manual_notes"], [])
        self.assertEqual(full["relationship_summary"], "")
        self.assertEqual(full["manual_notes"], [])

    def test_memory_store_save_creates_backup_and_validates_schema(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            memory_file = Path(tmp_dir) / "memory" / "long_term_memory.json"
            memory_file.parent.mkdir(parents=True)
            memory_file.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "updated_at": None,
                        "relationship_summary": "旧摘要",
                        "user_preferences": [],
                        "important_facts": [],
                        "recurring_topics": [],
                        "boundaries": [],
                        "manual_notes": [],
                        "daily_summaries": [],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            store = MemoryStore(memory_file)

            backup = store.save_full(
                {
                    "schema_version": 1,
                    "updated_at": None,
                    "relationship_summary": "新摘要",
                    "user_preferences": ["短句"],
                    "important_facts": [],
                    "recurring_topics": [],
                    "boundaries": [],
                    "manual_notes": [],
                    "daily_summaries": [],
                },
                actor="user",
            )
            saved = json.loads(memory_file.read_text(encoding="utf-8"))

            with self.assertRaises(ValueError):
                store.save_full({"schema_version": 1, "user_profile": {"name": "bad"}})

            self.assertTrue(backup.exists())
            self.assertIn("旧摘要", backup.read_text(encoding="utf-8"))
        self.assertEqual(saved["relationship_summary"], "新摘要")
        self.assertIsNotNone(saved["updated_at"])

    def test_explicit_memory_command_writes_manual_note(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            config = load_chat_config(project_root=root)
            memory = MemoryStore(config.storage)
            provider = RecordingProvider(
                {
                    "schema_version": 1,
                    "text": "记下啦。",
                    "sticker_id": None,
                    "action_id": None,
                    "intent": "chat",
                    "state_request": None,
                }
            )
            service = ChatService(
                config=config,
                history_store=HistoryStore(config.storage),
                memory_store=memory,
                provider=provider,
                clock=FixedClock(),
                id_generator=SequentialIds(),
            )

            result = service.send_user_message("记住我喜欢冰美式")
            saved = memory.load_full()

        note = saved["manual_notes"][0]
        self.assertEqual(note["text"], "用户喜欢冰美式")
        self.assertEqual(note["source"], "user_explicit")
        self.assertEqual(note["source_message_id"], result.user_message.id)
        self.assertEqual(result.metadata["explicit_memory"]["status"], "saved")
        self.assertTrue(result.metadata["explicit_memory"]["backup_created"])
        self.assertEqual(result.user_message.metadata["explicit_memory"]["status"], "saved")
        self.assertIn("用户喜欢冰美式", result.request_payload.long_term_memory["manual_notes"])
        self.assertEqual(len(provider.payloads), 1)
        self.assertIn("用户喜欢冰美式", provider.payloads[0].long_term_memory["manual_notes"])

    def test_explicit_memory_colon_command_writes_manual_note(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            config = load_chat_config(project_root=root)
            memory = MemoryStore(config.storage)
            service = ChatService(
                config=config,
                history_store=HistoryStore(config.storage),
                memory_store=memory,
                provider=StaticProvider(
                    {
                        "schema_version": 1,
                        "text": "好，我会注意。",
                        "sticker_id": None,
                        "action_id": None,
                        "intent": "chat",
                        "state_request": None,
                    }
                ),
                clock=FixedClock(),
                id_generator=SequentialIds(),
            )

            service.send_user_message("帮我记住：我不喜欢被叫全名")
            saved = memory.load_full()

        self.assertEqual(saved["manual_notes"][0]["text"], "用户不喜欢被叫全名")
        self.assertEqual(saved["manual_notes"][0]["source"], "user_explicit")

    def test_normal_chat_does_not_write_manual_note(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            config = load_chat_config(project_root=root)
            memory = MemoryStore(config.storage)
            service = ChatService(
                config=config,
                history_store=HistoryStore(config.storage),
                memory_store=memory,
                provider=StaticProvider(
                    {
                        "schema_version": 1,
                        "text": "冰美式听起来不错。",
                        "sticker_id": None,
                        "action_id": None,
                        "intent": "chat",
                        "state_request": None,
                    }
                ),
                clock=FixedClock(),
                id_generator=SequentialIds(),
            )

            result = service.send_user_message("我喜欢冰美式")
            saved = memory.load_full()

        self.assertEqual(saved["manual_notes"], [])
        self.assertEqual(result.metadata, {})
        self.assertFalse(config.storage.long_term_memory_file.exists())

    def test_empty_explicit_memory_command_does_not_write(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            config = load_chat_config(project_root=root)
            memory = MemoryStore(config.storage)
            service = ChatService(
                config=config,
                history_store=HistoryStore(config.storage),
                memory_store=memory,
                provider=StaticProvider(
                    {
                        "schema_version": 1,
                        "text": "你再补一句内容我就知道该记什么啦。",
                        "sticker_id": None,
                        "action_id": None,
                        "intent": "chat",
                        "state_request": None,
                    }
                ),
                clock=FixedClock(),
                id_generator=SequentialIds(),
            )

            result = service.send_user_message("帮我记住：")
            saved = memory.load_full()

        self.assertEqual(saved["manual_notes"], [])
        self.assertEqual(result.metadata["explicit_memory"]["status"], "ignored_empty")
        self.assertFalse(config.storage.long_term_memory_file.exists())

    def test_duplicate_explicit_memory_command_is_not_duplicated(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            config = load_chat_config(project_root=root)
            memory = MemoryStore(config.storage)
            service = ChatService(
                config=config,
                history_store=HistoryStore(config.storage),
                memory_store=memory,
                provider=StaticProvider(
                    {
                        "schema_version": 1,
                        "text": "嗯嗯。",
                        "sticker_id": None,
                        "action_id": None,
                        "intent": "chat",
                        "state_request": None,
                    }
                ),
                clock=FixedClock(),
                id_generator=SequentialIds(),
            )

            first = service.send_user_message("记住我喜欢冰美式")
            second = service.send_user_message("记住 我喜欢冰美式。")
            saved = memory.load_full()

        self.assertEqual(first.metadata["explicit_memory"]["status"], "saved")
        self.assertEqual(second.metadata["explicit_memory"]["status"], "already_exists")
        self.assertEqual(len(saved["manual_notes"]), 1)
        self.assertEqual(saved["manual_notes"][0]["text"], "用户喜欢冰美式")

    def test_sensitive_explicit_memory_command_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            config = load_chat_config(project_root=root)
            memory = MemoryStore(config.storage)
            history = HistoryStore(config.storage)
            provider = RecordingProvider(
                {
                    "schema_version": 1,
                    "text": "provider 不应该收到这句。",
                    "sticker_id": None,
                    "action_id": None,
                    "intent": "chat",
                    "state_request": None,
                }
            )
            service = ChatService(
                config=config,
                history_store=history,
                memory_store=memory,
                provider=provider,
                clock=FixedClock(),
                id_generator=SequentialIds(),
            )

            result = service.send_user_message("记住 sk-test-secret")
            saved = memory.load_full()
            payload_text = json.dumps(result.request_payload.to_dict(), ensure_ascii=False)
            history_text = "\n".join(
                json.dumps(message.to_dict(), ensure_ascii=False)
                for message in history.load_day(date(2026, 6, 4))
            )

        self.assertEqual(saved["manual_notes"], [])
        self.assertEqual(result.metadata["explicit_memory"]["status"], "rejected_sensitive")
        self.assertIn("explicit_memory_sensitive_rejected", result.warnings)
        self.assertNotIn("sk-test-secret", json.dumps(result.metadata, ensure_ascii=False))
        self.assertEqual(provider.payloads, [])
        self.assertEqual(result.provider_result.provider, "local_memory")
        self.assertEqual(result.pet_message.text, "这个我不能帮你记，也不会发出去。")
        self.assertNotIn("sk-test-secret", payload_text)
        self.assertNotIn("sk-test-secret", history_text)
        self.assertFalse(config.storage.long_term_memory_file.exists())

    def test_explicit_memory_write_creates_backup_before_save(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            config = load_chat_config(project_root=root)
            config.storage.long_term_memory_file.parent.mkdir(parents=True)
            config.storage.long_term_memory_file.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "updated_at": None,
                        "relationship_summary": "旧关系摘要",
                        "user_preferences": [],
                        "important_facts": [],
                        "recurring_topics": [],
                        "boundaries": [],
                        "manual_notes": [],
                        "daily_summaries": [],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            memory = MemoryStore(config.storage)
            service = ChatService(
                config=config,
                history_store=HistoryStore(config.storage),
                memory_store=memory,
                provider=StaticProvider(
                    {
                        "schema_version": 1,
                        "text": "记好啦。",
                        "sticker_id": None,
                        "action_id": None,
                        "intent": "chat",
                        "state_request": None,
                    }
                ),
                clock=FixedClock(),
                id_generator=SequentialIds(),
            )

            service.send_user_message("记一下，我周五通常比较忙")
            backups = list((config.storage.memory_dir / "backups").glob("*.json"))
            backup_text = backups[0].read_text(encoding="utf-8") if backups else ""
            saved = memory.load_full()

        self.assertEqual(len(backups), 1)
        self.assertIn("旧关系摘要", backup_text)
        self.assertEqual(saved["relationship_summary"], "旧关系摘要")
        self.assertEqual(saved["manual_notes"][0]["text"], "用户周五通常比较忙")

    def test_provider_failure_after_explicit_memory_save_mentions_saved_note(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            config = load_chat_config(project_root=root)
            memory = MemoryStore(config.storage)
            service = ChatService(
                config=config,
                history_store=HistoryStore(config.storage),
                memory_store=memory,
                provider=FailingProvider(),
                clock=FixedClock(),
                id_generator=SequentialIds(),
            )

            result = service.send_user_message("以后记得我怕冷")
            saved = memory.load_full()

        self.assertFalse(result.provider_result.ok)
        self.assertEqual(saved["manual_notes"][0]["text"], "用户怕冷")
        self.assertEqual(result.pet_message.text, "我先记下来了，但刚刚有点没连上。")
        self.assertIn("provider_down", result.warnings)

    def test_explicit_memory_delete_command_proposes_candidate_without_deleting(self) -> None:
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
            memory = MemoryStore(config.storage)
            service = ChatService(
                config=config,
                history_store=HistoryStore(config.storage),
                memory_store=memory,
                provider=FailingProvider("should_not_call_provider"),
                clock=FixedClock(),
                id_generator=SequentialIds(),
            )

            result = service.send_user_message("忘记我喜欢冰美式")
            saved = memory.load_full()

        proposal = result.metadata["memory_delete_proposal"]
        self.assertEqual(proposal["status"], "needs_confirmation")
        self.assertEqual(proposal["candidates"][0]["id"], "note_ice")
        self.assertEqual(proposal["candidates"][0]["text"], "用户喜欢冰美式")
        self.assertEqual(saved["manual_notes"][0]["text"], "用户喜欢冰美式")
        self.assertEqual(saved["relationship_summary"], "保留关系摘要")
        self.assertEqual(result.provider_result.provider, "local_memory")
        self.assertIn("要删掉吗", result.pet_message.text)
        self.assertIn("用户喜欢冰美式", result.request_payload.long_term_memory["manual_notes"])

    def test_explicit_memory_delete_command_parses_supported_variants(self) -> None:
        cases = {
            "删掉关于冰美式的记忆": "冰美式",
            "不要记得我喜欢冰美式了": "用户喜欢冰美式",
            "把“我喜欢冰美式”从记忆里删掉": "用户喜欢冰美式",
            "清除这条记忆：我喜欢冰美式": "用户喜欢冰美式",
        }

        for message, expected_query in cases.items():
            with self.subTest(message=message):
                command = parse_explicit_memory_delete_command(message)
                self.assertIsNotNone(command)
                assert command is not None
                self.assertTrue(command.can_propose)
                self.assertEqual(command.query, expected_query)

    def test_memory_store_confirm_delete_removes_single_manual_note_only(self) -> None:
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
                    },
                    {
                        "id": "note_cold",
                        "created_at": "2026-06-04T10:01:00+00:00",
                        "text": "用户怕冷",
                        "source": "user_explicit",
                        "source_message_id": "u1",
                        "tags": [],
                    },
                ],
            )
            memory = MemoryStore(load_chat_config(project_root=root).storage)
            candidates = memory.find_manual_notes("我喜欢冰美式")

            delete_result = memory.delete_manual_notes([candidates[0].id], actor="user")
            saved = memory.load_full()

        self.assertEqual(delete_result.status, "deleted")
        self.assertEqual(delete_result.deleted_count, 1)
        self.assertEqual([note["text"] for note in saved["manual_notes"]], ["用户怕冷"])
        self.assertEqual(saved["relationship_summary"], "保留关系摘要")
        self.assertEqual(saved["user_preferences"], ["保留偏好"])
        self.assertEqual(saved["important_facts"], ["保留事实"])
        self.assertEqual(saved["boundaries"], ["保留边界"])
        self.assertEqual(saved["daily_summaries"], ["保留日总结"])

    def test_explicit_memory_delete_not_found_does_not_write_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            _write_long_term_memory(
                root,
                [
                    {
                        "id": "note_tea",
                        "created_at": "2026-06-04T10:00:00+00:00",
                        "text": "用户喜欢热茶",
                        "source": "user_explicit",
                        "source_message_id": "u0",
                        "tags": [],
                    }
                ],
            )
            config = load_chat_config(project_root=root)
            memory = MemoryStore(config.storage)
            service = ChatService(
                config=config,
                history_store=HistoryStore(config.storage),
                memory_store=memory,
                provider=FailingProvider("should_not_call_provider"),
                clock=FixedClock(),
                id_generator=SequentialIds(),
            )

            result = service.send_user_message("删掉关于冰美式的记忆")
            saved = memory.load_full()
            backups = list((config.storage.memory_dir / "backups").glob("*.json"))

        self.assertEqual(result.metadata["memory_delete_proposal"]["status"], "not_found")
        self.assertEqual(saved["manual_notes"][0]["text"], "用户喜欢热茶")
        self.assertEqual(backups, [])
        self.assertEqual(result.pet_message.text, "没找到相关记忆。")

    def test_explicit_memory_delete_multiple_candidates_does_not_delete_all(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            _write_long_term_memory(
                root,
                [
                    {
                        "id": "note_ice_like",
                        "created_at": "2026-06-04T10:00:00+00:00",
                        "text": "用户喜欢冰美式",
                        "source": "user_explicit",
                        "source_message_id": "u0",
                        "tags": [],
                    },
                    {
                        "id": "note_ice_busy",
                        "created_at": "2026-06-04T10:01:00+00:00",
                        "text": "用户周五会买冰美式",
                        "source": "user_explicit",
                        "source_message_id": "u1",
                        "tags": [],
                    },
                ],
            )
            config = load_chat_config(project_root=root)
            memory = MemoryStore(config.storage)
            service = ChatService(
                config=config,
                history_store=HistoryStore(config.storage),
                memory_store=memory,
                provider=FailingProvider("should_not_call_provider"),
                clock=FixedClock(),
                id_generator=SequentialIds(),
            )

            result = service.send_user_message("删掉关于冰美式的记忆")
            saved = memory.load_full()

        proposal = result.metadata["memory_delete_proposal"]
        self.assertEqual(proposal["status"], "multiple_candidates")
        self.assertEqual(len(proposal["candidates"]), 2)
        self.assertEqual(len(saved["manual_notes"]), 2)
        self.assertIn("几条相关记忆", result.pet_message.text)

    def test_clear_all_memory_delete_command_is_rejected_without_write(self) -> None:
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
            memory = MemoryStore(config.storage)
            service = ChatService(
                config=config,
                history_store=HistoryStore(config.storage),
                memory_store=memory,
                provider=FailingProvider("should_not_call_provider"),
                clock=FixedClock(),
                id_generator=SequentialIds(),
            )

            result = service.send_user_message("清空全部记忆")
            saved = memory.load_full()
            backups = list((config.storage.memory_dir / "backups").glob("*.json"))

        self.assertEqual(result.metadata["memory_delete_proposal"]["status"], "rejected_clear_all")
        self.assertEqual(saved["manual_notes"][0]["text"], "用户喜欢冰美式")
        self.assertEqual(backups, [])
        self.assertIn("太危险", result.pet_message.text)

    def test_protected_memory_delete_target_is_rejected_without_write(self) -> None:
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
            memory = MemoryStore(config.storage)
            service = ChatService(
                config=config,
                history_store=HistoryStore(config.storage),
                memory_store=memory,
                provider=FailingProvider("should_not_call_provider"),
                clock=FixedClock(),
                id_generator=SequentialIds(),
            )

            result = service.send_user_message("忘记 user_profile")
            saved = memory.load_full()
            backups = list((config.storage.memory_dir / "backups").glob("*.json"))

        self.assertEqual(
            result.metadata["memory_delete_proposal"]["status"],
            "rejected_protected_target",
        )
        self.assertEqual(saved["manual_notes"][0]["text"], "用户喜欢冰美式")
        self.assertEqual(backups, [])
        self.assertIn("不能在聊天里删", result.pet_message.text)

    def test_memory_store_delete_creates_backup_before_save(self) -> None:
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
            memory = MemoryStore(config.storage)

            result = memory.delete_manual_notes(["note_ice"], actor="user")
            backups = list((config.storage.memory_dir / "backups").glob("*.json"))
            backup_text = backups[0].read_text(encoding="utf-8") if backups else ""
            saved = memory.load_full()

        self.assertEqual(result.status, "deleted")
        self.assertEqual(len(backups), 1)
        self.assertIn("用户喜欢冰美式", backup_text)
        self.assertEqual(saved["manual_notes"], [])

    def test_context_builder_uses_prompt_safe_memory_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            config = load_chat_config(project_root=root)
            config.storage.long_term_memory_file.parent.mkdir(parents=True)
            config.storage.long_term_memory_file.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "updated_at": "2026-06-04T10:00:00+00:00",
                        "relationship_summary": "关系摘要" * 80,
                        "user_preferences": ["偏好" * 80],
                        "important_facts": [],
                        "recurring_topics": [],
                        "boundaries": [],
                        "manual_notes": [
                            {
                                "id": "manual_1",
                                "created_at": "2026-06-04T10:00:00+00:00",
                                "text": "用户喜欢冰美式" * 40,
                                "source": "user_explicit",
                                "source_message_id": "u0",
                                "tags": [],
                            },
                            "内部路径 /Users/neko/secret/chat_data/memory/backups/a.json",
                        ],
                        "daily_summaries": ["日总结" * 80 for _ in range(5)],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            user = ChatMessage(
                id="u1",
                timestamp="2026-06-04T10:00:00+00:00",
                sender=ChatSender.USER,
                text="早呀",
            )
            payload = ContextBuilder(
                config=config,
                history_store=HistoryStore(config.storage),
                memory_store=MemoryStore(config.storage),
            ).build(user_message=user, recent_messages=())
            messages = build_deepseek_messages(payload)
            deepseek_user_payload = json.loads(messages[1]["content"])

        memory = payload.long_term_memory
        self.assertTrue(memory["read_only"])
        self.assertIn("不等于 pet_persona", memory["scope_note"])
        self.assertLessEqual(len(memory["relationship_summary"]), 280)
        self.assertLessEqual(len(memory["manual_notes"][0]), 120)
        self.assertTrue(memory["manual_notes"][0].startswith("用户喜欢冰美式"))
        self.assertNotIn("manual_1", memory["manual_notes"][0])
        self.assertNotIn("source_message_id", memory["manual_notes"][0])
        self.assertEqual(len(memory["daily_summaries"]), 3)
        deepseek_text = json.dumps(deepseek_user_payload["long_term_memory"], ensure_ascii=False)
        self.assertNotIn("/Users/neko", deepseek_text)
        self.assertNotIn("chat_data/memory", deepseek_text)
        self.assertNotIn("backups", deepseek_text)

    def test_memory_store_cannot_override_user_profile_or_pet_persona(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            config_dir = root / "config" / "chat"
            config_dir.mkdir(parents=True)
            (config_dir / "user_profile.json").write_text(
                json.dumps(
                    {"schema_version": 1, "pet_call_user": "主人"},
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            (config_dir / "pet_persona.json").write_text(
                json.dumps(
                    {"schema_version": 1, "name": "萝莉斯", "summary": "原人格"},
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            config = load_chat_config(project_root=root)
            store = MemoryStore(config.storage)

            with self.assertRaises(ValueError):
                store.save_full(
                    {
                        "schema_version": 1,
                        "updated_at": None,
                        "relationship_summary": "",
                        "user_preferences": [],
                        "important_facts": [],
                        "recurring_topics": [],
                        "boundaries": [],
                        "manual_notes": [],
                        "daily_summaries": [],
                        "pet_persona": {"name": "覆盖"},
                    }
                )
            reloaded = load_chat_config(project_root=root)

        self.assertEqual(reloaded.user_profile["pet_call_user"], "主人")
        self.assertEqual(reloaded.persona["name"], "萝莉斯")
        self.assertFalse(config.storage.long_term_memory_file.exists())

    def test_chat_service_saves_user_sticker_as_sticker_message(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            config_dir = root / "config" / "chat"
            config_dir.mkdir(parents=True)
            (config_dir / "pet_stickers.json").write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "stickers": [
                            {
                                "id": "sticker_01",
                                "label": "开心",
                                "metadata": {
                                    "tags": ["happy", "smile"],
                                    "source": "bundled",
                                },
                            }
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            config = load_chat_config(project_root=root)
            history = HistoryStore(config.storage)
            service = ChatService(
                config=config,
                history_store=history,
                memory_store=MemoryStore(config.storage),
                provider=StaticProvider(
                    {
                        "schema_version": 1,
                        "text": "收到这个表情啦。",
                        "sticker_id": None,
                        "action_id": None,
                        "intent": "chat",
                        "state_request": None,
                    }
                ),
                clock=FixedClock(),
                id_generator=SequentialIds(),
            )

            result = service.send_user_sticker(
                "sticker_01",
                label="开心",
                client_message_id="user_ui_sticker_1",
            )
            messages = history.load_day(date(2026, 6, 4))
            raw_history = next(config.storage.history_dir.glob("*.jsonl")).read_text(
                encoding="utf-8"
            )

        self.assertEqual(messages[0].sender, ChatSender.USER)
        self.assertEqual(messages[0].type, ChatMessageType.STICKER)
        self.assertEqual(messages[0].sticker_id, "sticker_01")
        self.assertEqual(messages[0].text, "开心")
        self.assertEqual(messages[0].metadata["label"], "开心")
        self.assertEqual(messages[0].metadata["tags"], ["happy", "smile"])
        self.assertIn('"type": "sticker"', raw_history)
        self.assertIn('"sticker_id": "sticker_01"', raw_history)
        self.assertNotIn("[贴纸:sticker_01]", raw_history)
        self.assertEqual(result.request_payload.user_message["type"], "sticker")
        self.assertEqual(result.request_payload.user_message["sticker_id"], "sticker_01")
        self.assertEqual(result.request_payload.user_message["label"], "开心")
        self.assertEqual(result.request_payload.user_message["tags"], ["happy", "smile"])
        self.assertEqual(result.effects, ())

    def test_available_stickers_keeps_paths_out_of_ai_payload(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            config_dir = root / "config" / "chat"
            config_dir.mkdir(parents=True)
            (config_dir / "storage.json").write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "pet_sticker_dir": "chat_data/pet_stickers",
                        "user_sticker_dir": "chat_data/user_stickers",
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            (config_dir / "pet_stickers.json").write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "stickers": [
                            {
                                "id": "wave",
                                "label": "挥手",
                                "metadata": {
                                    "path": "/private/tmp/wave.png",
                                    "image_path": "chat_data/pet_stickers/wave.png",
                                    "tags": ["hello"],
                                    "scenarios": ["打招呼"],
                                },
                            }
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            config = load_chat_config(project_root=root)
            user = ChatMessage(
                id="u1",
                timestamp="2026-06-04T10:00:00+00:00",
                sender=ChatSender.USER,
                text="早呀",
            )
            payload = ContextBuilder(
                config=config,
                history_store=HistoryStore(config.storage),
                memory_store=MemoryStore(config.storage),
            ).build(user_message=user, recent_messages=())
            messages = build_deepseek_messages(payload)

        self.assertEqual(config.storage.pet_stickers_dir, root / "chat_data" / "pet_stickers")
        self.assertEqual(config.storage.user_stickers_dir, root / "chat_data" / "user_stickers")
        self.assertEqual(
            payload.available_stickers,
            ({"id": "wave", "label": "挥手", "tags": ["hello"], "scenarios": ["打招呼"]},),
        )
        payload_text = json.dumps(payload.to_dict(), ensure_ascii=False)
        deepseek_user_payload = json.loads(messages[1]["content"])
        deepseek_text = json.dumps(deepseek_user_payload["available_stickers"], ensure_ascii=False)
        self.assertNotIn("path", payload_text)
        self.assertNotIn("image_path", payload_text)
        self.assertNotIn("/private/tmp", payload_text)
        self.assertNotIn("chat_data/pet_stickers", deepseek_text)

    def test_history_store_reads_legacy_sticker_text_as_sticker_message(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            history_dir = Path(tmp_dir)
            legacy = {
                "schema_version": 1,
                "id": "legacy_sticker",
                "timestamp": "2026-06-04T09:00:00+00:00",
                "sender": "user",
                "type": "text",
                "text": "[贴纸:sticker_01] 开心",
                "sticker_id": None,
                "metadata": {"sticker_id": "sticker_01"},
            }
            (history_dir / "2026-06-04.jsonl").write_text(
                json.dumps(legacy, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )

            messages = HistoryStore(history_dir).load_day(date(2026, 6, 4))

        self.assertEqual(messages[0].type, ChatMessageType.STICKER)
        self.assertEqual(messages[0].sticker_id, "sticker_01")
        self.assertEqual(messages[0].text, "开心")
        self.assertTrue(messages[0].metadata["legacy_text_format"])

    def test_ai_settings_new_fields_are_loaded_with_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            config_dir = root / "config" / "chat"
            config_dir.mkdir(parents=True)
            (config_dir / "ai_settings.json").write_text(
                json.dumps(
                    {
                        "provider": "deepseek",
                        "model": "deepseek-reasoner",
                        "api_key_env": "UNIT_TEST_DEEPSEEK_KEY",
                        "api_key_file": "config/chat/api_key.local.json",
                        "timeout_seconds": 12,
                        "retries": 2,
                        "temperature": 0.3,
                        "max_tokens": 256,
                        "api_key": "should_not_be_loaded",
                    }
                ),
                encoding="utf-8",
            )
            config = load_chat_config(project_root=root)

        self.assertEqual(config.ai_settings["provider"], "deepseek")
        self.assertEqual(config.ai_settings["model"], "deepseek-reasoner")
        self.assertEqual(config.ai_settings["api_key_env"], "UNIT_TEST_DEEPSEEK_KEY")
        self.assertEqual(config.ai_settings["api_key_file"], "config/chat/api_key.local.json")
        self.assertEqual(config.ai_settings["timeout_seconds"], 12)
        self.assertEqual(config.ai_settings["retries"], 2)
        self.assertEqual(config.ai_settings["temperature"], 0.3)
        self.assertEqual(config.ai_settings["max_tokens"], 256)
        self.assertNotIn("api_key", config.ai_settings)
        self.assertEqual(config.allowed_state_requests, ("use_item",))

    def test_user_profile_new_fields_are_loaded_and_clipped_for_request_payload(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            config_dir = root / "config" / "chat"
            config_dir.mkdir(parents=True)
            (config_dir / "user_profile.json").write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "profile_id": "unit_test_user",
                        "display_name": "测试用户",
                        "preferred_name": "小测试",
                        "preferred_pronouns": "",
                        "pet_call_user": "主人",
                        "avatar": {
                            "kind": "image",
                            "label": "本地头像",
                            "path": "/private/tmp/avatar.png",
                        },
                        "relationship_to_pet": "桌宠的主人",
                        "chat_preferences": {
                            "reply_length": "两句以内",
                            "comfort_style": "先陪着，再轻轻提醒",
                            "teasing_level": "轻微",
                            "advice_style": "只给一个下一步",
                            "emoji_or_sticker_preference": "克制使用",
                        },
                        "boundaries": {
                            "avoid_topics": ["真实隐私"],
                            "avoid_tone": ["客服腔"],
                            "never_call_user": ["用户大人"],
                        },
                        "profile_editing": {
                            "ai_may_modify": True,
                            "source_of_truth": "human_edit_only",
                            "instruction": "资料只读",
                        },
                        "notes": ["很长的备注" * 40, "人工短备注"],
                        "history_path": "/private/tmp/history",
                        "api_key": "BAD_TOKEN",
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            config = load_chat_config(project_root=root)
            user = ChatMessage(
                id="u1",
                timestamp="2026-06-04T10:00:00+00:00",
                sender=ChatSender.USER,
                text="早呀",
            )
            payload = ContextBuilder(
                config=config,
                history_store=HistoryStore(config.storage),
                memory_store=MemoryStore(config.storage),
            ).build(user_message=user, recent_messages=())

        self.assertEqual(config.user_profile["profile_id"], "unit_test_user")
        self.assertEqual(config.user_profile["history_path"], "/private/tmp/history")
        self.assertEqual(payload.user_profile["pet_call_user"], "主人")
        self.assertEqual(payload.user_profile["chat_preferences"]["reply_length"], "两句以内")
        self.assertEqual(payload.user_profile["boundaries"]["avoid_topics"], ["真实隐私"])
        self.assertEqual(payload.user_profile["boundaries"]["never_call_user"], ["用户大人"])
        self.assertFalse(payload.user_profile["profile_editing"]["ai_may_modify"])
        self.assertEqual(payload.user_profile["avatar"]["kind"], "image")
        self.assertNotIn("path", payload.user_profile["avatar"])
        self.assertLessEqual(len(payload.user_profile["notes"][0]), 120)
        payload_text = json.dumps(payload.to_dict(), ensure_ascii=False)
        self.assertNotIn("history_path", payload_text)
        self.assertNotIn("/private/tmp", payload_text)
        self.assertNotIn("BAD_TOKEN", payload_text)

    def test_user_profile_missing_fields_use_safe_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            config_dir = root / "config" / "chat"
            config_dir.mkdir(parents=True)
            (config_dir / "user_profile.json").write_text(
                json.dumps({"schema_version": 1}, ensure_ascii=False),
                encoding="utf-8",
            )
            config = load_chat_config(project_root=root)
            user = ChatMessage(
                id="u1",
                timestamp="2026-06-04T10:00:00+00:00",
                sender=ChatSender.USER,
                text="早呀",
            )
            payload = ContextBuilder(
                config=config,
                history_store=HistoryStore(config.storage),
                memory_store=MemoryStore(config.storage),
            ).build(user_message=user, recent_messages=())
            messages = build_deepseek_messages(payload)

        self.assertEqual(payload.user_profile["pet_call_user"], "主人")
        self.assertEqual(payload.user_profile["relationship_to_pet"], "桌宠的主人")
        self.assertIn("reply_length", payload.user_profile["chat_preferences"])
        self.assertIn("客服腔", payload.user_profile["boundaries"]["avoid_tone"])
        user_payload = json.loads(messages[1]["content"])
        self.assertEqual(user_payload["user_profile"]["pet_call_user"], "主人")

    def test_history_store_appends_failed_messages_and_loads_recent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            history = HistoryStore(Path(tmp_dir))
            history.append(
                ChatMessage(
                    id="u1",
                    timestamp="2026-06-03T10:00:00+00:00",
                    sender=ChatSender.USER,
                    text="hello",
                )
            )
            history.append(
                ChatMessage(
                    id="l1",
                    timestamp="2026-06-04T10:00:00+00:00",
                    sender=ChatSender.LOLITH,
                    type=ChatMessageType.SYSTEM_NOTICE,
                    text="failed",
                    status=ChatMessageStatus.FAILED,
                )
            )
            day_messages = history.load_day("2026-06-04")
            recent = history.load_recent(days=2, limit=1, today=date(2026, 6, 4))

        self.assertEqual(day_messages[0].status, ChatMessageStatus.FAILED)
        self.assertEqual(day_messages[0].type, ChatMessageType.SYSTEM_NOTICE)
        self.assertEqual(recent[0].id, "l1")

    def test_history_store_finds_available_days_and_loads_day_tail(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            history = HistoryStore(Path(tmp_dir))
            messages = [
                ChatMessage(
                    id="old",
                    timestamp="2026-06-02T10:00:00+00:00",
                    sender=ChatSender.USER,
                    text="old",
                )
            ]
            messages.extend(
                ChatMessage(
                    id=f"new_{index}",
                    timestamp=f"2026-06-04T10:00:0{index}+00:00",
                    sender=ChatSender.LOLITH,
                    text=f"new {index}",
                )
                for index in range(3)
            )
            history.append_many(messages)
            (Path(tmp_dir) / "not-a-date.jsonl").write_text("ignored\n", encoding="utf-8")

            latest = history.latest_day()
            previous = history.previous_day_before(date(2026, 6, 4))
            tail = history.load_day(date(2026, 6, 4), limit=2)

        self.assertEqual(latest, date(2026, 6, 4))
        self.assertEqual(previous, date(2026, 6, 2))
        self.assertEqual([message.id for message in tail], ["new_1", "new_2"])

    def test_deepseek_prompt_includes_full_json_contract(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            config = load_chat_config(project_root=Path(tmp_dir))
            user = ChatMessage(
                id="u1",
                timestamp="2026-06-04T10:00:00+00:00",
                sender=ChatSender.USER,
                text="早呀",
            )
            payload = ContextBuilder(
                config=config,
                history_store=HistoryStore(config.storage),
                memory_store=MemoryStore(config.storage),
            ).build(user_message=user, recent_messages=())
            messages = build_deepseek_messages(payload)

        system_payload = json.loads(messages[0]["content"])
        user_payload = json.loads(messages[1]["content"])
        contract = system_payload["json_contract"]
        required_fields = {
            "schema_version",
            "text",
            "sticker_id",
            "action_id",
            "intent",
            "state_request",
        }

        self.assertEqual(set(contract["required_fields"]), required_fields)
        self.assertEqual(contract["fixed_values"]["schema_version"], 1)
        self.assertIsNone(contract["defaults"]["sticker_id"])
        self.assertEqual(contract["defaults"]["action_id"], "say_self")
        self.assertIsNone(contract["defaults"]["state_request"])
        self.assertIn("不客服", contract["style"]["tone"])
        self.assertIn("any", contract["state_boundaries"])
        self.assertIn("use_any_state", contract["forbidden"])
        self.assertIn("modify_user_profile", system_payload["forbidden_requests"])
        self.assertIn("modify_user_profile", contract["forbidden"])
        self.assertIn("modify_memory", system_payload["forbidden_requests"])
        self.assertIn("modify_memory", contract["forbidden"])
        self.assertIn("user_profile_policy", system_payload)
        self.assertIn("memory_policy", system_payload)
        self.assertIn("pet_call_user", system_payload["user_profile_policy"]["address_user_as"])
        self.assertIn("明确说", system_payload["memory_policy"]["explicit_user_memory"])
        self.assertIn("长期记忆只读", user_payload["response_contract_reminder"]["memory_usage"])
        self.assertEqual(
            set(user_payload["response_contract_reminder"]["must_include_all_fields"]),
            required_fields,
        )
        self.assertEqual(
            user_payload["response_contract_reminder"]["default_null_fields"],
            ["sticker_id", "state_request"],
        )
        self.assertIn(
            "user_profile",
            user_payload["response_contract_reminder"]["user_profile_usage"],
        )

    def test_message_type_supports_next_ui_phase_values_and_legacy_mapping(self) -> None:
        self.assertEqual(ChatMessageType.TEXT.value, "text")
        self.assertEqual(ChatMessageType.STICKER.value, "sticker")
        self.assertEqual(ChatMessageType.FILE.value, "file")
        self.assertEqual(ChatMessageType.MIXED.value, "mixed")
        self.assertEqual(ChatMessageType.SYSTEM_NOTICE.value, "system_notice")
        self.assertEqual(
            ChatMessage.from_dict(
                {
                    "id": "legacy",
                    "timestamp": "2026-06-04T10:00:00+00:00",
                    "sender": "lolith",
                    "type": "error",
                    "text": "failed",
                }
            ).type,
            ChatMessageType.SYSTEM_NOTICE,
        )

    def test_reply_parser_handles_json_code_block_and_invalid_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            parser = ReplyParser(load_chat_config(project_root=Path(tmp_dir)))
            legal = parser.parse(
                json.dumps(
                    {
                        "schema_version": 1,
                        "text": "好呀",
                        "sticker_id": "sticker_01",
                        "action_id": None,
                        "intent": "chat",
                        "state_request": None,
                    },
                    ensure_ascii=False,
                )
            )
            fenced = parser.parse(
                """```json
{"schema_version":1,"text":"收到","sticker_id":null,"action_id":null,"intent":"chat","state_request":null}
```"""
            )
            invalid = parser.parse("not json")
            missing_schema = parser.parse(
                json.dumps(
                    {
                        "text": "好呀",
                        "sticker_id": None,
                        "action_id": None,
                        "intent": "chat",
                        "state_request": None,
                    },
                    ensure_ascii=False,
                )
            )

        self.assertEqual(legal.reply.sticker_id, "sticker_01")
        self.assertEqual(legal.effects, ())
        self.assertEqual(fenced.reply.text, "收到")
        self.assertIn("invalid_json_fallback", invalid.warnings)
        self.assertEqual(missing_schema.reply.text, "好呀")
        self.assertEqual(missing_schema.effects, ())
        self.assertIn("schema_version_missing", missing_schema.warnings)

    def test_reply_parser_rejects_privileged_requests_and_bad_ids(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            parser = ReplyParser(load_chat_config(project_root=Path(tmp_dir)))
            result = parser.parse(
                json.dumps(
                    {
                        "schema_version": 1,
                        "text": "我试试看",
                        "sticker_id": "missing_sticker",
                        "action_id": "missing_action",
                        "intent": "chat",
                        "state_request": {"type": "delete_memory"},
                        "delete_memory": True,
                        "memory_update": {"manual_notes": ["不应保存"]},
                        "modify_memory": True,
                        "visual_state": "any",
                    },
                    ensure_ascii=False,
                )
            )
            blocked_action = parser.parse(
                json.dumps(
                    {
                        "schema_version": 1,
                        "text": "回默认",
                        "sticker_id": None,
                        "action_id": "default",
                        "intent": "action_request",
                        "state_request": None,
                    },
                    ensure_ascii=False,
                )
            )

        self.assertIsNone(result.reply.sticker_id)
        self.assertIsNone(result.reply.action_id)
        self.assertIsNone(result.reply.state_request)
        self.assertEqual(result.effects, ())
        self.assertTrue(
            any(
                warning.startswith("safety_warning:forbidden_request_rejected")
                for warning in result.warnings
            )
        )
        self.assertIn("invalid_sticker_id_dropped:missing_sticker", result.warnings)
        self.assertIn("invalid_action_id_dropped:missing_action", result.warnings)
        self.assertIn(
            "safety_warning:forbidden_request_rejected:memory_update",
            result.warnings,
        )
        self.assertIn(
            "safety_warning:forbidden_request_rejected:delete_memory",
            result.warnings,
        )
        self.assertIn(
            "safety_warning:forbidden_request_rejected:modify_memory",
            result.warnings,
        )
        self.assertIsNone(blocked_action.reply.action_id)
        self.assertIn("invalid_action_id_dropped:default", blocked_action.warnings)

    def test_use_item_becomes_effect_but_sticker_does_not(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            parser = ReplyParser(load_chat_config(project_root=Path(tmp_dir)))
            result = parser.parse(
                json.dumps(
                    {
                        "schema_version": 1,
                        "text": "给你拿个饭团。",
                        "sticker_id": "sticker_01",
                        "action_id": None,
                        "intent": "use_item_request",
                        "state_request": {"type": "use_item", "item_id": "rice_ball"},
                    },
                    ensure_ascii=False,
                )
            )

        self.assertEqual(result.reply.sticker_id, "sticker_01")
        self.assertEqual(len(result.effects), 1)
        self.assertEqual(result.effects[0].kind, EffectKind.USE_ITEM)
        self.assertEqual(result.effects[0].item_id, "rice_ball")
        self.assertIsNone(result.effects[0].action_id)

    def test_chat_service_rate_limits_sticker_from_recent_ai_usage(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            config = load_chat_config(project_root=root)
            history = HistoryStore(config.storage)
            memory = MemoryStore(config.storage)
            context_builder = ContextBuilder(
                config=config,
                history_store=history,
                memory_store=memory,
                pet_context_provider=StaticChatPetContextProvider(
                    PetContextSnapshot(
                        recent_ai_usage={"last_sticker_turns_ago": 1}
                    )
                ),
            )
            service = ChatService(
                config=config,
                history_store=history,
                memory_store=memory,
                context_builder=context_builder,
                provider=StaticProvider(
                    {
                        "schema_version": 1,
                        "text": "",
                        "sticker_id": "sticker_01",
                        "action_id": None,
                        "intent": "chat",
                        "state_request": None,
                    }
                ),
                clock=FixedClock(),
                id_generator=SequentialIds(),
            )

            result = service.send_user_message("刚刚那个贴纸挺可爱")
            messages = history.load_day(date(2026, 6, 4))

        self.assertIsNone(result.pet_message.sticker_id)
        self.assertEqual(result.pet_message.type, ChatMessageType.TEXT)
        self.assertEqual(result.pet_message.text, "我先用文字陪你一下。")
        self.assertEqual(result.effects, ())
        self.assertIn("recent_ai_usage:sticker_rate_limited", result.warnings)
        self.assertIn(
            "empty_text_after_sticker_rate_limit_fallback",
            result.warnings,
        )
        self.assertIsNone(messages[-1].sticker_id)
        self.assertEqual(messages[-1].text, "我先用文字陪你一下。")

    def test_context_builder_marks_recent_lolith_sticker_usage(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            config = load_chat_config(project_root=root)
            history = HistoryStore(config.storage)
            memory = MemoryStore(config.storage)
            history.append_many(
                (
                    ChatMessage(
                        id="u1",
                        timestamp="2026-06-04T09:00:00+00:00",
                        sender=ChatSender.USER,
                        text="早呀",
                    ),
                    ChatMessage(
                        id="l1",
                        timestamp="2026-06-04T09:00:01+00:00",
                        sender=ChatSender.LOLITH,
                        type=ChatMessageType.MIXED,
                        text="早呀",
                        sticker_id="sticker_01",
                    ),
                )
            )
            user = ChatMessage(
                id="u2",
                timestamp="2026-06-04T09:01:00+00:00",
                sender=ChatSender.USER,
                text="再聊会",
            )
            payload = ContextBuilder(
                config=config,
                history_store=history,
                memory_store=memory,
            ).build(user_message=user, recent_messages=history.load_day(date(2026, 6, 4)))

        self.assertTrue(payload.recent_ai_usage["sticker_used_in_recent_lolith_turns"])
        self.assertEqual(payload.recent_ai_usage["last_sticker_turns_ago"], 1)
        self.assertEqual(payload.recent_ai_usage["recent_lolith_sticker_count_2"], 1)

    def test_privileged_request_mixed_with_valid_effects_blocks_all_effects(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            parser = ReplyParser(load_chat_config(project_root=Path(tmp_dir)))
            result = parser.parse(
                json.dumps(
                    {
                        "schema_version": 1,
                        "text": "我可以先陪你说说话。",
                        "sticker_id": "sticker_01",
                        "action_id": "say_self",
                        "intent": "use_item_request",
                        "state_request": {
                            "type": "use_item",
                            "item_id": "rice_ball",
                            "modify_api_settings": True,
                        },
                    },
                    ensure_ascii=False,
                )
            )

        self.assertEqual(result.reply.text, "我可以先陪你说说话。")
        self.assertEqual(result.reply.sticker_id, "sticker_01")
        self.assertIsNone(result.reply.action_id)
        self.assertIsNone(result.reply.state_request)
        self.assertEqual(result.effects, ())
        self.assertIn("safety_warning:effects_blocked", result.warnings)

    def test_any_state_is_normalized_out_of_context_and_parser_result(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            config = load_chat_config(project_root=Path(tmp_dir))
            history = HistoryStore(config.storage)
            memory = MemoryStore(config.storage)
            provider = StaticChatPetContextProvider(
                PetContextSnapshot(
                    pet_state={"mood": 80},
                    runtime_state={"visual_state": "any"},
                    visual_state="any",
                )
            )
            builder = ContextBuilder(
                config=config,
                history_store=history,
                memory_store=memory,
                pet_context_provider=provider,
            )
            user = ChatMessage(
                id="u1",
                timestamp="2026-06-04T10:00:00+00:00",
                sender=ChatSender.USER,
                text="状态看起来怎样",
            )
            payload = builder.build(user_message=user, recent_messages=())
            parsed = ReplyParser(config).parse(
                json.dumps(
                    {
                        "schema_version": 1,
                        "text": "不直接改状态。",
                        "state_request": {
                            "type": "set_visual_state",
                            "visual_state": "any",
                        },
                    },
                    ensure_ascii=False,
                )
            )

        self.assertEqual(payload.visual_state, "normal")
        self.assertEqual(payload.runtime_state["visual_state"], "normal")
        self.assertEqual(payload.allowed_state_requests, ("use_item",))
        self.assertIn("now", payload.time_context)
        self.assertIn("date", payload.time_context)
        self.assertIn("timezone", payload.time_context)
        payload_text = json.dumps(payload.to_dict(), ensure_ascii=False)
        self.assertNotIn('"visual_state": "any"', payload_text)
        self.assertIn("use_any_state", payload.forbidden_requests)
        self.assertIsNone(parsed.reply.state_request)
        self.assertEqual(parsed.effects, ())

    def test_deepseek_provider_without_key_fails_safely(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            config_dir = root / "config" / "chat"
            config_dir.mkdir(parents=True)
            (config_dir / "ai_settings.json").write_text(
                json.dumps(
                    {
                        "provider": "deepseek",
                        "api_key_env": "UNIT_TEST_MISSING_DEEPSEEK_KEY",
                    }
                ),
                encoding="utf-8",
            )
            config = load_chat_config(project_root=root)
            user = ChatMessage(
                id="u1",
                timestamp="2026-06-04T10:00:00+00:00",
                sender=ChatSender.USER,
                text="你好",
            )
            payload = ContextBuilder(
                config=config,
                history_store=HistoryStore(config.storage),
                memory_store=MemoryStore(config.storage),
            ).build(user_message=user, recent_messages=())
            with patch.dict(os.environ, {}, clear=True):
                result = DeepSeekChatProvider(config).complete(payload)

        self.assertFalse(result.ok)
        self.assertEqual(result.provider, "deepseek")
        self.assertEqual(result.error, "missing_api_key")

    def test_deepseek_key_only_comes_from_environment_and_not_history(self) -> None:
        captured: dict[str, object] = {}

        def fake_post(url: str, headers: dict[str, str], body: bytes, timeout: float) -> tuple[int, str]:
            captured["headers"] = dict(headers)
            captured["body"] = body.decode("utf-8")
            captured["timeout"] = timeout
            return (
                200,
                json.dumps(
                    {
                        "choices": [
                            {
                                "message": {
                                    "content": json.dumps(
                                        {
                                            "schema_version": 1,
                                            "text": "收到",
                                            "sticker_id": None,
                                            "action_id": None,
                                            "intent": "chat",
                                            "state_request": None,
                                        },
                                        ensure_ascii=False,
                                    )
                                }
                            }
                        ]
                    }
                ),
            )

        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            config_dir = root / "config" / "chat"
            config_dir.mkdir(parents=True)
            (config_dir / "ai_settings.json").write_text(
                json.dumps(
                    {
                        "provider": "deepseek",
                        "api_key_env": "UNIT_TEST_DEEPSEEK_KEY",
                        "api_key_file": "config/chat/api_key.local.json",
                        "api_key": "BAD_TOKEN",
                        "timeout_seconds": 9,
                    }
                ),
                encoding="utf-8",
            )
            (config_dir / "api_key.local.json").write_text(
                json.dumps({"deepseek_api_key": "LOCAL_FILE_TOKEN"}),
                encoding="utf-8",
            )
            config = load_chat_config(project_root=root)
            history = HistoryStore(config.storage)
            service = ChatService(
                config=config,
                history_store=history,
                memory_store=MemoryStore(config.storage),
                provider=DeepSeekChatProvider(config, http_post=fake_post),
                clock=FixedClock(),
                id_generator=SequentialIds(),
            )
            with patch.dict(os.environ, {"UNIT_TEST_DEEPSEEK_KEY": "SECRET_TOKEN"}, clear=True):
                result = service.send_user_message("你好")
            history_text = "\n".join(
                json.dumps(message.to_dict(), ensure_ascii=False)
                for message in history.load_day(date(2026, 6, 4))
            )

        self.assertTrue(result.provider_result.ok)
        self.assertEqual(captured["headers"]["Authorization"], "Bearer SECRET_TOKEN")
        self.assertEqual(captured["timeout"], 9.0)
        self.assertNotIn("SECRET_TOKEN", str(captured["body"]))
        self.assertNotIn("LOCAL_FILE_TOKEN", str(captured["body"]))
        self.assertNotIn("BAD_TOKEN", str(captured["body"]))
        self.assertNotIn("SECRET_TOKEN", json.dumps(result.request_payload.to_dict(), ensure_ascii=False))
        self.assertNotIn("SECRET_TOKEN", history_text)
        self.assertNotIn("LOCAL_FILE_TOKEN", history_text)
        self.assertNotIn("BAD_TOKEN", history_text)

    def test_deepseek_key_can_come_from_ignored_local_json(self) -> None:
        captured: dict[str, object] = {}

        def fake_post(url: str, headers: dict[str, str], body: bytes, timeout: float) -> tuple[int, str]:
            captured["headers"] = dict(headers)
            captured["body"] = body.decode("utf-8")
            return (
                200,
                json.dumps(
                    {
                        "choices": [
                            {
                                "message": {
                                    "content": json.dumps(
                                        {
                                            "schema_version": 1,
                                            "text": "在。",
                                            "sticker_id": None,
                                            "action_id": "say_self",
                                            "intent": "action_request",
                                            "state_request": None,
                                        },
                                        ensure_ascii=False,
                                    )
                                }
                            }
                        ]
                    }
                ),
            )

        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            config_dir = root / "config" / "chat"
            config_dir.mkdir(parents=True)
            (config_dir / "ai_settings.json").write_text(
                json.dumps(
                    {
                        "provider": "deepseek",
                        "api_key_env": "UNIT_TEST_MISSING_DEEPSEEK_KEY",
                        "api_key_file": "config/chat/api_key.local.json",
                    }
                ),
                encoding="utf-8",
            )
            (config_dir / "api_key.local.json").write_text(
                json.dumps({"deepseek_api_key": "LOCAL_FILE_TOKEN"}),
                encoding="utf-8",
            )
            config = load_chat_config(project_root=root)
            history = HistoryStore(config.storage)
            service = ChatService(
                config=config,
                history_store=history,
                memory_store=MemoryStore(config.storage),
                provider=DeepSeekChatProvider(config, http_post=fake_post),
                clock=FixedClock(),
                id_generator=SequentialIds(),
            )
            with patch.dict(os.environ, {}, clear=True):
                result = service.send_user_message("你好")
            history_text = "\n".join(
                json.dumps(message.to_dict(), ensure_ascii=False)
                for message in history.load_day(date(2026, 6, 4))
            )

        self.assertTrue(result.provider_result.ok)
        self.assertEqual(captured["headers"]["Authorization"], "Bearer LOCAL_FILE_TOKEN")
        self.assertNotIn("LOCAL_FILE_TOKEN", str(captured["body"]))
        self.assertNotIn("LOCAL_FILE_TOKEN", json.dumps(result.request_payload.to_dict(), ensure_ascii=False))
        self.assertNotIn("LOCAL_FILE_TOKEN", history_text)

    def test_chat_service_selects_fake_and_deepseek_from_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            fake_root = Path(tmp_dir) / "fake"
            fake_config = load_chat_config(project_root=fake_root)
            fake_result = ChatService(
                config=fake_config,
                clock=FixedClock(),
                id_generator=SequentialIds(),
            ).send_user_message("你好")

        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            config_dir = root / "config" / "chat"
            config_dir.mkdir(parents=True)
            (config_dir / "ai_settings.json").write_text(
                json.dumps(
                    {
                        "provider": "deepseek",
                        "api_key_env": "UNIT_TEST_MISSING_DEEPSEEK_KEY",
                    }
                ),
                encoding="utf-8",
            )
            deepseek_config = load_chat_config(project_root=root)
            with patch.dict(os.environ, {}, clear=True):
                deepseek_result = ChatService(
                    config=deepseek_config,
                    clock=FixedClock(),
                    id_generator=SequentialIds(),
                ).send_user_message("你好")

        self.assertEqual(fake_result.provider_result.provider, "fake")
        self.assertEqual(deepseek_result.provider_result.provider, "deepseek")
        self.assertFalse(deepseek_result.provider_result.ok)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = next(path for path in Path(__file__).resolve().parents if (path / "main.py").is_file())
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.chat.config import load_chat_config
from core.chat.providers.deepseek import build_deepseek_messages
from core.chat.providers.fake import FakeChatProvider
from core.chat.service import ChatService
from core.raising.activity import (
    ActivityCatalog,
    ActivityDefinition,
    ActivityProgress,
    ActivitySystem,
)
from core.raising.items import ItemCatalog, ItemDefinition
from core.raising.pet_state import PetState
from core.raising.save_game import SaveGame
from ui.pet_window_parts.chat_context import PetWindowChatContextProvider


class FakeDirector:
    def __init__(self, visual_state: str) -> None:
        self.visual_state = visual_state

    def pet_state(self) -> str:
        return self.visual_state


class PetWindowChatContextProviderTest(unittest.TestCase):
    def test_chat_service_payload_uses_real_pet_window_context_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            config = load_chat_config(project_root=Path(tmp_dir))
            save = _save_game()
            activity_system = ActivitySystem(save, _activity_catalog())
            provider = PetWindowChatContextProvider(
                save_game=save,
                director=FakeDirector("happy"),
                activity_system=activity_system,
                item_catalog=_item_catalog(),
                plugin_active=lambda: True,
                single_active=lambda: False,
                activity_playback_active=lambda: True,
                care_playback_active=lambda: False,
                auto_move_active=lambda: True,
            )
            service = ChatService(
                config=config,
                provider=FakeChatProvider(),
                pet_context_provider=provider,
            )

            result = service.send_user_message("现在状态怎么样")
            payload = result.request_payload
            deepseek_user_payload = json.loads(build_deepseek_messages(payload)[1]["content"])

        self.assertEqual(payload.pet_state["satiety"], 12)
        self.assertEqual(payload.pet_state["mood"], 34)
        self.assertEqual(payload.pet_state["money"], 56)
        self.assertEqual(payload.pet_state["level"], 3)
        self.assertEqual(payload.pet_state["affection"], 9)
        self.assertEqual(payload.pet_state["current_activity"], "学习")
        self.assertEqual(payload.visual_state, "happy")
        self.assertEqual(payload.runtime_state["plugin_active"], True)
        self.assertEqual(payload.runtime_state["single_active"], False)
        self.assertEqual(payload.runtime_state["activity_playback_active"], True)
        self.assertEqual(payload.runtime_state["care_playback_active"], False)
        self.assertEqual(payload.runtime_state["auto_move_active"], True)

        activity = payload.active_activity
        self.assertIsInstance(activity, dict)
        assert isinstance(activity, dict)
        self.assertEqual(activity["is_active"], True)
        self.assertEqual(activity["activity_id"], "study")
        self.assertEqual(activity["name"], "学习")
        self.assertEqual(activity["remaining_seconds"], 90)
        self.assertEqual(activity["progress_percent"], 25)

        inventory = {item["item_id"]: item for item in payload.inventory}
        self.assertEqual(inventory["rice_ball"]["name"], "饭团")
        self.assertEqual(inventory["rice_ball"]["count"], 2)
        self.assertEqual(inventory["rice_ball"]["category"], "food")
        self.assertEqual(inventory["rice_ball"]["type"], "food")
        self.assertEqual(inventory["rice_ball"]["is_care_item"], True)
        self.assertEqual(inventory["mystery_item"]["name"], "mystery_item")
        self.assertEqual(inventory["mystery_item"]["is_care_item"], False)

        self.assertEqual(deepseek_user_payload["pet_state"]["satiety"], 12)
        self.assertEqual(deepseek_user_payload["visual_state"], "happy")
        self.assertEqual(deepseek_user_payload["active_activity"]["activity_id"], "study")
        self.assertEqual(deepseek_user_payload["inventory"][0]["item_id"], "mystery_item")

    def test_visual_state_any_is_normalized_and_private_fields_stay_out(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            config_dir = root / "config" / "chat"
            config_dir.mkdir(parents=True)
            (config_dir / "ai_settings.json").write_text(
                json.dumps({"api_key": "BAD_TOKEN"}, ensure_ascii=False),
                encoding="utf-8",
            )
            config = load_chat_config(project_root=root)
            save = _save_game()
            save.last_saved_at = "/Users/neko/secret/save.json"
            save.status_decay_enabled = True
            provider = PetWindowChatContextProvider(
                save_game=save,
                director=FakeDirector("any"),
                activity_system=ActivitySystem(save, _activity_catalog()),
                item_catalog=_item_catalog(),
            )
            service = ChatService(
                config=config,
                provider=FakeChatProvider(),
                pet_context_provider=provider,
            )

            payload = service.send_user_message("状态").request_payload
            payload_text = json.dumps(payload.to_dict(), ensure_ascii=False)
            deepseek_text = "\n".join(
                message["content"] for message in build_deepseek_messages(payload)
            )

        self.assertEqual(payload.visual_state, "normal")
        self.assertEqual(payload.runtime_state["visual_state"], "normal")
        self.assertNotIn('"visual_state": "any"', payload_text)
        self.assertNotIn("SaveGame", deepseek_text)
        self.assertNotIn("last_saved_at", deepseek_text)
        self.assertNotIn("status_decay_enabled", deepseek_text)
        self.assertNotIn("BAD_TOKEN", deepseek_text)
        self.assertNotIn("/Users/neko", deepseek_text)
        self.assertNotIn("secret/save.json", deepseek_text)


def _save_game() -> SaveGame:
    return SaveGame(
        pet_state=PetState(
            money=56,
            satiety=12,
            mood=34,
            energy=45,
            health=67,
            cleanliness=89,
            level=3,
            affection=9,
            current_activity="待机",
        ),
        inventory={"rice_ball": 2, "mystery_item": 1},
        activity_progress=ActivityProgress("study", elapsed_seconds=30),
    )


def _activity_catalog() -> ActivityCatalog:
    return ActivityCatalog(
        [
            ActivityDefinition(
                id="study",
                name="学习",
                category="专注",
                duration_seconds=120,
                costs={"energy": 5},
                rewards={"exp": 10},
                requirements={},
            )
        ]
    )


def _item_catalog() -> ItemCatalog:
    return ItemCatalog(
        [
            ItemDefinition(
                id="rice_ball",
                name="饭团",
                category="food",
                price=6,
                effects={"satiety": 24},
                description="普通饭团",
                icon="/Users/neko/private/icon.png",
            )
        ]
    )


if __name__ == "__main__":
    unittest.main()

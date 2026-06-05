from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = next(path for path in Path(__file__).resolve().parents if (path / "main.py").is_file())
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.chat.config import load_chat_config
from core.chat.models import EffectKind, EffectRequest
from ui.pet_window_parts.chat_effects import (
    BUSY,
    DISABLED,
    INVALID_VISUAL_STATE,
    NO_CLIP,
    PERFORMED,
    UNAVAILABLE_FOR_VISUAL_STATE,
    UNKNOWN,
    UNSUPPORTED,
    ChatActionEffectExecutor,
)


class FakeClip:
    def __init__(self, action_id: str, source_state: str = "normal") -> None:
        self.action_id = action_id
        self.source_state = source_state
        self.duration_ms = 10


class FakeMode:
    def __init__(self, action_id: str) -> None:
        self.action_id = action_id
        self.start = FakeClip(action_id)
        self.loop = FakeClip(action_id)
        self.end = FakeClip(action_id)
        self.is_phased = True


class FakeCatalog:
    def __init__(
        self,
        *,
        types: dict[str, str] | None = None,
        states: dict[str, set[str]] | None = None,
        any_actions: set[str] | None = None,
    ) -> None:
        self.types = types or {
            "say_self": "phased",
            "say_serious": "phased",
            "say_shining": "phased",
            "say_shy": "phased",
        }
        self.states = states or {
            "say_self": {"happy", "normal", "poor_condition"},
            "say_serious": {"normal"},
            "say_shining": {"normal"},
            "say_shy": {"normal"},
        }
        self.any_actions = any_actions or set()
        self.single_requests: list[tuple[str, str]] = []

    def has_action(self, action_id: str) -> bool:
        return action_id in self.types

    def action_type(self, action_id: str) -> str:
        return self.types[action_id]

    def pet_states_for(self, action_id: str) -> tuple[str, ...]:
        return tuple(sorted(self.states.get(action_id, set())))

    def has_material_fallback(self, action_id: str) -> bool:
        return action_id in self.any_actions

    def _state_has_material(self, action_id: str, pet_state: str) -> bool:
        return pet_state in self.states.get(action_id, set()) or self.has_material_fallback(action_id)

    def is_single_available(self, action_id: str, pet_state: str) -> bool:
        return self.types.get(action_id) == "single" and self._state_has_material(action_id, pet_state)

    def single_for(self, action_id: str, pet_state: str) -> FakeClip:
        self.single_requests.append((action_id, pet_state))
        if not self.is_single_available(action_id, pet_state):
            raise KeyError(action_id)
        return FakeClip(action_id, pet_state)

    def is_mode_available(
        self,
        action_id: str,
        pet_state: str,
        *,
        action_type: str | None = None,
    ) -> bool:
        expected_type = action_type or self.types.get(action_id)
        return expected_type == self.types.get(action_id) and self._state_has_material(action_id, pet_state)


class FakeDirector:
    def __init__(self, pet_state: str = "normal") -> None:
        self.pet_state_value = pet_state
        self.interaction_active = False
        self.visual_override_active = False
        self.active_action_id: str | None = None
        self.started_interactions: list[str] = []
        self.ended_interactions: list[str | None] = []
        self.set_states: list[str] = []

    def pet_state(self) -> str:
        return self.pet_state_value

    def is_interaction_active(self) -> bool:
        return self.interaction_active

    def is_visual_override_active(self) -> bool:
        return self.visual_override_active

    def is_mode_available(self, mode_name: str) -> bool:
        return mode_name.startswith("say_")

    def start_interaction(self, interaction_name: str):
        if self.interaction_active:
            return None
        self.interaction_active = True
        self.active_action_id = interaction_name
        self.started_interactions.append(interaction_name)
        return FakeMode(interaction_name)

    def end_interaction(self) -> None:
        self.ended_interactions.append(self.active_action_id)
        self.interaction_active = False
        self.active_action_id = None

    def debug_snapshot(self):
        if self.interaction_active:
            return SimpleNamespace(source="interaction", action_id=self.active_action_id)
        return SimpleNamespace(source="mode", action_id=None)

    def set_pet_state(self, pet_state: str, *, resume: bool = True) -> None:
        del resume
        self.set_states.append(pet_state)
        self.pet_state_value = pet_state


class FakeSinglePlayer:
    def __init__(self) -> None:
        self.played: list[tuple[FakeClip, bool, bool]] = []
        self.active = False
        self.allow_play = True
        self.finished_callbacks: list[object] = []

    def is_active(self) -> bool:
        return self.active

    def play(
        self,
        clip: FakeClip,
        on_finished=None,
        *,
        resume: bool = True,
        interruptible: bool = False,
    ) -> bool:
        if not self.allow_play:
            return False
        self.active = True
        self.played.append((clip, resume, interruptible))
        self.finished_callbacks.append(on_finished)
        return True


def _executor(
    *,
    director: FakeDirector | None = None,
    catalog: FakeCatalog | None = None,
    single_player: FakeSinglePlayer | None = None,
    action_blocked: bool = False,
    single_active: bool = False,
    automated_action_active: bool = False,
    auto_move_active: bool = False,
    scheduled: list[object] | None = None,
    allowed_action_ids: list[str] | None = None,
) -> ChatActionEffectExecutor:
    scheduled = scheduled if scheduled is not None else []
    return ChatActionEffectExecutor(
        director=director or FakeDirector(),
        animation_catalog=catalog or FakeCatalog(),
        action_blocked=lambda: action_blocked,
        single_active=lambda: single_active,
        automated_action_active=lambda: automated_action_active,
        auto_move_active=lambda: auto_move_active,
        schedule_once=lambda delay_ms, callback: scheduled.append(callback),
        config=load_chat_config(project_root=ROOT),
        single_player=single_player,
        allowed_action_ids=allowed_action_ids,
    )


class ChatActionEffectExecutorTest(unittest.TestCase):
    def test_use_item_effect_is_unsupported(self) -> None:
        executor = _executor(single_player=FakeSinglePlayer())

        reasons = executor.execute((EffectRequest(kind=EffectKind.USE_ITEM, item_id="rice_ball"),))

        self.assertEqual(reasons, (UNSUPPORTED,))

    def test_unknown_and_disabled_actions_are_rejected(self) -> None:
        executor = _executor(
            single_player=FakeSinglePlayer(),
            allowed_action_ids=["say_self"],
        )

        reasons = executor.execute(
            (
                EffectRequest(kind=EffectKind.ACTION, action_id="missing_action"),
                EffectRequest(kind=EffectKind.ACTION, action_id="say_shy"),
            )
        )

        self.assertEqual(reasons, (UNKNOWN, DISABLED))

    def test_visual_state_any_is_invalid_and_does_not_play(self) -> None:
        single = FakeSinglePlayer()
        director = FakeDirector("any")
        executor = _executor(director=director, single_player=single)

        reasons = executor.execute((EffectRequest(kind=EffectKind.ACTION, action_id="say_self"),))

        self.assertEqual(reasons, (INVALID_VISUAL_STATE,))
        self.assertEqual(single.played, [])
        self.assertEqual(director.set_states, [])

    def test_busy_state_rejects_without_playing(self) -> None:
        single = FakeSinglePlayer()
        executor = _executor(single_player=single, auto_move_active=True)

        reasons = executor.execute((EffectRequest(kind=EffectKind.ACTION, action_id="say_self"),))

        self.assertEqual(reasons, (BUSY,))
        self.assertEqual(single.played, [])

    def test_missing_visual_state_material_is_unavailable(self) -> None:
        single = FakeSinglePlayer()
        director = FakeDirector("ill")
        executor = _executor(director=director, single_player=single)

        reasons = executor.execute((EffectRequest(kind=EffectKind.ACTION, action_id="say_self"),))

        self.assertEqual(reasons, (UNAVAILABLE_FOR_VISUAL_STATE,))
        self.assertEqual(single.played, [])

    def test_any_material_fallback_is_used_for_phased_action(self) -> None:
        scheduled: list[object] = []
        director = FakeDirector("normal")
        catalog = FakeCatalog(
            states={"say_self": set()},
            any_actions={"say_self"},
        )
        executor = _executor(
            director=director,
            catalog=catalog,
            scheduled=scheduled,
        )

        reasons = executor.execute((EffectRequest(kind=EffectKind.ACTION, action_id="say_self"),))

        self.assertEqual(reasons, (PERFORMED,))
        self.assertEqual(director.started_interactions, ["say_self"])

    def test_playable_single_uses_single_player_without_setting_visual_state(self) -> None:
        single = FakeSinglePlayer()
        director = FakeDirector("normal")
        catalog = FakeCatalog(
            types={"say_self": "single"},
            states={"say_self": {"normal"}},
        )
        executor = _executor(director=director, catalog=catalog, single_player=single)

        reasons = executor.execute((EffectRequest(kind=EffectKind.ACTION, action_id="say_self"),))

        self.assertEqual(reasons, (PERFORMED,))
        self.assertEqual([clip.action_id for clip, _, _ in single.played], ["say_self"])
        self.assertEqual(single.played[0][1:], (True, False))
        self.assertEqual(director.set_states, [])

    def test_single_action_without_single_player_reports_no_clip(self) -> None:
        catalog = FakeCatalog(
            types={"say_self": "single"},
            states={"say_self": {"normal"}},
        )
        executor = _executor(catalog=catalog)

        reasons = executor.execute((EffectRequest(kind=EffectKind.ACTION, action_id="say_self"),))

        self.assertEqual(reasons, (NO_CLIP,))

    def test_playable_phased_action_uses_interaction_entry(self) -> None:
        scheduled: list[object] = []
        director = FakeDirector("normal")
        executor = _executor(
            director=director,
            scheduled=scheduled,
        )

        reasons = executor.execute((EffectRequest(kind=EffectKind.ACTION, action_id="say_self"),))

        self.assertEqual(reasons, (PERFORMED,))
        self.assertEqual(director.started_interactions, ["say_self"])
        self.assertEqual(director.set_states, [])
        self.assertEqual(len(scheduled), 1)

        scheduled[0]()

        self.assertEqual(director.ended_interactions, ["say_self"])

    def test_unsupported_loop_action_reports_no_clip(self) -> None:
        catalog = FakeCatalog(
            types={"say_self": "loop"},
            states={"say_self": {"normal"}},
        )
        executor = _executor(catalog=catalog)

        reasons = executor.execute((EffectRequest(kind=EffectKind.ACTION, action_id="say_self"),))

        self.assertEqual(reasons, (NO_CLIP,))


if __name__ == "__main__":
    unittest.main()
